# Môi trường thực thi ứng dụng (Application Runtime) trong Spring Boot là gì và quản lý những gì?

## 1. Application runtime là gì?

**Application runtime** là toàn bộ môi trường và các thành phần hoạt động khi một ứng dụng đã được khởi chạy: tiến trình đang chạy, máy ảo Java, cấu hình được nạp, đối tượng ứng dụng, tài nguyên, luồng xử lý, thành phần tiếp nhận công việc và cơ chế dừng ứng dụng. Nói ngắn gọn, đây là **những gì cần có và những gì diễn ra để mã ứng dụng thực sự chạy**, từ lúc khởi động đến lúc kết thúc.

Trong Spring Boot, cần phân biệt ba khái niệm gần nhau:

- **JVM runtime:** JVM thực thi bytecode Java, quản lý bộ nhớ heap, garbage collection, class loading và các luồng Java. JVM không tự hiểu các khái niệm bean, dependency injection hay HTTP controller của Spring.
- **Spring ApplicationContext:** vùng chứa (container) các bean của Spring, phụ trách cấu hình, khởi tạo, nối các dependency và quản lý vòng đời bean.
- **Spring Boot application runtime:** ứng dụng đang chạy với JVM, ApplicationContext và những thành phần được Boot khởi tạo/tự cấu hình, chẳng hạn web server nhúng, data source, executor, scheduler và hệ thống quan sát. Không phải ứng dụng nào cũng có đủ các thành phần này.

Ví dụ, một API Spring Boot nhận HTTP request có một runtime đang mở cổng mạng, xử lý request, sử dụng các bean dịch vụ và có thể truy cập cơ sở dữ liệu. Một chương trình Spring Boot chỉ chạy công việc nền vẫn có runtime và ApplicationContext, nhưng có thể **không có HTTP server**.

## 2. Các lớp tạo nên runtime

| Lớp | Thành phần điển hình | Ai chịu trách nhiệm chính? |
| --- | --- | --- |
| Hệ điều hành / container | Tiến trình, CPU, bộ nhớ khả dụng, file, socket, tín hiệu dừng | OS, container runtime, nền tảng triển khai |
| Java Virtual Machine | Thực thi bytecode, class loading/JIT, heap, GC, luồng Java | JVM |
| Spring Boot bootstrap | Đọc cấu hình, chọn loại ứng dụng, khởi tạo ApplicationContext, áp dụng auto-configuration | Spring Boot và Spring Framework |
| Spring ApplicationContext | Bean definitions, dependency injection, scope, lifecycle, sự kiện ứng dụng | Spring Framework |
| Hạ tầng ứng dụng (nếu cấu hình) | Embedded HTTP server, connection pool, scheduler/executor, transaction manager, security filter chain | Các thư viện tương ứng, được Boot tích hợp/tự cấu hình |
| Logic nghiệp vụ | Controller, service, repository, quy tắc và dữ liệu nghiệp vụ | Mã do nhóm phát triển viết |

Sơ đồ khái quát:

~~~text
Hệ điều hành / Container
    └── Tiến trình java / JVM
          └── SpringApplication.run(...)
                └── Spring ApplicationContext
                      ├── Bean ứng dụng (Controller, Service, Repository, ...)
                      ├── Bean hạ tầng (DataSource, Executor, ...)
                      └── Web server nhúng (nếu là ứng dụng web)
~~~

**Lưu ý:** Spring Boot giúp tạo và cấu hình các thành phần. Nó không thay thế JVM trong việc cấp phát heap/GC, không thay hệ điều hành quản lý CPU và không thay cơ sở dữ liệu lưu trữ dữ liệu.

## 3. Vòng đời: runtime hình thành, phục vụ và kết thúc như thế nào?

### Giai đoạn A — Khởi động tiến trình

Khi chạy **java -jar app.jar** hoặc chạy bằng Maven/Gradle, hệ điều hành tạo tiến trình Java, JVM tải class, và phương thức **main()** của ứng dụng gọi **SpringApplication.run(...)**. Spring Boot chuẩn bị **Environment** để tra cứu cấu hình từ các nguồn phù hợp: file application.properties/application.yml, biến môi trường, tham số dòng lệnh và những nguồn được hỗ trợ khác. Các **Spring profiles** có thể quyết định cấu hình/bean nào có hiệu lực.

### Giai đoạn B — Dựng ApplicationContext

Spring Boot chọn loại ApplicationContext thích hợp và áp dụng auto-configuration dựa trên classpath, properties và các điều kiện cấu hình. Spring quét/đăng ký bean, giải quyết dependency, chạy các cơ chế mở rộng và khởi tạo bean cần thiết.

