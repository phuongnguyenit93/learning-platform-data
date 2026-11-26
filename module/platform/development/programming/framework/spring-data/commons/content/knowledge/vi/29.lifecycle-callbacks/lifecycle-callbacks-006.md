# Callback với đối tượng bất biến và giá trị trả về

## 1. Giá trị trả về là một phần của hợp đồng callback

Trong chương **Vòng đời và callback** của module `SPRING_DATA_COMMONS`, điểm cần hiểu rõ khi làm việc với đối tượng bất biến là: callback không nhất thiết sửa đối tượng đã nhận. Nó có thể trả về một instance khác để hạ tầng tiếp tục xử lý.

Giả sử ứng dụng chuẩn hóa mã hàng trước khi lưu. Với một entity mutable, mã có thể gọi setter. Với entity immutable, cách phù hợp là tạo bản sao có mã đã chuẩn hóa rồi **trả bản sao đó**. Nếu tạo bản sao nhưng vẫn trả entity đầu vào, thay đổi bị bỏ lại trong một biến local và không đi tiếp trong pipeline.

Spring Data Entity Callbacks cung cấp các điểm tích hợp đồng bộ và reactive có thứ tự trong chuỗi xử lý, cho phép trả entity đã thay đổi hoặc một wrapper reactive phát entity đó. Các callback cụ thể và đối số bổ sung do module store xác định. [Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html).

Bài học tập trung vào ba câu hỏi:

1. Callback trả instance nào cho bước tiếp theo?
2. Instance đó còn giữ đầy đủ identity, version và dữ liệu của entity không?
3. Ở thời điểm callback chạy, thay đổi đang tác động lên entity trong bộ nhớ hay lên biểu diễn thực sự được ghi xuống store?

Ví dụ cụ thể bên dưới dùng Spring Data MongoDB. Abstraction callback đến từ Commons; khả năng mapping, checkpoint và kiểu tham số của callback phải theo đúng store.

## 2. Bất biến không có nghĩa là không thể thay đổi trạng thái nghiệp vụ

Một đối tượng bất biến không cho phép thay đổi trạng thái của chính instance sau khi được tạo. Tuy nhiên, ứng dụng vẫn có thể tạo một instance mới biểu diễn trạng thái tiếp theo.

```text
Instance A: sku = "  sku-204  "
    |
    | tạo bản sao có sku đã chuẩn hóa
    v
Instance B: sku = "SKU-204"
```

Instance A vẫn giữ dữ liệu cũ. B là đối tượng khác mà callback cần đưa vào chuỗi xử lý tiếp theo.

Cần phân biệt ba khái niệm:

| Khái niệm | Câu hỏi |
| --- | --- |
| Identity trong domain | Entity này có ID nào? |
| Identity của object Java | Hai biến có trỏ đến cùng instance không? |
| Equality theo giá trị | Hai đối tượng có các giá trị được coi là bằng nhau không? |

Một bản sao immutable có thể có cùng ID nhưng khác object identity. Ngược lại, `equals` của một record có thể thay đổi kết quả khi version hoặc một thuộc tính khác thay đổi dù hai instance vẫn biểu diễn cùng entity trong store.

Không dùng điều kiện `saved == original` để suy ra thao tác lưu đúng hay sai. Hãy kiểm tra identity nghiệp vụ và các giá trị mà thao tác được yêu cầu tạo ra.

## 3. Mô hình minh họa: CatalogItem bất biến

Giả định nghiệp vụ của ví dụ:

- Mã SKU được chuẩn hóa bằng cách bỏ khoảng trắng ở hai đầu và chuyển thành chữ hoa theo `Locale.ROOT`.
- Nếu tên hiển thị bị thiếu hoặc chỉ có khoảng trắng, dùng SKU đã chuẩn hóa làm tên mặc định.
- Khi tạo bản sao, không làm mất ID hoặc version.

