# Scrolling, ScrollPosition và Window theo phiên bản

## 1. Vì sao cần Scrolling bên cạnh phân trang thông thường?

Một hệ thống bán hàng có hàng triệu đơn hàng trong MongoDB. Endpoint `GET /orders` chỉ cần hiển thị 20 đơn mỗi lần, trong khi một công việc xử lý nền phải duyệt qua hàng trăm nghìn đơn theo thứ tự ổn định.

Cách làm quen thuộc là dùng `Pageable`:

```java
PageRequest.of(0, 20);
PageRequest.of(1, 20);
PageRequest.of(2, 20);
```

Ở đây mỗi lần gọi có số trang, kích thước trang; MongoDB thường sử dụng `skip` và `limit` cho phân trang offset. Cách này thuận tiện khi người dùng muốn đi đến **trang thứ N**, nhưng có hai hạn chế đáng lưu ý:

- Với offset lớn, database có thể phải bỏ qua rất nhiều kết quả trước khi trả về 20 document.
- Nếu có document mới được chèn, xóa hoặc bị đổi thứ tự giữa các lần đọc, người dùng có thể gặp bản ghi **lặp hoặc bị bỏ qua**.

**Scrolling** chọn cách duyệt liên tiếp từng **cửa sổ (window)**. Ứng dụng nhận một `Window<T>` gồm tối đa một lượng kết quả có giới hạn, lấy một `ScrollPosition` để **tiếp tục sau phần tử cuối**, rồi đọc cửa sổ tiếp theo. Đây là bài thuộc chương **Phân trang và luồng** trong module **SPRING_DATA_MONGODB**: dùng Spring Data MongoDB để truy cập document qua repository hoặc `MongoTemplate`, đồng thời hiểu tác động của thứ tự sắp xếp, index, tính nhất quán, reactive access, kiểm thử và hiệu năng.

**Phải phân biệt ngay:** một `Window<T>` không phải MongoDB tailable cursor, không phải `Stream<T>` dùng một cursor mở lâu dài và cũng không phải snapshot bất biến của toàn collection. Mỗi lần lấy cửa sổ kế tiếp có thể thực hiện một truy vấn mới.

## 2. Hỗ trợ theo phiên bản Spring Data

Đề bài nhấn mạnh **theo phiên bản** vì Scroll API không hiện diện đồng nhất ở mọi dòng Spring Data.

| Thành phần và mốc | Ý nghĩa đối với ví dụ trong bài |
| --- | --- |
| **Spring Data Commons 3.1+** | Có các kiểu `ScrollPosition`, `OffsetScrollPosition`, `KeysetScrollPosition`, `Window<T>` và tiện ích `WindowIterator`. |
| **Spring Data MongoDB 4.1+** | Có hỗ trợ scrolling ở tầng repository và phương thức `MongoOperations.scroll(Query, Class<T>)`; có API tương ứng trong template imperative/reactive. |
| **Spring Data MongoDB 4.0 trở xuống** | Không nên sao chép trực tiếp ví dụ `MongoTemplate.scroll(...)`; thường phải dùng `skip/limit`, query keyset thủ công hoặc nâng cấp. |
| **Dòng 4.2, 4.3, 4.4, 4.5, 5.x** | Scroll API tiếp tục có mặt, nhưng chữ ký overload, tiện ích và yêu cầu nền tảng phải kiểm tra bằng Javadoc đúng phiên bản. |
| **Spring Boot dùng dependency management** | Xác định phiên bản `spring-data-mongodb` và `spring-data-commons` **thực tế** từ dependency tree/BOM; không chọn API chỉ dựa trên tên bản Spring Boot. |

Các mốc này phản ánh API Spring Data, **không** phải một tính năng `scroll()` mới được cài trong chính MongoDB Server. Spring Data xây truy vấn MongoDB để thực thi việc cuộn dữ liệu. Những khác biệt như khả năng dùng `Query.with(ScrollPosition)`, kiểu trả về reactive, hoặc các overload mới phải đối chiếu theo version đang triển khai.

Những phần code bên dưới lấy **Spring Data MongoDB 4.1+ / Spring Data Commons 3.1+** làm phạm vi tối thiểu cho các API scrolling được minh họa; cần Java và các dependency tương thích với release đó.

**Tham khảo chính thức để đối chiếu phiên bản:**

