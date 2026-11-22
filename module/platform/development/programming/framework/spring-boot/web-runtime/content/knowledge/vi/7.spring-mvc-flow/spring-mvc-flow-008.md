# HandlerExceptionResolver và chuỗi xử lý ngoại lệ trong Spring MVC

## 1. Mục tiêu bài học

Khi một controller Spring MVC gặp lỗi, việc bắt exception chỉ là một phần của quá trình biến lỗi thành **HTTP response**. Spring MVC có cơ chế trung tâm tên **HandlerExceptionResolver** để chuyển ngoại lệ phát sinh khi ánh xạ hoặc thực thi handler thành phản hồi HTTP có trạng thái, header và body phù hợp.

Sau bài này, bạn có thể:

1. Vẽ được luồng từ **DispatcherServlet** qua **HandlerExceptionResolver** tới HTTP response hoặc Servlet error dispatch.
2. Phân biệt **ExceptionHandlerExceptionResolver**, **ResponseStatusExceptionResolver**, **DefaultHandlerExceptionResolver** và resolver tùy chỉnh.
3. Dùng **@ExceptionHandler** trong controller và **@RestControllerAdvice** để quy định lỗi API.
4. Hiểu thứ tự ưu tiên của nhiều resolver, nhiều advice, root exception và nested cause.
5. Dùng **ProblemDetail**, **ResponseEntityExceptionHandler** và HTTP status code nhất quán.
6. Nhận biết lỗi xảy ra ở **Filter/Spring Security** hoặc sau khi response đã commit vốn cần cơ chế riêng.
7. Viết ứng dụng **Spring Boot 3.5, Java 17+** và kiểm tra lỗi thành công bằng curl hoặc MockMvc.

Phạm vi chính là **Spring MVC trên Servlet stack** (thường dùng embedded Tomcat). **Spring WebFlux** có cơ chế exception handling riêng, không được đồng nhất với HandlerExceptionResolver của MVC.

## 2. Ngoại lệ phát sinh ở đâu trong luồng Spring MVC?

Một HTTP request thông thường đi qua các tầng sau:

~~~mermaid
flowchart TD
    A[HTTP client] --> B[Servlet Filter chain]
    B --> C[DispatcherServlet]
    C --> D[HandlerMapping và HandlerAdapter]
    D --> E[Controller]
    E --> F[Service / Repository]
    F --> G{Có exception?}
    G -->|Không| H[HttpMessageConverter / View]
    G -->|Có| I[HandlerExceptionResolver chain]
    I --> J{Một resolver xử lý được?}
    J -->|Có| K[Status / Headers / Body / View]
    J -->|Không| L[Exception tiếp tục lên Servlet container]
    L --> M[Error dispatch /error nếu cấu hình]
    H --> N[HTTP response]
    K --> N
    M --> N
~~~

Trong Spring MVC, khi một exception phát sinh trong quá trình **mapping hoặc xử lý handler**, DispatcherServlet gọi các HandlerExceptionResolver theo thứ tự cấu hình. Các resolver có thể xử lý bằng exception-handler method, gắn HTTP status, tạo lỗi chuẩn của Spring MVC hoặc trả về view lỗi.

**Ba tầng cần phân biệt:**

- **Controller/handler:** nơi exception được ném, ví dụ không tìm thấy sản phẩm.
- **HandlerExceptionResolver:** bộ máy của Spring MVC có cơ hội chuyển exception thành HTTP response.
- **Servlet container và Spring Boot /error:** cơ chế xử lý cuối khi exception chưa được giải quyết hoặc container thực hiện error dispatch.

Nếu một resolver đã xử lý exception, yêu cầu không nhất thiết đi tiếp đến cơ chế /error. Ngược lại, HTTP status 404/500 và body ở /error không chứng minh rằng một @ExceptionHandler đã chạy.

## 3. Hợp đồng HandlerExceptionResolver

Interface nằm tại **org.springframework.web.servlet.HandlerExceptionResolver** và có phương thức khái niệm:

~~~java
ModelAndView resolveException(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception exception);
~~~

Đây là chữ ký API để hiểu cách hoạt động; đoạn trên không phải chương trình Java độc lập. Tham số **handler** có thể không xác định khi lỗi xảy ra trước khi tìm được handler.

Giá trị trả về quyết định cách DispatcherServlet tiếp tục:

| Giá trị | Ý nghĩa | Hành vi tiếp theo |
|---|---|---|
| **null** | Resolver chưa xử lý exception | Chuyển sang resolver tiếp theo |
| **new ModelAndView()** | Exception đã được xử lý và không cần render view | Dừng chuỗi resolver; response có thể đã được ghi/status đã thiết lập |
| **ModelAndView có view** | Exception được xử lý và cần render trang lỗi | DispatcherServlet render view được chỉ định |

**Lưu ý:** resolver có thể trực tiếp thiết lập HTTP response và trả ModelAndView rỗng. Vì vậy không phải cứ ModelAndView rỗng là response không có body.

Một exception được coi là **unresolved** khi mọi resolver đều trả null hoặc không thể xử lý. Khi đó exception có thể tiếp tục truyền lên Servlet container; Spring Boot thường cung cấp cấu hình error page trỏ tới **/error**.

## 4. Những HandlerExceptionResolver quan trọng

Spring MVC với cấu hình tiêu chuẩn đăng ký các resolver mặc định. Trong luồng phổ biến, có ba resolver cốt lõi sau đây, theo thứ tự:

### 4.1. ExceptionHandlerExceptionResolver

Resolver này tìm phương thức đánh dấu **@ExceptionHandler**:

- Trước hết xét **@ExceptionHandler** cục bộ trong controller thích hợp.
- Nếu không có phương thức phù hợp, xét các bean **@ControllerAdvice / @RestControllerAdvice** có phạm vi áp dụng.
- Chọn phương thức theo loại exception, độ cụ thể và các quy tắc root/cause, thứ tự advice, điều kiện media type.
- Gọi phương thức, sau đó dùng cơ chế xử lý return value của Spring MVC để tạo body, status, header hoặc view.

Ví dụ:

~~~java
@ExceptionHandler(IllegalArgumentException.class)
public ResponseEntity<String> invalid(IllegalArgumentException ex) {
    return ResponseEntity.badRequest().body("Invalid input");
}
~~~

Đoạn này đặt trong class controller hoặc advice có các import Spring tương ứng. Đây là cách linh hoạt nhất khi API cần định dạng lỗi và thông điệp riêng.

### 4.2. ResponseStatusExceptionResolver

Resolver này xử lý những trường hợp status được biểu diễn bằng **@ResponseStatus** hoặc **ResponseStatusException** theo cấu hình Spring MVC.

Ví dụ định nghĩa exception có trạng thái 404:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class DocumentNotFoundException extends RuntimeException {
    public DocumentNotFoundException(String id) {
        super("Document not found: " + id);
    }
}
~~~

Đây là một class độc lập khi đặt trong file **DocumentNotFoundException.java** với dependency Spring Web; chưa phải một HTTP server tự chạy.

Cũng có thể ném **ResponseStatusException** ở runtime:

~~~java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND, "Document not found");
~~~

**Quan trọng:** @ResponseStatus/ResponseStatusException biểu diễn HTTP status nhưng không tự đồng nghĩa với một JSON body tùy chỉnh. Khi thiết lập **reason** hoặc dùng sendError, Servlet container có thể thực hiện error dispatch. Nếu cần body API có cấu trúc ổn định, dùng ProblemDetail hoặc một exception handler rõ ràng.

### 4.3. DefaultHandlerExceptionResolver

Resolver này biết cách ánh xạ nhiều exception phát sinh từ **hạ tầng Spring MVC** thành HTTP status tương ứng:

| Nhóm lỗi thường gặp | HTTP status điển hình |
|---|---|
| **HttpRequestMethodNotSupportedException** | **405 Method Not Allowed** |
| **HttpMediaTypeNotSupportedException** | **415 Unsupported Media Type** |
| **HttpMediaTypeNotAcceptableException** | **406 Not Acceptable** |
| **MissingServletRequestParameterException** | **400 Bad Request** |
| **MethodArgumentTypeMismatchException** qua lỗi type conversion | **400 Bad Request** |
| **HttpMessageNotReadableException** (JSON body sai cấu trúc) | **400 Bad Request** |
| **NoHandlerFoundException** / **NoResourceFoundException** nếu được phát sinh | **404 Not Found** |

Tùy phiên bản Spring Framework, danh sách exception và cách biểu diễn body có thể khác nhau; bảng minh họa các ánh xạ tiêu biểu.

**Không nên** viết một global handler bắt mọi **Exception** và luôn trả 500, vì nó có thể nuốt các lỗi 400/404/405/415 mà các cơ chế mặc định vốn xử lý đúng.

### 4.4. SimpleMappingExceptionResolver

