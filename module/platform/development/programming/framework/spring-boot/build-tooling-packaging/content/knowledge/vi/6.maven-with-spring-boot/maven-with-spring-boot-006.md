# Gắn `repackage` vào `package` khi không dùng Spring Boot starter parent (Maven)

## 1. Mục tiêu bài học

Đề bài: **Gắn `repackage` vào `package` khi không dùng starter parent.**

Trong dự án Spring Boot dùng Maven, bạn có thể không kế thừa `org.springframework.boot:spring-boot-starter-parent` do đã dùng parent POM riêng của tổ chức hoặc muốn quản lý phiên bản plugin độc lập. Dự án vẫn có thể dùng Spring Boot starter và Spring Boot BOM. Tuy nhiên, chỉ import BOM hay khai báo starter **không khiến Maven tự chạy goal `spring-boot:repackage`**.

Mục tiêu sau cùng là chạy một lệnh duy nhất:

~~~bash
mvn clean package
~~~

và tạo được **executable Spring Boot JAR** chứa mã, runtime dependencies và Spring Boot launcher, để khởi động bằng:

~~~bash
java -jar target/boot-no-parent-1.0.0.jar
~~~

Sau bài này, bạn biết cách:

- Tách vai trò của starter, BOM, Maven parent, Maven build plugin và goal execution.
- Gắn `spring-boot-maven-plugin:repackage` vào phase `package` trong `pom.xml` **không dùng starter parent**.
- Giải thích thứ tự `jar:jar → spring-boot:repackage` và yêu cầu có source JAR/WAR.
- Chạy và kiểm chứng một dự án Spring Boot có POM hoàn chỉnh, Java 17 và unit test.
- Kiểm tra effective POM, log Maven, file `.jar`, manifest, `BOOT-INF` và kết quả `java -jar`.
- Vận dụng trong corporate parent, multi-module, classifier, build CI và xử lý lỗi.

**Phiên bản ví dụ:** Spring Boot **4.1.2**, Java **17**, Maven **3.6.3 trở lên** theo tài liệu yêu cầu hệ thống của Spring Boot 4.1.2. Tên starter sử dụng là `spring-boot-starter-webmvc` theo Spring Boot 4. Ví dụ không được mặc định dùng Java hoặc Boot mới hơn nếu chưa kiểm tra yêu cầu tương thích.

## 2. Phân biệt các vai trò cốt lõi

| Thành phần | Đặt ở đâu? | Vai trò | Có tự gắn repackage không? |
| --- | --- | --- | --- |
| `spring-boot-starter-webmvc` | `<dependencies>` | Chọn tập dependency để viết Spring MVC | Không |
| `spring-boot-dependencies` BOM | `<dependencyManagement>` với `<type>pom</type>` và `<scope>import</scope>` | Quản lý phiên bản dependency | Không |
| `spring-boot-maven-plugin` | `<build><plugins>` | Cung cấp goal như `repackage`, `run`, `build-image` | Chưa đủ nếu không có goal execution |
| `<execution>` của Maven plugin | `<executions>` trong khai báo plugin | Gắn một hoặc nhiều goal vào phase build | **Có**, nếu khai báo đúng |
| `spring-boot-starter-parent` | `<parent>` | Kế thừa dependency management, plugin management và một execution `repackage` đã cấu hình | Có cấu hình execution sẵn, khi plugin được kích hoạt |

**Điểm phải nhớ:** BOM `spring-boot-dependencies` cung cấp dependency version, còn `spring-boot-starter-parent` bổ sung cấu hình Maven/plugin. **Import BOM không mang theo plugin management và execution của starter parent.**

Một dự án có thể import BOM như sau:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau khi import, Maven có thể resolve dependency đã được BOM quản lý, ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc</artifactId>
</dependency>
~~~

mà không cần viết `<version>` tại dependency. Tuy nhiên, project **vẫn phải** khai báo và cấu hình build plugin để tạo executable JAR.

## 3. Điều gì xảy ra nếu thiếu `repackage`?

Đối với `<packaging>jar</packaging>`, Maven có các goal mặc định thuộc lifecycle; tại phase `package`, `maven-jar-plugin:jar` tạo **JAR thông thường**. Nó thường chứa class/resources theo cấu trúc package Java, chẳng hạn:

~~~text
target/boot-no-parent-1.0.0.jar
└── com/example/demo/DemoApplication.class
~~~

