# Chạy ứng dụng Spring Boot bằng IDE, Gradle wrapper hoặc Maven wrapper

Sau khi tạo dự án Spring Boot đầu tiên, việc tiếp theo là **khởi động ứng dụng**, quan sát log và thử gửi một HTTP request. Có ba cách thông dụng: chạy trực tiếp từ IDE, dùng **Gradle wrapper** hoặc dùng **Maven wrapper**. Cả ba đều có thể khởi động cùng một ứng dụng, nhưng cách chuẩn bị môi trường và câu lệnh hơi khác nhau.

Bài này hướng dẫn từng cách, cách xác nhận ứng dụng đã chạy, cách đổi cổng hoặc profile, và cách xử lý những lỗi thường gặp. Ví dụ sử dụng một ứng dụng Spring Boot có endpoint HTTP đơn giản.

## 1. Chuẩn bị trước khi chạy

Bạn cần:

1. **JDK tương thích với phiên bản Spring Boot của dự án.** Với các dự án Spring Boot 3.x hoặc 4.x, Java 17 là mức tối thiểu; hãy kiểm tra phiên bản cụ thể mà dự án yêu cầu và cấu hình `JAVA_HOME` hoặc Project SDK phù hợp.
2. **Mã nguồn của dự án** đã được tạo hoặc tải về đầy đủ.
3. **Một công cụ phát triển** nếu chạy bằng IDE: IntelliJ IDEA, Eclipse/Spring Tools, hoặc Visual Studio Code với tiện ích Java/Spring phù hợp.
4. **Kết nối mạng ở lần đầu** nếu wrapper phải tải phiên bản Gradle/Maven và dependency chưa có trong cache.

Trong terminal, kiểm tra Java:

```bash
java -version
javac -version
```

Lệnh `java` cho biết Java runtime đang được shell sử dụng; `javac` cho biết compiler của JDK. Nếu terminal tìm được Java nhưng IDE sử dụng JDK khác, ứng dụng có thể chạy khác nhau giữa hai môi trường.

### 1.1. Nhận diện dự án dùng Gradle hay Maven

Mở **thư mục gốc dự án** (nơi chứa file cấu hình build) và kiểm tra:

| Dấu hiệu ở thư mục gốc | Dự án dùng | Cách chạy phù hợp |
| --- | --- | --- |
| `build.gradle` hoặc `build.gradle.kts` | Gradle | `gradlew` / `gradlew.bat` |
| `pom.xml` | Maven | `mvnw` / `mvnw.cmd` |
| `gradle/wrapper/gradle-wrapper.properties` | Gradle wrapper | Wrapper tải và chọn bản Gradle đã cấu hình |
| `.mvn/wrapper/maven-wrapper.properties` | Maven wrapper | Wrapper tải và chọn bản Maven đã cấu hình |

Ví dụ cấu trúc một dự án Gradle:

```text
demo/
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    └── main/
        ├── java/com/example/demo/DemoApplication.java
        └── resources/application.properties
```

Dự án Maven thường có `pom.xml`, `mvnw`, `mvnw.cmd`, thư mục `.mvn/wrapper/` và cùng cấu trúc `src/main/...`.

**Chú ý:** thông thường dự án chỉ chọn **một** build tool. Nếu có `pom.xml` thì dùng hướng dẫn Maven; nếu có `build.gradle` hoặc `build.gradle.kts` thì dùng Gradle. Không cần cài đồng thời cả Gradle và Maven chỉ để chạy dự án có wrapper.

### 1.2. Ứng dụng ví dụ

Giả sử dự án có dependency **Spring Web** (thường là `spring-boot-starter-web`) và file `src/main/java/com/example/demo/DemoApplication.java`:

```java
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
        return "Hello Spring Boot";
    }
}
```

`@SpringBootApplication` đánh dấu lớp khởi động và kích hoạt cấu hình cơ bản của Spring Boot; `SpringApplication.run(...)` tạo và khởi động application context. `@RestController` kết hợp với `@GetMapping("/hello")` khai báo endpoint trả về chuỗi khi nhận `GET /hello`.

Lớp ví dụ trên đặt controller ngay trong lớp main để dễ quan sát. Trong dự án lớn hơn, thường tách controller ra file riêng. Hãy bảo đảm đường dẫn file tương ứng với `package` và các dependency Spring Boot được khai báo trong build file.

