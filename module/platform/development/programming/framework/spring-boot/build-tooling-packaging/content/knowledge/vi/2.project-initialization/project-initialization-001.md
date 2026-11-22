# Tạo dự án Spring Boot với Spring Initializr: chọn Java, phiên bản Spring Boot và công cụ build

## 1. Mục tiêu bài học

Sau bài này, bạn có thể tự tạo một dự án Spring Boot từ https://start.spring.io, giải thích được từng lựa chọn quan trọng trong màn hình khởi tạo, chọn bộ ba **phiên bản Java – phiên bản Spring Boot – công cụ build** tương thích, mở dự án trong IDE, chạy thử và xác định nguyên nhân của những lỗi cấu hình ban đầu.

**Spring Initializr** là công cụ sinh bộ khung dự án. Nó tạo sẵn cấu trúc thư mục, lớp khởi động Spring Boot, tệp cấu hình, mô tả dependencies và script Wrapper cho công cụ build. Initializr **không** thay bạn cài JDK, thiết lập môi trường chạy, thiết kế nghiệp vụ hay kiểm thử tính tương thích của mọi thư viện bên ngoài.

Ba lựa chọn dễ bị nhầm lẫn:

| Lựa chọn | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| **Language** | Ngôn ngữ nguồn của ứng dụng: Java, Kotlin hoặc Groovy | Chọn **Java** để mã nguồn là `.java` |
| **Java** | Mức phiên bản Java của dự án: bytecode/API và cấu hình biên dịch do công cụ build sinh ra | Chọn **21**, dùng JDK phù hợp để build/chạy |
| **Spring Boot** | Dòng phát hành framework và hệ sinh thái dependencies/plugin tương ứng | Chọn bản **stable/GA** tương thích yêu cầu |
| **Project** | Hệ thống quản lý phụ thuộc và vòng đời build | **Maven**, **Gradle – Groovy** hoặc **Gradle – Kotlin** |

Không nhầm mục **Java** (phiên bản) với **Language = Java** (ngôn ngữ), và không nhầm **Spring Boot version** với **JDK version**.

## 2. Chọn phiên bản Java và Spring Boot cho đúng

### 2.1. Phân biệt JDK, Java của dự án và JVM đang chạy

- **JDK** là bộ công cụ chứa `javac`, runtime Java và các công cụ phát triển. Cần JDK để biên dịch dự án.
- **Java** trong Initializr giúp bộ khung sinh cấu hình cấp độ ngôn ngữ/toolchain tương ứng. Chọn Java 21 không tự cài JDK 21 trên máy.
- **JDK mà Maven/Gradle sử dụng** có thể khác JDK đang hiển thị trong IDE hoặc ở lệnh `java -version`. Với Gradle, toolchain dùng để biên dịch cũng có thể khác JVM chạy Gradle.

Kiểm tra trước khi tạo/chạy dự án:

~~~bash
java -version
javac -version
~~~

Trong IDE, kiểm tra cả **Project SDK/JDK** và **Gradle JVM** hoặc **Maven Runner JRE**. Trên máy có nhiều JDK, kiểm tra `JAVA_HOME` và đường dẫn `java`/`javac` thực sự được gọi.

### 2.2. Kiểm tra tương thích trước khi bấm Generate

Các dòng **Spring Boot 3.x và 4.x yêu cầu tối thiểu Java 17**; Java 21 hoặc 25 là những lựa chọn LTS thường đáng cân nhắc nếu hệ thống, plugin và thư viện của bạn hỗ trợ. Spring Boot 4.x dùng Spring Framework 7 và nền Jakarta EE mới hơn dòng 3.x, nên chọn dòng framework còn phụ thuộc thư viện và hệ thống triển khai. Không mặc định một project cũ sẽ nâng cấp lên Boot 4 mà không cần kiểm tra.

Với Spring Boot 4.x, tài liệu chính thức nêu hỗ trợ Maven từ 3.6.3 và Gradle 8.14+ (nhánh 8.x) hoặc 9.x. Giới hạn có thể thay đổi ở những nhánh/phát hành khác: **hãy xem yêu cầu hệ thống của đúng phiên bản Boot trước khi kết hợp JDK và Gradle**. Một bản Gradle cũ có thể không chạy được trên JDK mới, ngay cả khi Spring Boot có thể chạy trên JDK đó.

Khi chọn Spring Boot trong Initializr:

1. Ưu tiên bản **ổn định (GA/release)** được hỗ trợ và phù hợp yêu cầu dự án.
2. Các bản **SNAPSHOT**, **M** (milestone) hoặc **RC** nhằm thử nghiệm tính năng sắp phát hành, thường không phải lựa chọn khởi đầu cho dự án thông thường.
3. Kiểm tra tương thích với Java, Spring Cloud (nếu dùng), starter và các thư viện của hệ thống. Không chọn phiên bản chỉ vì số lớn nhất.
4. Nếu dự án thuộc một codebase/team có sẵn, dùng dòng phiên bản đã được team phê duyệt; giữ đồng bộ giữa môi trường phát triển, CI và production.

**Nguyên tắc:** Spring Initializr giúp tạo bộ khung với các phiên bản có thể chọn tại thời điểm truy cập, nhưng vẫn cần xác nhận rằng máy build, JDK, plugin và dependencies thực tế tương thích.

## 3. Chọn Maven hay Gradle

Maven và Gradle đều có thể tải thư viện, biên dịch, chạy test, đóng gói và tạo ứng dụng Spring Boot chạy được. **Chỉ chọn một** hệ thống build cho một project mới, trừ khi có yêu cầu duy trì đa build riêng.

| Tiêu chí | Maven | Gradle |
| --- | --- | --- |
| File build chủ đạo | `pom.xml` (XML) | `build.gradle` (Groovy DSL) hoặc `build.gradle.kts` (Kotlin DSL) |
| Cách tổ chức | Vòng đời build theo quy ước khá rõ ràng, cấu hình khai báo | Task graph linh hoạt, DSL cho phép cấu hình/phần mở rộng đa dạng |
| Khởi đầu cho người học | Dễ tra cứu cấu trúc XML và lệnh chuẩn | Phù hợp khi muốn học Gradle, Kotlin DSL/Groovy hoặc dự án team đã dùng |
| Chạy Spring Boot | `spring-boot:run` | `bootRun` |
| Đóng gói executable JAR | `package` với Spring Boot Maven plugin trong project Initializr | `bootJar` với Spring Boot Gradle plugin |
| Wrapper đi kèm | `mvnw`, `mvnw.cmd`, `.mvn/wrapper/` | `gradlew`, `gradlew.bat`, `gradle/wrapper/` |

**Gradle – Groovy** và **Gradle – Kotlin** khác nhau ở cú pháp tệp cấu hình build, **không** quyết định ứng dụng phải viết bằng Groovy/Kotlin. Bạn có thể chọn **Language = Java** cùng với **Gradle – Kotlin**. Nếu mới học và không có quy ước team, **Maven + Java** là lựa chọn dễ theo dõi; nếu dự án lớn đã dùng Gradle, chọn đúng DSL đang được sử dụng để giảm chi phí bảo trì.

Các script **Wrapper** cho phép chạy công cụ build với phiên bản mà dự án khóa, không nhất thiết cài Maven/Gradle toàn cục. Lần đầu chạy, Wrapper có thể cần tải bản phân phối và dependencies qua mạng; **JDK vẫn phải khả dụng**.

## 4. Thao tác tạo dự án trên Spring Initializr

Mở **https://start.spring.io**. Các nhãn có thể thay đổi nhẹ giữa phiên bản giao diện, nhưng ý nghĩa các trường vẫn tương tự.

**Bước 1 — Project:** Chọn **Maven** cho ví dụ trong bài. Nếu muốn dùng Gradle, chọn **Gradle – Groovy** hoặc **Gradle – Kotlin** và sử dụng bộ lệnh Gradle ở phần sau.

**Bước 2 — Language:** Chọn **Java**. Đây là lựa chọn ngôn ngữ cho mã nguồn Spring Boot được sinh.

**Bước 3 — Spring Boot:** Chọn bản ổn định tương thích với JDK và môi trường triển khai. Khi học theo một khóa học hoặc làm trong team, dùng đúng dòng Boot mà bài học/team quy định, vì starter và API có thể thay đổi giữa các major version.

**Bước 4 — Project Metadata:** Có thể cấu hình như bảng ví dụ:

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Group | `com.example` | Nhóm định danh, thường theo tên miền đảo ngược |
| Artifact | `initializr-demo` | Định danh module/artifact, thường là tên thư mục và tiền tố tệp JAR |
| Name | `initializr-demo` | Tên mô tả dự án |
| Description | `Demo tạo dự án Spring Boot` | Mô tả metadata; không làm thay đổi hành vi runtime |
| Package name | `com.example.initializrdemo` | Package Java gốc; **không có dấu gạch nối** |
| Packaging | **Jar** | Đóng gói ứng dụng thường chạy độc lập với embedded server khi có web starter |
| Java | **21** | Cấp độ Java đã chọn; phải dùng JDK/toolchain tương thích |

