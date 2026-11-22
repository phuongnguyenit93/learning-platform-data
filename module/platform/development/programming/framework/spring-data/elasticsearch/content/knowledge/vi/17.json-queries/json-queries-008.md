# Search template, tham số mẫu và API triển khai phù hợp

Elasticsearch Search Template cho phép định nghĩa trước cấu trúc một truy vấn, sau đó truyền các giá trị khác nhau mỗi lần tìm kiếm. Template thường dùng Mustache để chèn tham số, bật/tắt một phần điều kiện hoặc lặp qua danh sách giá trị.

Cách này hữu ích khi nhiều màn hình hoặc service cần dùng chung một query có cấu trúc ổn định. Thay vì ghép chuỗi JSON trong code, ứng dụng gửi template ID cùng các tham số. Elasticsearch render template thành query DSL rồi thực thi trên index được chỉ định.

Trong Spring Data Elasticsearch, cần phân biệt Search Template với `CriteriaQuery` và `NativeQuery`. Search Template là tính năng của Elasticsearch Search API, được quản lý bằng Stored Script API và thực thi bằng Search Template API. Khi cần gọi trực tiếp tính năng này từ Java, có thể sử dụng Elasticsearch Java API Client được cấu hình trong ứng dụng.

## 1. Search Template giải quyết vấn đề gì?

Giả sử ứng dụng có nhiều màn hình tìm kiếm sản phẩm. Mỗi màn hình cần:

- Tìm toàn văn theo tên.
- Luôn giới hạn theo tenant.
- Có thể lọc theo trạng thái.
- Có thể lọc theo một hoặc nhiều danh mục.
- Có thể đặt giá tối thiểu hoặc tối đa.
- Có thể thay đổi page size.

Phần cấu trúc query gần như giống nhau, chỉ các giá trị thay đổi. Nếu mỗi service tự ghép JSON, code có thể lặp lại và khó kiểm soát dấu ngoặc, dấu phẩy hoặc quy tắc filter.

Search Template tách hai phần:

- **Template**: cấu trúc query DSL và quy tắc dùng tham số.
- **Params**: các giá trị cụ thể cho một lần tìm kiếm.

~~~mermaid
flowchart TD
    A["Ứng dụng gửi template ID + params"] --> B["Elasticsearch Search Template API"]
    B --> C["Lấy stored Mustache template"]
    C --> D["Render params thành JSON query"]
    D --> E["Thực thi Search API trên index"]
    E --> F["Search response"]
~~~

Một template có thể được tái sử dụng với nhiều bộ tham số. Việc thay đổi keyword hoặc status không cần tạo một query JSON hoàn toàn mới trong code ứng dụng.

## 2. Search Template và Mustache

Elasticsearch sử dụng Mustache làm ngôn ngữ template cho stored search templates.

Ví dụ template đơn giản:

~~~json
{
  "query": {
    "match": {
      "name": "{{query_string}}"
    }
  }
}
~~~

Khi render với tham số:

~~~json
{
  "query_string": "wireless keyboard"
}
~~~

Elasticsearch tạo query tương đương:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Cú pháp Mustache cơ bản:

| Cú pháp | Ý nghĩa |
|---|---|
| `{{name}}` | Thay bằng giá trị tham số `name` |
| `{{#name}}...{{/name}}` | Chỉ render phần nội dung khi tham số có giá trị truthy |
| `{{^name}}...{{/name}}` | Render phần nội dung khi tham số thiếu hoặc falsy |
| `{{#items}}...{{/items}}` | Lặp qua danh sách hoặc kiểm tra section |
| `{{.}}` | Giá trị phần tử hiện tại khi lặp |
| `{{#toJson}}value{{/toJson}}` | Serialize tham số thành JSON |

Với các tham số phức tạp như mảng hoặc object, helper `toJson` giúp tạo JSON đúng cấu trúc. Tránh tự nối chuỗi JSON hoặc chèn một đoạn JSON tùy ý từ input người dùng.

## 3. Tạo stored search template bằng Stored Script API

Search template được lưu dưới dạng stored script với language `mustache`. API triển khai là Stored Script API:

~~~http
PUT /_scripts/product-search
Content-Type: application/json

