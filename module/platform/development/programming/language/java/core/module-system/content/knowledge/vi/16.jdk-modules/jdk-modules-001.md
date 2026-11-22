# java.base và các module nền tảng trong Java Module System

## 1. Mục tiêu bài học

Sau bài này, bạn sẽ hiểu:

- Vì sao `java.base` là module đặc biệt, luôn cần thiết cho mọi ứng dụng Java modular.
- Những API phổ biến nằm trong `java.base` và những API phải lấy từ các module Java SE khác.
- Mối liên hệ giữa các module `java.*`, những module `jdk.*`, module ứng dụng và quá trình **module resolution**.
- Khi nào phải khai báo `requires` trong `module-info.java`, cách xác định module chứa một package và cách đọc descriptor của module.
- Cách dùng `java --list-modules`, `java --describe-module`, `jdeps` và API `ModuleFinder` để khảo sát runtime hiện tại.
- Tác động của runtime image tạo bằng `jlink` đến các module có thể sử dụng khi triển khai.

Bài hướng tới Java 17 trở lên, đồng thời giải thích những nguyên tắc JPMS đã có từ Java 9. Danh sách module và API có thể thay đổi giữa các phiên bản JDK hoặc runtime image.

## 2. Java Platform Module System (JPMS) tổ chức thư viện chuẩn ra sao?

Trước Java 9, người học thường nghĩ về thư viện Java dưới dạng tập các package luôn nằm trên classpath. Từ Java 9, Java Platform Module System chia platform và JDK thành các **named module** với ranh giới rõ ràng. Mỗi named module có:

1. **Tên module** duy nhất trong một cấu hình, ví dụ `java.base` hoặc `java.logging`.
2. **Module descriptor** mô tả dependency bằng `requires`, package công khai bằng `exports`, package mở cho reflection qua `opens` và hợp đồng service.
3. **Tập package/classes/resources** được chứa trong module.

Các module của platform thường được đóng gói trong **runtime image** của Java. Khi chạy `java --list-modules`, bạn thấy các module mà runtime đó cung cấp; đây không nhất thiết là toàn bộ những module đã được đưa vào boot layer của một ứng dụng cụ thể.

Ví dụ tên module tiêu biểu:

| Module | Ví dụ tính năng / package |
| --- | --- |
| `java.base` | `java.lang`, `java.util`, `java.io`, `java.nio`, `java.time`, `java.net`, `java.security` |
| `java.logging` | `java.util.logging`, logging API chuẩn |
| `java.xml` | XML parsing, SAX, DOM, StAX |
| `java.sql` | JDBC API, `java.sql`, `javax.sql` |
| `java.net.http` | HTTP Client API, WebSocket client |
| `java.management` | JMX/management API |
| `java.naming` | JNDI |
| `java.desktop` | AWT, Swing, Java 2D và các API desktop liên quan |
| `java.compiler` | Java language model và công cụ compiler chuẩn |
| `java.scripting` | Scripting API `javax.script`; engine cụ thể phải được cung cấp riêng |
| `java.instrument` | API instrumentation và Java agent |
| `java.security.jgss` | API GSS-API và Kerberos liên quan |
| `jdk.compiler` | Triển khai compiler của JDK, gồm các công cụ tương ứng |
| `jdk.jfr` | Java Flight Recorder |
| `jdk.httpserver` | HTTP server nhẹ thuộc JDK |

Các module này là ví dụ, không phải danh mục đầy đủ. Nhóm `java.*` chủ yếu thể hiện API Java SE; nhóm `jdk.*` cung cấp những khả năng riêng của JDK. Một runtime image có thể lược bớt nhiều module kể trên.

## 3. Tại sao `java.base` đặc biệt?

`java.base` là nền móng của JPMS. Nó chứa các thành phần cốt lõi mà mọi chương trình Java cần để định nghĩa đối tượng, chạy luồng điều khiển, xử lý chuỗi, tập hợp, ngoại lệ và nhiều thao tác cơ bản khác.

Các tính chất quan trọng:

- **Mọi named module đều đọc `java.base` một cách ngầm định.** Bạn không cần thêm `requires java.base;` trong descriptor.
- **`java.base` không có dependency vào module platform khác.** Điều này tạo điểm bắt đầu ổn định cho đồ thị phụ thuộc module.
- **Một runtime Java hợp lệ phải có `java.base`.** Bạn không thể dùng `jlink` để tạo runtime Java vận hành được mà loại bỏ module này.
- **`java.base` không đồng nghĩa toàn bộ JDK.** JDBC, logging chuẩn, XML, HTTP Client hiện đại, desktop API... được đặt trong những module khác.
- **Không phải mọi package trong `java.base` đều được export.** Các package triển khai nội bộ có thể bị đóng gói mạnh; chỉ nên dùng API được hỗ trợ và export.

Ví dụ đoạn code chỉ sử dụng API thuộc `java.base`:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class BaseOnly {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh", "An");
        Map<Integer, List<String>> byLength = names.stream()
                .collect(Collectors.groupingBy(String::length));

        System.out.println(LocalDate.now());
        System.out.println(byLength);
    }
}
~~~

`LocalDate` thuộc `java.time`, `List` và `Map` thuộc `java.util`, Stream/Collectors thuộc `java.util.stream`: tất cả đều nằm trong `java.base`. Một ứng dụng modular sử dụng duy nhất những API này không cần khai báo `requires` cho module Java SE khác.

### 3.1. Các package nền tảng đáng nhớ

| Nhóm | Package trong `java.base` | Ví dụ |
| --- | --- | --- |
| Ngôn ngữ và hệ kiểu | `java.lang`, `java.lang.annotation`, `java.lang.reflect` | `String`, `Object`, `Thread`, `Record`, reflection API |
| Invoke động | `java.lang.invoke` | `MethodHandle`, `MethodHandles` |
| Collection và tiện ích | `java.util`, `java.util.stream`, `java.util.function` | `List`, `Map`, `Optional`, Stream |
| Đồng thời | `java.util.concurrent`, `java.util.concurrent.atomic` | `ExecutorService`, `CompletableFuture`, atomics |
| Dữ liệu vào/ra | `java.io`, `java.nio`, `java.nio.file` | `InputStream`, `Path`, `Files` |
| Mạng cơ bản | `java.net` | `URI`, `URL`, `Socket` |
| Ngày giờ | `java.time`, `java.time.format` | `Instant`, `LocalDateTime`, `DateTimeFormatter` |
| Toán học, văn bản | `java.math`, `java.text` | `BigDecimal`, `NumberFormat` |
| Bảo mật | `java.security`, `javax.crypto`, `javax.net.ssl` | `MessageDigest`, `Cipher`, TLS API |
| Module metadata | `java.lang.module` | `ModuleFinder`, `ModuleDescriptor` |

Hai tên package dễ nhầm:

- `java.net` ở `java.base` chứa mạng cơ bản. `java.net.http` nằm ở module **`java.net.http`**, vì vậy named module muốn dùng `HttpClient` phải khai báo `requires java.net.http;`.
- `java.util` ở `java.base`, nhưng `java.util.logging` thuộc **`java.logging`**. Chỉ import `java.util.logging.Logger` không làm module ứng dụng tự động có quyền đọc `java.logging`.

Một package có tên gần giống hoặc có chung tiền tố không có nghĩa nó thuộc cùng module. JPMS quản lý theo module descriptor thực tế.

## 4. Từ `java.base` đến các module Java SE khác

Để giảm mức phụ thuộc của một ứng dụng, hãy xem các module chuẩn như các thành phần chức năng chỉ bổ sung khi cần.

### 4.1. `java.logging`: logging chuẩn

Module này cung cấp API Java Util Logging (JUL). Ví dụ:

~~~java
import java.util.logging.Logger;

public class LogDemo {
    private static final Logger LOG =
            Logger.getLogger(LogDemo.class.getName());

    public static void main(String[] args) {
        LOG.info("Ung dung da khoi dong");
    }
}
~~~

Trong **unnamed module** hoặc chương trình classpath đơn giản, người dùng thường không phải viết `module-info.java`. Nhưng nếu `LogDemo` nằm trong named module `com.example.app`, descriptor phải nêu rõ:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

`java.base` vẫn được đọc ngầm định. Ngược lại, quyền đọc `java.logging` không tự nhiên phát sinh chỉ vì class dùng `java.lang` hay `java.util`.

### 4.2. `java.sql` và `java.xml`

Các ứng dụng cần JDBC API thường khai báo:

~~~java
module com.example.database {
    requires java.sql;
}
~~~

