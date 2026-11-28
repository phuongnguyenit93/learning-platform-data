# Đo tỷ lệ lỗi, timeout và giới hạn tốc độ

Một trợ lý Spring AI có thể gặp nhiều kiểu suy giảm: model provider trả lỗi, tool backend phản hồi chậm, retriever bị giới hạn truy vấn hoặc người dùng gửi nhiều yêu cầu hơn năng lực xử lý. Nếu dashboard chỉ hiển thị một con số **error rate**, nhóm phát triển khó biết hệ thống đang lỗi nghiệp vụ, hết quota, bị timeout hay chủ động từ chối vì quá tải.

Ba nhóm tín hiệu cần được phân biệt:

- **Tỷ lệ lỗi (error rate):** bao nhiêu request, attempt hoặc tác vụ kết thúc với kết quả lỗi theo định nghĩa đã chọn?
- **Tỷ lệ timeout (timeout rate):** bao nhiêu thao tác vượt deadline hoặc không hoàn tất trong thời gian cho phép?
- **Tín hiệu giới hạn tốc độ (rate limiting):** bao nhiêu yêu cầu bị từ chối, trì hoãn hoặc điều tiết vì vượt giới hạn lưu lượng, token hay concurrency?

Các nhóm này có thể giao nhau nhưng không đồng nghĩa. Một request bị giới hạn tốc độ có thể được xử lý đúng chính sách; một request timeout có thể do provider chậm; một tác vụ cuối cùng thất bại có thể đã trải qua nhiều retry và nhiều loại lỗi.

Bài học này thuộc chương **Thiết kế metric** trong module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking, kiểm thử RAG và gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua các phiên bản prompt, model và pipeline. Bài này giúp thiết kế chỉ số vận hành có mẫu số rõ ràng và liên kết được với chất lượng thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt lỗi model, tool, retrieval, evaluator, timeout, rate limit và lỗi nghiệp vụ.
2. Chọn đúng đơn vị đo và mẫu số: request, attempt, user task, conversation, case-run hay business operation.
3. Tính error rate, timeout rate, throttling rate, retry rate và tỷ lệ hoàn tất theo cùng cửa sổ thời gian.
4. Thiết kế Counter, Timer, Gauge và tags hữu hạn để đo lỗi, timeout, retry, in-flight và rate limiting.
5. Hiểu tín hiệu 429, Retry-After, quota theo request/token và giới hạn concurrency.
6. Viết ví dụ Java Micrometer để ghi nhận lỗi và timeout tại ranh giới thích hợp của ứng dụng Spring AI.
7. Viết PromQL cho error rate, timeout rate, rate-limit rate, retry amplification và SLO.
8. Nhận biết retry storm, timeout chồng lớp, thiếu bằng chứng và khác biệt giữa attempt failure với task failure.
9. Kết hợp metric với traces, token usage, cost và oracle để chẩn đoán suy giảm chất lượng.

## 2. Trước tiên phải định nghĩa “lỗi”

Không phải mọi phản hồi khác 2xx đều có cùng ý nghĩa. Cũng không phải mọi câu trả lời không đạt yêu cầu đều là lỗi HTTP.

### 2.1. Phân loại theo tầng

| Tầng | Ví dụ lỗi | Bằng chứng phù hợp |
| --- | --- | --- |
| **Ứng dụng/API** | Validation, authentication, internal exception | HTTP response, exception class, request state |
| **Model/provider** | Quota exceeded, unavailable, invalid request, provider timeout | Provider response, request ID, usage/latency |
| **Tool dispatch** | Tool không tồn tại, schema arguments không hợp lệ, policy deny | Model tool request, dispatcher decision |
| **Tool execution** | Backend timeout, permission denied, dependency failure | Handler event, backend response, operation ID |
| **RAG/retrieval** | Vector store unavailable, no eligible document, search timeout | Retrieval span, query, document IDs |
| **Memory/context** | Store unavailable, conversation state conflict, context missing | Memory operation event, session metadata |
| **Evaluation** | Oracle unavailable, judge timeout, evidence missing | Evaluation runner, verdict, evaluator trace |
| **Business outcome** | Giao dịch bị từ chối, vẫn PENDING, hậu điều kiện không đạt | Source of truth và business state |

Model có thể trả lời tự tin nhưng sai trạng thái đơn hàng: đó là **quality failure** dù HTTP request thành công. Ngược lại, người dùng yêu cầu truy cập đơn không có quyền và hệ thống từ chối đúng chính sách là kết quả an toàn, không nhất thiết là lỗi chất lượng.

### 2.2. Error, timeout, rate limit và expected denial

| Kết quả | Ý nghĩa | Có phải lỗi hệ thống? |
| --- | --- | --- |
| **Success** | Thao tác hoàn tất đúng hợp đồng | Không |
| **Validation failure** | Input không đáp ứng schema/điều kiện | Thường là lỗi đầu vào; phân loại riêng |
| **Business rejection** | Nghiệp vụ từ chối theo quy tắc | Không nhất thiết |
| **Authorization denial** | Không đủ quyền | Có thể là hành vi bảo vệ đúng |
| **Provider/tool error** | Thành phần phụ thuộc trả lỗi | Thường là lỗi vận hành |
| **Timeout** | Deadline hết trước khi có kết quả hợp lệ | Thường là lỗi vận hành đối với SLO |
| **Rate limited** | Vượt giới hạn lưu lượng/quota/concurrency | Có thể là tín hiệu capacity hoặc policy |
| **Cancelled** | Công việc bị hủy theo yêu cầu hoặc deadline | Phụ thuộc lý do và hợp đồng |
| **Inconclusive** | Không đủ bằng chứng để kết luận | Không tự động là PASS hay FAIL |

Không gom tất cả vào một nhãn error=true. Hãy giữ **outcome** cho kết quả thực thi và **verdict** cho đánh giá chất lượng. Tool có thể thực thi thành công nhưng câu trả lời cuối vẫn FAIL do sai fact checking.

## 3. Chọn đúng đơn vị đo và mẫu số

Một user task trong ứng dụng Spring AI có thể tạo nhiều model calls, tool calls và retrievals. Một lần retry là một **attempt** mới nhưng không nhất thiết là một **tác vụ người dùng** mới.

| Đơn vị | Ví dụ | Câu hỏi được trả lời |
| --- | --- | --- |
| **HTTP request** | Một request vào endpoint assistant | API có trả lỗi không? |
| **Logical user task** | Người dùng yêu cầu kiểm tra đơn A123 | Tác vụ người dùng có hoàn tất không? |
| **Model request** | Một lần gọi model provider | Provider có lỗi/timeout không? |
| **Attempt** | Một lần thực thi kể cả retry | Tỷ lệ lỗi của từng lần thử là bao nhiêu? |
| **Tool call proposal** | Model đề nghị gọi tool | Model đề nghị công cụ bao nhiêu lần? |
| **Tool execution** | Dispatcher cho handler chạy | Tool backend thực thi có lỗi không? |
| **Retrieval** | Một lượt tìm tài liệu | Retriever có timeout hoặc bị throttle không? |
| **Evaluation case-run** | Một ca dataset chạy với một cấu hình | Bộ đánh giá có đủ bằng chứng và đạt không? |
| **Business operation** | Một operation ID hoàn tiền | Nghiệp vụ có hoàn tất không? |

### 3.1. Attempt error rate và task failure rate

Giả sử một user task tạo ba attempts:

~~~text
Attempt 1: provider timeout
Attempt 2: provider 429 rate limited
Attempt 3: thành công
Final task: thành công
~~~

Attempt error/throttle rate cho thấy hai lần thử không thành công trên ba attempts (cần quy định 429 thuộc nhóm nào). Logical task failure rate bằng 0 vì lần cuối đạt mục tiêu. Task latency và cost vẫn bao gồm thời gian, chi phí của những attempts trước.

Nếu chỉ báo task success, nhóm sẽ không thấy provider đang quá tải. Nếu chỉ báo attempt error, nhóm có thể kết luận nhầm rằng người dùng không nhận được kết quả. **Cần cả hai góc nhìn**.

### 3.2. Mẫu số phải khớp với tử số

\[
\text{Rate}=\frac{\text{Số sự kiện thỏa điều kiện}}{\text{Tổng số đơn vị quan sát phù hợp}}
\]

Ví dụ:

