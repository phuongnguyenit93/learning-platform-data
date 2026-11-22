# Cấu trúc pom.xml tối thiểu cho ứng dụng Spring Boot

## 1. Mục tiêu và điểm xuất phát

Một ứng dụng Spring Boot dùng Maven cần tệp `pom.xml` để Maven biết **dự án là gì**, **lấy thư viện ở đâu**, **dùng Java nào** và **biên dịch/đóng gói bằng plugin nào**. Với `spring-boot-starter-parent`, tệp POM có thể ngắn vì Spring Boot đã cung cấp nhiều mặc định và quản lý các phiên bản thư viện tương thích.

Sau bài học, bạn sẽ:

- Tạo và đọc được `pom.xml` hợp lệ cho ứng dụng Spring Boot đơn module dùng Maven.
- Giải thích chính xác vai trò của `modelVersion`, `parent`, `groupId`, `artifactId`, `version`, `properties`, `dependencies` và `build/plugins`.
- Phân biệt **tối thiểu để Maven hiểu dự án** với **tối thiểu để chạy ứng dụng Spring Boot và tạo executable JAR**.
- Biết vì sao starter không cần khai báo `<version>` khi phiên bản đã được parent quản lý.
- Biên dịch, chạy, kiểm thử và đóng gói ứng dụng mẫu; tìm được cấu hình Maven sau kế thừa.
- Nhận ra lỗi XML, parent, JDK, dependencies và plugin thường gặp.

**Phạm vi:** một ứng dụng Spring Boot dùng Maven, chưa mở rộng sang dự án nhiều module, profile doanh nghiệp hoặc pipeline CI/CD. Ví dụ dưới đây cố định **Spring Boot 3.3.13 và Java 17** để có cấu hình rõ ràng, có thể đối chiếu với tài liệu chính thức của cùng phiên bản. Đây là **phiên bản minh họa**, không phải khẳng định là bản Spring Boot mới nhất. Khi làm dự án thật, dùng phiên bản được đội ngũ/CI chọn và kiểm tra chính sách tương thích của phiên bản đó.

## 2. Phân biệt ba mức “tối thiểu”

Có ba yêu cầu khác nhau:

| Mục đích | Thành phần cần có |
| --- | --- |
| Maven nhận ra một project | XML POM hợp lệ với `project`, `modelVersion` và tọa độ dự án (`groupId`, `artifactId`, `version` hoặc giá trị được kế thừa phù hợp) |
| Spring Boot application có thể biên dịch và chạy | POM hợp lệ, cấu hình phiên bản Spring Boot, dependency phù hợp, JDK và mã nguồn có entrypoint |
| `mvn package` tạo executable Spring Boot JAR | Các điều kiện trên **cộng Spring Boot Maven Plugin và execution `repackage`**, ví dụ đã được cấu hình bởi `spring-boot-starter-parent` |

Một POM chỉ có phần `parent` và tọa độ dự án có thể khiến Maven chạy `package` thành công, thậm chí tạo JAR rỗng; điều đó **không chứng minh** ứng dụng Spring Boot đã sẵn sàng chạy. Ngược lại, thêm starter để biên dịch được code chưa đồng nghĩa Maven đã có plugin đóng gói JAR executable.

Bài này dùng mức **tối thiểu thực dụng cho một ứng dụng web chạy được**: parent, tọa độ, Java version, một web starter, một test starter và Spring Boot Maven Plugin. Phần test starter có thể bỏ nếu chỉ muốn skeleton không kiểm thử, nhưng nên giữ ở dự án học tập và thực tế.

## 3. Bản `pom.xml` đầy đủ có thể dùng trực tiếp

Tạo một thư mục tên `demo`, bên trong tạo tệp `pom.xml` với nội dung:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>demo</name>
    <description>Vi du Maven Spring Boot toi thieu</description>

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
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là **một tệp POM hoàn chỉnh**, không phải fragment cần ghép thêm. XML đóng đủ các tag, các thành phần ở đúng cấp và sử dụng các tên phần tử mà Maven hiểu. Maven tải parent, dependency và plugin từ repository cấu hình trong môi trường. Nếu máy bị chặn mạng/repository, dự án có thể không build được dù POM đúng cú pháp.