{
  "script": {
    "lang": "mustache",
    "source": {
      "query": {
        "match": {
          "name": "{{query_string}}"
        }
      }
    }
  }
}
~~~

Trong ví dụ:

- `_scripts/product-search` là endpoint lưu template với ID `product-search`.
- `lang: mustache` chỉ định engine render.
- `source` chứa query DSL có placeholder.
- `{{query_string}}` là tham số sẽ được truyền lúc chạy.

Template có thể dùng source dạng object JSON như trên hoặc dạng chuỗi JSON tùy API/phiên bản. Dạng object giúp cấu trúc dễ đọc và tránh lỗi escape dấu nháy.

Khi API trả về thành công, template được lưu trong cluster và có thể được gọi bằng ID từ các ứng dụng có quyền thực thi search template.

### Xem stored template

Có thể lấy lại template đã lưu:

~~~http
GET /_scripts/product-search
~~~

Việc đọc lại giúp kiểm tra template ID và nội dung đang được triển khai trên cluster.

### Xóa stored template

Khi template không còn được sử dụng:

~~~http
DELETE /_scripts/product-search
~~~

Xóa template cần được thực hiện theo quy trình triển khai có kiểm soát, vì các ứng dụng đang gọi ID đó có thể lập tức gặp lỗi nếu template không còn tồn tại.

## 4. Render template trước khi thực thi

Trước khi dùng template trong Search API, nên render thử để xem JSON query cuối cùng. Elasticsearch cung cấp Render Search Template API:

~~~http
POST /_render/template
Content-Type: application/json

{
  "id": "product-search",
  "params": {
    "query_string": "wireless keyboard"
  }
}
~~~

API trả về nội dung template sau khi Mustache thay thế tham số. Đây là cách kiểm tra:

- Placeholder có đúng tên không.
- Các section tùy chọn có render như mong muốn không.
- JSON sau khi render có cấu trúc hợp lệ không.
- Mảng và object được serialize đúng không.

Render API không thực hiện tìm kiếm trên index. Nó chỉ trả về nội dung đã render. Sau khi kiểm tra, có thể gửi cùng template ID và params đến Search Template API.

## 5. Thực thi Search Template trên index

Dùng Search Template API để render và thực thi template:

~~~http
POST /products/_search/template
Content-Type: application/json

{
  "id": "product-search",
  "params": {
    "query_string": "wireless keyboard"
  }
}
~~~

Trong request:

- `products` là index hoặc alias được tìm kiếm.
- `_search/template` là Search Template API.
- `id` xác định stored template.
- `params` chứa các giá trị đầu vào.

Kết quả là Search response tương tự Search API thông thường: có total hits, hits, score, source và các metadata tùy query.

Có thể dùng HTTP GET hoặc POST theo endpoint và nội dung request được Elasticsearch hỗ trợ; với request có body, POST thường dễ sử dụng nhất qua proxy, gateway và thư viện HTTP.

## 6. Dùng inline template khi chưa cần lưu trên cluster

Không nhất thiết phải lưu template trước. Search Template API cũng hỗ trợ truyền source trực tiếp trong request:

~~~http
POST /products/_search/template
Content-Type: application/json

{
  "source": {
    "query": {
      "match": {
        "name": "{{query_string}}"
      }
    }
  },
  "params": {
    "query_string": "wireless keyboard"
  }
}
~~~

Inline template hữu ích khi:

- Thử nghiệm query.
- Template chỉ dùng ở một luồng nhỏ.
- Muốn kiểm tra cách Mustache hoạt động trước khi triển khai stored template.

Khi cùng một cấu trúc được dùng ở nhiều service hoặc cần quản lý version, stored template thường thuận tiện hơn. Template ID giúp tách nội dung query khỏi code và cho phép triển khai thay đổi query độc lập theo quy trình quản trị.

## 7. Tham số tùy chọn và section trong Mustache

Biểu mẫu tìm kiếm thường có filter không bắt buộc. Mustache section cho phép chỉ render điều kiện khi tham số được cung cấp.

Ví dụ stored template có tenant bắt buộc và status tùy chọn:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "{{tenant_id}}"
          }
        }
        {{#status}},
        {
          "term": {
            "status": "{{status}}"
          }
        }
        {{/status}}
      ]
    }
  }
}
~~~

