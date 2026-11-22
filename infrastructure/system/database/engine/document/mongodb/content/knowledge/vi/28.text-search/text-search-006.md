# Search index, analyzer, tokenizer và chuẩn hóa văn bản trong MongoDB

## 1. Vì sao tìm kiếm văn bản cần thiết kế riêng?

Trong hệ thống quản lý sản phẩm, bất động sản, bài viết, tài liệu hoặc yêu cầu hỗ trợ, người dùng thường gõ một vài từ thay vì biết chính xác khóa của document:

- Tìm `"máy lọc nước"` trong tên và mô tả sản phẩm.
- Gõ `"may loc"` nhưng muốn thấy `"Máy lọc"` nếu ứng dụng hỗ trợ tìm kiếm không dấu.
- Gõ `"wireles"` và muốn thấy `"wireless"` nhờ fuzzy matching.
- Gõ vài ký tự đầu để thấy gợi ý autocomplete.
- Tìm cụm `"data engineering"` theo thứ tự từ.
- Chỉ hiển thị các kết quả thuộc `tenantId` của người đang đăng nhập, còn hàng và đang hoạt động.
- Giữ nguyên mã SKU `"AB-123-X"` để đối chiếu chính xác, không bị tách như văn xuôi.

Truy vấn như:

```javascript
db.products.find({
  title: /máy lọc/i
});
```

có thể dùng cho tình huống đơn giản, nhưng không mặc định cung cấp word tokenization, xử lý dấu, relevance score, fuzzy matching, tìm theo nhiều field hoặc ranking đầy đủ của một hệ search.

MongoDB có hai họ cơ chế tìm kiếm văn bản cần phân biệt:

1. **Legacy text index** do `createIndex({ field: "text" })` tạo, truy vấn bằng `$text`. Đây là tính năng text search truyền thống của MongoDB.
2. **MongoDB Search** (trước đây thường gọi **Atlas Search**), sử dụng **Search index** riêng, analyzer và aggregation stage `$search`/`$searchMeta`. Thành phần tìm kiếm sử dụng **Apache Lucene** thông qua tiến trình `mongot`.

Bài này tập trung vào **MongoDB Search index** và quá trình **phân tích văn bản** (analyzers, tokenizers, filters, normalization). Legacy `$text` được so sánh riêng để tránh trộn hai API.

> **Tư duy nền tảng:** Search không so sánh chuỗi gốc một cách đơn giản; nó thường biến chuỗi thành **tokens** có thể tìm kiếm. Analyzer quyết định tokens được tạo như thế nào khi index và khi query.

---

## 2. Kiến trúc: document dữ liệu và Search index là hai lớp khác nhau

Một document nghiệp vụ:

```javascript
{
  _id: "P100",
  tenantId: "T1",
  title: "Máy lọc nước mini",
  description: "Thiết bị lọc nước dùng trong gia đình.",
  sku: "MLN-100",
  brand: "AquaHome",
  status: "ACTIVE",
  priceMinor: 2490000
}
```

Các field tồn tại trong collection của `mongod`. Search index không phải một field mới nhét vào document và cũng không phải B-tree index thông thường.

Sơ đồ khái niệm:

```text
Application
     |
     +-- insert/update/delete ----------> mongod
     |                                      |
     |                                      | đồng bộ index
     |                                      v
     |                                   mongot
     |                              (Search/Lucene)
     |                                      |
     +-- aggregate([{$search: ...}]) -------+
             |
             v
     Documents + relevance scores
```

- `mongod` duy trì dữ liệu nguồn.
- `mongot` duy trì chỉ mục tìm kiếm được đồng bộ từ nguồn, và xử lý một phần nghiệp vụ Search.
- Client gửi aggregation query vào MongoDB qua driver; client **không kết nối trực tiếp tới mongot**.
- Dữ liệu index có thể cập nhật **bất đồng bộ** so với ghi vào collection. Vì vậy kết quả search ngay sau write có thể chưa phản ánh mọi thay đổi vừa commit.
- Search index phục vụ truy vấn từ khóa; với bài toán vector/semantic search còn có **MongoDB Vector Search index** và `$vectorSearch`, không phải đối tượng chính của bài này.

### 2.1. Điều kiện triển khai năm 2026

MongoDB Search không còn là một khả năng chỉ có ở MongoDB Atlas: từ giữa năm 2026, MongoDB Search và Vector Search cũng có bản **generally available cho Community Edition và Enterprise Advanced self-managed** theo các deployment requirements tương ứng.

| Môi trường | Search triển khai thế nào? |
| --- | --- |
| MongoDB Atlas hỗ trợ Search | Atlas quản lý `mongot` và Search indexes theo kiến trúc được cấp. |
| MongoDB self-managed được hỗ trợ | Operator quản trị triển khai, cấu hình và vận hành `mongot` riêng. |
| `mongod` thông thường không tích hợp Search | Chỉ có MongoDB server/driver không đảm bảo `$search` khả dụng. |
| Legacy `$text` index | Không cần cùng Search architecture, nhưng ít tính năng phân tích và ranking hơn. |

**Quan trọng:** Không thể mở một `mongod` standalone bất kỳ rồi chỉ chạy `createSearchIndex()` để tự động có Search đầy đủ nếu chưa triển khai `mongot` và cấu hình phiên bản/topology đúng. Hãy kiểm tra deployment options, compatibility và quyền quản trị.

