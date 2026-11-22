# Cấu hình plugin khi không kế thừa Spring Boot parent trong Maven

## 1. Vấn đề: dùng Spring Boot nhưng không dùng spring-boot-starter-parent

Nhiều dự án Spring Boot được tạo với parent POM:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
</parent>
```

Parent này không chỉ quản lý các phiên bản dependencies. Nó còn chuẩn bị **plugin management**, thiết lập Java/encoding, `-parameters` của compiler, cấu hình resource filtering và một execution của `spring-boot:repackage`. Nhờ thế nhiều ví dụ Spring Boot chỉ cần khai báo tên plugin `spring-boot-maven-plugin` trong `<plugins>` mà không ghi version hoặc execution.

Nhưng trong thực tế, bạn có thể:
- phải kế thừa **parent POM nội bộ** của tổ chức;
- có một parent Maven riêng chịu trách nhiệm license, Enforcer, repository và CI;
- quản lý plugin versions theo chính sách doanh nghiệp;
- muốn cấu hình Maven tường minh, không phụ thuộc các convention của Spring Boot parent.

**Không dùng Spring Boot parent hoàn toàn hợp lệ.** Bạn có thể import `spring-boot-dependencies` BOM để dùng dependency versions được Spring Boot kiểm thử, rồi **tự cấu hình Maven plugins**. Điểm mấu chốt là:

> **BOM import quản lý dependency versions, không mang theo plugin management, không tự bind goal `spring-boot:repackage`, và không tự cấu hình Compiler/Surefire/WAR/Resources Plugin.**

Bài này hướng dẫn cách thiết kế POM không kế thừa `spring-boot-starter-parent`, với trọng tâm **Maven plugin configuration** cho cả **executable JAR** và **executable/traditional WAR**. Ví dụ hoàn chỉnh dùng Maven 3.9.x, Java 17, Spring Boot **3.5.16** (một bản 3.5.x được ghim rõ), Compiler Plugin 3.13.0, Surefire Plugin 3.5.2, WAR Plugin 3.4.0 và Spring Boot Maven Plugin cùng version với framework.

### Bạn sẽ làm được gì?

1. Phân biệt `<parent>`, `<dependencyManagement>` và `<pluginManagement>`.
2. Import Spring Boot BOM đúng `type=pom` và `scope=import`.
3. Ghép một POM WAR đầy đủ **không có Spring Boot parent**, với version và execution plugin tường minh.
4. Gắn `spring-boot:repackage` vào `package` để tạo executable WAR/JAR, không chỉ một archive Maven thông thường.
5. Cấu hình Java 17, `-parameters`, UTF-8, JUnit Jupiter/Surefire và Maven WAR Plugin không cần `web.xml`.
6. Phân biệt Tomcat `provided` và executable WAR với `WEB-INF/lib-provided`.
7. Chạy một Spring Boot REST endpoint, kiểm tra HTTP response, test và nội dung archive.
8. Chuyển sang executable JAR, dùng corporate parent, quản lý filtering và tránh xung đột plugin versions.
9. Xử lý các lỗi `no main manifest attribute`, thiếu `repackage`, tests không chạy và WAR không tương thích với servlet container.

**Lựa chọn phiên bản:** Spring Boot 3.5.16 yêu cầu ít nhất Java 17 và Maven 3.6.3+. Dòng 3.5.x được dùng để có ví dụ dễ hiểu về Servlet WAR/Tomcat 10.1. Khi khởi tạo sản phẩm mới, cần đối chiếu dòng Spring Boot đang được tổ chức hỗ trợ và kiểm tra thay đổi Spring Boot 4.x; không coi bộ version ở đây là yêu cầu dùng mãi trong production.

## 2. Spring Boot parent đã làm những gì?

### 2.1. Thừa kế POM khác với import BOM

| Chức năng | Kế thừa spring-boot-starter-parent | Chỉ import spring-boot-dependencies BOM |
| --- | --- | --- |
| Dependency versions được quản lý | Có | Có |
| Có thể bỏ `<version>` của starter dependencies | Có | Có |
| Maven plugin versions/configuration được parent chuẩn bị | Có | **Không qua BOM import** |
| Execution `spring-boot:repackage` được parent chuẩn bị | Có | **Không** |
| Java 17/UTF-8/`-parameters` được parent định sẵn | Có | Phải tự khai báo hoặc được parent khác cấp |
| Resource filtering phù hợp `application.properties`/YAML | Parent chuẩn bị | Tự quyết định |
| Có thể đồng thời kế thừa parent doanh nghiệp | Không ở cùng cấp `<parent>` | Có; import BOM không chiếm parent slot |
| Tự tạo executable archive khi chỉ đặt starter dependency | Chỉ khi plugin được khai báo theo setup phù hợp | **Không** |

Một Maven POM chỉ có **một `<parent>` trực tiếp**. Nếu bạn đã cần `com.company:company-parent`, không thể thêm một `<parent>` thứ hai cho Spring Boot. Nhưng bạn vẫn có thể import BOM Spring Boot bên trong `<dependencyManagement>`.

### 2.2. Dependency management giải quyết bài toán versions của libraries

Ví dụ import:

```xml
<properties>
    <spring-boot.version>3.5.16</spring-boot.version>
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
```

Các starter được BOM quản lý có thể không ghi version:

```xml
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
```

Hai đoạn trên **chưa phải một POM đầy đủ**. Chúng chỉ giải quyết thư viện. Import BOM không tạo `spring-boot-maven-plugin`, không quyết định `maven-compiler-plugin` chạy `--release 17` và không bắt buộc Surefire ở phiên bản hỗ trợ JUnit Platform.

### 2.3. Plugin management là một namespace khác

Dependency artifact:

```text
org.springframework.boot:spring-boot-starter-web
```

Build plugin artifact:

```text
org.springframework.boot:spring-boot-maven-plugin
```

Đây là hai nhóm sử dụng khác nhau. `<dependencyManagement>` quản lý dependencies; `<build><pluginManagement>` quản lý plugin default version/config/executions. Không đưa Spring Boot Maven Plugin vào `<dependencies>` với hy vọng Maven sẽ chạy `repackage`. Nó phải được khai báo trong `<build><plugins>`.

Đặc biệt, `pluginManagement` có thể **đặt cấu hình mặc định** cho plugin, nhưng không đồng nghĩa plugin chắc chắn được thực thi ở một lifecycle phase nếu không được kích hoạt phù hợp. Trong project không có Spring Boot parent, cách minh bạch nhất là ghi phiên bản và execution trong `<build><plugins>` của chính project.

## 3. Spring Boot Maven Plugin và goal repackage

### 3.1. Vai trò của repackage

Goal `spring-boot:repackage` lấy **JAR hoặc WAR đã được Maven tạo trong phase package**, rồi đóng gói lại thành archive có thể khởi động bằng `java -jar`. Nó thêm Spring Boot loader, sửa manifest và bố trí dependencies theo cấu trúc của Boot.

Với executable JAR:
- application classes: `BOOT-INF/classes/`;
- dependencies: `BOOT-INF/lib/`;
- manifest có Main-Class của Boot launcher và Start-Class của application.

Với executable WAR:
- application classes: `WEB-INF/classes/`;
- dependencies thông thường: `WEB-INF/lib/`;
- dependencies `provided` dành cho chạy archive độc lập: `WEB-INF/lib-provided/`.

**Đây không phải Maven Shade Plugin:** Boot không trộn từng `.class` từ mọi JAR vào cùng một thư mục gốc. Nó giữ nested JARs theo layout Boot và dùng launcher của Spring Boot. Điều này quan trọng khi audit classpath, duplicate libs và công cụ giải nén.

### 3.2. Bind repackage khi không có Spring Boot parent

Một cấu hình tối thiểu:

```xml
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
```

Đây là **plugin fragment** thuộc `<build><plugins>`. `repackage` có default phase `package`; không bắt buộc đặt `<phase>package</phase>`. Ghi tường minh nếu nhóm cần dễ đọc, nhưng đừng bind hai executions cùng goal rồi để nó chạy hai lần.

Khi kế thừa `spring-boot-starter-parent`, parent **đã** đặt execution có ID `repackage`. Khi không kế thừa, phải tự khai báo execution hoặc có corporate parent/pluginManagement cung cấp tương đương. Nếu bạn copy một ví dụ dành cho parent mà chỉ có:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
</plugin>
```

