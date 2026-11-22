# Chọn classpath hay module path trong Java

## 1. Hai cơ chế tìm và tổ chức dependency

Java có hai cách phổ biến để cung cấp class và thư viện cho compiler hoặc JVM:

- **Classpath** là cơ chế truyền thống. Nó liệt kê thư mục chứa class và các JAR mà ứng dụng cần tìm.
- **Module path** là cơ chế của Java Platform Module System (JPMS), có từ Java 9. Nó liệt kê các module có tên để compiler và JVM phân giải quan hệ phụ thuộc giữa chúng.

Cả hai đều giúp Java tìm bytecode, nhưng cách chúng biểu diễn ranh giới và quyền truy cập khác nhau. Classpath chủ yếu trả lời câu hỏi “class nằm ở đâu?”. Module path còn trả lời “module nào cần module nào, package nào được công khai và package nào chỉ dành cho reflection?”.

Không có lựa chọn bắt buộc cho mọi dự án. Ứng dụng Java truyền thống có thể tiếp tục dùng classpath. Ứng dụng muốn dùng JPMS cần module descriptor và module path cho các module mà nó phụ thuộc.

## 2. Classpath hoạt động như thế nào?

Classpath là danh sách các vị trí tìm kiếm class và resource. Mỗi phần tử thường là:

- Một thư mục có cấu trúc package.
- Một file JAR.
- Một wildcard như `lib/*` để đưa các JAR trong thư mục lib vào classpath.

Ví dụ project có:

```text
legacy-app/
├── app.jar
├── lib/
│   ├── json.jar
│   └── logging.jar
└── config/
```

Chạy ứng dụng trên Windows:

```powershell
java -cp "app.jar;lib/*" com.example.app.Main
```

Trên Linux hoặc macOS:

```bash
java -cp 'app.jar:lib/*' com.example.app.Main
```

Dấu phân cách phần tử classpath là dấu chấm phẩy (`;`) trên Windows và dấu hai chấm (`:`) trên Linux/macOS. Dùng dấu nháy để shell không diễn giải wildcard theo cách ngoài ý muốn.

Có thể dùng các dạng tương đương `-cp`, `-classpath` hoặc `--class-path`. Khi không truyền classpath rõ ràng, Java launcher dùng biến môi trường `CLASSPATH` nếu được đặt, nếu không thì mặc định là thư mục hiện tại. Trong script build và CI, nên chỉ định classpath tường minh để kết quả không phụ thuộc cấu hình máy.

Classpath cũng được dùng khi biên dịch:

```bash
javac --release 17 -cp "lib/json.jar" -d out src/com/example/app/Main.java
```

`javac` ghi class vào thư mục `out`. Khi chạy, thư mục đó và dependency JAR phải xuất hiện trong classpath.

## 3. Unnamed module và giới hạn của classpath

Từ Java 9, code được nạp từ classpath thuộc về **unnamed module** của class loader tương ứng. Module này không có tên và không cần `module-info.java`.

Unnamed module có thể đọc các module quan sát được và các package của nó được export/open theo quy tắc của unnamed module. Tuy vậy, code trên classpath không nhận được các ranh giới dependency tường minh như module có tên.

Classpath không khai báo:

- Module này yêu cầu module nào.
- Package nào là API công khai của một module.
- Package nào chỉ được mở cho reflection.
- Dependency nào là bắt buộc khi biên dịch hay chỉ cần lúc chạy.

Vì vậy, ứng dụng classpath thường dựa vào convention, dependency manager và thứ tự classpath để tránh xung đột.

Một classpath có thể chứa nhiều JAR cùng khai báo một package. Hai JAR cũng có thể chứa class trùng tên. Khi class loader tìm thấy class đầu tiên theo thứ tự tìm kiếm, bản đó có thể che khuất bản còn lại. Đây là nguồn gây lỗi khó chẩn đoán khi ứng dụng dùng nhiều phiên bản thư viện.

## 4. Module path hoạt động như thế nào?

