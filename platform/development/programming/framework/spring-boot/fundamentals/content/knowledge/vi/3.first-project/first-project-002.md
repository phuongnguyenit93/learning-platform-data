# Khởi tạo dự án bằng Spring Initializr

Để bắt đầu học Spring Boot, bạn không cần tự tạo từng thư mục, viết cấu hình build từ đầu hoặc tải thủ công hàng loạt thư viện. **Spring Initializr** giúp sinh ra một bộ khung dự án Spring Boot với ngôn ngữ, công cụ build, phiên bản Java và những dependency do bạn chọn. Sau khi tải về, dự án vẫn là một dự án Java thông thường: bạn có toàn quyền đọc, sửa, chạy, kiểm thử, đóng gói và đưa mã nguồn vào Git.

Bài học này hướng dẫn tạo **dự án Spring Boot đầu tiên** từ Spring Initializr, hiểu những lựa chọn quan trọng trong biểu mẫu, mở dự án trên máy, chạy ứng dụng và tự thêm một HTTP endpoint đơn giản. Ví dụ ưu tiên Java 21, dự án dạng JAR và dependency **Spring Web**; nếu dùng Maven thay cho Gradle, các bước tương đương cũng được trình bày.

## 1. Spring Initializr là gì và tạo ra những gì?

