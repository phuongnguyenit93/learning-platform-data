# Nguyên tắc trách nhiệm đơn và độ kết dính của Aspect trong thiết kế AOP

## 1. Mục tiêu và bối cảnh

**Aspect-Oriented Programming (AOP)** là cách mô-đun hóa các *mối quan tâm cắt ngang* (*cross-cutting concerns*) xuất hiện ở nhiều lớp hoặc nhiều thao tác: quan sát thời gian thực thi, ghi log, truy vết, kiểm tra quyền, kiểm soát retry, quản lý ngữ cảnh và một số chính sách thực thi khác. Một **aspect** tập hợp các **advice** được áp dụng tại các **join point** do **pointcut** lựa chọn. Tùy cơ chế thực thi, mã aspect có thể được kết hợp bằng proxy, decorator, trình tạo mã hoặc weaving.

Tách mã ra khỏi nghiệp vụ **không tự động làm kiến trúc tốt hơn**. Nếu một aspect ôm cả bảo mật, retry, cache, transaction, log và chuyển đổi lỗi, nó có thể trở thành một “siêu mô-đun” mà chỉ cần sửa một yêu cầu nhỏ cũng ảnh hưởng nhiều luồng thực thi. Ngược lại, chia mỗi dòng log hay mỗi lời gọi kiểm tra thành một aspect riêng có thể khiến hệ thống khó hiểu vì có quá nhiều điểm chặn và thứ tự phối hợp.

Hai nguyên tắc thiết kế giải quyết tình huống này:

1. **Single Responsibility Principle (SRP — trách nhiệm đơn):** một aspect nên có **một lý do chính để thay đổi**, xuất phát từ một chính sách hoặc một trách nhiệm có chủ sở hữu rõ ràng.
2. **Cohesion (độ kết dính):** các advice, pointcut, cấu hình, trạng thái và phép đo trong cùng aspect cần **gắn chặt với mục tiêu chung ấy**. Những thành phần chỉ tình cờ cùng xuất hiện tại một phương thức chưa chắc thuộc cùng một trách nhiệm.

Mục tiêu thực hành là nhận ra đâu là một mối quan tâm có thể mô-đun hóa, đặt ranh giới cho aspect, thiết kế pointcut nhất quán, phối hợp nhiều aspect và kiểm thử khả năng thay đổi độc lập. Bài trình bày **AOP tổng quát từ cơ bản tới nâng cao** và ví dụ Java 17+ bằng decorator minh họa cách tổ chức quanh một lời gọi.

## 2. SRP trong aspect có nghĩa gì?

### 2.1. “Một trách nhiệm” là một lý do thay đổi

Không nên diễn giải SRP thành “mỗi aspect chỉ có một method/advice”. Một aspect quan sát hiệu năng có thể cần:

- Advice trước khi gọi để ghi mốc thời gian.
- Advice sau khi hoàn tất để tính độ trễ.
- Xử lý đường lỗi để cập nhật metric.
- Hàm nội bộ chuẩn hóa tên thao tác và nhãn metric.
- Bộ cấu hình quyết định mốc đo, loại join point được quan sát và ngân sách overhead.

Những thành phần này cùng phục vụ **một chính sách đo thời gian/hiệu năng**, được cập nhật khi yêu cầu observability đổi. Chúng có thể tạo thành một aspect kết dính cao dù có nhiều hàm.

Ngược lại, một aspect chứa cả luật “vai trò nào được phê duyệt đơn hàng”, “khi lỗi I/O thì retry mấy lần” và “log theo định dạng JSON nào” có **nhiều lý do độc lập để thay đổi**: thay chính sách bảo mật, thay chiến lược chịu lỗi, thay định dạng telemetry. Gom chúng vào một nơi làm tăng tác động của thay đổi và nguy cơ phá hành vi khác.

Dùng câu hỏi: **Ai yêu cầu thay đổi, vì sao phải thay, và có cần sửa những hành vi khác không?** Nếu ba thay đổi có thể do ba nhóm/chính sách vận hành khác nhau quyết định, đó là dấu hiệu phải cân nhắc tách.

### 2.2. “Một chức năng kỹ thuật” chưa chắc là một trách nhiệm

Tên gọi `InfrastructureAspect`, `CommonAspect` hay `UtilsAspect` chưa chứng minh phần mã kết dính. Đặc biệt, “mọi việc trước/sau lời gọi” không phải một mục đích thiết kế cụ thể. Một phần logic có chung đặc điểm kỹ thuật như “đều dùng reflection” không có nghĩa chúng cùng trách nhiệm.

Đồng thời, không cần tách máy móc theo từng **kiểu advice** (before/after/around). Nếu một policy cần cả before và after để giữ trạng thái chính xác, tách chúng sang các aspect chỉ để mỗi file có một advice có thể làm lộ chi tiết nội bộ và tăng nguy cơ sai thứ tự.

### 2.3. Những yếu tố cần xem cùng nhau

Một ranh giới aspect thường gồm:

| Thành phần | Cần kết dính theo điều gì? | Dấu hiệu bất thường |
| --- | --- | --- |
| **Policy/contract** | Một cam kết hoặc quy tắc nhất quán | Cùng aspect có nhiều rule không liên quan |
| **Pointcut** | Tập join point phục vụ đúng policy | Pointcut quá rộng, chặn mọi method |
| **Advice** | Những bước cần thiết để thực hiện policy | Advice làm cả nghiệp vụ và nhiều kỹ thuật |
| **State** | Dữ liệu nội bộ thuộc vòng đời policy | Biến đếm/timer/cache quyền dùng chung không rõ |
| **Configuration** | Các tham số thay đổi cùng policy | Một config bật tắt nhiều tính năng độc lập |
| **Dependencies** | Những dịch vụ thiết yếu để thi hành policy | Aspect phụ thuộc cả DB, HTTP, cache, mail, logger |
| **Tests** | Xác minh một hành vi/contract rõ | Chỉnh logging khiến test authorization hỏng |
| **Observability** | Đo được tác động của chính policy | Không biết lỗi phát sinh ở lớp advice nào |

Một aspect kết dính cao có giao diện hẹp, tên biểu đạt đúng policy, không lưu trạng thái ngoại lai và có tập kiểm thử tương ứng với thay đổi dự kiến.

## 3. Nhận biết các dạng cohesion

Trong thiết kế mô-đun nói chung, những thành phần gắn với nhau vì “cùng thời điểm” hoặc “cùng công cụ” thường kết dính yếu hơn các thành phần cùng phục vụ một mục đích chức năng rõ ràng.

Áp vào AOP:

- **Cùng xuất hiện theo thời điểm:** ghi log, kiểm tra quyền, mở transaction đều xảy ra trước một operation. Đây là lý do yếu để đưa chúng chung một aspect.
- **Cùng dùng dữ liệu đầu vào:** trace ID, principal và request ID cùng nằm trong context. Chúng có thể chia sẻ một abstraction context nhưng chưa chắc cùng thuộc một policy.
- **Cùng quy trình:** mở phạm vi đo, chạy nghiệp vụ, ghi kết quả và đóng phạm vi đo. Đây thường là một trách nhiệm observability thống nhất.
- **Cùng bất biến:** mọi advice trong nhóm cần bảo đảm “mỗi operation chỉ công bố một terminal metric”. Chúng có liên hệ chức năng chặt chẽ.
- **Cùng lý do thay đổi:** khi quy định đo latency đổi, các điểm bắt đầu/kết thúc, nhãn và timer cần đổi đồng bộ; một aspect duy nhất có thể là hợp lý.

Không phải cứ nhiều advice là cohesion thấp. Vấn đề là **mức phụ thuộc ngữ nghĩa giữa những advice**, không phải số dòng mã.

### 3.1. Cohesion của pointcut

Pointcut kết dính khi mọi join point được chọn đều chia sẻ **cùng semantics mà policy cần**. Ví dụ, một policy đếm thời gian truy vấn chỉ chọn các thao tác truy vấn có ranh giới hoàn tất rõ ràng.

Pointcut như “mọi method bắt đầu bằng `get`” có thể vô tình chặn:

- Method lấy dữ liệu công khai.
- Method đọc thông tin nhạy cảm.
- Method đọc dữ liệu cache, không truy cập I/O.
- Method chỉ trả một `Future` chưa hoàn tất.
- Getter đơn giản trong domain model.

Nếu advice áp cùng một timeout, transaction hoặc quyền lên những thao tác rất khác nhau, đó là **thiếu cohesion giữa policy và tập join point**. Hãy dùng các contract hoặc metadata ổn định, signature và ranh giới API có ý nghĩa, rồi kiểm thử chính xác danh sách join point được chặn.

### 3.2. Cohesion của state

Aspect ghi metric có thể sở hữu counter hoặc timer; aspect retry có thể sở hữu retry budget; aspect bảo mật có thể cần policy evaluator. Không nên dùng một mutable map trong “CommonAspect” để chứa cả trace context, authentication decision và retry counter chỉ vì tiện truy cập.

Đặc biệt, aspect instance có thể được chia sẻ giữa nhiều lời gọi. State gắn với mỗi invocation phải có phạm vi và đồng bộ rõ ràng; lưu principal hoặc timestamp của request gần nhất trên field dùng chung có thể gây race và rò dữ liệu giữa người dùng.

## 4. Vì sao một “God Aspect” gây hại?

Xét đoạn giả mã quanh một method bất kỳ:

~~~text
around serviceCall(args):
    if not authorized(args): return emptyResult()
    beginTransaction()
    key = buildCacheKey(args)
    if cache.has(key): return cache.get(key)
    for retry in 1..3:
        try:
            result = proceed(args)
            cache.put(key, result)
            logFullArguments(args, result)
            commit()
            return result
        catch Exception:
            logError()
    rollback()
    return defaultValue()
~~~

Đây là **giả mã anti-pattern**, không phải một chương trình chạy được. Nó chứa nhiều lỗi tiềm tàng:

- Trả kết quả rỗng khi thiếu quyền có thể che hành vi từ chối.
- Cache hit trả ra trước khi transaction được đóng đúng đường đi.
- Retry có thể thực thi side effect nhiều lần.
- Cache có thể nhận dữ liệu chưa commit.
- Exception gốc có thể biến mất sau nhiều lần lặp.
- Log toàn bộ tham số có thể lộ dữ liệu nhạy cảm.
- Transaction có thể không được rollback ở mọi nhánh.
- Thay đổi định dạng log có thể vô tình ảnh hưởng các nhánh xử lý lỗi.
- Không rõ ai chịu trách nhiệm cho từng invariant hoặc thứ tự.

