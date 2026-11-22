# Giới hạn query string, wildcard, script và kích thước truy vấn

Elasticsearch cho phép xây dựng truy vấn rất linh hoạt: người dùng có thể nhập cú pháp `query_string`, dùng wildcard để tìm chuỗi con, gọi script Painless để tính toán hoặc gửi các truy vấn có nhiều điều kiện và aggregation. Những khả năng này hữu ích cho công cụ tìm kiếm nội bộ và use case phân tích, nhưng nếu mở trực tiếp cho đầu vào không tin cậy, chúng có thể tạo ra lỗ hổng truy vấn, truy cập dữ liệu ngoài phạm vi và tiêu thụ quá nhiều CPU, heap hoặc I/O.

Trong chương bảo mật, mục tiêu không chỉ là kiểm tra query có hợp lệ hay không. Ứng dụng cần kiểm soát **ai được truy vấn index nào, field nào được phép tìm, loại cú pháp nào được dùng, độ phức tạp tối đa và lượng dữ liệu được trả về**. Query do người dùng nhập nên được chuyển thành cấu trúc Query DSL có giới hạn. Chỉ những use case quản trị đáng tin cậy mới nên được cấp quyền dùng cú pháp nâng cao hoặc script đã được duyệt.

Với Spring Data Elasticsearch, nên xây dựng query từ request DTO đã validate bằng `NativeQuery`/Query API thay vì ghép chuỗi JSON hoặc nhận nguyên Query DSL từ client rồi chuyển tiếp tới Elasticsearch. Giới hạn ở tầng ứng dụng cần đi cùng giới hạn của Elasticsearch, gateway, authentication và authorization.

## 1. Vì sao phải giới hạn truy vấn?

Một truy vấn tìm kiếm có thể tiêu tốn tài nguyên theo nhiều cách:

- Quét nhiều term hoặc nhiều field khi dùng wildcard/regexp rộng.
- Phân tích cú pháp và mở rộng một `query_string` có quá nhiều toán tử, field hoặc nhánh.
- Chạy script trên rất nhiều document.
- Tính score, sort hoặc aggregation trên tập dữ liệu lớn.
- Trả về page quá lớn hoặc `_source` có payload nặng.
- Mở nhiều request đồng thời từ một người dùng hoặc một tenant.

Các rủi ro chính:

| Rủi ro | Ví dụ | Hậu quả |
|---|---|---|
| Query injection/logic manipulation | Ghép trực tiếp chuỗi người dùng vào `query_string` | Người dùng thay đổi logic tìm kiếm hoặc mở rộng phạm vi query |
| Data exposure | Client tự chọn index, field hoặc bỏ tenant filter | Đọc dữ liệu ngoài quyền được cấp |
| Resource exhaustion | `*term*`, regexp rộng, script trên nhiều document | CPU cao, latency tăng, node quá tải |
| Oversized request | Query body, terms list hoặc aggregation quá lớn | Tốn network, heap, parse time và bộ nhớ query |
| Excessive result collection | `size` lớn, deep `from/size`, nhiều bucket | Tăng heap và response payload |
| Query flooding | Một client gửi nhiều query nặng đồng thời | Search thread pool và connection pool bị bão hòa |

Không nên trông chờ một setting duy nhất giải quyết tất cả. Bảo vệ tốt cần nhiều lớp: validate input, dựng query an toàn, giới hạn độ phức tạp, phân quyền, rate limit và theo dõi tài nguyên.

## 2. Phân biệt URL query string và `query_string` query

Hai khái niệm có tên gần giống nhưng khác nhau:

- **URL query parameters** là phần sau dấu `?` trong HTTP URL, ví dụ `?q=mouse&page=0`.
- **Elasticsearch `query_string` query** là một loại Query DSL có ngôn ngữ cú pháp riêng, ví dụ `name:mouse AND status:ACTIVE`.

Ví dụ request:

```http
GET /products/_search?q=name:mouse
```

Ở đây `q` là URL parameter chứa cú pháp query string. Dạng body tương đương:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "query_string": {
      "query": "name:mouse AND status:ACTIVE"
    }
  }
}
```

Đối với ứng dụng tìm kiếm cho người dùng phổ thông, thường chỉ cần một ô nhập từ khóa. Không nên vô tình biến ô này thành một giao diện cho phép người dùng điều khiển toàn bộ ngôn ngữ query của Elasticsearch.

## 3. `query_string` mạnh nhưng cần được kiểm soát

`query_string` hỗ trợ cú pháp giàu tính năng:

```text
name:mouse AND status:ACTIVE
brand:(Acme OR Contoso)
price:[10 TO 100]
name:wireless~
name:wire*
```

Nó có thể hỗ trợ field selection, boolean operators, grouping, range, phrase, fuzzy, wildcard và các toán tử khác. Đây là tính năng phù hợp cho công cụ tìm kiếm nâng cao có người dùng hiểu cú pháp, nhưng có thể tạo bất ngờ hoặc truy vấn đắt nếu mở cho mọi người.

### Không ghép trực tiếp input vào biểu thức

Ví dụ rủi ro:

```java
String expression = "name:" + userInput + " AND tenantId:" + tenantId;
```

Nếu `userInput` chứa toán tử, dấu ngoặc hoặc cú pháp field, nó có thể làm thay đổi cách parser hiểu query. Dù ứng dụng thêm tenant filter vào chuỗi, việc ghép chuỗi không phải cách tốt để bảo đảm điều kiện phân quyền luôn được giữ đúng.

### Ưu tiên Query DSL có cấu trúc

Với ô tìm kiếm đơn giản, dùng `match`/`multi_match` và đặt tenant/status trong `bool.filter`:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless mouse",
            "fields": ["name^3", "description"]
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "ACTIVE" } }
      ]
    }
  }
}
```

