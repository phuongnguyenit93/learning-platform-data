# Context chuyên biệt và supportsContext khi tùy biến một loại quan sát

Micrometer Observation cho phép tách vòng đời đo lường khỏi cách đặt tên và gắn thuộc tính cho một loại thao tác. Khi instrumentation cần truyền dữ liệu nghiệp vụ có kiểu rõ ràng, ta có thể tạo một lớp kế thừa `Observation.Context`. Một `ObservationConvention<T>` đọc context đó để chọn tên, contextual name và các key-value phù hợp.

Phương thức `supportsContext(Observation.Context)` trả lời câu hỏi: convention này có áp dụng cho context hiện tại hay không? Với context chuyên biệt, cách triển khai thường là kiểm tra `instanceof` đúng kiểu context. Điều này giúp registry chọn đúng convention và tránh áp dụng quy tắc của một loại quan sát cho những loại khác.

Cần phân biệt phương thức cùng tên trên `ObservationHandler`: convention dùng `supportsContext` để chọn cách đặt tên và metadata; handler dùng nó để quyết định có nhận các callback vòng đời như `onStart`, `onError` và `onStop` hay không.

## 1. Vì sao cần context chuyên biệt?

Một Observation thường có các thông tin như tên thao tác, trạng thái lỗi và các key-value. Với thao tác nghiệp vụ, đôi khi cần thêm dữ liệu có cấu trúc:

- Loại thanh toán và kênh tiếp nhận.
- Loại tác vụ batch và nhóm dữ liệu.
- Loại truy vấn và nguồn dữ liệu.
- Loại lệnh gửi đến hệ thống bên ngoài.

Có thể đưa những giá trị này vào context chung bằng các key tùy ý, nhưng mã đọc dữ liệu phải nhớ key và kiểu dữ liệu tương ứng. Khi số trường tăng, việc ép kiểu và dùng key dạng chuỗi dễ gây nhầm lẫn.

Một lớp context chuyên biệt giúp khai báo dữ liệu ngay tại constructor, cung cấp getter có kiểu và thể hiện rõ loại Observation mà instrumentation đang tạo. Convention và handler sau đó có thể đọc các trường này mà không phải tra cứu các key rời rạc.

Ví dụ, một thao tác thanh toán cần biết phương thức thanh toán, kênh bán hàng và mã tham chiếu giao dịch. Ta tạo `PaymentObservationContext` để chứa các giá trị đó.

## 2. Tạo lớp kế thừa Observation.Context

`Observation.Context` là một vùng chứa mutable kiểu Map, được truyền giữa instrumentation và các ObservationHandler trong suốt vòng đời Observation. Có thể kế thừa lớp này để bổ sung các trường có kiểu:

~~~java
import io.micrometer.observation.Observation;

public final class PaymentObservationContext extends Observation.Context {

    private final String paymentMethod;
    private final String channel;
    private final String transactionReference;

    public PaymentObservationContext(
            String paymentMethod,
            String channel,
            String transactionReference) {
        this.paymentMethod = paymentMethod;
        this.channel = channel;
        this.transactionReference = transactionReference;
    }

    public String paymentMethod() {
        return paymentMethod;
    }

    public String channel() {
        return channel;
    }

    public String transactionReference() {
        return transactionReference;
    }
}
~~~

Các trường được giữ bất biến sau khi tạo context. Cách này phù hợp khi những giá trị cần cho convention đã biết ngay lúc bắt đầu thao tác.

Context vẫn có thể được bổ sung thông tin trong quá trình chạy nếu nghiệp vụ yêu cầu. Tuy nhiên, chỉ nên lưu dữ liệu cần thiết cho convention và handler. Tránh giữ toàn bộ entity, request body lớn, credential hoặc đối tượng có vòng đời phức tạp trong context.

Context không phải nơi lưu trạng thái nghiệp vụ lâu dài. Nó tồn tại để truyền thông tin phục vụ một Observation và các thành phần xử lý Observation đó.

## 3. ObservationConvention có kiểu context cụ thể

