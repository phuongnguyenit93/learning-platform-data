# In, NotIn, True, False và tập tham số rỗng

> **Chương:** Truy vấn suy diễn  
> **Module:** `SPRING_DATA_MONGODB`

Spring Data MongoDB cho phép khai báo truy vấn từ **tên phương thức repository** thay vì tự viết mọi biểu thức MongoDB. Ví dụ, `findByStatusIn(...)` có thể được suy diễn thành truy vấn kiểm tra trạng thái thuộc một danh sách; `findByStatusNotIn(...)` loại các trạng thái trong danh sách; `findByActiveTrue()` và `findByActiveFalse()` lọc cờ boolean cố định.

Những từ khóa này ngắn gọn, nhưng dễ gây lỗi khi **tập tham số rỗng**, khi document **không có field** hoặc field chứa **`null`**, và khi ứng dụng hiểu “không có điều kiện” khác với “không có kết quả”. Đặc biệt, truy vấn loại trừ với danh sách rỗng có thể vô tình trả về một tập dữ liệu rất lớn nếu không có bộ lọc bảo vệ.

Bài này thuộc module `SPRING_DATA_MONGODB`: ánh xạ document, truy vấn bằng repository hoặc `MongoTemplate`, kết hợp với index, aggregation, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Trọng tâm trực tiếp là **ngữ nghĩa của `In`, `NotIn`, `True`, `False` và cách xử lý input rỗng có chủ đích**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Viết phương thức repository với các từ khóa `In`, `NotIn`, `True`, `False` và giải thích biểu thức MongoDB tương ứng.
2. Phân biệt kết quả của `$in: []` với `$nin: []`, bao gồm tình huống tham số đầu vào `null`.
3. Hiểu cách `$nin` xử lý field bị thiếu/`null` và vì sao boolean `false` không đồng nghĩa field vắng mặt.
4. Kết hợp điều kiện lọc theo tenant/cửa hàng, điều kiện boolean, phân trang, sorting và index hợp lý.
5. Tạo kiểm thử tích hợp trên BSON thật để phát hiện kết quả sai khi danh sách trống hoặc dữ liệu legacy có field không đầy đủ.

## 2. Bốn từ khóa và biểu thức truy vấn suy diễn

| Từ khóa trong tên phương thức | Ví dụ repository | Ý nghĩa MongoDB thường được sinh |
| --- | --- | --- |
| `In` / `IsIn` | `findByStatusIn(statuses)` | `{ status: { $in: [...] } }` |
| `NotIn` / `IsNotIn` | `findByStatusNotIn(statuses)` | `{ status: { $nin: [...] } }` |
| `True` / `IsTrue` | `findByActiveTrue()` | `{ active: true }` |
| `False` / `IsFalse` | `findByActiveFalse()` | `{ active: false }` |

Các từ khóa `True` và `False` trong tên hàm **không nhận tham số boolean tương ứng**. Giá trị đúng/sai đã được cố định bởi tên phương thức.

Ví dụ:

```java
List<OrderDocument> findByActiveTrue();
List<OrderDocument> findByActiveFalse();
```

Khác với:

```java
List<OrderDocument> findByActive(Boolean active);
```

Phương thức thứ ba có **một tham số**, cho phép caller chọn giá trị cần so khớp. Cả ba phương thức đều làm việc trên tên **thuộc tính Java** trong entity; Spring Data chuyển tên thuộc tính sang tên field BSON dựa trên metadata mapping.

### 2.1. Ngữ nghĩa thuộc tập và không thuộc tập

- `$in` trả các document mà field có giá trị thuộc **ít nhất một** phần tử trong danh sách so khớp.
- `$nin` trả các document mà field **không** có giá trị trong danh sách loại trừ; nó cũng có thể khớp document **không có field đó**.
- Nếu field chứa **array**, `$in` có thể khớp khi ít nhất một phần tử của array thuộc tập, còn `$nin` khớp khi không phần tử nào thuộc tập loại trừ. Bài này chủ yếu dùng field `status` dạng scalar.
- `True` và `False` là **so khớp boolean chính xác**, không phải phép kiểm tra “có giá trị” hay “không có giá trị”.

Không nên suy luận theo ngôn ngữ tự nhiên rằng “NotIn” luôn tương đương “field tồn tại và khác các giá trị đã cho”. MongoDB có quy tắc riêng với field thiếu; cần kiểm tra dữ liệu thực tế.

## 3. Dữ liệu ví dụ: trạng thái đơn hàng và cờ kích hoạt

Ứng dụng bán hàng lưu document trong collection `orders`. Trạng thái có thể là `NEW`, `PAID` hoặc `CANCELLED`; field `active` cho biết bản ghi còn đang được hiển thị trong các luồng xử lý hiện hành.

Để làm rõ trường hợp dữ liệu cũ, ta cố ý tạo một số document **thiếu field** hoặc có `status: null`.

### 3.1. Seed dữ liệu bằng mongosh

