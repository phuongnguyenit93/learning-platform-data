# Multikey index cho mảng và giới hạn index ghép nhiều trường mảng trong MongoDB

## 1. Vì sao mảng làm thay đổi cách MongoDB lập index?

MongoDB lưu dữ liệu dưới dạng BSON document. Một trường có thể là giá trị đơn hoặc một **mảng** chứa nhiều giá trị. Ví dụ, sản phẩm có nhiều nhãn, nhiều màu sắc hoặc nhiều biến thể:

```javascript
{
  _id: "P100",
  name: "Áo khoác gió",
  category: "OUTERWEAR",
  tags: ["outdoor", "waterproof", "sale"],
  variants: [
    { color: "black", size: "M", stock: 12 },
    { color: "blue", size: "L", stock: 4 }
  ]
}
```

Đối với trường đơn `category`, một document thường đóng góp một giá trị khóa cho index `{ category: 1 }`. Nhưng đối với trường mảng `tags`, một document có thể chứa nhiều phần tử cần tìm kiếm. MongoDB sử dụng **multikey index** để tạo khóa index từ các phần tử của mảng, cho phép truy vấn như:

```javascript
db.products.find({ tags: "waterproof" });
```

không nhất thiết phải quét từng document trong collection.

Trong chương *Index chuyên biệt*, điều quan trọng không chỉ là biết `createIndex()`, mà còn hiểu:

- Vì sao index một trường mảng được gọi là **multikey**.
- Khi nào một **compound index** vừa chứa trường scalar vừa chứa trường mảng.
- Tại sao MongoDB giới hạn index ghép nhiều **mảng độc lập**.
- Mảng chứa các **embedded document** khác gì hai mảng độc lập.
- Vai trò của `$elemMatch` trong việc bảo đảm nhiều điều kiện khớp **cùng một phần tử**.
- Những đánh đổi về kích thước index, cập nhật mảng, sort, covered query và tính duy nhất.

## 2. Multikey index là gì?

Một **multikey index** là index mà MongoDB sử dụng để lập khóa từ giá trị mảng. Khi tạo index cho một đường dẫn trường mà dữ liệu thực tế chứa mảng, MongoDB xác định index đó là multikey; không cần viết tùy chọn `multikey: true` trong `createIndex()`.

### 2.1. Index một trường mảng

Giả sử một collection thử nghiệm:

```javascript
db.products.insertMany([
  {
    _id: "P100",
    name: "Áo khoác gió",
    category: "OUTERWEAR",
    tags: ["outdoor", "waterproof", "sale"],
    price: NumberDecimal("750000")
  },
  {
    _id: "P101",
    name: "Giày chạy bộ",
    category: "FOOTWEAR",
    tags: ["running", "outdoor"],
    price: NumberDecimal("1200000")
  },
  {
    _id: "P102",
    name: "Túi laptop",
    category: "BAGS",
    tags: [],
    price: NumberDecimal("350000")
  },
  {
    _id: "P103",
    name: "Bàn làm việc",
    category: "FURNITURE",
    tags: ["office"],
    price: NumberDecimal("1600000")
  }
]);

db.products.createIndex({ tags: 1 });
```

MongoDB có thể lập các khóa logic cho từng phần tử mảng `tags`:

| Document | Phần tử `tags` | Các giá trị khóa index có ý nghĩa tìm kiếm |
|---|---|---|
| P100 | outdoor, waterproof, sale | outdoor, waterproof, sale |
| P101 | running, outdoor | running, outdoor |
| P102 | Mảng rỗng | Không có phần tử tag riêng lẻ để tìm |
| P103 | office | office |

Bảng chỉ minh họa **các giá trị phần tử tạo khóa**, không phải bản sao chính xác cấu trúc B-tree hoặc cách MongoDB biểu diễn khóa đặc biệt cho mảng rỗng/missing. Một entry index còn gắn với bản ghi tương ứng để máy chủ xác định document nguồn.

Với truy vấn:

```javascript
db.products.find({ tags: "outdoor" });
```

MongoDB có thể dùng multikey index để tìm **P100** và **P101**. Người dùng không phải viết cú pháp đặc biệt để nói rằng `tags` là array: MongoDB hiểu biểu thức so khớp một phần tử của mảng theo quy tắc truy vấn.

### 2.2. Mô hình một document tạo nhiều khóa

```text
Document P100
  tags = ["outdoor", "waterproof", "sale"]
            |          |         |
            v          v         v
         index key  index key  index key
         "outdoor"  "waterproof" "sale"
            \          |         /
             \         |        /
               cùng trỏ về P100
```

Mỗi phần tử khác nhau có thể tạo ra một khóa index để phục vụ tìm kiếm. Nếu một mảng có giá trị lặp lại trong **cùng một document**, MongoDB không cần lưu nhiều entry giống hệt nhau cho cùng tổ hợp khóa và record ID. Tuy vậy, số lượng phần tử mảng và mức độ đa dạng của chúng vẫn ảnh hưởng đáng kể đến kích thước index.

### 2.3. Không chỉ mảng chuỗi

Multikey index cũng áp dụng cho mảng số, ngày giờ và mảng embedded documents:

```javascript
db.students.insertOne({
  _id: "S01",
  scores: [72, 85, 96]
});

db.students.createIndex({ scores: 1 });

db.students.find({ scores: { $gte: 90 } });
```

Ở đây truy vấn có thể tìm học viên có **ít nhất một điểm** từ 90 trở lên. Nhưng nếu muốn hai điều kiện cùng áp dụng cho **một phần tử** của mảng hoặc một embedded document, cần hiểu thêm `$elemMatch` ở phần sau.

## 3. Cách MongoDB xác định một index là multikey

### 3.1. Tạo index trước hay chèn mảng trước?

Hai tình huống đều có thể dẫn tới multikey index:

**Tình huống A — collection đã có mảng, sau đó mới tạo index:**

```javascript
db.preExistingArray.insertOne({
  _id: 1,
  topics: ["mongodb", "index"]
});

db.preExistingArray.createIndex({ topics: 1 });
```

**Tình huống B — index được tạo trước, sau đó chèn document có mảng:**

```javascript
db.laterArray.createIndex({ topics: 1 });

db.laterArray.insertOne({
  _id: 1,
  topics: ["mongodb", "index"]
});
```