Người dùng chỉ kiểm soát giá trị tìm kiếm. Ứng dụng kiểm soát field, index, tenant và các filter bắt buộc.

## 4. `simple_query_string` khi cần cú pháp nhẹ hơn

`simple_query_string` cung cấp một cú pháp tìm kiếm đơn giản hơn và có tính chịu lỗi cao hơn. Khi gặp một số cú pháp không hợp lệ, nó có thể bỏ qua phần không hợp lệ thay vì trả lỗi parse như `query_string`.

Ví dụ:

```json
{
  "query": {
    "simple_query_string": {
      "query": "wireless mouse",
      "fields": ["name^3", "description"],
      "default_operator": "and"
    }
  }
}
```

`simple_query_string` không tự động trở thành an toàn tuyệt đối. Nó vẫn có các toán tử và cú pháp mà người dùng có thể dùng để mở rộng truy vấn. Hãy chỉ định `fields`, giới hạn flags được hỗ trợ theo use case, đặt độ dài input và kết hợp với filter phân quyền ở cấp ngoài.

### Chọn loại query

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Ô nhập từ khóa thông thường | `match` hoặc `multi_match` |
| Cho phép một tập cú pháp đơn giản | `simple_query_string` với field/flags được giới hạn |
| Công cụ quản trị cần cú pháp nâng cao | `query_string` với quyền riêng, allowlist và giới hạn chặt |
| Tìm đúng mã, trạng thái hoặc ID | `term`/`terms` trên field keyword |
| Lọc khoảng số/ngày | `range` |

Không dùng `query_string` chỉ vì nó cho phép viết query ngắn hơn. Structured DSL thường dễ kiểm tra, phân quyền và đo lường hơn.

## 5. Field allowlist và default field

Không nên để client tự chỉ định bất kỳ field nào trong index. Một index có thể chứa field nội bộ, field phục vụ ranking, field chứa dữ liệu nhạy cảm hoặc field có cardinality lớn.

Hãy định nghĩa allowlist field theo use case:

```java
private static final List<String> SEARCH_FIELDS = List.of(
    "name^3",
    "sku^5",
    "description"
);
```

Nếu dùng `query_string`/`simple_query_string`, truyền rõ danh sách `fields`. Không phụ thuộc vào default field dạng wildcard `*` hoặc cấu hình mặc định của index vì nó có thể thay đổi phạm vi tìm kiếm khi mapping được mở rộng.

Các nguyên tắc:

- Chỉ cho tìm trên field đã được duyệt.
- Không cho client truyền tên index hoặc alias tùy ý.
- Không cho client chọn field nội bộ như `tenantId`, `isDeleted` hay trường quyền truy cập để thay thế filter server.
- Phân biệt field text và keyword; dùng field đúng cho full-text, exact match, sort và aggregation.
- Nếu có nhiều vai trò người dùng, có thể có allowlist field khác nhau.

Field allowlist là kiểm soát chức năng và tài nguyên; nó không thay thế field-level security khi dữ liệu nhạy cảm cần được bảo vệ ở tầng Elasticsearch.

## 6. Ký tự đặc biệt và escaping

