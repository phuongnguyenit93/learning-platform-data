# Spring Boot Maven Plugin và mục đích của repackage

## 1. Bài toán đóng gói Spring Boot

Trong Maven, một dự án `packaging=jar` thường được Maven JAR Plugin đóng gói thành JAR chứa các lớp `.class` và tài nguyên của ứng dụng. Những dependency như Spring Framework, Jackson hay thư viện logging vẫn là các JAR khác; chỉ có ordinary JAR không đồng nghĩa bạn đã có toàn bộ runtime classpath để chạy từ một tệp duy nhất.

**Spring Boot Maven Plugin** là plugin có tọa độ `org.springframework.boot:spring-boot-maven-plugin`. Goal trọng tâm của bài là **`spring-boot:repackage`**. Nó đọc JAR hoặc WAR mà bước packaging thông thường đã tạo, rồi biến thành **executable archive**: đóng các thư viện cần thiết vào archive, thêm Spring Boot loader và metadata để khởi chạy qua `java -jar`.

Mục đích thực tế:

- Đơn giản hóa triển khai: ứng dụng và các runtime dependencies nằm trong một file JAR/WAR có cấu trúc Boot hiểu được.
- Giảm việc tự dựng `-classpath` dài và dễ sai khi chạy sản phẩm.
- Tạo cơ chế bootstrap biết tải nested JARs trong archive.
- Giữ cấu hình bản phát hành gắn với đúng nguồn, phiên bản Maven và dependency graph.
- Có thể tạo **executable JAR** hoặc **executable WAR** theo nhu cầu triển khai.

**Repackage không biên dịch Java, không chạy lại unit tests và không tự biến ứng dụng thành native binary.** Nó là bước thay đổi nội dung archive sau packaging.

```text
Source Java + resources + dependencies
     |
     v
Maven compile / resources / test
     |
     v
Maven JAR Plugin hoặc Maven WAR Plugin
     |     JAR/WAR thông thường
     v
Spring Boot Maven Plugin: repackage
     |
     +-- Spring Boot loader classes
     +-- cấu trúc BOOT-INF hoặc WEB-INF
     +-- nested runtime dependency JARs
     +-- manifest Main-Class / Start-Class
     |
     v
Executable Spring Boot JAR/WAR
     |
     +-- java -jar ...
     +-- install / deploy / container workflow khi phù hợp
```

Bài học dùng phiên bản **Spring Boot 3.4.2** cho các ví dụ Java 17. Đây là phiên bản được cố định để hướng dẫn, **không tuyên bố là bản mới nhất**. Khi nâng phiên bản, đọc tài liệu của đúng Spring Boot Maven Plugin vì các tham số và mặc định có thể thay đổi.

## 2. Plugin, goal, phase và packaging là những khái niệm khác nhau

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Plugin | `spring-boot-maven-plugin` | Cung cấp các goals liên quan Spring Boot |
| Goal | `spring-boot:repackage` | Biến JAR/WAR đã có thành executable archive |
| Goal khác | `spring-boot:run` | Chạy ứng dụng ở chế độ development |
| Goal khác | `spring-boot:build-image` | Tạo OCI container image theo workflow buildpacks |
| Phase | `package` | Điểm trong lifecycle nơi archive được đóng gói |
| Packaging | `jar` hoặc `war` | Chọn mapping đóng gói thông thường của dự án |
| Execution | `repackage` | Một lần gọi goal gắn vào lifecycle theo cấu hình |
| Artifact | `app-1.0.jar`, `app-1.0-exec.jar` | Tệp build dùng để chạy hoặc phân phối |

Một lần chạy Maven lifecycle gồm nhiều phase. Khi gọi `mvn package`, Maven đi qua compilation, test và những goals đã gắn vào phase package. Trong dự án dùng Spring Boot Plugin đúng cách, **JAR/WAR thường được tạo trước, sau đó mới repackage**.

So sánh các lệnh:

```bash
mvn clean package
mvn spring-boot:run
mvn spring-boot:repackage
mvn package spring-boot:repackage
```

- `clean package`: cách bình thường để tạo archive theo các executions đã bind.
- `spring-boot:run`: khởi động từ project/classpath trong quá trình phát triển, không phải bằng chứng JAR đã được repackaged.
- `spring-boot:repackage` gọi trực tiếp: cần archive đầu vào đã có; không phải lệnh tự compile/package mọi thứ trước đó.
- `package spring-boot:repackage`: thích hợp khi muốn gọi repackage thủ công và **chưa** cấu hình một execution repackage tự động. Nếu đã auto-bind, lệnh này có nguy cơ gọi lại repackage trùng.

Goal `repackage` có default phase là `package`. Nhưng việc nó tự tham gia lifecycle còn phụ thuộc vào **plugin configuration/execution**; chỉ thêm Spring Boot dependency hoặc chỉ import BOM không đảm bảo goal sẽ chạy.

## 3. Thứ tự quan trọng: archive phải được tạo trước repackage

Với `<packaging>jar</packaging>`:

```text
mvn clean package
  ├─ resources:resources
  ├─ compiler:compile
  ├─ compiler:testCompile
  ├─ surefire:test
  ├─ jar:jar              -> ordinary JAR
  └─ spring-boot:repackage -> executable JAR
```

Với `<packaging>war</packaging>`, mục packaging tương ứng do Maven WAR Plugin đảm nhiệm. Repackage **không tự thay thế cơ chế tạo archive đầu tiên**. Nếu nó chạy trước goal sinh archive, bạn có thể gặp lỗi thiếu source artifact.

Khi có nhiều custom plugin executions cùng phase `package`, hãy xem thứ tự goals, nhất là khi POM khai báo lại JAR/WAR Plugin một cách đặc biệt. Với những plugin khai báo tường minh và mục đích tương tự, đảm bảo JAR/WAR Plugin tạo output **trước** Spring Boot Plugin.

