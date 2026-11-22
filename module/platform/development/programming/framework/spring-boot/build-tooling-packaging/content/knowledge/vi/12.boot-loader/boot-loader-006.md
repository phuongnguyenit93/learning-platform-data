# Cấu hình PropertiesLauncher với loader.path và loader.main trong Spring Boot

## 1. Mục tiêu và mô hình tư duy

Spring Boot đóng gói ứng dụng Java thành executable JAR, nhưng không phải mọi executable JAR đều sử dụng cùng một **Boot Loader**. Với JAR chuẩn, `JarLauncher` thường nạp class ở `BOOT-INF/classes` và dependency JAR lồng trong `BOOT-INF/lib`. Khi ứng dụng cần lấy **thêm JAR từ thư mục bên ngoài** hoặc cần **chọn main class khi khởi động**, Spring Boot cung cấp `PropertiesLauncher`.

Hai thuộc tính trọng tâm:

- `loader.path`: chỉ định những thư mục, archive hoặc vị trí bên ngoài được bổ sung vào **classpath do Boot Loader quản lý**.
- `loader.main`: chỉ định **fully qualified class name** có phương thức `public static void main(String[] args)` mà `PropertiesLauncher` sẽ gọi.

Ví dụ ý tưởng:

```text
/opt/loader-demo/
├── app.jar                           # Boot archive với PropertiesLauncher
├── lib/
│   └── greeting-extension.jar        # JAR triển khai bên ngoài
└── config/
    └── loader.properties             # Cấu hình loader

        java -Dloader.path=/opt/loader-demo/lib -jar app.jar
                             |
                             v
               PropertiesLauncher (Main-Class)
                             |
              +--------------+---------------+
              |                              |
        BOOT-INF/classes                /opt/loader-demo/lib
        BOOT-INF/lib                    greeting-extension.jar
              |                              |
              +--------------+---------------+
                             v
                 loader.main hoặc Start-Class
                             |
                             v
                 main(String[] args) của app
```

**Điểm cần nhớ:** `PropertiesLauncher` hoạt động **trước** khi Spring Boot ApplicationContext được tạo. `loader.path` là cấu hình classpath của **bootstrap launcher**, không phải Spring property `spring.config.location`. `loader.main` chọn hàm `main`, không phải tên controller hay tên Spring bean.

Bài học dùng **Java 17+ và Spring Boot 3.5.0** để có cấu hình plugin/loader nhất quán. Đây là phiên bản cố định cho ví dụ, không phải tuyên bố nó là phiên bản mới nhất. Khi dùng Spring Boot 2.x hoặc 4.x, cần đối chiếu namespace launcher và cơ chế đóng gói theo phiên bản thực tế.

## 2. Phân biệt JarLauncher, WarLauncher và PropertiesLauncher

Boot Loader là nhóm lớp bootstrap được đặt trong executable archive để thiết lập classloader có thể đọc **nested JAR**. Trong Spring Boot 3.5:

| Launcher | Tình huống mặc định | Classpath từ archive | Có hỗ trợ loader.path? |
| --- | --- | --- | --- |
| `org.springframework.boot.loader.launch.JarLauncher` | JAR thực thi chuẩn | `BOOT-INF/classes`, `BOOT-INF/lib` | Không theo cơ chế `PropertiesLauncher` |
| `org.springframework.boot.loader.launch.WarLauncher` | WAR thực thi | `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided` | Không theo cơ chế `PropertiesLauncher` |
| `org.springframework.boot.loader.launch.PropertiesLauncher` | Layout linh hoạt, thêm classpath ngoài, chọn main | Các vị trí chuẩn của archive cộng với cấu hình launcher | **Có**: `loader.path`, `loader.main` và các thuộc tính liên quan |

Chỉ thêm `-Dloader.path=/some/lib` vào lệnh chạy **JarLauncher** không có nghĩa JarLauncher sẽ đọc đường dẫn đó. Với Spring Boot Maven Plugin, chọn `<layout>ZIP</layout>` (hoặc `DIR`, alias của ZIP) để tạo archive dùng `PropertiesLauncher`. `ZIP` ở đây là **tên layout của Boot plugin**, không có nghĩa bạn phải đổi đuôi file `.jar` sang `.zip`.

**Manifest** cho một Boot JAR chuẩn thường có:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

Khi dùng layout ZIP/PropertiesLauncher, mong đợi:

```text
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

`Main-Class` là lớp launcher được JVM gọi đầu tiên. `Start-Class` là main của ứng dụng Spring Boot, được launcher gọi sau khi chuẩn bị classpath. `loader.main` có thể ghi đè lựa chọn main của launcher lúc chạy; nó **không tự sửa nội dung manifest** của file JAR.

Maven/Spring Boot plugin có thể thêm manifest attributes khác; các dòng trên là **phần đại diện cần kiểm tra**, không phải manifest đầy đủ. Tên package launcher thay đổi giữa một số phiên bản Spring Boot, nên không sao chép đường dẫn launcher của Boot 2.x vào JAR Boot 3.5.

## 3. Cơ chế nạp class của PropertiesLauncher

Một lần chạy `java -jar app.jar` có thể được hiểu thành:

1. Java đọc `META-INF/MANIFEST.MF`, tìm `Main-Class`.
2. Nếu manifest chỉ tới `PropertiesLauncher`, JVM gọi `PropertiesLauncher.main(String[])`.
3. Launcher đọc các nguồn cấu hình của mình: system properties, environment variables, file cấu hình launcher và manifest, theo quy tắc của phiên bản.
4. Launcher chuẩn bị classloader cho các class/resource trong archive và các vị trí `loader.path` được phép.
5. Launcher xác định main class: dùng `loader.main` nếu được chỉ định hợp lệ, nếu không thường lấy `Start-Class` trong manifest.
6. Launcher gọi `main(String[] args)` của class đã chọn. Từ đây Spring Boot mới bắt đầu khởi tạo ApplicationContext, embedded web server, bean và xử lý config ứng dụng.

```text
java -jar
  |
  v
