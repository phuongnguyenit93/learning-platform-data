# Chọn module cần thiết khi tạo runtime image bằng `jlink`

`jlink` tạo runtime image từ một tập module đã chọn và các dependency cần thiết của chúng. Chọn module đúng giúp image có đủ API để ứng dụng hoạt động, đồng thời tránh đưa toàn bộ module của JDK vào bản triển khai.

Khi chọn module, cần phân biệt **module gốc** với **module phụ thuộc**. Module gốc là những module được yêu cầu trực tiếp trong `--add-modules`; linker tự phân giải quan hệ `requires` và bổ sung dependency bắt buộc. Những module được nạp động qua reflection, tên lớp dạng chuỗi, service provider hoặc JNI có thể cần được xem xét riêng vì phân tích tĩnh không phải lúc nào cũng phát hiện được chúng.

Quy trình đáng tin cậy thường là: đọc module descriptor, phân tích dependency bằng `jdeps`, chọn root module bằng `--add-modules`, quyết định có cần service binding hay không, liên kết bằng `jlink`, rồi kiểm thử image với các luồng chức năng thực tế.

## 1. Module gốc và dependency closure

Trong JPMS, module khai báo quan hệ với module khác bằng `requires` trong `module-info.java`.

Ví dụ:

~~~java
module com.example.audit {
    requires java.logging;
    requires java.sql;
}
~~~

Ứng dụng yêu cầu hai module nền tảng `java.logging` và `java.sql`. Mỗi module này lại có thể phụ thuộc vào module khác. Khi liên kết, `jlink` giải quyết module graph và đưa dependency bắt buộc vào image.

Các khái niệm cần phân biệt:

- **Root module:** module được chỉ định trực tiếp trong `--add-modules`.
- **Required module:** module được một module khác khai báo bằng `requires`.
- **Transitive dependency:** dependency tiếp tục được kéo vào qua các quan hệ module cần thiết.
- **Observable module:** module mà module finder có thể nhìn thấy trên module path hoặc trong hệ thống JDK.
- **Runtime image:** tập module đã được liên kết cùng JVM và thành phần runtime cần thiết.

Ví dụ:

~~~text
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --output audit-image
~~~

`com.example.audit` là root. Các module mà nó bắt buộc yêu cầu, như `java.logging` và `java.sql`, được giải quyết tự động. `java.base` cũng luôn là module nền tảng cơ bản của Java.

Không cần liệt kê thủ công mọi dependency đã được khai báo đúng trong `module-info.java`. Tuy nhiên, module được nạp gián tiếp hoặc được dùng theo cách công cụ không phân tích được có thể cần được thêm rõ ràng.

## 2. Đọc module descriptor trước khi chọn

`module-info.java` là nguồn thông tin quan trọng nhất về quan hệ module tĩnh.

| Chỉ thị | Ý nghĩa đối với việc chọn module |
|---|---|
| `requires other.module` | Khai báo dependency bắt buộc; module đó phải được phân giải |
| `requires transitive other.module` | Dependency được đọc gián tiếp bởi module khác đọc module hiện tại |
| `requires static other.module` | Dependency cần lúc biên dịch nhưng có thể không cần lúc runtime |
| `exports package.name` | Cho phép module khác truy cập package public; không tự kéo thêm module |
| `opens package.name` | Cho phép truy cập reflective sâu; không tự kéo thêm module |
| `uses service.Type` | Khai báo module sử dụng một service |
| `provides service.Type with Impl` | Khai báo module cung cấp implementation cho service |

### 2.1. `requires` và `requires transitive`

`requires` tạo quan hệ readability và dependency giữa các module. Nếu module ứng dụng dùng API của `java.sql`, khai báo `requires java.sql` để compiler và runtime phân giải module đó.

`requires transitive` còn làm dependency được đọc gián tiếp bởi module khác đọc module hiện tại. Điều này thường xuất hiện trong module API công khai khi kiểu của dependency xuất hiện trong chữ ký API.

Với `jlink`, các dependency bắt buộc được giải quyết theo module graph. Hãy khai báo quan hệ đúng trong module descriptor thay vì cố sửa thiếu dependency bằng cách thêm thật nhiều module vào command line.

### 2.2. `requires static`

`requires static` thể hiện dependency tùy chọn ở runtime nhưng vẫn cần có khi biên dịch module khai báo nó. Nếu tính năng tương ứng thực sự được dùng lúc chạy, hãy bảo đảm module đó có mặt trong image bằng cách thêm nó làm root hoặc thông qua một quan hệ bắt buộc khác.

