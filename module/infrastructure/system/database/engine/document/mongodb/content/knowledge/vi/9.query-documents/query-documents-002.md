# So sánh giá trị với $eq, $ne, $gt, $gte, $lt và $lte trong MongoDB

Khi truy vấn document trong MongoDB, một trong những công việc thường gặp nhất là **so sánh giá trị của trường với một giá trị tham chiếu**: tìm sản phẩm có giá từ 20 đến dưới 50, tìm tồn kho bằng 0, lọc đơn hàng không ở trạng thái CANCELLED, hoặc lấy những sự kiện xảy ra trong một khoảng thời gian. MongoDB cung cấp sáu toán tử so sánh cơ bản trong bộ lọc truy vấn:

- **$eq**: bằng.
- **$ne**: không bằng.
- **$gt**: lớn hơn.
- **$gte**: lớn hơn hoặc bằng.
- **$lt**: nhỏ hơn.
- **$lte**: nhỏ hơn hoặc bằng.

Các toán tử này xuất hiện trong điều kiện của **find()**, **findOne()**, **countDocuments()**, **updateOne()**, **updateMany()**, **deleteMany()** và nhiều thao tác khác có tham số filter. Kết quả phụ thuộc vào **giá trị và kiểu BSON** thực sự đang lưu, trạng thái trường có tồn tại hay không, và cách MongoDB xử lý mảng.

Bài học đi từ cú pháp cơ bản, dữ liệu mẫu và kết quả cụ thể đến những tình huống dễ nhầm như **null so với trường thiếu**, **String so với Number**, **nhiều điều kiện trên cùng một trường**, **mảng nhiều phần tử**, **Date**, **collation** và khả năng tận dụng index. Các ví dụ sử dụng mongosh và có phần chuyển sang Java MongoDB Driver/Spring Data MongoDB.

## 1. Cú pháp bộ lọc so sánh

Một truy vấn MongoDB thường có dạng:

~~~javascript
db.collection.find(
  { field: { $operator: value } },
  { fieldToReturn: 1 }
)
~~~

Trong đó:

| Thành phần | Ý nghĩa |
|---|---|
| db.collection | Collection cần truy vấn |
| field | Tên trường cần kiểm tra; có thể dùng đường dẫn dạng dấu chấm cho trường lồng nhau |
| $operator | Một trong sáu toán tử so sánh |
| value | Giá trị tham chiếu được so sánh với field |
| Đối số thứ hai của find | Projection, quyết định trường nào được trả về; có thể bỏ qua |

Ví dụ tìm sản phẩm có giá lớn hơn 100:

~~~javascript
db.products.find({
  price: { $gt: 100 }
})
~~~

MongoDB kiểm tra điều kiện **price > 100** với những document có giá trị thuộc nhóm kiểu BSON có thể so sánh theo quy tắc truy vấn. Kết quả trả về là các document phù hợp, không phải một giá trị true/false cho cả collection.

### 1.1. Bằng nhau có thể viết tắt

Hai câu truy vấn sau có cùng mục đích đối với một giá trị chuỗi đơn giản:

~~~javascript
db.products.find({
  status: "ACTIVE"
})

db.products.find({
  status: { $eq: "ACTIVE" }
})
~~~

MongoDB hỗ trợ cú pháp **đối chiếu trực tiếp** cho phép bằng, vì vậy khi chỉ cần so sánh bằng với một giá trị đơn giản, viết **status: "ACTIVE"** thường gọn hơn.

Cú pháp tường minh **$eq** đặc biệt hữu ích khi giải thích toán tử, tạo filter động, hoặc muốn đặt code thống nhất với những toán tử so sánh khác.

### 1.2. So sánh không giống gán giá trị

Trong filter:

~~~javascript
{ stock: { $gte: 10 } }
~~~

Đây là biểu thức **đọc và kiểm tra điều kiện**, không thay đổi stock. Muốn cập nhật dữ liệu, ứng dụng cần một thao tác update kèm toán tử cập nhật như **$set**, **$inc**. Cần phân biệt toán tử truy vấn với toán tử thay đổi document dù cả hai đều bắt đầu bằng dấu đô la.

## 2. Dữ liệu mẫu thống nhất để thực hành

Các ví dụ bên dưới dùng database riêng **comparison_lab** và collection **comparisonProducts**. Hãy chạy lệnh một lần trong mongosh với một database thử nghiệm còn trống:

~~~javascript
use comparison_lab

db.comparisonProducts.insertMany([
  {
    _id: "P01",
    name: "Notebook",
    category: "stationery",
    price: NumberDecimal("20.00"),
    stock: NumberInt(0),
    rating: 4.2,
    tags: ["paper", "school"],
    createdAt: ISODate("2026-11-10T08:00:00Z")
  },
  {
    _id: "P02",
    name: "Pen",
    category: "stationery",
    price: NumberDecimal("5.00"),
    stock: NumberInt(35),
    rating: 4.8,
    tags: ["office", "blue"],
    createdAt: ISODate("2026-11-11T08:00:00Z")
  },
  {
    _id: "P03",
    name: "Mouse",
    category: "electronics",
    price: NumberDecimal("25.00"),
    stock: NumberInt(12),
    rating: 4.5,
    tags: ["desk", "usb"],
    createdAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: "P04",
    name: "Keyboard",
    category: "electronics",
    price: NumberDecimal("55.00"),
    stock: NumberInt(7),
    rating: 3.9,
    tags: ["desk", "usb"],
    createdAt: ISODate("2026-11-13T08:00:00Z")
  },
  {
    _id: "P05",
    name: "Desk Lamp",
    category: "home",
    price: NumberDecimal("30.00"),
    stock: NumberInt(2),
    rating: 4.1,
    tags: ["desk", "lighting"],
    createdAt: ISODate("2026-11-14T08:00:00Z")
  },
  {
    _id: "P06",
    name: "Old Book",
    category: "stationery",
    price: NumberDecimal("12.00"),
    stock: NumberInt(3),
    rating: null,
    tags: ["paper"],
    createdAt: ISODate("2026-11-15T08:00:00Z")
  },
  {
    _id: "P07",
    name: "Scratch Pad",
    category: "stationery",
    price: NumberDecimal("9.00"),
    stock: NumberInt(1),
    tags: ["paper", "school"],
    createdAt: ISODate("2026-11-16T08:00:00Z")
  }
])
~~~

**P06** có trường rating với giá trị **null**; **P07 không có trường rating**. Sự khác biệt có chủ đích này giúp minh họa $eq và $ne với null.

Trường **price** được tạo bằng **NumberDecimal()** để lưu BSON Decimal128, **stock** dùng BSON Int32, **createdAt** là BSON Date, còn **tags** là array. Việc chọn kiểu rõ ràng giúp tránh ngộ nhận một chuỗi số hay một chuỗi ngày sẽ tự được MongoDB ép kiểu.

Bảng nhìn nhanh:

| _id | name | price | stock | rating | category |
|---|---|---:|---:|---:|---|
| P01 | Notebook | 20.00 | 0 | 4.2 | stationery |
| P02 | Pen | 5.00 | 35 | 4.8 | stationery |
| P03 | Mouse | 25.00 | 12 | 4.5 | electronics |
| P04 | Keyboard | 55.00 | 7 | 3.9 | electronics |
| P05 | Desk Lamp | 30.00 | 2 | 4.1 | home |
| P06 | Old Book | 12.00 | 3 | null | stationery |
| P07 | Scratch Pad | 9.00 | 1 | *không có trường* | stationery |

Nếu muốn kết quả truy vấn trình bày ngắn và theo thứ tự cố định trong bài thực hành:

~~~javascript
db.comparisonProducts
  .find(
    { stock: { $gt: 0 } },
    { _id: 1, name: 1, stock: 1 }
  )
  .sort({ _id: 1 })
~~~

