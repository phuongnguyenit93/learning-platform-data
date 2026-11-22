# Chọn kiểu ứng dụng và tập dependency tối thiểu

Khi tạo dự án Spring Boot đầu tiên, hai quyết định cần đưa ra trước khi viết nghiệp vụ là **ứng dụng sẽ chạy theo kiểu nào** và **cần đưa những thư viện nào vào dự án**. Hai lựa chọn này liên quan trực tiếp đến nhau: một REST API cần thành phần xử lý HTTP; một chương trình xử lý tệp theo lô có thể không cần web server; một ứng dụng truy cập cơ sở dữ liệu chỉ cần driver và thư viện thao tác dữ liệu khi thực sự có yêu cầu đó.

Mục tiêu của bước khởi tạo là tạo được **ứng dụng nhỏ nhất đáp ứng chức năng đầu tiên**, có thể chạy và mở rộng có chủ đích. Bắt đầu với ít dependency giúp dễ đọc cấu trúc dự án, thấy được vai trò từng thành phần và dễ tìm nguyên nhân khi ứng dụng không hoạt động như mong đợi.

## 1. Xác định chức năng đầu tiên trước khi chọn công nghệ

Hãy mô tả kết quả tối thiểu mà chương trình cần tạo ra. Một vài cách mô tả rõ ràng:

- “Khi gửi `GET /hello`, máy chủ trả JSON chứa lời chào.”
- “Khi truy cập trang chủ, trình duyệt nhận một trang HTML do server tạo.”
- “Khi chạy chương trình, ứng dụng đọc tệp CSV, xử lý rồi kết thúc.”
- “Khi có sự kiện từ hệ thống khác, ứng dụng nhận và xử lý thông điệp.”
- “Khi client yêu cầu danh sách sản phẩm, ứng dụng đọc từ PostgreSQL và trả JSON.”

Từ kết quả đầu tiên, mới chọn kiến trúc chạy phù hợp. Tên “Spring Boot application” chỉ là phạm vi chung; Spring Boot hỗ trợ nhiều kiểu ứng dụng.

### Các kiểu ứng dụng thường gặp

| Kiểu ứng dụng | Khi nào phù hợp | Nhu cầu cơ bản | Lựa chọn Spring thường gặp |
|---|---|---|---|
| **REST API / HTTP backend** | Mobile app, SPA hoặc hệ thống khác gọi endpoint và nhận JSON | HTTP routing, serialization, web server | Spring MVC qua **Spring Web** |
| **Web tạo HTML trên server** | Giao diện được render bằng template Java phía server | HTTP, controller và template engine | **Spring Web** + **Thymeleaf** nếu dùng Thymeleaf |
| **Command-line / tác vụ đơn giản** | Chạy một tác vụ, nhập/xuất tệp rồi kết thúc | ApplicationContext, xử lý logic; không cần nhận HTTP | **Spring Boot** cơ bản + `CommandLineRunner` hoặc `ApplicationRunner` |
| **Xử lý job theo lô** | Job nhiều bước, cần quản lý trạng thái, retry hoặc restart | Khả năng tổ chức job và step | **Spring Batch** khi bài toán thật sự cần |
| **Reactive HTTP service** | Luồng bất đồng bộ, I/O không chặn với các thư viện tương thích | Reactive HTTP stack | **Spring Reactive Web / WebFlux** |
| **Consumer sự kiện / message** | Nhận message từ broker, không nhất thiết cung cấp endpoint | Client tương ứng broker và cơ chế listener | Dependency Kafka, AMQP... theo hệ thống thực tế |

Nếu bài học đầu tiên chỉ là “trả lời `GET /hello`”, chọn Spring MVC là lựa chọn dễ quan sát và giải thích. Chưa có lý do để thêm database, messaging, cache hoặc reactive stack.

**Phân biệt quan trọng:** một REST API không bắt buộc phải dùng WebFlux. Spring MVC cũng xử lý REST API rất tốt. Từ “REST” mô tả cách thiết kế giao tiếp HTTP; “MVC” và “WebFlux” là các mô hình lập trình web khác nhau.

## 2. Dependency là gì và vì sao Spring Boot dùng starter?

