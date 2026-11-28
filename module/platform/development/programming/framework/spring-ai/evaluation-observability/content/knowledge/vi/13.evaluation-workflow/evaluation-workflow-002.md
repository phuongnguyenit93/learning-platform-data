# Chạy đánh giá theo lô với số công việc đồng thời có giới hạn

Một ca đánh giá Spring AI thường gồm **tạo câu trả lời**, **thu bằng chứng RAG/tool**, **chạy evaluator** và **lưu kết quả**. Khi có 10 ca, nhóm có thể chạy từng ca theo thứ tự. Nhưng khi dataset tăng thành 1.000–10.000 ca, chạy tuần tự mất nhiều thời gian; còn tạo 1.000 lời gọi đồng thời bằng cách “phóng” tất cả request ngay lập tức có thể gây lỗi `429 Too Many Requests`, timeout, hàng đợi tràn bộ nhớ, chi phí khó dự đoán và kết quả thiếu ca.

Giải pháp là **batch evaluation với bounded concurrency**: cho phép một số công việc *đang xử lý* cùng lúc, nhưng kiểm soát số công việc chưa hoàn thành, tốc độ gọi các dịch vụ ngoài, cách retry và khả năng ghi nhận đầy đủ kết quả. Đây không chỉ là một thủ thuật tăng tốc Java; nó quyết định **độ tin cậy, độ tái lập và tính công bằng của kết quả đánh giá**.

Trong chương **Quy trình đánh giá** của module **SPRING_AI_EVALUATION_OBSERVABILITY**, bài học tập trung vào việc tổ chức các batch chạy dataset có giới hạn song song, chấm relevance/fact checking/RAG/tool calling và liên kết kết quả với metrics, traces, token, chi phí, độ trễ theo phiên bản prompt/model/pipeline.

## 1. Mục tiêu học tập

Sau khi học xong, bạn có thể:

- Phân biệt `batch size`, `parallelism`, `in-flight limit`, độ dài hàng đợi, `rate limit` và quota token.
- Giải thích tại sao thread pool có số worker cố định **chưa đủ** để bảo vệ ứng dụng nếu hàng đợi nhận việc không giới hạn.
- Chạy một bộ ca đánh giá bằng Java với **số attempt chưa hoàn thành bị chặn trên**, thu đủ kết quả khi một số attempt lỗi.
- Bố trí timeout, retry, backoff và giới hạn riêng cho model, evaluator, VectorStore và tool backend.
- Phân biệt lỗi thực thi, lỗi chấm, FAIL chất lượng, ca chưa chấm và ca bị hủy.
- Thu metrics/traces về throughput, mức đồng thời, độ trễ p95, lỗi 429, token và chi phí.
- Chọn mức đồng thời bằng thực nghiệm có kiểm soát, thay vì chỉ tăng số thread.
- Giữ ca kiểm thử độc lập để chạy song song không gây lẫn memory, tool state hoặc dữ liệu giữa các case.
- So sánh baseline/candidate với cấu hình, quota, dataset và quy tắc chấm tương đương.

## 2. Các khái niệm nền tảng cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Batch** | Một đợt xử lý tập ca đã xác định | `runId=batch-2026-05-v1` gồm 500 case |
| **Batch size** | Số ca được gom trong một đợt hoặc khối đầu vào | 500 case trong một run |
| **Concurrency** | Số công việc đang được xử lý hoặc chờ I/O tại một thời điểm | Tối đa 8 case in-flight |
| **Parallelism** | Số phần công việc thực sự chạy đồng thời trên tài nguyên tính toán | Nhiều CPU thread xử lý cùng lúc |
| **In-flight window** | Số công việc đã gửi nhưng chưa thu hồi kết quả | `inFlight ≤ 8` |
| **Queue capacity** | Số công việc chờ được giữ trong hàng đợi | Không tạo queue của cả 500 case |
| **Rate limit** | Giới hạn số request trên một đơn vị thời gian | Provider cho 60 RPM |
| **Token quota** | Giới hạn token trong cửa sổ thời gian | Provider cho 120.000 TPM |
| **Retry** | Thử lại sau lỗi có thể phục hồi | Thử lại 429 sau `Retry-After` |
| **Backpressure** | Nguồn phát việc phải giảm tốc khi hệ thống xử lý chưa kịp | Chỉ nạp case mới sau khi một case cũ hoàn tất |

**Concurrency không phải rate limit.** Tối đa 4 lời gọi cùng lúc vẫn có thể vượt 60 request/phút nếu mỗi lời gọi hoàn thành trong 100 ms. Ngược lại, giữ 20 worker không giúp ích nếu provider chỉ chấp nhận rất ít request/phút.

**Một case cũng không nhất thiết là một model call.** Trong một attempt, RAG có thể gọi embedding, ChatModel có thể yêu cầu tool rồi gọi model lần hai, và evaluator có thể gọi thêm một judge model. Vì vậy, giới hạn *số case đang chạy* và giới hạn *số lời gọi tới một provider* là hai lớp kiểm soát khác nhau.

### 2.1. Ví dụ không giới hạn và có giới hạn

~~~mermaid
flowchart TD
    A["Dataset 1.000 ca"] --> B{"Cách lập lịch?"}
    B -- "Gửi toàn bộ ngay" --> C["1.000 Future / task được gửi"]
    C --> D["Hàng đợi dài hoặc lời gọi bùng nổ"]
    D --> E["429, timeout, retry chồng chất"]
    B -- "Cửa sổ 8 ca" --> F["Tối đa 8 attempt chưa hoàn tất"]
    F --> G["Đợi 1 attempt hoàn thành"]
    G --> H["Lưu kết quả + bổ sung 1 ca"]
    H --> F
~~~

Trong nhánh có giới hạn, dataset có thể lớn nhưng số task **đã đưa vào executor mà chưa hoàn tất** không vượt một ngưỡng. Khi xử lý kết quả chậm, tốc độ đưa thêm việc cũng chậm lại: đó là backpressure ở mức runner.

## 3. Vì sao batch evaluation cần bounded concurrency?

### 3.1. Bảo vệ quota và tính ổn định

Các dịch vụ model, embedding, vector database và tool backend đều có giới hạn tài nguyên. Nếu quá nhiều request đồng thời:

- Provider có thể trả 429 hoặc throttle, tạo nhiều retry.
- Connection pool, socket, memory, bộ đệm và CPU bị sử dụng quá mức.
- Tool backend có thể quá tải hoặc ghi đè trạng thái kiểm thử.
- Thời gian chờ không phản ánh đặc tính bình thường của model; điểm latency bị sai lệch.
- Mẫu lỗi tập trung ở các case chạy trùng đợt cao tải, làm khó diễn giải quality regression.

### 3.2. Tránh hàng đợi không giới hạn

Ví dụ:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(8);

for (EvaluationCase testCase : allCases) {
    pool.submit(() -> evaluate(testCase));
}
~~~

Đoạn mã trên **chỉ cố định số thread worker**. Trong JDK, `newFixedThreadPool` dùng hàng đợi tác vụ có khả năng nhận thêm nhiều phần tử; gọi `submit` cho hàng triệu ca vẫn có thể giữ hàng triệu task/Future đang chờ. Đó là rủi ro về bộ nhớ và khó xử lý dừng/khôi phục.

**Giới hạn thực sự** cần kiểm cả *số việc đã submit và chưa được thu kết quả*, hoặc dùng hàng đợi có capacity rõ với cơ chế từ chối/backpressure thích hợp.