Nguồn: [MongoDB Search deployment options](https://www.mongodb.com/docs/search/deployment/deployment-options/), [Self-Managed MongoDB Search](https://www.mongodb.com/docs/search/self-managed/current/).

---

## 3. Search index khác B-tree index và text index truyền thống

| Tiêu chí | B-tree index | Legacy text index | MongoDB Search index |
| --- | --- | --- | --- |
| Tạo bởi | `createIndex({field: 1})` | `createIndex({field:"text"})` | `createSearchIndex(...)` hoặc công cụ Search |
| Truy vấn | `find`, `aggregate` thông thường | `$text` | `$search`, `$searchMeta` |
| Cấu hình analyzer tùy biến | Không theo Search analyzer | Có cấu hình text/language riêng, giới hạn hơn | Analyzer và custom analyzer đầy đủ |
| Tokenizer/char filters/token filters | Không | Không tùy biến theo pipeline Search | Có |
| Phrase, fuzzy, autocomplete | Không phải mục tiêu của B-tree | Hạn chế | Có toán tử chuyên biệt |
| Scoring | Không mặc định relevance score | `textScore` | `searchScore`, nhiều scoring options |
| Exact equality và sort | Rất phù hợp | Không phải ưu tiên | Kiểu `token` và normalizer hỗ trợ một số trường hợp |
| Chi phí index | Tùy index keys | Text index trên server | Thêm Search storage, indexing, `mongot` |
| Đồng bộ sau ghi | Trong cơ chế write/index của MongoDB | Trong cơ chế server | Search có thể có indexing lag |

**Không dùng lẫn cú pháp:**

```javascript
// Legacy text index:
db.products.createIndex({ title: "text" });

// Legacy text search:
db.products.find({
  $text: { $search: "water filter" }
});

// MongoDB Search index là cơ chế khác:
// db.products.createSearchIndex(...)

// MongoDB Search query:
db.products.aggregate([
  {
    $search: {
      index: "catalog_text_v1",
      text: {
        query: "water filter",
        path: "title"
      }
    }
  }
]);
```

`$text` và `$search` không chỉ khác tên. Chúng cần **những loại index khác nhau** và có ngữ nghĩa phân tích/ranking không hoàn toàn giống.

---

## 4. Bộ dữ liệu thử nghiệm dùng xuyên suốt bài

Để ví dụ độc lập, tạo collection mới `searchLesson305` trong database thử nghiệm có MongoDB Search được hỗ trợ. Không chạy những đoạn này trên collection production có dữ liệu thật.

```javascript
const catalog = db.getSiblingDB("search_lab");
const products = catalog.getCollection("searchLesson305");

products.insertMany([
  {
    _id: "P001",
    tenantId: "T1",
    title: "Máy lọc nước mini",
    description: "Máy lọc nước gia đình, thiết kế nhỏ gọn",
    brand: "AquaHome",
    sku: "MLN-100",
    status: "ACTIVE",
    category: "home"
  },
  {
    _id: "P002",
    tenantId: "T1",
    title: "Máy lọc không khí",
    description: "Thiết bị lọc không khí trong phòng ngủ",
    brand: "AirPro",
    sku: "AIR-200",
    status: "ACTIVE",
    category: "home"
  },
  {
    _id: "P003",
    tenantId: "T1",
    title: "Bộ lọc nước thay thế",
    description: "Lõi lọc cho thiết bị gia đình",
    brand: "AquaHome",
    sku: "CORE-03",
    status: "ACTIVE",
    category: "parts"
  },
  {
    _id: "P004",
    tenantId: "T2",
    title: "Wireless Mouse",
    description: "Comfortable computer mouse with wireless connection",
    brand: "TechWorks",
    sku: "MOUSE-04",
    status: "ACTIVE",
    category: "electronics"
  },
  {
    _id: "P005",
    tenantId: "T1",
    title: "Water Filter",
    description: "Compact household water filtration system",
    brand: "AquaHome",
    sku: "WF-500",
    status: "ACTIVE",
    category: "home"
  },
  {
    _id: "P006",
    tenantId: "T1",
    title: "Data Engineering Handbook",
    description: "Learn data pipelines and modern analytics",
    brand: "BookLab",
    sku: "BOOK-06",
    status: "INACTIVE",
    category: "books"
  },
  {
    _id: "P007",
    tenantId: "T2",
    title: "Nước rửa tay",
    description: "Dung dịch chăm sóc gia đình",
    brand: "CareLife",
    sku: "CARE-07",
    status: "ACTIVE",
    category: "personal-care"
  }
]);
```

Đây là bộ mẫu để hiểu cách xây index và viết pipeline, **không phải lời hứa tập kết quả chính xác trong mọi phiên bản**. Kết quả text matching phụ thuộc analyzer, index definitions và thời điểm Search index đồng bộ xong.

### 4.1. Lý do phải có nhiều loại field

- `title` và `description` là **ngôn ngữ tự nhiên**, cần chia tokens.
- `sku` là **mã định danh**, thường phải giữ nguyên dấu gạch và so khớp chính xác.
- `brand` là **thuộc tính lọc/facet**, thường nên coi là một token nguyên vẹn.
- `tenantId` là **ràng buộc truy cập** và không được phụ thuộc duy nhất vào search score.
- `status`, `category` là metadata phục vụ lọc.
- Tiếng Việt có dấu, không dấu và nhiều **từ ghép nhiều âm tiết**, cần chiến lược analyzer có ý thức.

---

## 5. Tạo Search index đầu tiên: dynamic mapping

Cách làm đơn giản để thử nghiệm:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .createSearchIndex(
    "catalog_dynamic_v1",
    {
      mappings: {
        dynamic: true
      }
    }
  );
```

`dynamic: true` khiến MongoDB Search index những field có kiểu dữ liệu được hỗ trợ theo dynamic mapping; nó giúp thử nghiệm nhanh mà không cần liệt kê mọi đường dẫn.

### 5.1. Điểm mạnh và yếu

**Điểm mạnh:**

- Setup nhanh trên dữ liệu mẫu.
- Có thể search các string fields mà không phải chỉ định từng field.
- Hữu ích để khám phá query patterns trong giai đoạn prototype.

**Nhược điểm:**

- Có thể index cả field không phục vụ use case, tăng chi phí lưu trữ và indexing.
- Các string fields dưới dynamic mapping mặc định được index theo kiểu `string`, không tự có kiểu `token` cho equality/facet/sort.
- Analyzer chung có thể không phù hợp cho `sku`, `brand` hoặc ngôn ngữ riêng.
- Những field nhạy cảm có thể vô tình được đưa vào search index nếu không có chiến lược schema/mapping thích hợp.

Đối với production, thường nên dùng **static/explicit mapping** để kiểm soát field types và analyzer.

### 5.2. Search index không sẵn sàng ngay lập tức

`createSearchIndex()` kích hoạt **quá trình build bất đồng bộ**. Lệnh trả về không đảm bảo index đã có thể dùng ngay.

Kiểm tra:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $listSearchIndexes: {
        name: "catalog_dynamic_v1"
      }
    }
  ]);
```

Trạng thái có thể là `PENDING`, `BUILDING`, `READY`, `FAILED` hoặc `STALE` theo hoàn cảnh. **Chỉ xem `READY` là bằng chứng index mới có thể dùng đầy đủ**; trong lúc rebuild một index đã có, MongoDB có thể tiếp tục phục vụ bằng definition cũ.

Không đưa polling tạo index vào request của người dùng. Index management là thao tác deployment/migration.

---

## 6. Static mapping: field nào được index dưới kiểu nào?

Một index có chủ đích:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .createSearchIndex(
    "catalog_text_v1",
    {
      mappings: {
        dynamic: false,
        fields: {
          title: {
            type: "string",
            analyzer: "lucene.standard"
          },
          description: {
            type: "string",
            analyzer: "lucene.standard"
          },
          brand: {
            type: "token",
            normalizer: "lowercase"
          },
          sku: {
            type: "token",
            normalizer: "none"
          },
          tenantId: {
            type: "token"
          },
          status: {
            type: "token"
          },
          category: {
            type: "token"
          }
        }
      }
    }
  );
```

Các field được chọn:

| Field | Search field type | Mục tiêu |
| --- | --- | --- |
| `title` | `string` | Full-text retrieval và ranking |
| `description` | `string` | Full-text trong mô tả |
| `brand` | `token` | Equality, facet, sort theo chuỗi đã chuẩn hóa |
| `sku` | `token` | So khớp giá trị mã nguyên vẹn |
| `tenantId` | `token` | Lọc theo tenant một cách chính xác |
| `status` | `token` | Lọc trạng thái |
| `category` | `token` | Lọc phân loại |

**Từ khóa quan trọng:**

- **`string`**: có analyzer để tạo một hoặc nhiều searchable terms từ văn bản.
- **`token`**: biểu diễn một chuỗi thành **một token nguyên vẹn**; có `normalizer` như `none` hoặc `lowercase`.
- Không tự thay mọi `string` thành `token`: dùng `token` rồi kỳ vọng `text`/`phrase` vẫn làm full-text như trước là sai.

### 6.1. Dynamic mapping không mặc định là true

Nếu bỏ `mappings.dynamic`, cấu hình định nghĩa thường mặc định **false**. Vì vậy:

```javascript
{
  mappings: {
    fields: {
      title: { type: "string" }
    }
  }
}
```

thường tương đương mục tiêu index `title` được nêu tường minh; những field ngoài mapping không tự tham gia Search mặc định.

---

## 7. Truy vấn đầu tiên bằng $search

Trước khi query, xác nhận index `catalog_text_v1` đã `READY`.

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_text_v1",
        text: {
          query: "water filter",
          path: ["title", "description"]
        }
      }
    },
    { $limit: 10 },
    {
      $project: {
        _id: 1,
        title: 1,
        brand: 1,
        score: { $meta: "searchScore" }
      }
    }
  ]);
```

Các thành phần:

- `$search`: aggregation stage chạy MongoDB Search; thường phải là **stage đầu tiên** của pipeline chứa nó.
- `index`: tên Search index, không phải B-tree index.
- `text.query`: văn bản người dùng muốn tìm.
- `text.path`: string field hoặc mảng fields đã index kiểu `string`.
- `$limit`: giới hạn số kết quả.
- `$meta: "searchScore"`: relevance score do Search tính, không phải số lượng từ match đơn thuần.

### 7.1. Search không mặc định là exact substring

Nếu query là `"filter"`, analyzer có thể token hóa thành `filter` để so với token trong document. Điều này không có nghĩa mọi substring của `"filtering"` hoặc `"filtration"` đều match tự động; kết quả phụ thuộc analyzer, stemming, fuzzy và toán tử.

### 7.2. Search index có thể “stale” sau write

Nếu insert xong rồi ngay lập tức search:

```javascript
db.searchLesson305.insertOne({
  _id: "P008",
  title: "New Water Filter"
});
```

một query `$search` chạy ngay sau lệnh có thể chưa thấy P008. Đây là **indexing lag**, không mặc định là lỗi transaction hoặc document chưa được ghi. Với luồng nghiệp vụ yêu cầu **read-your-writes ngay lập tức**, có thể cần kết hợp đường đọc theo khóa thông thường thay vì chỉ tin Search.

---

## 8. Analyzer là gì?

**Analyzer** là quy trình biến chuỗi thành các **terms/tokens** để lập index hoặc tìm trong index.

Luồng custom analyzer:

```text
Text gốc
   |
   v
Character filters (0 hoặc nhiều)
   |
   v
Tokenizer (1)
   |
   v
Token filters (0 hoặc nhiều; theo thứ tự)
   |
   v
Tokens dùng cho index hoặc query
```

Ví dụ hình dung:

```text
Input:
  "MÁY-LỌC NƯỚC!"

Char normalization:
  chuẩn hóa Unicode khi có cấu hình

Tokenizer:
  "MÁY" | "LỌC" | "NƯỚC"

Lowercase:
  "máy" | "lọc" | "nước"

Accent folding (nếu được cấu hình):
  "may" | "loc" | "nuoc"

Index:
  các terms tương ứng document
```

Đây là **sơ đồ giải thích** chứ không khẳng định tất cả analyzers cho ra chính xác ba tokens này. Tách dấu gạch nối và xử lý dấu phụ thuộc tokenizer/filter thật.

### 8.1. Vì sao quan trọng?

Hai document có thể khác chuỗi gốc nhưng trùng tokens:

```text
"Wireless Mouse"
"wireless mouse"
```

Khi analyzer lowercase, cả hai có thể sinh `wireless`, `mouse`.

Nhưng nếu tokenizer giữ toàn chuỗi:

```text
"Wireless Mouse" -> "Wireless Mouse"
```

thì query `"mouse"` không thể chỉ dựa vào việc chữ `mouse` nằm bên trong token để match như full-text chia từ.

**Analyzer quyết định “thế nào là một từ có thể tìm” đối với index và query.**

---

## 9. Index analyzer và search analyzer

MongoDB Search có hai vị trí cấu hình cần phân biệt:

- **`analyzer`**: dùng khi **lập chỉ mục** text của document.
- **`searchAnalyzer`**: dùng khi **phân tích text của query** trước khi so với các terms trong index.

Ví dụ:

```text
Document "Máy Lọc Nước"   --index analyzer--> ["may", "loc", "nuoc"]
Query    "may loc"        --search analyzer-> ["may", "loc"]

=> các terms có khả năng gặp nhau.
```

Nếu hai analyzer không tương thích:

```text
Index analyzer keyword:
  "wireless mouse" -> ["wireless mouse"]

Search analyzer standard:
  "wireless mouse" -> ["wireless", "mouse"]

=> không có cùng token "wireless mouse" để match như mong đợi.
```

### 9.1. Thứ tự kế thừa cấu hình

Với field kiểu `string`, nếu không khai báo trực tiếp:

- Field `analyzer` thường lấy từ index-level `analyzer`, cuối cùng tới `lucene.standard`.
- Field `searchAnalyzer` ưu tiên field `analyzer` đã khai báo, sau đó index-level `searchAnalyzer` và index-level `analyzer` theo quy tắc kế thừa của Search, cuối cùng là `lucene.standard`.

Để tránh khó suy luận trong production, **khai báo tường minh** analyzer quan trọng ở field hoặc index definition.

### 9.2. Vì sao có thể cố ý dùng hai analyzer khác nhau?

Có những chiến lược bất đối xứng:

- Index dùng n-gram để hỗ trợ prefix nhưng query dùng tokenizer ít sinh tokens hơn.
- Index đưa cả token gốc và dạng stemmed; query áp quy tắc nhẹ hơn.
- Index phân tách một định danh kiểu `"AB-123"`; query có normalization riêng để hỗ trợ input của người dùng.

Tuy nhiên không phải mọi cặp analyzer đều hợp lệ hoặc cho kết quả đúng. **Phải kiểm tra token đầu ra của cả hai phía.** Nếu chỉ cần tìm kiếm full-text thông thường, dùng cùng analyzer thường đơn giản và dễ dự đoán hơn.

---

## 10. Built-in analyzers quan trọng

MongoDB Search có các analyzer built-in phổ biến:

| Analyzer | Cách hoạt động ở mức khái niệm | Phù hợp |
| --- | --- | --- |
| `lucene.standard` | Phân tích text theo quy tắc từ/Unicode thông dụng, analyzer mặc định | Full-text đa mục đích |
| `lucene.simple` | Tách khi gặp ký tự không phải chữ, lowercase | Văn bản đơn giản |
| `lucene.whitespace` | Chia theo khoảng trắng, **giữ nguyên case** | Text vốn đã được chuẩn hóa theo khoảng trắng |
| `lucene.keyword` | Toàn bộ chuỗi là **một token**, giữ nguyên case | Một chuỗi cần giữ nguyên như một đơn vị |
| `lucene.english` | Phân tích dành cho tiếng Anh, gồm quy tắc ngôn ngữ liên quan | English full-text, khi phù hợp |
| Các `lucene.<language>` khác | Stop words/word divisions/stemming tùy ngôn ngữ | Dữ liệu theo ngôn ngữ được hỗ trợ |

### 10.1. Không phải analyzer nào cũng lowercase

Ví dụ tài liệu MongoDB xác nhận:

- `lucene.simple` lowercase.
- `lucene.whitespace` **không tự lowercase**.
- `lucene.keyword` **không tự lowercase**.

Nếu SKU `"Ab-123"` phải được tìm bằng `"ab-123"`, dùng keyword analyzer không tự bảo đảm case-insensitive matching. Cần normalizer hoặc custom analyzer phù hợp.

### 10.2. Không chọn language analyzer theo tên quốc gia của ứng dụng

Một ứng dụng tại Việt Nam có thể chứa tên sản phẩm tiếng Việt và tiếng Anh, mã kỹ thuật, địa chỉ, nhãn hiệu. Nếu áp `lucene.english` lên toàn bộ field, các stop words và stemming tiếng Anh có thể gây biến đổi không phù hợp.

**Trong danh sách language analyzers built-in của MongoDB Search không có `lucene.vietnamese` theo tài liệu tra cứu năm 2026.** Không được tự bịa tên analyzer đó. Tiếng Việt cần lựa chọn index model/analyzer và kiểm thử riêng; các chiến lược được trình bày bên dưới.

Nguồn: [Language analyzers](https://www.mongodb.com/docs/search/indexes/analyzers/language/).

---

## 11. Tokenizer là gì?

**Tokenizer** là phần bắt buộc trong custom analyzer: nhận text sau char filters và quyết định **ranh giới token**.

Ví dụ:

```text
Input: "USB-C Adapter 65W"
```

Các chiến lược có thể sinh kết quả khác nhau:

| Tokenizer | Định hướng |
| --- | --- |
| `standard` | Chia theo word break rules, không chỉ dấu cách |
| `whitespace` | Chỉ tách theo whitespace |
| `keyword` | Giữ toàn input thành một token |
| `nGram` | Sinh các chuỗi con độ dài n, theo cấu hình |
| `edgeGram` | Sinh các chuỗi ở rìa, hữu ích cho prefix |
| Regex-based tokenizers | Tách/bắt nhóm theo pattern được cấu hình |

Lưu ý: tên tokenizer trong **custom analyzer** thường là `standard`, `whitespace`, `keyword`, không có prefix `lucene.`. Trong khi đó các **built-in analyzer names** thường là `lucene.standard`, `lucene.keyword`.

### 11.1. Word tokenization và tiếng Việt

Tiếng Việt sử dụng khoảng trắng giữa các **âm tiết**, trong khi một từ ngữ nghĩa có thể gồm nhiều âm tiết:

```text
"Bất động sản"

Theo whitespace:
  ["Bất", "động", "sản"]

Theo phân từ tiếng Việt chuyên dụng:
  có thể coi ["bất_động_sản"] là một đơn vị
```

Standard/whitespace tokenizer không nên được mô tả là tự hiểu mọi từ ghép tiếng Việt. Việc tìm chính xác cụm, ranking theo ý nghĩa, hoặc phân biệt các từ đồng âm cần chiến lược ngôn ngữ riêng.

### 11.2. Tokenization ảnh hưởng phrase query

Nếu field đã sinh tokens với vị trí:

```text
"The quick brown fox"
  the (position 0)
  quick (1)
  brown (2)
  fox (3)
```

`phrase` có thể dùng thông tin vị trí để xét trật tự/khoảng cách tokens. Nếu index chỉ lưu document frequencies mà không lưu positions, phrase query cần thông tin đó có thể không khả dụng.

---

## 12. Character filters: xử lý trước khi chia token

**Character filters** sửa text **trước tokenizer**. Chúng thích hợp cho HTML, ký tự phân cách hoặc các dạng input cần chuẩn hóa ở cấp chuỗi.

Một số loại chính:

- `htmlStrip`: loại bỏ markup HTML phù hợp.
- `mapping`: thay thế các chuỗi/ký tự theo danh sách mapping đã khai báo.

Ví dụ:

```html
<h2>Wireless Mouse</h2><p>USB receiver included</p>
```

Nếu token hóa trực tiếp phần HTML, các từ tên tag có thể ảnh hưởng kết quả. Một char filter `htmlStrip` đưa text về dạng nội dung trước khi tokenizer xử lý.

Cấu hình custom analyzer:

```javascript
{
  name: "htmlText",
  charFilters: [
    { type: "htmlStrip" }
  ],
  tokenizer: {
    type: "standard"
  },
  tokenFilters: [
    { type: "lowercase" }
  ]
}
```

### 12.1. Thứ tự xử lý rất quan trọng

```text
HTML source
  -> htmlStrip
  -> standard tokenizer
  -> lowercase
  -> index terms
```

Không đặt `htmlStrip` vào `tokenFilters` vì nó không phải token filter. Không tự đảo trình tự nếu kỳ vọng kết quả giống nhau.

### 12.2. Không coi htmlStrip là sanitizer bảo mật HTML

Char filter dành cho **search text analysis**, không phải giải pháp chống XSS cho nội dung render lên trang. Nếu ứng dụng hiển thị HTML của user, cần escape/sanitize ở tầng output theo chuẩn bảo mật riêng.

---

## 13. Token filters: biến đổi từng token sau tokenizer

**Token filters** chạy **sau tokenizer**, theo đúng thứ tự khai báo.

Một số chức năng:

| Filter | Mục đích |
| --- | --- |
| `lowercase` | Chuyển token về chữ thường |
| `asciiFolding` | Chuyển các ký tự Unicode có dạng ASCII tương đương |
| `icuFolding` | Unicode folding, bao gồm các dạng tương đương/case/accent theo ICU |
| `icuNormalizer` | Chuẩn hóa Unicode NFC/NFD/NFKC/NFKD |
| `stopword` | Loại bỏ các stop words cấu hình |
| `length` | Bỏ token ngắn/dài ngoài khoảng |
| `nGram` | Tạo n-grams từ mỗi token |
| `edgeGram` | Tạo prefix n-grams từ token |
| Stemming filters | Rút gọn biến thể hình thái theo quy tắc ngôn ngữ |
| `shingle` | Tạo các cụm tokens kề nhau theo cấu hình |

### 13.1. Ví dụ thứ tự filters

```javascript
{
  tokenizer: { type: "standard" },
  tokenFilters: [
    { type: "icuNormalizer", normalizationForm: "nfc" },
    { type: "lowercase" },
    { type: "asciiFolding", originalTokens: "omit" }
  ]
}
```

Thứ tự ở đây là:

```text
Chuỗi -> standard tokens
      -> Unicode NFC
      -> lowercase
      -> ASCII folding
```

Không mặc định mọi filter **đổi một token thành một token**. Các filter như `nGram`, `edgeGram` hoặc `shingle` có thể tạo **nhiều tokens** từ một input, ảnh hưởng index size, phrase behavior và tính tương thích với các operator nhất định.

### 13.2. Stemming không phải tìm từ đồng nghĩa

Stemming tiếng Anh có thể xử lý các biến thể:

```text
"talked" / "talking" / "talks" -> thân từ liên quan
```

Nhưng nó không đồng nhất `"car"` với `"automobile"` theo nghĩa từ đồng nghĩa. Synonyms là một cơ chế riêng và cần từ điển/mapping phù hợp.

### 13.3. Stop words không phải càng nhiều càng tốt

Loại từ “the”, “a”, “of” có thể hữu ích cho một số corpus tiếng Anh, nhưng những từ ngắn trong tên sản phẩm/địa chỉ có thể rất quan trọng:

```text
"iPhone 15 Pro"
"USB C"
"Loại A"
"Đường 3/2"
```

Xóa stop words hoặc token độ dài một ký tự bừa bãi có thể gây mất truy vấn đúng. Test theo domain.

---

## 14. Chuẩn hóa Unicode: NFC, NFD, NFKC, NFKD

**Unicode normalization** xử lý những chuỗi trông giống nhau nhưng có thể được mã hóa khác nhau.

Ví dụ ký tự `é`:

```text
U+00E9         : ký tự dựng sẵn "é"
U+0065 U+0301  : "e" + dấu sắc kết hợp
```

Hai chuỗi có thể hiển thị giống nhưng dãy code points khác. Nếu không normalization thích hợp, search/index có thể xử lý chúng khác nhau.

Bốn dạng Unicode phổ biến:

| Form | Ý nghĩa |
| --- | --- |
| `NFD` | Canonical decomposition |
| `NFC` | Canonical decomposition rồi composition |
| `NFKD` | Compatibility decomposition |
| `NFKC` | Compatibility decomposition rồi composition |

### 14.1. Canonical khác compatibility

- Canonical normalization nhằm thống nhất những biểu diễn Unicode **tương đương chính tắc**.
- Compatibility normalization có thể gộp một số biểu diễn khác nhau nhưng trông/hoạt động gần nhau, ví dụ ký tự trình bày đặc biệt.
- Compatibility folding có thể **mất khác biệt quan trọng** ở một số domain.

Chọn `NFKC` không đồng nghĩa “luôn an toàn hơn NFC”. Với mã định danh, tên pháp lý hoặc dữ liệu phải giữ nguyên ký tự, cần phân biệt dữ liệu gốc và search-only representation.

### 14.2. Dùng icuNormalizer

```javascript
{
  type: "icuNormalizer",
  normalizationForm: "nfc"
}
```

Lựa chọn này khác `asciiFolding`: NFC **không có nghĩa** bỏ dấu tiếng Việt. Nếu muốn người dùng gõ không dấu vẫn tìm thấy có dấu, cần chiến lược accent folding/dữ liệu search riêng.

---

## 15. Chữ hoa, chữ thường và dấu tiếng Việt

Ba yêu cầu có thể khác nhau:

1. `"MÁY"` và `"máy"` được coi là giống nhau về **case**.
2. `"máy"` và `"may"` được coi là tương đương để **tìm kiếm không dấu**.
3. `"má"`, `"mã"`, `"mạ"` được **phân biệt** khi cần nghĩa chính xác.

Ba yêu cầu không thể giải quyết hoàn hảo bằng một filter folding duy nhất trong mọi bài toán.

### 15.1. Lowercase chỉ xử lý case

```text
"MÁY" -> "máy"
"máy" != "may" nếu chưa bỏ dấu.
```

### 15.2. Accent folding mở rộng recall nhưng giảm precision

`asciiFolding` hoặc `icuFolding` có thể giúp khớp một số ký tự Latin có dấu với dạng không dấu.

```text
"nước" -> dạng được fold gần "nuoc"
"máy"  -> dạng được fold gần "may"
```

**Không đảm bảo** mọi ký tự tiếng Việt đều chuyển theo kỳ vọng; đặc biệt `đ`/`Đ` có behavior cần kiểm tra thực tế theo tokenizer/filter. Nếu domain yêu cầu chắc chắn `"đường"` tìm bằng `"duong"`, hãy đưa ca này vào test và có thể cần quy tắc/transliteration riêng được thiết kế ở ingestion.

### 15.3. Mất dấu có thể gây sai nghĩa

```text
"ma"  có thể tương ứng:
"ma", "má", "mà", "mả", "mã", "mạ"
```

Nếu cứ fold và ranking tất cả như nhau, tìm `"mã sản phẩm"` có thể trả các nội dung chứa từ khác gây nhiễu.

Giải pháp thường là **dual-field/alternate analyzer**:

- Analyzer giữ dấu phục vụ **precision**.
- Analyzer folded phục vụ **recall** cho query không dấu.
- Boost kết quả khớp bản giữ dấu cao hơn bản folded.
- Có test relevance bằng query thật thay vì chỉ đếm số matches.

---

## 16. Custom analyzer hoàn chỉnh: ví dụ Unicode và tiếng Việt

Ví dụ custom analyzer `viFold`:

```javascript
const viFoldDefinition = {
  mappings: {
    dynamic: false,
    fields: {
      title: {
        type: "string",
        analyzer: "viFold",
        searchAnalyzer: "viFold"
      },
      description: {
        type: "string",
        analyzer: "viFold",
        searchAnalyzer: "viFold"
      }
    }
  },
  analyzers: [
    {
      name: "viFold",
      charFilters: [],
      tokenizer: {
        type: "standard"
      },
      tokenFilters: [
        {
          type: "icuNormalizer",
          normalizationForm: "nfc"
        },
        {
          type: "lowercase"
        },
        {
          type: "asciiFolding",
          originalTokens: "omit"
        }
      ]
    }
  ]
};

db.getSiblingDB("search_lab")
  .searchLesson305
  .createSearchIndex(
    "catalog_folded_v1",
    viFoldDefinition
  );
```

**Ý đồ cấu hình:**

- Chỉ index `title` và `description`.
- Chuẩn hóa Unicode NFC.
- Lowercase.
- Fold một số ký tự có dấu sang ASCII.
- Dùng cùng analyzer khi index và query để giảm mismatch.

**Đây không phải “bộ tách từ tiếng Việt hoàn chỉnh”.** Standard tokenizer vẫn không tự hiểu tất cả từ ghép tiếng Việt; `asciiFolding` không bảo đảm mọi transliteration mong muốn. Phải test query corpus của ứng dụng.

### 16.1. Query với index riêng

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_folded_v1",
        text: {
          query: "may loc nuoc",
          path: "title"
        }
      }
    },
    { $limit: 10 },
    {
      $project: {
        _id: 1,
        title: 1,
        score: { $meta: "searchScore" }
      }
    }
  ]);
