# Timer.Sample qua nhiều callback và điểm kết thúc được xác định rõ

Trong luồng bất đồng bộ, một thao tác có thể bắt đầu trên request thread, đi qua nhiều callback trên các executor khác nhau rồi mới hoàn tất. Nếu tạo và dừng Timer.Sample bên trong cùng một method đồng bộ, phép đo chỉ bao phủ thời gian method đó đăng ký công việc, không bao phủ toàn bộ thao tác. Muốn đo từ lúc bắt đầu đến lúc kết quả cuối cùng được xác định, hãy tạo sample trước khi khởi chạy luồng và giữ nó cho đến callback kết thúc cuối cùng.

Timer.Sample là một đối tượng có thể giữ trong closure hoặc state của operation. Nó không yêu cầu callback kết thúc phải chạy trên cùng thread đã tạo sample. Điều quan trọng là chọn đúng điểm bắt đầu, chỉ dừng sample một lần và xác định rõ ý nghĩa của điểm kết thúc khi có success, exception, timeout hoặc cancellation.

## Chọn ranh giới thời gian trước khi viết code

Một luồng bất đồng bộ thường có nhiều khoảng thời gian khác nhau:

1. Thời gian từ khi nhận yêu cầu đến khi gửi công việc vào executor.
2. Thời gian công việc nằm trong queue chờ worker.
3. Thời gian worker thực sự xử lý.
4. Thời gian chờ các callback hoặc dependency bất đồng bộ.
5. Thời gian từ lúc bắt đầu đến khi operation đạt trạng thái terminal.

Một Timer.Sample chỉ trả lời câu hỏi tương ứng với hai điểm start/stop mà code chọn. Ví dụ, nếu start trước khi submit vào executor và stop sau callback cuối cùng, metric bao gồm cả queue wait, xử lý và thời gian chờ dependency. Nếu start bên trong task khi worker bắt đầu chạy, metric chỉ đo phần xử lý từ worker start đến terminal completion.

| Mục tiêu đo | Điểm start | Điểm stop |
|---|---|---|
| Toàn bộ workflow bất đồng bộ | Ngay trước khi khởi chạy workflow | Callback terminal cuối cùng |
| Độ trễ chờ executor và xử lý | Trước khi submit task | Khi task hoàn tất |
| Thời gian worker thực thi | Đầu thân task trên worker | Cuối thân task |
| Một dependency call | Ngay trước khi gọi dependency | Khi future của dependency hoàn tất |
| Thời gian đến khi caller nhận kết quả | Trước khi trả future cho caller | Khi stage cuối hoàn tất hoặc bị hủy/timeout theo hợp đồng |

Đừng đặt tên metric là processing.duration nếu sample thực tế bao gồm queue wait và thời gian chờ nhiều dependency. Tên và description cần mô tả đúng ranh giới đo.

## Timer.Sample có thể đi qua nhiều thread

Timer.Sample giữ mốc thời gian bắt đầu để tính elapsed time khi gọi stop(Timer). Có thể tạo sample ở một thread rồi đóng sample trong callback được thực thi trên thread khác. Không cần dùng ThreadLocal để chuyển sample giữa các callback.

Điều này khác với trạng thái gắn với thread như một số cách đo thủ công dùng biến cục bộ hoặc ThreadLocal. Trong luồng async, callback có thể chạy trên event loop, common pool hoặc executor riêng; giữ sample trực tiếp trong closure giúp mối liên hệ giữa operation và phép đo rõ ràng.

~~~mermaid
sequenceDiagram
    participant R as Request thread
    participant E as Executor
    participant D as Dependency
    participant C as Callback cuối
    R->>R: Timer.Sample.start()
    R->>E: submit workflow
    E->>D: gọi dependency async
    D-->>C: completion callback
    C->>C: xác định outcome
    C->>C: sample.stop(timer)
~~~

Mỗi operation phải có sample riêng. Không dùng chung một Timer.Sample cho nhiều request hoặc nhiều workflow chạy đồng thời. Nếu nhiều nhánh callback cùng có khả năng kết thúc một operation, cần một cơ chế bảo đảm chỉ một nhánh được stop sample.

## Đặt stop tại callback terminal cuối cùng

