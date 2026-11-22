# Tạo JAR thực thi bằng Maven package và repackage trong Spring Boot

## 1. Mục tiêu: từ mã Java đến một file chạy được bằng `java -jar`

Một ứng dụng Spring Boot thường phải được chuyển thành một artifact đủ để triển khai lên máy chủ hoặc container. Với Maven, lệnh phổ biến là:

```bash
mvn clean package
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
```

Đằng sau hai dòng lệnh là **hai công việc đóng gói khác nhau**:

1. Goal `jar:jar` của Maven JAR Plugin tạo **JAR thông thường** từ class/resource đã biên dịch. JAR này thường **không có** toàn bộ dependency đi kèm; nếu chỉ chạy `java -jar`, ứng dụng có thể thiếu classpath hoặc không có main manifest phù hợp.
2. Goal `spring-boot:repackage` của **Spring Boot Maven Plugin** lấy JAR nguồn đó, bổ sung loader và các dependency được chọn vào cấu trúc riêng của Spring Boot, thiết lập manifest phù hợp, tạo **executable/fat JAR** có thể chạy bằng `java -jar`.

Với project dùng `spring-boot-starter-parent` và đã khai báo `spring-boot-maven-plugin`, goal `repackage` được cấu hình sẵn trong lifecycle tại `package`. Vì vậy chỉ cần `mvn clean package`, không cần gọi thêm goal `repackage` bằng tay.

**Điều quan trọng:** “JAR thực thi” trong Spring Boot thường nghĩa là **Java executable archive** chạy được với `java -jar`. Nó không mặc nhiên là chương trình máy native; môi trường đích vẫn cần Java runtime tương thích. Nó cũng khác “fully executable JAR” có shell launch script (giải thích tại mục 11).

### Khi nào nên tạo executable JAR?

- Ứng dụng Spring Boot cần triển khai như một dịch vụ JVM chạy độc lập trên VM/server.
- API có embedded Tomcat/Jetty/Undertow hoặc ứng dụng không có web server, nhưng có một `main` dùng để khởi chạy.
- CI/CD cần một artifact rõ version, có thể kiểm tra và bàn giao cho image build hoặc deployment tool.
- Muốn chạy cùng artifact với các cấu hình môi trường khác nhau (`--server.port`, profile, credentials ngoài JAR).

Đừng dùng executable JAR làm dependency thư viện thông thường của project khác: class ứng dụng nằm dưới `BOOT-INF/classes`, khác bố cục classpath JAR chuẩn. Nếu cần shared library, tách module library hoặc giữ một JAR thường riêng qua classifier.

## 2. Hiểu thứ tự lifecycle của Maven

Maven có **lifecycle phases**; `package` là một phase, còn `jar:jar` và `spring-boot:repackage` là **plugin goals** được gắn vào phase đó. Một lệnh gọi phase `package` khiến Maven chạy tất cả phase trước nó trong lifecycle mặc định, rồi chạy các goals đã bind.

```text
mvn clean package
  |
  +-- clean lifecycle
  |     \-- xóa target/ cũ (maven-clean-plugin)
  |
  +-- default lifecycle đến package
        |
        +-- validate
        +-- process-resources
        +-- compile        --> target/classes
        +-- test-compile   --> target/test-classes (nếu có test)
        +-- test           --> chạy unit tests phù hợp
        +-- package
              |
              +-- maven-jar-plugin:jar
              |     \-- tạo JAR thông thường từ class/resource
              |
              +-- spring-boot-maven-plugin:repackage
                    \-- lấy JAR nguồn, đóng lại thành executable JAR
```

Sơ đồ trên **lược bỏ các phase trung gian** để thấy thứ tự chính; Maven còn có `generate-sources`, `process-classes`, `prepare-package` và những phase khác. Task plugin do project cấu hình có thể thêm goals. Với `<packaging>jar</packaging>` (hoặc khi không khai báo packaging, mặc định là `jar`), Maven JAR Plugin được bind vào `package` theo lifecycle mapping. Spring Boot plugin chạy `repackage` **sau** khi JAR nguồn đã được tạo.

| Lệnh | Điều gì xảy ra? | Kết quả thường gặp |
| --- | --- | --- |
| `mvn compile` | Biên dịch mã nguồn | `target/classes`; chưa tạo executable JAR |
| `mvn test` | Biên dịch rồi chạy tests | Kiểm thử, chưa tới phase `package` |
| `mvn package` | Chạy đến phase package, gồm goal đã bind | Executable JAR nếu plugin repackage được cấu hình |
| `mvn clean package` | Dọn bản dựng cũ rồi package | Artifact từ một lần build sạch |
| `mvn install` | Chạy qua package rồi install vào local Maven repository | Cài artifact chính/attached artifacts vào `~/.m2/repository` |
| `mvn deploy` | Chạy qua package rồi publish artifact vào remote Maven repository | Cần `distributionManagement` và quyền truy cập |
| `mvn spring-boot:repackage` | Gọi trực tiếp một goal cần JAR/WAR nguồn | **Không nên gọi đơn độc** khi chưa chạy `package` |

