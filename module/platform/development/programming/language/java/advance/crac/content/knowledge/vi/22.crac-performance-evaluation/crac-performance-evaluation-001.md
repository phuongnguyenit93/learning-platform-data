# Định nghĩa thời gian khởi động, thời gian sẵn sàng và thời gian đáp ứng đầu tiên

Khi đánh giá hiệu năng một ứng dụng Java dùng CRaC (Coordinated Restore at Checkpoint), cần phân biệt rõ thời gian khởi động, thời gian sẵn sàng và thời gian đáp ứng đầu tiên. Ba chỉ số này có liên quan nhưng mô tả những giai đoạn khác nhau. Một tiến trình có thể được khôi phục rất nhanh nhưng chưa thể nhận request vì còn phải tạo lại connection, refresh cache hoặc hoàn tất warm-up. Ngược lại, Pod có thể đã Ready nhưng request đầu tiên vẫn chậm do JIT compilation, cache miss hoặc kết nối đến dịch vụ phụ thuộc.

Nếu chỉ đo một con số như “startup time”, nhóm phát triển có thể kết luận sai về lợi ích của checkpoint. Cần xác định mốc bắt đầu, mốc kết thúc và phạm vi đo cho từng chỉ số. Đồng thời, cần tách số đo bên trong JVM khỏi số đo quan sát từ Kubernetes hoặc client bên ngoài.

Bài học này định nghĩa các mốc thời gian, cách đo chúng trong ứng dụng Java và Kubernetes, cách diễn giải kết quả khi dùng CRaC, cùng phương pháp benchmark để so sánh cold start với restore.

## 1. Vì sao cần định nghĩa riêng từng chỉ số?

Một ứng dụng Java trải qua nhiều giai đoạn từ lúc container được tạo đến khi xử lý thành công request đầu tiên:

1. Kubernetes schedule Pod lên node.
2. Container runtime chuẩn bị filesystem và khởi chạy process.
3. JVM khởi động hoặc tiến trình được restore từ checkpoint.
4. Framework và ứng dụng hoàn tất khởi tạo.
5. Resource bên ngoài được tạo lại hoặc kết nối lại.
6. Cache thiết yếu được kiểm tra và warm-up.
7. Ứng dụng chuyển sang trạng thái Ready.
8. Request đầu tiên được gửi đến ứng dụng.
9. Ứng dụng xử lý request và gửi response.

Mỗi giai đoạn có thể có chi phí đáng kể. Nếu đo từ lúc Pod được tạo đến khi request đầu tiên trả về, số đo sẽ bao gồm cả thời gian scheduling, image pull, restore, readiness và xử lý request. Nếu chỉ đo từ lúc vào hàm main đến lúc framework báo ready, các chi phí Kubernetes và container sẽ không xuất hiện.

Vì vậy, cần xác định câu hỏi đang muốn trả lời:

- JVM hoặc process mất bao lâu để bắt đầu thực thi?
- Ứng dụng mất bao lâu để hoàn tất khởi tạo?
- Pod mất bao lâu để được Kubernetes đánh dấu Ready?
- Từ lúc bắt đầu restore đến lúc ứng dụng có thể nhận traffic mất bao lâu?
- Request đầu tiên mất bao lâu để trả response?
- Từ lúc tạo Pod đến response thành công đầu tiên mất bao lâu?

Các câu hỏi này không thể thay thế cho nhau.

## 2. Mô hình các mốc thời gian

Có thể đặt các mốc quan sát như sau:

| Mốc | Ý nghĩa |
|---|---|
| T0 | Bắt đầu phép đo ở cấp process, container hoặc Pod |
| T1 | JVM bắt đầu thực thi mã ứng dụng |
| T2 | Hoàn tất khởi tạo framework và application context |
| T3 | Hoàn tất restore callback và resource thiết yếu |
| T4 | Ứng dụng nội bộ chuyển sang READY |
| T5 | Kubernetes đánh dấu Pod Ready |
| T6 | Request đầu tiên đến ứng dụng |
| T7 | Response thành công đầu tiên được gửi |

Không phải hệ thống nào cũng cần tất cả mốc này. Điều quan trọng là ghi rõ mốc nào được dùng trong từng metric.

~~~mermaid
flowchart TD
    A["T0: Container/process start"] --> B["T1: JVM/application execution"]
    B --> C["T2: Framework initialized"]
    C --> D["T3: CRaC resources restored"]
    D --> E["T4: Application READY"]
    E --> F["T5: Kubernetes Pod READY"]
    F --> G["T6: First request received"]
    G --> H["T7: First successful response"]
~~~

Trong cold start, T1 thường là lúc JVM bắt đầu thực thi ứng dụng. Trong CRaC restore, process được dựng lại từ checkpoint và có thể tiếp tục từ trạng thái đã lưu. Vì vậy, cần ghi riêng mốc bắt đầu restore do runtime hoặc orchestrator cung cấp thay vì giả định mọi lần chạy đều có cùng mốc JVM launch.

## 3. Thời gian khởi động là gì?

**Thời gian khởi động (startup time)** là khoảng thời gian từ một mốc bắt đầu được xác định trước đến khi một thành phần hoặc ứng dụng hoàn tất giai đoạn khởi tạo được định nghĩa.

Thuật ngữ startup time thường bị dùng cho nhiều phạm vi. Khi công bố số đo, cần nêu rõ đó là:

- JVM startup time.
- Application startup time.
- Container startup time.
- Pod startup time.
- CRaC restore duration.

### 3.1. JVM startup time

JVM startup time thường đo từ lúc process Java được khởi chạy đến khi JVM bắt đầu thực thi mã ứng dụng hoặc đạt một mốc runtime được chọn.

Ví dụ:

- T0: process Java được tạo.
- T1: mã ứng dụng bắt đầu chạy.
- JVM startup time = T1 − T0.

Mốc này hữu ích khi phân tích chi phí khởi tạo JVM, class loading ban đầu, cấu hình runtime và các hoạt động trước khi application code bắt đầu.

Tuy nhiên, với CRaC, restore không giống một lần chạy Java mới từ đầu. Tiến trình được phục hồi từ checkpoint và có thể tiếp tục ở trạng thái đã khởi tạo. Do đó, không nên so sánh trực tiếp JVM startup time của cold start với restore duration nếu hai phép đo bắt đầu ở những mốc khác nhau.

### 3.2. Application startup time

Application startup time đo từ lúc ứng dụng bắt đầu khởi tạo đến khi framework hoặc ứng dụng hoàn tất giai đoạn startup được định nghĩa.

