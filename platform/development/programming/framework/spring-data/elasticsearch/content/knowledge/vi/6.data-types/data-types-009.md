# Giá trị null, trường thiếu, chuỗi rỗng và `null_value`

Khi lưu document JSON vào Elasticsearch, một thuộc tính có thể ở nhiều trạng thái khác nhau: không xuất hiện trong document, xuất hiện với giá trị `null`, chứa chuỗi rỗng `""`, hoặc chứa một giá trị cụ thể. Những trạng thái này dễ bị xem là tương đương trong code Java, nhưng chúng có ý nghĩa khác nhau khi lưu trữ, lập chỉ mục và truy vấn.

Elasticsearch còn cung cấp mapping parameter `null_value` để thay thế giá trị `null` tường minh bằng một giá trị đại diện khi lập chỉ mục. Cơ chế này giúp truy vấn các document có trường được gửi với `null`, nhưng không biến `null_value` thành giá trị mặc định trong `_source` và cũng không tự xử lý các trường bị thiếu.

Ví dụ, xét bốn document:

```json
{ "id": "1", "nickname": "An" }
{ "id": "2", "nickname": null }
{ "id": "3", "nickname": "" }
{ "id": "4" }
```

Ý nghĩa:

- Document `1`: `nickname` có giá trị là chuỗi `An`.
- Document `2`: field có mặt trong JSON nhưng giá trị là `null`.
- Document `3`: field có mặt và giá trị là chuỗi rỗng.
- Document `4`: field `nickname` không xuất hiện.

Sự khác biệt này ảnh hưởng đến `exists` query, `term` query, aggregation, sort, validation trong Spring và cách ứng dụng chuyển đổi entity thành JSON.

## 1. Phân biệt bốn trạng thái dữ liệu

| Trạng thái | JSON | Ý nghĩa |
|---|---|---|
| Có giá trị | `"nickname": "An"` | Field hiện diện và có giá trị cụ thể. |
| Giá trị null | `"nickname": null` | Field hiện diện trong JSON nhưng không có giá trị. |
| Chuỗi rỗng | `"nickname": ""` | Field hiện diện với một chuỗi có độ dài bằng 0. |
| Field thiếu | Không có key `nickname` | Document không cung cấp field đó. |

Đây là các trạng thái ở tầng JSON. Khi lập chỉ mục, Elasticsearch có quy tắc riêng để quyết định field nào có giá trị searchable. Không phải mọi trạng thái có mặt trong `_source` đều tạo ra một giá trị trong inverted index hoặc doc values.

### Field null và field thiếu

Với mapping thông thường, một giá trị `null` không được lập chỉ mục như một giá trị có thể tìm kiếm. Field bị thiếu cũng không có giá trị để lập chỉ mục. Vì vậy, `exists` query thường xem cả hai trường hợp này là không tồn tại.

Tuy nhiên, nếu `_source` được bật và giữ nguyên dữ liệu đầu vào, khi đọc `_source` vẫn có thể phân biệt:

```json
{ "nickname": null }
```

với:

```json
{}
```

Khả năng phân biệt ở `_source` phụ thuộc document thực tế được gửi và cấu hình lưu `_source`. Custom converter hoặc serializer ở phía ứng dụng có thể loại bỏ property null trước khi gửi request, khiến Elasticsearch chỉ nhận document không có field.

### Chuỗi rỗng khác null

Chuỗi `""` là một giá trị chuỗi, không phải JSON null. Với field `keyword`, chuỗi rỗng có thể được lập chỉ mục như một giá trị chính xác và có thể được tìm bằng `term` query.

Với field `text`, chuỗi rỗng có thể không tạo token văn bản sau analyzer, nhưng field vẫn được xem là có giá trị đối với `exists` theo semantics của Elasticsearch. Nếu nghiệp vụ cần phân biệt chuỗi rỗng, hãy kiểm tra loại field và analyzer thực tế.

Chuỗi chỉ chứa khoảng trắng như `"   "` cũng không tự động tương đương `null`. Ứng dụng nên trim/normalize và validate dữ liệu theo quy tắc nghiệp vụ trước khi index nếu khoảng trắng không có ý nghĩa.

## 2. `exists` query nhìn nhận null, thiếu và chuỗi rỗng như thế nào?

`exists` query tìm document có giá trị được lập chỉ mục cho một field. Đây không phải phép kiểm tra xem key có xuất hiện trong JSON `_source` hay không.

