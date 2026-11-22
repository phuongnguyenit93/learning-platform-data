# Chọn mối quan tâm đủ ổn định để tách thành Aspect

## 1. Mục tiêu của quyết định kiến trúc

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP)**, một **aspect** tập trung xử lý một mối quan tâm xuyên suốt (**cross-cutting concern**) xuất hiện tại nhiều vị trí trong hệ thống. Các mối quan tâm thường gặp gồm ghi nhật ký tại ranh giới nghiệp vụ, đo lường, tracing, kiểm soát truy cập, giao dịch, kiểm toán hoặc cơ chế giới hạn tài nguyên.

Tuy nhiên, **việc một đoạn mã lặp lại nhiều lần chưa đủ để biến nó thành aspect**. Logic có thể lặp vì nhiều use case chia sẻ cùng quy tắc nghiệp vụ, cùng thuật toán hoặc cùng đối tượng miền. Những phần này thường phù hợp hơn với service, component, hàm chung hoặc abstraction nghiệp vụ tường minh.

Tách thành aspect là một quyết định về **ranh giới trách nhiệm**: hành vi được đưa ra khỏi thân chương trình nhưng vẫn được thực thi bằng cách chặn các điểm thích hợp. Vì thế cần xem xét cả **độ ổn định của quy tắc**, **độ ổn định của điểm cắt**, **tính nhất quán giữa các nơi áp dụng**, **hợp đồng lỗi**, **khả năng kiểm thử** và **chi phí diễn giải hành vi ẩn**.

**Luận điểm chính:** chỉ nên chọn một concern làm aspect khi nó có chính sách đủ chung và bền vững, có điểm áp dụng xác định được, ít phụ thuộc chi tiết nội bộ của từng use case và đem lại lợi ích nhất quán lớn hơn độ phức tạp của cơ chế interception.

## 2. Các thuật ngữ nền tảng của AOP

- **Concern:** một mối quan tâm hoặc trách nhiệm của hệ thống, chẳng hạn bảo mật hay ghi log.
- **Cross-cutting concern:** concern áp dụng trên nhiều thành phần hoặc luồng xử lý, làm mã xử lý phân tán nếu viết trực tiếp ở từng nơi.
- **Join point:** điểm trong hoạt động chương trình mà cơ chế AOP có thể can thiệp, chẳng hạn lần gọi hoặc thực thi một phương thức. Loại join point được hỗ trợ tùy cơ chế.
- **Pointcut:** quy tắc chọn một tập join point để áp dụng hành vi chung.
- **Advice:** hành vi chạy before, after, after returning, after throwing hoặc around join point, tùy mô hình AOP.
- **Aspect:** đơn vị đóng gói pointcut cùng advice cho một hoặc nhiều chính sách liên quan.
- **Weaving/interception:** cách đưa advice vào đường thực thi, có thể qua công cụ biến đổi mã hoặc lớp trung gian kiểu proxy/interceptor.
- **Proceed:** hành động cho phép đường thực thi tiếp tục tới join point/chuỗi advice tiếp theo; lời gọi quanh proceed có thể mang ý nghĩa khác nhau tùy hệ thống AOP.

Điểm quan trọng về mặt kiến trúc: **aspect không phải nơi chứa mọi logic dùng chung**. Nó là nơi quản lý một chính sách hoặc hành vi áp dụng **theo các join point được chọn**, thường không nằm trong API nghiệp vụ công khai. Nếu caller cần chủ động chọn chính sách tại từng lần gọi, một lời gọi API rõ ràng có thể phù hợp hơn.

## 3. Phân biệt ba loại mã thường bị nhầm

| Loại trách nhiệm | Ví dụ | Giải pháp thường phù hợp |
| --- | --- | --- |
| Quy tắc nghiệp vụ dùng chung | Tính chiết khấu theo hợp đồng, định giá, xác nhận hạn mức | Domain service, policy object, hàm nghiệp vụ |
| Cơ chế hạ tầng tái sử dụng | Serialize dữ liệu, truy vấn kho lưu trữ, gửi HTTP | Thư viện, component, adapter |
| Chính sách áp dụng tại nhiều boundary | Ghi business outcome, kiểm tra quyền theo action, đo duration | Aspect nếu thỏa các điều kiện lựa chọn |

Ví dụ “ghi thời gian của mọi operation nghiệp vụ được đánh dấu rõ” có thể tách thành aspect vì **thuật toán quan sát** gần như giống nhau. Nhưng “đơn hàng của khách VIP giảm 7%” là quy tắc định giá; dù nhiều phương thức cần tính chiết khấu, không nên giấu nó trong advice bắt các phương thức có tên chứa “calculate”.

Một trường hợp nằm giữa là **kiểm soát truy cập**: mechanism kiểm tra và deny có thể làm aspect, còn **quyết định Alice được sửa tài liệu X không** phải dựa trên policy và resource thực, thường cần một thành phần phân quyền có hợp đồng rõ. Aspect điều phối tại boundary chứ không tự thay thế logic miền.

## 4. Tính ổn định ở đây nghĩa là gì?

Một concern đủ ổn định không có nghĩa **không bao giờ thay đổi**. Nó có nghĩa có thể dự đoán thay đổi và quản lý trong một điểm chung mà ít gây tác động ngoài ý muốn.

Có ít nhất bốn chiều ổn định:

1. **Ổn định ngữ nghĩa:** ý nghĩa của hành vi không đổi khi các use case được refactor. Ví dụ “một completion event trên mỗi operation” có ý nghĩa ổn định hơn “in tên mọi method private”.
2. **Ổn định chính sách:** cách áp dụng phần chung gần như thống nhất; khác biệt được biểu diễn qua metadata hoặc tham số policy rõ ràng, không phải vô số nhánh if theo tên class.
3. **Ổn định điểm cắt:** các join point được chọn biểu diễn contract có ý nghĩa, không phụ thuộc đường dẫn package, tên helper hoặc chữ ký nội bộ dễ thay đổi.
4. **Ổn định vòng đời:** advice hiểu chính xác mốc bắt đầu, mốc kết thúc, lỗi và cancellation của công việc mà nó đo hoặc kiểm soát.

Một concern có thể ổn định về chính sách nhưng không ổn định về điểm cắt. Chẳng hạn đo kết quả của một workflow kéo dài là yêu cầu bền vững, song không thể chỉ chặn một phương thức trả về Future rồi coi đó là kết thúc workflow. Khi ấy phải thiết kế lại điểm quan sát hoặc observer theo kết quả bất đồng bộ; không ép vào một around advice đồng bộ.

## 5. Các câu hỏi sàng lọc trước khi tạo Aspect

### 5.1. Concern có thật sự cắt ngang nhiều vùng độc lập không?

Nếu chỉ một use case áp dụng, mã tường minh tại use case thường dễ đọc hơn. Nếu nhiều chức năng độc lập cùng cần chính sách tương đương, AOP có thể giảm phân tán. Nhưng đừng lấy **số dòng trùng** làm chỉ số duy nhất: đôi khi vài dòng ghi log lặp lại là hợp lý, trong khi một aspect có pointcut khó hiểu gây rủi ro lớn.

### 5.2. Có thể mô tả chính sách bằng một câu ngắn, không kể tên từng use case?

Một chính sách phù hợp: “Ghi đúng một bản ghi outcome với duration cho mỗi operation được đánh dấu”. Một “chính sách” đáng nghi: “Khi loại invoice X thì kiểm tra A, loại order Y thì sửa dữ liệu B, trừ khi class nằm ở package Z”. Trường hợp sau chứa nhiều nhánh nghiệp vụ, khó giữ ổn định trong aspect.

### 5.3. Có điểm cắt tường minh, đủ tin cậy không?

Tốt: operation được đánh dấu bằng một metadata rõ hoặc contract interface được review. Dễ vỡ: mọi phương thức có tên bắt đầu bằng process, mọi public method, hoặc mọi method trong package dễ bị di chuyển. Một điểm cắt tốt còn phải bao phủ **các đường gọi thực tế**; nếu một phần nghiệp vụ bypass proxy, mục tiêu bảo vệ/quan sát không đạt.

### 5.4. Advice có thể bảo toàn hành vi của join point không?

Đối với logging hoặc metric, việc thêm advice thường không được đổi kết quả, exception hay số lần thực hiện nghiệp vụ. Với authorization, chủ ý duy nhất là từ chối những lời gọi không được phép trước side effect. Với transaction hoặc retry, hành vi là một phần của hợp đồng và phải được công bố rõ; không tự biến read operation thành retry có side effect lặp.

### 5.5. Ai sở hữu vòng đời và kết quả?

Nếu một method trả CompletionStage, advice sau method return có thể đo duration của lời gọi ngắn, chưa đo tác vụ. Nếu concern cần toàn bộ duration thì cần completion observer hoặc điểm khác. Với stream lười, publisher creation và subscription là hai thời điểm khác nhau. Nếu vòng đời không phù hợp với join point sẵn có, AOP không nên che giấu vấn đề.

### 5.6. Có kiểm chứng được phạm vi và outcome không?

Có thể kiểm thử rằng mọi protected operation thật sự bị chặn, mỗi operation được đo một lần, lỗi gốc không bị nuốt và helper không bị instrument ngoài ý muốn không? Nếu không, complexity của aspect có thể lớn hơn lợi ích.

## 6. Ma trận đánh giá trước khi quyết định

Dùng bảng dưới như công cụ trao đổi, không phải thuật toán cộng điểm cứng.

| Tiêu chí | Tín hiệu thuận lợi | Tín hiệu rủi ro |
| --- | --- | --- |
| Nhiều nơi cùng cần | Nhiều use case có nhu cầu giống nhau | Chỉ một caller đặc thù |
| Chính sách đồng nhất | Một contract và một cách xử lý rõ | Nhiều ngoại lệ dựa trên loại nghiệp vụ |
| Điểm cắt ổn định | Boundary/annotation/contract rõ | Glob package hoặc tên helper dễ đổi |
| Coupling với miền | Chỉ cần metadata tối thiểu | Cần đọc và sửa nhiều đối tượng nghiệp vụ |
| Bảo toàn hành vi | Advice không đổi result/exception ngoài chủ đích | Retry/sửa kết quả ngầm |
| Vòng đời | Khớp invocation hoặc có lifecycle observer đúng | Async completion bị coi như method return |
| Kiểm thử | Có thể xác minh số lượt, lỗi và exclusion | Hành vi ẩn, coverage không biết |
| Thứ tự composition | Quan hệ với advice khác rõ | Kết quả phụ thuộc thứ tự khó kiểm soát |
| Khả năng vận hành | Có owner, metric/log ổn định | Log trùng, counter tăng đôi, overhead lớn |
| Khả năng thay đổi | Thêm use case mới qua metadata rõ | Mỗi tính năng phải sửa nhiều if trong aspect |

