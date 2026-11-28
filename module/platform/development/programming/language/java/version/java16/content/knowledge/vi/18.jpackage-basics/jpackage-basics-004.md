# Kiểm tra jpackage --version, --help và tùy chọn của JDK đang dùng

`jpackage` thay đổi và được bổ sung tùy chọn qua các bản JDK. Ngoài ra, một số tùy chọn chỉ có trên Windows, macOS hoặc Linux. Vì vậy, trước khi viết lệnh đóng gói hoặc cập nhật pipeline release, hãy kiểm tra **phiên bản và đường dẫn của chính công cụ đang chạy**, sau đó đọc `jpackage --help` trên hệ điều hành đích.

Hai lệnh cần nhớ:

- `jpackage --version` in phiên bản của công cụ đóng gói.
- `jpackage --help` in hướng dẫn và danh sách tùy chọn hợp lệ cho phiên bản công cụ cùng nền tảng hiện tại.

Đây là cách kiểm tra trực tiếp, nhanh và có thể lặp lại. Không nên sao chép một tùy chọn từ tài liệu của JDK mới hơn rồi giả định JDK đang cài cũng hỗ trợ nó. Bài học thuộc chương **jpackage cơ bản** của module **JAVA_VERSION_JAVA16**, tập trung vào cách kiểm tra công cụ chính thức từ Java 16 và chọn tài liệu tương ứng với JDK đang dùng trong Java hiện đại.

Từ JDK 16, `jpackage` là công cụ đóng gói chính thức, thuộc module `jdk.jpackage`. Khi dùng JDK 16 trở lên, gọi executable `jpackage` trực tiếp; không dùng tên module incubator `jdk.incubator.jpackage` của các bản thử nghiệm trước đó.

## 1. Phân biệt phiên bản JDK, phiên bản jpackage và phiên bản ứng dụng

Ba thông tin dưới đây có ý nghĩa khác nhau:

| Thông tin | Cách kiểm tra hoặc khai báo | Ý nghĩa |
| --- | --- | --- |
| Phiên bản Java runtime/JDK | `java --version` | Phiên bản của lệnh Java đang được shell tìm thấy |
| Phiên bản công cụ đóng gói | `jpackage --version` | Phiên bản của chính công cụ `jpackage` đang chạy |
| Phiên bản ứng dụng được đóng gói | `jpackage --app-version 1.2.0` | Metadata phiên bản của ứng dụng/package đầu ra |

Ví dụ, máy có thể dùng JDK 25 để chạy `jpackage` nhưng ứng dụng được đặt metadata phiên bản là `1.2.0`. Giá trị `--app-version` không thay đổi phiên bản JDK, không đổi bytecode và cũng không chọn runtime Java cho ứng dụng.

`jpackage --version` chỉ xác nhận phiên bản sản phẩm của công cụ. Để xác định công cụ thuộc bộ JDK nào trên máy, cần kiểm tra thêm đường dẫn executable và so sánh với `JAVA_HOME`.

## 2. Kiểm tra trên Windows bằng PowerShell

Mở PowerShell và chạy:

```powershell
java --version
javac --version
jpackage --version
```

Ba lệnh này cho biết phiên bản của các công cụ mà shell đang tìm thấy. Tiếp theo, xác định chính xác đường dẫn:

```powershell
Get-Command java, javac, jpackage -All |
    Select-Object Name, Source

where.exe java
where.exe javac
where.exe jpackage
```

`Get-Command -All` và `where.exe` giúp phát hiện trường hợp máy có nhiều JDK trong `PATH`. Ví dụ, `java` có thể đến từ JDK 25 nhưng `jpackage` lại được tìm thấy trong thư mục `bin` của JDK 21 nếu cấu hình môi trường không đồng nhất.

Kiểm tra `JAVA_HOME`:

```powershell
$env:JAVA_HOME
Test-Path "$env:JAVA_HOME\bin\java.exe"
Test-Path "$env:JAVA_HOME\bin\javac.exe"
Test-Path "$env:JAVA_HOME\bin\jpackage.exe"
```

Nếu `JAVA_HOME` trỏ tới JDK mong muốn, có thể gọi trực tiếp công cụ trong thư mục đó để tránh phụ thuộc thứ tự `PATH`:

```powershell
& "$env:JAVA_HOME\bin\java.exe" --version
& "$env:JAVA_HOME\bin\javac.exe" --version
& "$env:JAVA_HOME\bin\jpackage.exe" --version
& "$env:JAVA_HOME\bin\jpackage.exe" --help
```

Nếu `JAVA_HOME` chưa được đặt, hãy lấy đường dẫn từ `Get-Command` hoặc `where.exe`, xác định thư mục JDK tương ứng rồi gọi executable bằng đường dẫn đầy đủ.

## 3. Kiểm tra trên Linux và macOS

Trên Linux hoặc macOS, dùng shell để xác định các lệnh đang được phân giải:

```bash
java --version
javac --version
jpackage --version

type -a java javac jpackage
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
```

`type -a` liệt kê các vị trí shell có thể tìm thấy. Nếu `JAVA_HOME` đã trỏ tới JDK cần dùng, gọi trực tiếp:

```bash
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/javac" --version
"$JAVA_HOME/bin/jpackage" --version
"$JAVA_HOME/bin/jpackage" --help
```

Trên một số hệ thống, nhiều JDK được cài song song và lệnh `java` mặc định có thể do package manager hoặc cơ chế alternatives chọn. Vì vậy, cần xác nhận đường dẫn `jpackage` thực tế thay vì chỉ nhìn phiên bản `java`.

## 4. Đọc trợ giúp bằng --help

Chạy:

```bash
jpackage --help
```

Lệnh này in usage và danh sách tùy chọn hợp lệ cho **phiên bản `jpackage` đang chạy trên nền tảng hiện tại**, sau đó thoát. Nó không build ứng dụng, không tạo application image và không cài package.

`--help` hữu ích khi:

- Cần xem cú pháp và tham số của một tùy chọn.
- Không chắc JDK hiện tại có hỗ trợ tùy chọn mới hay không.
- Muốn biết tùy chọn nào chỉ xuất hiện trên hệ điều hành hiện tại.
- Cần kiểm tra script đóng gói sau khi đổi JDK hoặc nâng cấp runner.
- Muốn xác nhận tên định dạng package mà công cụ hiện tại chấp nhận.

Điểm cần nhớ: `jpackage --help` trên Windows chỉ hiển thị các tùy chọn dành cho Windows cùng các tùy chọn chung. Chạy trên macOS hoặc Linux sẽ hiển thị nhóm tùy chọn nền tảng tương ứng. Một lần gọi `--help` trên Windows không thể xác nhận đầy đủ tùy chọn dành cho macOS hoặc Linux.

## 5. Lưu trợ giúp để tra cứu và so sánh

Trên Windows PowerShell:

```powershell
jpackage --help | Out-File -FilePath .\jpackage-help.txt -Encoding utf8
```

Tìm một tùy chọn cụ thể:

```powershell
Select-String -Path .\jpackage-help.txt -Pattern '--app-content'
Select-String -Path .\jpackage-help.txt -Pattern '--win-shortcut'
Select-String -Path .\jpackage-help.txt -Pattern '--jlink-options'
```

Trên Linux hoặc macOS:

```bash
jpackage --help > jpackage-help.txt 2>&1
grep -n -- '--app-content' jpackage-help.txt
grep -n -- '--jlink-options' jpackage-help.txt
```

Nếu lệnh tìm kiếm không có kết quả, tùy chọn đó không xuất hiện trong trợ giúp của công cụ hiện tại. Hãy kiểm tra tài liệu đúng phiên bản JDK, hệ điều hành và kiểu package trước khi quyết định cách thay thế.

Lưu bản trợ giúp theo từng runner hoặc từng JDK trong quy trình release giúp đội phát triển nhận ra thay đổi khi nâng cấp JDK. Không nên dùng file trợ giúp cũ làm bằng chứng rằng công cụ trên máy hiện tại vẫn có cùng tùy chọn.

## 6. Các nhóm tùy chọn thường thấy trong --help

Tùy chọn của `jpackage` được chia theo công việc. Tên và phạm vi cụ thể có thể khác theo bản JDK:

| Nhóm | Tùy chọn tiêu biểu | Mục đích |
| --- | --- | --- |
| Thông tin và đầu ra chung | `--version`, `--help`, `--verbose`, `--name`, `--type`, `--dest` | Xem phiên bản, trợ giúp, tên và nơi lưu package |
| Runtime image | `--module-path`, `--add-modules`, `--jlink-options`, `--runtime-image` | Chọn module hoặc runtime đi kèm |
| Application payload | `--input`, `--app-content` | Chọn file ứng dụng và nội dung bổ sung |
| Launcher | `--main-jar`, `--main-class`, `--module`, `--java-options`, `--arguments`, `--add-launcher` | Chỉ định điểm vào và cấu hình launcher |
| Installer | `--app-image`, `--license-file`, `--install-dir`, `--file-associations` | Tạo package từ image và tùy chỉnh cài đặt |
| Nền tảng | `--win-*`, `--mac-*`, `--linux-*` | Tùy chỉnh installer hoặc launcher theo OS |

Không phải tùy chọn nào cũng có mặt trong mọi JDK. Bảng này giúp nhận diện nhóm chức năng; danh sách `--help` của JDK đang dùng mới là căn cứ để biết tùy chọn có sẵn trong môi trường đó.

## 7. Nhận diện tùy chọn chung và tùy chọn theo hệ điều hành

`jpackage` có một nhóm tùy chọn chung và các nhóm dành riêng cho hệ điều hành:

| Nền tảng | Ví dụ tùy chọn | Ý nghĩa |
| --- | --- | --- |
| Windows | `--win-console`, `--win-menu`, `--win-shortcut` | Launcher console, Start Menu và shortcut |
| macOS | `--mac-package-identifier`, `--mac-sign`, `--mac-entitlements` | Định danh bundle và ký ứng dụng |
| Linux | `--linux-package-name`, `--linux-deb-maintainer`, `--linux-shortcut` | Metadata package và shortcut |

Các ví dụ trên là những tên tùy chọn có trong tài liệu JDK tương ứng; danh sách chính xác cần đối chiếu với `--help` của bản JDK và hệ điều hành build. Không thêm tùy chọn `--win-*` vào lệnh chạy trên Linux rồi kỳ vọng nó hoạt động, hoặc dùng tùy chọn ký macOS trên Windows.

Ngoài tùy chọn, định dạng native package cũng phụ thuộc nền tảng. Ví dụ, Windows tạo `msi` hoặc `exe`; macOS tạo `pkg` hoặc `dmg`; Linux tạo `deb` hoặc `rpm`. `jpackage` không phải công cụ cross-platform để tạo installer cho một OS khác từ máy hiện tại.

## 8. Tùy chọn có thể thay đổi giữa các phiên bản JDK

Khi nâng cấp JDK, cần kiểm tra lại các lệnh đóng gói thay vì giả định danh sách tùy chọn không đổi. Có ba kiểu thay đổi cần chú ý:

1. **Tùy chọn mới:** một JDK hiện đại có thể bổ sung khả năng chưa có trong JDK cũ.
2. **Tùy chọn thay đổi hoặc bị loại bỏ:** tên, cú pháp hoặc cách hoạt động có thể thay đổi theo phiên bản.
3. **Hành vi mặc định thay đổi:** cùng một lệnh có thể tạo runtime hoặc package với nội dung khác khi JDK được nâng cấp.

Ví dụ, `--app-content` xuất hiện trong tài liệu `jpackage` hiện đại để thêm file hoặc thư mục vào application payload. Không nên mặc định JDK cũ nào cũng nhận tùy chọn này; hãy kiểm tra trợ giúp của chính công cụ đang chạy.

Một thay đổi hành vi đáng chú ý: từ JDK 25, runtime image do `jpackage` tạo không tự động bao gồm service bindings như các bản trước. Ứng dụng cần provider được tìm thấy qua service binding có thể cần truyền `--bind-services` qua `--jlink-options`. Khi nâng cấp JDK, hãy kiểm tra lại chức năng `ServiceLoader` trên runtime được đóng gói, kể cả khi lệnh cũ vẫn chạy thành công.

Vì vậy, cần đọc cả usage của `--help` và tài liệu phát hành đúng phiên bản. `--help` cho biết tùy chọn được nhận; tài liệu phiên bản giải thích đầy đủ ý nghĩa, mặc định và thay đổi hành vi.

## 9. Tra cứu tài liệu đúng phiên bản