```javascript
use shop

db.orders.insertMany([
  {
    _id: "O-1",
    storeId: "STORE-HCM",
    status: "NEW",
    active: true,
    createdAt: ISODate("2026-11-20T01:00:00Z")
  },
  {
    _id: "O-2",
    storeId: "STORE-HCM",
    status: "PAID",
    active: false,
    createdAt: ISODate("2026-11-20T02:00:00Z")
  },
  {
    _id: "O-3",
    storeId: "STORE-HCM",
    status: "CANCELLED",
    active: true,
    createdAt: ISODate("2026-11-20T03:00:00Z")
  },
  {
    _id: "O-4",
    storeId: "STORE-HCM",
    active: true,                    // cố ý thiếu status
    createdAt: ISODate("2026-11-20T04:00:00Z")
  },
  {
    _id: "O-5",
    storeId: "STORE-HCM",
    status: null,                    // BSON null, không phải thiếu field
    active: false,
    createdAt: ISODate("2026-11-20T05:00:00Z")
  },
  {
    _id: "O-6",
    storeId: "STORE-HCM",
    status: "PAID",
    active: true,
    createdAt: ISODate("2026-11-20T06:00:00Z")
  },
  {
    _id: "O-7",
    storeId: "STORE-HCM",
    status: "NEW",
    createdAt: ISODate("2026-11-20T07:00:00Z") // cố ý thiếu active
  }
])
```

Chỉ chạy bộ seed minh họa này trong database thử nghiệm cô lập. Trong ứng dụng thật, `status` và `active` có thể là field bắt buộc với schema validation; ở đây các giá trị thiếu/`null` được tạo có chủ đích để minh họa tương thích dữ liệu cũ.

Tóm tắt:

| `_id` | `status` | `active` |
| --- | --- | --- |
| `O-1` | `NEW` | `true` |
| `O-2` | `PAID` | `false` |
| `O-3` | `CANCELLED` | `true` |
| `O-4` | *Thiếu field* | `true` |
| `O-5` | `null` | `false` |
| `O-6` | `PAID` | `true` |
| `O-7` | `NEW` | *Thiếu field* |

Các truy vấn phần tiếp theo lấy kết quả trên **đúng bảy document** này.

## 4. In: chọn các giá trị được cho phép

Giả sử trang xử lý đơn cần tất cả đơn có trạng thái `NEW` hoặc `PAID`.

```javascript
db.orders.find({
  status: { $in: ["NEW", "PAID"] }
})
```

Kết quả theo tập ID (không xét thứ tự):

```text
O-1, O-2, O-6, O-7
```

`O-3` bị loại vì `CANCELLED` không có trong danh sách; `O-4` thiếu `status` và `O-5` có `null`, nên không khớp hai giá trị string đã cho.

Trong repository:

```java
List<OrderDocument> findByStatusIn(
    Collection<OrderStatus> statuses);
```

Gọi:

```java
repository.findByStatusIn(
    List.of(OrderStatus.NEW, OrderStatus.PAID));
```

Theo cơ chế mapping enum thông thường, Spring Data ghi `OrderStatus.NEW` thành chuỗi `"NEW"` và suy diễn truy vấn `$in` trên field `status`. Nếu dự án có custom converter hoặc đổi cách lưu enum, phải kiểm tra BSON được sinh và dữ liệu cũ tương ứng.

### 4.1. Điều kiện kết hợp

Trang quản trị có thể chỉ cần **đơn đang active và thuộc tập trạng thái cho phép**:

```java
List<OrderDocument> findByStatusInAndActiveTrue(
    Collection<OrderStatus> statuses);
```

Biểu thức mong đợi:

```javascript
db.orders.find({
  status: { $in: ["NEW", "PAID"] },
  active: true
})
```

Kết quả là `O-1` và `O-6`. `O-2` có trạng thái hợp lệ nhưng `active: false`; `O-7` không có field `active` nên cũng không khớp.

### 4.2. Khi field là array

Đối với `tags: ["sale", "featured"]`:

```javascript
db.products.find({
  tags: { $in: ["featured", "new"] }
})
```

Một document sẽ khớp nếu có **ít nhất một** tag trong tập được cho. Không nên nhầm `$in` với yêu cầu “document phải chứa tất cả các giá trị”; yêu cầu chứa tất cả thường được diễn đạt bằng `$all` hoặc các điều kiện tương ứng.

## 5. NotIn: loại trừ không đồng nghĩa field bắt buộc tồn tại

Giả sử cần lấy đơn **không có trạng thái `CANCELLED`**:

```javascript
db.orders.find({
  status: { $nin: ["CANCELLED"] }
})
```

Kết quả:

```text
O-1, O-2, O-4, O-5, O-6, O-7
```

Điều đáng chú ý: **`O-4` (thiếu `status`) và `O-5` (`status: null`) vẫn xuất hiện**. Chúng không có giá trị `CANCELLED`, nên không bị loại bởi điều kiện `$nin` này.

Repository:

```java
List<OrderDocument> findByStatusNotIn(
    Collection<OrderStatus> excludedStatuses);
```

Gọi:

```java
repository.findByStatusNotIn(
    List.of(OrderStatus.CANCELLED));
```

### 5.1. Vì sao NotIn không tương đương “trạng thái hợp lệ còn lại”?

Nếu enum hiện tại có ba trạng thái `NEW`, `PAID` và `CANCELLED`, có thể nghĩ:

```text
status NOT IN (CANCELLED)
  == status IN (NEW, PAID)
```

Nhận định này **không đúng** khi collection có field thiếu, `null` hoặc giá trị mới chưa được enum hiện tại biết đến. `$nin` chỉ nêu **những giá trị không muốn nhận**, nên những trường hợp còn lại vẫn có khả năng khớp.

Trong hệ thống nghiệp vụ hoặc truy vấn phục vụ phân quyền, việc nhận thêm những bản ghi có trạng thái không xác định có thể nguy hiểm. Nếu các giá trị hợp lệ là tập đóng, cách an toàn hơn là **lọc dương tính bằng `In` với danh sách trạng thái được phép**.

### 5.2. Nếu bắt buộc status tồn tại và không null

