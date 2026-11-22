# Bản đồ vòng đời Spring Boot: khởi động, sẵn sàng, hoạt động và dừng

## 1. Hiểu bản đồ trước khi học từng sự kiện

Một ứng dụng Spring Boot không chuyển ngay từ “chưa chạy” sang “phục vụ được yêu cầu” tại thời điểm JVM bắt đầu. Nó phải dựng môi trường cấu hình, tạo và làm mới `ApplicationContext`, khởi tạo bean và hạ tầng web (nếu có), thực hiện công việc khởi động, sau đó mới công bố trạng thái sẵn sàng. Khi dừng, ứng dụng cũng cần ngừng nhận công việc mới rồi giải phóng những tài nguyên đã sử dụng.

Hãy hình dung một quán ăn: **mở cửa tòa nhà** (tiến trình đang chạy) không đồng nghĩa với **bếp đã chuẩn bị xong** (ứng dụng sẵn sàng nhận khách). Khi đóng cửa, quán dừng nhận khách mới, hoàn tất phần việc đang phục vụ và mới tắt thiết bị. Mô hình đó giúp tránh nhầm lẫn giữa “JVM còn sống”, “Spring context đã tạo” và “ứng dụng đã nhận được lưu lượng”.

Bài này dùng ngữ nghĩa của **Spring Boot 3.3.x và Java 17+**. Với ứng dụng không có máy chủ HTTP (batch, CLI, consumer), “nhận lưu lượng” có thể hiểu tương ứng là “sẵn sàng nhận công việc”; các mốc dựng context và chạy runner vẫn có ý nghĩa.

```text
Bắt đầu tiến trình JVM
        |
        v
SpringApplication.run(...)
        |
        v
Nạp Environment -> dựng ApplicationContext -> refresh context
        |
        v
ApplicationStartedEvent -> LivenessState.CORRECT
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent -> ReadinessState.ACCEPTING_TRAFFIC
        |
        v
HOẠT ĐỘNG: HTTP requests, jobs, scheduled tasks, message processing...
        |
        v
Yêu cầu dừng -> ReadinessState.REFUSING_TRAFFIC
        |
        v
Đóng ApplicationContext -> dừng hạ tầng/beans -> giải phóng tài nguyên
        |
        v
Ứng dụng kết thúc; tiến trình JVM kết thúc theo vòng đời riêng của nó
```

Đây là **bản đồ tư duy**, không phải cam kết mọi thành phần đều được khởi động/dừng tuần tự trên cùng một luồng. Chẳng hạn, web server có thể đã mở cổng trước thời điểm `ApplicationReadyEvent`, và các tác vụ nền có thể tiếp tục chạy sau sự kiện đó.

## 2. Bốn giai đoạn nhìn từ người vận hành

| Giai đoạn | Điều đang diễn ra | Người vận hành cần biết |
| --- | --- | --- |
| **Khởi động (starting)** | JVM chạy `main`; Boot chuẩn bị `Environment`, context, bean, web server. | Có PID hoặc cổng lắng nghe **chưa chứng minh** đã sẵn sàng. |
| **Sẵn sàng (ready)** | Context đã refresh, các runner khởi động hoàn tất; Boot phát `ApplicationReadyEvent`, rồi chuyển readiness sang `ACCEPTING_TRAFFIC`. | Bộ điều phối có thể bắt đầu đưa lưu lượng vào instance. |
| **Hoạt động (running)** | Nhận và xử lý request/job, sử dụng thread, connection pool, scheduler, cache... | Readiness có thể đổi lại `REFUSING_TRAFFIC` trong khi JVM và context vẫn sống. |
| **Dừng (stopping/stopped)** | Ngừng nhận việc mới, cho việc đang xử lý kết thúc theo chính sách, đóng context và giải phóng tài nguyên. | Có shutdown tử tế hay không phụ thuộc tín hiệu dừng, cấu hình và thời gian cho phép. |