Khi ứng dụng HTTP khởi động thành công với cấu hình mặc định, mở:

```text
http://localhost:8080/hello
```

Kết quả mong đợi:

```text
Hello Spring Boot
```

Nếu chỉ tạo dự án Spring Boot không có dependency web, ứng dụng vẫn có thể khởi động nhưng sẽ **không** tự mở HTTP server trên cổng 8080. Việc không thấy cổng HTTP trong trường hợp đó không nhất thiết là lỗi.

## 2. Cách 1 — Chạy trực tiếp bằng IDE

IDE thuận tiện khi đang viết code: có nút Run/Debug, breakpoint, console, công cụ điều hướng mã và khả năng xem biến khi chương trình chạy.

### 2.1. Các bước chung

1. Mở IDE và chọn **Open/Import Project** từ **thư mục gốc** chứa `pom.xml` hoặc `build.gradle`.
2. Đợi IDE import Maven/Gradle project, resolve dependency và lập chỉ mục source code.
3. Chọn **Project SDK/JDK** phù hợp với yêu cầu của Spring Boot và build tool.
4. Mở lớp có `@SpringBootApplication` và phương thức `public static void main(String[] args)`, chẳng hạn `DemoApplication`.
5. Chọn **Run** cho phương thức `main` hoặc tạo cấu hình chạy kiểu Java/Spring Boot Application.
6. Theo dõi cửa sổ **Run/Console**; khi ứng dụng sẵn sàng, thử endpoint `/hello`.
7. Khi cần dừng, nhấn **Stop** ở cửa sổ Run.

Ví dụ từ `DemoApplication`:

```java
public static void main(String[] args) {
    SpringApplication.run(DemoApplication.class, args);
}
```

IDE gọi phương thức `main` giống như khi chạy một chương trình Java thông thường. Spring Boot tiếp tục thực hiện phần việc khởi tạo context, cấu hình bean và web server nếu ứng dụng có web stack tương ứng.

### 2.2. Thao tác với một số IDE phổ biến

| IDE | Cách bắt đầu | Nơi xem kết quả |
| --- | --- | --- |
| **IntelliJ IDEA** | Mở dự án, chọn JDK, nhấn biểu tượng Run cạnh `main()` hoặc dùng Run Configuration | Cửa sổ **Run** hoặc **Debug** |
| **Eclipse / Spring Tools** | Import dự án Maven/Gradle, mở lớp main, chọn **Run As → Java Application** hoặc **Spring Boot App** khi có Spring Tools | **Console** |
| **Visual Studio Code** | Cài hỗ trợ Java/Spring phù hợp, mở thư mục dự án, chờ import, chọn **Run Java** tại phương thức `main()` | **Terminal**, **Debug Console** hoặc Java Run output tương ứng |

Nếu IDE báo thiếu package `org.springframework...`, trước tiên hãy kiểm tra đã mở đúng thư mục dự án và quá trình import/đồng bộ dependency đã hoàn thành. Việc chỉ mở riêng một file `.java` thường không đủ để IDE nhận diện cấu hình build.

### 2.3. Run và Debug khác nhau ở đâu?

- **Run:** khởi động ứng dụng để tương tác và xem log.
- **Debug:** cũng khởi động ứng dụng, nhưng cho phép đặt breakpoint, tạm dừng tại từng dòng, xem giá trị biến và theo dõi call stack.

Ví dụ, đặt breakpoint ở:

```java
@GetMapping("/hello")
public String hello() {
    return "Hello Spring Boot";
}
```

Chạy bằng Debug rồi truy cập `http://localhost:8080/hello`. Khi request được xử lý, IDE có thể dừng tại breakpoint để bạn xem luồng chạy. Lưu ý: mỗi lần khởi động một tiến trình mới trên cùng cổng, tiến trình đang chiếm cổng cần được dừng trước.

### 2.4. Run Configuration cần lưu ý gì?

Một cấu hình chạy thường có:

- **Main class:** `com.example.demo.DemoApplication`.
- **JDK/runtime:** phiên bản Java phù hợp.
- **Working directory:** thường là thư mục gốc dự án.
- **Program arguments:** tham số đưa vào `main(String[] args)`, ví dụ `--server.port=8081`.
- **Environment variables:** ví dụ `SPRING_PROFILES_ACTIVE=dev`.
- **VM options:** tham số JVM, ví dụ `-Xmx512m`; **khác** với program arguments.

