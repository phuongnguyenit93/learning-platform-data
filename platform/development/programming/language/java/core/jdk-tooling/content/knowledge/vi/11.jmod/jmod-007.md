# Native command trong JMOD

Trong Java Development Kit, **native command** là chương trình thực thi ở mức hệ điều hành, chẳng hạn một tiện ích dòng lệnh được viết bằng C/C++, Rust hoặc ngôn ngữ biên dịch native khác. Nó chạy trực tiếp trên hệ điều hành và kiến trúc CPU mục tiêu, không phải một lớp Java được khởi chạy bằng JVM.

Công cụ `jmod` hỗ trợ đóng gói các native command vào JMOD bằng tùy chọn `--cmds`:

```text
jmod create --cmds <path> <module>.jmod
```

Tùy chọn này chỉ đưa các tệp command đã được tạo sẵn vào archive. Nó không biên dịch mã C/C++, không chuyển đổi binary giữa Windows/Linux/macOS và cũng không làm cho một JMOD trở thành chương trình có thể chạy trực tiếp. JMOD là định dạng phục vụ compile-time/link-time; để đưa module và các thành phần native vào một runtime image, quy trình thông thường dùng `jlink`.

## 1. Native command khác gì Java main class và native library?

Ba khái niệm này có liên quan nhưng giữ vai trò khác nhau:

| Thành phần | Ví dụ | Vai trò | Cách đưa vào JMOD |
|---|---|---|---|
| Java class | `com.example.Main.class` | Bytecode được JVM nạp và chạy | `--class-path` |
| Native command | `bin/report-helper`, `report-helper.exe` | Chương trình thực thi trực tiếp trên hệ điều hành | `--cmds` |
| Native library | `libreport.so`, `report.dll`, `libreport.dylib` | Thư viện được chương trình native hoặc Java/JNI nạp | `--libs` |

Một Java module có thể khai báo `main` class trong module descriptor bằng `--main-class`. Đây là metadata cho điểm vào Java của module. Nó không thay thế `--cmds`.

Tương tự, thư viện native dùng với JNI hoặc được một native executable liên kết không phải command. Nếu một command cần thư viện dùng chung, hãy đóng gói thư viện vào phần native libraries bằng `--libs` khi thích hợp, đồng thời bảo đảm các phụ thuộc hệ thống của thư viện có mặt trên máy đích.

Ví dụ:

- `jmod --cmds native-commands`: thêm executable như `report-helper`.
- `jmod --libs native-libs`: thêm thư viện native như `libreport.so`.
- `jmod --class-path mods/com.example.tools`: thêm module descriptor và Java class file.

## 2. Vị trí native command trong JMOD

JMOD chia nội dung thành các section theo loại dữ liệu. Native command được lưu trong section `bin/`. Một JMOD có thể chứa các section như:

| Section trong JMOD | Nội dung |
|---|---|
| `classes/` | Module descriptor và Java class file |
| `bin/` | Native command |
| `lib/` | Native library |
| `conf/` | Tệp cấu hình |
| `include/` | Header file |
| `legal/` | Legal notice |
| `man/` | Man page |

Ví dụ cấu trúc sau khi đóng gói:

```text
com.example.tools.jmod
├── classes/
│   ├── module-info.class
│   └── com/example/tools/Main.class
└── bin/
    └── report-helper
```

Đường dẫn `bin/report-helper` là entry bên trong JMOD. Khi dùng `jmod list`, tên section xuất hiện trong danh sách entry. Khi giải nén bằng `jmod extract`, nội dung được tái tạo dưới thư mục đích theo các section tương ứng.

JMOD có thể lưu thêm native library, configuration, header và tài liệu. Các phần này giúp module mang theo những thành phần cần thiết cho quá trình liên kết runtime image hoặc triển khai theo quy trình của sản phẩm.

## 3. Chuẩn bị native command trước khi đóng gói

`jmod` không phải compiler native. Trước khi gọi `--cmds`, command phải được build bằng toolchain phù hợp với nền tảng đích.

Ví dụ, một dự án có thể chuẩn bị:

```text
native-commands/
└── report-helper
```

Trong ví dụ Linux này, `report-helper` là binary đã được build cho Linux và kiến trúc CPU mục tiêu. Với Windows, file thực thi thường có phần mở rộng `.exe`; macOS và Linux có quy tắc đóng gói và liên kết native riêng.

Kiểm tra trước khi đóng gói:

1. Command đã được biên dịch thành công bằng toolchain dành cho hệ điều hành mục tiêu.
2. Kiến trúc CPU khớp với runtime image sẽ được tạo.
3. Các thư viện native mà command phụ thuộc đã được xác định.
4. Command có quyền thực thi phù hợp trên nền tảng đích.
5. Các tên command không xung đột với công cụ hoặc command khác được đưa vào runtime image.
6. Có thể chạy thử command độc lập trên môi trường tương thích trước khi đóng gói.

Trên Linux, có thể kiểm tra định dạng binary bằng công cụ hệ thống như `file`:

```sh
file native-commands/report-helper
```

Có thể xem các thư viện động mà executable yêu cầu bằng công cụ phù hợp của hệ điều hành, ví dụ `ldd` trên một số hệ Linux. Chỉ chạy công cụ kiểm tra này với binary đáng tin cậy và trong môi trường phù hợp.

Một binary Linux x86-64 không thể tự động chạy trên Windows hoặc macOS chỉ vì nó đã nằm trong JMOD. JMOD giữ binary đã build; nó không chuyển đổi định dạng executable hoặc instruction set.

## 4. Tạo JMOD có native command

Giả sử module Java đã được biên dịch vào:

```text
mods/
└── com.example.tools/
    ├── module-info.class
    └── com/
        └── example/
            └── tools/
                └── Main.class
```

Thư mục chứa native command:

```text
native-commands/
└── report-helper
```

Tạo thư mục chứa JMOD:

```sh
mkdir -p jmods
```

Tạo JMOD cho Linux AMD64:

```sh
jmod create \
  --class-path mods/com.example.tools \
  --cmds native-commands \
  --target-platform linux-amd64 \
  jmods/com.example.tools.jmod
```

Giải thích:

- `create`: tạo archive JMOD mới.
- `--class-path mods/com.example.tools`: lấy module descriptor và các class file đã biên dịch.
- `--cmds native-commands`: sao chép nội dung thư mục native command vào section command của JMOD.
- `--target-platform linux-amd64`: khai báo nền tảng mà JMOD được tạo cho.
- `jmods/com.example.tools.jmod`: đường dẫn archive đầu ra.

`--cmds` sao chép nội dung của đường dẫn được chỉ định, bao gồm các thư mục con và nội dung bên trong. Nếu chỉ định một thư mục có nhiều command, tất cả nội dung phù hợp sẽ được thêm vào archive. Có thể dùng `--exclude` khi cần loại trừ các file theo pattern được hỗ trợ.

Trên Windows, ví dụ với binary được build riêng cho Windows AMD64:

```powershell
New-Item -ItemType Directory -Force jmods
jmod create --class-path mods\com.example.tools --cmds native-commands --target-platform windows-amd64 jmods\com.example.tools.jmod
```

Không dùng JMOD Linux AMD64 cho runtime image Windows AMD64 hoặc macOS ARM64. Nếu phát hành nhiều nền tảng, hãy build native command và tạo JMOD tương ứng cho từng nền tảng.

## 5. Kiểm tra command đã được đưa vào JMOD

Sau khi tạo archive, dùng `jmod list`:

```sh
jmod list jmods/com.example.tools.jmod
```

Kết quả minh họa:

```text
classes/module-info.class
classes/com/example/tools/Main.class
bin/report-helper
```

Tên entry thực tế phụ thuộc nội dung module và thư mục command đã cung cấp. Điều cần xác nhận là command nằm dưới section `bin/`.

Có thể giải nén để kiểm tra:

```sh
jmod extract \
  --dir extracted \
  jmods/com.example.tools.jmod
```

Sau khi giải nén, cấu trúc có dạng:

```text
extracted/
├── classes/
│   ├── module-info.class
│   └── com/example/tools/Main.class
└── bin/
    └── report-helper
```

Trên Windows, dùng đường dẫn tương ứng:

```powershell
jmod extract --dir extracted jmods\com.example.tools.jmod
```

`jmod describe` hiển thị thông tin module descriptor như tên module và các quan hệ `requires`; nó không thay thế việc dùng `jmod list` để kiểm tra từng entry command.

## 6. Dùng JMOD với jlink

JMOD không phải archive có thể chạy trực tiếp bằng `java -jar`. Nó được dùng ở compile-time hoặc link-time. Công cụ `jlink` đọc các module trên module path và tạo một custom runtime image gồm module được chọn cùng các dependency bắc cầu của chúng.

Ví dụ trên Linux/macOS:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:jmods" \
  --add-modules com.example.tools \
  --output runtime-image
```

Trên Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;jmods" --add-modules com.example.tools --output runtime-image
```

Ở đây:

- `$JAVA_HOME/jmods` chứa các JMOD của JDK hiện tại.
- `jmods` là thư mục chứa `com.example.tools.jmod`.
- `--add-modules` chọn module gốc cần đưa vào image.
- `--output` xác định thư mục runtime image.

Nếu module được chọn và JMOD chứa native command, command section được xử lý trong quá trình link. Native command xuất hiện trong phần command của runtime image, thường dưới `runtime-image/bin/`.

Ví dụ trên Linux:

```sh
runtime-image/bin/report-helper --help
```

Kiểm tra Java runtime trong image:

```sh
runtime-image/bin/java --list-modules
```

Tên và cách gọi command phụ thuộc hệ điều hành và binary đã đóng gói. Trên Windows, command thường được gọi bằng tên file thực thi tương ứng, ví dụ `runtime-image\bin\report-helper.exe`.

Nếu chỉ muốn kiểm tra module có được link vào image hay không, dùng lệnh `java --list-modules` của runtime image. Lệnh này liệt kê module, không liệt kê đầy đủ các native command trong thư mục `bin`; hãy kiểm tra file system của image để xác nhận command cụ thể.

## 7. Phân biệt native command với launcher do jlink tạo

Có hai cách khác nhau để cung cấp command trong runtime image:

**Native command được đóng gói bằng `jmod --cmds`:** đây là executable native đã được build trước. JMOD chứa binary đó và jlink có thể đưa nó vào runtime image khi link module.

**Launcher được tạo bằng `jlink --launcher`:** đây là launcher cho một Java module và main class. Ví dụ:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:jmods" \
  --add-modules com.example.tools \
  --launcher tools=com.example.tools/com.example.tools.Main \
  --output runtime-image
```

Launcher `tools` khởi chạy Java module/main class đã khai báo. Nó không phải native command do dự án cung cấp thông qua `--cmds`, dù launcher được tạo ra có thể là executable/script phù hợp với nền tảng.

| Nhu cầu | Cách cấu hình |
|---|---|
| Đưa executable native đã build vào module | `jmod create --cmds` |
| Đưa native shared library vào module | `jmod create --libs` |
| Chọn Java main class của module | `jmod create --main-class` |
| Tạo command launcher cho Java module trong runtime image | `jlink --launcher` |

Phân biệt các cách này giúp tránh nhầm lẫn giữa một chương trình native độc lập và một launcher chỉ có nhiệm vụ gọi JVM để chạy Java code.

## 8. Native command và native library dependencies

Một native command có thể phụ thuộc vào shared library. Ví dụ trên Linux:

```text
native-commands/
└── report-helper

native-libs/
└── libreport.so
```

Đóng gói cả command và thư viện thuộc module:

```sh
jmod create \
  --class-path mods/com.example.tools \
  --cmds native-commands \
  --libs native-libs \
  --target-platform linux-amd64 \
  jmods/com.example.tools.jmod
