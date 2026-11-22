# Ứng dụng dòng lệnh, ứng dụng web và tác vụ nền đều có thể dùng Spring Boot

Khi nghe đến **Spring Boot**, nhiều người hình dung ngay một REST API chạy trên cổng 8080. Đó là một cách sử dụng phổ biến, nhưng không phải định nghĩa của Spring Boot. Cùng một nền tảng có thể tạo ra:

- **Ứng dụng dòng lệnh (CLI):** nhận tham số, xử lý công việc rồi kết thúc.
- **Ứng dụng web:** khởi động máy chủ HTTP, tiếp nhận request và trả response.
- **Ứng dụng chạy nền (background worker):** chờ lịch, sự kiện hoặc thông điệp để thực thi công việc mà không cần người dùng gọi HTTP trực tiếp.

Điểm chung không nằm ở giao diện hay cách công việc được kích hoạt. Điểm chung là cả ba đều có thể sử dụng **Spring ApplicationContext**, quản lý bean, dependency injection, cấu hình, logging, các thư viện tích hợp và cơ chế khởi động của Spring Boot.

## 1. Phân biệt Spring Boot với máy chủ web

**Spring Framework** cung cấp những thành phần nền tảng như IoC container, dependency injection, quản lý vòng đời bean, transaction và khả năng tích hợp với nhiều công nghệ. **Spring Boot** giúp khởi tạo, cấu hình và đóng gói ứng dụng dùng Spring thuận tiện hơn thông qua starter, auto-configuration, cấu hình ngoài mã nguồn và cơ chế khởi chạy nhất quán.

Spring Boot **không bắt buộc** ứng dụng phải có endpoint, controller hay máy chủ HTTP. Khi chạy một ứng dụng Boot, có thể hình dung luồng chung:

~~~text
Hàm main()
    │
    ▼
SpringApplication.run(...)
    │
    ├── Đọc cấu hình và môi trường
    ├── Tạo ApplicationContext
    ├── Khởi tạo, kết nối các bean
    ├── Áp dụng auto-configuration phù hợp
    │
    ▼
Ứng dụng sẵn sàng
    │
    ├── CLI: chạy CommandLineRunner / ApplicationRunner → kết thúc
    ├── Web: mở HTTP server → nhận request liên tục
    └── Worker: đăng ký lịch / listener → xử lý công việc nền
~~~

Sự khác biệt chủ yếu đến từ **thư viện đã chọn, cấu hình kiểu ứng dụng và cơ chế kích hoạt nghiệp vụ**. Chẳng hạn, thêm Spring MVC cùng embedded server là lựa chọn thích hợp cho ứng dụng web; một chương trình nhập dữ liệu từ file có thể chỉ cần Spring Boot cơ bản và thư viện đọc file.

### Các khái niệm cần tách bạch

| Khái niệm | Ý nghĩa |
|---|---|
| Spring Boot | Cơ chế khởi động, cấu hình và vận hành ứng dụng dựa trên Spring |
| ApplicationContext | Container quản lý bean và dependency của ứng dụng |
| Bean / Service | Đối tượng do Spring quản lý, có thể được dùng bởi CLI, web hoặc worker |
| HTTP server | Thành phần phục vụ request mạng, cần cho ứng dụng web nhưng không phải điều kiện để dùng Spring Boot |
| Runner | Điểm thực thi mã sau khi Spring khởi tạo xong context |
| Scheduler / Message listener | Cơ chế kích hoạt công việc định kỳ hoặc khi có thông điệp |

Trong các ví dụ dưới đây, hãy xem **mỗi kiểu là một ứng dụng độc lập**, có package và class khởi động riêng. Khi cần, một hệ thống thực tế có thể dùng chung lớp nghiệp vụ hoặc kết hợp nhiều vai trò trong cùng tiến trình.

## 2. Bức tranh so sánh ba kiểu ứng dụng