Spring Initializr là **trình sinh dự án** (project generator) cho các ứng dụng dùng Spring Boot. Giao diện phổ biến nhất là [https://start.spring.io/](https://start.spring.io/), nơi bạn chọn thông tin dự án và nhấn **Generate** để tải một tệp ZIP chứa mã nguồn khởi đầu.

Spring Initializr không phải máy chủ chạy ứng dụng của bạn, cũng không phải trình biên dịch Java. Nó chuẩn bị **đầu vào có cấu trúc** để IDE, Maven hoặc Gradle thực hiện công việc tiếp theo.

~~~text
Spring Initializr
      │
      ├── Chọn Java, phiên bản Spring Boot, công cụ build
      ├── Khai báo group, artifact, package, kiểu đóng gói
      └── Chọn dependency phù hợp
      │
      ▼
Generate → project.zip
      │
      ▼
Giải nén → mở project bằng IDE hoặc terminal
      │
      ▼
Maven / Gradle tải dependency và build mã nguồn
      │
      ▼
Chạy Spring Boot → thêm controller/service → thử endpoint
~~~

Một dự án được sinh ra thường có sẵn:

- Tệp cấu hình Maven hoặc Gradle, cùng cơ chế **wrapper** để dùng công cụ build theo phiên bản dự án.
- Thư mục **src/main/java** và một class chứa hàm **main()**.
- Annotation **@SpringBootApplication** và lời gọi **SpringApplication.run(...)**.
- Thư mục **src/main/resources** với tệp cấu hình ứng dụng.
- Thư mục **src/test/java** với lớp kiểm thử khởi tạo ban đầu.
- Danh sách dependency tương ứng với lựa chọn trên biểu mẫu.

Điểm cần nhớ: **Initializr tạo bộ khung; mã nghiệp vụ và cách ứng dụng hoạt động là do bạn viết.** Chọn Spring Web sẽ cung cấp nền tảng xử lý HTTP, nhưng không tự sinh ra endpoint nghiệp vụ **/hello** cho bạn.

## 2. Chuẩn bị trước khi tạo dự án

Bạn cần có trình duyệt để mở Spring Initializr, bộ **JDK** tương thích với phiên bản Spring Boot sẽ chọn, và một IDE hoặc trình soạn thảo Java. Các lựa chọn IDE phổ biến gồm IntelliJ IDEA, Eclipse/STS và Visual Studio Code có extension Java phù hợp.

Trong bài này dùng **JDK 21** làm ví dụ. Điều quan trọng là phiên bản Java cài trên máy phải phù hợp với lựa chọn trong Initializr và với yêu cầu của phiên bản Spring Boot cụ thể. Đừng chọn Java 21 trên biểu mẫu rồi cố build bằng JDK 17.

Kiểm tra Java từ terminal:

~~~bash
java -version
javac -version
~~~

Nếu Java chưa được nhận diện, cần cài JDK và cấu hình môi trường để terminal/IDE dùng đúng JDK. Đối với Maven và Gradle, **không nhất thiết phải cài phiên bản toàn cục** vì dự án mới thường đã bao gồm Maven Wrapper hoặc Gradle Wrapper.

Kết nối Internet cần thiết để tạo và tải dự án; lần build đầu tiên có thể cần Internet để công cụ build tải plugin và thư viện từ các kho phụ thuộc.

## 3. Mở Initializr và chọn cấu hình cho dự án đầu tiên

Mở **https://start.spring.io/**. Giao diện có thể thay đổi theo thời gian, nhưng các nhóm lựa chọn chính thường vẫn gồm **Project**, **Language**, **Spring Boot**, **Project Metadata**, **Packaging**, **Java** và **Dependencies**.

Để thực hành, có thể điền theo bảng:

| Trường | Giá trị ví dụ | Ý nghĩa |
|---|---|---|
| **Project** | Gradle - Groovy | Dùng Gradle với file build viết bằng Groovy; Maven là lựa chọn tương đương nếu quen XML |
| **Language** | Java | Viết mã nguồn ứng dụng bằng Java |
| **Spring Boot** | Phiên bản ổn định tương thích | Chọn bản phát hành ổn định đang được hỗ trợ trong giao diện, tránh bản Snapshot/Milestone khi mới bắt đầu |
| **Group** | com.example | Không gian tên thường dùng của tổ chức hoặc nhóm phát triển |
| **Artifact** | hello-spring | Định danh artifact và thường được dùng để đặt tên file build đầu ra |
| **Name** | hello-spring | Tên dự án hiển thị trong metadata |
| **Description** | First Spring Boot application | Mô tả ngắn về mục đích của project |
| **Package name** | com.example.hellospring | Package gốc cho class khởi động và các thành phần ứng dụng |
| **Packaging** | Jar | Đóng gói thành JAR thực thi; phù hợp với ứng dụng Spring Boot dùng embedded server |
| **Java** | 21 | Mức Java của dự án ví dụ; cần có JDK phù hợp khi build và chạy |
| **Dependencies** | Spring Web | Cung cấp nền tảng tạo REST API bằng Spring MVC |

**Giải thích hai lựa chọn dễ nhầm:**

**Project** quyết định công cụ build. Gradle và Maven đều tải thư viện, biên dịch, chạy test và tạo artifact; chúng khác nhau chủ yếu ở cách khai báo cấu hình và cú pháp lệnh. Bạn chỉ cần chọn **một** công cụ cho dự án ban đầu.

**Spring Boot** quyết định phiên bản nền tảng và tập dependency tương thích được quản lý. Không nhất thiết phải chọn con số cao nhất bất kể nhãn phát hành: bản **Snapshot** hoặc **Milestone/RC** dành cho các nhu cầu thử nghiệm sớm, trong khi bản **Stable** phù hợp hơn với bài thực hành cơ bản. Giao diện Initializr có thể thay đổi danh sách phiên bản, vì vậy nên dựa vào nhãn và yêu cầu tương thích thực tế thay vì sao chép một số phiên bản cố định từ tài liệu cũ.

### Group, Artifact và Package name liên quan như thế nào?

Ba trường này có vai trò khác nhau:

- **Group:** không gian tên dùng trong thông tin build, thường viết theo dạng tên miền đảo ngược, ví dụ **com.example**.
- **Artifact:** tên đơn vị được build và công bố, ví dụ **hello-spring**; có thể xuất hiện trong tên JAR.
- **Package name:** package Java chứa class chính, ví dụ **com.example.hellospring**. Package Java không dùng dấu gạch nối như artifact.

Ví dụ, một class do Initializr sinh ra có thể nằm tại:

~~~text
src/main/java/com/example/hellospring/HelloSpringApplication.java
~~~

Và bắt đầu bằng khai báo:

~~~java
package com.example.hellospring;
~~~

Đừng xem **Group** và **Package name** là hai trường buộc phải giống hệt nhau. Group giúp nhận diện artifact; package giúp tổ chức mã Java và ảnh hưởng vùng quét bean mặc định của Spring Boot.

### Tại sao chọn Jar thay vì War?

Với **Jar**, Spring Boot có thể đóng gói ứng dụng và các thành phần cần thiết để chạy bằng lệnh **java -jar**. Khi đã chọn Spring Web trên một cấu hình Servlet phù hợp, server HTTP nhúng được tích hợp vào cách chạy này. Đây là điểm khởi đầu phổ biến và thuận tiện.

**War** thường phù hợp hơn khi dự án cần được triển khai vào servlet container bên ngoài theo những ràng buộc cụ thể. Đối với dự án đầu tiên chưa có yêu cầu đó, **Jar** đơn giản hơn.

## 4. Chọn dependencies: bắt đầu ít nhưng đủ

Nhấn **Add Dependencies** và tìm **Spring Web**. Đây là dependency cốt lõi cho ví dụ HTTP trong bài: nó đưa các thành phần Spring MVC, cơ chế xử lý request/response và server nhúng phù hợp vào dự án.

Khi chọn dependency trên Initializr, bạn đang yêu cầu generator thêm các khai báo thích hợp vào file build. **Starter** tập hợp những thư viện thường dùng cùng nhau; **auto-configuration** của Spring Boot tận dụng các thư viện và cấu hình có sẵn để tự động thiết lập những bean mặc định phù hợp.

Với dự án học đầu tiên, chỉ cần **Spring Web** là đủ để viết REST controller. Một số dependency có thể gặp nhưng chưa bắt buộc:

| Dependency | Tác dụng | Có nên chọn ngay? |
|---|---|---|
| **Spring Web** | Xây dựng HTTP endpoint bằng Spring MVC | **Có**, cho ví dụ trong bài |
| **Spring Boot DevTools** | Hỗ trợ trải nghiệm phát triển, ví dụ restart khi classpath thay đổi | Tùy chọn |
| **Validation** | Hỗ trợ kiểm tra dữ liệu đầu vào với Bean Validation | Thêm khi có yêu cầu validate |
| **Spring Data JPA** | Truy cập dữ liệu quan hệ theo cách tiếp cận JPA | Chỉ khi cần database/JPA |
| **Spring Security** | Cơ chế xác thực và bảo vệ ứng dụng | Thêm khi đã có mục tiêu học bảo mật; cấu hình mặc định sẽ ảnh hưởng truy cập endpoint |
| **Actuator** | Cung cấp các khả năng quan sát, health và quản trị | Có thể học sau khi đã chạy được ứng dụng |

**Không nên chọn mọi dependency chỉ vì chúng xuất hiện trong danh sách.** Thư viện bổ sung có thể kéo theo cơ chế tự cấu hình, yêu cầu cấu hình hoặc hành vi lúc chạy mà bài thực hành chưa cần. Ví dụ, chọn một starter liên quan database khi chưa có nguồn dữ liệu tương ứng có thể khiến quá trình khởi động thất bại do thiếu cấu hình.

Lưu ý tên artifact thực tế của starter có thể khác giữa các phiên bản Spring Boot. Hãy để Initializr sinh dependency tương ứng với phiên bản đã chọn; ở bài này ta thao tác qua tên lựa chọn **Spring Web** trên giao diện.

## 5. Generate, giải nén và mở đúng thư mục dự án

Sau khi hoàn thành biểu mẫu, nhấn **Generate**. Trình duyệt tải một file ZIP, ví dụ **hello-spring.zip**. Giải nén vào thư mục làm việc, chẳng hạn:

~~~text
projects/
└── hello-spring/
    ├── build.gradle
    ├── settings.gradle
    ├── gradlew
    ├── gradlew.bat
    ├── gradle/
    └── src/
~~~

Ví dụ trên là cấu trúc **Gradle - Groovy**. Nếu bạn chọn Maven, file build chính sẽ là **pom.xml**, đi kèm **mvnw**, **mvnw.cmd** và thư mục **.mvn/**.

**Mở đúng thư mục gốc** chứa **build.gradle** hoặc **pom.xml**, thay vì chỉ mở thư mục **src**. IDE cần file build để nhận diện dự án, đồng bộ dependency và thiết lập cấu hình chạy.

### Mở bằng IDE

**IntelliJ IDEA:** dùng **Open** và chọn thư mục dự án đã giải nén. Khi IDE hỏi có tin cậy project không, xác nhận nếu đây đúng là project bạn vừa tạo; sau đó cho IDE import và đồng bộ Gradle/Maven.

**Eclipse / Spring Tools:** import như một dự án Gradle hoặc Maven có sẵn, tùy cấu hình đã chọn.

**Visual Studio Code:** mở thư mục gốc bằng **Open Folder**, đảm bảo extension Java và các thành phần hỗ trợ Spring/Gradle hoặc Maven phù hợp đã được cài đặt.

Đồng bộ dependency lần đầu có thể lâu hơn các lần sau vì công cụ build phải tải những thành phần còn thiếu. Khi có lỗi kết nối kho thư viện, cần kiểm tra mạng, proxy hoặc cấu hình kho dependency.

## 6. Đọc cấu trúc project được sinh ra

Với lựa chọn **Gradle - Groovy**, một cấu trúc đơn giản có dạng:

~~~text
hello-spring/
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── build.gradle
├── settings.gradle
├── .gitignore
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/hellospring/
    │   │       └── HelloSpringApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/hellospring/
                └── HelloSpringApplicationTests.java
~~~

Tên file có thể được điều chỉnh theo các giá trị nhập vào và phiên bản generator. Các vị trí quan trọng cần nhận biết:

| Đường dẫn | Vai trò |
|---|---|
| **build.gradle** | Plugin, Java toolchain, dependency và cấu hình build đối với Gradle - Groovy |
| **settings.gradle** | Thiết lập dự án Gradle và tên root project |
| **pom.xml** | File cấu hình build tương ứng nếu tạo bằng Maven |
| **gradlew / gradlew.bat** | Script chạy Gradle Wrapper trên Unix/macOS và Windows |
| **mvnw / mvnw.cmd** | Script Maven Wrapper nếu chọn Maven |
| **src/main/java** | Mã nguồn Java của ứng dụng |
| **src/main/resources** | Tài nguyên và cấu hình ngoài mã nguồn |
| **src/test/java** | Mã kiểm thử |
| **application.properties** | Cấu hình Spring Boot ban đầu; có thể dùng **application.yml** theo nhu cầu |
| **.gitignore** | Danh sách file/thư mục không nên đưa vào Git |

Hai thư mục **build/** (Gradle) và **target/** (Maven) thường xuất hiện **sau khi build**, không phải nơi bạn viết mã nguồn. Chúng chứa kết quả được tạo ra và có thể được xây dựng lại từ source cùng cấu hình dự án.

### Class khởi động: điểm vào của ứng dụng

Initializr tạo một class có cấu trúc tương tự:

~~~java
package com.example.hellospring;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HelloSpringApplication {

    public static void main(String[] args) {
        SpringApplication.run(HelloSpringApplication.class, args);
    }
}
~~~

**main()** là điểm vào Java thông thường. **SpringApplication.run(...)** tạo và khởi động Spring application context; Spring Boot đọc cấu hình và áp dụng những auto-configuration phù hợp.

Annotation **@SpringBootApplication** là lối viết gọn tập hợp những ý nghĩa quan trọng, gồm khai báo cấu hình Spring, bật auto-configuration và component scanning. Theo mặc định, component scanning tìm các thành phần nằm trong package của class khởi động và các package con. Vì thế việc đặt class chính ở package gốc **com.example.hellospring** rồi đặt controller/service bên dưới nó là cách tổ chức dễ hiểu cho người mới.

Bạn chưa cần hiểu hết mọi bean được khởi tạo để chạy được dự án đầu tiên. Trước hết hãy nhận ra **main() khởi động ứng dụng**, còn những class bổ sung sẽ đảm nhiệm nghiệp vụ.

## 7. Chạy ứng dụng lần đầu

Có thể chạy class **HelloSpringApplication** trực tiếp từ IDE bằng nút **Run**, hoặc dùng wrapper từ terminal. Các lệnh dưới đây là **cách sử dụng cho người học**, không cần cài Maven/Gradle toàn cục.

### Nếu chọn Gradle - Groovy

Trên Windows PowerShell, đứng trong thư mục chứa **gradlew.bat**:

~~~powershell
.\gradlew.bat bootRun
~~~

Trên Linux hoặc macOS:

~~~bash
./gradlew bootRun
~~~

### Nếu chọn Maven

Trên Windows PowerShell, đứng trong thư mục chứa **mvnw.cmd**:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Trên Linux hoặc macOS:

~~~bash
./mvnw spring-boot:run
~~~

**Chỉ dùng lệnh thuộc công cụ build mà bạn đã chọn trên Initializr.** Không có lý do để chạy cả Maven và Gradle cho cùng bộ khung mới.

Nếu dự án có **Spring Web**, khi khởi động thành công bạn thường thấy log cho biết application đã khởi động và server HTTP đang lắng nghe. Với cấu hình mặc định, cổng thường là **8080**. Nếu một chương trình khác đã dùng cổng này, Spring Boot có thể thông báo lỗi không bind được port.

Một điểm dễ gây nhầm: truy cập **http://localhost:8080/** ngay sau khi generate có thể nhận **404 Not Found**. Điều đó không nhất thiết là ứng dụng lỗi. Project cơ bản chưa có controller trả dữ liệu cho đường dẫn **/**. Ta sẽ tạo endpoint riêng ở bước tiếp theo.

Để dừng ứng dụng đang chạy trong terminal, thường nhấn **Ctrl+C**. Nếu chạy bằng IDE, dùng nút **Stop**.

## 8. Tạo HTTP endpoint đầu tiên

Trong project ví dụ, tạo file:

~~~text
src/main/java/com/example/hellospring/HelloController.java
~~~

Thêm nội dung:

~~~java
package com.example.hellospring;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public Map<String, String> hello(
            @RequestParam(defaultValue = "World") String name) {
        return Map.of("message", "Hello, " + name + "!");
    }
}
~~~