Ví dụ với một ứng dụng Spring Boot, có thể chọn sự kiện ApplicationReadyEvent làm mốc ứng dụng đã hoàn tất quá trình khởi tạo theo lifecycle của Spring Boot.

Nếu:

- T1: application startup bắt đầu.
- T2: application ready event xảy ra.

Thì:

\[
T_{\text{application-startup}} = T2 - T1
\]

Mốc này thường bao gồm:

- Khởi tạo dependency injection container.
- Tạo bean.
- Đăng ký route.
- Nạp cấu hình.
- Khởi tạo serializer và mapper.
- Tạo một số client hoặc resource.
- Chạy application runner hoặc startup task.

Cần xem xét chính xác framework event được chọn. Một sự kiện báo context refreshed không nhất thiết đồng nghĩa với việc mọi resource đã sẵn sàng để phục vụ request.

### 3.3. Container và Pod startup time

Container startup time thường đo từ lúc container runtime bắt đầu tạo hoặc chạy container đến khi process trong container bắt đầu hoạt động.

Pod startup time có phạm vi rộng hơn. Nó có thể gồm:

- Scheduler chọn node.
- Pull image.
- Mount volume.
- Tạo sandbox và network.
- Tạo container.
- Khởi động process.
- Restore hoặc khởi động JVM.
- Chờ startup/readiness probe.

Khi đo Pod startup time, cần quyết định T0 là Pod creation timestamp, thời điểm Pod được schedule hay thời điểm container bắt đầu chạy. Mỗi lựa chọn trả lời một câu hỏi vận hành khác nhau.

## 4. Thời gian restore trong CRaC

Với CRaC, cần thêm một metric riêng: **restore duration**.

Restore duration thường đo từ lúc runtime hoặc công cụ bắt đầu khôi phục checkpoint đến khi process được phục hồi và có thể tiếp tục thực thi ở mức runtime. Mốc kết thúc chính xác phụ thuộc vào công cụ tạo ảnh và cách tích hợp CRaC.

Restore duration không nhất thiết bao gồm toàn bộ công việc trong callback afterRestore, warm-up hoặc readiness. Vì vậy, nên ghi riêng:

- Restore start.
- Process resumed.
- afterRestore preparation completed.
- Application ready.
- Pod ready.

Ví dụ:

| Giai đoạn | Thời gian minh họa |
|---|---:|
| Restore process | 180 ms |
| Recreate database/Redis clients | 350 ms |
| Refresh cache thiết yếu | 220 ms |
| Application readiness transition | 30 ms |
| Kubernetes probe observation delay | 5 s |
| First request processing | 45 ms |

Trong ví dụ này, restore process chỉ mất 180 ms nhưng thời gian để Pod Ready dài hơn nhiều. Nếu chỉ báo cáo restore duration, người đọc có thể hiểu nhầm rằng ứng dụng đã có thể phục vụ sau 180 ms.

### 4.1. Mốc bắt đầu của phép đo restore

Tùy kiến trúc, có thể chọn:

- Thời điểm restore controller yêu cầu khôi phục.
- Thời điểm CRIU bắt đầu restore.
- Thời điểm container runtime bắt đầu thao tác restore.
- Thời điểm container process được khôi phục.

Nếu so sánh các lần chạy, phải dùng cùng một định nghĩa. Thời gian scheduling và image pull nên được đo riêng nếu mục tiêu là đánh giá riêng phần CRaC.

### 4.2. Callback afterRestore không đồng nghĩa với Pod Ready

Callback afterRestore cho phép ứng dụng phục hồi resource sau khi process được khôi phục. Trong callback, ứng dụng có thể:

- Tạo lại connection pool.
- Kết nối Redis hoặc database.
- Refresh DNS hoặc service discovery.
- Khôi phục subscription.
- Invalidate cache stale.
- Warm-up dữ liệu thiết yếu.

Khi callback kết thúc, ứng dụng mới chỉ hoàn tất những công việc được callback quản lý. Kubernetes còn cần quan sát readiness probe và cập nhật trạng thái Pod. Nếu ứng dụng còn thực hiện background initialization sau callback, Pod có thể cần chờ thêm.

## 5. Thời gian sẵn sàng là gì?

**Thời gian sẵn sàng (time to readiness)** là khoảng thời gian từ mốc bắt đầu được chọn đến khi ứng dụng hoặc Pod đáp ứng điều kiện sẵn sàng nhận traffic.

Cần phân biệt hai metric:

1. Application readiness time: thời điểm ứng dụng nội bộ tuyên bố đã sẵn sàng.
2. Kubernetes Pod Ready time: thời điểm Kubernetes đánh dấu Pod condition Ready là True.

Hai mốc này có thể cách nhau do chu kỳ probe, timeout, readiness gate và cập nhật trạng thái của control plane.

### 5.1. Application readiness

Ứng dụng có thể đánh dấu READY khi:

- JVM hoặc process đã tiếp tục thực thi.
- Các resource bắt buộc đã được tạo lại.
- Dependency thiết yếu có thể truy cập.
- Cache critical đã được refresh hoặc có fallback hợp lệ.
- Admission gate đã mở.
- Request handler có thể xử lý request đúng chính sách.

Không nên đánh dấu READY chỉ vì application context đã được tạo nếu database hoặc Redis là dependency bắt buộc mà vẫn chưa kết nối.

Ngược lại, không nên bắt mọi dependency tùy chọn phải sẵn sàng nếu ứng dụng có thể hoạt động an toàn khi chúng tạm thời unavailable.

### 5.2. Kubernetes Pod Ready

Kubernetes xác định readiness dựa trên container readiness, probe và các readiness gate được cấu hình.

Khi readiness probe thành công, trạng thái Pod có thể chuyển sang Ready sau khi kubelet cập nhật Pod condition. Do đó, Pod Ready time có thể muộn hơn thời điểm ứng dụng nội bộ chuyển READY.

Metric Pod Ready hữu ích cho việc vận hành rollout, autoscaling và Service endpoint. Metric application readiness hữu ích để phân tích thời gian khởi tạo bên trong process.

### 5.3. Readiness không phải thời gian khởi động

Một ứng dụng có thể khởi động xong nhưng chưa sẵn sàng nhận traffic. Ví dụ:

- Framework đã khởi tạo nhưng database connection pool chưa tạo xong.
- Redis client đã được tạo nhưng chưa xác thực.
- Cache đã tồn tại trong heap nhưng cần kiểm tra TTL/version.
- Message consumer chưa được đăng ký lại.
- Native resource chưa được mở lại.
- Warm-up critical chưa hoàn tất.

Vì vậy, application startup time thường ngắn hơn hoặc bằng time to readiness nếu readiness bao gồm các bước bổ sung. Nhưng điều này phụ thuộc cách định nghĩa mốc và lifecycle cụ thể.

