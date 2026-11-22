# Giới hạn của health check hoặc startup log khi chứng minh ứng dụng hoạt động đúng

Khi triển khai một ứng dụng Spring Boot, người vận hành thường kiểm tra hai dấu hiệu đầu tiên:

1. Log có dòng thông báo ứng dụng đã khởi động, chẳng hạn `Started OrdersApplication in ... seconds`.
2. Endpoint sức khỏe như `/actuator/health` trả `{"status":"UP"}` hoặc HTTP 200.

Đây đều là tín hiệu hữu ích, nhưng **không đủ để kết luận mọi chức năng của ứng dụng đang hoạt động đúng**. Một tiến trình có thể còn sống, application context đã được khởi tạo, health endpoint phản hồi tốt, trong khi API tạo đơn hàng không ghi được database, kết quả tính giá bị sai, người dùng không đăng nhập được hoặc chỉ một số replica đang gặp lỗi.

Bài học này tập trung vào giới hạn của từng tín hiệu, mối quan hệ giữa **startup, liveness, readiness, health, functional correctness** và cách dùng Spring Boot Actuator cùng các phép kiểm chứng khác để hình thành một bức tranh vận hành đáng tin cậy.

> **Nguyên tắc:** log khởi động và health check cung cấp *bằng chứng có phạm vi*, không phải lời chứng minh tổng quát rằng toàn bộ hành vi nghiệp vụ đều đúng.

## 1. “Ứng dụng hoạt động đúng” là câu hỏi có nhiều cấp độ

Hãy xem các phát biểu:

- JVM process chưa bị thoát.
- Spring application context đã refresh thành công.
- Embedded HTTP server đang lắng nghe cổng.
- Một health endpoint trả kết quả thành công.
- Replica đang sẵn sàng nhận request.
- Một API trả HTTP 200.
- Người dùng có thể hoàn tất hành trình đặt hàng.
- Kết quả đặt hàng có số tiền chính xác và dữ liệu nhất quán.

Những phát biểu này **không tương đương**. Chúng mô tả các tầng khác nhau trong hệ thống.

```text
               Độ bao phủ của phép kiểm chứng tăng dần

      Tiến trình còn tồn tại
                |
                v
      Spring Boot khởi động được
                |
                v
      Ứng dụng sẵn sàng nhận traffic
                |
                v
      Dependency cần thiết đáp ứng
                |
                v
      API / workflow hoạt động
                |
                v
      Kết quả nghiệp vụ chính xác
                |
                v
      Ổn định dưới tải và qua thời gian
```

Sơ đồ diễn đạt **các phạm vi cần kiểm tra**, không phải một chuỗi bảo đảm logic tuyệt đối: có những ứng dụng không có HTTP server, và một ứng dụng có thể trả request đúng ngay cả khi một dependency không thiết yếu đang gặp lỗi.

### 1.1. Bảng phân biệt các tầng

| Tầng | Câu hỏi | Tín hiệu thường gặp | Điều chưa chứng minh được |
| --- | --- | --- | --- |
| Process | JVM còn tồn tại? | PID, trạng thái container | Thread có xử lý được request không |
| Startup | Context đã khởi tạo? | Startup log, sự kiện startup | Runner và công việc nền đã hoàn tất chưa |
| Liveness | Instance có còn khả năng hoạt động? | Liveness probe | Database hoặc nghiệp vụ có đúng không |
| Readiness | Có nên đưa traffic tới instance? | Readiness probe | Mọi request sẽ thành công không |
| Dependency health | Một phụ thuộc có phản hồi? | HealthIndicator, ping | Query thực tế hoặc giao dịch đầy đủ sẽ đúng không |
| API availability | Endpoint trả response? | HTTP test, synthetic check | Dữ liệu trả ra có đúng ý nghĩa nghiệp vụ không |
| Functional correctness | Quy tắc nghiệp vụ đúng? | Integration/E2E/contract test | Độ ổn định dưới tải dài hạn |
| Reliability | Hệ thống đáp ứng mục tiêu theo thời gian? | Metrics, SLI/SLO, traces | Không có bất kỳ lỗi hiếm nào |

Một quy trình quan sát tốt kết hợp nhiều tín hiệu và nói rõ **mỗi tín hiệu kiểm chứng điều gì**.

## 2. Startup log thực sự chứng minh điều gì?

Log khởi động là những thông điệp phát ra khi JVM, Spring Boot và các component đi qua từng bước initialization.

Ví dụ minh họa:

```text
INFO  Starting OrdersApplication using Java ...
INFO  The following 1 profile is active: "prod"
INFO  Tomcat initialized with port 8080 (http)
INFO  Started OrdersApplication in 4.823 seconds
```

Log này có thể cho biết:

- Java đã bắt đầu chạy application.
- Spring Boot đã đọc một phần cấu hình và ghi nhận profile.
- Embedded server đã khởi tạo trong quá trình startup.
- Spring Boot đã đến mốc mà nó ghi thông điệp `Started ...`.

Nhưng **một dòng log chỉ là thông tin đã được ghi ở một thời điểm**. Nó không liên tục kiểm tra trạng thái ứng dụng sau thời điểm ấy.

### 2.1. `Started ...` không đồng nghĩa `ApplicationReadyEvent`

Trong trình tự startup phổ biến của Spring Boot:

```text
SpringApplication.run(...)
          |
          v
Tạo và refresh ApplicationContext
          |
          v
Ghi startup log "Started ...", theo luồng Boot phổ biến
          |
          v
ApplicationStartedEvent
          |
          v
ApplicationRunner / CommandLineRunner
          |
          v
ApplicationReadyEvent
          |
          v
ReadinessState.ACCEPTING_TRAFFIC
```

Đây là sơ đồ ở mức khái niệm; chi tiết phụ thuộc phiên bản Spring Boot và những customization của `SpringApplication`.

Điểm quan trọng là các **runner thường chạy sau mốc started và trước ready**. Vì vậy, trong một tình huống runner bị lỗi:

```text
INFO  Started OrdersApplication in 4.823 seconds
ERROR Failed to execute ApplicationRunner
ERROR Application run failed
```

Dòng `Started ...` vẫn có thể từng xuất hiện dù **lần khởi động cuối cùng không hoàn tất thành công**.

### 2.2. Startup log không chứng minh tiến trình vẫn sống

Giả sử lúc 09:00 ứng dụng ghi:

```text
Started OrdersApplication in 4.823 seconds
```

Lúc 09:05 tiến trình có thể bị kill, bị hết bộ nhớ hoặc bị restart. Dòng log cũ vẫn tồn tại trong hệ thống log.

Khi điều tra, phải kết hợp:

- Timestamp của log.
- Process/container hiện tại có còn sống không.
- Process start time hoặc container restart count.
- Health probe hiện tại.
- Request traffic và error metrics trong khoảng thời gian đang xét.

Không dùng một startup log cũ để xác nhận một deployment mới đang khỏe.

### 2.3. Log có thể bị thiếu hoặc trễ

Log collector có thể:

- Nhận log chậm.
- Làm mất một phần log khi process thoát đột ngột.
- Gom log của nhiều replica.
- Hiển thị log của pod đã bị thay thế.
- Bị ảnh hưởng bởi sampling, buffering hoặc cấu hình log level.

Do đó, **không thấy log thành công** cũng chưa đủ để kết luận ứng dụng chắc chắn khởi động thất bại. Hãy kiểm tra trạng thái runtime và kết quả probe tại thời điểm hiện tại.

## 3. Spring Boot startup events và giới hạn của chúng

Spring Boot cung cấp các sự kiện liên quan lifecycle, trong đó:

| Sự kiện | Ý nghĩa tổng quát |
| --- | --- |
| `ApplicationStartingEvent` | Quá trình khởi động đã bắt đầu, context chưa được tạo hoàn chỉnh |
| `ApplicationEnvironmentPreparedEvent` | Environment đã được chuẩn bị |
| `ApplicationPreparedEvent` | Context đã chuẩn bị nhưng chưa refresh |
| `ApplicationStartedEvent` | Context đã refresh, runners chưa chạy |
| `ApplicationReadyEvent` | Runners đã hoàn tất theo luồng startup thành công |
| `ApplicationFailedEvent` | Quá trình startup thất bại |

Các event này cho biết tiến trình startup đã đi qua **mốc nào**, không tự động kiểm tra tất cả nghiệp vụ.

### 3.1. Listener ghi nhận ready

```java
package com.example.orders.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupEventsLogger {

    private static final Logger log =
            LoggerFactory.getLogger(StartupEventsLogger.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("event=application.ready");
    }
}
```

Log `application.ready` có ý nghĩa cụ thể hơn `application.started` nếu cần biết runners đã kết thúc.

Tuy nhiên, trong listener này bạn **không được mặc định**:

- Mọi background task đã xong.
- Kết nối database còn khỏe tại thời điểm request kế tiếp.
- Redis, Kafka hoặc API đối tác luôn sẵn sàng.
- Cấu hình quyền truy cập mọi endpoint đều đúng.
- Dữ liệu trả về đã chính xác theo nghiệp vụ.

### 3.2. Runner có thể trả về trước khi công việc nền hoàn tất

```java
@Component
public class WarmupRunner implements ApplicationRunner {

    private final Executor executor;
    private final CatalogService catalog;

    public WarmupRunner(Executor executor, CatalogService catalog) {
        this.executor = executor;
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        executor.execute(catalog::warmUp);
    }
}
```