**Dependency** là thư viện mà dự án cần để biên dịch, chạy hoặc kiểm thử. Maven hay Gradle đọc khai báo dependency trong `pom.xml` hoặc `build.gradle` / `build.gradle.kts`, tải các artifact phù hợp và xây dựng tập thư viện cho từng giai đoạn.

Một dependency có thể kéo theo các dependency khác. Chẳng hạn, một starter web thường đem vào các thành phần phục vụ Spring MVC, JSON và web server nhúng. Đó là **transitive dependencies**: những thư viện phụ thuộc gián tiếp mà công cụ build giải quyết.

**Starter** là tập dependency được Spring Boot chuẩn bị cho một nhu cầu phổ biến. Thay vì tự ghép từng thành phần HTTP, ta bắt đầu từ starter đúng với bài toán. Spring Boot còn có cơ chế quản lý phiên bản tương thích giữa nhiều thư viện khi dự án dùng cấu hình dependency management phù hợp.

Ví dụ quen thuộc trong **Spring Boot 3.x**:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Dependency này cung cấp nền tảng thuận tiện để xây ứng dụng servlet Spring MVC, nhưng **không tự tạo endpoint nghiệp vụ**. Endpoint phải được khai báo qua code hoặc cấu hình tương ứng.

> **Lưu ý về phiên bản:** tên starter có thể thay đổi giữa các phiên bản Spring Boot lớn. Ví dụ, các dự án Spring Boot 4.x có thể dùng `spring-boot-starter-webmvc` cho stack Spring MVC. Khi bắt đầu dự án, hãy ưu tiên tên dependency và tập cấu hình mà **Spring Initializr của phiên bản đã chọn** sinh ra; các đoạn build minh họa ở dưới dùng quy ước Spring Boot 3.x.

### Dependency có thể thay đổi hành vi khởi động

Không nên xem dependency như một danh sách “thư viện để sau này dùng”. Spring Boot áp dụng **auto-configuration** dựa trên classpath, bean và property hiện có. Vì vậy:

- Thêm web starter có thể khiến ứng dụng khởi tạo HTTP server nhúng.
- Thêm starter Data JPA và driver liên quan có thể kích hoạt quá trình tạo bean kết nối dữ liệu, tùy điều kiện.
- Thêm Spring Security có thể khiến các HTTP endpoint được bảo vệ theo cấu hình mặc định, dù controller không đổi.
- Thêm WebFlux tạo ra các thành phần reactive; nếu đồng thời có Spring MVC, Spring Boot thường ưu tiên kiểu ứng dụng servlet MVC theo mặc định.

Dependency là một phần của quyết định kiến trúc. Chỉ thêm khi hiểu nhu cầu và ảnh hưởng của nó.

## 3. Quy trình chọn: bắt đầu từ luồng chạy chính

Có thể dùng sơ đồ quyết định ngắn sau cho dự án đầu tiên:

~~~text
Ứng dụng phải cung cấp HTTP endpoint?
│
├── Không
│   ├── Chỉ chạy logic khi khởi động
│   │   └── Spring Boot cơ bản + CommandLineRunner
│   ├── Cần job nhiều bước, restart/retry theo job
│   │   └── Xem xét Spring Batch
│   └── Nhận message từ broker
│       └── Thêm client/starter đúng broker khi dùng
│
└── Có
    ├── Đã có yêu cầu reactive cụ thể?
    │   ├── Có -> Xem xét WebFlux và cả chuỗi I/O reactive
    │   └── Chưa -> Chọn Spring Web (Spring MVC)
    │
    ├── Cần server render HTML?
    │   └── Thêm Thymeleaf hoặc template engine tương ứng
    │
    └── Có lưu dữ liệu trong cơ sở dữ liệu?
        ├── Chưa -> Chưa thêm dependency persistence
        └── Có -> Chọn JDBC / JPA / client phù hợp
~~~

Sơ đồ thể hiện **thứ tự hỏi**, không phải giới hạn tuyệt đối. Một ứng dụng thực tế có thể kết hợp HTTP, job và message listener. Với dự án học đầu tiên, hãy chọn một luồng hoạt động dễ chạy thử rồi thêm khả năng khi xuất hiện yêu cầu rõ ràng.

### Spring MVC hay WebFlux?