Có thể dùng `MongoTemplate` để diễn đạt điều kiện chính xác:

```java
import java.util.Collection;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<OrderDocument> findKnownStatusesNotExcluded(
        MongoTemplate template,
        Collection<OrderStatus> excludedStatuses) {

    Criteria status = Criteria.where("status")
        .exists(true)
        .ne(null)
        .nin(excludedStatuses);

    Query query = Query.query(status);
    return template.find(query, OrderDocument.class);
}
```

Đoạn này là **một phương thức minh họa** đặt trong class service; nó chưa bao gồm xác thực input rỗng hay giới hạn phạm vi theo cửa hàng. `$exists: true` yêu cầu field có mặt; `$ne: null` loại giá trị `null`; `$nin` loại những trạng thái không được phép.

Biểu thức MongoDB tương ứng:

```javascript
db.orders.find({
  status: {
    $exists: true,
    $ne: null,
    $nin: ["CANCELLED"]
  }
})
```

Trong tập ví dụ, kết quả là `O-1`, `O-2`, `O-6` và `O-7`. Nếu cần **chỉ những giá trị enum đã được hệ thống cho phép**, chỉ kiểm tra tồn tại và không null vẫn chưa đủ: dữ liệu có `status: "UNKNOWN"` sẽ khớp `$nin` nhưng không thuộc các trạng thái được duyệt. Khi đó dùng `$in` với tập hợp hợp lệ rõ ràng.

## 6. True và False: lọc boolean chính xác

Lọc các đơn active:

```javascript
db.orders.find({ active: true })
```

Kết quả:

```text
O-1, O-3, O-4, O-6
```

Lọc đơn inactive:

```javascript
db.orders.find({ active: false })
```

Kết quả:

```text
O-2, O-5
```

`O-7` **không có field `active`** nên không thuộc cả hai tập. Khi field là `null` hoặc dữ liệu legacy lưu string `"false"` thay vì BSON Boolean `false`, nó cũng không phải giá trị boolean false theo quy tắc so khớp kiểu BSON thông thường.

Trong repository:

```java
List<OrderDocument> findByActiveTrue();
List<OrderDocument> findByActiveFalse();

// Các biến thể có Is cũng dùng được:
List<OrderDocument> findByActiveIsTrue();
List<OrderDocument> findByActiveIsFalse();
```

### 6.1. False khác với Not(True)

`findByActiveFalse()` diễn đạt `active == false`. Trong khi đó truy vấn MongoDB:

```javascript
db.orders.find({ active: { $ne: true } })
```

có thể khớp thêm các document **không có field `active`**, và cả các giá trị không phải boolean true (ví dụ `null`). Vì vậy:

```text
active == false   KHÁC   active != true
```

Không sử dụng phép phủ định `$ne: true` làm tương đương `False` khi cần đúng BSON Boolean false.

### 6.2. Khác nhau giữa boolean primitive và Boolean wrapper

Trong Java:

```java
private boolean active; // chỉ true/false ở mức object Java
private Boolean activeFlag; // có thể null
```

Khi đọc tài liệu cũ có field thiếu, một primitive `boolean` không thể biểu diễn “không biết”; tùy cách mapping/constructor, giá trị thiếu có thể trở thành mặc định false hoặc gây vấn đề khởi tạo. `Boolean` wrapper thể hiện rõ ba trạng thái `true`/`false`/`null` ở model Java.

Nếu nghiệp vụ yêu cầu active luôn có giá trị, hãy áp dụng validation và quy trình migration dữ liệu cũ; không nên chỉ thay kiểu Java rồi giả định mọi document thiếu field sẽ có ngữ nghĩa đúng.

## 7. Tập tham số rỗng: điểm dễ gây lỗi nhất

Xét hai câu truy vấn MongoDB:

```javascript
db.orders.find({ status: { $in: [] } })
db.orders.find({ status: { $nin: [] } })
```

Trên dữ liệu mẫu:

| Điều kiện | Kết quả | Lý do |
| --- | --- | --- |
| `status: { $in: [] }` | **0 document** | Không có giá trị nào để khớp |
| `status: { $nin: [] }` | **Cả 7 document** | Không có giá trị nào cần loại trừ |
| `status: { $in: ["NEW"] }` | `O-1, O-7` | Chỉ khớp trạng thái được liệt kê |
| `status: { $nin: ["NEW"] }` | `O-2, O-3, O-4, O-5, O-6` | Loại các giá trị NEW, vẫn nhận thiếu/null |
| `active: true` | `O-1, O-3, O-4, O-6` | Chỉ khớp BSON boolean true |
| `active: false` | `O-2, O-5` | Chỉ khớp BSON boolean false |

Đây là **ngữ nghĩa của các operator MongoDB**, với điều kiện Spring Data thật sự tạo `$in`/`$nin` và danh sách rỗng tương ứng. Nên kiểm thử bằng phiên bản Spring Data/driver đang dùng thay vì suy đoán framework luôn tối ưu hoặc bỏ qua một điều kiện rỗng giống nhau ở mọi ngữ cảnh.

### 7.1. “Không chọn trạng thái” có ít nhất ba ý nghĩa

Giả sử một trang danh sách nhận danh sách `statuses` từ UI. Nếu người dùng chưa chọn gì, sản phẩm có thể muốn:

1. **Không có kết quả:** không trạng thái nào được chọn → danh sách rỗng.
2. **Không áp bộ lọc trạng thái:** hiển thị mọi trạng thái mà người dùng được quyền xem.
3. **Input không hợp lệ:** cần chọn ít nhất một trạng thái mới thực hiện truy vấn.