```java
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("catalog_items")
public record CatalogItem(
        @Id String id,
        String sku,
        String displayName,
        @Version Long version) {

    public CatalogItem {
        Objects.requireNonNull(sku, "SKU is required");
        if (sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
    }

    public CatalogItem withSku(String newSku) {
        if (Objects.equals(sku, newSku)) {
            return this;
        }
        return new CatalogItem(id, newSku, displayName, version);
    }

    public CatalogItem withDisplayName(String newDisplayName) {
        if (Objects.equals(displayName, newDisplayName)) {
            return this;
        }
        return new CatalogItem(id, sku, newDisplayName, version);
    }
}
```

Các phương thức `with...` là phương thức sao chép theo quy ước thiết kế của lớp. Chúng không sửa record hiện tại. Nếu giá trị không đổi, chúng có thể trả `this` để tránh tạo bản sao không cần thiết.

Record này chỉ chứa `String` và `Long`, phù hợp với ví dụ bất biến. Nếu thêm `List`, `Map` hoặc một đối tượng mutable vào record, thuộc tính final chỉ giữ nguyên tham chiếu, không tự làm nội dung bên trong bất biến. Khi đó cần thiết kế việc sao chép và đóng gói dữ liệu phù hợp.

Spring Data object mapping có cơ chế tạo instance qua constructor, dùng canonical constructor cho record và có thể tạo bản sao để xử lý thuộc tính immutable. Phạm vi này áp dụng cho các module có object mapping riêng; không phải một mô tả thay thế cho mapping của JPA provider. [Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html).

Constructor trong ví dụ cho phép `displayName` chưa có giá trị vì callback sẽ điền mặc định. Nếu constructor bắt buộc tên phải có ngay từ đầu, một đối tượng thiếu tên sẽ bị từ chối trước khi tới callback. Bất biến của model và giá trị mặc định ở callback cần được thiết kế nhất quán.

## 4. Callback đồng bộ phải trả đúng bản sao

### 4.1. Chuẩn hóa trước khi chuyển thành dữ liệu store

Đối với MongoDB, dùng `BeforeConvertCallback` để thay đổi entity trước khi mapper chuyển nó thành document:

```java
import java.util.Locale;
import org.springframework.core.Ordered;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public final class NormalizeCatalogItemCallback
        implements BeforeConvertCallback<CatalogItem>, Ordered {

    @Override
    public CatalogItem onBeforeConvert(
            CatalogItem item, String collection) {

        String normalizedSku = item.sku().strip().toUpperCase(Locale.ROOT);
        return item.withSku(normalizedSku);
    }

    @Override
    public int getOrder() {
        return 10;
    }
}
```

Callback nhận một `CatalogItem`, tính giá trị mới rồi trả kết quả từ `withSku`. Khi SKU đã đúng định dạng, kết quả có thể chính là `item`; khi chưa đúng, kết quả là bản sao.

Hợp đồng `BeforeConvertCallback` của MongoDB cho phép trả cùng instance hoặc instance đã thay đổi để tiếp tục lưu. Thời điểm của callback là trước khi domain object được chuyển đổi để persistence. [BeforeConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeConvertCallback.html).

### 4.2. Lỗi tạo bản sao rồi bỏ qua kết quả

```java
@Override
public CatalogItem onBeforeConvert(CatalogItem item, String collection) {
    String normalizedSku = item.sku().strip().toUpperCase(Locale.ROOT);
    item.withSku(normalizedSku); // Bản sao được tạo nhưng bị bỏ qua.
    return item;                 // Vẫn trả đối tượng đầu vào.
}
```

Đoạn mã vẫn biên dịch vì Java không bắt buộc sử dụng giá trị trả về của `withSku`. Nhưng SKU của `item` không đổi.

Hai cách thể hiện đúng:

```java
return item.withSku(normalizedSku);
```

Hoặc:

```java
CatalogItem updated = item.withSku(normalizedSku);
return updated;
```

Việc gán một bản sao cho biến local `item` cũng không thay tham chiếu mà caller đang giữ. Hạ tầng nhận bản sao nhờ giá trị trả về của callback, không phải nhờ Java truyền tham số theo tham chiếu.

