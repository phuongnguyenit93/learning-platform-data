# Quản lý vòng đời bộ lập lịch do ứng dụng tạo

Trong chương **Luồng thực thi**, bài học này tập trung vào việc tạo, tái sử dụng và giải phóng scheduler do ứng dụng sở hữu. Khi cần tách tác vụ blocking khỏi event-loop hoặc dành một nhóm thread riêng cho công việc của một thành phần, ứng dụng có thể tạo scheduler riêng bằng Reactor. Scheduler đó là tài nguyên có vòng đời: phải được giữ lại trong thời gian sử dụng và được dispose khi thành phần sở hữu kết thúc.

Bài học thuộc module **REACTIVE_PROGRAMMING**. Module hướng dẫn: “Học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Thực hành Mono, Flux, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java.” Việc quản lý vòng đời scheduler giúp pipeline thực thi đúng nơi, giới hạn tài nguyên thread và đóng ứng dụng một cách có kiểm soát.

## 1. Scheduler là tài nguyên thực thi có vòng đời

Trong Reactor, `Scheduler` cung cấp môi trường để lên lịch tác vụ. Nó có thể quản lý một hoặc nhiều thread, hàng đợi tác vụ và các tác vụ được hẹn giờ. Những toán tử như `subscribeOn`, `publishOn`, `delayElements` hoặc `subscribe` với scheduler có thể sử dụng scheduler để điều phối công việc.

Có hai nhóm scheduler cần phân biệt:

- **Scheduler dùng chung do Reactor quản lý:** lấy từ các factory như `Schedulers.parallel()`, `Schedulers.boundedElastic()` và `Schedulers.single()`. Đây là tài nguyên chia sẻ toàn ứng dụng theo chính sách của Reactor; thông thường thành phần sử dụng không tự dispose chúng.
- **Scheduler do ứng dụng tạo:** lấy từ các factory như `Schedulers.newParallel(...)`, `Schedulers.newSingle(...)` hoặc `Schedulers.newBoundedElastic(...)`. Thành phần tạo scheduler chịu trách nhiệm quản lý và dispose nó.

```java
Scheduler shared = Schedulers.parallel();

Scheduler dedicated =
    Schedulers.newParallel("report-cpu", 4);
```

`shared` là scheduler chia sẻ do Reactor quản lý. `dedicated` là scheduler riêng được tạo cho ứng dụng; ứng dụng phải lưu tham chiếu và giải phóng nó khi không còn cần.

Không nên tạo scheduler mới cho từng request. Việc đó có thể tạo ra quá nhiều thread, hàng đợi và tài nguyên hệ điều hành. Hãy tạo scheduler ở cấp thành phần hoặc ứng dụng, tái sử dụng trong nhiều pipeline, rồi dispose theo vòng đời của thành phần đó.

## 2. Chọn factory phù hợp với loại công việc

Reactor cung cấp các factory tạo scheduler riêng với mục đích khác nhau:

| Factory | Đặc điểm | Trường hợp sử dụng |
|---|---|---|
| `Schedulers.newSingle(name)` | Một thread riêng, xử lý tuần tự | Thành phần cần một luồng xử lý tuần tự |
| `Schedulers.newParallel(name, parallelism)` | Nhóm thread cố định theo mức song song | Tác vụ CPU-bound |
| `Schedulers.newBoundedElastic(threadCap, queuedTaskCap, name)` | Thread linh hoạt có giới hạn và hàng đợi có giới hạn | Tích hợp với API blocking |
| `Schedulers.fromExecutorService(executorService)` | Tạo scheduler từ ExecutorService do ứng dụng cung cấp | Tái sử dụng executor hiện có |

Ví dụ tạo scheduler cho tác vụ CPU:

```java
Scheduler reportScheduler =
    Schedulers.newParallel("report-cpu", 4);
```

Ví dụ tạo scheduler cho lời gọi blocking:

```java
Scheduler legacyIoScheduler =
    Schedulers.newBoundedElastic(
        8,
        100,
        "legacy-io"
    );
```

Các tham số của `newBoundedElastic` giới hạn số thread và số tác vụ có thể chờ theo cấu hình. Giới hạn giúp hệ thống không tạo thread vô hạn khi nhiều tác vụ blocking cùng đến. Khi hàng đợi hoặc giới hạn thread bị chạm, ứng dụng cần xử lý việc tác vụ không thể được tiếp nhận theo chính sách phù hợp.

