# Tạo collection có giới hạn kích thước hoặc số document

> **Module:** `SPRING_DATA_MONGODB` — Sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.
>
> **Chương:** Tailable cursor.
>
> **Trọng tâm:** thiết kế và tạo **capped collection** trong MongoDB bằng `mongosh`, `MongoTemplate` hoặc `ReactiveMongoTemplate`; hiểu chính xác vai trò của `size` và `max` để dữ liệu có thể được đọc bằng tailable cursor.

## 1. Vì sao cần một collection có giới hạn?

Giả sử hệ thống thiết bị IoT phát sinh một sự kiện trạng thái mỗi vài giây. Dịch vụ giám sát chỉ cần quan sát một cửa sổ dữ liệu gần đây để cập nhật dashboard. Nếu ghi vào collection thông thường, số bản ghi cứ tăng cho đến khi có tác vụ dọn dẹp. Nếu muốn đọc liên tục khi sự kiện mới được chèn, một **tailable cursor** phù hợp với collection được tổ chức theo thứ tự chèn.

**Capped collection** là collection có **dung lượng dữ liệu được giới hạn**. Khi không còn đủ chỗ để lưu document mới hoặc chạm ngưỡng số document đã cấu hình, MongoDB tự loại bỏ những document cũ nhất theo thứ tự tự nhiên để nhường chỗ cho document mới. Collection vì thế hoạt động giống một **vùng đệm vòng (circular buffer)**.

```text
Producer  ── insert ──> MongoDB capped collection ── tail ──> Consumer
                            │                         │
                            │                         └─ Đợi bản ghi insert mới
                            │
                   [cũ] [cũ hơn] [mới] [mới nhất]
                          │
                          └── Bị loại bỏ khi vượt ngưỡng
```

Một capped collection có hai thông số cấu hình trọng tâm:

- `size`: **bắt buộc**, dung lượng tối đa mục tiêu của phần dữ liệu collection, đơn vị **byte**.
- `max`: **tùy chọn**, số lượng document tối đa mong muốn; giới hạn này phối hợp với `size`.

**Lưu ý cốt lõi:** không thể tạo capped collection chỉ bằng một ngưỡng `max` mà bỏ qua `size`. Nếu chỉ cần giới hạn theo số document, vẫn phải cấp `size` đủ lớn để chứa số lượng đó.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt capped collection với collection thường, TTL index, time series và Change Streams.
2. Giải thích quy tắc lưu/xóa tự động dựa trên `size` và `max`, cùng hệ quả khi dung lượng hoặc số document chạm ngưỡng.
3. Tạo capped collection đúng cú pháp `db.createCollection` trong `mongosh`.
4. Tạo collection bằng `MongoTemplate` và `ReactiveMongoTemplate` với `CollectionOptions`.
5. Chọn dung lượng phù hợp dựa trên tốc độ insert, kích thước document và khoảng dữ liệu muốn giữ.
6. Kiểm tra collection thực sự đã là capped trước khi mở tailable cursor, nhất là trong môi trường nhiều instance.
7. Xây dựng ví dụ đọc liên tục bằng `Flux` và kiểm thử hành vi vòng đệm.
8. Nhận biết giới hạn về cập nhật, xóa, sharding, vận hành và xử lý chậm.

## 2. Capped collection hoạt động như thế nào?

Một collection thông thường không tự loại bỏ document cũ chỉ vì dung lượng của collection tăng. Capped collection thì có bộ nhớ dung lượng dữ liệu tối đa do bạn cấu hình khi tạo.

Giả sử collection có đủ chỗ cho ba document nhỏ. Khi chèn document thứ tư, MongoDB loại document lâu nhất để tạo chỗ:

```text
Sau insert A:   [ A ]
Sau insert B:   [ A ][ B ]
Sau insert C:   [ A ][ B ][ C ]
Sau insert D:        [ B ][ C ][ D ]  (A bị ghi đè về mặt logic)
Sau insert E:             [ C ][ D ][ E ]
```

Sơ đồ chỉ minh họa số phần tử; trên thực tế việc loại bỏ còn phụ thuộc dung lượng BSON của mỗi document và ngưỡng số document (nếu có). Không nên giả định mọi document chiếm số byte bằng nhau.

### 2.1. Hai ngưỡng `size` và `max`

| Thuộc tính | Kiểu giá trị | Bắt buộc | Vai trò |
| --- | --- | --- | --- |
| `capped` | `true` | Có | Chỉ định collection có giới hạn |
| `size` | Số nguyên dương, đơn vị **byte** | Có | Ngân sách dung lượng dữ liệu được cấp cho collection |
| `max` | Số nguyên dương | Không | Giới hạn số document; vẫn phải có `size` |
| `collation`, `validator`, ... | Tùy phiên bản MongoDB | Không | Cần đánh giá riêng nếu dùng cùng capped collection |

Quy tắc thực tế là **giới hạn nào bị chạm trước sẽ khiến document cũ được loại bỏ**. Đặt `max: 10000` không có nghĩa collection luôn giữ đủ 10.000 bản ghi. Nếu tài liệu chứa payload lớn khiến `size` bị lấp đầy trước, số document thực tế được giữ sẽ ít hơn.

Ngược lại, nếu mỗi document rất nhỏ, `max` có thể đạt trước khi dùng hết dung lượng `size`.

> `size` là giới hạn vùng lưu dữ liệu collection, **không phải số byte RAM** được MongoDB đặt trước, cũng không phải hạn mức tổng dung lượng của toàn bộ database. Tổng dung lượng thực tế trên đĩa còn phụ thuộc storage engine, index và các metadata khác. MongoDB có thể làm tròn đơn vị cấp phát tùy phiên bản.

### 2.2. Tính chất quan trọng