Khi có `status`, phần term được thêm vào filter. Khi không có status, section không render và query vẫn là JSON hợp lệ.

Ví dụ render với status:

~~~json
{
  "tenant_id": "tenant-42",
  "status": "PUBLISHED"
}
~~~

Query sau render sẽ lọc theo cả tenant và trạng thái.

Nếu chỉ truyền tenant:

~~~json
{
  "tenant_id": "tenant-42"
}
~~~

Điều kiện status bị bỏ qua. Điều kiện tenant vẫn luôn được giữ.

### Dùng section cho khoảng giá

Có thể tách hai cận thành hai range query tùy chọn:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "{{tenant_id}}"
          }
        }
        {{#min_price}},
        {
          "range": {
            "price": {
              "gte": {{min_price}}
            }
          }
        }
        {{/min_price}}
        {{#max_price}},
        {
          "range": {
            "price": {
              "lte": {{max_price}}
            }
          }
        }
        {{/max_price}}
      ]
    }
  }
}
~~~

Nếu chỉ có giá tối thiểu, template chỉ thêm cận dưới. Nếu chỉ có giá tối đa, template chỉ thêm cận trên. Nếu có cả hai, cả hai range query được kết hợp trong filter, tương đương điều kiện AND.

Giá trị số cần được truyền dưới dạng number trong params, không phải chuỗi có ký tự tiền tệ. Cần validate `min_price <= max_price` trước khi gửi request.

## 8. Truyền danh sách bằng toJson

Nếu người dùng chọn nhiều trạng thái hoặc danh mục, có thể dùng `terms` query và helper `toJson`:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "{{tenant_id}}"
          }
        }
        {{#statuses}},
        {
          "terms": {
            "status": {{#toJson}}statuses{{/toJson}}
          }
        }
        {{/statuses}}
      ]
    }
  }
}
~~~

Params:

~~~json
{
  "tenant_id": "tenant-42",
  "statuses": ["PUBLISHED", "APPROVED"]
}
~~~

Helper `toJson` serialize mảng thành JSON array. Sau khi render, điều kiện tương đương:

~~~json
{
  "terms": {
    "status": ["PUBLISHED", "APPROVED"]
  }
}
~~~

Section `statuses` giúp bỏ qua terms filter khi danh sách rỗng hoặc không được cung cấp. Ứng dụng vẫn nên chuẩn hóa và validate danh sách trước khi gửi, ví dụ loại giá trị trùng và chỉ chấp nhận trạng thái hợp lệ.

Không nên đặt `{{statuses}}` trực tiếp trong JSON rồi kỳ vọng Mustache tự biến một danh sách thành array đúng định dạng. Với mảng/object, dùng helper `toJson` để serialize dữ liệu.

## 9. Template hoàn chỉnh cho biểu mẫu lọc sản phẩm