**Quy tắc thực hành:** nếu đã bind repackage vào build, dùng `mvn clean package` và kiểm tra log. Không “chữa” lỗi source archive bằng cách gọi thêm repackage trước build hoặc copy một JAR cũ vào `target/`.

## 4. Ordinary JAR và executable Spring Boot JAR

JAR thông thường có thể chứa:

```text
META-INF/MANIFEST.MF
dev/course/BootRepackageApplication.class
dev/course/GreetingService.class
META-INF/maven/...
```

Đối với executable JAR layout của Spring Boot 3.4.x, bạn thường thấy cấu trúc:

```text
boot-repackage-demo-1.0.0-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   └── dev/course/
    │       ├── BootRepackageApplication.class
    │       └── GreetingService.class
    ├── lib/
    │   ├── spring-boot-3.4.2.jar
    │   ├── spring-context-....jar
    │   └── ... (những JAR phụ thuộc khác)
    ├── classpath.idx (khi có)
    └── layers.idx    (khi có)
```

Các mục trên chỉ là các entries tiêu biểu, không phải danh sách đầy đủ. Thứ tự ZIP entries và một số metadata tùy plugin/version.

**BOOT-INF/classes** chứa compiled application classes/resources; **BOOT-INF/lib** chứa runtime dependency JARs lồng. Spring Boot loader biết cách tìm thư viện trong nested JARs và tạo classloader cho ứng dụng.

Java classpath truyền thống không tự biết phải lấy lớp ở `BOOT-INF/classes` và tự mở mọi JAR dưới `BOOT-INF/lib`. Vì vậy:

```bash
java -jar target/boot-repackage-demo-1.0.0-SNAPSHOT.jar
```

là cách chạy tiêu chuẩn của Spring Boot executable JAR, còn lệnh:

```bash
java -cp target/boot-repackage-demo-1.0.0-SNAPSHOT.jar dev.course.BootRepackageApplication
```

**không tương đương**, vì JVM classpath thông thường không dùng cơ chế nested-archive loader của Boot theo cùng cách.

### 4.1. Repackage khác Maven Shade Plugin

Maven Shade Plugin thường gom/biến đổi các dependency class/resources theo cơ chế shading, có thể relocation package names và resource transformers. Spring Boot Plugin thường giữ các dependency JARs **lồng dưới BOOT-INF/lib** và thêm loader.

Cả hai có thể tạo archive chứa runtime libraries, nhưng chúng dùng cách cấu trúc/classloading khác nhau. Không cần Shade Plugin chỉ để chạy một Spring Boot app thông thường bằng `java -jar`; ghép tùy tiện hai plugin có thể gây xung đột archive/manifest.

## 5. Manifest và đường khởi động Main-Class / Start-Class

Sau repackage, manifest của executable JAR thường có các entries tương tự:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.course.BootRepackageApplication
Spring-Boot-Version: 3.4.2
Spring-Boot-Classes: BOOT-INF/classes/
Spring-Boot-Lib: BOOT-INF/lib/
```

Đây là **ví dụ các entry quan trọng**, không phải log/manifest thật nguyên văn. Plugin có thể thêm những metadata và wrapping khác.

- **`Main-Class`** trỏ tới **Spring Boot launcher** để JVM gọi trước.
- **`Start-Class`** chỉ rõ lớp ứng dụng được launcher chạy sau khi chuẩn bị classpath.
- **`Spring-Boot-Classes` / `Spring-Boot-Lib`** liên quan những vị trí classes/dependencies trong archive.

Với layout WAR, `Main-Class` thường là `org.springframework.boot.loader.launch.WarLauncher`.

**Không đổi trực tiếp `Main-Class` trong Maven JAR Plugin** thành tên application rồi mong Spring Boot loader vẫn boot đúng: goal repackage tự điều khiển manifest. Nếu có nhiều lớp `main` và plugin không chọn được, cấu hình `mainClass` của Spring Boot Plugin.

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>dev.course.BootRepackageApplication</mainClass>
    </configuration>
</plugin>
```

Đây chỉ là snippet đặt trong `build/plugins`, không phải một POM hoàn chỉnh. Nhớ phân biệt **cấu hình `mainClass`** và **manifest `Start-Class`** được sinh ra.

## 6. Spring Boot starter parent có sẵn execution repackage

Nhiều ứng dụng Spring Boot dùng parent:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.2</version>
    <relativePath/>
</parent>
```

Parent này cung cấp dependency/plugin management và đã cấu hình execution **ID `repackage`** cho Spring Boot Maven Plugin. Vì vậy khi dùng starter parent, thường chỉ khai báo:

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

Maven hợp nhất cấu hình parent, và goal repackage được chạy trong phase package theo setup của parent.

**Không thêm thêm một execution ID khác cùng goal repackage** chỉ vì bạn thấy trên internet ví dụ dùng `<executions>`. Nếu parent đã có execution, một execution mới có thể gây chạy trùng. Khi cần cấu hình execution kế thừa, dùng **ID repackage** tương ứng.

Phân biệt:

| Thiết lập | Kết quả |
| --- | --- |
| Starter parent + Boot Plugin trong build/plugins | Có execution repackage được cấu hình |
| Chỉ thêm `spring-boot-starter` dependency | Chưa chắc có Boot Plugin/repackage |
| Chỉ import `spring-boot-dependencies` BOM | Có dependency versions, **không tự có plugin executions** |
| Parent nội bộ + Boot Plugin tự khai báo goal | Có thể bind repackage nếu cấu hình đúng |
| Chỉ chạy `spring-boot:run` | Chạy app từ project, không chứng minh artifact executable được tạo |

## 7. Dự án Spring Boot Java 17 có thể chạy từ đầu

Ví dụ là một **non-web Spring Boot application**: nó khởi tạo Spring Context, in lời chào qua `CommandLineRunner` rồi đóng Context. Chọn cách này để kiểm chứng `java -jar` mà không cần database, server hoặc port.

### 7.1. Cấu trúc thư mục

```text
boot-repackage-demo/
├── pom.xml
└── src/
    ├── main/java/dev/course/
    │   ├── BootRepackageApplication.java
    │   └── GreetingService.java
    └── test/java/dev/course/
        └── GreetingServiceTest.java