### 4.3. Không trả null để báo “không thay đổi”

Nếu callback không cần sửa gì, trả entity hiện tại. Không dùng null làm tín hiệu bỏ qua callback, xóa entity hay dừng lưu. API quản lý callback đồng bộ của Commons công bố kết quả callback không null. [EntityCallbacks](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/callback/EntityCallbacks.html).

Nếu dữ liệu không hợp lệ, hãy báo lỗi phù hợp với hợp đồng của ứng dụng. Đây là quyết định khác với việc trả một entity hợp lệ để đi tiếp.

## 5. Chuỗi callback phải dùng kết quả của bước trước

### 5.1. Callback điền tên mặc định

```java
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public final class DefaultCatalogItemNameCallback
        implements BeforeConvertCallback<CatalogItem> {

    @Override
    public CatalogItem onBeforeConvert(
            CatalogItem item, String collection) {

        if (item.displayName() == null || item.displayName().isBlank()) {
            return item.withDisplayName(item.sku());
        }
        return item;
    }
}
```

Với hai callback trên, thứ tự mong muốn trong cùng checkpoint là chuẩn hóa SKU trước, rồi dùng SKU đó để điền tên:

```text
A: sku="  sku-204  ", displayName=null
  -> NormalizeCatalogItemCallback, order 10
B: sku="SKU-204", displayName=null
  -> DefaultCatalogItemNameCallback, order 20
C: sku="SKU-204", displayName="SKU-204"
  -> mapper chuyển C thành document
```

Có thể mô tả phép ghép theo dạng:

```text
current = callback1(original)
current = callback2(current)
current = callback3(current)
```

Không được mô tả thành việc mọi callback đều nhận lại `original`. Nếu một lớp tích hợp tự viết làm vậy, thay đổi của callback trước sẽ bị mất khi callback sau trả bản sao dựa trên dữ liệu cũ.

### 5.2. Thứ tự thuộc checkpoint tương ứng

Giá trị order nhỏ hơn được ưu tiên trước khi sắp các callback cùng điểm xử lý. `@Order` trên một `BeforeSaveCallback` không đưa callback đó lên trước giai đoạn `BeforeConvert`; hai giai đoạn có checkpoint riêng trong pipeline.

Với ví dụ, nếu callback điền tên chạy trước callback chuẩn hóa, tên mặc định có thể chứa SKU chưa được chuẩn hóa. Ngay cả khi dữ liệu SKU cuối cùng đúng, quan hệ giữa hai thuộc tính có thể sai yêu cầu.

Nếu hai phép biến đổi luôn đi cùng nhau và phụ thuộc chặt chẽ vào nhau, một callback duy nhất gọi các hàm xử lý nhỏ có thể dễ bảo trì hơn. Không cần chia callback chỉ để có nhiều lớp.

## 6. Giữ ID, version và dữ liệu không liên quan khi sao chép

Bản sao được trả về cần đại diện trạng thái tiếp theo của đúng entity đang xử lý. Ví dụ sai:

```java
return new CatalogItem(null, normalizedSku, item.displayName(), null);
```

Đoạn mã làm mất ID và version mà entity đầu vào có thể đang giữ. Với thao tác cập nhật, điều đó có thể ảnh hưởng nhận diện entity mới và optimistic locking.

Cách giữ metadata:

```java
return new CatalogItem(
        item.id(),
        normalizedSku,
        item.displayName(),
        item.version());
```

Hoặc dùng `withSku` đã đóng gói quy tắc sao chép.

| Thành phần | Nguyên tắc khi callback chỉ chuẩn hóa SKU |
| --- | --- |
| ID | Giữ identity của entity đang xử lý |
| Version | Giữ giá trị hiện tại; để cơ chế persistence quản lý cập nhật version |
| Tên hiển thị | Giữ nguyên trừ khi callback có trách nhiệm thay đổi |
| Thuộc tính auditing | Bảo toàn các giá trị không thuộc trách nhiệm callback |
| Collection hoặc value object đi kèm | Giữ đúng nội dung và mức bất biến mà domain yêu cầu |

