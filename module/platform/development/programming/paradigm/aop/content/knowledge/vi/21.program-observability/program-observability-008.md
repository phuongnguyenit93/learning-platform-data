# Tránh đo trùng khi có nhiều lớp Aspect hoặc công cụ quan sát

## 1. Một thao tác có thể bị đo nhiều lần

Trong **Aspect-Oriented Programming (AOP)**, một aspect có thể ghi log, tăng counter, đo thời gian hoặc tạo trace span tại các **join point** mà **pointcut** lựa chọn. Khi chương trình có nhiều aspect, proxy, decorator, interceptor và công cụ instrument tự động, một phương thức nghiệp vụ có thể bị quan sát bởi nhiều lớp.

Ví dụ:

~~~text
Caller
  -> MetricsAspect
     -> LoggingAspect
        -> AutomaticInstrumentation
           -> approveOrder() // thực thi đúng một lần
~~~

Nếu cả ba lớp đều tăng cùng counter **business_operation_completed_total** khi thao tác kết thúc, một yêu cầu phê duyệt lại bị báo thành ba lượt. Ngược lại, nếu chúng lần lượt đo **business operation**, **dependency call** và **trace child span** có ý nghĩa khác nhau, ba phép đo có thể hoàn toàn hợp lệ.

**Quy tắc:** mỗi phép đo phải có một **đơn vị được đếm**, một **sự kiện/lifecycle cụ thể** và một **chủ sở hữu tín hiệu** rõ ràng. Tránh nhiều lớp cùng phát một sự kiện có cùng ngữ nghĩa cho cùng một occurrence. Không gộp hoặc xóa những sự kiện độc lập chỉ vì cùng method name hoặc trace ID.

## 2. Xác định chính xác thế nào là trùng

Một **join point** có thể được nhiều pointcut và advice chọn; nhiều proxy, decorator hoặc công cụ instrumentation có thể cùng quan sát một đường gọi. Tuy nhiên, **occurrence** là *một lần xảy ra thật* của đơn vị đã định nghĩa (request, operation, attempt, call hoặc span), còn **semantic duplicate** là việc nhiều tín hiệu cùng biểu diễn *chính occurrence ấy ở cùng cấp độ và cùng ngữ nghĩa* do nguồn đo hoặc pipeline lặp.

Hai dòng log cho một method không tự chứng minh đo trùng: đó có thể là hai lần gọi thật, cặp start/end, các attempt khác nhau hoặc span cha–con. Phải xác định **đơn vị, mốc kết thúc và nguồn sở hữu phép đo** trước khi loại bỏ tín hiệu.

## 3. Các cấp độ quan sát khác nhau

~~~text
Một HTTP request
  -> Một business operation
     -> Attempt 1 (timeout)
     -> Attempt 2 (success)
        -> Dependency call A
        -> Dependency call B
~~~

Bảng mô tả những đơn vị thường bị trộn:

| Cấp độ | Một đơn vị | Tín hiệu phù hợp | Khi nào được có nhiều? |
| --- | --- | --- | --- |
| Request | Một request giao thức | request count, latency | Có nhiều request thực |
| Business operation | Một lần yêu cầu thực hiện use case | operation outcome, end-to-end duration | Có nhiều operation độc lập |
| Attempt | Một lượt thử hoặc retry | attempt count, attempt duration | Một operation có thể retry |
| Dependency call | Một lần gọi thành phần phụ thuộc | call outcome, dependency duration | Có fan-out hoặc retry thật |
| Method invocation | Một lần gọi/thực thi method | method timer, debug trace | Có nhiều lần gọi thực |
| Trace span | Một đoạn công việc có phạm vi | span start/end và thuộc tính | Có nhiều span cha/con khác nhau |
| Audit event | Một chuyển trạng thái được xác nhận | event có ID và actor | Có nhiều chuyển trạng thái thực |

Không so sánh thẳng **operation count** với **dependency count** để kết luận sai lệch. Không xem nhiều span trong một trace là duplicate: span cha và span con có nhiệm vụ riêng. Nếu chúng cùng cố mô tả chính một outbound call ở cùng cấp độ, mới có khả năng semantic duplicate.

## 4. Dấu hiệu và tác hại

### Đếm sai số lần xử lý

Một operation thành công nhưng counter tăng hai, khiến throughput và conversion bị nhân đôi. Nếu mỗi attempt thất bại được ghi là lỗi của operation, tỷ lệ lỗi cũng bị thổi phồng dù retry sau cùng đã thành công.

