# Truy vấn theo thời gian, chuỗi và collation trong MongoDB

## 1. Bài toán: cùng một document, nhiều cách so sánh

Một ứng dụng xuất bản nội dung có thể cần tìm bài viết:

- được đăng trong **ngày 14/11 theo giờ Việt Nam**;
- có tiêu đề **bắt đầu bằng “MongoDB”**, hoặc chứa một cụm từ;
- có tiêu đề khớp với “cafe” dù dữ liệu lưu `Cafe` hoặc `Café`;
- sắp xếp tiêu đề theo thứ tự từ vựng phù hợp với ngôn ngữ người đọc.

Những yêu cầu này thoạt nhìn đều là lọc dữ liệu, nhưng liên quan đến ba cơ chế khác nhau của MongoDB:

1. **So sánh thời gian:** làm việc với BSON `Date`, ranh giới thời gian và toán tử so sánh như `$gte`, `$lt`.
2. **So sánh và tìm chuỗi:** phân biệt truy vấn bằng giá trị chính xác, biểu thức chính quy `$regex`, các biểu thức aggregation và tìm kiếm toàn văn.
3. **Collation:** tập quy tắc so sánh và sắp xếp chuỗi theo ngôn ngữ, có ảnh hưởng đến điều kiện bằng, thứ tự, chỉ mục và tính duy nhất.

Không có một cách so sánh chuỗi đúng cho mọi trường hợp. Tìm mã định danh phân biệt chữ hoa/chữ thường khác với tìm tên người; tìm chuỗi con khác với tìm từ khóa; tìm sự kiện theo ngày UTC khác với ngày ở một múi giờ cụ thể.

Sau bài học, người học có thể viết truy vấn `mongosh` đúng kiểu dữ liệu, tạo khoảng ngày nửa mở, chọn giữa equality và `$regex`, cấu hình collation cho truy vấn và index, đồng thời nhận ra các trường hợp dễ gây sai kết quả hoặc truy vấn chậm.

## 2. Chuẩn bị dữ liệu thực hành

Các ví dụ sử dụng `mongosh` và database thử nghiệm `mongo_query_row104_lab`. Hãy kết nối đến MongoDB mà bạn được phép thao tác trước khi chạy:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Nếu bạn chạy MongoDB trên host/cổng khác hoặc cần xác thực, dùng URI đúng với môi trường được cấp. Trong shell:

```javascript
const lab = db.getSiblingDB("mongo_query_row104_lab");
const articles = lab.getCollection("articles");
const runId = "row104-" + new ObjectId().toHexString();

print("Database: " + lab.getName());
print("Run ID: " + runId);

articles.insertMany([
  {
    runId,
    title: "MongoDB nhập môn",
    category: "database",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-13T16:59:59.000Z")
  },
  {
    runId,
    title: "MongoDB và document",
    category: "database",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-13T17:00:00.000Z")
  },
  {
    runId,
    title: "mongodb cho người mới",
    category: "database",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-14T03:00:00.000Z")
  },
  {
    runId,
    title: "MONGODB nâng cao",
    category: "database",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-14T16:59:59.000Z")
  },
  {
    runId,
    title: "MongoDB tổng kết",
    category: "database",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-14T17:00:00.000Z")
  },
  {
    runId,
    title: "Café dữ liệu",
    category: "lifestyle",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-14T10:00:00.000Z")
  },
  {
    runId,
    title: "Cafe dữ liệu",
    category: "lifestyle",
    status: "PUBLISHED",
    publishedAt: ISODate("2026-11-14T11:00:00.000Z")
  }
]);

printjson(
  articles.find(
    { runId },
    { _id: 0, title: 1, publishedAt: 1 }
  ).sort({ publishedAt: 1 }).toArray()
);
```

`runId` giúp phân biệt dữ liệu của lượt thực hành này với lượt khác trong cùng collection. Hầu hết truy vấn bên dưới đều thêm `runId` để chỉ làm việc với dữ liệu ví dụ. Nếu mở phiên `mongosh` mới, biến `runId` không tự được khôi phục; hãy ghi lại giá trị đã in ra hoặc tạo lại dữ liệu theo một lượt thực hành mới.

**Phân biệt kiểu:** `publishedAt` trong dữ liệu mẫu là BSON `Date`. Trường `title` là `string`. Điều này rất quan trọng: MongoDB so sánh BSON Date theo giá trị thời gian, còn string có quy tắc so sánh chuỗi. Một chuỗi nhìn giống ngày giờ không tự trở thành BSON Date khi truy vấn.

## 3. Truy vấn thời gian với BSON Date

### 3.1. BSON Date là thời điểm, không phải chuỗi hiển thị

Trong MongoDB, BSON `Date` lưu số **mili giây** kể từ Unix epoch `1970-01-01T00:00:00Z` bằng số nguyên 64 bit có dấu. Giá trị Date đại diện một **thời điểm tuyệt đối**; bản thân nó không lưu tên múi giờ đã dùng lúc nhập.

Hai biểu diễn sau cùng trỏ đến một thời điểm:

```javascript
const utcInstant = ISODate("2026-11-14T01:30:00Z");
const localInstant = ISODate("2026-11-14T08:30:00+07:00");

print(utcInstant.getTime() === localInstant.getTime()); // true
print(localInstant.toISOString()); // 2026-11-14T01:30:00.000Z
```

Khi biểu diễn cho người dùng ở Việt Nam, instant `01:30 UTC` tương ứng `08:30` theo giờ `Asia/Ho_Chi_Minh` ở ngày này. Truy vấn nên dùng các mốc thời gian xác định; việc định dạng cho người xem được xử lý riêng.

### 3.2. So sánh thời điểm bằng `$gte`, `$gt`, `$lt`, `$lte`

Các toán tử so sánh phổ biến:

| Toán tử | Ý nghĩa | Ví dụ về thời gian |
| --- | --- | --- |
| `$gt` | Lớn hơn | Sau một mốc, không gồm mốc |
| `$gte` | Lớn hơn hoặc bằng | Từ một mốc, gồm mốc |
| `$lt` | Nhỏ hơn | Trước một mốc, không gồm mốc |
| `$lte` | Nhỏ hơn hoặc bằng | Trước hoặc đúng một mốc |
| `$eq` | Bằng đúng một giá trị | Bằng một instant cụ thể |
| `$exists` | Field có tồn tại | Kiểm tra dữ liệu có trường thời gian hay không |

Ví dụ tìm các bài từ một thời điểm:

```javascript
articles.find(
  {
    runId,
    publishedAt: {
      $gte: ISODate("2026-11-14T00:00:00Z")
    }
  },
  { _id: 0, title: 1, publishedAt: 1 }
);
```

Lệnh này lọc theo **instant UTC**. Nếu yêu cầu thực tế là “từ đầu ngày theo giờ Việt Nam”, mốc đầu phải được chuyển từ giờ Việt Nam sang UTC trước, như phần tiếp theo.

### 3.3. Chọn một ngày bằng khoảng nửa mở `[start, end)`

Để lấy toàn bộ sự kiện thuộc ngày `2026-11-14` theo UTC:

```javascript
articles.find({
  runId,
  publishedAt: {
    $gte: ISODate("2026-11-14T00:00:00.000Z"),
    $lt: ISODate("2026-11-15T00:00:00.000Z")
  }
});
```

Khoảng nửa mở có dạng:

```text
start <= publishedAt < end
```

Lấy **đầu ngày kế tiếp** làm mốc kết thúc giúp không bỏ sót giá trị có phần mili giây và không đếm trùng các phần tử nằm đúng ranh giới khi truy vấn ngày liên tiếp.

Không nên lọc bằng cách cho mốc cuối là `23:59:59`, vì các thời điểm `23:59:59.001` đến `23:59:59.999` sẽ bị bỏ qua. Cũng không nên viết `publishedAt: ISODate("2026-11-14")` để tìm “cả ngày”: điều kiện bằng chỉ khớp đúng instant tương ứng nửa đêm UTC.

### 3.4. Ngày theo giờ Việt Nam cần ranh giới khác

“Các bài đăng trong ngày 14/11/2026 theo giờ Việt Nam” có khoảng địa phương:

```text
2026-11-14 00:00:00 +07:00  (bao gồm)
                     đến
2026-11-15 00:00:00 +07:00  (không bao gồm)
```

Tương đương theo UTC:

```text
[2026-11-13T17:00:00Z, 2026-11-14T17:00:00Z)
```

Truy vấn:

```javascript
articles.find(
  {
    runId,
    publishedAt: {
      $gte: ISODate("2026-11-13T17:00:00Z"),
      $lt: ISODate("2026-11-14T17:00:00Z")
    }
  },
  { _id: 0, title: 1, publishedAt: 1 }
).sort({ publishedAt: 1 });
```

Hoặc viết trực tiếp các mốc có offset:

```javascript
articles.find({
  runId,
  publishedAt: {
    $gte: ISODate("2026-11-14T00:00:00+07:00"),
    $lt: ISODate("2026-11-15T00:00:00+07:00")
  }
});
```

Với dữ liệu mẫu, khoảng này bao gồm `MongoDB và document`, `mongodb cho người mới`, `MONGODB nâng cao`, `Café dữ liệu` và `Cafe dữ liệu`. Bản ghi lúc `2026-11-13T16:59:59Z` ở trước ranh giới và bản ghi lúc `2026-11-14T17:00:00Z` đã thuộc ngày tiếp theo theo giờ Việt Nam.

**Lưu ý múi giờ:** `+07:00` mô tả độ lệch UTC ở ví dụ này. Với khu vực có giờ mùa hè, một ngày địa phương có thể dài 23 hoặc 25 giờ. Khi viết báo cáo theo múi giờ như `America/New_York`, cần tính **hai ranh giới nửa đêm của ngày địa phương** theo tên múi giờ IANA; không mặc định lấy mốc đầu cộng đúng 24 giờ.

### 3.5. Query theo thời gian hiện tại và thời hạn

Ví dụ truy vấn các bản ghi đã đến thời điểm công bố:

```javascript
const now = new Date();

articles.find({
  runId,
  publishedAt: { $lte: now }
});
```

`new Date()` ở `mongosh` dựa vào đồng hồ máy chạy shell. Trong server application, thời điểm do máy ứng dụng tạo và múi giờ hiển thị là hai vấn đề khác nhau. Đồng hồ các hệ thống liên quan cần được đồng bộ phù hợp.

Khi dùng khoảng thời gian động để phân trang, nên cố định mốc kết thúc trong một đợt đọc nếu muốn kết quả ổn định, vì các bài mới có thể được thêm vào khi đang phân trang.

### 3.6. Trường bị thiếu, `null` và sai kiểu

Nếu cùng một field lúc được lưu bằng Date, lúc bằng string:

```javascript
{ publishedAt: ISODate("2026-11-14T01:30:00Z") }
{ publishedAt: "2026-11-14T01:30:00Z" }
```

Đây là **hai kiểu BSON khác nhau**. Không nên kỳ vọng một điều kiện so sánh với BSON Date sẽ xử lý chuỗi ngày giờ như Date. MongoDB thường thực hiện so sánh truy vấn trong phạm vi kiểu BSON tương ứng; dữ liệu trộn kiểu dẫn đến kết quả khó đoán nếu ứng dụng không có quy ước.

Có thể tìm các document có field thời gian là Date:

```javascript
articles.find({
  runId,
  publishedAt: { $type: "date" }
});
```

Với dữ liệu legacy dạng string, hãy cân nhắc chuyển đổi có kiểm soát thành BSON Date. Parse trong từng truy vấn thường làm logic phức tạp, có thể tạo lỗi dữ liệu và khó khai thác index như so sánh trực tiếp trên trường Date.

## 4. Truy vấn chuỗi chính xác: equality và các toán tử cơ bản

### 4.1. So khớp đúng chuỗi

```javascript
articles.find({
  runId,
  title: "MongoDB và document"
});
```

Nếu không cấu hình collation riêng, nhiều collection dùng **simple collation**, so sánh nhị phân theo giá trị chuỗi. Khi đó các chuỗi `MongoDB`, `mongodb` và `MONGODB` khác nhau; `Cafe` và `Café` cũng khác nhau.

Điều kiện bằng chính xác phù hợp với mã hệ thống, chuỗi cố định và trường mà ứng dụng quy định phải khớp đầy đủ. Nó không tự động tìm “chứa cụm từ” và không phải tìm kiếm toàn văn.

### 4.2. Truy vấn theo danh sách và điều kiện logic

```javascript
// Chỉ khớp những title nằm trong danh sách.
articles.find({
  runId,
  title: {
    $in: ["MongoDB nhập môn", "MongoDB và document"]
  }
});

// Kết hợp trạng thái, danh mục và điều kiện chuỗi.
articles.find({
  runId,
  status: "PUBLISHED",
  category: "database",
  title: "MongoDB và document"
});
```

`$in` hữu ích khi có một danh sách giá trị chính xác. Khi cần so khớp không phân biệt chữ hoa, dấu hoặc theo ngôn ngữ, ta phải xem xét **collation**, chứ không phải ép mọi yêu cầu thành biểu thức chính quy.

### 4.3. Cách sắp xếp chuỗi phụ thuộc quy tắc so sánh

```javascript
articles.find(
  { runId },
  { _id: 0, title: 1 }
).sort({ title: 1 });
```

`sort({ title: 1 })` biểu thị sắp xếp tăng dần. Với simple collation, thứ tự có thể không giống thứ tự từ điển người Việt kỳ vọng; các ký tự hoa, thường và chữ có dấu có thể nằm ở vị trí khác. Phần collation bên dưới cho phép chọn quy tắc theo ngôn ngữ phù hợp.

## 5. Tìm chuỗi bằng `$regex`

### 5.1. Regex giải quyết bài toán khác equality

`$regex` dùng biểu thức chính quy để tìm mẫu ký tự trong string. Các mẫu hay gặp:

| Mẫu | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `^MongoDB` | Bắt đầu bằng “MongoDB” | Tìm theo tiền tố |
| `MongoDB$` | Kết thúc bằng “MongoDB” | Tìm theo hậu tố |
| `MongoDB` | Có chứa “MongoDB” ở bất kỳ vị trí nào | Tìm chuỗi con |
| `^MongoDB$` | Toàn bộ string bằng “MongoDB” | Khớp nguyên chuỗi theo regex |
| `MongoDB` + tùy chọn `i` | Không phân biệt chữ hoa/thường theo cơ chế regex | Search không phân biệt case |
| `^MongoDB.*cơ bản$` | Bắt đầu và kết thúc theo hai mẫu | Kiểm tra một hình dạng chuỗi |

Trong `mongosh` có thể dùng regex literal:

```javascript
// Chỉ title bắt đầu đúng "MongoDB" với chữ hoa/thường như đã viết.
articles.find({
  runId,
  title: /^MongoDB/
});

// Tìm tiền tố không phân biệt case.
articles.find({
  runId,
  title: /^mongodb/i
});

// Tìm chuỗi con ở bất kỳ vị trí nào, không phân biệt case.
articles.find({
  runId,
  title: /mongodb/i
});
```

Tương đương cú pháp chuỗi `$regex`:

```javascript
articles.find({
  runId,
  title: {
    $regex: "^mongodb",
    $options: "i"
  }
});
```

Với dữ liệu mẫu, `/^MongoDB/` khớp các tiêu đề bắt đầu chính xác bằng chữ `MongoDB`; `/^mongodb/i` còn khớp các biến thể `mongodb` và `MONGODB`. Những mẫu này **không** có nghĩa sẽ bỏ qua dấu tiếng Việt hoặc tự hiểu từ đồng nghĩa.

### 5.2. Regex có thể làm truy vấn tốn kém

Mẫu tìm tiền tố có điểm bắt đầu rõ ràng, ví dụ `/^MongoDB/`, có khả năng tận dụng một **B-tree index** thông thường trên trường string trong những điều kiện phù hợp. Mẫu `/MongoDB/` không neo đầu hoặc `/^mongodb/i` có thể phải kiểm tra nhiều giá trị hơn, đặc biệt khi collection lớn.

```javascript
// Trên database thực hành, có thể tạo chỉ mục simple cho tiêu đề.
articles.createIndex(
  { title: 1 },
  { name: "title_simple" }
);

// Quan sát kế hoạch thực thi.
printjson(
  articles.find({
    title: /^MongoDB/
  }).explain("executionStats")
);
```

Khi đọc `explain()`, xem các trường như `winningPlan`, số document được đọc và số document trả về. Kết quả thực tế phụ thuộc số lượng dữ liệu, index và tối ưu hóa truy vấn; với collection chỉ có vài document, MongoDB có thể chọn collection scan vì rẻ hơn. Ví dụ không áp đặt một kế hoạch thực thi duy nhất.