### 3.3. Đảm bảo tính toàn vẹn của kết quả

Trong batch, ca thứ 20 có thể kết thúc trước ca thứ 2. Nếu code ghi verdict vào “dòng hiện tại” mà không kèm `caseId`/`attemptId`, kết quả sẽ bị gán sai ca.

Một runner đúng cần:

1. Mỗi attempt có định danh duy nhất.
2. Kết quả và lỗi được gắn trực tiếp với attempt.
3. Việc ghi bền vững không bị hai thread ghi chồng lẫn nhau.
4. Ca lỗi kỹ thuật không biến mất khỏi mẫu số.
5. Chạy lại có chính sách retry/idempotency rõ, nhất là với tool có tác dụng phụ.

## 4. Phạm vi giới hạn: nhiều tầng, không chỉ một thread pool

Một evaluation pipeline có thể gồm các bước:

~~~mermaid
flowchart LR
    C["Case scheduler<br/>max in-flight"] --> R["RAG / VectorStore"]
    R --> M["ChatModel<br/>provider quota"]
    M --> T["Tool backend<br/>concurrency / permissions"]
    T --> J["LLM judge<br/>provider quota"]
    J --> W["Result writer"]
    C -.-> O["Run metrics / tracing"]
    R -.-> O
    M -.-> O
    T -.-> O
    J -.-> O
~~~

Không phải mọi case đều qua tất cả các bước. Nhưng ở mỗi ranh giới, cần nêu **tài nguyên nào là điểm nghẽn**.

| Ranh giới | Cần bảo vệ | Cách kiểm soát điển hình |
| --- | --- | --- |
| Toàn bộ batch | Số attempt đang được xử lý | Bounded in-flight window |
| ChatModel provider | Số lời gọi cùng lúc, RPM/TPM | Semaphore + rate limiter/token budget |
| Embedding provider | Quota embedding, kích thước input | Giới hạn riêng; tránh tạo embedding không cần |
| VectorStore | Connection pool, query timeout, độ trễ | Pool/timeout và giới hạn truy vấn |
| Tool backend | Số kết nối, quyền, giao dịch | Concurrency cap, sandbox, idempotency |
| LLM judge | Token và quota của evaluator | Chấm theo lô riêng hoặc cap dùng chung |
| Kho lưu kết quả | I/O throughput, transaction size | Ghi có kiểm soát, checkpoint |

### 4.1. Nếu evaluator dùng cùng nhà cung cấp với model chính

Ví dụ 8 case chạy đồng thời, mỗi case gọi một ChatModel để sinh câu trả lời rồi một judge model để chấm. Nếu ChatModel và judge dùng chung quota của một tài khoản provider, chạy 8 + 8 lời gọi riêng rẽ không có điều phối có thể gây bùng tải.

Có hai cách tổ chức hợp lý:

- **Một pipeline nối tiếp theo case**, với giới hạn chung quanh *mọi lời gọi provider*.
- **Hai giai đoạn tách biệt**: sinh và lưu bằng chứng trước, sau đó chấm trong một batch riêng; cả hai cùng sử dụng một cơ chế quota nếu có thể chạy chồng nhau.

Giới hạn concurrency ở *runner* không tự thay thế bộ giới hạn provider, nhất là khi một attempt tạo nhiều lời gọi model/tool.

### 4.2. Giới hạn cục bộ không giới hạn nhiều tiến trình

`Semaphore(4)` trong một JVM chỉ giới hạn các thread dùng đúng semaphore đó. Nếu chạy 5 runner trên 5 máy, tổng vẫn có thể là 20 lời gọi cùng lúc. Khi có nhiều instance hoặc job song song, phải phối hợp quota toàn hệ thống hoặc phân chia ngân sách cho từng runner.

Không nhầm một giới hạn thread-local/process-local với cam kết toàn tài khoản provider.

## 5. Chọn mức đồng thời ban đầu

Không có số `maxConcurrency` phù hợp cho mọi mô hình. Nó phụ thuộc thời gian mỗi case, số lời gọi trong case, quota provider, tài nguyên và chi phí.

### 5.1. Tư duy từ độ trễ và thông lượng

Trong trạng thái ổn định, với các giả định của định luật Little:

\[
L \approx \lambda \times W
\]

Trong đó:

- \(L\): số công việc trung bình trong hệ thống đang xét;
- \(\lambda\): thông lượng hoàn thành (case/giây);
- \(W\): thời gian trung bình một công việc ở trong hệ thống (giây).

Nếu một case mất trung bình 2 giây và có 4 case đang thực thi, thông lượng lý tưởng xấp xỉ \(4/2=2\) case/giây, **khi không có nghẽn khác**. Đây là mô hình ước tính, không phải bảo đảm về tốc độ.

Nếu tăng concurrency từ 4 lên 16 nhưng provider bị giới hạn 60 requests/phút, thông lượng thực có thể không tăng, còn 429 và latency lại tăng.

### 5.2. Kiểm soát cả RPM và TPM

Giả sử một case có:

- 1 lần gọi model tạo câu trả lời;
- 1 lần gọi model chấm;
- tổng cộng khoảng 2.000 tokens (input + output) cho cả hai lần.

Quota **giả định** của tài khoản: 60 requests/phút và 60.000 tokens/phút.

Giới hạn thông lượng do số request:

\[
\frac{60\ \text{requests/min}}{2\ \text{requests/case}}
=30\ \text{cases/min}.
\]

Giới hạn do token:

\[
\frac{60{,}000\ \text{tokens/min}}{2{,}000\ \text{tokens/case}}
=30\ \text{cases/min}.
\]

Dù runner có 8 hay 80 worker, thông lượng dài hạn từ **hai quota giả định này** khó vượt khoảng 30 case/phút nếu mọi lời gọi đều tính vào cùng hạn mức. Trên thực tế cần chừa khoảng an toàn, dự trù token thay đổi và tuân theo các cửa sổ quota cụ thể của provider.

Công thức thực dụng để tìm ngưỡng khởi đầu:

\[
\text{targetThroughput}
\leq \min(
\text{capacity do latency/concurrency},
\text{capacity do RPM},
\text{capacity do TPM},
\text{capacity downstream}
).
\]

### 5.3. Quy trình tuning

1. Bắt đầu nhỏ, ví dụ `maxInFlight=1` hoặc `2`.
2. Chạy trên một tập ca đại diện, giữ cùng prompt/model/dataset và cấu hình tải.
3. Thử `2 → 4 → 8`; theo dõi throughput, p50/p95 latency, 429, timeout, token và cost.
4. Dừng tăng nếu throughput không cải thiện tương xứng, 429 xuất hiện, latency tăng mạnh hoặc đánh giá mất ổn định.
5. Cố định ngưỡng phù hợp và ghi vào run manifest để benchmark có thể so sánh.

Không dựa duy nhất vào số lõi CPU: lời gọi model qua mạng thường bị chặn ở I/O/provider quota, trong khi tokenization nội bộ, đánh giá rule hoặc parsing có thể dùng nhiều CPU.

## 6. Dữ liệu cần đóng băng trước khi chạy batch

Một batch không nên chỉ có tham số “chạy tất cả”. Cần biết đang đo cái gì và bằng cấu hình nào.

### 6.1. Dataset record