Với CompletionStage, có thể nối nhiều bước bằng thenApply, thenCompose hoặc thenCombine, rồi gắn một whenComplete ở stage cuối cùng. whenComplete được gọi khi stage đó hoàn tất bình thường hoặc exceptional, vì vậy đây là nơi thích hợp để dừng timer cho toàn bộ workflow.

Ví dụ, một luồng thanh toán gồm authorize bất đồng bộ, tải biên nhận và tạo kết quả:

~~~java
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicBoolean;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class PaymentWorkflow {
    private final MeterRegistry registry;
    private final PaymentGateway gateway;
    private final ReceiptService receipts;

    public PaymentWorkflow(
            MeterRegistry registry,
            PaymentGateway gateway,
            ReceiptService receipts) {
        this.registry = registry;
        this.gateway = gateway;
        this.receipts = receipts;
    }

    public CompletionStage<PaymentResult> execute(PaymentCommand command) {
        Timer.Sample sample = Timer.start(registry);
        AtomicBoolean stopped = new AtomicBoolean();

        try {
            CompletionStage<PaymentResult> terminalStage =
                    gateway.authorizeAsync(command)
                            .thenCompose(receipts::loadAsync)
                            .thenApply(this::toResult);

            return terminalStage.whenComplete((result, error) ->
                    stopOnce(sample, stopped, error));
        } catch (RuntimeException | Error error) {
            // Xử lý lỗi đồng bộ khi khởi chạy workflow,
            // trước khi terminalStage được trả về.
            stopOnce(sample, stopped, error);
            throw error;
        }
    }

    private void stopOnce(
            Timer.Sample sample,
            AtomicBoolean stopped,
            Throwable error) {
        if (!stopped.compareAndSet(false, true)) {
            return;
        }

        String outcome = classify(error);
        Timer timer = registry.timer(
                "payment.workflow.duration",
                "outcome", outcome);
        sample.stop(timer);
    }

    private String classify(Throwable error) {
        if (error == null) {
            return "success";
        }
        return "failure";
    }

    private PaymentResult toResult(Receipt receipt) {
        return new PaymentResult(receipt);
    }
}
~~~

Timer.start(registry) được gọi trước khi bắt đầu authorize, vì vậy thời lượng bao gồm toàn bộ chuỗi callback. Sample được giữ trong closure của whenComplete; callback có thể chạy trên thread khác với thread gọi execute(...).

AtomicBoolean bảo vệ điểm stop nếu code sau này bổ sung một đường kết thúc cạnh tranh, ví dụ timeout handler hoặc cancellation handler riêng. Trong một CompletionStage terminal duy nhất, completion callback vốn chỉ được gọi một lần; guard làm rõ invariant của workflow khi nhiều nguồn terminal được phối hợp. compareAndSet bảo đảm chỉ một nhánh thắng và ghi một observation.

Lời gọi registry.timer(...) dùng tag outcome với tập giá trị hữu hạn. Không đưa exception message, request ID, payment ID hoặc nội dung command vào tag. Có thể mở rộng classify(...) để phân biệt success, failure, timeout và cancelled, miễn là các giá trị được kiểm soát.

## Xử lý exception hoàn tất bất đồng bộ

Khi một stage trong chuỗi ném exception hoặc trả về một stage thất bại, stage cuối sẽ hoàn tất exceptional. whenComplete((result, error) -> ...) vẫn được gọi và error khác null; do đó sample vẫn được dừng.

Ví dụ rút gọn:

~~~java
CompletionStage<PaymentResult> terminalStage =
        gateway.authorizeAsync(command)
                .thenCompose(receipts::loadAsync)
                .thenApply(this::toResult);

return terminalStage.whenComplete((result, error) -> {
    Timer timer = registry.timer(
            "payment.workflow.duration",
            "outcome", error == null ? "success" : "failure");
    sample.stop(timer);
});
~~~

whenComplete giữ nguyên kết quả hoặc exception của stage trước đó nếu callback không ném exception mới. Đây thường là lựa chọn phù hợp khi chỉ muốn ghi metric mà không thay đổi kết quả workflow. handle(...) hoặc exceptionally(...) có thể biến lỗi thành kết quả thay thế; nếu dùng chúng, phải quyết định sample kết thúc trước hay sau bước phục hồi tùy định nghĩa success của nghiệp vụ.