| Tiêu chí | Ứng dụng dòng lệnh | Ứng dụng web | Ứng dụng chạy nền |
|---|---|---|---|
| Ai kích hoạt? | Người dùng, terminal, script, CI hoặc bộ lập lịch bên ngoài | Client gửi HTTP request | Lịch định kỳ, queue, event hoặc một nguồn công việc |
| Điểm vào nghiệp vụ | ApplicationRunner / CommandLineRunner, lệnh cụ thể | Controller / HTTP handler | Phương thức có @Scheduled, listener hoặc job handler |
| Cần HTTP server? | Không | Có nếu phục vụ HTTP | Thường không; có thể bật thêm để quản trị hoặc cung cấp API |
| Vòng đời thường gặp | Khởi chạy → làm việc → thoát | Khởi chạy → phục vụ request → dừng khi có tín hiệu | Khởi chạy → chờ và xử lý việc → dừng khi có tín hiệu |
| Ví dụ | Import CSV, chuyển đổi dữ liệu, tạo báo cáo một lần | REST API đặt hàng, trang quản trị, backend web | Gửi email từ queue, dọn dữ liệu theo lịch, xử lý sự kiện |
| Mối quan tâm chính | Tham số, kết quả, mã thoát, xử lý lỗi | API contract, bảo mật, timeout, khả năng chịu tải | Retry, tính lặp an toàn, trùng lịch, giám sát, shutdown |

**“Không có giao diện web” không đồng nghĩa với “không có Spring”.** Một chương trình chạy một lần vẫn hưởng lợi từ dependency injection và cấu hình; một worker chạy 24/7 cũng có thể dùng repository, transaction và service giống backend web.

## 3. Kiểu thứ nhất: ứng dụng dòng lệnh (CLI)

Giả sử cần tạo lệnh chào người dùng để thấy rõ cách Spring Boot xử lý tham số. Ứng dụng cần nhận giá trị từ terminal, sử dụng bean đã được Spring khởi tạo, in kết quả rồi thoát.

Với ứng dụng mới, dependency nền tảng như **spring-boot-starter** là đủ cho ví dụ này. Không cần thêm **spring-boot-starter-web** chỉ để có được dependency injection.

### Ví dụ sử dụng ApplicationRunner

~~~java
package com.example.cli;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Service;

@SpringBootApplication
public class CliApplication {

    public static void main(String[] args) {
        // Không tạo web server, kể cả khi classpath vô tình có thư viện web.
        try (var context = new SpringApplicationBuilder(CliApplication.class)
                .web(WebApplicationType.NONE)
                .run(args)) {
            // Spring đã chạy các ApplicationRunner trước khi run(args) trả về.
            // Đóng context sau khi công việc đồng bộ kết thúc.
        }
    }

    @Bean
    ApplicationRunner greetingCommand(GreetingService greetingService) {
        return arguments -> {
            List<String> names = arguments.getOptionValues("name");
            String name = (names == null || names.isEmpty())
                    ? "bạn"
                    : names.get(0);

            System.out.println(greetingService.greet(name));
        };
    }
}

