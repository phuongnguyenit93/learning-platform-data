# Khởi chạy ứng dụng Spring Boot từ IDE, Gradle bootRun và tệp JAR

## 1. Ba cách chạy đang giải quyết cùng một việc gì?

Một ứng dụng Spring Boot bắt đầu từ phương thức `main(String[] args)`. Lệnh `SpringApplication.run(...)` tạo ngữ cảnh Spring, đăng ký bean, áp dụng cấu hình, khởi động các thành phần cần thiết và, nếu có thư viện Web phù hợp, mở máy chủ HTTP nhúng. Ba cách chạy **IDE**, **Gradle `bootRun`** và **`java -jar`** đều đưa ứng dụng đến quá trình đó nhưng khác nhau ở cách chuẩn bị mã, thư viện, cấu hình và gói triển khai.

- **IDE:** mở lớp có `main` rồi Run/Debug. Phù hợp viết mã, đặt breakpoint, xem biến và sửa lỗi trong lúc phát triển.
- **`bootRun`:** dùng tác vụ Gradle do Spring Boot Gradle plugin cung cấp. Gradle biên dịch và chạy từ `runtimeClasspath` của dự án. Phù hợp tái hiện cấu hình chạy của dự án bằng lệnh, kể cả khi không mở IDE.
- **`java -jar`:** khởi động một **executable JAR** đã được tạo bằng `bootJar`. Phù hợp kiểm tra chính xác gói phát hành và chạy ứng dụng trên máy chủ/container.

Sơ đồ luồng:

```text
src/main/java + src/main/resources + dependencies
                |
        +-------+-------+
        |               |
   IDE / bootRun      Gradle bootJar
        |               |
  Classpath chạy       build/libs/*.jar
        |               |
        |           java -jar ...
        +-------+-------+
                |
        main() -> SpringApplication.run(...)
                |
       Spring context và (nếu là Web) HTTP server
```

**Phân biệt quan trọng:** `bootRun` thường sử dụng class và tài nguyên đã biên dịch trong thư mục build cùng các JAR phụ thuộc; `java -jar` chạy nội dung của tệp JAR tại thời điểm đóng gói. Sửa mã nguồn sau khi tạo JAR **không** tự thay đổi JAR cũ.

## 2. Điều kiện tiên quyết và ứng dụng minh họa

Bạn cần một dự án Spring Boot áp dụng Gradle plugin `org.springframework.boot`, có Java đúng phiên bản mà dự án yêu cầu và xác định được lớp khởi động. Spring Boot 3.x yêu cầu tối thiểu Java 17; ví dụ bên dưới dùng **Java 21**, Gradle 8.5 trở lên trong nhánh phù hợp và Spring Boot 3.3.x. Dự án thật phải dùng phiên bản đã khai báo trong repository, không tự nâng/hạ chỉ để chạy ví dụ.

Cấu trúc tối giản để thực hành:

```text
launch-demo/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat              (Gradle Wrapper nếu dự án đã tạo)
└── src/main/
    ├── java/com/example/demo/
    │   ├── DemoApplication.java
    │   └── PingController.java
    └── resources/
        └── application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'launch-demo'
```