| Tiêu chí | Spring MVC | Spring WebFlux |
|---|---|---|
| Kiểu lập trình phổ biến | Controller trả đối tượng, `ResponseEntity` hoặc kiểu tương tự | Controller/handler thường dùng `Mono`, `Flux` và Reactor |
| Mô hình xử lý phổ biến | Servlet, xử lý request theo mô hình dễ tiếp cận | Reactive, hướng đến I/O bất đồng bộ và khả năng backpressure |
| Khi mới học REST API | Thường là lựa chọn đơn giản | Chỉ nên ưu tiên khi đang học hoặc cần reactive |
| Tích hợp persistence truyền thống | Hợp với JDBC, JPA theo mô hình blocking | Nên xem xét toàn bộ chuỗi I/O; dùng blocking tùy tiện có thể làm mất lợi ích |
| Thư viện cần chọn | Spring Web / Spring MVC | Spring Reactive Web / WebFlux |

WebFlux không mặc nhiên nhanh hơn Spring MVC trong mọi bài toán. Hiệu năng phụ thuộc tải, cách xử lý I/O, thiết kế dữ liệu và môi trường. Chọn reactive chỉ vì “nghe hiện đại hơn” làm tăng số khái niệm cần học và độ phức tạp khi debug.

### Backend API có cần template engine?

Nếu frontend React, Vue, ứng dụng di động hoặc client khác nhận JSON, **không cần Thymeleaf** chỉ để làm REST API. Nếu muốn Java server tạo trang HTML từ template, thêm công cụ render như Thymeleaf mới có ý nghĩa. Hai phương án có thể tồn tại chung nhưng dự án đầu tiên nên có một mục tiêu chính.

## 4. Ví dụ lựa chọn tối thiểu: REST API “Hello”

Giả sử yêu cầu đầu tiên:

> Tạo chương trình Spring Boot chạy tại máy local. Khi gửi HTTP GET đến `/hello`, ứng dụng trả JSON `{"message":"Hello Spring Boot"}`.

Từ yêu cầu này suy ra:

1. Cần tiếp nhận HTTP và ánh xạ đường dẫn đến controller.
2. Cần chuyển đối tượng Java thành JSON.
3. Cần một web server để client gửi request.
4. **Chưa cần database, bảo mật nâng cao, queue hay template HTML**.

Chọn loại ứng dụng **Spring Web (MVC)**. Với Spring Boot 3.x, dependency chính là `spring-boot-starter-web`. Dependency kiểm thử theo bộ khởi tạo thông dụng là `spring-boot-starter-test` với scope `test`; thư viện này dành cho kiểm thử, không phải chức năng phục vụ HTTP ở production.

### 4.1. Tạo cấu hình dự án bằng Spring Initializr

Trong giao diện Spring Initializr:

| Mục | Lựa chọn minh họa | Ý nghĩa |
|---|---|---|
| Project | Maven | Công cụ build và quản lý dependency |
| Language | Java | Ngôn ngữ viết ứng dụng |
| Spring Boot | Phiên bản ổn định, được hỗ trợ và tương thích môi trường | Quyết định dòng framework và tập thư viện được quản lý |
| Group | `com.example` | Không gian tên tổ chức |
| Artifact | `hello-api` | Tên artifact; thường ảnh hưởng tên dự án |
| Name | `hello-api` | Tên dự án |
| Packaging | Jar | Đóng gói ứng dụng có thể chạy |
| Java | Phiên bản JDK tương thích Spring Boot đã chọn | Phiên bản dùng để build và chạy |
| Dependencies | **Spring Web** | Cung cấp Spring MVC và thành phần cần thiết |

Với Spring Boot 3.x, Java 17 là mốc nền tảng tối thiểu. Khi chọn phiên bản mới hơn, hãy dùng JDK mà phiên bản Spring Boot đó hỗ trợ và bảo đảm JDK triển khai không cũ hơn bytecode của bản build. Không cần chọn phiên bản Java mới nhất nếu máy học hoặc môi trường chạy chưa hỗ trợ.

Nếu mục tiêu là học Gradle, chọn Gradle vẫn phù hợp; Java code gần như không đổi, chỉ cú pháp file build và lệnh build khác. Chọn **một** công cụ build để hiểu rõ quy trình thay vì duy trì song song Maven và Gradle cho cùng ví dụ.

Sau khi tải dự án từ Initializr và giải nén, cấu trúc thông dụng:

~~~text
hello-api/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── ...
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/helloapi/
    │   │       └── HelloApiApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── ...
~~~

Tùy phiên bản và tùy chọn generator, tên file hay đường dẫn cụ thể có thể khác. File `pom.xml` hoặc `build.gradle(.kts)` mới là nơi mô tả build và dependency; thư mục `src/main/java` chứa code chính, còn `src/main/resources` chứa tài nguyên và cấu hình được đóng gói.

### 4.2. Đọc phần dependency trong dự án Maven

Với ví dụ Spring Boot 3.x, phần `dependencies` trong `pom.xml` có thể trông như sau:

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

Đây là **đoạn trích** của `pom.xml`; bản hoàn chỉnh do Initializr sinh ra còn chứa thông tin dự án, cơ chế quản lý phiên bản Spring Boot và plugin build thích hợp. Không cần tự gắn một số phiên bản vào từng starter khi dự án đang được Spring Boot dependency management quản lý.

Nếu tạo dự án Gradle Kotlin DSL trên Spring Boot 3.x, hai khai báo tương đương về ý định có dạng:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Khi sử dụng Spring Boot 4.x hoặc phiên bản khác, **đọc dependency thực tế generator tạo ra** thay vì sao chép nguyên tên starter từ ví dụ dành cho Boot 3.x.

### 4.3. Viết mã nguồn nhỏ nhất

Lớp khởi động:

~~~java
package com.example.helloapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HelloApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(HelloApiApplication.class, args);
    }
}
~~~

Controller:

~~~java
package com.example.helloapi;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello Spring Boot");
    }
}
~~~

Đặt `HelloController` trong cùng package hoặc package con của `HelloApiApplication`. Đây là vị trí phù hợp với cơ chế component scan mặc định của `@SpringBootApplication`.

Trong ví dụ:

- `@SpringBootApplication` xác định lớp cấu hình/khởi động và bật những cơ chế quan trọng của Spring Boot.
- `@RestController` khai báo bean xử lý HTTP và ghi kết quả trả về thành response body.
- `@GetMapping("/hello")` ánh xạ HTTP GET đến `/hello`.
- `Map.of(...)` là logic của chính ứng dụng; hệ thống chuyển đổi HTTP message phù hợp biến dữ liệu thành JSON.

### 4.4. Chạy ứng dụng và quan sát hành vi

Từ thư mục gốc dự án Maven, lệnh thường dùng trên macOS/Linux:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Nếu dùng Gradle, lệnh tương ứng thông thường là `./gradlew bootRun` (macOS/Linux) hoặc `.\gradlew.bat bootRun` (Windows).

Khi ứng dụng đã khởi động, dùng trình duyệt hoặc client HTTP:

~~~bash
curl http://localhost:8080/hello
~~~

Kết quả dự kiến:

~~~json
{"message":"Hello Spring Boot"}
~~~

`8080` là cổng mặc định phổ biến khi chạy servlet web Spring Boot mà chưa cấu hình cổng khác. Nếu cổng đã bị ứng dụng khác chiếm hoặc được đổi bằng property, địa chỉ thực tế cũng thay đổi.

Ví dụ này cho thấy rõ sự phân chia:

| Thành phần | Vai trò trong kết quả |
|---|---|
| `HelloController` | Xác định `/hello` và dữ liệu trả về |
| Spring MVC / JSON từ web starter | Tiếp nhận, định tuyến HTTP và biểu diễn JSON |
| Spring Boot và cấu hình chạy | Tạo application context, khởi tạo server ở cổng tương ứng |
| JVM và máy tính | Thực thi ứng dụng; cung cấp cổng mạng, CPU, RAM và môi trường |

## 5. Nếu bài toán đầu tiên không cần HTTP

Giả sử yêu cầu thay đổi thành “khi khởi chạy, in ra một dòng rồi kết thúc”. Trong trường hợp này, **web server là phần thừa**. Dự án Spring Boot có thể dùng starter cơ bản và khai báo một `CommandLineRunner`:

~~~java
package com.example.job;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JobApplication {

    public static void main(String[] args) {
        SpringApplication.run(JobApplication.class, args);
    }

    @Bean
    CommandLineRunner runJob() {
        return args -> System.out.println("Đã chạy tác vụ đầu tiên");
    }
}
~~~