Tham số như `--server.port=8081` là thuộc tính ứng dụng Spring Boot, không phải VM option. VM option như `-Xmx512m` phải được cấu hình cho JVM. Đặt nhầm loại có thể khiến cấu hình không có hiệu lực.

## 3. Cách 2 — Chạy bằng Gradle wrapper

**Gradle wrapper** là các script được lưu cùng dự án để sử dụng đúng phiên bản Gradle đã cấu hình. Wrapper giúp nhóm phát triển và CI dùng cùng phiên bản build tool mà không phải yêu cầu từng người cài Gradle thủ công.

Các tệp thường gặp:

```text
gradlew                         # script Unix/macOS/Linux
gradlew.bat                     # script Windows
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

`gradle-wrapper.properties` chứa thông tin phiên bản và địa chỉ phân phối Gradle, điển hình qua thuộc tính `distributionUrl`. Wrapper có thể tải bản Gradle đó trong lần chạy đầu; sau đó thường sử dụng lại bản đã cache.

### 3.1. Chạy trên macOS hoặc Linux

Mở terminal ở thư mục gốc có file `gradlew`:

```bash
./gradlew bootRun
```

Nếu báo lỗi không có quyền thực thi:

```bash
chmod +x ./gradlew
./gradlew bootRun
```

### 3.2. Chạy trên Windows

Trong **PowerShell**:

```powershell
.\gradlew.bat bootRun
```

Trong **Command Prompt (cmd.exe)**:

```bat
gradlew.bat bootRun
```

Lệnh `bootRun` được Spring Boot Gradle plugin cung cấp để chạy ứng dụng. Gradle sẽ xử lý dependency, biên dịch các thành phần cần thiết rồi khởi động ứng dụng với classpath phù hợp. Tiến trình thường tiếp tục chạy trong terminal cho đến khi bạn dừng nó.

Để dừng một ứng dụng đang chạy trong terminal, nhấn **Ctrl+C**. Lệnh này gửi tín hiệu dừng tới tiến trình hoặc nhóm tiến trình được điều khiển bởi terminal; hãy kiểm tra log để biết ứng dụng đã kết thúc.

### 3.3. Khi nào có task `bootRun`?

Dự án cần áp dụng Spring Boot Gradle plugin tương thích. Một đoạn cấu hình minh họa theo cú pháp Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'PHIEN_BAN_SPRING_BOOT'
}
```

Trong dự án thực tế, thay chuỗi minh họa `PHIEN_BAN_SPRING_BOOT` bằng phiên bản plugin hợp lệ và dùng cấu hình dependency management tương ứng của dự án. Nếu dự án tạo từ Spring Initializr, cấu hình này thường đã được tạo sẵn.

Để xem các task của dự án:

```bash
./gradlew tasks
```

Nếu không có task `bootRun`, hãy kiểm tra dự án có phải ứng dụng Spring Boot dùng Gradle hay không, và Spring Boot plugin đã được áp dụng chưa. Với dự án Maven, `bootRun` không phải câu lệnh phù hợp.

### 3.4. Truyền tham số ứng dụng

Ở shell Unix, có thể truyền program arguments tới ứng dụng thông qua task `bootRun`:

```bash
./gradlew bootRun --args='--server.port=8081'
```

Trong PowerShell:

```powershell
.\gradlew.bat bootRun --args="--server.port=8081"
```

`--server.port=8081` là tham số của **ứng dụng Spring Boot**; `--args` là tùy chọn của task chạy Java trong Gradle. Khi đổi cổng thành 8081, URL để thử sẽ là `http://localhost:8081/hello`.

### 3.5. Tạo file JAR với Gradle

Khi muốn đóng gói ứng dụng để chạy riêng:

```bash
./gradlew bootJar
```

JAR có thể được tạo trong thư mục `build/libs/`. Ví dụ:

```bash
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

Tên JAR thực tế phụ thuộc tên dự án, phiên bản và cấu hình build; hãy chọn đúng file mà `bootJar` sinh ra. Khác với `bootRun`, câu lệnh `java -jar` chạy artifact đã được đóng gói; nếu sửa source code, bạn cần build lại JAR để những thay đổi đó xuất hiện.

## 4. Cách 3 — Chạy bằng Maven wrapper

**Maven wrapper** có cùng mục tiêu: dùng phiên bản Maven do dự án quy định thông qua script đi kèm, giảm lệ thuộc vào phiên bản Maven đã cài trên máy.

Các tệp thường gặp:

```text
mvnw                         # script Unix/macOS/Linux
mvnw.cmd                     # script Windows
.mvn/wrapper/maven-wrapper.properties
```

Tùy phiên bản và kiểu wrapper, thư mục `.mvn/wrapper/` có thể chứa thêm file JAR cho wrapper. Nếu thiếu file cần thiết của wrapper, hãy khôi phục từ nguồn dự án thay vì chỉ chép riêng script từ một dự án khác.

### 4.1. Chạy trên macOS hoặc Linux

Mở terminal ở thư mục gốc có `pom.xml` và `mvnw`:

```bash
./mvnw spring-boot:run
```

Nếu script thiếu quyền thực thi:

```bash
chmod +x ./mvnw
./mvnw spring-boot:run
```

### 4.2. Chạy trên Windows

Trong **PowerShell**:

```powershell
.\mvnw.cmd spring-boot:run
```

Trong **Command Prompt (cmd.exe)**:

```bat
mvnw.cmd spring-boot:run
```

`spring-boot:run` là goal của **Spring Boot Maven plugin**. Plugin khởi động ứng dụng Spring Boot trực tiếp từ project với classpath cần thiết. Giống cách chạy bằng IDE hay Gradle, terminal này sẽ còn bận trong thời gian ứng dụng đang chạy; dùng **Ctrl+C** để dừng.

### 4.3. Plugin Maven cần thiết

Trong `pom.xml` của một ứng dụng Spring Boot Maven thông thường, có cấu hình như:

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

Phiên bản plugin thường được quản lý bởi Spring Boot parent POM hoặc cơ chế dependency/plugin management của dự án. Đoạn XML trên là một phần của `pom.xml`, không phải toàn bộ file build.

Nếu Maven không nhận ra tiền tố `spring-boot`, hãy kiểm tra plugin có được khai báo hoặc quản lý đúng cách không, và project có đang được chạy từ thư mục chứa `pom.xml` phù hợp không.

### 4.4. Chạy với profile hoặc tham số

Spring Boot Maven plugin có thể nhận cấu hình profile qua thuộc tính plugin:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

Trong PowerShell, nếu việc diễn giải đối số có dấu chấm hoặc dấu bằng gây lỗi, có thể truyền chuỗi nguyên vẹn:

```powershell
.\mvnw.cmd spring-boot:run "-Dspring-boot.run.profiles=dev"
```

Giá trị `dev` ở đây là tên Spring profile. Chỉ kích hoạt profile nếu ứng dụng có cấu hình hoặc bean liên quan. Một cách dùng chung cho IDE, Gradle và Maven là thiết lập biến môi trường `SPRING_PROFILES_ACTIVE`.

### 4.5. Đóng gói với Maven

Để biên dịch, kiểm tra theo vòng đời build và đóng gói:

```bash
./mvnw package
```

Khi Spring Boot Maven plugin được cấu hình để **repackage** executable JAR (thường có sẵn trong dự án Spring Boot tạo bằng parent phù hợp), file có thể nằm tại `target/demo-0.0.1-SNAPSHOT.jar`. Chạy nó:

```bash
java -jar target/demo-0.0.1-SNAPSHOT.jar
```

Thư mục `target/` là đầu ra thường gặp của Maven, tương ứng với `build/` của Gradle. Nếu `java -jar` báo không tìm thấy main manifest hoặc thiếu thư viện, cần xem dự án đã tạo **executable Spring Boot JAR** hay chỉ là JAR Java thông thường.

## 5. Quan sát và xác nhận ứng dụng đã chạy

Bất kể khởi động bằng cách nào, điều quan trọng là xem **kết quả từ ứng dụng**, không chỉ nhìn thấy lệnh build hoàn thành.

Một ứng dụng dùng Spring MVC với embedded Tomcat có thể ghi log tương tự:

```text
... Tomcat started on port 8080 (http) with context path '/'
... Started DemoApplication in ... seconds
```

Nội dung log cụ thể thay đổi theo phiên bản Spring Boot, logging configuration và web server. Với ứng dụng WebFlux dùng Netty hoặc không có web dependency, không nhất thiết sẽ có dòng `Tomcat started`.

Thử request từ trình duyệt hoặc terminal:

```bash
curl http://localhost:8080/hello
```

Phản hồi ví dụ:

```text
Hello Spring Boot
```

Có thể thử thêm `curl -i http://localhost:8080/hello` để xem HTTP status và headers, thường là `200 OK` cho endpoint hoạt động bình thường.

