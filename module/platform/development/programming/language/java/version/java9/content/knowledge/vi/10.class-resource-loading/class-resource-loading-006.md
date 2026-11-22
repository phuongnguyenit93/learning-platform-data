# Ảnh hưởng của đóng gói package tới việc tìm tài nguyên

## 1. Tổng quan

Trong Java Platform Module System (JPMS), package vừa là đơn vị tổ chức kiểu Java, vừa là ranh giới đóng gói của named module. Ranh giới này ảnh hưởng đến việc mã ở module khác tìm và đọc tài nguyên (resource) nằm bên trong module.

Tài nguyên thường gặp gồm:

- File cấu hình như `config.properties`, `application.yml`.
- File văn bản, mẫu email, template hoặc dữ liệu JSON/XML.
- Hình ảnh, font, file ngôn ngữ và dữ liệu nhúng trong JAR.
- File tài nguyên đặt cùng package với class để class đó tải theo đường dẫn tương đối.

Trên class path truyền thống, ứng dụng thường tìm tài nguyên bằng `Class.getResource`, `ClassLoader.getResource` hoặc các phương thức đọc stream tương ứng. Khi tài nguyên nằm trong named module, JPMS áp dụng quy tắc đóng gói package. Vì vậy, một resource có thể tồn tại trong JAR nhưng vẫn không được mã ở module khác tìm thấy.

Điểm cần nhớ:

- `exports` công khai các kiểu public trong package cho module khác.
- `opens` cho phép module khác truy cập package bằng reflection sâu và cho phép các API resource tương ứng đọc tài nguyên trong package.
- Một package được export nhưng không open vẫn có thể che giấu các resource bên trong.
- Resource nằm ở gốc module, không thuộc package, không chịu cùng quy tắc đóng gói package.
- `ClassLoader.getResource` có quy tắc riêng: resource thông thường trong package của named module chỉ được trả về khi package được mở vô điều kiện. Resource kết thúc bằng `.class` có ngoại lệ.

## 2. Resource được tổ chức theo package như thế nào?

Trong một named module, đường dẫn resource thường phản chiếu tên package:

~~~text
com.example.assets/
├── module-info.java
├── com/
│   └── example/
│       └── assets/
│           ├── api/
│           │   ├── AssetApi.class
│           │   └── api-info.txt
│           ├── internal/
│           │   └── secret.properties
│           └── templates/
│               └── invoice.html
└── config.properties
~~~

Ví dụ:

- `com/example/assets/api/api-info.txt` nằm trong package `com.example.assets.api`.
- `com/example/assets/internal/secret.properties` nằm trong package `com.example.assets.internal`.
- `config.properties` nằm ở gốc module, không thuộc package Java nào.

Đối với resource nằm trong package, quyền tìm và đọc từ module khác phụ thuộc vào trạng thái mở của package. Resource ở gốc module có thể được đọc mà không cần mở một package cụ thể.

Khi đóng gói thành modular JAR, cấu trúc resource phải được giữ nguyên. File `module-info.class` nằm ở gốc JAR, còn resource giữ đường dẫn tương ứng với vị trí trong module.

## 3. Ba API tìm resource thường dùng

### 3.1. Class.getResource

`Class.getResource(String name)` tìm resource theo class được gọi:

- Nếu tên không bắt đầu bằng dấu `/`, đường dẫn được xem là tương đối với package của class.
- Nếu tên bắt đầu bằng dấu `/`, dấu `/` đầu tiên được bỏ và đường dẫn được xem là tuyệt đối từ gốc resource.
- Trả về `URL` nếu tìm thấy, hoặc `null` nếu không tìm thấy hay không được phép truy cập.

Ví dụ:

~~~java
URL relative = AssetApi.class.getResource("api-info.txt");
URL absolute = AssetApi.class.getResource(
    "/com/example/assets/api/api-info.txt"
);
~~~

Nếu `AssetApi` nằm trong package `com.example.assets.api`, lời gọi tương đối tìm:

~~~text
com/example/assets/api/api-info.txt
~~~

Lời gọi tuyệt đối tìm đúng đường dẫn đã chỉ định từ gốc module/class path.

Với resource trong named module, package chứa resource phải được mở cho module gọi. Việc package chỉ được export là chưa đủ.

### 3.2. ClassLoader.getResource

`ClassLoader.getResource(String name)` tìm resource theo đường dẫn từ gốc class loader:

~~~java
URL resource = AssetApi.class
    .getClassLoader()
    .getResource("com/example/assets/api/api-info.txt");
~~~

