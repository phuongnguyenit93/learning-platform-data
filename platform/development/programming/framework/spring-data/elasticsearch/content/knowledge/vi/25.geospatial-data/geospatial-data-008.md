# Truy vấn bằng CriteriaQuery, NativeQuery hoặc client trực tiếp

Dữ liệu địa lý thường được dùng để trả lời những câu hỏi như: địa điểm nào nằm trong bán kính 5 km quanh người dùng, cửa hàng nào nằm trong một khu vực trên bản đồ, hoặc điểm giao hàng nào gần một tọa độ nhất. Elasticsearch hỗ trợ các kiểu dữ liệu và Query DSL chuyên dụng cho tọa độ, vùng địa lý và khoảng cách.

Trong Spring Data Elasticsearch, có thể xây dựng truy vấn địa lý bằng **CriteriaQuery** cho các điều kiện đơn giản được abstraction hỗ trợ, dùng **NativeQuery** khi cần kiểm soát Query DSL chi tiết, hoặc gọi trực tiếp **Elasticsearch Java API Client** khi cần sử dụng API cấp thấp hơn. Lựa chọn phụ thuộc vào độ phức tạp của query, mức độ cần tích hợp với mapping/conversion của Spring Data và khả năng kiểm soát request.

Bài học này dùng ví dụ ứng dụng tìm cửa hàng và điểm dịch vụ. Nội dung tập trung vào cách khai báo geo_point, truy vấn theo khoảng cách và vùng, sắp xếp theo khoảng cách, kết hợp filter nghiệp vụ và đọc kết quả trong Spring Data Elasticsearch.

## 1. Các kiểu dữ liệu địa lý trong Elasticsearch

Hai kiểu mapping thường gặp là:

- **geo_point**: một tọa độ địa lý, thường dùng cho vị trí cửa hàng, người dùng, trạm giao hàng hoặc thiết bị.
- **geo_shape**: một hình dạng địa lý như điểm, đường, polygon hoặc multi-shape, thường dùng cho vùng phục vụ, ranh giới hành chính hoặc khu vực giao hàng.

Chọn kiểu theo dữ liệu và nghiệp vụ. Nếu mỗi document chỉ có một vị trí và cần tìm theo bán kính hoặc khoảng cách, geo_point thường đủ. Nếu cần kiểm tra quan hệ giữa các vùng hoặc hình dạng phức tạp, cân nhắc geo_shape.

### geo_point

Một geo_point có thể được biểu diễn bằng nhiều định dạng. Dạng object thường dễ đọc nhất:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Một số định dạng khác được Elasticsearch hỗ trợ gồm:

~~~json
{
  "location": [106.7009, 10.7769]
}
~~~

~~~json
{
  "location": "10.7769,106.7009"
}
~~~

Lưu ý thứ tự tọa độ:

- Trong object, dùng tên rõ ràng lat và lon.
- Trong mảng tọa độ geo_point, thứ tự là [longitude, latitude].
- Trong chuỗi geo_point, định dạng là latitude,longitude.
- Khi dùng GeoJSON trong geo_shape, tọa độ theo chuẩn GeoJSON là [longitude, latitude].

Nhầm latitude và longitude là nguyên nhân phổ biến khiến truy vấn không lỗi nhưng tìm sai khu vực.

### geo_shape

geo_shape lưu hình dạng địa lý. Ví dụ polygon GeoJSON:

~~~json
{
  "deliveryArea": {
    "type": "polygon",
    "coordinates": [
      [
        [106.68, 10.77],
        [106.73, 10.77],
        [106.73, 10.81],
        [106.68, 10.81],
        [106.68, 10.77]
      ]
    ]
  }
}
~~~

Vòng tọa độ của polygon phải đóng bằng cách lặp lại điểm đầu ở cuối. Mỗi cặp tọa độ GeoJSON có thứ tự longitude rồi latitude.

## 2. Khai báo entity có vị trí địa lý

Spring Data Elasticsearch cung cấp kiểu GeoPoint và annotation @GeoPointField cho field geo_point.

Ví dụ entity cửa hàng:

~~~java
@Document(indexName = "stores")
public class Store {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Keyword)
    private String city;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @GeoPointField
    private GeoPoint location;
}
~~~