JAR thường **không nhất thiết** có đầy đủ runtime dependencies, Spring Boot loader hay manifest của executable Spring Boot JAR. Nếu bạn gọi:

~~~bash
mvn clean package
java -jar target/boot-no-parent-1.0.0.jar
~~~

với cấu hình chưa bind repackage, lệnh build có thể vẫn báo `BUILD SUCCESS`, nhưng `java -jar` không chạy theo kỳ vọng, ví dụ vì thiếu main manifest hoặc runtime classpath.

Ngược lại, khi `repackage` chạy đúng, archive Spring Boot có cấu trúc thường gặp:

~~~text
target/boot-no-parent-1.0.0.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/classes/com/example/demo/DemoApplication.class
├── BOOT-INF/lib/...
└── org/springframework/boot/loader/...
~~~

**`jar:jar` tạo source archive; `spring-boot:repackage` đóng gói lại source archive.** Repackage không biên dịch Java và không thay thế goal tạo JAR/WAR.

## 4. Maven lifecycle và thứ tự thực thi

Các phase tiêu biểu khi build dự án `jar`:

| Phase Maven | Goal hoặc hoạt động | Đầu ra |
| --- | --- | --- |
| `validate` | Kiểm tra POM và goal được bind nếu có | Cấu hình hợp lệ |
| `process-resources` | `resources:resources` | `target/classes` có resources |
| `compile` | `compiler:compile` | File `.class` |
| `test-compile` | `compiler:testCompile` | Test classes |
| `test` | `surefire:test` | Test reports |
| `package` | `jar:jar` | JAR thông thường |
| `package` | **`spring-boot:repackage`** khi được bind | Executable Spring Boot JAR |
| `verify` | Các kiểm tra khác được cấu hình | Kết quả kiểm chứng |

Maven thực thi các phase trước phase được yêu cầu. Do đó gọi `mvn package` sẽ chạy đến `package`, bao gồm test (trừ khi bị skip theo cấu hình). Gọi `mvn verify` cũng đi qua `package` trước khi tiến hành các goal verification đã cấu hình.

Đối với packaging `jar`, binding mặc định như `jar:jar` chạy trước goal bổ sung vào cùng phase qua POM. Nếu dự án có các execution tùy chỉnh của `maven-jar-plugin` và Spring Boot plugin trong `package`, tài liệu Spring Boot nhấn mạnh **khai báo Jar Plugin trước Boot Plugin** để source JAR đã sẵn sàng trước `repackage`.

Phân biệt:

~~~text
mvn clean package
    -> resources -> compiler -> test -> jar:jar -> boot:repackage

mvn spring-boot:repackage
    -> gọi riêng goal; không bảo đảm source JAR đã được tạo

mvn package spring-boot:repackage
    -> package rồi gọi goal tường minh; thích hợp khi CHƯA bind goal
    -> tránh gọi thừa với POM đã bind repackage
~~~

**Goal `repackage` có default phase `package`**, nhưng metadata này **không đồng nghĩa** chỉ cần liệt kê `spring-boot-maven-plugin` trong `<plugins>` là Maven tự chạy goal. Cần một `<execution>` có `<goals><goal>repackage</goal></goals>`, hoặc một execution kế thừa sẵn từ parent.

## 5. Đoạn cấu hình tối thiểu cần thêm vào POM

Trong một module ứng dụng có packaging `jar` hoặc `war`, thêm plugin sau vào `<build><plugins>`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <executions>
        <execution>
            <id>repackage</id>
            <phase>package</phase>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Các trường có ý nghĩa khác nhau:

- `groupId` và `artifactId` xác định **Spring Boot Maven Plugin**, không phải starter dependency.
- `version` chọn phiên bản plugin. Khi **chỉ** import BOM, phải cấp version plugin bằng cấu hình trực tiếp hoặc qua plugin management khác; BOM không cấp version plugin.
- `executions` cho Maven biết đây là goal cần tham gia build lifecycle.
- `id=repackage` đặt tên cho execution, hữu ích khi kiểm tra log và khi merge cấu hình inherited.
- `phase=package` cho biết chính xác thời điểm chạy. Metadata goal cũng mặc định là phase này, nên ghi phase là **tường minh, hợp lệ**, không bắt buộc trong ví dụ cơ bản.
- `goals/goal=repackage` là yêu cầu Maven chạy goal.
  
**Sai lầm phổ biến:** chỉ viết:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
</plugin>
~~~