- **Model attempt error rate** = model attempts kết thúc lỗi / tổng model attempts được phân loại.
- **Tool timeout rate** = tool executions timeout / tool executions bắt đầu theo cùng contract.
- **Task failure rate** = logical tasks không đạt / logical tasks đã kết thúc.
- **Rate-limit rejection rate** = request bị từ chối do limit / request được kiểm tra limit.

Không chia **số tool timeouts** cho **số user tasks** rồi gọi đó là tool timeout rate. Không chia số PASS của evaluator cho số model calls. Nếu một ca có nhiều tool calls, mẫu số của từng tầng phải phản ánh đúng cấp đó.

### 3.3. Xử lý request đang chạy

Một request đã bắt đầu nhưng vẫn in-flight không nên bị xem là thành công. Hãy tách:

- **Started:** attempt đã bắt đầu.
- **Completed:** attempt có kết quả cuối theo contract.
- **Timed out:** attempt vượt deadline.
- **Cancelled:** attempt được hủy.
- **In-flight:** trạng thái hiện tại.
- **Unknown/missing:** không đủ event để xác định.

Có thể dùng Counter cho started/completed/timeout và Gauge cho in-flight. Khi tính tỷ lệ, cần nêu rõ đang dùng **completed attempts** hay **started attempts** và cách xử lý attempts còn mở trong cửa sổ.

## 4. Công thức error rate, timeout rate và throttling rate

Các công thức sau là mẫu; thay tên và mẫu số theo contract thực tế của hệ thống.

### 4.1. Error rate theo attempt

\[
\text{Attempt error rate}=\frac{N_\text{error}}{N_\text{classified attempts}}
\]

Nếu timeout và rate limit được ghi thành outcome riêng, cần quyết định rõ chúng có nằm trong error rate tổng hay được báo riêng:

~~~text
attempt_failure_rate = (error + timeout + cancelled) / classified_attempts
provider_throttle_rate = rate_limited_attempts / provider_attempts
~~~

Đừng cộng các nhóm có thể chồng lấp nếu một attempt vừa timeout ở client vừa có provider response 429 đến muộn. Mỗi attempt nên có **một outcome cuối chính**, còn tín hiệu phụ có thể ghi riêng.

### 4.2. Task failure rate

\[
\text{Task failure rate}=\frac{N_\text{failed logical tasks}}{N_\text{completed logical tasks}}
\]

Một task chỉ được phân loại sau khi đạt success, failure, deadline cuối hoặc trạng thái cuối theo hợp đồng. Nếu tác vụ bất đồng bộ kéo dài, không coi PENDING là success; có thể báo **pending age** và tỷ lệ completion riêng.

### 4.3. Timeout rate

\[
\text{Timeout rate}=\frac{N_\text{timed out attempts}}{N_\text{started attempts eligible for timeout}}
\]

Mẫu số nên bao gồm attempts đã bắt đầu và có đủ thời gian đi tới deadline. Nếu lấy tất cả request mới bắt đầu ở cuối cửa sổ, chúng chưa có cơ hội timeout; timeout rate có thể thấp giả. Với báo cáo offline, có thể chờ tất cả ca kết thúc hoặc áp dụng cửa sổ quan sát cố định.

### 4.4. Rate-limit rejection rate

\[
\text{Rate-limit rate}=\frac{N_\text{requests rejected by limiter}}{N_\text{requests evaluated by limiter}}
\]

Nên phân biệt:

- **Application limiter:** giới hạn do hệ thống của bạn áp dụng.
- **Provider limiter:** giới hạn do model provider hoặc dịch vụ ngoài trả về.
- **Concurrency limiter:** từ chối hoặc trì hoãn vì số công việc đồng thời vượt ngưỡng.
- **Token/quota limiter:** vượt token-per-minute, request-per-minute hoặc quota theo tài khoản.

Yêu cầu bị application limiter từ chối trước khi gọi provider không phải provider 429. Nếu hai loại bị gộp, nhóm không biết nên tăng năng lực nội bộ, điều chỉnh quota provider hay giữ nguyên chính sách bảo vệ.

### 4.5. Retry amplification

\[
\text{Attempts per logical task}=\frac{\text{Tổng số attempts}}{\text{Số logical tasks}}
\]

Nếu trung bình tăng từ 1,1 lên 2,8, hệ thống có thể đang retry quá nhiều, provider throttling hoặc timeout. Chỉ số này không tự kết luận lỗi, nhưng giúp phát hiện **retry amplification** làm tăng latency và cost.

## 5. Timeout: định nghĩa deadline và đo đúng tầng

Timeout không chỉ là “Timer lâu hơn bình thường”. Timeout là **quyết định dừng chờ hoặc hủy thao tác khi vượt deadline**. Cần xác định deadline thuộc lớp nào.

### 5.1. Các timeout thường gặp

| Timeout | Phạm vi | Ví dụ |
| --- | --- | --- |
| Client/request timeout | Người gọi chờ ứng dụng | API gateway đóng request sau 10 s |
| Application task deadline | Toàn bộ tác vụ assistant | Tác vụ có tối đa 8 s |
| Model/provider timeout | Một model request | Provider call có timeout 5 s |
| Tool connect timeout | Thiết lập kết nối tới backend | Kết nối không mở trong 500 ms |
| Tool read/response timeout | Chờ phản hồi sau kết nối | Backend không trả dữ liệu trong 2 s |
| Retrieval timeout | Một lượt tìm kiếm RAG | Vector store không trả trong 1 s |
| Evaluation timeout | Một lần chấm/judge | Evaluator không trả trong 4 s |
| Business deadline | Hậu điều kiện nghiệp vụ | Giao dịch phải hoàn tất trước một mốc riêng |

**Deadline của task thường phải lớn hơn hoặc bằng ngân sách của các bước bên trong**, có tính đến số lần gọi và overhead. Nếu mỗi model request có timeout 8 s, nhưng task deadline là 5 s, request có thể bị hủy trước khi provider timeout.

### 5.2. Timeout lồng nhau

~~~mermaid
flowchart TD
    A["Task deadline: 8 s"] --> B["Model request budget: 4 s"]
    B --> C["Tool execution budget: 2 s"]
    C --> D["Backend connect: 300 ms"]
    C --> E["Backend read: 1.5 s"]
    A --> F["Final response assembly"]
~~~

Đây là cấu trúc minh họa. Khi thiết kế thật, phải tính **thời gian còn lại** trước mỗi bước; không cấp lại toàn bộ timeout cho mỗi retry nếu điều đó làm tổng task vượt deadline. Nếu một bước đã dùng 6 giây trong task 8 giây, bước kế tiếp không thể được cấp thêm 8 giây mà vẫn giữ cam kết end-to-end.

### 5.3. Ghi thời lượng timeout

Nếu attempt bắt đầu lúc t=0 và bị deadline ở t=2 s:

- Có thể ghi Timer **2 s** với outcome=timeout nếu Timer đo từ start đến lúc hệ thống tuyên bố timeout.
- Ghi Counter timeout +1.
- Giảm Gauge in-flight khi công việc được hủy/đóng ở đúng vòng đời.
- Nếu backend tiếp tục chạy dù client đã timeout, ghi nhận **orphan/background execution** riêng nếu có thể quan sát.

Không ghi **0 ms** vì không nhận được response. Không gọi thao tác đã timeout là thành công chỉ vì server gửi response sau khi client ngừng chờ.

### 5.4. Timeout và cancellation khác nhau

Một request có thể bị hủy vì người dùng đóng trang, parent task hết deadline, server shutdown, circuit breaker dừng hoặc provider/tool tự hủy. Không phải mọi cancellation đều là timeout. Dùng outcome hữu hạn như **success, error, timeout, cancelled, rate_limited**; thêm cancel_reason nếu cần và giới hạn giá trị.

### 5.5. Timeout không có response và thiếu quan sát

Nếu client timeout nhưng không có event xác nhận server dừng, **không thể suy ra backend không thực hiện hành động**. Với thao tác ghi dữ liệu, phải kiểm tra operation ID hoặc trạng thái source of truth trước khi retry để tránh tác động trùng. Timeout metric cần liên kết với idempotency và audit.

## 6. Rate limiting: giới hạn request, token và concurrency