Không tự đặt version về 0 hoặc null sau mỗi lần sao chép. Nếu ứng dụng có auditing, tránh dựng lại entity bằng một constructor rút gọn làm mất `createdAt`, `createdBy` hoặc dữ liệu mà auditing callback trước đó đã đưa vào.

Tương tự, không tạo một subtype khác chỉ để thêm trạng thái tạm nếu subtype đó không còn phù hợp với mapping hoặc kiểu mà repository cam kết trả về. Mục tiêu là bản sao hợp lệ của domain object, không phải thay hợp đồng model giữa chừng.

## 7. Caller phải sử dụng kết quả save

Repository MongoDB cho ví dụ:

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogItemRepository
        extends MongoRepository<CatalogItem, String> {
}
```

Khi tạo mới:

```java
CatalogItem draft = new CatalogItem(null, "  sku-204  ", null, null);
CatalogItem saved = repository.save(draft);
```

Sau thao tác, ứng dụng cần sử dụng `saved`. Đó là instance được đường lưu trả về, có thể chứa kết quả callback cùng các giá trị do persistence xử lý.

```java
return saved;
```

Không nên làm:

```java
repository.save(draft);
return draft;
```

Trong ví dụ immutable, `draft` vẫn có SKU ban đầu và tên chưa được điền. ID/version do store xử lý cũng không phải lý do để kỳ vọng object ban đầu tự thay đổi.

Hợp đồng `CrudRepository.save` yêu cầu dùng instance được trả về cho các thao tác tiếp theo vì quá trình lưu có thể thay instance hoàn toàn. [CrudRepository.save](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html#save(S)).

Một bảng kỳ vọng về dữ liệu:

| Biến | SKU | Tên hiển thị | ID/version |
| --- | --- | --- | --- |
| `draft` | `  sku-204  ` | null | Giá trị lúc tạo draft |
| Entity sau hai callback | `SKU-204` | `SKU-204` | Được các phép sao chép bảo toàn |
| `saved` | Kết quả đường lưu trả về | Kết quả đường lưu trả về | Theo mapping và cơ chế persistence thực tế |

Không gán một con số version khởi tạo chung cho mọi store. Khi cần kiểm chứng, dựa vào hợp đồng và cấu hình của module cụ thể.

Nếu tái sử dụng một draft cũ vẫn chưa có ID để lưu lại, ứng dụng có thể tạo thêm bản ghi mới thay vì cập nhật bản ghi vừa tạo. Nếu tái sử dụng một bản sao có version cũ, có thể gặp xung đột optimistic locking. Việc dùng kết quả `save` giúp tránh cả hai kiểu nhầm trạng thái này.

Với `saveAll`, cũng dùng tập entity trả về cho xử lý tiếp theo. Không kết luận danh sách đầu vào đã được cập nhật tại chỗ chỉ vì mọi phần tử đều được gửi vào thao tác lưu.

## 8. Thời điểm callback quyết định thứ gì thực sự được ghi

### 8.1. Trước chuyển đổi và sau chuyển đổi khác nhau

Đối với MongoDB, có thể hình dung đường lưu ở mức khái niệm:

```text
Entity
  -> BeforeConvertCallback trả entity kế tiếp
  -> mapper tạo Document
  -> BeforeSaveCallback nhận entity và Document
  -> ghi Document vào store
  -> AfterSaveCallback
  -> trả entity về caller
```

Sơ đồ chỉ mô tả các checkpoint liên quan bài học, không mô tả đầy đủ thứ tự của mọi event, auditing callback, xử lý ID, version hoặc transaction advice.

| Checkpoint MongoDB | Khi trả bản sao mới cần nhớ |
| --- | --- |
| `BeforeConvertCallback` | Phù hợp để thay đổi thuộc tính domain trước khi tạo document |
| `BeforeSaveCallback` | Document đã được tạo; đổi riêng thuộc tính persistent của entity không tự chuyển đổi lại document |
| `AfterSaveCallback` | Lệnh ghi tương ứng đã diễn ra; bản sao trả về không tự phát sinh một lần ghi khác |
| `AfterConvertCallback` | Tác động entity được trả từ đường đọc; không tự cập nhật dữ liệu trong store |

### 8.2. Lỗi đổi entity ở BeforeSave nhưng document còn giá trị cũ

Ví dụ dễ gây hiểu nhầm:

```java
import org.bson.Document;