```

Vì analyzer được áp dụng **cả khi index và query**, những terms đã fold có thể khớp dù người dùng gõ không dấu. Không khẳng định mọi cụm tiếng Việt và tên riêng đều khớp chính xác nếu chưa chạy thử trên server.

### 16.2. Điểm yếu của folded-only index

Nếu index chỉ lưu forms đã fold, nhiều từ khác nhau có thể hợp nhất một term. Search engine lúc đó không còn tín hiệu đủ tốt để ưu tiên bản có dấu đúng chỉ dựa vào field ấy. Với hệ thống có yêu cầu ranking cao, nên kết hợp bản gốc và bản folded.

---

## 17. Multi analyzer: giữ nhiều cách phân tích trên cùng string field

MongoDB Search có tùy chọn **`multi`** cho field kiểu `string`: index một field bằng analyzer chính và các analyzer **thay thế có tên**.

Ví dụ index `title` đồng thời theo:

- `lucene.standard`: giữ cách tìm kiếm thông thường.
- `viFold`: bản folded để mở rộng recall.
- `lucene.keyword`: giữ cả chuỗi để một số trường hợp exact-token search.

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .createSearchIndex(
    "catalog_multi_v1",
    {
      mappings: {
        dynamic: false,
        fields: {
          title: {
            type: "string",
            analyzer: "lucene.standard",
            multi: {
              folded: {
                type: "string",
                analyzer: "viFold",
                searchAnalyzer: "viFold"
              },
              whole: {
                type: "string",
                analyzer: "lucene.keyword"
              }
            }
          },
          tenantId: { type: "token" },
          status: { type: "token" }
        }
      },
      analyzers: [
        {
          name: "viFold",
          charFilters: [],
          tokenizer: { type: "standard" },
          tokenFilters: [
            { type: "icuNormalizer", normalizationForm: "nfc" },
            { type: "lowercase" },
            { type: "asciiFolding", originalTokens: "omit" }
          ]
        }
      ]
    }
  );
```