Module path chứa các module mà compiler hoặc JVM có thể quan sát và phân giải. Một phần tử module path có thể là:

- Modular JAR có file `module-info.class` ở gốc archive.
- Thư mục module đã giải nén (exploded module).
- JAR không có descriptor nhưng được coi là automatic module khi đặt trên module path.

Ví dụ chạy một ứng dụng modular:

```bash
java --module-path mods -m com.example.app/com.example.app.Main
```

`--module-path` (viết tắt `-p`) chỉ nơi tìm module. Tùy chọn `-m` chỉ module khởi chạy và class main. Cú pháp `module/class` giúp launcher biết class main thuộc module nào.

Khác với classpath, module path tạo điều kiện để JVM xây dựng module graph. Module graph xác định module gốc, các module được yêu cầu và quan hệ readability giữa chúng. Nếu thiếu một module bắt buộc hoặc có xung đột module/package, quá trình phân giải có thể thất bại trước khi main chạy.

## 5. Module descriptor: module-info.java

Một module tường minh khai báo tên và các directive trong file `module-info.java`. File này nằm ở gốc source của module, không nằm trong package thông thường.

Ví dụ:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

Module ứng dụng có thể yêu cầu module thư viện:

```java
module com.example.app {
    requires com.example.greeter;
}
```

Các directive quan trọng:

| Directive | Ý nghĩa |
|---|---|
| `requires` | Khai báo module dependency |
| `requires transitive` | Module consumer cũng đọc được dependency này qua module hiện tại |
| `requires static` | Dependency cần khi compile, có thể không cần lúc runtime |
| `exports` | Công khai package cho module khác truy cập ở compile time và runtime |
| `opens` | Mở package cho deep reflection lúc runtime |
| `uses` | Khai báo module sử dụng một service |
| `provides ... with ...` | Đăng ký implementation cho service |

Một class `public` chưa chắc được module khác truy cập. Package chứa class phải được module xuất qua `exports`, và module consumer phải đọc được module cung cấp package đó.

## 6. Readability và accessibility là hai điều kiện riêng

Module system phân biệt hai câu hỏi:

1. **Readability:** module hiện tại có quan hệ đọc module chứa kiểu mà nó muốn sử dụng không?
2. **Accessibility:** package và kiểu cần dùng có được module kia công khai phù hợp không?

Ví dụ, module A khai báo `requires B` để đọc module B. Nhưng nếu B không `exports` package chứa class cần dùng, A vẫn không thể truy cập class đó qua API Java thông thường.

`exports` kiểm soát truy cập API giữa module. `opens` phục vụ reflection sâu, chẳng hạn framework cần đọc private field để inject hoặc deserialize. `opens` không thay thế `exports` khi code cần import và gọi kiểu trong package ở compile time.