// Phần thân minh họa cho một MongoDB BeforeSaveCallback<CatalogItem>.
public CatalogItem onBeforeSave(
        CatalogItem item, Document document, String collection) {

    return item.withSku("SKU-CHANGED");
}
```

Đoạn mã trả một entity có SKU mới, nhưng document đã được tạo từ entity trước đó. Không thể kết luận store sẽ ghi `SKU-CHANGED` chỉ từ giá trị trả về này.

Javadoc của MongoDB chỉ rõ `BeforeSaveCallback` chạy sau chuyển đổi; thay đổi entity không được lấy để lưu lại document, còn nội dung document là thứ được ghi. Thuộc tính persistent nên được thay ở `BeforeConvertCallback`. [BeforeSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeSaveCallback.html).

Nếu mục tiêu là chỉnh biểu diễn document theo yêu cầu của store, xử lý document theo đúng hợp đồng đó. Nhưng không để một phép chỉnh entity ngầm và một phép chỉnh document độc lập tạo ra hai cách hiểu khác nhau về dữ liệu vừa lưu.

### 8.3. AfterSave không có nghĩa after commit

MongoDB `AfterSaveCallback` chạy sau khi domain object được lưu và có thể trả cùng hoặc một instance đã thay đổi. [AfterSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/AfterSaveCallback.html).

Việc callback có chữ “after” không tự chứng minh transaction bao ngoài đã commit. Một thay đổi chỉ làm trên entity trả về ở giai đoạn này không cập nhật ngược lệnh ghi đã hoàn tất. Tương tự, lỗi xuất hiện sau một lệnh ghi không đủ để kết luận dữ liệu chắc chắn đã rollback nếu đường chạy không có bảo đảm transaction tương ứng.

Không gọi lại `repository.save` trong cùng callback để “bảo đảm bản sao được lưu”. Cách đó có thể đi vào một vòng callback khác và tạo đệ quy hoặc ghi lặp. Hãy chọn checkpoint phù hợp với mục tiêu thay đổi ngay từ đầu.

## 9. Reactive callback phải phát entity kế tiếp

### 9.1. Implementation reactive riêng

```java
import java.util.Locale;
import org.reactivestreams.Publisher;
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
@Order(10)
public final class ReactiveNormalizeCatalogItemCallback
        implements ReactiveBeforeConvertCallback<CatalogItem> {

    @Override
    public Publisher<CatalogItem> onBeforeConvert(
            CatalogItem item, String collection) {

        return Mono.fromSupplier(() -> {
            String normalizedSku = item.sku().strip().toUpperCase(Locale.ROOT);
            return item.withSku(normalizedSku);
        });
    }
}
```

Khác biệt không nằm ở phép chuẩn hóa mà ở hợp đồng trả về: callback trả `Publisher` phát domain object để tiếp tục persistence. [ReactiveBeforeConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/ReactiveBeforeConvertCallback.html).

Ví dụ reactive này chỉ cài đặt quy tắc chuẩn hóa SKU. Nếu ứng dụng reactive cũng cần điền tên mặc định, phải có xử lý reactive tương ứng; callback đồng bộ ở mục 5 không tự trở thành callback reactive.

### 9.2. Giữ giá trị trong cùng pipeline

Với reactive repository, có thể sử dụng kết quả lưu như sau:

```java
return reactiveRepository.save(draft)
        .map(saved -> new CatalogItemView(
                saved.id(), saved.sku(), saved.displayName(), saved.version()));
```

Trong đó DTO kết quả có thể là:

```java
public record CatalogItemView(
        String id, String sku, String displayName, Long version) {}
