# Thiết kế advice nhỏ, rõ mục đích và ít tác dụng phụ

## 1. Vì sao thiết kế advice lại quan trọng?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, *advice* là hành vi bổ sung được đưa vào một **join point** (điểm thực thi có thể can thiệp) được **pointcut** lựa chọn. Advice rất hữu ích cho các mối quan tâm cắt ngang như metrics, audit, tracing, kiểm tra chính sách hoặc dọn dẹp tài nguyên: nhiều nơi cần cùng một quy tắc nhưng mã nghiệp vụ không cần gọi lặp đi lặp lại cùng một đoạn xử lý.

Đặc điểm khiến advice hữu ích cũng làm nó dễ nguy hiểm: **mã bổ sung chạy không hiển hiện ngay tại chỗ gọi nghiệp vụ**. Một advice quá lớn, nhiều tác dụng phụ hoặc tự thay đổi kết quả có thể ảnh hưởng hàng trăm phương thức mà người bảo trì không nhận ra. Vì vậy, nguyên tắc cốt lõi là:

> **Một advice nên có một mục đích rõ, hợp đồng tác động nhỏ và phạm vi pointcut vừa đủ.** Nếu chỉ được thiết kế để quan sát, nó nên giữ nguyên kết quả, ngoại lệ và số lần thực thi nghiệp vụ.

Ví dụ, khi gọi `submitOrder()`:

- **Core business:** kiểm tra quy tắc đặt hàng, điều chỉnh trạng thái đơn hàng và trả kết quả.
- **Audit advice:** ghi nhận sự kiện “bắt đầu / hoàn tất / thất bại” bằng thông tin được phép lưu.
- **Metric advice:** ghi số lần hoàn tất và độ trễ theo nhãn ổn định.
- **Tracing advice:** gắn hoặc chuyển tiếp định danh tương quan tới hệ thống theo dõi.

Những hành vi trên có thể cùng áp dụng cho một join point nhưng **không nhất thiết nên nhét tất cả vào một advice duy nhất**. Tách nhỏ giúp đọc, thử, thay đổi và quyết định chính sách lỗi cho từng mối quan tâm mà không kéo theo phần còn lại.

## 2. Bốn ranh giới cần làm rõ trước khi viết advice

Một thiết kế dễ bảo trì bắt đầu từ những câu hỏi cụ thể, không bắt đầu bằng một hàm `around` thật dài.

| Ranh giới | Câu hỏi | Ví dụ hợp đồng |
| --- | --- | --- |
| **Điểm áp dụng** | Advice chạy ở join point nào? | Chỉ thao tác ghi đơn hàng tại ranh giới API |
| **Thời điểm** | Trước, sau thành công, sau lỗi hay bao quanh? | Audit thành công ở normal return; lỗi ở exceptional exit |
| **Dữ liệu** | Advice cần nhìn và được phép lưu điều gì? | Tên thao tác và loại kết thúc, không ghi payload khách hàng |
| **Tác động** | Advice được quyền thay đổi điều gì? | Chỉ quan sát; không sửa tham số, result hay ngoại lệ |

Một advice **không có pointcut hợp lý** sẽ không giải quyết đúng vấn đề: nếu pointcut quá rộng, nó ghi thừa hoặc làm chậm nhiều đoạn không liên quan; nếu quá hẹp, hành vi cần thiết bị thiếu. Nhưng **pointcut và advice vẫn là hai trách nhiệm riêng**. Pointcut diễn đạt “ở đâu”; advice diễn đạt “làm gì”.

Thiết kế “nhỏ” không được hiểu là chỉ vài dòng code. Một advice có thể gọi dịch vụ độc lập để thực hiện một chính sách phức tạp, miễn cho người đọc thấy **một mục đích duy nhất** và **hợp đồng rõ ràng** tại ranh giới can thiệp.

## 3. Nguyên tắc một trách nhiệm: mỗi advice trả lời một câu hỏi

Một advice có mùi thiết kế khi nó vừa ghi audit, vừa sửa đầu vào, vừa retry, vừa quản lý cache, vừa chuyển ngoại lệ, vừa đổi kết quả trả về. Các chức năng này khác nhau ở yêu cầu, rủi ro, số lần thực thi và cách xử lý thất bại.

So sánh:

| Mẫu thiết kế | Đặc điểm | Rủi ro bảo trì |
| --- | --- | --- |
| **Advice “tất cả trong một”** | Một `around` vừa kiểm quyền, ghi log, retry, cache, đo thời gian | Thứ tự phụ thuộc ngầm; khó phân biệt lỗi do phần nào |
| **Audit advice** | Chỉ ghi sự kiện trước/sau với dữ liệu tối thiểu | Kiểm thử chính sách audit riêng |
| **Metric advice** | Chỉ đo/đếm bằng nhãn có giới hạn | Có thể đo overhead riêng và thay backend riêng |
| **Authorization advice** | Chỉ áp dụng quyết định truy cập ở ranh giới đã định | Hợp đồng từ chối rõ; không che quy tắc miền |
| **Retry advice** | Chỉ quản lý số lần chuyển tiếp theo chính sách an toàn | Kiểm soát idempotency và giới hạn thử |
| **Transformation advice** | Chỉ thay kết quả theo một yêu cầu được công bố | Kiểm thử kiểu trả về và contract caller |