- [MongoDB-specific Query Methods – Scrolling](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html)
- [Spring Data Commons – Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [MongoOperations Javadoc](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/MongoOperations.html)
- [ReactiveMongoOperations Javadoc](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/ReactiveMongoOperations.html)

Các URL tham khảo mặc định có thể trỏ tới bản tài liệu hiện hành; khi cần biên dịch một ứng dụng cụ thể, chọn bản Javadoc tương ứng với artifact đang dùng.

## 3. Ba đối tượng chính trong Scroll API

| Khái niệm | Vai trò | Không nên nhầm với |
| --- | --- | --- |
| `Window<T>` | Một nhóm kết quả có giới hạn và khả năng lấy vị trí để đọc tiếp | `Page<T>` có tổng số bản ghi/trang |
| `ScrollPosition` | Vị trí **loại trừ**: lần truy vấn sau bắt đầu **sau** vị trí đó | Số trang hay khóa MongoDB cursor |
| `OffsetScrollPosition` | Biểu diễn vị trí theo chỉ số trong tập kết quả có thứ tự | Offset ban đầu luôn là `0` |
| `KeysetScrollPosition` | Biểu diễn vị trí bằng giá trị các khóa sắp xếp và khóa phân biệt | Chỉ dùng mỗi `_id` cho mọi kiểu sort |
| `WindowIterator<T>` | Tiện ích lặp qua nhiều `Window` bằng cách yêu cầu cửa sổ tiếp | `Stream` giữ cursor server mở liên tục |

Một truy vấn scrolling cần ba yếu tố: **điều kiện lọc**, **thứ tự sắp xếp ổn định**, và **giới hạn số kết quả mỗi lượt**. Vị trí chỉ có ý nghĩa khi các yếu tố đó nhất quán giữa các lượt đọc.

### 3.1. Quy tắc vị trí loại trừ

Giả sử tập kết quả được sắp theo thời gian rồi ID:

```text
Vị trí     0        1        2        3        4
Đơn hàng   A        B        C        D        E
            └── Window 1 ──┘  └── Window 2 ──┘
               A, B, C          D, E
```

Nếu cửa sổ đầu chứa `A, B, C`, vị trí lấy từ `C` được truyền vào lần sau. Cửa sổ tiếp theo bắt đầu **sau C**, không trả lại C một lần nữa.

Cần đặc biệt chú ý:

- `ScrollPosition.offset()`: **vị trí khởi đầu**, chưa trỏ vào phần tử có chỉ số cụ thể.
- `ScrollPosition.offset(0)`: đã trỏ tới phần tử chỉ số 0; do vị trí được hiểu **exclusive**, cửa sổ sau nó **bỏ qua phần tử đầu tiên**.
- `ScrollPosition.keyset()`: **vị trí keyset khởi đầu**, chưa áp dụng điều kiện tiếp tục theo khóa.
- `window.positionAt(window.size() - 1)`: lấy vị trí của phần tử cuối trong cửa sổ **không rỗng**, để gọi tiếp.

Không gọi `positionAt(-1)` hoặc giả định cửa sổ rỗng vẫn có phần tử cuối.

## 4. Tạo dữ liệu để quan sát

Ví dụ collection `orders`, mỗi đơn có `customerId`, `placedAt`, `status` và `totalAmount`. Khi học scrolling, dùng database kiểm thử; không sao chép lệnh ghi vào production.

```javascript
db.orders.insertMany([
  {
    _id: "ord-001",
    customerId: "cus-01",
    placedAt: ISODate("2026-11-20T02:06:00Z"),
    status: "PAID",
    totalAmount: NumberDecimal("100000")
  },
  {
    _id: "ord-002",
    customerId: "cus-01",
    placedAt: ISODate("2026-11-20T02:05:00Z"),
    status: "PAID",
    totalAmount: NumberDecimal("200000")
  },
  {
    _id: "ord-003",
    customerId: "cus-01",
    placedAt: ISODate("2026-11-20T02:05:00Z"),
    status: "PAID",
    totalAmount: NumberDecimal("300000")
  },
  {
    _id: "ord-004",
    customerId: "cus-01",
    placedAt: ISODate("2026-11-20T02:04:00Z"),
    status: "PAID",
    totalAmount: NumberDecimal("400000")
  },
  {
    _id: "ord-005",
    customerId: "cus-01",
    placedAt: ISODate("2026-11-20T02:03:00Z"),
    status: "PAID",
    totalAmount: NumberDecimal("500000")
  }
]);
```

Hai đơn `ord-002` và `ord-003` có cùng thời điểm. Nếu chỉ sort theo `placedAt`, thứ tự của chúng có thể không đủ ổn định cho một con trỏ theo từng phần tử. Chúng ta sẽ dùng thêm `_id` như khóa phân biệt.

Kiểm tra dữ liệu trong `mongosh`:

```javascript
db.orders.find({ customerId: "cus-01" })
  .sort({ placedAt: -1, _id: -1 });
```

Với thứ tự giảm dần `placedAt` rồi giảm dần `_id`, phần đầu lần lượt là `ord-001`, `ord-003`, `ord-002`, `ord-004`, `ord-005`.

## 5. Định nghĩa entity và repository

### 5.1. Entity phù hợp với khóa keyset

Ví dụ Java 17+:

```java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING)
    String id,

    String customerId,
    Instant placedAt,
    String status,

    @Field(targetType = FieldType.DECIMAL128)
    BigDecimal totalAmount
) {}
```

`@MongoId(FieldType.STRING)` giúp thống nhất `_id` dạng BSON string và tránh nhầm với ObjectId. `placedAt` cần **không null**, có cùng kiểu BSON Date trên các document và nên là giá trị tương đối ổn định sau khi đơn được tạo. Với keyset, các trường sort bị thiếu/null có thể làm phép so sánh hoặc dựng con trỏ thất bại.

### 5.2. Repository scroll theo thời gian đặt và ID

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    Window<OrderDocument>
    findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(
        String customerId,
        ScrollPosition position
    );
}
```

Ý nghĩa của method:

- `findFirst2By...`: mỗi cửa sổ lấy một lượng nhỏ (ví dụ **2**) phục vụ bài thực hành.
- `ByCustomerId`: lọc theo một khách hàng.
- `OrderByPlacedAtDescIdDesc`: sort giảm dần theo thời gian rồi ID, tạo thứ tự toàn phần khi `_id` là duy nhất.
- `ScrollPosition`: truyền vị trí bắt đầu hoặc vị trí tiếp tục.
- `Window<OrderDocument>`: kết quả cuộn, khác `Page` và `Slice`.

Trong ví dụ production, có thể dùng `findFirst20By...` hoặc giới hạn động qua API phù hợp của phiên bản; không nên lấy cửa sổ cực lớn. Spring Data có cơ chế bổ sung khóa chính khi keyset cần đảm bảo thứ tự duy nhất; ta viết ID vào sort tường minh ở đây để hợp đồng và index dễ kiểm tra.

## 6. Offset scrolling với `ScrollPosition.offset()`

### 6.1. Đọc từng cửa sổ

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public void readOrdersByOffset(
    OrderRepository repository,
    String customerId
) {
    ScrollPosition position = ScrollPosition.offset();

    while (true) {
        Window<OrderDocument> window =
            repository.findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(
                customerId, position
            );

        for (OrderDocument order : window) {
            System.out.println(order.id());
        }

        if (window.isEmpty() || window.isLast()) {
            break;
        }

        position = window.positionAt(window.size() - 1);
    }
}
```

Luồng hoạt động:

1. `ScrollPosition.offset()` bắt đầu ở đầu danh sách.
2. Cửa sổ đầu nhận tối đa 2 document.
3. Nếu còn dữ liệu, lấy `positionAt` ở document cuối rồi gửi lại.
4. Sau mỗi lần đọc, tiếp tục cho tới khi `isLast()` hoặc `isEmpty()`.

`Window.isLast()` biểu thị cửa sổ cuối trong phạm vi kết quả tại thời điểm thực hiện truy vấn; nó không phải cam kết rằng collection sẽ **không bao giờ** có document mới.

### 6.2. Bẫy off-by-one

Hai lời gọi dưới đây **không tương đương**:

```java
ScrollPosition start = ScrollPosition.offset();

// Không phải vị trí đầu tiên, mà là vị trí ngay SAU phần tử chỉ số 0.
ScrollPosition afterFirst = ScrollPosition.offset(0);
```

Do con trỏ là **exclusive**, nếu muốn nhận phần tử đầu tiên thì dùng `ScrollPosition.offset()` hoặc `OffsetScrollPosition.initial()` ở phiên bản có API này. Nếu vô tình dùng `offset(0)` để khởi tạo, người đọc có thể không biết rằng đơn đầu tiên bị bỏ qua.

### 6.3. Chi phí offset lớn