`build.gradle` (ví dụ độc lập, dùng Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

`src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/com/example/demo/PingController.java`:

```java
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
```

`src/main/resources/application.properties`:

```properties
spring.application.name=launch-demo
server.port=8080
```

`@SpringBootApplication` giúp Spring Boot tự cấu hình và quét thành phần trong package `com.example.demo` cùng các package con. `PingController` được tìm thấy, nên khi ứng dụng Web chạy, yêu cầu `GET /ping` trả về chuỗi `pong`. Đây là ví dụ chạy được khi đã có Gradle Wrapper và tải được các dependency. Nếu dự án chưa có Wrapper, tạo dự án bằng Spring Initializr/IDE hoặc dùng một bản Gradle đã cài để sinh Wrapper; các lệnh `./gradlew` không tồn tại khi thiếu tệp Wrapper.

Kiểm tra công cụ trước khi chạy:

```bash
java -version
./gradlew --version
```

Trên Windows PowerShell, thay lệnh thứ hai bằng `.\gradlew.bat --version`. Phiên bản Java của **IDE Project SDK**, **Gradle Java toolchain** và lệnh `java` trong terminal có thể khác nhau; phải kiểm tra từng nơi khi phát sinh lỗi phiên bản.

## 3. Cách 1: chạy trực tiếp bằng IDE

Trong IntelliJ IDEA, Eclipse/STS hoặc IDE hỗ trợ Spring Boot:

1. Mở **đúng thư mục dự án Gradle**, chờ đồng bộ dependency và cấu hình JDK.
2. Mở `DemoApplication.java`, tìm phương thức `public static void main(String[] args)`.
3. Chọn **Run DemoApplication** (hoặc tạo Java/Spring Boot Run Configuration trỏ đến `com.example.demo.DemoApplication`).
4. Quan sát cửa sổ Run. Với ví dụ có `spring-boot-starter-web`, máy chủ HTTP sẽ chạy ở cổng 8080 nếu cổng còn trống và không có cấu hình khác ghi đè.
5. Mở `http://localhost:8080/ping` để kiểm tra; dừng ứng dụng bằng nút Stop của IDE.

Một Run Configuration thường có:

| Trường | Tác dụng |
|---|---|
| Main class | Lớp có `main` dùng để khởi động, ở đây là `com.example.demo.DemoApplication` |
| JDK / Java runtime | JVM thực thi chương trình; phải tương thích với bytecode |
| Working directory | Thư mục làm việc cho đường dẫn tương đối, ví dụ tệp ngoài |
| Program arguments | Đối số truyền đến `main`, như `--server.port=9090` |
| VM options | Đối số JVM, như `-Xmx512m` hoặc `-Dspring.profiles.active=dev` |
| Environment variables | Biến môi trường, như `SPRING_PROFILES_ACTIVE=dev` |

**Không nhầm Program arguments và VM options.** `--server.port=9090` là đối số ứng dụng; `-Xmx512m` là tùy chọn JVM. IDE có thể chạy classpath do nó biên dịch hoặc ủy quyền thao tác chạy cho Gradle, tùy cấu hình; vì vậy khi đối chiếu với `bootRun` phải kiểm tra chế độ thực tế của IDE.

Muốn gỡ lỗi, đặt breakpoint trong `PingController.ping()`, chọn **Debug** thay vì Run, rồi gửi yêu cầu `GET /ping`. IDE tạm dừng tại breakpoint để bạn xem stack và biến. Bấm Resume để hoàn tất phản hồi HTTP.

## 4. Cách 2: chạy bằng Gradle bootRun

Trong thư mục chứa Wrapper và `build.gradle` của dự án độc lập, chạy:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Gradle sẽ tải những plugin/dependency chưa có (lần đầu cần truy cập repository), thực hiện những tác vụ biên dịch/tài nguyên cần thiết rồi khởi chạy lớp `main` với classpath runtime. Tác vụ **`bootRun`** có khi Spring Boot Gradle plugin được áp dụng cho project phù hợp; không phải mọi module Gradle đều có tác vụ này.

### Truyền tham số ứng dụng

Đổi cổng chạy từ 8080 sang 9090:

```bash
./gradlew bootRun --args='--server.port=9090'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--server.port=9090"
```

Nhiều tham số được ngăn cách bằng dấu cách trong cùng giá trị `--args`:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --server.port=9090'
```

Đây là **tham số của ứng dụng**, không phải cờ cấu hình build của Gradle. Nếu đã chạy `bootRun` trong terminal, cần **dừng phiên cũ bằng Ctrl+C** trước khi khởi chạy lại cùng cổng. Đừng nhầm tiến trình Gradle daemon còn hoạt động với tiến trình Web đang phục vụ yêu cầu.

### Dự án nhiều module

Ở repository Gradle nhiều project, đứng tại thư mục gốc có Wrapper và dùng **đúng đường dẫn Gradle project** (tên thực tế lấy từ cấu hình dự án):

```bash
./gradlew :app:bootRun
./gradlew :app:bootJar
```

`:app` chỉ là ví dụ. `:app:bootRun` chạy một project con; nếu chạy `bootRun` ở root mà root không áp dụng Spring Boot plugin, Gradle có thể báo không tìm thấy tác vụ. Không suy ra đường dẫn Gradle project chỉ từ tên thư mục.

### Debug khi chạy bằng Gradle

`bootRun` kế thừa khả năng chạy Java của Gradle. Khi muốn gắn trình gỡ lỗi từ IDE, có thể dùng:

```bash
./gradlew bootRun --debug-jvm
```

JVM ứng dụng thường chờ debugger kết nối ở cổng 5005; tạo cấu hình **Remote JVM Debug** trong IDE để kết nối. Đây là **cổng gỡ lỗi**, khác với cổng HTTP của Spring Boot. Nếu phiên bản Gradle/plugin hoặc thiết lập project thay đổi cơ chế debug, xem các tùy chọn thực tế của tác vụ `bootRun`.

## 5. Cách 3: đóng gói và chạy executable JAR

Trong cùng dự án:

```bash
./gradlew clean bootJar
```

Windows PowerShell:

```powershell
.\gradlew.bat clean bootJar
```

`clean` xóa kết quả build trước đó và là lựa chọn khi muốn đóng gói sạch; không bắt buộc mỗi lần. `bootJar` tạo **Spring Boot executable JAR** chứa class ứng dụng, tài nguyên, dependency runtime và bộ nạp của Spring Boot. Với ví dụ ở trên, tên mặc định thường là:

```text
build/libs/launch-demo-0.0.1-SNAPSHOT.jar
```

Kiểm tra tên tệp thực tế trước khi chạy:

```bash
ls build/libs/
```

Windows PowerShell:

```powershell
Get-ChildItem .\build\libs\*.jar
```

Chạy JAR tương ứng:

```bash
java -jar build/libs/launch-demo-0.0.1-SNAPSHOT.jar
```

Windows PowerShell:

```powershell
java -jar .\build\libs\launch-demo-0.0.1-SNAPSHOT.jar
```

Nếu đổi cổng hoặc profile:

```bash
java -jar build/libs/launch-demo-0.0.1-SNAPSHOT.jar --server.port=9090 --spring.profiles.active=dev
```

Tùy chọn JVM phải **đứng trước** `-jar`, còn đối số ứng dụng đứng **sau** tên JAR:

```bash
java -Xmx512m -Dspring.profiles.active=dev -jar build/libs/launch-demo-0.0.1-SNAPSHOT.jar --server.port=9090
```

Với ứng dụng Spring Boot 3.3.x, một executable JAR thường có manifest phân biệt bộ nạp và lớp ứng dụng: `Main-Class` chỉ đến Spring Boot `JarLauncher`; `Start-Class` chỉ đến `DemoApplication`. Vì vậy chạy `java -jar` không cần tự liệt kê từng JAR dependency trong classpath.

**Đừng nhầm `jar` và `bootJar`.** Tác vụ `jar` của Java plugin có thể tạo JAR thông thường (đôi khi có hậu tố `-plain.jar`) mà không mang đủ dependency/bộ nạp để chạy theo cách trên. Với ứng dụng Spring Boot Web cần executable archive, dùng đầu ra của `bootJar`. Một module thư viện có thể được cấu hình tắt `bootJar` hoặc không có máy chủ Web; khi đó không áp đặt lệnh khởi động Web cho module đó.

Khác `bootRun`, JAR đã đóng gói không tự thay đổi khi sửa `src/main/java` hoặc `src/main/resources`. Muốn phát hành bản sửa, chạy lại `bootJar`, kiểm tra đúng tệp rồi khởi động lại tiến trình JAR mới.

## 6. Kiểm chứng ứng dụng đã chạy đúng

Sau mỗi cách khởi động, tìm dấu hiệu hoàn tất trong log, chẳng hạn thông báo khởi tạo Tomcat và `Started DemoApplication`. Các dòng log có thể khác theo phiên bản, cấu hình logging và thư viện Web; dòng **`Started ...` không đồng nghĩa mọi chức năng nghiệp vụ đều đã khỏe mạnh**.

Trong terminal thứ hai trên macOS/Linux:

```bash
curl -s http://localhost:8080/ping
```

Kết quả phần thân HTTP của chương trình minh họa:

```text
pong
```

Trên PowerShell:

```powershell
Invoke-RestMethod http://localhost:8080/ping
```

Kết quả tương ứng là `pong`. Khi đã dùng `--server.port=9090`, phải đổi URL thành `http://localhost:9090/ping`. Nếu phản hồi HTTP là 404, kiểm tra lại đường dẫn, cổng và controller; 404 khác với lỗi không kết nối được do tiến trình chưa chạy.

Muốn dừng ứng dụng chạy trực tiếp trong terminal, nhấn **Ctrl+C** và chờ tiến trình thoát. Với IDE, dùng Stop. Trước khi chạy bằng cách khác, hãy bảo đảm tiến trình cũ không còn chiếm cổng.

## 7. Cấu hình có giống nhau giữa ba cách chạy không?

Spring Boot dùng cùng cơ chế đọc cấu hình, nhưng **nguồn cấu hình được cung cấp** có thể khác. `application.properties`/`application.yml` đi cùng classpath; các tệp cấu hình ngoài, profile, đối số dòng lệnh, biến môi trường và tham số JVM có thể thay đổi kết quả khởi động.

Ví dụ bật profile `dev`:

- **IDE:** đặt Program arguments thành `--spring.profiles.active=dev`, hoặc cấu hình biến môi trường `SPRING_PROFILES_ACTIVE=dev`.
- **Gradle:** `./gradlew bootRun --args='--spring.profiles.active=dev'`.
- **JAR:** `java -jar build/libs/launch-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev`.

Khi có `application-dev.properties` trong `src/main/resources`, Spring Boot có thể nạp cấu hình theo profile đang hoạt động. Không tạo profile `dev` chỉ để chạy ứng dụng nếu dự án thực tế không cần; khi profile yêu cầu database, secret hoặc dịch vụ ngoài, phải cấp các phụ thuộc đó.

Tương tự, working directory và file ngoài không nhất thiết giống nhau. Ví dụ chuỗi đường dẫn tương đối `./config/settings.json` được giải theo thư mục làm việc của **tiến trình**; chạy từ IDE và chạy JAR ở thư mục khác có thể trỏ đến hai tệp khác nhau. Với hệ thống triển khai thực tế, nên khai báo rõ profile, biến môi trường, vị trí cấu hình và working directory, tránh phụ thuộc vào thiết lập riêng máy lập trình viên.

## 8. Bảng so sánh

| Tiêu chí | IDE Run/Debug | Gradle `bootRun` | Executable JAR + `java -jar` |
|---|---|---|---|
| Nguồn thực thi | Classpath IDE hoặc chạy qua Gradle theo cấu hình | Class/tài nguyên build + runtime dependency | Nội dung JAR đã đóng gói |
| Có cần tạo JAR trước? | Không | Không | Có, bằng `bootJar` |
| Phù hợp nhất | Lập trình, breakpoint | Chạy bằng lệnh, phát triển/tích hợp | Kiểm tra gói phát hành, triển khai |
| Sau khi sửa mã | Biên dịch/chạy lại theo IDE | Chạy lại tác vụ; biên dịch theo Gradle | Build lại JAR và chạy JAR mới |
| Cấu hình runtime | Run Configuration | `--args`, env, cấu hình Gradle | JVM options, env, application args |
| Điều kiện thường gặp | SDK và dependency IDE đúng | Wrapper, Gradle plugin, dependency đúng | JVM tương thích và executable JAR đúng |

Không có cách nào tự động là “đúng hơn” trong mọi tình huống. Điều quan trọng khi so sánh lỗi là dùng **cùng mã đã build, cùng Java, cùng profile, cùng tham số và cùng dịch vụ phụ thuộc**.

## 9. Lỗi phổ biến và cách lần theo nguyên nhân

| Triệu chứng | Kiểm tra và xử lý |
|---|---|
| `Task 'bootRun' not found` | Project đang gọi có áp dụng Spring Boot Gradle plugin không? Trong multi-project, gọi đúng `:module:bootRun`; kiểm tra danh sách task của project. |
| `Could not find or load main class` | Kiểm tra package, tên lớp, nguồn biên dịch và Main class của IDE. Với JAR, kiểm tra đã dùng `bootJar` và cấu hình lớp khởi động. |
| `no main manifest attribute` khi `java -jar` | Có thể đang chạy JAR thường hoặc tệp sai. Dùng đúng executable JAR do `bootJar` tạo. |
| `UnsupportedClassVersionError` | Java dùng để **chạy** cũ hơn phiên bản bytecode đã biên dịch. So sánh `java -version` ở terminal, JDK của IDE và toolchain Gradle. |
| `Port 8080 was already in use` | Có tiến trình khác chiếm cổng. Dừng tiến trình cũ hoặc chạy với `--server.port=9090`. |
| `Connection refused` ở `/ping` | Ứng dụng chưa chạy, đã thoát hoặc đang nghe ở cổng/host khác; kiểm tra log và URL. |
| HTTP 404 tại `/ping` | Server có thể đang chạy nhưng không có mapping này. Kiểm tra controller, đường dẫn, context path và cổng. |
| `ClassNotFoundException` / `NoClassDefFoundError` | Kiểm tra dependency runtime, nội dung JAR và đúng cấu hình build; đừng dùng JAR `-plain` để thay executable JAR. |
| Lỗi khởi tạo bean, database, thiếu cấu hình | Tìm **`Caused by:` đầu tiên có ý nghĩa** trong stack trace; kiểm tra profile, env, địa chỉ/credential dịch vụ và bean liên quan. |
| Tiến trình chạy rồi thoát ngay | Kiểm tra log lỗi; nếu là ứng dụng **không có Web server và không có tác vụ giữ tiến trình**, thoát sau khi hoàn tất khởi động có thể là bình thường. |

Một cách chẩn đoán nhất quán là: **(1)** xác định command và module đang chạy, **(2)** xác định Java/runtime arguments, **(3)** đọc lỗi gốc trong log, **(4)** kiểm tra cổng và profile, **(5)** chạy lại sau khi sửa đúng nguyên nhân. Không sửa nhiều yếu tố cùng lúc nếu chưa biết lỗi đến từ đâu.

## 10. Quy trình thực hành đề xuất

1. Chạy ứng dụng bằng IDE với cổng 8080; dùng `/ping` kiểm chứng và Debug tại `ping()`.
2. Dừng IDE, chuyển sang `./gradlew bootRun` (hoặc `.\gradlew.bat bootRun` trên Windows); kiểm tra kết quả `pong`. Thử chạy lại với cổng 9090 bằng `--args` và dùng đúng URL mới.
3. Dừng `bootRun`, thực hiện `bootJar`; quan sát tên executable JAR trong `build/libs`. Khởi động bằng `java -jar`, kiểm tra `/ping`.
4. Đổi giá trị trả về của controller từ `pong` thành `pong-v2`. Quan sát rằng **JAR cũ vẫn trả về `pong`**, rồi build lại JAR và xác minh bản mới trả `pong-v2`. Đây là bằng chứng trực tiếp về khác biệt giữa chạy từ mã đã biên dịch và chạy từ gói đã chốt.
5. Thử chủ động chiếm cổng 8080 bằng một phiên đang chạy rồi khởi động thêm một phiên ở cùng cổng; đọc lỗi, dừng phiên thừa hoặc chuyển cổng. Không để hai tiến trình giả vờ là một ứng dụng duy nhất.

**Điều cần ghi nhớ:** IDE giúp phát triển/gỡ lỗi, `bootRun` giúp chạy theo hệ thống build, còn `bootJar` + `java -jar` giúp kiểm tra chính gói phát hành. Cả ba vẫn phụ thuộc vào lớp khởi động, JVM, classpath/dependency và cấu hình Spring Boot của cùng ứng dụng.