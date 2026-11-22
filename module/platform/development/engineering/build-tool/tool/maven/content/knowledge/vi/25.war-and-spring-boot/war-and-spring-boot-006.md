# Spring Boot parent so với nhập BOM quản lý phụ thuộc trong Maven

Với Maven, dự án Spring Boot có thể nhận tập phiên bản dependency đã được Spring Boot kiểm thử bằng hai cách: (1) **kế thừa `spring-boot-starter-parent`**; hoặc (2) **import `spring-boot-dependencies` BOM** vào `dependencyManagement`. Cả hai thường giúp khai báo `spring-boot-starter`, `spring-boot-starter-test` và nhiều thư viện khác mà không ghi từng `<version>`, nếu cùng dùng một Spring Boot release.

**Nhưng parent và BOM import KHÔNG tương đương.** Spring Boot Starter Parent là một POM được Maven kế thừa, cung cấp cả quản lý dependency, phiên bản và cấu hình plugin, compiler defaults, resource filtering và execution `spring-boot:repackage`. BOM import chỉ nhập **dependencyManagement entries**; nó **không nhập pluginManagement, build/plugins, executions hoặc properties của BOM như một parent**. Vì vậy một ứng dụng BOM-only có thể compile nhưng chỉ tạo plain JAR, không chạy được bằng `java -jar`, nếu chưa cấu hình Spring Boot Maven Plugin.

Bài học giải thích hai mô hình, khi nào chọn, cách dùng corporate parent, ghi đè phiên bản dependency, cấu hình compiler/plugin, tạo executable JAR và WAR, rồi thực hành **hai ứng dụng Java 17 có chung source code**. Ví dụ dùng Spring Boot **3.5.7** (release có thật phát hành 23/10/2025), Maven 3.9.x, Java 17+. Phiên bản này được cố định để bài thực hành có thể tái lập, **không khẳng định là phiên bản mới nhất**.

## 1. Phân biệt các thành phần trong một POM Spring Boot

| Thành phần | Ý nghĩa | Điều KHÔNG tự làm |
| --- | --- | --- |
| `<parent>` | Chọn POM cha để kế thừa Maven model | Không thể có hai parent trực tiếp |
| `spring-boot-starter-parent` | Parent cung cấp Boot dependency management + build defaults | Không tự thêm mọi Spring starter vào ứng dụng |
| `spring-boot-dependencies` | BOM quản lý versions của Boot và thư viện liên quan | Không tự cấu hình Maven plugins khi import |
| `<dependencyManagement>` | Khai version/scope/exclusion mặc định cho dependency tương ứng | Không tự tải dependency chưa được khai |
| `<dependencies>` | Khai những dependency dự án thực sự dùng | Không điều khiển repackage JAR |
| `<pluginManagement>` | Quản lý plugin versions/config/executions khi plugin được dùng | Không tự gọi mọi plugin goal |
| `<build><plugins>` | Khai plugins được sử dụng và execution bindings | Không tự thêm Spring BOM |
| `spring-boot-maven-plugin` | Các goals như `run`, `repackage`, `build-image` | Không tự chạy repackage chỉ nhờ import BOM |
| `spring-boot-starter` | Starter dependency cung cấp runtime Boot cơ bản | Không phải parent hoặc BOM |
| `maven-compiler-plugin` | Biên dịch với Java target/release cụ thể | Không được BOM import tự chọn version/config |

**Công thức cần nhớ:** *parent = inheritance của Maven project model; import BOM = chỉ import các mục quản lý dependency*. Đây là quy tắc Maven cơ bản, không phải hạn chế riêng của Spring Boot.

### 1.1. Vì sao có cả starter-parent và dependencies BOM?

`spring-boot-starter-parent` là một parent POM tiện lợi, bản thân nó kế thừa từ `spring-boot-dependencies`. Spring Boot dependency BOM chứa curated versions của Spring Framework và nhiều third-party libraries. Dùng parent là nhận dependency management **cùng** những opinionated build defaults do Spring Boot cung cấp. Dùng BOM import là nhận phần quản lý phiên bản dependency **mà không áp chính sách build của Starter Parent**.

Sơ đồ:

```text
A. DÙNG STARTER PARENT

your-app (pom.xml)
  └── parent: spring-boot-starter-parent:3.5.7
         ├── parent: spring-boot-dependencies:3.5.7
         ├── dependencyManagement
         ├── compiler, resource filtering, encoding defaults
         ├── pluginManagement và execution repackage
         └── những build conventions khác

B. IMPORT BOM

your-app (pom.xml)
  ├── parent: corporate-parent (tùy chọn)
  ├── dependencyManagement
  │      └── import spring-boot-dependencies:3.5.7
  └── build/plugins do app hoặc corporate parent tự quản
         ├── compiler, Surefire, Resources, JAR/WAR plugins
         └── spring-boot-maven-plugin:repackage nếu cần
```

Trong sơ đồ B, corporate parent không bắt buộc. Nếu không có parent được khai, project vẫn kế thừa Maven Super POM; BOM import chỉ sửa dependency management.