Ví dụ tương đương về ý tưởng với truy vấn `skip`:

```javascript
db.orders.find({ customerId: "cus-01" })
  .sort({ placedAt: -1, _id: -1 })
  .skip(100000)
  .limit(20);
```

Một request chỉ trả 20 document, nhưng MongoDB có thể phải duyệt một lượng kết quả lớn trước đó. Chi phí thường tăng theo độ sâu `skip`. Offset scrolling cải thiện việc **không cần giữ toàn bộ kết quả trong RAM client**, nhưng không loại bỏ chi phí skip trên server.

**Chọn offset** nếu dữ liệu nhỏ/vừa, hoặc ứng dụng cần vị trí theo chỉ số và ưu tiên đơn giản hơn tối ưu sâu. Với luồng cuộn qua rất nhiều document, keyset thường đáng cân nhắc hơn.

## 7. Keyset scrolling với `ScrollPosition.keyset()`

### 7.1. Nguyên lý

Thay vì nói “bỏ qua 100.000 document”, keyset lưu **khóa sort của phần tử cuối đã thấy**, chẳng hạn:

```text
placedAt = 2026-11-20T02:05:00Z
id       = ord-003
```

Để tìm phần tử kế tiếp với sort giảm dần `placedAt`, `_id`, MongoDB có thể lọc những document **nhỏ hơn về thứ tự** so với khóa cuối:

```javascript
// Minh họa logic, không phải BSON do Spring Data cam kết sinh ra.
const lastTime = ISODate("2026-11-20T02:05:00Z");
const lastId = "ord-003";

db.orders.find({
  customerId: "cus-01",
  $or: [
    { placedAt: { $lt: lastTime } },
    { placedAt: lastTime, _id: { $lt: lastId } }
  ]
})
.sort({ placedAt: -1, _id: -1 })
.limit(2);
```

Vì có cả thời gian và ID, `ord-002` vẫn được trả sau `ord-003` dù chúng cùng `placedAt`. Nếu chỉ so sánh `placedAt < lastTime`, đơn `ord-002` có cùng thời điểm sẽ bị bỏ sót.

**Spring Data xây điều kiện keyset dựa trên sort và metadata ID**, nên không cần tự viết `$or` cho một derived repository query bình thường. Truy vấn minh họa giúp hiểu cơ chế, không khẳng định đúng từng byte của command do framework phát sinh trong mọi version.

### 7.2. Cách gọi repository

Dùng cùng phương thức ở mục 5:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public void readOrdersByKeyset(
    OrderRepository repository,
    String customerId
) {
    ScrollPosition position = ScrollPosition.keyset();

    while (true) {
        Window<OrderDocument> window =
            repository.findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(
                customerId, position
            );

        for (OrderDocument order : window) {
            System.out.printf(
                "%s - %s%n", order.id(), order.placedAt()
            );
        }

        if (window.isEmpty() || window.isLast()) {
            return;
        }

        position = window.positionAt(window.size() - 1);
    }
}
```

Cách gọi gần như giống offset, nhưng backend dùng **khóa sort để lọc thay vì nhảy qua một lượng bản ghi**. Với index phù hợp và dữ liệu lớn, keyset có thể duy trì độ trễ ổn định hơn khi cuộn sâu.

### 7.3. Keyset có các tiền điều kiện bắt buộc

- **Có sort ổn định:** cùng một bộ lọc và cùng thứ tự giữa mọi request.
- **Khóa sort không null:** tránh field thiếu/null; MongoDB không thể dựng điều kiện so sánh thông thường `$gt/$lt` tin cậy trên các khóa sort null/thiếu.
- **Có khóa phân biệt duy nhất:** MongoDB `_id` thường được Spring Data dùng như thành phần bổ sung để phân biệt kết quả có khóa sort giống nhau.
- **Projection chứa đủ khóa:** nếu chỉ trả `status` và bỏ `placedAt` hoặc `id`, Spring Data không thể dựng keyset tiếp theo một cách chắc chắn; phải bao gồm chúng trong projection/DTO.
- **BSON type nhất quán:** không trộn `placedAt` dạng string với BSON Date, hoặc ID dạng string/ObjectId giữa các document.
- **Index phù hợp:** ưu tiên index trên bộ lọc và thứ tự sort, nhưng vẫn kiểm tra bằng `explain`.
- **Trường sort ổn định theo nghiệp vụ:** nếu `placedAt` bị cập nhật, document có thể chuyển sang phía khác của ranh giới; keyset không tự tạo snapshot.

Một sai lầm thường gặp là dùng `status` làm khóa sort duy nhất khi trạng thái thay đổi liên tục và có rất nhiều bản ghi cùng `status`. Nếu không bổ sung ID và không suy nghĩ về thay đổi giữa các request, kết quả cuộn có thể không ổn định.

## 8. Lựa chọn index cho Keyset

Với câu truy vấn lọc theo `customerId` và sort `placedAt DESC, _id DESC`, một index có thể phù hợp:

```javascript
db.orders.createIndex({
  customerId: 1,
  placedAt: -1,
  _id: -1
});
```

Trong các truy vấn keyset, MongoDB cần lọc `customerId` và tiếp tục từ một bộ khóa. Index phù hợp có thể hỗ trợ cả lọc, sort và điều kiện tiếp tục.

Kiểm tra bằng `mongosh`:

```javascript
db.orders.find({
  customerId: "cus-01",
  $or: [
    { placedAt: { $lt: ISODate("2026-11-20T02:05:00Z") } },
    {
      placedAt: ISODate("2026-11-20T02:05:00Z"),
      _id: { $lt: "ord-003" }
    }
  ]
})
.sort({ placedAt: -1, _id: -1 })
.limit(2)
.explain("executionStats");
```

Quan sát các chỉ số như `totalKeysExamined`, `totalDocsExamined`, stage `IXSCAN`/`COLLSCAN`, chi phí sort và thời gian query. Đừng khẳng định query keyset luôn dùng index chỉ vì code có `ScrollPosition.keyset()`; index còn phụ thuộc cardinality, điều kiện, collation và quyết định query planner.

**Không tạo index chỉ dựa vào hình dạng một ví dụ.** Nếu use case thật lọc `status` rồi sort theo `placedAt`, có thể cần một index khác. Index rộng hơn tăng dung lượng và chi phí ghi; hiệu năng phải được đo trên dữ liệu đại diện.

## 9. `Window<T>` khác `Page<T>`, `Slice<T>` và Stream thế nào?

| API | Mục tiêu | Cần tổng số phần tử? | Cách tiếp tục |
| --- | --- | --- | --- |
| `Page<T>` | UI cần tổng trang/số kết quả | Thường cần count | `Pageable`, số trang và size |
| `Slice<T>` | UI chỉ cần biết còn trang sau | Không nhất thiết cần count | `Pageable` và next pageable |
| `Window<T>` | Duyệt tiếp theo một vị trí trong kết quả sort | Không cần tổng count | `ScrollPosition` từ phần tử cuối |
| `Stream<T>` từ repository | Xử lý tuần tự, có thể liên quan cursor mở | Không mặc định | Đọc trên stream, **đóng tài nguyên** |
| `Flux<T>` từ reactive repository | Chuỗi kết quả không chặn, có backpressure tùy nguồn | Không mặc định | Publisher; không tự biến thành Window |
| Tailable/change stream | Theo dõi dữ liệu mới/sự kiện của MongoDB | Không | Cursor hoặc subscription chuyên biệt |

### 9.1. Không nhầm `Window` với cursor server

`Window<T>` chứa một lượng phần tử hữu hạn tại một thời điểm. Khi gọi tiếp bằng `ScrollPosition`, ứng dụng gửi **truy vấn tiếp theo**. Nó không hứa một MongoDB cursor sẽ được giữ mở xuyên suốt toàn bộ cuộc duyệt.

Một `Stream<T>` repository có thể dùng cursor và cần đóng bằng `try-with-resources` để tránh giữ tài nguyên. MongoDB change stream/tailable cursor lại là các API dành cho dữ liệu mới hoặc sự kiện, không phải một dạng của `Window<T>`.

### 9.2. Không phải lúc nào có `Window` cũng tốt hơn `Slice`

Nếu ứng dụng cần đi thẳng tới trang 17 và hiển thị tổng 1.250 đơn, `Page` có thể phù hợp với chức năng, dù chi phí count/offset cao hơn. Nếu ứng dụng chỉ có nút “Xem thêm” hoặc công việc xuất dữ liệu quét lần lượt, `Window` thường hợp lý.

Không chuyển mọi endpoint sang scrolling chỉ để sử dụng API mới. Hãy xác định trải nghiệm người dùng và yêu cầu nhất quán trước.

## 10. `WindowIterator`: duyệt nhiều cửa sổ gọn hơn

Việc liên tục kiểm tra `isEmpty()`, `isLast()` và tính vị trí dễ bị lặp mã. Spring Data Commons cung cấp `WindowIterator<T>` từ dòng API có scrolling.

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

public void processAll(
    OrderRepository repository,
    String customerId
) {
    WindowIterator<OrderDocument> iterator = WindowIterator
        .of(position ->
            repository
                .findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(
                    customerId, position
                )
        )
        .startingAt(ScrollPosition.keyset());

    while (iterator.hasNext()) {
        OrderDocument order = iterator.next();
        System.out.println("Xử lý: " + order.id());
    }
}
```