Với dự án Maven Spring Boot 3.x, dependency nền tảng có thể là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
</dependency>
~~~

Không cần `spring-boot-starter-web` để dùng `@SpringBootApplication` hay `CommandLineRunner`. Nếu không có web stack hoặc các tác vụ giữ tiến trình hoạt động, ứng dụng có thể hoàn tất công việc rồi thoát, thay vì tiếp tục lắng nghe request.

Nếu dự án đã có web starter nhưng muốn ép kiểu chạy không có web server, Spring Boot cũng hỗ trợ property:

~~~properties
spring.main.web-application-type=none
~~~

Tuy nhiên, khi tạo dự án mới mà không có yêu cầu HTTP, cách rõ ràng hơn là **không thêm web dependency từ đầu**. Tránh biến cấu hình thành cách che giấu những dependency không cần thiết.

Cũng không nên đồng nhất “chạy một đoạn code khi startup” với “phải dùng Spring Batch”. `CommandLineRunner` hợp với ví dụ ngắn hoặc tác vụ đơn giản; Spring Batch phát huy vai trò ở các job có cấu trúc, quản lý trạng thái bước xử lý, kiểm soát restart và nhu cầu vận hành nghiêm túc.

## 6. Khi nào thêm dependency tiếp theo?

Khi chức năng đầu tiên chạy được, mỗi yêu cầu mới dẫn đến một quyết định dependency mới. Bảng sau là các lựa chọn thường gặp trong hệ sinh thái Spring Boot 3.x; tên artifact có thể thay đổi theo dòng Spring Boot, vì vậy hãy kiểm tra thư viện được Initializr hoặc tài liệu phiên bản dự án cung cấp.

| Yêu cầu thực tế | Dependency/starter thường gặp | Chỉ thêm khi... |
|---|---|---|
| Nhận HTTP, trả JSON | `spring-boot-starter-web` (Boot 3.x) | Ứng dụng cung cấp HTTP endpoint theo MVC |
| Render trang HTML server-side | `spring-boot-starter-thymeleaf` | Dùng Thymeleaf cho view HTML |
| Kiểm tra dữ liệu đầu vào qua Bean Validation | `spring-boot-starter-validation` | Có ràng buộc như `@NotBlank`, `@Size` và cơ chế validate |
| Viết SQL trực tiếp hoặc dùng `JdbcTemplate` | `spring-boot-starter-jdbc` | Cần tương tác database theo JDBC |
| ORM/repository với JPA | `spring-boot-starter-data-jpa` | Có nhu cầu entity, repository, transaction/ORM |
| Kết nối PostgreSQL | `org.postgresql:postgresql` | Thực tế sử dụng PostgreSQL với JDBC |
| Dùng database in-memory cho bài học/test | `com.h2database:h2` | Cần database thử nghiệm phù hợp mục đích |
| Bảo vệ API bằng Spring Security | `spring-boot-starter-security` | Sẵn sàng cấu hình authentication/authorization |
| Theo dõi health và các thông tin vận hành | `spring-boot-starter-actuator` | Có yêu cầu quan sát/giám sát phù hợp |
| Kiểm thử ứng dụng | `spring-boot-starter-test` (Boot 3.x) | Cần thư viện test; thường đã được generator thêm với scope test |
| Tiện ích phát triển như tự khởi động lại | `spring-boot-devtools` | Cần tăng tiện lợi khi phát triển; không phải dependency nghiệp vụ |

Một số ví dụ chọn theo yêu cầu:

**Ví dụ A — CRUD danh sách sách với PostgreSQL.** Khi đã cần lưu dữ liệu, lựa chọn có thể gồm Spring Web + Spring Data JPA + PostgreSQL driver + Validation nếu có ràng buộc đầu vào. Khi chỉ mới viết endpoint `/hello`, chưa có lý do thêm cả JPA và driver.

**Ví dụ B — REST API chỉ gọi một dịch vụ HTTP khác.** Có thể cần web starter để nhận request và một HTTP client thích hợp để gọi ra ngoài. Không cần thêm JPA nếu không lưu dữ liệu trong DB.

**Ví dụ C — Hiển thị danh sách sản phẩm bằng template.** Có thể dùng Spring Web + Thymeleaf; database chỉ được thêm khi sản phẩm cần đọc từ nguồn lưu trữ thực.