## 2. Kế thừa Spring Boot Starter Parent

Để dùng Starter Parent, POM đặt:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
</parent>
```

`<relativePath/>` trống tránh việc Maven tự thử lấy `../pom.xml` như parent local khi đó không phải Spring Boot Starter Parent. Maven resolve parent qua configured repositories nếu không được cung cấp local source tương ứng.

Theo hướng dẫn Maven Plugin Spring Boot 3.5, Starter Parent cung cấp:

- Java 17 làm mức compiler mặc định trong dòng Boot 3.5; có property `java.version` để điều chỉnh.
- UTF-8 source encoding.
- Compiler `-parameters` để ghi tên tham số phục vụ reflection/binding.
- Version management của thư viện qua parent chain chứa `spring-boot-dependencies`.
- Execution `spring-boot:repackage` có ID `repackage` được cấu hình sẵn.
- Resource filtering thích hợp cho `application.properties` và `application.yml`, dùng Maven delimiter `@...@` để không làm vỡ Spring placeholders.
- Những plugin defaults/profile hữu ích khác, tùy release.

**Lưu ý:** “preconfigured repackage execution” không có nghĩa chỉ cần có parent và không cần khai Spring Boot Maven Plugin. Với project đơn giản, thường khai **`spring-boot-maven-plugin` dưới `build/plugins`**, không phải tự khai thêm execution vì parent đã quản lý nó.

### 2.1. Khai dependency không cần version

```xml
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
```

Cả hai là dependencies có managed versions. Nhưng **parent không tự kéo những starter chưa được khai**: nếu cần Spring Web, Data JPA hay Security, project vẫn phải thêm starter tương ứng trong `<dependencies>`. Ngược lại, một thư viện ngoài danh sách BOM có thể vẫn cần version riêng.

## 3. Import Spring Boot BOM thay vì kế thừa Parent

Cú pháp chuẩn Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.7</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây không phải là POM độc lập; nó được đặt bên trong `<project>`. `type=pom` chỉ loại artifact POM; `scope=import` khi đặt trong `dependencyManagement` yêu cầu Maven nhập các mục quản lý dependency của BOM.

Khi project vẫn khai `spring-boot-starter`/`spring-boot-starter-test` ở `<dependencies>`, các versions có thể được resolve từ imported BOM. **Không cần tự ghi version cho các starters đã được quản lý**, nhưng cũng không có lý do để khai BOM như một compile/runtime dependency.

### 3.1. Những gì không được import

Import BOM **không** mang theo:

- `<build>`, `<plugins>` và `<pluginManagement>` của BOM.
- Execution `spring-boot:repackage` của Starter Parent.
- Compiler Plugin version/`release`/`parameters` theo Starter Parent.
- Các quy tắc Maven resource filtering của Starter Parent.
- Properties từ BOM theo cơ chế kế thừa để ghi đè từ POM con.
- Các Maven profiles/build policies của Spring Boot parent.

Vì vậy nếu doanh nghiệp có corporate parent quy định Compiler, Surefire, Checkstyle, JaCoCo, Enforcer... và chỉ muốn dùng Boot library versions, BOM import là giải pháp hợp lý. Corporate parent vẫn quyết định các build plugins và phiên bản của chúng.

### 3.2. Plugin vẫn phải có version và execution thích hợp

Trong một project chỉ import BOM, cấu hình bên dưới **chưa đủ để đảm bảo repackage**:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.7</version>
</plugin>
```

Nó chỉ khai plugin. Nếu không có execution/lifecycle binding khác, Maven package có thể vẫn tạo JAR thuần. Muốn executable Boot JAR, thêm:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.7</version>
    <executions>
        <execution>
            <id>repackage</id>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Goal `repackage` có default phase `package` trong metadata plugin, nên execution không bắt buộc ghi `<phase>package</phase>` trong ví dụ này. Maven JAR Plugin tạo archive gốc; Spring Boot plugin **repackage** thành executable archive. Cấu hình này được dùng trong POM BOM-only hoàn chỉnh ở phần thực hành.

## 4. Bảng so sánh đầy đủ

