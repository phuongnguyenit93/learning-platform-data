# Tài nguyên trên classpath và khác biệt với tệp ngoài hệ thống

Ứng dụng Java thường cần đọc dữ liệu ngoài mã nguồn: file cấu hình mặc định, thông điệp, template, schema, ảnh, file SQL hoặc dữ liệu mẫu cho kiểm thử. Một số dữ liệu được đóng gói cùng ứng dụng trong thư mục tài nguyên và JAR; một số khác nằm bên ngoài ứng dụng, chẳng hạn file cấu hình do người vận hành cung cấp trên máy chủ.

Hai loại dữ liệu này có cách truy cập khác nhau. **Tài nguyên trên classpath (classpath resource)** được tìm thông qua class loader hoặc module chứa lớp. **Tệp ngoài hệ thống (external filesystem file)** được truy cập bằng đường dẫn của hệ điều hành qua API như `Path` và `Files`. Nhầm lẫn hai khái niệm thường dẫn đến lỗi chỉ xuất hiện sau khi đóng gói JAR, lỗi đường dẫn khi chạy từ thư mục khác hoặc không thể cập nhật cấu hình sau khi triển khai.

## 1. Tài nguyên là gì và được đặt ở đâu?

Tài nguyên là dữ liệu mà chương trình cần sử dụng nhưng không phải mã nguồn Java được biên dịch thành `.class`. Ví dụ:

- `application.properties` hoặc `messages.properties`.
- File JSON, XML, YAML hoặc CSV chứa dữ liệu khởi tạo.
- Template HTML, email hoặc báo cáo.
- Schema JSON, XSD, file SQL và migration script.
- Hình ảnh, biểu tượng, font hoặc dữ liệu nhị phân.
- File cấu hình mặc định và dữ liệu fixture dùng trong kiểm thử.

Trong dự án Java dùng quy ước Gradle Java plugin hoặc Maven, tài nguyên thường nằm trong các thư mục:

```text
src/
├── main/
│   ├── java/
│   │   └── com/example/App.java
│   └── resources/
│       ├── application.properties
│       ├── config/defaults.json
│       └── templates/welcome.html
└── test/
    ├── java/
    │   └── com/example/AppTest.java
    └── resources/
        └── fixtures/sample-user.json
```

`src/main/resources` chứa tài nguyên của ứng dụng chính. `src/test/resources` chứa tài nguyên dành cho kiểm thử. Build tool sao chép các tài nguyên này vào thư mục đầu ra tương ứng để chúng xuất hiện trên classpath của source set.

Với Gradle Java plugin, đầu ra mặc định thường là:

```text
build/
├── classes/java/main/       # Các file .class của mã nguồn chính
├── resources/main/          # Tài nguyên chính đã được xử lý
├── classes/java/test/       # Các file .class của mã nguồn kiểm thử
└── resources/test/          # Tài nguyên kiểm thử đã được xử lý
```

Với Maven, tài nguyên chính thường được sao chép vào `target/classes`, còn tài nguyên kiểm thử vào `target/test-classes`. Các thư mục đầu ra có thể thay đổi nếu build được cấu hình khác.

Khi đóng gói JAR, các tài nguyên chính thường được đưa vào archive cùng với bytecode. Ví dụ:

```text
order-service-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── com/
│   └── example/
│       └── OrderService.class
├── application.properties
├── config/
│   └── defaults.json
└── templates/
    └── welcome.html
```

Trong JAR, tài nguyên nằm ở đường dẫn tương đối tính từ gốc archive. Chúng không còn nhất thiết là những file riêng lẻ trong một thư mục mà chương trình có thể sửa trực tiếp.

## 2. Classpath resource khác tệp hệ thống như thế nào?