thì có thể gọi `mvn spring-boot:run` được, nhưng **`mvn package` không nhất thiết tạo executable JAR/WAR**, vì thiếu binding của `repackage`.

### 3.3. Không gọi repackage như một compiler

Goal `repackage` cần archive do Maven JAR/WAR Plugin đã tạo. Nếu gọi:

```bash
mvn spring-boot:repackage
```

trên project mới chưa có JAR/WAR từ `package`, có thể lỗi “Source file must not be null” hoặc thiếu source archive. Cách build chuẩn là:

```bash
mvn clean package
```

với `repackage` execution đã được bind. Nếu project không bind execution mà muốn gọi goal thủ công, có thể dùng `mvn package spring-boot:repackage`, nhưng **không nên gọi thêm goal thủ công nếu `repackage` đã được bind**, vì có thể thực hiện đóng gói lặp.

### 3.4. Main-Class và Start-Class

Trong executable Boot archive, `Main-Class` thường là launcher của Spring Boot; `Start-Class` là class có `main(String[] args)` của ứng dụng. Đừng ghi Main-Class ứng dụng vào Maven JAR Plugin để “chữa” manifest Boot — repackage quản lý manifest.

Khi không dùng Spring Boot parent, nếu Boot không tìm được một main class duy nhất (ví dụ có nhiều class có `main`), hãy cấu hình:

```xml
<configuration>
    <mainClass>com.example.bootnoparent.DemoApplication</mainClass>
</configuration>
```

trong Spring Boot Maven Plugin. `<start-class>` là property tiện lợi mà Spring Boot parent có thể kết nối với plugin; **không nên giả định chỉ khai báo property đó là đủ khi không dùng parent**.

## 4. Bộ Maven plugins nên khai báo rõ

Một project không dùng parent Spring Boot cần chịu trách nhiệm về các quyết định build thường được parent đặt trước:

| Plugin/cấu hình | Tại sao cần quan tâm? | Cách ví dụ xử lý |
| --- | --- | --- |
| `spring-boot-maven-plugin` | Tạo executable JAR/WAR, chạy Boot | Ghim `3.5.16`, khai báo `repackage` |
| `maven-compiler-plugin` | Java language/API release và parameter metadata | Ghim `3.13.0`, Java `17`, `parameters=true` |
| `maven-surefire-plugin` | Chạy JUnit Jupiter tests ở `test` | Ghim `3.5.2` |
| `maven-war-plugin` | Tạo WAR trước khi repackage | Ghim `3.4.0`, không yêu cầu `web.xml` |
| `maven-resources-plugin` | Copy/filter application.properties/YAML | Chỉ bật filtering nếu cần; không để Maven thay runtime tokens |
| `maven-jar-plugin` | Tạo JAR thường trước repackage ở packaging JAR | Với JAR variant, ghim version phù hợp |
| `maven-failsafe-plugin` | IT nếu dự án có integration tests riêng | Cấu hình tùy nhu cầu, không tự có chỉ nhờ BOM |

### 4.1. Java 17 và -parameters

Tối thiểu:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Spring Boot parent thường còn đặt compiler với `-parameters` để giữ tên tham số trong bytecode, hữu ích cho reflection, binding và một số framework behaviors. Với project không dùng parent, cấu hình rõ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Trong POM runnable bên dưới dùng `maven.compiler.release=17` và `parameters=true`; không khai báo `release` hai lần với giá trị mâu thuẫn. Java `--release 17` giúp giới hạn Java SE API tương ứng, an toàn hơn chỉ đặt `source`/`target` nếu build trên JDK mới.

`mvn -version` cho biết JDK Maven đang sử dụng. Nếu Maven chạy bằng JDK 11 nhưng yêu cầu `release=17`, build không thể thành công trừ khi dùng JDK/toolchain khác phù hợp. Import BOM không tự tải/cài JDK.

### 4.2. Surefire và JUnit Platform

Spring Boot BOM quản lý version của `spring-boot-starter-test` và những thư viện kiểm thử liên quan, nhưng **không tự quản lý phiên bản Maven Surefire Plugin chỉ bằng BOM import**. Nếu project dùng plugin mặc định cũ của Maven/corporate parent, JUnit Jupiter tests có thể không được phát hiện như kỳ vọng.

Hãy ghim Surefire 3.5.2 (hoặc version đã được tổ chức xác minh) và dùng `mvn test`/`mvn verify` để biết JUnit 5 thực sự đã chạy. Kết quả `BUILD SUCCESS` không chứng minh tests được chạy nếu cấu hình làm chúng bị skip hoặc test provider không tìm thấy class.

