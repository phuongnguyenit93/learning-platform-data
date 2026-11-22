# Chỉ mục đảo, tìm kiếm văn bản và cơ chế cập nhật

Một ứng dụng có hàng triệu bài viết, sản phẩm hoặc dịch vụ cần trả lời: “Tìm dịch vụ **sửa máy lạnh**, ưu tiên kết quả phù hợp nhất, chỉ hiển thị những dịch vụ còn hoạt động của đúng người dùng hoặc tenant”. Nếu mỗi truy vấn phải đọc toàn bộ document rồi dò chuỗi, chi phí CPU, I/O và độ trễ sẽ tăng theo số lượng dữ liệu.

**Chỉ mục đảo (inverted index)** là cấu trúc truy cập giúp tìm văn bản theo hướng ngược lại với việc đọc document: thay vì bắt đầu từ document để hỏi có chứa từ gì, chỉ mục bắt đầu từ **term** để tìm những document có chứa term đó.

Trong NoSQL, chỉ mục đảo không chỉ là một bài toán tìm từ khóa. Hệ thống còn cần:

- Phân tích văn bản thành term, lựa chọn analyzer cho từng ngôn ngữ.
- Tìm nhiều từ, cụm từ, từ có tiền tố và kết quả gần đúng.
- Đánh giá độ liên quan và sắp xếp top-k.
- Kết hợp điều kiện có cấu trúc như `tenantId`, `status` và khoảng giá.
- Cập nhật chỉ mục khi document được thêm, sửa, xóa hoặc đổi quyền.
- Phân biệt **ghi dữ liệu nguồn thành công** với **search index đã nhìn thấy phiên bản mới**.
- Phục hồi khi quá trình đồng bộ, index refresh hoặc rebuild gặp lỗi.

Bài học nằm trong chủ đề **Chỉ mục và đường truy cập** của **Database No SQL**. Ví dụ sử dụng MongoDB classic text search, các khái niệm chung của công cụ dựa trên Apache Lucene và kiến trúc search projection. Các chi tiết về API, analyzer, transaction và refresh phụ thuộc sản phẩm, phiên bản và cách triển khai.

## 1. Vì sao cần một đường truy cập riêng cho văn bản?

Giả sử có ba tài liệu:

| Document | Nội dung |
|---|---|
| D1 | “máy lạnh tiết kiệm điện” |
| D2 | “sửa máy lạnh tại nhà” |
| D3 | “sửa quạt điện” |

Một đường đọc document thông thường:

~~~text
find D1 -> đọc văn bản -> so khớp
find D2 -> đọc văn bản -> so khớp
find D3 -> đọc văn bản -> so khớp
~~~

Mỗi truy vấn mới có thể lại kiểm tra toàn bộ tập dữ liệu. Nếu chỉ mục đảo đã được xây dựng, ta có ánh xạ logic:

~~~text
"máy"  -> [D1, D2]
"lạnh" -> [D1, D2]
"sửa"  -> [D2, D3]
"điện" -> [D1, D3]
"quạt" -> [D3]
~~~

Tìm document chứa cả `máy` và `lạnh`:

\[
P(\text{máy}) \cap P(\text{lạnh}) = \{D1,D2\}
\]

Tìm document chứa `sửa` nhưng không chứa `lạnh`:

\[
P(\text{sửa}) \setminus P(\text{lạnh}) = \{D3\}
\]

Các posting list giúp engine bắt đầu từ những document ứng viên thay vì đọc mọi document nguồn. Tuy nhiên, một term quá phổ biến vẫn có posting list rất dài; hiệu năng còn phụ thuộc cách kết hợp term, ranking và filter.

## 2. Chỉ mục đảo gồm những thành phần gì?

Một inverted index có thể chứa:

| Thành phần | Vai trò |
|---|---|
| **Term dictionary** | Tìm danh sách term đã được index |
| **Posting list** | Với mỗi term, xác định những document chứa nó |
| **Document ID nội bộ** | Định danh record trong index; có thể khác ID nghiệp vụ |
| **Term frequency** | Số lần term xuất hiện trong một document/field |
| **Position** | Vị trí token phục vụ phrase/proximity query |
| **Offset** | Vị trí ký tự/byte phục vụ một số cơ chế highlight |
| **Field metadata** | Term thuộc title, description hay field nào |
| **Document statistics** | Độ dài document, thống kê corpus, phục vụ ranking |
| **Stored fields / source reference** | Lấy dữ liệu hiển thị hoặc liên kết về document gốc |

Không phải index nào cũng lưu toàn bộ những metadata trên. Ví dụ index chỉ chứa term và document ID có thể kiểm tra “có term này” nhưng không đủ thông tin cho phrase query đòi đúng thứ tự và khoảng cách từ.

### Posting có vị trí

Với D2 là `"sửa máy lạnh tại nhà"`:

~~~text
position: 0    1    2    3    4
token:    sửa  máy  lạnh tại  nhà
~~~

Một posting có thể được hình dung:

~~~text
"sửa"  -> (D2, position 0), (D3, position 0)
"máy"  -> (D1, position 0), (D2, position 1)
"lạnh" -> (D1, position 1), (D2, position 2)
~~~

Phrase `"máy lạnh"` cần kiểm tra hai term ở hai vị trí liền kề đúng thứ tự, chứ không chỉ kiểm tra cả hai cùng có trong document.

Ví dụ này đơn giản hóa tokenization bằng cách tách theo khoảng trắng. Tiếng Việt thực tế có nhiều từ gồm nhiều âm tiết; analyzer chuyên biệt có thể tạo tập token khác.

## 3. So sánh inverted index với B-tree index

| Tiêu chí | Ordered/B-tree index | Inverted index |
|---|---|---|
| Khóa tra cứu | Giá trị field, khóa tổng hợp | Term/token |
| Query điển hình | Equality, range, sort | Full-text, phrase, relevance |
| Ví dụ | Giá từ 200.000 đến 500.000 | Mô tả chứa từ về sửa máy lạnh |
| Dữ liệu lưu | Khóa đã sắp thứ tự → record | Term → posting list |
| Truy vấn prefix | Có thể dùng với điều kiện về chuỗi/collation | Có thể dùng prefix term dictionary |
| Phân tích ngôn ngữ | Không phải chức năng cốt lõi | Analyzer/tokenization là nền tảng |
| Relevance ranking | Không phải mục đích chính | Có thể dùng TF-IDF/BM25 |
| Đổi document | Cập nhật entry của index | Cập nhật/reindex term và postings |

Một query:

~~~javascript
db.services.find({
  title: /^May/
});
~~~

có thể là prefix của **toàn field** với một số điều kiện về index, nhưng không tự hiểu ngữ nghĩa trong mô tả. Full-text search cũng không thay thế unique index cho mã SKU hoặc index range theo ngày.