Có thể mở riêng một package cho framework:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.json;
}
```

Chỉ module `com.example.json` được mở package `internal` theo directive trên. Dùng mở package có giới hạn sẽ giữ encapsulation tốt hơn mở toàn bộ module.

`open module` mở tất cả package cho deep reflection, nhưng không có nghĩa tất cả package tự động trở thành API được export ở compile time. Chỉ dùng khi framework thực sự cần quyền reflection rộng.

## 7. So sánh trực tiếp classpath và module path

| Tiêu chí | Classpath | Module path |
|---|---|---|
| Đơn vị tìm kiếm | Thư mục và JAR | Module có tên, automatic module, exploded module |
| Descriptor | Không bắt buộc | Module tường minh có `module-info` |
| Dependency graph | Không khai báo trong Java | `requires` và module resolution |
| Encapsulation | Package không có module boundary | `exports` và `opens` |
| Tên module | Unnamed module | Tên module ổn định |
| Split package | Có thể xuất hiện giữa nhiều JAR | Xung đột package giữa named modules bị kiểm soát |
| Dependency cũ | Tương thích trực tiếp | Có thể dùng qua automatic module hoặc classpath bridge |
| Launch | Tên class main | Module và class main |
| Phù hợp | Ứng dụng legacy, script, thư viện chưa modular | Ứng dụng có module boundary rõ ràng |

Module path cung cấp kiểm soát kiến trúc mạnh hơn nhưng yêu cầu quản lý module name, descriptor và package exports. Classpath dễ tiếp nhận thư viện cũ và thường ít thay đổi cấu hình hơn.

## 8. Khi nào nên chọn classpath?

Classpath thường là lựa chọn hợp lý khi:

- Ứng dụng chưa có module descriptor và không cần module boundary.
- Hệ thống legacy có nhiều dependency cũ chưa có module name ổn định.
- Framework hoặc plugin phụ thuộc cách nạp class từ classpath.
- Dự án nhỏ, ví dụ học Java, command-line tool hoặc script chạy độc lập.
- Việc modular hóa chưa mang lại lợi ích đủ lớn để bù chi phí migration.

Giữ classpath không có nghĩa là ứng dụng không thể dùng JDK mới. Java 17+ vẫn chạy các ứng dụng classpath bình thường. JPMS là lựa chọn kiến trúc, không phải điều kiện để sử dụng ngôn ngữ Java hiện đại.

Với classpath, vẫn cần quản lý version dependency, tránh JAR trùng class, kiểm soát thứ tự classpath và kiểm tra runtime classpath trong CI.

## 9. Khi nào nên chọn module path?

Module path đáng cân nhắc khi:

- Ứng dụng có nhiều module do team hoặc nhóm độc lập phát triển.
- Cần khai báo dependency rõ ràng giữa các phần.
- Muốn giới hạn package public và ẩn implementation package.
- Cần phát hiện dependency thiếu hoặc split package sớm.
- Cần tích hợp Java ServiceLoader theo module descriptor.
- Muốn chuẩn bị ứng dụng cho custom runtime image bằng jlink.
- Cần kiểm soát reflection và quyền truy cập giữa các module.

Không nên modular hóa chỉ để đổi tên classpath thành module path. Giá trị chính là tạo boundary có thể kiểm tra được. Nếu tất cả package vẫn export rộng, module descriptor không phản ánh API thực và dependency không đồng bộ, lợi ích sẽ giảm.

## 10. Explicit module, automatic module và unnamed module

Java có ba trường hợp dependency thường gặp:

| Loại | Nhận diện | Đặc điểm |
|---|---|---|
| Explicit module | JAR có `module-info.class` | Khai báo dependency và package exports rõ ràng |
| Automatic module | JAR không có descriptor nhưng nằm trên module path | Tên module được xác định từ manifest hoặc tên JAR; export/open mọi package và đọc các module quan sát được |
| Unnamed module | Code/JAR nằm trên classpath | Không có tên module; tương thích với cách tổ chức trước Java 9 |

Explicit module là mục tiêu tốt nhất khi thư viện đã sẵn sàng modular hóa.

Automatic module là cầu nối hữu ích khi thư viện chưa có `module-info.java` nhưng cần được `requires` từ explicit module. Nó không có danh sách dependency tường minh và mở tất cả package, do đó không tạo encapsulation mạnh như explicit module.

Unnamed module phù hợp cho ứng dụng classpath. Explicit module không tự động đọc unnamed module; muốn nối hai mô hình phải dùng tùy chọn module-system đặc biệt hoặc chuyển dependency sang module phù hợp.


## 11. Automatic-Module-Name và tên module ổn định

Một JAR không có `module-info.class` có thể được coi là automatic module khi đặt trên module path. Tên module có thể lấy từ thuộc tính `Automatic-Module-Name` trong manifest. Nếu thuộc tính này không có, Java suy ra tên từ tên file JAR theo quy tắc đặt tên module.

Ví dụ thêm tên ổn định cho một thư viện đang chuyển đổi dần:

```groovy
tasks.named('jar') {
    manifest {
        attributes('Automatic-Module-Name': 'com.example.greeter')
    }
}
```

Sau đó module khác có thể khai báo:

```java
module com.example.app {
    requires com.example.greeter;
}
```

`Automatic-Module-Name` không tạo explicit module descriptor. JAR vẫn là automatic module; nó chỉ có tên module ổn định để consumer không phụ thuộc vào tên file JAR. Khi thư viện phát hành `module-info.class` thực sự, descriptor sẽ cung cấp module metadata tường minh.

Kiểm tra tên module của JAR:

```bash
jar --describe-module --file lib/greeter.jar
```

Không dùng artifactId Maven hoặc tên project Gradle để đoán module name. Các tên này có thể khác nhau. Hãy đọc descriptor hoặc manifest của chính artifact.

## 12. Vì sao thư viện không modular có thể gây khó khi chuyển đổi?

Một explicit module không thể trực tiếp khai báo `requires` tới unnamed module. Ví dụ, nếu thư viện cũ chỉ là JAR thường và được giữ trên classpath, module mới không thể viết `requires legacy.library` để đọc nó.

Các hướng xử lý:

1. Nâng cấp thư viện lên bản có explicit module descriptor.
2. Dùng bản thư viện có `Automatic-Module-Name` và đặt trên module path.
3. Thêm `Automatic-Module-Name` khi chính bạn phát hành thư viện.
4. Tạo adapter module cho dependency legacy nếu cần.
5. Dùng `--add-reads` như giải pháp tương thích có kiểm soát trong thời gian chuyển đổi.

Automatic module có thể đọc unnamed module trong một số tình huống, nhưng đây là cầu nối một chiều hữu ích hơn cho migration; không nên coi đó là thiết kế module lâu dài. Trước khi chuyển dependency, kiểm tra thư viện thực tế có module descriptor hay automatic module name.

## 13. Split package và duplicate class

Classpath có thể chứa cùng package trong nhiều JAR, hoặc hai JAR cùng chứa một class. Thứ tự classpath có thể quyết định class nào được nạp. Điều này khiến lỗi phụ thuộc môi trường và khó tái hiện.

Module path kiểm soát package ở cấp module. Hai named modules không được cùng đóng góp package trùng nhau vào một cấu hình module hợp lệ. Một số cấu trúc legacy dựa vào split package vì thế không thể chuyển thẳng lên JPMS mà không tái cấu trúc.

Cách điều tra:

- Liệt kê JAR và module dependency thực tế.
- Tìm class trùng tên hoặc package bị chia giữa các artifact.
- Dùng `jdeps` để phân tích dependency.
- Dùng `jar --describe-module` để xem module name và package.
- Tách package hoặc gom class liên quan về một module duy nhất.

Không xử lý split package bằng cách đổi thứ tự module path. Cần sửa cấu trúc artifact hoặc chọn cách chạy tương thích phù hợp.

## 14. Biên dịch ứng dụng dùng classpath

Ví dụ có thư viện `Greeter` và class main `Main`. Hai file không có `module-info.java`.

```java
package com.example.greeter;