Ưu tiên tài liệu Oracle/OpenJDK khớp với JDK mà pipeline dùng:

| Phiên bản cần đối chiếu | Tài liệu |
| --- | --- |
| JDK 16 | `jpackage` man page và Packaging Tool User's Guide của Java SE 16 |
| JDK 17 | `jpackage` man page của Java SE 17 |
| JDK 25 | `jpackage` man page và Packaging Overview của Java SE 25 |
| JDK 26 | `jpackage` man page và Packaging Overview của Java SE 26 |

Nếu JDK đang dùng là bản khác trong bảng, hãy thay số phiên bản trong URL tài liệu bằng release tương ứng. Tránh lấy tài liệu của bản early-access làm căn cứ cho JDK production đã cài.

Khi đọc man page, tập trung vào:

- Synopsis và mô tả công cụ.
- Danh sách generic options.
- Tùy chọn tạo runtime image.
- Tùy chọn tạo application image và launcher.
- Tùy chọn tạo installer.
- Nhóm tùy chọn riêng cho Windows, macOS và Linux.
- Examples và ghi chú về mặc định.

## 10. Quy trình kiểm tra trước khi sửa script đóng gói

Khi nhận một pipeline cũ hoặc chuẩn bị nâng cấp JDK, làm theo thứ tự:

1. Ghi nhận hệ điều hành, kiến trúc và shell của runner.
2. Chạy `java --version`, `javac --version` và `jpackage --version`.
3. Xác định đường dẫn executable bằng `Get-Command`/`where.exe` trên Windows hoặc `type -a` trên Linux/macOS.
4. Xác nhận `JAVA_HOME` trỏ tới JDK mong muốn và gọi `jpackage` trực tiếp từ JDK đó.
5. Lưu output `jpackage --help` của môi trường.
6. Đối chiếu mọi tùy chọn script đang dùng với output và tài liệu cùng phiên bản.
7. Kiểm tra thay đổi mặc định có thể ảnh hưởng runtime hoặc installer.
8. Chạy thử tạo `app-image`, khởi chạy launcher và kiểm tra package trên OS đích.

Đừng bắt đầu bằng cách sửa tất cả tùy chọn theo một bài viết trên Internet. Trước hết, cần biết công cụ thật sự đang được pipeline gọi là bản nào và nó hỗ trợ gì.

## 11. Ví dụ kiểm tra một tùy chọn trước khi dùng

Giả sử script muốn dùng `--app-content` để đưa thư mục template vào application payload. Trên PowerShell:

```powershell
$jpackageHelp = jpackage --help 2>&1 | Out-String

if ($jpackageHelp -match '--app-content') {
    Write-Host 'The current jpackage lists --app-content.'
} else {
    Write-Host 'The current jpackage does not list --app-content.'
}
```

Kết quả giúp xác nhận tùy chọn có xuất hiện trong usage của công cụ hiện tại. Sau đó vẫn cần đọc tài liệu tương ứng để kiểm tra cú pháp, loại đường dẫn, số lần dùng được phép và giới hạn theo nền tảng.

Kiểm tra tương tự với tùy chọn runtime:

```powershell
$jpackageHelp | Select-String -Pattern '--runtime-image'
$jpackageHelp | Select-String -Pattern '--jlink-options'
$jpackageHelp | Select-String -Pattern '--add-modules'
```

Đừng suy luận rằng một tùy chọn hoạt động chỉ vì chuỗi tên của nó xuất hiện trong output: usage có thể mô tả option nhưng lệnh cụ thể vẫn cần giá trị hợp lệ, đúng mode và đúng OS.

## 12. Lưu ý khi dùng file chứa tùy chọn

`jpackage` hỗ trợ đọc tùy chọn từ file bằng cú pháp `@filename`. Cách này giúp tách lệnh dài khỏi script:

```text
jpackage-options.txt
  --type
  app-image
  --name
  Demo
  --input
  build/input
  --main-jar
  demo.jar
```

Sau đó gọi:

```bash
jpackage @jpackage-options.txt
```

Khi dùng option file, cần kiểm tra cú pháp và cách phân tách giá trị theo tài liệu của JDK đang chạy. Không giả định mọi cú pháp quoting của PowerShell, Bash và file option đều giống nhau. Đưa file option vào kiểm soát phiên bản và kiểm thử nó trên đúng OS/runner.

