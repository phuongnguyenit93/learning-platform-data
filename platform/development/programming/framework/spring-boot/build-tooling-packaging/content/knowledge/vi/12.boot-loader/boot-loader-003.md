# Quan hệ giữa manifest, lớp khởi chạy và classpath ứng dụng

Trong một ứng dụng Spring Boot đóng gói thành **executable JAR**, lệnh `java -jar app.jar` tưởng như chỉ cần một tệp. Nhưng để tìm được `main()` của ứng dụng và các class thuộc Spring, Jackson, Tomcat…, Java cần biết **entry point ở đâu** và **classpath thực sự gồm những gì**. Spring Boot giải quyết bài toán này bằng ba thành phần phối hợp chặt chẽ:

1. **Manifest (`META-INF/MANIFEST.MF`):** chứa `Main-Class` — lớp mà Java launcher sẽ gọi đầu tiên — và thường có `Start-Class` — lớp chính của *ứng dụng*.
2. **Boot Loader (`JarLauncher`, `WarLauncher` hoặc `PropertiesLauncher`):** khởi chạy trước ứng dụng, hiểu cấu trúc archive của Spring Boot, thiết lập classloader/classpath thích hợp và chuyển quyền điều khiển tới `Start-Class`.
3. **Classpath ứng dụng:** gồm những lớp/resource của chính dự án và những JAR runtime mà loader tìm được từ các vị trí bên trong archive hoặc những vị trí bổ sung được cấu hình hợp lệ.

**Điểm cần nhớ ngay:** Với Spring Boot 3.3.13, một executable JAR thông thường có `Main-Class: org.springframework.boot.loader.launch.JarLauncher`, còn `Start-Class: dev.example.bootloader.BootLoaderDemoApplication` là ví dụ lớp do người phát triển viết. **`Main-Class` và `Start-Class` không phải một.** Loader không phải Spring `ApplicationContext`; nó làm công việc tìm và nạp class *trước khi* `SpringApplication.run(...)` có thể thực thi.

Bài học cố định ví dụ ở **Java 17, Spring Boot 3.3.13** và cách đóng gói Maven/Gradle tương ứng. Các đường dẫn và package names được chọn để tái hiện, không đại diện cho phiên bản mới nhất của tất cả công cụ.

## 1. Hai tầng khởi động: JVM Launcher và Spring Boot Loader

Trước hết hãy phân biệt rõ hai tên rất giống nhau:

- **Java launcher** là chương trình `java` của JDK/JRE. Khi chạy `java -jar ...`, nó mở archive và đọc `Main-Class` theo chuẩn Java JAR.
- **Spring Boot Loader** là các class Java do Spring Boot đưa vào executable archive, ví dụ `org.springframework.boot.loader.launch.JarLauncher`. Nó chính là `Main-Class` mà Java launcher chạy, sau đó mới gọi class ứng dụng.

Luồng cho Spring Boot 3.3 executable JAR:

```text
Lệnh trong terminal
java -jar target/bootloader-demo-1.0.0.jar --spring.profiles.active=dev
     |
     v
[1] JVM / Java launcher
    Mở JAR -> đọc META-INF/MANIFEST.MF
    Main-Class = org.springframework.boot.loader.launch.JarLauncher
     |
     v
[2] Spring Boot JarLauncher
    Nhận diện BOOT-INF/classes và BOOT-INF/lib/*.jar
    Thiết lập classloader và classpath có nested JARs
    Đọc Start-Class = dev.example.bootloader.BootLoaderDemoApplication
     |
     v
[3] BootLoaderDemoApplication.main(String[] args)
    SpringApplication.run(BootLoaderDemoApplication.class, args)
     |
     v
[4] Spring Boot application startup
    Nạp configuration/profile, auto-configuration, beans, web server
     |
     v
[5] HTTP endpoint sẵn sàng phục vụ request
```

Chính giai đoạn **[2]** là lý do một executable Boot JAR có thể giữ thư viện dưới dạng các JAR lồng trong nó. `Main-Class` giúp Java vào đúng *bootstrap loader*; `Start-Class` giúp bootstrap loader tìm đúng *main method của ứng dụng*; **classpath** giúp main method và framework tải được những lớp mà chúng sử dụng.

Nếu một mắt xích bị sai:

- Không có `Main-Class`: `java -jar` không tìm được entry point.
- `Main-Class` trỏ tới tên lớp không có trong JAR/root classpath: Java báo không tải được main class.
- Loader có mặt nhưng `Start-Class` sai: loader khởi động nhưng không tìm được main class ứng dụng.
- Cả hai manifest attributes đúng nhưng classpath thiếu `spring-web`, `jackson-databind` hoặc module khác: ứng dụng vẫn có thể lỗi `ClassNotFoundException`/`NoClassDefFoundError` khi chạy.

## 2. Manifest cung cấp điều gì, và không cung cấp điều gì?

`META-INF/MANIFEST.MF` là tệp metadata chuẩn trong JAR. Một đoạn manifest minh họa cho Boot 3.3:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.bootloader.BootLoaderDemoApplication
Spring-Boot-Version: 3.3.13
Spring-Boot-Classes: BOOT-INF/classes/
Spring-Boot-Lib: BOOT-INF/lib/
```

Dòng trên là những **thuộc tính tiêu biểu**; các plugin có thể thêm `Build-Jdk-Spec`, metadata layer/classpath index, implementation version... Không dựa vào việc manifest thực tế phải giống từng byte hoặc thứ tự dòng. JAR manifest còn có quy tắc ngắt dòng dài; hãy dùng công cụ đọc manifest hợp lệ khi phân tích.

| Thuộc tính | Ai tiêu thụ? | Vai trò |
| --- | --- | --- |
| `Manifest-Version` | Công cụ chuẩn của định dạng JAR | Phiên bản định dạng manifest, **không phải version Spring Boot** |
| `Main-Class` | JVM Java launcher khi dùng `-jar` | Lớp được gọi **đầu tiên**; với Boot JAR mặc định là `JarLauncher` |
| `Start-Class` | Spring Boot Loader | Lớp application main do người phát triển viết |
| `Spring-Boot-Version` | Metadata do công cụ đóng gói Boot đưa vào | Cho biết version Boot dùng khi đóng gói |
| `Spring-Boot-Classes`/`Spring-Boot-Lib` | Metadata mô tả layout đóng gói | Vị trí tương ứng của classes và nested libraries, không phải manifest `Class-Path` của Java |
| `Class-Path` (nếu có trong JAR thường) | Java launcher/standard manifest classpath | Tham chiếu thư viện **bên ngoài** theo quy tắc Java manifest; không biến nested BOOT-INF/lib thành Java classpath tự động |

**Quan trọng:** `Start-Class` **không phải** thuộc tính mà Java launcher chuẩn sử dụng để chọn `main()`. Nếu không có Spring Boot Loader hoặc một bootstrap loader hiểu `Start-Class`, thêm dòng đó vào manifest không khiến Java tự động tìm class ứng dụng.

### Manifest không thay thế dependency graph hoặc runtime configuration

Manifest không tự download Maven dependencies, không quyết định Spring bean nào được tạo, không thay `application.yml` hay secret manager. Nó chỉ cung cấp một phần **hợp đồng khởi động**. Các tệp `application-dev.yml`, environment variables và `--spring.profiles.active` được Spring Boot xử lý **sau khi đã vào ứng dụng**, không dùng để tìm `JarLauncher`.

Nếu người dùng truyền:

```bash
java -jar target/bootloader-demo-1.0.0.jar --spring.profiles.active=prod
```

`--spring.profiles.active=prod` là **application argument** được chuyển vào `main(args)`; nó không đổi `Main-Class`, `Start-Class`, `BOOT-INF/lib` hay cách JVM đọc manifest.

## 3. Spring Boot executable JAR sắp xếp classes và dependencies thế nào?

Một JAR thông thường có thể chứa compiled application class tại đường dẫn theo package ngay từ root:

```text
plain.jar
├── META-INF/MANIFEST.MF
└── dev/example/bootloader/BootLoaderDemoApplication.class
```

Còn Spring Boot **executable JAR** có layout đặc thù:

```text
bootloader-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   ├── launch/JarLauncher.class
│   └── ... các lớp Boot Loader khác
└── BOOT-INF/
    ├── classes/
    │   ├── dev/example/bootloader/
    │   │   ├── BootLoaderDemoApplication.class
    │   │   └── ProbeController.class
    │   └── message.txt
    ├── lib/
    │   ├── spring-boot-3.3.13.jar
    │   ├── spring-boot-autoconfigure-3.3.13.jar
    │   ├── spring-web-*.jar
    │   ├── jackson-databind-*.jar
    │   └── ... runtime dependencies khác
    ├── classpath.idx       (có thể có)
    └── layers.idx          (có thể có)