@Service
class GreetingService {
    String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Chạy JAR đã được đóng gói:

~~~bash
java -jar cli-demo.jar --name=Lan
~~~

Kết quả nghiệp vụ có dạng:

~~~text
Xin chào, Lan!
~~~

Spring Boot cũng có thể in log khởi động; dòng trên là kết quả do lệnh tạo ra.

Ở ví dụ này:

1. **main()** tạo một Spring application loại **NONE**, nghĩa là không tạo web context.
2. Spring tạo bean **GreetingService**, rồi đưa bean này vào hàm tạo bean **ApplicationRunner**.
3. Khi context đã được khởi tạo, Boot gọi **ApplicationRunner.run(ApplicationArguments)**.
4. Runner đọc tùy chọn **--name=Lan** và gọi nghiệp vụ qua service.
5. Sau khi runner đồng bộ hoàn tất, khối **try-with-resources** đóng context; tiến trình có thể kết thúc.

**ApplicationRunner** cung cấp đối tượng **ApplicationArguments** giúp đọc option và đối số không đặt tên. **CommandLineRunner** có cùng thời điểm thực thi, nhưng nhận mảng **String... args** thô. Chọn loại phù hợp với cách muốn xử lý tham số; cả hai đều là bean do Spring quản lý.

### Khi CLI trở thành công cụ thực tế

Một ứng dụng thực tế có thể có các bước:

~~~text
Lệnh: java -jar import-tool.jar --file=/data/orders.csv
                 │
                 ▼
        Kiểm tra tham số file
                 │
                 ▼
    ImportService → Validator → Repository
                 │
                 ▼
     In kết quả / log / mã thoát
~~~

Khi đó các nguyên tắc hữu ích là:

- **Tách nghiệp vụ khỏi Runner:** Runner chỉ nhận input và điều phối; service đảm nhiệm import, validate và truy cập dữ liệu.
- **Phân biệt lỗi và thành công:** script hoặc hệ thống điều phối thường dựa vào **exit code**. Có thể dùng **ExitCodeGenerator** và **SpringApplication.exit(...)** để biểu diễn mã thoát phù hợp; không nên chỉ in “lỗi” rồi trả mã thành công.
- **Quản lý tài nguyên:** đọc file lớn theo luồng nếu phù hợp, đóng kết nối và context, xử lý transaction ở ranh giới nghiệp vụ.
- **Không khởi tạo tài nguyên web dư thừa:** tác vụ một lần không cần chạy HTTP server trong suốt quá trình nhập liệu.

Nếu công việc cần kết thúc sau một lần chạy, một **CLI được gọi bởi cron hoặc Kubernetes CronJob** có thể phù hợp hơn một tiến trình tự thức dậy liên tục. Đây là quyết định về cách vận hành, không phải giới hạn của Spring Boot.

## 4. Kiểu thứ hai: ứng dụng web

Ứng dụng web có một vòng đời khác: sau khi Spring khởi tạo, **máy chủ HTTP vẫn lắng nghe request**. Mỗi request đến endpoint sẽ đi qua tầng web và gọi service phù hợp.

Với Spring MVC, thường thêm dependency **spring-boot-starter-web**. Trên Spring Boot 3.x, starter này cung cấp các thành phần cần thiết cho REST controller và máy chủ Servlet nhúng mặc định. Nếu chọn WebFlux thì dùng stack reactive tương ứng; không cần cả hai stack cho một ví dụ cơ bản.

### Ví dụ REST API nhỏ

~~~java
package com.example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }
}

@RestController
class GreetingController {

    @GetMapping("/hello")
    GreetingResponse hello(@RequestParam(defaultValue = "bạn") String name) {
        return new GreetingResponse("Xin chào, " + name + "!");
    }
}

record GreetingResponse(String message) {}
~~~

Khi ứng dụng chạy với cổng mặc định, có thể gửi request:

~~~bash
curl "http://localhost:8080/hello?name=Lan"
~~~

Response JSON minh họa:

~~~json
{"message":"Xin chào, Lan!"}
~~~

Trong ứng dụng web:

1. **SpringApplication.run(...)** tạo context, tự cấu hình các thành phần phù hợp với dependency trên classpath và khởi động embedded HTTP server.
2. **@RestController** khai báo bean tiếp nhận HTTP request.
3. **@GetMapping("/hello")** ánh xạ request GET đến phương thức **hello(...)**.
4. **@RequestParam** nhận tham số **name** từ query string; response object được chuyển thành JSON bởi cơ chế HTTP message conversion thích hợp.
5. Ứng dụng tiếp tục phục vụ request cho tới khi bị dừng hoặc gặp điều kiện kết thúc.

Luồng xử lý thường gặp:

~~~text
Browser / Mobile / curl
          │ HTTP GET /hello
          ▼
Embedded HTTP server
          │
          ▼
Spring MVC → Controller → Service → Repository
          │
          ▼
HTTP status + JSON response
~~~

Khác với CLI, **một lần khởi động web application thường phục vụ rất nhiều request**. Vì vậy cần quan tâm đến HTTP status code, validate input, xác thực/ủy quyền, cấu hình cổng, timeout, xử lý ngoại lệ và số lượng request đồng thời.