### 4.3. WAR Plugin không phải Boot Plugin

Với `<packaging>war</packaging>`, Maven WAR Plugin tạo archive web chuẩn ở phase `package`. Spring Boot Maven Plugin **repackage archive đó**. Hai plugin có vai trò khác nhau:

```text
maven-compiler-plugin -> compile .class
maven-surefire-plugin -> execute JUnit tests
maven-war-plugin      -> create standard WAR
spring-boot-maven-plugin:repackage -> make WAR executable
```

Đối với Servlet 3+ style deployment, một app Spring Boot có thể không cần `WEB-INF/web.xml`. WAR Plugin 3.4.0 hỗ trợ `failOnMissingWebXml=false`; ví dụ cấu hình tường minh để tránh sự khác biệt từ legacy parent hoặc template cũ.

## 5. Ví dụ hoàn chỉnh: WAR không dùng Spring Boot parent

Bộ ví dụ này vừa **triển khai lên servlet container tương thích** vừa **chạy trực tiếp bằng java -jar** sau khi Spring Boot repackage.

Yêu cầu:
- Maven 3.9.x;
- JDK 17+ (tài liệu Spring Boot 3.5.16 yêu cầu Java 17 tối thiểu);
- repository có thể tải các artifact ở lần build đầu;
- khi triển khai WAR truyền thống, servlet container tương thích **Jakarta Servlet**, ví dụ Tomcat 10.1 phù hợp Boot 3.5.x. **Tomcat 9 dùng javax.servlet không tương thích trực tiếp với Spring Boot 3.5.x**.

### 5.1. Cây thư mục

```text
boot-no-parent-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/bootnoparent/
    │   │   ├── DemoApplication.java
    │   │   └── HelloController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/bootnoparent/
            └── HelloControllerTest.java
```

Chỉ có một Spring Boot application class, một REST controller và một JUnit Jupiter/MockMvc test. Không cần database, Docker, Servlet `web.xml` hay WAR overlay.

### 5.2. Tệp pom.xml đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>boot-no-parent-lab</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <!-- Không có thẻ <parent> của Spring Boot -->
    <properties>
        <spring-boot.version>3.5.16</spring-boot.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <!-- Chỉ nhập BOM dependency versions -->
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
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- WAR cho servlet container ngoài: Tomcat do container cấp -->
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
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
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
                <configuration>
                    <mainClass>com.example.bootnoparent.DemoApplication</mainClass>
                </configuration>
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

**Phân tích POM theo từng khối:**

1. **Không có `<parent>`**. Đây là thiết lập thực sự không kế thừa Spring Boot starter parent.
2. `spring-boot-dependencies` được import bằng `type=pom`, `scope=import` trong `dependencyManagement`, giúp bỏ versions của ba Boot starter dependencies.
3. `spring-boot.version` được dùng **cả ở BOM lẫn Spring Boot Maven Plugin** để tránh lệch version build plugin với runtime framework.
4. Spring Boot web starter cung cấp MVC và embedded Tomcat theo mặc định. Direct dependency `spring-boot-starter-tomcat` có `provided` để container triển khai WAR có thể cấp Servlet runtime của chính nó.
5. Compiler Plugin được ghim, `maven.compiler.release=17` điều khiển release; `parameters=true` giữ metadata tên tham số.
6. Surefire Plugin phiên bản đủ mới để chạy JUnit Jupiter trong `spring-boot-starter-test`.
7. WAR Plugin tạo archive chuẩn và không đòi `web.xml`.
8. Spring Boot Maven Plugin có **explicit version và execution `repackage`**. Đây là phần quan trọng nhất khi bỏ parent.
9. `mainClass` được ghi rõ để không cần suy từ tên entry point nếu sau này project có nhiều `main`.
10. `packaging=war` + `repackage` cho executable WAR; nó **không** phải `spring-boot-starter-parent`, không cần Shade Plugin.

**Lưu ý về `provided`:** Maven `provided` thông thường không đưa Tomcat vào WAR runtime libs của container. Khi Boot tạo executable WAR, những thư viện provided dùng để chạy trực tiếp có thể nằm ở `WEB-INF/lib-provided`. Khi deploy WAR vào Tomcat ngoài, container không xem `WEB-INF/lib-provided` như `WEB-INF/lib`; do đó tránh đụng thư viện Tomcat của server. Khi chạy `java -jar`, Boot launcher có thể sử dụng chúng.

### 5.3. src/main/java/com/example/bootnoparent/DemoApplication.java

```java
package com.example.bootnoparent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(DemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Ý nghĩa:
- `@SpringBootApplication` kích hoạt component scanning từ package `com.example.bootnoparent` và auto-configuration.
- `main()` hỗ trợ chạy trực tiếp executable WAR bằng `java -jar`.
- `SpringBootServletInitializer` + `configure(...)` cung cấp điểm khởi tạo khi WAR được triển khai **trong servlet container bên ngoài**.
- Code trên thuộc **Spring MVC/Servlet**, không phải WebFlux server ứng dụng thuần; tài liệu Spring Boot không hỗ trợ WAR truyền thống cho WebFlux application theo cùng cơ chế.

Bạn có thể để `SpringBootServletInitializer` trong source với JAR nếu muốn, nhưng trong executable JAR thông thường không cần nó. Tại đây nó cần thiết để minh họa cả hai đường triển khai WAR.

### 5.4. src/main/java/com/example/bootnoparent/HelloController.java

```java
package com.example.bootnoparent;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Boot without parent";
    }
}
```

Controller không cần truy cập external services. Request HTTP GET `/hello` sẽ trả **HTTP 200** và response body chính xác `Hello from Boot without parent` khi web server khởi động và không có context path/prefix tùy chỉnh.

### 5.5. src/main/resources/application.properties

```properties
spring.application.name=boot-no-parent-lab
server.port=${PORT:8080}
```

Ở đây `${PORT:8080}` là **Spring configuration placeholder**, không phải Maven token định thay trong package. Vì POM đầy đủ **không bật resource filtering**, Maven thường chỉ copy file nguyên nội dung. Lúc runtime, Spring nhận `PORT` từ environment nếu có, nếu không dùng 8080.

Nếu bạn chạy trên máy có biến môi trường `PORT` khác 8080, endpoint sẽ dùng port đó; vì vậy kết quả lệnh HTTP ở mục sau giả định `PORT` không đặt hoặc bằng 8080. Không bịa rằng ứng dụng chắc chắn luôn lắng nghe 8080.

### 5.6. src/test/java/com/example/bootnoparent/HelloControllerTest.java

```java
package com.example.bootnoparent;

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
class HelloControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void helloEndpointRespondsWithBody() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "Hello from Boot without parent"));
    }
}
```

Test này dùng **Spring Boot 3.5.x** imports và JUnit Jupiter. `@SpringBootTest` dựng context, `@AutoConfigureMockMvc` cấu hình mock HTTP request không cần server thật lắng nghe port 8080. Nó kiểm tra status 200 và body chính xác, đủ làm smoke test cho controller và dependency management.

**Không nhầm MockMvc với external WAR deployment test.** MockMvc xác nhận Spring application context + MVC routing, nhưng không kiểm chứng một Tomcat bên ngoài chấp nhận WAR. Triển khai thực tế cần test tiếp trên container được hỗ trợ.

## 6. Các lệnh thực hành và kết quả dự kiến

### 6.1. Kiểm tra môi trường

Tại thư mục `boot-no-parent-lab`:

```bash
mvn -version
java -version
javac -version
```

Maven cần phiên bản tương thích (ví dụ 3.9.x), JDK 17 hoặc cao hơn. Nếu Maven dùng JDK 11 trong `mvn -version` nhưng project yêu cầu `--release 17`, build sẽ thất bại ở compiler. `java -version` trên PATH đôi khi khác Java mà Maven dùng; ưu tiên xem cả hai.

### 6.2. Chạy test và tạo executable WAR

```bash
mvn clean verify
```

`verify` đi qua `test` và `package`, nên Surefire chạy `HelloControllerTest` rồi WAR Plugin và Spring Boot Maven Plugin đóng gói. Với code chính xác ở trên và dependencies tải được, kết quả mong đợi:

```text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **thông tin tổng hợp mong đợi**, không phải toàn bộ console log với timestamp, plugin versions, download status. Có thể thay đổi theo cờ skip, test report format hoặc môi trường.