Với cấu hình này, Maven thường tạo artifact mang tên `target/demo-0.0.1-SNAPSHOT.jar`; nếu mã nguồn có entrypoint hợp lệ, plugin sẽ đóng gói executable JAR tại phase `package`.

### 3.1. Vì sao không cần `<packaging>jar</packaging>`?

Nếu không ghi `<packaging>`, Maven mặc định sử dụng `jar`. Vì vậy POM trên có thể lược bỏ:

~~~xml
<packaging>jar</packaging>
~~~

Nếu muốn người đọc thấy rõ ý định đóng gói, bạn có thể thêm dòng đó **một lần** sau `<version>` của dự án. Khai báo `jar` tường minh hợp lệ nhưng không bắt buộc. Với WAR, thay đổi `packaging` và các phần liên quan theo yêu cầu triển khai; chỉ đổi một chữ `jar` thành `war` không tự cấu hình đầy đủ một ứng dụng WAR cho servlet container ngoài.

### 3.2. Vì sao `name` và `description` có thể bỏ?

`<name>` và `<description>` là metadata hữu ích cho người đọc, công cụ và các báo cáo. Chúng không quyết định dependency resolution, main class hoặc executable packaging. Bạn có thể xóa cả hai mà ứng dụng ví dụ vẫn có cùng chức năng build. POM thực tế thường giữ chúng để tài liệu và artifact rõ nghĩa.

## 4. Giải thích từng thành phần của POM

### 4.1. `project`, XML namespace và `modelVersion`

Phần ngoài cùng:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <!-- Các thành phần còn lại của POM -->
</project>
~~~

- `<project>` là phần tử gốc của Maven POM. Chỉ có **một root `project`** trong một tệp `pom.xml`.
- `xmlns` xác định namespace mô hình Maven POM 4.0.0; `xsi:schemaLocation` gợi ý XML Schema để IDE và công cụ có thể kiểm tra cấu trúc.
- `<modelVersion>4.0.0</modelVersion>` mô tả **phiên bản mô hình dữ liệu POM**, không phải Maven CLI version, Spring Boot version hay phiên bản ứng dụng.

Đừng sửa `modelVersion` thành `3.3.13` vì đó là phiên bản Spring Boot: Maven sẽ báo lỗi do version của model không hợp lệ.

### 4.2. `parent`: kế thừa cấu hình Spring Boot

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
</parent>
~~~

Đây là Maven parent POM mà project kế thừa. `spring-boot-starter-parent` cung cấp các mặc định phù hợp cho ứng dụng Spring Boot, trong đó có:

- `dependencyManagement` kế thừa từ `spring-boot-dependencies` để quản lý các phiên bản thư viện thường dùng.
- Cấu hình plugin và phiên bản plugin Maven tương thích trong `pluginManagement`.
- Mặc định compiler level Java 17 cho dòng Spring Boot 3.3, cùng encoding UTF-8 và cấu hình `-parameters`.
- Execution `spring-boot:repackage` được chuẩn bị; khi khai báo Spring Boot Maven Plugin trong project, goal này có thể chạy trong lifecycle `package`.
- Một số mặc định cho resource filtering và plugin phổ biến.

`<relativePath/>` rỗng hướng Maven **không tìm parent từ đường dẫn relative mặc định trong thư mục trên**, mà giải quyết parent từ repository. Nó đặc biệt hữu ích cho project một module, nơi không có parent Spring Boot dạng file local. Đây là cấu hình thường gặp, không phải một đường dẫn tải Spring Boot qua mạng.

**Hiểu đúng kế thừa:** project chỉ có thể khai báo **một parent** trong Maven. Nếu công ty đã dùng parent POM nội bộ, không thể thêm `spring-boot-starter-parent` làm parent thứ hai. Lúc đó thường import Spring Boot BOM và tự cấu hình plugin; xem mục 9.

### 4.3. GAV: nhận diện artifact

~~~xml
<groupId>com.example</groupId>
<artifactId>demo</artifactId>
<version>0.0.1-SNAPSHOT</version>
~~~

Ba thành phần gọi là **GAV (groupId, artifactId, version)**, xác định một artifact Maven:

- `groupId`: không gian tên của tổ chức/nhóm, thường dùng dạng reversed domain như `com.example`.
- `artifactId`: tên module/artifact, trong ví dụ là `demo`.
- `version`: phiên bản chính artifact do project tạo, trong ví dụ là `0.0.1-SNAPSHOT`.