Nếu ứng dụng chạy ở cổng khác hoặc có `server.servlet.context-path`, cần điều chỉnh URL tương ứng. Nếu đã sửa `@GetMapping("/hello")`, hãy dùng đúng đường dẫn mới.

### 5.1. Ý nghĩa của một số trạng thái thường gặp

| Quan sát | Ý nghĩa có thể có | Hướng kiểm tra |
| --- | --- | --- |
| `Started DemoApplication ...` và request trả về dữ liệu | Ứng dụng và endpoint ví dụ đã sẵn sàng | Tiếp tục phát triển hoặc thử request khác |
| Log báo ứng dụng khởi động nhưng `localhost:8080` không kết nối | Có thể không có web server, dùng cổng khác hoặc ứng dụng đã thoát | Kiểm tra web dependency, `server.port`, log cuối và tiến trình |
| `404 Not Found` | Server có phản hồi nhưng không tìm thấy route tương ứng | Kiểm tra `@GetMapping`, package scan, context path |
| `500 Internal Server Error` | Request đến server nhưng xử lý bên trong gặp lỗi | Xem stack trace và log request |
| `Port 8080 was already in use` | Một tiến trình khác đang giữ cổng hoặc ứng dụng chạy trùng | Dừng tiến trình cũ hoặc đổi cổng |

Việc build thành công chỉ chứng minh giai đoạn build tương ứng đã hoàn tất; nó không bảo đảm một endpoint HTTP hoạt động. Ngược lại, cửa sổ terminal vẫn đang chạy cũng không tự chứng minh ứng dụng sẵn sàng phục vụ request.

## 6. Cấu hình cổng và profile theo cách nhất quán

Spring Boot hỗ trợ nhiều nguồn cấu hình. Ở bài đầu tiên, hai thứ dễ quan sát nhất là **cổng HTTP** và **profile**.

### 6.1. Đổi cổng trong `application.properties`

Tạo hoặc chỉnh `src/main/resources/application.properties`:

```properties
spring.application.name=demo
server.port=8081
```

Khởi động lại ứng dụng. Sau đó dùng:

```text
http://localhost:8081/hello
```

Lưu ý file cấu hình phải được đưa vào classpath của ứng dụng. Khi thay đổi file cấu hình, nên khởi động lại để chắc chắn giá trị được áp dụng. Với ứng dụng không có HTTP server, `server.port` không tự tạo ra HTTP endpoint.

### 6.2. Sử dụng biến môi trường

Để đổi cổng tạm thời mà không sửa file cấu hình, đặt `SERVER_PORT`:

**Linux/macOS — ví dụ với Gradle:**

```bash
SERVER_PORT=8082 ./gradlew bootRun
```

**Windows PowerShell — ví dụ với Maven:**

```powershell
$env:SERVER_PORT = "8082"
.\mvnw.cmd spring-boot:run
```

Biến môi trường `SERVER_PORT` ánh xạ tới thuộc tính Spring Boot `server.port`. Giá trị từ biến môi trường có thể ghi đè giá trị trong `application.properties` theo thứ tự ưu tiên cấu hình chuẩn của Spring Boot.

Kích hoạt profile `dev` cũng tương tự:

**Linux/macOS:**

```bash
SPRING_PROFILES_ACTIVE=dev ./gradlew bootRun
```