MongoDB quản lý tính chất multikey của index khi nó gặp giá trị mảng ở đường dẫn được index. Ứng dụng không phải xóa rồi tạo lại index chỉ vì một trường vốn scalar bắt đầu chứa array, **miễn thao tác vẫn tuân thủ các giới hạn của index**.

### 3.2. Mảng của đối tượng lồng nhau

Cho document:

```javascript
{
  _id: "O01",
  items: [
    { sku: "BOOK", quantity: 2 },
    { sku: "PEN", quantity: 5 }
  ]
}
```

Index sau sẽ là multikey vì đường dẫn `items.sku` đi qua mảng `items`:

```javascript
db.orders.createIndex({ "items.sku": 1 });

db.orders.find({ "items.sku": "BOOK" });
```

Không cần index cả trường `items` để truy vấn `items.sku`. Đường dẫn dotted path chỉ rõ giá trị cần tìm trong các phần tử embedded document.

### 3.3. Kiểm tra bằng `explain()`

```javascript
db.products.find({ tags: "outdoor" })
  .explain("executionStats");
```

Tùy phiên bản và execution engine, kết quả explain có thể hiển thị:

- `IXSCAN`: bước đọc khóa từ index.
- `FETCH`: bước lấy document khi thông tin từ index chưa đủ.
- `isMultiKey`: thông tin về tính chất multikey khi stage liên quan cung cấp trường này.
- `multiKeyPaths`: các đường dẫn mảng làm index trở thành multikey, nếu xuất hiện trong explain.
- `totalKeysExamined`: số khóa index được xem xét.
- `totalDocsExamined`: số document cần đọc.
- `nReturned`: số document kết quả.

Không nên kỳ vọng mọi bản MongoDB đều in ra cấu trúc explain giống hệt nhau. Với collection rất nhỏ, planner còn có thể chọn `COLLSCAN` dù index đã tồn tại; mục đích ở đây là hiểu cách quan sát, không đưa ra kết luận hiệu năng từ vài document.

## 4. Compound multikey index: một trường thường và một trường mảng

Index ghép (compound index) có nhiều khóa theo một thứ tự nhất định. Một dạng thường rất hữu ích là **một trường scalar dùng để lọc bằng nhau, rồi tới một trường mảng**.

### 4.1. Ví dụ category + tags

```javascript
db.products.createIndex({
  category: 1,
  tags: 1
});
```

Index này có thể tạo các khóa logic như:

```text
P100 -> ("OUTERWEAR", "outdoor")
        ("OUTERWEAR", "waterproof")
        ("OUTERWEAR", "sale")

P101 -> ("FOOTWEAR", "running")
        ("FOOTWEAR", "outdoor")
```

Truy vấn:

```javascript
db.products.find({
  category: "OUTERWEAR",
  tags: "waterproof"
});
```

có thể sử dụng các thành phần của index ghép để thu hẹp vùng khóa cần quét. Giá trị `category` của một document kết hợp với từng phần tử `tags` để tạo khóa.

### 4.2. Thứ tự trường của compound index vẫn quan trọng

Hai index:

```javascript
{ category: 1, tags: 1 }
{ tags: 1, category: 1 }
```

không phải lúc nào cũng có kế hoạch và hiệu năng giống nhau. Cần xét mẫu truy vấn phổ biến: có hay không có điều kiện trên `category`, kiểu so sánh trên từng trường, nhu cầu sort và độ chọn lọc.

Ví dụ nếu đa số truy vấn lọc **một category cụ thể** rồi tìm tag, `{ category: 1, tags: 1 }` là ứng viên tự nhiên. Nếu truy vấn chủ yếu tìm tag trên toàn collection và chỉ thỉnh thoảng lọc category, cần đo để quyết định thứ tự index.

### 4.3. Index ghép vẫn chỉ có thể tận dụng thông tin đã được index

Với:

```javascript
db.products.find(
  { category: "OUTERWEAR", tags: "waterproof" },
  { _id: 0, name: 1, price: 1 }
);
```

Index `{ category: 1, tags: 1 }` không chứa `name` và `price`, nên MongoDB có thể phải đọc document gốc để hoàn thiện projection. Multikey index **không tự biến mọi truy vấn thành covered query**.

## 5. Giới hạn cốt lõi: không index hai mảng độc lập trong một compound index trên cùng document

Đây là phần dễ gặp lỗi nhất khi thiết kế index cho document nhiều mảng.

Giả sử một sản phẩm lưu hai danh sách độc lập:

```javascript
{
  _id: "P200",
  tags: ["sale", "winter"],
  availableSizes: ["M", "L", "XL"]
}
```

Ta có thể nghĩ tới:

```javascript
db.catalog.createIndex({
  tags: 1,
  availableSizes: 1
});
```

Nhưng khi một document chứa **cả hai trường được index dưới dạng các mảng độc lập**, MongoDB không cho phép compound multikey index như vậy. Lỗi thường được mô tả là **cannot index parallel arrays**.

### 5.1. Vì sao hai mảng độc lập gây vấn đề?

Nếu MongoDB phải kết hợp mọi nhãn với mọi size trong một document, các cặp khóa sẽ là:

```text
tags = ["sale", "winter"]
sizes = ["M", "L", "XL"]

Tích Descartes giả định:
  ("sale",   "M")
  ("sale",   "L")
  ("sale",   "XL")
  ("winter", "M")
  ("winter", "L")
  ("winter", "XL")
```

Hai mảng không có quan hệ phần tử-cùng-vị-trí để diễn tả cặp có ý nghĩa nghiệp vụ. Ví dụ này là **trực giác giải thích sự bùng nổ tổ hợp**, không phải mô tả rằng MongoDB thực sự tạo sáu khóa rồi chấp nhận index: MongoDB áp dụng ràng buộc và có thể từ chối thao tác.

Khi số phần tử hai mảng lần lượt là `m` và `n`, số cặp giả định là `m × n`. Với nhiều mảng hoặc mảng lớn, lượng khóa có thể tăng cực nhanh. MongoDB hạn chế kiểu **parallel arrays** để tránh cấu trúc index ghép không phù hợp.

### 5.2. Lỗi khi tạo index trên dữ liệu hiện có

```javascript
db.parallelArraysDemo.insertOne({
  _id: "P200",
  tags: ["sale", "winter"],
  availableSizes: ["M", "L", "XL"]
});

// Không hợp lệ với document trên.
db.parallelArraysDemo.createIndex({
  tags: 1,
  availableSizes: 1
});
```

