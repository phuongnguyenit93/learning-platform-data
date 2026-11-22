# Geo distance query và tìm kiếm quanh một vị trí

Tìm kiếm quanh một vị trí là một yêu cầu phổ biến trong ứng dụng giao hàng, bản đồ cửa hàng, đặt lịch dịch vụ, bất động sản và quản lý thiết bị. Người dùng cung cấp tọa độ hoặc một địa chỉ đã được geocoding; hệ thống cần tìm các document có vị trí nằm trong một bán kính nhất định, sau đó thường sắp xếp địa điểm gần nhất lên trước.

Elasticsearch hỗ trợ kiểu dữ liệu `geo_point` để lưu một điểm địa lý và `geo_distance` query để lọc các document nằm trong khoảng cách từ một điểm gốc. Khi cần xếp hạng theo khoảng cách, có thể kết hợp geo distance sort. Trong Spring Data Elasticsearch, property vị trí có thể được khai báo bằng `@GeoPointField`, còn truy vấn có thể được xây dựng bằng Elasticsearch Java API Client DSL và gắn vào `NativeQuery`.

Một nearby search điển hình có hai bước logic:

1. **Lọc theo bán kính:** chỉ giữ cửa hàng nằm trong phạm vi, ví dụ 10 km từ vị trí người dùng.
2. **Sắp xếp theo khoảng cách:** địa điểm gần nhất xuất hiện trước.

```text
Vị trí gốc (latitude, longitude)
              |
              v
       geo_distance query
       distance = 10 km
              |
              v
     Chỉ giữ địa điểm trong bán kính
              |
              v
       geo distance sort
        nearest first
              |
              v
       Pageable / page size
              |
              v
       SearchHits<Store>
```

## 1. `geo_point` là gì?

`geo_point` là kiểu field Elasticsearch dùng để lưu một tọa độ gồm latitude (vĩ độ) và longitude (kinh độ). Nó hỗ trợ các thao tác địa lý như tìm document trong bán kính, sắp xếp theo khoảng cách và một số dạng aggregation địa lý.

Ví dụ một cửa hàng ở Thành phố Hồ Chí Minh:

```json
{
  "store_id": "SG-001",
  "name": "Central Store",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
```

Trong đó:

- `lat` là latitude, nằm trong khoảng từ -90 đến 90 độ.
- `lon` là longitude, nằm trong khoảng từ -180 đến 180 độ.
- `location` phải được mapping là `geo_point` để dùng geo distance query/sort.

Nếu field được mapping là `object` thông thường, Elasticsearch không tự hiểu cặp số là một điểm địa lý. Truy vấn `geo_distance` yêu cầu field có kiểu địa lý phù hợp.

### 1.1. Các định dạng tọa độ Elasticsearch chấp nhận

Elasticsearch có thể nhận geo point ở một số dạng phổ biến:

**Object với lat/lon:**

```json
{ "lat": 10.7769, "lon": 106.7009 }
```

**Chuỗi `latitude,longitude`:**

```json
"10.7769,106.7009"
```

**Mảng tọa độ:**

```json
[106.7009, 10.7769]
```

Mảng tuân theo thứ tự longitude trước, latitude sau, tương tự quy ước tọa độ GeoJSON. Đây là nguồn lỗi thường gặp vì nhiều API Java dùng hai tham số `lat, lon`, trong khi mảng Elasticsearch/GeoJSON là `[lon, lat]`.

**GeoJSON Point:**

```json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
```

Khi trao đổi dữ liệu giữa Spring, Elasticsearch, GeoJSON và các dịch vụ bản đồ, hãy xác định rõ định dạng và thứ tự tọa độ ở từng ranh giới.

## 2. Khai báo `geo_point` trong mapping

Có thể khai báo mapping trực tiếp trong Elasticsearch:

```json
PUT /stores
{
  "mappings": {
    "properties": {
      "store_id": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword" }
        }
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
```

Trong Spring Data Elasticsearch, có thể dùng `@GeoPointField`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "stores")
public class StoreDocument {

    @Id
    private String id;