**Ví dụ D — Chạy job nhập CSV.** Có thể bắt đầu với Spring Boot cơ bản và thư viện xử lý CSV nếu cần. Chỉ dùng Spring Batch khi bài toán có đặc điểm batch đáng kể.

### JDBC, JPA và driver khác nhau thế nào?

Nếu chọn database, cần tách ba khái niệm:

- **JDBC** là API và cơ chế truy cập database quan hệ; trong Spring, starter JDBC cung cấp tiện ích như `JdbcTemplate`.
- **JPA** là đặc tả làm việc với entity/ORM; Spring Data JPA xây dựng thêm lớp repository và tích hợp JPA provider. Dùng JPA không có nghĩa không cần kết nối JDBC ở phía dưới.
- **Driver** là thư viện giao tiếp với hệ quản trị database cụ thể như PostgreSQL. Starter JPA hoặc JDBC không thay thế driver tương ứng.

Hơn nữa, **dependency không tạo hộ database bên ngoài**. Nếu cấu hình trỏ đến PostgreSQL, server PostgreSQL phải tồn tại, reachable qua mạng, có tài khoản và quyền thích hợp. Thêm database starter khi chưa có cấu hình phù hợp có thể khiến ứng dụng lỗi startup vì auto-configuration đang cố tạo các thành phần truy cập dữ liệu.

## 7. Thêm dependency có tác dụng phụ: ví dụ Spring Security

Giả sử một REST API trả dữ liệu công khai ở `/hello`. Sau đó ta thêm `spring-boot-starter-security` chỉ vì muốn “sẵn sàng bảo mật”. Spring Boot có thể áp dụng cấu hình bảo mật mặc định và yêu cầu xác thực cho các endpoint, dù code controller không hề thay đổi.

Điều này không phải lỗi ngẫu nhiên. Khi xuất hiện các lớp thư viện mới trên classpath, điều kiện auto-configuration có thể khác đi. Khi bổ sung Security cần thiết kế rõ:

- Endpoint nào công khai, endpoint nào yêu cầu người dùng đăng nhập.
- Sử dụng cơ chế xác thực nào, ví dụ session, HTTP Basic trong bài học đơn giản hoặc token cho API theo yêu cầu.
- Áp dụng quyền truy cập và hành vi trả lỗi ra sao.
- Cấu hình chuỗi lọc bảo mật `SecurityFilterChain` và quản lý thông tin xác thực thế nào.

Bài học thực tế: một dependency thêm vào phải có **lý do cụ thể** và người viết phải hiểu ít nhất hành vi hệ thống thay đổi ở mức nào. Điều này đặc biệt đúng với các starter web, data, security và messaging.

## 8. Tối thiểu không đồng nghĩa với bỏ hạ tầng hỗ trợ cần thiết

“Tối thiểu” là **chỉ có những gì chức năng hiện tại cần**, không có nghĩa loại bỏ mọi cơ chế hỗ trợ phát triển hoặc kiểm thử.

Ví dụ, với Spring MVC, thường hợp lý khi giữ dependency test do Initializr cung cấp, dù test không phải tính năng HTTP ở production. Tùy phiên bản Spring Boot, tên các starter test có thể được chia theo mô-đun; dùng đúng lựa chọn mà generator sinh ra. Phạm vi `test` giúp phân biệt dependency chỉ phục vụ kiểm thử với thư viện chạy ở môi trường production.

Mặt khác, không cần thêm hàng loạt thư viện “để dành”:

- **Lombok** giảm code lặp trong một số trường hợp nhưng đưa thêm annotation processing và quy ước mới; người mới có thể dùng constructor/getter Java trực tiếp để hiểu cấu trúc.
- **DevTools** tăng tiện lợi cho vòng lặp phát triển nhưng không phải yêu cầu để ứng dụng thực thi đúng; chỉ thêm nếu có nhu cầu.
- **Actuator** hữu ích cho health/metrics và vận hành, nhưng không phải điều kiện để `GET /hello` hoạt động.
- **H2** hữu ích khi cần luyện tập dữ liệu nhanh; không có lý do nếu ứng dụng chưa dùng database.
- **Swagger/OpenAPI UI** hữu ích khi có nhiều endpoint cần tài liệu; không cần cho một endpoint khởi đầu.

