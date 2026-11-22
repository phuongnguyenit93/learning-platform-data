# Tách trích xuất ngữ cảnh khỏi xử lý nghiệp vụ của aspect trong AOP

> **Mục tiêu:** Thiết kế advice theo hướng tách biệt **cách thu thập, chuẩn hóa và kiểm tra dữ liệu tại join point** với **quy tắc xử lý mà aspect thực hiện trên dữ liệu đó**. Người học cần biết ranh giới của join point context, cách tạo bản chụp dữ liệu an toàn, cách triển khai một tầng trích xuất độc lập có thể kiểm thử, cách advice phối hợp trước/sau/ngoại lệ và những giới hạn về weaving, hiệu năng, riêng tư, trạng thái đồng thời.

## 1. Vấn đề: một advice làm quá nhiều việc

Giả sử có một aspect quan sát hoạt động thanh toán. Tại mỗi lời gọi, advice cần xác định tên phương thức, đọc đối số, che dữ liệu tài khoản, kiểm tra có phải thao tác đáng theo dõi không, tạo mã sự kiện, ghi log và xử lý lỗi. Cách viết “mọi thứ trong một advice” dễ tạo đoạn mã kiểu sau:

~~~text
around selectedPaymentOperation:
    đọc chữ ký
    đọc đối số
    tìm tên tài khoản và số tiền
    chuyển đổi / che các giá trị nhạy cảm
    quyết định loại sự kiện cần ghi
    khởi tạo logger, formatter, metrics
    ghi lời gọi bắt đầu
    try:
        kết quả = proceed()
        đọc kết quả để quyết định trạng thái
        ghi lời gọi hoàn tất
        return kết quả
    catch error:
        đọc ngoại lệ
        ghi lỗi
        throw error
~~~

Đây là **pseudocode độc lập công cụ**, không phải cú pháp của một ngôn ngữ aspect cụ thể.

Đoạn mã trên trộn ít nhất ba trách nhiệm:

1. **Đọc và diễn giải join point:** nơi lấy chữ ký, target, đối số, metadata, kết quả và lỗi.
2. **Áp dụng quy tắc của mối quan tâm xuyên suốt:** sự kiện nào được ghi, ở mức nào, đếm như thế nào, xử lý loại lỗi nào.
3. **Điều phối luồng thực thi:** gọi tiếp hành vi gốc, bảo toàn return value/exception, chạy xử lý trước/sau đúng lúc.

Sự trộn lẫn gây khó kiểm thử, khó thay công cụ AOP và có thể vô tình biến việc đọc ngữ cảnh thành một thao tác nghiệp vụ nguy hiểm. Một thiết kế vững hơn tách những phần này thành các đơn vị với giao diện và trách nhiệm rõ ràng.

**Ý chính:** advice là **điểm phối hợp**; extractor là **bộ chuyển đổi ngữ cảnh**; policy của aspect là **bộ quyết định và xử lý mối quan tâm xuyên suốt**. Không nên để mọi policy phải biết trực tiếp đối tượng join point đặc thù của một cơ chế weaving.

## 2. Hiểu đúng “xử lý nghiệp vụ của aspect”

Trong bài này, cụm **“xử lý nghiệp vụ của aspect”** không có nghĩa copy logic thanh toán, đặt hàng hay tính phí từ ứng dụng vào aspect. Nó chỉ **quy tắc của mối quan tâm mà aspect đang đảm nhận**.

Ví dụ với aspect quan sát:

- Trích xuất ngữ cảnh: xác định `PaymentApi.pay(String,int)`, tên lớp đích, giá trị amount được phép dùng, loại kết thúc.
- Quy tắc aspect: với thao tác thanh toán, ghi một sự kiện `STARTED` và một sự kiện `FINISHED`; chỉ lưu tên ngoại lệ, không lưu message nhạy cảm.
- Nghiệp vụ gốc: quyết định việc thanh toán hợp lệ hay không, tạo kết quả, lưu trạng thái, gọi hệ thống bên ngoài.

Ba nhóm này khác nhau.

Một aspect kiểm toán không nên tự quyết định “thanh toán thành công” chỉ vì method trả về bình thường, nếu phương thức trả về một đối tượng nghiệp vụ biểu thị thất bại. Một aspect đo thời gian không nên mở/đóng tài nguyên nghiệp vụ mà nó không sở hữu.

**Mục đích tách lớp không phải chuyển nghiệp vụ gốc vào aspect, mà là tránh để logic của aspect gắn chặt với cách lấy dữ liệu từ một join point cụ thể.**

## 3. Cấu trúc khuyến nghị: adapter → extractor → context → policy

Một mô hình kiến trúc khái niệm:

~~~text
                      Join point được chọn
                               |
                               v
                    +----------------------+
                    | Advice / Adapter     |
                    | before/around/after  |
                    +----------------------+
                      |               ^
                      v               |
               +--------------+       | kết quả/ngoại lệ
               | Context      |       | của phần tiếp tục
               | Extractor    |       |
               +--------------+       |
                      |               |
                      v               |
               +--------------+       |
               | Context      |       |
               | Snapshot     |       |
               +--------------+       |
                      |               |
                      v               |
               +--------------+       |
               | Aspect       |       |
               | Policy       |       |
               +--------------+       |
                      |               |
                      v               |
               +--------------+       |
               | Event Sink / |       |
               | Observer     |       |
               +--------------+       |
                                      |
                     proceed / next --+
                                      |
                               Phần gốc
~~~

Sơ đồ chỉ minh họa **các trách nhiệm**; thứ tự gọi thực tế phụ thuộc loại advice và thời điểm lấy dữ liệu. Nếu policy cần biết kết quả/ngoại lệ, advice có thể phát sự kiện sau khi `proceed` trả về hoặc ném lỗi.

### 3.1. Advice/adapter làm gì?

- Nhận quyền điều khiển tại join point do pointcut chọn.
- Lấy dữ liệu được mô hình AOP cung cấp và chuyển cho extractor.
- Gọi policy ở mốc phù hợp: trước, sau thành công, sau lỗi hoặc finally.
- Với around advice, quyết định tiếp tục bằng `proceed` hoặc cơ chế tương đương **theo hợp đồng đã định**.
- Bảo toàn kết quả và ngoại lệ gốc nếu aspect chỉ có chức năng quan sát.
- Giữ phần phối hợp ngắn, không thực hiện parse/format phức tạp trong thân advice.

### 3.2. Context extractor làm gì?

- Nhận dữ liệu thô có cấu trúc từ join point.
- Chỉ lấy những trường được phép/được yêu cầu.
- Chuẩn hóa tên hoạt động, chữ ký, kiểu và giá trị cho mục tiêu quan sát.
- Che hoặc loại thông tin nhạy cảm.
- Tạo một **context snapshot** không phụ thuộc trực tiếp vào API của công cụ AOP.
- Có thể trả lỗi/thiếu dữ liệu theo hợp đồng rõ, không tự làm thay đổi nghiệp vụ gốc.

### 3.3. Aspect policy làm gì?

- Nhận context theo một schema ổn định.
- Áp dụng các quy tắc của mối quan tâm xuyên suốt: ghi loại sự kiện nào, tạo metric nào, phân loại thành công/thất bại kỹ thuật ra sao.
- Gửi sự kiện tới sink/logger/collector qua giao diện riêng.
- Không cần dùng `Method`, `Field`, `proceed` hoặc đối tượng join point cụ thể nếu policy không có nhu cầu đó.

### 3.4. Context snapshot là gì?