| Tiêu chí | Kế thừa `spring-boot-starter-parent` | Import `spring-boot-dependencies` BOM |
| --- | --- | --- |
| Khai báo | `<parent>` | `<dependencyManagement>` + `type=pom` + `scope=import` |
| Managed dependency versions | Có | Có |
| Tự thêm dependencies vào classpath | Không | Không |
| Mang theo build configuration | Có, theo inheritance | Không |
| Quản lý compiler Java defaults | Có theo parent | Chỉ khi app/corporate parent khai |
| Resource filtering conventions | Có theo parent | Không được import |
| Maven plugin version management | Có trong parent chain | Không được import |
| Boot Plugin `repackage` execution | Có sẵn trong parent; sử dụng khi plugin được khai | Tự khai hoặc nhờ parent khác |
| Plugin declarations trong app | Vẫn cần khi sử dụng plugin ngoài lifecycle/default | Vẫn cần |
| Có thể dùng corporate parent trực tiếp | Không đồng thời có hai parent | Có |
| Override managed version qua Boot property | Có thể qua inherited property `slf4j.version` | Không hoạt động tương đương; dùng dependencyManagement |
| Dễ bắt đầu dự án Boot mới | Rất thuận tiện | Nhiều build config hơn |
| Khả năng kiểm soát Maven policy độc lập | Theo parent/overrides | Cao, corporate parent tự quản |
| Tạo executable JAR | Có khi Boot plugin hoạt động | Có nếu cấu hình Boot plugin/repackage |
| Nên dùng cho library JAR | Có thể, nhưng repackage không cần nếu library | Dùng BOM quản lý libraries mà không bắt repackage rất thuận tiện |

Không có cách nào là “sai” tuyệt đối. Parent phù hợp khi bạn chấp nhận Boot defaults; BOM phù hợp khi cần giữ parent tổ chức và tự quản lý build.

## 5. Thực hành: hai Maven projects Java 17 có cùng chức năng

Bài tập gồm hai project:

- `boot-parent-demo` dùng Starter Parent.
- `boot-bom-demo` dùng BOM import và **không** kế thừa Starter Parent.

Cả hai có **cùng ba file source/resource/test** và cùng Java behavior. Ta dùng `SpringApplication` ở chế độ không mở web server, rồi in dòng `boot-mode=READY` từ `ApplicationRunner`. Sau build, kiểm tra JAR được Boot repackage và chạy bằng `java -jar`.

Môi trường: JDK 17+, Maven 3.9.x và repository cho phép tải Spring Boot 3.5.7 và Maven plugins. Khi khởi chạy JAR thành phẩm, không cần IDE hay Maven.

Cấu trúc:

```text
boot-parent-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/boot/DemoApplication.java
    │   └── resources/application.properties
    └── test/java/vn/example/boot/DemoApplicationTest.java

boot-bom-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/boot/DemoApplication.java
    │   └── resources/application.properties
    └── test/java/vn/example/boot/DemoApplicationTest.java
```

### 5.1. POM hoàn chỉnh của boot-parent-demo

File `boot-parent-demo/pom.xml`:

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
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>boot-parent-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
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

Đây là POM đầy đủ. Phiên bản `spring-boot-maven-plugin` và execution `repackage` đến từ plugin management của parent. Không cần lặp lại phần `<executions>` chỉ để gọi `repackage` mặc định.

### 5.2. POM hoàn chỉnh của boot-bom-demo

File `boot-bom-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>boot-bom-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <spring-boot.version>3.5.7</spring-boot.version>
        <java.version>17</java.version>
        <maven.compiler.release>${java.version}</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
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
</project>
```

Điểm cần đọc kỹ:

1. `<spring-boot.version>3.5.7</...` là property do **project** định nghĩa, được dùng cho chính BOM import và Spring Boot Maven Plugin, nên giúp chúng cùng version.
2. `<java.version>17</...` **không tự có hiệu lực compiler chỉ vì import BOM**. Ở đây project chủ động khai `maven.compiler.release=${java.version}`, và Compiler Plugin dùng `<release>${maven.compiler.release}</release>`.
3. `<parameters>true</parameters>` tái tạo compiler parameter metadata, hữu ích cho Spring binding.
4. Surefire/Resources/JAR/Clean Plugin versions được **pin rõ** vì BOM import không nhập pluginManagement.
5. Spring Boot Maven Plugin **có version và execution riêng**, giúp `mvn package` thực sự repackage JAR.
6. `spring-boot-starter`/`spring-boot-starter-test` vẫn không có version vì BOM quản lý chúng.
7. Không bật resource filtering trong POM ví dụ vì `application.properties` không cần Maven placeholder; cách này giữ hai bản có cùng runtime behavior.

Trong dự án có corporate parent, nhiều version/plugin configurations ở mục này có thể được quản lý tập trung trong parent nội bộ; không cần copy mọi dòng vào từng module.

### 5.3. Java source đầy đủ dùng cho cả hai

File `src/main/java/vn/example/boot/DemoApplication.java`:

```java
package vn.example.boot;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(DemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.run(args);
    }

    public static String status() {
        return "boot-mode=READY";
    }

    @Bean
    ApplicationRunner startupStatus() {
        return args -> System.out.println(status());
    }
}
```

Đây là Spring Boot app thực sự khởi động ApplicationContext, không chạy servlet/web server vì chọn `WebApplicationType.NONE`. `ApplicationRunner` in một dòng có giá trị xác định sau context startup. Nó sẽ được Spring Boot Maven Plugin nhận diện để tạo executable JAR có Boot loader khi `repackage` chạy.

### 5.4. Resources và JUnit test

File `src/main/resources/application.properties`:

```properties
spring.main.banner-mode=off
logging.level.root=OFF
```