| Đặc điểm | Tài nguyên trên classpath | Tệp ngoài hệ thống |
|---|---|---|
| Cách định vị | Tên tài nguyên được tìm qua class loader hoặc module | Đường dẫn `Path` của hệ điều hành |
| API thường dùng | `Class.getResource`, `ClassLoader.getResource`, `getResourceAsStream` | `Path`, `Files`, `File` |
| Nguồn dữ liệu | Thư mục classpath, JAR hoặc module | Thư mục, ổ đĩa, volume hoặc filesystem được mount |
| Khi đóng gói JAR | Có thể nằm bên trong JAR | Thường vẫn nằm ở vị trí bên ngoài do môi trường triển khai quản lý |
| Khả năng ghi | Thông thường chỉ đọc; không nên giả định ghi được | Có thể đọc/ghi nếu quyền và filesystem cho phép |
| Phụ thuộc thư mục làm việc | Không cần dựa vào current working directory | Đường dẫn tương đối thường phụ thuộc current working directory |
| Mục đích phù hợp | Mặc định, template, schema, dữ liệu bất biến đi cùng ứng dụng | Cấu hình triển khai, dữ liệu thay đổi, log, upload và file do người dùng cung cấp |

Ví dụ, `config/defaults.json` nằm trong `src/main/resources` là tài nguyên classpath. Còn `/etc/order-service/application.properties` trên máy Linux là file hệ thống bên ngoài. Dù cả hai đều là file văn bản, cách tìm và vòng đời của chúng khác nhau.

Một nguyên tắc dễ nhớ: nếu dữ liệu được đóng gói như một phần của ứng dụng và chỉ cần đọc, hãy xem nó như resource. Nếu dữ liệu do người triển khai hoặc người dùng quản lý bên ngoài artifact, hãy truy cập bằng filesystem path.

## 3. Tìm tài nguyên bằng Class

### 3.1. `Class.getResource`

`Class.getResource(String name)` tìm tài nguyên theo vị trí của lớp được gọi. Cách diễn giải tên phụ thuộc vào ký tự đầu tiên:

- Nếu tên bắt đầu bằng `/`, đường dẫn được tính từ gốc resource/classpath.
- Nếu tên không bắt đầu bằng `/`, đường dẫn được tính tương đối với package của lớp.

Giả sử lớp nằm ở package `com.example.config`:

```java
package com.example.config;

public class Settings {
    public void locate() {
        var relative = Settings.class.getResource("defaults.properties");
        var absolute = Settings.class.getResource("/config/defaults.properties");
    }
}
```

Hai lời gọi tìm hai vị trí khác nhau:

| Lời gọi | Đường dẫn được tìm |
|---|---|
| `Settings.class.getResource("defaults.properties")` | `com/example/config/defaults.properties` |
| `Settings.class.getResource("/config/defaults.properties")` | `config/defaults.properties` từ gốc resource |

Nếu file nằm tại `src/main/resources/com/example/config/defaults.properties`, lời gọi tương đối đầu tiên phù hợp. Nếu file nằm tại `src/main/resources/config/defaults.properties`, lời gọi bắt đầu bằng `/` phù hợp.

`getResource` trả về `URL` nếu tìm thấy, hoặc `null` nếu không có resource tương ứng. Vì vậy cần xử lý trường hợp thiếu tài nguyên thay vì giả định luôn tìm thấy.

### 3.2. Đọc dữ liệu bằng `getResourceAsStream`

Nếu mục tiêu là đọc nội dung, `Class.getResourceAsStream` thường thuận tiện hơn vì trả về `InputStream`:

```java
package com.example.config;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class Settings {
    public Properties loadDefaults() throws IOException {
        Properties properties = new Properties();

        try (InputStream input = Settings.class.getResourceAsStream(
                "/config/defaults.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                    "Missing resource: /config/defaults.properties");
            }
            properties.load(input);
        }

        return properties;
    }
}
```

`try-with-resources` bảo đảm stream được đóng ngay cả khi đọc dữ liệu xảy ra exception. Nếu resource không tồn tại, `getResourceAsStream` trả về `null`, vì vậy ví dụ kiểm tra và báo lỗi rõ ràng.

Với file văn bản UTF-8, nên dùng `InputStreamReader` và chỉ định charset rõ ràng:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public String readTemplate() throws IOException {
    try (var input = getClass().getResourceAsStream("/templates/welcome.html")) {
        if (input == null) {
            throw new IllegalStateException("Template not found");
        }

        try (var reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8))) {
            return reader.lines().collect(java.util.stream.Collectors.joining("\n"));
        }
    }
}
```

Với dữ liệu nhị phân như ảnh hoặc file PDF, giữ dữ liệu dưới dạng byte stream hoặc byte array; không chuyển tùy tiện sang `String`.

## 4. Tìm tài nguyên bằng ClassLoader

### 4.1. `ClassLoader.getResource`

`ClassLoader.getResource(String name)` tìm resource bằng tên tính từ gốc classpath. Khác với `Class.getResource`, tên truyền vào không dùng dấu `/` ở đầu.

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
var url = loader.getResource("config/defaults.properties");

if (url == null) {
    throw new IllegalStateException("Resource not found");
}
```