```

Cần JDK 17+, Maven tương thích (ví dụ Maven 3.9.x) và khả năng tải các dependencies lần đầu nếu local cache chưa có. Lưu source có tiếng Việt bằng UTF-8.

### 7.2. POM đầy đủ

Tạo `boot-repackage-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.course</groupId>
    <artifactId>boot-repackage-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Những điểm cần đọc:

1. Parent 3.4.2 quản lý starter dependencies và execution repackage; Boot Plugin được khai báo trong build.
2. `spring-boot-starter` cung cấp Spring Boot runtime nhưng không cấu hình một HTTP server.
3. `spring-boot-starter-test` ở scope `test` cấp JUnit Jupiter cho việc kiểm thử.
4. Java 17 và source UTF-8 được cấu hình rõ ràng.
5. POM không chứa custom repackage execution vì parent đã có.
6. Project không dùng parent nội bộ, không cần file hay module khác để chạy.

### 7.3. GreetingService.java

Tạo `src/main/java/dev/course/GreetingService.java`:

```java
package dev.course;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

`@Service` cho phép component scanning tạo bean. Hàm `greet` dùng API Java 17 và bảo vệ input null/blank.

### 7.4. BootRepackageApplication.java

Tạo `src/main/java/dev/course/BootRepackageApplication.java`:

```java
package dev.course;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BootRepackageApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(
                             BootRepackageApplication.class, args)) {
            // Context sẽ được đóng sau CommandLineRunner.
        }
    }

    @Bean
    CommandLineRunner greetingRunner(GreetingService service) {
        return args -> System.out.println(
                "APP_READY: " + service.greet(" Lan "));
    }
}
```

SpringApplication khởi tạo Context, gọi `CommandLineRunner` rồi trả về Context cho mã main. Method main đóng Context qua try-with-resources. Vì project không có embedded server, tiến trình kết thúc sau tác vụ.

Dòng **stdout do chương trình tạo**:

```text
APP_READY: Xin chào, Lan!
```

Spring Boot có thể in banner và startup logs theo cấu hình; phần chạy dưới đây tắt chúng để dễ thấy dòng ứng dụng.

### 7.5. GreetingServiceTest.java

Tạo `src/test/java/dev/course/GreetingServiceTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void greetsVietnameseName() {
        assertEquals("Xin chào, Lan!",
                service.greet(" Lan "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet(" "));
    }

    @Test
    void rejectsNullName() {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet(null));
    }
}
```

Đây là **3 unit tests**, không khởi động Spring context, không mở network. Surefire/parent plugin setup của Spring Boot dùng test classpath có JUnit Jupiter để thực thi chúng.

### 7.6. Build và kết quả cần quan sát

Từ thư mục `boot-repackage-demo`:

```bash
mvn -version
mvn clean package
```

Nếu JDK/Maven/registry phù hợp, Maven biên dịch mã, chạy 3 tests và tạo executable Spring Boot JAR. Các tệp có thể thấy:

```text
target/classes/dev/course/BootRepackageApplication.class
target/classes/dev/course/GreetingService.class
target/test-classes/dev/course/GreetingServiceTest.class
target/boot-repackage-demo-1.0.0-SNAPSHOT.jar
target/boot-repackage-demo-1.0.0-SNAPSHOT.jar.original
target/surefire-reports/
```

Tệp `.jar.original` là **bản backup local thường xuất hiện khi repackage thay artifact chính**. Nó không phải artifact classifier `original` để tiêu thụ qua Maven repository.

Kết quả kiểm thử trong log tương ứng:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
... spring-boot-maven-plugin:3.4.2:repackage (repackage) ...
BUILD SUCCESS
```

Đây là **các số liệu/cụm từ cần tìm**, không phải log nguyên văn.

### 7.7. Chạy JAR đã được repackage

```bash
java -jar target/boot-repackage-demo-1.0.0-SNAPSHOT.jar --spring.main.banner-mode=off --logging.level.root=OFF
```

Dòng stdout do code ứng dụng sinh ra **chính xác**:

```text
APP_READY: Xin chào, Lan!
```

Không thêm JAR dependencies vào CLI classpath: Spring Boot loader trong executable archive quản lý nested libraries. Nếu vẫn còn startup log từ một thành phần nào đó, hãy phân biệt nó với dòng do `CommandLineRunner` in; output từ logging không phải stdout logic ổn định của business code.

### 7.8. Kiểm tra contents

```bash
jar tf target/boot-repackage-demo-1.0.0-SNAPSHOT.jar
```

Tìm entries:

```text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/course/BootRepackageApplication.class
BOOT-INF/classes/dev/course/GreetingService.class
BOOT-INF/lib/spring-boot-3.4.2.jar
```

Không khẳng định output chỉ có bốn entry. Bạn sẽ thấy nhiều dependency JARs khác, manifest và metadata. Nếu tệp chỉ có `dev/course/*.class` ở root và không có BOOT-INF, có thể bạn đang xem ordinary JAR chưa được repackage.

## 8. Kiểm tra manifest bằng một chương trình Java 17 độc lập

Tạo tệp `InspectBootJar.java` **bên ngoài dự án Spring Boot**, trong thư mục chứa JAR hoặc một thư mục thử nghiệm. Nó không cần thư viện ngoài JDK:

```java
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class InspectBootJar {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Cần một đường dẫn JAR");
        }

        try (JarFile jar = new JarFile(args[0])) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("Không có manifest");
            }

            var attributes = manifest.getMainAttributes();
            System.out.println("Main-Class="
                    + attributes.getValue("Main-Class"));
            System.out.println("Start-Class="
                    + attributes.getValue("Start-Class"));

            boolean hasMainClass = jar.getEntry(
                    "BOOT-INF/classes/dev/course/"
                    + "BootRepackageApplication.class") != null;
            boolean hasNestedDependency = jar.stream().anyMatch(
                    entry -> entry.getName().startsWith("BOOT-INF/lib/")
                            && entry.getName().endsWith(".jar"));

            System.out.println("BootClass=" + hasMainClass);
            System.out.println("NestedDependency=" + hasNestedDependency);
        }
    }
}
```

Chạy từ vị trí có `InspectBootJar.java`, dùng đường dẫn đến JAR tương ứng; nếu bạn đặt inspector ở root project:

```bash
java InspectBootJar.java target/boot-repackage-demo-1.0.0-SNAPSHOT.jar
```

Với project mẫu, stdout kỳ vọng:

```text
Main-Class=org.springframework.boot.loader.launch.JarLauncher
Start-Class=dev.course.BootRepackageApplication
BootClass=true
NestedDependency=true
```

Chương trình xác minh **manifest và archive layout thực tế**. Nó được viết cho JAR; nếu dùng kiểm tra WAR, hai assertions về `BOOT-INF` sẽ false vì WAR có đường dẫn `WEB-INF`. Không dùng false đó để kết luận WAR đóng gói sai.

## 9. Không có starter parent: cần tự cấu hình repackage

Một tổ chức có parent POM riêng có thể chỉ import BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.4.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

BOM quản lý **dependency versions**, không tự thêm plugin execution. Nếu muốn repackage tự chạy trong Maven lifecycle, cấu hình Spring Boot Plugin với version/execution:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>

        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.4.2</version>
            <executions>
                <execution>
                    <id>repackage</id>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Hai đoạn này **thuộc một POM hoàn chỉnh lớn hơn**, không phải POM chạy trực tiếp. Dự án phải bổ sung `project`, coordinates, dependencies và những cấu hình cần thiết. Đặt `maven-jar-plugin` trước Spring Boot Plugin trong danh sách giúp thể hiện thứ tự đóng ordinary archive rồi repackage. Goal `repackage` có default phase `package`; có thể viết tường minh:

```xml
<execution>
    <id>repackage</id>
    <phase>package</phase>
    <goals>
        <goal>repackage</goal>
    </goals>
</execution>
```

**Không thêm execution thứ hai** cùng mục tiêu, và không gắn goal vào phase trước khi archive đầu vào tồn tại.

Điểm khác giữa hai phương án:

| Đặc điểm | Starter parent | Chỉ import Spring Boot BOM |
| --- | --- | --- |
| Managed Spring dependencies | Có | Có |
| Parent build defaults | Có | Không tự kế thừa |
| Plugin execution repackage chuẩn | Đã cấu hình khi plugin được sử dụng | Phải tự thiết lập |
| Plugin version management | Có những mặc định của parent | Tự quản lý/pluginManagement nội bộ |
| Parent nội bộ tùy ý | Chỉ một parent trực tiếp | Có thể dùng BOM với parent riêng |

Xem `mvn help:effective-pom` khi nghi ngờ POM cha, profiles hoặc pluginManagement đã thay hành vi.

## 10. Classifier exec để giữ ordinary JAR và executable JAR

Mặc định `spring-boot:repackage` **không đặt classifier**, nên executable archive thay thế primary artifact của project; original JAR thường được đổi thành tệp backup `.jar.original` ở output directory.

Đây là hành vi phù hợp với một application chỉ dùng để chạy. Nhưng Spring Boot executable JAR có lớp ứng dụng dưới `BOOT-INF/classes`, nên **không nên dùng nó làm ordinary library dependency** của một module Java khác.

Nếu cần cả hai variants:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <classifier>exec</classifier>
    </configuration>
</plugin>
```

Với starter parent, cấu hình này sử dụng execution `repackage` có sẵn. Sau package:

```text
target/boot-repackage-demo-1.0.0-SNAPSHOT.jar
target/boot-repackage-demo-1.0.0-SNAPSHOT-exec.jar
```

- File không classifier là ordinary JAR, có thể làm dependency ở classpath bình thường.
- File classifier `exec` là executable Boot JAR với nested dependencies/loader.
- Nếu `attach=true` (mặc định), Maven có thể `install`/`deploy` cả artifact chính và executable attachment.
- Khi muốn chạy app, phải dùng `java -jar target/boot-repackage-demo-1.0.0-SNAPSHOT-exec.jar`.

Một phương án kiến trúc sạch hơn cho nhiều project là **tách module library khỏi module boot-application**. Khi đó các module khác phụ thuộc library JAR, còn app Boot phụ thuộc library và được repackaged để triển khai.

### 10.1. attach=false và skip không giống classifier

Ví dụ:

```xml
<configuration>
    <classifier>exec</classifier>
    <attach>false</attach>
