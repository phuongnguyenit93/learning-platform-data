# Phân biệt `filter` và `post_filter` khi tạo bộ lọc thống kê

Trong trang tìm kiếm sản phẩm, người dùng thường vừa xem danh sách kết quả vừa chọn các bộ lọc như danh mục, thương hiệu, màu sắc hoặc khoảng giá. Bên cạnh danh sách sản phẩm, giao diện còn cần thống kê số lượng theo từng giá trị để hiển thị facet, ví dụ “Accessories (120)”, “Office (85)” hoặc “Acme (70)”.

Elasticsearch có hai vị trí lọc dễ bị nhầm lẫn:

- `bool.filter` nằm bên trong phần `query`: giới hạn tập document được dùng cho cả kết quả tìm kiếm và aggregation.
- `post_filter` nằm ở cấp cao nhất của search request: lọc danh sách hit sau khi aggregation đã được tính, vì vậy không làm thay đổi các bucket count.

Chọn đúng vị trí quyết định con số thống kê có phản ánh bộ lọc người dùng đang chọn hay vẫn hiển thị các lựa chọn thay thế. Đây là nền tảng của faceted search và disjunctive faceting.

## 1. Ba khái niệm filter cần phân biệt

Trong Elasticsearch, từ “filter” có thể chỉ ba cơ chế khác nhau:

| Cơ chế | Vị trí trong request | Tác động tới hits | Tác động tới aggregation |
| --- | --- | --- | --- |
| `bool.filter` | Bên trong `query.bool` | Có | Có; aggregation chỉ nhận document đã qua query. |
| `post_filter` | Cùng cấp với `query` và `aggs` | Có | Không; aggregation đã được tính trước khi post-filter lọc hits. |
| `filter` aggregation | Bên trong `aggs.<name>.filter` | Không trực tiếp lọc hits | Có; giới hạn document của aggregation đó và các sub-aggregation bên trong. |

Ba cơ chế này có thể cùng xuất hiện trong một request, nhưng chúng phục vụ các mục đích khác nhau.

### 1.1. `bool.filter`

`bool.filter` là một clause của Query DSL. Elasticsearch kiểm tra document có thỏa điều kiện hay không mà không tính relevance score từ clause đó. Vì điều kiện nằm trong query chính, nó giới hạn tập document đầu vào cho cả hits và aggregation.

Các điều kiện thường phù hợp với `bool.filter` gồm:

- Tenant hoặc phạm vi dữ liệu mà người dùng được phép truy cập.
- Trạng thái bắt buộc, ví dụ chỉ sản phẩm đang hoạt động.
- Danh mục hoặc loại document nếu muốn thống kê cũng bị giới hạn theo điều kiện đó.
- Khoảng giá, khoảng ngày hoặc điều kiện địa lý không cần đóng góp vào score.

### 1.2. `post_filter`

`post_filter` là một phần riêng của search request, nằm ngoài object `query`. Nó chỉ lọc hits được trả về sau khi Elasticsearch đã tính aggregation trên tập document phù hợp với query chính.

Điều này hữu ích khi giao diện muốn:

- Chỉ hiển thị các sản phẩm thỏa những facet người dùng đã chọn.
- Vẫn hiển thị số lượng của các lựa chọn facet khác để người dùng có thể thay đổi hoặc mở rộng lựa chọn.
- Tính thống kê trên tập cơ sở trước khi áp dụng lựa chọn facet hiện tại.

`post_filter` cũng không tính relevance score. Tuy nhiên, điểm khác biệt quan trọng của nó so với `bool.filter` là phạm vi tác động tới aggregation.

### 1.3. `filter` aggregation

`filter` aggregation tạo một phạm vi document riêng cho một aggregation. Các sub-aggregation bên trong chỉ tính trên document thỏa điều kiện của filter aggregation đó.

Ví dụ có thể tạo aggregation `categories` chỉ thống kê các sản phẩm của thương hiệu Acme, trong khi aggregation `brands` lại thống kê theo một phạm vi khác. Cơ chế này rất hữu ích khi cần disjunctive facet counts, tức mỗi facet bỏ qua lựa chọn của chính nó nhưng vẫn tôn trọng các facet khác.