Ví dụ, nếu có Spring Web MVC và cấu hình web phù hợp, Boot thường dựng servlet web server nhúng (ví dụ Tomcat) và các thành phần MVC. Với WebFlux, runtime có thể sử dụng một HTTP runtime reactive như Reactor Netty. Với ứng dụng non-web, runtime không cần mở cổng HTTP.

Các hook khởi tạo bean như **@PostConstruct** chỉ chứng minh một bean đã được khởi tạo; chúng **không đồng nghĩa toàn bộ ứng dụng đã sẵn sàng nhận lưu lượng**.

### Giai đoạn C — Hoàn thành startup và nhận công việc

Khi context đã được refresh, Spring Boot chạy các bean **ApplicationRunner** và **CommandLineRunner**. Sau khi các bước khởi động cần thiết kết thúc, sự kiện **ApplicationReadyEvent** báo hiệu ứng dụng đã hoàn thành quá trình startup ở phía Spring Boot. Với hệ thống có orchestrator, trạng thái sẵn sàng nhận traffic còn có thể phụ thuộc readiness probe và các kiểm tra phụ thuộc.

Ở trạng thái hoạt động, runtime thực hiện một hoặc nhiều loại việc: nhận HTTP request, tiêu thụ message, chạy job hoặc xử lý lịch định kỳ. Spring gọi các bean thích hợp; các thư viện hạ tầng cung cấp connection pool, transactions, thread pools hoặc các cơ chế khác nếu được đưa vào cấu hình.

### Giai đoạn D — Dừng và giải phóng

Khi ứng dụng nhận tín hiệu dừng thông thường, Spring đóng ApplicationContext và thực hiện các lifecycle callback như **@PreDestroy**, **DisposableBean** hoặc phương thức destroy của bean. Tài nguyên được quản lý đúng cách (pool, executor, kết nối...) cần được đóng. Khi bật **graceful shutdown** cho HTTP server, server có thể ngừng nhận việc mới và cho các request đang xử lý thời gian kết thúc theo timeout cấu hình. Lệnh cưỡng bức như **SIGKILL** không bảo đảm callback cleanup sẽ chạy.

Vòng đời tổng quát:

~~~text
START → JVM → SpringApplication → Environment/Auto-configuration
      → ApplicationContext/Beans → Runners → READY
      → Xử lý công việc → Shutdown → Đóng context/tài nguyên → STOP
~~~

## 4. Runtime quản lý những gì trong thực tế?

### 4.1. Cấu hình và profile

**Environment** của Spring cung cấp cách truy xuất properties và profile hiện hành. Cấu hình ảnh hưởng đến port, timeout, địa chỉ dịch vụ ngoài, mức log và cách khởi tạo bean. **@ConfigurationProperties** giúp ánh xạ nhóm cấu hình vào đối tượng có kiểu.

Phân biệt **Spring Environment** (cơ chế truy vấn cấu hình trong ứng dụng) với **môi trường triển khai dev/test/staging/prod**. Một ứng dụng có thể cùng một artifact nhưng sử dụng cấu hình khác ở mỗi nơi. Cấu hình đã được bind khi startup thường không tự cập nhật chỉ vì sửa file; việc refresh động cần cơ chế hỗ trợ riêng.

### 4.2. Bean và dependency injection

**ApplicationContext** tạo, liên kết, cung cấp và quản lý vòng đời bean. Với singleton mặc định, một instance được dùng chung trong context; scope khác có quy tắc riêng. Context xử lý lifecycle của các bean do Spring quản lý, không mặc nhiên quản lý mọi đối tượng được tạo bằng toán tử **new** ở bất kỳ đâu.

Ví dụ: Controller gọi Service; Service được inject Repository; Repository sử dụng DataSource. Runtime kết nối các thành phần theo cấu hình, còn thuật toán nghiệp vụ nằm trong chính các lớp đó.

### 4.3. Nhận request và thực thi công việc

Với ứng dụng web, HTTP server nhúng lắng nghe port, tiếp nhận kết nối và đưa request vào chuỗi xử lý của framework (filter, dispatcher/handler, controller...). Với job, consumer hoặc scheduled task, công việc được kích hoạt qua cơ chế tương ứng thay vì HTTP. **Không có quy tắc rằng mọi Spring Boot runtime đều phải mở port 8080**; port có thể đổi hoặc không tồn tại.

### 4.4. Luồng, executor và scheduler