Ngôn ngữ `query_string` có các ký tự mang ý nghĩa cú pháp như `+`, `-`, `=`, `&&`, `||`, `>`, `<`, `!`, ngoặc, ngoặc vuông, dấu nháy, `~`, `*`, `?`, `:`, `\` và `/`.

Nếu người dùng muốn tìm một chuỗi literal có các ký tự đó, parser có thể diễn giải chúng thành toán tử thay vì văn bản. Có thể escape theo cú pháp query string, nhưng cách an toàn hơn cho ô nhập thông thường là dùng `match`/`multi_match` để analyzer xử lý nội dung như text.

Ví dụ tìm literal `C++`:

```json
{
  "query": {
    "match": {
      "name": "C++"
    }
  }
}
```

Nếu bắt buộc hỗ trợ `query_string`, hãy dùng một hàm escape đã được kiểm thử theo đúng parser/version Elasticsearch và không tự viết một chuỗi replace đơn giản mà bỏ sót ký tự hoặc backslash kép. Một số ký tự cú pháp có quy tắc đặc biệt; escape không phải giải pháp thay thế cho field allowlist và query validation.

### Không nối thêm filter bảo mật vào raw query

Không nên làm:

```java
String query = "(" + userQuery + ") AND tenantId:" + tenantId;
```

Thay vào đó, đặt query người dùng vào một nhánh con và filter tenant ở nhánh `bool.filter` do server xây dựng. Như vậy cú pháp người dùng không thể đóng ngoặc để thoát khỏi filter bắt buộc.

## 7. Giới hạn độ dài và cú pháp `query_string`

Ngay cả khi query string hợp lệ, nó có thể quá dài hoặc chứa quá nhiều toán tử. Hãy đặt giới hạn ứng dụng trước khi gọi Elasticsearch.

Ví dụ quy tắc cho một ô tìm kiếm:

- Tối thiểu 1 ký tự có ý nghĩa sau trim.
- Tối đa một số ký tự phù hợp với UX, ví dụ 200 hoặc 500.
- Giới hạn số token/term.
- Giới hạn số toán tử boolean và số nhóm ngoặc nếu hỗ trợ cú pháp nâng cao.
- Từ chối chuỗi chỉ chứa wildcard hoặc regexp.
- Giới hạn số field được phép chọn.
- Không cho gửi query rỗng có thể match toàn bộ index.

Các con số là chính sách của ứng dụng, cần dựa trên use case và benchmark. Không coi giới hạn HTTP mặc định của Elasticsearch là giới hạn hợp lý cho một ô tìm kiếm.

### Ví dụ validate input

```java
public String validateSearchText(String input) {
    if (input == null) {
        throw new IllegalArgumentException("Search text is required");
    }

    String value = input.strip();
    if (value.isEmpty()) {
        throw new IllegalArgumentException("Search text must not be blank");
    }

    if (value.length() > 200) {
        throw new IllegalArgumentException("Search text is too long");
    }

    return value;
}
```

Độ dài ký tự chỉ là một guardrail cơ bản. Nếu hỗ trợ cú pháp nâng cao, cần giới hạn thêm cấu trúc query và các toán tử đắt.

## 8. Wildcard query và chi phí tìm kiếm

Wildcard query hỗ trợ hai ký tự đại diện chính:

- `*`: khớp với không hoặc nhiều ký tự.
- `?`: khớp với đúng một ký tự.

Ví dụ:

```json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "WM-10*"
      }
    }
  }
}
```

Query trên tìm các SKU bắt đầu bằng `WM-10`. Pattern `*mouse*` tìm chuỗi con ở bất kỳ vị trí nào và thường đắt hơn vì không có tiền tố cố định để giới hạn term expansion.

### Leading wildcard

Các pattern như:

```text
*mouse
*mouse*
?ireless*
```

có thể buộc Elasticsearch xem xét nhiều term hơn. Với field có cardinality cao hoặc index lớn, loại query này có thể tiêu tốn CPU đáng kể.

Đối với ô tìm kiếm người dùng phổ thông:

- Từ chối wildcard ở đầu pattern.
- Chỉ cho phép prefix wildcard ở cuối nếu nghiệp vụ cần.
- Giới hạn số wildcard trong một query.
- Giới hạn độ dài pattern.
- Chỉ chạy trên field keyword được chọn.
- Rate limit các endpoint hỗ trợ wildcard.

### `allow_leading_wildcard` của query_string

`query_string` có tùy chọn `allow_leading_wildcard`. Có thể đặt `false` để từ chối các wildcard ở đầu term trong cú pháp query string. Đây là một guardrail hữu ích, nhưng ứng dụng vẫn nên validate pattern và không để client điều khiển field hoặc các nhánh query tùy ý.

## 9. Chọn giải pháp thay wildcard rộng

Nếu yêu cầu là tìm theo tiền tố hoặc autocomplete, có các lựa chọn thường hiệu quả hơn `*term*`:

| Yêu cầu | Giải pháp có thể phù hợp |
|---|---|
| Tìm chuỗi bắt đầu bằng prefix | `prefix` query trên keyword hoặc field được tối ưu prefix |
| Autocomplete từ đầu từ | `search_as_you_type`, edge n-gram hoặc completion suggester |
| Tìm substring trong mã định danh | Thiết kế `wildcard` field hoặc index n-gram theo workload |
| Tìm full-text theo từ/ngữ nghĩa | `match`/`multi_match` với analyzer phù hợp |
| Tìm đúng mã | `term` trên keyword |

Không thay wildcard bằng n-gram một cách máy móc. N-gram làm tăng số term được index và dung lượng lưu trữ. Cần cân bằng chi phí ghi/index với latency query.

### Wildcard field

Elasticsearch có kiểu field `wildcard` được thiết kế cho các trường hợp tìm pattern trên chuỗi có nhiều giá trị và pattern substring. Nó có thể phù hợp với log message hoặc identifier có dạng chuỗi dài, nhưng không phải lựa chọn mặc định cho mọi text field. Cần benchmark theo độ dài chuỗi, cardinality và phân bố pattern.

## 10. `search.allow_expensive_queries`

Elasticsearch cung cấp setting `search.allow_expensive_queries` để chặn một số loại query được xem là tốn kém khi setting bị tắt. Những loại query bị ảnh hưởng tùy phiên bản và loại field, có thể gồm wildcard, regexp, fuzzy hoặc script query.

Setting này là guardrail ở cấp cluster, không phải bộ phân quyền theo người dùng. Nếu tắt, một số tính năng tìm kiếm có thể không chạy; nếu bật, ứng dụng vẫn phải tự giới hạn query.

Ví dụ cấu hình cluster setting (kiểm tra API/permission theo version đang triển khai):

```http
PUT /_cluster/settings
Content-Type: application/json