Ứng dụng xử lý DOM/SAX/XML chuẩn có thể khai báo:

~~~java
module com.example.xml {
    requires java.xml;
}
~~~

Phụ thuộc của các module này được JPMS xử lý qua module resolution. Nếu một module có `requires transitive` thì quan hệ đọc có thể được lan truyền theo hợp đồng descriptor. Hãy kiểm tra descriptor thực tế bằng `java --describe-module java.sql` thay vì giả định toàn bộ dependency luôn giống nhau ở mọi phiên bản Java.

### 4.3. `java.net.http`: HTTP Client từ Java 11

HTTP Client API chuẩn hiện đại thuộc `java.net.http`, không nằm trong `java.base`:

~~~java
module com.example.client {
    requires java.net.http;
}
~~~

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;

public class ClientDemo {
    public static void main(String[] args) {
        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://example.com"))
                    .GET()
                    .build();
            System.out.println(request.uri());
        }
    }
}
~~~

**Lưu ý về phiên bản:** `HttpClient` chỉ triển khai `AutoCloseable` ở những phiên bản Java mới hơn; ví dụ `try-with-resources` phía trên chỉ phù hợp Java 21 trở lên. Với Java 17, tạo client thông thường như sau:

~~~java
HttpClient client = HttpClient.newHttpClient();
~~~

Đối với module `java.net.http`, API đã được chuẩn hóa từ Java 11. Dùng cú pháp và API phù hợp với phiên bản Java mà dự án thực thi.

### 4.4. `java.desktop` và `java.management`

Ứng dụng Swing/AWT hoặc quản lý qua JMX cần các module tương ứng:

~~~java
module com.example.desktoptool {
    requires java.desktop;
    requires java.management;
}
~~~

Đưa `java.desktop` vào một ứng dụng phía server có thể làm tăng kích thước runtime image. Khi tạo runtime tối giản, nên chỉ đưa vào các module mà ứng dụng thực sự cần.

## 5. Phân biệt module Java SE và module riêng của JDK

Một bản phân phối JDK có thể cung cấp cả:

- Module **`java.*`**: nhiều module mô tả API Java SE được chuẩn hóa.
- Module **`jdk.*`**: cung cấp công cụ hoặc khả năng đặc thù JDK, chẳng hạn compiler, Java Flight Recorder, HTTP server nhẹ, hoặc các module triển khai.

Không suy luận rằng mọi package trong module `jdk.*` là API public ổn định. Dù module có thể được tìm thấy, một package không được `exports` vẫn không thể import bình thường từ module khác.

Ví dụ, `jdk.compiler` cung cấp các package dành cho các thành phần compiler, nhưng không cho phép mặc định việc truy cập mọi class trong `com.sun.tools.javac.*`. Có thể kiểm tra phần công khai bằng:

~~~bash
java --describe-module jdk.compiler
~~~

Một số runtime có module tổng hợp `java.se`. Đây là **aggregator module** với các phụ thuộc transitive tới các module Java SE thích hợp, không phải nơi chứa toàn bộ các class trong Java SE và cũng không phải tên thay thế của `java.base`. Khi cần kiểm soát dependency rõ ràng, nên khai báo module thực sự được sử dụng thay vì mặc định dựa vào một aggregate module.

## 6. Đọc `module-info.java` và quyền truy cập module

### 6.1. `requires` là gì?

`module-info.java` là nguồn khai báo descriptor của named module. Ví dụ:

~~~java
module com.example.foundation {
    requires java.logging;
    requires java.net.http;
}
~~~

Quan hệ đọc được hình thành nhờ `requires` và các quy tắc module khác. Riêng `java.base` được đọc tự động:

~~~text
com.example.foundation
   +-- java.base         (ngam dinh)
   +-- java.logging      (requires truc tiep)
   +-- java.net.http     (requires truc tiep)
         +-- ...         (dependency theo descriptor)
~~~

**Tìm được module chưa đủ để truy cập API**. Để module A dùng một public type của module B, module A cần đọc B và package chứa type phải được B export theo phạm vi phù hợp.

### 6.2. `exports` và `opens` khác gì?

