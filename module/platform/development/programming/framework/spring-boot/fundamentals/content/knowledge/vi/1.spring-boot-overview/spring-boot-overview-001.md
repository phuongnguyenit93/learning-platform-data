# Spring Boot là gì và giải quyết trở ngại nào khi xây dựng ứng dụng Java?

Một ứng dụng Java có thể bắt đầu rất đơn giản: viết một lớp có phương thức `main`, biên dịch rồi chạy. Nhưng khi ứng dụng phải nhận HTTP request, trả JSON, kết nối cơ sở dữ liệu, quản lý các thành phần, cấu hình theo môi trường, chạy kiểm thử và triển khai lên máy chủ, khối lượng công việc tăng nhanh. Phần lớn công việc mới không trực tiếp tạo ra tính năng nghiệp vụ mà dành cho việc **lắp ghép và vận hành hạ tầng ứng dụng**.

**Spring Boot** giúp xây dựng ứng dụng Java dựa trên Spring Framework với ít công việc thiết lập ban đầu hơn. Nó cung cấp các quy ước mặc định, quản lý bộ thư viện thường dùng, tự cấu hình nhiều thành phần khi đủ điều kiện và hỗ trợ đóng gói ứng dụng chạy độc lập. Nhờ đó, lập trình viên có thể dành nhiều thời gian hơn cho chức năng cần làm, đồng thời vẫn có quyền tùy chỉnh khi yêu cầu thay đổi.

Bài học này giải thích những trở ngại Spring Boot giải quyết, cách các cơ chế của nó phối hợp với nhau và giới hạn thực tế của những tiện ích đó.

## 1. Tại sao làm ứng dụng Java lại có nhiều việc ngoài viết nghiệp vụ?

Giả sử cần xây dựng một dịch vụ nhỏ có API:

~~~http
GET /api/greeting?name=Linh
~~~

Phản hồi mong muốn:

~~~json
{
  "message": "Xin chào, Linh!"
}
~~~

Phép nối chuỗi để tạo lời chào không khó. Tuy nhiên, nếu xây dựng một dịch vụ có thể chạy và được sử dụng thật, cần giải quyết nhiều câu hỏi khác:

- **Nhận HTTP:** Chương trình nào lắng nghe cổng mạng, nhận request và định tuyến `/api/greeting` đến đúng phương thức Java?
- **Chuyển đổi dữ liệu:** Kết quả Java được chuyển thành JSON như thế nào? Khi client gửi JSON, ai đọc và kiểm tra cấu trúc dữ liệu?
- **Ghép các thành phần:** Controller nhận một service qua cách nào để tránh việc mọi nơi tự khởi tạo và tự quản lý đối tượng?
- **Thư viện:** Nên dùng phiên bản nào của framework web, thư viện JSON và các thành phần liên quan để chúng tương thích?
- **Cấu hình:** Cổng chạy ở máy cá nhân khác với môi trường triển khai ra sao? Bí mật kết nối cơ sở dữ liệu đến từ đâu?
- **Đóng gói:** Sau khi build, chạy dịch vụ bằng lệnh gì? Có cần cài và cấu hình một application server riêng không?
- **Kiểm thử và theo dõi:** Làm sao kiểm tra endpoint, nhận biết ứng dụng còn hoạt động và tìm nguyên nhân khi khởi động lỗi?

Java có đủ khả năng để xử lý những việc này, và Spring Framework đã cung cấp nhiều nền tảng quan trọng. Vấn đề là **chọn, cấu hình và kết nối các bộ phận** thường mất thời gian, nhất là khi lập trình viên cần khởi tạo nhiều dự án tương tự.

Trước khi dùng Spring Boot, một dự án Spring truyền thống thường phải tự thiết lập nhiều mối quan hệ giữa framework web, servlet container, cấu hình Spring, dependency và cách triển khai. Cách cấu hình cụ thể còn phụ thuộc vào thế hệ công nghệ được sử dụng; không phải mọi dự án Spring trước Boot đều có đúng cùng một cấu trúc.

## 2. Spring Boot là gì? Nó nằm ở đâu trong hệ sinh thái Java?

Spring Boot là một dự án trong hệ sinh thái Spring, được xây dựng **trên Spring Framework** để giúp tạo và vận hành ứng dụng Spring thuận tiện hơn. Spring Boot không phải ngôn ngữ lập trình mới, cũng không phải sự thay thế cho Java hoặc Spring Framework.

