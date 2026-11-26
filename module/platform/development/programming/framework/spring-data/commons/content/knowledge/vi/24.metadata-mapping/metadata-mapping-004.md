# IdentifierAccessor và cách đọc định danh

Trong hạ tầng ánh xạ của Spring Data Commons, `IdentifierAccessor` cung cấp một cách đọc định danh từ một đối tượng miền mà không buộc code gọi phải biết tên field, tên getter hoặc chi tiết truy cập thuộc tính. Accessor được lấy từ metadata của entity và gắn với một đối tượng cụ thể.

Abstraction này hữu ích khi xây các thành phần dùng chung như xử lý sự kiện, bộ chuyển đổi hoặc tiện ích metadata. Thay vì luôn tìm một field tên `id`, thành phần dùng mapping metadata để hỏi: “Định danh của đối tượng này là gì?”.

Việc đọc định danh cần được phân biệt với sinh ID, kiểm tra bản ghi có tồn tại, xác định entity mới và chuyển đổi ID sang biểu diễn của store. Bài học làm rõ các ranh giới đó, dùng MongoDB làm ví dụ cho metadata triển khai cụ thể.

## 1. Hợp đồng nhỏ của IdentifierAccessor

Interface thuộc package:

```java
import org.springframework.data.mapping.IdentifierAccessor;
```

Hai phương thức cần nắm:

| Phương thức | Kiểu kết quả | Khi không có định danh |
| --- | --- | --- |
| `getIdentifier()` | `Object`, có thể null | Trả null |
| `getRequiredIdentifier()` | `Object` bắt buộc khác null | Ném `IllegalStateException` |

`IdentifierAccessor` không có tham số generic cho kiểu ID. Vì vậy, kết quả được khai báo là `Object`, dù giá trị thực tế có thể là `String`, `Long`, UUID hoặc một kiểu định danh khác.

Ví dụ với một accessor đã được lấy đúng cách:

```java
Object nullableId = accessor.getIdentifier();
Object requiredId = accessor.getRequiredIdentifier();
```

Không có ID là một trạng thái mà `getIdentifier()` cho phép biểu diễn. Biến thể required được dùng khi tại thời điểm đó ứng dụng yêu cầu đối tượng phải có định danh.

### “Required” chỉ yêu cầu có giá trị

`getRequiredIdentifier()` không phải một bộ validation nghiệp vụ. Nếu accessor trả một chuỗi rỗng hoặc một số 0 khác null, phương thức required không tự hiểu rằng giá trị đó không hợp lệ đối với mọi miền nghiệp vụ.

Nó cũng không xác minh ID là duy nhất, thuộc đúng tenant hoặc trỏ tới một bản ghi đang tồn tại. Những yêu cầu đó phải được giải quyết ở lớp thích hợp của ứng dụng và store.

## 2. Lấy accessor từ PersistentEntity

Cách dùng thông thường là để metadata cung cấp accessor:

```java
import org.springframework.data.mapping.IdentifierAccessor;
import org.springframework.data.mapping.PersistentEntity;

IdentifierAccessor accessor = persistentEntity.getIdentifierAccessor(entity);
Object id = accessor.getIdentifier();
```

Trong đoạn mã, `persistentEntity` là metadata phù hợp với domain type và `entity` là đối tượng cụ thể của domain type đó.

Luồng trách nhiệm có thể hình dung như sau:

```text
MappingContext của module
          |
          v
PersistentEntity cho domain type
          |
          +--> Thuộc tính nào là ID?
          +--> Dùng cơ chế truy cập nào?
          +--> Có chiến lược accessor chuyên biệt không?
          |
          v
IdentifierAccessor gắn với một entity
          |
          v
Giá trị định danh hoặc trạng thái không có ID
```

Không nên khởi tạo một implementation nội bộ của accessor chỉ để bỏ qua metadata. Cách truy cập phù hợp có thể phụ thuộc field, property, mô hình bất biến hoặc các đặc điểm mà module đã xử lý.

### Phân biệt metadata dùng chung và accessor gắn với object

Một `PersistentEntity` mô tả một domain type và có thể được mapping context quản lý, tái sử dụng. Một accessor lại được tạo cho một đối tượng cụ thể.

Không lưu một accessor của đơn hàng A vào một field dùng chung rồi dùng nó để đọc ID của đơn hàng B. Lời gọi `getIdentifier()` không nhận entity mới; nó đọc định danh qua đối tượng mà accessor đang gắn với.