Có thể mô tả tọa độ bằng `com.example:demo:0.0.1-SNAPSHOT`. Khi packaging mặc định là JAR, Maven thường xuất ra `target/demo-0.0.1-SNAPSHOT.jar`, trừ khi cấu hình `finalName`, classifier hoặc outputDirectory thay đổi.

**`version` của project khác version của Spring Boot:** project `0.0.1-SNAPSHOT` vẫn có thể dùng Spring Boot `3.3.13`. Bản `SNAPSHOT` biểu thị artifact project có thể tiếp tục được cập nhật trong chu kỳ phát triển; nó không tự biến tất cả dependency thành snapshot.

Trong Maven multi-module, parent có thể cung cấp groupId/version theo kế thừa; ví dụ đơn module dùng khai báo tường minh giúp quan sát dễ dàng.

### 4.4. `properties` và Java version

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

Khi sử dụng Spring Boot starter parent tương ứng, `java.version` là property được parent dùng cho cấu hình Java compiler. Với Spring Boot 3.3, Java 17 là mức hỗ trợ cơ sở; đặt tường minh giúp người đọc biết mục tiêu biên dịch của module.

Cần phân biệt:

- **Java dùng chạy Maven:** xác định qua `mvn -version` hoặc `./mvnw -version`.
- **Java mà Maven compiler dùng để phát sinh bytecode:** phụ thuộc cấu hình plugin và JDK/toolchain. Property `java.version` với parent giúp thống nhất compiler release, nhưng không tự đổi JDK đang chạy Maven.
- **Java runtime để chạy executable JAR:** phải tương thích với class files và dependencies được đóng gói.

Ví dụ khai báo Java 17 nhưng Maven được khởi động với JDK 11 có thể thất bại; sửa `JAVA_HOME`/IDE Maven runner/toolchain để phù hợp, không chỉ đổi `Project SDK` trong IDE. Nên kiểm tra JDK trước khi tìm lỗi trong POM.

### 4.5. `dependencies`: thư viện ứng dụng cần

~~~xml
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
~~~

Trong ví dụ:

- `spring-boot-starter-web` bổ sung hệ thư viện cần thiết để xây dựng ứng dụng web Servlet/MVC thông thường, gồm Spring MVC và embedded server theo mặc định của starter.
- `spring-boot-starter-test` bổ sung các tiện ích phục vụ kiểm thử Spring Boot và các thư viện kiểm thử được starter lựa chọn.
- `<scope>test</scope>` khiến dependency kiểm thử có mặt khi compile/chạy tests, thay vì đưa vào runtime dependency graph của ứng dụng.

Không có `<version>` trong hai dependency này vì parent quản lý version thông qua Spring Boot BOM. Không có nghĩa Maven dùng “phiên bản mới nhất”: Maven giải quyết các version đã được quản lý và các constraint/conflict theo mô hình build. Để biết phiên bản thực tế, xem dependency tree và effective POM.

**Lưu ý:** parent POM **không tự thêm `spring-boot-starter-web`** vào dependencies. Parent quản lý phiên bản, còn việc sử dụng web, data, actuator hay test là do bạn khai báo dependency tương ứng. Thiếu web starter sẽ không có các annotation/class web của ví dụ controller trên classpath.

### 4.6. `build/plugins`: Maven biết đóng gói Spring Boot

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

`spring-boot-maven-plugin` bổ sung các goal liên quan đến ứng dụng Spring Boot, trong đó có:

- `spring-boot:run`: chạy ứng dụng bằng plugin trong môi trường development.
- `spring-boot:repackage`: chuyển JAR/WAR cơ sở thành executable archive có Boot loader và nested dependencies.

Với `spring-boot-starter-parent`, version plugin và execution repackage đã được quản lý/cấu hình; do đó cấu hình plugin trong POM ví dụ **không cần version hoặc khai báo `executions` lặp lại**.

Khi chạy `mvn package`, Maven thực thi lifecycle và plugin goal cần thiết; plugin JAR chuẩn tạo archive trước, rồi execution `repackage` tạo executable JAR cho ứng dụng. **Khai báo dependency Spring Boot mà quên plugin này** có thể làm code compile bình thường nhưng file JAR chưa ở định dạng executable Spring Boot mong muốn.

