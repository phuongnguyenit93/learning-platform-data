# Resource lookup trong modular class (Java JPMS)

## 1. Mục tiêu và bối cảnh

Từ Java 9, Java Platform Module System (JPMS) cho phép ứng dụng tổ chức mã thành các **named module** được khai báo bằng `module-info.java`. Khi chuyển từ classpath sang module path, cách tìm file cấu hình, template, văn bản, JSON hoặc các resource đóng gói cùng ứng dụng có thể thay đổi.

Sau bài này, bạn có thể:

- Xác định chính xác tên resource và vị trí của nó trong JAR/module.
- Chọn đúng giữa `Class.getResource(...)`, `Class.getResourceAsStream(...)`, `Module.getResourceAsStream(...)` và `ClassLoader.getResource(...)`.
- Hiểu vì sao cùng một resource đọc được từ lớp trong module nhưng trả về `null` khi tra qua class loader hoặc từ module khác.
- Dùng `opens` đúng trường hợp; phân biệt `opens` với `exports`.
- Đọc resource an toàn khi chạy từ IDE, JAR hoặc module path mà không phụ thuộc đường dẫn trên máy.

**Phạm vi:** “Resource” ở đây là tệp được đóng gói trong output/JAR và tra cứu bằng tên logic, chẳng hạn `com/example/app/app.properties`. Nó không đồng nghĩa với một tệp vật lý có thể mở trực tiếp bằng `Path`.

## 2. Tên resource và các API cần nhớ

Giả sử cấu trúc trong artifact đã đóng gói là:

~~~text
module-info.class
com/example/app/App.class
com/example/app/app.properties
com/example/app/templates/welcome.txt
config/global.json
~~~

Tên của resource dùng dấu gạch chéo `/` làm dấu phân cách, kể cả khi chương trình chạy trên Windows. Không đưa `src/main/resources` hoặc đường dẫn tuyệt đối trên máy vào tên tra cứu.

| API | Cách diễn giải tên | Phù hợp khi |
| --- | --- | --- |
| `App.class.getResource("app.properties")` | Tương đối với package `com.example.app`; trả về `URL` hoặc `null` | Cần URL của resource đi cùng lớp |
| `App.class.getResourceAsStream("app.properties")` | Tương đối với package `com.example.app`; trả về `InputStream` hoặc `null` | Đọc nội dung resource của module chứa lớp |
| `App.class.getResourceAsStream("/config/global.json")` | Dấu `/` đầu tiên chỉ gốc module/classpath | Resource không nằm cùng package |
| `App.class.getModule().getResourceAsStream("com/example/app/app.properties")` | Tên đầy đủ tính từ gốc module, **không** thêm `/` ở đầu | Muốn chọn chính xác module sở hữu resource |
| `App.class.getClassLoader().getResource("com/example/app/app.properties")` | Tên tính từ gốc đường tìm kiếm của loader, **không** thêm `/` ở đầu | Tra cứu theo class loader khi biết rõ giới hạn hiển thị |

Đối với `Class.getResource*`, tên bắt đầu bằng `/` là tên tuyệt đối; tên không bắt đầu bằng `/` được ghép với package của lớp làm mốc. Còn `ClassLoader.getResource*` và `Module.getResourceAsStream` nhận tên logic từ gốc, không dùng dấu `/` mở đầu.

Ví dụ, các lời gọi sau nhắm đến cùng một resource:

~~~java
App.class.getResourceAsStream("app.properties");
App.class.getResourceAsStream("/com/example/app/app.properties");
App.class.getModule().getResourceAsStream(
    "com/example/app/app.properties"
);
~~~

Chúng không hoàn toàn thay thế nhau trong mọi tình huống: mỗi API có ngữ cảnh chọn module và quy tắc truy cập riêng, đặc biệt khi resource nằm trong named module.

## 3. Ví dụ đầy đủ: đọc cấu hình ngay trong named module

Dưới đây là cấu trúc dự án Java 11+ dùng layout Maven/Gradle thông dụng:

~~~text
src/
  main/
    java/
      module-info.java
      com/example/app/App.java
    resources/
      com/example/app/app.properties
~~~

File `src/main/java/module-info.java`:

~~~java
module com.example.app {
}
~~~

File `src/main/resources/com/example/app/app.properties`:

~~~properties
app.name=ModularResourceDemo
app.mode=production
~~~

File `src/main/java/com/example/app/App.java`:

~~~java
package com.example.app;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        Properties settings = loadSettings();
        System.out.println(settings.getProperty("app.name"));
        System.out.println(settings.getProperty("app.mode"));
    }

    public static Properties loadSettings() throws IOException {
        Properties settings = new Properties();

        try (InputStream in =
                 App.class.getResourceAsStream("app.properties")) {
            if (in == null) {
                throw new IOException(
                    "Thiếu resource com/example/app/app.properties"
                );
            }

            settings.load(
                new InputStreamReader(in, StandardCharsets.UTF_8)
            );
        }

        return settings;
    }
}
~~~

Kết quả mong đợi:

~~~text
ModularResourceDemo
production
~~~

**Vì sao cách này hoạt động?** `App.class` nằm trong `com.example.app` và thuộc module `com.example.app`. Tên tương đối `app.properties` được giải thành `com/example/app/app.properties`. Resource nằm cùng module với mã đang đọc; không cần `exports` hay `opens` chỉ để đọc nội bộ theo cách này.

Khi dùng Maven/Gradle với cấu hình mặc định, tệp trong `src/main/resources` được đưa vào classpath/output của bộ build, rồi có thể đóng gói trong JAR. Với cách build thủ công bằng `javac`, bạn phải tự copy tệp resource vào đúng vị trí trong output vì `javac` không tự đóng gói resource.

Lưu ý: `Properties.load(InputStream)` theo quy tắc riêng của định dạng properties, không mặc định diễn giải mọi byte theo UTF-8. Ví dụ dùng `InputStreamReader` với `StandardCharsets.UTF_8` để chủ động quy định mã hóa.

## 4. Quy tắc đóng gói và truy cập của JPMS

Một nguyên nhân hay gặp của `null` là **encapsulation**: JPMS có thể ẩn resource trong package của named module đối với mã ở module khác hoặc thao tác tìm qua class loader.

Cần phân biệt:

- `exports com.example.lib;` công khai **public types** của package cho module khác tại thời điểm biên dịch và chạy; nó không tự mở resource của package cho mọi API tra cứu.
- `opens com.example.lib;` mở package cho mọi module tại thời điểm chạy, phục vụ cả deep reflection và các quy tắc tìm resource liên quan.
- `opens com.example.lib to com.example.consumer;` mở có điều kiện cho module được chỉ định.
- `open module com.example.lib { ... }` mở toàn bộ package của module; chỉ nên dùng nếu chủ ý cần mức truy cập rộng đó.

Một cách nhìn thực dụng:

| Ngữ cảnh tìm resource trong package của named module | Hành vi cần ghi nhớ |
| --- | --- |
| Lớp trong chính module gọi `Class.getResourceAsStream` | Có thể tìm resource nội bộ theo tên đúng; không cần mở package cho bên ngoài |
| Mã ở module khác gọi `targetModule.getResourceAsStream` | Package chứa resource phải mở cho module đang gọi |
| `ClassLoader.getResource` / `getResourceAsStream` tìm qua loader | Với resource thông thường nằm trong package của named module, package phải được **mở vô điều kiện** |
| Chỉ có `exports`, không có `opens` | Không đủ để bảo đảm tìm thấy resource qua loader hoặc từ module khác |

Chi tiết quan trọng: tài liệu Java có ngoại lệ cho tên resource kết thúc bằng `.class` trong quy tắc encapsulation. Không nên suy diễn từ việc tra cứu được `Foo.class` rằng mọi tệp `.properties`, `.json` hay template trong cùng package đều được công khai.

