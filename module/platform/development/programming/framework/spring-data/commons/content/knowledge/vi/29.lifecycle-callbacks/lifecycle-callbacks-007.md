# Phân biệt callback đồng bộ với reactive

## 1. Khác biệt nằm ở hợp đồng thực thi

Trong chương **Vòng đời và callback** của **SPRING_DATA_COMMONS**, callback đồng bộ và callback reactive cùng giúp can thiệp vào quá trình xử lý entity, nhưng chúng có cách cung cấp kết quả và truyền lỗi khác nhau.

Với callback đồng bộ, hạ tầng gọi phương thức và nhận entity kết quả khi phương thức trả về. Với callback reactive, phương thức cung cấp một publisher; hạ tầng cần nối publisher đó vào pipeline để nhận entity trước khi tiếp tục các bước phụ thuộc.

Không thể đổi một callback đồng bộ thành reactive chỉ bằng cách chạy nó trên thread khác. Cũng không thể biến một callback reactive thành đồng bộ chỉ bằng cách gọi `subscribe()` rồi trả ngay entity đầu vào.

Bài này tập trung vào các câu hỏi:

- Khi nào logic callback thực sự được thực hiện?
- Entity mới đi tiếp trong pipeline bằng cách nào?
- Vì sao `block()`, `subscribe()` riêng và publisher rỗng dễ làm sai hợp đồng?
- Thứ tự, lỗi, retry, ngữ cảnh và transaction khác nhau ra sao?
- Phải kiểm chứng những gì trên đúng module Spring Data?

## 2. Commons cung cấp SPI, module store quyết định điểm gọi

`EntityCallback<T>` thuộc package:

```java
import org.springframework.data.mapping.callback.EntityCallback;
```

Đây là marker interface. Nó không tự khai báo một phương thức save chung cho mọi database. Các module store cung cấp callback cụ thể, chẳng hạn callback trước conversion hoặc sau save, với chữ ký phù hợp.

Commons có các abstraction điều phối như `EntityCallbacks` và `ReactiveEntityCallbacks`. Việc repository/template gọi chúng ở đâu thuộc về module và đường thao tác đang dùng.

Ví dụ trong **Spring Data MongoDB**:

| Pipeline | Interface trước conversion | Kết quả callback |
| --- | --- | --- |
| Đồng bộ | `BeforeConvertCallback<T>` | Entity `T` |
| Reactive | `ReactiveBeforeConvertCallback<T>` | `Publisher<T>`, có thể triển khai bằng `Mono<T>` |

Các tên này nằm trong package callback của MongoDB. Không lấy nguyên interface đó để cấu hình JDBC, R2DBC hoặc JPA rồi kỳ vọng cùng hành vi.

Với module hỗ trợ cả hai API, cần chọn đúng họ callback cho pipeline. Callback đồng bộ không tự được chuyển thành callback reactive, và callback reactive không tự được thực thi bởi template đồng bộ.

## 3. Bảng so sánh các khác biệt chính

| Khía cạnh | Callback đồng bộ | Callback reactive |
| --- | --- | --- |
| Giá trị trả về | Entity trực tiếp | Publisher mang entity kết quả |
| Điều kiện để bước sau nhận kết quả | Phương thức trả về thành công | Publisher được nối và phát kết quả theo hợp đồng |
| Logic được trì hoãn | Do code gọi quyết định | Có thể đặt trong publisher để thực hiện khi subscribe |
| Lỗi | Thường qua exception tại lời gọi | Qua error signal trong chuỗi, hoặc lỗi khi tạo publisher nếu code tính sớm |
| Thread | Theo lời gọi và cấu hình thực thi | Theo pipeline và scheduler; không tự có thread mới |
| I/O | Có thể là API blocking trong stack đồng bộ | Cần compose API phù hợp, tránh chặn luồng reactive |
| Ngữ cảnh thao tác | Theo cơ chế của stack đồng bộ | Cần xét Reactor Context và cơ chế propagation đang dùng |
| Transaction | Theo transaction manager và phạm vi đồng bộ | Theo reactive transaction manager và context của chuỗi |
| Thứ tự trong một chuỗi callback | Nối entity trả về | Nối publisher để lấy entity cho bước sau |
| Kiểm tra kết quả | Gọi và assert kết quả/exception | Subscribe có kiểm soát, kiểm tra value/error/completion |