## 6. Thời gian đáp ứng đầu tiên là gì?

Cụm từ **thời gian đáp ứng đầu tiên (first response time)** có thể được hiểu theo hai cách. Cần phân biệt rõ để tránh trộn lẫn latency của request với thời gian chờ từ lúc khởi động.

### 6.1. First-request latency

First-request latency là thời gian từ lúc ứng dụng nhận request đầu tiên đến lúc hoàn tất response của request đó.

Gọi:

- T6: thời điểm request đến.
- T7: thời điểm response hoàn tất.

Khi đó:

\[
L_{\text{first-request}} = T7 - T6
\]

Chỉ số này phản ánh chi phí xử lý request đầu tiên, có thể bao gồm:

- Routing và filter.
- Deserialization.
- JIT compilation còn thiếu.
- Lazy initialization.
- Cache miss.
- Kết nối dependency phát sinh theo request.
- Business logic.
- Serialization.
- Gửi response.

Đây là latency của một request cụ thể.

### 6.2. Time to first successful response

Time to first successful response đo từ mốc khởi động hoặc restore đến khi ứng dụng trả response thành công đầu tiên.

Gọi:

- T0: mốc bắt đầu phép đo.
- T7: response thành công đầu tiên.

Khi đó:

\[
T_{\text{first-response}} = T7 - T0
\]

Metric này bao gồm cả thời gian khởi động, readiness và thời gian chờ request đầu tiên được gửi đến ứng dụng.

Nếu request chỉ được gửi sau khi Pod Ready, có thể phân rã:

\[
T_{\text{first-response}} =
T_{\text{ready}} + T_{\text{wait-for-request}} + L_{\text{first-request}}
\]

Trong đó các thành phần đều được đo từ cùng mốc T0 và theo định nghĩa đã thống nhất.

### 6.3. Ví dụ phân biệt hai chỉ số

Giả sử:

- Pod bắt đầu restore lúc 10:00:00.000.
- Application Ready lúc 10:00:00.700.
- Kubernetes Pod Ready lúc 10:00:01.100.
- Load balancer gửi request đầu tiên lúc 10:00:01.300.
- Response hoàn tất lúc 10:00:01.420.

Khi đó:

| Metric | Giá trị |
|---|---:|
| Restore-to-application-ready | 700 ms |
| Restore-to-Pod-Ready | 1.100 ms |
| First-request latency | 120 ms |
| Restore-to-first-successful-response | 1.420 ms |

First-request latency chỉ là 120 ms. Nhưng hệ thống cần 1.420 ms từ lúc restore bắt đầu đến khi có response thành công đầu tiên.

Hai con số đều hữu ích và không nên thay thế nhau.

## 7. Các công thức nên dùng

Giả sử có các timestamp đã đồng bộ theo một nguồn đo:

| Metric | Công thức |
|---|---|
| JVM startup | T1 − T0_process |
| Application startup | T2 − T1 |
| CRaC restore duration | T_process_resumed − T_restore_start |
| Post-restore initialization | T3 − T_process_resumed |
| Application time to ready | T4 − T_restore_start |
| Kubernetes time to Ready | T5 − T_pod_created |
| First-request latency | T_response − T_request |
| Time to first successful response | T_first_success − T_restore_start |
| Post-ready first response | T_first_success − T_app_ready |

Công thức chỉ có ý nghĩa khi các mốc được định nghĩa thống nhất. Không nên trừ timestamp từ hai clock khác nhau hoặc hai máy không đồng bộ thời gian mà không tính sai số.

### 7.1. Phân rã thời gian

Một cách hữu ích là chia time to ready thành các phần:

\[
T_{\text{ready}} =
T_{\text{restore}} +
T_{\text{resource-init}} +
T_{\text{cache-warmup}} +
T_{\text{readiness-overhead}}
\]

Đây là mô hình phân rã đơn giản. Trong thực tế, một số bước có thể chạy song song, nên tổng thời gian không nhất thiết bằng tổng duration của tất cả task. Nếu các task chạy song song, cần đo critical path.

Ví dụ, database connect mất 300 ms và Redis connect mất 250 ms. Nếu chạy song song, giai đoạn kết nối có thể mất gần 300 ms cộng overhead, không phải 550 ms.

## 8. Xác định mốc đo trong ứng dụng Java

Đối với khoảng thời gian bên trong một process đang chạy, nên dùng System.nanoTime() để đo duration. nanoTime phù hợp cho đo khoảng thời gian vì không phụ thuộc vào thay đổi giờ hệ thống.

Không nên dùng System.currentTimeMillis() để đo duration ngắn nếu đồng hồ hệ thống có thể được điều chỉnh. Instant hoặc wall-clock timestamp phù hợp để ghi sự kiện có thời điểm lịch và đối chiếu log, nhưng duration benchmark nội bộ nên dùng monotonic clock.

### 8.1. Bộ đo duration đơn giản

~~~java
import java.util.concurrent.TimeUnit;

public final class StartupTimer {

    private final long startedAtNanos = System.nanoTime();

    public long elapsedMillis() {
        return TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - startedAtNanos
        );
    }
}
~~~

Tạo timer ở mốc bắt đầu muốn đo và đọc khi mốc kết thúc xảy ra.

Ví dụ:

~~~java
StartupTimer timer = new StartupTimer();

initializeFramework();
initializeRequiredClients();

long startupMillis = timer.elapsedMillis();
System.out.println("startup_ms=" + startupMillis);
~~~

Đây chỉ là ví dụ trong cùng một lần thực thi. Không dùng giá trị nanoTime được giữ trước checkpoint để tính một duration xuyên qua khoảng thời gian process bị dừng hoặc giữa các lần chạy khác nhau. Với các mốc xuyên qua restore, hãy dùng timestamp từ restore controller hoặc hệ thống đo bên ngoài.

### 8.2. Ghi timestamp và duration riêng

Có thể ghi cả wall-clock timestamp và monotonic duration:

~~~java
import java.time.Instant;

public final class StartupEvent {

    private final Instant occurredAt = Instant.now();
    private final long occurredAtNanos = System.nanoTime();

    public Instant occurredAt() {
        return occurredAt;
    }

    public long elapsedSince(StartupEvent start) {
        return (occurredAtNanos - start.occurredAtNanos) / 1_000_000;
    }
}
~~~

Timestamp giúp đối chiếu log và trace. Duration dùng để so sánh các mốc trong cùng process. Với restore, mốc bắt đầu từ controller bên ngoài cần được truyền hoặc ghi nhận theo một cách có correlation ID và nguồn clock rõ ràng.