## 3. Ví dụ MongoDB: thuộc tính ID không có tên là id

### 3.1. Mô hình minh họa

```java
package example.orders;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class PurchaseOrder {

    @Id
    private String orderNumber;

    private String description;

    public PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber, String description) {
        this.orderNumber = orderNumber;
        this.description = description;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }
}
```

Thuộc tính định danh Java là `orderNumber`, được đánh dấu bằng annotation mà mapping MongoDB hỗ trợ. Không có field tên `id`.

Ví dụ này thuộc module MongoDB. Không áp annotation `org.springframework.data.annotation.Id` cho JPA rồi mặc định nó thay thế `jakarta.persistence.Id`; mỗi module nhận diện mapping theo cơ chế của mình.

### 3.2. Lấy metadata và đọc ID

Giả sử thành phần đã được ứng dụng cung cấp `MongoMappingContext mappingContext` từ cấu hình MongoDB:

```java
import org.springframework.data.mapping.IdentifierAccessor;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;
import org.springframework.data.mongodb.core.mapping.MongoPersistentEntity;

MongoPersistentEntity<?> metadata =
    mappingContext.getRequiredPersistentEntity(PurchaseOrder.class);

PurchaseOrder order = new PurchaseOrder(
    "ORD-2026-0042",
    "Đơn hàng bàn phím"
);

IdentifierAccessor accessor = metadata.getIdentifierAccessor(order);

Object id = accessor.getIdentifier();
Object requiredId = accessor.getRequiredIdentifier();
```

Ở đây cả `id` và `requiredId` đều chứa giá trị Java `"ORD-2026-0042"`. Metadata giúp code tìm đúng thuộc tính đã được ánh xạ làm định danh, không phải tự dò một field có tên cố định.

Nếu cần biết tên thuộc tính Java để mô tả metadata, có thể kiểm tra:

```java
if (metadata.hasIdProperty()) {
    String propertyName = metadata.getIdProperty().getName();
}
```

Trong mô hình trên, tên đó là `orderNumber`. Việc kiểm tra có thuộc tính ID giúp tránh giả định mọi domain type đều khai báo một property định danh thông thường.

### 3.3. ID null trước khi lưu

```java
PurchaseOrder pending = new PurchaseOrder(null, "Đơn hàng mới");
IdentifierAccessor pendingAccessor = metadata.getIdentifierAccessor(pending);

Object idBeforeSave = pendingAccessor.getIdentifier();
```

`idBeforeSave` là null. Đọc ID không tự kích hoạt cơ chế sinh định danh, không thực hiện insert và không tự gọi repository.

Nếu tiếp tục gọi `pendingAccessor.getRequiredIdentifier()`, phương thức báo lỗi vì yêu cầu có ID chưa được đáp ứng. Điều này khác với lỗi không tìm được metadata của `PurchaseOrder`.

## 4. Không nhầm tên thuộc tính Java với tên lưu trữ

Trong ví dụ MongoDB, thuộc tính Java `orderNumber` đóng vai trò định danh và được hạ tầng mapping ánh xạ tới trường định danh của document.

Cần giữ rõ các lớp thông tin:

| Thông tin | Ví dụ | Nơi chịu trách nhiệm |
| --- | --- | --- |
| Tên thuộc tính Java | `orderNumber` | Domain model và mapping metadata |
| Giá trị Java đọc từ object | `"ORD-2026-0042"` | IdentifierAccessor |
| Tên trường định danh trong MongoDB | `_id` | Quy tắc mapping của MongoDB |
| Biểu diễn vật lý của giá trị | String, ObjectId hoặc dạng phù hợp với mapping | Converter và store |

`IdentifierAccessor` đọc giá trị trong mô hình Java. Nó không mặc định trả về giá trị đã được converter chuyển sang dạng BSON hoặc kiểu vật lý của một database khác.

Chẳng hạn, với một mapping cho phép chuyển ID Java dạng String sang một biểu diễn khác khi ghi, việc đọc qua accessor vẫn phải được hiểu ở tầng object. Không tự ép kết quả sang kiểu lưu trữ vật lý chỉ vì biết store đang dùng kiểu đó ở phía dưới.

Tương tự, không đưa tên `_id` vào code reflection để tìm field trong `PurchaseOrder`. Tên lưu trữ và tên thuộc tính không phải một khái niệm.