Ví dụ template có tenant bắt buộc, keyword, status, danh sách category và khoảng giá tùy chọn:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "{{query_string}}"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "tenantId": "{{tenant_id}}"
          }
        }
        {{#status}},
        {
          "term": {
            "status": "{{status}}"
          }
        }
        {{/status}}
        {{#categories}},
        {
          "terms": {
            "category": {{#toJson}}categories{{/toJson}}
          }
        }
        {{/categories}}
        {{#min_price}},
        {
          "range": {
            "price": {
              "gte": {{min_price}}
            }
          }
        }
        {{/min_price}}
        {{#max_price}},
        {
          "range": {
            "price": {
              "lte": {{max_price}}
            }
          }
        }
        {{/max_price}}
      ]
    }
  },
  "from": {{from}},
  "size": {{size}},
  "sort": [
    {
      "createdAt": {
        "order": "{{sort_order}}"
      }
    }
  ]
}
~~~

Một bộ params:

~~~json
{
  "tenant_id": "tenant-42",
  "query_string": "wireless keyboard",
  "status": "PUBLISHED",
  "categories": ["ACCESSORIES", "KEYBOARD"],
  "min_price": 100000,
  "max_price": 500000,
  "from": 0,
  "size": 20,
  "sort_order": "desc"
}
~~~

Nếu keyword cũng là tùy chọn, cần dùng section cho toàn bộ phần `must`, đồng thời đảm bảo query sau render vẫn có một query hợp lệ. Có thể thay bằng `match_all` khi không có từ khóa, nếu nghiệp vụ cho phép.

Trong production, các tham số `from`, `size` và `sort_order` phải được validate và giới hạn ở ứng dụng. Không nên để client gửi một page size rất lớn hoặc một giá trị sort không được phép.

## 10. Gọi Search Template bằng Elasticsearch Java API Client

Trong Spring Data Elasticsearch 5.x, ứng dụng thường có thể sử dụng Elasticsearch Java API Client thông qua bean `ElasticsearchClient` được cấu hình trong application context.

Import cần thiết:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.json.JsonData;
import co.elastic.clients.elasticsearch.core.SearchTemplateResponse;
import java.io.IOException;
import java.util.Map;
~~~

Ví dụ service gọi stored template:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.SearchTemplateResponse;
import co.elastic.clients.json.JsonData;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.Map;

@Service
public class ProductTemplateSearchService {

    private final ElasticsearchClient client;

    public ProductTemplateSearchService(ElasticsearchClient client) {
        this.client = client;
    }

    public SearchTemplateResponse<ProductDocument> search(
            String keyword,
            String tenantId
    ) throws IOException {

        Map<String, JsonData> params = Map.of(
                "query_string", JsonData.of(keyword),
                "tenant_id", JsonData.of(tenantId)
        );

        return client.searchTemplate(request -> request
                        .index("products")
                        .id("product-search")
                        .params(params),
                ProductDocument.class
        );
    }
}
~~~

Các thành phần:

- `ElasticsearchClient` gọi trực tiếp Search Template API.
- `index("products")` xác định index hoặc alias cần tìm.
- `id("product-search")` chọn stored template.
- `params(params)` truyền tham số dưới dạng `JsonData`.
- `SearchTemplateResponse<T>` chứa phản hồi của Search Template API.

Đoạn code minh họa cách gọi API của Java Client; tên overload và kiểu response cần tương thích với phiên bản Elasticsearch Java API Client mà dự án đang sử dụng.

### Lưu ý về chuyển đổi kết quả

Khi gọi trực tiếp `ElasticsearchClient.searchTemplate(...)`, việc deserialize `_source` do JSON mapper của Java Client đảm nhiệm. Đây là đường gọi trực tiếp client, không phải `ElasticsearchOperations.search(...)` của Spring Data.

Nếu entity sử dụng custom converter hoặc mapping metadata đặc thù của Spring Data, hãy kiểm tra cách client JSON mapper chuyển đổi document. Có thể dùng một DTO phù hợp với JSON mapper, nhận source dưới dạng JSON data/map rồi chuyển đổi qua mapper của ứng dụng, hoặc dùng `ElasticsearchOperations` với `NativeQuery` khi không cần Search Template API.

Không nên giả định `@Field`, `@WritingConverter` hoặc `@ReadingConverter` luôn được áp dụng giống hệt khi deserialize qua client trực tiếp. Hai con đường có thể dùng chung client connection nhưng có trách nhiệm mapping khác nhau.

## 11. Khi nào dùng Search Template, NativeQuery hoặc CriteriaQuery?

Ba lựa chọn này phục vụ các nhu cầu khác nhau:

| Tiêu chí | Search Template | NativeQuery | CriteriaQuery |
|---|---|---|---|
| Định nghĩa query | Stored hoặc inline Mustache template | Java Client Query DSL | Criteria API của Spring Data |
| Tham số | Truyền riêng qua params | Code Java xây dựng query object | Code Java thêm Criteria |
| Quản lý query | Có thể version và triển khai trên cluster | Nằm trong code ứng dụng | Nằm trong code ứng dụng |
| Tái sử dụng giữa nhiều client | Thuận tiện qua template ID | Cần chia sẻ code/thư viện | Cần chia sẻ code/thư viện |
| Query động | Mustache sections và params | Java logic và typed DSL | Điều kiện Criteria |
| Thực thi | Search Template API | ElasticsearchOperations | ElasticsearchOperations |
| Phù hợp | Query ổn định dùng lại ở nhiều nơi, cần thay đổi độc lập | DSL phức tạp được xây dựng trong Java | Filter phổ biến, cấu trúc đơn giản |

Chọn Search Template khi cấu trúc query cần được quản lý tập trung, được gọi từ nhiều ứng dụng hoặc cần triển khai thay đổi query độc lập với binary ứng dụng.

Chọn NativeQuery khi query được tạo động trong Java và cần type-safe DSL hoặc các tính năng Elasticsearch nâng cao.

Chọn CriteriaQuery khi form lọc có các điều kiện thông thường và muốn sử dụng abstraction của Spring Data.

## 12. Phân biệt Search Template với Index Template

Tên gọi gần giống nhau nhưng hai tính năng có mục đích hoàn toàn khác:

| Thành phần | Search Template | Index Template |
|---|---|---|
| Mục đích | Tái sử dụng cấu trúc truy vấn tìm kiếm | Áp dụng settings, mappings và aliases cho index mới |
| API quản lý | Stored Script API, `_scripts` | Index Template API, `_index_template` |
| Nội dung | Mustache query DSL | Index settings, mappings, aliases |
| Thời điểm áp dụng | Khi render/thực thi search request | Khi tạo index phù hợp với pattern |
| Ví dụ | `product-search` | `products-template` |

Search Template không tạo mapping và không tạo index. Index Template không phải query template và không nhận params cho từng lần search.

## 13. Quản lý phiên bản và triển khai template

Stored template nằm trong cluster. Vì vậy, nên quản lý nội dung template trong source control và triển khai qua pipeline hoặc migration có phiên bản.

Một quy trình thường dùng:

~~~mermaid
flowchart TD
    A["Lưu template JSON trong source control"] --> B["Review thay đổi"]
    B --> C["Pipeline gọi PUT /_scripts/template-id"]
    C --> D["Gọi POST /_render/template để kiểm tra"]
    D --> E["Chạy truy vấn thử trên index test"]
    E --> F["Cho ứng dụng gọi template ID"]
~~~

Có thể đặt tên template có version, ví dụ:

- `product-search-v1`
- `product-search-v2`

Khi cần thay đổi query có ảnh hưởng kết quả, triển khai ID mới, kiểm tra bằng Render API và test trên dữ liệu staging, sau đó cập nhật ứng dụng hoặc cấu hình để gọi ID mới.

Nếu thay thế nội dung của cùng một ID, các ứng dụng đang sử dụng ID đó có thể nhận hành vi mới ngay sau khi cập nhật. Cần phối hợp rollout và rollback phù hợp.

### Không nên triển khai stored template mỗi lần ứng dụng khởi động

Việc `PUT /_scripts/...` thường cần quyền quản trị cluster rộng hơn quyền tìm kiếm thông thường. Nếu mọi instance runtime đều cập nhật template khi khởi động:

- Nhiều instance có thể ghi đè cùng một template.
- Phiên bản template phụ thuộc thứ tự khởi động.
- Tài khoản runtime phải có quyền quản trị không cần thiết.
- Việc rollback và truy vết thay đổi khó kiểm soát.

Nên tách tài khoản hoặc job triển khai template khỏi tài khoản runtime chỉ thực hiện search.

## 14. Bảo mật và giới hạn tham số

Search Template giúp tách cấu trúc query khỏi dữ liệu đầu vào, nhưng không thay thế việc kiểm tra input.

Một số nguyên tắc:

1. Truyền tham số qua trường `params`, không nối chuỗi JSON từ dữ liệu người dùng.
2. Dùng `toJson` cho mảng và object.
3. Tránh dùng Mustache triple braces để chèn raw JSON từ input không đáng tin cậy.
4. Không cho client tự chọn tên field tùy ý bằng cách truyền vào placeholder.
5. Dùng allowlist cho sort field và sort order.
6. Validate page size, from/offset, khoảng giá và danh sách giá trị.
7. Luôn giữ tenant/permission filter bắt buộc trong template hoặc bổ sung từ context đã xác thực.
8. Chỉ cấp quyền quản lý stored scripts cho pipeline cần triển khai template.
9. Tài khoản runtime chỉ cần quyền search/read phù hợp với index hoặc alias.
10. Không đưa bí mật như API key, password hoặc token vào template params.

Nếu template cho phép thay cả tên field, loại query hoặc một đoạn cấu trúc JSON, người gọi có thể làm thay đổi phạm vi truy vấn ngoài dự kiến. Hãy giữ cấu trúc query do ứng dụng quản lý và chỉ cho tham số dữ liệu hợp lệ đi vào.

## 15. Lỗi thường gặp

### Template ID không tồn tại

Search Template API trả lỗi khi gọi stored template chưa được triển khai hoặc đã bị xóa. Kiểm tra bằng:

~~~http
GET /_scripts/product-search
~~~

### Render ra JSON không hợp lệ

Một section có thể tạo dấu phẩy thừa hoặc thiếu khi tham số rỗng. Gọi Render API với cả bộ params đầy đủ và bộ params tối thiểu để kiểm tra các nhánh.

### Quên truyền tham số bắt buộc

Nếu template có `{{tenant_id}}` nhưng request không truyền `tenant_id`, query có thể render thành giá trị không mong muốn hoặc lỗi. Validate tham số bắt buộc ở ứng dụng trước khi gọi.

### Dùng toJson sai vị trí

`toJson` tạo JSON representation. Không bọc kết quả của helper trong dấu nháy nếu vị trí đó cần một array/object JSON thực sự.

### Coi Search Template là Index Template

`_scripts` lưu query template. `_index_template` lưu settings/mapping áp dụng khi tạo index. Chọn sai API sẽ không tạo ra hành vi mong muốn.

### Kỳ vọng Search Template tự tạo mapping

Template chỉ tạo query. Index và mapping phải tồn tại trước, hoặc được tạo bởi quy trình provisioning riêng.

### Gọi Search Template qua ElasticsearchOperations

`ElasticsearchOperations.search(...)` nhận Spring Data Query như `NativeQuery` hoặc `CriteriaQuery`. Search Template API là endpoint riêng của Elasticsearch Java API Client; khi cần chức năng đó, gọi `ElasticsearchClient.searchTemplate(...)` hoặc HTTP API tương ứng.

### Dùng entity converter không đúng đường

Kết quả khi gọi trực tiếp Java Client được deserialize qua JSON mapper của client. Nếu cần custom conversion của Spring Data, hãy thiết kế bước chuyển đổi phù hợp thay vì mặc định cho rằng Search Template response đi qua `MappingElasticsearchConverter`.

## 16. Quy trình triển khai Search Template

Khi đưa một template vào ứng dụng:

1. Xác định query DSL và các field mapping mà template sẽ sử dụng.
2. Chọn tham số bắt buộc và tùy chọn; quy định kiểu dữ liệu cho từng tham số.
3. Viết Mustache source, dùng section cho điều kiện tùy chọn và `toJson` cho mảng/object.
4. Lưu template trong source control cùng version và mô tả tham số.
5. Triển khai bằng `PUT /_scripts/{id}` qua pipeline có quyền phù hợp.
6. Gọi `POST /_render/template` để kiểm tra các bộ params đại diện.
7. Thử thực thi bằng `POST /{index}/_search/template` trên index test/staging.
8. Cập nhật ứng dụng để gọi template ID và truyền params.
9. Theo dõi lỗi render, lỗi query và thời gian thực thi.
10. Khi thay đổi query lớn, triển khai ID version mới và chuyển ứng dụng theo kế hoạch.
11. Giữ template cũ trong thời gian rollback cần thiết.
12. Xóa template cũ khi không còn client nào sử dụng.

## Kết luận

Search Template là cách tái sử dụng query DSL bằng Mustache template và params. Stored template được quản lý bằng Stored Script API tại `_scripts/{id}`; Render API giúp xem query sau khi thay tham số; Search Template API thực thi template trên index. Trong Spring Data Elasticsearch, có thể gọi trực tiếp `ElasticsearchClient.searchTemplate(...)` khi cần tính năng này, trong khi `NativeQuery` và `CriteriaQuery` phù hợp cho truy vấn được xây dựng trong code qua `ElasticsearchOperations`. Hãy version template, validate params, giữ filter quyền truy cập bắt buộc và tách quyền triển khai stored script khỏi quyền search runtime.
