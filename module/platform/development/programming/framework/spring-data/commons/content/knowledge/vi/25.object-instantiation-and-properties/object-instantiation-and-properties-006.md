# Entity bất biến, phương thức wither và bản sao có ID

## 1. Vì sao entity bất biến vẫn có thể nhận ID mới?

Một entity có thể chưa có ID khi ứng dụng tạo nó, nhưng có ID sau khi được lưu. Với entity mutable, framework có thể cập nhật field hoặc gọi setter. Với entity immutable, cách biểu diễn thay đổi là tạo một object mới chứa ID và giữ lại phần trạng thái còn lại.

```text
Trước khi lưu:
  O1 = PurchaseOrder(id = null, orderNumber = "PO-001", ...)

Datastore sinh và trả identifier:
  id = 101L

Sau khi hoàn tất lưu và ánh xạ kết quả:
  O2 = PurchaseOrder(id = 101L, orderNumber = "PO-001", ...)
```

`O1` không cần bị sửa. `O2` là một snapshot khác, phản ánh trạng thái đã nhận ID. Một phương thức **wither**, chẳng hạn `withId`, có thể cung cấp đường tạo bản sao này cho hạ tầng mapping.

Trong chương **Khởi tạo và gán thuộc tính** của **SPRING_DATA_COMMONS**, chủ đề này nối ba kiến thức: metadata nhận diện identifier, cơ chế cập nhật thuộc tính immutable và hợp đồng trả kết quả của repository. Điểm cần nhớ ngay từ đầu là: **hãy sử dụng entity mà thao tác lưu trả về**.

Phạm vi áp dụng phải được xác định theo module. Commons cung cấp abstraction và hạ tầng mapping chung; khả năng sinh ID, kiểu ID, cách population và callback phụ thuộc datastore. Với Spring Data JPA, entity còn chịu quy tắc của JPA và persistence provider. Không thể suy ra rằng mọi lớp `final` chỉ có constructor đầy đủ đều trở thành một JPA entity hợp lệ.

## 2. Bất biến là bất biến trạng thái, không phải không có chuyển đổi

### 2.1. Những đặc điểm thường thấy

Một thiết kế immutable thường có:

- Field được gán trong constructor và không thay đổi sau đó.
- Không có setter làm thay đổi trạng thái object hiện tại.
- Phương thức cập nhật trả một object mới.
- Không để collection hoặc object mutable bên trong bị sửa từ bên ngoài.

`final` là một phần của thiết kế, nhưng chưa đủ để bảo đảm toàn bộ trạng thái bất biến:

```java
private final List<OrderLine> lines;
```

Field này không thể trỏ sang list khác sau khi constructor hoàn tất. Tuy nhiên, nếu list vẫn mutable và được lộ trực tiếp, phần tử của nó vẫn có thể bị thêm hoặc xóa.

Có thể dùng `List.copyOf` để lấy một bản chụp list không cho phép sửa qua API list. Nhưng phép sao chép đó không biến từng phần tử mutable thành immutable. Ví dụ trong bài dùng `OrderLine` chỉ chứa `String` và `int`, giúp trạng thái bên trong đơn giản và ổn định.

### 2.2. Mỗi bản sao đại diện cho một trạng thái

```text
O1: chưa có ID
O2: đã có ID
O3: đã có ID, danh sách hàng đã thay đổi
```

Có thể cả ba cùng liên quan đến một vòng đời nghiệp vụ. Điều đó không yêu cầu chúng là cùng một object Java.

Bất biến không cấm cập nhật dữ liệu. Nó yêu cầu mỗi lần cập nhật được biểu diễn bằng một giá trị mới, còn giá trị cũ vẫn giữ trạng thái cũ.

## 3. Phân biệt ba khái niệm về identity

| Khái niệm | Ví dụ | Điều cần phân biệt |
|---|---|---|
| Tham chiếu Java | `before == after` | Hai biến có trỏ đúng một object không? |
| Identifier lưu trữ | `id = 101L` | Nhận diện bản ghi/entity trong phạm vi datastore và kiểu tương ứng |
| Khóa nghiệp vụ | `orderNumber = "PO-001"` | Giá trị nghiệp vụ, có thể có quy tắc duy nhất riêng |

Sau khi lưu một entity immutable, `before == after` có thể là `false`, dù hai object cùng thể hiện một đơn hàng ở các thời điểm khác nhau.