**Cảnh báo:** index có collation không phân biệt case không làm `$regex` tự trở thành tìm kiếm không phân biệt case hiệu quả. Toán tử `$regex` **không collation-aware**, vì vậy case-insensitive index kiểu collation thường không cải thiện trực tiếp `$regex` với tùy chọn `i` như kỳ vọng. Khi yêu cầu là khớp nguyên chuỗi không phân biệt case, equality + collation thường phù hợp hơn.

### 5.3. Biểu thức chính quy và input người dùng

Nếu người dùng nhập `C++` hoặc `a.b`, các ký tự `+` và `.` có ý nghĩa đặc biệt trong regex. Không ghép raw user input thẳng vào biểu thức regex rồi coi đó là tìm chuỗi nguyên văn:

```javascript
// Không nên coi input này là literal regex an toàn.
const userInput = "a.b";
// new RegExp(userInput) sẽ có dấu "." mang ý nghĩa ký tự bất kỳ.
```

Nếu sản phẩm có tính năng “tìm nguyên văn chuỗi con”, cần **escape metacharacters** trước khi dựng regex, giới hạn độ dài/mức phức tạp đầu vào và áp kiểm soát tài nguyên truy vấn thích hợp. Với nhu cầu tìm kiếm ngôn ngữ tự nhiên ở quy mô lớn, đánh giá công cụ text/search chuyên dụng thay vì giả định regex bao quát mọi trường hợp.

### 5.4. Regex khác gì text search?

`$regex` tìm **mẫu ký tự**. Tìm kiếm toàn văn thường xử lý **từ**, token, quy tắc ngôn ngữ, đôi khi tính liên quan (relevance score).

MongoDB có cơ chế `$text` khi collection có text index; ngoài ra MongoDB Search trên triển khai hỗ trợ cung cấp các khả năng tìm kiếm chuyên dụng với index và analyzer tương ứng. Các cơ chế này có semantics khác `$regex`, ví dụ tách từ hoặc xử lý tiếng Việt, nên cần chọn dựa trên sản phẩm chứ không đổi toán tử một cách máy móc.

## 6. Collation: quy tắc so sánh chuỗi theo ngôn ngữ

### 6.1. Collation là gì?

**Collation** quy định cách MongoDB so sánh và sắp xếp các giá trị string. Nó có thể xét:

- ngôn ngữ/locale như `en` hoặc `vi`;
- phân biệt hoặc bỏ qua khác biệt chữ hoa/thường;
- phân biệt hoặc bỏ qua dấu/biến thể ký tự ở cấp độ so sánh nhất định;
- xử lý dãy chữ số khi sắp xếp;
- các lựa chọn như thứ tự dấu câu và khoảng trắng, tùy mục đích.

Ví dụ, khi tìm tên người, yêu cầu “hoa” khớp “Hoa” có thể hợp lý. Nhưng một mã bí mật hoặc token nhạy cảm không nên tự động bị xem là tương đương chỉ vì khác chữ hoa/thường. Vì vậy cần thiết kế collation theo **ý nghĩa của field**, không mặc định dùng cùng một collation cho mọi chuỗi.

### 6.2. Những tùy chọn cần biết

| Tùy chọn | Ý nghĩa thực tế |
| --- | --- |
| `locale` | Bộ quy tắc ngôn ngữ; ví dụ `"en"`, `"vi"` |
| `strength: 1` | So sánh cấp primary: thường bỏ qua case và khác biệt dấu ở cấp secondary, tùy bảng chữ của locale |
| `strength: 2` | Thêm phân biệt khác biệt secondary như dấu; thường vẫn bỏ qua case |
| `strength: 3` | Thêm phân biệt case/biến thể ở cấp tertiary; là mức mặc định phổ biến khi dùng ICU collation |
| `caseLevel` | Điều chỉnh phân biệt case ở cấp độ thấp khi cần |
| `numericOrdering: true` | Cho phép sắp xếp chuỗi chữ số theo giá trị số trong các trường hợp được hỗ trợ |
| `normalization` | Liên quan đến chuẩn hóa Unicode trong quá trình so sánh theo collation |

`strength` là cấp độ so sánh, **không đơn thuần là công tắc có/không phân biệt dấu** trên mọi ngôn ngữ. Một số chữ cái được coi là ký tự riêng ở cấp primary tùy locale; kết quả cụ thể nên được xác định theo ngôn ngữ, phiên bản ICU và dữ liệu nghiệp vụ.

### 6.3. Equality không phân biệt hoa/thường và dấu

Ví dụ tìm các bài có tiêu đề tương đương `cafe dữ liệu` theo English collation ở cấp primary:

```javascript
articles.find(
  { runId, title: "cafe dữ liệu" },
  { _id: 0, title: 1 }
).collation({
  locale: "en",
  strength: 1
});
```

Với dữ liệu mẫu, truy vấn thể hiện cách so sánh không phân biệt case và những dấu được xem là khác biệt secondary ở locale này; hai biến thể `Cafe dữ liệu` và `Café dữ liệu` là ví dụ dễ quan sát. Đây là **equality** kết hợp collation, không phải regex và không phải một lần biến đổi dữ liệu lưu trữ.

Nếu muốn **phân biệt dấu nhưng bỏ qua case**:

```javascript
articles.find({
  runId,
  title: "cafe dữ liệu"
}).collation({
  locale: "en",
  strength: 2
});
```

Với quy tắc này, `Cafe dữ liệu` có thể được coi tương đương `cafe dữ liệu` về case, còn `Café dữ liệu` có dấu sắc trên `é` nên khác ở cấp secondary. Nếu yêu cầu là phân biệt cả case, dùng collation có strength phù hợp hoặc simple collation khi muốn đối chiếu nhị phân.

### 6.4. Sắp xếp chuỗi tiếng Việt theo locale

```javascript
articles.find(
  { runId },
  { _id: 0, title: 1 }
).sort({ title: 1 }).collation({
  locale: "vi",
  strength: 3
});
```