Hai loại index nên được chọn theo **access pattern**, không phải vì loại nào được xem là hiện đại hơn.

## 4. Analyzer: biến văn bản thành term

Thông thường dữ liệu đi qua pipeline:

~~~mermaid
flowchart LR
    A["Văn bản gốc"] --> B["Chuẩn hóa ký tự"]
    B --> C["Tokenizer"]
    C --> D["Token filters"]
    D --> E["Term + positions"]
    E --> F["Inverted index"]
~~~

Các khâu có thể gồm:

1. **Character normalization:** thống nhất một số dạng Unicode, chữ hoa/thường, dấu và ký tự theo quy tắc.
2. **Tokenization:** chia chuỗi thành token để tra cứu.
3. **Stop words:** có thể bỏ những từ rất phổ biến không mang nhiều tín hiệu.
4. **Stemming/lemmatization:** gom những biến thể từ về dạng gần gốc nếu ngôn ngữ và analyzer hỗ trợ.
5. **Synonyms:** mở rộng từ đồng nghĩa ở index-time hoặc query-time.
6. **N-gram/edge n-gram:** tạo term cho những kiểu autocomplete nhất định.
7. **Positions/offsets:** lưu metadata nếu muốn phrase, proximity hoặc highlight.

Một pipeline có thể tạo từ văn bản:

~~~text
Input:  "Máy Lạnh tiết kiệm điện"
Output: ["máy", "lạnh", "tiết", "kiệm", "điện"]
~~~

Nhưng đây chỉ là analyzer giả định. **Cấu hình analyzer quyết định chính xác term nào được lập chỉ mục**, không phải người lập trình tự suy từ chuỗi nguồn.

## 5. Analyzer tiếng Việt: dấu và phân đoạn từ

Tiếng Việt có các cụm nhiều âm tiết:

~~~text
"máy lạnh"
"điều hòa không khí"
"bảo trì định kỳ"
"cơ sở dữ liệu"
~~~

Tách theo khoảng trắng có thể coi mỗi âm tiết là một token trong khi nghiệp vụ muốn nhận diện một từ/cụm. Vì vậy nên đánh giá:

- Word segmentation và từ điển lĩnh vực.
- Tìm có dấu/không dấu: `"may lanh"` so với `"máy lạnh"`.
- Case folding và Unicode normalization.
- Mã thiết bị: `"R32"`, `"AC-101"`, `"12000BTU"`.
- Tên thương hiệu và model.
- Từ đồng nghĩa: `"máy lạnh"` và `"điều hòa"` trong domain điện lạnh.
- Lỗi gõ, đảo ký tự và khoảng trắng thừa.

**Bỏ dấu không phải lúc nào cũng vô hại.** Nó có thể giúp gõ không dấu, nhưng cũng có thể làm các từ khác nghĩa trở thành giống nhau. Có thể cân nhắc multi-field analyzer: một trường giữ dấu để tăng precision, một trường chuẩn hóa phục vụ recall; cần đo trên dữ liệu thật.

Không nên giả định mọi MongoDB text index mặc định có bộ tokenizer tiếng Việt chất lượng như công cụ NLP chuyên biệt.

## 6. Analyzer lúc index và lúc query phải tương thích

Nếu văn bản được index thành:

~~~text
["máy_lạnh", "bảo_trì"]
~~~

nhưng query được phân tích thành:

~~~text
["máy", "lạnh", "bảo", "trì"]
~~~

thì những term có thể không khớp nếu engine không có cơ chế mapping phù hợp. Một hợp đồng tìm kiếm cần ghi:

- Index-time analyzer cho từng field.
- Query-time analyzer cho từng field.
- Chính sách stop words, stemming, synonyms.
- Version của analyzer hoặc index definition.
- Quy trình rebuild khi đổi tokenizer.
- Bộ query test để đo thay đổi về relevance.

Đổi analyzer có thể làm kết quả khác ngay cả khi **document nguồn giữ nguyên**.

## 7. Term query, Boolean query và phrase query

Với các posting từ mục 1:

~~~text
P("sửa")  = {D2,D3}
P("lạnh") = {D1,D2}
~~~

Ta có:

~~~text
sửa AND lạnh  -> {D2}
sửa OR lạnh   -> {D1,D2,D3}
sửa NOT lạnh  -> {D3}
~~~

Đây là logic Boolean, không phải mô tả chính xác mọi engine sẽ phân tích một chuỗi query tự nhiên thế nào.

Các loại truy vấn chuyên biệt:

| Loại | Câu hỏi | Cần dữ liệu nào? |
|---|---|---|
| Term | Có token t hay không? | Term dictionary + postings |
| AND | Có toàn bộ term? | Giao posting |
| OR | Có ít nhất một term? | Hợp posting |
| NOT | Loại term hoặc điều kiện | Boolean filtering |
| Phrase | Token xuất hiện liền nhau, đúng thứ tự? | Position |
| Proximity | Các term cách nhau tối đa n vị trí? | Position |
| Prefix term | Token bắt đầu bằng tiền tố? | Term dictionary/term expansion |
| Fuzzy | Token gần nhau theo khoảng cách ký tự? | Index/search algorithm hỗ trợ |
| Fielded | Term nằm trong title hay body? | Field-specific index |
| Ranked top-k | Document nào liên quan nhất? | Term/document statistics |

**Tìm phrase khác AND**. Một document `"máy đang được sửa vì quá lạnh"` có `máy` và `lạnh` nhưng không chứa phrase liền nhau `"máy lạnh"`.

## 8. Prefix search của token khác prefix của toàn field

Ba nhu cầu:

1. Tìm `productCode` bắt đầu bằng `KB-`.
2. Tìm từ trong `title` bắt đầu bằng `"má"`.
3. Tìm `description` có chuỗi `"máy"` ở vị trí bất kỳ.

Chúng có semantics và index khác nhau.

Một B-tree index phù hợp có thể đáp ứng mục 1. Mục 2 có thể cần prefix term dictionary hoặc edge n-gram theo cấu hình search engine. Mục 3 là substring/lexical search, không phải prefix field.

Regex không neo đầu chuỗi có thể quét nhiều candidate; không nên xem nó là thay thế trực tiếp cho một inverted index được thiết kế theo tokenizer.

## 9. Term phổ biến và term hiếm

Giả sử trong 1 triệu document:

~~~text
"dịch vụ" xuất hiện ở 900.000 document
"R32"     xuất hiện ở 2.000 document
"Q9XZ"    không xuất hiện
~~~

Posting list của `"dịch vụ"` dài hơn rất nhiều. Query `"dịch vụ AND R32"` có thể tận dụng term `R32` chọn lọc để giảm số candidate. Cơ chế thực thi thật phụ thuộc query planner và thuật toán của search engine.