Rate limiting là cơ chế điều tiết lưu lượng để bảo vệ hệ thống, đáp ứng quota hoặc chia sẻ tài nguyên công bằng. Trong một ứng dụng Spring AI, giới hạn có thể xuất hiện ở **API gateway**, **ứng dụng**, **model provider**, **retriever**, hoặc **backend tool**.

### 6.1. Các loại giới hạn

| Loại giới hạn | Đại lượng | Ví dụ |
| --- | --- | --- |
| Request rate | Requests per second/minute | 60 requests/minute |
| Token rate | Input/output tokens per minute | TPM quota của model provider |
| Concurrency | Số tác vụ đang chạy cùng lúc | Tối đa 20 model calls đồng thời |
| Tenant/user quota | Mức sử dụng theo tenant hoặc plan | Tenant A được 10.000 calls/ngày |
| Resource budget | CPU, connection pool, queue capacity | Giới hạn số truy vấn vector store |
| Business quota | Hành động nghiệp vụ theo chu kỳ | Số yêu cầu hoàn tiền trong ngày |

Không gộp mọi loại thành một metric rate_limit. Nếu provider trả 429 do TPM, giải pháp có thể là giảm token context hoặc phân phối request; nếu app limiter từ chối do concurrency, cần xem worker pool, queue và tải; nếu tenant hết quota, phải áp dụng chính sách sản phẩm.

### 6.2. HTTP 429 và Retry-After

HTTP **429 Too Many Requests** thường biểu thị client đã gửi quá nhiều request trong một khoảng thời gian. Response có thể kèm **Retry-After** để gợi ý thời điểm thử lại; giá trị có thể được biểu diễn theo số giây hoặc HTTP-date tùy giao thức và server.

Nhưng cần xác định **ai trả 429**:

- API gateway của ứng dụng từ chối trước khi vào service.
- Application limiter từ chối request.
- Model provider trả 429.
- Tool backend hoặc dịch vụ RAG trả 429.

Ghi nguồn limit thành một tag hữu hạn, ví dụ **limiter_source=application|provider|retriever|tool_backend**. Không đưa URL đầy đủ, tenant ID hoặc response body tùy ý vào tag.

Một 429 có thể là **hành vi bảo vệ mong đợi**, không nhất thiết là lỗi code. Nhưng tỷ lệ 429 tăng cao vẫn là tín hiệu vận hành cần cảnh báo, vì người dùng có thể không hoàn thành được tác vụ.

### 6.3. Token quota quan trọng với model

Model provider có thể giới hạn theo:

- Requests per minute (RPM).
- Tokens per minute (TPM), có thể tính input và output theo quy định provider.
- Quota theo model, project, organization hoặc tài khoản.
- Concurrent requests hoặc các giới hạn khác theo hợp đồng.

Một prompt dài có thể tiêu thụ nhiều token hơn và chạm TPM dù số request/second không tăng. Do đó, dashboard cần xem **requests**, **input/output tokens**, **rate-limit responses** và **model family** cùng nhau.

Nếu token usage không được provider trả về, không tự suy ra usage chính xác từ số ký tự. Có thể ghi estimated token count thành một metric khác có tên rõ là estimated, nhưng không trộn với provider-reported usage.

### 6.4. Token bucket, fixed window và concurrency limiter

Các thuật toán giới hạn có hành vi khác nhau:

| Cơ chế | Cách hoạt động khái quát | Tín hiệu cần theo dõi |
| --- | --- | --- |
| Fixed window | Đếm số request trong từng cửa sổ cố định | Requests/window, rejected |
| Sliding window | Tính lưu lượng trong cửa sổ trượt | Request rate, rejected |
| Token bucket | Token được nạp lại theo tốc độ; request tiêu thụ token | Available tokens, denied, wait |
| Leaky bucket | Xử lý theo tốc độ thoát được giới hạn | Queue depth, drain rate, overflow |
| Semaphore/concurrency limiter | Giới hạn số thao tác đồng thời | In-flight, permit acquired/denied |

Ví dụ token bucket có dung lượng 100 token và nạp 10 token/giây. Một đợt request có thể tiêu thụ nhanh 100 token rồi bị từ chối cho đến khi bucket được nạp lại. Vì vậy, một spike ngắn có thể tạo 429 ngay cả khi **rate trung bình 1 phút** trông thấp.

### 6.5. Phân biệt từ chối ngay và chờ trong queue

Rate limiter có thể:

1. **Reject:** từ chối ngay, thường trả 429 hoặc lỗi nội bộ tương đương.
2. **Delay:** giữ request và cho phép khi đủ quota.
3. **Queue:** xếp hàng chờ worker hoặc token.
4. **Degrade:** chọn model/tool khác hoặc giảm mức dịch vụ theo policy.

Chỉ đo số lần bị từ chối sẽ bỏ qua thời gian chờ và backlog. Nếu limiter xếp hàng, cần đo **queue wait duration**, **queue depth**, **oldest task age** và số tác vụ hết deadline khi đang chờ.

## 7. Retry và backoff: kiểm soát thay vì khuếch đại lỗi

Retry giúp vượt qua lỗi tạm thời nhưng có thể làm sự cố nặng hơn nếu nhiều request đồng loạt thử lại.

### 7.1. Retry storm

Giả sử provider bị quá tải và 1.000 request cùng nhận 429. Nếu tất cả retry sau đúng 1 giây, chúng có thể tạo thêm một đợt 1.000 request mới đúng thời điểm quota chưa phục hồi. Điều này làm tăng:

- Số provider attempts.
- Input/output tokens và chi phí.
- Thời gian hoàn tất user task.
- Số request in-flight và queue depth.
- Tỷ lệ timeout ở các lớp phía trên.

Đây là **retry amplification** hoặc retry storm. Một dashboard chỉ nhìn số task cuối cùng thành công có thể bỏ qua chi phí và áp lực mà retry gây ra.

### 7.2. Exponential backoff và jitter

Một chiến lược thường dùng là tăng khoảng chờ theo cấp số nhân:

\[
d_n=\min(d_{\max},d_0\times 2^n)
\]

Trong đó d0 là thời gian chờ ban đầu, n là số lần retry và dmax là giới hạn trên. Có thể thêm **jitter** (ngẫu nhiên có giới hạn) để tránh nhiều client retry đồng bộ.

Nếu provider gửi Retry-After hợp lệ, cần tuân theo chính sách của provider và giới hạn trong deadline tổng thể. Không retry ngay liên tục khi response đã cho biết quota chưa sẵn sàng.

### 7.3. Không retry mọi lỗi

| Loại lỗi | Hành động thường phù hợp |
| --- | --- |
| 429 rate limited | Chờ theo Retry-After/backoff, kiểm tra quota |
| 502/503/504 tạm thời | Có thể retry có giới hạn nếu thao tác an toàn |
| Connect reset/transient network | Có thể retry với budget và idempotency |
| 400 invalid request/schema | Sửa dữ liệu hoặc prompt; không retry mù |
| 401/403 | Kiểm tra credentials/quyền; không retry liên tục |
| Business rejection | Theo quy tắc nghiệp vụ; thường không retry tự động |
| Timeout của thao tác ghi | Kiểm tra trạng thái operation trước khi retry |
| Model output sai fact | Đây là quality failure; retry không bảo đảm sửa được |

Với tool ghi dữ liệu, retry chỉ an toàn khi có **idempotency key** hoặc cơ chế xác minh trạng thái để không tạo tác động trùng. Một timeout không chứng minh backend chưa nhận lệnh.

### 7.4. Retry budget

Đặt giới hạn:

- Số attempts tối đa cho mỗi logical task.
- Tổng thời gian retry không vượt task deadline.
- Tổng token/cost có thể tiêu thụ cho một task.
- Loại lỗi được phép retry.
- Số retry đồng thời hoặc retry budget theo service/tenant.

Theo dõi riêng **attempts per task**, **retry count per task**, **retry success rate** và **task failure rate**. Nếu chỉ đo provider error rate mà không đo retry, khó thấy việc một lỗi nhỏ đang bị khuếch đại.

## 8. Thiết kế metric cho lỗi, timeout và rate limiting

Tên dưới đây là ví dụ custom metric của ứng dụng. Cần kiểm tra những meter tương đương đã có trong Spring Boot/Spring AI/Micrometer để tránh ghi trùng.

