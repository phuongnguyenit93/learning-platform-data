# Kiến thức cần có: Java, IoC/DI, HTTP và xử lý đồng thời

Trước khi học **Spring Framework Web**, cần nối bốn mảng kiến thức: Java diễn tả đối tượng và hành vi; IoC/DI giúp Spring khởi tạo, ghép và quản lý các đối tượng; HTTP quy định cách client và server trao đổi thông điệp; xử lý đồng thời quyết định điều gì xảy ra khi nhiều request đi vào cùng lúc. Hiểu các nền tảng này sẽ giúp đọc controller, service và lỗi ứng dụng theo cơ chế thực tế, thay vì chỉ ghi nhớ annotation.

## 1. Bức tranh tổng thể của một yêu cầu web

Một yêu cầu đi qua các lớp trách nhiệm điển hình:

```text
Client (trình duyệt, curl, ứng dụng khác)
    │  HTTP request: method + URL + headers + body (nếu có)
    ▼
Web server / Servlet container
    ▼
Spring MVC DispatcherServlet
    ▼
Handler mapping → Controller → Service → (Repository / hệ thống ngoài)
    ▲                     │          │
    │                     └── Spring DI cung cấp dependency
    └── HTTP response: status + headers + body
```

Đây là sơ đồ khái niệm cho **Spring MVC truyền thống**. Bộ điều phối tìm handler phù hợp; tầng controller xử lý phần giao tiếp HTTP; service chứa hành vi nghiệp vụ; framework chuyển đổi dữ liệu giữa JSON và đối tượng Java qua HTTP message converter. Các thành phần có thể được nhiều request sử dụng đồng thời.

Bạn cần trả lời được bốn câu: đối tượng Java biểu diễn request/response như thế nào; ai tạo và nối controller với service; một request HTTP hợp lệ gồm gì; và liệu service có an toàn khi nhiều luồng gọi cùng lúc hay không.

## 2. Nền tảng Java cần nắm

### 2.1. Class, object, interface, constructor và phạm vi truy cập

- **Class** mô tả dữ liệu và phương thức; **object** là một thể hiện của class. Hai request có thể gọi cùng một object service.
- **Interface** mô tả hợp đồng hành vi. Code phụ thuộc interface giúp thay triển khai và viết test mà không buộc caller biết chi tiết.
- **Constructor** tạo trạng thái hợp lệ ban đầu. Spring thường dùng constructor để truyền dependency đã được quản lý.
- `private` che trạng thái triển khai; `final` trên field ngăn gán lại tham chiếu sau khi khởi tạo. `final` không tự làm cho đối tượng được tham chiếu trở thành bất biến.
- **Method parameter và local variable** là dữ liệu của từng lần gọi. Field của bean singleton là trạng thái có thể được chia sẻ giữa các lần gọi.

Ví dụ DI thuần Java dưới đây chạy độc lập, chưa cần Spring. File `ConstructorDiDemo.java`:

```java
interface Formatter {
    String format(String name);
}

final class VietnameseFormatter implements Formatter {
    @Override
    public String format(String name) {
        return "Xin chào, " + name + "!";
    }
}

final class WelcomeService {
    private final Formatter formatter;

    WelcomeService(Formatter formatter) {
        this.formatter = formatter;
    }

    String welcome(String name) {
        return formatter.format(name);
    }
}

public class ConstructorDiDemo {
    public static void main(String[] args) {
        Formatter formatter = new VietnameseFormatter();
        WelcomeService service = new WelcomeService(formatter);
        System.out.println(service.welcome("Lan"));
    }
}
```

Chạy với JDK 17+:

```bash
javac ConstructorDiDemo.java
java ConstructorDiDemo
```

Kết quả:

```text
Xin chào, Lan!
```

`WelcomeService` sử dụng `Formatter` do nơi khác cung cấp qua constructor; nó không tự khởi tạo `VietnameseFormatter`. Đó là cơ chế **dependency injection**, ngay cả khi chưa có container.

### 2.2. Dữ liệu, generics, record, exception và annotation