~~~json
{
  "datasetVersion": "support-eval-v2",
  "caseId": "REFUND-001",
  "question": "Gói Pro được hoàn phí trong bao lâu?",
  "referenceFacts": ["14 ngày kể từ ngày mua"],
  "referenceDocumentIds": ["policy-v3#pro"],
  "expectedRetrievalIds": ["policy-v3#pro"],
  "tags": ["rag", "policy", "vi"],
  "rubricVersion": "support-rubric-v2"
}
~~~

Chính sách “14 ngày” trong bài là **dữ liệu giả định phục vụ thực hành**.

### 6.2. Run manifest

~~~yaml
runId: eval-batch-2026-05-18-candidate
datasetVersion: support-eval-v2
promptVersion: support-prompt-v4
modelVersion: model-candidate
corpusVersion: policy-v3
indexVersion: vector-index-v3
pipelineVersion: rag-v2
judgeVersion: judge-v1
rubricVersion: support-rubric-v2
scheduler:
  maxInFlightCases: 4
  maxProviderConcurrentCalls: 3
  targetProviderRequestsPerMinute: 48
  maxAttemptsPerCase: 3
  perModelCallTimeoutSeconds: 25
environment: staging
~~~

Đây là **format tự thiết kế**, không phải cấu hình mặc định của Spring AI. Giá trị về concurrency/quota là ví dụ, phải hiệu chỉnh theo hạn mức thật.

### 6.3. Quy tắc nhận diện ca và attempt

- `runId` nhận diện một đợt đánh giá cùng bộ cấu hình.
- `caseId` nhận diện bài kiểm thử và kỳ vọng.
- `attemptId` nhận diện **một lần thực thi cụ thể** của case.
- `retryNo` nhận diện retry của một lần gọi hoặc một attempt tùy hợp đồng.
- `traceId` dẫn tới dấu vết nếu request có tracing.
- `rubricVersion` và `judgeVersion` giúp phân biệt thay đổi của cách chấm.

Cùng `caseId` có thể xuất hiện trong nhiều run. Không gán kết quả bằng thứ tự hoàn thành; thứ tự này không bảo đảm giống thứ tự trong dataset.

## 7. Thuật toán bounded in-flight: cửa sổ trượt

Phương án dễ hiểu và phù hợp cho một runner JVM đơn là **chỉ submit tối đa N task**. Khi một task hoàn thành, lấy kết quả, lưu hoặc phát sự kiện, rồi submit đúng một task mới. Đây là cửa sổ trượt.

~~~text
pending cases: [1,2,3,4,5,6,7,8,9,...]
maxInFlight = 3

submit 1,2,3
inFlight = 3

case 2 completes → record result 2 → submit case 4
inFlight = 3

case 1 completes → record result 1 → submit case 5
inFlight = 3

...
after all submitted:
drain remaining tasks
mark batch completed only when every case has a terminal outcome
~~~

**Ưu điểm:**

- Giới hạn số task đã submit nhưng chưa thu kết quả.
- Không tạo hàng đợi Future bằng kích thước toàn bộ dataset.
- Không chặn kết quả đã hoàn thành chỉ vì một case đứng trước đang chậm (*head-of-line blocking*).
- Dễ ghi mỗi outcome khi xong và thống kê tiến độ.

**Giới hạn:** một case bị treo vô thời hạn vẫn giữ slot. Phải cấu hình timeout ở các lời gọi I/O/provider/tool và có chính sách hủy/khôi phục hợp lý.

## 8. Java: triển khai runner với `ExecutorCompletionService`

Ví dụ Java 17+ dưới đây cố tình tách **lập lịch**, **công việc ứng dụng** và **ghi kết quả**. Runner không phụ thuộc vào provider Spring AI; nó có thể gọi một `CaseProcessor` được nối với Spring AI service.

~~~java
import java.util.List;
import java.util.Objects;
import java.util.concurrent.*;
import java.util.function.Consumer;

public final class BoundedEvaluationRunner {

    public record EvalCase(
            String caseId,
            String question,
            String group) {}

    public enum ExecutionStatus {
        COMPLETED, FAILED, INTERRUPTED
    }

    public record CaseOutcome(
            int inputIndex,
            String caseId,
            String group,
            ExecutionStatus status,
            String answer,
            String errorType,
            long durationNanos) {}

    @FunctionalInterface
    public interface CaseProcessor {
        String process(EvalCase testCase) throws Exception;
    }

    public static void run(
            List<EvalCase> cases,
            int maxInFlight,
            CaseProcessor processor,
            Consumer<CaseOutcome> resultSink)
            throws InterruptedException, ExecutionException {

        Objects.requireNonNull(cases);
        Objects.requireNonNull(processor);
        Objects.requireNonNull(resultSink);

        if (maxInFlight < 1) {
            throw new IllegalArgumentException("maxInFlight must be >= 1");
        }

        ExecutorService workers = Executors.newFixedThreadPool(maxInFlight);
        CompletionService<CaseOutcome> completions =
                new ExecutorCompletionService<>(workers);
        boolean finished = false;

        try {
            int nextIndex = 0;
            int inFlight = 0;

            // Nạp cửa sổ ban đầu; không submit toàn bộ dataset.
            while (nextIndex < cases.size() && inFlight < maxInFlight) {
                int index = nextIndex++;
                completions.submit(() -> execute(index, cases.get(index), processor));
                inFlight++;
            }

            while (inFlight > 0) {
                // Lấy bất kỳ task nào hoàn thành trước.
                Future<CaseOutcome> completed = completions.take();
                CaseOutcome result = completed.get();

                // Ghi một luồng tại thread điều phối, không ghi đè theo thứ tự case.
                resultSink.accept(result);
                inFlight--;

                if (nextIndex < cases.size()) {
                    int index = nextIndex++;
                    completions.submit(
                            () -> execute(index, cases.get(index), processor));
                    inFlight++;
                }
            }

            finished = true;
        } finally {
            if (finished) {
                workers.shutdown();
            } else {
                // Nếu runner bị gián đoạn, lỗi sink hoặc lỗi không xử lý,
                // yêu cầu các task còn chạy dừng; I/O cần hỗ trợ timeout.
                workers.shutdownNow();
            }
        }
    }

    private static CaseOutcome execute(
            int index,
            EvalCase testCase,
            CaseProcessor processor) {

        long started = System.nanoTime();

        try {
            String answer = processor.process(testCase);
            return new CaseOutcome(
                    index,
                    testCase.caseId(),
                    testCase.group(),
                    ExecutionStatus.COMPLETED,
                    answer,
                    null,
                    System.nanoTime() - started);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return new CaseOutcome(
                    index,
                    testCase.caseId(),
                    testCase.group(),
                    ExecutionStatus.INTERRUPTED,
                    null,
                    ex.getClass().getSimpleName(),
                    System.nanoTime() - started);
        } catch (Exception ex) {
            return new CaseOutcome(
                    index,
                    testCase.caseId(),
                    testCase.group(),
                    ExecutionStatus.FAILED,
                    null,
                    ex.getClass().getSimpleName(),
                    System.nanoTime() - started);
        }
    }

    private BoundedEvaluationRunner() {}
}
~~~

### 8.1. Sử dụng runner với Spring AI

Giả sử dự án đã có `ChatClient` được cấu hình với model, advisors và các kiểm tra nghiệp vụ cần thiết:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.ai.chat.client.ChatClient;

