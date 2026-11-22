# Tạo bộ lọc danh mục, khoảng giá và thống kê faceted search

## 1. Bài toán faceted search trong trang danh sách sản phẩm

Faceted search là kiểu tìm kiếm trong đó người dùng vừa xem danh sách kết quả, vừa thu hẹp kết quả bằng các nhóm bộ lọc có số lượng tương ứng. Một trang thương mại điện tử thường có các facet như:

- Danh mục: điện thoại, máy tính, âm thanh.
- Thương hiệu: Acme, Nova, Zenith.
- Khoảng giá: dưới 500.000, 500.000–2.000.000, trên 2.000.000.
- Tình trạng: còn hàng, hết hàng.
- Thuộc tính khác: màu sắc, kích thước, chất liệu hoặc đánh giá.

Một lựa chọn trong facet thường hiển thị cả tên và số sản phẩm phù hợp:

~~~text
Danh mục
[ ] Điện thoại             128
[ ] Máy tính                74
[x] Âm thanh                36

Thương hiệu
[ ] Acme                    18
[ ] Nova                    11
[ ] Zenith                   7

Khoảng giá
[ ] Dưới 500.000            12
[ ] 500.000 - 2.000.000     25
[ ] Trên 2.000.000           9
~~~

Khi người dùng chọn Âm thanh và khoảng giá từ 500.000 đến 2.000.000, danh sách chỉ hiển thị sản phẩm thỏa cả hai điều kiện. Các facet khác cũng cập nhật số lượng để người dùng biết có thể tiếp tục thu hẹp theo cách nào.

Một request faceted search thường cần trả về đồng thời:

1. Các sản phẩm phù hợp với tất cả filter đã chọn.
2. Tổng số sản phẩm phù hợp.
3. Danh sách giá trị của từng facet.
4. Số document thuộc từng giá trị hoặc khoảng giá.
5. Có thể thêm giá thấp nhất, cao nhất, giá trung bình hoặc các thống kê khác.

Elasticsearch có thể tính hits và nhiều aggregation trong cùng một Search API request. Spring Data Elasticsearch cung cấp NativeQuery để kết hợp query DSL của Java API Client với các aggregation đó.

Điểm cần thiết kế cẩn thận là phạm vi document mà từng facet dùng để đếm. Nếu mọi filter đều nằm trong query, facet category có thể chỉ còn trả về category đã được chọn. Faceted search thường cần một quy tắc khác: danh sách hit tuân theo toàn bộ filter, còn mỗi facet có thể bỏ qua chính filter của nó khi tính số lượng.

## 2. Thiết kế document và mapping cho bộ lọc

Các field dùng để lọc và thống kê cần có kiểu dữ liệu phù hợp. Với sản phẩm, một mapping cơ bản có thể như sau:

~~~json
PUT /products
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
      },
      "category": {
        "type": "keyword"
      },
      "brand": {
        "type": "keyword"
      },
      "price": {
        "type": "long"
      },
      "active": {
        "type": "boolean"
      },
      "inStock": {
        "type": "boolean"
      },
      "tenantId": {
        "type": "keyword"
      }
    }
  }
}
~~~

Ý nghĩa của từng field:

| Field | Mapping | Dùng cho |
|---|---|---|
| name | text + keyword subfield | Full-text search và sort/group chính xác nếu cần |
| category | keyword | Term/terms filter và terms aggregation |
| brand | keyword | Term/terms filter và terms aggregation |
| price | long | Range query, range aggregation, min/max/avg |
| active | boolean | Chỉ lấy sản phẩm đang kinh doanh |
| inStock | boolean | Bộ lọc còn hàng |
| tenantId | keyword | Giới hạn dữ liệu theo tenant |

Danh mục và thương hiệu thường là giá trị định danh. Dùng keyword để Elasticsearch so khớp nguyên giá trị, thay vì phân tích chuỗi thành token như field text.

Giá cần là field số. Không lưu giá dưới dạng chuỗi như "1.500.000 VND", vì khi đó range query và range aggregation không thể so sánh theo thứ tự số học. Với tiền tệ có phần thập phân, có thể lưu đơn vị nhỏ nhất dưới dạng long, ví dụ cents, hoặc dùng scaled_float với scaling factor phù hợp. Trong bài này, price là số nguyên theo đơn vị tiền mà ứng dụng quy định.

Một entity Spring Data Elasticsearch tương ứng:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(type = FieldType.Text),
        otherFields = {
            @InnerField(suffix = "keyword", type = FieldType.Keyword)
        }
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String brand;

    @Field(type = FieldType.Long)
    private Long price;

    @Field(type = FieldType.Boolean)
    private boolean active;

    @Field(type = FieldType.Boolean)
    private boolean inStock;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    // Constructors, getters and setters
}
~~~

Nếu muốn tìm kiếm full-text theo name nhưng vẫn cần sort hoặc aggregation trên giá trị nguyên vẹn, khai báo multi-field keyword cho name. Không chạy terms aggregation trên field text thông thường nếu chưa cân nhắc fielddata và chi phí heap.

Ví dụ dữ liệu:

~~~json
POST /products/_bulk?refresh=true
{"index":{"_id":"p-1"}}
{"name":"Wireless Headphones","category":"audio","brand":"Acme","price":1200000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-2"}}
{"name":"Bluetooth Speaker","category":"audio","brand":"Acme","price":1800000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-3"}}
{"name":"Studio Earbuds","category":"audio","brand":"Nova","price":850000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-4"}}
{"name":"Workstation Laptop","category":"computers","brand":"Acme","price":1900000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-5"}}
{"name":"Monitor","category":"computers","brand":"Nova","price":4200000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-6"}}
{"name":"Office Keyboard","category":"accessories","brand":"Acme","price":650000,"active":true,"inStock":false,"tenantId":"t-01"}
{"index":{"_id":"p-7"}}
{"name":"Studio Headphones","category":"audio","brand":"Acme","price":3200000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-8"}}
{"name":"Clearance Headphones","category":"audio","brand":"Acme","price":1500000,"active":false,"inStock":true,"tenantId":"t-01"}
~~~

Trong ví dụ, sản phẩm p-8 không active nên không xuất hiện trong trang danh sách của người dùng. Điều kiện active sẽ được áp dụng cho cả hits và aggregation để các con số chỉ phản ánh sản phẩm đang kinh doanh.

## 3. Mô hình hóa filter từ request của người dùng

API không nên nhận trực tiếp một query DSL tùy ý từ trình duyệt. Hãy định nghĩa DTO chứa những tiêu chí ứng dụng cho phép.

~~~java
import java.util.List;

public record ProductSearchCriteria(
    List<String> categories,
    List<String> brands,
    Long minPrice,
    Long maxPrice,
    Boolean inStock,
    int page,
    int size
) {
}
~~~

Ví dụ request:

~~~http
GET /api/products?categories=audio,computers&brands=Acme&minPrice=500000&maxPrice=2000000&inStock=true&page=0&size=20
~~~

Ý nghĩa:

- categories có thể chứa nhiều giá trị.
- brands có thể chứa nhiều giá trị.
- minPrice và maxPrice tạo thành một khoảng giá.
- inStock là filter tùy chọn.
- page và size điều khiển phân trang kết quả.

Trước khi tạo query, chuẩn hóa và kiểm tra input:

~~~java
public ProductSearchCriteria normalize(ProductSearchCriteria criteria) {
    if (criteria.page() < 0) {
        throw new IllegalArgumentException("page must be >= 0");
    }

    int safeSize = Math.min(Math.max(criteria.size(), 1), 100);

    if (criteria.minPrice() != null && criteria.minPrice() < 0) {
        throw new IllegalArgumentException("minPrice must be >= 0");
    }

    if (criteria.maxPrice() != null && criteria.maxPrice() < 0) {
        throw new IllegalArgumentException("maxPrice must be >= 0");
    }

    if (criteria.minPrice() != null
            && criteria.maxPrice() != null
            && criteria.minPrice() > criteria.maxPrice()) {
        throw new IllegalArgumentException(
            "minPrice must be <= maxPrice"
        );
    }

    return new ProductSearchCriteria(
        criteria.categories() == null
            ? List.of()
            : criteria.categories().stream().distinct().toList(),
        criteria.brands() == null
            ? List.of()
            : criteria.brands().stream().distinct().toList(),
        criteria.minPrice(),
        criteria.maxPrice(),
        criteria.inStock(),
        criteria.page(),
        safeSize
    );
}
~~~

Trong hệ thống thực tế, nên xác thực thêm category và brand theo danh mục được phép, giới hạn số giá trị filter, whitelist field sort và giới hạn page size. Các filter bảo mật như tenantId phải lấy từ security context của server, không tin tenantId do client tự gửi.

Quy ước quan trọng cho nhiều lựa chọn trong cùng một facet:

- Chọn nhiều category thường mang nghĩa OR: audio hoặc computers.
- Category và brand kết hợp với nhau thường mang nghĩa AND: thuộc audio và mang brand Acme.
- MinPrice và maxPrice cùng áp dụng trên một field price, tạo điều kiện khoảng.
- Filter inStock=true kết hợp với category và price bằng AND.

Với field category đơn trị, query terms với danh sách category sẽ khớp document có category thuộc một trong các giá trị đã chọn. Nếu nghiệp vụ muốn document phải thỏa tất cả giá trị đã chọn, cần biểu diễn từng điều kiện bằng các term riêng trong bool.filter hoặc thay đổi mô hình dữ liệu phù hợp. Không nhầm OR giữa các giá trị cùng facet với AND giữa các facet.

## 4. Tạo bộ lọc category và brand bằng terms query

Một term query so khớp một giá trị chính xác:

~~~json
{
  "term": {
    "category": "audio"
  }
}
~~~

Khi người dùng chọn nhiều danh mục, dùng terms query:

~~~json
{
  "terms": {
    "category": ["audio", "computers"]
  }
}
~~~

Query trên khớp document có category bằng audio hoặc computers. Nó không yêu cầu một document đồng thời thuộc cả hai category.

Một request có nhiều facet:

~~~http
GET /products/_search
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
          "term": {
            "tenantId": "t-01"
          }
        },
        {
          "terms": {
            "category": ["audio", "computers"]
          }
        },
        {
          "terms": {
            "brand": ["Acme"]
          }
        }
      ]
    }
  }
}
~~~

Các điều kiện trong bool.filter được kết hợp bằng AND. Document phải active, thuộc tenant t-01, có category được chọn và có brand Acme.

Filter context không tính relevance score. Đây là lựa chọn phù hợp cho category, brand, trạng thái, tenant và các điều kiện có tính cấu trúc. Nếu có từ khóa tìm kiếm, có thể đặt match query trong must và đặt các điều kiện cấu trúc trong filter.

Ví dụ kết hợp text search và filter:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless headphones"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "terms": {
            "category": ["audio"]
          }
        }
      ]
    }
  }
}
~~~

Điều kiện match tìm nội dung phù hợp; filter giới hạn kết quả theo trạng thái và category. Facet aggregation ở cùng request sẽ mặc định chạy trên document khớp toàn bộ top-level query.

## 5. Tạo bộ lọc khoảng giá bằng range query

Range query giới hạn giá trị theo cận dưới và cận trên.

~~~json
{
  "range": {
    "price": {
      "gte": 500000,
      "lte": 2000000
    }
  }
}
~~~

Các toán tử:

| Toán tử | Ý nghĩa |
|---|---|
| gt | Lớn hơn, không bao gồm cận |
| gte | Lớn hơn hoặc bằng, bao gồm cận |
| lt | Nhỏ hơn, không bao gồm cận |
| lte | Nhỏ hơn hoặc bằng, bao gồm cận |

Nếu giao diện ghi "500.000 đến 2.000.000" và muốn bao gồm cả hai giá trị biên, dùng gte và lte. Nếu chia thành các khoảng liên tiếp, cần quy ước cận trên của khoảng trước là exclusive để tránh document bị đếm hai lần.

Ví dụ thêm khoảng giá vào query:

~~~http
GET /products/_search
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
              "gte": 500000,
              "lte": 2000000
            }
          }
        }
      ]
    }
  }
}
~~~

Khi chỉ có minPrice, tạo điều kiện gte. Khi chỉ có maxPrice, tạo điều kiện lte. Khi cả hai đều null, không thêm range query. Không tạo range query với cận null hoặc chuỗi rỗng.

Một helper có thể xây query theo input tùy chọn:

~~~java
private Query priceRange(Long minPrice, Long maxPrice) {
    return Query.of(q -> q.range(r -> r.number(n -> {
        n.field("price");

        if (minPrice != null) {
            n.gte(minPrice.doubleValue());
        }

        if (maxPrice != null) {
            n.lte(maxPrice.doubleValue());
        }

        return n;
    })));
}
~~~

Java API Client dùng kiểu range cụ thể cho field số. Với phiên bản client đang dùng, có thể dùng number range variant cho field price dạng long/numeric. Nếu ứng dụng dùng field date, cần dùng date range variant tương ứng.

Không biến giá thành chuỗi trước khi tạo query. Cũng không dùng giá trị đã định dạng theo locale, ví dụ "1.500.000", làm giá trị gửi vào Elasticsearch.

## 6. Kết hợp filter tùy chọn trong bool.filter

Khi một tiêu chí không được chọn, bỏ nó khỏi danh sách filter. Điều này giúp query gọn và tránh nhầm lẫn giữa filter rỗng với filter có giá trị.