Nếu nhiều ô ở cột rủi ro cùng xuất hiện, ưu tiên component hoặc API tường minh, hoặc tách concern thành **mechanism chung + policy nghiệp vụ riêng**. Không cần “cố đạt đủ điểm” để dùng AOP.

## 7. Những concern thường có tiềm năng tách thành Aspect

### 7.1. Logging tại ranh giới nghiệp vụ

Aspect có thể nhận operation name ổn định, timestamp, duration, outcome và correlation ID, rồi ghi event theo schema chung. Điểm cắt nên là boundary có ý nghĩa, không phải mọi method helper.

Điều ổn định: **hợp đồng log và nơi đặt logging**. Điều biến thiên: tên operation và một số metadata cho phép.

Rủi ro: log tất cả arguments làm lộ dữ liệu, log success khi method trả về stage chưa xong, nhiều aspect cùng phát event cuối khiến đếm trùng.

### 7.2. Metrics và tracing

Đếm mỗi business operation một lần hoặc tạo trace span ở boundary rõ ràng là ví dụ điển hình của cross-cutting concern. Phải xác định đơn vị: request, operation, attempt hay dependency call.

Rủi ro: hai instrumenter cùng tăng counter, tạo hai semantic duplicate spans hoặc trộn thời gian invocation đồng bộ với thời gian completion bất đồng bộ trong một histogram. Có thể có nhiều span hợp lệ; chúng phải mô tả **phạm vi khác nhau**.

### 7.3. Phân quyền tại operation boundary

Một authorization advice có thể nhận context đã xác thực, resolve action và resource, hỏi policy evaluator và từ chối trước khi proceed. Cơ chế chung là **đọc context và enforce decision**; logic đánh giá quyền theo tenant/resource có thể ở policy engine hoặc domain boundary.

Rủi ro: bypass pointcut, tin context caller tự tạo, nhầm authenticated với authorized, bỏ qua TOCTOU và quyền bị thu hồi.

### 7.4. Transaction boundary

Một aspect có thể bắt đầu/kết thúc transaction theo contract use case. Nhưng transaction không chỉ là một before/after đơn giản: commit, rollback, exception semantics, nested invocation, transaction propagation và thread affinity có quy tắc riêng. Không gắn transaction vòng quanh mọi phương thức chỉ vì chúng gọi repository.

Rủi ro: transaction được giữ qua tác vụ async, commit sớm hơn nghiệp vụ cần thiết hoặc rollback theo lỗi không đúng policy.

### 7.5. Audit quyết định hoặc sự kiện đã xác nhận

Nếu nhiều operation cần chuẩn audit và có điểm commit/decision đáng tin, một aspect có thể hỗ trợ thêm metadata và ghi nhận đúng mốc. Nhưng **audit có tính bền vững** không được bảo đảm chỉ bằng một lệnh logger chạy trong advice; phải thiết kế trách nhiệm lưu trữ, tính nhất quán và failure semantics riêng.

### 7.6. Giới hạn tài nguyên hoặc rate limiting

Aspect có thể bảo vệ operation boundary bằng permit/budget theo policy, nhưng chỉ khi khóa giới hạn, vòng đời permit và cách giải phóng được xác định. Không giữ permit của lời gọi ngắn cho công việc kéo dài nếu chúng thuộc hai vòng đời khác nhau; một task dài cần cơ chế sở hữu permit theo task.

## 8. Những concern thường không nên giấu trong Aspect

**Định giá, tính thuế, chiết khấu:** đây là quyết định miền; thay đổi thường theo loại đơn hàng và luật nghiệp vụ, cần được biểu diễn tường minh trong domain service hoặc policy object.

**Tạo/chỉnh sửa trạng thái miền:** một advice tự thay đổi order status sau bất kỳ method tên save nào làm hành vi khó kiểm chứng và khó giữ invariant giao dịch.

**Validation nghiệp vụ đặc thù:** một số validation cấu trúc có thể là cơ chế chung, nhưng quy tắc “chỉ duyệt đơn khi tồn kho và hạn mức thỏa” thường phải gắn với use case/domain. Không đồng nhất validation mọi DTO với authorization mọi operation.

**Chọn luồng xử lý:** nếu aspect quyết định gọi nhà cung cấp A hay B, rẽ nhánh sản phẩm theo loại khách hoặc tính toán cách hoàn tiền, luồng nghiệp vụ bị giấu; strategy/policy object dễ review hơn.

**Mặc định retry mọi thứ:** retry có thể lặp side effect, gây double charge hoặc gửi notification nhiều lần. Chỉ khi policy có hợp đồng idempotency, loại lỗi retry được và giới hạn attempts rõ mới xem xét đưa mechanism retry vào một aspect.

**Caching mọi getter:** cache key, TTL, invalidation, tenant isolation, tính nhất quán và dữ liệu nhạy cảm khác nhau giữa operations. Một điểm chung về mechanism chưa đủ chứng minh chính sách cache đồng nhất.