// Ví dụ trong phương thức được phép ném Exception:
List<BoundedEvaluationRunner.EvalCase> cases = List.of(
        new BoundedEvaluationRunner.EvalCase(
                "REFUND-001", "Gói Pro hoàn phí bao lâu?", "rag"),
        new BoundedEvaluationRunner.EvalCase(
                "REFUND-002", "Quá thời hạn thì sao?", "no-evidence"));

ChatClient chatClient = configuredChatClient;
List<BoundedEvaluationRunner.CaseOutcome> results =
        new CopyOnWriteArrayList<>();

BoundedEvaluationRunner.run(
        cases,
        3,
        testCase -> chatClient.prompt()
                .user(testCase.question())
                .call()
                .content(),
        results::add);
~~~

`configuredChatClient` là **đối tượng đã được ứng dụng tạo/cấu hình**, không phải biến Spring AI có sẵn. Trong hệ thống thật, `CaseProcessor` nên gọi cùng pipeline RAG/tool mà sản phẩm sử dụng và lưu evidence; gọi một ChatClient không có RAG advisor sẽ không kiểm tra được retrieval thật.

`CopyOnWriteArrayList` trong ví dụ chỉ để nhìn kết quả trong bộ nhớ. Với batch lớn, dùng sink ghi có checkpoint ra database/JSONL hoặc hệ thống kết quả; tránh giữ hàng triệu câu trả lời và ngữ cảnh trong RAM. Do `resultSink.accept` chạy ở thread điều phối, một writer tuần tự thông thường có thể phù hợp, miễn bản thân nó xử lý lỗi I/O và quản lý vòng đời file.

### 8.2. Tại sao cách này thực sự giới hạn số task?

Một task mới chỉ được gửi **sau khi** runner nhận và ghi một `CaseOutcome` hoàn tất. Kể cả khi các worker xử lý rất nhanh, tối đa `maxInFlight` task chưa được thu hồi có mặt trong executor tại cùng thời điểm.

Tuy nhiên cần phân biệt:

- **Bounded submitted attempts:** đã được code bảo đảm.
- **Bounded provider calls:** chưa được bảo đảm nếu một attempt tự tạo nhiều lời gọi song song hoặc có các runner khác.
- **Bounded execution time:** chưa được bảo đảm nếu provider/tool không có timeout.
- **Bounded memory of results:** phụ thuộc `resultSink`; nếu gom toàn bộ kết quả vào list, RAM vẫn tăng theo dataset.

### 8.3. Vì sao lấy kết quả bằng `CompletionService`?

Nếu dùng một list các `Future` rồi gọi `future.get()` theo thứ tự input, ca #1 chạy 30 giây có thể khiến bộ điều phối chờ dù ca #2–#8 đã hoàn thành. `ExecutorCompletionService.take()` trả một Future **đã hoàn tất**, nhờ đó slot được bổ sung sớm.

Kết quả nhận theo thứ tự hoàn thành, vì vậy `inputIndex` và `caseId` giúp sắp xếp lại cho báo cáo. Không gán ID dựa trên “đây là kết quả thứ năm được đọc”.

### 8.4. Giới hạn của ví dụ và những điểm cần bổ sung

Đây là **bộ lập lịch mẫu**, không phải hệ thống production đầy đủ:

- Task trả lỗi nghiệp vụ hoặc exception thường dưới dạng `FAILED`; lỗi nghiêm trọng kiểu `Error` có thể khiến `Future.get()` ném `ExecutionException` và batch ngừng. Cần quy định cách xử lý lỗi hạ tầng.
- Nếu `resultSink` ném exception, run bị ngắt; cần đánh dấu `ABORTED/PARTIAL`, giữ checkpoint và không công bố như một batch hoàn tất.
- Nếu thread bị ngắt, `shutdownNow()` chỉ gửi tín hiệu interrupt; một blocking I/O không tôn trọng interruption có thể tiếp tục chạy. Cần timeout ở client/SDK/tool.
- Mã không tự động kiểm RPM/TPM, không retry và không có distributed coordinator.
- Kết quả `COMPLETED` nghĩa là **đã tạo được phản hồi kỹ thuật**. Nó **không đồng nghĩa PASS chất lượng**; phải chạy các evaluator tiếp theo.

## 9. Kiểm tra giới hạn concurrency bằng JUnit

Một test có thể dùng bộ xử lý giả lập để đếm số việc thực sự đang chạy. Không cần gọi provider thật để kiểm thử thuật toán lập lịch.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class BoundedEvaluationRunnerTest {

    @Test
    void neverExceedsConfiguredInFlightLimit() throws Exception {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        List<BoundedEvaluationRunner.CaseOutcome> outcomes =
                new ArrayList<>();

        List<BoundedEvaluationRunner.EvalCase> cases =
                java.util.stream.IntStream.range(0, 30)
                        .mapToObj(i -> new BoundedEvaluationRunner.EvalCase(
                                "CASE-" + i, "Question " + i, "demo"))
                        .toList();

        BoundedEvaluationRunner.run(
                cases,
                4,
                testCase -> {
                    int now = active.incrementAndGet();
                    peak.accumulateAndGet(now, Math::max);

                    try {
                        Thread.sleep(15);
                        return "answer for " + testCase.caseId();
                    } finally {
                        active.decrementAndGet();
                    }
                },
                outcomes::add);

        assertEquals(30, outcomes.size());
        assertTrue(peak.get() <= 4);
        assertTrue(outcomes.stream()
                .allMatch(r -> r.status()
                        == BoundedEvaluationRunner.ExecutionStatus.COMPLETED));
    }
}
~~~

Test chứng minh mức đồng thời quan sát được không vượt 4 trong tác vụ giả lập. Nó không khẳng định throughput đạt tối đa, không kiểm quota provider và không chứng minh chấm relevance/factual correctness đúng.

### 9.1. Các test khác nên có

- Dataset rỗng → runner kết thúc với 0 result, không bị treo.
- `maxInFlight=0` → từ chối cấu hình.
- Một ca ném exception → vẫn ghi outcome của ca đó, các ca khác tiếp tục.
- Kết quả về không theo thứ tự input → ID và index vẫn đúng.
- Một sink lỗi → run không bị đánh dấu thành công, có ghi nhận partial.
- Runner bị interrupt → có chính sách dừng và đánh dấu các case chưa kết thúc.
- Một client trả 429 liên tục → retry không vô hạn và không vượt ngân sách.
- Chạy hai run đồng thời → quota provider dùng chung không bị vượt nếu thiết kế yêu cầu.

## 10. Giới hạn riêng cho lời gọi ChatModel và evaluator

**Cửa sổ case** giới hạn số attempt đang hoạt động. Nhưng một attempt có thể gọi model nhiều lượt. Khi cần giới hạn các request tới cùng nhà cung cấp, dùng thêm semaphore quanh **toàn bộ nơi gọi provider**.

~~~java
import java.util.concurrent.Semaphore;
import org.springframework.ai.chat.client.ChatClient;

public final class ProviderCallGate {

    private final Semaphore permits = new Semaphore(3, true);
    private final ChatClient chatClient;

    public ProviderCallGate(ChatClient chatClient) {
        this.chatClient = chatClient;
    }

    public String complete(String question) throws InterruptedException {
        permits.acquire();
        try {
            return chatClient.prompt()
                    .user(question)
                    .call()
                    .content();
        } finally {
            permits.release();
        }
    }
}
~~~

Đây là giới hạn **ba lời gọi đã vào đoạn `complete` cùng lúc trên cùng instance**. Nếu Spring AI thực hiện những lời gọi lồng nhau hoặc có model khác không đi qua `ProviderCallGate`, chúng không bị semaphore này kiểm soát.

