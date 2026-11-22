# Phân biệt so khớp chuỗi, collation và tìm kiếm toàn văn trong MongoDB

## 1. Mục tiêu bài học

Một chức năng tìm kiếm trong ứng dụng thường bắt đầu bằng câu hỏi tưởng như đơn giản: “Người dùng nhập **cafe**, hệ thống phải trả những kết quả nào?”. Tùy mục tiêu, các kết quả hợp lệ có thể rất khác nhau:

- Chỉ lấy bản ghi có trường bằng chính xác `"cafe"`.
- Coi `"Cafe"`, `"CAFE"` và `"cafe"` là cùng một tên.
- Coi `"café"` và `"cafe"` là tương đương về dấu.
- Tìm sản phẩm có **tiền tố** `"caf"`.
- Tìm `"cafe"` xuất hiện **ở bất kỳ vị trí nào** trong mô tả.
- Tìm bài viết chứa một **từ**, một **cụm từ**, hoặc các từ liên quan về ngôn ngữ.
- Xếp hạng tài liệu dựa trên **độ liên quan**, hỗ trợ gõ sai, gợi ý khi nhập hoặc từ đồng nghĩa.

Trong MongoDB, các yêu cầu trên thuộc **những cơ chế khác nhau**, không thể giải quyết đầy đủ bằng một toán tử:

1. **So khớp chuỗi thông thường:** equality, range, prefix/substring qua `$regex` hoặc trường khóa đã chuẩn hóa.
2. **Collation:** quy tắc so sánh và sắp xếp chuỗi theo locale, phân biệt hoa/thường, dấu và các thuộc tính ngôn ngữ.
3. **Tìm kiếm toàn văn (full-text search):** phân tách văn bản thành token, tạo inverted/search index, tìm từ/cụm từ và xếp hạng relevance.

MongoDB có **`$text` + text index** ở Database Query Language và **MongoDB Search** với aggregation stage **`$search`**. Chúng không đồng nghĩa. MongoDB hiện khuyến nghị MongoDB Search cho những nhu cầu full-text search phong phú; khả năng triển khai phụ thuộc phiên bản và môi trường.

Sau bài học, bạn sẽ có khả năng chọn cơ chế phù hợp cho **mã sản phẩm, tên người, tên sản phẩm, tìm kiếm bài viết, autocomplete và tìm kiếm tiếng Việt**, hiểu chi phí index và giải thích kết quả sai phổ biến.

## 2. Tư duy cốt lõi: ba câu hỏi khác nhau

Giả sử collection lưu:

```javascript
{ sku: "CF-001", title: "Cà phê sữa", description: "Hương vị cà phê Việt Nam" }
```

Ba loại câu hỏi:

| Câu hỏi | Cơ chế thường phù hợp | Vì sao |
| --- | --- | --- |
| SKU có **bằng** `"CF-001"` không? | Equality + B-tree index | Dùng khóa xác định, cần độ chính xác |
| Tên `"cafe"` có tương đương `"Café"` khi **so sánh** không? | Collation hoặc normalized key | Cần quy tắc hoa/thường và dấu |
| Tài liệu nào nói về “cà phê”, đứng **liên quan nhất**? | Full-text search | Cần tokenization và relevance |
| Tên nào **bắt đầu** bằng `"Ca"`? | Regex prefix/index hoặc autocomplete index | Là truy vấn tiền tố, không phải equality |
| Mô tả nào **chứa chuỗi con** `"phe"`? | Regex substring / n-gram search | Cần substring, không phải token search |
| Gợi ý khi gõ `"ca ph"` | MongoDB Search autocomplete hoặc search service | Cần index tối ưu cho prefix/ngữ nghĩa |
| Sắp xếp tên theo tiếng Việt | `collation: { locale: "vi", ... }` | Cần thứ tự văn hóa/ngôn ngữ |

**Không nhầm lẫn:** một điều kiện `{ title: "cafe" }` không tìm các document *có nhắc tới từ cafe* trong câu dài. Nó là một phép **equality trên giá trị trường** theo collation được dùng.

## 3. Bảng so sánh tổng quan

| Thuộc tính | Equality/string range | `$regex` | Collation | Legacy `$text` | MongoDB Search `$search` |
| --- | --- | --- | --- | --- | --- |
| Đơn vị so khớp | Giá trị trường | Pattern ký tự | **Quy tắc** so sánh/sort | Token/từ được lập chỉ mục | Token, phrase, autocomplete, nhiều operators |
| So khớp toàn bộ field | Có | Nếu anchor đúng | Khi đi kèm equality | Không mặc định | Tùy operator/analyzer |
| Substring tùy vị trí | Không | Có | Không tự có | Không | Có thể cấu hình regex/wildcard/ngram |
| Phân biệt hoa/thường | Có với simple | Regex flags | `strength`, `caseLevel` | Tùy text index/query | Tùy analyzer/index |
| Phân biệt dấu | Có với simple | Theo pattern/normalization | `strength` và locale | Tùy text index/query | Tùy analyzer |
| Stemming/stop words | Không | Không | Không | Có với ngôn ngữ hỗ trợ | Tùy analyzer |
| Relevance score | Không | Không mặc định | Không | `textScore` | `searchScore` |
| Index chủ yếu | B-tree | B-tree cho prefix nhạy hoa/thường | B-tree **cùng collation** | Text index | MongoDB Search index |
| Autocomplete/gõ sai | Không | Rất hạn chế | Không | Không phải giải pháp phù hợp | Có operator/chính sách riêng |
| Điểm mạnh | Đúng khóa, hiệu năng ổn định | Pattern nhỏ, tiền tố | Equality/sort theo locale | Full-text cơ bản | Trải nghiệm tìm kiếm phong phú |
| Lỗi điển hình | Tưởng bằng nghĩa là chứa | Scan, regex injection | Tưởng collation tự tìm từ | Tưởng `$text` là substring | Chưa tạo Search index/analyzer |

**Collation không phải một search engine.** Nó là bộ quy tắc so sánh áp dụng cho những operation như equality, range, sort và uniqueness. Full-text search sử dụng **index và thuật toán tìm kiếm** riêng.

## 4. Lab A: so khớp chuỗi và collation

Các lệnh tiếp theo dành cho **mongosh** trên database thực hành. Không sử dụng `drop()` trên production.

```javascript
const lab = db.getSiblingDB("string_search_lab");

lab.names.drop();

lab.names.insertMany([
  { _id: 1, name: "cafe",        code: "item2",  group: "drink" },
  { _id: 2, name: "Café",        code: "item10", group: "drink" },
  { _id: 3, name: "CAFE",        code: "item1",  group: "drink" },
  { _id: 4, name: "café",        code: "item12", group: "drink" },
  { _id: 5, name: "café mocha",  code: "item3",  group: "drink" },
  { _id: 6, name: "Cà phê sữa",  code: "item4",  group: "drink" },
  { _id: 7, name: "cà Phê Sữa",  code: "item5",  group: "drink" },
  { _id: 8, name: "Ca phe sua",  code: "item6",  group: "drink" },
  { _id: 9, name: "trà xanh",    code: "item7",  group: "drink" }
]);

lab.names.createIndex(
  { name: 1 },
  { name: "ix_name_simple" }
);

lab.names.createIndex(
  { code: 1 },
  { name: "ix_code_simple" }
);
```

**Lưu ý:** collection này được tạo với collation mặc định `simple` (so sánh nhị phân), do không có `collation` ở lúc tạo collection. Dùng cùng một fixture cho các truy vấn, tránh lẫn kết quả do dữ liệu thay đổi.

## 5. Equality trên chuỗi: giá trị trường, không phải từ khóa

Truy vấn:

```javascript
lab.names.find(
  { name: "cafe" },
  { _id: 1, name: 1 }
).toArray();
```

Với collation `simple`, chỉ trả document:

```javascript
{ _id: 1, name: "cafe" }
```

Không khớp `"CAFE"`, `"Café"` hoặc `"café mocha"`.

### 5.1. Chuỗi khác nhau ở ký tự Unicode cũng khác nhau

Về mặt representation, `"é"` có thể được biểu diễn dưới dạng:

- Một code point dựng sẵn: U+00E9.
- Hai code points: `e` U+0065 và combining acute U+0301.

Hai cách hiển thị có thể trông giống nhau nhưng **không giống byte/code-point sequence**. Với `simple`, việc so sánh dựa trên giá trị mã ký tự, không tự coi mọi Unicode normalization forms là tương đương.

Khi cần business key chính xác, nên có chính sách chuẩn hóa ở application (ví dụ NFC, lowercase theo locale/quy tắc đã chọn) và lưu trường normalized key riêng. Không tự giả định mọi phép lowercasing đều đơn giản cho mọi ngôn ngữ.