- `exports com.example.api;` công khai public types trong package cho code ở module khác ở cả thời điểm biên dịch và thời điểm chạy theo quy tắc truy cập.
- `exports com.example.internal to com.example.friend;` chỉ export package cho các module được chỉ định.
- `opens com.example.model;` cho phép reflection sâu tới package tại runtime; không có ý nghĩa là mọi public type trong package tự động trở thành API import được từ module khác.
- `open module com.example.app { ... }` mở toàn bộ package trong module cho reflection sâu theo mô hình module mở, nhưng cần cân nhắc tính đóng gói.

`java.base` export nhiều API cơ bản nhưng cũng chứa package nội bộ không export. Việc dùng `--add-exports` hay `--add-opens` để vượt qua ranh giới module nên là trường hợp đặc biệt có lý do tương thích cụ thể, không phải quy tắc mặc định.

### 6.3. `requires transitive` và `requires static`

Một thư viện có thể dùng:

~~~java
module com.example.facade {
    requires transitive java.logging;
}
~~~

Module khác khai báo `requires com.example.facade;` sẽ được hưởng quan hệ đọc tới `java.logging` theo quy tắc `requires transitive`.

`requires static module.name;` chỉ bắt buộc dependency khi biên dịch; tại runtime dependency ấy có thể không có. Nếu code thực sự gọi API tùy chọn thì chương trình vẫn cần thiết kế đường chạy phù hợp khi dependency vắng mặt.

## 7. Ví dụ hoàn chỉnh: ứng dụng modular dùng `java.base` và `java.logging`

Tạo cấu trúc thư mục:

~~~text
src/
  com.example.foundation/
    module-info.java
    com/
      example/
        foundation/
          Main.java
mods/
  (thu muc sinh sau khi bien dich)
~~~

File `src/com.example.foundation/module-info.java`:

~~~java
module com.example.foundation {
    requires java.logging;
}
~~~

File `src/com.example.foundation/com/example/foundation/Main.java`:

~~~java
package com.example.foundation;

import java.time.LocalDate;
import java.util.List;
import java.util.logging.Logger;

public class Main {
    private static final Logger LOG = Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        List<String> messages = List.of("java.base", "java.logging");
        LOG.info("Running with " + messages);

        System.out.println("Today: " + LocalDate.now());
        System.out.println("Current module: " + Main.class.getModule().getName());

        Module ownModule = Main.class.getModule();
        Module base = Object.class.getModule();
        Module logging = Logger.class.getModule();

        System.out.println("Base module: " + base.getName());
        System.out.println("Logging module: " + logging.getName());
        System.out.println("Reads java.base: " + ownModule.canRead(base));
        System.out.println("Reads java.logging: " + ownModule.canRead(logging));
    }
}
~~~

Biên dịch từ thư mục dự án:

~~~bash
javac -d mods/com.example.foundation src/com.example.foundation/module-info.java src/com.example.foundation/com/example/foundation/Main.java
~~~

Khởi chạy:

~~~bash
java --module-path mods --module com.example.foundation/com.example.foundation.Main
~~~

Ví dụ đầu ra (không cố định ngày, vị trí logger hay cách trình bày):

~~~text
... INFO: Running with [java.base, java.logging]
Today: 2026-11-11
Current module: com.example.foundation
Base module: java.base
Logging module: java.logging
Reads java.base: true
Reads java.logging: true
~~~

`LocalDate`, `List`, `Object` và `Module` đều có trong `java.base`; `Logger` có trong `java.logging`. Vì thế descriptor chỉ cần `requires java.logging;`.

Nếu xóa dòng `requires java.logging;` rồi biên dịch lại, compiler sẽ báo package `java.util.logging` không visible đối với named module do thiếu quan hệ đọc. Thêm dependency đúng vào descriptor là cách sửa cơ bản.

Chạy lại để xem resolution:

~~~bash
java --show-module-resolution --module-path mods --module com.example.foundation/com.example.foundation.Main
~~~

Những dòng `root ...`, `requires ...` và những quan hệ khác giúp hình dung cách JVM chọn module; chi tiết đầu ra còn phụ thuộc các lựa chọn khởi chạy và phiên bản JDK.

## 8. Khảo sát module trực tiếp bằng công cụ JDK

### 8.1. Các lệnh thường dùng

~~~bash
java -version
java --list-modules
java --describe-module java.base
java --describe-module java.logging
java --describe-module java.net.http
java --describe-module jdk.compiler
~~~

Mỗi lệnh trả lời một câu hỏi:

| Lệnh | Tìm hiểu điều gì? |
| --- | --- |
| `java -version` | Đang chạy đúng Java version/runtime nào? |
| `java --list-modules` | Runtime image hiện tại cung cấp những module nào? |
| `java --describe-module X` | Descriptor của module `X` có những `requires`, `exports`, `uses` và `provides` nào? |
| `java --show-module-resolution ...` | JVM đã chọn những module/quan hệ nào khi chạy ứng dụng? |
| `jdeps --print-module-deps app.jar` | Phụ thuộc module được suy ra từ phân tích bytecode của JAR. |

Ở kết quả `--list-modules`, module thường được in theo dạng `module.name@version`. Phiên bản có thể khác hoặc không xuất hiện trong vài hoàn cảnh. Không mã hóa cứng phiên bản cụ thể vào ứng dụng.

### 8.2. Xác định module chứa một class

Từ Java code:

~~~java
import java.net.http.HttpClient;
import java.time.Instant;
import java.util.logging.Logger;

public class WhereIsMyClass {
    public static void main(String[] args) {
        System.out.println(String.class.getModule().getName());
        System.out.println(Instant.class.getModule().getName());
        System.out.println(Logger.class.getModule().getName());
        System.out.println(HttpClient.class.getModule().getName());
    }
}
~~~

Chạy trên classpath với Java 17+:

~~~bash
javac WhereIsMyClass.java
java WhereIsMyClass
~~~

Kết quả:

~~~text
java.base
java.base
java.logging
java.net.http
~~~

Cách này rất hữu ích khi bạn phân vân một class thuộc module nào. Nó kiểm tra module của type trong runtime mà chương trình đã thực sự load, không thay thế việc đọc descriptor để biết package có được export hay không.

### 8.3. Liệt kê bằng API `ModuleFinder.ofSystem()`

Ngoài CLI, Java cung cấp API module tại `java.lang.module` trong `java.base`:

~~~java
import java.lang.module.ModuleFinder;
import java.util.Comparator;

public class PlatformModules {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.ofSystem();

        finder.findAll().stream()
                .sorted(Comparator.comparing(ref -> ref.descriptor().name()))
                .forEach(ref -> {
                    String name = ref.descriptor().name();
                    String location = ref.location()
                            .map(Object::toString)
                            .orElse("(unknown)");
                    System.out.println(name + " -> " + location);
                });

        System.out.println("java.base available: "
                + finder.find("java.base").isPresent());
    }
}
~~~

Ví dụ URI của một system module có dạng `jrt:/java.base`. `jrt:/` là hệ thống URI dành cho nội dung runtime image và không cần đồng nhất với một file JAR trên đĩa.

**Phân biệt ba lớp thông tin:**

- `ModuleFinder.ofSystem().findAll()`: những module runtime cung cấp cho finder.
- `ModuleLayer.boot().configuration()`: đồ thị module được resolve cho boot layer.
- `ModuleLayer.boot().modules()`: những module thực tế được định nghĩa trong boot layer.

Việc một module xuất hiện trong finder không chứng tỏ nó đã được chọn vào boot layer của ứng dụng.

### 8.4. In descriptor bằng API

~~~java
import java.lang.module.ModuleFinder;

public class BaseDescriptor {
    public static void main(String[] args) {
        var base = ModuleFinder.ofSystem().find("java.base")
                .orElseThrow()
                .descriptor();

        System.out.println("Module: " + base.name());
        System.out.println("Requires: " + base.requires());
        System.out.println("Exported package count: " + base.exports().size());

        base.exports().stream()
                .map(export -> export.source())
                .sorted()
                .forEach(System.out::println);
    }
}
~~~

Đoạn code đọc metadata thay vì tự giữ danh sách package từ một bản JDK cũ. Thông thường `java.base` không phụ thuộc module khác; các module còn lại được mô tả qua quan hệ module resolution.

## 9. Khi nào hệ thống tự resolve các module nền tảng?

Mỗi lần khởi chạy modular application, JVM xác định **root modules** và dùng resolver truy tìm các module phụ thuộc. Quy trình khái quát:

~~~text
Root: com.example.foundation
             |
             | requires java.logging
             v
       java.logging
             |
             +-----> java.base (nen tang)
             ^
             |
com.example.foundation --(implicit read)--> java.base
~~~