Có thể phân biệt ba lớp trách nhiệm:

| Thành phần | Vai trò chính | Ví dụ |
| --- | --- | --- |
| **Java** | Ngôn ngữ, thư viện chuẩn và môi trường JVM để thực thi chương trình | Lớp, interface, collection, exception, thread |
| **Spring Framework** | Nền tảng xây dựng ứng dụng: quản lý đối tượng, dependency injection, web MVC, transaction và nhiều mô-đun khác | `ApplicationContext`, `@Service`, Spring MVC |
| **Spring Boot** | Cách khởi tạo, lựa chọn dependency, cấu hình mặc định, chạy, kiểm thử và vận hành ứng dụng Spring thuận tiện hơn | Starter, auto-configuration, `SpringApplication.run`, Actuator |

Hình dung theo quan hệ:

~~~text
Ứng dụng nghiệp vụ do bạn viết
             │
             ▼
  Spring Framework và các thư viện
  (IoC/DI, Web MVC, Data, Security, ...)
             ▲
             │ được Spring Boot hỗ trợ lắp ghép,
             │ cấu hình và khởi chạy
             │
      Spring Boot
             │
             ▼
        Java / JVM
~~~

Sơ đồ này diễn tả trách nhiệm, không phải thứ tự một lời gọi hàm ở runtime. Khi lập trình với Spring Boot, bạn **vẫn dùng các khái niệm Spring** như bean, IoC container, dependency injection, controller và service. Spring Boot giúp giảm phần thiết lập để các khái niệm ấy hoạt động cùng nhau.

Ba ý tưởng xuyên suốt Spring Boot là:

1. **Convention over configuration:** Có cách làm phổ biến thì cung cấp giá trị mặc định hợp lý; chỉ cần cấu hình khác khi thực sự có yêu cầu.
2. **Opinionated defaults:** Spring Boot đưa ra những lựa chọn có chủ đích cho một tổ hợp công nghệ thông dụng, để nhóm phát triển không phải tự quyết định lại mọi thứ từ đầu.
3. **Cho phép ghi đè có kiểm soát:** Cấu hình mặc định là điểm bắt đầu. Ứng dụng vẫn có thể khai báo thuộc tính, bean và cấu hình của riêng mình.

Ví dụ, dự án web thông dụng có thể bắt đầu với một web starter. Spring Boot sẽ hỗ trợ các thành phần cần thiết để nhận request HTTP và trả JSON. Khi muốn đổi cổng, bạn đặt một thuộc tính cấu hình thay vì phải viết lại quy trình tạo server.

## 3. Những trở ngại Spring Boot xử lý cụ thể

| Trở ngại khi xây dựng ứng dụng | Spring Boot hỗ trợ bằng gì? | Lợi ích thực tế |
| --- | --- | --- |
| Phải tìm và phối hợp nhiều thư viện | **Starters** cùng cơ chế quản lý phiên bản dependency | Khởi tạo nhanh một nhóm khả năng thường dùng, giảm xung đột phiên bản |
| Phải khai báo nhiều cấu hình kỹ thuật lặp đi lặp lại | **Auto-configuration** dựa vào classpath, bean và thuộc tính | Tự tạo cấu hình thường dùng khi điều kiện phù hợp |
| Phải cài servlet container riêng để chạy API | **Embedded server** trong ứng dụng web phù hợp | Chạy ứng dụng như một tiến trình Java độc lập |
| Nhiều môi trường có giá trị cấu hình khác nhau | **Externalized configuration** và **profiles** | Dùng một bản build với cấu hình khác nhau |
| Khó khởi động ứng dụng theo cách nhất quán | `SpringApplication` và plugin build | Có entry point và quy trình build/chạy thông dụng |
| Cần quan sát tình trạng ứng dụng khi vận hành | **Actuator** (khi được thêm vào) | Có endpoint sức khỏe, thông tin, metrics theo cấu hình |
| Cần kiểm thử theo nhiều cấp độ | Tích hợp bộ kiểm thử Spring và starter test | Dễ kết hợp unit test, web test, integration test |

Các tính năng trên là **cơ chế hỗ trợ**, không có nghĩa chỉ cần thêm Spring Boot là ứng dụng tự có nghiệp vụ, dữ liệu, bảo mật và cấu hình triển khai đúng.