trong project không có execution inherited, rồi kỳ vọng `mvn package` tự repackage. Khai báo plugin đơn lẻ vẫn cho phép gọi goal một cách tường minh, nhưng không thêm binding mong muốn vào `package`.

### `<pluginManagement>` có đủ không?

Không. `<build><pluginManagement>` thường **định nghĩa phiên bản và cấu hình mặc định**, nhưng không tự biến một plugin chưa kích hoạt thành plugin chạy tại module hiện tại. Nếu corporate parent đặt Boot plugin trong `pluginManagement`, module application vẫn phải kích hoạt plugin qua `<build><plugins>` và bảo đảm đã có execution `repackage`.

## 6. Ví dụ POM đầy đủ **không có starter parent**

Dự án Maven độc lập sử dụng Java 17 và Spring Boot 4.1.2:

~~~text
boot-no-parent/
├── pom.xml
├── src/
│   ├── main/
│   │   └── java/com/example/demo/DemoApplication.java
│   └── test/
│       └── java/com/example/demo/DemoApplicationTest.java
└── target/      # Maven tạo sau khi build
~~~

**`pom.xml`** hoàn chỉnh:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>boot-no-parent</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>4.1.2</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>4.1.2</version>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <phase>package</phase>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Lý do cấu hình trên có thể build độc lập:

1. Có `<packaging>jar</packaging>`, nghĩa là Maven tạo source JAR ở `package`.
2. BOM nhập phiên bản phù hợp của Spring Boot starters; các starter không phải tự ghi version.
3. `maven.compiler.release` chọn release Java 17; `maven-compiler-plugin` được pin version để tránh mặc định cũ.
4. `maven-surefire-plugin` phiên bản 3.6.1 có khả năng chạy JUnit Platform/JUnit Jupiter, kể cả dòng JUnit 6 mà Spring Boot 4 có thể sử dụng.
5. `maven-jar-plugin` được khai báo trước Spring Boot plugin; goal `jar:jar` có output để Boot xử lý.
6. `spring-boot-maven-plugin` có version và **execution gắn vào phase package**. Không cần kế thừa starter parent để có binding đó.
7. Không có `<parent>` trong POM hoàn chỉnh này. POM **không chỉ là snippet**; có thể dùng cho project mới theo cấu trúc ví dụ.

Các plugin mặc định khác như Maven Clean Plugin có thể do phiên bản Maven/parent khác quy định. Ví dụ pin những plugin trực tiếp ảnh hưởng compile/test/package, còn dự án doanh nghiệp nên pin toàn bộ plugin theo chính sách tổ chức.

## 7. Java 17 và unit test có thể chạy

**Tệp `src/main/java/com/example/demo/DemoApplication.java`**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Boot without parent";
    }
}
~~~