Nếu dùng `Settings.class.getClassLoader()`, resource cũng được tìm theo tên từ gốc classpath:

```java
var loader = Settings.class.getClassLoader();
try (var input = loader.getResourceAsStream("config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Missing config/defaults.properties");
    }
    // Đọc input stream
}
```

Không thêm dấu `/` đầu tên resource khi gọi `ClassLoader.getResource` hoặc `getResourceAsStream`. Ví dụ `"config/defaults.properties"` là cách viết phù hợp; `"/config/defaults.properties"` thường sẽ không tìm thấy như mong muốn.

### 4.2. Chọn Class hay ClassLoader?

| API | Cách viết tên | Phạm vi tìm kiếm |
|---|---|---|
| `SomeClass.class.getResource("name")` | Tương đối với package của lớp | Resource theo ngữ cảnh lớp |
| `SomeClass.class.getResource("/path/name")` | Từ gốc resource | Resource theo ngữ cảnh lớp |
| `classLoader.getResource("path/name")` | Luôn từ gốc classpath, không có `/` đầu | Resource mà class loader có thể nhìn thấy |

Nếu resource thuộc về một lớp cụ thể, `SomeClass.class.getResourceAsStream(...)` thường dễ đọc vì tên tương đối có thể đi cùng package của lớp. Nếu đang viết framework hoặc cần tìm resource theo quy ước class loader, API `ClassLoader` có thể phù hợp.

`Thread.currentThread().getContextClassLoader()` thường được dùng trong framework, container hoặc thư viện cần dùng class loader do môi trường gọi cung cấp. Trong ứng dụng đơn giản, class loader của một lớp cụ thể thường dễ dự đoán hơn. Không nên thay class loader tùy tiện khi chưa hiểu môi trường nạp lớp.

## 5. Vì sao không nên chuyển mọi classpath resource thành File?

Khi chạy từ IDE, resource thường nằm trong một thư mục như `build/resources/main` hoặc `target/classes`. Khi đó URL có thể dùng giao thức `file:` và có thể chuyển thành `Path`. Nhưng sau khi đóng gói, resource có thể nằm bên trong JAR:

```text
jar:file:/opt/apps/order-service.jar!/config/defaults.properties
```

Đây là URL với giao thức `jar:`, không phải một đường dẫn file độc lập mà `new File(...)` có thể mở trực tiếp.

Ví dụ dễ gây lỗi:

```java
// Không an toàn cho resource nằm trong JAR
var url = getClass().getResource("/config/defaults.properties");
File file = new File(url.getFile());
```

Đoạn mã có thể chạy trong IDE nhưng thất bại sau khi ứng dụng được đóng gói. Ngay cả khi URL dùng `file:`, `url.getFile()` còn có thể chứa ký tự đã encode hoặc khoảng trắng; không nên tự phân tích chuỗi URL thành đường dẫn.

Nếu chỉ cần đọc nội dung, hãy dùng stream:

```java
try (var input = getClass().getResourceAsStream("/config/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Resource not found");
    }
    // Đọc dữ liệu trực tiếp từ stream
}
```

Nếu thực sự cần một `Path` để gọi API yêu cầu đường dẫn file, trước tiên phải biết resource có phải file vật lý hay không. Với URL `file:`, chuyển qua URI:

```java
var url = getClass().getResource("/config/defaults.properties");
if (url == null) {
    throw new IllegalStateException("Resource not found");
}

if ("file".equals(url.getProtocol())) {
    var path = java.nio.file.Paths.get(url.toURI());
    // Có thể dùng path với Files khi resource là file vật lý
} else {
    // Ví dụ URL jar: - đọc qua stream hoặc dùng API phù hợp với archive
}
```

Với resource nằm trong JAR, có thể dùng `JarFile` hoặc `FileSystem` của NIO nếu thật sự cần thao tác theo đường dẫn trong archive. Tuy nhiên, đọc bằng stream vẫn là cách đơn giản và ít phụ thuộc cách đóng gói nhất.