### 5.2. Equality, `$in` và range

```javascript
// Giá trị chính xác trong tập lựa chọn.
lab.names.find({
  name: { $in: ["cafe", "CAFE"] }
});

// Tìm khoảng từ điển theo collation hiện tại.
lab.names.find({
  name: { $gte: "C", $lt: "D" }
});
```

Các toán tử này không tự “hiểu nghĩa”, không stem từ, không tìm substring. Collation có thể thay đổi cách so sánh chuỗi trong equality và range.

### 5.3. B-tree index cho equality

Index `{ name: 1 }` phù hợp với equality trên `name` theo **cùng collation**. Với `simple` và điều kiện trên, query có thể dùng index để tránh scan toàn collection. Trên fixture nhỏ, optimizer có thể chọn plan khác vì collection rất ít document; không suy từ lab rằng server bắt buộc chọn `IXSCAN`.

Quan sát:

```javascript
lab.names.find({ name: "cafe" })
  .explain("executionStats");
```

Đọc `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned` và đường đi index trong output phiên bản đang dùng.

## 6. `$regex`: pattern ký tự, không phải full-text search

MongoDB cho phép regular-expression predicate:

```javascript
// Tên bắt đầu bằng "caf" (case-sensitive).
lab.names.find({ name: /^caf/ });

// Tên có chuỗi "cafe" ở bất kỳ vị trí nào.
lab.names.find({ name: /cafe/ });

// Bỏ qua khác biệt chữ hoa/thường.
lab.names.find({ name: /^cafe/i });

// Toàn bộ string phải là "cafe", không chấp nhận hậu tố.
lab.names.find({ name: /^cafe$/i });
```

Với lab:

- `/^caf/` khớp `cafe`, `café`, `café mocha` vì ba giá trị đều bắt đầu bằng `caf` viết thường; nó không khớp `Café` hoặc `CAFE` viết hoa.
- `/^cafe/i` khớp `cafe`/`CAFE`, nhưng **không tự bỏ dấu để khớp `"café"`**; `e` và `é` là ký tự khác nhau.
- `/^cafe$/i` yêu cầu toàn bộ giá trị là `cafe` hoặc dạng khác về hoa/thường của cùng các chữ không dấu, không trả `"café mocha"`.
- Pattern `/cafe/` không tự tách từ hay xếp hạng relevance.

### 6.1. Prefix regex có thể tận dụng index

MongoDB có tối ưu cho **case-sensitive prefix expression** bắt đầu bằng `^` hoặc `\A`, theo sau bởi ký tự xác định:

```javascript
lab.names.find({ name: /^caf/ })
  .explain("executionStats");
```

Với index phù hợp, MongoDB có thể suy ra range của prefix và hạn chế phần index cần quét.

So sánh:

```javascript
lab.names.find({ name: /^caf/ });  // Prefix.
lab.names.find({ name: /caf/ });   // Substring ở bất kỳ đâu.
lab.names.find({ name: /caf/i });  // Case-insensitive substring.
```

Hai truy vấn sau thường khó tận dụng B-tree hiệu quả hơn; chúng có thể phải xét nhiều key/document.

**Không phải mọi regex đều nhanh vì field có index.** Hình dạng pattern và flags rất quan trọng.

### 6.2. Regex case-insensitive không dùng được lợi thế của collation index

Một lỗi thiết kế phổ biến:

```javascript
lab.names.createIndex(
  { name: 1 },
  {
    name: "ix_name_casefold",
    collation: { locale: "en", strength: 2 }
  }
);

// Đừng kỳ vọng index collation này làm regex /i nhanh.
lab.names.find({ name: /^cafe/i })
  .collation({ locale: "en", strength: 2 });
```

`$regex` **không collation-aware**. MongoDB documentation nêu rõ case-insensitive indexes dựa trên collation **không làm `$regex` nhanh hơn**. Dùng equality + matching collation cho so khớp tên không phân biệt hoa/thường; dùng index chuyên cho autocomplete/search nếu nhu cầu thật là gõ tiền tố.

### 6.3. Regex do người dùng nhập cần kiểm soát

Không nên nối trực tiếp input người dùng vào regex như một biểu thức tùy ý:

```javascript
// Không khuyến nghị nếu input không được kiểm tra:
const userPattern = request.query.q;
const query = { name: { $regex: userPattern } };
```

Rủi ro:

- Ký tự `.`, `^`, `$`, `(`, `)` thay đổi ý nghĩa.
- Những pattern phức tạp có thể tốn CPU (ReDoS).
- Regex không anchor có thể gây scan rộng.
- Unicode case folding và word boundaries có thể khác dự đoán.
- Query tự do như search engine có thể trả kết quả không liên quan.

Nên xác định API “prefix”, “contains” hay “regex thật” rõ ràng; nếu regex được tạo từ literal input, **escape metacharacters**, giới hạn độ dài và dùng timeout/resource budgets. Với tìm kiếm quy mô lớn, cân nhắc Search index.

## 7. Collation là gì?

**Collation** xác định các quy tắc MongoDB so sánh và sắp xếp **chuỗi**. MongoDB dùng thư viện ICU để hỗ trợ nhiều locale, trong đó có `vi` (tiếng Việt), `en`, `fr` và nhiều ngôn ngữ khác.

Một collation document thường gồm:

```javascript
{
  locale: "vi",
  strength: 2
}
```

`locale` xác định ngôn ngữ/quy tắc so sánh. `strength` xác định mức độ phân biệt giữa ký tự, dấu và hoa/thường. Collation có thể được đặt:

- Mặc định cho **collection** khi tạo.
- Trên **index**.
- Trên từng **query/sort/aggregate** phù hợp.
- Trên một số operation về so sánh/unique constraints.

Collation **không đổi dữ liệu string đã lưu**. Nó đổi việc MongoDB xem hai giá trị “bằng nhau” hoặc thứ tự sort ra sao.

## 8. `locale`, `strength` và phân biệt chữ hoa/dấu

Bảng mức quan trọng:

| Cấu hình | Ý nghĩa chính | Case-sensitive? | Diacritic-sensitive? |
| --- | --- | --- | --- |
| `{ locale: "simple" }` | Binary/code-point comparison | Có | Có |
| `{ locale: "fr", strength: 1 }` | Chỉ base characters (primary level) | Thường **không** | Thường **không** |
| `{ locale: "fr", strength: 2 }` | Base + diacritic differences | **Không** nếu `caseLevel:false` | **Có** |
| `{ locale: "fr", strength: 3 }` | Base + diacritics + case/variants | **Có** | **Có** |
| `strength: 1` + `caseLevel:true` | Thêm so sánh case ở primary strength | **Có** | Không theo secondary strength |

Các mức phụ thuộc quy tắc ICU của locale; không nên suy rằng mọi biến thể chữ cái ở mọi ngôn ngữ đều có cùng base relationship. `strength:3` là mặc định khi dùng locale không phải `simple`; `caseLevel:false` là mặc định.

### 8.1. Thử với dữ liệu `"cafe"`/`"café"`

```javascript
// Bỏ qua hoa/thường và dấu theo French primary strength.
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 1 })
  .toArray();
```

Theo chính sách so sánh này, các dạng tương đương của **cùng từ** như `"cafe"`, `"CAFE"`, `"café"`, `"Café"` có thể khớp. Nhưng `"café mocha"` **không trở thành `"cafe"`**, vì collation không phải substring matching.

```javascript
// Không phân biệt case nhưng vẫn phân biệt dấu.
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 2 })
  .toArray();
```

Lần này `"cafe"` và `"CAFE"` được coi tương đương về case; `"café"` có dấu vẫn được phân biệt. Với `strength: 3`, `"cafe"` và `"CAFE"` cũng khác nhau.

### 8.2. Ví dụ tiếng Việt

```javascript
lab.names.find({ name: "Cà phê sữa" })
  .collation({ locale: "vi", strength: 2 })
  .toArray();
```

Mức 2 thường không phân biệt hoa/thường, nhưng vẫn giữ secondary diacritic differences. Vì vậy có thể so sánh những biến thể như `"Cà phê sữa"` và `"cà Phê Sữa"` theo quy tắc locale tiếng Việt.

Muốn tìm cả `"Ca phe sua"` không dấu, cần đánh giá collation `strength:1` hoặc **normalized search field**. Trong tiếng Việt, những chữ như `đ` có thể có quan hệ base khác chữ `d` theo ICU, nên “bỏ dấu” bằng locale collation **không phải phép transliteration toàn diện**. Đừng tự khẳng định mọi cách viết không dấu đều khớp mà chưa thử trên dữ liệu thực tế.

### 8.3. `caseLevel` và `caseFirst`