Các thành phần chính:

1. **@RestController** cho Spring biết class này xử lý HTTP request và giá trị trả về của handler được ghi vào HTTP response body.
2. **@GetMapping("/hello")** ánh xạ các request HTTP **GET /hello** tới phương thức **hello(...)**.
3. **@RequestParam** lấy tham số **name** từ URL; nếu không có thì dùng giá trị **World**.
4. **Map<String, String>** chứa dữ liệu response; với các thành phần JSON cần thiết do Spring Web cung cấp, Spring MVC có thể chuyển giá trị này thành JSON.

Vì **HelloController** nằm cùng package với **HelloSpringApplication**, nó ở trong vùng component scanning mặc định. Bạn không cần tự khởi tạo controller bằng toán tử **new** hoặc đăng ký nó thủ công.

Sau khi lưu file, nếu ứng dụng đã chạy từ trước mà không có cơ chế tự restart phù hợp, hãy dừng và chạy lại để mã mới được biên dịch và nạp vào ứng dụng.

### Gửi thử request

Dùng trình duyệt hoặc terminal để gọi:

~~~text
http://localhost:8080/hello
http://localhost:8080/hello?name=Lan
~~~

Trên Windows, dùng **curl.exe** để tránh nhầm với alias của PowerShell:

~~~powershell
curl.exe "http://localhost:8080/hello?name=Lan"
~~~