Bảng mô tả hai mô hình. Không phải mọi store đều có cùng tập callback, mức hỗ trợ transaction hoặc hành vi trên bulk/update/projection.

## 4. Cùng một quy tắc domain, hai cách tích hợp

Giả sử ứng dụng quy định SKU được bỏ khoảng trắng đầu/cuối và viết hoa trước khi mapping để lưu. Mô hình tối giản:

```java
public record Product(String id, String sku) {

    public Product withSku(String value) {
        return new Product(id, value);
    }
}
```

Tách phép chuẩn hóa thành một hàm không phụ thuộc persistence:

```java
import java.util.Locale;

public final class SkuRules {

    private SkuRules() {
    }

    public static Product normalize(Product product) {
        String sku = product.sku();

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Product SKU is required");
        }

        String normalized = sku.strip().toUpperCase(Locale.ROOT);

        return normalized.equals(sku)
                ? product
                : product.withSku(normalized);
    }
}
```

Quy tắc viết hoa SKU là lựa chọn nghiệp vụ của ví dụ. `Locale.ROOT` giúp kết quả không phụ thuộc locale mặc định của máy chạy.

Ví dụ dùng record và các API chuỗi tương ứng nên cần phiên bản Java phù hợp. Các lớp `public` cần đặt trong file Java riêng khi triển khai. Đây là các đoạn minh họa, chưa phải cấu hình persistence đầy đủ.

### 4.1. Callback đồng bộ cho MongoDB

```java
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public final class SyncNormalizeSkuCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, String collection) {
        return SkuRules.normalize(entity);
    }
}
```

Khi callback được gọi:

1. `SkuRules.normalize` chạy trong lời gọi đó.
2. Nếu hợp lệ, phương thức trả entity kết quả.
3. Bước conversion tiếp tục với entity được trả về.
4. Nếu hàm phát sinh lỗi, lời gọi không trả kết quả thành công.

Với `Product("p-001", " ab-42 ")`, kết quả là entity có SKU `AB-42`. Do record bất biến, object đầu vào vẫn giữ SKU ban đầu.

### 4.2. Callback reactive cho MongoDB

```java
import reactor.core.publisher.Mono;

import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public final class ReactiveNormalizeSkuCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Mono<Product> onBeforeConvert(Product entity, String collection) {
        return Mono.fromSupplier(() -> SkuRules.normalize(entity));
    }
}
```

`Mono<Product>` là một cách triển khai hợp đồng publisher của callback này. Hạ tầng reactive cần subscribe và nối kết quả vào phần còn lại của thao tác.

Trong ví dụ, phép chuẩn hóa nằm trong supplier. Nó được thực hiện khi publisher được subscribe, và exception từ phép tính được đưa vào luồng lỗi reactive.

Một ứng dụng có cả hai stack có thể có các callback tương ứng cho từng đường. Điều cần xác nhận là template/repository thực tế dùng đúng API, đúng callback beans và đúng cấu hình store.

## 5. Tách thời điểm gọi phương thức khỏi thời điểm chạy publisher

Một hiểu nhầm phổ biến là “cứ trả `Mono` thì mọi dòng code trong phương thức đều tự chạy muộn”. Thực tế, code Java bên ngoài publisher vẫn chạy khi phương thức được gọi.

So sánh:

```java
return Mono.just(SkuRules.normalize(entity));
```

với:

```java
return Mono.fromSupplier(() -> SkuRules.normalize(entity));
```

Ở trường hợp đầu, Java phải gọi `normalize` để tính đối số trước khi tạo `Mono.just`. Ở trường hợp sau, phép tính được đưa vào supplier và được trì hoãn theo subscription của publisher đó.

| Đặc điểm | `Mono.just(normalize(entity))` | `Mono.fromSupplier(() -> normalize(entity))` |
| --- | --- | --- |
| Lúc tính giá trị | Khi dòng code được thực thi trong phương thức callback | Khi publisher được subscribe |
| Exception của phép tính | Có thể phát sinh trước khi phương thức trả publisher | Được phát thành lỗi trong publisher khi thực hiện supplier |
| Nhiều subscription vào cùng publisher | Dùng lại giá trị đã tính | Có thể thực hiện lại phép tính mỗi subscription |