`ObservationConvention<T>` định nghĩa cách tạo metadata từ context có kiểu `T`. Các phương thức thường được tùy chỉnh gồm:

| Phương thức | Vai trò |
|---|---|
| `supportsContext(context)` | Xác định convention có áp dụng cho context này không |
| `getName()` | Trả về tên kỹ thuật ổn định của Observation |
| `getContextualName(context)` | Trả về tên dễ đọc, có thể dùng làm tên span |
| `getLowCardinalityKeyValues(context)` | Trả về thuộc tính có số giá trị hữu hạn |
| `getHighCardinalityKeyValues(context)` | Trả về thuộc tính có thể có nhiều giá trị |

Một interface riêng giúp mặc định hóa quy tắc chọn context cho mọi convention của loại thanh toán:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

public interface PaymentObservationConvention
        extends ObservationConvention<PaymentObservationContext> {

    @Override
    default boolean supportsContext(Observation.Context context) {
        return context instanceof PaymentObservationContext;
    }
}
~~~

Khi context là `PaymentObservationContext`, convention thanh toán được xem là phù hợp. Với context chung hoặc context của một loại nghiệp vụ khác, phương thức trả về `false`.

Nếu cần chỉ nhận đúng một lớp và loại trừ cả lớp con, có thể so sánh `context.getClass() == PaymentObservationContext.class`. Thông thường `instanceof` phù hợp hơn vì vẫn cho phép mở rộng context bằng subclass.

## 4. Convention mặc định cho thao tác thanh toán

Convention mặc định định nghĩa tên và cách chuyển các trường của context thành key-value:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