## 6. Tệp ngoài hệ thống: Path và Files

### 6.1. Đường dẫn tuyệt đối và tương đối

Tệp ngoài hệ thống được định vị bằng đường dẫn của filesystem. Java hiện đại khuyến khích dùng `Path` và `Files` thay vì bắt đầu với `File`.

```java
import java.nio.file.Path;

Path absolute = Path.of("/etc/order-service/application.properties");
Path relative = Path.of("config/application.properties");
```

Đường dẫn tuyệt đối xác định vị trí từ gốc filesystem hoặc volume tương ứng. Đường dẫn tương đối được phân giải theo thư mục làm việc hiện tại của tiến trình (current working directory), không phải tự động theo package của lớp hoặc vị trí JAR.

Có thể quan sát thư mục làm việc hiện tại:

```java
System.out.println(System.getProperty("user.dir"));
```

Nếu chương trình được khởi chạy từ các thư mục khác nhau, `Path.of("config/app.properties")` có thể trỏ đến các file khác nhau. Đây là nguyên nhân phổ biến khiến chương trình chạy được trong IDE nhưng không tìm thấy file khi chạy từ service manager hoặc container.

### 6.2. Đọc file bằng Files

Với file văn bản nhỏ:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path configPath = Path.of("/etc/order-service/application.properties");
String content = Files.readString(configPath, StandardCharsets.UTF_8);
```

Với file lớn hoặc cần xử lý theo dòng, có thể dùng `Files.newBufferedReader`:

```java
try (var reader = Files.newBufferedReader(configPath, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng
    }
}
```

Với dữ liệu nhị phân, có thể dùng `Files.newInputStream`, `Files.readAllBytes` hoặc các API phù hợp với kích thước file. Tránh đọc toàn bộ file lớn vào bộ nhớ nếu không cần thiết.

### 6.3. Kiểm tra và ghi file

Filesystem file có thể được tạo, sửa hoặc xóa nếu quyền truy cập cho phép:

```java
Path output = Path.of("var/reports/result.txt");
Files.createDirectories(output.getParent());
Files.writeString(output, "Build completed\n", StandardCharsets.UTF_8);
```

Đường dẫn tương đối ở ví dụ trên vẫn phụ thuộc working directory. Với ứng dụng production, nên lấy thư mục output từ cấu hình rõ ràng hoặc một thư mục dữ liệu do môi trường triển khai cấp.

Trước khi đọc hoặc ghi, có thể kiểm tra:

```java
if (!Files.exists(configPath)) {
    throw new IllegalStateException("Config file does not exist: " + configPath);
}

if (!Files.isReadable(configPath)) {
    throw new IllegalStateException("Config file is not readable: " + configPath);
}
```

Kiểm tra trước không loại bỏ hoàn toàn lỗi I/O vì file hoặc quyền truy cập có thể thay đổi giữa lúc kiểm tra và lúc mở. Vẫn cần xử lý `IOException` ở thao tác thực tế.

## 7. Chọn resource hay external file cho cấu hình ứng dụng?

Một ứng dụng thường cần cả hai loại:

- **Cấu hình mặc định** đi kèm ứng dụng, ví dụ timeout mặc định hoặc tên logger. Có thể đặt trong `src/main/resources`.
- **Cấu hình theo môi trường triển khai** do người vận hành cung cấp, ví dụ URL database, cổng lắng nghe hoặc feature flag. Thường nên đặt bên ngoài JAR.

Nếu đóng gói mọi cấu hình vào JAR, mỗi lần đổi URL database hoặc giới hạn bộ nhớ có thể phải build và phát hành lại artifact. Ngược lại, nếu đưa mọi template và schema bất biến ra ngoài filesystem, triển khai sẽ phải quản lý thêm nhiều file rời.

Một cách thiết kế phổ biến là đóng gói cấu hình mặc định làm resource, sau đó cho phép external file hoặc tham số môi trường ghi đè các giá trị cần thay đổi.

Ví dụ với properties:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class AppConfiguration {
    public static Properties load() throws IOException {
        Properties properties = new Properties();

        // 1. Nạp cấu hình mặc định đi kèm ứng dụng
        try (InputStream input = AppConfiguration.class.getResourceAsStream(
                "/application-defaults.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                    "Missing classpath resource: application-defaults.properties");
            }
            properties.load(input);
        }

        // 2. Nếu có đường dẫn cấu hình ngoài, nạp đè lên mặc định
        String externalConfig = System.getProperty("app.config");
        if (externalConfig != null && !externalConfig.isBlank()) {
            Path path = Path.of(externalConfig);
            try (InputStream input = Files.newInputStream(path)) {
                properties.load(input);
            }
        }

        return properties;
    }

    private AppConfiguration() {
    }
}
```