Ví dụ, cổng có thể được cấu hình trong **application.yml**:

~~~yaml
server:
  port: 8081
~~~

Lúc đó endpoint minh họa được gọi tại **http://localhost:8081/hello**. Việc đổi cổng chỉ có ý nghĩa khi ứng dụng thực sự chạy một HTTP server.

## 5. Kiểu thứ ba: ứng dụng chạy nền (background worker)

Worker phục vụ các công việc **không bắt nguồn trực tiếp từ một HTTP request tại thời điểm xử lý**: dọn dữ liệu hằng đêm, tổng hợp thống kê, tạo báo cáo theo lịch, nhận message từ queue hoặc đồng bộ dữ liệu với hệ thống khác.

Một worker có thể chạy lâu dài mà **không mở HTTP port**. Spring Boot vẫn quản lý service, cấu hình, dependency, logging và vòng đời của nó.

### Ví dụ công việc định kỳ với @Scheduled

Đây là một ứng dụng độc lập sử dụng **spring-boot-starter** và tính năng scheduling của Spring:

~~~java
package com.example.worker;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableScheduling
public class WorkerApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(WorkerApplication.class)
                .web(WebApplicationType.NONE)
                .run(args);
    }
}

@Component
class CleanupJob {

    private static final Logger log = LoggerFactory.getLogger(CleanupJob.class);

    @Scheduled(fixedDelay = 60_000)
    public void cleanup() {
        log.info("Bắt đầu lượt kiểm tra dữ liệu cần dọn dẹp");

        // Ở ứng dụng thực tế: gọi CleanupService để xử lý dữ liệu.

        log.info("Kết thúc lượt kiểm tra");
    }
}
~~~

Điểm đáng chú ý:

- **@EnableScheduling** bật cơ chế tìm và đăng ký các phương thức **@Scheduled**.
- **@Scheduled(fixedDelay = 60_000)** lên lịch lần tiếp theo sau khi lần trước kết thúc được 60.000 mili giây.
- **WebApplicationType.NONE** tắt phần web; worker không có endpoint **/cleanup**.
- **main()** không đóng context ngay như CLI, vì ứng dụng phải tiếp tục sống để bộ lập lịch kích hoạt các lần chạy tiếp theo.

Khi muốn chạy đúng 2 giờ sáng hằng ngày theo giờ Việt Nam, có thể dùng:

~~~java
@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void cleanupEveryNight() {
    // Gọi nghiệp vụ dọn dẹp.
}
~~~

Biểu thức cron của Spring ở ví dụ này gồm **sáu trường**, trong đó trường đầu tiên là **giây**. Hãy chọn một phương thức lên lịch cho một job cụ thể; nếu đặt cả hai ví dụ trên cùng lúc, chúng tạo ra hai lịch kích hoạt độc lập.

### Ba nguồn kích hoạt công việc nền khác nhau

Không phải worker nào cũng dùng **@Scheduled**:

| Nguồn kích hoạt | Cách tổ chức | Ví dụ |
|---|---|---|
| Lịch nội bộ của ứng dụng | **@Scheduled** với fixed delay, fixed rate hoặc cron | Kiểm tra và dọn dữ liệu mỗi đêm |
| Lịch bên ngoài | Hệ điều hành, cron, Kubernetes CronJob khởi chạy CLI/Job | Tạo báo cáo lúc 02:00 rồi thoát |
| Thông điệp / sự kiện | Listener của RabbitMQ, Kafka hoặc hệ thống hàng đợi tương tự | Nhận yêu cầu gửi email sau khi đơn hàng được tạo |

Với công việc xử lý theo lô có nhiều bước, cần restart hoặc theo dõi trạng thái từng phần, **Spring Batch** có thể là công cụ phù hợp. Bản thân **@Scheduled** chỉ giải quyết việc **khi nào gọi phương thức**, không tự mang lại đầy đủ retry bền vững, checkpoint, chia partition hay cơ chế tránh chạy trùng trên nhiều máy.

### Các vấn đề worker phải chủ động xử lý