## 9. Đo application readiness trong Spring Boot

Spring Boot cung cấp ApplicationReadyEvent để thông báo ứng dụng đã hoàn tất quá trình startup theo lifecycle của framework.

Ví dụ ghi nhận thời gian từ lúc process bắt đầu chạy đến ApplicationReadyEvent:

~~~java
import java.lang.management.ManagementFactory;
import java.time.Instant;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationReadyMetrics {

    private final long processStartedAtNanos = System.nanoTime();

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        long elapsedMillis =
                (System.nanoTime() - processStartedAtNanos) / 1_000_000;

        System.out.println(
            "application_ready"
            + " elapsed_ms=" + elapsedMillis
            + " event_time=" + Instant.now()
        );
    }
}
~~~

Ví dụ này đo từ lúc Spring tạo bean đến khi event được phát. Nó không bao gồm thời gian trước khi bean được tạo và không tự động đại diện cho Kubernetes Pod Ready.

Nếu cần đo từ lúc process được tạo, có thể ghi timestamp sớm hơn trong entry point hoặc dùng metric từ container runtime. Nếu cần đo post-restore readiness, hãy đặt mốc riêng trong CRaC lifecycle.

### 9.1. ApplicationReadyEvent không phải lúc nào cũng là readiness nghiệp vụ

Một số ứng dụng cần làm thêm công việc sau ApplicationReadyEvent:

- Refresh cache.
- Khởi tạo subscription.
- Chờ consumer assignment.
- Kiểm tra quyền truy cập.
- Warm-up endpoint quan trọng.

Trong trường hợp đó, nên duy trì trạng thái readiness riêng và chỉ chuyển sang READY sau khi các điều kiện nghiệp vụ hoàn tất.

## 10. Đo các giai đoạn CRaC bằng Resource

Có thể ghi nhận các mốc callback trước checkpoint và sau restore. Ví dụ dưới đây minh họa một resource quản lý trạng thái thời gian trong một lần restore.

~~~java
import java.time.Instant;
import java.util.concurrent.TimeUnit;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RestoreTimingResource implements Resource {

    private volatile long afterRestoreStartedNanos;
    private volatile Instant afterRestoreStartedAt;

    public RestoreTimingResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {

        System.out.println(
            "before_checkpoint_at=" + Instant.now()
        );
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        afterRestoreStartedNanos = System.nanoTime();
        afterRestoreStartedAt = Instant.now();

        recreateRequiredResources();
        verifyDependencies();

        long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - afterRestoreStartedNanos
        );

        System.out.println(
            "after_restore_initialization_ms=" + elapsedMillis
            + " started_at=" + afterRestoreStartedAt
            + " completed_at=" + Instant.now()
        );
    }

    private void recreateRequiredResources() throws Exception {
        // Recreate database, Redis and other required resources.
    }

    private void verifyDependencies() throws Exception {
        // Verify the dependencies required before readiness.
    }
}
~~~

Trong ví dụ, duration được đo bên trong callback afterRestore. Nó phản ánh phần công việc từ lúc callback bắt đầu đến khi hai bước minh họa hoàn tất. Nó không bao gồm restore duration trước callback hoặc probe delay sau callback.

Trong production, nên phát metric riêng cho từng dependency để xác định bước nào chiếm thời gian. Không nên chỉ log một duration tổng nếu cần tối ưu.

## 11. Đo Kubernetes Pod Ready time

Ở cấp Kubernetes, có thể dùng Pod condition và container status để phân tích thời gian.

Một số mốc hữu ích:

- metadata.creationTimestamp: thời điểm Pod object được tạo.
- PodScheduled condition: thời điểm Pod được scheduler gán node.
- container state running.startedAt: thời điểm container bắt đầu chạy theo container status.
- ContainersReady condition: các container đã sẵn sàng.
- Ready condition: Pod đã sẵn sàng theo readiness và readiness gate.

Có thể xem bằng:

~~~bash
kubectl get pod orders-api-abc123 -o yaml
kubectl describe pod orders-api-abc123
~~~

Để đo tự động, một controller hoặc script có thể đọc các timestamp condition và tính duration. Nên giữ nguyên các mốc thô để có thể phân tích lại khi định nghĩa metric thay đổi.

### 11.1. Pod Ready time gồm nhiều chi phí

Nếu lấy Pod creation timestamp làm T0 và Ready condition làm T1, metric bao gồm:

- Scheduling delay.
- Image pull.
- Volume mount.
- Container startup.
- CRaC restore.
- Application resource initialization.
- Startup/readiness probe.
- Readiness gate.

Đây là metric tốt để đánh giá trải nghiệm rollout ở cấp platform, nhưng không phải phép đo riêng của JVM hoặc CRaC.

### 11.2. Probe interval tạo độ trễ quan sát

Giả sử ứng dụng nội bộ chuyển READY lúc 10:00:00.100, nhưng readiness probe chạy mỗi 5 giây. Kubelet có thể chỉ quan sát trạng thái thành công ở lần probe tiếp theo.

Vì vậy, Pod Ready time có thể muộn hơn application readiness time. Muốn giảm độ trễ quan sát, có thể điều chỉnh periodSeconds, nhưng probe quá thường xuyên cũng tạo thêm request và tải lên ứng dụng.

### 11.3. Readiness gate

Nếu Pod dùng readiness gate, Pod condition Ready chỉ thành True khi các condition bổ sung cũng thỏa mãn. Điều này hữu ích khi restore controller cần cấp restore budget hoặc xác nhận một dependency ở cấp fleet.

Cần ghi riêng thời điểm ứng dụng ready và thời điểm external gate được mở để xác định phần nào tạo độ trễ.

## 12. Đo first-request latency

First-request latency nên được đo từ lúc request thực sự đến ứng dụng đến lúc response hoàn tất.

Không nên lấy thời điểm gửi request ở client và thời điểm response nhận được làm latency ứng dụng nếu mục tiêu là đo riêng xử lý bên trong server. Hai mốc đó còn bao gồm network, load balancer, service mesh và client scheduling.

Nên phân biệt:

| Phạm vi | Bắt đầu | Kết thúc |
|---|---|---|
| Client-observed latency | Client gửi request | Client nhận response |
| Gateway latency | Gateway nhận request | Gateway gửi response |
| Server processing time | Server nhận request | Server hoàn tất xử lý |
| Dependency latency | Gửi lệnh đến dependency | Nhận kết quả |
| First-request latency | Server nhận request đầu tiên | Server hoàn tất response đầu tiên |

Nếu mục tiêu là trải nghiệm người dùng, client-observed latency thường quan trọng nhất. Nếu mục tiêu là phân tích JIT hoặc lazy initialization, server processing time và trace span có thể hữu ích hơn.