| Tên logic | Loại meter | Đơn vị/ý nghĩa | Tags hữu hạn gợi ý |
| --- | --- | --- | --- |
| app.ai.request.started | Counter | Số logical requests bắt đầu | component, route_family |
| app.ai.request.completed | Counter | Số logical requests có kết quả cuối | outcome |
| app.ai.request.duration | Timer | Thời gian end-to-end | outcome |
| app.ai.attempt.completed | Counter | Số attempts đã kết thúc | component, outcome |
| app.ai.attempt.duration | Timer | Thời lượng mỗi attempt | component, outcome |
| app.ai.model.request.failed | Counter | Số model attempts lỗi | model_group, error_class |
| app.ai.model.request.timeout | Counter | Số model attempts timeout | model_group |
| app.ai.tool.execution.failed | Counter | Số tool executions lỗi | tool_family, error_class |
| app.ai.tool.execution.timeout | Counter | Số tool executions timeout | tool_family |
| app.ai.rag.retrieval.timeout | Counter | Số retrieval timeout | source_family |
| app.ai.rate_limit.decision | Counter | Số quyết định allowed/rejected của limiter | limiter_source, limit_type, decision |
| app.ai.provider.rate_limit.response | Counter | Số provider rate-limit responses | provider_group, model_group |
| app.ai.retry.attempt | Counter | Số retry attempts | component, reason |
| app.ai.retry.per_task | DistributionSummary | Số retry trên mỗi logical task | route_family |
| app.ai.request.inflight | Gauge | Request hiện đang xử lý | route_family |
| app.ai.rate_limit.queue.depth | Gauge | Số request đang chờ | limiter_source |
| app.ai.rate_limit.queue.wait | Timer | Thời gian chờ quota/queue | limiter_source |

### 8.1. Một attempt chỉ có một outcome chính

Đối với một tool attempt, outcome cuối có thể là:

~~~text
success | error | timeout | rate_limited | cancelled
~~~

Nếu vừa có timeout ở client vừa có response 429 đến muộn, cần quyết định outcome chính theo điểm kết thúc của attempt và ghi thêm signal phụ nếu cần. Không tăng hai Counter outcome rồi cộng chúng vào một mẫu số chung như thể đó là hai attempts.

### 8.2. Tags phải giới hạn cardinality

Có thể dùng:

- component: model, tool, retrieval, evaluator.
- error_class: validation, auth, transient, provider, business, unknown.
- outcome: success, error, timeout, rate_limited, cancelled.
- limiter_source: application, provider, retriever, tool_backend.
- limit_type: rpm, tpm, concurrency, tenant_quota, queue_capacity.
- model_group/tool_family: các nhóm được quản lý.

Không dùng raw prompt, user_id, tenant ID, order ID, conversation ID, trace ID, provider request ID hoặc exception message làm metric tag. Chi tiết riêng lẻ thuộc traces/logs có kiểm soát; metrics dùng để tổng hợp.

### 8.3. Không đếm trùng giữa Timer và Counter

Timer thường đã cung cấp count số lần ghi. Nếu chỉ cần số tool executions và thời lượng, Timer có thể đủ. Tạo Counter riêng khi nó biểu diễn một sự kiện khác, ví dụ **model đề nghị tool**, **dispatcher từ chối**, **provider trả 429** hoặc **business outcome đã xác minh**.

Counter request.started và request.completed có thể hữu ích để đo lifecycle; nhưng phải định nghĩa rõ khi nào request được xem là started và khi nào completed. Gauge in-flight nên được cập nhật đúng vòng đời, kể cả nhánh lỗi/cancel.

## 9. Ví dụ Java Micrometer: ghi attempt, timeout, rate limit và retry

Ví dụ sau tạo bộ ghi nhận ở ranh giới quan sát của ứng dụng. Nó không tự quyết định retry, không thay thế model provider hoặc tool dispatcher. Lớp gọi phải cung cấp **outcome đã phân loại**, duration thực tế và các quyết định rate limiter.

~~~java
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class AiFailureMeters {

    public enum Outcome {
        SUCCESS, ERROR, TIMEOUT, RATE_LIMITED, CANCELLED
    }

    private final MeterRegistry registry;
    private final AtomicInteger inFlight = new AtomicInteger();

    public AiFailureMeters(MeterRegistry registry) {
        this.registry = registry;

        Gauge.builder("app.ai.request.inflight",
                        inFlight, AtomicInteger::get)
                .description("Logical requests currently in progress")
                .baseUnit("requests")
                .register(registry);
    }

    private static String component(String raw) {
        return switch (raw) {
            case "model", "tool", "retrieval", "evaluator" -> raw;
            default -> "other";
        };
    }

    private static String limiterSource(String raw) {
        return switch (raw) {
            case "application", "provider",
                    "retriever", "tool_backend" -> raw;
            default -> "other";
        };
    }

    private static String limitType(String raw) {
        return switch (raw) {
            case "rpm", "tpm", "concurrency",
                    "tenant_quota", "queue_capacity" -> raw;
            default -> "other";
        };
    }

    // Một sample cho mỗi attempt đã kết thúc.
    // Timer count có thể làm mẫu số cho attempt-level rate.
    public void recordAttemptResult(
            String rawComponent,
            Outcome outcome,
            Duration elapsed
    ) {
        String part = component(rawComponent);
        String result = outcome.name().toLowerCase(Locale.ROOT);

        Timer.builder("app.ai.attempt.duration")
                .description("Duration of a completed component attempt")
                .tag("component", part)
                .tag("outcome", result)
                .register(registry)
                .record(elapsed);

        Counter.builder("app.ai.attempt.completed")
                .description("Completed attempts by component and outcome")
                .baseUnit("attempts")
                .tag("component", part)
                .tag("outcome", result)
                .register(registry)
                .increment();
    }

    // Ghi một quyết định limiter; mẫu số gồm cả allowed và rejected.
    public void recordLimiterDecision(
            String rawSource,
            String rawLimitType,
            boolean rejected
    ) {
        Counter.builder("app.ai.rate_limit.decision")
                .description("Rate limiter decisions")
                .baseUnit("decisions")
                .tag("limiter_source", limiterSource(rawSource))
                .tag("limit_type", limitType(rawLimitType))
                .tag("decision", rejected ? "rejected" : "allowed")
                .register(registry)
                .increment();
    }

    public void recordRetry(String rawComponent, String reason) {
        String part = component(rawComponent);
        String retryReason = switch (reason) {
            case "timeout", "rate_limited", "transient_error" -> reason;
            default -> "other";
        };

        Counter.builder("app.ai.retry.attempt")
                .description("Additional attempts caused by retry policy")
                .baseUnit("attempts")
                .tag("component", part)
                .tag("reason", retryReason)
                .register(registry)
                .increment();
    }

    public <T> T observeLogicalRequest(Callable<T> operation)
            throws Exception {
        inFlight.incrementAndGet();
        try {
            return operation.call();
        } finally {
            inFlight.decrementAndGet();
        }
    }

    public int currentInFlight() {
        return inFlight.get();
    }
}
~~~

### 9.1. Gọi recorder tại ranh giới đúng

~~~java
import java.time.Duration;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

var registry = new SimpleMeterRegistry();
var meters = new AiFailureMeters(registry);

// Model request đã kết thúc do provider timeout sau 4 giây.
meters.recordAttemptResult(
        "model",
        AiFailureMeters.Outcome.TIMEOUT,
        Duration.ofSeconds(4));

// Provider rate limit là một outcome riêng.
meters.recordAttemptResult(
        "model",
        AiFailureMeters.Outcome.RATE_LIMITED,
        Duration.ofMillis(40));

// Retry được ghi như một attempt bổ sung, không phải task mới.
meters.recordRetry("model", "rate_limited");

// Application limiter đã kiểm tra và từ chối request.
meters.recordLimiterDecision(
        "application", "concurrency", true);

// Một request khác được limiter cho phép.
meters.recordLimiterDecision(
        "application", "concurrency", false);
~~~

**Lưu ý quan trọng:**

- Nếu limiter từ chối request trước khi có model/tool attempt, ghi **limiter decision**; không tạo model attempt giả.
- Nếu provider trả 429, ghi attempt outcome **RATE_LIMITED** và provider limiter signal nếu cần. Không coi đó là application limiter.
- Mỗi attempt đã kết thúc ghi một Timer và một Counter cùng sự kiện; hai meter này có chủ đích dùng cho hai loại truy vấn khác nhau. Nếu chỉ cần count, Timer đã có count và Counter có thể bỏ.
- Request in-flight được giảm trong finally. Với tác vụ bất đồng bộ, chỉ giảm khi Future/Publisher hoặc worker thực sự kết thúc theo hợp đồng.
- Trong thực tế nên chuẩn hóa outcome/error taxonomy ở một lớp duy nhất; không lấy exception message tùy ý làm tag.

