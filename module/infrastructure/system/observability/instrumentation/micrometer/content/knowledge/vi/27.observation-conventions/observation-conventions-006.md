# Thứ tự ưu tiên giữa quy ước tùy chỉnh, quy ước dùng chung và mặc định

Micrometer Observation cho phép instrumentation định nghĩa cách đặt tên Observation và cách tạo các key-value đi kèm thông qua `ObservationConvention`. Một thư viện có thể cung cấp convention mặc định để ứng dụng dùng ngay; ứng dụng cũng có thể truyền một convention riêng cho từng lần tạo Observation hoặc đăng ký convention dùng chung trên `ObservationRegistry`.

Khi nhiều convention cùng có thể áp dụng, Micrometer chọn đúng một convention theo thứ tự ưu tiên:

1. **Custom convention** được truyền trực tiếp khi tạo Observation.
2. **Global convention** đã đăng ký trên `ObservationRegistry` và có `supportsContext(context)` trả về `true`.
3. **Default convention** do instrumentation cung cấp, dùng khi không có custom hoặc global convention phù hợp.

Ba cấp này không được ghép tự động với nhau. Convention được chọn chịu trách nhiệm cung cấp tên, contextual name và key-value của Observation. Nếu cần thêm một số key-value chung cho mọi Observation bất kể convention nào thắng, hãy dùng `ObservationFilter`.

## 1. ObservationConvention định nghĩa những gì?

`ObservationConvention<T>` mô tả cách đặt tên và các key-value dựa trên một `Observation.Context` cụ thể. Các phương thức thường được triển khai gồm:

| Phương thức | Vai trò |
|---|---|
| `getName()` | Tên Observation ổn định, thường được dùng làm tên metric hoặc span |
| `getContextualName(context)` | Tên mô tả thao tác cụ thể trong ngữ cảnh, hữu ích cho tracing |
| `getLowCardinalityKeyValues(context)` | Các key-value có số lượng giá trị hữu hạn, phù hợp để tạo metric tags |
| `getHighCardinalityKeyValues(context)` | Các key-value có thể có rất nhiều giá trị, thường hữu ích cho trace |
| `supportsContext(context)` | Xác định convention có áp dụng cho loại context này hay không |

Một convention có thể cung cấp tên và tag mặc định cho instrumentation. Ứng dụng có thể thay đổi cách đặt tên hoặc cách phân loại mà không cần sửa phần code thực hiện nghiệp vụ.

Ví dụ, một thư viện thuế có thể cung cấp Observation tên `tax.calculate`, low-cardinality key `tax.type` và high-cardinality key `tax.user.id`. Ứng dụng có thể giữ nguyên tên nhưng thêm tag môi trường hoặc thay cách biểu diễn loại thuế.

## 2. Ba cấp convention và thứ tự chọn

Micrometer chọn convention theo quy tắc:

| Thứ tự | Loại convention | Nơi cấu hình | Phạm vi |
|---:|---|---|---|
| 1 | Custom `ObservationConvention` | Truyền trực tiếp vào lời gọi tạo Observation hoặc API builder của instrumentation | Một instrumentation/lần tạo cụ thể |
| 2 | `GlobalObservationConvention` | `ObservationRegistry.observationConfig().observationConvention(...)` | Mọi Observation có context phù hợp trong registry |
| 3 | Default `ObservationConvention` | Do thư viện hoặc instrumentation truyền làm fallback | Chỉ dùng khi hai cấp trước không áp dụng |

Quy tắc quyết định:

~~~text
Có custom convention được truyền trực tiếp?
    Có  -> Dùng custom convention
    Không
      |
      v
Có GlobalObservationConvention hỗ trợ context?
    Có  -> Dùng global convention phù hợp đầu tiên
    Không
      |
      v
Dùng default convention của instrumentation
~~~

Custom convention thắng global convention kể cả khi global convention được đăng ký trên registry trước đó. Global convention thắng default convention nếu `supportsContext(context)` trả về `true`. Default chỉ là fallback.

## 3. Context là cơ sở để chọn convention