Một **bản chụp nhỏ** mô tả một lần quan sát: operation, loại điểm, lớp đích, các trường an toàn, correlation ID nếu có, timestamp nếu cần. Nó không nhất thiết là “bản sao toàn bộ trạng thái ứng dụng”.

Nên ưu tiên cấu trúc **bất biến** để dễ truyền giữa các bước và tránh một policy vô tình sửa dữ liệu mà policy khác đang sử dụng.

## 4. Điểm can thiệp có những dữ liệu gì?

Không phải join point nào cũng cung cấp các trường giống nhau.

| Nhóm dữ liệu | Ví dụ | Lưu ý khi tách extractor |
|---|---|---|
| **Loại join point** | Method call, method execution, constructor execution | Phụ thuộc join point model |
| **Signature** | Tên, declaring type, parameter types | Thường là thông tin cấu trúc |
| **Metadata khai báo** | Modifier, annotation nếu truy cập được | Nguồn interface/implementation có thể khác |
| **Đối tượng liên quan** | Target, receiver, `this` | Có thể khác nhau trong proxy và các mô hình AOP |
| **Đối số runtime** | Mã đơn hàng, số lượng, cờ ưu tiên | Thay đổi mỗi lần gọi, có thể nhạy cảm |
| **Kết quả** | Giá trị trả về khi hoàn tất bình thường | Chưa có trước khi phần gốc chạy |
| **Ngoại lệ** | Lỗi đi ra khỏi ranh giới quan sát | Lỗi nội bộ đã được bắt có thể không xuất hiện |
| **Source location** | File, dòng mã nguồn nếu cung cấp | Không chắc có hoặc ổn định |
| **Ngữ cảnh liên kết** | Correlation ID, thông tin theo tác vụ/luồng | Phải xác định nguồn và quy tắc truyền |

**Không được tự giả định extractor có thể đọc mọi trường ở mọi loại advice.** Advice chạy trước không biết trước kết quả. Method execution và method call có ranh giới khác; một công cụ chỉ dùng proxy interface không có mọi join point của constructor hay field access.

Một extractor tốt có **hợp đồng đầu vào rõ ràng**: những dữ liệu nào có, những dữ liệu nào có thể thiếu, và thiếu thì làm gì.

## 5. Phân biệt dữ liệu tĩnh và dữ liệu của mỗi lần gọi

Với phương thức Java:

~~~java
String pay(String accountId, int amount);
~~~

*Đây là khai báo minh họa, không phải chương trình độc lập.*

**Thông tin cấu trúc** thường có thể dùng lại:

~~~text
declaringType = PaymentApi
memberName    = pay
parameterType = [String, int]
returnType    = String
~~~

**Thông tin động** thay đổi giữa các lần:

~~~text
Lần 1: accountId="acct-1", amount=120
Lần 2: accountId="acct-2", amount=0
~~~

Không nên cache **giá trị đối số** theo chữ ký phương thức. Có thể cache **cách trình bày chữ ký**, khi khóa cache và vòng đời lớp phù hợp, nhưng một context snapshot của mỗi invocation nên được tạo theo dữ liệu của chính lần đó.

Một policy quan sát cần thông tin cấp hoạt động (operation name) có thể không cần lưu đối số. Giới hạn thông tin ở ngay tầng extractor làm giảm rủi ro rò rỉ và chi phí xử lý.

## 6. Thiết kế context DTO có hợp đồng rõ

Trong Java 17, **record** phù hợp với nhiều bản chụp dữ liệu nhỏ, chẳng hạn:

~~~java
record InvocationSnapshot(
        String operation,
        String targetType,
        java.util.List<String> safeArguments
) {
    InvocationSnapshot {
        safeArguments = java.util.List.copyOf(safeArguments);
    }
}
~~~

Đây là **mảnh mã Java minh họa**, có thể đặt bên trong một class/file Java phù hợp.

Ưu điểm:

- **Tên trường mang ý nghĩa cụ thể:** operation, targetType, safeArguments.
- **Chỉ lưu thông tin tối thiểu:** không lưu toàn bộ join point/proxy/target.
- **Bất biến theo bề mặt API:** record không cho thay các thành phần sau khi khởi tạo; `List.copyOf` tạo danh sách không cho sửa trực tiếp.
- **Không gắn với công cụ AOP:** policy có thể được unit test bằng cách tự tạo record.

**Cẩn thận về “deep immutability”:** record chỉ giữ reference bất biến. Nếu một trường tham chiếu tới đối tượng mutable, nội dung đối tượng đó vẫn có thể bị thay đổi. Vì vậy ưu tiên primitive, `String`, enum, những record bất biến khác và bản sao an toàn của collection.

Không nên đặt trực tiếp một `Object[] args` mutable vào DTO chỉ vì nó sẵn có. Array có thể bị sửa; các object bên trong còn có thể mang dữ liệu nhạy cảm hoặc trạng thái biến đổi sau khi advice kết thúc.

## 7. Extractor nên nhận gì và trả gì?

Có hai hướng thiết kế thường thấy.

### 7.1. Extractor nhận đối tượng join point thô

~~~text
extract(RawJoinPoint) -> InvocationSnapshot
~~~

Ưu điểm: adapter ít dòng. Nhược điểm: extractor bị gắn với API AOP cụ thể, khó kiểm thử độc lập hoặc chuyển sang cơ chế weaving khác.

### 7.2. Adapter chuyển dữ liệu sang mô hình đầu vào trung lập

~~~text
Advice đọc:
    kind, memberDescriptor, target, arguments

ContextExtractor.extract:
    (kind, memberDescriptor, targetInfo, arguments)
        -> InvocationSnapshot
~~~

Ưu điểm: extractor ít phụ thuộc cơ chế AOP; kiểm thử có thể tự tạo dữ liệu đầu vào. Nhược điểm: adapter phải ánh xạ dữ liệu chính xác, không được làm mất khác biệt quan trọng giữa method call và method execution.

Không có một lựa chọn tốt cho mọi trường hợp. Một cách cân bằng:

- **Adapter** chịu trách nhiệm phụ thuộc vào công cụ và thu thập các trường đã được cung cấp.
- **Extractor** chịu trách nhiệm **biến đổi/kiểm tra/chọn dữ liệu** theo hợp đồng.
- **Policy** chỉ biết mô hình trung lập và quy tắc của aspect.

Nếu extractor cần khả năng đặc thù như metadata annotation, có thể đưa thông tin ấy qua một descriptor trung lập thay vì truyền toàn bộ đối tượng runtime đặc thù vào policy.

## 8. Interface của các trách nhiệm nên được phân định thế nào?

Pseudocode độc lập công cụ:

~~~text
interface ContextExtractor:
    extract(rawMetadata, runtimeArguments) -> ContextSnapshot

interface AspectPolicy:
    before(snapshot)
    completed(snapshot, completion)

interface EventSink:
    emit(event)

around selectedJoinPoint:
    snapshot = extractor.extract(joinPoint.metadata, joinPoint.arguments)
    policy.before(snapshot)
    try:
        result = proceed()
        policy.completed(snapshot, NormalCompletion)
        return result
    catch error:
        policy.completed(snapshot, ExceptionalCompletion(typeOf(error)))
        throw error
~~~

Phần trên minh họa trách nhiệm. **Không nên triển khai nguyên xi** nếu cơ chế AOP có cách xử lý lỗi, outcome, invocation hoặc return/throw khác; cần tuân thủ hợp đồng của công cụ.

Một extractor **không nên tự gọi `proceed`**. Nếu có `proceed` bên trong extractor, tầng chuyển đổi dữ liệu đã nắm quyền điều khiển nghiệp vụ; việc test hay dùng lại trở nên khó và có thể làm phần gốc chạy nhầm số lần.

