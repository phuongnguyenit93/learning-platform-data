# Script, runtime field và các tùy chọn tùy phiên bản

NativeQuery cho phép Spring Data Elasticsearch sử dụng Elasticsearch Query DSL ở mức chi tiết hơn CriteriaQuery và các derived query. Trong những trường hợp cần tính toán ngay khi tìm kiếm, có thể dùng script, script field hoặc runtime field.

Ba cơ chế này có liên quan nhưng giải quyết những việc khác nhau:

- **Script query** dùng một biểu thức để quyết định document có khớp hay không.
- **Script field** tính thêm một giá trị cho từng hit được trả về, thường để hiển thị hoặc xử lý kết quả.
- **Runtime field** khai báo một field được tính khi truy vấn chạy. Field này có thể tham gia query, sort, aggregation và được trả về như một field tùy theo kiểu và ngữ cảnh hỗ trợ.

Script chạy linh hoạt nhưng có chi phí CPU và có thể làm query khó tối ưu. Runtime field giúp bổ sung logic mà không cần ghi lại document, nhưng giá trị vẫn được tính trong lúc truy vấn. Nếu một phép tính được dùng thường xuyên và có thể xác định ngay khi ghi dữ liệu, lưu sẵn field đã tính thường hiệu quả hơn.

## 1. Script trong Elasticsearch là gì?

Elasticsearch hỗ trợ scripting để thực hiện logic trên dữ liệu trong nhiều ngữ cảnh. Ngôn ngữ script mặc định thường dùng là Painless, được thiết kế để chạy trong môi trường có kiểm soát.

Ví dụ, giả sử document sản phẩm có các field:

~~~json
{
  "sku": "SKU-1001",
  "price": 200000,
  "cost": 150000,
  "active": true
}
~~~

Một script có thể tính lợi nhuận:

~~~text
price - cost
~~~

Hoặc xác định document có lợi nhuận lớn hơn một ngưỡng:

~~~text
doc['price'].value - doc['cost'].value > params.minimum
~~~

Script có thể được dùng trong nhiều ngữ cảnh:

| Ngữ cảnh | Mục đích | Kết quả script |
|---|---|---|
| Script query | Lọc document theo logic | true/false |
| Script field | Thêm giá trị tính toán vào từng hit | Giá trị trả về |
| Runtime field | Tạo field ảo khi truy vấn | Giá trị được emit |
| Script score | Tính điểm liên quan tùy chỉnh | Số điểm |
| Update script | Thay đổi document trong thao tác cập nhật | Cập nhật source |
| Aggregation script | Tính toán trong aggregation khi API hỗ trợ | Giá trị phục vụ aggregation |

Không nên dùng một ví dụ script query để suy ra cách viết script cho update hoặc runtime field. Mỗi ngữ cảnh có biến, hàm và quy tắc trả kết quả riêng.

## 2. Painless và các biến thường dùng

Painless là ngôn ngữ script được Elasticsearch thiết kế để kiểm soát quyền truy cập và giới hạn thao tác. Script được biên dịch và chạy trong một context cụ thể.

Trong nhiều query context, script có thể truy cập:

- doc: truy cập doc values của field đã được lập chỉ mục.
- params: tham số do request truyền vào.
- _source: dữ liệu nguồn trong một số context được hỗ trợ, nhưng thường tốn chi phí hơn doc values.
- Các hàm và kiểu dữ liệu được context cho phép.

Ví dụ đọc giá trị số:

~~~text
doc['price'].value
~~~

Kiểm tra field có giá trị:

~~~text
doc['price'].size() != 0
~~~

Truy cập tham số:

~~~text
doc['price'].value > params.minimum
~~~

Nên kiểm tra field có tồn tại trước khi truy cập value nếu dữ liệu có thể thiếu field. Nếu không, script có thể phát sinh lỗi khi gặp document không có giá trị đó.

### 2.1. doc values và _source

doc values là cấu trúc dữ liệu được Elasticsearch tối ưu cho một số thao tác như sort, aggregation và truy cập field trong script. Các kiểu field hỗ trợ doc values thường có thể được truy cập bằng doc['field'].

Ví dụ:

~~~text
doc['price'].value
~~~