Với mapping thông thường không khai báo `null_value`, quy tắc phổ biến là:

| Giá trị đầu vào | `exists` query |
|---|---|
| `"An"` | Khớp |
| `null` | Không khớp |
| `""` | Khớp |
| Field bị thiếu | Không khớp |
| `[]` | Không khớp |
| `[null]` | Không khớp nếu không có `null_value` áp dụng |
| `[null, "An"]` | Khớp vì có giá trị `An` |

Ví dụ query tìm document có nickname:

```json
GET /customers/_search
{
  "query": {
    "exists": {
      "field": "nickname"
    }
  }
}
```

Tìm document không có giá trị nickname được lập chỉ mục:

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "nickname"
          }
        }
      ]
    }
  }
}
```

Kết quả của query thứ hai có thể bao gồm cả document có `nickname: null` và document thiếu `nickname`. Nếu cần phân biệt hai trường hợp, phải xem `_source` hoặc lưu một field trạng thái riêng; `exists` không thể tự phân biệt khi cả hai đều không tạo giá trị được lập chỉ mục.

### Vì sao `exists` không phải kiểm tra key trong JSON?

Một field có thể xuất hiện trong `_source` nhưng không searchable, ví dụ:

- Giá trị là `null` và không có `null_value`.
- Giá trị là mảng rỗng `[]`.
- Field có `index: false` và không có doc values.
- Giá trị không được lập chỉ mục do cấu hình mapping hoặc quá trình xử lý dữ liệu.

Ngược lại, một chuỗi rỗng trong field được lập chỉ mục có thể được coi là có giá trị. Vì vậy, nếu câu hỏi nghiệp vụ là “JSON có chứa key này không?”, `exists` không nhất thiết trả lời đúng câu hỏi đó.

## 3. `null_value` hoạt động như thế nào?

Mapping parameter `null_value` cho phép thay thế một giá trị JSON `null` tường minh bằng một giá trị đại diện khi Elasticsearch lập chỉ mục field. Giá trị gốc trong `_source` không bị thay thế.

Ví dụ mapping:

```json
PUT /customers
{
  "mappings": {
    "properties": {
      "nickname": {
        "type": "keyword",
        "null_value": "__NULL__"
      },
      "age": {
        "type": "integer",
        "null_value": -1
      }
    }
  }
}
```

Index document:

```json
POST /customers/_doc/1
{
  "nickname": null,
  "age": null
}
```

Khi lập chỉ mục, Elasticsearch dùng `__NULL__` cho `nickname` và `-1` cho `age`. Có thể tìm document bằng giá trị đại diện:

```json
GET /customers/_search
{
  "query": {
    "term": {
      "nickname": "__NULL__"
    }
  }
}
```

Và `exists` query trên `nickname` có thể khớp document này vì `null_value` đã cung cấp một giá trị để lập chỉ mục.

### `null_value` không sửa `_source`

Sau khi index document trên, đọc lại document:

```http
GET /customers/_doc/1
```

Phần `_source` vẫn thể hiện giá trị đầu vào:

```json
{
  "nickname": null,
  "age": null
}
```

`null_value` chỉ thay đổi cách Elasticsearch lập chỉ mục giá trị null; nó không ghi đè dữ liệu gốc trong `_source` và không biến null thành một giá trị mặc định trong object Java.

### `null_value` chỉ áp dụng cho null tường minh

Các trường hợp sau cần phân biệt:

| Đầu vào | Có dùng `null_value` không? |
|---|---|
| `"nickname": null` | Có, nếu field type và giá trị thay thế hợp lệ. |
| Không có key `nickname` | Không. |
| `"nickname": ""` | Không; đây là chuỗi rỗng. |
| `"nickname": []` | Không có phần tử để thay thế. |
| `"nickname": [null, "An"]` | Giá trị null trong mảng có thể được thay bằng sentinel theo mapping, đồng thời `An` vẫn là giá trị khác. |

Không dùng `null_value` như một default value cho mọi document thiếu field. Nếu muốn field luôn có giá trị mặc định, ứng dụng hoặc ingest pipeline phải chủ động thêm giá trị khi field không được gửi.

## 4. Chọn giá trị sentinel cho `null_value`

Giá trị `null_value` là một sentinel đại diện cho null. Cần chọn giá trị sao cho:

- Hợp lệ với kiểu mapping của field.
- Không bị nhầm với giá trị nghiệp vụ thực tế.
- Dễ nhận diện khi truy vấn, aggregation hoặc xử lý dữ liệu.
- Không tạo ra sai lệch trong sort, range query hoặc thống kê.

Ví dụ:

| Kiểu field | Sentinel minh họa | Lưu ý |
|---|---|---|
| `keyword` | `"__NULL__"` | Chọn chuỗi không thể là giá trị hợp lệ theo domain. |
| `integer` | `-1` | Chỉ phù hợp nếu số âm không phải giá trị hợp lệ. |
| `long` | `-1` | Kiểm tra domain và range query. |
| `boolean` | `false` | Thường không phù hợp nếu `false` có ý nghĩa nghiệp vụ riêng. |
| `date` | Một ngày quy ước | Cần tránh va chạm với ngày hợp lệ và thống nhất format. |

Không phải mọi kiểu field đều hỗ trợ mọi dạng sentinel. Giá trị `null_value` phải tương thích với kiểu mapping và các giới hạn của phiên bản Elasticsearch. Ví dụ field `integer` không thể dùng sentinel là chuỗi `"UNKNOWN"`.

### Rủi ro khi dùng `-1` cho số

Giả sử `age` dùng `null_value: -1`. Khi aggregate hoặc sort, giá trị `-1` được xem là giá trị số đã lập chỉ mục. Nếu ứng dụng không loại sentinel, kết quả thống kê có thể bị ảnh hưởng.

Ví dụ aggregation:

```json
GET /customers/_search
{
  "size": 0,
  "aggs": {
    "average_age": {
      "avg": {
        "field": "age",
        "missing": 0
      }
    }
  }
}
```

Ở đây `missing` trong aggregation có nghĩa là dùng giá trị thay thế cho document không có giá trị được lập chỉ mục ở field `age`. Nó không xóa hoặc bỏ qua sentinel `-1` đã được lập chỉ mục bởi `null_value`. Nếu muốn loại các document có sentinel khỏi phép tính, hãy lọc chúng ra trong query/filter aggregation hoặc thiết kế field trạng thái riêng.

Đừng nhầm `null_value` trong mapping với thuộc tính `missing` của aggregation. Một cái thay giá trị null lúc index; cái còn lại cung cấp giá trị cho document thiếu field khi tính aggregation.

## 5. Null trong mảng và object lồng nhau

Elasticsearch xử lý field đa trị theo các giá trị có trong mảng. Mảng rỗng không cung cấp giá trị cho field. Mảng chứa null có thể được xem như không có giá trị nếu không cấu hình `null_value`.

Ví dụ:

```json
{ "tags": [] }
{ "tags": [null] }
{ "tags": ["spring", "elasticsearch"] }
{ "tags": [null, "spring"] }
```

Với `tags` kiểu `keyword` không có `null_value`, hai document đầu không có giá trị để `exists` khớp; hai document sau có ít nhất một giá trị chuỗi. Nếu mapping có `null_value`, phần tử null tường minh có thể được thay bằng sentinel khi lập chỉ mục.

Ví dụ:

```json
PUT /articles
{
  "mappings": {
    "properties": {
      "tags": {
        "type": "keyword",
        "null_value": "__NULL_TAG__"
      }
    }
  }
}
```

Document `{"tags": [null, "spring"]}` có thể được truy vấn theo `__NULL_TAG__` và `spring`. `_source` vẫn giữ cấu trúc mảng ban đầu nếu được lưu.

Với object lồng nhau, mỗi property có mapping riêng. `null_value` phải được khai báo trên field con cần xử lý, không phải trên toàn bộ object:

```json
PUT /customers
{
  "mappings": {
    "properties": {
      "address": {
        "properties": {
          "city": {
            "type": "keyword",
            "null_value": "__NO_CITY__"
          }
        }
      }
    }
  }
}
```

Document:

```json
{
  "address": {
    "city": null
  }
}
```

Field cần truy vấn là `address.city`. Nếu toàn bộ `address` bị thiếu hoặc là `null`, không có giá trị `address.city` để thay thế. Nếu `address` là object nhưng thiếu `city`, `null_value` của `city` cũng không tự điền giá trị.

## 6. `null_value` và dynamic mapping

Dynamic mapping có thể tự suy luận kiểu field khi Elasticsearch nhận giá trị có thể dùng để xác định kiểu. Một giá trị `null` không cung cấp đủ thông tin để suy ra kiểu dữ liệu của field.

Ví dụ document đầu tiên:

```json
POST /dynamic-customers/_doc/1
{
  "nickname": null
}
```

Elasticsearch không thể suy ra `nickname` nên là `keyword`, `text`, `integer` hay kiểu khác chỉ từ giá trị null. Nếu sau đó một document gửi `nickname` là chuỗi, dynamic mapping có thể tạo mapping dựa trên giá trị chuỗi đó.

Nếu cần `null_value`, nên khai báo mapping tường minh trước khi index dữ liệu:

```json
PUT /dynamic-customers
{
  "mappings": {
    "properties": {
      "nickname": {
        "type": "keyword",
        "null_value": "__NULL__"
      }
    }
  }
}
```

Không nên trông chờ dynamic mapping tự tạo `null_value` hoặc tự đoán quy tắc null theo nghiệp vụ.

## 7. Ánh xạ null trong Spring Data Elasticsearch

Trong Java, cần phân biệt kiểu primitive và wrapper:

| Java type | Có thể biểu diễn null? | Ý nghĩa khi đọc dữ liệu thiếu |
|---|---|---|
| `boolean` | Không | Giá trị mặc định trong Java là `false`, dễ làm mất thông tin “không được cung cấp”. |
| `Boolean` | Có | Có thể biểu diễn `true`, `false` hoặc `null`. |
| `int` | Không | Giá trị mặc định là `0`. |
| `Integer` | Có | Có thể phân biệt `0` với `null`. |
| `long` | Không | Giá trị mặc định là `0L`. |
| `Long` | Có | Có thể phân biệt `0L` với `null`. |
| `String` | Có | Có thể là `null`, `""` hoặc chuỗi có nội dung. |

Với dữ liệu có thể thiếu hoặc null, wrapper type thường phù hợp hơn primitive vì giữ được trạng thái chưa biết/chưa cung cấp.

Entity ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "customers", createIndex = false)
public class CustomerDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword, nullValue = "__NULL__")
    private String nickname;

    @Field(type = FieldType.Integer, nullValue = "-1")
    private Integer age;

    private Boolean active;

    // constructors, getters, setters
}
```