### Histogram bị pha trộn phạm vi

Một timer đo method return sau 2 ms, timer khác đo completion sau 700 ms, nhưng cả hai gửi vào cùng histogram **business_operation_duration_seconds**. Thống kê p95 không còn một ý nghĩa rõ ràng.

### Trace có hai span mô tả cùng hành động

Ví dụ hai instrumenter cùng tạo span "outbound HTTP call" quanh một network request. Số span và tài nguyên lưu trữ tăng, biểu đồ trace khó đọc, có thể hiểu lầm tồn tại hai network call.

### Nhật ký nhân bản

Một event "order.approved" được ghi cả từ aspect bên ngoài và interceptor bên trong; một appender hoặc pipeline chuyển tiếp cũng có thể ghi lại hai lần. Người vận hành khó biết có hai hành động nghiệp vụ thật hay chỉ một hành động bị ghi trùng.

### Overhead tăng

Thêm proxy, callback, capture context, serialization, allocation, metric label, log I/O và exporter queue có thể tiêu tốn CPU, bộ nhớ, lưu trữ và tăng latency. Mức tăng phụ thuộc implementation; không có công thức chung "hai aspect thì chậm gấp đôi".

**Lưu ý:** một log bắt đầu và một log kết thúc của cùng operation không bị coi là trùng, nếu hai event có loại khác nhau.

## 5. Bảy nguồn thường gây trùng phép đo

### 5.1. Hai aspect cùng phát một counter

**MetricsAspect** và **ObservabilityAspect** đều bắt phương thức nghiệp vụ, mỗi aspect tăng một counter có cùng tên, nhãn và định nghĩa. Lời gọi chạy một lần nhưng counter tăng hai.

**Giải pháp:** phân định chủ sở hữu; aspect kia chuyển thành context enrichment hoặc đo tín hiệu khác.

### 5.2. Pointcut quá rộng hoặc chồng lấn

Một pointcut chọn tất cả public methods trong package nghiệp vụ; pointcut khác chọn các method có annotation đánh dấu operation. Phương thức thỏa cả hai bị đo nhiều lần. Cũng có thể đăng ký cùng advice hai lần qua cấu hình.

**Giải pháp:** chọn một pointcut chuẩn ở boundary, đặt exclusion hoặc tách phạm vi theo semantic scope; kiểm tra chính tập join point được instrument lúc runtime.

### 5.3. Nhiều proxy/decorator bao quanh cùng đối tượng

Service có thể bị bọc nhiều tầng. Mỗi tầng thấy cùng lời gọi, nhưng không phải tầng nào cũng là ranh giới business operation. Cơ chế proxy có thể bỏ qua self-invocation, trong khi kiểu weaving khác có thể quan sát những join point khác; cần kiểm tra đường gọi thực tế.

**Giải pháp:** chọn tầng sở hữu operation metric, đặt tên phép đo khác cho các lớp hợp lệ còn lại.

### 5.4. Instrumentation thủ công và tự động

Code tự tạo span cho một dependency call, trong khi công cụ quan sát tự động cũng tạo span cho chính call ấy. Nếu cùng ngữ nghĩa, chúng có thể là semantic duplicate. Nếu span thủ công đại diện cả repository operation, span tự động đại diện network request bên trong thì cả hai hợp lệ: đặt tên, quan hệ cha/con và phạm vi riêng.

**Giải pháp:** kiểm kê instrumenter, xác định tầng tạo span, vô hiệu hóa đúng một nguồn cho đúng scope bị trùng.

### 5.5. Retry làm số attempt nhiều hơn operation

RetryAdvice có thể gọi phần nghiệp vụ bên trong ba lần; một aspect trong retry thấy ba attempts, aspect ngoài retry thấy một operation. Nếu cả hai dùng metric name "operation_total", số liệu mất ý nghĩa.

**Giải pháp:** bộ đếm attempt và operation khác tên; business outcome ghi tại tầng biết kết quả cuối.

### 5.6. Async: đo ở cả return và completion

Method trả CompletionStage nhanh rồi task mới thực thi. Nếu một advice ghi "success" lúc method return, observer khác ghi "success" khi stage hoàn tất, vừa đo trùng vừa đánh đồng **trả handle** với **hoàn thành công việc**.

**Giải pháp:** sự kiện "submitted/invocation_returned" khác "operation_completed". Chỉ observer có lifecycle phù hợp tăng operation completion counter.

### 5.7. Event lặp ở collector, storage hoặc dashboard

