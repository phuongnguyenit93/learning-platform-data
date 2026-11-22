# Thông tin nền tảng và tính tương thích của gói JMOD

JMOD là định dạng gói mô-đun của JDK, được thiết kế để các công cụ như `jmod` và `jlink` đóng gói, kiểm tra và liên kết mô-đun. Ngoài bytecode và `module-info.class`, một JMOD có thể chứa thư viện native, lệnh native, cấu hình, header, tài liệu pháp lý và man page. Vì vậy, metadata nền tảng và quan hệ hash có vai trò quan trọng khi đưa JMOD vào một runtime image.

Khi đánh giá một gói JMOD, cần phân biệt ba loại thông tin:

- **Nền tảng đích (`--target-platform`)** cho biết mô-đun được đóng gói cho nền tảng nào, ví dụ `windows-amd64`.
- **Phiên bản mô-đun (`--module-version`)** ghi phiên bản của mô-đun trong descriptor.
- **Hash của mô-đun phụ thuộc (`--hash-modules`)** ràng buộc mô-đun được đóng gói với các mô-đun khác phụ thuộc vào nó.

Ba loại metadata này giải quyết các câu hỏi khác nhau. Chúng không thay thế kiểm thử API, tương thích bytecode, chữ ký số hoặc quy trình phát hành.

## 1. JMOD lưu những gì?

JMOD chứa `module-info.class` và các file của mô-đun trong những section riêng. `jmod list` hiển thị đường dẫn entry kèm tên section.

| Section | Nội dung thường gặp | Tùy chọn tạo gói |
| --- | --- | --- |
| `classes/` | Class đã biên dịch, tài nguyên Java và `module-info.class` | `--class-path` |
| `bin/` | Lệnh native đi kèm mô-đun | `--cmds` |
| `conf/` | File cấu hình có thể chỉnh sửa | `--config` |
| `include/` | Header dùng khi tích hợp native/JNI | `--header-files` |
| `legal/` | License và legal notices | `--legal-notices` |
| `lib/` | Thư viện native và thành phần runtime | `--libs` |
| `man/` | Manual pages | `--man-pages` |

Không phải JMOD nào cũng có đủ mọi section. Ví dụ JMOD của một thư viện Java thuần có thể chỉ chứa `classes/`; JMOD của mô-đun JDK có thể có thêm `bin/`, `conf/`, `include/`, `legal/` và `lib/`.

Kiểm tra nội dung gói:

```bash
jmod list path/to/module.jmod
```

Đọc descriptor và metadata:

```bash
jmod describe path/to/module.jmod
```

Giải nén để kiểm tra file thực tế:

```bash
jmod extract --dir extracted path/to/module.jmod
```

Trong thư mục giải nén, `classes/module-info.class` là descriptor đã biên dịch. Dùng `jmod` để liệt kê, mô tả và giải nén; không dựa vào tên file để suy đoán nội dung section.

## 2. `--target-platform` — metadata nền tảng đích

`jmod create` hỗ trợ `--target-platform` để ghi nhãn nền tảng mà mô-đun hướng tới:

```bash
jmod create \
    --class-path build/classes/com.example.nativeapi \
    --target-platform windows-amd64 \
    build/jmods/com.example.nativeapi.jmod
```

Giá trị là chuỗi nền tảng, thường thể hiện hệ điều hành và kiến trúc. Ví dụ JMOD của JDK trên Windows có thể hiển thị:

```text
platform windows-amd64
```

JMOD của một nền tảng Linux có thể mang nhãn như `linux-x64`. Hãy lấy giá trị từ JDK dùng để liên kết image thay vì tự đoán tên:

```powershell
jmod describe "$env:JAVA_HOME\jmods\java.base.jmod" | Select-String '^platform '
```

Trên Bash:

```bash
jmod describe "$JAVA_HOME/jmods/java.base.jmod" | grep '^platform '
```

