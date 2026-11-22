# Kiểm tra module có tồn tại trong JDK runtime

Khi phát triển ứng dụng modular, một module có thể được khai báo trong `module-info.java` nhưng không tồn tại trong runtime image đang dùng để chạy ứng dụng. Tình huống này thường xuất hiện khi chạy ứng dụng trên một JRE tùy chỉnh được tạo bằng `jlink`, dùng nhầm JDK, hoặc triển khai lên container có bộ module nhỏ hơn môi trường phát triển.

Để kiểm tra chính xác, cần xác định **runtime image mà tiến trình Java thực sự sử dụng**, sau đó tra cứu module trong tập system modules của image đó. Có thể dùng lệnh `java --list-modules`, `java --describe-module` hoặc API `ModuleFinder.ofSystem()`.

## Mục tiêu

Sau bài học, bạn có thể:

- Xác định Java runtime đang được dùng bởi terminal hoặc ứng dụng.
- Liệt kê các module có trong runtime image.
- Tra cứu descriptor của một module cụ thể.
- Dùng ModuleFinder để kiểm tra sự tồn tại của system module bằng Java code.
- Phân biệt module có trong runtime image với module đã được resolve vào boot layer.
- Chẩn đoán lỗi khi module cần thiết không có trong runtime image.
- Kiểm tra tập module trước khi tạo custom runtime bằng jlink.

## 1. Module của JDK và runtime image

JDK được tổ chức thành nhiều module. Mỗi module cung cấp một nhóm API hoặc công cụ có tên riêng, ví dụ:

| Module | Vai trò khái quát |
|---|---|
| `java.base` | Các API nền tảng như `java.lang`, `java.util`, I/O cơ bản và reflection |
| `java.sql` | JDBC API |
| `java.xml` | API XML |
| `java.logging` | Logging API chuẩn |
| `java.desktop` | AWT, Swing và một số API desktop |
| `java.compiler` | API liên quan đến compiler và mô hình ngôn ngữ |
| `jdk.compiler` | Công cụ biên dịch javac và implementation compiler |
| `jdk.jlink` | Công cụ tạo runtime image tùy chỉnh |

Một bản JDK thông thường chứa nhiều module, nhưng runtime image có thể được tạo với tập module nhỏ hơn. Ví dụ, nhà phát triển có thể dùng `jlink` để tạo runtime chỉ chứa những module mà ứng dụng cần.

Vì vậy, việc một module có trong một bản JDK cài trên máy phát triển không bảo đảm module đó có trong runtime image mà ứng dụng production đang sử dụng.

### 1.1. Module name khác package name

Module name là định danh của module trong module graph. Package name là tên namespace của class.

Ví dụ:

- Module: `java.sql`
- Package: `java.sql`
- Class: `java.sql.Connection`

Trong trường hợp này module và package trùng tên, nhưng đó không phải quy tắc bắt buộc. Một module có thể chứa nhiều package.

Khi kiểm tra module, hãy dùng module name như `java.sql`. Khi kiểm tra class, hãy dùng tên đầy đủ như `java.sql.Connection`.

### 1.2. java.base luôn có mặt

Mọi named module đều phụ thuộc trực tiếp hoặc gián tiếp vào `java.base`. Đây là module nền tảng của Java và luôn có trong runtime image hợp lệ.

Các module khác như `java.sql`, `java.xml`, `java.desktop`, `jdk.compiler` hoặc `jdk.jlink` có thể không có trong một runtime image tối giản.

## 2. Xác định runtime đang được sử dụng

Trước khi kiểm tra module, cần xác định đúng executable Java. Một máy có thể cài nhiều phiên bản JDK, nhiều bản JRE hoặc một runtime image được tạo riêng.

### 2.1. Kiểm tra phiên bản Java

Chạy:

~~~bash
java --version
~~~

Ví dụ đầu ra:

~~~text
openjdk 21.0.2 2024-01-16
OpenJDK Runtime Environment
OpenJDK 64-Bit Server VM
~~~

Lệnh cho biết phiên bản của executable `java` được shell tìm thấy. Nó chưa cho biết đầy đủ đường dẫn cài đặt.

### 2.2. Kiểm tra đường dẫn executable

Trên Windows PowerShell:

~~~powershell
Get-Command java -All | Select-Object Source
Get-Command javac -All | Select-Object Source
~~~

Hoặc trong Command Prompt:

~~~cmd
where java
where javac
~~~

Trên Linux hoặc macOS:

~~~bash
command -v java
command -v javac
~~~