Ngay cả khi khắc phục các lỗi cú pháp/luồng, việc gom tất cả vào một aspect vẫn làm **mỗi thay đổi của policy có phạm vi tác động quá rộng**.

### 4.1. Dấu hiệu phát hiện khi review

Một số cảnh báo:

1. Tên `EverythingAspect`, `GenericAspect`, `ServiceInterceptor` nhưng không mô tả được mục đích duy nhất.
2. Có nhiều cờ `enableSecurity`, `enableCache`, `enableRetry`, `enableAudit` trong cùng một cấu hình.
3. Advice nhận hàng loạt dependency chỉ để chọn nhánh theo loại method.
4. Pointcut có nhiều điều kiện đặc biệt “trừ method X”, “chỉ áp cho service Y”.
5. Test của một tính năng phải dựng database, cache, mạng và policy khác không liên quan.
6. Thay đổi thứ tự log lại làm thay đổi transaction hoặc exception.
7. Một lời gọi được bảo vệ theo kiểu “nếu method có annotation A thì check quyền, nếu B thì cache” nhưng không có hợp đồng nhất quán về composition.
8. Nhóm phát triển không thể chỉ ra owner của policy hoặc nguyên nhân sửa gần nhất của aspect.

Đây là dấu hiệu cần đánh giá kiến trúc, không phải mệnh lệnh bắt buộc chia mọi file ngay lập tức. Chi phí phối hợp, hiệu năng và giới hạn của cơ chế weaving cũng ảnh hưởng ranh giới tối ưu.

## 5. Phân tách trách nhiệm có chủ đích

Thay vì một aspect làm tất cả, có thể tách:

| Aspect / module | Trách nhiệm chính | Không nên tự quyết |
| --- | --- | --- |
| `AuthorizationAspect` | Yêu cầu quyết định allow/deny theo policy đã công bố | Tạo fallback “thành công” khi bị từ chối |
| `TracingAspect` | Tạo/kết nối span, lan truyền trace context, đóng vòng đời span | Quyết định có retry hay rollback nghiệp vụ |
| `MetricsAspect` | Ghi số lần gọi, lỗi, latency theo contract đo lường | Chuyển exception lỗi thành giá trị khác |
| `RetryAspect` | Thực hiện lại thao tác theo policy retry công khai | Tự cho phép retry lệnh ghi chưa có idempotency |
| `TransactionAspect` | Bắt đầu, commit, rollback trong một transaction boundary được định nghĩa | Thay thế nguyên tử nghiệp vụ phân tán bằng giả định |
| `CachingAspect` | Tra/lưu kết quả với key, TTL, invalidation và consistency rõ | Bỏ qua kiểm tra quyền của dữ liệu được bảo vệ |
| `AuditAspect` | Ghi sự kiện kiểm toán theo hợp đồng độ bền và dữ liệu | Dùng log debug có sampling như chứng cứ kiểm toán đầy đủ |
| `ContextAspect` | Thiết lập/khôi phục context thuộc lời gọi khi cần | Dùng field dùng chung gây rò principal giữa invocation |

Bảng thể hiện một phương án hợp lý; đôi khi một policy kỹ thuật cần nhiều lớp nhỏ hoặc vài concern gắn kết có thể ở cùng một aspect. Điều cốt lõi là **lý do thay đổi, hợp đồng và chủ sở hữu**.

### 5.1. Một aspect nhiều advice vẫn có thể đúng SRP

Ví dụ một `LatencyAspect`:

~~~java
// Minh hoa API gia dinh, khong phai chuong trinh doc lap.
long startedAt = System.nanoTime();
try {
    return proceed();
} finally {
    metrics.recordDuration(System.nanoTime() - startedAt);
}
~~~

Nó có một trách nhiệm là đo elapsed time, một đường vào và một đường ra. Nếu một phương thức trả `CompletionStage`, advice đồng bộ đo **thời gian tạo stage**; muốn đo đến completion phải gắn callback thích hợp. Mở rộng để hỗ trợ async vẫn có thể thuộc **cùng lý do thay đổi** nếu hợp đồng của aspect là “đo thời gian hoàn tất operation”, miễn bảo đảm logic terminal một lần và cleanup đúng.

### 5.2. Cái gì nên là helper/library thay vì aspect khác?

Một số code như `normalizeMetricName`, `captureContext` hoặc `safeTruncate` có thể là **hàm hỗ trợ dùng chung**, không nhất thiết là một aspect mới. Aspect chỉ nên tồn tại khi cần tham gia composition tại join point. Tách một thuật toán thuần thành một “aspect” chỉ để dùng lại là thêm interception và dependency không cần thiết.

Ngược lại, nếu một chính sách phải được chèn ở nhiều join point và có vòng đời riêng, đóng gói nó vào aspect thay vì lặp ở từng domain service có thể hữu ích.

## 6. Ví dụ Java 17+: mỗi decorator đại diện một trách nhiệm