### Vì sao target platform ảnh hưởng tính tương thích?

JMOD có thể chứa native library, native command và thành phần phụ thuộc ABI của hệ điều hành. Khi `jlink` resolve các mô-đun để tạo image, metadata target platform phải tương thích với các mô-đun nền tảng khác.

Ví dụ JDK hiện tại có `java.base.jmod` mang nhãn `windows-amd64`. Nếu đưa thêm một JMOD có `platform linux-x64`, quá trình resolve có thể dừng với lỗi tương tự:

```text
Error: Module java.base has constraints on target platform (windows-amd64)
that conflict with other modules: linux-x64
```

Đây là lỗi không tương thích nền tảng. Hãy dùng JMOD được xây dựng cho cùng target platform với bộ JDK/JMOD nền tảng đang dùng để tạo image.

### Không có `platform` không có nghĩa là portable

`--target-platform` là metadata có thể không xuất hiện trong một JMOD. Nếu `jmod describe` không in dòng `platform`, điều đó chỉ có nghĩa gói không khai báo nhãn này. Nó không chứng minh rằng native library hoặc lệnh bên trong có thể chạy trên mọi hệ điều hành.

Metadata platform cũng không mô tả đầy đủ mọi giới hạn của môi trường, chẳng hạn phiên bản libc, ABI cụ thể, CPU instruction set hoặc thư viện hệ thống mà native code cần. Những yêu cầu đó vẫn phải được xác định và kiểm thử trong quy trình build/phát hành.

## 3. `--module-version` — phiên bản của mô-đun

JMOD có thể ghi phiên bản mô-đun bằng `--module-version`:

```bash
jmod create \
    --class-path build/classes/com.example.lib \
    --module-version 1.2.0 \
    build/jmods/com.example.lib.jmod
```

Khi mô tả, tên và phiên bản được hiển thị cùng nhau:

```text
com.example.lib@1.2.0
exports com.example.lib
requires java.base mandated
```

Phiên bản này là metadata trong module descriptor. Nó giúp công cụ và người vận hành nhận diện phiên bản mô-đun, nhưng không tự chứng minh rằng hai phiên bản tương thích nhị phân hoặc tương thích API.

Không nhầm `--module-version` với:

- Phiên bản JDK/JVM đang chạy.
- Phiên bản định dạng JMOD.
- Mức bytecode hoặc API Java mà mã nguồn nhắm tới.
- Phiên bản của native ABI hoặc hệ điều hành.

Nếu cần biên dịch cho một mức Java cụ thể, hãy dùng `javac --release` và kiểm thử trên runtime tương ứng. `--module-version` không thay thế tùy chọn biên dịch đó.

## 4. `--hash-modules` — ràng buộc các mô-đun phụ thuộc

Một mô-đun có thể được đóng gói cùng hash của các mô-đun khác phụ thuộc trực tiếp hoặc gián tiếp vào nó. Điều này giúp module resolver phát hiện khi mô-đun phụ thuộc đã bị thay đổi so với nội dung được ghi nhận lúc tạo hash.

`jmod create` hỗ trợ tạo hash ngay khi đóng gói:

```bash
jmod create \
    --class-path build/classes/com.example.lib \
    --module-path build/app-mods \
    --hash-modules 'com\.example\.app' \
    --module-version 1.2.0 \
    --target-platform windows-amd64 \
    build/jmods/com.example.lib.jmod
```

Regex sau `--hash-modules` chọn tên mô-đun phụ thuộc cần được ràng buộc. Trong ví dụ, gói `com.example.lib` lưu hash của `com.example.app` vì app phụ thuộc vào lib.

Nếu đã tạo JMOD, có thể cập nhật hash bằng lệnh `jmod hash`:

```bash
jmod hash \
    --module-path build/app-mods \
    --hash-modules 'com\.example\.app' \
    build/jmods/com.example.lib.jmod
```

Thêm `--dry-run` để xem hash dự kiến mà không ghi thay đổi:

```bash
jmod hash --dry-run \
    --module-path build/app-mods \
    --hash-modules 'com\.example\.app' \
    build/jmods/com.example.lib.jmod
```

Khi chạy `jmod describe`, hash đã lưu được hiển thị theo dạng:

```text
hashes com.example.app SHA-256 <module-hash>
```

SHA-256 ở đây là hash nội dung mô-đun được dùng cho quan hệ ràng buộc giữa các module. Đây không phải chữ ký số của nhà phát hành và cũng không thay thế việc xác minh checksum của file tải xuống từ nguồn phát hành.

### Resolver kiểm tra hash khi nào?

Khi `jlink` resolve module graph, nó kiểm tra hash đã ghi với nội dung mô-đun phụ thuộc đang được cung cấp. Nếu JAR của `com.example.app` bị thay đổi sau khi hash được tạo, liên kết image có thể thất bại với lỗi dạng:

```text
Error: Hash of com.example.app (...) differs to expected hash (...)
recorded in com.example.lib
```

Đây là kiểm tra tính nhất quán của bộ mô-đun. Khi cập nhật app một cách hợp lệ, cần tạo lại hash trong JMOD của mô-đun được app phụ thuộc, rồi kiểm thử lại toàn bộ module graph.

## 5. Ví dụ hoàn chỉnh: JMOD có version, target platform và module hash

Ví dụ dưới đây có hai mô-đun:

- `com.example.lib` cung cấp API `Api.message()` và được đóng gói thành JMOD.
- `com.example.app` phụ thuộc vào library và được đóng gói thành modular JAR.

Library JMOD ghi phiên bản `1.2.0`, target platform `windows-amd64` và hash của mô-đun app.

### Cấu trúc thư mục

```text
src/
├── com.example.lib/
│   ├── module-info.java
│   └── com/example/lib/Api.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

`src/com.example.lib/module-info.java`:

```java
module com.example.lib {
    exports com.example.lib;
}
```

`src/com.example.lib/com/example/lib/Api.java`:

```java
package com.example.lib;

public final class Api {
    private Api() { }

    public static String message() {
        return "JMOD linked";
    }
}
```

`src/com.example.app/module-info.java`:

```java
module com.example.app {
    requires com.example.lib;
}
```

`src/com.example.app/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.lib.Api;

public class Main {
    public static void main(String[] args) {
        System.out.println(Api.message());
    }
}
```

### Bước 1 — biên dịch hai mô-đun

Chạy từ thư mục gốc chứa `src/`:

```bash
mkdir -p build/mods build/app-mods build/lib-jmods
javac --release 17 --module-source-path src -d build/mods \
    -m com.example.lib,com.example.app
```

`--release 17` kiểm soát API Java và bytecode mục tiêu của mã nguồn. Nó độc lập với metadata `--module-version` sẽ ghi vào JMOD.

### Bước 2 — đóng gói app thành modular JAR

```bash
jar --create \
    --file build/app-mods/com.example.app.jar \
    --main-class com.example.app.Main \
    -C build/mods/com.example.app .
```

App JAR là explicit named module vì chứa `module-info.class`. Nó cũng là đầu vào để JMOD ghi hash cho mô-đun phụ thuộc.

### Bước 3 — tạo library JMOD

Trên Windows PowerShell, dùng target platform lấy từ JDK Windows tương ứng:

```powershell
jmod create `
    --class-path build/mods/com.example.lib `
    --module-path build/app-mods `
    --hash-modules 'com\.example\.app' `
    --module-version 1.2.0 `
    --target-platform windows-amd64 `
    build/lib-jmods/com.example.lib.jmod