## 2. `bool.filter` ảnh hưởng cả hits và thống kê

Giả sử index `products` có các field:

| Field | Mapping | Ý nghĩa |
| --- | --- | --- |
| `name` | `text` | Tên sản phẩm để tìm kiếm toàn văn. |
| `tenantId` | `keyword` | Phạm vi tenant. |
| `active` | `boolean` | Sản phẩm có đang hoạt động hay không. |
| `category` | `keyword` | Danh mục sản phẩm. |
| `brand` | `keyword` | Thương hiệu. |
| `color` | `keyword` | Màu sắc. |
| `price` | `long` | Giá sản phẩm. |

Request tìm sản phẩm có tên liên quan đến `wireless`, thuộc tenant `tenant-42`, đang hoạt động và có giá trong khoảng 100–500:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless"
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "active": true } },
        {
          "range": {
            "price": {
              "gte": 100,
              "lte": 500
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
        "size": 20
      }
    },
    "brands": {
      "terms": {
        "field": "brand",
        "size": 20
      }
    }
  }
}
~~~

Trong request này, các aggregation chỉ thống kê những document đã thỏa:

1. Tên sản phẩm khớp truy vấn `wireless`.
2. Thuộc tenant `tenant-42`.
3. Đang hoạt động.
4. Giá nằm trong khoảng 100–500.

Nếu người dùng chưa chọn danh mục hoặc thương hiệu, đây thường là hành vi mong muốn. Mọi thống kê đều phản ánh cùng tập kết quả cơ sở.

Nhưng nếu thêm `category = ACCESSORIES` vào `bool.filter`, aggregation `categories` cũng chỉ nhìn thấy sản phẩm thuộc `ACCESSORIES`. Các bucket danh mục khác biến mất hoặc không còn số lượng có ý nghĩa để người dùng chuyển sang danh mục khác.

## 3. `post_filter` giữ thống kê độc lập với facet đang chọn

Giả sử giao diện có bộ lọc danh mục và thương hiệu. Người dùng chọn:

- Category: `ACCESSORIES`.
- Brand: `ACME`.

Mục tiêu là danh sách hits chỉ chứa sản phẩm Accessories của Acme, nhưng thống kê danh mục và thương hiệu vẫn được tính trên tập cơ sở `wireless` trong tenant hiện tại, trước khi áp dụng hai lựa chọn facet.

Đưa các điều kiện chung vào query, còn lựa chọn facet vào `post_filter`:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "wireless" } }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "active": true } }
      ]
    }
  },
  "post_filter": {
    "bool": {
      "filter": [
        { "term": { "category": "ACCESSORIES" } },
        { "term": { "brand": "ACME" } }
      ]
    }
  },
  "aggs": {
    "categories": {
      "terms": { "field": "category", "size": 20 }
    },
    "brands": {
      "terms": { "field": "brand", "size": 20 }
    }
  }
}
~~~

Kết quả có hai phạm vi:

- **Hits:** chỉ có sản phẩm khớp `wireless`, thuộc tenant `tenant-42`, đang hoạt động, thuộc category `ACCESSORIES` và brand `ACME`.
- **Aggregations:** thống kê trên sản phẩm khớp `wireless`, thuộc tenant `tenant-42` và đang hoạt động; chúng chưa bị giới hạn bởi category và brand trong `post_filter`.

Đây là điểm khác biệt cốt lõi: `post_filter` không làm thay đổi bucket counts. Nếu mục tiêu là hiển thị các lựa chọn facet thay thế, đây thường là điều cần thiết.

## 4. Ví dụ kết quả và cách giao diện sử dụng

Giả sử tập cơ sở sau query có thống kê:

| Category | Số sản phẩm |
| --- | ---: |
| ACCESSORIES | 120 |
| OFFICE | 85 |
| HOME | 30 |