{
  "persistent": {
    "search.allow_expensive_queries": false
  }
}
```

Trước khi thay đổi setting này trong môi trường đang chạy, kiểm tra các use case hiện tại và thử trên staging. Không dùng setting cluster để thay thế allowlist field, rate limit hoặc authorization.

## 11. Regexp query cũng cần giới hạn

Regexp query hỗ trợ pattern mạnh hơn wildcard và có thể tạo automaton phức tạp. Ví dụ:

```json
{
  "query": {
    "regexp": {
      "sku": {
        "value": "WM-[0-9]{2,5}"
      }
    }
  }
}
```

Nếu cho phép người dùng nhập regexp tùy ý, cần kiểm soát độ dài và cấu trúc pattern, đồng thời tránh các pattern có thể mở rộng rất rộng. Elasticsearch có giới hạn liên quan đến determinized states; tăng giới hạn không nên là phản xạ đầu tiên khi query bị từ chối.

Với tìm kiếm thông thường, không cần mở regexp cho người dùng. Nếu có use case quản trị, nên cung cấp tập pattern được duyệt hoặc một DSL nghiệp vụ nhỏ hơn thay vì nhận regex tùy ý.

## 12. Script query và Painless

Script cho phép thực hiện logic tùy biến trong Elasticsearch. Painless là ngôn ngữ scripting được sandbox hóa của Elasticsearch và được dùng cho script query, script score, runtime field, update script và một số context khác.

Ví dụ script query:

```json
{
  "query": {
    "script": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].size() != 0 && doc['price'].value < params.maxPrice",
        "params": {
          "maxPrice": 100
        }
      }
    }
  }
}
```

Script query có thể được đánh giá trên nhiều document ứng viên. Vì vậy, nó có thể tốn kém hơn query native đã được Elasticsearch tối ưu. Nếu logic có thể biểu diễn bằng `term`, `range`, `bool`, `exists` hoặc field dẫn xuất đã index sẵn, hãy ưu tiên query native.

### Không nhận script source từ client

Rủi ro nghiêm trọng là cho client gửi trực tiếp:

```json
{
  "script": {
    "source": "...do người dùng cung cấp..."
  }
}
```

Painless sandbox không có nghĩa ứng dụng nên cho người dùng tùy ý thực thi script. Script tùy ý vẫn có thể tiêu tốn CPU, truy cập dữ liệu trong context được phép và tạo truy vấn khó dự đoán. Không nhận `source`, `lang`, script context hoặc stored script ID tùy ý từ request public.

## 13. Dùng parameters thay vì nối giá trị vào script

Nếu script đã được ứng dụng định nghĩa, truyền dữ liệu động qua `params`:

```json
{
  "script": {
    "lang": "painless",
    "source": "doc['price'].value * params.factor",
    "params": {
      "factor": 1.1
    }
  }
}
```

Không tạo source bằng cách nối giá trị người dùng:

```java
// Không nên: source thay đổi theo input
String source = "doc['price'].value < " + userValue;
```

Thay vào đó, giữ source cố định và truyền `userValue` vào params sau khi validate kiểu và miền giá trị. Điều này giúp giảm nguy cơ script injection, tránh tạo nhiều biến thể source gây compile churn và dễ kiểm soát hơn.

### Parameters không thay thế validation

`params` giúp tách code và dữ liệu, nhưng vẫn cần validate giá trị. Ví dụ `factor` phải nằm trong miền hợp lệ; danh sách ID phải có kích thước tối đa; chuỗi phải có độ dài phù hợp.

## 14. Stored scripts và script allowlist

Với logic cần tái sử dụng, có thể đăng ký stored script do đội phát triển kiểm soát, rồi request chỉ tham chiếu ID đã được allowlist.

Ví dụ lưu script:

```http
PUT /_scripts/price-below-limit
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "doc['price'].size() != 0 && doc['price'].value < params.maxPrice"
  }
}
```

Gọi stored script:

```json
{
  "query": {
    "script": {
      "script": {
        "id": "price-below-limit",
        "params": {
          "maxPrice": 100
        }
      }
    }
  }
}
```

Stored script không tự an toàn nếu client có thể chọn bất kỳ ID nào. Ứng dụng nên map một operation nghiệp vụ sang một script ID được duyệt và chỉ truyền các params đã validate.

### Kiểm soát script settings

Elasticsearch có các setting liên quan tới loại script và context được phép, ví dụ `script.allowed_types` và `script.allowed_contexts` trong những phiên bản hỗ trợ. Có thể dùng chúng để thu hẹp bề mặt scripting theo nhu cầu vận hành.

Không nên thay đổi các setting này khi chưa kiểm tra tính tương thích với plugin, ingest pipeline, update script và các tính năng đang dùng. Cấu hình script là kiểm soát ở cấp cluster; quyền gọi API vẫn phải được phân quyền riêng.

## 15. Script compilation và hiệu năng

Elasticsearch biên dịch script và có cơ chế cache compiled script. Nếu ứng dụng tạo source khác nhau cho mỗi request bằng cách nhúng giá trị động vào chuỗi, cache có thể kém hiệu quả và số lần compile tăng.

Nên:

- Giữ source ổn định.
- Đưa dữ liệu thay đổi vào `params`.
- Tránh compile một script khác nhau cho mỗi giá trị người dùng.
- Theo dõi script compilation và cache eviction metrics.
- Không chạy script query trên tập document lớn nếu có thể chuyển logic sang field đã index.
- Giới hạn concurrency và thời gian truy vấn.

## 16. Giới hạn kích thước request body

Query có thể lớn không chỉ vì chuỗi tìm kiếm mà còn do:

- Một danh sách `terms` có hàng chục nghìn hoặc hàng trăm nghìn phần tử.
- Nhiều nhánh `bool.should`/`must`.
- Nhiều nested query và aggregation lồng nhau.
- Script source hoặc params payload lớn.
- Danh sách field, sort và highlight dài.
- Request multi-search chứa quá nhiều sub-request.

Elasticsearch có giới hạn HTTP request body như `http.max_content_length`; reverse proxy, API gateway và load balancer cũng có thể đặt giới hạn riêng. Không nên dựa vào các giới hạn hạ tầng này như validation nghiệp vụ. Một body nhỏ vẫn có thể mô tả query rất tốn kém.

### Dùng POST cho query phức tạp

Query DSL lớn nên được gửi trong body POST thay vì URL dài. URL có giới hạn ở client, proxy và server; query trong URL cũng dễ xuất hiện trong access log. POST giúp biểu diễn cấu trúc tốt hơn nhưng không tự làm query an toàn hoặc nhẹ hơn.

### Đặt giới hạn ứng dụng

Ví dụ:

- Giới hạn body search API ở mức phù hợp với request nghiệp vụ.
- Giới hạn số phần tử trong `terms` list.
- Giới hạn số sort fields và aggregation levels.
- Giới hạn số query con trong multi-search.
- Giới hạn độ dài script params và chuỗi tìm kiếm.
- Từ chối payload vượt giới hạn trước khi gọi Elasticsearch.

## 17. Giới hạn số lượng clause và nhánh query

Một query có hàng nghìn hoặc hàng chục nghìn nhánh có thể làm parser, rewrite và execution tốn tài nguyên. Ví dụ:

```json
{
  "bool": {
    "should": [
      { "term": { "sku": "A-1" } },
      { "term": { "sku": "A-2" } },
      { "term": { "sku": "A-3" } }
    ],
    "minimum_should_match": 1
  }
}
```

Nếu danh sách giá trị có thể lớn, `terms` query thường phù hợp hơn việc tạo một `should` clause cho từng giá trị:

```json
{
  "terms": {
    "sku": ["A-1", "A-2", "A-3"]
  }
}
```

Tuy nhiên, `terms` list cũng cần giới hạn kích thước. Hãy validate số phần tử ở API layer.

Giới hạn boolean clause nội bộ đã thay đổi qua các phiên bản Elasticsearch. Một số version dùng cơ chế giới hạn động dựa trên tài nguyên thay vì một con số cố định có thể điều chỉnh như trước. Không hard-code một giá trị mặc định cũ; hãy tham khảo version đang chạy và đặt quota nghiệp vụ thấp hơn nhiều.

## 18. Giới hạn aggregation buckets

Aggregation có thể tạo ra rất nhiều bucket, đặc biệt khi lồng nhiều `terms` aggregation hoặc dùng cardinality cao. Elasticsearch có setting `search.max_buckets` để giới hạn số bucket trong một response.

Ví dụ một query có nhiều chiều:

```json
{
  "aggs": {
    "by_brand": {
      "terms": { "field": "brandId", "size": 1000 },
      "aggs": {
        "by_category": {
          "terms": { "field": "categoryId", "size": 1000 }
        }
      }
    }
  }
}
```

Số bucket thực tế có thể tăng theo tích số nhánh. Không tăng `search.max_buckets` chỉ để một dashboard trả về tất cả tổ hợp. Hãy cân nhắc composite aggregation và phân trang bucket nếu cần duyệt toàn bộ key space.

Ứng dụng cũng nên giới hạn số aggregation được phép, kích thước mỗi terms aggregation và độ sâu lồng nhau. Server limit là lớp bảo vệ cuối, không phải thiết kế API.

## 19. Giới hạn kết quả và deep pagination

`from`/`size` có thể tiêu tốn bộ nhớ khi phân trang sâu vì Elasticsearch phải giữ và xử lý các kết quả trước offset. `index.max_result_window` giới hạn result window của nhiều query search thông thường; giá trị mặc định phổ biến là 10.000 nhưng cần kiểm tra version/index thực tế.

Không nên tăng `index.max_result_window` tùy tiện để hỗ trợ page số rất lớn. Với export hoặc scan sâu, cân nhắc:

- `search_after` với sort ổn định.
- Point in Time (PIT) để giữ snapshot khi cần tính nhất quán.
- Scroll cho một số workload batch phù hợp.
- Composite aggregation cho phân trang bucket.

### Giới hạn page size ở API

Ngay cả page đầu, client cũng không nên được tự do yêu cầu hàng chục nghìn hit nếu giao diện chỉ hiển thị 20–100 kết quả. Đặt page size tối đa phía server và bỏ qua hoặc từ chối giá trị vượt giới hạn.

## 20. Giới hạn tổng số hit và payload trả về

Đếm chính xác toàn bộ hit có thể tốn thêm công việc. Nếu giao diện không cần tổng số chính xác, có thể dùng `track_total_hits: false` hoặc đặt ngưỡng phù hợp.

Ví dụ:

```json
{
  "track_total_hits": 10000,
  "size": 50,
  "_source": ["id", "name", "priceAmount"],
  "query": {
    "match": {
      "name": "wireless"
    }
  }
}
```

Source filtering giảm payload và chi phí deserialize. Không trả về toàn bộ document nếu UI chỉ cần một vài field. Nếu có field lớn hoặc nhạy cảm, loại khỏi response ngay từ query layer.

## 21. Timeout, terminate và giới hạn công việc

Search API hỗ trợ timeout để giới hạn thời gian chờ xử lý ở phía Elasticsearch. Có thể dùng `timeout` trong request hoặc API client phù hợp.

```http
POST /products/_search?timeout=2s
Content-Type: application/json