Nếu gateway.authorizeAsync(...) ném exception đồng bộ trước khi trả về stage, không có whenComplete nào được đăng ký. Vì vậy, nếu API có thể ném lỗi ngay lúc khởi chạy, cần bắt lỗi đồng bộ và dừng sample như ví dụ execute(...) ở trên.

## Phân biệt timeout, cancellation và kết thúc công việc thật

Timeout hoặc cancellation có thể làm CompletionStage hoàn tất, nhưng không phải lúc nào cũng có nghĩa công việc nền đã dừng:

- **Timeout:** future được hoàn tất exceptional sau thời hạn. Tác vụ underlying có thể vẫn chạy nếu thư viện không hủy được nó.
- **Cancellation:** future báo CancellationException. Một số API chuyển tín hiệu hủy đến task, nhưng API khác chỉ đổi trạng thái future.
- **Completion:** operation trả kết quả cuối cùng hoặc exception cuối cùng theo hợp đồng.

Nếu metric đo độ trễ mà caller trải qua, stop tại thời điểm future timeout/cancel là hợp lý vì đó là lúc caller nhận trạng thái terminal. Nếu metric đo thời gian worker thực sự chạy, cần stop bên trong worker khi task thực sự kết thúc, kể cả khi caller đã timeout trước đó.

Không dùng cùng một timer để trộn hai ý nghĩa này. Có thể có hai meter riêng:

| Metric | Phạm vi |
|---|---|
| payment.workflow.duration | Thời gian từ lúc nhận workflow đến khi future trả trạng thái terminal cho caller |
| payment.worker.execution.duration | Thời gian worker thực sự thực thi task |

Nếu thêm timeout bằng orTimeout(...), gắn whenComplete sau khi áp dụng timeout để đo thời gian đến terminal signal. Cần xác nhận API future và thư viện dependency có hủy công việc underlying hay không; đừng suy ra điều đó chỉ từ việc future đã timeout.

## Phân loại lỗi mà không tạo cardinality cao

Khi cần phân biệt outcome, dùng tập giá trị nhỏ và ổn định. Có thể unwrap CompletionException hoặc ExecutionException để nhận diện nguyên nhân:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeoutException;

private String classify(Throwable error) {
    if (error == null) {
        return "success";
    }

    Throwable cause = error;
    while ((cause instanceof CompletionException
            || cause instanceof ExecutionException)
            && cause.getCause() != null) {
        cause = cause.getCause();
    }

    if (cause instanceof TimeoutException) {
        return "timeout";
    }
    if (cause instanceof CancellationException) {
        return "cancelled";
    }
    return "failure";
}
~~~

Các tag outcome ở đây chỉ có bốn giá trị. Không dùng tên class exception đầy đủ làm tag nếu hệ thống có nhiều exception tùy biến hoặc exception có thể sinh theo input. Nếu cần phân tích nguyên nhân chi tiết, dùng log hoặc trace; metric có thể giữ một nhóm lỗi hữu hạn như timeout, cancelled, validation và dependency.

## Nhiều callback hoặc nhiều nhánh song song

Khi workflow có nhiều callback tuần tự, chỉ gắn whenComplete sau stage cuối. Không stop ở mỗi thenApply hoặc thenCompose, vì như vậy cùng một sample có thể bị stop nhiều lần hoặc chỉ đo một phần workflow.

Với hai nhánh chạy song song, dùng một stage hợp nhất như CompletableFuture.allOf(...), sau đó dừng sample ở stage tổng:

~~~java
import java.util.concurrent.CompletableFuture;

import io.micrometer.core.instrument.Timer;

Timer.Sample sample = Timer.start(registry);

CompletableFuture<Customer> customerFuture =
        customerClient.loadAsync(customerId);
CompletableFuture<Balance> balanceFuture =
        accountClient.loadBalanceAsync(customerId);

CompletableFuture<AccountView> terminal =
        CompletableFuture.allOf(customerFuture, balanceFuture)
                .thenApply(ignored -> new AccountView(
                        customerFuture.join(),
                        balanceFuture.join()));

return terminal.whenComplete((view, error) -> {
    Timer timer = registry.timer(
            "account.view.workflow.duration",
            "outcome", error == null ? "success" : "failure");
    sample.stop(timer);
});
~~~

