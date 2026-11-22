# Normalizer cho keyword và tìm kiếm không phân biệt hoa thường

Trong Elasticsearch, field kiểu `keyword` thường dùng để lưu các giá trị cần so khớp chính xác như username, email, mã sản phẩm, trạng thái hoặc tên nhóm. Tuy nhiên, so khớp chính xác theo mặc định cũng phân biệt chữ hoa và chữ thường. Ví dụ, `Alice`, `ALICE` và `alice` là các giá trị khác nhau.

**Normalizer** cho phép chuẩn hóa giá trị của field `keyword` trước khi Elasticsearch lập chỉ mục và khi xử lý giá trị tìm kiếm. Nhờ đó, ứng dụng có thể tìm kiếm không phân biệt hoa thường mà vẫn giữ được semantics của một giá trị keyword: toàn bộ chuỗi được xem là một giá trị, không bị tách thành nhiều token như field `text`.

Bài này tập trung vào normalizer, đặc biệt là bộ lọc `lowercase` và `asciifolding`, cách khai báo mapping, cách truy vấn và cách tích hợp với Spring Data Elasticsearch.

## 1. Phân biệt keyword, text và normalizer

Hai kiểu field thường gặp là `keyword` và `text`:

| Đặc điểm | `keyword` | `text` |
|---|---|---|
| Mục đích | Giá trị nguyên vẹn, lọc chính xác, sort, aggregation | Nội dung văn bản cần tìm kiếm toàn văn |
| Phân tích thành token | Không dùng analyzer để tách từ | Có analyzer để phân tích nội dung |
| Ví dụ | Email, mã đơn hàng, trạng thái | Mô tả sản phẩm, nội dung bài viết |
| Query thường dùng | `term`, `terms`, `range` tùy kiểu field | `match`, `match_phrase` |
| Chuẩn hóa | Có thể dùng normalizer | Dùng analyzer |

Giả sử một document chứa:

```json
{
  "username": "Alice Nguyen",
  "description": "Java Developer"
}
```

Nếu `username` là `keyword`, Elasticsearch xem toàn bộ `Alice Nguyen` là một giá trị. Query `term` tìm giá trị nguyên vẹn, không tách thành `Alice` và `Nguyen`.

Nếu `description` là `text`, analyzer có thể tách nội dung thành token như `java` và `developer`, tùy analyzer được cấu hình.

Normalizer là cơ chế chuẩn hóa dành cho field kiểu `keyword`. Nó không biến keyword thành text và không thực hiện phân tích ngôn ngữ hay tách câu thành từ. Thông thường, một normalizer phải tạo ra đúng một token từ đầu vào.

## 2. Vấn đề phân biệt hoa thường khi tìm kiếm keyword

Giả sử index có các document:

```json
{ "username": "Alice" }
{ "username": "BOB" }
{ "username": "charlie" }
```

Mapping đơn giản:

```json
{
  "properties": {
    "username": {
      "type": "keyword"
    }
  }
}
```

Query:

```http
GET /users/_search
{
  "query": {
    "term": {
      "username": "alice"
    }
  }
}
```

không tìm thấy document có `username = "Alice"`, vì keyword mặc định được so khớp theo giá trị đã lập chỉ mục và có phân biệt chữ hoa/chữ thường.

Một cách xử lý là chuẩn hóa cả giá trị khi lập chỉ mục lẫn giá trị truy vấn về cùng một dạng. Ví dụ, chuyển tất cả chữ cái thành chữ thường:

```text
Alice  -> alice
ALICE  -> alice
alice  -> alice
```

Normalizer đảm nhiệm việc này một cách nhất quán, thay vì yêu cầu mọi nơi trong ứng dụng tự gọi `toLowerCase()`.

## 3. Normalizer hoạt động như thế nào?

Normalizer là một cấu hình analysis dành cho keyword. Một custom normalizer có thể kết hợp:

- Character filter: biến đổi ký tự trước bước token filter.
- Token filter: biến đổi token duy nhất của giá trị keyword.

Normalizer không khai báo tokenizer riêng như analyzer. Nó sử dụng cơ chế keyword tokenization và chỉ cho phép các filter phù hợp với một token. Các filter tạo nhiều token hoặc tách văn bản thành nhiều phần không phù hợp với normalizer.

Hai token filter thường dùng:

- `lowercase`: chuyển chữ cái thành chữ thường.
- `asciifolding`: chuyển nhiều ký tự Unicode có dấu hoặc ký tự ngoài ASCII về dạng ASCII gần tương đương.

Ví dụ custom normalizer:

```json
{
  "analysis": {
    "normalizer": {
      "folding_lowercase": {
        "type": "custom",
        "filter": [
          "lowercase",
          "asciifolding"
        ]
      }
    }
  }
}
```

Kết quả minh họa:

| Giá trị đầu vào | Sau lowercase | Sau asciifolding |
|---|---|---|
| `Alice` | `alice` | `alice` |
| `ALICE` | `alice` | `alice` |
| `Café` | `café` | `cafe` |
| `Đặng` | `đặng` | `dang` |
| `MÜNCHEN` | `münchen` | `munchen` |

Kết quả cụ thể phụ thuộc bảng chuyển đổi của bộ lọc ASCII folding. Nó không phải là quy tắc phiên âm ngôn ngữ hoàn chỉnh. Với dữ liệu tiếng Việt hoặc ngôn ngữ khác, hãy kiểm tra những trường hợp có dấu và ký tự đặc thù mà nghiệp vụ cần hỗ trợ.

### 3.1. Chỉ dùng lowercase hay thêm asciifolding?

Nếu yêu cầu chỉ là bỏ phân biệt hoa thường, normalizer có `lowercase` là đủ:

```json
{
  "analysis": {
    "normalizer": {
      "lowercase_normalizer": {
        "type": "custom",
        "filter": ["lowercase"]
      }
    }
  }
}
```

Khi đó:

- `ALICE` và `Alice` được chuẩn hóa thành `alice`.
- `Café` và `café` được chuẩn hóa thành `café`.
- `cafe` vẫn khác `café`.

Nếu muốn bỏ cả dấu trong các ký tự mà ASCII folding hỗ trợ, thêm `asciifolding`:

```json
{
  "analysis": {
    "normalizer": {
      "folding_lowercase": {
        "type": "custom",
        "filter": ["lowercase", "asciifolding"]
      }
    }
  }
}
```

Khi đó `Café`, `CAFÉ` và `cafe` có thể được chuẩn hóa về cùng giá trị `cafe`.

Chọn cách nào phụ thuộc semantics dữ liệu. Nếu dấu có ý nghĩa phân biệt trong mã định danh, tên tài khoản hoặc dữ liệu pháp lý, không nên tự động loại bỏ dấu chỉ vì muốn tìm kiếm dễ hơn.

## 4. Khai báo normalizer khi tạo index

Normalizer phải được định nghĩa trong index settings và được gắn vào field `keyword` qua mapping.

Ví dụ tạo index:

```http
PUT /users
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folding_lowercase": {
          "type": "custom",
          "filter": [
            "lowercase",
            "asciifolding"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "username": {
        "type": "keyword",
        "normalizer": "folding_lowercase"
      },
      "email": {
        "type": "keyword",
        "normalizer": "lowercase"
      },
      "displayName": {
        "type": "keyword",
        "normalizer": "folding_lowercase"
      }
    }
  }
}
```

Trong ví dụ:

- `folding_lowercase` là custom normalizer do index định nghĩa.
- `username` và `displayName` dùng lowercase kết hợp ASCII folding.
- `email` dùng normalizer built-in `lowercase`.
- Field không khai báo normalizer vẫn giữ hành vi keyword mặc định.

Elasticsearch có sẵn normalizer `lowercase`. Nếu chỉ cần chuyển chữ thường, có thể tham chiếu trực tiếp tên này mà không cần định nghĩa custom normalizer.

Sau khi tạo index, kiểm tra mapping:

```http
GET /users/_mapping?pretty
```

Và kiểm tra settings:

```http
GET /users/_settings?pretty
```

Khi tạo index bằng ứng dụng, hãy đảm bảo settings có normalizer được áp dụng trước khi field mapping tham chiếu tới tên normalizer đó. Nếu index đã tồn tại với mapping cũ, không nên cho rằng việc thay annotation trong Java sẽ tự thay đổi mapping hiện có.

## 5. Truy vấn không phân biệt hoa thường

Sau khi field được gắn normalizer, Elasticsearch chuẩn hóa giá trị keyword khi lập chỉ mục và khi xử lý giá trị tìm kiếm cho field đó.

Ví dụ:

```http
GET /users/_search
{
  "query": {
    "term": {
      "username": "ALICE"
    }
  }
}
```

