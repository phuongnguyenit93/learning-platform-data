# Ghi nhật ký tại ranh giới nghiệp vụ thay vì mọi phương thức trong AOP

## 1. Ý tưởng cốt lõi

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), ghi nhật ký (logging) là một mối quan tâm xuyên suốt (**cross-cutting concern**): nhiều thao tác nghiệp vụ cần được quan sát theo cách nhất quán mà không chèn cùng một khối ghi log vào mọi nơi.

Nhưng **AOP không đồng nghĩa với việc tự động log tất cả phương thức**. Khi một tác vụ “đặt hàng” gọi hàng chục hàm để kiểm tra dữ liệu, tính giá, kiểm tra tồn kho, ghi trạng thái và gửi thông báo, log mỗi lần vào/ra hàm dễ tạo hàng trăm dòng kỹ thuật mà vẫn không trả lời được câu hỏi quan trọng: *yêu cầu đặt hàng đã được chấp nhận, bị từ chối hay thất bại?*

Nguyên tắc của bài này:

> Đặt quan sát mặc định tại **ranh giới nghiệp vụ có ý nghĩa** — nơi một hành động của người dùng, một lệnh, một job hoặc một sự kiện đi vào và cho ra kết quả — rồi chỉ thêm log ở các bước bên trong khi chúng thực sự giúp chẩn đoán hoặc đáp ứng yêu cầu vận hành.

“Ranh giới” ở đây là ranh giới về **ngữ nghĩa của thao tác**, không nhất thiết là lớp ngoài cùng trong chương trình hoặc mọi public method. Một lần xử lý thông điệp, một lần chạy tác vụ định kỳ, một use case xử lý giao dịch hoặc một operation của dịch vụ có thể là ranh giới phù hợp. Việc chọn điểm cắt phụ thuộc vào kiến trúc và câu hỏi cần quan sát.

### Phân biệt những khái niệm dễ nhầm

- **Business operation / use case:** một hành động có ý nghĩa với người sử dụng hệ thống hoặc nghiệp vụ, ví dụ “xác nhận đơn hàng”, “phê duyệt khoản chi”, “hoàn tất xuất kho”.
- **Business boundary:** điểm bắt đầu/kết thúc có hợp đồng và kết quả của operation đó, đủ ổn định để thống kê và chẩn đoán.
- **Join point:** điểm trong chương trình mà cơ chế AOP có thể can thiệp, như lần gọi hoặc thực thi một phương thức. Không phải mọi điểm nghiệp vụ đều mặc nhiên là join point được công cụ AOP hỗ trợ.
- **Pointcut:** quy tắc chọn các join point cần can thiệp.
- **Advice:** hành vi áp dụng tại điểm được chọn (trước, sau, khi ném lỗi hoặc bao quanh).
- **Aspect:** tập hợp có tổ chức của pointcut và advice phục vụ mối quan tâm xuyên suốt.

**Mục đích của pointcut ở đây là chọn đúng operation; mục đích của advice là ghi lại điều có ích.** Độ bao phủ rộng không phải là chỉ số chất lượng logging.

## 2. Vì sao log mọi phương thức thường phản tác dụng?

Hãy xem đường đi đơn giản:

~~~text
placeOrder()
    validateCustomer()
    normalizeAddress()
    calculatePrice()
        calculateDiscount()
        calculateTax()
    reserveInventory()
    persistOrder()
    sendConfirmation()
~~~

Nếu advice ghi “ENTER/EXIT” cho tất cả phương thức, chỉ một yêu cầu đã sinh ra ít nhất 18 dòng (chưa kể các thao tác bên dưới). Trong một chương trình thực, recursion, thư viện, helper và callback có thể làm số dòng tăng rất mạnh. Người đọc vẫn phải suy luận ngược xem operation nào đang diễn ra và cuối cùng có thành công không.

Những vấn đề điển hình:

1. **Nhiễu tín hiệu:** các sự kiện có giá trị thấp che khuất thành công/thất bại quan trọng.
2. **Chi phí:** format chuỗi, cấp phát đối tượng, ghi I/O, indexing và lưu trữ tăng theo số lần gọi, không theo số operation nghiệp vụ.
3. **Khó liên kết:** log “enter calculateTax()” không cho biết nó thuộc yêu cầu đặt hàng nào nếu thiếu correlation ID.
4. **Lộ dữ liệu:** log tham số và giá trị trả về một cách máy móc có thể ghi mật khẩu, token, thông tin thanh toán hoặc dữ liệu cá nhân.
5. **Phụ thuộc chi tiết triển khai:** tách một phương thức thành ba helper làm số log thay đổi dù hành vi nghiệp vụ không đổi.
6. **Lặp hoặc tự gọi lại:** advice có thể quan sát cả các lời gọi lồng nhau, đôi khi chính bộ phát log cũng khớp pointcut và gây recursion.
7. **Diễn giải sai outcome:** phương thức nội bộ trả bình thường không có nghĩa cả use case thành công; một helper lỗi nhưng được retry thành công cũng không nhất thiết là một operation thất bại.