| Brand | Số sản phẩm |
| --- | ---: |
| ACME | 70 |
| CONTOSO | 65 |
| NORTHWIND | 40 |

Người dùng chọn `ACCESSORIES` và `ACME`. Với `post_filter`, hits chỉ còn các sản phẩm thỏa cả hai lựa chọn, nhưng aggregation vẫn trả các con số cơ sở như trên.

Giao diện có thể tiếp tục hiển thị:

- ACCESSORIES (120)
- OFFICE (85)
- HOME (30)
- ACME (70)
- CONTOSO (65)
- NORTHWIND (40)

Các con số trên không phải số lượng sau khi áp dụng toàn bộ facet đang chọn. Chúng là số lượng trước `post_filter`. Nếu sản phẩm cần hiển thị số lượng theo các facet khác trong khi vẫn tôn trọng những lựa chọn còn lại, cần dùng disjunctive facet aggregation ở phần tiếp theo.

## 5. Disjunctive faceting: mỗi thống kê bỏ qua chính facet của nó

Trong giao diện thương mại điện tử, hành vi thường mong muốn tinh tế hơn việc mọi aggregation bỏ qua tất cả facet được chọn.

Ví dụ người dùng đang chọn:

- Category = `ACCESSORIES`.
- Brand = `ACME`.
- Color = `BLACK`.

Khi hiển thị thống kê category, ta muốn giữ brand và color nhưng bỏ qua category đang chọn. Khi hiển thị thống kê brand, ta muốn giữ category và color nhưng bỏ qua brand. Tương tự, thống kê color giữ category và brand nhưng bỏ qua color.

Đó là **disjunctive faceting**:

| Aggregation cần tính | Những lựa chọn được áp dụng | Lựa chọn được bỏ qua |
| --- | --- | --- |
| `categories` | Brand = ACME, Color = BLACK | Category = ACCESSORIES |
| `brands` | Category = ACCESSORIES, Color = BLACK | Brand = ACME |
| `colors` | Category = ACCESSORIES, Brand = ACME | Color = BLACK |

Có thể triển khai bằng một `filter` aggregation cho từng facet. Mỗi filter aggregation áp dụng tất cả selected facet filters ngoại trừ field mà nó đang thống kê.

### 5.1. Query và post_filter cho hits

Query chính chứa tìm kiếm văn bản và các điều kiện bắt buộc toàn cục:

~~~json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "wireless" } }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "active": true } }
      ]
    }
  },
  "post_filter": {
    "bool": {
      "filter": [
        { "term": { "category": "ACCESSORIES" } },
        { "term": { "brand": "ACME" } },
        { "term": { "color": "BLACK" } }
      ]
    }
  }
~~~

Hits chỉ chứa document thỏa tất cả ba facet đã chọn. Các aggregation được khai báo tiếp ở cùng cấp với `query` và `post_filter`.

### 5.2. Aggregation category bỏ qua category đã chọn

Aggregation `categories` áp dụng brand và color, nhưng không áp dụng category:

~~~json
"aggs": {
  "categories": {
    "filter": {
      "bool": {
        "filter": [
          { "term": { "brand": "ACME" } },
          { "term": { "color": "BLACK" } }
        ]
      }
    },
    "aggs": {
      "values": {
        "terms": {
          "field": "category",
          "size": 20
        }
      }
    }
  }
}
~~~

Kết quả `categories.values` cho biết các danh mục có sản phẩm thuộc brand ACME và màu BLACK trong tập cơ sở. Người dùng có thể xem danh mục khác và chuyển lựa chọn mà vẫn giữ hai điều kiện brand/color.

### 5.3. Aggregation brand bỏ qua brand đã chọn

~~~json
"brands": {
  "filter": {
    "bool": {
      "filter": [
        { "term": { "category": "ACCESSORIES" } },
        { "term": { "color": "BLACK" } }
      ]
    }
  },
  "aggs": {
    "values": {
      "terms": {
        "field": "brand",
        "size": 20
      }
    }
  }
}
~~~

### 5.4. Aggregation color bỏ qua color đã chọn