`WindowIterator` dùng hàm nhận `ScrollPosition` để tự yêu cầu các `Window` kế tiếp và trình bày giao diện duyệt dạng `Iterator<T>`. Nó hữu ích trong các công việc xử lý tuần tự nhưng cần hiểu:

- Nó **không** làm các truy vấn thành một transaction.
- Nó **không** tự xử lý retry idempotent nếu công việc dừng giữa chừng.
- Nó **không** bảo đảm thứ tự bất biến khi có document bị sửa/xóa/chèn đồng thời.
- Với dữ liệu lớn, vẫn cần quan tâm tốc độ xử lý từng phần tử, checkpoint và số lần truy vấn.

Không dùng `WindowIterator` thay cho một thiết kế batch song song có quản lý partition nếu khối lượng và SLA đòi hỏi. Cũng không dùng nó như một tailable cursor theo dõi dữ liệu mới mãi mãi.

## 11. Dùng `MongoTemplate.scroll(...)` khi cần query động

Repository derived query tiện cho bộ lọc và sort tương đối cố định. Khi cần xây điều kiện động, thay đổi giới hạn hoặc chọn projection, có thể sử dụng **MongoTemplate** ở phiên bản hỗ trợ scrolling.

### 11.1. Query với vị trí bắt đầu

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.Window;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Window<OrderDocument> fetchWindow(
    MongoTemplate template,
    String customerId,
    ScrollPosition position
) {
    Query query = Query.query(
        Criteria.where("customerId").is(customerId)
    );

    query.with(
        Sort.by(
            Sort.Order.desc("placedAt"),
            Sort.Order.desc("id")
        )
    );
    query.limit(20);
    query.with(position);

    return template.scroll(query, OrderDocument.class);
}
```

`Query.with(position)` mang vị trí offset hoặc keyset vào truy vấn; `limit(20)` giới hạn số document trả mỗi cửa sổ. Kiểu `OrderDocument.class` giúp Spring Data dùng metadata mapping của entity (ví dụ `id` ánh xạ vào `_id`).

Một số phiên bản có overload `scroll(query, entityType, collectionName)` để chỉ định collection tường minh. Hãy đối chiếu Javadoc của bản đang dùng trước khi dùng overload đó.

### 11.2. Lấy cửa sổ tiếp theo

```java
ScrollPosition pos = ScrollPosition.keyset();

while (true) {
    Window<OrderDocument> window =
        fetchWindow(mongoTemplate, "cus-01", pos);

    for (OrderDocument order : window) {
        System.out.println(order.id());
    }

    if (window.isEmpty() || window.isLast()) {
        break;
    }

    pos = window.positionAt(window.size() - 1);
}
```

Đây là vòng lặp truy vấn hữu hạn. Nếu query được xây lại mỗi lượt, **bộ lọc, sort, page size và các option ảnh hưởng kết quả phải đồng nhất**. Truyền cùng một con trỏ vào truy vấn có sort khác là không an toàn.

### 11.3. Projection và con trỏ keyset

Giả sử muốn trả DTO danh sách chỉ có `id`, `status`, `totalAmount`, `placedAt`. Với keyset, **phải giữ `id` và `placedAt`** vì đó là khóa sort/định vị. Nếu một projection loại bỏ `placedAt` thì framework có thể không rút ra được keyset từ phần tử cuối.

```java
query.fields()
    .include("id")
    .include("placedAt")
    .include("status")
    .include("totalAmount");