**1. Chạy trùng giữa nhiều instance.** Nếu có ba bản sao ứng dụng cùng chứa một **@Scheduled(cron=...)**, cả ba có thể chạy job tại cùng thời điểm. Khi nghiệp vụ chỉ được phép thực hiện một lần, cần thiết kế cơ chế phối hợp như distributed lock, job scheduler có khả năng điều phối hoặc đưa công việc vào queue với quy tắc xử lý phù hợp.

**2. Xử lý lỗi và retry.** Log lỗi không làm job tự có retry bền vững. Cần xác định lỗi nào có thể thử lại, số lần thử, khoảng lùi, nơi lưu trạng thái và cách xử lý công việc thất bại lâu dài.

**3. Idempotency.** Nếu cùng một thông điệp được giao hai lần, thao tác “gửi tiền” hoặc “tạo hóa đơn” không được mặc nhiên thực hiện hai lần. Có thể dựa trên mã công việc duy nhất, constraint trong database hoặc cơ chế xử lý lặp an toàn được thiết kế ở tầng nghiệp vụ.

**4. Thời gian chạy và shutdown.** Job dài cần xử lý dừng ứng dụng, transaction, timeout và lưu tiến độ. Nếu ứng dụng bị dừng giữa chừng, phải biết khi khởi động lại cần làm gì.

**5. Khả năng quan sát.** Cần log theo job ID, đếm thành công/thất bại, theo dõi thời lượng và cảnh báo khi việc định kỳ không hoàn thành. Một worker không có endpoint HTTP vẫn cần được giám sát.

## 6. Cùng một service, nhiều cách gọi

Tưởng tượng hệ thống có một nghiệp vụ tạo báo cáo tồn kho. Ta có thể đặt logic vào một Spring bean:

~~~java
package com.example.reports;

import org.springframework.stereotype.Service;

@Service
public class InventoryReportService {

    public String generate() {
        // Minh họa: trong thực tế có thể đọc repository và xuất file báo cáo.
        return "Bao cao ton kho da duoc tao";
    }
}
~~~

Bean này không cần biết ai gọi nó. Ba adapter khác nhau có thể sử dụng cùng service:

~~~text
                         InventoryReportService
                         + generate()
                              ▲
             ┌────────────────┼────────────────┐
             │                │                │
     CLI ApplicationRunner    │        Worker @Scheduled
     chạy khi gọi lệnh        │        chạy theo lịch
                              │
                     Web @PostMapping
                     chạy khi có HTTP request
~~~

Một vài cách kết nối tương ứng:

~~~java
// CLI: gọi một lần khi ứng dụng khởi động.
@Bean
ApplicationRunner reportCommand(InventoryReportService reports) {
    return args -> System.out.println(reports.generate());
}
~~~

~~~java
// Web: gọi khi client gửi POST /reports.
@RestController
class ReportController {
    private final InventoryReportService reports;

    ReportController(InventoryReportService reports) {
        this.reports = reports;
    }

    @PostMapping("/reports")
    String createReport() {
        return reports.generate();
    }
}
~~~

~~~java
// Worker: gọi mỗi ngày lúc 02:00 theo giờ Việt Nam.
@Component
class NightlyReportJob {
    private final InventoryReportService reports;

    NightlyReportJob(InventoryReportService reports) {
        this.reports = reports;
    }

    @Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
    void createReport() {
        reports.generate();
    }
}
~~~

Các đoạn mã trên minh họa **ba adapter thay thế nhau**; chúng cần được đặt trong ứng dụng có cấu hình, dependency và import tương ứng. Không nên sao chép cả ba vào một project rồi cho rằng chỉ một kiểu sẽ tự chạy: nếu đăng ký cả controller, runner và scheduler thì cả ba cơ chế đều có thể hoạt động.

Ý nghĩa kiến trúc là **service giữ nghiệp vụ, adapter quyết định khi nào và bằng cách nào gọi nghiệp vụ**. Điều này giúp kiểm thử logic độc lập với HTTP hoặc terminal và giảm việc lặp lại mã khi hệ thống mở rộng.