**Phân biệt `clean` và `package`:** `clean` thuộc một lifecycle khác, nên `mvn package` không tự xóa `target`. Trong CI nên dùng `mvn -B -ntp clean verify` hoặc `clean package` tùy yêu cầu kiểm thử; `verify` thường chạy các kiểm tra/goal bổ sung được bind sau `package`. Với JAR executable, artifact được tạo tại phase `package`.

Nếu test thất bại, Maven thông thường dừng trước `repackage`. `-DskipTests` bỏ bước **chạy** tests nhưng vẫn có thể compile test; `-Dmaven.test.skip=true` có thể bỏ cả biên dịch và chạy test. Không dùng các cờ này để che test lỗi trong đường build phát hành chính.

## 3. Spring Boot starter parent đã cấu hình repackage như thế nào?

`spring-boot-starter-parent` kế thừa quản lý version dependency/plugin và quản lý sẵn một execution của `spring-boot-maven-plugin` với ID **`repackage`**. Tuy nhiên, project vẫn phải khai báo plugin trong phần `<build><plugins>` để kích hoạt sử dụng plugin trong module ứng dụng.

POM tiêu biểu:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Đây là **hai đoạn bên trong `pom.xml`**, chưa phải POM đầy đủ. `3.5.0` được cố định để minh họa nhất quán trên Java 17; đây không phải tuyên bố về phiên bản Spring Boot mới nhất.

Khi sử dụng parent ở trên:
- Plugin version được quản lý theo parent.
- Execution có ID `repackage` đã tồn tại, goal `repackage` chạy trong phase `package`.
- Không cần thêm một execution mới với ID khác hoặc thêm `<goals>` lặp lại.
- Có thể tùy chỉnh execution **đúng ID `repackage`** để dùng classifier, main class hoặc những option phù hợp.

Một lỗi phổ biến là vừa dùng starter parent, vừa thêm một `<execution>` khác có goal `repackage` và ID mới. Maven có thể thực thi repackage hai lần, làm build phức tạp hoặc phát sinh lỗi do artifact đã được đóng lại. Với parent, chỉ cần plugin declaration như trên.

## 4. Ví dụ Java 17+ hoàn chỉnh, xây và chạy được

Ta tạo một API cực nhỏ có endpoint trả lời HTTP. Mục này dùng **Spring Boot 3.5.0**, **Java 17+**, Maven thích hợp với phiên bản Boot. Cần mạng truy cập Maven Central hoặc repository mirror nội bộ để tải parent POM, dependencies và plugins lần đầu.

Cấu trúc project:

```text
packaging-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── packaging/
                        └── PackagingDemoApplication.java
```

### 4.1. File `pom.xml` đầy đủ

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
    <artifactId>packaging-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>packaging-demo</name>
    <description>Demo Maven package and Spring Boot repackage</description>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` cung cấp Spring MVC và embedded servlet server theo starter của nhánh Spring Boot 3.5. Plugin Maven biến JAR ứng dụng thành archive có loader và dependency. POM không cần khai báo version của `spring-boot-starter-web` vì parent quản lý dependency versions.

### 4.2. File Java có entry point và HTTP endpoint

**`src/main/java/com/example/packaging/PackagingDemoApplication.java`:**

```java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PackagingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PackagingDemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello(
            @RequestParam(name = "name", defaultValue = "World") String name) {
        return "Hello, " + name + "!";
    }
}
```

File Java phải khớp `package com.example.packaging` và tên public class `PackagingDemoApplication`. `main` là **ứng dụng thật** được Spring Boot launcher gọi sau khi thiết lập classpath nested JAR. Có thể gộp controller vào class ứng dụng ở ví dụ nhỏ; với ứng dụng lớn nên tách controller/service thành class riêng để dễ bảo trì.

### 4.3. Tạo artifact

Từ thư mục có `pom.xml`:

```bash
java -version
mvn -version
mvn -B -ntp clean package
```

- `-B`: chạy Maven theo chế độ batch, phù hợp CI.
- `-ntp`: không in tiến trình tải artifact quá dài (Maven hiện đại hỗ trợ).
- `clean package`: loại output build trước và thực hiện compilation, tests rồi đóng gói.
- Nếu repo đã có Maven Wrapper, dùng `./mvnw -B -ntp clean package` (Windows: `mvnw.cmd`).

Khi build thành công, thông thường có:

```text
target/
├── classes/
│   └── com/example/packaging/PackagingDemoApplication.class
├── packaging-demo-0.0.1-SNAPSHOT.jar
└── packaging-demo-0.0.1-SNAPSHOT.jar.original
```

Đây là **các file liên quan chính**, không phải danh sách đầy đủ của thư mục `target`: Maven còn có metadata, generated sources và các thư mục khác. `.jar` là executable archive sau `repackage`, `.jar.original` là JAR thông thường trước khi repackaging theo cấu hình mặc định. Không phải JAR `.original` luôn chạy độc lập với `java -jar`.

### 4.4. Chạy JAR và kiểm tra response

```bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
```

Ứng dụng Spring Boot khởi động HTTP server; mặc định thường nghe port **8080** nếu không có cấu hình ghi đè và cổng còn trống. Mở terminal khác:

```bash
curl -fsS 'http://localhost:8080/hello'
curl -fsS 'http://localhost:8080/hello?name=Mai'
```

**Response body tương ứng:**

```text
Hello, World!
Hello, Mai!
```

Mỗi lệnh `curl` gọi riêng một lần và response Java String không tự thêm newline; khi chạy hai lệnh liên tiếp terminal có thể hiển thị liền nhau. Khối output ở trên tách dòng để dễ đọc, không hàm ý server tự gửi ký tự xuống dòng. Dừng server bằng Ctrl+C.

Có thể đổi port tại **thời điểm chạy** mà không đóng gói lại:

```bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar --server.port=9090
```

Khi đó endpoint ở `http://localhost:9090/hello`. Đây là **Spring Boot application argument** chuyển vào `main(String[] args)`, không liên quan đến quá trình Maven repackage. Cấu hình môi trường như database password và token nên được cấp qua nguồn ngoài artifact khi triển khai.