Truy cập _source có thể hữu ích khi cần cấu trúc JSON gốc hoặc field không có doc values, nhưng thường tốn chi phí giải mã và truy cập hơn. Trong script chạy trên nhiều document, ưu tiên doc values khi logic cho phép.

Không phải mọi kiểu field đều hỗ trợ doc values theo cùng cách. Text field thường không có doc values mặc định; nếu cần truy cập chuỗi cho sort/aggregation, thường dùng multi-field keyword hoặc cấu hình phù hợp. Kiểm tra mapping thực tế trước khi viết script.

### 2.2. Xử lý field bị thiếu

Không nên giả định mọi document đều có đủ field:

~~~text
if (doc['cost'].size() == 0 || doc['price'].size() == 0) {
    return false;
}
return doc['price'].value > doc['cost'].value;
~~~

Cú pháp return và biểu thức cần phù hợp với script context. Với runtime field, cơ chế phát kết quả là emit(...), không phải return giá trị như một hàm thông thường.

Hãy xác định rõ chính sách cho field thiếu: loại document khỏi kết quả, dùng giá trị mặc định hay báo dữ liệu không hợp lệ. Tránh để script vô tình tạo ra giá trị sai cho document thiếu field.

## 3. Tham số hóa script bằng params

Không nên ghép trực tiếp dữ liệu đầu vào của người dùng vào chuỗi source script. Hãy giữ source ổn định và truyền giá trị động qua params.

Ví dụ source:

~~~text
doc['price'].value >= params.minimum
~~~

Tham số:

~~~json
{
  "minimum": 100000
}
~~~

Lợi ích:

- Tránh phải tạo source string mới cho mỗi giá trị đầu vào.
- Giúp Elasticsearch tái sử dụng script đã biên dịch tốt hơn.
- Tách logic script khỏi dữ liệu nghiệp vụ.
- Giảm nguy cơ đưa chuỗi không tin cậy vào source code của script.

Không đưa input tùy ý vào source script hoặc tên field. Hãy validate giá trị đầu vào và chỉ cho phép lựa chọn field từ danh sách được ứng dụng kiểm soát.

## 4. Script query: lọc document bằng logic tùy chỉnh

Script query dùng biểu thức trả về boolean để xác định document có khớp hay không.

REST DSL:

~~~http
POST /products/_search
{
  "query": {
    "script": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].value - doc['cost'].value > params.minimum",
        "params": {
          "minimum": 30000
        }
      }
    }
  }
}
~~~

Query trả về document có lợi nhuận lớn hơn 30.000 theo đơn vị được lưu trong price và cost.

Script query hữu ích khi điều kiện cần kết hợp nhiều field theo phép tính mà các query chuẩn không biểu đạt trực tiếp. Tuy nhiên, nó thường đắt hơn term/range query vì script phải được thực thi cho các document ứng viên trên shard.

Nếu có thể chuyển điều kiện thành query chuẩn, hãy làm như vậy. Ví dụ lọc price >= 100000 nên dùng range query trên price thay vì script query chỉ để so sánh một field.

### 4.1. Kết hợp script query với filter thông thường

Có thể dùng bool query để lọc sơ bộ bằng điều kiện rẻ trước, sau đó mới chạy script:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 100000
            }
          }
        },
        {
          "script": {
            "script": {
              "lang": "painless",
              "source": "doc['price'].value - doc['cost'].value > params.minimum",
              "params": {
                "minimum": 30000
              }
            }
          }
        }
      ]
    }
  }
}
~~~

Filter active và price thu hẹp tập document trước khi đánh giá điều kiện script. Đây thường là cách tổ chức query dễ hiểu hơn so với đưa toàn bộ logic vào một script.

Script query vẫn có thể tốn CPU trên tập ứng viên còn lại. Cần đo với dữ liệu gần quy mô production.

## 5. Script field: tính giá trị bổ sung cho từng kết quả

Script field không quyết định document có khớp hay không. Nó tính thêm một giá trị cho từng hit được trả về.

Ví dụ thêm lợi nhuận vào kết quả tìm kiếm:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "active": true
    }
  },
  "script_fields": {
    "profit": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].value - doc['cost'].value"
      }
    }
  }
}
~~~