Archive chính:

```text
target/boot-no-parent-lab-1.0.0.war
```

Spring Boot repackage có thể giữ archive ban đầu dưới tên có đuôi `.original`; không triển khai nhầm archive gốc khi mục tiêu là executable WAR.

### 6.3. Kiểm tra cấu trúc WAR

```bash
jar tf target/boot-no-parent-lab-1.0.0.war
```

Trong danh sách dài, tìm các entries:

```text
WEB-INF/classes/com/example/bootnoparent/DemoApplication.class
WEB-INF/classes/com/example/bootnoparent/HelloController.class
WEB-INF/classes/application.properties
WEB-INF/lib/
WEB-INF/lib-provided/
```

Có thể còn Spring Boot loader, manifest, JAR của dependencies và lớp khác. `WEB-INF/lib-provided` dự kiến chứa những Tomcat libraries có `scope=provided` dùng khi chạy executable WAR. Tên JAR cụ thể có version do BOM quản lý, vì vậy không hard-code một tên file Tomcat tương ứng.

Một WAR thường **không có** `BOOT-INF/classes`/`BOOT-INF/lib` như executable JAR. Đừng kiểm tra sai layout rồi kết luận repackage thất bại.

### 6.4. Chạy WAR bằng Java

```bash
java -jar target/boot-no-parent-lab-1.0.0.war
```

Ứng dụng khởi động web server dùng provided Tomcat libs trong executable WAR theo cơ chế Boot loader. Log khởi động có timestamp và nhiều dòng thay đổi theo máy/port, nên **không có stdout cố định để cam kết**. Khi Tomcat sẵn sàng và `PORT` trống hoặc là 8080, ở terminal khác:

```bash
curl --silent http://localhost:8080/hello
```

**HTTP response body chính xác:**

```text
Hello from Boot without parent
```

Trên Windows PowerShell, có thể dùng `curl.exe` thay cho `curl` nếu `curl` là alias. Endpoint được truy cập qua `http://localhost:8080/hello` nếu port mặc định. Nếu biến môi trường `PORT` là một port khác, thay số port trong URL.

**Không hứa lệnh HTTP trả thành công khi server chưa chạy, port đã bị chiếm hoặc firewall/network chặn request.** Những điều kiện đó là vấn đề runtime, không tự chứng minh BOM hoặc repackage lỗi.

### 6.5. Triển khai WAR lên Tomcat ngoài

Với Tomcat 10.1 tương thích Boot 3.5:
1. Build bằng `mvn clean package`.
2. Dùng archive `target/boot-no-parent-lab-1.0.0.war` sau repackage.
3. Deploy theo cơ chế của Tomcat (ví dụ sao chép WAR vào thư mục `webapps` khi được phép).
4. Servlet container khởi tạo app qua `SpringBootServletInitializer`.
5. URL có thể chứa **context path** từ tên WAR, ví dụ `/boot-no-parent-lab-1.0.0/hello`, hoặc `/hello` khi ứng dụng được triển khai làm ROOT context.

Trong WAR truyền thống, Tomcat ngoài cung cấp server runtime; trong `java -jar`, Boot dùng layout executable WAR và thư viện phù hợp ở `WEB-INF/lib-provided`. Cùng một artifact có hai con đường chạy nhưng phải test cả hai nếu sản phẩm cam kết hỗ trợ cả hai.

**Không triển khai Boot 3.5 lên Tomcat 9 theo kiểu WAR thông thường.** Tomcat 9 dựa trên `javax.servlet`, trong khi Spring Boot 3 sử dụng `jakarta.servlet`. Đây là không tương thích API, không thể sửa bằng cách chỉ đổi `maven-war-plugin` version.

## 7. Khi muốn executable JAR thay vì WAR

Nếu ứng dụng chỉ cần chạy bằng `java -jar` và không cần servlet container ngoài, executable JAR thường đơn giản hơn.

Điều chỉnh **POM runnable hiện tại**, không tạo hai file POM xung đột:

1. Đổi `<packaging>war</packaging>` thành `<packaging>jar</packaging>`.
2. **Bỏ** direct dependency `spring-boot-starter-tomcat` với `scope=provided` để web starter cung cấp embedded server theo runtime bình thường.
3. Bỏ `maven-war-plugin`; có thể ghim `maven-jar-plugin` phiên bản 3.4.2 trong `<plugins>`.
4. Giữ BOM import, Java compiler/Surefire config, Spring Boot Maven Plugin version + `repackage` execution.
5. `DemoApplication` có thể tiếp tục extends `SpringBootServletInitializer` mà không phá JAR, nhưng có thể rút gọn thành class `@SpringBootApplication` với `main` nếu không cần WAR deployment.