Một thư viện không sử dụng có thể làm đồ thị dependency lớn hơn, thời gian xử lý build tăng, tạo thêm bề mặt cập nhật bảo mật và khiến kết quả auto-configuration khó hiểu hơn.

## 9. Chọn phiên bản và phạm vi dependency đúng ngay từ đầu

### Dùng cơ chế quản lý phiên bản của Spring Boot

Trong Maven, Spring Boot thường cung cấp parent POM hoặc BOM để quản lý bộ phiên bản dependency. Trong Gradle, cấu hình plugin và dependency management tương ứng giữ vai trò tương tự. Các file Initializr sinh ra đã đặt nền tảng cho việc này.

Với các starter được quản lý, thông thường không cần tự ghi `<version>` cho từng dependency. Việc tự chốt phiên bản thư viện không tương thích có thể khiến dự án biên dịch lỗi hoặc phát sinh lỗi runtime như `NoSuchMethodError`.

Đối với dự án đầu tiên:

1. Chọn phiên bản Spring Boot đang được hỗ trợ, tương thích với Java và môi trường sử dụng.
2. Để Initializr sinh ra cấu hình Maven/Gradle đồng bộ với phiên bản đó.
3. Dùng tên starter và dependency được khuyến nghị cho chính phiên bản đang chạy.
4. Chỉ nâng hoặc thay phiên bản thư viện riêng khi có lý do và hiểu tương thích.
5. Khi chuyển phiên bản Spring Boot lớn, đọc thay đổi tương thích và tên starter thay vì giả định mọi artifact đều giữ nguyên.

### Phân biệt phạm vi sử dụng

Ví dụ một dự án Maven Spring Boot 3.x có thể khai báo:

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

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Đoạn trích trên **không phải dependency tối thiểu của Hello API**; phần PostgreSQL minh họa khi dự án đã có chức năng cần database. `scope=runtime` thường phù hợp với JDBC driver vì mã nghiệp vụ làm việc qua API JDBC/JPA trong lúc biên dịch. `scope=test` dành cho thư viện được dùng trong kiểm thử. Phạm vi dependency ảnh hưởng classpath và artifact cuối, vì vậy không nên đổi scope tùy tiện chỉ để làm hết lỗi thiếu lớp.

Trong Gradle cũng có phân biệt `implementation`, `runtimeOnly`, `testImplementation` và các cấu hình khác. Với dự án sinh bởi Initializr, chọn định nghĩa dependency theo đúng mục đích đã được generator gợi ý.

## 10. Các sai lầm thường gặp khi bắt đầu

| Tình huống | Nguyên nhân có thể liên quan đến lựa chọn ban đầu | Hướng điều chỉnh |
|---|---|---|
| Thêm `@RestController` nhưng ứng dụng không phục vụ HTTP | Không có web stack phù hợp, hoặc controller không được nhận diện | Chọn Spring Web cho MVC, kiểm tra package scan và mapping |
| API trả `401 Unauthorized` sau khi thêm Security | Auto-configuration bảo vệ endpoint | Cấu hình bảo mật theo yêu cầu thay vì loại bỏ ngẫu nhiên logic khác |
| Ứng dụng cố kết nối DB rồi lỗi dù chưa dùng DB | Thêm Data JPA/JDBC và các điều kiện khởi tạo dữ liệu được kích hoạt | Gỡ dependency chưa cần hoặc cung cấp cấu hình DB đúng khi thật sự cần |
| Chọn WebFlux nhưng phần lớn code dùng JDBC blocking | Chuỗi I/O không theo mô hình reactive | Cân nhắc MVC, hoặc thiết kế lại I/O reactive khi có yêu cầu |
| Thêm `Spring Data REST` chỉ để có một REST API | Nhầm tính năng tạo REST từ repository với Spring Web nói chung | Bắt đầu bằng controller MVC thông thường |
| Dự án có cả MVC và WebFlux mà hành vi khác dự đoán | Hai web stack cùng có mặt, kiểu ứng dụng được chọn theo quy tắc Spring Boot | Chọn rõ stack chính, chỉ trộn khi hiểu mục đích |
| Không nhận ra code sửa có hiệu lực | Đang chạy artifact cũ hoặc sai project | Xác định build đang chạy; build lại đúng project |
| Runtime lỗi thiếu lớp hoặc phương thức | Scope dependency hoặc phiên bản không phù hợp | Xem dependency runtime và cách quản lý phiên bản |
| Build chạy trên máy mình nhưng không chạy máy khác | JVM/JDK hoặc điều kiện môi trường khác nhau | Kiểm tra phiên bản Java, cấu hình và phụ thuộc ngoài |