### 9.2. Vì sao không ghi trực tiếp user ID và provider request ID?

Metrics được dùng để tổng hợp. Nếu mỗi user hoặc request tạo một label riêng, số time series sẽ tăng rất nhanh. Dùng tags như **component, outcome, limiter_source, limit_type**; giữ **trace ID, provider request ID, conversation ID và operation ID** trong trace/log/audit có phân quyền.

## 10. PromQL cho error rate, timeout và rate limiting

Các truy vấn dưới đây dùng tên series **giả định** theo quy ước Micrometer Prometheus phổ biến. Tên thực tế phụ thuộc base unit, registry, exporter và phiên bản; phải kiểm tra scrape endpoint trước khi sử dụng.

### 10.1. Attempt error rate

Giả sử Counter được xuất thành series tương tự **app_ai_attempt_completed_attempts_total**:

~~~promql
sum(rate(
  app_ai_attempt_completed_attempts_total{
    outcome=~"error|timeout|rate_limited|cancelled"
  }[5m]
))
/
sum(rate(
  app_ai_attempt_completed_attempts_total[5m]
))
~~~

Kết quả là tỷ lệ attempt kết thúc với outcome không thành công trong cửa sổ 5 phút. Nếu business muốn coi rate_limited là tín hiệu riêng và không đưa vào error budget, bỏ nó khỏi biểu thức error rate nhưng giữ panel throttling riêng.

### 10.2. Timeout rate theo component

~~~promql
sum by (component) (
  rate(app_ai_attempt_completed_attempts_total{outcome="timeout"}[5m])
)
/
sum by (component) (
  rate(app_ai_attempt_completed_attempts_total[5m])
)
~~~

Tử và mẫu đều đếm **attempts đã kết thúc**. Nếu muốn tỷ lệ timeout trên mọi attempt đã bắt đầu, cần có metric started và xử lý các attempt còn in-flight hoặc chưa đến deadline. Không trộn hai mẫu số.

### 10.3. Task failure rate

Nếu ứng dụng có Counter riêng cho logical request với tag outcome:

~~~promql
sum(rate(
  app_ai_request_completed_requests_total{
    outcome=~"error|timeout|rate_limited|cancelled"
  }[5m]
))
/
sum(rate(
  app_ai_request_completed_requests_total[5m]
))
~~~

Đây là **task-level unsuccessful rate**, không phải attempt-level error rate. Ví dụ đang coi error, timeout, rate_limited và cancelled là kết quả không thành công; điều chỉnh tập outcome theo SLO và chính sách sản phẩm. Một task có thể có nhiều attempts nhưng chỉ có một kết quả cuối.

### 10.4. Rate-limit rejection rate

Với metric limiter decision có hai giá trị allowed/rejected:

~~~promql
sum(rate(
  app_ai_rate_limit_decision_decisions_total{decision="rejected"}[5m]
))
/
sum(rate(
  app_ai_rate_limit_decision_decisions_total[5m]
))
~~~

Phân theo nguồn:

~~~promql
sum by (limiter_source, limit_type) (
  rate(app_ai_rate_limit_decision_decisions_total{
    decision="rejected"
  }[5m])
)
/
sum by (limiter_source, limit_type) (
  rate(app_ai_rate_limit_decision_decisions_total[5m])
)
~~~

Đây là tỷ lệ từ chối trong số các quyết định được limiter ghi nhận. Provider HTTP 429 có thể cần một Counter riêng nếu nó không đi qua cùng decision hook của application limiter.

### 10.5. Retry amplification

Giả sử có Counter **app_ai_request_started_requests_total** và **app_ai_retry_attempt_attempts_total**:

~~~promql
sum(rate(app_ai_retry_attempt_attempts_total[5m]))
/
sum(rate(app_ai_request_started_requests_total[5m]))
~~~

Kết quả là **retry attempts trên mỗi logical request bắt đầu** trong cửa sổ. Nó không phải tỷ lệ task thất bại. Cần xác định metric retry chỉ đếm **attempt bổ sung**, không đếm attempt đầu tiên.

### 10.6. In-flight requests

~~~promql
sum(app_ai_request_inflight_requests)
~~~

Gauge này là số logical requests đang xử lý tại thời điểm scrape. Nếu queue depth tăng cùng timeout rate, có thể hệ thống đang quá tải hoặc một dependency chậm. Nhưng Gauge không cho biết số request đã hoàn tất trong cửa sổ.

### 10.7. Error budget theo SLO

Giả sử SLO yêu cầu **99% logical requests** kết thúc thành công. Một biểu thức success ratio:

~~~promql
sum(rate(
  app_ai_request_completed_requests_total{outcome="success"}[5m]
))
/
sum(rate(
  app_ai_request_completed_requests_total[5m]
))
~~~

Error ratio là **1 - success ratio** nếu tất cả kết quả cuối được phân loại đầy đủ. Phải quyết định business rejection, expected denial và rate limit có nằm trong denominator/error budget hay không; quy tắc này phụ thuộc hợp đồng sản phẩm.

### 10.8. Xử lý mẫu số bằng 0

Trong cửa sổ không có request, rate có thể không có dữ liệu hoặc phép chia không xác định. Dashboard nên thể hiện **N/A/no traffic**, không tự gán error rate=0% hoặc success rate=100%. Không có lưu lượng không chứng minh hệ thống khỏe.

## 11. Thiết kế cảnh báo có ý nghĩa

Một cảnh báo tốt phải cho biết **điều gì đang hỏng, ở cấp nào, ảnh hưởng ra sao và cần kiểm tra đâu**. Không nên chỉ gửi cảnh báo chung chung “error rate cao” khi chưa xác định mẫu số và nhóm lỗi.

### 11.1. Các nhóm cảnh báo nên tách

| Cảnh báo | Tín hiệu | Ý nghĩa cần điều tra |
| --- | --- | --- |
| Logical task failure tăng | Task failure rate | Người dùng không hoàn thành được tác vụ |
| Model provider errors tăng | Model attempt error rate | Provider, credential, request schema hoặc network |
| Model timeout tăng | Model timeout rate + model latency | Provider chậm, prompt/token lớn, deadline không phù hợp |
| Tool timeout tăng | Tool timeout theo tool_family | Backend/tool cụ thể hoặc connection pool |
| Retrieval timeout tăng | Retrieval timeout + queue | Vector store, index, network hoặc quá tải |
| Provider throttling tăng | Provider 429 rate + token usage | RPM/TPM quota hoặc phân phối tải |
| App limiter reject tăng | Application limiter decision | Capacity, concurrency policy hoặc burst traffic |
| Retry amplification tăng | Retries/logical task | Retry storm và chi phí tăng |
| In-flight/queue tăng liên tục | Gauge + oldest age | Backlog, worker thiếu hoặc dependency bị treo |
| Quality failure tăng | Oracle FAIL, fact checking, relevance | Câu trả lời sai dù request có thể không lỗi kỹ thuật |

### 11.2. Không cảnh báo theo một mẫu đơn lẻ

Một timeout duy nhất trong môi trường thử nghiệm ít lưu lượng có thể không đáng báo động. Một tỷ lệ 429 tăng trong vài phút với hàng nghìn request có thể rất nghiêm trọng. Alert nên cân nhắc:

- **Tỷ lệ** và **số lượng tuyệt đối**.
- Cỡ mẫu tối thiểu.
- Thời gian duy trì điều kiện.
- Mức độ quan trọng của component/route.
- Error budget còn lại và mức ảnh hưởng tới người dùng.
- Có hay không một đợt deploy hoặc thay đổi quota gần thời điểm đó.

Ví dụ: cảnh báo khi model timeout rate vượt 5% trong 10 phút **và** có ít nhất 50 attempts. Đây chỉ là ví dụ; ngưỡng phải được chọn theo SLO, tải thực và mức độ rủi ro của ứng dụng.

### 11.3. Error budget và rate-limit policy