Đây là ba hợp đồng **khác nhau**. Không thể tự chọn bằng cách truyền `List.of()` vào mọi phương thức repository. Đặc biệt:

- Với **allowlist**, rỗng thường hợp lý để trả **0 kết quả**.
- Với **denylist**, rỗng thường có nghĩa **không loại ai**, có thể trả rất nhiều kết quả nếu không có điều kiện khác.
- Với **bộ lọc phục vụ phân quyền**, “không có quyền nào” phải có nghĩa **không có kết quả**, không được vô tình chuyển thành “không có ràng buộc”.

### 7.2. Null collection không đồng nghĩa empty collection

`null` có thể nghĩa là input không được truyền, còn empty collection có nghĩa đã truyền nhưng không có phần tử. Việc đưa `null` thẳng vào tham số `In`/`NotIn` có thể dẫn đến lỗi binding hoặc ngữ nghĩa không như mong muốn tùy framework và cấu hình.

Hãy định nghĩa rõ contract tại service/API:

```java
Objects.requireNonNull(statuses, "statuses");
```

Nếu `null` được sản phẩm quy định là “bỏ qua bộ lọc”, phải thể hiện trường hợp đó bằng một nhánh nghiệp vụ có tên rõ ràng, không truyền `null` rồi hy vọng repository tự bỏ điều kiện.

### 7.3. Không lẫn collection rỗng với collection chứa null

`List.of()` là danh sách rỗng; `[null]` trong BSON là danh sách **có một giá trị null**. Các operator MongoDB có quy tắc riêng với giá trị `null` và field bị thiếu; vì vậy `$in: [null]` không thể được xem là tương đương `$in: []`.

Với truy vấn enum/boolean thông thường, hãy **loại `null` khỏi tập tham số khi hợp đồng không cho phép**, đồng thời có test rõ ràng nếu ứng dụng thực sự cần tìm field null/missing.

## 8. Model và repository Spring Data MongoDB hoàn chỉnh

### 8.1. Enum cho trạng thái

File `OrderStatus.java`:

```java
package com.example.shop.orders;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

### 8.2. Entity

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String storeId,
    OrderStatus status,
    Boolean active,
    Instant createdAt
) {}
```

`Boolean active` được chọn để mô hình hóa được cả tài liệu legacy thiếu field: khi đọc, đối tượng có thể chứa `null` thay vì giả định thiếu field tương đương false. Giá trị `OrderStatus` được lưu dưới dạng tên enum thông thường khi không có custom converter. Các ID `O-1` không có dạng ObjectId nên được lưu như BSON String trong ví dụ.

### 8.3. Repository với bốn từ khóa

File `OrderRepository.java`:

```java
package com.example.shop.orders;

import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderDocument> findByStatusIn(
        Collection<OrderStatus> statuses);

    List<OrderDocument> findByStatusNotIn(
        Collection<OrderStatus> statuses);

    List<OrderDocument> findByActiveTrue();

    List<OrderDocument> findByActiveFalse();

    List<OrderDocument> findByStatusInAndActiveTrue(
        Collection<OrderStatus> statuses);

    List<OrderDocument> findByStatusNotInAndActiveTrue(
        Collection<OrderStatus> excludedStatuses);

    Page<OrderDocument> findByStoreIdAndStatusInAndActiveTrue(
        String storeId,
        Collection<OrderStatus> statuses,
        Pageable pageable);
}
```

Spring Data parse tên phương thức dựa trên **property** `status`, `active` và `storeId`. Không cần cài đặt thủ công cho các phương thức trên khi repository được quét/đăng ký đúng. Nếu field BSON đổi tên với `@Field("order_status")`, tên phương thức vẫn dùng **`Status`** vì đây là tên Java; mapping infrastructure xử lý field đích.

### 8.4. Minh họa method name → câu truy vấn

| Phương thức | Phần điều kiện được suy diễn |
| --- | --- |
| `findByStatusIn([NEW, PAID])` | `status: { $in: ["NEW","PAID"] }` |
| `findByStatusNotIn([CANCELLED])` | `status: { $nin: ["CANCELLED"] }` |
| `findByActiveTrue()` | `active: true` |
| `findByActiveFalse()` | `active: false` |
| `findByStatusInAndActiveTrue([NEW, PAID])` | `$in` trên status **và** active bằng true |
| `findByStatusNotInAndActiveTrue([CANCELLED])` | `$nin` trên status **và** active bằng true |
| `findByStoreIdAndStatusInAndActiveTrue("STORE-HCM", [...], page)` | Giới hạn store, lọc status, active và áp paging |

`And` kết hợp nhiều điều kiện theo phép giao. Khi tăng số điều kiện, tên phương thức có thể trở nên khó hiểu; ở truy vấn phức tạp, cân nhắc `MongoTemplate`, `@Query` hoặc `Aggregation` thay vì cố nối tất cả từ khóa vào một tên quá dài.

## 9. Xử lý input rỗng một cách có chủ đích ở service

Repository không nên là nơi quyết định ý nghĩa nghiệp vụ của “không có lựa chọn”. Service có thể bảo đảm contract và giới hạn dữ liệu trước khi tạo truy vấn.

### 9.1. Allowlist: rỗng nghĩa là không có kết quả

File `OrderFilterService.java`:

```java
package com.example.shop.orders;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class OrderFilterService {
    private final OrderRepository repository;

    public OrderFilterService(OrderRepository repository) {
        this.repository = repository;
    }

    public List<OrderDocument> findAllowedStatuses(
            Collection<OrderStatus> statuses) {
        Objects.requireNonNull(statuses, "statuses");

        // Không có trạng thái nào được cho phép.
        if (statuses.isEmpty()) {
            return List.of();
        }
        if (statuses.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                "Danh sách statuses không được chứa null");
        }
        return repository.findByStatusIn(statuses);
    }
}
```

Với hợp đồng này, `findAllowedStatuses(List.of())` trả list rỗng mà **không cần gọi MongoDB**. Điều này rõ ràng, tránh chi phí truy vấn và không phụ thuộc việc framework xử lý empty `In` ra sao.

### 9.2. Denylist: rỗng có thể bị từ chối

Nếu phương thức được sử dụng cho một báo cáo chỉ được xuất khi có tiêu chí loại trừ, ta có thể yêu cầu caller phải chọn ít nhất một trạng thái:

```java
public List<OrderDocument> findWithExclusions(
        Collection<OrderStatus> excludedStatuses) {
    Objects.requireNonNull(
        excludedStatuses, "excludedStatuses");

    if (excludedStatuses.isEmpty()) {
        throw new IllegalArgumentException(
            "Phải chọn ít nhất một trạng thái cần loại trừ");
    }
    if (excludedStatuses.stream().anyMatch(Objects::isNull)) {
        throw new IllegalArgumentException(
            "Danh sách loại trừ không được chứa null");
    }

    return repository.findByStatusNotIn(excludedStatuses);
}
```

Đây là **phương thức minh họa** có thể đặt thêm vào `OrderFilterService` ở phần trước. Nó không phải quy tắc framework bắt buộc: một chức năng tìm kiếm bình thường hoàn toàn có thể định nghĩa “denylist rỗng = không loại trạng thái nào”.

Nếu chọn ý nghĩa “không loại ai”, hãy gọi **một truy vấn có giới hạn và quyền rõ ràng**, chẳng hạn `findByActiveTrue()` chỉ trong một hệ thống đơn cửa hàng, hoặc tốt hơn `findByStoreIdAndActiveTrue(storeId)` trong hệ thống nhiều cửa hàng. Đừng vô tình biến input rỗng thành một full collection scan không có giới hạn.

### 9.3. Tenant/storeId không được lấy hoàn toàn từ input không tin cậy

Giả sử mỗi người dùng chỉ được xem đơn của cửa hàng được cấp quyền. Trong service, `storeId` phải được xác định/xác thực từ ngữ cảnh bảo mật, không chỉ tin vào chuỗi từ request. Câu repository:

```java
Page<OrderDocument> findByStoreIdAndStatusInAndActiveTrue(
    String storeId,
    Collection<OrderStatus> statuses,
    Pageable pageable);
```

là một cách thể hiện giới hạn này trong truy vấn. Nếu `statuses` rỗng, có thể trả trang rỗng có chủ đích; không được tự ý gọi một phương thức không lọc store khi “không chọn trạng thái”.

## 10. Phân trang và sorting

Khi danh sách `In` chứa nhiều trạng thái, số bản ghi phù hợp có thể lớn. Nên giới hạn kích thước trang và sắp xếp ổn định:

```java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest pageRequest = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<OrderDocument> page =
    repository.findByStoreIdAndStatusInAndActiveTrue(
        "STORE-HCM",
        List.of(OrderStatus.NEW, OrderStatus.PAID),
        pageRequest
    );
```

`id` là thuộc tính Java ánh xạ với `_id`. Thêm khóa tiebreak `id` giúp có thứ tự xác định khi nhiều document có cùng `createdAt`. Ví dụ này giả định có biến `repository` đã được inject.

`Page` thường kèm nhu cầu lấy tổng số bản ghi để tính tổng trang, có thể thêm chi phí truy vấn count. Nếu màn hình chỉ cần nút “xem thêm”, có thể cân nhắc `Slice` hoặc phân trang theo khóa tùy phiên bản framework và yêu cầu sản phẩm.

**Không coi việc thêm `Pageable` là bảo đảm an toàn tuyệt đối**: phải giới hạn page size ở API và có điều kiện phạm vi truy cập hợp lệ. Một câu `NotIn` ít chọn lọc với page rất lớn vẫn có thể gây tải cao.

## 11. Tương tác với dữ liệu null, missing và migration

Khi nâng cấp một hệ thống đang chạy, các document cũ có thể thiếu `status`/`active`, mang kiểu dữ liệu khác hoặc dùng giá trị enum đã bị xóa.

### 11.1. Kiểm tra field thực sự tồn tại

```javascript
// Field status không tồn tại.
db.orders.find({
  status: { $exists: false }
})

// Field status tồn tại và không null.
db.orders.find({
  status: { $exists: true, $ne: null }
})

// Boolean active bằng false thực sự.
db.orders.find({
  active: false
})
```

Trên dữ liệu ví dụ, câu đầu trả `O-4`, câu thứ hai trả `O-1`, `O-2`, `O-3`, `O-6` và `O-7`, câu thứ ba trả `O-2` và `O-5`.

**Không nên dùng `$exists: true` một mình để nói field có giá trị:** field hiện diện với BSON `null` vẫn thỏa `$exists: true`.

### 11.2. Khi enum có trạng thái mới

Giả sử phiên bản mới bổ sung `REFUNDED` vào trạng thái. `NotIn([CANCELLED])` có thể nhận cả `REFUNDED`, dù giao diện cũ chỉ định xử lý `NEW` và `PAID`. `In([NEW, PAID])` không tự mở rộng khi enum thêm giá trị.