**Qualified opens không tương đương unconditional opens.** Ví dụ `opens com.example.assets to com.example.consumer;` có thể cho phép mã của module `com.example.consumer` dùng `Module.getResourceAsStream`, nhưng không khiến tìm kiếm toàn cục bằng `ClassLoader.getResource` nhìn thấy resource trong package đó như với `opens com.example.assets;`.

## 5. Ví dụ đọc resource của một module khác

Giả sử ứng dụng có hai named module, `com.example.assets` và `com.example.consumer`. Module assets có một Java class trong package `com.example.assets` và tệp `colors.json` được đóng gói cùng package.

Cấu trúc phần liên quan:

~~~text
com.example.assets
  module-info.java
  com/example/assets/Anchor.java
  com/example/assets/colors.json

com.example.consumer
  module-info.java
  com/example/consumer/Consumer.java
~~~

`module-info.java` của assets:

~~~java
module com.example.assets {
    opens com.example.assets to com.example.consumer;
}
~~~

`module-info.java` của consumer:

~~~java
module com.example.consumer {
    requires com.example.assets;
}
~~~

Trong `Consumer.java`:

~~~java
package com.example.consumer;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Consumer {
    public static void main(String[] args) throws IOException {
        Module assets = ModuleLayer.boot()
            .findModule("com.example.assets")
            .orElseThrow(() -> new IllegalStateException(
                "Module com.example.assets chưa được resolve"
            ));

        try (InputStream in = assets.getResourceAsStream(
                "com/example/assets/colors.json")) {
            if (in == null) {
                throw new IOException("Không thể đọc colors.json");
            }

            String json = new String(
                in.readAllBytes(), StandardCharsets.UTF_8
            );
            System.out.println(json);
        }
    }
}
~~~

Điều kiện cần thỏa mãn:

1. `com.example.assets` nằm trong module graph đã resolve; ở ví dụ trên, `requires com.example.assets;` bảo đảm quan hệ module.
2. `colors.json` thực sự được đóng gói dưới `com/example/assets/`.
3. Package `com.example.assets` được mở cho module `com.example.consumer`; lời gọi `Module.getResourceAsStream` xét module của mã gọi.
4. Tên truyền vào `Module.getResourceAsStream` là tên từ gốc module và **không** bắt đầu bằng `/`.

Nếu cần cho nhiều module bất kỳ truy cập resource này, có thể dùng `opens com.example.assets;`. Nếu chỉ cần một consumer cụ thể, `opens ... to ...` thường diễn đạt ý đồ rõ hơn.

Khi resource chỉ phục vụ nội bộ module assets, lựa chọn tốt hơn là để chính assets cung cấp một API đọc nội bộ và trả về dữ liệu đã xử lý; consumer không cần biết vị trí resource trong JAR.

## 6. Vì sao ClassLoader.getResource có thể trả về null?

Ví dụ:

~~~java
ClassLoader loader = App.class.getClassLoader();

var fromClass = App.class.getResource(
    "/com/example/app/app.properties"
);

var fromLoader = loader.getResource(
    "com/example/app/app.properties"
);
~~~

Trong named module có package chưa `opens` vô điều kiện, `fromClass` có thể tìm được resource nội bộ trong khi `fromLoader` trả về `null`. Đây là khác biệt về quy tắc truy cập, không nhất thiết là lỗi đường dẫn hoặc lỗi build.

Thêm hai điểm cần chú ý:

- Class loader có thể phục vụ nhiều module; tra cứu theo tên qua loader không phải cách chọn module sở hữu một resource một cách chính xác. Với tên có thể trùng, hãy lấy `Class` hoặc `Module` của thành phần bạn thực sự muốn đọc.
- `Thread.currentThread().getContextClassLoader()` phù hợp với một số framework/cơ chế plugin, nhưng không tự vượt qua encapsulation của JPMS. Đừng tùy tiện thay `App.class.getResourceAsStream` bằng context loader khi chuyển ứng dụng sang module path.

`ClassLoader` của một số lớp nền tảng có thể là `null` (bootstrap loader). Nếu cần API loader, phải xử lý trường hợp này; trong mã ứng dụng modular thông thường, cách dựa trên `Class` hoặc `Module` vẫn rõ chủ đích hơn.