```

Trong một query có metadata của `OrderDocument`, property `id` tương ứng `_id` trong BSON. Khi dùng API raw driver hoặc DTO mapping đặc biệt, phải xác minh tên field thực tế và tránh nhầm `id` với `_id`.

Với interface/record DTO, cần bảo đảm constructor/getter chứa **toàn bộ khóa sắp xếp và ID**. Có thể muốn giấu chúng khỏi HTTP response nhưng vẫn cần chúng trong kết quả từ repository để dựng con trỏ tiếp tục.

## 12. Reactive scrolling: một cửa sổ dưới dạng `Mono<Window<T>>`

Ở các phiên bản Spring Data MongoDB có ReactiveMongoTemplate scrolling, phương thức `scroll(...)` trả về `Mono<Window<T>>`. Đây là một khác biệt API quan trọng so với việc hiểu nhầm rằng mọi reactive repository query luôn trả `Flux<T>`.

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Sort;
import org.springframework.data.domain.Window;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import reactor.core.publisher.Mono;

public Mono<Window<OrderDocument>> fetchReactiveWindow(
    ReactiveMongoTemplate template,
    String customerId,
    ScrollPosition position
) {
    Query query = Query.query(
        Criteria.where("customerId").is(customerId)
    );
    query.with(
        Sort.by(
            Sort.Order.desc("placedAt"),
            Sort.Order.desc("id")
        )
    );
    query.limit(20);
    query.with(position);

    return template.scroll(query, OrderDocument.class);
}
```

Trong Reactor, một `Mono<Window<T>>` đại diện **một lần đọc window**. Nếu cần nhiều window, xây chuỗi gọi tiếp dựa trên `positionAt` và điều kiện `isLast`/`isEmpty`. Cần bảo đảm các lần gọi không chạy song song vô tình gây sai thứ tự, không dùng `block()` trong luồng WebFlux và không phát ra vô hạn dữ liệu khi client đã hủy subscription.

Ví dụ ý tưởng tổ chức nhiều cửa sổ thành `Flux<Window<OrderDocument>>`:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<Window<OrderDocument>> windows =
    fetchReactiveWindow(
        reactiveMongoTemplate,
        "cus-01",
        ScrollPosition.keyset()
    ).expand(window -> {
        if (window.isEmpty() || window.isLast()) {
            return Mono.empty();
        }

        ScrollPosition next =
            window.positionAt(window.size() - 1);

        return fetchReactiveWindow(
            reactiveMongoTemplate,
            "cus-01",
            next
        );
    });
```

Đây là mẫu xử lý **một đường kế tiếp** cho mỗi cửa sổ. Trong ứng dụng thật, nên bổ sung quản lý lỗi, cancellation, giới hạn tổng số phần tử, checkpoint và monitoring. Reactive không tự làm mất chi phí query, không tự tạo transaction hoặc biến keyset thành snapshot.

Với nhu cầu đọc liên tục không ngừng, hãy cân nhắc reactive cursor/change streams theo use case thay vì dùng `scroll` như một cơ chế nghe dữ liệu mới.

## 13. Cursor token cho API “Xem thêm”

Ứng dụng web/mobile thường không giữ trực tiếp instance Java `ScrollPosition` giữa nhiều HTTP request. Có thể thiết kế endpoint:

```text
GET /orders?customerId=cus-01&limit=20
→ { items: [...], nextCursor: "opaque-token" }

GET /orders?customerId=cus-01&limit=20&cursor=opaque-token
→ { items: [...], nextCursor: "next-token-or-null" }
```

**Không nên đưa trực tiếp `ScrollPosition.toString()` ra HTTP rồi mặc định đó là serialization protocol ổn định**. Cần tự định nghĩa format cursor của ứng dụng hoặc dùng một codec được kiểm soát, có version và tính toàn vẹn.

### 13.1. Cursor nên chứa gì?

Một cursor keyset thường cần những thông tin sau (dạng cấu trúc minh họa trước khi mã hóa):

```json
{
  "v": 1,
  "mode": "keyset",
  "customerId": "cus-01",
  "sort": ["placedAt:DESC", "id:DESC"],
  "lastPlacedAt": "2026-11-20T02:05:00Z",
  "lastId": "ord-003",
  "limit": 20
}
```

Ví dụ trên giải thích cách ứng dụng lưu vị trí; **không phải JSON do Spring Data tự động sinh ra**. Từ các trường này, ứng dụng có thể tái dựng điều kiện keyset theo hợp đồng đã xác định hoặc khôi phục kiểu `KeysetScrollPosition` bằng API tương ứng của phiên bản, sau khi kiểm tra dữ liệu và kiểu BSON.

Một token sản xuất nên:

- Có **version** để hỗ trợ thay đổi schema và sort.
- Ràng buộc vào **bộ lọc/tenant/quyền** để không dùng cursor của khách A cho khách B.
- Có chữ ký/HMAC hoặc cơ chế chống sửa tùy mức độ nhạy cảm; base64 không phải cơ chế bảo vệ dữ liệu.
- Không lộ thông tin riêng tư nhạy cảm dưới dạng văn bản đọc được; cân nhắc mã hóa nếu cần.
- Giới hạn kích thước, thời hạn, thứ tự và số lượng item.
- Từ chối cursor không hợp lệ hoặc không tương thích với truy vấn hiện tại.

Phân trang bằng cursor không được dùng để vượt kiểm tra quyền truy cập. Với mỗi request, API vẫn phải xác minh người dùng và điều kiện truy vấn.

### 13.2. Khi nào nên vô hiệu hóa cursor?

Nếu hệ thống đổi sort từ `placedAt DESC` sang `paidAt DESC`, cursor cũ không còn tương thích. Nếu kiểu `_id` hoặc `placedAt` thay đổi, các khóa trong token cũ có thể không còn so sánh đúng BSON. Nếu quyền truy cập hoặc bộ lọc thay đổi, ứng dụng có thể phải yêu cầu tải lại từ đầu.

Cần trả lỗi có ý nghĩa hoặc yêu cầu client bắt đầu lại, **không âm thầm tiếp tục bằng một sort khác**.

## 14. Thay đổi đồng thời: offset và keyset đều có giới hạn

### 14.1. Offset có thể lặp hoặc bỏ sót bản ghi

Giả sử cửa sổ đầu là `A, B` trong một danh sách sort mới nhất trước. Trước khi client lấy cửa sổ thứ hai, có người tạo document mới đứng trước `A`. Nếu client dùng offset = 2 dựa trên thứ tự cũ, kết quả có thể chứa `B` một lần nữa, làm trùng dữ liệu.

Tương tự, khi một document ở trước vị trí offset bị xóa, những document sau có thể bị dịch lên và một phần tử chưa đọc bị bỏ qua.

### 14.2. Keyset giảm tác động dịch chuyển vị trí, nhưng không tạo snapshot

Nếu cursor lưu khóa sort của `B`, document mới nằm **trước B** thường không ảnh hưởng việc lấy tiếp những document **sau B**. Đây là lý do keyset phù hợp với cuộn sâu trên tập dữ liệu lớn.

Tuy nhiên:

- Một document chưa đọc đổi `placedAt` và chuyển sang trước cursor có thể bị **bỏ lỡ**.
- Một document đã đọc đổi khóa sort và chuyển xuống sau cursor có thể được **đọc lại**.
- Một document bị xóa sẽ không xuất hiện ở các cửa sổ tiếp theo.
- Các write concurrent có thể ảnh hưởng thứ tự/trang; mỗi window không mặc nhiên được cố định trong cùng một MongoDB snapshot.

Do đó, scrolling là một **chiến lược duyệt kết quả**, không phải cam kết “mỗi bản ghi của toàn bộ dữ liệu sống được xử lý đúng một lần”.

### 14.3. Xử lý nền phải có checkpoint và idempotency

Đối với job xử lý hàng triệu đơn, nên xác định:

1. Khóa sort có **bất biến** hoặc đủ ổn định hay không?
2. Lưu checkpoint **sau khi** xử lý thành công phần tử/nhóm phần tử theo quy tắc nghiệp vụ nào?
3. Nếu process chết giữa window, lần chạy lại có thể lặp một số document không?
4. Ghi kết quả có idempotent theo `orderId`/job version không?
5. Có cần chặn cửa sổ thời gian, ví dụ chỉ quét đơn `placedAt < cutoff` để giới hạn tập dữ liệu?
6. Nếu cần snapshot nghiêm ngặt, có thể tổ chức dữ liệu/transaction/session đúng theo yêu cầu và giới hạn vận hành không?

Một job xuất dữ liệu có thể chọn `placedAt <= cutoff` để tránh nhập thêm đơn mới trong lúc đang duyệt. Nhưng cutoff **không** ngăn sửa/xóa document đã tồn tại; nếu phải xuất snapshot bất biến, cần chiến lược đồng bộ hoặc trích xuất riêng.

## 15. Offset, keyset và pagination theo bản chất MongoDB

### 15.1. Hình dạng truy vấn

**Offset:**

```javascript
db.orders.find({ customerId: "cus-01" })
  .sort({ placedAt: -1, _id: -1 })
  .skip(40000)
  .limit(20);