{
  "size": 50,
  "query": {
    "match": {
      "name": "wireless"
    }
  }
}
```

Timeout là guardrail hữu ích nhưng không thay thế việc giới hạn query complexity. Một số thao tác có thể đã tiêu tốn tài nguyên trước khi timeout; timeout cũng không đồng nghĩa với việc mọi công việc phía client hoặc downstream bị dừng ngay lập tức.

`terminate_after` có thể giới hạn số document được thu thập trên mỗi shard cho một số loại search, nhưng nó ảnh hưởng semantics của kết quả và không phải giới hạn tổng thời gian/CPU chính xác. Chỉ dùng khi nghiệp vụ chấp nhận kết quả bị dừng sớm.

### Circuit breaker không phải quota query

Elasticsearch có circuit breaker để ngăn một số hoạt động tiêu thụ quá nhiều memory. Nếu breaker kích hoạt, request có thể thất bại. Đây là cơ chế bảo vệ cluster, không phải lý do để cho phép client gửi query lớn rồi dựa vào breaker.

## 22. Spring Data Elasticsearch: xây query từ DTO đã validate

Một API tìm kiếm nên nhận DTO nghiệp vụ nhỏ, ví dụ:

```java
public record ProductSearchRequest(
    String text,
    String categoryId,
    String status,
    Integer page,
    Integer size) {
}
```

Validate các giá trị:

```java
public ProductSearchRequest validate(ProductSearchRequest request) {
    String text = request.text() == null ? "" : request.text().strip();

    if (text.length() > 200) {
        throw new IllegalArgumentException("Search text is too long");
    }

    int page = request.page() == null ? 0 : request.page();
    int size = request.size() == null ? 20 : request.size();

    if (page < 0) {
        throw new IllegalArgumentException("Page must be non-negative");
    }
    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("Page size must be between 1 and 100");
    }

    return new ProductSearchRequest(
        text,
        request.categoryId(),
        request.status(),
        page,
        size
    );
}
```

Trong ứng dụng thực tế, validate enum status, format ID và category theo domain rule. Tenant ID nên được lấy từ security context phía server thay vì nhận tùy ý từ request body.

## 23. Tạo `NativeQuery` với filter bắt buộc

Ví dụ tạo query theo text và filter tenant:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query buildQuery(ProductSearchRequest request, String authenticatedTenantId) {
    return NativeQuery.builder()
        .withQuery(q -> q.bool(b -> {
            if (!request.text().isBlank()) {
                b.must(m -> m.multiMatch(mm -> mm
                    .query(request.text())
                    .fields("name^3", "sku^5", "description")
                ));
            }

            b.filter(f -> f.term(t -> t
                .field("tenantId")
                .value(authenticatedTenantId)
            ));

            if (request.categoryId() != null) {
                b.filter(f -> f.term(t -> t
                    .field("categoryId")
                    .value(request.categoryId())
                ));
            }

            if (request.status() != null) {
                b.filter(f -> f.term(t -> t
                    .field("status")
                    .value(request.status())
                ));
            }
            return b;
        }))
        .withPageable(PageRequest.of(request.page(), request.size()))
        .build();
}
```

