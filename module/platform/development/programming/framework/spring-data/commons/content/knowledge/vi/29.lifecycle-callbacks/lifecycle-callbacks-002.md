# EntityCallbacks và ReactiveEntityCallbacks

## 1. Callback là một điểm can thiệp trong đường xử lý entity

Trong chương **Vòng đời và callback** của module **SPRING_DATA_COMMONS**, `EntityCallbacks` và `ReactiveEntityCallbacks` cung cấp cơ chế gọi callback theo kiểu entity và nhận lại kết quả xử lý.

Ví dụ, trước khi chuyển một đơn hàng thành dữ liệu lưu trữ, ứng dụng muốn chuẩn hóa mã tham chiếu:

~~~text
"  order-2025-001  " → "ORDER-2025-001"
~~~

Vấn đề không chỉ là gọi một hàm. Hạ tầng cần xác định callback nào áp dụng cho kiểu entity, thứ tự giữa các callback và cách chuyển kết quả sang bước kế tiếp. Với reactive, kết quả còn phải nằm trong một chuỗi Publisher thay vì bị xử lý tách rời.

Hai abstraction của Commons giải quyết việc điều phối đó. Các điểm vòng đời như before-convert hoặc before-save và chữ ký callback cụ thể do module Spring Data cung cấp.

Không nên suy ra rằng mọi lời gọi `save` trong mọi store đều đi qua cùng tập callback.

## 2. Ba thành phần cần phân biệt

| Thành phần | Vai trò |
| --- | --- |
| `EntityCallback<T>` | Marker interface chung cho callback gắn với kiểu entity `T` |
| Interface callback cụ thể | Định nghĩa phương thức, đối số bổ sung và kiểu kết quả của một điểm can thiệp |
| `EntityCallbacks` hoặc `ReactiveEntityCallbacks` | Tìm và gọi các callback phù hợp, truyền kết quả trong một lần dispatch |

`EntityCallback<T>` không tự định nghĩa một phương thức chung như `onSave(T)`. Interface con xác định phương thức cần gọi.

Ví dụ, hai module có thể đều có callback trước khi lưu nhưng nhận đối số khác nhau:

- Một module document có thể cung cấp document đã được chuyển đổi và tên collection.
- Một module relational có thể cung cấp thông tin thay đổi aggregate.
- Một interface do ứng dụng định nghĩa có thể nhận một nhãn ngữ cảnh riêng.

Không thể đổi import từ module này sang module khác rồi mặc định phương thức vẫn giống nhau.

### 2.1. Hai bộ điều phối

| Tiêu chí | EntityCallbacks | ReactiveEntityCallbacks |
| --- | --- | --- |
| Cách nhận kết quả dispatch | Entity trực tiếp | `Mono<T>` |
| Phương thức của callback cụ thể | Trả entity theo hợp đồng đồng bộ | Trả Publisher chứa entity theo hợp đồng reactive |
| Báo lỗi | Ném ngoại lệ | Phát tín hiệu lỗi trong pipeline; cũng cần tránh lỗi eager ngoài ý muốn |
| Cách nối các callback | Kết quả trước thành đầu vào sau | Kết quả reactive trước được nối vào bước sau |
| Đường persistence sử dụng | Hạ tầng đồng bộ có tích hợp | Hạ tầng reactive có tích hợp |

Cả hai dùng marker `EntityCallback<T>` trong mô hình callback của Commons. Tính reactive không xuất phát từ một annotation đặt lên một callback đồng bộ, mà từ interface callback và đường điều phối được sử dụng.

## 3. Luồng xử lý: entity trả về là dữ liệu của bước kế tiếp

Một lần dispatch có thể được hình dung như sau:

~~~mermaid
flowchart LR
    A["Entity đầu vào"] --> B["Chọn callback theo interface và kiểu entity"]
    B --> C["Callback thứ nhất"]
    C --> D["Entity kết quả thứ nhất"]
    D --> E["Callback tiếp theo"]
    E --> F["Entity kết quả cuối"]
    F --> G["Bước xử lý tiếp theo của caller"]
~~~

Entity đầu ra không bắt buộc phải là cùng một object với đầu vào.

Điều này quan trọng với mô hình immutable:

~~~text
order ban đầu
    → callback tạo order mới
    → store cần dùng order mới để tiếp tục
~~~

Nếu ứng dụng gọi callback nhưng bỏ qua giá trị trả về, thay đổi có thể bị mất.

Với callback đồng bộ, phương thức phải trả một entity hợp lệ theo hợp đồng. Nếu không cần thay đổi, trả chính entity đã nhận; không trả `null` để biểu thị “bỏ qua”.

Với callback reactive, trả một Publisher phát entity. Không dùng Publisher rỗng như cách mặc định để nói “không thay đổi”.