**Ranh giới quan trọng:** “started” và “ready” là hai mốc khác nhau; “live” và “ready” là hai câu hỏi khác nhau; “đã đóng Spring context” và “tiến trình JVM đã kết thúc” cũng không phải cùng một sự kiện.

## 3. Đi sâu vào chặng khởi động

### 3.1. Từ `main` đến `Environment`

`SpringApplication.run(...)` là điểm vào phổ biến. `SpringApplication` phát `ApplicationStartingEvent` rất sớm, rồi chuẩn bị `Environment` (thuộc tính cấu hình, profile, biến môi trường, tham số dòng lệnh...) và phát `ApplicationEnvironmentPreparedEvent`.

Ở những thời điểm này, context và các bean thông thường **chưa sẵn sàng**. Vì thế, listener cho sự kiện rất sớm không thể mặc nhiên lấy bean qua dependency injection. Nếu thật sự cần bắt những sự kiện đó, đăng ký listener ngay trên `SpringApplication` hoặc cơ chế đăng ký sớm mà Boot hỗ trợ.

### 3.2. Dựng và làm mới `ApplicationContext`

Boot tạo loại `ApplicationContext` thích hợp, nạp bean definitions, áp dụng auto-configuration, thiết lập dependency injection rồi gọi `refresh()`. Trong quá trình này, các singleton không lazy được khởi tạo; các callback như `@PostConstruct` xảy ra ở **vòng đời của từng bean**, không phải mốc toàn ứng dụng đã sẵn sàng.

Một số dấu mốc hữu ích:

- `ApplicationContextInitializedEvent`: context đã được chuẩn bị và chạy initializer, nhưng bean definitions chưa được nạp.
- `ApplicationPreparedEvent`: bean definitions đã nạp, ngay trước khi refresh bắt đầu.
- `ContextRefreshedEvent`: Spring Framework phát khi context refresh xong.
- `WebServerInitializedEvent`: web server đã khởi tạo (nếu là ứng dụng web).
- `ApplicationStartedEvent`: Boot đã refresh context, nhưng **chưa gọi** `ApplicationRunner` và `CommandLineRunner`.

Không nên coi `WebServerInitializedEvent` hoặc việc log “Tomcat started on port 8080” là phép thử readiness. Một runner còn đang nạp dữ liệu hoặc xác thực trạng thái ban đầu có thể khiến ứng dụng chưa sẵn sàng nhận lưu lượng dù cổng đã mở.

### 3.3. Công việc sau khi context đã được dựng

Boot gọi các bean `ApplicationRunner` và `CommandLineRunner` sau `ApplicationStartedEvent`. Đây là chỗ phù hợp cho công việc bắt buộc phải hoàn tất **trước** khi hệ thống công bố ready, chẳng hạn chuẩn bị dữ liệu khởi động thiết yếu. Nếu có nhiều runner, có thể dùng `@Order` hoặc `Ordered` để xác định thứ tự tương đối.

Khi các runner đã chạy xong, Boot phát `ApplicationReadyEvent`. Sau đó, Boot phát `AvailabilityChangeEvent` với `ReadinessState.ACCEPTING_TRAFFIC`. Sự kiện “ready” đánh dấu **kết thúc chuỗi khởi động do Boot quản lý**; nó không chứng minh mọi kết nối bên ngoài sẽ luôn thành công trong tương lai.

Nếu một runner ném ngoại lệ và không được xử lý, tiến trình khởi động có thể thất bại: không đạt `ApplicationReadyEvent` và Boot phát `ApplicationFailedEvent`.

## 4. Bảng sự kiện theo đúng mốc