### 12.1. Dùng Micrometer Timer

Có thể ghi thời gian xử lý request bằng Micrometer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

import java.io.IOException;

public final class RequestTimingFilter implements Filter {

    private final Timer requestTimer;

    public RequestTimingFilter(MeterRegistry registry) {
        this.requestTimer = Timer.builder("http.server.request.duration")
                .tag("scope", "application")
                .register(registry);
    }

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, jakarta.servlet.ServletException {

        Timer.Sample sample = Timer.start();

        try {
            chain.doFilter(request, response);
        } finally {
            sample.stop(requestTimer);
        }
    }
}
~~~

Đây là ví dụ minh họa cho servlet stack. Framework reactive cần instrumentation phù hợp với vòng đời reactive, không nên dùng filter đồng bộ theo cách trên.

Metric trên đo thời gian xử lý request qua filter. Để xác định request đầu tiên, cần thêm một cơ chế nhận biết first successful request theo từng process hoặc Pod UID.

### 12.2. Định nghĩa response thành công

Cần thống nhất response nào được xem là thành công:

- HTTP 2xx.
- HTTP 2xx hoặc 3xx.
- Một response nghiệp vụ hợp lệ.
- Một response không phải lỗi tạm thời.
- Một response của endpoint kiểm tra chức năng cụ thể.

HTTP 200 từ health endpoint không chứng minh đường nghiệp vụ chính đã hoạt động. Nếu muốn đo khả năng phục vụ thật, hãy dùng một request smoke test đại diện và không gây side effect.

## 13. Đo time to first successful response từ bên ngoài

Một synthetic client hoặc test harness bên ngoài có thể:

1. Ghi lại mốc bắt đầu restore hoặc Pod creation.
2. Theo dõi Pod Ready.
3. Gửi request kiểm tra theo nhịp đã định.
4. Ghi timestamp của request đầu tiên.
5. Ghi timestamp của response thành công đầu tiên.
6. Ghi latency của request đó.
7. Lưu lỗi trước khi có response thành công.

Cách đo bên ngoài có lợi thế là quan sát được trải nghiệm từ góc nhìn client hoặc platform, thay vì chỉ tin vào log nội bộ của process.

Ví dụ dữ liệu:

| Event | Timestamp |
|---|---|
| Restore requested | 10:00:00.000 |
| Process resumed | 10:00:00.180 |
| Application ready | 10:00:00.700 |
| Pod Ready | 10:00:01.100 |
| First request sent | 10:00:01.300 |
| First response received | 10:00:01.420 |

Từ dữ liệu này có thể tính riêng restore duration, readiness delay, first-request latency và time to first response.

### 13.1. Không gửi request dồn dập trong lúc chờ

Synthetic probe không nên poll liên tục với tần suất quá cao. Nếu 100 Pod cùng restore và mỗi probe gửi request mỗi 100 ms, chính phép đo có thể tạo tải lên hệ thống.

Có thể dùng polling interval hợp lý, jitter giữa client và readiness signal của Kubernetes. Ghi rõ tần suất probe trong benchmark.

### 13.2. Ghi cả lỗi trước response đầu tiên

Nếu request đầu tiên trả 503 và request thứ hai trả 200, cần lưu cả hai:

- First attempt latency.
- First successful response latency.
- Số lần thất bại trước thành công.
- Thời gian từ lần thử đầu tiên đến thành công.

Nếu chỉ ghi response 200 đầu tiên, có thể bỏ qua khoảng thời gian hệ thống chưa phục vụ được request.

## 14. So sánh cold start và CRaC restore

Để đánh giá CRaC, cần so sánh hai quy trình với cùng ứng dụng và điều kiện môi trường.

### 14.1. Cold start

Cold start thường gồm:

- Tạo container/process.
- Khởi động JVM.
- Khởi tạo framework.
- Tạo resource.
- Warm-up nếu ứng dụng thực hiện lúc startup.
- Chuyển READY.
- Xử lý request đầu tiên.

### 14.2. CRaC restore

Restore path thường gồm:

- Khởi tạo môi trường restore.
- Khôi phục process từ checkpoint.
- Chạy afterRestore callback.
- Tạo lại hoặc xác thực resource.
- Refresh cache cần thiết.
- Chuyển READY.
- Xử lý request đầu tiên.

~~~mermaid
flowchart LR
    subgraph Cold["Cold start"]
        A["Process start"] --> B["JVM startup"]
        B --> C["Framework initialization"]
        C --> D["Resource initialization"]
        D --> E["Ready"]
        E --> F["First request"]
    end
    subgraph Restore["CRaC restore"]
        G["Restore requested"] --> H["Process restored"]
        H --> I["afterRestore"]
        I --> J["Resource recreation"]
        J --> K["Ready"]
        K --> L["First request"]
    end
~~~

Không nên kết luận CRaC tốt hơn chỉ vì process restore nhanh hơn. Cần so sánh time to readiness và time to first successful response vì đó là những mốc gần với khả năng phục vụ.

### 14.3. So sánh cùng điều kiện

Giữ các yếu tố sau nhất quán:

- Cùng application version.
- Cùng JDK distribution và build.
- Cùng JVM flags.
- Cùng CPU và memory limit.
- Cùng node pool hoặc loại máy.
- Cùng dependency endpoint.
- Cùng cấu hình cache và dữ liệu.
- Cùng warm-up workload.
- Cùng readiness probe.
- Cùng request đầu tiên và payload.

Nếu restore dùng cache đã nóng còn cold start dùng cache rỗng, kết quả sẽ trộn lẫn lợi ích của checkpoint với lợi ích của cache. Cần quyết định trạng thái cache nào là một phần của chiến lược và ghi rõ trong benchmark.

## 15. Percentile và phân bố thời gian

Không nên chỉ báo cáo average startup time. Một số lần restore có thể chậm vì scheduling, node contention, DNS, dependency failover hoặc image pull.

Nên báo cáo:

- Minimum và maximum để hiểu phạm vi.
- Median hoặc p50 để mô tả lần chạy điển hình.
- p90/p95 để đánh giá phần lớn lần chạy.
- p99 khi số mẫu đủ lớn và tail latency quan trọng.
- Error rate hoặc số lần không đạt readiness.

Ví dụ minh họa:

| Metric | Cold start p50 | CRaC restore p50 | Cold start p95 | CRaC restore p95 |
|---|---:|---:|---:|---:|
| Process start to app ready | 4.2 s | 0.8 s | 6.1 s | 1.4 s |
| Pod creation to Pod Ready | 7.5 s | 2.1 s | 11.0 s | 4.0 s |
| First-request latency | 310 ms | 140 ms | 650 ms | 290 ms |
| Time to first successful response | 7.9 s | 2.3 s | 11.6 s | 4.3 s |