## 4. Ví dụ độc lập với store: callback đồng bộ

Phần này minh họa cách dùng bộ điều phối trực tiếp. Interface do ứng dụng định nghĩa không tự trở thành một điểm vòng đời của repository.

Khi áp dụng, mỗi public type được đặt trong một file Java riêng. Ví dụ dùng lớp immutable để làm rõ vai trò của kết quả trả về.

### 4.1. Entity minh họa

~~~java
import java.util.Objects;

public final class PurchaseOrder {

    private final String id;
    private final String reference;

    public PurchaseOrder(String id, String reference) {
        this.id = id;
        this.reference = Objects.requireNonNull(
                reference, "reference");
    }

    public String getId() {
        return id;
    }

    public String getReference() {
        return reference;
    }

    public PurchaseOrder withReference(String reference) {
        return new PurchaseOrder(id, reference);
    }
}
~~~

Lớp này phục vụ ví dụ dispatch. Việc mapping entity immutable, chọn constructor và gán ID khi persistence phải tuân theo khả năng của store thực tế.

### 4.2. Interface callback

~~~java
import org.springframework.data.mapping.callback.EntityCallback;

public interface NormalizeReferenceCallback<T>
        extends EntityCallback<T> {

    T onNormalizeReference(T entity, String logicalScope);
}
~~~

`logicalScope` là đối số do caller của ví dụ truyền vào. Commons không tự tìm tenant, request hay collection để gán vào đối số này.

### 4.3. Implementation có thứ tự

~~~java
import java.util.Locale;

import org.springframework.core.Ordered;

public final class OrderReferenceCallback
        implements NormalizeReferenceCallback<PurchaseOrder>, Ordered {

    @Override
    public PurchaseOrder onNormalizeReference(
            PurchaseOrder entity,
            String logicalScope) {

        String normalized = entity.getReference()
                .trim()
                .toUpperCase(Locale.ROOT);

        return entity.withReference(normalized);
    }

    @Override
    public int getOrder() {
        return -100;
    }
}
~~~

`Locale.ROOT` giúp phép chuẩn hóa kỹ thuật này không phụ thuộc locale mặc định của máy. Quy tắc chuẩn hóa chỉ là lựa chọn minh họa; ứng dụng cần dùng quy tắc đúng với mã tham chiếu của mình.

### 4.4. Gọi bộ điều phối

~~~java
import org.springframework.data.mapping.callback.EntityCallbacks;

public final class SynchronousCallbackExample {

    public PurchaseOrder normalize(PurchaseOrder input) {
        EntityCallbacks callbacks = EntityCallbacks.create(
                new OrderReferenceCallback());

        return callbacks.callback(
                NormalizeReferenceCallback.class,
                input,
                "manual-example");
    }
}
~~~

Nếu input có reference `"  order-2025-001  "`, kết quả trả về có reference `"ORDER-2025-001"`.

Đối tượng ban đầu vẫn giữ reference cũ vì callback tạo một bản sao.

Việc tạo dispatcher trong phương thức chỉ để ví dụ dễ đọc. Trong ứng dụng, có thể cấu hình và tái sử dụng một dispatcher phù hợp, thay vì tạo lại registry cho từng entity.

Quan trọng hơn, đoạn mã này là lời gọi chủ động của ứng dụng. Repository sẽ không tự gọi `NormalizeReferenceCallback` chỉ vì interface đó kế thừa `EntityCallback`.

## 5. Đăng ký callback và phát hiện kiểu entity

Có hai hướng sử dụng cần tách biệt:

1. **Dispatch do ứng dụng chủ động:** tạo registry với callback cụ thể rồi gọi `callback(...)`.
2. **Lifecycle của store:** đăng ký implementation của interface mà module đó thực sự gọi trong pipeline.

Hạ tầng có thể khám phá callback từ bean trong Spring container khi được cấu hình tương ứng. Tạo một dispatcher riêng không tự thay dispatcher mà store đang dùng.

Khi callback được chọn theo kiểu entity, thông tin generic giúp giới hạn phạm vi:

~~~text
BeforeConvertCallback<PurchaseOrder>
~~~

khác về ý định với:

~~~text
BeforeConvertCallback<Object>
~~~

Một callback khai báo cho `Object` có thể có phạm vi rất rộng. Chỉ nên dùng khi thực sự muốn xử lý nhiều loại entity và đã kiểm soát các điều kiện áp dụng.

### 5.1. Ưu tiên implementation có thông tin kiểu rõ ràng

Lớp hoặc enum triển khai interface callback cụ thể thường giúp framework xác định kiểu entity dễ hơn.

Lambda có thể làm thông tin generic khó suy ra từ lớp runtime. Điều này có thể ảnh hưởng khả năng lọc callback và chi phí dispatch.

