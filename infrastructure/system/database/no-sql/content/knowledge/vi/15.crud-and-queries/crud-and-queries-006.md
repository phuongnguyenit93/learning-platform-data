# Truy vấn theo khoảng, tiền tố và thứ tự sắp xếp

Trong một ứng dụng NoSQL, yêu cầu “lấy 20 đơn hàng mới nhất có mã bắt đầu bằng `ORD-2026-` và tổng tiền trong một khoảng” là tổ hợp của ba vấn đề: **lọc theo khoảng (range)**, **tìm theo tiền tố (prefix)** và **xác định thứ tự sắp xếp (sort)**. Cú pháp tương đối ngắn, nhưng tính đúng đắn phụ thuộc kiểu dữ liệu, biên so sánh, collation, index và cách phân trang.

MongoDB cho phép filter trên nhiều field và tạo compound index. DynamoDB đặt trọng tâm vào partition key/sort key; Cassandra dùng partition key và clustering key. Cùng một câu hỏi nghiệp vụ có thể cần **mô hình dữ liệu khác nhau** trên từng hệ.

Bài học này sử dụng MongoDB/mongosh để minh họa chính và so sánh với DynamoDB, Cassandra. Các ví dụ kỹ thuật giả định môi trường thử nghiệm và schema đã được chuẩn hóa; những bảo đảm chính xác phụ thuộc phiên bản, topology và cấu hình hệ quản trị.

## 1. Bộ dữ liệu ví dụ

Giả sử collection `orders` trong hệ thống đa tenant:

~~~javascript
db.orders.insertMany([
  {
    _id: "ord-101",
    tenantId: "shop-17",
    orderCodeKey: "ORD-2026-0001",
    status: "CONFIRMED",
    totalMinor: NumberLong("250000"),
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: "ord-102",
    tenantId: "shop-17",
    orderCodeKey: "ORD-2026-0002",
    status: "PENDING",
    totalMinor: NumberLong("450000"),
    createdAt: ISODate("2026-11-02T09:30:00Z")
  },
  {
    _id: "ord-103",
    tenantId: "shop-17",
    orderCodeKey: "ORD-2026-0003",
    status: "CONFIRMED",
    totalMinor: NumberLong("150000"),
    createdAt: ISODate("2026-11-02T09:30:00Z")
  },
  {
    _id: "ord-104",
    tenantId: "shop-17",
    orderCodeKey: "ORD-2025-0199",
    status: "CANCELLED",
    totalMinor: NumberLong("900000"),
    createdAt: ISODate("2026-11-04T10:00:00Z")
  },
  {
    _id: "ord-105",
    tenantId: "shop-42",
    orderCodeKey: "ORD-2026-0001",
    status: "CONFIRMED",
    totalMinor: NumberLong("300000"),
    createdAt: ISODate("2026-11-03T11:00:00Z")
  },
  {
    _id: "ord-106",
    tenantId: "shop-17",
    orderCodeKey: "ORD-2026-0004",
    status: "CONFIRMED",
    totalMinor: NumberLong("600000"),
    createdAt: ISODate("2026-11-05T08:00:00Z")
  }
]);
~~~

Các field có vai trò:

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `_id` | string | ID kỹ thuật bất biến, duy nhất trong collection |
| `tenantId` | string | Phạm vi dữ liệu và quyền truy cập |
| `orderCodeKey` | string | Mã đã chuẩn hóa phục vụ so sánh và tìm tiền tố |
| `status` | string enum | Trạng thái nghiệp vụ |
| `totalMinor` | BSON Int64 | Tổng tiền theo đơn vị nhỏ nhất đã quy ước |
| `createdAt` | BSON Date | Thời điểm tạo, lưu theo UTC |

Có hai đơn ở `shop-17` cùng `createdAt = 2026-11-02T09:30:00Z`. Chi tiết này giúp thấy tại sao cần **khóa phá hòa** khi sort và phân trang.

## 2. Khoảng và toán tử so sánh

MongoDB có các toán tử:

| Toán tử | Ý nghĩa | Biên |
|---|---|---|
| `$gt` | Lớn hơn | Không gồm cận |
| `$gte` | Lớn hơn hoặc bằng | Gồm cận |
| `$lt` | Nhỏ hơn | Không gồm cận |
| `$lte` | Nhỏ hơn hoặc bằng | Gồm cận |
| `$eq` | Bằng | Một giá trị |
| `$ne` | Khác | Cần chú ý missing field |

Ví dụ tổng tiền từ **200.000 (bao gồm) đến dưới 500.000**:

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  totalMinor: {
    $gte: NumberLong("200000"),
    $lt: NumberLong("500000")
  }
});
~~~

Trong dữ liệu mẫu, `ord-101` và `ord-102` thỏa điều kiện. `ord-105` có 300.000 nhưng ở tenant khác; không được trả về.

### Viết rõ loại khoảng

Trong ký hiệu toán học:

- `[a,b]`: gồm cả hai cận.
- `(a,b)`: không gồm hai cận.
- `[a,b)`: gồm cận đầu, loại cận cuối.
- `(a,b]`: loại cận đầu, gồm cận cuối.

Tương ứng:

~~~javascript
// Khoảng đóng [a,b]
{ value: { $gte: a, $lte: b } }

// Khoảng mở (a,b)
{ value: { $gt: a, $lt: b } }

// Khoảng nửa kín [a,b)
{ value: { $gte: a, $lt: b } }

// Khoảng nửa kín (a,b]
{ value: { $gt: a, $lte: b } }
~~~

API phải quy định rõ cận nào được bao gồm. Nếu người dùng nhập `minPrice > maxPrice`, nên báo lỗi hợp đồng hoặc xử lý theo một chính sách đã công bố, không tự ý tạo ra kết quả khó đoán.

## 3. Khoảng thời gian: nên dùng `[start, end)`

Tìm đơn được tạo trong ngày 02/11/2026 **theo UTC**:

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  createdAt: {
    $gte: ISODate("2026-11-02T00:00:00Z"),
    $lt: ISODate("2026-11-03T00:00:00Z")
  }
});
~~~