```

Không đổi giá trị cuối thành draft:

```java
// Bỏ mất entity do đường lưu phát ra.
return reactiveRepository.save(draft).thenReturn(draft);
```

Dòng trên vẫn chờ publisher lưu hoàn tất, nhưng kết quả trả cho tầng tiếp theo là draft cũ do chính ứng dụng chọn.

### 9.3. Những giá trị trả về không phù hợp

| Cách viết | Vấn đề |
| --- | --- |
| Tạo `Mono` rồi không trả nó | Hạ tầng không nhận được phép biến đổi |
| Gọi `withSku` trong `doOnNext` rồi bỏ kết quả | Chỉ quan sát hoặc chạy tác vụ phụ, không thay phần tử trong stream |
| Trả `Mono.empty()` để nói “không sửa gì” | Không phát entity để đi tiếp; không tương đương trả entity nguyên trạng |
| Trả null thay vì publisher | Vi phạm hợp đồng cung cấp publisher |
| Tự gọi `subscribe()` trong callback | Tách công việc khỏi chuỗi persistence và luồng xử lý lỗi |
| Gọi `.block()` để lấy entity | Phá cách phối hợp reactive và có thể chặn thread |

Nếu không cần sửa, phát entity hiện tại, chẳng hạn `Mono.just(item)`. Nếu có lỗi cần từ chối lưu, biểu diễn lỗi trong pipeline phù hợp. Đặt hợp đồng một entity đầu vào tạo ra một entity hợp lệ cho bước tiếp theo; không dùng callback như một bộ lọc ngầm làm mất entity.

## 10. Phạm vi đăng ký và giới hạn giữa các store

Các lớp `@Component` trong ví dụ cần được đăng ký trong application context mà template/repository sử dụng. Nếu ứng dụng tạo template riêng và tự cấu hình callbacks, cần nối đúng các instance vào template đó.

Không kết luận callback hoạt động chỉ vì gọi trực tiếp phương thức `onBeforeConvert` thấy đúng kết quả. Lời gọi trực tiếp mới kiểm chứng logic của lớp, chưa xác nhận hạ tầng persistence đã phát hiện callback hoặc gọi đúng checkpoint.

Các giới hạn cần giữ rõ:

| Tình huống | Điều không nên tự suy ra |
| --- | --- |
| Dùng MongoDB callback trong ứng dụng JPA | Provider JPA sẽ tự gọi interface đó |
| Đã có callback đồng bộ | Reactive template cũng sử dụng callback đó |
| Lưu entity chạy callback | Mọi bulk update hoặc thao tác driver trực tiếp đều chạy cùng callback |
| Chuẩn hóa SKU khi lưu | Tham số của derived query hoặc Query by Example tự được chuẩn hóa |
| Đọc entity có callback | Mọi projection hoặc kết quả tổng hợp đều có cùng lifecycle |
| Có callback trên aggregate root | Mọi giá trị lồng bên trong luôn được gọi riêng như root |

Ví dụ, lưu SKU dạng `SKU-204` không bảo đảm `findBySku("sku-204")` sẽ tự đổi đầu vào sang chữ hoa. Cần áp dụng hợp đồng mã hàng cả ở điểm xây điều kiện truy vấn, hoặc dùng cơ chế so sánh phù hợp với store.

Commons cung cấp abstraction dùng chung; module quyết định đường đọc/ghi nào có checkpoint tương ứng. Chọn interface và chữ ký theo đúng module thay vì dựa vào việc tên lớp đều chứa `BeforeSave`.

## 11. Tính ổn định của phép biến đổi

### 11.1. Nên tránh biến đổi tích lũy ngoài ý muốn

Quy tắc chuẩn hóa của ví dụ có tính lặp ổn định:

```text
normalize(normalize(item)) có cùng giá trị nghiệp vụ với normalize(item)
```

Đó là đặc tính hữu ích khi entity có thể được lưu nhiều lần. Một callback thêm tiền tố hoặc hậu tố vô điều kiện có thể tạo dữ liệu khác sau mỗi lần lưu:

```text
SKU-204 -> SKU-204-X -> SKU-204-X-X
```

Nếu sự tăng dần đó không phải yêu cầu nghiệp vụ, cần thay quy tắc thay vì trông chờ callback chỉ chạy đúng một lần trong suốt đời entity.

### 11.2. Entity bất biến không làm callback tự an toàn khi chạy đồng thời

Một callback bean thường được dùng lại cho nhiều lời gọi. Không giữ entity hiện tại vào field như `lastProcessedItem` rồi dùng field đó để tạo kết quả. Các lời gọi có thể xen kẽ nhau dù từng record riêng lẻ là bất biến.

Giữ phép biến đổi dựa trên tham số đầu vào và dependency có hợp đồng rõ ràng. Với quy tắc đơn giản, dữ liệu tạm nên nằm trong local variable.

Nếu callback cần thời gian hoặc giá trị cấu hình, làm rõ thời điểm lấy và chính sách khi retry. Không dùng immutable copy để che việc một phép biến đổi có tác dụng phụ thay đổi mỗi lần chạy.

## 12. Bài thực hành và các điểm kiểm chứng

### 12.1. Quan sát chuỗi callback không cần database

Có thể tạo bộ quản lý callback riêng để quan sát giá trị trả về:

```java
import org.springframework.data.mapping.callback.EntityCallbacks;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;