File này không dùng Maven placeholders nên không cần filtering. `SpringApplication` trong Java cũng tắt banner; cấu hình logging ở đây giảm output startup không liên quan. Trong môi trường khác, vẫn có thể có warnings trên stderr; **đừng hiểu dòng application output là toàn bộ log JVM**.

File `src/test/java/vn/example/boot/DemoApplicationTest.java`:

```java
package vn.example.boot;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DemoApplicationTest {
    @Test
    void expectedStatus() {
        assertEquals("boot-mode=READY", DemoApplication.status());
    }
}
```

Đây là **unit test thuần** của method `status()`; nó **không chạy Spring context trong JUnit**. Mục tiêu test là xác minh code và JUnit provider/Surefire; kiểm chứng Spring context và Boot executable JAR nằm ở lệnh `java -jar`. Với một ứng dụng thật, bổ sung `@SpringBootTest` hoặc integration tests khi cần đánh giá auto-configuration/bean wiring.

### 5.5. Lệnh Maven và Java

Mở terminal trong `boot-parent-demo`:

```bash
java -version
mvn --version
mvn -B clean verify
java -jar target/boot-parent-demo-1.0.0.jar
```

Sau đó đổi sang `boot-bom-demo` và chạy:

```bash
java -version
mvn --version
mvn -B clean verify
java -jar target/boot-bom-demo-1.0.0.jar
```

**Ứng dụng ở cả hai project in ra dòng stdout sau** nếu build và startup thành công:

```text
boot-mode=READY
```

Đây là **dòng do `ApplicationRunner` in**; log Maven/Java có thể chứa thêm nội dung tùy môi trường. `mvn clean verify` chạy compilation, unit test và phase package, trong đó Boot repackage execution tạo executable archive. Khi Java 17+ chạy JAR, Boot loader khởi động ApplicationContext rồi thực thi runner.

Các file output quan trọng:

```text
boot-parent-demo/target/boot-parent-demo-1.0.0.jar
boot-bom-demo/target/boot-bom-demo-1.0.0.jar
```

Đây là các đường dẫn tương đối **trên filesystem theo từng project**, không phải hai JAR trong cùng thư mục. Plugin có thể giữ JAR gốc trước repackage dưới đuôi `.jar.original`; không dùng file `.original` để kiểm tra executable Boot app.

## 6. Kiểm chứng JAR được repackage đúng

Một ứng dụng Spring Boot executable JAR của dòng 3.5 thường có bố cục:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/vn/example/boot/DemoApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/...
org/springframework/boot/loader/...
```

Trên mỗi project sau `package`:

```bash
jar tf target/boot-parent-demo-1.0.0.jar
```

Hoặc:

```bash
jar tf target/boot-bom-demo-1.0.0.jar
```

Đây là **các entry cần tìm trong danh sách**, không phải toàn bộ stdout. File JAR có thể còn metadata Maven, index layers và nhiều dependencies khác.

### 6.1. Main-Class và Start-Class của Spring Boot

Manifest executable JAR thông thường do Spring Boot 3.5 tạo có entry tương tự:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: vn.example.boot.DemoApplication
```

- `Main-Class` thường là **Boot loader**; không phải trực tiếp app class.
- `Start-Class` chỉ application entry point.
- `BOOT-INF/lib` chứa nested runtime JARs mà Boot loader biết cách nạp.
- `BOOT-INF/classes` chứa application classes và resources.

Nếu chỉnh `Main-Class` trong Maven JAR Plugin thành `vn.example.boot.DemoApplication` rồi vẫn dùng nested JAR layout, có thể phá cơ chế loader. Hãy để **Spring Boot Maven Plugin** quản lý manifest cho archive đã repackage.

### 6.2. Trường hợp BOM-only bị thiếu repackage

Nếu chỉ có BOM import, phần `dependencies` và `<plugin>spring-boot-maven-plugin</plugin>` mà **không có execution**, `mvn package` có thể tạo plain JAR, chẳng hạn file chỉ chứa:

```text
vn/example/boot/DemoApplication.class
application.properties
META-INF/MANIFEST.MF
```

JAR thường chưa chắc tự chạy bằng `java -jar`: có thể thiếu `Main-Class` và runtime dependencies không được nhúng vào cùng bố cục. Nếu bị lỗi `no main manifest attribute` hoặc thiếu Boot loader, kiểm tra `repackage` execution và Maven build log trước khi thay thư viện trong BOM.

### 6.3. Đừng gọi repackage hai lần vô ý

Với Starter Parent, execution ID `repackage` đã được quản lý. Nếu bạn tự thêm execution khác ID vào chính plugin, có thể khiến goal chạy hai lần trong cùng phase. Muốn chỉnh cấu hình execution sẵn có (ví dụ thêm classifier), dùng **đúng `<id>repackage</id>`** để merge theo Maven execution ID, không tạo một execution mới không chủ ý.

Khi đã khai execution trong POM, lệnh `mvn clean verify` thường đủ. Lệnh `mvn package spring-boot:repackage` có thể gọi goal trực tiếp **thêm lần nữa** trên một build đã bind nó; tránh nếu không có mục đích rõ.