Đối với `newParallel`, chọn mức song song theo khả năng CPU và đặc tính công việc. Không tăng số thread tùy tiện với tác vụ CPU-bound vì quá nhiều thread có thể làm tăng chi phí chuyển ngữ cảnh mà không tăng thông lượng.

## 3. Lưu scheduler ở đúng phạm vi sở hữu

Một thành phần sử dụng scheduler riêng nên tạo nó một lần, giữ tham chiếu trong field và dùng lại cho nhiều pipeline.

```java
public final class ReportService implements AutoCloseable {

    private final Scheduler scheduler =
        Schedulers.newParallel("report-cpu", 4);

    public Mono<Report> generate(String reportId) {
        return Mono.fromCallable(() -> buildReport(reportId))
            .subscribeOn(scheduler);
    }

    private Report buildReport(String reportId) {
        // Tính toán báo cáo
        return new Report(reportId);
    }

    @Override
    public void close() {
        scheduler.dispose();
    }
}
```

Trong ví dụ này, `ReportService` sở hữu scheduler. Mọi lần gọi `generate` đều dùng cùng scheduler. Khi ứng dụng đóng thành phần, phương thức `close()` dispose scheduler.

Cách tổ chức này có một số lợi ích:

- Số scheduler và thread được kiểm soát theo số thành phần sở hữu.
- Các pipeline không phải tạo rồi bỏ scheduler sau mỗi lần chạy.
- Vòng đời scheduler gắn với vòng đời của thành phần tạo ra nó.
- Có một vị trí rõ ràng để giải phóng tài nguyên khi ứng dụng dừng.

Nếu dùng dependency injection, hãy để container quản lý vòng đời bean và gọi phương thức đóng tương ứng. Ví dụ với Spring, có thể dùng `@PreDestroy` trên phương thức dispose scheduler:

```java
@Component
public final class LegacyGateway {

    private final Scheduler ioScheduler =
        Schedulers.newBoundedElastic(
            8, 100, "legacy-gateway"
        );

    public Mono<Result> fetch(String key) {
        return Mono.fromCallable(() -> blockingClient.fetch(key))
            .subscribeOn(ioScheduler);
    }

    @PreDestroy
    void shutdown() {
        ioScheduler.dispose();
    }
}
```

Đảm bảo phương thức vòng đời được container gọi khi bean bị đóng. Không tạo scheduler trong phương thức `fetch`, vì mỗi request sẽ tạo thêm một scheduler mà không có cơ chế sở hữu và giải phóng rõ ràng.

## 4. Dùng scheduler riêng trong pipeline

Scheduler có thể được sử dụng qua `subscribeOn` hoặc `publishOn`, tùy vị trí muốn điều phối thực thi.

`subscribeOn(scheduler)` ảnh hưởng đến quá trình subscription và cách nguồn bắt đầu thực thi. Nó thường được dùng để đưa một nguồn blocking như `fromCallable` sang scheduler phù hợp.

```java
Mono<Customer> customer =
    Mono.fromCallable(() -> blockingRepository.findById(id))
        .subscribeOn(legacyIoScheduler);
```

`publishOn(scheduler)` tạo ranh giới để các tín hiệu downstream tiếp tục được xử lý trên scheduler được chỉ định:

```java
Mono<ReportView> view =
    reportRepository.findById(id)
        .publishOn(reportScheduler)
        .map(ReportView::from)
        .map(this::enrichView);
```

Cả hai toán tử đều có thể dùng cùng một scheduler riêng đã được thành phần sở hữu. Không cần tạo scheduler mới cho từng pipeline.

Hãy chú ý vị trí của ranh giới. Đặt `publishOn` sau nguồn không làm cho thao tác nguồn đã xảy ra trước đó chuyển sang scheduler mới. Nếu cần chuyển thao tác blocking ở nguồn, hãy đặt `subscribeOn` phù hợp với nguồn, thường là ngay sau publisher được tạo từ `fromCallable`.

## 5. Dispose scheduler khi thành phần kết thúc

`Scheduler` triển khai hợp đồng `Disposable`. Với scheduler do ứng dụng tạo, gọi `dispose()` khi thành phần sở hữu không còn nhận công việc mới và các pipeline không cần dùng scheduler nữa.