- `String`, primitive, `List<T>`, `Map<K,V>` và `Optional<T>` là các kiểu thường xuất hiện trong request handler và service. Generics giúp compiler kiểm tra kiểu; `List<String>` biểu diễn tập phần tử khác với `String`.
- `record` (Java 16+, dùng được ở Java 17) thích hợp cho DTO đơn giản: compiler sinh constructor chuẩn, accessor, `equals`, `hashCode` và `toString`. Record ngăn gán lại các thành phần của record, nhưng không tự bảo đảm bất biến sâu nếu chứa collection mutable.
- Checked exception buộc khai báo/xử lý theo quy tắc ngôn ngữ; runtime exception không có yêu cầu đó. Trong ứng dụng web, một exception chưa được xử lý có thể dẫn tới HTTP 500; muốn chuyển thành mã lỗi nghiệp vụ cần cơ chế xử lý tương ứng.
- Annotation như `@Override` là metadata gắn vào khai báo. Spring đọc các annotation như `@Controller`, `@Service`, `@GetMapping` theo cơ chế của framework; viết annotation đơn thuần không làm một class trở thành HTTP endpoint nếu không được Spring đăng ký.
- Phân biệt **tham chiếu**, **giá trị** và **khả năng thay đổi trạng thái**. Java truyền đối số theo giá trị, kể cả khi giá trị đó là tham chiếu đến object; truyền tham chiếu không tạo bản sao độc lập của object.

Ví dụ DTO:

```java
record GreetingRequest(String name) {}
record GreetingResponse(String message) {}
```

Trong request JSON `{"name":"Lan"}`, tên khóa cần khớp cách ánh xạ của bộ chuyển đổi JSON. Đừng mặc định mọi lỗi dữ liệu đầu vào sẽ bị chặn: kiểm tra ràng buộc như chuỗi rỗng, null, độ dài và định dạng là bước riêng của validation.

## 3. IoC và DI trong Spring

### 3.1. IoC là quyền kiểm soát vòng đời; DI là cách truyền dependency

**Inversion of Control (IoC)** nghĩa là code ứng dụng giao cho một cơ chế bên ngoài quyền tạo, cấu hình và ghép các thành phần. Trong Spring, `ApplicationContext` là container quản lý các **bean**. **Dependency Injection (DI)** là cách container cung cấp đối tượng mà bean cần, thường qua constructor.

Không có DI, một service có thể tự `new` dependency cụ thể, khiến việc thay triển khai khó hơn. Với constructor injection, dependency là một yêu cầu rõ ràng của class và có thể cung cấp một fake khi unit test.

Một luồng tạo đối tượng điển hình:

```text
Spring khởi động → quét cấu hình/component → đăng ký bean
             → giải dependency → gọi constructor → bean sẵn sàng phục vụ
```

Các annotation stereotype hay gặp:

| Annotation | Vai trò thường gặp |
| --- | --- |
| `@Component` | Bean Spring tổng quát |
| `@Service` | Bean ở tầng nghiệp vụ; một dạng chuyên biệt của `@Component` |
| `@Repository` | Bean tầng truy cập dữ liệu; hỗ trợ cơ chế chuyển đổi một số exception truy cập dữ liệu |
| `@Controller` | Controller MVC, thường dùng với view |
| `@RestController` | Kết hợp `@Controller` và `@ResponseBody`; kết quả được ghi vào HTTP response body |

Cần có cấu hình đăng ký bean phù hợp (component scan hoặc khai báo `@Bean`). Spring Boot thường cung cấp cấu hình khởi đầu, nhưng vị trí package scan vẫn ảnh hưởng việc tìm thấy class.

### 3.2. Chọn constructor injection

```java
@Service
class GreetingService {
    String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}

@RestController
class GreetingController {
    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/hello")
    String hello(@RequestParam(defaultValue = "bạn") String name) {
        return greetingService.greet(name);
    }
}
```

Đoạn này **minh họa trong ứng dụng Spring MVC**; nó chưa phải chương trình Java độc lập vì phụ thuộc thư viện Spring, việc đăng ký bean và ứng dụng khởi động. Khi class chỉ có một constructor, Spring không yêu cầu `@Autowired` trên constructor đó.

`GreetingController` chỉ biết nó cần `GreetingService`. Trong unit test có thể truyền trực tiếp một service hoặc tách interface và truyền stub/fake. Một bean không được đăng ký sẽ gây lỗi giải dependency khi khởi động; nhiều bean phù hợp cùng một kiểu có thể cần `@Qualifier` hoặc `@Primary`.