Đặc biệt, nếu `ChatClient` trong đoạn này được cấu hình với tool calls và tự động tạo các lượt gọi model tiếp theo, cần xác định ranh giới semaphore ở **cấp mỗi provider/model invocation** khi quota áp dụng trên từng lời gọi. Giữ permit cho toàn bộ chuỗi `chatClient.call()` chỉ là một biện pháp giới hạn *số conversation đang chạy*, không tự đếm số provider requests trong mỗi conversation.

### 10.1. Tránh deadlock khi dùng nhiều semaphore

Nếu một công việc giữ permit A rồi chờ permit B, còn công việc khác giữ B rồi chờ A, có nguy cơ deadlock. Cần chọn thứ tự lấy permit nhất quán, hoặc không giữ permit của tài nguyên không dùng trong lúc chờ tài nguyên khác.

Ví dụ không nên giữ permit “model provider” suốt thời gian tool backend xử lý nếu mọi pipeline dùng chung permit đó và điều này khiến throughput bị bóp nghẹt vô ích. Cấp độ giới hạn nên phù hợp **tài nguyên thật mà quota bảo vệ**.

### 10.2. Virtual threads có thay thế giới hạn concurrency không?

Không. Java virtual threads hữu ích cho nhiều tác vụ bị chặn bởi I/O nhưng **không tự giới hạn số lời gọi tới provider**. Nếu dùng `Executors.newVirtualThreadPerTaskExecutor()` mà tạo một thread cho mỗi case không có in-flight cap, ứng dụng vẫn có thể vượt quota.

Thread nền là phương tiện thực thi; **bounded scheduling, rate limiting và backpressure** là chính sách tải cần thiết dù dùng platform threads hay virtual threads.

## 11. Rate limiting và retry: hai lớp bảo vệ bổ sung

Một semaphore kiểm soát số lời gọi **đang cùng lúc**; rate limiter kiểm soát **số lời gọi mới theo thời gian**. Provider có thể thực thi cả hai quy tắc và thêm quota TPM.

### 11.1. Chính sách rate limit

Nếu provider cho tối đa 60 RPM, một runner có thể đặt mục tiêu an toàn 45–50 RPM tùy trường hợp. Rate limiter cần được chia sẻ bởi mọi call site dùng cùng quota; nếu các worker tự ngủ độc lập 1 giây rồi gửi request, chúng vẫn có thể cùng phát tại một thời điểm và tạo burst.

Một `token bucket` hoặc cơ chế cấp permit theo cửa sổ có thể giới hạn tốc độ gửi. Với TPM, cần ước lượng token trước request và cập nhật usage sau request; nếu dự báo thấp hơn thực tế, phải xử lý sai lệch và có mức dự phòng.

**Không nên nhầm `input tokens` với `total tokens` trong quota.** Quy tắc tính TPM, output token reservation và cache có thể khác theo provider; cần đối chiếu hợp đồng quota thực tế.

### 11.2. Phân loại lỗi trước khi retry

| Tình huống | Có nên retry tự động? | Ghi chú |
| --- | --- | --- |
| 429 / rate limit | Thường có, theo `Retry-After` và ngân sách | Không gửi lại ngay lập tức |
| 503 / lỗi tạm thời | Có thể, giới hạn số lần | Exponential backoff + jitter |
| Timeout đọc dữ liệu | Có thể nếu thao tác an toàn, idempotent | Phải biết kết quả trước đó có thể đã xảy ra |
| 400 / validation | Thường không | Sửa dữ liệu hoặc mã |
| 401/403 | Thường không | Kiểm tra quyền/credentials |
| Lỗi rubric/evaluator | Có thể retry chấm; giữ evidence | Không tự xem answer là FAIL |
| Tool tạo giao dịch | Không retry mù quáng | Cần idempotency key/hậu điều kiện |

### 11.3. Backoff có giới hạn

Pseudocode:

~~~text
attempt = 1
while attempt <= maxAttempts:
    reserve provider rate/token budget
    acquire provider concurrency permit
    try:
        call provider with per-call timeout
        return success
    catch retryable transient error:
        if attempt == maxAttempts:
            return terminal failure
        sleep with capped exponential backoff + jitter
        honor Retry-After when provided
        attempt += 1
    catch non-retryable error:
        return terminal failure
    finally:
        release concurrency permit
~~~

Quan trọng: **nên nhả concurrency permit trước khi ngủ backoff**, nếu permit chỉ để bảo vệ lời gọi provider đang hoạt động. Giữ permit suốt thời gian sleep sẽ làm nghẽn không cần thiết.

### 11.4. Retry không được làm méo kết quả đánh giá

Nếu case A thành công ngay còn case B thành công sau ba lần retry, cả hai có thể có answer-quality PASS, nhưng operational evidence khác nhau. Ghi:

- `attemptCount`, nguyên nhân retry, tổng chờ backoff.
- Tổng latency nhìn từ test runner và thời gian provider riêng.
- Token/cost của tất cả lời gọi, kể cả những lời gọi bị tính phí trước khi thất bại nếu biết.
- Lỗi kỹ thuật cuối cùng nếu hết retry.

Đừng xóa retry khỏi kết quả để làm latency “đẹp hơn”. Đừng tự động coi tất cả lỗi 429 là FAIL về chất lượng câu trả lời; chúng là lỗi thực thi/hạn mức, cần báo riêng.

## 12. Timeout, hủy và checkpoint khi batch lớn

Concurrency có giới hạn không ngăn một task chờ mãi. Nếu `ChatClient` hoặc tool backend không bao giờ trả lời, vòng `CompletionService.take()` có thể bị chặn chờ kết quả cuối cùng.

### 12.1. Đặt timeout ở đúng tầng

- **Provider HTTP/client timeout:** giới hạn connect/read hoặc timeout toàn lời gọi theo SDK.
- **Tool backend timeout:** không chờ vô hạn vào một service phụ thuộc.
- **Attempt deadline:** giới hạn thời gian end-to-end của một case.
- **Batch deadline:** tránh cả run kéo dài vô hạn khi quota/lỗi kéo dài.
- **Evaluator timeout:** không để bước judge giữ mãi slot khi sinh response đã hoàn tất.

Dùng `Future.get(timeout, unit)` trên một Future **đã được CompletionService trả về sau khi hoàn tất** không giải quyết việc task đang treo. Phải áp dụng deadline vào đúng lời gọi đang chạy hoặc dùng cơ chế điều phối có khả năng theo dõi/hủy các task chưa hoàn thành.

### 12.2. Hủy không đồng nghĩa đã dừng I/O

`future.cancel(true)` hoặc `shutdownNow()` chủ yếu gửi tín hiệu interrupt. Một số thư viện blocking I/O không dừng ngay. Cần kiểm tra SDK/client hỗ trợ cancellation và timeout thế nào; không giả định đã nhả tài nguyên chỉ vì Future được đánh dấu canceled.

Đặc biệt với tool có tác dụng phụ, timeout ở phía client **không chứng minh thao tác backend chưa xảy ra**. Khi retry, cần idempotency key hoặc kiểm tra trạng thái giao dịch tại hệ thống nguồn.

### 12.3. Checkpoint và khôi phục

Batch hàng nghìn ca có thể bị dừng giữa chừng do máy khởi động lại hoặc lỗi kho lưu. Nên lưu kết quả sau mỗi ca hoặc theo từng nhóm nhỏ, đồng thời lưu trạng thái run:

~~~yaml
runId: eval-batch-candidate-v2
status: PARTIAL
totalCases: 1000
finishedCases: 617
technicalCompleted: 590
technicalFailed: 27
unstartedOrIncomplete: 383
lastCheckpointAt: "2026-05-18T10:30:00Z"
~~~

Dữ liệu minh họa. Khôi phục bằng cách đọc các `caseId`/`attemptId` đã có kết quả bền vững và lập kế hoạch cho ca chưa hoàn tất. Không tạo duplicate verdict và không coi những ca bị mất là PASS.

**Khuyến nghị nghiệp vụ:** phân biệt attempt được chạy lại với attempt cũ; lưu `retryOfAttemptId` hoặc version tương đương nếu cần. Khi chạy tool có tác dụng phụ, phải sử dụng sandbox hoặc idempotency token tương ứng.

## 13. Tách giai đoạn sinh câu trả lời và chấm điểm khi cần

Một pipeline per-case nối tiếp như:

~~~text
case → retrieve → answer → evaluate → persist
~~~

dễ xây dựng nhưng có thể giữ slot lâu vì judge model chậm. Với dataset lớn, có thể chia thành **hai batch**:

~~~mermaid
flowchart LR
    D["Versioned dataset"] --> G["Generation batch<br/>N1 bounded"]
    G --> E["Durable execution evidence"]
    E --> J["Scoring batch<br/>N2 bounded"]
    J --> R["Verdicts + feedback"]
    R --> A["Aggregate + compare"]
    E --> T["Traces / usage / costs"]
    T --> A
~~~

**Lợi ích:**

- Chạy lại judge/rubric mà không cần gọi model sinh câu trả lời lần nữa, nếu evidence đã đủ.
- Đặt giới hạn khác nhau cho generation và evaluation.
- Phân biệt chi phí tạo câu trả lời với chi phí đánh giá.
- Cô lập lỗi evaluator để không làm mất answer đã tạo.

**Đổi lại:** cần kho evidence bền vững và cơ chế nối `attemptId` chính xác. Nếu generation/scoring cùng sử dụng provider quota và cùng chạy song song, phải có chính sách phối hợp tốc độ.

### 13.1. Bản ghi tối thiểu của hai giai đoạn

~~~json
{
  "runId": "candidate-v2",
  "caseId": "REFUND-001",
  "attemptId": "candidate-v2-REFUND-001-1",
  "generation": {
    "status": "COMPLETED",
    "answerRef": "secure-answer-reference",
    "effectiveContextRefs": ["policy-v3#pro"],
    "traceId": "real-trace-id-if-present",
    "inputTokens": 1200,
    "outputTokens": 130
  },
  "evaluation": {
    "status": "PENDING",
    "rubricVersion": "support-rubric-v2",
    "judgeVersion": "judge-v1"
  }
}
~~~

Sau khi judge hoàn tất, thêm kết quả đánh giá riêng, **không ghi đè** evidence generation. Nếu thiếu effective context, groundedness có thể ở trạng thái `NOT_EVALUATED`.

### 13.2. Các giới hạn chất lượng không nên bị thay đổi bởi song song

Chạy 8 ca đồng thời không thay đổi định nghĩa relevance, groundedness hay factual correctness. Nhưng nó có thể tạo tác động gián tiếp: memory dùng chung, tool fixture có trạng thái, quota làm timeout, provider tăng latency. Vì vậy, cần **isolation giữa các ca** và báo cáo yếu tố tải để so sánh công bằng.

## 14. Độc lập trạng thái: RAG, tool calling và memory trong batch

### 14.1. Memory và conversation ID

Nếu dùng `ChatMemory`/Memory Advisors, mỗi case độc lập phải có conversation ID riêng hoặc trạng thái memory được reset đúng cách. Nếu hai worker cùng dùng một conversation ID, nội dung của case A có thể đi vào prompt của case B, làm điểm đánh giá mất ý nghĩa và có nguy cơ rò dữ liệu.

Với test hội thoại nhiều lượt, các lượt **trong cùng một case** thường phải chạy theo đúng thứ tự, còn các case độc lập có thể song song.

### 14.2. VectorStore và snapshot dữ liệu

Khi chạy batch so prompt/model, nên giữ cùng corpus/index version hoặc ghi rõ nếu dữ liệu thay đổi. Nếu một worker đang cập nhật index trong lúc worker khác đánh giá, kết quả sẽ phụ thuộc thời điểm và khó tái hiện. Dùng snapshot hoặc môi trường kiểm thử ổn định khi yêu cầu so sánh chính xác.

### 14.3. Tool backend và dữ liệu fixture

Nếu 8 ca dùng chung một đơn hàng thử nghiệm và một ca thay đổi trạng thái, các ca sau có thể nhận kết quả khác dự kiến. Nên:

- Dùng test double/sandbox cho tool có tác dụng phụ.
- Cấp dữ liệu fixture độc lập theo case hoặc theo run.
- Áp dụng kiểm tra quyền backend, schema, idempotency và hậu điều kiện.
- Tránh retry mù quáng các thao tác không idempotent.

### 14.4. Ngữ cảnh mô hình và biến dùng chung

Tránh biến mutable global như `currentCaseId`, `lastRetrievedDocuments` hoặc `lastAnswer` khi nhiều worker dùng chung. Những biến này có thể bị ghi đè giữa ca, dẫn đến evaluator chấm câu A với tài liệu B.

Mỗi task nên nhận một input object bất biến, trả một `CaseOutcome`/evidence riêng và tham chiếu tới `attemptId`. Dùng concurrency-safe clients theo hợp đồng của thư viện; các đối tượng trạng thái hội thoại hoặc builder đang thay đổi không nên chia sẻ tùy tiện giữa các task.

## 15. Thu metrics, traces và đánh giá throughput

Để biết batch đã chọn concurrency hợp lý chưa, phải đo **cả runner** và **các thành phần Spring AI**.

### 15.1. Metrics nên có

| Metric/tín hiệu | Câu hỏi được trả lời | Lưu ý |
| --- | --- | --- |
| `casesSubmitted` / `casesFinished` | Batch tiến triển tới đâu? | Theo run, không coi submitted là completed |
| `inFlightCases` | Có giữ đúng cap không? | Dùng gauge theo runner |
| `runningProviderCalls` | Provider đang có bao nhiêu lời gọi? | Cần instrument tại ranh giới provider |
| `caseDuration` p50/p95/p99 | Ca đánh giá nhanh/chậm ra sao? | Đo end-to-end và từng giai đoạn |
| `throughputCasesPerSecond` | Hoàn thành bao nhiêu case/giây? | Gắn cửa sổ đo rõ |
| `429Count` / retryCount | Có đang vượt quota không? | Tách lỗi provider và lỗi tool |
| `technicalFailureRate` | Bao nhiêu case thất bại kỹ thuật? | Không gộp với quality FAIL |
| `judgeFailureRate` | Bộ chấm có hoạt động ổn định không? | NOT_EVALUATED khác FAIL |
| `input/outputTokens` | Prompt và output có tăng không? | Tổng các model calls |
| `estimatedCost` | Chi phí batch/ca là bao nhiêu? | Đơn giá theo model và ngày |
| `qualityPassRate` | Những ca được chấm có đạt không? | Luôn ghi số mẫu/mẫu số |

### 15.2. Micrometer đo một attempt