Hoặc dùng lệnh PowerShell:

~~~powershell
Invoke-RestMethod "http://localhost:8080/hello?name=Lan"
~~~

Trên Linux/macOS:

~~~bash
curl "http://localhost:8080/hello?name=Lan"
~~~

Response JSON dự kiến:

~~~json
{
  "message": "Hello, Lan!"
}
~~~

Đây là kết quả của **controller bạn vừa viết**. Spring Initializr giúp bạn chuẩn bị project và các thư viện; request được xử lý vì dự án hiện có mapping **/hello** và ứng dụng đã được chạy.

### Đường đi của request trong ví dụ

~~~text
Trình duyệt / curl
         │
         │ GET /hello?name=Lan
         ▼
HTTP server nhúng
         │
         ▼
Spring MVC tìm @GetMapping("/hello")
         │
         ▼
HelloController.hello("Lan")
         │
         ▼
Map: message = "Hello, Lan!"
         │
         ▼
HTTP response chứa JSON
~~~

Về sau, khi nghiệp vụ phức tạp hơn, controller nên giao việc cho service thay vì chứa toàn bộ xử lý. Nhưng ở dự án đầu tiên, phương thức nhỏ này giúp quan sát rõ quan hệ giữa một request và một phương thức Java.

## 9. Cấu hình ứng dụng ở đâu?