Nếu có nhiều kết quả, shell có thể đang chọn một Java khác với Java mà IDE hoặc service sử dụng. Hãy kiểm tra executable cụ thể thay vì chỉ dựa vào giá trị `JAVA_HOME`.

Có thể gọi trực tiếp Java trong `JAVA_HOME`:

Trên Windows:

~~~powershell
& "$env:JAVA_HOME\bin\java.exe" --version
& "$env:JAVA_HOME\bin\java.exe" --list-modules
~~~

Trên Linux hoặc macOS:

~~~bash
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/java" --list-modules
~~~

### 2.3. Kiểm tra java.home bên trong ứng dụng

Nếu ứng dụng chạy qua IDE, service manager, container hoặc script riêng, runtime của tiến trình có thể khác runtime trong terminal.

In thông tin runtime ngay trong ứng dụng:

~~~java
public class RuntimeInfo {
    public static void main(String[] args) {
        System.out.println("java.version = "
            + System.getProperty("java.version"));

        System.out.println("java.home = "
            + System.getProperty("java.home"));

        System.out.println("java.vendor = "
            + System.getProperty("java.vendor"));

        System.out.println("Runtime.version = "
            + Runtime.version());
    }
}
~~~

`java.home` cho biết thư mục runtime mà JVM đang chạy sử dụng. Đây là bằng chứng hữu ích khi đối chiếu kết quả kiểm tra từ terminal với môi trường thực tế của ứng dụng.

## 3. Liệt kê module có trong runtime image

### 3.1. Dùng java --list-modules

Lệnh cơ bản:

~~~bash
java --list-modules
~~~

Ví dụ một phần kết quả:

~~~text
java.base@21.0.2
java.compiler@21.0.2
java.datatransfer@21.0.2
java.desktop@21.0.2
java.logging@21.0.2
java.sql@21.0.2
java.xml@21.0.2
jdk.compiler@21.0.2
jdk.jlink@21.0.2
~~~

Tên module đứng trước ký tự `@` là module name. Phần sau `@` thường là phiên bản module được cung cấp bởi runtime.

Khi chạy lệnh mà không bổ sung module path của ứng dụng, danh sách cho biết các system modules có thể quan sát từ runtime image hiện tại. Đây là bước kiểm tra nhanh để xác định module JDK có sẵn hay không.

### 3.2. Tìm một module cụ thể

Trên Windows PowerShell:

~~~powershell
java --list-modules | Select-String '^java.sql(@|$)'
~~~

Trên Command Prompt:

~~~cmd
java --list-modules | findstr /B java.sql
~~~

Trên Linux hoặc macOS:

~~~bash
java --list-modules | grep '^java.sql@'
~~~

Nếu có kết quả, runtime image hiện tại có module `java.sql`. Nếu không có kết quả, hãy xác nhận lại executable Java và runtime image đang được kiểm tra.

Ví dụ kiểm tra module compiler:

~~~bash
java --list-modules | grep '^jdk.compiler@'
~~~

Trên Windows có thể thay `grep` bằng `Select-String` hoặc `findstr`.

### 3.3. Đọc kết quả đúng cách

Nếu kết quả có:

~~~text
java.sql@21.0.2
~~~

Điều đó cho biết system module `java.sql` có trong runtime image đang được truy vấn.

Nếu không có:

~~~text
~~~

Không thể kết luận ngay rằng toàn bộ JDK bị lỗi. Runtime có thể là một custom image chỉ chứa các module cần thiết. Hãy kiểm tra `java.home`, đường dẫn executable và cách runtime image được tạo.

## 4. Xem descriptor của module bằng java --describe-module

Khi đã xác định module tồn tại, dùng:

~~~bash
java --describe-module java.sql
~~~

Lệnh hiển thị module descriptor, gồm thông tin như:

- Tên module.
- Các package được chứa hoặc export.
- Các dependency `requires`.
- Các service được `uses`.
- Các provider được `provides`, nếu có.

Ví dụ đầu ra rút gọn có thể chứa:

~~~text
java.sql
exports java.sql
exports javax.sql
requires java.logging
requires java.transaction.xa
requires java.base mandated
uses java.sql.Driver
~~~

Đầu ra thực tế phụ thuộc phiên bản JDK. Hãy dùng nó để xác nhận tên module, package và dependency mà module công bố.

Có thể kiểm tra module khác:

~~~bash
java --describe-module java.xml
java --describe-module java.logging
java --describe-module jdk.compiler
~~~

Nếu module không được tìm thấy trong runtime image, lệnh có thể báo lỗi tìm module. Khi đó quay lại kiểm tra danh sách module và executable Java.