~~~json
"colors": {
  "filter": {
    "bool": {
      "filter": [
        { "term": { "category": "ACCESSORIES" } },
        { "term": { "brand": "ACME" } }
      ]
    }
  },
  "aggs": {
    "values": {
      "terms": {
        "field": "color",
        "size": 20
      }
    }
  }
}
~~~

Có thể đặt cả ba aggregation trong cùng object `aggs` của một request. Mỗi aggregation có filter riêng nên các số lượng được tính theo đúng tập điều kiện của facet tương ứng.

## 6. Phân biệt filter aggregation và post_filter

`post_filter` và `filter` aggregation thường được dùng cùng nhau nhưng không thay thế nhau:

- `post_filter` quyết định document nào xuất hiện trong `hits`.
- `filter` aggregation quyết định document nào được tính trong một nhánh thống kê cụ thể.

Ví dụ, một request có `post_filter` category `ACCESSORIES`, đồng thời có aggregation `brands` với filter category `ACCESSORIES` và color `BLACK`. `post_filter` không ảnh hưởng aggregation; filter bên trong `brands` mới xác định tập document được thống kê cho nhánh đó.

Có thể dùng filter aggregation ngay cả khi không có post_filter, ví dụ dashboard cần nhiều nhóm thống kê trên các tập điều kiện khác nhau trong cùng một request.

## 7. Khi nào cần `global` aggregation?

`global` aggregation tạo một phạm vi thống kê bỏ qua query ở cấp cao nhất. Nó có thể hữu ích khi cần thống kê trên toàn bộ document của index, độc lập với full-text query hoặc query filter.

Ví dụ:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "aggs": {
    "all_products": {
      "global": {},
      "aggs": {
        "by_category": {
          "terms": {
            "field": "category"
          }
        }
      }
    }
  }
}
~~~

Aggregation `all_products` bỏ qua query `match` và thống kê trên toàn bộ document của index. Điều này cũng có nghĩa nó bỏ qua các query filters như tenant, quyền truy cập, trạng thái hoặc phạm vi dữ liệu.

**Không đặt điều kiện bảo mật chỉ trong query rồi dùng global aggregation mà quên áp dụng lại điều kiện đó bên trong aggregation.** Nếu aggregation trả bucket hoặc số lượng thuộc tenant khác, thông tin có thể bị lộ dù hits đã được giới hạn đúng.

Ví dụ khi dùng global aggregation trong môi trường multi-tenant, phải đưa tenant scope vào filter aggregation bên trong global:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } }
      ]
    }
  },
  "aggs": {
    "all_products_for_tenant": {
      "global": {},
      "aggs": {
        "tenant_scope": {
          "filter": {
            "term": { "tenantId": "tenant-42" }
          },
          "aggs": {
            "categories": {
              "terms": { "field": "category" }
            }
          }
        }
      }
    }
  }
}
~~~

Trong ví dụ, tenant filter được lặp lại bên trong phạm vi global để bảo đảm thống kê vẫn giới hạn theo tenant. Cần áp dụng tương tự với mọi điều kiện authorization bắt buộc.

## 8. Dùng `NativeQuery` trong Spring Data Elasticsearch

`NativeQuery` hỗ trợ các query builder của Elasticsearch Java API Client, bao gồm query, aggregation và filter. Trong API Spring Data Elasticsearch hiện đại, `NativeQueryBuilder.withFilter(...)` thiết lập filter cấp search request tương ứng với `post_filter`; còn `withQuery(...)` thiết lập query chính. Hãy kiểm tra API của phiên bản Spring Data Elasticsearch mà dự án đang sử dụng.