Document được chọn bởi query active=true. Với mỗi hit, Elasticsearch tính field profit và trả về trong phần fields của hit.

Response rút gọn:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "P-1001",
        "_source": {
          "price": 200000,
          "cost": 150000,
          "active": true
        },
        "fields": {
          "profit": [
            50000
          ]
        }
      }
    ]
  }
}
~~~

Script field không ghi profit vào _source và không cập nhật mapping của index. Giá trị chỉ được tính cho response hiện tại.

Dùng script field khi:

- Giao diện cần hiển thị giá trị được tính từ các field khác.
- Phép tính chỉ cần cho một số hit trả về.
- Không cần dùng kết quả tính toán làm điều kiện lọc chính.
- Không cần lưu giá trị tính toán lâu dài.

Nếu cần lọc theo giá trị tính toán, script query hoặc runtime field phù hợp hơn. Nếu phép tính được dùng thường xuyên, cân nhắc lưu field đã tính khi ghi document.

## 6. Runtime field là gì?

Runtime field là field có giá trị được tính khi query chạy thay vì được lưu sẵn trong document source/index theo cách field thông thường được lập chỉ mục.

Có thể khai báo runtime field ở cấp index mapping hoặc trong request tìm kiếm qua runtime_mappings.

Ví dụ runtime field profit kiểu long:

~~~http
POST /products/_search
{
  "runtime_mappings": {
    "profit": {
      "type": "long",
      "script": {
        "source": "if (doc['price'].size() != 0 && doc['cost'].size() != 0) { emit(doc['price'].value - doc['cost'].value); }"
      }
    }
  },
  "query": {
    "range": {
      "profit": {
        "gte": 30000
      }
    }
  },
  "fields": [
    "profit"
  ]
}
~~~

Ở đây:

- runtime_mappings định nghĩa field ảo profit cho request.
- type xác định kiểu dữ liệu của field.
- script tính giá trị và gọi emit(...) để phát giá trị.
- query range có thể tham chiếu profit.
- fields yêu cầu Elasticsearch trả runtime field trong response.

Runtime field không tự ghi dữ liệu vào document. Nếu cùng request cần dùng profit trong query và trả về kết quả, runtime mapping cho phép tái sử dụng định nghĩa field đó.

### 6.1. emit khác return

Trong runtime field script, dùng emit(value) để phát giá trị:

~~~text
emit(doc['price'].value - doc['cost'].value);
~~~

Nếu runtime field có nhiều giá trị, script có thể gọi emit nhiều lần theo kiểu field hỗ trợ.

Không dùng return như script query. Script query cần kết quả boolean theo query context; runtime field cần phát giá trị đúng với kiểu đã khai báo.

### 6.2. Runtime field trong mapping hay trong request?

Runtime field có thể được khai báo ở hai phạm vi:

| Phạm vi | Đặc điểm | Khi phù hợp |
|---|---|---|
| Index mapping | Field runtime được định nghĩa trong mapping và có thể dùng trong nhiều request | Logic dùng chung cho nhiều truy vấn |
| Request runtime_mappings | Field chỉ được khai báo cho một request tìm kiếm | Thử nghiệm, logic tạm thời hoặc khác nhau theo truy vấn |

Ví dụ runtime field trong mapping có thể được khai báo qua mapping API. Request runtime_mappings cho phép thêm field tính toán mà không cần thay mapping của index.

Dù được khai báo ở phạm vi nào, runtime field vẫn phải tính khi được sử dụng. Khai báo trong mapping không biến nó thành field vật lý đã được index như một field thông thường.

## 7. Dùng runtime field trong truy vấn, sort và aggregation

Runtime field có thể được tham chiếu bởi nhiều phần của Search API khi kiểu dữ liệu và API hỗ trợ.

Ví dụ lọc theo lợi nhuận:

~~~http
POST /products/_search
{
  "runtime_mappings": {
    "profit": {
      "type": "long",
      "script": {
        "source": "emit(doc['price'].value - doc['cost'].value)"
      }
    }
  },
  "query": {
    "range": {
      "profit": {
        "gte": 50000
      }
    }
  }
}
~~~

Có thể dùng runtime field trong aggregation:

~~~http
POST /products/_search
{
  "size": 0,
  "runtime_mappings": {
    "profit": {
      "type": "long",
      "script": {
        "source": "emit(doc['price'].value - doc['cost'].value)"
      }
    }
  },
  "aggs": {
    "average_profit": {
      "avg": {
        "field": "profit"
      }
    }
  }
}
~~~

Và trong sort:

~~~http
POST /products/_search
{
  "runtime_mappings": {
    "profit": {
      "type": "long",
      "script": {
        "source": "emit(doc['price'].value - doc['cost'].value)"
      }
    }
  },
  "sort": [
    {
      "profit": {
        "order": "desc"
      }
    }
  ]
}
~~~

Các thao tác này có thể tốn chi phí đáng kể vì script phải tính giá trị cho document được xét. Với field được dùng thường xuyên để filter, sort hoặc aggregate trên lượng dữ liệu lớn, field vật lý được lập chỉ mục thường hiệu quả hơn.

## 8. Script query, script field và runtime field khác nhau thế nào?

| Cơ chế | Vai trò | Có lọc document? | Có trả giá trị tính toán? | Dùng trong query/sort/aggregation? |
|---|---|---:|---:|---|
| Script query | Điều kiện boolean tùy chỉnh | Có | Không phải mục tiêu | Dùng làm query |
| Script field | Tính giá trị cho hit trả về | Không | Có, trong fields | Không dùng như field mapping chung |
| Runtime field | Field ảo tính lúc query | Có thể được query | Có thể trả qua fields | Có, tùy kiểu và API hỗ trợ |
| Field vật lý | Giá trị đã lưu và lập chỉ mục | Có | Có từ source/doc values | Có, thường hiệu quả hơn |

Ví dụ chọn:

- Muốn chỉ trả sản phẩm có lợi nhuận > 50.000: script query hoặc runtime field + range query.
- Muốn hiển thị lợi nhuận của 20 sản phẩm tìm được: script field hoặc runtime field.
- Muốn sort và aggregation theo lợi nhuận trên nhiều request: runtime field có thể dùng, nhưng nên cân nhắc lưu profit thành field vật lý nếu hiệu năng quan trọng.

## 9. NativeQuery trong Spring Data Elasticsearch

NativeQuery cho phép sử dụng các kiểu Query của Elasticsearch Java API Client. Trong Spring Data Elasticsearch 5.x, NativeQuery thuộc package:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
~~~

