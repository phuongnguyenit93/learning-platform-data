# Boolean, binary, IP và các kiểu chuyên biệt

Elasticsearch cung cấp nhiều kiểu field ngoài các kiểu văn bản và số cơ bản. Những kiểu như `boolean`, `binary`, `ip`, `geo_point`, `geo_shape`, `completion`, `flattened` hoặc vector giúp mô hình hóa dữ liệu theo đúng cách hệ thống cần lưu trữ và truy vấn.

Trong Spring Data Elasticsearch, mapping của field thường được khai báo bằng `@Field` trên property Java. Annotation này mô tả kiểu Elasticsearch và một số thuộc tính lập chỉ mục; Spring Data sử dụng metadata đó khi tạo mapping và chuyển đổi document. Tuy nhiên, kiểu Java và kiểu Elasticsearch không phải lúc nào cũng tương ứng một-một. Cần chọn kiểu dựa trên cách dữ liệu được tìm kiếm, lọc, sắp xếp hoặc sử dụng trong ứng dụng.

```text
Java model                         Elasticsearch mapping
----------                         ----------------------
Boolean / boolean       ------->   boolean
String chứa Base64      ------->   binary
String chứa địa chỉ IP  ------->   ip
GeoPoint                ------->   geo_point
Shape                   ------->   geo_shape
String / object         ------->   completion / flattened / ...
```

Các kiểu chuyên biệt và thuộc tính mapping có thể thay đổi theo phiên bản Elasticsearch và Spring Data Elasticsearch. Khi sử dụng kiểu mới, hãy đối chiếu phiên bản server, Java client và Spring Data mà ứng dụng đang quản lý.

## 1. Boolean: dữ liệu đúng hoặc sai

Kiểu `boolean` lưu trạng thái có hai giá trị logic: `true` hoặc `false`. Đây là kiểu phù hợp cho các thuộc tính như tài khoản đang hoạt động, sản phẩm được bật bán, đơn hàng đã xác nhận hoặc thiết bị đang kết nối.

Ví dụ entity:

```java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(name = "is_active", type = FieldType.Boolean)
    private Boolean active;
}
```

Mapping tương ứng ở Elasticsearch:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "is_active": {
        "type": "boolean"
      }
    }
  }
}
```

Document:

```json
{
  "is_active": true
}
```

### Truy vấn boolean

Có thể dùng `term` query để tìm chính xác các document có giá trị `true`:

```json
GET /products/_search
{
  "query": {
    "term": {
      "is_active": true
    }
  }
}
```

Trong Spring Data, repository có thể khai báo query method theo property Java:

```java
List<ProductDocument> findByActiveTrue();