```javascript
{
  locale: "en",
  strength: 1,
  caseLevel: true
}
```

Dù strength 1 bỏ secondary diacritic comparison, `caseLevel:true` bổ sung phân biệt case. `caseFirst:"upper"` hoặc `"lower"` có thể ảnh hưởng thứ tự case khi mức so sánh xét case.

Cần định nghĩa rõ business requirement: **không phân biệt dấu và hoa/thường** khác **không phân biệt dấu nhưng phân biệt hoa/thường**.

## 9. Collation thay đổi sort, không tạo relevance ranking

So sánh sort mặc định:

```javascript
lab.names.find(
  {},
  { _id: 0, name: 1 }
).sort({ name: 1 });
```

với sort theo tiếng Việt:

```javascript
lab.names.find(
  {},
  { _id: 0, name: 1 }
)
.sort({ name: 1 })
.collation({ locale: "vi", strength: 3 });
```

Hai thứ tự có thể khác nhau vì `simple` sắp theo binary values còn locale `vi` theo ICU rules.

**Đừng nhầm sort alphabetic với relevance.** Nếu user search `"mongodb"`, sort `title` theo locale chỉ sắp tên theo bảng chữ cái; nó không biết bài nào phù hợp hơn truy vấn.

### 9.1. `numericOrdering`

Một bài toán quen thuộc:

```javascript
lab.names.find(
  {},
  { _id: 0, code: 1 }
)
.sort({ code: 1 })
.collation({ locale: "en", numericOrdering: true });
```

Với chuỗi kiểu `item2` và `item10`, `numericOrdering:true` giúp so sánh **đoạn số dương** theo giá trị số thay vì từng ký tự (`item2` trước `item10`). Nó không phải parser số đầy đủ: số âm, dấu thập phân và chuỗi có ký tự phân cách có giới hạn riêng. Không thay thế việc lưu các giá trị numeric bằng BSON numeric type khi thật sự là số.

### 9.2. `alternate`, `normalization`, `backwards`

Collation còn có tùy chọn nâng cao:

- `alternate:"shifted"`: có thể làm một số ký tự khoảng trắng/dấu câu ít quan trọng ở một số mức.
- `maxVariable`: loại ký tự variable được áp dụng cùng `alternate`.
- `normalization:true`: kiểm tra/cân nhắc những chuỗi có Unicode normalization khác nhau.
- `backwards:true`: cách đánh giá dấu ở một số locale (ví dụ một số quy tắc tiếng Pháp).

Đây là các tham số ICU, không phải tùy chọn “tự động hiểu nghĩa câu”. Chỉ dùng khi requirement đủ rõ và đã kiểm chứng tương thích các client/locale.

## 10. Collation index và query phải đồng bộ

**Quy tắc trọng yếu:** Muốn index hỗ trợ **string comparison** theo collation, query phải dùng **cùng collation** với index, hoặc thừa hưởng default collation tương ứng của collection.

Tạo index phù hợp với French primary strength:

```javascript
lab.names.createIndex(
  { name: 1 },
  {
    name: "ix_name_fr_strength1",
    collation: { locale: "fr", strength: 1 }
  }
);
```

Query dùng cùng collation:

```javascript
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 1 })
  .explain("executionStats");
```

Index này có cơ hội phục vụ equality theo cùng quy tắc collation.

Query dùng collation khác:

```javascript
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 2 })
  .explain("executionStats");
```

Dù chỉ khác `strength`, không nên kỳ vọng index `ix_name_fr_strength1` hỗ trợ việc so sánh string như collation thứ hai. MongoDB có thể dùng index khác hoặc chọn plan không dùng index đó cho string comparison.

### 10.1. Collection default collation

Khi tạo collection:

```javascript
lab.namesWithDefault.drop();

lab.createCollection(
  "namesWithDefault",
  {
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);

lab.namesWithDefault.insertMany([
  { _id: 1, name: "Cà phê sữa" },
  { _id: 2, name: "cà Phê Sữa" }
]);

// Index kế thừa default collation.
lab.namesWithDefault.createIndex({ name: 1 });
```

`find()` và `sort()` trên collection này mặc định thừa hưởng `vi/strength:2` khi không override. Tạo index cũng thừa hưởng default collation nếu không ghi rõ.

Muốn truy vấn binary:

```javascript
lab.namesWithDefault.find({
  name: "Cà phê sữa"
}).collation({ locale: "simple" });
```

Index có collation mặc định `vi/strength:2` không phải index dùng cho binary string comparison trên cùng field. Nếu cần cả hai, có thể tạo một **index riêng với `locale:"simple"`**, đặt tên khác.

### 10.2. Collation-aware index có chi phí

Collation indexes có thể lưu **ICU collation keys** lớn hơn binary keys, làm tăng:

- Dung lượng index.
- Chi phí write và cache.
- Thời gian index build.
- Số index phải giữ nếu app hỗ trợ nhiều kiểu so sánh.

Đừng tạo một index cho mọi locale nếu sản phẩm không cần; đánh giá query patterns và explain trước.

## 11. Unique index với collation: ảnh hưởng tới dữ liệu hợp lệ

Một username cần không phân biệt case nên có thể dùng unique index theo collation.

```javascript
lab.accounts.drop();

lab.accounts.createIndex(
  { username: 1 },
  {
    unique: true,
    name: "uq_username_case_insensitive",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);

lab.accounts.insertOne({
  username: "Alice"
});
```

Thử:

```javascript
// Dự kiến E11000 vì "alice" tương đương "Alice"
// theo collation strength 2.
lab.accounts.insertOne({
  username: "alice"
});
```

Unique constraint chịu tác động của collation index. Điều này rất hữu ích cho username, nhưng có thể nguy hiểm nếu business key cố tình phân biệt hoa/thường.

### 11.1. Nếu dùng strength 1

Với French collation strength 1, `"cafe"` và `"café"` có thể được coi là trùng theo unique index. Nếu business coi hai thương hiệu có dấu và không dấu là khác, strength 1 không phù hợp.

### 11.2. Migration cần kiểm tra duplicates trước

Nếu collection đã có `"Alice"` và `"alice"`, tạo unique collation index ngay có thể thất bại bởi `E11000`. Cần:

1. Xác định semantic key.
2. Phát hiện các nhóm collision theo collation mục tiêu.
3. Giải quyết hoặc hợp nhất bản ghi trùng theo quy trình nghiệp vụ.
4. Tạo unique index sau khi dữ liệu hợp lệ.
5. Xử lý race condition và lỗi `E11000` trong API.

**Đừng** xóa những documents trùng bằng script không có business approval; hai bản có thể được liên kết tới tài khoản, lịch sử hoặc quyền khác nhau.

## 12. Collation không phải full-text search

Ví dụ:

```javascript
// So sánh toàn bộ trường name với "cafe".
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 1 });
```

Query trên sẽ không tự tìm `"café mocha"` chỉ vì `"café"` là một phần của chuỗi. Collation **không phân tách từ** và **không xếp hạng kết quả** theo tần suất hoặc trọng số.

Tương tự:

```javascript
lab.names.find({ name: "phê" })
  .collation({ locale: "vi", strength: 1 });
```

không có nghĩa tìm mọi tên chứa từ `phê`. Nếu yêu cầu là “tên có chứa một từ trong câu”, cần `$regex` phù hợp, `$text` hoặc Search index.

## 13. Full-text search với `$text` và text index

MongoDB hỗ trợ toán tử **`$text`** dựa trên **text index**. Nó:

- Tokenize chuỗi thành từ/ngữ tố theo quy tắc.
- Có thể áp dụng **stemming** (quy về gốc từ) và **stop words** theo ngôn ngữ hỗ trợ.
- Tìm document chứa token liên quan trong các trường đã index.
- Tạo **`textScore`** để xếp hạng tương đối.
- Cho phép tìm từ, cụm từ trong dấu nháy kép và loại trừ từ.

Đây là cơ chế khác B-tree equality/index collation.

**MongoDB khuyến nghị MongoDB Search cho tính năng full-text nâng cao.** Tuy vậy `$text` vẫn hữu ích để hiểu cơ chế built-in và một số ứng dụng nhỏ/cũ.

### 13.1. Legacy text index có giới hạn

- **Tối đa một text index trên một collection**; index duy nhất đó có thể chứa nhiều trường text.
- Text index **chỉ dùng simple binary collation**, dù cách `$text` tokenize/case-fold có thể insensitive.
- `$text` yêu cầu text index tương ứng.
- Text indexes không dùng để tăng tốc sort thông thường.
- Không dùng `hint()` ép text index cho query `$text`.
- Compound text indexes có ràng buộc về tiền tố equality và các special indexes.
- `$text` không mặc định sort theo score.
- Query `$text` và aggregation `$search` stage **không phải cùng cú pháp hoặc index**.