Đồ thị trên chỉ thể hiện phần dependency cần để hiểu ví dụ. Mỗi runtime có thể có những chi tiết resolution bổ sung.

Có hai lưu ý quan trọng:

1. `java.base` luôn là module nền; đối với named module, quan hệ đọc tới `java.base` là tự động dù `module-info.java` không ghi ra.
2. **Observable module** chưa chắc đã được resolve. Thông tin `java --list-modules` cho thấy nguồn system modules, còn `--show-module-resolution` giúp quan sát những module được chọn khi chạy một ứng dụng cụ thể.

Nếu module cần thiết không có trong nguồn quan sát được, JVM có thể báo lỗi dạng:

~~~text
java.lang.module.FindException: Module java.logging not found, required by com.example.foundation
~~~

Điều này thường xuất hiện ở runtime image quá tối giản hoặc khi cấu hình module path không chứa module ứng dụng cần dùng. Cần kiểm tra bằng executable Java thực sự được dùng để khởi chạy.

## 10. Runtime image tối giản và ý nghĩa của `java.base`

`jlink` (có trong JDK) tạo runtime image tùy chỉnh từ các module được lựa chọn và các dependency cần thiết.

Ví dụ trên hệ thống có JDK đầy đủ, sử dụng một thư mục đầu ra chưa tồn tại:

~~~bash
jlink --module-path /path/to/jdk/jmods --add-modules java.base,java.logging --output runtime-small
~~~

Trên Linux/macOS có thể thay `/path/to/jdk/jmods` bằng đường dẫn `$JAVA_HOME/jmods` khi biến môi trường đã được thiết lập đúng. Trên Windows dùng đường dẫn tới thư mục `jmods` của bản JDK thực tế, ví dụ `C:\Java\jdk-17\jmods`.

Kiểm tra:

~~~bash
runtime-small/bin/java --list-modules
~~~

Trên Windows thường gọi `runtime-small\bin\java.exe --list-modules`.

Runtime image được tạo sẽ có `java.base`, `java.logging` và những phần phụ thuộc mà `jlink` cần đóng gói. Nhiều module khác của JDK đầy đủ có thể không hiện diện.

Tác động thực tế:

- Không thể bỏ `java.base`, vì nó là nền tảng của runtime.
- Nếu ứng dụng sử dụng `java.net.http`, `java.sql` hoặc `java.desktop`, image phải có các module tương ứng.
- Bản JDK khi build và image khi deploy có thể khác nhau. Việc compile được trên JDK đầy đủ không bảo đảm runtime tối giản đủ module.
- Dùng `jdeps` để gợi ý dependency tĩnh, đồng thời kiểm tra thêm reflection, service loading và những đường gọi được quyết định động.

Lệnh ví dụ phân tích modular JAR:

~~~bash
jdeps --print-module-deps my-app.jar
~~~

`jdeps` chỉ có thể phân tích những thông tin xuất hiện trong bytecode và cấu hình được cung cấp; nó không thể suy ra hoàn hảo mọi dependency động của ứng dụng.

## 11. Những nhầm lẫn thường gặp

### Nhầm 1: “`java.base` chứa toàn bộ thư viện chuẩn”

Không đúng. `java.base` chứa một lượng lớn API cốt lõi, nhưng logging, JDBC, XML, management, desktop, HTTP Client hiện đại và nhiều khả năng khác ở module riêng. Khi viết `module-info.java`, cần xác định chính xác module chứa package đang sử dụng.

### Nhầm 2: “Thấy `java.util.logging` thì nó nằm trong `java.base`”

Package có tiền tố `java.util` chưa đủ để quyết định module. `java.util.logging` thuộc `java.logging`, còn `java.util.concurrent` ở `java.base`. Dùng `Class.getModule()` hoặc descriptor để xác minh.

### Nhầm 3: “Mọi module trong `java --list-modules` đều đã được load”

`--list-modules` cho thấy module runtime có, còn những module đã được resolve phụ thuộc roots, dependencies và tùy chọn runtime. Để quan sát graph, dùng `--show-module-resolution` hoặc kiểm tra boot layer.

### Nhầm 4: “Một module trong runtime thì package của nó luôn import được”

Có mặt trong runtime là điều kiện cần nhưng chưa đủ. Module ứng dụng phải có **readability** phù hợp và package đích phải được export; reflection sâu có thể cần `opens`. Những package nội bộ kiểu `jdk.internal.*` không nên được xem là API công khai chỉ vì JVM sử dụng chúng.

