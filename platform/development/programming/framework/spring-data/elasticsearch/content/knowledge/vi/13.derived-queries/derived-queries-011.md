# Giới hạn biểu diễn nested, geo-shape và điều kiện phức tạp

Spring Data Elasticsearch hỗ trợ nhiều cách khai báo truy vấn. Với các điều kiện đơn giản, derived query từ tên phương thức thường dễ đọc và đủ dùng. Khi yêu cầu tìm kiếm có nhiều tầng `bool`, điều kiện phải khớp trên cùng một phần tử `nested`, truy vấn hình học `geo_shape`, aggregation hoặc các nhánh điều kiện động, tên phương thức và query annotation có thể trở nên khó diễn đạt.

Giới hạn ở đây không có nghĩa Elasticsearch không hỗ trợ những truy vấn đó. Elasticsearch Query DSL có thể biểu diễn các cấu trúc rất phong phú. Vấn đề là chọn abstraction của Spring Data phù hợp với độ phức tạp của query:

- **Derived query**: phù hợp với điều kiện đơn giản có thể suy ra từ tên method.
- **`@Query`**: phù hợp với Query DSL JSON tường minh, tương đối ổn định và có thể tham số hóa.
- **`NativeQuery` / `ElasticsearchOperations`**: phù hợp với query động, nested, geo-shape và cấu trúc DSL phức tạp cần xây dựng bằng code.
- **Elasticsearch Java Client trực tiếp**: phù hợp khi cần kiểm soát request/response hoặc tính năng mà abstraction Spring Data hiện tại chưa biểu diễn thuận tiện.

Mục tiêu là giữ ý nghĩa của truy vấn rõ ràng, đặc biệt là phạm vi của điều kiện nested và semantics hình học của geo-shape.

## 1. Ba mức biểu diễn truy vấn trong Spring Data Elasticsearch

### 1.1 Derived query từ tên phương thức

Spring Data có thể phân tích tên phương thức repository để tạo query. Ví dụ:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByActiveTrue();

    List<Product> findByPriceBetween(Double min, Double max);

    List<Product> findByCategoryAndActiveTrue(String category);
}
```

Các method này dễ hiểu vì mỗi method mô tả một điều kiện đơn giản. Tuy nhiên, derived query chỉ hỗ trợ tập từ khóa và cách phân tích tên được Spring Data định nghĩa. Nó không phải ngôn ngữ tổng quát để biểu diễn mọi cấu trúc Query DSL.

Khi truy vấn cần một nested query chứa nhiều điều kiện cùng phạm vi, một geo-shape relation, nhiều nhánh `should`, `minimum_should_match`, `inner_hits` hoặc query lồng nhiều tầng, việc cố nhồi tất cả vào tên method sẽ làm tên dài, khó đọc và có thể không biểu đạt đúng semantics.

Ví dụ tên method như:

```java
findByVariantsColorAndVariantsSizeAndVariantsAvailableTrue(...)
```

không tự bảo đảm rằng các điều kiện màu, size và available được đánh giá trên cùng một phần tử trong mảng `variants`. Nếu field là `nested`, cần một nested query với phạm vi rõ ràng. Tên method không thể thay thế việc thiết kế nested Query DSL đúng.

### 1.2 `@Query` với Elasticsearch Query DSL JSON

`@Query` cho phép khai báo query JSON ngay trên repository method. Cách này hữu ích khi query có cấu trúc tĩnh, dễ đọc dưới dạng JSON và chỉ cần thay một vài tham số.

Ví dụ query nested:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "nested": {
            "path": "variants",
            "query": {
              "bool": {
                "filter": [
                  { "term": { "variants.color": "?0" } },
                  { "term": { "variants.size": "?1" } },
                  { "term": { "variants.available": true } }
                ]
              }
            }
          }
        }
        """)
    List<Product> findProductsWithAvailableVariant(String color, String size);
}
```

Hai placeholder `?0` và `?1` tham chiếu tham số thứ nhất và thứ hai. Cả ba điều kiện nằm trong cùng một nested query, nên phải khớp trên cùng một nested document thuộc `variants`.