**Tệp `src/test/java/com/example/demo/DemoApplicationTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DemoApplicationTest {
    @Test
    void helloReturnsExpectedText() {
        DemoApplication app = new DemoApplication();
        assertEquals("Hello from Boot without parent", app.hello());
    }
}
~~~

Đây là **unit test** cho method trả về chuỗi, không tạo HTTP server. Vì vậy test này chỉ chứng minh logic của method, chưa chứng minh executable JAR đã được Boot loader xử lý đúng. Giai đoạn sau sẽ kiểm tra bằng `java -jar` và một HTTP request.

Khi chạy `mvn clean package`, Maven chạy test nếu bạn không bật cờ skip. Tên `DemoApplicationTest` nằm trong quy tắc nhận diện test tiêu chuẩn của Surefire. Trong ví dụ, `spring-boot-starter-test` mang theo test dependency được BOM quản lý.

## 8. Chạy build và đọc log đúng cách

Trong thư mục chứa `pom.xml`, với Maven và JDK phù hợp:

~~~bash
mvn -version
java -version
mvn clean package
~~~

Một log build hợp lệ sẽ có các goal với thứ tự về logic giống sau (đây **không phải** bản stdout cố định):

~~~text
maven-resources-plugin:3.3.1:resources
maven-compiler-plugin:3.14.1:compile
maven-compiler-plugin:3.14.1:testCompile
maven-surefire-plugin:3.6.1:test
maven-jar-plugin:3.4.2:jar
spring-boot-maven-plugin:4.1.2:repackage (repackage)
BUILD SUCCESS
~~~

Maven còn có các goal resource/test resource và thông báo về dependency, tải artifact, số test, thời gian build. Những thông báo này có thể khác do môi trường, Maven version và cache. Điều quan trọng cho đề bài là **Boot goal `repackage` được gọi tự động trong `package` sau `jar:jar`**, không cần lệnh thứ hai.

File sau build mặc định:

~~~text
target/
├── classes/com/example/demo/DemoApplication.class
├── test-classes/com/example/demo/DemoApplicationTest.class
├── surefire-reports/...
├── boot-no-parent-1.0.0.jar
└── boot-no-parent-1.0.0.jar.original
~~~

- `boot-no-parent-1.0.0.jar` là **JAR executable** đã được repackaged theo mặc định.
- `boot-no-parent-1.0.0.jar.original` là **JAR gốc** trước khi repackage; không nên chọn file này cho deployment.
- Maven version, finalName, classifier hoặc build plugin khác có thể làm file name thay đổi. Khi kiểm chứng, đối chiếu `artifactId`/`version`/`finalName` và log của lần build hiện tại.
- Nếu `repackage` chưa chạy, `target/boot-no-parent-1.0.0.jar` có thể vẫn tồn tại dưới dạng plain JAR: **sự tồn tại của tên file không đủ chứng minh thành công**.

Nếu project có Maven Wrapper trong repository, có thể chạy `./mvnw clean package` hoặc `mvnw.cmd clean package` trên Windows. Ví dụ không tự tạo wrapper.

## 9. Kiểm tra executable artifact một cách có bằng chứng

### 9.1. Xem nội dung JAR

~~~bash
jar tf target/boot-no-parent-1.0.0.jar
~~~

Kết quả cần xuất hiện các khu vực:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/demo/DemoApplication.class
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

`BOOT-INF/classes` chứa class/resources ứng dụng; `BOOT-INF/lib` chứa nested JAR runtime; `org/springframework/boot/loader` chứa Boot launcher. Đây là dấu hiệu đặc trưng của một Spring Boot executable JAR theo layout JAR tiêu chuẩn.

### 9.2. Kiểm tra manifest

Đọc `META-INF/MANIFEST.MF` từ archive bằng công cụ hỗ trợ (chẳng hạn `unzip -p target/boot-no-parent-1.0.0.jar META-INF/MANIFEST.MF` trên máy có `unzip`). Manifest điển hình:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.DemoApplication
~~~

`Main-Class` trỏ tới Boot launcher, còn `Start-Class` trỏ tới class application có `main`. Boot plugin quản lý các mục này khi repackage; nếu cần chỉ rõ main class, cấu hình `mainClass` ở Boot Maven Plugin.

### 9.3. Chạy runtime và thử HTTP

Ở terminal thứ nhất:

~~~bash
java -jar target/boot-no-parent-1.0.0.jar
~~~

Chờ server khởi động, mở terminal thứ hai:

~~~bash
curl -fsS http://localhost:8080/hello
~~~

**HTTP response body chính xác của endpoint**:

~~~text
Hello from Boot without parent
~~~

Controller trả chuỗi không có newline. Công cụ terminal hoặc prompt có thể hiển thị thêm nội dung riêng; log khởi động Spring Boot thay đổi theo môi trường và không được coi là stdout cố định.

Nếu cổng 8080 đã được dùng, chạy:

~~~bash
java -jar target/boot-no-parent-1.0.0.jar --server.port=8081
~~~

rồi thử `curl -fsS http://localhost:8081/hello`. Trên Windows PowerShell có thể dùng `curl.exe` để tránh nhầm alias. Bài test HTTP ở đây là **smoke test**, khác với unit test ở mục 7.

## 10. Kiểm tra binding thông qua Effective POM

POM đang nhìn thấy có thể khác model Maven dùng sau khi kế thừa parent, xử lý properties, profiles và plugin management. Để xác nhận:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

Mở `effective-pom.xml` trong workspace dự án và tìm:

- `spring-boot-maven-plugin` được khai báo trong `build/plugins` của module ứng dụng;
- phiên bản Boot plugin được resolve là `4.1.2` trong ví dụ;
- execution ID `repackage` có goal `repackage`, phase `package`;
- không có thêm execution khác vô tình chạy `repackage` lần hai;
- cấu hình `skip`, `classifier`, `mainClass` nếu có.