Đoạn plugin JAR minh họa:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
</plugin>
```

Đây là **thay thế WAR Plugin**, không dùng để tạo WAR. Sau đó:

```bash
mvn clean package
java -jar target/boot-no-parent-lab-1.0.0.jar
```

Executable JAR thường chứa:
- `BOOT-INF/classes/com/example/bootnoparent/DemoApplication.class`;
- `BOOT-INF/classes/com/example/bootnoparent/HelloController.class`;
- `BOOT-INF/lib/` và các nested dependency JARs;
- Boot launcher metadata.

Cùng URL `/hello` sẽ trả body như trên nếu server chạy. **Không xem file JAR xây từ Maven JAR Plugin đơn thuần là executable Boot JAR**: phải bảo đảm `repackage` thực sự đã chạy.

## 8. Corporate parent, pluginManagement và inheritance

### 8.1. Parent nội bộ cùng với Spring Boot BOM

Ví dụ tổ chức bắt buộc dùng:

```xml
<parent>
    <groupId>com.example.build</groupId>
    <artifactId>company-maven-parent</artifactId>
    <version>2.0.0</version>
</parent>
```

Đây chỉ là **đoạn mô tả một parent nội bộ giả định**, không phải tọa độ đã phát hành. Không copy nguyên vào project demo khi artifact này không tồn tại. Nếu có parent thật, Maven có thể kế thừa pluginManagement, compiler settings, repositories và một số policy từ parent ấy. Bên cạnh đó, vẫn import `spring-boot-dependencies` BOM trong `dependencyManagement`.

**Phải kiểm tra effective POM**: một parent nội bộ có thể đã pin Compiler Plugin ở version cũ, bind Surefire cũ, bật filtering trên `application.properties` hoặc có execution Boot plugin tương tự. Không tự ghi thêm hai executions trùng goal chỉ vì “không dùng Spring Boot parent”.

### 8.2. pluginManagement vs plugins

`pluginManagement` chứa version/cấu hình mặc định cho plugin khi plugin được dùng, ví dụ tổ chức có thể đặt:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>${spring-boot.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Đoạn đó **không tự bảo đảm repackage goal được chạy**. Cần bật plugin trong `<build><plugins>` cùng execution, hoặc có quản lý execution từ parent được áp dụng khi plugin xuất hiện.

Một nhóm có thể đặt toàn bộ pluginManagement trong parent doanh nghiệp để các modules dùng nhất quán; khi đó mỗi module chỉ khai báo plugin cần thiết và execution theo convention. Nhưng **đừng phỏng đoán cấu hình đã được kế thừa**: đọc `mvn help:effective-pom` và lifecycle logs.

### 8.3. Tránh double execution khi migrate parent

Nếu trước đó dự án dùng `spring-boot-starter-parent`, parent đã quản lý execution `repackage`. Khi bỏ parent và thay bằng BOM, execution ấy biến mất trừ khi bạn chuyển nó sang POM/corporate parent.

Ngược lại, nếu corporate parent **đã** cung cấp execution, thêm một execution khác id có thể khiến repackage chạy hai lần. Khi muốn override execution kế thừa, dùng đúng `id` (ví dụ `repackage`), kiểm tra merge semantics rồi xác nhận log plugin chỉ có lần thực thi mong muốn.

Không trộn `spring-boot-maven-plugin` với Maven Shade Plugin nhằm “làm thêm một lớp uber JAR” nếu chưa hiểu cả hai cùng thay archive; Boot dùng nested JAR layout, Shade dùng relocation/merge, kết hợp thiếu kiểm soát có thể phá manifest hoặc classpath.

## 9. Phần dễ bỏ sót: resource filtering khi không dùng parent

### 9.1. Spring property và Maven property dùng cùng cú pháp

Một Spring application property:

```properties
server.port=${PORT:8080}
app.message=${GREETING:Hello}
```

`${...}` là runtime placeholder của Spring. Maven Resources Plugin cũng có delimiter mặc định `${*}` khi **bật filtering**. Nếu bạn bật `<filtering>true</filtering>` mà không điều chỉnh delimiters, Maven có thể nhận nhầm hoặc thay giá trị ngay lúc build.

Spring Boot parent có cấu hình resource filtering phù hợp Spring placeholders, thường dùng Maven tokens dạng `@project.version@`. **Chỉ import BOM không kéo cấu hình ấy về.**

Ví dụ runnable ở mục 5 **không bật filtering**, nên file `application.properties` được copy như dữ liệu. Đây là cách đơn giản nhất nếu không cần chèn metadata lúc build.

### 9.2. Khi thực sự cần filtering, chỉ dùng @...@ cho Maven

Nếu muốn chèn version vào resource text:

```properties
app.build.version=@project.version@
server.port=${PORT:8080}
```

thì bạn có thể bật filtering một cách có chủ đích và cấu hình Maven Resources Plugin:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>true</filtering>
    </resource>
</resources>
```

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <delimiters>
            <delimiter>@</delimiter>
        </delimiters>
        <useDefaultDelimiters>false</useDefaultDelimiters>
    </configuration>
</plugin>
```

**Đây là hai đoạn cấu hình bổ sung**, lần lượt đặt trong `<build>` và `<build><plugins>`. Không tự thêm chúng vào POM demo nếu không cần. Với version 1.0.0, `app.build.version` thành 1.0.0, `server.port=${PORT:8080}` được giữ nguyên cho Spring.

**Đừng quên `useDefaultDelimiters=false`.** Chỉ thêm delimiter `@` chưa bảo đảm Maven ngừng nhận `${*}`. Đồng thời không nên filter ảnh, JAR, font hoặc template runtime; khi cần, tách directory filtering=true và filtering=false.

## 10. Plugin versions khác dependency versions như thế nào?

### 10.1. Đừng đặt version Boot plugin theo default Maven

BOM Spring Boot quản lý versions của rất nhiều dependencies, nhưng **không khiến Maven tự chọn spring-boot-maven-plugin cùng version**. Vì vậy:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>${spring-boot.version}</version>
</plugin>
```

là lựa chọn rõ ràng. Khi nâng framework BOM, nâng đồng bộ Boot plugin và chạy regression tests. Một plugin version cũ có thể không biết layout hoặc feature của framework runtime mới.

### 10.2. Không dựa hoàn toàn vào lifecycle plugin mặc định