**Group** và **Artifact** thường tham gia tạo coordinates `groupId:artifactId` (Maven) hoặc tên dự án/artifact tương ứng (Gradle). **Package name** là không gian tên của lớp Java; phải tuân thủ cú pháp package Java. Không dùng tên chứa dấu gạch nối làm package.

**Bước 5 — Dependencies:** Nhấn **Add Dependencies**. Để làm phép thử HTTP ở mục 7, chọn **Spring Web**. Initializr sẽ tạo khai báo starter tương ứng cho **dòng Spring Boot đã chọn**; không cần tự nhớ tên artifact chính xác cho mọi major version. Nếu chỉ muốn quan sát bộ khung và vòng đời khởi tạo, có thể tạo dự án không có Spring Web, nhưng khi đó không mặc nhiên có HTTP server để gọi `/ping`. Chỉ thêm các starter thật sự cần (ví dụ Validation, Spring Data JPA) khi bài toán yêu cầu; mỗi starter kéo theo dependencies và auto-configuration.

**Bước 6 — Generate:** Nhấn **Generate**, giải nén ZIP, mở **thư mục gốc chứa `pom.xml` hoặc `build.gradle(.kts)`** bằng IntelliJ IDEA, VS Code hoặc IDE có hỗ trợ Java/Spring. Chờ IDE tải dependencies và nhận diện project. Trong team, đưa Wrapper cùng tệp build vào version control để CI và máy đồng đội dùng cùng cách build.

**Bước 7 — Kiểm tra:** Đối chiếu lựa chọn thực tế trên giao diện với file build đã sinh. Nếu muốn đổi một tham số lớn (major version Boot, công cụ build, phiên bản Java), tốt nhất hiểu hậu quả hoặc tạo lại một project sạch để so sánh, thay vì chép lẫn hai bộ build.

## 5. Bộ khung được sinh ra gồm những gì?

Ví dụ dưới đây minh họa cấu trúc thường gặp của **Maven + Java + Jar**. Tên tệp/lớp thực tế phụ thuộc thông tin đã nhập và version Initializr.

~~~text
initializr-demo/
├── .mvn/wrapper/                 # Cấu hình Maven Wrapper
├── mvnw                          # Wrapper cho macOS/Linux
├── mvnw.cmd                      # Wrapper cho Windows
├── pom.xml                       # Maven build, dependencies, plugins
├── src/
│   ├── main/
│   │   ├── java/com/example/initializrdemo/
│   │   │   └── InitializrDemoApplication.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/java/com/example/initializrdemo/
│       └── InitializrDemoApplicationTests.java
└── .gitignore
~~~

Lớp `InitializrDemoApplication` thường có `@SpringBootApplication` và phương thức `main` gọi `SpringApplication.run(...)`. Annotation này kết hợp cấu hình Spring Boot, cơ chế auto-configuration và component scanning theo package gốc. Vì vậy khi bổ sung controller/service, đặt chúng trong package gốc hoặc package con để được quét mặc định.

Nếu chọn **Gradle**, cấu trúc `src/main` và `src/test` về cơ bản tương tự, nhưng sẽ dùng:

~~~text
build.gradle       # Nếu chọn Gradle - Groovy
# HOẶC build.gradle.kts nếu chọn Gradle - Kotlin
settings.gradle    # Hoặc settings.gradle.kts, tùy DSL
gradlew
gradlew.bat
gradle/wrapper/
~~~

Trong project Maven Initializr, `pom.xml` thường có cấu hình Spring Boot parent/dependency management và Maven plugin. Trong project Gradle, tệp build cấu hình Spring Boot plugin, dependency management và Java toolchain. **Không chép trực tiếp XML của Maven vào Gradle hoặc ngược lại.** Nên sửa thông qua cơ chế của công cụ build đã chọn.

Ví dụ phần đặt cấp Java cho **Maven** (chỉ là đoạn trong `pom.xml`, không phải toàn bộ POM độc lập):

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

Ví dụ cấu hình Java toolchain trong **Gradle – Groovy** (chỉ là đoạn trong `build.gradle`):

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Cả hai đều phải đi kèm JDK/toolchain thực sự có thể được build tool sử dụng. Để thay đổi version Spring Boot, xem cấu hình version Boot plugin/parent do Initializr sinh; **không sửa riêng từng thư viện Spring theo cảm tính**, vì Boot quản lý tập phiên bản tương thích qua dependency management.