Điều này không có nghĩa `Mono.just` luôn sai. Nó phù hợp khi đã có sẵn một giá trị và không cần trì hoãn việc tạo giá trị. Chọn theo thời điểm tính toán và hợp đồng lỗi mà bạn muốn.

### 5.1. Vai trò của `Mono.defer`

`Mono.defer` hữu ích khi chính việc tạo publisher cần được thực hiện trong phạm vi subscription:

```java
return Mono.defer(() -> policyClient.validate(entity.sku())
        .thenReturn(entity));
```

Ở đây, lời gọi `policyClient.validate(...)` nằm trong phần được trì hoãn. Hợp đồng của `policyClient` vẫn phải là API reactive phù hợp; bọc một lời gọi blocking trong `defer` không tự biến nó thành non-blocking.

Thời điểm module gọi phương thức callback có thể phụ thuộc pipeline của module. Phân biệt phần code được gọi để tạo publisher với phần công việc nằm bên trong publisher giúp tránh dựa vào giả định thời gian không rõ ràng.

### 5.2. Reactive không tự tạo một thread mới

Một `Mono.fromSupplier` có thể chạy supplier trên thread subscribe nếu không có scheduler boundary khác. Nó không tương đương với việc gửi công việc vào một executor.

Với phép chuẩn hóa chuỗi nhỏ, điều này thường phù hợp. Với I/O blocking, chỉ đổi kiểu trả về thành `Mono` không giải quyết vấn đề chặn luồng.

## 6. Nối công việc bất đồng bộ vào kết quả callback

Giả sử cần kiểm tra SKU qua một API reactive trước khi tiếp tục ghi. Hợp đồng của client:

```java
import reactor.core.publisher.Mono;

public interface SkuPolicyClient {

    // Complete: SKU được chấp nhận.
    // Error: không được chấp nhận hoặc không kiểm tra được.
    Mono<Void> validate(String sku);
}
```

Một callback minh họa:

```java
import java.util.Objects;

import reactor.core.publisher.Mono;

import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;

public final class ValidateSkuReactiveCallback
        implements ReactiveBeforeConvertCallback<Product> {

    private final SkuPolicyClient policyClient;

    public ValidateSkuReactiveCallback(SkuPolicyClient policyClient) {
        this.policyClient = Objects.requireNonNull(policyClient);
    }

    @Override
    public Mono<Product> onBeforeConvert(Product entity, String collection) {
        return Mono.fromSupplier(() -> SkuRules.normalize(entity))
                .flatMap(normalized -> policyClient
                        .validate(normalized.sku())
                        .thenReturn(normalized));
    }
}
```

Đăng ký implementation này bằng cơ chế bean phù hợp nếu chọn sử dụng nó. Ví dụ tập trung vào composition, không yêu cầu đăng ký thêm một callback kiểm tra trùng lặp với callback chuẩn hóa trước đó.

### 6.1. Vì sao dùng `flatMap`?

`validate` trả về một publisher. Callback cần chờ tín hiệu của publisher đó rồi mới phát entity đi tiếp. `flatMap` nối công việc này vào chuỗi thay vì tạo ra một publisher lồng bên trong một giá trị thông thường.

Nếu validation thất bại, lỗi đi theo chuỗi. Nếu validation hoàn tất thành công, `thenReturn(normalized)` phát entity kết quả cho hạ tầng.

### 6.2. `Mono<Void>` bên trong khác `Mono<Void>` làm kết quả callback

Trong hợp đồng client, không phát giá trị mà chỉ complete là thành công hợp lệ. Nhưng callback vẫn cần trả một entity để bước mapping tiếp tục.

Vì vậy:

```text
validate(sku): Mono<Void>
    -> complete thành công
    -> thenReturn(product)
    -> Mono<Product> cho callback
```

Trả thẳng `Mono<Void>` không đáp ứng hợp đồng callback yêu cầu entity. Tương tự, dùng `then()` ở cuối và làm mất entity là sai mục tiêu của ví dụ.

### 6.3. Validation bên ngoài không tự tạo tính nguyên tử với database

Một kết quả validation có thể thay đổi trước khi dữ liệu được ghi. Callback không tự tạo transaction phân tán giữa dịch vụ policy và store.