Identifier lưu trữ cũng không tự quyết định kết quả `equals`. Nếu class không override `equals`, nó kế thừa semantics so sánh object của `Object`. Nếu class có `equals` riêng hoặc là record, semantics lại phụ thuộc cách định nghĩa đó.

Không dùng một phép kiểm tra tham chiếu để kết luận entity đã được lưu hay chưa. Cũng không xem ID của hai loại entity khác nhau là cùng identity chỉ vì chúng có cùng giá trị số.

## 4. Hợp đồng của một wither

### 4.1. Với thuộc tính `id`, tên thường là `withId`

Một wither điển hình có dạng:

```java
public PurchaseOrder withId(Long id) {
    return new PurchaseOrder(id, this.orderNumber, this.lines);
}
```

Phương thức nhận giá trị mới cho một thuộc tính và trả entity có giá trị đó. Nó không sửa `this`.

Để dễ được hạ tầng mapping nhận diện và sử dụng, nên cung cấp tên và chữ ký rõ ràng theo quy ước:

| Thành phần | Ví dụ |
|---|---|
| Thuộc tính Java | `id` |
| Phương thức | `withId` |
| Tham số | Một giá trị đúng kiểu của `id` |
| Kiểu trả về | Kiểu entity cụ thể |
| Tác dụng | Trả bản sao giữ các thuộc tính khác |

Một phương thức fluent tên `id(...)`, `assignKey(...)` hoặc một builder có `build()` không mặc nhiên là wither của property `id`.

Tên được suy theo **thuộc tính domain**, không phải chỉ theo tên cột/field của datastore. Nếu property Java tên `id` được ánh xạ sang tên lưu trữ `order_id`, không vì vậy mà tự đổi wither thành `withOrderId`.

### 4.2. Wither không phải setter

```java
// Setter: sửa chính object hiện tại.
public void setId(Long id) {
    this.id = id;
}
```

```java
// Wither: trả object có trạng thái mới.
public PurchaseOrder withId(Long id) {
    return new PurchaseOrder(id, this.orderNumber, this.lines);
}
```

Setter ở ví dụ so sánh chỉ phù hợp với field mutable. Không thể dùng nó để gán lại một field `final` sau khi constructor đã hoàn tất.

Với wither, phía gọi phải giữ lại kết quả:

```java
PurchaseOrder identified = draft.withId(101L);
```

Lời gọi dưới đây bỏ mất bản sao:

```java
draft.withId(101L);
```

Sau lời gọi bị bỏ kết quả, biến `draft` vẫn trỏ object cũ. Đây là cùng loại lỗi tư duy như bỏ kết quả của một phép biến đổi trên `String` immutable.

### 4.3. Wither nên là phép tạo giá trị có thể dự đoán

Wither cần bảo toàn trạng thái không được thay đổi. Không nên đặt vào đó thao tác ghi database, phát sự kiện nghiệp vụ hoặc gọi API bên ngoài chỉ vì mapping có thể dùng phương thức này.

Một converter có thể chọn đường tạo object khác tùy ngữ cảnh. Không có lý do để coi việc gọi `withId` là một thông báo chắc chắn rằng một insert vừa hoàn tất.

Có thể tối ưu trả lại `this` khi giá trị không thay đổi nếu thiết kế cho phép. Bởi vậy, hợp đồng wither không bắt buộc mọi lần gọi đều có tham chiếu mới; điều quan trọng là object nhận được biểu diễn trạng thái yêu cầu.

## 5. Ví dụ đầy đủ: đơn hàng immutable

Các kiểu dưới đây minh họa domain Java và các điểm mở rộng mapping. Để chạy với một repository thật, ứng dụng còn cần module lưu trữ, mapping aggregate và cấu hình datastore phù hợp. Kiểu ID `Long` được chọn để minh họa, không phải kiểu ID sinh tự động dùng chung cho mọi datastore.

### 5.1. Giá trị dòng hàng

```java
package com.example.orders;

public record OrderLine(String sku, int quantity) {

    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity < 1) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}
```

Trong ví dụ này, dòng hàng là một value object: không có thao tác thay đổi `sku` hoặc `quantity` của instance hiện tại. Module áp dụng cần hỗ trợ mapping kiểu thành phần tương ứng nếu lưu cả danh sách dòng hàng.

### 5.2. Aggregate có ID nullable trước khi lưu

