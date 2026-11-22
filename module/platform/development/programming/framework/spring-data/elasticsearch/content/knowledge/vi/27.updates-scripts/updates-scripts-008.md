# Scripted field và runtime field trong tìm kiếm

## 1. Vì sao cần field được tính toán khi tìm kiếm?

Document trong Elasticsearch thường chứa các field đã được index như tên, trạng thái, ngày tạo hoặc giá tiền. Tuy nhiên, ứng dụng đôi khi cần một giá trị được suy ra từ những field đã có mà không muốn ghi thêm giá trị đó vào document.

Ví dụ, một sản phẩm có:

~~~json
{
  "name": "Wireless Headphones",
  "category": "audio",
  "price": 1200000,
  "taxRate": 0.1
}
~~~

Ứng dụng có thể cần hiển thị giá sau thuế:

\[
priceWithTax = price \times (1 + taxRate)
\]

Hoặc một đơn hàng có thể cần:

- Tính tổng tiền từ số lượng và đơn giá.
- Ghép tên đầy đủ từ họ và tên.
- Phân loại đơn hàng theo số lượng sản phẩm.
- Tính số ngày kể từ ngày tạo.
- Chuẩn hóa một giá trị để phục vụ bộ lọc.
- Tạo nhãn từ nhiều field có sẵn.

Có thể tính các giá trị này trong Java sau khi nhận document. Tuy nhiên, khi cần dùng giá trị tính toán trong chính thao tác tìm kiếm, cách đó không đủ. Ví dụ, ứng dụng muốn tìm tất cả sản phẩm có giá sau thuế từ 1.500.000 trở lên. Nếu chỉ tính sau khi nhận kết quả, Elasticsearch chưa thể lọc document theo giá trị đó.

Elasticsearch hỗ trợ hai cơ chế quan trọng:

- **Scripted field (script_fields):** chạy script cho mỗi hit đã được chọn và bổ sung giá trị tính toán vào response.
- **Runtime field:** định nghĩa một field được tính trong lúc tìm kiếm. Field này có thể tham gia query, filter, sort, aggregation và có thể được trả về cho ứng dụng.

Cả hai đều giúp tạo giá trị từ dữ liệu đã lưu. Điểm khác biệt chính là runtime field có thể tham gia vào giai đoạn chọn document, còn scripted field chỉ bổ sung dữ liệu cho những hit đã được chọn.

## 2. Phân biệt Scripted field và Runtime field

Hai khái niệm có thể cùng dùng Painless và cùng đọc dữ liệu của document, nhưng mục đích khác nhau.

| Tiêu chí | Scripted field | Runtime field |
|---|---|---|
| API Elasticsearch | `script_fields` | `runtime_mappings` hoặc `runtime` trong mapping |
| Thời điểm thực thi | Fetch phase, sau khi query đã chọn hit | Query time, khi field được dùng trong tìm kiếm |
| Lọc document theo giá trị tính toán | Không | Có |
| Sort theo giá trị tính toán | Không | Có |
| Aggregation theo giá trị tính toán | Không | Có |
| Trả giá trị trong response | Có, dưới `fields` | Có thể dùng `fields` để lấy giá trị |
| Phạm vi khai báo | Một search request | Một search request hoặc mapping của index |
| Ghi giá trị vào `_source` | Không | Mặc định không |
| Cú pháp trả kết quả Painless | Trả về giá trị bằng `return` hoặc biểu thức cuối | Dùng `emit(...)` |

Ví dụ yêu cầu:

- Chỉ muốn hiển thị thêm giá sau thuế cho 20 sản phẩm đã tìm được: dùng scripted field.
- Muốn tìm sản phẩm có giá sau thuế lớn hơn một ngưỡng: dùng runtime field.
- Muốn nhóm sản phẩm theo giá sau thuế: dùng runtime field.
- Muốn sắp xếp sản phẩm theo giá sau thuế: dùng runtime field.

Có thể ghi nhớ:

~~~text
Scripted field
  Query chọn document
        |
        v
  Script tính giá trị cho từng hit
        |
        v
  Response có thêm field tính toán

Runtime field
  Khai báo field và script
        |
        v
  Query / Filter / Sort / Aggregation
        |
        v
  Giá trị được tính khi cần
        |
        v
  Response có thể trả field tính toán
~~~

Không nên dùng scripted field khi cần lọc hoặc sắp xếp theo giá trị tính toán. Ngược lại, nếu chỉ cần trang trí dữ liệu trong response, runtime field có thể làm thêm công việc ở query phase mà ứng dụng không cần.

## 3. Painless và ngữ cảnh thực thi script

Elasticsearch sử dụng **Painless** làm ngôn ngữ scripting mặc định. Painless được thiết kế để chạy script trong các ngữ cảnh của Elasticsearch như tìm kiếm, tính score, aggregation, cập nhật document và ingest.

Một script thường có ba phần:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "doc['price'].value * params.taxRate",
    "params": {
      "taxRate": 1.1
    }
  }
}
~~~

- `lang`: ngôn ngữ script; thường là `painless`.
- `source`: nội dung script inline.
- `params`: các tham số truyền vào script.