`@Query` giúp tránh tên method quá dài và thể hiện trực tiếp DSL. Tuy nhiên, query được viết dưới dạng chuỗi. Khi có nhiều nhánh tùy chọn, nhiều shape khác nhau hoặc logic phụ thuộc input, việc ghép JSON string có thể khó bảo trì. Cần tránh tự nối chuỗi đầu vào người dùng vào JSON; sử dụng cơ chế binding được Spring Data hỗ trợ và kiểm tra query được sinh ra.

### 1.3 `NativeQuery` và `ElasticsearchOperations`

Khi query cần được xây dựng động, `NativeQuery` kết hợp với `ElasticsearchOperations` thường phù hợp hơn. Có thể thêm hoặc bỏ điều kiện theo input, dựng các nhánh `bool`, khai báo nested query, sort, aggregation và các tùy chọn search mà không phải tạo tên method hoặc nối JSON thủ công.

Ví dụ cấu trúc service:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(Query query) {
        return operations.search(query, Product.class);
    }
}
```

`Query` có thể là `NativeQuery` được tạo từ builder của Elasticsearch Java Client. API builder cụ thể phụ thuộc phiên bản Spring Data Elasticsearch và Elasticsearch Java Client mà dự án sử dụng. Với query đơn giản, repository vẫn tiện lợi; với query động hoặc cần giữ chính xác cấu trúc DSL, xây dựng `NativeQuery` trong một lớp chuyên trách giúp logic rõ ràng hơn.

## 2. Nested query: phạm vi của điều kiện quan trọng hơn tên method

Giả sử một sản phẩm có nhiều biến thể:

```json
{
  "name": "Áo khoác",
  "variants": [
    { "color": "red", "size": "XL", "available": true },
    { "color": "blue", "size": "M", "available": true }
  ]
}
```

Field `variants` cần được mapping là `nested` nếu truy vấn phải bảo toàn quan hệ giữa các thuộc tính của từng phần tử:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "variants": {
        "type": "nested",
        "properties": {
          "color": { "type": "keyword" },
          "size": { "type": "keyword" },
          "available": { "type": "boolean" }
        }
      }
    }
  }
}
```

### 2.1 Một nested query chứa nhiều điều kiện

Yêu cầu: tìm sản phẩm có một biến thể vừa màu đỏ vừa size M và còn hàng.

```json
GET /products/_search
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            { "term": { "variants.color": "red" } },
            { "term": { "variants.size": "M" } },
            { "term": { "variants.available": true } }
          ]
        }
      },
      "inner_hits": {}
    }
  }
}
```

Tất cả điều kiện nằm trong một nested scope, nên phải cùng khớp trên một biến thể. Với document mẫu, không có phần tử nào vừa màu đỏ vừa size M, do đó sản phẩm không được trả về.

### 2.2 Nhiều nested query độc lập có nghĩa khác