Ghi log ở mọi phương thức chỉ có thể phù hợp với một phiên chẩn đoán có kiểm soát, tập phương thức nhỏ hoặc công cụ trace chuyên dụng có sampling và ngân sách rõ ràng. Nó không phải chính sách ghi log nghiệp vụ mặc định.

## 3. Chọn ranh giới nghiệp vụ ở đâu?

Một ranh giới tốt thường có một hoặc nhiều đặc tính:

- Có **tên operation ổn định**, phản ánh mục đích, ví dụ `order.place` hoặc `invoice.approve`.
- Có đầu vào và kết quả đủ rõ để phân loại **success, rejected, failed, cancelled**.
- Có thể xác định ai/cái gì khởi tạo, correlation ID và thời điểm bắt đầu.
- Gần với nơi mã thực hiện **use case** hoặc nơi task được điều phối; cho phép quan sát đầy đủ những bước bên trong.
- Không thay đổi chỉ vì refactor helper, cấu trúc package hoặc thuật toán.

Bảng gợi ý:

| Phạm vi | Nên ghi ở đâu? | Sự kiện quan tâm | Mức độ |
| --- | --- | --- | --- |
| Hành động người dùng | Điểm bắt đầu/kết thúc use case | “Đặt hàng được chấp nhận” hoặc “bị từ chối” | Mặc định |
| Job định kỳ | Một lần chạy job, kèm run ID | “Bắt đầu, hoàn tất, thất bại, mất bao lâu” | Mặc định |
| Message consumer | Một lần xử lý message/command | “Đã xử lý, retry, đưa vào hàng đợi lỗi” | Mặc định |
| Giao tiếp dịch vụ bên ngoài | Điểm gọi phụ thuộc quan trọng | “Timeout, lỗi phụ thuộc, retry” | Bổ sung có chọn lọc |
| Repository, mapper, getter, validator nhỏ | Thường không phải boundary nghiệp vụ | Log chỉ khi có lỗi bất thường đáng chẩn đoán | Hạn chế |
| Từng bước tính toán thuần | Bên trong operation | Thường thay bằng test, metric hoặc trace khi cần | Không mặc định |

Ví dụ: một HTTP handler chỉ chuyển tham số sang use case có thể là ranh giới **giao thức**; còn use case `approvePayment` mới là ranh giới **nghiệp vụ**. Nếu log cả hai, hãy gắn vai trò rõ ràng: một bản ghi request transport, một bản ghi business outcome, cùng trace/correlation ID nhưng khác operation và khác ý nghĩa. Không ghi hai dòng tương đương chỉ vì có hai lớp.

Đối với một operation gồm nhiều command hợp lệ, ranh giới không nhất thiết là “một phương thức”. Có thể cần một định danh workflow và các sự kiện nghiệp vụ riêng để nắm được các bước trải qua nhiều process.

## 4. Ghi điều gì ở ranh giới?

Một bản ghi có giá trị thường thể hiện **“điều gì xảy ra với một operation?”**, thay vì “hàm tên gì vừa chạy?”.

### Các trường khuyến nghị

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `timestamp` | Thời gian sự kiện phát sinh, có múi giờ hoặc UTC | `2026-10-20T02:00:00Z` |
| `level` | Mức độ log, tách khỏi outcome | `INFO`, `WARN`, `ERROR` |
| `event` | Loại sự kiện ổn định | `business_operation_finished` |
| `operation` | Tên thao tác có cardinality thấp | `order.place` |
| `outcome` | Kết quả đã xác định theo hợp đồng | `success`, `rejected`, `failed` |
| `duration_ms` | Thời gian đo được, thống nhất mốc bắt đầu/kết thúc | `87.4` |
| `correlation_id` / `trace_id` | Ghép bản ghi của cùng luồng xử lý | ID theo ngữ cảnh |
| `error_code` | Nhóm nguyên nhân lỗi ổn định, đã được làm sạch | `INVENTORY_UNAVAILABLE` |
| `attempt` | Lần thử, nếu có retry | `2` |

Các trường khác chỉ thêm khi có mục đích rõ và được phép lưu: tenant ID đã xử lý phù hợp, loại tác vụ, kích thước batch, tên phụ thuộc, version schema. Không tự động ghi toàn bộ đối tượng request/response hoặc stack trace của mọi thành công.

**Structured logging** (ví dụ JSON một sự kiện trên một dòng) giúp truy vấn theo operation/outcome/duration chính xác hơn so với ghép chuỗi tùy ý. Chọn tên trường và schema ổn định để dashboard, alert và hệ thống tổng hợp dùng được lâu dài.