Đây là sắp xếp theo quy tắc của locale tiếng Việt qua ICU. Nó có thể khác thứ tự binary khi dùng simple collation. Khi ứng dụng có người dùng ở nhiều khu vực, cần quyết định locale dựa trên ngôn ngữ hiển thị hoặc chính sách sắp xếp của sản phẩm.

Không nên xem collation là chức năng “bỏ dấu tiếng Việt” để chuẩn hóa mọi tên riêng. Đặc biệt, những ký tự có ý nghĩa chữ cái riêng như `đ` có thể không tương đương với `d` theo các quy tắc collation thông thường. Nếu tính năng yêu cầu tìm gần đúng, phiên âm, bỏ dấu toàn phần hoặc synonym, cần cơ chế tìm kiếm được định nghĩa riêng.

### 6.5. Sắp xếp chuỗi chứa số

Với các mã hiển thị `"Bài 2"` và `"Bài 10"`, sắp xếp nhị phân thường đặt `"Bài 10"` trước `"Bài 2"`. Khi muốn dãy chữ số được xem xét theo giá trị số trong collation:

```javascript
const labels = lab.getCollection("labels_demo");
labels.insertMany([
  { runId, label: "Bài 2" },
  { runId, label: "Bài 10" },
  { runId, label: "Bài 1" }
]);

labels.find(
  { runId },
  { _id: 0, label: 1 }
).sort({ label: 1 }).collation({
  locale: "vi",
  numericOrdering: true
});
```

Kết quả mong đợi theo thứ tự số là `Bài 1`, `Bài 2`, `Bài 10`. `numericOrdering` dành cho các dãy chữ số trong chuỗi theo quy tắc được hỗ trợ; không nên hiểu nó như bộ parse mọi định dạng số âm, số thập phân hoặc mã phiên bản phức tạp.

## 7. Collation của collection, truy vấn và index

### 7.1. Collation được chọn ở đâu?

MongoDB cho phép chỉ định collation ở nhiều phạm vi:

1. **Collection default collation:** thiết lập khi tạo collection; dùng làm mặc định cho các thao tác hỗ trợ collation nếu không chỉ định khác.
2. **Operation collation:** đưa vào từng lệnh `find`, `sort`, `aggregate` và một số thao tác khác khi cần quy tắc riêng.
3. **Index collation:** quy tắc của một index trên trường string, ảnh hưởng đến khả năng sử dụng index cho phép so sánh/sắp xếp.

Nếu collection không có default collation riêng, so sánh string mặc định thường theo `simple`. Khi một truy vấn muốn so sánh theo locale, nên khai báo rõ collation và bảo đảm index phục vụ truy vấn có cấu hình phù hợp.

Ví dụ tạo collection có default collation cho dữ liệu **thử nghiệm mới**:

```javascript
lab.createCollection("contacts_demo", {
  collation: {
    locale: "vi",
    strength: 2
  }
});
```

Collection mới này nhận collation mặc định đã nêu. Không dùng `createCollection` với tên trùng collection hiện có; nếu dự án cần thay đổi mặc định hoặc chuyển schema, hãy thiết kế kế hoạch migration riêng.

### 7.2. Tạo index khớp với phép so sánh

Giả sử ứng dụng liên tục tìm title bằng equality không phân biệt dấu/case theo English locale:

```javascript
articles.createIndex(
  { title: 1 },
  {
    name: "title_en_primary",
    collation: {
      locale: "en",
      strength: 1
    }
  }
);
```

Truy vấn cần cùng cấu hình collation để có thể tận dụng index phù hợp cho phần so sánh chuỗi:

```javascript
articles.find({
  title: "cafe dữ liệu"
}).collation({
  locale: "en",
  strength: 1
});
```

Nếu truy vấn dùng collation khác index, MongoDB có thể không dùng được index đó cho phép so sánh/sắp xếp string như mong đợi. Chỉ việc thấy index trên trường `title` chưa đủ; phải xem cả **collation của index và của operation**.

Đối với index trên nhiều field, một vài phần truy vấn không phải string có thể vẫn tận dụng tiền tố index trong những điều kiện nhất định, nhưng không nên mặc định index không khớp collation vẫn tối ưu được toàn bộ truy vấn. Quan sát `explain()` trên dữ liệu và query pattern thực tế.

### 7.3. Index simple và index collation có thể phục vụ hai nhu cầu

Trong bài thực hành đã có index `title_simple` (simple collation) cho nhu cầu tìm tiền tố có phân biệt case. Index `title_en_primary` phục vụ equality và sắp xếp phù hợp với English collation ở cấp primary.

Hai index này có thể cùng tồn tại trong một collection nếu tên index khác nhau và các quy tắc phiên bản hỗ trợ được thỏa mãn. Tuy nhiên, mỗi index làm tăng dung lượng và chi phí duy trì khi ghi. Ở hệ thống thật, chỉ giữ các index tương ứng với truy vấn quan trọng và lợi ích đo được.

### 7.4. Unique index và collation

Collation còn ảnh hưởng đến khái niệm **duy nhất** của chuỗi. Ví dụ, hệ thống muốn nickname không được trùng khi chỉ khác hoa/thường:

```javascript
const accounts = lab.getCollection("accounts_demo");

accounts.createIndex(
  { nickname: 1 },
  {
    unique: true,
    name: "uniq_nickname_en_secondary",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
```

Theo quy tắc này, hai giá trị `"Minh"` và `"minh"` được coi là cùng khóa unique xét về case. Nhưng `"Mính"` có khác biệt dấu có thể là khóa khác ở strength 2. Đây là quyết định về **định danh người dùng**, không chỉ là lựa chọn hiển thị.