```

Trên Linux/macOS, lệnh tương tự dùng dấu `\` để xuống dòng và thay `windows-amd64` bằng target platform của JDK đích.

### Bước 4 — kiểm tra metadata và nội dung

```bash
jmod describe build/lib-jmods/com.example.lib.jmod
jmod list build/lib-jmods/com.example.lib.jmod
```

Đầu ra mô tả có cấu trúc tương tự:

```text
com.example.lib@1.2.0
exports com.example.lib
requires java.base mandated
platform windows-amd64
hashes com.example.app SHA-256 <module-hash>
```

`jmod list` cho JMOD thư viện Java thuần hiển thị:

```text
classes/module-info.class
classes/com/example/lib/Api.class
```

### Bước 5 — liên kết runtime image bằng JMOD

Đưa JDK `jmods`, app JAR và library JMOD lên cùng module path. Trên Linux/macOS:

```bash
jlink --module-path "$JAVA_HOME/jmods:build/app-mods:build/lib-jmods" \
    --add-modules com.example.app \
    --output build/runtime
```

Trên Windows PowerShell:

```powershell
$modulePath = "$env:JAVA_HOME\jmods;build/app-mods;build/lib-jmods"
jlink --module-path $modulePath `
    --add-modules com.example.app `
    --output build/runtime
```

`jlink` resolve `com.example.app`, đọc dependency `com.example.lib` từ JMOD, kiểm tra target platform và hash rồi tạo runtime image.

Chạy ứng dụng bằng runtime trong image:

```bash
build/runtime/bin/java --module com.example.app/com.example.app.Main
```

Kết quả standard output:

```text
JMOD linked
```

### Bước 6 — thử hash mismatch

Sau khi tạo JMOD có hash, thay đổi bytecode của `com.example.app` nhưng vẫn giữ JMOD cũ. Khi chạy lại `jlink`, resolver phát hiện hash app không còn khớp với hash lưu trong `com.example.lib` và từ chối liên kết image.

Để cập nhật hợp lệ, tạo lại hash:

```bash
jmod hash --module-path build/app-mods \
    --hash-modules 'com\.example\.app' \
    build/lib-jmods/com.example.lib.jmod