Giả sử `Executor` và `CatalogService` đã được cấu hình. Runner trên chỉ **submit tác vụ** rồi trả về ngay. Spring Boot có thể tiếp tục đến `ApplicationReadyEvent` khi `warmUp()` còn chạy.

Nếu warm-up bắt buộc trước khi xử lý request, có hai hướng thiết kế:

1. Chờ công việc hoàn tất trong một runner đồng bộ, với timeout và xử lý lỗi rõ ràng.
2. Nếu công việc thực sự chạy nền, đặt điều kiện readiness phản ánh trạng thái hoàn tất thực tế trước khi cho phép traffic.

Một log “warm-up scheduled” hoàn toàn không đồng nghĩa “warm-up completed”.

### 3.3. Event ready là cột mốc, không phải health monitor

`ApplicationReadyEvent` thường phát khi startup thành công. Nó không tự phát lại mỗi khi database mất kết nối hoặc khi một hàng đợi bị nghẽn.

Vấn đề runtime cần health signals, metrics, tracing, logging hoặc các phép kiểm tra chuyên biệt khác.

## 4. Health check là gì?

**Health check** là một phép kiểm tra có phạm vi, trả về đánh giá sức khỏe theo tiêu chí được lập trình.

Một health endpoint có thể xem:

- Ứng dụng có phản hồi request kiểm tra không.
- JVM và application context còn vận hành.
- Một dependency có thể kết nối được không.
- Một điều kiện readiness tùy chỉnh đã được thỏa mãn chưa.

Với Spring Boot Actuator, health subsystem tập hợp kết quả từ nhiều `HealthIndicator` hoặc `HealthContributor` để tạo trạng thái tổng thể.

Ví dụ minh họa:

```http
GET /actuator/health
```

Response:

```json
{
  "status": "UP"
}
```

Điều này nói rằng **những health contributors đang được đưa vào kết quả** đã cho một đánh giá tổng thể `UP` theo chính sách aggregation. Nó không nói rằng mọi API và mọi hành trình nghiệp vụ đều được chạy thử.

### 4.1. `UP` là kết quả theo định nghĩa đã cấu hình

Giả sử endpoint chỉ có:

```text
PingHealthIndicator -> UP
```

Khi đó health `UP` có thể gần như chỉ chứng minh health endpoint đang xử lý được request, không chứng minh một database query hay chức năng thanh toán nào.

Nếu health group có:

```text
readinessState -> ACCEPTING_TRAFFIC
database -> UP
```

phạm vi kiểm tra rộng hơn, nhưng vẫn chưa chứng minh logic tính phí hoặc ghi giao dịch đúng.

**Một phép đo không thể cung cấp nhiều ý nghĩa hơn những điều kiện mà nó thực sự kiểm tra.**

### 4.2. HTTP 200 và JSON `UP` không phải hai bằng chứng độc lập

Trong cấu hình Actuator thông thường, health status được ánh xạ sang HTTP status theo các quy tắc của health endpoint. Ví dụ `UP` thường trả 200, còn `DOWN` hoặc `OUT_OF_SERVICE` thường trả 503.

Nhưng:

- Một reverse proxy có thể trả 200 thay cho backend.
- Endpoint sai path có thể trả 200 từ một static fallback.
- Một HTTP 401/403 có thể do security policy hoặc ingress, không nhất thiết do JVM chết.
- HTTP code mapping có thể được tùy chỉnh.

Vì vậy, kiểm tra đáng tin cậy phải xác định **đúng URL, đúng instance/route, đúng response contract và đúng thời điểm**, không chỉ tìm một response 200 bất kỳ.

## 5. Thêm Spring Boot Actuator

Trong dự án có Spring Boot dependency management, thêm starter tương ứng.

### 5.1. Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

### 5.2. Maven

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Ứng dụng web Spring Boot phù hợp có thể cung cấp endpoint health tại:

```text
/actuator/health
```

Đường dẫn thực tế có thể thay đổi theo `management.endpoints.web.base-path`, management port hoặc cấu hình khác.

### 5.3. Cấu hình hiển thị thông tin

Ví dụ:

```properties
management.endpoint.health.show-details=never
```

Các chế độ hiển thị chi tiết phụ thuộc version, thường có các lựa chọn như `never`, `when-authorized`, `always`.

Trong production, tránh expose chi tiết connection URL, topology hoặc thông tin nội bộ cho người không được phép. Health endpoints có mục tiêu phục vụ vận hành, không phải công khai toàn bộ trạng thái hạ tầng.

### 5.4. Health endpoint mặc định là điểm khởi đầu

Đừng giả định chỉ thêm Actuator thì ứng dụng sẽ kiểm tra mọi dependency.

Những health contributors auto-configured phụ thuộc vào:

- Dependency có trên classpath.
- Bean và auto-configuration được bật.
- Driver/kết nối đã được cấu hình.
- Health indicator tương ứng có được enable hay không.
- Health group nào đang được gọi.

Ví dụ một app có JDBC datasource có thể có database health contributor; một app không dùng datasource không tự có phép kiểm tra database.

## 6. Liveness và readiness khác nhau

Hai khái niệm này đặc biệt quan trọng khi triển khai bằng Kubernetes hoặc một orchestrator có cơ chế health probes.

### 6.1. Liveness: có cần restart instance không?

**Liveness** nhằm trả lời:

> Instance còn khả năng vận hành theo tiêu chí mà hệ thống dùng để quyết định có nên khởi động lại hay không?

Một lỗi liveness kéo dài có thể khiến orchestrator restart container, tùy cấu hình.

Nếu bạn đưa database health vào liveness, một đợt database outage có thể khiến **mọi instance bị restart đồng loạt**. Việc restart thường không chữa được database outage và còn tăng tải lên hạ tầng khi khôi phục.

Vì vậy, liveness nên tập trung vào tình trạng mà restart process **có khả năng giúp phục hồi**, chứ không gom mọi dependency bên ngoài vào.

### 6.2. Readiness: có nên gửi traffic tới instance không?

**Readiness** nhằm trả lời:

> Instance hiện có đủ điều kiện để nhận traffic theo hợp đồng vận hành của service không?

Khi readiness không thành công, orchestrator có thể loại instance khỏi tập endpoints phục vụ request, nhưng không nhất thiết restart process.

Readiness có thể phụ thuộc:

- Startup initialization bắt buộc đã hoàn tất.
- Một cache/reference data bắt buộc đã được nạp.
- Khả năng phục vụ loại request cốt lõi.
- Một dependency quan trọng, **nếu** chính sách vận hành quyết định từ chối traffic khi dependency ấy mất khả dụng.

### 6.3. Hai câu hỏi khác nhau, không dùng một probe cho mọi mục đích

| Tình huống | Liveness | Readiness | Cân nhắc |
| --- | --- | --- | --- |
| Context đã khởi động, đang warm-up bắt buộc | Có thể tốt | Chưa sẵn sàng | Không gửi traffic sớm |
| Database dùng chung tạm thời mất kết nối | Process có thể tốt | Tùy chính sách phục vụ | Restart hàng loạt có thể làm xấu hơn |
| Process deadlock, không xử lý được request | Có thể fail nếu probe thực sự phát hiện | Thường fail | Cần đánh giá khả năng phục hồi bằng restart |
| Service hoạt động nhưng API đối tác tùy chọn bị lỗi | Tốt | Có thể vẫn ready | Trả degraded behavior nếu thiết kế cho phép |
| Instance đang graceful shutdown | Có thể còn sống | Nên từ chối traffic mới | Cho request cũ hoàn tất |

Đừng biến readiness thành phép kiểm tra “mọi thứ trong thế giới bên ngoài luôn khỏe”. Nó phải phản ánh **khả năng phục vụ traffic theo cam kết**.

## 7. Spring Boot Availability API

Spring Boot cung cấp các trạng thái:

```java
LivenessState.CORRECT
LivenessState.BROKEN

ReadinessState.ACCEPTING_TRAFFIC
ReadinessState.REFUSING_TRAFFIC
```

Bạn có thể đọc bằng `ApplicationAvailability`.

```java
package com.example.orders.observability;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Service;

@Service
public class ReadinessReporter {

    private final ApplicationAvailability availability;

    public ReadinessReporter(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean acceptsTraffic() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
```

### 7.1. Khi nào readiness thành `ACCEPTING_TRAFFIC`?

Theo trình tự thông thường, Spring Boot phát `ApplicationReadyEvent` sau khi các runners đã hoàn tất, rồi công bố trạng thái sẵn sàng nhận traffic.

Đây là **tín hiệu lifecycle của Spring Boot**, không đồng nghĩa framework đã thực hiện mọi kiểm thử chức năng.

### 7.2. Phát thay đổi trạng thái

Ứng dụng có thể công bố tình trạng từ chối traffic:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

