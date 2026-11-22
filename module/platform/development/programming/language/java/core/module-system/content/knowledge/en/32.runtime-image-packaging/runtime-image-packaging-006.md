# jmod create và module native command

JMOD là định dạng archive của JDK dùng để đóng gói nội dung module phục vụ quá trình liên kết runtime image. Ngoài class Java và module descriptor, một JMOD có thể chứa native command, native library, cấu hình, header, legal notice và man page.

Lệnh `jmod create` tạo file `.jmod` từ các đầu vào đã chuẩn bị. Khi dùng `jlink` để tạo runtime image, nội dung phù hợp trong JMOD được đưa vào image. Chủ đề này đặc biệt quan trọng khi module Java cần phân phối kèm một chương trình native có thể gọi từ shell hoặc từ `ProcessBuilder`.

Cần phân biệt hai loại native artifact:

- **Native command** là executable độc lập, ví dụ `acme-check` hoặc `acme-check.exe`. Đóng gói nó bằng `jmod create --cmds`; khi link module, command được đặt trong thư mục `bin` của runtime image.
- **Native library** là thư viện dùng từ code Java qua JNI hoặc cơ chế native tương ứng, ví dụ `libacme.so`, `acme.dll` hoặc `libacme.dylib`. Đóng gói bằng `--libs`, không phải `--cmds`.

## 1. Cấu trúc của một JMOD

JMOD có thể chứa những section sau:

| Section | Nội dung | Tùy chọn jmod create |
|---|---|---|
| `classes/` | Class Java, resource và `module-info.class` | `--class-path` |
| `bin/` | Native command executable | `--cmds` |
| `conf/` | File cấu hình của module | `--config` |
| `include/` | Native header files | `--header-files` |
| `legal/` | License và legal notices | `--legal-notices` |
| `lib/` | Native libraries | `--libs` |
| `man/` | Man pages | `--man-pages` |

Không phải module nào cũng cần tất cả section. Một module thuần Java có thể chỉ cần `classes/`; module cung cấp native command sẽ có thêm `bin/`.

Module descriptor vẫn là phần quan trọng của JMOD. Đối với module được dùng làm đầu vào cho `jlink`, thư mục class đầu vào phải có `module-info.class` hợp lệ để công cụ xác định tên module và dependency.

## 2. Cú pháp jmod create

Cú pháp tổng quát:

~~~bash
jmod create [OPTIONS] <jmod-file>
~~~