Ví dụ minh họa một bản ghi hoàn tất (các giá trị thời gian, ID và độ trễ chỉ để minh họa):

~~~json
{
  "timestamp": "2026-10-20T02:00:00Z",
  "level": "INFO",
  "event": "business_operation_finished",
  "operation": "order.place",
  "outcome": "success",
  "duration_ms": 87.4,
  "correlation_id": "req-7e23"
}
~~~

Đây là **định dạng dữ liệu ví dụ**, không phải stdout cố định của mã Java ở phần sau. Trong hệ thống thật, cần xác định bên nào phát timestamp, cách xử lý clock, cách tạo ID, cũng như thứ tự giữa log và việc chuyển kết quả tới người gọi.

## 5. Chọn chiến lược sự kiện: bắt đầu và kết thúc, hay chỉ hoàn tất?

Ba cách thường gặp:

**A. Một bản ghi khi operation kết thúc** — thường là điểm khởi đầu hiệu quả.

- Bao gồm tên operation, outcome và duration.
- Ít bản ghi, phù hợp hệ thống có lưu lượng cao.
- Nhược điểm: nếu tiến trình chết trước khi kết thúc, không có bản ghi hoàn tất; để phát hiện operation bị treo cần cơ chế ngoài log hoàn tất, chẳng hạn active-operation metric hoặc watchdog.

**B. Một bản ghi bắt đầu + một bản ghi kết thúc** — phù hợp operation quan trọng hoặc kéo dài.

- Bản ghi bắt đầu giúp nhận diện công việc đang hoạt động.
- Bản ghi kết thúc giúp đo kết quả; cần ID/attempt để ghép cặp.
- Có thể tăng lưu lượng log; việc thiếu dòng kết thúc không tự chứng minh một nguyên nhân cụ thể.

**C. Bản ghi kết thúc + các mốc nghiệp vụ chọn lọc** — phù hợp quy trình nhiều bước.

- Các mốc có ngữ nghĩa như `inventory_reserved`, `payment_authorized` có ích nếu được chính nghiệp vụ xác nhận.
- Tránh biến mọi helper call thành “milestone”.
- Các mốc phải phân biệt trạng thái dự định và trạng thái đã được hệ thống xác nhận.

Chọn một quy ước nhất quán; tránh một Aspect ghi success ở sau `proceed()` và Aspect khác lại ghi success khi kết quả bất đồng bộ hoàn tất, khiến mỗi operation thành công được đếm hai lần.

## 6. Pointcut: chọn theo ý nghĩa, không theo số lượng phương thức

Các cách nhận diện boundary:

1. **Đánh dấu tường minh bằng annotation hoặc metadata** trên method đại diện cho use case. Dễ review và dễ kiểm toán phạm vi; phải tránh đánh dấu helper tùy tiện.
2. **Một interface/contract của lớp điều phối nghiệp vụ**: mọi operation công khai trong một contract được chỉ định là boundary, thay vì toàn bộ package.
3. **Danh sách operation qua cấu hình có kiểm soát**: hữu ích khi không thể sửa source hoặc cần cấu hình instrumentation.
4. **Quy ước package/lớp**: có thể dùng nếu cấu trúc kiến trúc thực sự ổn định, nhưng nên có exclusion rõ cho helper/internal methods.

Các kiểu chọn quá rộng như “mọi phương thức public”, “mọi phương thức tên bắt đầu bằng get”, hoặc “mọi phương thức trong tất cả package ứng dụng” không mô tả được ngữ nghĩa nghiệp vụ. Khi triển khai bằng proxy, weaving lúc biên dịch, lúc tải lớp hoặc một interceptor khác, tập join point có thể khác nhau; cần kiểm tra **đường gọi thực tế được instrument**. Một lời gọi nội bộ cùng đối tượng có thể không đi qua interceptor dạng proxy; các cơ chế weaving khác có đặc điểm khác. Không mặc định annotation tự khiến advice chạy: annotation là metadata, còn AOP mechanism mới thực hiện interception.

Nếu dùng annotation, định nghĩa chặt chẽ:

- `operation` là định danh ổn định, ví dụ `order.place`, không phải UUID hay ID đơn hàng.
- Áp dụng cho những method cụ thể đại diện use case; tránh “đánh dấu cho đủ”.
- Rõ việc tra annotation ở interface method, implementation method hoặc quy tắc kế thừa; metadata trên một method không luôn tự kế thừa sang method override.
- Khi đổi tên phương thức nhưng nghiệp vụ không đổi, cố gắng giữ tên operation ổn định để đồ thị lịch sử không bị đứt.

## 7. Around advice đúng trách nhiệm