Một query đơn giản có thể được xây dựng từ Elasticsearch Java API Client:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query query = Query.of(q -> q
    .term(t -> t
        .field("active")
        .value(v -> v.booleanValue(true))
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(query)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

Với script query, tạo Script và gắn vào Query:

~~~java
import co.elastic.clients.elasticsearch._types.Script;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import co.elastic.clients.json.JsonData;

Script script = Script.of(s -> s
    .inline(i -> i
        .lang("painless")
        .source(
            "doc['price'].value - doc['cost'].value > params.minimum"
        )
        .params("minimum", JsonData.of(30000))
    )
);

Query scriptQuery = Query.of(q -> q
    .script(s -> s.script(script))
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(scriptQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

Đoạn code minh họa API của Elasticsearch Java API Client dùng với Spring Data Elasticsearch 5.x. Tên package, builder method và overload cần khớp version dependency của project.

Nếu IDE không nhận .inline(...), .script(...) hoặc withQuery(...), kiểm tra phiên bản Elasticsearch Java API Client và Spring Data Elasticsearch đang dùng. Không trộn kiểu Query của Elasticsearch Java API Client với Query của Spring Data Criteria API; chúng là hai abstraction khác nhau.

## 10. Script field trong NativeQuery

Elasticsearch Java API Client cung cấp kiểu ScriptField để mô tả script field. NativeQuery ở các phiên bản hỗ trợ có builder method để thêm scripted field.

Ví dụ theo API 5.x:

~~~java
import co.elastic.clients.elasticsearch._types.Script;
import co.elastic.clients.elasticsearch._types.ScriptField;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Script profitScript = Script.of(s -> s
    .inline(i -> i
        .lang("painless")
        .source("doc['price'].value - doc['cost'].value")
    )
);

ScriptField profitField = ScriptField.of(f -> f
    .script(profitScript)
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(Query.of(q -> q.matchAll(m -> m)))
    .withScriptedField("profit", profitField)
    .build();
~~~

Tên method withScriptedField và kiểu ScriptField cần xác nhận theo Spring Data Elasticsearch version. Kết quả script field được trả trong metadata fields của search hit; nó không trở thành property trong _source của Product.

Ở tầng ứng dụng, cần đọc field từ SearchHit metadata hoặc cơ chế mapping kết quả mà phiên bản Spring Data cung cấp. Không mặc định rằng một script field sẽ tự động được gán vào property Product nếu entity không có mapping phù hợp.

Nếu cần trả về một DTO có profit, có thể dùng SearchHit metadata để xây dựng response DTO thay vì cố ghi giá trị tính toán vào entity domain.

## 11. Runtime field trong NativeQuery

Elasticsearch Java API Client biểu diễn runtime field bằng kiểu RuntimeField. Với các phiên bản Spring Data Elasticsearch có hỗ trợ runtime field trong NativeQuery builder, có thể truyền map runtime field vào query.

Ví dụ minh họa theo kiểu API Java Client:

~~~java
import co.elastic.clients.elasticsearch._types.Script;
import co.elastic.clients.elasticsearch._types.mapping.RuntimeField;

Script profitScript = Script.of(s -> s
    .inline(i -> i
        .lang("painless")
        .source(
            "if (doc['price'].size() != 0 && doc['cost'].size() != 0) " +
            "{ emit(doc['price'].value - doc['cost'].value); }"
        )
    )
);

RuntimeField profitRuntimeField = RuntimeField.of(r -> r
    .type("long")
    .script(profitScript)
);
~~~

Trong Spring Data versions expose runtime mappings qua NativeQuery builder, runtime field có thể được thêm bằng method tương ứng như withRuntimeField hoặc withRuntimeFields. Tên method và kiểu map cần được xác nhận trên Javadoc của đúng dependency; API này đã thay đổi giữa các thế hệ Spring Data Elasticsearch.

Nếu phiên bản không expose runtime mappings qua NativeQuery builder, có thể dùng Elasticsearch Java API Client trực tiếp để tạo SearchRequest có runtime_mappings, hoặc nâng cấp lên phiên bản tương thích. Không nên giả định CriteriaQuery có thể biểu diễn mọi runtime field option.

Một cách kiểm tra thực tế là xem autocomplete/Javadoc của NativeQuery.Builder và tìm các method runtime field, scripted field, query, sort và aggregation có trong dependency hiện tại.

## 12. Runtime field và Spring Data entity mapping

Runtime field được khai báo trong request không giống field Java thông thường trong entity.

Ví dụ Product có:

~~~java
public class Product {
    private Long price;
    private Long cost;
}
~~~

Runtime field profit có thể được tạo trong request mà không thêm property profit vào class Product. Kết quả profit được trả trong phần fields của search hit.

Nếu muốn map kết quả thành object riêng:

~~~java
public record ProductSearchResult(
    String id,
    Long price,
    Long cost,
    Long profit
) {
}
~~~

Service có thể đọc Product từ hit và lấy profit từ metadata field, rồi tạo DTO. Cách lấy giá trị field cụ thể phụ thuộc kiểu SearchHit và phiên bản Spring Data Elasticsearch.

Đừng nhầm runtime field với @Field trong entity. @Field mô tả mapping field của document; runtime field được tính khi truy vấn và có thể chỉ tồn tại trong phạm vi request.

## 13. Stored script và inline script

Script có thể được gửi trực tiếp trong request (inline) hoặc được lưu trên cluster và tham chiếu bằng ID (stored script).

Inline script:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "doc['price'].value > params.minimum",
    "params": {
      "minimum": 100000
    }
  }
}
~~~

Stored script được đăng ký bằng Stored Scripts API:

~~~http
PUT /_scripts/price-threshold
{
  "script": {
    "lang": "painless",
    "source": "doc['price'].value > params.minimum"
  }
}
~~~

Sau đó gọi bằng ID:

~~~http
POST /products/_search
{
  "query": {
    "script": {
      "script": {
        "id": "price-threshold",
        "params": {
          "minimum": 100000
        }
      }
    }
  }
}
~~~

Stored script hữu ích khi cùng một logic được dùng ở nhiều nơi và cần quản lý tập trung. Thay đổi script cần có quy trình versioning, kiểm thử và triển khai phù hợp.

Dù dùng inline hay stored script, vẫn nên truyền giá trị động bằng params. Không tạo một stored script ID mới cho mỗi request hoặc đưa input tùy ý vào source.

## 14. Giới hạn và hiệu năng của script

Script có thể chạy trên nhiều document và nhiều shard. Một script đơn giản vẫn có thể tốn đáng kể khi áp dụng cho hàng triệu document.

Các nguyên tắc:

- Dùng term, range, exists, bool và các query chuẩn khi có thể.
- Đặt điều kiện filter rẻ để thu hẹp tập document trước script.
- Tránh truy cập _source trong vòng lặp nếu doc values đủ dùng.
- Kiểm tra field thiếu trước khi truy cập value.
- Dùng params để source ổn định và hỗ trợ cache biên dịch.
- Hạn chế script chạy trên tập kết quả lớn.
- Đo latency, CPU và số shard thực thi.
- Tránh script phức tạp trong sort hoặc aggregation nếu có thể lưu sẵn giá trị.

Elasticsearch có các giới hạn và thiết lập bảo mật liên quan đến scripting, bao gồm context được phép, loại script và khả năng sử dụng inline/stored script. Cấu hình cụ thể phụ thuộc phiên bản và chính sách cluster. Không nên thay đổi cluster-wide script settings chỉ để làm một ví dụ chạy được mà chưa hiểu ảnh hưởng bảo mật và vận hành.

### 14.1. Script compilation cache

Elasticsearch biên dịch script và có thể cache compiled script. Nếu source thay đổi liên tục do ghép giá trị request vào chuỗi, cache có thể kém hiệu quả và gây áp lực compilation.

Giữ source ổn định:

~~~text
doc['price'].value > params.minimum
~~~

và chỉ thay params.minimum theo request.

Điều này vừa giúp code rõ ràng vừa hỗ trợ tái sử dụng script đã biên dịch.

### 14.2. Script không phải nơi thay thế mọi business logic

Không đưa toàn bộ logic nghiệp vụ phức tạp vào Painless chỉ vì có thể truy cập field. Các quy tắc liên quan nhiều hệ thống, authorization, trạng thái giao dịch hoặc kiểm tra cần thông báo lỗi chi tiết thường phù hợp hơn ở tầng ứng dụng.

Script nên thực hiện phép tính hoặc điều kiện gọn, sát dữ liệu và có thể kiểm soát trong query.

## 15. Runtime field so với field được lưu sẵn

Giả sử lợi nhuận luôn bằng price - cost. Có hai lựa chọn:

**Tính lúc truy vấn bằng runtime field**

Ưu điểm:
- Không cần cập nhật document cũ khi đổi logic tính toán.
- Không tăng kích thước _source bằng field tính sẵn.
- Có thể thử nghiệm logic nhanh.

Hạn chế:
- Tính toán mỗi lần query cần field.
- Query, sort và aggregation có thể tốn CPU.
- Không có inverted index/doc values được tạo sẵn như field vật lý.
- Phụ thuộc script và runtime field support của Elasticsearch.

**Lưu profit khi ghi document**

Ưu điểm:
- Query/filter/sort/aggregation thường hiệu quả hơn.
- Có thể dùng mapping và index structure thông thường.
- Giảm việc tính lại cùng một biểu thức ở mọi request.

Hạn chế:
- Phải cập nhật profit khi price hoặc cost thay đổi.
- Có thể phát sinh dữ liệu không nhất quán nếu luồng ghi không cập nhật đủ field.
- Khi đổi công thức, cần migration hoặc reindex dữ liệu.

| Tiêu chí | Runtime field | Field vật lý |
|---|---|---|
| Lưu trong document source | Không bắt buộc | Có |
| Tính khi query | Có | Không, nếu đã ghi sẵn |
| Cập nhật công thức | Có thể đổi script | Cần cập nhật dữ liệu |
| Filter/sort/aggregation thường xuyên | Có thể tốn chi phí | Thường hiệu quả hơn |
| Thử nghiệm logic | Thuận tiện | Cần thay đổi pipeline ghi |
| Phù hợp | Logic ít dùng hoặc cần linh hoạt | Field quan trọng, dùng thường xuyên |

## 16. NativeQuery và sự khác nhau giữa các phiên bản

API NativeQuery đã thay đổi theo thế hệ client và Spring Data Elasticsearch. Khi làm việc với script và runtime field, phải biết project đang dùng phiên bản nào.

| Thế hệ | Kiểu API thường gặp | Điểm cần chú ý |
|---|---|---|
| Spring Data Elasticsearch 4.x và cũ hơn | NativeSearchQuery, NativeSearchQueryBuilder, thường gắn với RestHighLevelClient | Không dùng trực tiếp builder/type của Elasticsearch Java API Client 8.x nếu dependency chưa chuyển đổi |
| Spring Data Elasticsearch 5.x | NativeQuery và Elasticsearch Java API Client | Query, Script, ScriptField, RuntimeField dùng kiểu từ co.elastic.clients |
| Các bản 5.x khác nhau | Builder và overload có thể bổ sung theo release | Kiểm tra Javadoc/source của đúng minor version |
| Các bản mới hơn | Có thể thay đổi client/API theo Elasticsearch compatibility | Kiểm tra ma trận tương thích Spring Data, Spring Boot và Elasticsearch |

Không trộn các kiểu sau:

- org.springframework.data.elasticsearch.core.query.Query: abstraction query của Spring Data.
- co.elastic.clients.elasticsearch._types.query_dsl.Query: query type của Elasticsearch Java API Client.
- Các lớp query của RestHighLevelClient trong dự án cũ.

NativeQuery của thế hệ Elasticsearch Java Client nhận kiểu query tương ứng từ client. CriteriaQuery vẫn là Spring Data Query abstraction. Khi chuyển đổi giữa hai API, hãy tạo đúng loại query mà method overload yêu cầu.

### 16.1. Cách xác định API trong project

Kiểm tra dependency tree hoặc build file để xác định version Spring Data Elasticsearch và Elasticsearch Java API Client. Sau đó:

1. Mở Javadoc hoặc autocomplete của NativeQuery.Builder.
2. Xác nhận method withQuery nhận kiểu Query nào.
3. Kiểm tra có withScriptedField, withRuntimeField hoặc withRuntimeFields hay không.
4. Xem Script và RuntimeField thuộc package client nào.
5. Đối chiếu version Elasticsearch server với client.
6. Chạy integration test trên Elasticsearch version tương ứng.

Nếu project dùng NativeSearchQueryBuilder của thế hệ cũ, ví dụ NativeQuery 5.x không thể copy nguyên vào. Hãy dùng API tương ứng hoặc lên kế hoạch nâng cấp dependency đồng bộ.

## 17. Kiểm thử script và runtime field

Không nên chỉ kiểm tra script bằng cách đọc source. Hãy chạy query trên Elasticsearch test instance với dữ liệu đại diện.

Ví dụ tạo ba sản phẩm:

~~~json
POST /products/_bulk
{"index":{"_id":"P-1"}}
{"price":200000,"cost":150000,"active":true}
{"index":{"_id":"P-2"}}
{"price":250000,"cost":220000,"active":true}
{"index":{"_id":"P-3"}}
{"price":90000,"cost":40000,"active":false}
~~~

Kiểm tra script query với minimum = 30000:

~~~http
POST /products/_search
{
  "query": {
    "script": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].value - doc['cost'].value > params.minimum",
        "params": {
          "minimum": 30000
        }
      }
    }
  }
}
~~~