- **Đọc theo thứ tự tự nhiên (`$natural`):** capped collection giữ thứ tự chèn; rất phù hợp cho cursor đọc theo luồng.
- **Ghi nối đuôi bằng insert:** phù hợp với event log tạm thời, telemetry, dữ liệu quan sát gần thời gian thực.
- **Tự loại bỏ bản ghi cũ:** không cần một tác vụ `deleteMany` định kỳ để khống chế số document.
- **Không dùng xóa riêng lẻ như collection thường:** capped collection không phù hợp nghiệp vụ cần `deleteOne` hoặc `deleteMany` theo từng document; để dọn toàn bộ phải dùng thao tác quản trị như drop hoặc cơ chế phù hợp.
- **Hạn chế cập nhật làm document lớn hơn:** việc update khiến document tăng kích thước vượt chỗ đã cấp có thể bị từ chối; nên ưu tiên bản ghi bất biến (append-only).
- **Không shard capped collection** theo cách sharding collection thông thường.
- **Không có lưu giữ theo thời gian cố định:** thời gian một document tồn tại phụ thuộc tốc độ và kích thước insert mới, không phải một TTL 60 phút hay 24 giờ.
- **Không hỗ trợ bảo toàn vô hạn:** khi producer chạy nhanh hơn consumer hoặc ứng dụng dừng lâu, document chưa đọc có thể đã bị loại bỏ.

Các hạn chế cụ thể theo phiên bản MongoDB cần được đối chiếu khi nâng cấp server.

## 3. Quan hệ giữa capped collection và tailable cursor

**Tailable cursor** là cursor không đóng ngay khi đọc đến cuối một capped collection. Nó có thể tiếp tục nhận các document mới được insert khi dữ liệu xuất hiện.

Một tailable cursor:

- Đọc document theo **natural order** của capped collection.
- Thường được mở ở chế độ **awaitData** để đợi thêm bản ghi thay vì liên tục polling không cần thiết.
- Chỉ đọc các document được trả bởi truy vấn; bản thân nó không phát các sự kiện UPDATE/DELETE như MongoDB Change Streams.
- Có thể trở nên không hợp lệ khi cursor bị ngắt hoặc document ở vị trí cần đọc đã bị loại bỏ; khi đó cần chính sách mở lại và xử lý khoảng dữ liệu có thể đã mất.
- Không có **resume token** bền vững tương tự Change Streams. Không nên coi tailable cursor là hàng đợi durable với delivery guarantee.

### 3.1. Vì sao collection phải là capped?

Capped collection có tổ chức dữ liệu phù hợp với cursor kéo dài theo natural order. Một `find()` thông thường trên collection thường sẽ kết thúc khi đã trả hết tập kết quả hiện có, không giữ vai trò cursor đợi insert mới.

```text
Collection thường:
find() ──> hết dữ liệu ──> cursor kết thúc

Capped collection:
tail() ──> bản ghi đang có ──> chờ ──> insert mới ──> emit tiếp
```

Một tailable cursor có thể kết thúc sớm nếu mở trên capped collection **đang rỗng**. Vì vậy bài thực hành nên tạo một bản ghi khởi động trước khi tail, hoặc có vòng đời và cơ chế mở lại khi hoàn tất. Việc chỉ gọi `subscribe()` rồi insert ngay lập tức không chứng minh cursor đã sẵn sàng.

### 3.2. Phân biệt với Change Streams

| Tiêu chí | Tailable cursor | Change Streams |
| --- | --- | --- |
| Nguồn | Document nằm trong **capped collection** | Luồng thay đổi từ MongoDB deployment hỗ trợ |
| Collection thường | Không tail được | Có thể theo dõi thay đổi nếu topology/phiên bản phù hợp |
| Thao tác nhận được | Document có thể đọc khi insert | Các loại event như insert, update, delete, replace |
| Thứ tự | Natural order của capped collection | Thứ tự và metadata của change stream |
| Resume token | Không có | Có khi event hỗ trợ |
| Giữ lịch sử | Dựa trên `size`/`max` của capped collection | Phụ thuộc khả năng giữ lịch sử oplog và cơ chế resume |
| Thích hợp | Luồng sự kiện append-only có retention ngắn | Đồng bộ thay đổi dữ liệu và workflow phản ứng với CRUD |

**Lựa chọn:** nếu nhu cầu là “ghi event rồi nhiều người đọc liên tục trong một cửa sổ ngắn”, capped collection có thể hợp lý. Nếu cần biết document nghiệp vụ đã bị UPDATE hoặc DELETE, Change Streams phù hợp hơn.

## 4. Tạo capped collection bằng `mongosh`

### 4.1. Chỉ giới hạn dung lượng

Ví dụ tạo collection `device_events` với ngân sách dữ liệu 64 MiB:

```javascript
use telemetry_demo;

db.createCollection("device_events", {
  capped: true,
  size: 64 * 1024 * 1024
});
```

Tính toán:

```text
64 MiB = 64 × 1024 × 1024 = 67.108.864 byte
```

Ở đây MongoDB tự xác định số document còn giữ được dựa trên kích thước của từng bản ghi.

### 4.2. Giới hạn dung lượng và số document

Nếu muốn giữ nhiều nhất 100.000 document trong giới hạn 128 MiB:

```javascript
db.createCollection("app_events", {
  capped: true,
  size: 128 * 1024 * 1024,
  max: 100000
});
```

- `size`: 134.217.728 byte.
- `max`: 100.000 document.
- Nếu 128 MiB hết trước khi đủ 100.000 document, MongoDB đã phải loại document cũ.
- Nếu 100.000 document được ghi mà chưa đầy 128 MiB, số document là giới hạn có hiệu lực trước.

### 4.3. Những ví dụ cấu hình sai

**Sai: không khai báo `size`**

```javascript
// Không hợp lệ: capped collection yêu cầu size.
db.createCollection("invalid_events", {
  capped: true,
  max: 5000
});
```