## 14. Lab B: `$text` trên bài viết tiếng Anh

Tạo collection riêng không dùng collation mặc định khác simple:

```javascript
lab.articles.drop();

lab.articles.insertMany([
  {
    _id: 1,
    title: "MongoDB indexing basics",
    body: "Indexing helps queries run faster",
    category: "database"
  },
  {
    _id: 2,
    title: "MongoDB index tuning",
    body: "Compound indexes help queries",
    category: "database"
  },
  {
    _id: 3,
    title: "Coffee brewing guide",
    body: "Fresh beans and water",
    category: "lifestyle"
  },
  {
    _id: 4,
    title: "Fast MongoDB backup",
    body: "Backup restores and replicas",
    category: "database"
  },
  {
    _id: 5,
    title: "Search indexing practices",
    body: "Search engines rank documents",
    category: "technology"
  }
]);

lab.articles.createIndex(
  { title: "text", body: "text" },
  {
    name: "txt_title_body",
    default_language: "english",
    weights: { title: 10, body: 2 }
  }
);
```

`weights` ảnh hưởng tới text relevance score: một từ xuất hiện trong `title` có trọng số cao hơn khi xuất hiện trong `body`, theo cấu hình ví dụ.

### 14.1. Tìm một từ

```javascript
lab.articles.find({
  $text: {
    $search: "mongodb"
  }
}).toArray();
```

`$text` tìm token phù hợp trong **các trường đã text index**, không đòi toàn bộ `title` phải bằng `"mongodb"`. Các document có từ MongoDB ở title/body là ứng viên.

### 14.2. Nhiều từ là OR theo mặc định

```javascript
lab.articles.find({
  $text: {
    $search: "mongodb indexing"
  }
}).toArray();
```

Legacy `$text` thường tokenize và thực hiện **logical OR** của các từ chưa bị coi là stop words/negative terms; nó không mặc định yêu cầu cả hai từ đều có mặt.

Nếu cần tất cả khái niệm hoặc logic boolean phức tạp, dùng predicates bổ sung đúng ngữ nghĩa hoặc MongoDB Search với `compound`/`matchCriteria`.

### 14.3. Tìm cụm từ

```javascript
lab.articles.find({
  $text: {
    $search: "\"mongodb indexing\""
  }
}).toArray();
```

Chuỗi JavaScript bên trong `$search` chứa dấu nháy kép **là một phần của cú pháp truy vấn text**, để yêu cầu một cụm từ. Khác hẳn equality:

```javascript
lab.articles.find({
  title: "MongoDB indexing"
});
```

Equality trên title chỉ khớp khi toàn bộ trường bằng giá trị tương ứng theo collation; phrase search yêu cầu cụm từ xuất hiện trong text fields được index.

### 14.4. Loại trừ token

```javascript
lab.articles.find({
  $text: {
    $search: "mongodb -backup"
  }
}).toArray();
```

Dấu `-` đứng trước token trong ngữ cảnh `$search` thể hiện loại trừ, không phải ký tự trừ của một biểu thức số. Vì parser `$text` coi một số dấu câu đặc biệt, nếu muốn tìm literal chứa dấu gạch nối trong SKU/code, không nên đưa thẳng vào `$text` rồi mong exact equality.

### 14.5. Stemming không phải substring

Text index tiếng Anh có stemming. Các từ liên quan như `index`, `indexes`, `indexing` có thể được quy về gốc phù hợp theo English stemmer. Nhưng từ `"blue"` **không** mặc định khớp với `"blueberry"` chỉ vì là prefix.

Khác với regex:

```javascript
// Prefix ký tự:
lab.articles.find({ title: /^Mongo/ });

// Từ đã lập chỉ mục:
lab.articles.find({
  $text: { $search: "mongo" }
});
```

`$text` không phải phép tìm prefix “bất kỳ chuỗi con”. Muốn gõ dở, cần autocomplete/ngram hoặc công cụ phù hợp.

## 15. Xếp hạng kết quả với `textScore`

MongoDB gắn score cho các kết quả `$text`. Không nên giả định kết quả tự sắp theo điểm.

```javascript
lab.articles.find(
  { $text: { $search: "mongodb indexing" } },
  {
    title: 1,
    category: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
}).toArray();
```

Lưu ý:

- Score là **độ liên quan theo text index**, không phải xác suất document đúng.
- Trọng số `title:10` và `body:2` có thể làm một kết quả có token trong title được xếp cao hơn.
- Không hardcode thứ tự/giá trị score giữa các phiên bản hoặc khi corpus thay đổi.
- Có thể thêm thứ tự phụ ổn định cho pagination nếu dùng sort phù hợp, nhưng không kỳ vọng score một mình là unique.

### 15.1. Dùng `$text` trong aggregation

```javascript
lab.articles.aggregate([
  {
    $match: {
      $text: { $search: "mongodb" }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "textScore" }
    }
  },
  { $sort: { score: -1, _id: 1 } }
]).toArray();
```

Ở đây `$match` chứa `$text` được đặt **làm stage đầu tiên** theo yêu cầu của `$text` trong aggregation. Đừng đặt `$project`/`$addFields` trước stage này và cho rằng planner vẫn chấp nhận.

### 15.2. `$caseSensitive`, `$diacriticSensitive`

Ví dụ:

```javascript
lab.articles.find({
  $text: {
    $search: "MongoDB",
    $caseSensitive: true
  }
});
```

Với text index version 3 thông thường, `$text` mặc định không phân biệt case và diacritics; `$caseSensitive:true` hoặc `$diacriticSensitive:true` thay đổi cách lọc và có thể làm truy vấn chậm hơn.

**Đây là options của `$text`**, không phải options của collation. Một text index chỉ hỗ trợ binary collation vẫn có thể thực hiện case/diacritic-insensitive token matching theo đặc tính của text index. Không đồng nhất hai ý nghĩa “binary index collation” và “cách text token matching xử lý case”.

## 16. Giới hạn ngôn ngữ: tiếng Việt là ví dụ quan trọng

**MongoDB collation** có locale `vi` cho quy tắc so sánh chuỗi. Nhưng **legacy `$text` text index không có Vietnamese stemming/stop-word language** trong danh sách ngôn ngữ text search được hỗ trợ của MongoDB Database Manual.

Hai danh sách ngôn ngữ là **khác nhau**:

- `collation({locale:"vi"})`: so sánh/sắp xếp string theo ICU locale tiếng Việt.
- `$text` với `default_language:"vietnamese"`: **không phải một lựa chọn ngôn ngữ được hỗ trợ của legacy text index**.

Các ngôn ngữ `$text` có stemming/stop words trong danh sách chính thức bao gồm English, French, German, Spanish, Russian, Turkish... nhưng **không có Vietnamese**.

### 16.1. Dùng `default_language:"none"` khi không muốn English stemming

Một lựa chọn cơ bản cho tài liệu đa ngôn ngữ:

```javascript
lab.viArticles.drop();

lab.viArticles.insertMany([
  {
    _id: 1,
    title: "Cà phê sữa Việt Nam",
    body: "Hướng dẫn pha cà phê sữa"
  },
  {
    _id: 2,
    title: "Trà xanh",
    body: "Uống trà và bảo quản lá trà"
  },
  {
    _id: 3,
    title: "Máy pha cà phê",
    body: "Thiết bị pha chế tại nhà"
  }
]);

lab.viArticles.createIndex(
  { title: "text", body: "text" },
  {
    name: "txt_vi_terms",
    default_language: "none"
  }
);
```

`none` khiến MongoDB không áp dụng stop-word removal và suffix stemming theo một ngôn ngữ cụ thể. Nó **không tạo ra tokenizer tiếng Việt có khả năng nhận diện mọi từ ghép/từ có dấu**.

```javascript
lab.viArticles.find({
  $text: {
    $search: "cà phê"
  }
}).toArray();
```

Đây vẫn là `$text` search theo token được parser xử lý, thông thường **OR**, không phải full Vietnamese semantic search. Với một phrase:

```javascript
lab.viArticles.find({
  $text: {
    $search: "\"cà phê\""
  }
}).toArray();
```

Cần kiểm thử tokenizer, dấu, normalization và dữ liệu đa ngôn ngữ thực tế. Tìm `"ca phe"` có thể khác tìm `"cà phê"` khi analyzer và dữ liệu được chuẩn hóa theo những quy tắc khác nhau.

### 16.2. Trường normalized text cho một số use case

Nếu yêu cầu là tìm **tên sản phẩm không dấu** theo nghiệp vụ, có thể lưu song song:

```javascript
{
  title: "Cà phê sữa",
  titleKey: "ca phe sua"
}
```