### Nhầm 5: “Module riêng của JDK đều xuất hiện trong mọi Java runtime”

Một image sinh bằng `jlink` có thể loại bỏ nhiều module `jdk.*` và thậm chí những module `java.*` không cần. Hãy đối chiếu runtime triển khai với module dependencies của ứng dụng.

### Nhầm 6: “`java.se` là một bản sao lớn hơn của `java.base`”

`java.se` là aggregate module trên các runtime có cung cấp nó; nó dùng dependency để gom các module Java SE, không phải nơi lưu trữ tất cả class. `java.base` là module nền tảng độc lập với nhiệm vụ khác.

### Nhầm 7: “Khai báo `requires` thay thế mọi cấu hình runtime”

`requires` diễn đạt quan hệ module cần thiết nhưng không tự tạo ra module còn thiếu trong một runtime image, không thay thế `--module-path`, và không giải quyết các trường hợp phải mở package để reflection.

## 12. Bài thực hành

**Bài 1 — Xác định module theo class.** In tên module của `Object`, `Path`, `Logger`, `HttpClient`, `DocumentBuilderFactory` và `Connection` bằng `SomeClass.class.getModule().getName()`. Nhóm những class thuộc `java.base` và ngoài `java.base`. Nếu cần import, xác định module tương ứng.

**Bài 2 — Mô tả `java.base`.** Chạy `java --describe-module java.base` và trả lời: module này có bao nhiêu `exports`? Nó có khai báo `requires` tới module khác không? Một package nội bộ không xuất hiện trong danh sách `exports` có thể được mã ứng dụng import bình thường không?

**Bài 3 — Thiết kế descriptor.** Cho một ứng dụng dùng `LocalDate`, `List`, `Logger`, `HttpClient` và JDBC `Connection`, hãy viết `module-info.java` tối thiểu chỉ dựa trên những module chứa các API này. Giải thích tại sao không cần `requires java.base;`.

**Bài 4 — Quan sát module resolution.** Chạy ví dụ `com.example.foundation` trong mục 7 cùng `--show-module-resolution`. Chỉ ra root module, module được yêu cầu trực tiếp và sự hiện diện của `java.base`.

**Bài 5 — So sánh runtime.** Chạy `java --list-modules` trên JDK đầy đủ và runtime image `runtime-small` được tạo bằng `jlink`. Giải thích vì sao kết quả khác nhau và tại sao `java.base` vẫn xuất hiện ở cả hai.

**Bài 6 — Kiểm tra ranh giới module.** Thử loại bỏ `requires java.logging;` trong ví dụ rồi chạy lại `javac`. Đọc thông báo compiler và đưa dependency về đúng vị trí trong `module-info.java`.

Ghi lại phiên bản Java và lệnh thực thi khi làm bài. Kết quả danh sách module có thể khác nhau giữa các máy và bản phân phối JDK.

## 13. Tổng kết

- `java.base` là module cốt lõi của JPMS và được mọi named module đọc ngầm định.
- Không phải API Java SE nào cũng ở `java.base`. Các tính năng như logging, JDBC, HTTP Client, XML, desktop và management nằm trong các module chức năng.
- `module-info.java` dùng `requires` cho dependency ngoài `java.base`; quyền sử dụng public API còn phụ thuộc `exports` và quan hệ đọc.
- `java --list-modules` và `ModuleFinder.ofSystem()` quan sát module runtime cung cấp; `--show-module-resolution` và `ModuleLayer.boot()` hỗ trợ quan sát các module được chọn cho quá trình chạy.
- `jlink` cho phép tối giản runtime theo module nhưng không thể lược bỏ `java.base`.
- Luôn kiểm tra module trên đúng phiên bản và runtime image, tránh giả định một JDK đầy đủ và runtime triển khai có danh sách module giống nhau.

## 14. Tài liệu tham khảo

- Java Language Specification, phần Modules và Module Declarations.
- Java Platform Module System — JEP 261.
- Java SE API: `java.lang.Module`, `java.lang.ModuleLayer`, `java.lang.module.ModuleDescriptor`, `java.lang.module.ModuleFinder`.
- JDK Tools Reference: `java`, `javac`, `jdeps`, `jlink` của phiên bản Java đang sử dụng.