### 4.1. Phân biệt với jar --describe-module

Hai lệnh có mục đích khác nhau:

~~~bash
java --describe-module java.sql
~~~

Tra cứu module trong môi trường Java runtime hiện tại.

~~~bash
jar --describe-module --file libs/payment.jar
~~~

Tra cứu descriptor hoặc tên module của một JAR cụ thể.

Một JAR trên đĩa có thể là explicit module hoặc automatic module. Việc JAR tồn tại không chứng minh module cùng tên là một system module của JDK.

## 5. Kiểm tra bằng Java API với ModuleFinder.ofSystem()

Nếu cần kiểm tra trong code, dùng API `java.lang.module.ModuleFinder`.

`ModuleFinder.ofSystem()` tạo finder cho các system modules của runtime image hiện tại. Có thể gọi `find(moduleName)` để kiểm tra một module cụ thể.

Ví dụ:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.util.Optional;

public class CheckSystemModule {
    public static void main(String[] args) {
        String moduleName = "java.sql";

        Optional<ModuleReference> reference =
            ModuleFinder.ofSystem().find(moduleName);

        System.out.println(
            moduleName + " exists: " + reference.isPresent()
        );

        reference.ifPresent(module ->
            System.out.println(
                "Found module: " + module.descriptor().name()
            )
        );
    }
}
~~~

Nếu `find()` trả về một `Optional` có giá trị, module được tìm thấy trong system modules của runtime image hiện tại.

Có thể thay `java.sql` bằng `java.xml`, `java.desktop`, `jdk.compiler` hoặc module cần kiểm tra khác.

### 5.1. Kiểm tra nhiều module

Ví dụ kiểm tra một danh sách:

~~~java
import java.lang.module.ModuleFinder;
import java.util.List;

public class CheckSeveralModules {
    public static void main(String[] args) {
        List<String> names = List.of(
            "java.base",
            "java.sql",
            "java.xml",
            "java.desktop",
            "jdk.compiler"
        );

        ModuleFinder finder = ModuleFinder.ofSystem();

        for (String name : names) {
            boolean exists = finder.find(name).isPresent();
            System.out.printf("%-18s %s%n", name, exists);
        }
    }
}
~~~

Kết quả phụ thuộc runtime image đang chạy. Một custom image có thể có `java.base` và `java.sql` nhưng thiếu `java.desktop` hoặc `jdk.compiler`.

### 5.2. Kiểm tra descriptor

Sau khi tìm thấy module, có thể đọc descriptor:

~~~java
ModuleFinder.ofSystem()
    .find("java.sql")
    .ifPresent(reference -> {
        var descriptor = reference.descriptor();

        System.out.println("Name: " + descriptor.name());
        System.out.println("Packages: " + descriptor.packages());
        System.out.println("Requires: " + descriptor.requires());
        System.out.println("Exports: " + descriptor.exports());
    });
~~~

Đoạn code giúp kiểm tra cấu trúc module mà runtime cung cấp mà không cần mở file JMOD thủ công.

## 6. Module có trong runtime image và module đã resolve là hai trạng thái khác nhau

Đây là điểm quan trọng khi debug JPMS.

Một system module có thể tồn tại trong runtime image nhưng chưa được đưa vào module graph của ứng dụng đang chạy. Module chỉ được resolve khi là root module hoặc được yêu cầu gián tiếp qua dependency/service binding phù hợp.

Có hai cách kiểm tra khác nhau:

| Câu hỏi | Cách kiểm tra |
|---|---|
| Runtime image có cung cấp module không? | `ModuleFinder.ofSystem().find(name)` hoặc `java --list-modules` |
| Module đã được resolve vào boot layer chưa? | `ModuleLayer.boot().findModule(name)` |

Ví dụ:

~~~java
import java.lang.module.ModuleFinder;

public class ModuleState {
    public static void main(String[] args) {
        String name = "java.sql";

        boolean inRuntimeImage =
            ModuleFinder.ofSystem().find(name).isPresent();

        boolean inBootLayer =
            ModuleLayer.boot().findModule(name).isPresent();

        System.out.println("In runtime image: " + inRuntimeImage);
        System.out.println("In boot layer: " + inBootLayer);
    }
}
~~~

Nếu `inRuntimeImage` là `true` nhưng `inBootLayer` là `false`, module có sẵn trong runtime image nhưng chưa được resolve vào boot layer của tiến trình.

Muốn module được resolve khi khởi chạy, ứng dụng có thể khai báo `requires` trong descriptor hoặc bổ sung root module phù hợp bằng tùy chọn `--add-modules`.

