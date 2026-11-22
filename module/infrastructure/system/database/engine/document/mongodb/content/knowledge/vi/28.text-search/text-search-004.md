# Giới hạn của text index khi tìm gần đúng, tự hoàn thành và tiếng Việt trong MongoDB

Một ứng dụng quản lý sản phẩm có thể lưu hàng trăm nghìn tên hàng, mô tả, thương hiệu và danh mục trong MongoDB. Người dùng có thể nhập `điện thoại Samsung`, `dien thoai`, `sam sung`, `samsng`, `điện` hoặc chỉ gõ `sam` rồi chờ hệ thống tự hoàn thành. Tất cả đều là yêu cầu “tìm kiếm văn bản” ở góc nhìn sản phẩm, nhưng chúng **không phải cùng một bài toán kỹ thuật**.

MongoDB có **text index truyền thống** để phục vụ toán tử `$text`. Nó rất hữu ích khi cần tìm từ khóa theo các token có trong document, hỗ trợ một số lựa chọn liên quan đến ngôn ngữ và xếp hạng `textScore`. Tuy nhiên, text index này **không phải** một công cụ tìm kiếm gần đúng theo khoảng cách chỉnh sửa, một engine tự hoàn thành khi gõ từng ký tự, hay một bộ phân tích tiếng Việt chuyên sâu.

Bài học trong chương **Tìm kiếm văn bản** của module **Database Engine Document MongoDB** giải thích cách đánh giá ba giới hạn chính:

1. **Tìm gần đúng (fuzzy search):** người dùng gõ sai, thiếu hoặc dư ký tự, ví dụ `samsng` thay vì `samsung`.
2. **Tự hoàn thành (autocomplete/typeahead):** người dùng nhập một tiền tố hoặc đoạn ngắn và muốn nhận gợi ý ngay.
3. **Tiếng Việt:** dấu thanh, ký tự `đ`, Unicode normalization, từ ghép nhiều âm tiết như `bất động sản` và biến thể cách viết.

Sau khi hiểu hạn chế của `$text`, ta sẽ cân nhắc **index B-tree + prefix filter**, **field chuẩn hóa**, **MongoDB Search/Atlas Search**, hoặc một **search engine riêng**, dựa trên yêu cầu thực tế thay vì dùng một kỹ thuật cho mọi trường hợp.

## 1. Bốn loại “tìm kiếm” cần phân biệt

Trước khi chọn index, hãy phân loại câu hỏi của ứng dụng.

| Loại truy vấn | Ví dụ người dùng nhập | Định nghĩa mong muốn | Cách tiếp cận phù hợp để đánh giá |
| --- | --- | --- | --- |
| **Exact lookup** | `SKU-IPH-15-BLK` | Tìm đúng mã sản phẩm | Equality + B-tree index |
| **Full-text keyword search** | `điện thoại samsung` | Tìm document chứa những từ khóa liên quan | Text index `$text` hoặc search index |
| **Prefix/autocomplete** | `sams` | Gợi ý `Samsung Galaxy…` khi đang nhập | Prefix field/index hoặc autocomplete search |
| **Fuzzy/typo tolerance** | `samsng` | Tìm `Samsung` dù sai chính tả | Fuzzy search chuyên dụng |
| **Vietnamese-aware search** | `bat dong san` / `bất động sản` | Tìm kết quả đúng ngữ nghĩa và biến thể dấu/tách từ | Normalization + phân tích ngôn ngữ + ranking |
| **Semantic search** | `điện thoại pin trâu cho du lịch` | Tìm theo ý nghĩa, không chỉ từ trùng | Search ranking/semantic or vector search khi cần |

Một API duy nhất có thể kết hợp nhiều loại tìm kiếm; điều quan trọng là **không đánh đồng khả năng của text index với khả năng của toàn bộ nền tảng MongoDB Search**.

### Tình huống thực tế

Giả sử database có sản phẩm:

```javascript
{
  _id: "P001",
  tenantId: "shop-01",
  name: "Điện thoại Samsung Galaxy A55",
  description: "Điện thoại Android pin lâu, chụp ảnh đẹp",
  category: "phone",
  brand: "Samsung"
}
```

Ứng dụng có thể cần những kết quả khác nhau:

- Tìm `P001`: phải chính xác, không cần fuzzy.
- Tìm `Samsung Galaxy`: có thể dùng tìm theo từ khóa.
- Gõ `Sam`: cần prefix/autocomplete.
- Gõ `Samsng`: cần chịu lỗi chính tả.
- Gõ `dien thoai`: cần chiến lược xử lý dấu tiếng Việt.
- Gõ `điện thoại pin lâu`: cần cân bằng nhiều từ, độ liên quan và thứ hạng.

Việc tạo một text index không tự làm đủ sáu việc trên.

## 2. Text index truyền thống hoạt động như thế nào?

MongoDB text index lập chỉ mục cho **các từ/token trong trường văn bản** đã chọn. Khi chạy `$text`, MongoDB dùng index đó để tìm document phù hợp, thay vì quét mọi document để kiểm tra một chuỗi con.

Ví dụ trên collection `products`:

```javascript
db.products.createIndex(
  { name: "text", description: "text" },
  {
    name: "idx_product_text",
    default_language: "none",
    weights: {
      name: 8,
      description: 2
    }
  }
);
```

Ý nghĩa:

- `name` và `description` là các trường được lập chỉ mục văn bản.
- `weights` cho phép đánh giá từ khóa trùng ở tên sản phẩm có trọng số cao hơn trùng ở mô tả.
- `default_language: "none"` tắt **stemming** và **stop-word filtering** theo danh sách ngôn ngữ hỗ trợ của text index.
- `name: "idx_product_text"` là tên của index, **không phải tên field tìm kiếm**.

### Token thay vì chuỗi con tùy ý

Về bản chất, text index phân tích nội dung thành token rồi xây cấu trúc tra cứu từ khóa. Nó **không lưu mọi tiền tố của mọi token** hoặc mọi biến thể chính tả có thể phát sinh.

```text
Tên sản phẩm: "Samsung Galaxy A55"
                 |
                 v
           phân tích/tokenize
                 |
       +---------+---------+
       |         |         |
   "samsung"  "galaxy"   "a55"
       |         |         |
       +---------+---------+
                 |
               text index
```

Truy vấn tìm từ `samsung` có thể tận dụng token tương ứng. Nhưng chuỗi `sams` **không nhất thiết** khớp token `samsung`; `samsng` cũng không tự biến thành `samsung`.

### Text index có ích cho nhu cầu nào?

Phù hợp để bắt đầu với những ứng dụng:

- Tìm keyword tương đối rõ, đã nhập đủ từ.
- Không yêu cầu chịu lỗi gõ sai phức tạp.
- Không đòi gợi ý tức thời theo từng ký tự.
- Có tập dữ liệu và schema không quá phức tạp.
- Không phụ thuộc vào linguistic analysis chuyên biệt cho tiếng Việt.
- Cần giải pháp full-text cơ bản ngay trong truy vấn MongoDB.

**Không nên bỏ qua text index chỉ vì nó không có fuzzy.** Nó vẫn hữu ích khi đúng yêu cầu; giới hạn chỉ xuất hiện nếu sản phẩm kỳ vọng những khả năng khác.

## 3. Bộ dữ liệu thực hành

Các ví dụ dưới đây chỉ nên chạy trên database thực hành; nếu collection đã tồn tại, có thể gặp duplicate key hoặc xung đột index. Sử dụng `mongosh` trên MongoDB được phép thao tác:

```javascript
use mongo_text_search_lab

db.products.insertMany([
  {
    _id: "P001",
    tenantId: "shop-01",
    name: "Điện thoại Samsung Galaxy A55",
    description: "Điện thoại Android pin lâu và chụp ảnh đẹp",
    brand: "Samsung",
    category: "phone"
  },
  {
    _id: "P002",
    tenantId: "shop-01",
    name: "Điện thoại iPhone 15 Pro",
    description: "Smartphone hiệu năng cao, camera chất lượng",
    brand: "Apple",
    category: "phone"
  },
  {
    _id: "P003",
    tenantId: "shop-01",
    name: "Máy ảnh Sony Alpha",
    description: "Máy ảnh kỹ thuật số cho người mới học",
    brand: "Sony",
    category: "camera"
  },
  {
    _id: "P004",
    tenantId: "shop-01",
    name: "Máy lọc không khí",
    description: "Thiết bị làm sạch không khí trong phòng",
    brand: "AirHome",
    category: "home"
  },
  {
    _id: "P005",
    tenantId: "shop-01",
    name: "Sách học máy cơ bản",
    description: "Giới thiệu học máy và trí tuệ nhân tạo",
    brand: "BookHouse",
    category: "book"
  },
  {
    _id: "P006",
    tenantId: "shop-01",
    name: "Bàn phím cơ không dây",
    description: "Bàn phím Bluetooth cho lập trình viên",
    brand: "KeyLab",
    category: "accessory"
  },
  {
    _id: "P007",
    tenantId: "shop-01",
    name: "Bún bò Huế đóng gói",
    description: "Món ăn đặc sản có vị cay",
    brand: "HueFoods",
    category: "food"
  },
  {
    _id: "P008",
    tenantId: "shop-02",
    name: "Điện thoại Samsung Galaxy S24",
    description: "Điện thoại camera tốt và màn hình lớn",
    brand: "Samsung",
    category: "phone"
  },
  {
    _id: "P009",
    tenantId: "shop-02",
    name: "Bất động sản ven sông",
    description: "Danh sách nhà ở và căn hộ",
    brand: "RealHome",
    category: "realestate"
  },
  {
    _id: "P010",
    tenantId: "shop-01",
    name: "Áo khoác chống nắng",
    description: "Quần áo dùng trong mùa hè",
    brand: "Wear",
    category: "clothing"
  }
])
```

Bộ dữ liệu có các từ tiếng Việt nhiều âm tiết, dấu tiếng Việt, nhiều tenant và các từ thương hiệu tiếng Anh để minh họa sự khác nhau giữa token search, autocomplete và fuzzy.

Tạo text index truyền thống:

```javascript
db.products.createIndex(
  { name: "text", description: "text" },
  {
    name: "idx_product_text",
    default_language: "none",
    weights: { name: 10, description: 2 }
  }
)
```

## 4. Các thao tác `$text` làm được

### 4.1. Tìm từ khóa

```javascript
db.products.find({
  $text: {
    $search: "Samsung"
  }
})
```