Một builder minh họa:

~~~java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

public class ProductQueryFactory {

    public Query buildSelectedFilters(ProductSearchCriteria criteria) {
        List<Query> filters = new ArrayList<>();

        if (criteria.categories() != null
                && !criteria.categories().isEmpty()) {
            filters.add(Query.of(q -> q.terms(t -> t
                .field("category")
                .terms(tf -> tf.value(
                    criteria.categories().stream()
                        .map(FieldValue::of)
                        .toList()
                ))
            )));
        }

        if (criteria.brands() != null
                && !criteria.brands().isEmpty()) {
            filters.add(Query.of(q -> q.terms(t -> t
                .field("brand")
                .terms(tf -> tf.value(
                    criteria.brands().stream()
                        .map(FieldValue::of)
                        .toList()
                ))
            )));
        }

        if (criteria.minPrice() != null
                || criteria.maxPrice() != null) {
            filters.add(priceRange(
                criteria.minPrice(),
                criteria.maxPrice()
            ));
        }

        return and(filters);
    }

    private Query and(List<Query> filters) {
        if (filters.isEmpty()) {
            return Query.of(q -> q.matchAll(m -> m));
        }

        return Query.of(q -> q.bool(b -> b.filter(filters)));
    }

    private Query priceRange(Long minPrice, Long maxPrice) {
        return Query.of(q -> q.range(r -> r.number(n -> {
            n.field("price");
            if (minPrice != null) {
                n.gte(minPrice.doubleValue());
            }
            if (maxPrice != null) {
                n.lte(maxPrice.doubleValue());
            }
            return n;
        })));
    }
}
~~~

Helper and() trả match_all khi không có selected filter. Trong request thực tế, có thể không gọi withFilter nếu không có filter nào; match_all cũng cho cùng kết quả logic.

Một số quy tắc nên giữ nhất quán:

- Mỗi filter là một Query độc lập.
- Các filter khác facet kết hợp bằng AND.
- Nhiều giá trị trong cùng category hoặc brand được đưa vào một terms query để có semantics OR.
- Khoảng giá chỉ được thêm khi có ít nhất một cận.
- Filter tenant và active luôn nằm trong base query của server.
- Không cho client tự chọn tên field để đưa thẳng vào query builder.

Trong ví dụ này, inStock là điều kiện nền bổ sung chứ chưa phải facet có thống kê riêng. Nếu người dùng chọn còn hàng, hãy thêm điều kiện đó vào base query để mọi facet đều tôn trọng trạng thái này. Nếu muốn hiển thị số lượng còn hàng và hết hàng, hãy tạo một facet scope riêng cho inStock giống như category và brand.

Cấu trúc này giúp tách việc đọc request khỏi việc tạo Elasticsearch DSL. Nó cũng giúp test riêng từng helper: category query, brand query, price range query và cách kết hợp chúng.

## 7. Từ search filter đến faceted search

Nếu chỉ cần lọc danh sách, đưa mọi điều kiện vào query.bool.filter là đủ. Nhưng trang faceted search còn cần hiển thị số lượng của các lựa chọn khác để người dùng tiếp tục lọc.

Hãy xét ví dụ người dùng chọn:

- Brand = Acme.
- Category = audio.
- Price từ 500.000 đến 2.000.000.

Nếu đưa cả ba filter vào top-level query, Elasticsearch chỉ tính aggregation trên tập sản phẩm đã thỏa cả ba điều kiện. Category aggregation lúc này gần như chỉ còn trả về audio. Người dùng không thấy có bao nhiêu sản phẩm computers hoặc accessories của Acme trong khoảng giá đó.

Có hai cách hiển thị facet thường gặp:

**Cách A: Các facet độc lập với toàn bộ lựa chọn facet.** Top-level query chứa điều kiện cố định như tenant, active và text search. Các lựa chọn category, brand, price được đặt trong post_filter. Aggregation không bị ảnh hưởng bởi bất kỳ lựa chọn facet nào. Cách này hiển thị số lượng tổng quát trong tập nền.

**Cách B: Mỗi facet bỏ qua filter của chính nó nhưng vẫn tôn trọng các facet khác.** Category counts được tính theo brand và price đang chọn, nhưng không bị giới hạn bởi category đã chọn. Brand counts được tính theo category và price, nhưng bỏ qua brand đã chọn. Price ranges được tính theo category và brand, nhưng không bị giới hạn bởi khoảng giá đã chọn. Đây thường là trải nghiệm tự nhiên hơn cho bộ lọc thương mại điện tử.

Cách B được gọi là disjunctive faceting hoặc self-excluding facets. Nó cần các filter aggregation có scope riêng cho từng facet.

## 8. Phân biệt query filter và post_filter

Elasticsearch có hai vị trí quan trọng để lọc:

- bool.filter trong query.
- post_filter ở cấp Search API request.

bool.filter áp dụng cho cả hits và aggregations. post_filter chỉ áp dụng sau khi aggregations đã được tính, nên nó thu hẹp search hits mà không thu hẹp aggregation results.

Ví dụ:

~~~http
GET /products/_search
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
          "term": {
            "tenantId": "t-01"
          }
        }
      ]
    }
  },
  "post_filter": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "audio"
          }
        },
        {
          "range": {
            "price": {
              "gte": 500000,
              "lte": 2000000
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    },
    "brands": {
      "terms": {
        "field": "brand"
      }
    }
  }
}
~~~

Trong request:

- Query chỉ giới hạn sản phẩm active thuộc tenant t-01.
- post_filter chọn category audio và price trong khoảng.
- Hits chỉ chứa sản phẩm audio trong khoảng giá.
- Aggregation categories và brands tính trên tất cả sản phẩm active của tenant t-01, kể cả những category và giá khác.

Đây là cách A: mọi facet bỏ qua toàn bộ selected facet filters.

Đừng đặt tenant hoặc quyền truy cập chỉ trong post_filter. Aggregation chạy trước post_filter nên có thể thống kê dữ liệu ngoài phạm vi người dùng được phép xem. Các điều kiện bảo mật và phạm vi dữ liệu bắt buộc phải nằm trong top-level query, hoặc được áp dụng tương đương trong mọi aggregation scope nếu dùng global aggregation.

## 9. Tạo scope riêng cho từng facet

Để có cách B, top-level query vẫn chứa điều kiện nền. post_filter chứa toàn bộ filter người dùng đã chọn để lọc hits. Mỗi aggregation được bọc bằng một filter aggregation chỉ chứa các selected filter khác với facet đang được tính.

Giả sử người dùng đã chọn:

~~~json
{
  "categories": ["audio"],
  "brands": ["Acme"],
  "minPrice": 500000,
  "maxPrice": 2000000
}
~~~