public final class Greeter {
    private Greeter() { }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

```java
package com.example.app;

import com.example.greeter.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.greet("JPMS"));
    }
}
```

Biên dịch thư viện và đóng JAR:

```bash
javac --release 17 -d out/lib src/com/example/greeter/Greeter.java
jar --create --file lib/greeter.jar -C out/lib .
```

Biên dịch ứng dụng dựa vào JAR:

```bash
javac --release 17 -cp lib/greeter.jar -d out/app src/com/example/app/Main.java
```

Chạy trên Windows:

```powershell
java -cp "out/app;lib/greeter.jar" com.example.app.Main
```

Chạy trên Linux/macOS:

```bash
java -cp 'out/app:lib/greeter.jar' com.example.app.Main
```

Stdout chính xác:

```text
Hello, JPMS!
```

Cả thư viện và ứng dụng đều thuộc unnamed module của class loader tương ứng. Không cần khai báo quan hệ `requires` hay `exports`.

## 15. Biên dịch hai explicit modules

Tạo source tree:

```text
src/
├── com.example.greeter/
│   ├── module-info.java
│   └── com/example/greeter/Greeter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Descriptor của thư viện:

```java
module com.example.greeter {
    exports com.example.greeter;
}
```

Descriptor của ứng dụng:

```java
module com.example.app {
    requires com.example.greeter;
}
```

Hai file Java `Greeter` và `Main` dùng cùng nội dung như ví dụ classpath. Biên dịch hai module cùng lúc:

```bash
javac --release 17 --module-source-path src -d out -m com.example.greeter,com.example.app
```

`--module-source-path` chỉ cấu trúc source của các module. `-m` liệt kê các module cần biên dịch. Output được tổ chức thành các thư mục `out/com.example.greeter` và `out/com.example.app`.

Chạy trực tiếp từ exploded modules:

```bash
java --module-path out -m com.example.app/com.example.app.Main
```

Stdout chính xác:

```text
Hello, JPMS!
```

Đóng mỗi module thành modular JAR:

```bash
jar --create --file mods/com.example.greeter.jar -C out/com.example.greeter .
jar --create --file mods/com.example.app.jar -C out/com.example.app .
java --module-path mods -m com.example.app/com.example.app.Main
```

Kết quả vẫn là `Hello, JPMS!`. Module path có thể chứa exploded modules hoặc modular JAR. Đường dẫn module cần được phân giải đúng và module name phải khớp directive `requires`.

## 16. Gradle và module path inference

Gradle Java Plugin hỗ trợ JPMS. Khi source set có `module-info.java` và dependency là module phù hợp, Gradle có thể tự đặt dependency lên module path thay vì classpath.

Có thể khai báo tường minh:

```groovy
plugins {
    id 'application'
}

java {
    modularity.inferModulePath = true
}

application {
    mainModule = 'com.example.app'
    mainClass = 'com.example.app.Main'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

File `src/main/java/module-info.java`:

```java
module com.example.app {
}
```

File `src/main/java/com/example/app/Main.java`:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Gradle module path: OK");
    }
}
```

Chạy bằng Gradle Wrapper:

```bash
./gradlew clean run
```

Stdout chính xác:

```text
Gradle module path: OK
```

Gradle Java Plugin bật module path inference theo mặc định ở các phiên bản hiện đại; khai báo rõ giúp người đọc build script thấy ý định của dự án. Có thể tắt bằng `modularity.inferModulePath = false` trong trường hợp tương thích đặc biệt, nhưng hãy cân nhắc ảnh hưởng đến module compilation và launch.

Gradle nhận diện module dựa trên `module-info.class` hoặc thuộc tính `Automatic-Module-Name` của JAR. Dependency không có module metadata có thể vẫn được đưa lên classpath. Khi ứng dụng là explicit module, dependency trên unnamed module có thể không đọc được; cần nâng cấp, tạo automatic module hoặc cấu hình bridge có chủ đích.

## 17. Đồng bộ module-info.java với Gradle dependencies

Khi dùng `java-library`, khai báo dependency trong Gradle và `module-info.java` cần phản ánh cùng một ý định.

| Directive trong module-info | Gradle configuration | Ý nghĩa |
|---|---|---|
| `requires` | `implementation` | Dependency phục vụ triển khai module |
| `requires transitive` | `api` | Consumer cũng cần đọc dependency |
| `requires static` | `compileOnly` | Cần khi compile, không nhất thiết khi runtime |
| `requires static transitive` | `compileOnlyApi` | Compile-time API dependency không cần ở runtime |

Ví dụ:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.example:internal-helper:1.4'
    api 'org.example:public-api:2.0'
}
```