**Projection** giúp chọn trường hiển thị, còn **sort()** quyết định thứ tự kết quả. Không nên suy ra thứ tự mặc định của find() luôn là thứ tự chèn.

## 3. $eq: bằng một giá trị

Toán tử **$eq** chọn các document có giá trị trường bằng với giá trị được yêu cầu theo ngữ nghĩa so sánh của MongoDB.

### 3.1. Bằng chuỗi

~~~javascript
db.comparisonProducts.find({
  category: { $eq: "electronics" }
})
~~~

Kết quả theo dữ liệu mẫu: **P03 (Mouse)** và **P04 (Keyboard)**.

Cú pháp rút gọn tương đương:

~~~javascript
db.comparisonProducts.find({
  category: "electronics"
})
~~~

Tên trường và kiểu dữ liệu cần đúng. Document có category là chuỗi "electronics" khác document có category là một object hay array không tương ứng.

### 3.2. Bằng số

~~~javascript
db.comparisonProducts.find({
  stock: { $eq: NumberInt(0) }
})
~~~

Kết quả: **P01 (Notebook)**. Có thể viết:

~~~javascript
db.comparisonProducts.find({ stock: 0 })
~~~

Đối với các kiểu số BSON, MongoDB có ngữ nghĩa so sánh số cho phép so sánh qua một số kiểu số khác nhau, chẳng hạn Int32, Int64, Double và Decimal128 khi giá trị số tương ứng. Tuy nhiên, **BSON String "0" không bằng BSON Number 0**.

Nếu hệ thống lưu tiền hoặc số lớn cần độ chính xác, hãy dùng kiểu phù hợp nhất ở cả phần ghi và phần so sánh thay vì dựa vào việc chuyển đổi ngầm từ String.

### 3.3. Bằng Decimal128

~~~javascript
db.comparisonProducts.find({
  price: { $eq: NumberDecimal("25.00") }
})
~~~

Kết quả: **P03 (Mouse)**. Câu này không tìm các document có price bằng chuỗi "25.00"; đó là một loại giá trị khác.

**Lưu ý với tiền:** Dùng Decimal128 một cách nhất quán giúp tránh các bất ngờ khi chuyển một giá trị thập phân qua Double. Nếu ứng dụng Java dùng BigDecimal, hãy cấu hình mapping/codec sang Decimal128 phù hợp với schema.

### 3.4. Bằng Date và ObjectId

Ví dụ trường BSON Date:

~~~javascript
db.comparisonProducts.find({
  createdAt: {
    $eq: ISODate("2026-11-12T08:00:00Z")
  }
})
~~~

Kết quả: **P03 (Mouse)**.

Nếu một collection khác có **_id** là ObjectId:

~~~javascript
db.customers.find({
  _id: {
    $eq: ObjectId("66f1c2a4b1d2e3f405162738")
  }
})
~~~

Giá trị ObjectId không tự bằng chuỗi hex tương ứng. Tương tự, Date không tự bằng một String có hình thức ISO-8601. MongoDB so sánh giá trị BSON, không suy luận kiểu từ hình thức của chuỗi.

## 4. $ne: khác một giá trị

Toán tử **$ne** chọn document có trường **không bằng** giá trị tham chiếu. Một chi tiết rất quan trọng: **$ne thường cũng khớp document không chứa trường đang kiểm tra**.

### 4.1. Khác chuỗi

~~~javascript
db.comparisonProducts.find({
  category: { $ne: "electronics" }
})
~~~

Kết quả: **P01, P02, P05, P06, P07**. Chỉ P03 và P04 bị loại, vì chúng có category bằng "electronics".

Nếu document không có trường category, nó cũng thường được chọn bởi điều kiện **category: { $ne: "electronics" }**, bởi vì nó không chứa giá trị bằng "electronics".

### 4.2. Khác số

~~~javascript
db.comparisonProducts.find({
  stock: { $ne: NumberInt(0) }
})
~~~

Kết quả trên bộ dữ liệu mẫu: **P02 đến P07**, vì chỉ P01 có stock bằng 0.

Trong nghiệp vụ, "stock khác 0" không nhất thiết đồng nghĩa "còn hàng": stock âm, null hoặc trường không tồn tại đều cần được định nghĩa cách xử lý. Nếu muốn hàng tồn kho dương, nên dùng **$gt: 0** thay vì dùng **$ne: 0**.

### 4.3. Trường không tồn tại: khác biệt quan trọng

Thử:

~~~javascript
db.comparisonProducts.find(
  { rating: { $ne: 4.8 } },
  { _id: 1, rating: 1 }
).sort({ _id: 1 })
~~~

Kết quả gồm **P01, P03, P04, P05, P06 và P07**. P02 bị loại vì rating bằng 4.8.

P06 có rating là null và P07 không chứa rating, nhưng cả hai vẫn được chọn khi so sánh khác 4.8.

Để chỉ xét các document **có trường rating** và khác 4.8:

~~~javascript
db.comparisonProducts.find({
  rating: {
    $ne: 4.8,
    $exists: true
  }
})
~~~

Kết quả: **P01, P03, P04, P05 và P06**. P07 bị loại vì không có trường rating. **P06 vẫn được chọn** vì null khác 4.8.

Muốn loại cả null và trường thiếu, điều kiện **$ne: null** có ý nghĩa đặc biệt, trình bày ở phần tiếp theo.

### 4.4. $ne có thể không chọn lọc tốt

Một điều kiện như **status != "CANCELLED"** có thể khớp phần lớn collection. Khi đó truy vấn phải đọc rất nhiều document và index chưa chắc đem lại cải thiện đáng kể.

Nếu nghiệp vụ chỉ cần các trạng thái cụ thể như NEW và PAID, đôi khi điều kiện **$in** với danh sách trạng thái hợp lệ rõ ràng sẽ dễ hiểu và có tính chọn lọc hơn. Tuy nhiên, không được thay đổi ngữ nghĩa: tập trạng thái được liệt kê cần đúng với quy tắc nghiệp vụ, và vấn đề có hay không có field phải được xử lý có chủ đích.

## 5. $gt: lớn hơn nghiêm ngặt

**$gt** là viết tắt của *greater than*. Nó yêu cầu giá trị trường **lớn hơn** giá trị so sánh; trường hợp bằng bị loại.

### 5.1. So sánh giá

~~~javascript
db.comparisonProducts.find({
  price: {
    $gt: NumberDecimal("25.00")
  }
})
~~~

Kết quả: **P04 (55.00)** và **P05 (30.00)**. **P03 (25.00)** không được chọn vì bằng ngưỡng, không lớn hơn.

### 5.2. Tìm hàng còn tồn kho

~~~javascript
db.comparisonProducts.find({
  stock: { $gt: 0 }
})
~~~

Kết quả: **P02, P03, P04, P05, P06, P07**. P01 stock bằng 0 nên bị loại.

Đây là ví dụ dùng **$gt** phù hợp hơn **$ne**: nghiệp vụ "còn hàng" thường yêu cầu **stock dương** chứ không chỉ "khác 0".

### 5.3. So sánh với Date

~~~javascript
db.comparisonProducts.find({
  createdAt: {
    $gt: ISODate("2026-11-13T08:00:00Z")
  }
})
~~~

Kết quả: **P05, P06, P07**. P04 có createdAt bằng chính xác mốc đưa vào nên không được chọn.

Date trong MongoDB biểu diễn thời điểm. Nếu muốn truy vấn từ **đầu ngày** thay vì từ đúng 08:00:00 UTC, hãy chọn mốc đầu ngày và chỉ rõ múi giờ/ngữ nghĩa nghiệp vụ tương ứng.

## 6. $gte: lớn hơn hoặc bằng

**$gte** là viết tắt của *greater than or equal*. Khác biệt với $gt nằm ở dấu **bằng**.