## 7. Đọc văn bản, JSON hoặc nhị phân bằng stream

Cách đọc đơn giản cho UTF-8 text, với tên resource từ gốc module:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class ResourceText {
    private ResourceText() {
    }

    public static String read(String absoluteResourceName)
            throws IOException {
        try (InputStream in = ResourceText.class.getModule()
                .getResourceAsStream(absoluteResourceName)) {
            if (in == null) {
                throw new IOException(
                    "Resource không tồn tại hoặc không được phép đọc: "
                    + absoluteResourceName
                );
            }

            return new String(
                in.readAllBytes(), StandardCharsets.UTF_8
            );
        }
    }
}
~~~

Ví dụ dùng trong chính module chứa `ResourceText`:

~~~java
String text = ResourceText.read(
    "com/example/app/templates/welcome.txt"
);
~~~

Đối với tài nguyên lớn, đừng dùng `readAllBytes()` nếu không cần giữ toàn bộ nội dung trong bộ nhớ; hãy xử lý theo stream hoặc reader từng phần. Với JSON, truyền stream/reader vào thư viện parser thích hợp. Với ảnh hoặc dữ liệu nhị phân, giữ nguyên byte và tránh chuyển qua `String`.

**Không giả định resource là file thường:**

~~~java
// Dễ lỗi khi đóng gói trong JAR hoặc runtime image:
Path path = Path.of(App.class.getResource("app.properties").toURI());
~~~

URL từ `getResource` có thể mang scheme như `jar:` hoặc scheme của runtime image, không luôn chuyển được thành một `Path` trên filesystem mặc định. Nếu API phía sau nhận `InputStream`, hãy đưa stream trực tiếp. Nếu thư viện bắt buộc nhận file vật lý, cần một quy trình trích xuất tạm có quản lý vòng đời riêng.

## 8. Kiểm tra đóng gói và chẩn đoán lỗi

Khi nhận `null`, hãy kiểm tra theo thứ tự:

1. **Tên resource có chính xác không?** `App.class.getResource("x.txt")` là tên tương đối với package; `App.class.getResource("/x.txt")` là tên từ gốc. `Module` và `ClassLoader` không dùng `/` ở đầu.
2. **Resource có trong artifact không?** Với JAR, có thể dùng `jar tf application.jar` để tìm đúng entry, kể cả chữ hoa/chữ thường. Java phân biệt tên resource theo đường dẫn.
3. **Nó nằm trong module nào?** In `App.class.getModule().getName()` và kiểm tra module graph. Lớp trên classpath thuộc unnamed module, khác với named module trên module path.
4. **Đang dùng API nào?** Nếu `Class.getResourceAsStream` chạy được nhưng `ClassLoader.getResource` thất bại, xem lại quy tắc package `opens` của named module.
5. **Có đang gọi từ module khác?** Với `Module.getResourceAsStream`, kiểm tra `opens p to caller;` hoặc `opens p;`. Chỉ `exports` không giải quyết mọi trường hợp tra cứu resource.
6. **Đã copy tệp resource khi build chưa?** `javac` biên dịch lớp Java, không copy resource tự động; Maven/Gradle thường có bước resource processing.
7. **Có phụ thuộc thứ tự class loader không?** Nếu nhiều JAR hoặc module chứa tên giống nhau, đừng dựa vào resource được tìm đầu tiên; tham chiếu module/lớp sở hữu để giảm nhập nhằng.

Đoạn quan sát tối thiểu trong module đang gặp lỗi:

~~~java
System.out.println("Module: " + App.class.getModule().getName());
System.out.println("Loader: " + App.class.getClassLoader());
System.out.println("Relative: "
    + App.class.getResource("app.properties"));
System.out.println("Absolute: "
    + App.class.getResource(
        "/com/example/app/app.properties"));
~~~

Không cần log toàn bộ nội dung file cấu hình, đặc biệt nếu resource có dữ liệu nhạy cảm. Chỉ log tên logic, module, API đã gọi và kết quả có/không tìm thấy.