Trong các phiên bản Spring Data Elasticsearch có hỗ trợ thuộc tính `nullValue` trên `@Field`, annotation có thể được dùng để mô tả sentinel của field. Cú pháp và kiểu giá trị cần kiểm tra theo đúng phiên bản thư viện đang sử dụng; mapping JSON thực tế trên Elasticsearch vẫn là nơi xác nhận cuối cùng.

Nếu phiên bản hoặc kiểu mapping không hỗ trợ khai báo qua annotation như mong muốn, có thể quản lý mapping bằng settings/mapping resource hoặc `IndexOperations` khi tạo index. Không nên giả định rằng `@Field` tự thay đổi mapping của index đã tồn tại.

### Null trong Java có được gửi thành JSON null không?

Không nên chỉ nhìn vào giá trị Java để kết luận Elasticsearch đã nhận JSON null. Kết quả phụ thuộc vào converter và cấu hình serialization của ứng dụng. Spring Data Elasticsearch sử dụng mapping converter để chuyển entity thành document; ứng dụng cũng có thể có custom converter hoặc cách tạo request riêng.

Ví dụ entity:

```java
CustomerDocument customer = new CustomerDocument();
customer.setId("C-100");
customer.setNickname(null);
customer.setAge(null);
```

Trước khi trông chờ `null_value`, hãy xác nhận payload thực tế hoặc đọc lại `_source` sau khi lưu. Nếu field null đã bị loại bỏ trước khi gửi, Elasticsearch nhận một field thiếu và `null_value` không được kích hoạt.