public void refuseTraffic(ApplicationContext context) {
    AvailabilityChangeEvent.publish(
            context,
            ReadinessState.REFUSING_TRAFFIC
    );
}
```

Điều này phù hợp khi có một điều kiện runtime khiến instance không nên nhận thêm request.

Nhưng state chỉ có ý nghĩa nếu hệ thống triển khai **thật sự đọc readiness signal**. Nếu một client gọi trực tiếp cổng HTTP mà không đi qua routing có health awareness, nó vẫn có thể gửi request.

### 7.3. Không dùng trạng thái để che nguyên nhân lỗi

Nếu một service chuyển readiness sang refusing, nên đồng thời có:

- Metric ghi lý do.
- Log event an toàn, không chứa secret.
- Trạng thái hoặc failure code phục vụ chẩn đoán.
- Quy tắc khôi phục readiness khi điều kiện được cải thiện.

Chỉ thay đổi readiness mà không có khả năng tìm nguyên nhân sẽ làm việc điều tra khó khăn.

## 8. Health probes trong Spring Boot Actuator

Với dòng Spring Boot hỗ trợ availability probes, có thể bật các health groups chuyên biệt trong môi trường phù hợp.

Ví dụ `application.properties`:

```properties
management.endpoint.health.probes.enabled=true
```

Những endpoint thường gặp:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Trong môi trường Kubernetes được nhận diện, một số phiên bản Spring Boot có thể tự kích hoạt probes. Khi chạy local, có thể bật tường minh như ví dụ.

### 8.1. Trường hợp thành công

Ví dụ response readiness:

```json
{
  "status": "UP"
}
```

Đây là đánh giá của **readiness health group**, không phải bài test chạy mọi controller.

### 8.2. Trường hợp từ chối traffic

Ví dụ response:

```json
{
  "status": "OUT_OF_SERVICE"
}
```

Với status mapping thông thường, trường hợp này có thể trả HTTP 503, cho orchestrator biết instance không sẵn sàng.

### 8.3. Health group khác nhau có thể có kết quả khác nhau

Một instance có thể có:

```text
Liveness: UP
Readiness: OUT_OF_SERVICE
```

Đây không phải mâu thuẫn. Nó có thể biểu thị JVM vẫn hoạt động nhưng không muốn nhận traffic, ví dụ trong startup warm-up hoặc graceful shutdown.

### 8.4. Group có phạm vi được cấu hình

Đừng suy luận:

```text
/actuator/health/readiness = UP
```

có nghĩa mọi HealthIndicator trong hệ thống đã được chạy. Readiness group thường dựa trên readiness state và những contributors bạn chọn thêm, không tự động bao gồm toàn bộ health contributors.

## 9. Health check chỉ đúng tại thời điểm quan sát

Giả sử health endpoint thực hiện một truy vấn `SELECT 1` và nhận response thành công lúc 10:00:00.

Lúc 10:00:01:

- Network có thể đứt.
- Connection pool có thể cạn.
- Transaction có thể deadlock.
- Database có thể chuyển primary.
- Một replica khác có thể bị lỗi.

Kết quả “UP lúc 10:00:00” **không chứng minh UP ở mọi thời điểm sau đó**.

### 9.1. Sampling và khoảng mù

Một probe được chạy mỗi 10 giây:

```text
10:00:00  UP
10:00:10  UP
10:00:20  UP
```

Nếu ứng dụng bị lỗi từ 10:00:12 đến 10:00:18 rồi hồi phục, các lần probe trên có thể **không nhìn thấy lỗi**.

Đây là giới hạn của kiểm tra định kỳ (*sampling*).

### 9.2. Probe nhanh không phát hiện mọi loại suy giảm

Ví dụ:

```text
Health request duration: 3 ms
Order checkout p99 latency: 9.5 s
```

Health endpoint có thể luôn rất nhanh vì không thực hiện cùng công việc với checkout. Trong khi đó, người dùng trải nghiệm chậm hoặc timeout.

Không dùng latency của `/actuator/health` thay thế latency của API thực tế.

### 9.3. Một lần thành công không chứng minh độ tin cậy

Nếu một API thành công 1 lần trong 100 lần, một lần health check `UP` không nói gì đáng tin cậy về tỷ lệ thành công của API.

Cần số liệu theo thời gian như request rate, error rate, latency distribution và những synthetic checks lặp lại theo chu kỳ hợp lý.

## 10. Dependency ping không chứng minh nghiệp vụ hoạt động

Một health indicator cho database có thể kiểm tra kết nối hoặc chạy truy vấn đơn giản. Điều này rất hữu ích để biết database **có phản hồi**.

Nhưng một API ghi đơn hàng có thể cần:

1. Lấy thông tin giỏ hàng.
2. Kiểm tra tồn kho.
3. Tính khuyến mãi.
4. Ghi bản ghi đơn hàng.
5. Cập nhật trạng thái tồn kho hoặc phát sự kiện.

Database trả `UP` không tự chứng minh các bước trên đúng.

### 10.1. Các tình huống database UP nhưng nghiệp vụ lỗi

- Schema thiếu cột sau một deployment.
- Entity mapping không khớp bảng.
- Permission của tài khoản service chỉ cho phép đọc, không cho phép ghi.
- Một bảng bị lock hoặc transaction thường timeout.
- Dữ liệu tham chiếu bắt buộc bị thiếu.
- Một migration đã thực hiện một phần.
- Query thực tế quá chậm dù truy vấn health đơn giản thành công.
- Business constraint được cấu hình sai.

Đây là những vấn đề **ngoài phạm vi** của một ping tối giản.

### 10.2. Một dependency có thể UP nhưng hệ thống vẫn lỗi

Ví dụ:

```text
Database: UP
Redis: UP
Kafka: UP
Payment gateway: UP

Checkout response: số tiền sai
```

Sức khỏe từng dependency không chứng minh logic tổng hợp đúng.

### 10.3. Không biến health indicator thành giao dịch nguy hiểm

Ý tưởng “health check sẽ thực hiện một thanh toán thật” có thể phát hiện nhiều lỗi hơn, nhưng gây:

- Tác dụng phụ nghiệp vụ.
- Chi phí và tranh chấp dữ liệu.
- Tăng tải khi probe được gọi thường xuyên.
- Nguy cơ trùng giao dịch và khó cleanup.

Health endpoint phục vụ orchestrator cần **nhẹ, nhanh, an toàn, có thể gọi lặp lại**. Các bài kiểm tra luồng nghiệp vụ sâu nên được thiết kế ở một tầng kiểm chứng khác.

## 11. Viết `HealthIndicator` tùy chỉnh

Spring Boot Actuator cho phép khai báo `HealthIndicator` để biểu diễn một điều kiện sức khỏe của ứng dụng.

Ví dụ, ứng dụng cần hoàn tất việc nạp dữ liệu tham chiếu trước khi trả kết quả cho API.

### 11.1. Trạng thái warm-up

```java
package com.example.orders.startup;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmupState {

    private final AtomicBoolean complete =
            new AtomicBoolean(false);

    public void markComplete() {
        complete.set(true);
    }

    public boolean isComplete() {
        return complete.get();
    }
}
```

`AtomicBoolean` giúp thread khác đọc trạng thái cập nhật an toàn ở mức bộ nhớ.

### 11.2. Runner làm công việc bắt buộc

```java
package com.example.orders.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmupRunner implements ApplicationRunner {

    private final CatalogService catalog;
    private final CatalogWarmupState state;

    public CatalogWarmupRunner(
            CatalogService catalog,
            CatalogWarmupState state) {
        this.catalog = catalog;
        this.state = state;
    }

    @Override
    public void run(ApplicationArguments args) {
        catalog.loadRequiredReferenceData();
        state.markComplete();
    }
}
```

`CatalogService` là service giả định do dự án định nghĩa, có method `loadRequiredReferenceData()`. Vì runner chờ method này trả về trước khi đánh dấu hoàn tất, trạng thái chỉ chuyển sang true **sau khi công việc đồng bộ thực sự kết thúc thành công**.

Nếu method ném exception, runner không đánh dấu complete và startup có thể thất bại. Đây là lựa chọn hợp lý khi thiếu dữ liệu khiến instance hoàn toàn không thể phục vụ request.

### 11.3. Custom indicator

```java
package com.example.orders.startup;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmupHealthIndicator
        implements HealthIndicator {

    private final CatalogWarmupState state;

    public CatalogWarmupHealthIndicator(CatalogWarmupState state) {
        this.state = state;
    }

    @Override
    public Health health() {
        return state.isComplete()
                ? Health.up().build()
                : Health.down().build();
    }
}
```

Bean name `catalogWarmupHealthIndicator` thường được Actuator chuyển thành contributor ID `catalogWarmup` theo quy ước đặt tên `HealthIndicator`.

### 11.4. Đưa indicator vào readiness group

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,catalogWarmup
```

Ý nghĩa mong muốn:

- `readinessState` phản ánh readiness lifecycle của Spring Boot.
- `catalogWarmup` phản ánh điều kiện dữ liệu tham chiếu đã chuẩn bị.

Khi cả hai contributors đánh giá phù hợp, health group có thể báo UP theo chính sách aggregation.

**Điểm cần nhớ:** việc một HealthIndicator tồn tại không tự động làm nó thuộc readiness group. Phải cấu hình health group phù hợp nếu muốn probe dùng kết quả của nó.

### 11.5. Custom health indicator không tự kiểm tra dữ liệu đã đúng

Trong ví dụ, `isComplete()` chỉ cho biết code đã đánh dấu xong. Nếu `loadRequiredReferenceData()` có bug, nạp thiếu một số bản ghi nhưng vẫn trả về bình thường, state vẫn thành true.

Indicator chỉ đáng tin bằng **điều kiện mà bạn lập trình**. Nếu điều kiện “complete” chưa kiểm chứng dữ liệu hợp lệ, health `UP` vẫn có thể xảy ra khi nghiệp vụ sai.

### 11.6. Đừng để phép kiểm tra bị block quá lâu

`health()` có thể được gọi nhiều lần bởi orchestrator hoặc hệ thống giám sát. Nếu mỗi lần gọi lại quét toàn bộ database hoặc tải file lớn:

- Probe dễ timeout.
- Connection pool chịu thêm tải.
- Lỗi hạ tầng có thể lan rộng do health checks.
- Hàng trăm replica có thể đồng thời tạo lượng truy vấn không cần thiết.