## 7. Khác biệt khi ghi đè versions: inherited properties và BOM import

Một trong những điểm khó nhất là tên property `slf4j.version` hoặc `jackson.version` xuất hiện trong Spring Boot dependency management nhưng **có thể override theo hai cách khác nhau**.

### 7.1. Khi kế thừa Starter Parent

Project con có thể override property do parent dùng để định nghĩa managed version. Ví dụ **minh họa cách viết**, không phải khuyến nghị thay thư viện:

```xml
<properties>
    <java.version>17</java.version>
    <slf4j.version>2.0.17</slf4j.version>
</properties>
```

Khi property đó thực sự được Boot parent dùng để quản lý library, giá trị child có thể tham gia vào effective dependencyManagement. Kiểm tra phiên bản thực tế bằng `mvn dependency:tree`, vì parent/child/profiles có thể có overrides khác.

**Cảnh báo compatibility:** Spring Boot quản lý tập versions được kiểm thử. Nâng/hạ riêng các core libraries (Spring Framework, SLF4J, Jackson, Tomcat...) có thể gây binary incompatibility, auto-configuration failure hoặc security regressions. Cần lý do, test, changelog và policy rõ.

### 7.2. Khi import BOM không dùng Starter Parent

Nếu POM chỉ import `spring-boot-dependencies`, khai:

```xml
<properties>
    <slf4j.version>2.0.17</slf4j.version>
</properties>
```

**không override managed entries bằng cơ chế inherited property như phương án parent**. Spring Boot Maven docs nói rõ hạn chế này. BOM import chỉ nhập dependency management entries đã được xây trong ngữ cảnh BOM.

Muốn override một dependency, có thể khai **direct entry ở `dependencyManagement` trước BOM import**:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.7</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đoạn này **minh họa precedence**, không phải phần bắt buộc của hai POM runnable. Nó chỉ override `org.slf4j:slf4j-api`, không tự điều chỉnh toàn bộ những artifacts liên quan đến cùng framework. Nếu cần thay một release train, có thể import BOM quản lý nhóm đó trước Spring Boot BOM theo hướng dẫn của Boot.

### 7.3. Thứ tự BOM imports có ý nghĩa

Khi hai imported BOMs quản lý cùng dependency, Maven có quy tắc precedence; trong trường hợp các entries imported bị trùng mà không có khai báo trực tiếp ưu tiên hơn, BOM xuất hiện trước thường có quyền ưu tiên. Các direct managed dependencies trong project cùng parent management và explicit dependency versions có thể tác động thêm.

Để hạn chế bất ngờ:

1. Chỉ import những BOM cần thiết.
2. Khai rõ các direct managed overrides có chủ đích.
3. Kiểm tra version bằng `dependency:tree` và `effective-pom`.
4. Giữ thống nhất Spring Boot BOM và Boot Maven Plugin major/minor/patch theo release đã kiểm chứng.
5. Không dựa vào một property chưa được định nghĩa trong POM đang import BOM.

**Phân biệt:** `spring-boot.version` trong BOM-only POM ở mục 5 là project property tự tạo để điều khiển **BOM coordinate version** và **plugin version**; nó hoàn toàn hợp lệ. Điều không tương đương là dùng property con để override **bên trong những entries đã được import từ BOM**.

## 8. Khi công ty có corporate parent

Maven mỗi project chỉ có **một parent trực tiếp**. Vì vậy đoạn sau là cấu trúc **cố tình sai**:

```xml
<!-- Không được có hai phần tử parent trực tiếp trong cùng project -->
<parent>...corporate-parent...</parent>
<parent>...spring-boot-starter-parent...</parent>
```

Hai chiến lược hợp lệ:

### 8.1. Corporate parent kế thừa Spring Boot parent

```text
app
 └─ corporate-parent:2.1.0
      └─ spring-boot-starter-parent:3.5.7
           └─ spring-boot-dependencies:3.5.7
```

Corporate parent có thể thêm pluginManagement/Enforcer/JaCoCo/supply-chain policy trên Boot defaults, và các ứng dụng kế thừa corporate parent. Phù hợp khi hầu hết modules của tổ chức đều là Boot apps và tổ chức chấp nhận Boot parent làm nền.

### 8.2. Corporate parent độc lập, ứng dụng import Boot BOM

```text
app
 ├─ corporate-parent:2.1.0 (compiler, tests, code quality)
 ├─ dependencyManagement/import: spring-boot-dependencies:3.5.7
 ├─ dependencies: spring-boot-starter, spring-boot-starter-test
 └─ spring-boot-maven-plugin:repackage (nếu là executable app)
```

Tổ chức giữ một parent dùng chung cho Java library, Spring Boot services và modules khác; Boot chỉ quản lý dependency versions. Chi phí là phải thống nhất plugin versions/bindings từ corporate parent hoặc từng app.