Có thể tạo tọa độ trong Java:

~~~java
GeoPoint location = new GeoPoint(10.7769, 106.7009);
~~~

Constructor GeoPoint của Spring Data nhận latitude trước rồi longitude. Khi chuyển sang GeoJSON hoặc mảng tọa độ, cần đổi thứ tự theo định dạng tương ứng.

Mapping Elasticsearch tương đương:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "city": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "active": {
        "type": "boolean"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

Nếu dùng @Field(type = FieldType.GeoPoint) thay cho @GeoPointField, hãy xác nhận annotation và converter phù hợp với kiểu property trong phiên bản Spring Data Elasticsearch đang dùng. Với Spring Data, @GeoPointField là cách khai báo chuyên biệt dễ nhận biết.

### Lưu tọa độ và cập nhật mapping

Field phải được mapping đúng kiểu trước khi index dữ liệu. Nếu một field đã được tạo thành keyword hoặc object, không thể đổi trực tiếp sang geo_point trên index hiện tại. Cần tạo index mới, khai báo mapping đúng, reindex hoặc ghi lại dữ liệu rồi chuyển alias/luồng truy cập.

Đối với dữ liệu nhập từ API, validate latitude trong khoảng -90 đến 90 và longitude trong khoảng -180 đến 180. Không chấp nhận tọa độ ngoài miền hợp lệ chỉ vì JSON có thể parse được.

## 3. Những truy vấn địa lý thường dùng

Elasticsearch cung cấp nhiều query type cho geo_point và geo_shape.

| Query | Mục đích | Ví dụ sử dụng |
|---|---|---|
| geo_distance | Tìm điểm trong một bán kính từ tọa độ | Cửa hàng trong 5 km |
| geo_bounding_box | Tìm điểm trong hình chữ nhật địa lý | Các địa điểm nằm trong vùng bản đồ đang hiển thị |
| geo_polygon | Tìm điểm nằm trong polygon | Các điểm bên trong khu vực được chọn |
| geo_shape | Kiểm tra quan hệ giữa điểm/hình dạng và vùng | Điểm thuộc vùng phục vụ hoặc hai vùng giao nhau |

Query phù hợp phụ thuộc kiểu mapping. Các query trên geo_point và geo_shape không thể thay thế tùy tiện cho nhau.

## 4. Truy vấn theo bán kính với geo_distance

geo_distance tìm document có vị trí nằm trong khoảng cách tối đa so với một điểm trung tâm.

Ví dụ tìm cửa hàng trong bán kính 5 km quanh một tọa độ:

~~~http
POST /stores/_search
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
~~~

distance nhận giá trị kèm đơn vị như 5km, 500m hoặc 3mi. Nên ghi đơn vị tường minh để query dễ đọc và tránh hiểu nhầm.

Có thể kết hợp query địa lý với filter nghiệp vụ bằng bool:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
          }
        },
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "status": "OPEN"
          }
        }
      ]
    }
  }
}
~~~

Trong ví dụ này, cửa hàng phải nằm trong bán kính và đồng thời đang active, có status là OPEN. Vì các điều kiện nằm trong filter context, chúng dùng để giới hạn tập kết quả thay vì cộng điểm relevance văn bản.

### Khoảng cách được tính như thế nào?

Elasticsearch hỗ trợ các cách tính khoảng cách địa lý. Với truy vấn khoảng cách, lựa chọn phổ biến là arc, tính theo cung trên bề mặt hình cầu và phù hợp cho nhiều use case. Một số API còn hỗ trợ lựa chọn plane, có thể nhanh hơn trong phạm vi nhỏ nhưng kém phù hợp hơn khi khoảng cách lớn hoặc khu vực rộng.

Không nên tự tính khoảng cách bằng phép trừ latitude/longitude trong Java rồi dùng kết quả như kilomet. Độ dài một độ kinh/vĩ thay đổi theo vị trí và phép tính phẳng không phản ánh đúng khoảng cách địa lý trên bề mặt Trái Đất.

## 5. Truy vấn trong vùng chữ nhật với geo_bounding_box

Khi người dùng kéo bản đồ và màn hình chỉ cần tải các điểm đang nằm trong khung nhìn, geo_bounding_box là lựa chọn phù hợp.