Dùng đầu ngày kế tiếp làm cận trên tốt hơn cách ghi `23:59:59`, vì timestamp có thể chứa mili giây hoặc độ chính xác khác. Hai khoảng ngày liên tiếp không bị chồng lấn:

~~~text
Ngày 02: [2026-11-02T00:00Z, 2026-11-03T00:00Z)
Ngày 03: [2026-11-03T00:00Z, 2026-11-04T00:00Z)
~~~

Thời điểm đúng 00:00 ngày 03 chỉ thuộc khoảng ngày 03.

### Ngày kinh doanh và múi giờ

“Ngày 02/11 ở Việt Nam” không phải khoảng UTC từ 00:00 đến 00:00 ngày tiếp theo. Với múi giờ `Asia/Ho_Chi_Minh` (UTC+07 trong ngày ví dụ), ngày 02/11/2026 tương ứng:

~~~javascript
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-11-01T17:00:00Z"),
    $lt: ISODate("2026-11-02T17:00:00Z")
  }
});
~~~

Ứng dụng nên dùng thư viện ngày giờ có timezone database để tính hai đầu ngày **ở múi giờ nghiệp vụ**, rồi chuyển sang UTC. Đối với múi giờ có daylight saving, một ngày lịch có thể dài 23 hoặc 25 giờ: cộng cứng 24 giờ vào mốc UTC không luôn đúng.

Cần phân biệt `createdAt`, `paidAt`, `fulfilledAt`, `eventTime` và `ingestedAt`; mỗi trường trả lời một câu hỏi thời gian khác nhau.

## 4. Kiểu dữ liệu là một phần của điều kiện khoảng

Ba giá trị nhìn giống nhau:

~~~javascript
{ totalMinor: NumberLong("100000") }
{ totalMinor: "100000" }
{ totalMinor: 100000 }
~~~

nhưng không có cùng BSON type. String không tự được coi là số nguyên khi lọc và sort; MongoDB có quy tắc so sánh theo loại BSON và type bracketing.

Nếu một số record lưu tiền thành chuỗi, query số có thể không cho kết quả mong muốn. Contract phải chọn kiểu ổn định, ví dụ BSON Int64 cho `totalMinor`, và có migration cho legacy data.

### Khoảng số và currency

Không so sánh `100 USD` và `100 VND` chỉ bằng trường amount. Nếu một collection có nhiều loại tiền, cần lọc currency hoặc quy đổi theo quy tắc nghiệp vụ có thời điểm tỷ giá rõ ràng.

### Null và missing

Document thiếu `totalMinor` không tương đương document có `totalMinor: null` hoặc `totalMinor: 0`. Không tự ép missing thành 0 trừ khi hợp đồng quy định. Với dữ liệu cần tính tiền, validation thường nên yêu cầu có field đúng kiểu.

## 5. Truy vấn khoảng trên chuỗi không phải so sánh số học

Giả sử mã:

~~~text
INV-2
INV-10
INV-100
INV-9
~~~

Sort chuỗi theo thứ tự lexicographic có thể đưa `INV-10` trước `INV-2`. Nếu muốn thứ tự tăng theo con số:

- Lưu `sequenceNumber` kiểu số; hoặc
- Zero-pad số đến độ rộng cố định: `INV-0002`, `INV-0010`; hoặc
- Chọn collation có numeric ordering nếu engine/query/index đáp ứng.

Đừng cho rằng giá trị “trông giống số” tự được sort như số.

## 6. Truy vấn tiền tố có những nghĩa khác nhau

“Prefix search” có thể chỉ:

1. Toàn field **bắt đầu** bằng một chuỗi: `ORD-2026-0001` bắt đầu bằng `ORD-2026-`.
2. Một **token/từ** trong văn bản bắt đầu bằng chuỗi: autocomplete theo từ; có thể cần search index.
3. Một **sort key tổng hợp** bắt đầu bằng thành phần như `ORDER#2026#`.
4. Tìm chuỗi **xuất hiện bất kỳ đâu**: đây là substring/contains, không phải prefix.

Ví dụ:

~~~text
Prefix = "ORD-2026-"

Khớp:
  ORD-2026-0001
  ORD-2026-0002

Không khớp:
  ORD-2025-0199
  X-ORD-2026-0001
~~~

Cần xác định rõ ý nghĩa trong API trước khi chọn operator và index.

## 7. MongoDB: regex neo tại đầu chuỗi

Một cách tìm prefix:

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  orderCodeKey: { $regex: "^ORD-2026-" }
});
~~~

Dấu `^` chỉ **đầu chuỗi**. Regex không có neo:

~~~javascript
{ orderCodeKey: { $regex: "ORD-2026-" } }
~~~

có thể khớp một chuỗi chứa `ORD-2026-` ở giữa, sai yêu cầu prefix.

### Regex và B-tree index

Với regex case-sensitive có neo ở đầu và phần đầu là literal prefix đơn giản, MongoDB có thể tận dụng index phù hợp để giới hạn vùng tìm kiếm. Tuy nhiên, hiệu quả phụ thuộc:

- Regex có thực sự là literal prefix hay chứa pattern rộng.
- Collation và cấu trúc index.
- Độ chọn lọc prefix.
- Các field equality khác như `tenantId`.
- Số kết quả và sort yêu cầu.

Ví dụ so sánh:

| Regex | Ý nghĩa | Ghi chú |
|---|---|---|
| `^ORD-2026-` | Bắt đầu bằng literal prefix | Có thể tận dụng index |
| `ORD-2026-` | Chứa ở bất kỳ đâu | Không còn là prefix |
| `.*2026` | Có bất kỳ phần trước 2026 | Thường khó tận dụng prefix index |
| `^ORD-.*A` | Prefix ngắn rồi pattern rộng | Có thể quét nhiều candidate |
| `^ord-` với `i` | Case-insensitive | Không tự tương đương index phù hợp |

**Không nên đoán index được dùng; hãy xem `explain` trên dữ liệu thật.**

## 8. Chuẩn hóa mã để prefix nhất quán

Nếu producer lưu `ord-2026-0001`, `ORD-2026-0001` và ` Ord-2026-0001 ` tùy tiện, một regex case-sensitive trên giá trị thô sẽ bỏ sót hoặc trả kết quả không đồng nhất.