Đây là một lý do dùng **allowlist** cho các hành động cần trạng thái được phê duyệt, chẳng hạn thanh toán, xuất báo cáo nhạy cảm hoặc xử lý hàng loạt. Sự mở rộng miền giá trị phải là quyết định nghiệp vụ được kiểm thử, không phải tác dụng phụ của `NotIn`.

### 11.3. Trạng thái boolean ba giá trị

Nếu `active` thiếu nghĩa là “chưa xác định”, không nên âm thầm chuyển nó thành `false` mà không có quyết định dữ liệu. Có thể cần migration đặt lại field theo nguồn có thẩm quyền hoặc bổ sung một trạng thái nghiệp vụ như `UNKNOWN`.

Khi model Java dùng `Boolean`, hãy xử lý `null` minh bạch ở service. `findByActiveFalse()` sẽ không tự tìm những document `active` bị thiếu để “bù” cho các đối tượng đang ở trạng thái không xác định.

## 12. Hiệu năng, index và giới hạn kích thước danh sách

Các từ khóa suy diễn chỉ là cách tạo câu truy vấn; tốc độ thực tế phụ thuộc phân bố dữ liệu, index và kích thước tập tham số.

Ví dụ endpoint thường lọc theo `storeId`, `active`, tập `status` và sắp xếp `createdAt` mới nhất:

```javascript
db.orders.createIndex({
  storeId: 1,
  active: 1,
  status: 1,
  createdAt: -1,
  _id: -1
})
```

Index này là **ứng viên cần đo** theo mẫu truy vấn, không phải bảo đảm tối ưu cho mọi tập `In`. Khi có nhiều giá trị trạng thái trong `$in`, cách kết hợp index scan và sorting có thể khác với câu lọc một trạng thái; một số phương án vẫn cần sort bổ sung.

Kiểm tra kế hoạch truy vấn:

```javascript
db.orders
  .find({
    storeId: "STORE-HCM",
    active: true,
    status: { $in: ["NEW", "PAID"] }
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Theo dõi `totalKeysExamined`, `totalDocsExamined`, `nReturned` và thời gian thực thi trên tập dữ liệu đại diện. Duyệt `explain` từ `mongosh` không đo được toàn bộ chi phí của service (serialization, round trip mạng, count query, mapping), nhưng giúp đánh giá cách MongoDB chạy truy vấn.

### 12.1. $nin thường kém chọn lọc

`$nin` có thể khớp phần lớn collection, nhất là khi tập loại trừ nhỏ. Một index trên `status` không đảm bảo `$nin` được tối ưu tốt; MongoDB vẫn có thể phải kiểm tra nhiều document.

Nếu thực tế chỉ cho phép một tập trạng thái nhỏ, `$in` với các trạng thái cho phép thường vừa diễn đạt đúng nghiệp vụ, vừa dễ kiểm soát tập kết quả hơn.

### 12.2. Danh sách In quá lớn

Khi `statuses` chỉ có vài enum, chi phí nhỏ. Nhưng một API khác có thể dùng `findByIdIn(Collection<String> ids)` với hàng chục nghìn ID. Danh sách rất lớn làm tăng kích thước lệnh, chi phí xử lý và có thể chạm giới hạn BSON của request. Với lượng lớn, cần cân nhắc chia batch, staging collection hoặc phương án truy vấn khác tùy bài toán.

Không xây danh sách `In`/`NotIn` từ input chưa kiểm tra độ dài. Nên đặt giới hạn đầu vào ở API/service và đo với phân bố dữ liệu thật.

### 12.3. Truy vấn đếm và aggregation

Một phương thức suy diễn cũng có thể đếm:

```java
long countByStatusIn(Collection<OrderStatus> statuses);
boolean existsByStatusIn(Collection<OrderStatus> statuses);
```

Chúng vẫn có ngữ nghĩa tập hợp tương ứng và cần xử lý input rỗng theo contract. Với dashboard cần nhóm nhiều trạng thái hoặc tính tổng doanh thu, `Aggregation`/`MongoTemplate` có thể phù hợp hơn nhiều phương thức repository gọi lặp lại.

## 13. Kiểm thử tích hợp trên MongoDB thật

Các quy tắc về `$in`, `$nin` và field thiếu nên được kiểm tra trên BSON **thực sự lưu**. Test mock repository không chứng minh MongoDB xử lý điều kiện rỗng ra sao.

Ví dụ sau dùng Spring Boot `@DataMongoTest` với MongoDB instance dành riêng cho test (có thể cấu hình qua Testcontainers theo hạ tầng dự án).

### 13.1. Seed bằng driver để tạo cả field thiếu và null

File `OrderDerivedQueriesTest.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class OrderDerivedQueriesTest {
    @Autowired
    MongoTemplate template;

    @Autowired
    OrderRepository repository;

    private static Document order(
            String id, String status, Boolean active) {
        Document document = new Document("_id", id)
            .append("storeId", "STORE-HCM")
            .append(
                "createdAt",
                Date.from(Instant.parse("2026-11-20T01:00:00Z"))
            );
        if (status != null) {
            document.append("status", status);
        }
        if (active != null) {
            document.append("active", active);
        }
        return document;
    }

    private static List<String> ids(List<OrderDocument> documents) {
        return documents.stream()
            .map(OrderDocument::id)
            .toList();
    }

    @BeforeEach
    void seed() {
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        Document missingStatus = order("O-4", null, true);
        Document nullStatus = order("O-5", null, false);
        nullStatus.append("status", null);
        Document missingActive = order("O-7", "NEW", null);

        collection.insertMany(List.of(
            order("O-1", "NEW", true),
            order("O-2", "PAID", false),
            order("O-3", "CANCELLED", true),
            missingStatus,
            nullStatus,
            order("O-6", "PAID", true),
            missingActive
        ));
    }

    @Test
    void inMatchesOnlyAllowedStatuses() {
        assertThat(ids(repository.findByStatusIn(
            List.of(OrderStatus.NEW, OrderStatus.PAID))))
            .containsExactlyInAnyOrder(
                "O-1", "O-2", "O-6", "O-7");
    }

    @Test
    void notInCanIncludeMissingAndNullStatuses() {
        assertThat(ids(repository.findByStatusNotIn(
            List.of(OrderStatus.CANCELLED))))
            .containsExactlyInAnyOrder(
                "O-1", "O-2", "O-4", "O-5", "O-6", "O-7");
    }

    @Test
    void trueAndFalseDoNotTreatMissingAsFalse() {
        assertThat(ids(repository.findByActiveTrue()))
            .containsExactlyInAnyOrder(
                "O-1", "O-3", "O-4", "O-6");

        assertThat(ids(repository.findByActiveFalse()))
            .containsExactlyInAnyOrder("O-2", "O-5");
    }

    @Test
    void emptyCollectionsHaveOppositeServerSemantics() {
        assertThat(repository.findByStatusIn(List.of()))
            .isEmpty();

        assertThat(repository.findByStatusNotIn(List.of()))
            .hasSize(7);
    }

    @Test
    void combinedFiltersExcludeWrongBooleanValues() {
        assertThat(ids(repository.findByStatusInAndActiveTrue(
            List.of(OrderStatus.NEW, OrderStatus.PAID))))
            .containsExactlyInAnyOrder("O-1", "O-6");
    }
}
```

Các test đặt dữ liệu trực tiếp qua `MongoTemplate.getCollection(...)` (driver) thay vì lưu `OrderDocument`, nhằm bảo đảm `status` bị thiếu thật sự khác `status: null`. Đây là điểm khó quan sát khi chỉ sử dụng mock hoặc ghi entity từ model Java mới.

**Điều kiện chạy:** test phải dùng MongoDB thử nghiệm được cô lập; `deleteMany(new Document())` xóa toàn bộ collection `orders` trong database của test. Không kết nối test này tới database thật hoặc một database dùng chung với tiến trình khác. Package import `@DataMongoTest` ở đây tương ứng dòng Spring Boot cung cấp annotation tại namespace minh họa; khi nâng cấp major version, đối chiếu package import của dependency thực tế.

Nếu test `emptyCollectionsHaveOppositeServerSemantics` khác kỳ vọng, hãy kiểm tra các câu lệnh MongoDB thực sự được gửi bởi phiên bản Spring Data/driver và custom query configuration đang dùng. Mục tiêu của test là **khóa hợp đồng** và phát hiện thay đổi qua lần nâng cấp.

### 13.2. Kiểm tra BSON trực tiếp cho hai operator rỗng

Để tách biệt ngữ nghĩa MongoDB server với parsing phương thức repository, có thể chạy:

```javascript
db.orders.countDocuments({ status: { $in: [] } })   // 0
db.orders.countDocuments({ status: { $nin: [] } })  // 7
```

Nếu lớp repository trả kết quả khác, hãy kiểm tra phần bind/biến đổi query của Spring Data, thay vì kết luận MongoDB có ngữ nghĩa khác.

### 13.3. Các kịch bản nên bổ sung

| Kịch bản | Kỳ vọng |
| --- | --- |
| Input `null` thay cho collection | Service từ chối hoặc xử lý đúng contract, không đẩy thẳng xuống repository |
| Collection chứa `null` | Service từ chối hoặc test rõ ngữ nghĩa MongoDB nếu hợp đồng cho phép |
| Trạng thái mới xuất hiện | `In` không mở rộng ngoài allowlist; `NotIn` có thể nhận giá trị chưa được biết |
| Field `active` bị thiếu/null/string | `True`/`False` chỉ khớp BSON Boolean tương ứng |
| Nhiều trạng thái và giới hạn store | Không trả document của store khác, kể cả với input rỗng |
| Paging với cùng `createdAt` | Tiebreak bằng `_id` giúp thứ tự ổn định |
| `NotIn` trên collection lớn | Đo số document examined và độ trễ để nhận diện truy vấn ít chọn lọc |
| Thay đổi custom converter enum | Kiểm tra BSON query và dữ liệu cũ, không chỉ kiểm thử enum mới |

## 14. Reactive repository có khác ngữ nghĩa không?

Khi dùng reactive access, tên phương thức suy diễn vẫn thể hiện các điều kiện tương tự; điều khác nằm ở API trả về và cách thực thi bất đồng bộ:

```java
import java.util.Collection;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    Flux<OrderDocument> findByStatusIn(
        Collection<OrderStatus> statuses);

    Flux<OrderDocument> findByStatusNotIn(
        Collection<OrderStatus> excludedStatuses);

    Flux<OrderDocument> findByActiveTrue();

    Flux<OrderDocument> findByActiveFalse();
}
```

Không giả định Reactive tự tối ưu `NotIn(empty)` hoặc tự bỏ qua field thiếu. Với pipeline reactive, service vẫn cần **kiểm tra tham số trước**, áp giới hạn truy cập và viết kiểm thử bằng `StepVerifier` hoặc công cụ tương đương. Một `Flux` trả về chậm do query không chọn lọc vẫn là vấn đề hiệu năng dù không chặn thread theo cách imperative.

## 15. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `findByStatusIn(empty)` không trả dữ liệu | `$in: []` không có giá trị để khớp | Nếu đây là ý nghĩa đúng, trả list rỗng từ service; nếu “không lọc”, viết nhánh khác |
| `findByStatusNotIn(empty)` trả quá nhiều dữ liệu | `$nin: []` không loại giá trị nào | Cấm input rỗng khi cần hoặc gọi query có phạm vi chặt |
| `NotIn([CANCELLED])` trả document thiếu status | `$nin` có thể nhận field không tồn tại | Dùng allowlist `In`, hoặc thêm `$exists`/`$ne` theo contract |
| `findByActiveFalse()` không trả document thiếu active | Boolean false khác field missing/null | Migration/validation hoặc yêu cầu nghiệp vụ rõ về trạng thái chưa biết |
| Truy vấn trả sai sau đổi tên field BSON | Nhầm tên Java property với field lưu trữ | Kiểm tra `@Field`, metadata và query mapper |
| Enum mới vẫn xuất hiện trong kết quả `NotIn` | Truy vấn dùng denylist thay vì allowlist | Xác định tập trạng thái cho phép dương tính |
| `NotIn` rất chậm dù có index status | Điều kiện ít chọn lọc, trả nhiều document | Đo `explain` và cân nhắc filter/index theo tenant, active, thời gian |
| Phân trang có kết quả lặp/thiếu giữa các lần đọc | Sort thiếu tie-break, dữ liệu thay đổi | Sort bằng createdAt + _id, dùng keyset khi phù hợp |
| Test mock repository xanh nhưng production khác | Mock không thực hiện BSON query | Dùng integration test với document missing/null thực |
| Input rỗng làm rộng phạm vi truy cập dữ liệu | Service tự bỏ filter mà không kiểm tra quyền | Giữ ràng buộc store/tenant, fail-closed cho allowlist rỗng |

## 16. Bài tập vận dụng

Một hệ thống quản lý thiết bị lưu collection `devices` với các field:

- `region`: mã vùng thuộc tenant.
- `state`: `ONLINE`, `OFFLINE`, `MAINTENANCE`, có thể thiếu ở bản ghi cũ.
- `verified`: BSON Boolean, có thể `null` nếu chưa kiểm tra.
- `lastSeenAt`: BSON Date.

Trang quản trị cần hiển thị thiết bị thuộc các trạng thái được phép, chỉ lấy thiết bị đã xác minh và sắp xếp mới nhất. Đồng thời có một báo cáo riêng dùng danh sách trạng thái cần loại.

Hãy thực hiện:

1. Viết repository `findByRegionAndStateInAndVerifiedTrue(...)` hỗ trợ `Pageable`; chỉ định tham số nào phải có giá trị.
2. Với `allowedStates = []`, chọn trả 0 kết quả hay bỏ điều kiện? Giải thích bằng chính sách truy cập.
3. Với `excludedStates = []`, giải thích vì sao `NotIn` có thể trả tất cả thiết bị nếu thiếu điều kiện phạm vi.
4. Chèn một document `verified: false`, một document thiếu `verified`, một document `verified: null` và kiểm tra `findByVerifiedFalse()` trả những document nào.
5. Đề xuất index ứng viên cho truy vấn theo `region`/`verified`/`state` và sorting theo `lastSeenAt`; dùng `explain` để kiểm chứng.
6. Thêm một trạng thái mới `QUARANTINED` rồi kiểm tra query allowlist và denylist còn đúng quy tắc nghiệp vụ không.

**Định hướng giải:** với allowlist phục vụ quyền truy cập, tập rỗng nên trả **không có bản ghi**. Với denylist, tập rỗng về mặt MongoDB nghĩa là không có giá trị bị loại, nên vẫn phải giữ điều kiện tenant/region và giới hạn trang. `False` chỉ khớp BSON Boolean false, không phải null/missing. Truy vấn hiệu quả là kết quả của mô hình dữ liệu, index và cách giới hạn phạm vi — không đến từ việc dùng tên phương thức repository ngắn hơn.

## 17. Tài liệu tham khảo

- Spring Data MongoDB — [Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): khai báo truy vấn suy diễn và các keyword MongoDB.
- Spring Data Commons — [Repository Query Keywords](https://docs.spring.io/spring-data/commons/reference/repositories/query-keywords-reference.html): cú pháp phương thức repository và từ khóa.
- MongoDB Manual — [`$in`](https://www.mongodb.com/docs/manual/reference/operator/query/in/): phép thuộc tập, field array và lưu ý hiệu năng.
- MongoDB Manual — [`$nin`](https://www.mongodb.com/docs/manual/reference/operator/query/nin/): phép không thuộc tập và quy tắc đối với field không tồn tại.
- MongoDB Manual — [`$exists`](https://www.mongodb.com/docs/manual/reference/operator/query/exists/): phân biệt field có mặt và không có mặt.

## Ghi nhớ

`In`/`NotIn` được Spring Data MongoDB suy diễn thành điều kiện thuộc tập/loại trừ; `True`/`False` so khớp **boolean chính xác**. Điểm quan trọng nhất là **`$in: []` không khớp document nào, còn `$nin: []` không loại document nào**. Hơn nữa, `$nin` có thể nhận cả document thiếu field, trong khi `False` không tự nhận document có field thiếu hoặc null. Vì vậy hãy xác định contract cho input rỗng tại service, dùng allowlist khi cần an toàn theo quyền, giữ bộ lọc store/tenant, kiểm thử BSON với null/missing thực và đo query bằng index/explain trước khi triển khai.