Không phải lúc nào cũng bắt buộc nhiều aspect: **tách về mặt trách nhiệm** mới là mục tiêu. Một engine có thể cung cấp những loại advice khác nhau trong cùng một aspect, trong khi mã triển khai vẫn được chia thành những hàm/dịch vụ có tên tốt. Ngược lại, tách thành nhiều class mà mỗi class vẫn xử lý nhiều chính sách không làm thiết kế tốt hơn.

Một kỹ thuật đặt tên hữu ích: tên advice nên chỉ ra **hành động cắt ngang** và **phạm vi** — ví dụ `recordOrderCompletion`, `countApiFailures`, `traceExternalCalls`. Tránh những tên chung như `handleEverything` hoặc `doMoreWork` khiến người đọc không thể dự đoán tác động.

## 4. Chọn loại advice ít quyền lực nhất đủ đáp ứng yêu cầu

Các loại advice có quyền can thiệp khác nhau. Dùng loại **đơn giản nhất đáp ứng yêu cầu**, thay vì luôn dùng `around` vì nó linh hoạt.

| Nhu cầu | Kiểu advice thường phù hợp | Lưu ý |
| --- | --- | --- |
| Ghi sự kiện bắt đầu | **Before** | Không có kết quả trả về |
| Chỉ ghi hoàn tất bình thường | **After returning** | Bình thường không đồng nghĩa nghiệp vụ thành công |
| Ghi ngoại lệ thoát khỏi join point | **After throwing** | Quan sát lỗi khác với nuốt hoặc đổi lỗi |
| Cleanup/ghi số liệu trên cả hai nhánh | **After / finally** | Bảo toàn nguyên nhân lỗi và phạm vi cleanup |
| Cần trực tiếp điều khiển thực thi | **Around** | Phải quản lý `proceed`, kết quả, exception và số lần gọi |

Giả sử chỉ muốn in thời điểm một phương thức hoàn tất thành công. `After returning` nói đúng mục đích và không yêu cầu ta quyết định có gọi target hay không. Nếu dùng `around`, chỉ một lỗi quên `proceed` có thể khiến nghiệp vụ **không chạy**, hoặc gọi `proceed` lần hai có thể gây **tác dụng phụ lặp**.

Tuy nhiên, **around** hoàn toàn hợp lý khi cần bao quanh lời gọi để đo thời gian chính xác qua cả hai nhánh, áp dụng caching hoặc điều khiển retry. Điều quan trọng là **thực thi đúng quyền mà hợp đồng cho phép**, không phải né tuyệt đối một loại advice.

## 5. Hợp đồng “ít tác dụng phụ” nghĩa là gì?

*Side effect* là thay đổi trạng thái quan sát được ngoài giá trị trả về thuần túy. Advice được thiết kế để ghi audit hoặc metrics **vẫn có tác dụng phụ hợp lệ** — nó ghi sự kiện hoặc cập nhật bộ đếm. “Ít tác dụng phụ” không có nghĩa “không được ghi log”; nó nghĩa là **chỉ gây đúng tác dụng phụ cần cho mục đích đã công bố, với ảnh hưởng tối thiểu lên nghiệp vụ**.

Đối với một advice chỉ quan sát, hãy dùng các bất biến làm tiêu chí thiết kế:

1. **Không thay kết quả nghiệp vụ:** caller nhận cùng giá trị và kiểu kết quả như khi không có advice.
2. **Không thay loại và ngữ nghĩa ngoại lệ:** ngoại lệ gốc được chuyển tiếp, trừ khi có chính sách biến đổi được công bố.
3. **Không tự ý đổi số lần gọi target:** một lời gọi qua aspect quan sát dẫn tới đúng một lời gọi nghiệp vụ nếu đường chạy vốn như vậy.
4. **Không sửa dữ liệu đầu vào hoặc object graph kết quả:** tránh ghi dữ liệu mutable vào chỗ chia sẻ hoặc biến đổi đối tượng theo cách caller không dự đoán.
5. **Không chèn lời gọi tốn thời gian vô hạn vào đường nóng:** hoạt động quan sát phải có chi phí và timeout hợp lý.
6. **Không lộ dữ liệu vượt mục đích:** log thông tin tối thiểu và phân quyền khi lưu trữ.

Mọi quy tắc đều có ngoại lệ theo nhu cầu hệ thống. Ví dụ authorization advice có thể cố ý từ chối truy cập, caching advice có thể bỏ gọi target, retry advice có thể gọi nhiều lần. Nhưng những khác biệt ấy cần xuất hiện trong **tên, hợp đồng, tài liệu và test**, không được ẩn sau một advice mang tên “logging”.

## 6. Quan sát dữ liệu an toàn: đầu vào, đầu ra, exception