Ví dụ dưới đây giữ tenant và trạng thái trong query, còn category và brand do người dùng chọn được đặt trong post-filter. Aggregation category và brand được tính trên tập cơ sở trước post-filter:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("name")
                        .query("wireless")))
                .filter(f -> f.term(t -> t
                        .field("tenantId")
                        .value(FieldValue.of("tenant-42"))))
                .filter(f -> f.term(t -> t
                        .field("active")
                        .value(FieldValue.of(true))))))
        .withFilter(f -> f.bool(b -> b
                .filter(x -> x.term(t -> t
                        .field("category")
                        .value(FieldValue.of("ACCESSORIES"))))
                .filter(x -> x.term(t -> t
                        .field("brand")
                        .value(FieldValue.of("ACME"))))))
        .withAggregation("categories", Aggregation.of(a -> a
                .terms(t -> t.field("category").size(20))))
        .withAggregation("brands", Aggregation.of(a -> a
                .terms(t -> t.field("brand").size(20))))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
~~~

Trong đoạn code:

- `withQuery(...)` tạo query chính; tenant và active nằm trong `bool.filter`, nên chúng giới hạn cả hits lẫn aggregation.
- `withFilter(...)` đặt các facet người dùng chọn vào top-level post-filter, nên chúng chỉ giới hạn hits.
- `withAggregation(...)` khai báo thống kê category và brand.
- `operations.search(...)` thực thi request và trả `SearchHits` cùng metadata aggregation.

Để thực hiện disjunctive faceting, định nghĩa mỗi aggregation bằng `Aggregation.of(...)` với một `filter` aggregation bao quanh `terms` aggregation, tương tự các ví dụ REST API ở phần trước. Như vậy, từng facet có thể bỏ qua lựa chọn của chính nó và áp dụng các lựa chọn còn lại.

### 8.1. Đọc aggregation từ kết quả Spring Data

Kết quả `SearchHits<T>` chứa danh sách hit và phần aggregation response. API truy cập và kiểu container cụ thể phụ thuộc phiên bản Spring Data Elasticsearch; hãy dùng `SearchHits.getAggregations()` cùng các kiểu aggregation result tương ứng của dependency dự án.

Khi parse kết quả, cần phân biệt bucket count của `categories`, `brands` và các bucket `values` bên trong filter aggregation. Với filter aggregation, `docCount` ở cấp filter là số document trong phạm vi filter; các bucket terms con mới là số lượng theo từng giá trị facet.

Không lấy tổng số hits đã qua `post_filter` để thay thế số lượng của aggregation. Hai con số đại diện cho hai tập document khác nhau.

## 9. Ví dụ đầy đủ với filter aggregation cho nhiều facet

Request sau minh họa một tập cơ sở, các facet được chọn và ba nhánh thống kê độc lập. Query chính giới hạn tenant và trạng thái; post-filter giới hạn hits theo category, brand và color; mỗi aggregation bỏ qua filter của chính field đang thống kê:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "wireless" } }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "active": true } }
      ]
    }
  },
  "post_filter": {
    "bool": {
      "filter": [
        { "term": { "category": "ACCESSORIES" } },
        { "term": { "brand": "ACME" } },
        { "term": { "color": "BLACK" } }
      ]
    }
  },
  "aggs": {
    "categories": {
      "filter": {
        "bool": {
          "filter": [
            { "term": { "brand": "ACME" } },
            { "term": { "color": "BLACK" } }
          ]
        }
      },
      "aggs": {
        "values": {
          "terms": { "field": "category", "size": 20 }
        }
      }
    },
    "brands": {
      "filter": {
        "bool": {
          "filter": [
            { "term": { "category": "ACCESSORIES" } },
            { "term": { "color": "BLACK" } }
          ]
        }
      },
      "aggs": {
        "values": {
          "terms": { "field": "brand", "size": 20 }
        }
      }
    },
    "colors": {
      "filter": {
        "bool": {
          "filter": [
            { "term": { "category": "ACCESSORIES" } },
            { "term": { "brand": "ACME" } }
          ]
        }
      },
      "aggs": {
        "values": {
          "terms": { "field": "color", "size": 20 }
        }
      }
    }
  }
}
~~~

Request này tạo ba tập thống kê:

1. `categories.values`: các category trong tập cơ sở, sau khi áp dụng brand ACME và color BLACK.
2. `brands.values`: các brand trong tập cơ sở, sau khi áp dụng category ACCESSORIES và color BLACK.
3. `colors.values`: các màu trong tập cơ sở, sau khi áp dụng category ACCESSORIES và brand ACME.