### 17.1. Query alternate analyzer bằng multi path

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_multi_v1",
        text: {
          query: "may loc nuoc",
          path: {
            value: "title",
            multi: "folded"
          }
        }
      }
    },
    { $limit: 10 },
    { $project: { title: 1, score: { $meta: "searchScore" } } }
  ]);
```

`path: { value:"title", multi:"folded" }` chỉ rõ alternate analyzer subpath trong index. Việc có `multi` **không tạo thêm field `title.folded` trong document nguồn**; đây là cách index Search biểu diễn dữ liệu.

### 17.2. Giới hạn của multi

- Chỉ dùng trên những field types được hỗ trợ, trọng tâm là `string`.
- Không được lồng nhiều tầng `multi` vào nhau.
- Càng nhiều alternate analyzer, index lớn hơn và chi phí indexing tăng.
- Không tự chọn bản tốt nhất cho một query nếu chưa cấu hình query/boost.

### 17.3. Tại sao không dùng regex thay multi?

Một regex chạy trên text gốc không tự tạo relevance/stop words/folding và có thể rất tốn kém với dữ liệu lớn. Multi analyzer giúp phân tích chủ động trong index để phục vụ những kiểu truy vấn khác nhau.

---

## 18. Boost kết quả khớp bản gốc so với bản không dấu

Nếu dùng `catalog_multi_v1`, có thể kết hợp hai đường tìm bằng `compound.should`:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_multi_v1",
        compound: {
          should: [
            {
              text: {
                query: "máy lọc nước",
                path: "title",
                score: {
                  boost: {
                    value: 3
                  }
                }
              }
            },
            {
              text: {
                query: "máy lọc nước",
                path: {
                  value: "title",
                  multi: "folded"
                }
              }
            }
          ],
          minimumShouldMatch: 1,
          filter: [
            {
              equals: {
                path: "tenantId",
                value: "T1"
              }
            },
            {
              equals: {
                path: "status",
                value: "ACTIVE"
              }
            }
          ]
        }
      }
    },
    { $limit: 10 },
    {
      $project: {
        title: 1,
        tenantId: 1,
        score: { $meta: "searchScore" }
      }
    }
  ]);
```

Ý nghĩa:

- Bản `title` với analyzer mặc định có boost 3 trong ví dụ.
- Bản `folded` mở rộng khả năng tìm không dấu.
- `minimumShouldMatch: 1` cho phép khớp ít nhất một nhánh.
- `compound.filter` giới hạn kết quả theo tenant và status; filter không phải cách boost score.

**Đây là chiến lược relevance cần tune**, không phải hệ số 3 luôn tối ưu. Hãy đo trên bộ queries thật và cân nhắc BM25, length normalization, token overlap.

### 18.1. Không dựa vào relevance score để bảo vệ tenant

Nếu thiếu filter tenant ở Search, dữ liệu có thể xuất hiện sai phạm vi, dù layer sau cố lọc. Security authorization phải đặt ở đường query/data access phù hợp và được test. `boost` là xếp hạng, **không phải ACL**.

---

## 19. String analyzer khác token normalizer

Đây là khác biệt dễ nhầm:

| Thuật ngữ | Dùng ở đâu? | Số token | Mục tiêu |
| --- | --- | --- | --- |
| `analyzer` | Field kiểu `string` | Có thể nhiều | Full-text và ranking |
| `tokenizer` | Thành phần của custom analyzer | Tách text thành tokens | Quy tắc word boundaries |
| `token filter` | Sau tokenizer | Có thể biến đổi/sinh nhiều tokens | Lowercase, folding, n-gram, stemming |
| **`normalizer`** | Field kiểu **`token`** | Một token cho cả chuỗi | So sánh exact/equality/sort/facet theo dạng chuẩn hóa |

Theo MongoDB Search, `token` hiện hỗ trợ normalizer:

- `none` (mặc định): giữ nguyên chuỗi.
- `lowercase`: chuyển cả token thành chữ thường.

**Không được chỉ định arbitrary custom analyzer của `string` làm `normalizer` của `token`.** Đây là hai cơ chế cấu hình khác nhau.

### 19.1. SKU nên là token

```javascript
{
  mappings: {
    dynamic: false,
    fields: {
      sku: {
        type: "token",
        normalizer: "none"
      }
    }
  }
}
```

Một SKU `"AB-100-X"` được giữ như một token; không tự split thành `ab`, `100`, `x` như một số analyzers văn xuôi.

### 19.2. Brand có thể dùng lowercase normalizer

```javascript
{
  brand: {
    type: "token",
    normalizer: "lowercase"
  }
}
```

Giúp case-insensitive equality theo semantics của normalizer, nhưng **không đồng nghĩa bỏ dấu hay stemming**.

### 19.3. Query kiểu token dùng equals/in/range

Ví dụ index `catalog_text_v1` có `brand` kiểu `token`:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_text_v1",
        equals: {
          path: "brand",
          value: "AquaHome"
        }
      }
    },
    { $project: { title: 1, brand: 1 } }
  ]);
```

Nếu muốn query text như `"aqua home"` theo từ rời, cần index field ấy **cũng như `string`** hoặc có bản text field riêng; chỉ `token` không tạo full-text terms.

---

## 20. Một string field có thể cần nhiều field types

Một tên sản phẩm có nhiều nhu cầu:

- Tìm theo từng từ và mô tả: `string`.
- Sort theo title không phân biệt chữ hoa/thường: `token` với `lowercase`.
- Gợi ý khi gõ: `autocomplete`.

MongoDB Search hỗ trợ index một field theo nhiều type definitions trong mapping theo cú pháp tương ứng, ví dụ:

```javascript
{
  mappings: {
    dynamic: false,
    fields: {
      title: [
        {
          type: "string",
          analyzer: "lucene.standard"
        },
        {
          type: "token",
          normalizer: "lowercase"
        }
      ]
    }
  }
}
```

Không phải `string` tự hỗ trợ mọi operator của `token`. Nếu cần equals, facet hoặc string sort thì theo tài liệu hiện đại nên dùng field `token` thay vì phụ thuộc kiểu `stringFacet` cũ.

**Giới hạn:** mỗi type/analyzer thêm chi phí lưu trữ và indexing. Chỉ định nghĩa những loại thật sự được dùng.

---

## 21. Autocomplete không tự có chỉ vì đã bật Search

Autocomplete là một yêu cầu khác full-text search.

Ví dụ:

```text
User nhập: "wire"
Gợi ý:    "Wireless Mouse"
```

Một index text chuẩn chỉ tạo tokens như `wireless`, `mouse`; query `wire` không tự là token `wireless`.

MongoDB Search có **field type `autocomplete`** và operator `autocomplete`:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .createSearchIndex(
    "catalog_autocomplete_v1",
    {
      mappings: {
        dynamic: false,
        fields: {
          title: {
            type: "autocomplete",
            tokenization: "edgeGram",
            minGrams: 2,
            maxGrams: 15,
            foldDiacritics: true
          }
        }
      }
    }
  );
```

Sau khi index `READY`:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_autocomplete_v1",
        autocomplete: {
          query: "wire",
          path: "title"
        }
      }
    },
    { $limit: 10 },
    { $project: { _id: 1, title: 1 } }
  ]);
```

### 21.1. Ba chiến lược n-gram

| Tokenization | Ý nghĩa | Use case |
| --- | --- | --- |
| `edgeGram` | Prefix của token | Gõ từ đầu |
| `rightEdgeGram` | Suffix của token | Gõ phần cuối |
| `nGram` | Chuỗi con của token | Match substring trong token |

Ví dụ token `"water"` với grams từ 2 đến 4, ở mức khái niệm:

```text
edgeGram  -> "wa", "wat", "wate"
nGram     -> "wa", "at", "te", "er", "wat", "ate", ...
```

Không coi ví dụ này là mô phỏng tất cả tokenizers/normalizers; tập tokens chính xác phụ thuộc cấu hình Search.

### 21.2. Tại sao không dùng minGrams=1 bừa bãi?

N-grams ngắn sinh rất nhiều terms, giảm độ chọn lọc và tăng index size/query cost. Tài liệu khuyến nghị cân nhắc `minGrams` tương đối lớn ở một số chiến lược. Chọn theo UX, ngôn ngữ và độ dài từ của dữ liệu.

### 21.3. Autocomplete và full-text nên được đo riêng

Autocomplete thường ưu tiên response nhanh cho input đang gõ, còn full-text có thể chú trọng relevance với truy vấn đã hoàn tất. Không nên cho mọi request vào autocomplete index chỉ vì nó match nhiều substring.

---

## 22. Fuzzy matching khác normalization

Người dùng gõ sai:

```text
"wireles"  thay vì "wireless"
```

Fuzzy search dựa vào **edit distance** để xét các từ gần giống, không phải chỉ lowercase hoặc bỏ dấu.

Ví dụ:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_text_v1",
        text: {
          query: "wireles",
          path: "title",
          fuzzy: {
            maxEdits: 1,
            prefixLength: 2,
            maxExpansions: 50
          }
        }
      }
    },
    { $limit: 10 },
    { $project: { title: 1, score: { $meta: "searchScore" } } }
  ]);
```