Một thiết kế có thể lưu:

~~~javascript
{
  orderCode: "ord-2026-0001",
  orderCodeKey: "ORD-2026-0001"
}
~~~

`orderCode` phục vụ hiển thị; `orderCodeKey` được chuẩn hóa cho tìm kiếm/unique. Hợp đồng normalization cần mô tả:

- Trim hay giữ khoảng trắng đầu/cuối?
- Case folding/uppercase theo locale nào?
- Cho phép ký tự Unicode và dấu không?
- Dấu gạch nối hoặc khoảng trắng có được xem như tương đương không?
- Thuật toán đổi version thì dữ liệu cũ được xử lý ra sao?

Không dùng quy tắc của SKU ASCII cho tên người, địa chỉ email hoặc từ ngữ tiếng Việt một cách máy móc.

## 9. Escape regex literal từ input

Nếu client nhập prefix `AB.12`, dấu `.` trong regex có nghĩa ký tự bất kỳ. Query `^AB.12` có thể khớp cả `ABX12`. Đó không phải yêu cầu literal prefix.

Cần escape các metacharacter trước khi dùng regex.

Ví dụ ý tưởng trong Java:

~~~java
import java.util.regex.Pattern;
import org.bson.Document;

public Document buildPrefixFilter(String prefixKey) {
    if (prefixKey == null || prefixKey.isBlank() ||
        prefixKey.length() > 40) {
        throw new IllegalArgumentException("Invalid prefix");
    }

    return new Document("orderCodeKey",
        new Document("$regex", "^" + Pattern.quote(prefixKey)));
}
~~~

Cần kiểm tra cách driver/server diễn giải regex escape của stack cụ thể. Nếu business key chỉ gồm `A-Z`, `0-9` và `-`, validate whitelist có thể giúp đơn giản hóa. Không cho client cung cấp regex tùy ý khi API chỉ cam kết prefix.

Ngoài escape, cần giới hạn prefix length, page size, timeout của query và field/operator được phép. **Escape không thay thế bảo vệ tài nguyên hoặc tenant authorization.**

## 10. Prefix bằng khoảng chuỗi: chỉ dùng khi biết thứ tự so sánh

Với một alphabet ASCII có thứ tự được kiểm soát, có thể chuyển prefix thành khoảng lexicographic.

Ví dụ prefix `ORD-2026-`:

~~~text
Lower inclusive: "ORD-2026-"
Upper exclusive: "ORD-2026."
~~~

Dấu `.` đứng ngay sau dấu `-` trong thứ tự ASCII, nên dưới một thứ tự binary/simple phù hợp, những chuỗi bắt đầu bằng `ORD-2026-` nằm trong khoảng này.

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  orderCodeKey: {
    $gte: "ORD-2026-",
    $lt: "ORD-2026."
  }
});
~~~

**Đây là ví dụ có điều kiện**, không phải thuật toán cận trên cho mọi prefix. Muốn dùng rộng rãi phải xác định:

1. Collation và kiểu BSON được sử dụng.
2. Alphabet được phép.
3. Cách tạo upper bound kế tiếp prefix.
4. Trường hợp ký tự cuối đạt giá trị lớn nhất.
5. Unicode normalization và cách so sánh code point/byte.
6. Kết quả có chính xác khi query và index dùng collation khác không.

Không tự “tăng ký tự cuối lên 1” cho mọi Unicode hoặc ngôn ngữ. Với yêu cầu phức tạp, anchored literal regex hoặc search index chuyên dụng có thể an toàn và dễ hiểu hơn.

## 11. Collation của chuỗi

Collation quyết định cách so sánh/sort chuỗi trong các ngữ cảnh engine hỗ trợ. Đối với tên người, cần quy tắc ngôn ngữ; đối với business key chuẩn hóa, thường muốn thứ tự ổn định theo một quy ước đơn giản.

Ví dụ sort tên hiển thị:

~~~javascript
db.customers.find({
  tenantId: "shop-17"
})
.sort({ displayName: 1, _id: 1 })
.collation({ locale: "vi", strength: 2 });
~~~

Index phục vụ sort theo collation cần tương thích với collation query. **Regex trong MongoDB không phải công cụ collation-aware theo cùng cách với phép so sánh thông thường**; một case-insensitive index không mặc nhiên làm regex có cờ `i` nhanh. Với mã nghiệp vụ, field key chuẩn hóa dễ kiểm soát hơn.

Collation có thể ảnh hưởng dấu, chữ hoa/thường và numeric ordering. Nó là **một phần của hợp đồng truy vấn**, không chỉ cài đặt hiển thị.

## 12. Sort trong MongoDB

Đơn mới nhất trước:

~~~javascript
db.orders.find({
  tenantId: "shop-17"
})
.sort({ createdAt: -1 })
.limit(20);
~~~

Trong `sort`:

- `1`: tăng dần.
- `-1`: giảm dần.

Nhưng `createdAt` có thể trùng; hai Order có cùng timestamp không được bảo đảm thứ tự tương đối khi chỉ sort theo thời gian.

### Khóa phá hòa tạo thứ tự đầy đủ

~~~javascript
db.orders.find({
  tenantId: "shop-17"
})
.sort({
  createdAt: -1,
  _id: -1
})
.limit(20);
~~~

Khi timestamp bằng nhau, `_id` quyết định thứ tự. Dữ liệu mẫu có `ord-102` và `ord-103` cùng thời gian: theo `_id` giảm dần, `ord-103` đứng trước `ord-102`.

Khóa phá hòa nên ổn định và duy nhất trong tập kết quả. Thứ tự xác định giúp tránh bỏ sót/trùng lặp do timestamp bằng nhau trong phân trang.

## 13. Sort theo thứ tự nghiệp vụ khác sort theo chữ cái

Giả sử muốn hiển thị trạng thái:

~~~text
PENDING -> CONFIRMED -> CANCELLED
~~~

Sort `status: 1` sẽ theo thứ tự so sánh string/collation, không theo độ ưu tiên nghiệp vụ. Có thể:

- Lưu một trường `statusPriority` với mapping có contract.
- Dùng aggregation tạo priority theo `status`.
- Tạo read model phục vụ màn hình riêng nếu dùng thường xuyên.

Nếu lưu priority dẫn xuất, phải đồng bộ khi status đổi. Không nên âm thầm dựa vào thứ tự chữ cái của enum code.

## 14. Sort theo field mảng không tự chọn phần tử đã lọc

Ví dụ:

~~~javascript
{
  variants: [
    { color: "red", priceMinor: 200000 },
    { color: "blue", priceMinor: 900000 }
  ]
}
~~~

Một query lọc `"variants.color": "blue"` rồi sort `"variants.priceMinor": 1` không nhất thiết sort theo giá của **biến thể xanh**. Engine có quy tắc chọn giá trị mảng cho sort tùy hướng, và phần tử tham gia sort có thể không là phần tử khớp filter.

Nếu yêu cầu “giá thấp nhất của biến thể xanh”, phải tính scalar đúng từ **tập biến thể xanh** bằng aggregation hoặc duy trì field tổng hợp có ý nghĩa. Không suy ra sự gắn cặp phần tử chỉ từ hai dot paths.

## 15. Khoảng trên mảng và `$elemMatch`

Cho document:

~~~javascript
{
  _id: "prod-1",
  scores: [1, 10]
}
~~~

Yêu cầu “mảng có **một phần tử** trong khoảng từ 4 đến 7”.

Truy vấn đơn thuần:

~~~javascript
db.products.find({
  scores: { $gte: 4, $lte: 7 }
});
~~~

có thể khớp nhờ các phần tử khác nhau thỏa từng cận. Để buộc cùng phần tử:

~~~javascript
db.products.find({
  scores: {
    $elemMatch: {
      $gte: 4,
      $lte: 7
    }
  }
});
~~~

`[1,10]` không có phần tử trong khoảng 4–7, nên không khớp `$elemMatch`.

### Mảng object

~~~javascript
{
  offers: [
    { region: "HN", priceMinor: 300000 },
    { region: "HCM", priceMinor: 900000 }
  ]
}
~~~

Yêu cầu “có offer của HCM giá dưới 500.000”:

~~~javascript
db.products.find({
  offers: {
    $elemMatch: {
      region: "HCM",
      priceMinor: { $lt: 500000 }
    }
  }
});
~~~

Dùng hai điều kiện dot path riêng có thể khớp bởi hai object khác nhau. `$elemMatch` diễn đạt chính xác **cùng một phần tử của mảng**.

## 16. Kết hợp filter, sort, projection và limit

~~~javascript
db.orders.find(
  {
    tenantId: "shop-17",
    status: "CONFIRMED",
    createdAt: {
      $gte: ISODate("2026-11-01T00:00:00Z"),
      $lt: ISODate("2026-12-01T00:00:00Z")
    }
  },
  {
    _id: 1,
    orderCodeKey: 1,
    totalMinor: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Ý nghĩa từng phần:

1. `find` filter chọn document đúng điều kiện.
2. Projection giới hạn field trả về.
3. `sort` xác định thứ tự.
4. `limit` giới hạn số document trong response.

`limit(20)` không bảo đảm database chỉ đọc 20 document. Nếu index không phù hợp, engine có thể phải quét và sort nhiều candidate trước khi tìm top 20.

Projection cũng không thay thế kiểm tra quyền: chỉ hiển thị ít field không có nghĩa người dùng được phép truy cập tài nguyên đó.

## 17. Một truy vấn kết hợp cả ba nhu cầu

Yêu cầu:

> Lấy các đơn CONFIRMED của shop-17 có mã bắt đầu bằng ORD-2026-, tạo từ 01/11 đến trước 06/11/2026, mới nhất trước, tối đa 20 đơn.

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  status: "CONFIRMED",
  orderCodeKey: { $regex: "^ORD-2026-" },
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-11-06T00:00:00Z")
  }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Từng phần có hợp đồng riêng:

- Tenant là điều kiện bảo mật.
- Status là enum nghiệp vụ.
- Prefix là chuỗi literal đã chuẩn hóa.
- Khoảng thời gian là UTC, nửa kín.
- Sort có ID phá hòa.
- Limit là giới hạn page size.

Truy vấn có **nhiều điều kiện range-like**: prefix và createdAt range, nên không một index ngẫu nhiên nào chắc chắn tối ưu cả filter và sort.

## 18. Compound index và thứ tự trường

Nếu thường xuyên truy vấn đơn của tenant theo thời gian:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: -1,
  _id: -1
});
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "shop-17"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

có thể tận dụng thứ tự index trong điều kiện phù hợp.

Thứ tự field trong compound index rất quan trọng:

~~~javascript
// Index A
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }

// Index B
{ createdAt: -1, tenantId: 1, status: 1, _id: -1 }
~~~

Hai index chứa cùng field nhưng không có cùng khả năng lọc/sort. Index A thường phù hợp hơn khi query có equality `tenantId`, `status` rồi sort theo thời gian.

## 19. ESR: Equality, Sort, Range

Một heuristic hữu ích khi thiết kế compound index MongoDB:

1. **Equality:** các field so sánh bằng, ví dụ `tenantId`, `status`.
2. **Sort:** các field tạo thứ tự, ví dụ `createdAt`, `_id`.
3. **Range:** các field giới hạn khoảng, ví dụ `totalMinor`.

Ví dụ index:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1,
  totalMinor: 1
});
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  status: "CONFIRMED",
  totalMinor: {
    $gte: NumberLong("200000"),
    $lt: NumberLong("700000")
  }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Index theo ESR có thể giúp lấy dữ liệu theo sort order mà không cần sort riêng lớn. Tuy nhiên, nếu khoảng `totalMinor` rất chọn lọc, đặt range sớm hơn có thể giảm số entry cần xét.

Một index thay thế:

~~~javascript
{
  tenantId: 1,
  status: 1,
  totalMinor: 1,
  createdAt: -1,
  _id: -1
}
~~~