## 5. Kiểm tra JAR thật sự đã được repackage

Chỉ thấy `BUILD SUCCESS` chưa đủ để kết luận archive chạy tốt. Hãy kiểm tra **file đúng đường dẫn**, manifest, layout và chạy smoke test.

### 5.1. Liệt kê nội dung archive

```bash
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar
```

Một số entry kỳ vọng với Spring Boot 3.5:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/packaging/PackagingDemoApplication.class
BOOT-INF/lib/spring-boot-3.5.0.jar
BOOT-INF/lib/...
BOOT-INF/layers.idx
```

Đây là **danh sách entry đại diện**, không phải stdout đầy đủ; version và tập JAR trong `BOOT-INF/lib` phụ thuộc dependency tree/build. Dấu `...` mang tính minh họa, không phải tên file thật. Có thể lọc:

```bash
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar | grep -E '^(BOOT-INF/|org/springframework/boot/loader/)'
```

Lệnh `grep` áp dụng cho Bash/Linux/macOS có grep. Trên Windows PowerShell:

```powershell
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar |
    Select-String '^(BOOT-INF/|org/springframework/boot/loader/)'
```

Nếu class ứng dụng ở ngay `com/example/packaging/...` tại root JAR và không có `BOOT-INF/lib`, rất có thể đó là **plain JAR**, hoặc build chưa chạy `repackage`.

### 5.2. Kiểm tra manifest

Trên hệ Unix có `unzip`:

```bash
unzip -p target/packaging-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
```

Những dòng quan trọng thường là:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.packaging.PackagingDemoApplication
```

Manifest thực có các thuộc tính khác và thứ tự dòng có thể khác. Với Boot 3.x, `Main-Class` là **Spring Boot launcher**, còn `Start-Class` là **main class của ứng dụng**. Spring Boot launcher biết cách nạp JAR nằm trong `BOOT-INF/lib`, rồi gọi `Start-Class`. Đây là lý do không nên tự set `Main-Class` bằng Maven JAR Plugin để thay cho `repackage`.

Đường dẫn class launcher và cấu trúc manifest có thể thay đổi giữa các major version của Spring Boot; khi nâng cấp Boot 4.x hoặc khác, phải xem tài liệu và inspect artifact đúng version, không hardcode hành vi từ một ví dụ 3.5.

### 5.3. Test tối thiểu cần pass

Một artifact đúng phải đáp ứng các kiểm tra:

1. `mvn -B -ntp clean package` trả exit code **0**.
2. `target/packaging-demo-0.0.1-SNAPSHOT.jar` tồn tại và đọc được bằng công cụ JAR.
3. `META-INF/MANIFEST.MF` có main loader/Start-Class phù hợp.
4. `BOOT-INF/classes` chứa class ứng dụng, `BOOT-INF/lib` chứa dependency runtime cần thiết.
5. `java -jar ...` khởi động thành công với Java version được hỗ trợ.
6. `curl -fsS http://localhost:8080/hello` trả body **`Hello, World!`** và HTTP status 2xx.
7. Không có secret/credential nội bộ bị đóng cứng trong resource hoặc cấu hình build ngoài ý muốn.

Nếu CI chỉ kiểm tra kích thước file JAR hoặc kết quả `mvn package` mà không smoke test, vẫn có thể phát hành archive thiếu runtime config hoặc sai Java version.

## 6. Phân biệt JAR thường, executable Boot JAR và “fat JAR”

| Tiêu chí | JAR thường từ `jar:jar` | Executable Boot JAR từ `repackage` |
| --- | --- | --- |
| Class ứng dụng | Thường ở root theo package, ví dụ `com/example/...` | Ở `BOOT-INF/classes/com/example/...` |
| Dependency runtime | Thường **không** đóng kèm | Được đóng thành nested JAR trong `BOOT-INF/lib` |
| Manifest | Có thể không có `Main-Class` chạy được | Boot plugin quản lý `Main-Class` launcher và `Start-Class` |
| Chạy với `java -jar` | Chỉ chạy nếu đủ main/classpath và cấu hình manifest; thường không đủ với app có dependency | Được thiết kế để chạy bằng `java -jar` với Java tương thích |
| Dùng làm thư viện project khác | Thích hợp hơn | Không thích hợp làm dependency theo classpath chuẩn |
| Artifact ví dụ | `...jar.original` hoặc JAR với classifier plain | `...jar` hoặc `...-exec.jar` nếu dùng classifier |