Ví dụ:

~~~bash
java --add-modules java.sql --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Không cần thêm `--add-modules` nếu ứng dụng đã khai báo dependency cần thiết bằng `requires`.

## 7. Kiểm tra module graph thực tế của ứng dụng

Khi cần biết module nào thực sự được resolve lúc khởi động, dùng:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Tùy chọn `--show-module-resolution` in thông tin resolution, bao gồm các module được chọn làm root và các dependency được resolve.

So sánh ba lệnh:

~~~bash
java --list-modules
java --describe-module java.sql
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.app.Main
~~~

- `--list-modules`: liệt kê các module có thể quan sát trong runtime/module path của lần gọi.
- `--describe-module`: xem descriptor của một module.
- `--show-module-resolution`: xem module graph được resolve khi chạy ứng dụng cụ thể.

Đừng dùng kết quả của `--show-module-resolution` để kết luận module không xuất hiện trong runtime image. Một module có thể có sẵn nhưng không được chọn vào graph của ứng dụng.

## 8. Khi module cần thiết không tồn tại trong runtime

Giả sử module app khai báo:

~~~java
module com.acme.app {
    requires java.sql;
}
~~~

Nhưng runtime image triển khai không chứa `java.sql`. Khi resolve module graph, JVM không thể tìm dependency bắt buộc và ứng dụng có thể thất bại với lỗi dạng:

~~~text
java.lang.module.FindException:
Module java.sql not found, required by com.acme.app
~~~

Cách xử lý:

1. Xác định chính xác runtime image mà ứng dụng đang chạy.
2. Dùng `java --list-modules` để kiểm tra module còn thiếu.
3. Kiểm tra module có thực sự cần thiết với chức năng ứng dụng không.
4. Nếu cần, tạo lại runtime image có chứa module đó.
5. Chạy lại ứng dụng bằng đúng runtime image vừa tạo.

Không thể khắc phục việc thiếu system module bằng cách chỉ thêm một dòng `requires`. `requires` khai báo dependency; runtime image vẫn phải cung cấp module tương ứng.

## 9. Tạo custom runtime có module cần thiết bằng jlink

`jlink` tạo runtime image tùy chỉnh từ các module có sẵn. Công cụ này phù hợp khi muốn đóng gói runtime nhỏ hơn một JDK đầy đủ.

Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods"       --add-modules com.acme.app,java.sql       --output app-runtime
~~~

Trong ví dụ:

- `$JAVA_HOME/jmods` cung cấp các JDK modules từ JDK đang dùng.
- `mods` cung cấp module của ứng dụng.
- `--add-modules` chọn root modules cho runtime image.
- `--output` xác định thư mục runtime được tạo.

Trên Windows, dấu phân cách giữa các vị trí module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app,java.sql --output app-runtime
~~~

Nếu module được chỉ định không có trong nguồn module finder, `jlink` sẽ báo lỗi. Nếu app đã khai báo `requires java.sql;`, dependency này cũng được đưa vào quá trình giải quyết khi tạo image từ root app.

Sau khi tạo image, kiểm tra chính runtime mới:

~~~bash
app-runtime/bin/java --list-modules
~~~

Trên Windows:

~~~powershell
.\app-runtime\bin\java.exe --list-modules
~~~

Đây là bước xác nhận runtime image được tạo có module mong muốn. Không nên chỉ kiểm tra JDK dùng để chạy `jlink`, vì tập module của image đầu ra có thể nhỏ hơn JDK nguồn.

## 10. Dùng jdeps để tìm module ứng dụng cần

Khi không chắc ứng dụng cần những system module nào, có thể dùng `jdeps` để phân tích dependency tĩnh.

Với một JAR thông thường:

~~~bash
jdeps --print-module-deps --class-path "libs/*" app.jar
~~~

Với named module:

~~~bash
jdeps --print-module-deps --module-path mods --module com.acme.app
~~~

Kết quả có thể được dùng làm đầu vào cho `jlink --add-modules`.

Ví dụ kết quả rút gọn:

~~~text
java.base,java.logging,java.sql
~~~

Lưu ý:

- `jdeps` phân tích dependency có thể suy ra từ bytecode.
- Reflection, class name lấy từ cấu hình, plugin và class loading động có thể không được phát hiện đầy đủ.
- Cần kiểm tra thêm các module mà ứng dụng sử dụng qua `ServiceLoader` hoặc cơ chế nạp động.
- Luôn chạy kiểm thử trên runtime image cuối cùng.

## 11. Lỗi và nhầm lẫn thường gặp