Một policy quan sát thông thường cũng **không nên gọi trực tiếp phương thức đích bằng reflection**. Những thao tác đó thuộc vòng đời tiếp tục của adapter/around advice, không phải trách nhiệm quyết định nội dung log.

## 9. Ví dụ Java 17 đầy đủ: advice adapter, extractor và policy độc lập

Để học cách tách ba trách nhiệm, ví dụ dưới đây dùng **Java Dynamic Proxy** như một **ranh giới can thiệp minh họa**. Nó không tự weaving mọi join point và không đại diện cho đầy đủ ngữ nghĩa của một công cụ AOP bất kỳ.

Thiết kế:

- `InvocationSnapshot` là DTO bất biến chỉ chứa thông tin an toàn.
- `ContextExtractor` biến `Method`, target và đối số thành snapshot.
- `AuditPolicy` chỉ nhận snapshot và kết quả hoàn tất, không biết reflection/proxy.
- `AdviceBridge` là adapter phối hợp, chuyển lời gọi tới nghiệp vụ và bảo toàn kết quả/ngoại lệ gốc trong các đường chạy minh họa.
- `PaymentService` là nghiệp vụ thực tế; nó không biết aspect.

Lưu tệp **`SeparatedAdviceDemo.java`**:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class SeparatedAdviceDemo {
    interface PaymentApi {
        String pay(String accountId, int amount);
        String status();
    }

    static final class PaymentService implements PaymentApi {
        @Override
        public String pay(String accountId, int amount) {
            System.out.println("[business] pay amount=" + amount);
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            return "ok-" + amount;
        }

        @Override
        public String status() {
            System.out.println("[business] status");
            return "READY";
        }
    }

    record InvocationSnapshot(
            String operation,
            String targetType,
            List<String> safeArguments
    ) {
        InvocationSnapshot {
            safeArguments = List.copyOf(safeArguments);
        }
    }

    enum Completion {
        RETURNED,
        THREW
    }

    static final class ContextExtractor {
        InvocationSnapshot extract(
                Method method, Object target, Object[] arguments) {
            List<String> safe = new ArrayList<>();

            // Chỉ công khai trường được phép trong hợp đồng.
            if (method.getName().equals("pay")
                    && method.getParameterCount() == 2
                    && arguments != null && arguments.length == 2) {
                safe.add("account=***");
                safe.add("amount=" + arguments[1]);
            } else if (arguments != null) {
                for (int i = 0; i < arguments.length; i++) {
                    safe.add("arg" + i + "=<hidden>");
                }
            }

            return new InvocationSnapshot(
                    method.getDeclaringClass().getSimpleName()
                            + "." + method.getName(),
                    target.getClass().getSimpleName(),
                    safe
            );
        }
    }

    static final class AuditPolicy {
        void started(InvocationSnapshot context) {
            System.out.println("[aspect] enter "
                    + context.operation()
                    + " target=" + context.targetType()
                    + " args=" + context.safeArguments());
        }

        void finished(
                InvocationSnapshot context,
                Completion completion,
                String detail) {
            System.out.println("[aspect] exit "
                    + context.operation()
                    + " outcome=" + completion
                    + " detail=" + detail);
        }
    }

    static final class AdviceBridge implements InvocationHandler {
        private final Object target;
        private final ContextExtractor extractor;
        private final AuditPolicy policy;

        AdviceBridge(
                Object target,
                ContextExtractor extractor,
                AuditPolicy policy) {
            this.target = target;
            this.extractor = extractor;
            this.policy = policy;
        }

        @Override
        public Object invoke(
                Object proxy, Method method, Object[] arguments)
                throws Throwable {
            InvocationSnapshot context =
                    extractor.extract(method, target, arguments);
            policy.started(context);

            try {
                Object result = method.invoke(target, arguments);
                policy.finished(
                        context, Completion.RETURNED, "returned");
                return result;
            } catch (InvocationTargetException wrapped) {
                Throwable cause = wrapped.getCause();
                policy.finished(
                        context, Completion.THREW,
                        cause.getClass().getSimpleName());
                throw cause;
            }
        }
    }

    public static void main(String[] args) {
        PaymentApi target = new PaymentService();
        ContextExtractor extractor = new ContextExtractor();
        AuditPolicy policy = new AuditPolicy();

        PaymentApi observed = (PaymentApi) Proxy.newProxyInstance(
                PaymentApi.class.getClassLoader(),
                new Class<?>[] {PaymentApi.class},
                new AdviceBridge(target, extractor, policy)
        );

        System.out.println("[caller] " + observed.pay("acct-123", 120));

        try {
            observed.pay("acct-999", 0);
        } catch (IllegalArgumentException error) {
            System.out.println("[caller] caught " + error.getMessage());
        }

        System.out.println("[caller] " + observed.status());
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac SeparatedAdviceDemo.java
java SeparatedAdviceDemo
~~~

**Stdout chính xác:**

~~~text
[aspect] enter PaymentApi.pay target=PaymentService args=[account=***, amount=120]
[business] pay amount=120
[aspect] exit PaymentApi.pay outcome=RETURNED detail=returned
[caller] ok-120
[aspect] enter PaymentApi.pay target=PaymentService args=[account=***, amount=0]
[business] pay amount=0
[aspect] exit PaymentApi.pay outcome=THREW detail=IllegalArgumentException
[caller] caught amount must be positive
[aspect] enter PaymentApi.status target=PaymentService args=[]
[business] status
[aspect] exit PaymentApi.status outcome=RETURNED detail=returned
[caller] READY
~~~

### 9.1. Nghiệp vụ và aspect không phụ thuộc lẫn nhau

`PaymentService` thực hiện kiểm tra `amount` và trả chuỗi kết quả. Nó **không** gọi extractor, không ghi sự kiện audit và không biết proxy.

`AuditPolicy` nhận `InvocationSnapshot` cùng loại hoàn tất và một chi tiết an toàn. Nó **không** biết `Method.invoke`, `InvocationTargetException`, tên account thật hoặc tham chiếu đối tượng đích.

Đây là tác dụng cốt lõi của việc tách lớp: thay đổi cách thu thập metadata **không buộc viết lại chính sách audit**, và thay đổi định dạng audit **không buộc thay cách gọi nghiệp vụ**.

### 9.2. Vì sao snapshot che tài khoản?

Ở `pay`, extractor cố ý biến mọi account ID thành `"account=***"`. Policy không bao giờ nhận giá trị nguyên bản nên khó vô tình ghi nó ra log. Trường amount được chọn để minh họa dữ liệu không bị che theo **quy ước riêng của ví dụ**.

Trong ứng dụng thật, ngay cả số tiền cũng có thể là thông tin nhạy cảm. Danh sách trường được phép ghi và cách masking phải xuất phát từ hợp đồng dữ liệu và yêu cầu riêng tư cụ thể.

### 9.3. Vì sao không dùng `arguments.toString()`?

`Object[]` không có cách `toString()` trực tiếp cho nội dung theo ý muốn, còn `Arrays.toString(arguments)` có thể in thông tin nhạy cảm hoặc gọi `toString()` của những đối tượng phức tạp. Extractor không nên serialize cả mảng đối số một cách tùy tiện.

Ở đây extractor dùng **allowlist minh họa**: chỉ với phương thức `pay` hai tham số thì lấy amount, mọi tham số khác sẽ được che. Cách nhận diện bằng tên/số tham số phù hợp với demo nhỏ, nhưng trong hệ thật nên xét **chữ ký, metadata hoặc descriptor chính xác** để tránh nhầm những overload trùng tên.

### 9.4. Vì sao result không được lưu trong context đầu vào?

Snapshot được tạo **trước khi gọi phần gốc** nên chưa có return value. Khi phần gốc hoàn tất, `AdviceBridge` tạo dữ liệu hoàn tất `Completion.RETURNED` hoặc `Completion.THREW` để đưa cho policy.

Giữ **bản chụp đầu vào** và **sự kiện hoàn tất** riêng giúp tránh ghi một trường `result` vào context lúc chưa biết giá trị, hoặc làm một DTO mutable đổi trạng thái từ “chưa hoàn tất” sang “đã hoàn tất”.

### 9.5. Vì sao cần gỡ `InvocationTargetException`?

Khi gọi `method.invoke(target, arguments)`, lỗi do phần gốc ném có thể được bọc bởi `InvocationTargetException`. Adapter giải lớp bọc để policy phân loại **loại lỗi gốc** rồi ném lại chính nguyên nhân.

Đây là một đặc điểm của **reflection trong ví dụ**, không phải cú pháp bắt buộc của mọi around advice. Những cơ chế weaving khác có thể cho return/throw đi qua continuation trực tiếp.

### 9.6. Phạm vi ví dụ không bao phủ mọi lỗi của adapter

Ví dụ minh họa xử lý đường **method trả bình thường** và **method đích ném qua `InvocationTargetException`**. Nếu **extractor, policy hoặc chính hạ tầng reflection** ném lỗi khác, mã adapter có thể chưa ghi sự kiện exit và lỗi của chính aspect có thể ảnh hưởng caller.

Điều này **không được xem là thiết kế production hoàn chỉnh**. Phần sau phân tích chiến lược lỗi và cách kiểm thử trường hợp hạ tầng/aspect gặp sự cố. Quan trọng là không che đi giới hạn của một chương trình chỉ nhằm học kiến trúc tách lớp.

## 10. Tiêu chí của một ContextExtractor tốt

Một extractor chuyên trách nên có những phẩm chất sau.

### 10.1. Có đầu vào và đầu ra rõ ràng

Giao diện khai báo rõ đọc dữ liệu nào và trả kiểu gì; không âm thầm truy cập một biến toàn cục hoặc log thẳng.

### 10.2. Ít tác dụng phụ

Lý tưởng, extractor là một phép biến đổi dữ liệu: cùng dữ liệu đầu vào hợp lệ tạo cùng snapshot (bỏ qua metadata động được khai báo là một phần input). Không thực hiện I/O mạng, ghi database hay gọi lại nghiệp vụ.

### 10.3. Không điều khiển proceed

Chỉ advice/adapter phối hợp `proceed` hoặc cơ chế tương đương. Extractor không tự chạy phần nghiệp vụ, không retry, không short-circuit.

### 10.4. Không làm lộ dữ liệu không cần thiết

Áp dụng allowlist và masking **trước khi** đưa dữ liệu đến policy hoặc sink. Hạn chế cả những dữ liệu trung gian bị giữ quá lâu.

### 10.5. Có cách xử lý thiếu dữ liệu

Nếu source location không có, giá trị target là null hoặc model không cung cấp tên tham số, extractor cần trả một dạng `unknown`/optional theo schema hoặc xử lý theo hợp đồng. Không tự đoán những trường chưa được quan sát.

### 10.6. Chi phí có thể dự đoán

Tránh truy cập dữ liệu lớn, gọi `toString()` tùy ý, lập bản sao sâu quá mức hoặc dùng reflection lặp lại đắt đỏ mà không có nhu cầu.

### 10.7. Có thể kiểm thử độc lập

Có thể gọi extractor bằng dữ liệu giả lập mà không cần kích hoạt AOP thực, sau đó so khớp snapshot. Đây là ưu điểm trực tiếp của việc tách trách nhiệm.

## 11. Kiểm thử extractor riêng không cần chạy cả aspect

Một extractor tốt nên được kiểm thử như một hàm chuyển đổi. Ví dụ các ca cho `ContextExtractor` của chương trình Java 17 ở trên:

| Đầu vào | Kỳ vọng |
|---|---|
| `PaymentApi.pay("acct-123",120)` | Operation `PaymentApi.pay`; target `PaymentService`; args chỉ `account=***`, `amount=120` |
| `PaymentApi.pay("acct-999",0)` | Tài khoản vẫn bị che; amount là `0` |
| `PaymentApi.status()` | Operation `PaymentApi.status`; args là danh sách trống |
| Một method khác có đối số | Mỗi đối số bị che bằng placeholder |
| Mảng đối số gốc bị thay đổi sau khi trích xuất | Snapshot không tự biến đổi vì chỉ giữ chuỗi an toàn và `List.copyOf` |
| Tên chữ ký không phù hợp chính sách allowlist | Không tự tiết lộ giá trị chưa được phép |

### 11.1. Một phép kiểm thử Java 17 tối giản

Giả sử các lớp nằm trong cùng chương trình `SeparatedAdviceDemo`, ta có thể bổ sung **một phương thức kiểm thử** dưới đây trong class đó (đây là **mảnh mã để gắn vào ví dụ**, không phải tệp chạy độc lập):

~~~java
static void verifyExtractor() throws Exception {
    var method = PaymentApi.class.getMethod(
            "pay", String.class, int.class);

    var extractor = new ContextExtractor();
    var context = extractor.extract(
            method, new PaymentService(),
            new Object[] {"private-account", 120});

    if (!context.operation().equals("PaymentApi.pay")) {
        throw new AssertionError("wrong operation");
    }
    if (!context.safeArguments().equals(
            List.of("account=***", "amount=120"))) {
        throw new AssertionError("unexpected safe arguments");
    }
    if (context.safeArguments().toString()
            .contains("private-account")) {
        throw new AssertionError("sensitive data leaked");
    }
}
~~~

Muốn chạy phép kiểm thử này trong ví dụ, gọi `verifyExtractor()` từ `main` hoặc từ một bộ kiểm thử Java tương thích. Vì phương thức không in gì nếu thành công, stdout minh họa của `main` **không đổi** khi gắn nó và gọi ở đầu `main`.

Điểm chính là **không cần tạo proxy** mới xác minh được việc che dữ liệu. Bộ kiểm thử AOP/integration vẫn cần ở tầng khác để xác minh extractor thực sự được gọi tại các join point như kỳ vọng.

## 12. Kiểm thử policy riêng bằng context giả

Tương tự, policy không nên bắt buộc có một đối tượng join point thật để chạy.

Pseudocode:

~~~text
snapshot = InvocationSnapshot(
    operation="PaymentApi.pay",
    targetType="PaymentService",
    safeArguments=["account=***", "amount=120"])

sink = FakeEventSink()

policy = AuditPolicy(sink)
policy.started(snapshot)
policy.finished(snapshot, RETURNED, "returned")

assert sink.events == [
    EnterEvent("PaymentApi.pay", ...),
    ExitEvent("PaymentApi.pay", RETURNED, ...)
]
~~~

Đây là mã **minh họa kiến trúc**, không phải cú pháp Java độc lập.

Việc dùng **fake sink** giúp test không ghi vào log thật hoặc gọi dịch vụ ngoài. Kiểm thử policy chỉ quan tâm quyết định phát sự kiện; nó không cần biết `Method`, `Proxy` hay cách engine AOP bind tham số.

Để làm được điều này trong chương trình production, tách `AuditPolicy` khỏi `System.out` bằng giao diện `EventSink` là một bước hữu ích. Demo dùng `System.out` trực tiếp chỉ để stdout dễ quan sát.

## 13. Phân biệt kiểm thử extractor, policy và advice adapter

Ba tầng nên có bộ kiểm thử riêng:

| Tầng | Cần kiểm thử | Không cần giả định |
|---|---|---|
| **Extractor unit test** | Mapping metadata, masking, chuẩn hóa, xử lý null/thiếu trường | Không cần weaving |
| **Policy unit test** | Quy tắc chọn loại sự kiện, phân loại completion, gọi sink | Không cần đối tượng join point của công cụ |
| **Adapter/integration test** | Pointcut khớp, adapter được gọi, proceed đúng một lần, return/throw bảo toàn | Không chỉ dựa vào test `extract()` |
| **System/observability test** | Sự kiện có tới sink đúng trong môi trường chạy, giới hạn riêng tư và số lần ghi | Không suy từ stdout demo |

**Unit test extractor PASS không chứng minh pointcut bao phủ tất cả đường gọi cần thiết.** Ngược lại, integration test nhìn thấy một dòng log cũng không chứng minh extractor không rò rỉ dữ liệu ở các overload và tình huống lỗi khác.

## 14. Sai lầm: để extractor phụ thuộc vào policy

Một thiết kế kém:

~~~text
extract(joinPoint):
    if methodName startsWith "pay":
        log("PAYMENT STARTED")
    updateMetrics()
    return rawArguments
~~~

Bộ phận mang tên extractor ở đây vừa **đọc** ngữ cảnh, vừa **thực thi chính sách**. Hệ quả:

- Không thể kiểm thử mapping mà không làm phát sinh log.
- Đổi quy tắc audit buộc sửa mã đọc join point.
- Dùng lại extractor cho metrics có thể tạo log không mong muốn.
- Một lần trích xuất nhiều lần có thể tạo nhiều sự kiện sai.
- Dữ liệu raw được trả ra policy, tăng nguy cơ rò rỉ.

Cách tách:

~~~text
snapshot = extractor.extract(joinPoint)
policy.recordStart(snapshot)
~~~

Extractor chỉ trả một snapshot an toàn; policy quyết định có phát sự kiện hay không. Nếu cần nhiều policy, tất cả có thể dùng cùng schema nhưng phải có hợp đồng rõ về thứ tự và quyền truy cập.

## 15. Sai lầm ngược: đẩy mọi quyết định ngữ cảnh vào advice

Một thiết kế khác cũng khó bảo trì:

~~~text
around selected:
    if joinPoint.kind == METHOD_EXECUTION:
        if joinPoint.signature.name == "pay":
            if joinPoint.args.length == 2:
                account = joinPoint.args[0]
                amount = joinPoint.args[1]
                ...
    policy.handle(account, amount, declaringClass, ...)
~~~

Lúc này advice trở thành một extractor khổng lồ. Khi thêm overload, method call, constructor hoặc dữ liệu ngữ cảnh mới, phần điều phối `proceed` có nguy cơ bị sửa sai trong lúc cập nhật mapping.

Giải pháp là đưa khối ánh xạ/chuẩn hóa dữ liệu vào **một hàm có tên và hợp đồng riêng**. Advice đọc dễ hơn:

~~~text
snapshot = extractor.extract(joinPointContext)
policy.before(snapshot)
return proceed()
~~~

Nếu policy cần kết quả/ngoại lệ, advice đưa sự kiện hoàn tất vào policy sau `proceed` mà không hòa trộn mã phân tích chữ ký với mã điều khiển luồng.

## 16. Vì sao không truyền trực tiếp RawJoinPoint xuống mọi tầng?

Một đối tượng join point thô có thể có quyền truy cập rộng:

- Danh sách đối số gốc chứa dữ liệu nhạy cảm.
- Tham chiếu target cho phép chạm trạng thái mutable.
- Dữ liệu của công cụ weaving/proxy gắn với vòng đời invocation hiện tại.
- Các API `proceed`, `getThis`, `getTarget`, `getArgs` hoặc tương đương có semantics phụ thuộc công cụ.

Nếu truyền trực tiếp nó qua nhiều tầng, các policy trở nên **phụ thuộc vào công cụ**, dễ đọc dữ liệu thừa hoặc gọi nhầm phần gốc. Nếu giữ join point sau khi invocation kết thúc, có thể vi phạm hợp đồng vòng đời của cơ chế.

Một context snapshot nhỏ là ranh giới **giảm quyền**: chỉ cung cấp những trường cần và không cho policy nắm quyền điều khiển lời gọi nghiệp vụ.

**Ngoại lệ có chủ đích:** một số aspect thực sự cần khả năng đặc thù của join point ở policy (ví dụ chính sách có phép biến đổi đối số). Khi đó phải định nghĩa một giao diện năng lực hẹp, tách riêng khỏi extractor quan sát, thay vì giả định mọi policy đều có quyền điều khiển `proceed`.

## 17. Chữ ký, metadata và đối tượng đích: mapping đúng nguồn

Với Java:

~~~java
interface PaymentApi {
    String pay(String account, int amount);
}

final class PaymentService implements PaymentApi {
    public String pay(String account, int amount) {
        return "ok";
    }
}
~~~

Đây là **mã khai báo minh họa**, không phải chương trình độc lập.

Một proxy của `PaymentApi` có thể cung cấp `Method` được khai báo trên interface. Vì thế:

- `method.getDeclaringClass()` có thể là `PaymentApi`.
- `target.getClass()` là `PaymentService`.

Đây là **hai thông tin đúng nhưng khác mục đích**. Extractor không nên đổi nhầm declaring type thành runtime target type hoặc ngược lại.

Tương tự, annotation có thể được khai báo trên interface hoặc implementation. Một phương thức reflection của interface **không tự mang mọi annotation của phương thức implementation**. Nếu policy dựa trên annotation, extractor/adapter phải xác định rõ nguồn metadata và quy tắc tra cứu của công cụ.

### 17.1. Generic, overload và biến thể chữ ký

Một method `submit(String)` khác `submit(String,int)`. Một extractor chọn chính sách chỉ bằng tên có thể nhầm overload. Với generic Java, các type argument có thể bị **type erasure** trong bytecode; không tự coi `List<String>` và `List<Integer>` là hai chữ ký runtime phân biệt.

Để an toàn, có thể dùng một **operation descriptor** đã được xác định rõ: loại join point, declaring type, method name, parameter types và các metadata cần thiết, thay vì phụ thuộc một tên ngắn.

## 18. Lỗi trích xuất ngữ cảnh phải được xử lý thế nào?

Có hai loại lỗi khác nhau:

1. **Lỗi nghiệp vụ gốc:** phần xử lý được quan sát ném ngoại lệ.
2. **Lỗi của aspect/extractor/policy/sink:** thao tác đọc metadata, masking, format hoặc ghi nhận gặp lỗi.

Nếu aspect **chỉ quan sát**, một yêu cầu thường gặp là không để lỗi telemetry làm thất bại thao tác nghiệp vụ vốn sẽ thành công. Nhưng nếu aspect thực thi **một bảo đảm bắt buộc** (ví dụ kiểm tra chính sách tại ranh giới được thiết kế), chọn “bỏ qua mọi lỗi và tiếp tục” có thể là sai về tính đúng đắn/an toàn.

Cần phân loại chính sách:

| Loại mối quan tâm | Hướng xử lý lỗi thường cần cân nhắc |
|---|---|
| Metrics best-effort | Hạn chế ảnh hưởng nghiệp vụ; ghi dấu mất metrics bằng kênh thích hợp |
| Log chẩn đoán best-effort | Có chiến lược fallback/gộp hoặc bỏ bản ghi an toàn |
| Audit bắt buộc | Xác định rõ hợp đồng fail-closed/fail-open, độ bền lưu trữ và cách thông báo lỗi |
| Kiểm soát an toàn | Không tự bỏ qua lỗi của kiểm tra bắt buộc |
| Dọn ngữ cảnh bắt buộc | Phải cân nhắc giữ lỗi chính và báo lỗi cleanup |

### 18.1. Nếu extractor lỗi trước proceed

Một around advice gọi extractor **trước** `proceed`. Nếu extractor ném lỗi, phần nghiệp vụ có thể **chưa chạy**. Đó có thể là lựa chọn có chủ đích đối với chính sách bắt buộc, nhưng là rủi ro không mong muốn với logging best-effort.

Có thể thiết kế wrapper an toàn quanh extractor để tạo snapshot tối thiểu hoặc báo tình trạng thiếu dữ liệu, **chỉ khi chính sách cho phép**. Không nên tự dùng chuỗi `"unknown"` cho mọi lỗi rồi ngầm giả vờ thông tin quan sát đầy đủ.

### 18.2. Nếu policy lỗi sau proceed

Nghiệp vụ có thể đã hoàn tất, nhưng policy/sink ghi kết quả tự ném lỗi. Caller có nguy cơ nhìn thấy lỗi từ aspect dù nghiệp vụ gốc thành công.

Nếu nghiệp vụ gốc đã ném lỗi và cleanup/policy cũng ném lỗi, lỗi aspect có thể **che nguyên nhân gốc**. Muốn bảo toàn lỗi gốc, cần hợp đồng riêng khi nhiều ngoại lệ đồng thời xuất hiện.

### 18.3. Đừng tự ném return/exception trong finally

Trong Java, `return` hoặc `throw` trong `finally` có thể thay thế kết quả hoặc ngoại lệ đang chờ. Mã dọn dẹp ở advice nên tránh hành vi này trừ khi đang triển khai một chính sách chuyển đổi có chủ đích và đã được kiểm thử.

## 19. Bản chụp khi vào và sự kiện khi thoát

Một mô hình tách lớp tốt thường có **hai thời điểm**:

~~~text
Vào join point:
    entry = extractor.extractEntry(rawContext)
    policy.onEntry(entry)

    result = proceed()

Thoát bình thường:
    completion = extractor.extractReturn(entry, result)
    policy.onCompletion(completion)

Thoát ngoại lệ:
    completion = extractor.extractFailure(entry, error)
    policy.onCompletion(completion)
    throw error
~~~

Đây là pseudocode, không phải cú pháp công cụ AOP.

Vì return value và exception chưa tồn tại lúc bắt đầu, hãy cân nhắc hai kiểu record:

~~~text
EntrySnapshot(operation, safeArguments, correlation)
CompletionSnapshot(entryId, completionKind, safeResultOrErrorType)
~~~

Điều này tránh tạo một object mutable có các trường lúc đầu null, sau đó thay đổi; những policy cần quan sát đồng thời cũng không phải lo có thread khác sửa snapshot sau khi nhận.

### 19.1. “Method return” không đồng nghĩa “nghiệp vụ thành công”

Một method có thể trả về bình thường một kết quả `DECLINED`. Completion kind `RETURNED` nói rằng không có ngoại lệ thoát khỏi ranh giới method. Trạng thái nghiệp vụ cần được diễn giải từ **hợp đồng kết quả** nếu chính sách thật sự cần nó, và chỉ khi được phép đọc.

### 19.2. “Method return” không đồng nghĩa tác vụ bất đồng bộ hoàn tất

Một method có thể trả một `CompletionStage` hoặc handle của công việc đang chạy. Nếu policy cần quan sát thời điểm tác vụ hoàn tất, phải có extractor/adapter của **sự kiện hoàn tất đó** hoặc cơ chế callback tương ứng. Advice quanh method trả về chỉ quan sát ranh giới method.

## 20. Lưu ý về đồng thời, lồng nhau và vòng đời context

### 20.1. Không dùng biến toàn cục làm snapshot của lần gọi

Nếu advice đặt `currentOperation` vào một biến static dùng chung, hai thread hoặc hai lời gọi lồng nhau có thể ghi đè. Thay vào đó, giữ snapshot trong **biến cục bộ của invocation** hoặc trong một cơ chế ngữ cảnh được thiết kế rõ cho từng lần gọi.

### 20.2. Context theo thread cần lưu-phục hồi

Một `ThreadLocal` dùng cho correlation có thể phù hợp với lời gọi đồng bộ, nhưng khi advice lồng nhau, giá trị mới cần **phục hồi giá trị cũ** thay vì xóa sạch. Nếu không, advice bên trong có thể làm mất context của advice bên ngoài.

### 20.3. Không giữ RawJoinPoint để xử lý về sau

Nếu cần gửi sự kiện bất đồng bộ tới queue, nên gửi **snapshot bất biến, tối thiểu**, không gửi đối tượng join point thô cùng tham chiếu target và argument array mutable. Context gốc có thể chỉ có ý nghĩa trong vòng đời invocation.

### 20.4. Bounded data

Một argument có thể chứa tập dữ liệu lớn. Snapshot nên giữ các trường cần thiết, kích thước giới hạn hoặc mã tham chiếu an toàn, thay vì sao chép toàn bộ object graph rồi đẩy qua nhiều queue.

## 21. Mở rộng cho nhiều loại join point

Nếu hệ AOP hỗ trợ **method call**, **method execution**, **constructor execution**, **field get/set**, các loại điểm đó có thông tin mô tả khác nhau. Không nên thiết kế extractor giả định luôn có `Method` và `Object[] args`.

Một cách mở rộng:

~~~text
sealed ContextDescriptor:
    MethodDescriptor(kind, declaringType, name, parameterTypes)
    ConstructorDescriptor(kind, declaringType, parameterTypes)
    FieldDescriptor(kind, declaringType, fieldName, fieldType)

Extractor:
    extract(descriptor, runtimeData) -> ContextSnapshot
~~~

Đây là pseudocode nêu kiến trúc. Một hệ thống Java 17 có thể biểu diễn hierarchy đóng bằng `sealed interface` và các record implement phù hợp.

**Không nhất thiết mọi loại join point đều cần cùng schema.** Ví dụ field set có giá trị gán, field get có giá trị đọc; constructor execution không có kiểu trả về như method. Có thể dùng các context type chuyên biệt để tránh nhiều trường null và những phép ép kiểu thiếu an toàn.

### 21.1. Method call và method execution không thể gộp mù quáng

Call site là nơi caller yêu cầu gọi; execution là nơi phần đích chạy. Nếu policy quan sát “được gọi từ module nào”, thông tin call site cần được thu ở một loại join point có ngữ nghĩa phù hợp. Nếu extractor chỉ có metadata của method execution, không thể tự suy chính xác caller từ method signature.

### 21.2. Khả năng đọc metadata khác khả năng can thiệp

Java Reflection đọc được `Method`, `Constructor`, `Field`. Điều đó **không chứng minh** một công cụ AOP hỗ trợ advice trên mọi method call, constructor hay field access. Cần xác minh join point model, phạm vi weaving và runtime path trước khi triển khai extractor của loại điểm đó.

## 22. Điều kiện pointcut thuộc tầng nào?

Pointcut quyết định **điểm nào** được chọn. Extractor quyết định **dữ liệu nào** được lấy ở một điểm đã vào adapter. Hai khái niệm khác nhau.

Ví dụ:

~~~text
Pointcut:
    chọn method execution thuộc nhóm thao tác thanh toán

Extractor:
    tạo snapshot gồm operation, targetType và amount an toàn

Policy:
    ghi enter / exit cho tất cả điểm phù hợp
~~~

Nếu một phần điều kiện phụ thuộc đối số lúc chạy, ngôn ngữ AOP có thể có **dynamic pointcut**. Không được tùy tiện chuyển toàn bộ logic chọn điểm sang extractor rồi coi như hiệu ứng tương đương: với cách đó, advice có thể đã được kích hoạt và tiêu tốn chi phí trước khi extractor quyết định bỏ qua.

Ngược lại, không nên nhét mọi quy tắc format và masking vào pointcut. Pointcut nên mô tả tập điểm, còn extractor nên cung cấp dữ liệu sạch để policy xử lý.

**Một ranh giới dễ bảo trì:** pointcut chọn *nơi* cần quan sát, extractor chọn *dữ liệu* cần mang theo, policy chọn *phản ứng* tương ứng.

## 23. Khi nào extractor cần biết chính sách?

Không phải mọi hệ thống đều muốn một extractor “không biết gì” về mục tiêu. Để chọn trường an toàn, extractor có thể nhận **cấu hình** như:

~~~text
ExtractionPolicy:
    allowedFields = ["operation", "targetType", "amount"]
    redactFields = ["accountId"]
    maxStringLength = 120
~~~

Điều đó khác với việc extractor tự quyết định có ghi audit hay gửi metrics không.

- **Cấu hình trích xuất** mô tả tập dữ liệu đầu ra hợp lệ và cách bảo vệ dữ liệu.
- **Aspect policy** mô tả hành động trên snapshot đã trích xuất.
- **Sink policy** mô tả nơi, định dạng và độ bền khi phát sự kiện.

Tách biệt trách nhiệm **không nhất thiết** đòi hỏi mỗi class không có cấu hình. Điều quan trọng là không tạo vòng phụ thuộc khiến thay đổi logging buộc thay đổi mã reflection ở mọi advice.

## 24. Hiệu năng: tách lớp không được biến thành sao chép vô hạn

Việc tạo một DTO cho mỗi join point có chi phí. Nhưng trộn mọi thứ trong advice cũng không miễn phí. Hãy đo các chi phí chính:

1. Truy xuất signature/annotation ở các điểm tần suất cao.
2. Sao chép hoặc định dạng đối số.
3. Chuẩn hóa, masking, serialize dữ liệu.
4. Tạo DTO và sự kiện.
5. Gửi sink đồng bộ hoặc bất đồng bộ.
6. Kiểm tra điều kiện động.
7. Logging trong đường nóng.

Các cách giảm chi phí có thể có:

- Pointcut đủ hẹp để không chặn những điểm không cần quan sát.
- Cache **metadata tĩnh** theo định danh phù hợp và vòng đời class loader.
- Không cache **đối số runtime** như dữ liệu tĩnh.
- Chỉ trích xuất trường policy thật sự cần.
- Hạn chế `toString()` trên object không rõ nguồn.
- Dùng schema/snapshot nhẹ, có kích thước giới hạn.
- Nếu dùng queue, thiết kế giới hạn dung lượng, backpressure và chính sách mất sự kiện rõ ràng.

Không được mặc định một implementation AOP sẽ tối ưu hóa các bước theo cùng cách. Việc đo phải thực hiện trong cơ chế, pointcut và workload thực tế.

## 25. Những lỗi thường gặp và cách sửa

### 25.1. “Extractor” vừa ghi log vừa gọi phần gốc

**Lỗi:** bộ phận chuyển dữ liệu có side effect và quyền điều khiển luồng.

**Cách sửa:** extractor trả snapshot; adapter chịu trách nhiệm proceed; policy/sink chịu trách nhiệm ghi sự kiện.

### 25.2. Policy nhận trực tiếp đối tượng join point của công cụ

**Lỗi:** policy phụ thuộc API AOP, khó unit test và có quyền đọc raw arguments không cần thiết.

**Cách sửa:** truyền context DTO trung lập; giữ phụ thuộc công cụ ở adapter.

### 25.3. Context giữ `Object[]` mà không snapshot

**Lỗi:** đối số là mảng mutable và có thể chứa object nhạy cảm; thay đổi sau khi event phát sẽ làm dữ liệu không nhất quán.

**Cách sửa:** sao chép dữ liệu được phép vào kiểu bất biến/đã chuẩn hóa.

### 25.4. Gọi `toString()` trên mọi đối số

**Lỗi:** lộ dữ liệu bí mật, tạo log lớn hoặc kích hoạt tác dụng phụ.

**Cách sửa:** allowlist, masking, giới hạn kích thước; không serialize object tùy tiện.

### 25.5. Phụ thuộc tên method mà bỏ chữ ký

**Lỗi:** overload cùng tên có hợp đồng đối số khác nhau.

**Cách sửa:** dùng descriptor có kiểu khai báo, tên và kiểu tham số; kiểm thử overload.

### 25.6. Nhầm kiểu khai báo với kiểu runtime

**Lỗi:** xem declaring type của method interface là class thực của target.

**Cách sửa:** tách `declaringType` và `targetType`, chỉ lấy cái cần thiết.

### 25.7. Bắt lỗi aspect rồi luôn cho phép thao tác

**Lỗi:** với chính sách bắt buộc, fail-open có thể vi phạm yêu cầu an toàn.

**Cách sửa:** định nghĩa chính sách lỗi theo mức độ bắt buộc của aspect, không theo sự tiện lợi của code.

### 25.8. Lỗi logging che ngoại lệ nghiệp vụ

**Lỗi:** advice ném ngoại lệ mới khi đang xử lý lỗi gốc.

**Cách sửa:** có chính sách lỗi quan sát và bảo toàn nguyên nhân gốc theo hợp đồng; kiểm thử lỗi kép.

### 25.9. Dùng `ThreadLocal` mà không phục hồi

**Lỗi:** context lồng nhau sai hoặc dữ liệu rò sang tác vụ khác trên thread pool.

**Cách sửa:** lưu giá trị cũ, restore trong `finally`, thiết kế truyền context cho async riêng.

### 25.10. Giữ context thô sau khi method kết thúc

**Lỗi:** vòng đời invocation có thể đã kết thúc; tham chiếu tới target hoặc args vẫn mutable.

**Cách sửa:** tạo snapshot tối thiểu trước khi gửi qua queue/callback.

### 25.11. Để policy quyết định thành công nghiệp vụ bằng exception đơn thuần

**Lỗi:** method có thể trả về trạng thái từ chối bình thường hoặc trả một handle tác vụ chưa hoàn tất.

**Cách sửa:** phân biệt completion kỹ thuật và outcome nghiệp vụ; lấy từ đúng hợp đồng và đúng điểm quan sát.

### 25.12. Coi một unit test extractor là đủ cho toàn hệ

**Lỗi:** phần trích xuất đúng nhưng pointcut không khớp hoặc lời gọi đi ngoài weaving.

**Cách sửa:** kết hợp test extractor, policy, adapter và runtime integration với đường gọi dương/âm.

## 26. Kịch bản nâng cao: nhiều policy dùng chung một snapshot

Một hệ thống có thể có nhiều mối quan tâm:

- Metrics chỉ cần operation và completion.
- Audit cần operation, correlation ID và một số trường được cho phép.
- Tracing cần operation, span context và mốc thời gian.
- Chẩn đoán cần thêm metadata khi mức debug được bật.

Một snapshot chung quá rộng dễ mang dữ liệu thừa tới tất cả policy. Có thể chọn:

1. **Một context cơ sở tối thiểu**, sau đó extractor chuyên biệt tạo các phần mở rộng theo quyền.
2. **Các DTO khác nhau theo mục đích**, ví dụ `MetricContext`, `AuditContext`.
3. **Một descriptor cấu trúc dùng chung**, cộng phần runtime trích xuất có điều kiện.

Đánh đổi: quá nhiều DTO gây phức tạp, một DTO quá rộng gây rủi ro. Chọn giải pháp dựa trên mức nhạy cảm và khả năng thay đổi của từng mối quan tâm.

**Không nên cấp toàn bộ raw arguments cho mọi policy chỉ vì nó làm API tiện hơn.**

## 27. Checklist thiết kế một aspect có tầng trích xuất riêng

1. Tôi đã xác định **loại join point** và vùng weaving thật sự được hỗ trợ chưa?
2. Pointcut chọn điểm nào, bao gồm/loại trừ các trường hợp nào?
3. Advice có chỉ làm nhiệm vụ **điều phối** và bảo toàn return/throw không?
4. Extractor có giao diện dữ liệu đầu vào/đầu ra rõ không?
5. Snapshot có phân biệt metadata cấu trúc với dữ liệu runtime không?
6. Snapshot có bất biến, kích thước giới hạn và không lưu tham chiếu thô không cần thiết không?
7. Có allowlist/redaction cho đối số hoặc giá trị kết quả không?
8. Policy có thể chạy unit test mà không cần engine AOP không?
9. Có fake sink để xác minh số lượng/loại sự kiện không?
10. Lỗi của extractor/policy/sink được xử lý theo chính sách bắt buộc hoặc best-effort rõ ràng chưa?
11. Thứ tự advice, lời gọi lồng nhau và đồng thời có được kiểm chứng?
12. Một lần method return có bị nhầm thành task async đã hoàn tất không?
13. Có thử cả ca **success**, **exception**, **pointcut không khớp** và **đường ngoài weaving** không?
14. Có xác minh không rò dữ liệu nhạy cảm trong log, exception message và những trường dự phòng?
15. Phần trích xuất có bị lặp ở nhiều advice không, và có thể chuẩn hóa thành một lớp chung đúng phạm vi không?

## 28. Bài tập tự kiểm tra

### Bài 1: Phân trách nhiệm

Một advice trực tiếp gọi `joinPoint.getArgs()`, format JSON, gửi thông điệp audit, quyết định kết quả `proceed` và tự làm retry. Hãy xác định đâu là ba trách nhiệm đang bị trộn.

**Đáp án:** đọc/chuyển đổi ngữ cảnh; chính sách audit và sink; điều phối luồng phần gốc bằng continuation. Retry lại là một chính sách điều khiển có hợp đồng riêng, không nên vô tình bị gộp vào extractor.

### Bài 2: Dữ liệu nào không nên đưa vào snapshot?

Tầng metrics chỉ cần loại thao tác và thời lượng. Có cần giữ toàn bộ `Object[] args` để “sau này tiện tra cứu” không?

**Đáp án:** không. Chỉ giữ các trường cần; lưu raw arguments làm tăng rủi ro quyền riêng tư, chi phí và tính mutable.

### Bài 3: Policy có cần `Method`?

Một policy chỉ quyết định in `STARTED` hoặc `FINISHED` theo operation. Có cần nhận `java.lang.reflect.Method` không?

**Đáp án:** thường không. Một `InvocationSnapshot` có operation đã chuẩn hóa và completion là đủ. `Method` nên thuộc adapter/extractor khi cần metadata.

### Bài 4: Lỗi của extractor

Một extractor logging best-effort ném lỗi trước khi advice gọi `proceed`. Điều gì có thể xảy ra?

**Đáp án:** phần gốc có thể không chạy, dù chính sách chỉ muốn quan sát. Cần thiết kế lỗi ở ranh giới aspect rõ ràng và kiểm thử tình huống đó.

### Bài 5: Return bình thường nhưng nghiệp vụ thất bại

Một method trả `PaymentResult.declined()` và không ném ngoại lệ. Snapshot completion nên ghi gì nếu chỉ quan sát ranh giới method?

**Đáp án:** `RETURNED` hoặc trạng thái tương đương. Việc thanh toán từ chối là **outcome nghiệp vụ**, không tự đồng nghĩa exceptional completion.

### Bài 6: Context với async

Advice đưa `RawJoinPoint` chứa target và args vào queue xử lý sau. Vấn đề có thể là gì?

**Đáp án:** object mutable, vòng đời join point, rò dữ liệu/giữ tham chiếu lớn; cần snapshot an toàn, nhỏ và đủ thông tin.

### Bài 7: Overload

Extractor che tài khoản cho phương thức tên `pay`, nhưng thêm overload `pay(Account, String)`. Dùng chỉ `method.getName().equals("pay")` có đủ không?

**Đáp án:** không. Phải kiểm tra descriptor/chữ ký thích hợp hoặc metadata hợp đồng để mapping đúng đối số theo từng overload.

### Bài 8: Kiểm thử ranh giới

Extractor và policy đều pass unit test, nhưng lời gọi `target.pay(...)` trực tiếp không có audit khi dùng proxy interface. Do lớp nào gây ra?

**Đáp án:** ranh giới runtime/weaving của adapter proxy. Unit test hai lớp kia không chứng minh mọi đường gọi đã đi qua proxy.

### Bài 9: Nhiều policy

Metrics cần operation, audit cần account đã che, tracing cần correlation. Nên phát cho cả ba raw arguments rồi để mỗi policy tự lọc không?

**Đáp án:** không nên mặc định. Tốt hơn dùng dữ liệu tối thiểu theo quyền, extractor chung hoặc chuyên biệt với schema rõ và masking trước khi truyền.

## 29. Ghi nhớ

- **Advice/adapter** chịu trách nhiệm đi qua ranh giới AOP và phối hợp continuation, return, exception.
- **Context extractor** chịu trách nhiệm chuyển dữ liệu join point thành **snapshot tối thiểu, an toàn, dễ kiểm thử**.
- **Aspect policy** chịu trách nhiệm quy tắc quan sát/kiểm toán/đo lường; không cần hiểu cơ chế phản chiếu hoặc weaving nếu không cần.
- **Event sink** là phụ thuộc riêng cho việc gửi/ghi sự kiện; policy có thể được test bằng fake sink.
- **Metadata cấu trúc** như chữ ký khác với **đối số/kết quả/ngoại lệ** của từng lần xuất hiện động.
- Không truyền dữ liệu thô rộng quyền hoặc mutable qua nhiều tầng khi chỉ cần một vài trường đã chuẩn hóa.
- Tách lớp không xóa bỏ trách nhiệm kiểm chứng **pointcut, join point model, weaving scope và runtime path**.
- Một aspect quan sát tốt phải có hợp đồng rõ về **lỗi của chính nó**, quyền riêng tư, đồng thời và hoàn tất bất đồng bộ.

Cách tự kiểm tra đơn giản: **“Nếu ngày mai thay cơ chế AOP nhưng giữ nguyên chính sách audit, tôi phải sửa phần đọc join point/adapter hay buộc viết lại toàn bộ chính sách?”** Nếu policy chỉ nhận một context rõ nghĩa, bất biến và trung lập, việc thay đổi sẽ được cô lập tốt hơn, đồng thời bộ kiểm thử trở nên đơn giản và đáng tin hơn.
