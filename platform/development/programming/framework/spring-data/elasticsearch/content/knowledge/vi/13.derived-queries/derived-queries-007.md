# Phân biệt trường thiếu, chuỗi rỗng và điều kiện `IsEmpty`

Khi xây dựng truy vấn theo tên với Spring Data Elasticsearch, cần phân biệt ba khái niệm thường bị nhầm: field không xuất hiện trong document, field có giá trị là chuỗi rỗng `""`, và điều kiện `IsEmpty` trong tên method của Repository. Chúng không mặc nhiên có cùng ý nghĩa.

Elasticsearch lưu document JSON và lập chỉ mục các giá trị theo mapping. Một field có thể tồn tại trong `_source` nhưng không có giá trị searchable; ngược lại, một chuỗi rỗng vẫn là một giá trị JSON hợp lệ. Spring Data Repository còn có quy tắc phân tích tên method riêng, vì vậy không nên suy luận rằng từ `Empty` trong tên method luôn tương đương với truy vấn chuỗi rỗng hoặc field bị thiếu.

Ví dụ bốn document:

```json
{ "id": "1", "name": "Spring" }
{ "id": "2", "name": "" }
{ "id": "3", "name": null }
{ "id": "4" }
```

Ý nghĩa ở tầng JSON:

- Document `1`: `name` có nội dung `Spring`.
- Document `2`: `name` hiện diện và có giá trị chuỗi rỗng.
- Document `3`: `name` hiện diện với giá trị `null`.
- Document `4`: key `name` không có trong document.

Với mapping thông thường, chuỗi rỗng là một giá trị khác null; `null` tường minh và field bị thiếu thường không tạo giá trị được lập chỉ mục. Vì vậy, `exists` query có thể khớp document `1` và `2`, nhưng không khớp `3` và `4`. Muốn phân biệt null tường minh với field thiếu trong truy vấn, cần lưu thêm thông tin hoặc dùng cơ chế mapping phù hợp; chỉ dựa vào `exists` là chưa đủ.

## 1. Field thiếu và chuỗi rỗng trong Elasticsearch

### Field thiếu

Field bị thiếu nghĩa là key không xuất hiện trong JSON `_source`:

```json
{
  "id": "C-100",
  "email": "an@example.com"
}
```

Document này không có key `name`. Với mapping thông thường, Elasticsearch không có giá trị `name` để lập chỉ mục. Truy vấn `exists` trên `name` không khớp document này.

### Chuỗi rỗng

Chuỗi rỗng là một giá trị chuỗi có độ dài bằng 0:

```json
{
  "id": "C-101",
  "name": ""
}
```

Với field kiểu `keyword`, chuỗi rỗng có thể được lập chỉ mục như một giá trị chính xác và tìm bằng `term` query. Nó cũng được xem là một giá trị hiện diện đối với `exists` query.

Với field kiểu `text`, analyzer có thể không tạo token từ chuỗi rỗng. Do đó, truy vấn full-text trên `text` không phải cách đáng tin cậy để kiểm tra chuỗi rỗng. Nếu cần lọc chính xác giá trị chuỗi, hãy dùng field `keyword` hoặc multi-field `keyword`.

### Null tường minh

Document có thể chứa:

```json
{
  "id": "C-102",
  "name": null
}
```

Mặc định, `null` không được lập chỉ mục như một giá trị thông thường. Với `exists` query, null thường có kết quả giống field thiếu. Tuy nhiên, nếu `_source` được lưu, khi đọc document có thể phân biệt JSON `null` với key không tồn tại.

### Bảng so sánh

| Dữ liệu trong JSON | Có key trong `_source`? | Có giá trị được lập chỉ mục theo mapping thông thường? | `exists` thường khớp? |
|---|---:|---:|---:|
| `"name": "Spring"` | Có | Có | Có |
| `"name": ""` | Có | Có với field keyword; field text có thể không có token để tìm kiếm | Có |
| `"name": null` | Có | Không | Không |
| Không có key `name` | Không | Không | Không |
| `"name": []` | Có | Không có phần tử | Không |
| `"name": [null, "Spring"]` | Có | Có giá trị `Spring` | Có |

Kết quả cụ thể còn phụ thuộc mapping, `null_value`, analyzer, doc values và cách serializer tạo JSON. Bảng trên mô tả hành vi phổ biến của Elasticsearch khi không có cấu hình đặc biệt.

## 2. Khai báo mapping để truy vấn tên chính xác

Nếu yêu cầu có tìm kiếm toàn văn và cũng cần so khớp chính xác, có thể dùng multi-field:

```json
PUT /customers
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
```

Field `name` phục vụ full-text search; subfield `name.keyword` phục vụ so khớp chính xác, sort hoặc aggregation. Nếu chỉ cần tên như một giá trị định danh và không cần full-text search, có thể khai báo `name` trực tiếp là `keyword`.

Với mapping này, document có tên rỗng vẫn có thể được tìm chính xác bằng `name.keyword`:

```json
GET /customers/_search
{
  "query": {
    "term": {
      "name.keyword": ""
    }
  }
}
```

Nếu `name` được map trực tiếp là `keyword`, truy vấn dùng `name` thay vì `name.keyword`.

Không nên dùng `match` query cho việc so sánh chính xác chuỗi rỗng. `match` query phân tích văn bản theo analyzer; với input rỗng, analyzer có thể tạo ra không token và truy vấn không biểu diễn được điều kiện equality mà ứng dụng mong muốn.

## 3. Dùng `exists` để tìm field có giá trị được lập chỉ mục

`exists` query kiểm tra field có giá trị được lập chỉ mục hay không. Nó không đơn giản kiểm tra key có xuất hiện trong JSON `_source`.

Tìm document có `name`:

```json
GET /customers/_search
{
  "query": {
    "exists": {
      "field": "name"
    }
  }
}
```

Với mapping thông thường, kết quả có thể bao gồm cả tên có nội dung và chuỗi rỗng, nhưng loại trừ null và field thiếu.

Tìm document không có giá trị được lập chỉ mục cho `name`:

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "name"
          }
        }
      ]
    }
  }
}
```

Truy vấn này thường khớp document có `name: null` và document thiếu `name`. Nếu mapping có `null_value`, explicit null có thể được lập chỉ mục bằng sentinel và khi đó `exists` sẽ khớp document explicit null.

### Vì sao `exists` không đủ để phân biệt field thiếu và null?

Ở tầng index, cả null và missing đều có thể không tạo ra một giá trị để tìm kiếm. Elasticsearch không thể suy ra từ inverted index rằng key đã được gửi với `null` hay hoàn toàn không xuất hiện trong JSON.

Nếu nghiệp vụ cần phân biệt hai trạng thái, có thể:

- Đọc `_source` và kiểm tra key có hiện diện hay không.
- Lưu thêm field trạng thái, ví dụ `name_provided` hoặc `name_state`.
- Dùng `null_value` nếu muốn explicit null có sentinel riêng trong index.
- Chuẩn hóa dữ liệu tại ứng dụng hoặc ingest pipeline trước khi lập chỉ mục.

## 4. Phân biệt `IsEmpty` trong tên method Repository

Spring Data phân tích tên method repository thành các phần điều kiện dựa trên tên property và keyword. Một số keyword như `IsNull`, `IsNotNull`, `Exists`, `IsTrue`, `IsFalse`, `IsEmpty` và `IsNotEmpty` có ý nghĩa riêng trong query derivation.

Điểm cần nhớ: `IsEmpty` thường được dùng để biểu diễn trạng thái rỗng của collection/array trong các abstraction Spring Data hỗ trợ. Không nên mặc định `findByNameIsEmpty()` sẽ luôn được dịch thành `name = ""`, hoặc thành `must_not exists`, trên mọi phiên bản Spring Data Elasticsearch.

Ví dụ các method có tên dễ gây nhầm:

```java
public interface CustomerRepository
        extends ElasticsearchRepository<CustomerDocument, String> {

    List<CustomerDocument> findByName(String name);

    List<CustomerDocument> findByNameIsNull();

    List<CustomerDocument> findByNameIsNotNull();

    List<CustomerDocument> findByNameIsEmpty();

    List<CustomerDocument> findByNameIsNotEmpty();
}
```

Các method trên chỉ minh họa cú pháp tên method. Việc một keyword được hỗ trợ cho một kiểu property cụ thể và cách nó được chuyển thành Query DSL phụ thuộc phiên bản Spring Data Elasticsearch và query creator đang sử dụng. Đặc biệt, không nên coi `IsEmpty` là cách portable để tìm chuỗi rỗng trong field `String`.

### Truy vấn chuỗi rỗng một cách tường minh

Nếu mục tiêu là tìm tên có giá trị chính xác bằng chuỗi rỗng, dùng `term` query trên field `keyword`:

```java
@Query("{\"term\": {\"name.keyword\": \"\"}}")
List<CustomerDocument> findCustomersWithEmptyName();
```

Tên field trong raw Query DSL phải là tên thực tế trong Elasticsearch mapping. Nếu field được khai báo là `keyword` trực tiếp, dùng `name` thay cho `name.keyword`.

Một lựa chọn khác là dùng `ElasticsearchOperations` hoặc Java API Client để tạo `TermQuery` rõ ràng. Cách này tránh sự mơ hồ giữa keyword `IsEmpty` và giá trị chuỗi rỗng.

### Truy vấn field không có giá trị

Nếu mục tiêu là tìm document không có giá trị được lập chỉ mục, dùng `must_not exists`:

```java
@Query("{\"bool\": {\"must_not\": [{\"exists\": {\"field\": \"name\"}}]}}")
List<CustomerDocument> findCustomersWithoutIndexedName();
```

Tên method nên diễn tả đúng ý nghĩa, chẳng hạn `findCustomersWithoutIndexedName`, thay vì dùng `IsEmpty` nếu điều kiện thực tế là field thiếu/null ở tầng index.

## 5. `IsNull`, `IsNotNull`, `IsEmpty` và chuỗi rỗng

Các keyword sau không nên bị xem là hoán đổi cho nhau:

| Điều kiện mong muốn | Query Elasticsearch thường dùng | Ghi chú |
|---|---|---|
| Field có giá trị được lập chỉ mục | `exists` | Chuỗi rỗng có thể vẫn được xem là có giá trị. |
| Field không có giá trị được lập chỉ mục | `must_not exists` | Có thể bao gồm explicit null và field thiếu. |
| Tên đúng bằng chuỗi rỗng | `term` trên `keyword` với `""` | Đây là equality với một giá trị cụ thể. |
| Tên đúng bằng một chuỗi cụ thể | `term` trên `keyword` hoặc query phù hợp | Chọn field và query theo mapping. |
| Property Java là null | Phụ thuộc converter và query derivation | Không bảo đảm payload có explicit JSON null. |
| Collection không có phần tử | Keyword/query phù hợp cho collection và mapping | `IsEmpty` thường liên quan đến collection; kiểm tra support của phiên bản. |

Với `null_value`, explicit null có thể được lập chỉ mục thành sentinel. Khi đó `exists` có thể khớp explicit null, còn field thiếu vẫn không khớp. `IsNull` trong query derivation không tự động đồng nghĩa với việc so khớp sentinel; cần xác nhận query được tạo ra và mapping thực tế.

## 6. Tích hợp trong Spring Data Elasticsearch

Entity mẫu:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "customers", createIndex = false)
public class CustomerDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(name = "name_exact", type = FieldType.Keyword)
    private String nameExact;

    // getters, setters, constructors
}
```