## 13. Các lỗi thường gặp khi đọc --version và --help

| Triệu chứng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| `jpackage` không được nhận diện | JDK không nằm trong `PATH` hoặc đang dùng runtime không có công cụ | Kiểm tra `JAVA_HOME` và đường dẫn `bin` |
| `jpackage --version` khác phiên bản `java --version` | Hai executable đến từ hai JDK khác nhau | Kiểm tra `Get-Command`/`where.exe` hoặc `type -a` |
| Tùy chọn không có trong `--help` | JDK hiện tại chưa hỗ trợ hoặc tùy chọn chỉ dành cho OS khác | Dùng tùy chọn được hỗ trợ hoặc nâng cấp JDK có chủ đích |
| Tùy chọn có trong tài liệu nhưng không có trên máy | Đang đọc tài liệu của JDK khác phiên bản | Mở man page đúng release và kiểm tra đường dẫn executable |
| Không thấy `--win-*` trên Linux | `--help` chỉ hiển thị tùy chọn nền tảng hiện tại | Chạy kiểm tra trên Windows runner |
| Lệnh cũ chạy nhưng runtime thay đổi sau nâng cấp | Hành vi mặc định đã đổi giữa các JDK | Đọc release notes, kiểm thử runtime và service provider |
| `--help` hiển thị option nhưng lệnh đóng gói thất bại | Sai giá trị, sai mode hoặc thiếu prerequisite hệ thống | Kiểm tra mô tả đầy đủ của option và log `--verbose` |

## 14. Bài tập tự kiểm tra

Một pipeline Windows được nâng từ JDK 17 lên JDK 25. Script cũ dùng `--win-shortcut` và `--jlink-options`. Sau khi nâng cấp, nhóm phát triển muốn thêm `--app-content`.

Hãy trả lời:

1. Lệnh nào xác nhận phiên bản công cụ đóng gói thực tế?
2. Lệnh nào liệt kê các tùy chọn được hỗ trợ trên Windows runner hiện tại?
3. Vì sao chỉ chạy `java --version` chưa đủ để xác nhận `jpackage` đến từ cùng JDK?
4. Nếu `--app-content` không xuất hiện trong output `--help`, bước tiếp theo nên là gì?
5. Vì sao cần kiểm thử lại runtime khi nâng từ JDK 17 lên JDK 25 dù script vẫn chấp nhận cú pháp cũ?
6. Có thể dùng output `jpackage --help` trên Windows để xác nhận `--mac-sign` được hỗ trợ trên macOS không?

**Đáp án:**

1. `jpackage --version`.
2. `jpackage --help` chạy bằng đúng executable trên Windows runner.
3. Vì `java` và `jpackage` có thể được phân giải từ các thư mục JDK khác nhau trong `PATH`; cần kiểm tra đường dẫn từng executable.
4. Đối chiếu man page của đúng JDK và xác nhận phiên bản công cụ. Nếu JDK không hỗ trợ, không dùng option đó trên môi trường hiện tại.
5. Vì từ JDK 25, runtime image do `jpackage` tạo thay đổi hành vi service binding; ứng dụng dùng `ServiceLoader` có thể cần `--bind-services`.
6. Không. Trợ giúp hiển thị tùy chọn dành cho nền tảng đang chạy; cần kiểm tra trên macOS runner hoặc tài liệu đúng nền tảng.

## Ghi nhớ

**Luôn kiểm tra `jpackage --version` và `jpackage --help` từ đúng JDK, đúng executable và đúng hệ điều hành trước khi viết hoặc nâng cấp script đóng gói.** `--version` xác nhận phiên bản công cụ; `--help` cho biết usage và tùy chọn được công cụ hiện tại chấp nhận trên nền tảng hiện tại. So sánh đường dẫn `java`, `javac`, `jpackage` với `JAVA_HOME`, đọc tài liệu cùng release, rồi kiểm thử application image và installer. Không lấy danh sách option của JDK mới hơn làm bảo đảm cho JDK cũ.

## Tài liệu tham khảo

- [Oracle Java SE 16 — The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Oracle Java SE 17 — The jpackage Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html)
- [Oracle Java SE 25 — The jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html)
- [Oracle Java SE 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Oracle Java SE 26 — Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392)
