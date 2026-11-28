# Dùng `@argfile` để quản lý cấu hình đóng gói dài và quoting

`jpackage` tạo application image hoặc gói cài đặt từ ứng dụng Java và runtime image. Một lệnh đóng gói thực tế có thể chứa nhiều đường dẫn, metadata, module, launcher, JVM option và tùy chọn `jlink`. Khi lệnh dài, khó review hoặc cần dùng lại trong CI, hãy chuyển các đối số sang file cấu hình và gọi `jpackage @filename`.

Java 16 đã hỗ trợ `@filename` trong `jpackage`. File này chứa các option và giá trị của chúng; có thể truyền nhiều file argument trong cùng một lần gọi. Cách làm giúp quản lý cấu hình có thể review bằng Git, nhưng vẫn cần viết đúng quy tắc tách token và quoting của jpackage.

## 1. `@argfile` giải quyết vấn đề gì?

Không dùng file, một lệnh có thể dài và khó đọc:

```powershell
jpackage --type app-image --name AcmeDesk --app-version 1.4.2 --vendor "Acme Corp" --input "build\package input" --main-jar "acme desk.jar" --main-class com.acme.Main --dest "build\dist" --icon "packaging\acme desk.ico" --java-options "-Dfile.encoding=UTF-8"
```

Đưa các đối số vào `packaging.args` rồi chạy:

```powershell
jpackage '@packaging.args'
```

Trên Linux hoặc macOS:

```bash
jpackage @packaging.args
```

Trong PowerShell, đặt `@packaging.args` trong dấu nháy đơn để truyền nguyên token cho chương trình native. File argument được jpackage đọc và mở rộng thành danh sách đối số trước khi xử lý các option.

## 2. Cấu trúc cơ bản của file argument

Nên viết mỗi option và giá trị của nó trên một dòng riêng. Cách này dễ rà soát và giảm nguy cơ gộp nhầm hai giá trị:

```text
# Metadata của ứng dụng
--type
app-image
--name
AcmeDesk
--app-version
1.4.2
--vendor
Acme Corporation

# Nguồn ứng dụng và thư mục kết quả
--input
build/input
--main-jar
acme-desk.jar
--main-class
com.acme.Main
--dest
build/dist
```

Các quy tắc thực hành:

- Khoảng trắng và xuống dòng phân tách các token.
- Có thể đặt option và giá trị cùng dòng, nhưng tách riêng từng dòng thường dễ đọc hơn.
- Dùng dấu nháy đơn hoặc nháy kép để gom một giá trị có khoảng trắng thành một token.
- Có thể đặt dòng chú thích bắt đầu bằng `#`; nên để comment trên dòng riêng.
- Không thêm dấu `\` cuối dòng theo thói quen nối lệnh của shell. Mỗi dòng trong file đã là một phần của danh sách đối số.

File argument của jpackage là file đối số dành cho chính công cụ đóng gói. Không mặc định mọi quy tắc của `java @argfile` đều áp dụng giống hệt cho nó.

## 3. Quoting đường dẫn có khoảng trắng

Nếu đường dẫn chứa khoảng trắng, đặt toàn bộ giá trị trong một cặp dấu nháy:

```text
--input
"build/package input"
--dest
"build/package output"
--main-jar
"Acme Desktop.jar"
```

Jpackage nhận mỗi đường dẫn trên thành một đối số duy nhất. Nếu bỏ dấu nháy, parser có thể tách đường dẫn tại khoảng trắng và coi phần còn lại là một option hoặc giá trị khác.

Trên Windows, khi dùng dấu gạch chéo ngược trong giá trị được đặt trong dấu nháy, hãy escape dấu gạch chéo ngược theo quy tắc command file:

```text
--input
"C:\Build Area\Acme\input"
--dest
"C:\Build Area\Acme\output"
--icon
"C:\Build Area\Acme\assets\app.ico"
```

Trong file, mỗi dấu gạch chéo ngược cần được viết thành hai dấu liên tiếp bên trong quoted path; parser khôi phục một dấu trong đường dẫn sau khi xử lý.

## 4. Quoting hai lớp cho `--arguments`

`--arguments` cấu hình các đối số mặc định truyền cho `main(String[] args)` khi người dùng khởi chạy ứng dụng mà không truyền đối số riêng. Nếu một đối số ứng dụng có khoảng trắng, cần giữ lại lớp dấu nháy bên trong để launcher tạo ra đúng một phần tử trong mảng `args`.

Ví dụ muốn truyền một đối số duy nhất có giá trị `profile=desktop mode`:

```text
--arguments
"'profile=desktop mode'"
```

Dấu nháy kép bên ngoài gom toàn bộ giá trị thành một token cho jpackage. Dấu nháy đơn bên trong được giữ lại trong giá trị để launcher hiểu cụm có khoảng trắng là một đối số. Tài liệu jpackage cũng minh họa cách lồng dấu nháy đơn bên trong dấu nháy kép hoặc dấu nháy kép đã escape.

Có thể khai báo nhiều đối số mặc định bằng nhiều lần `--arguments`:

```text
--arguments
--mode
--arguments
"'desktop mode'"
--arguments
--config
```

Khi kiểm tra kết quả, hãy xác nhận ứng dụng nhận đúng số phần tử và đúng nội dung từng phần tử trong `args`. Đừng chỉ nhìn chuỗi hiển thị trong terminal vì một chuỗi có khoảng trắng có thể bị tách thành nhiều đối số.

Lưu ý: các giá trị mặc định từ `--arguments` được dùng khi người dùng không truyền đối số lúc chạy launcher. Nếu người dùng truyền đối số riêng, launcher sử dụng các đối số đó theo hợp đồng của jpackage.

## 5. Quoting hai lớp cho `--java-options`

`--java-options` cấu hình JVM option được áp dụng khi launcher khởi chạy JVM. Nó không truyền đối số cho `main()`. Nếu giá trị của một system property có khoảng trắng, hãy giữ nguyên nó thành một JVM option:

```text
--java-options
"'-Dapp.display-name=Acme Desktop'"
--java-options
-Dfile.encoding=UTF-8
--java-options
Xms256m
```

Trong ví dụ, option thứ nhất chứa một giá trị có khoảng trắng; lớp dấu nháy bên trong giữ nó thành một JVM argument duy nhất. Các option không có khoảng trắng có thể viết trực tiếp. Có thể lặp lại `--java-options` để khai báo từng option riêng.

Không nhầm lẫn:

| Option | Đích nhận giá trị |
| --- | --- |
| `--arguments` | Ứng dụng Java, thông qua `main(String[] args)`. |
| `--java-options` | JVM, trước khi ứng dụng bắt đầu chạy. |

Nếu một JVM option cần chứa cả dấu nháy, dấu gạch chéo hoặc ký tự đặc biệt, hãy thử trên đúng JDK và hệ điều hành mục tiêu rồi kiểm tra cấu hình launcher được sinh ra. Tránh đoán số lớp escape bằng cách sao chép nguyên xi một lệnh từ Bash sang PowerShell hoặc ngược lại.

## 6. Quoting giá trị gồm nhiều option con

Một số option của jpackage nhận một chuỗi chứa nhiều giá trị con. Ví dụ `--jlink-options` nhận danh sách option được chuyển tiếp cho `jlink`:

```text
--jlink-options
"--strip-debug --no-man-pages --no-header-files"
```

Ở đây, toàn bộ chuỗi là giá trị của một option jpackage; jpackage phân tích chuỗi đó thành các tùy chọn dành cho jlink. Không tách các option con thành các option jpackage độc lập.

Tương tự, `--module-path` có thể chứa nhiều đường dẫn phân tách bằng dấu phân cách path của nền tảng. Hãy dùng đúng dấu phân cách của hệ điều hành đang build:

| Hệ điều hành | Dấu phân cách path |
| --- | --- |
| Windows | `;` |
| Linux, macOS | `:` |

Nếu một thành phần đường dẫn có khoảng trắng, cần quote giá trị đầy đủ và kiểm tra cách jpackage nhận path list trên nền tảng đó.

## 7. Ví dụ file cấu hình hoàn chỉnh

Ví dụ sau tạo application image từ ứng dụng không modular. Giả sử thư mục input chứa file JAR chính và các dependency cần đóng gói:

```text
# Loại output và metadata
--type
app-image
--name
AcmeDesk
--app-version
1.4.2
--vendor
Acme Corporation
--description
Acme desktop client

# Input và entry point
--input
"build/package input"
--main-jar
"Acme Desktop.jar"
--main-class
com.acme.desktop.Main

# Tài nguyên và output
--icon
"packaging/Acme Desktop.ico"
--dest
"build/package output"

# Runtime options
--java-options
-Dfile.encoding=UTF-8
--java-options
"'-Dapp.display-name=Acme Desktop'"
--arguments
"'--profile=desktop mode'"

# Tùy chọn runtime image
--jlink-options
"--strip-debug --no-man-pages --no-header-files"