Không nên mặc định rằng một lambda được gán cho biến có generic ở mã nguồn luôn để lại đầy đủ metadata generic cho cơ chế khám phá bean.

Các ví dụ trong bài dùng lớp có tên để thể hiện rõ interface, kiểu entity và thứ tự.

### 5.2. Đối số phải đúng với phương thức callback

Khi dispatch trực tiếp, caller phải cung cấp các đối số bổ sung theo chữ ký interface:

~~~java
callbacks.callback(
        NormalizeReferenceCallback.class,
        order,
        "orders");
~~~

Chuỗi `"orders"` ở đây chỉ là nhãn logic. Nó không tự trở thành tên collection được store xác thực.

Đừng đưa đối số của một callback MongoDB vào interface JDBC hoặc interface tự định nghĩa chỉ vì chúng cùng diễn ra “trước lưu”.

## 6. Thứ tự callback và giới hạn của thứ tự đó

Callback có thể khai báo thứ tự bằng cơ chế của Spring, chẳng hạn triển khai `Ordered` hoặc dùng `@Order` khi được hạ tầng hỗ trợ.

Giá trị order nhỏ hơn có ưu tiên chạy trước.

Ví dụ trong một lần dispatch:

~~~text
-100: chuẩn hóa reference
   0: kiểm tra reference sau chuẩn hóa
 100: bổ sung thông tin dẫn xuất
~~~

Như vậy, callback kiểm tra có thể nhận entity đã được callback chuẩn hóa trả về.

Nếu hai callback có cùng order, không nên dựa vào một thứ tự tương đối chưa được cam kết. Hãy đặt thứ tự khác nhau khi logic có phụ thuộc.

Có ba ranh giới quan trọng:

- Order trong một nhóm callback không tự sắp lại các giai đoạn before-convert và before-save.
- Order của callback không mặc định dùng chung với order của application event listener.
- Order trong một thao tác không tuần tự hóa các yêu cầu persistence chạy đồng thời.

Nếu callback B luôn cần kết quả của A, cần kiểm tra cả thứ tự và việc caller tiếp tục bằng entity trả về, thay vì chỉ dựa vào thay đổi trên object gốc.

## 7. Ví dụ reactive: Publisher phải chứa entity kết quả

Với reactive, không đổi callback đồng bộ thành reactive bằng cách gọi `subscribe()` bên trong nó.

Cần một interface có hợp đồng trả Publisher và một đường dispatch reactive.

### 7.1. Interface reactive riêng của ví dụ

~~~java
import org.reactivestreams.Publisher;
import org.springframework.data.mapping.callback.EntityCallback;

public interface ReactiveNormalizeReferenceCallback<T>
        extends EntityCallback<T> {

    Publisher<T> onNormalizeReference(
            T entity, String logicalScope);
}
~~~

Interface này vẫn dùng marker `EntityCallback<T>`. Phương thức trả Publisher và caller dùng `ReactiveEntityCallbacks`.

### 7.2. Implementation không block

~~~java
import java.util.Locale;

import reactor.core.publisher.Mono;

public final class ReactiveOrderReferenceCallback
        implements ReactiveNormalizeReferenceCallback<PurchaseOrder> {

    @Override
    public Mono<PurchaseOrder> onNormalizeReference(
            PurchaseOrder entity,
            String logicalScope) {

        return Mono.fromSupplier(() -> {
            String normalized = entity.getReference()
                    .trim()
                    .toUpperCase(Locale.ROOT);

            return entity.withReference(normalized);
        });
    }
}
~~~

`Mono<PurchaseOrder>` là một kiểu trả về cụ thể phù hợp với hợp đồng `Publisher<PurchaseOrder>`.

`Mono.fromSupplier(...)` trì hoãn phần chuẩn hóa đến khi publisher đó được thực thi theo subscription. Ví dụ không thực hiện I/O.

### 7.3. Giữ kết quả trong pipeline

~~~java
import org.springframework.data.mapping.callback.ReactiveEntityCallbacks;

import reactor.core.publisher.Mono;

public final class ReactiveCallbackExample {

    private final ReactiveEntityCallbacks callbacks =
            ReactiveEntityCallbacks.create(
                    new ReactiveOrderReferenceCallback());

    public Mono<PurchaseOrder> normalize(PurchaseOrder input) {
        return callbacks.callback(
                ReactiveNormalizeReferenceCallback.class,
                input,
                "manual-example");
    }
}
~~~

Caller tiếp tục trả hoặc nối `Mono` này vào pipeline của mình.

Chỉ tạo một `Mono` chưa đủ để chứng minh thao tác đã hoàn tất. Luồng reactive cần được subscribe ở ranh giới phù hợp, chẳng hạn do web framework hoặc thành phần điều phối ứng dụng thực hiện.