P-1 và P-3 có lợi nhuận lớn hơn 30.000, còn P-2 không thỏa. Nếu chỉ muốn sản phẩm active, thêm filter active=true.

Kiểm tra runtime field:

~~~http
POST /products/_search
{
  "runtime_mappings": {
    "profit": {
      "type": "long",
      "script": {
        "source": "if (doc['price'].size() != 0 && doc['cost'].size() != 0) { emit(doc['price'].value - doc['cost'].value); }"
      }
    }
  },
  "fields": ["profit"],
  "query": {
    "range": {
      "profit": {
        "gte": 30000
      }
    }
  }
}
~~~

Test nên bao gồm:

- Document có đủ field.
- Document thiếu price hoặc cost.
- Giá trị âm hoặc bằng 0 nếu nghiệp vụ cho phép.
- Kiểu field không đúng mapping.
- Query có params ở các giá trị biên.
- Runtime field có kiểu khai báo phù hợp với giá trị emit.
- Kết quả fields được đọc đúng ở tầng Spring Data.

Nếu runtime field dùng trong query, sort hoặc aggregation, hãy test từng hành vi riêng. Một runtime field trả đúng giá trị không tự chứng minh sort và aggregation đang có semantics mong muốn.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Script compilation error | Cú pháp Painless hoặc context không phù hợp | Xem error message, kiểm tra biến và hàm được phép |
| No field found / field access error | Sai field name hoặc mapping chưa tồn tại | Đọc mapping và kiểm tra document |
| Field thiếu làm script lỗi | Truy cập .value khi không có giá trị | Kiểm tra .size() trước khi đọc |
| Script query chậm | Chạy trên quá nhiều document | Dùng filter chuẩn thu hẹp tập ứng viên |
| Script compilation rate cao | Source thay đổi liên tục | Đưa dữ liệu động vào params |
| Runtime field không xuất hiện trong _source | Runtime field không ghi vào source | Đọc từ fields trong search hit |
| Runtime field không dùng được trong query | Khai báo sai type/script hoặc version/API không hỗ trợ | Kiểm tra runtime_mappings và mapping |
| NativeQuery không nhận Script type | Trộn API của Spring Data và Elasticsearch client | Kiểm tra import và version |
| withRuntimeField không tồn tại | Spring Data minor version không expose builder method đó | Xem Javadoc, dùng client trực tiếp hoặc nâng cấp |
| Script bị từ chối | Cluster policy/script context hạn chế | Kiểm tra quyền và cấu hình scripting của cluster |
| Giá trị runtime sai | emit sai kiểu, thiếu field hoặc đơn vị không thống nhất | Kiểm tra type, dữ liệu và script |