Ví dụ dưới cho thấy ba lớp cắt ngang tách biệt: **authorization**, **tracing** và **metrics**. Chúng được cài bằng decorator quanh interface để quan sát rõ composition. Decorator không tự động weaving, nhưng hành vi `next.call()` tương đương ý tưởng `proceed()` của around advice. Từng lớp có một mục đích, và nghiệp vụ không biết lớp nào đang bao quanh.

Lưu file `AspectCohesionDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public class AspectCohesionDemo {
    interface OrderOperation {
        String place(String role, String orderId);
    }

    static final class CoreOperation implements OrderOperation {
        @Override
        public String place(String role, String orderId) {
            System.out.println("domain: process");
            return "receipt:" + orderId;
        }
    }

    static final class AuthorizationAspect implements OrderOperation {
        private final OrderOperation next;
        private final AtomicLong denied = new AtomicLong();

        AuthorizationAspect(OrderOperation next) {
            this.next = next;
        }

        @Override
        public String place(String role, String orderId) {
            if (!"operator".equals(role)) {
                denied.incrementAndGet();
                throw new SecurityException("forbidden");
            }
            return next.place(role, orderId);
        }

        long deniedCount() {
            return denied.get();
        }
    }

    static final class TracingAspect implements OrderOperation {
        private final OrderOperation next;

        TracingAspect(OrderOperation next) {
            this.next = next;
        }

        @Override
        public String place(String role, String orderId) {
            System.out.println("trace: begin place");
            try {
                String result = next.place(role, orderId);
                System.out.println("trace: success");
                return result;
            } catch (RuntimeException e) {
                System.out.println("trace: error");
                throw e;
            }
        }
    }

    static final class MetricsAspect implements OrderOperation {
        private final OrderOperation next;
        private final AtomicLong attempts = new AtomicLong();
        private final AtomicLong successes = new AtomicLong();
        private final AtomicLong failures = new AtomicLong();

        MetricsAspect(OrderOperation next) {
            this.next = next;
        }

        @Override
        public String place(String role, String orderId) {
            attempts.incrementAndGet();
            try {
                String result = next.place(role, orderId);
                successes.incrementAndGet();
                return result;
            } catch (RuntimeException e) {
                failures.incrementAndGet();
                throw e;
            }
        }

        String summary() {
            return "attempts=" + attempts.get()
                    + " successes=" + successes.get()
                    + " failures=" + failures.get();
        }
    }

    public static void main(String[] args) {
        AuthorizationAspect auth =
                new AuthorizationAspect(new CoreOperation());
        TracingAspect tracing = new TracingAspect(auth);
        MetricsAspect metrics = new MetricsAspect(tracing);

        System.out.println("caller: " + metrics.place("operator", "order-1"));
        try {
            metrics.place("guest", "order-2");
        } catch (SecurityException e) {
            System.out.println("caller: " + e.getMessage());
        }

        System.out.println("metrics: " + metrics.summary());
        System.out.println("auth: denied=" + auth.deniedCount());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 AspectCohesionDemo.java
java AspectCohesionDemo
~~~

**Stdout chính xác:**

~~~text
trace: begin place
domain: process
trace: success
caller: receipt:order-1
trace: begin place
trace: error
caller: forbidden
metrics: attempts=2 successes=1 failures=1
auth: denied=1
~~~

Điểm cần nhận ra:

- `AuthorizationAspect` chỉ kiểm tra quyền theo policy đơn giản, không đo metric hay ghi trace; đường không được phép không vào `CoreOperation`.
- `TracingAspect` đánh dấu vòng đời lời gọi và phân biệt success/error nhưng **không thay** kết quả hay exception.
- `MetricsAspect` chỉ đếm các sự kiện; mọi invocation đi qua wrapper đều được đếm, bao gồm một lần bị từ chối. Định nghĩa `failures` ở demo bao gồm `SecurityException`; sản phẩm thực có thể phải tách `denied` và `businessFailed`.
- `CoreOperation` sở hữu logic nghiệp vụ. Trong demo, role chỉ là chuỗi để trình bày cấu trúc; hệ thống thực phải lấy principal từ ngữ cảnh xác thực tin cậy và cần kiểm soát quyền tại boundary phù hợp.
- Thay trace formatter chỉ cần sửa `TracingAspect`. Thay rule phân quyền chỉ cần sửa `AuthorizationAspect` và test bảo mật. Thay tên metric chỉ cần sửa `MetricsAspect`.
- Thứ tự wrapper ở đây là **Metrics -> Tracing -> Authorization -> Core**. Nếu chuyển `MetricsAspect` vào phía trong `AuthorizationAspect`, một lần bị từ chối sẽ không tăng `attempts`. Đây là thay đổi semantics thống kê nên phải được quyết định theo hợp đồng metric.

Ví dụ cố ý đồng bộ và không có cache/transaction để minh họa SRP rõ ràng. Những policy cắt ngang khác có thể được thêm bằng lớp riêng khi thực sự cần. Đừng nhầm “mỗi aspect làm một việc” với “cứ thêm bao nhiêu aspect cũng không có rủi ro”: composition order và performance vẫn phải được xét.

## 7. Độ kết dính và mức độ phụ thuộc giữa các aspect

**Cohesion** trả lời: các phần bên trong một aspect có phục vụ cùng chính sách không? **Coupling** trả lời: một aspect phải biết hoặc thay đổi theo các aspect khác nhiều đến mức nào?

Một kiến trúc đáng mong muốn thường có **cohesion cao**, đồng thời giảm **coupling không cần thiết**. Ví dụ:

- Metrics không cần gọi trực tiếp `AuthorizationAspect.check()`; nó quan sát kết quả/loại lỗi theo hợp đồng.
- Tracing không nên trực tiếp điều chỉnh retry counter.
- Authorization không nên biết cache exporter format ra sao.
- Transaction không nên tự format log nhạy cảm hoặc quyết định sampling.

Tuy nhiên có những **phụ thuộc ngữ nghĩa có thật** cần nêu rõ. Cache trả dữ liệu nhạy cảm phải được đặt sau enforcement đúng mức. Retry và transaction phải phối hợp để không lặp side effect ngoài hợp đồng. Tracing có thể cần biết một logical operation chứa bao nhiêu attempt để đặt span và tags hợp lý. Tách file **không xóa các phụ thuộc này**; nó khiến chúng được mô tả ở cấu trúc composition thay vì ẩn trong một phương thức dài.

### 7.1. Không tạo vòng phụ thuộc

Một vòng như sau khó vận hành:

~~~text
TracingAspect -> MetricsAspect -> RetryAspect
       ^                             |
       +-----------------------------+
~~~

Nếu mỗi aspect gọi ngược trực tiếp vào aspect khác hoặc interceptor lại gọi chính join point mình chặn, có thể xảy ra recursion, double-count hoặc deadlock. Đặt các abstraction hẹp ở tầng thấp hơn:

- `TraceContext` truyền ngữ cảnh; không buộc Metrics phải gọi Tracing.
- `PolicyDecision` là kết quả trung lập được Authorization cung cấp ở boundary.
- `OperationOutcome`/`ExecutionAttempt` mô tả kết quả để telemetry nhận thông tin.
- `Clock`/`Scheduler` có thể là dependency độc lập, giúp kiểm thử.

Những abstraction dùng chung cần có **quy tắc sở hữu trạng thái**; nếu mọi aspect chỉnh cùng một mutable context map không ràng buộc, vòng phụ thuộc chỉ đổi hình thức.

### 7.2. DIP và phụ thuộc vào hợp đồng

Nguyên tắc đảo ngược phụ thuộc (Dependency Inversion Principle) hữu ích trong AOP: advice phụ thuộc interface nhỏ như `MetricRecorder`, `PolicyEvaluator` hoặc `Clock` thay vì tạo thẳng database client, network exporter và cache ở trong. Điều này cho phép:

- Test advice với fake không cần dựng toàn bộ hạ tầng.
- Thay backend quan sát hay policy engine mà không đổi logic interception.
- Giữ mã nghiệp vụ độc lập với công cụ weaving cụ thể.
- Bắt rõ failure mode của dependency: không có evaluator, recorder bị lỗi, clock nhảy hoặc exporter bị nghẽn.

Không biến interface thành tầng trừu tượng vô nghĩa cho một hàm nhỏ. Đặt abstraction ở nơi nó bảo vệ ranh giới thay đổi thật.

## 8. Thứ tự composition thuộc kiến trúc, không thuộc SRP riêng lẻ

Một aspect có SRP đúng vẫn có thể làm hệ thống sai khi đặt sai thứ tự. Ví dụ:

### 8.1. Authorization và cache

~~~text
Authorization -> Cache -> Domain   (authorization chạy trên mọi đường trả)
Cache -> Authorization -> Domain   (cache hit có thể bỏ qua authorization)
~~~

Nếu cache chứa dữ liệu được bảo vệ và trả trực tiếp khi hit, chuỗi thứ hai có thể làm lộ dữ liệu. Cache key phân theo user giảm một số rủi ro nhưng **không thay thế việc kiểm tra quyền** khi quyền bị thu hồi hay context đổi. Vì vậy một `AuthorizationAspect` kết dính cao vẫn cần composition contract rõ với `CachingAspect`.

### 8.2. Retry và transaction

~~~text
Retry -> Transaction -> Domain
Transaction -> Retry -> Domain
~~~

Hai thứ tự có thể tạo khác biệt lớn. Với retry ở ngoài, mỗi attempt có thể có transaction riêng. Với transaction ở ngoài, nhiều attempt có thể nằm trong một transaction không phù hợp để khôi phục sau lỗi. Quy tắc chỉ hợp lệ khi operation cho phép retry và cơ sở dữ liệu có semantics tương ứng. Một giao dịch thất bại có thể phải rollback toàn bộ trước attempt mới; không được giả định mọi transaction vẫn usable sau bất kỳ exception nào.

### 8.3. Logging, tracing và lỗi

Nếu một error-mapping aspect bên ngoài biến exception thành kết quả fallback, một metrics aspect bên trong ghi lỗi còn một metrics aspect bên ngoài ghi success. Đây có thể đúng nếu họ đo **hai đại lượng khác nhau** (attempt outcome vs caller-visible outcome), nhưng phải đặt tên rõ. Nếu không, dashboard mâu thuẫn là dấu hiệu ranh giới contract chưa rõ.

Phân tách trách nhiệm tạo ra **những điểm phối hợp có thể nhìn thấy và kiểm thử**. Đừng để thứ tự advice phụ thuộc ngẫu nhiên vào classpath, thứ tự đăng ký không được bảo đảm hoặc tên file.

## 9. SRP có liên quan thế nào đến business rules?

Một mối quan tâm cắt ngang xuất hiện ở nhiều module chưa chắc được phép ẩn hoàn toàn trong Aspect. Quy tắc như “đơn hàng đã hủy không được giao”, “số dư không được âm”, “không chuyển tiền hai lần” thuộc bất biến domain, phải có hợp đồng nghiệp vụ và kiểm thử độc lập. Nếu chỉ có một aspect thực hiện kiểm tra, đường gọi bypass proxy/weaving có thể phá bất biến.

Aspect có thể giúp **áp dụng chính sách đã công bố** ở nhiều boundary, ví dụ một cơ chế kiểm tra quyền chuẩn. Nhưng điều kiện allow/deny phải có nguồn policy và nơi bảo vệ đáng tin. Đừng dùng một “ValidationAspect” tổng quát để biến dữ liệu sai thành dữ liệu có vẻ hợp lệ hoặc nuốt exception nhằm làm hệ thống chạy tiếp.

Một cách phân chia:

| Nhu cầu | Chủ sở hữu chính | Vai trò hợp lý của aspect |
| --- | --- | --- |
| Bất biến của entity | Domain model / service | Có thể đo/ghi outcome, không là nguồn bảo vệ duy nhất |
| Điều kiện API | API contract / boundary | Tái sử dụng validation đã khai báo, giữ nguyên lỗi |
| Kiểm soát quyền | Security policy và boundary đáng tin | Áp dụng PEP theo pointcut rõ, test bypass |
| Retry | Contract thao tác, idempotency, failure policy | Điều phối attempt đúng điều kiện |
| Audit | Hợp đồng kiểm toán và đường lưu tin cậy | Thu thập event đúng vòng đời, không biến audit thành log debug |
| Performance telemetry | Observability contract | Đo theo semantic đã chọn, giảm overhead |

**SRP không có nghĩa policy chỉ được phép xuất hiện đúng một nơi.** Có thể cần nhiều lớp bảo vệ cùng bất biến ở các boundary khác nhau; điều quan trọng là chúng có trách nhiệm và hợp đồng được đặt tên, tránh các bản sao khác nghĩa.

## 10. Độ kết dính ở những ranh giới bất đồng bộ

Một method có thể trả về `CompletionStage<T>` ngay khi công việc chưa hoàn tất. Nếu một aspect đo thành công ngay lúc method trả stage, nó đang đo **return của handle** chứ chưa đo terminal outcome của nghiệp vụ. Việc hỗ trợ async là quyết định về **semantics của policy**, không phải phép bổ sung callback tùy tiện.

Nếu `TracingAspect` cam kết quan sát một logical operation đến khi kết thúc, nó có thể cần:

- Mở span khi bắt đầu.
- Truyền context qua executor/callback một cách tường minh.
- Gắn observer vào completion stage thích hợp.
- Đánh dấu success/error/cancel/timeout đúng thời điểm.
- Đảm bảo đóng span **một lần**, tránh race giữa completion và cancellation.
- Không làm hỏng kết quả nghiệp vụ nếu exporter hỏng.

Những việc này có cohesion cao dưới một trách nhiệm tracing. Nhưng nó không có quyền tự ý quyết định retry, rollback hay đóng resource của worker khi chỉ nhìn thấy handle đã timeout.

Một `MetricsAspect` có thể ghi cùng thời gian nhưng theo ngữ nghĩa khác (thời gian queue, thời gian worker, thời gian caller chờ). Không dùng tên `latency` chung chung; định nghĩa điểm bắt đầu/kết thúc để metric có thể so sánh.

Với stream nhiều phần tử, một aspect có thể quản lý lifecycle **subscription** và một module riêng đếm item; việc chia hay gộp phụ thuộc chúng có cùng budget, owner và lý do thay đổi không. Không tạo một chuỗi aspect cho mỗi item nếu chi phí vượt ngân sách.

## 11. Lựa chọn độ hạt: quá to và quá nhỏ

### 11.1. Aspect quá lớn

Khi một aspect chứa nhiều policy độc lập, chi phí thay đổi tăng vì:

- Bề mặt test lớn và dễ có regression ngoài mục tiêu.
- Cấu hình phình ra, các tổ hợp cờ khó bao phủ hết.
- Một exception không rõ phát sinh từ rule nào.
- Các đội sở hữu policy độc lập cùng sửa một file, tăng xung đột.
- Khó benchmark chi phí riêng của từng policy.
- Khó thay một cơ chế weaving hoặc một backend mà không đụng toàn module.

### 11.2. Aspect quá nhỏ

Nếu mỗi bước của một policy thành aspect riêng, có thể gặp:

- Bắt buộc đặt thứ tự cực kỳ chi tiết để một operation đúng.
- Trạng thái `startTime` hoặc correlation context phải truyền qua nhiều nơi.
- Một thay đổi policy kéo theo chỉnh cả chuỗi component.
- Mỗi layer thêm interceptor invocation/callback, có thể tăng overhead.
- Khó truy vết vì một hành vi bị chia quá nhiều file.

Ví dụ không cần tách `LatencyStartAspect` và `LatencyStopAspect` nếu cả hai bắt buộc đi cùng nhau để đo một khoảng thời gian đúng. Around advice nhỏ gọn quản lý cả start/stop thường rõ hơn và an toàn hơn khi exception xảy ra.

### 11.3. Quy tắc chọn độ hạt

Hãy gom những thành phần có:

1. Cùng **invariant/policy**.
2. Cùng **lý do thay đổi** và owner.
3. Cùng **vòng đời invocation/context**.
4. Cùng **phạm vi pointcut** có thể giải thích.
5. Cùng **chiến lược kiểm thử**.

Hãy tách khi hai nhóm có contract, owner, thứ tự điều phối hoặc lifecycle khác nhau và có thể phát triển độc lập. Đừng quyết định chỉ bằng số lượng method, số dòng code hoặc tên “concern”.

## 12. Thiết kế pointcut để hỗ trợ cohesion

Pointcut quyết định nơi aspect chạy. Chọn sai phạm vi có thể buộc advice chứa hàng loạt nhánh đặc biệt, làm cohesion giảm:

~~~java
// GIA MA / minh hoa, khong phai API AOP cu the:
// if (methodName.startsWith("get") && !isHealthCheck()
//     && !isInternalCall() && !isCachedSpecialCase()) { ... }
~~~

Nếu liên tục phải bổ sung exception theo tên method, hãy xem lại abstraction đầu vào. Có thể nên dùng:

- **Contract/metadata** biểu đạt chính sách cần áp, ví dụ marker `@MeasuredOperation` do hệ thống tự định nghĩa.
- **API boundary** ổn định như một nhóm endpoint hoặc interface xác định.
- **Rule cấu hình có kiểm thử** mô tả các thao tác được phép, không chọn theo tên ngẫu nhiên.
- **Phân nhóm theo lifecycle**: đồng bộ, async, streaming có thể cần những advice hoặc adapter khác nhau.
- **Kiểm thử join-point coverage** để phát hiện method mới vô tình không được chặn.

Pointcut càng rộng không đồng nghĩa khả năng bao phủ càng an toàn. Nếu một Aspect bảo mật chỉ chặn method bên ngoài proxy, self-invocation có thể bypass; nếu một MetricAspect chặn cả phương thức telemetry nội bộ, nó có thể tự gọi lặp vô hạn.

## 13. Kiểm thử SRP và cohesion bằng khả năng thay đổi độc lập

Một bộ kiểm thử hữu ích gồm bốn tầng.

### 13.1. Kiểm thử riêng từng aspect

Với target giả:

- `AuthorizationAspect`: allow đi qua đúng một lần; deny không chạy target; lỗi loại đúng; không phát log chứa secret.
- `MetricsAspect`: đếm success, failure, cancellation theo hợp đồng; metric exporter fail không làm hỏng nghiệp vụ nếu chính sách cho phép.
- `TracingAspect`: context được khôi phục, span đóng đúng một lần ở mọi đường, không giữ context của invocation khác.
- `RetryAspect`: chỉ retry lỗi đủ điều kiện; bảo toàn deadline và idempotency; không nhân side effect khi không an toàn.

Không cần dựng toàn bộ application để kiểm thử một policy đơn lẻ. Nếu test phải cần mọi subsystem, aspect có thể có quá nhiều dependency.

### 13.2. Kiểm thử composition

Test riêng lẻ xanh chưa đủ. Phải xác minh thứ tự thực:

| Tình huống | Điều cần khẳng định |
| --- | --- |
| Authorization deny + metrics | Định nghĩa request/rejection được đếm đúng; domain không chạy |
| Cache hit sau khi quyền thu hồi | Không bypass kiểm tra quyền |
| Retry sau lỗi ở transaction | Transaction mới/rollback đúng policy |
| Trace khi gọi lồng nhau | Parent-child context đúng, không tạo span trùng |
| Fallback và exception mapping | Caller-visible outcome và attempt outcome được ghi khác tên |
| Async completion/timeout | Đóng observer đúng vòng đời, không phát hai terminal event |
| Self-call bypass proxy | Không làm mất invariant nghiệp vụ hoặc bảo vệ dữ liệu |
| Exporter chậm/không khả dụng | Giới hạn overhead/queue của telemetry |

### 13.3. Kiểm thử thay đổi có chủ đích

Thử thay policy logging trong test:

1. Đổi định dạng trace.
2. Xác nhận các test tracing cần cập nhật.
3. Kiểm thử authorization, business invariant, transaction và retry không đổi.

Sau đó thử thay quyền từ `operator` sang tập vai trò cấu hình: test authorization thay đổi đúng; metric semantics không vô tình đổi. Nếu cùng một thay đổi đòi sửa mọi Aspect, cân nhắc lại coupling, interface và vị trí state chung.

### 13.4. Performance và concurrency

AOP thêm code tại các join point được chặn; nhiều aspect lồng nhau có thể tăng chi phí gọi, cấp phát, context switch hoặc contention. Benchmark cả:

- Độ trễ bình thường và p99 với policy bật/tắt.
- Lượng allocation, kích thước context và overhead từng advice.
- Chi phí của pointcut matching và reflection (nếu có).
- Tác động của logging/metrics sink bị quá tải.
- Race khi aspect instance được dùng chung bởi nhiều luồng.
- Số lần invoke thực tế khi kết hợp retry, cache và transaction.

Không bỏ kiểm tra quyền vì benchmark thấy tốn kém; chọn kiến trúc tối ưu mà vẫn bảo đảm hợp đồng bảo mật.

## 14. Quy trình tái cấu trúc một aspect đang ôm quá nhiều việc

Một trình tự thực dụng giúp tách dần mà không thay đổi hành vi ngoài ý muốn:

1. **Liệt kê hành vi hiện có:** tất cả pointcut, before/around/after, exception mapping, retry, caching, transaction, audit và telemetry.
2. **Ghi lại observable contract:** khi nào target chạy, chạy bao nhiêu lần, thứ tự thay đổi trạng thái, exception/return, resource cleanup và metric.
3. **Nhóm theo lý do thay đổi:** policy nào có owner/cấu hình/vòng đời riêng; đánh dấu chỗ cần composition ordering.
4. **Viết characterization tests:** bảo toàn hành vi **hợp lệ** hiện tại, đồng thời xác định các anti-pattern phải sửa theo yêu cầu đã phê duyệt.
5. **Trích xuất dependency chung đúng tầng:** `PolicyEvaluator`, `TraceContext`, `Clock`, `CacheAdapter`; không kéo logic nghiệp vụ vào “common helper”.
6. **Tách một policy một lần:** ví dụ telemetry trước, rồi authorization, tránh thay mọi chính sách cùng lúc.
7. **Khai báo order rõ:** xem xét cache hit, denial, retry, commit và callback async ở cả đường success/failure.
8. **Chạy test integration và benchmark:** xác minh chưa mất join point, chưa đếm trùng, chưa thay exception hoặc side effect.
9. **Xóa nhánh obsolete:** sau khi policy đã tách, bỏ cờ, guard và code cũ không dùng, tránh hai đường xử lý song song.
10. **Tài liệu hóa owner và contract:** mô tả mỗi aspect chịu trách nhiệm gì, không chịu trách nhiệm gì và cách composition.

Trong refactor, **không mặc định mọi hành vi cũ đều đúng**. Nếu God Aspect đang nuốt `SecurityException`, đó là bug cần có quyết định sửa hợp đồng và bài kiểm thử phù hợp; việc giữ hành vi sai chỉ để “không đổi regression” có thể không chấp nhận được.

## 15. Dấu hiệu kiến trúc khỏe mạnh

Một aspect được thiết kế tốt thường có những đặc điểm sau:

- Tên phản ánh một policy cụ thể, ví dụ `LatencyMetricsAspect`, `AuthorizationEnforcementAspect`.
- Tập join point có chung semantics và có bài test chứng minh coverage.
- Các advice và helper phục vụ cùng một invariant hoặc một lý do thay đổi.
- Ít dependency, giao diện hẹp; dependency là interface có contract rõ.
- State theo đúng vòng đời và được xử lý an toàn khi concurrency/async.
- Exception/return không bị thay ngoài phạm vi policy công bố.
- Thứ tự với aspect khác được cấu hình, tài liệu hóa và kiểm thử.
- Không vô tình bypass bảo mật khi cache hit, retry, callback hoặc direct call.
- Metrics/log mô tả được policy nào gây thay đổi và số lần chạy.
- Khi đổi một chính sách, phạm vi code và test cần đổi có thể dự đoán được.

### 15.1. Checklist nhanh khi review

| Câu hỏi | Dấu hiệu tốt | Dấu hiệu cần xem lại |
| --- | --- | --- |
| Vì sao aspect thay đổi? | Một chủ sở hữu/policy rõ | Nhiều nhóm yêu cầu không liên quan |
| Pointcut chọn gì? | Join point cùng contract | Chọn theo tên quá rộng và nhiều ngoại lệ |
| Advice gọi target mấy lần? | Theo policy đã định | Ngầm retry hoặc bỏ qua proceed |
| State thuộc ai? | Invocation/adapter phù hợp | Trộn principal, retry count và cache state |
| Thêm tính năng mới? | Mô-đun riêng hoặc mở rộng trách nhiệm hợp lý | Thêm `if` vào aspect tổng |
| Tách một policy? | Không phải sửa các policy không liên quan | Phải sửa cả authorization, cache, metric |
| Kiểm thử được không? | Fake target + fake dependency | Cần dựng mọi hạ tầng |
| Bảo mật/consistency? | Có integration tests cho order | Dựa trên giả định thứ tự ngẫu nhiên |

**Kết luận thực hành:** một aspect có SRP tốt khi **mọi phần của nó cùng phục vụ một lý do thay đổi**, không phải khi nó ngắn nhất hoặc chỉ có một advice. Cohesion cao giúp chính sách dễ hiểu, dễ sửa và dễ kiểm thử. Khi cần nhiều aspect, hãy coi **thứ tự composition và hợp đồng nghiệp vụ** là phần thiết kế bắt buộc để các mô-đun độc lập phối hợp đúng.