Nếu SLO là 99% task thành công, error budget là 1% logical tasks theo cửa sổ đánh giá. Nhưng một application limiter có thể từ chối đúng chính sách để bảo vệ hệ thống. Product team cần quyết định:

- Request bị limiter từ chối có được tính là **bad event** đối với SLO người dùng không?
- Request vượt quota do tenant đã dùng hết plan có được tính như lỗi dịch vụ không?
- Provider 429 có được tính vào reliability của hệ thống tổng thể không?
- Request bị từ chối đúng policy nhưng người dùng được thông báo rõ có được xem là task hoàn tất theo contract không?

Không có câu trả lời chung cho mọi sản phẩm. Điều bắt buộc là **định nghĩa trước và giữ nhất quán**; đừng loại những lỗi khó chịu khỏi mẫu số chỉ để dashboard đẹp hơn.

## 12. Retry, backoff và deadline trong một pipeline Spring AI

Một pipeline có thể gọi model nhiều lần: model yêu cầu tool, tool lỗi tạm thời, hệ thống retry tool, rồi model tiếp tục tổng hợp. Retry phải nằm trong **ngân sách thời gian, số lần và chi phí** của task.

### 12.1. Retry budget phải trừ vào deadline tổng

Ví dụ task deadline 8 giây:

~~~text
Task deadline: 8 s
  Model request 1: 1.2 s
  Tool attempt 1: 2.0 s (timeout)
  Backoff: 0.5 s
  Tool attempt 2: 1.0 s (success)
  Model request 2: 1.4 s
  Response assembly: 0.3 s
Total: 6.4 s
Remaining: 1.6 s
~~~

Nếu bước kế tiếp cần 3 giây, task đã không còn đủ budget. Không cấp lại timeout đầy đủ cho mỗi lần retry; trước mỗi attempt hãy tính **remaining deadline**.

### 12.2. Exponential backoff và jitter

\[
d_n=\min(d_{\max},d_0\times 2^n)
\]

Jitter thêm biến thiên ngẫu nhiên trong một miền được định nghĩa để các client không retry đồng bộ. Khi provider trả **Retry-After**, hãy tôn trọng giá trị hợp lệ theo chính sách và deadline còn lại; không retry sớm hơn chỉ vì backoff nội bộ nhỏ hơn.

### 12.3. Không retry mọi lỗi

| Loại lỗi | Hướng xử lý thường phù hợp |
| --- | --- |
| 429 rate limited | Chờ Retry-After/backoff, kiểm tra RPM/TPM/quota |
| 502/503/504 tạm thời | Có thể retry có giới hạn nếu thao tác an toàn |
| Network reset/transient | Có thể retry với budget và idempotency |
| 400 invalid request/schema | Sửa input/schema/prompt; không retry mù |
| 401/403 | Kiểm tra credential/quyền; không retry liên tục |
| Business rejection | Theo quy tắc nghiệp vụ; thường không retry tự động |
| Timeout của thao tác ghi | Kiểm tra operation state trước khi retry |
| Model trả lời sai fact | Quality failure; retry không bảo đảm sửa được |

### 12.4. Idempotency khi tool ghi dữ liệu

Một lệnh hủy đơn hoặc hoàn tiền có thể đã được backend tiếp nhận nhưng response bị mất. Nếu client retry mà không có idempotency key, backend có thể tạo hai tác động. Trước khi retry:

1. Giữ operation ID hoặc idempotency key xuyên suốt attempts.
2. Truy vấn trạng thái source of truth nếu kết quả lần trước không rõ.
3. Chỉ retry khi operation có thể thực hiện an toàn theo contract.
4. Phân biệt **request accepted**, **operation pending** và **verified completed**.
5. Ghi duplicate effect nếu có, không chỉ ghi HTTP error.

### 12.5. Retry không nên che lỗi chất lượng

Nếu model chọn sai tool hoặc trả câu trả lời không grounded, chạy lại model nhiều lần có thể làm tăng chi phí nhưng không giải quyết nguyên nhân. Đặt metric riêng cho số model turns, tool attempts, retries và retrievals trên mỗi logical task; đo tỷ lệ PASS sau retry, cost và latency trên mỗi verified success.

## 13. Liên hệ metrics với Spring AI: model, tool, RAG và evaluator

Spring AI có abstraction cho ChatClient, model, tool calling và các thành phần dữ liệu; instrumentation có thể tích hợp qua hệ sinh thái Micrometer Observation. Tuy nhiên, **tên observation, tag và phạm vi đo cụ thể phụ thuộc phiên bản và cấu hình**. Những custom metric trong bài là ví dụ của ứng dụng, không phải danh sách mặc định.

### 13.1. Model/provider

Theo dõi attempts, outcome, provider errors, timeout theo model group, rate-limit responses (đặc biệt 429), input/output token usage nếu provider trả dữ liệu đáng tin và model latency.

Nếu model request lỗi, ghi provider response/error class ở span hoặc log có kiểm soát. Không lưu raw API key, prompt riêng tư hay response nhạy cảm vào metric label.

### 13.2. Tool calling

Phân biệt ba sự kiện:

1. **Proposed:** model đề nghị gọi tool.
2. **Dispatched/denied:** policy/dispatcher cho phép hoặc từ chối.
3. **Executed:** handler thực sự chạy và trả kết quả.

Một tool call bị từ chối do quyền không phải tool execution timeout. Một tool execution thành công không chứng minh nghiệp vụ hoàn tất. Đo Timer ở handler và Counter cho dispatch decision, timeout, permission denial, verified outcome theo ngữ nghĩa riêng.

### 13.3. RAG/retrieval

Theo dõi retrieval attempts, timeout và dependency errors; rate limit từ vector store/search provider; số documents/chunks trả về; retrieval latency và queue wait; relevance, source freshness, groundedness và fact checking ở tầng evaluator.

**No result** không tự động là retrieval error. Có thể không có tài liệu phù hợp. Phân biệt empty result hợp lệ với lỗi truy vấn hoặc source unavailable.

### 13.4. Evaluation runner

Oracle/judge cũng là dependency có thể lỗi hoặc timeout. Không đánh dấu **FAIL về chất lượng** chỉ vì evaluator không trả kết quả; trường hợp này nên là **INCONCLUSIVE/EVALUATOR_ERROR** theo contract.

Ghi số case-run hoàn tất theo verdict, evaluator errors/timeouts, số claim được chấm và claim thiếu evidence, thời gian/cost của evaluator nếu dùng model judge. Dataset version, rubric version và evaluator version nên được lưu trong metadata run, không tạo tag vô hạn.

## 14. Ví dụ chẩn đoán qua một sự cố

Sau khi deploy prompt mới, người dùng phản ánh trợ lý đôi khi không trả lời. Dashboard cho thấy:

| Chỉ số | Trước deploy | Sau deploy |
| --- | ---: | ---: |
| Logical task failure rate | 1,2% | 6,8% |
| Model attempt timeout rate | 0,5% | 1,0% |
| Provider 429 rate | 0,2% | 4,5% |
| Tool timeout rate | 0,8% | 0,9% |
| Attempts/logical task | 1,08 | 1,75 |
| Input tokens/model request | 900 | 1.650 |
| Verified task success | 96,5% | 91,0% |

**Điều có thể suy ra:** tool timeout gần như không đổi; provider 429 và retry amplification tăng; token input mỗi model request tăng. Điều này gợi ý cần xem quota TPM/RPM, kích thước context và số model calls. Bảng chưa chứng minh prompt là nguyên nhân duy nhất.

### Quy trình điều tra

1. Chia lỗi theo model/provider, tool, retrieval và application limiter.
2. Kiểm tra provider 429 có đi kèm Retry-After và model/token group nào.
3. Mở traces của task thất bại để đếm model turns, tool calls và retry.
4. So sánh input tokens và context documents giữa hai prompt.
5. Kiểm tra task deadline có bị tiêu hao bởi backoff/retry không.
6. Xác minh evaluator có đủ bằng chứng; không gộp evaluator timeout vào quality FAIL.
7. Chạy lại cùng dataset/fixture với phiên bản prompt trước và sau, cùng model/provider quota nếu có thể.
8. Đánh giá task success, fact checking, latency và cost per verified success trước khi quyết định.

### Một tình huống khác: app limiter reject tăng nhưng provider 429 giảm