Interface reactive tự định nghĩa ở đây cũng không tự được store gọi. Nó minh họa cơ chế điều phối độc lập với điểm vòng đời của module.

## 8. Những quy tắc quan trọng của callback reactive

### 8.1. Không subscribe nội bộ

Mẫu sau làm công việc rời khỏi chuỗi xử lý chính:

~~~java
auditService.record(entity).subscribe();
return Mono.just(entity);
~~~

Khi đó caller có thể nhận entity trước khi `record` hoàn tất. Lỗi của công việc phụ cũng không còn được truyền theo cùng pipeline.

Nếu công việc thực sự thuộc callback, cần nối nó vào publisher trả về:

~~~java
return auditService.record(entity)
        .thenReturn(entity);
~~~

Đoạn này giả định `record` trả về một publisher hoàn tất khi tác vụ cần thiết đã xong. Nó chỉ minh họa cách composition, không khẳng định việc gọi dịch vụ bên ngoài là phù hợp ở mọi callback.

### 8.2. Không block để lấy kết quả

Gọi `block()` trong callback reactive có thể chặn luồng xử lý, phá mô hình thực thi và gây vấn đề khi luồng không cho phép blocking.

Đổi kiểu trả về thành `Mono` không làm một lời gọi JDBC hoặc HTTP đồng bộ bên trong trở thành nonblocking.

Nếu còn phụ thuộc blocking, cần một thiết kế tích hợp và bố trí thực thi phù hợp. Không xem việc bọc tùy ý bằng `Mono.just(...)` là đã xử lý xong vấn đề.

### 8.3. Không trả publisher rỗng để nói “giữ nguyên”

Nếu không thay đổi entity:

~~~java
return Mono.just(entity);
~~~

Không dùng:

~~~java
return Mono.empty();
~~~

Publisher rỗng không phát entity để truyền sang callback hoặc bước lưu kế tiếp. Không nên dựa vào một hành vi fallback chưa được cam kết.

Tương tự, `then()` làm mất giá trị entity. Khi cần đợi một bước hoàn tất rồi trả lại entity, có thể dùng `thenReturn(entity)` nếu đúng ngữ nghĩa.

Hợp đồng callback là một entity kết quả cho một entity đầu vào. Không dùng một `Flux` phát nhiều entity để nhân bản thao tác lưu.

### 8.4. Đặt phần việc cần trì hoãn đúng chỗ

Hai đoạn sau không có cùng thời điểm thực hiện công việc:

~~~java
return Mono.just(normalize(entity));
~~~

~~~java
return Mono.fromSupplier(() -> normalize(entity));
~~~

Đoạn đầu gọi `normalize` khi biểu thức Java được thực thi để tạo publisher. Đoạn sau gọi supplier khi publisher đó được subscribe.

Nếu cần truy cập context theo subscription hoặc trì hoãn phần việc có thể ném ngoại lệ, chọn composition tương ứng thay vì tạo kết quả quá sớm.

Callback phải bảo đảm kết quả không null. Supplier trả null có thể tạo một publisher không phát giá trị, làm mất entity trong chuỗi.

### 8.5. Retry và subscribe lại có thể chạy công việc lại

Một pipeline lạnh có thể được subscribe nhiều lần. Việc retry ở phạm vi bao gồm callback cũng có thể chạy lại callback.

Chuẩn hóa chuỗi theo cùng quy tắc thường dễ thiết kế theo tính idempotent:

~~~text
normalize(normalize(value)) = normalize(value)
~~~

Ngược lại, gửi thông báo, tăng bộ đếm bên ngoài hoặc tạo tài nguyên mới có thể lặp lại nếu callback được chạy lại.

Không nên mặc định callback chỉ được thực thi đúng một lần trong toàn bộ vòng đời một entity.

## 9. Ví dụ tích hợp store: before-convert của MongoDB

Hai ví dụ tiếp theo sử dụng interface thật của Spring Data MongoDB. Chúng minh họa implementation callback, chưa cung cấp toàn bộ cấu hình MongoDB hoặc mapping immutable entity của một ứng dụng.

Callback đồng bộ và reactive là hai interface khác nhau. Chọn implementation tương ứng với pipeline MongoDB mà ứng dụng sử dụng.

### 9.1. Callback đồng bộ

~~~java
import java.util.Locale;

import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public final class MongoOrderBeforeConvert
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(
            PurchaseOrder entity,
            String collection) {

        String normalized = entity.getReference()
                .trim()
                .toUpperCase(Locale.ROOT);

        return entity.withReference(normalized);
    }
}
~~~

Khi hạ tầng MongoDB tương ứng phát hiện bean và gọi điểm before-convert cho entity này, entity trả về được dùng trong đường xử lý tiếp theo.