List<ProductDocument> findByActiveFalse();
```

Tên method tham chiếu property `active`; mapping metadata chuyển property đó thành field `is_active` khi Spring Data xây dựng truy vấn.

### Boolean khác null

Trong Java, `boolean` là kiểu primitive chỉ có `true` hoặc `false`; `Boolean` là kiểu wrapper và có thể nhận thêm `null`. Sự khác nhau này quan trọng khi dữ liệu có thể thiếu field hoặc chưa được xác định.

| Giá trị trong document | Ý nghĩa có thể dùng trong nghiệp vụ |
|---|---|
| `true` | Đã bật / đúng / được xác nhận. |
| `false` | Đã tắt / sai / bị từ chối. |
| Không có field | Chưa biết, chưa được ghi nhận hoặc dữ liệu cũ chưa có thuộc tính. |

Elasticsearch không tự biến field bị thiếu thành `false`. Nếu nghiệp vụ coi thiếu field là `false`, ứng dụng cần chuẩn hóa dữ liệu hoặc dùng truy vấn có xử lý rõ trường hợp missing. Không nên nhập nhằng giữa `false` và `null` nếu chúng có ý nghĩa khác nhau.

## 2. Binary: lưu dữ liệu nhị phân dạng Base64

Kiểu `binary` dùng cho dữ liệu nhị phân được biểu diễn bằng chuỗi Base64 trong JSON. Một số trường hợp sử dụng có thể là nội dung nhị phân nhỏ, chữ ký hoặc payload được nhúng trong document.

Mapping:

```json
PUT /attachments
{
  "mappings": {
    "properties": {
      "file_name": {
        "type": "keyword"
      },
      "content_base64": {
        "type": "binary"
      }
    }
  }
}
```

Document có thể chứa chuỗi Base64:

```json
{
  "file_name": "sample.bin",
  "content_base64": "SGVsbG8gRWxhc3RpY3NlYXJjaA=="
}
```

Giá trị trên là dữ liệu đã mã hóa Base64. Khi gửi JSON, client truyền chuỗi Base64; Elasticsearch giải mã biểu diễn đó để lưu nội dung binary theo mapping.

### Binary có tìm kiếm được không?

Field `binary` không được thiết kế để full-text search hoặc lọc theo nội dung byte. Nó không được lập chỉ mục như `text`/`keyword`, và không cung cấp doc values để sort/aggregation thông thường. Nếu cần tìm kiếm metadata của file, hãy lưu metadata thành field riêng:

```json
{
  "file_name": "report.pdf",
  "content_type": "application/pdf",
  "size_bytes": 125000,
  "content_base64": "..."
}
```

Ứng dụng có thể lọc theo `file_name`, `content_type` hoặc `size_bytes`; `content_base64` chỉ giữ nội dung nhị phân.

Trong Spring Data, có thể khai báo field với `FieldType.Binary`:

```java
@Field(name = "content_base64", type = FieldType.Binary)
private String contentBase64;
```

Ở ví dụ này, property Java giữ chuỗi Base64. Nếu muốn dùng `byte[]`, cần bảo đảm converter/serializer của ứng dụng chuyển đổi byte array sang biểu diễn Base64 đúng với mapping binary của Elasticsearch. Hãy kiểm tra document thực tế trong `_source` và thử đọc lại trong integration test; không giả định mọi serializer đều xử lý byte array giống nhau.

Binary trong Elasticsearch không thay thế object storage hoặc hệ thống quản lý file. Với file lớn, thường nên lưu nội dung trong object storage hoặc file service, còn Elasticsearch chỉ lưu URL/key, tên file, loại MIME, kích thước, checksum và các metadata phục vụ tìm kiếm. Việc nhúng binary làm document lớn hơn, tăng chi phí mạng, lưu trữ, snapshot và reindex.

## 3. IP: địa chỉ IPv4 và IPv6

Kiểu `ip` lưu địa chỉ IPv4 hoặc IPv6. Nó phù hợp cho địa chỉ client, địa chỉ máy chủ, thiết bị mạng hoặc thông tin nguồn của request.

Entity:

```java
@Document(indexName = "access-logs")
public class AccessLogDocument {

    @Id
    private String id;

    @Field(name = "client_ip", type = FieldType.Ip)
    private String clientIp;