MongoDB tìm theo các token và quy tắc của text index. Nếu một document có token phù hợp, nó có thể được trả về.

Tìm nhiều từ:

```javascript
db.products.find({
  $text: {
    $search: "Samsung Galaxy"
  }
})
```

**Không mặc định chuỗi nhiều từ là phép AND chính xác theo thứ tự.** Trong cú pháp `$text`, các từ tìm kiếm không nằm trong cụm đặt trong dấu ngoặc kép thường được xử lý theo ngữ nghĩa tìm term, không phải câu “phải chứa nguyên văn toàn bộ cụm này”.

Nếu sản phẩm yêu cầu tất cả các từ đều bắt buộc có mặt, cần xem xét **cú pháp query, phrase search, search engine** hoặc các điều kiện nghiệp vụ bổ sung. Tìm từ đơn và tìm câu có nghĩa là hai việc khác nhau.

### 4.2. Tìm cụm từ

Để tìm cụm được đặt trong dấu ngoặc kép ở cú pháp `$search`:

```javascript
db.products.find({
  $text: {
    $search: "\"Samsung Galaxy\""
  }
})
```

Điều kiện tìm cụm vẫn chịu ảnh hưởng của **tokenization, case/diacritic behavior và index language**. Nó không phải toán tử “so sánh giá trị string nguyên văn” theo cách của equality trên field.

### 4.3. Loại trừ từ

Trong cú pháp text search, dấu trừ có thể biểu diễn term cần loại trừ:

```javascript
db.products.find({
  $text: {
    $search: "điện thoại -iPhone"
  }
})
```

Truy vấn trên minh họa ngữ nghĩa term/exclusion. Với dữ liệu tiếng Việt và cách tokenize khác nhau, **không dự đoán cứng tập kết quả** chỉ từ cảm giác nhìn tên sản phẩm; dùng dữ liệu thật và kiểm tra truy vấn.

### 4.4. Sắp xếp bằng `textScore`

```javascript
db.products.find(
  {
    tenantId: "shop-01",
    $text: { $search: "Samsung Galaxy" }
  },
  {
    name: 1,
    brand: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
})
```

`textScore` là một **tín hiệu đánh giá độ phù hợp dạng text search**, không phải xác suất rằng sản phẩm “đúng 90%”, không đo khoảng cách Levenshtein và không tự hiểu mục đích mua hàng.

Một index có weights cao cho `name` sẽ khiến term trùng trong tên có ảnh hưởng khác với term trùng trong description. Cần đánh giá quality bằng các truy vấn đại diện, không coi score là một thang đo tuyệt đối có thể so giữa mọi bộ dữ liệu/index/version.

### 4.5. Cấu hình ngôn ngữ của một truy vấn

```javascript
db.products.find({
  $text: {
    $search: "điện thoại",
    $language: "none",
    $caseSensitive: false,
    $diacriticSensitive: false
  }
})
```

Đây là các option của **classic `$text`**, không phải cấu hình fuzzy search. `$language: "none"` có ý nghĩa đối với stemming/stop words, nhưng **không biến MongoDB thành bộ NLP tiếng Việt**.

## 5. Những giới hạn cơ bản của text index

| Khả năng | Classic text index/`$text` | Ý nghĩa với người dùng |
| --- | --- | --- |
| Tìm token có trong văn bản | **Có** | Gõ đủ từ thường dễ tìm |
| Tìm cụm từ theo cú pháp text search | **Có giới hạn theo tokenizer** | Phrase search không phải so khớp chuỗi nguyên văn |
| Xếp hạng bằng `textScore` | **Có** | Có thể ưu tiên một số kết quả theo term |
| Tự sửa lỗi gõ `samsng` thành `samsung` | **Không có edit-distance fuzzy tự động** | Sai một ký tự có thể không trả kết quả |
| Autocomplete `sam` → `Samsung` | **Không tự sinh prefix tokens** | Gõ chưa đủ từ có thể chưa tìm thấy |
| Tách từ ghép tiếng Việt chính xác theo ngữ nghĩa | **Không có Vietnamese linguistic analyzer chuyên biệt** | Từ nhiều âm tiết dễ gặp sai lệch |
| Tìm từ đồng nghĩa theo domain | **Không tự biết** | `điện thoại` và `smartphone` không mặc nhiên là synonyms |
| Gợi ý sửa chính tả | **Không có chức năng spell suggestion tích hợp của `$text`** | Cần pipeline/engine bổ sung |
| Tìm theo ý nghĩa ngữ cảnh | **Không phải semantic search** | Tìm keyword và hiểu intent khác nhau |
| Highlight phần khớp | **Không có hệ highlight chuyên dụng như search engine** | UI cần giải pháp khác nếu muốn tô sáng |
| Tinh chỉnh analyzer đa dạng | **Hạn chế so với search engine** | Khó đáp ứng nhu cầu tiếng Việt sâu |

Một giải pháp tìm kiếm hoàn chỉnh thường kết hợp **exact lookup**, **prefix**, **keyword**, **fuzzy**, **synonyms** và **ranking**. Không có lý do phải ép tất cả thành một câu `$text`.

## 6. Giới hạn thứ nhất: tìm gần đúng và lỗi chính tả

### 6.1. “Gần đúng” là một thuật ngữ có nhiều nghĩa

Trong ứng dụng, “tìm gần đúng” có thể là:

- **Typo tolerance:** `samsng` → `samsung` (thiếu chữ `u`).
- **Thừa chữ:** `samsungg` → `samsung`.
- **Sai thứ tự ký tự:** `samusng` → `samsung`.
- **Khác dấu tiếng Việt:** `dien thoai` → `điện thoại`.
- **Khác cách viết có khoảng trắng:** `sam sung` → `samsung`.
- **Viết tắt:** `dt` → `điện thoại`.
- **Đồng nghĩa:** `smartphone` → `điện thoại thông minh`.
- **Tương tự về ý nghĩa:** `điện thoại quay video tốt` → sản phẩm có camera phù hợp.

Đây là **những bài toán riêng**. Khoảng cách chỉnh sửa ký tự (*edit distance*) chỉ giải quyết một phần, không tự sinh synonym, không hiểu nghĩa câu và không nhất thiết giải quyết sự tách âm tiết tiếng Việt.

### 6.2. Text index không tự tạo biến thể một ký tự

Ví dụ:

```javascript
// Tên thật:
// "Điện thoại Samsung Galaxy A55"

db.products.find({
  $text: { $search: "samsng" }
})
```

Nếu chỉ có token `samsung` trong index, `$text` **không tự tìm token cách một lần chèn ký tự**. Nó không có option kiểu:

```javascript
// CÚ PHÁP KHÔNG HỢP LỆ với classic $text:
{
  $text: {
    $search: "samsng",
    fuzzy: { maxEdits: 1 }
  }
}
```

Không được nhầm một ví dụ tính năng của **MongoDB Search** với option của classic `$text`. Hai hệ thống có loại index và cú pháp truy vấn khác nhau.

### 6.3. Vì sao thêm `$regex` không giải quyết trọn vẹn?

Một người có thể thử:

```javascript
db.products.find({
  name: /sam.*ng/i
})
```

Regex này chỉ khớp những chuỗi thỏa mẫu `sam` rồi `ng`, **không** tự tính mọi phép thay thế/thêm/xóa ký tự. Khi lỗi chính tả đa dạng, phải tạo rất nhiều mẫu regex, vừa khó bảo trì vừa có thể tốn tài nguyên.

Regex **không phải** thuật toán spell checker và không có cơ chế scoring theo edit distance tích hợp vào classic text index.

## 7. Edit distance và fuzzy search thực sự là gì?

**Levenshtein distance** là số thao tác chèn, xóa hoặc thay thế ký tự tối thiểu để biến chuỗi A thành chuỗi B.

Ví dụ:

```text
"samsng" -> "samsung"
      chèn "u"
Khoảng cách chỉnh sửa = 1

"samsang" -> "samsung"
      thay "a" bằng "u"
Khoảng cách chỉnh sửa = 1
```

Một fuzzy engine có thể giới hạn số edits cho phép, ví dụ 1 hoặc 2, cùng những ngưỡng khác như:

- **prefixLength:** số ký tự đầu phải khớp chính xác.
- **maxExpansions:** giới hạn số ứng viên biến thể được xét.
- **tokenization:** fuzzy áp dụng trên từ/token nào.
- **minimum query length:** hạn chế fuzzy trên query quá ngắn để tránh nhiều kết quả vô nghĩa.

### Fuzzy không nên luôn bật với mức cao nhất

Nếu người dùng chỉ gõ `a` và search engine cho phép 2 edits, sẽ có rất nhiều token gần ký tự đó. Hệ thống có thể trả kết quả không liên quan hoặc tăng đáng kể chi phí tìm kiếm.

Một chiến lược UX thường hợp lý:

1. Ưu tiên **exact/keyword/prefix** khi đã có kết quả tốt.
2. Nếu query đủ dài và kết quả ít, mở rộng sang **fuzzy với max edits giới hạn**.
3. Giảm weight của fuzzy match so với exact match.
4. Thêm filter theo tenant, quyền truy cập, trạng thái sản phẩm và danh mục.
5. Đo **precision, recall và latency**, không chỉ số kết quả trả về.

### Tiếng Việt không chỉ là Levenshtein

`điện thoại` và `dien thoai` khác nhau ở dấu thanh, dấu mũ và ký tự `đ`. Nếu tính khoảng cách từng code point Unicode một cách thô, khoảng cách có thể lớn hơn kỳ vọng của người dùng. Vì vậy, một pipeline tiếng Việt thường cần **normalize** trước rồi mới quyết định có dùng fuzzy hay không.

## 8. Giới hạn thứ hai: autocomplete không phải full-text keyword search

Autocompletion thường xảy ra khi người dùng chưa gõ xong:

```text
Người dùng gõ:
  "s" -> "sa" -> "sam" -> "sams" -> "samsu"

Ứng dụng muốn gợi ý:
  Samsung
  Samsung Galaxy A55
  Samsung Galaxy S24
```

Trong classic text index, token `samsung` không tự sinh những entry `s`, `sa`, `sam`, `sams`, `samsu`. Vì vậy:

```javascript
db.products.find({
  $text: { $search: "sam" }
})
```

không tương đương với “mọi sản phẩm có từ bắt đầu bằng `sam`”.

### 8.1. Prefix search trên trường chuẩn hóa