Các scope cần dùng:

| Aggregation | Filter scope áp dụng | Filter bị bỏ qua |
|---|---|---|
| category facet | brand Acme + price 500.000–2.000.000 | category |
| brand facet | category audio + price 500.000–2.000.000 | brand |
| price facet | category audio + brand Acme | price |

Request đầy đủ:

~~~http
GET /products/_search
{
  "size": 20,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "tenantId": "t-01"
          }
        }
      ]
    }
  },
  "post_filter": {
    "bool": {
      "filter": [
        {
          "terms": {
            "category": ["audio"]
          }
        },
        {
          "terms": {
            "brand": ["Acme"]
          }
        },
        {
          "range": {
            "price": {
              "gte": 500000,
              "lte": 2000000
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "category_scope": {
      "filter": {
        "bool": {
          "filter": [
            {
              "terms": {
                "brand": ["Acme"]
              }
            },
            {
              "range": {
                "price": {
                  "gte": 500000,
                  "lte": 2000000
                }
              }
            }
          ]
        }
      },
      "aggs": {
        "categories": {
          "terms": {
            "field": "category",
            "size": 30
          }
        }
      }
    },
    "brand_scope": {
      "filter": {
        "bool": {
          "filter": [
            {
              "terms": {
                "category": ["audio"]
              }
            },
            {
              "range": {
                "price": {
                  "gte": 500000,
                  "lte": 2000000
                }
              }
            }
          ]
        }
      },
      "aggs": {
        "brands": {
          "terms": {
            "field": "brand",
            "size": 30
          }
        }
      }
    },
    "price_scope": {
      "filter": {
        "bool": {
          "filter": [
            {
              "terms": {
                "category": ["audio"]
              }
            },
            {
              "terms": {
                "brand": ["Acme"]
              }
            }
          ]
        }
      },
      "aggs": {
        "price_ranges": {
          "range": {
            "field": "price",
            "keyed": true,
            "ranges": [
              {
                "key": "under-500k",
                "to": 500000
              },
              {
                "key": "500k-2m",
                "from": 500000,
                "to": 2000000
              },
              {
                "key": "2m-5m",
                "from": 2000000,
                "to": 5000000
              },
              {
                "key": "5m-plus",
                "from": 5000000
              }
            ]
          }
        }
      }
    }
  }
}
~~~

Cách đọc request:

1. Query giới hạn toàn bộ request vào active products của tenant t-01.
2. post_filter áp dụng category, brand và price đã chọn cho hits.
3. category_scope áp dụng brand và price, rồi nhóm theo category.
4. brand_scope áp dụng category và price, rồi nhóm theo brand.
5. price_scope áp dụng category và brand, rồi chia giá thành các khoảng.
6. Mỗi aggregation trả số document theo phạm vi của chính nó.

Không cần global aggregation trong trường hợp này vì top-level query đã xác định đúng tập document nền. Filter aggregation chỉ tiếp tục thu hẹp tập nền cho từng facet.

Nếu dùng global aggregation, nó bỏ qua top-level query. Khi đó phải lặp lại các filter bảo mật như tenant, trạng thái truy cập và quyền dữ liệu bên trong từng scope. Điều này dễ tạo lỗi rò rỉ số liệu giữa tenant, nên chỉ dùng global khi thực sự cần vượt qua top-level query và đã thiết kế lại phạm vi dữ liệu cẩn thận.

## 10. Hiểu số lượng trong từng facet

Giả sử dữ liệu có các sản phẩm active sau:

| ID | Category | Brand | Price |
|---|---|---|---:|
| p-1 | audio | Acme | 1.200.000 |
| p-2 | audio | Acme | 1.800.000 |
| p-3 | audio | Nova | 850.000 |
| p-4 | computers | Acme | 1.900.000 |
| p-5 | computers | Nova | 4.200.000 |
| p-6 | accessories | Acme | 650.000 |
| p-7 | audio | Acme | 3.200.000 |

Người dùng chọn category audio, brand Acme và khoảng 500.000–2.000.000.

Hits chỉ còn p-1 và p-2.

Nhưng các facet counts theo self-excluding scope sẽ là:

**Category facet** áp dụng brand Acme và khoảng giá:

- audio: 2.
- computers: 1.
- accessories: 1.

**Brand facet** áp dụng category audio và khoảng giá:

- Acme: 2.
- Nova: 1.

**Price facet** áp dụng category audio và brand Acme:

- dưới 500.000: 0.
- 500.000–2.000.000: 2.
- 2.000.000–5.000.000: 1.
- từ 5.000.000 trở lên: 0.

Như vậy, danh sách sản phẩm vẫn tuân theo tất cả lựa chọn. Các con số ở từng facet phản ánh việc người dùng thay đổi riêng lựa chọn đó trong khi giữ nguyên các lựa chọn còn lại.

Nếu thay vì self-excluding facets mà dùng một terms aggregation đơn giản sau post_filter, category counts sẽ bao gồm toàn bộ sản phẩm active của tenant, không phụ thuộc brand hoặc price đã chọn. Cả hai cách đều hợp lệ nếu đúng với UX đã thiết kế; quan trọng là không nhầm lẫn semantics của số đếm.

## 11. Terms aggregation cho danh mục và thương hiệu

Terms aggregation nhóm document theo giá trị của field keyword.

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 30,
        "order": {
          "_count": "desc"
        }
      }
    }
  }
}
~~~

Response có dạng:

~~~json
{
  "categories": {
    "doc_count_error_upper_bound": 0,
    "sum_other_doc_count": 0,
    "buckets": [
      {
        "key": "audio",
        "doc_count": 42
      },
      {
        "key": "computers",
        "doc_count": 27
      },
      {
        "key": "accessories",
        "doc_count": 18
      }
    ]
  }
}
~~~

Mỗi bucket gồm:

- key: giá trị category.
- doc_count: số document trong bucket.
- Có thể có thông tin sai số phân tán tùy cấu hình terms aggregation.

size giới hạn số bucket trả về. Nếu chỉ hiển thị top 10 thương hiệu, không nên lấy hàng chục nghìn bucket rồi mới cắt danh sách ở Java.

Terms aggregation mặc định ưu tiên bucket có document count lớn. Với dữ liệu phân tán trên nhiều shard, số lượng có thể có sai số nếu một shard không gửi đủ bucket ứng viên về coordinating node. Có thể điều chỉnh shard_size để tăng số bucket ứng viên, nhưng cần cân bằng memory, network và reduce cost.

Nếu danh mục là một tập giá trị do nghiệp vụ quản lý và UI cần hiển thị cả lựa chọn có count bằng 0, không nên chỉ dựa vào terms aggregation. Terms aggregation thường chỉ trả các giá trị có document trong tập dữ liệu phù hợp. Có thể dùng filters aggregation với danh sách category cố định, hoặc lấy danh mục từ catalog service rồi ghép count từ Elasticsearch.