Ý nghĩa:

- `maxEdits` giới hạn số edits để tìm từ gần giống.
- `prefixLength` yêu cầu phần đầu token được giữ ổn định theo quy tắc fuzzy.
- `maxExpansions` giới hạn số terms mở rộng được xét.

Fuzzy không phải transliteration tiếng Việt: lỗi gõ thiếu dấu có thể gồm nhiều code points; fuzzy `maxEdits:1` không tự đảm bảo match mọi từ không dấu.

### 22.1. Fuzzy có thể tăng false positives

Nếu quá rộng, query tên sản phẩm ngắn có thể match nhiều từ khác nghĩa, tăng CPU, latency và độ nhiễu. Cần giới hạn trên những fields cần thiết, đo precision và có fallback strategy.

---

## 23. Phrase query và vị trí token

Full-text thường match những từ xuất hiện ở nhiều vị trí. Khi người dùng muốn một **cụm** từ theo thứ tự, dùng operator `phrase`:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_text_v1",
        phrase: {
          query: "water filter",
          path: "title",
          slop: 0
        }
      }
    },
    { $project: { title: 1, score: { $meta: "searchScore" } } }
  ]);
```

`phrase` kiểm tra **trật tự và vị trí tokens**, không mặc định so nguyên chuỗi byte-for-byte như một SQL equality predicate. Tokenizer có thể bỏ punctuation/stop words hoặc thay đổi positions tùy analyzer.

### 23.1. IndexOptions

MongoDB Search `string` field có thể cấu hình:

- `docs`: chỉ lưu thông tin document chứa term.
- `freqs`: thêm term frequency.
- `positions`: thêm vị trí term; cần cho phrase và các operator tương ứng.
- `offsets`: thêm character offsets; cần cho highlight.

Mặc định thường là `offsets`. Giảm thông tin lưu có thể tiết kiệm index storage, nhưng **có thể làm phrase/highlight không dùng được**. Hãy chọn theo use case thay vì giảm size mù quáng.

---

## 24. Highlighting dựa vào index offsets

Nếu muốn đánh dấu phần khớp để hiển thị trên UI:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .aggregate([
    {
      $search: {
        index: "catalog_text_v1",
        text: {
          query: "water",
          path: "title"
        },
        highlight: {
          path: "title"
        }
      }
    },
    { $limit: 5 },
    {
      $project: {
        title: 1,
        score: { $meta: "searchScore" },
        highlights: { $meta: "searchHighlights" }
      }
    }
  ]);
```

Kết quả highlight gồm thông tin các đoạn `hit`/`text` để UI dựng đoạn nhấn mạnh.

**Bảo mật UI:** không ghép nội dung document chưa escape vào HTML tùy ý chỉ vì highlight. Highlight là metadata search, không thay XSS protection.

### 24.1. Vì sao highlight không hiện?

Một số nguyên nhân:

- Field không được index kiểu `string` với offsets phù hợp.
- Search path và highlight path khác nhau.
- Analyzer đã biến đổi token khiến vị trí hiển thị khó suy luận.
- Document không khớp field được yêu cầu highlight.

---

## 25. Synonyms khác stemming và token filters

Một từ có nhiều cách gọi:

```text
"tv" / "television"
"laptop" / "notebook computer"
"điện thoại" / "smartphone"
```

**Synonym mappings** có thể giúp mở rộng các truy vấn theo từ/cụm tương đương, khác với:

- Lowercase: `TV` → `tv`.
- Accent folding: `máy` → dạng không dấu.
- Stemming: `running` → một stem liên quan.
- Fuzzy: `laptpo` gần `laptop` qua edits.

MongoDB Search cho phép khai báo synonym mapping trong Search index và dùng `text.synonyms` khi query, với source collection chứa các từ đồng nghĩa.

### 25.1. Các điểm cần lưu ý

- Synonym dictionary cần cập nhật và kiểm soát chất lượng.
- Synonym query có yêu cầu index options positions/offsets phù hợp.
- Theo tài liệu Search, **không dùng `fuzzy` cùng `synonyms` trong cùng `text` operator**.
- Nên khai báo `matchCriteria` khi dùng synonyms theo khuyến nghị của MongoDB.
- Không mặc định mọi cặp có vẻ giống nghĩa đều thay thế được trong tên sản phẩm/địa chỉ.

Ví dụ `"apple"` có thể là hãng công nghệ hoặc quả táo; synonym không có context có thể gây noise.

---

## 26. Chuẩn hóa trước khi lưu hay tại analyzer?

Có hai chiến lược chính:

### 26.1. Giữ nguyên text nguồn, analyzer xử lý cho Search

```javascript
{
  title: "Máy lọc nước"
}
```

Khi lập Search index, custom analyzer tạo forms thích hợp.

Ưu điểm:

- Dữ liệu nguồn không mất dấu/nguyên bản.
- Có thể có nhiều alternate analyzers.
- Đổi chiến lược Search bằng cập nhật index definition/rebuild thay vì sửa document nghiệp vụ.

Giới hạn:

- Analyzer built-in/custom chưa chắc hỗ trợ toàn bộ phân từ tiếng Việt.
- Some normalization requirements có thể không biểu diễn được bằng filter có sẵn.

### 26.2. Thêm field tìm kiếm được chuẩn hóa ở ingestion

```javascript
{
  title: "Bất động sản",
  titleSearch: "bat dong san"
}
```

Ưu điểm:

- Ứng dụng có thể dùng thuật toán transliteration/word segmentation riêng.
- Dễ kiểm soát quy tắc domain, ví dụ thay `đ` thành `d` đúng policy.

Rủi ro:

- Có thêm dữ liệu phải đồng bộ.
- Có thể làm mất phân biệt dấu/ngữ nghĩa.
- Cần migration/rebuild khi thay normalization algorithm.
- Nếu `title` đổi mà `titleSearch` không đổi, search bị stale về mặt dữ liệu.

**Khuyến nghị:** giữ field gốc làm source of truth, chuẩn hóa vào **Search index hoặc field phụ rõ version**, không ghi đè văn bản hiển thị.

---

## 27. Thiết kế riêng cho tiếng Việt

### 27.1. Bài toán dấu

Các query:

```text
"may loc nuoc"
"máy lọc nước"
"Máy Lọc Nước"
```

có thể cần cùng tìm một sản phẩm. Nhưng tìm:

```text
"ma"
"mã"
"má"
```

không phải lúc nào cũng nên coi hoàn toàn đồng nghĩa. Thay vì global accent folding không kiểm soát, dùng:

1. Search field giữ dấu.
2. Alternate folded search field.
3. Boost field giữ dấu.
4. Evaluation corpus có cả queries có dấu/không dấu.
5. Business tests cho tên riêng, địa chỉ và mã sản phẩm.

### 27.2. Bài toán từ ghép

```text
"bất động sản"
"công nghệ thông tin"
"máy học"
```

Whitespace tokenizer tạo tokens theo khoảng trắng, còn semantic word segmentation tiếng Việt có thể muốn xem cả cụm nhiều âm tiết là một từ/cụm. Đừng nói `lucene.standard` tự hiểu mọi cụm này.

Những lựa chọn:

- Search theo tokens thông thường và dùng `phrase` cho cụm.
- Index thêm shingle/ngram có kiểm soát, nếu truy vấn phù hợp.
- Chuẩn hóa/phân từ tiếng Việt ở pipeline bên ngoài, index vào field riêng.
- Dùng hybrid/vector search nếu use case yêu cầu gần nghĩa, nhưng phải tách khỏi semantics của lexical Search.

### 27.3. Bài toán mã và tên thương hiệu

Không nên áp analyzers ngôn ngữ tự nhiên lên:

- SKU/serial numbers.
- Mã hợp đồng.
- Mã tòa nhà.
- Email/phone normalized fields.
- ID đơn hàng.

Ví dụ `"AB-123"` nếu bị split thành `ab` và `123` có thể làm query mã sai. Field `token` hoặc field đã chuẩn hóa nghiệp vụ phù hợp hơn.

### 27.4. Kiểm thử kí tự đặc biệt

Corpus nên có:

```text
Đường, đường, duong
Hòa, Hoà, hoa
máy, may, mã, ma
C++, C#, Node.js
USB-C, USB C
AB-123, AB123
iPhone 15 Pro
Trần, Tran
¼, 1/4
```

Mục tiêu là đánh giá tokenization, Unicode normalization, accent folding và false matches với dữ liệu thật, không chỉ chọn analyzer dựa trên một ví dụ đẹp.

---

## 28. Tìm hiểu tokens trước khi tune relevance

Khi một query không tìm được document mà con người thấy “rõ là phải tìm ra”, điều quan trọng nhất không phải tăng fuzzy vô hạn mà là kiểm tra:

1. Text nguồn thực sự lưu là gì?
2. Field được index kiểu nào?
3. Index analyzer dùng gì?
4. Search analyzer dùng gì?
5. Document sinh những tokens nào?
6. Query sinh những tokens nào?
7. Có filter tenant/status hoặc field path sai không?
8. Index đã READY và đồng bộ đủ chưa?

### 28.1. Ví dụ mismatch

```text
Document:
  "AB-123-X"

Index analyzer keyword:
  ["AB-123-X"]

Query analyzer standard:
  ["ab", "123", "x"]

Kết quả:
  các terms có thể không tương ứng.
```

Muốn exact SKU: dùng `token` + `equals`, không dùng `text` trên văn bản được split.

### 28.2. Sử dụng công cụ xem text analysis

Trong MongoDB Atlas Search Index editor có **View text analysis** giúp xem tokens ở phía index/query theo cấu hình analyzer. Với self-managed, tham khảo các công cụ/diagnostics được hỗ trợ của môi trường đó; không dựa vào một method shell tự chế chưa được MongoDB công bố.

### 28.3. Ghi lại testcase thành fixture

```text
Input document: "Máy lọc nước"
Input query:    "may loc nuoc"

Index expected:
  candidate P001 phải có cơ hội khớp folded.

Query: "mã sản phẩm"
Expected:
  không được gây quá nhiều matches cho "ma".
```

Không test chỉ “API HTTP trả 200”; cần kiểm tra ranking, false positives, false negatives và đa ngôn ngữ.

---

## 29. Nhiều loại truy vấn trên cùng một ứng dụng

Một app thương mại điện tử có thể chia đường query:

| Route | Yêu cầu | Index/Query |
| --- | --- | --- |
| `GET /products/{sku}` | Exact lookup | B-tree index trên SKU hoặc Search `token + equals` |
| `GET /search?q=...` | Full-text | `string` analyzer + `$search.text` |
| `GET /suggest?q=...` | Gợi ý prefix | `autocomplete` field/operator |
| `GET /search?q=...&brand=...` | Text + filter | `compound.must/filter` |
| `GET /search?sort=brand` | Sort theo chuỗi | `token` type/normalizer phù hợp |
| `GET /reports/category` | Facet | `token` field + `$searchMeta`/facet |
| Tìm nội dung có cùng nghĩa | Semantic search | Vector/hybrid architecture riêng |

### 29.1. Đừng làm mọi bài toán bằng text matching