Với điều kiện cần tính toán nặng, cân nhắc **duy trì trạng thái đã đo định kỳ** rồi để `health()` trả kết quả nhanh, có giới hạn tuổi dữ liệu và cơ chế xử lý stale state.

## 12. Liveness, readiness và dependency health không nên gom bừa

Giả sử một hệ thống có 20 replicas cùng dùng một database.

Nếu database mất kết nối trong 30 giây và liveness của mọi replica phụ thuộc vào kết nối database:

```text
Database outage
      |
      v
20 liveness probes fail
      |
      v
Orchestrator restart 20 replicas
      |
      v
Connection storms + cold caches
      |
      v
Database phục hồi khó hơn
```

Đây là ví dụ về **tác hại của việc đưa một lỗi phụ thuộc dùng chung vào tiêu chí restart tiến trình**.

### 12.1. Có nên đưa database vào readiness?

Không có câu trả lời chung cho mọi hệ thống.

**Lý do có thể đưa vào:**

- Mọi request cốt lõi đều cần database.
- Replica không thể trả kết quả hữu ích khi database mất kết nối.
- Cần tránh gửi traffic tới instance không thể phục vụ.

**Lý do cần cân nhắc:**

- Mọi replica cùng mất database thì tất cả có thể unready.
- Một hệ thống có thể muốn trả degraded response hoặc 503 có kiểm soát thay vì bị gateway báo “không có endpoint”.
- Ping database có thể không phản ánh query thực tế.
- Quá nhiều probes có thể thêm tải trong sự cố.

Lựa chọn dựa trên **hợp đồng phục vụ traffic và chiến lược phục hồi**, không phải nguyên tắc “càng check nhiều càng tốt”.

### 12.2. Dependency không thiết yếu

Ví dụ hệ thống đơn hàng có dịch vụ gửi email xác nhận. Nếu gửi email lỗi, nhưng đơn hàng vẫn có thể được ghi và email được retry bất đồng bộ, không nhất thiết cần đánh readiness của toàn bộ Order API là DOWN.

Thay vào đó có thể:

- Ghi metric về email failures và queue backlog.
- Cảnh báo khi backlog tăng.
- Trả response nghiệp vụ theo quy tắc đã công bố.
- Theo dõi job retry riêng.

Readiness không nên bị chi phối bởi mọi thành phần phụ trợ.

## 13. Health endpoint trên management port riêng

Spring Boot có thể expose Actuator trên một management port khác với application HTTP port.

Ví dụ:

```properties
server.port=8080
management.server.port=9090
management.endpoint.health.probes.enabled=true
```

Khi đó health probe trên management port 9090 có thể trả UP **ngay cả khi đường xử lý traffic trên cổng 8080 có vấn đề riêng**.

Ví dụ:

- Main application connector không chấp nhận kết nối.
- Middleware chỉ áp dụng ở cổng ứng dụng đang bị lỗi.
- Ingress route tới cổng ứng dụng cấu hình sai.
- Cổng quản trị có thread pool hoặc connector khác.

### 13.1. Kiểm tra trên cùng đường nhận traffic

Trong các dòng Spring Boot hỗ trợ, có thể expose thêm liveness/readiness paths ở cổng ứng dụng:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

Khi tính năng được hỗ trợ và cấu hình đúng, các đường bổ sung thường là:

```text
/livez
/readyz
```

trên application port chính.

Hãy kiểm tra đường dẫn và phiên bản Spring Boot đang dùng. Đây là cách giảm rủi ro health riêng trên management port không phát hiện lỗi của application connector.

### 13.2. Cùng cổng vẫn không đồng nghĩa mọi endpoint đúng

Một `/readyz` trả UP trên cổng 8080 chỉ chứng minh request tới path đó thành công theo logic probe.

Nó vẫn không chạy route `/api/orders`, authentication pipeline đặc thù hoặc quy trình thanh toán.

Vì thế kiểm tra health ở cùng cổng là **cải thiện độ phủ của kết nối**, không phải phép chứng minh đúng nghiệp vụ.

## 14. Kubernetes probes: `startup`, `liveness`, `readiness`

Kubernetes có ba loại probe thường gặp:

| Loại | Câu hỏi | Hệ quả chính khi thất bại liên tiếp theo cấu hình |
| --- | --- | --- |
| `startupProbe` | Container đã qua giai đoạn startup cần thiết chưa? | Có thể restart container khi vượt ngưỡng failure |
| `livenessProbe` | Container có cần restart để phục hồi không? | Restart container nếu vượt ngưỡng |
| `readinessProbe` | Pod có nên nhận service traffic không? | Đánh dấu unready, rút khỏi các endpoints phục vụ traffic |

Một điều quan trọng: khi `startupProbe` được khai báo, Kubernetes **chưa thực thi liveness/readiness probes cho đến khi startup probe thành công**. Điều này giúp ứng dụng khởi động chậm không bị liveness restart quá sớm.

### 14.1. Ví dụ manifest fragment