Nếu requirement đơn giản là gợi ý **tên bắt đầu bằng tiền tố**, có thể tạo field `nameNorm` được chuẩn hóa trước khi ghi:

```javascript
{
  _id: "P001",
  name: "Điện thoại Samsung Galaxy A55",
  nameNorm: "dien thoai samsung galaxy a55"
}
```

Tạo B-tree index:

```javascript
db.products.createIndex(
  { tenantId: 1, nameNorm: 1 },
  { name: "idx_tenant_name_norm" }
)
```

Khi user nhập `dien t` sau khi normalize, có thể thử **anchored regex**:

```javascript
db.products.find({
  tenantId: "shop-01",
  nameNorm: /^dien t/
}, {
  name: 1,
  brand: 1
}).limit(10)
```

Với index B-tree và các điều kiện phù hợp, regex **bắt đầu bằng `^` và một prefix literal** có khả năng tận dụng index hiệu quả hơn so với regex chứa `.*` ở đầu. Không bảo đảm mọi regex case-insensitive/collation đều dùng index như nhau; hãy kiểm tra `explain()`.

### Nhưng prefix của cả tên chưa phải autocomplete mọi từ

`nameNorm: "dien thoai samsung galaxy a55"` bắt đầu bằng `dien`, **không bắt đầu bằng `sam`**. Query:

```javascript
db.products.find({
  nameNorm: /^sam/
})
```

có thể **không tìm thấy P001** dù trong tên có `Samsung`. Đây là hạn chế của **prefix-of-field** so với **prefix-of-token**.

Cách giải quyết có thể là:

- Tạo trường gợi ý riêng theo thương hiệu.
- Tạo mảng prefix/token đã chuẩn hóa với thiết kế index rõ ràng.
- Dùng **autocomplete search index** có tokenizer phù hợp.
- Dùng dịch vụ search riêng nếu UI cần gợi ý ở mọi vị trí trong tên.

Đừng tuyên bố regex anchored trên nguyên tên đã đạt chức năng autocomplete như search engine.

### 8.2. Contains search có thể đắt

Truy vấn:

```javascript
db.products.find({
  nameNorm: /samsung/
})
```

là dạng **substring search** không có tiền tố neo ở đầu field. Nó thường không khai thác B-tree index theo cách hiệu quả như equality/prefix; trên collection lớn có thể phải xem rất nhiều giá trị/document.

```javascript
// Đặc biệt cần thận trọng:
db.products.find({
  nameNorm: /.*samsung.*/i
})
```

Thêm `.*` và option `i` không biến truy vấn thành full-text engine. Với dữ liệu Unicode và collation, tác động tới index còn cần đo thực tế.

### 8.3. Autocomplete không chỉ là truy vấn

Một UI gợi ý tốt còn cần:

- **Debounce**: không gửi request cho mọi phím bấm quá nhanh.
- **Minimum length**: có thể bắt đầu từ 2–3 ký tự thay vì 1.
- **Limit**: chỉ trả top N gợi ý.
- **Cancel stale request**: bỏ kết quả của query cũ nếu user đã gõ query mới.
- **Ranking**: ưu tiên khớp đầu tên, thương hiệu, phổ biến, còn hàng, theo tenant.
- **Authorization**: không gợi ý sản phẩm của tenant khác.
- **Latency budget**: typeahead cần phản hồi nhất quán ở p95/p99, không chỉ trung bình.

Do đó, “có prefix index” mới là một phần của giải pháp.

## 9. Giới hạn thứ ba: tiếng Việt có cấu trúc từ riêng

Tiếng Việt thường tách các **âm tiết bằng dấu cách**, nhưng một từ có thể gồm nhiều âm tiết:

```text
"điện thoại"      -> một khái niệm, hai âm tiết
"bất động sản"    -> một khái niệm, ba âm tiết
"học máy"         -> thuật ngữ hai âm tiết
"thành phố"       -> hai âm tiết
"bún bò Huế"      -> tên món ăn gồm nhiều thành phần
```

Một tokenizer dựa chủ yếu vào khoảng trắng có thể nhìn `bất`, `động`, `sản` như ba token độc lập. Điều đó có thể làm search theo term trả về document liên quan đến một âm tiết nhưng không liên quan đến khái niệm đầy đủ.

### 9.1. Tách âm tiết khác phân đoạn từ

Ví dụ:

```text
Câu: "Tôi đang tìm tài liệu học máy"

Tách bằng khoảng trắng:
  Tôi | đang | tìm | tài | liệu | học | máy

Phân đoạn ngôn ngữ theo từ/thuật ngữ có thể muốn:
  tôi | đang | tìm | tài_liệu | học_máy
```

Ký hiệu gạch dưới ở ví dụ chỉ để **minh họa word segmentation**, không phải định dạng bắt buộc của MongoDB. Một bộ phân tích tiếng Việt thực tế có thể nhận diện từ ghép, từ đa nghĩa, tên riêng, viết tắt và ngữ cảnh theo mô hình/nguyên tắc riêng.

Classic text index **không cung cấp một Vietnamese stemmer và word segmenter chuyên biệt như một công cụ NLP tiếng Việt**. Việc chọn một language khác, chẳng hạn `english`, không làm text index hiểu từ ghép tiếng Việt.

### 9.2. `default_language: "none"` giải quyết điều gì?

MongoDB classic text index có bộ xử lý theo một số ngôn ngữ hỗ trợ. Khi dùng:

```javascript
db.products.createIndex(
  { name: "text", description: "text" },
  { default_language: "none" }
)
```

MongoDB **không thực hiện stemming và stop-word removal theo bộ ngôn ngữ**. Điều này có thể tránh việc áp những quy tắc stemming/stop words không phù hợp lên nội dung tiếng Việt.

Nhưng `none` **không có nghĩa**:

- Tự phân đoạn `bất động sản` thành một đơn vị từ vựng.
- Tự nhận diện `điện thoại` và `smartphone` là đồng nghĩa.
- Tự chấp nhận mọi dạng không dấu/có dấu.
- Tự sửa `samsng`.
- Tự gợi ý `điện` khi user mới gõ `đi`.

**Đây là biện pháp tránh biến đổi sai theo ngôn ngữ, không phải giải pháp NLP tiếng Việt hoàn chỉnh.**

### 9.3. Stemmer và stop words có rủi ro với từ chuyên ngành

Nếu một index dùng rule ngôn ngữ không phù hợp, những từ như mã sản phẩm, tên hãng, tên địa điểm hoặc từ viết tắt có thể bị xử lý ngoài ý muốn. Một hệ thống catalog thường cần giữ chính xác:

```text
iPhone 15
Galaxy A55
USB-C
Wi-Fi 6
Quận 1
RTX 4070
```

Các token có số, ký tự đặc biệt hoặc tên sản phẩm không phải lúc nào cũng thích hợp với cùng bộ phân tích như văn xuôi thông thường.

## 10. Dấu thanh, Unicode và ký tự `đ`

Một từ tiếng Việt có nhiều cách biểu diễn ở mức Unicode. Hai chuỗi trông như nhau có thể được tạo bởi:

- Ký tự **precomposed** đã có sẵn dấu.
- Ký tự nền cộng với **combining marks**.

Ví dụ chữ `ế` có thể là một code point đã ghép hoặc chuỗi code points kết hợp. Nếu ứng dụng chuẩn hóa không thống nhất, equality/prefix matching và việc lưu field search bổ sung có thể cho kết quả bất ngờ.

### 10.1. Chuẩn hóa Unicode NFC

Trong JavaScript:

```javascript
const a = "ế";
const b = "e\u0302\u0301";

print(a === b);  // có thể false ở dạng chuỗi code point
print(a.normalize("NFC") === b.normalize("NFC")); // true
```

`normalize("NFC")` thống nhất cách biểu diễn của các dấu có thể tổ hợp. Điều này **khác** với việc **bỏ dấu để tìm không dấu**.

### 10.2. Bỏ dấu để tạo field search

Một hàm chuẩn hóa ứng dụng đơn giản:

```javascript
function normalizeVietnameseForSearch(input) {
  return String(input ?? "")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLocaleLowerCase("vi-VN")
    .replace(/\s+/g, " ")
    .trim()
    .normalize("NFC");
}

print(normalizeVietnameseForSearch("Điện thoại"));
// "dien thoai"

print(normalizeVietnameseForSearch("Bún bò Huế"));
// "bun bo hue"
```

Giải thích:

1. `NFD` tách nhiều ký tự có dấu thành ký tự nền + combining marks.
2. `\p{M}` trong regular expression Unicode loại các dấu thuộc Unicode category **Mark**.
3. `đ` và `Đ` **không tự biến thành d/D chỉ bằng NFD**, nên được xử lý riêng.
4. `toLocaleLowerCase("vi-VN")` đưa chuỗi về chữ thường theo locale khi môi trường JavaScript hỗ trợ.
5. Chuẩn hóa whitespace và NFC để tạo representation ổn định.

Đây là **hàm phục vụ search**, không phải tiêu chuẩn xử lý ngôn ngữ đúng cho mọi ứng dụng. Nó có thể làm mất sự khác biệt có ý nghĩa:

```text
"ma" vs "má" vs "mà" vs "mã"
"ban" vs "bán" vs "bàn" vs "bạn"
"do" vs "đo"
```

Vì vậy, nên **giữ field gốc** để hiển thị và tra cứu chính xác; field bỏ dấu chỉ là một **biến thể hỗ trợ tìm kiếm**.

### 10.3. Text index và diacritic sensitivity

Classic `$text` có option `$diacriticSensitive`; nhiều text indexes phiên bản hiện đại có chế độ diacritic-insensitive mặc định. Nhưng “không phân biệt dấu” ở cơ chế index/text search **không tương đương** một phép chuẩn hóa tiếng Việt theo nghiệp vụ:

- Cách phân tích token vẫn có thể không khớp từ ghép.
- Cách biểu diễn `đ`/`d` và Unicode cần được kiểm tra thực tế.
- Query không dấu có thể khớp quá rộng hoặc không như kỳ vọng.
- Ranking kết quả đúng dấu có thể cần ưu tiên hơn kết quả chỉ khớp bản bỏ dấu.

Không nên coi `$diacriticSensitive: false` là đủ để triển khai search tiếng Việt chất lượng cao.

## 11. Thiết kế field gốc và field chuẩn hóa

Một schema có thể giữ cả nội dung gốc và bản chuẩn hóa:

```javascript
{
  _id: "P001",
  tenantId: "shop-01",
  name: "Điện thoại Samsung Galaxy A55",
  nameNorm: "dien thoai samsung galaxy a55",
  brand: "Samsung",
  brandNorm: "samsung",
  description: "Điện thoại Android pin lâu và chụp ảnh đẹp"
}
```

Điểm quan trọng:

- `name` là nguồn hiển thị và dữ liệu gốc; không ghi đè thành không dấu.
- `nameNorm` phục vụ prefix/equality/range theo quy tắc normalization đã xác định.
- `brandNorm` có thể phục vụ autocomplete nhãn hiệu ngay từ đầu chuỗi.
- Các bản norm được tạo **cùng thuật toán ở cả index-time và query-time**.
- Khi tên/brand thay đổi, phải cập nhật field gốc và field chuẩn hóa nhất quán.

### Cập nhật dữ liệu mẫu với field chuẩn hóa

Để thực hành trong `mongosh`, có thể tạo bản normalize cho collection lab:

```javascript
function normalizeVietnameseForSearch(input) {
  return String(input ?? "")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLocaleLowerCase("vi-VN")
    .replace(/\s+/g, " ")
    .trim()
    .normalize("NFC");
}

db.products.find({}, { _id: 1, name: 1, brand: 1 }).forEach(p => {
  db.products.updateOne(
    { _id: p._id },
    {
      $set: {
        nameNorm: normalizeVietnameseForSearch(p.name),
        brandNorm: normalizeVietnameseForSearch(p.brand)
      }
    }
  );
});
```

Đây là backfill trên **collection lab**. Không chạy một vòng `find().forEach(updateOne)` không kiểm soát trên hàng triệu document production; ở hệ lớn cần migration/batch, khả năng resume và theo dõi tải.

Tạo index:

```javascript
db.products.createIndex(
  { tenantId: 1, nameNorm: 1 },
  { name: "idx_tenant_nameNorm" }
)

db.products.createIndex(
  { tenantId: 1, brandNorm: 1 },
  { name: "idx_tenant_brandNorm" }
)
```

### Dùng prefix trên field norm

```javascript
const rawInput = "Điện t";
const normalized = normalizeVietnameseForSearch(rawInput);

// Với ví dụ lab đã biết normalized = "dien t".
db.products.find({
  tenantId: "shop-01",
  nameNorm: /^dien t/
}, {
  name: 1, brand: 1, _id: 1
}).limit(10)
```

Trong ứng dụng thật, **không ghép trực tiếp chuỗi user vào regex** nếu chưa escape các metacharacters, áp giới hạn độ dài và ràng buộc chỉ dùng prefix literal. Ví dụ dùng regex literal ở trên để tránh nhầm lẫn giữa regex mang ý nghĩa kỹ thuật và chuỗi người dùng.

### Prefix không thay thế fuzzy

Field `nameNorm` cho phép `dien` khớp `Điện…` sau normalize, nhưng `dnien` vẫn không tự trở thành `dien`. Nếu người dùng gõ sai ký tự, prefix index thường không cứu được; cần thêm fuzzy search hoặc gợi ý sửa.

## 12. Tránh lạm dụng `$regex` cho tiếng Việt

Một hệ thống có thể muốn “chứa chuỗi ở bất kỳ vị trí nào”:

```javascript
db.products.find({
  nameNorm: /thoai/
})
```

Truy vấn này không có prefix neo đầu field nên không mang cùng lợi thế B-tree như:

```javascript
db.products.find({
  nameNorm: /^dien/
})
```

Khi data lớn, số lượng regex contains queries lớn có thể tạo tải đáng kể. Chưa kể:

- Nhiều kết quả không liên quan vì substring ngắn nằm trong nhiều từ.
- Không có cơ chế ranking từ vựng tốt như search engine.
- Không có typo tolerance thực sự.
- User-controlled regex có nguy cơ tiêu tốn tài nguyên nếu ứng dụng truyền thẳng pattern phức tạp.
- Truy vấn theo tenant/quyền truy cập vẫn bắt buộc.

### Regex injection và kiểm soát input

Không nên:

```javascript
// Không phù hợp: userInput được dùng trực tiếp như regex pattern.
db.products.find({
  nameNorm: { $regex: userInput, $options: "i" }
})
```

Nên:

1. Chuẩn hóa chuỗi input.
2. Giới hạn chiều dài input và số request.
3. Escape ký tự regex đặc biệt nếu dùng prefix literal.
4. Neo `^` cho trường hợp prefix-of-field.
5. Dùng collation/index đồng nhất với field đã normalize.
6. Trả `limit` hợp lý và kiểm tra `explain("executionStats")`.

### Một hàm escape regex literal

```javascript
// Escape các ký tự có ý nghĩa đặc biệt trong JS regex.
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const norm = normalizeVietnameseForSearch("Điện t");
const safePrefix = "^" + escapeRegExp(norm);

db.products.find({
  tenantId: "shop-01",
  nameNorm: { $regex: safePrefix }
}).limit(10);
```

Regex này không thêm `i` vì field `nameNorm` đã được chuyển chữ thường. **Không tự suy rằng mọi regex tạo động đều dùng index**; index optimization phụ thuộc pattern, engine, collation và query plan.

## 13. Giới hạn kiến trúc của một text index truyền thống

Ngoài thiếu fuzzy/autocomplete, classic text index có những đặc điểm cần cân nhắc:

### 13.1. Một text index trên một collection

MongoDB cho phép **một text index truyền thống cho mỗi collection**, dù index đó có thể bao gồm nhiều text fields.

```javascript
db.products.createIndex(
  { name: "text", description: "text", brand: "text" },
  {
    name: "idx_all_text",
    weights: {
      name: 10,
      brand: 8,
      description: 2
    },
    default_language: "none"
  }
)
```

Ví dụ này minh họa **thiết kế thay thế** cho index trước, **không phải lệnh chạy tiếp khi collection đã có text index**. Nếu chạy thêm một text index trong cùng collection, MongoDB sẽ không cho tạo một text index thứ hai độc lập.

Một text index nhiều field có thể tìm trên nhiều nội dung, nhưng nếu muốn mỗi field dùng analyzer riêng hoặc tokenization đặc thù cho tên thương hiệu và mô tả, cơ chế truyền thống không linh hoạt bằng search index chuyên dụng.

### 13.2. Compound text index có quy tắc riêng

Có thể kết hợp field thường và text components trong một số compound indexes. Tuy nhiên, thứ tự, kiểu field và yêu cầu equality trên những prefix non-text đứng trước text component có quy tắc riêng. Không coi compound text index như B-tree index thuần rồi sắp field tùy ý.

Ví dụ chỉ mang ý nghĩa thiết kế:

```javascript
db.products.createIndex(
  { tenantId: 1, name: "text", description: "text" },
  { default_language: "none" }
)
```

Với dạng index có prefix thường `tenantId`, truy vấn `$text` cần đáp ứng điều kiện equality tương ứng trên prefix để sử dụng index hợp lệ. Điều này phù hợp với ứng dụng đa tenant nếu mọi truy vấn đều có tenant context, nhưng có thể không phù hợp với báo cáo search toàn catalog.

### 13.3. Không tương đương search index của MongoDB Search

Classic text index được tạo bằng:

```javascript
db.products.createIndex({ name: "text" })
```

MongoDB Search sử dụng **search index và search stage riêng**, chẳng hạn `$search` trên deployment hỗ trợ. Hai loại index **không thay thế lẫn nhau**:

- `$text` yêu cầu classic text index.
- `$search` yêu cầu search index và hạ tầng tìm kiếm được hỗ trợ.
- Tạo classic text index **không** tự làm `$search.autocomplete` hoạt động.
- Tạo search index **không** làm `$text` tự có fuzzy.

Đây là một khác biệt cần xác nhận ngay từ bước thiết kế.

## 14. MongoDB Search/Atlas Search giải quyết được phần nào?

Trong các deployment MongoDB hỗ trợ **MongoDB Search** (thường được biết đến với tên **Atlas Search** trong MongoDB Atlas), người dùng có thể tạo **search index** riêng và dùng aggregation stage `$search` để thực hiện các tác vụ như text ranking, autocomplete hoặc fuzzy matching.

**Không mặc định `$search` chạy trên mọi MongoDB standalone/self-managed replica set**. Tính khả dụng, cú pháp index và các giới hạn phụ thuộc phiên bản và cách triển khai dịch vụ tìm kiếm. Cần có search deployment thực sự hỗ trợ.

### 14.1. Fuzzy text search bằng `$search`