Ví dụ filters aggregation cho tập category cố định:

~~~json
{
  "aggs": {
    "category_counts": {
      "filters": {
        "filters": {
          "audio": {
            "term": {
              "category": "audio"
            }
          },
          "computers": {
            "term": {
              "category": "computers"
            }
          },
          "accessories": {
            "term": {
              "category": "accessories"
            }
          }
        }
      }
    }
  }
}
~~~

Filters aggregation có thể trả bucket cho từng filter được khai báo, kể cả bucket có doc_count bằng 0. Đây là lựa chọn phù hợp khi UI cần danh sách facet cố định, được quản lý ngoài index.

## 12. Range aggregation cho các khoảng giá

Range aggregation chia giá trị số thành các bucket do ứng dụng định nghĩa.

~~~json
{
  "aggs": {
    "price_ranges": {
      "range": {
        "field": "price",
        "keyed": true,
        "ranges": [
          {
            "key": "under-500k",
            "to": 500000
          },
          {
            "key": "500k-2m",
            "from": 500000,
            "to": 2000000
          },
          {
            "key": "2m-5m",
            "from": 2000000,
            "to": 5000000
          },
          {
            "key": "5m-plus",
            "from": 5000000
          }
        ]
      }
    }
  }
}
~~~

Mỗi khoảng bao gồm cận dưới và loại trừ cận trên:

- under-500k: price < 500.000.
- 500k-2m: 500.000 <= price < 2.000.000.
- 2m-5m: 2.000.000 <= price < 5.000.000.
- 5m-plus: price >= 5.000.000.

Vì cận trên là exclusive, một sản phẩm giá đúng 2.000.000 thuộc bucket 2m-5m theo định nghĩa trên. Nếu giao diện muốn khoảng 500.000 đến 2.000.000 bao gồm cả 2.000.000, hãy chọn ranh giới kế tiếp theo đơn vị tiền nhỏ nhất hoặc định nghĩa bucket phù hợp với quy ước nghiệp vụ. Đừng để nhãn hiển thị và ranh giới query khác nhau.

Khi dùng range aggregation, các khoảng có thể chồng lấn. Một document có thể được tính trong nhiều bucket nếu giá của nó nằm trong các khoảng giao nhau. Với facet giá dạng các dải liền nhau, hãy thiết kế khoảng không chồng lấn và không để hở giá trị giữa hai bucket.

Nếu muốn UI hiển thị nhãn tiếng Việt, có thể dùng key ổn định như under-500k, 500k-2m và map sang nhãn trong ứng dụng. Không nên dùng key làm nội dung hiển thị duy nhất vì ngôn ngữ, đơn vị tiền và định dạng số có thể thay đổi.

## 13. Histogram hay range aggregation?

Hai loại aggregation thường bị nhầm lẫn:

| Aggregation | Cách chia bucket | Khi phù hợp |
|---|---|---|
| range | Ứng dụng định nghĩa từng khoảng | Các nhóm giá mang ý nghĩa nghiệp vụ |
| histogram | Chia theo interval số cố định | Biểu đồ phân phối giá hoặc số liệu liên tục |
| terms | Nhóm theo giá trị phân loại | Category, brand, status |

Ví dụ histogram với interval 500.000:

~~~json
{
  "aggs": {
    "price_histogram": {
      "histogram": {
        "field": "price",
        "interval": 500000,
        "min_doc_count": 0
      }
    }
  }
}
~~~

Histogram hữu ích cho biểu đồ phân phối hoặc phân tích xu hướng. Range phù hợp hơn khi UI có các lựa chọn cố định như "Dưới 500.000", "500.000–2.000.000", "Trên 2.000.000".

Histogram có thể tạo bucket theo các khoảng đều nhau. Nếu các khoảng giá của nghiệp vụ không đều nhau, dùng range aggregation để định nghĩa chính xác.

## 14. Thêm metric thống kê trong facet

Ngoài doc_count, ứng dụng có thể cần giá nhỏ nhất, lớn nhất hoặc trung bình của sản phẩm trong phạm vi hiện tại.

Ví dụ:

~~~json
{
  "aggs": {
    "price_stats": {
      "stats": {
        "field": "price"
      }
    },
    "average_price": {
      "avg": {
        "field": "price"
      }
    },
    "minimum_price": {
      "min": {
        "field": "price"
      }
    },
    "maximum_price": {
      "max": {
        "field": "price"
      }
    }
  }
}
~~~

Nếu các metric cần tuân theo selected facets, đặt chúng trong filter aggregation có scope phù hợp, ví dụ price_scope. Nếu metric là thống kê toàn bộ tập sản phẩm của tenant, đặt nó ở top-level aggregation trên base query.

Metric có ý nghĩa khác nhau:

- avg: trung bình cộng các giá trị price có mặt.
- min: giá nhỏ nhất.
- max: giá lớn nhất.
- stats: count, min, max, avg và sum.
- value_count: số giá trị field, không nhất thiết bằng số document nếu field có nhiều giá trị.

Không dùng average price để suy ra median. Nếu UI cần median hoặc percentile, dùng percentile aggregation và cân nhắc chi phí cũng như độ chính xác của thuật toán.

## 15. Chú ý missing values và dữ liệu không đồng nhất

Một document có thể thiếu category, brand hoặc price. Các aggregation mặc định thường bỏ qua document không có giá trị ở field đang nhóm hoặc tính metric.

Điều này có thể làm tổng bucket nhỏ hơn số document trong phạm vi.

Nếu cần thể hiện sản phẩm chưa phân loại, có thể dùng missing aggregation hoặc cấu hình missing value cho aggregation phù hợp. Với terms aggregation, tham số missing có thể gán giá trị thay thế cho document thiếu field.

Ví dụ:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "missing": "uncategorized"
      }
    }
  }
}
~~~

Cần phân biệt hai tình huống:

- Field không tồn tại.
- Field tồn tại nhưng có giá trị rỗng hoặc sai chuẩn.

Nên chuẩn hóa dữ liệu ở ingest hoặc application layer. Không nên để "Audio", "audio", " AUDIO " và "audio " trở thành các bucket riêng nếu nghiệp vụ coi chúng là cùng một category.

Nếu dữ liệu cũ có mapping sai kiểu hoặc field chưa được index dưới dạng keyword/numeric, có thể cần reindex để tạo mapping mới. Không thể đổi tùy ý một field text đã tồn tại thành keyword chỉ bằng cách sửa annotation trong code.

## 16. Sắp xếp kết quả và phân trang cùng faceted search