Initializr thường tạo file **src/main/resources/application.properties**. Đây là một trong những nơi Spring Boot có thể đọc cấu hình. Chẳng hạn, muốn đổi cổng HTTP từ **8080** sang **8081**, thêm:

~~~properties
server.port=8081
~~~

Sau khi chạy lại với cấu hình mới, dùng URL:

~~~text
http://localhost:8081/hello?name=Lan
~~~

Spring Boot cũng hỗ trợ cách biểu diễn YAML trong **application.yml**, ví dụ tương đương:

~~~yaml
server:
  port: 8081
~~~

Hãy chọn một cách khai báo nhất quán và tránh cấu hình cùng khóa ở nhiều file nếu chưa hiểu thứ tự ưu tiên cấu hình. Bên cạnh file trong project, Spring Boot còn hỗ trợ các nguồn cấu hình như biến môi trường và tham số dòng lệnh. Điều đó cho phép một artifact có thể chạy ở những môi trường khác nhau với cấu hình khác nhau.

**Lưu ý:** Cấu hình **server.port** chỉ có tác dụng khi ứng dụng thực sự dùng một web server. Spring Boot cũng có thể tạo CLI hoặc worker không mở cổng HTTP.

## 10. Build và đóng gói thành JAR

Trong lúc phát triển, lệnh **bootRun** hoặc **spring-boot:run** tiện để chạy project. Khi muốn tạo một file ứng dụng có thể chạy độc lập bằng Java, ta **build** dự án để nhận JAR thực thi.