| Sự kiện | Ý nghĩa | Đã có thể dùng bean thông thường? |
| --- | --- | --- |
| `ApplicationStartingEvent` | Boot vừa bắt đầu quy trình chạy. | Chưa. |
| `ApplicationEnvironmentPreparedEvent` | `Environment` đã chuẩn bị; context chưa tạo. | Chưa. |
| `ApplicationContextInitializedEvent` | Context đã được tạo/khởi tạo sơ bộ. | Không giả định đã có bean ứng dụng. |
| `ApplicationPreparedEvent` | Bean definitions đã nạp; sắp refresh. | Không giả định bean đã khởi tạo xong. |
| `ContextRefreshedEvent` / `WebServerInitializedEvent` | Context đã refresh / web server đã khởi tạo. | Thông thường có thể dùng bean; chưa chắc ready. |
| `ApplicationStartedEvent` | Refresh xong, chưa chạy runner. | Có; vẫn chưa phải mốc ready. |
| `AvailabilityChangeEvent(LivenessState.CORRECT)` | Boot công bố ứng dụng live. | Có. |
| `ApplicationReadyEvent` | Các runner đã chạy xong. | Có. |
| `AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)` | Boot công bố sẵn sàng nhận lưu lượng. | Có. |
| `ApplicationFailedEvent` | Gặp ngoại lệ khiến khởi động thất bại. | Tùy thời điểm lỗi; context có thể chưa tồn tại. |
| `ContextClosedEvent` | Context bắt đầu đóng. | Không nên khởi tạo công việc mới. |

Bảng mô tả mốc của một `SpringApplication` thông thường. Các listener sự kiện mặc định chạy đồng bộ với luồng phát sự kiện; không nên đặt thao tác lâu, có thể chặn khởi động, trong listener. Với cây parent/child contexts, một listener có thể nhận sự kiện của nhiều context: cần phân biệt context phát sự kiện.

## 5. Live khác Ready như thế nào?

Spring Boot dùng `ApplicationAvailability` để biểu diễn hai trục trạng thái:

- **Liveness**: ứng dụng có còn ở trạng thái nội bộ cho phép hoạt động/khôi phục đúng không? `CORRECT` là bình thường; `BROKEN` gợi ý cần khởi động lại instance.
- **Readiness**: ứng dụng có nên nhận lưu lượng/công việc **ngay lúc này** không? `ACCEPTING_TRAFFIC` cho phép định tuyến; `REFUSING_TRAFFIC` yêu cầu tạm thời không định tuyến.

| Tình huống | Liveness | Readiness | Cách hiểu |
| --- | --- | --- | --- |
| Đang khởi động | `BROKEN` (trạng thái ban đầu) | `REFUSING_TRAFFIC` | Chưa phục vụ; probe HTTP thậm chí có thể chưa truy cập được. |
| Context đã refresh; runner còn chạy | `CORRECT` | `REFUSING_TRAFFIC` | Ứng dụng live nhưng chưa sẵn sàng. |
| Đã ready, vận hành bình thường | `CORRECT` | `ACCEPTING_TRAFFIC` | Có thể nhận việc mới. |
| Đang graceful shutdown | Thường vẫn `CORRECT` | `REFUSING_TRAFFIC` | Ngừng nhận việc mới; xử lý việc còn lại. |
| Đã shutdown xong | Không còn trạng thái ứng dụng để truy vấn | Không còn | Context/web server đã đóng. |

**Vì sao không gộp hai probe?** Một kho dữ liệu dùng chung bị chậm có thể khiến instance không nên nhận request mới, nhưng khởi động lại mọi instance không chữa được kho dữ liệu ấy, thậm chí làm sự cố dây chuyền nặng hơn. Vì vậy, **không đưa phụ thuộc bên ngoài vào liveness một cách tùy tiện**. Nếu cần đưa phụ thuộc vào readiness, phải xác định nó có thực sự là điều kiện nhận traffic và ứng dụng có cơ chế dự phòng hay không.

Khi thêm `spring-boot-starter-actuator`, Spring Boot có thể mở hai health group:

- `GET /actuator/health/liveness`
- `GET /actuator/health/readiness`