Vì document P200 có **hai đường dẫn mảng độc lập** cùng nằm trong index specification, thao tác tạo index bị từ chối.

### 5.3. Lỗi khi insert sau khi đã tạo index

Ràng buộc không chỉ được kiểm tra lúc tạo index. Giả sử collection lúc đầu chỉ có trường scalar:

```javascript
db.parallelInsertDemo.insertOne({
  _id: "P201",
  tags: "sale",
  availableSizes: "M"
});

db.parallelInsertDemo.createIndex({
  tags: 1,
  availableSizes: 1
});

// Document mới có hai mảng độc lập; thao tác ghi có thể bị từ chối.
db.parallelInsertDemo.insertOne({
  _id: "P202",
  tags: ["sale", "winter"],
  availableSizes: ["M", "L"]
});
```

Sau khi compound index tồn tại, các thao tác insert hoặc update cũng phải tuân thủ ràng buộc. Một lệnh `$set` biến trường scalar thứ hai thành mảng có thể thất bại nếu nó khiến document có hai mảng độc lập trong những đường dẫn của cùng index.

### 5.4. Quy tắc không đơn giản là “mỗi collection chỉ được có một trường mảng”

Đây là điểm cần hiểu chính xác. Giới hạn áp dụng đối với **các đường dẫn mảng được compound index kết hợp trong một document**, không có nghĩa:

- Collection MongoDB chỉ được có một trường mảng.
- Một document không thể chứa hai mảng.
- Chỉ được tạo một multikey index trong collection.
- Index ghép không bao giờ được phép có các trường mà ở các document khác nhau có thể mang kiểu mảng.

Ví dụ mô hình sau có thể hợp lệ cho compound index `{ a: 1, b: 1 }` khi **mỗi document chỉ có một trong hai trường được index là mảng**:

```javascript
db.separateArrayDocs.insertMany([
  { _id: 1, a: [1, 2], b: 5 },
  { _id: 2, a: 3, b: [7, 8] }
]);

db.separateArrayDocs.createIndex({ a: 1, b: 1 });
```

Nhưng thêm:

```javascript
db.separateArrayDocs.insertOne({
  _id: 3,
  a: [1, 2],
  b: [7, 8]
});
```

sẽ vi phạm giới hạn của compound multikey index vì **cùng document** chứa hai mảng độc lập trên các đường dẫn đó.

**Quy tắc thực hành:** một document không được yêu cầu compound index kết hợp khóa từ **hai array path độc lập**. Khi xem xét index nhiều trường liên quan đến mảng, phải xét đường dẫn mảng thực tế, chứ không chỉ đếm tên trường bắt đầu bằng `$` hoặc chỉ nhìn dữ liệu của một document.

## 6. Trường hợp quan trọng: nhiều thuộc tính thuộc cùng một mảng embedded documents

Giới hạn “không index parallel arrays” dễ khiến ta hiểu sai rằng hai đường dẫn có tiền tố mảng giống nhau cũng luôn bị cấm. Nhưng một **mảng các embedded document** thể hiện quan hệ giữa các thuộc tính trong **cùng một phần tử** và có thể hỗ trợ compound multikey index trên nhiều đường dẫn của mảng chung.

### 6.1. Mô hình biến thể sản phẩm

```javascript
db.variantCatalog.insertMany([
  {
    _id: "P300",
    variants: [
      { color: "black", size: "M", stock: 10 },
      { color: "blue", size: "L", stock: 3 }
    ]
  },
  {
    _id: "P301",
    variants: [
      { color: "black", size: "L", stock: 7 },
      { color: "red", size: "M", stock: 2 }
    ]
  },
  {
    _id: "P302",
    variants: [
      { color: "blue", size: "M", stock: 5 }
    ]
  }
]);

db.variantCatalog.createIndex({
  "variants.color": 1,
  "variants.size": 1
});
```

Ở đây `variants.color` và `variants.size` đều đi qua **cùng đường dẫn mảng `variants`**, không phải hai mảng cấp trên độc lập như `tags` và `availableSizes`.

### 6.2. Các khóa thể hiện cặp thuộc tính trong phần tử

Với P300, ta quan tâm tới các cặp:

```text
variants[0] = { color: "black", size: "M" }
variants[1] = { color: "blue",  size: "L" }

Cặp dữ liệu từ từng phần tử:
    ("black", "M")
    ("blue",  "L")
```

Điều này khác với việc tạo ra mọi tổ hợp màu/kích cỡ không tồn tại:

```text
("black", "L")  <- KHÔNG phải một biến thể có trong P300
("blue",  "M")  <- KHÔNG phải một biến thể có trong P300
```

Khi xây dựng index trên các thuộc tính của cùng một mảng embedded documents, MongoDB có thể sử dụng mối quan hệ giữa các đường dẫn này. Tuy nhiên, **việc truy vấn có bảo đảm hai điều kiện cùng đúng trên một phần tử hay không lại phụ thuộc cú pháp filter**.

### 6.3. Không có `$elemMatch`: điều kiện có thể khớp hai phần tử khác nhau

```javascript
db.variantCatalog.find({
  "variants.color": "black",
  "variants.size": "L"
});
```

Truy vấn này có thể khớp **P300** dù P300 không có biến thể nào vừa black vừa size L:

- Phần tử thứ nhất có `color: "black"`.
- Phần tử thứ hai có `size: "L"`.
- Các điều kiện trên dotted paths có thể được đáp ứng bởi **các phần tử khác nhau**.

P301 cũng khớp vì thực sự có phần tử `{ color: "black", size: "L" }`. Nếu nghiệp vụ cần “màu black và size L của **cùng biến thể**”, kết quả P300 là **false positive theo nghiệp vụ**, dù MongoDB không hề xử lý sai biểu thức truy vấn đã viết.

### 6.4. Dùng `$elemMatch` để yêu cầu cùng phần tử

```javascript
db.variantCatalog.find({
  variants: {
    $elemMatch: {
      color: "black",
      size: "L"
    }
  }
});
```

Kết quả đúng ý định: **P301**, không phải P300.

`$elemMatch` bảo đảm tồn tại **một phần tử của mảng `variants`** thỏa đồng thời cả hai điều kiện. Đây là yêu cầu cơ bản khi lọc trên những cặp thuộc tính có quan hệ với nhau như:

- `color + size` của một biến thể.
- `sku + quantity` của một dòng hàng.
- `examType + score` của một lần thi.
- `warehouseId + stock` của một vị trí kho.

### 6.5. `$elemMatch` còn ảnh hưởng cách compound index được sử dụng

Không chỉ sửa ngữ nghĩa kết quả, `$elemMatch` trên **đường dẫn mảng chung** còn có thể cho phép query planner **compound các index bounds** của nhiều đường dẫn liên quan.

Với index:

```javascript
{ "variants.color": 1, "variants.size": 1 }
```

và query:

```javascript
{
  variants: {
    $elemMatch: {
      color: "black",
      size: "L"
    }
  }
}
```

MongoDB có thể xét cả điều kiện màu và size trong một mối quan hệ cùng phần tử. Nếu chỉ có hai predicate dotted paths tách rời, planner không được tùy tiện giả định chúng thuộc cùng phần tử, nên khả năng ghép bounds có thể bị hạn chế.

**Lưu ý:** không phải cứ thêm `$elemMatch` là truy vấn chắc chắn dùng một index cụ thể. Việc chọn kế hoạch vẫn phụ thuộc version, dữ liệu, index, sort và các điều kiện khác. Đọc `explain()` để xem bounds thực tế.

## 7. Index bounds với một trường mảng có nhiều điều kiện

### 7.1. Khi hai điều kiện có thể khớp hai phần tử khác nhau

Giả sử mỗi học viên có mảng điểm:

```javascript
db.examResults.insertMany([
  { _id: "S01", scores: [65, 98] },
  { _id: "S02", scores: [75, 82] },
  { _id: "S03", scores: [45, 55] }
]);

db.examResults.createIndex({ scores: 1 });
```

Truy vấn:

```javascript
db.examResults.find({
  scores: { $gte: 70, $lte: 90 }
});
```

có thể khớp S01, dù S01 không có điểm nào nằm trong khoảng 70–90:

- `98 >= 70` là đúng.
- `65 <= 90` cũng đúng.
- Hai điều kiện có thể được thỏa bởi hai phần tử khác nhau.

S02 cũng khớp vì nó có 75 và 82 trong khoảng, còn S03 không khớp.

### 7.2. Dùng `$elemMatch` với hai điều kiện trên cùng phần tử

```javascript
db.examResults.find({
  scores: {
    $elemMatch: {
      $gte: 70,
      $lte: 90
    }
  }
});
```

Kết quả là **S02**. Câu truy vấn nay yêu cầu có ít nhất một phần tử điểm vừa >= 70 vừa <= 90.

Với multikey index `{ scores: 1 }`, `$elemMatch` còn giúp MongoDB có thể **intersect index bounds** đối với cùng một array path, ví dụ khoảng `[70, 90]`, thay vì phải sử dụng một bound rồi kiểm tra điều kiện còn lại theo quy tắc truy vấn nhiều phần tử.

### 7.3. Hai thuật ngữ nên phân biệt

| Khái niệm | Ý nghĩa trong bối cảnh multikey |
|---|---|
| **Bounds intersection** | Giao các điều kiện giới hạn trên **một trường index** khi chúng phải được thỏa bởi cùng phần tử |
| **Bounds compounding** | Ghép điều kiện của **nhiều trường** trong compound index thành một vùng khóa tìm kiếm |
| **`$elemMatch`** | Diễn đạt ràng buộc “cùng phần tử mảng”, giúp planner có cơ sở giao/ghép bounds trong các trường hợp được hỗ trợ |

Không phải mọi `$elemMatch` đều tạo lợi thế index giống nhau. Đường dẫn đặt `$elemMatch` phải phù hợp cấu trúc mảng và các field path của index.

## 8. Những điều index không tự giải quyết

### 8.1. `$all`, `$size` và ý nghĩa của một mảng

```javascript
// Có cả hai nhãn, có thể ở hai phần tử khác nhau.
db.products.find({
  tags: { $all: ["outdoor", "waterproof"] }
});

// Mảng tags có đúng 3 phần tử.
db.products.find({
  tags: { $size: 3 }
});
```

Multikey index có thể giúp các truy vấn tìm phần tử mảng bằng giá trị. Nhưng `$size` hỏi **độ dài mảng**, trong khi multikey index không lưu một trường “số lượng phần tử” theo dạng có thể luôn sử dụng trực tiếp để giải quyết điều kiện đó.

Nếu hệ thống thường xuyên lọc theo số phần tử:

```javascript
{
  _id: "P100",
  tags: ["outdoor", "waterproof", "sale"],
  tagCount: 3
}
```

có thể cân nhắc trường dẫn xuất `tagCount` và index `{ tagCount: 1 }`, **nếu** ứng dụng duy trì `tagCount` đúng khi mảng thay đổi. Chỉ nên đánh đổi thêm trường dẫn xuất khi nhu cầu truy vấn và dữ liệu thực tế đủ lớn để biện minh cho chi phí đồng bộ.

### 8.2. Index trên mảng không tự bảo đảm uniqueness theo phần tử con

Ví dụ một giỏ hàng:

```javascript
{
  _id: "C01",
  items: [
    { sku: "P01", quantity: 1 },
    { sku: "P01", quantity: 2 }
  ]
}
```

Nếu nghiệp vụ muốn **một SKU chỉ xuất hiện một lần trong một giỏ**, thì index trên `items.sku`, kể cả một **unique multikey index**, không nên được coi là công cụ tự động áp đặt ràng buộc này bên trong cùng document. Unique multikey index có ngữ nghĩa **giữa các document**, được giải thích ở phần 10.

### 8.3. Index không sửa lỗi mô hình dữ liệu

Truy vấn yêu cầu màu black và size L của cùng biến thể sẽ sai nếu filter chỉ ghép hai dotted paths độc lập. Thêm index chỉ làm cách truy vấn đó chạy theo kế hoạch khác; **nó không tự sửa nghĩa của filter**. Trước khi tối ưu hiệu năng, phải diễn đạt đúng quan hệ giữa các phần tử mảng.

## 9. Multikey index với sort

Sắp xếp dữ liệu liên quan đến mảng có thể phức tạp hơn sắp xếp trường scalar.

### 9.1. Truy vấn có cả lọc theo mảng và sort

```javascript
db.products.find({ tags: "outdoor" })
  .sort({ price: 1 });
```