`titleKey` được chuẩn hóa **tại ingestion** bằng thuật toán có version và test rõ ràng. Với query exact:

```javascript
lab.products.find({
  titleKey: "ca phe sua"
});
```

Đây là mô hình equality trên khóa chuẩn hóa, **không phải full-text search**. Tìm substring/prefix vẫn cần index và query riêng. Không dùng phép bỏ dấu đơn giản cho toàn hệ thống nếu yêu cầu phân biệt những chữ cái mang ý nghĩa khác (ví dụ `d` và `đ`) mà không có chính sách rõ.

## 17. Compound text index và giới hạn quan trọng

Text index có thể ghép với các key thường trong một index compound, nhưng có các quy tắc riêng.

Ví dụ muốn tenant-specific text search:

```javascript
lab.tenantArticles.drop();

lab.tenantArticles.insertMany([
  { _id: 1, tenantId: "A", title: "MongoDB indexing", body: "Index basics" },
  { _id: 2, tenantId: "B", title: "MongoDB indexing", body: "Other tenant" }
]);

lab.tenantArticles.createIndex(
  { tenantId: 1, title: "text", body: "text" },
  {
    name: "txt_tenant_title_body",
    default_language: "english"
  }
);
```

Khi index có key thường **đứng trước** các text keys, query `$text` cần equality trên những prefix fields đó:

```javascript
lab.tenantArticles.find({
  tenantId: "A",
  $text: { $search: "mongodb indexing" }
});
```

Không giả định query chỉ có `$text` sử dụng index compound trên mà không đưa `tenantId` vào equality predicate.

Những quy tắc khác:

- Mỗi collection tối đa **một text index** dù nó index nhiều trường text.
- Trong compound index, các text keys cần được liệt kê **liền kề** theo quy tắc.
- Compound text index không thể kết hợp tùy ý các special index types khác.
- Text index không tối ưu sort; muốn sort theo date hoặc relevance phải đánh giá plan/score riêng.
- Với collection có **non-simple default collation**, khi tạo text index phải **explicitly** chỉ định `{ collation: { locale:"simple" } }`.

### 17.1. Text index trên collection có default collation

```javascript
lab.localizedArticles.drop();

lab.createCollection(
  "localizedArticles",
  {
    collation: {
      locale: "fr",
      strength: 1
    }
  }
);

// Text index bắt buộc đơn giản về collation.
lab.localizedArticles.createIndex(
  { title: "text", body: "text" },
  {
    name: "txt_localized_simple",
    collation: { locale: "simple" },
    default_language: "english"
  }
);
```

Collation của text index phải là **simple**, không có nghĩa query `$text` không bao giờ có cách so khớp không phân biệt case/diacritic. Hai cơ chế độc lập ở những tầng khác nhau.

## 18. MongoDB Search với `$search`: lựa chọn nâng cao

MongoDB Search xây dựng search index riêng (dựa trên công nghệ search phù hợp), sử dụng **analyzers** để tokenize/normalize và cung cấp nhiều toán tử:

- `text`: tìm từ đã phân tích.
- `phrase`: tìm cụm từ theo vị trí/khoảng cách được cấu hình.
- `autocomplete`: gợi ý khi nhập.
- `regex`/`wildcard`: mẫu tìm kiếm có điều kiện.
- `compound`: kết hợp must/should/filter/mustNot.
- `fuzzy`: chịu một số lỗi chính tả.
- Synonyms, highlighting, facets và scoring tùy cấu hình.

**Cập nhật về môi trường hỗ trợ:** MongoDB Search không còn chỉ là tính năng trên Atlas. Theo tài liệu MongoDB hiện hành, `$search` hỗ trợ Atlas và các môi trường self-managed **MongoDB Community 8.2+** hoặc **Enterprise 8.2+ với Kubernetes Operator** theo các điều kiện cài đặt/triển khai được tài liệu nêu. Các deployment cũ hoặc chưa cấu hình Search service/index không thể chỉ copy một `$search` pipeline rồi chạy.

### 18.1. `$text.$search` và aggregation `$search` khác nhau

**Legacy:**

```javascript
lab.articles.find({
  $text: {
    $search: "mongodb"
  }
});
```

**MongoDB Search:**