Đoạn sau là phần cấu hình đặt dưới **một container** trong Pod spec:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 24

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
```

Ví dụ giả định các endpoint trên nằm tại cổng 8080, application có Actuator và probes đã được bật phù hợp.

Thông số `periodSeconds`, `timeoutSeconds` và `failureThreshold` phải được lựa chọn theo thời gian startup và đặc điểm runtime thực tế. Không sao chép nguyên các ngưỡng vào production mà không đo.

### 14.2. Giới hạn của startup probe

Nếu `startupProbe` chỉ gọi endpoint liveness, nó có thể thành công khi Spring Boot đã đánh giá liveness tốt nhưng một warm-up nghiệp vụ sau đó chưa kết thúc.

Vì vậy, startup probe là cơ chế điều phối **chờ một điều kiện startup đã định nghĩa**, không tự chứng minh nghiệp vụ đã ready. Readiness probe vẫn cần phản ánh khả năng nhận traffic.

### 14.3. Probe có thể không bắt kịp sự cố ngắn

Giả sử readiness probe chạy mỗi 5 giây. Một sự cố tồn tại 2 giây giữa hai lần probe có thể không bị phát hiện. Đây là giới hạn thời gian lấy mẫu.

Cần metrics và traces theo request thực tế để phát hiện những lỗi ngắn mà probe không ghi nhận.

### 14.4. Probe thất bại do mạng hoặc cấu hình

Probe có thể thất bại vì:

- Sai port/path.
- Không đúng HTTP scheme.
- Security filter yêu cầu authentication.
- Network policy hoặc sidecar gây lỗi kết nối.
- Timeout quá thấp.
- Node quá tải.

Khi thấy probe fail, hãy xác định **probe không truy cập được endpoint** hay **endpoint đã đánh giá ứng dụng không healthy**. Hai nguyên nhân có cách xử lý khác nhau.

## 15. Health check có thể báo UP khi authorization đang sai

Giả sử:

```text
GET /actuator/health   -> 200 UP
GET /api/orders        -> 403 Forbidden
```

Một khả năng là Spring Security configuration đã vô tình chặn nhóm user hợp lệ.

Health check mặc định có thể chạy qua một route hoặc security policy khác với API nghiệp vụ. Vì vậy, nó không phát hiện lỗi phân quyền ở endpoint thực.

### 15.1. Lỗi chức năng nhưng HTTP vẫn 200

Ví dụ API:

```http
GET /api/prices/SKU-100
```

Response:

```json
{
  "sku": "SKU-100",
  "price": 0,
  "currency": "VND"
}
```

Nó trả HTTP 200, nhưng giá 0 có thể vi phạm quy tắc nghiệp vụ.

Một synthetic check chỉ kiểm tra status 200 vẫn bỏ sót lỗi. Cần assert **response contract và kết quả mong đợi**, không chỉ mã HTTP.

### 15.2. Health không kiểm tra mọi role, tenant hoặc feature flag

Một API có thể đúng với admin nhưng sai với khách hàng thông thường, đúng với tenant A nhưng lỗi với tenant B, hoặc chỉ lỗi khi một feature flag đang bật.

Không hợp lý khi ép một health endpoint rất nhẹ chạy mọi ma trận điều kiện này. Hãy bổ sung tests, synthetic journeys, metrics phân nhóm và alert phù hợp.

## 16. Phân biệt “đang chạy” với “đúng dữ liệu”

Đây là khác biệt giữa **availability** và **correctness**.

Một chương trình có thể xử lý request ổn định, không throw exception và trả 200 cho mọi lời gọi, nhưng tính sai:

```java
public BigDecimal total(
        BigDecimal unitPrice,
        int quantity) {
    return unitPrice.add(
            BigDecimal.valueOf(quantity)
    );
}
```

Đoạn code trên cộng thay vì nhân. Nếu nghiệp vụ mong muốn `unitPrice × quantity`, kết quả sai mà không nhất thiết có lỗi hạ tầng.

Health check:

```text
Database: UP
JVM: healthy
HTTP route: reachable
```

không phát hiện quy tắc tính giá bị sai.

### 16.1. Cần kiểm thử nghiệp vụ

Ví dụ unit test minh họa:

```java
@Test
void calculatesTotalCorrectly() {
    BigDecimal total = calculator.total(
            new BigDecimal("125000"),
            3
    );

    assertThat(total).isEqualByComparingTo("375000");
}
```

Test này kiểm chứng một invariant cụ thể, khác với liveness/readiness.

### 16.2. Test cũng có giới hạn

Một unit test thành công không chứng minh production đang dùng cùng dữ liệu, cùng secret, cùng policy mạng và cùng trạng thái dependency.

Do đó, cần phối hợp **kiểm thử trước triển khai** với **quan sát runtime sau triển khai**.

### 16.3. Các invariant cần có nguồn sự thật

Một phép kiểm chứng chức năng tốt cần biết kết quả nào là đúng:

- Tổng tiền tính theo luật nào?
- Giao dịch có được ghi đúng một lần không?
- Một order đã thanh toán có thể chuyển trạng thái ra sao?
- Response nào được chấp nhận cho từng role?

Nếu tiêu chí đúng/sai không được định nghĩa, cả synthetic test lẫn health check đều khó bảo đảm chất lượng.

## 17. Tổng hợp một số tình huống “UP nhưng sai”

| Dấu hiệu | Lỗi thực tế | Vì sao health/startup không đủ? |
| --- | --- | --- |
| `Started ...` xuất hiện | Runner thất bại sau mốc started | Startup log đi trước runners |
| `/actuator/health` UP | Checkout gặp lỗi SQL permission | Health ping không ghi đơn hàng |
| Readiness UP | Cache nạp bất đồng bộ chưa xong | Runner chỉ submit task rồi trả về |
| Readiness UP | API trả sai giá | Readiness không kiểm thử quy tắc nghiệp vụ |
| Database health UP | Migration schema thiếu cột | Connectivity không bảo đảm schema phù hợp |
| Health UP | Một role bị chặn 403 sai | Health route có security path khác |
| Health UP | API p99 latency 9 giây | Probe nhẹ không đại diện tải thực |
| Health UP | Payment provider trả sai currency | Dependency alive không đồng nghĩa dữ liệu đúng |
| Health UP ở management port | Main port không nhận request | Hai connector có thể độc lập |
| Health UP trên một pod | Pod khác lỗi | Một probe không đại diện cả deployment |
| Log ready có timestamp cũ | Process đã crash/restart | Log là sự kiện lịch sử |
| Synthetic check trả 200 | Response body vi phạm contract | Kiểm tra status chưa đủ |
| E2E smoke test pass | Lỗi chỉ xảy ra khi tải cao | Smoke test không đo độ bền |

Những tình huống trên minh họa một nguyên tắc: **mọi phép đo đều có một tập điều kiện chưa được kiểm tra**.

## 18. Kiểm tra đường đi thật bằng synthetic monitoring

**Synthetic monitoring** chủ động gửi request giả lập vào hệ thống theo lịch để kiểm tra một số hành vi mong muốn.

Ví dụ một synthetic HTTP check cho API tra cứu danh mục:

1. Gọi một endpoint công khai phù hợp.
2. Xác nhận HTTP status dự kiến.
3. Xác nhận response có schema hợp lệ.
4. Kiểm tra một số field quan trọng.
5. Đo thời gian phản hồi.
6. Ghi kết quả ở hệ thống monitor riêng.

### 18.1. Synthetic sâu hơn health ping

Health check:

```http
GET /actuator/health
```

Kiểm tra chức năng:

```http
GET /api/catalog/items/SKU-DEMO
```

Đối với một mã sản phẩm giả lập ổn định, synthetic có thể kiểm tra:

```json
{
  "sku": "SKU-DEMO",
  "currency": "VND",
  "available": true
}
```

Nếu phép kiểm tra có dữ liệu và điều kiện mong đợi rõ ràng, nó phát hiện được nhiều loại lỗi nằm ngoài Actuator health.

### 18.2. Không dùng giao dịch thật để thử liên tục

Với luồng thanh toán, nên thiết kế:

- Sandbox payment provider.
- Test account hoặc test tenant được phân tách.
- Dữ liệu canary riêng.
- Hợp đồng không gây chuyển tiền thực.
- Cleanup/idempotency cho dữ liệu phát sinh.

Đừng tự động đặt hàng thật hoặc thực hiện khoản thu thật mỗi 10 giây chỉ để có synthetic check.

### 18.3. Synthetic vẫn không chứng minh tất cả

Một synthetic chỉ chạy bằng test account có thể bỏ sót lỗi của tài khoản thực, locale khác, loại sản phẩm khác hoặc dữ liệu quá lớn.

Hãy chọn một số **user journeys quan trọng**, không cố biến một synthetic test thành bản sao mọi tình huống production.

### 18.4. Synthetic nhìn từ vị trí nào?

Kiểm tra trực tiếp localhost của pod có thể bỏ qua:

- DNS công khai.
- API gateway.
- TLS termination.
- WAF.
- Ingress và routing.
- Network path từ người dùng.

Ngược lại, synthetic từ bên ngoài kiểm tra được nhiều thành phần hơn nhưng có thể chịu ảnh hưởng của Internet.

Nên sử dụng các điểm quan sát phù hợp với câu hỏi: **instance có hoạt động?** hay **người dùng từ bên ngoài có hoàn tất request được?**

## 19. Integration test, contract test và end-to-end test

Health checks phục vụ runtime; tests phục vụ kiểm chứng những hợp đồng và chức năng xác định.

### 19.1. Unit test

Kiểm tra quy tắc trong phạm vi một component:

```java
@Test
void rejectsNegativeQuantity() {
    assertThatThrownBy(
            () -> calculator.total(
                    new BigDecimal("10"),
                    -1
            )
    ).isInstanceOf(IllegalArgumentException.class);
}
```

Đây là ví dụ giả định calculator có validation như yêu cầu.

### 19.2. Integration test

Kiểm chứng tương tác với một hoặc nhiều thành phần thật hoặc môi trường test gần thực tế:

- Repository với một database test phù hợp.
- Transaction boundaries.
- SQL schema.
- Serialization/deserialization.
- Spring Security filter chain.

### 19.3. Contract test

Kiểm chứng giao diện trao đổi giữa consumer và provider:

- Request/response schema.
- Status code.
- Những field bắt buộc.
- Tương thích API version.

Một dependency trả health `UP` có thể vẫn vi phạm contract với service gọi nó. Contract testing bổ sung góc nhìn khác.

### 19.4. End-to-end test

Kiểm tra một hành trình từ đầu đến cuối:

```text
Đăng nhập
   |
   v
Tạo giỏ hàng
   |
   v
Áp dụng giá / khuyến mãi
   |
   v
Tạo đơn
   |
   v
Xác nhận trạng thái
```

E2E test tăng độ phủ tương tác nhưng thường tốn kém hơn, dễ phụ thuộc dữ liệu và môi trường. Nó không thay thế health probes nhẹ, luôn sẵn sàng cho orchestrator.

### 19.5. Phân bổ đúng vai trò

```text
Unit tests ------------> Đúng quy tắc nhỏ
Integration tests -----> Tương tác đúng giữa thành phần
Contract tests --------> Giao diện giữa service đúng
E2E tests -------------> User journey đúng trên môi trường test
Synthetic monitoring --> Một số user journey thật được kiểm tra định kỳ
Metrics/tracing/logs --> Hành vi và sự cố của traffic thực
Liveness/readiness ----> Quyết định vận hành instance
```

Không có một loại nào là “bằng chứng cuối cùng” bao phủ mọi trường hợp.

## 20. Metrics phản ánh trải nghiệm người dùng tốt hơn một ping

Để biết người dùng có thực sự sử dụng hệ thống được không, cần theo dõi các **Service Level Indicators (SLIs)** phù hợp.

Một số SLIs thường dùng:

- **Availability / success rate:** tỷ lệ request thành công theo định nghĩa dịch vụ.
- **Latency:** thời gian phản hồi, thường quan tâm các phân vị p95/p99.
- **Error rate:** tỷ lệ lỗi theo route và loại lỗi.
- **Throughput:** lưu lượng request hoặc số giao dịch.
- **Queue lag:** độ trễ hàng đợi trong hệ thống async.
- **Business outcome:** tỷ lệ giao dịch hoàn thành, tỷ lệ thanh toán thành công theo định nghĩa nghiệp vụ.

### 20.1. Tỷ lệ thành công

Một SLI minh họa:

\[
\text{Success rate}
= \frac{\text{Số request hợp lệ hoàn tất thành công}}
{\text{Tổng request hợp lệ được đo}}
\times 100\%
\]

Định nghĩa **request hợp lệ** và **thành công** cần được thống nhất. Ví dụ với API xác thực, HTTP 401 khi người dùng nhập sai mật khẩu có thể là kết quả hợp lệ của ứng dụng chứ không nhất thiết là lỗi availability.

### 20.2. Percentile latency

Nếu:

```text
Health endpoint: p99 = 5 ms
Checkout API:    p99 = 8 s
```

người dùng checkout vẫn gặp vấn đề dù health endpoint rất nhanh.

Latency cần đo **route hoặc user journey thực tế**, không dùng health endpoint làm đại diện cho mọi công việc.

### 20.3. Error budget và SLO

Một **SLO** (Service Level Objective) đặt mục tiêu như tỷ lệ thành công hoặc latency trong một khoảng thời gian.

Ví dụ:

```text
Mục tiêu: 99,9% checkout requests đủ điều kiện
hoàn thành thành công trong cửa sổ đo 30 ngày
```

Đây chỉ là ví dụ về cách biểu diễn SLO, không phải mục tiêu bắt buộc cho mọi ứng dụng.

Một deployment có `/health=UP` liên tục vẫn có thể vi phạm SLO vì 2% checkout requests bị lỗi.

### 20.4. Không nhầm metric của process với metric của sản phẩm

CPU thấp, JVM heap ổn định và health UP là những chỉ số vận hành đáng quan tâm, nhưng không chứng minh người dùng hoàn tất thanh toán hoặc nhận dữ liệu chính xác.

Khi thiết kế dashboard, đặt **service outcomes** bên cạnh **infrastructure signals**.

## 21. Tracing và logging giúp điều tra, không tự chứng minh đúng

Distributed tracing ghi lại một số bước xử lý của request:

```text
HTTP POST /orders
      |
      +--> validate input
      |
      +--> inventory-service
      |
      +--> database insert
      |
      +--> publish event