Không nên hiểu `requires static` là cam kết module luôn bị loại khỏi image. Nếu module được thêm trực tiếp hoặc được kéo vào bởi dependency khác, nó vẫn có thể xuất hiện.

### 2.3. `exports`, `opens`, `uses` và `provides`

`exports` và `opens` điều chỉnh quyền truy cập package; chúng không thay thế `requires` và không tự chọn module.

`uses` và `provides` mô tả service. Nếu ứng dụng dùng `ServiceLoader`, cần xem xét module khai báo `uses` lẫn module cung cấp implementation. Tùy cấu hình liên kết, có thể cần dùng `jlink --bind-services` để đưa provider module và dependency của provider vào image.

## 3. Dùng `jdeps` để khám phá dependency

`jdeps` là công cụ phân tích dependency của Java class file, JAR và module. Nó giúp nhận diện module nền tảng được tham chiếu trong bytecode và quan hệ module mà compiler đã ghi.

Với modular JAR trên module path, có thể xem dependency dạng dễ đọc:

~~~text
jdeps --module-path mods --list-deps --module com.example.audit
~~~

Để lấy danh sách module dạng phân cách bằng dấu phẩy:

~~~text
jdeps --module-path mods --print-module-deps --module com.example.audit
~~~

Kết quả `--print-module-deps` có thể dùng làm dữ liệu đầu vào khi xây dựng lệnh liên kết. Với ứng dụng minh họa trong bài này, cần thấy các module trực tiếp `java.logging` và `java.sql`, cùng `java.base`; danh sách cụ thể có thể phụ thuộc bytecode, module descriptor và phiên bản JDK.

Một số tùy chọn hữu ích:

| Tùy chọn | Công dụng |
|---|---|
| `--list-deps` | Liệt kê dependency theo dạng dễ đọc |
| `--list-reduced-deps` | Hiển thị dependency đã được rút gọn theo quan hệ module |
| `--print-module-deps` | In danh sách module dạng CSV, thuận tiện cho `jlink` |
| `--module-path` | Chỉ định nơi tìm module |
| `--module` | Phân tích module có tên được chỉ định |
| `--class-path` | Bổ sung classpath khi phân tích ứng dụng hoặc thư viện |
| `--jdk-internals` | Phát hiện việc phụ thuộc vào API nội bộ của JDK |
| `--ignore-missing-deps` | Tiếp tục phân tích khi thiếu dependency; cần dùng thận trọng |
| `--multi-release` | Chọn phiên bản entry khi phân tích multi-release JAR |

### 3.1. Phân tích ứng dụng dạng JAR

Với JAR chưa phải named module, có thể phân tích dependency nền tảng:

~~~text
jdeps --print-module-deps app.jar
~~~

Nếu ứng dụng có thư viện phụ thuộc bên ngoài, bổ sung classpath thích hợp.

Windows PowerShell:

~~~powershell
jdeps --class-path "lib/*" --print-module-deps app.jar
~~~

macOS/Linux:

~~~sh
jdeps --class-path 'lib/*' --print-module-deps app.jar
~~~

Kết quả giúp xác định các module JDK mà bytecode tham chiếu. Tuy nhiên, `jdeps` không biến ứng dụng classpath thành named module. `jlink` cần các module có thể được phân giải trên module path; ứng dụng cần được modularize hoặc đóng gói thành named module phù hợp trước khi liên kết.

### 3.2. Giới hạn của phân tích tĩnh

`jdeps` phân tích các tham chiếu mà nó nhìn thấy trong class file và module descriptor. Nó có thể không phát hiện đầy đủ dependency được chọn khi chạy, ví dụ:

- `Class.forName("com.vendor.Driver")` với tên lớp nằm trong chuỗi.
- Reflection hoặc framework quét package để tìm implementation.
- Tên provider hoặc plugin được đọc từ file cấu hình.
- Native library được nạp bằng JNI hoặc `System.loadLibrary`.
- Resource và file cấu hình quyết định module/plugin nào được nạp.

Không nên dùng riêng kết quả `jdeps` để khẳng định image đã đủ cho mọi chức năng. Kết hợp phân tích tĩnh với module descriptor, cấu hình framework, danh sách service và kiểm thử thực tế.

## 4. Chọn root module bằng `jlink --add-modules`

Cú pháp cơ bản:

~~~text
jlink --module-path module-path --add-modules module-name[,module-name...] --output image-directory
~~~