```java
package com.example.orders;

import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;

public final class PurchaseOrder {

    @Id
    private final Long id;

    private final String orderNumber;

    private final List<OrderLine> lines;

    @PersistenceCreator
    public PurchaseOrder(
            Long id,
            String orderNumber,
            List<OrderLine> lines) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("orderNumber must not be blank");
        }
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("lines must not be empty");
        }
        this.id = id;
        this.orderNumber = orderNumber;
        this.lines = List.copyOf(lines);
    }

    public static PurchaseOrder draft(
            String orderNumber,
            List<OrderLine> lines) {
        return new PurchaseOrder(null, orderNumber, lines);
    }

    public PurchaseOrder withId(Long id) {
        return new PurchaseOrder(id, this.orderNumber, this.lines);
    }

    public PurchaseOrder withLines(List<OrderLine> lines) {
        return new PurchaseOrder(this.id, this.orderNumber, lines);
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
```

Có năm quyết định trong thiết kế:

1. `Long` cho phép biểu diễn trạng thái chưa có ID bằng `null`.
2. Persistence constructor nhận đầy đủ `id`, `orderNumber` và `lines`.
3. Factory `draft` phục vụ ứng dụng tạo đơn mới; nó không được đánh dấu làm persistence creator.
4. `withId` thay identifier nhưng giữ nguyên số đơn và nội dung dòng hàng.
5. `withLines` thay nội dung nhưng giữ identifier hiện tại.

`List.copyOf` chặn sửa cấu trúc list thông qua giá trị trả từ `getLines`. Trong mô hình này, các phần tử `OrderLine` cũng là immutable, nên phía gọi không thể sửa trạng thái dòng hàng đã nằm trong đơn bằng setter.

`@Id` nhận diện property identifier cho mapping hỗ trợ annotation ấy. Nó không tự khai báo sequence, identity column hoặc một bộ sinh `Long` cho mọi module.

### 5.3. Persistence constructor khác factory nghiệp vụ

Khi đọc một đơn đã tồn tại, mapper cần khả năng tạo object có ID sẵn. Vì thế constructor nhận `id` là một lựa chọn rõ ràng:

```text
new PurchaseOrder(101L, "PO-001", linesFromStore)
```

Nếu mapper lại dùng một factory luôn đặt `id = null`, nó sẽ cần một đường bổ sung identifier sau đó. Factory nghiệp vụ và creator dùng để materialize dữ liệu có thể có mục đích khác nhau; không nên đánh dấu creator chỉ theo thói quen.

Tên tham số creator phải có metadata phù hợp để nối với property. Với Java class thông thường, biên dịch kèm tên tham số, chẳng hạn qua tùy chọn `-parameters`, là một cách phổ biến. Annotation chọn creator không tự bù được mọi thông tin tên đang thiếu.

## 6. Lúc đọc và lúc lưu có thể dùng đường khác nhau

### 6.1. Đọc từ datastore: ID có thể đi thẳng qua constructor

Giả sử nguồn dữ liệu đã có:

```text
id          = 101L
orderNumber = "PO-001"
lines       = các dòng hàng đã chuyển đổi
```

Với persistence constructor đầy đủ của `PurchaseOrder`, mapper có thể truyền cả ba giá trị khi tạo object. Khi ấy `id` đã được cung cấp qua creator và không cần population lại bằng `withId` trong lượt đọc thông thường.

Điều này giải thích vì sao đặt breakpoint ở `withId` rồi đọc repository có thể không thấy phương thức chạy, dù entity và mapping hoàn toàn hợp lệ.

### 6.2. Population: wither xử lý phần trạng thái chưa qua creator

Nếu một model khác có creator chưa nhận `id`, identifier có thể được bổ sung sau khi có instance ban đầu. Với thuộc tính immutable và wither phù hợp, hạ tầng mapping có thể dùng wither và thay instance hiện tại bằng kết quả trả về.

```text
creator -> instance chưa có ID
population identifier -> withId(...)
property accessor -> giữ instance mới
converter -> trả instance mới nhất
```

Property accessor có thể giữ tham chiếu entity bên trong. Sau một phép cập nhật tạo bản sao, việc lấy object hiện tại từ accessor quan trọng hơn việc tiếp tục dùng tham chiếu đã lưu trước khi cập nhật.

### 6.3. Lưu entity mới: ID có thể chỉ xuất hiện sau thao tác ghi

Đối với datastore sinh identifier khi insert, lúc bắt đầu lưu ứng dụng chưa biết ID. Sau khi nhận identifier, module phải biểu diễn entity đã có ID trong kết quả lưu.