Khác với `Class.getResource`, tên resource truyền cho `ClassLoader.getResource` không có dấu `/` ở đầu. Nếu thêm dấu này, nó trở thành một phần của tên resource và thường không tìm thấy.

Với resource thông thường nằm trong package của named module, package phải được **mở vô điều kiện** để API này trả về resource. Một directive `opens package to com.example.app;` hoặc một `--add-opens` chỉ nhắm đến một module cụ thể không tương đương với mở vô điều kiện cho mục đích của `ClassLoader.getResource`.

Có một ngoại lệ quan trọng: tên resource kết thúc bằng `.class` không bị đóng gói theo quy tắc resource này. Vì vậy, `ClassLoader.getResource(".../SomeType.class")` có thể trả về resource ngay cả khi package tương ứng không được mở. Điều này không có nghĩa package đã được export hoặc mã khác được phép sử dụng kiểu Java trong package đó.

### 3.3. Module.getResourceAsStream

Từ Java 9, `Module.getResourceAsStream(String name)` cung cấp cách đọc resource trực tiếp từ một module:

~~~java
Module module = AssetApi.class.getModule();

try (InputStream input =
         module.getResourceAsStream(
             "com/example/assets/internal/secret.properties")) {
    if (input != null) {
        // Đọc nội dung resource.
    }
}
~~~

Tên resource là đường dẫn phân tách bằng dấu `/`. Dấu `/` đầu tiên, nếu có, được bỏ qua.

Với resource nằm trong package, package đó phải được mở cho module của mã đang gọi phương thức. Nếu package không mở cho caller, phương thức trả về `null`. Resource không nằm trong package, ví dụ `config.properties` ở gốc module, có thể được đọc mà không cần mở package.

Phương thức này trả về `InputStream`, không trả về `URL`. Cần đóng stream sau khi đọc, tốt nhất bằng try-with-resources.

## 4. exports và opens ảnh hưởng khác nhau tới resource

Giả sử module tài nguyên khai báo:

~~~java
module com.example.assets {
    exports com.example.assets.api;
}
~~~

Directive `exports` cho phép module khác truy cập các kiểu public trong package API. Nó không mở package cho deep reflection và cũng không làm các resource trong package trở nên công khai.

Nếu module ứng dụng cần đọc `api-info.txt` nằm trong package `com.example.assets.api`, chỉ khai báo `exports` vẫn chưa đủ. Cần mở package:

~~~java
module com.example.assets {
    exports com.example.assets.api;
    opens com.example.assets.api;
}
~~~

Có thể chỉ mở cho một module cụ thể:

~~~java
module com.example.assets {
    exports com.example.assets.api;
    opens com.example.assets.api to com.example.app;
}
~~~

Hai hình thức `opens`:

| Directive | Phạm vi |
|---|---|
| `opens package.name;` | Mở package vô điều kiện cho các module khác |
| `opens package.name to module.one, module.two;` | Chỉ mở package cho các module được liệt kê |

Một module cũng có thể được khai báo là open module:

~~~java
open module com.example.assets {
    exports com.example.assets.api;
}
~~~

Open module ngầm mở tất cả package cho truy cập runtime/reflection. Trong open module không khai báo thêm directive `opens` riêng. Cách này rộng hơn và thường không cần thiết nếu chỉ một vài package chứa resource cần chia sẻ.

**Không dùng exports để thay thế opens.** Nếu mục tiêu là công khai kiểu Java cho mã nguồn khác, dùng `exports`. Nếu mục tiêu là cho phép reflection sâu hoặc đọc resource trong package từ module khác, dùng `opens` đúng phạm vi.

## 5. Quy tắc truy cập theo API

| Vị trí resource | Class.getResource / Module.getResourceAsStream | ClassLoader.getResource |
|---|---|---|
| Resource ở gốc named module, không thuộc package | Có thể đọc | Có thể đọc |
| Resource trong package không open | Bị chặn khi caller ở module khác | Bị chặn |
| Resource trong package open vô điều kiện bằng `opens p;` | Có thể đọc | Có thể đọc |
| Resource trong package chỉ open cho caller bằng `opens p to m;` | Module `m` có thể đọc | Không đủ điều kiện mở vô điều kiện |
| File `.class` trong package không open | Tuân theo API/module lookup và quyền caller | `ClassLoader.getResource` có ngoại lệ, có thể trả về |

Bảng trên mô tả resource trong named module khi được truy cập từ module khác. Với code đọc resource từ chính module của nó, quy tắc caller và module cần được xét theo ngữ cảnh gọi cụ thể.