Painless có các biến và API khác nhau tùy ngữ cảnh. Vì vậy, cùng một biểu thức có thể cần cách trả kết quả khác nhau.

### Các biến thường gặp

| Biến | Ý nghĩa |
|---|---|
| `doc` | Truy cập giá trị field qua doc values |
| `params` | Các tham số do request truyền vào |
| `params._source` | Truy cập nội dung `_source` của document |
| `ctx` | Ngữ cảnh document trong một số thao tác cập nhật hoặc ingest |
| `emit()` | Phát giá trị cho runtime field |

Trong scripted field và runtime field, thường dùng `doc['field']` để đọc field có doc values. Đây thường là cách truy cập hiệu quả hơn so với tải và phân tích toàn bộ `_source`.

Không phải mọi field đều có doc values. Field `text` được phân tích thường không có doc values mặc định. Không nên bật fielddata trên text chỉ để dùng script nếu chưa đánh giá bộ nhớ và chi phí CPU.

### Truy cập giá trị field

Ví dụ đọc giá:

~~~java
double price = doc['price'].value;
~~~

Trong Painless, `doc['price']` là danh sách giá trị của field. Với field một giá trị, `.value` lấy giá trị đó.

Nếu field có thể thiếu, cần kiểm tra trước khi đọc:

~~~java
if (doc.containsKey('price') && doc['price'].size() != 0) {
    // Có thể đọc doc['price'].value
}
~~~

`doc.containsKey('price')` kiểm tra field có trong mapping hay không. `doc['price'].size() != 0` kiểm tra document hiện tại có giá trị cho field đó hay không.

Nếu bỏ qua kiểm tra và document thiếu giá, script có thể phát sinh lỗi khi truy cập `.value`.

### Truy cập _source

Có thể đọc dữ liệu từ `_source`:

~~~java
def name = params._source['name'];
~~~

Cách này hữu ích khi cần đọc cấu trúc object hoặc dữ liệu không có doc values. Tuy nhiên, `_source` cần được tải và phân tích, thường chậm hơn đọc một giá trị qua doc values.

Ưu tiên `doc['field']` khi có thể. Dùng `_source` khi thật sự cần cấu trúc JSON hoặc dữ liệu không được cung cấp qua doc values.

## 4. Scripted field trong Elasticsearch

Scripted field được khai báo ở phần `script_fields` của search request. Script chạy cho từng hit được chọn và tạo thêm một giá trị trong response.

Ví dụ tính giá sau thuế:

~~~http
GET /products/_search
{
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "script_fields": {
    "price_with_tax": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].value * params.taxRate",
        "params": {
          "taxRate": 1.1
        }
      }
    }
  }
}
~~~

Query chọn các sản phẩm thuộc danh mục audio. Sau đó, scripted field tính giá sau thuế cho từng hit được trả về.

Response có cấu trúc tương tự:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "p-01",
        "_source": {
          "name": "Wireless Headphones",
          "category": "audio",
          "price": 1200000
        },
        "fields": {
          "price_with_tax": [
            1320000.0
          ]
        }
      }
    ]
  }
}
~~~

Giá trị tính toán nằm trong `fields.price_with_tax`, không được ghi vào `_source`.

Một scripted field có thể trả một giá trị hoặc nhiều giá trị. Elasticsearch thường biểu diễn dữ liệu trong `fields` dưới dạng mảng, kể cả khi chỉ có một giá trị.

### Scripted field không tham gia điều kiện query

Không thể dùng `price_with_tax` trong range query của cùng request trên chỉ vì nó đã được khai báo trong `script_fields`.

Ví dụ sau không có ý nghĩa như mong muốn:

~~~json
{
  "query": {
    "range": {
      "price_with_tax": {
        "gte": 1500000
      }
    }
  },
  "script_fields": {
    "price_with_tax": {
      "script": {
        "source": "doc['price'].value * 1.1"
      }
    }
  }
}
~~~

Query phase cần chọn document trước khi fetch phase chạy scripted field. Vì vậy, query không thể dùng kết quả của scripted field để lọc document. Hãy chuyển phép tính thành runtime field nếu cần lọc theo giá trị đó.

## 5. Runtime field trong Elasticsearch

Runtime field là field được tính khi tìm kiếm thay vì được lưu như một field thông thường trong inverted index hoặc doc values.

Có hai nơi để khai báo runtime field:

1. Trong mapping của index, bên dưới phần `runtime`.
2. Trong một search request, bên dưới `runtime_mappings`.

Runtime field có thể được dùng trong:

- Query và filter.
- Range query.
- Sort.
- Aggregation.
- Trường `fields` của response.

Khi khai báo runtime field, script phải dùng `emit(...)` để phát giá trị. Một script có thể gọi `emit` nhiều lần để tạo field đa trị. `emit` không nhận `null`; nếu document không có dữ liệu hợp lệ thì không gọi `emit`.

### Runtime field chỉ tồn tại trong một search request

Ví dụ tính giá sau thuế trong một request:

~~~http
GET /products/_search
{
  "runtime_mappings": {
    "price_with_tax": {
      "type": "double",
      "script": {
        "source": """
          if (doc.containsKey('price') && doc['price'].size() != 0) {
            emit(doc['price'].value * params.taxRate);
          }
        """,
        "params": {
          "taxRate": 1.1
        }
      }
    }
  },
  "query": {
    "range": {
      "price_with_tax": {
        "gte": 1500000
      }
    }
  },
  "fields": [
    "price_with_tax"
  ]
}
~~~

Elasticsearch tạo runtime field `price_with_tax` trong phạm vi request này. Range query có thể sử dụng field đó để chọn document.

Runtime field không được thêm vĩnh viễn vào mapping của index. Request khác muốn dùng cùng field cần khai báo lại runtime mapping hoặc dùng một runtime field đã được định nghĩa trong mapping.

### Runtime field có thể thay thế field đã mapping trong một request

Nếu runtime field có cùng tên với một field đã tồn tại trong mapping, định nghĩa runtime field trong request có thể ghi đè giá trị field đó trong phạm vi tìm kiếm.

Tính năng này hữu ích khi thử nghiệm cách tính mới hoặc kiểm tra dữ liệu trước khi thay đổi mapping. Tuy nhiên, cần thận trọng khi dùng cùng tên field vì query có thể không còn sử dụng giá trị đã lập chỉ mục như người đọc request mong đợi.

## 6. Dùng runtime field trong filter, sort và aggregation

Runtime field có thể tham gia vào các thành phần tìm kiếm như field thông thường.

Ví dụ tính giá sau thuế, lọc theo khoảng giá, sắp xếp và nhóm theo danh mục:

~~~http
GET /products/_search
{
  "runtime_mappings": {
    "price_with_tax": {
      "type": "double",
      "script": {
        "source": "emit(doc['price'].value * params.taxRate)",
        "params": {
          "taxRate": 1.1
        }
      }
    }
  },
  "query": {
    "range": {
      "price_with_tax": {
        "gte": 1000000,
        "lte": 2500000
      }
    }
  },
  "sort": [
    {
      "price_with_tax": {
        "order": "asc"
      }
    }
  ],
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 10
      },
      "aggs": {
        "average_price_with_tax": {
          "avg": {
            "field": "price_with_tax"
          }
        }
      }
    }
  },
  "fields": [
    "price_with_tax"
  ]
}
~~~

Trong request:

- Runtime field tính giá sau thuế.
- Range query chỉ giữ sản phẩm trong khoảng giá.
- Sort sắp xếp theo giá sau thuế.
- Terms aggregation nhóm theo danh mục.
- Metric `avg` tính giá sau thuế trung bình trong mỗi nhóm.
- `fields` yêu cầu trả giá trị runtime field cho từng hit.

Đây là điểm khác biệt quan trọng so với scripted field. Scripted field chỉ bổ sung giá trị cho hit đã được chọn; runtime field có thể ảnh hưởng chính việc chọn và sắp xếp hit.

## 7. Định nghĩa runtime field trong mapping của index

Nếu nhiều request cần dùng cùng một runtime field, có thể định nghĩa nó trong mapping để không phải gửi lại script ở từng search request.

Ví dụ tạo index:

~~~http
PUT /products
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      }
    },
    "runtime": {
      "price_with_tax": {
        "type": "double",
        "script": {
          "source": """
            if (doc.containsKey('price') && doc['price'].size() != 0) {
              emit(doc['price'].value * params.taxRate);
            }
          """,
          "params": {
            "taxRate": 1.1
          }
        }
      }
    }
  }
}
~~~

Sau khi runtime field đã được khai báo trong mapping, request có thể sử dụng nó mà không cần gửi `runtime_mappings`:

~~~http
GET /products/_search
{
  "query": {
    "range": {
      "price_with_tax": {
        "gte": 1500000
      }
    }
  },
  "fields": [
    "price_with_tax"
  ]
}
~~~

Runtime field trong mapping có phạm vi dùng chung cho các request trên index. Runtime field trong search request chỉ tồn tại trong request đó.

Khi cần sửa một runtime field thông thường trong mapping, có thể cập nhật hoặc xóa định nghĩa qua Mapping API. Hãy lưu ý rằng việc thay đổi định nghĩa trong khi query đang chạy có thể khiến các shard quan sát các phiên bản mapping khác nhau trong khoảng thời gian cập nhật.

## 8. Chọn kiểu dữ liệu runtime field

Runtime field cần khai báo kiểu dữ liệu để Elasticsearch biết cách xử lý giá trị do script phát ra.

Các kiểu runtime field phổ biến gồm:

| Kiểu | Giá trị phát ra | Ví dụ sử dụng |
|---|---|---|
| `boolean` | `true` hoặc `false` | Đơn hàng có giao trễ không |
| `date` | Giá trị ngày/thời gian | Ngày được suy ra từ timestamp |
| `double` | Số thực | Giá sau thuế, tỷ lệ chuyển đổi |
| `long` | Số nguyên | Tuổi, số ngày, số lượng |
| `keyword` | Chuỗi không phân tích | Nhóm trạng thái, nhãn phân loại |
| `ip` | Địa chỉ IP | Địa chỉ được chuẩn hóa hoặc suy ra |
| `geo_point` | Điểm địa lý | Điểm được tính từ dữ liệu khác |