~~~javascript
db.comparisonProducts.find({
  price: {
    $gte: NumberDecimal("25.00")
  }
})
~~~

Kết quả: **P03 (25.00), P04 (55.00) và P05 (30.00)**.

So sánh với $gt ở phần trước:

| Toán tử | Điều kiện toán học | Giá bằng 25.00 được chọn? |
|---|---|---|
| $gt: 25 | price > 25 | Không |
| $gte: 25 | price ≥ 25 | Có |

Ví dụ khác, tìm sản phẩm có tồn kho ít nhất 10:

~~~javascript
db.comparisonProducts.find({
  stock: { $gte: 10 }
})
~~~

Kết quả: **P02 (35)** và **P03 (12)**.

Trong yêu cầu nghiệp vụ, các cụm từ **"ít nhất"**, **"từ ... trở lên"**, **"không nhỏ hơn"** thường tương ứng $gte. Cần kiểm tra xem mốc chính xác có được chấp nhận hay không trước khi chọn toán tử.

## 7. $lt: nhỏ hơn nghiêm ngặt

**$lt** là viết tắt của *less than*. Nó chọn giá trị **nhỏ hơn**, không nhận trường hợp bằng.

~~~javascript
db.comparisonProducts.find({
  price: {
    $lt: NumberDecimal("12.00")
  }
})
~~~

Kết quả: **P02 (5.00)** và **P07 (9.00)**. P06 có giá đúng 12.00 nên bị loại.

Ví dụ tìm những sản phẩm có tồn kho dưới 3:

~~~javascript
db.comparisonProducts.find({
  stock: { $lt: 3 }
})
~~~

Kết quả: **P01 (0), P05 (2), P07 (1)**.

Lưu ý: một điều kiện **stock < 3** có thể bao gồm cả stock âm nếu dữ liệu có số âm. Nếu chỉ muốn tập các số từ 0 đến 2, cần kết hợp thêm $gte: 0.

## 8. $lte: nhỏ hơn hoặc bằng

**$lte** là viết tắt của *less than or equal*. Nó bao gồm cả giá trị tại ngưỡng.

~~~javascript
db.comparisonProducts.find({
  price: {
    $lte: NumberDecimal("12.00")
  }
})
~~~

Kết quả: **P02 (5.00), P06 (12.00) và P07 (9.00)**.

So với $lt:

| Toán tử | Điều kiện toán học | Giá bằng 12.00 được chọn? |
|---|---|---|
| $lt: 12 | price < 12 | Không |
| $lte: 12 | price ≤ 12 | Có |

Ví dụ sản phẩm có tồn kho nhiều nhất 2:

~~~javascript
db.comparisonProducts.find({
  stock: { $lte: 2 }
})
~~~

Kết quả: **P01, P05, P07**.

Những cụm từ **"tối đa"**, **"không vượt quá"**, **"đến ... bao gồm"** thường tương ứng với $lte.

## 9. Bảng kết quả của sáu toán tử

Áp dụng lên dữ liệu mẫu:

| Filter | Ý nghĩa | _id dự kiến |
|---|---|---|
| { stock: { $eq: 0 } } | Tồn kho bằng 0 | P01 |
| { category: { $ne: "electronics" } } | Không thuộc electronics | P01, P02, P05, P06, P07 |
| { price: { $gt: NumberDecimal("25") } } | Giá trên 25 | P04, P05 |
| { price: { $gte: NumberDecimal("25") } } | Giá từ 25 trở lên | P03, P04, P05 |
| { price: { $lt: NumberDecimal("12") } } | Giá dưới 12 | P02, P07 |
| { price: { $lte: NumberDecimal("12") } } | Giá không quá 12 | P02, P06, P07 |

Có thể ghi nhớ qua một trục số:

~~~text
                       Ngưỡng = 25
      5        12      20      25      30          55
      |--------|-------|-------|-------|-----------|
                                ^
                    $gt 25:     chỉ bên phải
                    $gte 25:    cả 25 và bên phải
                    $lt 25:     chỉ bên trái
                    $lte 25:    cả 25 và bên trái
                    $eq 25:     đúng điểm 25
                    $ne 25:     các giá trị khác 25
~~~

Sơ đồ mô tả ngữ nghĩa trên trục số. Đối với BSON, các giá trị phải được so sánh trong ngữ cảnh kiểu dữ liệu và quy tắc của MongoDB; không thể lấy một biểu đồ số để suy luận toàn bộ so sánh giữa String, ObjectId, Date và Null.

## 10. Ghép nhiều toán tử trên cùng một trường

Một nhu cầu rất phổ biến là lọc giá trị **trong một khoảng**. Ta đặt nhiều toán tử trong object của cùng field:

~~~javascript
db.comparisonProducts.find({
  price: {
    $gte: NumberDecimal("12.00"),
    $lt: NumberDecimal("30.00")
  }
})
~~~

Điều kiện có nghĩa:

\[
12 \leq price < 30
\]

Kết quả: **P01 (20.00), P03 (25.00), P06 (12.00)**. P05 có giá bằng 30.00 nên không thuộc khoảng.

### 10.1. Các loại khoảng cơ bản

| Khoảng | Cú pháp | Hai biên |
|---|---|---|
| (a, b) | { $gt: a, $lt: b } | Không gồm a, b |
| [a, b] | { $gte: a, $lte: b } | Gồm cả a, b |
| [a, b) | { $gte: a, $lt: b } | Gồm a, không gồm b |
| (a, b] | { $gt: a, $lte: b } | Không gồm a, gồm b |

Đối với truy vấn theo thời gian, **khoảng nửa mở [start, end)** thường đặc biệt hữu ích. Nó giúp ghép các khoảng liên tiếp mà không đếm trùng một thời điểm ở ranh giới:

~~~text
Ngày 1: [00:00 ngày 1, 00:00 ngày 2)
Ngày 2: [00:00 ngày 2, 00:00 ngày 3)
~~~

### 10.2. Sai lầm khi khai báo trùng khóa field

Không nên viết:

~~~javascript
// Sai: cùng một object JavaScript khai báo price hai lần.
{
  price: { $gte: 12 },
  price: { $lt: 30 }
}
~~~

Trong một object JavaScript, việc khai báo trùng tên property có thể khiến giá trị sau ghi đè giá trị trước. Kết quả chỉ còn một vế điều kiện và dễ gây lỗi âm thầm.

Viết đúng bằng cách **đặt cả hai toán tử trong cùng object**:

~~~javascript
{
  price: {
    $gte: NumberDecimal("12.00"),
    $lt: NumberDecimal("30.00")
  }
}
~~~

### 10.3. Dùng $ne cùng các toán tử phạm vi

Ví dụ chỉ lấy stock lớn hơn 0 nhưng khác 2:

~~~javascript
db.comparisonProducts.find({
  stock: {
    $gt: 0,
    $ne: 2
  }
})
~~~

Kết quả: **P02, P03, P04, P06, P07**. P01 bị loại vì bằng 0, P05 bị loại vì bằng 2.

Các điều kiện trên **một giá trị vô hướng** phải cùng được thỏa. Với trường kiểu array, việc áp dụng nhiều toán tử có thêm quy tắc phần tử sẽ được giải thích ở phần về mảng.

## 11. Ghép điều kiện của nhiều trường

Trong MongoDB, nhiều điều kiện trên các field khác nhau trong cùng một filter mặc định được kết hợp theo logic **AND**.

Ví dụ:

~~~javascript
db.comparisonProducts.find({
  category: "electronics",
  price: {
    $gte: NumberDecimal("25.00"),
    $lte: NumberDecimal("55.00")
  },
  stock: { $gt: 0 }
})
~~~

Ý nghĩa:

1. category bằng "electronics";
2. price nằm trong khoảng [25.00, 55.00];
3. stock lớn hơn 0.

Kết quả: **P03 và P04**.

### 11.1. AND tường minh với $and