Một ứng viên index:

```javascript
db.products.createIndex({
  tags: 1,
  price: 1
});
```

Compound index này có **một trường mảng** `tags` và một trường scalar `price`, vì thế có thể là một thiết kế hợp lệ. Nó có thể hỗ trợ lọc theo tag và sắp xếp theo giá tùy cách planner sử dụng index và các điều kiện khác.

### 9.2. Sort trực tiếp trên trường mảng

Nếu dùng:

```javascript
db.products.find().sort({ tags: 1 });
```

ngữ nghĩa thứ tự của array và khả năng tận dụng thứ tự index có các quy tắc riêng. Theo ngữ nghĩa so sánh mảng của MongoDB, với sort tăng dần, phần tử nhỏ nhất có thể quyết định khóa sort của mảng; với sort giảm dần, phần tử lớn nhất có thể quyết định. Không nên hiểu sort trực tiếp trên array là “lấy phần tử đầu tiên của mảng rồi sort”.

Trong nhiều trường hợp truy vấn sort liên quan multikey index có thể phải dùng **bước SORT trong bộ nhớ**, ngay cả khi index đã tồn tại, vì các điều kiện về index bounds và tiền tố đường dẫn mảng không đáp ứng yêu cầu dùng thứ tự index.

Khi tối ưu:

1. Xác định thực sự cần sort **document** theo trường nào.
2. Nếu cần sort theo một thuộc tính của phần tử mảng, xác định **phần tử nào** là đại diện của document.
3. Nếu cần sắp xếp **phần tử bên trong mảng**, dùng aggregation hoặc cập nhật mảng theo đúng ngữ nghĩa, không nhầm với sort các document.
4. Quan sát `SORT`, `IXSCAN` và index bounds trong `explain()`.

**Không có quy tắc chung rằng mọi multikey index đều có thể sort hoặc đều không thể sort.** Khả năng hỗ trợ phụ thuộc truy vấn cụ thể.

## 10. Unique multikey index: duy nhất giữa document, không khử trùng lặp trong một mảng

Đây là giới hạn rất quan trọng khi thiết kế dữ liệu.

### 10.1. Unique index trên trường mảng

Xét collection mới:

```javascript
db.uniqueTagDemo.createIndex(
  { tags: 1 },
  { unique: true }
);

db.uniqueTagDemo.insertOne({
  _id: "A",
  tags: ["mongodb", "index", "mongodb"]
});
```

Trong phạm vi cùng một document, các phần tử `"mongodb"` trùng nhau **không tự gây lỗi uniqueness của index** chỉ vì xuất hiện hai lần. MongoDB không cần nhiều entry giống hệt nhau cho cùng khóa và cùng document.

Nhưng nếu thêm:

```javascript
db.uniqueTagDemo.insertOne({
  _id: "B",
  tags: ["mongodb", "storage"]
});
```

thao tác có thể bị từ chối vì khóa `"mongodb"` của **document B** trùng với khóa đã thuộc về **document A**.

Nói cách khác, unique multikey index hạn chế **hai document cùng sở hữu một giá trị index giống nhau**; nó **không** bảo đảm mảng của một document chỉ có một bản của mỗi giá trị.

### 10.2. Có nên unique index trên tags?

Thường **không**, vì hai sản phẩm khác nhau hoàn toàn có thể cùng mang tag `"mongodb"` hoặc `"sale"`. Unique multikey index như ví dụ hữu ích để hiểu quy tắc nhưng ít phù hợp làm index nhãn sản phẩm thực tế.

Nếu muốn nhiều sản phẩm được chia sẻ tag, tạo index thường:

```javascript
db.products.createIndex({ tags: 1 });
```

Nếu muốn một tài liệu con có mã duy nhất trong phạm vi một cha, cân nhắc collection riêng với unique compound index phù hợp:

```javascript
// Mỗi cặp orderId + sku là một document riêng.
db.orderItems.createIndex(
  { orderId: 1, sku: 1 },
  { unique: true }
);
```

Index trên collection con có thể áp đặt một quy tắc rõ ràng **giữa các document dòng hàng**, thay vì cố suy ra uniqueness theo trường con bên trong một document có mảng.

## 11. Covered query: multikey index có thể cover nhưng có điều kiện

Một **covered query** là truy vấn có thể đáp ứng từ index mà không cần lấy document gốc để trả các trường yêu cầu, khi thỏa các điều kiện cần thiết.

### 11.1. Một trường mảng dùng để lọc, trường scalar dùng để trả về

Giả sử index:

```javascript
db.products.createIndex({
  tags: 1,
  category: 1
});
```

Truy vấn chỉ yêu cầu `category`:

```javascript
db.products.find(
  { tags: "outdoor" },
  { _id: 0, category: 1 }
);
```

Trong các điều kiện phù hợp, MongoDB có thể lấy trường scalar `category` từ index sau khi tìm theo tag mà không cần trả nguyên document. Vì thế **một index multikey vẫn có thể hỗ trợ covered query**.

### 11.2. Vì sao trả lại chính trường mảng thường không được cover?

```javascript
db.products.find(
  { tags: "outdoor" },
  { _id: 0, tags: 1 }
);
```

Truy vấn yêu cầu trả lại **toàn bộ mảng tags**. Các khóa multikey chỉ là biểu diễn phục vụ tìm kiếm; chúng không cung cấp mọi thông tin đầy đủ để tái tạo document mảng như dữ liệu gốc trong tất cả trường hợp. Vì vậy, điều kiện covered query đối với multikey index **không cho phép projection trả lại trường mảng đó**.

Ngoài ra, những truy vấn dùng `$elemMatch` có giới hạn riêng và không thể dùng làm covered query multikey theo quy tắc phủ index thông thường.

### 11.3. Quan sát `totalDocsExamined`

```javascript
db.products.find(
  { tags: "outdoor" },
  { _id: 0, category: 1 }
).explain("executionStats");
```

Nếu kế hoạch dùng index và `totalDocsExamined` bằng 0, đó là dấu hiệu truy vấn không cần lấy document từ storage engine để giải quyết kết quả. Cần đọc cả plan để chắc kết luận phù hợp với ngữ cảnh.

## 12. Các phương án khi gặp giới hạn index ghép nhiều mảng