Convention không được chọn chỉ bằng tên class hoặc tên metric. Micrometer truyền `Observation.Context` cho `supportsContext` để xác định convention có áp dụng hay không.

Tạo một context riêng cho thao tác tính thuế:

~~~java
import io.micrometer.observation.Observation;

final class TaxContext extends Observation.Context {
    private final String taxType;
    private final String userId;

    TaxContext(String taxType, String userId) {
        this.taxType = taxType;
        this.userId = userId;
    }

    String getTaxType() {
        return taxType;
    }

    String getUserId() {
        return userId;
    }
}
~~~

Context mang dữ liệu mà convention cần để tạo key-value. Ví dụ `taxType` có tập giá trị hữu hạn như `income`, `vat`, `service`; `userId` có thể có số lượng giá trị rất lớn.

Khi đăng ký global convention, `supportsContext` có thể kiểm tra kiểu context:

~~~java
return context instanceof TaxContext;
~~~

Nhờ vậy, convention thuế không áp dụng nhầm cho Observation HTTP, database hoặc các context của instrumentation khác.

## 4. Default convention do instrumentation cung cấp

Instrumentation nên có một default convention để người dùng không phải tự cấu hình mọi Observation. Default convention định nghĩa tên ổn định và các key-value cơ bản có ý nghĩa với instrumentation.

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

interface TaxObservationConvention
        extends ObservationConvention<TaxContext> {

    @Override
    default boolean supportsContext(Observation.Context context) {
        return context instanceof TaxContext;
    }
}