Không nhầm `build/plugins` với `build/pluginManagement`. `pluginManagement` cung cấp cấu hình/phiên bản mặc định cho plugin khi plugin được sử dụng; nó không có cùng ý nghĩa với khai báo plugin trực tiếp trong `plugins` của ứng dụng.

## 5. Cấu trúc thư mục tối thiểu đi kèm POM

Maven áp dụng cấu trúc thư mục chuẩn:

~~~text
demo/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/demo/
│   │   │       ├── DemoApplication.java
│   │   │       └── PingController.java
│   │   └── resources/
│   │       └── application.properties    # tùy chọn
│   └── test/
│       └── java/
│           └── com/example/demo/
│               └── DemoApplicationTests.java
└── target/                               # Maven sinh ra khi build
~~~

Đường dẫn `target/` **không cần tự tạo** vì Maven sinh ra trong quá trình build. Thư mục `src/main/resources` và `application.properties` có thể để trống/không tạo trong bản ví dụ vì Spring Boot có defaults hợp lý, gồm cổng HTTP mặc định 8080 với web starter.

Bạn có thể dùng Maven Wrapper (các file `mvnw`, `mvnw.cmd`, thư mục `.mvn/wrapper`) để cố định Maven distribution trong dự án. Wrapper **không tự xuất hiện chỉ vì đã viết pom.xml**: cần tạo từ Spring Initializr hoặc chuẩn bị theo quy trình của nhóm.

## 6. Hai file Java tạo ứng dụng thực sự chạy được

### 6.1. Entry point

Tạo tệp `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bật cấu hình ứng dụng Spring Boot, auto-configuration và component scanning bắt đầu từ package chứa class này. `SpringApplication.run` tạo/chạy application context. Trong ví dụ, package `com.example.demo` là package gốc của controller nên component scan sẽ phát hiện controller.

### 6.2. Endpoint kiểm tra

Tạo tệp `src/main/java/com/example/demo/PingController.java`:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

`@RestController` báo đây là Spring MVC controller có response body; `@GetMapping("/ping")` ánh xạ GET /ping. Với cổng 8080 mặc định, gọi endpoint này sẽ nhận body `pong`. Code dùng API từ `spring-boot-starter-web`, cho thấy dependency được khai báo trong POM có tác dụng cụ thể.

Hai file phải nằm dưới đúng đường dẫn tương ứng với `package com.example.demo;`. Tên public class phải trùng tên file `.java`: `DemoApplication.java` và `PingController.java`. Cố gắng chạy cả hai public class trong một file sai tên sẽ khiến Java compiler báo lỗi.

### 6.3. Kiểm thử context đơn giản (khuyến nghị)

Tạo `src/test/java/com/example/demo/DemoApplicationTests.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DemoApplicationTests {

    @Test
    void contextLoads() {
        // Kiểm tra Spring application context khởi tạo được.
    }
}
~~~

Khi chạy test lifecycle, `spring-boot-starter-test` cung cấp JUnit Jupiter và Spring Test. Test này xác nhận application context có thể nạp; **nó không thực hiện HTTP request và không chứng minh endpoint trả `pong`**. Để kiểm tra endpoint cần gọi nó khi ứng dụng chạy hoặc viết một bài test HTTP riêng.

Trong bài học tối thiểu, file test không bắt buộc để compile một ứng dụng không có test, nhưng thêm nó khiến `mvn test` có một kiểm tra hữu ích.

## 7. Chạy từ terminal: lệnh nào kiểm chứng điều gì?

Mở terminal tại thư mục `demo` chứa `pom.xml`.

### 7.1. Xác minh JDK và Maven trước

~~~bash
java -version
mvn -version
~~~

Nếu dự án có Maven wrapper, dùng:

~~~bash
./mvnw -version
~~~

Trên Windows PowerShell với wrapper, dùng `.\mvnw.cmd -version`. Với POM ví dụ, cần Maven/JDK tương thích Spring Boot 3.3 và Java 17+, cùng đường tới repository Maven để tải dependency. `mvn -version` cho biết cả Maven version và Java mà Maven thực sự chạy.

**Các lệnh tiếp theo dùng `mvn` vì ta chỉ tự tạo pom.xml, chưa tạo wrapper.** Nếu wrapper đã có trong project, thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trên Windows để dùng Maven distribution được dự án cố định.