**Windows PowerShell:**

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
.\mvnw.cmd spring-boot:run
```

Khi profile `dev` được kích hoạt, Spring Boot có thể nạp thêm `application-dev.properties` hoặc `application-dev.yml` nếu tồn tại. Dùng profile để phân biệt cấu hình theo môi trường, ví dụ các endpoint tích hợp hoặc mức log; không nên hard-code thông tin bí mật vào file chia sẻ trong repository.

Với PowerShell, các biến `$env:...` được đặt trong **phiên shell hiện tại**; chúng có thể ảnh hưởng đến những lệnh chạy sau trong cùng phiên. Khi muốn trở lại cấu hình mặc định, đóng shell đó hoặc xóa biến thích hợp, ví dụ `Remove-Item Env:SERVER_PORT`.

### 6.3. Program arguments và JVM options

Hai loại đối số không giống nhau:

```text
--server.port=8083    → thuộc tính Spring Boot (program argument)
-Xmx512m              → tùy chọn của JVM (giới hạn heap)
```

Trong IDE, đặt `--server.port=8083` vào trường **Program arguments**. Khi chạy executable JAR:

```bash
java -Xmx512m -jar build/libs/demo-0.0.1-SNAPSHOT.jar --server.port=8083
```

Ví dụ này dùng tên file JAR của Gradle. Với Maven, thay đường dẫn bằng file trong `target/`. Không đặt `-Xmx512m` phía sau tên JAR với kỳ vọng JVM tự nhận đó là VM option.

## 7. So sánh ba cách chạy

| Tiêu chí | IDE | Gradle wrapper | Maven wrapper |
| --- | --- | --- | --- |
| Cách bắt đầu | Run/Debug tại lớp main | `./gradlew bootRun` | `./mvnw spring-boot:run` |
| Điều kiện chính | IDE, JDK và project import đúng | Dự án Gradle có wrapper và Spring Boot plugin | Dự án Maven có wrapper và Spring Boot Maven plugin |
| Xem log | Run/Console của IDE | Terminal | Terminal |
| Debug với breakpoint | Thuận tiện, tích hợp sẵn | Cần cấu hình debugger nếu muốn gắn vào tiến trình | Cần cấu hình debugger nếu muốn gắn vào tiến trình |
| Phù hợp nhất | Học, viết code, điều tra lỗi | Terminal, tài liệu nhóm, CI dùng Gradle | Terminal, tài liệu nhóm, CI dùng Maven |
| Dừng | Nút Stop của IDE | `Ctrl+C` | `Ctrl+C` |

Các cách này **không phải ba phiên bản Spring Boot khác nhau**. Chúng là ba con đường khởi động mã ứng dụng. Chọn cách phù hợp với build tool của project và công việc hiện tại.

Một luồng thực hành hợp lý khi mới học là:

1. Chạy bằng **IDE** để hiểu phương thức `main`, log và breakpoint.
2. Chạy bằng **wrapper** tương ứng của dự án để bảo đảm thao tác có thể thực hiện từ terminal trên máy khác.
3. Thử **đổi cổng** và gọi HTTP endpoint để xác nhận bạn đang tác động đúng tiến trình.
4. Tạo **executable JAR** rồi chạy bằng `java -jar` để hiểu khác biệt giữa phát triển và chạy artifact đã đóng gói.

## 8. Lỗi thường gặp và cách xử lý

### 8.1. `java` hoặc `javac` không được nhận diện

Ví dụ trên Windows:

```text
'java' is not recognized as an internal or external command
```

Hoặc trên Unix:

```text
java: command not found
```

Hệ điều hành chưa tìm được Java trong `PATH`, hoặc JDK chưa được cài. Cần cài JDK tương thích, cấu hình `JAVA_HOME` và `PATH` phù hợp, mở terminal mới rồi kiểm tra lại `java -version`.

### 8.2. `UnsupportedClassVersionError` hoặc `invalid source release`

Đây thường là dấu hiệu **phiên bản Java không khớp** giữa compiler, bytecode hoặc JVM đang chạy. Xem yêu cầu của dự án, phiên bản từ `java -version`, cấu hình toolchain của Gradle/Maven và JDK trong IDE. Không chỉ đổi Java ngoài terminal rồi giả định IDE tự chuyển sang bản mới.

### 8.3. Không tìm thấy wrapper hoặc không chạy được script

Lỗi ví dụ:

```text
./gradlew: No such file or directory
```

Hãy kiểm tra terminal đã đứng tại thư mục chứa `gradlew` chưa và dự án dùng Gradle hay Maven. Trên Windows cần gọi script `.bat`/`.cmd`; trên Unix script cần quyền thực thi phù hợp. Nếu wrapper thiếu file trong thư mục `wrapper/`, lấy lại bộ wrapper đầy đủ từ repository.

### 8.4. Không tải được dependency hoặc bản Gradle/Maven

Wrapper lần đầu có thể tải build tool; Gradle/Maven tiếp tục tải plugin và thư viện. Nếu quá trình này thất bại, xem lỗi cụ thể về mạng, proxy, certificate, repository, URL của wrapper, phiên bản dependency hoặc cache hỏng. Không nên coi mọi lỗi tải dependency là lỗi source code Java.

### 8.5. Port 8080 đã được sử dụng

Thông báo điển hình:

```text
Web server failed to start. Port 8080 was already in use.
```

Nguyên nhân có thể là bạn đã chạy một bản ứng dụng trong IDE và đang mở thêm bản khác bằng wrapper. Dừng tiến trình cũ bằng nút Stop hoặc `Ctrl+C`, hoặc cấu hình `server.port=8081` cho tiến trình mới.

### 8.6. Ứng dụng khởi động lỗi khi tạo bean

Spring có thể báo lỗi `ApplicationContext` hoặc `BeanCreationException` nếu cấu hình bean, dependency injection, biến môi trường hoặc kết nối database chưa phù hợp. Hãy đọc **nguyên nhân gốc** trong stack trace (`Caused by`), không chỉ đọc dòng `APPLICATION FAILED TO START`.

Ví dụ nếu đã thêm dependency JPA và database nhưng chưa cấu hình `spring.datasource.url`, ứng dụng có thể không khởi động được. Đây là vấn đề cấu hình ứng dụng, không phải do lựa chọn IDE, Gradle hay Maven wrapper.

### 8.7. Ứng dụng chạy nhưng endpoint trả về 404

Kiểm tra:

- Đã có dependency web phù hợp chưa?
- Controller có `@RestController` và method có `@GetMapping("/hello")` chưa?
- Controller có nằm trong package được component scan không?
- Đã dùng đúng cổng, context path và đường dẫn URL chưa?
- Có vô tình chạy phiên bản JAR cũ, thay vì code mới sửa, không?

Nếu dự án đang chạy bằng JAR, việc chỉnh source mà không đóng gói lại sẽ không thay đổi nội dung của JAR đã tạo.

## 9. Bài thực hành

### Bài 1 — Chạy ứng dụng bằng hai cách

Chọn một ứng dụng Spring Boot có endpoint `/hello`. Chạy bằng IDE, truy cập `http://localhost:8080/hello`, quan sát kết quả. Dừng ứng dụng và chạy lại bằng **wrapper phù hợp** với dự án (Gradle hoặc Maven), rồi truy cập cùng URL.