## 5. Chọn nullable hay required theo đúng thời điểm

### 5.1. Đọc nullable khi chưa có ID là trạng thái hợp lệ

Những tình huống phù hợp gồm:

- Đối tượng mới chưa đi qua cơ chế sinh ID.
- Thành phần chẩn đoán cần mô tả có hay chưa có định danh.
- Logic chuẩn bị dữ liệu cần giữ nguyên sự khác biệt giữa thiếu ID và có ID.

Có thể chuyển giá trị nullable thành Optional tại ranh giới tiện ích:

```java
import java.util.Optional;

Optional<Object> id = Optional.ofNullable(accessor.getIdentifier());
```

Optional rỗng ở đây có nghĩa accessor không cung cấp ID khác null. Nó không có nghĩa đối tượng không tồn tại trong bộ nhớ hoặc chắc chắn không có bản ghi tương ứng trong database.

### 5.2. Đọc required khi hợp đồng đã yêu cầu ID

Ví dụ, sau một bước lưu thành công theo hợp đồng của store, thành phần tiếp theo có thể cần ID để tạo thông tin tham chiếu. Khi đó, yêu cầu bắt buộc được diễn đạt rõ hơn bằng:

```java
Object id = accessor.getRequiredIdentifier();
```

Nếu ID vẫn thiếu, lỗi làm lộ một giả định chưa được đáp ứng thay vì tạo một chuỗi giả như `"null"`.

Không dùng:

```java
String id = String.valueOf(accessor.getIdentifier());
```

để xử lý mọi kiểu ID và mọi trường hợp vắng mặt. Với giá trị null, `String.valueOf(...)` tạo chuỗi `"null"`, làm mất thông tin rằng chưa có định danh. Với ID phức hợp, chuỗi `toString()` cũng chưa chắc là định dạng dùng để tra cứu hoặc truyền qua API.

## 6. Quản lý kiểu dữ liệu khi kết quả là Object

Ép kiểu chỉ an toàn khi đã biết mapping và kiểu ID:

```java
Object rawId = accessor.getRequiredIdentifier();

if (!(rawId instanceof String)) {
    throw new IllegalStateException("Mong đợi định danh Java kiểu String");
}

String orderNumber = (String) rawId;
```

Không ép sang `Long` chỉ vì các entity khác trong hệ thống dùng ID số. Domain type khác nhau có thể có ID khác nhau.

Một tiện ích dùng chung có thể nhận kiểu mong đợi và kiểm tra tường minh:

```java
import java.util.Objects;
import java.util.Optional;

import org.springframework.data.mapping.PersistentEntity;

public final class IdentifierReaders {

    private IdentifierReaders() {
    }

    public static <ID> Optional<ID> read(
            PersistentEntity<?, ?> metadata,
            Object entity,
            Class<ID> expectedIdType) {

        Objects.requireNonNull(metadata, "metadata không được null");
        Objects.requireNonNull(entity, "entity không được null");
        Objects.requireNonNull(expectedIdType, "Thiếu kiểu ID mong đợi");

        if (expectedIdType.isPrimitive()) {
            throw new IllegalArgumentException(
                "Dùng kiểu wrapper khi kiểm tra kiểu của giá trị ID"
            );
        }

        Object rawId = metadata.getIdentifierAccessor(entity).getIdentifier();

        if (rawId == null) {
            return Optional.empty();
        }

        if (!expectedIdType.isInstance(rawId)) {
            throw new IllegalStateException(
                "Kiểu ID thực tế không khớp với kiểu Java mong đợi"
            );
        }

        return Optional.of(expectedIdType.cast(rawId));
    }
}
```

Sử dụng với metadata MongoDB ở ví dụ:

```java
Optional<String> orderNumber = IdentifierReaders.read(
    metadata,
    order,
    String.class
);
```

Tiện ích phân biệt hai trạng thái: thiếu giá trị ID trả Optional rỗng; có ID nhưng sai kiểu là lỗi. Không nuốt lỗi kiểu dữ liệu rồi trả Optional rỗng, vì như vậy cấu hình sai bị biến thành trạng thái vắng mặt bình thường.

`Long.class` phù hợp khi kiểm tra một giá trị được trả về dưới dạng object; `long.class` không biểu diễn một wrapper instance cho `Class.isInstance(...)`. Đó là lý do helper từ chối kiểu primitive làm kiểu mong đợi.