**Sai về cách hiểu đơn vị:**

```javascript
// size: 1024 nghĩa là 1024 BYTE, không phải 1024 MiB.
db.createCollection("tiny_events", {
  capped: true,
  size: 1024,
  max: 10000
});
```

Tùy giới hạn kích thước tối thiểu và quy tắc cấp phát của phiên bản MongoDB, lệnh trên có thể bị từ chối hoặc tạo collection quá nhỏ để sử dụng. Trong tài liệu thực hành, hãy dùng giá trị kích thước phù hợp như 1 MiB trở lên rồi tính lại từ nhu cầu.

**Sai: tưởng gọi createCollection lần nữa sẽ đổi cấu hình:**

```javascript
db.createCollection("app_events", {
  capped: true,
  size: 256 * 1024 * 1024,
  max: 100000
});
```

Nếu `app_events` đã tồn tại, thao tác tạo lại không tự trở thành migration thay đổi `size`. Cần quy trình quản trị/migration theo phiên bản MongoDB hoặc tạo collection mới rồi chuyển consumer một cách có kiểm soát.

## 5. Kiểm tra collection sau khi tạo

Không suy luận rằng collection là capped chỉ vì nó có tên `events`, có annotation `@Document` hoặc có một index nào đó.

### 5.1. Kiểm tra nhanh bằng `isCapped()`

```javascript
use telemetry_demo;

db.device_events.isCapped();
// Kỳ vọng: true

db.app_events.isCapped();
// Kỳ vọng: true
```

Nếu kết quả là `false`, ứng dụng chưa có điều kiện để mở tailable cursor trên collection đó.

### 5.2. Kiểm tra metadata tạo collection

```javascript
db.getCollectionInfos({
  name: "app_events"
});
```

Định nghĩa hợp lệ sẽ có phần `options` thể hiện `capped`, `size` và `max` đã tạo (cách hiển thị có thể khác theo phiên bản server/shell).

Có thể đọc thống kê:

```javascript
db.app_events.stats();
```

Quan tâm đến số document, dung lượng dữ liệu đang dùng và các trường thống kê về capped collection nếu được phiên bản hỗ trợ. Đừng lấy `storageSize` hoặc `totalIndexSize` làm giá trị đúng tuyệt đối của `size` cấu hình: chúng thể hiện khía cạnh lưu trữ khác nhau.

### 5.3. Thử cơ chế loại bỏ document cũ

Tạo một collection đủ lớn tính theo byte để vài document thử nghiệm không vượt `size`, nhưng giới hạn số lượng bằng `max`:

```javascript
db.createCollection("ring_test", {
  capped: true,
  size: 1024 * 1024,
  max: 3
});

db.ring_test.insertMany([
  { _id: "A", sequence: 1 },
  { _id: "B", sequence: 2 },
  { _id: "C", sequence: 3 }
]);

db.ring_test.insertOne({ _id: "D", sequence: 4 });

db.ring_test.find({}, { _id: 1, sequence: 1 })
            .sort({ $natural: 1 })
            .toArray();
```

Với document nhỏ và không có producer khác, kết quả dự kiến theo thứ tự tự nhiên là `B`, `C`, `D`. Document `A` bị loại khi insert `D`. Đây là thử nghiệm đơn giản để xác nhận chính sách theo số document.

Không dùng phép thử này làm bằng chứng bảo đảm “giữ đúng ba document” khi thay đổi payload hoặc khi `size` có thể bị chạm trước.

## 6. Thiết kế kích thước theo tốc độ ghi

Một giá trị `size` chọn ngẫu nhiên sẽ tạo retention khó dự đoán. Trước khi tạo collection, xác định:

1. Tốc độ insert trung bình và cao điểm: `r` document/giây.
2. Kích thước trung bình và percentile cao của document BSON: `b` byte/document.
3. Thời gian cần giữ dữ liệu để các consumer chậm có thể đọc: `t` giây.
4. Biên dự phòng khi lưu lượng tăng, document biến đổi kích thước hoặc consumer tạm dừng.

Ước lượng ban đầu:

\[
\text{requiredBytes} \approx r \times b \times t \times \text{safetyFactor}
\]

Giá trị `safetyFactor` có thể bắt đầu từ 1,5–3 tùy mức biến động của dữ liệu và yêu cầu vận hành. Đây là công thức lập kế hoạch, không phải bảo đảm thời gian giữ lịch sử.

### 6.1. Ví dụ tính ngân sách một giờ

Giả sử:

- `r = 50` document/giây.
- `b = 1.200` byte/document, tính theo payload và overhead đo được.
- `t = 3.600` giây, muốn giữ khoảng một giờ dữ liệu.
- `safetyFactor = 2`.

Tính:

```text
50 × 1.200 × 3.600 = 216.000.000 byte
Thêm hệ số 2:         432.000.000 byte
432.000.000 / 1.048.576 ≈ 412 MiB
```

Một lựa chọn khởi đầu là `size: 512 * 1024 * 1024` (512 MiB). Sau đó đo retention thực tế khi chạy tải gần production.

Số document trong một giờ:

```text
50 × 3.600 = 180.000 document
```

Nếu muốn giữ khoảng một giờ, đặt `max: 100000` sẽ làm ngưỡng số document đạt trước, khiến retention chỉ vào khoảng 33 phút khi tốc độ không đổi. Trong trường hợp này, nên bỏ `max` hoặc đặt `max` lớn hơn số document kỳ vọng và tính đến cao điểm.

### 6.2. Ma trận minh họa

| Tốc độ | Kích thước bình quân | Mục tiêu giữ | Số document dự kiến | Dữ liệu thô ước tính |
| --- | --- | --- | --- | --- |
| 2/s | 512 B | 1 giờ | 7.200 | ~3,7 MB |
| 50/s | 1.200 B | 1 giờ | 180.000 | ~216 MB |
| 100/s | 2 KB | 10 phút | 60.000 | ~120 MB |
| 500/s | 1 KB | 15 phút | 450.000 | ~450 MB |