Điều này có thể là dấu hiệu **application limiter đang bảo vệ provider tốt hơn**. Nếu task success và latency người dùng vẫn đạt SLO, đây có thể là hành vi mong muốn. Nếu task failure tăng vì request bị từ chối, product phải quyết định có cần queue, capacity hoặc quota theo tenant khác hay không.

Đừng kết luận hệ thống xấu đi chỉ vì số lần limiter reject tăng; cần đọc **policy outcome**, **task success** và **user impact** cùng nhau.

## 15. Dashboard và runbook: đọc tín hiệu theo thứ tự

Một dashboard cho ứng dụng Spring AI nên giúp phân biệt **lưu lượng**, **lỗi**, **deadline**, **rate limit**, **chất lượng** và **chi phí**. Đừng đặt mọi chỉ số lên một panel rồi chỉ nhìn màu đỏ/xanh.

### 15.1. Các panel nên có

| Nhóm | Chỉ số | Câu hỏi |
| --- | --- | --- |
| Traffic | Logical requests/s, model attempts/s, tool executions/s | Tải tăng ở tầng nào? |
| Reliability | Task failure rate, attempt error rate | Người dùng thất bại hay chỉ có attempts lỗi? |
| Timeout | Timeout rate theo model/tool/retrieval | Dependency hoặc deadline nào đang gây lỗi? |
| Rate limiting | Application reject, provider 429, RPM/TPM | Ai đang áp giới hạn và loại quota nào? |
| Retry | Attempts/task, retries/task, retry success | Retry có giúp hay chỉ khuếch đại? |
| Concurrency | In-flight, queue depth, oldest age | Có backlog hoặc worker bị treo? |
| Latency | p50/p95 theo component và end-to-end | Thành phần nào chậm? |
| Quality | Verified task success, fact-check, relevance | Tác vụ có đúng không? |
| Cost | Tokens/task, cost/verified success | Retry và prompt có làm chi phí tăng? |
| Coverage | Unknown/inconclusive, missing telemetry | Có đủ dữ liệu để kết luận? |

### 15.2. Thứ tự điều tra khi có cảnh báo

1. **Xác định tác động:** task failure, timeout, rate limit hay quality FAIL đang tăng?
2. **Xác định tầng:** model/provider, application limiter, tool backend, retriever hay evaluator?
3. **Kiểm tra mẫu số:** có thay đổi traffic, case mix, retry policy hoặc coverage không?
4. **Kiểm tra thời điểm:** có deploy prompt/model, thay đổi quota, traffic burst hoặc backend incident không?
5. **Mở traces đại diện:** một ca thất bại, một ca chậm và một ca thành công sau retry.
6. **Đối chiếu source of truth:** tool đã thực thi chưa, nghiệp vụ đã hoàn tất chưa?
7. **Đưa ra hành động có căn cứ:** giảm context, điều chỉnh retry budget, queue, quota, timeout hoặc rollback.

### 15.3. Runbook ngắn cho provider 429

Khi provider 429 tăng:

- Xem model group nào, RPM/TPM hay quota nào bị chạm nếu provider cung cấp tín hiệu.
- Kiểm tra input/output tokens/request và số model calls/task.
- Đọc Retry-After và retry attempts; xác nhận backoff có jitter và nằm trong task deadline.
- Kiểm tra có nhiều instance dùng chung quota nhưng không chia sẻ limiter state không.
- Xem task failure, p95 và cost per verified success.
- Nếu cần, giảm context hoặc concurrency, phân phối tải, queue hoặc dùng fallback model theo policy đã định.

### 15.4. Runbook ngắn cho timeout tăng

Khi timeout tăng:

- Phân biệt timeout client, task, model, tool, retrieval và evaluator.
- Xem Timer theo component và outcome; kiểm tra timeout có bị loại khỏi histogram thành công không.
- Xem in-flight, queue depth, connection pool và oldest age.
- Mở trace của ca chậm để tìm span đầu tiên vượt budget.
- Xác minh backend có tiếp tục xử lý sau khi client timeout không.
- Với thao tác ghi, kiểm tra operation ID trước khi retry.

## 16. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gộp attempt error và task failure | Không biết người dùng có nhận kết quả không | Báo riêng hai cấp |
| Dùng số user tasks làm mẫu số tool timeout | Tỷ lệ không cùng đơn vị | Dùng tool executions/attempts |
| Bỏ qua request đang in-flight | Error rate thấp giả | Định nghĩa started/completed và deadline |
| Ghi 429 thành lỗi provider chung | Mất tín hiệu quota/throttling | Tách rate_limited và limiter_source |
| Gộp app limiter với provider 429 | Chẩn đoán sai thành phần | Tag nguồn giới hạn riêng |
| Retry ngay sau 429 | Retry storm và tăng tải | Backoff, jitter, Retry-After |
| Retry cả lỗi 400/403 | Tăng cost nhưng không thể thành công | Phân loại retryable errors |
| Retry thao tác ghi không idempotent | Tác động trùng | Idempotency key và kiểm tra state |
| Timer chỉ ghi success | p95 đẹp giả khi timeout tăng | Ghi cả outcome lỗi/timeout |
| Ghi timeout thành 0 ms | Latency thấp giả | Ghi thời gian đến deadline |
| Đánh evaluator timeout thành quality FAIL | Sai phân loại chất lượng | INCONCLUSIVE/EVALUATOR_ERROR |
| Coi HTTP 200 là business completed | Verified success ảo | Kiểm tra hậu điều kiện backend |
| Dùng raw exception message làm tag | Cardinality cao, rò dữ liệu | Map về error_class hữu hạn |
| Không đo retry attempts | Không thấy amplification | Counter retry và attempts/task |
| Chỉ nhìn provider error rate | Bỏ qua app rejection và user impact | Đọc cả task-level SLI |
| Không tách timeout theo component | Không tìm được dependency chậm | Timer/counter theo component |

## 17. Kiểm thử metric và chính sách lỗi

Metric cho lỗi, timeout và rate limit cần được kiểm thử cùng hành vi thực thi. Chỉ kiểm tra rằng Counter tồn tại là chưa đủ; phải xác nhận **mỗi sự kiện tăng đúng một lần, đúng nhãn và đúng mẫu số**.

### 17.1. Bộ ca kiểm thử tối thiểu

| Ca | Kịch bản | Kết quả metric mong đợi |
| --- | --- | --- |
| Success attempt | Model/tool hoàn tất | Timer + Counter outcome=success |
| Provider error | Provider trả lỗi | outcome=error, error class tương ứng |
| Timeout | Attempt hết deadline sau 2 s | outcome=timeout, duration xấp xỉ 2 s |
| Provider 429 | Provider trả rate limit | outcome=rate_limited và provider signal |
| App limiter reject | Limiter chặn trước provider | decision=rejected, không có provider attempt giả |
| Limiter allow | Limiter cho phép | decision=allowed |
| Retry | Một attempt bổ sung | Retry counter tăng; logical task vẫn là một |
| Retry success | Attempt sau thành công | Attempt errors và task outcome được báo riêng |
| Cancelled by user | Người dùng chủ động hủy | outcome=cancelled, không gộp timeout |
| Evaluator unavailable | Judge không trả kết quả | INCONCLUSIVE/EVALUATOR_ERROR |
| Tool write timeout | Response mất sau khi backend nhận lệnh | Kiểm tra operation state trước retry |
| Gauge lifecycle | Request ném exception | In-flight giảm trong finally |

### 17.2. Kiểm tra bằng SimpleMeterRegistry

Ví dụ dưới đây xác nhận một timeout attempt được ghi thành một sample và một event:

~~~java
import java.time.Duration;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

var registry = new SimpleMeterRegistry();
var meters = new AiFailureMeters(registry);

meters.recordAttemptResult(
        "model",
        AiFailureMeters.Outcome.TIMEOUT,
        Duration.ofSeconds(2));

var timer = registry.find("app.ai.attempt.duration")
        .tag("component", "model")
        .tag("outcome", "timeout")
        .timer();

var counter = registry.find("app.ai.attempt.completed")
        .tag("component", "model")
        .tag("outcome", "timeout")
        .counter();

if (timer == null || timer.count() != 1) {
    throw new AssertionError("Expected one timeout Timer sample");
}
if (counter == null || counter.count() != 1.0) {
    throw new AssertionError("Expected one timeout event");
}
~~~

Test này kiểm tra dữ liệu trong Micrometer registry. Nếu cần xác minh Prometheus series, phải dùng Prometheus registry hoặc endpoint scrape tương ứng và kiểm tra tên/labels thực tế.