Không nên thay đổi collation hoặc index unique trên collection dữ liệu thật mà chưa kiểm tra giá trị trùng theo quy tắc mới. Một index unique có thể không tạo được nếu collection đã chứa các document được coi là trùng dưới collation được chọn.

### 7.5. Regex không tuân theo collation như equality

Ví dụ hai biểu thức sau có ý nghĩa khác nhau:

```javascript
// Equality được so sánh theo collation.
articles.find({
  title: "cafe dữ liệu"
}).collation({
  locale: "en",
  strength: 1
});

// Regex chạy theo ngữ nghĩa regex; collation không biến regex
// thành mẫu tìm có thể bỏ dấu hoặc tìm theo chữ tương đương.
articles.find({
  title: /cafe/i
}).collation({
  locale: "en",
  strength: 1
});
```

Mẫu `/cafe/i` không tự khớp `Café` chỉ vì operation có collation cấp primary. Và chỉ mục không phân biệt case do collation tạo ra không tự tối ưu hiệu quả cho regex `i`. Đây là ranh giới quan trọng khi thiết kế API “tìm kiếm”.

## 8. Kết hợp thời gian, chuỗi và collation trong một truy vấn

### 8.1. Tìm bài trong ngày địa phương và khớp title theo collation

Ví dụ cần các bài trong **ngày 14/11 tại Việt Nam**, có tiêu đề tương đương “cafe dữ liệu” theo English collation cấp primary:

```javascript
const localDayStart = ISODate("2026-11-14T00:00:00+07:00");
const localNextDayStart = ISODate("2026-11-15T00:00:00+07:00");

articles.find(
  {
    runId,
    status: "PUBLISHED",
    publishedAt: {
      $gte: localDayStart,
      $lt: localNextDayStart
    },
    title: "cafe dữ liệu"
  },
  { _id: 0, title: 1, publishedAt: 1 }
).sort({
  publishedAt: 1
}).collation({
  locale: "en",
  strength: 1
});
```

Trong ví dụ này:

- `publishedAt` so sánh các **BSON Date**, không phải chuỗi ngày giờ.
- `title` so sánh các **string theo collation** được chọn.
- `sort({ publishedAt: 1 })` sắp xếp theo thời điểm.
- `runId` bảo đảm kết quả chỉ thuộc lượt thực hành.

Các phép so sánh Date không chuyển thành so sánh từ vựng chỉ vì truy vấn có collation. Collation chủ yếu điều chỉnh quy tắc string.

### 8.2. Tìm tiền tố, giới hạn thời gian và sắp xếp mới nhất

```javascript
articles.find(
  {
    runId,
    status: "PUBLISHED",
    publishedAt: {
      $gte: ISODate("2026-11-14T00:00:00+07:00"),
      $lt: ISODate("2026-11-15T00:00:00+07:00")
    },
    title: /^MongoDB/
  },
  { _id: 0, title: 1, publishedAt: 1 }
).sort({
  publishedAt: -1
});
```

Do regex phân biệt chữ hoa/thường theo mặc định, mẫu này không tự bao gồm `mongodb cho người mới` hoặc `MONGODB nâng cao`. Nếu cần không phân biệt case, hãy chủ động đổi yêu cầu sang regex `i` hoặc thiết kế cơ chế tìm kiếm khác; đánh giá lại cách index có thể phục vụ truy vấn.

### 8.3. Chọn index theo truy vấn thực tế

Với ứng dụng thường lọc bài theo trạng thái và khoảng ngày rồi sắp xếp theo ngày mới nhất:

```javascript
articles.createIndex(
  { status: 1, publishedAt: -1 },
  { name: "status_publishedAt_desc" }
);
```

Nếu thường lọc chính xác theo title với một collation cụ thể và chỉ lấy bản ghi mới nhất, cần cân nhắc **index ghép** tương ứng với pattern thực tế, ví dụ:

```javascript
articles.createIndex(
  { title: 1, publishedAt: -1 },
  {
    name: "title_en_primary_publishedAt",
    collation: {
      locale: "en",
      strength: 1
    }
  }
);
```

Quyết định index cần dựa trên điều kiện equality, điều kiện range, sort, độ chọn lọc, tần suất đọc/ghi và dữ liệu đại diện. Không nhất thiết giữ tất cả index minh họa trong sản phẩm thật. Kiểm tra bằng `explain("executionStats")` sau khi có dữ liệu đủ lớn để việc đo có ý nghĩa.

## 9. Aggregation: trích xuất, định dạng và nhóm theo ngày

Truy vấn `find` thích hợp khi ứng dụng cần các document thỏa điều kiện. Aggregation pipeline hữu ích khi cần báo cáo theo ngày, chuyển định dạng hoặc tạo trường kết quả dẫn xuất.

### 9.1. Hiển thị thời gian theo múi giờ

```javascript
articles.aggregate([
  { $match: { runId } },
  {
    $project: {
      _id: 0,
      title: 1,
      publishedAt: 1,
      publishedAtVietnam: {
        $dateToString: {
          format: "%Y-%m-%d %H:%M:%S",
          date: "$publishedAt",
          timezone: "Asia/Ho_Chi_Minh",
          onNull: null
        }
      }
    }
  },
  { $sort: { publishedAt: 1 } }
]);
```

`publishedAtVietnam` là **chuỗi phục vụ hiển thị**. Trường `publishedAt` gốc vẫn là BSON Date. Dùng tên múi giờ IANA giúp phép định dạng theo quy tắc của vùng, thay vì chỉ ghép thêm hậu tố `+07:00` lên một thời gian đã ở UTC.

### 9.2. Nhóm bài theo ngày Việt Nam với `$dateTrunc`

```javascript
articles.aggregate([
  { $match: { runId, status: "PUBLISHED" } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$publishedAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      articleCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      localDate: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$_id",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      articleCount: 1
    }
  }
]);
```