Helper này chỉ đọc và kiểm tra kiểu. Nó không chuyển String sang UUID, không parse ID số và không thay converter của store.

## 7. Trường hợp có ID property, Persistable hoặc không có ID

Metadata phổ biến trong Commons, như `BasicPersistentEntity`, có thể cung cấp accessor theo đặc điểm của domain type. Không phải mọi trường hợp đều đơn giản là đọc một field có annotation.

### 7.1. Domain type có thuộc tính định danh được ánh xạ

Accessor có thể dùng cơ chế truy cập property của mapping infrastructure để đọc đúng giá trị. Thuộc tính có thể được truy cập qua field hoặc property theo metadata và khả năng của module.

Lợi ích là thành phần gọi không phải tự giải quyết mọi khác biệt giữa field private, getter hay cơ chế truy cập được tối ưu. Tuy vậy, mapping sai vẫn có thể gây lỗi; accessor không tự sửa một domain model không tương thích với store.

### 7.2. Domain type triển khai Persistable

Commons có interface `Persistable<ID>` với `getId()` và `isNew()`. Trong metadata hỗ trợ chiến lược này, accessor có thể lấy định danh bằng hợp đồng `getId()` của đối tượng.

Do đó, chỉ tìm một field ID bằng reflection có thể bỏ qua cách đọc mà metadata đã lựa chọn. Cũng không nên kết luận mọi kiểu không có ID property thông thường đều không thể có định danh qua một cơ chế accessor được hỗ trợ.

`Persistable.getId()` và `Persistable.isNew()` là hai thông tin khác nhau. Một entity có ID được ứng dụng gán trước vẫn có thể chủ động được coi là mới theo chiến lược vòng đời của nó.

### 7.3. Không có định danh mà accessor có thể cung cấp

Với một đối tượng thông thường không có mapping ID và không có cơ chế định danh thay thế mà metadata hỗ trợ, accessor có thể biểu diễn trạng thái không có ID. `getIdentifier()` trả null; biến thể required báo lỗi.

Không nhầm điều này với việc store hoàn toàn không có định danh vật lý. Chẳng hạn, một document có thể có trường định danh ở phía lưu trữ nhưng domain type không ánh xạ giá trị đó trở lại một thuộc tính. Đọc định danh từ object và kiểm tra cấu trúc document là hai công việc khác nhau.

## 8. Accessor không phải snapshot và không chuyển sang instance mới

Accessor gắn với object được truyền vào lúc lấy nó. Không coi việc tạo accessor là thao tác sao chép sâu trạng thái entity.

Với đối tượng mutable và cơ chế truy cập property thông thường:

```java
PurchaseOrder order = new PurchaseOrder("ORD-A", "Đơn mẫu");
IdentifierAccessor accessor = metadata.getIdentifierAccessor(order);

Object firstRead = accessor.getIdentifier();

order.setOrderNumber("ORD-B");

Object laterRead = accessor.getIdentifier();
```

Ví dụ thể hiện vì sao không nên xem accessor như một snapshot ID bất biến. Việc cố ý thay ID của entity đã lưu còn có ý nghĩa persistence riêng và không phải thao tác được khuyến khích trong luồng nghiệp vụ.

Nếu cần giữ giá trị ở một thời điểm để so sánh, hãy giữ giá trị đã đọc theo hợp đồng của kiểu ID, thay vì giữ accessor rồi giả định lần đọc sau chắc chắn phản ánh trạng thái cũ.

### Đối tượng bất biến hoặc kết quả save là instance khác

Một số luồng lưu hoặc cập nhật trả về instance khác với đầu vào. Accessor của instance cũ không tự chuyển sang instance mới.

Ví dụ repository MongoDB có thể khai báo:

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PurchaseOrderRepository
        extends MongoRepository<PurchaseOrder, String> {
}
```

Sau thao tác lưu, đọc trên kết quả trả về:

```java
PurchaseOrder saved = repository.save(pending);

Object savedId = metadata
    .getIdentifierAccessor(saved)
    .getRequiredIdentifier();