Khái niệm quan trọng:

- **Document frequency (df):** số document chứa term.
- **Term frequency (tf):** số lần term xuất hiện trong một document/field.
- **Posting length:** số entry cần xét.
- **Selectivity:** tỷ lệ dữ liệu còn lại sau điều kiện.
- **Top-k pruning:** bỏ qua candidate không thể vượt điểm top-k theo thuật toán thích hợp.

Chỉ mục đảo giúp tra cứu có cấu trúc, nhưng term quá phổ biến và query phức tạp vẫn có thể tốn CPU/memory.

## 10. Ranking bằng độ liên quan

Một query tìm `"sửa máy lạnh"` thường muốn dịch vụ đúng ý xuất hiện trước. Các tín hiệu có thể gồm:

- Term khớp ở title hay description.
- Term xuất hiện bao nhiêu lần.
- Term có hiếm trong corpus không.
- Document/field dài hay ngắn.
- Term có ở gần nhau theo thứ tự không.
- Khớp phrase hay chỉ khớp từng term.
- Boost theo category hoặc quy tắc nghiệp vụ.
- Tín hiệu bổ sung: độ mới, rating, khoảng cách.

**BM25** là một họ mô hình ranking lexical phổ biến. Một biểu thức minh họa:

\[
\operatorname{score}(D,Q)=
\sum_{t\in Q}\operatorname{IDF}(t)\,
\frac{f(t,D)(k_1+1)}
{f(t,D)+k_1\left(1-b+b\frac{|D|}{\operatorname{avgdl}}\right)}
\]

Trong đó:

- `f(t,D)` là tần suất term trong document.
- `IDF(t)` biểu diễn mức độ hiếm của term.
- `|D|` và `avgdl` liên quan đến chuẩn hóa độ dài.
- `k1` và `b` là các tham số của mô hình.

Trực giác: term hiếm đóng góp tín hiệu lớn, term xuất hiện nhiều có thể tăng điểm nhưng không tăng vô hạn theo tỷ lệ đơn giản, document dài không mặc nhiên được ưu tiên.

**Điểm BM25 không phải xác suất người dùng sẽ thích kết quả**, không phải tỷ lệ phần trăm chuẩn. Cần test relevance bằng truy vấn và nhãn đánh giá có ý nghĩa nghiệp vụ.

## 11. Field boosting và business ranking

Giả sử một dịch vụ chứa `"máy lạnh"` trong title, dịch vụ khác chỉ nhắc tới từ đó trong mô tả rất dài. Search có thể ưu tiên title bằng field weights.

Một hợp đồng có thể là:

~~~text
title match       : trọng số cao
category match    : tín hiệu bổ sung
description match : trọng số thấp hơn title
quality/rating    : tín hiệu nghiệp vụ
distance          : tín hiệu địa lý
availability      : filter bắt buộc
tenant/ACL        : filter bắt buộc
~~~

Phân biệt **filter** và **boost**:

- Filter quyết định document có được phép xuất hiện không.
- Boost quyết định thứ tự của những document đã hợp lệ.

Không được dùng “điểm thấp” thay cho việc loại document thuộc tenant khác hoặc dịch vụ đã bị cấm hiển thị.

## 12. MongoDB classic text index: tạo và truy vấn

Một ví dụ collection `services`:

~~~javascript
db.services.insertMany([
  {
    _id: "svc-101",
    tenantId: "tenant-a",
    title: "Sửa máy lạnh tại nhà",
    description: "Kiểm tra và bảo trì máy lạnh",
    status: "ACTIVE"
  },
  {
    _id: "svc-102",
    tenantId: "tenant-a",
    title: "Vệ sinh quạt điện",
    description: "Dịch vụ bảo trì quạt",
    status: "ACTIVE"
  },
  {
    _id: "svc-103",
    tenantId: "tenant-b",
    title: "Sửa máy lạnh",
    description: "Dịch vụ sửa chữa thiết bị lạnh",
    status: "ACTIVE"
  }
]);
~~~

Tạo compound text index:

~~~javascript
db.services.createIndex(
  {
    tenantId: 1,
    title: "text",
    description: "text"
  },
  {
    name: "idx_services_tenant_text",
    default_language: "none",
    weights: {
      title: 8,
      description: 2
    }
  }
);
~~~

Ý nghĩa:

- `tenantId` là field equality đứng trước các text keys.
- `title` và `description` được index phục vụ `$text`.
- `weights` giúp điều chỉnh mức ưu tiên tương đối của các field.
- `default_language: "none"` minh họa việc không áp các quy tắc stemming/stop words dành cho một ngôn ngữ cụ thể, **không phải** cấu hình word segmentation tiếng Việt chuyên sâu.
- Với compound text index có field thường đứng trước text fields, query dùng `$text` cần equality trên những field prefix theo yêu cầu của MongoDB.

MongoDB classic text index có các hạn chế về language, index definition, truy vấn và số lượng text index; đừng coi ví dụ này là thay thế cho mọi nhu cầu autocomplete, fuzzy hoặc search ranking tùy biến.

## 13. MongoDB `$text` và `textScore`

~~~javascript
db.services.find(
  {
    tenantId: "tenant-a",
    status: "ACTIVE",
    $text: {
      $search: "máy lạnh"
    }
  },
  {
    title: 1,
    description: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
});
~~~

Truy vấn:

1. Giới hạn tenant được phép.
2. Lọc trạng thái.
3. Dùng text index để tìm term tương ứng với query.
4. Trả điểm `textScore`.
5. Sort theo score.

Không nên suy ra chuỗi `"máy lạnh"` mặc định là phrase bắt buộc trong mọi text query. Các engine có semantics khác nhau cho nhiều từ, phrase và từ đồng nghĩa.

### Phrase trong MongoDB classic text query

~~~javascript
db.services.find({
  tenantId: "tenant-a",
  $text: {
    $search: "\"máy lạnh\""
  }
});
~~~

Dấu ngoặc kép bên trong `$search` biểu diễn phrase search theo semantics của MongoDB text query và analyzer thực tế.

### Text index không phải unique index

Text index không tự bảo đảm tên sản phẩm, SKU hoặc mã dịch vụ là duy nhất. Nếu `(tenantId, skuKey)` phải unique, cần ràng buộc thích hợp riêng.

## 14. Classic `$text` khác Search/Atlas `$search`

Trong hệ sinh thái MongoDB, cần phân biệt:

| Nội dung | MongoDB classic `$text` | Search index chuyên biệt/`$search` |
|---|---|---|
| Cơ chế | Text index tích hợp DB | Search engine/index phục vụ truy vấn riêng |
| Analyzer | Các khả năng cổ điển của text index | Có thể hỗ trợ mapping/analyzer phong phú hơn |
| Query | `$text` | Search DSL hoặc pipeline `$search` |
| Ranking | MongoDB text score | Có thể dùng BM25/boost và tín hiệu khác |
| Search visibility | Theo semantics của đường index/đọc DB | Có thể near-real-time hoặc eventual |
| Cập nhật | Trong cơ chế bảo trì index DB | Có thể có pipeline/refresh riêng |
| Tính năng nâng cao | Bị giới hạn theo classic text API | Có thể có autocomplete, fuzzy, highlight tùy sản phẩm |

Hai cơ chế có thể cùng nằm trong một hệ sinh thái nhưng **không cùng một API và không cùng mọi bảo đảm consistency**. Cần kiểm tra tài liệu/version của chức năng search đang chọn.

Một hệ bên ngoài như Elasticsearch/OpenSearch lại có nguồn dữ liệu, pipeline đồng bộ và vòng đời vận hành riêng. Không lấy đặc tính của hệ này suy diễn hoàn toàn sang hệ kia.

## 15. Luồng xử lý một truy vấn full-text

~~~mermaid
flowchart TD
    A["Người dùng nhập query"] --> B["Validate input và quyền"]
    B --> C["Query analyzer"]
    C --> D["Term dictionary"]
    D --> E["Posting list retrieval"]
    E --> F["Boolean/phrase/filter"]
    F --> G["Score và top-k"]
    G --> H["Fetch/hydrate document"]
    H --> I["Kiểm tra trạng thái/quyền hiện hành khi cần"]
    I --> J["Trả kết quả"]
~~~

Đây là sơ đồ logic. Một engine có thể áp filter sớm, hợp nhất posting trên nhiều shard và tính score trong lúc retrieval, thay vì chạy đúng thứ tự từng ô.

### Filter tenant phải được áp đúng thời điểm

Giả sử search index có 1 triệu dịch vụ nhiều tenant, nhưng tenant-a chỉ có 2.000. Nếu search lấy **top 10 toàn bộ corpus** rồi ứng dụng mới lọc tenant, có thể chỉ còn 0–1 kết quả dù tenant-a có hàng chục dịch vụ phù hợp.

Cần dùng khả năng lọc tenant/quyền trong query engine theo semantics được hỗ trợ, không lấy top-k toàn hệ thống rồi mới cố sửa bằng hậu lọc. Ngoài tính đúng đắn, đây còn là yêu cầu chống lộ dữ liệu.

Khi thực hiện hành động nghiệp vụ như đặt dịch vụ, nên kiểm tra lại nguồn có thẩm quyền vì search index có thể trễ.

## 16. Cơ chế cập nhật chỉ mục khi thêm document

Khi một document mới được ghi:

~~~javascript
{
  _id: "svc-104",
  tenantId: "tenant-a",
  title: "Bảo trì máy lạnh",
  description: "Kiểm tra hệ thống điều hòa",
  status: "ACTIVE"
}
~~~

Về logic, hệ indexing cần:

1. Xác định field được index.
2. Chạy analyzer.
3. Tạo term, vị trí và metadata.
4. Ghi hoặc bổ sung posting tương ứng.
5. Khi thích hợp, làm phiên bản index mới **visible cho searcher**.

~~~mermaid
flowchart LR
    A["Write document"] --> B["Analyze fields"]
    B --> C["Terms + positions"]
    C --> D["Index postings"]
    D --> E["Refresh / make searchable"]
    E --> F["Query nhìn thấy document"]
~~~

Bước cuối **không có cùng thời điểm** trong mọi kiến trúc.

- Classic text index của DB thường được bảo trì trong đường write/index của engine.
- Search projection ngoài có thể chờ CDC/event và index worker.
- Near-real-time search engine có thể cần refresh trước khi searcher nhìn thấy dữ liệu mới.

Do đó, không đồng nhất `source write acknowledged` với `search-visible` nếu dùng index bất đồng bộ.

## 17. Khi sửa document, posting cũ phải được xử lý

Ví dụ:

~~~text
Trước:
  svc-101: "sửa máy lạnh"

Sau:
  svc-101: "sửa máy giặt"
~~~

Về logic, search index mới không được tiếp tục xem document này là kết quả cho term `lạnh` nếu field đã được thay đổi và không còn term đó.

~~~text
Trước:
  "lạnh" -> [svc-101]
  "giặt" -> []

Sau:
  "lạnh" -> []
  "giặt" -> [svc-101]
~~~

Nhưng cơ chế vật lý khác nhau:

- DB tích hợp index có thể thay đổi các entry/index structures theo write của document.
- Search engine dựa trên **immutable segments** như Lucene thường tổ chức logical update thành xóa phiên bản cũ và lập chỉ mục phiên bản document mới.
- Projection đồng bộ qua event có thể làm upsert toàn bộ search document theo `sourceVersion`.

Không nên giả định mọi engine sửa posting tại chỗ hoặc mọi field update chỉ chạm đúng một posting list. Chi phí indexing phụ thuộc cấu trúc và implementation.

## 18. Khi xóa hoặc ẩn document

Các trạng thái khác nhau:

- Xóa cứng bản ghi nguồn.
- Xóa mềm bằng `deletedAt`.
- Đổi `ACTIVE → INACTIVE`.
- Chuyển owner/tenant.
- Thu hồi quyền xem.
- Ẩn theo quyết định moderation.

Với search, cần quyết định:

1. Kết quả có phải biến mất ngay về mặt nghiệp vụ không?
2. Index nhận tín hiệu xóa/ẩn thế nào?
3. Có chấp nhận khoảng thời gian chỉ mục còn cũ không?
4. Khi event update cũ đến sau delete, có resurrect document không?
5. Khi index physically compact/delete, dữ liệu có còn trong backup/cache hay không?

**Ẩn khỏi query không đồng nghĩa xóa vật lý khỏi mọi bản sao.** Với dữ liệu nhạy cảm, phải có chính sách riêng cho index, cache, log, retention và backup.

### Đường ghi vẫn kiểm tra nguồn có thẩm quyền

Nếu search trả một dịch vụ `ACTIVE` từ index cũ, Booking service vẫn cần kiểm tra status hiện hành trước khi xác nhận đặt. Search phục vụ **khám phá**; bất biến giao dịch phải được bảo vệ ở nguồn có thẩm quyền hoặc transaction/conditional write phù hợp.

## 19. Immutable segments trong engine dựa trên Lucene

Nhiều hệ search dựa trên Lucene tổ chức dữ liệu thành các **segment**. Segment đã được ghi thường không bị sửa nội dung postings tùy ý như một document object trong bộ nhớ.

~~~text
Indexing buffer
   |
   v
Segment A: term dictionary, postings
Segment B: term dictionary, postings
Segment C: term dictionary, postings
   |
   v