Ví dụ minh họa trên cluster đã tạo search index tên `product_search` với mapping phù hợp cho `name`:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "product_search",
      text: {
        query: "samsng",
        path: "name",
        fuzzy: {
          maxEdits: 1,
          prefixLength: 1,
          maxExpansions: 50
        }
      }
    }
  },
  {
    $match: {
      tenantId: "shop-01"
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      brand: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
])
```

Ý nghĩa:

- `text` là search operator **khác** classic `$text`.
- `fuzzy.maxEdits` đặt giới hạn số thao tác chỉnh sửa trên token được phân tích theo search analyzer.
- `prefixLength` giảm không gian mở rộng khi những ký tự đầu phải khớp.
- `maxExpansions` kiểm soát số biến thể mà search engine xét.
- `searchScore` là điểm ranking của MongoDB Search, không phải classic `textScore`.

**Vấn đề cần đánh giá:** `$match` theo tenant sau `$search` có thể hoạt động về mặt kết quả, nhưng filtering sớm **bên trong `$search.compound.filter`**, với mapping phù hợp, có thể tốt hơn về hiệu năng và giới hạn search scope. Không đặt `$limit` trước filter quyền truy cập rồi tưởng đã lấy đủ 10 kết quả hợp lệ của tenant.

### 14.2. Fuzzy một token không giải quyết tiếng Việt trọn vẹn

Với `samsng` → `samsung`, một edit-distance fuzzy search có thể rất hữu ích. Nhưng với:

```text
"bat dong san" <-> "bất động sản"
"sams ung"     <-> "samsung"
"dien thoai"   <-> "smartphone"
```

Các cặp có thể đòi:

- **Accent folding**.
- **Word segmentation** và xử lý khoảng trắng.
- **Synonym dictionary** của domain.
- **Query rewriting**.
- Ranking có hiểu intent.

Fuzzy matching không tự giải quyết các mục này. Thậm chí bật fuzzy quá rộng trên tiếng Việt có thể làm nhiều token ngắn trở nên gần nhau, tạo false positives.

## 15. Autocomplete của MongoDB Search

MongoDB Search có operator **`autocomplete`** để phục vụ đề xuất khi người dùng gõ từng phần của một hoặc nhiều token, với cấu hình search index phù hợp.

Ví dụ về **ý tưởng cấu hình** field `name` trong search index:

```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "name": [
        {
          "type": "autocomplete",
          "tokenization": "edgeGram",
          "minGrams": 2,
          "maxGrams": 15,
          "foldDiacritics": true
        },
        {
          "type": "string"
        }
      ]
    }
  }
}
```

Đây là **mẫu search index mapping** cho môi trường MongoDB Search có hỗ trợ các tùy chọn tương ứng; không phải cú pháp `createIndex({name:"text"})`. Thiết lập thực tế phải đối chiếu deployment/version. Việc map field thành cả `autocomplete` và `string` có thể hữu ích khi cùng field cần autocomplete và full-text search.

### 15.1. Query autocomplete

```javascript
db.products.aggregate([
  {
    $search: {
      index: "product_autocomplete",
      autocomplete: {
        query: "sam",
        path: "name",
        tokenOrder: "sequential",
        fuzzy: {
          maxEdits: 1
        }
      }
    }
  },
  {
    $project: {
      name: 1,
      brand: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
])
```

Nếu dữ liệu có `Samsung Galaxy A55`, query `sam` có thể có kết quả thông qua index autocomplete phù hợp. Nhưng **chất lượng còn phụ thuộc cách tokenize, analyzer, field mapping, tokenOrder và dữ liệu**, không phải chỉ thêm operator là mọi gợi ý tự đúng.

### 15.2. Edge n-gram hoạt động ra sao?

Đối với token `samsung` và giới hạn từ 2 ký tự:

```text
Token gốc: samsung
Các prefix có thể được index:
  sa
  sam
  sams
  samsu
  samsun
  samsung
```

Đây là giải thích **khái niệm**, không phải danh sách token chắc chắn của mọi analyzer. Cấu hình `minGrams`/`maxGrams`, tokenization và analyzer quyết định token được lập chỉ mục.

### 15.3. Đánh đổi autocomplete

- Tăng số token trong search index, có thể tăng dung lượng và chi phí index.
- Chuỗi rất ngắn dễ gợi ý quá nhiều kết quả.
- Analyzer khi index và search phải phù hợp.
- Gợi ý theo thứ tự token và gợi ý giữa chuỗi có thể cần chiến lược khác.
- Ranking nên ưu tiên đúng brand/term và kết quả phổ biến hơn biến thể fuzzy xa.
- Nên kiểm tra latency khi nhiều người dùng gõ liên tục.

Nếu yêu cầu chỉ là prefix của mã SKU hoặc tên bắt đầu chuỗi, một index B-tree có thể đơn giản hơn. Nếu cần prefix ở **mọi token trong câu**, typo tolerance và ranking, search index chuyên dụng đáng thử hơn.

## 16. Tiếng Việt với MongoDB Search: analyzer vẫn cần thiết

MongoDB Search cung cấp các cơ chế analyzer/tokenizer linh hoạt hơn classic text index, nhưng **không có nghĩa mọi deployment mặc nhiên có bộ phân đoạn từ tiếng Việt tối ưu cho từng lĩnh vực**.

Một chiến lược thường dùng là chuẩn bị:

1. **Nội dung gốc:** để hiển thị, bảo toàn dấu và câu.
2. **Nội dung NFC:** nhất quán về biểu diễn Unicode.
3. **Nội dung normalized không dấu:** để hỗ trợ truy vấn không dấu.
4. **Nội dung đã phân đoạn theo từ:** nếu cần hiểu từ ghép tiếng Việt.
5. **Trường synonyms/aliases:** `điện thoại`, `smartphone`, `đt` theo domain.

Ví dụ document search-ready:

```javascript
{
  _id: "P005",
  name: "Sách học máy cơ bản",
  nameNorm: "sach hoc may co ban",
  searchTerms: [
    "sách học máy",
    "học máy",
    "machine learning",
    "ml"
  ],
  category: "book"
}
```

Không cần nhất thiết lưu tất cả các field trên trong collection nguồn nếu search pipeline hỗ trợ phân tích tương đương lúc index. Nhưng nếu ứng dụng cần tự kiểm soát chuẩn hóa hoặc segmentation, một representation bổ sung giúp tái lập kết quả.

### 16.1. Cùng một thuật toán tại index-time và query-time

Nếu index lưu `dien thoai` nhưng query vẫn gửi `Điện thoại` mà không có analyzer/normalization tương ứng, hiệu quả phụ thuộc vào search engine có tự normalize đúng không.

Một hợp đồng đơn giản:

```text
INGEST:
    rawName
      -> Unicode NFC
      -> lowercase/fold accents
      -> tokenize/segment nếu cần
      -> index searchable fields

QUERY:
    rawQuery
      -> đúng normalization policy
      -> tokenize/segment nếu cần
      -> truy vấn cùng searchable fields
```

Nếu pipeline ingest và pipeline query khác nhau, đặc biệt khi đổi phiên bản tokenizer tiếng Việt, kết quả có thể thiếu hoặc lệch. Khi đổi chính sách phân đoạn từ, có thể cần **reindex/backfill** và so sánh chất lượng trước/sau.

### 16.2. Từ ghép và đồng nghĩa

Ví dụ:

```text
Người dùng nhập: "laptop học sinh"
Sản phẩm ghi:    "máy tính xách tay dành cho học tập"
```

Mặc dù hai câu có liên quan về ý nghĩa, classic text index hoặc fuzzy 1–2 edits **không chắc tìm ra** vì ít token trùng trực tiếp. Cần synonym dictionary, query rewriting hoặc semantic retrieval.

Đối với tiếng Việt, synonyms có thể chứa các cặp:

```text
điện thoại  <-> smartphone
máy tính xách tay <-> laptop
điều hòa <-> máy lạnh
xe máy <-> mô tô (tùy ngữ cảnh)
```

Không phải mọi cặp đều tương đương hoàn toàn trong mọi lĩnh vực. Synonym phải được **đánh giá theo domain** để tránh trả kết quả sai.

### 16.3. Tiếng Việt có nhiều khoảng trắng giữa các âm tiết

Autocomplete có thể gợi ý tốt từng token nhưng thiếu chất lượng khi người dùng gõ:

```text
"bat d..."  -> "bất động sản"
"dien th..." -> "điện thoại"
```

Muốn trải nghiệm tốt, cần kiểm tra analyzer xử lý chuỗi nhiều âm tiết và những query đang gõ dở ra sao. Không chỉ test với từ thương hiệu tiếng Anh như `samsung` rồi kết luận autocomplete tiếng Việt đã hoàn thiện.

## 17. So sánh bốn chiến lược kỹ thuật

| Chiến lược | Mạnh ở đâu? | Yếu ở đâu? | Khi nên chọn |
| --- | --- | --- | --- |
| **Equality/B-tree** | ID, SKU, prefix có cấu trúc | Không full-text/fuzzy thực sự | Exact lookup, mã sản phẩm, gợi ý tiền tố đơn giản |
| **Classic text index + `$text`** | Keyword search, phrase/exclusion, score cơ bản | Thiếu typo/autocomplete/Vietnamese NLP | Search đơn giản, yêu cầu ít |
| **Field norm + prefix/alias** | Tự kiểm soát dấu, viết tắt, prefix; dễ triển khai | Chịu trách nhiệm sync field; khó ranking/fuzzy rộng | Catalog vừa/nhỏ, autocomplete có kiểm soát |
| **MongoDB Search/Atlas Search** | Fuzzy, autocomplete, analyzer/ranking nâng cao | Cần search index/deployment hỗ trợ, tuning và chi phí | Product search/UX đòi chất lượng hơn |
| **Search engine chuyên dụng khác** | Hệ sinh thái analyzer, synonyms, typo, scale/search analytics tùy sản phẩm | Đồng bộ dữ liệu, vận hành, latency/consistency | Hệ thống cần chức năng chuyên sâu hoặc hạ tầng đã có |

Không có lựa chọn nào miễn phí. Một search index có thể cần đồng bộ bất đồng bộ từ dữ liệu gốc, khiến tài liệu vừa ghi chưa xuất hiện tức thì trong kết quả tìm kiếm. Yêu cầu **read-after-write search visibility** phải được đo và thiết kế rõ.

### Quy trình nâng cấp dần

```text
Giai đoạn 1:
  exact lookup + text index
          |
          v
Thêm normalize:
  Unicode NFC, no-accent fields, tenant filtering
          |
          v
Thêm autocomplete:
  prefix field hoặc MongoDB Search autocomplete
          |
          v
Thêm fuzzy:
  typo tolerance + ranking exact > fuzzy
          |
          v
Nâng tiếng Việt:
  segmentation, synonyms, evaluation set
```

Một ứng dụng có thể dừng ở giai đoạn 1 hoặc 2 nếu KPI thực tế đã đạt. Không triển khai fuzzy/semantic chỉ vì công nghệ có sẵn.

## 18. Multi-tenant search: đúng kết quả vẫn phải đúng quyền

Trong bộ dữ liệu mẫu, cả `shop-01` và `shop-02` đều có điện thoại Samsung. Một query:

```javascript
db.products.find({
  $text: { $search: "Samsung" }
})
```

có thể trả sản phẩm của **nhiều tenant**. Trong ứng dụng nhiều khách hàng, đây có thể là lỗi bảo mật dữ liệu.

Truy vấn phù hợp hơn:

```javascript
db.products.find({
  tenantId: "shop-01",
  $text: { $search: "Samsung" }
})
```

Với MongoDB Search, nên thiết kế **filter tenant/permissions phù hợp ngay trong search stage khi có thể**, thay vì chỉ cắt kết quả sau khi đã `$limit` top N toàn cục.

### Lỗi khi filter sau `$limit`

```javascript
// Không phù hợp khi top 10 toàn cụm chứa nhiều tenant:
db.products.aggregate([
  { $search: { /* search toàn catalog */ } },
  { $limit: 10 },
  { $match: { tenantId: "shop-01" } }
])
```

Nếu trong 10 kết quả đầu chỉ có hai sản phẩm của `shop-01`, UI có thể hiển thị hai gợi ý dù còn nhiều sản phẩm hợp lệ bị xếp sau 10 kết quả toàn cục. Ngoài ra, search scope không được thu hẹp sớm.

Mọi lớp exact/prefix/fuzzy/autocomplete đều cần **context xác thực**, scope và quy tắc xếp hạng hợp lệ. Truy vấn nhanh nhưng để lộ tên/mô tả của tenant khác là một thiết kế sai.

## 19. Lựa chọn ranking cho tiếng Việt

Giả sử người dùng gõ `dien thoai samsung`, hệ thống có ba dạng match:

1. Sản phẩm có cụm `Điện thoại Samsung` ngay trong tên.
2. Sản phẩm chỉ có `Samsung` trong description.
3. Sản phẩm khác chỉ gần giống vì fuzzy/normalization.

Một chiến lược ranking có thể:

```text
Exact phrase/title match           ưu tiên cao
Exact word/title match             ưu tiên cao
Accent-insensitive normalized hit  ưu tiên tiếp theo
Prefix/autocomplete hit            ưu tiên theo UI
Fuzzy typo match                   thấp hơn exact
Synonym expansion                  theo domain
Popularity / inventory / recency   signal bổ sung
```

Đây là **thứ tự minh họa**, không phải trọng số do MongoDB tự áp dụng. Sản phẩm thật cần ghi rõ hành vi mong muốn và đo trên tập query người dùng thực.

### Khớp có dấu nên ưu tiên hơn bản không dấu khi phù hợp

Nếu user gõ `bán`, các từ `bàn`, `ban`, `bạn` có thể trùng sau khi bỏ dấu. Một công cụ chỉ tìm trên `nameNorm` sẽ mất sự khác biệt này. Có thể ưu tiên:

- Match đúng chuỗi có dấu.
- Match đúng từ khóa sau Unicode normalization.
- Match trên bản bỏ dấu nếu không có kết quả đủ tốt.

Với tên người, địa điểm, thuật ngữ pháp lý hay mã chuyên môn, bỏ dấu quá mạnh có thể làm giảm độ chính xác. Cần quyền lựa chọn giữa **recall** và **precision**, không đơn giản luôn bật bỏ dấu.

## 20. Highlight và snippet: không ghép chuỗi tùy tiện

Một UI tìm kiếm thường muốn tô đậm phần khớp:

```text
Người dùng: "samsung"
Hiển thị:  "Điện thoại [Samsung] Galaxy A55"
```

Classic `textScore` chỉ là điểm số, **không trả một vùng highlight ngữ nghĩa đầy đủ**. Nếu frontend tự dùng search string để tìm substring trong tên, nó có thể thất bại khi:

- Query không dấu, tên có dấu.
- Match đến từ synonym hoặc typo.
- Match nằm trong description, không phải name.
- Unicode normalization thay đổi vị trí code point.
- HTML được render không escape đúng, gây lỗi hiển thị hoặc rủi ro chèn nội dung.

MongoDB Search có những khả năng highlight trên deployment và index phù hợp, nhưng phải kiểm tra giới hạn và API của search engine. Nếu tự xây highlight, **không render raw user input như HTML**; giữ phân biệt rõ text gốc, token match và vùng hiển thị.

## 21. Đọc `explain()` và đo hiệu năng

### 21.1. Classic `$text`

```javascript
db.products.find({
  tenantId: "shop-01",
  $text: { $search: "Samsung" }
}).explain("executionStats")
```

Đối chiếu các yếu tố:

- Query có dùng text index dự kiến không?
- Bao nhiêu keys/docs được xét?
- Predicate tenant có được áp dụng hợp lý không?
- Score/sort có phát sinh thêm chi phí không?
- Dữ liệu lớn hơn/đa dạng ngôn ngữ có thay đổi selectivity không?

### 21.2. Prefix B-tree

```javascript
db.products.find({
  tenantId: "shop-01",
  nameNorm: /^dien/
}).explain("executionStats")
```

So với contains:

```javascript
db.products.find({
  tenantId: "shop-01",
  nameNorm: /dien/
}).explain("executionStats")
```

Quan sát index usage, examined keys/docs và thời gian trên **tập dữ liệu đại diện**. Dữ liệu lab có 10 document không đủ chứng minh khả năng scale.

### 21.3. MongoDB Search

Với `$search`, cần đọc **search explain/metrics** theo phiên bản/hạ tầng hỗ trợ và đo latency tổng:

- Index build/update lag.
- Search stage execution time.
- Query expansion/fuzzy expansions.
- Filter/selectivity.
- Documents trả về và xử lý pipeline tiếp theo.
- p50/p95/p99 khi nhiều request đồng thời.

**Đừng chỉ so số milliseconds của một lần chạy.** Cache ấm, index mới xây, load đồng thời, số kết quả trả và tài nguyên search backend đều có thể làm sai lệch kết luận.

## 22. Thiết kế API tìm kiếm theo hai giai đoạn

Một kiến trúc có thể tách **suggest API** và **search results API**:

```text
Người dùng gõ:
  "s" -> "sa" -> "sam"
          |
          v
  /search/suggest?q=sam
   - prefix / autocomplete index
   - min length
   - tenant filter
   - limit 5-10
          |
          v
   Gợi ý ngắn (brand/product)

Người dùng nhấn Enter:
          |
          v
  /search?q=samsng
   - exact keyword
   - fallback fuzzy nếu cần
   - filter category/tenant
   - rank kết quả đầy đủ
          |
          v
  Danh sách kết quả có phân trang
```

Tách hai API có lợi:

- Suggest ưu tiên **độ trễ thấp** và ít kết quả.
- Full search ưu tiên **recall, relevance và khả năng phân trang**.
- Không cần chạy fuzzy expansions nặng theo mỗi ký tự đầu tiên.
- Có thể áp dụng timeout/monitoring khác nhau.

Một giải pháp search không chỉ có query MongoDB; **contract API** và hành vi khi query ngắn, rỗng hoặc sai chính tả cũng phải được định nghĩa.

## 23. Java MongoDB Sync Driver: classic text index và truy vấn

Ví dụ dưới đây sử dụng MongoDB Java Sync Driver. Nó minh họa cách chạy classic text search theo tenant; ứng dụng cần dependency `mongodb-driver-sync` phù hợp và biến môi trường `MONGODB_URI`.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

public class VietnameseTextSearchDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("mongo_text_search_lab");
            MongoCollection<Document> products =
                db.getCollection("products");

            String tenantId = "shop-01";
            String keyword = "Samsung Galaxy";

            Bson filter = Filters.and(
                Filters.eq("tenantId", tenantId),
                Filters.text(keyword)
            );

            Document projection = new Document("name", 1)
                .append("brand", 1)
                .append("score",
                    new Document("$meta", "textScore"));

            Document sort = new Document(
                "score", new Document("$meta", "textScore"));

            for (Document product : products.find(filter)
                    .projection(projection)
                    .sort(sort)
                    .limit(10)) {
                System.out.println(product.toJson());
            }
        }
    }
}
```

Đoạn mã giả định text index đã được tạo. Nếu collection **không có text index hợp lệ**, server sẽ trả lỗi cho `$text`. Driver không tự tạo index chỉ vì gọi `Filters.text()`.

### Kết quả rỗng khi gõ `samsng` không phải lỗi driver

Nếu thay:

```java
String keyword = "samsng";
```

và text search không trả kết quả, đó có thể là **giới hạn của text token matching**, không phải vấn đề mã hóa Java hay kết nối.

Không nên viết vòng lặp tự động thêm ký tự vào keyword rồi gửi hàng trăm truy vấn `$text` để giả lập fuzzy. Cách đó khó kiểm soát tải và chất lượng; nếu cần typo tolerance, dùng engine hoặc pipeline được thiết kế cho fuzzy.

## 24. Java: chuẩn hóa tiếng Việt khi ingest và query

Java cung cấp API Unicode normalization trong `java.text.Normalizer`:

```java
import java.text.Normalizer;
import java.util.Locale;

public class VietnameseSearchNormalize {
    public static String normalize(String input) {
        if (input == null) {
            return "";
        }

        String decomposed = Normalizer.normalize(
            input, Normalizer.Form.NFD);

        String noMarks =
            decomposed.replaceAll("\\p{M}+", "");

        String noSpecialD = noMarks
            .replace('đ', 'd')
            .replace('Đ', 'D');

        String lower =
            noSpecialD.toLowerCase(Locale.forLanguageTag("vi-VN"));

        String collapsed = lower
            .replaceAll("\\s+", " ")
            .trim();

        return Normalizer.normalize(
            collapsed, Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        System.out.println(normalize("Điện thoại"));
        // dien thoai

        System.out.println(normalize("Bất động sản"));
        // bat dong san
    }
}
```

Hàm Java và JavaScript ở các mục trước phải được giữ **tương thích về cách chuẩn hóa** nếu cùng hệ thống có nhiều service viết/đọc `nameNorm`. Có thể tạo unit tests chung cho các trường hợp:

```text
"Điện thoại"        -> "dien thoai"
"ĐIỆN THOẠI"        -> "dien thoai"
"Bún bò Huế"        -> "bun bo hue"
"Máy học"           -> "may hoc"
"  Điện   thoại  "  -> "dien thoai"
```

Nhưng nhớ rằng normalize bỏ dấu làm mất thông tin; chỉ dùng cho **searchable fields**, không tự sửa `name` gốc.

### Java prefix search an toàn

Một ví dụ đơn giản:

```java
import com.mongodb.client.model.Filters;
import org.bson.conversions.Bson;
import java.util.regex.Pattern;

String userInput = "Điện t";
String normalized =
    VietnameseSearchNormalize.normalize(userInput);

String safePrefix =
    "^" + Pattern.quote(normalized);

Bson filter = Filters.and(
    Filters.eq("tenantId", "shop-01"),
    Filters.regex("nameNorm", safePrefix)
);
```

`Pattern.quote()` bảo vệ query khỏi việc input bị hiểu thành regex pattern. Tuy nhiên, **cú pháp escaped với `\Q...\E` có thể không được optimizer MongoDB nhận diện như một literal prefix để dùng index tối ưu ở mọi phiên bản**, nên cần kiểm tra `explain()`. Đối với hệ đòi prefix index hiệu quả, có thể dùng một hàm escape chỉ những metacharacters theo quy tắc đã kiểm chứng hoặc một chiến lược tìm kiếm khác.

Không tự suy rằng `Filters.regex()` luôn đi qua index hoặc luôn phù hợp với search volume lớn.

## 25. Java: gọi MongoDB Search qua aggregation

Khi cluster có search index `product_search`, Java có thể tạo BSON pipeline:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

public class MongoDbSearchFuzzyExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("mongo_text_search_lab");
            MongoCollection<Document> products =
                db.getCollection("products");

            Document fuzzy = new Document("maxEdits", 1)
                .append("prefixLength", 1)
                .append("maxExpansions", 50);

            Document textSearch = new Document("query", "samsng")
                .append("path", "name")
                .append("fuzzy", fuzzy);

            Document searchStage = new Document("$search",
                new Document("index", "product_search")
                    .append("text", textSearch));

            Document tenantFilter = new Document("$match",
                new Document("tenantId", "shop-01"));

            Document projection = new Document("$project",
                new Document("name", 1)
                    .append("brand", 1)
                    .append("score",
                        new Document("$meta", "searchScore")));

            List<Document> pipeline = Arrays.asList(
                searchStage,
                tenantFilter,
                projection,
                new Document("$limit", 10)
            );

            for (Document product : products.aggregate(pipeline)) {
                System.out.println(product.toJson());
            }
        }
    }
}
```

Đây là **ví dụ trên MongoDB Search deployment được hỗ trợ**, không phải mã chạy với một classic text index thông thường. Trong hệ đa tenant và workload lớn, nên đưa điều kiện tenant vào `$search.compound.filter` với mapping đúng để tránh search trên phạm vi rộng rồi lọc về sau.

## 26. Khi nào nên dùng search engine riêng?

MongoDB Search có thể đáp ứng nhiều yêu cầu ngay trong hệ sinh thái MongoDB, nhưng cũng có những tình huống cần cân nhắc một search service khác:

- Tổ chức đã vận hành một engine tìm kiếm chuyên dụng với analyzer tiếng Việt được kiểm chứng.
- Hệ thống cần **spell correction**, **synonym management**, **custom tokenization**, **highlight** và nhiều chiến lược ranking nâng cao.
- Query volume và latency yêu cầu tách hoàn toàn compute search khỏi database giao dịch.
- Cần một hệ **indexing pipeline** riêng hợp nhất tài liệu từ nhiều nguồn ngoài MongoDB.
- Cần search analytics, click feedback, learning-to-rank hoặc query suggestion đặc thù.

Đổi lại, hệ thống phải giải quyết **đồng bộ dữ liệu** từ MongoDB sang search engine, độ trễ index, retry, missing/deleted documents, idempotency, replay và consistency.

Một sơ đồ:

```text
        Ứng dụng ghi
             |
             v
       MongoDB products
             |
        Change Stream/
        Outbox/Queue
             |
             v
       Indexing Service
          /      \
   normalize    segment
          \      /
             |
             v
        Search Index
             |
         Search API
             |
             v
        Người dùng