Một Maven distribution hoặc super POM có thể cung cấp versions mặc định của Compiler/WAR/Surefire/JAR plugins. Nhưng chúng không nhất thiết giống những version Spring Boot parent thường quản lý. Ví dụ một Surefire quá cũ có thể không chạy JUnit Jupiter như bạn mong đợi, và một WAR Plugin quá cũ có thể yêu cầu `web.xml` hoặc gặp vấn đề với JDK mới.

Do đó ví dụ chọn ghi rõ versions. Trong team, có thể quản lý tập versions này ở parent nội bộ; đích đến vẫn là **effective POM có versions và executions được kiểm soát**.

### 10.3. BOM import không cho override property theo cách parent làm

Khi kế thừa `spring-boot-starter-parent`, parent cho phép override nhiều library versions qua project properties như `slf4j.version`. Khi **import BOM** từ `dependencyManagement`, những properties nằm bên trong BOM **không tự trở thành properties có thể override từ importing POM theo cách parent inheritance**.

Nếu cần override một dependency version cụ thể, hãy khai báo `dependencyManagement` entry tương ứng **trước BOM import**, hoặc dùng cơ chế dependency management rõ ràng được kiểm tra. Chỉ thêm `<slf4j.version>...` vào project properties rồi hy vọng BOM import áp dụng là không đáng tin.

Bất kỳ override nào cũng có nguy cơ làm lệch tập dependency versions mà Spring Boot đã kiểm thử. Chỉ override khi có lý do như security fix và chạy đầy đủ tests.

## 11. Packaging WAR: hiểu provided đúng để tránh lỗi khi triển khai

### 11.1. Vì sao Spring Boot web starter kéo Tomcat?

`spring-boot-starter-web` (Boot 3.5) sử dụng Spring MVC/Servlet và thông thường kéo Tomcat embedded starter. Với **executable JAR**, Tomcat embedded là runtime của ứng dụng, giữ ở runtime/compile graph.

Với **WAR triển khai lên Tomcat ngoài**, container ngoài đã mang servlet runtime và các Tomcat classes. Vì vậy direct dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

nói container sẽ cung cấp dependency ấy khi deployment. Boot Maven Plugin khi repackaging WAR có cơ chế `WEB-INF/lib-provided` để artifact vẫn có thể chạy `java -jar`.

### 11.2. Ba trường hợp dễ nhầm

| Tình huống | Packaging | Tomcat scope | Runtime |
| --- | --- | --- | --- |
| Standalone Spring MVC service | `jar` | Thông thường đi qua web starter runtime | `java -jar app.jar` |
| WAR deploy external Tomcat | `war` | `provided` | External servlet container cung cấp Tomcat |
| Executable WAR | `war` + `repackage` | `provided`, được Boot tổ chức trong lib-provided | `java -jar app.war` |

Đừng đổi scope của toàn bộ `spring-boot-starter-web` sang `provided` chỉ để “giảm WAR”: controller/MVC libraries và nhiều runtime dependencies còn cần được đóng gói cho webapp. Thực hiện đúng ví dụ của Spring Boot: đánh dấu **servlet container starter** là provided.

### 11.3. Tương thích với Jakarta Servlet

Spring Boot 3.x chuyển sang `jakarta.servlet.*`. Một ứng dụng WAR chạy đúng với Tomcat 10.1 không có nghĩa deploy lên Tomcat 9 thành công; Tomcat 9 dùng `javax.servlet.*`. Nếu gặp `NoClassDefFoundError: jakarta/servlet/...` hoặc startup lỗi ở container cũ, hãy xác minh server version, Servlet API và cấu hình deployment, không chỉ Maven plugin version.

Nếu dự án dùng WebFlux thay vì Spring MVC, mô hình WAR truyền thống khác và không hỗ trợ theo cách Servlet-based Boot application này. Không chuyển mọi project Spring Boot sang WAR chỉ vì công ty có Tomcat server.

## 12. Vấn đề khi đóng gói và chạy

### 12.1. “no main manifest attribute” hoặc executable archive không chạy

**Nguyên nhân thường gặp:** Maven WAR/JAR Plugin tạo archive thường, nhưng Spring Boot `repackage` không chạy. Có thể bạn chỉ khai báo Boot plugin name mà thiếu execution vì không dùng starter parent.

Cách điều tra:
1. Xem `mvn clean package` log có `spring-boot-maven-plugin:...:repackage` không.
2. Kiểm tra `<executions><execution><goals><goal>repackage</goal>` trong effective POM.
3. Xem archive có Boot loader và thư mục `BOOT-INF` hoặc `WEB-INF/lib-provided` thích hợp không.
4. Xem manifest `Main-Class`/`Start-Class` thay vì tự chỉnh Maven JAR Plugin manifest ngẫu nhiên.
5. Đảm bảo `mainClass` chỉ đúng `DemoApplication`.

### 12.2. “Unable to find a single main class”

Nguyên nhân có thể:
- không có class chứa `public static void main(String[] args)`;
- có nhiều main classes và plugin không thể chọn;
- package/class name trong `mainClass` sai;
- Java compilation chưa tạo file class mong đợi.

Cấu hình tường minh `<mainClass>com.example.bootnoparent.DemoApplication</mainClass>` trong Boot Maven Plugin, rồi `mvn clean package`. Không dựa vào `<start-class>` riêng lẻ nếu không có parent cấu hình property mapping tương ứng.

### 12.3. Java release mismatch

Lỗi như `release version 17 not supported` hoặc `invalid target release: 17` thường đến từ JDK Maven/compiler quá cũ. Chạy `mvn -version` và kiểm tra toolchain. Chỉ đổi `<java.version>17</java.version>` trong POM khi không dùng Boot parent **không bảo đảm** Compiler Plugin đã được cấu hình đúng.

### 12.4. JUnit Jupiter tests không được phát hiện

Một project có `spring-boot-starter-test` nhưng Surefire version cũ có thể chạy 0 tests. Kiểm tra:
- tên class `HelloControllerTest`, `@Test` thuộc `org.junit.jupiter.api.Test`;
- Maven Surefire Plugin version 3.5.2;
- tests không bị `-DskipTests` hoặc `-Dmaven.test.skip=true`;
- report `target/surefire-reports`;
- BOM và starter versions đã resolve.

Đừng chỉ đọc `BUILD SUCCESS`; hãy xác minh `Tests run: 1` trong ví dụ này.

### 12.5. WAR không có web.xml