Với Gradle trên Windows:

~~~powershell
.\gradlew.bat bootJar
~~~

Với Gradle trên Linux/macOS:

~~~bash
./gradlew bootJar
~~~

File JAR thực thi nằm trong **build/libs/**. Với metadata ví dụ, tên có thể tương tự:

~~~text
build/libs/hello-spring-0.0.1-SNAPSHOT.jar
~~~

Chạy file đó từ thư mục gốc dự án:

~~~bash
java -jar build/libs/hello-spring-0.0.1-SNAPSHOT.jar
~~~

Nếu chọn Maven, thực hiện:

~~~powershell
.\mvnw.cmd package
~~~

Hoặc trên Linux/macOS:

~~~bash
./mvnw package
~~~

Artifact thường được tạo dưới **target/**, ví dụ:

~~~bash
java -jar target/hello-spring-0.0.1-SNAPSHOT.jar
~~~

**Tên và phiên bản file JAR thực tế có thể khác** theo metadata và cấu hình build; hãy xem file được tạo trong thư mục đầu ra thay vì giả định ví dụ trên luôn đúng.

Các thao tác build thông thường cũng liên quan đến việc biên dịch và chạy test theo lifecycle của công cụ. Nếu test lỗi, hãy đọc lỗi và sửa nguyên nhân; file build đầu ra chỉ có ý nghĩa khi quá trình đóng gói hoàn tất theo yêu cầu của dự án.

### Build tool làm gì khi chạy?

Maven/Gradle sử dụng metadata do Initializr tạo ra để:

- Xác định plugin và phiên bản Spring Boot tương thích.
- Tải các dependency được khai báo cùng dependency bắc cầu cần thiết.
- Biên dịch mã Java và xử lý resources.
- Thực thi những bước test/build đã được cấu hình.
- Đóng gói artifact để chạy hoặc phát hành.

Spring Initializr không làm hết các việc đó tại thời điểm Generate. ZIP có mã nguồn và cấu hình cần thiết; **build xảy ra sau khi bạn giải nén và chạy công cụ build**.

## 11. Hiểu quan hệ giữa Initializr, starter và auto-configuration

Đây là ba khái niệm có liên quan nhưng giữ nhiệm vụ khác nhau:

| Thành phần | Khi nào tham gia? | Nhiệm vụ |
|---|---|---|
| **Spring Initializr** | Khi tạo project | Sinh thư mục, mã khởi động, wrapper và khai báo dependency |
| **Spring Boot Starter** | Khi Gradle/Maven tải thư viện | Đem vào một nhóm dependency thích hợp với nhu cầu phát triển |
| **Spring Boot Auto-configuration** | Khi ứng dụng khởi động | Dựa trên classpath, bean và cấu hình để thiết lập thành phần phù hợp |

Ví dụ, chọn **Spring Web** giúp Initializr thêm starter thích hợp vào file build. Sau khi build, các thư viện web có trong classpath. Lúc **SpringApplication.run(...)** chạy, Spring Boot có thể auto-configure MVC, JSON conversion và HTTP server phù hợp. Sau đó, phương thức có **@GetMapping** mà bạn tự viết mới quyết định endpoint trả dữ liệu gì.

Nhìn theo trình tự:

~~~text
Generate        Build                  Runtime
────────        ─────                  ───────
Initializr  →   Starter dependencies → Auto-configuration
                                        │
                                        ▼
                                  Controller hoạt động
~~~

Spring Boot tiết kiệm công sức bằng các giá trị mặc định hợp lý, nhưng vẫn cho phép thay đổi cấu hình, bean và dependency theo nhu cầu thật của ứng dụng.

## 12. Những lỗi dễ gặp ở lần đầu

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| **java** không được nhận diện | Chưa cài JDK hoặc cấu hình môi trường chưa đúng | Kiểm tra cài đặt JDK, PATH và cấu hình JDK trong IDE |
| Báo Java version không phù hợp | JDK dùng để build không khớp mức Java và phiên bản Spring Boot | Chọn JDK phù hợp và kiểm tra **java -version** |
| IDE không tải được dependency | Mạng, proxy, kho thư viện hoặc cấu hình build gặp lỗi | Kiểm tra thông báo Gradle/Maven và khả năng truy cập repository |
| Không tìm thấy **gradlew.bat** hoặc **mvnw.cmd** | Đang ở sai thư mục hoặc chọn công cụ build khác | Mở thư mục gốc chứa đúng wrapper và file build |
| Không chạy được **bootRun** | Dự án được tạo bằng Maven, hoặc Gradle không import đúng | Dùng lệnh **spring-boot:run** nếu là Maven; kiểm tra file build |
| Truy cập **/** trả 404 | Chưa có mapping cho đường dẫn gốc | Gọi đúng endpoint **/hello** đã khai báo |
| **/hello** trả 404 | Controller chưa được biên dịch, nằm ngoài vùng scan hoặc ứng dụng chưa restart | Kiểm tra package, file, mapping và chạy lại |
| Lỗi **Port 8080 already in use** | Có chương trình khác đang lắng nghe cổng 8080 | Dừng tiến trình đang chiếm cổng hoặc đổi **server.port** |
| Không thấy JSON như kỳ vọng | Chưa chọn Spring Web hoặc mapping/response chưa đúng | Kiểm tra dependency do Initializr tạo và controller |
| Chạy JAR nhưng không thấy ứng dụng | Chọn sai file, build lỗi hoặc JDK không phù hợp | Xác nhận artifact thực tế, log khởi động và lệnh **java -jar** |