Không nên chỉ cố tạo lại index hoặc bỏ index mỗi khi gặp thông báo `cannot index parallel arrays`. Trước hết cần xem **mô hình dữ liệu** và **mẫu truy vấn**.

### 12.1. Tạo hai index riêng

Với document có:

```javascript
{
  _id: "P400",
  tags: ["sale", "winter"],
  availableSizes: ["M", "L", "XL"]
}
```

hai index độc lập là hợp lệ:

```javascript
db.catalog.createIndex({ tags: 1 });
db.catalog.createIndex({ availableSizes: 1 });
```

Truy vấn:

```javascript
db.catalog.find({
  tags: "sale",
  availableSizes: "L"
});
```

có thể dùng một trong hai index, xét index intersection nếu planner hỗ trợ và thấy hữu ích, hoặc chọn kế hoạch khác. **Không mặc định** MongoDB sẽ giao hai index cho một phép giao tối ưu trong mọi trường hợp.

Khi có nhiều truy vấn phổ biến, đôi khi hai index riêng với lọc bổ sung có chi phí tổng thể tốt hơn một thiết kế document phức tạp chỉ để có compound index.

### 12.2. Ghép mảng với trường scalar có ích cho phân vùng truy vấn

Nếu truy vấn thường thêm `tenantId` hoặc `category`, có thể tạo:

```javascript
db.catalog.createIndex({
  tenantId: 1,
  tags: 1
});

db.catalog.createIndex({
  tenantId: 1,
  availableSizes: 1
});
```

Mỗi index chỉ chứa **một đường dẫn mảng**; hai index độc lập cùng tồn tại trong collection. Đây là chiến lược phổ biến khi dữ liệu được lọc theo tenant hoặc category và sau đó theo một trong các mảng.

### 12.3. Đổi hai danh sách độc lập thành một mảng embedded documents khi có quan hệ cặp

Giả sử điều người dùng muốn tìm không phải “sản phẩm có tag sale và có size L” một cách độc lập, mà là **biến thể màu đen, size L còn hàng**. Khi đó mô hình:

```javascript
{
  _id: "P500",
  colors: ["black", "blue"],
  sizes: ["M", "L"]
}
```

không đủ để xác định cặp màu-size nào thật sự bán được. Nên lưu:

```javascript
{
  _id: "P500",
  variants: [
    { color: "black", size: "M", stock: 12 },
    { color: "blue", size: "L", stock: 4 }
  ]
}
```

và sử dụng:

```javascript
db.catalog.createIndex({
  "variants.color": 1,
  "variants.size": 1
});

db.catalog.find({
  variants: {
    $elemMatch: {
      color: "black",
      size: "M"
    }
  }
});
```

Giải pháp này giúp diễn đạt **các cặp thực sự tồn tại**. Tuy vậy, không nên biến hai tập độc lập thành mảng cặp một cách máy móc; nếu nghiệp vụ cho phép mọi kết hợp thì cần xem số lượng tổ hợp, rủi ro mảng phình to và chi phí duy trì.

### 12.4. Tách quan hệ thành collection con

Với số biến thể rất lớn hoặc cần cập nhật tồn kho từng biến thể thường xuyên:

```javascript
// products
{
  _id: "P500",
  name: "Áo khoác gió"
}

// productVariants
{
  _id: "P500-black-M",
  productId: "P500",
  color: "black",
  size: "M",
  stock: 12
}
```

Có thể index:

```javascript
db.productVariants.createIndex({
  color: 1,
  size: 1,
  stock: 1
});
```

Ở collection `productVariants`, mỗi thuộc tính trong document có thể là giá trị scalar nên không vướng giới hạn parallel arrays. Có thể áp dụng unique index theo `productId, color, size` nếu nghiệp vụ cần ràng buộc mỗi biến thể là duy nhất và topology cho phép:

```javascript
db.productVariants.createIndex(
  { productId: 1, color: 1, size: 1 },
  { unique: true }
);
```

Đổi lại, đọc sản phẩm cùng tất cả biến thể có thể cần nhiều truy vấn hoặc `$lookup`. Đây là **đánh đổi giữa embed và reference**, không phải chiến lược “tách collection luôn tốt hơn”.

### 12.5. Chuẩn hóa điều kiện thành một khóa tìm kiếm có chủ đích

Nếu ứng dụng thường tìm đúng các cặp đã biết và tập cặp nhỏ, có thể lưu một trường dẫn xuất như `variantKeys`:

```javascript
{
  _id: "P500",
  variants: [
    { color: "black", size: "M" },
    { color: "blue", size: "L" }
  ],
  variantKeys: ["black|M", "blue|L"]
}
```

```javascript
db.catalog.createIndex({ variantKeys: 1 });
db.catalog.find({ variantKeys: "black|M" });
```

Giải pháp này yêu cầu thiết kế bộ mã hóa cặp khóa **không nhập nhằng**, xử lý ký tự phân cách và đồng bộ `variantKeys` với `variants` trong cùng thao tác khi cần. Nếu dữ liệu mảng đã phù hợp với `$elemMatch` và index trên subfields, không cần tạo trường dẫn xuất chỉ để có một cú pháp ngắn hơn.

## 13. Hiệu năng: một mảng dài không có nghĩa index luôn tốt

### 13.1. Multikey index làm tăng số khóa và chi phí ghi

Một document có hàng nghìn tag khác nhau có thể đóng góp nhiều entry cho một index. Nếu cập nhật tag, MongoDB phải duy trì các khóa index tương ứng. Chi phí không chỉ là dung lượng document gốc:

- **Dung lượng index** tăng theo số giá trị riêng biệt được index.
- **Bộ nhớ cache** phải phục vụ nhiều khóa index hơn.
- **Ghi** có thể tốn thêm I/O và CPU để cập nhật khóa.
- **Xây dựng index** trên collection lớn có thể tốn thời gian và tài nguyên.
- **Query** có thể phải đọc nhiều khóa nếu điều kiện kém chọn lọc, rồi loại trùng document.

Một giá trị tag như `"sale"` xuất hiện trong phần lớn sản phẩm có độ chọn lọc thấp. Index trên tag đó có thể không giảm nhiều công việc so với quét collection, đặc biệt nếu truy vấn trả về rất nhiều document.

### 13.2. Một document có thể khớp nhiều khóa

Với điều kiện trên mảng như:

```javascript
db.products.find({
  tags: { $in: ["outdoor", "waterproof"] }
});
```