</configuration>
```

Đây là snippet cấu hình thử nghiệm. Repackaged archive có classifier vẫn có thể xuất hiện dưới `target/`, nhưng `attach=false` nghĩa là **không gắn nó vào project để Maven install/deploy như attachment**.

Ngược lại, `skip=true` yêu cầu bỏ qua chính goal repackage theo cấu hình. Đặt classifier chỉ đổi tên/identity của variant, **không tự tắt attach**.

Các tham số cần nhớ:

| Tham số | Vai trò |
| --- | --- |
| `attach` | Đăng ký repackaged artifact cho install/deploy (mặc định true) |
| `classifier` | Tạo variant như `exec` bên cạnh primary artifact |
| `mainClass` | Chọn lớp khởi động của ứng dụng |
| `layout` | Chọn cấu trúc JAR, WAR, ZIP/DIR hoặc NONE |
| `skip` | Bỏ qua repackage khi được bật |
| `includes`/`excludes` | Lọc dependencies được đưa vào archive |
| `excludeDevtools` | Loại `spring-boot-devtools` khỏi archive theo mặc định |
| `excludeDockerCompose` | Loại `spring-boot-docker-compose` theo mặc định của phiên bản |
| `layers` | Cấu hình layer metadata |
| `outputTimestamp` | Ổn định timestamp entries hỗ trợ reproducibility |
| `requiresUnpack` | Chọn một số dependencies cần unpack khi chạy |

Không dùng excludes bừa để giảm kích thước nếu dependency đó cần ở runtime. Một archive nhỏ hơn nhưng thiếu class lúc chạy là artifact sai.

## 11. Spring Boot WAR: khác biệt so với executable JAR

WAR dành cho ứng dụng servlet web. Khi Spring Boot Plugin repackage WAR với layout tương ứng, cấu trúc điển hình là:

```text
boot-war-demo-1.0.0-SNAPSHOT.war
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/WarLauncher.class
└── WEB-INF/
    ├── classes/
    │   └── dev/course/WarDemoApplication.class
    ├── lib/
    │   └── ... runtime dependency JARs ...
    └── lib-provided/
        └── ... provided dependencies ...
```

Khác biệt quan trọng:

| Mục | Executable JAR | Executable WAR |
| --- | --- | --- |
| Packaging | `jar` | `war` |
| Lớp ứng dụng | `BOOT-INF/classes` | `WEB-INF/classes` |
| Nested runtime jars | `BOOT-INF/lib` | `WEB-INF/lib` |
| Provided server deps | Không dùng mô hình WEB-INF/lib-provided | `WEB-INF/lib-provided` |
| Launcher | Thường `JarLauncher` | Thường `WarLauncher` |
| Có thể chạy bằng `java -jar` | Có khi repackaged đúng | Có khi repackaged đúng |
| Deploy trực tiếp vào servlet container ngoài | Không phải cách thường dùng | Có thể với WAR/initializer/container phù hợp |

Trong Spring Boot 3.x, ứng dụng Servlet dùng Jakarta Servlet namespace. External servlet container phải tương thích (ví dụ Tomcat 10.1 theo dải phiên bản hỗ trợ), không thể giả định Tomcat 9/Javax Servlet cũ triển khai được một WAR Spring Boot 3.

**Spring WebFlux thuần reactive không được hỗ trợ triển khai WAR truyền thống theo hướng dẫn WAR Servlet của Spring Boot.**

## 12. Dự án WAR riêng: đóng gói và khởi chạy HTTP endpoint

Ví dụ thứ hai **là một dự án độc lập**, không trộn với project CLI ở mục 7.

### 12.1. Cấu trúc

```text
boot-war-demo/
├── pom.xml
└── src/
    ├── main/java/dev/course/
    │   ├── WarDemoApplication.java
    │   └── GreetingController.java
    └── test/java/dev/course/
        └── GreetingControllerTest.java
```

### 12.2. POM WAR đầy đủ

Tạo `boot-war-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.course</groupId>
    <artifactId>boot-war-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
            </plugin>
        </plugins>
    </build>
</project>
```

Vì sao dùng `spring-boot-starter-tomcat` với scope `provided`?

- Khi deploy WAR lên servlet container ngoài, server đã cung cấp Tomcat/Servlet runtime; không nên đưa một embedded Tomcat vào `WEB-INF/lib` gây va chạm.
- Khi repackage executable WAR, Boot Plugin đưa các provided dependencies phù hợp vào `WEB-INF/lib-provided` để `java -jar ...war` vẫn chạy embedded container.
- Nếu xóa hết dependency web server thay vì dùng `provided`, executable WAR có thể thiếu môi trường để khởi động.

Spring Boot starter parent có cấu hình Maven WAR Plugin tương ứng với packaging war. Không cần tự khai báo một plugin WAR khác chỉ để làm ví dụ.

### 12.3. WarDemoApplication.java

Tạo `src/main/java/dev/course/WarDemoApplication.java`:

```java
package dev.course;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
```

`SpringBootServletInitializer` với `configure` cho external container đường khởi tạo application; `main` phục vụ chạy archive bằng Boot launcher. Đây là mẫu được tài liệu Spring Boot hướng dẫn cho WAR truyền thống.

### 12.4. GreetingController.java

Tạo `src/main/java/dev/course/GreetingController.java`:

```java
package dev.course;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello from WAR";
    }
}
```

### 12.5. GreetingControllerTest.java

Tạo `src/test/java/dev/course/GreetingControllerTest.java`:

```java
package dev.course;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingControllerTest {
    @Test
    void returnsGreeting() {
        assertEquals("Hello from WAR",
                new GreetingController().hello());
    }
}
```

Đây là một unit test của Java method, **chưa phải HTTP integration test**. HTTP sẽ được kiểm tra riêng sau khi chạy WAR.

### 12.6. Build, chạy và gọi HTTP

```bash
mvn clean package
java -jar target/boot-war-demo-1.0.0-SNAPSHOT.war --server.port=18080 --spring.main.banner-mode=off
```

Ứng dụng web vẫn chạy để nhận requests, nên mở một terminal thứ hai.

Bash/zsh:

```bash
curl -fsS http://localhost:18080/hello
```

PowerShell:

```powershell
Invoke-RestMethod -Uri "http://localhost:18080/hello" -Method Get
```

**HTTP response body mong đợi**:

```text
Hello from WAR
```

Đây là **response HTTP**, không phải toàn bộ stdout của Spring Boot server. Sau khi kiểm tra, dừng server bằng Ctrl+C trong terminal đầu.

Xem archive:

```bash
jar tf target/boot-war-demo-1.0.0-SNAPSHOT.war
```

Tìm `WEB-INF/classes/dev/course/WarDemoApplication.class`, `WEB-INF/classes/dev/course/GreetingController.class`, `WEB-INF/lib/`, `WEB-INF/lib-provided/` và `WarLauncher.class`. Đây là các vị trí điển hình của Spring Boot executable WAR.

### 12.7. Deploy lên external servlet container

Muốn deploy WAR lên một servlet container bên ngoài cần:

1. `packaging=war` và WAR Plugin tạo archive phù hợp.
2. Entry point extending `SpringBootServletInitializer` như ví dụ.
3. Embedded servlet container dependency có `scope=provided`, với container runtime đúng version.
4. Servlet container tương thích Jakarta Servlet và Java runtime tương thích.
5. Context path, app configuration, connection settings và permissions đúng.

Với external server, URL có thể có **context path gắn với tên WAR**, không nhất thiết là `http://server/hello`. Cần xem cấu hình máy chủ. Chạy được bằng `java -jar` **không tự chứng minh** có thể deploy lên mọi servlet server.