```java
module com.example.library {
    requires org.example.internal.helper;
    requires transitive org.example.public.api;
}
```

Gradle hiện không tự xác nhận tất cả khai báo Gradle và module descriptor luôn đồng bộ. Review cả hai khi thêm hoặc đổi dependency. Nếu Gradle có dependency nhưng module descriptor thiếu `requires`, compile module có thể thất bại. Nếu module descriptor yêu cầu module nhưng Gradle không cung cấp nó trên module path, build cũng thất bại.

## 18. ServiceLoader trong module system

JPMS hỗ trợ khai báo service provider ngay trong descriptor:

```java
module com.example.api {
    exports com.example.api;
}
```

```java
module com.example.provider {
    requires com.example.api;
    provides com.example.api.GreetingService
        with com.example.provider.DefaultGreetingService;
}
```

Module sử dụng service khai báo:

```java
module com.example.app {
    requires com.example.api;
    uses com.example.api.GreetingService;
}
```

`uses` cho biết module cần service; `provides ... with ...` đăng ký implementation. Điều này giúp module resolver và ServiceLoader làm việc theo module graph, không cần dựa hoàn toàn vào file `META-INF/services` như cách classpath truyền thống.

Khi chuyển ứng dụng dùng ServiceLoader từ classpath sang module path, kiểm tra provider descriptor và cách framework đóng gói service. Một service không được khai báo đúng có thể không xuất hiện khi ứng dụng modular chạy.