```

Sau đó chạy lại `jmod describe` và `jlink` để xác minh.

## 6. JMOD chỉ dùng ở giai đoạn liên kết

JMOD không phải modular JAR thông thường. Dùng `jmod` để đóng gói và kiểm tra, sau đó dùng `jlink` để liên kết runtime image.

Không đặt JMOD vào runtime module path của lệnh `java` như một JAR. Ví dụ:

```bash
java --module-path build/lib-jmods/com.example.lib.jmod --list-modules
```

Runtime launcher từ chối JMOD với lỗi:

```text
java.lang.module.FindException:
JMOD format not supported at execution time
```

Nếu cần phân phối thư viện để ứng dụng chạy trực tiếp bằng `java --module-path`, hãy dùng modular JAR. JMOD phù hợp khi cần đóng gói thêm native files, cấu hình, headers hoặc metadata dành cho `jlink`.

## 7. Phiên bản JDK và tương thích bytecode

JMOD mang module descriptor và class file được đóng gói. Các yếu tố sau cần được xem riêng:

| Yếu tố | Cách kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Target platform | `jmod describe` và `jlink` | Mô-đun có target platform phù hợp với các JMOD nền tảng hay không |
| Module version | `jmod describe` | Nhận diện phiên bản mô-đun; không tự bảo đảm tương thích API |
| Module hashes | `jmod describe`, `jmod hash`, `jlink` | Kiểm tra mô-đun phụ thuộc có còn khớp nội dung đã ghi nhận hay không |
| Java API/bytecode release | `javac --release`, kiểm thử trên runtime đích | Kiểm soát API Java và mức bytecode mà mã nguồn sử dụng |
| Native ABI/dependency | Kiểm thử trên OS/CPU đích | Xác minh thư viện native chạy được với môi trường triển khai thật |

Nên tạo JMOD bằng `jmod` và JDK `jmods` cùng bộ công cụ dự kiến dùng để chạy `jlink`. Tránh trộn JMOD của nhiều JDK release, vendor hoặc target platform mà chưa kiểm tra. Khi nâng JDK, hãy tạo lại hoặc xác minh lại JMOD, hash và runtime image bằng toolchain đích.

`--target-platform` chỉ là metadata nhận diện nền tảng; nó không kiểm tra mọi dependency native của hệ điều hành. `--module-version` chỉ là version metadata; nó không thay thế semantic versioning, kiểm thử tương thích hoặc `javac --release`.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `JMOD format not supported at execution time` | Đưa JMOD vào runtime module path của `java` | Dùng modular JAR khi chạy trực tiếp hoặc dùng JMOD làm đầu vào `jlink` |
| `Module ... has constraints on target platform ... that conflict` | JMOD có `--target-platform` khác với JDK/JMOD nền tảng | Dùng đúng JMOD cho OS/architecture đích và cùng target JDK |
| `Two versions of module ... found` | Module path chứa nhiều JMOD/JAR cùng tên mô-đun | Loại bản trùng và chỉ giữ một phiên bản cho lần resolve |
| `Hash of ... differs to expected hash` | Mô-đun phụ thuộc đã thay đổi sau khi hash được tạo | Xác minh thay đổi, tạo lại hash bằng `jmod hash` rồi chạy lại `jlink` |
| Không thấy dòng `platform` trong `jmod describe` | JMOD không khai báo target-platform | Kiểm tra nguồn native và yêu cầu triển khai; không mặc định gói là portable |
| Module version không như mong đợi | Gói được tạo mà không truyền `--module-version` hoặc dùng nhầm artifact | Kiểm tra đúng file bằng `jmod describe` và tạo lại gói nếu cần |
| Thiếu native library khi chạy | Library chưa được đưa vào section phù hợp hoặc sai nền tảng | Kiểm tra `jmod list`, `--libs`, target platform và dependency native trên máy đích |

## 9. Quy trình kiểm tra trước khi phát hành

1. Xác định OS, architecture và JDK release đích.
2. Dùng JDK đích để kiểm tra target platform trong `java.base.jmod`.
3. Kiểm tra module descriptor và dependency của các mô-đun đầu vào.
4. Tạo JMOD với `--module-version`; thêm `--target-platform` khi gói cần ràng buộc nền tảng.
5. Dùng `--hash-modules` hoặc `jmod hash` nếu cần ràng buộc các mô-đun phụ thuộc.
6. Chạy `jmod describe` để kiểm tra version, platform, requires và hashes.
7. Chạy `jmod list` để xác minh classes, native libraries, commands, config và legal files đã được đóng gói.
8. Dùng `jlink` với đúng JDK `jmods` và module path để kiểm tra toàn bộ graph.
9. Chạy image trên nền tảng đích và kiểm thử native/API thực tế.
10. Khi thay đổi một mô-đun đã được hash, cập nhật hash và liên kết lại image.

## Ghi nhớ

- JMOD có thể chứa nhiều section hơn class file; `jmod list` cho biết nội dung thực tế.
- `--target-platform` ghi nhãn OS/architecture và giúp `jlink` phát hiện các mô-đun không cùng nền tảng.
- Không có dòng `platform` không chứng minh JMOD chứa native code là portable.
- `--module-version` là metadata phiên bản mô-đun, không phải cam kết tương thích API/bytecode.
- `--hash-modules` lưu hash của mô-đun phụ thuộc; resolver có thể từ chối graph khi nội dung thay đổi.
- Hash JMOD không phải chữ ký số hay checksum tải xuống.
- JMOD dành cho công cụ đóng gói/liên kết; dùng modular JAR cho runtime module path.
- Dùng `jmod` và `jlink` từ toolchain phù hợp với JDK release và target platform của image.

## Tài liệu tham khảo

- [The `jmod` Command — JDK 24 Tool Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmod.html)
- [The `jlink` Command — JDK 24 Tool Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261)