```java
Scheduler scheduler =
    Schedulers.newSingle("notification-worker");

try {
    Mono<Void> task =
        notificationService.sendPending()
            .subscribeOn(scheduler);

    task.block();
} finally {
    scheduler.dispose();
}
```

Ví dụ trên minh họa việc giải phóng scheduler sau khi công việc hoàn tất. Trong ứng dụng server, thường không nên dùng `block()` như cách điều phối request; hãy để vòng đời ứng dụng hoặc container quản lý thời điểm dừng thành phần. Khối `try/finally` phù hợp hơn với một tác vụ độc lập có thời điểm bắt đầu và kết thúc rõ ràng.

Khi gọi `dispose()`, scheduler ngừng nhận hoặc thực thi các tác vụ theo chính sách dispose của implementation. Các tác vụ đang chờ có thể bị hủy hoặc từ chối; không nên giả định rằng mọi công việc đang xếp hàng đều sẽ hoàn tất. Vì vậy, hãy dừng tiếp nhận công việc mới và chờ các pipeline cần thiết hoàn thành trước khi dispose nếu nghiệp vụ yêu cầu hoàn tất có kiểm soát.

Nếu phiên bản Reactor đang dùng cung cấp `disposeGracefully()`, có thể dùng publisher mà phương thức này trả về để chờ quá trình giải phóng theo cơ chế graceful của scheduler:

```java
scheduler.disposeGracefully()
    .block();
```

Đoạn này chỉ phù hợp ở ranh giới shutdown đồng bộ của ứng dụng hoặc thành phần sở hữu, nơi việc chờ kết thúc là có chủ đích. Không gọi `block()` trong event-loop hoặc bên trong một pipeline reactive đang xử lý request.

## 6. Quản lý Scheduler.Worker riêng

Ngoài scheduler, Reactor còn có khái niệm `Scheduler.Worker`. Worker là một đơn vị thực thi được tạo từ scheduler, thường dùng để lên lịch một chuỗi tác vụ tuần tự trên cùng worker.

```java
Scheduler scheduler =
    Schedulers.newParallel("batch-worker", 2);

Scheduler.Worker worker = scheduler.createWorker();

worker.schedule(() -> process("batch-1"));
worker.schedule(() -> process("batch-2"));

// Khi worker không còn cần dùng:
worker.dispose();

// Khi thành phần sở hữu scheduler kết thúc:
scheduler.dispose();
```

Worker và scheduler có vòng đời riêng. Nếu ứng dụng tự gọi `createWorker()`, ứng dụng cần dispose worker khi không còn dùng, đồng thời dispose scheduler khi thành phần sở hữu kết thúc. Chỉ dispose worker không giải phóng toàn bộ scheduler; chỉ dispose scheduler cũng không thay thế việc quản lý rõ ràng các worker mà ứng dụng đã tạo.

Không tạo worker mới cho mỗi phần tử của một luồng nếu không có lý do cụ thể. Hãy cân nhắc tái sử dụng worker hoặc dùng các toán tử Reactor có sẵn để quản lý việc điều phối.

## 7. Scheduler bọc ExecutorService

Nếu ứng dụng đã có `ExecutorService`, có thể tạo scheduler từ executor đó:

```java
ExecutorService executor =
    Executors.newFixedThreadPool(4);

Scheduler scheduler =
    Schedulers.fromExecutorService(executor);
```

Cách này hữu ích khi hệ thống có sẵn cấu hình executor và muốn dùng nó trong pipeline Reactor. Cần xác định rõ ai sở hữu executor và ai chịu trách nhiệm shutdown. Khi scheduler được tạo từ một `ExecutorService` do ứng dụng quản lý, việc dispose scheduler có thể tác động đến executor được bọc. Hãy tuân theo hợp đồng của phiên bản Reactor đang dùng và tránh shutdown cùng một executor từ nhiều nơi theo cách không phối hợp.

Nếu muốn quản lý executor trực tiếp, hãy giữ cả hai tham chiếu và đóng theo thứ tự được thiết kế:

```java
ExecutorService executor =
    Executors.newFixedThreadPool(4);

Scheduler scheduler =
    Schedulers.fromExecutorService(executor);

// Dừng nhận công việc, hoàn tất phần việc cần giữ lại,
// sau đó giải phóng scheduler/executor theo ownership đã chọn.
scheduler.dispose();
```