### 3.3. Scope và vòng đời ảnh hưởng trực tiếp đến concurrency

**Singleton** là bean scope mặc định: trong một Spring container, thông thường một bean definition sinh ra một object được tái sử dụng. Nó **không đồng nghĩa** với singleton JVM toàn cục và **không đồng nghĩa** thread-safe. Một controller singleton phục vụ nhiều request đồng thời; lưu tên người dùng hoặc bộ đếm chưa đồng bộ vào field của nó có thể gây lỗi.

Scope `prototype` tạo đối tượng mới mỗi lần container được yêu cầu lấy bean theo scope đó; các scope request/session phụ thuộc web context. Đổi scope không phải cách tự động sửa mọi lỗi concurrency. Trạng thái theo từng request nên được truyền bằng tham số, local variable hoặc một abstraction quản lý phạm vi phù hợp.

## 4. HTTP: ngôn ngữ trao đổi giữa client và server

### 4.1. Cấu trúc request và response

Một HTTP request gồm phương thức, đường dẫn/tài nguyên đích, header và có thể có body. Một response gồm status, header và có thể có body. Ví dụ dễ đọc (dòng đầu phản ánh dạng HTTP/1.1; HTTP/2 và HTTP/3 có cách truyền trên đường dây khác):

```http
POST /api/greetings HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"name":"Lan"}
```

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"message":"Xin chào, Lan!"}
```

**URL path** như `/api/greetings/42` thường dùng để định danh tài nguyên; **query parameter** như `?lang=vi&page=2` thường biểu diễn lọc, sắp xếp hoặc phân trang; **header** chứa metadata như `Content-Type` hoặc `Authorization`; **body** mang payload. Cần phân biệt `Content-Type` (kiểu biểu diễn được gửi) với `Accept` (kiểu biểu diễn client mong nhận).

HTTP được thiết kế theo mô hình **stateless ở mức request**: mỗi request cần đủ thông tin để xử lý theo giao thức. Ứng dụng vẫn có thể duy trì trạng thái phiên bằng cookie, session hoặc token; đây là lớp cơ chế bổ sung, không phải tính chất lưu trạng thái sẵn có trong từng request.

### 4.2. Method và thuộc tính ngữ nghĩa

| Method | Ý nghĩa điển hình | Safe? | Idempotent? |
| --- | --- | --- | --- |
| `GET` | Lấy biểu diễn tài nguyên | Có | Có |
| `HEAD` | Lấy metadata response như GET, không có response body | Có | Có |
| `POST` | Yêu cầu xử lý/tạo tài nguyên theo ngữ nghĩa endpoint | Không | Không bảo đảm |
| `PUT` | Tạo hoặc thay thế trạng thái tài nguyên tại URI xác định | Không | Có |
| `PATCH` | Sửa một phần tài nguyên | Không | Không bảo đảm |
| `DELETE` | Xóa liên kết/tài nguyên theo ngữ nghĩa endpoint | Không | Có |

**Safe** nghĩa là client không yêu cầu một thay đổi trạng thái có ý nghĩa; log/metric kỹ thuật vẫn có thể phát sinh. **Idempotent** nghĩa là lặp cùng yêu cầu có cùng hiệu ứng dự định lên trạng thái server; các lần gọi không nhất thiết trả cùng status hoặc cùng response body. Ví dụ DELETE lần đầu có thể trả 204, lần sau trả 404 nhưng hiệu ứng "tài nguyên không còn" không thay đổi.

Các thuộc tính này quyết định cách thiết kế API, retry và cache. Đừng đưa thao tác chuyển tiền/xóa dữ liệu vào GET. Nếu cần chống tạo trùng do client gửi lại POST, API có thể thiết kế khóa idempotency và lưu trạng thái xử lý, thay vì cho rằng POST mặc nhiên idempotent.

### 4.3. Status code quan trọng

| Status | Ý nghĩa thường gặp |
| --- | --- |
| `200 OK` | Request thành công, thường có response body |
| `201 Created` | Đã tạo tài nguyên; có thể kèm header `Location` |
| `204 No Content` | Thành công, không có response body |
| `400 Bad Request` | Request không hợp lệ về cú pháp hoặc đầu vào theo xử lý |
| `401 Unauthorized` | Thiếu/không hợp lệ thông tin xác thực cho tài nguyên cần xác thực |
| `403 Forbidden` | Server hiểu request nhưng từ chối cấp quyền |
| `404 Not Found` | Không tìm thấy tài nguyên/endpoint tương ứng |
| `405 Method Not Allowed` | URI tồn tại nhưng method không được hỗ trợ |
| `409 Conflict` | Request xung đột với trạng thái tài nguyên |
| `415 Unsupported Media Type` | Kiểu nội dung gửi lên không được hỗ trợ |
| `500 Internal Server Error` | Lỗi phía server chưa được ánh xạ phù hợp |

Mã 4xx chủ yếu phản ánh lỗi phía request/client; 5xx phản ánh phía server, nhưng phải xem hoàn cảnh cụ thể. Cấu trúc JSON body không tự quyết định status. Cũng đừng nhầm **401 (authentication)** và **403 (authorization)**.

### 4.4. Điều Spring MVC làm giúp bạn

- `@GetMapping`, `@PostMapping`, `@PutMapping` ánh xạ method/đường dẫn đến handler.
- `@PathVariable` lấy giá trị trong đường dẫn; `@RequestParam` lấy query parameter/form parameter tùy trường hợp; `@RequestBody` yêu cầu chuyển body thành đối tượng.
- `@ResponseBody`/`@RestController` giúp serialize giá trị trả về qua message converter; `ResponseEntity<T>` cho phép điều khiển status, header và body.
- Converter JSON (ví dụ Jackson khi có dependency phù hợp) không thay thế validation hay định nghĩa quy tắc nghiệp vụ.
- DispatcherServlet thực hiện điều phối ở tầng web; service không nên bị buộc hiểu `HttpServletRequest` chỉ để làm một phép tính nghiệp vụ.

HTTPS là HTTP qua kết nối được bảo vệ bằng TLS; sử dụng HTTPS không thay thế xác thực, phân quyền, kiểm tra input hoặc cấu hình CORS. CORS là cơ chế do browser thực thi đối với truy cập khác origin, không phải cơ chế phân quyền API nói chung.

## 5. Xử lý đồng thời trong ứng dụng web

### 5.1. Nhiều request, cùng bean

Ở cấu hình Spring MVC dùng Servlet xử lý đồng bộ thông thường, server sử dụng các luồng thực thi để phục vụ nhiều request cùng lúc. Chi tiết còn tùy container, cấu hình, cơ chế async hoặc virtual threads; không nên giả định rằng mỗi kết nối HTTP mãi gắn với một Java thread.

Giả sử hai request gọi một controller singleton:

```java
@RestController
class UnsafeCounterController {
    private int counter = 0;