META-INF/MANIFEST.MF
  |
  +-- Main-Class = PropertiesLauncher
                       |
                       +-- xác định loader.home
                       +-- đọc loader.properties / thông số loader
                       +-- xác định loader.path và BOOT-INF/*
                       +-- chọn loader.main hoặc Start-Class
                       |
                       v
                JVM context classloader
                       |
                       v
                main(String[] args)
                       |
                       v
                SpringApplication.run(...)
```

Đường `BOOT-INF/classes` và `BOOT-INF/lib` bên trong archive vẫn được PropertiesLauncher sử dụng trong mô hình JAR thông thường; `loader.path` nhằm **bổ sung** vị trí mới, không phải xóa các dependency đã đóng gói. Khi vô tình có hai JAR chứa cùng một class, thứ tự tìm kiếm có thể gây version conflict; đừng xem `loader.path` là một hệ thống thay dependency chính thức có cơ chế quản lý conflict như Maven.

## 4. Bảng cấu hình launcher cần nắm

| Thuộc tính | Mục đích | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| `loader.path` | Classpath bổ sung (danh sách phân tách bằng dấu phẩy) | `lib,plugins/analytics.jar` | Các mục tương đối được giải quyết theo `loader.home` |
| `loader.main` | Class chứa static main được chạy | `com.example.loader.AlternateMain` | Phải tồn tại trong classloader đã tạo |
| `loader.home` | Thư mục gốc cho đường dẫn tương đối và tìm cấu hình ngoài | `/opt/loader-demo` | Mặc định thường theo thư mục làm việc JVM (`user.dir`) |
| `loader.config.name` | Tên file cấu hình launcher không gồm phần mở rộng | `loader` → `loader.properties` | Có thể chủ động chỉ định để tránh nhầm file |
| `loader.config.location` | Vị trí cụ thể của file cấu hình launcher | `file:/opt/loader-demo/config/loader.properties` | Chấp nhận location theo cơ chế loader, không phải Spring config data |
| `loader.args` | Các application arguments mặc định | `--server.port=9090` | Được thêm vào danh sách args trước khi gọi main |
| `loader.system` | Cho phép xuất các properties launcher đã đọc sang Java System properties | `false` | Mặc định false; cân nhắc tránh lộ/đụng giá trị |

Tên tương ứng được dùng phổ biến:

| Loader property | Environment variable | Manifest attribute |
| --- | --- | --- |
| `loader.path` | `LOADER_PATH` | `Loader-Path` |
| `loader.home` | `LOADER_HOME` | `Loader-Home` |
| `loader.main` | `LOADER_MAIN` | `Start-Class` |
| `loader.args` | `LOADER_ARGS` | `Loader-Args` |
| `loader.config.location` | `LOADER_CONFIG_LOCATION` | `Loader-Config-Location` |
| `loader.system` | `LOADER_SYSTEM` | `Loader-System` |

Ví dụ ba cách thể hiện một đường dẫn:

```bash
# Java system property, chỉ có tác dụng với launcher thực sự là PropertiesLauncher:
java -Dloader.path=/opt/loader-demo/lib -jar app.jar

# Environment variable trên Linux/macOS:
LOADER_PATH=/opt/loader-demo/lib java -jar app.jar
```

```properties
# File loader.properties:
loader.path=/opt/loader-demo/lib
```

**Không tự đánh đồng** `LOADER_MAIN` với `SPRING_MAIN_*`, hoặc `loader.path` với `spring.config.location`. Nguồn đầu là của Boot Loader; nguồn sau thuộc hệ thống cấu hình Spring Boot application.

### Thứ tự ưu tiên và quy tắc file cấu hình

Theo tài liệu specification của dòng Boot 3.x, các giá trị của `PropertiesLauncher` có thể lấy từ environment variables, Java system properties, `loader.properties`, manifest của exploded archive và manifest của archive. Trong các nguồn có cùng khóa, thứ tự ưu tiên được tài liệu mô tả thông thường là **environment → system → loader.properties → manifest**, khi khóa đó hỗ trợ các nguồn này. Không nên tự suy đoán thứ tự giữa các file override nằm ở nhiều nơi; dùng đúng một nguồn cấu hình trong triển khai thực tế và kiểm tra JAR của phiên bản đang chạy.

Một nơi tên `loader.properties` được tìm là thư mục `loader.home`; các vị trí khác có thể bao gồm classpath root và `BOOT-INF/classes`. Có thể chỉ rõ file bằng `-Dloader.config.location=file:/.../loader.properties`. Một số chi tiết mặc định/nguồn tìm file đã có thay đổi và khác biệt trong tài liệu API giữa các phiên bản; **cách vận hành an toàn là cấu hình file location rõ ràng** trên môi trường đòi tính tái lập.

## 5. Ví dụ hoàn chỉnh: Spring Boot 3.5.0 + Maven layout ZIP

Phần thực hành xây một web app. Khi chạy **chưa có external JAR**, endpoint trả giá trị built-in. Khi thêm JAR vào `loader.path`, cùng endpoint tìm được class bên ngoài và trả giá trị khác. Một main class thứ hai sẽ chứng minh `loader.main` có thể thay entry point.

**Yêu cầu:**

- JDK 17 trở lên và Maven hỗ trợ Spring Boot 3.5.
- Có kết nối Maven Central hoặc repository manager được cấp quyền để tải dependency/plugin.
- Terminal Bash/Linux/macOS cho các lệnh `mkdir`, `javac`, `jar` và `curl`. Trên Windows có thể chạy Git Bash hoặc điều chỉnh lệnh tạo thư mục cho PowerShell.
- Project này là ví dụ độc lập; đừng dán thêm vào project Maven/Gradle đang có mà chưa ghép đúng POM.

Cấu trúc:

```text
loader-demo/
├── pom.xml
├── src/
│   └── main/java/com/example/loader/
│       ├── LoaderDemoApplication.java
│       └── AlternateMain.java
├── extensions-src/
│   └── com/example/extra/GreetingExtension.java
├── extension-classes/                  # được javac tạo, không commit
├── external-libs/
│   └── greeting-extension.jar          # được jar tạo, KHÔNG nằm trong app.jar
└── target/
    └── loader-demo-0.0.1-SNAPSHOT.jar  # được Maven repackage
```

### 5.1. File pom.xml đầy đủ

**`pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>loader-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>loader-demo</name>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>com.example.loader.LoaderDemoApplication</mainClass>
                    <layout>ZIP</layout>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`<layout>ZIP</layout>` là cấu hình **mấu chốt** giúp Boot plugin dùng `PropertiesLauncher` làm manifest `Main-Class`. `<mainClass>...LoaderDemoApplication</mainClass>` chỉ rõ entry point mặc định; điều này quan trọng vì project có thêm `AlternateMain` và plugin không cần đoán main class nào.

Vì POM kế thừa `spring-boot-starter-parent` và khai báo `spring-boot-maven-plugin`, execution `repackage` đã được cấu hình trong phase `package`. Không thêm execution `repackage` thứ hai với ID khác. Nếu project **không** dùng starter parent, cần bind goal `spring-boot:repackage` riêng vào phase package và pin plugin version thích hợp.

### 5.2. Main application và endpoint để kiểm tra external class

**`src/main/java/com/example/loader/LoaderDemoApplication.java`:**

```java
package com.example.loader;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LoaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoaderDemoApplication.class, args);
    }

    @GetMapping("/greet")
    public String greet(
            @RequestParam(name = "name", defaultValue = "Lan") String name) {
        try {
            ClassLoader contextLoader =
                    Thread.currentThread().getContextClassLoader();

            Class<?> extension = Class.forName(
                    "com.example.extra.GreetingExtension", true, contextLoader);

            Object value = extension
                    .getMethod("greet", String.class)
                    .invoke(null, name);

            return (String) value;
        }
        catch (ClassNotFoundException ex) {
            return "builtin:" + name;
        }
        catch (ReflectiveOperationException ex) {
            throw new IllegalStateException("Invalid greeting extension", ex);
        }
    }
}
```

Ở ví dụ này, ứng dụng **cố ý dùng reflection** để không có compile-time dependency vào external JAR. Đó là cách dễ nhất để thấy `loader.path` thực sự thêm classpath. Trong hệ thống lớn, dùng interface chung và `ServiceLoader`, SPI hoặc Spring bean contract được thiết kế/đóng version rõ ràng sẽ đáng bảo trì hơn. Reflection ở đây là ví dụ học tập, không phải đề xuất một plugin platform hoàn chỉnh.

`Thread.currentThread().getContextClassLoader()` là classloader phù hợp khi ứng dụng Boot đã được launcher thiết lập. Dùng `ClassLoader.getSystemClassLoader()` để tìm class bên trong nested JAR có thể gây lỗi, vì JVM system classloader không nhất thiết hiểu bố cục nested dependency của Boot Loader.

Nếu không có external `GreetingExtension`, controller trả **`builtin:Lan`** hoặc `builtin:<name>`. Nếu class tồn tại nhưng phương thức không đúng kiểu hoặc reflection lỗi, ứng dụng sẽ ném exception; không im lặng coi plugin lỗi như plugin chưa tồn tại. Điều này giúp phân biệt **chưa nạp JAR** với **JAR hỏng hoặc không tương thích**.

### 5.3. Main class thay thế để thử loader.main

**`src/main/java/com/example/loader/AlternateMain.java`:**

```java
package com.example.loader;

public final class AlternateMain {

    private AlternateMain() {
    }

    public static void main(String[] args) {
        String value = (args.length == 0) ? "no-args" : args[0];
        System.out.println("alternate-main:" + value);
    }
}
```

`AlternateMain` **không khởi động SpringApplication**, vì vậy khi chọn main này sẽ không có HTTP server. Đây là cách test rõ ràng nhất để biết `loader.main` đã thực sự ghi đè `Start-Class`.

### 5.4. Build executable JAR

Chạy từ project root:

```bash
mvn -B -ntp clean package
```

Với POM mẫu, file chính được tạo thường là:

```text
target/loader-demo-0.0.1-SNAPSHOT.jar
```

Và JAR nguồn trước repackage thường được giữ với hậu tố `.jar.original`. `mvn package` tạo JAR Maven trước, `spring-boot:repackage` đóng lại thành executable archive. `layout=ZIP` vẫn tạo **JAR có đuôi .jar**, nhưng manifest trỏ đến `PropertiesLauncher`.

Nếu repository dùng Maven Wrapper, gọi `./mvnw -B -ntp clean package` (Windows: `mvnw.cmd`). POM này không có tests, nên `package` có thể báo không có test để chạy; đó không phải lỗi runtime. Với dự án thật, đừng bỏ qua unit/integration tests khi chuẩn bị artifact phát hành.

### 5.5. Kiểm tra launcher trong JAR

```bash
jar tf target/loader-demo-0.0.1-SNAPSHOT.jar
```

Các entry quan trọng sẽ bao gồm:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/PropertiesLauncher.class
BOOT-INF/classes/com/example/loader/LoaderDemoApplication.class
BOOT-INF/classes/com/example/loader/AlternateMain.class
BOOT-INF/lib/...
```

`BOOT-INF/lib/...` ở trên là **mô tả nhóm dependency**, không phải tên file JAR thực tế. Cách kiểm tra manifest trực tiếp trên Bash:

```bash
unzip -p target/loader-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
```

Hai dòng cần tìm:

```text
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

Manifest có thể chứa nhiều dòng khác. Nếu thấy `Main-Class: org.springframework.boot.loader.launch.JarLauncher`, kiểm tra lại `<layout>ZIP</layout>` và đúng artifact đang chạy. Chỉ có class `PropertiesLauncher.class` bên trong JAR chưa đủ: **manifest Main-Class** mới quyết định launcher nào được gọi bởi `java -jar`.

## 6. Thực hành loader.path: nạp JAR hoàn toàn bên ngoài archive

### 6.1. Tạo external JAR bằng JDK 17

Tạo file **`extensions-src/com/example/extra/GreetingExtension.java`** trong project root, **không** đặt trong `src/main/java` của app:

```java
package com.example.extra;

public final class GreetingExtension {

    private GreetingExtension() {
    }

    public static String greet(String name) {
        return "external:" + name;
    }
}
```

Dùng Java compiler của JDK:

```bash
mkdir -p extension-classes external-libs
javac --release 17 -d extension-classes \
  extensions-src/com/example/extra/GreetingExtension.java

jar --create \
  --file external-libs/greeting-extension.jar \
  -C extension-classes .
```

`javac --release 17` tạo bytecode/API target Java 17 cho source đơn giản này. `jar --create` đóng compiled class vào JAR độc lập. Kiểm tra:

```bash
jar tf external-libs/greeting-extension.jar
```

Kỳ vọng có entry:

```text
com/example/extra/GreetingExtension.class
```

JAR này **không** được Maven đóng sẵn vào `BOOT-INF/lib` vì source của nó nằm ngoài `src/main/java` và POM không khai báo dependency vào artifact đó. Vì vậy chỉ có cách bổ sung runtime classpath qua launcher mới giúp ứng dụng tìm class ấy.

### 6.2. Chạy không có loader.path

Từ project root, chạy:

```bash
java -jar target/loader-demo-0.0.1-SNAPSHOT.jar
```

Ở terminal khác:

```bash
curl -fsS 'http://localhost:8080/greet?name=Lan'
```

**Response body kỳ vọng:**

```text
builtin:Lan
```

Nếu port 8080 đã có ứng dụng khác chiếm hoặc cấu hình Spring Boot đang override port, chỉnh cổng lúc chạy:

```bash
java -jar target/loader-demo-0.0.1-SNAPSHOT.jar --server.port=9090
```

Khi đó dùng `http://localhost:9090/greet?name=Lan`. Dừng JVM bằng Ctrl+C trước khi đổi cách khởi động, tránh hai process tranh nhau cổng 8080.

### 6.3. Chạy với loader.path

Chạy:

```bash
java -Dloader.path=external-libs \
  -jar target/loader-demo-0.0.1-SNAPSHOT.jar
```

Lệnh trên giả định **thư mục làm việc hiện tại chính là project root**, nên `external-libs` trỏ tới thư mục đã chứa `greeting-extension.jar`. PropertiesLauncher sẽ tìm thêm JAR trong đường dẫn đó.

Gọi:

```bash
curl -fsS 'http://localhost:8080/greet?name=Lan'
```

**Response body kỳ vọng:**

```text
external:Lan
```

Đây là sự khác biệt quan sát được bằng cùng một app JAR, **không rebuild ứng dụng**: khi không cấp `loader.path`, class extension vắng mặt; khi cấp, nó được đưa vào classloader của ứng dụng.

Đường classloader được thiết lập **khi tiến trình JVM khởi động**. Chép thêm JAR vào `external-libs` sau khi Spring Boot đã start không bảo đảm nó được phát hiện ngay; bình thường cần restart JVM để đưa archive mới vào classpath.

### 6.4. Dùng đường dẫn tuyệt đối, biến môi trường và nhiều vị trí

Với Linux/macOS, nếu không chạy từ project root, tránh phụ thuộc working directory:

```bash
java -Dloader.path=/opt/loader-demo/lib \
  -jar /opt/loader-demo/app.jar
```

Hoặc dùng biến môi trường:

```bash
LOADER_PATH=/opt/loader-demo/lib \
  java -jar /opt/loader-demo/app.jar
```

Có thể khai báo nhiều mục, phân tách bằng **dấu phẩy**:

```bash
java -Dloader.path=/opt/loader-demo/lib,/opt/loader-demo/plugins \
  -jar /opt/loader-demo/app.jar
```

Hai thư mục trên là ví dụ cấu trúc triển khai, cần được tạo và chứa các JAR hợp lệ. Trong PowerShell:

```powershell
$env:LOADER_PATH = "C:\apps\loader-demo\lib"
java -jar C:\apps\loader-demo\app.jar
```

Dùng path Windows phù hợp; đừng sao chép `/opt/...` sang Windows. Khi chỉ cần dùng một archive trực tiếp thay vì thư mục:

```bash
java -Dloader.path=/opt/loader-demo/lib/greeting-extension.jar \
  -jar /opt/loader-demo/app.jar
```

Các mục `loader.path` có thể là thư mục chứa resource, JAR/ZIP cụ thể hoặc dạng thư mục archive được hỗ trợ; không coi đây là cú pháp Maven dependency hay URL repository. `loader.path` không tự tải artifact từ Maven Central. Build/publish JAR bên ngoài vẫn cần quy trình dependency management và kiểm soát provenance riêng.

### 6.5. Tại sao không dùng -cp thông thường?

Với executable Boot JAR, `java -jar app.jar` sử dụng manifest và Boot Loader; `-cp` của JVM không tự biết cách giải quyết nested `BOOT-INF/lib/*.jar`. Cú pháp:

```bash
java -cp external-libs/* -jar app.jar
```

không phải một cách tin cậy để bổ sung classpath cho executable JAR: khi dùng `-jar`, JVM xử lý classpath theo executable archive, không dựa trên `-cp` như khi gọi một main class thông thường. Với Spring Boot `PropertiesLauncher`, dùng **`loader.path`** là con đường được thiết kế cho classpath bổ sung.

## 7. Thực hành loader.main: đổi main class mà không rebuild

Manifest của ví dụ mặc định có `Start-Class: com.example.loader.LoaderDemoApplication`, nên chạy bình thường sẽ tạo web server.

Muốn **thay main class** bằng `AlternateMain`:

```bash
java -Dloader.main=com.example.loader.AlternateMain \
  -jar target/loader-demo-0.0.1-SNAPSHOT.jar \
  demo
```

**Stdout do `AlternateMain` in ra (không tính log JVM/launcher):**

```text
alternate-main:demo
```

Lần chạy này không tạo embedded web server, vì `AlternateMain.main` chỉ in ra một dòng rồi kết thúc. Đối số `demo` sau tên JAR được chuyển tới `String[] args` của main thay thế.

Có thể dùng environment variable:

```bash
LOADER_MAIN=com.example.loader.AlternateMain \
  java -jar target/loader-demo-0.0.1-SNAPSHOT.jar demo
```

Hoặc đưa main class vào `loader.properties`:

```properties
loader.main=com.example.loader.AlternateMain
```

**Không nhầm đối số trước/sau `-jar`:**

- `java -Dloader.main=com.example.loader.AlternateMain -jar app.jar`: Java system property được launcher đọc **trước khi chọn main**.
- `java -jar app.jar --loader.main=com.example.loader.AlternateMain`: đây là **application argument** gửi tới main đã chọn; PropertiesLauncher không nên được kỳ vọng đổi main theo cách này.
- `java -jar app.jar --spring.profiles.active=dev`: cấu hình Spring application **sau** khi main được chọn; không thay launcher main.
- `-Dloader.main=...` có hiệu lực theo cơ chế PropertiesLauncher, khác với `-Dstart.class=...` của một Maven build script.

`loader.main` phải có một class thực sự tồn tại trong classpath mà PropertiesLauncher vừa tạo. Class đó phải có static `main(String[])` truy cập được. Nếu nhập sai package, lỗi liên quan **main class not found** xuất hiện ngay ở bootstrap, trước khi Spring beans được tạo.

### Có thể đặt main class nằm trong external JAR không?

Có, nếu class main hợp lệ nằm trong một archive mà `loader.path` đã nạp. Ví dụ tổng quát:

```bash
java -Dloader.path=/opt/loader-demo/plugins \
  -Dloader.main=com.example.plugin.PluginEntryPoint \
  -jar /opt/loader-demo/app.jar
```

`com.example.plugin.PluginEntryPoint` ở đây là tên **minh họa**, không nằm trong demo đã viết. Để thực sự chạy, JAR bên ngoài phải chứa class đó với `public static void main(String[] args)`, các dependency phù hợp và khả năng tương thích với classloader. Không dùng `loader.main` để chạy ngẫu nhiên mã không được tin cậy; nó cấp quyền khởi động mã Java trong chính tiến trình ứng dụng.

## 8. File loader.properties và loader.home

Nếu mọi lần đều truyền nhiều `-Dloader.*` trên dòng lệnh, cấu hình sẽ khó quản lý. `PropertiesLauncher` hỗ trợ file cấu hình launcher, thường đặt tên `loader.properties`.

Ví dụ triển khai trên Linux:

```text
/opt/loader-demo/
├── app.jar
├── config/
│   └── loader.properties
└── lib/
    └── greeting-extension.jar
```

**`/opt/loader-demo/config/loader.properties`:**

```properties
loader.path=lib
loader.main=com.example.loader.LoaderDemoApplication
```

Lệnh chạy với location tường minh:

```bash
java \
  -Dloader.home=/opt/loader-demo \
  -Dloader.config.location=file:/opt/loader-demo/config/loader.properties \
  -jar /opt/loader-demo/app.jar
```

**Giải thích:**

- `loader.home=/opt/loader-demo` làm gốc để giải quyết `loader.path=lib` thành `/opt/loader-demo/lib`.
- `loader.config.location=file:/opt/loader-demo/config/loader.properties` trỏ **đúng file cấu hình launcher**. Không phụ thuộc việc file nằm trong CWD hay được nhúng trong JAR.
- `loader.main=...LoaderDemoApplication` có thể bỏ khỏi file vì manifest `Start-Class` đã đúng; giữ lại chỉ để minh họa khả năng điều khiển.
- Đường dẫn `file:/...` là ví dụ URI cho Linux/Unix. Trên Windows cần dùng file URI và escaping phù hợp.

Nếu file launcher nằm trong `loader.home` ở tên được nhận diện, có thể dùng `-Dloader.home=/opt/loader-demo` và cách tìm `loader.properties` mặc định. Nhưng để triển khai nhiều môi trường và giảm nhầm lẫn, khai báo **location tường minh** là phương án rõ ràng hơn.

### 8.1. loader.config.name và loader.config.location khác nhau

- `loader.config.name` cho biết **tên file** không gồm `.properties`, ví dụ `loader`; launcher sẽ tìm `loader.properties` ở những vị trí được hỗ trợ.
- `loader.config.location` cho biết **địa chỉ file** cụ thể, ví dụ `file:/opt/loader-demo/config/loader.properties`.
- Không dùng `loader.path` để mong launcher tìm ra file `loader.properties`: **classpath của file cấu hình launcher và classpath mở rộng sau khi nạp loader.path là hai việc khác nhau**.

Ví dụ chạy với tên được chỉ định rõ và file nằm trong project working directory:

```bash
java -Dloader.config.name=loader \
  -Dloader.home=. \
  -jar target/loader-demo-0.0.1-SNAPSHOT.jar
```

Ví dụ trên giả định có `./loader.properties` hợp lệ. Nếu không muốn đặt file vào root project, dùng `loader.config.location=file:/absolute/path/loader.properties` như phần trước.

### 8.2. Đừng nhầm với Spring application.properties

Hai file có nhiệm vụ khác nhau:

| File | Được xử lý bởi | Đặt loại khóa nào? |
| --- | --- | --- |
| `loader.properties` | `PropertiesLauncher` ở giai đoạn bootstrap | `loader.path`, `loader.main`, `loader.home`, tùy chọn loader |
| `application.properties` | Spring Boot Environment/Config Data **sau khi main chạy** | `server.port`, `spring.profiles.active`, datasource, logging, v.v. |

Đặt `loader.path=lib` vào `application.properties` rồi kỳ vọng PropertiesLauncher đọc như cấu hình loader là cách **không nên dựa vào** trong thiết kế mới. Hãy tách rõ file launcher và cấu hình ứng dụng.

Để Spring Boot nạp application config ngoài JAR, dùng cơ chế được Spring Boot hỗ trợ, ví dụ:

```bash
java -Dloader.path=/opt/loader-demo/lib \
  -jar /opt/loader-demo/app.jar \
  --spring.config.additional-location=optional:file:/opt/loader-demo/config/
```

`--spring.config.additional-location` là **application argument** và Spring xử lý sau khi main đã chạy. Nó không thay đường dẫn JAR của loader. Thư mục `config` phải chứa cấu hình Spring được đặt tên phù hợp, ví dụ `application.properties`.

**Bảo mật:** nếu `loader.properties` hoặc `application.properties` chứa thông tin nhạy cảm, đặt ngoài Git/JAR và cấp quyền file tối thiểu. Tuy nhiên, chỉ vì có `loader.path` không có nghĩa mọi secrets an toàn: bất kỳ JAR mở rộng nào cũng có thể đọc dữ liệu/process env khi chạy trong cùng JVM.

## 9. Chọn nguồn cấu hình: -D, environment, loader.properties hay manifest

Ba cách thông dụng nhất cho `loader.path`:

```bash
# Cách 1: Java system property
java -Dloader.path=/opt/loader-demo/lib -jar /opt/loader-demo/app.jar

# Cách 2: Environment variable (Bash)
LOADER_PATH=/opt/loader-demo/lib java -jar /opt/loader-demo/app.jar

# Cách 3: loader.properties ở location tường minh
java -Dloader.config.location=file:/opt/loader-demo/config/loader.properties \
  -jar /opt/loader-demo/app.jar
```

Chọn **một nguồn chủ đạo** cho mỗi deployment để tránh xung đột. Nếu nhiều nguồn cùng chứa `loader.path` hoặc `loader.main`, việc hệ thống chọn giá trị nào phụ thuộc quy tắc ưu tiên của PropertiesLauncher phiên bản đang chạy; không mặc định quy tắc ưu tiên của Spring Boot Application Environment sẽ được áp dụng cho launcher. Cách kiểm tra đáng tin cậy là xem manifest, lệnh JVM, environment và endpoint của ví dụ.

Một cách khai báo manifest `Loader-Path` hoặc `Start-Class` ở build time có thể hữu ích khi mọi môi trường có cùng layout, nhưng khi đã dùng Spring Boot Maven plugin nên cấu hình **mainClass/layout trong plugin**, không sửa manifest thủ công sau khi repackage. Sửa file JAR sau khi ký/checksum còn làm hỏng tính toàn vẹn artifact.

### 9.1. Dấu phẩy trong loader.path, dấu phân cách của CLASSPATH

`loader.path` dùng **dấu phẩy** để tách nhiều mục. Không dùng nhầm dấu hai chấm `:` của Unix classpath hoặc dấu chấm phẩy `;` của Windows classpath:

```properties
loader.path=/opt/loader-demo/lib,/opt/loader-demo/plugins
```

Đây không phải:
```properties
loader.path=/opt/loader-demo/lib:/opt/loader-demo/plugins
```

Với các tên thư mục hoặc JAR chứa dấu cách, cần đặt giá trị đúng trong file properties hoặc escape/quote phù hợp shell; ưu tiên path triển khai ổn định không có ký tự đặc biệt, khoảng trắng không cần thiết hoặc dấu phẩy trong tên.

### 9.2. Classpath order và class trùng tên

Khi `loader.path` có nhiều mục, các mục trước thường được ưu tiên hơn mục sau theo contract của launcher. Nhưng đừng dựa vào class shadowing để “vá” dependency:

- Hai JAR chứa cùng `com.example.Util` có thể gây chọn phiên bản sai, `NoSuchMethodError` hoặc `LinkageError`.
- Dependency nằm trong `BOOT-INF/lib` có thể đã được loader dùng ở startup; không mặc định external JAR sẽ ghi đè an toàn.
- Resource trùng tên (ví dụ `META-INF/services/...`) có thể có cơ chế đọc khác với class lookup thông thường.
- Dùng phiên bản Spring Boot/Java không khớp có thể gây lỗi bytecode và dependency APIs.

Với plugin architecture, nên định nghĩa API/SPI nhỏ, quản lý compatibility và đóng version rõ. Nếu cần isolation thật sự giữa các plugin không tin cậy, **một classloader chung của PropertiesLauncher là không đủ**; cân nhắc cách ly bằng process/container riêng hoặc nền tảng plugin có classloader policy rõ ràng.

## 10. Khác biệt giữa loader.main và SpringApplication

`loader.main` là **lớp chứa main** được launcher chọn. Lớp ấy có thể gọi `SpringApplication.run(...)`, nhưng không bắt buộc.

Ví dụ demo minh chứng:

- Không chỉ định `loader.main`: launcher đọc `Start-Class` và chạy `LoaderDemoApplication`, HTTP server lên.
- `loader.main=...AlternateMain`: launcher chạy `AlternateMain`, chỉ in dòng console, không có Spring context/web server.
- `loader.main=...MissingMain`: launcher không tìm được class, build vẫn có thể thành công nhưng **runtime fail**.
- Nếu main được chọn nằm trong external JAR, phải bảo đảm external JAR đã được `loader.path` nạp trước khi gọi main.

Trong một ứng dụng nhiều entry points, dùng `loader.main` để chuyển giữa các chế độ chạy **chỉ khi thiết kế có chủ đích**. Không sử dụng nó để “chọn controller” hoặc “đổi Spring profile”; dùng `--spring.profiles.active=...`, biến môi trường `SPRING_PROFILES_ACTIVE` hay file Spring config cho profile.

**Phân biệt các thời điểm:**

| Thay đổi | Có cần rebuild JAR? | Có cần restart JVM? |
| --- | --- | --- |
| Đổi `loader.path` ở lệnh chạy cho phiên mới | Không | Có, vì classpath xây khi startup |
| Đổi `loader.main` cho phiên mới | Không | Có, vì main được chọn khi startup |
| Cập nhật nội dung external JAR | Không cần rebuild app JAR | Thông thường có, để nạp class/version mới |
| Đổi `<layout>ZIP</layout>` của Boot plugin | **Có** | Có, chạy artifact mới |
| Đổi `<mainClass>` để thay Start-Class trong manifest | **Có** | Có |
| Đổi `--server.port`, `SPRING_PROFILES_ACTIVE` | Không | Thường có; app đọc config khi startup |

`loader.main` không phải một lựa chọn hot reload có thể thay main trong JVM đang chạy. Khi cần tác vụ batch riêng, cân nhắc đóng gói module/ứng dụng phù hợp thay vì để một artifact có nhiều main phức tạp khó kiểm soát.

## 11. Spring Boot Maven Plugin: ZIP/DIR layout và repackage

Maven lifecycle cho ví dụ:

```text
mvn clean package
    |
    +-- compile Java source
    +-- test (nếu có)
    +-- maven-jar-plugin:jar tạo source JAR
    +-- spring-boot-maven-plugin:repackage
          |
          +-- đưa application classes vào BOOT-INF/classes
          +-- đưa dependency JAR vào BOOT-INF/lib
          +-- thêm Boot Loader classes
          +-- dùng layout ZIP => Main-Class PropertiesLauncher
```

`ZIP` / `DIR` của Boot Maven Plugin là layout tương tự JAR nhưng khởi động bằng `PropertiesLauncher`. `NONE` là kiểu layout khác không có bootstrap loader; không dùng `NONE` nếu vẫn muốn `java -jar` tự động nạp nested dependencies bằng PropertiesLauncher.

Đoạn plugin tối thiểu nếu đã có Spring Boot starter parent và app main rõ ràng:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <layout>ZIP</layout>
                <mainClass>com.example.loader.LoaderDemoApplication</mainClass>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là đoạn POM, không phải một file `pom.xml` đầy đủ. Với starter parent, **không cần khai báo goal repackage thêm lần nữa**. Nếu không có starter parent, phải khai báo plugin version, execution repackage trong phase `package` và compiler Java phù hợp.

### Với Gradle thì sao?

Khái niệm Boot Loader **không phụ thuộc Maven**, nhưng cách Gradle cấu hình task `bootJar` khác Maven plugin. Không chép nguyên XML `<layout>ZIP</layout>` vào `build.gradle` hoặc `build.gradle.kts`. Khi dùng Gradle, kiểm tra hướng dẫn đúng version cho `BootJar`/manifest và cách tạo executable archive để `Main-Class` thật sự là `PropertiesLauncher`. Các thao tác `loader.path`, `loader.main` ở **JVM runtime** chỉ hoạt động nếu file JAR cuối có launcher tương ứng. Quan sát `META-INF/MANIFEST.MF` là phép kiểm chứng chung cho mọi build tool.

## 12. Triển khai thực tế trên VM, Docker và Kubernetes

### 12.1. VM/host: layout ngoài JAR ổn định

Một cấu trúc triển khai rõ ràng:

```text
/opt/loader-demo/
├── app.jar                     # cố định theo release
├── lib/
│   └── greeting-extension.jar # được kiểm định, version rõ
├── config/
│   ├── loader.properties
│   └── application.properties
└── logs/                       # runtime logs theo cấu hình riêng
```

`loader.properties`:

```properties
loader.path=lib
loader.main=com.example.loader.LoaderDemoApplication
```

Lệnh khởi động:

```bash
java \
  -Dloader.home=/opt/loader-demo \
  -Dloader.config.location=file:/opt/loader-demo/config/loader.properties \
  -jar /opt/loader-demo/app.jar \
  --spring.config.additional-location=optional:file:/opt/loader-demo/config/
```

Đường `loader.home` và `loader.config.location` là **JVM options đặt trước `-jar`**. Spring application option `--spring.config.additional-location` đặt **sau tên JAR**, vì nó được chuyển vào `main(String[] args)`.

Các file dưới `lib` nên do quy trình build/release có quyền kiểm soát đưa vào, không phải thư mục cho người dùng bất kỳ upload. Nếu thay một JAR đang được classloader dùng, nên triển khai bằng artifact bất biến và rolling restart có kiểm soát, tránh sửa file JAR ngay giữa phiên JVM đang chạy.

### 12.2. Docker: đóng app cố định, mount thư mục ngoài

Dockerfile minh họa với JAR build từ Maven ở mục 5:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /opt/app
COPY target/loader-demo-0.0.1-SNAPSHOT.jar /opt/app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-Dloader.path=/opt/app/extensions", "-jar", "/opt/app/app.jar"]
```

Build image:

```bash
mvn -B -ntp clean package
docker build -t loader-demo:dev .
```

Giả định `external-libs/greeting-extension.jar` đã tạo ở mục 6. Chạy container và **mount folder chỉ đọc**:

```bash
docker run --rm \
  -p 127.0.0.1:8080:8080 \
  -v "$PWD/external-libs:/opt/app/extensions:ro" \
  loader-demo:dev
```

Nếu dùng Bash với Docker daemon/host setup hỗ trợ volume mount này, request `curl -fsS 'http://localhost:8080/greet?name=Lan'` kỳ vọng **`external:Lan`**. Nếu volume không có JAR tương thích, kết quả **`builtin:Lan`**. Trên Windows PowerShell cần điều chỉnh cú pháp đường dẫn host và nối dòng. Đây là ví dụ môi trường **development**, không bao gồm networking/secret/repository policy của production.

Điểm quan trọng:

- `-Dloader.path=/opt/app/extensions` được truyền trực tiếp tới JVM ứng dụng (khác Gradle `-D` trên build JVM).
- Mount `:ro` hạn chế ghi đè file extension từ container; tuy nhiên phải bảo vệ nguồn JAR trước khi mount.
- Khởi động từ image vẫn phải có `Main-Class=PropertiesLauncher`; thêm `-Dloader.path` vào image của `JarLauncher` không giải quyết yêu cầu.
- Container image phải có Java runtime tương thích và `app.jar` thực sự là executable Boot archive.
- Khi thay extension JAR, cần restart container để launcher dựng classpath mới.

### 12.3. Kubernetes: lựa chọn an toàn

Trong Kubernetes, có thể mount một volume **chỉ đọc** chứa external JAR và đưa `-Dloader.path` vào JVM command hoặc `JAVA_TOOL_OPTIONS` của container ứng dụng. Tuy nhiên, đặt `JAVA_TOOL_OPTIONS` bừa ở mức cả build agent hoặc pod nhiều tiến trình có thể ảnh hưởng JVM khác. Nên cấu hình trực tiếp entrypoint của **application container**.

Một đoạn `containers` minh họa, **chưa phải Kubernetes Deployment đầy đủ**:

```yaml
containers:
  - name: app
    image: registry.example.org/loader-demo:dev
    command: ["java"]
    args:
      - "-Dloader.path=/opt/app/extensions"
      - "-jar"
      - "/opt/app/app.jar"
    volumeMounts:
      - name: extensions
        mountPath: /opt/app/extensions
        readOnly: true
```

Cần cung cấp `volumes` tương ứng và nguồn artifact được phê duyệt. Không coi ConfigMap là nơi phù hợp cho các binary JAR tùy ý kích thước lớn; volume/image được quản lý theo quy trình release thường có kiểm soát tốt hơn. Khi dùng nhiều replica, mọi pod phải nhận cùng extension version (digest/checksum) và được restart/rollout nhất quán. Không có cơ chế tự động hot reload chỉ nhờ mount JAR mới.

## 13. Bảo mật và rủi ro classpath mở rộng

`loader.path` cho phép tiến trình nạp **mã Java bổ sung**. Điều này làm tăng linh hoạt nhưng cũng mở thêm bề mặt tấn công:

1. **Chỉ dùng artifact có nguồn gốc tin cậy:** repository nội bộ được phê duyệt, checksums/signatures phù hợp, kiểm tra SBOM và vulnerability theo chính sách.
2. **Không cho người dùng cuối ghi vào thư mục extension:** JAR có thể thực thi mã bên trong process với quyền của JVM, không chỉ đọc dữ liệu thụ động.
3. **Giới hạn quyền file:** đặt file/volume read-only khi thích hợp; tài khoản chạy ứng dụng không có quyền sửa JAR.
4. **Không dùng external path để “vá nóng” dependency bảo mật mà không có test:** classpath precedence và binary compatibility có thể làm crash hoặc thay đổi hành vi.
5. **Version pinning:** ghi rõ extension version và checksum cùng bản build app; deployment phải được tái tạo được.
6. **Kiểm thử compatibility:** class Java target version, plugin API, dependency transitive và các class trùng package/name.
7. **Không tin rằng PropertiesLauncher sandbox plugin:** các JAR cùng JVM có thể gọi network, filesystem và các API khác theo quyền process; cần isolation mạnh thì chạy ở process/container tách biệt.
8. **Không đưa secret vào loader.properties nếu không cần:** loader settings chỉ chọn classpath/main. Spring runtime secrets nên qua secret manager/env riêng được bảo vệ.
9. **Theo dõi mọi thay đổi ngoài JAR:** vì app.jar checksum không đổi mà external JAR có thể đổi, CI/CD phải lưu release manifest gồm cả extension artifact.
10. **Rollback rõ ràng:** giữ phiên bản JAR ngoài trước và quy trình restart, rollback config/JAR theo bộ; tránh live-edit nhiều pod đồng thời.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `-Dloader.path=...` không có tác dụng | Archive dùng `JarLauncher` chứ không phải `PropertiesLauncher` | `unzip -p app.jar META-INF/MANIFEST.MF`; cấu hình `layout=ZIP` và rebuild |
| `NoClassDefFoundError` hoặc `ClassNotFoundException` cho extension | `loader.path` sai, thiếu JAR/class, path tương đối sai home, class nằm trong JAR sai | `jar tf extension.jar`, kiểm tra `-Dloader.home`, đường dẫn thực và môi trường container |
| Controller vẫn trả `builtin:Lan` | Reflection không thấy class extension | So sánh chạy không path/có path; kiểm tra đúng `com/example/extra/GreetingExtension.class` |
| Controller trả HTTP 500 sau khi có JAR | Class có mặt nhưng method signature, dependency hoặc reflective invocation lỗi | Xem cause của `IllegalStateException`/`InvocationTargetException` và version extension |
| `loader.main` không đổi main | Archive không dùng PropertiesLauncher, sai nguồn property hoặc tên class | Đọc Main-Class, thử `java -Dloader.main=... -jar app.jar` |
| `Main class not found` | `loader.main` sai package, class không nằm trên classpath | `jar tf` của BOOT-INF/classes hoặc external JAR; kiểm tra dấu chấm/viết hoa |
| Có hai main class, build Maven fail | Plugin không tự phát hiện duy nhất main | Thêm `<mainClass>...LoaderDemoApplication</mainClass>` trong Boot plugin |
| `java -jar app.jar --loader.path=lib` không nạp JAR | `--loader.path` được truyền như argument của application, không phải JVM loader property | Đặt `-Dloader.path=lib` **trước** `-jar` hoặc dùng `LOADER_PATH` |
| `loader.properties` không được đọc | Đặt sai nơi, config.name/location sai, nhầm với Spring `application.properties` | Dùng `-Dloader.config.location=file:/absolute/path/loader.properties` |
| Relative path hoạt động trên dev nhưng fail ở systemd/CI | CWD khác, `loader.home` mặc định theo `user.dir` | Đặt `-Dloader.home=/opt/app` và path cố định |
| Thay JAR ngoài nhưng app dùng version cũ | Classloader được dựng từ lúc JVM start; process chưa restart | Rollout/restart JVM hoặc container |
| `NoSuchMethodError` / `LinkageError` | Trùng class hoặc dependency binary incompatibility giữa JAR embedded và external | Kiểm tra version, danh sách jar, loại trùng, test compatibility |
| `UnsupportedClassVersionError` | Extension compile bằng Java mới hơn JVM runtime | Kiểm tra `java -version` và compile `javac --release 17` khi phù hợp |
| Đọc resource bằng system classloader không thấy | Nested JAR/classpath dùng launcher classloader | Dùng context classloader hoặc API framework tương ứng |
| HTTP endpoint không mở port | `loader.main` trỏ AlternateMain thay vì Spring app; hoặc app startup fail | Xem launcher selection và startup logs |
| Docker nạp extension trên host nhưng không trong container | Path phải là đường **bên trong container** và mount đúng | Kiểm tra volume mount, readOnly, `-Dloader.path` |
| Lỗi permission ở thư mục lib | User chạy JVM không đọc được external JAR/dir | Đảm bảo read/execute permission phù hợp cho user của JVM |
| Nạp nhầm file loader.properties của cwd | Có nhiều file cùng tên ở những vị trí được tìm | Dùng config location tuyệt đối, loại file cũ không cần thiết |
| Classpath thay đổi giữa replica | Volume/image chứa extension không đồng nhất | Pin artifact digest, rollout theo release nhất quán |

### Checklist debug có hệ thống

1. Kiểm tra **phiên bản Java/Spring Boot**: `java -version`, Boot plugin version/parent.
2. Kiểm tra **artifact đang chạy**: đúng đường dẫn `target/...jar` hay image digest?
3. Đọc **`META-INF/MANIFEST.MF`**: `Main-Class` có là `PropertiesLauncher` không? `Start-Class` có đúng main mặc định không?
4. Đọc **`BOOT-INF/classes` / `BOOT-INF/lib`** và chính external JAR bằng `jar tf`.
5. Xem đúng **lệnh startup JVM**, xác nhận `-Dloader.path` và `-Dloader.main` đặt trước `-jar`.
6. Nếu dùng file, chỉ rõ **`loader.config.location`**; nếu dùng đường tương đối, xác nhận `loader.home`.
7. Xác nhận **thư mục mở rộng/JAR tồn tại trong filesystem của chính tiến trình** (đặc biệt Docker/Kubernetes).
8. Tái hiện bằng endpoint demo `/greet?name=Lan`: `builtin:Lan` không có extension; `external:Lan` khi nạp thành công.
9. Nếu extension có nhưng app lỗi, xem stack trace của linkage/reflection/config, không chỉ kết luận loader.path “không chạy”.
10. Xác nhận runtime config Spring Boot và loader config không bị trộn; Spring profile/server port không thay đổi classpath bootstrap.
11. Kiểm thử artifact version và restart có kiểm soát; không tùy tiện xóa dependency cache hoặc rebuild mọi thứ để che lỗi path.

### Lệnh kiểm tra ngắn

```bash
mvn -B -ntp clean package

# Xem manifest của app:
unzip -p target/loader-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF

# Xem main class nằm trong executable JAR:
jar tf target/loader-demo-0.0.1-SNAPSHOT.jar |
  grep -E '^(BOOT-INF/classes|org/springframework/boot/loader/launch)'

# Xem class trong JAR ngoài:
jar tf external-libs/greeting-extension.jar

# Test không có extension:
java -jar target/loader-demo-0.0.1-SNAPSHOT.jar

# Test có extension (sau khi dừng app ở lệnh trước):
java -Dloader.path=external-libs -jar target/loader-demo-0.0.1-SNAPSHOT.jar

# Test main class khác (sau khi dừng ứng dụng web):
java -Dloader.main=com.example.loader.AlternateMain \
  -jar target/loader-demo-0.0.1-SNAPSHOT.jar demo
```

Những dòng `jar tf`/`unzip`/`grep` dùng công cụ CLI của JDK và Unix; `grep`/`unzip` không phải lệnh mặc định trên mọi bản Windows. Trên PowerShell có thể thay bước lọc bằng `Select-String`, và dùng công cụ ZIP/JAR tương đương để kiểm tra manifest. Các lệnh `java -jar` web server ở trên **chạy lâu dài**, nên phải dừng JVM trước khi thực thi lệnh startup tiếp theo; chúng không phải chuỗi lệnh Bash chạy tự động hết từ đầu đến cuối.

## 15. Những hiểu lầm cần tránh

1. **“Chỉ cần thêm loader.path vào application.properties.”** Sai tư duy: loader.path của PropertiesLauncher được quyết định trước Spring configuration processing. Tách loader.properties khỏi Spring config data.
2. **“JarLauncher và PropertiesLauncher đều dùng loader.path.”** Không: JarLauncher dùng classpath layout cố định, còn PropertiesLauncher hỗ trợ mở rộng.
3. **“layout ZIP tạo file ZIP không chạy được bằng java -jar.”** Không: với Boot Maven plugin nó vẫn có thể tạo JAR thực thi, khác nhau ở launcher được chọn.
4. **“loader.main thay cấu hình server.port hoặc Spring profile.”** Không: loader.main chỉ lựa chọn Java main class.
5. **“Nếu có Start-Class thì không thể override main.”** Không: PropertiesLauncher có thể đọc loader.main và chọn một main khác khi class có sẵn.
6. **“Thêm external JAR vào thư mục sau khi server start là đủ.”** Không đảm bảo: classpath xây khi JVM bootstrap; nên restart để nạp artifact mới.
7. **“Dùng -cp cùng -jar sẽ mở rộng classpath cho Boot archive.”** Không nên dựa vào điều đó; dùng cơ chế PropertiesLauncher và loader.path.
8. **“External JAR an toàn vì không đóng trong app.jar.”** Sai: nó có quyền thực thi trong cùng JVM; phải quản trị nguồn, checksum và quyền.
9. **“Chạy từ thư mục nào cũng resolve path tương đối như nhau.”** Không: loader.home/user.dir và path thực tế có thể khác.
10. **“Tệp loader.properties có thể được nạp nhờ loader.path trỏ tới thư mục chứa nó.”** Không nên dùng cách suy luận vòng tròn: cấu hình launcher cần được tìm **trước** khi xác định classpath mở rộng.
11. **“Một app JAR bất biến đồng nghĩa deployment bất biến.”** Không khi runtime tải JAR ngoài có thể thay đổi; cần pin cả extension artifact.
12. **“PropertiesLauncher là sandbox đa plugin.”** Không: các plugin có thể chia sẻ classloader/process và gây xung đột hoặc lộ secret nếu thiếu kiểm soát.
13. **“Maven package tự tạo PropertiesLauncher.”** Không nếu layout mặc định là JAR; phải chọn layout phù hợp và kiểm tra manifest.
14. **“Lỗi ClassNotFound luôn do Maven thiếu dependency.”** Có thể class nằm trong external JAR nhưng loader.path sai hoặc file permission không hợp lệ.
15. **“Main-Class trong manifest phải là SpringApplication class.”** Đối với Boot executable archive, `Main-Class` là Boot launcher; app main nằm trong `Start-Class`, trừ khi launcher override qua loader.main.

## 16. Quy trình áp dụng vào dự án thật

1. Xác định **nhu cầu hợp lệ**: có thực sự cần nạp dependency/JAR bên ngoài hoặc đổi main runtime không? Nếu không, `JarLauncher` đơn giản hơn.
2. Chọn Spring Boot version và plugin version thống nhất; dùng Java runtime được hỗ trợ.
3. Với Maven và Spring Boot starter parent, cấu hình `spring-boot-maven-plugin` với `<layout>ZIP</layout>`, `<mainClass>...` nếu có nhiều entry points.
4. Chạy `mvn clean package`, kiểm tra manifest **`Main-Class=PropertiesLauncher`**.
5. Chuẩn bị thư mục external JAR đã pin version; kiểm tra `jar tf`, runtime compatibility và quyền đọc.
6. Chọn nguồn loader setting rõ ràng: `-Dloader.path`, `LOADER_PATH` hoặc file `loader.properties` có `loader.config.location` tường minh.
7. Đặt `loader.home` nếu dùng đường dẫn tương đối, đặc biệt khi chạy qua systemd, Docker, Kubernetes hoặc CI.
8. Nếu cần chọn entry point khác, xác định class chính xác và truyền `loader.main` khi khởi động; kiểm tra không gọi nhầm main thay thế ở môi trường production.
9. Kiểm thử launcher bằng smoke test có/không external JAR và so sánh đầu ra, sau đó kiểm thử logic thực tế.
10. Bảo vệ thư mục JAR, checksum, CI/CD release manifest, rolling restart và phương án rollback; không dùng loader.path để nạp mã do người dùng upload.
11. Giữ riêng **loader configuration**, **Spring Boot runtime configuration** và **build tool configuration** để không lẫn phạm vi áp dụng.
12. Khi nâng cấp major Spring Boot, xác nhận lại launcher class package, layout semantics, file lookup và classpath behavior từ tài liệu của **đúng phiên bản**.

## 17. Tài liệu chính thức

- Spring Boot 3.5 – [Launching Executable Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html): phân biệt JarLauncher, WarLauncher, PropertiesLauncher, Main-Class và Start-Class.
- Spring Boot 3.5 – [PropertiesLauncher Features](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/property-launcher.html): loader.path, loader.home, loader.main và các nguồn cấu hình launcher.
- Spring Boot 3.5 – [PropertiesLauncher Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/loader/launch/PropertiesLauncher.html): API và mô tả các property của launcher.
- Spring Boot 3.5 Maven Plugin – [Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): repackage, ZIP/DIR layout và manifest.
- Spring Boot 3.5 – [The Executable Jar Format](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html): nested JAR, classloader và các ràng buộc định dạng.
- Spring Boot – [Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): so sánh với cấu hình ứng dụng sau bootstrap.
- Java SE 17 – [The Java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): quy tắc `java -D... -jar ...` và Java runtime options.

**Kết luận:** `PropertiesLauncher` là một Boot Loader có classpath/entry point có thể điều khiển tại lúc khởi động. `loader.path` **bổ sung vị trí class/JAR**, `loader.main` **chọn main class**, còn `loader.home` và file `loader.properties` giúp triển khai đường dẫn ổn định. Trong Spring Boot Maven Plugin, **`layout=ZIP`** tạo JAR dùng launcher này; phải kiểm tra **manifest** thay vì chỉ suy đoán từ file extension. Dùng external JAR có kiểm soát, version/checksum rõ ràng và restart JVM khi thay đổi classpath để giữ build/deployment tái lập được.