**SimpleMappingExceptionResolver** ánh xạ tên class exception sang tên **view** (ví dụ trang HTML error). Nó có ích trong ứng dụng MVC render giao diện server-side và thường cần được khai báo tùy mục đích. REST API hiện đại thường phù hợp hơn với **@RestControllerAdvice** và ResponseEntity/ProblemDetail.

### 4.5. Resolver tự viết

Bạn có thể thêm bean implements HandlerExceptionResolver khi thật sự cần logic xử lý ở tầng thấp. Tuy nhiên phần lớn API không cần làm như vậy: **@ExceptionHandler**, **@RestControllerAdvice** và **ResponseEntityExceptionHandler** là các extension point dễ bảo trì hơn.

Một resolver tùy chỉnh nên chỉ xử lý các loại exception mà nó thực sự phụ trách, trả **null** cho loại không thuộc phạm vi, tôn trọng quy tắc response đã commit và tránh ghi body trùng với các resolver sau.

## 5. Thứ tự thực thi và cách chọn handler

### 5.1. Thứ tự các resolver

Với Spring MVC mặc định, bộ ba cốt lõi thường được thử:

~~~text
1. ExceptionHandlerExceptionResolver
       |
       | Không có @ExceptionHandler phù hợp?
       v
2. ResponseStatusExceptionResolver
       |
       | Không xử lý được @ResponseStatus / ResponseStatusException?
       v
3. DefaultHandlerExceptionResolver
       |
       | Vẫn unresolved?
       v
4. Servlet container / error dispatch
~~~

Đây là **thứ tự chuẩn phổ biến**, không phải cấu trúc bất biến trong mọi ứng dụng. Các bean tùy chỉnh có **order** có thể thay đổi thứ tự và các resolver có thể được đặt trong **HandlerExceptionResolverComposite**. Trong Spring, **giá trị order thấp hơn có ưu tiên cao hơn**; một resolver trả kết quả đã xử lý sẽ dừng chuỗi.

### 5.2. Local @ExceptionHandler so với global advice

Khi một controller có phương thức **@ExceptionHandler** phù hợp, nó thường được ưu tiên so với phương thức global trên **@ControllerAdvice**. Ví dụ controller cụ thể có thể trả HTML lỗi theo bố cục riêng trong khi advice toàn ứng dụng trả JSON cho API.

Dùng **@RestControllerAdvice** khi body trả trực tiếp là JSON hoặc ProblemDetail. Nó tương đương chức năng **@ControllerAdvice + @ResponseBody** cho các method được khai báo trong advice.

Khi chỉ cần áp dụng cho một nhóm controller, giới hạn phạm vi:

~~~java
@RestControllerAdvice(basePackages = "com.example.catalog.api")
public class CatalogErrorAdvice {
    // Các @ExceptionHandler chỉ áp dụng trong phạm vi controller phù hợp.
}
~~~

Đoạn này là minh họa annotation, chưa phải một ứng dụng chạy độc lập.

### 5.3. Nhiều @ControllerAdvice: @Order và loại exception

Nếu có nhiều advice, dùng **@Order** hoặc **Ordered** để công bố mức ưu tiên. Một advice ưu tiên cao có thể xử lý **nested cause** trước khi advice ưu tiên thấp xử lý **root exception**.

Bên trong một advice, root match được ưu tiên hơn cause match phù hợp với độ sâu exception. Nhưng trên toàn bộ danh sách nhiều advice, **thứ tự advice** có thể thắng ưu tiên root/cause giữa hai advice khác nhau.

Ví dụ:

~~~java
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class BusinessErrorAdvice {
    // Xử lý lỗi nghiệp vụ cụ thể.
}
~~~

Các import cần có: **org.springframework.core.Ordered**, **org.springframework.core.annotation.Order** và **org.springframework.web.bind.annotation.RestControllerAdvice**.

Tránh đăng ký nhiều @ExceptionHandler cạnh tranh cùng một loại exception trong cùng advice với cùng điều kiện media type. Spring có thể báo mapping mơ hồ và không khởi động được resolver đúng cách.

### 5.4. Exception trong cause chain

Giả sử service ném **new IllegalStateException("wrapper", new IOException("disk"))**. Một handler nhắm **IOException** có thể match nested cause; Spring Framework hỗ trợ tìm cause ở nhiều tầng.

Tuy nhiên việc handler nhận được đối tượng root hay cause qua tham số phụ thuộc cách khai báo. Dùng tham số exception càng cụ thể càng tốt. Đừng ép mọi lỗi vào **@ExceptionHandler(Exception.class)** rồi phân loại bằng chuỗi thông báo; thay vào đó tạo exception nghiệp vụ có kiểu rõ ràng.