### 7.2. Biên dịch, kiểm thử, đóng gói

~~~bash
mvn validate
mvn compile
mvn test
mvn package
~~~

Các lệnh có ý nghĩa khác nhau:

- `validate`: kiểm tra project có thông tin cần thiết để bắt đầu build; không phải full compile.
- `compile`: chạy lifecycle đến compile để biên dịch source trong `src/main/java`.
- `test`: chạy đến test, gồm biên dịch test và thực thi test khi Surefire/test configuration cho phép.
- `package`: chạy đến package, tạo JAR và thực thi `repackage` nếu plugin/execution đã cấu hình như POM ví dụ.

Maven phase có tính kế thừa: gọi `mvn package` bình thường đã đi qua các phase trước. Không bắt buộc chạy bốn lệnh liên tiếp mỗi lần; chia chúng trong bài học nhằm giúp quan sát khác biệt.

Để làm sạch output cũ và tạo lại:

~~~bash
mvn clean package
~~~

`clean` thuộc lifecycle clean, xóa thư mục build (thường là `target`) trước khi chạy default lifecycle tới `package`. Thao tác này giúp không nhầm artifact từ build cũ với output hiện tại.

### 7.3. Chạy ứng dụng bằng Maven plugin

~~~bash
mvn spring-boot:run
~~~

Lệnh gọi goal `spring-boot:run` để khởi động ứng dụng trực tiếp. Đây là cách tiện khi phát triển; nó **khác** lệnh `mvn package`, vốn tập trung vào tạo artifact. Khi thấy ứng dụng đã khởi động thành công, mở terminal khác:

~~~bash
curl -s http://localhost:8080/ping
~~~

Nội dung phản hồi mong đợi:

~~~text
pong
~~~

`curl -s` không tự thêm ký tự xuống dòng vào body; phần hiển thị này chỉ biểu diễn body chính xác. Nếu ứng dụng đổi server port hoặc cổng 8080 đang bị ứng dụng khác chiếm, điều chỉnh/cấp lại cổng phù hợp. Dừng ứng dụng Maven bằng Ctrl+C.

### 7.4. Chạy executable JAR

~~~bash
mvn clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

Từ terminal khác, gọi lại endpoint `/ping` như trên. Kết quả `pong` cho biết archive chứa mã/đường chạy HTTP của ví dụ và có thể được thực thi trong môi trường hiện tại.

Trong thư mục target, thường xuất hiện:

~~~text
target/
├── classes/
├── test-classes/
├── demo-0.0.1-SNAPSHOT.jar
└── demo-0.0.1-SNAPSHOT.jar.original
~~~

`.jar` là executable Boot archive sau khi plugin repackage thành công; `.jar.original` thường là archive trước khi repackage ở cấu hình mặc định. File cụ thể có thể khác theo plugin config, Java tests, classifier, `finalName` hoặc phiên bản plugin. Tránh hardcode tên artifact trong CI nếu project định nghĩa tên output khác.

Nếu `mvn package` thành công nhưng `java -jar` báo thiếu main manifest hoặc thư viện, cần kiểm tra Maven plugin execution, archive đúng hay chưa, main class và đầu ra build. Một regular JAR không tự có khả năng chạy Spring Boot như executable JAR.

## 8. Cơ chế giải quyết dependencies và plugin versions

### 8.1. Parent quản lý, dependency quyết định sử dụng

Điểm rất dễ nhầm: `spring-boot-starter-parent` **không tự tải tất cả Spring Boot starter vào ứng dụng**. Nó cung cấp dependency management và plugin defaults. Bạn vẫn phải khai báo các dependency cần dùng trong `dependencies`.

Trong POM ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Không có version nhưng Maven có thể tìm version qua dependencyManagement của parent/BOM. Mối liên hệ:

~~~text
spring-boot-starter-parent:3.3.13
    ↓ quản lý version cho các dependency đã được chọn
spring-boot-dependencies:3.3.13
    ↓ dependencyManagement
spring-boot-starter-web (khai báo trong ứng dụng)
    ↓ kéo các transitive dependencies cần thiết
Spring MVC, embedded server, JSON và thư viện hỗ trợ
~~~