`collection` là đối số do điểm tích hợp MongoDB cung cấp. Nó không phải một đối số có sẵn trong mọi callback của Commons.

### 9.2. Callback reactive

~~~java
import java.util.Locale;

import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class ReactiveMongoOrderBeforeConvert
        implements ReactiveBeforeConvertCallback<PurchaseOrder> {

    @Override
    public Mono<PurchaseOrder> onBeforeConvert(
            PurchaseOrder entity,
            String collection) {

        return Mono.fromSupplier(() -> {
            String normalized = entity.getReference()
                    .trim()
                    .toUpperCase(Locale.ROOT);

            return entity.withReference(normalized);
        });
    }
}
~~~

Đăng ký một `BeforeConvertCallback` đồng bộ không có nghĩa reactive template sẽ tự chuyển nó thành `ReactiveBeforeConvertCallback`. Chiều ngược lại cũng không tự xảy ra.

Nếu ứng dụng dùng cả hai đường truy cập, cần cấu hình và kiểm chứng từng đường. Có thể dùng chung một hàm chuẩn hóa thuần để tránh lặp quy tắc, nhưng vẫn cần adapter theo đúng interface.

### 9.3. Before-convert và before-save không tương đương

Với MongoDB, trước-convert là nơi thuận tiện để thay đổi giá trị domain trước khi nó được chuyển thành `Document`.

Ở before-save, document lưu trữ đã được tạo. Chữ ký callback của module có thể cung cấp cả entity và document để xử lý.

Vì vậy:

- Thay entity trước conversion cho phép conversion nhìn thấy giá trị mới.
- Thay entity khi document đã được tạo không tự chứng minh document cũng thay đổi.
- Thay document trực tiếp cần giữ rõ quan hệ giữa dữ liệu lưu và entity trả về.

Ví dụ này giải thích vì sao phải chọn đúng điểm vòng đời. Nó không đặt ra một chữ ký before-save chung cho JDBC, R2DBC hoặc các store khác.

## 10. Phạm vi hỗ trợ theo module và đường thao tác

| Hạ tầng | Cách đọc đúng về callback |
| --- | --- |
| Spring Data Commons | Cung cấp marker và bộ điều phối; không tự nối mọi repository vào mọi callback |
| Spring Data MongoDB | Có callback theo giai đoạn mapping, với interface đồng bộ và reactive tương ứng |
| Spring Data JDBC | Có các điểm callback trong đường xử lý aggregate; chữ ký và ngữ nghĩa thuộc module relational |
| Spring Data R2DBC | Có các điểm callback reactive theo đường persistence của module |
| Spring Data JPA | Lifecycle như `@PrePersist` và entity listener do JPA provider xử lý; không đồng nhất với dispatch của Commons |
| Các module khác | Phải kiểm tra interface, giai đoạn và thao tác được tích hợp ở module thực tế |

Không nên tạo một implementation của `EntityCallback` rồi mặc định nó sẽ được gọi chỉ vì repository kế thừa `CrudRepository`.

`CrudRepository` và `ReactiveCrudRepository` mô tả hợp đồng truy cập dữ liệu. Store implementation và pipeline cụ thể quyết định các điểm callback.

### 10.1. Bulk update có thể không materialize từng entity

Một câu lệnh update trực tiếp theo điều kiện có thể không tạo từng entity trong bộ nhớ. Khi đó không nên kỳ vọng callback dựa trên chuyển đổi entity sẽ chạy giống `save(entity)`.

Các đường thao tác cần xem riêng bao gồm:

- Save hoặc insert entity.
- Save nhiều entity.
- Update bằng câu lệnh hay API điều kiện.
- Delete theo entity hoặc theo ID.
- Bulk operation.
- Đọc entity, DTO hoặc projection.

Danh sách này không khẳng định tất cả đường trên đều có hoặc đều không có callback. Nó nhắc rằng mỗi đường cần được kiểm tra theo module.

### 10.2. Callback của aggregate root không bảo đảm callback cho mọi object con

Một aggregate có thể chứa nhiều object lồng nhau. Store không nhất thiết dispatch callback riêng cho từng object trong toàn bộ đồ thị.

Nếu cần chuẩn hóa dữ liệu con, có thể thực hiện quy tắc ở aggregate hoặc một hàm domain rõ ràng, thay vì mặc định mọi object lồng nhau đều là mục tiêu lifecycle độc lập.

## 11. Callback, application event và domain event

Ba cơ chế có thể xuất hiện cùng một ứng dụng nhưng có mục đích khác nhau.

| Cơ chế | Điểm cần nhớ |
| --- | --- |
| Entity callback | Tham gia pipeline có hợp đồng nhận lại entity hoặc Publisher entity |
| Application event của store | Thông báo sự kiện theo cơ chế sự kiện và đường phát của module |
| Domain event của aggregate | Biểu diễn điều đã xảy ra ở mức nghiệp vụ theo cơ chế publication được cấu hình |