Trong ví dụ này, ứng dụng có thể dùng `name` cho full-text search và `nameExact` cho equality chính xác. Nếu muốn dùng multi-field `name.keyword`, hãy khai báo mapping multi-field tương ứng ở index; không khai báo property Java riêng cho subfield nếu không có nhu cầu mô hình hóa riêng.

Repository:

```java
public interface CustomerRepository
        extends ElasticsearchRepository<CustomerDocument, String> {

    List<CustomerDocument> findByName(String name);

    List<CustomerDocument> findByNameExact(String name);
}
```

`findByNameExact("")` diễn tả rõ hơn một equality condition trên property `nameExact` nếu query creator của phiên bản đang dùng hỗ trợ method này theo mapping. Nếu cần bảo đảm raw Query DSL chính xác, dùng `@Query` hoặc `ElasticsearchOperations` với `term` query.

Đối với query method được suy ra từ property, Spring Data dùng tên property Java để xác định field. Đối với raw JSON trong `@Query`, cần dùng tên field Elasticsearch trong mapping, ví dụ `name_exact` hoặc `name.keyword`.

## 7. Serialization có thể biến null thành field thiếu

Một entity Java có property `name = null` không bảo đảm Elasticsearch nhận JSON:

```json
{
  "name": null
}
```

Converter hoặc serializer có thể loại bỏ property null trước khi gửi request. Nếu field bị bỏ khỏi payload, Elasticsearch nhận field thiếu; `null_value` không được kích hoạt vì nó chỉ áp dụng cho null tường minh.

Ví dụ Java:

```java
CustomerDocument customer = new CustomerDocument();
customer.setId("C-200");
customer.setName(null);
```

Để hiểu đúng kết quả, hãy kiểm tra:

1. Cấu hình converter/serializer đang dùng.
2. Request JSON thực tế được gửi đến Elasticsearch.
3. `_source` sau khi lưu.
4. Mapping của field `name`, bao gồm `null_value`, `index` và analyzer.

Nếu yêu cầu nghiệp vụ là “client không gửi field” khác với “client gửi null”, cần giữ lại trạng thái đó một cách tường minh. Một property Java nullable đơn lẻ có thể không đủ để biểu diễn cả hai trạng thái khi deserialize request.

## 8. Mô hình hóa trạng thái rõ ràng ở ứng dụng

Trong một số nghiệp vụ, ba trạng thái sau có ý nghĩa khác nhau:

- Chưa cung cấp tên.
- Người dùng chủ động xóa tên hoặc đặt tên thành null.
- Người dùng nhập chuỗi rỗng.

Có thể biểu diễn rõ bằng field trạng thái riêng:

```json
{
  "name": null,
  "name_state": "EXPLICIT_NULL"
}
```

Hoặc:

```json
{
  "name": "",
  "name_state": "EMPTY"
}
```

Và document không có `name` có thể mang `name_state: "NOT_PROVIDED"` nếu cần tìm kiếm trạng thái đó mà không phải đọc toàn bộ `_source`.

Trong Spring, có thể dùng enum:

```java
public enum NameState {
    PRESENT,
    EMPTY,
    EXPLICIT_NULL,
    NOT_PROVIDED
}
```

Việc lưu trạng thái riêng làm rõ hợp đồng dữ liệu, nhưng cần bảo đảm các field được cập nhật nhất quán. Nên chuẩn hóa trạng thái ở service hoặc ingest pipeline thay vì để mỗi caller tự gán tùy ý.

## 9. Ví dụ truy vấn theo từng trạng thái

Giả sử `name_exact` là field `keyword`:

### Tìm tên rỗng

```json
GET /customers/_search
{
  "query": {
    "term": {
      "name_exact": ""
    }
  }
}
```

### Tìm tên có nội dung bất kỳ

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "filter": [
        { "exists": { "field": "name_exact" } }
      ],
      "must_not": [
        { "term": { "name_exact": "" } }
      ]
    }
  }
}
```

Query này loại chuỗi rỗng và chỉ giữ document có giá trị `name_exact` được lập chỉ mục. Nếu dữ liệu có khoảng trắng như `"   "`, giá trị vẫn khác chuỗi rỗng; cần normalize ở ứng dụng nếu muốn coi whitespace-only là rỗng.

### Tìm field thiếu hoặc null không có sentinel

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "must_not": [
        { "exists": { "field": "name_exact" } }
      ]
    }
  }
}
```

Query này không phân biệt explicit null và missing. Nếu `null_value` được cấu hình, explicit null có thể được lập chỉ mục bằng sentinel và không còn xuất hiện trong kết quả này.

### Tìm một trạng thái cụ thể

Nếu đã lưu `name_state` kiểu `keyword`, có thể query chính xác:

```json
GET /customers/_search
{
  "query": {
    "term": {
      "name_state": "EXPLICIT_NULL"
    }
  }
}
```

Đây là cách rõ ràng khi trạng thái null/missing có ý nghĩa nghiệp vụ và cần truy vấn thường xuyên.

## 10. Kiểm thử `IsEmpty` và query thực tế

Không nên chỉ dựa vào tên method để kết luận query được gửi đến Elasticsearch. Hãy kiểm thử trên đúng phiên bản Spring Data Elasticsearch và mapping của dự án.

Một integration test nên tạo các document đại diện:

```json
{ "id": "1", "name": "Spring", "name_exact": "Spring" }
{ "id": "2", "name": "", "name_exact": "" }
{ "id": "3", "name": null, "name_state": "EXPLICIT_NULL" }
{ "id": "4", "name_state": "NOT_PROVIDED" }
```

Sau đó xác minh:

1. `exists(name_exact)` trả về document có tên `Spring` và chuỗi rỗng.
2. `term(name_exact, "")` chỉ trả về document có giá trị chuỗi rỗng.
3. `must_not exists(name_exact)` trả về các document không có giá trị được lập chỉ mục.
4. Raw query trong `@Query` dùng đúng field name trong mapping.
5. Query method `IsEmpty` nếu được dùng có semantics đúng với kiểu property và phiên bản thư viện.
6. Serializer không âm thầm biến explicit null thành missing ngoài ý muốn.