Các tùy chọn thường dùng:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--class-path <path>` | Thư mục chứa class và resource của module |
| `--cmds <path>` | Thư mục chứa native command executable |
| `--libs <path>` | Thư mục chứa native library |
| `--config <path>` | Thư mục chứa file cấu hình |
| `--header-files <path>` | Thư mục chứa header dùng cho native integration |
| `--legal-notices <path>` | Thư mục chứa license/legal notice |
| `--man-pages <path>` | Thư mục chứa man page |
| `--main-class <class>` | Main class của module, nếu module có entry point Java |
| `--module-version <version>` | Version được ghi vào metadata module |
| `--target-platform <target-platform>` | Nền tảng đích mà JMOD được tạo cho |

Ví dụ tạo JMOD chỉ có class Java:

~~~bash
jmod create \
  --class-path build/classes/com.acme.tools \
  --module-version 1.0.0 \
  build/jmods/com.acme.tools.jmod
~~~

Ví dụ có thêm native command:

~~~bash
jmod create \
  --class-path build/classes/com.acme.tools \
  --cmds native/bin \
  --module-version 1.0.0 \
  build/jmods/com.acme.tools.jmod
~~~

Tên file JMOD thường phản ánh module name, nhưng module name chính thức nằm trong `module-info.class`. Đổi tên file không làm thay đổi tên module bên trong descriptor.

## 3. Chuẩn bị một module Java để đóng gói

Ví dụ module có tên `com.acme.tools`:

~~~text
project/
├── src/
│   └── com.acme.tools/
│       ├── module-info.java
│       └── com/acme/tools/ToolInfo.java
├── native/
│   ├── acme-check.c
│   └── bin/
└── build/
    ├── classes/
    └── jmods/
~~~

Descriptor:

~~~java
module com.acme.tools {
    exports com.acme.tools;
}
~~~

Class Java:

~~~java
package com.acme.tools;

public class ToolInfo {
    public static String version() {
        return "1.0.0";
    }
}
~~~

Compile module:

~~~bash
javac \
  -d build/classes/com.acme.tools \
  src/com.acme.tools/module-info.java \
  src/com.acme.tools/com/acme/tools/ToolInfo.java
~~~

Sau khi compile, thư mục `build/classes/com.acme.tools` cần có cấu trúc:

~~~text
build/classes/com.acme.tools/
├── module-info.class
└── com/
    └── acme/
        └── tools/
            └── ToolInfo.class
~~~

Đây là đầu vào cho `--class-path`. Không đưa source `.java` vào JMOD thay cho class đã compile.

## 4. Chuẩn bị native command

Một native command là chương trình thực thi riêng của hệ điều hành. Ví dụ C đơn giản:

~~~c
#include <stdio.h>

int main(void) {
    puts("acme-check from the linked runtime image");
    return 0;
}
~~~

Lưu file thành `native/acme-check.c`.

Trên Linux hoặc macOS, dùng compiler C phù hợp với nền tảng:

~~~bash
mkdir -p native/bin
cc -O2 -o native/bin/acme-check native/acme-check.c
~~~

Kiểm tra file thực thi:

~~~bash
file native/bin/acme-check
./native/bin/acme-check
~~~

Trên Windows với Microsoft C/C++ Build Tools, có thể tạo executable tương ứng:

~~~powershell
New-Item -ItemType Directory -Force native/bin
cl /O2 /Fe:native/bin/acme-check.exe native/acme-check.c
native/bin/acme-check.exe
~~~

Thư mục truyền cho `--cmds` chứa **binary đã biên dịch**, không phải file source C. Tên file command sẽ được giữ trong runtime image; trên Windows thường có phần mở rộng `.exe`.

Native command phải phù hợp với hệ điều hành và kiến trúc CPU của runtime image đích. Một binary Linux không thể chạy trong runtime image Windows chỉ vì nó được đóng gói trong JMOD.

## 5. Đóng gói module và native command bằng jmod create

Tạo thư mục chứa JMOD:

~~~bash
mkdir -p build/jmods
~~~

Tạo JMOD:

~~~bash
jmod create \
  --class-path build/classes/com.acme.tools \
  --cmds native/bin \
  --module-version 1.0.0 \
  build/jmods/com.acme.tools.jmod
~~~

Trong lệnh trên:

- `--class-path` lấy `module-info.class`, class Java và resource của module.
- `--cmds` lấy các native executable trong `native/bin`.
- `--module-version` ghi version vào module metadata.
- Đối số cuối cùng là đường dẫn file JMOD cần tạo.

Nếu module còn có native library, config, header, license hoặc man page, có thể bổ sung các tùy chọn tương ứng:

~~~bash
jmod create \
  --class-path build/classes/com.acme.tools \
  --cmds native/bin \
  --libs native/lib \
  --config config \
  --header-files native/include \
  --legal-notices legal \
  --man-pages man \
  --module-version 1.0.0 \
  build/jmods/com.acme.tools.jmod
~~~

Chỉ truyền các thư mục thực sự cần thiết. Các thư mục đầu vào phải chứa đúng loại artifact mà tùy chọn mô tả.

Nếu đóng gói binary cho một nền tảng cụ thể, có thể gắn metadata nền tảng bằng `--target-platform`. Giá trị phải theo định danh target platform mà bộ JDK/toolchain đang dùng hỗ trợ. Giữ nhất quán JDK, kiến trúc và hệ điều hành khi tạo JMOD và runtime image.

## 6. Phân biệt --cmds, --libs và --header-files

Ba tùy chọn này dễ nhầm vì đều liên quan native code, nhưng mục đích khác nhau.

### --cmds: executable được gọi như command

Ví dụ:

~~~text
native/bin/
└── acme-check
~~~

Sau khi link module, command được đưa vào:

~~~text
runtime/
└── bin/
    ├── java
    ├── jlink
    └── acme-check
~~~

Có thể chạy trực tiếp từ shell:

~~~bash
runtime/bin/acme-check
~~~

Trên Windows:

~~~powershell
runtime/bin/acme-check.exe
~~~

Command này có thể là một tiện ích độc lập, không nhất thiết phải được Java class gọi. Nó cũng không trở thành main class của module chỉ vì được đóng gói trong JMOD.

### --libs: thư viện native được Java nạp

Ví dụ:

~~~text
native/lib/
├── libacme_native.so
├── libacme_native.dylib
└── acme_native.dll
~~~

Tên và định dạng thực tế phụ thuộc hệ điều hành. Một Java class có thể gọi native library qua JNI, ví dụ:

~~~java
public final class NativeBridge {
    static {
        System.loadLibrary("acme_native");
    }

    public static native int calculate(int value);
}
~~~

Thư viện được đóng gói bằng:

~~~bash
jmod create \
  --class-path build/classes/com.acme.tools \
  --libs native/lib \
  build/jmods/com.acme.tools.jmod
~~~

`System.loadLibrary` nạp thư viện native theo cơ chế tìm kiếm library path của JVM. Việc đóng gói thư viện vào JMOD giúp nó được đưa vào runtime image khi module được link; vẫn cần kiểm tra tên thư viện, kiến trúc, ABI và cách JVM tìm thấy thư viện trong image.

### --header-files: header dùng khi tích hợp native

Header C/C++ có thể được tạo bởi `javac -h` khi Java class khai báo native method:

~~~bash
javac -h native/include \
  -d build/classes/com.acme.tools \
  src/com.acme.tools/com/acme/tools/NativeBridge.java
~~~

Thư mục `native/include` có thể được đóng gói bằng `--header-files` để phân phối header cùng module. Header không phải executable và cũng không phải native library; nó hỗ trợ compile native code tương thích với Java API/JNI.

## 7. Link JMOD thành runtime image bằng jlink

JMOD là đầu vào cho công cụ liên kết. Java launcher không nạp file `.jmod` trực tiếp như một module runtime. Dùng `jlink` để tạo runtime image có module cần thiết.

Trên Linux/macOS:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:build/jmods" \
  --add-modules com.acme.tools \
  --output runtime
~~~

Trên Windows PowerShell:

~~~powershell
$jmods = Join-Path $env:JAVA_HOME "jmods"
jlink --module-path "$jmods;build/jmods" --add-modules com.acme.tools --output runtime
~~~

`--module-path` chứa cả JMOD của JDK và JMOD ứng dụng. `--add-modules` chọn module cần đưa vào image; dependency được giải quyết theo descriptor. `--output` xác định thư mục runtime image.

Sau khi link thành công, chạy native command trong image:

~~~bash
runtime/bin/acme-check
~~~

Trên Windows:

~~~powershell
runtime/bin/acme-check.exe
~~~

Kiểm tra module có trong image:

~~~bash
runtime/bin/java --list-modules
runtime/bin/java --describe-module com.acme.tools
~~~

Nếu JMOD chứa native library, hãy kiểm tra thư viện cũng đã được link vào image và thử nạp từ một chương trình Java trong runtime đó.

## 8. Kiểm tra nội dung JMOD

Dùng `jmod list` để xem các entry:

~~~bash
jmod list build/jmods/com.acme.tools.jmod
~~~

Có thể thấy các entry tương tự:

~~~text
classes/module-info.class
classes/com/acme/tools/ToolInfo.class
bin/acme-check
~~~

Dùng `jmod describe` để xem metadata module:

~~~bash
jmod describe build/jmods/com.acme.tools.jmod
~~~

Đầu ra có thể hiển thị tên module, version, exports, requires và target platform nếu metadata có khai báo. `jmod describe` tập trung vào descriptor; dùng `jmod list` để kiểm tra file được đóng gói.

Muốn giải nén archive để kiểm tra từng section:

~~~bash
jmod extract --dir extracted build/jmods/com.acme.tools.jmod
~~~

Sau đó kiểm tra:

~~~text
extracted/
├── classes/
├── bin/
├── lib/
├── conf/
├── include/
├── legal/
└── man/
~~~

Chỉ những section có nội dung mới xuất hiện. Việc extract hữu ích để xác nhận binary command đã được đưa vào đúng section trước khi tạo runtime image.

## 9. Native command khác với jlink --launcher

Không nhầm native command đóng gói trong JMOD với launcher được tạo bởi `jlink --launcher`.

- `jmod create --cmds` đóng gói **một executable native có sẵn** vào JMOD. Đây có thể là công cụ C/C++ độc lập.
- `jlink --launcher` tạo launcher để khởi chạy một module Java và main class của nó.

Ví dụ tạo launcher Java:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:build/jmods" \
  --add-modules com.acme.tools \
  --launcher acme-java=com.acme.tools/com.acme.tools.ToolMain \
  --output runtime
~~~

Lệnh trên tạo launcher `runtime/bin/acme-java` để chạy main class Java. Nó không thay thế native command đã được đóng gói qua `--cmds`; hai loại command có thể cùng tồn tại nếu tên không xung đột.

Nếu module chỉ cung cấp một native command mà không có main class Java, không cần khai báo `--launcher` cho module đó.

## 10. Các lỗi thường gặp

**jmod create báo không tìm thấy module descriptor.** Kiểm tra `--class-path` có trỏ tới thư mục gốc chứa `module-info.class` hay không. Đừng trỏ nhầm vào package con hoặc thư mục source.

**JMOD được tạo nhưng không tìm thấy native command sau jlink.** Kiểm tra command có thực sự nằm trong thư mục truyền cho `--cmds`, `jmod list` có entry `bin/...`, và module chứa JMOD đã được chọn trong `--add-modules`.

**Command có trong runtime nhưng không chạy được.** Kiểm tra executable bit trên Unix, định dạng binary, kiến trúc CPU, dynamic dependencies và thư viện hệ điều hành cần thiết. Trên Windows, kiểm tra đúng file `.exe` và runtime dependency của compiler.

**Dùng --libs nhưng mong command xuất hiện trong bin.** `--libs` đóng gói native library; command executable phải được đưa vào bằng `--cmds`.

**Dùng --cmds để đóng gói JNI library.** JNI library không phải command độc lập. Đưa nó vào `--libs`, sau đó kiểm tra `System.loadLibrary` và cấu hình nạp native library.

**JMOD chạy được trên máy tạo nhưng không chạy trên máy đích.** Native content phụ thuộc OS, CPU architecture và ABI. Tạo JMOD/runtime image cho đúng target platform; không sao chép binary Linux vào image Windows hoặc ngược lại.

**Java launcher báo không tìm thấy module khi trỏ trực tiếp tới JMOD.** JMOD dùng cho link time. Hãy dùng `jlink` để tạo runtime image, sau đó chạy ứng dụng từ image đó.

**Trùng tên command trong nhiều module.** Nhiều native command cùng được link vào một runtime image có thể xung đột tên file trong `bin`. Đặt tên command có namespace rõ ràng, ví dụ `acme-db-check`, và tránh để hai module sở hữu cùng tên executable.

## 11. Quy trình đóng gói khuyến nghị

1. Compile module Java để tạo `module-info.class` và class/resource.
2. Build native command riêng cho đúng OS và kiến trúc đích.
3. Phân loại native artifact: executable vào `--cmds`, JNI/shared library vào `--libs`, header vào `--header-files`.
4. Tạo JMOD bằng `jmod create` và chỉ truyền các section cần thiết.
5. Dùng `jmod list` để xác nhận các entry, đặc biệt là `bin/<command>` và `lib/<library>`.
6. Dùng `jmod describe` để xác nhận module name, version và descriptor.
7. Dùng `jlink` để tạo runtime image từ JMOD cùng JMOD của JDK.
8. Chạy native command từ `runtime/bin` và kiểm tra ứng dụng Java trên cùng runtime image.
9. Thực hiện kiểm thử trên đúng hệ điều hành và kiến trúc sẽ triển khai.

## 12. Thực hành

1. Tạo module `com.acme.tools` với `module-info.java` và class `ToolInfo`.
2. Compile module vào `build/classes/com.acme.tools`.
3. Viết chương trình C `acme-check.c`, compile thành executable trong `native/bin`.
4. Dùng `jmod create --class-path ... --cmds ...` tạo `com.acme.tools.jmod`.
5. Dùng `jmod list` xác nhận có `classes/module-info.class` và `bin/acme-check`.
6. Dùng `jlink` tạo runtime image chỉ chứa module cần thiết.
7. Chạy `runtime/bin/acme-check` và `runtime/bin/java --describe-module com.acme.tools`.
8. Nếu có JNI library, tạo thêm một native library, đóng gói bằng `--libs`, viết Java bridge và kiểm tra `System.loadLibrary` trong runtime image.
9. Thử tạo JMOD cho một target platform khác bằng toolchain tương ứng; ghi nhận vì sao binary native không thể dùng tùy ý giữa các hệ điều hành.

Khi đóng gói native content cho module, hãy phân biệt executable, shared library và header. `--cmds` đưa native command vào `bin` của runtime image; `--libs` đưa thư viện native vào image để Java có thể nạp; `--header-files` phân phối header cho quá trình tích hợp native. JMOD gom các thành phần đó với descriptor và class Java, còn `jlink` tạo runtime image cuối cùng có thể triển khai.