Một request faceted search thường trả cả hits và aggregations. Có thể dùng Pageable để giới hạn hits:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(baseQuery)
    .withFilter(postFilter)
    .withPageable(PageRequest.of(0, 20))
    .withAggregation("category_scope", categoryScope)
    .withAggregation("brand_scope", brandScope)
    .withAggregation("price_scope", priceScope)
    .build();
~~~

Aggregation được tính trên tập document theo scope của nó; page size chỉ giới hạn số hits trả về. Không đặt size bằng số bucket cần hiển thị. Số bucket được điều khiển bởi size của terms aggregation hoặc các ranges đã định nghĩa.

Sort có thể được khai báo riêng:

~~~java
.withSort(SortOptions.of(s -> s.field(f -> f
    .field("price")
    .order(SortOrder.Asc)
)))
~~~

Khi sort theo giá, nên có thêm tie-breaker nếu dùng cursor pagination để tránh thứ tự không ổn định giữa document có cùng price. Với phân trang nông, PageRequest phù hợp; nếu người dùng duyệt rất sâu, cân nhắc search_after và PIT như chiến lược phân trang riêng.

Nếu UI cần tổng số trang chính xác, hãy quyết định rõ có theo dõi total hits chính xác hay không. Nếu chỉ cần nút tiếp theo, có thể tránh đếm tổng không cần thiết. Aggregation count của từng facet không thay thế total hits của search request.

## 17. Kết quả SearchHits trong Spring Data Elasticsearch

SearchOperations trả về SearchHits<T>, trong đó có:

- Danh sách SearchHit<T>.
- Total hits và relation.
- Thời gian thực thi.
- Aggregations.
- Suggest results nếu có.
- Metadata khác của search.

Ví dụ:

~~~java
SearchHits<Product> searchHits =
    operations.search(nativeQuery, Product.class);

List<Product> products = searchHits.getSearchHits().stream()
    .map(SearchHit::getContent)
    .toList();

long totalHits = searchHits.getTotalHits();

AggregationsContainer<?> aggregationContainer =
    searchHits.getAggregations();
~~~

Aggregation container là abstraction của Spring Data. Với Elasticsearch Java Client, implementation cụ thể là ElasticsearchAggregations. Có thể lấy aggregation theo tên và chuyển nó thành DTO ứng dụng.

~~~java
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);

ElasticsearchAggregations aggregations =
    (ElasticsearchAggregations) hits.getAggregations();

var categoryScope = aggregations.get("category_scope")
    .aggregation()
    .getAggregate();

var categoryBuckets = categoryScope.filter()
    .aggregations()
    .get("categories")
    .sterms()
    .buckets()
    .array();
~~~

Với terms aggregation trên field keyword, response variant là string terms. Java API Client có thể biểu diễn key dưới dạng FieldValue; với client version mới, lấy chuỗi bằng key().stringValue(). Kiểu variant cần khớp với aggregation đã gửi. Nếu đổi field sang long hoặc aggregation sang range, cách đọc response cũng phải đổi.

Ví dụ chuyển bucket thành DTO:

~~~java
public record FacetOption(
    String value,
    long count
) {
}
~~~

~~~java
List<FacetOption> categoryOptions = categoryBuckets.stream()
    .map(bucket -> new FacetOption(
        bucket.key().stringValue(),
        bucket.docCount()
    ))
    .toList();
~~~

Đừng trả trực tiếp các kiểu Java Client sâu ra controller nếu không cần. Tạo DTO ổn định của ứng dụng để UI không phụ thuộc cấu trúc response nội bộ của Elasticsearch.

## 18. Tạo aggregation bằng Java API Client

Spring Data NativeQuery hỗ trợ các aggregation từ Elasticsearch Java API Client. Một helper có thể tạo terms facet nằm trong filter scope:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

private Aggregation termsFacet(
        Query scope,
        String field,
        int size) {

    return Aggregation.of(a -> a
        .filter(scope)
        .aggregations("values", values -> values
            .terms(t -> t
                .field(field)
                .size(size)
            )
        )
    );
}
~~~

Với helper trên, aggregation ngoài cùng là filter aggregation. Terms aggregation nằm trong sub-aggregation tên values.

Một helper cho price ranges:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import co.elastic.clients.elasticsearch._types.aggregations.AggregationRange;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

private Aggregation priceRangeFacet(Query scope) {
    return Aggregation.of(a -> a
        .filter(scope)
        .aggregations("ranges", ranges -> ranges
            .range(r -> r
                .field("price")
                .keyed(true)
                .ranges(
                    AggregationRange.of(b -> b
                        .key("under-500k")
                        .to(500000.0)
                    ),
                    AggregationRange.of(b -> b
                        .key("500k-2m")
                        .from(500000.0)
                        .to(2000000.0)
                    ),
                    AggregationRange.of(b -> b
                        .key("2m-plus")
                        .from(2000000.0)
                    )
                )
            )
        )
    );
}
~~~

AggregationRange.from là cận dưới inclusive và to là cận trên exclusive. Key giúp ứng dụng nhận diện bucket mà không cần tự suy ra từ chuỗi do Elasticsearch tạo.

Tạo query hoàn chỉnh:

~~~java
List<Query> baseFilters = new ArrayList<>(List.of(
    term("active", true),
    term("tenantId", currentTenantId)
));

if (criteria.inStock() != null) {
    baseFilters.add(term("inStock", criteria.inStock()));
}

Query baseQuery = and(baseFilters);

Query categoryScope = and(concat(
    selectedBrandFilters,
    selectedPriceFilters
));

Query brandScope = and(concat(
    selectedCategoryFilters,
    selectedPriceFilters
));

Query priceScope = and(concat(
    selectedCategoryFilters,
    selectedBrandFilters
));

Query postFilter = and(concat(
    selectedCategoryFilters,
    selectedBrandFilters,
    selectedPriceFilters
));

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(baseQuery)
    .withFilter(postFilter)
    .withPageable(PageRequest.of(criteria.page(), criteria.size()))
    .withAggregation(
        "category_scope",
        termsFacet(categoryScope, "category", 30)
    )
    .withAggregation(
        "brand_scope",
        termsFacet(brandScope, "brand", 30)
    )
    .withAggregation(
        "price_scope",
        priceRangeFacet(priceScope)
    )
    .build();
~~~

Trong đoạn trên, các danh sách selectedCategoryFilters, selectedBrandFilters và selectedPriceFilters được tạo từ DTO đã validate. Hàm concat chỉ ghép các query có mặt. Hàm and trả match_all khi danh sách rỗng.

NativeQueryBuilder có các phương thức riêng cho withQuery, withFilter và withAggregation. Trong NativeQuery, withFilter biểu diễn post-filter của Search API. Đặt nhầm selected facets vào withQuery sẽ làm chúng giới hạn aggregation, khiến facet counts thay đổi theo cách khác với thiết kế self-excluding.