Spring MVC Boot dùng `SpringBootServletInitializer` và Servlet container initializer, không nhất thiết cần `WEB-INF/web.xml`. WAR Plugin 3.4.0 cho phép `failOnMissingWebXml=false`. Nếu một parent nội bộ buộc web.xml hoặc plugin quá cũ, hãy điều chỉnh WAR Plugin và xác nhận Java Servlet configuration thay vì tạo web.xml rỗng chỉ để né lỗi.

### 12.6. WAR chạy bằng java -jar nhưng deploy vào container khác thất bại

Các khả năng:
- servlet container không hỗ trợ Jakarta Servlet API phù hợp;
- `SpringBootServletInitializer` hoặc `configure(...)` chưa đúng;
- Tomcat `provided` chưa áp dụng;
- application cần tài nguyên/environment mà server ngoài không cung cấp;
- context path khác khi deploy (không phải `/hello` tại root);
- security constraints, JNDI, proxy, startup environment khác.

Phải tách **Maven build correctness**, **Spring context correctness** và **container deployment correctness**. MockMvc test chỉ xác nhận một phần.

### 12.7. POM dependency graph lệch version

Nếu import BOM version 3.5.16 nhưng khai báo một Spring starter 4.x thủ công, hoặc Boot Maven Plugin khác major, build có thể compile nhưng runtime gặp `NoSuchMethodError`/`ClassNotFoundException`. Kiểm tra `mvn dependency:tree`, effective POM, các entries quản lý phiên bản và các exclusions ở parent. Đừng thêm version riêng cho từng starter một cách tùy tiện.

## 13. Cách dùng help:effective-pom, describe và dependency:tree để QA

Với project đã cấu hình:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16" -Dgoal=repackage -Ddetail=true
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
```

Những điều cần đối chiếu:
- BOM import `spring-boot-dependencies:3.5.16` có mặt và starter dependencies được resolve đúng series.
- Compiler Plugin có version `3.13.0`, Java release `17`, `parameters=true`.
- Surefire Plugin có version `3.5.2`, report không có 0 tests do selector.
- WAR Plugin có version `3.4.0` và `packaging=war`.
- Spring Boot Maven Plugin có version `3.5.16` và execution `repackage` gắn đúng lifecycle.
- Resource filtering không thay Spring runtime placeholder `${PORT:8080}`.
- Không có hai executions repackage vô ý hoặc trùng plugin configurations gây side effects.

`help:describe` mô tả goal, **không thực thi goal được mô tả**. `dependency:tree` hiển thị Maven dependency graph, **không hiển thị đầy đủ Maven plugin graph**. `jar tf` và `java -jar` mới kiểm tra artifact runtime thực tế.

## 14. So sánh ba cách tổ chức POM

### Cách A — dùng Spring Boot starter parent

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
</parent>
```

**Ưu điểm:** ít cấu hình, được chuẩn bị plugin versions/defaults, repackage và resource filtering. **Nhược điểm:** không thể đồng thời có một parent trực tiếp khác; có thể xung đột policy nội bộ.

### Cách B — không dùng parent, import BOM

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

**Ưu điểm:** tự do chọn corporate parent, vẫn dùng dependency versions đã quản lý. **Nhược điểm:** phải quản lý plugin versions, compiler settings, tests, repackage và filtering. **Đây là cách mà bài thực hành áp dụng.**

### Cách C — corporate parent + Spring Boot BOM

Sử dụng `<parent>` của doanh nghiệp, import Boot BOM, và đưa plugin versions/executions vào corporate parent (qua pluginManagement/appropriate plugin declarations) hoặc từng module. Cách này phù hợp monorepo hoặc nhiều service cần chính sách build nhất quán. Tuy nhiên nên phân định rõ:
- ai quản lý version Spring Boot BOM;
- ai quản lý Spring Boot Maven Plugin version;
- ai bind repackage execution;
- ai quy định Java release, Surefire/Failsafe/WAR;
- cách tránh duplicate executions, override filtering, và sự khác biệt giữa các modules.

Đừng đưa các plugin vào mọi module nếu một số module là library JAR không cần Boot repackage. Corporate parent có thể quản lý defaults, nhưng các modules kích hoạt plugin theo vai trò thực tế.

## 15. Các lỗi nhầm lẫn thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “Import BOM là thừa kế toàn bộ Spring Boot parent.” | Sai: BOM chỉ quản lý dependencies, không nhập plugin management/executions. |
| “Chỉ cần khai báo spring-boot-maven-plugin là mvn package tự repackage.” | Chỉ đúng khi execution đã được parent/cấu hình khác cung cấp; không mặc nhiên đúng khi không có parent. |
| “Đổi packaging=war là WAR đã chạy được bằng java -jar.” | WAR thường không phải executable Boot WAR nếu chưa repackage. |
| “Maven WAR Plugin thay cho spring-boot-maven-plugin.” | WAR Plugin tạo WAR, Boot Plugin tổ chức lại để executable. |
| “provided nghĩa là Tomcat không bao giờ có trong executable WAR.” | Boot repackage có thể đặt provided dependencies ở WEB-INF/lib-provided để chạy độc lập. |
| “Không dùng parent nhưng java.version=17 sẽ tự cấu hình compiler.” | Phải khai báo Compiler Plugin/release hoặc có cấu hình hiệu lực từ parent khác. |
| “BOM import quản lý luôn Surefire, WAR Plugin versions.” | Plugin versions cần quản lý riêng. |
| “JUnit starter-test có nghĩa JUnit Jupiter chắc chắn được chạy.” | Surefire version và test discovery phải đúng; cần kiểm tra reports. |
| “Boot 3.5 WAR chạy được trên Tomcat 9.” | Servlet javax vs jakarta không tương thích trực tiếp. |
| “Maven filtering trên application.properties luôn an toàn.” | Default ${...} có thể xung đột runtime Spring placeholders. |
| “MockMvc test pass nghĩa là deploy Tomcat ngoài pass.” | Chưa kiểm tra WAR/container compatibility và context path. |
| “Chỉ cần inspect pom.xml, không cần chạy jar/war.” | Effective POM/actual archive/runtime smoke test mới xác nhận đúng. |
| “Maven pluginManagement lúc nào cũng kích hoạt goal.” | Nó chủ yếu là vùng quản lý cấu hình/defaults; việc thực thi cần binding/activation đúng. |
| “mainClass tự tìm nên không cần kiểm tra manifest.” | Khi nhiều main classes hoặc archive bị thay đổi, vẫn cần cấu hình/kiểm chứng. |