```

Các thư viện được đặt trong section native libraries của JMOD. Khi tạo runtime image, các thành phần native được xử lý theo quy tắc của JMOD/jlink và nền tảng. Tuy nhiên, việc thêm một thư viện vào JMOD không bảo đảm mọi phụ thuộc hệ thống của nó cũng được đóng gói.

Ví dụ, một thư viện native có thể phụ thuộc vào C runtime hoặc shared library của hệ điều hành. Những dependency này phải tồn tại và tương thích trên hệ thống đích. Hãy kiểm tra dependency của binary bằng công cụ phù hợp trên chính nền tảng build/target.

Trên Linux, `ldd` có thể giúp xem shared library mà executable liên kết động cần. Trên macOS có thể dùng `otool -L`; trên Windows có thể dùng công cụ phân tích PE/dependency tương ứng. Kết quả kiểm tra trên một nền tảng không thay thế kiểm thử trên nền tảng khác.

## 9. Target platform và phân phối đa nền tảng

Native command gắn với hệ điều hành và kiến trúc CPU. Tùy chọn `--target-platform` khai báo nền tảng mục tiêu của JMOD. Một số giá trị ví dụ:

| Target platform | Hệ điều hành | Kiến trúc |
|---|---|---|
| `linux-amd64` | Linux | AMD64/x86-64 |
| `windows-amd64` | Windows | AMD64/x86-64 |
| `macos-aarch64` | macOS | ARM64/Apple Silicon |

Giá trị target platform là metadata mô tả đích. Nó không biên dịch lại command, không đổi định dạng PE/ELF/Mach-O và không chuyển instruction set.

Nếu sản phẩm hỗ trợ nhiều nền tảng, quy trình thường là:

1. Build native command trên toolchain phù hợp cho từng target.
2. Kiểm thử executable trên target tương ứng.
3. Tạo JMOD với native command và target-platform tương ứng.
4. Link runtime image phù hợp bằng JDK/toolchain của target.
5. Kiểm thử command trong runtime image hoàn chỉnh.
6. Phân phối artifact đúng nền tảng.

Không gộp binary Windows, Linux và macOS vào một JMOD rồi kỳ vọng JVM tự chọn đúng executable. Hãy quản lý các artifact riêng biệt và đặt tên rõ ràng theo nền tảng/kiến trúc.

## 10. Quyền thực thi và bảo mật

Native command chạy với quyền của người dùng khởi chạy nó. Việc đặt một executable trong JMOD hoặc runtime image không tạo sandbox và không hạn chế quyền hệ điều hành của command.

Các lưu ý khi đóng gói:

- Chỉ đưa vào JMOD các binary đã được kiểm tra nguồn gốc và tính toàn vẹn.
- Không đóng gói executable lấy từ nguồn không đáng tin cậy.
- Không dùng tên command dễ xung đột với command hệ thống hoặc command khác trong image.
- Kiểm tra quyền thực thi và quyền truy cập file theo nền tảng.
- Không giả định binary có thể chạy chỉ vì nó xuất hiện trong kết quả `jmod list`.
- Xác minh các thư viện native và system dependency khi chạy trên máy đích.
- Cập nhật và phát hành lại runtime image khi native command có lỗ hổng hoặc cần bản vá.

Một JMOD có thể được link vào runtime image nhưng không có nghĩa mọi command trong đó tự động an toàn. Chính sách cập nhật, ký artifact, kiểm tra checksum và kiểm thử bảo mật vẫn thuộc quy trình phát hành của sản phẩm.

## 11. jlink và tùy chọn loại bỏ native commands

`jlink` có plugin `strip-native-commands` để loại native commands khỏi runtime image. Tùy chọn này hữu ích khi muốn giảm thành phần command trong image, nhưng nếu ứng dụng cần command đã đóng gói qua `--cmds`, hãy kiểm tra cấu hình plugin để tránh loại bỏ chúng.

Liệt kê plugin được JDK hiện tại hỗ trợ:

```sh
jlink --list-plugins
```

Nếu image được tạo với tùy chọn loại bỏ native commands, các executable có thể không còn trong image dù chúng từng có trong JMOD. Vì vậy, sau khi link, luôn kiểm tra trực tiếp thư mục `bin` của runtime image và chạy thử command cần thiết.

Không nhầm `--strip-native-commands` với `--no-header-files` hoặc `--no-man-pages`; chúng loại các loại thành phần khác nhau.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jmod` báo không tìm thấy đường dẫn `--cmds` | Đường dẫn sai hoặc thư mục chưa được tạo | Kiểm tra thư mục native command và chạy lệnh từ đúng working directory |
| `jmod list` không có `bin/` | Tạo JMOD mà không truyền `--cmds`, hoặc thư mục đầu vào rỗng/không đúng | Kiểm tra command input và tạo lại JMOD từ đúng thư mục |
| JMOD có `bin/...` nhưng command không chạy | Binary không tương thích hệ điều hành/CPU, thiếu quyền hoặc thiếu shared library | Kiểm tra định dạng binary, quyền thực thi và dependency trên target |
| `jlink` không tìm thấy module | JMOD không nằm trong module path, tên module sai hoặc module descriptor không hợp lệ | Kiểm tra `--module-path`, `jmod describe` và `module-info.class` |
| `jlink` từ chối target platform | JMOD không phù hợp với nền tảng runtime image | Tạo JMOD cho đúng hệ điều hành/kiến trúc và dùng JDK phù hợp |
| Native command không có trong runtime image | Module không được link, JMOD không có command entry hoặc plugin đã loại native command | Kiểm tra `--add-modules`, `jmod list`, `jlink --list-plugins` và thư mục image `bin` |
| Command báo thiếu DLL/shared library | Chưa đóng gói native library hoặc thiếu dependency hệ thống | Kiểm tra dependency và thêm library phù hợp bằng `--libs` khi cần |
| Command chạy trên máy build nhưng lỗi trên máy đích | Môi trường build có thư viện hoặc runtime dependency không có trên target | Kiểm thử trên image sạch tương ứng với nền tảng triển khai |
| Tên command bị trùng hoặc bị gọi nhầm | Có nhiều command cùng tên hoặc xung đột với công cụ trong image | Đặt tên riêng và kiểm tra nội dung cuối của thư mục `bin` |
| Command không chạy sau khi link image | Runtime image được tạo với tùy chọn strip native commands hoặc artifact đã bị loại bỏ | Kiểm tra plugin và tạo lại image với cấu hình phù hợp |