Bảng chưa tính hệ số an toàn, độ lệch kích thước, index và các khác biệt vật lý của storage engine. Phân biệt **KB/MB thập phân** (1.000) và **KiB/MiB nhị phân** (1.024) khi đưa thông số vào `size`.

### 6.3. Chi phí của index và kích thước document

Capped collection vẫn có thể có index phù hợp với các thao tác tra cứu thông thường, nhưng tailable cursor được thiết kế để đọc theo natural order và không thay thế một truy vấn sắp xếp tùy ý theo trường có index.

Nếu tài liệu quá lớn:

- Ít document nằm trong vùng capped hơn.
- Document lớn bất thường có thể làm thời gian giữ những document trước giảm mạnh.
- Xử lý/serialize đầy đủ document làm tăng lưu lượng mạng và RAM consumer.
- Khi document lớn hơn giới hạn kích thước BSON hợp lệ, insert sẽ bị MongoDB từ chối.

Đối với stream, thường chọn một schema event nhỏ, cố định, append-only; payload lớn nên được lưu ở nơi khác và event chỉ chứa tham chiếu.

## 7. Tạo capped collection bằng `MongoTemplate`

Trong Spring Data MongoDB, API tạo collection với tùy chọn là `MongoTemplate.createCollection(...)` kết hợp `CollectionOptions`.

### 7.1. Ví dụ Java đầy đủ

```java
import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class CappedCollectionSetup {

    private static final String COLLECTION = "device_events";

    private final MongoTemplate template;

    public CappedCollectionSetup(MongoTemplate template) {
        this.template = template;
    }

    public void createIfAbsent() {
        if (template.collectionExists(COLLECTION)) {
            return;
        }

        CollectionOptions options = CollectionOptions.empty()
                .capped()
                .size(64L * 1024 * 1024)
                .maxDocuments(100_000L);

        template.createCollection(COLLECTION, options);
    }
}
```

**Giải thích API:**

- `CollectionOptions.empty()` tạo đối tượng cấu hình cho collection.
- `.capped()` đánh dấu collection dạng capped.
- `.size(...)` khai báo ngân sách byte.
- `.maxDocuments(...)` chuyển thành tùy chọn tương đương `max` tại MongoDB.
- `collectionExists(...)` chỉ xác định có tên collection đó hay không.
- `createCollection(...)` là thao tác tạo schema/collection, nên được thực thi trong bootstrap hoặc migration có kiểm soát.

**Điểm bắt buộc khi triển khai thật:** nếu collection đã tồn tại nhưng **không phải capped**, `collectionExists` trả về `true` và mã trên sẽ đi qua mà không sửa loại collection. Vì vậy phải xác minh trạng thái bằng metadata và từ chối khởi động consumer nếu cấu hình không phù hợp.

### 7.2. Vì sao không tự tạo collection mỗi lần save?

Một thao tác repository như `repository.save(...)` hoặc `mongoTemplate.insert(...)` có thể làm MongoDB tự tạo **collection thường** khi chưa tồn tại. Nếu lần insert đầu tiên chạy trước bootstrap tạo capped collection, collection sẽ có hình thức không phù hợp cho tailable cursor.

Quy trình đúng:

```text
Migration / bootstrap (tạo capped collection)
                │
                ▼
Kiểm tra options: capped=true, size/max đúng dự kiến
                │
                ▼
Cho phép producer insert
                │
                ▼
Khởi động tailable consumer
```

Nên giao quyền tạo hoặc sửa schema cho tài khoản triển khai, giữ tài khoản ứng dụng ở mức quyền cần thiết để đọc/ghi. Nếu nhiều pod cùng khởi động, lệnh “check rồi create” có race condition; cần một tiến trình migration hoặc xử lý lỗi “namespace đã tồn tại” kèm bước xác minh metadata.

## 8. Tạo capped collection bằng `ReactiveMongoTemplate`

Với ứng dụng Spring WebFlux và `ReactiveMongoTemplate`, thao tác tạo collection trả về publisher và **chỉ thực thi khi có subscription**.

```java
import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;

public final class ReactiveCappedCollectionSetup {

    private static final String COLLECTION = "device_events";

    private final ReactiveMongoTemplate template;

    public ReactiveCappedCollectionSetup(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Void> createIfAbsent() {
        CollectionOptions options = CollectionOptions.empty()
                .capped()
                .size(64L * 1024 * 1024)
                .maxDocuments(100_000L);

        return template.collectionExists(COLLECTION)
                .flatMap(exists -> {
                    if (exists) {
                        return Mono.empty();
                    }

                    return template.createCollection(COLLECTION, options)
                            .then();
                });
    }
}
```

**Không viết:**

```java
// Chỉ khai báo Publisher, không kích hoạt thao tác create.
setup.createIfAbsent();
```

Đúng hơn, compose nó vào quá trình khởi động hoặc các pipeline phụ thuộc:

```java
Mono<Void> startup = setup.createIfAbsent()
        .then(checkCollectionConfiguration())
        .then(startProducerOrConsumer());
```

Ở đây `checkCollectionConfiguration()` và `startProducerOrConsumer()` là các bước ứng dụng phải cài đặt và trả về `Mono<Void>`. Chúng minh họa thứ tự bắt buộc: **tạo → xác minh → khởi động đọc/ghi**. Không tự gọi `subscribe()` rời rạc rồi giả định các bước khác đã hoàn tất.

### 8.1. Thận trọng khi nhiều instance khởi động

`collectionExists` rồi `createCollection` là quy trình gồm hai bước không nguyên tử. Hai instance có thể đồng thời thấy chưa tồn tại rồi cùng tạo.

Trong production, ưu tiên:

- Quản lý collection bằng migration/triển khai riêng trước khi tăng số replica ứng dụng.
- Nếu vẫn tạo tự động, bắt lỗi đã tồn tại chỉ sau khi xác minh schema hiện tại thực sự đúng.
- Không bắt mọi exception rồi tiếp tục như đã khởi tạo xong.
- Không tự xóa/recreate collection trong runtime để “sửa cấu hình”, vì sẽ làm mất dữ liệu và ngắt tailable cursor của những consumer khác.

## 9. Thiết kế entity cho event lưu trong capped collection

Ví dụ mô hình event nhỏ, có thời điểm tạo và nội dung để hiển thị:

```java
import java.time.Instant;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "device_events")
public record DeviceEvent(
        @Id ObjectId id,
        String deviceId,
        String type,
        String payload,
        Instant createdAt
) {}
```

Đây là record Java 17+; với Java cũ, có thể dùng POJO có constructor, getter và setter phù hợp Spring Data. `@Document` ánh xạ entity với tên collection, **không tự đảm bảo collection được tạo ở chế độ capped**.

Chèn một document:

```java
import java.time.Instant;

import reactor.core.publisher.Mono;

public Mono<DeviceEvent> append(DeviceEvent newEvent) {
    return template.insert(newEvent, "device_events");
}

DeviceEvent event = new DeviceEvent(
        null,
        "sensor-42",
        "TEMPERATURE",
        "27.5",
        Instant.now()
);
```

`template` trong ví dụ là `ReactiveMongoTemplate`. MongoDB/Spring Data sẽ ánh xạ `id` khi chèn theo quy tắc hiện hành; mã thực tế nên thiết kế ID, độ lớn payload và validation rõ ràng.

### 9.1. Nên ghi event bất biến

Với capped collection, ưu tiên thêm document mới cho mỗi sự kiện thay vì cập nhật tài liệu cũ theo một workflow:

```text
Đúng mục đích:
insert { deviceId, eventType, payload, timestamp }
insert { deviceId, eventType, payload, timestamp }
insert { deviceId, eventType, payload, timestamp }

Không phù hợp:
insert một document
update nhiều lần làm document lớn lên
delete document theo điều kiện nghiệp vụ
```

Nếu ứng dụng cần sửa/xóa linh hoạt, lịch sử lâu dài hoặc truy vấn phân tích nhiều chiều, hãy lưu dữ liệu nguồn ở collection thường/time series và dùng cơ chế phát sự kiện phù hợp.

## 10. Tạo collection xong, đọc bằng tailable `Flux`

Capped collection là **điều kiện nền tảng** cho tailable cursor. Spring Data MongoDB reactive cung cấp `ReactiveMongoTemplate.tail(...)` để chuyển dòng document đọc được thành `Flux<T>`.

### 10.1. Ví dụ đọc liên tục

```java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public final class DeviceEventTailer {

    private final ReactiveMongoTemplate template;

    public DeviceEventTailer(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<DeviceEvent> tail() {
        return template.tail(
                Query.empty(),
                DeviceEvent.class,
                "device_events"
        );
    }
}
```

- `Query.empty()` yêu cầu đọc không áp điều kiện lọc thêm.
- `DeviceEvent.class` xác định kiểu entity khi map BSON.
- `"device_events"` phải trỏ đến **capped collection thực sự tồn tại**.
- `Flux` không kết thúc theo số lượng phần tử cố định trong điều kiện stream hoạt động bình thường.
- Muốn chạy luồng, phải có subscription; một số lỗi có thể khiến publisher kết thúc và cần mở cursor mới.

### 10.2. Xử lý qua Reactor

```java
Flux<Void> handled = tailer.tail()
        .concatMap(event ->
                eventHandler.process(event)
        );
```

Giả định `eventHandler.process` trả `Mono<Void>` và hoàn thành sau side effect. `concatMap` giúp xử lý lần lượt theo thứ tự mà upstream cung cấp. Đừng dùng:

```java
// Không chờ việc xử lý async; lỗi có thể bị tách khỏi luồng chính.
tailer.tail().doOnNext(event ->
        eventHandler.process(event).subscribe()
).subscribe();
```

Khi xử lý sự kiện rất nhanh và độc lập, `flatMap` với giới hạn đồng thời có thể tăng throughput, nhưng phải tự giải quyết thứ tự hoàn thành và trạng thái xử lý.

### 10.3. Seed event và thời điểm mở cursor

Một caveat quan trọng: tailable cursor có thể đóng ngay nếu capped collection đang **rỗng lúc mở cursor**. Vì vậy bài thực hành nên insert bản ghi khởi tạo trước hoặc xây dựng cơ chế mở lại có trì hoãn.

```javascript
db.device_events.insertOne({
  deviceId: "system",
  type: "BOOTSTRAP",
  payload: "ready",
  createdAt: new Date()
});
```

Sau đó mới mở tailable cursor. Một tailable cursor mới có thể trả về những document hiện còn trong collection trước khi đợi insert mới. Consumer phải quyết định có phát lại dữ liệu cũ hay bỏ qua bằng logic nghiệp vụ.

> Nếu cần dấu mốc resume chắc chắn sau restart, tailable cursor không cung cấp resume token như Change Streams. Thiết kế consumer phải chấp nhận giới hạn retention và nguy cơ trùng/mất sự kiện hoặc dùng cơ chế bền vững hơn.

## 11. Hiểu giới hạn của `size` và `max` trong luồng thật

### 11.1. `max` không phải “xử lý tối đa bao nhiêu sự kiện”

`max: 10000` nghĩa là **số document còn lưu đồng thời** không vượt ngưỡng đó nếu `size` đủ lớn, chứ không phải producer chỉ được phép ghi 10.000 sự kiện rồi dừng. Producer tiếp tục insert; MongoDB tự loại các document cũ.

### 11.2. Dữ liệu bị loại bỏ có thể chưa được consumer đọc