Nếu document đã lưu `username = "Alice"`, query với `ALICE` vẫn có thể khớp vì cả hai được chuẩn hóa về cùng giá trị.

Tương tự:

```http
GET /users/_search
{
  "query": {
    "term": {
      "displayName": "CAFÉ"
    }
  }
}
```

Với normalizer `folding_lowercase`, giá trị truy vấn được chuẩn hóa thành `cafe`, nên có thể khớp với document chứa `Café`, `CAFÉ` hoặc `cafe`.

### 5.1. Vì sao term query vẫn dùng được?

`term` query dùng để so khớp giá trị chính xác của field. "Chính xác" ở đây là chính xác theo giá trị đã được chuẩn hóa và lập chỉ mục, không nhất thiết là chuỗi ký tự ban đầu.

Điều này khác với việc đổi `term` thành `match`. Normalizer không biến field keyword thành field text. Bạn vẫn đang tìm kiếm một giá trị nguyên vẹn.

Với field keyword không có normalizer, `term` phân biệt hoa thường theo giá trị đã lập chỉ mục. Với field keyword có normalizer, cả giá trị lập chỉ mục và giá trị truy vấn được đưa qua cùng quy tắc chuẩn hóa.

### 5.2. Không thay đổi nội dung _source

Normalizer thay đổi dạng term được Elasticsearch lập chỉ mục và dùng trong tìm kiếm. Nó không ghi đè chuỗi gốc trong `_source`.

Ví dụ document được gửi lên:

```json
{
  "username": "Alice"
}
```

Khi lấy document:

```http
GET /users/_doc/1
```

`_source.username` vẫn có thể là `Alice`. Tuy nhiên, term được dùng để tìm kiếm, sort hoặc aggregation trên field đã chuẩn hóa có thể là `alice`.

Nhờ vậy ứng dụng có thể giữ nguyên cách viết gốc để hiển thị, đồng thời hỗ trợ tìm kiếm không phân biệt hoa thường.

## 6. Kiểm tra normalizer bằng Analyze API

Trước khi đưa mapping vào sử dụng, có thể kiểm tra kết quả chuẩn hóa bằng Analyze API.

Ví dụ kiểm tra normalizer gắn với field `username`:

```http
POST /users/_analyze
{
  "field": "username",
  "text": "ÁLICE"
}
```

Response rút gọn có thể có token:

```json
{
  "tokens": [
    {
      "token": "alice",
      "start_offset": 0,
      "end_offset": 5,
      "type": "word",
      "position": 0
    }
  ]
}
```

Với custom normalizer gồm `lowercase` và `asciifolding`, giá trị `ÁLICE` được chuyển thành `alice`.

Có thể kiểm tra thêm các trường hợp:

```http
POST /users/_analyze
{
  "field": "username",
  "text": [
    "Alice",
    "ALICE",
    "Café",
    "CAFÉ",
    "cafe",
    "Đặng"
  ]
}
```

Analyze API giúp nhìn thấy kết quả chuẩn hóa trước khi kết luận query sai. Nếu field không tồn tại hoặc mapping chưa gắn normalizer, kết quả có thể khác với mong đợi.

Nên kiểm tra cả dữ liệu thực tế của nghiệp vụ: ký tự có dấu, dấu gạch nối, dấu chấm, khoảng trắng, email, chữ số, ký tự Unicode và các trường hợp có quy tắc riêng theo ngôn ngữ.

## 7. Kết hợp normalizer với multi-fields

Một field đôi khi cần hai cách truy vấn:

- Tìm kiếm toàn văn trên nội dung.
- So khớp chính xác nhưng không phân biệt hoa thường.

Multi-fields cho phép một giá trị được lập chỉ mục theo nhiều kiểu field. Ví dụ:

```http
PUT /products
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folding_lowercase": {
          "type": "custom",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "folded": {
            "type": "keyword",
            "normalizer": "folding_lowercase"
          }
        }
      }
    }
  }
}
```

Với mapping này:

- `name` là field text phục vụ full-text search.
- `name.folded` là field keyword đã chuẩn hóa để so khớp nguyên vẹn, sort hoặc aggregation.

Tìm kiếm toàn văn:

```http
GET /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
```

Tìm giá trị nguyên vẹn không phân biệt hoa thường và dấu theo normalizer:

```http
GET /products/_search
{
  "query": {
    "term": {
      "name.folded": "WIRELESS MOUSE"
    }
  }
}
```