--verbose
```

Lưu nội dung thành `packaging.args`. Chạy từ thư mục gốc dự án:

```powershell
jpackage '@packaging.args'
```

Hoặc trên Linux/macOS:

```bash
jpackage @packaging.args
```

Trong ví dụ, `--main-jar` là đường dẫn tương đối bên trong thư mục `--input`; các đường dẫn `--input`, `--icon` và `--dest` được diễn giải theo working directory của lệnh đóng gói. Hãy sửa các giá trị theo cấu trúc dự án thực tế.

## 8. Dùng nhiều file argument

Jpackage cho phép dùng nhiều `@filename` trong cùng một lần gọi. Có thể tách cấu hình chung và cấu hình theo nền tảng:

```text
# common.args
--name
AcmeDesk
--app-version
1.4.2
--input
build/input
--main-jar
acme-desk.jar
--main-class
com.acme.Main
```

```text
# linux-image.args
--type
app-image
--dest
build/linux
```

Gọi cả hai file:

```bash
jpackage @common.args @linux-image.args
```

Các file được mở rộng theo thứ tự xuất hiện trên command line. Nên để mỗi file chịu trách nhiệm cho một nhóm cấu hình rõ ràng và tránh khai báo trùng option đơn trị nếu không có chủ đích. Những option được tài liệu cho phép lặp như `--java-options`, `--arguments` hoặc `--add-modules` có thể được lặp theo đúng ý nghĩa của chúng.

Không coi `@file` là cơ chế include đệ quy. Hãy truyền các file cần dùng trực tiếp trên command line thay vì đặt một dòng `@another.args` bên trong file cấu hình rồi mong jpackage tự mở rộng tiếp.

## 9. Đường dẫn được tính từ đâu?

Có hai loại đường dẫn cần phân biệt:

1. **Đường dẫn của file argument:** `@packaging.args` được tìm theo working directory của tiến trình đang chạy jpackage.
2. **Đường dẫn nằm trong option:** các path như `--input`, `--dest`, `--icon`, `--runtime-image` và `--module-path` thường là tuyệt đối hoặc tương đối với current working directory, không tự động tương đối với thư mục chứa file argument.

Ví dụ cấu trúc:

```text
project/
  packaging/
    packaging.args
  build/
    input/
      app.jar
```

Nếu chạy từ thư mục `project`, file có thể ghi `--input build/input`. Nếu chạy từ thư mục cha, giá trị tương đối đó sẽ trỏ tới vị trí khác. Vì vậy:

- Chọn một working directory thống nhất trong script build và CI.
- Hoặc dùng đường dẫn tuyệt đối cho các path quan trọng.
- Ghi rõ trong tài liệu build nơi cần chạy lệnh.
- Không giả định path trong file argument được resolve tương đối với chính file đó.

Riêng `--main-jar` của ứng dụng không modular là đường dẫn tương đối với input directory theo hợp đồng của option này.

## 10. Phân biệt `@argfile` với file cấu hình khác của jpackage

`@argfile` chứa các đối số dòng lệnh của chính lệnh `jpackage`. Một số option khác lại nhận file có định dạng riêng:

| Option | File được truyền vào | Mục đích |
| --- | --- | --- |
| `@packaging.args` | File argument | Chứa option và giá trị của lệnh jpackage. |
| `--add-launcher` | File Properties | Cấu hình launcher phụ, ví dụ main class, arguments hoặc java-options. |
| `--file-associations` | File Properties | Cấu hình phần mở rộng, MIME type, icon và mô tả liên kết file. |
| `--resource-dir` | Thư mục tài nguyên | Ghi đè template, icon hoặc resource của jpackage. |

Không đưa nội dung dạng `key=value` của file Properties vào `@argfile` rồi mong jpackage tự hiểu đó là cấu hình launcher. Trong argument file, phải gọi option tương ứng và truyền đường dẫn đến file riêng.

## 11. Các lỗi quoting thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Path bị tách thành nhiều token | Giá trị có khoảng trắng nhưng không được quote. | Đặt toàn bộ path trong một cặp dấu nháy. |
| Windows path mất dấu `\` | Dấu gạch chéo ngược trong quoted value bị parser xem là escape. | Escape thành `\` trong file hoặc dùng cách viết path phù hợp đã kiểm thử. |
| `main()` nhận nhiều phần tử thay vì một | Chỉ có lớp quote ngoài cho jpackage, không giữ lớp quote cho launcher. | Dùng nested quoting cho `--arguments`. |
| JVM option bị tách tại khoảng trắng | Giá trị `--java-options` chưa được quote đúng hai lớp. | Dùng nested quoting và kiểm tra launcher config. |
| File không được tìm thấy | Đường dẫn `@filename` tính từ working directory khác dự kiến. | Chạy từ thư mục đã quy định hoặc truyền path tuyệt đối. |
| Option không được nhận diện | Dùng option không có trong phiên bản JDK hoặc loại package hiện tại. | Chạy `jpackage --help` bằng đúng JDK build target. |
| File argument thứ hai không được mở rộng | Đặt `@other.args` bên trong file đầu và mong có include đệ quy. | Truyền từng `@file` trực tiếp trên command line. |
| Gói native không tạo được trên OS khác | Jpackage không hỗ trợ cross-platform packaging. | Build loại package native trên nền tảng đích. |

## 12. Xác minh cấu hình trước khi phát hành

Không nên chỉ dựa vào việc lệnh trả exit code 0. Hãy kiểm tra cả application image và hành vi launcher:

1. Chạy `jpackage --version` và `jpackage --help` bằng đúng JDK dùng trong build.
2. Tạo `app-image` trước để kiểm tra cấu hình đóng gói mà chưa cần tạo installer native.
3. Dùng `--verbose` để xem tiến trình và các lệnh công cụ con khi cần chẩn đoán.
4. Kiểm tra thư mục input, main JAR, icon, runtime image và thư mục output thực sự tồn tại.
5. Kiểm tra file cấu hình launcher được sinh trong application image, đặc biệt các mục `ArgOptions` và `JavaOptions`.
6. Chạy launcher không truyền đối số để kiểm tra default arguments.
7. Chạy launcher với đối số tường minh để xác nhận hành vi override.
8. Kiểm tra system property và JVM option trong ứng dụng để xác nhận quoting giữ nguyên giá trị có khoảng trắng.
9. Chỉ sau khi application image chạy đúng mới tạo gói cài đặt phù hợp với OS đích.

Jpackage hỗ trợ các loại output như `app-image`, `exe`, `msi`, `rpm`, `deb`, `pkg` và `dmg` tùy nền tảng. Mỗi định dạng native cần được build trên nền tảng tương ứng; file argument dùng chung không làm cho jpackage trở thành công cụ cross-compile installer.

## 13. Quy trình đề xuất cho dự án

Một cách tổ chức có thể duy trì lâu dài:

```text
packaging/
  common.args
  windows.args
  linux.args
  macos.args
  launchers/
    diagnostics.properties