Có thể dùng **$and** khi cần tạo điều kiện phức tạp hoặc kết hợp những biểu thức khó viết gọn:

~~~javascript
db.comparisonProducts.find({
  $and: [
    { category: "electronics" },
    { price: { $gte: NumberDecimal("25.00") } },
    { stock: { $gt: 0 } }
  ]
})
~~~

Với dữ liệu mẫu, kết quả vẫn là **P03 và P04**. Trong các trường hợp đơn giản, viết các field cạnh nhau thường dễ đọc hơn dùng $and.

### 11.2. OR với $or

Giả sử muốn sản phẩm **đã hết hàng** hoặc **giá từ 50 trở lên**:

~~~javascript
db.comparisonProducts.find({
  $or: [
    { stock: { $eq: 0 } },
    { price: { $gte: NumberDecimal("50.00") } }
  ]
})
~~~

Kết quả: **P01 (stock = 0)** và **P04 (price = 55.00)**.

Đừng viết nhiều điều kiện trên các field khác nhau rồi kỳ vọng MongoDB hiểu là OR; mặc định chúng được kết hợp bằng AND.

### 11.3. So sánh với $in và $nin

Khi cần so sánh với **nhiều giá trị rời rạc**, toán tử $in và $nin thường phù hợp hơn:

~~~javascript
db.comparisonProducts.find({
  category: { $in: ["electronics", "home"] }
})
~~~

Kết quả: **P03, P04, P05**.

$eq chỉ kiểm tra một giá trị tại một lần so sánh; $in phù hợp với tập giá trị được cho phép. $ne là "khác một giá trị", còn $nin là "không thuộc một danh sách". Giống $ne, $nin cũng có những chú ý riêng với field thiếu, nên phải xác định rõ semantics khi thiết kế filter.

## 12. Null và trường thiếu: cách xử lý đặc biệt của $eq, $ne

Trong document MongoDB, ba trạng thái sau khác nhau:

~~~javascript
{ rating: 4.5 }
{ rating: null }
{ /* không có trường rating */ }
~~~

**null** là một giá trị BSON được lưu. Trường thiếu nghĩa là key không tồn tại trong document.

### 12.1. $eq: null chọn cả null lẫn missing

Truy vấn:

~~~javascript
db.comparisonProducts.find({
  rating: { $eq: null }
})
~~~

Kết quả: **P06 và P07**.

Ở đây:

- **P06** có rating: null.
- **P07** không chứa trường rating.

MongoDB có quy tắc đặc biệt: **điều kiện bằng null** khớp cả field có giá trị null và field không tồn tại. Cú pháp rút gọn:

~~~javascript
db.comparisonProducts.find({ rating: null })
~~~

cũng mang ý nghĩa này.

### 12.2. $ne: null chọn các field tồn tại và khác null

Truy vấn:

~~~javascript
db.comparisonProducts.find({
  rating: { $ne: null }
})
~~~

Kết quả: **P01, P02, P03, P04, P05**.

Điểm này cần ghi nhớ cùng với quy tắc chung của $ne: **$ne: null** có ngữ nghĩa riêng để chọn các document có field tồn tại và giá trị không phải null; không chọn P06 và P07.

### 12.3. Kết hợp với $exists để phân biệt rõ

| Mục tiêu | Filter | Kết quả mẫu |
|---|---|---|
| Rating bằng null **hoặc không có field** | { rating: null } | P06, P07 |
| Rating không phải null, field phải tồn tại | { rating: { $ne: null } } | P01–P05 |
| Có trường rating, bao gồm cả null | { rating: { $exists: true } } | P01–P06 |
| Không có trường rating | { rating: { $exists: false } } | P07 |
| Rating khác 4.8, gồm cả thiếu trường | { rating: { $ne: 4.8 } } | P01, P03–P07 |
| Rating khác 4.8 **và có field** | { rating: { $ne: 4.8, $exists: true } } | P01, P03–P06 |

Trong code thực tế, hãy viết điều kiện theo câu hỏi nghiệp vụ: **"không có đánh giá"**, **"đánh giá chưa được nhập"**, **"đánh giá đã có và khác 4.8"** có thể là ba yêu cầu khác nhau.

### 12.4. Đừng tự suy ra thứ tự của null khi lọc phạm vi

Không nên sử dụng $gt/$gte/$lt/$lte với ngưỡng null như một cách diễn đạt mơ hồ cho "có dữ liệu". Các phép so sánh phạm vi chịu quy tắc **type bracketing** và hành vi riêng của BSON. Nếu muốn kiểm tra field có giá trị không null, hãy dùng **$ne: null**; nếu chỉ muốn field có mặt, dùng **$exists: true**.

## 13. So sánh theo kiểu BSON: đừng nhầm chuỗi với số

MongoDB lưu giá trị theo các kiểu BSON như String, Int32, Int64, Double, Decimal128, Date, ObjectId, Boolean, Array và Object. Các phép so sánh truy vấn thường có **type bracketing**: phép so sánh chỉ thực hiện trong nhóm kiểu phù hợp, với một số ngoại lệ được định nghĩa, đặc biệt là nhóm kiểu số.

Ví dụ dữ liệu:

~~~javascript
db.typeExamples.insertMany([
  { _id: "T01", amount: NumberInt(20) },
  { _id: "T02", amount: NumberLong("20") },
  { _id: "T03", amount: NumberDecimal("20.00") },
  { _id: "T04", amount: NumberDouble("20.0") },
  { _id: "T05", amount: "20" },
  { _id: "T06", amount: "100" }
])
~~~

Truy vấn số:

~~~javascript
db.typeExamples.find({
  amount: { $gte: 20 }
})
~~~

Các giá trị số ở T01–T04 nằm trong nhóm so sánh số; T05 và T06 là **String**, vì vậy không nên coi chúng là số 20 hay 100 khi đánh giá filter số.

### 13.1. Ngược lại, String so sánh như String

~~~javascript
db.typeExamples.find({
  amount: { $gt: "20" }
})
~~~

Điều kiện này so sánh giá trị chuỗi theo quy tắc collation áp dụng, chứ không tự ép chuỗi thành số. **"100"** có thể được sắp trước **"20"** trong cách so sánh từ điển mặc định, dù giá trị toán học 100 lớn hơn 20.

Nếu một field phải là số, hãy lưu đồng nhất dưới dạng số BSON và thiết lập schema validation phù hợp, thay vì mong chờ toán tử truy vấn tự sửa dữ liệu sai kiểu.

### 13.2. Các kiểu số BSON khác nhau

MongoDB có các kiểu số như:

| BSON type | Đặc điểm | Ví dụ mongosh |
|---|---|---|
| Int32 | Số nguyên có dấu 32 bit | NumberInt(20) |
| Int64 | Số nguyên có dấu 64 bit | NumberLong("20") |
| Double | Số dấu phẩy động nhị phân | NumberDouble("20.0") |
| Decimal128 | Số thập phân với độ chính xác theo định dạng Decimal128 | NumberDecimal("20.00") |

Các kiểu số có thể được so sánh theo **giá trị số** trong quy tắc MongoDB, nhưng việc chuyển đổi qua JavaScript Number hoặc ứng dụng khác vẫn có nguy cơ mất chính xác với số nguyên lớn và giá trị thập phân. Với tiền, nên dùng kiểu và giá trị tham chiếu được xây dựng nhất quán, ví dụ **NumberDecimal("25.00")**.

### 13.3. Kiểm tra kiểu dữ liệu thực tế

Để quan sát kiểu BSON trong collection:

~~~javascript
db.typeExamples.aggregate([
  {
    $project: {
      amount: 1,
      amountType: { $type: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Bạn có thể thấy các kiểu như **int**, **long**, **decimal**, **double**, **string**. Đây là cách tốt để điều tra vì sao cùng nhìn "20" trên giao diện nhưng kết quả truy vấn khác nhau.

## 14. So sánh String và collation

So sánh chuỗi không chỉ có "bằng" hoặc "khác": với **$gt, $gte, $lt, $lte**, MongoDB còn cần xác định thứ tự giữa các chuỗi.

Theo cấu hình so sánh chuỗi đơn giản (simple collation), thứ tự dựa vào biểu diễn nhị phân của chuỗi. Nếu cần quy tắc ngôn ngữ, phân biệt/không phân biệt chữ hoa chữ thường, dấu hoặc cách sắp xếp, MongoDB hỗ trợ **collation**.

Ví dụ tìm tên "pen" theo cách không phân biệt chữ hoa thường:

~~~javascript
db.comparisonProducts.find({
  name: { $eq: "pen" }
}).collation({
  locale: "en",
  strength: 2
})
~~~

Với dữ liệu mẫu, truy vấn có thể khớp **P02 (Pen)** nhờ collation tiếng Anh ở mức so sánh không phân biệt chữ hoa thường.

Nếu không chỉ định collation và collection dùng simple collation, chuỗi **"Pen"** thường khác **"pen"**.

**Lưu ý khi tạo index:** Index có collation riêng. Một truy vấn dùng collation khác với index có thể không tận dụng index như mong muốn để so sánh/sắp xếp chuỗi. Vì vậy, collation cần được tính cùng chiến lược index và cách tìm kiếm của ứng dụng.

Đừng dùng các khoảng chuỗi như **name >= "A" và name < "Z"** mà mặc định chúng tương đương tìm mọi chuỗi bắt đầu từ A đến Z trong mọi ngôn ngữ. Dấu, chữ hoa/thường, Unicode và collation có thể làm quy tắc so sánh khác kỳ vọng.

## 15. So sánh trên Array: quy tắc phần tử rất dễ nhầm

Một field MongoDB có thể là array. Với điều kiện truy vấn thông thường, MongoDB có khả năng khớp array dựa trên **một hoặc nhiều phần tử của mảng**, tùy biểu thức.

### 15.1. $eq trên phần tử của Array

Trong dữ liệu mẫu, P03, P04 và P05 đều có tag **"desk"**:

~~~javascript
db.comparisonProducts.find({
  tags: { $eq: "desk" }
})
~~~

Kết quả: **P03, P04, P05**.

Điều này không yêu cầu toàn bộ array phải bằng chuỗi "desk"; chỉ cần array chứa phần tử phù hợp. Viết gọn:

~~~javascript
db.comparisonProducts.find({ tags: "desk" })
~~~

cũng dùng để kiểm tra array chứa phần tử "desk".

### 15.2. Bằng nguyên Array khác với chứa phần tử

~~~javascript
db.comparisonProducts.find({
  tags: { $eq: ["desk", "usb"] }
})
~~~

Kết quả: **P03 và P04** vì chúng lưu đúng array đó theo thứ tự đã khai báo. Đây là yêu cầu khác với tìm một phần tử.

Với so sánh nguyên array, thứ tự phần tử là quan trọng. Array **["usb", "desk"]** không phải cùng một array theo phép bằng nguyên mảng như **["desk", "usb"]**.

### 15.3. $ne với Array

~~~javascript
db.comparisonProducts.find({
  tags: { $ne: "desk" }
})
~~~

Điều kiện chọn document không có giá trị phần tử "desk" khớp điều kiện, đồng thời có thể chọn document thiếu tags. Với dữ liệu mẫu, kết quả là **P01, P02, P06, P07**.

Nếu bạn chỉ muốn document có tags nhưng không chứa "desk", kết hợp thêm **$exists: true** hoặc một điều kiện kiểu array nếu cần kiểm soát kiểu dữ liệu.

### 15.4. Các điều kiện khoảng trên Array có thể do phần tử khác nhau thỏa

Tạo dữ liệu thử:

~~~javascript
db.arrayExamples.insertMany([
  { _id: "A", scores: [40, 90] },
  { _id: "B", scores: [60, 70] },
  { _id: "C", scores: [20, 30] },
  { _id: "D", scores: [] },
  { _id: "E", scores: [85, 95] }
])
~~~

Truy vấn:

~~~javascript
db.arrayExamples.find({
  scores: {
    $gte: 80,
    $lt: 90
  }
})
~~~

Kết quả có thể gồm **A và E**:

- **A** có phần tử 90 thỏa **>= 80**, đồng thời phần tử 40 thỏa **< 90**. Hai điều kiện được thỏa bởi **hai phần tử khác nhau**.
- **E** có phần tử 85 thỏa cả hai điều kiện.

Đây là điểm rất quan trọng: khi ghép nhiều điều kiện trên một array, MongoDB không nhất thiết yêu cầu **cùng một phần tử** thỏa mọi điều kiện.

Nếu mục tiêu là **có ít nhất một phần tử nằm trong khoảng [80, 90)**, sử dụng **$elemMatch**:

~~~javascript
db.arrayExamples.find({
  scores: {
    $elemMatch: {
      $gte: 80,
      $lt: 90
    }
  }
})
~~~

Kết quả: **E**. A không được chọn vì không có **một phần tử riêng lẻ** vừa >= 80 vừa < 90.

**Ghi nhớ:** Điều kiện phạm vi trên **scalar** kiểm tra cùng một giá trị. Điều kiện phạm vi trên **array** có quy tắc khớp phần tử; dùng $elemMatch khi muốn các ràng buộc cùng áp vào một phần tử.

### 15.5. Array chứa document

Ví dụ:

~~~javascript
{
  orderId: "O-001",
  items: [
    { sku: "A", quantity: 1, price: 10 },
    { sku: "B", quantity: 5, price: 50 }
  ]
}
~~~

Muốn tìm đơn có **một item** vừa có quantity >= 3 vừa price < 60:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      quantity: { $gte: 3 },
      price: { $lt: 60 }
    }
  }
})
~~~

Không nên viết các điều kiện dấu chấm riêng rẽ rồi giả định luôn kiểm tra cùng item:

~~~javascript
// Hai điều kiện này có thể được thỏa bởi hai item khác nhau.
{
  "items.quantity": { $gte: 3 },
  "items.price": { $lt: 60 }
}
~~~

Với array các object, **$elemMatch** là cách biểu đạt rõ ràng khi điều kiện phải cùng đúng trên một phần tử.

## 16. So sánh trường lồng nhau

MongoDB hỗ trợ đường dẫn trường bằng dấu chấm, ví dụ **dimensions.width** hoặc **address.zipCode**.

Giả sử document:

~~~javascript
{
  _id: "P100",
  name: "Storage Box",
  dimensions: {
    width: 30,
    height: 20,
    depth: 15
  }
}
~~~

Truy vấn các sản phẩm có chiều rộng ít nhất 25:

~~~javascript
db.products.find({
  "dimensions.width": { $gte: 25 }
})
~~~

Truy vấn này kiểm tra giá trị field **width** bên trong **dimensions**.

### 16.1. Bằng cả embedded document

Nếu so sánh toàn bộ document lồng nhau:

~~~javascript
db.products.find({
  dimensions: {
    width: 30,
    height: 20,
    depth: 15
  }
})
~~~

MongoDB có thể yêu cầu **embedded document khớp chính xác nội dung và thứ tự các field** khi so sánh bằng toàn bộ object. Nếu chỉ cần điều kiện trên một trường con, hãy dùng đường dẫn dấu chấm thay vì so sánh cả object.

Ví dụ:

~~~javascript
db.products.find({
  "dimensions.width": { $eq: 30 }
})
~~~

Đây là cách ít phụ thuộc vào những trường con bổ sung và thứ tự key của object.

## 17. Khoảng thời gian bằng $gte và $lt

Truy vấn theo ngày là một ứng dụng quan trọng của toán tử so sánh. Nên lưu thời điểm ở **BSON Date** và so sánh với mốc Date thật.

Giả sử muốn lấy tất cả sản phẩm được tạo trong ba ngày UTC **11, 12 và 13/11/2026**:

~~~javascript
db.comparisonProducts.find({
  createdAt: {
    $gte: ISODate("2026-11-11T00:00:00Z"),
    $lt: ISODate("2026-11-14T00:00:00Z")
  }
}).sort({ createdAt: 1 })
~~~

Kết quả: **P02, P03, P04**.

### 17.1. Vì sao dùng [start, end)?

Một cách dễ mắc lỗi là dùng thời điểm cuối ngày như **23:59:59**:

~~~javascript
{
  createdAt: {
    $gte: ISODate("2026-11-11T00:00:00Z"),
    $lte: ISODate("2026-11-13T23:59:59Z")
  }
}
~~~

Cách này có thể bỏ sót những bản ghi được tạo trong phần mili giây cuối cùng, như **23:59:59.500Z**.

Để tránh phải tự xác định "mili giây cuối ngày", thường dùng mốc đầu ngày kế tiếp với **$lt**:

~~~javascript
{
  createdAt: {
    $gte: ISODate("2026-11-11T00:00:00Z"),
    $lt: ISODate("2026-11-14T00:00:00Z")
  }
}
~~~

Đây là khoảng **bao gồm đầu, không bao gồm cuối**, dễ ghép các khoảng liên tiếp và tránh đếm trùng ranh giới.

### 17.2. Múi giờ quyết định mốc so sánh

Nếu người dùng hỏi "ngày 14/11 theo giờ Việt Nam", mốc ngày địa phương bắt đầu ở **2026-11-14T00:00:00+07:00**, tương đương **2026-11-13T17:00:00Z**.

Ví dụ:

~~~javascript
db.comparisonProducts.find({
  createdAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
})
~~~

Khoảng trên biểu diễn ngày 14/11/2026 theo UTC+07:00. Trong hệ thống có múi giờ và thay đổi giờ mùa hè, nên tính ranh giới qua thư viện xử lý múi giờ chuẩn thay vì luôn cộng cứng 24 giờ.

**BSON Date lưu một thời điểm**, không lưu chuỗi tên múi giờ. Múi giờ là yếu tố để diễn giải ngày nghiệp vụ và xây dựng hai mốc Date đưa vào truy vấn.

### 17.3. Chuỗi thời gian không tự bằng Date

Document có:

~~~javascript
{ createdAt: "2026-11-14T08:00:00Z" }
~~~

không giống document có:

~~~javascript
{ createdAt: ISODate("2026-11-14T08:00:00Z") }
~~~

Vì vậy, filter Date có thể bỏ qua các record sai kiểu String. Đây là một trong những lý do nên dùng schema validation để đảm bảo createdAt là BSON Date ngay từ lúc ghi.

## 18. Dùng toán tử so sánh trong update và delete

Sáu toán tử này cũng được dùng làm **điều kiện chọn document** trước khi cập nhật hoặc xóa.

Ví dụ đánh dấu những sản phẩm có tồn kho không quá 2 là cần bổ sung hàng:

~~~javascript
db.comparisonProducts.updateMany(
  { stock: { $lte: 2 } },
  { $set: { needsRestock: true } }
)
~~~

Theo bộ dữ liệu mẫu, filter chọn **P01, P05, P07**. Phần **$lte** chỉ chọn record; phần **$set** mới thực sự thay đổi dữ liệu.

Ví dụ hủy một trạng thái xử lý quá cũ có thể viết:

~~~javascript
db.jobs.updateMany(
  {
    status: "PENDING",
    createdAt: { $lt: ISODate("2026-11-01T00:00:00Z") }
  },
  { $set: { status: "EXPIRED" } }
)
~~~

Cần có điều kiện status để tránh sửa những job đã hoàn thành trước thời hạn.

### 18.1. Đọc kiểm tra trước thao tác xóa

Một filter xóa cũng dùng chính các toán tử so sánh:

~~~javascript
// Kiểm tra phạm vi trước khi xóa ở môi trường có dữ liệu thật.
db.sessionCache.find({
  expiresAt: { $lt: new Date() }
})
~~~

Nếu nghiệp vụ thực sự cần xóa và đã xác nhận điều kiện, mới sử dụng:

~~~javascript
db.sessionCache.deleteMany({
  expiresAt: { $lt: new Date() }
})
~~~

Trong hệ thống có TTL index, việc hết hạn có thể được MongoDB xử lý bất đồng bộ theo cấu hình. Không dùng $lt như một cơ chế bảo đảm mỗi phiên sẽ được xóa ngay ở đúng mili giây hết hạn; nếu phiên ảnh hưởng bảo mật, ứng dụng vẫn cần kiểm tra điều kiện expiresAt khi xác thực.

### 18.2. Điều kiện cập nhật giúp tránh thay đổi sai trạng thái

Một cập nhật có điều kiện là cách tránh ghi đè trạng thái bất ngờ:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-001",
    status: { $eq: "NEW" },
    total: { $gte: NumberDecimal("0") }
  },
  { $set: { status: "PAID" } }
)
~~~

