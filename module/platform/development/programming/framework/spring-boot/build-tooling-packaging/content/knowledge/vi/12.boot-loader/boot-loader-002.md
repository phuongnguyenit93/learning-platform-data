# Vai trò của JarLauncher, WarLauncher và PropertiesLauncher trong Spring Boot Loader

## 1. Ba launcher giải quyết vấn đề gì?

Khi biên dịch Spring Boot, bạn có thể đóng gói ứng dụng thành **executable JAR** hoặc **executable WAR** để chạy bằng `java -jar`. Bên trong archive không chỉ có class của ứng dụng, mà thường chứa các thư viện phụ thuộc **dưới dạng JAR lồng trong JAR/WAR**. JVM chuẩn không mặc nhiên tìm được class trong các JAR lồng nhiều tầng chỉ bằng cách thêm file archive ngoài cùng vào `-classpath`.

**Spring Boot Loader** là mã bootstrap được đóng gói ở archive để:

1. Nhận quyền điều khiển khi JVM đọc `META-INF/MANIFEST.MF`.
2. Xác định vị trí class ứng dụng và thư viện lồng bên trong archive.
3. Tạo/thiết lập class loader phù hợp.
4. Gọi phương thức `main(String[] args)` thật sự của ứng dụng Spring Boot.

Ba launcher thường được nhắc đến:

- **`JarLauncher`:** launcher mặc định cho executable **JAR** theo layout `BOOT-INF/classes` và `BOOT-INF/lib`.
- **`WarLauncher`:** launcher mặc định cho executable **WAR** theo layout `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided`.
- **`PropertiesLauncher`:** launcher có thể cấu hình nơi tìm thư viện bổ sung và main class, ví dụ qua `loader.path`, `loader.main` và `loader.properties`. Phù hợp khi muốn mở rộng classpath ngoài archive mà không đóng gói lại ngay.

Đây là thành phần **khởi động archive**, không phải Spring MVC controller, Spring bean, annotation processor hay ba loại application server.

**Phạm vi phiên bản:** ví dụ và package class trong bài dùng **Spring Boot 3.5.x**, Java 17+. Từ Spring Boot 3.2, launcher nằm trong package `org.springframework.boot.loader.launch`. Khi đọc hướng dẫn Spring Boot 2.x hoặc 3.1, bạn có thể thấy tên cũ `org.springframework.boot.loader.JarLauncher`/`WarLauncher`/`PropertiesLauncher`; **không sao chép tên class cũ** sang manifest của Boot 3.5.

## 2. Cơ chế khởi động: Main-Class không phải Start-Class

Trong một executable archive Spring Boot được đóng gói bằng Maven/Gradle plugin, thông thường manifest có **hai vai trò khác nhau**:

- `Main-Class`: tên class có phương thức `main` mà lệnh `java -jar` gọi đầu tiên — một **launcher** của Boot Loader.
- `Start-Class`: tên class có `main(String[] args)` của **ứng dụng bạn**, chẳng hạn `com.example.loader.LoaderDemoApplication`.

Manifest của executable JAR điển hình:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

Manifest của executable WAR điển hình:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

Manifest của JAR chọn PropertiesLauncher:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.PropertiesLauncher
Start-Class: com.example.loader.LoaderDemoApplication
```

Các dòng này là ví dụ **phần metadata liên quan**, không phải bản dump đầy đủ. Manifest thực tế có thể có `Spring-Boot-Version`, `Spring-Boot-Classes`, `Spring-Boot-Lib` và các trường khác.

Luồng khởi động:

```text
java -jar app.jar / app.war
            |
            v
JVM đọc META-INF/MANIFEST.MF
            |
            v
Main-Class = Boot Loader Launcher
            |
            v
Launcher xác định classpath:
    app classes + nested dependency jars
            |
            v
Tạo class loader + nạp Start-Class
            |
            v
LoaderDemoApplication.main(args)
            |
            v
SpringApplication.run(...)
```

Điểm quan trọng: **`Start-Class` không tự trở thành Java main entry point chỉ vì được ghi trong manifest**. `java -jar` sử dụng `Main-Class`, launcher mới tìm và gọi `Start-Class`. Không nên cố sửa manifest `Main-Class` thành class ứng dụng trong khi vẫn giữ nguyên layout nested JAR; khi đó classpath của các dependency lồng bên trong có thể không được thiết lập đúng.

**Không cần tự tạo `Class-Path` trong manifest cho từng nested JAR.** Spring Boot Loader suy ra classpath từ layout được hỗ trợ.

## 3. So sánh trực tiếp ba launcher

| Tiêu chí | `JarLauncher` | `WarLauncher` | `PropertiesLauncher` |
|---|---|---|---|
| Trường hợp chính | Executable JAR | Executable WAR | Archive cần classpath/main tùy biến |
| Application classes | `BOOT-INF/classes/` | `WEB-INF/classes/` | Thường `BOOT-INF/classes/` với layout kiểu JAR/ZIP |
| Nested dependencies | `BOOT-INF/lib/` | `WEB-INF/lib/` và `WEB-INF/lib-provided/` | Mặc định dùng `BOOT-INF/lib/`; có thể thêm classpath |
| Đường dẫn thư viện | Quy ước cố định | Quy ước cố định | `loader.path` / `LOADER_PATH` / cấu hình launcher |
| Chọn main ứng dụng | `Start-Class` | `Start-Class` | `loader.main` hoặc `Start-Class` khi phù hợp |
| Thay đổi classpath bằng `loader.path` | Không phải cách cấu hình của launcher này | Không phải cách cấu hình của launcher này | Có |
| Có thể dùng `java -jar`? | Có, nếu archive được đóng gói đúng | Có, nếu WAR là executable WAR | Có, nếu được đóng gói với launcher/layout đúng |
| Công cụ build thường chọn | Maven repackage với layout `JAR` / Gradle `bootJar` | Maven repackage với layout `WAR` / Gradle `bootWar` | Maven layout `ZIP`/`DIR`; Gradle có thể cấu hình manifest của Boot archive |
| Có thay SpringApplication? | Không | Không | Không |
| Rủi ro thường gặp | Cố dùng `-cp` hoặc thêm jar ngoài mà loader không biết | Nhầm executable WAR với triển khai external servlet container | Xung đột version/classpath, tin tưởng thư viện ngoài, nhầm `loader.*` với `spring.*` |

**Ghi nhớ:** tên launcher mô tả **cách khởi động và cách tìm class**, không quyết định ứng dụng dùng Tomcat, Undertow, Netty, MVC hay WebFlux. Một JAR Boot có thể chứa ứng dụng không phải web; một WAR Boot thường liên quan servlet web application.

## 4. Vì sao cần Boot Loader thay vì JAR thông thường?

JAR thường chứa file `.class` trực tiếp ở gốc package path và có thể dùng `java -cp` với các thư viện nằm **bên ngoài** archive. Spring Boot executable archive thường giữ nguyên từng thư viện phụ thuộc dưới dạng **nested JAR**, khác cách “shade” hợp nhất tất cả class của các thư viện vào một namespace JAR.

Ví dụ cấu trúc executable JAR:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class     # Boot Loader ở archive root
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/loader/LoaderDemoApplication.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-context-*.jar
    │   └── ... các dependency khác
    ├── classpath.idx                # Có thể được tạo bởi plugin
    └── layers.idx                   # Có thể được tạo bởi plugin
```