Trong Kubernetes, các probe group này được kích hoạt tự động khi Boot nhận diện môi trường. Ở môi trường khác, bật `management.endpoint.health.probes.enabled=true`. Không có Actuator hoặc chưa bật probes thì không nên mặc định hai URL đó tồn tại. Trạng thái bên trong `ApplicationAvailability` cũng khác với **khả năng gửi một HTTP request thành công**; nếu web server chưa mở hoặc đã đóng, probe không có phản hồi bình thường để đọc.

Có thể truy vấn trạng thái nội bộ qua `ApplicationAvailability.getLivenessState()` và `getReadinessState()`. Khi thực sự cần tạm dừng nhận lưu lượng trong lúc ứng dụng vẫn chạy, ứng dụng có thể phát `AvailabilityChangeEvent` với `ReadinessState.REFUSING_TRAFFIC`, sau đó phát `ACCEPTING_TRAFFIC` khi phục hồi. Thay đổi readiness **không tự động dừng thread, HTTP listener hoặc job đang chạy**; bộ điều phối phải sử dụng tín hiệu đó để quyết định định tuyến.

## 6. Chặng dừng: yêu cầu dừng khác với tắt ngay

Những đường dừng thường gặp gồm tín hiệu `SIGTERM` trong container/Linux, đóng `ApplicationContext` có chủ đích, và thao tác dừng từ môi trường triển khai. Spring Boot thông thường đăng ký JVM shutdown hook để đóng context khi JVM kết thúc bình thường. Không nên xem `SIGKILL`, mất điện, crash JVM hoặc lời gọi `Runtime.halt()` là graceful shutdown: các trường hợp đó có thể bỏ qua callback dọn dẹp.

Với ứng dụng web Spring Boot **3.3.x**, cấu hình rõ ràng:

```properties
# src/main/resources/application.properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Khi đóng context, cơ chế graceful shutdown của embedded web server cho request đang xử lý một khoảng thời gian để hoàn thành và ngừng nhận request mới theo cách mà server hỗ trợ. Spring Boot 3.3.x hỗ trợ Tomcat, Jetty, Reactor Netty và Undertow; hành vi từ chối request mới có thể khác nhau theo server (chẳng hạn Undertow trả 503). `spring.lifecycle.timeout-per-shutdown-phase` đặt giới hạn thời gian **mỗi pha dừng lifecycle**, không phải cam kết mọi công việc sẽ hoàn thành bất kể kéo dài bao lâu.

Trong quy trình đóng context, có các mốc/cơ chế liên quan:

1. Công bố không sẵn sàng (`ReadinessState.REFUSING_TRAFFIC`) để hệ thống định tuyến rút instance ra khỏi nhóm nhận traffic.
2. Context phát `ContextClosedEvent`; các bean triển khai `SmartLifecycle` được yêu cầu dừng theo pha (bao gồm web server graceful shutdown).
3. Spring tiêu hủy singleton, gọi callback dọn dẹp tương ứng như `@PreDestroy`, `DisposableBean.destroy()` hoặc destroy method đã khai báo.
4. Tài nguyên ứng dụng (pool, scheduler, client kết nối...) được giải phóng theo lifecycle đã đăng ký. Việc tiến trình JVM thực sự kết thúc còn phụ thuộc các luồng non-daemon và tiến trình quản lý nó.

Các bước trên mô tả **trách nhiệm và trình tự logic**; không nên tự giả định thứ tự tuyệt đối của mọi listener/bean khi có nhiều pha hoặc triển khai tùy biến.

Đối với Kubernetes, cần đủ thời gian cho việc ngừng định tuyến và dọn dẹp: đối chiếu `terminationGracePeriodSeconds` với thời gian shutdown, các pha `SmartLifecycle` và chi phí hoàn tất request. Nếu thời hạn của nền tảng hết, tiến trình có thể bị buộc dừng dù ứng dụng đang graceful shutdown.

**Cần tự quyết định chính sách riêng cho công việc nền**: một scheduled job, Kafka consumer hay thread tự tạo không tự nhiên được bảo đảm “drain” chỉ nhờ bật `server.shutdown=graceful`. Hãy quản lý việc ngừng nhận job mới, hoàn tất/hủy job đang làm và đóng tài nguyên bằng lifecycle phù hợp. Callback `@PreDestroy` nên nhanh, hữu hạn và có thể gọi trong tình huống dừng lỗi.

## 7. Ví dụ quan sát vòng đời bằng Java

Tạo một ứng dụng Spring Boot 3.3.x, Java 17+, với dependency `Spring Web` và `Spring Boot Actuator` (có thể tạo project bằng Spring Initializr). Lớp dưới đây là một file hoàn chỉnh tại `src/main/java/com/example/lifecycle/RuntimeLifecycleApplication.java`, trong package `com.example.lifecycle`.

```java
package com.example.lifecycle;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RuntimeLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeLifecycleApplication.class, args);
    }

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("[STARTED] Context da refresh; chua chay runner");
    }

    @Bean
    ApplicationRunner prepareApplication() {
        return args -> {
            // Chi minh hoa mot buoc khoi tao ngan, khong gia lap I/O that.
            System.out.println("[RUNNER] Hoan tat cong viec khoi dong");
        };
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("[READY] ApplicationReadyEvent");
    }

    @EventListener
    public void onReadinessChange(
            AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("[READINESS] " + event.getState());
    }

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println("[CLOSING] ContextClosedEvent");
    }

    @PreDestroy
    public void releaseResources() {
        System.out.println("[DESTROY] @PreDestroy");
    }
}
```

Thêm cấu hình cho ví dụ:

```properties
spring.application.name=lifecycle-demo
server.port=8080
management.endpoint.health.probes.enabled=true
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Chạy dự án Gradle trong terminal (Windows dùng `gradlew.bat bootRun`):