Ví dụ runtime field kiểu keyword để phân loại đơn hàng:

~~~json
{
  "runtime_mappings": {
    "order_size": {
      "type": "keyword",
      "script": {
        "source": """
          if (doc['quantity'].size() == 0) {
            return;
          }

          long quantity = doc['quantity'].value;

          if (quantity == 1) {
            emit('single');
          } else if (quantity <= 3) {
            emit('small');
          } else if (quantity <= 6) {
            emit('medium');
          } else {
            emit('large');
          }
        """
      }
    }
  },
  "aggs": {
    "order_sizes": {
      "terms": {
        "field": "order_size"
      }
    }
  }
}
~~~

Runtime field `order_size` có thể được dùng trong terms aggregation để thống kê số lượng đơn hàng theo nhóm.

Nếu script có thể phát nhiều giá trị cho cùng một document, hãy gọi `emit` nhiều lần. Kiểu của mọi giá trị được phát ra phải phù hợp với kiểu runtime field đã khai báo.

## 9. Kiểm tra field thiếu và dữ liệu không hợp lệ

Một trong những lỗi phổ biến là truy cập `.value` khi document không có giá trị cho field.

Ví dụ không an toàn:

~~~painless
emit(doc['price'].value * 1.1);
~~~

Nếu field `price` không có trong mapping hoặc document hiện tại không có giá trị, script có thể phát sinh lỗi.

Cách kiểm tra:

~~~painless
if (doc.containsKey('price') && doc['price'].size() != 0) {
    emit(doc['price'].value * 1.1);
}
~~~

Hai điều kiện bảo vệ hai tình huống khác nhau:

- `doc.containsKey('price')`: field tồn tại trong mapping.
- `doc['price'].size() != 0`: document hiện tại có ít nhất một giá trị.

Nếu dữ liệu có thể là số âm hoặc nằm ngoài miền nghiệp vụ, hãy kiểm tra thêm trước khi tính toán.

Ví dụ:

~~~painless
if (doc.containsKey('price') && doc['price'].size() != 0) {
    double price = doc['price'].value;

    if (price >= 0 && price <= params.maxPrice) {
        emit(price * params.taxRate);
    }
}
~~~

Không nên gọi `emit(null)`. Nếu không có giá trị hợp lệ, hãy bỏ qua việc emit cho document đó.

## 10. Script parameters và cache biên dịch

Elasticsearch biên dịch script và lưu bản đã biên dịch trong cache. Nếu ứng dụng thay đổi nội dung `source` mỗi lần chỉ để thay một con số, Elasticsearch có thể phải biên dịch nhiều script khác nhau.

Không nên tạo script source theo kiểu nối chuỗi:

~~~java
String source = "doc['price'].value * " + taxRate;
~~~

Nên giữ source ổn định và truyền dữ liệu thay đổi qua `params`:

~~~json
{
  "script": {
    "source": "doc['price'].value * params.taxRate",
    "params": {
      "taxRate": 1.1
    }
  }
}
~~~

Khi `taxRate` thay đổi, Elasticsearch vẫn có thể tái sử dụng script đã biên dịch vì nội dung source không đổi.

Lợi ích:

- Giảm số lần biên dịch script.
- Tái sử dụng compiled script cache.
- Dễ kiểm soát giá trị đầu vào.
- Tránh tạo source khác nhau từ dữ liệu người dùng.
- Tách logic tính toán khỏi tham số nghiệp vụ.

Nếu cùng một script được dùng ở nhiều nơi, có thể cân nhắc stored script. Ứng dụng gửi ID của stored script cùng params thay vì gửi toàn bộ source trong từng request.

## 11. Truy cập doc values và _source trong script

Có hai cách phổ biến để đọc dữ liệu document:

~~~painless
doc['price'].value
~~~

và:

~~~painless
params._source['price']
~~~

`doc['field']` truy cập doc values. Doc values được tổ chức theo cột, phù hợp để đọc một field từ nhiều document. Đây thường là cách ưu tiên cho script tìm kiếm và aggregation.

`params._source` đọc cấu trúc JSON gốc của document. Cách này phù hợp khi cần truy cập object lồng nhau hoặc dữ liệu không có doc values, nhưng Elasticsearch phải tải và phân tích `_source`, nên thường tốn chi phí hơn.

| Cách đọc | Ưu điểm | Hạn chế |
|---|---|---|
| `doc['field']` | Thường nhanh hơn, phù hợp cho nhiều document | Chỉ truy cập giá trị có doc values, không trả object JSON |
| `params._source` | Đọc được cấu trúc JSON gốc | Phải tải và parse source, thường chậm hơn |

Ví dụ scripted field ghép tên từ hai field:

~~~json
{
  "script_fields": {
    "full_name": {
      "script": {
        "lang": "painless",
        "source": "params._source['first_name'] + ' ' + params._source['last_name']"
      }
    }
  }
}
~~~

Nếu `first_name` và `last_name` có thể thiếu, cần kiểm tra null hoặc giá trị tồn tại trong script trước khi ghép.