**Corporate coordinates trong hai sơ đồ là ví dụ khái niệm**, không phải artifacts công khai để resolve. Hai POM runnable ở mục 5 không đòi corporate parent, nên có thể chạy trực tiếp.

### 8.3. Parent khác aggregator

Một POM có `<modules>` chỉ đóng vai trò aggregator cho reactor; module không tự thừa kế nó nếu không có `<parent>`. Khi nhiều service trong một repository dùng Boot BOM khác nhau, phải xem **effective POM của từng module**, không chỉ POM aggregator.

## 9. Resource filtering: Spring placeholders và Maven placeholders

Parent có những conventions Maven Resources Plugin đặc biệt để tránh xung đột giữa placeholders của Spring và Maven.

Ví dụ application properties:

```properties
service.name=@project.name@
spring.datasource.url=${DB_URL:jdbc:h2:mem:demo}
```

Trong một project có Maven filtering đúng cấu hình:

- `@project.name@` là placeholder để Maven có thể thay bằng tên project khi **filtering được bật và delimiter `@...@` được hỗ trợ**.
- `${DB_URL:jdbc:h2:mem:demo}` là placeholder của **Spring Environment**, được Spring xử lý tại runtime, không phải Maven build bắt buộc phải thay nó.
- Nếu BOM-only project cấu hình Resources Plugin filtering với delimiters mặc định `${...}` mà không cân nhắc, có nguy cơ làm thay đổi giá trị dành cho Spring.

**Không nên bật `<filtering>true</filtering>` cho mọi binary resources** như ảnh, ZIP, font; text filtering có thể làm hỏng bytes. Đội có thể tách filtered resources và unfiltered resources.

Trong ví dụ runnable, `application.properties` chỉ có `spring.main.banner-mode` và `logging.level.root` không có placeholders; vì thế hai cách parent/BOM khác về defaults nhưng vẫn cho cùng behavior.

### 9.1. Java release và parameters

Spring Boot 3.5 yêu cầu Java 17 trở lên. Parent đặt compiler defaults; BOM-only POM nên khai rõ:

```xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>${java.version}</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

và Compiler Plugin:

```xml
<configuration>
    <release>${maven.compiler.release}</release>
    <parameters>true</parameters>