`$dateTrunc` với `unit: "day"` đưa mỗi instant về **đầu ngày địa phương**. Giá trị kết quả vẫn là Date, nên trong shell ranh giới `00:00` của Việt Nam có thể hiển thị thành `17:00Z` của ngày UTC trước. Bước `$dateToString` tạo nhãn ngày địa phương để đọc báo cáo.

### 9.3. Kiểm tra kiểu dữ liệu khi dữ liệu cũ bị trộn

```javascript
articles.aggregate([
  { $match: { runId } },
  {
    $group: {
      _id: { $type: "$publishedAt" },
      count: { $sum: 1 }
    }
  }
]);
```

Trong dữ liệu mẫu, `publishedAt` có kiểu `date`. Nếu kết quả thực tế có thêm `string` hoặc `missing`, cần xác định quy tắc chuyển đổi dữ liệu và schema validation trước khi viết các pipeline giả định mọi document đều có Date.

### 9.4. Các phép biến đổi chuỗi trong aggregation

MongoDB có các biểu thức xử lý string như `$toLower`, `$toUpper`, `$strLenCP` và `$regexMatch`:

```javascript
articles.aggregate([
  { $match: { runId } },
  {
    $project: {
      _id: 0,
      title: 1,
      titleLengthCodePoints: { $strLenCP: "$title" },
      startsWithMongoDBCaseInsensitive: {
        $regexMatch: {
          input: "$title",
          regex: "^mongodb",
          options: "i"
        }
      }
    }
  }
]);
```

`$strLenCP` đếm **Unicode code points**, khác với số byte UTF-8 và có thể khác số ký tự mà người dùng cảm nhận khi text chứa ký tự kết hợp. `$regexMatch` thực hiện kiểm tra theo regex trong aggregation và cũng không tự tuân thủ collation của operation.

Với `$toLower` và `$toUpper`, hãy chú ý giới hạn xử lý Unicode/locale của từng toán tử và phiên bản MongoDB. Không coi biến đổi chữ hoa/thường đơn giản là thay thế hoàn chỉnh cho so sánh ngôn ngữ bằng collation.

## 10. Những tình huống dễ sai và cách xử lý

| Tình huống | Cách viết dễ sai | Hướng giải quyết |
| --- | --- | --- |
| Báo cáo ngày Việt Nam | Dùng `00:00Z` đến `00:00Z` hôm sau | Tính hai mốc theo `Asia/Ho_Chi_Minh` rồi dùng `$gte`/`$lt` |
| Bỏ sót cuối ngày | Dùng `$lte` đến `23:59:59` | Lọc khoảng nửa mở `[start, nextStart)` |
| Date lưu thành string | So sánh lexicographic và giả định tương đương thời gian | Lưu BSON Date cho instant và chuyển dữ liệu cũ có kiểm soát |
| Tìm đúng title bằng regex | Dùng `/title/i` dù cần equality | Dùng equality với collation phù hợp |
| Bỏ qua dấu khi regex | Dùng `/cafe/i` và kỳ vọng khớp `Café` | Hiểu regex không collation-aware; dùng equality/collation hoặc search theo nhu cầu |
| Regex trên input tùy ý | Ghép raw string của user vào regex | Escape metacharacters, giới hạn đầu vào và tài nguyên truy vấn |
| Phân trang sort bằng chuỗi | Sort có collation nhưng không dùng tie-breaker | Kết hợp thứ tự ổn định, ví dụ title và `_id` |
| Truy vấn index có collation khác | Index `en/strength1`, query `simple` và mong index tối ưu equality string | Khớp collation operation và index, kiểm tra `explain()` |
| Tạo unique index không phân biệt case trên dữ liệu cũ | Các nickname chỉ khác case đã tồn tại | Phân tích trùng lặp theo collation mới trước khi tạo |
| Dùng strength 1 cho mọi field | Mã kỹ thuật khác dấu/case có thể bị coi tương đương | Chọn collation theo ý nghĩa field; giữ simple cho định danh cần khớp nhị phân |
| Chỉ nhìn số bản ghi trả về | Không phát hiện query phải quét hàng triệu document | Đo `totalDocsExamined`, `totalKeysExamined`, thời gian và kế hoạch |

### 10.1. Dữ liệu Unicode có thể có nhiều cách biểu diễn

Một số ký tự có dấu có thể được biểu diễn thành **một code point dựng sẵn** hoặc **nhiều code point kết hợp**. Hai chuỗi có thể hiển thị giống nhau nhưng khác nhau ở mức byte. Với ID kỹ thuật và khóa lưu trữ, cần xác định quy tắc chuẩn hóa Unicode ngay ở tầng ứng dụng nếu sản phẩm yêu cầu. Với tên người hoặc tiêu đề, collation giúp so sánh theo quy tắc ngôn ngữ; cần hiểu rõ chính sách normalization và cách các hệ thống trao đổi chuỗi.

### 10.2. Stable sort khi có giá trị tương đương theo collation

Khi `strength: 1` coi hai title giống nhau, sắp xếp chỉ theo `title` có thể không đủ tạo thứ tự xác định giữa các document có khóa so sánh tương đương. Với phân trang, thêm một trường phân biệt ổn định:

```javascript
articles.find(
  { runId },
  { title: 1, publishedAt: 1 }
).sort({
  title: 1,
  _id: 1
}).collation({
  locale: "en",
  strength: 1
});
```

`_id` làm tie-breaker cho những document có title tương đương theo collation. Nếu dùng cursor pagination, cần xây dựng điều kiện tiếp tục trang phù hợp với **cùng bộ khóa sắp xếp và cùng collation**.

## 11. Thực hành quan sát truy vấn và index

### 11.1. So sánh ba câu hỏi

Chạy từng câu trên dữ liệu đã tạo:

```javascript
// A. Chính xác title "Cafe dữ liệu".
articles.find({ runId, title: "Cafe dữ liệu" });

// B. Title tương đương "cafe dữ liệu" theo English primary collation.
articles.find({
  runId,
  title: "cafe dữ liệu"
}).collation({ locale: "en", strength: 1 });

// C. Title chứa mẫu "cafe", regex ignore-case.
articles.find({
  runId,
  title: /cafe/i
});
```

Hãy quan sát sự khác nhau về ý nghĩa: A so khớp đúng string; B so sánh nguyên chuỗi theo collation; C tìm mẫu ký tự theo regex. C không mặc nhiên xử lý dấu giống B.

### 11.2. Hai truy vấn ngày có cùng dữ liệu nhưng khác định nghĩa

```javascript
// Ngày 14/11 theo UTC.
const utcDay = articles.countDocuments({
  runId,
  publishedAt: {
    $gte: ISODate("2026-11-14T00:00:00Z"),
    $lt: ISODate("2026-11-15T00:00:00Z")
  }
});

// Ngày 14/11 theo giờ Việt Nam.
const vietnamDay = articles.countDocuments({
  runId,
  publishedAt: {
    $gte: ISODate("2026-11-14T00:00:00+07:00"),
    $lt: ISODate("2026-11-15T00:00:00+07:00")
  }
});

printjson({ utcDay, vietnamDay });
```

Các giá trị đếm có thể khác nhau dù cả hai truy vấn đều đúng về cú pháp; nguyên nhân là **ngày được định nghĩa theo hai múi giờ khác nhau**. Việc chọn mốc phải xuất phát từ yêu cầu nghiệp vụ.

### 11.3. Quan sát `explain()`

```javascript
const stats = articles.find({
  title: "cafe dữ liệu"
}).collation({
  locale: "en",
  strength: 1
}).explain("executionStats");

printjson(stats);
```

Các chỉ số nên hiểu:

- `nReturned`: số document truy vấn trả về.
- `totalDocsExamined`: số document được kiểm tra.
- `totalKeysExamined`: số khóa index được quét.
- `winningPlan`: kế hoạch thực thi mà optimizer chọn.

Tỷ lệ tốt/xấu không thể kết luận chỉ từ một vài document thử nghiệm; phải xem quy mô dữ liệu, mẫu query, index đang có và mức chi phí chấp nhận được của sản phẩm.

### 11.4. Dọn dữ liệu của lượt thực hành

Trước khi xóa, kiểm tra đúng database và `runId`, xem trước document phù hợp:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);
print("articles=" + articles.countDocuments({ runId }));
print("labels=" + labels.countDocuments({ runId }));

printjson(
  articles.find(
    { runId },
    { _id: 1, title: 1, runId: 1 }
  ).toArray()
);

printjson(
  labels.find(
    { runId },
    { _id: 1, label: 1, runId: 1 }
  ).toArray()
);
```

Nếu cả hai tập kết quả đúng là dữ liệu bạn tạo trong môi trường thử nghiệm, có thể xóa theo chính `runId` đã xác nhận:

```javascript
printjson(articles.deleteMany({ runId }));
printjson(labels.deleteMany({ runId }));

print("remaining articles=" + articles.countDocuments({ runId }));
print("remaining labels=" + labels.countDocuments({ runId }));
```

Các lệnh xóa trên **không** xóa document có `runId` khác. Chúng cũng **không xóa các index đã tạo** hoặc hai collection `contacts_demo` và `accounts_demo`. Với database riêng chỉ phục vụ bài tập, có thể quản lý tài nguyên còn lại theo quy trình của môi trường; không dùng `dropDatabase()` hoặc `deleteMany({})` trên database chia sẻ để dọn nhanh.

## 12. Câu hỏi ôn tập và bài tập mở rộng

1. Vì sao truy vấn `publishedAt: ISODate("2026-11-14")` không tương đương “mọi bài đăng ngày 14/11”?
2. Ngày 14/11/2026 theo giờ Việt Nam có điểm bắt đầu và kết thúc UTC là gì? Nếu áp dụng vùng có DST, vì sao không luôn lấy mốc đầu cộng 24 giờ?
3. Khi nào nên dùng `title: "MongoDB nhập môn"`, khi nào dùng `title: /^MongoDB/`, và khi nào dùng equality kèm collation?
4. `/^mongodb/i` có dùng các quy tắc so sánh không dấu của `collation({ locale: "en", strength: 1 })` hay không?
5. Sự khác biệt giữa `strength: 1`, `strength: 2` và `strength: 3` trong collation là gì?
6. Vì sao tạo index trên `title` chưa đủ để đảm bảo truy vấn có collation bất kỳ sẽ dùng được index đó?
7. Một unique index trên nickname với collation không phân biệt case sẽ xử lý `"Minh"` và `"minh"` như thế nào?
8. Khi người dùng muốn “tìm mọi tiêu đề chứa cụm từ bất kỳ, bỏ dấu, xếp theo mức độ liên quan”, vì sao regex đơn giản hoặc equality kèm collation có thể chưa đáp ứng đầy đủ?
9. Tại sao nên thêm `_id` làm tie-breaker khi phân trang dữ liệu đã sort theo title với collation?
10. Làm thế nào để phát hiện một trường `publishedAt` chứa cả string và Date trước khi triển khai báo cáo thời gian?

Một thiết kế truy vấn đáng tin bắt đầu từ **ý nghĩa dữ liệu**: Date đại diện thời điểm, ngày báo cáo luôn gắn với múi giờ, equality khác tìm kiếm mẫu, và collation định nghĩa cách string được so sánh. Từ những lựa chọn đó mới xây dựng điều kiện lọc, sắp xếp và index phù hợp với ứng dụng.