Trong một hệ thống có SKU, tenantId và status, exact match/filter nên có **kiểu index và operator chính xác**; không dùng fuzzy cho ID vì một ký tự khác có thể chỉ tới sản phẩm khác.

### 29.2. Sự khác biệt giữa lexical và semantic search

Lexical Search dựa trên terms/tokens/ngôn ngữ và ranking. Vector Search dùng embeddings nhằm tìm nội dung gần nhau về ngữ nghĩa. Cả hai có thể kết hợp ở tầng query, nhưng **normalizer** và **tokenizer** của Search index không tự tạo semantic understanding.

---

## 30. Java MongoDB Sync Driver: thực thi $search

Java Sync Driver cho phép dùng aggregation pipeline. Ví dụ dùng BSON `Document` để không phụ thuộc vào một DSL Search builder cụ thể:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

public final class ProductSearchRepository {

    public static void search(
            MongoCollection<Document> products,
            String userQuery
    ) {
        if (userQuery == null ||
            userQuery.isBlank() ||
            userQuery.length() > 200) {
            throw new IllegalArgumentException(
                "Invalid search query"
            );
        }

        Document searchStage = new Document(
            "$search",
            new Document("index", "catalog_text_v1")
                .append(
                    "text",
                    new Document("query", userQuery)
                        .append(
                            "path",
                            Arrays.asList(
                                "title",
                                "description"
                            )
                        )
                )
        );

        List<Document> pipeline = Arrays.asList(
            searchStage,
            new Document("$limit", 20),
            new Document(
                "$project",
                new Document("_id", 1)
                    .append("title", 1)
                    .append("brand", 1)
                    .append(
                        "score",
                        new Document(
                            "$meta",
                            "searchScore"
                        )
                    )
            )
        );

        products.aggregate(pipeline).forEach(
            document ->
                System.out.println(document.toJson())
        );
    }
}
```

Điểm cần nhớ:

- MongoCollection phải trỏ tới collection có Search index tên `catalog_text_v1`.
- MongoDB deployment phải hỗ trợ Search/`mongot`.
- Đưa query text làm **BSON value**, không tự ghép JSON string có dữ liệu người dùng.
- Kiểm tra input length và empty query; thêm auth/tenant filter trong ứng dụng thật.
- `$search` là stage đầu tiên; có thể bổ sung limit, projection, pagination, sort phù hợp sau đó.

### 30.1. Tại sao không dùng Java String.hashCode hay Regex?

Search tokenization/index không dùng Java String.hashCode để tạo terms. Regex Java cũng không tự có BM25, analyzer hay autocomplete. Driver gửi lệnh Search; server và mongot chịu trách nhiệm matching/ranking.

---

## 31. Java: Search với tenant filter tường minh

Cho một SaaS multi-tenant, không được tìm toàn bộ catalog rồi **chỉ lọc tenant sau khi đã trả dữ liệu**.

Ví dụ `compound`:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

public final class TenantCatalogSearch {

    public static void search(
            MongoCollection<Document> products,
            String tenantId,
            String keyword
    ) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant");
        }
        if (keyword == null || keyword.isBlank()) {
            throw new IllegalArgumentException("Empty query");
        }

        Document textQuery = new Document(
            "text",
            new Document("query", keyword)
                .append("path", "title")
        );

        Document tenantFilter = new Document(
            "equals",
            new Document("path", "tenantId")
                .append("value", tenantId)
        );

        Document statusFilter = new Document(
            "equals",
            new Document("path", "status")
                .append("value", "ACTIVE")
        );

        Document compound = new Document(
            "must",
            Arrays.asList(textQuery)
        ).append(
            "filter",
            Arrays.asList(
                tenantFilter,
                statusFilter
            )
        );

        List<Document> pipeline = Arrays.asList(
            new Document(
                "$search",
                new Document("index", "catalog_text_v1")
                    .append(
                        "compound",
                        compound
                    )
            ),
            new Document("$limit", 20),
            new Document(
                "$project",
                new Document("title", 1)
                    .append("status", 1)
                    .append("tenantId", 1)
                    .append(
                        "score",
                        new Document("$meta", "searchScore")
                    )
            )
        );

        products.aggregate(pipeline).forEach(
            result -> System.out.println(result.toJson())
        );
    }
}
```

Trong production, `tenantId` phải đến từ **authenticated context**, không phải một query parameter mà người dùng tự chọn.

### 31.1. Filter không làm mất relevance

`compound.filter` áp điều kiện match mà không tạo thêm relevance score. Điều này thuận tiện để kết hợp “tìm text phù hợp nhất” và “chỉ các document được phép”.

### 31.2. Query có thể cần index thêm metadata

Nếu Search index chỉ có `title` kiểu string mà không có `tenantId`/`status` kiểu token, `equals` filter có thể báo field/index mapping không phù hợp. Trước khi viết code phải thiết kế mapping cùng query.

---

## 32. Search score: thứ hạng không phải tỷ lệ tin cậy

MongoDB Search dùng các cơ chế scoring như BM25 tùy loại query và cấu hình. `searchScore`:

- Dùng để **xếp hạng tương đối các hits**.
- Phụ thuộc term statistics, field length, frequency và nhiều yếu tố khác.
- Không mặc định nằm từ 0 đến 1.
- Không phải xác suất “document đúng 93%”.
- Có thể thay đổi khi corpus, Search index, analyzer hoặc cách triển khai thay đổi.

Ví dụ:

```javascript
{
  $project: {
    _id: 1,
    title: 1,
    relevance: { $meta: "searchScore" }
  }
}
```

### 32.1. Có nên dùng score threshold cố định?

Một threshold như `score >= 5` có thể hoạt động trên dataset hiện tại nhưng không tự giữ ý nghĩa khi có thêm 1 triệu documents hoặc chỉnh analyzer. Nếu cần threshold, đo distribution trên tập queries và version hóa relevance policy.

### 32.2. Ranking và pagination

Nếu dùng score để phân trang, phải có chiến lược ổn định/đúng Search pagination semantics. Khi search nodes khác nhau có term statistics thay đổi, thứ tự bằng score có thể dao động. Tài liệu MongoDB có những options scoring như `stableTfl`/`boolean` cho trường hợp cần tính ổn định hơn, nhưng đổi scoring có đánh đổi về ranking.

---

## 33. Fuzzy, synonyms, autocomplete và stemming: không trộn không kiểm soát

Ba chiến lược tăng recall đều có chi phí:

| Chiến lược | Nới match theo | Rủi ro |
| --- | --- | --- |
| Normalization/folding | Chữ hoa/dấu/các forms | Gộp từ khác nghĩa |
| Stemming | Biến thể từ/ngữ pháp | Gộp khác nghĩa, sai ngôn ngữ |
| Fuzzy | Ký tự gần giống qua edits | False positives và query expansions |
| Synonyms | Quan hệ từ/cụm theo từ điển | Đồng nghĩa sai ngữ cảnh |
| Autocomplete/ngram | Prefix/substring | Nhiều tokens, index lớn, nhiễu |

Đừng bật tất cả rồi cho là kết quả luôn “thông minh” hơn. Hãy xác định use case:

- Người dùng gõ thiếu dấu? Folding.
- Người dùng gõ sai chính tả? Fuzzy.
- Người dùng gõ chưa hết từ? Autocomplete.
- Người dùng gõ cách gọi khác? Synonym mapping.
- Người dùng tìm từ biến thể tiếng Anh? Stemming theo đúng ngôn ngữ.

Có thể kết hợp, nhưng phải đánh giá interactions và giới hạn operator cụ thể.

---

## 34. Index size, hiệu năng và chi phí

Một index phân tích văn bản có thể lớn vì mỗi chuỗi sinh ra nhiều terms.

Ví dụ:

```text
"wireless"
  standard analyzer -> 1 token

"wireless"
  nGram 2..5         -> nhiều tokens

Index 1 triệu product titles:
  số terms/memory/storage khác đáng kể.
```

Các yếu tố tăng chi phí:

1. `dynamic: true` index quá nhiều field.
2. Nhiều multi analyzers cho cùng field.
3. N-gram/edgeGram có `minGrams` quá nhỏ.
4. Lưu positions/offsets không cần thiết.
5. Index trên mô tả rất dài hoặc HTML chưa strip.
6. Synonym dictionary và analyzer phức tạp.
7. Fuzzy expansions quá rộng.
8. Số lượng search indexes trùng chức năng.
9. Nhiều updates làm `mongot` phải reindex.
10. Query không có tenant/status filters hoặc path quá rộng.

### 34.1. Lưu ý chiều dài token

MongoDB Search có giới hạn độ dài token ở field `string`: tokens vượt **32.766 bytes** không được index theo behavior của tài liệu. Analyzer `keyword` giữ toàn chuỗi thành một token nên đặc biệt dễ gặp giới hạn với field quá dài.

Kiểu `token` cũng có xử lý giới hạn chiều dài riêng (MongoDB Search nêu có thể truncate những string vượt **8.181 ký tự** trước khi index). Không dùng `token` cho hàng trăm KB văn bản và kỳ vọng exact match đầy đủ.

### 34.2. Không dùng Search index làm primary-key lookup mặc định

Một query chỉ cần `_id` hoặc unique `sku` mà MongoDB đã có B-tree index có thể đơn giản và nhất quán hơn. Search index có overhead riêng và index propagation lag, nên chọn dựa trên yêu cầu thực.

---

## 35. Cập nhật Search index và thay analyzer

Analyzer ảnh hưởng terms **được lưu trong index**. Đổi analyzer không chỉ thay cách query: phải xây lại biểu diễn tìm kiếm phù hợp.

Ví dụ:

```javascript
db.getSiblingDB("search_lab")
  .searchLesson305
  .updateSearchIndex(
    "catalog_text_v1",
    {
      mappings: {
        dynamic: false,
        fields: {
          title: {
            type: "string",
            analyzer: "lucene.simple"
          }
        }
      }
    }
  );
```

**Đoạn trên là ví dụ thao tác thay toàn definition được cung cấp**, không phải patch “chỉ sửa analyzer của title”. Nếu chạy lên index đang dùng có thể làm các field khác không còn được index như trước. Đừng sao chép mà không xem complete current definition.

### 35.1. Kế hoạch thay analyzer trong production

1. Ghi nhận index definition hiện hành.
2. Tạo một Search index **mới có tên khác** với analyzer mới nếu môi trường cho phép.
3. Chờ index mới tới trạng thái `READY`.
4. Chạy tập queries so sánh relevance và latency.
5. Chuyển traffic theo canary/feature flag.
6. Theo dõi indexing lag, false negatives/positives, errors.
7. Chỉ xóa index cũ sau khi có rollback plan.

Cách này giúp tránh đổi đồng thời index definition và application logic mà không có đường quay lại.

### 35.2. Không coi READY là mọi document đã read-your-writes

`READY` là trạng thái index có thể phục vụ. Search vẫn đồng bộ thay đổi bất đồng bộ; một update vừa commit có thể chưa xuất hiện tức thì. Nếu cần nhận biết độ trễ, giám sát Search indexing process và hành vi query thay vì chỉ status.

---

## 36. Sự khác nhau giữa case-insensitive exact và full-text

Giả sử:

```text
Stored brand: "AquaHome"
Query:        "aquahome"
```

Với `brand` kiểu `token` và `normalizer:"lowercase"`, exact equality có thể được xử lý không phân biệt hoa/thường theo chuẩn hóa.