Nếu quy tắc là uniqueness hoặc một ràng buộc cạnh tranh trong database, cần cơ chế constraint/concurrency phù hợp. Nếu việc kiểm tra bên ngoài là một quyết định nghiệp vụ lớn, tầng service/use case có thể là nơi điều phối rõ ràng hơn callback vòng đời.

## 7. Các cách làm dễ tách sai pipeline

### 7.1. Tự `subscribe()` trong callback

Ví dụ sai về quan hệ chờ kết quả:

```java
policyClient.validate(entity.sku()).subscribe();
return Mono.just(entity);
```

Publisher validation đã bị tách thành một subscription riêng. Hạ tầng save chỉ nhìn thấy `Mono.just(entity)` và có thể tiếp tục mà chưa biết validation thành công hay thất bại.

Hệ quả có thể gồm:

- Ghi dữ liệu trước khi validation xong.
- Lỗi của validation không làm thao tác save thất bại theo chuỗi mong muốn.
- Cancellation và ngữ cảnh transaction không còn gắn với cùng một chuỗi.
- Công việc chạy ngoài vòng đời mà phía gọi có thể quản lý.

Hãy trả lại publisher đã compose như ví dụ `flatMap(...thenReturn(...))` để hạ tầng điều phối subscription.

### 7.2. Gọi `block()` để chờ trong callback reactive

Ví dụ cần tránh:

```java
policyClient.validate(entity.sku()).block();
return Mono.just(entity);
```

Cách này chặn thread đang thực thi phương thức. Trong một pipeline dùng event loop, nó có thể làm giảm khả năng xử lý hoặc gây lỗi theo cơ chế phát hiện blocking của môi trường.

Nó cũng làm quan hệ giữa transaction/context của các thao tác khó kiểm soát hơn. Nếu nguồn đã là reactive, compose nguồn đó vào kết quả thay vì chặn để lấy kết quả.

### 7.3. Chỉ tạo publisher rồi bỏ đi

Đoạn sau không nối validation vào save:

```java
policyClient.validate(entity.sku());
return Mono.just(entity);
```

Việc gọi phương thức để lấy một publisher không bảo đảm công việc bên trong đã thực hiện. Với nguồn lazy, publisher bị bỏ đi sẽ không được subscribe bởi chuỗi save.

### 7.4. Dùng `@Async` thay cho callback reactive

Đưa logic đồng bộ sang một executor không tự tạo hợp đồng publisher với pipeline store. Callback vẫn phải cung cấp entity theo chữ ký interface, và hạ tầng phải nhận đúng kết quả trước bước tiếp theo.

Nếu cần pipeline reactive, sử dụng interface reactive được module hỗ trợ. Nếu cần stack đồng bộ, tổ chức việc chờ và trả entity theo hợp đồng đồng bộ. Một kiểu trả về future tùy ý không tự được chấp nhận thay cho publisher của callback.

## 8. Entity, null, empty và số lượng kết quả

Trong callback trả entity, một instance mới có thể mang các thay đổi mà bước sau cần sử dụng. Với reactive, instance đó phải được phát qua publisher kết quả.

| Kết quả | Cách hiểu trong callback yêu cầu entity |
| --- | --- |
| Đồng bộ trả entity hợp lệ | Entity này đi tiếp theo hợp đồng |
| Đồng bộ trả null | Không phải quy ước chung để bỏ qua save |
| Reactive phát một entity | Cung cấp giá trị cho bước sau |
| Reactive trả null thay cho publisher | Sai hợp đồng publisher |
| Reactive complete mà không phát entity | Cần xét hợp đồng module; không tự coi là cách hủy save được hỗ trợ |
| Reactive phát nhiều entity | Không phù hợp với ý định một callback biến đổi một entity nếu module yêu cầu một kết quả |

Với callback trong ví dụ, mục tiêu là **một entity kết quả hoặc một lỗi**. Không dùng `Mono.empty()` như một tín hiệu ngầm “bỏ qua sản phẩm này” nếu module không có hợp đồng đó.

Nếu nghiệp vụ cần lọc danh sách entity trước khi ghi, hãy thể hiện thao tác lọc ở tầng điều phối của danh sách thay vì dựa vào một publisher rỗng ngoài ý định của callback.

### Giá trị trả về vẫn quan trọng với entity bất biến

Phép biến đổi:

```text
Product(id=p-001, sku=" ab-42 ")
    -> Product(id=p-001, sku="AB-42")
```