Sơ đồ tập trung vào nguyên tắc; dependency graph thực tế phải xem từ `mvn dependency:tree`. Nếu tự thêm `<version>` cho một dependency được Spring Boot quản lý, bạn có thể override lựa chọn tương thích của BOM; chỉ làm khi có lý do kỹ thuật và đã kiểm tra compatibility.

### 8.2. `dependencies` khác `dependencyManagement`

- `dependencies`: khai báo **project cần dùng thư viện nào**; Maven sẽ đưa dependency vào các classpath phù hợp với scope.
- `dependencyManagement`: quy định **version/scope/thuộc tính mặc định** cho dependency khi dependency được sử dụng; nó không tự thêm dependency vào classpath của module.
- `pluginManagement`: đặt defaults cho Maven plugins; không giống với việc dùng plugin trong `build/plugins`.

Chính sự phân biệt này giúp POM Spring Boot tối thiểu vừa ngắn vừa kiểm soát được phiên bản.

### 8.3. Scope để giữ runtime gọn

Scope có tác động đến classpath khi compile/test/run:

| Scope | Ý nghĩa ngắn gọn | Ví dụ sử dụng |
| --- | --- | --- |
| `compile` | Mặc định nếu bỏ scope; thường có ở compile/runtime/test classpath | `spring-boot-starter-web` |
| `test` | Chỉ cần cho việc biên dịch/chạy tests | `spring-boot-starter-test` |
| `provided` | Cần cho compile/test nhưng thường kỳ vọng runtime/container cung cấp | Servlet API/Tomcat trong WAR triển khai container ngoài |
| `runtime` | Không cần khi compile source chính, nhưng cần để chạy | JDBC driver trong nhiều tình huống |

Không đặt `spring-boot-starter-web` thành `test` nếu source chính dùng Spring MVC annotations: code có thể không compile vì class cần thiết không có trong main compile classpath.

## 9. Nếu không dùng `spring-boot-starter-parent` thì sao?

Với parent Maven của doanh nghiệp hoặc parent riêng của nhóm, POM **không thể khai báo thêm parent thứ hai**. Có thể import Spring Boot BOM trong `dependencyManagement`:

~~~xml
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
~~~

Đây chỉ là **fragment** cho một POM đã có parent hoặc tọa độ project hợp lệ. Import BOM giữ được quản lý dependency version, nhưng **không nhập toàn bộ plugin management, compiler configuration hoặc execution `repackage`** như khi kế thừa starter parent.

Nếu không kế thừa starter parent, ứng dụng muốn đóng gói executable JAR cần plugin version phù hợp và cấu hình execution, ví dụ:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.3.13</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Ngoài ra, phải khai báo Java compiler release/encoding và các plugin tiêu chuẩn theo policy của parent đang dùng. Không nên copy fragment và coi đó đã là một POM đầy đủ. Bài này ưu tiên starter parent vì nó giúp cấu hình ngắn, dễ học và ít phải quản lý version thủ công.

## 10. Đọc cấu hình Maven thực sự có hiệu lực

POM viết tay chỉ là một phần của mô hình build. Maven còn kết hợp Super POM, parent POM, `dependencyManagement`, `pluginManagement`, profiles, settings và tham số dòng lệnh.

Các lệnh thực hành:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn help:active-profiles
mvn dependency:tree
mvn help:effective-settings
~~~

- **`help:effective-pom`**: xuất mô hình POM sau kế thừa và activation; dùng để xác nhận version Spring Boot plugin, Java compiler và execution repackage.
- **`help:active-profiles`**: cho biết những Maven profile nào thực sự đang kích hoạt; ví dụ tối thiểu không định nghĩa custom profile.
- **`dependency:tree`**: hiện dependency graph đã được giải quyết, kể cả transitive dependencies; dùng để điều tra version hoặc dependency bị kéo thêm.
- **`help:effective-settings`**: xem settings đã hợp nhất để điều tra repository/mirror. Không chia sẻ credential, private repository token hoặc settings nhạy cảm.

Khi đổi version Spring Boot trong parent, không chỉ nhìn phiên bản ghi ở POM: dùng effective POM và dependency tree để quan sát version plugin/ thư viện thực sự đã được Maven chọn.

Nếu gặp lỗi `No plugin found for prefix 'spring-boot'`, có thể thiếu plugin trong build hoặc thiếu khả năng resolve plugin từ repository. Nếu lỗi xảy ra trong khi Maven đang tải parent, kiểm tra khả năng truy cập repository và parent version trước.