    @Field(name = "store_id", type = FieldType.Keyword)
    private String storeId;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Boolean)
    private boolean active;

    @GeoPointField
    private GeoPoint location;

    // constructors, getters, setters
}
```

`@GeoPointField` báo cho Spring Data biết property phải được ánh xạ thành `geo_point`. Kiểu `GeoPoint` của Spring Data Elasticsearch biểu diễn tọa độ latitude và longitude.

Ví dụ tạo entity:

```java
StoreDocument store = new StoreDocument();
store.setId("SG-001");
store.setStoreId("SG-001");
store.setName("Central Store");
store.setActive(true);
store.setLocation(new GeoPoint(10.7769, 106.7009));
```

Tham số constructor ở ví dụ là latitude trước, longitude sau. Khi dùng API khác hoặc tạo mảng GeoJSON, cần chuyển sang đúng thứ tự mà API đó yêu cầu.

### 2.1. Kiểm tra mapping sau khi tạo index

Có thể đọc mapping:

```http
GET /stores/_mapping
```

Kết quả cần thể hiện:

```json
{
  "properties": {
    "location": {
      "type": "geo_point"
    }
  }
}
```

Nếu index đã tồn tại với `location` là `object` hoặc kiểu không phù hợp, chỉ thêm annotation vào entity không tự đổi mapping của index hiện có. Cần tạo index mới với mapping đúng và reindex dữ liệu. Không thể đổi kiểu field hiện có từ `object` sang `geo_point` trực tiếp trong mapping đang dùng.

## 3. `geo_distance` query

`geo_distance` query tìm các document có ít nhất một giá trị geo point nằm trong khoảng cách chỉ định từ điểm gốc.

Ví dụ tìm cửa hàng trong bán kính 5 km quanh một tọa độ:

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

Các phần chính:

- `distance`: bán kính tìm kiếm, ví dụ `500m`, `5km`, `3mi`.
- `location`: field `geo_point` trong mapping.
- `lat` và `lon`: tọa độ gốc dùng làm tâm của vùng tìm kiếm.

Query khớp document có vị trí nằm trong bán kính. Document không có giá trị `location` hợp lệ thường không khớp điều kiện này.

### 3.1. Đơn vị khoảng cách

Elasticsearch hỗ trợ nhiều đơn vị khoảng cách, thường gặp:

| Đơn vị | Ký hiệu |
|---|---|
| Kilometre | `km` |
| Metre | `m` |
| Centimetre | `cm` |
| Millimetre | `mm` |
| Mile | `mi` |
| Yard | `yd` |
| Foot | `ft` |
| Nautical mile | `nmi` |

Nên dùng đơn vị tường minh trong request để dễ đọc và tránh hiểu nhầm. Ví dụ `distance: "5000m"` và `distance: "5km"` biểu diễn cùng bán kính.

### 3.2. Tìm kiếm kết hợp điều kiện nghiệp vụ

Nearby search thường cần lọc thêm trạng thái hoặc loại địa điểm:

```json
GET /stores/_search
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
            "category": "GROCERY"
          }
        },
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
          }
        }
      ]
    }
  }
}
```

Ở đây cả ba điều kiện đều là điều kiện lọc: cửa hàng phải đang hoạt động, thuộc danh mục grocery và nằm trong bán kính 5 km. Đặt `geo_distance` trong filter context phù hợp khi khoảng cách chỉ quyết định có được xuất hiện trong kết quả hay không.

Nếu muốn dùng khoảng cách như một tín hiệu relevance, có thể thiết kế scoring riêng, ví dụ `distance_feature` hoặc `function_score`. Không nên kỳ vọng `geo_distance` filter tự động xếp cửa hàng gần hơn lên trước.

## 4. `geo_distance` query không tự sắp xếp gần nhất

Một lỗi phổ biến là cho rằng kết quả của `geo_distance` query tự động được trả theo khoảng cách tăng dần. Query chỉ xác định document nào nằm trong bán kính; thứ tự mặc định của search vẫn theo relevance score hoặc quy tắc sort của request.

Để cửa hàng gần nhất xuất hiện trước, cần thêm geo distance sort:

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
```

`order: "asc"` đưa khoảng cách nhỏ hơn lên trước. `unit: "km"` quy định đơn vị sort distance trong kết quả. `distance_type: "arc"` sử dụng khoảng cách theo cung trên bề mặt hình cầu; đây là lựa chọn mặc định phù hợp cho hầu hết nearby search.

Nếu chỉ dùng geo sort mà không dùng geo distance query, request có thể sắp xếp document theo khoảng cách nhưng vẫn trả về các địa điểm rất xa. Vì vậy, khi giao diện yêu cầu “trong vòng 5 km và gần nhất trước”, cần cả filter bán kính và sort.

### 4.1. Thêm tie-breaker để thứ tự ổn định

Hai cửa hàng có thể cách điểm gốc gần như bằng nhau. Nếu chỉ sort theo khoảng cách, thứ tự giữa các document có cùng giá trị sort có thể không ổn định giữa các request.

Có thể thêm field duy nhất, có doc values và có mapping `keyword` làm tie-breaker:

```json
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
    "store_id": "asc"
  }
]
```

Field `store_id` phải có giá trị ổn định và duy nhất trong tập kết quả liên quan. Không mặc định `_id` có thể dùng làm field sort thông thường.

## 5. Geo distance sort với document có nhiều vị trí

Một document `geo_point` có thể chứa nhiều tọa độ. Ví dụ một đơn vị giao hàng có nhiều điểm phục vụ hoặc một tài sản có nhiều vị trí được ghi nhận.

```json
{
  "service_id": "S-100",
  "locations": [
    { "lat": 10.77, "lon": 106.70 },
    { "lat": 10.80, "lon": 106.68 }
  ]
}
```

Geo distance query sẽ khớp document nếu giá trị geo point phù hợp nằm trong bán kính. Với geo distance sort, có thể chọn cách kết hợp khoảng cách của nhiều điểm bằng `mode`, ví dụ:

- `min`: khoảng cách gần nhất trong các điểm của document.
- `max`: khoảng cách xa nhất.
- `avg`: khoảng cách trung bình.
- `median`: trung vị khoảng cách.

Với bài toán tìm đơn vị gần nhất, `min` thường là lựa chọn hợp lý vì document được xếp theo điểm phục vụ gần nhất. Hãy cấu hình mode rõ ràng nếu một document có nhiều tọa độ và nghiệp vụ phụ thuộc cách tính đó.

## 6. `distance_type`: arc và plane

Geo distance query/sort có thể sử dụng các cách tính khoảng cách khác nhau:

- `arc`: tính khoảng cách theo cung trên bề mặt hình cầu. Phù hợp với phần lớn ứng dụng địa lý và khoảng cách thực tế.
- `plane`: dùng phép tính phẳng gần đúng. Có thể nhanh hơn trong một số trường hợp nhỏ, nhưng sai số tăng khi khoảng cách lớn hoặc ở vĩ độ cao.

Nếu chưa có lý do đo đạc cụ thể để chọn plane, hãy dùng mặc định arc. Không tự chuyển sang plane chỉ để tối ưu hiệu năng mà chưa so sánh kết quả trên khu vực và khoảng cách thực tế của ứng dụng.

Khoảng cách Elasticsearch trả về là khoảng cách địa lý theo mô hình tính toán của Elasticsearch, không phải quãng đường lái xe, đi bộ hay thời gian di chuyển. Nếu sản phẩm cần “gần nhất theo đường đi”, cần một routing/directions service bên ngoài; geo distance chỉ đo khoảng cách đường chim bay.

## 7. `geo_distance` query bằng Spring Data Elasticsearch

Với Spring Data Elasticsearch hiện đại, có thể tạo `geo_distance` query bằng Elasticsearch Java API Client DSL và gắn vào `NativeQuery`.

Ví dụ tìm cửa hàng trong 5 km:

```java
import co.elastic.clients.elasticsearch._types.GeoLocation;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public SearchHits<StoreDocument> findNearby(
        double latitude,
        double longitude,
        String radius) {

    Query geoQuery = Query.of(q -> q
            .geoDistance(g -> g
                    .field("location")
                    .distance(radius)
                    .location(GeoLocation.of(l -> l
                            .latlon(point -> point
                                    .lat(latitude)
                                    .lon(longitude)
                            )
                    ))
            )
    );

    NativeQuery query = NativeQuery.builder()
            .withQuery(geoQuery)
            .build();

    return operations.search(query, StoreDocument.class);
}
```

Trong đoạn code:

- `field("location")` là tên field `geo_point` trong Elasticsearch mapping.
- `distance(radius)` nhận chuỗi có đơn vị như `"5km"` hoặc `"500m"`.
- `GeoLocation.latlon(...)` tạo điểm gốc với latitude và longitude.
- `NativeQuery` giữ query DSL của Elasticsearch Java API Client.
- `ElasticsearchOperations.search(...)` thực thi và ánh xạ kết quả thành `StoreDocument`.

Đây là API của Elasticsearch Java API Client được Spring Data Elasticsearch 5.x sử dụng. Package và overload cụ thể cần tương thích với phiên bản Spring Data/Java API Client của dự án.

### 7.1. Kết hợp filter nghiệp vụ

Ví dụ chỉ lấy cửa hàng active và nằm trong bán kính:

```java
Query nearbyActiveStores = Query.of(q -> q
        .bool(b -> b
                .filter(f -> f.term(t -> t
                        .field("active")
                        .value(true)
                ))
                .filter(f -> f.geoDistance(g -> g
                        .field("location")
                        .distance("5km")
                        .location(GeoLocation.of(l -> l
                                .latlon(ll -> ll
                                        .lat(10.7769)
                                        .lon(106.7009)
                                )
                        ))
                ))
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(nearbyActiveStores)
        .build();
```