~~~http
POST /stores/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.72,
          "lon": 106.76
        }
      }
    }
  }
}
~~~

Query trả về các điểm nằm trong hình chữ nhật được xác định bởi hai góc. Tên top_left và bottom_right mô tả góc của bounding box; không nhầm chúng với thứ tự [lon, lat] của mảng GeoJSON.

Một bounding box thường phù hợp với viewport của bản đồ, nhưng không biểu diễn chính xác một vùng có ranh giới phức tạp. Nếu người dùng vẽ polygon hoặc cần xác định điểm nằm trong khu vực có hình dạng bất quy tắc, dùng geo_shape hoặc query polygon phù hợp.

### Bounding box qua kinh tuyến 180 độ

Với vùng gần đường đổi ngày quốc tế, bounding box có thể cắt qua kinh tuyến 180 độ. Đây là trường hợp đặc biệt cần kiểm tra kỹ dữ liệu, cách xác định góc và kết quả thực tế. Không nên áp dụng quy tắc so sánh longitude đơn giản trong Java để thay cho semantics của Elasticsearch.

## 6. Truy vấn vùng polygon và geo_shape

Với vùng đa giác, Elasticsearch có geo_polygon cho các trường hợp điểm và polygon đơn giản, tùy phiên bản và khả năng được hỗ trợ. Với hình dạng phong phú hơn, dùng field geo_shape và query geo_shape.

Ví dụ query điểm nằm trong polygon:

~~~json
{
  "query": {
    "geo_shape": {
      "deliveryArea": {
        "shape": {
          "type": "polygon",
          "coordinates": [
            [
              [106.68, 10.77],
              [106.73, 10.77],
              [106.73, 10.81],
              [106.68, 10.81],
              [106.68, 10.77]
            ]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

Query geo_shape so sánh hình dạng được cung cấp với hình dạng đã index. Quan hệ thường dùng gồm:

- intersects: hai hình dạng có phần giao nhau.
- within: hình dạng được index nằm trong hình dạng query theo semantics của relation.
- contains: hình dạng được index chứa hình dạng query.
- disjoint: hai hình dạng không giao nhau.

Hãy xác nhận hướng quan hệ theo đối tượng được index và đối tượng query; within và contains không thể đổi chỗ mà vẫn giữ nguyên ý nghĩa.

### Mapping geo_shape

Mapping có thể khai báo:

~~~json
{
  "mappings": {
    "properties": {
      "deliveryArea": {
        "type": "geo_shape"
      }
    }
  }
}
~~~

geo_shape phù hợp với polygon, multipolygon, line string và các hình dạng địa lý được Elasticsearch hỗ trợ. Dữ liệu có thể được gửi theo GeoJSON. Cần đóng vòng polygon và bảo đảm tọa độ có thứ tự longitude, latitude.

Nếu ứng dụng chỉ lưu một điểm giao hàng, dùng geo_point sẽ đơn giản hơn. Không dùng geo_shape chỉ vì nó có vẻ tổng quát hơn; mapping và query shape có chi phí cũng như semantics riêng.

## 7. Xây dựng truy vấn địa lý bằng CriteriaQuery

CriteriaQuery là lựa chọn thuận tiện khi điều kiện địa lý thuộc tập thao tác mà Spring Data Criteria hỗ trợ. Với các truy vấn đơn giản như tìm trong vòng tròn hoặc bounding box, abstraction này giúp code Java rõ ràng mà không cần tự dựng toàn bộ Query DSL.

Ví dụ tìm cửa hàng trong vòng tròn:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);

GeoCircle searchArea = new GeoCircle(
    center,
    new Distance(5, Metrics.KILOMETERS)
);

Criteria criteria = new Criteria("location")
    .within(searchArea);

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Các kiểu GeoPoint, GeoCircle, Criteria, CriteriaQuery, Distance và Metrics thuộc các package Spring Data tương ứng. Import cụ thể phụ thuộc phiên bản; GeoPoint dùng thứ tự latitude rồi longitude.

### Bounding box bằng Criteria

Với một vùng chữ nhật, có thể dùng GeoBox nếu phiên bản Criteria API đang dùng cung cấp overload within cho kiểu này:

~~~java
GeoBox box = new GeoBox(
    new GeoPoint(10.82, 106.65),
    new GeoPoint(10.72, 106.76)
);

Criteria criteria = new Criteria("location").within(box);
Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Hai điểm truyền vào lần lượt là top-left và bottom-right theo mô hình GeoBox. Kiểm tra constructor và API geo criteria của release train thực tế nếu phiên bản Spring Data khác với ví dụ.

### Kết hợp Criteria địa lý với điều kiện nghiệp vụ

Có thể ghép điều kiện địa lý với các điều kiện khác trong Criteria:

~~~java
Criteria criteria = new Criteria("location").within(searchArea)
    .and("active").is(true)
    .and("status").is("OPEN");

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Đây là cách diễn đạt cho điều kiện đơn giản. Khi cần kiểm soát rõ các nhánh bool, nhiều loại query địa lý, should, must_not, sort khoảng cách hoặc geo_shape relation, Criteria có thể không biểu diễn hết nhu cầu. Khi đó, dùng NativeQuery.

### Khi nào CriteriaQuery không đủ?

Chọn abstraction khác nếu:

- Query cần geo_shape với relation hoặc hình dạng phức tạp.
- Cần kết hợp nhiều nhánh bool và query địa lý theo cấu trúc tùy chỉnh.
- Cần distance sort với nhiều tùy chọn.
- Cần nested query hoặc aggregation kết hợp địa lý.
- Cần sử dụng option của Elasticsearch chưa được Criteria API bọc lại.
- Cần giữ đúng cấu trúc Query DSL do hệ thống khác tạo.

Không nên cố ép một query phức tạp thành chuỗi Criteria dài khó đọc.

## 8. Dùng NativeQuery khi cần kiểm soát Query DSL

NativeQuery của Spring Data Elasticsearch cho phép dùng query model của Elasticsearch Java API Client. Nó phù hợp khi muốn giữ tích hợp với ElasticsearchOperations, mapping entity và SearchHits, nhưng cần query DSL chi tiết.

Ví dụ xây geo-distance query bằng Java API Client query builder:

~~~java
co.elastic.clients.elasticsearch._types.query_dsl.Query geoQuery =
    co.elastic.clients.elasticsearch._types.query_dsl.Query.of(q -> q
        .geoDistance(g -> g
            .field("location")
            .distance("5km")
            .location(location -> location.latlon(point -> point
                .lat(10.7769)
                .lon(106.7009)
            ))
        )
    );

NativeQuery query = NativeQuery.builder()
    .withQuery(geoQuery)
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Đoạn builder minh họa API của Elasticsearch Java API Client được dùng trong các phiên bản Spring Data Elasticsearch hiện đại. Tên package, overload và cấu trúc builder có thể thay đổi theo phiên bản client; hãy đối chiếu dependency của dự án. Điểm chính là NativeQuery nhận một Query object đã được tạo bằng client builder, thay vì tự ghép JSON bằng phép nối chuỗi.

Có thể thêm filter nghiệp vụ vào bool query:

~~~java
Query combinedQuery = Query.of(q -> q.bool(b -> b
    .filter(f -> f.geoDistance(g -> g
        .field("location")
        .distance("5km")
        .location(location -> location.latlon(point -> point
            .lat(10.7769)
            .lon(106.7009)
        ))
    ))
    .filter(f -> f.term(t -> t
        .field("active")
        .value(true)
    ))
    .filter(f -> f.term(t -> t
        .field("status")
        .value("OPEN")
    ))
));

NativeQuery query = NativeQuery.builder()
    .withQuery(combinedQuery)
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Cấu trúc này tách ba điều kiện trong filter context. Nếu query cần thêm full-text relevance, có thể đưa match vào must và giữ điều kiện địa lý trong filter.

### Dùng Query DSL JSON để thiết kế trước

Khi query có nhiều tầng, nên viết và thử JSON trong Elasticsearch Dev Tools trước:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "coffee"
          }
        }
      ],
      "filter": [
        {
          "geo_distance": {
            "distance": "3km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
          }
        },
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  }
}
~~~

Sau khi xác nhận semantics và mapping, chuyển cấu trúc sang Java API Client builder rồi bọc trong NativeQuery. Cách này giúp phân biệt lỗi Query DSL với lỗi do cách dựng builder.

## 9. Gọi Elasticsearch Java API Client trực tiếp

Có thể gọi ElasticsearchClient trực tiếp khi cần kiểm soát request/response ở mức client. Đây là lựa chọn hữu ích cho các API đặc biệt hoặc khi ứng dụng muốn sử dụng chức năng client chưa được abstraction Spring Data cung cấp.

Ví dụ:

~~~java
SearchResponse<Store> response = elasticsearchClient.search(s -> s
    .index("stores")
    .size(20)
    .query(q -> q.geoDistance(g -> g
        .field("location")
        .distance("5km")
        .location(location -> location.latlon(point -> point
            .lat(10.7769)
            .lon(106.7009)
        ))
    )),
    Store.class
);

List<Store> stores = response.hits().hits().stream()
    .map(hit -> hit.source())
    .filter(Objects::nonNull)
    .toList();
~~~

Đây là ví dụ theo Java API Client; kiểm tra kiểu generic, import và builder overload theo phiên bản Elasticsearch client đang được Spring Boot quản lý.

### Khác biệt giữa NativeQuery và direct client

| Tiêu chí | NativeQuery + Operations | ElasticsearchClient trực tiếp |
|---|---|---|
| Query DSL | Dùng query model của Java API Client | Dùng query model của Java API Client |
| Mapping entity | Tích hợp converter và mapping của Spring Data | Caller chịu trách nhiệm chuyển đổi source/response |
| Kết quả | SearchHits<T>, SearchHit<T> | SearchResponse<T>, hit của client |
| Aggregation/metadata | Theo abstraction Spring Data | Truy cập response client trực tiếp |
| Kiểm soát request | Cao, trong khuôn khổ Operations | Rất cao |
| Tích hợp repository/service | Thuận tiện với hệ thống Spring Data | Cần tổ chức adapter và conversion rõ ràng |

Nếu ứng dụng đã dùng Spring Data cho phần lớn truy vấn, NativeQuery thường giữ được một mô hình làm việc thống nhất. Direct client phù hợp khi thật sự cần API cấp thấp hoặc muốn kiểm soát hoàn toàn response.

### Tránh trộn hai tầng truy cập thiếu quy ước

Nếu một số service dùng Operations, số khác dùng client trực tiếp, hãy thống nhất:

- Ai chịu trách nhiệm chọn index/alias?
- Mapping và conversion entity được thực hiện ở đâu?
- Cách xử lý lỗi Elasticsearch có giống nhau không?
- Timeout, retry và tracing có được cấu hình nhất quán không?
- Response raw được chuyển thành DTO ở lớp nào?

Có thể đóng gói direct client trong một adapter để phần còn lại của ứng dụng không phụ thuộc trực tiếp vào kiểu response của client.

## 10. Sắp xếp theo khoảng cách với geo-distance sort

Một use case phổ biến là tìm cửa hàng trong bán kính rồi sắp xếp cửa hàng gần nhất lên trước.

Query DSL:

~~~json
{
  "size": 20,
  "query": {
    "geo_distance": {
      "distance": "10km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km",
        "distance_type": "arc"
      }
    }
  ]
}
~~~