Đừng mặc định rằng mọi lỗi startup là do thiếu dependency. Một số lỗi đến từ sai tên property, thiếu biến môi trường, lỗi mã, cổng bị chiếm hoặc dịch vụ ngoài không có sẵn. Việc chọn dependency ít và đúng giúp thu hẹp phạm vi điều tra.

## 11. Tự luyện tập bằng ba bài toán

Hãy thử quyết định kiểu ứng dụng và dependency **trước khi mở Initializr**, sau đó so với yêu cầu thực tế.

### Bài toán 1: API trả thông tin khóa học tĩnh

Yêu cầu: `GET /courses` trả về JSON gồm ba khóa học hard-code trong Java; không lưu database.

Lựa chọn hợp lý: **Spring Web (MVC)**. Cần controller trả về danh sách object hoặc record; JSON conversion đến từ web stack. Không cần Data JPA, JDBC, H2 hay PostgreSQL vì dữ liệu đang có sẵn trong bộ nhớ.

### Bài toán 2: Công cụ tính tổng số dòng trong CSV

Yêu cầu: nhận đường dẫn file khi chạy, đếm số bản ghi, in kết quả rồi kết thúc; không nhận HTTP.

Lựa chọn hợp lý: **Spring Boot cơ bản** cùng `CommandLineRunner` hoặc `ApplicationRunner`. Có thể dùng Java standard library để đọc file nếu cấu trúc CSV đơn giản. Chỉ thêm thư viện CSV chuyên dụng khi định dạng hoặc quy tắc parse thực sự cần; không thêm web server.

### Bài toán 3: API tạo và đọc đơn hàng từ PostgreSQL

Yêu cầu: `POST /orders` ghi đơn hàng và `GET /orders/{id}` đọc lại dữ liệu từ PostgreSQL.

Lựa chọn hợp lý thường gặp: **Spring Web + Spring Data JPA + PostgreSQL driver**, có thể thêm Validation nếu muốn kiểm tra đầu vào bằng Bean Validation. Ngoài khai báo dependency, cần có server PostgreSQL, connection URL, credentials, bảng/schema phù hợp và code entity/repository/service/controller. Nếu nhóm muốn viết SQL tường minh, có thể chọn JDBC thay cho JPA tùy nhu cầu.

Ba bài toán cho cùng một kết luận thực hành: **dependency được suy ra từ hành vi cần có**, không phải từ danh sách những công nghệ Spring Boot hỗ trợ.

## 12. Kiểm tra quyết định trước khi bắt tay vào tính năng lớn hơn

Trước khi tiếp tục mở rộng dự án Spring Boot đầu tiên, người học nên trả lời được:

- Ứng dụng này xử lý HTTP, chạy tác vụ độc lập hay nhận sự kiện? Có cần web server không?
- Vì sao đã chọn Spring MVC hoặc WebFlux? Có nhu cầu kỹ thuật nào yêu cầu reactive không?
- Mỗi dependency khai báo phục vụ chức năng cụ thể nào?
- Những starter nào có thể thay đổi auto-configuration và cách ứng dụng khởi động?
- Có cần database ngay bây giờ không? Nếu có, đang dùng JDBC hay JPA và driver nào?
- Có đang dùng phiên bản Spring Boot, JDK và tên starter tương thích với nhau không?
- Phần nào chỉ phục vụ test hoặc phát triển, phần nào cần có ở runtime?

Một điểm khởi đầu tốt cho REST API đơn giản là **Java + Spring Boot + một web starter phù hợp + cấu hình build/test do Initializr sinh ra**. Từ đó, thêm dependency khi yêu cầu mới thực sự xuất hiện và quan sát sự thay đổi tương ứng trong cấu hình cũng như hành vi khởi động. Cách làm này giúp mỗi bước của dự án đầu tiên trở nên dễ hiểu, có thể giải thích và thuận tiện để mở rộng sau này.