</configuration>
```

`--release 17` hướng compiler dùng Java API và class-file compatible với Java 17 khi JDK hỗ trợ. `-parameters` lưu parameter names để nhiều framework features/binding theo tên hoạt động. Nó **không tự cài JDK 17**; Maven vẫn phải chạy trên JDK thích hợp.

## 10. WAR và Spring Boot: BOM không quyết định loại artifact

Bài thuộc nhóm WAR và Spring Boot, vì vậy cần biết parent/BOM **không tự quyết định** ứng dụng đóng gói dưới dạng JAR hay WAR. Chính `<packaging>`, plugins và source code/runtime contract quyết định.

Với hai demo, `<packaging>jar</packaging>` và Boot repackage tạo executable JAR có `BOOT-INF/classes`, `BOOT-INF/lib`.

Với servlet application muốn deploy thành WAR, thường phải:

- Chọn `<packaging>war</packaging>` và quản lý Maven WAR Plugin.
- Bổ sung dependencies của Web/Servlet stack phù hợp phiên bản Spring Boot.
- Khi deploy lên **external servlet container**, ứng dụng thường mở rộng `SpringBootServletInitializer` và đặt scope của embedded servlet container dependency theo cách Boot khuyến nghị.
- Nếu cần **executable WAR**, chạy Boot Maven Plugin `repackage` với archive WAR và kiểm tra loader/layout.
- Kiểm tra các thư mục `WEB-INF/classes`, `WEB-INF/lib` và khi phù hợp `WEB-INF/lib-provided`.

**Không được chỉ đổi `jar` thành `war` trong POM của console demo rồi tuyên bố nó là web app deploy được**. Cần controller, servlet configuration và kiểm thử servlet container thật. Đây là kiến thức packaging riêng, không thuộc năng lực của BOM import.

Spring Boot Maven Plugin thực hiện `repackage` cả executable JAR và WAR khi được cấu hình đúng. Parent cho execution defaults; BOM-only vẫn cần bind execution.

## 11. Migrate từ Starter Parent sang BOM-only

Một quy trình chuyển đổi tránh lỗi “dependency đủ nhưng JAR sai”:

1. **Chụp baseline** bằng `mvn --version`, `help:effective-pom`, `dependency:tree`, test reports và manifest/JAR layout.
2. Thay `spring-boot-starter-parent` bằng corporate parent mong muốn (nếu có), hoặc bỏ parent tường minh.
3. Import `spring-boot-dependencies` cùng Spring Boot release trong `dependencyManagement`.
4. Giữ các starter dependencies như trước, không tự thêm version cho artifacts do Boot quản lý.
5. Khôi phục Java release/encoding/`-parameters` và Maven plugin versions/config mà parent cũ cung cấp.
6. Cấu hình `spring-boot-maven-plugin` **cùng version** và bind `repackage` nếu cần executable archive.
7. Kiểm tra resource filtering; phân biệt Maven `@...@` và Spring `${...}`.
8. Chuyển property-based dependency overrides sang direct dependencyManagement/BOM precedence khi cần, với review.
9. Chạy `mvn -B clean verify` rồi kiểm tra log Surefire/Failsafe thực sự chạy tests.
10. Kiểm tra JAR/WAR output và `java -jar` trong môi trường không phụ thuộc IDE.
11. Bảo đảm CI/deploy sử dụng đúng artifact đã kiểm chứng, không build lại binary khác.
12. Sau khi đạt, áp quy tắc vào các module còn lại, từng module theo nhóm tương thích.

Nếu chuyển ngược từ BOM-only sang Starter Parent, **đừng giữ một execution `repackage` khác ID** cạnh execution parent đã quản lý; nó có thể chạy hai lần. Dùng effective POM để gỡ plugin config dư thừa cẩn thận.

## 12. Debug bằng Maven: nhìn vào effective POM và artifact thật

Từ từng project:

```bash
mvn --version
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn dependency:tree
mvn -B clean verify
```

Các goal Help/Dependency Plugin có thể cần tải từ repository. Effective POM cho biết model sau merge và inheritance/import, nhưng **không chứng minh mọi goal đã chạy**. Xem build log để kiểm tra `compiler:compile`, `surefire:test`, `jar:jar`, `spring-boot:repackage` đúng số lần, đúng version.

### 12.1. Checklist so sánh hai effective POM

| Hạng mục | Với parent | Với BOM |
| --- | --- | --- |
| Spring Boot managed versions | Từ parent/BOM chain | Từ imported BOM |
| Compiler Plugin version | Kế thừa parent | Khai thủ công/corporate parent |
| Java release | Boot defaults và `java.version` | Explicit `release`/property |
| Resources Plugin | Có Boot filtering conventions | Theo explicit/corporate configuration |
| Surefire | Managed by parent | Explicit/corporate version |
| Boot Maven Plugin version | Parent quản lý | Pin `3.5.7` |
| Repackage execution | Parent cung cấp khi plugin được dùng | Tự khai goal/execution |
| Build output | Executable Boot archive nếu plugin chạy | Executable Boot archive chỉ nếu repackage chạy |

Ngoài effective POM, dùng:

```bash
mvn dependency:tree -Dincludes=org.springframework.boot
```

để xem Boot versions và toàn bộ `mvn dependency:tree` khi cần đánh giá transitive conflicts. Nếu corporate parent hoặc profiles can thiệp, hai project có thể resolve dependency versions khác nhau dù cùng Spring Boot BOM.

### 12.2. Kiểm tra manifest và archive

Sau package, dùng:

```bash
jar tf target/boot-parent-demo-1.0.0.jar
```

hoặc thay tên JAR với BOM project. Trong executable Boot archive tìm `BOOT-INF/classes`, `BOOT-INF/lib` và `org/springframework/boot/loader`. Nếu không thấy, kiểm tra mục tiêu `repackage` trước khi đổ lỗi cho managed dependency versions.

Lệnh `mvn spring-boot:run` chạy ứng dụng bằng build classpath, **không phải bằng chứng** JAR đóng gói đã executable. Luôn smoke JAR thật bằng `java -jar`.

## 13. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Import BOM nhưng starter báo thiếu version | Đặt BOM sai chỗ, thiếu `type=pom`/`scope=import` | Kiểm tra `dependencyManagement` và effective POM |
| Starter không có trong classpath | Chỉ import BOM, chưa khai dependency | Thêm starter vào `dependencies` |
| Parent và corporate parent cùng xuất hiện | Hai `<parent>` trực tiếp không hợp lệ | Chọn một parent, dùng BOM import hoặc parent chain |
| BOM-only báo compiler source/target cũ | Thiếu Compiler Plugin version/release | Pin compiler, `release=17` |
| BOM-only `java.version=17` không tác dụng | Property chưa được compiler sử dụng | Gắn property vào `maven.compiler.release`/config |
| BOM-only JAR không chạy `java -jar` | Thiếu `spring-boot:repackage` | Bind execution + kiểm jar layout |
| Boot Maven Plugin không có version | BOM import không quản lý plugins | Pin plugin version/corporate pluginManagement |
| Parent dùng plugin configuration nhưng repackage không chạy | Plugin chưa được khai thực sự hoặc bị skip | Khai Boot Maven Plugin trong build/plugins |
| Repackage chạy hai lần | Thêm execution mới cạnh ID `repackage` của parent | Merge bằng cùng ID hoặc bỏ duplicate |
| `slf4j.version` không override trong BOM-only | BOM import khác parent property inheritance | Direct dependencyManagement override trước BOM |
| Placeholder `${DB_URL}` bị thay sai | Maven filtering lẫn Spring runtime placeholder | Cấu hình `@...@` hoặc tắt Maven filtering |
| `NoClassDefFoundError` sau nâng dependency | Override phiên bản gây binary incompatibility hoặc thiếu library | Xem dependency tree/runtime jar |
| `BOOT-INF/lib` thiếu runtime lib | Scope/exclusion/repackage khác dự kiến | Kiểm POM graph và JAR archive |
| Dùng Spring Boot Plugin 4.x với BOM 3.5 | Version divergence chưa được kiểm chứng | Đồng bộ plugin với Spring Boot release |
| WAR không chạy/deploy được | Servlet initializer/scope/War Plugin/container sai | Kiểm packaging contract và test container |
| Maven success nhưng không test | Plugin/provider/skip flags/test patterns | Xem Surefire reports và counts |

### 13.1. Khi nào không nên dùng Spring Boot Starter Parent?

- Một tổ chức đã chuẩn hóa parent độc lập cho nhiều mô hình module và không muốn parent đó thừa kế Boot.
- Project chỉ cần Boot-managed dependencies, còn output là **library JAR** hoặc một artifact không cần executable Boot loader.
- Build cần compiler/Surefire/resources/packaging policies không tương thích Boot defaults mà override quá khó kiểm soát.
- Một mono-repo có nhiều version trains/frameworks phải phối hợp BOMs rõ ràng.

Ngược lại, với một ứng dụng Spring Boot mới, không có corporate parent bắt buộc và muốn giảm POM boilerplate, Starter Parent là lựa chọn tiện lợi và được Boot hướng dẫn chính thức.

## 14. Câu hỏi tự luyện và đáp án

**Câu 1.** Vì sao có thể khai `spring-boot-starter-test` không có version với cả parent lẫn BOM import?

**Đáp án:** Vì cả hai cung cấp dependency management tương ứng. Nhưng test dependency vẫn phải được khai trong `dependencies`.

**Câu 2.** Import `spring-boot-dependencies` có tự đem `spring-boot:repackage` execution vào project không?

**Đáp án:** Không. BOM import chỉ chuyển dependencyManagement entries; Boot plugin goals/versions phải được khai qua app POM hoặc corporate parent.

**Câu 3.** Maven có cho khai trực tiếp cả corporate parent và Spring Boot parent không?

**Đáp án:** Không. Mỗi POM có một parent trực tiếp. Có thể tạo parent chain hoặc dùng corporate parent + Boot BOM import.

**Câu 4.** BOM-only project có `<java.version>17</java.version>`. Điều đó tự buộc compiler dùng release 17 chưa?

**Đáp án:** Chưa. Cần POM/corporate parent tham chiếu property vào Compiler Plugin `release` hoặc `maven.compiler.release`.

**Câu 5.** Tại sao `slf4j.version` override theo cách parent có thể không có tác dụng khi chỉ import BOM?

**Đáp án:** Import BOM không thừa kế property model của BOM như parent; dùng dependencyManagement direct override hoặc một imported BOM ưu tiên có review.

**Câu 6.** Nếu cùng BOM 3.5.7, hai projects có luôn tạo JAR cùng kiểu không?

**Đáp án:** Không. Packaging và Maven plugin executions là cấu hình build; có thể khác nhau hoàn toàn dù dependencies giống nhau.

**Câu 7.** Một module Java library chỉ cần Boot-managed dependency versions có phải bind `repackage` không?

**Đáp án:** Không. Library JAR tiêu chuẩn thường được consumer Maven/Gradle resolve; không cần executable Boot loader trừ khi thiết kế sản phẩm yêu cầu.

**Câu 8.** Sau migration parent → BOM-only, `mvn clean verify` pass nhưng JAR không có `BOOT-INF/lib`. Cần kiểm tra điều gì đầu tiên?

**Đáp án:** `spring-boot-maven-plugin:repackage` có được bind/chạy không, rồi kiểm artifact path/manifest. Không cần thay BOM version ngay.

**Câu 9.** Vì sao nên để Maven filtering nhận `@project.version@` mà để Spring xử lý `${DB_URL:...}`?

**Đáp án:** Hai placeholder thuộc hai thời điểm khác nhau: Maven build và Spring runtime. Maven filtering sai delimiter có thể thay/cản trở placeholder của Spring.

**Câu 10.** Cách nào đơn giản hơn để bắt đầu một Boot app mới không có corporate parent, và cách nào phù hợp corporate parent sẵn có?

**Đáp án:** Starter Parent thường đơn giản hơn cho app mới; BOM import hợp với corporate parent, nhưng phải bảo đảm các plugin/version/executions cần thiết.

## 15. Tài liệu chính thức

- [Spring Boot 3.5 — Maven Plugin: Inheriting the Starter Parent / Without the Parent](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html)
- [Spring Boot 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Build Systems / Dependency Management](https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 3.5 — Building an Executable Jar with Maven](https://docs.spring.io/spring-boot/3.5/how-to/build.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Spring Boot 3.5.7 release announcement](https://spring.io/blog/2025/10/23/spring-boot-3-5-7-available-now)