Application event listener không mặc nhiên có cùng hợp đồng biến đổi entity với callback.

Nếu application event multicaster được cấu hình bất đồng bộ, không thể mặc định listener đã hoàn tất trước khi đường lưu tiếp tục. Entity callbacks thích hợp khi cần một bước nằm trong chuỗi xử lý và cần sử dụng entity trả về.

Một số module vẫn có cả sự kiện mapping và entity callbacks. Không nên đăng ký cùng một quy tắc ở cả hai rồi mặc định nó chỉ chạy một lần.

Cũng không dùng `@Order` của listener để suy ra thứ tự chung giữa mọi event và callback. Phải xem pipeline của module.

## 12. After-save không đồng nghĩa transaction đã commit

Một callback sau lưu thường nói về một điểm trong thao tác persistence của store. Nó không tự bảo đảm transaction bao quanh đã commit thành công.

Tình huống có thể xảy ra:

1. Một thao tác lưu hoàn tất bước ghi trong transaction.
2. Callback hoặc phần code tiếp theo chạy.
3. Một lỗi khác khiến transaction rollback.

Nếu đã gửi email hoặc gọi dịch vụ ngoài ở bước 2, rollback database không tự thu hồi tác động bên ngoài.

Vì vậy, cần chọn cơ chế theo mục tiêu:

- Thay đổi entity trước persistence: dùng callback phù hợp nếu đường store hỗ trợ.
- Chỉ thực hiện sau commit: dùng cơ chế gắn với transaction completion phù hợp.
- Bảo đảm ghi nhận yêu cầu phát sự kiện cùng dữ liệu: cân nhắc thiết kế outbox và xử lý publication riêng.

Các lựa chọn này vẫn cần cấu hình transaction và đường I/O thực tế. Callback không tự mở transaction, không tự làm nhiều hệ thống trở thành một giao dịch.

Với reactive cũng tương tự: một publisher hoàn tất tại điểm callback không phải cam kết rằng toàn bộ transaction ứng dụng đã commit.

## 13. Auditing và các callback tùy chỉnh

Auditing có thể được tích hợp bằng callback của store hoặc cơ chế lifecycle khác tùy module.

Khi dùng `@CreatedDate`, `@LastModifiedDate` hoặc thông tin người tạo, cần bật và cấu hình auditing tương ứng. Thêm một callback tùy chỉnh không tự bật auditing.

Nếu callback của ứng dụng phụ thuộc một field auditing:

1. Xác định auditing diễn ra ở giai đoạn nào.
2. Kiểm tra thứ tự với callback cùng giai đoạn nếu có.
3. Bảo đảm callback dùng entity đã được bước trước trả về.
4. Không dựa vào order của một module khác.

Không nên tự đặt lại thời gian tạo ở mọi before-save nếu auditing đang quản lý field đó. Hai cơ chế cùng ghi một field có thể tạo kết quả khó dự đoán.

Với reactive auditing, nguồn người dùng cũng cần được giải quyết trong reactive context theo cấu hình của module. Đọc người dùng từ một biến thread-local không tự bảo đảm đúng khi pipeline chuyển luồng.

## 14. Lỗi, đồng thời và trách nhiệm của callback

### 14.1. Lỗi phải đi theo hợp đồng của pipeline

Callback đồng bộ có thể từ chối dữ liệu bằng ngoại lệ. Callback reactive nên phát lỗi trong publisher khi điều kiện xử lý không thỏa mãn.

Không nên nuốt mọi lỗi rồi trả entity gốc nếu quy tắc đó là bắt buộc. Ví dụ, chuẩn hóa thất bại hoặc thiếu metadata cần thiết không nên bị biến thành một lần lưu có vẻ thành công.

Một lỗi callback không tự đảo ngược mọi tác động đã xảy ra trước đó. Khả năng rollback phụ thuộc transaction, store và các tài nguyên đã tham gia.

### 14.2. Callback bean nên tránh trạng thái theo request

Callback thường có thể được dùng bởi nhiều thao tác đồng thời. Không giữ entity hiện tại hoặc tenant hiện tại trong field mutable của một bean dùng chung.

Trạng thái an toàn hơn là cấu hình immutable được inject vào constructor.

Nếu cần dữ liệu theo subscription trong reactive, có thể dùng cơ chế Reactor Context ở đúng ranh giới. Context đó phải được caller đưa vào; dispatcher không tự tạo tenant hoặc người dùng hiện tại.

Ví dụ khung truy cập context trong một callback reactive:

~~~java
return Mono.deferContextual(context -> {
    if (!context.hasKey("operationSource")) {
        return Mono.error(
                new IllegalStateException(
                        "Missing operationSource"));
    }

    return Mono.just(entity);
});
~~~

Ví dụ chỉ minh họa việc đọc context tại subscription. Trong ứng dụng, cần quyết định rõ kiểu dữ liệu của key, nơi ghi context và cách xử lý thiếu context.

Không dùng các biến context tùy ý như bằng chứng người dùng đã được xác thực.

### 14.3. Immutable entity giúp kiểm soát việc tái sử dụng

Nếu hai pipeline cùng dùng một object mutable, callback thay đổi object đó có thể tạo tương tác ngoài ý muốn.

Trả một bản sao immutable giúp dữ liệu đầu vào và đầu ra rõ ràng hơn. Caller vẫn phải tiếp tục bằng bản sao trả về.

Callback cũng không thay thế việc entity giữ các invariant quan trọng. Nếu một quy tắc domain phải luôn đúng, cần thiết kế nó ở domain hoặc tầng nghiệp vụ phù hợp, đặc biệt khi có đường cập nhật bỏ qua callback.

## 15. Liên hệ với repository, query và projection

### 15.1. Dùng kết quả save

Ngoài kết quả callback, caller cũng cần dùng kết quả persistence:

~~~java
PurchaseOrder saved = repository.save(order);
~~~

Tham chiếu `saved` có thể mang các giá trị hoặc bản sao mà pipeline trả về. Không nên mặc định mọi thay đổi đều xuất hiện trên `order` ban đầu.

Với repository reactive:

~~~java
return repository.save(order);
~~~

Giữ kết quả đó trong pipeline. Mẫu `thenReturn(order)` sau save có thể làm caller nhận lại object đầu vào thay vì entity mà persistence trả về.

Các đoạn này giả định repository đã được cấu hình cho domain và store tương ứng; chúng không tạo một repository hoạt động chỉ từ dispatcher của Commons.

### 15.2. Derived query cần cùng quy ước dữ liệu

Nếu callback chuẩn hóa reference thành chữ hoa trước khi lưu, tham số tìm kiếm cũng cần được xử lý theo hợp đồng query của ứng dụng.

Callback trước ghi không tự chuẩn hóa mọi tham số của `findByReference(...)`.

Cũng cần xem tác động đến dữ liệu cũ: thêm callback hôm nay không tự sửa những bản ghi đã lưu trước đó.

### 15.3. Phân trang và sort

Callback có thể bổ sung giá trị dùng để sort khi ghi. Tuy nhiên, nó không tự tạo index hoặc bảo đảm thứ tự ổn định cho phân trang.

Nếu giá trị được tính lại khi đọc, việc đó không có nghĩa store đã sắp xếp theo giá trị mới. Sort ở database diễn ra theo dữ liệu và biểu thức query mà store thực sự dùng.

### 15.4. Projection và Query by Example

Một query trả DTO hoặc projection có thể đi qua đường mapping khác với query trả entity đầy đủ. Không mặc định mọi callback của entity đều áp dụng cho từng dạng kết quả.

Query by Example dùng probe và matcher theo khả năng store. Callback lưu entity không tự biến probe thành một bản đã chuẩn hóa.

Nếu quy tắc chuẩn hóa cần dùng chung cho ghi, tìm kiếm và probe, nên tách một hàm quy tắc thuần rồi gọi ở đúng các điểm, thay vì kỳ vọng callback được thực hiện ở mọi đường.

## 16. Cách kiểm chứng theo hợp đồng

Không chỉ kiểm tra rằng một callback đã được gọi. Cần kiểm tra entity nào được truyền tiếp và dữ liệu nào thực sự đi vào store.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Callback trả một bản sao | Bước tiếp theo nhận bản sao, object cũ không bị dùng nhầm |
| Có hai callback theo thứ tự | Callback sau thấy kết quả callback trước |
| Kiểu entity không thuộc phạm vi | Callback không bị áp dụng ngoài ý định |
| Không thay đổi dữ liệu | Callback vẫn trả entity hợp lệ |
| Callback đồng bộ ném lỗi | Đường persistence báo lỗi đúng hợp đồng |
| Callback reactive trả lỗi | Lỗi được truyền trong pipeline, không bị subscribe tách rời |
| Publisher chưa được subscribe | Không suy ra công việc đã hoàn tất |
| Retry hoặc subscribe lại | Tác động lặp được kiểm soát |
| Đọc context theo subscription | Context đúng với từng pipeline, không bị giữ nhầm trong field |
| Save entity qua repository thật | Store sử dụng callback đã cấu hình |
| Update trực tiếp hoặc bulk | Xác định rõ có đi qua callback hay không |
| Auditing và callback tùy chỉnh | Giai đoạn và thứ tự cho kết quả mong muốn |
| Transaction rollback sau save | Tác động ngoài database không bị hiểu nhầm là đã rollback theo |
| Projection hoặc DTO | Không suy rộng callback từ đường trả entity đầy đủ |