Giả sử capped collection giữ 1.000 event gần nhất, producer ghi 100 event/giây, consumer ngừng 20 giây. Trong thời gian ngừng, có 2.000 event mới được chèn. Những event cũ chưa kịp đọc có thể không còn khi consumer kết nối lại.

```text
Producer:  E001 ... E1000 E1001 ... E3000
                       └──────────────┘
                       Chỉ 1000 gần nhất còn giữ

Consumer dừng từ E0900, mở lại sau 20 giây:
E0901 ... nhiều event trung gian đã bị loại
```

Vì vậy capped collection là vùng đệm hữu hạn. Nó **không thay thế** hệ thống message broker có retention/delivery guarantee phù hợp với yêu cầu không mất sự kiện.

### 11.3. Document lớn có thể làm retention giảm đột ngột

Một payload nhiều KB có thể chiếm chỗ bằng nhiều document nhỏ. Dù `max` không đổi, cửa sổ lịch sử thực tế vẫn giảm. Nên đo percentile kích thước BSON (P95/P99) và đặt hạn mức kích thước payload ngay tại producer.

### 11.4. Quan sát áp lực và backpressure

Reactor backpressure cho biết consumer muốn nhận dữ liệu ở tốc độ nào, nhưng **không ngăn producer ghi vào MongoDB**. Nếu consumer chậm kéo dài, vùng capped vẫn quay vòng. Cần cảnh báo lag và bổ sung phương án khôi phục theo yêu cầu nghiệp vụ.

## 12. So sánh capped collection, TTL và time series

| Tiêu chí | Capped collection | Collection thường + TTL index | Time series collection |
| --- | --- | --- | --- |
| Giới hạn chính | Kích thước dữ liệu và tùy chọn số document | Thời điểm hết hạn của document | Lưu dữ liệu theo thời gian, tối ưu ghi/lưu và truy vấn theo thời gian |
| Tự loại dữ liệu cũ | Có khi chạm ngưỡng | TTL monitor xóa bản ghi khi tới hạn, không tức thời tuyệt đối | Tùy chính sách expiration được hỗ trợ |
| Phù hợp tailable cursor | **Có** | Không | Không dùng như capped collection thông thường |
| Dữ liệu insert-only | Phù hợp nhất | Không bắt buộc | Phù hợp chuỗi đo đạc |
| Bảo đảm giữ đúng một giờ | Không | Gần đúng theo TTL monitor và cách cấu hình | Theo chính sách time series, không là cơ chế tailable |
| Khả năng truy vấn/lưu trữ dài hạn | Bị giới hạn bởi vòng đệm | Linh hoạt hơn | Thường phù hợp telemetry/time-based analytics |

Nếu mục tiêu là **giới hạn byte và đọc nối đuôi**, capped collection phù hợp. Nếu mục tiêu là **xóa dữ liệu sau N ngày**, TTL/time series nên được cân nhắc. Nếu phải đồng bộ CRUD trên collection nghiệp vụ, dùng Change Streams.

## 13. Thao tác tạo, chuyển đổi và migration

### 13.1. Tạo collection trước luồng ghi

Luồng chuẩn tại môi trường production:

```text
Infrastructure / migration:
  1. Chọn namespace, size và max phù hợp
  2. Tạo capped collection
  3. Xác minh capped=true, size/max đúng yêu cầu

Ứng dụng:
  4. Cho producer insert
  5. Đợi có dữ liệu hoặc xác định chiến lược cursor rỗng
  6. Mở tailable Flux và giám sát
```

Không nên để nhiều bản ứng dụng sản xuất tự thay đổi cấu trúc collection khi scale-out.

### 13.2. Collection đã tồn tại dưới dạng thường thì sao?

Không thể biến collection đang tồn tại thành capped bằng cách chỉ thêm `@Document`, gọi repository hay chạy lại `createCollection`.

MongoDB có lệnh quản trị `convertToCapped` trong các môi trường/phiên bản hỗ trợ, ví dụ:

```javascript
// CHỈ tham khảo cú pháp, cân nhắc downtime, dữ liệu và giới hạn triển khai.
db.runCommand({
  convertToCapped: "legacy_events",
  size: 128 * 1024 * 1024
});
```

Việc chuyển đổi có thể cần khóa collection, thay đổi hành vi và loại bỏ document cũ nếu không đủ chỗ. Nó không phù hợp cho migration tự động bất ngờ trong một ứng dụng đang xử lý dữ liệu quan trọng.

Một quy trình an toàn hơn trong nhiều trường hợp là tạo collection capped mới với tên khác, chuyển producer, điều chỉnh consumer, xác minh dữ liệu rồi mới loại collection cũ theo kế hoạch được phê duyệt. Cần nêu rõ mức dữ liệu lịch sử muốn mang sang.

### 13.3. Muốn thay `size` hoặc `max` sau khi tạo?

Không giả định mọi phiên bản MongoDB cho phép thay đổi `size`/`max` bằng cùng một lệnh hoặc giao diện. Một số khả năng sửa capped collection phụ thuộc phiên bản server, topology và công cụ. Đối chiếu tài liệu chính thức trước khi thay đổi môi trường production.

Khi cần thay đổi lớn về retention, ưu tiên migration có kiểm soát và đo dung lượng thực tế. Không xóa collection đang được tail để “reset” nếu chưa có kế hoạch dữ liệu và reconnect.

## 14. Kiểm thử hành vi capped collection

### 14.1. Các kiểm thử cần có