Nếu viết hai nested query riêng ở cấp parent, một query tìm màu đỏ và một query tìm size M, chúng có thể khớp hai biến thể khác nhau:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "nested": {
            "path": "variants",
            "query": { "term": { "variants.color": "red" } }
          }
        },
        {
          "nested": {
            "path": "variants",
            "query": { "term": { "variants.size": "M" } }
          }
        }
      ]
    }
  }
}
```

Truy vấn này có ý nghĩa: sản phẩm có ít nhất một biến thể màu đỏ và có ít nhất một biến thể size M; hai biến thể không cần giống nhau.

| Cấu trúc | Điều kiện phải khớp |
|---|---|
| Một `nested` chứa nhiều filter | Cùng một phần tử nested |
| Nhiều `nested` độc lập ở parent | Có thể là các phần tử nested khác nhau |

Đây là khác biệt ngữ nghĩa mà derived query theo tên thường không diễn đạt đủ rõ. Khi có nhiều điều kiện con, nên viết nested DSL tường minh và kiểm thử với document có các phần tử cố tình phân tán điều kiện.

### 2.3 Nested query lồng nhau

Mapping có thể chứa nested field bên trong nested field. Ví dụ đơn hàng có danh sách `items`, mỗi item có danh sách `discounts`. Nếu cần tìm một item có một discount thỏa điều kiện, query phải đi qua đúng các nested path theo cấu trúc mapping.

```json
{
  "nested": {
    "path": "items",
    "query": {
      "bool": {
        "filter": [
          { "term": { "items.sku": "SKU-1001" } },
          {
            "nested": {
              "path": "items.discounts",
              "query": {
                "range": {
                  "items.discounts.percent": { "gte": 10 }
                }
              }
            }
          }
        ]
      }
    }
  }
}
```

Ví dụ minh họa nested scope lồng nhau. `items.discounts` phải được khai báo nested trong mapping tương ứng. Query cần đúng path và đúng phạm vi parent-child; chỉ dùng field path dạng chấm mà không có nested query sẽ không tạo ra semantics nested.

## 3. Geo-shape: truy vấn hình học vượt quá điều kiện tên method

Geo query thông thường có thể tìm điểm gần một tọa độ hoặc nằm trong một khoảng địa lý. Geo-shape mở rộng mô hình để làm việc với hình dạng phức tạp như polygon, multipolygon, linestring và envelope. Ứng dụng có thể biểu diễn vùng phục vụ, ranh giới hành chính, khu vực giao hàng, tuyến đường hoặc vùng cấm.

Các yêu cầu như “tìm cửa hàng có vùng phục vụ giao với vùng người dùng chọn” hoặc “tìm khu đất nằm hoàn toàn trong ranh giới dự án” cần một `geo_shape` query với relation cụ thể. Derived query theo tên không phải abstraction thích hợp để diễn đạt hình học này.

### 3.1 Mapping field geo_shape

Ví dụ index cửa hàng có field `serviceArea`:

```json
PUT /stores
{
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "serviceArea": { "type": "geo_shape" }
    }
  }
}
```

Một document có thể lưu polygon dưới dạng GeoJSON:

```json
PUT /stores/_doc/store-01
{
  "name": "Cửa hàng trung tâm",
  "serviceArea": {
    "type": "polygon",
    "coordinates": [
      [
        [106.68, 10.76],
        [106.72, 10.76],
        [106.72, 10.79],
        [106.68, 10.79],
        [106.68, 10.76]
      ]
    ]
  }
}
```

Trong GeoJSON, thứ tự tọa độ là `[longitude, latitude]`, tức kinh độ trước và vĩ độ sau. Đây là lỗi dễ gặp khi dữ liệu đầu vào từ hệ thống khác dùng thứ tự latitude/longitude. Polygon phải khép kín bằng cách lặp lại điểm đầu ở cuối ring; ring đầu tiên là outer boundary, các ring tiếp theo (nếu có) biểu diễn holes.

Các kiểu shape phổ biến gồm `point`, `multipoint`, `linestring`, `multilinestring`, `polygon`, `multipolygon`, `geometrycollection` và `envelope`. Cần chọn kiểu phù hợp với dữ liệu địa lý và kiểm tra tính hợp lệ của tọa độ/hình học trước khi index.

### 3.2 `geo_shape` query và relation

Ví dụ tìm các cửa hàng có vùng phục vụ giao với một polygon truy vấn:

```json
GET /stores/_search
{
  "query": {
    "geo_shape": {
      "serviceArea": {
        "shape": {
          "type": "polygon",
          "coordinates": [
            [
              [106.70, 10.77],
              [106.74, 10.77],
              [106.74, 10.80],
              [106.70, 10.80],
              [106.70, 10.77]
            ]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
```

`relation` quy định quan hệ giữa shape được index trong document và shape trong query:

| Relation | Ý nghĩa khái quát |
|---|---|
| `intersects` | Hai hình có phần giao nhau; đây là lựa chọn mặc định phổ biến |
| `within` | Shape được index nằm trong shape truy vấn |
| `contains` | Shape được index bao chứa shape truy vấn |
| `disjoint` | Hai shape không giao nhau |

Hãy đọc relation theo hướng **shape trong document so với shape truy vấn**. Đảo chiều chủ thể có thể làm thay đổi kết quả. Với `within`, document shape phải nằm trong query shape; với `contains`, document shape phải chứa query shape.

### 3.3 Geo-shape khác geo-distance và geo-bounding-box

Không phải mọi truy vấn địa lý đều cần `geo_shape`:

| Loại field/query | Dữ liệu | Bài toán phù hợp |
|---|---|---|
| `geo_point` + `geo_distance` | Một điểm tọa độ | Tìm điểm trong bán kính quanh vị trí |
| `geo_point` + `geo_bounding_box` | Một điểm tọa độ | Tìm điểm nằm trong hình chữ nhật tọa độ |
| `geo_shape` | Polygon, line, envelope và shape khác | Quan hệ giữa các vùng hoặc hình học |

Nếu chỉ cần tìm cửa hàng cách người dùng 5 km, `geo_point` và `geo_distance` thường đơn giản hơn. Nếu cần kiểm tra vùng phục vụ giao với polygon của khách hàng, `geo_shape` phù hợp hơn.

## 4. Vì sao derived query khó diễn đạt geo-shape?

Tên method repository biểu diễn điều kiện theo các keyword được Spring Data hỗ trợ, chẳng hạn `Between`, `LessThan`, `Containing`, `Near` (tùy module và kiểu dữ liệu). Nhưng quan hệ hình học của hai shape không thể rút gọn thành tên thuộc tính cộng một toán tử đơn giản.

Một yêu cầu geo-shape có thể cần:

- Field mapping là `geo_shape`.
- Hình học query gồm type và coordinates.
- Relation như `intersects`, `within`, `contains` hoặc `disjoint`.
- Quy tắc orientation cho polygon trong trường hợp phù hợp.
- Nhiều shape hoặc nhiều nhánh bool.
- Bộ lọc nghiệp vụ bổ sung như trạng thái cửa hàng hoặc loại dịch vụ.

Các thành phần đó thuộc cấu trúc Query DSL. Việc cố đặt chúng trong tên method không làm query rõ hơn. Dùng `@Query` nếu shape tĩnh; dùng `NativeQuery`/Java Client nếu shape được tạo theo request hoặc cần nhiều điều kiện tùy chọn.

### 4.1 Query geo-shape tĩnh bằng `@Query`

Ví dụ repository method với một polygon cố định:

```java
@Query("""
    {
      "geo_shape": {
        "serviceArea": {
          "shape": {
            "type": "envelope",
            "coordinates": [
              [106.70, 10.80],
              [106.74, 10.76]
            ]
          },
          "relation": "intersects"
        }
      }
    }
    """)
List<Store> findStoresIntersectingConfiguredArea();
```

Đây là query tĩnh, không nhận shape từ người gọi. Với dữ liệu tọa độ động, không nên nối chuỗi JSON thủ công. Hãy sử dụng query builder hoặc API client có kiểu dữ liệu để tạo shape an toàn.

## 5. Kết hợp nested, geo-shape và bool query

Một yêu cầu thực tế có thể cần tìm cửa hàng:

- Đang hoạt động.
- Vùng phục vụ giao với polygon do người dùng chọn.
- Có ít nhất một dịch vụ phù hợp trong mảng nested `services`.
- Dịch vụ đó đang bật và có loại `delivery`.

Mapping ví dụ:

```json
PUT /stores
{
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "active": { "type": "boolean" },
      "serviceArea": { "type": "geo_shape" },
      "services": {
        "type": "nested",
        "properties": {
          "type": { "type": "keyword" },
          "enabled": { "type": "boolean" }
        }
      }
    }
  }
}
```

Query DSL:

```json
GET /stores/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        {
          "geo_shape": {
            "serviceArea": {
              "shape": {
                "type": "polygon",
                "coordinates": [
                  [
                    [106.70, 10.77],
                    [106.74, 10.77],
                    [106.74, 10.80],
                    [106.70, 10.80],
                    [106.70, 10.77]
                  ]
                ]
              },
              "relation": "intersects"
            }
          }
        },
        {
          "nested": {
            "path": "services",
            "query": {
              "bool": {
                "filter": [
                  { "term": { "services.type": "delivery" } },
                  { "term": { "services.enabled": true } }
                ]
              }
            }
          }
        }
      ]
    }
  }
}
```

Query này cho thấy vì sao derived query không còn phù hợp: điều kiện được đặt ở ba phạm vi khác nhau. `active` là field của document cha; `serviceArea` là quan hệ hình học; `services.type` và `services.enabled` phải cùng khớp trong một nested document. Một `bool.filter` ở cấp ngoài kết hợp ba yêu cầu này.

## 6. Chọn giữa @Query, NativeQuery và Elasticsearch Java Client

Không có một lựa chọn duy nhất cho mọi query. Có thể dùng các tiêu chí sau:

| Tình huống | Cách biểu diễn nên cân nhắc | Lý do |
|---|---|---|
| Equality/range đơn giản | Derived query | Tên method ngắn, ý nghĩa rõ |
| Query DSL tĩnh, ít tham số | `@Query` | JSON hiển thị trực tiếp cấu trúc query |
| Nhiều điều kiện tùy chọn | `NativeQuery` + `ElasticsearchOperations` | Dựng query theo input mà không nối JSON |
| Nested scope phức tạp | `NativeQuery` hoặc Java Client | Kiểm soát rõ phạm vi và các nhánh bool |
| Geo-shape động | `NativeQuery` hoặc Java Client | Tạo shape, coordinates và relation theo request |
| Aggregation, highlight, inner hits, sort phức tạp | `NativeQuery`/`ElasticsearchOperations` | API search cho phép kiểm soát nhiều phần của request |
| Tính năng chưa được abstraction hỗ trợ thuận tiện | Elasticsearch Java Client trực tiếp | Truy cập request/response của Elasticsearch API |

### 6.1 Khi dùng `@Query`

Ưu điểm:

- Query DSL hiện rõ, có thể so sánh trực tiếp với request REST.
- Không cần viết builder nhiều tầng cho query ổn định.
- Dễ lưu query mẫu và kiểm tra với Elasticsearch Dev Tools.

Giới hạn:

- Query nằm trong chuỗi Java, có thể dài và khó đọc nếu nhiều tầng.
- Logic điều kiện tùy chọn không tự nhiên; thường phải tạo nhiều method hoặc chuyển sang builder.
- Thay đổi cấu trúc JSON có thể khó kiểm tra ở compile time.
- Placeholder và escaping phụ thuộc cơ chế binding của Spring Data; không nên tự nối dữ liệu người dùng vào chuỗi JSON.

### 6.2 Khi dùng NativeQuery

Ưu điểm:

- Có thể xây dựng query theo dữ liệu đầu vào.
- Hỗ trợ nhiều thành phần của Elasticsearch Query DSL thông qua Java Client builder.
- Có thể kết hợp query, sort, aggregation, highlight và các search option.
- Có thể dùng cùng `ElasticsearchOperations` để ánh xạ kết quả về entity.

Giới hạn:

- Builder có thể dài khi query nhiều tầng.
- API builder thay đổi theo thế hệ Elasticsearch Java Client và Spring Data.
- Người viết vẫn phải hiểu Query DSL; builder không tự sửa semantics sai.
- Một số tính năng mới của Elasticsearch có thể chưa được phiên bản client mà dự án đang dùng hỗ trợ.

### 6.3 Khi dùng Java Client trực tiếp

Nếu cần API hoặc response field chưa được `ElasticsearchOperations` biểu diễn, có thể inject `ElasticsearchClient` và gọi API trực tiếp. Cách này cho quyền kiểm soát cao hơn nhưng ứng dụng phải tự chịu trách nhiệm về mapping kết quả, xử lý lỗi, phân trang và chuyển đổi dữ liệu.

Không nên trộn nhiều tầng client chỉ vì một query phức tạp. Chọn một abstraction phù hợp cho từng use case và giữ logic xây dựng query trong service/repository adapter riêng.

## 7. Xây dựng query động mà không ghép chuỗi JSON

Giả sử người dùng có thể chọn category, vùng địa lý và một số bộ lọc dịch vụ. Một số điều kiện có thể không được gửi. Cách tiếp cận tốt là xây dựng danh sách filter theo input rồi kết hợp chúng trong một `bool`.

Pseudo-code mô tả cấu trúc:

```java
List<Query> filters = new ArrayList<>();