Filter chỉ chọn đơn hàng khi trạng thái và tổng tiền đang phù hợp. Tuy nhiên, các quy tắc thanh toán phức tạp, quyền người dùng và tính nhất quán liên document còn cần thiết kế nghiệp vụ, transaction hoặc cơ chế riêng khi phù hợp.

## 19. MongoDB Java Driver: xây dựng filter an toàn

Khi dùng Java MongoDB Sync Driver, package **com.mongodb.client.model.Filters** cung cấp các hàm tạo toán tử tương ứng, tránh phải tự xây object BSON bằng chuỗi ở mọi nơi.

Giả sử ứng dụng đã thêm dependency **mongodb-driver-sync** phù hợp và có biến môi trường **MONGODB_URI**.

### 19.1. Ghép một khoảng giá tiền

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.Decimal128;

import java.math.BigDecimal;

public class ComparePriceDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Decimal128 min = new Decimal128(new BigDecimal("12.00"));
        Decimal128 max = new Decimal128(new BigDecimal("30.00"));

        Bson filter = Filters.and(
                Filters.gte("price", min),
                Filters.lt("price", max)
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> products = client
                    .getDatabase("comparison_lab")
                    .getCollection("comparisonProducts");

            try (MongoCursor<Document> cursor = products
                    .find(filter)
                    .projection(Projections.include("_id", "name", "price"))
                    .sort(Sorts.ascending("_id"))
                    .iterator()) {

                while (cursor.hasNext()) {
                    System.out.println(cursor.next().toJson());
                }
            }
        }
    }
}
~~~

Điều kiện Java tương đương:

~~~javascript
{
  price: {
    $gte: NumberDecimal("12.00"),
    $lt: NumberDecimal("30.00")
  }
}
~~~

Với dữ liệu mẫu, kết quả là **P01, P03, P06**. Lớp **Decimal128** giúp tạo giá trị so sánh khớp với cách ứng dụng lưu giá tiền.

### 19.2. Ánh xạ đủ sáu toán tử sang Filters

~~~java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.ne;
import static com.mongodb.client.model.Filters.gt;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Filters.lt;
import static com.mongodb.client.model.Filters.lte;

// Bằng
var equalsZero = eq("stock", 0);

// Khác
var notElectronics = ne("category", "electronics");

// Lớn hơn
var greaterThanZero = gt("stock", 0);

// Lớn hơn hoặc bằng
var atLeastTen = gte("stock", 10);

// Nhỏ hơn
var belowThree = lt("stock", 3);

// Nhỏ hơn hoặc bằng
var atMostTwo = lte("stock", 2);
~~~

Các biến trên đều đại diện cho **filter BSON**; chúng không tự thực hiện query cho đến khi được truyền vào một API như find(), countDocuments(), updateOne() hoặc deleteMany().