Khi chẩn đoán, hãy phân biệt **ba giai đoạn**: lỗi generate/download, lỗi Gradle/Maven lúc build, và lỗi Spring Boot lúc startup hoặc xử lý request. Biết lỗi xảy ra ở giai đoạn nào sẽ giúp tìm đúng nguyên nhân.

Một trường hợp thường thấy là sau khi generate, người học mở URL gốc và thấy **404** rồi cho rằng Spring Boot “không chạy”. Nếu log cho thấy server đã khởi động và **/hello** phản hồi đúng, 404 ở **/** chỉ cho biết **không có handler cho đường dẫn đó**.

## 13. Nếu không muốn xây dựng ứng dụng web thì sao?

Spring Initializr có thể tạo dự án Spring Boot **không có Spring Web**. Ví dụ, nếu bạn muốn viết một công cụ xử lý file khi chạy từ terminal:

1. Chọn Java, Maven hoặc Gradle và thông tin metadata như bình thường.
2. Không chọn Spring Web nếu không cần HTTP server.
3. Viết một bean **ApplicationRunner** hoặc **CommandLineRunner** để thực hiện công việc sau khi Spring khởi tạo.
4. Quản lý kết thúc ứng dụng và mã thoát theo tính chất lệnh.

Một ứng dụng xử lý nền theo lịch cũng có thể được tạo từ Initializr rồi thêm scheduling hoặc message listener khi có nhu cầu. Điều đó làm rõ một đặc điểm nền tảng: **Initializr không chỉ để tạo REST API**; kiểu ứng dụng cuối cùng phụ thuộc dependency và mã bạn xây dựng.

## 14. Thực hành mở rộng sau khi khởi tạo

Khi đã chạy được **GET /hello**, có thể tự phát triển project qua một số thay đổi nhỏ:

**Thử nghiệm A — Tham số request:** gọi **/hello?name=Minh**, sau đó gọi **/hello** không có query string. Quan sát vai trò của **@RequestParam(defaultValue = "World")**.