Một @ExceptionHandler có thể **ném lại đúng exception ban đầu** để rút khỏi việc xử lý và cho chuỗi resolver tiếp tục. Không coi việc ném một exception mới bất kỳ là cách chuyển tiếp an toàn.

## 6. Tạo HTTP error response chuẩn

Một phản hồi lỗi có ít nhất ba thành phần:

1. **HTTP status**: 400 cho input không hợp lệ, 404 cho resource không tồn tại, 409 cho xung đột, 500 cho lỗi không mong đợi.
2. **Headers**: Content-Type, và khi phù hợp các header đặc biệt như Allow hoặc Retry-After.
3. **Body**: thông tin máy khách có thể hiểu, dùng hợp đồng API nhất quán.

### 6.1. ProblemDetail theo RFC 9457

Spring Framework hiện đại hỗ trợ **ProblemDetail**, là dạng dữ liệu để mô tả một vấn đề HTTP:

~~~json
{
  "type": "about:blank",
  "title": "Product not found",
  "status": 404,
  "detail": "Product 42 was not found",
  "instance": "/api/products/42",
  "errorCode": "PRODUCT_NOT_FOUND"
}
~~~

Các trường chuẩn thường gặp: **type**, **title**, **status**, **detail** và **instance**. **errorCode** là extension property của ứng dụng, không phải trường bắt buộc của RFC.

Khi một handler trả **ProblemDetail**, Spring dùng giá trị **status** để xác định HTTP status, ưu tiên content type **application/problem+json** cho JSON, và có thể tự điền **instance** từ đường dẫn hiện tại nếu chưa đặt.

### 6.2. ErrorResponse và ResponseEntityExceptionHandler

**ErrorResponse** là hợp đồng của Spring để mô tả trạng thái HTTP, headers và ProblemDetail. Một số exception hạ tầng Spring MVC triển khai ErrorResponse.

**ResponseEntityExceptionHandler** là base class thuận tiện cho **@ControllerAdvice**. Nó có các method xử lý lỗi chuẩn như body không đọc được, validation, method sai hoặc media type sai, đồng thời cho phép override những điểm phù hợp để tùy biến.

Spring Boot 3.5 có thể tự cấu hình xử lý chuẩn RFC 9457 khi bật:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

Khi đã bật cấu hình này, Boot có thể tạo một advice/handler mặc định cho những exception MVC built-in; nếu muốn tự xử lý cùng một loại exception, cần kiểm soát **@Order** của advice của bạn so với handler mặc định. Với các lỗi nghiệp vụ riêng, một **@RestControllerAdvice** có handler cụ thể thường là đủ.

**Tránh tạo hai tầng trả lỗi trùng nhau**: vừa cấu hình Boot problem details, vừa mở rộng ResponseEntityExceptionHandler để override toàn bộ mà không kiểm tra thứ tự. Điều đó có thể khiến body và status thay đổi theo advice được chọn.

### 6.3. Cần phân biệt sendError và setStatus

**response.setStatus(404)** chỉ thiết lập mã phản hồi. **response.sendError(404)** báo lỗi cho Servlet container và có thể kích hoạt error page/error dispatch. Khi error dispatch xảy ra, Spring Boot có thể đưa request sang **/error**.

Điều này giải thích tại sao hai endpoint đều trả status 404 nhưng body có thể khác. Đừng suy đoán resolver nào đã chạy dựa vào status đơn thuần; cần đọc log, breakpoint hoặc test HTTP body và headers.

## 7. Ví dụ Spring Boot MVC chạy được

Ví dụ sử dụng **Java 17**, **Spring Boot 3.5.0**, **Maven** và **embedded Tomcat**. Nó minh họa lỗi nghiệp vụ được @ExceptionHandler xử lý, lỗi của MVC được cơ chế ProblemDetail chuẩn xử lý, và response bình thường từ controller.

### 7.1. Cấu trúc dự án

~~~text
exception-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/exceptiondemo/
    │   │   ├── ExceptionDemoApplication.java
    │   │   ├── ProductController.java
    │   │   ├── ProductNotFoundException.java
    │   │   └── ApiExceptionHandler.java
    │   └── resources/application.yml
    └── test/java/com/example/exceptiondemo/
        └── ProductApiTest.java
~~~

### 7.2. Maven pom.xml

~~~xml
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
    <artifactId>exception-demo</artifactId>
    <version>1.0.0</version>

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