Nếu dùng corporate parent, plugin version có thể được quản lý trong `build/pluginManagement`; bản **effective POM** cho biết cấu hình sau khi merge. Khi thấy build xanh nhưng log chỉ có `jar:jar`, effective POM là nơi nên kiểm tra trước tiên.

Có thể kiểm tra graph dependency riêng:

~~~bash
mvn dependency:tree
~~~

Nếu dependency graph đúng mà chưa thấy executable archive, vấn đề rất có thể nằm ở **plugin/lifecycle binding**, không phải BOM.

## 11. Áp dụng trong công ty có corporate parent

Ví dụ tổ chức yêu cầu dùng parent POM chứa repository, policy và plugin config. Maven chỉ cho phép một parent trực tiếp; **không thể khai báo đồng thời corporate parent và starter parent trong hai `<parent>`**.

Cách triển khai theo thứ tự:

1. Giữ parent POM của tổ chức.
2. Import `spring-boot-dependencies` vào `dependencyManagement` của module hoặc parent thích hợp.
3. Khai báo starter web/test ở `dependencies` theo nhu cầu.
4. Đảm bảo `spring-boot-maven-plugin` có version được quản lý bởi corporate parent hoặc khai báo tại module.
5. Đặt plugin vào `build/plugins` ở module ứng dụng, thêm execution `repackage` tới `package` **nếu chưa có execution inherited tương đương**.
6. Chạy `mvn help:effective-pom` để kiểm tra kết quả merge và lifecycle goals.
7. Chạy `mvn clean package`, kiểm tra JAR layout và `java -jar`.

**Điểm dễ sai khi chuyển từ starter parent:** parent Boot còn từng cấp mặc định Java release, encoding, plugin management và resource filtering. Khi thay parent, không chỉ cần repackage; phải xác minh compiler/test/resource plugins còn phù hợp. Đừng tin rằng import BOM là cách giữ mọi build behavior như trước.

Nếu corporate parent đã cấu hình một execution ID `repackage`, child POM có thể dùng **cùng ID** để tùy biến theo quy tắc inheritance của Maven. Nếu tự thêm ID khác và cả hai executions cùng chạy, bạn có nguy cơ xử lý archive hai lần. Cần dựa vào effective POM và log để kết luận.

## 12. Dự án multi-module: gắn đúng module

Giả sử:

~~~text
my-platform/              packaging=pom
├── shared-utils/         packaging=jar  (library)
├── business-domain/      packaging=jar  (library)
└── web-service/          packaging=jar  (Spring Boot application)
~~~

Quy tắc áp dụng:

- **Root aggregator** packaging `pom` không tạo source JAR ứng dụng bằng binding `jar:jar`; không bind repackage bừa bãi tại root.
- **Library modules** nên giữ plain JAR để các module khác có thể dùng class theo layout thông thường.
- **Application module** có `main()` và triển khai bằng `java -jar` mới cần executable archive và goal `repackage`.
- **Corporate parent/pluginManagement** có thể quản lý phiên bản plugin tập trung; chỉ activate goal tại module cần chạy.
- Khi chạy Maven reactor từ root, xem module nào tạo Boot executable; không đánh đồng tất cả output `.jar` thành application.

Điểm thực tế: trong Spring Boot executable JAR, class ứng dụng nằm trong `BOOT-INF/classes`, không phải layout thư viện Maven JAR thông thường. Nếu thay artifact chính của thư viện bằng Boot executable JAR, downstream library consumers có thể không tìm được class.

## 13. Giữ JAR thường và tạo thêm executable JAR bằng classifier

Mặc định, `spring-boot:repackage` **thay thế main artifact** bằng executable JAR và giữ bản gốc dưới dạng file `.jar.original`.

Nếu thực sự cần cả plain JAR để dùng như library **và** executable JAR để deploy, có thể đặt classifier cho bản executable. **Thay thế** phần khai báo Boot plugin ở mục 6 bằng:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>4.1.2</version>
    <executions>
        <execution>
            <id>repackage</id>
            <phase>package</phase>
            <goals>
                <goal>repackage</goal>
            </goals>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Khi không có source artifact nào đã mang classifier `exec`, output thường là:

~~~text
target/boot-no-parent-1.0.0.jar        # JAR thường
target/boot-no-parent-1.0.0-exec.jar   # Executable Spring Boot JAR
~~~

Lúc đó lệnh chạy ứng dụng là:

~~~bash
mvn clean package
java -jar target/boot-no-parent-1.0.0-exec.jar
~~~