**“Fat JAR/uber JAR”** là thuật ngữ rộng: nhiều công cụ có thể gom class/dependency vào một file. Spring Boot executable JAR là một dạng fat JAR có **dependency JAR lồng nhau**, loader riêng và layout cụ thể; nó không giống lúc Maven Shade Plugin “trộn” toàn bộ các class của dependency vào root JAR. Khi hệ thống tích hợp đòi một layout cụ thể, phải kiểm tra loader và runtime; không chỉ dựa vào chữ “fat”.

`maven-jar-plugin` tự tạo plain JAR, còn `spring-boot-maven-plugin` repackage **sau đó**. Hai plugin phối hợp; không thể dùng Maven JAR Plugin một mình để có Spring Boot nested-loader layout.

## 7. Không dùng Spring Boot parent: phải bind goal `repackage`

Nhiều dự án có corporate parent POM riêng hoặc chỉ import Spring Boot BOM. Trường hợp này **import BOM không đồng nghĩa được hưởng plugin execution** của `spring-boot-starter-parent`.

Ví dụ cấu hình trong một `pom.xml` dùng parent khác; phần below mô tả **những block cần ghép vào POM hợp lệ**, không phải POM độc lập:

```xml
<properties>
    <java.version>17</java.version>
    <spring-boot.version>3.5.0</spring-boot.version>
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
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
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
```

Những điểm cần bảo đảm:

- Project có `<modelVersion>4.0.0</modelVersion>`, `groupId/artifactId/version` hoặc các giá trị kế thừa, và Java main class.
- `<packaging>jar</packaging>` hoặc packaging mặc định là `jar` để Maven tạo plain source archive.
- Version plugin **được khai báo rõ** khi parent không quản lý, và Java compiler hướng tới release 17.
- `repackage` **được bind vào `package`**, ở sau goal tạo source JAR.
- BOM chỉ quản lý dependency version; các plugin khác (compiler, surefire, jar...) nên được pin version qua project/corporate parent theo chính sách build có thể tái lập.

Sau khi ghép đúng, `mvn clean package` cũng tạo executable JAR. Nếu parent doanh nghiệp đã cấu hình goal `repackage`, hãy kiểm tra `mvn help:effective-pom` trước khi **thêm execution thứ hai**, tránh chạy goal trùng. Khi dùng nhiều executions cùng phase, đảm bảo `maven-jar-plugin` tạo JAR nguồn trước `spring-boot-maven-plugin:repackage`.

### Gọi trực tiếp `spring-boot:repackage`

Spring Boot Maven Plugin khuyến cáo **không gọi `repackage` đơn độc** vì goal cần source JAR/WAR được tạo từ phase `package`. Nếu một project có plugin nhưng **chưa bind repackage vào package**, có thể chủ động chạy:

```bash
mvn package spring-boot:repackage
```

Đây là chuỗi Maven chạy phase `package` trước rồi gọi goal `repackage`. Tuy nhiên, **với POM dùng `spring-boot-starter-parent` như mục 4, `mvn package` đã chạy repackage rồi**. Không cần thêm goal một lần nữa; chỉ dùng `mvn clean package` cho ví dụ chính.

## 8. Giữ cả plain JAR và executable JAR bằng classifier

Mặc định `repackage` **thay thế main artifact** của Maven bằng executable JAR và giữ JAR nguồn tại `.jar.original` để tham khảo trong thư mục `target`. Khi cần publish một JAR thông thường cho module khác và đồng thời có executable JAR để chạy, sử dụng `classifier`, ví dụ `exec`.

Với POM có `spring-boot-starter-parent` ở mục 4, **thay đúng khối `<build>` hiện tại** bằng:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>repackage</id>
                    <configuration>
                        <classifier>exec</classifier>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

**Điểm rất quan trọng:** execution ID phải là `repackage` để tùy chỉnh execution đã kế thừa từ parent. Không thêm một execution khác có ID tùy ý chỉ để đặt classifier.

Kết quả của `mvn clean package` thường là:

```text
target/packaging-demo-0.0.1-SNAPSHOT.jar        # Plain JAR (main artifact)
target/packaging-demo-0.0.1-SNAPSHOT-exec.jar   # Executable Boot JAR (classified artifact)
```

Chạy đúng executable artifact:

```bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT-exec.jar
```

Đừng dùng plain JAR ở dòng đầu rồi kỳ vọng nó chạy độc lập. Với classifier, artifact executable có thể được attached để `mvn install`/`mvn deploy` publish bên cạnh main JAR (theo cấu hình plugin và repository). Nếu project khác cần mã dùng lại, vẫn **nên tách module thư viện** thay vì phụ thuộc vào classes của ứng dụng.

### Đổi tên file cuối