```

`repository` là `PurchaseOrderRepository` được ứng dụng cung cấp. Đoạn mã giả định cơ chế lưu thành công đã tạo hoặc giữ một ID phù hợp với mapping. Việc sử dụng `saved` tuân theo hợp đồng repository thay vì dựa vào giả định rằng instance đầu vào luôn được cập nhật tại chỗ.

Accessor chỉ có chức năng đọc ID. Khi cần ghi thuộc tính trong hạ tầng mapping, đó là trách nhiệm khác, có thể liên quan `PersistentPropertyAccessor` và cơ chế cập nhật object của module. Không tìm một setter ID trên `IdentifierAccessor` vì interface này không định nghĩa thao tác đó.

## 9. Không dùng IdentifierAccessor để suy ra isNew

Một cách suy luận quá đơn giản là:

```java
boolean isNew = accessor.getIdentifier() == null;
```

Dòng này chỉ thể hiện một quy tắc do người viết tự đặt. Nó không bảo đảm giống chiến lược mới của repository đang dùng.

Trạng thái mới có thể được xác định từ:

- ID theo quy tắc của module.
- Thuộc tính version với cách xử lý primitive hoặc wrapper tương ứng.
- `Persistable.isNew()`.
- Một chiến lược metadata tùy chỉnh được hạ tầng sử dụng.

Vì vậy, nếu cần đúng quyết định mà repository dùng, phải sử dụng abstraction trạng thái mới phù hợp như `EntityInformation.isNew(...)` hoặc cơ chế mapping tương ứng của module, thay vì tự suy từ một lần đọc ID.

Cũng không có chiều suy ngược rằng ID khác null thì bản ghi chắc chắn tồn tại. Một assigned ID có thể đã được đặt trước lần ghi đầu tiên; một đối tượng khác có thể mang ID của bản ghi đã bị xóa.

`IdentifierAccessor` không cung cấp hợp đồng kiểm tra tồn tại trong database. Nếu một trường hợp sử dụng cần tra cứu tồn tại, đó là một thao tác truy cập store riêng và vẫn phải xét khả năng dữ liệu thay đổi giữa các lần đọc, ghi.

## 10. Phân biệt với EntityInformation và PersistentPropertyAccessor

| Abstraction | Phạm vi chính | Điều không nên suy ra |
| --- | --- | --- |
| `IdentifierAccessor` | Đọc ID từ một object đã gắn với accessor | Không tự quyết định entity mới hoặc sinh ID |
| `EntityInformation<T, ID>` | Thông tin kiểu miền, kiểu ID, cách lấy ID và trạng thái mới | Không phải bản thân object entity |
| `PersistentEntity` | Metadata mapping của một domain type và cách lấy accessor | Không bảo đảm mọi object được truyền vào đều tương thích |
| `PersistentPropertyAccessor` | Truy cập các thuộc tính theo mapping, gồm các khả năng khác với chỉ đọc ID | Không tự cấp quyền sửa dữ liệu |
| Converter của store | Chuyển đổi giữa biểu diễn Java và biểu diễn lưu trữ | Không đồng nhất với việc đọc nguyên giá trị ID từ object |

Các phương thức required cũng không nên bị gộp thành một API duy nhất. `IdentifierAccessor.getRequiredIdentifier()` và `EntityInformation.getRequiredId(entity)` có tên, kiểu khai báo và hợp đồng lỗi riêng. Khi viết tầng tích hợp, xử lý đúng abstraction đang dùng thay vì bắt lỗi theo tên gần giống nhau.

Trong một ứng dụng JPA, metadata chuyên biệt của JPA có thể là điểm truy cập phù hợp hơn cho một số nhu cầu. Không giả định mọi JPA entity đều được quản lý bằng `MongoMappingContext` hoặc có cùng cơ chế lấy metadata như ví dụ document trong bài.

## 11. Chọn domain type và xử lý proxy đúng cách

Lấy metadata bằng runtime class của object có thể gây nhầm khi object là proxy hoặc một lớp do framework tạo ra. Tên runtime class chưa chắc chính là domain type mà mapping context được cấu hình quản lý.

Nếu thành phần đã biết repository hoặc domain type, nên dùng thông tin đó để tìm metadata phù hợp:

```java
MongoPersistentEntity<?> metadata =
    mappingContext.getRequiredPersistentEntity(PurchaseOrder.class);