Các hits vẫn bị giới hạn bởi cả ba lựa chọn facet nhờ `post_filter`. Những bucket counts cho phép giao diện hiển thị các lựa chọn khác theo các facet còn lại.

## 10. Multi-select facet: OR hay AND?

Khi người dùng chọn nhiều giá trị trong cùng một facet, cần xác định semantics trước khi dựng query.

Ví dụ người dùng chọn hai category `ACCESSORIES` và `OFFICE`:

- Nếu chỉ cần sản phẩm thuộc một trong hai category, dùng `terms` query. Đây là OR giữa các giá trị trong cùng field.
- Nếu document phải thỏa cả hai điều kiện, cần một mô hình dữ liệu và cách truy vấn khác phù hợp với semantics AND; không thể giả định `terms` tự tạo AND.

Ví dụ OR:

~~~json
{
  "terms": {
    "category": ["ACCESSORIES", "OFFICE"]
  }
}
~~~

Khi xây dựng disjunctive facet, filter cho một facet phải tái tạo đúng semantics multi-select của các facet khác. Nếu một facet dùng OR trong nhóm giá trị, hãy giữ OR đó trong filter aggregation. Nếu nghiệp vụ yêu cầu AND giữa các giá trị, biểu diễn từng điều kiện riêng và kiểm tra mapping, đặc biệt khi field là mảng.

## 11. Các điều kiện bắt buộc phải nằm trong query

Không nên đưa mọi điều kiện vào `post_filter`. Những điều kiện có ý nghĩa bảo vệ dữ liệu hoặc xác định tập thống kê toàn cục phải được đặt ở query chính.

Ví dụ:

- Tenant scope.
- Quyền truy cập theo người dùng hoặc tổ chức.
- Phạm vi dữ liệu được phép xem.
- Trạng thái soft-delete hoặc điều kiện loại bỏ document không được phép xuất hiện.

Nếu chỉ đặt tenant filter trong `post_filter`, hits có thể được giới hạn theo tenant nhưng aggregation vẫn đếm document của tenant khác. Bucket name và count cũng có thể tiết lộ sự tồn tại hoặc phân bố dữ liệu ngoài phạm vi.

Đưa tenant filter vào `query.bool.filter` giúp nó áp dụng cho cả hits và aggregation. Nếu có `global` aggregation, phải áp dụng lại tenant/authorization filter bên trong nhánh global vì global aggregation bỏ qua query chính.

## 12. Hiệu năng và độ chính xác của thống kê

Aggregation có thể tốn tài nguyên khi số lượng document hoặc cardinality của field lớn. Một số lưu ý:

- Chỉ tạo các aggregation mà giao diện thực sự cần.
- Dùng `size` hợp lý cho `terms` aggregation để giới hạn số bucket trả về.
- Với cardinality lớn hoặc cần duyệt bucket đầy đủ, cân nhắc `composite` aggregation và phân trang bằng `after_key`.
- `terms` aggregation phân tán trên nhiều shard có thể có sai số đếm do cơ chế chọn bucket ứng viên; xem `doc_count_error_upper_bound` và `sum_other_doc_count` khi cần đánh giá độ chính xác.
- Có thể điều chỉnh `shard_size` để cải thiện độ chính xác của terms aggregation, nhưng cần cân bằng với bộ nhớ và lượng dữ liệu truyền giữa shard và coordinating node.
- Hạn chế lồng quá nhiều tầng aggregation hoặc filter aggregation trùng lặp nếu không cần thiết.
- Đo request trên dữ liệu đại diện; số lượng bucket, số shard và phân bố term ảnh hưởng đáng kể tới chi phí.