Maven hỗ trợ `<finalName>` trong `<build>`:

```xml
<build>
    <finalName>orders-service</finalName>
</build>
```

Đây là **đoạn tùy chọn** cần hợp nhất với block build đang có, không tạo block build thứ hai. Nếu cấu hình `finalName=orders-service`, file trong `target` có thể là `orders-service.jar` thay cho `artifactId-version.jar`. Tuy nhiên, Maven artifact coordinates khi install/deploy vẫn được xác định bởi `groupId/artifactId/version/classifier`; **tên file local không phải toàn bộ danh tính Maven artifact**.

## 9. Tùy chỉnh main class và manifest đúng cách

Nếu project có **nhiều** class chứa `public static void main(String[] args)`, auto-detection có thể thất bại hoặc chọn không như mong muốn. Cấu hình trực tiếp trong Spring Boot Maven plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <mainClass>com.example.packaging.PackagingDemoApplication</mainClass>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là **khối thay thế/ghép vào plugin đang có**, không khai báo song song hai plugin trùng tọa độ. Boot plugin sẽ quản lý `Main-Class` là loader và `Start-Class` là class ứng dụng theo layout/version. Cấu hình `<mainClass>` là cách chủ động khi có nhiều entry points.

Không tự đặt:

```xml
<archive>
    <manifest>
        <mainClass>com.example.packaging.PackagingDemoApplication</mainClass>
    </manifest>
</archive>
```

vào Maven JAR Plugin rồi coi đó là thay thế cho loader Boot. Đây chỉ là dạng cấu hình manifest của JAR plugin, **không tạo `BOOT-INF/lib`** và không bảo đảm nested dependency sẽ được nạp. Với executable JAR Spring Boot, phần manifest liên quan loader/main phải được quản lý qua Boot plugin.

### Các layout khác

Spring Boot Maven Plugin có các layout thường gặp:

| `layout` | Ý nghĩa |
| --- | --- |
| `JAR` | Executable Spring Boot JAR layout chuẩn |
| `WAR` | Executable WAR, class ở `WEB-INF/classes` |
| `ZIP`/`DIR` | Layout dùng `PropertiesLauncher` trong các trường hợp cấu hình riêng |
| `NONE` | Đóng dependency lồng nhau nhưng **không có bootstrap loader**, do đó không mặc nhiên chạy được bằng `java -jar` |

Giữ layout mặc định nếu mục tiêu là executable JAR chuẩn. Đừng chọn `NONE` để “sửa” lỗi `Main-Class`, vì layout này không có loader. Với ứng dụng cần deploy lên servlet container bên ngoài, WAR là một lựa chọn khác và cần cấu hình Spring MVC/servlet container tương thích; không nên ép JAR thành WAR chỉ bằng cách đổi `layout`.

## 10. Dependency nào được đóng vào executable JAR?

Spring Boot plugin chọn dependencies theo dependency graph và cấu hình plugin. JAR thường có:

```text
BOOT-INF/classes/    # Class + resource của ứng dụng
BOOT-INF/lib/        # Dependency JAR cần thiết khi chạy
org/springframework/boot/loader/...  # Spring Boot loader
META-INF/MANIFEST.MF
```

**Không phải mọi dependency trong POM đều cần đi vào artifact.** Các scope `compile`, `runtime`, `provided`, `test` và optional flag ảnh hưởng dependency graph và cách repackage. Boot Maven Plugin có quy tắc đóng gói riêng: trong các nhánh Boot 3.x thông dụng, cả dependency `provided`/`optional` có thể được đưa vào executable archive, trừ khi có exclude cụ thể; `test` dependencies không được coi là runtime dependencies. Hãy kiểm tra bố cục `BOOT-INF/lib` thật thay vì suy đoán chỉ từ scope.

Một số điểm cụ thể ở Spring Boot 3.5:

- `spring-boot-devtools` và `spring-boot-docker-compose` mặc định được loại khỏi repackaged archive bởi các thiết lập `excludeDevtools`/`excludeDockerCompose`.
- `<excludes>` hoặc `<excludeGroupIds>` của Boot plugin có thể bỏ những artifact không muốn phân phối; dùng đúng groupId/artifactId, tránh loại thư viện bắt buộc khiến runtime lỗi.
- `includeSystemScope` không mặc định đưa toàn bộ dependency scope `system` vào executable archive; tránh dựa vào file JAR cục bộ tuyệt đối trên máy dev.
- Một số nested library có yêu cầu đặc biệt phải được giải nén khi chạy; Boot plugin hỗ trợ `requiresUnpack` cho trường hợp cụ thể. Không nên bật đại trà.

Ví dụ **đoạn cấu hình bên trong plugin Spring Boot** để loại một dependency chỉ dùng khi build/dev:

```xml
<configuration>
    <excludes>
        <exclude>
            <groupId>com.example</groupId>
            <artifactId>dev-only-helper</artifactId>
        </exclude>
    </excludes>
</configuration>
```