```

Những điểm đáng chú ý:

1. **Boot Loader classes** ở vị trí mà Java launcher có thể tìm khi gọi `Main-Class` trong archive.
2. **Classes/resources của ứng dụng** ở `BOOT-INF/classes/`, không ở classpath root của Java khi chạy `-cp myboot.jar`.
3. **Runtime dependencies** là các archive JAR riêng nằm bên trong `BOOT-INF/lib/`. Một JAR ngoài theo định dạng ZIP thông thường không làm các JAR con bên trong trở thành classpath entries của Java một cách tự động.
4. **JarLauncher** biết cấu trúc Boot, tạo classloader hiểu nested JARs và đưa app classes/dependencies vào đường tìm kiếm tài nguyên.
5. `classpath.idx` và `layers.idx` là metadata khác mục đích; chúng không phải hai tên thay thế cho `Main-Class`/`Start-Class`.

Đây là lý do **không thể đổi tên plain JAR thành boot JAR** hoặc chỉ chèn `Main-Class: ...JarLauncher` vào một file đã tồn tại rồi tin rằng nó có đầy đủ Boot Loader và nested layout.

### Tại sao giữ dependency dưới dạng nested JAR?

Giả sử `spring-web-6.x.jar` nằm trong `BOOT-INF/lib/`. Thay vì giải nén tất cả `.class` của Spring Web ra root, Boot giữ nó là một JAR riêng. Việc này giúp nhận diện thư viện, quản lý tài nguyên/class loader theo layout của Spring Boot và hỗ trợ việc phân lớp image.

Cơ chế thực thi phụ thuộc vào lớp giải quyết nested archive của Boot; trình đọc ZIP thông thường chỉ thấy nó là một **entry bên trong ZIP**, không tự đưa nó vào classpath. Spring Boot Loader sử dụng các tiện ích đọc archive và classloader để giải quyết chúng khi chạy.

**Không tự sửa ZIP nested JAR tùy tiện.** Theo hạn chế executable archive của Spring Boot, entry chứa nested JAR trong archive ngoài phải dùng ZIP method `STORED` để loader truy cập dữ liệu bên trong đúng cách; nội dung nested JAR có thể nén theo cơ chế riêng. Một chương trình repack ZIP tự phát có thể làm hỏng điều kiện này dù `jar tf` vẫn liệt kê được tên file.

## 4. Classpath của ứng dụng được tạo ra ở đâu?

**Classpath** là tập các nơi Java/classloader tìm class và resources: directory, JAR, module hoặc nguồn đặc thù mà một classloader hỗ trợ. Với ứng dụng Java thường, lập trình viên có thể đưa những nơi đó vào tham số `-cp`. Với Spring Boot executable JAR, chính launcher dựng phần classpath cần thiết.

### 4.1. Java classpath truyền thống

```bash
java -cp "app.jar:lib/*" dev.example.bootloader.BootLoaderDemoApplication
```

Lệnh trên là kiểu Linux/macOS. Với Windows, dấu phân tách classpath entries là `;`:

```powershell
java -cp "app.jar;lib/*" dev.example.bootloader.BootLoaderDemoApplication
```

Java tìm class ứng dụng ở root của `app.jar` và class thư viện từ các `.jar` trực tiếp trong thư mục `lib/`. Điều này phù hợp với **plain JAR + external dependencies**, nếu `app.jar` thực sự có lớp ở package root và mọi thư viện cần thiết đã được cung cấp.

### 4.2. Classpath của Spring Boot executable JAR

```bash
java -jar target/bootloader-demo-1.0.0.jar
```

Ở đây bạn **không** liệt kê từng dependency trên `-cp`. Java launcher tìm `JarLauncher` từ manifest; launcher lần lượt đưa `BOOT-INF/classes/` và nested libraries trong `BOOT-INF/lib/` vào classpath do Boot quản lý, sau đó gọi `Start-Class`.

**Trong chế độ `-jar` của Java, tham số `-cp`/`CLASSPATH` không được sử dụng theo cách khởi động `-cp`.** Vì vậy câu lệnh:

```bash
java -cp "external/*" -jar target/bootloader-demo-1.0.0.jar
```

không làm `external/*` tự xuất hiện trong Boot application classpath. Nếu cần thư viện ngoài archive, phải dùng cơ chế phù hợp như `PropertiesLauncher`, hoặc thay đổi cách đóng gói/chạy ứng dụng một cách có chủ đích.

### 4.3. Loader classpath khác dependency management

BOM/Maven/Gradle **quyết định version và tập artifact build cần resolve**. Build plugin **quyết định artifact nào thực sự được đóng gói**. `JarLauncher` **quyết định cách tìm và nạp artifact đã đóng gói**. Ba việc độc lập nhưng nối tiếp:

```text
pom.xml / build.gradle
    |
    | dependency resolution: xác định runtime dependencies
    v
spring-boot:repackage / bootJar
    |
    | đưa runtime jars vào BOOT-INF/lib
    | đưa compiled app vào BOOT-INF/classes
    | chèn loader và manifest
    v
executable JAR
    |
    | java -jar -> JarLauncher -> tạo runtime classpath
    v
SpringApplication.run -> application
```

Nếu `BOOT-INF/lib` thiếu một dependency vì scope/configuration sai, **loader không tự tải dependency đó qua Internet**. Nếu `BOOT-INF/lib` có nhiều bản một library, classpath ordering có thể quyết định bản được nhìn thấy; cần sửa dependency resolution/build thay vì “hy vọng loader tự chọn bản mới nhất”.

## 5. JarLauncher, WarLauncher và PropertiesLauncher: chọn đúng bootstrap

Spring Boot 3.3 có ba launcher tiêu biểu:

| Launcher | Main-Class trong manifest | Classpath/archive mà nó hướng tới | Khi nào dùng |
| --- | --- | --- | --- |
| **JarLauncher** | `org.springframework.boot.loader.launch.JarLauncher` | `BOOT-INF/classes/` và các nested JAR ở `BOOT-INF/lib/` | Executable **JAR** mặc định |
| **WarLauncher** | `org.springframework.boot.loader.launch.WarLauncher` | `WEB-INF/classes/`, `WEB-INF/lib/` và `WEB-INF/lib-provided/` | Executable **WAR** |
| **PropertiesLauncher** | `org.springframework.boot.loader.launch.PropertiesLauncher` | Boot application paths và đường dẫn bổ sung do `loader.path`/`LOADER_PATH` chỉ định | Khi cần thêm classpath locations ngoài archive |

**`JarLauncher`/`WarLauncher` có layout classpath tương đối cố định.** Không đặt `loader.path` rồi mặc định `JarLauncher` sẽ bắt đầu tìm thêm thư viện ngoài. `loader.path` là một tính năng của **`PropertiesLauncher`**, cần Boot archive được đóng gói/cấu hình để khởi chạy bằng launcher đó.

### Ví dụ WAR

Một executable WAR thường có:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/WarLauncher.class
WEB-INF/classes/dev/example/bootloader/BootLoaderDemoApplication.class
WEB-INF/lib/*.jar
WEB-INF/lib-provided/*.jar
```

Manifest có thể chỉ định:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: dev.example.bootloader.BootLoaderDemoApplication
```

`WEB-INF/lib-provided` lưu những dependency cần có khi WAR chạy kiểu executable nhưng không nên gây xung đột khi deploy vào servlet container ngoài. Ứng dụng WAR thực tế cần đúng `war` packaging, cấu hình server dependency và cơ chế bootstrap tương ứng. Không chuyển một Boot JAR thành WAR bằng cách đổi phần mở rộng.

### `PropertiesLauncher` và external libraries

Nếu có yêu cầu hợp lệ về plugin/library được cài ngoài JAR, `PropertiesLauncher` cho phép bổ sung thư mục/archive vào classpath:

```bash
java -Dloader.path=external-libs -jar target/bootloader-demo-1.0.0.jar
```

**Chỉ có tác dụng đúng ý khi manifest của JAR chỉ định `PropertiesLauncher`**. Với `JarLauncher` mặc định, đây không phải “công tắc universal add classpath”. Đường `external-libs` được giải quyết tương đối với cấu hình `loader.home`/working directory, và thư mục cần chứa các JAR thực tế. Đừng dùng nguồn classpath ngoài không tin cậy: một JAR độc hại trong đường nạp class có thể được JVM thực thi trong tiến trình ứng dụng.

Việc cấu hình `PropertiesLauncher` có thể thực hiện ở Maven bằng layout `ZIP` hoặc `DIR` (alias), và trong Gradle qua task manifest/Main-Class theo hướng dẫn plugin. Bài sẽ có fragment mẫu ở mục 9.

## 6. Bài thực hành Maven Spring Boot: quan sát manifest, classpath và classloader

Ta sẽ dùng một application đủ nhỏ để chạy được trên JDK 17, nhưng vẫn có một thư viện thực nằm trong `BOOT-INF/lib` để chứng minh classpath nested hoạt động. App cung cấp endpoint `/probe`:

- Đọc tệp resource `message.txt` ở `BOOT-INF/classes` thông qua **thread context classloader**.
- Yêu cầu classloader tải `com.fasterxml.jackson.databind.ObjectMapper`, một class từ thư viện Jackson được Spring Boot Web starter kéo vào.
- Trả về body cố định `message=loader-ready; jackson=true` để kiểm tra mà không phụ thuộc tên classloader hay URL nội bộ.

### 6.1. Cấu trúc dự án

```text
bootloader-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/bootloader/
    │   │   ├── BootLoaderDemoApplication.java
    │   │   └── ProbeController.java
    │   └── resources/
    │       └── message.txt
    └── test/
        └── java/dev/example/bootloader/
            └── ProbeControllerTest.java
```

### 6.2. POM đầy đủ

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>bootloader-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <mainClass>dev.example.bootloader.BootLoaderDemoApplication</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích:

- Parent `spring-boot-starter-parent` cung cấp dependency management và cấu hình plugin phù hợp, kể cả execution `repackage` khi Spring Boot Maven Plugin được khai báo trong `build/plugins`.
- Maven JAR Plugin tạo archive JAR thông thường theo lifecycle `package`; goal `spring-boot:repackage` thêm loader, nested libraries và manifest phù hợp, thay thế main artifact mặc định.
- `<mainClass>...BootLoaderDemoApplication</mainClass>` nói rõ main class ứng dụng mà **Boot plugin dùng khi đóng gói**, tương ứng `Start-Class`. Nó **không** làm `Main-Class` của executable JAR trỏ thẳng tới application class; `Main-Class` vẫn do layout/launcher quyết định.
- Nếu project **chỉ import `spring-boot-dependencies` BOM** thay vì dùng starter parent, BOM không tự bind plugin goal; cần khai báo version và execution `repackage` rõ ràng.
- Version Spring Boot 3.3.13 giúp tránh trộn tên package cũ của `JarLauncher` từ Spring Boot 2.x với tên mới có `.launch.`.

### 6.3. Java main class

Tệp `src/main/java/dev/example/bootloader/BootLoaderDemoApplication.java`:

```java
package dev.example.bootloader;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BootLoaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootLoaderDemoApplication.class, args);
    }
}
```

Tệp `src/main/java/dev/example/bootloader/ProbeController.java`:

```java
package dev.example.bootloader;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    @GetMapping("/probe")
    public String probe() throws IOException, ClassNotFoundException {
        ClassLoader loader = Thread.currentThread().getContextClassLoader();

        String message;
        try (InputStream input = loader.getResourceAsStream("message.txt")) {
            if (input == null) {
                throw new IllegalStateException("message.txt missing from classpath");
            }
            message = new String(input.readAllBytes(), StandardCharsets.UTF_8).trim();
        }

        Class<?> jackson = Class.forName(
                "com.fasterxml.jackson.databind.ObjectMapper",
                false,
                loader
        );

        return "message=" + message + "; jackson=" + (jackson != null);
    }
}
```

Tệp `src/main/resources/message.txt` có **một dòng**:

```text
loader-ready
```

Các bước trong `ProbeController` chỉ mang tính giáo dục:

1. `Thread.currentThread().getContextClassLoader()` lấy classloader mà framework/loader đã thiết lập cho luồng xử lý. Đây là cách phù hợp để tìm resources và class khi dùng nested JARs.
2. `getResourceAsStream("message.txt")` tìm resource trong **application classpath** — khi đóng gói Boot JAR, tài nguyên nằm dưới `BOOT-INF/classes/message.txt` nhưng vẫn được giải quyết bằng tên logic `message.txt`.
3. `Class.forName(..., false, loader)` yêu cầu classloader tìm `ObjectMapper`. Trong ví dụ Boot 3.3 với `spring-boot-starter-web`, Jackson có trong runtime dependency graph; nó thường nằm trong một nested JAR ở `BOOT-INF/lib`. `false` nghĩa là không bắt buộc khởi tạo class qua static initializer chỉ vì phép kiểm tra.
4. Kết quả HTTP là chuỗi cố định, không tiết lộ chi tiết đường file hoặc toàn bộ classpath của server. Trên production, không nên mở endpoint cho phép khách chọn bất kỳ class name và thử nạp class.

**Lưu ý về classloader:** `ClassLoader.getSystemClassLoader()` không đảm bảo nhìn thấy classes trong nested Boot JARs. Spring Boot documentation nhấn mạnh dùng **thread context classloader** khi thư viện cần nạp class động. Đừng hard-code tên concrete classloader: implementation có thể đổi giữa các release.

### 6.4. Kiểm thử Java

Tệp `src/test/java/dev/example/bootloader/ProbeControllerTest.java`:

```java
package dev.example.bootloader;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProbeControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void classpathResourceAndJacksonAreAccessible() throws Exception {
        mockMvc.perform(get("/probe"))
                .andExpect(status().isOk())
                .andExpect(content().string("message=loader-ready; jackson=true"));
    }
}
```

**Phạm vi bằng chứng:** Bài test xác nhận resource và Jackson class có thể được load trong **classpath của test runner**, không chứng minh bản executable archive được tái đóng gói hoàn toàn đúng. Vì vậy ở phần dưới bắt buộc chạy thêm `java -jar` và HTTP smoke test trên **chính JAR phát hành**.

## 7. Maven build: tạo artifact và quan sát đúng hai lớp khởi động

Trong thư mục `bootloader-demo`, với JDK 17 và Maven 3.9.x (hoặc Maven Wrapper phù hợp):

```bash
mvn -version
mvn clean verify
```

Nếu có Maven Wrapper, có thể thay `mvn` bằng `./mvnw`; trên Windows dùng `mvnw.cmd`.

Theo cấu hình POM ở mục 6, sau build thông thường có:

```text
target/bootloader-demo-1.0.0.jar
target/bootloader-demo-1.0.0.jar.original
```

- `bootloader-demo-1.0.0.jar` là **Spring Boot executable JAR** sau `repackage`.
- `.jar.original` là archive JAR trước khi Boot tái đóng gói, thường không có loader và không tự mang runtime dependencies. Nó là JAR gốc theo định dạng ZIP dù đuôi file kết thúc bằng `.original`.
- Nếu project dùng classifier hoặc custom plugin configuration, tên và cách attach artifact có thể khác; luôn kiểm tra output thực tế.

### 7.1. Kiểm tra manifest

Linux/macOS, nếu có `unzip`:

```bash
unzip -p target/bootloader-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Các dòng quan trọng cần tìm:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.bootloader.BootLoaderDemoApplication
```

Java `jar` tool cũng có thể trích xuất manifest ra một thư mục làm việc trống, nếu hệ thống không có `unzip`:

```bash
mkdir -p target/inspect-jar
cd target/inspect-jar
jar xf ../bootloader-demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

Sau lệnh `cd` ở ví dụ này, trở lại project root trước khi chạy lệnh `mvn` hoặc `java -jar target/...`.

**Chẩn đoán manifest:**

- `Main-Class` là `JarLauncher` và `Start-Class` là lớp của mình: đúng thiết kế executable JAR thông thường.
- `Main-Class` trỏ vào app class nhưng classes đã nằm ở `BOOT-INF/classes`: dấu hiệu có người sửa manifest hoặc task build sai.
- `Start-Class` trỏ lớp không tồn tại/không có `main(String[])`: cần sửa cấu hình main class của Boot plugin.
- Chỉ thấy `Main-Class` ở archive gốc: đó có thể là một runnable Java JAR khác, không chứng minh đã có Boot nested classpath.

### 7.2. Kiểm tra archive classpath entries

```bash
jar tf target/bootloader-demo-1.0.0.jar
```

Trong output thực tế, tìm tối thiểu:

```text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/example/bootloader/BootLoaderDemoApplication.class
BOOT-INF/classes/dev/example/bootloader/ProbeController.class
BOOT-INF/classes/message.txt
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/spring-boot-autoconfigure-3.3.13.jar
```

Tên của các dependency khác có thể thay đổi theo version của Spring Boot, BOM và resolved graph. `jar tf` liệt kê **file entries**, không tự chứng minh mọi dependency đều tương thích hoặc sẽ được nạp thành công; phải chạy smoke test.

Kiểm tra nguyên tắc “application classes không nằm ở root” bằng cách so sánh:

```bash
jar tf target/bootloader-demo-1.0.0.jar.original
```

Plain JAR có thể chứa:

```text
dev/example/bootloader/BootLoaderDemoApplication.class
dev/example/bootloader/ProbeController.class
message.txt
```

Nhưng nó **không** có `BOOT-INF/lib` gồm các Spring runtime JAR theo cấu trúc executable Boot.

### 7.3. Khởi động và xác nhận classpath thực hoạt động

Dùng `java -jar` với JAR sau repackage:

```bash
java -jar target/bootloader-demo-1.0.0.jar
```

Khi server đã khởi động, terminal khác:

```bash
curl -s http://localhost:8080/probe
```

Body trả về từ code ví dụ:

```text
message=loader-ready; jackson=true
```

Hai nguồn dữ liệu của body chứng minh classloader nhìn thấy cả **application resource** và **class trong runtime dependency**. Vẫn cần kiểm tra chính JAR cuối bằng `jar tf` và manifest như trên; endpoint không chứng minh startup classpath của mọi thư viện khác trong hệ thống đều đúng.

Nếu cổng 8080 đã được dùng, chọn cổng khác:

```bash
java -jar target/bootloader-demo-1.0.0.jar --server.port=8081
curl -s http://localhost:8081/probe
```

Lệnh `curl` chạy ở terminal thứ hai khi ứng dụng đang phục vụ; không chạy đồng thời hai ứng dụng trên cùng cổng. `--server.port=8081` là Spring Boot argument, không sửa classpath hoặc manifest.

## 8. Maven: cấu hình main class và ý nghĩa của `spring-boot:repackage`

Trong POM mẫu, fragment:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>dev.example.bootloader.BootLoaderDemoApplication</mainClass>
    </configuration>
</plugin>
```

đảm bảo Boot plugin biết **application main class**. Với layout JAR mặc định:

- `Main-Class` của executable archive do Boot plugin chọn dựa trên **layout JAR**: `org.springframework.boot.loader.launch.JarLauncher`.
- `Start-Class` của executable archive trỏ tới `BootLoaderDemoApplication` theo `mainClass`.
- `BOOT-INF/classes` và `BOOT-INF/lib` được tạo từ compiled output và dependencies theo cấu hình plugin.
- Nếu không có multiple main classes, plugin có thể tự dò một main class phù hợp; với nhiều main classes nên cấu hình rõ để tránh ambiguity.

**Không sửa `Main-Class` bằng `maven-jar-plugin` rồi hy vọng Boot plugin giữ nguyên.** Spring Boot Maven Plugin quản lý lại manifest trong quá trình `repackage`. Nếu cần đổi main class ứng dụng, cấu hình `mainClass` của **Boot plugin**; nếu cần launcher khác, cấu hình đúng **layout/launcher** được Boot hỗ trợ.

### BOM import không tạo Boot Loader

Nếu chỉ có:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

thì đó chỉ là quản lý dependency versions. Nó không tự gắn goal `spring-boot:repackage`, không thêm `JarLauncher` và không làm các runtime JAR xuất hiện dưới `BOOT-INF/lib`. Khi dùng corporate parent và BOM import, project phải tự cấu hình Spring Boot Maven Plugin/version/execution để có executable archive.

**Phân biệt ba bước:** Maven dependency resolution là chọn *JAR nào*; `repackage` là quyết định *đóng JAR vào đâu*; `JarLauncher` là quyết định *nạp JAR đã đóng gói như thế nào*.

## 9. Cấu hình `PropertiesLauncher` khi thực sự cần external classpath

`JarLauncher` đủ cho phần lớn Spring Boot service. Khi ứng dụng cần classpath từ thư mục ngoài JAR (ví dụ plugin JAR được phân phối riêng), có thể đổi launcher bằng cấu hình được hỗ trợ.

### 9.1. Maven: layout ZIP/DIR

Thay phần cấu hình của Spring Boot Maven Plugin trong POM mẫu bằng:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>dev.example.bootloader.BootLoaderDemoApplication</mainClass>
        <layout>ZIP</layout>
    </configuration>
</plugin>
```

Đây là **fragment** nằm trong `<build><plugins>` của POM đầy đủ, không phải POM riêng. Với `layout=ZIP` (alias `DIR`), Spring Boot Maven Plugin dùng **`PropertiesLauncher`** theo tài liệu; output vẫn là executable archive nhưng `Main-Class` thay đổi.

Sau khi build lại:

```bash
mvn clean package
unzip -p target/bootloader-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Dòng quan trọng phải trở thành:

```text
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: dev.example.bootloader.BootLoaderDemoApplication
```

Sau đó mới có thể bổ sung đường thư viện ngoài qua `loader.path`:

```bash
java -Dloader.path=external-libs -jar target/bootloader-demo-1.0.0.jar
```

Trong ví dụ học tập chưa có thư viện ngoài nào, nên ứng dụng vẫn chỉ dùng nested dependencies đã đóng gói. Nếu tạo `external-libs` chứa JAR, `PropertiesLauncher` có thể đưa chúng vào classpath theo quy tắc và thứ tự của nó. **Không đưa thư viện từ nguồn không tin cậy vào đường nạp ứng dụng**, vì đây là cách nạp mã thực thi vào JVM.

Một đường khác là đặt environment variable `LOADER_PATH` hoặc tệp `loader.properties`; cú pháp cấu hình chính thức cũng hỗ trợ `loader.home`, `loader.main` và những thuộc tính launcher riêng. Đừng trộn `loader.path` với `spring.config.location`: đường thứ nhất liên quan **Java classpath**, đường thứ hai liên quan **tệp cấu hình Spring Boot**.

### 9.2. Gradle: chọn launcher qua manifest

Trong `build.gradle` của Spring Boot Gradle Plugin, có thể cấu hình `bootJar` dùng launcher khác khi có nhu cầu:

```groovy
tasks.named('bootJar') {
    manifest {
        attributes 'Main-Class': 'org.springframework.boot.loader.launch.PropertiesLauncher'
    }
}
```

Đây là **fragment tùy chọn**, không nên thêm vào ví dụ Gradle JAR mặc định ở mục 10 nếu bạn đang học `JarLauncher`. Sau khi đổi, luôn inspect manifest và chạy thử. Không đặt `Main-Class` thành application main class trong một Boot JAR có nested `BOOT-INF`; khi đó sẽ bỏ qua trách nhiệm của Boot Loader.

### 9.3. Những gì `loader.path` không tự giải quyết

- Không tự download dependency từ Maven Central.
- Không kiểm chứng compatibility/security của các JAR ngoài.
- Không giải quyết triệt để xung đột version nếu một class có ở cả nested archive và external directory; classpath precedence trở thành một vấn đề cần kiểm soát.
- Không sửa cấu trúc archive bị hỏng hoặc thiếu `Start-Class`.
- Không biến `JarLauncher` thành `PropertiesLauncher` nếu manifest không đổi.
- Không nên dùng để tải code tùy ý từ nơi có quyền ghi bởi người không được phép.

Thường nên **đóng gói dependency đúng từ build tool** thay vì dùng external library path. Chỉ dùng `PropertiesLauncher` khi có thiết kế plugin/extensibility phù hợp.

## 10. Gradle: `bootJar` tạo manifest và Boot classpath

Trong một project Gradle, cùng nguồn Java và resource ở mục 6 có thể dùng `settings.gradle`:

```groovy
rootProject.name = 'bootloader-demo'
```

và `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'dev.example.bootloader.BootLoaderDemoApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Cấu hình này dùng Spring Boot Gradle Plugin + Dependency Management Plugin để lấy BOM tương ứng; có thể bỏ version của starter dependencies. `springBoot.mainClass` cho biết app main class; `bootJar` sinh executable archive với manifest entry `Start-Class` thích hợp.

**Chọn một build tool cho một dự án nguồn**. Nếu muốn thực hành Gradle, dùng hai file `settings.gradle`/`build.gradle` thay vì POM, và giữ lại cùng `src/main`/`src/test` ở mục 6.

Với Gradle Wrapper phù hợp đã có sẵn:

```bash
./gradlew clean test bootJar jar
jar tf build/libs/bootloader-demo-1.0.0.jar
jar tf build/libs/bootloader-demo-1.0.0-plain.jar
java -jar build/libs/bootloader-demo-1.0.0.jar
```

Windows dùng `gradlew.bat`. Nếu chưa có wrapper, phải tạo/cài bản Gradle tương thích; không giả định file `gradlew` hiện diện ở mọi dự án.

Theo convention khi dùng Spring Boot Gradle Plugin 3.3:

- `bootJar` sinh `build/libs/bootloader-demo-1.0.0.jar` chứa Boot loader, `BOOT-INF/classes` và `BOOT-INF/lib`.
- `jar` sinh `build/libs/bootloader-demo-1.0.0-plain.jar` thông thường với application classes ở root và không có nested runtime libraries.
- `bootRun` chạy app từ source-set runtime classpath, **không đòi phải mở executable JAR rồi đọc manifest**. Vì vậy chạy tốt bằng `./gradlew bootRun` chưa chứng minh JAR cuối có manifest/layout đúng.

Nếu project đặt custom classifier/name hoặc dùng custom packaging task, tên và layout có thể khác. Kiểm tra nội dung và manifest của **chính file dự kiến triển khai**.

### Gradle kiểm tra startup manifest

Có thể trích xuất manifest của `bootJar` như với Maven:

```bash
unzip -p build/libs/bootloader-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Các giá trị cần kiểm tra vẫn là:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.bootloader.BootLoaderDemoApplication
```

Nếu tên `Start-Class` sai, sửa `springBoot.mainClass`/`bootJar.mainClass` trong Gradle configuration. Đừng nhầm `Main-Class` là tên class ứng dụng khi archive vẫn dùng nested JAR layout.

## 11. `classpath.idx` và `layers.idx`: khác manifest như thế nào?

Spring Boot có hai index file có thể xuất hiện trong executable archive. Cần phân biệt để tránh sửa nhầm khi một class không được tìm thấy.

### 11.1. `BOOT-INF/classpath.idx`

Đây là **classpath index**, biểu diễn thứ tự nested libraries để loader dùng theo cách mà executable archive hỗ trợ. Ví dụ một tệp index minh họa:

```yaml
- "BOOT-INF/lib/spring-boot-3.3.13.jar"
- "BOOT-INF/lib/spring-boot-autoconfigure-3.3.13.jar"
- "BOOT-INF/lib/spring-web-6.x.y.jar"
```

Phần `6.x.y` chỉ biểu thị tên phiên bản minh họa, **không phải tên file để copy vào artifact thật**. Build plugin sẽ ghi các entry theo dependencies thực tế.

Tài liệu Spring Boot nêu rõ classpath index được loader sử dụng khi archive chạy kiểu **`java -jar`**, không có cùng hiệu lực trong IDE, `mvn spring-boot:run` hoặc `./gradlew bootRun`. Đây là lý do thứ tự tìm resource/class khi chạy từ IDE và khi chạy JAR có thể khác trong những tình huống dependency conflicts đặc biệt.

**Không tự sửa `classpath.idx` để “fix” thư viện thiếu**. Trước hết kiểm tra `BOOT-INF/lib` thực sự chứa JAR chưa, dependency graph và cách build plugin đóng gói. Sửa danh sách mà không đóng dependency vào archive sẽ không tạo ra library.

### 11.2. `BOOT-INF/layers.idx`

Đây là **layer index** giúp tổ chức components thành container image layers, chẳng hạn ứng dụng, Boot Loader, dependencies và snapshot-dependencies. Nó **không quyết định `Start-Class`** và không phải Java `Class-Path` manifest attribute.

Ví dụ khái niệm:

```text
dependencies layer      -> BOOT-INF/lib/...
spring-boot-loader      -> org/springframework/boot/loader/...
application layer       -> BOOT-INF/classes/...
```

Nếu layers được thiết kế để caching OCI image, vẫn phải giữ lớp/đường nạp thực tế mà Boot Loader hiểu. Không đổi manifest thành lớp của một layer.

## 12. Kiểu ClassLoader và các giới hạn khi nạp nested JARs

Spring Boot Loader cần một classloader có khả năng giải quyết URL/resources bên trong nested JARs. Điều này đặc biệt quan trọng với code/framework nào dùng reflection, `ServiceLoader` hoặc nạp tài nguyên theo tên.

### 12.1. Nên ưu tiên thread context classloader

Đoạn Java minh họa:

```java
ClassLoader appLoader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName("com.fasterxml.jackson.databind.ObjectMapper",
                             false, appLoader);
```

**Đây là fragment**, cần context/source file và dependency phù hợp để chạy. Đoạn `ProbeController` ở mục 6 là phiên bản đầy đủ.

Không thay bừa bằng:

```java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
```

và mặc định rằng system classloader luôn nhìn thấy mọi class trong `BOOT-INF/lib`. Với executable nested JARs, các class ở đó thường được tìm qua classloader do Boot thiết lập. Một thư viện bên thứ ba hard-code system classloader có thể chạy bình thường trong IDE nhưng thất bại khi chạy `java -jar`.

Nếu một công nghệ đặc thù bắt buộc dùng system classloader và không thể thích nghi, có thể phải thay cách phân phối/classpath (exploded archive, external libraries, shaded JAR) hoặc cấu hình chuyên biệt; đừng chèn đường dẫn `BOOT-INF/lib/...jar` vào `java -cp` mà chưa hiểu nested archive semantics.

### 12.2. ZIP entry rules và nguyên tắc build từ công cụ chuẩn

Để truy cập nested JAR trực tiếp mà không phải giải nén mọi thư viện ra đĩa, Boot có yêu cầu về cách lưu entry của JAR con trong outer archive. Cụ thể **nested JAR entry phải dùng method `ZipEntry.STORED`**; dữ liệu *bên trong* JAR con vẫn có thể được nén.

Vì vậy, một công cụ ZIP thông thường có thể vẫn liệt kê `BOOT-INF/lib/foo.jar` nhưng vô tình nén lại entry outer thành phương thức khác, khiến Boot Loader không thể truy cập theo thiết kế. Hãy sử dụng `spring-boot:repackage` hoặc `bootJar` và tránh tự “zip lại cho nhỏ” JAR phát hành.

### 12.3. Trùng class và tài nguyên

Nếu hai nested libraries cùng chứa tên class hoặc service file, kết quả phụ thuộc vào dependency resolution, classpath order và cơ chế nạp resource. Boot không tự chứng nhận rằng version mới nhất luôn được ưu tiên hoặc rằng hai bản class cùng tên có thể sống chung an toàn.

**Kiểm tra đúng nguồn xung đột:**

```bash
mvn dependency:tree
# Hoặc Gradle:
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Sau khi sửa dependency versions/exclusions, build sạch và inspect `BOOT-INF/lib`. Nếu lỗi chỉ xuất hiện với executable archive, kiểm tra classloader assumptions cùng classpath index và sự khác biệt giữa packaged run với IDE run.

## 13. Cách đúng để truyền JVM options, Spring arguments và đường nạp ngoài

Cùng một lệnh `java` có nhiều “vùng” tùy chọn, và không phải tất cả đều sửa classpath:

```bash
java -Xmx512m -Duser.timezone=UTC \
     -jar target/bootloader-demo-1.0.0.jar \
     --server.port=8081 --spring.profiles.active=dev
```

Diễn giải:

- `-Xmx512m` và `-Duser.timezone=UTC`: **JVM options**, đứng trước `-jar`.
- `-jar target/...jar`: Java đọc `Main-Class`, gọi Boot Loader.
- `--server.port=8081` và `--spring.profiles.active=dev`: **application args** được chuyển qua loader vào main của Spring Boot, rồi Spring xử lý.
- Không có bước nào trên tự sửa `BOOT-INF/lib` hoặc thêm một external JAR vào classpath.

Bảng phân loại:

| Thao tác | Tầng xử lý chính | Tác động |
| --- | --- | --- |
| `java -jar app.jar` | Java launcher → Boot Loader | Chọn bootstrap entry từ manifest, dựng classpath và gọi app main |
| `java -cp "app.jar:lib/*" app.Main` | Java launcher truyền thống | Chạy class trực tiếp từ classpath người dùng chỉ định |
| `java -Dfoo=bar -jar app.jar` | JVM system properties | Truyền system property tới JVM/ứng dụng, không đổi manifest |
| `java -jar app.jar --spring.profiles.active=dev` | Spring Boot application args | Chọn Spring profile sau khi vào ứng dụng |
| `java -Dloader.path=extra -jar app.jar` | `PropertiesLauncher` (nếu manifest sử dụng) | Thêm đường libraries ngoài khi được launcher hỗ trợ |
| `mvn -Pci package` | Maven | Kích hoạt **Maven profile**; không tự sửa active Spring profile |
| `mvn spring-boot:run` | Boot Maven Plugin | Chạy từ project classpath, không đồng nghĩa `java -jar` |
| `./gradlew bootRun` | Boot Gradle Plugin | Chạy từ runtime classpath của source set, không cần manifest của bootJar |

**Điểm cảnh báo:** `java -jar app.jar -Dfoo=bar` đặt `-Dfoo=bar` sau `app.jar`, nên nó trở thành **application argument string**, không phải JVM `-D` property. JVM options phải đứng trước `-jar`.

## 14. Chẩn đoán các lỗi theo đúng mắt xích

| Triệu chứng | Nơi có thể hỏng | Cách xác minh/sửa |
| --- | --- | --- |
| `no main manifest attribute` | Manifest thiếu `Main-Class` | Đọc `META-INF/MANIFEST.MF`; xác định file có phải Boot JAR sau repackage/bootJar không |
| `Could not find or load main class ...JarLauncher` | `Main-Class` đúng tên nhưng Boot loader classes thiếu/đặt sai root | `jar tf` tìm `org/springframework/boot/loader/launch/JarLauncher.class`; build lại bằng Boot plugin |
| Boot loader chạy nhưng không tìm thấy `Start-Class` | `Start-Class` sai, app main bị đổi tên hoặc không được compile/đóng gói | So sánh manifest với `BOOT-INF/classes/...class` và cấu hình mainClass |
| `java -cp app.jar app.Main` không tìm thấy app class | App nằm dưới `BOOT-INF/classes`, không ở root | Dùng `java -jar` trên Boot JAR; nếu muốn `-cp`, dùng plain JAR kèm external dependencies |
| `NoClassDefFoundError: org/springframework/...` sau khi đóng gói | `BOOT-INF/lib` thiếu dependency hoặc scope bị loại | Đọc `jar tf` và Maven/Gradle runtime graph; sửa build model |
| Jackson/Web dependency load được ở IDE nhưng không trong JAR | Source run và packaged run có classpath khác | So sánh `spring-boot:run`/`bootRun` với `BOOT-INF/lib`; build/inspect lại |
| Đặt `-Dloader.path=external-libs` nhưng class không xuất hiện | Dùng `JarLauncher` thay vì `PropertiesLauncher` hoặc đường thư viện sai | Đọc `Main-Class`, kiểm tra location và JAR thực tế |
| Lỗi khi sử dụng `ClassLoader.getSystemClassLoader()` | System loader không nhìn thấy nested libraries | Thử thread context classloader theo Spring Boot loader contract |
| `jar tf` vẫn thấy nested JAR nhưng startup lỗi sau khi zip lại | Compression method/metadata outer JAR không đúng | Không tự rezip; build lại bằng `repackage`/`bootJar` |
| `Start-Class` thay đổi ngoài ý muốn | Có nhiều main classes hoặc cấu hình plugin khác giữa local/CI | Pin mainClass trong Boot Maven/Gradle plugin; inspect manifest của artifact phát hành |
| `java -jar` chạy nhưng ứng dụng không bind `application-prod.yml` | Spring profile/config sai, không phải lỗi launcher | Kiểm tra Spring config sources/`spring.profiles.active` sau khi main đã chạy |
| `UnsupportedClassVersionError` | JDK runtime thấp hơn version bytecode | Kiểm tra `java -version`, Maven Compiler/Gradle Java toolchain |
| `ClassNotFoundException` do trùng dependency versions | Dependency graph hoặc classpath order không đúng | `dependency:tree`/`dependencyInsight`, kiểm tra `BOOT-INF/lib` và `classpath.idx` |
| Thư viện nội bộ được publish dưới dạng Boot JAR và module khác không thấy class | Class của library nằm dưới `BOOT-INF/classes` | Publish plain JAR hoặc tách library module; executable Boot JAR không thay thế library JAR thông thường |
| Container build đổi nội dung JAR sau QA | Artifact identity không được bảo toàn | Publish/deploy chính checksum/digest đã test; scan artifact trong image |

### Quy trình điều tra ưu tiên

1. **Lấy đúng câu lệnh đã chạy** (`java -jar`, `java -cp`, `bootRun` hay `spring-boot:run`).
2. **Xác định đúng artifact**: module, version, classifier và đường dẫn file thật được deploy.
3. **Kiểm tra manifest**: `Main-Class` có đúng launcher? `Start-Class` có đúng app main?
4. **Kiểm tra archive entries**: Boot loader classes, `BOOT-INF/classes`, `BOOT-INF/lib` có đúng không?
5. **Kiểm tra dependency graph**: artifact cần thiết có được resolve và đóng gói không?
6. **Chạy smoke test trên chính executable JAR**: dùng `java -jar`, thử endpoint; đọc root cause đầu tiên trong stack trace.
7. **Xử lý classloader-specific issue**: kiểm tra `Thread.currentThread().getContextClassLoader()`, classpath index và external paths nếu có.
8. **Rebuild, test và kiểm tra lại**: sửa build config/POM, không vá manifest hoặc ZIP file phát hành bằng tay.

## 15. Bài tập củng cố

**Bài 1.** Manifest của một Spring Boot JAR có `Main-Class: org.springframework.boot.loader.launch.JarLauncher` và `Start-Class: dev.example.bootloader.BootLoaderDemoApplication`. JVM trực tiếp gọi main của lớp nào?

*Đáp án:* JVM dùng `Main-Class` để gọi `JarLauncher` trước. Sau khi dựng classpath thích hợp, Boot Loader mới gọi main của `BootLoaderDemoApplication` theo `Start-Class`.

**Bài 2.** Một JAR chứa app class ở `BOOT-INF/classes` và Spring libs ở `BOOT-INF/lib`. Chạy `java -cp app.jar dev.example.bootloader.BootLoaderDemoApplication` có tự hoạt động không?

*Đáp án:* Không theo classpath thông thường. Java nhìn JAR như một classpath root, không tự xem `BOOT-INF/classes` như root và không tự nạp JAR lồng nhau. Dùng `java -jar` với Boot Loader, hoặc xây dựng một classpath/exploded distribution hợp lệ.

**Bài 3.** Có người sửa duy nhất manifest thành `Main-Class: dev.example.bootloader.BootLoaderDemoApplication` trên một Boot JAR đã có `BOOT-INF`. Vì sao dễ thất bại?

*Đáp án:* Họ bỏ qua `JarLauncher`, tức thành phần thiết lập classpath cho app classes và nested dependencies. Sửa mainClass của Spring Boot plugin nếu muốn đổi application entry point, không thay Boot launcher bằng app class.

**Bài 4.** Tại sao thêm `Class-Path: BOOT-INF/lib/spring-web.jar` vào manifest thường không thay thế được `JarLauncher`?

*Đáp án:* Java standard manifest `Class-Path` không tự giải quyết nested archive entries bên trong Boot JAR theo định dạng Boot. Cần loader hiểu layout/nested JARs; tên JAR thực tế còn chứa version, và libs có thể nhiều hơn một.

**Bài 5.** Trong IDE ứng dụng chạy tốt nhưng packaged JAR thiếu `ObjectMapper`. Bạn kiểm tra chỗ nào trước?

*Đáp án:* Xem `BOOT-INF/lib` của đúng JAR sau build và dependency graph/runtime scope. Test IDE dùng classpath khác archive phát hành, nên không thể thay thế archive inspection.

**Bài 6.** `LOADER_PATH` luôn có tác dụng với `JarLauncher` không?

*Đáp án:* Không. Đây là khả năng của `PropertiesLauncher`. Phải cấu hình manifest/layout để dùng launcher này và xác minh đường thư viện ngoài.

**Bài 7.** `BOOT-INF/layers.idx` có thể thay `Start-Class` để đổi main method không?

*Đáp án:* Không. `layers.idx` mô tả phân lớp artifact phục vụ container caching; `Start-Class` nằm trong manifest và được Boot Loader dùng để biết application main class.

**Bài 8.** Một JAR outer có nested `BOOT-INF/lib/foo.jar` nhưng công cụ ZIP nén entry outer không đúng phương thức. Có thể Boot Loader vẫn lỗi dù `jar tf` liệt kê được file không?

*Đáp án:* Có. Spring Boot Loader có yêu cầu về ZIP entry method của nested JAR; hãy build lại bằng plugin chuẩn thay vì tái nén thủ công.

**Bài 9.** Đọc `Start-Class` trong manifest chứng minh chắc chắn ứng dụng khởi động thành công?

*Đáp án:* Không. Nó chỉ nói ứng dụng muốn gọi main class nào. Còn phải có loader class, compiled app, tất cả runtime dependencies, Java runtime và cấu hình hợp lệ; nên chạy `java -jar` rồi smoke test.

**Bài 10.** Vì sao test `ProbeControllerTest` trong mục 6 chưa đủ để chứng minh `JarLauncher` đã chạy đúng?

*Đáp án:* Test runner dùng test classpath của Maven/Gradle chứ không mở executable archive như `java -jar`. Phải kiểm tra manifest/`BOOT-INF` của artifact và chạy nó thật.

## 16. Checklist khi chuẩn bị phát hành Spring Boot executable JAR

- **Artifact đúng:** file deploy là output của `spring-boot:repackage` hoặc `bootJar`, không phải plain/library JAR, `.jar.original` hay `-plain.jar`.
- **Manifest đúng:** `Main-Class` là launcher phù hợp layout, `Start-Class` trỏ tới class ứng dụng có `public static void main(String[])`.
- **Loader đầy đủ:** lớp `JarLauncher`/`WarLauncher`/`PropertiesLauncher` có mặt ở vị trí mà Java launcher tải được.
- **App classes/resources đúng:** `BOOT-INF/classes` chứa compiled classes và resources ứng dụng, bao gồm những thứ được code đọc bằng classpath.
- **Runtime libs đúng:** `BOOT-INF/lib` chứa đúng tập dependencies từ runtime graph; không có bản trùng/xung đột vô ý.
- **Không rezip làm hỏng nested archive:** build bằng plugin phù hợp và bảo toàn ZIP entry semantics.
- **Classpath strategy đúng:** dùng `JarLauncher` cho Boot JAR chuẩn; chỉ dùng `PropertiesLauncher` và `loader.path` khi cần external jars có kiểm soát.
- **Đối số chạy đúng vị trí:** JVM `-D` trước `-jar`; Spring `--...` sau JAR; `-cp` không thay thế nested launcher.
- **JDK tương thích:** runtime target hỗ trợ bytecode của project (mẫu dùng Java 17).
- **Smoke test chính artifact:** chạy `java -jar` từ output phát hành, kiểm tra endpoint/health và đọc lỗi classpath startup.
- **CI phát hành artifact đã kiểm chứng:** lưu checksum/digest, không build lại bằng quy tắc khác tại bước deploy.

**Kết luận:** Spring Boot executable JAR hoạt động nhờ **manifest chỉ tới Boot Launcher, Boot Launcher dựng classpath từ application classes và nested dependencies, rồi mới gọi `Start-Class` của ứng dụng**. Nhầm lẫn ba vai trò này là nguyên nhân phổ biến của lỗi “JAR build được nhưng `java -jar` không chạy”. Hãy kiểm tra **manifest + loader class + archive layout + runtime classpath + smoke test**, thay vì chỉ nhìn tên file hoặc trạng thái build thành công.

### Tài liệu chính thức để đối chiếu

- Spring Boot 3.3 — Executable JAR, Launching Executable Jars: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/launching.html
- Spring Boot 3.3 — Executable JAR, Nested JARs: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/nested-jars.html
- Spring Boot 3.3 — PropertiesLauncher Features: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/property-launcher.html
- Spring Boot 3.3 — Executable JAR Restrictions: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/restrictions.html
- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3.13 — JarLauncher API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/loader/launch/JarLauncher.html
- Oracle Java 17 — Java launcher: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html