Đừng triển khai trực tiếp vào production server chỉ để làm bài thực hành. Bài học chỉ yêu cầu chạy local executable WAR và kiểm tra HTTP endpoint.

## 13. Layouts, layers và executable artifacts

Goal `repackage` có tham số `layout`:

| Layout | Hành vi |
| --- | --- |
| `JAR` | Boot executable JAR, BOOT-INF/classes và BOOT-INF/lib |
| `WAR` | Boot executable WAR, WEB-INF/classes, WEB-INF/lib và lib-provided |
| `ZIP` / `DIR` | Layout tương tự JAR sử dụng `PropertiesLauncher` |
| `NONE` | Đóng dependencies/resources nhưng **không thêm bootstrap loader** |

Thông thường để plugin tự chọn layout theo archive type. **`layout=NONE` không phải một executable Boot archive tương tự JAR/WAR**, vì không có loader; muốn chạy cần giải pháp bootstrap/classpath khác.

Spring Boot 3.4 có thể ghi metadata layers vào executable archive, giúp các Docker/OCI images tận dụng cache. Các layer thường gồm:

- `dependencies`: third-party dependencies không phải SNAPSHOT.
- `spring-boot-loader`: loader classes.
- `snapshot-dependencies`: dependencies SNAPSHOT.
- `application`: application classes/resources và module dependencies tương ứng.

Layer metadata như `BOOT-INF/layers.idx` hoặc `WEB-INF/layers.idx` **không thay classpath**, chỉ mô tả cách phân tầng archive.

Cấu hình tùy chọn tắt layer metadata:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <layers>
            <enabled>false</enabled>
        </layers>
    </configuration>
</plugin>
```

Đây là một snippet, không phải POM đầy đủ. Tắt layers không loại runtime dependencies. Cũng không nhầm goal `spring-boot:build-image` (xây OCI image) với goal `spring-boot:repackage` (đóng executable archive).

## 14. Những dependency nào nằm trong executable archive?

Spring Boot Plugin dùng dependency graph và các cấu hình gồm excludes/includes để quyết định libraries cần đóng gói.

- Thư viện runtime như Spring Boot, Spring Context, logging được đưa vào archive theo dependency graph phù hợp.
- Test dependencies như JUnit Jupiter chỉ dùng khi biên dịch/chạy tests, thường **không đưa vào runtime Boot JAR**.
- Với executable WAR, một số `provided` dependencies của servlet container được đóng dưới `WEB-INF/lib-provided` để phục vụ chế độ `java -jar` mà tránh xung đột external container.
- Spring Boot devtools và Docker Compose support có những cấu hình exclude mặc định của plugin.
- Một số libraries có yêu cầu unpack khi chạy; `requiresUnpack` là tính năng nâng cao để xử lý trường hợp cụ thể.

Đoạn minh họa loại một dependency:

```xml
<configuration>
    <excludes>
        <exclude>
            <groupId>org.example</groupId>
            <artifactId>unused-tool</artifactId>
        </exclude>
    </excludes>
</configuration>
```

`org.example:unused-tool` là tọa độ **giả định**, không có trong POM runnable. Không thêm exclude bừa chỉ để giảm JAR size; nếu loại nhầm thư viện app cần khi chạy, có thể gặp `ClassNotFoundException`/`NoClassDefFoundError`.

**Repackage không phải plugin kiểm tra security**. Cần quét dependency vulnerabilities, kiểm tra secrets trong resources và dùng runtime configuration an toàn riêng.

## 15. Các profiles khác nhau: Maven và Spring

Một nhầm lẫn thường gặp là:

```bash
mvn -Pdev clean package
java -jar target/boot-repackage-demo-1.0.0-SNAPSHOT.jar --spring.profiles.active=dev
```

- `-Pdev` ở Maven **kích hoạt một Maven profile** để điều chỉnh mô hình build, plugins hoặc dependencies.
- `--spring.profiles.active=dev` là **application argument lúc chạy Spring Boot**, ảnh hưởng cấu hình ứng dụng.
- JVM system property cho Spring profile đặt **trước** `-jar`:

```bash
java -Dspring.profiles.active=dev -jar target/boot-repackage-demo-1.0.0-SNAPSHOT.jar
```

Đừng cho rằng thay Spring profile sẽ tạo lại executable archive. Profiles của runtime không tự bật goal `repackage`, và Maven profile không mặc định kích hoạt Spring profile.

Với tổ chức muốn chỉ tạo executable cho một số môi trường, có thể bind plugin execution trong Maven profile phát hành và xác nhận phase/profile active, nhưng phải đảm bảo pipeline chạy tới package với cấu hình có hiệu lực.

## 16. Repackage, install và deploy

Sau `mvn package`, output nằm ở `target/`. `mvn install` đưa project artifact và attachments hợp lệ vào local Maven repository; `mvn deploy` xuất bản lên remote repository đã cấu hình và được cho phép.

Không classifier:

```text
target/boot-repackage-demo-1.0.0-SNAPSHOT.jar
  -> executable JAR là primary artifact sau repackage