Đoạn này chỉ mang tính minh họa cho một artifact nội bộ tên `dev-only-helper`. Nếu ứng dụng thật cần class của nó khi chạy, loại bỏ sẽ gây lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError`. Kiểm tra `mvn dependency:tree` và chạy smoke test trước khi cắt giảm dependency.

### Kiểm tra dependency tree

```bash
mvn -B -ntp dependency:tree
```

Lệnh trên hiển thị **cây Maven dependencies đã resolve**, còn `jar tf` hiển thị **những file thực sự nằm trong JAR**. Hai thứ khác nhau: dependency tree còn phản ánh các scope/transitive/omitted conflicts, trong khi executable archive đã áp dụng luật đóng gói của plugin. `dependency:tree` cần Maven Dependency Plugin, có thể phải tải lần đầu.

## 11. Layered JAR và fully executable JAR

Hai tùy chọn này thường bị nhầm vì đều liên quan “tối ưu triển khai”.

### 11.1. Layered JAR phục vụ caching khi build container image

Trong Spring Boot 3.5, executable JAR thường có `BOOT-INF/layers.idx` để mô tả các layer như:

- `dependencies`: dependency release ít đổi;
- `spring-boot-loader`: bootstrap loader;
- `snapshot-dependencies`: dependency snapshot;
- `application`: classes/resources của ứng dụng và module local.

Layer metadata giúp quy trình tạo container image sắp xếp các phần ít đổi thành layer có thể cache, nhưng **JAR vẫn là một archive chạy bằng `java -jar`**. File `layers.idx` không tự biến JAR thành OCI image và cũng không làm Maven tự publish image.

Muốn tắt metadata layer với plugin Boot, thêm **trong `<configuration>` của plugin**:

```xml
<layers>
    <enabled>false</enabled>
</layers>
```

Chỉ cần tùy chỉnh khi có yêu cầu cụ thể; mặc định thường phù hợp. Nếu build OCI image, có thể sử dụng `spring-boot:build-image` hoặc Dockerfile, nhưng đó là **bước triển khai riêng** ngoài mục tiêu `mvn package`/`repackage`.

### 11.2. Fully executable JAR có shell launch script

Spring Boot Maven plugin còn tùy chọn:

```xml
<configuration>
    <executable>true</executable>
</configuration>
```

Tùy chọn này có thể thêm launch script phía trước file JAR để chạy trực tiếp như file executable trên hệ Unix. Đây **khác** executable Boot JAR thông thường vẫn chạy tốt bằng `java -jar`. Một số công cụ ZIP/JAR không xử lý dạng fully executable có prefix script như mong đợi; vì vậy chỉ bật khi thực sự cần chạy file trực tiếp theo cách đó. Mặc định `executable=false`, phù hợp cho phát hành JAR và kiểm tra bằng `jar tf`.

**Đừng coi permission +x của file và Java launcher là cùng khái niệm.** `chmod +x app.jar` không giúp plain JAR chưa repackage tự có loader hoặc dependency.

## 12. Các cách tùy chỉnh ở mức CI/CD

### 12.1. Không đóng secret và runtime-specific config vào binary

Trong ví dụ, `src/main/resources/application.properties` (nếu có) đi vào `BOOT-INF/classes`. File này có thể chứa default **không nhạy cảm**, còn password/token, database URL theo môi trường, khóa ký… nên được cấp từ environment, secret store hoặc cấu hình ngoài artifact.

```bash
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar --server.port=9090
```

Đây là runtime argument, không làm JAR bị thay đổi. Nếu mục đích là giữ **một binary cho dev/staging/prod**, tách cấu hình như vậy giúp tránh build lại theo từng secret.

### 12.2. Bảo đảm Java version

Spring Boot 3.5 yêu cầu Java 17 hoặc cao hơn. Trong POM ví dụ `<java.version>17</java.version>` được parent dùng để đặt compiler release. Build bằng JDK mới hơn nhưng cần chạy ở Java 17 thì phải phát hành bytecode phù hợp và tránh sử dụng API chỉ tồn tại ở phiên bản mới. Trên server:

```bash
java -version
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
```

`UnsupportedClassVersionError` báo hiệu bytecode yêu cầu phiên bản Java mới hơn runtime. Giải pháp là dùng JRE/JDK runtime đủ version hoặc compile đúng release mà dự án thực sự hỗ trợ.

### 12.3. Dùng Maven Wrapper và output xác định

Nên dùng Maven Wrapper `./mvnw`/`mvnw.cmd` khi repository đã cung cấp để mọi máy chạy cùng Maven distribution; cố định Spring Boot/plugin version qua POM và kiểm tra dependency update theo kế hoạch.

Một ví dụ job CI tối thiểu (shell):

```bash
set -e
./mvnw -B -ntp clean verify
test -f target/packaging-demo-0.0.1-SNAPSHOT.jar
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar |
    grep -q 'BOOT-INF/classes/com/example/packaging/PackagingDemoApplication.class'