Chạy ứng dụng với file cấu hình bên ngoài:

```bash
java -Dapp.config=/etc/order-service/application.properties -jar order-service.jar
```

Trong ví dụ, file resource cung cấp giá trị mặc định. Nếu property `app.config` được truyền, file ngoài được nạp sau và có thể ghi đè các key trùng. Cách này giúp một artifact có thể chạy ở nhiều môi trường mà không cần đóng gói lại.

`Properties.load(InputStream)` dùng cách diễn giải ký tự theo quy ước ISO-8859-1 và escape Unicode của định dạng properties truyền thống. Nếu file `.properties` được lưu UTF-8 và cần đọc đúng UTF-8, hãy dùng `Reader`:

```java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

Với resource UTF-8, bọc `InputStream` trong `InputStreamReader` với `StandardCharsets.UTF_8` tương tự. Cần thống nhất encoding khi tạo file và khi đọc.

## 8. Tài nguyên trên classpath trong JAR và nhiều thư viện

### 8.1. Classpath có thể gồm thư mục và JAR

Classpath không chỉ là một thư mục duy nhất. Nó có thể chứa nhiều thư mục đầu ra và nhiều JAR. Ví dụ khi chạy Java:

```bash
java -cp "build/classes/java/main:build/resources/main:lib/*" com.example.Main
```

Trên Windows, dấu phân cách các phần tử classpath là `;` thay cho `:`:

```bat
java -cp "build\classes\java\main;build\resources\main;lib\*" com.example.Main
```

Khi chạy với `-jar`, Java dùng JAR được chỉ định làm executable archive và các thiết lập classpath phù hợp từ manifest hoặc cơ chế đóng gói. Không nên giả định các tham số `-cp` bên ngoài sẽ được kết hợp theo cách giống lệnh chạy class thông thường khi dùng `-jar`.

### 8.2. Resource trùng tên

Nhiều JAR có thể chứa resource cùng tên, ví dụ `META-INF/services/...` hoặc `config/defaults.properties`. Khi dùng `ClassLoader.getResource`, thông thường một URL đầu tiên theo thứ tự tìm kiếm sẽ được trả về. Thứ tự classpath hoặc class loader có thể ảnh hưởng kết quả.

Nếu cần liệt kê mọi resource cùng tên, có thể dùng `getResources`:

```java
var loader = Thread.currentThread().getContextClassLoader();
var resources = loader.getResources("META-INF/services/com.example.Plugin");

while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
```

Điều này hữu ích với cơ chế service provider hoặc plugin discovery. Nếu ứng dụng tự đặt một file cấu hình chung tên giống file của thư viện, kết quả có thể phụ thuộc thứ tự tìm kiếm. Nên chọn tên resource có namespace rõ ràng, ví dụ `com/example/order/config/defaults.properties`.

### 8.3. Resource trong executable/fat JAR

Một số plugin framework đóng gói dependency vào executable JAR theo cấu trúc riêng. Resource có thể nằm trong archive lồng nhau hoặc được cung cấp bởi class loader đặc biệt. Dùng `getResourceAsStream` giúp code ít phụ thuộc vào cấu trúc archive hơn việc cố tạo `File` từ URL.

Khi dùng thư viện hoặc framework có class loader riêng, nên tuân theo API resource mà framework cung cấp nếu nó có quy ước riêng. Tránh giả định resource luôn nằm trong JAR phẳng hoặc luôn có giao thức `file:`.

## 9. Tài nguyên trong Java Platform Module System (JPMS)

Classpath và module path có mô hình đóng gói khác nhau. Khi ứng dụng dùng JPMS, resource có thể thuộc một named module thay vì chỉ là một phần tử classpath không tên.

### 9.1. Resource thuộc module

Một module có thể chứa resource cùng package với các lớp:

```text
src/main/java/
└── com/example/orders/
    ├── module-info.java
    ├── OrderService.java
    └── defaults.properties