Không bật fielddata trên `text` chỉ để truy cập từ script khi chưa đánh giá chi phí. Với nhu cầu đọc chuỗi nguyên văn, field `keyword` hoặc multi-field keyword thường phù hợp hơn.

## 12. Spring Data Elasticsearch hỗ trợ Scripted field

Spring Data Elasticsearch cung cấp hai thành phần có tên gần giống nhau:

- Annotation `org.springframework.data.elasticsearch.annotations.ScriptedField`: đánh dấu property trong entity là nơi nhận giá trị scripted field từ response.
- Class `org.springframework.data.elasticsearch.core.query.ScriptedField`: mô tả scripted field cần gửi trong query.

Annotation trên entity giúp Spring Data không tạo mapping thông thường cho property đó. Property được dùng làm nơi nhận giá trị tính toán khi ánh xạ kết quả tìm kiếm.

Ví dụ entity sản phẩm:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.ScriptedField;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @ScriptedField
    private Double priceWithTax;

    // Constructors, getters và setters
}
~~~

`priceWithTax` không phải field được ghi vào `_source` khi lưu sản phẩm. Nó là property để nhận giá trị do scripted field trả về trong search response.

Có thể dùng thuộc tính `name` của annotation nếu tên scripted field trong response khác tên property Java:

~~~java
@ScriptedField(name = "price_with_tax")
private Double priceWithTax;
~~~

## 13. Tạo ScriptedField bằng Spring Data Elasticsearch

Spring Data cung cấp class `ScriptedField` cùng `ScriptData` để mô tả script.

Ví dụ tính giá sau thuế:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.query.ScriptData;
import org.springframework.data.elasticsearch.core.query.ScriptedField;

ScriptData scriptData = ScriptData.of(
    "painless",
    "doc['price'].value * params.taxRate",
    null,
    Map.of("taxRate", 1.1)
);

ScriptedField scriptedField = ScriptedField.of(
    "priceWithTax",
    scriptData
);
~~~

`ScriptData.of` nhận:

1. Ngôn ngữ script, ở đây là `painless`.
2. Nội dung source của script.
3. Tên stored script nếu dùng stored script; ở ví dụ inline thì để `null`.
4. Map các tham số truyền vào script.

Sau đó, gắn scripted field vào query:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;
import org.springframework.data.elasticsearch.core.query.StringQuery;

StringQuery query = new StringQuery("""
    {
      "match_all": {}
    }
    """);

query.addScriptedField(scriptedField);

query.addSourceFilter(
    FetchSourceFilter.of(b -> b.withIncludes("*"))
);

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

`addScriptedField` thêm script vào phần `script_fields` của search request. Source filter được cấu hình để lấy lại các field bình thường trong document source cùng với giá trị tính toán.

Spring Data ánh xạ giá trị `priceWithTax` trong response vào property có annotation `@ScriptedField`.

Có thể đọc kết quả:

~~~java
for (var hit : hits) {
    Product product = hit.getContent();

    System.out.println(product.getPrice());
    System.out.println(product.getPriceWithTax());
}
~~~

`priceWithTax` chỉ có giá trị trong kết quả tìm kiếm được tạo bởi request có scripted field. Nếu lưu hoặc đọc entity theo thao tác thông thường, không nên kỳ vọng property này tự được tính.

## 14. Dùng ScriptedField trong Repository

Có thể truyền scripted field vào repository method. Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.ScriptedField;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    SearchHits<Product> findAllBy(ScriptedField scriptedField);
}
~~~

Khi gọi:

~~~java
SearchHits<Product> hits =
    repository.findAllBy(scriptedField);
~~~

Spring Data dùng scripted field được truyền vào để bổ sung giá trị trong kết quả.

Cách này phù hợp khi repository method chỉ cần một query tìm kiếm cơ bản và một tập scripted field cụ thể. Nếu cần kết hợp nhiều điều kiện query, runtime mapping, sort hoặc aggregation phức tạp, có thể dùng `ElasticsearchOperations` với implementation của `Query`.

## 15. Spring Data Elasticsearch hỗ trợ RuntimeField

Spring Data cung cấp class:

`org.springframework.data.elasticsearch.core.query.RuntimeField`

Constructor thường dùng:

~~~java
new RuntimeField(
    "priceWithTax",
    "double",
    "emit(doc['price'].value * params.taxRate)",
    Map.of("taxRate", 1.1)
);
~~~

Các tham số:

- Tên runtime field.
- Kiểu dữ liệu của field.
- Painless script.
- Map tham số cho script.

Ví dụ hoàn chỉnh:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.query.RuntimeField;

RuntimeField runtimeField = new RuntimeField(
    "priceWithTax",
    "double",
    "emit(doc['price'].value * params.taxRate)",
    Map.of("taxRate", 1.1)
);
~~~

Khác với scripted field, script runtime phải gọi `emit` để phát giá trị. Kiểu `double` cho biết giá trị tính toán là số thực.

Nếu field có thể thiếu, nên thêm điều kiện kiểm tra:

~~~java
RuntimeField runtimeField = new RuntimeField(
    "priceWithTax",
    "double",
    """
    if (doc.containsKey('price') && doc['price'].size() != 0) {
        emit(doc['price'].value * params.taxRate);
    }
    """,
    Map.of("taxRate", 1.1)
);
~~~