Background merge/compaction
   |
   v
Larger segment với dữ liệu đã gộp
~~~

Khi document được cập nhật, engine có thể đánh dấu document cũ bị xóa ở phiên bản index và thêm một bản được index lại. Segment merge dọn bỏ dữ liệu cũ, gộp postings và giảm số segment theo chiến lược của engine.

Hệ quả:

- Update có thể có **write amplification**.
- Xóa logic không nhất thiết thu hồi dung lượng vật lý ngay.
- Merge dùng CPU, RAM và I/O.
- Nhiều update lớn có thể tạo nhiều segment và tăng chi phí search.
- Cần theo dõi indexing rate, merge backlog và số segment.

Đây là mô hình cơ chế chung, không phải cam kết cách mỗi dịch vụ managed triển khai nội bộ.

## 20. Refresh, commit, durability và replication khác nhau

Một số khái niệm dễ nhầm:

| Khái niệm | Câu hỏi |
|---|---|
| Write acknowledged | Hệ đã nhận/xác nhận ghi theo cấu hình nào? |
| Index accepted | Yêu cầu lập chỉ mục đã được tiếp nhận chưa? |
| Refresh | Searcher có nhìn thấy phiên bản index mới không? |
| Durable commit/flush | Đã có bảo đảm bền vững nào trên disk/log? |
| Replica acknowledgment | Bao nhiêu replica xác nhận? |
| Merge | Segment đã được gộp/tối ưu chưa? |
| Source DB commit | Thay đổi document nguồn đã commit chưa? |

Trong engine near-real-time, **refresh phục vụ khả năng nhìn thấy trong search** và có thể khác việc ghi dữ liệu bền vững lên disk/log. Một document có thể được tiếp nhận nhưng chưa xuất hiện trong kết quả trước khi searcher refresh.

Không nên nói “đã refresh” nghĩa là mọi replica đều đã durable, hay “đã commit” nghĩa là tất cả search index phụ đã lập chỉ mục xong.

## 21. Timeline của một cập nhật bất đồng bộ

~~~text
t0  API nhận yêu cầu tạo Service
t1  Source DB commit Service version 12
t2  CDC/outbox phát hiện thay đổi
t3  Consumer nhận event
t4  Indexer phân tích và ghi index
t5  Searcher refresh phiên bản mới
t6  Truy vấn bắt đầu thấy Service version 12
~~~

Khoảng thời gian từ `t1` đến `t6` là độ trễ từ source commit tới search visibility. Trong thực tế:

- Pipeline có thể có nhiều queue hoặc replica.
- Từng worker có thể retry.
- Refresh có lịch riêng.
- Một event có thể bị kẹt hoặc cần dead-letter handling.
- Một index mới có thể đang backfill dữ liệu.

Cần đặt SLO cho độ trễ tìm kiếm nếu người dùng cần tìm ngay sau khi tạo. Không hứa “ghi xong sẽ tìm thấy tức thì” nếu kiến trúc không có bảo đảm đó.

## 22. Classic MongoDB text index so với search projection ngoài

**MongoDB classic text index** được duy trì trong cơ chế index của MongoDB khi dữ liệu document thay đổi. Nó không đồng nghĩa với việc tạo một service search khác phải chờ message.

Với **search projection tách riêng**:

~~~text
MongoDB source
    -> CDC/event
    -> Search indexing worker
    -> Search index
    -> Search API
~~~

index thường có một vòng đời cập nhật độc lập. Nó có thể trễ, cần checkpoint, có thể cần rebuild và xử lý event lỗi.

Cũng cần phân biệt chuyện index/search với chuyện **đọc từ MongoDB replica**: một request đọc từ replica có thể nhìn thấy mức độ mới khác do read preference/consistency config. Atomicity của write nguồn và độ mới của một đường đọc khác không phải cùng khái niệm.

## 23. Nguồn sự thật và projection phục vụ tìm kiếm

Giả sử Product/Catalog service lưu:

~~~javascript
{
  _id: "svc-101",
  tenantId: "tenant-a",
  providerId: "pro-17",
  title: "Sửa máy lạnh tại nhà",
  description: "Bảo trì máy lạnh",
  status: "ACTIVE",
  version: NumberLong("12")
}
~~~

Một search projection:

~~~json
{
  "serviceId": "svc-101",
  "tenantId": "tenant-a",
  "title": "Sửa máy lạnh tại nhà",
  "description": "Bảo trì máy lạnh",
  "status": "ACTIVE",
  "sourceVersion": 12
}
~~~

Các quyết định:

- `Service` nguồn quyết định status, title, description hiện hành.
- Search index là **read model** có thể dựng lại.
- `serviceId` giữ danh tính ổn định.
- `tenantId` cần nằm trong điều kiện quyền của mọi query thích hợp.
- `sourceVersion` giúp chống cập nhật cũ và đo chênh lệch.
- Khi dịch vụ bị khóa, đường nghiệp vụ phải kiểm tra nguồn ngay cả khi index còn cũ.

Mô hình này thích hợp khi cần tính năng tìm kiếm riêng, nhưng tăng chi phí đồng bộ và vận hành.

## 24. Dual-write có khoảng hở lỗi

Code kiểu:

~~~text
1. Update source document
2. Call Search API to update index
~~~

có thể gặp:

- Process chết sau bước 1 → source mới, index cũ.
- Search API timeout → không rõ đã nhận index update chưa.
- Retry gửi lặp → có thể ghi lại event.
- Hai update của cùng document chạy song song → index có thể nhận phiên bản cũ sau phiên bản mới.

Đảo thứ tự hai bước không giải quyết atomicity: Search có thể nhận dữ liệu chưa commit ở source.

**Hai API call trong cùng hàm Java không tạo thành distributed transaction.** Phải có cơ chế đồng bộ và xử lý lỗi phù hợp.

## 25. CDC và transactional outbox

Hai hướng thường dùng:

**CDC:** đọc thay đổi đã commit từ log/change stream của nguồn và chuyển tới indexer, có checkpoint và cơ chế replay.

**Transactional outbox:** ghi thay đổi nghiệp vụ và một outbox event trong cùng transaction/atomic unit được DB hỗ trợ, sau đó publisher gửi event tới search consumer.

Ví dụ logic:

~~~text
BEGIN TRANSACTION
  update Service(svc-101, version=13)
  insert OutboxEvent(
    eventId=evt-201,
    serviceId=svc-101,
    sourceVersion=13,
    type=ServiceUpdated
  )
COMMIT

Publisher -> Message broker -> Search indexer
~~~

Outbox tránh mất tín hiệu cần publish do process chết giữa DB commit và broker send **nếu được ghi đúng phạm vi transaction**. Nhưng publisher vẫn có thể gửi event lặp. Consumer phải idempotent và indexer phải chịu được out-of-order.