```

Trong lớp thuộc module đó, có thể tìm resource tương đối:

```java
package com.example.orders;

public class OrderService {
    public void loadDefaults() {
        try (var input = OrderService.class.getResourceAsStream("defaults.properties")) {
            if (input == null) {
                throw new IllegalStateException("defaults.properties not found");
            }
            // Đọc resource thuộc module này
        } catch (java.io.IOException e) {
            throw new RuntimeException(e);
        }
    }
}
```

Khi resource thuộc named module, quy tắc đóng gói module có thể ảnh hưởng đến khả năng truy cập từ module khác. Resource nằm trong package của module không mặc nhiên trở thành tài nguyên công khai chỉ vì file JAR chứa nó.

### 9.2. `exports` và `opens` không có cùng mục đích

Trong `module-info.java`:

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.config;
}
```

- `exports` cho phép module khác truy cập các kiểu public trong package được export theo quy tắc JPMS.
- `opens` cho phép truy cập sâu bằng reflection vào package ở runtime và cũng có ý nghĩa đối với việc truy cập resource theo quy tắc module.

Nếu một module khác cần đọc resource nằm trong package của module `com.example.orders`, package đó có thể cần được mở cho module gọi. Có thể mở cho một module cụ thể thay vì mở rộng cho tất cả:

```java
module com.example.orders {
    opens com.example.orders.config to com.example.config.reader;
}
```

Chỉ dùng `opens` cho package cần thiết. `exports` không phải cách thay thế để mở resource hoặc hỗ trợ deep reflection.

### 9.3. Module API để đọc resource

`Module` cung cấp `getResourceAsStream(String name)` để truy cập resource theo module. Tên resource được truyền theo đường dẫn tương đối trong module, không thêm dấu `/` ở đầu:

```java
Module module = OrderService.class.getModule();

try (var input = module.getResourceAsStream("com/example/orders/defaults.properties")) {
    if (input == null) {
        throw new IllegalStateException("Module resource not found");
    }
    // Đọc dữ liệu
}
```

Với resource thuộc package, khả năng truy cập từ module khác chịu các quy tắc encapsulation và package openness của JPMS. Code trong chính module có thể truy cập resource của module mình; khi chia sẻ resource qua ranh giới module, cần thiết kế `opens` và quyền truy cập có chủ đích.

## 10. Tùy chỉnh thư mục resource trong Gradle và Maven

### 10.1. Gradle sourceSets

Java plugin mặc định dùng `src/main/resources` và `src/test/resources`, nhưng có thể cấu hình thêm thư mục:

```groovy
sourceSets {
    main {
        resources {
            srcDir 'src/shared-resources'
        }
    }
}
```

Khi build, tài nguyên từ các thư mục được khai báo sẽ được xử lý và đưa vào resource output của source set. Nếu thêm nhiều thư mục có file trùng đường dẫn tương đối, cần xác định quy tắc xử lý để tránh kết quả phụ thuộc thứ tự hoặc gây lỗi duplicate theo cấu hình.

Có thể cấu hình task xử lý resource, ví dụ chỉ đưa một số file vào output:

```groovy
tasks.named('processResources') {
    exclude '**/*.bak'
}
```

### 10.2. Maven resources

Maven mặc định dùng `src/main/resources` và `src/test/resources`. Có thể cấu hình thư mục khác trong `pom.xml`:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/shared-resources</directory>
            <filtering>false</filtering>
        </resource>
    </resources>
</build>
```

Maven Resources Plugin sao chép resource vào output directory theo cấu hình. `filtering` có thể thay thế placeholder bằng property trong lúc build. Chỉ bật filtering cho file văn bản cần thay thế; không nên áp dụng bừa bãi cho ảnh, font, archive hoặc dữ liệu nhị phân vì nội dung có thể bị biến đổi.

Gradle cũng có cơ chế xử lý resource và thay thế nội dung qua CopySpec, chẳng hạn `expand`. Cần xác định rõ file nào được xử lý và giá trị nào được đưa vào artifact. Nếu cùng một JAR được phát hành cho nhiều môi trường, việc nhúng cấu hình môi trường cụ thể vào resource lúc build có thể làm giảm khả năng tái sử dụng artifact.

## 11. Kiểm thử resource

Tài nguyên trong `src/test/resources` được đưa vào test runtime classpath. Test có thể đọc fixture bằng chính các API resource:

```java
package com.example;