## 16. Dùng RuntimeField trong CriteriaQuery

Có thể gắn runtime field vào CriteriaQuery rồi sử dụng field đó trong điều kiện tìm kiếm.

Ví dụ tìm sản phẩm audio có giá sau thuế lớn hơn hoặc bằng một mức tối thiểu:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;
import org.springframework.data.elasticsearch.core.query.RuntimeField;

RuntimeField runtimeField = new RuntimeField(
    "priceWithTax",
    "double",
    "emit(doc['price'].value * params.taxRate)",
    Map.of("taxRate", 1.1)
);

CriteriaQuery query = CriteriaQuery.builder(
        Criteria.where("category").is("audio")
            .and("priceWithTax").greaterThanEqual(1500000)
    )
    .withRuntimeFields(List.of(runtimeField))
    .withFields("priceWithTax")
    .withSourceFilter(
        FetchSourceFilter.of(b -> b.withIncludes("*"))
    )
    .build();

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

Các bước:

1. Tạo runtime field tên `priceWithTax`.
2. Gắn runtime field vào query bằng `withRuntimeFields`.
3. Dùng `priceWithTax` trong Criteria để lọc.
4. Dùng `withFields` để yêu cầu giá trị runtime field trong response.
5. Dùng source filter để lấy các field bình thường của document.
6. Thực thi bằng `ElasticsearchOperations.search`.

Trong ví dụ, runtime field được tính cho các document cần thiết để thực hiện điều kiện tìm kiếm. Kết quả có thể được ánh xạ vào property `priceWithTax` đã đánh dấu `@ScriptedField` trong entity.

Nếu dùng implementation Query khác, Spring Data cũng cung cấp `addRuntimeField(runtimeField)` để thêm runtime field vào query.

## 17. Dùng RuntimeField trong Repository method

Spring Data Elasticsearch cũng cho phép truyền runtime field vào repository method:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.RuntimeField;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    SearchHits<Product> findByCategoryAndPriceWithTaxGreaterThanEqual(
        String category,
        Double minimumPrice,
        RuntimeField runtimeField
    );
}
~~~

Khi gọi:

~~~java
SearchHits<Product> hits =
    repository.findByCategoryAndPriceWithTaxGreaterThanEqual(
        "audio",
        1500000.0,
        runtimeField
    );
~~~

Runtime field được thêm vào query method để điều kiện có thể dùng field tính toán.

Cách này hữu ích khi truy vấn phù hợp với query method derivation. Với query nhiều nhánh, nhiều runtime field hoặc cần kiểm soát chi tiết request, dùng custom repository implementation hoặc `ElasticsearchOperations` sẽ rõ ràng hơn.

## 18. Khai báo runtime field trong mapping qua Spring Data

Nếu runtime field được nhiều query sử dụng, có thể định nghĩa trong file JSON nằm trên classpath và gắn vào entity bằng annotation `@Mapping`.

Ví dụ file `runtime-fields.json`:

~~~json
{
  "priceWithTax": {
    "type": "double",
    "script": {
      "source": "emit(doc['price'].value * params.taxRate)",
      "params": {
        "taxRate": 1.1
      }
    }
  }
}
~~~

Entity:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Mapping;

@Document(indexName = "products")
@Mapping(runtimeFieldsPath = "/runtime-fields.json")
public class Product {
    // Các property của entity
}
~~~

`runtimeFieldsPath` trỏ đến tài nguyên JSON trên classpath. Khi Spring Data tạo mapping cho index, định nghĩa runtime field được thêm vào mapping.

Khi đó, các query có thể sử dụng `priceWithTax` mà không cần truyền runtime mapping trong từng request.

Ví dụ:

~~~java
CriteriaQuery query = new CriteriaQuery(
    Criteria.where("priceWithTax").greaterThanEqual(1500000)
);

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

Runtime field được định nghĩa trong mapping có thể dùng lại giữa nhiều request. Cần bảo đảm index đã được tạo với mapping chứa runtime field trước khi thực thi query.

## 19. Khi nào nên dùng scripted field, runtime field hay field thông thường?

Việc chọn cơ chế phụ thuộc vào nơi cần dùng giá trị tính toán và mức độ thường xuyên của phép tính.

| Yêu cầu | Lựa chọn |
|---|---|
| Chỉ hiển thị thêm giá trị cho các hit đã tìm thấy | Scripted field |
| Lọc document theo giá trị tính toán | Runtime field |
| Sort theo giá trị tính toán | Runtime field |
| Aggregation theo giá trị tính toán | Runtime field |
| Dùng một giá trị tính toán trong nhiều query | Runtime field trong mapping |
| Thử nghiệm logic tính toán chỉ trong một request | Runtime field trong `runtime_mappings` |
| Tính toán được dùng thường xuyên và cần hiệu năng cao | Cân nhắc field được tính trước khi index |
| Giá trị là dữ liệu nghiệp vụ ổn định và cần truy vấn thường xuyên | Field thông thường được lưu/index |