Có hai mức kiểm chứng khác nhau:

- Dispatch độc lập xác minh lựa chọn callback, thứ tự và việc truyền entity kết quả.
- Tích hợp store xác minh điểm vòng đời, conversion, dữ liệu lưu và các đường truy cập thực tế.

Một lời gọi dispatcher thành công chưa chứng minh repository sử dụng registry đó.

Các đoạn mã trong bài là ví dụ minh họa. Chúng không phải báo cáo đã chạy kiểm thử, khởi động store hoặc xác nhận cấu hình của một dự án cụ thể.

## 17. Chẩn đoán các lỗi thường gặp

| Biểu hiện | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Callback không chạy khi save | Sai interface, thiếu đăng ký hoặc đường thao tác không tích hợp | Kiểm tra store, pipeline và cách khám phá callback |
| Callback tự định nghĩa không chạy tự động | Chưa có caller dispatch interface đó | Gọi chủ động hoặc tích hợp vào adapter của ứng dụng |
| Callback chạy nhưng giá trị không được lưu | Bỏ qua entity trả về hoặc chọn giai đoạn sau conversion | Kiểm tra entity tiếp tục và biểu diễn lưu trữ |
| Reactive không có tác động | Publisher chưa được subscribe hoặc không được nối vào pipeline | Trả publisher qua đúng ranh giới xử lý |
| Lưu hoàn tất trước tác vụ phụ | Có subscribe nội bộ | Nối tác vụ vào publisher trả về nếu nó thuộc hợp đồng callback |
| Entity biến mất trong chuỗi | Publisher rỗng, supplier trả null hoặc dùng then làm mất giá trị | Bảo đảm phát entity kết quả |
| Quy tắc chạy hai lần | Đăng ký cả event listener và callback, hoặc retry | Loại bỏ xử lý trùng và kiểm tra tính idempotent |
| Callback áp dụng quá rộng | Generic quá rộng hoặc khó suy ra kiểu implementation | Dùng lớp có kiểu entity cụ thể |
| Hai thao tác làm lẫn dữ liệu | Callback giữ trạng thái mutable theo request | Dùng trạng thái immutable và context đúng phạm vi |
| After-save đã gửi thông báo nhưng transaction rollback | Nhầm điểm lifecycle với after-commit | Chọn cơ chế transaction completion hoặc outbox thích hợp |

Không nên giải quyết lỗi bằng cách gọi lại `repository.save(...)` từ callback đang nằm trong chính đường save nếu chưa có thiết kế rõ ràng. Cách đó có thể tạo đệ quy, lặp tác động hoặc thêm lần ghi ngoài dự kiến.

## 18. Tự kiểm tra kiến thức

**EntityCallback có phải một interface chứa sẵn phương thức onSave không?**

Không. Nó là marker có generic entity. Interface callback cụ thể định nghĩa phương thức và đối số.

**Vì sao callback được phép trả một entity mới?**

Để bước xử lý tiếp theo có thể dùng kết quả biến đổi, kể cả với entity immutable. Vì vậy phải giữ và truyền giá trị trả về.

**Tự định nghĩa callback interface có làm repository gọi nó không?**

Không. Cần một caller dispatch interface đó. Lifecycle của store chỉ tích hợp những điểm được module hỗ trợ.

**Callback đồng bộ có tự chạy trong pipeline reactive không?**

Không mặc định. Phải dùng interface và đường điều phối phù hợp với store reactive.

**Vì sao không dùng Mono.empty khi không có thay đổi?**

Vì chuỗi cần một entity để tiếp tục. Hãy phát chính entity nhận vào nếu không cần thay đổi.

**Order có bảo đảm hai request không chạy đồng thời không?**

Không. Nó sắp thứ tự callback trong phạm vi dispatch, không khóa toàn bộ ứng dụng.

**Before-save có luôn thích hợp để thay một field domain không?**

Không. Nếu biểu diễn lưu trữ đã được tạo, đổi entity chưa chắc đổi dữ liệu sắp ghi. Cần chọn giai đoạn và hợp đồng của store.

**After-save có nghĩa transaction đã commit không?**

Không. Transaction bao quanh có thể chưa hoàn tất. Tác động cần xảy ra sau commit phải dùng cơ chế phù hợp với transaction.

**Điều gì cần nhớ khi dùng callback cùng các abstraction của Commons?**

Callback điều phối việc xử lý entity tại những điểm được tích hợp. Repository, derived query, projection, phân trang, Query by Example và auditing vẫn có đường xử lý và giới hạn riêng theo store.
