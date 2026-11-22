# Giữ quy tắc nghiệp vụ cốt lõi tường minh khi cần trong AOP

## 1. Vấn đề thiết kế: AOP giúp tách mối quan tâm, nhưng không nên che giấu nghiệp vụ

Trong **Aspect-Oriented Programming (AOP)**, một aspect đóng gói hành vi có thể áp dụng tại nhiều **join point** thông qua **pointcut** và **advice**. Những cơ chế như đo thời gian, ghi log có cấu trúc, kiểm tra điều kiện truy cập tại một ranh giới hoặc tạo trace span có thể phù hợp với cách tổ chức này. Nhờ đó, phần thân của nhiều phương thức không phải lặp đi lặp lại cùng một đoạn hạ tầng.

Tuy nhiên, một quyết định như **giá đơn hàng được tính thế nào, khi nào cho phép chuyển trạng thái, điều kiện nào khiến giao dịch được chấp thuận hay từ chối, hoặc ai chịu trách nhiệm sửa dữ liệu** không nên biến mất khỏi mô hình nghiệp vụ chỉ vì có thể chèn logic bằng advice.

**Nguyên tắc trung tâm:** những quy tắc quyết định kết quả và trạng thái cốt lõi của hệ thống cần có **hợp đồng tường minh, tên gọi mang ý nghĩa nghiệp vụ, vị trí sở hữu rõ ràng và kiểm thử trực tiếp**. AOP nên hỗ trợ các mối quan tâm xuyên suốt ở ranh giới thích hợp; không làm quy tắc miền trở thành một tác dụng phụ vô hình của tên phương thức hay thứ tự aspect.

Trong thực tế, vẫn có các chính sách được áp dụng xuyên suốt và ảnh hưởng đến quyền thực thi, như authorization, transaction hoặc rate limiting. Vì vậy không thể nói mọi advice phải thuần túy quan sát. Tiêu chí đúng là **một thay đổi có ý nghĩa miền phải được thể hiện bằng chính sách hoặc hợp đồng được khai báo rõ**, có thể tìm thấy, đánh giá và xác minh, thay vì giấu một nhánh đặc thù trong advice quá rộng.

## 2. Phân biệt logic nghiệp vụ cốt lõi với cross-cutting concern

**Business rule (quy tắc nghiệp vụ):** điều kiện, phép tính hoặc chuyển trạng thái mà hệ thống phải tuân thủ để cho ra kết quả đúng. Ví dụ: đơn hàng chỉ được chốt nếu mặt hàng còn được bán; mức giảm giá phụ thuộc hạng khách và chương trình khuyến mại; thanh toán không thể vượt hạn mức đã được cấp.

**Business invariant (bất biến nghiệp vụ):** điều kiện phải tiếp tục đúng tại các mốc cam kết trạng thái, chẳng hạn tổng tiền không âm theo quy tắc miền, một mã hoàn tiền không được thực hiện hai lần, hoặc một tài nguyên không được chuyển chủ sở hữu trái phép.

**Cross-cutting concern:** một trách nhiệm lặp trên nhiều phần mà cơ chế áp dụng thường giống nhau, chẳng hạn ghi sự kiện hoàn tất thao tác, đo duration, correlation ID, telemetry hoặc kiểm tra một policy đã được mô tả.

**Application service / use case:** nơi điều phối lời gọi, chính sách và các thành phần miền để thực hiện một ý định nghiệp vụ cụ thể.

**Domain service / policy object:** nơi mô tả quy tắc không tự nhiên thuộc một entity hoặc cần dùng lại; hợp đồng đầu vào/đầu ra đủ rõ để kiểm thử.

**Aspect:** cơ chế can thiệp tại join point, có thể bao quanh một use case hoặc một boundary để áp dụng một chính sách chung. Aspect không tự phân biệt được phương thức là nghiệp vụ hay helper nếu không có pointcut/metadata được thiết kế đúng.

| Câu hỏi | Thường là logic miền | Thường là concern xuyên suốt |
| --- | --- | --- |
| Có quyết định giá, hạn mức, quyền sở hữu, chuyển trạng thái? | Có | Chỉ hỗ trợ bảo vệ/quan sát |
| Có cần chuyên gia nghiệp vụ phê duyệt quy tắc? | Thường có | Phụ thuộc chính sách chung |
| Kết quả có thay đổi giữa các loại sản phẩm/khách hàng? | Thường có | Cơ chế thường giống nhau |
| Có thể mô tả bằng operation name, outcome, duration chung? | Có thể cung cấp metadata | Thường là trọng tâm |
| Nếu bỏ hành vi này thì kết quả nghiệp vụ sai? | Dấu hiệu cần tường minh | Nếu là authorization, phải có enforcement được công bố rõ |
| Có thể kiểm thử bằng input và output nghiệp vụ trực tiếp? | Nên làm | Thường kiểm thử interception/metadata |

Bảng chỉ là công cụ phân tích. Không phải mọi trách nhiệm đều chỉ thuộc một bên. Một thiết kế tốt có thể dùng **aspect để kích hoạt kiểm tra**, còn **domain policy** định nghĩa nội dung điều kiện. Chẳng hạn advice biết khi nào phải hỏi quyền; policy biết một nhân viên có được phê duyệt hồ sơ nào hay không.

## 3. “Tường minh” nghĩa là gì?

Một quy tắc đủ tường minh khi người bảo trì có thể:

1. **Tìm được nó** theo tên use case, policy hoặc invariant.
2. **Biết ai sở hữu**: entity, domain service, application service, policy object hay một cấu hình nghiệp vụ chính thức.
3. **Biết khi nào nó chạy**, tại bước nào so với đọc dữ liệu, ghi dữ liệu và commit.
4. **Đọc hợp đồng**: đầu vào, kết quả, trạng thái thất bại, side effect và điều kiện áp dụng.
5. **Kiểm thử trực tiếp** quy tắc mà không cần dựng cả hệ thống weaving hoặc một chuỗi proxy khó quan sát.
6. **Đánh giá tác động** khi sửa luật: những use case nào bị ảnh hưởng, dữ liệu nào cần migration, các đường thực thi nào phải giữ invariant.
7. **Phân biệt** kết quả nghiệp vụ với hành vi đo lường/logging và xử lý lỗi hạ tầng.

Tường minh không bắt buộc viết một chuỗi câu lệnh if lớn trong từng method. Một đối tượng chính sách có tên rõ, một bảng quyết định được kiểm soát, một state machine hoặc một rule evaluator có version cũng có thể tường minh nếu điểm gọi, hợp đồng và owner được công bố.

Không nên áp đặt một phương pháp biểu diễn duy nhất. Mục đích là giúp quyết định nghiệp vụ **có địa chỉ kiến trúc và có bằng chứng kiểm chứng**, thay vì chỉ xảy ra vì một pointcut vô tình khớp.

## 4. Dấu hiệu đã đưa quá nhiều nghiệp vụ vào Aspect

### 4.1. Advice sửa kết quả trả về theo loại khách

Một around advice thấy phương thức tính giá, gọi proceed rồi bí mật giảm 10% nếu một ThreadLocal chứa nhãn VIP. Người đọc phương thức tính giá sẽ hiểu sai rằng nó trả giá cuối; quy tắc discount lại không nằm ở nơi định nghĩa giá và thứ tự áp dụng thuế/chiết khấu có thể thay đổi theo advice order.

### 4.2. Advice chuyển trạng thái nghiệp vụ

Một advice after-returning quanh mọi method tên save tự chuyển đơn hàng sang APPROVED. Việc lưu dữ liệu và quyết định phê duyệt là hai ý nghĩa khác nhau; tên method hoặc một lời gọi kỹ thuật không đủ xác định điều kiện phê duyệt.

### 4.3. Pointcut mã hóa tên class và tên method đặc thù

Ví dụ quy tắc “khi class tên PremiumOrder và method tên update thì áp dụng thuế vùng X” phụ thuộc cấu trúc mã. Refactor tên lớp khiến quy tắc biến mất, trong khi yêu cầu nghiệp vụ không hề thay đổi.

### 4.4. Thêm use case mới phải sửa nhiều nhánh if trong một Aspect

Một aspect chứa những điều kiện riêng cho Order, Invoice, Payment, Membership và Refund dần trở thành điểm hội tụ của những domain không liên quan. Các nhóm sở hữu domain khác nhau có thể gây thay đổi ngoài ý muốn cho nhau.

### 4.5. Lỗi hoặc retry của advice thay đổi trạng thái nghiệp vụ không được công bố

Một around advice chung tự retry mọi exception, bao gồm cả phương thức chuyển tiền không có idempotency. Một lần người dùng yêu cầu có thể tạo hai side effect. Nếu retry là một chính sách có chủ ý, nó phải có ràng buộc về idempotency, loại lỗi retry được, số lần thử và outcome, thay vì âm thầm hoạt động trên mọi method.

### 4.6. Tests chỉ kiểm tra proxy, bỏ qua hợp đồng miền

Nếu bài test về giảm giá phải dựng weaving và cấu hình pointcut để biết 10% được áp dụng thế nào, khả năng logic định giá đã nằm sai lớp. Kiểm thử giá nên gọi pricing policy hoặc use case có contract rõ; bài test aspect chỉ cần chứng minh phần concern xuyên suốt chạy đúng.

## 5. Khi nào quy tắc miền cần ở entity, service hay policy?

Không có đáp án cố định cho mọi mô hình, nhưng có những hướng dẫn hữu ích:

| Quy tắc | Vị trí ứng viên | Lý do |
| --- | --- | --- |
| Một trạng thái chỉ có thể chuyển từ DRAFT sang APPROVED khi đủ điều kiện | Entity/aggregate hoặc domain service | Bảo vệ invariant trạng thái |
| Giá cuối tính từ giá gốc, thuế và khuyến mại | Pricing policy/domain service | Có công thức nghiệp vụ rõ, thay đổi theo loại đơn |
| Một tác vụ phải gọi ba dịch vụ theo một quy trình | Application service/use case | Điều phối workflow và outcome |
| Một action cần quyền trên resource | Authorization policy + điểm enforcement | Quyết định theo subject/action/resource |
| Ghi operation outcome theo schema chung | Logging aspect ở business boundary | Cơ chế chung, ít phụ thuộc loại nghiệp vụ |
| Đo duration của mỗi operation | Metrics aspect hoặc instrumentation theo lifecycle | Quan sát chung và tách khỏi công thức nghiệp vụ |
| Áp dụng retry cho dependency có hợp đồng an toàn | Retry policy + interceptor riêng | Cần contract idempotency và loại lỗi |
| Kiểm tra giới hạn tồn kho trước cập nhật | Domain/storage boundary, giao dịch thích hợp | Cần ngăn race và bảo vệ dữ liệu thực |

Một **domain service** không bắt buộc phải có trạng thái. Điều quan trọng là input, output và điều kiện rõ ràng. Một **policy object** giúp thay đổi luật mà không đặt một danh sách switch/if theo tên method trong advice.

## 6. Đừng nhầm “cross-cutting” với “mọi nơi đều làm giống nhau”

Một yêu cầu có thể xuất hiện ở nhiều domain nhưng chỉ giống nhau ở tên.