không sửa record ban đầu. Hạ tầng phải sử dụng kết quả của callback, và phía gọi nên sử dụng entity do save trả về khi cần trạng thái sau persistence.

Một test chỉ quan sát object đầu vào có thể kết luận nhầm callback chưa chạy.

## 9. Thứ tự callback khác thứ tự xử lý nhiều entity

### 9.1. Nối các callback cho cùng entity

Với callback đồng bộ:

```text
entity -> callback A -> entity A -> callback B -> entity B
```

Với callback reactive:

```text
entity
    -> publisher của callback A
    -> entity A
    -> publisher của callback B
    -> entity B
```

Khi module điều phối một chuỗi callback theo thứ tự, việc callback A có công việc bất đồng bộ không có nghĩa callback B được phép bỏ qua kết quả A. B phải nhận kết quả theo composition của chuỗi.

Các cơ chế như `Ordered` xác định ưu tiên giữa callbacks trong phạm vi điều phối phù hợp. Giá trị order nhỏ hơn được ưu tiên trước giá trị lớn hơn trong thứ tự đó.

Tuy nhiên, ordering không đổi vị trí các giai đoạn: một callback sau mapping không được chuyển lên trước mapping chỉ vì có con số order nhỏ.

### 9.2. Nhiều entity có thể được xử lý xen kẽ

Pipeline xử lý nhiều entity là một vấn đề khác. Nếu tầng ứng dụng dùng `flatMap` để thực hiện nhiều save, các thao tác có thể chồng lấn và kết quả có thể không giữ thứ tự đầu vào.

Nếu cần xử lý tuần tự ở tầng đó, có thể cân nhắc một chuỗi như:

```java
Flux.fromIterable(products)
        .concatMap(reactiveRepository::save);
```

Đây là ví dụ điều phối repository reactive, không phải cấu hình ordering của callbacks. Nó cũng không tự tạo một transaction chung cho toàn bộ danh sách.

Không suy ra cách một module triển khai `saveAll` chỉ từ ví dụ `flatMap` hoặc `concatMap` của ứng dụng; cần kiểm tra hợp đồng của API đang dùng.

### 9.3. Callback bean dùng chung cần tránh trạng thái theo lần gọi

Không lưu các giá trị như `currentProduct`, `currentTenant` hoặc `lastValidationResult` vào field mutable của một singleton callback.

Hai entity có thể đang đi qua callback cùng lúc, kể cả trong stack đồng bộ có nhiều request. Dùng biến cục bộ, entity bất biến và dependency có phạm vi/thread-safety phù hợp.

## 10. Lỗi, retry và cancellation

### 10.1. Lỗi phải đi đến đúng phía gọi

Trong đồng bộ, exception ở callback trước ghi thường dừng đường thao tác trước bước ghi đó. Trong reactive, lỗi từ publisher phải được nối vào chuỗi để phía gọi nhận được error signal.

Tránh nuốt lỗi bằng một fallback vô điều kiện:

```java
return validationFlow.onErrorReturn(entity);
```

Nếu validation thất bại mà callback vẫn phát entity gốc, pipeline có thể tiếp tục ghi dữ liệu không thỏa điều kiện. Chỉ phục hồi khi nghiệp vụ đã quy định rõ trạng thái thay thế hợp lệ.

### 10.2. Lỗi sau save không chứng minh dữ liệu chưa ghi

Callback có thể chạy ở giai đoạn sau bước ghi. Nếu nó phát sinh lỗi, phương thức hoặc publisher có thể báo thất bại dù bước ghi đã diễn ra.

Kết quả cuối cùng còn phụ thuộc transaction, vị trí rollback và cơ chế xác nhận của store. Không coi mọi lỗi từ save là bằng chứng chắc chắn rằng database chưa thay đổi.

### 10.3. Retry có thể thực hiện lại logic

Một subscription mới hoặc retry tại phạm vi chứa callback có thể chạy lại việc chuẩn hóa, validation hoặc ghi. Phạm vi operator retry quyết định phần nào được thực hiện lại.

Ví dụ:

```java
reactiveRepository.save(product).retry(1);
```

không phải bảo đảm “chỉ thử lại callback mà không đụng đến ghi”. Tùy source và đường lỗi, thao tác trong publisher có thể được lặp lại.

Phép chuẩn hóa SKU có tính lặp ổn định:

```text
normalize(normalize(product)) = normalize(product)
```

Các tác động như tăng bộ đếm, gọi dịch vụ có side effect hoặc phát thông báo cần cơ chế kiểm soát lặp riêng. Callback không cung cấp bảo đảm thực thi đúng một lần.

### 10.4. Cancellation không tự rollback mọi việc đã bắt đầu

Khi subscription bị hủy, công việc reactive phía sau có thể không tiếp tục. Nhưng một thao tác ghi đã gửi đến store có thể có trạng thái khác nhau tùy driver và thời điểm hủy.

Không dùng cancellation như một API chung để khẳng định dữ liệu chưa được ghi hoặc đã rollback. Nếu cần biết trạng thái cuối, phải theo hợp đồng transaction/store và thiết kế thao tác có khả năng xử lý lại phù hợp.

## 11. Ngữ cảnh thực thi và transaction

### 11.1. `ThreadLocal` không phải hợp đồng truyền ngữ cảnh reactive

Một callback có thể cần tenant, auditor hoặc thông tin người dùng. Trong stack đồng bộ, nguồn dữ liệu có thể gắn với thread theo thiết kế của framework.

Trong reactive, pipeline có thể chuyển thread. Không mặc định một `ThreadLocal` được đặt ở nơi nhận request sẽ còn có đúng dữ liệu khi callback thực thi.

Sử dụng Reactor Context hoặc cơ chế propagation mà ứng dụng đã cấu hình và kiểm chứng. Ví dụ khi tenant được cung cấp rõ trong Reactor Context:

```java
Mono.deferContextual(contextView -> {
    String tenantId = contextView.get("tenantId");
    return prepareForTenant(entity, tenantId);
});
```

Đoạn này minh họa cách đọc context; `prepareForTenant` là thao tác của ứng dụng trả `Mono<Product>`, và nguồn gọi phải cung cấp key tương ứng. Spring Data không tự tạo key `tenantId` chỉ vì callback cần nó.

### 11.2. Transaction đồng bộ và reactive có cơ chế gắn phạm vi khác nhau

| Bối cảnh | Điều cần xác định |
| --- | --- |
| Stack đồng bộ | Transaction manager, phạm vi gọi và tài nguyên đang tham gia |
| Stack reactive | Reactive transaction manager, subscription và context của chuỗi |
| Callback gọi một client khác | Client có thực sự tham gia cùng transaction không? |
| Callback dùng cả API đồng bộ và reactive | Có ranh giới blocking hoặc transaction khác bị đưa vào không? |

Callback reactive tự `subscribe()` một nhánh khác có thể làm nhánh đó không tham gia phạm vi transaction mà thao tác save đang dùng. Compose công việc là điều kiện để giữ quan hệ điều phối; việc tham gia cùng transaction còn phụ thuộc tài nguyên và transaction manager.

### 11.3. Sau save chưa phải sau commit

Cả callback đồng bộ lẫn reactive sau save đều mô tả một vị trí trong pipeline của module. Transaction bên ngoài có thể vẫn chưa commit.

Nếu gửi một thông báo ngay trong callback rồi transaction rollback, bên nhận có thể thấy một thay đổi không trở thành dữ liệu đã commit. Với tác động cần gắn với commit, sử dụng cơ chế transaction phù hợp hoặc thiết kế như outbox theo nhu cầu hệ thống.

Đổi kiểu trả về từ entity sang `Mono<Entity>` không tự giải quyết vấn đề nhất quán đó.

## 12. Phạm vi áp dụng theo module và đường thao tác

Một callback chuẩn hóa trước conversion không tự bao phủ mọi cách cập nhật cùng field.

| Đường thao tác | Cần kiểm tra |
| --- | --- |
| Save một entity qua template | Callback đúng họ đồng bộ/reactive có được gọi không? |
| Repository save | Repository có đi qua pipeline dự kiến không? |
| Update theo điều kiện | Có tạo entity và chạy callback này không? |
| Bulk operation | Có bỏ qua pipeline entity thông thường không? |
| Driver trực tiếp | Có đi qua hạ tầng callback của Spring Data không? |
| Projection hoặc đọc một phần | Có materialize đúng kiểu entity và giai đoạn callback không? |
| Auditing | Callback/cơ chế auditing có phù hợp stack và nguồn auditor không? |