## 7. Một ứng dụng có thể kết hợp nhiều vai trò không?

**Có.** Một ứng dụng web có thể vừa phục vụ API, vừa có **@Scheduled** để dọn cache. Một worker có thể mở thêm HTTP endpoint để nhận lệnh quản trị. Một CLI cũng có thể dùng repository và transaction như server lâu dài.

Tuy nhiên, việc kết hợp phải là **lựa chọn triển khai có chủ đích**:

- Khi tác vụ ngắn được chạy một lần, CLI thường đơn giản về vận hành.
- Khi cần phản hồi request từ client, web app là lựa chọn tự nhiên.
- Khi cần chờ queue hoặc chạy định kỳ, worker phù hợp với nhịp công việc nền.
- Khi công việc nền tốn nhiều tài nguyên, chạy nó trong cùng tiến trình web có thể ảnh hưởng độ trễ API; tách worker giúp cấp phát tài nguyên và mở rộng độc lập.
- Khi deploy nhiều bản sao web app, lịch **@Scheduled** bên trong mỗi bản sao có thể bị kích hoạt nhiều lần; phải xác định cơ chế tránh trùng trước khi đưa vào production.

Đặc biệt, **@Async** không phải là giải pháp thay thế mặc định cho một job bền vững. Nó hỗ trợ chạy công việc bất đồng bộ trong ứng dụng nhưng không tự biến tác vụ thành hàng đợi có lưu trữ, cơ chế thử lại và khôi phục sau khi tiến trình chết.

## 8. Cách chọn kiểu ứng dụng từ yêu cầu thực tế

Hãy bắt đầu bằng câu hỏi: **Điều gì làm công việc bắt đầu và lúc nào nó được xem là hoàn thành?**

~~~text
Công việc bắt đầu như thế nào?
        │
        ├── Một lệnh hoặc lịch bên ngoài khởi chạy
        │      └── CLI / batch chạy một lần rồi thoát
        │
        ├── Client cần request/response qua HTTP
        │      └── Web application + controller/handler
        │
        └── Ứng dụng chủ động chờ lịch hoặc thông điệp
               └── Background worker + scheduler/listener
~~~

Sau đó mới chọn dependency, cấu hình, cách đóng gói và cách deploy. Các ví dụ:

| Yêu cầu | Lựa chọn ban đầu hợp lý | Lý do |
|---|---|---|
| Chạy lệnh di chuyển dữ liệu cũ một lần | CLI | Có điểm bắt đầu/kết thúc rõ, dễ ghi mã thoát |
| Cung cấp API tra cứu sản phẩm | Web | Client cần gửi request và nhận response |
| Mỗi phút đọc queue và xử lý yêu cầu | Worker/listener | Công việc đến từ nguồn bất đồng bộ |
| Tạo báo cáo ban đêm rồi thoát | CLI được CronJob kích hoạt hoặc batch job | Lịch có thể do hạ tầng điều phối |
| Gửi email xác nhận sau khi đặt hàng | Worker nhận message | Tách xử lý lâu khỏi đường phản hồi HTTP |
| Quản trị viên bấm nút để bắt đầu job lớn | Web gửi yêu cầu vào queue + worker xử lý | HTTP phản hồi nhanh, công việc chạy độc lập |

### Tình huống kết hợp: “Tạo báo cáo” không nhất thiết phải nằm trong request

Giả sử API nhận yêu cầu tạo file báo cáo rất lớn. Nếu controller thực hiện toàn bộ trong request, client có thể bị timeout và server phải giữ kết nối lâu. Cách tổ chức thường phù hợp hơn là:

~~~text
Client ── POST /reports ──► Web API
                               │
                               ├── Kiểm tra yêu cầu
                               ├── Lưu job với trạng thái PENDING
                               └── Đẩy message vào queue
                                            │
                                            ▼
                                     Background worker
                                            │
                                            ├── Đọc dữ liệu
                                            ├── Sinh báo cáo
                                            └── Cập nhật trạng thái DONE/FAILED