### Validation ở tầng ứng dụng

Mapping không phải công cụ bắt buộc field xuất hiện trong mọi document. Nếu nghiệp vụ yêu cầu nickname phải có nội dung, hãy kiểm tra ở tầng ứng dụng bằng Bean Validation hoặc domain validation:

```java
public class CustomerRequest {

    @NotBlank
    private String nickname;

    @NotNull
    private Boolean active;
}
```

`@NotNull` chỉ yêu cầu giá trị khác null; chuỗi rỗng vẫn có thể hợp lệ theo constraint đó. `@NotBlank` yêu cầu chuỗi không null và có ít nhất một ký tự không phải khoảng trắng. Chọn constraint theo quy tắc nghiệp vụ, không dùng `null_value` để thay thế validation.

## 8. Query để phân biệt null, thiếu và chuỗi rỗng

### Tìm document có giá trị field

```json
GET /customers/_search
{
  "query": {
    "exists": {
      "field": "nickname"
    }
  }
}
```

### Tìm document không có giá trị được lập chỉ mục

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "nickname"
          }
        }
      ]
    }
  }
}
```

Không có `null_value`, query này thường khớp cả explicit null và field thiếu.

### Tìm document có chuỗi rỗng

Với field `keyword`:

```json
GET /customers/_search
{
  "query": {
    "term": {
      "nickname": ""
    }
  }
}
```

### Tìm document có explicit null đã được thay bằng sentinel

```json
GET /customers/_search
{
  "query": {
    "term": {
      "nickname": "__NULL__"
    }
  }
}
```

Query này tìm các document mà giá trị null tường minh đã được lập chỉ mục bằng `null_value`. Nó không tìm field bị thiếu.

### Tìm document thiếu field, loại trừ null đã được thay sentinel

Khi mapping có `null_value`, document explicit null có giá trị sentinel và `exists` sẽ khớp. Vì vậy, query `must_not exists` chỉ lấy những document không có giá trị được lập chỉ mục, chẳng hạn field thiếu hoặc mảng rỗng:

```json
GET /customers/_search
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "nickname"
          }
        }
      ]
    }
  }
}
```

Nếu cần phân biệt explicit null với missing trong kết quả, có thể dùng `_source` để kiểm tra sự hiện diện của key hoặc lưu thêm field trạng thái như `nickname_provided`.

## 9. Phân biệt `null_value`, default value và aggregation `missing`

Ba khái niệm thường bị nhầm:

| Cơ chế | Thời điểm hoạt động | Tác động |
|---|---|---|
| `null_value` mapping | Khi Elasticsearch lập chỉ mục giá trị null tường minh. | Thay null bằng sentinel trong index; `_source` vẫn giữ null. |
| Default value ở ứng dụng | Trước khi gửi document. | Ghi một giá trị thật vào document nếu ứng dụng quyết định điền mặc định. |
| `missing` trong aggregation | Khi chạy aggregation trên document không có giá trị được lập chỉ mục cho field. | Dùng giá trị thay thế chỉ trong phép tính aggregation đó. |

Ví dụ ứng dụng đặt default:

```java
if (customer.getActive() == null) {
    customer.setActive(true);
}
```

Trong trường hợp này, document được ghi với `active: true`; đây là giá trị thật của document. `null_value` lại chỉ tạo giá trị sentinel cho indexing, còn `_source` vẫn giữ null.

Aggregation `missing` chỉ ảnh hưởng phép tính:

```json
GET /customers/_search
{
  "size": 0,
  "aggs": {
    "age_distribution": {
      "terms": {
        "field": "age",
        "missing": -1
      }
    }
  }
}
```

Document không có giá trị `age` được tính vào bucket `-1` trong aggregation này. Điều đó không cập nhật `_source`, không thay mapping và không làm document trở thành có giá trị age trong các query khác.

## 10. Thay đổi `null_value` trên index đã tồn tại

Mapping được tạo ra cho index đang chạy là hợp đồng dữ liệu của index. Nếu field đã được khai báo với mapping không có `null_value`, việc thêm sentinel sau này không tự lập chỉ mục lại các document cũ.

Khi cần thay đổi cách xử lý null cho field đã tồn tại, hãy kiểm tra khả năng cập nhật mapping của phiên bản Elasticsearch. Với thay đổi mapping parameter không thể cập nhật tại chỗ hoặc cần áp dụng nhất quán cho dữ liệu cũ, quy trình an toàn thường là:

1. Tạo index mới với mapping có `null_value`.
2. Reindex document từ index cũ sang index mới.
3. Xác minh `_source`, mapping và kết quả query cho các trường hợp null, missing, empty string.
4. Đồng bộ dữ liệu phát sinh trong lúc reindex.
5. Chuyển alias sang index mới.
6. Giữ index cũ trong thời gian rollback.

Reindex chỉ có thể áp dụng sentinel cho những document mà `_source` còn giữ explicit null. Nếu dữ liệu cũ đã bị serializer loại bỏ null thành field thiếu, Elasticsearch không thể suy ra từ index cũ rằng key từng được gửi với null. Khi đó cần bổ sung thông tin từ hệ thống nguồn hoặc quy tắc migration.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `exists` không tìm thấy document có `field: null` | Null không tạo giá trị được lập chỉ mục nếu không có `null_value`. | Dùng `_source` để phân biệt hoặc cấu hình sentinel cho dữ liệu mới/reindex. |
| `exists` tìm thấy field có `""` | Chuỗi rỗng là giá trị khác null. | Validate/normalize chuỗi rỗng ở ứng dụng nếu nghiệp vụ coi là không hợp lệ. |
| `null_value` không được áp dụng | Serializer đã bỏ field null hoặc field thực tế bị thiếu. | Kiểm tra payload và `_source`; bảo đảm gửi explicit JSON null. |
| Document thiếu field vẫn không có sentinel | `null_value` không áp dụng cho field bị thiếu. | Điền default ở ứng dụng hoặc ingest pipeline nếu cần. |
| Aggregation có bucket `-1` không mong muốn | Sentinel của `null_value` được xem là giá trị số thật trong index. | Lọc sentinel hoặc dùng field trạng thái riêng; cân nhắc sentinel khác. |
| Dynamic mapping không tạo field sau document null đầu tiên | Null không đủ thông tin để suy luận kiểu. | Khai báo mapping tường minh trước khi index. |
| Primitive Java trả `false`/`0` dù dữ liệu thiếu | Primitive có giá trị mặc định và không biểu diễn null. | Dùng wrapper `Boolean`, `Integer`, `Long` khi cần trạng thái chưa biết. |
| Đổi annotation nhưng index cũ không đổi | Annotation không tự migration mapping đã tồn tại. | Tạo index mới/reindex hoặc chạy migration mapping phù hợp. |

## 12. Quy tắc thiết kế dữ liệu

- Dùng `null` khi field được biết là chưa có giá trị hoặc không áp dụng, theo quy tắc nghiệp vụ.
- Bỏ field khi muốn biểu diễn trạng thái không được cung cấp hoặc không thuộc document.
- Dùng chuỗi rỗng chỉ khi nó thực sự là một giá trị có ý nghĩa; nếu không, chuẩn hóa thành null hoặc loại bỏ field ở tầng ứng dụng.
- Chọn wrapper type trong Java khi cần phân biệt `false` với chưa biết, hoặc `0` với chưa cung cấp.
- Dùng `null_value` khi cần truy vấn explicit null như một giá trị sentinel.
- Không dùng sentinel có thể va chạm với dữ liệu hợp lệ.
- Không xem `null_value` là default value, validation hoặc cơ chế bắt buộc field.
- Kiểm tra converter/serializer để biết null có được gửi thành JSON null hay bị bỏ qua.
- Lưu field trạng thái riêng nếu ứng dụng cần phân biệt rõ “null được gửi” và “field không được gửi” trong truy vấn.
- Kiểm tra mapping thực tế và `_source` thay vì chỉ dựa vào annotation Java.

## 13. Những điểm cần nhớ

- Field thiếu, explicit `null` và chuỗi rỗng là ba trạng thái JSON khác nhau.
- `exists` kiểm tra giá trị được lập chỉ mục, không đơn giản kiểm tra key trong `_source`.
- Không có `null_value`, explicit null và field thiếu thường đều không khớp `exists`.
- Chuỗi rỗng có thể được xem là có giá trị; với `keyword`, có thể tìm bằng `term` query.
- `null_value` thay explicit null bằng sentinel khi index; nó không thay đổi `_source`.
- `null_value` không điền giá trị cho field bị thiếu hoặc mảng rỗng.
- `null_value` có thể làm sentinel tham gia vào `exists`, term query, sort và aggregation như một giá trị đã index.
- Dynamic mapping không suy luận được kiểu field chỉ từ null; khai báo mapping rõ ràng khi cần null handling.
- Trong Java, wrapper type giữ được null còn primitive có giá trị mặc định.
- `null_value`, default value ở ứng dụng và `missing` của aggregation là ba cơ chế khác nhau.
- Khi thay đổi mapping cho dữ liệu cũ, cần đánh giá reindex và khả năng khôi phục explicit null từ `_source`.

Hiểu đúng sự khác nhau giữa null, field thiếu và chuỗi rỗng giúp ứng dụng Spring Data Elasticsearch tránh lỗi truy vấn và sai lệch dữ liệu. Hãy xác định ý nghĩa nghiệp vụ của từng trạng thái, cấu hình mapping phù hợp, kiểm tra dữ liệu JSON thực tế và dùng `null_value` như một sentinel có chủ đích thay vì xem nó là cơ chế tự động điền mặc định.