```

Có classifier exec:

```text
target/boot-repackage-demo-1.0.0-SNAPSHOT.jar
  -> ordinary primary JAR
target/boot-repackage-demo-1.0.0-SNAPSHOT-exec.jar
  -> executable attached JAR (nếu attach=true)
```

Local repository có thể được cấu hình bằng `settings.xml` hoặc `-Dmaven.repo.local`. File `.jar.original` chỉ là backup local, **không phải artifact classifier** để tiêu thụ.

Không chạy `mvn deploy` tới repository tổ chức chỉ để thực hành. Deploy có thể ảnh hưởng downstream consumers và yêu cầu quyền/credentials/policy.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `java -jar` báo không có main manifest | JAR chưa repackage hoặc manifest/main class thiếu | Kiểm tra plugin execution và archive manifest |
| Lỗi không tìm thấy main class | Nhiều candidates hoặc chưa có main method hợp lệ | Đặt `mainClass` trong Boot Plugin |
| Repackage không tìm thấy source JAR/WAR | Goal chạy trước packaging hoặc gọi trực tiếp quá sớm | Chạy package trước, kiểm tra execution plan |
| Repackage chạy hai lần | Starter parent đã có execution và POM thêm một execution mới | Dùng execution kế thừa ID repackage |
| Chỉ import BOM không tạo executable JAR | BOM không cấu hình plugin | Thêm Boot Maven Plugin với execution phù hợp |
| `java -cp executable.jar YourApp` không tìm class | Classes ở BOOT-INF/classes | Chạy bằng `java -jar` hoặc dùng ordinary JAR/classpath |
| Consumer không compile với Boot JAR dependency | Primary artifact là executable JAR | Dùng module library hoặc classifier exec |
| Build có JAR nhưng không chứa BOOT-INF | Plugin không được kích hoạt, skip hoặc đang xem ordinary JAR | Xem manifest, plugin log và effective POM |
| JAR thiếu runtime class | Dependency bị exclude hoặc scope không phù hợp | Kiểm tra dependency tree và repackage config |
| Spring Boot web server không start | Port conflict, cấu hình sai hoặc dependency thiếu | Kiểm tra port, logs và starter-web |
| WAR standalone chạy được nhưng external server lỗi | Servlet container thiếu tương thích, initializer thiếu hoặc Tomcat scope sai | Kiểm tra Jakarta Servlet, initializer và provided |
| `.jar.original` không được publish | Đó là tệp backup local | Muốn ordinary JAR như primary, dùng classifier exec |
| `layout=NONE` không chạy qua java -jar | Không có bootstrap loader | Dùng layout JAR/WAR hoặc launcher khác |
| WAR không có WEB-INF/lib-provided | Không có provided dependencies hoặc sai packaging/config | Xem POM và jar tf |
| App CLI vừa in một dòng rồi tắt | Project non-web gọi close context | Hành vi đúng của demo |
| `spring-boot:run` chạy được nhưng JAR không chạy | Runtime classpath khác archive, thiếu repackage hoặc excluded lib | Kiểm tra artifact thật |
| CI build khác local | Java/Boot/plugin version, Maven profiles hoặc repositories khác | So sánh mvn -version, effective POM, dependency tree |
| JAR nặng hơn mong đợi | Chứa nested runtime dependencies | Kiểm tra graph và dependencies thay vì xóa JAR tùy tiện |

Một build `BUILD SUCCESS` chỉ chứng minh các goals được Maven thực thi đã thành công. Muốn xác nhận artifact thực sự chạy được, **chạy đúng JAR/WAR và kiểm tra output**.

## 18. Debug bằng Maven và JDK

Những lệnh hữu ích:

```bash
mvn -version
mvn help:effective-pom
mvn help:active-profiles
mvn dependency:tree
mvn clean package
jar tf target/boot-repackage-demo-1.0.0-SNAPSHOT.jar
```

Để tra tham số goal:

```bash
mvn help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail
```

Trong effective POM, tìm plugin ở build/plugins, version, execution ID `repackage` và các thuộc tính `classifier`, `attach`, `layout`. Trong build log tìm dấu hiệu Maven JAR/WAR Plugin **tạo archive trước** Spring Boot Plugin.

Nếu cần log chi tiết:

```bash
mvn -X clean package
```

Log debug có thể chứa paths, repository URLs, tham số môi trường hoặc thông tin nội bộ; không chia sẻ công khai nguyên log khi chưa kiểm tra.

### 18.1. Kiểm chứng một executable JAR cần gì?

1. File JAR tồn tại ở target.
2. Archive có `BOOT-INF/classes` và `BOOT-INF/lib`.
3. Manifest có `Main-Class` là loader và `Start-Class` là application main.
4. `java -jar ...` chạy được với JVM phù hợp.
5. Startup output/behavior đúng (CLI demo in một dòng; WAR demo trả HTTP body).
6. Những tests cần thiết đã chạy; không skip ngầm.
7. Nếu publish classifier `exec`, đúng artifact classifier được install/deploy.

## 19. CI, bảo mật và tính tái lập

Ví dụ một job CI:

```bash
mvn -B -ntp clean verify
```

Vì `verify` nằm sau `package`, Boot Plugin repackage (nếu bound) đã chạy. Tuy nhiên một CI cần artifact chạy được nên thêm bước smoke test đối với executable JAR/WAR, đặc biệt khi thay dependencies, profiles hoặc Spring Boot version.

Checklist:

- Ghim Spring Boot và JDK versions, quản lý plugin versions nhất quán.
- Không cho test bị skip trong job kiểm tra chính.
- Xác nhận goal repackage chỉ chạy đúng một lần ở phase dự kiến.
- Đảm bảo archive input được tạo trước Boot Plugin.
- Giữ classifier/attachment đúng với mục đích: app chạy độc lập hay module library.
- Kiểm tra nested libraries, manifest, Start-Class và output.
- Với WAR, kiểm thử ở embedded mode hoặc trên external container tương thích như kế hoạch triển khai.
- Không đóng secrets, access tokens hoặc cấu hình nhạy cảm vào JAR/WAR resources.
- Review dependency vulnerabilities và nâng phiên bản theo chính sách.
- Khi cần reproducible builds, kiểm soát timestamp, contents, plugin versions, generated resources và môi trường.

Boot Plugin có `outputTimestamp` và cấu hình layer metadata, nhưng một giá trị timestamp **không tự bảo đảm** byte-for-byte reproducibility nếu đầu vào khác nhau.

## 20. Bài tập tự kiểm tra

1. Giải thích sự khác nhau giữa Maven JAR Plugin và goal `spring-boot:repackage`.
2. Vì sao repackage cần ordinary JAR/WAR có trước? Lệnh `mvn spring-boot:repackage` có tự chạy package không?
3. Dùng POM Java 17 của mục 7, chạy `mvn clean package`; xác minh 3 JUnit tests pass và executable JAR tồn tại.
4. Dùng `jar tf` chỉ ra `BOOT-INF/classes/dev/course/BootRepackageApplication.class` và nested libraries trong `BOOT-INF/lib`.
5. Chạy `java -jar ... --spring.main.banner-mode=off --logging.level.root=OFF`. Vì sao không cần thêm `-cp`?
6. Chạy `InspectBootJar.java`, giải thích vì sao `Main-Class=JarLauncher` và `Start-Class=BootRepackageApplication`.
7. Gỡ Boot Plugin khỏi `build/plugins` trong nhánh thử nghiệm, build lại và quan sát archive có gì khác.
8. Khi không dùng starter parent mà chỉ import BOM, cần khai báo phần nào để repackage chạy tự động?
9. Thêm `<classifier>exec</classifier>` rồi build lại. Hai JAR có vai trò gì khác nhau?
10. Nếu đặt `attach=false` khi có classifier exec, quá trình install/deploy có tự đưa executable attachment đi không?
11. Vì sao executable Boot JAR không dùng như ordinary dependency library? Khi nào nên tách module?
12. So sánh `spring-boot:run` với `java -jar`. Hai lệnh có kiểm tra cùng archive không?
13. Tạo project WAR của mục 12, chạy web server bằng `java -jar ...war`, gọi `/hello` và ghi HTTP response.
14. Vì sao `spring-boot-starter-tomcat` cần scope provided khi deploy WAR vào external Tomcat?
15. So sánh `BOOT-INF/lib` và `WEB-INF/lib-provided`.
16. Spring Boot 3 WAR có deploy lên servlet container chỉ có `javax.servlet` được không? Vì sao?
17. Nếu thay `layout=NONE`, kỳ vọng `java -jar` có còn như JAR layout không?
18. `mvn -Pdev` và `--spring.profiles.active=dev` tác động lên hai tầng nào?
19. Khi phát hành cả ordinary và executable artifact, nên xác minh những tọa độ/classifiers nào?
20. Nếu một JAR khởi động tốt local nhưng CI fail, bạn sẽ kiểm tra JDK, profile, artifact, dependencies và log theo thứ tự nào?

## 21. Tóm tắt

**Spring Boot Maven Plugin** tạo executable archives cho ứng dụng Spring Boot. Goal **`repackage`** nhận JAR/WAR đã được Maven đóng gói, thêm nested runtime dependencies, Spring Boot loader và manifest, để chạy bằng **`java -jar`**.

Ba điểm cần ghi nhớ:

- **Cơ chế:** Maven JAR/WAR Plugin tạo archive trước; Spring Boot Maven Plugin repackage sau. Repackage không thay compiler hoặc test runner.
- **Cấu hình:** Starter parent đã chuẩn bị execution `repackage`; chỉ import BOM thì chưa có execution. Dùng `classifier=exec` khi muốn giữ ordinary JAR làm primary và thêm executable JAR.
- **JAR và WAR:** executable JAR dùng `BOOT-INF/classes`, `BOOT-INF/lib`, `JarLauncher`; executable WAR dùng `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided`, `WarLauncher`. External WAR deployment cần initializer và compatible servlet container.

Trong project Java 17, ba tests xác nhận service, executable JAR in **`APP_READY: Xin chào, Lan!`**. Dự án WAR riêng chạy HTTP endpoint `/hello` trả **`Hello from WAR`**. Hãy kiểm chứng kết quả bằng archive thực tế, manifest, lệnh khởi chạy và output thay vì chỉ nhìn `BUILD SUCCESS`.

## 22. Tài liệu chính thức

- [Spring Boot 3.4 — Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.4/maven-plugin/packaging.html)
- [Spring Boot 3.4 — Maven Plugin: Using the Plugin](https://docs.spring.io/spring-boot/3.4/maven-plugin/using.html)
- [Spring Boot 3.4 — Maven Plugin: Goals](https://docs.spring.io/spring-boot/3.4/maven-plugin/goals.html)
- [Spring Boot 3.4 — Traditional Deployment](https://docs.spring.io/spring-boot/3.4/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.4 — Executable Jar Specification](https://docs.spring.io/spring-boot/3.4/specification/executable-jar/index.html)
- [Spring Boot — Use a Spring Boot Application as a Dependency](https://docs.spring.io/spring-boot/how-to/build.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