`--add-modules` nhận một hoặc nhiều tên module làm root. Linker sẽ giải quyết dependency bắt buộc của các root module và tạo image.

Ví dụ:

~~~text
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --output audit-image
~~~

Trong đó:

- `$JAVA_HOME/jmods` chứa các JMOD của JDK.
- `mods` chứa modular JAR hoặc JMOD của ứng dụng.
- `com.example.audit` là module gốc.
- `audit-image` là thư mục runtime image đầu ra.

Nếu ứng dụng có thêm module được nạp động, chẳng hạn driver hoặc plugin, có thể thêm nó vào danh sách root:

~~~text
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit,com.vendor.driver --output audit-image
~~~

Chỉ thêm module thực sự cần thiết và có mặt trên module path. Tên module phải là tên trong module descriptor, không nhất thiết trùng tên tệp JAR.

## 5. Chọn module thông qua service binding

Java ServiceLoader cho phép module sử dụng service mà không phụ thuộc trực tiếp vào implementation cụ thể.

Module ứng dụng có thể khai báo:

~~~java
module com.example.audit {
    uses com.example.spi.AuditProvider;
}
~~~

Module provider khai báo:

~~~java
module com.example.audit.provider {
    requires com.example.audit.api;
    provides com.example.spi.AuditProvider
        with com.example.provider.DefaultAuditProvider;
}
~~~

Trong thiết kế thực tế, API service thường nằm trong một module riêng để cả ứng dụng và provider cùng đọc được.

Tùy chọn:

~~~text
jlink --bind-services --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --output audit-image
~~~

`--bind-services` yêu cầu linker tìm service provider module phù hợp trong tập module có thể quan sát, rồi liên kết provider cùng dependency của chúng. Điều này hữu ích khi ứng dụng dùng service mà không muốn liệt kê thủ công từng implementation.

Cần cân nhắc:

- Provider phải có mặt trên module path hoặc trong các module hệ thống có thể quan sát.
- Module sử dụng service cần khai báo `uses` phù hợp.
- Provider module phải khai báo `provides` đúng service type.
- Service binding có thể đưa thêm module và dependency vào image, làm image lớn hơn.
- Nếu không dùng service binding, có thể phải thêm provider module tường minh bằng `--add-modules`.

Sau khi liên kết, kiểm tra image và chạy chức năng thực tế để xác nhận provider được tìm thấy.

## 6. Giới hạn tập module có thể quan sát bằng `--limit-modules`

`--limit-modules` giới hạn tập module mà linker có thể quan sát và phân giải. Nó thường được dùng để kiểm soát module universe trong quá trình resolve.

Ví dụ minh họa:

~~~text
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --limit-modules com.example.audit,java.base,java.logging,java.sql --output audit-image
~~~

Tùy chọn này không thay thế `--add-modules`:

- `--add-modules` chọn root module cần đưa vào image.
- `--limit-modules` giới hạn tập module có thể được xem xét để phân giải.

Nếu giới hạn loại bỏ dependency bắt buộc, linker sẽ không thể resolve module graph. Khi dùng `--limit-modules`, cần tính cả dependency bắc cầu của các module gốc và kiểm thử lại image.

Trong nhiều ứng dụng, chỉ định root module rõ ràng bằng `--add-modules` đã đủ. Chỉ thêm `--limit-modules` khi có lý do kiểm soát module universe cụ thể.

## 7. Selector đặc biệt được jlink hỗ trợ

Với jlink, selector đặc biệt được tài liệu hóa cho tùy chọn --add-modules là ALL-MODULE-PATH. Selector này yêu cầu linker đưa mọi module quan sát được trên module path vào tập root để phân giải. Nó hữu ích khi khảo sát hoặc tạo image thử nghiệm, nhưng thường làm runtime image lớn hơn cần thiết.

| Giá trị | Ý nghĩa trong jlink |
|---|---|
| Tên module tường minh, ví dụ java.logging | Chọn module đó làm root; linker tiếp tục phân giải dependency closure |
| ALL-MODULE-PATH | Chọn tất cả module quan sát được trên module path làm root |

Không sao chép các selector ALL-SYSTEM hoặc ALL-DEFAULT từ tài liệu của javac sang lệnh jlink. Cú pháp và tập selector phụ thuộc từng công cụ; hãy xác nhận bằng jlink --help của đúng JDK đang dùng và tài liệu man page tương ứng.

Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules ALL-MODULE-PATH --output all-modules-image
~~~