Query xác định tập cửa hàng nằm trong 10 km. Sort tính khoảng cách từ từng cửa hàng đến tọa độ trung tâm và xếp tăng dần, tức cửa hàng gần nhất đứng trước.

Query distance và distance sort có mục đích khác nhau:

- geo_distance trong query quyết định document có được lấy hay không.
- _geo_distance trong sort quyết định thứ tự document.

Nếu chỉ sort mà không lọc, kết quả có thể chứa những điểm ở rất xa. Nếu chỉ query mà không sort, không có bảo đảm cửa hàng gần nhất đứng đầu.

### Một document có nhiều geo_point

Nếu field chứa nhiều vị trí, sort cần quy định cách chọn khoảng cách đại diện. Elasticsearch hỗ trợ các mode như min, max, avg hoặc median tùy loại sort. Với ứng dụng tìm chi nhánh gần người dùng, thường cần khoảng cách nhỏ nhất đến bất kỳ chi nhánh nào.

Hãy xác định rõ document đại diện cho một điểm hay nhiều điểm. Nếu mỗi chi nhánh cần được xếp hạng riêng, mô hình một document cho mỗi chi nhánh thường đơn giản hơn một document chứa mảng nhiều tọa độ.

### Pagination sau geo-distance sort

Nếu cần phân trang sâu, sort phải ổn định. Có thể thêm một field duy nhất làm tie-breaker sau khoảng cách:

~~~json
{
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km"
      }
    },
    {
      "storeId": "asc"
    }
  ]
}
~~~

Khi dùng search_after, truyền lại toàn bộ sort values của hit cuối, bao gồm cả distance và tie-breaker. Không tự tính lại giá trị sort từ entity vì giá trị Elasticsearch trả về là cursor chính xác của query đó.

## 11. Kết hợp tìm kiếm địa lý với filter và full-text

Một trang tìm địa điểm có thể cho phép tìm từ khóa như coffee, giới hạn bán kính, chỉ lấy cửa hàng đang mở và lọc theo loại hình.

Query có thể có cấu trúc:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "coffee"
          }
        }
      ],
      "filter": [
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
          }
        },
        {
          "term": {
            "active": true
          }
        },
        {
          "terms": {
            "category": ["cafe", "restaurant"]
          }
        }
      ]
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km"
      }
    }
  ]
}
~~~

must tìm nội dung liên quan đến coffee. filter giới hạn khoảng cách, trạng thái và category. Sort xếp các địa điểm gần nhất lên trước.

Nếu sản phẩm muốn relevance quan trọng hơn khoảng cách, có thể sắp xếp theo _score trước rồi mới đến khoảng cách. Nếu khoảng cách là tiêu chí chính, sort theo _geo_distance trước. Đây là quyết định trải nghiệm sản phẩm, không chỉ là chi tiết kỹ thuật.

## 12. Đọc kết quả và khoảng cách trong Spring Data

Với ElasticsearchOperations, kết quả tìm kiếm có thể được giữ trong SearchHits<T>:

~~~java
SearchHits<Store> hits =
    operations.search(query, Store.class);

for (SearchHit<Store> hit : hits.getSearchHits()) {
    Store store = hit.getContent();
    float score = hit.getScore();

    // Dùng store cho dữ liệu entity.
    // Đọc metadata sort nếu query đã khai báo sort.
}
~~~

SearchHit<T> cung cấp entity content và metadata như ID, index, score, sort values, highlight và inner hits tùy request. Nếu sort theo khoảng cách, distance sort value có thể nằm trong getSortValues() theo thứ tự các tiêu chí sort.

Không nên giả định khoảng cách luôn là phần tử đầu tiên nếu query còn sort theo _score hoặc field khác. Giữ một định nghĩa sort duy nhất và ánh xạ đúng vị trí sort value.

Nếu gọi direct client, kết quả nằm trong SearchResponse<T> và mỗi hit có source cùng sort values theo response của client. Adapter nên chuyển response đó sang DTO ứng dụng.

### Trả khoảng cách trong DTO

API có thể trả:

~~~java
public record StoreSearchItem(
    String id,
    String name,
    GeoPoint location,
    Double distanceKm
) {}
~~~

distanceKm nên được lấy từ metadata distance sort hoặc được tính theo một quy tắc thống nhất. Không lấy giá trị sort index 0 một cách mù quáng; cần xác định cấu trúc sort của query.

Nếu ứng dụng tính khoảng cách lại ở Java để hiển thị, hãy dùng thư viện hoặc công thức địa lý phù hợp và coi đó là giá trị trình bày. Kết quả xếp hạng chính vẫn nên dựa trên semantics của Elasticsearch query/sort đã chạy.

## 13. Xây dựng service tìm cửa hàng gần nhất

Một service nên nhận tọa độ và bán kính dưới dạng tham số có kiểu, validate trước rồi mới xây query.

Ví dụ cấu trúc:

~~~java
public List<Store> findNearby(
        double latitude,
        double longitude,
        double radiusKm) {

    validateCoordinates(latitude, longitude);

    if (radiusKm <= 0 || radiusKm > 100) {
        throw new IllegalArgumentException(
            "radiusKm must be between 0 and 100"
        );
    }

    GeoCircle circle = new GeoCircle(
        new GeoPoint(latitude, longitude),
        new Distance(radiusKm, Metrics.KILOMETERS)
    );

    Criteria criteria = new Criteria("location").within(circle)
        .and("active").is(true);

    Query query = new CriteriaQuery(criteria);

    SearchHits<Store> hits =
        operations.search(query, Store.class);

    return hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();
}
~~~