public class DefaultPaymentObservationConvention
        implements PaymentObservationConvention {

    @Override
    public String getName() {
        return "payment.process";
    }

    @Override
    public String getContextualName(PaymentObservationContext context) {
        return "process payment";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            PaymentObservationContext context) {
        return KeyValues.of(
            KeyValue.of("payment.method", context.paymentMethod()),
            KeyValue.of("payment.channel", context.channel())
        );
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(
            PaymentObservationContext context) {
        return KeyValues.of(
            KeyValue.of(
                "payment.transaction.reference",
                context.transactionReference()
            )
        );
    }
}
~~~

Tên `payment.process` là tên kỹ thuật, cần ổn định giữa các lần gọi. Contextual name `process payment` mô tả thao tác theo cách dễ đọc hơn.

Hai thuộc tính `payment.method` và `payment.channel` có tập giá trị hữu hạn nên được xếp vào low cardinality. Mã tham chiếu giao dịch có thể khác nhau ở từng lần thanh toán nên được xếp vào high cardinality.

Với `DefaultMeterObservationHandler`, low-cardinality key-value được dùng làm meter tags. High-cardinality key-value không được đưa vào meter vì có thể tạo quá nhiều chuỗi thời gian; chúng có thể được giữ trong dữ liệu tracing. Không đưa dữ liệu nhạy cảm như số thẻ, token hoặc thông tin cá nhân vào high-cardinality key-value chỉ vì chúng không trở thành metric tag.

## 5. supportsContext được dùng ở đâu?

Khi một Observation được tạo, Micrometer cần chọn một convention để lấy tên và key-value. Nếu instrumentation cung cấp custom convention, convention đó được ưu tiên. Nếu không, registry tìm một `GlobalObservationConvention` có `supportsContext(context)` trả về true. Nếu không tìm thấy convention toàn cục phù hợp, convention mặc định do instrumentation cung cấp sẽ được dùng.

Quy trình chọn convention:

~~~mermaid
flowchart TD
    A["Tạo Observation và context"] --> B{"Có custom convention?"}
    B -->|Có| C["Dùng custom convention"]
    B -->|Không| D{"Có GlobalObservationConvention hỗ trợ context?"}
    D -->|Có| E["Dùng global convention phù hợp"]
    D -->|Không| F["Dùng default convention"]
    C --> G["Lấy name và key-values"]
    E --> G
    F --> G
~~~

Thứ tự ưu tiên:

| Thứ tự | Convention | Khi nào được chọn? |
|---|---|---|
| 1 | Custom convention | Instrumentation truyền trực tiếp khi tạo Observation |
| 2 | GlobalObservationConvention | Không có custom convention và registry có convention hỗ trợ context |
| 3 | Default convention | Không có custom convention hoặc global convention phù hợp |

Trong registry, convention toàn cục được kiểm tra theo thứ tự đăng ký; convention phù hợp đầu tiên được chọn. Vì vậy, tránh đăng ký nhiều global convention có điều kiện `supportsContext` chồng lấn. Hãy làm điều kiện nhận diện càng rõ càng tốt.

`supportsContext` chỉ chọn convention. Nó không bắt đầu Observation, không quyết định Observation có bị vô hiệu hóa hay không và cũng không gọi handler.

## 6. Tạo Observation với default convention

Khi instrumentation muốn giữ convention mặc định nhưng cho phép cấu hình toàn cục ghi đè, dùng overload nhận custom convention, default convention, context supplier và registry:

~~~java
Observation observation = Observation.createNotStarted(
    null,
    new DefaultPaymentObservationConvention(),
    () -> new PaymentObservationContext("card", "web", "tx-93821"),
    observationRegistry
);

observation.observe(() -> paymentService.processPayment());
~~~

Tham số đầu tiên là `null`, nghĩa là instrumentation không ép một custom convention cụ thể. Micrometer sẽ tìm global convention phù hợp trong registry; nếu không có, nó dùng `DefaultPaymentObservationConvention`.

Dùng context supplier thay vì truyền trực tiếp context cho phép Micrometer trì hoãn việc tạo context cho đến khi biết Observation không phải no-op. Đây cũng là cách phù hợp với API nhận supplier trong Micrometer.

Nếu muốn chỉ định custom convention cho một lời gọi, truyền convention đó ở tham số đầu:

~~~java
Observation observation = Observation.createNotStarted(
    new PartnerPaymentObservationConvention(),
    new DefaultPaymentObservationConvention(),
    () -> new PaymentObservationContext("card", "web", "tx-93821"),
    observationRegistry
);

observation.observe(() -> paymentService.processPayment());
~~~

Trong trường hợp này custom convention thắng global convention và default convention. Đây là lựa chọn phù hợp khi một tích hợp cụ thể cần quy ước riêng mà không thay đổi quy tắc cho mọi thao tác thanh toán.

Khi truyền custom convention trực tiếp, instrumentation chịu trách nhiệm bảo đảm convention đó tương thích với kiểu context. Không nên dựa vào `supportsContext` như một bước kiểm tra để từ chối custom convention không phù hợp; custom convention được ưu tiên theo lựa chọn tường minh của caller.

## 7. Đăng ký GlobalObservationConvention

`GlobalObservationConvention<T>` là convention được đăng ký vào `ObservationRegistry`. Nó kế thừa `ObservationConvention<T>` và được registry kiểm tra khi chọn convention cho context tương ứng.

Ví dụ, một convention toàn cục thay đổi tên và bổ sung tag cho mọi PaymentObservationContext:

~~~java
import io.micrometer.observation.GlobalObservationConvention;

public final class GlobalPaymentObservationConvention
        extends DefaultPaymentObservationConvention
        implements GlobalObservationConvention<PaymentObservationContext> {

    @Override
    public String getName() {
        return "commerce.payment.process";
    }
}
~~~

Đăng ký với registry thuần Micrometer:

~~~java
ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
    .observationConvention(new GlobalPaymentObservationConvention());
~~~

Vì class kế thừa convention mặc định, nó giữ nguyên cách phân loại low/high cardinality và chỉ thay tên kỹ thuật. Có thể ghi đè thêm contextual name hoặc key-value nếu cần.

Nếu registry có nhiều global convention, hãy đảm bảo mỗi convention nhận đúng loại context. Ví dụ, convention cho PaymentObservationContext không nên trả về true với mọi Observation.Context, vì như vậy nó có thể chiếm quyền chọn của convention khác.

## 8. Tích hợp trong Spring Boot

Spring Boot tự động đăng ký các bean có kiểu `GlobalObservationConvention`, `ObservationHandler`, `ObservationFilter` và `ObservationPredicate` vào ObservationRegistry được quản lý. Vì vậy, có thể khai báo global convention thành bean:

~~~java
import io.micrometer.observation.GlobalObservationConvention;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PaymentObservationConfiguration {

    @Bean
    GlobalObservationConvention<PaymentObservationContext>
            paymentObservationConvention() {
        return new GlobalPaymentObservationConvention();
    }
}
~~~

Instrumentation chỉ cần inject `ObservationRegistry` và tạo Observation với context chuyên biệt cùng default convention. Khi không truyền custom convention, Spring Boot registry sẽ tìm global convention phù hợp.

Nếu muốn convention chỉ áp dụng cho một lần gọi, truyền custom convention trực tiếp khi tạo Observation. Không cần đăng ký convention toàn cục cho trường hợp đó.

Lưu ý: Spring Boot tự động đăng ký bean có kiểu `GlobalObservationConvention`. Một bean chỉ triển khai `ObservationConvention` thông thường không tự động trở thành global convention. Hãy dùng đúng interface nếu muốn registry chọn convention toàn cục.

## 9. Phân biệt supportsContext của Convention và Handler

Micrometer có hai interface đều định nghĩa `supportsContext(Observation.Context)`, nhưng chúng có trách nhiệm khác nhau:

| Nơi khai báo | Câu hỏi mà phương thức trả lời | Ảnh hưởng |
|---|---|---|
| ObservationConvention | Convention này có mô tả đúng loại context không? | Chọn tên và key-value cho Observation |
| ObservationHandler | Handler này có xử lý được loại context không? | Chọn handler nhận callback lifecycle |

Ví dụ handler chỉ xử lý context thanh toán:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;

public final class PaymentAuditHandler
        implements ObservationHandler<PaymentObservationContext> {

    @Override
    public void onStart(PaymentObservationContext context) {
        auditLog.started(context.paymentMethod(), context.channel());
    }

    @Override
    public void onStop(PaymentObservationContext context) {
        auditLog.finished(context.transactionReference());
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof PaymentObservationContext;
    }
}
~~~

Đăng ký handler:

~~~java
registry.observationConfig()
    .observationHandler(new PaymentAuditHandler());
~~~

Convention quyết định metadata của Observation; handler quyết định hành động cần thực hiện khi Observation bắt đầu, kết thúc hoặc gặp lỗi. Có thể có nhiều handler cùng hỗ trợ một context, ví dụ một handler tạo metrics và một handler ghi audit. Mỗi handler được chọn theo điều kiện hỗ trợ của chính nó.

Đừng dùng `ObservationHandler.supportsContext` để thay đổi tên metric hoặc key-value. Đó là trách nhiệm của convention. Ngược lại, đừng dùng `ObservationConvention.supportsContext` để quyết định có ghi audit hoặc tạo span hay không.

## 10. Phân biệt Convention, Predicate và Filter

Ba thành phần này thường được cấu hình cùng registry nhưng có mục đích khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| ObservationConvention | Đặt tên và tạo key-value theo loại context | Payment method, channel, transaction reference |
| ObservationPredicate | Quyết định Observation có được tạo hay trở thành no-op | Bỏ qua thao tác test hoặc một nhóm request |
| ObservationFilter | Chỉnh sửa context trước khi handler xử lý ở giai đoạn stop | Bổ sung thông tin môi trường dùng chung |

Nếu cần thêm một key-value cho mọi Observation, hãy cân nhắc ObservationFilter hoặc cấu hình common observation key-values trong Spring Boot. Không nên đưa logic toàn cục vào từng convention riêng lẻ.

Một điểm về thời gian: ObservationFilter được áp dụng khi Observation dừng, trước các handler xử lý `onStop`. Nếu một giá trị cần có ngay từ `onStart` — ví dụ tag của LongTaskTimer theo dõi tác vụ đang chạy — hãy thêm nó vào context trước khi gọi `start()`, thông qua context hoặc convention phù hợp.

## 11. Thiết kế low-cardinality và high-cardinality

Convention là nơi tốt để tập trung chính sách phân loại key-value. Với mỗi trường trong context, hãy xác định liệu tập giá trị có giới hạn hay có thể tăng theo từng lần gọi.

| Dữ liệu | Phân loại thường phù hợp | Lý do |
|---|---|---|
| payment.method | Low cardinality | Tập giá trị hữu hạn như card, bank, wallet |
| payment.channel | Low cardinality | Tập giá trị hữu hạn như web, mobile, store |
| transaction.reference | High cardinality | Có thể khác nhau cho từng giao dịch |
| customer identifier | High cardinality hoặc không thu thập | Dễ tạo nhiều giá trị và có thể nhạy cảm |
| exception message | Không nên dùng làm metric tag | Giá trị tự do, cardinality cao và có thể chứa dữ liệu nhạy cảm |

Với metrics, `DefaultMeterObservationHandler` chỉ sử dụng low-cardinality key-values làm meter tags. High-cardinality key-values dành cho tracing và không được đưa vào metrics để tránh bùng nổ số chuỗi thời gian.

Không phải mọi dữ liệu high-cardinality đều nên gửi vào trace. Hãy tuân thủ chính sách dữ liệu và quyền riêng tư của ứng dụng; loại bỏ bí mật, token, thông tin thanh toán và dữ liệu cá nhân không cần thiết.

## 12. Kiểm thử supportsContext và convention selection

Nên kiểm tra cả điều kiện nhận diện context và kết quả metadata. Kiểm thử đơn vị cho supportsContext:

~~~java
@Test
void paymentConventionSupportsOnlyPaymentContext() {
    PaymentObservationConvention convention =
        new DefaultPaymentObservationConvention();

    assertTrue(convention.supportsContext(
        new PaymentObservationContext("card", "web", "tx-1")
    ));

    assertFalse(convention.supportsContext(new Observation.Context()));
}
~~~

Kiểm thử metadata:

~~~java
@Test
void defaultConventionCreatesExpectedNamesAndKeyValues() {
    PaymentObservationContext context =
        new PaymentObservationContext("card", "web", "tx-1");

    PaymentObservationConvention convention =
        new DefaultPaymentObservationConvention();

    assertEquals("payment.process", convention.getName());
    assertEquals("process payment", convention.getContextualName(context));

    assertEquals(
        KeyValues.of(
            KeyValue.of("payment.method", "card"),
            KeyValue.of("payment.channel", "web")
        ),
        convention.getLowCardinalityKeyValues(context)
    );

    assertEquals(
        KeyValues.of(KeyValue.of("payment.transaction.reference", "tx-1")),
        convention.getHighCardinalityKeyValues(context)
    );
}
~~~

Có thể dùng `SimpleMeterRegistry` và `DefaultMeterObservationHandler` để kiểm tra các low-cardinality key-value trở thành meter tags:

~~~java
@Test
void observationUsesConventionAndCreatesTimer() {
    SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
    ObservationRegistry observationRegistry = ObservationRegistry.create();

    observationRegistry.observationConfig()
        .observationHandler(
            DefaultMeterObservationHandler.builder(meterRegistry).build()
        );

    PaymentObservationContext context =
        new PaymentObservationContext("card", "web", "tx-1");

    Observation.createNotStarted(
        null,
        new DefaultPaymentObservationConvention(),
        () -> context,
        observationRegistry
    ).observe(() -> paymentService.processPayment());

    assertEquals(
        1,
        meterRegistry.get("payment.process")
            .tag("payment.method", "card")
            .tag("payment.channel", "web")
            .timer()
            .count()
    );
}
~~~

Kiểm thử tích hợp nên bổ sung các trường hợp:

- Context thanh toán được convention thanh toán hỗ trợ.
- Context loại khác không được convention thanh toán nhận.
- Global convention được chọn khi không có custom convention.
- Custom convention truyền trực tiếp ghi đè global convention.
- Default convention được dùng khi không có global convention phù hợp.
- Handler chỉ nhận các context đúng kiểu.
- High-cardinality key-value không xuất hiện dưới dạng meter tag.
- Observation vẫn được dừng và báo lỗi đúng khi nghiệp vụ ném exception.

Khi kiểm tra registry, cần bảo đảm đã đăng ký handler tạo metrics. Chỉ tạo Observation và convention không tự động sinh Timer nếu registry chưa có handler tương ứng.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng Observation.Context chung cho mọi nghiệp vụ | Convention phải tra cứu key và ép kiểu | Tạo context chuyên biệt có getter có kiểu |
| supportsContext luôn trả true | Convention có thể nhận nhầm context | Kiểm tra đúng kiểu hoặc marker interface |
| Nhầm supportsContext của convention và handler | Đặt sai logic chọn metadata hoặc callback | Phân biệt convention chọn name/tags, handler chọn lifecycle |
| Đăng ký nhiều global convention có điều kiện chồng lấn | Convention đăng ký trước có thể chiếm quyền chọn | Thiết kế điều kiện nhận diện không chồng lấn |
| Truyền custom convention khi muốn global convention hoạt động | Custom convention luôn thắng global | Truyền null custom và cung cấp default convention |
| Dùng ObservationConvention thay GlobalObservationConvention để đăng ký toàn cục | Registry không xem bean đó là global convention | Triển khai GlobalObservationConvention |
| Đưa mã giao dịch vào low-cardinality key-value | Cardinality tăng theo từng giao dịch | Chuyển sang high cardinality hoặc bỏ khỏi metrics |
| Thêm key-value sau start nhưng kỳ vọng LongTaskTimer có tag đó | Meter active đã được tạo trước khi giá trị xuất hiện | Đặt key-value vào context trước start |
| Dùng ObservationFilter để chọn convention | Filter chạy ở giai đoạn khác và không có vai trò chọn convention | Dùng supportsContext và convention |
| Nghĩ convention tự tạo metrics | Không có meter nếu thiếu handler | Đăng ký DefaultMeterObservationHandler hoặc handler phù hợp |

## 14. Checklist triển khai

- [ ] Xác định loại Observation và dữ liệu nghiệp vụ cần truyền.
- [ ] Tạo context chuyên biệt kế thừa Observation.Context.
- [ ] Giữ context gọn, tránh lưu entity lớn hoặc dữ liệu nhạy cảm.
- [ ] Tạo ObservationConvention có generic context đúng kiểu.
- [ ] Triển khai supportsContext bằng điều kiện nhận diện rõ ràng.
- [ ] Đặt tên kỹ thuật và contextual name ổn định.
- [ ] Phân loại low-cardinality và high-cardinality key-values.
- [ ] Dùng GlobalObservationConvention nếu muốn cấu hình toàn registry.
- [ ] Dùng custom convention khi một instrumentation call cần ghi đè riêng.
- [ ] Hiểu thứ tự ưu tiên custom, global và default convention.
- [ ] Phân biệt supportsContext của convention với handler.
- [ ] Dùng Predicate để quyết định có tạo Observation và Filter để sửa context.
- [ ] Đảm bảo handler phù hợp đã đăng ký để tạo metrics hoặc tracing.
- [ ] Kiểm thử context match, convention selection và meter tags.
- [ ] Đặt các key-value cần cho active observation trước khi start.

Context chuyên biệt cung cấp dữ liệu có kiểu cho một loại Observation; convention chuyển dữ liệu đó thành tên và key-value nhất quán. `supportsContext` giúp registry nhận diện đúng context để chọn global convention phù hợp. Hãy giữ điều kiện nhận diện rõ ràng, phân biệt convention với handler, tuân thủ thứ tự custom/global/default và kiểm soát cardinality ngay tại nơi chuyển context thành metadata.

## Tài liệu tham khảo

- [Micrometer Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Observation Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [ObservationConvention API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/ObservationConvention.html)
- [Observation.Context API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/Observation.Context.html)
- [Spring Boot Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)