## 19. Quy trình lựa chọn

Có thể chọn cơ chế theo nhu cầu:

1. Nếu điều kiện có thể viết bằng term, range, exists hoặc bool query, dùng query chuẩn.
2. Nếu cần lọc bằng một phép tính tùy chỉnh, cân nhắc script query.
3. Nếu chỉ cần thêm giá trị tính toán vào từng hit, dùng script field.
4. Nếu cần một field ảo có thể được query, sort hoặc aggregate, dùng runtime field.
5. Nếu phép tính được dùng thường xuyên và ảnh hưởng hiệu năng, cân nhắc lưu field vật lý.
6. Nếu Criteria không biểu đạt được DSL cần thiết, dùng NativeQuery.
7. Nếu NativeQuery builder của version hiện tại không expose tùy chọn, dùng Elasticsearch Java API Client trực tiếp hoặc nâng cấp có kiểm soát.

## 20. Bảng tra cứu nhanh

| Nhu cầu | API |
|---|---|
| Lọc document bằng script | script query |
| Thêm giá trị tính toán vào hit | script_fields |
| Tạo field ảo trong một search request | runtime_mappings |
| Định nghĩa runtime field dùng chung | runtime field trong index mapping |
| Tính điểm tìm kiếm | script_score / function_score |
| Dùng query DSL từ Java API Client | NativeQuery |
| Dùng giá trị động an toàn | script params |
| Dùng script lặp lại nhiều nơi | stored script |
| Tránh tính lại field thường xuyên | Lưu field vật lý khi ghi |
| API builder không có tùy chọn cần thiết | Elasticsearch Java API Client trực tiếp hoặc nâng cấp version |

Script, script field và runtime field mở rộng khả năng truy vấn của NativeQuery khi CriteriaQuery hoặc derived query không đủ biểu đạt. Hãy phân biệt script dùng để lọc, script field dùng để bổ sung giá trị cho hit và runtime field dùng như một field tính toán lúc query. Tham số hóa script, xử lý field thiếu, kiểm soát chi phí thực thi và xác nhận API theo đúng phiên bản Spring Data Elasticsearch cùng Elasticsearch Java API Client của dự án.