Đoạn code minh họa cho trường hợp Criteria API của phiên bản đang dùng hỗ trợ GeoCircle và cách kết hợp Criteria như trên. Nếu cần thứ tự gần nhất, hãy thêm geo-distance sort qua API sort phù hợp hoặc dùng NativeQuery để khai báo rõ _geo_distance.

Hàm validate tọa độ:

~~~java
private void validateCoordinates(double latitude, double longitude) {
    if (!Double.isFinite(latitude)
            || latitude < -90
            || latitude > 90) {
        throw new IllegalArgumentException("Invalid latitude");
    }

    if (!Double.isFinite(longitude)
            || longitude < -180
            || longitude > 180) {
        throw new IllegalArgumentException("Invalid longitude");
    }
}
~~~

Không chỉ validate miền tọa độ. Ứng dụng cũng nên giới hạn bán kính tối đa và page size để tránh truy vấn quá rộng hoặc trả payload lớn ngoài dự kiến.

## 14. Kiểm thử truy vấn địa lý

Truy vấn địa lý cần integration test với Elasticsearch thật hoặc môi trường test tương thích. Unit test cho phần validate tọa độ không đủ để xác nhận mapping và semantics geo query.

Tạo một tập dữ liệu nhỏ có các điểm:

| Cửa hàng | Tọa độ minh họa | Kỳ vọng với tâm tìm kiếm |
|---|---|---|
| Store A | Gần tâm | Nằm trong bán kính nhỏ |
| Store B | Xa hơn A nhưng vẫn trong bán kính | Có trong kết quả |
| Store C | Ngoài bán kính | Không có trong kết quả |
| Store D | Trong bounding box nhưng ngoài polygon | Phân biệt được hai loại vùng |
| Store E | Tọa độ trùng hoặc gần bằng điểm khác | Tie-breaker xác định thứ tự |

Các trường hợp nên kiểm tra:

1. Tọa độ tâm trả về kết quả mong đợi.
2. Điểm ngay trong và ngoài ranh giới bán kính.
3. Đơn vị km và m được hiểu đúng.
4. Bounding box trả đúng các điểm trong khung.
5. Polygon có vòng tọa độ đóng và thứ tự longitude/latitude đúng.
6. Geo_shape relation tạo kết quả đúng theo hướng quan hệ.
7. Filter active/status kết hợp với geo query không làm lọt document.
8. Geo-distance sort xếp đúng thứ tự gần đến xa.
9. Document có nhiều điểm tuân theo mode sort đã chọn.
10. Pagination giữ thứ tự ổn định qua các trang.
11. Tọa độ không hợp lệ bị từ chối ở tầng service.
12. Index alias có mapping đồng nhất nếu query trên nhiều index.

### Kiểm tra bằng Dev Tools

Trước khi đưa query vào Java, chạy request JSON trực tiếp trong Elasticsearch Dev Tools. Điều này giúp xác nhận:

- Mapping field có đúng geo_point hoặc geo_shape.
- Tọa độ có đúng thứ tự.
- Query type có phù hợp.
- Bán kính và đơn vị đúng.
- Sort trả về đúng khoảng cách.

Sau khi query DSL chạy đúng, chuyển sang CriteriaQuery hoặc NativeQuery. Nếu kết quả khác nhau, so sánh request thực tế mà Spring Data gửi với JSON đã kiểm tra.