Một cách ghi nhớ hữu ích:

- `Class.getResource` và `Module.getResourceAsStream` kiểm tra package có open cho caller hay không.
- `ClassLoader.getResource` yêu cầu package chứa resource được mở vô điều kiện, ngoại trừ resource `.class`.
- Resource không thuộc package không bị giới hạn bởi directive opens của package.

## 6. Ví dụ hoàn chỉnh: resource trong package đóng và package mở

Ví dụ sau có hai named module:

- `com.example.assets` chứa API và resource.
- `com.example.app` đọc resource từ module tài nguyên.

### 6.1. Cấu trúc thư mục

~~~text
src/
├── com.example.assets/
│   ├── module-info.java
│   ├── config.properties
│   └── com/example/assets/
│       ├── api/
│       │   ├── AssetApi.java
│       │   └── api-info.txt
│       ├── closed/
│       │   ├── Hidden.java
│       │   └── secret.txt
│       └── opened/
│           ├── OpenMarker.java
│           └── public.txt
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

### 6.2. Module tài nguyên

File `src/com.example.assets/module-info.java`:

~~~java
module com.example.assets {
    exports com.example.assets.api;
    opens com.example.assets.opened;
}
~~~

Trong ví dụ:

- Package `com.example.assets.api` được export nhưng không open.
- Package `com.example.assets.closed` không export và không open.
- Package `com.example.assets.opened` được open vô điều kiện.
- `config.properties` nằm ở gốc module.

File `src/com.example.assets/com/example/assets/api/AssetApi.java`:

~~~java
package com.example.assets.api;

public final class AssetApi {
    private AssetApi() {
    }
}
~~~

File `src/com.example.assets/com/example/assets/closed/Hidden.java`:

~~~java
package com.example.assets.closed;

public final class Hidden {
}
~~~

File `src/com.example.assets/com/example/assets/opened/OpenMarker.java`:

~~~java
package com.example.assets.opened;

public final class OpenMarker {
}
~~~

Tạo các file resource với nội dung:

| Đường dẫn | Nội dung |
|---|---|
| `com/example/assets/api/api-info.txt` | `api-only-exported` |
| `com/example/assets/closed/secret.txt` | `closed-secret` |
| `com/example/assets/opened/public.txt` | `opened-public` |
| `config.properties` | `root-config` |

### 6.3. Module ứng dụng

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.assets;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.assets.api.AssetApi;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class Main {

    private static String read(InputStream input) throws Exception {
        if (input == null) {
            return "<null>";
        }
        try (input) {
            return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
            );
        }
    }

    private static String read(URL url) throws Exception {
        if (url == null) {
            return "<null>";
        }
        try (InputStream input = url.openStream()) {
            return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
            );
        }
    }

    public static void main(String[] args) throws Exception {
        String api = "com/example/assets/api/api-info.txt";
        String closed = "com/example/assets/closed/secret.txt";
        String opened = "com/example/assets/opened/public.txt";
        String root = "config.properties";
        String classFile = "com/example/assets/closed/Hidden.class";

        Module module = AssetApi.class.getModule();
        ClassLoader loader = AssetApi.class.getClassLoader();

        System.out.println(
            "Module.api.txt=" + read(module.getResourceAsStream(api))
        );
        System.out.println(
            "Class.relative.api.txt="
                + read(AssetApi.class.getResource("api-info.txt"))
        );
        System.out.println(
            "Class.root="
                + read(AssetApi.class.getResource("/config.properties"))
        );
        System.out.println(
            "Loader.root=" + read(loader.getResource(root))
        );
        System.out.println(
            "Module.closed.txt=" + read(module.getResourceAsStream(closed))
        );
        System.out.println(
            "Module.opened.txt=" + read(module.getResourceAsStream(opened))
        );
        System.out.println(
            "Module.root=" + read(module.getResourceAsStream("/" + root))
        );
        System.out.println(
            "Class.closed.txt="
                + read(AssetApi.class.getResource("/" + closed))
        );
        System.out.println(
            "Class.opened.txt="
                + read(AssetApi.class.getResource("/" + opened))
        );
        System.out.println(
            "Loader.api.txt=" + read(loader.getResource(api))
        );
        System.out.println(
            "Loader.closed.txt=" + read(loader.getResource(closed))
        );
        System.out.println(
            "Loader.opened.txt=" + read(loader.getResource(opened))
        );
        System.out.println(
            "Loader.closed.class=" + (loader.getResource(classFile) != null)
        );
    }
}
~~~

### 6.4. Biên dịch và đóng gói modular JAR