Client ── GET /reports/{id} ──► Web API trả trạng thái/kết quả
~~~

Trong thiết kế này, **web và worker đều có thể viết bằng Spring Boot**, nhưng vai trò và nhịp vận hành khác nhau. Cơ chế queue, lưu job và retry phải được triển khai hoặc chọn bằng công nghệ thích hợp; Spring Boot không tự tạo một hàng đợi bền vững chỉ từ annotation.

## 9. Những hiểu nhầm thường gặp

**“Dùng Spring Boot là phải có Tomcat và port 8080.”** Không đúng. Tomcat nhúng là một lựa chọn trong ứng dụng Servlet web thông thường. CLI và worker có thể chạy với **WebApplicationType.NONE** mà không mở HTTP port.

**“Không có controller thì không dùng được dependency injection.”** Không đúng. Dependency injection thuộc ApplicationContext, hoạt động với service, runner, scheduler, listener và nhiều thành phần khác.

**“ApplicationRunner là một bộ lập lịch.”** Không đúng. Runner được gọi khi khởi động ứng dụng; bản thân nó không tự chạy lại theo chu kỳ.

**“Đã có @Scheduled thì job chỉ chạy một lần trên toàn hệ thống.”** Không đúng. Mỗi instance có scheduler riêng nếu cùng đăng ký job. Cần phối hợp giữa instance khi yêu cầu tính duy nhất.

**“Đưa mọi công việc nặng vào controller vì tất cả đều là Spring Boot.”** Không nên suy luận như vậy. Việc dùng chung framework không làm mất đi khác biệt về timeout HTTP, áp lực tải, cách retry và vòng đời công việc.

**“Worker nhất thiết phải là một microservice riêng.”** Không bắt buộc. Đây là quyết định về triển khai và quy mô, không phải ràng buộc của Spring Boot. Có thể bắt đầu cùng tiến trình rồi tách ra khi nhu cầu vận hành đòi hỏi.

## 10. Tự quan sát sự khác nhau khi chạy

Có thể tự tạo ba project nhỏ theo các ví dụ trên, chạy từng project rồi quan sát hành vi:

| Thử nghiệm | Điều nên quan sát |
|---|---|
| Chạy CLI với **--name=Lan** | Runner được gọi một lần, in lời chào rồi tiến trình kết thúc |
| Chạy web và gọi **GET /hello?name=Lan** nhiều lần | Mỗi request nhận JSON; ứng dụng tiếp tục chạy giữa các request |
| Chạy worker với lịch **fixedDelay** | Log xuất hiện nhiều lần theo lịch, không cần gọi HTTP |
| Chạy worker mà thử gọi **localhost:8080** | Không có web server do worker cố ý dùng **WebApplicationType.NONE** |
| Thêm hai instance worker cùng lịch | Có thể nhìn thấy mỗi instance tự kích hoạt job; đây là lý do phải thiết kế phối hợp khi cần |

Khi quan sát, hãy chú ý ba câu hỏi: **Ai khởi động công việc? Spring quản lý những bean nào? Khi nào tiến trình kết thúc?** Ba câu hỏi này giúp phân loại ứng dụng chính xác hơn việc nhìn thấy hay không nhìn thấy controller.

## Kết luận

Spring Boot là nền tảng xây dựng **nhiều kiểu ứng dụng Java**, không chỉ REST API. CLI, web application và background worker có thể cùng dùng dependency injection, configuration, service, repository và những tích hợp quen thuộc của Spring. Phần thay đổi là **điểm kích hoạt nghiệp vụ, nhu cầu HTTP server và vòng đời vận hành**.

Khi thiết kế hệ thống, hãy chọn kiểu ứng dụng theo cách công việc xuất hiện và được xử lý: **chạy một lần bằng lệnh, phục vụ HTTP liên tục, hoặc xử lý nền theo lịch/sự kiện**. Hiểu sự phân biệt đó giúp chọn đúng starter, tổ chức mã dễ tái sử dụng và tránh những lỗi vận hành như tác vụ chạy trùng hoặc request bị giữ quá lâu.