JVM cung cấp luồng thực thi. Web server, thư viện xử lý bất đồng bộ, **TaskExecutor** và **TaskScheduler** có thể sử dụng thread pools. Spring tích hợp và quản lý vòng đời những bean hạ tầng này khi chúng được khai báo/tự cấu hình. Các tính năng như **@Async** hay **@Scheduled** cần điều kiện kích hoạt/cấu hình phù hợp; thêm annotation không có nghĩa Spring sẽ tự quản lý mọi loại tác vụ nền một cách an toàn.

Cần đặt giới hạn cho pool, hàng đợi, timeout và khả năng dừng; tạo quá nhiều luồng hoặc tác vụ không giới hạn có thể làm ứng dụng cạn tài nguyên.

### 4.5. Kết nối và giao dịch

Khi dùng JDBC/JPA, runtime có thể có **DataSource** và connection pool (thường là HikariCP trong cấu hình JDBC phù hợp), cùng transaction manager. Pool cấp/phục hồi kết nối cho các tác vụ, còn transaction manager phối hợp ranh giới giao dịch nếu cơ chế transaction được bật. **Database server vẫn là hệ thống bên ngoài**; Spring không quản lý bộ nhớ hay độ bền lưu trữ của chính database server.

### 4.6. Bảo mật và quan sát hệ thống

Khi tích hợp Spring Security, filter chain và các thành phần bảo mật tham gia xử lý request. Logging giúp quan sát lỗi/sự kiện; với **Spring Boot Actuator** và các thư viện tương ứng, ứng dụng có thể cung cấp health, metrics và thông tin phục vụ vận hành. Các endpoint và dữ liệu được lộ ra phụ thuộc dependency, cấu hình và chính sách bảo vệ.

Runtime không tự bảo đảm ứng dụng khỏe: một tiến trình Java vẫn sống dù phụ thuộc quan trọng đang lỗi hoặc request liên tục timeout. Cần phân biệt **liveness** (tiến trình cần được khởi động lại hay không) và **readiness** (có nên nhận lưu lượng hay chưa) khi triển khai cùng nền tảng điều phối.

## 5. Ví dụ Java 17+: quan sát runtime hoạt động

Tạo một dự án Spring Boot bằng Spring Initializr, chọn **Java 17 trở lên**, **Maven** và dependency **Spring Web**. Thay nội dung file **src/main/java/com/example/demo/RuntimeDemoApplication.java** bằng:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class RuntimeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeDemoApplication.class, args);
    }

    @GetMapping("/runtime")
    public Map<String, String> runtime() {
        return Map.of("status", "RUNNING");
    }

    @Bean
    public ApplicationRunner afterStartup() {
        return args -> System.out.println("ApplicationRunner executed");
    }

    @Bean(destroyMethod = "close")
    public RuntimeResource runtimeResource() {
        return new RuntimeResource();
    }

    public static final class RuntimeResource implements AutoCloseable {
        public RuntimeResource() {
            System.out.println("RuntimeResource created");
        }

        @Override
        public void close() {
            System.out.println("RuntimeResource closed");
        }
    }
}
~~~

Trong ví dụ này:

1. **SpringApplication.run** dựng runtime và context.
2. **@RestController** tạo endpoint GET /runtime, được phục vụ bởi web server do Spring Boot cấu hình.
3. **ApplicationRunner** chạy sau khi context được khởi tạo, trước mốc **ApplicationReadyEvent**.
4. **RuntimeResource** là singleton bean được Spring tạo và đóng thông qua **destroyMethod = "close"** lúc context kết thúc bình thường.

Chạy ứng dụng từ thư mục dự án Maven đã sinh:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows, dùng lệnh tương đương:
# mvnw.cmd spring-boot:run

# Mở terminal thứ hai:
curl http://localhost:8080/runtime
~~~

Phản hồi HTTP body dự kiến:

~~~json
{"status":"RUNNING"}
~~~

Trong log sẽ có các dòng do ví dụ tự in (xen giữa log của Spring Boot):

~~~text
RuntimeResource created
ApplicationRunner executed
~~~

Dùng **Ctrl+C** để dừng ứng dụng theo cách thông thường, có thể quan sát:

~~~text
RuntimeResource closed
~~~

Lưu ý: ví dụ cần classpath/dependency của dự án Spring Boot; không thể biên dịch chỉ bằng **javac RuntimeDemoApplication.java** mà không khai báo thư viện Spring. Nếu port 8080 đang được dùng hoặc cấu hình server đổi port, hãy điều chỉnh địa chỉ curl tương ứng.

### Thử cấu hình runtime