```

Đây là **đoạn Bash dành cho repo đã có Maven Wrapper**, có `grep`/`test`; không phải YAML pipeline hoàn chỉnh. `verify` đi qua `package` nên artifact đã được tạo; test/execution fail thì job dừng. Trước khi triển khai, bổ sung smoke test chạy thực tế ở môi trường gần production với các dependency bên ngoài được cấu hình thích hợp.

Có thể dùng checksum để xác nhận artifact chuyển qua CI/registry không bị thay đổi:

```bash
sha256sum target/packaging-demo-0.0.1-SNAPSHOT.jar
```

`sha256sum` phổ biến ở Linux; Windows PowerShell có `Get-FileHash -Algorithm SHA256`. Checksum cho biết tính toàn vẹn của **bytes cụ thể**, không chứng minh artifact đúng chức năng hoặc không có lỗ hổng.

## 13. Lỗi phổ biến khi package và repackage

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Có `target/app.jar` nhưng `java -jar` báo `no main manifest attribute` | Chỉ tạo plain JAR, chưa có Boot launcher/manifest | Kiểm tra khai báo Spring Boot Maven plugin, parent và execution `repackage`; đọc manifest |
| `ClassNotFoundException` lúc chạy JAR | Thiếu dependency trong archive hoặc layout/classpath sai | `jar tf` tìm `BOOT-INF/lib`, xem exclude và dependency tree |
| `Could not find main class` / không xác định main class | Thiếu `main` hoặc có nhiều class entry point | Kiểm tra class/package và cấu hình `<mainClass>` trong Boot plugin |
| Gọi `mvn spring-boot:repackage` rồi plugin không tìm được source JAR | Chưa chạy package, goal repackage không tự compile/package từ đầu | Dùng `mvn clean package` nếu parent đã bind hoặc `mvn package spring-boot:repackage` khi chưa bind |
| Gọi goal `repackage` hai lần | Starter parent đã có execution, POM thêm execution/CLI goal dư | Giữ đúng một execution ID `repackage` khi muốn tùy chỉnh |
| Có executable JAR nhưng không chạy được với Java runtime đích | Java version runtime cũ hơn bytecode | Kiểm tra `java -version`, compiler release và Spring Boot requirements |
| `jar tf` không thấy `BOOT-INF/classes` hoặc `BOOT-INF/lib` | Đang xem plain JAR, build bị skip repackage hoặc classifier khác | Kiểm tra tên output, `<classifier>` và `spring-boot.repackage.skip` |
| POM import Boot BOM nhưng không có executable JAR | BOM chỉ quản lý dependency, không bind plugin goal | Khai báo Boot Maven plugin + execution `repackage` vào package |
| Plugin resolution fail, báo `Plugin not found` | Repository/proxy/mirror không truy cập được Spring Boot plugin | Kiểm tra `settings.xml`, `pluginRepositories`, credentials và mirror |
| Plugin báo không có main class | Project là module library, app main không đúng, source không compile | Kiểm tra `src/main/java`, packaging và entry point; module thư viện nên là plain JAR |
| `jar.original` được chạy nhầm | File backup là plain source JAR | Chạy file `.jar` đã repackage hoặc `-exec.jar` khi có classifier |
| Cấu hình `<finalName>` khiến CI không tìm được artifact | Tên trong `target` đổi so với `artifactId-version` | Kiểm tra output thực tế và điều chỉnh CI path |
| Test fail trước khi tạo JAR | Maven chạy `test` trước `package` | Sửa test; chỉ skip theo chính sách rõ ràng, không che lỗi |
| Ứng dụng chạy nhưng port 8080 bận | Runtime config xung đột, tiến trình khác chiếm port | Dừng tiến trình khác hoặc `--server.port=9090` |
| JAR chạy được trên máy dev nhưng fail khi deploy | Khác Java version, secret/config, DNS, network, filesystem permissions | Chạy smoke test trong môi trường triển khai thực tế |
| `maven-jar-plugin` và repackage cùng phase nhưng thứ tự sai | Source archive chưa sẵn sàng cho repackage | Đảm bảo goal tạo JAR được chạy trước goal repackage |
| Có `<layout>NONE</layout>` nhưng `java -jar` không chạy | Layout NONE không có bootstrap launcher | Dùng layout JAR tiêu chuẩn |
| Maven install/deploy xuất bản artifact khác dự kiến | Không hiểu main artifact/classifier/attach | Xem output `mvn install`, plugin `classifier`/`attach` và tọa độ artifact |

### Các lệnh chẩn đoán hữu ích

```bash
mvn -version
mvn help:effective-pom
mvn -B -ntp clean package
mvn -B -ntp dependency:tree
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar
unzip -p target/packaging-demo-0.0.1-SNAPSHOT.jar META-INF/MANIFEST.MF
```

`help:effective-pom` hiển thị cấu hình plugin sau khi kế thừa parent; rất hữu ích để phát hiện `repackage` chưa được bind hoặc chạy lặp. `jar tf` và `unzip -p` kiểm tra archive thực tế. Nếu đang dùng classifier `exec`, thay đường dẫn bằng `...-exec.jar`. Maven Help Plugin và Dependency Plugin cũng có thể cần network để tải lần đầu.

Không nên xóa toàn bộ `~/.m2/repository` chỉ vì một lần build lỗi; hãy xác định đó là lỗi dependency resolution, test, compilation hay archive layout. Với lỗi không tìm thấy dependency đã cache, `mvn -U` có thể cập nhật metadata sau khi sửa repository.

## 14. Các nhầm lẫn hay gặp

1. **“`package` là tên khác của `repackage`.”** Sai: `package` là lifecycle phase; `repackage` là goal của Spring Boot plugin chạy trong phase khi được bind.
2. **“Chỉ cần `spring-boot-starter-web` là JAR tự thực thi.”** Sai: starter cung cấp runtime dependencies, còn plugin Maven và goal repackage tạo layout/launcher.
3. **“Gọi `mvn package spring-boot:repackage` luôn tốt hơn `mvn package`.”** Không đúng với starter parent: repackage đã có trong `package`, gọi thêm là dư.
4. **“BOM thay thế Spring Boot starter parent hoàn toàn.”** BOM chỉ quản lý dependency versions; nó không tự thêm plugin management/execution vào lifecycle.
5. **“Manifest chỉ cần trỏ `Main-Class` về class `@SpringBootApplication`.”** Không đủ cho dependency JAR lồng bên trong; Boot loader và `Start-Class` giải quyết phần này.
6. **“Có file `.jar` nghĩa là chạy được bằng `java -jar`.”** Đuôi file chỉ mô tả định dạng archive. Cần main class, manifest và classpath phù hợp.
7. **“`.jar.original` là bản backup giống executable JAR.”** Đó thường là JAR gốc trước repackage với layout và dependency khác.
8. **“`mvn package` bỏ tests.”** Mặc định Maven đi qua `test` phase; chỉ bypass khi có cấu hình/cờ skip hoặc không có tests.
9. **“`classifier=exec` làm executable JAR trở thành main artifact.”** Với ví dụ cấu hình, main artifact là plain JAR, bản executable mang classifier `exec`.
10. **“`spring-boot:repackage` tạo Docker image.”** Không: nó tạo executable JAR/WAR; image cần một bước riêng, ví dụ Buildpacks hoặc Dockerfile.
11. **“JAR đóng dependency nên có cả secret và Java runtime.”** Không: application config nhạy cảm và Java runtime thường nằm ngoài archive.
12. **“Khi tăng version Spring Boot chỉ cần sửa số version.”** Cần kiểm tra Java requirements, plugin, launcher class, dependency compatibility và chạy lại verification/test theo nhánh tương ứng.

## 15. Quy trình thực hành khuyến nghị

Cho một project Spring Boot mới dùng Maven:

1. Chọn Java version được Spring Boot version hỗ trợ (ví dụ **Java 17** cho Boot **3.5.0**).
2. Dùng `spring-boot-starter-parent` hoặc BOM/corporate parent có cấu hình plugin tương đương.
3. Đảm bảo có một Spring Boot main class và file Java đúng package.
4. Khai báo `spring-boot-maven-plugin`; nếu dùng starter parent, **không thêm execution goal trùng lặp**.
5. Chạy `mvn -B -ntp clean package` để compile, test và repackage.
6. Kiểm tra `target/...jar`, `BOOT-INF/classes`, `BOOT-INF/lib`, `META-INF/MANIFEST.MF`.
7. Chạy `java -jar target/...jar`; kiểm tra endpoint/logic với runtime configuration.
8. Nếu phải có cả thư viện và ứng dụng, tách module hoặc thiết kế classifier `exec`, xác nhận artifact nào được install/deploy.
9. Trong CI, phát hành artifact đã QA, tránh chứa secret, xác minh Java runtime và smoke test trước triển khai.
10. Khi nâng cấp major Spring Boot, đối chiếu hướng dẫn **đúng phiên bản** vì cấu trúc launcher/plugin có thể thay đổi.

## 16. Tài liệu chính thức để đối chiếu theo phiên bản

- Spring Boot 3.5 – [Packaging Executable Archives (Maven Plugin)](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html): `repackage`, classifier, mainClass, dependency exclusions, layers, JAR layout.
- Spring Boot 3.5 – [Using the Maven Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html): starter parent, plugin execution và trường hợp không dùng parent.
- Spring Boot 3.5 – [Build](https://docs.spring.io/spring-boot/3.5/how-to/build.html): executable JAR không phù hợp làm dependency, cách tạo artifact cho library.
- Spring Boot 3.5 – [Efficient Deployments](https://docs.spring.io/spring-boot/3.5/reference/packaging/efficient.html): JAR layers và chiến lược triển khai.
- Apache Maven – [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase `package`, plugin goals và binding.
- Apache Maven – [Maven JAR Plugin](https://maven.apache.org/plugins/maven-jar-plugin/): goal `jar:jar` và manifest.

**Quy tắc ghi nhớ:** Maven `package` **tạo artifact nguồn** theo lifecycle; Spring Boot Maven Plugin `repackage` **tái đóng gói artifact đó** thành executable archive với loader, dependency và manifest đúng để chạy bằng `java -jar`. Khi dùng `spring-boot-starter-parent`, `mvn clean package` đã đủ vì execution `repackage` được cấu hình sẵn.