### 3.1. Starter: giảm công sức chọn dependency

Một ứng dụng web Spring thường cần framework HTTP, thư viện chuyển JSON, servlet container và các phần hỗ trợ liên quan. Thay vì chọn riêng từng artifact với nhiều phiên bản, ta thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

`spring-boot-starter-web` là một **starter dependency**: nó kéo vào tập dependency thường dùng cho ứng dụng web theo Spring MVC, bao gồm các thành phần web và, trong cấu hình mặc định của dòng Spring Boot 3.x, embedded Tomcat.

Một số starter khác:

- `spring-boot-starter-validation`: hỗ trợ kiểm tra dữ liệu theo Bean Validation.
- `spring-boot-starter-data-jpa`: các thành phần để làm việc với JPA, repository và transaction liên quan.
- `spring-boot-starter-security`: tích hợp Spring Security.
- `spring-boot-starter-test`: tập thư viện kiểm thử thường dùng.

**Starter không tự viết hoặc kích hoạt mọi chức năng nghiệp vụ.** Chẳng hạn, thêm starter JPA không tự tạo một cơ sở dữ liệu hoạt động hoặc tự định nghĩa entity. Ứng dụng vẫn cần datasource, entity và cấu hình phù hợp. Tương tự, thêm starter Security ảnh hưởng đến hành vi bảo mật mặc định và cần được cấu hình theo yêu cầu thực tế.

Spring Boot còn cung cấp **dependency management** để đề xuất các phiên bản tương thích trong cùng một dòng phát hành. Khi dùng Spring Boot Maven parent hoặc BOM, nhiều dependency được quản lý phiên bản và không cần khai báo phiên bản riêng. Nếu cố ý ghi đè một phiên bản, trách nhiệm kiểm tra tính tương thích quay trở lại với người phát triển.

### 3.2. Auto-configuration: cấu hình tự động theo điều kiện

**Auto-configuration** là cơ chế Spring Boot kiểm tra những gì đã có trong ứng dụng, rồi đóng góp cấu hình mặc định khi các điều kiện thích hợp được thỏa mãn.

Ví dụ với ứng dụng Spring MVC:

1. Classpath có các thư viện web cần thiết.
2. Spring Boot nhận ra đây là kiểu ứng dụng web tương ứng.
3. Các cấu hình tự động phù hợp có thể tạo những bean hạ tầng như thành phần phục vụ request và cấu hình JSON.
4. Khi bạn định nghĩa một bean riêng tại vị trí mà auto-configuration cho phép ghi đè, cấu hình mặc định tương ứng có thể **nhường chỗ**.

Spring Boot thường dùng những điều kiện như `@ConditionalOnClass`, `@ConditionalOnMissingBean` và điều kiện theo thuộc tính cấu hình để quyết định có kích hoạt cấu hình cụ thể hay không.

Điểm rất quan trọng: **auto-configuration không có nghĩa là cấu hình bất kể điều kiện nào**. Nó phụ thuộc vào dependency, loại ứng dụng, các bean đã tồn tại và các giá trị cấu hình. Thêm một thư viện mới đôi khi khiến cấu hình tự động khác được xét đến; vì thế nên hiểu tác động của các starter được thêm vào.

Nếu một ứng dụng không dùng web starter thì không thể suy ra rằng nó sẽ có HTTP server chỉ vì phụ thuộc Spring Boot.

### 3.3. `@SpringBootApplication`: điểm bắt đầu của ứng dụng

Một ứng dụng Boot thường có lớp khởi động:

~~~java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` kết hợp những chức năng thường dùng:

- `@SpringBootConfiguration`: đánh dấu lớp là một nguồn cấu hình Spring.
- `@EnableAutoConfiguration`: cho phép cơ chế auto-configuration của Boot.
- `@ComponentScan`: tìm các component của ứng dụng trong phạm vi package mặc định.

`SpringApplication.run(...)` chuẩn bị và khởi tạo Spring application context, trong đó có các bean cần thiết. Với ứng dụng web phù hợp, quy trình khởi động còn khởi tạo embedded web server.

**Vị trí package của lớp main có ý nghĩa.** Theo mặc định, component scan bắt đầu từ package chứa lớp được đánh dấu và các package con. Nếu một service nằm ngoài phạm vi này, Spring có thể không phát hiện được bean ấy. Lỗi đó khác với việc “Spring Boot không hỗ trợ service”.

### 3.4. Embedded server: chạy bằng JAR

Với ứng dụng web Spring MVC dùng starter mặc định, server như Tomcat có thể được **nhúng trong ứng dụng**. Lập trình viên không phải cài đặt riêng một Tomcat rồi triển khai file WAR chỉ để chạy ví dụ API cơ bản.

Sau khi build, quy trình thường có dạng:

~~~text
JAR thực thi
 ├── Mã ứng dụng
 ├── Thư viện Spring và dependency liên quan
 └── Thành phần hỗ trợ khởi chạy và web server nhúng
             │
             ▼
   java -jar ten-ung-dung.jar
             │
             ▼
      Tiến trình JVM nhận HTTP
~~~

Đây là một thuận lợi cho phát triển tại máy cá nhân, môi trường CI và triển khai theo tiến trình hoặc container. Spring Boot vẫn có cách đóng gói WAR trong những trường hợp cần triển khai theo mô hình servlet container bên ngoài; “JAR thực thi” là con đường phổ biến, không phải con đường duy nhất.

Server nhúng **không đồng nghĩa** ứng dụng đã sẵn sàng cho production: cần bổ sung thiết lập bảo mật, nguồn cấu hình, log, tài nguyên, giám sát và quy trình triển khai phù hợp.

## 4. Ví dụ hoàn chỉnh: từ yêu cầu HTTP đến ứng dụng Spring Boot

Ví dụ dưới đây dùng **Java 21**, **Maven** và **Spring Boot 3.3.5** để minh họa một dự án Spring Boot 3.x cụ thể. Phiên bản này được chọn để mã mẫu nhất quán; khi bắt đầu dự án thực tế nên chọn dòng Spring Boot đang được hỗ trợ và tương thích với Java của hệ thống.

### 4.1. Cấu trúc dự án

~~~text
demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/demo/
    │   │       └── DemoApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/demo/
                └── GreetingControllerTest.java
~~~

Mọi lớp ứng dụng trong ví dụ nằm dưới package `com.example.demo`, nơi Spring Boot thực hiện component scan mặc định.

### 4.2. Khai báo dependency trong `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>demo</name>

    <properties>
        <java.version>21</java.version>
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

Ở đây:

- `spring-boot-starter-parent` cung cấp cách quản lý dependency và các thiết lập Maven dùng chung cho dự án mẫu.
- `spring-boot-starter-web` cung cấp tập thành phần web thông dụng để xây dựng API.
- `spring-boot-starter-test` dành cho mã kiểm thử.
- `spring-boot-maven-plugin` hỗ trợ chạy và đóng gói ứng dụng Boot thành executable JAR.

Không cần tự đưa phiên bản vào từng starter vì Maven parent đang quản lý chúng.

### 4.3. Viết lớp khởi động, controller và service

Để ví dụ dễ đọc, các kiểu Java dưới đây được đặt trong cùng một file `DemoApplication.java`. Trong dự án lớn, nên tách chúng thành các file theo trách nhiệm.

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api")
class GreetingController {

    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    GreetingResponse greeting(
            @RequestParam(defaultValue = "Bạn") String name) {
        return new GreetingResponse(greetingService.sayHello(name));
    }
}

@Service
class GreetingService {

    String sayHello(String name) {
        return "Xin chào, " + name + "!";
    }
}

record GreetingResponse(String message) {
}
~~~

Chúng ta đã tự viết phần nghiệp vụ là `sayHello` và hợp đồng HTTP trong controller. Phần hạ tầng có thể được Boot hỗ trợ thiết lập:

- `@Service` khiến `GreetingService` trở thành ứng viên bean mà Spring quản lý.
- `@RestController` đánh dấu controller và cho phép trả dữ liệu response body.
- Spring cung cấp `GreetingService` cho constructor của `GreetingController` thông qua **constructor injection**; không cần `new GreetingService()` trong controller.
- `@GetMapping("/greeting")` cùng `@RequestMapping("/api")` ánh xạ request đến `/api/greeting`.
- `@RequestParam` nhận giá trị query parameter `name` hoặc dùng giá trị mặc định.
- Thư viện chuyển đổi JSON tích hợp với Spring MVC biến đối tượng `GreetingResponse` thành JSON trong HTTP response.

**Không có chuyện Spring Boot tự hiểu mọi phương thức Java là API.** Ta vẫn phải khai báo mapping và cấu trúc response theo yêu cầu.