Đặt nội dung sau trong **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8081
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Sau khi khởi động lại, gọi **http://localhost:8081/runtime**. Cấu hình này đổi port HTTP và yêu cầu graceful shutdown trong thời gian cho phép. Timeout 20 giây là giới hạn của pha dừng, **không bảo đảm mọi tác vụ hoặc mọi tài nguyên đều sẽ hoàn tất** trước khi tiến trình bị dừng.

Nếu thêm dependency **Spring Boot Actuator**, có thể dùng các health endpoint được cấu hình/phân quyền phù hợp để theo dõi runtime. Đây là thành phần tùy chọn, không tự có trong ví dụ chỉ khai báo Spring Web.

## 6. Spring Boot quản lý tới đâu, và phần nào nằm ngoài phạm vi?

| Tình huống | Thành phần chịu trách nhiệm chủ yếu |
| --- | --- |
| Khởi tạo bean, inject dependency, lifecycle callback | Spring ApplicationContext |
| Chọn auto-configuration và dựng hạ tầng dựa trên dependency/properties | Spring Boot |
| Thu gom rác, thực thi bytecode, quản lý heap JVM | JVM |
| Giới hạn CPU/bộ nhớ container, điều phối tiến trình, restart pod | OS, container runtime, orchestrator |
| Tiếp nhận HTTP request | Embedded web server và framework web tương ứng |
| Mở/thu hồi kết nối trong pool ứng dụng | Connection-pool library / DataSource |
| Lưu trữ dữ liệu bền vững, replication, backup database | Hệ quản trị cơ sở dữ liệu và nền tảng quản trị |
| Quy tắc nghiệp vụ, xử lý lỗi nghiệp vụ, idempotency | Mã ứng dụng của nhóm phát triển |

Phân định này rất quan trọng khi xử lý sự cố. Ví dụ, Spring có thể đóng pool khi dừng context, nhưng **không thể thay** cấu hình giới hạn bộ nhớ cho container; ứng dụng có thể tự chạy lại sau lỗi nếu orchestrator cấu hình restart, chứ Spring Boot không tự khởi động lại cả tiến trình trong mọi trường hợp.

## 7. Những nhầm lẫn thường gặp

- **“Runtime chính là JVM.”** JVM chỉ là lớp thực thi Java. Spring Boot runtime còn có Spring context, cấu hình ứng dụng và các thành phần hạ tầng đã khởi tạo.
- **“Có Spring Boot là luôn có web server.”** Ứng dụng command-line, batch hoặc worker nền có thể chạy không có HTTP server.
- **“@PostConstruct nghĩa là đã sẵn sàng nhận request.”** Hook này thuộc vòng đời một bean; hãy dùng cơ chế readiness thích hợp để đánh giá khả năng nhận traffic của toàn ứng dụng.
- **“Cứ sửa application.yml là runtime tự nạp cấu hình mới.”** Nhiều property/bean được xác định khi startup; thay đổi cần restart hoặc cơ chế refresh được thiết kế riêng.
- **“Spring quản lý hết thread, database và bộ nhớ.”** JVM, library, database và OS có trách nhiệm khác nhau. Nhiều tài nguyên phải được nhóm phát triển cấu hình giới hạn và đóng đúng cách.
- **“Dừng tiến trình kiểu nào cũng giải phóng sạch.”** Dừng cưỡng bức có thể bỏ qua lifecycle callback; cần thiết kế hệ thống chịu được việc bị ngắt, đặc biệt với tác vụ nền và giao dịch.

## 8. Checklist khi vận hành một Spring Boot runtime

1. **Startup:** ứng dụng có tạo được ApplicationContext, nạp đúng profile/config, và khởi tạo đủ dependency bắt buộc không?
2. **Serving:** web port/consumer/scheduler có hoạt động như kỳ vọng không? Công việc được xử lý bằng cơ chế đồng bộ hay bất đồng bộ nào?
3. **Resources:** heap, thread pools, connection pools, timeout, file handle và hàng đợi có giới hạn hợp lý không?
4. **Observability:** log có đủ thông tin; health/readiness/metrics có được bật và bảo vệ phù hợp không?
5. **Shutdown:** ứng dụng có ngừng nhận việc mới, hoàn tất/hoàn tác tác vụ còn dở và giải phóng bean/tài nguyên trong thời gian cho phép không?

**Kết luận:** Khi nói “môi trường thực thi ứng dụng trong Spring Boot”, hãy hình dung một **hệ thống đang vận hành** gồm JVM + ApplicationContext + cấu hình + các thành phần hạ tầng và logic nghiệp vụ. Spring Boot đơn giản hóa quá trình tạo và vận hành hệ thống đó; hiểu ranh giới quản lý của từng lớp giúp phát triển, giám sát và xử lý lỗi chính xác.