Ví dụ với giá sau thuế:

- Nếu giao diện chỉ cần hiển thị giá sau thuế trong trang kết quả: scripted field là đủ.
- Nếu người dùng có bộ lọc giá sau thuế: runtime field.
- Nếu mọi truy vấn, báo cáo và sắp xếp đều cần giá sau thuế: cân nhắc tính giá khi ghi document và lưu thành field thông thường.

Runtime field có thể giúp thử nghiệm schema mà không cần reindex. Nhưng nếu field được dùng liên tục trong filter hoặc sort trên tập dữ liệu lớn, việc tính toán lại ở query time có thể tốn tài nguyên. Khi logic đã ổn định, hãy cân nhắc đưa giá trị vào pipeline ingest hoặc tính trong ứng dụng trước khi index.

## 20. Hiệu năng của Scripted field và Runtime field

Script có thể làm chậm tìm kiếm nếu được chạy trên nhiều document hoặc thực hiện nhiều phép tính.

Scripted field chạy trong fetch phase cho các hit được trả về. Vì vậy, giới hạn page size có thể giúp kiểm soát số lần thực thi script. Tuy nhiên, nếu ứng dụng yêu cầu hàng nghìn hit, script vẫn có thể tốn thời gian.

Runtime field có thể được dùng trong query, filter, sort và aggregation. Khi một điều kiện runtime field phải đánh giá trên rất nhiều document, chi phí có thể lớn hơn nhiều so với chỉ tính giá trị cho các hit cuối cùng.

Một số nguyên tắc:

- Chỉ tạo field tính toán khi ứng dụng thật sự cần.
- Giữ script ngắn và tránh vòng lặp hoặc xử lý dữ liệu lớn.
- Ưu tiên doc values qua `doc['field']`.
- Tránh truy cập `_source` nếu không cần cấu trúc JSON.
- Dùng `params` thay cho nối giá trị vào script source.
- Giới hạn page size khi dùng scripted field.
- Dùng runtime field trong filter chung để giới hạn tập dữ liệu nếu logic cho phép.
- Nếu field được dùng thường xuyên, cân nhắc lưu kết quả ngay khi ingest.
- Theo dõi latency và số lần biên dịch script.
- Kiểm tra lỗi script trên dữ liệu thiếu hoặc không đúng kiểu.

Elasticsearch có script cache để tránh biên dịch lại script giống nhau. Cache chỉ phát huy hiệu quả tốt khi source được giữ ổn định và giá trị thay đổi được truyền qua params.

## 21. Indexed runtime field trong các phiên bản Elasticsearch hỗ trợ

Runtime field thông thường được tính khi query sử dụng nó. Một số phiên bản Elasticsearch mới còn hỗ trợ **indexed runtime field**, tức là chuyển runtime field sang dạng được lập chỉ mục để tăng hiệu năng truy vấn.

Khái niệm này khác với runtime field chỉ tính ở query time:

| Loại | Cách hoạt động |
|---|---|
| Runtime field thông thường | Tính giá trị khi query cần dùng |
| Indexed runtime field | Tính và lập chỉ mục giá trị để phục vụ truy vấn nhanh hơn |

Indexed runtime field phù hợp khi logic tính toán đã ổn định và giá trị được dùng thường xuyên. Elasticsearch có thể tận dụng giá trị đã index thay vì chạy script cho mọi truy vấn.

Có một ràng buộc quan trọng: sau khi runtime field đã được index theo cơ chế này, không thể cập nhật script của field đó như một runtime field thông thường. Nếu cần thay đổi logic, phải tạo field mới với script mới và thực hiện quy trình index dữ liệu phù hợp.

Khả năng này phụ thuộc phiên bản Elasticsearch. Hãy kiểm tra tài liệu của phiên bản cluster trước khi thiết kế mapping. Không nên giả định mọi cluster hỗ trợ indexed runtime field.

## 22. Lỗi thường gặp

**Dùng scripted field để lọc document.** Scripted field chỉ chạy sau khi query đã chọn hit. Dùng runtime field nếu giá trị cần tham gia điều kiện tìm kiếm.

**Quên emit trong runtime field.** Runtime field cần gọi `emit(value)` để trả giá trị. Script chỉ có `return` không đáp ứng yêu cầu này.

**Dùng emit trong scripted field.** Scripted field sử dụng field context và trả kết quả bằng biểu thức hoặc `return`; `emit` là cơ chế của runtime field.

**Không kiểm tra field thiếu.** Truy cập `.value` khi field không có trong mapping hoặc document có thể gây lỗi. Kiểm tra `doc.containsKey` và `doc['field'].size()`.

**Gọi emit với null.** `emit` không nhận null. Nếu không có giá trị hợp lệ, hãy bỏ qua việc emit.

**Nhầm field tính toán với field trong _source.** Scripted field và runtime field không tự ghi kết quả vào `_source`. Giá trị được trả qua `fields` hoặc được dùng trong query.

**Quên lấy runtime field trong response.** Khi cần đọc giá trị tính toán, hãy yêu cầu field qua `fields` hoặc `withFields(...)` phù hợp.