Nhưng:

```text
Stored title: "Máy lọc nước mini"
Query:        "lọc"
```

đây là **full-text word retrieval**, nên dùng `string` + analyzer + `text` operator.

Ví dụ câu hỏi dễ nhầm:

| Yêu cầu | Nên dùng |
| --- | --- |
| Brand đúng giá trị, không phân biệt hoa/thường | `token + lowercase normalizer + equals` |
| Tên sản phẩm chứa từ được phân tích | `string + analyzer + text` |
| Tên sản phẩm đúng cả chuỗi đã normal hóa | `token` hoặc keyword analyzer với yêu cầu tương ứng |
| Tên sản phẩm có từ bắt đầu bằng vài ký tự | `autocomplete` |
| Tên sản phẩm có từ sai chính tả nhẹ | `text.fuzzy` |
| Truy vấn gần đúng về ngữ nghĩa | Vector/semantic retrieval nếu cần |

Không lẫn lộn `normalizer` và `analyzer`; cùng có thể lowercase nhưng các contract về tokens/operators khác nhau.

---

## 37. Lỗi triển khai và cách suy luận

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `$search` báo không có index | Index name sai hoặc chưa tạo/READY | `$listSearchIndexes`, tên index |
| MongoDB không hỗ trợ `$search` | Deployment thiếu mongot/Search hoặc không tương thích | Kiểm tra Atlas/self-managed Search setup |
| Search không thấy document vừa insert | Indexing lag | Giám sát đồng bộ Search, retry phù hợp |
| `text` không match SKU nguyên chuỗi | SKU bị token hóa sai hoặc chỉ index token | Dùng `token + equals` |
| Query không dấu không tìm thấy có dấu | Analyzer chưa fold | Thiết kế analyzer/multi folded, test tokens |
| Query `"đường"`/`"duong"` lệch | Unicode transliteration không đầy đủ | Test `đ`, custom normalization riêng |
| Query EN bị mất từ quan trọng | Stemming/stop words quá mạnh | Xem analyzer từng field |
| Query hoa/thường không match | `keyword`/`whitespace` giữ case | Lowercase/token normalizer |
| Phrase không hoạt động | `indexOptions` thiếu positions hoặc analyzer khác | Kiểm tra field mapping |
| Highlight không xuất hiện | Thiếu offsets hoặc highlight path sai | Kiểm tra mapping/query |
| Autocomplete không có kết quả | Field chưa index `autocomplete` | Tạo đúng field type/index |
| Autocomplete quá nhiều nhiễu | `minGrams` nhỏ/nGram quá rộng | Tăng ngưỡng, điều chỉnh ranking |
| Fuzzy rất chậm | `maxExpansions` và scope lớn | Giới hạn path, expansions và latency |
| Brand filter không hoạt động | Field chưa index `token`/type sai | Kiểm tra mapping và `equals` |
| `$text` không dùng Search index | Hai cơ chế khác nhau | Dùng `$search` |
| `$search` không dùng B-tree `createIndex` | Search cần index riêng | Tạo Search index |
| Multi path báo lỗi | Path hoặc tên `multi` sai | So với definition |
| Relevance thay đổi sau deploy | Analyzer/score/corpus/index khác | So sánh corpus và score details |
| Search trả tenant khác | Thiếu filter/authorization | Thêm `compound.filter` và ACL |
| Search chậm khi có mô tả dài | Index/query quá rộng hoặc ngrams nhiều | Explain/monitor resources |
| Đổi analyzer nhưng results cũ | Rebuild chưa hoàn tất hoặc đang dùng index cũ | Kiểm tra trạng thái/index name |
| Keyword field dài không được index | Token length limit | Chia nội dung hoặc dùng analyzer phù hợp |
| Tiếng Việt tách âm tiết sai kỳ vọng | Standard không phải semantic segmenter Việt | Field phụ/pipeline ngôn ngữ |
| Token normalizer không nhận custom analyzer | `token` chỉ có normalizers được hỗ trợ | Dùng `string`/field alternate |

---

## 38. Bài tập vận dụng

### Bài 1 — Phân biệt index

Tạo:

```javascript
db.products.createIndex({ title: "text" });
```

**Hỏi:** Lệnh đó có tạo MongoDB Search index dùng cho `$search` không?

**Đáp án:** Không. Đó là legacy text index, dùng với `$text`. Search index tạo bằng API/công cụ Search riêng.

### Bài 2 — Thứ tự phân tích

Custom analyzer có `htmlStrip`, `standard` tokenizer và `lowercase`.

**Hỏi:** Thứ tự xử lý?

**Đáp án:** Character filter → tokenizer → token filter.

### Bài 3 — Giữ nguyên SKU

SKU `"AB-123-X"` cần so khớp đúng toàn bộ, không split.

**Đáp án:** Field `token` với normalizer phù hợp và `equals`; hoặc một thiết kế exact-match B-tree.

### Bài 4 — Không dấu tiếng Việt

User gõ `"may loc nuoc"`, dữ liệu `"Máy lọc nước"`.

**Đáp án:** Thiết kế folded analyzer/alternate field trên cả index và query, kèm test Vietnamese diacritics/`đ`.

### Bài 5 — Keyword analyzer

Field `"Wireless Mouse"` được index bằng `lucene.keyword` nhưng query `"mouse"`.

**Hỏi:** Có mặc định match như một từ riêng không?

**Đáp án:** Không. Keyword giữ cả chuỗi làm một token.

### Bài 6 — Whitespace và case

Index dùng `lucene.whitespace`, có `"HELLO world"`; query `"hello"`.

**Đáp án:** Whitespace giữ case, nên không thể mặc định coi `HELLO` và `hello` là một token. Cần lowercase filter/analyzer phù hợp.

### Bài 7 — Token normalizer

Muốn tìm `"AquaHome"` bằng `"aquahome"` trong brand và facet theo brand.

**Đáp án:** `token` với `normalizer: "lowercase"` là một lựa chọn phù hợp.

### Bài 8 — Token vs analyzer

Một field được index `token`. Developer muốn dùng `text` operator trên field để tìm một từ ở giữa.

**Đáp án:** Chỉ `token` không đủ; index field như `string` để dùng text/phrase operators.

### Bài 9 — Search index build

`createSearchIndex()` trả về thành công; query lập tức lỗi.

**Đáp án:** Build bất đồng bộ; kiểm tra `$listSearchIndexes` và `READY`.

### Bài 10 — Cùng một field, nhiều mục tiêu

`title` vừa cần full-text vừa cần case-insensitive sort.

**Đáp án:** Có thể index `title` kiểu `string` và `token` trong Search mapping theo nhu cầu.

### Bài 11 — Autocomplete

User gõ `"wire"` và muốn thấy `"Wireless Mouse"`.

**Đáp án:** Dùng field type `autocomplete` + autocomplete operator/edgeGram theo cấu hình, không mặc định chỉ `string` analyzer là đủ.

### Bài 12 — Fuzzy

User gõ `"wireles"` thay vì `"wireless"`.

**Đáp án:** `text.fuzzy` phù hợp, giới hạn `maxEdits`, `prefixLength` và `maxExpansions`.

### Bài 13 — Phrase và positions

Index field với `indexOptions: "docs"`. Team muốn phrase query.

**Đáp án:** Phrase cần term positions. Cần mapping hỗ trợ `positions` hoặc `offsets`.

### Bài 14 — Unicode

Hai chuỗi nhìn giống `"é"` nhưng một chuỗi ở dạng decomposed.

**Đáp án:** Có thể dùng `icuNormalizer` với NFC cho canonical equivalence; không đồng nghĩa accent stripping.

### Bài 15 — Stop words tiếng Việt

Team lọc mọi token một ký tự và loại từ `"c"`.

**Hỏi:** Tại sao nguy hiểm?

**Đáp án:** `C` có thể là ký hiệu kỹ thuật hoặc một phần product model (USB-C). Stopword/length filtering cần theo domain.

### Bài 16 — Ranking và dấu

Index folded-only; user tìm `"mã"` nhưng có nhiều document chứa `"ma"`.

**Đáp án:** Folding gộp khác biệt. Giữ một index alternate không fold và boost exact-accent path.

### Bài 17 — Tenant isolation

Query `$search.text` match sản phẩm của T1 và T2; ứng dụng chỉ được thấy T1.

**Đáp án:** Dùng `compound.filter` với tenantId lấy từ authenticated context và bảo đảm authorization.

### Bài 18 — Data freshness

User vừa cập nhật title rồi Search lập tức không thấy bản mới.

**Đáp án:** Search indexing có thể bất đồng bộ. Với read-after-write nghiêm ngặt, dùng dữ liệu nguồn/theo khóa phù hợp.

### Bài 19 — Chi phí nGram

Autocomplete dùng `minGrams:1` trên một triệu titles.

**Đáp án:** Terms nổ lớn, index/query cost tăng. Cần tune threshold và strategy.

### Bài 20 — Dynamic mapping

Production dùng `dynamic:true` trên documents chứa nhiều nested fields nhạy cảm không phục vụ tìm kiếm.

**Đáp án:** Nên dùng explicit mapping/field allowlist, tránh index dữ liệu ngoài mục tiêu và tăng chi phí.

### Bài 21 — Fuzzy và synonyms

Một `text` query khai báo cả fuzzy và synonyms.

**Đáp án:** Tài liệu không cho dùng đồng thời trong cùng text operator; cần điều chỉnh query design.

### Bài 22 — Phân từ tiếng Việt

Dữ liệu `"bất động sản"`, standard analyzer tạo tokens theo word breaks.

**Hỏi:** Nó có tự nhận `"bất_động_sản"` là một từ đúng nghĩa không?

**Đáp án:** Không được mặc định. Cần kiểm thử/analyzer hoặc preprocessing ngôn ngữ phù hợp.

### Bài 23 — Thay analyzer

Team đổi `lucene.standard` sang `viFold` rồi nghĩ chỉ query mới thay đổi.

**Đáp án:** Terms trong index cũng thay đổi; cần reindex/rebuild và quy trình rollout an toàn.

### Bài 24 — Search score

Hai kết quả có score 5.6 và 3.2.

**Hỏi:** Có thể khẳng định kết quả đầu “đúng 56%” không?

**Đáp án:** Không. Score phục vụ ranking theo thuật toán, không phải xác suất độ đúng.

---

## 39. Quy trình thiết kế Search cho hệ thống thực tế

### Bước 1 — Xác định contract của search

Viết rõ:

- Field nào được search?
- Có cần full-text hay exact?
- Có cần tiếng Việt không dấu?
- Có cần đa ngôn ngữ, từ ghép, phrase?
- Có autocomplete/fuzzy/synonyms?
- Có security filter tenant/status?
- Ranking/latency SLA thế nào?
- Có bắt buộc read-your-writes không?

### Bước 2 — Phân loại field

| Loại field | Ví dụ | Search type/analyzer |
| --- | --- | --- |
| Văn xuôi | `title`, `description` | `string` + analyzer |
| Exact identifier | `sku`, `contractCode` | `token` hoặc B-tree exact index |
| Facet/keyword | `brand`, `category` | `token` + normalizer |
| Prefix suggestion | `title` | `autocomplete` |
| Tenant/status | `tenantId`, `status` | `token` và compound filter |
| Vector semantic | `embedding` | Vector Search architecture riêng |

### Bước 3 — Chọn analyzer cho từng use case