**Outbox không tự bảo đảm exactly-once end-to-end**, không tự làm search index tức thời và không thay thế monitoring/reconciliation.

## 26. Indexer idempotent và version

Giả sử index đang lưu version 13. Event version 12 đến sau vì retry.

Nếu indexer ghi đè theo thứ tự nhận, search trở về dữ liệu cũ. Một quy tắc khái niệm:

~~~text
if incomingVersion < indexedVersion:
    ignore stale update

if incomingVersion == indexedVersion:
    treat as duplicate or verify compatible payload

if incomingVersion > indexedVersion:
    apply using conditional write/version guard
~~~

**Đọc version rồi ghi sau bằng hai lệnh độc lập có thể bị race** nếu nhiều consumer cùng chạy. Phải dùng cơ chế conditional/versioned write hoặc một bộ điều phối bảo đảm tuần tự theo key.

### Vì sao không chỉ dùng timestamp?

Event có thể có đồng hồ nguồn khác nhau, timestamp trùng, hiệu lực hồi tố hoặc retry nhiều giờ. Một `sourceVersion` tăng đơn điệu theo từng entity thường rõ nghĩa hơn để quyết định thứ tự trạng thái nếu nguồn có cơ chế cấp version đúng.

## 27. Version hóa delete và tombstone

Giả sử:

~~~text
v18: ServiceUpdated(status=ACTIVE)
v19: ServiceDeleted
~~~

Indexer áp v19 để xóa dịch vụ. Sau đó event v18 đến muộn; nếu indexer upsert vô điều kiện, dịch vụ **xuất hiện lại**.

Một giải pháp là giữ tombstone/version guard:

~~~text
serviceId = svc-101
sourceVersion = 19
deleted = true
~~~

Với event v18, indexer bỏ qua.

Nếu index xóa hoàn toàn record, phải có cơ chế khác (versioning API của engine, registry hoặc state checkpoint) để ngăn event cũ tạo lại dữ liệu. Retention của tombstone phải xem xét thời gian có thể replay các event cũ.

**Logical delete và physical removal của segment không phải cùng thời điểm**, cũng như xóa search hit không đồng nghĩa xóa hết backup, cache hoặc log.

## 28. Rebuild chỉ mục: backfill + catch-up

Đổi analyzer, thêm field hoặc khắc phục index hỏng có thể cần xây dựng lại.

Một kế hoạch:

1. Tạo cấu hình **index mới** với analyzer/mapping/version đã chọn.
2. Chọn snapshot/checkpoint nguồn xác định.
3. Backfill document nguồn vào index mới.
4. Tiếp nhận những thay đổi phát sinh trong lúc backfill qua CDC/event.
5. Áp event còn thiếu, bảo vệ sourceVersion và delete.
6. Đối soát số lượng/ID/phiên bản với nguồn.
7. Kiểm thử search relevance và latency.
8. Khi index mới đuổi kịp theo tiêu chí, cutover traffic.
9. Giữ khả năng rollback trong cửa sổ phù hợp.
10. Ngừng index cũ khi đã xác nhận ổn định.

~~~mermaid
flowchart LR
    A["Source DB"] --> B["Backfill snapshot"]
    A --> C["CDC changes"]
    B --> D["New index"]
    C --> D
    D --> E["Catch-up và đối soát"]
    E --> F["Cutover"]
~~~

**Chỉ copy nguồn một lần rồi đổi query không đủ** nếu dữ liệu tiếp tục thay đổi. Cần tránh khoảng hở giữa snapshot và event stream, và bảo đảm các event sau snapshot không bị bỏ sót.

## 29. Thay đổi synonym và analyzer

Ví dụ muốn `"điều hòa"` có thể tìm được dịch vụ gắn với `"máy lạnh"`.

Hai chiến lược:

- **Index-time synonym expansion:** tạo thêm term trong lúc index; đổi từ điển có thể yêu cầu reindex để áp vào document cũ.
- **Query-time synonym expansion:** mở rộng query trước khi tìm; có thể đổi chính sách truy vấn dễ hơn trong một số hệ, nhưng ranking và phrase semantics có thể phức tạp.

Khả năng reload synonym động, versioning và cách index hỗ trợ phụ thuộc engine. Không giả định đổi file từ điển là cập nhật ngay mọi document.

Synonym cần kiểm thử ngữ cảnh: một từ đồng nghĩa đúng trong miền điện lạnh có thể gây false positive ở miền khác.

## 30. Dung lượng index và write amplification

Một inverted index tiêu thụ tài nguyên cho:

- Term dictionary.
- Posting lists.
- Position, offset, term vector nếu bật.
- Field-specific metadata.
- Stored fields.
- Multiple analyzers và n-gram.
- Replicas.
- Segments đang chờ merge/compaction.
- Các phiên bản document chưa được thu hồi vật lý.

Mô hình khái niệm:

\[
\text{Index bytes}
\approx
\text{dictionary}
+
\text{postings}
+
\text{positions/offsets}
+
\text{metadata}
\]

Đây không phải công thức dự báo chính xác; compression và cấu trúc thực tế thay đổi theo engine.

Mỗi lần update description có thể gây công việc indexing mới. Nếu index tất cả field, tạo n-gram dày và giữ nhiều representation, write amplification, disk usage và merge load sẽ tăng.

**Chỉ index những field thực sự cần cho truy vấn**. Tránh index thông tin riêng tư không được phép tìm kiếm.

## 31. Filter, xếp hạng và top-k

Một search request:

~~~text
query: "sửa máy lạnh"
tenantId: tenant-a
status: ACTIVE
categoryId: home-maintenance
sort: relevance DESC
limit: 20
~~~

Cần xác định:

1. Filter bắt buộc như tenant và quyền được áp ở đâu?
2. Search index có trường `status` mới nhất không?
3. Query analyzer biến câu thành term nào?
4. Ranking dựa trên title/body/boost ra sao?
5. Nếu nhiều document cùng score, thứ tự phá hòa thế nào?
6. Có cần hydrate document hiện hành trước khi trả không?
7. Nếu user bấm booking, đường ghi kiểm tra nguồn nào?

Không nên lấy top 20 toàn corpus rồi mới lọc tenant, vì có thể làm mất nhiều kết quả hợp lệ. Với quyền bảo mật, một bản sao index có thể trễ phải được kết hợp với chính sách kiểm tra hiện hành theo yêu cầu nghiệp vụ.

## 32. Pagination khi sort theo score

Hai document có thể có cùng relevance score. Score còn có thể thay đổi khi index thêm document hoặc refresh. Nếu chỉ sort `score DESC` rồi phân trang offset, thứ tự có thể dao động.

Có thể cân nhắc:

- Sort thêm ID ổn định để phá hòa.
- Cursor/search-after theo API engine.
- Point-in-time snapshot nếu sản phẩm/engine hỗ trợ và nghiệp vụ cần.
- Cursor gắn với query, filter và index version.
- Không cho client sửa cursor để truy cập dữ liệu trái quyền.

Không có một công thức MongoDB `skip` áp dụng nguyên xi cho mọi search engine. Deep pagination bằng offset thường đòi nhiều candidate và có thể tốn chi phí.

## 33. Search result không phải nguồn xác nhận giao dịch

Giả sử:

~~~text
Search projection:
  serviceId=svc-101
  status=ACTIVE
  price=350000
  indexedAt=09:00

Source DB:
  status=INACTIVE
  price=400000
  updatedAt=09:01
~~~

Search có thể vẫn trả dịch vụ ACTIVE vì index chưa cập nhật. Nếu người dùng tạo booking, service ghi phải kiểm tra trạng thái/giá và bất biến tại nguồn có thẩm quyền, dùng transaction hoặc conditional write phù hợp.

Một mô hình rõ:

- Search phục vụ khám phá.
- Document nguồn quyết định trạng thái hiện hành.
- Booking service bảo vệ các quy tắc giao dịch.
- UI có thể báo giá cuối cùng sẽ được xác nhận ở bước đặt.

Cách này cho phép eventual search visibility mà không đánh đổi tính đúng đắn giao dịch.

## 34. Quan sát chất lượng search và cập nhật

| Nhóm | Metric gợi ý |
|---|---|
| Query | QPS, p50/p95/p99 latency, timeout |
| Candidate retrieval | Posting/candidate count, cache hit, scanned terms |
| Relevance | Precision@k, Recall@k, MRR, nDCG |
| UX | Zero-result rate, query reformulation, click-through |
| Indexing | Documents/s, failed updates, retry count |
| Đồng bộ | CDC lag, queue depth, last applied sourceVersion |
| Dung lượng | Index bytes, segment count, deletion ratio |
| Tài nguyên | CPU, memory, disk I/O, merge time |
| Drift | Missing IDs, extra IDs, mismatched versions |
| Bảo mật | Query trả trái tenant/quyền — phải bằng 0 |

Không phải engine nào cũng cung cấp mọi metric. Có thể cần thêm telemetry từ ứng dụng và các job đối soát.

### Search visibility lag

Nếu đo được:

~~~text
source commit time -> moment indexed version becomes searchable
~~~

đó là độ trễ người dùng có thể cảm nhận khi vừa tạo/sửa dữ liệu rồi tìm kiếm. Cần thận trọng khi hai đồng hồ không đồng bộ; version/checkpoint hoặc đo end-to-end có thể đáng tin hơn phép trừ timestamp máy chủ không cùng nguồn thời gian.

## 35. Đo relevance bằng bộ truy vấn tiếng Việt

Ví dụ tập truy vấn kiểm thử:

| Query | Mong muốn | Trường hợp biên |
|---|---|---|
| “sửa máy lạnh” | Dịch vụ sửa máy lạnh | Dịch vụ chỉ bán máy lạnh xếp thấp hơn |
| “dieu hoa” | Kết quả điều hòa nếu hỗ trợ không dấu | Có nguy cơ false positive do bỏ dấu |
| “R32” | Mô tả liên quan gas/model R32 | Tokenizer không làm mất mã số |
| “bảo trì tại nhà” | Dịch vụ đến tận nơi | Phrase/synonyms ảnh hưởng |
| “sửa máy giặt” | Máy giặt, không phải máy lạnh | Phân biệt term và ngữ cảnh |
| “AC-101” | Mã máy cụ thể | Dấu gạch nối và tokenization |

Các phép đo:

- **Precision@k:** tỷ lệ kết quả top-k liên quan theo nhãn.
- **Recall@k:** mức tìm thấy các kết quả liên quan trong tập chuẩn.
- **MRR:** vị trí của kết quả liên quan đầu tiên.
- **nDCG@k:** chất lượng thứ tự theo mức độ liên quan.
- **Latency:** kết quả phải đủ nhanh.
- **Freshness:** nội dung cập nhật phải xuất hiện trong giới hạn chấp nhận.

Chỉ tối ưu latency mà bỏ relevance có thể tạo hệ tìm kiếm rất nhanh nhưng không hữu ích.

## 36. Một số lỗi thiết kế cần tránh

**“Inverted index là B-tree đổi tên.”** Inverted index tổ chức theo term/posting, phục vụ full-text và ranking.

**“Có text index thì tự hiểu tiếng Việt và từ đồng nghĩa.”** Cần analyzer và kiểm thử chất lượng.

**“Chứa cùng từ thì mọi document có cùng score.”** Score còn phụ thuộc term frequency, rarity, độ dài và boosts.

**“Phrase chỉ là AND giữa các từ.”** Phrase cần thông tin vị trí/thứ tự theo semantics engine.

**“MongoDB `$text` và `$search` là cùng một tính năng.”** Chúng có index/query API và cơ chế riêng.

**“Đã commit nguồn thì search index ngoài phải thấy ngay.”** Pipeline và refresh có thể làm visible trễ.

**“Refresh đồng nghĩa durable commit.”** Search visibility và durability là hai bảo đảm khác nhau.

**“Mọi update chỉ sửa posting tại chỗ.”** Engine dựa trên immutable segments có thể dùng delete + reindex và merge.

**“Delete xong không bao giờ có document xuất hiện lại.”** Event cũ đến muộn có thể resurrect khi thiếu version guard.

**“Ghi source rồi gọi search trong cùng function là atomic.”** Process có thể chết giữa hai bước.

**“Event đến đúng một lần và theo thứ tự.”** Cần idempotency, version và retry/replay.

**“Top-k toàn hệ rồi lọc tenant là đủ.”** Có thể thiếu kết quả đúng và không bảo đảm quyền.

**“Search trả ACTIVE thì có thể bán/đặt ngay.”** Cần kiểm tra lại nguồn có thẩm quyền.

**“Thêm nhiều index luôn tốt.”** Chỉ mục có chi phí lưu, ghi, merge và rebuild.

## 37. Bài tập áp dụng

### Bài A — Lập posting list

Cho:

~~~text
D1: "cà phê sữa"
D2: "cà phê đen"
D3: "trà sữa"
D4: "cà phê rang"
~~~

Giả định tách token theo khoảng trắng, không chuẩn hóa thêm. Hãy lập posting list.

**Gợi ý:**

~~~text
cà  -> [D1,D2,D4]
phê -> [D1,D2,D4]
sữa -> [D1,D3]
trà -> [D3]
đen -> [D2]
rang -> [D4]
~~~

`cà AND sữa` trả D1. Đây là ví dụ cấu trúc, không khẳng định tokenizer tiếng Việt sản xuất nên tách như vậy.