Đây là POM cho một ứng dụng hoàn chỉnh. Starter test cung cấp JUnit Jupiter, các công cụ Spring Test và MockMvc phù hợp với Boot 3.5.

### 7.3. Class main

**ExceptionDemoApplication.java**

~~~java
package com.example.exceptiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExceptionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExceptionDemoApplication.class, args);
    }
}
~~~

### 7.4. Controller và lỗi nghiệp vụ

**ProductNotFoundException.java**

~~~java
package com.example.exceptiondemo;

public class ProductNotFoundException extends RuntimeException {
    private final long id;

    public ProductNotFoundException(long id) {
        super("Product " + id + " was not found");
        this.id = id;
    }

    public long getId() {
        return id;
    }
}
~~~

**ProductController.java**

~~~java
package com.example.exceptiondemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping("/{id}")
    public Product find(@PathVariable long id) {
        if (id != 7) {
            throw new ProductNotFoundException(id);
        }
        return new Product(7, "Bút");
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Product create(@RequestBody NewProduct request) {
        if (request.name() == null || request.name().isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        return new Product(8, request.name().trim());
    }

    public record Product(long id, String name) {
    }

    public record NewProduct(String name) {
    }
}
~~~

Giải thích:

- **GET /api/products/7** trả một Product hợp lệ.
- **GET /api/products/42** ném ProductNotFoundException.
- **POST /api/products** với tên rỗng ném IllegalArgumentException.
- **GET /api/products/not-a-number** thất bại khi convert path variable thành long; đây là exception do binding/mapping trong Spring MVC, không do nhánh **if** của controller.

### 7.5. Global handler dùng ProblemDetail

**ApiExceptionHandler.java**

~~~java
package com.example.exceptiondemo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ProblemDetail productMissing(ProductNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, ex.getMessage());
        problem.setTitle("Product not found");
        problem.setProperty("errorCode", "PRODUCT_NOT_FOUND");
        return problem;
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail invalidInput(IllegalArgumentException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, ex.getMessage());
        problem.setTitle("Invalid request");
        problem.setProperty("errorCode", "INVALID_PRODUCT");
        return problem;
    }
}
~~~

Hai handler chỉ phụ trách **exception nghiệp vụ đã xác định**. Không thêm @ExceptionHandler(Exception.class) trả 500 mặc định vì nó có thể che mất cách xử lý các exception hạ tầng.

Khi làm dịch vụ thực tế, đừng đưa trực tiếp ex.getMessage() cho mọi exception. Chỉ dùng thông điệp đã được kiểm soát, không tiết lộ stack trace, câu SQL, secrets hoặc đường dẫn nội bộ. Với lỗi không mong đợi, ghi log có correlation ID và trả thông điệp chung.

### 7.6. Bật xử lý lỗi chuẩn

**application.yml**

~~~yaml
server:
  port: 8080

spring:
  mvc:
    problemdetails:
      enabled: true

server.error.include-message: never
~~~

Đoạn cấu hình dùng YAML hợp lệ: **server.error.include-message** là key dạng dotted property tại cấp gốc, nên có thể được Spring Boot binding. Để dễ đọc hơn, cũng có thể lồng **error.include-message** dưới **server**, miễn không tạo trùng key. Cấu hình này hạn chế hiển thị thông điệp lỗi mặc định không kiểm soát trong các error response đi qua Boot /error.

### 7.7. Chạy ứng dụng

Cần JDK 17 trở lên và Maven. Tại thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Hoặc đóng gói:

~~~bash
mvn clean package
java -jar target/exception-demo-1.0.0.jar
~~~

**Kiểm tra request thành công**

~~~bash
curl -i http://localhost:8080/api/products/7
~~~

Status mong đợi: **HTTP 200**. Body JSON mong đợi:

~~~json
{"id":7,"name":"Bút"}
~~~

**Kiểm tra lỗi không tìm thấy sản phẩm**

~~~bash
curl -i http://localhost:8080/api/products/42
~~~

Status mong đợi: **HTTP 404**; Content-Type thường là **application/problem+json**. Body gồm các trường sau (giá trị **instance** được Spring bổ sung theo request path):

~~~json
{
  "type": "about:blank",
  "title": "Product not found",
  "status": 404,
  "detail": "Product 42 was not found",
  "instance": "/api/products/42",
  "errorCode": "PRODUCT_NOT_FOUND"
}
~~~

Thứ tự các key JSON không có ý nghĩa và có thể thay đổi. Điều cần kiểm tra là HTTP status, Content-Type và giá trị của từng trường.