Ứng dụng có thể phát một lần nhưng message được replay; một exporter bị scrape qua hai đường; dashboard cộng dữ liệu thô với dữ liệu đã tổng hợp. Lỗi nằm sau nguồn phát, không nhất thiết ở các aspect.

**Giải pháp:** so sánh event ở producer, collector, storage và query; dùng event identity phù hợp để nhận diện delivery duplicate, xem lại aggregation và source labels.

## 6. Thiết kế hợp đồng đo lường trước khi code

Một phép đo nên trả lời bốn câu hỏi:

1. **Tôi đang đếm cái gì?** Một request, một business operation, một attempt, một call hay một span?
2. **Mốc nào xác nhận điều được đo?** Khi vào lời gọi, sau method return, khi callback chạy, sau commit hay sau task thực sự dừng?
3. **Ai được quyền ghi?** Aspect, interceptor, exporter hay một công cụ tự động?
4. **Tín hiệu nào thể hiện kết quả?** success, rejected, failed, cancelled hoặc trạng thái khác theo contract?

Có thể lập **ownership matrix**:

| Tín hiệu | Nguồn phát chuẩn | Đơn vị | Thời điểm |
| --- | --- | --- | --- |
| business_operation_completed_total | Advice tại boundary use case | Operation | Sau outcome cuối |
| business_operation_duration | Cùng boundary hoặc observer completion | Operation | Mốc kết thúc theo contract |
| business_operation_finished log | Chủ sở hữu business outcome | Operation | Một event kết thúc |
| attempt_total | Retry controller / attempt advice | Attempt | Sau mỗi attempt |
| dependency_call_duration | Interceptor ở dependency boundary | Dependency call | Sau call |
| request_total | Thành phần quan sát giao thức | Request | Sau request |
| diagnostic child span | Instrumenter sở hữu bước con | Child work scope | Theo span lifecycle |

Hai công cụ vẫn có thể hoạt động cùng nhau, miễn không phát lại cùng một tín hiệu ở cùng cấp độ. Nếu cần đo cả HTTP latency và business latency, dùng tên và nhãn khác nhau; không nhập chung histogram.

## 7. Ví dụ Java 17 chạy được: hai advice đếm trùng

Ví dụ dùng JDK dynamic proxy để mô phỏng hai lớp advice cùng chặn một interface method. Cấu hình đầu ghi hai business metrics cho một lời gọi; cấu hình sau chỉ một lớp sở hữu counter và lớp kia phụ trách trace riêng.