```

**Keyset:**

```javascript
db.orders.find({
  customerId: "cus-01",
  $or: [
    { placedAt: { $lt: ISODate("2026-11-20T02:05:00Z") } },
    {
      placedAt: ISODate("2026-11-20T02:05:00Z"),
      _id: { $lt: "ord-003" }
    }
  ]
})
.sort({ placedAt: -1, _id: -1 })
.limit(20);
```

Hai truy vấn trên là cách hình dung phép duyệt, chưa phải truy vấn tương đương vì cursor cụ thể và offset 40000 đang trỏ những vùng khác nhau. Mục đích là đối chiếu **bỏ qua N kết quả** với **lọc theo khóa tiếp tục**.

### 15.2. Tính phù hợp

| Tình huống | Thường ưu tiên | Lý do |
| --- | --- | --- |
| UI muốn nhảy trực tiếp tới trang 15 | `Pageable` offset | Số trang là hợp đồng của UI |
| Danh sách “Xem thêm” theo thời gian | Keyset scrolling | Đọc sâu với index, giảm phụ thuộc skip lớn |
| Tập dữ liệu nhỏ, prototyping | Offset scrolling | Dễ hiểu và triển khai |
| Xử lý nền quét nhiều document | Keyset với checkpoint | Có thể tiếp tục theo khóa, cần idempotency |
| Cần tổng số trang | `Page` | `Window` không có total count tự động |
| Theo dõi event mới theo thời gian thực | Change stream hoặc tailable cursor theo điều kiện | Không phải use case của `Window` |
| Cần query/aggregation nhiều bước | `MongoTemplate` hoặc aggregation chuyên dụng | Cần kiểm soát pipeline hơn derived query |

Không có lựa chọn mặc định cho mọi hệ thống. Dù dùng keyset, nếu sort/filter không có index phù hợp hoặc field sort liên tục biến đổi thì lợi ích có thể giảm hoặc hành vi khó dự đoán.

## 16. Projection, mapping và keyset: chi tiết rất dễ lỗi

### 16.1. Không bỏ khóa sort khỏi DTO

Ví dụ projection phù hợp:

```java
import java.time.Instant;

public interface OrderListView {
    String getId();
    Instant getPlacedAt();
    String getStatus();
}
```

Với keyset trên `placedAt DESC, id DESC`, projection cần trả **cả id lẫn placedAt**. Nếu dùng interface chỉ có `getStatus()`, framework không có đủ thông tin để lấy `positionAt` chính xác từ phần tử được trả.

Ngoài ra, nếu field trong BSON được lưu dưới tên khác nhờ `@Field`, phải xác minh cách ánh xạ và projection giữ đúng khóa. Nếu dùng custom converter cho thời gian hoặc ID, cần kiểm tra cả kiểu BSON và kiểu Java trong vị trí keyset.

### 16.2. Trường null/thiếu làm keyset không đáng tin cậy

Ví dụ document:

```javascript
{ _id: "ord-100", customerId: "cus-01", placedAt: null }
{ _id: "ord-101", customerId: "cus-01" }
```

MongoDB có hành vi so sánh null/thiếu khác với các giá trị Date. Spring Data không thể khôi phục điều kiện vị trí keyset một cách an toàn nếu khóa sort rỗng hoặc không tồn tại. Nên:

- Validation `placedAt` khi ghi.
- Kiểm tra dữ liệu cũ và migration trước khi dùng keyset.
- Nếu cần, chọn trường sort bắt buộc không null khác.
- Thử integration test có null/thiếu để biết hệ thống phản ứng thế nào.

### 16.3. Phân biệt ID dạng String và ObjectId

`@MongoId(FieldType.STRING)` xác định `_id` dạng BSON string. Nếu có document cũ lưu BSON ObjectId, keyset theo ID và truy vấn `_id` có thể gặp khác biệt kiểu, đặc biệt khi khôi phục cursor. Đừng đoán từ `String id` trong Java rằng toàn bộ collection lưu cùng BSON type.

Kiểm tra kiểu:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        idType: { $type: "$_id" },
        timeType: { $type: "$placedAt" }
      },
      documents: { $sum: 1 }
    }
  },
  { $sort: { documents: -1 } }
]);
```