Với hạ tầng hỗ trợ kiểu immutable và wither tương ứng, cập nhật này có thể đi qua `withId`. Module khác có thể tái tạo object bằng đường khác. Không nên viết logic ứng dụng phụ thuộc số lần framework gọi wither.

| Ngữ cảnh | ID đã có trước creator? | Vai trò có thể có của wither |
|---|---|---|
| Đọc và creator nhận `id` | Có | Không cần để gán lại ID |
| Đọc và creator không nhận `id` | Chưa nằm trong instance | Có thể dùng để population ID |
| Lưu mới, datastore cấp ID sau insert | Chưa có trong entity đầu vào | Có thể tạo bản sao có ID |
| Entity đã có ID, không có thay đổi liên quan | Có | Không nhất thiết được gọi |

## 7. Luôn tiếp tục từ kết quả của `save`

### 7.1. Ví dụ đồng bộ

Một repository minh họa dùng abstraction Commons:

```java
package com.example.orders;

import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Repository còn cần được module lưu trữ cụ thể tạo implementation. Các lời gọi sau giả định datastore và module đã được cấu hình để sinh, ghi và trả identifier phù hợp:

```java
PurchaseOrder draft = PurchaseOrder.draft(
        "PO-001",
        List.of(new OrderLine("BOOK-01", 2)));

PurchaseOrder saved = repository.save(draft);

Long generatedId = saved.getId();
```

Hợp đồng `CrudRepository.save` yêu cầu phía gọi dùng instance trả về cho các thao tác tiếp theo vì thao tác lưu có thể thay đổi hoàn toàn instance entity.

Với model immutable đang xét:

```text
draft.getId() -> vẫn null
saved.getId() -> ID được trả về, nếu cơ chế sinh ID đã cấu hình thành công
```

Không kiểm tra thành công bằng điều kiện `saved != draft`: một implementation có thể trả cùng instance nếu không cần thay trạng thái. Điều cần kiểm tra là kết quả lưu và trạng thái được trả theo hợp đồng của module.

### 7.2. Lỗi phổ biến: bỏ kết quả rồi dùng draft

```java
repository.save(draft);

Long id = draft.getId();
```

Câu lệnh đầu bỏ mất entity kết quả. Với `PurchaseOrder` immutable, không có cơ sở để biến `draft` tự trỏ sang bản sao có ID.

Lỗi này thường lan sang tầng API: response được tạo từ draft sẽ thiếu identifier dù bản ghi đã được lưu thành công. Hãy tạo response từ `saved`.

```java
PurchaseOrder saved = repository.save(draft);
return saved.getId();
```

Kiểu trả về cụ thể của service có thể là một DTO; nguyên tắc vẫn là lấy dữ liệu từ kết quả lưu.

### 7.3. Lưu lại draft có thể bị coi là một lần tạo mới nữa

```java
repository.save(draft);
repository.save(draft);
```

Nếu cơ chế nhận diện entity mới của module dựa vào identifier `null` trong trường hợp này, cả hai lần có thể bị xem là lưu entity mới. Tùy datastore và ràng buộc, kết quả có thể là hai bản ghi, lỗi khóa duy nhất hoặc hành vi khác theo chiến lược ghi.

Không kết luận rằng gọi `save` hai lần trên cùng tham chiếu Java luôn có tính idempotent.

Khi cần tiếp tục thay đổi entity đã lưu:

```java
PurchaseOrder saved = repository.save(draft);

PurchaseOrder changed = saved.withLines(
        List.of(new OrderLine("BOOK-01", 3)));