**Kiểm tra lỗi binding**

~~~bash
curl -i http://localhost:8080/api/products/not-a-number
~~~

Status mong đợi: **HTTP 400**. Khi đã bật Problem Details, phản hồi có thể là **application/problem+json** do cơ chế MVC/Boot xử lý. Lỗi này phát sinh khi Spring cố chuyển chuỗi thành số, trước khi thực thi thân controller. Không được trả 500 vì đó là lỗi input.

**Kiểm tra phương thức không được hỗ trợ**

~~~bash
curl -i http://localhost:8080/api/products
~~~

Ở ví dụ này **/api/products** chỉ có POST handler. GET vào đường dẫn đó thường trả **HTTP 405 Method Not Allowed**, có thể kèm header **Allow** liệt kê phương thức được hỗ trợ.

**Kiểm tra POST dữ liệu hợp lệ**

Trên Bash:

~~~bash
curl -i -H 'Content-Type: application/json' \
  -d '{"name":"Sách"}' \
  http://localhost:8080/api/products
~~~

Status mong đợi: **HTTP 200** (vì controller trả trực tiếp Product và không khai báo @ResponseStatus(CREATED)). Body:

~~~json
{"id":8,"name":"Sách"}
~~~

Muốn trả 201 Created với API tạo tài nguyên thật, hãy dùng **ResponseEntity.created(location).body(product)**, tạo Location URI đúng, và bảo đảm tài nguyên đã được lưu.

**Kiểm tra POST tên không hợp lệ**

~~~bash
curl -i -H 'Content-Type: application/json' \
  -d '{"name":"  "}' \
  http://localhost:8080/api/products
~~~

Status mong đợi **HTTP 400**; ProblemDetail có **errorCode=INVALID_PRODUCT**.

**Kiểm tra lỗi JSON malformed**

~~~bash
curl -i -H 'Content-Type: application/json' \
  --data-binary '{"name":' \
  http://localhost:8080/api/products
~~~

Status mong đợi: **HTTP 400** vì JSON body không đọc được. Cơ chế hạ tầng có thể xử lý **HttpMessageNotReadableException** trước khi controller được gọi.

Các lệnh curl nhiều dòng phía trên dùng Bash. Trên Windows PowerShell, có thể dùng **curl.exe** và file payload UTF-8 để tránh rắc rối escape dấu nháy.

## 8. Kiểm thử tự động bằng MockMvc

**ProductApiTest.java**