## 19. Tách service tạo query khỏi service chuyển kết quả

Không nên gom toàn bộ việc parse request, xây DSL, gọi Elasticsearch và chuyển aggregation vào controller.

Có thể chia trách nhiệm:

- ProductSearchCriteria: dữ liệu filter đã được validate.
- ProductQueryFactory: tạo base query, post-filter và aggregation scopes.
- ProductSearchService: gọi ElasticsearchOperations.
- FacetMapper: chuyển aggregation buckets thành DTO.
- ProductSearchResponse: cấu trúc trả về cho API.

Ví dụ response DTO:

~~~java
import java.util.List;

public record ProductSearchResponse(
    List<Product> items,
    long totalHits,
    List<FacetOption> categories,
    List<FacetOption> brands,
    List<PriceFacetOption> priceRanges
) {
}

public record FacetOption(
    String value,
    long count
) {
}

public record PriceFacetOption(
    String key,
    long count,
    Double from,
    Double to
) {
}
~~~

Service có thể thực hiện:

~~~java
public ProductSearchResponse search(ProductSearchCriteria criteria) {
    NativeQuery query = queryFactory.build(criteria, currentTenantId());

    SearchHits<Product> hits =
        operations.search(query, Product.class);

    List<Product> products = hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();

    FacetResult facets = facetMapper.map(hits.getAggregations());

    return new ProductSearchResponse(
        products,
        hits.getTotalHits(),
        facets.categories(),
        facets.brands(),
        facets.priceRanges()
    );
}
~~~

FacetMapper chịu trách nhiệm xử lý aggregation names và typed variants. Nếu aggregation không có trong response, cần báo lỗi hoặc dùng giá trị mặc định có chủ đích. Không ép kiểu một aggregation terms thành range hoặc ngược lại.

Nếu ứng dụng dùng reactive stack, có thể dùng ReactiveElasticsearchOperations và trả publisher. Phần tạo query và định nghĩa aggregation vẫn tương tự; chỉ khác API thực thi và kiểu kết quả. Không gọi block trong WebFlux request path để biến reactive operation thành đồng bộ.

## 20. Tối ưu số lượng bucket và chi phí aggregation

Faceted search thường chạy mỗi lần người dùng đổi một filter. Một request có thể chứa nhiều aggregation, nên số bucket và phạm vi document cần được kiểm soát.

Một số nguyên tắc:

- Giới hạn size của terms aggregation theo số lựa chọn UI thực sự hiển thị.
- Dùng keyword hoặc numeric fields có doc values.
- Giới hạn tập nền bằng tenant, active, quyền truy cập và text query.
- Không tạo aggregation trên field text nếu chưa có keyword subfield.
- Dùng range aggregation cho khoảng giá có ý nghĩa nghiệp vụ.
- Dùng filters aggregation khi danh sách lựa chọn cố định và cần cả bucket 0.
- Tránh lồng nhiều tầng terms aggregation có cardinality cao nếu UI không cần.
- Cân nhắc cache kết quả facet khi query và dữ liệu ít thay đổi.

Không đặt size quá lớn chỉ để bảo đảm mọi category đều xuất hiện. Nếu danh mục có hàng nghìn giá trị, hãy lấy catalog từ nguồn quản lý danh mục và dùng aggregation cho số lượng hoặc phân trang riêng cho facet options.

Nếu muốn bucket theo thứ tự nghiệp vụ như category priority, không dựa vào thứ tự mặc định của terms aggregation. Lấy bucket counts rồi sắp xếp theo thứ tự catalog trong ứng dụng, hoặc dùng filters aggregation có key rõ ràng cho tập nhỏ.

## 21. Chọn chính xác semantics của giá và bucket

Giá là một trong những chỗ dễ tạo lỗi nhất vì filter slider và price facet có thể sử dụng hai quy tắc biên khác nhau.

Giả sử UI có ba lựa chọn:

| Nhãn | Điều kiện |
|---|---|
| Dưới 500.000 | price < 500.000 |
| 500.000 đến dưới 2.000.000 | 500.000 <= price < 2.000.000 |
| Từ 2.000.000 | price >= 2.000.000 |

Các điều kiện trên không chồng lấn và không bỏ sót giá trị.

Nếu UI cho phép nhập min và max tùy ý, query slider có thể dùng gte và lte để bao gồm cả hai biên. Cần ghi rõ contract này trong API để front-end và back-end không diễn giải khác nhau.

Không lấy số bucket làm min/max slider nếu các sản phẩm thiếu price hoặc có giá trị bất thường. Có thể dùng min/max aggregation riêng, kèm giới hạn nghiệp vụ và validation.

Đối với tiền tệ, định dạng số chỉ thực hiện ở UI hoặc tầng presentation. Elasticsearch lưu số nguyên hoặc scaled numeric để so sánh và aggregation ổn định.

## 22. Kiểm thử filter và facet counts

Có thể kiểm tra query factory bằng unit test, nhưng để xác nhận mapping, query DSL và aggregation thực sự hoạt động, cần integration test với Elasticsearch.

Dùng một dataset nhỏ có số lượng biết trước:

| ID | Category | Brand | Price | Active |
|---|---|---|---:|---|
| p-1 | audio | Acme | 1.200.000 | true |
| p-2 | audio | Acme | 1.800.000 | true |
| p-3 | audio | Nova | 850.000 | true |
| p-4 | computers | Acme | 1.900.000 | true |
| p-5 | computers | Nova | 4.200.000 | true |
| p-6 | accessories | Acme | 650.000 | true |
| p-7 | audio | Acme | 3.200.000 | true |
| p-8 | audio | Acme | 1.500.000 | false |

Test case nên xác nhận:

1. Chỉ active products được tính trong base query.
2. Chọn audio và computers trả đúng các sản phẩm thuộc một trong hai category.
3. Chọn nhiều brand có semantics OR.
4. minPrice và maxPrice áp dụng đúng biên.
5. post_filter lọc hits nhưng không làm thay đổi aggregation scope.
6. category facet bỏ qua category selection nhưng vẫn áp dụng brand và price.
7. brand facet bỏ qua brand selection nhưng vẫn áp dụng category và price.
8. price facet bỏ qua price selection nhưng vẫn áp dụng category và brand.
9. Một bucket không có sản phẩm được biểu diễn theo đúng contract UI.
10. Tenant filter không bị bỏ qua ở bất kỳ aggregation nào.

Ví dụ kiểm tra kết quả query:

~~~java
@Test
void shouldReturnHitsAndSelfExcludingCategoryCounts() {
    ProductSearchCriteria criteria = new ProductSearchCriteria(
        List.of("audio"),
        List.of("Acme"),
        500000L,
        2000000L,
        null,
        0,
        20
    );

    ProductSearchResponse response = searchService.search(criteria);

    assertThat(response.items())
        .extracting(Product::getId)
        .containsExactlyInAnyOrder("p-1", "p-2");

    assertThat(response.categories())
        .contains(
            new FacetOption("audio", 2),
            new FacetOption("computers", 1),
            new FacetOption("accessories", 1)
        );
}
~~~

Test trên giả định dataset đã được index và refresh trước khi chạy search. Với integration test, tạo index/mapping, seed document, refresh rồi mới gọi service. Không dùng Thread.sleep để chờ dữ liệu searchable.

Nếu test chỉ kiểm tra query factory, có thể kiểm tra các danh sách filter được tạo đúng mà không cần container. Tuy nhiên, test đó không chứng minh Elasticsearch hiểu query và aggregation theo đúng semantics.

## 23. Những lỗi thường gặp khi triển khai faceted search

**Đưa tất cả filter vào query.bool.filter.** Hits và aggregations đều bị giới hạn bởi tất cả filter. Category facet có thể chỉ còn category đang chọn.

**Dùng post_filter nhưng mong aggregation cũng bị lọc.** post_filter chỉ thu hẹp hits sau aggregation. Nếu muốn facet counts tôn trọng một số filter khác, phải tạo filter aggregation scope riêng.

**Để tenant filter trong post_filter.** Aggregations chạy trước post_filter và có thể thống kê dữ liệu ngoài tenant. Tenant và quyền truy cập phải được áp dụng trong base query hoặc từng scope tương đương.

**Nhầm OR trong cùng facet với AND giữa các facet.** Nhiều category thường dùng terms query; category kết hợp brand và price bằng AND.

**Dùng term query trên field text.** Full-text mapping phân tích chuỗi. Bộ lọc chính xác nên dùng keyword field.

**Lưu giá thành chuỗi đã định dạng.** Range query và numeric aggregation cần field số.

**Để khoảng giá chồng lấn hoặc hở biên.** Một sản phẩm có thể bị đếm hai lần hoặc không xuất hiện trong bucket nào. Quy ước from inclusive, to exclusive cần được phản ánh trong nhãn UI.

**Cho rằng terms aggregation luôn trả mọi giá trị.** Terms thường trả top buckets theo size. Dùng filters aggregation hoặc catalog service nếu cần danh sách facet cố định.

**Dùng size của search hits để điều khiển số facet options.** Search size và terms aggregation size là hai tham số độc lập.

**Tạo quá nhiều aggregation không cần thiết.** Mỗi facet scope có thể tăng công việc của cluster. Chỉ tính những facet UI đang hiển thị hoặc thật sự cần.

**Dùng global aggregation mà quên tenant filter.** Global aggregation bỏ qua top-level query. Nếu dùng, phải tái áp dụng đầy đủ phạm vi dữ liệu và bảo mật.

**Trả raw Elasticsearch aggregation object ra API.** Điều này làm contract của ứng dụng phụ thuộc sâu vào client library. Chuyển kết quả thành DTO ổn định.

**Không kiểm tra dữ liệu thiếu field.** Document không có category, brand hoặc price có thể bị bỏ khỏi bucket. Hãy quyết định có cần bucket "Chưa phân loại" hay không.

**Không giới hạn input.** Một request với hàng nghìn category hoặc page size rất lớn có thể làm query nặng và response quá lớn. Validate và giới hạn ở server.

**Tính facet counts bằng nhiều request rời rạc.** Có thể tạo ra nhiều round trip và các con số từ những thời điểm dữ liệu khác nhau. Khi phù hợp, gộp hits và aggregations vào một Search API request.

## 24. Quy trình xây dựng một endpoint faceted search

Có thể triển khai theo trình tự:

1. Xác định các field có thể lọc và mapping phù hợp.
2. Thiết kế DTO cho category, brand, price, trạng thái, page và sort.
3. Validate input, chuẩn hóa giá trị và giới hạn page size.
4. Tạo base query chứa tenant, quyền truy cập, active và từ khóa nền.
5. Tạo selected facet filters cho category, brand và price.
6. Đặt toàn bộ selected facet filters vào post_filter để lọc hits.
7. Tạo category aggregation scope bỏ category filter.
8. Tạo brand aggregation scope bỏ brand filter.
9. Tạo price aggregation scope bỏ price filter.
10. Thêm terms aggregation cho category và brand.
11. Thêm range aggregation cho khoảng giá.
12. Gửi một NativeQuery qua ElasticsearchOperations.
13. Đọc hits, total hits và aggregations từ SearchHits.
14. Chuyển bucket thành DTO của ứng dụng.
15. Kiểm thử từng filter và semantics của từng facet với Elasticsearch thật.
16. Theo dõi latency và giới hạn bucket khi đưa endpoint vào production.

## Kết luận

Một endpoint faceted search cần kết hợp ba phần: filter cho danh sách document, aggregation để đếm lựa chọn và quy tắc xác định tập document cho từng facet. Category và brand thường dùng terms query; khoảng giá dùng range query. Terms aggregation tạo số lượng theo giá trị phân loại, còn range aggregation chia giá thành những dải có ranh giới rõ ràng.

Trong Elasticsearch, bool.filter tác động đến cả hits và aggregations. post_filter chỉ tác động đến hits sau khi aggregation đã chạy. Với giao diện cần self-excluding facets, hãy giữ tenant, trạng thái và điều kiện nền trong query; đặt toàn bộ lựa chọn facet vào post_filter; sau đó tạo một filter aggregation scope cho mỗi facet để áp dụng tất cả selected filters ngoại trừ chính filter của facet đó.

Spring Data Elasticsearch NativeQueryBuilder hỗ trợ kết hợp withQuery, withFilter và withAggregation trong một request. SearchHits cung cấp hits, total count và aggregation container. Chuyển aggregation buckets thành DTO của ứng dụng để controller và giao diện chỉ phụ thuộc vào contract nghiệp vụ. Khi mapping field, ranh giới giá và semantics OR/AND được thiết kế nhất quán, faceted search sẽ trả về cả danh sách phù hợp lẫn số lượng facet có ý nghĩa cho thao tác lọc tiếp theo.

## Tài liệu tham khảo

- [Elasticsearch — Filter search results and post_filter](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/filter-search-results)
- [Elasticsearch — Boolean query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-bool-query)
- [Elasticsearch — Terms aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-terms-aggregation)
- [Elasticsearch — Range aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-range-aggregation)
- [Elasticsearch — Filters aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-filters-aggregation)
- [Elasticsearch — Aggregations](https://www.elastic.co/docs/explore-analyze/query-filter/aggregations)
- [Elasticsearch Java API Client — Aggregations](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/aggregations)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — NativeQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch — ElasticsearchAggregations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchAggregations.html)