Đây là cách hữu ích khi cùng một thuộc tính vừa cần tìm kiếm nội dung vừa cần lọc chính xác. Hãy đặt tên field phụ rõ ràng, chẳng hạn `folded`, `normalized` hoặc `raw_ci`, để người viết query biết semantics của nó.

## 8. Normalizer cho sort và aggregation

Normalizer cũng hữu ích khi cần nhóm các giá trị khác cách viết hoa thường vào cùng một bucket hoặc sắp xếp dựa trên giá trị chuẩn hóa.

Ví dụ aggregation:

```http
GET /users/_search
{
  "size": 0,
  "aggs": {
    "usernames": {
      "terms": {
        "field": "username"
      }
    }
  }
}
```

Nếu field `username` dùng lowercase normalizer, các document có giá trị `Alice`, `ALICE` và `alice` có thể được gom vào cùng bucket theo term đã chuẩn hóa.

Sort cũng dựa trên giá trị keyword được lập chỉ mục:

```http
GET /users/_search
{
  "query": {
    "match_all": {}
  },
  "sort": [
    {
      "username": {
        "order": "asc"
      }
    }
  ]
}
```

Nếu cần giữ cả cách viết gốc và cách sắp xếp chuẩn hóa, có thể dùng multi-fields hoặc một field phụ riêng. Cần nhớ rằng aggregation trên field normalized có thể hiển thị key đã chuẩn hóa, không phải cách viết gốc trong `_source`.

## 9. Tích hợp normalizer trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp annotation để mô tả field mapping. Với các phiên bản hỗ trợ thuộc tính `normalizer` trong `@Field`, entity có thể khai báo:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "users")
@Setting(settingPath = "/elasticsearch/users-settings.json")
public class User {

    @Id
    private String id;

    @Field(type = FieldType.Keyword, normalizer = "folding_lowercase")
    private String username;

    @Field(type = FieldType.Keyword, normalizer = "lowercase")
    private String email;

    // constructors, getters and setters
}
```

File settings đặt trong classpath, ví dụ `src/main/resources/elasticsearch/users-settings.json`:

```json
{
  "analysis": {
    "normalizer": {
      "folding_lowercase": {
        "type": "custom",
        "filter": [
          "lowercase",
          "asciifolding"
        ]
      }
    }
  }
}
```

Ở đây:

- `@Setting` tham chiếu file settings để Spring Data dùng khi tạo index.
- `@Document` khai báo tên index của entity.
- `@Field(type = FieldType.Keyword, normalizer = ...)` gắn normalizer đã định nghĩa trong settings vào field.
- `username` dùng custom normalizer; `email` dùng built-in lowercase normalizer.

Tên package và khả năng của annotation phụ thuộc phiên bản Spring Data Elasticsearch. Nếu dự án đang dùng phiên bản không hỗ trợ thuộc tính `normalizer` hoặc có cách khai báo settings khác, hãy kiểm tra API đúng với dependency hiện tại. Điều quan trọng là settings tạo normalizer và mapping field phải được áp dụng cùng nhau khi index được tạo.

### 9.1. Dùng IndexOperations để kiểm tra index

Có thể kiểm tra index và mapping thông qua `ElasticsearchOperations`:

```java
IndexOperations indexOps = operations.indexOps(User.class);

boolean exists = indexOps.exists();