## 19. Reflection, exports và opens

Framework dependency injection, JSON mapper, ORM và serialization library có thể cần reflection vào package của ứng dụng.

- `exports` công khai kiểu và thành viên public/protected của package cho module khác.
- `opens` cho phép deep reflection vào package ở runtime.
- `open module` mở tất cả package cho reflection nhưng không tự biến tất cả package thành API compile-time.

Ví dụ:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.json;
}
```

Nếu framework báo `InaccessibleObjectException`, kiểm tra package đã được mở cho đúng module chưa. Không mở toàn bộ module ngay lập tức nếu chỉ một package cần reflection.

Các cờ tương thích có thể giúp ứng dụng cũ:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar com.example.Main
```

`ALL-UNNAMED` áp dụng cho code trong unnamed modules, thường là code trên classpath. `--add-opens` là quyền reflection runtime; `--add-exports` điều chỉnh quyền truy cập package ở compile/runtime; `--add-reads` bổ sung quan hệ readability. Đây là biện pháp migration hoặc tích hợp có kiểm soát, không nên thay thế module descriptor đúng.

## 20. Công cụ chẩn đoán module

Các lệnh sau hữu ích khi build hoặc chạy module path:

```bash
jar --describe-module --file mods/com.example.greeter.jar
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
java --module-path mods --validate-modules
jdeps --print-module-deps app.jar
```

| Công cụ | Mục đích |
|---|---|
| `jar --describe-module` | Xem module name, exports và requires của JAR |
| `java --show-module-resolution` | In quá trình JVM phân giải module |
| `java --validate-modules` | Kiểm tra xung đột trong module path |
| `jdeps` | Phân tích dependency giữa class, package và module |
| `javac -verbose` | Xem thông tin compile và tìm kiếm class/module |

Dùng `jdeps` để tìm dependency trước migration, nhưng đọc và xác nhận kết quả trước khi viết `module-info.java`. Công cụ phân tích bytecode không thay thế hiểu biết về API public, reflection và service provider của ứng dụng.

## 21. Lỗi thường gặp

| Lỗi hoặc hiện tượng | Nguyên nhân | Cách kiểm tra |
|---|---|---|
| `ClassNotFoundException` | Thiếu JAR/thư mục trên classpath | Kiểm tra `-cp` và đường dẫn |
| `NoClassDefFoundError` | Dependency có lúc compile nhưng thiếu runtime | So sánh compile và runtime path |
| `FindException: Module not found` | Thiếu module hoặc sai tên module | Dùng `jar --describe-module` |
| `ResolutionException` | Module graph hoặc package bị xung đột | Dùng `--validate-modules` |
| `package ... is not visible` | Module không export package hoặc không readable | Kiểm tra `requires` và `exports` |
| `IllegalAccessError` | Runtime truy cập kiểu/package không được export | Kiểm tra descriptor và module path |
| `InaccessibleObjectException` | Reflection vào package chưa mở | Kiểm tra `opens` hoặc `--add-opens` |
| Không tìm thấy automatic module | Tên `requires` khác module name thực tế | Kiểm tra manifest và tên JAR |
| Split package | Nhiều module đóng góp cùng package | Tách package hoặc tái cấu trúc module |
| Gradle đặt JAR cũ trên classpath | JAR thiếu module descriptor và automatic name | Kiểm tra module path inference và metadata |
| ServiceLoader không tìm thấy provider | Thiếu `uses`/`provides` hoặc service metadata | Kiểm tra module descriptor |
| IDE chạy được, CI thất bại | IDE dùng classpath/module path khác build script | Chạy bằng Gradle Wrapper và JDK đã pin |