```bash
./gradlew bootRun
```

Trong quá trình khởi động thành công, các dòng do chính ví dụ in ra có thứ tự khái niệm như sau; log của Spring Boot sẽ xen kẽ:

```text
[STARTED] Context da refresh; chua chay runner
[RUNNER] Hoan tat cong viec khoi dong
[READY] ApplicationReadyEvent
[READINESS] ACCEPTING_TRAFFIC
```

Ở terminal khác, sau khi ứng dụng ready:

```bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

Khi hai health group khả dụng và ở trạng thái khỏe mạnh, HTTP thường trả 200 cùng body có `"status":"UP"`. Nếu khởi động còn dở, không được suy luận rằng luôn đọc được HTTP 503: server có thể chưa sẵn sàng để nhận kết nối. Khi gửi tín hiệu dừng được JVM xử lý bình thường, quan sát các log `[CLOSING]`, `[DESTROY]` và trạng thái readiness; thứ tự xen kẽ của các listener khi dừng không nên dùng làm hợp đồng cho nghiệp vụ.

**Không dùng thời điểm in log để điều phối request**. Hãy dùng readiness probe của môi trường triển khai, kết hợp các chỉ số độ trễ, lỗi và việc xử lý công việc nền.

## 8. Ba kịch bản để tự kiểm tra hiểu biết

**Kịch bản A — “Port 8080 đã mở nhưng request chưa nên vào”.** Một `ApplicationRunner` mất 8 giây để nạp dữ liệu thiết yếu. Trong khoảng đó, context đã refresh và có thể đã có web server, nhưng `ApplicationReadyEvent` chưa xuất hiện; trạng thái readiness vẫn `REFUSING_TRAFFIC`. Bộ điều phối cần chờ readiness thay vì chỉ kiểm tra cổng TCP.

**Kịch bản B — “Ứng dụng còn sống nhưng tạm thời quá tải”.** JVM vẫn chạy, nội bộ vẫn hợp lệ, song instance cần tạm dừng nhận traffic. Đây thường là bài toán readiness: chuyển sang `REFUSING_TRAFFIC`, không mặc định chuyển liveness sang `BROKEN` để buộc restart.

**Kịch bản C — “Triển khai bản mới, instance cũ phải rút”.** Khi nhận yêu cầu dừng, instance cần tránh request mới, cho request đang xử lý hoàn tất trong giới hạn cho phép, dừng consumer/scheduler và đóng tài nguyên. Bật graceful shutdown cho web server và bảo đảm nền tảng cấp đủ thời gian. `SIGKILL` bỏ qua cơ hội dọn dẹp này.

## 9. Lỗi hiểu nhầm và cách chẩn đoán

| Nhầm lẫn / triệu chứng | Cách hiểu đúng / điểm cần kiểm tra |
| --- | --- |
| “Thấy `Started ... in ... seconds` là đã ready.” | Log có thể xuất hiện trước runner; xem `ApplicationReadyEvent` và readiness. |
| “Liveness trả UP nghĩa là tiếp nhận request được.” | Chỉ phản ánh một mặt của trạng thái; kiểm tra readiness, web server, đường đi thật. |
| “Có `@PostConstruct` là ứng dụng đã khởi động xong.” | Callback của **một bean** xảy ra trong lúc context dựng, có thể trước runner và ready. |
| “Mở cổng HTTP là phục vụ an toàn.” | Server có thể bind trước khi hoàn tất tác vụ khởi động. |
| “Đổi readiness sẽ đóng socket.” | Readiness là tín hiệu; bộ điều phối quyết định ngừng định tuyến. |
| “Bật graceful thì mọi background job hoàn thành.” | Cần cơ chế dừng/chờ riêng cho job và giới hạn thời gian phù hợp. |
| “Bất cứ lỗi database nào cũng phải đánh `BROKEN`.” | Lỗi phụ thuộc ngoài thường không đồng nghĩa instance nội bộ cần restart; cân nhắc readiness/fallback. |
| “Listener `ApplicationFailedEvent` dùng như bean bình thường luôn bắt được mọi lỗi.” | Lỗi có thể xảy ra trước lúc bean được tạo; listener bắt sự kiện sớm cần đăng ký sớm. |
| “`ContextClosedEvent` chứng minh JVM đã thoát.” | Nó cho biết context đóng; JVM/process còn có thể giữ thread hoặc tài nguyên khác. |

Khi gặp lỗi khởi động, kiểm tra **ngoại lệ gốc**, log `APPLICATION FAILED TO START`, profile/configuration, bean creation và cổng bị chiếm. Khi gặp lỗi dừng chậm, kiểm tra request đang chạy, `SmartLifecycle`, shutdown timeout, thread non-daemon, connection pool, consumer và deadline của orchestrator.

## 10. Checklist kiến thức cần giữ lại

1. Vẽ lại luồng `SpringApplication.run -> refresh context -> ApplicationStartedEvent -> runners -> ApplicationReadyEvent -> ACCEPTING_TRAFFIC`.
2. Giải thích được vì sao `@PostConstruct`, cổng HTTP mở và `ApplicationStartedEvent` chưa phải là “ready”.
3. Phân biệt liveness (có cần restart không?) và readiness (có nhận traffic ngay không?).
4. Mô tả đường dừng từ tín hiệu shutdown đến `ContextClosedEvent`, `SmartLifecycle` và hủy bean; nêu điều kiện graceful shutdown.
5. Khi vận hành, đo thời gian khởi động, theo dõi health probes, bảo đảm có giới hạn thời gian dừng và kiểm soát công việc nền.

## Tài liệu đối chiếu chính thức (Spring Boot 3.3)

- [SpringApplication: application events, runners và availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Actuator endpoints, Kubernetes probes và bảng trạng thái theo vòng đời](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