P100 có thể khớp **hai khóa index** nhưng query `find()` vẫn trả **một document P100**, không trả hai bản của cùng document chỉ vì hai phần tử thỏa điều kiện. Query execution phải quản lý việc loại trùng bản ghi khi index scan có nhiều khóa dẫn tới cùng document.

### 13.3. Multikey index và mảng không giới hạn

Nếu một document chứa lịch sử hoạt động với hàng triệu phần tử:

```javascript
{
  _id: "U01",
  activityIds: [ /* tăng không giới hạn */ ]
}
```

thì ngay cả khi index `activityIds` giúp tìm phần tử, thiết kế vẫn có vấn đề:

- BSON document có giới hạn kích thước **16 MiB**.
- Một document rất lớn làm việc đọc/ghi nặng.
- Mảng có số lượng khóa index khổng lồ làm tăng tài nguyên.
- Nhiều ghi đồng thời vào một document có thể tạo điểm nóng.

Trong tình huống này, tách hoạt động thành collection riêng theo `userId` và `activityId` thường là một hướng cần cân nhắc. Multikey index không thay được thiết kế vòng đời dữ liệu.

## 14. Quy trình khảo sát index trước khi triển khai

Với yêu cầu “lọc sản phẩm theo tag, category, size và màu”, có thể làm theo các bước:

### Bước 1 — Xác định ngữ nghĩa điều kiện

Đang tìm:

- Sản phẩm có tag `sale` **và** có bất kỳ size `L`?
- Hay sản phẩm có **một biến thể** cùng thỏa `color = black`, `size = L`, `stock > 0`?

Nếu là trường hợp thứ hai, cần cấu trúc dữ liệu bảo toàn quan hệ giữa thuộc tính của cùng biến thể và thường cần `$elemMatch`.

### Bước 2 — Xác định field path nào đi qua mảng

Ví dụ:

```text
category                 scalar
tags                     array #1
availableSizes           array #2
variants                 array #3 (các embedded documents)
variants.color           thuộc array path variants
variants.size            thuộc cùng array path variants
```

Đếm các **mảng độc lập được index trong cùng một document**, không đơn giản đếm số trường trong index key.

### Bước 3 — Đề xuất ít index có mục tiêu

```javascript
// Lọc theo category và tag.
{ category: 1, tags: 1 }

// Lọc theo category và size độc lập.
{ category: 1, availableSizes: 1 }

// Lọc theo cặp thuộc tính trong cùng biến thể.
{ "variants.color": 1, "variants.size": 1 }
```

Tránh đề xuất `{ tags: 1, availableSizes: 1 }` khi document thực tế chứa hai mảng độc lập.

### Bước 4 — Dùng `explain()`

```javascript
db.variantCatalog.find({
  variants: {
    $elemMatch: {
      color: "black",
      size: "L"
    }
  }
}).explain("executionStats");
```

Quan sát index được chọn, `IXSCAN`, `FETCH`, index bounds, `totalKeysExamined`, `totalDocsExamined` và `nReturned`. Không chỉ nhìn thời gian thực thi của một lần chạy, đặc biệt khi cache nóng/lạnh và kích thước dữ liệu khác nhau.

### Bước 5 — Đo tải ghi và dung lượng

Với collection lớn, chi phí index có thể phát sinh chủ yếu khi thêm phần tử vào mảng, thay đổi biến thể hoặc xây lại nhiều khóa. Hãy cân nhắc:

- Tần suất ghi cập nhật mảng.
- Số phần tử trung bình và phân bố cực đại.
- Độ chọn lọc của query.
- Số lượng index mà mỗi thao tác phải cập nhật.
- Thời gian build index và tài nguyên lưu trữ cần thiết.

### Bước 6 — Quản lý index theo topology

Trên sharded collection, còn cần xét ràng buộc của shard key, unique index và phân bố dữ liệu. Không suy từ khả năng tạo một compound multikey index trên collection thường rằng nó mặc nhiên phù hợp làm **shard key index**. Các quy tắc này khác nhau và cần được xem xét riêng trước khi đưa vào hệ thống phân mảnh.

## 15. Những hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Phải bật `multikey: true` khi tạo index | MongoDB tự xác định index multikey khi đường dẫn index chứa array |
| Mỗi document chỉ đóng góp đúng một khóa cho index | Trường mảng có thể sinh nhiều khóa liên quan đến các phần tử |
| Một document có hai mảng là không hợp lệ | Document hoàn toàn có thể có nhiều mảng; giới hạn nằm ở compound index trên các array path độc lập |
| Một collection chỉ được có một multikey index | Có thể có nhiều index riêng trên các trường mảng khác nhau |
| `{ tags: 1, sizes: 1 }` luôn hợp lệ vì từng trường đều index được | Không hợp lệ với document chứa cả hai mảng độc lập |
| Chỉ kiểm tra giới hạn khi tạo index | Insert/update về sau cũng có thể bị từ chối nếu tạo parallel arrays |
| Hai trường từ cùng mảng embedded documents cũng luôn bị cấm | Có thể tạo compound multikey index trên các đường dẫn liên quan trong cùng array path |
| Dotted predicates luôn khớp cùng embedded document | Có thể khớp ở hai phần tử khác nhau; cần `$elemMatch` để ràng buộc cùng phần tử |
| Multikey index luôn compounding được mọi bounds | Cần xét `$elemMatch`, array path và ngữ nghĩa điều kiện |
| Unique multikey index xóa trùng trong một mảng | Nó ràng buộc giữa các document, không tự khử trùng phần tử của một document |
| Multikey index không thể cover bất cứ query nào | Có thể cover khi thỏa các điều kiện, nhưng thường không khi projection trả mảng hoặc query dùng `$elemMatch` |
| Có index trên mảng là `$size` nhanh ngay | `$size` không tự được giải quyết từ các entry phần tử để lấy độ dài mảng |
| Tạo càng nhiều index cho array càng tốt | Index làm tăng chi phí ghi, dung lượng và bảo trì |
| `IXSCAN` đồng nghĩa query tối ưu | Cần xem số khóa/tài liệu đã đọc và kết quả thực tế |

## 16. Bài tập thực hành

### Bài 1 — Dự đoán các khóa của multikey index

Cho:

```javascript
{
  _id: "P1",
  category: "BOOK",
  tags: ["mongodb", "database", "mongodb"]
}
```