Đặt geo query trong `filter` giúp thể hiện rằng khoảng cách là điều kiện có/không. Nếu có thêm tìm kiếm tên cửa hàng cần relevance, có thể đặt `match` trong `must` và các điều kiện active/geo trong `filter`.

## 8. Kết hợp tìm kiếm văn bản và nearby search

Một ứng dụng có thể cho phép người dùng tìm “pharmacy” quanh vị trí hiện tại. Khi đó:

- `match` trên tên/loại địa điểm xác định mức độ phù hợp với từ khóa.
- `term` trên trạng thái đảm bảo chỉ lấy địa điểm đang hoạt động.
- `geo_distance` giới hạn bán kính.
- Geo distance sort ưu tiên địa điểm gần nhất.

Ví dụ Query DSL:

```json
GET /places/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "pharmacy",
            "fields": ["name^2", "category"]
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        {
          "geo_distance": {
            "distance": "3km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
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
    },
    { "place_id": "asc" }
  ]
}
```

Trong ví dụ này, geo sort đứng đầu nên khoảng cách quyết định thứ tự trước. Nếu muốn relevance quyết định trước rồi khoảng cách chỉ là tie-breaker, đặt `_score` trước geo sort:

```json
"sort": [
  { "_score": "desc" },
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
  { "place_id": "asc" }
]
```

Thứ tự sort phải phản ánh UX: “gần nhất” và “liên quan nhất” là hai mục tiêu khác nhau. Nếu sort theo khoảng cách đầu tiên, một địa điểm khớp từ khóa yếu nhưng gần có thể đứng trước địa điểm khớp rất tốt nhưng xa hơn.

## 9. Geo distance sort trong Spring Data `NativeQuery`

Elasticsearch Java API Client có `SortOptions` cho geo distance sort. Có thể xây dựng sort theo tọa độ gốc, đơn vị và chiều tăng dần:

```java
import co.elastic.clients.elasticsearch._types.DistanceUnit;
import co.elastic.clients.elasticsearch._types.GeoDistanceType;
import co.elastic.clients.elasticsearch._types.GeoLocation;
import co.elastic.clients.elasticsearch._types.SortMode;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;

SortOptions nearestFirst = SortOptions.of(s -> s
        .geoDistance(g -> g
                .field("location")
                .location(GeoLocation.of(l -> l
                        .latlon(point -> point
                                .lat(10.7769)
                                .lon(106.7009)
                        )
                ))
                .order(SortOrder.Asc)
                .unit(DistanceUnit.Kilometers)
                .distanceType(GeoDistanceType.Arc)
                .mode(SortMode.Min)
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(nearbyActiveStores)
        .withSort(nearestFirst)
        .withPageable(PageRequest.of(0, 20))
        .build();
```

`SortMode.Min` chọn khoảng cách nhỏ nhất khi document có nhiều geo point. Với field đơn trị, mode này không làm thay đổi kết quả. Nếu API builder của phiên bản đang dùng có overload khác cho danh sách `SortOptions`, hãy dùng overload tương ứng; nguyên tắc là sort được thêm vào `NativeQuery` trước khi gọi `operations.search`.

Khi cần tie-breaker, thêm một field sort có thứ tự xác định sau geo sort. Ví dụ `store_id` kiểu `keyword`. Điều này đặc biệt hữu ích khi phân trang bằng `search_after`.

## 10. Lấy khoảng cách từ kết quả search

Geo distance sort thường trả giá trị khoảng cách trong mảng `sort` của mỗi hit. Nếu request sort theo `_geo_distance`, response có thể có dạng:

```json
{
  "_id": "SG-001",
  "_source": {
    "name": "Central Store",
    "location": {
      "lat": 10.7769,
      "lon": 106.7009
    }
  },
  "sort": [
    0.42,
    "SG-001"
  ]
}
```

Giá trị đầu tiên là khoảng cách theo đơn vị đã chọn trong geo sort, ví dụ kilomet; giá trị thứ hai là tie-breaker `store_id`.

Trong Spring Data Elasticsearch, `SearchHit<T>` cung cấp sort values của hit theo API phiên bản tương ứng. Có thể đọc `SearchHit.getSortValues()` để xây dựng DTO chứa khoảng cách:

```java
SearchHits<StoreDocument> hits = operations.search(query, StoreDocument.class);

List<NearbyStore> results = hits.getSearchHits().stream()
        .map(hit -> {
            Object distance = hit.getSortValues().get(0);
            return new NearbyStore(
                    hit.getContent(),
                    ((Number) distance).doubleValue()
            );
        })
        .toList();
```

Ví dụ giả định geo distance là sort value đầu tiên và đơn vị là kilomet. Nếu thay đổi thứ tự sort hoặc thêm một sort field trước geo distance, index trong danh sách sẽ thay đổi. Nên đóng gói quy tắc này trong mapper/service thay vì để controller tự đọc vị trí số cố định.

Nếu ứng dụng cần khoảng cách nhưng không muốn sắp xếp theo geo distance, có thể dùng `script_fields` hoặc cơ chế tính distance phù hợp, nhưng thường geo distance sort vừa xếp thứ tự vừa trả sort value là cách thuận tiện.

## 11. Phân trang nearby search

Nearby search thường trả danh sách địa điểm gần nhất, do đó có thể dùng `Pageable` với geo distance sort:

```java
Pageable pageable = PageRequest.of(
        0,
        20
);

NativeQuery query = NativeQuery.builder()
        .withQuery(nearbyActiveStores)
        .withSort(nearestFirst)
        .withPageable(pageable)
        .build();
```

`PageRequest` dùng page index bắt đầu từ 0. Với trang đầu size 20, Elasticsearch lấy 20 địa điểm gần nhất theo geo sort.

### 11.1. Sort ổn định khi khoảng cách bằng nhau

Nếu nhiều địa điểm có cùng khoảng cách sau khi làm tròn hoặc cùng sort value, hãy thêm field tie-breaker duy nhất. Nếu không, khi chuyển trang, thứ tự giữa các document bằng nhau có thể không ổn định.

### 11.2. Deep pagination

`from/size` không phù hợp để đi sâu qua hàng trăm nghìn địa điểm. Với danh sách lớn, có thể dùng `search_after` và sort ổn định. Nếu dữ liệu có thể thay đổi trong lúc người dùng duyệt, kết hợp Point in Time (PIT) để giữ góc nhìn search nhất quán.

Với PIT, sort cần có các giá trị xác định. Có thể dùng geo distance trước, một business ID duy nhất làm tie-breaker và `_shard_doc` nếu dùng PIT theo cách Elasticsearch khuyến nghị. Lấy mảng `sort` của hit cuối trang trước và truyền nguyên vẹn vào `search_after` của request tiếp theo.

## 12. Kiểm tra đầu vào tọa độ và bán kính

Không nên chuyển trực tiếp mọi giá trị do client gửi thành geo query. Service cần kiểm tra:

- Latitude nằm trong `[-90, 90]`.
- Longitude nằm trong `[-180, 180]`.
- Bán kính là số dương.
- Đơn vị khoảng cách nằm trong tập được hỗ trợ bởi API.
- Bán kính không vượt giới hạn nghiệp vụ cho phép.
- Giá trị không phải `NaN`, vô cực hoặc chuỗi không parse được.

Ví dụ validation:

```java
public record Coordinates(double latitude, double longitude) {

    public Coordinates {
        if (!Double.isFinite(latitude)
                || latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException("Invalid latitude");
        }

        if (!Double.isFinite(longitude)
                || longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("Invalid longitude");
        }
    }
}
```

Với radius, nên parse thành một kiểu dữ liệu nội bộ hoặc dùng enum đơn vị thay vì nối chuỗi tùy ý từ client. Ví dụ API chỉ cho phép `500m`, `1km`, `3km`, `5km` và `10km` thì service nên whitelist các lựa chọn này.

Không nên mặc định vị trí hiện tại do browser/mobile gửi luôn đúng. Nếu vị trí không được cấp quyền hoặc không có dữ liệu, hãy yêu cầu người dùng nhập địa chỉ hoặc chọn một điểm trên bản đồ.

## 13. Tìm quanh địa chỉ: geocoding và geo distance là hai bước riêng

Người dùng thường nhập địa chỉ như “Quận 1, Thành phố Hồ Chí Minh” thay vì tọa độ. Elasticsearch geo distance query cần tọa độ, vì vậy ứng dụng thường có hai bước:

1. Dùng geocoding service chuyển địa chỉ thành latitude/longitude.
2. Dùng `geo_distance` query tìm document quanh tọa độ đó.

Geocoding không phải chức năng của `geo_distance` query. Nó là bước riêng, có thể dùng dịch vụ bản đồ hoặc dữ liệu địa chỉ nội bộ. Nên lưu tọa độ đã geocode cho địa điểm cố định để tránh gọi geocoder lặp lại mỗi lần tìm kiếm.

