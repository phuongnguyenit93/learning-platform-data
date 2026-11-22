# Tìm kiếm bằng $regex và điều kiện có thể tận dụng index trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Tìm kiếm văn bản

## 1. Bài toán và mục tiêu

Một ứng dụng bán hàng cho phép người dùng tìm sản phẩm theo tên hoặc SKU. Những yêu cầu thường gặp:

- SKU **bắt đầu** bằng `PH`.
- Tên **chứa** `phone` ở vị trí bất kỳ.
- SKU **kết thúc** bằng `-VN`.
- Tên bắt đầu bằng `phone` nhưng **không phân biệt hoa/thường**.
- Mã literal chứa dấu chấm hoặc dấu cộng, chẳng hạn `AB.42` hay `C++`.

Chúng có thể được diễn đạt bằng regex:

~~~javascript
db.products.find({ sku: /^PH/ });
db.products.find({ name: /phone/ });
db.products.find({ sku: /-VN$/ });
db.products.find({ name: /^phone/i });
~~~

Tuy nhiên, những regex này **không có cùng khả năng tận dụng B-tree index**.

**Nguyên tắc trọng tâm:** Regex **phân biệt hoa/thường**, có anchor đầu chuỗi `^` hoặc `\A` và **theo sau ngay bằng một literal prefix đơn giản** có thể giúp MongoDB tạo một khoảng quét index hẹp. Regex contains, suffix, wildcard đầu chuỗi hoặc dùng cờ `i` thường không nhận được cùng lợi thế.

Bài học giúp bạn:

1. Sử dụng `$regex` và `$options` đúng cú pháp.
2. Phân biệt exact, prefix, contains và suffix.
3. Biết điều kiện nào tạo **prefix expression** có thể dùng index range.
4. Đọc `explain("executionStats")` và hiểu `IXSCAN` không tự đồng nghĩa truy vấn nhanh.
5. Kết hợp equality filters với regex trong compound index.
6. Hiểu vì sao case-insensitive collation index không tự tối ưu regex `i`.
7. Chọn field chuẩn hóa khi cần prefix search không phân biệt case.
8. Escape user input và kiểm soát regex tốn CPU.
9. Dùng MongoDB Java Sync Driver thực hành.
10. Biết khi nào nên dùng text index hoặc MongoDB Search.

## 2. Regex là tìm mẫu chuỗi, không phải tìm kiếm ngữ nghĩa

Toán tử `$regex` là query predicate kiểm tra chuỗi khớp biểu thức chính quy (*regular expression*).

~~~javascript
db.products.find({
  name: { $regex: "phone" }
});
~~~

Có thể khớp `phone case`, `smartphone cover`, `headphone` hoặc `new phone stand`.

~~~javascript
db.products.find({
  name: { $regex: "^phone" }
});
~~~

Chỉ khớp chuỗi bắt đầu bằng `phone` theo chế độ regex thông thường.

Regex **không tự** cung cấp:

- Tách từ tiếng Việt và hiểu đồng nghĩa.
- Fuzzy matching khi gõ sai.
- Stemming, tokenization hoặc language analyzer.
- Chấm điểm độ liên quan và sắp xếp theo relevance.
- Bỏ dấu tiếng Việt.
- Search theo một từ nằm trong giữa văn bản với cùng hiệu năng của prefix index.

### 2.1. Những cú pháp regex cơ bản

| Pattern | Ý nghĩa |
|---|---|
| `/^PH/` | Bắt đầu bằng PH |
| `/PH/` | Có PH ở bất kỳ vị trí |
| `/PH$/` | Kết thúc bằng PH |
| `/^PH$/` | Khớp toàn chuỗi PH |
| `/^PH-\d{3}$/` | PH- theo sau ba chữ số |
| `/^PH[0-9]/` | Bắt đầu PH rồi một chữ số |
| `/^P[Hh]/` | Bắt đầu P rồi H hoặc h |
| `/^(PH|TAB)/` | Bắt đầu PH hoặc TAB |
| `/^phone/i` | Bắt đầu phone không phân biệt case |
| `/\bphone\b/` | Match word boundary theo regex engine |