Ở MongoDB, một update theo query không tải entity thường không đi qua chuỗi save entity được minh họa. Những module khác có thể có chi tiết riêng.

Vì vậy, trước khi chuyển một quy tắc từ service vào callback, hãy lập rõ các đường ghi thực tế. Quy tắc domain, API cập nhật và ràng buộc của store cần phối hợp để tránh một đường bỏ qua chuẩn hóa.

Spring Data JPA có cơ chế vòng đời của JPA provider; không áp dụng trực tiếp interface callback MongoDB vào JPA. R2DBC có mô hình reactive nhưng cũng không vì thế dùng nguyên chữ ký callback MongoDB. Hợp đồng store luôn cần được đối chiếu riêng.

## 13. Kiểm chứng khác biệt thay vì chỉ kiểm tra kiểu trả về

Các ví dụ kiểm tra dưới đây dùng để học cách xác nhận hành vi. Chúng chưa được chạy trên một project hoặc database cụ thể trong bài này.

### 13.1. Callback đồng bộ

Kiểm tra các hành vi:

- Đầu vào `" ab-42 "` tạo kết quả `"AB-42"`.
- SKU không hợp lệ làm lời gọi phát sinh lỗi.
- Object bất biến đầu vào không bị sửa.
- ID được giữ nguyên khi tạo entity mới.

Sau đó kiểm tra tích hợp để xác nhận dữ liệu được lưu thật đã chuẩn hóa. Kết quả của một lời gọi callback trực tiếp chưa chứng minh bean đã được template sử dụng.

### 13.2. Kiểm tra subscription bằng `StepVerifier`