Có thể dùng `MeterRegistry` để ghi metric riêng của runner (không thay cho observations Spring AI):

~~~java
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class EvaluationMetrics {

    private final MeterRegistry registry;

    public EvaluationMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(BoundedEvaluationRunner.CaseOutcome outcome) {
        Timer.builder("app.ai.evaluation.case.duration")
                .description("One evaluation execution attempt")
                .tag("stage", "generation")
                .tag("status", outcome.status().name())
                .register(registry)
                .record(outcome.durationNanos(), TimeUnit.NANOSECONDS);
    }
}
~~~

Không đưa `caseId`, raw question, user ID hoặc trace ID vào **metric tags** vì có thể gây cardinality cao và rủi ro riêng tư. Các ID cụ thể nên nằm trong record/evidence store có phân quyền, gắn trace khi có.

Muốn p95 từ một timer trong Prometheus, cần histogram/distribution được cấu hình tương ứng; không thể suy phân vị chỉ từ tổng và số lượng.

### 15.3. Tracing với executor tùy chỉnh

Spring AI/Spring Boot có thể cung cấp observations của `ChatClient`, `ChatModel`, `VectorStore` và tool calls theo phiên bản, nhưng **trace context không nhất thiết tự truyền qua mọi custom executor**. Nếu cần liên kết các span của một attempt với trace cha từ evaluation runner, phải cấu hình context propagation phù hợp với hệ thống tracing đang dùng.

Nếu sampling không giữ một trace, record cần ghi rằng trace không sẵn có; không sinh ra “trace ID tượng trưng” rồi coi như có thể tra cứu.

### 15.4. Đo chi phí của runner và evaluator riêng

Chi phí model có thể ước tính từ usage:

\[
\mathrm{modelCost}
=
\frac{\mathrm{inputTokens}\times \mathrm{priceInputPerMillion}}{10^6}
+
\frac{\mathrm{outputTokens}\times \mathrm{priceOutputPerMillion}}{10^6}.
\]

Ví dụ giá **giả định** 2 USD/triệu input tokens và 8 USD/triệu output tokens, với 2.000 input và 500 output:

\[
\frac{2000\times2 + 500\times8}{10^6}
=0{,}008\ \mathrm{USD}.
\]

Con số trên không bao gồm embedding, reranking, tool/backend, hạ tầng, cache hay evaluator. Nếu một attempt có nhiều lời gọi model, cộng chi phí của từng lời gọi. Nếu judge cũng tiêu thụ token, báo cáo **generation cost** và **evaluation cost** riêng để không nhầm chi phí ứng dụng phục vụ người dùng với chi phí chạy bộ kiểm định.

## 16. Khi nào thêm concurrency làm chất lượng đo kém đi?

Không phải việc chạy nhiều ca cùng lúc làm mô hình trở nên kém về ngữ nghĩa. Nhưng tải quá cao có thể làm **bối cảnh thực thi thay đổi**, khiến phép so sánh không còn công bằng:

- 429/timeout khiến nhiều ca không có answer để chấm.
- Retry và rate-limit backoff làm latency cao bất thường.
- Memory hoặc tool fixture chia sẻ trạng thái làm câu trả lời bị nhiễu.
- Index bị cập nhật trong lúc đánh giá khiến tài liệu khác nhau giữa các ca.
- Một bộ chấm bị quá tải làm tăng `NOT_EVALUATED` hoặc cho phản hồi thiếu ổn định.
- Chi phí đo được phình to do retry, khiến candidate dường như đắt hơn vì mức tải khác.

Vì vậy phải **báo điều kiện concurrency và quota**, không chỉ quality pass rate.

### 16.1. Tách quality regression khỏi overload

| Quan sát | Điều có thể kết luận | Điều còn cần kiểm |
| --- | --- | --- |
| Relevance giảm, không có lỗi 429 | Chất lượng trên mẫu đã chấm thấp hơn | Rubric, model, nguồn, tải có thay đổi không |
| Technical failures tăng theo concurrency | Batch gặp vấn đề khi tăng tải | Provider quota, timeout, kết nối |
| Quality trên completed cases không đổi, completion rate giảm | Phần lớn vấn đề trước mắt là thực thi | End-to-end success và cảnh báo người dùng |
| Groundedness giảm khi cùng dữ liệu, không lỗi tải | Có thể là regression ngữ nghĩa | Context thực tế, prompt, judge |
| Chỉ các case chạy song song với tool side effects bị sai | Có thể có xung đột trạng thái | Isolation, idempotency và backend fixtures |

**Không âm thầm loại mọi ca thất bại kỹ thuật khỏi báo cáo**. Với 100 case, nếu chỉ 70 case có answer và 68 trong số đó PASS, cần báo cả 70% technical completion và 68/70 ≈ 97,1% quality pass *trên ca đã chấm*, không công bố “97,1% của 100 case hoàn thành tốt”.

## 17. Thực hành: tuning batch 200 ca

**Bối cảnh:** một chatbot Spring AI sử dụng RAG cho chính sách dịch vụ giả định và tool `getOrderStatus`. Bạn có dataset 200 ca với các nhóm có nguồn, thiếu nguồn, nguồn mâu thuẫn và tool calling. Mục tiêu là tìm concurrency đủ nhanh mà không làm mất bằng chứng, vượt quota hoặc che giấu lỗi.

### 17.1. Chuẩn bị

1. Ghi `datasetVersion`, `promptVersion`, `modelVersion`, `corpus/indexVersion`, `judgeVersion` và rubric.
2. Tạo fixture hoặc sandbox tool; các case độc lập không cùng thay đổi trạng thái backend.
3. Đặt per-model-call timeout và max retry attempts.
4. Thiết lập provider quota và mức dự phòng giả định; nếu không biết quota, không thử mức tải cao đột ngột.
5. Cài runner bounded in-flight và sink lưu từng outcome ngay khi hoàn thành.

### 17.2. Chạy các mức song song

Thử các cấu hình `1, 2, 4, 8` (và cao hơn chỉ nếu quota cho phép). Bảng sau là **số liệu giả định** để luyện phân tích, không phải benchmark thực của Spring AI:

| maxInFlight | Cases/s | p95 case latency | 429 | Technical completion | Quality PASS trên ca được chấm |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0,40 | 2,8 s | 0 | 200/200 | 190/200 |
| 2 | 0,78 | 3,0 s | 0 | 200/200 | 190/200 |
| 4 | 1,42 | 3,7 s | 1 | 199/200 | 189/199 |
| 8 | 1,50 | 8,2 s | 34 | 185/200 | 176/185 |

**Phân tích:** từ 4 lên 8, throughput tăng không đáng kể nhưng p95, 429 và tỷ lệ không hoàn thành tăng mạnh. Nếu muốn so chất lượng nội dung giữa các phiên bản, cấu hình 8 có thể tạo nhiều sai lệch vận hành. Mức 2 hoặc 4 có thể hợp lý hơn tùy mục tiêu throughput và mức chấp nhận lỗi.

Tỷ lệ quality chỉ là **trên số ca được chấm**; không được bù số ca không hoàn thành bằng giả định đạt.

### 17.3. Thu thập bằng chứng cho một lỗi 429

Chọn một `attemptId` có retry, ghi:

~~~yaml
runId: eval-batch-max8
caseId: REFUND-019
attemptId: eval-batch-max8-REFUND-019-1
generationStatus: FAILED
provider:
  transientErrors:
    - type: RATE_LIMIT
      retryAfterMillis: 1000
  callsAttempted: 3
  terminalReason: RETRY_BUDGET_EXHAUSTED