**Lưu ý kỹ thuật:** nếu plugin khác đã tạo JAR mang classifier `exec`, Boot plugin có thể chọn chính artifact cùng classifier làm **source để repackage**. Hãy kiểm tra thứ tự và đầu vào khi tạo nhiều archive trong cùng phase. Cấu hình `attach` (mặc định `true`) quyết định cách artifact đã repackage được đưa vào install/deploy; với classifier, artifact executable có thể được attach bên cạnh JAR thường.

Thường tốt hơn nên tách module library và module ứng dụng khi hai artifact phục vụ hai mục đích khác nhau. Dù chọn classifier, mục tiêu của bài vẫn là **bind repackage vào package**.

## 14. Các biến thể và ranh giới cần lưu ý

### 14.1. Đặt main class thủ công

Nếu có nhiều class `main()` hoặc plugin không dò được entry point, thêm vào cấu hình Spring Boot plugin:

~~~xml
<configuration>
    <mainClass>com.example.demo.DemoApplication</mainClass>
</configuration>
~~~

Đây là đoạn cấu hình **bên trong plugin**, không phải POM độc lập. Không dùng property của starter parent rồi mặc định nó vẫn hoạt động y hệt khi đã loại parent; cấu hình `mainClass` trực tiếp trong Boot plugin rõ ràng hơn.

### 14.2. `layout=NONE` không tạo archive chạy được theo cách thông thường

Goal `repackage` hỗ trợ layout `JAR`, `WAR`, `ZIP`/`DIR` và `NONE`. `NONE` có thể gói dependencies nhưng không thêm bootstrap launcher, vì vậy không đáp ứng bài toán tạo Spring Boot JAR chạy bằng `java -jar`. Không dùng `NONE` nếu mục tiêu là executable JAR.

### 14.3. WAR không có cấu trúc giống JAR

Nếu project dùng `<packaging>war</packaging>`, phải cấu hình WAR Plugin/servlet runtime tương ứng. Executable WAR sử dụng layout `WEB-INF/classes`, `WEB-INF/lib` và có thể có `WEB-INF/lib-provided`. Các điều kiện kiểm tra `BOOT-INF` của JAR không áp dụng nguyên xi cho WAR.

### 14.4. `skip` và dependency excludes

Nếu `repackage` có `skip=true` (từ POM, profile hoặc command line), build có thể thành công mà bỏ qua executable packaging. Khi exclude dependencies của Boot plugin, phải xác nhận không loại runtime library cần thiết. Không kết luận lỗi classpath chỉ từ kết quả compile thành công.

### 14.5. Không dùng `mvn package spring-boot:repackage` khi đã bind

Tài liệu Boot có ví dụ `mvn package spring-boot:repackage` để chạy goal trực tiếp sau khi Maven đã tạo source archive. **Với POM đang được học, execution đã bind repackage vào package**, nên lệnh chuẩn là `mvn package` hoặc `mvn clean package`. Gọi thêm goal trực tiếp sẽ không giúp đảm bảo chất lượng và có thể gây thao tác lặp.

### 14.6. Đúng version, đúng Java và đúng scope

Giữ BOM, starter version được BOM quản lý và Boot Maven Plugin cùng dòng phù hợp. Spring Boot 4.1.2 cần Java 17+, Maven 3.6.3+. Java chạy Maven và Java dùng compile có thể khác nếu cấu hình toolchains; hãy đọc `mvn -version` và compiler configuration để biết thực tế. Executable archive chạy ở production cần runtime Java tương thích với Boot, class và dependency.

## 15. Các lỗi phổ biến và cách truy nguyên