Các con số chỉ minh họa cách trình bày, không phải benchmark của CRaC hay mục tiêu mặc định.

### 15.1. Số mẫu và tính ổn định

Một vài lần chạy không đủ để kết luận p95 hoặc p99. Cần đủ mẫu, kiểm soát outlier và ghi nhận điều kiện môi trường.

Nếu thử nghiệm chỉ có 10 lần restore, p99 gần như không có ý nghĩa thống kê. Hãy báo số lượng mẫu cùng percentile.

### 15.2. Phân nhóm kết quả

Nên tách kết quả theo:

- Node hoặc node pool.
- JDK version.
- Cold start hay restore.
- Checkpoint version.
- Dependency khỏe hay có sự cố.
- Cache warm hay cold.
- Pod mới hay Pod restart.
- Single Pod hay fleet restore.

Nếu gộp mọi trường hợp, một nhóm restore chậm có thể bị che khuất bởi nhóm chạy nhanh.

## 16. Các yếu tố làm sai lệch phép đo

### 16.1. Probe interval và readiness delay

Nếu readiness probe chạy mỗi 10 giây, Pod Ready time có thể bị lượng tử hóa theo chu kỳ probe. Thời gian ứng dụng thực sự sẵn sàng có thể ngắn hơn nhiều.

### 16.2. Image pull và node cache

Một lần chạy trên node đã cache image có thể nhanh hơn lần chạy phải pull image. Nếu mục tiêu là đánh giá CRaC, cần đo image pull riêng hoặc dùng cùng điều kiện.

### 16.3. Dependency cache và connection reuse

Database, Redis và DNS có thể có cache riêng. Lần chạy sau có thể nhanh hơn vì connection hoặc cache ở dependency đã nóng, không phải vì checkpoint.

### 16.4. JIT và request payload

Request đầu tiên có thể kích hoạt JIT compilation hoặc lazy initialization. Payload khác nhau có thể đi qua code path khác nhau. Cần dùng cùng payload và endpoint.

### 16.5. Background activity

Scheduler, telemetry exporter, cache refresh hoặc consumer startup có thể cạnh tranh CPU và connection với request đầu tiên.

Nên ghi nhận background task nào đang hoạt động và có ảnh hưởng đến benchmark hay không.

### 16.6. Đồng hồ giữa nhiều máy

Nếu T0 được ghi trên restore controller và T7 được ghi trên client khác, clock skew có thể làm duration sai. Hãy dùng hệ thống timestamp đồng bộ và ước lượng sai số, hoặc đo cả hai mốc ở cùng một observer.

## 17. Dùng monotonic clock và wall clock đúng cách

Có hai loại thời gian thường gặp:

**Wall clock** biểu diễn thời điểm lịch, ví dụ Instant.now(). Nó phù hợp để ghi log, timestamp event và đối chiếu giữa hệ thống nếu clock được đồng bộ.

**Monotonic clock** như System.nanoTime() phù hợp đo duration trong cùng tiến trình hoặc cùng môi trường clock. Nó không bị ảnh hưởng bởi việc chỉnh giờ hệ thống theo cách wall clock có thể bị ảnh hưởng.

Không nên:

- Lấy hai giá trị nanoTime từ hai process rồi trừ cho nhau.
- So sánh nanoTime của hai host.
- Giữ một giá trị nanoTime trước checkpoint rồi mặc định nó là mốc đáng tin cậy để tính duration xuyên qua restore.
- Trộn timestamp từ client và server mà không xác định clock source.

Đối với time to first response xuyên qua restore, cách chắc chắn hơn là dùng một observer bên ngoài có clock ổn định để ghi mốc bắt đầu và kết thúc. Trong process, dùng nanoTime để đo các đoạn nội bộ sau khi process đã tiếp tục chạy.

## 18. Instrumentation và metric naming

Metric nên có tên rõ ràng và đơn vị nhất quán. Ví dụ:

| Metric | Loại | Đơn vị |
|---|---|---|
| jvm_startup_duration | Histogram/Timer | seconds |
| application_startup_duration | Histogram/Timer | seconds |
| crac_restore_duration | Histogram/Timer | seconds |
| crac_after_restore_duration | Histogram/Timer | seconds |
| application_time_to_ready | Histogram/Timer | seconds |
| pod_creation_to_ready_duration | Histogram | seconds |
| first_request_duration | Histogram/Timer | seconds |
| time_to_first_successful_response | Histogram | seconds |
| startup_failure_total | Counter | count |
| restore_failure_total | Counter | count |
| readiness_transition_total | Counter | count |

Không đưa Pod UID, request ID hoặc checkpoint ID vào label của metric có cardinality cao. Các ID này phù hợp hơn với log hoặc trace. Metric nên dùng label có số lượng giá trị giới hạn như application, version, startup_mode hoặc node_pool.

### 18.1. Phân biệt counter, gauge và histogram

- Counter đếm số lần startup/restore thất bại.
- Gauge biểu diễn trạng thái hiện tại như readiness hoặc số dependency đang kết nối.
- Histogram/Timer ghi phân bố duration.

Không dùng một gauge đơn lẻ để biểu diễn startup duration của mọi lần chạy vì giá trị sẽ bị ghi đè và khó phân tích percentile.

### 18.2. Correlation ID

Mỗi lần restore nên có một restore attempt ID. Gắn ID này vào log của:

- Restore start.
- Process resumed.
- Resource initialization.
- Cache warm-up.
- Application ready.
- Pod ready.
- First request.
- First successful response.

Nhờ đó có thể dựng lại timeline cho một Pod mà không cần đưa ID vào mọi metric label.

## 19. Thiết kế endpoint health và readiness

Một ứng dụng có thể cung cấp ba endpoint riêng:

| Endpoint | Mục tiêu | Điều kiện |
|---|---|---|
| /health/startup | Khởi tạo cơ bản đã hoàn tất | Process và framework có thể tiến triển |
| /health/ready | Có thể nhận traffic | Dependency bắt buộc và admission gate sẵn sàng |
| /health/live | Process còn sống | Không deadlock hoặc hỏng nội bộ nghiêm trọng |

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 4
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: app
          image: registry.example.com/catalog-api:2026.11
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 3
            timeoutSeconds: 2
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Probe path là ví dụ và cần được triển khai trong ứng dụng. Startup probe cho phép quá trình khởi động kéo dài mà không bị liveness probe restart quá sớm. Readiness probe ngăn Pod nhận traffic khi chưa sẵn sàng. Liveness probe nên phản ánh sức khỏe nội bộ của process, không nên fail chỉ vì database hoặc Redis tạm thời chậm.