1. Bắt đầu với `lucene.standard` nếu chưa có nhu cầu đặc biệt.
2. Thử lowercasing và Unicode normalization trên fixture.
3. Thêm folded analyzer cho tiếng Việt không dấu.
4. Giữ bản gốc để tăng precision.
5. Không ép ID hoặc SKU qua analyzer văn xuôi.
6. Chỉ thêm nGram/autocomplete khi có đường query cần.
7. Đánh giá từng lựa chọn trên corpus.

### Bước 4 — Triển khai index theo version

Dùng tên có version:

```text
catalog_text_v1
catalog_multi_v2
catalog_autocomplete_v1
```

Chờ READY, test trên staging, chuyển query theo canary nếu thay definition lớn.

### Bước 5 — Đo chất lượng tìm kiếm

Metrics:

- Precision@k: trong top k có bao nhiêu kết quả phù hợp.
- Recall@k: bao nhiêu kết quả đúng được tìm lại (khi có ground truth).
- MRR/NDCG nếu có bộ đánh giá xếp hạng.
- Zero-result rate theo query.
- p50/p95/p99 latency.
- Search indexing lag.
- Index size, Search CPU/memory, update throughput.
- Query expansion cost cho fuzzy/ngram.
- Tỷ lệ query không dấu/đổi case/typos.

### Bước 6 — Quản trị thay đổi

Khi đổi analyzer hay dữ liệu nguồn:

1. Version hóa config.
2. Xây index mới khi phù hợp.
3. Chạy regression tests.
4. Theo dõi câu query có ít hoặc không kết quả.
5. Có rollback index/query path.
6. Không thay đổi tokenizer và synonyms cùng lúc nếu không thể phân tích nguyên nhân.

---

## 40. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “`$text` index và Search index là một.” | Hai cơ chế khác nhau với APIs và kiến trúc khác. |
| “Search index là B-tree index thêm option analyzer.” | MongoDB Search dùng chỉ mục do `mongot` duy trì. |
| “MongoDB Search chỉ chạy Atlas.” | Đến 2026 có self-managed được hỗ trợ; cần triển khai `mongot` đúng. |
| “`createSearchIndex` trả success là query ngay được.” | Index build bất đồng bộ, cần READY. |
| “Search luôn read-your-writes.” | Có indexing lag. |
| “Analyzer là tokenizer.” | Analyzer gồm char filters, tokenizer và token filters. |
| “Custom analyzer chỉ cần token filters.” | Cần tokenizer; char/token filters có thể tùy chọn. |
| “Search analyzer không ảnh hưởng kết quả.” | Query tokens phải tương thích index tokens. |
| “Mọi analyzer đều lowercase.” | Keyword/whitespace built-in giữ case. |
| “Normalizer và analyzer giống nhau.” | `normalizer` dành cho `token`, tạo một token. |
| “Có `lucene.vietnamese` built-in.” | Không thấy trong danh sách MongoDB Search language analyzers 2026. |
| “Standard analyzer hiểu từ ghép tiếng Việt.” | Không được giả định semantic segmentation. |
| “Lowercase là bỏ dấu.” | Lowercase chỉ đổi case. |
| “NFC biến mọi từ thành không dấu.” | NFC là canonical normalization, không phải accent folding. |
| “Folding không mất ý nghĩa.” | Có thể gộp từ khác nhau như `ma`/`má`/`mã`. |
| “`asciiFolding` luôn biến `đ` thành `d`.” | Cần kiểm thử hoặc transliteration riêng. |
| “Stemming là synonyms.” | Stemming theo hình thái; synonyms theo từ điển quan hệ. |
| “Fuzzy sửa mọi lỗi gõ.” | Bị giới hạn edit distance và có false positives. |
| “Keyword analyzer tìm được từng từ con.” | Nó thường tạo một token cho cả chuỗi. |
| “Search string type tự facet/sort/exact tối ưu.” | Dùng `token` type cho các operator phù hợp. |
| “Một index full-text tự phục vụ autocomplete.” | Cần mapping/operator autocomplete thích hợp. |
| “`$search` luôn trả score như xác suất.” | Score để ranking, không phải xác suất. |
| “Có `limit` thì query chắc rẻ.” | Index, expansions và scanning vẫn quyết định cost. |
| “`dynamic:true` luôn tốt nhất production.” | Có thể index nhiều field không cần thiết. |
| “Search score thay quyền truy cập.” | Phải lọc/kiểm tra authorization theo tenant. |
| “Đổi analyzer không cần rebuild.” | Index terms phụ thuộc analyzer; cần rollout/reindex. |
| “Tokenizers xử lý mọi định dạng tiếng Việt tự nhiên.” | Cần corpus tests và có thể cần external processing. |
| “Regexp và `$search.text` tương đương.” | Khác logic tokenization, index và relevance. |
| “Một query match là đã đánh giá chất lượng Search.” | Cần đo precision/recall và p95/p99 trên workload. |

---

## 41. Checklist production

1. Deployment đã có MongoDB Search/`mongot` được hỗ trợ?
2. Search indexes có trạng thái `READY` và đang đồng bộ?
3. Phân biệt rõ Search index, legacy text index và B-tree index?
4. Mỗi field có Search type đúng use case?
5. Dynamic mapping có đang index nhiều field không cần thiết?
6. Index analyzer có được chọn có chủ đích?
7. Search analyzer có tương thích với terms ở index?
8. Custom analyzer có charFilters → tokenizer → tokenFilters đúng thứ tự?
9. SKU/IDs có tránh tokenization làm thay đổi định danh?
10. Token normalizer có dùng đúng `none`/`lowercase`?
11. Unicode NFC/NFKC có phù hợp domain?
12. Accent folding đã test cả `đ`, `Đ` và dấu tổ hợp?
13. Có test từ ghép tiếng Việt?
14. Có giữ bản chính xác khi bổ sung folded analyzer?
15. Có token/field hỗ trợ facet, exact filtering và sort?
16. Autocomplete có mapping/operator riêng và minGrams hợp lý?
17. Fuzzy có giới hạn edits/expansions, ngăn query quá rộng?
18. Phrase/highlight có indexOptions phù hợp?
19. Synonyms có từ điển, analyzer và matchCriteria rõ?
20. Query có filter tenant/status được bảo đảm ở tầng Search và authorization?
21. `$search` được đặt đúng vị trí trong aggregation?
22. Có limit, projection, timeout và pagination strategy?
23. Có đo searchScore/relevance bằng test corpus thay vì trực giác?
24. Có monitoring indexing lag, Search node resource và error rate?
25. Thay index/analyzer có version, staging tests, canary và rollback?
26. Có phân biệt lexical Search với semantic/vector Search?
27. Có chính sách không log nội dung nhạy cảm của query/document?
28. Có bộ test tiếng Việt có dấu/không dấu, từ viết tắt, SKU, typo?
29. Có giới hạn số lượng Search indexes và ngân sách lưu trữ?
30. Query kết quả ngay sau update có chịu được indexing lag không?

---

## 42. Tài liệu tham khảo MongoDB chính thức

- [MongoDB Search Overview](https://www.mongodb.com/docs/search/): tính năng, Search architecture và các operator.
- [Deployment Options](https://www.mongodb.com/docs/search/deployment/deployment-options/): Atlas và self-managed options.
- [Self-Managed Search](https://www.mongodb.com/docs/search/self-managed/current/): vai trò `mongot`, kết nối và quản trị.
- [Create a Search Index — `db.collection.createSearchIndex()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/): cú pháp và trạng thái build.
- [`$listSearchIndexes`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/listSearchIndexes/): trạng thái READY/BUILDING/STALE.
- [Search Index Definitions](https://www.mongodb.com/docs/search/indexes/index-definitions/): mappings, analyzer, searchAnalyzer và custom analyzers.
- [Process Data with Analyzers](https://www.mongodb.com/docs/search/indexes/analyzers/overview/): tổng quan analyzer/tokenizer/normalizers.
- [Custom Analyzers](https://www.mongodb.com/docs/search/indexes/analyzers/custom/): `charFilters`, `tokenizer`, `tokenFilters`.
- [Character Filters](https://www.mongodb.com/docs/search/indexes/analyzers/character-filters/): `htmlStrip`, `mapping`.
- [Token Filters](https://www.mongodb.com/docs/search/indexes/analyzers/token-filters/): lowercase, Unicode, folding, stemming, n-grams.
- [Built-in Language Analyzers](https://www.mongodb.com/docs/search/indexes/analyzers/language/): analyzers theo ngôn ngữ.
- [String Field Type](https://www.mongodb.com/docs/search/indexes/field-types/string-type/): analyzer, searchAnalyzer, multi, indexOptions.
- [Token Field Type](https://www.mongodb.com/docs/search/indexes/field-types/token-type/): exact/facet/sort và normalizer.
- [Multi Analyzer](https://www.mongodb.com/docs/search/indexes/analyzers/multi/): alternate analysis cho string fields.
- [Autocomplete Field Type](https://www.mongodb.com/docs/search/indexes/field-types/autocomplete-type/): edgeGram/nGram và cấu hình gợi ý.
- [`text` Search Operator](https://www.mongodb.com/docs/search/query/operators-collectors/text/): full-text, fuzzy và synonyms.
- [`autocomplete` Search Operator](https://www.mongodb.com/docs/search/query/operators-collectors/autocomplete/): query prefix/partial matches.
- [Score Details](https://www.mongodb.com/docs/search/query/score/get-details/): scoring và những yếu tố ảnh hưởng.
- [Unicode Normalization Forms](https://unicode.org/reports/tr15/): NFC/NFD/NFKC/NFKD.
- [Java MongoDB Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/): dựng và chạy pipeline qua Java.

Lưu ý: field types, Search node/`mongot` deployment và các phương thức index management tiếp tục phát triển giữa các phiên bản MongoDB. Luôn đối chiếu **server, driver, Atlas/self-managed, Search release và FCV** trước khi áp dụng ví dụ vào production.

## 43. Kết luận

**Search index** là hạ tầng chuyên biệt phục vụ lexical text search của MongoDB, độc lập với B-tree và legacy `$text` indexes. MongoDB Search xử lý query qua `$search`, với các operators text, phrase, fuzzy, autocomplete và khả năng scoring/filtering tương ứng. Trong deployment có hỗ trợ Search, chỉ mục được duy trì bởi `mongot` và có thể cập nhật bất đồng bộ.

**Analyzer** quy định chuỗi được biến thành terms thế nào; **tokenizer** quyết định ranh giới tokens; **character filters** chuẩn hóa trước khi tách; **token filters** biến đổi tokens sau khi tách. **Index analyzer** và **search analyzer** phải tạo ra những terms tương thích. Đối với các field exact-match/facet/sort, kiểu **`token` và normalizer** là cơ chế khác với full-text analyzer của `string`.

Với tiếng Việt, phân biệt **case folding**, **Unicode normalization**, **accent folding** và **word segmentation**. Bỏ dấu có thể tăng recall nhưng giảm precision, nên thường cần kết hợp bản giữ dấu và bản folded có weighting hợp lý. Mã sản phẩm, tên riêng và nhiều từ ghép cần được kiểm thử riêng.

**Thiết kế Search tốt không chỉ làm query “có kết quả”, mà còn đảm bảo đúng ngôn ngữ, đúng tenant, ranking hữu ích, độ trễ phù hợp và khả năng thay analyzer an toàn khi dữ liệu thay đổi.**