| Kịch bản | Kỳ vọng |
| --- | --- |
| Tạo collection với `capped: true` và `size` | `isCapped() == true` |
| Tạo với `size` và `max` | MongoDB nhận đúng tùy chọn |
| Insert nhiều hơn `max` document nhỏ | Document cũ nhất bị loại |
| Chèn document lớn làm đầy `size` trước `max` | Retention ít document hơn `max` |
| Mở tail trên capped collection có seed | Consumer nhận document và có thể đợi thêm |
| Mở tail trên collection thường | Truy vấn tailable không hoạt động theo thiết kế |
| Mở tail trên collection trống | Xử lý khả năng cursor đóng ngay |
| Consumer bị ngắt rồi khởi động lại | Không giả định có resume token; đánh giá duplicate/gap |
| Nhiều instance tạo cùng collection | Không bỏ qua race khi bootstrap |
| Collection có sẵn nhưng không capped | Startup từ chối hoặc có migration rõ ràng |

### 14.2. Thực hành nhanh bằng `mongosh`

```javascript
use telemetry_demo;

db.createCollection("small_buffer", {
  capped: true,
  size: 1024 * 1024,
  max: 5
});

for (let i = 1; i <= 8; i++) {
  db.small_buffer.insertOne({
    _id: i,
    event: "tick",
    createdAt: new Date()
  });
}

print("isCapped:", db.small_buffer.isCapped());
print("count:", db.small_buffer.countDocuments({}));

db.small_buffer.find({})
               .sort({ $natural: 1 })
               .toArray();
```

Với document nhỏ, kỳ vọng còn các ID từ 4 đến 8. Nếu một kết quả khác xuất hiện, cần kiểm tra kích thước thực của dữ liệu, collection có bị producer khác ghi không và thông tin metadata của collection.

### 14.3. Kiểm thử reactive bằng `StepVerifier`

Ví dụ một đoạn integration test **cần fixture đã tạo capped collection và MongoDB thật**:

```java
import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DeviceEventTailIntegrationTest {

    private final ReactiveMongoTemplate template;

    DeviceEventTailIntegrationTest(ReactiveMongoTemplate template) {
        this.template = template;
    }

    @Test
    void tailReadsNewDocumentsAfterSeed() {
        // Fixture phải tạo "device_events" là capped collection,
        // xóa dữ liệu cũ ở mức collection trước khi chạy test.
        DeviceEvent seed = new DeviceEvent(
                null, "system", "BOOTSTRAP", "ready", Instant.now());

        template.insert(seed, "device_events").block();

        Flux<DeviceEvent> stream = template.tail(
                Query.empty(), DeviceEvent.class, "device_events"
        ).take(2);

        StepVerifier.create(stream)
                .expectNextMatches(e ->
                        "BOOTSTRAP".equals(e.type()))
                .then(() -> template.insert(
                        new DeviceEvent(
                                null, "sensor-01", "TEMPERATURE",
                                "29.1", Instant.now()),
                        "device_events"
                ).block())
                .expectNextMatches(e ->
                        "TEMPERATURE".equals(e.type()))
                .verifyComplete();
    }
}
```

Đây là **khung integration test**: cần bổ sung constructor/fixture injection thực tế (`@SpringBootTest`, Testcontainers hoặc tương đương), cô lập namespace test và timeout hữu hạn. Hai lời gọi `block()` minh họa đồng bộ hóa trong **test code**; không được copy vào event-loop của ứng dụng reactive.

Sự kiện seed có vai trò bảo đảm cursor nhìn thấy ít nhất một document trước khi đợi insert mới, hạn chế race. Nếu test chạy song song với producer khác, số event và thứ tự có thể khác. Nên dùng namespace test độc lập.

### 14.4. Kiểm thử quy mô và vòng đời

Trên môi trường replica set phù hợp, chạy producer có tốc độ biến động, giả lập consumer tạm dừng:

1. Tạo capped collection theo `size` đã tính.
2. Insert dữ liệu thử với phân bố kích thước giống production.
3. Theo dõi số document còn giữ và khoảng thời gian giữa document mới nhất/cũ nhất.
4. Đặt consumer chậm hơn producer, quan sát tình trạng lag và các lần cursor chết.
5. Khởi động lại consumer và xác nhận chính sách nghiệp vụ khi event đã mất.
6. Đo ảnh hưởng của nhiều subscriber cùng tail một collection.
7. Sau thử nghiệm, chỉ dọn namespace test thuộc quyền của mình.

Đừng xem `StepVerifier.withVirtualTime` là thay thế cho MongoDB thật trong kiểm thử storage rotation, khóa collection hay tương tác driver.

## 15. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách chẩn đoán |
| --- | --- | --- |
| `cannot use tailable cursor on a non-capped collection` | Collection tồn tại nhưng không capped | `db.collection.isCapped()`; kiểm tra thứ tự bootstrap |
| Lỗi khi tạo collection | Thiếu `size`, giá trị không hợp lệ, thiếu quyền hoặc trùng tên | Kiểm tra `createCollection` và lỗi MongoDB |
| `collectionExists` trả true nhưng tail vẫn lỗi | Collection thường được tạo trước bởi insert tự động | Đọc metadata, áp dụng migration có kiểm soát |
| Collection giữ ít document hơn `max` | `size` chạm trước | Đo BSON size và tốc độ insert |
| Không giữ dữ liệu đủ thời gian mong muốn | Lưu lượng tăng, document lớn, `max` nhỏ | Tính lại sizing và quan sát retention thực tế |
| Tail không nhận event mới | Flux chưa subscribe, cursor đóng hoặc collection trống khi mở | Kiểm tra subscription, seed event và lifecycle |
| Tail phát document cũ | Cursor mới đọc những document hiện còn từ natural order | Thiết kế lọc/dedup theo yêu cầu |
| Consumer bỏ lỡ event sau restart | Document đã bị rotation; không có resume token | Tăng dung lượng/đổi kiến trúc nếu không được mất dữ liệu |
| `update` / `delete` bị từ chối | Hạn chế của capped collection | Dùng append-only hoặc collection thường |
| Sắp xếp theo trường ứng dụng khác natural order | Trộn use case query thông thường và tailable | Dùng natural order cho tail; tách projection khi cần sort khác |
| Nhiều pod cùng tạo collection | Race giữa exists và create | Migration singleton, xác minh metadata sau lỗi namespace exists |
| CPU/memory tăng | Consumer chậm, buffer không giới hạn hoặc payload lớn | Giới hạn concurrency, batch size và đo lag |