Với dataset lớn, aggregation thống kê kiểu có thể tốn tài nguyên, cần chạy trên môi trường được phép hoặc dữ liệu sao chép có kiểm soát.

## 17. Kiểm thử integration: không bỏ sót hoặc lặp trong dữ liệu cố định

### 17.1. Tình huống kiểm thử cơ bản

Dùng database MongoDB kiểm thử thật, không chỉ mock repository. Nên tạo nhiều document có **cùng `placedAt`** để kiểm tra ID dùng làm tie-breaker.

Tập dữ liệu được giữ **không thay đổi trong suốt test**. Kỳ vọng:

1. Cửa sổ đầu chứa 2 đơn đúng thứ tự.
2. Cửa sổ hai tiếp tục **sau** đơn cuối của cửa sổ một.
3. Tập ID sau khi duyệt bằng keyset không thiếu/không trùng.
4. Offset scrolling bắt đầu bằng `ScrollPosition.offset()` cũng đọc được phần tử đầu.
5. `ScrollPosition.offset(0)` cố ý bỏ qua phần tử đầu theo semantics exclusive.
6. Cửa sổ cuối có `isLast()` đúng với tình trạng result set khi truy vấn.
7. DTO dùng keyset phải giữ đủ sort keys.
8. Sort thiếu tie-breaker hoặc field null phải được phát hiện/đưa ra quyết định trước khi triển khai.

### 17.2. Ví dụ test keyset

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

@DataMongoTest
class OrderScrollingIntegrationTest {

    @Autowired OrderRepository orders;

    @Test
    void keysetScrollVisitsEveryOrderOnceWithDuplicateTime() {
        String customer = "cus-scroll-test";
        Instant time = Instant.parse("2026-11-20T02:05:00Z");

        for (int i = 1; i <= 5; i++) {
            orders.insert(new OrderDocument(
                "scroll-" + i,
                customer,
                time,
                "PAID",
                new BigDecimal("100000")
            ));
        }

        ScrollPosition position = ScrollPosition.keyset();
        List<String> ids = new ArrayList<>();

        while (true) {
            Window<OrderDocument> window =
                orders.findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(
                    customer, position
                );

            for (OrderDocument order : window) {
                ids.add(order.id());
            }

            if (window.isEmpty() || window.isLast()) {
                break;
            }

            position = window.positionAt(window.size() - 1);
        }

        assertThat(ids)
            .containsExactly(
                "scroll-5", "scroll-4", "scroll-3",
                "scroll-2", "scroll-1"
            );
    }
}
```

Test giả định database test đã được cấu hình và ID không trùng từ lượt chạy trước. Nếu chạy nhiều lần trên cùng database, cần dọn dữ liệu tương ứng hoặc dùng namespace/ID duy nhất. Đây là mẫu test **chưa được thực thi trong dự án**; nó minh họa kiểm tra thứ tự, boundary và kết quả.

### 17.3. Test các tình huống thay đổi đồng thời

Ngoài test trên dữ liệu cố định, tạo test có thao tác:

- Chèn một đơn mới trước cursor sau khi đọc cửa sổ đầu.
- Xóa một đơn đã đọc hoặc chưa đọc.
- Sửa `placedAt` của một đơn chưa đọc, làm nó đổi vị trí.
- Kiểm tra kết quả với offset và keyset, ghi nhận khác biệt.
- Thêm document có `placedAt=null` trong một test riêng để xác định cách hệ thống ngăn chặn/đọc lỗi.

Đây không phải bài test có “một kết quả đúng tuyệt đối” cho mọi kiểu ghi đồng thời; kết quả mong đợi cần dựa vào hợp đồng sản phẩm, độ nhất quán và mô hình dữ liệu.

## 18. Chẩn đoán: query plan, tải và consistency

### 18.1. Quan sát `explain("executionStats")`

Trước khi kết luận keyset nhanh hơn, hãy kiểm tra các truy vấn tương đương trên dữ liệu đủ lớn:

```javascript
db.orders.getIndexes();

db.orders.find({ customerId: "cus-01" })
  .sort({ placedAt: -1, _id: -1 })
  .skip(10000)
  .limit(20)
  .explain("executionStats");