allOf đại diện cho điểm mà cả hai nhánh đã hoàn tất. Nếu một nhánh lỗi, stage tổng sẽ hoàn tất exceptional; whenComplete vẫn dừng sample. join() ở đây được gọi sau khi allOf hoàn tất nên các future con đã terminal; trong luồng xử lý khác, tránh gọi join() trên thread có thể bị block không cần thiết.

Nếu chỉ cần đo một nhánh cụ thể, gắn sample riêng cho nhánh đó. Không dùng một sample chung rồi stop ở callback đầu tiên trong khi nhánh còn lại vẫn chạy.

## Đặt ranh giới khi có retry

Nếu workflow thử lại dependency nhiều lần, sample đặt trước toàn bộ workflow sẽ đo tổng thời gian bao gồm retry và backoff. Đây thường là latency mà caller trải qua. Nếu muốn biết từng lần gọi dependency mất bao lâu, tạo Timer riêng cho từng attempt.

~~~java
private CompletionStage<Authorization> authorizeAttempt(
        PaymentCommand command) {
    Timer.Sample attempt = Timer.start(registry);
    try {
        return gateway.authorizeAsync(command)
                .whenComplete((value, error) -> {
                    Timer timer = registry.timer(
                            "payment.gateway.attempt.duration",
                            "outcome", error == null ? "success" : "failure");
                    attempt.stop(timer);
                });
    } catch (RuntimeException | Error error) {
        attempt.stop(registry.timer(
                "payment.gateway.attempt.duration",
                "outcome", "failure"));
        throw error;
    }
}
~~~

Workflow timer và attempt timer trả lời hai câu hỏi khác nhau. Không cộng tổng duration của các attempt với workflow duration vì workflow đã bao gồm các attempt và thời gian chờ giữa chúng.

## Callback phải nhẹ và không có side effect

Callback dừng timer nên thực hiện nhanh. Tránh gọi database, ghi file, gửi network request hoặc chờ một future khác bên trong callback chỉ để hoàn tất instrumentation. Nếu callback bị block, nó có thể làm chậm executor hoặc event loop đang hoàn tất operation.

Việc dừng timer nên là thao tác cuối hoặc gần cuối của callback terminal. Nếu cần xử lý kết quả nghiệp vụ, hãy quyết định ranh giới đo:

- Nếu muốn đo đến khi dependency trả kết quả, stop trước bước xử lý hậu kỳ.
- Nếu muốn đo toàn bộ workflow gồm hậu kỳ, stop sau khi stage hậu kỳ hoàn tất.
- Nếu muốn cả hai, tạo hai metric có tên và ranh giới rõ ràng.

Không để callback ghi nhận lại nghiệp vụ hoặc thay đổi kết quả chỉ để phục vụ metric. Instrumentation cần quan sát luồng thực thi, không trở thành một nhánh xử lý nghiệp vụ mới.

## Tác vụ không bao giờ hoàn tất

Timer.Sample chỉ được ghi vào Timer khi gọi stop(...). Nếu future bị treo và không bao giờ hoàn tất, sample không tạo observation; không có một timer đang chạy được xuất tự động chỉ vì sample đã được tạo.

Để bảo đảm có điểm kết thúc, workflow cần chính sách timeout hoặc cancellation rõ ràng. Nếu muốn theo dõi số tác vụ vẫn đang chạy và thời gian của chúng khi chưa hoàn tất, cân nhắc LongTaskTimer cho trạng thái active. Có thể kết hợp:

- Timer để ghi thời lượng sau khi operation terminal.
- LongTaskTimer để quan sát số task đang chạy và thời lượng hiện tại của task.

Hai meter phục vụ hai mục tiêu khác nhau. Dừng LongTaskTimer.Sample khi task thực sự kết thúc; nếu caller timeout nhưng worker vẫn chạy, cần chọn điểm stop theo trạng thái worker chứ không theo future của caller.

## Kiểm thử sample qua nhiều callback