    @Field(name = "request_path", type = FieldType.Keyword)
    private String requestPath;
}
```

Mapping:

```json
PUT /access-logs
{
  "mappings": {
    "properties": {
      "client_ip": {
        "type": "ip"
      },
      "request_path": {
        "type": "keyword"
      }
    }
  }
}
```

Document có thể dùng IPv4 hoặc IPv6:

```json
POST /access-logs/_doc
{
  "client_ip": "192.0.2.10",
  "request_path": "/api/products"
}
```

```json
POST /access-logs/_doc
{
  "client_ip": "2001:db8::1",
  "request_path": "/api/orders"
}
```

### Truy vấn IP

Có thể lọc một địa chỉ cụ thể bằng `term`:

```json
GET /access-logs/_search
{
  "query": {
    "term": {
      "client_ip": "192.0.2.10"
    }
  }
}
```

Có thể tìm địa chỉ nằm trong một CIDR bằng range query:

```json
GET /access-logs/_search
{
  "query": {
    "range": {
      "client_ip": {
        "gte": "192.0.2.0",
        "lte": "192.0.2.255"
      }
    }
  }
}
```

Tùy nhu cầu, có thể sử dụng cú pháp CIDR được hỗ trợ trong truy vấn IP để lọc một subnet, ví dụ `192.0.2.0/24`. Cần kiểm tra cú pháp cụ thể của query được dùng và phiên bản Elasticsearch.

### `ip` khác `ip_range`

`ip` lưu một địa chỉ IP đơn lẻ. `ip_range` lưu một khoảng địa chỉ, chẳng hạn một dải mạng hoặc CIDR. Hai kiểu này phục vụ mô hình dữ liệu khác nhau:

| Kiểu | Dữ liệu | Ví dụ |
|---|---|---|
| `ip` | Một địa chỉ | `192.0.2.10` |
| `ip_range` | Một khoảng địa chỉ | `192.0.2.0` đến `192.0.2.255` |

Nếu document đại diện cho một thiết bị hoặc một request, thường dùng `ip`. Nếu document đại diện cho một subnet hoặc dải được cấp phát, có thể cân nhắc `ip_range`.

Không nên dùng `keyword` cho IP chỉ vì dữ liệu đầu vào là chuỗi. Kiểu `ip` cung cấp cách lưu trữ và truy vấn phù hợp với ngữ nghĩa địa chỉ mạng, bao gồm kiểm tra theo dải.

## 4. Geo-point: vị trí địa lý dạng điểm

`geo_point` biểu diễn một vị trí bằng kinh độ và vĩ độ. Đây là kiểu thường dùng cho cửa hàng, địa chỉ giao hàng, thiết bị GPS hoặc vị trí phát sinh sự kiện.

Mapping:

```json
PUT /stores
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
```

Một document có thể truyền tọa độ dưới dạng object:

```json
POST /stores/_doc/store-1
{
  "name": "Central Store",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
```

Elasticsearch cũng hỗ trợ một số dạng biểu diễn khác như chuỗi `"lat,lon"` hoặc mảng `[lon, lat]`. Cần chú ý thứ tự tọa độ: dạng mảng GeoJSON sử dụng kinh độ trước, vĩ độ sau.

Trong Spring Data Elasticsearch, có thể sử dụng kiểu `GeoPoint` của Spring Data và mapping geo point tương ứng:

```java
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Field(name = "location", type = FieldType.Geo_Point)
private GeoPoint location;
```

Khi chuyển đổi giữa Java và Elasticsearch, hãy giữ nhất quán quy ước latitude/longitude. Đảo thứ tự có thể tạo vị trí sai dù giá trị vẫn hợp lệ về mặt số học.

### Tìm kiếm theo khoảng cách

`geo_distance` query tìm các document có điểm nằm trong bán kính quanh một vị trí:

```json
GET /stores/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  }
}
```

Có thể kết hợp với `sort` theo khoảng cách để đưa địa điểm gần nhất lên trước. `geo_point` phù hợp khi mỗi document chỉ cần một điểm đại diện. Nếu cần mô hình hóa ranh giới hoặc vùng, hãy xem `geo_shape`.

## 5. Geo-shape: vùng và hình học địa lý

`geo_shape` dùng để lưu các hình học như điểm, đường, đa giác hoặc tập hợp hình học. Nó phù hợp khi cần biểu diễn ranh giới khu vực giao hàng, vùng phủ sóng, khu vực hành chính hoặc vùng cấm.

Ví dụ mapping:

```json
PUT /delivery-zones
{
  "mappings": {
    "properties": {
      "zone_name": {
        "type": "keyword"
      },
      "boundary": {
        "type": "geo_shape"
      }
    }
  }
}
```

Document polygon theo GeoJSON:

```json
POST /delivery-zones/_doc/zone-1
{
  "zone_name": "Zone A",
  "boundary": {
    "type": "polygon",
    "coordinates": [
      [
        [106.69, 10.77],
        [106.72, 10.77],
        [106.72, 10.79],
        [106.69, 10.79],
        [106.69, 10.77]
      ]
    ]
  }
}
```

Với polygon, vòng tọa độ phải đóng bằng cách lặp lại điểm đầu ở cuối. Thứ tự tọa độ GeoJSON là `[longitude, latitude]`.

Có thể dùng `geo_shape` query với các quan hệ như `intersects`, `within`, `contains` hoặc `disjoint` tùy loại truy vấn và phiên bản. Ví dụ tìm các vùng giao với một hình học đầu vào:

```json
GET /delivery-zones/_search
{
  "query": {
    "geo_shape": {
      "boundary": {
        "shape": {
          "type": "point",
          "coordinates": [106.7009, 10.7769]
        },
        "relation": "intersects"
      }
    }
  }
}
```

`geo_shape` mạnh hơn `geo_point` về khả năng mô hình hóa, nhưng cũng làm mapping và truy vấn phức tạp hơn. Nếu chỉ cần tìm cửa hàng trong bán kính quanh người dùng, `geo_point` thường là lựa chọn đơn giản hơn.

## 6. Completion: gợi ý khi người dùng nhập

Kiểu `completion` được tối ưu cho chức năng autocomplete/suggest. Ví dụ khi người dùng nhập `spr`, hệ thống có thể gợi ý `Spring Data Elasticsearch`, `Spring Boot` hoặc `Spring Framework`.

Mapping:

```json
PUT /suggestions
{
  "mappings": {
    "properties": {
      "title": {
        "type": "completion"
      }
    }
  }
}
```

Document:

```json
POST /suggestions/_doc/1
{
  "title": {
    "input": [
      "Spring Data Elasticsearch",
      "Spring Elasticsearch"
    ],
    "weight": 10
  }
}
```

Gửi suggest request:

```json
GET /suggestions/_search
{
  "suggest": {
    "title-suggest": {
      "prefix": "spr",
      "completion": {
        "field": "title"
      }
    }
  }
}
```

Completion suggester dùng cấu trúc dữ liệu chuyên biệt để trả gợi ý nhanh. Nó phù hợp với danh sách gợi ý được chuẩn bị trước, ví dụ tên sản phẩm, tên địa điểm hoặc từ khóa. Nếu cần full-text search có phân tích token, điều kiện lọc phức tạp hoặc tìm kiếm theo nội dung dài, `text` kết hợp query phù hợp có thể thích hợp hơn.

Spring Data Elasticsearch có hỗ trợ mapping cho completion field ở các phiên bản tương ứng. Khi dùng annotation chuyên biệt hoặc kiểu Java đại diện cho completion input, hãy kiểm tra API đúng phiên bản thay vì giả định mọi property `String` được tự chuyển thành cấu trúc `input`/`weight`.

## 7. Flattened: object có nhiều key động

Thông thường, Elasticsearch tạo mapping riêng cho các field con của một object. Nếu mỗi document chứa rất nhiều key động, mapping có thể tăng nhanh và gặp giới hạn số field.

Kiểu `flattened` lưu các key và value của object dưới dạng một field tổng hợp, giúp hạn chế bùng nổ mapping. Nó phù hợp với metadata có cấu trúc key-value linh hoạt, chẳng hạn thuộc tính mở rộng do nhiều nguồn gửi đến.

Mapping:

```json
PUT /events
{
  "mappings": {
    "properties": {
      "event_id": {
        "type": "keyword"
      },
      "metadata": {
        "type": "flattened"
      }
    }
  }
}
```

Document:

```json
POST /events/_doc/1
{
  "event_id": "EVT-001",
  "metadata": {
    "source": "mobile",
    "region": "south",
    "campaign": "summer-2026"
  }
}
```

Có thể truy vấn key con bằng đường dẫn field:

```json
GET /events/_search
{
  "query": {
    "term": {
      "metadata.region": "south"
    }
  }
}
```

Flattened giúp quản lý object có key không cố định, nhưng không thay thế object mapping thông thường trong mọi trường hợp. Các value được xử lý theo ngữ nghĩa keyword đơn giản; khả năng truy vấn số, range, full-text và aggregation không tương đương với việc mỗi field con có mapping kiểu riêng. Nếu cần phân tích nội dung, tính toán số hoặc truy vấn theo kiểu dữ liệu chuyên biệt, hãy khai báo field rõ ràng.

## 8. Range fields: lưu một khoảng giá trị

Elasticsearch có các kiểu range để lưu một khoảng thay vì một giá trị đơn lẻ, ví dụ `integer_range`, `long_range`, `float_range`, `double_range`, `date_range` và `ip_range`.

Ví dụ một chương trình khuyến mãi có hiệu lực trong một khoảng ngày:

```json
PUT /promotions
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "valid_period": {
        "type": "date_range"
      }
    }
  }
}
```

Document:

```json
POST /promotions/_doc/promo-1
{
  "name": "Summer sale",
  "valid_period": {
    "gte": "2026-06-01",
    "lt": "2026-09-01"
  }
}
```

Range query có thể kiểm tra khoảng đã lưu có giao với một khoảng tìm kiếm hay không:

```json
GET /promotions/_search
{
  "query": {
    "range": {
      "valid_period": {
        "gte": "2026-07-01",
        "lt": "2026-08-01",
        "relation": "INTERSECTS"
      }
    }
  }
}
```

Các quan hệ range thường gồm `INTERSECTS`, `CONTAINS` và `WITHIN`. Cần chọn đúng quan hệ theo câu hỏi nghiệp vụ: chương trình có hiệu lực trong bất kỳ phần nào của tháng, bao trọn tháng hay nằm hoàn toàn trong tháng.

Range field không giống hai field `start_date` và `end_date` độc lập. Nó biểu diễn khoảng như một giá trị có cấu trúc và cho phép truy vấn theo quan hệ giữa các khoảng.

## 9. Vector và các kiểu chuyên biệt khác

Elasticsearch có các kiểu phục vụ tìm kiếm ngữ nghĩa và xếp hạng, ví dụ `dense_vector`, `sparse_vector`, `rank_feature` và `rank_features`. Khả năng cụ thể phụ thuộc phiên bản Elasticsearch, license/tính năng triển khai và cấu hình index.

### Dense vector

`dense_vector` lưu một vector số có số chiều xác định. Vector thường được tạo bởi mô hình embedding bên ngoài hoặc dịch vụ AI, sau đó dùng để tìm các document có nội dung gần nghĩa với câu truy vấn.

Mapping minh họa:

```json
PUT /knowledge
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 3,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
```

Document minh họa:

```json
POST /knowledge/_doc/1
{
  "title": "Spring Data Elasticsearch",
  "embedding": [0.12, -0.08, 0.91]
}
```

Vector ba chiều ở ví dụ chỉ để minh họa cấu trúc. Trong ứng dụng thật, số chiều phải khớp chính xác với model embedding đã chọn. Khi thay model có số chiều hoặc không gian vector khác, cần thiết kế lại mapping và tạo lại embedding phù hợp.

### Rank feature

`rank_feature` và `rank_features` lưu tín hiệu số dùng trong việc xếp hạng kết quả, chẳng hạn độ phổ biến, mức độ uy tín hoặc các chỉ số liên quan. Chúng hỗ trợ query chuyên biệt để kết hợp tín hiệu này vào relevance score. Không nên dùng chúng thay cho các field số thông thường nếu ứng dụng cần tính toán, range query hoặc aggregation như dữ liệu số phổ thông.

Các kiểu vector và ranking cần được chọn theo tính năng truy vấn cụ thể. Trước khi thiết kế, kiểm tra tài liệu của đúng phiên bản server vì tên tham số, khả năng index và các thuật toán tìm kiếm vector có thể thay đổi giữa các bản phát hành.

## 10. Chọn kiểu field theo nhu cầu

| Nhu cầu dữ liệu | Kiểu Elasticsearch nên xem xét | Ghi chú |
|---|---|---|
| Cờ bật/tắt, trạng thái đúng/sai | `boolean` | Phân biệt `false` với field bị thiếu. |
| Nội dung nhị phân Base64 nhỏ | `binary` | Không dùng để tìm kiếm nội dung byte; cân nhắc object storage cho file lớn. |
| Địa chỉ IPv4/IPv6 đơn lẻ | `ip` | Hỗ trợ truy vấn theo địa chỉ và dải IP. |
| Một vị trí GPS | `geo_point` | Dùng cho tìm kiếm theo khoảng cách và vị trí. |
| Đường, polygon hoặc vùng địa lý | `geo_shape` | Dùng cho quan hệ hình học như intersects/within. |
| Gợi ý khi nhập tiền tố | `completion` | Tối ưu cho danh sách autocomplete được chuẩn bị trước. |
| Object có nhiều key động | `flattened` | Hạn chế mapping explosion, đổi lại kiểu dữ liệu con ít chuyên biệt hơn. |
| Khoảng số, ngày hoặc IP | Các kiểu `*_range` | Truy vấn quan hệ giữa các khoảng. |
| Embedding hoặc tìm kiếm vector | `dense_vector` / `sparse_vector` | Số chiều và tính năng phải tương thích model/server. |
| Tín hiệu xếp hạng | `rank_feature` / `rank_features` | Dùng trong query scoring chuyên biệt. |

Không nên chọn kiểu chuyên biệt chỉ vì Elasticsearch hỗ trợ nó. Hãy bắt đầu từ câu hỏi mà ứng dụng cần trả lời, sau đó chọn mapping có ngữ nghĩa phù hợp. Ví dụ, nếu chỉ cần lưu latitude/longitude và tìm cửa hàng trong bán kính, `geo_point` đơn giản hơn `geo_shape`; nếu cần tìm kiếm tên người dùng theo nội dung, `text` phù hợp hơn `completion`.

## 11. Áp dụng trong Spring Data Elasticsearch

Spring Data cung cấp annotation để khai báo mapping trên entity. Với những kiểu thông dụng, có thể mô tả trực tiếp bằng `@Field`:

```java
@Document(indexName = "network-devices")
public class NetworkDeviceDocument {