Các tên JAR `spring-boot-*.jar` trong cây chỉ minh họa, không phải tên cụ thể sẽ luôn có ở mọi phiên bản. Bootstrap loader ở **gốc archive**, còn source class của ứng dụng nằm tại `BOOT-INF/classes`.

**Lý do kỹ thuật:** Java `URLClassLoader` với classpath thông thường không tự coi mỗi `BOOT-INF/lib/dependency.jar` là một archive riêng để mở và tải class. Spring Boot cung cấp cơ chế truy cập nested JAR, đọc vị trí entry trong file archive và class loader hỗ trợ URL nested. Với layout đúng, không cần giải nén toàn bộ dependency JAR ra một thư mục tạm chỉ để chạy ứng dụng.

Một số thư viện không tương thích với custom loader nếu cố dùng `ClassLoader.getSystemClassLoader()` hoặc giả định mọi resource đều là `java.io.File` trên filesystem. Khi cần lấy resource đóng gói, ưu tiên classpath resource stream thay vì ép nó thành đường dẫn file vật lý.

## 5. JarLauncher: lựa chọn mặc định cho executable JAR

### 5.1. Cách JarLauncher tìm class

`JarLauncher` nhận diện những vị trí đã được Boot quy định, chủ yếu:

- `BOOT-INF/classes/`: class và resource ứng dụng.
- `BOOT-INF/lib/`: những JAR dependency được plugin đóng gói.

Nó dựng runtime classpath và gọi `Start-Class`. Khi lệnh là:

```bash
java -jar target/loader-demo-0.1.0-SNAPSHOT.jar
```

JVM không trực tiếp gọi `LoaderDemoApplication.main` từ manifest. Nó gọi `JarLauncher.main`; launcher lo classpath rồi mới chuyển quyền cho ứng dụng. **JarLauncher không phải công cụ lấy thư viện từ một thư mục tùy ý bên cạnh JAR khi bạn đặt `loader.path`.** Nếu cần cơ chế đó, xem `PropertiesLauncher`.

### 5.2. Spring Boot Maven Plugin tạo nó thế nào?

Trong Maven dùng `spring-boot-starter-parent` và `spring-boot-maven-plugin`, `mvn package` có thể tạo executable JAR qua goal `repackage` đã được cấu hình. Layout mặc định dựa trên loại archive.

Ví dụ phần cấu hình plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Đoạn này dành cho POM đã kế thừa `spring-boot-starter-parent`, có source main và project có `<packaging>jar</packaging>` hoặc mặc định là JAR. Parent thường đã định nghĩa execution `repackage`; không cần thêm execution trùng nếu chỉ muốn JAR mặc định.

Với Maven không dùng parent Boot, cần cấu hình plugin version, execution `repackage` và dependency management phù hợp. **Chỉ thêm thư viện `spring-boot-loader` làm dependency không tự biến một JAR thường thành executable JAR đúng layout**.

### 5.3. Gradle bootJar

Với Gradle Groovy DSL, Java plugin và Spring Boot Gradle plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Đoạn `build.gradle` là cấu hình có thể sử dụng trong project single-module đã có `settings.gradle`/wrapper, và Java main ở phần thực hành. Gọi:

```bash
./gradlew bootJar
java -jar build/libs/loader-demo-0.1.0-SNAPSHOT.jar
```

Tên JAR phụ thuộc tên root project, `version` và các tùy chỉnh archive; `bootJar` tạo executable JAR, còn task `jar` là Java archive thông thường. `./gradlew bootRun` chạy trực tiếp từ classpath phát triển, không phải test thực tế đường `JarLauncher` từ executable JAR đã đóng gói.

## 6. WarLauncher: khởi chạy executable WAR

### 6.1. Layout WAR là một quy ước khác

Executable WAR Spring Boot thường có cấu trúc:

```text
app.war
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/WarLauncher.class
└── WEB-INF/
    ├── classes/
    │   └── com/example/web/WebApplication.class
    ├── lib/
    │   ├── spring-webmvc-*.jar
    │   └── ... thư viện ứng dụng
    └── lib-provided/
        ├── tomcat-embed-*.jar
        └── ... dependency ở provided scope (nếu có)
```

`WarLauncher` tìm class trong `WEB-INF/classes` và các JAR trong `WEB-INF/lib` **cũng như `WEB-INF/lib-provided`** khi chạy bằng `java -jar app.war`. Hai thư mục thư viện có lý do tồn tại khác nhau.

`WEB-INF/lib-provided` phục vụ các dependency **cần để chạy WAR tự chứa bằng `java -jar`** nhưng **không nên được external servlet container nạp trùng** khi triển khai WAR theo cách truyền thống. Ví dụ phổ biến: embedded servlet container dependency được đánh dấu `provided`.