## 15. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy điểm gần dù tọa độ có vẻ đúng | Đảo latitude và longitude | Kiểm tra định dạng input và mapping |
| Điểm xuất hiện ở vị trí rất xa | Mảng tọa độ dùng sai thứ tự | Với geo_point array dùng [lon, lat]; với GeoJSON cũng dùng [lon, lat] |
| Query báo field không phải geo_point | Mapping field là keyword/object hoặc mapping cũ | Tạo mapping đúng và reindex |
| geo_distance trả nhiều kết quả hơn mong đợi | Bán kính hoặc đơn vị không đúng | Ghi rõ đơn vị như 5km |
| Kết quả trong bounding box khác vùng vẽ | Bounding box chỉ là hình chữ nhật | Dùng polygon/geo_shape cho vùng bất quy tắc |
| Polygon không hợp lệ | Vòng chưa đóng hoặc tọa độ sai thứ tự | Kiểm tra GeoJSON coordinates |
| geo_shape relation ngược ý nghĩa | Nhầm hướng within/contains | Xác định hình được index và hình query |
| Cửa hàng gần nhất không đứng đầu | Chỉ dùng geo_distance query mà chưa sort | Thêm _geo_distance sort |
| Kết quả trang sau bị lặp | Sort có nhiều khoảng cách bằng nhau nhưng thiếu tie-breaker | Thêm field duy nhất và dùng toàn bộ sort values |
| Criteria không biểu diễn được query | API abstraction không hỗ trợ option cần thiết | Chuyển sang NativeQuery |
| Direct client trả source null | Hit không có _source hoặc response projection khác | Xử lý null và kiểm tra request/mapping |
| Query trên alias lỗi giữa các index | Mapping geo field không đồng nhất | Đồng bộ mapping hoặc tách alias |

## 16. Chọn CriteriaQuery, NativeQuery hay direct client

Ba cách đều có chỗ dùng phù hợp:

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Tìm trong vòng tròn hoặc vùng chữ nhật với điều kiện đơn giản | CriteriaQuery |
| Kết hợp geo query, bool, sort khoảng cách, nested hoặc shape relation | NativeQuery |
| Cần API client cấp thấp, response raw hoặc tính năng chưa được Spring Data bọc | ElasticsearchClient trực tiếp |
| Muốn giữ SearchHits<T>, mapping và converter của Spring Data | CriteriaQuery hoặc NativeQuery qua ElasticsearchOperations |
| Muốn kiểm soát hoàn toàn request/response | Direct client, có adapter conversion riêng |

Không cần dùng direct client chỉ vì query có một điều kiện geo_distance. Nếu NativeQuery đã biểu diễn được query, giữ Operations giúp code tích hợp với Spring Data nhất quán hơn.

Ngược lại, cũng không nên ép một truy vấn địa lý nhiều tầng vào Criteria nếu abstraction làm mất khả năng diễn đạt hoặc khiến code khó hiểu. Hãy chọn tầng API thấp nhất cần thiết để biểu diễn đúng semantics.

## 17. Checklist triển khai truy vấn địa lý

- [ ] Field vị trí được mapping là geo_point hoặc geo_shape theo đúng dữ liệu.
- [ ] Tọa độ được chuẩn hóa và validate.
- [ ] Không nhầm thứ tự latitude/longitude với longitude/latitude.
- [ ] Khoảng cách có đơn vị tường minh.
- [ ] Dùng geo_distance cho bán kính và geo_bounding_box cho viewport.
- [ ] Dùng geo_shape cho vùng có hình dạng phức tạp.
- [ ] Chọn đúng relation giữa shape được index và shape query.
- [ ] Query địa lý được kết hợp với filter nghiệp vụ trong bool khi cần.
- [ ] Có geo-distance sort nếu cần kết quả gần nhất trước.
- [ ] Sort có tie-breaker nếu cần cursor pagination.
- [ ] CriteriaQuery chỉ dùng cho thao tác abstraction hỗ trợ.
- [ ] NativeQuery dùng query builder đúng phiên bản Java API Client.
- [ ] Direct client được bọc trong adapter có quy ước conversion/error handling.
- [ ] Integration test xác nhận mapping, ranh giới, đơn vị và sort.
- [ ] Mapping thay đổi được triển khai bằng index mới và reindex khi cần.

CriteriaQuery phù hợp với các truy vấn địa lý đơn giản mà Spring Data đã có abstraction. NativeQuery cho phép kết hợp các query địa lý của Elasticsearch Java API Client với filter, sort và các điều kiện phức tạp trong khi vẫn dùng ElasticsearchOperations. Direct client cung cấp quyền kiểm soát request/response ở mức thấp hơn. Dù chọn cách nào, hãy bắt đầu từ mapping đúng, quy ước tọa độ rõ ràng và Query DSL có semantics được xác nhận bằng dữ liệu thực tế.