```

Nếu dùng Change Stream, cần checkpoint/resume và xử lý lịch sử oplog không còn. Search service không tự được miễn các bài toán **exactly-once, backfill và xóa tài liệu**.

## 27. Bộ tiêu chí đánh giá chất lượng tìm kiếm

Không nên đánh giá bằng cảm giác rằng “gõ vài từ thấy sản phẩm”.

Hãy tạo **query set** gồm những tình huống đại diện:

| Nhóm | Ví dụ query | Kỳ vọng |
| --- | --- | --- |
| Đúng từ có dấu | `điện thoại samsung` | Điện thoại Samsung lên đầu |
| Không dấu | `dien thoai samsung` | Kết quả vẫn liên quan |
| Sai chính tả | `samsng galaxy` | Fuzzy giúp tìm sản phẩm |
| Prefix đầu tên | `dien th` | Gợi ý tên phù hợp |
| Prefix giữa tên | `sam` | Gợi ý Samsung ở field/thương hiệu |
| Từ ghép | `bất động sản` | Ưu tiên đúng khái niệm |
| Viết tắt | `dt samsung` | Có kết quả nếu domain định nghĩa alias |
| Đồng nghĩa | `smartphone` | Có thể trả điện thoại theo synonym |
| Nhiều dấu dễ lẫn | `ban` / `bàn` / `bán` | Không khớp quá rộng khi yêu cầu precision |
| Mã chính xác | `SKU-IPH-15-BLK` | Trả đúng SKU, không fuzzy làm sai |
| Tenant isolation | Sản phẩm `shop-02` khi user ở `shop-01` | Không xuất hiện |
| Query rất ngắn | `a` | Có policy gợi ý rõ, không trả vô hạn |
| Query rỗng | `" "` | Không quét toàn catalog ngoài ý muốn |
| Unicode khác dạng | NFC vs decomposed accents | Hành vi nhất quán |

### Các metric có ý nghĩa

- **Recall@K:** trong top K có bao nhiêu kết quả liên quan cần tìm?
- **Precision@K:** tỷ lệ kết quả liên quan trong top K.
- **MRR/NDCG:** đánh giá vị trí của kết quả đúng/relevance nếu có nhãn.
- **Zero-result rate:** tỷ lệ query không trả kết quả.
- **Typo recovery rate:** tỷ lệ lỗi gõ vẫn tìm được sản phẩm mong muốn.
- **Suggestion acceptance rate:** tỷ lệ gợi ý được người dùng chọn.
- **p50/p95/p99 latency:** đặc biệt quan trọng cho typeahead.
- **Resource/storage cost:** kích thước search index, CPU/RAM/I/O.
- **Freshness:** độ trễ từ lúc thêm sản phẩm đến lúc tìm thấy.
- **Security leakage rate:** cần bằng 0 theo chính sách truy cập.

Đây là một bộ metric tham khảo; đội sản phẩm nên xác định **K**, cách gắn nhãn relevance và trọng số theo loại query trước khi benchmark.

## 28. Benchmark công bằng giữa các cách tiếp cận

Để so sánh classic `$text`, prefix index và MongoDB Search:

1. Dùng **cùng collection logic** hoặc cùng tập dữ liệu sản phẩm.
2. Đảm bảo bộ index đã được build và hệ thống ổn định trước đo.
3. Sử dụng cùng query set, phân bổ query thường gặp và query khó.
4. Phân biệt **exact, keyword, autocomplete, typo, no-accent, synonyms**.
5. Đo chất lượng kết quả **và latency**; nhanh nhưng trả sai sản phẩm không phải thành công.
6. Kiểm tra concurrency, cache lạnh/ấm và update/search-index refresh lag.
7. Theo dõi index/storage overhead và lượng ghi lúc catalog thay đổi.
8. Ghi nhận version MongoDB, driver, search deployment và analyzer.

### Ví dụ bảng quyết định

| Tiêu chí | Classic `$text` | Prefix `nameNorm` | MongoDB Search |
| --- | --- | --- | --- |
| Keyword search | Tốt cho cơ bản | Hạn chế | Có |
| Prefix tên | Không tự có | Có, nếu index phù hợp | Có với autocomplete |
| Prefix giữa tên/token | Không | Không nếu chỉ prefix-of-field | Có thể hỗ trợ tùy analyzer/tokenization |
| Typo `samsng` | Không | Không | Có với fuzzy |
| No-accent Vietnamese | Phụ thuộc text index behavior | Rõ nếu tự normalize | Có thể thiết kế analyzer/field norm |
| Vietnamese word segmentation | Không chuyên biệt | Phải tự làm | Tùy custom preprocessing/analyzer |
| Ranking phong phú | Hạn chế | Thường phải tự làm | Linh hoạt hơn |
| Phức tạp vận hành | Thấp | Vừa (sync field) | Cao hơn (search index, tuning) |
| Query latency | Cần đo | Cần đo | Cần đo |
| Search freshness | Liên quan index dữ liệu MongoDB | Liên quan cập nhật field norm | Có thể có search indexing lag |

**Không gán “luôn nhanh hơn” cho bất kỳ cột nào** khi chưa có số liệu của workload cụ thể.

## 29. Các lỗi thường gặp khi triển khai

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `$text` trả lỗi không có index | Collection chưa tạo text index | Tạo text index hợp lệ; kiểm tra tên/trường |
| Tìm `sam` không ra Samsung | Classic text index không tự lập mọi prefix | Prefix field/autocomplete index |
| Tìm `samsng` không ra Samsung | Không có fuzzy edit distance | Search engine fuzzy/query correction |
| Query không dấu cho kết quả khó hiểu | Diacritics, Unicode và tokenizer khác kỳ vọng | Test accent behavior, chuẩn hóa ứng dụng |
| `đ` không khớp `d` như kỳ vọng | Folding Unicode không đồng nhất | Normalize riêng `đ`/`Đ` nếu phù hợp |
| Tìm `học máy` ra tài liệu không liên quan | Tách theo âm tiết, thuật ngữ nhiều từ | Segmentation/phrase/synonym/ranking |
| Kết quả cross-tenant | Thiếu tenant/auth filter | Filter quyền ở query và search stage |
| Contains regex chậm | Không có prefix index hiệu quả | Dùng prefix đúng bài toán hoặc search engine |
| Regex người dùng gây tải lớn | User input thành regex pattern phức tạp | Escape, rate limit, input length, index |
| Có nhiều field cần analyzer khác nhau | Classic text index hạn chế | Search index custom mapping |
| Autocomplete trả nhiều kết quả sai | Prefix quá ngắn, fuzzy quá rộng | Min length, ranking, tokenization |
| Gợi ý không có sản phẩm vừa thêm | Search index freshness lag | Theo dõi indexing lag, UX fallback |
| Tạo text index thứ hai thất bại | Một classic text index/collection | Thiết kế lại compound text index |
| `$search` báo không hỗ trợ | Deployment chưa hỗ trợ MongoDB Search | Kiểm tra hạ tầng/index/server version |
| `$limit` trước tenant filter cho quá ít kết quả | Top K toàn catalog rồi mới lọc | Đưa filter vào search scope trước khi limit |
| Name norm khác nhau giữa Java và JS | Hai normalization implementations lệch | Test cases dùng chung, version hóa policy |
| Dữ liệu trùng tên nhưng khác SKU lẫn nhau | Fuzzy dùng cho exact ID | Chuyển exact lookup riêng |

## 30. Bài tập và đáp án

### Bài 1. Nhận diện đúng công cụ

Người dùng nhập `sam` và UI muốn gợi ý `Samsung Galaxy A55` ngay khi đang gõ. Một classic text index trên `name` có đủ không?

**Đáp án:** Không. `$text` tìm token, không tự tạo prefix. Có thể dùng field chuẩn hóa + prefix khi gợi ý đầu tên/thương hiệu hoặc MongoDB Search autocomplete nếu cần gợi ý theo token và ranking.

### Bài 2. Tìm lỗi chính tả

Text index có token `samsung`, user gõ `samsng`. Có thể thêm `fuzzy: {maxEdits:1}` vào `$text` không?

**Đáp án:** Không. `fuzzy` không phải option của classic `$text`. Cần dùng MongoDB Search text operator có fuzzy trên deployment hỗ trợ hoặc một search engine khác.

### Bài 3. Vietnamese `none`

Vì sao dùng `default_language:"none"` có thể thích hợp hơn ép `english` cho collection tên sản phẩm tiếng Việt? Nó có tự nhận diện từ ghép không?

**Đáp án:** `none` tránh stemming/stop-word removal theo quy tắc ngôn ngữ không phù hợp, nhưng **không** cung cấp Vietnamese word segmentation, synonym hoặc fuzzy search.

### Bài 4. Chuẩn hóa ký tự `đ`

Hàm `normalize("NFD")` rồi bỏ combining marks có tự biến `điện thoại` thành `dien thoai` hoàn toàn không?

**Đáp án:** Không. `đ` là ký tự riêng, cần xử lý `đ` → `d` và `Đ` → `D` nếu muốn accent-folding kiểu đó. Đồng thời cần lowercasing và chuẩn hóa whitespace.

### Bài 5. Truy vấn nào hưởng lợi từ prefix index?

Giả sử có index B-tree trên `{tenantId:1,nameNorm:1}` và field norm đã lowercase:

```javascript
// A
{ tenantId: "shop-01", nameNorm: /^dien/ }