if (exists) {
    Map<String, Object> mapping = indexOps.getMapping();
    Map<String, Object> settings = indexOps.getSettings();
}
```

Đoạn code minh họa việc đọc metadata hiện tại từ Elasticsearch. Khi debug, hãy xác nhận:

- Index thực tế có tồn tại.
- Settings có normalizer đúng tên.
- Mapping của field có tham chiếu đúng normalizer.
- Ứng dụng đang kết nối đúng cluster và đúng index.
- Repository hoặc `ElasticsearchOperations` sử dụng entity/mapping mong muốn.

Thay đổi annotation trong source code không tự chứng minh index hiện tại đã được cập nhật. Nếu index đã tồn tại từ trước, hãy đọc mapping và settings trực tiếp từ Elasticsearch.

## 10. Thay đổi normalizer khi index đã tồn tại

Normalizer là một phần của cách field được lập chỉ mục. Không thể tùy ý đổi normalizer của một field đã tồn tại như thay đổi một giá trị cấu hình thông thường.

Nếu field `username` đang được tạo mà không có normalizer, rồi sau đó muốn chuyển sang lowercase, cách an toàn thường là:

1. Tạo index mới với settings chứa normalizer.
2. Tạo mapping field tham chiếu normalizer đó.
3. Reindex dữ liệu từ index cũ sang index mới.
4. Kiểm tra số document, mapping và kết quả truy vấn.
5. Chuyển alias hoặc ứng dụng sang index mới sau khi xác nhận dữ liệu đúng.

Ví dụ tạo index mới:

```http
PUT /users-v2
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "username": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
```

Sau đó reindex:

```http
POST /_reindex
{
  "source": {
    "index": "users"
  },
  "dest": {
    "index": "users-v2"
  }
}
```

Reindex là thao tác ghi dữ liệu vào index đích và có thể tốn tài nguyên với tập dữ liệu lớn. Hãy thực hiện theo quy trình migration, kiểm tra mapping và dữ liệu sau khi sao chép. Nếu ứng dụng đang ghi đồng thời vào index cũ, cần có kế hoạch đồng bộ thay đổi phát sinh trong lúc migration trước khi chuyển alias.

Một phương án khác là thêm multi-field vào mapping hiện có trong những trường hợp được Elasticsearch hỗ trợ, rồi cập nhật/reindex các document cũ để field phụ được lập chỉ mục. Chỉ thêm mapping không tự tạo lại dữ liệu đã lập chỉ mục trước đó. Với thay đổi analysis hoặc normalizer, tạo index mới thường giúp quy trình dễ kiểm soát hơn.

## 11. So sánh normalizer với các cách tìm kiếm không phân biệt hoa thường khác

| Cách làm | Phạm vi | Ưu điểm | Hạn chế |
|---|---|---|---|
| Keyword không normalizer | So khớp keyword phân biệt hoa thường | Giữ nguyên semantics gốc | `Alice` khác `alice` |
| Keyword + lowercase normalizer | So khớp nguyên vẹn, không phân biệt hoa thường | Nhất quán ở index và query; hỗ trợ sort/aggregation | Cần cấu hình mapping từ đầu |
| Keyword + lowercase + asciifolding | So khớp nguyên vẹn, bỏ hoa thường và một số dấu | Hữu ích với dữ liệu cần tìm gần đúng về dấu | Có thể gộp các giá trị nghiệp vụ vốn khác nhau |
| Text + analyzer | Tìm kiếm toàn văn | Hỗ trợ tokenization, stemming và các bước phân tích | Không phải so khớp nguyên vẹn như keyword |
| Term query với `case_insensitive` | So khớp ASCII không phân biệt hoa thường trên phiên bản hỗ trợ | Có thể dùng cho một số truy vấn mà không đổi mapping | Phạm vi hạn chế; không thay thế chuẩn hóa dấu hay semantics của normalizer |

Một số phiên bản Elasticsearch hỗ trợ tùy chọn `case_insensitive` cho `term` query. Khả năng này phụ thuộc phiên bản và tập ký tự được hỗ trợ; tài liệu của API mô tả phạm vi cụ thể. Nếu cần quy tắc chuẩn hóa nhất quán cho cả tìm kiếm, sort và aggregation, normalizer thường là lựa chọn rõ ràng hơn.

## 12. Những trường hợp cần cân nhắc

### 12.1. Không phải mọi field đều nên bỏ phân biệt hoa thường

Các giá trị như username hoặc email thường có yêu cầu so khớp không phân biệt hoa thường ở tầng ứng dụng. Tuy nhiên, mã định danh, token, mật khẩu, mã phân biệt hoa thường hoặc dữ liệu cần giữ nguyên semantics có thể không phù hợp với lowercase normalizer.

Không áp dụng một normalizer chung cho mọi field chỉ để đơn giản hóa query. Quy tắc so khớp phải xuất phát từ ý nghĩa nghiệp vụ của dữ liệu.

### 12.2. ASCII folding có thể làm nhiều giá trị trở thành một

Nếu dùng cả `lowercase` và `asciifolding`, các giá trị như `cafe` và `café` có thể cùng trở thành `cafe`. Điều này hữu ích cho tìm kiếm thân thiện với người dùng, nhưng có thể gây trùng lặp về mặt logic khi hai giá trị cần phân biệt.

Nếu cần giữ cả hai khả năng, lưu giá trị gốc và tạo field phụ normalized để tìm kiếm. Không dùng giá trị normalized làm khóa duy nhất nếu quy tắc nghiệp vụ yêu cầu phân biệt các dạng gốc.

### 12.3. Quy tắc chữ thường theo ngôn ngữ

Chuyển chữ thường không phải lúc nào cũng đơn giản với mọi ngôn ngữ. Một số ngôn ngữ có quy tắc xử lý chữ hoa/chữ thường đặc thù. Nếu dữ liệu đa ngôn ngữ, hãy kiểm tra các trường hợp Unicode và quy tắc locale cần thiết; đừng giả định một phép chuyển chữ thường mặc định giải quyết mọi quy tắc ngôn ngữ.

### 12.4. Không nhầm normalizer với analyzer

Normalizer không tách nội dung thành nhiều từ. Nếu cần tìm một phần của tên, tìm cụm từ hoặc tìm kiếm toàn văn, hãy dùng field `text` với analyzer phù hợp. Nếu cần so khớp nguyên vẹn không phân biệt hoa thường, dùng field `keyword` với normalizer.

Có thể kết hợp cả hai bằng multi-fields để phục vụ hai nhu cầu trên cùng một giá trị nguồn.

## 13. Quy trình kiểm tra khi query không phân biệt hoa thường không hoạt động

Khi query vẫn không tìm thấy kết quả, hãy kiểm tra theo thứ tự:

**Bước 1 — Xác nhận field mapping**

```http
GET /users/_mapping?pretty
```

Kiểm tra field có kiểu `keyword` và có thuộc tính `normalizer` đúng tên hay không.

**Bước 2 — Xác nhận settings**

```http
GET /users/_settings?pretty
```

Kiểm tra normalizer được khai báo trong analysis settings và tên tham chiếu có khớp mapping không.

**Bước 3 — Kiểm tra kết quả chuẩn hóa**

```http
POST /users/_analyze
{
  "field": "username",
  "text": "ÁLICE"
}
```

Xem token được tạo ra có đúng với kỳ vọng nghiệp vụ không.

**Bước 4 — Kiểm tra document gốc**

```http
GET /users/_search
{
  "query": {
    "match_all": {}
  },
  "size": 5
}
```

Xác nhận document đã được ghi vào đúng index và `_source` có giá trị cần tìm.

**Bước 5 — Chạy term query trực tiếp**

```http
GET /users/_search
{
  "query": {
    "term": {
      "username": "ALICE"
    }
  }
}
```

Nếu query trên field keyword đã gắn normalizer vẫn không khớp, hãy xác nhận document được lập chỉ mục sau khi mapping có normalizer, query đang dùng đúng index/alias và field name chính xác.

**Bước 6 — Kiểm tra dữ liệu cũ**

Nếu normalizer mới chỉ được thêm vào mapping hoặc index mới nhưng document cũ chưa được reindex/cập nhật, dữ liệu hiện có có thể chưa có term theo quy tắc mới. Kiểm tra lịch sử tạo index và quá trình migration.

## 14. Bảng tra cứu nhanh

| Nhu cầu | Cấu hình hoặc query |
|---|---|
| Chỉ bỏ phân biệt hoa thường | Keyword với normalizer `lowercase` |
| Bỏ hoa thường và một số dấu | Custom normalizer với `lowercase` và `asciifolding` |
| So khớp nguyên vẹn | `term` query trên field keyword |
| Tìm kiếm toàn văn | `match` query trên field text |
| Kiểm tra kết quả chuẩn hóa | Analyze API với tham số `field` |
| Sort/aggregation theo giá trị normalized | Dùng keyword field có normalizer |
| Vừa full-text vừa exact normalized | Multi-fields: text và keyword |
| Thay đổi normalizer cho dữ liệu hiện có | Tạo index mới và reindex theo kế hoạch |

Normalizer giúp chuẩn hóa keyword theo cùng một quy tắc ở lúc lập chỉ mục và lúc tìm kiếm. Với nhu cầu không phân biệt hoa thường, `lowercase` thường là đủ; nếu cần bỏ dấu, có thể bổ sung `asciifolding` sau khi đánh giá nguy cơ gộp các giá trị khác nhau. Trong Spring Data Elasticsearch, settings định nghĩa normalizer và mapping của entity tham chiếu tên đó. Hãy kiểm tra mapping thực tế, thử Analyze API và quản lý migration khi thay đổi index đã tồn tại.