| Biểu hiện | Nguyên nhân thường gặp | Kiểm tra/khắc phục |
| --- | --- | --- |
| `mvn package` thành công nhưng chỉ có plain JAR | Chưa bind `repackage`, plugin chỉ ở `pluginManagement` | Xem effective POM; đặt plugin vào `build/plugins` và thêm execution |
| Maven báo thiếu phiên bản Boot Maven Plugin | Import BOM không quản lý plugin version | Chỉ định `<version>4.1.2</version>` hoặc lấy version từ corporate pluginManagement |
| Log không có `spring-boot:repackage` | Execution thiếu goal, profile tắt, module sai hoặc skip | Kiểm tra `<goals>`, `<phase>` và profile thực tế |
| `repackage` chạy trước `jar:jar` | Đặt sai execution/order khi custom packaging | Tạo archive đầu vào trước; khai báo Jar Plugin trước Boot Plugin |
| Chạy `mvn spring-boot:repackage` độc lập thất bại | Goal chưa có JAR/WAR đầu vào | Bind goal rồi chạy `mvn clean package` |
| `Unable to find main class` | Không có main phù hợp, có nhiều main hoặc chưa compile | Xác minh Java entry point, `target/classes` và `mainClass` |
| `no main manifest attribute` | Đang chạy JAR thường, `.jar.original` hoặc không repackage | Kiểm tra `jar tf`, manifest và tên file được chạy |
| `ClassNotFoundException` khi chạy | Thiếu runtime dependency hoặc chọn sai plain JAR | Kiểm tra `BOOT-INF/lib`, scopes, exclusions và archive |
| `BOOT-INF` thiếu dù build xanh | Goal bị skip, layout khác, hoặc output không phải archive vừa tạo | Chạy `mvn clean package`, kiểm tra log/repackage configuration |
| `repackage` chạy hai lần | Corporate parent đã có execution, child thêm execution khác ID | Kiểm tra effective POM và merge execution |
| Multi-module root báo không có source artifact | Repackage bị bind vào packaging `pom` | Chỉ bind tại module application `jar`/`war` |
| Module khác không import được class trong Boot JAR | Đã dùng executable JAR như library dependency | Giữ plain library JAR hoặc tách module |
| CI không tìm thấy executable | Có `classifier=exec` hoặc `finalName` nhưng đường dẫn CI chưa cập nhật | Đối chiếu output path, version và classifier |
| Unit tests không chạy | Surefire quá cũ hoặc test discovery sai | Pin Surefire phù hợp, xem `target/surefire-reports`, không coi 0 tests là PASS |
| Build Maven chạy được nhưng Java 17 runtime không nạp class | Compiler release/dependency Java không phù hợp | Kiểm tra `maven.compiler.release`, JDK và class file version |

Một lỗi tại `compile`, `test` hoặc dependency resolution **không nên sửa bằng cách thay cấu hình repackage**. Hãy xác định phase lỗi đầu tiên, kiểm tra input/output và chạy lại đúng vòng đời.

## 16. Quy trình kiểm chứng bắt buộc cho một pull request chỉnh POM

Dùng bảng sau để review:

| Tiêu chí | Bằng chứng mong muốn | PASS khi |
| --- | --- | --- |
| Quản lý dependency | `mvn dependency:tree` | Starter/runtime dependency được resolve đúng |
| Cấu hình plugin | `mvn help:effective-pom` | Plugin version đúng và có execution `repackage` ở `package` |
| Thứ tự phase | Log `mvn clean package` | `jar:jar` trước `spring-boot:repackage` |
| Compile và test | Class files và Surefire report | Không lỗi và các test bắt buộc thực sự được phát hiện |
| Executable layout | `jar tf target/...jar` | Có `BOOT-INF/classes`, `BOOT-INF/lib`, Boot loader |
| Manifest | `META-INF/MANIFEST.MF` | `Main-Class` là launcher; `Start-Class` là main class |
| Khởi động | `java -jar target/...jar` | App start được trên JDK mục tiêu |
| HTTP smoke test | `curl` tới `/hello` | HTTP 200 và body đúng |
| Multi-module / classifier | Artifact path, classifier, reactor log | Đúng module được repackage, không làm hỏng JAR library |

**Tại sao cần nhiều tầng kiểm tra?** `BUILD SUCCESS` chứng minh các goal được Maven thực thi đã hoàn tất theo cấu hình hiện có. Nó không tự chứng minh rằng goal `repackage` từng được bind, JAR được chọn là executable, hoặc ứng dụng sẵn sàng ở runtime. Phải đối chiếu đúng output.

## 17. Bài tập kiểm tra hiểu biết

**1.** Một project import `spring-boot-dependencies` và khai báo `spring-boot-starter-webmvc`. Tại sao `mvn package` vẫn có thể chỉ tạo plain JAR?

*Đáp án:* BOM chỉ quản lý phiên bản dependency; starter chỉ khai báo dependency. Không phần nào tự bind Boot Maven Plugin vào phase `package`.

**2.** Project không dùng starter parent nhưng trong `build/plugins` đã có Boot Maven Plugin version `4.1.2`. Có cần `<executions>` không?