Ví dụ dùng Java API Client builder được Spring Data Elasticsearch tích hợp. Cú pháp lambda và kiểu `NativeQuery` có thể khác nhẹ theo version; điểm cốt lõi là server chọn field tìm kiếm và luôn thêm tenant filter từ danh tính đã xác thực.

Không đưa `tenantId` từ client vào `authenticatedTenantId` mà không xác thực quyền. Không cho client gửi `NativeQuery`, `Query` hoặc raw JSON để bỏ qua các điều kiện này.

## 24. Nếu cần `query_string`, bọc trong filter do server quản lý

Với công cụ tìm kiếm nâng cao, có thể cho phép một tập cú pháp nhỏ và vẫn đặt filter ở cấp ngoài:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "query_string": {
            "query": "name:wireless AND sku:WM-*",
            "fields": ["name", "sku"],
            "allow_leading_wildcard": false,
            "default_operator": "AND"
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "ACTIVE" } }
      ]
    }
  }
}
```

Ở đây filter bảo mật nằm ngoài query string do người dùng cung cấp. Ứng dụng vẫn cần giới hạn field, độ dài, wildcard, số toán tử và quyền sử dụng tính năng nâng cao.

## 25. Phân quyền index, document và field

Query validation không thay thế authorization. Một endpoint tìm kiếm cần xác định:

- Người dùng được phép truy vấn index/alias nào?
- Có được xem dữ liệu của tenant nào?
- Có field nào cần ẩn hoặc không được trả về?
- Có được dùng aggregation trên field nhạy cảm không?
- Có được dùng script, wildcard hoặc regexp không?

Các lớp kiểm soát có thể gồm:

- Application authorization: server kiểm tra quyền trước khi dựng query.
- Tenant filter bắt buộc trong Query DSL.
- Elasticsearch document-level security (DLS) nếu license/deployment hỗ trợ và use case cần enforce tại cluster.
- Field-level security (FLS) để giới hạn field đọc/ghi theo role nếu được hỗ trợ.
- Index privileges để giới hạn index/alias và API mà credential có thể gọi.

Không dựa vào client-side filter hoặc ẩn field trong UI để bảo vệ dữ liệu. Nếu user có thể gọi trực tiếp Elasticsearch bằng credential rộng, application filter có thể bị bỏ qua; cần giới hạn quyền ở cluster/security layer.

## 26. Rate limiting và concurrency limiting

Ngay cả query nhỏ cũng có thể gây quá tải nếu gửi với tốc độ rất cao. Cần giới hạn theo user, tenant, API key hoặc client application.

Ví dụ chính sách:

- Rate limit số search request mỗi giây/phút.
- Giới hạn số request đang chạy đồng thời trên mỗi user/tenant.
- Giới hạn concurrency toàn service tới Elasticsearch.
- Ưu tiên hoặc tách queue cho query tương tác và query báo cáo.
- Áp dụng quota thấp hơn cho wildcard, regexp và script query.
- Dùng circuit breaker/bulkhead để bảo vệ các luồng khác khi search chậm.

Rate limit nên đặt ở API gateway hoặc application service để nhận diện user/tenant. Elasticsearch cluster setting không thay thế quota nghiệp vụ theo từng người dùng.

## 27. Ghi log và quan sát query an toàn

Để điều tra truy vấn tốn kém, cần log metadata có ích:

- Correlation ID/request ID.
- User/tenant ID đã được ẩn danh hoặc chuẩn hóa theo chính sách.
- Index/alias được truy vấn.
- Loại query được dùng (`match`, `wildcard`, `script`, aggregation...).
- Thời gian thực thi và số hit trả về.
- Page size, số clause hoặc số phần tử terms.
- Timeout, rejection, 429 và circuit breaker.
- Query category hoặc hash đã chuẩn hóa.

Không log tùy tiện toàn bộ query text hoặc script params nếu chúng có thể chứa dữ liệu cá nhân, token, thông tin bí mật hoặc nội dung người dùng nhạy cảm. Có thể log hash, độ dài, loại toán tử và các metric tổng hợp.

### Theo dõi slow logs và profile

Slow logs giúp phát hiện query hoặc fetch chậm. Profile API có thể giải thích execution plan nhưng tạo overhead đáng kể và không nên bật đại trà trên mọi request production. Dùng profile có chọn lọc trong môi trường kiểm thử/điều tra.

## 28. Lỗi và phản hồi cho client

Không trả nguyên stack trace Elasticsearch hoặc nội dung nội bộ của script/query ra client. Có thể phân loại lỗi:

| Loại lỗi | Phản hồi API có thể phù hợp |
|---|---|
| Input quá dài/không hợp lệ | HTTP 400 với thông báo validation rõ ràng |
| Field hoặc operator không được phép | HTTP 400 hoặc 403 theo hợp đồng API |
| Không có quyền truy cập index/tenant | HTTP 403 hoặc 404 theo chính sách tránh lộ tài nguyên |
| Query timeout | HTTP 504 hoặc trạng thái lỗi tìm kiếm theo hợp đồng dịch vụ |
| Elasticsearch quá tải/rejected | HTTP 503 với retry guidance phù hợp |
| Lỗi mapping/query nội bộ | HTTP 500, log chi tiết có correlation ID |

Thông báo cho client nên nói cách sửa input hoặc thử lại sau, không để lộ tên index nội bộ, field nhạy cảm, script source hoặc topology cluster.

## 29. Kiểm thử giới hạn và bảo mật query

Nên có kiểm thử ở tầng service/controller và integration test với Elasticsearch:

1. Chuỗi tìm kiếm rỗng hoặc chỉ whitespace bị xử lý theo chính sách.
2. Chuỗi vượt giới hạn bị từ chối trước khi gọi Elasticsearch.
3. Ký tự đặc biệt được coi là literal với query thường.
4. Query string không thể phá tenant filter hoặc chọn field ngoài allowlist.
5. Leading wildcard bị từ chối nếu endpoint không cho phép.
6. Wildcard/regexp có pattern quá dài hoặc quá rộng bị từ chối.
7. Script source do client gửi không được chấp nhận.
8. Script ID ngoài allowlist bị từ chối.
9. Script params được validate kiểu và miền giá trị.
10. Terms list, bool clauses, sort và aggregation đều có giới hạn.
11. Page size vượt giới hạn bị từ chối hoặc clamp theo hợp đồng API.
12. Tenant filter được thêm từ security context và không thể bị client ghi đè.
13. User không thể truy cập index/field ngoài quyền.
14. Rate limit và concurrency limit hoạt động khi gửi nhiều request.
15. Timeout/rejection được chuyển thành lỗi API an toàn.

### Test không chỉ kiểm tra chuỗi query

Hãy kiểm tra query cuối cùng được gửi tới Elasticsearch có tenant filter, field allowlist và page size đúng. Với query builder, có thể kiểm tra cấu trúc Query DSL hoặc chạy integration test trên dữ liệu thuộc nhiều tenant để chứng minh không rò kết quả chéo tenant.

## 30. Checklist thiết kế endpoint tìm kiếm

Trước khi đưa endpoint search vào production, xác định:

- Input là text thuần hay một DSL nâng cao?
- Field allowlist là gì?
- Có cho phép wildcard, regexp hoặc script không?
- Độ dài input và số toán tử tối đa là bao nhiêu?
- Index/alias nào được phép truy vấn?
- Tenant và authorization filter được thêm ở đâu?
- Page size, result window và aggregation buckets bị giới hạn thế nào?
- `track_total_hits`, source filtering và timeout được cấu hình ra sao?
- Rate limit và concurrency limit theo user/tenant thế nào?
- Những metric nào dùng để phát hiện query đắt?
- Log có tránh lưu dữ liệu nhạy cảm không?
- Có test injection, data isolation và resource limit không?

## 31. Quy trình xây dựng query an toàn

Một flow phù hợp cho Spring Data Elasticsearch:

```text
HTTP request
     |
     v