import org.junit.jupiter.api.Test;

import java.io.InputStream;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class OrderServiceTest {
    @Test
    void loadsFixture() {
        try (InputStream input = getClass().getResourceAsStream(
                "/fixtures/sample-user.json")) {
            assertNotNull(input, "Fixture should be available on the test classpath");
        } catch (java.io.IOException e) {
            throw new RuntimeException(e);
        }
    }
}
```

Không nên viết test chỉ dựa vào đường dẫn như `src/test/resources/fixtures/sample-user.json`. Đường dẫn đó có thể tồn tại trong checkout của source code nhưng không phản ánh cách ứng dụng sẽ tìm resource khi chạy từ test classpath hoặc JAR.

Nếu muốn kiểm tra artifact cuối cùng có chứa resource, cần kiểm tra nội dung JAR hoặc chạy integration test với artifact đã đóng gói. Test resource trong classpath kiểm thử không tự chứng minh resource đó đã được đưa vào JAR chính.

## 12. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra hoặc sửa |
|---|---|---|
| `getResource` trả về `null` | Sai tên, sai chữ hoa/thường, resource chưa được copy hoặc dùng nhầm quy tắc đường dẫn | Kiểm tra file trong resource output/JAR và cách dùng dấu `/` |
| Chạy trong IDE được nhưng JAR không tìm thấy resource | Code chuyển URL thành `File`, hoặc resource không được đóng gói | Dùng `getResourceAsStream`; kiểm tra nội dung JAR |
| File cấu hình không được tìm thấy khi chạy từ service | Dùng đường dẫn tương đối phụ thuộc working directory | Truyền đường dẫn tuyệt đối hoặc cấu hình thư mục rõ ràng |
| `FileNotFoundException` với đường dẫn có khoảng trắng | Tự lấy `URL.getFile()` rồi tạo `File` | Nếu resource, đọc stream; nếu URL `file:`, chuyển qua URI |
| Resource trả về nội dung cũ | Đang đọc resource đóng gói trong JAR hoặc build output chưa cập nhật | Xác định nguồn resource, rebuild khi cần hoặc chuyển cấu hình thay đổi ra ngoài |
| Resource trùng tên được lấy từ thư viện khác | Nhiều classpath entry chứa cùng tên | Dùng namespace riêng hoặc `getResources` để liệt kê |
| JPMS không cho module khác đọc resource | Package chứa resource chưa mở cho caller | Xem module-info và mở đúng package/module nếu cần |
| Ký tự tiếng Việt bị lỗi | Charset khi đọc không khớp encoding file | Dùng UTF-8 tường minh với Reader hoặc API tương ứng |
| File ảnh hoặc font bị hỏng sau build | Resource nhị phân bị filtering/expand | Tắt filtering cho file nhị phân |

Khi resource bị thiếu, hãy xác định nó thuộc source set nào, được copy vào output nào và có nằm trong artifact không. Sau đó kiểm tra tên resource và API lookup. Đừng bắt đầu bằng việc thay đổi hàng loạt đường dẫn trong mã nguồn.

## 13. Quy trình chẩn đoán resource không tìm thấy

Có thể lần lượt kiểm tra:

1. **Xác định loại dữ liệu:** resource được đóng gói hay file do môi trường triển khai cung cấp?
2. **Xác định vị trí nguồn:** file nằm trong `src/main/resources`, `src/test/resources` hay thư mục ngoài project?
3. **Kiểm tra output build:** Gradle có copy vào `build/resources/main` hoặc Maven có copy vào `target/classes` không?
4. **Kiểm tra artifact:** nếu lỗi chỉ xảy ra khi chạy JAR, liệt kê nội dung JAR và xác nhận đường dẫn resource.
5. **Kiểm tra quy tắc tên:** `Class.getResource` có tên tương đối/absolute đúng không; `ClassLoader.getResource` có bỏ dấu `/` đầu không?
6. **Kiểm tra module:** nếu dùng JPMS, package có bị encapsulate đối với caller không?
7. **Kiểm tra filesystem:** nếu là file ngoài, in đường dẫn đã phân giải và `user.dir`, rồi kiểm tra quyền truy cập.

Các lệnh hữu ích:

```bash
# Gradle: chạy xử lý resource
./gradlew processResources