Các ký tự `.`, `*`, `+`, `?`, `[ ]`, `( )`, `|`, `^`, `$` và `\` đều có vai trò đặc biệt. Chỉ dùng chúng như regex operators nếu người dùng **thực sự yêu cầu tìm theo regex**.

## 3. Hai cách viết $regex trong mongosh

### 3.1. Dạng regex literal

~~~javascript
db.products.find({ sku: /^PH/ });

db.products.find({
  sku: { $regex: /^PH/ }
});
~~~

### 3.2. Dạng string

~~~javascript
db.products.find({
  sku: { $regex: "^PH" }
});

db.products.find({
  name: {
    $regex: "^phone",
    $options: "i"
  }
});
~~~

Dạng string thuận tiện khi dựng query ở runtime hoặc dùng cú pháp PCRE2 không biểu diễn được bằng JavaScript RegExp literal.

### 3.3. Các options thường gặp

| Flag | Ý nghĩa | Đánh đổi |
|---|---|---|
| `i` | Không phân biệt case | Không có cùng ưu thế prefix case-sensitive |
| `m` | Multiline, `^`/`$` có thể xét biên dòng | Anchor không còn chỉ đầu toàn chuỗi |
| `s` | Dot-all, dấu `.` khớp newline | Không cần cho prefix đơn giản |
| `x` | Bỏ qua một số khoảng trắng và comment regex | Cần chú ý nếu pattern chứa khoảng trắng literal |

~~~javascript
db.products.find({
  description: {
    $regex: "phone.*case",
    $options: "is"
  }
});
~~~

### 3.4. Escaping khi pattern là JavaScript string

~~~javascript
// Regex literal.
db.products.find({ sku: /^PH-\d+/ });

// Trong string cần escape backslash.
db.products.find({
  sku: { $regex: "^PH-\\d+" }
});
~~~

MongoDB Server sử dụng **PCRE2 từ phiên bản 6.1**. Một số constructs PCRE2 có thể khác JavaScript regex; vì vậy không tự động chuyển mọi JavaScript RegExp thành biểu thức PCRE2 nâng cao rồi kỳ vọng semantics giống hệt.

Ví dụ một PCRE2 pattern string có phạm vi case-insensitive:

~~~javascript
db.products.find({
  sku: { $regex: "(?i)ph(?-i)-100" }
});
~~~

Việc một regex được PCRE2 hỗ trợ **không đồng nghĩa nó có thể tạo index prefix bounds**.

## 4. Bộ dữ liệu thực hành

Mở `mongosh` trên MongoDB mà bạn có quyền sử dụng và dùng database lab riêng:

~~~javascript
const lab = db.getSiblingDB("regex_index_lab");
const products = lab.getCollection("products");

products.insertMany([
  {
    _id: 1, tenantId: "t1", status: "ACTIVE",
    sku: "PH-100", name: "Phone Case",
    nameLower: "phone case", category: "accessory"
  },
  {
    _id: 2, tenantId: "t1", status: "ACTIVE",
    sku: "PH-101", name: "Phone Charger",
    nameLower: "phone charger", category: "accessory"
  },
  {
    _id: 3, tenantId: "t1", status: "ACTIVE",
    sku: "PH-102", name: "Phone Stand",
    nameLower: "phone stand", category: "accessory"
  },
  {
    _id: 4, tenantId: "t1", status: "ACTIVE",
    sku: "TAB-100", name: "Tablet Stand",
    nameLower: "tablet stand", category: "accessory"
  },
  {
    _id: 5, tenantId: "t1", status: "ARCHIVED",
    sku: "PH-200", name: "Phone Case Old",
    nameLower: "phone case old", category: "accessory"
  },
  {
    _id: 6, tenantId: "t1", status: "ACTIVE",
    sku: "XPH-300", name: "Smartphone Cover",
    nameLower: "smartphone cover", category: "accessory"
  },
  {
    _id: 7, tenantId: "t1", status: "ACTIVE",
    sku: "PH-VN", name: "iPhone 15",
    nameLower: "iphone 15", category: "device"
  },
  {
    _id: 8, tenantId: "t1", status: "ACTIVE",
    sku: "ph-103", name: "iphone Mini",
    nameLower: "iphone mini", category: "device"
  },
  {
    _id: 9, tenantId: "t1", status: "ACTIVE",
    sku: "LAP-VN", name: "Laptop Pro",
    nameLower: "laptop pro", category: "device"
  },
  {
    _id: 10, tenantId: "t1", status: "ACTIVE",
    sku: "AB.42", name: "Cable USB-C",
    nameLower: "cable usb-c", category: "accessory"
  },
  {
    _id: 11, tenantId: "t2", status: "ACTIVE",
    sku: "PH-100", name: "Phone Case",
    nameLower: "phone case", category: "accessory"
  },
  {
    _id: 12, tenantId: "t2", status: "ACTIVE",
    sku: "PH-900", name: "phone headset",
    nameLower: "phone headset", category: "accessory"
  },
  {
    _id: 13, tenantId: "t2", status: "ACTIVE",
    sku: "TAB-500", name: "Tablet",
    nameLower: "tablet", category: "device"
  },
  {
    _id: 14, tenantId: "t1", status: "ACTIVE",
    sku: "VN-PH", name: "Headphone",
    nameLower: "headphone", category: "device"
  },
  {
    _id: 15, tenantId: "t1", status: "ACTIVE",
    sku: "NOTE-01", name: "Điện thoại phổ thông",
    nameLower: "điện thoại phổ thông", category: "device"
  },
  {
    _id: 16, tenantId: "t1", status: "ACTIVE",
    sku: "NOTE-02", name: "Điện Thoại Thông Minh",
    nameLower: "điện thoại thông minh", category: "device"
  },
  {
    _id: 17, tenantId: "t1", status: "ACTIVE",
    sku: "PH-777", name: "Phone Grip",
    nameLower: "phone grip", category: "accessory"
  },
  {
    _id: 18, tenantId: "t1", status: "ACTIVE",
    sku: "CASE-PH", name: "New phone case",
    nameLower: "new phone case", category: "accessory"
  }
]);

print("Products:", products.countDocuments({}));
~~~

Tập mẫu có **18 documents**. Chạy phần tạo dữ liệu đúng một lần trên database lab trống; nếu chạy lại, các `_id` trùng sẽ gây duplicate key. Không dùng `dropDatabase()` trên dữ liệu production hoặc database dùng chung để chạy lại bài.

### 4.1. Tạo các index

~~~javascript
products.createIndex(
  { sku: 1 },
  { name: "idx_sku" }
);
products.createIndex(
  { name: 1 },
  { name: "idx_name" }
);
products.createIndex(
  { nameLower: 1 },
  { name: "idx_name_lower" }
);
products.createIndex(
  { tenantId: 1, status: 1, sku: 1 },
  { name: "idx_tenant_status_sku" }
);

printjson(products.getIndexes());
~~~

Đây là các **index ứng viên cho bài lab**. Không sao chép tất cả sang production: mỗi index tăng chi phí ghi và dung lượng.

## 5. Prefix expression: khi nào regex tận dụng được B-tree index range?

MongoDB documentation mô tả **prefix expression** là một regex:

1. Bắt đầu bằng anchor `^` hoặc `\A`.
2. Theo sau là một chuỗi ký tự **đơn giản, cố định** mà mọi chuỗi khớp đều phải bắt đầu bằng chuỗi đó.

Ví dụ:

~~~javascript
products.find({ sku: /^PH/ });
~~~

Với index `{sku:1}`, MongoDB có thể suy ra **index range** cho những khóa bắt đầu bằng `PH`.

### 5.1. Hình dung index có thứ tự

~~~text
AB.42
CASE-PH
LAP-VN
NOTE-01
NOTE-02
PH-100       ┐
PH-101       │
PH-102       │  Vùng key có tiền tố PH
PH-200       │
PH-777       │
PH-900       │
PH-VN        ┘
TAB-100
VN-PH
XPH-300
ph-103
~~~

B-tree index sắp giá trị theo thứ tự, nên có thể đọc một vùng gần nhau thay vì quét mọi khóa.

Không nên tự xây upper bound bằng cách cộng một đơn vị cho ký tự cuối. MongoDB/query planner có cơ chế tạo bounds theo loại index, collation, pattern và server version.

### 5.2. ^ là anchor, nhưng chỉ ^ chưa đủ

~~~javascript
// Có prefix PH rõ ràng.
products.find({ sku: /^PH/ });

// Dấu ^ vẫn có mặt nhưng phần đầu bị .* ăn tùy ý.
products.find({ sku: /^.*PH/ });
~~~

Regex thứ hai **không yêu cầu** SKU bắt đầu bằng PH; nó có thể khớp `XPH-300` hoặc `CASE-PH`. Vì vậy không có tiền tố PH chung để tạo cùng index range.

### 5.3. \A trong PCRE

Ký hiệu `\A` neo đầu toàn chuỗi. Khi dùng ở mongosh, chọn pattern dạng string:

~~~javascript
products.find({
  sku: { $regex: "\\APH" }
});
~~~

JavaScript string `"\\APH"` đại diện cho PCRE pattern `\APH` sau khi giải mã. Không nhầm nó với regex literal mà JavaScript parser diễn giải theo luật của JavaScript RegExp.

### 5.4. Các dạng regex và khả năng suy ra prefix

| Regex | Tiền tố cố định | Ý nghĩa về index |
|---|---|---|
| `/^PH/` | PH | Ứng viên tốt |
| `/^PH-10/` | PH-10 | Dải có thể chọn lọc hơn |
| `/^PH.*/` | PH | Có thể dùng bounds nhưng thêm work |
| `/^PH.*$/` | PH | Có thể có bounds, phần sau thường không cần |
| `/^PH[0-9]/` | PH | Phải kiểm tra tiếp chữ số |
| `/^P[Hh]/` | P | Prefix literal ngắn hơn |
| `/^.*PH/` | Không hữu ích | Wildcard đứng trước literal |
| `/PH/` | Không | Contains |
| `/PH$/` | Không | Suffix |
| `/^ph/i` | Có anchor nhưng case-insensitive | Không có cùng prefix optimization |
| `/^(PH|TAB)/` | Nhiều lựa chọn | Không giả định tối ưu như prefix duy nhất |
| `/^[A-Z]+PH/` | Không có literal cụ thể đầu chuỗi | Không kỳ vọng prefix bounds hẹp |

**Lưu ý:** Regex không có literal prefix có thể vẫn được planner đưa qua `IXSCAN` để kiểm tra nhiều index entries. Điều khác biệt là **có quét được một khoảng hẹp không**, chứ không chỉ “index có được nhắc tới hay không”.

## 6. Vì sao /^a/ tốt hơn /^a.*/ và /^a.*$/?

MongoDB documentation nêu ba biểu thức:

~~~javascript
/^a/
/^a.*/
/^a.*$/
~~~

Với giá trị một dòng thông thường, chúng có thể khớp các chuỗi bắt đầu bằng `a` như nhau, nhưng có **đặc tính hiệu năng khác nhau**.

- `/^a/` biểu diễn điều kiện tiền tố trực tiếp; có thể dừng khi không còn key nằm trong range.
- `/^a.*/` thêm phần `.*` mà việc tìm startsWith không cần.
- `/^a.*$/` còn biểu diễn phần đến cuối chuỗi, không đem lại lợi thế cho mục tiêu prefix đơn giản.

Vì vậy:

~~~javascript
// Nên ưu tiên khi chỉ cần startsWith.
products.find({ sku: /^PH/ });

// Không cần thêm .* chỉ để match SKU dài hơn.
products.find({ sku: /^PH.*/ });
~~~

Regex `/^PH/` đã match `PH-100`; không có yêu cầu toàn chuỗi phải chỉ gồm PH.

**Cẩn trọng:** Newline, `m` hoặc `s` options có thể làm semantics của `.`, `^`, `$` thay đổi. Khuyến nghị trên dành cho chuỗi mã/tên một dòng và mục tiêu prefix search.

## 7. Contains và suffix: tại sao B-tree kém hữu ích?

### 7.1. Contains

~~~javascript
products.find({ sku: /PH/ });
~~~

Có thể match:

- `PH-100`.
- `XPH-300`.
- `VN-PH`.
- `CASE-PH`.

Những giá trị đó không bắt đầu bằng cùng một literal, nên B-tree sắp theo đầu chuỗi không thể tạo một range như `/^PH/`.

### 7.2. Suffix

~~~javascript
products.find({ sku: /-VN$/ });
~~~

Có thể match `PH-VN` và `LAP-VN`. Các chuỗi có hậu tố giống nhau không nhất thiết nằm cạnh nhau trong index trên toàn SKU.

### 7.3. Kỹ thuật reversed field cho suffix query

Nếu tìm suffix thường xuyên, có thể lưu giá trị đảo ngược:

~~~javascript
{
  sku: "LAP-VN",
  skuReversed: "NV-PAL"
}
~~~

Tạo index `{skuReversed:1}` rồi tìm:

~~~javascript
products.find({
  skuReversed: /^NV-/
});
~~~

Nhược điểm:

- Thêm field và index.
- Cần cập nhật khi SKU thay đổi.
- Phải xử lý đúng Unicode/code points nếu không chỉ là mã ASCII.
- Không có ích nếu người dùng chủ yếu cần full-text hoặc fuzzy search.

Đây là một giải pháp data modeling có chủ đích, không phải tính năng tích hợp sẵn của regex.

## 8. Exact match: nên dùng equality

Với SKU chính xác `PH-100`:

~~~javascript
products.find({ sku: "PH-100" });
~~~

thường rõ và phù hợp hơn:

~~~javascript
products.find({ sku: /^PH-100$/ });
~~~

Equality tận dụng equality bounds trực tiếp, không cần regex engine và dễ phối hợp compound/unique indexes.

Nếu cần equality không phân biệt case, có thể sử dụng collation thích hợp hoặc normalized key.

## 9. i flag và case-insensitive index là hai chuyện khác nhau

### 9.1. Case-sensitive

~~~javascript
products.find({ name: /^Phone/ });
~~~

Khớp `Phone Case` nhưng không tự khớp `phone headset`.

### 9.2. Case-insensitive

~~~javascript
products.find({ name: /^phone/i });
~~~

Khớp nhiều kiểu chữ hơn nhưng không nhận được cùng ưu thế **literal prefix bounds** như regex case-sensitive.

### 9.3. Collation index không làm $regex tự tối ưu

Ví dụ tạo index:

~~~javascript
products.createIndex(
  { name: 1 },
  {
    name: "idx_name_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Equality với cùng collation:

~~~javascript
products.find({
  name: "phone case"
}).collation({
  locale: "en",
  strength: 2
});
~~~

có thể dùng index phù hợp.

Nhưng regex:

~~~javascript
products.find({
  name: /^phone/i
}).collation({
  locale: "en",
  strength: 2
});
~~~

**không tự có prefix optimization từ case-insensitive collation index**. MongoDB docs nhấn mạnh rằng regex không collation-aware, nên case-insensitive indexes không tăng tốc regex theo cách người dùng thường nghĩ.

### 9.4. Normalized search field

Khi ứng dụng chủ yếu cần case-insensitive prefix autocomplete, có thể lưu:

~~~javascript
{
  name: "Phone Charger",
  nameLower: "phone charger"
}
~~~

Tạo index:

~~~javascript
products.createIndex({ nameLower: 1 });
~~~

Tìm bằng regex phân biệt case trên key đã chuẩn hóa:

~~~javascript
products.find({ nameLower: /^pho/ });
~~~

Quy trình phải:

- Tạo `nameLower` cùng quy tắc khi insert/update.
- Chuẩn hóa user input bằng cùng thuật toán.
- Backfill dữ liệu cũ.
- Kiểm tra Unicode, locale và trường hợp accent-insensitive riêng.
- Đánh giá chi phí field/index bổ sung.

## 10. Tiếng Việt và Unicode

Cờ `i` không tự loại dấu:

~~~javascript
products.find({
  name: /dien thoai/i
});
~~~

không được mặc định match `Điện thoại phổ thông`.

Cần phân biệt:

1. **Case-insensitive**: `Phone` và `phone`.
2. **Accent-insensitive**: `điện` và `dien`.
3. **Unicode normalization**: cùng ký tự nhìn thấy nhưng cách mã hóa khác.
4. **Word segmentation**: xác định đơn vị từ/cụm từ.
5. **Fuzzy search**: sửa lỗi gõ.

Nếu sản phẩm cần không phân biệt dấu tiếng Việt, hãy thiết kế searchable key hoặc Search analyzer nhất quán; tránh tự nhận `toLowerCase()` hoặc `/i` giải quyết mọi trường hợp.

MongoDB 6.1+ hỗ trợ một số PCRE2 Unicode options như `(*UCP)`, có chi phí xử lý bổ sung. Ví dụ dùng trong pattern string:

~~~javascript
products.find({
  name: { $regex: "(*UCP)\\bphone\\b" }
});
~~~

Word boundary Unicode không đồng nghĩa phân tách từ tiếng Việt hoặc xử lý đồng nghĩa.

## 11. Equality + prefix trong compound index

Một API thường cần lọc theo tenant, trạng thái, rồi prefix SKU:

~~~javascript
products.find({
  tenantId: "t1",
  status: "ACTIVE",
  sku: /^PH/
});
~~~

Index ứng viên:

~~~javascript
products.createIndex(
  { tenantId: 1, status: 1, sku: 1 },
  { name: "idx_tenant_status_sku" }
);
~~~

Với query này:

- `tenantId` là equality.
- `status` là equality.
- `sku` có thể có prefix range.

Đây là pattern thuận lợi cho index theo thứ tự equality fields trước, range field sau.

### 11.1. Leading fields quan trọng

Index `{tenantId:1,status:1,sku:1}` không tự phù hợp như `{sku:1}` đối với:

~~~javascript
products.find({ sku: /^PH/ });
~~~

vì query thiếu equality trên các field dẫn đầu.

Nếu có query toàn hệ thống theo SKU, có thể cần index riêng `{sku:1}`; hãy cân nhắc chi phí ghi và workload.

### 11.2. Nếu không có điều kiện status

~~~javascript
products.find({
  tenantId: "t1",
  sku: /^PH/
});
~~~

Index có `status` nằm giữa `tenantId` và `sku` chưa được ràng buộc. Có thể cần một index `{tenantId:1,sku:1}` nếu đây là query nóng. Đừng tạo vô số index theo mọi tổ hợp có thể có.

### 11.3. Prefix quá ngắn

Regex `/^P/` có thể match phần lớn sản phẩm. **Indexable** không đồng nghĩa **selective**. Nếu prefix quá phổ biến, index range vẫn có thể lớn, thậm chí collection scan có thể rẻ hơn.

### 11.4. Sort

~~~javascript
products.find({
  tenantId: "t1",
  status: "ACTIVE",
  sku: /^PH/
}).sort({ sku: 1 }).limit(20);
~~~

Index compound có thể hỗ trợ filter/sort khi thứ tự phù hợp. Nhưng nếu sort theo một field khác sau regex range, không được mặc định thêm field ấy cuối index sẽ luôn tránh sort trên tất cả kết quả.

## 12. $or, $in, $not và nhiều regex

### 12.1. Hai prefix khác nhau

~~~javascript
products.find({
  tenantId: "t1",
  $or: [
    { sku: /^PH/ },
    { sku: /^TAB/ }
  ]
});
~~~

MongoDB có thể lập kế hoạch cho mỗi nhánh nếu index phù hợp, nhưng cần explain.

Regex gộp:

~~~javascript
products.find({
  sku: /^(PH|TAB)/
});
~~~

không được mặc định tạo hai khoảng range hiệu quả như query OR tường minh.

### 12.2. $in nhận regex literals

~~~javascript
products.find({
  sku: {
    $in: [/^PH/, /^TAB/]
  }
});
~~~

Nhưng không dùng object `{$regex:"..."}` bên trong mảng `$in` để thay regex literal:

~~~javascript
// Không phải dạng $in regex được hỗ trợ.
products.find({
  sku: {
    $in: [
      { $regex: "^PH" },
      { $regex: "^TAB" }
    ]
  }
});
~~~

Khi cần `$regex` dạng chuỗi cùng `$options`, dùng `$or` cho từng predicate.

### 12.3. $not

~~~javascript
products.find({
  sku: { $not: /^PH/ }
});
~~~

Điều kiện phủ định có thể trả hầu hết collection và thường không chọn lọc. Không coi một negative regex là index-efficient chỉ vì có anchor.

### 12.4. Hai regex cùng field

~~~javascript
products.find({
  $and: [
    { sku: /^PH/ },
    { sku: /VN$/ }
  ]
});
~~~

Planner có thể dùng prefix để thu hẹp rồi áp suffix regex làm residual filter. Không kỳ vọng cả hai tự tạo một index range duy nhất chính xác.

## 13. $regex trong aggregation khác $regexMatch

Predicate trong `$match`:

~~~javascript
products.aggregate([
  {
    $match: {
      tenantId: "t1",
      sku: /^PH/
    }
  },
  {
    $project: { sku: 1, name: 1 }
  }
]);
~~~

Có thể được optimizer đẩy tới phần quét index khi pipeline đủ điều kiện.

Trong khi `$regexMatch` là aggregation expression tạo boolean:

~~~javascript
products.aggregate([
  {
    $project: {
      sku: 1,
      startsWithPH: {
        $regexMatch: {
          input: "$sku",
          regex: "^PH"
        }
      }
    }
  }
]);
~~~

Nếu chỉ cần lọc document, không tự coi:

~~~javascript
{
  $match: {
    $expr: {
      $regexMatch: {
        input: "$sku",
        regex: "^PH"
      }
    }
  }
}
~~~

là tương đương về index optimization với:

~~~javascript
{ $match: { sku: /^PH/ } }
~~~

Tương tự, tính `$toLower: "$name"` trong pipeline không làm index trên field `name` tự biến thành index của kết quả lowercase.

## 14. Đọc explain("executionStats")

~~~javascript
const result = products.find({
  sku: /^PH/
}).explain("executionStats");

printjson(result.queryPlanner);
printjson(result.executionStats);
~~~

Các thông tin quan trọng:

| Chỉ số | Diễn giải |
|---|---|
| `IXSCAN` | Có quét index |
| `COLLSCAN` | Quét collection |
| `FETCH` | Lấy document sau index filtering |
| `indexBounds` | Khoảng giá trị index được xem xét |
| `totalKeysExamined` | Số index keys đã xét |
| `totalDocsExamined` | Số documents đã xét |
| `nReturned` | Số documents trả về |
| `executionTimeMillis` | Thời gian báo cáo |
| `winningPlan` | Kế hoạch được chọn |

### 14.1. Thí nghiệm ba trường hợp

~~~javascript
const tests = [
  ["prefix", /^PH/],
  ["contains", /PH/],
  ["insensitive", /^ph/i]
];

for (const [label, pattern] of tests) {
  const exp = products.find({
    sku: pattern
  }).explain("executionStats");

  printjson({
    label: label,
    nReturned: exp.executionStats.nReturned,
    keys: exp.executionStats.totalKeysExamined,
    docs: exp.executionStats.totalDocsExamined,
    millis: exp.executionStats.executionTimeMillis
  });
}
~~~

**Không kết luận tốc độ production từ 18 documents**. Query planner có thể chọn COLLSCAN vì tập dữ liệu quá nhỏ.

### 14.2. Có IXSCAN không đủ

Một query contains `/PH/` có thể quét phần lớn index để kiểm tra từng khóa, trong khi `/^PH/` có thể quét dải tiền tố hẹp.

Đọc **bounds và keysExamined**, không chỉ tên stage. Explain JSON cũng khác nhau giữa classic engine/Slot-Based Execution và server versions.

### 14.3. Hint chỉ để nghiên cứu

~~~javascript
products.find({
  sku: /^PH/
}).hint("idx_sku").explain("executionStats");

products.find({
  sku: /PH/
}).hint("idx_sku").explain("executionStats");
~~~

Hint ép một kế hoạch index cụ thể để khảo sát; không chứng minh nó tốt nhất. Dùng thận trọng trên production.

## 15. Benchmark trên dữ liệu lớn hơn

Một collection 18 documents không đủ để so sánh latency. Trong database lab, có thể tạo 20.000 sản phẩm:

~~~javascript
const bench = lab.getCollection("products_bench");
const batch = [];

for (let i = 0; i < 20000; i++) {
  const prefix = i % 50 === 0 ? "PH" : "ITEM";

  batch.push({
    _id: i,
    tenantId: "t" + (i % 20),
    status: i % 7 === 0 ? "ARCHIVED" : "ACTIVE",
    sku: prefix + "-" + String(i).padStart(7, "0"),
    name: prefix === "PH" ? "Phone Sample " + i : "Item " + i
  });
}

bench.insertMany(batch);
bench.createIndex({ sku: 1 });
bench.createIndex({ tenantId: 1, status: 1, sku: 1 });
~~~

Sau đó:

~~~javascript
bench.find({ sku: /^PH/ }).explain("executionStats");
bench.find({ sku: /PH/ }).explain("executionStats");
bench.find({ sku: /^ph/i }).explain("executionStats");
~~~

Đánh giá:

- Query có trả cùng kết quả không?
- Keys examined so với nReturned?
- Docs examined?
- Index bounds?
- Query latency nhiều lần, cache ấm/lạnh?
- CPU/I/O và phân bố prefix thật?

Không so sánh mỗi `executionTimeMillis` của một lần chạy rồi kết luận.

## 16. Escape input người dùng

Một ô tìm kiếm SKU thường nhận **literal text**, không phải regex pattern.

Nếu user gõ:

~~~text
AB.42
~~~

và code ghép:

~~~javascript
const pattern = "^" + userInput;
~~~

thì dấu `.` có nghĩa “một ký tự bất kỳ”; regex có thể match `ABX42`.

### 16.1. Hàm escape literal

~~~javascript
function escapeRegexLiteral(value) {
  return value.replace(/[.*+?^{}()|[\]\\$]/g, "\\$&");
}

const raw = "AB.42";
const pattern = "^" + escapeRegexLiteral(raw);

print(pattern); // ^AB\.42

products.find({
  sku: { $regex: pattern }
});
~~~

User nhập `C++` hay `foo(bar)` cũng phải được escape nếu mục tiêu là tìm nguyên văn.

### 16.2. Validate độ dài

~~~javascript
function validatePrefix(input) {
  if (typeof input !== "string") {
    throw new Error("Prefix must be a string");
  }

  const value = input.trim();

  if (value.length < 1 || value.length > 64) {
    throw new Error("Prefix length must be 1..64");
  }

  return value;
}
~~~

64 chỉ là chính sách minh họa. Với Unicode, số UTF-16 code units có thể khác số ký tự người dùng nhìn thấy.

### 16.3. Chống regex gây quá tải

Pattern có nested quantifiers như:

~~~text
^(a+)+$
~~~

có thể gây backtracking tốn CPU với một số chuỗi dài. Không cho public API gửi arbitrary regex rồi chạy trên hàng triệu documents nếu chưa kiểm soát rủi ro.

Biện pháp:

- Dùng literal prefix API thay vì raw regex.
- Escape metacharacters.
- Giới hạn length/complexity.
- Đặt query timeout và `maxTimeMS`.
- Limit kết quả.
- Rate limiting và monitoring.
- Chọn Search nếu yêu cầu không còn phù hợp regex B-tree.

Ví dụ:

~~~javascript
products.find({ sku: /^PH/ })
  .limit(20)
  .maxTimeMS(500);
~~~

Timeout là **lỗi thực thi**, không đồng nghĩa “không tìm thấy”.

## 17. API tìm kiếm prefix không phân biệt case

Giả sử endpoint:

~~~text
GET /api/products?prefix=Pho&limit=20
~~~

Yêu cầu:

1. Tenant lấy từ security context.
2. Input là literal.
3. Case-insensitive bằng normalized key.
4. Chỉ trả ACTIVE products.
5. Kết quả có limit/sort/timeout.

### 17.1. Dữ liệu và index

~~~javascript
{
  name: "Phone Charger",
  nameLower: "phone charger",
  tenantId: "t1",
  status: "ACTIVE"
}
~~~

Index ứng viên:

~~~javascript
products.createIndex(
  { tenantId: 1, status: 1, nameLower: 1, _id: 1 },
  { name: "idx_tenant_status_name_lower" }
);
~~~

Không mặc định luôn cần `_id` cuối index; nó chỉ là ứng viên cho sort tie-breaker, phải đánh giá chi phí.

### 17.2. Truy vấn

~~~javascript
function escapeRegexLiteral(value) {
  return value.replace(/[.*+?^{}()|[\]\\$]/g, "\\$&");
}

function searchProducts(tenantId, rawPrefix) {
  if (typeof rawPrefix !== "string") {
    throw new Error("Missing prefix");
  }

  const prefix = rawPrefix.trim().normalize("NFC").toLowerCase();

  if (prefix.length < 2 || prefix.length > 64) {
    throw new Error("Invalid prefix length");
  }

  const pattern = "^" + escapeRegexLiteral(prefix);

  return db.getSiblingDB("regex_index_lab")
    .products
    .find({
      tenantId: tenantId,
      status: "ACTIVE",
      nameLower: { $regex: pattern }
    })
    .sort({ nameLower: 1, _id: 1 })
    .limit(20)
    .maxTimeMS(500)
    .toArray();
}

printjson(searchProducts("t1", "Pho"));
~~~

Đây là minh họa kỹ thuật, không phải mẫu đầy đủ về authorization; backend phải tự kiểm tra quyền tenant.

### 17.3. Duy trì field dẫn xuất

Khi sửa tên:

~~~javascript
products.updateOne(
  { _id: 2, tenantId: "t1" },
  {
    $set: {
      name: "Phone Adapter",
      nameLower: "phone adapter"
    }
  }
);
~~~

Cập nhật cả hai field trong cùng document operation tránh searchable key bị lỗi thời. Cần backfill data cũ trước khi chuyển API sang `nameLower`.

## 18. Regex trên array, nested field, non-string

### 18.1. Mảng chuỗi

~~~javascript
products.insertOne({
  _id: 99,
  tenantId: "t1",
  status: "ACTIVE",
  sku: "PACK-99",
  name: "Gift Pack",
  tags: ["phone-accessory", "gift", "portable"]
});

products.find({
  tags: /^phone/
});
~~~

Có thể match nếu một phần tử chuỗi trong array phù hợp. Index trên `tags` là multikey index và cần hiểu các quy tắc bounds/multikey riêng.

### 18.2. Nested field

~~~javascript
products.find({
  "manufacturer.name": /^Sony/
});

products.createIndex({
  "manufacturer.name": 1
});
~~~

Index trên `name` không tự là index trên `manufacturer.name`.

### 18.3. Non-string

Regex không tự chuyển number hoặc Date thành chuỗi. Nếu mã số cần prefix lookup, hãy dùng searchable key dạng string hoặc toán tử numeric khi đúng nghiệp vụ.

## 19. Java Sync Driver: Filters.regex()

### 19.1. Ví dụ hoàn chỉnh

Giả sử dùng dependency `org.mongodb:mongodb-driver-sync`:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import static com.mongodb.client.model.Filters.regex;
import static com.mongodb.client.model.Sorts.ascending;

public final class RegexPrefixExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            uri = "mongodb://127.0.0.1:27017";
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("regex_index_lab");
            MongoCollection<Document> products = db.getCollection("products");

            Bson filter = regex("sku", "^PH");

            for (Document doc : products.find(filter)
                    .sort(ascending("sku"))
                    .limit(20)) {
                System.out.println(doc.toJson());
            }
        }
    }
}
~~~

### 19.2. Regex options

~~~java
import static com.mongodb.client.model.Filters.regex;

Bson sensitive = regex("name", "^Phone");
Bson insensitive = regex("name", "^phone", "i");
~~~

Thêm `i` không biến nó thành case-sensitive prefix range index.

### 19.3. Java Pattern

~~~java
import java.util.regex.Pattern;
import static com.mongodb.client.model.Filters.regex;

Pattern pattern = Pattern.compile("^PH");
Bson filter = regex("sku", pattern);
~~~

Cẩn thận vì Java regex syntax và server PCRE2 có thể khác với những construct nâng cao.

### 19.4. Escape user input với Pattern.quote

~~~java
import java.util.regex.Pattern;
import static com.mongodb.client.model.Filters.regex;

String userPrefix = "AB.42";
String safeRegex = "^" + Pattern.quote(userPrefix);
Bson filter = regex("sku", safeRegex);
~~~

`Pattern.quote()` thường sinh `\Q...\E` để match literal. PCRE2 có hỗ trợ cách quote trong ngữ cảnh phù hợp. Không gửi raw input khi UI chỉ yêu cầu literal prefix.

### 19.5. Java service với normalized field

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.regex;

public final class ProductPrefixService {
    private final MongoCollection<Document> products;

    public ProductPrefixService(MongoCollection<Document> products) {
        this.products = products;
    }

    public List<Document> search(
            String tenantId,
            String rawPrefix,
            int maxResults) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant");
        }
        if (rawPrefix == null) {
            throw new IllegalArgumentException("Missing prefix");
        }

        String prefix = Normalizer.normalize(
                rawPrefix.trim(), Normalizer.Form.NFC)
                .toLowerCase(Locale.ROOT);

        if (prefix.length() < 2 || prefix.length() > 64) {
            throw new IllegalArgumentException("Invalid prefix length");
        }

        int limit = Math.max(1, Math.min(50, maxResults));

        Bson filter = and(
                eq("tenantId", tenantId),
                eq("status", "ACTIVE"),
                regex("nameLower", "^" + Pattern.quote(prefix))
        );

        return products.find(filter)
                .limit(limit)
                .into(new ArrayList<>());
    }
}
~~~

Ứng dụng thực cần authorization, timeout, rate limiting và đảm bảo cùng normalization rules trong mọi write/update.

### 19.6. Explain từ Java

~~~java
import com.mongodb.ExplainVerbosity;
import org.bson.Document;

Document explain = products.find(regex("sku", "^PH"))
        .explain(ExplainVerbosity.EXECUTION_STATS);

System.out.println(explain.toJson());
~~~

Giới hạn thời gian:

~~~java
import java.util.concurrent.TimeUnit;

for (Document row : products.find(regex("sku", "^PH"))
        .limit(20)
        .maxTime(500, TimeUnit.MILLISECONDS)) {
    System.out.println(row.toJson());
}
~~~

## 20. Sharding, tenant và hai lớp tối ưu

Trên sharded collection, cần phân biệt:

- **Shard targeting:** mongos quyết định shard nào sẽ nhận query.
- **Index filtering:** mỗi shard áp dụng index/range cho dữ liệu của nó.

~~~javascript
products.find({
  sku: /^PH/
});
~~~

Nếu shard key liên quan tenantId nhưng query thiếu tenantId, nó có thể phải hỏi nhiều shards.

~~~javascript
products.find({
  tenantId: "t1",
  sku: /^PH/
});
~~~

Khi ràng buộc shard key phù hợp, router có thể target tốt hơn.

Một regex prefix có index trên mỗi shard **không tự động bảo đảm single-shard query**. Đồng thời, tenantId phải được xác thực từ security context; không bỏ qua chỉ để query ngắn gọn.

## 21. Khi nào không nên dùng $regex?

| Nhu cầu | Giải pháp cần cân nhắc |
|---|---|
| Tìm SKU đúng hoàn toàn | Equality + B-tree |
| Bắt đầu bằng literal, case-sensitive | Anchored `$regex` + B-tree |
| Bắt đầu bằng literal, case-insensitive | Normalized indexed field hoặc MongoDB Search |
| Contains substring quy mô lớn | MongoDB Search hoặc search engine |
| Suffix thường xuyên | Reversed key hoặc Search |
| Full-text theo từ | `$text`/text index hoặc Search |
| Fuzzy, typo, autocomplete | Search với analyzer/operator phù hợp |
| Relevance, synonym, stemming | Search engine |
| Regex pattern admin tự nhập | `$regex` có kiểm soát tài nguyên/quyền |

### 21.1. $text khác $regex

~~~javascript
products.createIndex({ name: "text" });

products.find({
  $text: { $search: "phone" }
});
~~~

Text index có tokenization/stemming/stop-word rules riêng; không phải B-tree cho prefix regex và không giải quyết tùy ý substring lookup.

### 21.2. MongoDB Search

MongoDB Search/Atlas Search sử dụng **search index** và semantics khác với `$regex` trên collection. Nó phù hợp hơn cho những yêu cầu như fuzzy, autocomplete, phrase, full-text ranking và nhiều field.

Không dùng cú pháp Search regex/wildcard rồi suy ra B-tree `$regex` có cùng hiệu năng.

## 22. Các lỗi thiết kế phổ biến

| Sai lầm | Vấn đề | Cách giải quyết |
|---|---|---|
| `/PH/` cho startsWith | Không có prefix literal cố định ở đầu | `/^PH/` nếu đúng nghiệp vụ |
| `/^.*PH/` rồi tin rằng có `^` là đủ | Wildcard ăn đầu chuỗi | Bỏ wildcard nếu chỉ tìm prefix |
| `/^PH.*$/` khi chỉ cần startsWith | Regex work thêm | Dùng `/^PH/` |
| `/^ph/i` + case-insensitive index | Regex không collation-aware | Normalized field/Search |
| Regex cho exact SKU | Thừa regex engine | Equality |
| Nối raw input | Sai kết quả/regex abuse | Escape literal |
| Cho regex bất kỳ vào public API | ReDoS/CPU tăng | Giới hạn length/pattern/timeout |
| IXSCAN nên coi là tối ưu | Có thể full index scan | Đọc bounds/keysExamined |
| Benchmark trên 18 docs | Không representative | Benchmark theo workload thật |
| `$regexMatch` được coi là indexed predicate | Computed expression có thể ngăn pushdown | Dùng `$match` trực tiếp khi phù hợp |
| `i` được hiểu là bỏ dấu tiếng Việt | Không đúng semantics | Normalize/search analyzer |
| Không có tenant filter | Rủi ro lộ dữ liệu/scatter-gather | Authentication + predicate |
| Có quá nhiều indexes | Write/storage cost cao | Chọn theo query pattern |
| Regex trên numeric field | Không phải string search | Searchable key hoặc numeric comparison |
| `$in` chứa object `{$regex:...}` | Không phải regex literal hợp lệ trong $in | Dùng regex literals/$or |
| Negative regex mặc định nhanh | Có thể match phần lớn collection | Xem selectivity |
| Dùng maxTimeMS thay validation | Không tránh mọi rủi ro | Validate/escape/rate-limit |
| Bỏ cập nhật normalized field | Trả thiếu/sai kết quả | Update đồng thời và backfill |
| Dùng regex cho typo/relevance | Không có semantics đó | Search engine |

## 23. Tình huống phân tích

### 23.1. IXSCAN nhưng totalKeysExamined rất lớn

Query contains có thể đi qua index song phải kiểm tra gần hết keys. Nó vẫn là `IXSCAN` nhưng không có bounded prefix range hẹp. Cần so số khóa với lượng kết quả và thử query/filter khác nếu nghiệp vụ cho phép.

### 23.2. Prefix chỉ có một ký tự

`/^P/` có thể match 40% products. Index vẫn có thể được dùng nhưng selectivity thấp. Đặt minimum prefix length, limit và rate limiting theo UX.

### 23.3. Thêm i flag làm chậm autocomplete

Khi chuyển `/^Phone/` thành `/^phone/i`, kết quả tìm được nhiều hơn nhưng bounds khác. Không cố chữa bằng case-insensitive collation index như equality; hãy thử normalized field/Search.

### 23.4. Regex trên computed field

Nếu pipeline tạo field `$toLower` rồi dùng regex trên field đó, index gốc trên `name` không tự dùng được như index của computed `lowerName`. Precomputed key hoặc Search có thể phù hợp hơn.

### 23.5. Regex input có dấu chấm

User nhập `AB.42` nhưng query raw regex `^AB.42` có thể match `ABX42`. Escape literal nếu đó là ô tìm mã.

## 24. Bài tập

### Bài A — Dự đoán kết quả

Cho các SKU:

~~~text
PH-100
PH-101
PH-VN
XPH-300
CASE-PH
ph-103
~~~

Dự đoán kết quả của:

1. `/^PH/`.
2. `/PH/`.
3. `/PH$/`.
4. `/^ph/i`.
5. `/^PH.*$/`.

Giải thích vì sao 1 và 5 thường cho kết quả tương tự trên chuỗi một dòng nhưng khác hiệu năng.

### Bài B — Explain

1. Tạo index `{sku:1}`.
2. Explain `/^PH/`, `/PH/`, `/^ph/i`.
3. So sánh indexBounds, totalKeysExamined, totalDocsExamined.
4. Giải thích vì sao MongoDB có thể chọn COLLSCAN khi chỉ có 18 docs.
5. Dùng hint trong lab để khảo sát chi phí index.

### Bài C — Compound index

Với query có tenantId equality, status equality, sku prefix, hãy đề xuất index. Sau đó bỏ status hoặc tenantId và phân tích sự thay đổi của khả năng dùng compound index.

### Bài D — Case-insensitive

1. So sánh `name:/^phone/i` và `nameLower:/^phone/`.
2. Tạo index cho `nameLower`.
3. Kiểm tra explain.
4. Nêu các chi phí migration và update.

### Bài E — Escaping

Người dùng nhập `AB.42`, `C++` và `foo(bar)`.

- Dùng escapeRegexLiteral() để tạo regex literal prefix.
- Giải thích tại sao không escape sẽ làm sai match.
- Nêu chính sách giới hạn độ dài và timeout.

### Bài F — Java Sync Driver

Thử:

- `Filters.regex("sku","^PH")`.
- `Filters.regex("name","^phone","i")`.
- `Pattern.quote(userInput)`.
- Kết hợp tenant/status equality filters.
- Explain và maxTime.

### Bài G — Tiếng Việt

User nhập `dien thoai` muốn tìm `Điện thoại phổ thông`:

- Cờ `i` có đủ không?
- Cần normalize/accent removal thế nào?
- Khi nào dùng analyzer của MongoDB Search?
- Cách giữ nguyên tên gốc cho UI?

### Bài H — Sharding

Collection sharded theo tenant. So sánh query có và không có tenantId. Phân biệt shard targeting và index bounds.

### Bài I — Chọn công cụ

Hãy chọn equality, prefix regex, normalized field, text index, Search hoặc reversed key cho các tính năng exact SKU, prefix tên, contains mô tả, typo autocomplete, suffix mã kho và relevance ranking.

### Bài J — Runbook hiệu năng

Một API prefix search chậm sau khi thêm `i` flag. Hãy viết runbook:

1. Xác minh query và semantics.
2. Xem index/collation.
3. Đọc explain.
4. Kiểm tra selectivity và tenant distribution.
5. Thử normalized indexed field.
6. Benchmark dữ liệu representative.
7. Đặt monitoring/rollback.

## 25. Checklist

- [ ] Exact, prefix, contains hay suffix?
- [ ] Input literal hay regex pattern?
- [ ] Có anchor đầu chuỗi cùng simple literal prefix?
- [ ] Có cờ i/m làm thay đổi semantics?
- [ ] Equality filters và compound index đã phù hợp?
- [ ] Prefix có đủ chọn lọc?
- [ ] Index collation và query collation thế nào?
- [ ] Đã xem indexBounds, keysExamined, docsExamined?
- [ ] Input đã escape và validate?
- [ ] Có tenant authorization?
- [ ] Có limit, maxTimeMS, rate limit?
- [ ] Normalized key có được backfill/đồng bộ?
- [ ] Có yêu cầu accent-insensitive/fuzzy/relevance vượt regex?
- [ ] Benchmark trên workload đại diện?

## 26. Tài liệu chính thức

- [MongoDB Manual – $regex Query Predicate](https://www.mongodb.com/docs/manual/reference/operator/query/regex/)
- [MongoDB Manual – Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/)
- [MongoDB Manual – Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual – Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual – Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [MongoDB Manual – Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual – $match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/)
- [MongoDB Manual – $regexMatch](https://www.mongodb.com/docs/manual/reference/operator/aggregation/regexMatch/)
- [MongoDB Manual – $text](https://www.mongodb.com/docs/manual/reference/operator/query/text/)
- [MongoDB Manual – Text Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/)
- [MongoDB Search](https://www.mongodb.com/docs/atlas/atlas-search/)
- [MongoDB Java Sync Driver – Filters Builders](https://www.mongodb.com/docs/drivers/java/sync/current/builders/filters/)
- [MongoDB Java Sync Driver – Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)

## 27. Kết luận

`$regex` là công cụ hữu ích để tìm mẫu chuỗi. Nhưng **khả năng tận dụng B-tree index hiệu quả nhất thường đến từ simple case-sensitive literal prefix ngay sau `^` hoặc `\A`**. Contains, suffix, wildcard đầu chuỗi và case-insensitive matching không có cùng điều kiện tối ưu.

Không dừng ở câu “có index” hoặc “explain có IXSCAN”. Hãy xem index bounds, số index keys/documents đã xét, số kết quả và latency trên workload đại diện. Dùng equality cho exact match, normalized field cho một số bài toán case-insensitive prefix, escape input người dùng để an toàn, và chuyển sang công cụ Search khi yêu cầu là fuzzy, relevance hoặc full-text phức tạp.