có thể lọc range tốt hơn nhưng không nhất thiết cung cấp thứ tự `createdAt` trực tiếp trên **toàn bộ khoảng totalMinor**. Đây là đánh đổi giữa **tập candidate** và **chi phí sort**.

**ESR là quy tắc kinh nghiệm, không phải bảo đảm tối ưu**. Cần đo bằng query plan và workload.

## 20. Prefix và sort có thể cạnh tranh trên cùng index

Hai ứng viên:

~~~javascript
// Tập trung vào prefix
db.orders.createIndex({
  tenantId: 1,
  orderCodeKey: 1,
  createdAt: -1,
  _id: -1
});

// Tập trung vào thời gian
db.orders.createIndex({
  tenantId: 1,
  createdAt: -1,
  _id: -1,
  orderCodeKey: 1
});
~~~

Với prefix có nhiều giá trị `orderCodeKey` khác nhau, index thứ nhất không nhất thiết cung cấp trực tiếp thứ tự `createdAt` toàn cục. Index thứ hai thuận sort thời gian nhưng có thể phải xét nhiều candidate mới lọc hết prefix.

Cần biết:

- Prefix dài hay ngắn?
- Khoảng ngày hẹp hay rộng?
- Tenant có bao nhiêu đơn?
- Page size là 20 hay 10.000?
- Sort mặc định theo thời gian hay mã?
- Truy vấn nào chiếm phần lớn tải?
- Index bổ sung làm tăng chi phí ghi bao nhiêu?

Có thể cần **hai index cho hai access pattern khác nhau** thay vì tạo một compound index khổng lồ.

## 21. `explain` để kiểm tra kế hoạch thực thi

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  status: "CONFIRMED",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Các chỉ số thường hữu ích:

| Thông tin | Ý nghĩa |
|---|---|
| `winningPlan` | Kế hoạch thực thi được chọn |
| `IXSCAN` | Đọc các entry index |
| `COLLSCAN` | Quét collection |
| `FETCH` | Truy cập document nguồn |
| `SORT` | Một bước sort không được xử lý hoàn toàn bằng thứ tự index |
| `nReturned` | Số document trả về |
| `totalKeysExamined` | Số index entry đã xem |
| `totalDocsExamined` | Số document đã xem |
| `executionTimeMillis` | Thời gian theo thống kê thử nghiệm |

Tên stage và cách trình bày có thể khác theo phiên bản/query engine. Một `IXSCAN` quét hàng triệu key cho một kết quả không mặc nhiên tốt; một `COLLSCAN` trên collection cực nhỏ có thể hợp lý.

Đừng chỉ nhìn một chỉ số. Cần đo latency p95/p99, tải đồng thời, số lần ghi index và phân bố dữ liệu của tenant lớn.

## 22. Sort và top-k tốn tài nguyên

Nếu query phải lấy hàng trăm nghìn document rồi sort theo field không có index phù hợp, nó có thể cần nhiều tài nguyên và tạo độ trễ đáng kể.

Giải pháp thường cân nhắc:

- Giới hạn tenant và điều kiện equality.
- Hạn chế khoảng ngày theo nhu cầu nghiệp vụ.
- Dùng index hỗ trợ filter và sort phổ biến.
- Giới hạn `limit` và thời gian query.
- Chỉ trả những field cần.
- Tránh sort mảng hoặc expression phức tạp nếu có thể lưu scalar tổng hợp đúng nghĩa.
- Theo dõi execution stats và query latency.

Không thể kết luận `limit(20)` nghĩa là mọi query chỉ đọc đúng 20 item.

## 23. Offset pagination với `skip`

~~~javascript
const pageSize = 20;
const pageNumber = 3;

db.orders.find({
  tenantId: "shop-17"
})
.sort({ createdAt: -1, _id: -1 })
.skip((pageNumber - 1) * pageSize)
.limit(pageSize);
~~~

Cách này dễ triển khai và hỗ trợ chọn trang thứ N. Nhưng offset lớn thường khiến engine phải đi qua nhiều kết quả trước khi trả trang cần, đồng thời dữ liệu thêm/xóa giữa các request có thể làm vị trí dịch chuyển.

Ví dụ: người dùng xem trang 1, sau đó một đơn mới được chèn lên đầu. `skip(20)` ở trang 2 có thể gặp lại một đơn đã ở trang 1.

Đối với lịch sử lớn hoặc infinite scroll, **keyset/cursor pagination** thường phù hợp hơn.

## 24. Keyset pagination: dùng tuple sort làm cursor

Nếu sort giảm dần:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

và document cuối trang trước là:

~~~javascript
{
  _id: "ord-103",
  createdAt: ISODate("2026-11-02T09:30:00Z")
}
~~~

thì trang tiếp theo cần:

\[
createdAt < cursorDate
\;\lor\;
(createdAt = cursorDate \land \_id < cursorId)
\]

Query:

~~~javascript
const cursorDate = ISODate("2026-11-02T09:30:00Z");
const cursorId = "ord-103";