```

Một trace có thể cho biết:

- Bước nào chậm.
- Service nào trả lỗi.
- Có retry hay không.
- Request đã đi qua những span nào.

Nhưng trace không tự chứng minh:

- Giá tiền đúng công thức.
- Quyền truy cập được áp dụng chính xác.
- Dữ liệu ghi vào database đúng business invariant.
- Một message đã được consumer xử lý đúng một lần.

### 21.1. Trace thành công nhưng kết quả vẫn sai

```text
checkout trace status = OK
all spans completed
HTTP = 200
chargedAmount = 0 (đáng lẽ 300000)
```

Nếu code không phát hiện và đánh dấu lỗi logic, tracing có thể hiển thị một request “thành công”.

Do đó, muốn biết đúng sai nghiệp vụ phải có **assertion, invariant hoặc signal nghiệp vụ** tương ứng.

### 21.2. Logging cần field có ý nghĩa

Hữu ích:

```text
event=checkout.failed
failureCode=INVENTORY_TIMEOUT
route=/api/orders
traceId=<trace-id>
durationMs=713
```

Không nên:

```text
requestBody={...}
authorization=Bearer ...
customerEmail=...
```

Log chỉ nên chứa metadata đủ cho chẩn đoán, không dump dữ liệu nhạy cảm.

## 22. Quan sát theo replica, zone và version

Trong deployment nhiều replica:

```text
Load balancer
      |
      +--> pod A: healthy
      |
      +--> pod B: healthy
      |
      +--> pod C: faulty
```

Một lần gọi health qua load balancer có thể luôn được route tới pod A hoặc B. Kết quả 200 không phát hiện pod C lỗi.

### 22.1. Kiểm tra từng instance

Với orchestrator:

- Probe nên nhắm đúng instance/container cần đánh giá.
- Dashboard nên phân biệt pod, instance, zone, version.
- Metrics nên giúp so sánh error rate sau khi rollout.
- Logs/traces nên có instance hoặc deployment metadata phù hợp.

### 22.2. Lỗi chỉ xảy ra trên một phiên bản

Ví dụ rollout:

```text
version v1: 95% traffic, 0,1% errors
version v2:  5% traffic, 8% errors
```

Health endpoint của v2 vẫn có thể UP. Theo dõi **error rate và latency theo version** giúp phát hiện canary xấu trước khi mở rộng rollout.

### 22.3. Lỗi theo vùng

Một zone có thể mất kết nối tới cache, trong khi zone khác bình thường. Nếu dashboard chỉ tổng hợp tất cả replica, sự cố theo vùng có thể bị che.

Health status cần được nhìn cùng metadata triển khai và các SLIs theo phân đoạn có ý nghĩa.

## 23. Kiểm chứng sau deployment

Một quy trình deployment có thể chia thành các lớp kiểm tra:

```text
Build artifact
      |
      v
Start process
      |
      v
Verify startup state
      |
      v
Readiness gate
      |
      v
Smoke / synthetic tests
      |
      v
Gradual traffic rollout
      |
      v
Observe latency, errors, business SLIs
      |
      +--> Satisfactory -> Continue rollout
      |
      +--> Regression --> Stop / rollback according to policy
```

### 23.1. Kiểm tra artifact và configuration

Trước khi dựa vào health:

- Artifact đúng version/commit chưa?
- Active profile đúng chưa?
- Cấu hình external resources đã được nạp chưa?
- Schema migration có tương thích với version mới không?
- Secret và quyền service account có phù hợp không?

Một ứng dụng chạy được nhưng đang kết nối nhầm môi trường hoặc dùng feature flag sai vẫn có thể gây hậu quả lớn.

### 23.2. Readiness trước khi nhận traffic

Nếu startup runner tải dữ liệu bắt buộc, readiness nên từ chối traffic khi công việc chưa hoàn tất.

Không dùng startup log làm tín hiệu duy nhất để load balancer bắt đầu gửi request.

### 23.3. Smoke test

Chọn một số endpoint đại diện:

- Một read-only endpoint.
- Một protected endpoint với test principal phù hợp.
- Một chức năng nghiệp vụ cốt lõi.
- Một dependency path quan trọng.

Smoke test chỉ nên thực hiện thao tác an toàn, có dữ liệu kiểm soát và điều kiện mong đợi rõ.

### 23.4. Theo dõi sau rollout

Kiểm tra:

- Success/error rate của traffic thực.
- p95/p99 latency theo route.
- Database/HTTP client error classes.
- Queue backlog nếu hệ thống asynchronous.
- Business outcome metrics.
- So sánh với baseline trước rollout.

Nếu một trong các chỉ số này suy giảm nghiêm trọng, health UP không phải lý do để tiếp tục rollout bất chấp cảnh báo.

## 24. Khi nào một health indicator cần phép kiểm tra thật?

Không phải custom indicator nào cũng nên chỉ trả một `AtomicBoolean`. Một số điều kiện runtime cần kiểm tra theo thời gian.

Ví dụ: service chỉ có thể xử lý request khi bản snapshot cấu hình nghiệp vụ còn mới.

### 24.1. Kiểm tra freshness

Một trạng thái:

```java
@Component
public class SnapshotState {

    private final AtomicReference<Instant> lastLoadedAt =
            new AtomicReference<>();

    public void markLoaded(Instant instant) {
        lastLoadedAt.set(instant);
    }