class DefaultTaxObservationConvention
        implements TaxObservationConvention {

    @Override
    public String getName() {
        return "tax.calculate";
    }

    @Override
    public String getContextualName(TaxContext context) {
        return "calculate tax";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(TaxContext context) {
        return KeyValues.of(
                KeyValue.of("tax.type", context.getTaxType())
        );
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(TaxContext context) {
        return KeyValues.of(
                KeyValue.of("tax.user.id", context.getUserId())
        );
    }
}
~~~

Default convention thường do thư viện instrumentation tạo và truyền vào khi bắt đầu Observation. Ứng dụng có thể dùng nguyên bản hoặc thay thế bằng convention riêng.

Giữ default convention có ý nghĩa quan trọng: nếu ứng dụng không đăng ký custom hay global convention, instrumentation vẫn tạo Observation với tên và key-value nhất quán.

## 5. Đăng ký GlobalObservationConvention trên ObservationRegistry

`GlobalObservationConvention<T>` là convention dùng chung. Nó được đăng ký vào cấu hình của registry và chỉ được chọn khi `supportsContext` phù hợp.

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.GlobalObservationConvention;
import io.micrometer.observation.Observation;

final class GlobalTaxObservationConvention
        implements GlobalObservationConvention<TaxContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof TaxContext;
    }

    @Override
    public String getName() {
        return "tax.calculate.global";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(TaxContext context) {
        return KeyValues.of(
                KeyValue.of("tax.type", context.getTaxType()),
                KeyValue.of("application", "billing")
        );
    }
}
~~~

Đăng ký convention:

~~~java
ObservationRegistry observationRegistry = ObservationRegistry.create();

observationRegistry.observationConfig()
        .observationConvention(new GlobalTaxObservationConvention());
~~~

Global convention áp dụng cho mọi instrumentation dùng registry này và tạo context mà convention hỗ trợ. Nó là cách chia sẻ naming/tag policy giữa nhiều thành phần mà không cần truyền cùng một object convention vào từng lời gọi.

Không nên đăng ký một global convention có `supportsContext` trả về `true` cho mọi context nếu nó chỉ được thiết kế cho một loại Observation. Một convention quá rộng có thể ghi đè default convention của các instrumentation không liên quan.

## 6. Custom convention truyền trực tiếp có ưu tiên cao nhất

Custom convention được truyền trực tiếp khi tạo Observation:

~~~java
Observation.createNotStarted(
        customConvention,
        defaultConvention,
        () -> context,
        observationRegistry
).observe(this::calculateInterest);
~~~

Nếu `customConvention` khác null, Micrometer dùng nó ngay. Registry không tìm global convention cho lần tạo này và default convention cũng không được chọn.

Ví dụ custom convention kế thừa default để giữ lại các tag chuẩn rồi bổ sung hoặc điều chỉnh:

~~~java
final class CustomTaxObservationConvention
        extends DefaultTaxObservationConvention {

    @Override
    public String getName() {
        return "billing.tax.calculate";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(TaxContext context) {
        return super.getLowCardinalityKeyValues(context)
                .and(KeyValue.of("channel", "online"));
    }
}
~~~

Kế thừa default convention giúp tái sử dụng key-value đã có. Nếu custom convention triển khai trực tiếp interface và trả về bộ key-value mới, nó chịu trách nhiệm cung cấp đầy đủ những key-value mà instrumentation cần.

## 7. Minh họa cả ba cấp trong cùng một luồng

Tạo registry có global convention, sau đó tạo ba Observation với cấu hình khác nhau:

~~~java
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig()
        .observationConvention(new GlobalTaxObservationConvention());

TaxContext context = new TaxContext("income", "user-123");
DefaultTaxObservationConvention defaultConvention =
        new DefaultTaxObservationConvention();

// Không truyền custom: global convention được chọn.
Observation.createNotStarted(
        null,
        defaultConvention,
        () -> context,
        registry
).observe(this::calculateInterest);

// Truyền custom: custom convention thắng global convention.
Observation.createNotStarted(
        new CustomTaxObservationConvention(),
        defaultConvention,
        () -> context,
        registry
).observe(this::calculateInterest);
~~~

Nếu registry không có global convention phù hợp, lời gọi đầu tiên dùng `DefaultTaxObservationConvention`. Khi global convention được đăng ký và hỗ trợ `TaxContext`, lời gọi đầu tiên dùng global convention. Lời gọi thứ hai luôn dùng custom convention.

## 8. Khi có nhiều GlobalObservationConvention cùng hỗ trợ context

Registry có thể chứa nhiều global convention. Khi tìm convention phù hợp, Micrometer duyệt danh sách đã đăng ký và dùng convention đầu tiên có `supportsContext(context)` trả về `true`.

Điều này có nghĩa hai convention có điều kiện hỗ trợ chồng lấn có thể làm kết quả phụ thuộc thứ tự đăng ký:

~~~java
registry.observationConfig()
        .observationConvention(new SpecificTaxConvention())
        .observationConvention(new GeneralBusinessConvention());
~~~

Nếu cả hai đều hỗ trợ `TaxContext`, `SpecificTaxConvention` được chọn trước vì được đăng ký trước. Nên thiết kế `supportsContext` đủ cụ thể để các convention không tranh nhau cùng một loại context.

Một chiến lược dễ kiểm soát là:

- Global convention chuyên biệt kiểm tra context class hoặc interface cụ thể.
- Global convention dùng chung cho một họ context kiểm tra marker interface.
- Không đăng ký một convention tổng quát trước các convention chuyên biệt nếu nó sẽ nhận tất cả context.

Custom convention truyền trực tiếp vẫn thắng mọi global convention, không phụ thuộc thứ tự đăng ký.

## 9. Convention không tự động hợp nhất

Giả sử:

- Default convention thêm `tax.type`.
- Global convention thêm `application`.
- Custom convention thêm `channel`.

Không có quy tắc tự động tạo kết quả gồm cả ba key-value. Chỉ một convention được chọn, và bộ key-value của convention đó được dùng cho Observation.

Nếu custom convention chỉ trả `channel`, các key-value của global và default convention không tự được giữ lại. Muốn kết hợp, hãy chủ động:

1. Kế thừa default convention rồi bổ sung key-value.
2. Delegate đến convention khác rồi hợp nhất `KeyValues`.
3. Dùng `ObservationFilter` cho các key-value cần thêm bất kể convention nào được chọn.

Chọn cách kết hợp theo mục đích. Convention quyết định danh tính và bộ key-value của một loại Observation; filter phù hợp với dữ liệu chung của toàn registry.

## 10. Dùng ObservationFilter cho key-value dùng chung

`ObservationFilter` được gọi khi Observation dừng, trước khi các handler xử lý sự kiện `onStop`. Filter nhận context hiện tại, có thể thêm hoặc loại bỏ key-value rồi trả lại context.

Ví dụ, thêm cloud zone vào low cardinality và instance ID vào high cardinality cho mọi Observation:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;

final class CloudObservationFilter implements ObservationFilter {
    @Override
    public Observation.Context map(Observation.Context context) {
        context.addLowCardinalityKeyValue(
                KeyValue.of("cloud.zone", "ap-southeast-1a")
        );
        context.addHighCardinalityKeyValue(
                KeyValue.of("cloud.instance.id", "instance-42")
        );
        return context;
    }
}
~~~

Đăng ký:

~~~java
registry.observationConfig()
        .observationFilter(new CloudObservationFilter());
~~~

Filter được áp dụng bất kể custom, global hay default convention được chọn. Đây là điểm khác biệt cốt lõi: convention được chọn theo thứ tự ưu tiên; filter là bước biến đổi bổ sung trên context.

Nếu cần thêm tag chung cho tất cả Observation, filter thường là công cụ phù hợp hơn việc tạo một GlobalObservationConvention quá rộng.

## 11. Low cardinality và high cardinality vẫn phải tách biệt

Convention có thể cung cấp hai nhóm key-value:

| Nhóm | Đặc điểm | Ví dụ | Dùng trong metrics |
|---|---|---|---|
| Low cardinality | Tập giá trị hữu hạn, có giới hạn | `tax.type=income`, `channel=online`, `cloud.zone=ap-southeast-1a` | Có |
| High cardinality | Có thể có rất nhiều giá trị khác nhau | `tax.user.id=user-123`, `request.id=...`, `cloud.instance.id=...` | Không được đưa vào meter tags bởi DefaultMeterObservationHandler |

`DefaultMeterObservationHandler` dùng low-cardinality key-value để tạo metric tags. High-cardinality key-value không được đưa vào metrics vì có thể làm số lượng time series tăng rất lớn. Các tracing handler có thể sử dụng high-cardinality values cho span attributes.

Không chuyển user ID, order ID, session ID hoặc request ID sang low cardinality chỉ để nhìn thấy chúng trong metrics. Nếu cần tra cứu theo định danh, hãy dùng trace hoặc log.

## 12. ObservationFilter và convention có vai trò khác nhau

| Thành phần | Quyết định điều gì? | Thời điểm |
|---|---|---|
| Custom convention | Tên và key-value cho một lần tạo Observation | Khi tạo Observation |
| Global convention | Convention dùng chung cho context phù hợp | Khi tạo Observation |
| Default convention | Fallback do instrumentation cung cấp | Khi tạo Observation |
| ObservationFilter | Chỉnh sửa context, thêm/bớt key-value chung | Khi Observation dừng, trước handler onStop |
| ObservationPredicate | Cho phép hoặc bỏ qua Observation | Khi tạo Observation |

Không dùng ObservationFilter để thay thế việc chọn convention nếu mục tiêu là đổi tên Observation cho một loại instrumentation. Đổi tên nên thuộc convention. Không dùng convention toàn cục để thêm một tag giống nhau cho mọi loại context; filter phù hợp hơn.

## 13. ObservationPredicate không phải một cấp convention

`ObservationPredicate` quyết định Observation có được tạo thật hay trở thành no-op. Predicate có thể dựa trên tên hoặc context:

~~~java
registry.observationConfig()
        .observationPredicate((name, context) ->
                !"internal.noisy.operation".equals(name)
        );
~~~

Predicate không chọn giữa custom, global và default convention. Nó là một bước kiểm soát việc Observation có được bật hay không. Nếu predicate từ chối, các handler sẽ không ghi metrics hoặc tracing cho Observation no-op đó.

Khi debug một metric không xuất hiện, kiểm tra cả:

- Convention nào được chọn và tên Observation cuối cùng.
- Predicate có từ chối tên/context đó không.
- Handler cần thiết đã đăng ký trên registry chưa.
- Observation đã được start và stop đúng vòng đời chưa.

## 14. Thứ tự xử lý tổng thể

Luồng tạo và hoàn tất Observation có thể hiểu như sau:

~~~text
Instrumentation tạo Context
        |
        v
Chọn Convention
  1. Custom truyền trực tiếp
  2. Global hỗ trợ Context đầu tiên
  3. Default fallback
        |
        v
Predicate kiểm tra có bật Observation?
        |
        +---- Không ----> No-op Observation
        |
        v
Observation start / scope / event / error
        |
        v
Observation stop
        |
        v
ObservationFilter biến đổi Context
        |
        v
ObservationHandler xử lý onStop
        |
        v
Metrics / Tracing / Logging
~~~

Convention xác định metadata nền của Observation; predicate kiểm soát việc bật; filter bổ sung hoặc điều chỉnh context; handler tiêu thụ context theo mục đích của nó.

## 15. Tích hợp với ObservationDocumentation

Instrumentation có thể dùng `ObservationDocumentation` để khai báo tên và danh sách key-name được tài liệu hóa. Enum documentation thường cung cấp:

- Prefix của Observation.
- Contextual name.
- Low-cardinality key names.
- High-cardinality key names.
- Class của default convention.

Khi tạo Observation qua documentation, instrumentation truyền custom convention nếu có và default convention tương ứng. Micrometer vẫn áp dụng cùng thứ tự ưu tiên: custom, global phù hợp, rồi default.

Documentation giúp thống nhất key names và tạo tài liệu instrumentation. Nó không làm thay đổi quy tắc ưu tiên convention.

## 16. Kiểm thử thứ tự ưu tiên bằng SimpleMeterRegistry

Có thể đăng ký `DefaultMeterObservationHandler` để quan sát tên và low-cardinality tags được tạo thành Timer:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.DefaultMeterObservationHandler;

SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry observations = ObservationRegistry.create();
observations.observationConfig()
        .observationHandler(new DefaultMeterObservationHandler(meters));
~~~

Test fallback:

~~~java
Observation.createNotStarted(
        null,
        new DefaultTaxObservationConvention(),
        () -> new TaxContext("income", "user-123"),
        observations
).observe(() -> {});

assertThat(meters.find("tax.calculate").timer()).isNotNull();
~~~

Test global override:

~~~java
observations.observationConfig()
        .observationConvention(new GlobalTaxObservationConvention());

Observation.createNotStarted(
        null,
        new DefaultTaxObservationConvention(),
        () -> new TaxContext("income", "user-123"),
        observations
).observe(() -> {});

assertThat(meters.find("tax.calculate.global").timer()).isNotNull();
~~~

Test custom override:

~~~java
Observation.createNotStarted(
        new CustomTaxObservationConvention(),
        new DefaultTaxObservationConvention(),
        () -> new TaxContext("income", "user-123"),
        observations
).observe(() -> {});

assertThat(meters.find("billing.tax.calculate").timer()).isNotNull();
~~~

Trong test thực tế, nên tạo registry và meter registry mới cho từng trường hợp để tránh các meter đã đăng ký từ lần chạy trước ảnh hưởng kết quả. Cũng nên xác minh low-cardinality tags được chọn đúng và high-cardinality key-value không trở thành metric tags.

## 17. Kiểm thử nhiều global convention

Nếu nhiều global convention cùng có thể hỗ trợ một context, kiểm thử thứ tự đăng ký:

~~~java
ObservationRegistry registry = ObservationRegistry.create();
SimpleMeterRegistry meters = new SimpleMeterRegistry();
registry.observationConfig()
        .observationHandler(new DefaultMeterObservationHandler(meters))
        .observationConvention(new SpecificTaxConvention())
        .observationConvention(new GeneralBusinessConvention());
~~~

Tạo Observation với `TaxContext` rồi xác minh tên do `SpecificTaxConvention` cung cấp. Đổi thứ tự đăng ký trong một test khác để xác nhận convention đầu tiên phù hợp được chọn theo cấu hình hiện tại.

Đây là lý do nên thiết kế `supportsContext` không chồng lấn. Nếu thứ tự đăng ký không được kiểm soát, một convention tổng quát có thể vô tình che khuất convention chuyên biệt.

## 18. Những lỗi thường gặp

**Cho rằng global convention luôn thắng custom convention.** Custom convention truyền trực tiếp có ưu tiên cao nhất.

**Cho rằng default convention được hợp nhất với global.** Khi global phù hợp, nó thay thế default trong lần tạo đó. Muốn giữ default key-values, hãy kế thừa hoặc delegate.

**Đăng ký nhiều global convention có supportsContext quá rộng.** Convention phù hợp đầu tiên được chọn. Thu hẹp điều kiện hỗ trợ và kiểm soát thứ tự đăng ký.

**Dùng GlobalObservationConvention để thêm tag cho mọi Observation.** Nếu chỉ cần bổ sung key-value chung, dùng ObservationFilter.

**Đưa user ID vào low-cardinality key.** User ID có cardinality lớn; giữ nó ở high-cardinality cho tracing hoặc dùng log.

**Nghĩ high-cardinality key-value luôn xuất thành metric tag.** DefaultMeterObservationHandler chỉ dùng low-cardinality values cho meter.

**Dùng Predicate để thay convention.** Predicate chỉ quyết định Observation có được bật hay không; nó không thay tên hoặc key-value.

**Không truyền context khi convention cần contextual name.** Convention phải nhận context đúng kiểu để tạo contextual name và key-value.

**Đổi tên Observation trong filter.** Naming thuộc convention; filter dành cho biến đổi context và key-value.

## 19. Checklist chọn và cấu hình convention

Trước khi đưa quy ước vào ứng dụng, hãy xác minh:

- [ ] Instrumentation có default convention với tên và key-value ổn định.
- [ ] Custom convention chỉ được truyền khi cần override riêng cho instrumentation đó.
- [ ] Global convention đăng ký trên đúng ObservationRegistry.
- [ ] `supportsContext` kiểm tra đúng kiểu context cần áp dụng.
- [ ] Thứ tự custom > global phù hợp > default được hiểu rõ.
- [ ] Nhiều global convention không có điều kiện hỗ trợ chồng lấn ngoài chủ ý.
- [ ] Nếu custom cần giữ tag mặc định, nó kế thừa hoặc delegate đúng cách.
- [ ] Key-value dùng chung được thêm qua ObservationFilter.
- [ ] Low-cardinality values có tập giá trị hữu hạn.
- [ ] High-cardinality values không bị đưa vào metric tags.
- [ ] ObservationPredicate chỉ dùng để bật/tắt Observation.
- [ ] Có test xác minh tên, tags và convention được chọn.

## 20. Kết luận

Micrometer chọn đúng một ObservationConvention cho mỗi Observation. Custom convention truyền trực tiếp có độ ưu tiên cao nhất; nếu không có, registry chọn GlobalObservationConvention đầu tiên hỗ trợ context; nếu không tìm được global convention phù hợp, instrumentation dùng default convention.

Ba convention không tự động hợp nhất. Muốn giữ key-value của default khi custom override, hãy kế thừa hoặc delegate. Muốn bổ sung key-value cho mọi Observation bất kể convention được chọn, hãy dùng ObservationFilter. Giữ low-cardinality values cho metrics, high-cardinality values cho tracing và thiết kế `supportsContext` cụ thể sẽ giúp quy ước dễ dự đoán, nhất quán và tránh tăng cardinality không kiểm soát.

## Tài liệu tham khảo

- [Micrometer – Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer – ObservationConvention API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/ObservationConvention.html)
- [Micrometer – GlobalObservationConvention API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/GlobalObservationConvention.html)
- [Micrometer – ObservationRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/ObservationRegistry.html)