Authenticate user
     |
     v
Authorize index/tenant/use case
     |
     v
Validate DTO: length, page size, fields, operators
     |
     v
Build structured Query DSL on server
     |
     +--> Add mandatory tenant/security filters
     |
     +--> Apply timeout, source filtering and result limits
     |
     v
Apply rate/concurrency limits
     |
     v
Execute through Spring Data Elasticsearch
     |
     v
Map safe response DTO and record metrics
```

Với endpoint nâng cao, bước validate phải kiểm tra cả cú pháp và chi phí. Nếu một query không thể được giới hạn đáng tin cậy, không cung cấp khả năng đó cho caller không tin cậy.

## 32. Kết luận

`query_string`, wildcard và script là các tính năng mạnh nhưng có thể mở rộng phạm vi truy vấn và tiêu thụ nhiều tài nguyên. Với ô tìm kiếm thông thường, ưu tiên `match`/`multi_match` hoặc một DSL nghiệp vụ nhỏ. Nếu dùng `query_string`/`simple_query_string`, hãy chỉ định field allowlist, giới hạn cú pháp và độ dài, đồng thời đặt filter phân quyền bên ngoài nhánh query do người dùng kiểm soát. Wildcard/regexp cần kiểm soát leading pattern, độ dài và tần suất; script cần source được ứng dụng duyệt, parameters đã validate và quyền dùng context phù hợp.

Kích thước truy vấn phải được giới hạn ở nhiều cấp: HTTP body, số terms/clauses, số aggregation buckets, page size, result window, payload trả về và concurrency. Trong Spring Data Elasticsearch, nhận DTO nghiệp vụ đã validate rồi dựng `NativeQuery` có cấu trúc; không nhận raw Query DSL hoặc script source từ client. Kết hợp authorization, tenant filter, rate limit, timeout, source filtering, logging an toàn và integration tests để bảo vệ cả dữ liệu lẫn tài nguyên Elasticsearch.

## Tài liệu tham khảo

- [Elasticsearch – Query string query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-query-string-query)
- [Elasticsearch – Simple query string query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-simple-query-string-query)
- [Elasticsearch – Wildcard query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-wildcard-query)
- [Elasticsearch – Regexp query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-regexp-query)
- [Elasticsearch – Script query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-script-query)
- [Elasticsearch – Painless scripting](https://www.elastic.co/docs/reference/scripting-languages/painless/painless)
- [Elasticsearch – Search settings](https://www.elastic.co/docs/reference/elasticsearch/configuration-reference/search-settings)
- [Elasticsearch – Index settings](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules)
- [Elasticsearch – Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch – Security privileges](https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/authorization)
- [Spring Data Elasticsearch – NativeQuery and operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