// B
{ tenantId: "shop-01", nameNorm: /dien/ }
```

**Đáp án:** A có anchored literal prefix, thường có khả năng tận dụng index hiệu quả hơn B. Cần xác nhận bằng `explain` trong môi trường thực.

### Bài 6. Prefix-of-field so với prefix-of-token

`nameNorm` của sản phẩm là `"dien thoai samsung galaxy a55"`. Vì sao regex `/^sam/` trên field này không tìm được?

**Đáp án:** Chuỗi bắt đầu bằng `dien` chứ không phải `sam`. Gợi ý prefix ở giữa tên cần field riêng/brand field/token prefix index hoặc autocomplete index phù hợp.

### Bài 7. Fuzzy không giải synonyms

Người dùng nhập `laptop`, document chỉ chứa `máy tính xách tay`. Vì sao fuzzy maxEdits=1 không phải cách giải quyết đúng?

**Đáp án:** Hai cụm khác nhau về từ vựng và độ dài, không phải lỗi gõ một ký tự. Cần synonym mapping, query expansion hoặc semantic search.

### Bài 8. Tìm nhiều từ

Đoạn:

```javascript
db.products.find({
  $text: { $search: "Samsung Galaxy" }
})
```

có chắc chỉ trả document chứa nguyên cụm `Samsung Galaxy` theo đúng thứ tự không?

**Đáp án:** Không. Những term không được đặt trong phrase quote không tự có ngữ nghĩa phrase AND theo thứ tự. Cần dùng cú pháp phrase phù hợp hoặc search operator được thiết kế cho yêu cầu đó.

### Bài 9. Một text index mỗi collection

Collection đã có text index trên `name`. Nhóm phát triển muốn tạo text index thứ hai độc lập trên `description`. Có thể làm trực tiếp không?

**Đáp án:** Không theo quy tắc classic text index. Một collection chỉ có một classic text index, nhưng index đó có thể lập chỉ mục nhiều fields với weights. Nếu cần analyzer/index strategies độc lập, đánh giá MongoDB Search.

### Bài 10. Lỗi gợi ý cross-tenant

Search index có nhiều sản phẩm, nhưng API chạy `$search` → `$limit: 10` → `$match: {tenantId:"shop-01"}`. Vấn đề là gì?

**Đáp án:** Limit trên top 10 toàn bộ corpus có thể bỏ những kết quả của `shop-01` nằm sau vị trí 10; cần đưa điều kiện quyền/tenant vào phạm vi search sớm, lý tưởng trong search stage với index mapping phù hợp, rồi mới lấy top N. Đồng thời bảo đảm quyền truy cập ở tầng ứng dụng.

### Bài 11. Bỏ dấu làm mất thông tin

Tại sao không lưu tên sản phẩm chỉ ở dạng không dấu?

**Đáp án:** Dạng không dấu làm mất thông tin hiển thị và ngữ nghĩa: `bán`, `bàn`, `bạn` có thể thành cùng chuỗi `ban`. Nên giữ field gốc và dùng field chuẩn hóa riêng phục vụ search.

### Bài 12. Tính năng nào không thuộc `$text`?

Chọn hai khả năng **không có sẵn** trong classic `$text`: (A) textScore, (B) phrase search, (C) fuzzy edit distance, (D) autocomplete edge-gram.

**Đáp án:** C và D. A và B là các khả năng có trong phạm vi text search truyền thống (với giới hạn về ngôn ngữ/tokenization).

### Bài 13. Vì sao search index cần reindex khi đổi tokenizer?

Nhóm phát triển đổi chính sách phân đoạn `học máy` thành một term đặc biệt, nhưng chỉ thay bước normalize của query, không cập nhật dữ liệu/index cũ. Vấn đề gì?

**Đáp án:** Token/index-time representation và query-time representation có thể không khớp, làm giảm recall và thay đổi ranking. Cần một chính sách thống nhất và backfill/reindex có kiểm soát khi đổi analyzer/segmentation.

### Bài 14. Chọn giải pháp theo độ phức tạp

Ứng dụng nội bộ có 20.000 mã thiết bị, user luôn tìm đúng mã hoặc prefix đầu mã, không cần fuzzy hay tiếng Việt. Có nên triển khai MongoDB Search phức tạp ngay?

**Đáp án:** Không nhất thiết. Equality và index B-tree cho mã, cùng prefix query được kiểm chứng bằng `explain`, có thể đủ. Chọn công cụ nhỏ nhất đáp ứng yêu cầu.

### Bài 15. Kiểm thử typo và precision

Bạn bật fuzzy maxEdits=2 và thấy zero-result rate giảm. Có thể kết luận chất lượng search tốt hơn chưa?

**Đáp án:** Chưa. Fuzzy rộng có thể trả nhiều kết quả sai. Cần đo precision/recall@K, vị trí kết quả đúng, query latency và trải nghiệm gợi ý trên tập lỗi gõ đại diện.

## 31. Checklist thiết kế search tiếng Việt

Khi triển khai:

1. **Phân loại query:** exact ID/SKU, keyword, prefix, fuzzy, synonyms hay semantic.
2. **Giữ dữ liệu gốc:** lưu đúng tên, dấu, mã, mô tả để hiển thị và đối soát.
3. **Chuẩn hóa Unicode:** NFC, whitespace và quy tắc viết hoa/viết thường nhất quán.
4. **Quyết định accent folding:** có cần bỏ dấu không, `đ` xử lý ra sao, ưu tiên khớp có dấu thế nào.
5. **Xử lý từ ghép:** kiểm tra từ nhiều âm tiết và cụm từ chuyên ngành.
6. **Đồng bộ index/query normalization:** cùng thuật toán và phiên bản, có test cases.
7. **Không ép fuzzy vào classic `$text`:** dùng search engine hoặc giải pháp riêng nếu cần edit distance.
8. **Không ép autocomplete vào text index:** dùng prefix index hoặc autocomplete search index phù hợp.
9. **Giới hạn tenant/permission:** filter được áp dụng trước top-K và không tạo rò rỉ dữ liệu.
10. **Thiết kế ranking:** exact > normalized/fuzzy trong những trường hợp phù hợp; cân nhắc brand, availability, category.
11. **Giới hạn query đầu vào:** trim, max length, min length, escape regex, rate limit.
12. **Đo chất lượng:** query set tiếng Việt, recall/precision, typo recovery và zero-result rate.
13. **Đo hiệu năng:** p95/p99, index/storage overhead, concurrency, search freshness.
14. **Kiểm tra hạ tầng:** classic text index hay MongoDB Search; không trộn cú pháp của hai công cụ.
15. **Có đường migration/reindex:** khi thêm field norm, đổi analyzer, synonyms hoặc ranking.

## 32. Tổng kết

**Classic MongoDB text index** là giải pháp tìm từ khóa cơ bản, có ích cho token matching, phrase/exclusion syntax và `textScore`. Nhưng nó **không tự có tìm gần đúng theo typo**, **không tự xây autocomplete prefixes**, và **không có bộ phân tích ngôn ngữ tiếng Việt chuyên sâu**. Những giới hạn này không phải lỗi của `$text` mà là khác biệt giữa **text keyword index** và **search engine**.

Đối với tiếng Việt, cần hiểu rằng **bỏ dấu không đồng nghĩa hiểu ngôn ngữ**: Unicode normalization, ký tự `đ`, từ đa âm tiết, viết tắt, synonyms và chính sách ranking đều ảnh hưởng chất lượng. Một hướng triển khai thực tế là giữ **field gốc**, bổ sung **field chuẩn hóa**, dùng **B-tree prefix index** cho yêu cầu đơn giản, và chọn **MongoDB Search/Atlas Search hoặc search engine khác** khi cần autocomplete/fuzzy/analyzer nâng cao.

Cuối cùng, lựa chọn nên dựa trên **query thật của người dùng, bảo mật tenant, chất lượng kết quả và latency**, không dựa vào giả định cứ tạo text index là tìm kiếm sẽ “giống Google”. Thiết kế tìm kiếm tốt là chọn đúng cơ chế cho đúng kiểu truy vấn, kiểm thử kỹ tiếng Việt và duy trì khả năng đánh giá khi dữ liệu/nhu cầu thay đổi.

### Tài liệu MongoDB để đối chiếu theo phiên bản

- [MongoDB Manual — Text Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/)
- [MongoDB Manual — `$text` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/text/)
- [MongoDB Search — Overview](https://www.mongodb.com/docs/atlas/atlas-search/)
- [MongoDB Search — Fuzzy Matching](https://www.mongodb.com/docs/atlas/atlas-search/text/)
- [MongoDB Search — Autocomplete](https://www.mongodb.com/docs/atlas/atlas-search/autocomplete/)