    public boolean isFresh(Duration maxAge, Clock clock) {
        Instant loadedAt = lastLoadedAt.get();
        if (loadedAt == null) {
            return false;
        }
        return !loadedAt.isBefore(
                clock.instant().minus(maxAge)
        );
    }
}
```

Ví dụ giả định có imports `Instant`, `Duration`, `Clock` và `AtomicReference`.

Một indicator có thể dùng:

```java
@Component
public class SnapshotFreshnessHealthIndicator
        implements HealthIndicator {

    private final SnapshotState state;
    private final Clock clock;

    public SnapshotFreshnessHealthIndicator(
            SnapshotState state,
            Clock clock) {
        this.state = state;
        this.clock = clock;
    }

    @Override
    public Health health() {
        return state.isFresh(Duration.ofMinutes(10), clock)
                ? Health.up().build()
                : Health.down().build();
    }
}
```

Ở đây cần một `Clock` bean trong context, ví dụ cấu hình `Clock.systemUTC()` bằng `@Bean`.

### 24.2. Giới hạn của freshness check

Snapshot “vừa được tải” không bảo đảm nội dung đúng. Ví dụ nó có thể thiếu bản ghi hoặc chứa dữ liệu bất hợp lệ.

Do đó, nếu business contract yêu cầu dữ liệu chính xác, quá trình tải snapshot phải có validation phù hợp. Health check chỉ phản ánh trạng thái đã được cung cấp, không thay thế toàn bộ validation.

### 24.3. Tránh remote call ở mọi probe

Nếu 100 replicas, mỗi replica nhận readiness probe mỗi 5 giây và mỗi probe gọi database:

```text
100 / 5 = 20 probe-driven DB calls/giây
```

Chưa kể các monitoring agents khác. Khi database đang chậm, probes có thể góp thêm tải.

Một giải pháp có thể là health state được cập nhật định kỳ với timeout và giới hạn tần suất, trong khi endpoint trả về trạng thái cached có thông tin tuổi dữ liệu.

Nếu cache quá lâu, health report bị stale. Đây là **trade-off giữa chi phí đo và độ tươi của tín hiệu**.

## 25. Khi nào dùng `Health.up()` và khi nào `Health.down()`?

Một custom indicator nên phản ánh **định nghĩa sức khỏe được công bố**, không phải cảm nhận chung.

Ví dụ:

```java
@Override
public Health health() {
    if (!referenceDataAvailable()) {
        return Health.down().build();
    }
    return Health.up().build();
}
```

Nếu `referenceDataAvailable()` chỉ kiểm tra `cache != null`, ứng dụng vẫn có thể có cache rỗng hoặc stale mà health UP.

### 25.1. Có tiêu chí rõ, đo được

Ví dụ tiêu chí:

```text
Catalog snapshot đã được load thành công.
Validation của dữ liệu bắt buộc pass.
Snapshot không cũ hơn 10 phút.
```

Lúc này `UP` có ý nghĩa rõ hơn.

### 25.2. Không dùng một health status cho mọi tình huống

Nếu một tính năng phụ bị lỗi nhưng API chính vẫn phục vụ tốt, có thể ghi metric và cảnh báo về degradation thay vì đánh cả service DOWN.

Nếu hệ thống không thể bảo đảm tính đúng đắn cốt lõi, readiness refusing có thể là lựa chọn phù hợp.

Định nghĩa này cần được thống nhất giữa developer, vận hành và người chịu trách nhiệm dịch vụ.

## 26. Rủi ro thiết kế health check quá “thông minh”

Một health check chạy nhiều thao tác nghiệp vụ có thể biến chính nó thành nguồn lỗi:

- Đọc quá nhiều bảng và làm cạn connection pool.
- Gây deadlock với những transaction nghiệp vụ.
- Tạo side effect trên hệ thống thanh toán.
- Tạo thêm log và trace volume.
- Làm readiness dao động (flapping) khi một dependency có latency biến động.
- Tạo một vòng phụ thuộc khi service A kiểm tra service B và B lại kiểm tra A.

### 26.1. Hiện tượng readiness flapping

Ví dụ:

```text
12:00:00 UP
12:00:05 DOWN
12:00:10 UP
12:00:15 DOWN
```

Load balancer có thể liên tục thêm/bớt instance, làm traffic dao động.

Có thể cân nhắc:

- Probe thresholds hợp lý.
- Timeout và retry có giới hạn.
- Hysteresis trong cơ chế đánh giá trạng thái nếu nghiệp vụ cần.
- Dữ liệu trạng thái đo theo cửa sổ thời gian.

Đừng “fix” bằng cách luôn trả UP. Làm vậy che mất sự cố thay vì giảm nhiễu đo.

### 26.2. Health endpoint phải chịu được tình huống thiếu dependency

Một health endpoint dùng cùng database connection pool đã bị cạn có thể timeout. Điều này có thể là tín hiệu phù hợp về readiness, nhưng cũng cần phân biệt:

- App đang nghẽn tới mức không xử lý được request nào.
- Health check bị thiết kế tốn tài nguyên.
- Dependency bên ngoài lỗi trong khi app vẫn phục vụ những luồng khác.

Thiết kế readiness phải dựa trên khả năng phục vụ thực tế.

## 27. Health endpoint và an toàn thông tin

Health endpoint là một bề mặt HTTP cần quản lý.

### 27.1. Tránh lộ chi tiết không cần thiết

Một health response quá chi tiết có thể tiết lộ:

- Tên database hoặc loại database.
- Hostname nội bộ.
- Thông tin topology.
- Error message của dependency.
- Các thành phần hạ tầng đang được dùng.

Tốt hơn là cung cấp status tối giản cho người gọi probe và giới hạn chi tiết chẩn đoán ở endpoint/hệ thống nội bộ được bảo vệ.

### 27.2. 401/403 không tự động là app chết

Nếu Kubernetes probe không có credential nhưng endpoint đòi authentication, probe có thể thất bại mặc dù application hoạt động.

Cần cấu hình đường probe và policy truy cập thống nhất:

- Đủ mở cho thành phần điều phối cần gọi.
- Không expose không cần thiết ra Internet.
- Không làm lộ trạng thái hạ tầng nhạy cảm.

### 27.3. Tránh log secret khi debug health

Khi health indicator gặp lỗi kết nối, không ghi nguyên connection string chứa password, access token hoặc raw exception message chưa kiểm soát.

Nên log loại dependency, failure code và correlation information phù hợp:

```text
event=health.dependency.failed
dependency=database
failureCode=CONNECTION_TIMEOUT
```

Thời gian lưu và quyền truy cập các log này vẫn phải tuân theo chính sách vận hành.

## 28. Một ví dụ đầy đủ: startup log, readiness và API có kết quả sai

Giả sử ứng dụng Orders API:

```text
Spring Boot startup -> success
Catalog warm-up ------> completed
Readiness probe ------> UP
GET /api/prices ------> 200
```

Nhưng code tính giá:

```java
public BigDecimal calculate(
        BigDecimal unitPrice,
        int quantity) {
    return unitPrice.add(
            BigDecimal.valueOf(quantity)
    );
}
```

Lỗi này không vi phạm điều kiện liveness hoặc readiness đang được kiểm tra.

### 28.1. Dấu hiệu nào phát hiện?

| Phép kiểm tra | Có thể phát hiện lỗi cộng thay vì nhân? |
| --- | --- |
| Startup log | Không |
| `ApplicationReadyEvent` | Không |
| `/actuator/health` | Không, trừ khi custom health cố tình kiểm tra invariant đó |
| Database health | Không |
| HTTP status-only check | Không nếu API trả 200 |
| Unit test có expected total | Có |
| Integration/E2E test có expected total | Có |
| Synthetic với dữ liệu và expected result | Có, nếu test đi qua logic lỗi |
| Business invariant monitor | Có thể, nếu định nghĩa và quan sát được bất thường |

### 28.2. Không nhét bài test tính giá vào liveness

Việc thêm mọi unit test vào liveness không phù hợp:

- Liveness được gọi thường xuyên.
- Liveness fail có thể restart process.
- Một lỗi tính giá do code sẽ không được sửa bằng restart.
- Lỗi code có thể ảnh hưởng mọi instance, gây restart loop.

Giải pháp đúng hơn là ngăn lỗi qua tests và deployment checks; nếu phát hiện lỗi ở runtime, rollback hoặc tắt feature theo quy trình.

### 28.3. Readiness chỉ nên phản ánh điều kiện phục vụ được

Nếu một dependency hoặc dữ liệu cấu hình khiến instance **tạm thời không thể phục vụ an toàn**, readiness có thể từ chối traffic.

Nhưng nếu code logic triển khai bị bug ở mọi instance, readiness fail đồng loạt không phải chiến lược khôi phục đầy đủ. Cần xác định nguyên nhân và phát hành bản sửa/rollback.

## 29. Xây “bộ bằng chứng” thay vì một đèn xanh

Trong dashboard vận hành, nên hiển thị các tín hiệu có phạm vi khác nhau:

```text
Deployment: order-api v2.4

Process:
  8/8 instances running

Startup:
  8 instances reached ready event

Probes:
  8/8 liveness passing
  8/8 readiness passing

Service SLIs:
  checkout success rate = 98.1%
  checkout p99 = 6.4s

Functional checks:
  catalog synthetic = passing
  checkout synthetic = failing