Với `ValidateSkuReactiveCallback`, có thể kiểm tra việc validation được nối vào publisher:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ValidateSkuReactiveCallbackTest {

    @Test
    void composesValidationBeforeEmittingEntity() {
        AtomicInteger validations = new AtomicInteger();

        SkuPolicyClient policy = sku -> Mono.defer(() -> {
            validations.incrementAndGet();
            return Mono.<Void>empty();
        });

        ValidateSkuReactiveCallback callback =
                new ValidateSkuReactiveCallback(policy);

        Product input = new Product("p-001", " ab-42 ");
        Mono<Product> result = callback.onBeforeConvert(input, "products");

        assertEquals(0, validations.get());

        StepVerifier.create(result)
                .assertNext(product -> {
                    assertEquals("AB-42", product.sku());
                    assertEquals("p-001", product.id());
                })
                .verifyComplete();

        assertEquals(1, validations.get());
        assertEquals(" ab-42 ", input.sku());
    }
}
```

Ví dụ cần JUnit và `reactor-test` trong môi trường triển khai. Nó xác nhận validation chưa thực hiện trước subscription, hoàn tất trước entity kết quả và không làm mất entity khi client trả `Mono<Void>`.

Đây vẫn là kiểm tra callback trực tiếp. Chưa có bằng chứng về đăng ký bean, thứ tự với auditing, transaction hoặc dữ liệu trong store.

### 13.3. Các nhánh cần xác nhận thêm

| Tình huống | Kỳ vọng cần kiểm tra |
| --- | --- |
| Policy phát lỗi | Publisher callback phát lỗi, không phát entity thành công |
| SKU rỗng | Không đi tiếp bằng một entity chưa hợp lệ |
| Hai subscription khi thiết kế cho phép | Không dựa vào trạng thái mutable từ lần trước |
| Hai sản phẩm thực thi xen kẽ | Không lẫn dữ liệu giữa các lần gọi |
| Callback A tạo entity mới | Callback B nhận đúng entity đó |
| Save tích hợp | Entity trả về và biểu diễn lưu trữ thống nhất |
| Thiếu tenant/auditor bắt buộc | Hành vi theo hợp đồng, không âm thầm dùng ngữ cảnh khác |
| Lỗi sau ghi | Trạng thái dữ liệu cuối cùng phù hợp transaction thực tế |

Khi kiểm tra reactive repository, phải subscribe và chờ tín hiệu kết thúc bằng công cụ phù hợp. Chỉ tạo một `Mono` rồi kết thúc test không chứng minh thao tác đã diễn ra.

## 14. Các lỗi thường gặp và cách khoanh vùng

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Reactive repository không gọi callback đồng bộ | Dùng sai họ callback | Chọn interface reactive của đúng module |
| Có `Mono` nhưng validation không chạy | Publisher bị tạo rồi bỏ đi, không được compose | Nối công việc vào publisher trả về |
| Save chạy trước validation | Có subscription tách riêng | Bỏ `subscribe()` nội bộ, dùng composition |
| Request bị chặn dù code trả `Mono` | Công việc blocking vẫn chạy trong callback | Dùng client phù hợp hoặc thiết kế ranh giới thực thi rõ ràng |
| Callback trả publisher nhưng lỗi phát sinh quá sớm | Phép tính được thực hiện trước `Mono.just` | Dùng cơ chế trì hoãn khi cần |
| Bước sau không nhận entity | Trả empty hoặc kết thúc bằng `then()` | Bảo toàn entity theo hợp đồng callback |
| Entity trả về đúng nhưng database sai | Thay đổi ở sai giai đoạn mapping | Kiểm tra before-convert/before-save và dữ liệu ghi |
| Tenant/auditor biến mất khi đổi thread | Phụ thuộc `ThreadLocal` ngoài hợp đồng propagation | Kiểm tra nguồn context reactive |
| Logic chạy lặp khi retry | Tác động không có khả năng xử lý lặp phù hợp | Xác định phạm vi retry và thiết kế tác động |
| Báo lỗi nhưng dữ liệu vẫn tồn tại | Lỗi ở giai đoạn sau ghi hoặc rollback không bao phủ | Kiểm tra transaction và thời điểm lỗi |

Khi khoanh vùng, tách rõ bốn câu hỏi: callback có được chọn không, publisher có được subscribe không, entity nào được phát ra và thao tác store cuối cùng có trạng thái gì.

## 15. Tự kiểm tra mức hiểu

**Trả `Mono` có tự làm callback chạy trên thread khác không?**

Không. Thread thực thi phụ thuộc pipeline và scheduler. Một supplier vẫn có thể chạy trên thread subscribe.

**Vì sao `Mono.just(normalize(entity))` khác `Mono.fromSupplier(() -> normalize(entity))`?**

Biểu thức đầu tính giá trị trước khi tạo publisher. Biểu thức sau trì hoãn phép tính đến subscription và đưa lỗi của phép tính vào chuỗi.

**Client trả `Mono<Void>` có dùng được trong callback trả entity không?**

Có thể compose client đó và dùng `thenReturn(entity)` sau khi nó complete thành công. Không trả mất entity ở đầu ra callback.

**Vì sao không tự `subscribe()` trong callback?**

Vì nó tạo một nhánh thực thi riêng mà hạ tầng save không chờ và không quản lý lỗi/cancellation theo chuỗi mong muốn.

**`Ordered` có bảo đảm toàn bộ danh sách entity được lưu tuần tự không?**

Không. Ordering callback cho một phạm vi điều phối khác với concurrency của nhiều thao tác save.

**`Mono.empty()` có phải cách chung để hủy save không?**

Không. Phải theo hợp đồng module; với callback cần entity, thiết kế rõ entity thành công hoặc lỗi thay vì một quy ước ngầm.

**Callback sau save reactive có nghĩa dữ liệu đã commit chưa?**

Chưa thể kết luận. Vị trí callback và ranh giới commit của transaction là hai vấn đề cần xác định riêng.

## 16. Nguyên tắc áp dụng

Chọn callback theo đúng module, đúng pipeline đồng bộ hoặc reactive và đúng giai đoạn vòng đời. Hợp đồng cốt lõi là entity kết quả phải đi tiếp: trả trực tiếp trong đồng bộ, hoặc phát qua publisher được compose trong reactive.

Với reactive, xác định phần code tính ngay và phần được trì hoãn, giữ công việc trong một chuỗi được hạ tầng điều phối, truyền lỗi rõ ràng và sử dụng nguồn context phù hợp. Với cả hai mô hình, kiểm tra dữ liệu lưu thực tế, phạm vi callback, thứ tự và transaction thay vì chỉ kiểm tra tên interface hoặc kiểu trả về.

Một cấu hình đúng cần thống nhất **điểm gọi, kết quả entity, mô hình thực thi và ranh giới dữ liệu**. Khi bốn phần đó rõ ràng, callback mới thực hiện đúng vai trò trong vòng đời entity của ứng dụng.