### Bài B — Phrase và AND

~~~text
D1: "máy lạnh đang sửa"
D2: "máy đang sửa rất lạnh"
~~~

Hai document có cả `máy` và `lạnh`, nhưng chỉ D1 chứa phrase liền nhau `"máy lạnh"`. Cần metadata gì để phân biệt?

**Hướng giải:** positions hoặc cấu trúc tương đương hỗ trợ phrase.

### Bài C — Ranking

D1 chứa query term ở title; D2 chứa ở một mô tả dài. Tại sao ranking khác nhau?

**Hướng giải:** field weights, tf, IDF, độ dài field và scoring configuration.

### Bài D — Update term

D7 đổi từ `"sửa máy lạnh"` sang `"sửa máy giặt"`. Chỉ mục logic cần thay đổi thế nào?

**Hướng giải:** phiên bản search mới không được giữ D7 trong kết quả cho `lạnh` chỉ vì văn bản cũ. Cần loại/đánh dấu postings cũ và index term mới theo cơ chế engine.

### Bài E — Event sai thứ tự

Indexer nhận Service v20 rồi v19. Nếu ghi vô điều kiện, hệ sẽ ở trạng thái nào?

**Hướng giải:** có thể lùi về v19. Cần conditional write theo sourceVersion hoặc cách sắp thứ tự an toàn.

### Bài F — Delete đến trước update cũ

Service bị xóa ở version 30; event cập nhật version 29 đến muộn. Chỉ xóa record search có đủ không?

**Hướng giải:** có thể cần tombstone/version guard để ngăn event v29 tạo lại record.

### Bài G — Search đa tenant

Lấy top 10 toàn hệ, lọc tenant-a ở ứng dụng còn một kết quả. Có thể kết luận tenant-a chỉ có một kết quả liên quan?

**Hướng giải:** không, các kết quả phù hợp khác có thể không thuộc top 10 toàn hệ. Cần filter trong retrieval đúng semantics và kiểm tra quyền.

### Bài H — Source đã commit, search chưa thấy

Document tạo thành công nhưng tìm không ra trong vài giây. Điều đó luôn có nghĩa transaction DB lỗi?

**Hướng giải:** không. Search projection/NRT index có thể chậm; cần đo index visibility lag và xử lý lỗi pipeline.

### Bài I — Chọn loại index

Yêu cầu:

1. SKU bắt đầu bằng `KB-`.
2. Mô tả liên quan `"sửa máy lạnh"`.
3. Giá trong khoảng.
4. Sort theo createdAt.

**Hướng giải:** ordered index có thể phù hợp prefix field và range/sort; inverted index phù hợp lexical full-text; có thể cần nhiều index hoặc query strategy phối hợp.

### Bài J — Đổi analyzer

Đội ngũ thêm synonym và tokenizer mới. Có thể giả định mọi document cũ tự có term mới ngay không?

**Hướng giải:** tùy index-time/query-time analysis và engine. Có thể cần rebuild, relevance testing và cutover có kiểm soát.

## 38. Quy trình đưa inverted index vào hệ NoSQL

1. Liệt kê access pattern: term, phrase, prefix, autocomplete, filter, sort.
2. Chọn field có thể index; loại field nhạy cảm không cần thiết.
3. Chọn tokenizer/analyzer và test tiếng Việt theo domain.
4. Thiết kế scoring và boosting, phân biệt filter bắt buộc.
5. Chọn classic text index, search tích hợp hay hệ search riêng theo SLO.
6. Xác định nguồn sự thật và định danh document ổn định.
7. Thiết kế add/update/delete path với consistency rõ.
8. Nếu đồng bộ bất đồng bộ, áp dụng CDC/outbox và idempotency.
9. Có sourceVersion, xử lý out-of-order và tombstone.
10. Định nghĩa độ trễ source-commit-to-search-visible được chấp nhận.
11. Lập kế hoạch index build, rebuild, catch-up và rollback.
12. Đo query plan, postings, latency, index size, merge load.
13. Đo relevance với test set và nhãn được duyệt.
14. Bảo vệ tenant/ACL và kiểm tra dữ liệu hiện hành trước giao dịch.
15. Giám sát mismatch, indexing lag, queue, retry và lỗi phục hồi.

Một hợp đồng minh họa:

~~~yaml
index: ServiceTextSearch
owner: CatalogService
source:
  entity: Service
  idField: serviceId
  versionField: version
indexedFields:
  - title
  - description
filterFields:
  - tenantId
  - status
analyzer:
  language: Vietnamese
  policy: "Tokenization và normalization theo bộ test domain"
ranking:
  primary: lexicalRelevance
  titleWeight: higherThanDescription
updates:
  mechanism: "CDC/outbox -> search projection"
  deduplication: "serviceId + sourceVersion"
  deletion: versionedTombstone
consistency:
  model: eventual
  objective: "Search visibility lag theo SLO"
security:
  tenantFilter: required
  sourceCheckForBooking: true
recovery:
  rebuild: "snapshot + event catch-up + cutover"
observability:
  - searchLatencyP95
  - indexingLag
  - failedIndexUpdates
  - staleDocumentRate
  - ndcgAt10
~~~

Đây là tài liệu thiết kế, không phải cấu hình được MongoDB, Lucene hay một công cụ search tự động thực thi. Cần hiện thực bằng index mapping, API và pipeline của nền tảng cụ thể.

## 39. Kết luận

**Chỉ mục đảo** giúp truy vấn theo term qua posting lists thay vì quét mọi document. Analyzer quyết định cách văn bản trở thành term; positional postings giúp tìm phrase; thống kê term/document và ranking như BM25 giúp đưa các kết quả phù hợp hơn lên trước.

Nhưng một hệ tìm kiếm đúng còn phải giải quyết **cập nhật chỉ mục**. Document có thể được thêm, sửa, xóa, đổi owner hoặc trạng thái. Cơ chế cập nhật index tích hợp trong database và search projection bất đồng bộ có bảo đảm khác nhau. Source DB commit, index accepted, refresh, durable commit và search visibility là các khái niệm phải phân biệt.

Ba câu hỏi nên luôn được trả lời:

> **Tìm bằng những term nào?** → Analyzer và inverted index.  
> **Kết quả nào xuất hiện trước?** → Query semantics, relevance và filter quyền.  
> **Khi dữ liệu thay đổi, khi nào kết quả đổi theo?** → Update pipeline, version, visibility lag và khả năng rebuild.

Khi ba câu hỏi này có hợp đồng rõ, hệ NoSQL có thể hỗ trợ tìm kiếm văn bản nhanh, đủ chất lượng và vẫn giữ được tính đúng đắn của dữ liệu cùng quyền truy cập trong quá trình vận hành.