### 6.2. Hai cách dùng cùng một executable WAR

**Cách A — chạy độc lập:**

```bash
java -jar target/web-demo-0.1.0-SNAPSHOT.war
```

Trong đường này, JVM đọc manifest, gọi `WarLauncher`, sử dụng những dependency cần thiết bên trong WAR (bao gồm những thư viện ở `WEB-INF/lib-provided` nếu đã đóng gói) để khởi động embedded server.

**Cách B — triển khai vào một servlet container bên ngoài:** đặt WAR vào Tomcat/servlet container tương thích. Container xử lý deployment theo mô hình Servlet, dùng `WEB-INF/classes` và `WEB-INF/lib` cùng API/container do nó cung cấp. **External container không gọi `WarLauncher` bằng cơ chế `java -jar` của Boot Loader**; ứng dụng cần được cấu hình để Servlet container bootstrap đúng, thường qua một class kế thừa `SpringBootServletInitializer`.

Vì vậy **“dùng WAR” không tự đồng nghĩa “WarLauncher sẽ được external Tomcat gọi”**. WarLauncher thuộc **đường chạy executable WAR**, không thay thế cơ chế deploy WAR của servlet container.

### 6.3. Ví dụ class cho servlet WAR

Trong project có Spring MVC/Tomcat dependency phù hợp, tạo:

```java
package com.example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WebApplication extends SpringBootServletInitializer {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(WebApplication.class);
    }
}
```

`main` hỗ trợ `java -jar`; `configure` hỗ trợ đường Servlet container khi WAR được deploy. Đây là source Java hợp lệ nhưng cần classpath Spring Boot và cấu hình build WAR đầy đủ. Nó khác ví dụ non-web ở phần sau; **không ghép hai main class vào cùng project** rồi hy vọng plugin tự chọn một cách đúng.

### 6.4. Maven WAR packaging

Một POM Spring Boot web project cần chọn WAR:

```xml
<packaging>war</packaging>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-tomcat</artifactId>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

Đây là **phần ghép vào POM** đã có parent Boot, `groupId`, `artifactId`, `version` và `spring-boot-maven-plugin`; không phải XML document độc lập. Việc khai báo Tomcat provided là hướng cấu hình phổ biến khi cần deploy WAR vào container ngoài. Khi Spring Boot Plugin repackage, dependency provided phù hợp đi vào `WEB-INF/lib-provided` cho executable WAR.

Chạy `./mvnw package` rồi kiểm tra `target/*.war`. Khi deploy container ngoài, kiểm tra **Servlet API, Jakarta namespace, version Tomcat/JDK** phù hợp với version Spring Boot. Không lấy một WAR Boot 3.5 rồi tùy tiện deploy vào servlet container quá cũ.

### 6.5. Gradle bootWar

Với Gradle Java web project đã áp dụng Spring Boot plugin, có thể thêm `war` plugin và cấu hình:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

Trong project thật, đặt thêm `group`, `version`, toolchain và source `WebApplication` như ví dụ ở trên. Task `bootWar` tạo executable WAR; `war` thông thường tạo WAR theo Java war plugin. Sử dụng `providedRuntime` đúng mục đích thay vì xóa tùy tiện embedded servlet container khỏi toàn bộ runtime classpath, bởi executable WAR vẫn cần khởi động độc lập.

## 7. PropertiesLauncher: mở rộng classpath và chỉ định main

### 7.1. Cách nghĩ đúng

`PropertiesLauncher` vẫn làm nhiệm vụ bootstrap class loader và gọi ứng dụng. Nó khác ở chỗ cho phép người vận hành **cung cấp thêm vị trí classpath hoặc thông tin main class khi chạy**. Đó là lý do nó phù hợp với một số cách đóng gói/triển khai muốn giữ dependencies ở ngoài archive hoặc bổ sung thư viện đáng tin cậy.

Nó **không tự động tải dependency mới từ Maven Central**, không thay đổi `pom.xml`/`build.gradle`, không cung cấp hot-reload, và không phải Spring `PropertySource` cho các thuộc tính nghiệp vụ.

Trong archive layout kiểu JAR/ZIP mà nó hỗ trợ, class/thư viện tại `BOOT-INF/classes` và `BOOT-INF/lib` tiếp tục được sử dụng; `loader.path` bổ sung những entry khác vào classpath.

Ví dụ ý định:

```text
/opt/demo/
├── app.jar                     # Spring Boot ZIP layout, PropertiesLauncher
├── loader.properties           # Cấu hình cho launcher (tùy chọn)
└── external-lib/
    ├── vendor-client.jar
    └── plugin-api-impl.jar
```

Khi `loader.path=external-lib` và `loader.home=/opt/demo`, launcher có thể tìm các thư viện bổ sung trong thư mục này mà không nhất thiết phải rebuild `app.jar`. Nhưng mở rộng classpath là một thay đổi **mã được thực thi**, nên phải kiểm soát version, signature, quyền truy cập và nguồn file.

### 7.2. Thuộc tính thường dùng

| Thuộc tính | Ý nghĩa |
|---|---|
| `loader.path` / `LOADER_PATH` | Danh sách cách nhau bằng dấu phẩy: thư mục, JAR/ZIP hoặc vị trí được loader hỗ trợ để bổ sung classpath |
| `loader.home` / `LOADER_HOME` | Thư mục cơ sở cho đường dẫn tương đối trong `loader.path`, mặc định thường là current working directory |
| `loader.main` / `LOADER_MAIN` | Chỉ định class ứng dụng để gọi; nếu không có thì có thể dùng `Start-Class` |
| `loader.args` / `LOADER_ARGS` | Các application arguments mặc định được chuyển cho main |
| `loader.config.name` | Tên file cấu hình launcher, thường là `loader.properties` (không gồm phần mở rộng) |
| `loader.config.location` | Vị trí file cấu hình launcher nếu cần trỏ tường minh, ví dụ `file:/opt/demo/loader.properties` |
| `loader.system` / `LOADER_SYSTEM` | Cơ chế tùy chọn chuyển loader configuration thành System properties; mặc định không nên giả định bật |

Spring Boot còn hỗ trợ cấu hình qua manifest entry và Java system property. Thứ tự ưu tiên cụ thể giữa các nguồn cấu hình được xác định bởi implementation/phiên bản loader; khi nhiều nơi cùng đặt `loader.path`, hãy kiểm tra hành vi thật trên archive đang chạy, tránh dựa vào suy luận từ thứ tự shell command.

**Không nhầm namespace:**

- `loader.path`: đường dẫn **class/library** mà launcher nạp.
- `spring.config.location` hoặc `spring.config.additional-location`: đường dẫn **tệp cấu hình Spring Boot**.
- `spring.profiles.active`: profile **ứng dụng Spring**.
- `java.class.path`/`-cp`: classpath mà **JVM chuẩn** sử dụng; khi chạy `java -jar`, launcher còn dựng classpath ứng dụng từ nested JAR.

Chúng giải quyết các vấn đề khác nhau.

### 7.3. Ví dụ loader.properties

Đặt file `loader.properties` ở vị trí mà `PropertiesLauncher` có thể tìm, chẳng hạn thư mục làm việc mặc định của tiến trình:

```properties
loader.path=external-lib
loader.home=/opt/demo
```

Giá trị `/opt/demo` là ví dụ Linux. Trong môi trường thật, hãy đặt đúng đường dẫn có quyền đọc. Đường dẫn tương đối của `loader.path` được resolve dựa trên `loader.home`; nếu đổi current working directory mà không kiểm soát `loader.home`, launcher có thể không tìm thấy file.

Hoặc truyền trực tiếp Java system property khi chạy (không cần tạo file):

```bash
java -Dloader.home=/opt/demo -Dloader.path=external-lib \
     -jar /opt/demo/app.jar
```

Lệnh nhiều dòng dùng nối dòng `\` cho shell Unix/macOS; trên Windows nhập một dòng và dùng đường dẫn phù hợp. Để đặt env var trong shell POSIX:

```bash
LOADER_PATH=/opt/demo/external-lib java -jar /opt/demo/app.jar
```

Những cách này **chỉ hữu dụng khi archive dùng PropertiesLauncher**. Với `JarLauncher`, đặt `-Dloader.path` không làm launcher cố định này chuyển sang cách giải quyết classpath như PropertiesLauncher.

### 7.4. Cách chọn PropertiesLauncher khi đóng gói bằng Maven

**Trong Spring Boot Maven Plugin, `layout=ZIP` (tên khác `DIR`) tạo layout tương tự JAR nhưng sử dụng `PropertiesLauncher`.** Chữ “ZIP” ở đây là tên **layout**, không có nghĩa bắt buộc đổi extension của executable file từ `.jar` thành `.zip`.

Nếu POM kế thừa `spring-boot-starter-parent` và đã khai báo Spring Boot Maven Plugin, sửa cấu hình plugin thành:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layout>ZIP</layout>
    </configuration>
</plugin>
```

Đây là **fragment trong `<build><plugins>` của POM**, không phải POM độc lập. Với starter parent, execution `repackage` thường đã được cấu hình; nếu dùng parent khác, phải bind goal `repackage` vào quy trình build.

Build lại:

```bash
./mvnw clean package
```

Rồi kiểm tra manifest của executable JAR mới: `Main-Class` phải là `org.springframework.boot.loader.launch.PropertiesLauncher`. Nếu vẫn là `JarLauncher`, bạn có thể đã sửa nhầm module, chạy nhầm Maven profile hoặc kiểm tra nhầm file artifact cũ.

### 7.5. Cách cấu hình manifest khi dùng Gradle

Với project có task `bootJar` từ Spring Boot Gradle plugin, có thể tùy chỉnh manifest của **task tạo executable archive**. Ví dụ Groovy DSL cho Boot 3.5:

```groovy
tasks.named('bootJar') {
    manifest {
        attributes 'Main-Class':
            'org.springframework.boot.loader.launch.PropertiesLauncher'
    }
}
```

Đây là **đoạn thêm vào `build.gradle`**, không phải file hoàn chỉnh. Sau khi chạy `./gradlew bootJar`, hãy **kiểm tra lại manifest** và thử `java -Dloader.path=... -jar ...`. Tránh chỉnh manifest của task `jar` thường rồi mặc định task `bootJar` đã thay launcher; task nào tạo file bạn chạy mới quyết định.

Đối với archive WAR/Gradle Boot plugin hoặc các custom layout, phải kiểm tra khả năng tương thích của bố cục archive với launcher được chọn. `PropertiesLauncher` thường phù hợp layout kiểu **BOOT-INF**; đừng chỉ đổi `Main-Class` của một executable WAR dùng `WEB-INF` sang PropertiesLauncher rồi mặc định nó sẽ hiểu đúng mọi đường dẫn. Khi cần WAR cho servlet container ngoài, ưu tiên launcher/mô hình WAR chuẩn.

## 8. Thực hành chạy được: kiểm chứng JarLauncher và PropertiesLauncher

Bài tập dưới đây dùng **Maven + Spring Boot 3.5.x + Java 17**, một ứng dụng **không có web server** để log dễ quan sát. Mục đích là chứng minh rằng Java runtime **chỉ** tìm thấy một class ngoài archive khi classpath được bổ sung đúng cách qua PropertiesLauncher.

### 8.1. Tạo ứng dụng

Cấu trúc thư mục:

```text
loader-demo/
├── pom.xml
├── mvnw / mvnw.cmd / .mvn/              # Maven Wrapper từ Initializr
├── src/main/java/com/example/loader/
│   └── LoaderDemoApplication.java
└── extra-src/demo/extra/
    └── Greeting.java
```

Maven `pom.xml` (đây là file hoàn chỉnh cho ví dụ):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>loader-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Lớp Java `src/main/java/com/example/loader/LoaderDemoApplication.java`:

```java
package com.example.loader;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LoaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoaderDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showExternalLibrary() {
        return args -> {
            System.out.println("BOOT_APP_OK");
            try {
                Class<?> greetingClass =
                        Class.forName("demo.extra.Greeting");
                Object message =
                        greetingClass.getMethod("say").invoke(null);
                System.out.println("EXTENSION=" + message);
            } catch (ClassNotFoundException e) {
                System.out.println("EXTENSION=absent");
            }
        };
    }
}
```

Ứng dụng dùng Spring Boot và Spring Framework để tạo context, sau đó thực thi `ApplicationRunner`. Khi launcher không tìm thấy class `demo.extra.Greeting`, nó in `EXTENSION=absent`. Khi external JAR được nạp, reflection gọi method `say()` và in chuỗi trả về. Đây là Java 17 hợp lệ **khi chạy qua Maven với Spring dependencies**, không phải lớp có thể chạy bằng `javac` trần.

### 8.2. Chạy executable JAR mặc định

Tại root project:

```bash
./mvnw clean package
java -jar target/loader-demo-0.1.0-SNAPSHOT.jar
```

Trong log Spring Boot có nhiều dòng thay đổi theo môi trường. Hai dòng **do ứng dụng tự in** sẽ là:

```text
BOOT_APP_OK
EXTENSION=absent
```

Sau khi runner hoàn thành, vì ví dụ chỉ có `spring-boot-starter` (không có embedded web server), tiến trình thường kết thúc thay vì tiếp tục giữ cổng HTTP. Nếu bạn thêm `spring-boot-starter-web`, hành vi vòng đời tiến trình sẽ khác.

Xem manifest và cấu trúc:

```bash
jar tf target/loader-demo-0.1.0-SNAPSHOT.jar
unzip -p target/loader-demo-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
```

Lệnh `unzip -p` dùng cho hệ thống có `unzip`; ở Windows có thể dùng công cụ xem archive hoặc giải nén vào thư mục kiểm tra riêng. Kỳ vọng manifest chứa `Main-Class: org.springframework.boot.loader.launch.JarLauncher` và `Start-Class: com.example.loader.LoaderDemoApplication`.

### 8.3. Tạo thư viện JAR bổ sung ngoài ứng dụng

Tạo file `extra-src/demo/extra/Greeting.java`:

```java
package demo.extra;

public final class Greeting {
    private Greeting() {
    }

    public static String say() {
        return "hello-from-external-jar";
    }
}
```

Class này **chỉ dùng Java Standard Library**, có thể biên dịch độc lập bằng `javac`:

```bash
mkdir -p extra-classes external-lib
javac --release 17 -encoding UTF-8 -d extra-classes \
      extra-src/demo/extra/Greeting.java
jar --create --file external-lib/greeting.jar -C extra-classes .
```

Trên Windows tạo trước hai thư mục `extra-classes` và `external-lib` bằng File Explorer hoặc PowerShell `New-Item -ItemType Directory -Force extra-classes,external-lib`; nhập lệnh `javac` thành một dòng. Kết quả là file `external-lib/greeting.jar` **không nằm trong `BOOT-INF/lib` của ứng dụng**.

### 8.4. Với JarLauncher: loader.path không có tác dụng như mong muốn

Chạy lại **JAR mặc định từ bước 8.2**:

```bash
java -Dloader.path=external-lib \
     -jar target/loader-demo-0.1.0-SNAPSHOT.jar
```

Vì archive này vẫn dùng `JarLauncher`, launcher không nạp external-lib bằng cơ chế riêng của PropertiesLauncher. Do đó phần output do ứng dụng in vẫn là:

```text
BOOT_APP_OK
EXTENSION=absent
```

Nếu kết quả khác, xem manifest xem có thực sự là JarLauncher không, hoặc kiểm tra class `demo.extra.Greeting` có vô tình nằm ở nguồn/đầu ra chính hay một dependency khác không.

### 8.5. Chuyển sang PropertiesLauncher

Trong `pom.xml`, thay phần `spring-boot-maven-plugin` hiện tại bằng:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layout>ZIP</layout>
    </configuration>
</plugin>
```

Build lại để không chạy artifact cũ:

```bash
./mvnw clean package
unzip -p target/loader-demo-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
```

Kỳ vọng `Main-Class` chuyển thành `org.springframework.boot.loader.launch.PropertiesLauncher`; `Start-Class` vẫn là main ứng dụng.

Chạy với external library:

```bash
java -Dloader.path=external-lib \
     -jar target/loader-demo-0.1.0-SNAPSHOT.jar
```

Hai dòng output do ứng dụng in:

```text
BOOT_APP_OK
EXTENSION=hello-from-external-jar
```

**Tại sao cùng source nhưng kết quả khác?** `PropertiesLauncher` đã thêm JAR trong `external-lib` vào classpath có hiệu lực. `Class.forName` của lớp ứng dụng bây giờ tìm được class `demo.extra.Greeting`. Đây là ví dụ chứng minh **cơ chế nạp class**, không phải khuyến nghị đưa plugin JAR tùy ý vào production.

Bạn cũng có thể đặt `loader.path=external-lib` trong file `loader.properties` ở thư mục làm việc, sau đó chạy `java -jar ...` mà không truyền `-Dloader.path`. Việc tìm thấy file properties phụ thuộc `loader.home` và các vị trí loader hỗ trợ; nếu chạy từ thư mục khác, cân nhắc dùng đường dẫn tuyệt đối để tránh sai vị trí.

### 8.6. Bảng quan sát của thí nghiệm

| Archive đang chạy | Cách chạy | Kỳ vọng |
|---|---|---|
| Maven JAR mặc định: JarLauncher | `java -jar app.jar` | `EXTENSION=absent` |
| JAR mặc định: JarLauncher | `java -Dloader.path=external-lib -jar app.jar` | Vẫn `EXTENSION=absent` |
| Maven ZIP layout: PropertiesLauncher | `java -jar app.jar`, không loader.path | `EXTENSION=absent` |
| Maven ZIP layout: PropertiesLauncher | `java -Dloader.path=external-lib -jar app.jar` | `EXTENSION=hello-from-external-jar` |

Bảng giả định đúng cấu trúc thư mục của ví dụ và không có config khác. Nếu các giá trị khác kỳ vọng, kiểm tra Main-Class/Start-Class, classpath source output, `loader.home` và file external library trước khi đổi code.

## 9. Xem manifest, nested JAR và launcher theo từng build tool

### 9.1. Maven

Từ root của project:

```bash
./mvnw clean package
jar tf target/loader-demo-0.1.0-SNAPSHOT.jar
unzip -p target/loader-demo-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
```

Tìm những entry:

```text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/loader/LoaderDemoApplication.class
BOOT-INF/lib/...
```

Nếu đã đổi layout ZIP, entry launcher thay đổi trong manifest; archive có thể vẫn chứa nhiều launcher class, nên **sự hiện diện của một file class không chứng minh launcher đang được chọn**. Dựa vào `Main-Class`.

### 9.2. Gradle

Trong project đã có Boot plugin:

```bash
./gradlew bootJar
jar tf build/libs/loader-demo-0.1.0-SNAPSHOT.jar
unzip -p build/libs/loader-demo-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
```

Khi cần WAR, dùng `bootWar` và kiểm tra file `.war` tương ứng:

```bash
./gradlew bootWar
jar tf build/libs/web-demo-0.1.0-SNAPSHOT.war
```

Tên file cuối chỉ minh họa. Nếu project tùy chỉnh `archiveFileName`, `version`, root name hoặc multi-module, hãy tìm đúng archive được sinh. **Không kiểm tra JAR `plain` rồi kết luận loader sai**: trong một số Gradle build có thể tồn tại cả JAR thường và bootJar.

### 9.3. Dùng Java để đọc manifest nếu thiếu unzip

Một chương trình Java 17 độc lập có thể đọc manifest của JAR hoặc WAR (đường dẫn truyền qua command line):

```java
import java.io.IOException;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class ReadManifest {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java ReadManifest <archive.jar-or-war>");
            System.exit(2);
        }

        try (JarFile archive = new JarFile(args[0])) {
            Manifest manifest = archive.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("No manifest");
            }

            Attributes attributes = manifest.getMainAttributes();
            System.out.println("Main-Class="
                    + attributes.getValue("Main-Class"));
            System.out.println("Start-Class="
                    + attributes.getValue("Start-Class"));
        }
    }
}
```

Lưu file tên `ReadManifest.java`, dùng JDK 17+:

```bash
javac --release 17 ReadManifest.java
java ReadManifest target/loader-demo-0.1.0-SNAPSHOT.jar
```

Nếu dùng JAR mặc định của ví dụ, hai dòng **stdout của chương trình kiểm tra** là:

```text
Main-Class=org.springframework.boot.loader.launch.JarLauncher
Start-Class=com.example.loader.LoaderDemoApplication
```

Nếu dùng PropertiesLauncher, dòng `Main-Class=...PropertiesLauncher` thay thế; nếu dùng executable WAR, `...WarLauncher`. Đây là chương trình Java Standard Library **biên dịch độc lập**, không cần Spring dependencies.

## 10. Hành vi classpath: khác biệt cần nắm

### 10.1. Nested classpath và thứ tự nạp

Trong Boot JAR/WAR, class ứng dụng thường được ưu tiên theo classpath mà launcher dựng. Thứ tự các nested dependency cũng có thể được mô tả bởi `BOOT-INF/classpath.idx` do plugin tạo. File index phục vụ việc kiểm soát thứ tự classpath khi khởi chạy archive bằng Boot Loader; không phải file cấu hình `spring.profiles.active`.

Khi mở rộng `loader.path` bằng PropertiesLauncher, classpath có thể chứa các phiên bản class/JAR trùng nhau với `BOOT-INF/lib`. **Class nào được nạp phụ thuộc loader và thứ tự classpath có hiệu lực**, không phải “bản mới nhất” hay “file có version lớn nhất”. Do đó thêm `vendor.jar` bên ngoài có thể vô tình ghi đè API hoặc gây `NoSuchMethodError`/`ClassCastException`/`LinkageError` khi version không tương thích.

Không cố giải quyết xung đột phiên bản bằng cách copy hàng loạt JAR vào external-lib rồi hy vọng Spring Boot tự chọn bộ đúng. Nên quản lý BOM/dependency version từ build tool và chỉ dùng external classpath với yêu cầu cụ thể.

### 10.2. Boot class loader và system class loader

Lớp ứng dụng được nạp bởi class loader của Spring Boot Launcher. Một số thư viện tự gọi `ClassLoader.getSystemClassLoader()` để tìm resource có thể không thấy lớp trong nested JAR; cách phổ biến là dùng **thread context class loader** hoặc class loader của class đang xử lý.

Ví dụ lấy resource đúng cách trong ứng dụng:

```java
try (var input =
        LoaderDemoApplication.class.getResourceAsStream("/banner.txt")) {
    if (input == null) {
        throw new IllegalStateException("Missing banner.txt");
    }
    // Đọc bytes từ stream; không ép resource trong JAR thành File.
}
```

Đây là đoạn Java minh họa **nằm trong method có xử lý IOException**; cần file `src/main/resources/banner.txt` trong classpath. Không phải chương trình độc lập.

### 10.3. Index file và Docker layers không phải launcher mới

- `BOOT-INF/classpath.idx` có thể mô tả thứ tự thư viện trong classpath.
- `BOOT-INF/layers.idx` mô tả lớp phân tách archive để tối ưu xây dựng container image.
- Không có launcher tên “LayersLauncher” chỉ vì JAR có layers metadata.
- Layer metadata **không tự tạo classloader khác** và không biến archive kiểu WAR thành JAR.

### 10.4. Giới hạn định dạng ZIP/JAR

Spring Boot nested jar mechanism yêu cầu nested JAR entry trong archive ngoài dùng phương thức lưu phù hợp (`STORED` ở cấp entry nested jar), để loader có thể định vị dữ liệu bên trong. Một script ZIP tự viết sai cách có thể tạo file vẫn giải nén được nhưng **không khởi chạy** đúng qua Boot Loader.

Nếu cần custom packaging, ưu tiên Spring Boot Maven/Gradle Plugin thay vì tự ghép archive thủ công. `jar tf` chỉ chứng minh archive có entry, không chứng minh manifest/classloader và dependencies đã đúng để chạy.

## 11. Những khái niệm dễ bị đánh đồng

| Khái niệm | Có giống launcher không? | Phân biệt |
|---|---|---|
| `SpringApplication.run` | Không | Bootstrap **Spring ApplicationContext** sau khi class đã được tải |
| `@SpringBootApplication` | Không | Annotation tổ hợp của cấu hình/auto-configuration/component scan |
| Maven `spring-boot:run` | Không | Goal chạy ứng dụng từ development classpath, không yêu cầu đóng gói executable JAR |
| Gradle `bootRun` | Không | Task JavaExec chạy từ runtime classpath, khác đường `java -jar` |
| `spring-boot:repackage` | Không | **Build-time**: tạo executable archive và manifest/loader |
| Gradle `bootJar` / `bootWar` | Không | **Build-time**: đóng gói archive; launcher chạy sau khi artifact khởi động |
| `java -cp` | Không | JVM classpath thông thường; không tự giải quyết nested JAR kiểu Boot |
| `loader.path` | Là cấu hình của PropertiesLauncher | Bổ sung thư viện/class vào classpath ứng dụng |
| `spring.config.additional-location` | Không | Nơi Spring tìm file cấu hình ứng dụng |
| `java -jar app.war` | Đường launcher WAR | JVM dùng Main-Class/WarLauncher nếu WAR executable |
| Deploy WAR lên external Tomcat | Đường servlet container | Không có nghĩa external Tomcat gọi WarLauncher |
| Shaded uber JAR | Không | Hợp nhất class vào JAR, khác cách Spring Boot giữ nested dependency jars |
| Native image GraalVM | Không theo đường JVM JAR loader | Native executable có mô hình đóng gói/khởi động riêng |

Đừng đổ lỗi cho Spring Boot Loader khi lỗi nằm ở **application context startup** (ví dụ thiếu datasource, port đang bận). Ngược lại, lỗi `ClassNotFoundException` trước khi banner Spring xuất hiện thường đáng kiểm tra manifest/classpath/nested dependencies.

## 12. Lỗi thường gặp và cách chẩn đoán

### 12.1. `no main manifest attribute`

**Dấu hiệu:** `java -jar app.jar` báo không có main manifest attribute.

**Nguyên nhân có thể:** đang chạy JAR thường do `jar` tạo, hoặc Maven plugin `repackage` chưa thực thi, hoặc file build sai.

**Cách kiểm tra:** xem `META-INF/MANIFEST.MF`. Với Maven, kiểm tra plugin `spring-boot-maven-plugin`/goal `repackage` và file đúng sau `package`. Với Gradle, chọn output của `bootJar` thay vì plain jar.

### 12.2. `ClassNotFoundException: org.springframework.boot.loader.launch.JarLauncher`

**Nguyên nhân có thể:** manifest trỏ tới Boot 3.2+ launcher nhưng archive không có loader classes ở gốc; tự sửa manifest của plain JAR, hoặc trộn class/package cũ với bản mới.

**Cách xử lý:** không copy riêng manifest; tạo lại archive bằng plugin phù hợp. Xem `jar tf` để xác nhận loader classes ở root và đường class/package chính xác cho **phiên bản Spring Boot thực tế**.

### 12.3. `ClassNotFoundException` với class ứng dụng

**Nguyên nhân có thể:** `Start-Class` sai package/class, project có nhiều main class và plugin chọn sai, class không được compile hoặc bị exclude khỏi archive.

**Cách xử lý:** kiểm tra `Start-Class`, entry trong `BOOT-INF/classes`/`WEB-INF/classes`, source package và thuộc tính main class của plugin. Đừng thay `Main-Class` bằng main ứng dụng để né bước kiểm tra.

### 12.4. `NoClassDefFoundError` với thư viện bên thứ ba

**Nguyên nhân có thể:** dependency thiếu trong `BOOT-INF/lib` hoặc `WEB-INF/lib`, bị exclude/đặt scope sai, hoặc version không tương thích.

**Cách xử lý:** kiểm tra dependency tree Maven/Gradle và các entry thực tế của archive. Đừng mặc định một thư viện thấy được khi chạy từ IDE/`bootRun` cũng đã có trong executable JAR.

### 12.5. Có `-Dloader.path` nhưng external JAR vẫn không được nạp

**Các câu hỏi phải kiểm tra:**

1. Manifest có thật sự chọn `PropertiesLauncher` không?
2. `loader.path` trỏ đúng thư mục/JAR được hỗ trợ không?
3. Đường dẫn tương đối được resolve theo `loader.home`/working directory nào?
4. File có quyền đọc và là JAR hợp lệ không?
5. Có class name/package trùng ở các JAR khác dẫn tới loader nạp một class khác không?

Một phiên `JarLauncher` **không biến thành PropertiesLauncher** chỉ vì bạn cung cấp `-Dloader.path`.

### 12.6. Executable WAR chạy bằng `java -jar` nhưng deploy Tomcat lỗi

**Nguyên nhân có thể:** thiếu `SpringBootServletInitializer` hoặc mapping `configure`, Tomcat ngoài không tương thích Servlet/Jakarta namespace, trùng servlet container dependency trong `WEB-INF/lib`, hoặc thiếu cấu hình context path.

**Cách xử lý:** phân biệt rõ đường chạy WAR tự chứa với đường external container. Kiểm tra `WEB-INF/lib-provided`/provided scope, server version và log triển khai của container; không chỉ kiểm tra `Main-Class`.

### 12.7. Một JAR chạy ở IDE nhưng lỗi với `java -jar`

IDE, Maven `spring-boot:run` và Gradle `bootRun` thường dùng development classpath. Boot executable JAR dùng nested classpath của archive. Kiểm tra packaging, dependencies, file resources, JVM version, profile/environment và những tài nguyên được truy cập qua `File` thay vì stream classpath.

## 13. Lựa chọn launcher theo tình huống

| Tình huống | Khuyến nghị |
|---|---|
| Microservice Spring Boot dạng executable JAR | **JarLauncher mặc định** qua Maven repackage/Gradle bootJar |
| CLI/batch Spring Boot đóng gói một JAR | **JarLauncher**; không cần web server hay WAR |
| Web app cần executable WAR và/hoặc deploy servlet container ngoài | **WarLauncher** cho `java -jar`; có cấu hình `SpringBootServletInitializer` cho deploy ngoài |
| Cần nạp thư viện bổ sung từ thư mục được kiểm soát | **PropertiesLauncher** với layout phù hợp, `loader.path` và kiểm thử tích hợp |
| Chỉ cần đổi `application.yml` ở môi trường deploy | Không cần đổi launcher; dùng **Spring externalized configuration** |
| Muốn đổi `server.port` hoặc profile | Không cần đổi launcher; truyền application args/env/`spring.*` |
| Build image tối ưu cache | Dùng container layers/layered JAR hoặc buildpacks, không nhất thiết đổi launcher |
| Muốn đưa logic plugin tùy ý vào runtime | Cân nhắc rủi ro bảo mật/classpath; PropertiesLauncher có thể hữu ích nhưng cần whitelist, kiểm thử và kiểm soát phiên bản |
| Dự án muốn giảm lỗi vận hành, build bất biến | Ưu tiên JarLauncher/WarLauncher mặc định và dependencies cố định trong artifact |

**Nguyên tắc:** dùng launcher **ít tùy biến nhất** vẫn đáp ứng yêu cầu triển khai. PropertiesLauncher có ích khi classpath thực sự phải thay đổi bên ngoài artifact, nhưng nó cũng tạo thêm một nguồn thay đổi hành vi không được mô tả đầy đủ chỉ bởi hash của file ứng dụng.

## 14. Bảo mật và tái lập build với external classpath

Khi dùng `PropertiesLauncher`, một file `external-lib/unknown.jar` có thể chứa bytecode được thực thi trong JVM ứng dụng với quyền của tiến trình. Đây **không phải nơi lưu các plugin không tin cậy** hoặc coi như một sandbox. Launcher chỉ làm công việc tải class, không tự quét lỗ hổng, ký số, xác minh license hay cô lập quyền truy cập.

Checklist an toàn:

1. Chỉ cho pipeline/nhóm vận hành được ủy quyền ghi vào thư mục external-lib.
2. Pin phiên bản và checksum/signature nếu quy trình triển khai yêu cầu; log build manifest/phiên bản external dependency.
3. Quét dependency/vulnerability trong cả nested `BOOT-INF/lib` **và** external JAR.
4. Giữ file permissions chặt chẽ; tránh cho người dùng chưa tin cậy tác động `loader.path`.
5. Kiểm tra conflict class/version bằng integration test trên đúng artifact và đúng external library set.
6. Tránh dùng external JAR để âm thầm thay thế thư viện bảo mật cốt lõi nếu không có review.
7. Ghi rõ `loader.home` và working directory của systemd/container/script startup.
8. Nếu cần rollback, rollback **cả file ứng dụng lẫn external-lib**; một artifact không đổi có thể hoạt động khác khi external-lib thay đổi.

Trong triển khai container, một directory mount có thể thay đổi runtime classpath ngoài image bất biến. Nếu đó không phải yêu cầu bắt buộc, đóng gói dependency vào image/artifact và để config dữ liệu bên ngoài sẽ dễ tái lập hơn.

## 15. Checklist xác minh sau khi đóng gói

1. **Xác định loại artifact:** `.jar` hay `.war`? Có thực sự là executable archive do Boot plugin tạo?
2. **Xem `Main-Class`:** khớp `JarLauncher`, `WarLauncher` hoặc `PropertiesLauncher`?
3. **Xem `Start-Class`:** trỏ đúng class có `public static void main(String[] args)`?
4. **Kiểm tra layout:** `BOOT-INF/classes/lib` cho JAR, `WEB-INF/classes/lib/lib-provided` cho WAR?
5. **Kiểm tra nested dependencies:** JAR cần ở những thư mục được launcher nhận diện; không phụ thuộc vào classpath IDE.
6. **Thực thi `java -jar`:** kiểm tra exit code/log ứng dụng và chức năng chính, không chỉ `jar tf`.
7. **Với PropertiesLauncher:** xác nhận `loader.path`, `loader.home`, vị trí `loader.properties` và cách chọn `loader.main` nếu có override.
8. **Với executable WAR:** kiểm thử riêng hai đường `java -jar` và deploy external container (nếu cả hai là yêu cầu).
9. **Kiểm tra đường dẫn class/resource:** tránh giả định nested JAR hoặc resource luôn là file vật lý.
10. **Đối chiếu Spring Boot version:** class launcher đã đổi package giữa Boot 3.1 và 3.2; không trộn tài liệu của các phiên bản.
11. **Kiểm soát nguồn external code:** ghi nhận hash/version/quyền truy cập của thư viện ngoài.
12. **Tránh thay đổi thủ công archive sau khi build:** nếu cần thay layout, chỉnh Maven/Gradle build script và build lại để có artifact tái lập.

### Tài liệu chính thức

- [Spring Boot 3.5 — Launching Executable Jars](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/launching.html)
- [Spring Boot 3.5 — Nested JARs](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.5 — PropertiesLauncher Features](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/property-launcher.html)
- [Spring Boot 3.5 — Executable Jar Restrictions](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/restrictions.html)
- [Spring Boot 3.5 — Maven Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [PropertiesLauncher Java API (Spring Boot 3.5)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/loader/launch/PropertiesLauncher.html)

**Ghi nhớ:** `JarLauncher` khởi chạy **JAR theo BOOT-INF**; `WarLauncher` khởi chạy **WAR theo WEB-INF**, kể cả thư viện `lib-provided` ở đường executable; `PropertiesLauncher` thêm quyền **điều chỉnh classpath và main class**. Cả ba đều là bootstrap của Spring Boot Loader: chúng dựng môi trường nạp class, rồi gọi đúng ứng dụng của bạn theo manifest/cấu hình.