## 20. Ví dụ phân tích timeline sau restore

Giả sử một Pod có các event:

| Event | Thời gian kể từ restore start |
|---|---:|
| Restore requested | 0 ms |
| Process resumed | 160 ms |
| afterRestore started | 170 ms |
| Database ready | 410 ms |
| Redis ready | 520 ms |
| Cache warm-up complete | 680 ms |
| Application readiness true | 710 ms |
| Kubernetes Pod Ready | 3.100 ms |
| First request received | 3.350 ms |
| First response completed | 3.470 ms |

Từ timeline này có thể rút ra:

- Restore process nhanh.
- Resource initialization và cache warm-up chiếm phần lớn thời gian nội bộ sau restore.
- Khoảng cách giữa application ready và Pod Ready chủ yếu nằm ở probe/control-plane observation.
- First-request latency là 120 ms.
- Time to first successful response là 3.470 ms.

Nếu mục tiêu là giảm thời gian từ restore đến traffic, có thể tối ưu readiness probe interval hoặc readiness gate. Nếu mục tiêu là giảm first-request latency, cần phân tích request trace và lazy initialization.

Không nên tối ưu restore process khi bottleneck thực tế nằm ở cache warm-up hoặc probe interval.

## 21. Cách xác định bottleneck theo từng metric

| Quan sát | Khả năng cần điều tra |
|---|---|
| JVM startup cao | JVM flags, classpath, class loading, runtime initialization |
| Application startup cao | Framework bean creation, configuration, startup hooks |
| Restore duration cao | Checkpoint size, storage I/O, CRIU và host compatibility |
| afterRestore duration cao | Connection recreation, DNS, TLS, cache refresh |
| Application ready nhanh nhưng Pod Ready chậm | Probe interval, readiness gate, kubelet/control plane |
| Pod Ready nhanh nhưng first request chậm | JIT, lazy init, cache miss, connection on demand |
| First request latency thấp nhưng time to first response cao | Chờ readiness, load balancer routing hoặc request schedule |
| p95 cao nhưng p50 thấp | Node contention, dependency tail latency, retry hoặc scheduling |
| Restore lỗi không ổn định | Resource không được phục hồi, dependency timeout, environment mismatch |

Cách phân tích theo giai đoạn giúp chọn đúng nơi cần tối ưu. Một chỉ số tổng không đủ để giải thích nguyên nhân.

## 22. Benchmark CRaC theo quy trình lặp lại

Một benchmark có thể thực hiện như sau:

### Bước 1: Xác định mục tiêu

Ví dụ:

- Giảm Pod creation-to-ready p95.
- Giảm restore-to-first-successful-response p95.
- Giảm first-request latency p95.
- Giữ checkpoint size trong giới hạn.

Không nên chọn một mục tiêu chung như “startup nhanh hơn” mà không có ngưỡng đo.

### Bước 2: Chuẩn hóa môi trường

Giữ cố định:

- Image digest.
- JDK build.
- JVM flags.
- CPU/memory limit.
- Node pool.
- Dependency.
- Probe configuration.
- Workload và payload.
- Cache state.

### Bước 3: Chạy cold-start baseline

Chạy đủ số lần, thu thập startup, readiness và first-response metric. Ghi lại lỗi và điều kiện môi trường.

### Bước 4: Tạo checkpoint

Khởi động ứng dụng, warm-up theo workload đã xác định, chuẩn bị resource và tạo checkpoint. Ghi checkpoint creation duration và image size riêng.

### Bước 5: Restore nhiều lần

Restore cùng checkpoint trong điều kiện tương đương. Ghi restore duration, afterRestore duration, application ready, Pod Ready và first response.

### Bước 6: So sánh percentile

So sánh p50, p95 và p99 nếu có đủ mẫu. Báo cáo số lần chạy và các lần thất bại.

### Bước 7: Kiểm tra tail case

Thử khi dependency chậm, cache stale, node contention hoặc nhiều Pod restore đồng thời. Một checkpoint tốt không chỉ nhanh trong môi trường hoàn hảo mà còn cần có hành vi phục hồi rõ ràng khi dependency chậm.

## 23. Bảng kết quả benchmark mẫu

Bảng dưới đây minh họa cách tổ chức báo cáo:

| Metric | Cold start | CRaC restore | Chênh lệch |
|---|---:|---:|---:|
| Application startup p50 | 4.2 s | 0.8 s | -81.0% |
| Application time to ready p50 | 5.1 s | 1.2 s | -76.5% |
| Pod creation to Ready p50 | 7.5 s | 2.1 s | -72.0% |
| First-request latency p50 | 310 ms | 140 ms | -54.8% |
| Time to first response p50 | 7.9 s | 2.3 s | -70.9% |
| First-request latency p95 | 650 ms | 290 ms | -55.4% |

Các số liệu trên chỉ là ví dụ minh họa. Không dùng làm cam kết hoặc kỳ vọng hiệu năng cho mọi ứng dụng. Kết quả thực tế phụ thuộc workload, JDK, checkpoint, dependency, host và cách định nghĩa metric.

### 23.1. Tính phần trăm cải thiện

Có thể tính:

\[
\text{Improvement} =
\frac{T_{\text{baseline}} - T_{\text{new}}}
{T_{\text{baseline}}} \times 100\%
\]

Ví dụ baseline 5 giây và restore 1 giây:

\[
\frac{5 - 1}{5} \times 100\% = 80\%
\]

Luôn ghi cả giá trị tuyệt đối và phần trăm. Giảm từ 100 ms xuống 50 ms và từ 10 giây xuống 5 giây đều là 50%, nhưng tác động sản phẩm khác nhau.

## 24. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| Gọi mọi metric là startup time | Không rõ phạm vi đo | Đặt tên theo start/end event |
| Dùng restore duration làm time to ready | Bỏ qua callback và readiness | Đo riêng các giai đoạn |
| Dùng first-request latency làm time to first response | Bỏ qua thời gian chờ trước request | Ghi cả request và response timestamp |
| Chỉ đo trong JVM | Không thấy scheduling, image pull và probe | Bổ sung observer ở Kubernetes/client |
| Chỉ đo từ Pod creation | Trộn chi phí platform với JVM | Giữ các mốc container/process/restore |
| Chỉ báo average | Che khuất tail latency | Báo p50/p95/p99 và số mẫu |
| Dùng wall clock để đo duration nội bộ | Clock có thể bị điều chỉnh | Dùng monotonic clock |
| Trừ nanoTime giữa hai process | Không cùng clock domain | Dùng external observer hoặc timestamp đồng bộ |
| Bỏ qua request thất bại đầu tiên | Đánh giá quá lạc quan | Ghi attempt và first successful response |
| So sánh cache warm với cache cold | Trộn nhiều biến số | Chuẩn hóa hoặc phân nhóm cache state |
| Chỉ benchmark một Pod | Không thấy dependency storm | Thử cả fleet restore |
| Để health check quá nặng | Phép đo tạo tải phụ | Dùng readiness state và probe nhẹ |