### 19.3. Cẩn thận với null trong Java

Một bộ lọc như **Filters.eq("rating", null)** có ngữ nghĩa của MongoDB đối với null: khớp field là null hoặc thiếu field. **Filters.ne("rating", null)** chọn field tồn tại và không phải null.

Nếu logic Java muốn kiểm tra một trường **tồn tại bất kể giá trị**, cần dùng **Filters.exists("rating", true)**. Đừng dùng ne với một giá trị bất kỳ rồi mặc định mọi kết quả đều có field.

## 20. Spring Data MongoDB: Criteria và Query

Với Spring Data MongoDB, lớp **Criteria** cung cấp các phương thức tương ứng:

| MongoDB operator | Spring Data Criteria |
|---|---|
| $eq | is(value) |
| $ne | ne(value) |
| $gt | gt(value) |
| $gte | gte(value) |
| $lt | lt(value) |
| $lte | lte(value) |

Ví dụ lọc stock trong khoảng [2, 12]:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import java.util.List;

public class ProductQueryService {
    private final MongoTemplate mongoTemplate;

    public ProductQueryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> findMediumStock() {
        Query query = new Query(
                Criteria.where("stock").gte(2).lte(12)
        );

        return mongoTemplate.find(
                query,
                Document.class,
                "comparisonProducts"
        );
    }
}
~~~

Filter tương ứng:

~~~javascript
{ stock: { $gte: 2, $lte: 12 } }
~~~

Kết quả theo dữ liệu mẫu: **P03, P04, P05, P06**.

Ví dụ kiểm tra khác null:

~~~java
Query ratedOnly = new Query(
        Criteria.where("rating").ne(null)
);
~~~

Query trên chọn những document có rating tồn tại và không phải null. Khi thiết kế repository, nên dùng kiểu Java và mapping phù hợp với kiểu BSON của field; một phép so sánh đúng về mặt cú pháp vẫn có thể không trả kết quả mong muốn nếu dữ liệu cũ lưu sai kiểu.

## 21. Index và hiệu năng truy vấn so sánh

MongoDB có thể sử dụng **index** để hạn chế số document cần đọc khi thực hiện filter. Các toán tử so sánh bằng và phạm vi thường là những thành phần quan trọng khi thiết kế index.

Ví dụ một ứng dụng thường truy vấn sản phẩm theo category rồi lọc giá:

~~~javascript
db.comparisonProducts.createIndex({
  category: 1,
  price: 1
})
~~~

Truy vấn:

~~~javascript
db.comparisonProducts.find({
  category: "electronics",
  price: {
    $gte: NumberDecimal("20.00"),
    $lt: NumberDecimal("60.00")
  }
})
~~~

Index ghép **category, price** có thể hỗ trợ các thao tác tìm đúng category rồi duyệt một khoảng giá. Dù vậy, việc MongoDB thực sự chọn index nào phụ thuộc thống kê, kích thước collection, độ chọn lọc của filter và query planner.

### 21.1. Equality trước, range sau

Với nhiều truy vấn, một index ghép thường được thiết kế theo nhu cầu như:

~~~text
category = "electronics"      -> equality
price >= 20 và price < 60     -> range
~~~

Tùy workload, index:

~~~javascript
{ category: 1, price: 1 }
~~~

có thể phù hợp. Nhưng không nên máy móc áp dụng một thứ tự index cho mọi trường hợp: sort, số lượng trạng thái, mức phân bố dữ liệu và điều kiện bổ sung đều ảnh hưởng hiệu quả.

### 21.2. Xem query plan với explain()

~~~javascript
db.comparisonProducts
  .find({
    category: "electronics",
    price: {
      $gte: NumberDecimal("20.00"),
      $lt: NumberDecimal("60.00")
    }
  })
  .explain("executionStats")
~~~

Chú ý các chỉ số:

- **winningPlan:** chiến lược thực thi được chọn.
- **totalKeysExamined:** số entry của index được duyệt.
- **totalDocsExamined:** số document được kiểm tra.
- **nReturned:** số document trả về.

Trên tập dữ liệu mẫu chỉ có bảy document, collection scan có thể hợp lý. Đừng kết luận index không có ích trong production chỉ vì MongoDB không chọn nó khi dữ liệu thử quá ít.

### 21.3. $ne thường kém chọn lọc hơn $eq

Ví dụ nếu 99% sản phẩm **không** có category là "obsolete", filter:

~~~javascript
{ category: { $ne: "obsolete" } }
~~~

sẽ chọn gần như toàn bộ collection. Index có thể không giúp giảm nhiều công việc đọc.

Ngược lại:

~~~javascript
{ category: { $eq: "electronics" } }
~~~

có khả năng chọn lọc hơn nếu electronics chiếm một tỷ lệ nhỏ. Cần đo bằng **explain()**, không chỉ đoán từ tên toán tử.

### 21.4. Index không khắc phục sai kiểu dữ liệu

Nếu một số document lưu **price: "25.00"** dưới dạng String và phần khác lưu **price: NumberDecimal("25.00")**, index vẫn lưu giá trị theo kiểu BSON thực tế. Filter theo ngưỡng số sẽ không tự ép mọi chuỗi thành số.

Schema validation, quy tắc mapping trong ứng dụng và migration dữ liệu cũ là cách giải quyết sự không nhất quán về kiểu. Thêm index lên dữ liệu sai kiểu không làm chúng trở thành một miền giá trị thống nhất.

## 22. Những lỗi thường gặp khi dùng sáu toán tử

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Giá đúng 25 không xuất hiện trong kết quả | Dùng $gt: 25 thay vì $gte: 25 | Xác định biên có được tính hay không |
| Giá đúng 30 vẫn xuất hiện dù muốn dưới 30 | Dùng $lte: 30 thay vì $lt: 30 | Dùng biên trên không bao gồm |
| Filter khoảng chỉ áp dụng điều kiện cuối | Viết trùng khóa field trong cùng object | Gộp $gte/$lt vào một object của field |
| $ne trả cả document thiếu field | Đây là ngữ nghĩa của $ne với giá trị thông thường | Kết hợp $exists: true khi cần field có mặt |
| So sánh bằng null trả cả document thiếu field | $eq: null có quy tắc đặc biệt | Dùng $exists để phân biệt trường vắng mặt |
| Truy vấn price > 20 không lấy dữ liệu "25.00" | price lưu String, filter dùng Number | Sửa schema và chuyển dữ liệu sang số BSON |
| Query _id không tìm thấy dù chuỗi hex giống nhau | _id là ObjectId nhưng filter truyền String | Tạo ObjectId theo schema thực tế |
| Lọc ngày thiếu bản ghi cuối ngày | Dùng $lte tới 23:59:59 và bỏ sót mili giây | Dùng [start, nextDayStart) |
| Mảng [40, 90] vẫn khớp >=80 và <90 | Hai điều kiện có thể do hai phần tử khác nhau thỏa | Dùng $elemMatch để bắt buộc cùng phần tử |
| So sánh tên không khớp khác chữ hoa/thường | Collation mặc định không như yêu cầu | Xác định collation của collection/query/index |
| Sử dụng $ne chậm trên dữ liệu lớn | Điều kiện không chọn lọc, khớp phần lớn document | Đánh giá kế hoạch với explain và thiết kế filter/index |
| Kết quả find() thay đổi thứ tự | Không có sort tường minh | Dùng sort theo khóa nghiệp vụ và khóa phụ nếu cần |

### 22.1. Khác nhau giữa giá trị đầu vào và biểu thức toán tử

Trong code JavaScript, ví dụ:

~~~javascript
const minPrice = NumberDecimal("20.00");

db.comparisonProducts.find({
  price: { $gte: minPrice }
})
~~~

là filter hợp lệ vì **minPrice** là một biến có giá trị BSON Decimal128. Nhưng:

~~~javascript
db.comparisonProducts.find({
  price: { $gte: "minPrice" }
})
~~~

so sánh với chuỗi literal **"minPrice"**, không truy cập biến. Đây là lỗi thường thấy khi xây dựng filter động.

### 22.2. Tên field và kiểu dữ liệu đều quan trọng

Hai filter sau truy cập hai field khác nhau:

~~~javascript
{ stock: { $gt: 0 } }
{ "inventory.stock": { $gt: 0 } }
~~~

Truy vấn thứ hai chỉ đúng khi document có object **inventory** với trường con **stock**. MongoDB không tự dò mọi nơi trong document để tìm field cùng tên.

### 22.3. Toán tử trong filter khác toán tử biểu thức trong aggregation

Trong truy vấn thông thường:

~~~javascript
db.items.find({
  stock: { $gt: 10 }
})
~~~

**$gt** nhận một giá trị tham chiếu là 10 trong điều kiện của field stock.

Nếu cần so sánh **hai field trong cùng document**, thường dùng **$expr** với cú pháp toán tử biểu thức:

~~~javascript
db.items.find({
  $expr: {
    $gt: ["$stock", "$reorderLevel"]
  }
})
~~~

Ở đây hai đối số là biểu thức tham chiếu field, đặt trong một array. Hai cách dùng cùng tên $gt nhưng **cú pháp và ngữ cảnh khác nhau**. Đừng lấy nguyên cú pháp $expr để đặt vào bộ lọc field thông thường.

## 23. Bài tập thực hành

Hãy dùng collection **comparisonProducts** đã tạo ở phần đầu, chạy thử từng filter và đối chiếu các _id thực tế.

### Bài 1. Chọn toán tử chính xác

Viết filter cho từng yêu cầu:

1. Stock bằng 0.
2. Giá khác 20.00.
3. Giá lớn hơn 25.00.
4. Giá ít nhất 25.00.
5. Stock dưới 3.
6. Stock tối đa 3.

**Đáp án tham khảo:**

~~~javascript
// 1. Bằng 0
{ stock: { $eq: 0 } }

// 2. Khác 20.00
{ price: { $ne: NumberDecimal("20.00") } }

// 3. Trên 25.00
{ price: { $gt: NumberDecimal("25.00") } }

// 4. Từ 25.00 trở lên
{ price: { $gte: NumberDecimal("25.00") } }

// 5. Dưới 3
{ stock: { $lt: 3 } }

// 6. Không quá 3
{ stock: { $lte: 3 } }
~~~

### Bài 2. Lọc trong khoảng giá

Yêu cầu: các sản phẩm có **price từ 10.00 đến 30.00, bao gồm hai đầu**.

~~~javascript
db.comparisonProducts.find({
  price: {
    $gte: NumberDecimal("10.00"),
    $lte: NumberDecimal("30.00")
  }
}).sort({ _id: 1 })
~~~

Kết quả: **P01, P03, P05, P06**.

Nếu thay **$lte: 30.00** bằng **$lt: 30.00**, P05 bị loại. Giải thích vì sao chỉ một thay đổi nhỏ ở toán tử làm thay đổi tập kết quả.

### Bài 3. Tìm rating chưa có

Hãy viết truy vấn cho ba trường hợp:

1. Rating là null hoặc field bị thiếu.
2. Rating tồn tại và khác null.
3. Rating tồn tại nhưng khác 4.8 (chấp nhận null).

**Đáp án tham khảo:**

~~~javascript
// 1. Null hoặc field thiếu
{ rating: { $eq: null } }

// 2. Field tồn tại và không phải null
{ rating: { $ne: null } }

// 3. Field tồn tại và khác 4.8, có thể là null
{ rating: { $ne: 4.8, $exists: true } }
~~~

Những kết quả mẫu lần lượt là **P06/P07**, **P01–P05**, và **P01/P03/P04/P05/P06**.

### Bài 4. So sánh thời gian theo khoảng nửa mở

Yêu cầu: document được tạo trong khoảng **từ đầu 12/11/2026 đến trước đầu 15/11/2026 theo UTC**.

~~~javascript
db.comparisonProducts.find({
  createdAt: {
    $gte: ISODate("2026-11-12T00:00:00Z"),
    $lt: ISODate("2026-11-15T00:00:00Z")
  }
})
~~~

Kết quả: **P03, P04, P05**.

Thử giải thích vì sao không cần tự tính thời điểm **23:59:59.999** của ngày 14/11.

### Bài 5. Mảng và $elemMatch

Với collection arrayExamples:

~~~javascript
{ _id: "A", scores: [40, 90] }
{ _id: "E", scores: [85, 95] }
~~~

So sánh hai filter:

~~~javascript
// Filter A
{ scores: { $gte: 80, $lt: 90 } }

// Filter B
{ scores: { $elemMatch: { $gte: 80, $lt: 90 } } }
~~~

Tại sao filter A có thể khớp **A và E**, còn filter B chỉ khớp **E**? Trả lời bằng cách chỉ rõ **phần tử cụ thể** nào thỏa từng điều kiện.

### Bài 6. Ghép nhiều điều kiện

Yêu cầu: sản phẩm thuộc **stationery**, **giá dưới 15.00**, **stock dương**.

~~~javascript
db.comparisonProducts.find({
  category: { $eq: "stationery" },
  price: { $lt: NumberDecimal("15.00") },
  stock: { $gt: 0 }
}).sort({ _id: 1 })
~~~

Kết quả: **P02, P06, P07**.

Giải thích cách MongoDB kết hợp ba điều kiện theo AND và vì sao P01 không được chọn.

### Bài 7. Giải thích kế hoạch truy vấn

Tạo index:

~~~javascript
db.comparisonProducts.createIndex({
  category: 1,
  price: 1
})
~~~

Sau đó chạy:

~~~javascript
db.comparisonProducts.find({
  category: "stationery",
  price: { $gte: NumberDecimal("10.00") }
}).explain("executionStats")
~~~

Hãy xác định **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, **nReturned**. Giải thích vì sao việc có index không bảo đảm query planner sẽ dùng index cho một collection chỉ có vài document, và vì sao cần kiểm tra trên dữ liệu có phân bố gần thực tế.

## 24. Cách chọn toán tử theo yêu cầu nghiệp vụ

| Cách diễn đạt | Toán tử thích hợp |
|---|---|
| Bằng / đúng một giá trị | $eq hoặc cú pháp field: value |
| Khác / không bằng một giá trị | $ne |
| Lớn hơn / trên / sau một mốc | $gt |
| Tối thiểu / ít nhất / từ một mốc trở lên | $gte |
| Nhỏ hơn / dưới / trước một mốc | $lt |
| Tối đa / không vượt quá / tới một mốc bao gồm | $lte |
| Trong khoảng gồm cả hai đầu | $gte kết hợp $lte |
| Trong khoảng không gồm hai đầu | $gt kết hợp $lt |
| Trong khoảng từ start đến trước end | $gte kết hợp $lt |
| Có nhiều giá trị rời rạc được phép | Cân nhắc $in |
| Một phần tử array phải thỏa đồng thời nhiều ràng buộc | $elemMatch kết hợp toán tử so sánh |
| Kiểm tra field có tồn tại | $exists |

Để dùng đúng sáu toán tử so sánh trong MongoDB, hãy luôn xác nhận **giá trị mốc có được bao gồm không**, **field là scalar hay array**, **field có thể null/thiếu không**, và **BSON type thực tế là gì**. Sau đó, với truy vấn thường xuyên trên dữ liệu lớn, thiết kế index theo filter thực tế và quan sát bằng explain().

Khi các yếu tố này được xác định rõ, những câu điều kiện đơn giản như **price >= 20 và price < 50** trở thành bộ lọc MongoDB dễ đọc, chính xác và có thể mở rộng an toàn trong ứng dụng Java.