Không bọc một executor dùng chung của thành phần khác rồi tùy tiện dispose scheduler, vì điều đó có thể làm gián đoạn công việc của thành phần không sở hữu scheduler wrapper.

## 8. Không dispose scheduler dùng chung của Reactor

Các factory như `Schedulers.parallel()`, `Schedulers.boundedElastic()` và `Schedulers.single()` trả về scheduler dùng chung do Reactor quản lý. Nhiều pipeline trong ứng dụng có thể cùng sử dụng các tài nguyên này.

```java
Mono<Result> result =
    Mono.fromCallable(this::blockingOperation)
        .subscribeOn(Schedulers.boundedElastic());
```

Không gọi `Schedulers.boundedElastic().dispose()` sau mỗi request. Việc dispose scheduler dùng chung có thể ảnh hưởng đến các pipeline khác trong cùng ứng dụng. Hãy để Reactor quản lý scheduler dùng chung và chỉ giải phóng scheduler được tạo riêng bởi thành phần sở hữu.

Tương tự, không dùng `Schedulers.shutdownNow()` như cách dừng một scheduler riêng lẻ. Đây là thao tác ở phạm vi các tài nguyên scheduler toàn cục do Reactor quản lý, phù hợp với tình huống shutdown toàn ứng dụng được điều phối tập trung, không phải thao tác cleanup của một service.

| Tài nguyên | Ai quản lý vòng đời? | Hành động của thành phần sử dụng |
|---|---|---|
| `Schedulers.parallel()` | Reactor | Dùng và không tự dispose |
| `Schedulers.boundedElastic()` | Reactor | Dùng và không tự dispose |
| `Schedulers.single()` | Reactor | Dùng và không tự dispose |
| `Schedulers.newParallel(...)` | Thành phần tạo | Giữ tham chiếu và dispose |
| `Schedulers.newSingle(...)` | Thành phần tạo | Giữ tham chiếu và dispose |
| `Schedulers.newBoundedElastic(...)` | Thành phần tạo | Giữ tham chiếu và dispose |
| `Schedulers.fromExecutorService(...)` | Theo ownership executor và scheduler wrapper | Phối hợp shutdown theo hợp đồng đã chọn |

## 9. Cancellation, shutdown và tác vụ đang chạy

Dispose scheduler là một phần của quy trình dừng ứng dụng, nhưng không thay thế cancellation của từng subscription. Nếu một pipeline đang chạy và downstream hủy, tín hiệu hủy được truyền ngược qua pipeline để các nguồn và tác vụ hỗ trợ cancellation có thể dừng công việc.

Khi chuẩn bị shutdown:

1. Ngừng nhận công việc mới ở thành phần sở hữu.
2. Hủy hoặc chờ các subscription theo chính sách của ứng dụng.
3. Chờ những tác vụ cần hoàn tất nếu nghiệp vụ yêu cầu.
4. Dispose worker và scheduler do thành phần tạo.
5. Hoàn tất việc đóng các executor hoặc tài nguyên liên quan theo ownership đã xác định.

Không nên dispose scheduler ngay khi ứng dụng vừa bắt đầu shutdown nếu vẫn còn request hợp lệ cần hoàn tất trên scheduler đó. Ngược lại, giữ scheduler sống vô thời hạn sau khi thành phần đã dừng có thể để lại thread và tác vụ không cần thiết.

Các tác vụ blocking có thể không phản hồi cancellation ngay lập tức. Nếu scheduler hoặc executor bị dispose trong khi một tác vụ blocking vẫn chạy, hành vi dừng phụ thuộc implementation và khả năng đáp ứng interrupt của tác vụ. Thiết kế tác vụ nên có timeout, giới hạn thời gian và cơ chế dừng phù hợp.

## 10. Kiểm thử vòng đời scheduler

Các test tạo scheduler riêng cần giải phóng scheduler sau khi hoàn tất. Có thể dùng `try/finally` để bảo đảm cleanup ngay cả khi assertion hoặc pipeline phát lỗi:

```java
Scheduler scheduler =
    Schedulers.newSingle("test-worker");

try {
    StepVerifier.create(
            Mono.fromCallable(() -> "done")
                .subscribeOn(scheduler)
        )
        .expectNext("done")
        .verifyComplete();
} finally {
    scheduler.dispose();
}
```