    @Id
    private String id;

    @Field(name = "enabled", type = FieldType.Boolean)
    private Boolean enabled;

    @Field(name = "management_ip", type = FieldType.Ip)
    private String managementIp;

    @Field(name = "configuration_base64", type = FieldType.Binary)
    private String configurationBase64;
}
```

Các kiểu cần biểu diễn phức tạp hơn có thể dùng `@Field` với type tương ứng, annotation chuyên biệt của Spring Data (nếu phiên bản cung cấp), hoặc khai báo mapping JSON khi tạo index. Ví dụ `geo_point` có thể ánh xạ với `GeoPoint`; completion và vector cần cấu trúc Java phù hợp với contract của client/converter.

Đối với mapping do ứng dụng quản lý, có thể dùng `IndexOperations` để kiểm tra hoặc tạo index theo mapping đã chuẩn bị. Cần bảo đảm index thực tế được tạo với mapping mong muốn trước khi ghi dữ liệu. Việc chỉ thêm annotation vào entity không đảm bảo index đang tồn tại tự đổi kiểu field.

Ví dụ đọc mapping từ Elasticsearch:

```http
GET /network-devices/_mapping
```

Khi một field đã được tạo với kiểu không phù hợp, thường cần tạo index mới và reindex dữ liệu thay vì cố đổi trực tiếp kiểu field tại chỗ. Hãy kiểm tra khả năng tương thích của mapping với phiên bản Spring Data và server trước khi triển khai.

## 12. Kiểm tra dữ liệu và các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ghi Boolean bị lỗi parse | Gửi chuỗi không phải biểu diễn boolean hợp lệ hoặc kiểu Java không khớp. | Kiểm tra JSON thực tế và mapping `boolean`. |
| Binary không được tìm thấy bằng query | Binary field không được lập chỉ mục để tìm kiếm nội dung. | Tìm theo metadata riêng như tên, MIME type hoặc checksum. |
| IP bị từ chối | Giá trị không phải IPv4/IPv6 hợp lệ hoặc field đang có mapping khác. | Kiểm tra dữ liệu đầu vào và mapping `ip`. |
| Geo query không trả kết quả | Đảo latitude/longitude, sai cấu trúc GeoJSON hoặc dùng sai kiểu field. | Kiểm tra thứ tự `[lon, lat]` và mapping geo. |
| Completion không có gợi ý | Field chưa được map `completion`, request dùng sai field hoặc dữ liệu chưa có input phù hợp. | Kiểm tra mapping, document và suggest request. |
| Object động tạo quá nhiều field | Mỗi key được map thành field riêng. | Xem xét `flattened` nếu không cần kiểu mapping riêng cho từng key. |
| Vector query báo sai dimension | Vector ghi vào có số phần tử khác `dims` trong mapping. | Đồng bộ model embedding và mapping; tạo lại vector nếu đổi model. |
| Thay annotation nhưng lỗi mapping conflict | Index hiện tại đã có field với kiểu cũ. | Tạo index mới, reindex và chuyển alias theo kế hoạch. |

Khi điều tra, nên kiểm tra cả ba phần: entity Java, mapping hiện tại và document trong `_source`. Nếu query không hoạt động, kiểm tra thêm loại query, analyzer hoặc tính năng chuyên biệt của field.

## 13. Những điểm cần nhớ

- `boolean` lưu `true`/`false`; field bị thiếu vẫn khác với giá trị `false`.
- `binary` nhận dữ liệu nhị phân dưới dạng Base64 và không phù hợp để tìm kiếm nội dung byte.
- `ip` dành cho địa chỉ IPv4/IPv6; `ip_range` dành cho khoảng địa chỉ.
- `geo_point` biểu diễn một điểm; `geo_shape` biểu diễn hình học như đường hoặc polygon.
- `completion` phục vụ autocomplete; `flattened` phù hợp với object có nhiều key động.
- Các kiểu `*_range`, vector và rank feature giải quyết những nhu cầu truy vấn chuyên biệt.
- Spring Data có thể khai báo mapping qua `@Field` và các annotation hỗ trợ; với kiểu phức tạp cần kiểm tra converter và khả năng của phiên bản đang dùng.
- Mapping của index đã tồn tại không tự thay đổi chỉ vì entity được sửa; thay đổi kiểu field thường cần migration/reindex.

Chọn đúng kiểu field giúp Elasticsearch lưu trữ và truy vấn dữ liệu theo đúng ngữ nghĩa. Với Spring Data Elasticsearch, hãy kết hợp annotation rõ ràng, mapping thực tế có thể kiểm tra được và integration test để bảo đảm Java model, document JSON và truy vấn luôn nhất quán.