**Không lấy lại source thông thường trong Spring Data.** Khi thêm scripted field hoặc runtime field, cấu hình source filter thích hợp để các property gốc của entity vẫn được lấy về.

**Thay đổi script source cho mỗi request.** Điều này có thể làm tăng số lần biên dịch. Dùng params để giữ source ổn định.

**Dùng _source cho mọi phép tính.** Truy cập `_source` thường chậm hơn doc values. Chỉ dùng khi cần dữ liệu cấu trúc hoặc field không có doc values.

**Dùng runtime field cho giá trị được truy vấn liên tục mà không đánh giá hiệu năng.** Nếu field được dùng thường xuyên trong query hoặc sort, cân nhắc index giá trị tính toán hoặc dùng indexed runtime field khi phiên bản hỗ trợ.

**Nhầm hai ScriptedField trong Spring Data.** Annotation `@ScriptedField` ở package `annotations` dùng cho property entity; class `ScriptedField` ở package `core.query` dùng để tạo query. Hai kiểu có cùng tên đơn giản nhưng vai trò khác nhau.

**Khai báo runtimeFieldsPath sai.** File JSON phải nằm trên classpath và đúng định dạng runtime mapping. Nếu file không được tìm thấy hoặc JSON sai, quá trình tạo mapping có thể thất bại.

## 23. Quy trình triển khai trong dự án

Có thể thực hiện theo trình tự sau:

1. Xác định giá trị tính toán chỉ cần hiển thị hay cần dùng trong query.
2. Nếu chỉ hiển thị trên hit, chọn scripted field.
3. Nếu cần filter, sort hoặc aggregation, chọn runtime field.
4. Xác định kiểu dữ liệu runtime field và các field đầu vào.
5. Kiểm tra mapping để chắc chắn các field đầu vào có kiểu phù hợp.
6. Viết Painless script và kiểm tra trường hợp field thiếu hoặc null.
7. Đưa giá trị thay đổi vào params, không nối trực tiếp vào source.
8. Thử script bằng request Elasticsearch với dữ liệu đại diện.
9. Tích hợp bằng `ScriptedField`, `RuntimeField`, `CriteriaQuery` hoặc repository method.
10. Nếu runtime field được dùng ở nhiều nơi, cân nhắc khai báo trong mapping bằng `@Mapping(runtimeFieldsPath = ...)`.
11. Yêu cầu trả field tính toán trong response nếu ứng dụng cần hiển thị nó.
12. Đo hiệu năng trên tập dữ liệu gần production.
13. Nếu logic được dùng thường xuyên, đánh giá việc tính trước và lưu field vào index.

## Kết luận

Scripted field và runtime field đều cho phép tạo giá trị từ dữ liệu đã lưu mà không phải ghi thêm giá trị đó vào `_source`. Tuy nhiên, chúng phục vụ hai mục đích khác nhau. Scripted field (`script_fields`) chỉ bổ sung giá trị cho những hit đã được query chọn. Runtime field có thể tham gia filter, query, sort và aggregation.

Trong Painless, scripted field trả kết quả bằng giá trị trả về của script, còn runtime field phải dùng `emit(...)`. Có thể khai báo runtime field ngay trong `runtime_mappings` của một search request hoặc định nghĩa lâu dài trong mapping của index.

Spring Data Elasticsearch hỗ trợ scripted field qua class `ScriptedField`, `ScriptData` và annotation `@ScriptedField`. Runtime field được biểu diễn bằng `RuntimeField`, có thể thêm vào `Query` hoặc khai báo qua `@Mapping(runtimeFieldsPath = ...)`. Khi chọn cơ chế, hãy cân nhắc nơi cần dùng giá trị tính toán, tần suất truy vấn và chi phí thực thi. Với field được sử dụng thường xuyên, tính trước và lưu vào index thường là hướng phù hợp hơn.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Scripted and runtime fields](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/scripted-and-runtime-fields.html)
- [Spring Data Elasticsearch — Miscellaneous operations and runtime fields](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html)
- [Spring Data Elasticsearch — ScriptedField annotation API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/ScriptedField.html)
- [Spring Data Elasticsearch — ScriptedField query API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/ScriptedField.html)
- [Spring Data Elasticsearch — ScriptData API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/ScriptData.html)
- [Spring Data Elasticsearch — RuntimeField API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/RuntimeField.html)
- [Elasticsearch — Use Painless scripts in runtime fields](https://www.elastic.co/docs/reference/scripting-languages/painless/use-painless-scripts-in-runtime-fields)
- [Elasticsearch — Map a runtime field](https://www.elastic.co/docs/manage-data/data-store/mapping/map-runtime-field)
- [Elasticsearch — Field context for script fields](https://www.elastic.co/docs/reference/scripting-languages/painless/painless-field-context)
- [Elasticsearch — Accessing document fields and special variables](https://www.elastic.co/docs/explore-analyze/scripting/modules-scripting-fields)
- [Elasticsearch — Scripts, caching, and search speed](https://www.elastic.co/docs/explore-analyze/scripting/scripts-search-speed)
- [Elasticsearch — Use parameters in your script](https://www.elastic.co/docs/explore-analyze/scripting/modules-scripting-use-parameters)