db.orders.find({
  tenantId: "shop-17",
  $or: [
    { createdAt: { $lt: cursorDate } },
    {
      createdAt: cursorDate,
      _id: { $lt: cursorId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Trong dữ liệu ví dụ, `ord-102` có timestamp bằng cursor nhưng ID nhỏ hơn, nên có thể xuất hiện ở trang sau.

Nếu sort **tăng dần**, đổi điều kiện sang `$gt` ở cả các thành phần cùng hướng. Nếu sort pha trộn tăng/giảm giữa các trường, phải xây điều kiện theo **hướng riêng của từng field**.

### Kiểu ID của cursor

Dữ liệu ví dụ dùng `_id` string. Nếu database dùng ObjectId, cursor phải giữ và truyền lại BSON ObjectId theo mapping đúng. Đừng trộn string/ObjectId vì hình thức hiển thị giống nhau.

## 25. Keyset phải giữ nguyên filter gốc

Giả sử trang đầu lọc:

~~~javascript
{
  tenantId: "shop-17",
  status: "CONFIRMED",
  orderCodeKey: { $regex: "^ORD-2026-" },
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}
~~~

Trang tiếp theo phải **giữ toàn bộ điều kiện này** và bổ sung điều kiện cursor:

~~~javascript
const start = ISODate("2026-11-01T00:00:00Z");
const end = ISODate("2026-12-01T00:00:00Z");
const cursorDate = ISODate("2026-11-02T09:30:00Z");
const cursorId = "ord-103";

db.orders.find({
  tenantId: "shop-17",
  status: "CONFIRMED",
  orderCodeKey: { $regex: "^ORD-2026-" },
  createdAt: { $gte: start, $lt: end },
  $or: [
    { createdAt: { $lt: cursorDate } },
    {
      createdAt: cursorDate,
      _id: { $lt: cursorId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Cursor cần được tạo từ document cuối cùng đã trả về trong trang trước. Nếu client đổi filter nhưng dùng lại cursor cũ, kết quả không có nghĩa nhất quán. API có thể gắn fingerprint của filter vào cursor token.

### Cursor là dữ liệu không tin cậy

Client có thể sửa token. Nếu muốn bảo vệ tính toàn vẹn, có thể mã hóa/ký token theo chính sách server và kiểm tra tenant, sort, filter, phiên bản, expiry. Cursor **không cấp quyền**; mọi trang vẫn cần xác thực/ủy quyền.

## 26. Keyset không tự tạo snapshot bất biến

Keyset giúp duyệt theo vị trí của sort tuple, nhưng nếu dữ liệu đổi:

- Một đơn mới xuất hiện trước cursor không tự chèn vào những trang đã xem.
- Một đơn bị xóa biến mất khỏi trang sau.
- Một đơn đổi status có thể ra/vào filter.
- Một field sort bị cập nhật có thể làm document đổi vị trí.
- Dữ liệu đọc ở các replica có thể không mới như nhau.

Nếu nghiệp vụ đòi một ảnh chụp dữ liệu cố định của cả báo cáo, cần chính sách snapshot/cutoff và mức read consistency tương ứng, không chỉ dựa vào cursor.

Đối với danh sách đơn, `createdAt` nên là field bất biến theo hợp đồng để giảm biến động thứ tự.

## 27. Prefix và keyset theo mã

Nếu sort theo mã tăng dần rồi ID:

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  orderCodeKey: { $regex: "^ORD-2026-" }
})
.sort({ orderCodeKey: 1, _id: 1 })
.limit(20);
~~~

Trang tiếp theo dùng cursor `(orderCodeKey, _id)`:

~~~javascript
const cursorCode = "ORD-2026-0002";
const cursorId = "ord-102";

db.orders.find({
  tenantId: "shop-17",
  orderCodeKey: { $regex: "^ORD-2026-" },
  $or: [
    { orderCodeKey: { $gt: cursorCode } },
    {
      orderCodeKey: cursorCode,
      _id: { $gt: cursorId }
    }
  ]
})
.sort({ orderCodeKey: 1, _id: 1 })
.limit(20);
~~~

Sort/so sánh/cursor/index phải dùng cùng một collation và dữ liệu chuẩn hóa phù hợp. Nếu `orderCodeKey` unique trong tenant, ID là khóa phá hòa không bắt buộc về mặt lý thuyết trong tập hiện tại nhưng vẫn có thể làm contract rõ hơn.

## 28. DynamoDB: Query tập trung vào primary key

DynamoDB `Query` cần điều kiện **partition key equality**; nếu có sort key, có thể dùng các điều kiện thích hợp trên sort key, bao gồm so sánh, `BETWEEN` và `begins_with`.

Thiết kế khóa minh họa:

~~~text
PK = TENANT#shop-17
SK = ORDER#2026-11-02T09:30:00Z#ord-102

status = CONFIRMED
totalMinor = 450000
~~~

Ý tưởng key condition:

~~~text
PK = :tenant AND begins_with(SK, :prefix)

:tenant = "TENANT#shop-17"
:prefix = "ORDER#2026-11-"
~~~

Chỉ những item trong partition đã chọn có sort key bắt đầu bằng tiền tố được truy vấn.

### Range trên sort key

Nếu encode thời gian theo định dạng ISO chuẩn có thể so sánh lexicographic, sort key có thể hỗ trợ truy vấn khoảng thời gian. Nhưng phải hiểu:

- `BETWEEN` trong DynamoDB bao gồm cả hai đầu.
- `begins_with` áp dụng trên sort key trong KeyConditionExpression theo khả năng API.
- Query chỉ đọc trực tiếp trong partition/index phù hợp; muốn truy vấn theo status hoặc customer có thể cần GSI hoặc projection khác.
- `FilterExpression` lọc sau khi đọc các item theo key condition; nó không biến non-key field thành key range hiệu quả.
- DynamoDB Query trả theo sort key và có thể đảo thứ tự qua `ScanIndexForward`.

DynamoDB phân trang bằng `LastEvaluatedKey`. Khi có FilterExpression, `Limit` được áp theo ngữ nghĩa đánh giá item của Query và một trang có thể trả **ít item hơn limit**, thậm chí không có item mà vẫn có `LastEvaluatedKey`. Consumer phải tiếp tục theo token đúng hợp đồng.

Không chuyển logic MongoDB `skip(10000)` sang DynamoDB và mặc định API tương đương.

## 29. Cassandra: phân vùng và clustering

Cassandra tối ưu query theo primary key, gồm **partition key** và **clustering columns**.

Ví dụ bảng phục vụ truy vấn đơn trong một ngày của tenant:

~~~sql
CREATE TABLE orders_by_tenant_day (
    tenant_id text,
    order_day date,
    created_at timestamp,
    order_id text,
    status text,
    total_minor bigint,
    PRIMARY KEY ((tenant_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
~~~

Query:

~~~sql
SELECT order_id, created_at, status, total_minor
FROM orders_by_tenant_day
WHERE tenant_id = 'shop-17'
  AND order_day = '2026-11-02'
  AND created_at >= '2026-11-02T00:00:00Z'
  AND created_at < '2026-11-03T00:00:00Z';
~~~

Ý nghĩa:

- Partition xác định bởi `(tenant_id, order_day)`.
- Clustering key có thứ tự theo cấu hình.
- Range thường phù hợp với clustering columns khi query thỏa các ràng buộc khóa.
- `ORDER BY` trong Cassandra không phải sort tùy ý theo mọi field.
- Nếu cần query nhiều ngày, có thể phải đọc nhiều partition rồi merge hoặc thiết kế một bảng theo query khác.

Prefix tìm một string bất kỳ không có cùng cách làm như anchored regex + B-tree trong MongoDB. Cần cân nhắc thiết kế key, search index hoặc mô hình bảng riêng. Không dùng `ALLOW FILTERING` như cách giải quyết mọi truy vấn không khớp key design nếu không hiểu khả năng scan và chi phí.

## 30. So sánh ba hướng truy vấn NoSQL

| Nhu cầu | MongoDB | DynamoDB | Cassandra |
|---|---|---|---|
| Lọc khoảng ngày | `$gte`/`$lt` trên BSON Date | Range trên sort key trong Query | Range trên clustering column theo điều kiện khóa |
| Lọc prefix | Anchored regex hoặc lexical range có điều kiện | `begins_with` trên sort key | Phụ thuộc mô hình key/index/search |
| Sort theo field tùy chọn | `sort`, có thể dùng index | Chủ yếu sort key trong một Query | Chủ yếu clustering order trong partition |
| Compound sort | Nhiều field và compound index | Encode thứ tự vào sort key/index | Clustering columns theo thiết kế |
| Offset pagination | `skip`/`limit` nhưng có chi phí sâu | Không tương đương offset MongoDB | Driver paging state |
| Cursor pagination | Tuple sort + filter cursor | `LastEvaluatedKey` | Paging state và khóa theo CQL |
| Tối ưu | Query planner + indexes | PK/SK + GSI theo access pattern | Partition/clustering + query-first table |

Đây là bảng định hướng, không thay thế tài liệu API phiên bản cụ thể.

## 31. Xây query an toàn trong Java/Spring Data MongoDB

Ví dụ API:

~~~http
GET /orders?from=2026-11-01&toExclusive=2026-12-01&codePrefix=ORD-2026-&limit=20
~~~

Ứng dụng cần parse ngày theo timezone nghiệp vụ thành UTC Instant, normalize prefix, validate khoảng và giới hạn số lượng.

~~~java
import java.time.Instant;
import java.util.regex.Pattern;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Query buildSearch(
        String authenticatedTenantId,
        Instant fromInclusive,
        Instant toExclusive,
        String prefixKey,
        int limit) {

    if (!fromInclusive.isBefore(toExclusive)) {
        throw new IllegalArgumentException("Invalid time range");
    }
    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("Invalid page size");
    }

    Query query = new Query();
    query.addCriteria(
        Criteria.where("tenantId").is(authenticatedTenantId)
    );
    query.addCriteria(
        Criteria.where("createdAt")
            .gte(fromInclusive)
            .lt(toExclusive)
    );

    if (prefixKey != null && !prefixKey.isBlank()) {
        if (prefixKey.length() > 40) {
            throw new IllegalArgumentException("Prefix too long");
        }
        query.addCriteria(
            Criteria.where("orderCodeKey")
                .regex("^" + Pattern.quote(prefixKey))
        );
    }

    query.with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")
    ));
    query.limit(limit);
    return query;
}
~~~

Đây là đoạn minh họa xây query, chưa có controller/repository, mapping BSON hoặc chiến lược cursor đầy đủ. Cần kiểm tra phiên bản thư viện, cách escape regex và kiểu ID thực tế.

**Không tin `tenantId` từ tham số client nếu người gọi không được quyền chọn tenant**; dùng ngữ cảnh đã xác thực/ủy quyền. Không nhận raw filter object, raw operator hoặc sort field bất kỳ từ client; dùng allowlist.

## 32. API contract cho khoảng thời gian

API:

~~~http
GET /orders?startDate=2026-11-01&endDate=2026-11-30
~~~

dễ mơ hồ: endDate bao gồm ngày cuối không, múi giờ nào và field ngày nào? Một hợp đồng rõ hơn:

~~~text
createdFrom:        ISO 8601 instant, inclusive
createdBefore:      ISO 8601 instant, exclusive
businessTimeZone:   supplied or defined by tenant
defaultSort:        createdAt desc, id desc
maxPageSize:        100
~~~

Nếu nhận ngày lịch thay vì Instant, server phải chuyển **đầu ngày tại timezone nghiệp vụ** sang UTC, kể cả những ngày địa phương dài 23/25 giờ.

API cần còn ghi giới hạn khoảng tối đa, cách phân trang, cursor expiry, trường hợp cận ngược và status filter mặc định.

## 33. Bảo mật và tài nguyên

Truy vấn prefix rất ngắn như `"A"` có thể khớp hàng triệu mã. Một filter range nhiều năm cũng có thể quá rộng. Những giới hạn cần cân nhắc:

- Giới hạn độ dài tối thiểu/tối đa cho prefix nếu nghiệp vụ chấp nhận.
- Escape input regex và không cho phép pattern tùy ý.
- Giới hạn khoảng thời gian và page size.
- Timeout/maxTimeMS hoặc giới hạn tài nguyên query.
- Tenant scope bắt buộc, kể cả khi ID là UUID ngẫu nhiên.
- Kiểm soát sort field và direction bằng allowlist.
- Query rate limiting nếu endpoint bị lạm dụng.
- Không trả dữ liệu nhạy cảm chỉ vì projection có field đó.
- Theo dõi slow query, scan và hotspot trên tenant lớn.

Một query hợp lệ về cú pháp vẫn có thể tạo load quá lớn hoặc lộ dữ liệu nếu bỏ qua scope.

## 34. Bài tập vận dụng

### Bài A — Range tổng tiền

Tìm đơn `shop-17` từ 250.000 (bao gồm) đến dưới 600.000:

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  totalMinor: {
    $gte: NumberLong("250000"),
    $lt: NumberLong("600000")
  }
});
~~~

Kết quả mẫu gồm `ord-101`, `ord-102`; `ord-106` có 600.000 bị loại do cận trên mở.

### Bài B — Prefix mã đơn

Tìm mã bắt đầu bằng `ORD-2026-`:

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  orderCodeKey: { $regex: "^ORD-2026-" }
});
~~~

Hãy giải thích tại sao bỏ dấu `^` làm thay đổi ngữ nghĩa, và tại sao input có dấu `.` phải được escape.

### Bài C — Hai timestamp bằng nhau

Sort giảm dần theo `createdAt` rồi `_id`:

~~~javascript
db.orders.find({
  tenantId: "shop-17"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Giải thích vì sao `ord-102` và `ord-103` có thứ tự xác định khi thêm ID phá hòa.

### Bài D — Keyset sau một cursor

Cursor trang trước là `(2026-11-02T09:30Z, ord-103)`. Tìm trang sau:

~~~javascript
db.orders.find({
  tenantId: "shop-17",
  $or: [
    {
      createdAt: {
        $lt: ISODate("2026-11-02T09:30:00Z")
      }
    },
    {
      createdAt: ISODate("2026-11-02T09:30:00Z"),
      _id: { $lt: "ord-103" }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Vì sao chỉ dùng `createdAt < cursorDate` sẽ bỏ sót `ord-102`?

### Bài E — Range mảng

`scores = [1,10]`. Yêu cầu một phần tử từ 4 đến 7:

~~~javascript
db.products.find({
  scores: {
    $elemMatch: {
      $gte: 4,
      $lte: 7
    }
  }
});
~~~

`[1,10]` không khớp vì không có phần tử nào trong khoảng đó.

### Bài F — Compound index

Hai truy vấn:

~~~javascript
// Query 1: danh sách PENDING mới nhất
db.orders.find({
  tenantId: "shop-17",
  status: "PENDING"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);

// Query 2: đơn có giá trị cao
db.orders.find({
  tenantId: "shop-17",
  totalMinor: { $gte: NumberLong("1000000") }
})
.sort({ totalMinor: -1, _id: -1 })
.limit(20);
~~~

Thảo luận tại sao một index `(tenantId,status,createdAt,_id)` hợp Query 1 hơn Query 2. Query 2 có thể cần index khác; phải đo query planner thay vì kết luận dựa vào tên trường.

### Bài G — DynamoDB thiếu access pattern

Một table chỉ có `PK = orderId`, không có GSI. Cần lấy 20 Order mới nhất của một tenant. Có thể Query hiệu quả trực tiếp theo tenant/time không?

Không chỉ với primary key này. Cần key/index/projection được thiết kế theo tenant và thời gian, hoặc chấp nhận phương án quét không phù hợp ở quy mô lớn.

### Bài H — Cassandra nhiều ngày

Bảng có partition key `(tenantId, orderDay)`. Một query duy nhất vào một partition có tự trả 20 đơn mới nhất trong 30 ngày không?

Không; nó chỉ bao phủ partition ngày được chọn. Cần truy vấn/hợp nhất nhiều partition hoặc một bảng truy vấn phù hợp hơn.

## 35. Checklist thiết kế trước khi triển khai

1. Xác định field cần lọc và kiểu BSON thực tế.
2. Ghi rõ cận mở/đóng, đơn vị và múi giờ.
3. Chọn semantics prefix: đầu toàn field, đầu token hay substring.
4. Chuẩn hóa mã và escape literal input khi dùng regex.
5. Xác định sort field, hướng và khóa phá hòa duy nhất.
6. Chọn phân trang offset hay keyset theo quy mô và UX.
7. Giữ nguyên filter giữa các trang; bảo vệ cursor token nếu cần.
8. Xác định mức nhất quán khi dữ liệu thay đổi giữa các trang.
9. Thiết kế index, partition/sort key theo access pattern của engine.
10. Đo query plan, candidate count, sort stage và latency p95/p99.
11. Kiểm tra missing/null, mixed BSON types, array và Unicode/collation.
12. Đặt tenant authorization, field allowlist và giới hạn tải.
13. Ghi query contract để reader và writer không hiểu khác nhau.
14. Kiểm thử cận ngày, timestamp trùng, tiền tố đặc biệt và dữ liệu lớn.

Một bản ghi quyết định truy vấn có thể là:

~~~yaml
query: ListTenantOrders
owner: OrderService
filters:
  tenantId: "from authenticated context"
  status: "optional enum"
  createdAt:
    start: inclusive
    end: exclusive
    type: utc-instant
  orderCodeKey:
    type: literal-normalized-prefix
sort:
  - { field: createdAt, direction: desc }
  - { field: _id, direction: desc }
pagination:
  type: keyset
  pageSizeMax: 100
  cursorFields: [createdAt, _id]
consistency:
  fixedSnapshot: false
indexes:
  candidates:
    - [tenantId, status, createdAt, _id]
    - [tenantId, orderCodeKey]
security:
  tenantScopeRequired: true
  fieldAllowlist: true
~~~

YAML chỉ mô tả hợp đồng, không phải cấu hình được MongoDB/DynamoDB tự thực thi. Các index và ràng buộc cần triển khai và đo trên hệ thống thật.

## 36. Kết luận

**Truy vấn theo khoảng** cần đúng loại dữ liệu, đơn vị và biên inclusive/exclusive. **Truy vấn tiền tố** cần biết đang tìm đầu field hay đầu token, có chuẩn hóa và collation nào, regex có được escape và index có hiệu quả không. **Sắp xếp** cần hướng, khóa phá hòa và cách phân trang giữ thứ tự có thể dự đoán.

Trong NoSQL, thiết kế truy vấn còn là thiết kế dữ liệu: MongoDB tối ưu qua compound indexes và query planner; DynamoDB dựa nhiều vào partition/sort key; Cassandra dựa vào partition và clustering. Không giả định mọi engine có thể sort hoặc lọc theo mọi field một cách hiệu quả.

Quy trình đáng nhớ là **xác định ngữ nghĩa → viết filter chính xác → tạo thứ tự ổn định → chọn key/index theo access pattern → đo hiệu năng → kiểm soát concurrency, pagination và quyền truy cập**. Khi thực hiện đầy đủ, range, prefix và sort trở thành một hợp đồng truy vấn vừa đúng nghiệp vụ vừa vận hành được ở quy mô thực tế.