```

Sau đó chạy truy vấn keyset với giá trị cursor tương ứng ở gần mốc sâu tương đương. Đo:

| Chỉ số | Câu hỏi |
| --- | --- |
| `totalKeysExamined` | Có phải duyệt quá nhiều index key? |
| `totalDocsExamined` | Có đọc nhiều document thừa trước khi trả window? |
| `IXSCAN`/`COLLSCAN` | Query đang dùng index hay scan toàn bộ collection? |
| Sort stage | Có phải sort ngoài index trong bộ nhớ không? |
| Thời gian truy vấn | Có tăng mạnh khi cuộn sâu? |
| Số request cho toàn bộ lượt duyệt | Window size quá nhỏ hay quá lớn? |
| Bytes nhận và thời gian mapping | Projection có giảm dữ liệu thực sự? |
| Số bản ghi trùng/bỏ sót khi concurrent writes | Sort key và cursor contract có phù hợp? |

Một index phù hợp có thể giúp keyset duy trì chi phí gần với kích thước window trên nhiều tình huống, nhưng không nên hứa độ phức tạp hằng số cho mọi truy vấn/cluster.

### 18.2. Timeout, error và retry

Nếu truy vấn window thứ 10 thất bại:

- Không chuyển cursor sang vị trí mới trước khi xác nhận dữ liệu cửa sổ đó đã xử lý thành công theo yêu cầu.
- Với job có side effect, thao tác xử lý cần **idempotent** vì retry có thể đọc lại phần tử.
- Phân biệt timeout tạm thời với cursor token không hợp lệ hoặc dữ liệu sort sai kiểu.
- Ghi log có chọn lọc loại scroll (offset/keyset), window size, index plan và thời gian, nhưng không log token/ID nhạy cảm tùy tiện.
- Giới hạn số lượt retry và dùng backoff khi phù hợp; không tạo vòng lặp vô hạn nếu sort/keyset bị lỗi.

Trong MongoDB, transaction và read concern có thể giúp một số bài toán nhất quán nhiều thao tác, nhưng không nên tự động mở **một transaction dài bao trùm hàng triệu bản ghi** chỉ để cuộn dữ liệu. Transaction lâu tăng chi phí tài nguyên và nguy cơ xung đột, còn scrolling bản thân không mang tính giao dịch.

## 19. Những sai lầm phổ biến

**Sai lầm 1: dùng `ScrollPosition.offset(0)` để bắt đầu.** Đây là vị trí sau phần tử chỉ số 0, nên có thể bỏ qua phần tử đầu. Dùng `ScrollPosition.offset()` hoặc `OffsetScrollPosition.initial()`.

**Sai lầm 2: bỏ qua sort.** Nếu thứ tự không ổn định, vị trí giữa các lần đọc không đáng tin; keyset đòi hỏi các khóa sort rõ ràng.

**Sai lầm 3: chỉ sort `placedAt` khi nhiều đơn trùng thời điểm.** Cần một thứ tự phân biệt, ví dụ thêm ID. Spring Data cũng có cơ chế bổ sung ID để đảm bảo keyset unique.

**Sai lầm 4: keyset trên trường `null` hoặc thiếu.** Phép so sánh không thể khôi phục an toàn; cần validation/migration hoặc chọn khóa khác.

**Sai lầm 5: projection loại `id` hoặc trường sort.** Framework không thể dựng đúng vị trí keyset tiếp theo nếu kết quả không chứa khóa cần thiết.

**Sai lầm 6: gửi `ScrollPosition.toString()` ra ngoài làm cursor token.** Không có cam kết về giao thức serialization ổn định/an toàn; cần một định dạng ứng dụng được kiểm soát.

**Sai lầm 7: xem `Window<T>` như MongoDB stream mở liên tục.** Mỗi window là một nhóm kết quả, thường cần query mới để tiếp tục; nó không phải tailable/change stream.

**Sai lầm 8: nghĩ keyset cho snapshot bất biến.** Concurrent update có thể làm document dịch chuyển qua ranh giới vị trí.

**Sai lầm 9: sử dụng Scroll API trên Spring Data MongoDB 4.0 mà không kiểm tra.** Những API như `MongoTemplate.scroll(...)` được giới thiệu từ dòng 4.1; với dependency cũ phải dùng phương án tương thích.

**Sai lầm 10: truyền cursor của một bộ lọc vào bộ lọc khác.** Con trỏ chỉ có ý nghĩa cùng filter/sort/schema; mọi tham số cần được bind vào token hoặc xác minh lại.

**Sai lầm 11: dùng offset scrolling cực sâu rồi kỳ vọng query luôn rẻ.** Dù client nhận ít dữ liệu, server vẫn có thể phải skip nhiều kết quả.

**Sai lầm 12: cho client đặt window size tùy ý.** Phải giới hạn hợp lý để tránh truy vấn/tạo object quá lớn và bảo vệ tài nguyên server.

## 20. Bài thực hành và checklist trước khi triển khai

### 20.1. Bài thực hành

1. Tạo 5–10 document đơn hàng; cố ý cho 2–3 document có cùng `placedAt`.
2. Tạo `OrderRepository` có method `Window<OrderDocument> findFirst2ByCustomerIdOrderByPlacedAtDescIdDesc(..., ScrollPosition)`.
3. Đọc toàn bộ dữ liệu bằng `ScrollPosition.offset()` và quan sát vị trí mỗi cửa sổ.
4. Thử riêng `ScrollPosition.offset(0)` để giải thích hiện tượng bỏ qua phần tử đầu.
5. Đổi sang `ScrollPosition.keyset()`, so sánh kết quả và số lượt truy vấn.
6. Viết `WindowIterator` để duyệt liên tiếp mà không tự quản lý vòng lặp `isLast()`.
7. Dựng `Query` với `Sort`, `limit`, `with(position)` rồi gọi `MongoTemplate.scroll(...)`.
8. Tạo index `{customerId:1, placedAt:-1, _id:-1}`, so sánh query plan offset sâu và keyset bằng `explain`.
9. Thử projection bỏ `placedAt` để nhận diện lỗi thiếu khóa keyset; sửa DTO/projection.
10. Chèn/xóa/sửa bản ghi giữa các lần đọc và mô tả giới hạn consistency.
11. Viết integration test đảm bảo mọi ID được duyệt đúng một lần trên **dữ liệu cố định**.
12. Nếu dùng reactive, thử `ReactiveMongoTemplate.scroll(...)` và quan sát `Mono<Window<T>>`.

### 20.2. Checklist

| Kiểm tra | Câu hỏi cần trả lời |
| --- | --- |
| Phiên bản | Có `ScrollPosition`/`Window` và MongoDB `scroll` API trong dependencies thực tế không? |
| Use case | Cần đi đến trang N, tổng count, hay chỉ đọc tiếp? |
| Kiểu con trỏ | Offset hay keyset? Chi phí cuộn sâu thế nào? |
| Khởi tạo | Có dùng **initial position** chứ không nhầm `offset(0)`? |
| Sort | Sort đủ ổn định và có tie-breaker ID? |
| Field sort | Không null, không thiếu, kiểu BSON thống nhất và ít biến đổi? |
| Projection | Có trả đủ khóa sort và ID cho keyset không? |
| Index | Bộ lọc, sort và điều kiện tiếp tục có index phù hợp? |
| Cursor token | Có version, chữ ký, ràng buộc filter/tenant và thời hạn? |
| Quyền truy cập | Có xác thực và ủy quyền cho mỗi lần đọc không? |
| Concurrent writes | Có chấp nhận lặp/bỏ sót khi dữ liệu thay đổi không? |
| Job nền | Có checkpoint, retry và idempotency không? |
| Reactive | Dùng đúng `Mono<Window<T>>`/context và không block event loop? |
| Kiểm thử | Đã thử nhiều window, trùng khóa sort, null, cursor sai và dữ liệu đồng thời? |
| Hiệu năng | Đã đo `explain`, keys/docs examined, thời gian và băng thông chưa? |

**Kết luận:** `Window<T>` là đơn vị kết quả, `ScrollPosition` là điểm tiếp tục và **offset/keyset** là hai chiến lược thực thi khác nhau. Từ **Spring Data Commons 3.1 / Spring Data MongoDB 4.1**, các API scrolling giúp triển khai đọc theo cửa sổ với repository hoặc `MongoTemplate`, kể cả reactive template khi cấu hình tương thích. **Offset** đơn giản nhưng có thể đắt khi cuộn sâu; **keyset** tận dụng sort và index nhưng yêu cầu khóa không null, projection đầy đủ, con trỏ hợp lệ và phải chấp nhận giới hạn khi dữ liệu thay đổi đồng thời. Muốn hệ thống vận hành đáng tin, hãy kiểm tra phiên bản đang chạy, thiết kế index/cursor/authorization rõ ràng và kiểm thử toàn bộ quá trình tiếp tục qua nhiều cửa sổ.