PurchaseOrder updated = repository.save(changed);
```

`changed` giữ identifier của `saved`. Việc module chọn insert, update, merge hoặc upsert vẫn theo cơ chế state detection và semantics của nó. Giữ đúng ID là một phần của luồng trạng thái, không phải một quy tắc ghi phổ quát cho mọi datastore.

## 8. Có ID trong object không đồng nghĩa đã có bản ghi

### 8.1. `withId` chỉ tạo trạng thái trong bộ nhớ

```java
PurchaseOrder identified = draft.withId(999L);
```

Phép gọi này không gửi query, không insert, không kiểm tra bản ghi `999L` đã tồn tại và không dành trước identifier tại datastore.

Nếu tiếp tục lưu `identified`, module sẽ áp dụng cơ chế nhận diện trạng thái và thao tác ghi của nó. Không dùng `withId` như một cách thay thế cho API cấp ID hoặc thao tác lưu.

### 8.2. ID do ứng dụng cấp cần thiết kế state detection phù hợp

Có hệ thống tạo UUID, khóa nghiệp vụ hoặc identifier khác ngay trong ứng dụng trước khi lưu. Entity có ID non-null khi đó vẫn có thể chưa tồn tại trong datastore.

Cách repository xác định entity mới phụ thuộc module và metadata, có thể xét identifier, version hoặc cơ chế `Persistable`. Vì vậy:

- Không áp dụng máy móc điều kiện “ID non-null nghĩa là đã tồn tại”.
- Không đặt `null` vào một identifier do ứng dụng cấp chỉ để ép framework chọn insert.
- Nếu cần tùy chỉnh state detection, sử dụng cơ chế được module hỗ trợ và kiểm tra cùng lifecycle của nó.

Trong ví dụ chính, giả định đơn giản là entity mới chưa có ID và datastore sẽ cấp ID. Khi đổi chiến lược cấp ID, cần đánh giá lại giả định đó.

### 8.3. Kiểu primitive dễ làm trạng thái chưa có ID kém rõ

Với `long`, giá trị Java mặc định là `0`; không thể biểu diễn `null`. Một số cơ chế nhận diện trạng thái có quy tắc cho giá trị primitive, nhưng không nên suy rộng một quy tắc duy nhất sang mọi module.

Dùng `Long` trong ví dụ làm trạng thái chưa có identifier dễ đọc hơn. Điều này không tự cấu hình bộ sinh ID và không thay cho việc kiểm tra chính sách identifier của datastore.

## 9. Bản sao phải giữ đủ trạng thái

### 9.1. Không gọi lại factory tạo mới trong `withId`

Một implementation sai:

```java
public PurchaseOrder withId(Long id) {
    return PurchaseOrder.draft(this.orderNumber, this.lines);
}
```

Factory `draft` luôn trả entity có ID `null`. Phương thức trên nhận `id` nhưng làm mất giá trị ấy, nên kết quả không đáp ứng hợp đồng của wither.

Một lỗi khác là bỏ mất dữ liệu không liên quan:

```java
public PurchaseOrder withId(Long id) {
    return new PurchaseOrder(
            id,
            this.orderNumber,
            List.of(new OrderLine("UNKNOWN", 1)));
}
```

Bản sao có ID nhưng nội dung đơn đã bị thay thế. Đây là lỗi mất trạng thái, không phải lỗi sinh ID.

Bản đúng trong ví dụ giữ `orderNumber` và `lines`:

```java
public PurchaseOrder withId(Long id) {
    return new PurchaseOrder(id, this.orderNumber, this.lines);
}
```

### 9.2. Thêm field mới phải rà soát các phép sao chép

Khi model phát triển, thêm field vào constructor chưa đủ. Cần xem lại tất cả factory, wither và phép cập nhật để bảo toàn field đó.

| Thuộc tính thêm vào | Lỗi nếu bản sao không giữ đúng |
|---|---|
| Địa chỉ giao hàng | Bản sao có ID nhưng mất nơi giao |
| Trạng thái nghiệp vụ | Đơn đã xử lý bị quay về trạng thái khởi tạo |
| Version | Mất thông tin dùng cho nhận diện trạng thái hoặc kiểm tra ghi đồng thời |
| Thời điểm tạo | Metadata bị đặt lại hoặc không còn phản ánh bản ghi |
| Giá trị do datastore tính | Kết quả lưu không còn phản ánh trạng thái mới nhất |

Không có yêu cầu mọi cache transient phải được sao chép nguyên xi; cache có thể được tính lại theo thiết kế. Điều cần bảo toàn là trạng thái có ý nghĩa theo hợp đồng entity và mapping.

### 9.3. `@Version` đòi hỏi giữ phiên bản mới nhất

Nếu module hỗ trợ optimistic locking bằng property version, entity immutable có thể có thêm field final tương ứng và đường cập nhật phù hợp.

Khi sao chép chỉ để thay ID, giữ version đang có. Khi thay nội dung đơn, tiếp tục giữ version hiện tại của snapshot để datastore có thông tin kiểm tra. Khi lưu trả về version mới, dùng entity mới đó cho lần xử lý tiếp theo.

Không tự đặt version về `null` hoặc `0` trong mọi wither. Thao tác này có thể phá state detection hoặc optimistic locking. Quy tắc khởi tạo/tăng version phải theo module.

Bất biến không tự giải quyết lost update: hai snapshot cùng ID vẫn có thể được sửa và lưu đồng thời. Cần cơ chế kiểm soát ghi đồng thời tương ứng nếu nghiệp vụ yêu cầu.

### 9.4. Auditing có thể bổ sung trạng thái ngoài ID

Khi module hỗ trợ auditing cho immutable model, các giá trị như thời điểm tạo hoặc sửa cũng cần một đường cập nhật hợp lệ. Một wither đặt ID mà làm rơi các field auditing có thể khiến kết quả cuối thiếu dữ liệu vừa được callback bổ sung.

Không tự gán thời gian hiện tại bên trong mọi `withId`. Wither là thao tác tạo bản sao theo property; thời điểm nghiệp vụ và metadata auditing cần được quản lý ở đúng lifecycle.

## 10. Chuỗi wither phải bắt đầu từ object mới nhất

Với entity immutable, luồng cập nhật được diễn tả bằng chuỗi giá trị:

```java
PurchaseOrder identified = draft.withId(101L);
PurchaseOrder changed = identified.withLines(
        List.of(new OrderLine("BOOK-01", 5)));
