param([string]$Out = "D:\VPN\tools\screen.png", [string]$Title = "QuChen VPN")
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class W5 {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out R r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [StructLayout(LayoutKind.Sequential)] public struct R { public int L, T, Rr, B; }
}
'@
$script:h = [IntPtr]::Zero
[W5]::EnumWindows({ param($h, $l)
  $sb = New-Object System.Text.StringBuilder 256
  [W5]::GetWindowText($h, $sb, 256) | Out-Null
  if ($sb.ToString() -eq $Title) { $script:h = $h; return $false }
  return $true
}, [IntPtr]::Zero) | Out-Null
if ($script:h -eq [IntPtr]::Zero) { "no-window"; exit 1 }
[W5]::ShowWindow($script:h, 9) | Out-Null
[W5]::SetForegroundWindow($script:h) | Out-Null
Start-Sleep -Milliseconds 900
$r = New-Object W5+R
[W5]::GetWindowRect($script:h, [ref]$r) | Out-Null
$w = $r.Rr - $r.L; $ht = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $ht
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size $w, $ht))
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
"saved $Out  fg=$([W5]::GetForegroundWindow() -eq $script:h)"