    @GetMapping("/unsafe-count")
    int next() {
        return ++counter;
    }
}
```

Đây là **mã minh họa lỗi**. `++counter` không phải thao tác nguyên tử; nhiều thread có thể đọc cùng giá trị rồi ghi đè kết quả, làm mất lượt tăng. Ngoài tính nguyên tử, việc đọc/ghi không có cơ chế đồng bộ còn liên quan đến quy tắc visibility của Java Memory Model. Không chữa bằng cách chỉ thêm `volatile`: `volatile` hỗ trợ visibility và thứ tự nhất định, nhưng không biến `++` thành một phép cập nhật nguyên tử.

Giải pháp cho một bộ đếm trong bộ nhớ, ở mức một JVM:

```java
private final AtomicInteger counter = new AtomicInteger();

int next() {
    return counter.incrementAndGet();
}
```

Cần import `java.util.concurrent.atomic.AtomicInteger`. Đây chỉ là một bộ đếm cục bộ. Nhiều instance ứng dụng hoặc yêu cầu cập nhật nhiều bản ghi cần cơ chế nhất quán ở tầng dữ liệu, chẳng hạn atomic database update/transaction. AtomicInteger không giải quyết tự động một giao dịch gồm nhiều bước.

### 5.2. Ví dụ Java 17+ chạy độc lập và có output xác định

File `ConcurrentCounterDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentCounterDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger requests = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> results = new ArrayList<>();
            for (int i = 0; i < 1_000; i++) {
                results.add(pool.submit(() -> {
                    requests.incrementAndGet();
                }));
            }
            for (Future<?> result : results) {
                result.get();
            }
            System.out.println("Tổng yêu cầu: " + requests.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Chạy:

```bash
javac ConcurrentCounterDemo.java
java ConcurrentCounterDemo
```

Output:

```text
Tổng yêu cầu: 1000
```

`ExecutorService` điều phối 1.000 tác vụ trên pool 4 thread; `Future.get()` đợi tác vụ hoàn tất hoặc ném exception nếu tác vụ thất bại; `AtomicInteger.incrementAndGet()` cập nhật nguyên tử nên kết quả là 1.000. Ví dụ dùng pool cố định để mô phỏng các lời gọi đồng thời, **không có nghĩa** Spring MVC luôn dùng đúng cấu hình pool này.

Nếu đổi sang `int` và `requests++` không đồng bộ, kết quả có thể thấp hơn 1.000; tuy nhiên **không được lấy một lần chạy tình cờ ra 1.000 làm bằng chứng code an toàn**. Race condition phụ thuộc lịch chạy nên rất khó tái hiện ổn định.

### 5.3. Quy tắc an toàn khi viết controller/service

- Ưu tiên bean **stateless**: mỗi request đưa input vào method và nhận kết quả; biến cục bộ được tạo cho mỗi lời gọi.
- Với trạng thái phải chia sẻ, xác định phạm vi: một request, một JVM, nhiều instance ứng dụng hay database. Dùng cấu trúc dữ liệu thread-safe, lock hoặc giao dịch phù hợp với phạm vi đó.
- Bất biến và `final` giúp giảm rủi ro nhưng không thay thế thiết kế đồng bộ cho đối tượng mutable được chia sẻ.
- Một số API như `SimpleDateFormat` mutable không được thiết kế dùng chung an toàn; ưu tiên API `java.time` immutable như `DateTimeFormatter` khi phù hợp.
- Blocking I/O chờ database/HTTP ngoài sẽ giữ tài nguyên thực thi trong mô hình đồng bộ. Timeout, giới hạn connection pool, giới hạn tải và quan sát độ trễ quan trọng hơn việc tự thêm `new Thread()` cho từng request.
- Không lưu thông tin request/người dùng vào static field hoặc field singleton. Với `ThreadLocal`, phải hiểu luồng có thể được tái sử dụng và cần cleanup đúng vòng đời; truyền dữ liệu rõ ràng thường dễ kiểm soát hơn.
- **Spring MVC** và **Spring WebFlux** có mô hình thực thi khác nhau; reactive/non-blocking không làm mã nghiệp vụ có mutable shared state tự nhiên trở nên an toàn.

## 6. Ghép bốn kiến thức trong ví dụ Spring MVC

Ví dụ sau cần một **dự án Spring Boot 3.x / Spring Framework 6.x với dependency `spring-boot-starter-web`**, JDK 17+ và build tool đã cấu hình. Các file dưới đây là mã ứng dụng trong project đó, không phải chương trình chạy bằng `javac` thuần nếu chưa có thư viện Spring. Đặt ba file trong `src/main/java/demo/web/`.

`WebPrerequisitesApplication.java`:

```java
package demo.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebPrerequisitesApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebPrerequisitesApplication.class, args);
    }
}
```

`GreetingService.java`:

```java
package demo.web;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

`GreetingController.java`:

```java
package demo.web;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping
    public GreetingResponse read(
            @RequestParam(defaultValue = "bạn") String name) {
        return new GreetingResponse(service.greet(name));
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public GreetingResponse create(@RequestBody GreetingRequest request) {
        return new GreetingResponse(service.greet(request.name()));
    }

    public record GreetingRequest(String name) {}
    public record GreetingResponse(String message) {}
}
```

Với ứng dụng đã khởi động tại localhost:8080, thử:

```bash
curl -i 'http://localhost:8080/api/greetings?name=Lan'
curl -i -X POST 'http://localhost:8080/api/greetings' -H 'Content-Type: application/json' -d '{"name":"Mai"}'
```

Phản hồi GET có status **200** và JSON tương đương `{"message":"Xin chào, Lan!"}`; POST có status **201** và JSON tương đương `{"message":"Xin chào, Mai!"}`. Header thực tế và cách biểu diễn ký tự JSON có thể thay đổi theo môi trường.

Phân tích từng bước:

1. Spring Boot đăng ký `GreetingService` và `GreetingController` nhờ component scanning trong cùng package gốc `demo.web` (**IoC**).
2. Container truyền một `GreetingService` vào constructor của controller (**DI**, Java constructor và `final` field).
3. DispatcherServlet tìm mapping theo path và HTTP method; `@RequestParam` lấy query trên GET, `@RequestBody` chuyển JSON sang Java record trên POST (**HTTP + Java**).
4. Controller gọi method nghiệp vụ và trả một DTO record; Spring serialize thành JSON và gán status (**HTTP response**).
5. Mỗi request tạo dữ liệu local riêng trong method; service không lưu name vào field, nên phần logic này không có shared mutable state do ứng dụng tự tạo (**concurrency**).

Ví dụ cố ý đơn giản: không lưu tài nguyên thực, không chứng minh ý nghĩa "create" của POST trong API production, không xác thực/ủy quyền, không có validation và không xử lý lỗi tùy chỉnh. Nếu nhận `{"name":null}`, logic ví dụ có thể tạo lời chào với chữ `null`; cần bổ sung ràng buộc đầu vào trong bài về validation. Nếu xây API tạo tài nguyên thật, thường cần định danh tài nguyên, trạng thái bền vững và cân nhắc header `Location`.

## 7. Lỗi tư duy phổ biến và cách kiểm tra

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| "Có `@Service` là tự được tiêm ở mọi nơi" | Bean phải nằm trong cấu hình/scan của context; dependency phải giải được |
| "Singleton tương đương thread-safe" | Scope chỉ nói về số instance; field mutable vẫn có race |
| "Field `final` làm cả object bất biến" | `final` chỉ cấm gán lại tham chiếu field; object bên trong có thể mutable |
| "GET và POST chỉ khác tên method" | Ngữ nghĩa safe, idempotent, cache và retry khác nhau |
| "HTTP stateless nghĩa là website không thể có login session" | Cookie/session/token bổ sung cơ chế giữ/xác minh trạng thái |
| "Trả về Java record tức tự có JSON và HTTP 200 trong mọi tình huống" | Cần Spring MVC/message converter, mapping và quy tắc chọn status |
| "Một request luôn có một thread riêng bất biến" | Phụ thuộc container, cấu hình, async và mô hình thực thi |
| "Dùng `volatile int` thì `++` an toàn" | `++` là thao tác đọc-sửa-ghi; cần atomic/lock phù hợp |
| "Chạy test concurrency một lần đúng kết quả là đủ" | Race có thể không xuất hiện ở lần chạy đó; cần thiết kế an toàn và test thích hợp |

Khi debug một endpoint, hãy truy lần lượt: **HTTP method/URL → handler mapping → binding/deserialize → dependency service → hành vi nghiệp vụ → xử lý exception → serialize/status → trạng thái dùng chung giữa request**. Cách lần theo này thường khoanh vùng lỗi nhanh hơn việc thử thay annotation ngẫu nhiên.

## 8. Tự kiểm tra trước khi học Spring Web sâu hơn

1. Nếu `WelcomeService` tự tạo `new VietnameseFormatter()` thay vì nhận `Formatter` từ constructor, khả năng thay implementation khi test thay đổi ra sao?
2. Vì sao `@RestController` có thể là singleton mà vẫn phục vụ nhiều người dùng đúng cách? Điều kiện nào làm nó nguy hiểm?
3. Hãy chỉ ra method, path, header và body trong ví dụ POST. Vì sao `Content-Type` và `Accept` không tương đương?
4. Vì sao cùng một DELETE có thể lần đầu trả 204, lần sau trả 404 mà vẫn giữ thuộc tính idempotent?
5. Nếu hai request đồng thời gọi `++counter`, thao tác nào có thể mất lượt tăng? Tại sao `AtomicInteger` chỉ giải quyết bộ đếm trong một JVM?
6. Trong ví dụ Spring, phần nào do Java cung cấp, phần nào do Spring container, phần nào do HTTP và phần nào phụ thuộc thiết kế concurrency?

**Đạt yêu cầu đầu vào** khi bạn có thể tự giải thích luồng request đi vào controller, đọc một constructor injection, phân biệt dữ liệu theo request với state chia sẻ, chọn HTTP method/status phù hợp và phát hiện field mutable nguy hiểm trong singleton. Khi đó các chủ đề tiếp theo như routing, data binding, validation, exception handling, filter/interceptor và security sẽ có nền tảng rõ ràng.