Tạo file **DuplicateObservationDemo.java**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class DuplicateObservationDemo {
    interface ApprovalService {
        String approve(String orderId);
    }

    static final class RealApprovalService implements ApprovalService {
        @Override
        public String approve(String orderId) {
            return "APPROVED";
        }
    }

    static final class Counter {
        int completed;

        void record(String source) {
            completed++;
            System.out.println("COUNT source=" + source
                    + " operation=order.approve");
        }
    }

    static Object proceed(Object target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static ApprovalService withCounter(
            ApprovalService next, Counter counter, String owner) {
        return (ApprovalService) Proxy.newProxyInstance(
                ApprovalService.class.getClassLoader(),
                new Class<?>[] { ApprovalService.class },
                (proxy, method, args) -> {
                    Object value = proceed(next, method, args);
                    if (method.getName().equals("approve")) {
                        counter.record(owner);
                    }
                    return value;
                });
    }

    static ApprovalService withTrace(ApprovalService next) {
        return (ApprovalService) Proxy.newProxyInstance(
                ApprovalService.class.getClassLoader(),
                new Class<?>[] { ApprovalService.class },
                (proxy, method, args) -> {
                    boolean observe = method.getName().equals("approve");
                    if (observe) {
                        System.out.println("TRACE operation=order.approve start");
                    }
                    try {
                        return proceed(next, method, args);
                    } finally {
                        if (observe) {
                            System.out.println("TRACE operation=order.approve end");
                        }
                    }
                });
    }

    public static void main(String[] args) {
        ApprovalService real = new RealApprovalService();

        Counter duplicated = new Counter();
        ApprovalService wrong = withCounter(
                withCounter(real, duplicated, "inner"),
                duplicated, "outer");
        System.out.println("result=" + wrong.approve("A-101"));
        System.out.println("duplicate_count=" + duplicated.completed);

        Counter correct = new Counter();
        ApprovalService fixed = withCounter(
                withTrace(real), correct, "business-boundary");
        System.out.println("result=" + fixed.approve("A-102"));
        System.out.println("correct_count=" + correct.completed);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DuplicateObservationDemo.java
java DuplicateObservationDemo
~~~

Stdout chính xác:

~~~text
COUNT source=inner operation=order.approve
COUNT source=outer operation=order.approve
result=APPROVED
duplicate_count=2
TRACE operation=order.approve start
TRACE operation=order.approve end
COUNT source=business-boundary operation=order.approve
result=APPROVED
correct_count=1
~~~

**Phân tích:**

- Cả hai lần thử đều gọi business method đúng một lần. Chỉ cấu hình sai mới đếm hai business completions.
- Ở cấu hình đúng, việc in hai dòng TRACE đại diện start/end của một phạm vi, không phải hai business operations. Hệ thống tracing thật tạo một span có context, start/end và quan hệ parent phù hợp.
- Lớp **withCounter** chỉ ghi thành công khi method trả bình thường. Ứng dụng thật phải quy định cả failed/rejected/cancelled theo outcome contract; không đếm là success chỉ vì trả về một đối tượng lỗi.
- **Counter** dùng int cho demo tuần tự; bộ đếm thực tế cần an toàn khi chạy đồng thời, cùng schema và cardinality phù hợp.
- Hàm **proceed** gỡ InvocationTargetException do reflection bọc để giữ nguyên kiểu lỗi gốc.
- Ví dụ dùng proxy để mô tả nguyên lý AOP chung; không giả định mọi cơ chế AOP chặn được cùng tập join point.

**Bài học từ ví dụ:** không cần bỏ hết lớp quan sát. Cần để mỗi lớp cung cấp tín hiệu có ý nghĩa riêng và một nguồn duy nhất đếm completion của operation.

## 8. Thứ tự aspect, retry và thời gian đo

Cùng một lời gọi có hai cách bọc:

~~~text
A: OperationTimer -> RetryAdvice -> BusinessCall
B: RetryAdvice -> AttemptTimer -> BusinessCall
~~~

Trong **A**, timer ngoài đo cả operation, bao gồm các attempt và khoảng nghỉ giữa các lần nếu retry thực hiện việc chờ ở trong. Trong **B**, timer trong được gọi mỗi attempt, tạo N mẫu khi có N attempt. Đó là dữ liệu hợp lệ nếu B ghi **attempt_duration**, không phải **operation_duration**.

~~~text
OperationTimer
  -> RetryAdvice
      -> AttemptTimer
          -> BusinessCall
    1 operation sample
    N attempt samples
~~~

Một operation thành công sau ba attempts có thể có:

- **operation_total{outcome=success}: +1**
- **attempt_total{outcome=failed}: +2**
- **attempt_total{outcome=success}: +1**

Đây không phải đo trùng; nếu dùng tên operation failure cho hai attempt thất bại, đó là sai đơn vị. Thứ tự các aspect cũng tác động đến việc advice thấy lỗi attempt hay kết quả cuối. Không chỉ đọc cấu hình trên giấy; kiểm tra thứ tự bọc và đường gọi thực tế.

Cache cũng ảnh hưởng ngữ nghĩa. Timer ngoài cache thấy cả cache hit và miss; timer trong cache chỉ thấy lần thật sự gọi target. Hai thời gian này không nên nhập chung nếu chúng trả lời hai câu hỏi khác nhau.

## 9. Pointcut chồng lấn: sửa tại nguồn

Ví dụ ba pointcut:

~~~text
P1: mọi method trong nhóm use case
P2: mọi method có annotation chỉ operation
P3: mọi public method thuộc package nghiệp vụ
~~~

Nếu cùng method khớp cả P1, P2 và P3, có thể có ba advice quanh cùng join point. Những hành động nên thực hiện:

1. Xác định một **pointcut chuẩn** cho business outcome hoặc dùng annotation/contract quy ước rõ.
2. Thu hẹp P3 để tránh các method đã có owner; đặt exclusion theo chức năng thực tế nếu công cụ hỗ trợ.
3. Đặt tên metric của P1/P2 riêng nếu chúng cố ý đo **hai cấp độ khác nhau**.
4. Loại registration trùng của cùng interceptor/aspect do module cấu hình.
5. Kiểm tra thực nghiệm tập join point: method qua proxy có thể được chặn khác self-invocation; weaving ở call/execution join point có thể khác proxy.
6. Thêm kiểm thử bật **tất cả** aspect/công cụ quan sát, vì test từng aspect riêng không phát hiện trùng khi ghép.

Pointcut tốt biểu diễn ngữ nghĩa và phạm vi. Không nên chọn mọi getter, helper hoặc mọi method public chỉ vì dễ cấu hình, nhất là khi dự định dùng dữ liệu đó để đếm business operations.

## 10. Khi nào nên sử dụng guard chống lặp?

Guard hữu ích cho **reentrancy**: code ghi log lại gọi một method được pointcut chặn, khiến advice tự kích hoạt mãi. Một guard cục bộ cùng thread có thể hỗ trợ:

~~~text
advice:
    if alreadyInsideThisInstrumentationOnCurrentThread:
        return proceed()
    markEntered()
    try:
        return observeAndProceed()
    finally:
        clearMarker()
~~~

Đây là giả mã; không phải Java độc lập. Hạn chế:

- Nếu hai instrumenter độc lập, guard riêng của mỗi bên **không ngăn chúng cùng đếm**.
- Một request có hai nested business operations hợp lệ có thể bị guard quá rộng xóa mất phép đo của operation bên trong.
- Boolean toàn cục gây lỗi giữa các request đồng thời.
- ThreadLocal không tự truyền sang executor và phải được cleanup trên chính thread dùng nó. Không giữ marker từ invocation ngắn cho đến callback async nếu scope không hỗ trợ.
- Khi task được retry hoặc chạy lại, cần giữ ngữ nghĩa operation/attempt rõ ràng; không xem mọi lần gọi lại là duplicate.

**Ưu tiên thiết kế một owner trước khi thêm runtime guard.** Guard chống recursion và cơ chế dedup dựa trên event identity xử lý hai loại lỗi khác nhau.

## 11. Identity: trace, operation, attempt, event

Những định danh có vai trò khác nhau:

| Định danh | Đại diện | Không nên dùng để |
| --- | --- | --- |
| trace_id | Một trace bao nhiều span/operation | Dedup tất cả sự kiện trong cùng trace |
| operation_id | Một occurrence của use case | Xóa attempt hợp lệ bên trong |
| attempt_id | Một lượt thử cụ thể | Coi mọi retry là một attempt |
| event_id | Một event logic được phát ra | Coi mọi event chung operation là trùng |
| message_id | Một thông điệp logic | Xóa dấu vết các lần delivery/processing hợp lệ |

Ví dụ:

~~~text
trace = T5
  operation = O8, order.approve
    attempt A1 -> timeout
    attempt A2 -> success
  operation outcome -> success
~~~

Hai attempt hợp lệ, một business outcome. Nếu event completion được vận chuyển hai lần với cùng **event_id**, pipeline có thể loại duplicate delivery theo quy tắc phù hợp; không xóa event attempt chỉ vì có cùng trace hoặc operation ID.

Nếu dùng cache ID đã gặp để dedup, cần định nghĩa TTL, dung lượng, chia sẻ state giữa instance, restart và các trường hợp eviction. Sự trùng chuỗi log hay timestamp gần nhau chưa đủ để xác minh cùng occurrence. Không đặt ID theo request/user/trace thành label metric phổ biến vì cardinality có thể tăng mạnh.

## 12. Log: phân biệt sự kiện với bản ghi lặp

Những dòng sau không phải đo trùng:

~~~text
operation=order.approve event=started  operation_id=O8
operation=order.approve event=finished operation_id=O8 outcome=success
~~~

Vì chúng biểu diễn hai mốc khác nhau. Ngược lại:

~~~text
operation=order.approve event=finished operation_id=O8 outcome=success source=A
operation=order.approve event=finished operation_id=O8 outcome=success source=B
~~~

có thể là hai instrumentation sources cùng phát một business completion. Cũng có thể một collector ghi cùng event hai lần; cần kiểm tra event_id và nguồn thực tế.

Để điều tra, thử log trong môi trường kiểm thử:

- instrumentation source và version của aspect;
- semantic operation name và occurrence ID;
- event type (started, finished, attempt_failed...);
- trace/span ID nếu phù hợp;
- nơi log được gửi/thu thập.

Không nên log tràn lan toàn bộ args, token, session secret, thông tin thanh toán hoặc nội dung người dùng để tìm nguyên nhân đếm trùng. Structured logging với schema ổn định, chính sách redaction và encoding giúp an toàn và dễ đối chiếu hơn.

## 13. Metrics: double count tại nguồn và tại truy vấn

Giả sử một metric counter được tăng hai lần ở ứng dụng, hai mẫu đã sai từ producer. Nhưng có trường hợp ứng dụng chỉ phát một lần mà số liệu dashboard vẫn gấp đôi:

- Exporter bị scrape qua hai target trong cùng phép cộng.
- Một pipeline đưa cùng series vào hai kho rồi truy vấn hợp nhất không loại duplicate.
- Recording rule cộng dữ liệu đã tổng hợp cùng dữ liệu thô.
- Cấu hình federation/remote forwarding chuyển cùng measurement theo hai nhánh.
- Nhãn source bị xử lý khiến nhiều phiên bản series nhập chung sai.

Để định vị:

1. Kiểm tra số event/counter increment ngay tại unit test/in-memory collector.
2. Kiểm tra dữ liệu exporter phát ra.
3. Kiểm tra số bản ghi/series được collector nhận.
4. Kiểm tra storage và query aggregation.
5. Thay đổi **tầng gây trùng**; không sửa bừa pointcut nếu producer đã đúng.

Với histogram, một operation nên đóng góp một mẫu theo định nghĩa duration của nó. Nếu có sampling, so sánh count của histogram với counter chưa sampling sẽ không công bằng. Chênh lệch giữa thời điểm flush, trạng thái pending và cửa sổ query cũng tạo sai khác không phải duplicate.

## 14. Trace spans: span cha/con khác span trùng

Ví dụ hợp lệ:

~~~text
span business.operation (150 ms)
  span repository.load (60 ms)
    span database.query (40 ms)
~~~

Ba span phản ánh ba phạm vi lồng nhau. Không cộng 150 + 60 + 40 để kết luận request mất 250 ms: span cha đã bao một phần thời gian con.

Ví dụ đáng nghi:

~~~text
span http.client.request (42 ms) [manual instrumenter]
span http.client.request (40 ms) [automatic instrumenter]
       đúng một HTTP call
~~~

Nếu hai span này cùng đại diện toàn bộ một HTTP request ở cùng cấp, nguồn có thể trùng. Cần kiểm tra instrumenter, operation name, span kind, peer, parent, call site và thời điểm. Nếu manual span thật ra đo công việc chuẩn bị/phân tích thêm, nên đặt tên khác như **dependency.enrichment** hoặc **repository.load** và ghi quan hệ phù hợp.

Không lọc bằng span name đơn thuần: hai HTTP call khác nhau có thể cùng span name; một trace có thể lặp lệnh SQL hợp lệ.

## 15. Bất đồng bộ: khác biệt invocation và completion

Một method có thể trả về:

~~~java
CompletionStage<Receipt> submitApprovalAsync(Command command);
~~~

Đây chỉ là khai báo API minh họa. Khi gọi:

~~~text
enter advice
    proceed() -> trả stage
leave advice -> invocation kết thúc
                         task xử lý...
                         stage completed
~~~

Nếu **after-returning advice** ghi business success, stage có thể chưa chạy hoặc cuối cùng thất bại. Phân biệt:

- **invocation_returned:** method trả handle, chưa biết kết quả cuối.
- **operation_submitted:** một tác vụ được chấp nhận submit nếu contract thực sự bảo đảm điều đó.
- **operation_completed:** tín hiệu kết thúc hợp lệ theo API, có outcome cuối.
- **task_released_resources:** task đã cleanup khi thực sự dừng; không đồng nhất với timeout trên handle.

Với CompletionStage, một observer có thể đăng ký **whenComplete**, nhưng mỗi observer ghi cùng counter sẽ tạo duplicate. Cần một chủ sở hữu outcome; observer khác có thể thêm trace context hoặc tín hiệu khác. Callback có thể chạy trên thread khác hoặc ngay khi stage đã hoàn tất; mã callback phải nhẹ, không giả định ThreadLocal caller còn hợp lệ. Nếu callback ném lỗi, dependent stage có thể thay đổi trạng thái; instrumentation cần chính sách bảo toàn kết quả nghiệp vụ.

Với Future thường, không nên gọi **get()** trong advice chỉ để đo, vì sẽ chặn lời gọi và có thể gây deadlock. Với Publisher/lazy stream, creation khác subscription/completion; không tự subscribe chỉ để ghi log. Với một workflow có nhiều child tasks, completion của một nhánh chưa phải completion của operation toàn bộ.

Timeout/cancellation cũng phải được mô tả đúng: handle có thể timeout trước khi task nền dừng. Một event "finished" phải có contract minh bạch; không gắn chuyện đóng tài nguyên nền vào một observer bên ngoài nếu task còn sử dụng chúng.

## 16. Retry và phân phối: tại sao exactly-once không tự xuất hiện?

Trong hệ thống phân tán, một message có thể được giao lại, request được client retry, task được executor resubmit hoặc collector gửi lại telemetry. Đó có thể là **lần xử lý mới thật**, **lần truyền event cũ** hoặc **chỉ bản sao khi truy vấn**.

Cách nhìn đúng:

1. **Business idempotency:** một lệnh có được phép tạo side effect nhiều lần hay không? Đây là trách nhiệm thiết kế nghiệp vụ, không phải của aspect logging.
2. **Measurement ownership:** trong mỗi lần xử lý, ai đếm operation và ai đếm attempt?
3. **Event delivery:** nếu một event được gửi lặp, có event ID ổn định và cách lưu dấu thích hợp không?
4. **Query correctness:** có cộng cùng dòng telemetry hai lần không?

AOP không tự cung cấp giao dịch, durable event hay bảo đảm thực thi **exactly once** xuyên service. Nếu cần dedup bền vững qua nhiều instance, phải xác định storage, TTL, tính nhất quán và khả năng retry của cơ chế lưu dấu. Không thể kết luận “một business outcome” chỉ từ việc nhìn log bằng mắt.

## 17. Bảo vệ hành vi của chương trình khi instrument

Một around advice lý tưởng cho quan sát cần:

- Chỉ gọi **proceed() đúng một lần**, trừ khi retry là chủ đích được đặc tả riêng.
- Trả lại result gốc hoặc propagate đúng exception; không nuốt lỗi, không chuyển failed thành success.
- Ghi metric theo **outcome đã định nghĩa**, không máy móc coi mọi method return là nghiệp vụ thành công.
- Không mở resource/lock của lời gọi ngắn rồi giữ cho công việc bất đồng bộ kéo dài.
- Không dùng logger/collector có thể block vô hạn trong đường request nếu mục tiêu vận hành không cho phép.
- Có phương án cho lỗi bên observer, tránh logging/serialization exception che lỗi nghiệp vụ.
- Dùng **System.nanoTime()** cho chênh lệch duration trong cùng tiến trình; không cộng các duration lồng nhau như thể độc lập.
- Chỉ capture context tối thiểu, có chính sách bảo mật và scope cleanup rõ.

Một guard chống recursion đôi khi cần thiết, nhưng không thay thế ownership matrix và không nên gây mất signal từ nested operation hợp lệ.

## 18. Kiểm thử tránh đo trùng

Dùng bộ ghi event/metric trong bộ nhớ hoặc sink thử nghiệm để kiểm tra **số occurrence và semantic scope**, không kiểm thử các chuỗi log ngẫu nhiên hoặc timing chính xác từng nanosecond.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Một operation thành công | Một success outcome và một duration cấp operation |
| Hai aspect chồng pointcut | Vẫn đúng một owner business completion |
| Một method helper được gọi nhiều lần | Không phát thêm business operation outcome |
| Operation thất bại | Một failed outcome, không cộng success |
| Retry hai lỗi rồi thành công | Một operation success; ba attempts nếu instrument attempt |
| Nested use case độc lập | Mỗi operation hợp lệ được đo riêng |
| Hai nguồn tracing chồng lấn | Không có semantic duplicate span cho cùng call |
| Async stage trả trước khi xong | Return không được đếm như final completion |
| Timeout/cancel | Mốc handle và task lifecycle được tách đúng |
| Thread pool reuse | Context/guard không rò sang task sau |
| Event gửi lặp ở collector | Đếm đúng nếu pipeline có chính sách dedup |
| Logger/observer ném exception | Kết quả nghiệp vụ tuân chính sách bảo toàn đã định |
| Hai instrumenter được bật đồng thời | Số signal đúng tại producer và backend |

Một phép kiểm tra bất biến trong điều kiện **N operation đồng bộ đã kết thúc, không retry, không sampling** có thể là:

~~~text
operation_completed_total delta = N
operation_duration_sample_count delta = N
success + rejected + failed + cancelled delta = N
~~~

Điều này chỉ đúng nếu các outcome được định nghĩa loại trừ nhau và bao phủ đầy đủ. Với async pending, dropped telemetry, sampling hoặc các cửa sổ thời gian khác nhau, cần điều chỉnh cách đối chiếu.

## 19. Quy trình truy tìm số liệu bị nhân đôi

**Bước 1: xác nhận đơn vị.** Giá trị kỳ vọng là số request, operation, attempt hay dependency call? Chọn đúng nguồn xác thực occurrence.

**Bước 2: tìm điểm nhân đôi sớm nhất.** Dùng một lời gọi có ID cố định trong môi trường kiểm thử, đếm event ngay sau advice, tiếp đó qua exporter/collector/storage và dashboard. Chỗ đầu tiên biến 1 thành 2 là nơi cần sửa.

**Bước 3: vẽ call chain.** Xác định thứ tự aspect và nơi từng metric được tăng; bao gồm registration của tool tự động và manual instrumentation.

**Bước 4: đọc pointcut và scope.** Kiểm tra match chồng lấn, proxy lồng, annotation, advice order, self-invocation, recursion và các đường đi khác nhau.

**Bước 5: chọn một owner.** Giữ business counter ở ranh giới có đủ contract outcome; chuyển tín hiệu bên trong sang attempt/dependency hoặc trace riêng nếu có ý nghĩa.

**Bước 6: kiểm thử các đường đặc biệt.** Success, failed, rejected, retry, nested operation, asynchronous completion, timeout/cancel và lỗi của observer.

**Bước 7: giám sát sau sửa.** So đối chiếu request count, business operation count, attempts và latency histogram trong cùng cửa sổ với nhãn và sampling policy tương thích.

## 20. Những sai lầm phổ biến

**“Hai span cùng tên là trùng.”** Không đủ: cần identity occurrence, instrumenter và scope. Nhiều call khác nhau có thể dùng cùng span name.

**“Mọi metric count phải bằng nhau.”** Không: một request có nhiều business operations, một operation có nhiều attempts, một attempt có nhiều dependency calls.

**“Lọc ở dashboard là đủ.”** Có thể che duplicate trong query nhưng không sửa counter đã tăng sai, log đã ghi đôi hoặc observer đã thay đổi behavior.

**“Dùng một boolean toàn cục để chống trùng.”** Làm mất phép đo của request chạy song song. ThreadLocal cũng có giới hạn qua async và nested operation.

**“Tắt tất cả log bên trong operation.”** Có thể làm mất dependency failure hay business milestone hữu ích. Cần phân biệt event có ý nghĩa khác nhau với event outcome ghi trùng.

**“Method return tức operation thành công.”** Sai với Result.Failure, Future, CompletionStage, task fire-and-forget và transaction có commit trễ.

**“Thấy số liệu x2 thì lỗi ở aspect.”** Cũng có thể là collector retry, exporter scrape trùng, recording rules hoặc query aggregation.

**“Một method bị intercept hai lần nghĩa là business logic chạy hai lần.”** Interception có thể nhiều lớp trong khi proceed chain chỉ vào target một lần. Ngược lại, lỗi advice gọi proceed nhiều lần mới thật sự có nguy cơ lặp side effect.

## 21. Checklist thực hành

- [ ] Mỗi signal có tên, đơn vị đo, điểm kết thúc và owner rõ.
- [ ] Tên metric khác nhau khi phạm vi operation, attempt, dependency hoặc invocation khác.
- [ ] Pointcut đủ hẹp, kiểm tra overlap và đăng ký lặp.
- [ ] Mọi nguồn manual và automatic instrumentation đã được kiểm kê.
- [ ] Không có hai nguồn cùng phát final outcome của một operation occurrence.
- [ ] Trace span cha/con hợp lệ được giữ; semantic duplicate cùng scope được loại.
- [ ] Counter và histogram dùng labels cardinality thấp và cùng contract đo.
- [ ] Async return, task completion, cancellation và timeout được phân biệt.
- [ ] Retry không bị ghi thành nhiều business operations nếu đó chỉ là các attempts.
- [ ] Context/guard cleanup đúng thread và đúng lifecycle.
- [ ] Truy vấn và collector đã được kiểm tra nếu producer phát đúng mà dashboard sai.
- [ ] Unit/integration tests bật nhiều aspect cùng lúc và khẳng định số event chính xác.
- [ ] Ghi log không làm lộ dữ liệu nhạy cảm và instrumentation không đổi hành vi nghiệp vụ.

**Kết luận kiến thức:** giải pháp bền vững là **mỗi tín hiệu có chủ sở hữu và ngữ nghĩa rõ ràng**, thay vì cố ép toàn hệ thống chỉ còn một aspect, một log hay một span. Một business operation được đếm một lần ở cấp operation; các attempt, dependency call và span con thực sự khác biệt vẫn được quan sát đầy đủ.