## 6. Chạy, test và đóng gói ứng dụng

Mở terminal tại **thư mục gốc dự án**. Chọn **một** bộ lệnh tương ứng công cụ build đã chọn.

### Maven (macOS/Linux)

~~~bash
./mvnw test
./mvnw spring-boot:run
~~~

Mở terminal khác khi ứng dụng đang chạy; để đóng gói sau đó:

~~~bash
./mvnw clean package
~~~

### Maven (Windows PowerShell)

~~~powershell
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run
~~~

Lệnh đóng gói là `.\mvnw.cmd clean package`. File JAR thường xuất hiện trong `target/`. Khi chạy thủ công với `java -jar`, dùng **tên JAR thực tế** vừa sinh, tránh nhầm file `.original` hoặc các tệp JAR khác.

### Gradle (macOS/Linux)

~~~bash
./gradlew test
./gradlew bootRun
~~~

Để đóng gói executable JAR của Spring Boot:

~~~bash
./gradlew clean bootJar
~~~

### Gradle (Windows PowerShell)

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Lệnh đóng gói là `.\gradlew.bat clean bootJar`. File đầu ra thường nằm trong `build/libs/`. Nếu dùng Gradle, không gọi task `spring-boot:run`; nếu dùng Maven, không gọi task `bootRun`.

**`test`** chạy bộ kiểm thử đã sinh; **`spring-boot:run`/`bootRun`** khởi động ứng dụng qua plugin; **`package`/`bootJar`** tạo gói ứng dụng. **`java -jar <đường-dẫn-đến-boot-jar>`** chạy executable JAR đã build (thay placeholder đường dẫn bằng tệp thật). Việc có máy chủ HTTP lắng nghe port phụ thuộc dependencies và cấu hình của project.

## 7. Kiểm chứng bằng một endpoint nhỏ

Để thấy rõ bộ khung hoạt động, với dự án có **Spring Web**, tạo file `src/main/java/com/example/initializrdemo/PingController.java`. Mã sau là **một lớp hoàn chỉnh**, được biên dịch như một phần của dự án Spring Boot do Initializr tạo; nó không phải ứng dụng Java độc lập.

~~~java
package com.example.initializrdemo;

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

Giải thích: `@RestController` đánh dấu bean nhận HTTP request và trả response body; `@GetMapping("/ping")` ánh xạ HTTP GET tại `/ping`; chuỗi `"pong"` được trả về dưới dạng text. Vì controller cùng package với lớp ứng dụng chính (hoặc ở package con), nó được Spring Boot phát hiện qua component scanning mặc định.

Khởi động ứng dụng bằng **một trong hai** lệnh đã nêu (Maven hoặc Gradle). Với cổng HTTP mặc định 8080, gọi từ terminal khác:

~~~bash
curl -s http://localhost:8080/ping
~~~

Kết quả body kỳ vọng:

~~~text
pong
~~~

Nếu dùng Windows PowerShell, có thể gọi `curl.exe -s http://localhost:8080/ping`. Không dựa vào thứ tự các dòng log startup làm tiêu chí kiểm tra vì banner, phiên bản và log có thể khác. Nếu bạn đổi `server.port` trong `application.properties`, dùng đúng cổng đã cấu hình. Nếu không thêm **Spring Web** hoặc controller chưa được quét, ví dụ HTTP này sẽ không hoạt động như mô tả.

## 8. Ba phương án lựa chọn thực tế

**Phương án A — Người mới học Spring Boot:** Chọn **Maven + Java + Java 21 + Spring Boot stable/GA + Jar + Spring Web**. Đổi sang Java 17 nếu môi trường học chỉ hỗ trợ 17 và dòng Boot đã chọn cho phép. Dùng Wrapper và kiểm tra `/ping`. Điều quan trọng là biết mỗi lựa chọn ảnh hưởng file build và runtime như thế nào.

**Phương án B — Team đã dùng Gradle:** Chọn **Gradle – Groovy** hoặc **Gradle – Kotlin** đúng theo convention repo, **Language = Java**, Java và Boot theo ma trận tương thích của team. Dùng `gradlew`/`gradlew.bat`; kiểm tra Java toolchain và JVM chạy Gradle trong CI.