*Đáp án:* Có, nếu chưa kế thừa execution thích hợp từ parent khác. Phải yêu cầu goal `repackage` chạy như một phần lifecycle.

**3.** Mục đích của `<phase>package</phase>` trong execution là gì? Có bắt buộc ghi tường minh không?

*Đáp án:* Nó chỉ định thời điểm chạy goal. Vì goal repackage đã có default phase `package` nên có thể bỏ phase khi dùng goal execution thông thường; ghi rõ giúp người đọc và CI reviewer dễ kiểm tra.

**4.** Nếu gọi `mvn spring-boot:repackage` từ một project chưa có source JAR, chuyện gì có thể xảy ra?

*Đáp án:* Goal thiếu archive để đóng gói lại và có thể lỗi. Cần chạy đến `package` để tạo JAR/WAR trước.

**5.** Có JAR ở `target` và Maven báo `BUILD SUCCESS`. Đã chứng minh repackage chạy đúng chưa?

*Đáp án:* Chưa. Cần kiểm tra log goal, effective POM, Boot layout, manifest và thử `java -jar`.

**6.** Trong một dự án corporate parent với module `common` và `service`, nên bind repackage ở đâu?

*Đáp án:* Ở module `service` cần executable; `common` giữ JAR thư viện thông thường.

**7.** Tại sao executable Boot JAR không nên được dùng như dependency cho module library khác?

*Đáp án:* Class nằm ở `BOOT-INF/classes`, khác layout classpath thông thường của library JAR. Có thể tách module hoặc giữ plain JAR bằng classifier.

**8.** Khi thêm `<classifier>exec</classifier>`, lệnh chạy nào phù hợp?

*Đáp án:* `java -jar target/boot-no-parent-1.0.0-exec.jar`, với điều kiện output đó là executable artifact thực sự.

**9.** Khi bỏ starter parent để thay corporate parent, ngoài repackage còn phải kiểm tra gì?

*Đáp án:* Java compiler release, encoding, resource filtering, version compiler/resources/test/jar plugins, dependency versions và cấu hình inherited trong effective POM.

**10.** Nếu log Boot plugin xuất hiện hai lần, đâu là điểm kiểm tra đầu tiên?

*Đáp án:* `mvn help:effective-pom` để xem các executions được kế thừa, ID của chúng, và liệu child POM đã thêm một execution mới ngoài execution `repackage` có sẵn hay chưa.

## 18. Checklist tự áp dụng

- [ ] POM module application sử dụng đúng `<packaging>jar</packaging>` hoặc `war`.
- [ ] Không dựa vào starter parent khi project chủ đích dùng parent khác.
- [ ] BOM `spring-boot-dependencies` được import để quản lý versions của dependency.
- [ ] Spring Boot Maven Plugin có version đúng và được kích hoạt trong `build/plugins`.
- [ ] Có execution `repackage`, goal `repackage` và phase `package` (tường minh hoặc qua default phase).
- [ ] Không có hai execution repackage ngoài ý muốn do parent/profile.
- [ ] Jar Plugin/source archive chạy trước Boot repackage.
- [ ] Java release, resources và Surefire không phụ thuộc mặc định đã mất khi bỏ parent.
- [ ] `mvn clean package` chạy tests cần thiết và tạo executable archive.
- [ ] `jar tf` thể hiện Boot layout, manifest có `Main-Class` launcher và `Start-Class` app.
- [ ] `java -jar` khởi động được và HTTP smoke test trả đúng nội dung.
- [ ] CI chọn đúng artifact khi có `classifier`/`finalName`.
- [ ] Trong multi-module, chỉ module application được repackage.

**Ghi nhớ:** *Starter chọn thư viện, BOM quản lý phiên bản dependency, còn Maven build plugin + execution gắn `repackage` vào phase `package`*. Khi không dùng starter parent, **chủ động cấu hình execution** là bước quyết định để `mvn clean package` tạo Spring Boot executable JAR.

## 19. Tài liệu chính thức

1. [Spring Boot — Create an Executable JAR with Maven](https://docs.spring.io/spring-boot/how-to/build.html)
2. [Spring Boot Maven Plugin — Using the Plugin; without the Parent POM](https://docs.spring.io/spring-boot/maven-plugin/using.html)
3. [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
4. [Spring Boot — Launching Executable JARs](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html)
5. [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
6. [Apache Maven — Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html)
7. [Apache Maven Surefire — JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
8. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