Một phép thử đơn giản: **nếu bỏ aspect đi, business rule có bị mất nghĩa hay chỉ mất một cơ chế hạ tầng?** Nếu mất logic quyết định kết quả nghiệp vụ, concern có thể nằm sai nơi. Tuy nhiên security enforcement là trường hợp đặc biệt: được phép thay đổi quyền thực thi theo chính sách, nên câu hỏi đúng hơn là “policy bảo mật có được mô tả tường minh và bao phủ đầy đủ không?”

## 9. Thiết kế pointcut như một hợp đồng kiến trúc

Pointcut bền vững phải gắn với **ý nghĩa của boundary**. Những lựa chọn có thể dùng:

1. **Annotation tường minh:** một method hoặc contract được đánh dấu là operation cần quan sát. Người review nhìn thấy ý định.
2. **Interface nghiệp vụ có phạm vi rõ:** một tập operation public được chỉ định thuộc nhóm được bảo vệ.
3. **Contract metadata ngoài mã:** dùng registry/config được kiểm soát, có kiểm thử tương ứng.
4. **Cấu trúc module ổn định:** package/class pointcut chỉ nên dùng khi kiến trúc thực sự bảo đảm tên/phạm vi bền.

Ví dụ hai pointcut giả định:

~~~text
Dễ vỡ: mọi method public trong package *service*
Ổn định hơn: các method được chỉ định là BusinessOperation
~~~

Trong thực tế, annotation đặt trên interface có thể không được một công cụ nhìn thấy trên implementation nếu nó không tìm metadata phù hợp. Proxy có thể không chặn self-invocation; weaving theo execution join point có cách bao phủ khác. Cần kiểm chứng **đường gọi runtime**, không chỉ điểm cắt trên giấy.

Không nên yêu cầu mọi team nhớ thêm annotation bằng thói quen. Hãy có coverage test hoặc checklist review đối chiếu tập protected operations với tập được instrument. Một protected method mới bị bỏ sót có thể nguy hiểm hơn việc giữ một ít code tường minh.

## 10. Advice phải có contract rất rõ

### Before

Phù hợp kiểm tra precondition, authorization trước side effect hoặc thiết lập một scope đã định nghĩa. Nhưng advice phải tránh tác dụng phụ không dự kiến; nếu nó từ chối, cần exception/kết quả theo hợp đồng.

### After returning

Quan sát method đã trả về bình thường; **không đồng nghĩa operation bất đồng bộ đã thành công**. Một method trả Result.Failure vẫn là return bình thường.

### After throwing

Quan sát exception xảy ra ở invocation được chặn; có thể không nhìn thấy lỗi task nền nếu lỗi xảy ra sau khi method return.

### Around

Cho phép đo thời gian, quản lý scope hoặc điều phối proceed. Đây là điểm mạnh nhưng cũng rủi ro: advice có thể vô tình gọi proceed hai lần, thay đổi exception, giữ lock quá lâu, làm nghẽn lời gọi hoặc tác động đến return type.

Một contract nên viết rõ:

~~~text
Một lời gọi được áp dụng advice:
  - cách chọn join point và loại trừ
  - metadata bắt buộc
  - số lần proceed được phép (thường đúng một)
  - mốc bắt đầu/kết thúc được đo
  - hành vi với return bình thường, lỗi đồng bộ, async failure
  - cách bảo toàn result/exception
  - thời điểm tạo và đóng scope
  - overhead và failure policy của observer
~~~

Nếu không thể viết contract ngắn gọn mà phải dựa vào điều kiện của từng tính năng mới, hãy xem lại mức độ ổn định của concern.

## 11. Java 17: minh họa tách một concern có hợp đồng ổn định

Ví dụ dùng JDK dynamic proxy để minh họa AOP độc lập với thư viện cụ thể. Chúng ta muốn ghi **bắt đầu và kết quả cho mỗi operation được đánh dấu**, không log các helper hoặc mọi method. Chính sách logging ổn định và có thể dùng cho nhiều operation. Trong khi đó, quyết định chuẩn hóa mã đơn hàng vẫn nằm trong implementation nghiệp vụ.