CatalogItem draft = new CatalogItem(null, "  sku-204  ", null, null);

EntityCallbacks callbacks = EntityCallbacks.create(
        new NormalizeCatalogItemCallback(),
        new DefaultCatalogItemNameCallback());

CatalogItem prepared = callbacks.callback(
        BeforeConvertCallback.class, draft, "catalog_items");
```

Kỳ vọng của bài thực hành:

```text
Draft:
  sku         = "  sku-204  "
  displayName = null

Prepared:
  sku         = "SKU-204"
  displayName = "SKU-204"
```

Bộ quản lý callback nhận và trả entity; thao tác này chưa lưu dữ liệu và không tự thực hiện quy trình sinh ID/version của MongoDB. Vì vậy không dùng kết quả bài thử này làm bằng chứng cho mapping hay persistence.

### 12.2. Kiểm chứng qua repository hoặc template

Trong một ứng dụng tích hợp thực tế, các tình huống sau giúp kiểm chứng đầy đủ hơn:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Callback tạo bản sao | Original không đổi, kết quả có dữ liệu mới |
| Hai callback nối tiếp | Callback thứ hai nhận giá trị do callback đầu trả |
| Entity đã có ID/version | Bản sao bảo toàn metadata không thuộc trách nhiệm sửa |
| SKU đã chuẩn hóa | Giá trị không tiếp tục thay đổi khi chạy lại quy tắc |
| Tên hiển thị do người dùng cung cấp | Không bị callback mặc định ghi đè |
| Lưu rồi đọc lại | Dữ liệu trong store khớp thay đổi cần persistence |
| Trả entity ở BeforeSave | Phân biệt dữ liệu trả về với document thực sự được ghi |
| Reactive save | DTO được tạo từ entity phát ra bởi `save`, không từ draft |
| Đường update trực tiếp | Xác nhận có hoặc không có checkpoint theo hợp đồng store |

Nên kiểm tra giá trị của ID, SKU, tên và version theo từng kỳ vọng, thay vì chỉ so sánh toàn bộ record với draft. Sau khi lưu, một số giá trị được persistence quản lý có thể khác ban đầu dù logic callback hoàn toàn đúng.

Với đối tượng bất biến, giá trị trả về nối các trạng thái lại thành một luồng xử lý rõ ràng: callback trả entity kế tiếp, hạ tầng dùng entity đó tại checkpoint phù hợp và caller tiếp tục từ kết quả của persistence. Giữ đúng ba điểm nối này giúp tránh việc dữ liệu mới chỉ tồn tại trong một bản sao bị bỏ quên hoặc trong kết quả trả về không khớp dữ liệu đã lưu.