### 4.4. Cấu hình tối thiểu rồi chạy

Đặt file `src/main/resources/application.properties`:

~~~properties
spring.application.name=demo
server.port=8080
~~~

Từ thư mục chứa `pom.xml`, với JDK 21 và Maven có sẵn:

~~~bash
mvn spring-boot:run
~~~

Sau khi ứng dụng khởi động thành công, gọi:

~~~bash
curl "http://localhost:8080/api/greeting?name=Linh"
~~~

Phản hồi mong đợi:

~~~json
{"message":"Xin chào, Linh!"}
~~~

Có thể chạy theo cách đóng gói JAR:

~~~bash
mvn package
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

Đổi `server.port=8081` rồi chạy lại, endpoint sẽ chuyển sang cổng `8081`. Bạn không phải sửa phương thức `main` hoặc khởi tạo Tomcat bằng mã Java.

Nếu đang dùng PowerShell, có thể gọi endpoint bằng lệnh:

~~~powershell
Invoke-RestMethod "http://localhost:8080/api/greeting?name=Linh"
~~~

### 4.5. Điều gì thực sự diễn ra khi có request?

~~~mermaid
flowchart LR
    A["Client: GET /api/greeting"] --> B["Embedded Tomcat"]
    B --> C["Spring MVC / DispatcherServlet"]
    C --> D["GreetingController"]
    D --> E["GreetingService"]
    E --> D
    D --> F["Chuyển GreetingResponse thành JSON"]
    F --> A
~~~

Giải thích từng đoạn:

1. Tomcat nhận kết nối HTTP khi ứng dụng web đã khởi động.
2. Spring MVC tiếp nhận request và xác định handler phù hợp với route.
3. Spring gọi `GreetingController.greeting(...)` với query parameter đã được chuyển thành tham số Java.
4. Controller sử dụng `GreetingService` do Spring cung cấp, nhận chuỗi lời chào và tạo `GreetingResponse`.
5. Bộ chuyển đổi thông điệp HTTP phù hợp, thường dựa trên Jackson trong cấu hình mẫu, ghi dữ liệu thành JSON rồi gửi response.

Spring Framework thực hiện nhiều hành vi runtime như dependency injection, xử lý MVC và gọi controller. Spring Boot giúp ứng dụng có cấu hình và dependency cần thiết để những cơ chế ấy làm việc với nhau nhanh hơn.

## 5. Cấu hình: một ứng dụng, nhiều môi trường

Một khó khăn khác của hệ thống thật là môi trường phát triển, kiểm thử và production thường có các giá trị khác nhau. Ví dụ: cổng HTTP, địa chỉ database, timeout, URL của dịch vụ bên ngoài và mức log.

Spring Boot hỗ trợ **externalized configuration**: đọc cấu hình từ nhiều nguồn như file `application.properties` hoặc `application.yml`, biến môi trường và tham số dòng lệnh. Bạn có thể giữ mã nguồn và bản build giống nhau, còn giá trị cấu hình thay đổi theo môi trường.

### 5.1. Cấu hình qua file

~~~properties
# src/main/resources/application.properties
spring.application.name=demo
server.port=8080
~~~

Ngoài định dạng `.properties`, Spring Boot cũng hỗ trợ cấu hình YAML:

~~~yaml
spring:
  application:
    name: demo

server:
  port: 8080
~~~

Một dự án thường chọn một cách trình bày rõ ràng cho cùng tập thuộc tính, tránh khai báo giá trị mâu thuẫn không cần thiết ở nhiều nơi.

### 5.2. Ghi đè qua biến môi trường hoặc tham số chạy

Ví dụ trên hệ thống triển khai có thể cung cấp biến môi trường:

~~~text
SERVER_PORT=9090
~~~

Spring Boot có cơ chế liên kết tên biến môi trường với thuộc tính `server.port`. Hoặc chạy JAR cùng tham số:

~~~bash
java -jar target/demo-0.0.1-SNAPSHOT.jar --server.port=9090
~~~

Theo cơ chế ưu tiên cấu hình của Boot, tham số dòng lệnh thông thường có thể ghi đè giá trị trong `application.properties`. Cách này giúp thay đổi cổng mà không cần sửa mã nguồn hoặc build lại JAR.

### 5.3. Profile cho cấu hình theo hoàn cảnh

Giả sử file `application-dev.properties` chứa:

~~~properties
server.port=8081
~~~

Còn `application-prod.properties` chứa:

~~~properties
server.port=9090
~~~

Có thể kích hoạt profile bằng:

~~~bash
java -jar target/demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=prod
~~~

Khi profile `prod` được kích hoạt, Boot tải các cấu hình áp dụng cho profile đó theo quy tắc hợp nhất và ưu tiên của hệ thống cấu hình.

**Profile không tự tạo ranh giới bảo mật.** Không nên đưa mật khẩu, API key hoặc secret thật vào file được commit. Giá trị nhạy cảm nên được cấp từ cơ chế quản lý secret hoặc nguồn cấu hình an toàn của môi trường triển khai.

## 6. Vận hành và kiểm thử: Spring Boot hỗ trợ đến đâu?

### 6.1. Quan sát ứng dụng với Actuator

Một API trả lời được request chưa chắc đã khỏe mạnh: ứng dụng có thể thiếu kết nối cơ sở dữ liệu hoặc đang gặp vấn đề tài nguyên. Spring Boot Actuator cung cấp các endpoint và tích hợp để theo dõi tình trạng ứng dụng.

Muốn dùng Actuator, trước tiên cần thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Trong cấu hình web mặc định, health endpoint thường có đường dẫn:

~~~http
GET /actuator/health
~~~

Ví dụ phản hồi:

~~~json
{"status":"UP"}
~~~

`UP` cho biết kết quả đánh giá của các health indicator đang tham gia; nó **không bảo đảm mọi quy trình nghiệp vụ đều chính xác**. Metrics, readiness/liveness, chi tiết health và những endpoint khác phụ thuộc vào dependency cùng cấu hình triển khai.

Chỉ công khai những endpoint thật sự cần, kiểm soát quyền truy cập và cân nhắc thông tin nhạy cảm. Actuator giúp quan sát hệ thống; nó không thay thế cấu hình giám sát, cảnh báo và bảo mật của môi trường production.

### 6.2. Kiểm thử endpoint