Test nên chứng minh sample chưa được ghi nhận khi callback trung gian hoàn tất, và chỉ có một observation khi stage terminal kết thúc:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class AsyncTimerTest {
    @Test
    void stopsOnlyAfterTheTerminalStageCompletes() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CompletableFuture<Integer> source = new CompletableFuture<>();

        Timer.Sample sample = Timer.start(registry);
        CompletionStage<Integer> terminal = source
                .thenApply(value -> value + 1)
                .thenApply(value -> value * 2)
                .whenComplete((value, error) -> {
                    Timer timer = registry.timer(
                            "workflow.duration",
                            "outcome", error == null ? "success" : "failure");
                    sample.stop(timer);
                });

        Timer timer = registry.get("workflow.duration")
                .tag("outcome", "success")
                .timer();
        assertThat(timer.count()).isZero();

        source.complete(3);

        assertThat(terminal.toCompletableFuture().join()).isEqualTo(8);
        assertThat(timer.count()).isEqualTo(1);

        registry.close();
    }
}
~~~

Test dùng future chưa hoàn tất để kiểm soát thời điểm callback. Trước khi source.complete(...), Timer chưa có observation. Sau khi chuỗi callback hoàn tất, Timer có đúng một observation. Để kiểm tra exception, gọi completeExceptionally(...) và xác nhận series outcome=failure có count bằng một.

Nếu test timeout hoặc cancellation, xác nhận metric được ghi theo định nghĩa đã chọn: caller terminal hay worker terminal. Không dựa vào Thread.sleep(...) ngắn để phỏng đoán callback đã chạy; dùng future hoàn tất tường minh hoặc latch với timeout rõ ràng.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Timer chỉ đo thời gian submit task | Sample được stop ngay sau khi executor nhận task | Giữ sample đến terminal callback |
| Duration quá lớn so với thời gian worker chạy | Sample bắt đầu trước queue wait hoặc bao gồm backoff/dependency | Đổi tên hoặc tách metric theo ranh giới |
| Một operation tăng count nhiều lần | Stop ở nhiều callback hoặc nhiều terminal handler | Chỉ có một điểm stop; dùng guard nếu có nhiều terminal path |
| Exception không được đo | Chỉ stop trong callback success như thenApply | Gắn whenComplete vào stage cuối |
| Lỗi đồng bộ khi khởi chạy không được đo | API ném exception trước khi trả CompletionStage | Bắt lỗi quanh đoạn tạo workflow và stop sample |
| Timeout đã ghi xong nhưng worker vẫn chạy | Future timeout không hủy được underlying task | Đo caller latency và worker execution riêng |
| Metric không có observation | Future không bao giờ terminal nên sample không được stop | Đặt timeout/cancel policy hoặc theo dõi active task bằng LongTaskTimer |
| Tag tăng cardinality | Dùng exception message, request ID hoặc task ID làm tag | Dùng outcome hữu hạn và chuyển chi tiết vào log/trace |
| Callback làm chậm event loop | Thực hiện I/O hoặc xử lý nặng trong whenComplete | Giữ callback instrumentation ngắn và không block |

## Checklist triển khai

- [ ] Đã xác định metric đo toàn workflow, queue wait, worker execution hay dependency attempt.
- [ ] Timer.Sample được tạo đúng trước điểm bắt đầu đã chọn.
- [ ] Sample được giữ trong closure/state của operation, không dùng chung giữa các operation.
- [ ] Chỉ stop tại terminal stage cuối cùng của ranh giới đo.
- [ ] Success và exceptional completion đều đi qua điểm stop.
- [ ] Lỗi đồng bộ trước khi tạo stage cũng được xử lý.
- [ ] Timeout và cancellation có ngữ nghĩa rõ đối với caller và worker.
- [ ] Nhiều terminal path dùng guard để chỉ stop một lần.
- [ ] Tag outcome có tập giá trị hữu hạn.
- [ ] Callback không thực hiện I/O hoặc công việc blocking.
- [ ] Test xác nhận không ghi trước terminal completion và chỉ ghi một observation sau đó.
- [ ] Task có thể treo được quản lý bằng timeout hoặc metric active phù hợp.

Timer.Sample có thể được giữ qua nhiều callback và dừng trên thread khác với thread bắt đầu. Độ chính xác của metric phụ thuộc vào việc chọn đúng ranh giới và dừng sample đúng một lần khi operation đạt trạng thái terminal đã định nghĩa. Với success, exception, timeout và cancellation, hãy quyết định rõ đang đo trải nghiệm của caller hay thời gian worker thực sự chạy; nếu hai câu hỏi đều cần thiết, dùng hai metric riêng thay vì trộn chúng vào một duration.