**Thử nghiệm B — Tách service:** tạo **GreetingService** có phương thức trả lời chào; dùng constructor injection để đưa service vào **HelloController**, sau đó để controller gọi service.

**Thử nghiệm C — Đổi cổng:** đặt **server.port=8081** trong cấu hình, chạy lại và truy cập endpoint qua cổng mới.

**Thử nghiệm D — Tạo artifact:** dùng wrapper build ra JAR, chạy bằng **java -jar**, rồi gửi cùng HTTP request như lúc chạy trong IDE. Nhận ra mã ứng dụng không cần thay đổi chỉ vì cách khởi chạy khác nhau.

**Thử nghiệm E — Quan sát source:** mở file build, class có **@SpringBootApplication**, controller và file cấu hình. Xác định phần nào do Initializr tạo ra và phần nào là mã bạn vừa bổ sung.

Các thử nghiệm này giúp phân biệt **khung dự án**, **dependency**, **cấu hình**, **mã xử lý request** và **cách chạy ứng dụng**.

## 15. Khi hoàn thành bài học, bạn đã có gì?

Một project Spring Boot cơ bản được tạo qua Spring Initializr và có thể chạy từ IDE hoặc terminal; một class **main()** sử dụng **@SpringBootApplication**; dependency web để phục vụ HTTP; controller do bạn tự viết tại **GET /hello**; file cấu hình cho phép đổi cổng; và khả năng đóng gói ứng dụng bằng wrapper.

Trọng tâm của bước khởi tạo không nằm ở việc thuộc lòng mọi tùy chọn trên biểu mẫu. Hãy nắm **chuỗi quan hệ**:

**Spring Initializr tạo project → Maven/Gradle tải và build dependency → Spring Boot khởi động ApplicationContext → controller xử lý HTTP request do bạn định nghĩa.**

Từ bộ khung này, bạn có thể tiếp tục học dependency injection, cấu trúc controller-service-repository, xử lý dữ liệu, cấu hình môi trường và kiểm thử trong những bài tiếp theo mà không phải tạo lại dự án từ đầu.