if (category != null) {
    filters.add(termQuery("category", category));
}

if (serviceArea != null) {
    filters.add(geoShapeIntersectsQuery("serviceArea", serviceArea));
}

if (serviceType != null || enabledOnly) {
    filters.add(nestedServiceFilter(serviceType, enabledOnly));
}

Query query = boolFilter(filters);
```

Các hàm `termQuery`, `geoShapeIntersectsQuery`, `nestedServiceFilter` và `boolFilter` ở đây là hàm minh họa ý tưởng, không phải API có sẵn của Spring Data. Trong implementation, chúng có thể trả về `co.elastic.clients.elasticsearch._types.query_dsl.Query` từ Elasticsearch Java Client rồi được đưa vào `NativeQuery.builder().withQuery(...)`.

Tách builder theo phạm vi giúp code dễ kiểm tra:

- Hàm dựng filter parent chỉ xử lý field của document cha.
- Hàm dựng nested query chịu trách nhiệm gom điều kiện phải cùng khớp trên một child.
- Hàm dựng geo-shape query chịu trách nhiệm type, coordinates và relation.
- Hàm cuối kết hợp các nhánh theo `bool.filter`, `must`, `should` hoặc `must_not`.

Không đưa mọi điều kiện vào một danh sách phẳng nếu chúng thuộc các nested scope khác nhau. Cấu trúc object query nên phản ánh cấu trúc semantics của yêu cầu.

## 8. Những giới hạn biểu diễn và cách xử lý

### 8.1 Tên method quá dài

Khi tên method chứa nhiều `And`, `Or`, `Between`, `Containing`, `Not` và các property path, nó trở nên khó đọc và khó xác định thứ tự logic. Chuyển sang `@Query` hoặc builder để thể hiện cấu trúc query rõ ràng.

### 8.2 Derived query không thể tự bảo đảm nested scope

Tên method chứa nhiều property con không tự nói rằng điều kiện phải khớp trên cùng nested object. Dùng một nested query chứa các điều kiện cùng scope.

### 8.3 `@Query` không thuận tiện cho nhiều nhánh tùy chọn

Nếu request có hàng chục filter tùy chọn, chuỗi JSON tĩnh khó mở rộng. Dùng `NativeQuery` và builder để chỉ thêm điều kiện được cung cấp.

### 8.4 Geo-shape không phải chỉ là hai tọa độ

Geo-shape cần loại geometry, cấu trúc coordinates và relation. Không thay bằng `geo_distance` hoặc bounding box nếu yêu cầu là giao nhau/bao chứa giữa hai hình học.

### 8.5 Query có nhiều `must_not` hoặc `should`

Các nhánh `bool` lồng nhau và `minimum_should_match` ảnh hưởng trực tiếp đến kết quả. Hãy viết query JSON hoặc builder theo cấu trúc rõ ràng và tạo dữ liệu kiểm thử đại diện cho từng nhánh.

### 8.6 Query DSL được hỗ trợ theo phiên bản

Elasticsearch Java Client, Spring Data Elasticsearch và Elasticsearch server phải tương thích. Một tính năng mới có thể chưa có trong client đang được Spring Boot quản lý. Kiểm tra version matrix và API reference của đúng dependency; không tự nâng riêng một client version nếu framework quản lý phiên bản khác.

## 9. Kiểm thử truy vấn phức tạp

Với nested và geo-shape, một test chỉ có document khớp là chưa đủ. Cần tạo cả trường hợp gần giống nhưng không được khớp để xác nhận semantics.

### 9.1 Test nested same-element

Tạo ít nhất hai document:

```json
{
  "_id": "p1",
  "variants": [
    { "color": "red", "size": "XL" },
    { "color": "blue", "size": "M" }
  ]
}
```

```json
{
  "_id": "p2",
  "variants": [
    { "color": "red", "size": "M" }
  ]
}
```

Query một nested scope yêu cầu red và M phải chỉ trả `p2`. Nếu trả cả `p1`, hãy kiểm tra mapping và cách đặt nested query.

### 9.2 Test geo-shape relation

Tạo shape:

- Nằm hoàn toàn bên trong query polygon.
- Cắt qua biên query polygon.
- Bao chứa query polygon.
- Nằm hoàn toàn ngoài query polygon.

Chạy từng relation (`intersects`, `within`, `contains`, `disjoint`) và xác nhận kết quả theo hướng so sánh shape document với query shape. Test cả tọa độ biên và polygon có nhiều ring nếu nghiệp vụ sử dụng holes.

### 9.3 Test query động

Với mỗi filter tùy chọn, test:

- Không truyền filter nào.
- Chỉ truyền một filter.
- Truyền nhiều filter cùng lúc.
- Truyền giá trị rỗng hoặc không hợp lệ.
- Kết hợp parent filter với nested filter và geo-shape.

Kiểm tra query thực tế được gửi đi khi cần. Có thể bật logging có kiểm soát trong môi trường phát triển hoặc chạy cùng JSON DSL trên Elasticsearch test instance.

### 9.4 Dùng Elasticsearch thật trong integration test

Các hành vi phụ thuộc mapping, nested, analyzer và geo-shape nên được kiểm thử với Elasticsearch tương thích thay vì chỉ mock repository. Mock có thể kiểm tra service gọi đúng collaborator, nhưng không chứng minh query DSL được server hiểu đúng.

## 10. Nguyên tắc thiết kế

- Dùng derived query cho điều kiện đơn giản, ổn định và tên method vẫn dễ đọc.
- Dùng `@Query` cho Query DSL tĩnh, có cấu trúc rõ và ít biến thể.
- Dùng `NativeQuery` khi query được xây dựng động hoặc có nhiều tầng nested/geo-shape/bool.
- Dùng Elasticsearch Java Client trực tiếp khi cần API/response mà abstraction hiện tại chưa đáp ứng.
- Đặt các điều kiện phải khớp trên cùng child vào cùng một nested query.
- Đặt các nested query độc lập ở cấp parent khi các điều kiện có thể khớp trên các child khác nhau.
- Dùng `geo_shape` cho quan hệ hình học giữa vùng/shape; dùng `geo_point` cho bài toán điểm và khoảng cách đơn giản.
- Luôn xác nhận thứ tự tọa độ GeoJSON là longitude rồi latitude.
- Không nối input người dùng vào JSON query bằng string concatenation.
- Giữ query builder theo từng phạm vi nghiệp vụ và kiểm thử các trường hợp biên.
- Kiểm tra tính tương thích của Spring Data, Elasticsearch Java Client và Elasticsearch server.

## 11. Tổng kết

Derived query theo tên method là lựa chọn tốt cho điều kiện đơn giản, nhưng không phải ngôn ngữ biểu diễn đầy đủ Query DSL. Nested query cần kiểm soát phạm vi để các điều kiện có thể được đánh giá trên cùng một phần tử hoặc trên các phần tử khác nhau theo đúng nghiệp vụ. Geo-shape cần geometry, coordinates và relation; các điều kiện bool phức tạp cũng cần cấu trúc lồng nhau rõ ràng.

Với query tĩnh, `@Query` giúp thể hiện trực tiếp JSON DSL. Với query động, nested nhiều tầng, geo-shape hoặc search request nhiều thành phần, `NativeQuery` kết hợp `ElasticsearchOperations` thường linh hoạt hơn. Khi cần quyền kiểm soát API đầy đủ, có thể dùng Elasticsearch Java Client trực tiếp. Dù chọn cách nào, hãy để cấu trúc query phản ánh đúng phạm vi dữ liệu, mapping thực tế và semantics mà người dùng mong đợi.