## 25. Checklist định nghĩa và đo lường

### Định nghĩa metric

- [ ] Có mốc bắt đầu rõ ràng cho từng metric.
- [ ] Có mốc kết thúc rõ ràng cho từng metric.
- [ ] Phân biệt JVM startup, application startup và Pod startup.
- [ ] Phân biệt CRaC restore duration với time to readiness.
- [ ] Phân biệt application Ready với Kubernetes Pod Ready.
- [ ] Phân biệt first-request latency với time to first successful response.

### Instrumentation

- [ ] Dùng System.nanoTime() cho duration trong cùng process.
- [ ] Dùng wall-clock timestamp để ghi sự kiện và đối chiếu log.
- [ ] Không tính duration xuyên restore bằng nanoTime cũ.
- [ ] Có restore attempt ID hoặc correlation ID.
- [ ] Có metric riêng cho resource initialization và cache warm-up.
- [ ] Có observer bên ngoài để đo Pod Ready và first response.

### Benchmark

- [ ] Cold start và CRaC restore dùng cùng điều kiện.
- [ ] Đã ghi image digest và JDK build.
- [ ] Đã chuẩn hóa CPU, memory, dependency và payload.
- [ ] Có đủ số mẫu cho percentile được báo cáo.
- [ ] Ghi cả lỗi và response thất bại trước thành công.
- [ ] Đã thử single-Pod và multi-Pod restore.
- [ ] Đã ghi checkpoint creation duration và image size riêng.

### Diễn giải

- [ ] Báo cáo p50/p95/p99 khi đủ dữ liệu.
- [ ] Phân tích bottleneck theo từng giai đoạn.
- [ ] Không kết luận chỉ từ một con số startup tổng.
- [ ] Nêu rõ metric đo ở cấp process, Pod hay client.
- [ ] Ghi điều kiện môi trường và sai số clock.

## 26. Câu hỏi thường gặp

### Startup time và time to readiness khác nhau thế nào?

Startup time đo thời gian hoàn tất một giai đoạn khởi tạo đã định nghĩa, thường là JVM hoặc application startup. Time to readiness đo từ mốc bắt đầu đến lúc ứng dụng hoặc Pod có thể nhận traffic. Readiness có thể cần thêm kết nối dependency, cache warm-up và probe.

### Restore duration có phải thời gian ứng dụng sẵn sàng không?

Không. Restore duration thường chỉ đo phần khôi phục process. Ứng dụng có thể còn phải chạy afterRestore callback, tạo lại resource, refresh cache và chờ readiness probe.

### ApplicationReadyEvent có đồng nghĩa với Kubernetes Pod Ready không?

Không. ApplicationReadyEvent là sự kiện của Spring Boot. Kubernetes Pod Ready còn phụ thuộc readiness probe, container readiness và readiness gate. Ứng dụng cũng có thể có điều kiện nghiệp vụ bổ sung sau event.

### First-request latency có phải time to first response không?

Không. First-request latency đo từ lúc request đầu tiên đến lúc response hoàn tất. Time to first successful response đo từ mốc startup/restore đến response thành công đầu tiên, nên bao gồm cả thời gian khởi động và chờ request.

### Nên dùng System.nanoTime() hay Instant.now()?

Dùng nanoTime để đo duration trong cùng process. Dùng Instant hoặc wall-clock timestamp để ghi thời điểm sự kiện và đối chiếu log. Với khoảng thời gian xuyên qua checkpoint hoặc giữa nhiều máy, dùng observer bên ngoài và clock đã đồng bộ thay vì trừ nanoTime từ hai môi trường.

### Có nên gửi request ngay sau khi restore để đo first response?

Có thể, nếu request được thiết kế an toàn và phép đo xác định rõ mốc. Nên gửi qua đúng đường routing dự kiến, không tạo side effect và ghi cả lỗi trước response thành công đầu tiên.

### Vì sao Pod Ready nhanh nhưng request đầu tiên vẫn chậm?

Có thể còn JIT compilation, lazy initialization, cache miss, kết nối dependency on-demand hoặc code path chưa được warm-up. Hãy đo first-request latency và trace để xác định phần chi phí.

### Vì sao application Ready nhanh nhưng Pod Ready chậm?

Readiness probe có thể chưa chạy đến lần tiếp theo, readiness gate chưa được mở hoặc kubelet/control plane chưa cập nhật Pod condition. Hãy so sánh application readiness timestamp với Pod Ready condition timestamp.

### Nên tối ưu chỉ số nào trước?

Chọn theo mục tiêu sản phẩm. Nếu rollout chậm, ưu tiên Pod creation-to-ready. Nếu ứng dụng nội bộ restore lâu, phân tích restore và afterRestore duration. Nếu người dùng gặp request đầu tiên chậm, tối ưu first-request latency. Nếu cần biết toàn bộ trải nghiệm từ lúc khởi tạo đến khi có response, đo time to first successful response.

### Có thể so sánh trực tiếp cold start và restore không?

Có, nếu định nghĩa start/end event tương đương và chuẩn hóa môi trường. Cần báo cáo riêng phần platform, restore, readiness và request latency để tránh so sánh hai phạm vi khác nhau.

## Kết luận

Thời gian khởi động, thời gian sẵn sàng và thời gian đáp ứng đầu tiên mô tả ba phần khác nhau của trải nghiệm khởi tạo ứng dụng. Startup time đo một giai đoạn khởi tạo; time to readiness đo thời điểm ứng dụng hoặc Pod có thể nhận traffic; first-request latency đo thời gian xử lý request đầu tiên; time to first successful response đo từ lúc bắt đầu đến response thành công đầu tiên.

Với CRaC, cần tách restore duration khỏi afterRestore initialization và Kubernetes readiness. Hãy ghi rõ mốc bắt đầu/kết thúc, dùng monotonic clock cho duration trong cùng process, dùng observer bên ngoài cho các mốc xuyên restore, và báo cáo percentile cùng điều kiện benchmark. Khi có timeline đầy đủ, nhóm phát triển sẽ biết phần chậm nằm ở JVM, framework, resource, cache, probe hay request đầu tiên và có thể tối ưu đúng giai đoạn.