# Maven: xử lý resource chính qua phase process-resources
./mvnw process-resources

# Liệt kê nội dung JAR
jar tf build/libs/order-service-1.0.0.jar
```

Tên và đường dẫn JAR thực tế phụ thuộc cấu hình dự án. Với Maven, JAR thường nằm trong `target/`; với Gradle Java plugin, thường nằm trong `build/libs/`.

## 14. Bảo mật và vận hành khi đọc file bên ngoài

File ngoài hệ thống thường do người vận hành hoặc người dùng cung cấp, vì vậy cần xem xét quyền truy cập và tính hợp lệ của đường dẫn.

- Không tin tưởng đường dẫn tùy ý từ request hoặc dữ liệu người dùng. Cần kiểm soát thư mục gốc được phép truy cập và ngăn path traversal.
- Không ghi token, mật khẩu hoặc khóa riêng vào resource mặc định được đóng gói trong JAR.
- Hạn chế quyền đọc/ghi của file cấu hình và thư mục dữ liệu theo tài khoản chạy ứng dụng.
- Xử lý trường hợp file không tồn tại, không đọc được hoặc nội dung không hợp lệ bằng thông báo rõ ràng.
- Không ghi toàn bộ nội dung cấu hình nhạy cảm vào log khi chẩn đoán.
- Nếu file có thể được thay đổi trong lúc ứng dụng chạy, xác định chính sách reload và đồng bộ thay vì giả định nội dung không đổi.

Đối với resource classpath, xem chúng như dữ liệu đi kèm artifact và thường bất biến trong suốt vòng đời chạy. Đối với external file, xác định ai sở hữu file, ai có thể thay đổi nó và ứng dụng phản ứng thế nào khi file đổi.

## 15. Bài tập vận dụng

Một ứng dụng `order-service` có cấu trúc:

```text
src/main/resources/
├── application-defaults.properties
├── templates/receipt.html
└── schemas/order.json

src/test/resources/
└── fixtures/order-created.json
```

Khi triển khai, nhóm vận hành cung cấp file `/etc/order-service/application.properties`. Hãy xác định:

1. `application-defaults.properties`, `receipt.html` và `order.json` nên được truy cập bằng API nào?
2. `fixtures/order-created.json` xuất hiện trên classpath nào?
3. Vì sao không nên tạo `File` trực tiếp từ URL của `receipt.html`?
4. Nếu dùng `Class.getResource` từ lớp `com.example.receipt.ReceiptRenderer`, tên tương đối nào trỏ đến resource cùng package và tên nào trỏ từ gốc?
5. Nếu dùng `ClassLoader.getResource`, có nên thêm dấu `/` đầu tên resource không?
6. File cấu hình bên ngoài nên được đọc bằng `Path`/`Files` hay class loader? Vì sao?
7. Làm thế nào để cấu hình ngoài ghi đè giá trị mặc định trong resource?
8. Nếu ứng dụng chuyển sang JPMS và module khác cần đọc resource trong package nội bộ, cần xem xét quy tắc nào?

Có thể tự kiểm chứng bằng cách đọc resource trong test, chạy `./gradlew processResources` hoặc `./mvnw process-resources`, đóng gói JAR rồi dùng `jar tf` để xem resource có nằm trong artifact hay không. Hãy thử chạy từ một working directory khác để quan sát sự khác biệt giữa resource lookup và đường dẫn filesystem tương đối.

Khi thiết kế cách đọc dữ liệu trong Java, hãy xác định trước dữ liệu đó thuộc về artifact hay thuộc về môi trường triển khai. Resource classpath phù hợp với dữ liệu mặc định, bất biến và được đóng gói cùng ứng dụng; `Path` và `Files` phù hợp với file bên ngoài có vị trí và vòng đời do hệ thống vận hành quản lý. Chọn đúng mô hình giúp chương trình chạy ổn định từ IDE, classpath, JAR và môi trường production.