## 16. Checklist triển khai

- [ ] Chọn use case phù hợp với **vùng đệm append-only có retention hữu hạn**.
- [ ] Xác định tốc độ insert, kích thước BSON, thời gian cần giữ và hệ số dự phòng.
- [ ] Khai báo `capped: true` và `size` bằng byte; thêm `max` nếu thực sự cần.
- [ ] Đảm bảo `size` đủ chứa số document mục tiêu khi dùng `max`.
- [ ] Tạo collection trong migration/bootstrap **trước** khi producer ghi dữ liệu đầu tiên.
- [ ] Xác minh `isCapped() == true` và metadata `size/max` thực tế.
- [ ] Dùng `MongoTemplate`/`ReactiveMongoTemplate` với `CollectionOptions` nếu quản lý bằng Java.
- [ ] Đảm bảo reactive create operation được subscribe/chaining đúng, không bỏ quên publisher.
- [ ] Đảm bảo tailable cursor được mở trên capped collection và xử lý trường hợp collection rỗng.
- [ ] Không dựa vào một tailable cursor để bảo đảm phát lại mọi event sau downtime dài.
- [ ] Giám sát write rate, document size, retention thực tế, lag và vòng đời subscription.
- [ ] Có kế hoạch migration khi muốn đổi kích thước hay loại collection.

## 17. Bài tập tự luyện

**Bài 1 — So sánh giới hạn.** Tạo ba collection: (A) `size` 1 MiB; (B) `size` 1 MiB và `max` 50; (C) `size` 4 MiB và `max` 50. Chèn 200 document cùng kích thước, dự đoán collection nào giữ nhiều dữ liệu nhất. Sau đó thay đổi kích thước payload để kiểm tra nhận định.

**Bài 2 — Sizing.** Một dịch vụ ghi 75 event/giây, trung bình 1.600 byte/event, muốn giữ 30 phút, hệ số an toàn 2. Tính `size` đề xuất và số document tối thiểu để `max` không rút ngắn retention. Nêu rõ cách chuyển đổi giữa MB và MiB.

**Bài 3 — Bootstrap.** Viết migration tạo `audit_tail` bằng `MongoTemplate`. Nếu collection có sẵn nhưng không capped, migration phải báo lỗi có chỉ dẫn thay vì lặng lẽ trả về thành công.

**Bài 4 — Reactive setup.** Viết `Mono<Void> initialize()` tạo capped collection nếu chưa có, xác minh metadata, sau đó mới cho `tail` chạy. Giải thích tại sao lệnh `initialize()` không được subscribe thì không có tác dụng.

**Bài 5 — Behavior.** Tạo `ring_test` có `max: 3` và document nhỏ. Chèn A, B, C, D; mô tả chính xác document nào được giữ. Thử tăng payload để xem ngưỡng `size` thay đổi kết quả thế nào.

**Bài 6 — Stream.** Tạo `DeviceEventTailer`, insert seed, mở `tail()` rồi insert 10 bản ghi. Dùng `StepVerifier` hoặc một test subscriber có timeout để chứng minh các event mới được nhận theo thứ tự natural.

**Bài 7 — Giới hạn hệ thống.** Giả định collection chứa tối đa khoảng 20.000 event, producer phát 500 event/giây còn consumer dừng hai phút. Tính số event sản sinh trong thời gian dừng và giải thích tại sao capped collection không thể đảm bảo xử lý mọi event.

**Bài 8 — Kiến trúc.** So sánh cách dùng capped collection + tailable cursor với Change Streams và một message broker có lưu offset. Đề xuất cơ chế cho dashboard theo dõi gần thời gian thực và cơ chế cho luồng thanh toán không được bỏ sót event.

## 18. Tài liệu chính thức và điểm cần đối chiếu

1. [MongoDB Manual — Capped Collections](https://www.mongodb.com/docs/manual/core/capped-collections/): tính chất lưu trữ, giới hạn update/delete, tailable cursor và các yêu cầu liên quan.
2. [MongoDB Manual — db.createCollection](https://www.mongodb.com/docs/manual/reference/method/db.createCollection/): định dạng `capped`, `size` và `max` khi tạo collection.
3. [MongoDB Manual — Tailable Cursors](https://www.mongodb.com/docs/manual/core/tailable-cursors/): vòng đời cursor, natural order và hành vi khi collection rỗng.
4. [Spring Data MongoDB — Tailable Cursors](https://docs.spring.io/spring-data/mongodb/reference/mongodb/tailable-cursors.html): `ReactiveMongoTemplate.tail` và cách dùng với capped collection.
5. [Spring Data MongoDB — CollectionOptions API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/CollectionOptions.html): cấu hình capped/size/maxDocuments theo phiên bản.
6. [Spring Data MongoDB — MongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): `createCollection` và `collectionExists`.
7. [Spring Data MongoDB — ReactiveMongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): tạo collection và tail theo Reactor.

Các giới hạn về thao tác collection, driver và cú pháp migration có thể thay đổi theo phiên bản MongoDB và Spring Data. Khi triển khai, đối chiếu đúng bộ phiên bản đang vận hành và kiểm chứng hành vi trên môi trường giống production.

**Kết quả mong đợi:** bạn phải tạo được một capped collection có `size` bắt buộc, biết khi nào cần `max`, chứng minh collection tự loại document cũ, dùng `MongoTemplate` hoặc `ReactiveMongoTemplate` để tạo/kiểm tra cấu hình, và mở được `Flux` từ `tail(...)` trên collection đó.