Lệnh trên có chủ đích tạo image từ toàn bộ module nhìn thấy trên module path. Trong production, ưu tiên liệt kê root module thật sự cần thiết, sau đó kiểm tra dependency và chạy thử image trên môi trường đích.

## 8. Ví dụ hoàn chỉnh: phân tích và chọn module cho Java 17

Ta tạo ứng dụng modular có sử dụng API logging và SQL. Mục tiêu là chọn module nền tảng, tạo runtime image và chạy ứng dụng bằng image đó.

Cấu trúc:

~~~text
project/
  src/
    module-info.java
    com/
      example/
        audit/
          Main.java
  out/
  mods/
  audit-image/
~~~

### 8.1. Khai báo module

Tệp `src/module-info.java`:

~~~java
module com.example.audit {
    requires java.logging;
    requires java.sql;
}
~~~

Tệp `src/com/example/audit/Main.java`:

~~~java
package com.example.audit;

import java.sql.DriverManager;
import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        System.out.println(
                "Logging module: " + Logger.class.getModule().getName());
        System.out.println(
                "SQL module: " + DriverManager.class.getModule().getName());
    }
}
~~~

Chương trình in tên module chứa hai API đang dùng. Nó không mở kết nối cơ sở dữ liệu nên có thể chạy độc lập mà không cần database driver.

### 8.2. Biên dịch và đóng gói modular JAR

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out, mods | Out-Null
javac --release 17 -d out src/module-info.java src/com/example/audit/Main.java
jar --create --file mods/com.example.audit.jar -C out .
~~~

macOS/Linux:

~~~sh
mkdir -p out mods
javac --release 17 -d out src/module-info.java src/com/example/audit/Main.java
jar --create --file mods/com.example.audit.jar -C out .
~~~

JAR có `module-info.class` ở gốc nên có thể được phân giải như named module. Kiểm tra descriptor:

~~~text
jar --describe-module --file mods/com.example.audit.jar
~~~

Chạy thử trước khi tạo image:

~~~text
java --module-path mods -m com.example.audit/com.example.audit.Main
~~~

Stdout:

~~~text
Logging module: java.logging
SQL module: java.sql
~~~

### 8.3. Phân tích dependency bằng `jdeps`

Liệt kê dependency:

~~~text
jdeps --module-path mods --list-deps --module com.example.audit
~~~

Lấy danh sách dạng CSV:

~~~text
jdeps --module-path mods --print-module-deps --module com.example.audit
~~~

Với ứng dụng này, cần thấy hai module được khai báo trực tiếp là `java.logging` và `java.sql`; `java.base` là module nền tảng. Output có thể hiển thị thêm dependency theo module graph và JDK đang dùng.

### 8.4. Tạo runtime image với root module tối thiểu

Trên macOS/Linux:

~~~sh
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --launcher audit=com.example.audit/com.example.audit.Main --output audit-image
~~~

Trên Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.audit --launcher audit=com.example.audit/com.example.audit.Main --output audit-image
~~~

Chỉ định `com.example.audit` làm root. `jlink` tự giải quyết `java.logging`, `java.sql` và dependency bắt buộc của chúng. Không cần thêm toàn bộ module JDK.

### 8.5. Chạy và kiểm tra image

Linux/macOS:

~~~sh
./audit-image/bin/audit
./audit-image/bin/java --list-modules
~~~

Windows PowerShell:

~~~powershell
.\audit-image\bin\audit.exe
.\audit-image\bin\java.exe --list-modules
~~~

Stdout của launcher ứng dụng:

~~~text
Logging module: java.logging
SQL module: java.sql
~~~

Danh sách module của image hiển thị module ứng dụng cùng dependency được liên kết. Tên và phiên bản cụ thể trong `--list-modules` phụ thuộc bản JDK dùng để tạo image.

## 9. Khi nào cần thêm module tường minh?

Dependency tĩnh được khai báo trong module descriptor thường được linker giải quyết tự động. Nhưng một số chức năng cần module bổ sung vì quan hệ đó không thể suy ra đầy đủ từ `requires`.

### 9.1. Nạp lớp theo tên

Ví dụ:

~~~java
Class<?> driver = Class.forName("com.vendor.Driver");
~~~

Tên lớp nằm trong chuỗi nên phân tích tĩnh có thể không xác định được module chứa lớp. Nếu module chứa driver phải có trong image, thêm module đó vào `--add-modules` hoặc cấu hình service provider phù hợp.

### 9.2. Plugin và framework