Ví dụ “validate” xuất hiện ở tạo tài khoản, đặt hàng và thanh toán. Validation cấu trúc dữ liệu có thể dùng một abstraction chung, nhưng điều kiện thanh toán vượt hạn mức, tuổi người dùng hoặc tồn kho không giống nhau. Không thể chỉ tạo một ValidationAspect khớp mọi method có tên process rồi coi các luật là đồng nhất.

Tương tự:

- **Caching:** cùng cơ chế lưu cache nhưng key, TTL, tenant isolation và invalidation khác biệt theo nghiệp vụ.
- **Retry:** cùng vòng lặp retry nhưng mức độ idempotent, backoff và error classification khác nhau.
- **Transaction:** cùng cơ chế begin/commit nhưng phạm vi atomicity và rollback rule có thể khác.
- **Authorization:** cùng enforcement nhưng policy tài nguyên và delegation khác.
- **Logging:** có thể dùng schema chung nhưng không có quyền in toàn bộ argument chứa dữ liệu nhạy cảm.

Vì thế cần tách **mechanism ổn định** và **policy biến thiên**. Aspect chỉ điều phối mechanism tại boundary; từng domain cung cấp metadata/policy cần thiết.

## 7. Một ví dụ phản thiết kế và cách cải thiện

### Phản thiết kế: advice thay đổi giá

Giả mã không khuyến nghị:

~~~text
around *calculatePrice*(...):
    price = proceed()
    if currentUser.isPremium():
        return price * 0.9
    return price
~~~

Những lỗi kiến trúc có thể gặp:

1. Một method trả price đã tính thuế và một method khác trả base price; 10% bị áp dụng khác mốc.
2. Caller không thấy discount là một phần của hợp đồng.
3. Advice phụ thuộc context hiện hành có thể mất khi chuyển executor hoặc thread.
4. Khi một method gọi method khác cũng khớp pointcut, discount có thể bị áp dụng hai lần.
5. Refactor tên method có thể làm mất hoặc nhân đôi quy tắc.
6. Phép toán số thực có thể gây lỗi làm tròn tiền tệ nếu thiếu money type/chính sách rounding.
7. Luật khuyến mại có thể thay đổi theo thời gian nhưng không có version hoặc policy owner.
8. Kết quả trả về được đổi sau proceed mà không tương ứng với dữ liệu đã ghi hoặc audit.

### Thiết kế rõ trách nhiệm

~~~text
CheckoutUseCase
    -> kiểm tra input / lập kế hoạch
    -> PricingPolicy.calculate(request, customerContext)
    -> tạo PriceQuote theo công thức được kiểm thử
    -> xác nhận/ghi trạng thái khi phù hợp

ObservabilityAspect
    -> quan sát boundary use case
    -> ghi start/outcome/metric
    -> trả nguyên kết quả của use case
~~~

PricingPolicy có thể là một interface với nhiều cách tính cụ thể; một bộ quy tắc ngoài mã cũng có thể dùng nếu được quản lý/version hóa. Điều phải rõ là **một use case chủ động gọi policy chính thức**, và policy quyết định giá. Aspect không cần biết khách hàng thuộc hạng nào.

## 8. Java 17 chạy được: quy tắc giá tường minh, Aspect chỉ ghi sự kiện

Ví dụ minh họa hai trách nhiệm:

- **PricingService** chịu trách nhiệm tính giá theo quy tắc nghiệp vụ cụ thể: số lượng phải dương, đơn giá tính bằng cent không âm, khách premium giảm 10% của subtotal; phần cent lẻ trong discount được làm tròn xuống bằng chia số nguyên.
- **OperationLoggingAdvice** quan sát những method có metadata BusinessOperation, ghi bắt đầu/kết thúc hoặc lỗi, nhưng không tự sửa quote.

Ví dụ dùng JDK dynamic proxy để giải thích cơ chế can thiệp ở interface method; không phụ thuộc thư viện AOP riêng.

Tạo tệp **ExplicitBusinessRulesDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class ExplicitBusinessRulesDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface BusinessOperation {
        String value();
    }

    record QuoteRequest(int quantity, int unitPriceCents, boolean premium) { }

    record PriceQuote(int subtotalCents, int discountCents, int totalCents) { }

    interface PricingService {
        @BusinessOperation("price.quote")
        PriceQuote quote(QuoteRequest request);
    }

    static final class DefaultPricingService implements PricingService {
        @Override
        public PriceQuote quote(QuoteRequest request) {
            if (request == null || request.quantity() <= 0
                    || request.unitPriceCents() < 0) {
                throw new IllegalArgumentException("invalid quote request");
            }

            // Chính sách giá là mã miền tường minh.
            int subtotal = Math.multiplyExact(
                    request.quantity(), request.unitPriceCents());
            int discount = request.premium() ? subtotal / 10 : 0;
            int total = Math.subtractExact(subtotal, discount);
            return new PriceQuote(subtotal, discount, total);
        }
    }

    static final class OperationLoggingAdvice implements InvocationHandler {
        private final PricingService target;

        OperationLoggingAdvice(PricingService target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            BusinessOperation metadata =
                    method.getAnnotation(BusinessOperation.class);
            if (metadata == null) {
                return invokeTarget(method, args);
            }

            String operation = metadata.value();
            System.out.println("BEGIN " + operation);
            try {
                Object result = invokeTarget(method, args);
                System.out.println("END " + operation + " outcome=returned");
                return result;
            } catch (Throwable error) {
                System.out.println("END " + operation + " outcome=threw type="
                        + error.getClass().getSimpleName());
                throw error;
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
        PricingService service = (PricingService) Proxy.newProxyInstance(
                PricingService.class.getClassLoader(),
                new Class<?>[] { PricingService.class },
                new OperationLoggingAdvice(new DefaultPricingService())
        );

        PriceQuote premium = service.quote(new QuoteRequest(3, 1000, true));
        System.out.println("premium_total=" + premium.totalCents());

        PriceQuote regular = service.quote(new QuoteRequest(2, 500, false));
        System.out.println("regular_total=" + regular.totalCents());

        try {
            service.quote(new QuoteRequest(0, 1000, true));
        } catch (IllegalArgumentException error) {
            System.out.println("rejected="
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy trên Java 17 trở lên:

~~~bash
javac ExplicitBusinessRulesDemo.java
java ExplicitBusinessRulesDemo
~~~

Stdout dự kiến chính xác:

~~~text
BEGIN price.quote
END price.quote outcome=returned
premium_total=2700
BEGIN price.quote
END price.quote outcome=returned
regular_total=1000
BEGIN price.quote
END price.quote outcome=threw type=IllegalArgumentException
rejected=IllegalArgumentException
~~~

### Phân tích code

**Quy tắc miền được đọc ngay trong DefaultPricingService.** QuoteRequest kiểm soát quantity và unitPriceCents; khi hợp lệ, subtotal = quantity × unitPriceCents; discount premium = floor(subtotal / 10) vì phép chia số nguyên; tổng = subtotal − discount. Với 3 × 1000 cent, subtotal 3000, discount 300, total 2700. Với 2 × 500 cent và khách thường, discount 0, total 1000.

**Math.multiplyExact và Math.subtractExact** giúp phát hiện tràn số nguyên bằng ArithmeticException thay vì cho giá trị không đúng. Ứng dụng thực tế có thể dùng một kiểu Money và decimal arithmetic theo quy tắc làm tròn, currency và hạn mức riêng; ví dụ dùng int cent để stdout dễ xác minh.

**Aspect không hiểu công thức giá.** Nó chỉ xem một method có BusinessOperation và ghi outcome. Khi chính sách premium đổi từ 10% sang mức mới, ta sửa pricing policy và test giá mà không chỉnh pointcut hoặc logic logging.

**Advice bảo toàn kết quả và exception.** Proxy gọi target đúng một lần, trả nguyên PriceQuote hoặc ném lại nguyên nhân qua InvocationTargetException. Dòng "outcome=returned" chỉ mô tả method đồng bộ trả bình thường; nếu API trả một đối tượng chứa thất bại hoặc Future chưa hoàn tất, định nghĩa business success phải khác.

**Ví dụ chỉ instrument lời gọi qua proxy.** Gọi trực tiếp DefaultPricingService sẽ không kích hoạt advice, dù công thức miền vẫn chính xác. Đây là một lý do rất quan trọng để quy tắc cốt lõi không được đặt độc quyền trong cơ chế chặn có thể bị bypass.

**Dòng log không chứa request.** Một aspect production cần dùng structured logger, schema ổn định, correlation phù hợp và cơ chế redaction. Không log argument nguyên bản chỉ vì reflection có thể đọc được nó.

## 9. Vì sao không nên đặt quy tắc cốt lõi độc quyền trong proxy?

Cơ chế AOP có thể chặn các điểm khác nhau:

- **Proxy/interceptor:** thường thấy lời gọi đi qua đối tượng bọc. Lời gọi trực tiếp target hoặc self-invocation có thể không đi qua interceptor.
- **Weaving trên call join point:** chọn các vị trí gọi method; tập điểm cắt có thể khác execution join point.
- **Weaving trên execution join point:** can thiệp lúc method thực thi; không đồng nghĩa mọi construction, field access hoặc async task sẽ được chặn.
- **Instrumentation khi chạy:** có thể bị thay đổi bởi cấu hình, môi trường, version agent hoặc cách nạp mã.

Nếu quy tắc về giá hoặc một state invariant chỉ tồn tại trong advice, đường thực thi bypass được advice sẽ thiếu quy tắc. Với logging, bỏ log có thể là lỗi quan sát; với hoàn tiền hoặc chuyển tiền, bỏ quy tắc cốt lõi có thể gây sai dữ liệu và rủi ro đáng kể.

Cách giảm rủi ro:

1. Đặt domain invariant tại nơi thực hiện state transition hoặc policy được gọi tường minh.
2. Xác định các entry paths: API, batch job, message consumer, scheduler, CLI, test utility và gọi giữa service.
3. Sử dụng AOP cho policy enforcement tại boundary khi có lý do, nhưng không giả định nó thay thế mọi bảo vệ ở domain/storage.
4. Test cả đường gọi có aspect và những đường trực tiếp có thể tồn tại.
5. Có coverage test/architecture test cho protected operations nếu an toàn phụ thuộc vào pointcut.

## 10. “Giữ tường minh” không có nghĩa copy-paste logic ở nhiều nơi

Một hiểu nhầm là chỉ có hai lựa chọn: viết cùng quy tắc trong mọi phương thức hoặc đưa nó vào aspect. Thực tế có thể tách quy tắc thành abstraction có tên:

~~~text
OrderApplicationService
  -> PricingPolicy.calculate()
  -> InventoryPolicy.ensureReservable()
  -> OrderAggregate.confirm()

RefundApplicationService
  -> RefundEligibilityPolicy.check()
  -> RefundAggregate.issue()

Cross-cutting aspects
  -> logging / metrics / tracing tại boundary
  -> authorization enforcement theo chính sách đã khai báo
~~~

Mỗi use case gọi policy phù hợp, không phải chứa lại toàn bộ code. Tính tường minh nằm ở **đường phụ thuộc, tên và hợp đồng**, không nằm ở số dòng. Nếu một policy được nhiều use case dùng, service hoặc policy object có thể tái sử dụng mà vẫn biểu diễn quy tắc như một quyết định miền.

Một aspect quá “thông minh” thường biến lời gọi nghiệp vụ thành một bí mật: người đọc thấy calculate(), nhưng discount và tax lại được ghép thêm ở những vòng advice mà không có dấu hiệu trong hợp đồng. Loại coupling này làm refactor và bảo trì khó hơn lợi ích giảm trùng lặp mã.

## 11. Invariant cần bảo vệ gần thời điểm thay đổi trạng thái

Có những quy tắc đọc trạng thái có thể thay đổi giữa lúc kiểm tra và lúc dùng (**TOCTOU – time of check to time of use**).

Ví dụ:

~~~text
T1: advice kiểm tra balance >= withdrawal
T2: một transaction khác thay đổi balance
T3: business method thực hiện withdrawal
~~~

Một kiểm tra tại method entry không bảo đảm bất biến vẫn đúng ở T3. Với thao tác nhạy cảm, cần xác định biện pháp nhất quán: kiểm tra và cập nhật trong transaction thích hợp, optimistic version, conditional update hoặc locking theo mô hình dữ liệu.

Phần kiểm tra có thể được hỗ trợ bởi aspect ở boundary, nhưng **invariant về trạng thái bền vững** không nên chỉ dựa vào một kết quả boolean đọc từ quá sớm. Nó thuộc hợp đồng của thao tác ghi/commit có thẩm quyền.

Tương tự:

- “Chỉ được chuyển đơn DRAFT → APPROVED” phải bảo đảm trong logic chuyển trạng thái, kể cả khi caller là batch job.
- “Không hoàn tiền hai lần cùng payment” cần idempotency key/unique constraint hoặc cơ chế chống lặp thích hợp.
- “Không vượt tồn kho” cần xử lý cạnh tranh đồng thời tại thời điểm ghi.
- “Không truy cập dữ liệu tenant khác” cần bảo vệ nguồn dữ liệu và phân quyền resource; không chỉ tin tenant ID do request tự khai.
- “Không dùng quyền đã thu hồi” cần xem thời hạn authorization decision và mốc kiểm tra lại.

## 12. Authorization: cơ chế chung và luật truy cập riêng

Authorization là ví dụ cần phân chia trách nhiệm cẩn thận. Một authorization aspect có thể:

1. Chọn những protected operations đã đánh dấu hoặc thuộc contract.
2. Lấy **trusted principal** và invocation context.
3. Resolve action cùng resource descriptor.
4. Gọi policy evaluator.
5. Deny trước proceed khi không đủ quyền.
6. Ghi event quyết định an toàn và cleanup context.

Nhưng **quy tắc** “nhân viên chỉ phê duyệt hợp đồng thuộc phòng ban mình và dưới hạn mức được cấp” cần được mô tả trong policy rõ, có kiểm thử và dữ liệu resource đáng tin. Không nên nhét một danh sách điều kiện đặc biệt của từng loại hợp đồng vào một AuthorizationAspect dùng chung.

Ngoài ra, context từ ThreadLocal không tự bảo đảm danh tính đã được xác thực. Quyền trên tài nguyên có thể thay đổi; quyết định allow phải có phạm vi, hạn dùng và cơ chế revalidation phù hợp. Lời gọi trực tiếp vượt proxy không nên cho phép bỏ qua enforcement quan trọng.

**Đây không phải lý do tránh AOP trong bảo mật.** Đây là lý do phân định **enforcement mechanism** với **policy quyết định** và thiết kế kiểm soát ở các trust boundary đúng.

## 13. Retry, transaction và caching cũng có quy tắc miền

### Retry

Một retry advice tổng quát chỉ an toàn cho tập operation có hợp đồng xử lý lặp phù hợp. Việc gửi email, thu tiền hay chuyển trạng thái có thể không idempotent. Không mặc nhiên retry mọi RuntimeException.

Mô tả policy bằng các thành phần tường minh: attempt limit, backoff, retryable exceptions, deadline, idempotency strategy và cách xử lý kết quả sau lần thử cuối. Nếu một operation không chịu được retry, phải loại trừ nó hoặc cấu trúc lại cơ chế.

### Transaction

Một transaction aspect có thể bắt đầu/kết thúc transaction, nhưng **ranh giới atomicity** là quyết định gắn với use case và bất biến. Nếu chia một operation thành nhiều transaction hoặc giữ transaction xuyên async boundary một cách máy móc, trạng thái có thể không như mong muốn. Commit/rollback cần được định nghĩa theo luật nghiệp vụ và API lưu trữ.

### Cache

Một cache advice có thể giảm số lần tính toán, nhưng key, TTL, invalidation, tenant isolation, consistency và dữ liệu nhạy cảm phải rõ. Nếu cache trả một giá cũ sau khi chương trình khuyến mại thay đổi, policy có thể sai. Đừng coi “mọi method bắt đầu bằng get” là đủ chứng minh cache an toàn.

Một tiêu chí chung: khi **policy chứa tri thức miền biến thiên**, giữ tri thức đó trong thành phần tường minh, dù mechanism được điều phối bằng advice.

## 14. Thứ tự các Aspect có thể thay đổi ý nghĩa

Một operation có thể bị bọc bởi nhiều aspect:

~~~text
LoggingAdvice
  -> AuthorizationAdvice
    -> RetryAdvice
      -> TransactionAdvice
        -> businessOperation
~~~

Với thứ tự này, logging ở ngoài có thể thấy cả denial; retry có thể thực thi bên trong transaction advice nhiều lần. Đảo thứ tự có thể khiến transaction bao toàn bộ retry, authorization check xảy ra từng attempt hoặc timer đo những phạm vi khác nhau.

Phải xác định và kiểm thử:

- Advice nào được phép **chặn không cho proceed**?
- Advice nào được phép **lặp proceed** và khi nào?
- Exception nào dẫn tới rollback hoặc retry?
- Timer đo operation, attempt hay dependency?
- Business outcome được ghi tại mốc nào?
- Nếu một advice ném exception, các lớp ngoài nhìn thấy gì?
- Nếu có security context, scope được tạo/đóng trên thread nào?
- Với task bất đồng bộ, những lớp advice nào kết thúc trước task?

Một quy tắc cốt lõi được thực hiện thông qua nhiều advice không có thứ tự được kiểm soát sẽ khó đảm bảo tính đúng. Việc gọi policy tường minh trong use case giúp làm rõ ít nhất phần quyết định nghiệp vụ.

## 15. Vòng đời bất đồng bộ: return chưa phải kết quả cuối

Một method có thể chỉ submit công việc và trả Future hoặc CompletionStage:

~~~text
around advice enters
  -> proceed() returns CompletionStage
around advice exits
  -> task still executing
  -> completion occurs later
~~~

Nếu aspect đặt luật “chỉ chốt đơn khi tồn kho đủ” ở after-returning, nó có thể chạy **trước khi công việc xác nhận tồn kho hoàn tất**. Tương tự, ghi success vào outcome ngay khi method trả stage là sai mốc.

Cần tách:

- **Invocation lifecycle:** thời gian method được chặn chạy cho tới return/throw đồng bộ.
- **Task lifecycle:** từ lúc công việc thực tế chạy tới khi dừng, cleanup tài nguyên.
- **Completion lifecycle:** tín hiệu kết quả được hoàn tất, có thể thành công, lỗi, hủy hoặc timeout theo API.
- **Business commit lifecycle:** thay đổi trạng thái đã được xác nhận bền vững.

Một rule phụ thuộc dữ liệu cuối phải được thực thi ở nơi có dữ liệu và có quyền thay đổi trạng thái. Một observer completion có thể ghi metric/log đúng mốc, nhưng không nên thay policy được thực thi ở task/transaction boundary.

Đừng giữ lock, transaction hoặc scope của invocation ngắn đến lúc task dài hoàn tất nếu resource không được thiết kế cho vòng đời đó. Khi truyền identity hoặc correlation qua executor, dùng snapshot phù hợp, scope riêng ở worker và try/finally cleanup.

## 16. Logging và tracing hỗ trợ hiểu nghiệp vụ, không định nghĩa nghiệp vụ

Một aspect logging có thể phát:

~~~json
{
  "event": "operation_finished",
  "operation": "order.checkout",
  "outcome": "success",
  "duration_ms": 37,
  "correlation_id": "req-42"
}
~~~

Đây là dữ liệu minh họa, không phải một kết quả stdout của Java. Nó giúp tìm kiếm và tổng hợp, nhưng **không phải bằng chứng một giao dịch đã commit** nếu event được ghi trước commit.

Các lưu ý:

- Không log password, token, thông tin thanh toán hoặc toàn bộ object vì tiện.
- Tên operation và error code nên ổn định và có tập giá trị hữu hạn; không lấy ID mỗi đơn hàng làm label metric thông thường.
- Nếu một operation có nhiều retry attempts, không đếm mỗi attempt là một business operation.
- Nếu nhiều aspect/instrumenter cùng ghi business completion, có thể đo trùng.
- Audit có yêu cầu tính toàn vẹn nên có cơ chế riêng, không mặc định logger.info tương đương audit event bền vững.

**Quy tắc nghiệp vụ** nên sinh outcome rõ ràng; **aspect observability** tiêu thụ outcome đó để quan sát, thay vì suy đoán hoặc âm thầm sửa outcome sau khi nghiệp vụ trả kết quả.

## 17. Trường hợp hợp lệ cho aspect có ảnh hưởng hành vi

Không phải mọi advice đều phải chỉ đọc. Một số concern mang nghĩa kiểm soát luồng và có thể được triển khai bằng aspect nếu contract được khai báo:

| Concern | Tác động có chủ ý | Điều kiện an toàn quan trọng |
| --- | --- | --- |
| Authorization | Deny trước khi xử lý | Principal tin cậy, policy resource, không bypass |
| Rate limiting | Từ chối hoặc chờ permit | Key, quota, tài nguyên và vòng đời permit rõ |
| Transaction | Commit/rollback | Boundary atomicity, propagation, exception policy |
| Retry | Thực hiện lại attempt | Idempotency, deadline, loại lỗi, số lần thử |
| Circuit breaker | Fail fast khi phụ thuộc lỗi | Trạng thái breaker, fallback và lỗi rõ |
| Input normalization chung | Chuẩn hóa một tập input có contract | Không đổi ngầm ý nghĩa miền riêng |

Điểm chung: **tác động được công khai trong API, metadata hoặc kiến trúc**, và có test cho cả allow/deny, side effect, exception, concurrent execution và lựa chọn pointcut. Với những logic thay đổi liên tục theo domain, có thể giữ policy tường minh còn aspect chịu phần enforcement.

Nếu một concern chỉ xuất hiện ở một nơi hoặc đòi nhiều ngoại lệ nghiệp vụ, gọi một API trực tiếp thường đơn giản hơn.

## 18. Những sai lầm thường gặp và sửa thế nào

### Sai lầm A: “Có code lặp là cần aspect”

Nhiều đoạn tính giá lặp nhau có thể nên được thay bằng PricingPolicy. AOP phù hợp hơn khi **chính sách áp dụng tại các join point** là ổn định, không phụ thuộc công thức từng nơi.

### Sai lầm B: “Quy tắc nghiệp vụ đặt trong advice vẫn dễ bảo trì”

Một advice áp dụng discount dựa trên method name làm chính sách khó truy vết, test và refactor. Di chuyển luật sang policy với đầu vào/ra rõ và để advice phục vụ quan sát/boundary enforcement.

### Sai lầm C: “Nếu pointcut khớp thì mọi đường gọi đều được bảo vệ”

Proxy có thể bị bypass; self-invocation hoặc gọi target trực tiếp không đi qua interceptor tương ứng. Kiểm thử runtime và đặt invariant quan trọng ở vị trí không dễ bỏ qua.

### Sai lầm D: “Thay đổi thứ tự aspect chỉ ảnh hưởng log”

Retry, transaction, authorization và cache có thể thay đổi hành vi thực, số lần side effect hoặc thời điểm commit. Ghi contract composition và test thứ tự.

### Sai lầm E: “Method trả về bình thường là nghiệp vụ thành công”

Một method có thể trả Result.Failure, Future chưa hoàn tất hoặc dữ liệu chưa commit. Observer và policy phải hiểu lifecycle, không gán success bằng một after-returning hook máy móc.

### Sai lầm F: “Giấu quy tắc ở một annotation là đủ tường minh”

Annotation chỉ có thể mô tả metadata; khi chính sách phụ thuộc hàng chục trường hoặc nhánh miền, cần component/policy được đặt tên, version hóa và kiểm thử. Không để annotation string trở thành một ngôn ngữ điều khiển nghiệp vụ khó kiểm tra.

### Sai lầm G: “Lỗi instrumentation có thể làm hỏng operation”

Một logger hoặc serializer ném exception trong advice có thể che exception gốc; một callback phụ có thể đổi trạng thái dependent stage. Cần quy định failure policy để quan sát không vô tình làm đổi contract nghiệp vụ.

### Sai lầm H: “Càng nhiều aspect càng tách biệt tốt”

Một hệ thống có nhiều aspect chồng pointcut có thể sinh log/metric trùng, rối thứ tự và giảm khả năng hiểu. Cần ownership cho từng concern, scope rõ, naming nhất quán và kiểm thử tích hợp.

## 19. Bộ câu hỏi quyết định dùng AOP hay abstraction tường minh

Trước khi tạo aspect mới, hãy trả lời:

1. **Ai là người sở hữu quy tắc?** Team miền, nhóm bảo mật hay nhóm hạ tầng?
2. **Quy tắc có thay đổi theo sản phẩm/khách hàng không?** Nếu có, policy miền nên được biểu diễn ở đâu?
3. **Một người chỉ đọc use case có hiểu business outcome không?** Nếu không, có luật bị giấu trong advice?
4. **Bỏ cơ chế AOP có làm sai dữ liệu không?** Nếu có, cần bảo vệ invariant ở domain/storage hoặc enforcement boundary đáng tin.
5. **Pointcut có bền vững khi đổi tên, tách helper hoặc di chuyển class không?**
6. **Có cần gọi proceed nhiều lần hoặc thay đổi return value không?** Nếu có, contract và idempotency đã rõ chưa?
7. **Có nhiều cơ chế cùng quan sát một operation không?** Nếu có, ai chịu trách nhiệm metric/log outcome?
8. **Có async, retry, transaction hoặc cancellation không?** Các mốc lifecycle đã được phân biệt?
9. **Có thể kiểm thử policy riêng mà không cần weaving không?**
10. **Một lần sửa business rule có ảnh hưởng những operation không liên quan?** Nếu có, phạm vi advice quá rộng?
11. **Chi phí performance/traceability có tương xứng lợi ích giảm phân tán mã không?**
12. **Có đường gọi nào đi vòng qua proxy hoặc observer không?** Invariant còn đúng trên đường đó không?

Nếu đa số câu trả lời chỉ ra logic miền có nhiều biến thể hoặc phụ thuộc state, ưu tiên **policy object, domain service, state machine hoặc use case method**. Nếu concern có semantics nhất quán và điểm cắt ổn định, aspect là ứng viên tốt.

## 20. Kiểm thử kiến trúc và hành vi

### Kiểm thử chính sách nghiệp vụ

- Tất cả trường hợp premium/regular và biên quantity, đơn giá đều cho kết quả theo công thức.
- Giá trị không hợp lệ ném exception được định nghĩa.
- Overflow, rounding và currency được xử lý theo contract.
- Thay đổi rule không bắt buộc sửa logging advice.
- Domain invariant vẫn đúng khi gọi implementation trực tiếp, không qua proxy.
- Side effect phải phản ánh kết quả policy tại commit, không phản ánh giá trị đã lỗi thời.

### Kiểm thử Aspect

- Pointcut chỉ chọn operations cần quan sát hoặc bảo vệ.
- Advice gọi proceed đúng một lần khi không có retry được thiết kế riêng.
- Return value và exception gốc được giữ nguyên.
- Method helper hoặc direct call không có logging nếu không thuộc điểm cắt.
- Nhiều aspect lồng nhau không đếm business outcome trùng.
- Với async, không ghi completion chỉ vì method trả stage.
- Thread/correlation context được cleanup trong finally, không rò vào thread pool.
- Failure của observer có chính sách rõ, không vô tình làm business call sai.

### Kiểm thử tích hợp

- Đường vào thật (request, message, job) gọi tới use case chính xác.
- Protected operations không bypass enforcement cần thiết.
- Thứ tự authorization, retry, transaction và logging đúng contract.
- Một thay đổi pointcut không vô tình khiến luật nghiệp vụ mất hiệu lực.
- Một domain refactor không khiến số business events tăng/giảm vô cớ.

Một tiêu chuẩn mạnh: **kiểm thử quy tắc miền vẫn thành công khi tắt các aspect chỉ mang chức năng quan sát**. Với aspect authorization/transaction ảnh hưởng behavior, cần kiểm thử riêng các ranh giới bắt buộc, không vô hiệu hóa cơ chế an toàn trong hệ thống đang vận hành.

## 21. Quy trình cải tổ một Aspect đang chứa quá nhiều business logic

**Bước 1 — Khoanh vùng behavior.** Liệt kê những câu điều kiện trong advice quyết định giá, trạng thái, hạn mức, quyền sở hữu hoặc side effect; đánh dấu những nhánh thuần hạ tầng.

**Bước 2 — Xác định chủ sở hữu miền.** Quy tắc nào thuộc pricing, order, payment, membership hay inventory? Ai phê duyệt thay đổi policy?

**Bước 3 — Viết kiểm thử đặc tả hiện hành.** Bao gồm trường hợp thường, biên, failure, concurrency và dữ liệu cũ. Mục tiêu là bảo toàn kết quả đúng, đồng thời phơi bày behavior đã sai hoặc mơ hồ.

**Bước 4 — Tách policy có tên và hợp đồng.** Đưa công thức, state transition và điều kiện chuyên biệt về domain service/policy/aggregate. Công bố input, output, lỗi, rounding và version.

**Bước 5 — Cho use case gọi policy tường minh.** Luồng đọc code thể hiện thời điểm quyết định nghiệp vụ, không dựa vào tên method để lời khuyên AOP kích hoạt.

**Bước 6 — Thu hẹp advice còn mechanism chung.** Logging, metrics, tracing hoặc enforcement đã có metadata và policy component đúng nghĩa; xóa các nhánh logic miền không còn cần thiết.

**Bước 7 — Xác minh mọi đường gọi.** Direct implementation, proxy, nested call, async, retry và các entry paths khác nhau.

**Bước 8 — Đối chiếu kết quả và observability.** Nghiệp vụ sau refactor giữ semantics dự kiến; telemetry chỉ phát các tín hiệu đúng owner, không nhân đôi.

Không cần di chuyển mọi nhánh trong một lần. Mỗi phần được tách phải có contract và kiểm thử trước khi thay đường gọi, đặc biệt nếu hệ thống đã có các workflow chứa dữ liệu quan trọng.

## 22. Checklist review nhanh

- [ ] Quy tắc quyết định business outcome xuất hiện qua service/entity/policy có tên rõ.
- [ ] Domain invariant được bảo vệ ở điểm có thẩm quyền, kể cả khi bypass proxy.
- [ ] Aspect áp dụng concern xuyên suốt có semantics chung và pointcut đã được kiểm chứng.
- [ ] Pointcut không phụ thuộc tràn lan vào tên helper hoặc package dễ đổi.
- [ ] Metadata/annotation diễn đạt chính sách công khai, không che giấu hàng loạt trường hợp miền.
- [ ] Advice bảo toàn return value và exception, trừ tác động đã được công bố.
- [ ] Retry có idempotency và error policy; transaction có boundary chính xác.
- [ ] Async invocation, task completion và durable commit được phân biệt.
- [ ] Logging/audit không tự tạo nguồn chân lý nghiệp vụ và không lộ dữ liệu nhạy cảm.
- [ ] Metric/span/log có owner, không double count khi nhiều công cụ cùng hoạt động.
- [ ] Policy có unit tests độc lập; Aspect có tests riêng cho interception/composition.
- [ ] Domain refactor không khiến quy tắc biến mất do đổi tên hoặc thay đường gọi.
- [ ] Quyết định tổ chức mã giúp người bảo trì hiểu điều kiện nghiệp vụ từ use case.

## 23. Tóm lại qua một tình huống

Giả sử đội phát triển nhận yêu cầu: “Khách premium được giảm 10% cho một tập sản phẩm hợp lệ; đơn hàng vượt hạn mức phải từ chối; mọi yêu cầu báo giá cần có duration và outcome log.”

Kiến trúc rõ ràng:

- **PricingPolicy** xác định hàng nào được giảm, tỷ lệ, thứ tự tính thuế và rounding.
- **Eligibility/LimitPolicy** xác định hạn mức và những điều kiện từ chối.
- **QuoteUseCase** gọi các policy, tạo kết quả và điều phối hành vi.
- **ObservabilityAspect** ghi một event kết thúc, duration và correlation ID theo boundary đã chọn.
- **Authorization mechanism** chỉ cho phép các đối tượng đủ quyền truy cập operation, với policy riêng nếu cần.

Khi tỷ lệ chiết khấu đổi, không phải sửa aspect đo thời gian; khi schema log đổi, không phải viết lại PricingPolicy. Khi thêm một use case báo giá, người review nhìn thấy chính sách được gọi và cách chọn pointcut. Các quy tắc ảnh hưởng business outcome vẫn có tên, quyền sở hữu và kiểm thử.

**Bài học:** giữ quy tắc nghiệp vụ cốt lõi tường minh là điều kiện để AOP phát huy lợi ích mà không làm mất khả năng giải thích hệ thống. Aspect xử lý mechanism xuyên suốt khi điểm cắt và hợp đồng đủ rõ; chính sách miền quyết định giá trị, trạng thái và invariant tại nơi có thể xác minh chúng.