Nếu geocoder trả nhiều candidate, cần chọn kết quả phù hợp hoặc yêu cầu người dùng xác nhận. Tọa độ sai vài kilomet có thể làm kết quả nearby search sai đáng kể.

## 14. Field thiếu, nhiều vị trí và nested location

### Field location thiếu

Document không có location hợp lệ không thể tham gia geo distance query theo cách thông thường. Nếu dữ liệu vị trí là bắt buộc, hãy validate trước khi index. Nếu location là tùy chọn, có thể lọc thêm `exists` để loại document thiếu vị trí hoặc chấp nhận geo query tự loại chúng.

### Nhiều geo point trên cùng một document

Nếu property chứa nhiều geo point, query có thể khớp khi một điểm nằm trong bán kính. Geo sort cần `mode` để quyết định cách kết hợp khoảng cách của các điểm. Với “địa điểm gần nhất”, thường dùng `min`.

### Geo point nằm trong nested object

Nếu tọa độ nằm trong nested object, cần mapping nested và sử dụng nested query với path tương ứng. Ví dụ document có nhiều chi nhánh, mỗi chi nhánh có location và trạng thái riêng. Nếu dùng object thông thường, các điều kiện ở các phần tử mảng có thể bị ghép chéo. Với nested mapping, query cần đi vào đúng path và sort có thể cần nested sort filter/path theo cấu trúc dữ liệu.

Không cần dùng nested chỉ vì một document có một `geo_point`. Chỉ dùng nested khi mỗi phần tử object trong mảng cần giữ quan hệ độc lập giữa location và các field khác của phần tử đó.

## 15. Những lưu ý về độ chính xác và ý nghĩa khoảng cách

Geo distance đo khoảng cách địa lý giữa tọa độ, thường được gọi là khoảng cách đường chim bay. Nó không tính:

- Đường đi bộ hoặc đường lái xe.
- Sông, cầu, đường một chiều hoặc rào chắn.
- Thời gian di chuyển theo giao thông.
- Khả năng tiếp cận của người dùng.
- Khoảng cách thực tế trong tòa nhà nhiều tầng.

Nếu người dùng cần cửa hàng gần nhất theo đường đi, hãy dùng một routing engine hoặc directions API để tính route distance/time. Elasticsearch có thể lọc candidate theo bán kính đường chim bay trước, sau đó ứng dụng gọi routing service cho một tập candidate nhỏ.

Đối với các khu vực gần đường đổi ngày quốc tế hoặc gần cực, Elasticsearch xử lý tọa độ địa lý theo mô hình geo của nó; ứng dụng không nên tự tính khoảng cách bằng công thức Euclidean trên latitude/longitude. Nếu tự tính ở service, cần dùng công thức địa lý phù hợp và xử lý wrap-around longitude.

## 16. Geo distance aggregation theo khoảng cách

Ngoài query, Elasticsearch còn có `geo_distance` aggregation để chia document thành các bucket theo khoảng cách từ một điểm gốc. Điều này hữu ích khi dashboard muốn biết có bao nhiêu địa điểm trong 1 km, 1–5 km hoặc trên 5 km.

Ví dụ:

```json
GET /stores/_search
{
  "size": 0,
  "aggs": {
    "distance_bands": {
      "geo_distance": {
        "field": "location",
        "origin": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "unit": "km",
        "ranges": [
          { "to": 1 },
          { "from": 1, "to": 5 },
          { "from": 5 }
        ]
      },
      "aggs": {
        "average_rating": {
          "avg": {
            "field": "rating"
          }
        }
      }
    }
  }
}
```

Mỗi distance bucket có `doc_count` và metric con `average_rating`. Đây là aggregation để phân tích phân bố, không thay thế `geo_distance` query khi cần giới hạn kết quả trả về.

## 17. Ví dụ service Spring Data hoàn chỉnh

Ví dụ sau kết hợp kiểm tra tọa độ, filter cửa hàng active, lọc bán kính và sắp xếp gần nhất. Để tập trung vào geo search, radius được truyền dưới dạng chuỗi đã được validate ở tầng service.