Spring Boot hỗ trợ các công cụ tích hợp để viết test. Với `spring-boot-starter-test` đã khai báo trong ví dụ, có thể viết `GreetingControllerTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsGreetingForName() throws Exception {
        mockMvc.perform(get("/api/greeting").param("name", "Linh"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Xin chào, Linh!"));
    }
}
~~~

Trong ví dụ này:

- `@SpringBootTest` khởi tạo Spring application context phục vụ kiểm thử tích hợp.
- `@AutoConfigureMockMvc` tạo hạ tầng `MockMvc` cho kiểu ứng dụng Spring MVC phù hợp.
- `MockMvc` mô phỏng xử lý request qua Spring MVC để kiểm tra status và nội dung JSON mà không cần mở cổng HTTP thật.

Lệnh `mvn test` sẽ thực thi các test Maven nhận diện được. Với logic chỉ xử lý chuỗi của `GreetingService`, một **unit test thuần Java** còn nhẹ hơn việc khởi tạo cả Spring context. Boot hỗ trợ nhiều mức kiểm thử, nhưng lựa chọn mức phù hợp vẫn là trách nhiệm của nhóm phát triển.

## 7. So sánh cách phát triển có và không dùng Spring Boot

Xét cùng một ứng dụng API dùng hệ sinh thái Spring:

| Công việc | Tự lắp ghép ứng dụng Spring | Dùng Spring Boot |
| --- | --- | --- |
| Chọn nhóm thư viện web | Tự chọn và phối hợp nhiều dependency | Có thể bắt đầu với `spring-boot-starter-web` |
| Quản lý phiên bản | Tự bảo đảm các thư viện tương thích hoặc xây dựng bộ quản lý riêng | Có dependency management theo phiên bản Boot |
| Thiết lập Spring MVC và thành phần hạ tầng | Thường cần cấu hình thủ công nhiều hơn | Nhiều cấu hình phù hợp được cung cấp tự động |
| Khởi chạy dịch vụ web | Có thể cần thiết lập container/cách đóng gói riêng | Thường dùng embedded server và executable JAR |
| Chuyển cổng theo môi trường | Tùy cách dự án tự xây dựng cấu hình | Có `server.port`, biến môi trường, tham số chạy |
| Endpoint sức khỏe và metrics | Tự xây dựng hoặc tích hợp từng giải pháp | Có thể dùng Actuator khi thêm dependency |
| Logic nghiệp vụ và thiết kế API | Vẫn phải tự xây dựng | **Vẫn phải tự xây dựng** |

Bảng trên so sánh **mức công sức tích hợp ban đầu**, không khẳng định ứng dụng không dùng Boot thì thiếu năng lực kỹ thuật. Spring Framework, servlet API, thư viện khác hoặc cấu hình tùy biến đều có thể đạt kết quả tương đương; Boot giúp chuẩn hóa cách đi đến kết quả đó cho nhiều trường hợp phổ biến.

Một phép so sánh dễ nhớ: nếu Spring Framework cung cấp các bộ phận và cơ chế để xây ứng dụng, Spring Boot cung cấp nhiều bộ lắp ghép và thiết lập sẵn có điều kiện. Bạn vẫn quyết định kiến trúc, luật nghiệp vụ, dữ liệu và cách vận hành.

## 8. Giới hạn và những hiểu nhầm thường gặp

### “Spring Boot tự làm hết, không cần học Spring”

Sai. Khi gặp lỗi bean không tồn tại, dependency vòng tròn, phạm vi component scan hoặc giao dịch không như mong muốn, cần hiểu Spring Framework. Spring Boot giảm mã cấu hình nhưng không loại bỏ các khái niệm IoC, DI, lifecycle, HTTP và transaction.

### “Cứ thêm starter là tính năng đã hoạt động đúng”

Không chắc. Starter cung cấp các dependency thích hợp, còn auto-configuration phụ thuộc điều kiện. Ví dụ, một ứng dụng dùng JPA vẫn cần kết nối đến database và mô hình dữ liệu; cấu hình thiếu có thể khiến ứng dụng không khởi động. Thêm Spring Security cũng đòi hỏi hiểu quy tắc xác thực và phân quyền mong muốn.

### “Auto-configuration khiến ứng dụng không thể tùy chỉnh”

Không đúng. Có thể thay đổi thuộc tính, cung cấp bean tùy chỉnh, điều chỉnh cấu hình theo cách được Spring/Boot hỗ trợ, hoặc loại trừ auto-configuration khi thực sự cần. Cái giá là người phát triển phải hiểu cấu hình mặc định đang làm gì trước khi thay đổi nó.

Khi cần tìm lý do một cấu hình tự động được áp dụng hoặc bị bỏ qua, có thể khởi chạy cùng tham số:

~~~bash
java -jar target/demo-0.0.1-SNAPSHOT.jar --debug
~~~

Trong điều kiện phù hợp, Boot ghi thông tin **condition evaluation report** giúp điều tra các quyết định auto-configuration. Báo cáo này phục vụ chẩn đoán, không thay thế việc đọc exception và kiểm tra dependency.

### “Dùng Spring Boot thì mặc nhiên an toàn, nhanh và dễ mở rộng”

Không. Boot tạo nền tảng thuận tiện, nhưng bảo mật còn phụ thuộc vào dependency, cấu hình, kiểm soát truy cập, cách xử lý secret và thiết kế ứng dụng. Hiệu năng và khả năng mở rộng còn phụ thuộc vào mô hình dữ liệu, thuật toán, truy vấn, I/O, cấu hình tài nguyên và kiến trúc triển khai.

Ứng dụng có thể chạy trong một JAR nhưng vẫn cần reverse proxy, TLS, cấu hình container, logging, theo dõi sức khỏe và quy trình cập nhật. Boot không tự tạo một hệ thống phân tán hoặc cơ chế scale phù hợp cho mọi trường hợp.

### “Spring Boot chỉ dành cho microservice hoặc ứng dụng web”

Không. Boot thường được dùng cho REST API và dịch vụ web, nhưng cũng có thể phục vụ ứng dụng batch, xử lý message, tác vụ nền hoặc chương trình dòng lệnh. Có hay không có web server phụ thuộc vào dependency và cấu hình của từng ứng dụng.

Ngược lại, nếu chỉ viết một chương trình Java rất nhỏ, không cần Spring container hay hệ thống cấu hình, việc đưa cả Spring Boot vào có thể là chi phí không cần thiết. Cần chọn công cụ theo nhu cầu thay vì mặc định mọi dự án Java đều phải dùng Boot.

## 9. Khi nào nên chọn Spring Boot?

Spring Boot đặc biệt hữu ích khi dự án cần một hoặc nhiều khả năng sau:

- Xây dựng REST API, web backend hoặc dịch vụ kết nối với các hệ thống khác.
- Dùng IoC/DI, Spring MVC, Spring Data, Spring Security hay các mô-đun thuộc hệ sinh thái Spring.
- Khởi tạo và duy trì nhiều dịch vụ với cấu trúc, dependency và cách chạy tương đối thống nhất.
- Cấu hình cho nhiều môi trường, đóng gói thành executable JAR và tích hợp vào quy trình CI/CD.
- Dùng các công cụ quan sát tình trạng và kiểm thử tích hợp theo quy ước chung.

Đổi lại, nhóm cần hiểu vòng đời Spring context, các cấu hình tự động được kích hoạt và tác động của dependency. Những quy ước tiện lợi mang lại hiệu quả lớn nhất khi mọi người **biết tại sao cấu hình mặc định phù hợp**, đồng thời biết cách thay đổi nó có chủ đích.

Một cách ra quyết định thực tế là hỏi: *Ứng dụng có đang dành đáng kể công sức để lắp ghép framework và hạ tầng mà Spring Boot đã hỗ trợ tốt không?* Nếu có, Boot thường là lựa chọn đáng cân nhắc. Nếu ứng dụng gần như chỉ cần Java chuẩn, một giải pháp nhỏ hơn có thể đủ.

## 10. Tự kiểm tra mức hiểu

**Câu 1.** Có phải Spring Boot thay thế Spring Framework?

**Trả lời:** Không. Boot xây dựng trên Spring Framework, giúp chọn dependency, cấu hình mặc định và khởi chạy ứng dụng Spring thuận tiện hơn. IoC container, DI, Spring MVC và nhiều cơ chế nền tảng vẫn thuộc Spring Framework.

**Câu 2.** Tại sao thêm `spring-boot-starter-web` lại giúp xây REST API nhanh hơn?

**Trả lời:** Starter đưa vào nhóm thư viện web thường cần. Kết hợp với auto-configuration của Boot, ứng dụng có thể có Spring MVC, bộ chuyển đổi JSON và embedded server phù hợp mà không phải tự lắp ghép từng thành phần trong trường hợp thông dụng.

**Câu 3.** Nếu muốn chạy cùng JAR ở cổng khác mà không build lại thì làm gì?

**Trả lời:** Truyền cấu hình từ bên ngoài, chẳng hạn `--server.port=9090` khi chạy JAR hoặc biến môi trường `SERVER_PORT`. Đây là ứng dụng của externalized configuration.

**Câu 4.** Sau khi dùng Spring Boot, phần nào vẫn cần lập trình viên chịu trách nhiệm?

**Trả lời:** Thiết kế API, luật nghiệp vụ, dữ liệu, phân quyền, kiểm soát lỗi, kiểm thử phù hợp, vận hành an toàn và các quyết định hiệu năng. Spring Boot hỗ trợ hạ tầng và quy ước, không quyết định tính đúng đắn của sản phẩm.

**Câu 5.** Vì sao chỉ thêm một dependency mới có thể thay đổi cách ứng dụng khởi động?

**Trả lời:** Nhiều auto-configuration của Boot xét điều kiện trên classpath và bean. Dependency mới có thể làm một số điều kiện trở thành đúng hoặc thay đổi tập bean được tạo, vì thế cần hiểu chức năng của starter và theo dõi cấu hình khi thay đổi dependency.

## Kết luận

Spring Boot giải quyết một vấn đề thường gặp khi phát triển Java: **trước khi viết được nhiều chức năng, nhóm đã phải dành công sức tích hợp thư viện, cấu hình framework, dựng server, đóng gói và chuẩn bị vận hành**. Bằng starter, dependency management, auto-configuration, embedded server và cơ chế cấu hình tập trung, Boot giúp rút ngắn quãng đường từ ý tưởng đến một ứng dụng Spring có thể chạy và kiểm thử.

Giá trị của Spring Boot nằm ở việc **giảm công việc hạ tầng lặp lại và tạo ra một nền tảng phát triển nhất quán**. Hiểu rõ điều này giúp bạn sử dụng các mặc định của Boot hiệu quả, nhận ra khi nào phải cấu hình thêm, và phân biệt được phần việc framework hỗ trợ với phần thiết kế phần mềm mà chính mình phải đảm nhận.