Có thể kiểm tra request Query DSL thực tế bằng logging phù hợp ở môi trường test hoặc dùng Elasticsearch Java API Client để tạo query rõ ràng. Đồng thời đọc `_mapping` và `_source` để xác định khác biệt giữa dữ liệu JSON và dữ liệu searchable.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `findByNameIsEmpty()` không tìm chuỗi rỗng | `IsEmpty` được hiểu theo semantics collection hoặc không được query creator hỗ trợ cho String như kỳ vọng. | Dùng equality query rõ ràng trên field `keyword`; kiểm tra phiên bản. |
| `exists` khớp document có tên rỗng | Chuỗi rỗng vẫn là giá trị, khác null/missing. | Dùng `term` với `""` để lọc riêng chuỗi rỗng. |
| `exists` không khớp document có `name: null` | Null không được lập chỉ mục mặc định. | Dùng `null_value`, field trạng thái hoặc đọc `_source` nếu cần phân biệt. |
| Query `must_not exists` trả cả null và missing | Cả hai đều không có giá trị được lập chỉ mục. | Lưu trạng thái explicit null/missing riêng nếu cần query phân biệt. |
| Query chuỗi rỗng trên field text không có kết quả | Analyzer không tạo token từ chuỗi rỗng. | Dùng field `keyword` hoặc multi-field cho equality. |
| `name = null` trong Java nhưng Elasticsearch coi là missing | Converter/serializer loại bỏ property null. | Kiểm tra payload JSON và cấu hình serialization. |
| Chuỗi chỉ có khoảng trắng không được coi là rỗng | Whitespace khác chuỗi `""`. | Trim/normalize và validate trước khi index. |
| Raw `@Query` không tìm thấy field | JSON dùng tên property Java thay vì tên field Elasticsearch. | Dùng đúng field name trong mapping. |

## 12. Quy tắc thiết kế

- Dùng `keyword` hoặc multi-field `keyword` nếu cần so khớp tên chính xác, bao gồm chuỗi rỗng.
- Dùng `text` cho full-text search; không dùng `match` để kiểm tra equality của chuỗi rỗng.
- Dùng `exists` để kiểm tra có giá trị được lập chỉ mục, không dùng nó như phép kiểm tra key trong `_source`.
- Dùng `must_not exists` để tìm document không có giá trị được lập chỉ mục; hiểu rằng nó có thể gồm cả null và missing.
- Dùng `term` trên keyword field với `""` khi cần tìm chuỗi rỗng.
- Không giả định `IsEmpty` trong derived query có nghĩa là `name = ""`; kiểm tra semantics của kiểu property và phiên bản Spring Data Elasticsearch.
- Dùng `IsEmpty`/`IsNotEmpty` theo đúng kiểu dữ liệu và support của query derivation, thường liên quan đến collection/array.
- Dùng `null_value` hoặc field trạng thái riêng khi explicit null cần được truy vấn.
- Kiểm tra converter/serializer để bảo đảm explicit null không bị biến thành field thiếu ngoài ý muốn.
- Chuẩn hóa whitespace ở tầng ứng dụng nếu nghiệp vụ coi chuỗi chỉ có khoảng trắng là rỗng.

## 13. Những điểm cần nhớ

- Field thiếu, explicit null và chuỗi rỗng là các trạng thái JSON khác nhau.
- Chuỗi rỗng là giá trị hợp lệ; với `keyword`, có thể tìm bằng `term` query.
- `exists` kiểm tra giá trị được lập chỉ mục, không kiểm tra đơn thuần sự hiện diện của key trong `_source`.
- `must_not exists` thường trả cả field null và field thiếu khi không có `null_value`.
- `IsEmpty` là keyword của Spring Data query derivation; không mặc định tương đương chuỗi rỗng hoặc field thiếu.
- Với `String`, dùng equality/term query rõ ràng trên field keyword để tìm `""`.
- Với collection, xác nhận `IsEmpty` được hỗ trợ cho repository/query creator và kiểu field của phiên bản đang dùng.
- Raw Query DSL trong `@Query` cần tên field Elasticsearch; query method thường tham chiếu property Java.
- Nếu phải phân biệt explicit null và missing trong query, lưu trạng thái riêng hoặc dùng sentinel có chủ đích.

Hiểu đúng field thiếu, chuỗi rỗng và `IsEmpty` giúp các truy vấn theo tên trong Spring Data Elasticsearch có semantics rõ ràng. Hãy xác định trạng thái cần tìm ở tầng JSON, chọn mapping phù hợp, dùng query tường minh cho chuỗi rỗng và kiểm tra query thực tế được tạo ra bởi phiên bản Spring Data đang chạy.