`post_filter` không làm aggregation rẻ hơn: aggregation vẫn phải tính trên tập query cơ sở, thường là tập rộng hơn tập hits cuối cùng. Đây chính là lý do nó hữu ích cho faceted search, nhưng cũng là lý do cần kiểm soát kích thước tập cơ sở và số lượng aggregation.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Chọn category xong các category khác biến mất khỏi thống kê | Category filter được đặt trong `query.bool.filter`. | Chuyển lựa chọn facet sang `post_filter` hoặc dùng filter aggregation bỏ qua facet hiện tại. |
| Hits không bị giới hạn theo facet đã chọn | Chỉ đặt điều kiện trong aggregation filter. | Thêm các lựa chọn facet vào `post_filter` để lọc hits. |
| Tất cả facet counts bỏ qua mọi lựa chọn khác | Dùng một terms aggregation đơn giản cùng post_filter. | Dùng filter aggregation riêng cho từng facet để giữ các filter khác và bỏ qua filter của chính nó. |
| Thống kê có dữ liệu của tenant khác | Tenant chỉ nằm trong post_filter hoặc bị bỏ qua trong global aggregation. | Đưa tenant scope vào query và lặp lại trong nhánh global khi cần. |
| Aggregation không phản ánh khoảng giá hoặc full-text mong muốn | Điều kiện cần áp dụng cho tập cơ sở bị đặt nhầm ở post_filter. | Đưa điều kiện toàn cục vào query.bool.filter hoặc query chính. |
| Bucket count không bằng total hits | Aggregation và hits đang dùng phạm vi document khác nhau. | Xác định rõ query, post_filter và filter aggregation của từng nhánh. |
| Một số bucket terms bị thiếu hoặc count không chính xác tuyệt đối | `terms` aggregation có giới hạn bucket/shard candidate hoặc cardinality cao. | Kiểm tra error fields, size/shard_size hoặc dùng composite aggregation. |
| NativeQuery filter không có hành vi như mong đợi | Nhầm `withFilter` với `bool.filter` trong query. | Xác nhận request được sinh; `withFilter` là post-filter, còn bool.filter phải nằm trong query. |

## 14. Quy trình thiết kế bộ lọc thống kê

Khi xây dựng trang tìm kiếm có facet, hãy thực hiện theo trình tự:

1. Xác định tập cơ sở cho tìm kiếm: full-text query, tenant scope, authorization và các điều kiện toàn cục.
2. Đặt các điều kiện toàn cục vào `query`, dùng `bool.filter` cho điều kiện không cần relevance score.
3. Xác định các facet người dùng có thể chọn và semantics multi-select của từng facet.
4. Đặt các lựa chọn chỉ dùng để lọc hits vào top-level `post_filter`.
5. Nếu mọi aggregation cần thống kê trên cùng tập cơ sở, dùng terms aggregation trực tiếp.
6. Nếu mỗi facet cần bỏ qua lựa chọn của chính nó nhưng vẫn giữ lựa chọn facet khác, tạo filter aggregation riêng cho từng facet.
7. Chỉ dùng `global` aggregation khi thật sự cần bỏ qua query chính; áp dụng lại tenant và authorization filters bên trong nhánh global.
8. Kiểm tra hits và bucket counts trên dữ liệu mẫu có nhiều category/brand/color.
9. Đánh giá cardinality, số bucket, shard count và độ chính xác của terms aggregation.
10. Quan sát Query DSL được gửi để xác nhận vị trí của `query`, `post_filter` và `aggs`.

## 15. Tài liệu tham khảo

- [Elasticsearch — Filter search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/filter-search-results.html)
- [Elasticsearch — Query and filter context](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-filter-context.html)
- [Elasticsearch — Filter aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-filter-aggregation.html)
- [Elasticsearch — Global aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-global-aggregation.html)
- [Spring Data Elasticsearch — NativeQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

`bool.filter` giới hạn tập document cho cả hits và aggregation. Top-level `post_filter` chỉ lọc hits sau khi aggregation đã được tính. `filter` aggregation tạo phạm vi riêng cho từng nhánh thống kê. Kết hợp đúng ba cơ chế này cho phép xây dựng faceted search với số lượng phù hợp, đồng thời giữ tenant và authorization filters trong phạm vi thống kê an toàn.