Framework có thể tìm implementation qua cấu hình, package scanning, reflection hoặc registry. Xác định module plugin thực sự được dùng trong production và đưa chúng vào module path; sau đó chọn root hoặc dùng service binding theo cơ chế framework hỗ trợ.

### 9.3. JNI và native library

Nếu ứng dụng gọi native library, kiểm tra module chứa thư viện và cấu hình đường dẫn native tương ứng. `jdeps` không thể suy ra mọi native dependency từ lời gọi Java. Cần kiểm tra binary theo hệ điều hành/kiến trúc và smoke test trên image.

### 9.4. Resource và file cấu hình

Module selection không tự bảo đảm mọi resource bên ngoài được copy vào image. Kiểm tra resource có nằm trong modular JAR hoặc được đóng gói theo quy trình triển khai riêng. Nếu resource quyết định module/plugin nào được nạp, kiểm tra các module tương ứng.

## 10. Chọn module cho ứng dụng classpath và automatic module

`jlink` làm việc với named module có thể được phân giải trên module path. Một ứng dụng chỉ chạy trên classpath thuộc unnamed module; không thể chỉ đưa JAR classpath đó vào `--add-modules` rồi mong `jlink` đóng gói nó như named module.

Nếu có JAR chưa modularize:

1. Dùng `jdeps` để phân tích dependency và phát hiện API nội bộ.
2. Xác định module name và package của thư viện.
3. Tạo hoặc bổ sung `module-info.java` phù hợp.
4. Kiểm tra `requires`, `exports`, `opens`, `uses` và `provides`.
5. Đóng gói thành named module, rồi mới đưa vào module path cho `jlink`.

Automatic module có thể hữu ích khi ứng dụng dùng trên module path trong một số cấu hình, nhưng không phải đầu vào phù hợp để `jlink` tạo runtime image. Hãy dùng named module thực sự có module descriptor hợp lệ.

## 11. Tối ưu image sau khi chọn module

Sau khi xác định module cần thiết, có thể giảm thành phần phụ trợ bằng các tùy chọn `jlink`:

| Tùy chọn | Tác động |
|---|---|
| `--strip-debug` | Loại bỏ debug information khỏi module được liên kết |
| `--no-header-files` | Không đưa header file vào image |
| `--no-man-pages` | Không đưa man page vào image |
| `--compress` | Nén tài nguyên/module theo mức hỗ trợ |
| `--bind-services` | Bổ sung provider module cho service binding |
| `--launcher` | Tạo launcher cho module và main class |
| `--list-plugins` | Liệt kê plugin liên kết có sẵn |

Ví dụ:

~~~text
jlink --strip-debug --no-header-files --no-man-pages --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.audit --output audit-image
~~~

Chỉ loại bỏ header, man page hoặc debug metadata nếu quy trình vận hành không cần chúng. Việc giảm kích thước không được làm mất thành phần mà ứng dụng hoặc đội vận hành cần để chẩn đoán.

## 12. Lỗi thường gặp khi chọn module

### `Module ... not found`

**Nguyên nhân:** module path thiếu JDK `jmods` hoặc thư mục chứa module ứng dụng; tên module bị nhầm với tên file.

**Cách xử lý:** kiểm tra `--module-path`, dùng `jar --describe-module` hoặc `jmod describe` để xác nhận module name, rồi chạy lại `jdeps`.

### `Module ... does not read ...` hoặc package không được export

**Nguyên nhân:** module descriptor thiếu `requires`, hoặc module cung cấp API chưa export package cần truy cập.

**Cách xử lý:** sửa module descriptor ở đúng phía cung cấp/tiêu thụ API. `--add-modules` không thay thế quan hệ readability hoặc exports.

### Ứng dụng chạy trên JDK đầy đủ nhưng lỗi trong image

**Nguyên nhân:** module được nạp động, service provider, native library hoặc resource chưa được đưa vào image.

**Cách xử lý:** xem lại `jdeps`, module descriptor, cấu hình framework, `uses`/`provides`, và bổ sung module cần thiết. Kiểm thử lại chức năng thực tế bằng launcher trong image.

### Thiếu service provider

**Nguyên nhân:** provider module không được liên kết hoặc service declaration không đúng.

**Cách xử lý:** xác nhận module sử dụng có `uses`, provider có `provides`, provider nằm trên module path và thử `--bind-services`. Nếu cần, thêm provider module tường minh.

### Image lớn hơn dự kiến