```

Đây không phải yêu cầu luôn hardcode lớp trong mọi thành phần dùng chung. Một tiện ích tổng quát có thể nhận domain type hoặc metadata từ nơi đã biết ngữ cảnh, thay vì tự suy bằng `object.getClass()` trong mọi trường hợp.

Nếu truyền object sai loại vào metadata, hãy coi đó là lỗi hợp đồng. Không bắt lỗi rồi trả null như thể entity chỉ chưa có ID.

Cần phân biệt tối thiểu các tình huống:

| Tình huống | Cách diễn giải |
| --- | --- |
| Không lấy được metadata cho domain type cần xử lý | Vấn đề tra cứu hoặc cấu hình mapping |
| Metadata và object không tương thích | Lỗi chọn kiểu hoặc truyền đối tượng |
| Có accessor nhưng ID chưa được gán | Trạng thái giá trị vắng mặt có thể hợp lệ |
| Có ID nhưng kiểu khác dự kiến | Sai giả định kiểu hoặc mapping cần được đối chiếu |
| Đọc required trong lúc ID còn thiếu | Yêu cầu bắt buộc có ID chưa được đáp ứng |

Việc tách những tình huống này giúp lỗi cấu hình không bị che thành một Optional rỗng thông thường.

## 12. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Không đọc được ID khi field tên khác id | Tự tìm field bằng tên cố định | Dùng metadata và IdentifierAccessor |
| Ép kiểu gây ClassCastException | Giả định mọi entity dùng cùng kiểu ID | Kiểm tra kiểu Java mong đợi trước khi cast |
| ID bị biến thành chuỗi `"null"` | Dùng String.valueOf để xử lý vắng mặt | Giữ null, Optional hoặc yêu cầu required theo hợp đồng |
| ID vẫn thiếu sau khi tạo accessor | Tưởng accessor tự sinh định danh | Xác định đúng thời điểm và cơ chế gán ID của store |
| Đọc ID cũ sau một thao tác trả instance mới | Giữ accessor của object đầu vào | Lấy accessor cho kết quả mà thao tác trả về |
| Một request đọc ID của request khác | Chia sẻ accessor gắn với object qua trạng thái dùng chung | Tạo accessor theo object của lần xử lý |
| ID Java bị ép sang kiểu BSON hoặc SQL | Nhầm đọc giá trị với chuyển đổi lưu trữ | Để converter thực hiện nhiệm vụ ánh xạ |
| Entity bị phân loại mới sai | Tự coi ID null là toàn bộ chiến lược isNew | Dùng cơ chế xác định mới của module |
| Metadata lookup thất bại với proxy | Suy domain type từ runtime class không phù hợp | Dùng domain type hoặc metadata từ ngữ cảnh quản lý |
| Lỗi mapping bị báo thành không có ID | Bắt mọi exception rồi trả null | Tách lỗi cấu hình, lỗi kiểu và giá trị chưa có |

Đọc ID cũng không xác nhận quyền truy cập hoặc quyền ghi. Một entity có định danh hợp lệ vẫn có thể thuộc phạm vi người gọi không được sửa; kiểm tra đó cần nằm trong luồng nghiệp vụ phù hợp.

## 13. Tự thực hành đối chiếu cách đọc định danh

Dùng một module đã cấu hình mapping phù hợp và lần lượt quan sát:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Thuộc tính ID tên `orderNumber` | Accessor lấy đúng giá trị dù không có field tên id |
| Đối tượng có ID null | getIdentifier trả null, không tự sinh ID |
| Cùng object được đọc bằng biến thể required | Trạng thái thiếu ID được báo rõ bằng lỗi hợp đồng |
| ID có giá trị nhưng không đúng kiểu helper mong đợi | Không bị biến thành Optional rỗng |
| Tên thuộc tính Java khác tên trường lưu trữ | Giá trị đọc ở tầng Java không bị nhầm với tên hoặc kiểu vật lý |
| Entity dùng assigned ID trước khi lưu | Có ID chưa chứng minh tồn tại trong store |
| Object được thay bằng kết quả save | Accessor mới gắn với đúng instance cần đọc |
| Metadata nhận object khác domain type | Lỗi kiểu được tách khỏi trường hợp chưa có ID |
| Domain type triển khai Persistable | Hiểu cơ chế đọc getId mà metadata hỗ trợ và sự độc lập với isNew |

`IdentifierAccessor` giữ việc đọc định danh nhỏ và rõ: nhận accessor phù hợp từ metadata, đọc giá trị trên đúng object, rồi xử lý trạng thái có hoặc chưa có ID theo hợp đồng của bước hiện tại. Những quyết định về sinh ID, chuyển đổi lưu trữ, trạng thái mới và quyền thao tác dữ liệu cần được giao cho đúng thành phần của Spring Data và ứng dụng.