## 22. Lộ trình chuyển từ classpath sang module path

Không nên chuyển toàn bộ ứng dụng cùng một lúc nếu dependency graph phức tạp. Một lộ trình có kiểm soát:

1. **Kiểm kê:** ghi lại JDK, thư viện, plugin, framework, reflection và service provider đang dùng.
2. **Phân tích dependency:** dùng `jdeps` và kiểm tra manifest từng JAR.
3. **Chọn module boundary:** xác định package public và package nội bộ.
4. **Đặt module name:** ưu tiên tên ổn định; dùng `Automatic-Module-Name` cho thư viện đang chuyển tiếp.
5. **Tạo descriptor:** khai báo `requires`, `exports`, `opens`, `uses` và `provides` đúng nhu cầu.
6. **Chuyển dependency:** đưa explicit/automatic modules lên module path; xử lý JAR cũ còn trên classpath.
7. **Chạy test:** compile, unit test, integration test, reflection và ServiceLoader.
8. **Kiểm tra runtime:** xác nhận lệnh launcher, module resolution và môi trường CI.
9. **Thu hẹp bridge:** bỏ dần các cờ `--add-reads`, `--add-exports` và `--add-opens` khi đã sửa module boundary.
10. **Đóng gói:** nếu cần, dùng `jlink` để tạo runtime image từ module graph đã được kiểm soát.

Giữ module name ổn định qua các phiên bản. Thay đổi tên module là thay đổi ảnh hưởng consumer vì `requires` phụ thuộc vào tên đó.

## 23. Checklist quyết định

- [ ] Ứng dụng có cần ranh giới module và dependency graph tường minh không?
- [ ] Các thư viện có module descriptor hoặc `Automatic-Module-Name` không?
- [ ] Có package bị chia giữa nhiều JAR không?
- [ ] Có framework cần deep reflection không?
- [ ] Service provider đã được khai báo đúng chưa?
- [ ] Module name có ổn định và không phụ thuộc tên file JAR không?
- [ ] Gradle dependencies có khớp module descriptor không?
- [ ] Cả compile và runtime đều dùng đúng path không?
- [ ] CI dùng cùng JDK và Gradle Wrapper như môi trường phát triển không?
- [ ] Có thể bỏ các cờ mở quyền tạm sau migration không?

## 24. Tổng kết

Classpath là cơ chế truyền thống, dễ dùng và phù hợp với ứng dụng legacy hoặc dependency chưa modular. Module path bổ sung module graph, dependency rõ ràng và encapsulation theo package.

Hãy chọn classpath khi ứng dụng chưa cần module boundary và việc tương thích thư viện cũ là ưu tiên. Chọn module path khi muốn kiểm soát dependency, package exports, reflection và service integration ở cấp module. Khi chuyển đổi, hiểu rõ explicit module, automatic module và unnamed module; kiểm tra cả module descriptor lẫn cấu hình build.

**Tài liệu tham khảo chính thức:**

- [Oracle JDK 24 — javac command and module source path](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Oracle Java Language Specification — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html)
- [Oracle Java SE — ModuleDescriptor and automatic modules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [Oracle Java SE — Module and unnamed modules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html)
- [Gradle User Manual — Java Library Plugin and Java Module System](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle User Manual — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Oracle JDK Migration Guide — Strong Encapsulation](https://docs.oracle.com/en/java/javase/26/migrate/jdk-migration-guide.pdf)