```java
import co.elastic.clients.elasticsearch._types.DistanceUnit;
import co.elastic.clients.elasticsearch._types.GeoDistanceType;
import co.elastic.clients.elasticsearch._types.GeoLocation;
import co.elastic.clients.elasticsearch._types.SortMode;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class NearbyStoreService {

    private final ElasticsearchOperations operations;

    public NearbyStoreService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<StoreDocument> findNearby(
            double latitude,
            double longitude,
            String radius,
            int page,
            int size) {

        Coordinates origin = new Coordinates(latitude, longitude);
        validateRadius(radius);

        GeoLocation point = GeoLocation.of(l -> l.latlon(ll -> ll
                .lat(origin.latitude())
                .lon(origin.longitude())
        ));

        Query queryDsl = Query.of(q -> q
                .bool(b -> b
                        .filter(f -> f.term(t -> t
                                .field("active")
                                .value(true)
                        ))
                        .filter(f -> f.geoDistance(g -> g
                                .field("location")
                                .distance(radius)
                                .location(point)
                        ))
                )
        );

        SortOptions distanceSort = SortOptions.of(s -> s
                .geoDistance(g -> g
                        .field("location")
                        .location(point)
                        .order(SortOrder.Asc)
                        .unit(DistanceUnit.Kilometers)
                        .distanceType(GeoDistanceType.Arc)
                        .mode(SortMode.Min)
                )
        );

        NativeQuery query = NativeQuery.builder()
                .withQuery(queryDsl)
                .withSort(distanceSort)
                .withPageable(PageRequest.of(page, size))
                .build();

        return operations.search(query, StoreDocument.class);
    }

    private void validateRadius(String radius) {
        // Parse and whitelist supported values, for example 500m, 1km, 3km, 5km.
        if (radius == null || radius.isBlank()) {
            throw new IllegalArgumentException("Radius is required");
        }
    }
}
```

Đây là mẫu cấu trúc service; `Coordinates` là record validation đã trình bày ở phần trước. Trong ứng dụng thực tế, nên dùng kiểu radius có cấu trúc thay vì chỉ kiểm tra chuỗi rỗng. Nếu cần tie-breaker, thêm sort field ổn định sau geo sort theo API `NativeQuery` của phiên bản đang dùng.

## 18. Kiểm thử nearby search

Nên dùng integration test với Elasticsearch thật hoặc Testcontainers để kiểm tra mapping `geo_point`, khoảng cách và sort. Mock `ElasticsearchOperations` chỉ xác nhận service tạo lời gọi, không xác nhận kết quả địa lý của Elasticsearch.

Một bộ fixture đơn giản:

| ID | Latitude | Longitude | Ý nghĩa |
|---|---:|---:|---|
| S1 | 10.7769 | 106.7009 | Điểm gốc. |
| S2 | 10.7800 | 106.7009 | Gần điểm gốc. |
| S3 | 10.8200 | 106.7009 | Xa hơn. |
| S4 | 10.7769 | 106.7600 | Ở phía đông. |
| S5 | 10.7769 | 106.7009 | Cùng tọa độ với điểm gốc nhưng inactive. |

Các test nên xác nhận:

1. Điểm gốc nằm trong bán kính nhỏ.
2. Điểm gần được trả trước điểm xa khi geo sort tăng dần.
3. Điểm nằm ngoài bán kính bị loại.
4. Cửa hàng inactive bị loại bởi filter nghiệp vụ.
5. Tọa độ bị đảo latitude/longitude tạo kết quả khác hoặc bị validation từ chối nếu ngoài phạm vi.
6. Document thiếu location không xuất hiện.
7. Sort tie-breaker giữ thứ tự ổn định khi hai document có cùng khoảng cách.
8. Page 0 và page 1 không lặp document khi dữ liệu và snapshot ổn định.
9. Multi-valued geo point dùng đúng `mode` đã chọn.

Khoảng cách thực tế trong fixture phụ thuộc phép tính địa lý của Elasticsearch. Test nên kiểm tra thứ tự và việc nằm trong/ngoài bán kính với các điểm cách nhau đủ rõ, tránh dùng ngưỡng sát ranh giới do sai số số thực.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `geo_distance` báo field không phải geo_point | Mapping field sai hoặc index cũ được tạo trước annotation. | Kiểm tra mapping và tạo index/reindex với `geo_point`. |
| Kết quả nearby không đúng khu vực | Đảo latitude và longitude. | Dùng `lat, lon` cho object/API; nhớ GeoJSON array là `[lon, lat]`. |
| Query trả địa điểm xa nhất trước | Chỉ dùng `geo_distance` query, chưa thêm geo distance sort. | Thêm `_geo_distance` sort với `order: asc`. |
| Sort gần nhất nhưng vẫn trả địa điểm ngoài bán kính | Có geo sort nhưng không có geo distance filter. | Dùng cả query lọc bán kính và sort. |
| Khoảng cách hiển thị sai đơn vị | Không đặt `unit` hoặc mapper hiểu sai sort value. | Đặt unit tường minh và ghi rõ đơn vị trong DTO. |
| Tìm theo đường chim bay nhưng người dùng kỳ vọng đường đi | Geo distance không tính routing hoặc giao thông. | Dùng routing/directions service cho route distance/time. |
| Hai trang bị lặp hoặc thứ tự thay đổi | Sort không có tie-breaker hoặc dữ liệu thay đổi giữa request. | Thêm field sort duy nhất; dùng PIT + `search_after` khi cần snapshot. |
| Multi-location document được xếp theo điểm không mong muốn | Geo sort mode chưa phù hợp. | Chọn `min`, `max`, `avg` hoặc mode đúng với nghiệp vụ. |
| Không tìm thấy địa điểm thiếu tọa độ | Geo distance query không khớp document thiếu geo point. | Bổ sung dữ liệu vị trí hoặc xử lý nhóm document không có location riêng. |
| Query chậm khi radius quá lớn | Tập candidate quá rộng hoặc query kết hợp nhiều điều kiện tốn kém. | Giới hạn radius, lọc thêm điều kiện phù hợp và benchmark. |