Biên dịch hai module:

~~~bash
javac --release 17 --module-source-path src -d out -m com.example.assets,com.example.app
~~~

Javac biên dịch các file Java và tạo class file. Nó không tự sao chép các file resource thông thường từ source tree vào thư mục output. Cần bảo đảm resource được copy vào đúng vị trí trước khi đóng gói.

Trên Windows PowerShell:

~~~powershell
Copy-Item -Recurse src/com.example.assets/com out/com.example.assets/
Copy-Item src/com.example.assets/config.properties out/com.example.assets/
~~~

Trên Linux hoặc macOS:

~~~bash
cp -R src/com.example.assets/com out/com.example.assets/
cp src/com.example.assets/config.properties out/com.example.assets/
~~~

Trong dự án Maven hoặc Gradle, đặt resource ở thư mục resource chuẩn của build, ví dụ `src/main/resources`, để build tool copy chúng vào output module và JAR.

Đóng gói module tài nguyên:

~~~bash
jar --create --file assets.jar -C out/com.example.assets .
~~~

Kiểm tra resource có trong JAR:

~~~bash
jar --list --file assets.jar
~~~

Kết quả cần có `module-info.class`, các class file và các resource như `config.properties`, `secret.txt`, `public.txt`.

### 6.5. Chạy ứng dụng

Trên Windows PowerShell:

~~~powershell
java --module-path "assets.jar;out/com.example.app" -m com.example.app/com.example.app.Main
~~~

Trên Linux hoặc macOS:

~~~bash
java --module-path assets.jar:out/com.example.app -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Module.api.txt=<null>
Class.relative.api.txt=<null>
Class.root=root-config
Loader.root=root-config
Module.closed.txt=<null>
Module.opened.txt=opened-public
Module.root=root-config
Class.closed.txt=<null>
Class.opened.txt=opened-public
Loader.api.txt=<null>
Loader.closed.txt=<null>
Loader.opened.txt=opened-public
Loader.closed.class=true
~~~

Giải thích:

- `api-info.txt` nằm trong package đã export nhưng chưa open, nên resource vẫn bị chặn.
- `secret.txt` nằm trong package không open, nên các API resource thông thường từ module ứng dụng không đọc được.
- `public.txt` nằm trong package được mở vô điều kiện, nên cả Module, Class và ClassLoader API đều đọc được.
- `config.properties` nằm ở gốc module, nên không cần mở package.
- `Hidden.class` vẫn có thể được lấy qua `ClassLoader.getResource` do ngoại lệ dành cho resource `.class`.

## 7. Mở package có chọn lọc khi chạy

Nếu không muốn mở package vô điều kiện trong module descriptor, có thể mở package cho một module cụ thể bằng `--add-opens` khi khởi chạy.

Ví dụ:

~~~bash
java --module-path assets.jar:out/com.example.app --add-opens com.example.assets/com.example.assets.closed=com.example.app -m com.example.app/com.example.app.Main
~~~

Trên Windows PowerShell, dùng dấu chấm phẩy trong module path:

~~~powershell
java --module-path "assets.jar;out/com.example.app" --add-opens com.example.assets/com.example.assets.closed=com.example.app -m com.example.app/com.example.app.Main
~~~

Sau khi mở package cho `com.example.app`, hai kết quả thay đổi:

~~~text
Module.closed.txt=closed-secret
Class.closed.txt=closed-secret
~~~

Nhưng:

~~~text
Loader.closed.txt=<null>
~~~

Đây là khác biệt cần lưu ý: `--add-opens` có đích cụ thể cho phép Module/Class resource lookup từ module đó, nhưng không làm package trở thành mở vô điều kiện cho `ClassLoader.getResource`.

Nếu ứng dụng cần `ClassLoader.getResource` đọc resource thông thường trong package, dùng directive mở vô điều kiện:

~~~java
opens com.example.assets.closed;
~~~

Chỉ mở package cần thiết để giảm phạm vi truy cập. `--add-opens` là tùy chọn runtime; nó không thay đổi module descriptor được đóng gói trong JAR.

## 8. Lựa chọn API theo nhu cầu

| Nhu cầu | API phù hợp |
|---|---|
| Tải resource tương đối với package của một class | `SomeClass.class.getResource("file.txt")` |
| Tải resource theo đường dẫn tuyệt đối | `SomeClass.class.getResource("/path/file.txt")` |
| Tìm resource theo class loader | `classLoader.getResource("path/file.txt")` |
| Đọc resource trực tiếp từ một named module | `module.getResourceAsStream("path/file.txt")` |
| Đọc resource dạng stream tương đối với class | `SomeClass.class.getResourceAsStream("file.txt")` |
| Liệt kê nhiều resource cùng tên | `ClassLoader.getResources("path/file.txt")` |