### 17.3. Kiểm thử retry không làm tăng task count

Với một logical task có hai attempts lỗi và attempt thứ ba thành công:

- Attempt counter có ba kết quả.
- Retry counter tăng hai (nếu attempt đầu không được tính là retry).
- Logical request completed counter tăng một với outcome success.
- Task failure rate không tăng.
- Attempt error/throttle rate vẫn phản ánh hai attempts không thành công.
- Task duration và cost bao gồm cả retry/backoff.

Đây là kiểm thử quan trọng để ngăn dashboard đánh đồng **một task** với **ba attempts**.

### 17.4. Kiểm thử timeout không tạo false success

Giả lập một tool timeout nhưng backend vẫn hoàn tất muộn. Bộ kiểm thử phải xác minh:

1. Client attempt được phân loại timeout theo deadline của nó.
2. Backend state được kiểm tra bằng operation ID.
3. Không gửi lại lệnh ghi nếu chưa xác định trạng thái và không có idempotency.
4. Nếu backend hoàn tất muộn, ghi nhận late completion riêng.
5. Câu trả lời người dùng không tuyên bố hoàn tất trước khi có bằng chứng.

## 18. Bài thực hành

**Bối cảnh:** trợ lý Spring AI có model provider, tool tra cứu đơn, tool tạo yêu cầu hoàn tiền, retriever chính sách và evaluator fact checking. Sau khi tăng traffic, người dùng phản ánh đôi lúc request bị từ chối hoặc chờ quá lâu.

### Phần A — Phân loại sự kiện

1. Một model request trả 429 kèm Retry-After.
2. Application limiter từ chối vì concurrency vượt ngưỡng.
3. Tool tra cứu đơn timeout sau 2 giây.
4. Tool hoàn tiền trả ACCEPTED nhưng trạng thái vẫn PENDING.
5. Evaluator timeout nên không thể chấm groundedness.
6. Người dùng không có quyền xem đơn của tenant khác.

Với từng trường hợp, ghi **component, outcome, error class, có phải timeout/rate limit không, nguồn bằng chứng và ảnh hưởng đến logical task**.

### Phần B — Tính tỷ lệ

Trong một cửa sổ quan sát có:

- 1.000 model attempts: 30 error, 40 timeout, 50 provider 429, 880 success.
- 400 logical tasks: 20 failure, 370 success, 10 inconclusive.
- 500 application limiter decisions: 35 rejected, 465 allowed.
- 200 tool attempts: 10 timeout, 5 error, 185 success.

Tính:

1. Attempt failure rate nếu định nghĩa gồm error + timeout, không gồm 429.
2. Provider throttle rate.
3. Logical task failure rate trên các task đã kết luận.
4. Task coverage.
5. Application limiter rejection rate.
6. Tool timeout rate.

**Đáp án kiểm tra nhanh:**

- Attempt failure rate = (30 + 40) / 1.000 = **7%**.
- Provider throttle rate = 50 / 1.000 = **5%**.
- Task failure rate trên ca có kết luận = 20 / (20 + 370) ≈ **5,13%**.
- Task coverage = (20 + 370) / 400 = **97,5%**.
- Application limiter rejection rate = 35 / 500 = **7%**.
- Tool timeout rate = 10 / 200 = **5%**.

Các kết quả trên giả định các nhóm outcome không chồng lấp và mỗi attempt/task được phân loại đúng một lần.

### Phần C — Thiết kế và kiểm tra metrics

1. Tạo Counter cho attempt outcomes, retry attempts, limiter decisions và logical task outcomes.
2. Tạo Timer cho model/tool/retrieval attempts, ghi cả nhánh lỗi.
3. Tạo Gauge cho in-flight requests và queue depth.
4. Dùng tags hữu hạn cho component, outcome, limiter_source và limit_type.
5. Viết PromQL cho attempt error rate, timeout rate, provider throttle, app limiter rejection và retries/task.
6. Kiểm tra mẫu số bằng 0, reset counter và request còn in-flight.

### Phần D — Phân tích sự cố và đề xuất

1. Giả sử provider 429 tăng sau khi prompt làm input tokens tăng 60%. Xác định những traces và metrics cần kiểm tra.
2. Giả sử app limiter rejection tăng nhưng provider 429 giảm. Đánh giá đó là cải thiện bảo vệ hay suy giảm trải nghiệm người dùng.
3. Giả sử tool timeout giảm nhưng task failure tăng. Tìm những tầng khác có thể gây lỗi.
4. Đề xuất retry budget, backoff, jitter và deadline cho task 8 giây.
5. Với tool hoàn tiền, mô tả cách dùng operation ID/idempotency để tránh tác động trùng sau timeout.
6. Viết một alert có điều kiện về tỷ lệ, cỡ mẫu và thời gian duy trì.

### Câu hỏi tự kiểm tra

- Error rate theo attempt khác task failure rate như thế nào?
- Vì sao một task có thể thành công dù có hai attempts thất bại?
- Mẫu số timeout rate nên xử lý các request mới bắt đầu ở cuối cửa sổ ra sao?
- 429 từ application limiter khác 429 từ provider như thế nào?
- Vì sao TPM có thể bị chạm dù requests per second không tăng?
- Khi nào cần queue thay vì reject ngay?
- Vì sao Retry-After và jitter giúp hạn chế retry storm?
- Những lỗi nào không nên retry tự động?
- Vì sao timeout của tool ghi dữ liệu phải kiểm tra operation state?
- Tại sao evaluator timeout không được chấm như quality FAIL?
- Vì sao cần đo cả attempt error và verified task outcome?
- Những metric nào giúp nhận biết retry đang làm tăng cost và latency?

## 19. Những điều cần ghi nhớ

1. **Định nghĩa lỗi theo tầng và theo hợp đồng.** HTTP error, provider error, tool error, business rejection và quality failure không đồng nghĩa.
2. **Tách attempt-level và task-level metrics.** Một task có thể chứa nhiều attempts, retries, model calls và tool executions.
3. **Mẫu số phải khớp đơn vị đo.** Tool timeout chia cho tool attempts; task failure chia cho logical tasks đã kết thúc.
4. **Timeout cần deadline rõ ràng.** Phân biệt model, tool, retrieval, request và business completion; không ghi timeout bằng 0 ms.
5. **Rate limiting có nhiều nguồn.** Application limiter, provider 429, RPM, TPM, concurrency và tenant quota cần được đo riêng.
6. **Retry có thể khuếch đại sự cố.** Dùng backoff, jitter, Retry-After, retry budget và idempotency.
7. **Counter, Timer và Gauge bổ sung nhau.** Đếm outcome, đo duration và đọc trạng thái in-flight; không đếm trùng một sự kiện.
8. **Không để metric tags tăng vô hạn.** Dùng component/outcome/error_class hữu hạn; giữ ID và nội dung chi tiết trong trace/log có phân quyền.
9. **Quality và reliability cần được xem cùng nhau.** Một model request có thể thành công về kỹ thuật nhưng câu trả lời sai fact checking; evaluator timeout là inconclusive.
10. **Cảnh báo phải phản ánh user impact.** Đọc error rate, timeout, throttling, retry, latency, coverage, verified success và cost cùng nhau.

## Tài liệu tham khảo

- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): đếm sự kiện và cách sử dụng Counter.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo duration, count và tổng thời gian.
- [Micrometer Reference — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html): trạng thái tức thời và vòng đời đối tượng.
- [Micrometer Reference — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html): Prometheus registry và export.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): quan sát ChatClient, model và tool.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistry và endpoint metrics.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): rate, increase và các hàm truy vấn.
- [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry): chính sách retry, số lần thử và interval.
- [Resilience4j — RateLimiter](https://resilience4j.readme.io/docs/ratelimiter): giới hạn tốc độ và thời gian chờ permit.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): HTTP 429 Too Many Requests.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): semantics của HTTP, retry và response headers.

**Lưu ý phiên bản:** tên observation, API timeout/retry, provider error mapping và metric có sẵn có thể thay đổi theo phiên bản Spring AI, Spring Boot, Micrometer và provider. Các tên app.ai trong bài là ví dụ tự thiết kế; khi triển khai, kiểm tra metric thực tế, contract nghiệp vụ và chính sách quota của dịch vụ đang dùng.