```

Các số trên **chỉ minh họa**, không phản ánh một hệ thống thực tế.

Trong tình huống này, kết luận đúng không phải “ứng dụng khỏe vì 8/8 health UP”. Checkout đang có dấu hiệu suy giảm rõ ràng và cần được xử lý.

### 29.1. Tách kết luận theo từng tín hiệu

| Tín hiệu | Kết luận được phép |
| --- | --- |
| 8/8 process chạy | Tiến trình đang tồn tại |
| 8/8 ready event | Startup đã đến mốc ready trong lần khởi động ghi nhận |
| 8/8 readiness UP | Các readiness conditions hiện tại đang pass |
| Checkout success 98.1% | Theo định nghĩa SLI, khoảng 1.9% không thành công |
| Checkout synthetic fail | Hành trình synthetic cụ thể chưa đạt điều kiện mong đợi |

Những kết luận này không phủ định nhau. Chúng cho biết các tầng khác nhau của hệ thống đang ở tình trạng khác nhau.

### 29.2. Không chỉ hiển thị trạng thái hiện tại

Một dashboard tốt còn có:

- Đồ thị theo thời gian.
- So sánh với trước deployment.
- Phân nhóm theo version, zone hoặc tenant nếu phù hợp.
- Chú thích thời điểm rollout.
- Tương quan giữa errors, latency và dependency incidents.

Điều này giảm khả năng một sự cố ngắn bị che bởi trạng thái UP tại thời điểm bạn mở dashboard.

## 30. Cách điều tra khi startup log thành công nhưng người dùng báo lỗi

Một quy trình thực tế:

### Bước 1 — Xác nhận phạm vi

- Người dùng gặp lỗi ở endpoint nào?
- Lỗi xảy ra với mọi request hay một nhóm cụ thể?
- Có liên quan một tenant, role, region hoặc version không?
- Có timestamp, request ID hoặc trace ID không?

Không yêu cầu người dùng cung cấp password, OTP hoặc access token.

### Bước 2 — Kiểm tra trạng thái runtime

- Process/pod hiện đang chạy không?
- Có restart liên tục không?
- Liveness/readiness của đúng instance là gì?
- Pod đã ready trước hay sau khi lỗi xuất hiện?

### Bước 3 — Kiểm tra SLI của route bị ảnh hưởng

- Tỷ lệ 5xx hoặc các failure codes có tăng không?
- Latency p95/p99 có thay đổi không?
- Traffic volume có thay đổi không?
- Một dependency có timeout hoặc connection pool exhaustion không?

### Bước 4 — Xem trace và log có correlation

Tìm request cụ thể, xem:

- Request đi qua những service nào.
- Span nào lỗi hoặc mất thời gian dài.
- Failure code được ghi là gì.
- Có retry hoặc circuit breaker không.

Tránh dump raw request hoặc response chứa dữ liệu cá nhân.

### Bước 5 — Xác nhận correctness

Nếu HTTP trả 200 nhưng kết quả sai:

- So sánh với business invariant hoặc expected result.
- Kiểm tra dữ liệu, feature flags, schema và version.
- Tạo một test tái hiện bằng dữ liệu kiểm soát.
- Đánh giá phạm vi ảnh hưởng đến dữ liệu đã ghi.

### Bước 6 — Chọn cách khôi phục

- Restart instance nếu nguyên nhân là trạng thái process có thể phục hồi bằng restart.
- Tạm rút traffic nếu instance không thể phục vụ.
- Rollback deployment khi lỗi nằm ở code/config mới.
- Khôi phục dependency hoặc điều chỉnh resource khi lỗi hạ tầng.
- Sửa dữ liệu nếu sự cố ảnh hưởng tính đúng đắn, theo quy trình riêng.

Không mặc định restart chỉ vì một dashboard báo lỗi. Hành động phải phù hợp với nguyên nhân.

## 31. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Có dòng `Started ...` nghĩa ứng dụng đã ready.” | Startup log có thể xuất hiện trước runners và ready event |
| “Log startup hôm qua chứng minh app hiện còn sống.” | Log chỉ phản ánh thời điểm đã ghi |
| “`/health` trả 200 là mọi API đúng.” | Health chỉ kiểm tra các contributors được cấu hình |
| “Readiness UP chứng minh thanh toán đúng.” | Readiness là quyết định nhận traffic, không phải E2E nghiệp vụ |
| “Database UP nghĩa CRUD chắc chắn thành công.” | Ping không kiểm tra permission, schema, transaction hoặc query thực tế |
| “Liveness nên chứa mọi dependency để chặt chẽ.” | Có thể gây restart storm khi dependency dùng chung lỗi |
| “Readiness DOWN luôn phải restart process.” | Unready thường nhằm rút traffic, không nhất thiết restart |
| “Health endpoint nhanh nghĩa API nhanh.” | Health route có workload khác API |
| “Một lần synthetic pass chứng minh không có bug.” | Synthetic chỉ bao phủ một số input và thời điểm |
| “HTTP 200 đồng nghĩa kết quả nghiệp vụ đúng.” | Body có thể sai contract hoặc business invariant |
| “Management port UP nghĩa application port UP.” | Hai connector có thể gặp lỗi khác nhau |
| “Một pod khỏe nghĩa cả deployment khỏe.” | Replica/zone/version khác có thể hỏng |
| “`ApplicationReadyEvent` đợi mọi async task.” | Runner có thể chỉ submit task rồi kết thúc |
| “Cho health check gọi toàn bộ workflow thật là tốt nhất.” | Có thể tốn tài nguyên và gây side effects |
| “Readiness luôn phải phụ thuộc database.” | Phụ thuộc chiến lược phục vụ, fallback và phục hồi |
| “Metrics thay thế mọi test.” | Metrics cho biết hành vi quan sát được; test xác nhận các điều kiện kỳ vọng |
| “Trace hoàn tất nghĩa kết quả đúng.” | Trace có thể không biết invariant nghiệp vụ |
| “Health UP là đủ để tăng rollout lên 100%.” | Cần theo dõi SLI và synthetic của version mới |

## 32. Bài tập thực hành

### Bài 1 — Phân loại tín hiệu

Cho các tín hiệu:

1. JVM process tồn tại.
2. `Started ...` log xuất hiện.
3. `/actuator/health/liveness` UP.
4. `/actuator/health/readiness` UP.
5. `POST /api/orders` trả 201.
6. Một order test có tổng tiền đúng.
7. Checkout success rate 99.9% trong 24 giờ.

Hãy phân loại chúng theo process, startup, readiness, API availability, correctness và reliability. Nêu giới hạn của mỗi tín hiệu.

### Bài 2 — Runner thất bại sau startup log

Tạo một `ApplicationRunner` ném `IllegalStateException` không được xử lý.

Quan sát các log và lifecycle events trong một dự án thử nghiệm. Giải thích vì sao có thể đã thấy startup log nhưng không có ready event.

### Bài 3 — Actuator health

Thêm Spring Boot Actuator và bật probes trong môi trường local:

```properties
management.endpoint.health.probes.enabled=true
```

Quan sát:

```text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
```

Giải thích vì sao những endpoints đó có thể trả kết quả khác nhau.

### Bài 4 — Custom warm-up indicator

Tạo `CatalogWarmupState`, runner và `CatalogWarmupHealthIndicator`. Cấu hình readiness group chứa `catalogWarmup`.

Giải thích tiêu chí cho phép chuyển từ DOWN sang UP và điều gì xảy ra nếu tác vụ warm-up ném exception.

### Bài 5 — Async warm-up

Sửa runner để submit warm-up vào executor rồi trả về ngay.

Hãy dự đoán khi nào `ApplicationReadyEvent` xuất hiện và trạng thái custom warm-up indicator có thể là gì. Thiết kế cơ chế readiness gate để tránh nhận traffic quá sớm.

### Bài 6 — Dependency ping khác CRUD

Giả sử datasource health UP nhưng API ghi đơn hàng bị lỗi do database user chỉ có quyền `SELECT`.

Hãy xác định:

- Phép kiểm tra nào đã pass?
- Phép kiểm tra nào còn thiếu?
- Có nên thêm một lệnh ghi thật vào liveness không?
- Test hoặc synthetic nào sẽ phát hiện an toàn?

### Bài 7 — Readiness và database outage

Một deployment có 20 replicas cùng dùng một database. Thiết kế chính sách liveness/readiness khi database mất kết nối 30 giây.

Phân tích nguy cơ restart storm, khả năng degraded response và lựa chọn alert dựa trên error rate.

### Bài 8 — Management port riêng

Chạy Actuator trên một management port khác application port.

Giả lập trường hợp đường HTTP của app chính không hoạt động trong khi management health vẫn UP. Đề xuất cách probe trên đường nhận traffic theo khả năng của Spring Boot version.

### Bài 9 — Kubernetes probes

Viết ba probe `startupProbe`, `livenessProbe`, `readinessProbe` cho một service có startup kéo dài.

Giải thích:

- Vì sao startup probe giúp tránh liveness restart sớm.
- Vì sao readiness có vai trò khác.
- Điều gì xảy ra khi probe timeout hoặc endpoint bị security filter trả 401.

### Bài 10 — HTTP 200 nhưng tính tiền sai

Tạo một `PriceCalculator` và test với giá 125000, số lượng 3, expected total 375000.

Làm hỏng logic từ nhân thành cộng và quan sát unit test phát hiện lỗi. Giải thích vì sao Actuator health không phát hiện.

### Bài 11 — Synthetic monitoring

Thiết kế một synthetic check cho endpoint danh mục dùng test data ổn định:

- HTTP status dự kiến.
- Schema response.
- Một số field và giá trị mong đợi.
- Latency threshold.
- Hợp đồng không gây side effects.

Nêu giới hạn của synthetic đó và trường hợp nó chưa đại diện người dùng thật.

### Bài 12 — Tính success rate

Trong một cửa sổ đo, service có 10.000 request đủ điều kiện, trong đó 9.850 request hoàn tất thành công.

Hãy tính success rate và so sánh với mục tiêu giả định 99.9%. Giải thích vì sao readiness UP trong cùng thời gian không mâu thuẫn với SLO bị vi phạm.

### Bài 13 — Canary rollout

Giả sử version A có error rate 0.2%, version B mới triển khai có error rate 7%, nhưng cả hai đều readiness UP.

Hãy mô tả quyết định rollout hợp lý, tín hiệu cần kiểm tra thêm và điều kiện stop/rollback theo policy.

### Bài 14 — Dashboard nhiều tầng

Thiết kế dashboard gồm:

- Replica count/restart count.
- Liveness/readiness status.
- API request rate/error rate/latency.
- Synthetic test results.
- Business outcome metric.
- Deployment version và thời điểm rollout.

Giải thích một trường hợp dashboard báo health xanh nhưng business metric đỏ.

### Bài 15 — Chẩn đoán khi người dùng báo lỗi

Người dùng báo “không đặt hàng được” và cung cấp request ID.

Hãy lập thứ tự kiểm tra từ runtime, probes, metrics, logs, traces tới correctness tests. Chỉ rõ thông tin nào không nên yêu cầu người dùng gửi.

### Bài 16 — Viết định nghĩa readiness

Với một dịch vụ giả định, viết tài liệu ngắn về:

- Điều kiện bắt buộc trước khi nhận traffic.
- Dependency thiết yếu và không thiết yếu.
- Điều kiện chuyển sang refusing.
- Quy tắc khôi phục accepting.
- Thời gian kiểm tra và giới hạn tải probe.
- Cách người vận hành xác định nguyên nhân khi probe fail.

Không dùng cụm “mọi thứ hoạt động tốt” làm định nghĩa readiness nếu không có điều kiện đo được.

## 33. Tổng kết

**Startup log** cho biết ứng dụng đã đi tới một mốc trong quá trình khởi động. **Liveness** giúp quyết định instance có cần restart không. **Readiness** cho biết instance có nên được đưa vào tập nhận traffic hay không. **Health check** chỉ đánh giá những điều kiện và contributors mà hệ thống đã định nghĩa.

Không tín hiệu nào trong số đó tự chứng minh mọi endpoint, mọi role, mọi dữ liệu và mọi quy tắc nghiệp vụ đều đúng. Một database health `UP` không bảo đảm giao dịch ghi thành công; một HTTP 200 không bảo đảm response đúng; một ready event không có nghĩa công việc bất đồng bộ đã hoàn tất; một probe xanh không phản ánh độ tin cậy theo thời gian.

Hãy dùng Actuator và Kubernetes probes cho quyết định vận hành, dùng tests và synthetic checks cho các hành vi quan trọng, dùng metrics/SLI/SLO để đánh giá trải nghiệm và độ tin cậy, dùng tracing/logging để tìm nguyên nhân. Chọn mỗi tín hiệu theo đúng câu hỏi cần trả lời, tránh health checks gây side effect hoặc tạo thêm tải khi có sự cố.

**Kết luận cần nhớ:** “Ứng dụng đang chạy” là một nhận định về trạng thái; “ứng dụng hoạt động đúng” đòi hỏi các bằng chứng về hành vi, kết quả và chất lượng phục vụ phù hợp với hợp đồng nghiệp vụ. Chỉ khi kết hợp những bằng chứng này, đội ngũ mới có thể đánh giá một hệ thống Spring Boot đáng tin cậy mà không đánh đồng một dòng startup log hoặc một kết quả health `UP` với thành công toàn diện.