```

Hoặc nối trực tiếp:

```java
PurchaseOrder changed = draft
        .withId(101L)
        .withLines(List.of(new OrderLine("BOOK-01", 5)));
```

Đây là minh họa phép sao chép trong bộ nhớ. Giá trị `101L` trong đoạn code không được tự coi là ID do datastore vừa cấp.

Lỗi thường gặp là rẽ nhánh từ draft cũ:

```java
PurchaseOrder identified = draft.withId(101L);

// Lỗi luồng dữ liệu nếu mục đích là giữ ID đã nhận ở identified.
PurchaseOrder changed = draft.withLines(
        List.of(new OrderLine("BOOK-01", 5)));
```

`changed` vẫn có ID `null`, vì nó được sao chép từ `draft`. `identified` có ID nhưng không được dùng trong bước cập nhật tiếp theo.

Khi đọc code service, hãy lần theo biến làm nguồn cho từng bản sao. Đây là cách nhanh để tìm lỗi mất ID hoặc mất version.

## 11. Record có phải tự có wither không?

Java record là một lựa chọn thuận tiện để biểu diễn dữ liệu immutable, nhưng Java không tự sinh phương thức `withId`.

```java
public record NoteSnapshot(Long id, String text) {

    public NoteSnapshot withId(Long id) {
        return new NoteSnapshot(id, this.text);
    }
}
```

Ví dụ này minh họa semantics Java. Để dùng làm entity hoặc DTO được mapping, vẫn cần module hỗ trợ và metadata phù hợp. Record cũng chỉ immutable theo các component; một component trỏ đến list mutable vẫn đòi hỏi thiết kế defensive copy.

Khi record được materialize qua canonical constructor có đủ identifier, không cần wither chỉ để gán lại ID vừa đi qua constructor. Nếu một lifecycle cần cập nhật thuộc tính sau đó, có thể cần cơ chế sao chép phù hợp.

Record tự có `equals` và `hashCode` theo các component. Hai snapshot cùng ID nhưng khác nội dung vì vậy có thể không bằng nhau. Đây là so sánh giá trị record, không phải một lời khẳng định về persistent identity.

## 12. `equals`, `hashCode` và collection

### 12.1. Hai entity mới đều có ID `null` chưa chắc là cùng entity

Nếu tự viết `equals` chỉ dựa vào `Objects.equals(id, other.id)`, hai đơn chưa lưu đều có ID `null` có thể bị coi là bằng nhau. Điều này có thể làm mất phần tử khi đưa vào set.

Cần chọn semantics equality theo domain, chẳng hạn object identity, một khóa nghiệp vụ ổn định có bảo đảm phù hợp hoặc một quy tắc identifier được thiết kế cẩn thận. Không có một implementation duy nhất đúng cho mọi entity.

`PurchaseOrder` trong ví dụ không override `equals`/`hashCode`; không được suy ra hai bản sao bằng nhau chỉ vì có cùng `orderNumber` hoặc ID.

### 12.2. Bản sao có ID không tự thay thế object trong set/map

Giả sử ứng dụng đã đặt draft vào một collection, rồi nhận bản sao `saved`. Collection vẫn chứa object ban đầu, trừ khi ứng dụng cập nhật nó.

Nếu equality dựa vào ID hoặc toàn bộ trạng thái, bản sao có thể có semantics equality/hash khác draft. Không thể giả định `set.contains(saved)` luôn đúng vì set đã chứa draft.

Điểm khác với entity mutable là hash của **chính draft immutable** không bị thay đổi bởi `withId`; wither tạo object khác. Vấn đề nằm ở việc collection còn giữ snapshot cũ và cách ứng dụng quản lý snapshot mới.

Nếu dùng map theo ID, chỉ đưa entity vào map có khóa lưu trữ sau khi đã có identifier hợp lệ, hoặc chọn một khóa tạm/khóa nghiệp vụ phù hợp cho giai đoạn trước lưu.

## 13. Quy tắc tương tự trong repository reactive

Với module có hỗ trợ `ReactiveCrudRepository`, entity mới nhất được phát ra trong publisher kết quả:

```java
return reactiveRepository.save(draft)
        .map(saved -> saved.getId());