Khi chẩn đoán, đi theo chuỗi: kiểm tra thư mục đầu vào → kiểm tra JMOD bằng `jmod list` → kiểm tra module bằng `jmod describe` → kiểm tra runtime image sau `jlink` → chạy command trên đúng nền tảng. Cách này giúp xác định lỗi thuộc khâu build native, đóng gói, module resolution hay runtime.

## 13. Checklist

- [ ] Native command đã được build trước bằng toolchain phù hợp.
- [ ] Binary đúng hệ điều hành và kiến trúc CPU mục tiêu.
- [ ] Đã phân biệt command với Java class và native shared library.
- [ ] Đã dùng `--cmds` để thêm command vào JMOD.
- [ ] Đã dùng `--libs` cho shared library cần đóng gói.
- [ ] Đã đặt `--target-platform` đúng khi tạo JMOD cho target cụ thể.
- [ ] Đã kiểm tra section `bin/` bằng `jmod list`.
- [ ] Đã kiểm tra nội dung giải nén nếu cần bằng `jmod extract`.
- [ ] Đã link module bằng `jlink` với module path và root module đúng.
- [ ] Đã xác nhận command xuất hiện trong runtime image.
- [ ] Không vô tình bật plugin loại bỏ native commands.
- [ ] Đã kiểm thử command cùng dependency trên môi trường đích.

## 14. Tài liệu tham khảo

- Oracle JDK Tool Reference — The `jmod` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jmod.html
- Oracle JDK Tool Reference — The `jlink` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html

Native command trong JMOD là cách đóng gói executable phụ thuộc nền tảng cùng một Java module để phục vụ quá trình liên kết runtime image. Hiểu đúng `--cmds`, section `bin/`, `--target-platform`, `--libs` và vai trò của `jlink` giúp xây dựng artifact native nhất quán, có thể kiểm tra và triển khai đúng hệ điều hành/kiến trúc.