Một advice có thể được cấp thông tin phương thức, đối số, kết quả hoặc ngoại lệ. Khả năng tiếp cận dữ liệu **không phải sự cho phép ghi mọi dữ liệu vào log**.

### 6.1. Tham số và kết quả

Không nên in `Arrays.toString(args)` hoặc serialize thẳng kết quả cho tất cả join point, đặc biệt với tài khoản, thông tin thanh toán, token, mật khẩu hoặc dữ liệu cá nhân. Thay vào đó, cân nhắc chỉ ghi:

- Tên hoặc mã thao tác đã được chuẩn hóa.
- Mã kết quả được cho phép, không phải toàn bộ response.
- Thời lượng, số đếm và trạng thái normal/exceptional completion.
- Correlation ID được tạo cho mục đích quan sát, không dùng token xác thực làm trace ID.

`toString()` của một object cũng có thể chậm, đụng dữ liệu nhạy cảm, chứa cấu trúc rất lớn, hoặc tự ném lỗi. **Không coi `toString()` là phép quan sát luôn an toàn**. Nếu advice chỉ cần biết `result == null` hoặc loại kết quả, hãy dùng kiểm tra tối thiểu thay vì dump nội dung.

### 6.2. Mutable object

Nếu method trả một `List<Order>` mutable và advice thực hiện `result.clear()`, caller sẽ thấy danh sách bị xóa dù advice không thay tham chiếu. Tương tự, advice thay đổi map đầu vào có thể khiến target xử lý dữ liệu khác. Đây là can thiệp nghiệp vụ thật, không còn là ghi nhận sự kiện.

Muốn biến đổi dữ liệu có chủ đích, cần một layer có hợp đồng riêng — thường là `around` hoặc cơ chế transformation tương ứng — và test rõ hành vi trước/sau. Advice quan sát nên coi các object được nhìn thấy là **read-only về mặt chính sách**, kể cả khi Java type chưa thật sự immutable.

### 6.3. Ngoại lệ

Advice ghi lỗi nên phân biệt **class lỗi**, nhãn xử lý và những trường có thể tiết lộ dữ liệu. Không phải message ngoại lệ nào cũng an toàn để lưu, vì nó có thể chứa email, đường dẫn nội bộ hoặc nội dung đầu vào.

Một advice `after throwing` chỉ log rồi chuyển tiếp lỗi khác với advice bắt và **nuốt** ngoại lệ. Nuốt lỗi có thể khiến caller tưởng thao tác thành công. Nếu yêu cầu là chuyển `SQLException` thành `StorageUnavailableException` (ví dụ ý niệm), đó là một chính sách thay đổi hợp đồng cần test riêng, không nên nằm ngầm trong audit advice.

## 7. Lỗi trong chính advice: fail-open, fail-closed và mức độ quan trọng

Một thách thức khó nhất là **observer tự gặp lỗi**. Ví dụ backend metrics đang quá tải, audit sink không ghi được, serializer lỗi hoặc API phát sự kiện timeout. Ta phải trả lời:

> Khi công cụ quan sát thất bại, nghiệp vụ có tiếp tục hoạt động hay cần bị từ chối?

Có ít nhất hai chính sách:

| Chính sách | Ý nghĩa | Khi cân nhắc | Rủi ro |
| --- | --- | --- | --- |
| **Fail-open** | Cho nghiệp vụ tiếp tục dù kênh quan sát lỗi | Metrics/log kỹ thuật không bắt buộc | Mất dữ liệu quan sát, cần có dấu hiệu giám sát riêng |
| **Fail-closed** | Không cho nghiệp vụ tiếp tục khi hành vi bắt buộc không hoàn tất | Yêu cầu kiểm soát hoặc audit bắt buộc theo hợp đồng | Giảm availability, lỗi hạ tầng có thể chặn giao dịch |

**Không có một lựa chọn đúng cho mọi advice.** Nếu audit là điều kiện tuân thủ bắt buộc, âm thầm bỏ qua lỗi có thể vi phạm yêu cầu. Nếu chỉ là biểu đồ latency phụ trợ, ném exception ra caller vì hệ thống metrics ngừng hoạt động có thể không phù hợp. Chính sách phải được thống nhất trước, được đặt tên và có kiểm thử mô phỏng backend lỗi.

Với advice fail-open, cũng không nên “nuốt mọi `Throwable`” vô điều kiện: nó có thể che `Error` nghiêm trọng hoặc phá tính đúng của hệ thống. Hãy giới hạn loại lỗi hạ tầng được phép xử lý, có dấu hiệu báo sự cố và tránh fallback tạo vòng đệ quy. Với fail-closed, phải làm rõ lúc nào từ chối, trả loại lỗi nào, và khi nào có khả năng rollback hoặc hậu quả giao dịch đã xảy ra.

**Thứ tự thời điểm quan trọng:** nếu audit bắt buộc phải hoàn tất trước khi giao dịch được chấp nhận, chỉ ghi ở `after returning` có thể quá muộn để đảm bảo tính nguyên tử. Khi có ràng buộc giao dịch, một cơ chế outbox hoặc đồng bộ dữ liệu được thiết kế phù hợp có thể cần thiết. Advice không tự biến hai hệ thống độc lập thành một giao dịch nguyên tử.