Ở một lời gọi đồng bộ, around advice điển hình có thể:

~~~text
around(business operation):
    operation = stableBusinessName()
    context = safeCorrelationContext()
    start = monotonicClock()
    try:
        result = proceedExactlyOnce()
        recordFinished(operation, "success", elapsed(start), context)
        return result
    catch KnownBusinessRejection:
        recordFinished(operation, "rejected", elapsed(start), context)
        rethrow
    catch error:
        recordFinished(operation, "failed", elapsed(start), context)
        rethrow
~~~

Đây là **giả mã** minh họa điểm đặt trách nhiệm; tên hàm và kiểu lỗi chưa định nghĩa.

Những điều cần giữ:

- **Không sửa kết quả nghiệp vụ** nếu chức năng của Aspect chỉ là quan sát.
- **Không nuốt exception** và không biến một lỗi thành kết quả thành công.
- **Không gọi proceed() hai lần**, trừ khi retry thật sự là chính sách riêng có đặc tả về idempotency.
- **Dùng đồng hồ đơn điệu** để đo khoảng thời gian (trong Java: `System.nanoTime()`), không lấy chênh lệch wall clock có thể bị chỉnh.
- **Giữ logging tách biệt khỏi nghiệp vụ**: nếu hệ thống log lỗi, cố gắng không làm operation thất bại theo cách ngoài ý muốn. Chiến lược xử lý lỗi logger là quyết định kiến trúc; không được bí mật bỏ qua lỗi khi log là phần của một bảo đảm kiểm toán bắt buộc.
- **Phân loại exception theo contract**: validation rejection có thể là kết quả được dự kiến, không phải lỗi hệ thống; không thể suy ra mọi `IllegalArgumentException` đều là business rejection.

Một điểm đặc biệt: **trả về bình thường của phương thức không luôn tương đương thành công nghiệp vụ**. Phương thức có thể trả `Result.Failure`, trạng thái “pending”, hoặc CompletionStage chưa hoàn tất. Advice phải hiểu hợp đồng của operation mới gán outcome chính xác.

## 8. Ví dụ Java 17: dynamic proxy chỉ log method được đánh dấu là boundary

Ví dụ chạy độc lập dưới đây sử dụng **JDK dynamic proxy** làm cơ chế interception tối giản để minh họa AOP chung. Chỉ phương thức `placeOrder` được đánh dấu là boundary; `findStatus` và các helper nội bộ không tạo event nghiệp vụ. Đây là mô hình học tập, không phải thư viện AOP hoàn chỉnh.

Tạo tệp **BusinessBoundaryLoggingDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.LongAdder;

public final class BusinessBoundaryLoggingDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface BusinessBoundary {
        String operation();
    }

    interface OrderService {
        @BusinessBoundary(operation = "order.place")
        String placeOrder(String orderId);

        String findStatus(String orderId);
    }

    static final class DefaultOrderService implements OrderService {
        @Override
        public String placeOrder(String orderId) {
            validate(orderId);
            return "ACCEPTED";
        }

        @Override
        public String findStatus(String orderId) {
            return "ACTIVE";
        }

        private void validate(String orderId) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId is missing");
            }
        }
    }

    static final class BoundaryAdvice implements InvocationHandler {
        private final Object target;
        private final LongAdder totalDurationNanos = new LongAdder();

        BoundaryAdvice(Object target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {

            BusinessBoundary boundary =
                    method.getAnnotation(BusinessBoundary.class);

            if (boundary == null) {
                return callTarget(method, args);
            }

            String operation = boundary.operation();
            long start = System.nanoTime();
            System.out.println("event=started operation=" + operation);

            try {
                Object result = callTarget(method, args);
                System.out.println("event=finished operation=" + operation
                        + " outcome=success");
                return result;
            } catch (Throwable error) {
                System.out.println("event=finished operation=" + operation
                        + " outcome=failure error_type="
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                totalDurationNanos.add(System.nanoTime() - start);
            }
        }

        private Object callTarget(Method method, Object[] args)
                throws Throwable {
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException wrapper) {
                // Phản ánh lỗi gốc của nghiệp vụ, không để lộ lớp bọc reflection.
                throw wrapper.getCause();
            }
        }
    }

    public static void main(String[] args) {
        OrderService service = (OrderService) Proxy.newProxyInstance(
                OrderService.class.getClassLoader(),
                new Class<?>[] { OrderService.class },
                new BoundaryAdvice(new DefaultOrderService())
        );

        // Method không được đánh dấu: không tạo log nghiệp vụ.
        System.out.println("status=" + service.findStatus("O-100"));

        System.out.println("result=" + service.placeOrder("O-100"));

        try {
            service.placeOrder(" ");
        } catch (IllegalArgumentException error) {
            System.out.println("caller_error="
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

Chạy bằng Java 17 trở lên:

~~~bash
javac BusinessBoundaryLoggingDemo.java
java BusinessBoundaryLoggingDemo
~~~

Đầu ra chính xác:

~~~text
status=ACTIVE
event=started operation=order.place
event=finished operation=order.place outcome=success
result=ACCEPTED
event=started operation=order.place
event=finished operation=order.place outcome=failure error_type=IllegalArgumentException
caller_error=IllegalArgumentException
~~~

### Điểm cần hiểu từ ví dụ

- Method `placeOrder` mang metadata `@BusinessBoundary`; `findStatus` và `validate` không được log theo chính sách boundary.
- Proxy chỉ chặn lời gọi thông qua interface `OrderService`; helper `validate` được gọi trực tiếp trong implementation. Cơ chế khác có thể cung cấp tập join point khác.
- `Method.invoke` bọc lỗi do target ném trong `InvocationTargetException`; `callTarget` gỡ lớp bọc để caller vẫn thấy `IllegalArgumentException`.
- Giá trị trả về `ACCEPTED` vẫn được trả về nguyên vẹn; logging không sửa business behavior.
- `LongAdder` cho thấy vị trí ghi nhận duration dùng đồng hồ đơn điệu. Ví dụ không in duration vì giá trị phụ thuộc máy chạy; trong hệ thống thật cần đưa vào hệ thống metric với đơn vị và nhãn rõ ràng.
- `outcome=failure` trong ví dụ chỉ có nghĩa lời gọi ném exception; chưa phân loại `rejected` theo hợp đồng nghiệp vụ. Trong chương trình thật, phải có loại kết quả/lỗi đã định nghĩa để phân biệt rejection có chủ đích với lỗi hạ tầng.
- Code `System.out.println` chỉ để tạo đầu ra dễ kiểm tra. Logging thật nên dùng API ghi log có cấu trúc, ngưỡng level, cơ chế chống nghẽn và chính sách xử lý dữ liệu nhạy cảm.
- Đây là instrumentation đồng bộ; với API bất đồng bộ, việc method trả về handle chưa phải thời điểm operation hoàn tất.

## 9. Điểm quan sát trước và sau: đủ sự kiện, tránh nhân đôi

Nên xác định rõ **ai chịu trách nhiệm phát sự kiện chính của một operation**. Nếu các Aspect cùng bọc nhau, chúng có thể tạo bản ghi khác nhau cho cùng operation:

~~~text
TracingAdvice -> BoundaryLoggingAdvice -> RetryAdvice -> businessOperation
~~~

Trong minh họa này, một lần gọi nghiệp vụ có thể chứa nhiều attempt do retry. Nếu logging nằm ngoài retry, thường ghi một outcome cho operation tổng thể; nếu nằm trong retry, có thể ghi outcome từng attempt. Thứ tự thực thi và phạm vi pointcut quyết định ý nghĩa kết quả, không thể suy đoán chỉ từ tên Aspect.

Quy ước nên phân biệt:

- **Operation:** một lần người dùng hoặc hệ thống yêu cầu thực hiện việc.
- **Attempt:** một lượt thử của operation, có thể có nhiều lần khi retry.
- **Step:** một mốc có ý nghĩa nghiệp vụ hoặc hạ tầng bên trong.
- **Dependency call:** một lần gọi dịch vụ bên ngoài, có thể nhiều hơn một trong một attempt.

Ví dụ, một operation cuối cùng thành công sau hai lần retry không nên mặc định tạo hai sự kiện “order.place failed” ở cấp operation. Nếu cần quan sát attempt, đặt các bản ghi có tên `attempt_failed`, `attempt_succeeded` cùng attempt number và ID của operation. Điều này giúp alert phản ánh lỗi thực thay vì chênh lệch do cơ chế retry.

## 10. Đo thời gian đúng cấp độ

Logging AOP thường bổ sung duration; nhưng định nghĩa mốc đo phải rõ:

| Loại thời gian | Bắt đầu | Kết thúc | Dùng khi |
| --- | --- | --- | --- |
| Invocation duration | Trước `proceed()` | Khi `proceed()` trả về hoặc ném lỗi | Đo lời gọi đồng bộ |
| End-to-end async duration | Khi operation được chấp nhận | Khi kết quả cuối của operation được xác nhận | Đo trải nghiệm/tổng thời gian workflow |
| Queue waiting time | Khi gửi task | Khi task bắt đầu thực thi | Phân tích nghẽn hàng đợi |
| Task processing time | Khi task thực sự bắt đầu | Khi task thực sự dừng | Phân tích khối lượng xử lý |
| Attempt duration | Bắt đầu attempt | Kết thúc attempt | Phân tích retry |

Một `CompletionStage` có thể được trả về ngay trong vài microsecond trong khi công việc chạy vài giây. Nếu advice ghi success ngay sau `proceed()`, log có thể chỉ xác nhận **submission thành công**, không phải **operation thành công**. Cách phù hợp là quan sát tín hiệu completion của contract hoặc đặt instrumentation ở nơi thực thi; không gọi `join()`/`get()` trong advice chỉ để chờ kết quả vì dễ phá vỡ tính bất đồng bộ.

Khi một stage timeout hoặc bị hủy, cần phân biệt **handle đã hoàn tất** với **task thực tế đã dừng và cleanup xong**. Mốc completion nào được ghi phải mô tả trung thực. Với callback và publisher lười, cũng phải hiểu vòng đời callback hoặc subscription trước khi gắn logging; không tự subscribe chỉ để kích hoạt log vì có thể làm chạy thêm công việc.

## 11. Truyền correlation context và theo dõi yêu cầu xuyên luồng

Một bản ghi outcome có thể đúng nhưng vẫn khó tìm nếu không liên kết với bản ghi của bước khác. Dùng **correlation ID** hoặc **trace ID** xuyên suốt đường xử lý:

~~~text
request received: correlation_id = C42
  -> order.place: C42
      -> inventory.reserve: C42
      -> payment.authorize: C42
  -> order.place finished: C42, outcome = success
~~~

Đây là sơ đồ ví dụ. Trong triển khai thật:

- Tạo hoặc xác thực ID ở ranh giới đầu vào; không nhận mọi giá trị client cung cấp mà không kiểm tra độ dài, ký tự và chính sách tin cậy.
- Truyền ID qua lời gọi có chủ đích; không dùng ID khách hàng làm correlation ID mặc định.
- Với thread pool hoặc callback, không giả định `ThreadLocal` tự đi theo tác vụ. Chụp **dữ liệu ngữ cảnh bất biến** rồi gắn/tháo scope ở luồng thực thi bằng try/finally.
- Xác định quan hệ giữa log, span của distributed tracing và metric. Log cung cấp sự kiện chi tiết; trace liên kết các thao tác theo thời gian; metric cho biết tỷ lệ lỗi và phân phối độ trễ. Chúng bổ trợ nhau, không phải thay thế lẫn nhau.
- Không mở một scope gắn với luồng gọi rồi giữ nguyên đến khi công việc nền hoàn tất nếu scope không được thiết kế cho vòng đời đó.

Có trace ID không có nghĩa log đủ thông tin nghiệp vụ. Trường `operation`, `outcome` và `error_code` vẫn quan trọng để query theo nghiệp vụ.

## 12. An toàn dữ liệu và cardinality

Chính sách ghi log tại boundary cần bảo vệ dữ liệu ngay từ lúc thiết kế:

**Không tự động ghi:** mật khẩu, token, authorization header, session secret, private key, thông tin thẻ thanh toán, nội dung tài liệu nhạy cảm, request/response object đầy đủ hoặc stack trace chứa giá trị cá nhân. Ngay cả `toString()` của object cũng có thể tiết lộ dữ liệu.

**Ưu tiên:** tên operation cố định, mã lỗi đã chuẩn hóa, độ trễ, trạng thái, attempt và correlation ID được tạo đúng chính sách. Với mã nghiệp vụ cần tìm kiếm, cân nhắc surrogate ID, hashing có quy tắc và kiểm soát quyền truy cập; hashing không tự bảo đảm ẩn danh.

**Cardinality:** nếu dùng `orderId`, `userId`, URL có ID, hoặc nội dung exception làm **label metric**, hệ thống metric có thể nổ số lượng time series. Tên operation và error code nên thuộc tập hữu hạn; ID có thể nằm trong log khi được phép nhưng không nên làm label thống kê phổ biến.

**Phân loại mức log:**

- `INFO`: sự kiện hoàn tất quan trọng, có giới hạn lưu lượng.
- `WARN`: từ chối hay retry cần chú ý, nhưng có thể nằm trong hoạt động dự kiến.
- `ERROR`: lỗi bất thường hoặc failure ảnh hưởng mục tiêu vận hành.

Level không đồng nhất outcome: `rejected` vì quy tắc nghiệp vụ có thể chỉ ở INFO/WARN; một operation cuối cùng thành công sau retry có thể có WARN cho từng attempt. Chính sách cần dựa trên tính chất lỗi và mục tiêu vận hành.

**Log injection:** nội dung người dùng không đáng tin có thể chứa newline và cấu trúc giả. Dùng encoder/structured logger và giới hạn kích thước thay vì ghép raw input vào log line.

## 13. Sampling, volume và khả năng vận hành

Boundary logging vẫn có thể phát lượng log rất lớn. Thiết kế cần có **ngân sách log**:

1. Luôn giữ những failure quan trọng theo chính sách giữ lại; có thể sampling các success lưu lượng cao nhưng phải biết tỷ lệ lấy mẫu.
2. Dùng metric counter cho số operation thành công/thất bại và histogram cho latency; tránh tổng hợp tỷ lệ lỗi chỉ từ log đã sampling.
3. Quyết định nơi xử lý backpressure: queue logger, giới hạn buffer, chính sách drop/fallback. Blocking logger có thể làm tăng latency của operation.
4. Đặt retention và quyền truy cập theo loại dữ liệu; kết hợp cơ chế xóa đúng hạn và kiểm soát người xem.
5. Dùng operation name ổn định để dashboard không biến động theo refactor. Version hóa event schema nếu thay đổi trường có ảnh hưởng tới downstream.
6. Cảnh báo dựa trên tỷ lệ lỗi, latency, throughput và các tín hiệu nghiệp vụ phù hợp; không tạo cảnh báo mỗi lần helper ném exception rồi đã được xử lý thành công.

**AOP ghi log giúp giảm trùng lặp code**, nhưng không làm biến mất chi phí serialization, lưu trữ hay vận hành. Ngưỡng log và sampling nên thiết kế trước khi nhân rộng instrumentation.

## 14. Ranh giới giữa log quan sát và audit nghiệp vụ

**Log vận hành** trả lời “điều gì đã xảy ra, vì sao thất bại, tốn bao lâu?”. Nó thường được đưa vào hệ thống observability, có thể sampling, xoay vòng, giữ lại theo TTL.

**Audit nghiệp vụ** trả lời “ai đã thay đổi trạng thái nào, từ đâu, vào lúc nào, dựa trên quyền nào?” và có thể có yêu cầu về tính đầy đủ, tính nhất quán, chống sửa, truy vết pháp lý.

Không nên coi một lời gọi `logger.info("approved")` từ around advice là bằng chứng chắc chắn rằng giao dịch phê duyệt đã được commit thành công. Nếu operation rollback sau khi method đã return, hoặc event phát trước durable commit, thông điệp có thể không phản ánh trạng thái tồn tại lâu dài.

Khi cần audit có bảo đảm, nên gắn cơ chế ghi audit vào ranh giới trạng thái nghiệp vụ được xác nhận và định nghĩa rõ các bảo đảm giao dịch/durable event. AOP có thể hỗ trợ bổ sung metadata, correlation ID hoặc quy tắc chung, nhưng bản thân interception không tạo ra tính nguyên tử hay bảo đảm giao dịch.

## 15. Những trường hợp dễ sai và cách sửa

### Trường hợp A: log ở mọi getter, setter, mapper

**Hiện tượng:** log tăng đột biến khi thay đổi thuật toán nội bộ; không có thông tin outcome của use case.

**Sửa:** chọn pointcut theo operation có ý nghĩa nghiệp vụ. Đặt debug/trace mức thấp chỉ ở vị trí cần chẩn đoán, với giới hạn phạm vi và thời gian.

### Trường hợp B: quanh method có retry

**Hiện tượng:** một yêu cầu cuối cùng thành công nhưng dashboard đếm nhiều business failures.

**Sửa:** phân biệt operation với attempt; ghi tên sự kiện, cấp độ và vị trí advice nhất quán với outcome cần theo dõi. Có thể log attempt riêng khi cần.

### Trường hợp C: after-returning ghi thành công cho Future

**Hiện tượng:** log success xuất hiện khi task chưa chạy hoặc sau đó thất bại.

**Sửa:** ghi `submitted` tại thời điểm return, và `completed`/`failed` tại đúng lifecycle kết quả nếu có tín hiệu phù hợp.

### Trường hợp D: Advice log hết tham số

**Hiện tượng:** thông tin cá nhân, token hoặc payload lớn xuất hiện trong log.

**Sửa:** schema với các trường cho phép, bỏ mặc định toàn bộ args/return value; redaction/encoding phù hợp, giới hạn kích thước và kiểm thử dữ liệu nhạy cảm.

### Trường hợp E: Advice làm đổi nghiệp vụ

**Hiện tượng:** logger hoặc serializer ném exception che mất lỗi gốc; callback observer đổi trạng thái trả về.

**Sửa:** tách instrumentation khỏi đường dữ liệu nghiệp vụ; quy định cụ thể phản ứng khi phát log thất bại. Nếu phải tuân thủ audit bắt buộc, mô hình bảo đảm cần thiết kế công khai thay vì âm thầm nuốt lỗi.

### Trường hợp F: nhiều Aspect trùng pointcut

**Hiện tượng:** log đôi, thứ tự không rõ, số success không khớp số yêu cầu.

**Sửa:** xác định một nơi chịu trách nhiệm event cấp operation; các Aspect khác thêm trace/metric hoặc event ở cấp khác với tên rõ ràng. Kiểm thử thứ tự bao quanh thực tế.

### Trường hợp G: tên operation động

**Hiện tượng:** mỗi đơn hàng sinh một operation name khác nhau; query và metric khó tổng hợp.

**Sửa:** giữ `operation="order.place"` ổn định; ID tài nguyên đi vào trường riêng có quy tắc bảo mật thích hợp.

## 16. Kiểm thử AOP logging theo hành vi, không theo số dòng ngẫu nhiên

Nên kiểm thử các thuộc tính có ý nghĩa:

| Kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Gọi use case thành công | Một outcome `success` cấp operation theo chính sách đã chọn |
| Helper hoặc getter được gọi | Không phát event cấp business operation ngoài chủ đích |
| Use case ném lỗi | Một outcome đúng loại; lỗi vẫn tới caller |
| Nhiều lời gọi lồng nhau | Không đếm trùng một operation; các operation độc lập được phân biệt |
| Retry hai lần rồi thành công | Một outcome cuối cấp operation; attempt được đếm riêng nếu cần |
| Kết quả dạng failure object | Không ghi success chỉ vì method return bình thường |
| CompletionStage lỗi sau return | Log completion là failure nếu observer được thiết kế cho lifecycle đó |
| Luồng executor được tái sử dụng | Correlation context không rò từ task trước sang task sau |
| Input chứa newline/token/PII | Dữ liệu nhạy cảm không bị ghi ra; giá trị không chèn thêm log giả |
| Observer/logger phát sinh lỗi | Kết quả nghiệp vụ tuân theo chính sách thất bại đã định nghĩa |
| Refactor helper | Số event nghiệp vụ ổn định nếu contract use case không đổi |

Hãy kiểm tra **schema, tên operation, outcome, lỗi và correlation**. Tránh gắn test vào chi tiết format của một logger ngẫu nhiên nếu kiến trúc có thể thay thư viện. Khi kiểm thử timing, dùng đồng hồ kiểm soát được hoặc assertion khoảng hợp lý; không dựa vào số nanosecond chính xác.

## 17. Quy trình áp dụng trong dự án

**Bước 1 — Liệt kê các operation quan trọng.** Ghi tên, actor/nguồn kích hoạt, hợp đồng trả về, trạng thái thành công/thất bại và liệu chúng có bất đồng bộ không.

**Bước 2 — Chọn join point gần ranh giới phù hợp nhất.** Đảm bảo lời gọi thực tế đi qua cơ chế AOP; dùng annotation/contract nếu giúp kiểm soát phạm vi.

**Bước 3 — Định nghĩa event schema.** Chọn tên operation cố định, outcome, duration, correlation ID, error code, level và dữ liệu an toàn; đồng thời xác định operation/attempt/step.

**Bước 4 — Viết advice bảo toàn hợp đồng.** Gọi proceed() đúng một lần; hoàn trả kết quả hoặc ném lại lỗi; đo thời gian theo vòng đời thực; không tự log args/return theo reflection một cách mù quáng.

**Bước 5 — Bổ sung quan sát có mục tiêu.** Chỉ thêm mốc ở phụ thuộc quan trọng, retry hoặc trạng thái nghiệp vụ khi có câu hỏi vận hành cần trả lời.

**Bước 6 — Kiểm thử và đo chi phí.** Xác minh không trùng, không rò dữ liệu, không làm đổi kết quả; theo dõi throughput, latency, dung lượng log, tỉ lệ sample và tác động khi logger bị nghẽn.

**Bước 7 — Duy trì chính sách khi hệ thống thay đổi.** Review annotation/pointcut trong code review; bảo vệ event schema và dashboard khỏi thay đổi tên method vô tình.

## 18. Ghi nhớ

Logging AOP chất lượng cao tập trung vào **ý nghĩa của một operation**:

- **Đúng điểm:** quan sát tại boundary có hợp đồng nghiệp vụ; không mặc định mọi method.
- **Đúng dữ liệu:** operation, outcome, duration, correlation, nguyên nhân được chuẩn hóa và thông tin được phép ghi.
- **Đúng vòng đời:** lời gọi đồng bộ, tác vụ bất đồng bộ, retry attempt và trạng thái đã commit có các mốc khác nhau.
- **Đúng tác dụng:** có thể chẩn đoán và thống kê, nhưng không nhân đôi log, tiết lộ dữ liệu, che lỗi hay làm biến dạng hành vi nghiệp vụ.

Một sự kiện `order.place failed` với correlation ID, mã lỗi rõ và duration hữu ích hơn hàng trăm dòng `enter/exit` không cho biết chuyện gì thực sự xảy ra.