```

- `common.args` chứa metadata, input, main entry point và JVM options chung.
- File theo nền tảng chứa loại package, icon, resource và destination riêng.
- File Properties dành cho launcher phụ được tham chiếu qua `--add-launcher`.
- Build script chọn đúng bộ file và working directory.
- CI build application image hoặc native package trên runner phù hợp với nền tảng.
- Review thay đổi của file argument như review source code: kiểm tra path, quoting, option mới và kết quả launcher.

Không nên tạo một file argument khổng lồ chứa mọi cấu hình của mọi nền tảng nếu các path và loại package khác nhau. Chia theo trách nhiệm giúp phát hiện sớm cấu hình xung đột và giảm rủi ro build sai nền tảng.

## 14. Những điểm cần nhớ

- `jpackage @filename` đọc option từ file; Java 16 cho phép dùng nhiều file argument.
- Dùng một option và một giá trị trên mỗi dòng để file dễ đọc.
- Quote path có khoảng trắng; với Windows path trong quoted value, chú ý escape dấu `\`.
- `--arguments` dành cho đối số của ứng dụng; `--java-options` dành cho JVM.
- Giá trị có khoảng trắng trong hai option trên cần nested quoting để giữ đúng một đối số ở lớp launcher.
- `--jlink-options` nhận một chuỗi chứa danh sách option con.
- Đường dẫn tương đối được tính theo working directory của lệnh, không theo vị trí file argument.
- Truyền nhiều `@file` trực tiếp trên command line; không dựa vào include đệ quy.
- `@argfile`, file Properties của `--add-launcher` và file association là các loại cấu hình khác nhau.
- Kiểm tra bằng đúng phiên bản JDK, xem launcher config và chạy thử application image trước khi phát hành installer.

Hãy dùng `@argfile` để biến lệnh đóng gói dài thành cấu hình có cấu trúc, có thể review và tái sử dụng. Giá trị quan trọng nhất là giữ mỗi option, path và chuỗi có khoảng trắng thành đúng token mà jpackage và launcher mong đợi; kiểm tra application image thực tế là bước xác nhận cuối cùng.

## Tài liệu tham khảo

- [The jpackage Command – Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Packaging Tool User's Guide – Java SE 16](https://docs.oracle.com/en/java/javase/16/jpackage/packaging-tool-user-guide.pdf)
- [Support Application Requirements – Java SE 16](https://docs.oracle.com/en/java/javase/16/jpackage/support-application-features.html)
- [The jpackage Command – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