Hãy mô tả các giá trị khóa có ý nghĩa tìm kiếm khi tạo:

```javascript
db.exercise.createIndex({ tags: 1 });
db.exercise.createIndex({ category: 1, tags: 1 });
```

Giải thích vì sao cùng một giá trị `"mongodb"` xuất hiện hai lần trong mảng **không nhất thiết tạo hai entry trùng nhau cho cùng document**.

### Bài 2 — Phát hiện parallel arrays

Cho ba document:

```javascript
{ _id: 1, a: [1, 2], b: 5 }
{ _id: 2, a: 3,      b: [7, 8] }
{ _id: 3, a: [1, 2], b: [7, 8] }
```

Hãy giải thích:

1. Khi chỉ có hai document đầu, index `{ a: 1, b: 1 }` có thể được tạo không?
2. Khi thêm document thứ ba trước khi tạo index, điều gì xảy ra nếu tạo index?
3. Nếu index đã tồn tại từ trước, điều gì xảy ra khi insert document thứ ba?
4. Vì sao quy tắc này không có nghĩa “collection chỉ được chứa một array field”?

### Bài 3 — Điều kiện trên cùng phần tử embedded document

Cho:

```javascript
{
  _id: "P2",
  variants: [
    { color: "black", size: "M" },
    { color: "blue", size: "L" }
  ]
}
```

Hãy dự đoán P2 có khớp các filter sau hay không:

```javascript
// A
{
  "variants.color": "black",
  "variants.size": "L"
}

// B
{
  variants: {
    $elemMatch: {
      color: "black",
      size: "L"
    }
  }
}
```

Giải thích sự khác nhau và đề xuất index compound multikey thích hợp cho trường hợp B.

### Bài 4 — Giao điều kiện trên một mảng số

Với:

```javascript
{ _id: "A", scores: [65, 98] }
{ _id: "B", scores: [75, 82] }
```

Hãy so sánh:

```javascript
db.exams.find({
  scores: { $gte: 70, $lte: 90 }
});

db.exams.find({
  scores: {
    $elemMatch: { $gte: 70, $lte: 90 }
  }
});
```

Điều kiện nào cho phép MongoDB hiểu **cùng một phần tử** phải nằm trong khoảng? Điều đó ảnh hưởng đến cách intersect bounds của multikey index như thế nào?

### Bài 5 — Unique multikey

Cho index:

```javascript
db.tagsDemo.createIndex({ tags: 1 }, { unique: true });
```

Dự đoán:

```javascript
db.tagsDemo.insertOne({ _id: 1, tags: ["a", "a", "b"] });
db.tagsDemo.insertOne({ _id: 2, tags: ["b", "c"] });
```

Tại sao document đầu có thể được chấp nhận dù `"a"` lặp hai lần, nhưng document thứ hai có thể bị từ chối? Nếu yêu cầu nghiệp vụ là **mỗi document không có tag trùng**, cần xử lý ở đâu?

### Bài 6 — Covered query và projection

Tạo dữ liệu/index:

```javascript
db.coveredDemo.insertOne({
  _id: "D1",
  tags: ["a", "b"],
  category: "C1",
  description: "Văn bản dài"
});

db.coveredDemo.createIndex({ tags: 1, category: 1 });
```

So sánh:

```javascript
db.coveredDemo.find(
  { tags: "a" },
  { _id: 0, category: 1 }
);

db.coveredDemo.find(
  { tags: "a" },
  { _id: 0, tags: 1 }
);
```

Truy vấn nào có khả năng được cover bởi index? Vì sao trả lại mảng `tags` khác với chỉ trả field scalar `category`?

### Bài 7 — Thiết kế cho hệ thống thương mại điện tử

Một sản phẩm có:

- `tags`: nhiều nhãn tiếp thị.
- `availableSizes`: danh sách size có thể bán.
- `variants`: từng biến thể màu-size-tồn kho.
- `categoryId`: một danh mục.

Ứng dụng thường thực hiện ba query:

1. Tìm sản phẩm theo `categoryId` và tag `"sale"`.
2. Tìm sản phẩm có bất kỳ size `"L"`, độc lập với màu.
3. Tìm sản phẩm có **một biến thể** màu black, size L và còn hàng.

Hãy đề xuất index cho từng query. Giải thích tại sao không nhất thiết nên đưa `tags` và `availableSizes` vào **một compound index**. Trường hợp nào cần `$elemMatch`?

### Bài 8 — Khi nào nên tách collection?

Một sản phẩm có 30.000 biến thể và tồn kho thay đổi liên tục. So sánh:

- Nhúng toàn bộ `variants` vào một document `products` và dùng multikey index.
- Tạo collection `productVariants`, mỗi biến thể là một document có `productId, color, size, stock`.

Đánh giá kích thước document, index, cạnh tranh ghi, yêu cầu truy vấn, bảo đảm nguyên tử và chi phí kết hợp dữ liệu. Không chọn mô hình chỉ vì một lệnh `find()` trông ngắn hơn.

## 17. Ghi nhớ

**Multikey index cho phép MongoDB index các phần tử mảng.** Một document có thể đóng góp nhiều khóa index; khả năng này giúp truy vấn theo tag, điểm số hoặc thuộc tính trong embedded documents hiệu quả hơn trong những điều kiện phù hợp.

**Giới hạn compound multikey quan trọng nhất là parallel arrays.** Không thể index ghép hai array path độc lập đang xuất hiện cùng lúc trong một document bằng một compound index. Quy tắc được kiểm tra cả lúc tạo index và lúc ghi dữ liệu về sau; nó không cấm một collection có nhiều mảng hoặc nhiều multikey index riêng.

**Mảng embedded documents có quan hệ cùng phần tử.** Các thuộc tính cùng đi qua một array path có thể tham gia compound multikey index; khi truy vấn yêu cầu các điều kiện thuộc **cùng một phần tử**, hãy sử dụng `$elemMatch` để biểu đạt đúng ngữ nghĩa và hỗ trợ xử lý bounds.

**Index không thay thế thiết kế dữ liệu.** Unique multikey không tự chống phần tử trùng trong một document, `$size` không được giải quyết tự động bởi index, và sort/covered query có những điều kiện riêng. Khi gặp giới hạn index ghép nhiều mảng, hãy cân nhắc index riêng, scalar + array, mảng embedded documents hoặc collection con theo mẫu truy cập thực tế.