```

Giá trị trả từ chuỗi này là kết quả reactive chứa ID, không phải ID đồng bộ đã có sẵn tại lúc xây dựng pipeline. Thao tác cần được thực thi theo lifecycle subscription của ứng dụng để nhận kết quả.

Không tạo response từ draft ở một bước khác rồi kỳ vọng draft sẽ được sửa sau khi publisher hoàn tất.

Nếu tiếp tục lưu một thay đổi, nối từ entity được phát ra:

```java
return reactiveRepository.save(draft)
        .flatMap(saved -> {
            PurchaseOrder changed = saved.withLines(
                    List.of(new OrderLine("BOOK-01", 3)));
            return reactiveRepository.save(changed);
        });
```

Đoạn code minh họa cách truyền trạng thái qua pipeline, không yêu cầu phải ghi hai lần cho nghiệp vụ thông thường. Quy tắc transaction, concurrency và mapping vẫn thuộc module reactive đang dùng.

## 14. Bảng chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Lưu thành công nhưng response không có ID | Response lấy từ draft thay vì kết quả `save` | Dùng entity trả về |
| Gọi `withId` nhưng biến cũ vẫn không có ID | Bỏ kết quả wither | Gán hoặc truyền tiếp bản sao |
| `withId` chạy nhưng kết quả vẫn có ID `null` | Wither gọi factory tạo mới hoặc bỏ tham số | Tạo bản sao dùng đúng ID đầu vào |
| Bản sao có ID nhưng thiếu dữ liệu khác | Constructor/wither không bảo toàn field | Rà soát mọi đường sao chép |
| Đọc entity không gọi `withId` | ID đã được truyền vào creator | Kiểm tra metadata và object cuối, không dựa vào số lần gọi |
| Có `@Id` nhưng không có ID được sinh | Chưa cấu hình hoặc datastore không hỗ trợ chiến lược đang giả định | Kiểm tra cơ chế sinh ID của module/datastore |
| Hai lần lưu dẫn đến hai lần tạo mới | Tiếp tục dùng snapshot chưa có ID hoặc state detection không phù hợp | Truyền entity kết quả và kiểm tra chính sách nhận diện entity mới |
| Cập nhật gặp lỗi version | Dùng snapshot cũ hoặc bản sao làm mất version | Giữ version và xử lý xung đột theo module |
| Bên ngoài sửa được nội dung entity | Lộ collection hoặc phần tử mutable | Defensive copy và thiết kế value object phù hợp |
| Không materialize được lớp immutable | Creator, tên tham số hoặc đường cập nhật không hợp lệ | Kiểm tra metadata và khả năng mapping thực tế |

Khi chẩn đoán lỗi mapping, cần biết property nào đang được cập nhật và converter/provider nào thực hiện. Repository chỉ là điểm gọi; lỗi có thể phát sinh trong creator, conversion, wither hoặc cơ chế lưu trữ bên dưới.

## 15. Kiểm chứng thiết kế theo hai lớp

### 15.1. Kiểm tra semantics của wither độc lập với datastore

Có thể quan sát trực tiếp:

```java
PurchaseOrder draft = PurchaseOrder.draft(
        "PO-001",
        List.of(new OrderLine("BOOK-01", 2)));

PurchaseOrder identified = draft.withId(101L);