## 16. Bài tập tự đánh giá

**Bài tập 1 — BOM vs plugin:** Một POM import Spring Boot BOM 3.5.16 nhưng không khai báo Boot Maven Plugin. `mvn package` có chắc tạo executable Boot JAR/WAR không? **Không**, BOM không bind goal repackage.

**Bài tập 2 — execution:** Cần hai dòng lõi nào trong plugin để tạo executable archive khi không có parent? **Explicit plugin version** và **`<executions><execution><goals><goal>repackage</goal>`**.

**Bài tập 3 — Java:** POM chỉ đặt `<java.version>17</java.version>` khi không dùng Boot parent. Java compiler chắc target 17 không? **Không chắc**; đặt `maven.compiler.release=17` và plugin config rõ.

**Bài tập 4 — WAR:** Vì sao cần `SpringBootServletInitializer` cho WAR traditional deployment? Vì servlet container bên ngoài cần entry point để khởi tạo Spring application context.

**Bài tập 5 — Tomcat:** Với Boot 3.5, `spring-boot-starter-tomcat` nên đặt scope gì khi deploy WAR vào Tomcat ngoài? **provided**; Boot executable WAR có thể bố trí provided jars ở `WEB-INF/lib-provided`.

**Bài tập 6 — build:** Sau `mvn clean package` tạo `target/boot-no-parent-lab-1.0.0.war` nhưng `java -jar` báo thiếu launcher. Kiểm tra gì? **`spring-boot:repackage` execution và archive thật**.

**Bài tập 7 — test:** `HelloControllerTest` dùng JUnit Jupiter nhưng build in “Tests run: 0”. Kiểm tra gì? **Surefire version/provider, tên test, skip flags và reports**.

**Bài tập 8 — runtime:** `application.properties` có `server.port=${PORT:8080}`. Nếu Maven filtering bị bật sai, rủi ro gì? Maven có thể xử lý token runtime; cần tắt filtering hoặc dùng `@`-only.

**Bài tập 9 — BOM override:** Chỉ đặt project property `<slf4j.version>...` có bảo đảm override phiên bản trong imported BOM không? **Không**; cần `dependencyManagement` override tường minh khi thực sự cần.

**Bài tập 10 — chuyển JAR:** Những thay đổi cần thiết khi không deploy external container? Đổi `packaging` sang `jar`, bỏ direct Tomcat provided, dùng JAR plugin/lifecycle, giữ Boot repackage; `SpringBootServletInitializer` không còn bắt buộc.

**Bài tập 11 — verify:** Vì sao `mvn clean verify` cho nhiều bằng chứng hơn chỉ `mvn spring-boot:run`? Vì nó đi qua compile/tests/package/repackage; run goal chủ yếu khởi động ứng dụng phát triển, không tự xác minh artifact phát hành.

**Bài tập 12 — build policy:** Một corporate parent đã bind repackage, module lại khai báo execution khác id cho cùng goal. Có nguy cơ gì? **Double execution**, archive bị repackage lặp hoặc artifact thay đổi khác dự kiến; phải kiểm tra effective POM/lifecycle log.

## 17. Checklist áp dụng vào dự án thực tế

- [ ] Đã quyết định không dùng `spring-boot-starter-parent` vì có yêu cầu rõ.
- [ ] Đã import đúng `spring-boot-dependencies` BOM với `type=pom`, `scope=import`.
- [ ] Đã dùng cùng một Spring Boot version cho BOM và Boot Maven Plugin.
- [ ] Đã quản lý versions của Compiler, Surefire, WAR/JAR và các plugins cần thiết.
- [ ] Đã cấu hình Java release, UTF-8 và `-parameters` theo yêu cầu framework.
- [ ] Đã khai báo `repackage` execution cho project executable, không chỉ plugin name.
- [ ] Đã kiểm tra không có repackage execution trùng từ corporate parent.
- [ ] Đã xác định `mainClass` nếu project có nhiều entry points.
- [ ] Khi dùng WAR, đã khai báo `packaging=war` và WAR Plugin version phù hợp.
- [ ] Khi deploy WAR vào external Tomcat, đã triển khai `SpringBootServletInitializer`.
- [ ] Đã đặt Tomcat starter scope `provided` đúng và chọn servlet container tương thích Jakarta API.
- [ ] Đã xác nhận Spring runtime placeholders không bị Maven filtering thay nhầm.
- [ ] Đã chạy `mvn clean verify`, kiểm tra test counts và reports.
- [ ] Đã mở `jar tf` và kiểm tra `WEB-INF`/`BOOT-INF` tương ứng.
- [ ] Đã chạy `java -jar` và thử endpoint thật ở môi trường phù hợp.
- [ ] Nếu deploy WAR ngoài, đã test trên servlet container/runtime version của sản phẩm.
- [ ] Đã kiểm tra Maven effective POM khi kế thừa corporate parent và nâng Spring Boot.
- [ ] CI nhận diện đúng artifact executable, tránh deploy nhầm `.original`/thin archive.
- [ ] Đã có kế hoạch cập nhật Spring Boot lên dòng còn được hỗ trợ, nhất là khi dùng 3.5.x sau khi hết OSS support.

**Kết luận:** Không kế thừa Spring Boot parent không làm mất khả năng xây dựng Spring Boot application. Bạn chỉ phải tách rõ trách nhiệm: **Spring Boot BOM** quản lý **dependency versions**, **Maven plugin configuration** quản lý **compile/test/package/repackage**, và **WAR deployment configuration** quản lý **servlet runtime**. Đối với executable JAR/WAR, điều dễ bỏ sót nhất là **ghim Spring Boot Maven Plugin và tự bind `repackage`**, sau đó kiểm tra artifact thực bằng `java -jar` và test HTTP. Với WAR triển khai ngoài, hãy quan tâm `SpringBootServletInitializer`, Tomcat `provided` và Jakarta Servlet compatibility — những việc BOM không thể làm thay.

### Tài liệu chính thức và nguồn đối chiếu

- [Spring Boot 3.5 — Using the Maven Plugin, including without the Parent POM](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html)
- [Spring Boot 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Traditional Deployment / Create a Deployable War File](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot Maven Plugin — Maven Goals](https://docs.spring.io/spring-boot/3.5/maven-plugin/goals.html)
- [Apache Maven WAR Plugin 3.4.0 — war:war goal](https://maven.apache.org/components/plugins-archives/maven-war-plugin-3.4.0/war-mojo.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Spring Boot 3.5.16 — Release announcement](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