~~~java
package com.example.exceptiondemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ProductApiTest {

    @Autowired
    MockMvc mvc;

    @Test
    void found() throws Exception {
        mvc.perform(get("/api/products/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Bút"));
    }

    @Test
    void missingProductIsProblemDetail() throws Exception {
        mvc.perform(get("/api/products/42"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.errorCode").value("PRODUCT_NOT_FOUND"))
            .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void typeMismatchIsClientError() throws Exception {
        mvc.perform(get("/api/products/not-a-number"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidNameIsClientError() throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"   \"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errorCode").value("INVALID_PRODUCT"));
    }

    @Test
    void unsupportedMethodIs405() throws Exception {
        mvc.perform(get("/api/products"))
            .andExpect(status().isMethodNotAllowed());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Khi các test đều đạt, Maven Surefire kết thúc với trạng thái thành công và không có test failure. Log tổng kết phụ thuộc Maven plugin; bài không giả định một stdout cố định.

Điểm quan trọng của test:

- Test lỗi phải so **HTTP status**, **media type** và trường **errorCode**, không chỉ kiểm tra có exception được ném.
- **MockMvc** gọi Spring MVC pipeline trong môi trường test, không mở một HTTP socket thật. Để kiểm thử error dispatch của Servlet container, connector và reverse proxy, cần thêm integration test với embedded server chạy cổng thực hoặc test môi trường triển khai.
- Không khẳng định mọi response lỗi của Boot đều có cùng body nếu chưa xác nhận cấu hình **spring.mvc.problemdetails.enabled** và các advice đang đăng ký.

## 9. Khi nào nên mở rộng ResponseEntityExceptionHandler?

Nếu API cần định dạng chung cho cả lỗi nghiệp vụ và lỗi **Spring MVC framework** như JSON malformed, validation, type mismatch, có thể tạo advice extends **ResponseEntityExceptionHandler**.

Ví dụ minh họa sau **không cài cùng lúc như một advice mới bên cạnh handler mặc định khác nếu chưa thiết kế thứ tự**, nhằm tránh handler cạnh tranh:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@ControllerAdvice
public class JsonErrorAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, "Malformed JSON request");
        problem.setTitle("Invalid JSON");
        return handleExceptionInternal(ex, problem, headers, status, request);
    }
}
~~~

Đây là đoạn minh họa cần đặt trong package ứng dụng và cài đúng dependencies. Nếu ứng dụng đã bật problem details của Boot, có thể ưu tiên tạo **@RestControllerAdvice** riêng với @ExceptionHandler cụ thể và **@Order** cao hơn handler Boot cho trường hợp thực sự cần override. Không nên kết hợp tất cả chiến lược theo thói quen.

Ưu điểm khi extends base class là có thể kế thừa nhiều xử lý exception hạ tầng, rồi override những hook cần thiết. Nhược điểm là dễ trùng với advice hiện có nếu kiến trúc không thống nhất.

## 10. Giới hạn của HandlerExceptionResolver

### 10.1. Exception ở Servlet Filter và Spring Security

Một exception phát sinh trong **Filter trước khi DispatcherServlet được gọi** không tự động đi qua chuỗi HandlerExceptionResolver của Spring MVC. Ví dụ authentication/authorization error của Spring Security thường được xử lý ở filter chain, thông qua **ExceptionTranslationFilter**, **AuthenticationEntryPoint** hoặc **AccessDeniedHandler** thích hợp.

Vì thế một @RestControllerAdvice xử lý **AccessDeniedException** không bảo đảm sẽ nhận được mọi lỗi 401/403 của Spring Security.

Nếu muốn tái sử dụng định dạng lỗi giữa filter và MVC, phải chủ động thiết kế điểm tích hợp hoặc dùng handler bảo mật tương ứng. Không tự bắt mọi lỗi trong Filter và trả status 200 kèm JSON báo lỗi.

### 10.2. Endpoint không tồn tại và static resources

Khi một URL không có controller tương ứng, Spring MVC có thể phát sinh **NoHandlerFoundException** nếu cấu hình tạo exception. Nhưng trong ứng dụng Boot, mapping tài nguyên tĩnh có thể nhận một phần các đường dẫn; nếu file tĩnh không tìm thấy, có thể phát sinh **NoResourceFoundException**. Các ứng dụng khác có thể đi tới **/error**.

Vì thế **không đảm bảo** rằng một **@ExceptionHandler(NoHandlerFoundException.class)** sẽ xử lý mọi 404. Hãy test cụ thể với cấu hình static resources, Boot version và route thực tế.

### 10.3. Response đã được commit

Nếu response body hoặc headers đã được flush/commit, server có thể không thể thay status hoặc viết một body lỗi mới. Trường hợp có streaming response, gửi file lớn hoặc lỗi xảy ra sau khi đã gửi một phần dữ liệu, resolver có thể không còn khả năng tạo JSON lỗi chuẩn.

Không cố ghi body lỗi lần hai vào một response đã commit. Kiểm tra log, metric và kết nối, đồng thời xem xét cơ chế streaming đặc thù.

### 10.4. Async và exception ở luồng khác

Với asynchronous request hoặc các công việc chạy trên thread riêng, exception có thể được đưa lại vào Servlet async dispatch và xử lý tùy cơ chế tích hợp. Nhưng exception ném trong một background task tự tạo không nằm trong request lifecycle **không tự động** đến @ExceptionHandler.

Dùng Future/CompletableFuture hoặc cơ chế async có quản lý rõ ràng, ghi nhận thất bại của tác vụ và thiết kế đường truyền lỗi phù hợp, thay vì kỳ vọng mọi exception đều được giải quyết bởi DispatcherServlet.

### 10.5. WebFlux sử dụng cơ chế khác

Trong WebFlux, cơ chế error handling phụ thuộc mô hình reactive và các abstraction như **WebExceptionHandler**, **ErrorWebExceptionHandler** cùng @ExceptionHandler trong reactive controller. Không triển khai **org.springframework.web.servlet.HandlerExceptionResolver** để mong áp dụng cho Reactor Netty/WebFlux.

## 11. Vận hành và phân loại lỗi thực tế

| Dấu hiệu | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| API trả HTML thay vì JSON | Container error page hoặc Boot /error trả trang HTML theo Accept | Xem Accept, Content-Type, /error và cấu hình problem details |
| Lỗi nghiệp vụ thành 500 | Thiếu @ExceptionHandler phù hợp; exception bị wrap không khớp | Kiểm tra loại root/cause, package scan, advice scope |
| Lỗi 400/405 biến thành 500 | Handler catch-all nuốt exception hạ tầng | Loại handler quá rộng, giữ xử lý mặc định của Spring |
| Exception handler không chạy | Exception xảy ra trong Filter hoặc trước DispatcherServlet | Xem Servlet Filter chain và Spring Security |
| Handler gọi sai khi có nhiều advice | @Order, điều kiện media type hoặc exception mapping cạnh tranh | Kiểm tra order, selector và mapping từng advice |
| Một 404 không vào NoHandlerFoundException | Static resource handler hoặc Boot error dispatch | Kiểm tra NoResourceFoundException và mapping /error |
| Log trùng lỗi hoặc body bị ghi hai lần | Logging ở nhiều tầng, response đã commit | Chỉ log tại ranh giới phù hợp và kiểm tra isCommitted |
| Lộ thông tin nhạy cảm | Trả ex.getMessage() của lỗi nội bộ | Map thông điệp an toàn, không trả SQL/stack trace |
| API thay đổi body theo môi trường | Config bật/tắt ProblemDetail hoặc khác Boot version | Kiểm tra properties, dependency và integration test |

### Logging và observability

- Với lỗi **4xx dự kiến**, có thể log thông tin hữu ích ở mức phù hợp mà không tạo tiếng ồn hoặc log dữ liệu nhạy cảm.
- Với lỗi **5xx bất ngờ**, log exception và correlation/request ID ở ranh giới xử lý. Tránh ghi nhiều stack trace cùng một lỗi qua controller, service và filter.
- Dùng metrics theo status, endpoint và loại lỗi; quan sát tỷ lệ 4xx/5xx, latency và các đợt tăng đột biến.
- Giữ hợp đồng phản hồi ổn định: mã HTTP và **errorCode** cho client, chi tiết nội bộ ở log.
- Không gửi tên class nội bộ, SQL, access token, mật khẩu hay stack trace trong ProblemDetail trả về ngoài.

## 12. Nguyên tắc thiết kế chuỗi xử lý lỗi

1. **Định nghĩa exception nghiệp vụ có ý nghĩa**, ví dụ ProductNotFoundException, DuplicateOrderException, InsufficientBalanceException.
2. **Ánh xạ chính xác sang HTTP status** bằng handler cụ thể. Tránh một catch-all trả mã giống nhau cho mọi lỗi.
3. **Dùng ProblemDetail hoặc DTO nhất quán** cho REST API; phân biệt lỗi có thể phục hồi và lỗi hệ thống.
4. **Giữ handler hạ tầng** của Spring MVC cho các lỗi framework, trừ khi đã có lý do rõ ràng để override.
5. **Kiểm soát @Order**, phạm vi advice và khả năng root/cause matching khi có nhiều advice.
6. **Không dùng exception cho nhánh nghiệp vụ bình thường** nếu có kết quả kiểu rõ ràng phù hợp hơn.
7. **Tách lỗi filter/security khỏi MVC** để phân quyền và xác thực không bị xử lý sai.
8. **Xử lý response commit/async đúng vòng đời**, không ghi thêm body sau khi đã gửi.
9. **Test status, headers, body và thông điệp an toàn** trong cả MockMvc và môi trường HTTP thực.
10. **Duy trì tài liệu API** để client biết 400, 404, 409, 422, 500 hay 503 mang ý nghĩa gì đối với nghiệp vụ cụ thể.

## 13. Tài liệu chính thức

1. Spring Framework – Exception resolvers trong DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
2. Spring Framework – @ExceptionHandler, root/cause và nhiều advice: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
3. Spring Framework – @ControllerAdvice và @RestControllerAdvice: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html
4. Spring Framework – Error Responses, ProblemDetail và ResponseEntityExceptionHandler: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
5. Spring Boot 3.5 – Servlet web applications, mục Error Handling: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
6. Spring Boot 3.5 – Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
7. RFC 9457 – Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457

**Kết luận:** HandlerExceptionResolver là chuỗi giải quyết lỗi ở tầng **DispatcherServlet**, trong đó ExceptionHandlerExceptionResolver xử lý @ExceptionHandler, ResponseStatusExceptionResolver xử lý status từ exception và DefaultHandlerExceptionResolver xử lý lỗi hạ tầng MVC. Spring Boot có thêm cơ chế **/error** của Servlet container. Thiết kế tốt cần chọn đúng resolver/advice, đặt status chính xác, trả body chuẩn, kiểm soát bảo mật và kiểm thử đường lỗi thực tế.