**Nguyên nhân:** chọn `ALL-MODULE-PATH` hoặc thêm quá nhiều root module; `--bind-services` cũng có thể liên kết thêm provider phù hợp và dependency của chúng.

**Cách xử lý:** quay lại danh sách root module tối thiểu, xem dependency closure, loại root dư và kiểm thử lại. Không bỏ module chỉ dựa vào kích thước nếu chưa xác nhận không có luồng chức năng nào cần nó.

### `jdeps` báo thiếu dependency hoặc bỏ sót chức năng

**Nguyên nhân:** thiếu JAR trên classpath/module path hoặc dependency chỉ được nạp động.

**Cách xử lý:** cung cấp đầy đủ dependency khi phân tích, không dùng `--ignore-missing-deps` để che lỗi trong báo cáo cuối, và kiểm tra các đường nạp động bằng integration test.

### Image không chạy trên máy khác

**Nguyên nhân:** runtime image được tạo cho hệ điều hành/kiến trúc khác, hoặc native library không tương thích.

**Cách xử lý:** tạo image theo nền tảng đích và kiểm tra binary native, quyền thực thi, launcher cùng biến môi trường triển khai.

## 13. Quy trình chọn module có thể tái hiện

Khi chuẩn bị runtime image, thực hiện theo thứ tự:

1. **Xác định module ứng dụng:** kiểm tra tên module và `module-info.java`.
2. **Đọc quan hệ tĩnh:** liệt kê `requires`, `requires transitive`, `requires static`, `uses` và `provides`.
3. **Phân tích bytecode:** chạy `jdeps --list-deps` và `jdeps --print-module-deps`.
4. **Bổ sung dependency động:** kiểm tra reflection, plugin, service, JNI và resource configuration.
5. **Chọn root:** chỉ định module ứng dụng và các module được nạp động thực sự cần bằng `--add-modules`.
6. **Quyết định service binding:** dùng `--bind-services` khi cần liên kết provider module.
7. **Giới hạn module universe nếu có lý do:** cân nhắc `--limit-modules` và bảo đảm không loại dependency bắt buộc.
8. **Liên kết image:** dùng module path gồm JDK `jmods` và module ứng dụng.
9. **Kiểm tra image:** dùng `java --list-modules` và kiểm tra launcher.
10. **Chạy smoke/integration test:** xác nhận mọi chức năng, service, plugin và native call quan trọng hoạt động trên image.

Ghi lại JDK version, module path, danh sách root, tùy chọn service binding, lệnh `jlink` và nền tảng đích. Điều này giúp build image có thể tái hiện trong CI.

## 14. Checklist ghi nhớ

- [ ] `--add-modules` chọn root module.
- [ ] `jlink` tự giải quyết dependency bắt buộc của root module.
- [ ] `java.base` là module nền tảng luôn cần thiết.
- [ ] `requires` và `requires transitive` mô tả quan hệ module tĩnh.
- [ ] `requires static` là dependency tùy chọn ở runtime; kiểm tra nếu tính năng cần nó.
- [ ] `exports` và `opens` điều chỉnh truy cập, không tự thêm module.
- [ ] `uses` và `provides` mô tả service; cân nhắc `--bind-services`.
- [ ] `jdeps --list-deps` giúp đọc dependency; `--print-module-deps` in danh sách dạng CSV.
- [ ] Phân tích tĩnh có thể bỏ sót reflection, plugin, JNI và nạp lớp theo tên.
- [ ] Module path phải chứa module ứng dụng và JDK `jmods`.
- [ ] `--limit-modules` giới hạn tập module có thể quan sát, không thay thế `--add-modules`.
- [ ] `ALL-MODULE-PATH` và `ALL-SYSTEM` có thể làm image lớn hơn nhu cầu.
- [ ] `jlink` cần named module phù hợp; JAR classpath/automatic module không tự trở thành đầu vào link hợp lệ.
- [ ] Kiểm tra image bằng `--list-modules` và chạy integration test.
- [ ] Tạo image cho đúng hệ điều hành, kiến trúc và native dependency của máy đích.

Chọn module đúng bắt đầu từ module descriptor và phân tích dependency, sau đó kiểm tra cả những thành phần được nạp động. `jdeps` giúp xác định tập dependency tĩnh; `--add-modules` chọn root; `--bind-services` xử lý provider; còn `--limit-modules` kiểm soát module universe. Kết hợp các bước này với kiểm thử trên runtime image sẽ giúp tạo bản triển khai đủ chức năng và tránh mang theo module không cần thiết.