## 8. Ví dụ Java 17+ chạy được: tách audit và metrics

Ví dụ sau triển khai **mô hình AOP tối giản bằng JDK dynamic proxy**. Mục tiêu không phải cung cấp engine pointcut tổng quát mà để nhìn rõ thiết kế:

- `OrderCore` chỉ chứa nghiệp vụ và ném lỗi hợp đồng khi số lượng không hợp lệ.
- `AuditAdvice` chỉ ghi sự kiện bắt đầu/thành công/thất bại, không ghi input nhạy cảm hoặc sửa kết quả.
- `MetricAdvice` chỉ đếm **số lời gọi hoàn tất**, gồm thành công và thất bại, bằng `AtomicInteger`.
- Adapter `instrument()` chọn duy nhất phương thức `submit` và ghép hai advice theo thứ tự rõ ràng. `health()` không khớp nên bỏ qua hai advice.
- `callTarget()` bóc `InvocationTargetException` để caller nhìn thấy nguyên nhân nghiệp vụ gốc.

**Đây là chương trình Java độc lập**, không phải cú pháp của một engine AOP chuyên dụng. Tạo file `SmallAdviceDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public final class SmallAdviceDemo {
    interface OrderService {
        String submit(int quantity);
        String health();
    }

    static final class OrderCore implements OrderService {
        @Override
        public String submit(int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            System.out.println("BUSINESS submit");
            return "accepted:" + quantity;
        }

        @Override
        public String health() {
            return "READY";
        }
    }

    @FunctionalInterface
    interface Proceeding {
        Object proceed() throws Throwable;
    }

    static final class AuditAdvice {
        Object apply(String operation, Proceeding next) throws Throwable {
            System.out.println("AUDIT begin " + operation);
            try {
                Object result = next.proceed();
                System.out.println("AUDIT success " + operation);
                return result;
            } catch (Throwable error) {
                System.out.println("AUDIT failure " + operation + " "
                        + error.getClass().getSimpleName());
                throw error;
            }
        }
    }

    static final class MetricAdvice {
        private final AtomicInteger completed = new AtomicInteger();

        Object apply(Proceeding next) throws Throwable {
            try {
                return next.proceed();
            } finally {
                completed.incrementAndGet();
            }
        }

        int completedCalls() {
            return completed.get();
        }
    }

    static Object callTarget(OrderService target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    static OrderService instrument(OrderService target, AuditAdvice audit,
                                   MetricAdvice metrics) {
        return (OrderService) Proxy.newProxyInstance(
                OrderService.class.getClassLoader(),
                new Class<?>[] { OrderService.class },
                (proxy, method, args) -> {
                    Proceeding original = () -> callTarget(target, method, args);
                    if (!method.getName().equals("submit")) {
                        return original.proceed();
                    }
                    return metrics.apply(
                            () -> audit.apply("submit", original));
                });
    }

    public static void main(String[] args) {
        AuditAdvice audit = new AuditAdvice();
        MetricAdvice metrics = new MetricAdvice();
        OrderService service = instrument(new OrderCore(), audit, metrics);

        System.out.println("STATUS " + service.health());
        System.out.println("RESULT " + service.submit(2));
        try {
            service.submit(0);
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
        System.out.println("METRIC completed=" + metrics.completedCalls());
    }
}
~~~

Biên dịch/chạy trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 SmallAdviceDemo.java
java SmallAdviceDemo
~~~

Đầu ra đã được kiểm chứng:

~~~text
STATUS READY
AUDIT begin submit
BUSINESS submit
AUDIT success submit
RESULT accepted:2
AUDIT begin submit
AUDIT failure submit IllegalArgumentException
CALLER quantity must be positive
METRIC completed=2
~~~

### 8.1. Đọc luồng thành công

`health()` là phương thức không khớp; nó chỉ trả `READY` và **không sinh audit hoặc metrics**. Với `submit(2)`, adapter áp dụng `MetricAdvice` bao ngoài `AuditAdvice`:

~~~text
MetricAdvice.enter
  AuditAdvice.begin
    OrderCore.submit(2) -> "accepted:2"
  AuditAdvice.success
MetricAdvice.finally increments completed
Caller receives "accepted:2"
~~~

`AuditAdvice` không sửa `"accepted:2"` và `MetricAdvice` trả lại đúng kết quả của tầng trong. Kết quả caller nhận được bảo toàn. `MetricAdvice` chỉ đếm sau khi tầng bên trong kết thúc, không yêu cầu biết loại dữ liệu được trả về.

### 8.2. Đọc luồng thất bại

Với `submit(0)`, nghiệp vụ ném `IllegalArgumentException` ngay trước câu lệnh `BUSINESS submit`. `AuditAdvice` ghi loại ngoại lệ, ném lại chính đối tượng đó. `MetricAdvice` tăng bộ đếm trong `finally` và cho ngoại lệ tiếp tục đến caller. Không có `AUDIT success` hoặc `RESULT` cho lời gọi lỗi.

**Bộ đếm `completed=2` không phải số lượt thành công.** Nó đếm hai lần `submit` kết thúc (một normal, một exceptional). Nếu muốn success count và failure count riêng, hãy định nghĩa **hai metric có ý nghĩa rõ ràng** hoặc một cơ chế phân loại trạng thái, không đặt tên mập mờ `successes` cho một counter trong `finally`.

### 8.3. Giới hạn thiết kế của ví dụ

- `System.out.println` chỉ là sink minh họa, không phải hạ tầng audit sản xuất với bảo đảm lưu trữ; nếu sink lỗi, kết quả có thể bị ảnh hưởng. Phần ví dụ **không hiện thực fail-open/fail-closed**; phải quyết định chính sách trước khi dùng thực tế.
- Bộ chọn `method.getName().equals("submit")` được giữ đơn giản để dễ đọc. Khi có overload, cần lọc thêm chữ ký/annotation để không áp dụng nhầm.
- JDK proxy chỉ chặn lời gọi **qua interface proxy**. Gọi trực tiếp `new OrderCore().submit(2)` không qua advice; self-invocation trong target cũng có thể bỏ qua proxy.
- `AtomicInteger` xử lý cập nhật counter đồng thời nhưng không tự giải quyết các vấn đề chia sẻ ngữ cảnh, bảo mật và tính nguyên tử của audit.
- Hai advice đang dùng một dạng **around wrapper** để dễ minh họa hợp đồng chuyển tiếp. Trong engine AOP có các kiểu `before`, `after returning`, `after throwing` và `finally` riêng, ta có thể phân chia vị trí thực thi thích hợp với mục đích của từng advice.

## 9. Tách điểm quan sát khỏi cơ chế ghi sự kiện

Một advice được viết tốt có thể đóng vai trò **adapter**: đọc context tối thiểu và gọi một dịch vụ chuyên trách. Ví dụ, advice audit không cần biết logic gửi HTTP, format JSON, vòng đời connection, retry của message broker hoặc nơi lưu trữ. Những chi tiết đó thuộc về **audit sink/transport**; pointcut và advice chỉ quyết định **khi nào phát sự kiện và dữ liệu nào cần phát**.

Sơ đồ:

~~~text
selected join point
      |
      v
  AuditAdvice
      |
      +--> AuditEvent {operation, outcome, correlationId}
                   |
                   v
              AuditSink
                |
         +------+------+
         |             |
      Storage       Queue/Stream
~~~

Sơ đồ này không phải lời khuyên phải dùng queue trong mọi tình huống. Điểm mấu chốt là **phân tách việc quyết định sự kiện với cách ghi nó**. Nếu audit có yêu cầu durability hoặc tính nhất quán với giao dịch, sink và cơ chế bảo đảm cần được lựa chọn theo yêu cầu; đưa event vào queue không tự động bảo đảm “chắc chắn không mất dữ liệu”.

Các interface nhỏ thường dễ fake trong kiểm thử:

~~~java
interface AuditSink {
    void record(AuditEvent event);
}

record AuditEvent(String operation, String outcome) {}
~~~

Đây là **đoạn minh họa hợp đồng**, không phải chương trình chạy riêng. Advice có thể cung cấp một `AuditEvent` nhỏ, còn sink giả trong unit test ghi nhận đúng sự kiện và mô phỏng lỗi. Không cần mock cả engine AOP để kiểm tra cách serialize hoặc quyết định lưu trữ.

## 10. Thứ tự advice và các tác dụng phụ gián tiếp

Hai advice đều nhỏ nhưng kết hợp sai thứ tự vẫn có thể gây hành vi không mong đợi. Giả sử có audit, authorization, retry và metrics:

~~~text
Timing
  Audit
    Authorization
      Retry
        Business
~~~

Nếu authorization từ chối trước khi business chạy, audit nằm ngoài authorization có thể thấy sự kiện bị từ chối; audit nằm phía trong authorization có thể **không hề chạy**. Nếu retry bên trong metrics, một metric có thể bao toàn bộ các lần thử; nếu metrics bên trong retry, mỗi lần thử có thể được đo riêng. Tên metric phải phản ánh thứ nó thực sự đếm.

Không có một thứ tự “chuẩn” cho mọi ứng dụng. Hãy mô tả trước:

1. Ai được phép chặn target?
2. Ai cần thấy cả thất bại do authorization?
3. Số lần gọi target có thay đổi khi retry không?
4. Advice nào bắt đầu và kết thúc phép đo?
5. Khi một advice ném lỗi, những tầng phía ngoài sẽ thấy nó dưới dạng gì?
6. Một advice bên trong có thay đổi kết quả trước khi advice ngoài nhìn thấy không?

**Precedence thuộc hợp đồng AOP cụ thể**, không được đoán từ tên file, thứ tự method hay thứ tự khai báo class. Viết integration test với thứ tự đã chọn thay vì chỉ unit test riêng từng advice.

### 10.1. Phân biệt lỗi của target và lỗi của advice

Giả sử after-returning advice tự ném `IllegalStateException` trong lúc serialize kết quả. Target có thể đã hoàn tất bình thường, nhưng một wrapper ngoài có thể quan sát **exceptional completion**. Nếu nó ghi “nghiệp vụ thất bại” một cách máy móc, metric sẽ sai.

Cần phân biệt ít nhất ba nguồn: lỗi nghiệp vụ, lỗi chính sách chủ động từ chối, và lỗi hạ tầng do chính advice. Đừng biến mọi exception trong chuỗi advice thành cùng một nhãn “business_failure”.

### 10.2. Tránh recursion khi advice ghi log

Nếu pointcut chọn mọi lời gọi dịch vụ và audit sink cũng sử dụng một dịch vụ nằm trong tập ấy, một sự kiện audit có thể kích hoạt advice audit lần nữa, rồi tiếp tục vô hạn. Cách giảm rủi ro:

- Loại trừ lớp/hợp đồng của logging hoặc audit sink khỏi pointcut.
- Sử dụng một ranh giới kỹ thuật rõ ràng giữa phần quan sát và phần phát sự kiện.
- Nếu cần chặn reentrancy, quản lý guard theo phạm vi lời gọi, cleanup trong `finally`, và kiểm thử lồng nhau.

Không dùng biến `static boolean` toàn cục làm guard ngây thơ: nó có thể chặn nhầm giữa các thread, không xử lý lồng nhau và dễ bị giữ lại sau ngoại lệ.

## 11. Trạng thái dùng chung và thread-safety

Một advice có thể dùng lại qua hàng nghìn lời gọi đồng thời. Điều đó khiến các field mutable đáng cân nhắc:

- **Không lưu dữ liệu riêng của mỗi lời gọi trong field của singleton advice** nếu không có cơ chế cách ly. Ví dụ field `currentUserId` có thể bị thread khác ghi đè.
- **Cấu hình bất biến** như tên service hoặc policy id thường an toàn hơn khi được khởi tạo một lần.
- **Bộ đếm chung** có thể dùng `AtomicInteger`, `AtomicLong`, `LongAdder` hoặc hệ metrics tùy yêu cầu độ chính xác/tải.
- **Ngữ cảnh riêng của request** có thể được cung cấp qua đối số advice, ngữ cảnh do engine quản lý hoặc cơ chế propagation thích hợp; không tự giả định `ThreadLocal` đi theo `CompletableFuture` giữa thread.

Trong ví dụ, `AuditAdvice` không giữ state theo lời gọi. `MetricAdvice` chỉ có `AtomicInteger` chung, phù hợp cho minh họa và các cập nhật đồng thời đơn giản. Với hệ thống thực, nên đo overhead và tránh nhãn metric có độ phân biệt quá lớn như mọi mã đơn hàng/user ID, vì chúng có thể làm nổ cardinality và bộ nhớ.

## 12. Vấn đề bất đồng bộ và kết quả trả về

Một phương thức `CompletableFuture<Result> start()` có thể trả Future ngay trong khi công việc bên trong chưa xong. Advice `after returning` quan sát normal return của **method**, không nhất thiết quan sát **completion của task**. Nếu audit chỉ đếm “đã nhận yêu cầu”, đó có thể là điểm phù hợp. Nếu muốn đếm “đơn hàng cuối cùng hoàn tất thành công”, phải quan sát completion của Future hoặc sự kiện nghiệp vụ tương ứng.

Không nên bắt mọi lời gọi bất đồng bộ bằng cách chặn thread hoặc gọi `join()` trong advice chỉ để lấy kết quả: nó có thể thay đổi latency, deadlock, điều kiện timeout và xử lý ngoại lệ. Thay vào đó, dùng callback hoặc instrumentation tương ứng khi cần, với hợp đồng xử lý cancellation và exceptional completion.

Một lời khuyên thực tế: **đặt tên metric/event theo thời điểm thật được đo**. `requestAccepted` khác `taskCompleted`; `methodReturnedNormally` khác `businessSucceeded`. Đặt tên đúng giúp tránh lẫn lộn ngay cả khi logic advice nhỏ.

## 13. Khả năng can thiệp của công cụ là một phần hợp đồng

Advice tốt nhưng chạy không đúng nơi vẫn tạo hệ thống khó dự đoán. Với AOP, phải xác nhận kỹ thuật được dùng có thể quan sát loại join point đã chọn:

| Cơ chế/đường gọi | Điều có thể khác nhau |
| --- | --- |
| Proxy dựa trên interface | Thường chỉ thấy lời gọi qua interface proxy |
| Proxy cần override method | Có hạn chế với `final`/`private`, phụ thuộc kỹ thuật |
| Bytecode weaving | Có thể chèn sâu hơn nếu engine hỗ trợ loại điểm và lớp được weaving |
| Self-invocation `this.method()` | Có thể bypass proxy khi gọi nội bộ |
| Constructor, field access, exception handler | Không phải engine nào cũng hỗ trợ những join point này |
| Tác vụ bất đồng bộ | Không đảm bảo tự truyền ngữ cảnh theo thread/task |
| Method call và method execution | Có thể là hai join point khác nhau với phạm vi khác nhau |

Không nên khẳng định “đã khai báo pointcut là chắc chắn áp dụng lên mọi phương thức” hoặc “mọi engine đều có chung cú pháp advice”. Hãy kiểm thử **đường gọi thực** qua ranh giới proxy/weaving và các trường hợp không khớp. Điều này quan trọng khi dùng advice để kiểm quyền hoặc audit bắt buộc, vì một đường bypass có thể làm mất chính sách bảo vệ.

## 14. Quy trình refactor một advice quá lớn

Khi thấy một advice dài và có nhiều mối quan tâm, có thể cải tiến theo trình tự:

1. **Liệt kê toàn bộ side effect hiện có:** gọi logger, ghi DB, sửa input, thay output, retry, chuyển exception, đo thời gian, cập nhật cache.
2. **Vẽ thứ tự hành vi hiện tại:** trước target, sau normal return, sau exception, trong finally. Ghi nhận số lần `proceed` và điều kiện target bị bỏ qua.
3. **Tách chính sách theo mục tiêu:** audit, metrics, authorization, retry, transformation. Đặt tên rõ các hợp đồng.
4. **Di chuyển logic hạ tầng sang dịch vụ riêng:** ví dụ tách serialization và transport ra khỏi advice audit.
5. **Quy định chính sách thất bại cho từng phần:** audit bắt buộc khác metrics phụ trợ.
6. **Chọn loại advice với quyền kiểm soát tối thiểu:** không giữ mọi thứ trong một `around` nếu có lựa chọn đơn giản hơn.
7. **Cố định precedence của các thành phần** và chạy các ca lỗi/return/cancellation.
8. **So sánh hành vi trước và sau refactor:** giá trị trả, loại exception, số lần target chạy, sự kiện audit, metric và thời lượng.
9. **Kiểm thử đường không đi qua advice:** gọi trực tiếp target, self-invocation, overload và tác vụ bất đồng bộ.
10. **Đo overhead** trên tải đại diện, không chỉ kiểm tra tính đúng trong unit test.

Refactor đúng không nhất thiết làm tổng số dòng ít hơn. Mục tiêu là **giảm coupling và rủi ro**, giúp thay đổi chính sách logging không làm thay đổi retry hoặc hợp đồng của API nghiệp vụ.

## 15. Bảng kiểm thử cho một advice nhỏ và an toàn

| Ca thử | Mục đích | Kỳ vọng |
| --- | --- | --- |
| Lời gọi được chọn, return bình thường | Giữ kết quả | Caller nhận kết quả gốc |
| Lời gọi được chọn, ném ngoại lệ | Giữ lỗi | Caller nhận cùng nguyên nhân/loại lỗi theo hợp đồng |
| Điểm không được chọn | Kiểm pointcut | Không sinh tác dụng phụ của advice |
| Lời gọi được chọn lần thứ hai | Số lần chạy | Không nhân đôi target ngoài chính sách |
| Kết quả `null` | Quan sát an toàn | Không tự phát sinh `NullPointerException` |
| Method `void` hoặc primitive | Đúng loại dữ liệu | Không ép kiểu sai |
| Audit sink lỗi | Chính sách lỗi | Fail-open/closed theo hợp đồng, cảnh báo phù hợp |
| Hai advice cùng áp dụng | Kiểm thứ tự | Event và metric đúng phạm vi |
| Lời gọi đồng thời | Trạng thái chia sẻ | Không race hoặc rò dữ liệu giữa các lần gọi |
| Trường hợp `CompletableFuture` | Phân biệt thời điểm | Không gọi method return là task completion |
| Gọi trực tiếp target | Kiểm interception | Không giả định advice trên proxy tự chạy |
| Điểm lặp/đệ quy logging | Kiểm reentrancy | Không tạo chuỗi gọi vô hạn |

**Đừng chỉ gọi thẳng hàm advice trong unit test.** Cách ấy xác minh thuật toán advice nhưng không xác minh pointcut, weaving, proxy và thứ tự thực tế. Cần ít nhất một integration test đi qua chính đường can thiệp của ứng dụng.

Một tiêu chí rất hữu ích là **behavior-preserving test** cho advice quan sát:

~~~text
runWithoutAdvice(input) -> (result, exceptionType, businessCallCount)
runWithAdvice(input)    -> (result, exceptionType, businessCallCount)

Kỳ vọng:
  result và exceptionType tương đương theo hợp đồng
  businessCallCount không tăng ngoài ý định
  chỉ các quan sát được cho phép xuất hiện thêm
~~~

Đây là pseudocode mô tả test, không phải mã có thể chạy riêng. Nếu advice có chủ đích thay đổi hành vi, hãy thay các assertion tương ứng bằng **hợp đồng chuyển đổi đã công bố**, thay vì lặng lẽ bỏ kiểm thử.

## 16. Lỗi thiết kế thường gặp

1. **Một advice quản mọi trách nhiệm:** vừa audit, caching, retry, auth, sửa kết quả và chuyển ngoại lệ; khó cô lập lỗi và phụ thuộc ngầm.
2. **Dùng `around` dù chỉ cần quan sát một thời điểm:** mở rộng quyền kiểm soát luồng không cần thiết.
3. **Quên `proceed` hoặc gọi hai lần:** bỏ thực thi nghiệp vụ hoặc lặp lại tác dụng phụ.
4. **Ghi log nguyên payload hoặc exception message nhạy cảm:** rủi ro bảo mật và chi phí lớn.
5. **Sửa result/args mutable dù advice được mô tả “chỉ quan sát”:** caller và target nhận dữ liệu ngoài hợp đồng.
6. **Nuốt mọi lỗi của logger:** có thể mất audit bắt buộc hoặc che lỗi hạ tầng nghiêm trọng.
7. **Để lỗi metrics tự ném phá kết quả nghiệp vụ:** nếu chính sách định nghĩa metrics fail-open, hành vi này sai hợp đồng.
8. **Bộ đếm không thread-safe trong advice dùng chung:** kết quả không ổn định dưới tải đồng thời.
9. **Không kiểm tra precedence:** audit có thể bỏ lỡ từ chối auth; metrics có thể đo sai vùng hoặc đếm sai retry.
10. **Không loại trừ logger khỏi pointcut:** tạo reentrancy và vòng gọi vô hạn.
11. **Coi normal return là thành công nghiệp vụ:** `Result.failure` hoặc `false` có thể là kết quả bình thường.
12. **Cho rằng proxy nhìn thấy mọi lời gọi:** self-invocation, gọi target trực tiếp và các loại join point chưa hỗ trợ có thể bypass.
13. **Thêm network call chậm vào mọi điểm nóng:** tăng tail latency dù logic nghiệp vụ không thay đổi.
14. **Giấu bất biến nghiệp vụ trong advice kỹ thuật:** khiến người đọc code miền không thấy điều kiện quan trọng và việc bypass trở nên nguy hiểm.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Advice ghi log có thể vẫn có side effect không?  
**Đáp án:** Có. Nó ghi dữ liệu vào một nơi khác; mục tiêu là side effect **được cho phép, tối thiểu và dự đoán được**, không phải tuyệt đối không có side effect.

**Câu 2.** Vì sao metrics và audit có thể nên là hai advice tách biệt?  
**Đáp án:** Chúng có mục đích, dữ liệu, hạ tầng và chính sách xử lý lỗi khác nhau; tách trách nhiệm giúp kiểm thử và thay đổi độc lập.

**Câu 3.** Nếu audit ghi lỗi và để exception từ logger thay exception nghiệp vụ, có phải advice “chỉ quan sát” đã bảo toàn hợp đồng không?  
**Đáp án:** Không. Caller có thể nhìn thấy loại lỗi khác; phải quyết định fail-open/fail-closed và kiểm thử.

**Câu 4.** `MetricAdvice` tăng `completed` trong `finally`. Có thể gọi đây là số giao dịch thành công không?  
**Đáp án:** Không; bộ đếm bao gồm cả normal và exceptional completion trong phạm vi được bao.

**Câu 5.** Vì sao cần test `health()` không khớp pointcut?  
**Đáp án:** Kiểm thử các trường hợp **không được chọn** giúp phát hiện overmatching, tránh advice chạy thừa.

**Câu 6.** Nếu một advice cần retry `submitOrder()`, giữ một lượt `proceed` có phải hợp đồng phù hợp không?  
**Đáp án:** Retry có thể gọi nhiều lần có chủ đích; vì vậy phải xác định số lần tối đa, lỗi được phép retry, và bảo vệ idempotency/tác dụng phụ của nghiệp vụ.

**Câu 7.** Có thể dùng một after-returning của method trả Future để kết luận task thành công không?  
**Đáp án:** Không. Nó có thể chỉ cho biết method đã trả Future bình thường; task có thể chưa hoàn tất.

## 18. Tổng kết

Một **advice tốt không chỉ “chạy đúng thời điểm” mà còn “chỉ làm đúng điều được giao”**. Hãy giới hạn mỗi advice ở một mục đích rõ, chọn loại advice ít quyền lực nhất phù hợp, thiết kế dữ liệu quan sát an toàn, và quy định riêng chính sách khi chính advice gặp lỗi. Với advice chỉ quan sát, ưu tiên **giữ nguyên giá trị trả về, ngoại lệ và số lần thực thi target**; những thay đổi có chủ đích phải là hợp đồng công khai có kiểm thử. Cuối cùng, kiểm tra thứ tự nhiều advice, trạng thái chia sẻ, phạm vi proxy/weaving và đường bất đồng bộ để các hành vi cắt ngang thực sự nâng cao tính bảo trì thay vì tạo tác dụng phụ khó truy vết.