## 20. Nguyên tắc thiết kế

- Mapping field vị trí thành `geo_point`; trong Spring Data dùng `@GeoPointField`.
- Thống nhất thứ tự tọa độ: API Java thường nhận latitude trước longitude; mảng GeoJSON là longitude trước latitude.
- Validate latitude, longitude và bán kính trước khi tạo query.
- Dùng `geo_distance` query để giới hạn bán kính.
- Dùng geo distance sort với `asc` để đưa địa điểm gần nhất lên trước.
- Không nhầm query lọc bán kính với sort khoảng cách; hai thao tác có mục đích riêng.
- Đặt geo filter trong filter context khi khoảng cách chỉ là điều kiện có/không.
- Chọn `arc` cho đa số trường hợp; chỉ dùng `plane` khi đã đo và chấp nhận sai số.
- Với nhiều geo point, chọn `mode` phù hợp, thường là `min` cho điểm gần nhất.
- Thêm tie-breaker duy nhất để phân trang ổn định.
- Dùng `NativeQuery` và Elasticsearch Java API Client DSL khi cần geo query/sort trong Spring Data Elasticsearch hiện đại.
- Dùng geocoding để chuyển địa chỉ thành tọa độ; geo distance query không tự geocode.
- Dùng routing service nếu cần khoảng cách hoặc thời gian theo đường đi.

## 21. Những điểm cần nhớ

- `geo_point` lưu latitude/longitude và là kiểu mapping cần thiết cho geo distance query/sort.
- `@GeoPointField` ánh xạ property vị trí trong entity Spring Data Elasticsearch.
- `geo_distance` query lọc document nằm trong bán kính từ một điểm gốc.
- Query không tự sắp xếp theo khoảng cách; cần thêm `_geo_distance` sort.
- `order: asc` đưa địa điểm gần nhất lên trước; đặt `unit` rõ ràng để diễn giải sort value.
- `arc` là lựa chọn mặc định phù hợp cho hầu hết tìm kiếm địa lý; `plane` là phép tính gần đúng.
- `mode: min` thường phù hợp khi một document có nhiều vị trí và cần khoảng cách gần nhất.
- GeoJSON coordinates dùng thứ tự `[longitude, latitude]`; object `lat/lon` ghi rõ tên nên ít mơ hồ hơn.
- Spring Data Elasticsearch có thể xây dựng geo query bằng Java API Client DSL, gắn vào `NativeQuery` và thực thi qua `ElasticsearchOperations`.
- Geo distance là đường chim bay, không phải route distance hoặc thời gian di chuyển.
- Dùng tie-breaker và PIT + `search_after` khi cần phân trang sâu ổn định.

Geo distance query là nền tảng cho nearby search trong Spring Data Elasticsearch. Hãy lưu vị trí bằng `geo_point`, lọc bằng bán kính phù hợp, sắp xếp riêng theo khoảng cách và validate tọa độ ở biên API. Khi kết hợp đúng query, sort và phân trang, ứng dụng có thể trả về các địa điểm gần nhất một cách nhất quán và dễ kiểm soát.

## Tài liệu tham khảo

- [Elasticsearch — Geo-point field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-point.html)
- [Elasticsearch — Geo-distance query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-geo-distance-query.html)
- [Elasticsearch — Sort search results by geographic distance](https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html#geo-sorting)
- [Elasticsearch Java API Client — Query DSL](https://www.elastic.co/guide/en/elasticsearch/client/java-api-client/current/query.html)
- [Spring Data Elasticsearch — Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