Các API trả về `null` hoặc không có kết quả khi resource không tồn tại, sai đường dẫn hoặc bị quy tắc đóng gói module chặn. Nên phân biệt lỗi đường dẫn với lỗi quyền truy cập package.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Resource có trong JAR nhưng trả về `null` | Package chứa resource không open cho caller | Thêm `opens` đúng package và đúng phạm vi |
| Đã khai báo `exports` nhưng vẫn không đọc được resource | Export package chỉ công khai kiểu public, không mở resource | Dùng `opens` cho package chứa resource |
| `Class.getResource` không tìm thấy file | Dùng sai đường dẫn tương đối hoặc tuyệt đối | Kiểm tra package của class và dấu `/` đầu tên resource |
| `ClassLoader.getResource` không tìm thấy resource | Có dấu `/` ở đầu hoặc package chỉ được mở có chọn lọc | Bỏ dấu `/`; mở package vô điều kiện nếu cần API ClassLoader |
| Module API trả về `null` | Resource nằm trong package không open cho module gọi | Mở package cho caller bằng `opens p to caller;` hoặc `--add-opens` |
| Resource chạy được trong IDE nhưng mất khi đóng JAR | Build chỉ biên dịch class mà không copy resource vào output | Đặt resource trong source resource directory hoặc cấu hình copy resource của build |
| Dùng `--add-exports` để mở resource | Nhầm export với open | Dùng `opens` hoặc `--add-opens` |
| Dùng `--add-opens` ở javac | `--add-opens` là tùy chọn runtime | Cấu hình ở lệnh `java`; compile-time access tới kiểu dùng exports/readability |
| Resource `.class` vẫn tìm thấy khi package đóng | ClassLoader có ngoại lệ cho resource kết thúc bằng `.class` | Không suy ra package đã export/open từ kết quả này |

## 10. Nguyên tắc thiết kế

- Đặt resource gần package hoặc module sở hữu chúng để đường dẫn dễ quản lý.
- Dùng resource ở gốc module cho dữ liệu thực sự không thuộc package cụ thể.
- Export package chứa API public; không export package chỉ để chia sẻ resource.
- Mở package resource có chọn lọc bằng `opens p to consumer;` khi dùng Module/Class API.
- Nếu cần `ClassLoader.getResource`, xác định rõ yêu cầu mở vô điều kiện của API này.
- Tránh dùng `open module` nếu chỉ một hoặc hai package cần truy cập.
- Giữ nguyên cấu trúc resource khi đóng modular JAR.
- Dùng Maven/Gradle hoặc bước copy rõ ràng để bảo đảm resource được đưa vào output.
- Luôn kiểm thử resource sau khi đóng gói JAR, không chỉ chạy từ thư mục IDE.
- Dùng API lookup phù hợp với mục đích và cách mở package của module.

## 11. Checklist kiểm tra resource

- Xác định resource nằm trong package nào hay ở gốc module.
- Kiểm tra đường dẫn trong JAR có đúng chữ hoa/thường và dấu phân cách `/` hay không.
- Xác định API đang dùng: Class, ClassLoader hay Module.
- Với `Class.getResource`, kiểm tra đường dẫn tương đối/absolute.
- Với `ClassLoader.getResource`, không thêm dấu `/` đầu đường dẫn.
- Kiểm tra package chứa resource đã được open đúng phạm vi chưa.
- Không nhầm `exports` với `opens`.
- Xác nhận resource thực sự được copy vào output và modular JAR.
- Kiểm thử cả trường hợp package mở và package đóng.
- Kiểm tra lại JAR cuối cùng bằng `jar --list --file`.

## 12. Tài liệu tham khảo

- [Class.getResource — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String)) — quy tắc đường dẫn tương đối và tuyệt đối.
- [ClassLoader.getResource — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ClassLoader.html#getResource(java.lang.String)) — tìm resource qua class loader và quy tắc đóng gói resource của named module.
- [Module.getResourceAsStream — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String)) — đọc resource trực tiếp từ module.
- [Java Language Specification — Module Declarations](https://docs.oracle.com/javase/specs/jls/se24/html/jls-7.html#jls-7.7) — cú pháp exports, opens và open module.
- [Java Archive Tool — jar](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html) — đóng gói và kiểm tra nội dung modular JAR.