## 11. Những lỗi phổ biến khi viết POM tối thiểu

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra/sửa |
| --- | --- | --- |
| `Non-parseable POM` | XML không đóng tag, sai nesting, ký tự `&` chưa escape | Kiểm tra XML syntax và một root `project`; dùng `&amp;` nếu cần literal `&` trong XML |
| `Unrecognised tag` | Đặt `dependency` ngoài `dependencies` hoặc `plugin` sai vị trí | Đọc cấu trúc POM; một `dependency` nằm trong `dependencies` hoặc `dependencyManagement/dependencies` |
| Parent POM không resolve | Sai phiên bản, mất mạng, mirror/proxy hoặc `relativePath` dẫn nhầm | Xác nhận version parent và repo settings; dùng `<relativePath/>` khi tải starter parent từ repository |
| `Cannot find symbol RestController/GetMapping` | Thiếu web starter hoặc dependency không resolve | Xem `dependencies`, chạy Maven sync và `mvn dependency:tree` |
| Dependency version is missing | Không có parent/BOM quản lý version, hoặc dependency không nằm trong danh sách quản lý | Kiểm tra effective POM và khai báo version đúng nơi |
| `invalid target release: 17` | JDK của Maven/compiler thấp hơn release đã chọn | Chạy `mvn -version`, kiểm tra JDK/toolchain và `JAVA_HOME` |
| `No plugin found for prefix spring-boot` | Plugin chưa được khai báo/resolve | Kiểm tra `build/plugins` và repository truy cập được |
| `mvn package` tạo JAR nhưng không chạy `java -jar` | Thiếu repackage execution, lấy nhầm plain archive hoặc không có main class | Xem effective POM, log `spring-boot:repackage` và manifest/archive |
| `Unable to find a single main class` | Có nhiều entrypoints hoặc không có main class mà plugin tìm được | Giữ entrypoint rõ ràng, cấu hình `mainClass` khi thực sự cần |
| Test compile/fail | Thiếu starter test, test code sai hoặc context khởi tạo lỗi | Xem Surefire output, package test, annotations và môi trường |
| `mvn` thành công nhưng IDE vẫn báo đỏ | IDE chưa import POM, JDK sai, Maven settings khác | Reload Maven project, so sánh JDK và Maven distribution/settings |
| Build chạy được trên máy A nhưng lỗi máy B | Khác Maven/JDK, mirror, profile, environment hoặc cache | Dùng Maven wrapper/JDK chuẩn, ghi version và lệnh tái hiện |

Không giải quyết bằng cách xóa ngẫu nhiên parent, gắn `<version>` thủ công lên mọi starter hoặc xóa cache toàn bộ. Hãy xác định lỗi nằm ở **cú pháp POM**, **resolution**, **compiler**, **test** hay **packaging**, rồi sửa đúng phần.

## 12. Các sai lầm tư duy cần tránh

**“Parent POM là dependency.”** Sai. Parent được khai báo trong `<parent>` để Maven kế thừa cấu hình. Dependency nằm trong `<dependencies>` để đưa thư viện vào classpath.

**“Có `spring-boot-starter-parent` là tự có web server.”** Sai. Parent quản lý cấu hình; muốn ứng dụng web MVC đơn giản như ví dụ phải khai báo `spring-boot-starter-web`.

**“`<java.version>17</java.version>` tự cài JDK 17.”** Sai. Đây là property cấu hình mục tiêu Java; cần JDK thích hợp được cài và được Maven/compiler dùng.

**“Không khai báo version starter thì Maven lấy bản mới nhất.”** Sai. Phiên bản được quản lý qua BOM/parent; nếu không có quản lý phù hợp, Maven có thể báo thiếu version.

**“Maven có plugin Boot trong `pluginManagement` tức là luôn tự chạy repackage.”** Sai. Cần plugin/execution được áp dụng cho module; parent Spring Boot chuẩn đã cung cấp execution khi dùng plugin đúng cách.

**“`mvn test` chạy rồi là có executable JAR.”** Sai. `test` nằm trước `package`; cần `package` để tạo JAR. Ngược lại, `spring-boot:run` có thể chạy ứng dụng mà chưa tạo executable JAR dưới `target`.