## 9. Những nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `getResource("config.yml")` trả về `null` | File ở gốc nhưng tên tương đối được ghép thêm package | Dùng `getResource("/config.yml")` hoặc chuyển file vào package |
| `ClassLoader.getResource("/a/b.txt")` không thấy | Có dấu `/` đầu tên | Dùng `getResource("a/b.txt")` |
| Chạy trên IDE được nhưng JAR không tìm thấy | Resource chưa được đưa vào JAR hoặc đường dẫn artifact khác | Kiểm tra output build và `jar tf` |
| `Class` đọc được, `ClassLoader` không thấy | Package của named module chưa `opens` vô điều kiện | Ưu tiên tra cứu qua lớp/module sở hữu; chỉ mở package khi thực sự cần |
| Module khác không đọc được `Module.getResourceAsStream` | Package không mở cho module gọi | Khai báo `opens p to consumer;` hoặc công khai API đọc nội bộ |
| `exports` rồi mà vẫn không tìm thấy resource | `exports` phục vụ khả năng truy cập kiểu public, không tương đương `opens` | Xem lại API lookup và quy tắc mở package |
| `Path.of(url.toURI())` lỗi | Resource nằm trong JAR/runtime image | Đọc bằng `InputStream` |
| Tìm resource trong module chưa resolve | Module không thuộc layer/graph đang dùng | Đảm bảo module được resolve và chọn đúng `ModuleLayer` |

## 10. Thực hành tốt

- Ưu tiên `SomeClass.class.getResourceAsStream(...)` cho resource gắn với chính thành phần Java đó; dùng `SomeClass.class.getModule().getResourceAsStream(...)` khi muốn nêu rõ module đích và tên resource tuyệt đối.
- Đặt tên resource ổn định, không gắn đường dẫn source/build vào mã ứng dụng; tổ chức resource gần package sử dụng nếu hợp lý.
- Kiểm tra `null` và thông báo lỗi kèm tên resource; bao `InputStream` trong `try-with-resources`.
- Chỉ dùng `opens` ở phạm vi cần thiết; không mở cả module chỉ để sửa một lời gọi lookup sai.
- Đặt ranh giới API rõ ràng: module sở hữu dữ liệu có thể trả về đối tượng đã parse, thay vì bắt mọi consumer tự tìm tệp bên trong module.
- Khi resource có thể thay đổi theo môi trường, phân biệt **resource đóng gói chỉ đọc** với **file cấu hình bên ngoài**. Với file bên ngoài, dùng `Files.newInputStream(Path)` và một chính sách cấu hình rõ ràng.
- Khi tích hợp `ResourceBundle`, `ServiceLoader` hoặc framework dùng reflection, tra cứu resource và đăng ký service là các cơ chế khác nhau; cần áp dụng đúng contract của từng API thay vì chỉ sửa đường dẫn.

## 11. Checklist ghi nhớ

1. `Class.getResource("x")`: tương đối với package; `Class.getResource("/x")`: từ gốc.
2. `ClassLoader.getResource("a/b")` và `Module.getResourceAsStream("a/b")`: dùng tên từ gốc, không có `/` đầu.
3. Trong named module, **module sở hữu và package chứa resource** quyết định khả năng truy cập.
4. `exports` công khai API Java; `opens` liên quan đến mở package ở runtime, bao gồm các quy tắc resource lookup.
5. `Module.getResourceAsStream` phù hợp khi cần chọn một module cụ thể; `ClassLoader.getResource` có giới hạn lookup đối với resource bị encapsulate.
6. Đọc bằng stream, kiểm tra `null`, đóng stream; xác minh resource có mặt trong artifact trước khi nghi ngờ JPMS.

**Tài liệu để tra cứu thêm:** Javadoc của `java.lang.Class#getResource`, `java.lang.ClassLoader#getResource`, `java.lang.Module#getResourceAsStream`; *The Java Language Specification*, chương về modules; hướng dẫn JPMS của OpenJDK.