Tạo tệp **StableAspectDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class StableAspectDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface BusinessOperation {
        String value();
    }

    interface OrderService {
        @BusinessOperation("order.submit")
        String submit(String orderId);

        String status(String orderId);
    }

    static final class RealOrderService implements OrderService {
        @Override
        public String submit(String orderId) {
            return "SUBMITTED:" + normalize(orderId);
        }

        @Override
        public String status(String orderId) {
            return "PENDING";
        }

        private String normalize(String orderId) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("missing order id");
            }
            return orderId.trim();
        }
    }

    static final class OperationLogAdvice implements InvocationHandler {
        private final OrderService target;

        OperationLogAdvice(OrderService target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            BusinessOperation mark =
                    method.getAnnotation(BusinessOperation.class);

            if (mark == null) {
                return invokeTarget(method, args);
            }

            String name = mark.value();
            System.out.println("BEGIN " + name);
            try {
                Object result = invokeTarget(method, args);
                System.out.println("END " + name + " outcome=success");
                return result;
            } catch (Throwable failure) {
                System.out.println("END " + name
                        + " outcome=failure type="
                        + failure.getClass().getSimpleName());
                throw failure;
            }
        }

        private Object invokeTarget(Method method, Object[] args)
                throws Throwable {
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException wrapper) {
                throw wrapper.getCause();
            }
        }
    }

    public static void main(String[] args) {
        OrderService service = (OrderService) Proxy.newProxyInstance(
                OrderService.class.getClassLoader(),
                new Class<?>[] { OrderService.class },
                new OperationLogAdvice(new RealOrderService()));

        System.out.println("status=" + service.status("O-9"));
        System.out.println("result=" + service.submit(" O-9 "));

        try {
            service.submit(" ");
        } catch (IllegalArgumentException error) {
            System.out.println("caller_error="
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy với Java 17 trở lên:

~~~bash
javac StableAspectDemo.java
java StableAspectDemo
~~~

Stdout xác định:

~~~text
status=PENDING
BEGIN order.submit
END order.submit outcome=success
result=SUBMITTED:O-9
BEGIN order.submit
END order.submit outcome=failure type=IllegalArgumentException
caller_error=IllegalArgumentException
~~~

**Giải thích:**

- Metadata BusinessOperation là **dấu hiệu lựa chọn join point**; chỉ method submit được instrument theo chính sách log. Method status không phát log, và normalize chỉ làm nhiệm vụ miền.
- Advice gọi target **một lần** rồi trả lại kết quả nguyên vẹn; trường hợp lỗi thì ném lại nguyên nhân gốc qua InvocationTargetException để không đổi contract ngoại lệ.
- Hành vi logging không cần biết cách normalize order ID. Nếu thay thuật toán normalize hoặc tách thành nhiều helper, điểm phát log tại operation boundary vẫn đúng.
- Chính sách ở ví dụ chỉ cho rằng “method trả bình thường” là outcome success của invocation đồng bộ. Nếu trả Result chứa failure hoặc CompletionStage chưa hoàn tất, cần thiết kế outcome observer phù hợp; không dùng nguyên xi advice này để báo hoàn thành nghiệp vụ bất đồng bộ.
- System.out được dùng để có stdout kiểm chứng. Trong sản phẩm thật nên dùng structured logger có schema ổn định, redaction, level, ngân sách log và xử lý lỗi observer.
- Proxy chỉ chặn lời gọi qua interface proxy. Gọi trực tiếp RealOrderService không qua advice; các cơ chế weaving khác có tập join point khác. Đây là mô hình giảng dạy, không phải bảo đảm interception toàn cục.

Điều làm concern logging này đủ thích hợp cho aspect không phải vì nó chỉ chiếm vài dòng, mà vì **ý nghĩa, đầu vào cần thiết, điểm cắt và kết quả quan sát đều ổn định khi miền thay đổi**.

## 12. So sánh phương án trước và sau

**Trước khi tách**: mỗi use case tự viết các dòng bắt đầu, kết thúc, duration và phân loại lỗi. Nếu một nhóm quên finally, log có thể thiếu outcome; nếu thêm một trường correlation, phải chỉnh ở nhiều nơi.

**Sau khi tách một concern ổn định**: phương thức nghiệp vụ khai báo rõ boundary, một advice chung phát event theo schema. Thêm operation có thể chỉ cần khai báo metadata và test coverage. Ngược lại, caller phải hiểu rằng advice sẽ chạy; cần tài liệu thiết kế và quan sát được runtime weaving/proxy.

| Thuộc tính | Viết ở từng use case | Aspect ở boundary rõ |
| --- | --- | --- |
| Vị trí chính sách logging | Phân tán | Tập trung |
| Thêm metadata thống nhất | Sửa nhiều chỗ | Sửa một advice/schema |
| Hiện rõ hành vi ngay trong method | Rõ | Cần biết pointcut |
| Nguy cơ thiếu logging | Từng method có thể quên | Có thể bỏ sót join point |
| Bảo toàn kết quả nghiệp vụ | Dễ nhìn trực tiếp | Cần kiểm thử advice |
| Thay đổi thuật toán miền | Ít ảnh hưởng cơ chế | Không cần đổi pointcut nếu boundary ổn định |
| Khả năng chẩn đoán | Phụ thuộc từng tác giả | Có schema đồng nhất |
| Chi phí abstraction | Thấp khi ít điểm | Đáng giá khi nhiều điểm phù hợp |

AOP không loại mọi sự phân tán. Một số thông tin chuyên biệt như lỗi nghiệp vụ có mã riêng vẫn cần được nghiệp vụ/policy cung cấp. Đừng biến một aspect chung thành nơi chứa điều kiện của từng use case chỉ để giữ tất cả logic trong một lớp.

## 13. Khi cơ chế và chính sách cần tách đôi

Một mô hình bền vững cho concern có nhiều biến thể là:

~~~text
Business operation
   -> AOP advice tại boundary
      -> cung cấp trusted context, action, resource
      -> gọi Policy / Strategy được chỉ định
      -> áp dụng quyết định chung
   -> proceed hoặc từ chối
~~~

Ví dụ:

- Aspect biết **khi nào** kiểm tra authorization; policy engine biết **ai được làm gì trên tài nguyên nào**.
- Aspect biết **khi nào** bắt đầu/đóng metric; metadata nghiệp vụ biết tên operation/outcome code.
- Aspect biết **khi nào** bắt đầu transaction; transaction policy chỉ ra read-only, propagation hoặc rollback conditions.
- Aspect biết **khi nào** xin rate-limit permit; rate-limit policy biết key/quota/time window và vòng đời permit.

Tách như vậy giúp chính sách có thể thay đổi mà không ép pointcut thành một ma trận if/else theo tên class. Tuy nhiên, không tách bằng mọi giá: khi chỉ một operation có nhu cầu rất riêng, một API tường minh dễ hiểu và ít rủi ro hơn.

## 14. Thứ tự nhiều Aspect và tác động đến quyết định

Một operation có thể đồng thời chịu nhiều concern:

~~~text
TracingAdvice
  -> AuthorizationAdvice
     -> RetryAdvice
        -> TransactionAdvice
           -> businessOperation
~~~

Chỉ cần đổi thứ tự, hành vi quan sát đã có thể khác:

- **Authorization ngoài retry:** kiểm tra quyền một lần trước mọi attempt; cần xem quyền có thể hết hạn giữa các lần thử không.
- **Authorization trong retry:** kiểm tra lại mỗi attempt; hữu ích trong một số hoàn cảnh nhưng có chi phí và failure semantics khác.
- **Timer ngoài retry:** duration bao gồm các attempt và thời gian chờ giữa chúng.
- **Timer trong retry:** tạo một mẫu mỗi attempt, phải đặt tên attempt duration.
- **Transaction ngoài retry:** có thể giữ cùng transaction trong nhiều attempts và khó rollback đúng, trong khi transaction bên trong có scope khác.
- **Tracing ngoài/in giữa:** span cha và child spans có thể mang phạm vi khác nhau; đừng phát semantic duplicate spans do instrument hai tầng cùng một công việc.

**Một concern dù ổn định một mình cũng có thể không còn ổn định khi kết hợp với concern khác.** Vì thế quyết định tách thành aspect phải xét luật composition: thứ tự, nesting, exception propagation, context propagation và idempotency.

Với retry, phải xác minh nghiệp vụ có chịu lặp hay không. Không chọn retry aspect rộng chỉ vì “xử lý lỗi mạng” xuất hiện ở nhiều method; một operation chuyển tiền không thể bị gọi lại tùy tiện chỉ dựa trên exception type.

## 15. Vòng đời đồng bộ và bất đồng bộ

Một around advice chạy quanh phương thức đồng bộ thường có thể xác định thời điểm vào, return, throw. Nhưng khi một phương thức chỉ gửi công việc đi và trả handle, **invocation** kết thúc trước **task**.

~~~text
Caller / Aspect                  Worker
--------------                   ---------------------
before proceed()
proceed() -> trả CompletionStage
after returning
caller tiếp tục                 task chạy
                                task thất bại/thành công
                                completion callback
~~~

Đối với concern logging/metric “thời gian hoàn tất operation”, cơ chế chung cần hiểu loại async API. Một advice sau proceed không thể tự khẳng định task đã thành công. Có thể cần quan sát CompletionStage, Future theo hợp đồng, callback lifecycle, job completion hoặc subscription. Với Publisher lười, việc tạo publisher không đồng nghĩa có subscription; không tự subscribe để ép đo.

Khi gắn callback, giữ những quy tắc:

- Callback có thể chạy ở thread khác hoặc chạy ngay lúc đăng ký nếu stage đã xong.
- Không giữ lock, transaction hay scope ngắn của invocation tới lúc công việc dài hoàn tất nếu resource không có hợp đồng như vậy.
- Không cho observer tự ném exception làm thay đổi kết quả của dependent stage ngoài chủ đích.
- Không tăng business outcome ở cả method return và completion.
- Timeout hoặc cancel của handle chưa bảo đảm task đã dừng và tài nguyên nền đã cleanup.

**Nếu concern không có cùng vòng đời giữa các điểm áp dụng, nó có thể cần nhiều adapter rõ ràng hơn là một aspect “tổng quát cho mọi method”.**

## 16. Scope, thread và các rủi ro ẩn

Một số aspect tạo scope theo thread để gắn tracing context, security context hoặc transaction. Với tác vụ đồng bộ, try/finally có thể bảo đảm cleanup; nhưng thread pool và callbacks làm scope phức tạp hơn.

Các rủi ro:

- ThreadLocal còn dữ liệu sau lời gọi, khiến request sau trên cùng thread dùng nhầm context.
- Lời gọi lồng nhau remove context nhưng không restore parent.
- Callback ở thread khác cố đóng scope có thread affinity của caller.
- Advice giữ connection hoặc permit đến lúc async completion dù task không cần giữ nó.
- Context của caller được truyền sang task dài hơn hiệu lực của token/ủy quyền.

Giải pháp thường là gắn scope với đúng logical operation, truyền snapshot tối thiểu và bất biến tới worker, tạo worker scope riêng và cleanup ở chính worker. Với security, context propagation không tự xác minh quyền; cần nguồn context tin cậy và quy tắc reauthorization/expiry phù hợp.

Một concern cần phức tạp hóa lifecycle như vậy mới vận hành đúng có thể vẫn đáng tách, nhưng chi phí kiến trúc phải được nhận diện trước.

## 17. Tính dễ kiểm thử là tiêu chí lựa chọn

Một aspect phù hợp nên có bộ kiểm thử tập trung để giữ contract chung:

| Tình huống | Kỳ vọng |
| --- | --- |
| Method thuộc boundary hợp lệ | Advice chạy đúng số lần đã quy định |
| Method helper ngoài pointcut | Không bị áp dụng ngoài chủ đích |
| Method return bình thường | Kết quả nguyên vẹn, event theo contract |
| Method ném lỗi | Lỗi gốc được lan truyền, cleanup đúng |
| Nested aspect | Không đo trùng, thứ tự có thể giải thích |
| Retry | Operation và attempt được phân biệt |
| Direct target/self-invocation | Không có bypass ngoài ý muốn |
| Method mới/overload mới | Coverage được review và kiểm thử |
| Async completion | Mốc return khác mốc hoàn tất được giữ đúng |
| Scope nested / thread reuse | Context được restore và remove |
| Observer/logger gặp lỗi | Chính sách failure rõ, không che lỗi nghiệp vụ |
| Nhiều requests đồng thời | Không chia sẻ mutable state làm lẫn outcome |
| Đầu vào nhạy cảm | Không log token, credential hoặc payload nguyên bản |

Nên kiểm thử **pointcut mapping ở runtime** và một vài đường gọi tích hợp, không chỉ unit test trực tiếp advice. Một advice unit test có thể pass dù proxy không được lắp vào hệ thống hoặc một protected method bị gọi trực tiếp.

Kiểm thử số lần **proceed** đặc biệt quan trọng với around advice. Khi một lời gọi đủ điều kiện, target thường chạy đúng một lần; khi bị từ chối truy cập trước side effect, target phải chạy 0 lần. Với policy retry chủ ý, nhiều lần chạy phải được ghi nhận theo attempt và có bảo đảm idempotency.

## 18. Khả năng quan sát chính cơ chế AOP

Aspect che bớt mã lặp nhưng cũng tạo **hành vi không hiện trên thân method**. Do đó cần cơ chế giúp người đọc biết:

- Một operation đang chịu những aspect nào?
- Pointcut có chọn đúng những join point dự kiến không?
- Advice chạy theo thứ tự nào?
- Vì sao một lời gọi bị DENY, RETRY, ROLLBACK hoặc bị ghi metric?
- Có bao nhiêu nguồn phát cùng signal?
- Khi một aspect bị lỗi, result/exception nghiệp vụ thay đổi ra sao?

Nên có tài liệu ngắn về metadata, ownership của event/metric, biểu đồ invocation chain và kết quả kiểm thử hiệu lực. Tránh log mọi lần chặn để “debug aspect” trong môi trường production: dễ tạo vòng lặp logging, lộ dữ liệu và thêm overhead. Dùng diagnostic logging có kiểm soát, giới hạn phạm vi và không chứa bí mật.

## 19. Chi phí hiệu năng, coupling và tiến hóa

AOP có thể giảm số dòng lặp nhưng không xóa chi phí:

1. Proxy/interceptor/weaving có overhead gọi method; có thể tạo allocation cho metadata, timer, closure.
2. Mỗi advice có thể ghi log, metric, trace và gửi exporter, làm tăng I/O và áp lực GC.
3. Pointcut rộng làm instrument nhiều helper không cần thiết.
4. Cơ chế lấy tham số bằng reflection hoặc resolve resource có thể đắt hơn bản thân nghiệp vụ ngắn.
5. Multiple aspect layers làm stack trace và exception flow khó theo dõi.
6. Một aspect chứa danh sách special-case của nhiều domain trở thành điểm coupling cao: team A sửa chính sách làm team B đổi hành vi.

Khi đánh giá lợi ích, so sánh tổng chi phí sửa đổi, test coverage, readability, runtime overhead và xác suất bỏ sót policy. Với codebase nhỏ, một interceptor tường minh hoặc hàm wrapper đơn giản có thể rõ ràng hơn. Với nhiều module có boundary chung, aspect được kiểm soát tốt có thể giảm lỗi phân tán đáng kể.

Không nên dựa vào số dòng code giảm để xác định hiệu quả kiến trúc. Một aspect duy nhất nhưng thay đổi hành vi của 500 phương thức có thể có tác động lớn hơn 500 lời gọi API tường minh.

## 20. Các dấu hiệu một Aspect đang phình thành “God Aspect”

Cảnh báo khi:

- Pointcut khớp gần như mọi method trong hệ thống nhưng loại trừ bằng danh sách dài.
- Advice chứa nhiều switch/if dựa trên tên class, tên method, loại khách hàng hoặc trạng thái nghiệp vụ.
- Muốn thêm một use case mới phải sửa logic aspect thay vì chỉ khai báo contract/metadata.
- Aspect tự đọc và ghi nhiều aggregate/domain object.
- Một advice vừa retry, cache, authorize, log, transform result và cập nhật database.
- Thứ tự chạy giữa các aspect không còn ai giải thích được.
- Nhiều team cùng sửa một aspect khi policy nghiệp vụ từng team thay đổi.
- Thay tên helper gây lỗi không mong đợi ở metric, transaction hoặc authorization.
- Kiểm thử phải bật hàng loạt infrastructure mới xác minh một quy tắc nhỏ.

Cách cải thiện: thu hẹp pointcut, chia theo trách nhiệm thật, đưa policy đặc thù về domain service/strategy và giữ advice làm bộ điều phối cơ chế chung. Nếu chỉ một số nhỏ join point cần policy, có thể thay bằng API tường minh cho dễ đánh giá.

## 21. Quy trình quyết định và triển khai

**Bước 1 — Nêu vấn đề bằng kết quả mong muốn.** Ví dụ: “Mọi operation được bảo vệ phải kiểm tra quyền trước side effect và ghi một audit decision”, thay vì “muốn thêm aspect cho module”.

**Bước 2 — Kiểm kê các điểm áp dụng.** Có bao nhiêu use case thực sự cần concern? Chúng chia sẻ cùng contract? Có ngoại lệ mang tính nghiệp vụ không?

**Bước 3 — Viết hợp đồng chính sách.** Ghi rõ input, outcome, exception, lifecycle, giới hạn dữ liệu, tính bất biến và các điều kiện loại trừ.

**Bước 4 — Đánh giá bốn chiều ổn định.** Ngữ nghĩa, chính sách, pointcut và lifecycle có giữ nguyên qua một lần refactor hợp lý không?

**Bước 5 — Đối chiếu các phương án khác.** Service, policy object, decorator, explicit interceptor, wrapper function hoặc middleware có thể đáp ứng đơn giản hơn? Chọn phương án với coupling và nguy cơ ẩn ít nhất cho nhu cầu hiện tại.

**Bước 6 — Thiết kế pointcut tường minh.** Ưu tiên contract/annotation/registry có thể kiểm chứng, tránh quét toàn bộ helper.

**Bước 7 — Định nghĩa composition.** Khi có authorization, transaction, retry, cache, trace, xác định thứ tự và owner của kết quả/metric.

**Bước 8 — Kiểm thử và đo overhead.** Kịch bản thành công, lỗi, nested, async, concurrency, bypass, double counting và mã nghiệp vụ không bị thay đổi ngoài dự tính.

**Bước 9 — Triển khai theo phạm vi nhỏ trước.** Chọn vài operation đại diện, đo độ rõ và sự chính xác, rồi mở rộng nếu policy thật sự đủ chung.

**Bước 10 — Giữ governance.** Khi thêm operation, thay metadata hay sửa pointcut, yêu cầu review phạm vi ảnh hưởng và chạy lại kiểm thử coverage/behavior.

## 22. Câu hỏi tự đánh giá

1. Một concern áp dụng ở ba nơi khác nhau nhưng mỗi nơi có điều kiện nghiệp vụ riêng. Nên đưa tất cả vào một aspect không? **Thông thường không**: trước hết tách mechanism chung khỏi policy miền, sau đó đánh giá liệu còn có boundary policy ổn định để instrument không.
2. Thêm một method helper làm số log tăng gấp ba. Dấu hiệu gì? **Pointcut có thể quá rộng hoặc phụ thuộc cấu trúc mã thay vì operation contract**.
3. Hai timers đo cùng method, một timer ngoài retry và một timer trong retry. Có chắc đo trùng không? **Không** nếu chúng lần lượt đo operation và attempts, có tên/scope rõ. Nếu cùng phát một loại business-operation sample thì có nguy cơ trùng ngữ nghĩa.
4. Aspect đo duration của method trả CompletionStage. Đó có phải end-to-end duration không? **Không nhất thiết**: method có thể chỉ trả handle. Cần observer theo completion contract.
5. Một aspect kiểm tra role trước phương thức chuyển tiền, nhưng method được gọi trực tiếp không qua proxy. Có an toàn không? **Không**: enforcement có thể bị bypass; cần quản lý các đường gọi và bảo vệ invariant ở vị trí thích hợp.
6. Một chính sách logging ổn định nhưng nhiều use case cần ẩn dữ liệu khác nhau. Có nên bỏ AOP không? **Chưa chắc**: schema chung và allowlist metadata có thể tách biệt; không để aspect tự serialize toàn bộ arguments.

## 23. Checklist review thiết kế

- [ ] Concern thực sự xuyên nhiều boundary độc lập.
- [ ] Có contract chung ổn định, không phải tập hợp quy tắc nghiệp vụ rời rạc.
- [ ] Pointcut dựa vào ngữ nghĩa operation, có coverage test và exclusion rõ.
- [ ] Advice biết chính xác mốc invocation, completion, failure và cancellation.
- [ ] Kết quả và exception nghiệp vụ được bảo toàn ngoài thay đổi có chủ đích.
- [ ] Ownership metric/log/trace được phân định, không double count.
- [ ] Thứ tự aspect với transaction, retry, authorization, cache đã được kiểm tra.
- [ ] Cơ chế không cho phép bypass quyền hoặc transaction invariant quan trọng.
- [ ] Context/thread scope được cleanup đúng; async có propagation phù hợp.
- [ ] Concern không biến thành kho chứa if/else theo từng use case.
- [ ] Logging không lộ dữ liệu; cardinality metric được kiểm soát.
- [ ] Có thử nghiệm performance và behavior khi nhiều aspect cùng hoạt động.
- [ ] Có kế hoạch review pointcut và metadata khi chương trình tiến hóa.

**Kết luận:** một concern là ứng viên tốt cho aspect khi **quy tắc chung ổn định hơn những phương thức mà nó áp dụng**, điểm cắt diễn đạt được ý nghĩa nghiệp vụ hoặc hạ tầng, và advice có hợp đồng đủ rõ để giữ đúng hành vi. AOP hiệu quả nhất ở nơi nó **tập trung được chính sách chung** mà không che giấu các quyết định miền vốn cần xuất hiện công khai trong thiết kế.