**Phương án C — Dự án có tích hợp hệ thống cũ:** Chọn dòng Boot dựa trên yêu cầu thư viện và mức độ hỗ trợ trước, sau đó mới chọn JDK và build tool tương ứng. Một thư viện chỉ tương thích với Boot 3 không tự nhiên dùng được trên Boot 4 chỉ vì Java cùng là 17/21; đặc biệt phải kiểm tra thay đổi Spring Framework/Jakarta ở các bản major.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra, xử lý |
| --- | --- | --- |
| `invalid target release` / `invalid source release: 21` | JDK dùng để biên dịch thấp hơn phiên bản Java đã chọn | Kiểm tra `javac -version`, `JAVA_HOME`, Maven/Gradle JVM và toolchain; cài/chọn JDK phù hợp |
| `Unsupported class file major version` hoặc Gradle không khởi động | JVM chạy build tool hoặc phiên bản Gradle không hỗ trợ cấp Java đang dùng | Đọc thông báo lỗi; đối chiếu phiên bản Java–Gradle–Boot và Wrapper |
| `bootRun` không tồn tại | Đang dùng Maven hoặc thiếu Spring Boot Gradle plugin | Xác nhận `pom.xml`/`build.gradle(.kts)`; dùng đúng lệnh build |
| `spring-boot:run` không chạy | Đang dùng Gradle, chạy sai thư mục hoặc build bị lỗi | Mở đúng thư mục gốc; dùng `./gradlew bootRun` cho Gradle |
| Không tải được dependencies/distribution | Mạng, DNS, proxy, repository hoặc chứng chỉ | Kiểm tra kết nối, proxy, log download; Wrapper có thể cần mạng ở lần đầu |
| HTTP 404 tại `/ping` | Sai path, controller không được quét hoặc thiếu mapping | Kiểm tra `@GetMapping`, package của controller, dependency Spring Web |
| Không kết nối được `localhost:8080` | Ứng dụng chưa chạy, không có web starter hoặc dùng cổng khác | Đọc log startup, kiểm tra dependencies, `server.port` và tiến trình |
| `Port 8080 was already in use` | Có ứng dụng khác đang chiếm cổng | Dừng tiến trình chiếm cổng hoặc cấu hình `server.port=8081` |
| Mã build được ở máy cá nhân nhưng hỏng CI | JDK, Gradle/Maven Wrapper hoặc cache/repository khác nhau | Đồng bộ JDK/toolchain, commit Wrapper, khóa phiên bản và chạy cùng lệnh trong CI |

Khi lỗi xuất hiện, hãy đọc **dòng lỗi gốc đầu tiên** trong log và xác định nó thuộc một trong ba tầng: **JDK/toolchain**, **build tool + dependencies**, hay **runtime của Spring Boot**. Đổi liên tiếp nhiều version cùng lúc thường làm khó khoanh vùng.

## 10. Checklist hoàn thành

- [ ] Chọn đúng **Language = Java** và hiểu phiên bản **Java** đã cấu hình.
- [ ] Chọn **Spring Boot stable/GA** tương thích với JDK, build tool và libraries cần dùng.
- [ ] Chọn một hệ build: Maven hoặc Gradle với đúng DSL team sử dụng.
- [ ] Xác nhận `group`, `artifact`, `package name` (package Java không chứa dấu `-`), **Jar** và dependencies cần thiết.
- [ ] Giải nén, mở đúng project root, kiểm tra JDK và file Wrapper.
- [ ] Chạy `test`, khởi động ứng dụng và kiểm tra `/ping` nếu đã chọn Spring Web.
- [ ] Biết tìm cấu hình Java/Boot ở `pom.xml` hoặc `build.gradle(.kts)`; biết tệp executable JAR nằm trong `target/` hoặc `build/libs/`.
- [ ] Giải thích được vì sao một phiên bản Boot, JDK hoặc Gradle cụ thể được chọn trong dự án của mình.

## Tài liệu chính thức để tra cứu theo phiên bản

- Spring Initializr: https://start.spring.io
- Spring guide — Building an Application with Spring Boot: https://spring.io/guides/gs/spring-boot
- Spring Boot System Requirements (chọn tài liệu theo dòng Boot đang dùng): https://docs.spring.io/spring-boot/system-requirements.html
- Spring Boot Installation/Build Tools: https://docs.spring.io/spring-boot/4.0/installing.html
- Spring Initializr source và khái niệm generator: https://github.com/spring-io/initializr

**Kết quả cần đạt:** Bạn có một project Spring Boot Java có thể build, test, chạy bằng đúng Wrapper; giải thích được các lựa chọn Java, phiên bản Spring Boot và Maven/Gradle thay vì chỉ bấm Generate theo mặc định.