// draft.getId() vẫn null.
// identified.getId() là 101L.
// identified giữ nguyên orderNumber và nội dung lines.
// draft và identified là hai instance khác nhau trong implementation này.
```

Các thuộc tính cần xác nhận:

- Object đầu vào giữ trạng thái ban đầu.
- Kết quả có ID yêu cầu.
- Phần trạng thái không đổi được bảo toàn.
- Với `withLines`, ID được giữ khi thay nội dung.
- Collection không thể bị sửa từ bên ngoài theo hợp đồng immutable đã chọn.

Các kiểm tra này chứng minh code domain đúng, nhưng chưa chứng minh module thực sự nhận diện wither hoặc sinh ID được.

### 15.2. Kiểm tra tích hợp với module lưu trữ thật

Dùng datastore hoặc môi trường tích hợp phù hợp với ứng dụng để kiểm tra:

1. Tạo draft không có ID.
2. Lưu qua repository và giữ entity trả về.
3. Xác nhận ID được cấp theo cấu hình.
4. Đọc lại bằng ID đó và đối chiếu dữ liệu nghiệp vụ.
5. Tạo thay đổi từ entity đã lưu, lưu tiếp và kiểm tra semantics ghi mà module cam kết.
6. Nếu dùng version/auditing, xác nhận các giá trị này không bị mất qua bản sao.

Mock repository trả sẵn một entity có ID có thể kiểm tra service dùng đúng kết quả. Nó không kiểm chứng việc mapper thật gọi wither, truyền creator argument hoặc nhận generated key từ datastore.

Không dùng điều kiện duy nhất `saved != draft` làm tiêu chí kiểm thử tích hợp. Một cơ chế hợp lệ có thể chọn đường materialization khác; hãy kiểm tra dữ liệu và hợp đồng vòng đời thực tế.

## 16. Bài thực hành

### Bài 1: sửa luồng làm mất ID

Bắt đầu bằng service bỏ kết quả `save` rồi tạo response từ draft. Điều chỉnh để response lấy từ entity trả về. Trong kiểm thử service, cho repository trả một bản sao có ID khác với object đầu vào để lỗi không bị che bởi việc mock trả cùng tham chiếu.

Kết quả cần chứng minh response chứa ID từ kết quả lưu, không phải từ giả định entity đầu vào bị sửa.

### Bài 2: bảo toàn trạng thái qua các wither

Thêm một thuộc tính nghiệp vụ immutable vào entity, chẳng hạn `deliveryAddress`. Cập nhật constructor, factory, `withId` và `withLines`.

Tạo chuỗi draft → bản sao có ID → bản sao đổi nội dung. Xác nhận địa chỉ không biến mất ở bất kỳ bước nào và ID vẫn còn sau khi đổi nội dung.

### Bài 3: quan sát hai đường nhận ID

Trong module hỗ trợ immutable mapping, so sánh một lượt đọc với creator nhận đủ ID và một lượt lưu mới được datastore cấp ID. Quan sát object kết quả và đường cập nhật mà converter dùng.

Mục tiêu là hiểu vì sao wither có thể được dùng trong ngữ cảnh này nhưng không cần trong ngữ cảnh khác. Không thay creator chỉ để buộc breakpoint phải chạy.

### Bài 4: nhận diện snapshot cũ

Tạo một biến draft, nhận một biến saved rồi cố ý tạo thay đổi từ draft. Giải thích vì sao bản sao đổi nội dung bị mất ID. Sửa bằng cách tạo thay đổi từ saved.

Nếu bài thực hành có version, thực hiện tương tự với version để thấy lỗi truyền snapshot cũ không chỉ liên quan identifier.

## 17. Các điểm cần nhớ

- Entity immutable nhận trạng thái mới bằng bản sao; object ban đầu không cần bị sửa.
- Wither như `withId` phải trả entity có giá trị mới và giữ phần trạng thái còn lại.
- Creator nhận đủ ID có thể khiến lượt đọc không cần gọi wither cho identifier.
- `@Id` nhận diện identifier; cơ chế sinh ID thuộc module và datastore.
- Luôn tiếp tục từ entity mà `save` trả về, kể cả khi đang quen với entity mutable.
- Tạo bản sao có ID trong bộ nhớ không chứng minh bản ghi đã tồn tại.
- Version, auditing và field nghiệp vụ phải được bảo toàn qua các phép sao chép.
- Tham chiếu Java, equality và persistent identity là các khái niệm khác nhau.
- Kiểm tra domain và kiểm tra tích hợp mapping giải quyết những câu hỏi khác nhau; cần biết mình đang xác nhận lớp nào.