Test trên xác nhận pipeline phát giá trị rồi hoàn tất, đồng thời scheduler được dispose dù test thành công hay thất bại.

Có thể kiểm tra trạng thái dispose:

```java
Scheduler scheduler =
    Schedulers.newSingle("lifecycle-test");

assertFalse(scheduler.isDisposed());

scheduler.dispose();

assertTrue(scheduler.isDisposed());
```

Với scheduler tùy chỉnh, `StepVerifier.withVirtualTime` không tự động thay thế scheduler đó bằng đồng hồ ảo. Đồng hồ ảo chủ yếu điều khiển các toán tử sử dụng scheduler ảo mà Reactor cài đặt trong test. Nếu pipeline truyền scheduler riêng vào toán tử hoặc dùng scheduler riêng để chạy tác vụ, cần kiểm thử tài nguyên đó theo cách phù hợp, và vẫn dispose nó sau test.

Không nên dựa vào `Thread.sleep` để chờ scheduler thực hiện công việc trong unit test. Hãy dùng `StepVerifier`, latch hoặc cơ chế đồng bộ phù hợp với test; đảm bảo mọi scheduler và executor được tạo trong test đều được giải phóng.

## 11. Những lỗi quản lý vòng đời thường gặp

- **Tạo scheduler theo từng request.** Điều này làm tăng số thread và tài nguyên. Hãy tạo ở phạm vi service hoặc ứng dụng và tái sử dụng.
- **Quên dispose scheduler do ứng dụng tạo.** Thread và tác vụ có thể còn tồn tại sau khi thành phần đã dừng.
- **Dispose scheduler dùng chung.** Có thể làm hỏng pipeline của các thành phần khác đang dùng cùng tài nguyên Reactor.
- **Dispose quá sớm khi pipeline còn hoạt động.** Tác vụ đang chờ có thể bị hủy hoặc bị từ chối; hãy điều phối shutdown theo vòng đời công việc.
- **Quên dispose Worker.** Worker được tạo thủ công cũng có vòng đời riêng.
- **Không xác định ownership của ExecutorService.** Scheduler wrapper và executor có thể cùng liên quan đến shutdown; cần một chủ sở hữu rõ ràng.
- **Dùng scheduler không phù hợp.** CPU-bound và blocking I/O có đặc tính khác nhau; chọn loại scheduler và giới hạn tài nguyên tương ứng.
- **Dùng virtual time cho scheduler riêng mà không kiểm soát nó.** Scheduler tùy chỉnh không tự động được đồng hồ ảo điều khiển.

## 12. Bài tập vận dụng

Một ứng dụng có hai thành phần: dịch vụ tạo báo cáo cần bốn thread cho tác vụ CPU-bound, và gateway tích hợp hệ thống cũ cần tối đa tám thread cho lời gọi blocking. Cả hai thành phần có nhiều request đồng thời và có thể bị dừng độc lập trong quá trình shutdown.

Hãy thiết kế cách quản lý scheduler cho hai thành phần:

1. Chọn factory phù hợp cho từng loại công việc và giải thích giới hạn thread.
2. Tạo scheduler một lần ở cấp thành phần, giữ trong field và tái sử dụng trong nhiều pipeline.
3. Đưa phép tính báo cáo sang scheduler CPU bằng `subscribeOn` hoặc `publishOn` ở đúng vị trí.
4. Đưa lời gọi blocking của gateway sang scheduler bounded elastic.
5. Thiết kế phương thức đóng thành phần để ngừng nhận việc mới, xử lý subscription còn hoạt động và dispose scheduler.
6. Giải thích vì sao không dispose `Schedulers.parallel()` hoặc `Schedulers.boundedElastic()` sau mỗi request.
7. Viết test dùng scheduler riêng, kiểm tra kết quả và bảo đảm cleanup kể cả khi test thất bại.

Sau khi hoàn thành, hãy xác định ai sở hữu từng scheduler, khi nào nó được tạo, được tái sử dụng ở đâu và được dispose ở thời điểm nào. Một thiết kế tốt giữ số thread trong giới hạn, không làm gián đoạn pipeline của thành phần khác và giải phóng tài nguyên khi vòng đời ứng dụng kết thúc.