evaluationStatus: NOT_EVALUATED
latencyMs: 9000
traceRef: "actual-trace-reference-if-available"
~~~

Đây là record minh họa. Đừng biến `evaluationStatus: NOT_EVALUATED` thành factual correctness FAIL, bởi không có answer để chấm. Tuy vậy, ở mức end-to-end, case đã không phục vụ được yêu cầu nên là một thất bại kỹ thuật.

### 17.4. Kiểm tra fairness baseline/candidate

Nếu đánh giá prompt A với concurrency 2 và prompt B với concurrency 8, khác biệt lỗi 429 và latency có thể do **điều kiện chạy**, không phải riêng prompt. Khi so quality và hiệu năng:

- Cố gắng dùng cùng giới hạn concurrency/quota và bộ dữ liệu.
- Ghi thời điểm chạy, tải hệ thống, model/provider và phiên bản.
- Chạy lại một số ca để kiểm tra độ dao động.
- Phân tích cả kết quả theo ca và metric vận hành, không chỉ điểm tổng.

### 17.5. Bài tập mở rộng

Thiết kế hai batch có giới hạn riêng: generation `N=4` và scoring `N=2`. Nếu cả hai gọi chung provider, thêm cơ chế quota dùng chung. Cho một số ca judge timeout; kiểm tra rằng answer đã tạo vẫn được lưu và kết quả chấm thành `NOT_EVALUATED`, không bị xóa.

**Tiêu chí hoàn thành:** dataset 200 ca có đủ terminal outcome, không vượt giới hạn in-flight tại runner, có báo cáo throughput/error/latency/token/cost, và ít nhất một ca FAIL có thể truy ngược vào evidence/trace tương ứng.

## 18. Những sai lầm thường gặp

**Sai lầm 1 — Cứ tạo một Future cho mỗi case vì đã có fixed thread pool.** Fixed worker count không có nghĩa queue cũng bounded. Dùng sliding window hoặc queue có capacity và chính sách backpressure.

**Sai lầm 2 — Xem concurrency là RPM/TPM.** Concurrency chặn số lời gọi cùng lúc; một request rất nhanh vẫn có thể vượt RPM. Token quota cần lớp dự trù riêng.

**Sai lầm 3 — Semaphore ở runner đủ bảo vệ cả judge và provider.** Một case có thể tạo nhiều lời gọi; nhiều process còn chia sẻ cùng quota. Phải xác định đúng cấp giới hạn.

**Sai lầm 4 — Sleep backoff trong lúc giữ permit provider.** Dễ giảm throughput và làm hàng chờ dài thêm. Nhả permit khi đã kết thúc một call rồi mới backoff nếu cơ chế cho phép.

**Sai lầm 5 — Retry mọi lỗi.** 400, 403 và hành động có tác dụng phụ không idempotent cần xử lý khác 429/503.

**Sai lầm 6 — Xem `Future.get(timeout)` sau `CompletionService.take()` là timeout thực thi.** Task đã hoàn thành khi `take()` trả Future; timeout phải áp vào lời gọi đang chạy và deadline toàn attempt.

**Sai lầm 7 — Chia sẻ ChatMemory hoặc tool fixture giữa case độc lập.** Điều này làm dữ liệu rò giữa các ca, kết quả không tái lập và có thể gây nguy cơ quyền riêng tư.

**Sai lầm 8 — Ghi kết quả theo thứ tự hoàn thành mà không có `caseId`.** Hai case kết thúc lệch thứ tự sẽ bị ghép nhầm dữ liệu.

**Sai lầm 9 — Một case lỗi khiến toàn bộ batch âm thầm mất kết quả.** Cần lưu terminal outcome và trạng thái batch `PARTIAL/ABORTED` nếu có hỏng ở runner/sink.

**Sai lầm 10 — Coi `COMPLETED` là quality PASS.** Thành công kỹ thuật chỉ có nghĩa đã tạo response; evaluator và rubric mới quyết định chất lượng.

**Sai lầm 11 — Chỉ báo average latency.** p95/p99, 429, retries và throughput cho biết hàng đợi quá tải tốt hơn một con số trung bình.

**Sai lầm 12 — So candidate dưới tải khác baseline nhưng kết luận lỗi do model.** Cần kiểm soát điều kiện thử hoặc nêu rõ giới hạn suy luận.

**Sai lầm 13 — Log nguyên văn question, prompt, completion và tool args làm metric labels.** Dễ gây cardinality cao và rò dữ liệu. Dùng nhãn hữu hạn, evidence refs và phân quyền phù hợp.

## 19. Checklist vận hành batch evaluation

- [ ] Dataset, rubric và nguồn tham chiếu có phiên bản.
- [ ] Run manifest có prompt/model/pipeline, quota và `maxInFlight`.
- [ ] Scheduler không submit số task không giới hạn vào hàng đợi.
- [ ] Các provider/model calls có concurrency limit và rate/token budget phù hợp.
- [ ] Có timeout ở model, VectorStore, tool, judge và deadline toàn case.
- [ ] Retry có giới hạn, backoff+jitter, tuân theo `Retry-After`, không retry tool nguy hiểm mù quáng.
- [ ] Từng attempt có `caseId`, `attemptId` và terminal execution status.
- [ ] Có phân biệt `COMPLETED`, `FAILED`, `INTERRUPTED` với quality PASS/FAIL.
- [ ] Mỗi case độc lập về memory, tool fixtures và dữ liệu test.
- [ ] Actual answer, context và tool events được lưu hoặc tham chiếu an toàn.
- [ ] Sink có checkpoint, run PARTIAL không bị báo thành COMPLETED.
- [ ] Judge failure và thiếu evidence được ghi `NOT_EVALUATED`.
- [ ] Metrics có throughput, concurrency, 429, latency phân vị, retries, usage/cost.
- [ ] Trace ID chỉ ghi khi có trace thật và context propagation phù hợp.
- [ ] Khi so phiên bản, giữ điều kiện tải có thể so sánh và báo mẫu số.
- [ ] Các ca lỗi có bằng chứng trở thành regression cases sau khi xác minh.

## 20. Tổng kết

**Chạy đánh giá theo lô có giới hạn đồng thời** là cách mở rộng từ vài ca kiểm thử Spring AI tới hàng nghìn ca mà vẫn kiểm soát tài nguyên và giữ khả năng truy vết. Hạt nhân của giải pháp là **bounded in-flight scheduling**, cùng với giới hạn provider calls, RPM/TPM, timeout, retry có ngân sách, cô lập trạng thái và ghi kết quả bền vững.

Một batch **nhanh** chưa chắc **đáng tin**: 429, timeout, mất ca, lẫn ngữ cảnh hoặc bộ chấm quá tải đều có thể khiến báo cáo chất lượng sai lệch. Ngược lại, một batch được tổ chức tốt cho phép xem riêng **tỷ lệ hoàn tất kỹ thuật**, **điểm relevance/fact checking/RAG/tool trên các ca đã chấm**, **độ trễ**, **token** và **chi phí**. Khi mọi verdict đều gắn với `caseId`, `attemptId`, cấu hình và trace/evidence phù hợp, nhóm có thể so sánh các phiên bản prompt, model và pipeline một cách có cơ sở.

### Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Java 21 — ExecutorCompletionService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html)
- [Java 21 — Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