Ghi lại điểm giống nhau và khác nhau giữa cách khởi động trong IDE và terminal: nơi xem log, cách dừng, cách đặt breakpoint.

### Bài 2 — Đổi cổng

Thiết lập `server.port=8081` trong `application.properties`, khởi động lại ứng dụng và thử hai URL:

```text
http://localhost:8080/hello
http://localhost:8081/hello
```

Giải thích vì sao chỉ URL tương ứng với cổng đã cấu hình mới kết nối đúng ứng dụng đó (giả sử không có tiến trình khác trên cổng còn lại).

### Bài 3 — Dùng profile `dev`

Tạo file `src/main/resources/application-dev.properties`:

```properties
server.port=8082
```

Chạy ứng dụng với `SPRING_PROFILES_ACTIVE=dev`. Xác nhận endpoint chuyển sang cổng 8082. Sau đó bỏ profile `dev`, khởi động lại và quan sát cổng trở về cấu hình mặc định hoặc giá trị trong `application.properties`.

### Bài 4 — Chạy JAR

Đóng gói executable JAR bằng `bootJar` (Gradle) hoặc `package` kèm cấu hình repackage phù hợp (Maven). Chạy bằng `java -jar` và gọi endpoint. Thử sửa nội dung trả về của `/hello` trong source code mà **chưa build lại JAR**; giải thích vì sao tiến trình chạy từ JAR vẫn dùng phiên bản cũ.

## 10. Kết nối kiến thức

Lớp `DemoApplication` với `@SpringBootApplication` và `main()` là điểm bắt đầu chung. **IDE** gọi `main()` qua cấu hình chạy của công cụ phát triển; **Gradle wrapper** dùng task `bootRun`; **Maven wrapper** dùng goal `spring-boot:run`. Sau khi Spring Boot thực sự khởi động, bạn có thể xác nhận bằng log và một HTTP request tới endpoint của mình.

Khi chuyển giữa các cách chạy, hãy luôn xác định rõ **JDK**, **thư mục gốc**, **build tool**, **cổng** và **profile**. Nắm vững những thông tin này sẽ giúp bạn tự khởi động và xử lý sự cố ở các bài học Spring Boot tiếp theo.