### 11.1. Terminal có module nhưng ứng dụng vẫn báo thiếu

Nguyên nhân thường là terminal và ứng dụng sử dụng hai Java executable khác nhau. Kiểm tra `java.home` bên trong tiến trình và so sánh với đường dẫn của lệnh `java` trong terminal.

### 11.2. Module có trong JDK nhưng không có trong custom runtime

JDK đầy đủ và runtime image tạo bằng `jlink` có thể chứa tập module khác nhau. Chạy `--list-modules` bằng executable của custom runtime để kiểm tra.

### 11.3. Module không được resolve nhưng thực tế vẫn có

`java --list-modules` có thể liệt kê module, trong khi `ModuleLayer.boot().findModule(name)` trả về rỗng. Điều này có thể bình thường vì module chưa được đưa vào graph khởi động.

### 11.4. Nhầm module với package

Một package có thể thuộc một module nhưng không được export. Việc tìm thấy module không đảm bảo module sử dụng có thể truy cập mọi package bên trong.

### 11.5. Nhầm JAR với system module

Một thư viện JAR nằm trên module path có thể là explicit named module hoặc automatic module. Nó không vì thế trở thành module thuộc JDK runtime image. Dùng `ModuleFinder.ofSystem()` để kiểm tra system modules; dùng `ModuleFinder.of(path)` để tìm module từ nguồn bên ngoài.

## 12. Quy trình kiểm tra thực tế

Khi được giao xác minh một module có tồn tại trong JDK runtime, thực hiện theo trình tự:

1. Lấy đường dẫn Java executable đang chạy ứng dụng.
2. In `java.home` và `java.version` từ chính tiến trình nếu có thể.
3. Chạy `java --list-modules` bằng đúng executable đó.
4. Tìm tên module chính xác trong danh sách.
5. Dùng `java --describe-module <module-name>` để xem descriptor.
6. Nếu cần kiểm tra bằng code, dùng `ModuleFinder.ofSystem().find(name)`.
7. Nếu cần biết module đã được resolve chưa, kiểm tra `ModuleLayer.boot().findModule(name)`.
8. Nếu thiếu module trong custom runtime, cập nhật danh sách root cho `jlink` rồi tạo và kiểm tra lại image.
9. Chạy ứng dụng và quan sát `--show-module-resolution` để xác nhận module graph thực tế.

## 13. Tự kiểm tra

**Tình huống 1:** Lệnh `java --list-modules` hiển thị `java.sql@21.0.2`. Tên module cần dùng trong `requires` là gì?

**Trả lời:** `java.sql`. Phần sau dấu `@` là thông tin phiên bản.

**Tình huống 2:** `ModuleFinder.ofSystem().find("java.sql")` có giá trị nhưng `ModuleLayer.boot().findModule("java.sql")` rỗng. Có phải runtime bị lỗi?

**Trả lời:** Không nhất thiết. Module có trong runtime image nhưng chưa được resolve vào boot layer của tiến trình.

**Tình huống 3:** Vì sao `java --list-modules` trên máy phát triển có `java.desktop`, nhưng custom runtime lại không có?

**Trả lời:** Custom runtime có thể được tạo bằng jlink với tập root modules nhỏ hơn và không bao gồm dependency dẫn tới `java.desktop`.

**Tình huống 4:** `module-info.java` có `requires java.xml;` nhưng ứng dụng báo module không tìm thấy. Cần kiểm tra gì?

**Trả lời:** Kiểm tra runtime image thực tế, executable Java và kết quả `java --list-modules`. Nếu image thiếu `java.xml`, cần tạo lại image có module đó.

**Tình huống 5:** Lệnh nào xem descriptor của system module `java.sql`?

**Trả lời:** `java --describe-module java.sql`.

**Tình huống 6:** Muốn kiểm tra module system có tồn tại ngay bên trong ứng dụng Java, nên dùng API nào?

**Trả lời:** Dùng `ModuleFinder.ofSystem().find(moduleName)` và kiểm tra `Optional` trả về.

**Tình huống 7:** Muốn biết module nào thực sự được resolve khi chạy ứng dụng, dùng tùy chọn nào?

**Trả lời:** Dùng `--show-module-resolution` trong lệnh khởi chạy.

Khi kiểm tra module JDK, hãy luôn gắn kết quả với đúng runtime image đang chạy ứng dụng. Liệt kê module xác nhận module có sẵn; xem descriptor xác nhận nội dung module; kiểm tra boot layer xác nhận module đã được resolve; còn log module resolution cho biết graph của ứng dụng được hình thành ra sao.