**“Chỉ cần pom.xml, không cần mã Java.”** Maven có thể nhận dự án và đóng gói artifact cơ sở khi thiếu source; để có ứng dụng chạy thật cần entrypoint và code phù hợp.

## 13. Bài thực hành tự làm và tiêu chí hoàn thành

Thực hành tại một thư mục `demo` mới, với JDK 17+ và Maven tương thích.

1. Tạo POM hoàn chỉnh ở mục 3, hai Java files mục 6.1–6.2 và tùy chọn test mục 6.3.
2. Chạy `mvn -version`, ghi lại Java runtime đang chạy Maven.
3. Chạy `mvn clean test`. Xác nhận Java classes compile được và JUnit context test pass nếu đã tạo test.
4. Chạy `mvn spring-boot:run`, gửi GET đến `http://localhost:8080/ping`, xác nhận body `pong`; dừng ứng dụng bằng Ctrl+C.
5. Chạy `mvn clean package`; xác định file dưới `target`, kiểm tra Maven log có `spring-boot:repackage` và chạy `java -jar target/demo-0.0.1-SNAPSHOT.jar`.
6. Chạy `mvn help:effective-pom -Doutput=target/effective-pom.xml`; tìm `java.version`/compiler config, Spring Boot plugin, execution repackage và dependencyManagement.
7. Thử **xóa riêng** `spring-boot-starter-web` khỏi một bản sao POM: source controller sẽ không còn API MVC trên compile classpath. Khôi phục dependency và xác minh build lại.
8. Thử bỏ `spring-boot-maven-plugin` khỏi một bản sao POM: kiểm tra `package` còn tạo JAR cơ sở nhưng thiếu repackage execution cho executable Boot archive. Khôi phục plugin và xác minh kết quả.
9. Thử đổi `artifactId` trong một bản sao và giải thích vì sao tên file kết quả thay đổi, trong khi URL `/ping` không phụ thuộc `artifactId`.

### Câu hỏi tự kiểm tra

**Câu 1.** Trong POM ví dụ, tại sao `spring-boot-starter-web` không cần `<version>`?

**Đáp án:** `spring-boot-starter-parent` kế thừa dependencyManagement từ `spring-boot-dependencies` để cung cấp version được quản lý.

**Câu 2.** Có bắt buộc khai báo `<packaging>jar</packaging>`?

**Đáp án:** Không. Maven mặc định dùng packaging `jar` nếu không khai báo.

**Câu 3.** Khác nhau giữa `<version>0.0.1-SNAPSHOT</version>` ở project và `<version>3.3.13</version>` ở parent?

**Đáp án:** Phiên bản thứ nhất là của artifact ứng dụng; phiên bản thứ hai chọn phiên bản của Spring Boot starter parent và các mặc định quản lý tương ứng.

**Câu 4.** Vì sao `mvn spring-boot:run` và `java -jar target/...jar` không phải cùng một thao tác?

**Đáp án:** Goal `run` khởi động ứng dụng qua plugin khi phát triển; `java -jar` chạy executable archive đã được build/repackage.

**Câu 5.** Nếu không thể dùng `spring-boot-starter-parent` do có parent nội bộ, chỉ import BOM đã đủ thay thế toàn bộ cấu hình không?

**Đáp án:** Chưa. BOM giải quyết dependency management, còn Java compiler, plugin management và execution repackage cần được cấu hình qua parent hiện tại hoặc POM của module.

**Đạt yêu cầu khi:** bạn có một POM hợp lệ, project Java 17+ biên dịch được, `mvn test`/`mvn package` thành công theo cấu hình, `/ping` trả `pong`, executable JAR chạy được, và bạn giải thích được từng khối POM mà không nhầm giữa parent, dependency và plugin.

## 14. Nguồn tham khảo chính thức

- Spring Boot 3.3 — Tutorial: Developing Your First Spring Boot Application: https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Spring Boot 3.3 — Maven Plugin, Using the Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Maven POM Reference: https://maven.apache.org/pom.html
- Maven Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html

Khi tạo dự án thực tế bằng Spring Initializr hoặc template đã được nhóm kiểm chứng, ưu tiên duy trì cấu trúc và version tương ứng của template. POM là đầu vào quan trọng của build nhưng **kết quả sau kế thừa và dependency resolution** mới cho biết chính xác Maven sẽ chạy như thế nào.