```javascript
lab.articles.aggregate([
  {
    $search: {
      index: "title_body_search",
      text: {
        query: "mongodb",
        path: ["title", "body"]
      }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

Đây là hai hệ thống có **index khác nhau**, **cú pháp khác nhau**, **score khác nhau**. Không gộp `textScore` của `$text` với `searchScore` của `$search`.

### 18.2. Tạo MongoDB Search index (khi deployment hỗ trợ)

Trên môi trường có MongoDB Search đã bật, có thể cấu hình search index thông qua UI/API hoặc phương thức shell hỗ trợ. Ví dụ minh họa index title/body:

```javascript
lab.articles.createSearchIndex({
  name: "title_body_search",
  definition: {
    mappings: {
      dynamic: false,
      fields: {
        title: { type: "string" },
        body: { type: "string" }
      }
    }
  }
});
```

Index build là bất đồng bộ; cần kiểm tra trạng thái index đã **READY/queryable** trước khi thử `$search`. API/mô hình quản trị search index có thể khác giữa dịch vụ/version. Nếu môi trường chỉ có legacy text index nhưng không có MongoDB Search, đoạn code trên không tạo được tìm kiếm `$search` hoạt động.

### 18.3. `text` và fuzzy matching

```javascript
lab.articles.aggregate([
  {
    $search: {
      index: "title_body_search",
      text: {
        query: "mongdb",
        path: ["title", "body"],
        fuzzy: {
          maxEdits: 1,
          prefixLength: 2
        }
      }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
]);
```

Đây là ví dụ yêu cầu Search index phù hợp. `fuzzy` không phải phép so sánh mọi chuỗi gần nhau tự động: thuật toán dựa trên edit distance và analyzer; tùy độ dài token, prefixLength và cấu hình, một lỗi có thể chưa khớp. Đừng hứa kết quả cụ thể khi chưa kiểm chứng trên index/corpus thực.

### 18.4. `phrase` và autocomplete

Tìm cụm:

```javascript
lab.articles.aggregate([
  {
    $search: {
      index: "title_body_search",
      phrase: {
        query: "mongodb indexing",
        path: "title",
        slop: 0
      }
    }
  },
  { $project: { title: 1 } }
]);
```

Để gợi ý khi gõ `"mong"` hoặc `"caf"`, nên tạo **Search index có field mapping `autocomplete`** và sử dụng operator `autocomplete`. Một field index kiểu `string` như ví dụ trên **không tự tạo autocomplete mapping**.

```javascript
// Chỉ chạy khi đã tạo Search index có autocomplete mapping
// cho field title.
lab.articles.aggregate([
  {
    $search: {
      index: "title_autocomplete",
      autocomplete: {
        query: "mong",
        path: "title"
      }
    }
  },
  {
    $project: {
      title: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

**Search index** là một phần phải thiết kế riêng. Có thể cần search analyzer, index analyzer, edge grams, min/max grams và resource capacity; không nên mặc định cấu hình dynamic mapping giải quyết gõ sai hoặc tiền tố tốt.

### 18.5. Search indexing có tính bất đồng bộ

Search indexes có pipeline cập nhật riêng. Sau insert/update trên primary, `$search` có thể chưa nhìn thấy thay đổi ngay lập tức; cần xét **search index freshness** và tính nhất quán khi ứng dụng yêu cầu đọc ngay write mới.

Với định danh SKU hoặc quyền truy cập vừa cập nhật, API kiểm tra tính đúng đắn nên dùng **database equality/atomic operations** phù hợp; không lấy search index làm nguồn quyền quyết định chỉ vì kết quả có score.

## 19. Thiết kế theo tiếng Việt: collation vi và Search analyzer không đồng nghĩa

Một số use cases:

| Nhu cầu tiếng Việt | Gợi ý |
| --- | --- |
| Sort danh sách tên tiếng Việt | Collation `locale:"vi"` với strength phù hợp |
| Đối chiếu tên không phân biệt hoa/thường | Equality + collation `vi`, strength 2 và index cùng collation |
| Đối chiếu tên không dấu | Cân nhắc `strength:1` và kiểm tra ICU behavior; normalized key nếu cần chính sách bỏ dấu riêng |
| Tìm trong mô tả nhiều câu | MongoDB Search với analyzer được kiểm nghiệm |
| Tìm cụm “cà phê sữa” | Search `phrase` với analyzer hợp lý hoặc legacy `$text` hạn chế |
| Gợi ý “ca ph” | Search autocomplete và chính sách normalized tokens |
| Tìm đúng mã `CF-001` | Equality/B-tree index hoặc normalized SKU key |
| Xếp hạng kết quả | Search relevance scoring |
| Query ít dữ liệu, literal prefix | Prefix `$regex` case-sensitive nếu đủ nhanh |

### 19.1. Tokenization của tiếng Việt

Tiếng Việt dùng dấu cách giữa nhiều **âm tiết**, không phải luôn tương ứng một từ nghĩa. Ví dụ `"cà phê sữa"` thường được diễn đạt thành những token/thuật ngữ khác nhau tùy analyzer. Một analyzer chung cho Latin text không có nghĩa tự nhận diện mọi từ ghép tiếng Việt.

Cần kiểm thử trên một bộ dữ liệu thực:

- Có dấu/không dấu.
- Chữ hoa/chữ thường.
- Các cặp `d` và `đ`.
- Dạng Unicode NFC/NFD.
- Từ ghép nhiều âm tiết.
- Dấu câu, emoji, số và ký hiệu SKU.
- Viết tắt, tên riêng, lỗi gõ phổ biến.
- Mixed English/Vietnamese.
- Synonyms do domain đặt.
- Tên thương hiệu phải exact.

**Đừng** chỉ chạy một search `"ca phe"` thấy vài kết quả rồi kết luận analyzer đã đủ tốt cho toàn hệ thống.

### 19.2. Một schema phục vụ nhiều mục đích

```javascript
{
  _id: ObjectId("..."),
  sku: "CF-001",
  title: "Cà phê sữa",
  titleKey: "ca phe sua",
  description: "Cà phê pha cùng sữa đặc",
  categoryId: "beverages",
  locale: "vi",
  isActive: true
}
```

Có thể thiết kế:

- Unique index trên `sku` để xác định sản phẩm.
- B-tree index trên `titleKey` cho exact/prefix match theo quy ước normalized input.
- Collation-aware index trên `title` phục vụ sort/display comparisons.
- Search index trên `title`/`description` phục vụ full-text relevance.
- Index theo `categoryId`, `isActive` để lọc, hoặc Search filter mapping khi phù hợp.

Đây là những nhiệm vụ khác nhau, không cần ép một field/index làm tất cả.

## 20. Khi nào dùng `$regex`, khi nào dùng Search?

### 20.1. Bài toán prefix ngắn và chính xác

Ví dụ tìm mã đầu `"CF-"`:

```javascript
db.products.find({
  sku: /^CF-/
}).limit(20);
```

Index `{sku:1}` có thể hỗ trợ prefix case-sensitive. Nếu cần case-insensitive SKU, thường tốt hơn khi **chuẩn hóa SKU khi ghi** và query trên `skuKey`, thay vì mỗi lần dùng `/i` trên tập lớn.

### 20.2. Substring trong đoạn dài

Ví dụ mô tả có chữ `"phê"` ở bất kỳ đâu:

```javascript
db.products.find({
  description: /phê/
});
```

Về chức năng có thể phù hợp, nhưng chi phí có thể cao vì không có prefix tối ưu. Với khối lượng lớn và UX search, cân nhắc Search index với analyzer/ngram thích hợp.

### 20.3. Search có relevance, fuzzy, synonyms và autocomplete

Nếu yêu cầu:

- Tìm gần đúng `"mongdb"` → `"mongodb"`.
- Gợi ý khi gõ dở.
- Ưu tiên match trong title hơn body.
- Phân tích nhiều ngôn ngữ.
- Tìm theo phrase và ranking.
- Highlight đoạn văn kết quả.

MongoDB Search là lựa chọn cần đánh giá. Nó có chi phí index/storage/search process, indexing latency và cần test relevance, không phải miễn phí so với regex.

## 21. Collation và `$regex` trong aggregation

Collation áp dụng cho nhiều string comparisons trong aggregation phù hợp:

```javascript
lab.names.aggregate(
  [
    { $match: { name: "cafe" } },
    { $sort: { name: 1 } }
  ],
  {
    collation: {
      locale: "fr",
      strength: 1
    }
  }
);
```

Nhưng nếu trong `$match` dùng `$regex`:

```javascript
lab.names.aggregate(
  [
    { $match: { name: { $regex: "^cafe", $options: "i" } } }
  ],
  {
    collation: {
      locale: "fr",
      strength: 1
    }
  }
);
```

thì regex vẫn không collation-aware, không có chuyện `"café"` tự trở thành `"cafe"` chỉ nhờ aggregation collation.

### 21.1. `$toLower` không thay collation một cách tổng quát

MongoDB có string expressions như `$toLower`, nhưng hỗ trợ Unicode/locale và semantics không tương đương ICU collation hoàn chỉnh. Đặc biệt, thao tác lower toàn dữ liệu trong query có thể làm giảm khả năng dùng B-tree index theo field gốc.

Nếu ứng dụng cần search key đã chuẩn hóa, nên chuẩn hóa nhất quán **khi ghi** và lưu key riêng thay vì tính lại trên hàng triệu document cho mỗi request.

## 22. API Node.js minh họa từng mục đích

Ví dụ dùng MongoDB Node.js Driver, giả định đã có collection `products`/indexes thích hợp:

```javascript
const { MongoClient } = require("mongodb");

async function examples() {
  const client = new MongoClient(process.env.MONGODB_URI);

  try {
    await client.connect();
    const products = client.db("app").collection("products");

    // 1. SKU identity: strict equality.
    const bySku = await products.findOne({
      sku: "CF-001"
    });

    // 2. Tên tương đương không phân biệt case theo locale.
    const byName = await products.find({
      title: "Cà phê sữa"
    }, {
      collation: { locale: "vi", strength: 2 }
    }).toArray();

    // 3. Prefix trên khóa đã chuẩn hóa.
    const prefix = await products.find({
      titleKey: /^ca phe/
    }).limit(20).toArray();

    console.log({
      foundSku: !!bySku,
      nameMatches: byName.length,
      prefixMatches: prefix.length
    });
  } finally {
    await client.close();
  }
}

examples().catch(err => {
  console.error(err);
  process.exitCode = 1;
});
```

Ở đây có ba cách tìm, phục vụ ba contract khác nhau. `titleKey` cần được tạo ổn định khi ghi; nếu index `titleKey` có collation không phù hợp hoặc input không chuẩn hóa, kết quả và hiệu năng sẽ khác.

### 22.1. Legacy `$text` với Node.js

```javascript
const articles = client.db("app").collection("articles");

const results = await articles.find(
  {
    $text: {
      $search: "mongodb indexing"
    }
  },
  {
    projection: {
      title: 1,
      score: { $meta: "textScore" }
    },
    sort: {
      score: { $meta: "textScore" }
    },
    limit: 20
  }
).toArray();
```

Code này đòi **text index** đã tạo. Không tự động tạo index ở từng request. Với Search nâng cao, dùng `aggregate([{$search:...}, ...])` trên deployment có MongoDB Search index.

## 23. Java Sync Driver: collation trên query

Java Driver có các class `Collation`, `CollationStrength` và `FindIterable` để cấu hình:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.FindIterable;
import com.mongodb.client.model.Collation;
import com.mongodb.client.model.CollationStrength;
import org.bson.Document;

public class StringMatchExample {
    public static void main(String[] args) {
        try (MongoClient client = MongoClients.create(
                System.getenv("MONGODB_URI"))) {

            MongoDatabase database = client.getDatabase("app");
            MongoCollection<Document> products =
                database.getCollection("products");

            // So khớp tên theo locale vi,
            // không phân biệt case nhưng có xét diacritic differences.
            Collation vietnamese = Collation.builder()
                .locale("vi")
                .collationStrength(CollationStrength.SECONDARY)
                .build();

            FindIterable<Document> matches = products.find(
                new Document("title", "Cà phê sữa")
            ).collation(vietnamese);

            for (Document product : matches) {
                System.out.println(product.toJson());
            }
        }
    }
}
```

Điểm quan trọng:

- Driver truyền collation đến database operation.
- Index dùng để tăng tốc string comparison cần có collation tương ứng.
- Collation không chuyển truy vấn equality thành full-text search.
- API class/import có thể được điều chỉnh theo phiên bản driver; ví dụ dùng Java Sync Driver với cấu trúc API phổ biến.

## 24. Chọn cơ chế cho các use cases thực tế

| Use case | Chọn trước | Vì sao | Cảnh giác |
| --- | --- | --- | --- |
| Lookup SKU, invoice ID, token ID | Equality + unique B-tree index | Phải chính xác một giá trị | Không dùng case-insensitive nếu ID phân biệt case |
| Username không phân biệt case | Unique collation index hoặc usernameKey | Chặn collision | Migration dữ liệu và Unicode policy |
| Danh sách tên sắp theo tiếng Việt | Collation `vi` + matching index | Sắp xếp theo locale | Không xếp theo relevance |
| Filter email giống nhau không phân biệt case | Normalized email key hoặc collation | Equality | Email normalization có policy riêng |
| Prefix mã sản phẩm | Anchored regex trên normalized code | Có thể dùng B-tree | Regex `/i` không hưởng lợi collation index |
| Substring mô tả nhỏ | Regex có kiểm soát | Dễ triển khai | Có thể scan rộng |
| Tìm bài viết tiếng Anh theo từ | `$text` hoặc MongoDB Search | Token/stemming | `$text` chỉ một text index/coll |
| Gợi ý khi gõ, typo tolerance | MongoDB Search autocomplete/fuzzy | Search index riêng | Chi phí index và cấu hình |
| Tìm nội dung tiếng Việt dài | MongoDB Search và analyzer đã test | Relevance và tùy chỉnh | Word segmentation/Unicode |
| Truy vấn tên thương hiệu phải exact | Equality + normalized/locale index | Tránh false positives | Bỏ dấu quá mạnh có thể gộp nhầm |
| Kết quả có score | `$text` textScore hoặc Search searchScore | Sắp độ liên quan | Score không có ý nghĩa tuyệt đối |
| Search sau write vừa tạo | Equality read theo consistency phù hợp | Không phụ thuộc search-index lag | Search indexing có thể async |

Không có một cơ chế thắng mọi tiêu chí. Một sản phẩm thực tế thường giữ **nhiều indexes cho các chức năng khác nhau** theo tỷ lệ sử dụng.

## 25. Hiệu năng: đánh giá bằng `explain`, không bằng cảm giác

### 25.1. B-tree equality

```javascript
lab.names.find({ name: "cafe" })
  .explain("executionStats");
```

Kỳ vọng xem xét `IXSCAN`/`FETCH` hoặc plan tương ứng, số keys/docs examined và số result.

### 25.2. Collation-aware equality

```javascript
lab.names.find({ name: "cafe" })
  .collation({ locale: "fr", strength: 1 })
  .explain("executionStats");
```

Nếu có index cùng collation, query có cơ hội sử dụng. Nếu query override collation khác, cần xem lại plan.

### 25.3. Regex prefix và regex contains

```javascript
lab.names.find({ name: /^caf/ })
  .explain("executionStats");

lab.names.find({ name: /caf/ })
  .explain("executionStats");
```

Trên dữ liệu lớn, prefix case-sensitive thường có cơ hội hẹp hơn. Ở lab vài document, optimizer có thể chọn scan do chi phí khởi động index.

### 25.4. Legacy `$text`

```javascript
lab.articles.find({
  $text: { $search: "mongodb" }
}).explain("executionStats");
```

Đừng nhầm internal text index plans với B-tree equality. `$text` có điều kiện riêng về index và không hỗ trợ `hint()` ép text index.

### 25.5. MongoDB Search

Với `$search`, cần dùng monitoring, explain/profiling support phù hợp với phiên bản và search service. MongoDB Search có cơ chế index riêng, thời gian build và search-specific resource usage.

**Chỉ số cần đo:**

- Query latency p50/p95/p99.
- `nReturned`, documents/keys examined khi applicable.
- Tỷ lệ query bị COLLSCAN hoặc scan rộng.
- Số index và tổng index size.
- Insert/update cost (write amplification).
- Search index freshness.
- Relevance quality: precision/recall trên bộ truy vấn đánh giá.
- CPU/memory/network và chi phí Search nodes/service.

## 26. Bảo mật và correctness trong tìm kiếm

### 26.1. Không biến search thành quyền truy cập

Nếu một người dùng chỉ được xem sản phẩm của tenant A, mọi kết quả phải được **giới hạn theo tenant/ACL** bằng điều kiện phù hợp. Không lấy search score làm quyền truy cập.

Ví dụ tư duy:

```javascript
// Bảo đảm tenant scope ngay trong query nghiệp vụ.
db.products.find({
  tenantId: "A",
  sku: "CF-001"
});
```

Với MongoDB Search, cần thiết kế filter/compound hoặc kiểm tra quyền hậu truy vấn theo kiến trúc, tránh rò rỉ dữ liệu qua autocomplete, facets hoặc highlighting.

### 26.2. Không chạy regex tùy ý từ người dùng

Trường search nhập tự do có thể chứa ký tự đặc biệt. Nếu API dự định chỉ tìm literal prefix, cần escape regex characters, giới hạn chiều dài và đặt resource/time budgets.

### 26.3. Unique constraints là invariant nghiệp vụ

Search index **không** thay unique index cho `username`/`sku`. Full-text match chỉ cho ra tài liệu liên quan, không chứng minh một giá trị là duy nhất theo policy.

### 26.4. Search index có thể trễ

Ứng dụng vừa tạo một sản phẩm nhưng search kết quả chưa thấy ngay: không nhất thiết insert thất bại. Tìm trực tiếp bằng `_id`/`sku` và write/read concern phù hợp có thể cho kết luận chính xác hơn.

### 26.5. Không “bỏ dấu” mọi thứ

Nếu normalize tên người, địa chỉ, mã hoặc thương hiệu mà không có policy, có thể vô tình hợp nhất những giá trị vốn khác nhau. Nên lưu **giá trị hiển thị gốc** và **key chuẩn hóa** riêng, quản lý version của thuật toán normalization.

## 27. Những sai lầm phổ biến

| Nhận định sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `{title:"mongodb"}` tìm mọi bài nhắc từ mongodb | Equality so sánh toàn field | `$text`/Search |
| Collation chính là full-text search | Collation không tokenize/rank | Chọn search index |
| `strength:1` nghĩa bỏ mọi dấu/chuyển tự của mọi chữ | ICU locale có primary differences | Test locale, normalized field nếu cần |
| Regex `/i` sẽ tận dụng case-insensitive collation index | Regex không collation-aware | Equality+collation hoặc Search |
| Regex `/cafe/` giống `$text:"cafe"` | Substring khác token | Xác định contract |
| Một index B-tree giải quyết mọi prefix/contains | Không phải mọi regex có prefix tối ưu | Explain và Search |
| `$text` là aggregation stage `$search` | Hai API/index khác nhau | Dùng đúng syntax và index |
| Text index có thể tạo nhiều cái trên một collection | Legacy chỉ một text index | Gộp fields hoặc Search |
| Text index có collation `vi` để stem tiếng Việt | Text indexes chỉ simple collation, no Vietnamese stemmer | Search analyzer hoặc `none` có giới hạn |
| `default_language:"english"` xử lý tiếng Việt tốt | Stemming/stop words không phù hợp | Chọn `none`/Search tùy use case |
| `$text` mặc định AND tất cả từ | Mặc định là OR các tokens | Phrase/compound semantics |
| `$text` mặc định sắp theo relevance | Không | Sort textScore |
| Có `textScore` thì score là xác suất đúng | Score tương đối theo corpus/index | Đánh giá ranking |
| Tìm `"mongo"` sẽ luôn match `"mongodb"` | Text matching không là prefix | Autocomplete/ngram |
| Collation-aware unique chỉ thay sort | Nó có thể thay uniqueness | Audit collisions trước migration |
| Đổi collection collation không ảnh hưởng indexes | Default collation và index collation liên quan | Xem creation/migration plan |
| Search trả kết quả mới ngay sau mọi write | Search indexing có thể async | Direct lookup nếu cần freshness |
| Search index thay B-tree index | Mục tiêu khác | Dùng đúng index cho invariant/query |
| Có `IXSCAN` là query chắc chắn nhanh | Còn nhiều keys/docs, sort và fetch | Đo nReturned, p95/p99 |
| Không cần escape user regex | Pattern injection và CPU risk | Escape/limit/timeout |
| Locale `vi` và `$text` language `vietnamese` là một | Danh sách hỗ trợ khác nhau | Phân biệt ICU collator và text stemmer |
| Có fuzzy thì mọi typo sẽ khớp | Edit limits/analyzer có giới hạn | Test corpus và options |

## 28. Bài tập thực hành

### Bài 1 — Xác định yêu cầu

Với bốn API sau, hãy chọn equality, regex, collation, `$text` hay MongoDB Search:

1. `GET /products/sku/CF-001`.
2. Tìm username `Alice` không phân biệt hoa/thường.
3. Tìm bài viết nói về “indexing” và xếp theo liên quan.
4. Gợi ý tên sản phẩm khi user mới gõ `ca`.

**Đáp án định hướng:** 1 equality+B-tree; 2 collation-aware unique hoặc normalized key; 3 text search; 4 Search autocomplete hoặc prefix nếu nhỏ.

### Bài 2 — So khớp simple

Dữ liệu names có `"cafe"`, `"CAFE"`, `"Café"`, `"café"`. Query `{name:"cafe"}` với collation `simple` khớp bản nào?

**Đáp án:** Chỉ bản `"cafe"` trong fixture.

### Bài 3 — Strength 1 vs 2

Với `locale:"fr"`, tìm `"cafe"` ở strength 1 và strength 2. Mức nào bỏ cả case và dấu? Mức nào bỏ case nhưng phân biệt dấu?

**Đáp án:** Strength 1 bỏ cả case/diacritic theo quan hệ base locale; strength 2 bỏ case nhưng giữ diacritic differences.

### Bài 4 — Collation không phải substring

Vì sao `{name:"cafe"}` + strength 1 không có nghĩa khớp `"café mocha"`?

**Đáp án:** Equality so sánh **toàn bộ giá trị field**, không tìm token/substring.

### Bài 5 — Regex prefix

So sánh `/^caf/`, `/caf/`, `/^cafe/i` về semantics và khả năng dùng index.

**Đáp án:** Anchored case-sensitive prefix có cơ hội tạo index range; contains và regex case-insensitive kém tối ưu hơn.

### Bài 6 — Regex và dấu

Regex `/^cafe/i` có mặc nhiên khớp `"café"` không? Vì sao collation strength 1 không biến regex thành accent-insensitive?

**Đáp án:** Không; regex không collation-aware.

### Bài 7 — Matching collation index

Tạo index `{name:1}` với `locale:"fr",strength:1`. Query với strength 2 có sử dụng cùng index để hỗ trợ string comparison không?

**Đáp án:** Không nên kỳ vọng; query cần collation tương ứng index.

### Bài 8 — Username unique

Tạo unique index username strength 2, insert `"Alice"` rồi `"alice"`. Điều gì xảy ra? Nếu collection đã có cả hai trước khi tạo index thì sao?

**Đáp án:** Insert thứ hai bị unique violation; tạo index mới trên dữ liệu đã có collision cũng lỗi.

### Bài 9 — Sort mã item

Mặc định string sort có thể đặt `item10` trước `item2`. Dùng collation option nào để so sánh đoạn số dương theo giá trị?

**Đáp án:** `numericOrdering:true` với locale được hỗ trợ.

### Bài 10 — Text index cơ bản

Tạo text index trên `title`/`body` với weights title 10, body 2. Giải thích ý nghĩa weights; có tạo thêm một text index thứ hai trên `description` được không?

**Đáp án:** Weights điều chỉnh relevance, collection chỉ có một legacy text index; có thể index nhiều fields trong index đó.

### Bài 11 — OR và phrase

So sánh:

```javascript
{ $text: { $search: "mongodb indexing" } }
{ $text: { $search: "\"mongodb indexing\"" } }
```

**Đáp án:** Chuỗi nhiều từ không quote thường OR token; quote yêu cầu cụm từ.

### Bài 12 — Negation

`$search:"mongodb -backup"` có ý nghĩa gì? Vì sao tìm literal SKU có dấu gạch nối thường nên dùng equality thay vì `$text`?

### Bài 13 — TextScore

Viết query `$text` để trả `title`, `score` và sắp giảm theo score. Điều gì xảy ra nếu bỏ `.sort()`?

**Đáp án:** `$text` không mặc định sort theo relevance.

### Bài 14 — Text index language

Legacy `$text` có Vietnamese stemming language mặc định không? `default_language:"none"` mang lại điều gì và không mang lại điều gì?

**Đáp án:** Không có Vietnamese trong danh sách supported stemmers; `none` bỏ stemming/stop words đặc thù, không tự thành analyzer tiếng Việt hoàn chỉnh.

### Bài 15 — Phân biệt `$text` và `$search`

Một developer viết `$search` aggregation stage trên MongoDB không cấu hình Search service/index nhưng đã có legacy text index. Có chạy được không? Vì sao?

**Đáp án:** Không chỉ dựa trên text index là đủ; `$search` cần MongoDB Search availability và Search index phù hợp.

### Bài 16 — MongoDB Search fuzzy

Viết ví dụ `$search.text` với `fuzzy.maxEdits:1`. Giải thích vì sao không nên hứa mọi typo đều tìm thấy.

### Bài 17 — Autocomplete

Muốn gợi ý title khi nhập `"mong"`, chỉ tạo Search index với field mapping `"string"` đã đủ chưa?

**Đáp án:** Không; cần autocomplete mapping và operator phù hợp.

### Bài 18 — Tiếng Việt

Thiết kế test suite cho search `"Cà phê sữa"`, `"ca phe sua"`, `"cà Phê Sữa"`, `"cafe sua"` và tên có `đ`/`d`. Những mức nào cần kiểm tra ICU collation, normalized key và Search analyzer?

### Bài 19 — Query performance

Đo `explain("executionStats")` cho equality, collation-aware equality, prefix regex và substring regex. Những metric nào quan trọng hơn việc chỉ thấy tên `IXSCAN`?

**Đáp án:** Keys/docs examined, nReturned, latency/p95/p99 và index size.

### Bài 20 — Chọn kiến trúc tổng hợp

Xây hệ thống tìm kiếm sản phẩm gồm:

- SKU phải globally unique.
- Product title hiển thị có dấu.
- Filter tên không phân biệt case.
- Sort tên theo tiếng Việt.
- Autocomplete và fuzzy.
- Search ranking kết hợp title và description.
- Tenant data isolation.
- Kết quả phải biết khi nào search index chưa cập nhật write mới.

Hãy đề xuất schema, B-tree/collation/Search indexes, API routing và kiểm soát security; giải thích vì sao không một index duy nhất đáp ứng tất cả.

## 29. Tổng kết

**So khớp chuỗi**, **collation** và **full-text search** là ba tầng khác nhau:

1. **Equality/B-tree**: tìm toàn bộ giá trị trường chính xác; thích hợp ID, mã, normalized key.
2. **Regex**: kiểm tra pattern ký tự; prefix case-sensitive có thể tối ưu bằng B-tree, contains và `/i` thường tốn kém hơn.
3. **Collation**: quy tắc equality/sort/unique theo locale và strength. Collation không tokenize hoặc rank văn bản.
4. **Legacy `$text` + text index**: tìm theo token, stem/stop words của ngôn ngữ hỗ trợ, phrase/negation/textScore; có giới hạn một text index/collection.
5. **MongoDB Search `$search`**: tìm kiếm nâng cao với Search index/analyzer, relevance, fuzzy, autocomplete, phrase, synonyms và filtering; yêu cầu deployment/configuration hỗ trợ.

Với tiếng Việt, cần phân biệt **ICU collation locale `vi`** và **legacy text index language**: hỗ trợ thứ nhất không có nghĩa thứ hai có Vietnamese stemming. Nếu search theo nghĩa, gõ dở hoặc không dấu là yêu cầu quan trọng, phải kiểm chứng analyzer/normalization trên dữ liệu thật.

**Quy tắc lựa chọn cuối:** Hỏi rõ sản phẩm cần **bằng nhau**, **chứa ký tự**, **so sánh/sắp xếp theo locale**, hay **tìm từ/cụm từ theo relevance**. Sau đó mới chọn index và API phù hợp.

### Tài liệu MongoDB chính thức

- [Comparison/Collation](https://www.mongodb.com/docs/manual/reference/collation/) — quy tắc ICU, `strength`, `caseLevel`, `numericOrdering` và index matching.
- [Collation Locales and Defaults](https://www.mongodb.com/docs/manual/reference/collation-locales-defaults/) — locale `vi`, `en`, `fr` và option defaults.
- [Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/) — matching collation indexes và giới hạn regex.
- [`$regex` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/regex/) — cú pháp, prefix optimization, case-insensitive regex.
- [Text Search](https://www.mongodb.com/docs/manual/text-search/) — phân biệt legacy `$text` và MongoDB Search.
- [`$text` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/text/) — OR/phrase/negation/score và hạn chế.
- [Text Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-restrictions/) — một text index, compound index và binary collation.
- [Text Search Languages](https://www.mongodb.com/docs/manual/reference/text-search-languages/) — danh sách legacy stemming languages.
- [Specify Text Index Language](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/specify-text-index-language/) — English/default_language none.
- [MongoDB Search `$search` Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/search/) — supported deployments và pipeline.
- [MongoDB Search Text Operator](https://www.mongodb.com/docs/search/query/operators-collectors/text/) — analyzer, fuzzy và query semantics.
- [Search Autocomplete and Partial Match](https://www.mongodb.com/docs/search/tutorial/partial-match/) — autocomplete, phrase, regex và wildcard.
- [Create a MongoDB Search Index](https://www.mongodb.com/docs/atlas/atlas-search/create-index/) — định nghĩa và build index.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — ràng buộc uniqueness trên collection.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — query plan và executionStats.
