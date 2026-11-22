# Sắp xếp, tổng hợp và trả về khoảng cách phù hợp

Trong ứng dụng có dữ liệu địa lý, tìm document nằm trong bán kính chỉ là bước đầu. Một API tìm cửa hàng gần người dùng thường cần làm thêm ba việc:

1. Sắp xếp cửa hàng từ gần đến xa.
2. Tổng hợp số lượng cửa hàng theo các dải khoảng cách, chẳng hạn 0–1 km, 1–5 km và 5–20 km.
3. Trả khoảng cách của từng kết quả về client theo đơn vị phù hợp để hiển thị.

Elasticsearch hỗ trợ các việc này trên field kiểu geo_point. Có thể dùng geo-distance sort để xếp hạng theo khoảng cách, geo_distance aggregation để gom nhóm theo dải khoảng cách và sort values hoặc script field để lấy giá trị khoảng cách trong response.

Trong Spring Data Elasticsearch, NativeQuery cùng Elasticsearch Java API Client cho phép xây dựng các cấu hình này. Khi đọc kết quả, cần phân biệt document content với hit metadata: khoảng cách dùng để sort thường nằm trong sort values của SearchHit, không tự động trở thành property trong entity hay _source.

## 1. Chuẩn bị field geo_point

Giả sử ứng dụng quản lý cửa hàng:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "stores")
public class Store {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.GeoPoint)
    private GeoPoint location;

    // constructors, getters and setters
}
~~~

Field location phải được mapping thành geo_point. Mapping tương ứng:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "category": {
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

Có thể kiểm tra mapping:

~~~http
GET /stores/_mapping?pretty
~~~

Nếu location đang là object thông thường hoặc text, geo-distance sort và geo_distance aggregation sẽ không hoạt động như mong muốn. Annotation trong Java không tự sửa mapping của index đã tồn tại; khi đổi field type, cần tạo index mới và migrate/reindex dữ liệu theo quy trình phù hợp.

### 1.1. Quy ước latitude và longitude

Với Spring Data GeoPoint, constructor thường nhận latitude trước, longitude sau:

~~~java
GeoPoint point = new GeoPoint(10.7769, 106.7009);
~~~

Trong JSON object của Elasticsearch, dùng thuộc tính lat và lon:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Nếu dùng mảng tọa độ, thứ tự là longitude trước, latitude sau:

~~~json
{
  "location": [
    106.7009,
    10.7769
  ]
}
~~~

Đây là nguồn lỗi phổ biến. Latitude phải nằm trong khoảng -90 đến 90; longitude nằm trong khoảng -180 đến 180. Hãy kiểm tra dữ liệu đầu vào trước khi lưu và thống nhất quy ước tại API boundary.

## 2. Xác định điểm gốc để tính khoảng cách

Mọi phép tính khoảng cách đều cần một điểm gốc (origin). Trong ứng dụng tìm địa điểm, origin thường là:

- Vị trí hiện tại do thiết bị gửi lên.
- Địa chỉ người dùng đã chọn và được geocode thành tọa độ.
- Một trung tâm cố định như sân bay, kho hàng hoặc chi nhánh.
- Một điểm do nghiệp vụ chỉ định.

Ví dụ:

~~~java
double originLat = 10.7769;
double originLon = 106.7009;
~~~

Không lấy hai giá trị này từ chuỗi không được kiểm tra. Hãy xác nhận chúng là số hữu hạn, latitude/longitude nằm trong miền hợp lệ và giá trị có đúng thứ tự.

Khoảng cách phụ thuộc origin. Nếu origin thay đổi theo request, query sort và aggregation phải dùng cùng một origin để kết quả nhất quán. Không sort theo tọa độ này nhưng tổng hợp theo một tọa độ khác.

### 2.1. Đơn vị khoảng cách

Elasticsearch hỗ trợ nhiều đơn vị khoảng cách, thường gặp:

| Đơn vị | Ký hiệu |
|---|---|
| Mét | m |
| Kilômét | km |
| Centimét | cm |
| Milimét | mm |
| Dặm | mi |
| Yard | yd |
| Feet | ft |
| Hải lý | nmi |

Với ứng dụng bản đồ hoặc tìm cửa hàng, km thường phù hợp cho khoảng cách lớn hơn vài trăm mét; m phù hợp khi hiển thị khoảng cách đi bộ ngắn.

Nên thống nhất đơn vị trong request, aggregation và DTO. Nếu sort trả khoảng cách theo km nhưng DTO gắn nhãn mét, client sẽ hiển thị sai dù query vẫn chạy đúng.

## 3. Geo-distance sort: sắp xếp từ gần đến xa

Geo-distance sort xếp document dựa trên khoảng cách từ origin tới geo_point của document.

REST DSL:

~~~http
POST /stores/_search
{
  "query": {
    "term": {
      "active": true
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

Ý nghĩa:

- _geo_distance yêu cầu sort theo khoảng cách địa lý.
- location là field geo_point trong document.
- lat/lon là origin.
- order asc đặt điểm gần nhất trước.
- unit km biểu diễn khoảng cách theo kilômét.
- distance_type arc dùng tính khoảng cách theo cung trên bề mặt Trái Đất.

Nếu đổi order thành desc, document xa hơn sẽ đứng trước. Với tìm kiếm gần nhất, thông thường dùng asc.

### 3.1. Kết hợp geo-distance sort với geo_distance query

Geo-distance sort chỉ sắp xếp các document được query chọn. Nó không tự giới hạn bán kính.

Nếu API chỉ muốn cửa hàng trong 10 km, thêm geo_distance query:

~~~http
POST /stores/_search
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
          "geo_distance": {
            "distance": "10km",
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
        "unit": "km",
        "distance_type": "arc"
      }
    }
  ]
}
~~~

Query geo_distance giới hạn tập kết quả theo bán kính. Sort geo-distance sắp xếp các kết quả còn lại từ gần đến xa.

Đây là pattern phổ biến cho endpoint nearby places:

- Filter theo trạng thái, category, tenant hoặc quyền truy cập.
- Geo-distance query giới hạn bán kính.
- Geo-distance sort xếp hạng theo khoảng cách.
- Search size/Pageable giới hạn số kết quả trả về.

### 3.2. Arc và plane

Elasticsearch có thể dùng hai cách tính khoảng cách thường gặp:

- arc: khoảng cách theo cung trên hình cầu, phù hợp với khoảng cách địa lý tổng quát.
- plane: phép tính phẳng gần đúng, có thể nhanh hơn nhưng sai số tăng khi khoảng cách lớn hoặc vùng địa lý rộng.

Với ứng dụng địa điểm thông thường, arc là lựa chọn an toàn để có khoảng cách địa lý phù hợp. Chỉ chọn plane sau khi đã đo hiệu năng và sai số trên vùng dữ liệu thực tế.

Không nhầm distance_type với unit. distance_type chọn phương pháp tính; unit chọn đơn vị biểu diễn khoảng cách.

### 3.3. Sort trên field có nhiều GeoPoint

Một document có thể chứa nhiều giá trị geo_point. Khi đó Elasticsearch cần xác định khoảng cách nào đại diện cho document.

Geo-distance sort hỗ trợ mode như min, max, avg hoặc sum tùy ngữ cảnh hỗ trợ. Ví dụ:

~~~http
POST /branches/_search
{
  "sort": [
    {
      "_geo_distance": {
        "locations": [
          {
            "lat": 10.7769,
            "lon": 106.7009
          }
        ],
        "order": "asc",
        "unit": "km",
        "mode": "min"
      }
    }
  ]
}
~~~

Với tìm chi nhánh gần nhất trong một tập địa điểm của document, mode min thường là lựa chọn phù hợp. Nếu muốn khoảng cách xa nhất hoặc trung bình, chọn mode tương ứng và diễn giải kết quả đúng nghiệp vụ.

Với một địa điểm duy nhất trên mỗi document, mode không cần thiết trong nhiều trường hợp. Nếu field đa giá trị, hãy xác định rõ distance đại diện cho điểm nào.

### 3.4. Missing geo field và index không đồng nhất

Một số document có thể không có location. Khi tìm trên alias gồm nhiều index, có thể có index không chứa field geo_point hoặc mapping khác nhau.

Geo-distance sort có tùy chọn xử lý field không được mapping trên một số index, như ignore_unmapped. Hãy xác nhận cú pháp của Elasticsearch version và mapping của mọi index đích. Việc bỏ qua field không mapping không biến document thiếu tọa độ thành một vị trí hợp lệ.

Nếu vị trí là bắt buộc trong nghiệp vụ, có thể lọc document có location bằng exists query trước khi sort.

## 4. Lấy khoảng cách từ sort values

Khi dùng _geo_distance trong sort, Elasticsearch trả giá trị sort cho mỗi hit trong thuộc tính sort của response. Giá trị đó là khoảng cách đã tính theo unit được chỉ định.

Response minh họa:

~~~json
{
  "hits": {
    "hits": [
      {
        "_index": "stores",
        "_id": "S-1001",
        "_score": null,
        "_source": {
          "name": "Central Store",
          "location": {
            "lat": 10.7800,
            "lon": 106.7020
          }
        },
        "sort": [
          0.42
        ]
      }
    ]
  }
}
~~~

Trong ví dụ, sort value 0.42 tương ứng 0.42 km vì sort đã khai báo unit km. Response có thể chứa thêm các sort value nếu query có nhiều tiêu chí sort.

Điểm quan trọng: sort value là metadata của hit. Nó không tự động được ghi vào _source và không tự động xuất hiện trong property của entity Store.

Trong Spring Data Elasticsearch, giữ SearchHit để đọc cả content và metadata:

~~~java
SearchHits<Store> hits =
    operations.search(nativeQuery, Store.class);

for (SearchHit<Store> hit : hits) {
    Store store = hit.getContent();

    List<Object> sortValues = hit.getSortValues();

    System.out.println(store.getName());
    System.out.println(sortValues);
}
~~~

SearchHit.getSortValues() là API metadata cần kiểm tra theo phiên bản Spring Data Elasticsearch đang dùng. Giá trị đầu tiên trong ví dụ là geo-distance sort nếu đó là sort đầu tiên. Nếu có nhiều sort, phải đọc đúng vị trí tương ứng với thứ tự sort đã khai báo.

Không ép kiểu sort value thành Double một cách mù quáng. Kiểu Java cụ thể phụ thuộc serializer/client version. Hãy kiểm tra giá trị và kiểu runtime trong integration test, sau đó chuyển đổi có kiểm soát.

### 4.1. Map distance vào DTO

Ví dụ DTO:

~~~java
public record NearbyStore(
    String id,
    String name,
    double distanceKm
) {
}
~~~

Mapping minh họa khi geo-distance là sort đầu tiên và API trả sort value dạng Number:

~~~java
List<NearbyStore> results =
    hits.getSearchHits().stream()
        .map(hit -> {
            Store store = hit.getContent();

            Number rawDistance =
                (Number) hit.getSortValues().get(0);

            return new NearbyStore(
                hit.getId(),
                store.getName(),
                rawDistance.doubleValue()
            );
        })
        .toList();
~~~

Đây là ví dụ cần khớp kiểu sort value của phiên bản đang dùng. Nếu sort list có thêm tiêu chí, hãy dùng index đúng với geo-distance sort. Có thể đóng gói việc đọc sort value trong mapper riêng để tránh lặp chỉ số magic trong service.

### 4.2. Sort values khi có nhiều sort

Ví dụ:

~~~json
{
  "sort": [
    { "_geo_distance": { "location": { "lat": 10.7769, "lon": 106.7009 }, "order": "asc", "unit": "km" } },
    { "name.keyword": "asc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Sort values của hit có thể chứa ba phần theo đúng thứ tự:

1. Khoảng cách.
2. Giá trị name.keyword.
3. Giá trị id.keyword.

Không giả định sort values chỉ có một phần. Khi thay đổi sort definition, cập nhật mapper và test tương ứng.

## 5. Trả khoảng cách mà không dùng geo-distance sort

Có trường hợp API muốn sắp xếp theo giá hoặc relevance nhưng vẫn cần trả khoảng cách. Khi đó sort values không phải cách duy nhất.

Một lựa chọn là dùng script field để tính khoảng cách từ doc values của geo_point. Trong Painless, geo_point có các phương thức khoảng cách như arcDistance trong các context hỗ trợ.

Ví dụ REST DSL:

~~~http
POST /stores/_search
{
  "query": {
    "term": {
      "active": true
    }
  },
  "script_fields": {
    "distance_meters": {
      "script": {
        "lang": "painless",
        "source": "doc['location'].size() == 0 ? null : doc['location'].arcDistance(params.lat, params.lon)",
        "params": {
          "lat": 10.7769,
          "lon": 106.7009
        }
      }
    }
  },
  "sort": [
    {
      "priceInCents": {
        "order": "asc"
      }
    }
  ]
}
~~~

Script field tính khoảng cách cho mỗi hit được trả về, nhưng không thay đổi thứ tự sort theo giá. Kết quả script field nằm trong phần fields của hit, không nằm trong _source.

Phương thức arcDistance thường trả khoảng cách theo mét. Nếu cần km, có thể chia cho 1000 trong script hoặc chuyển đổi ở tầng ứng dụng. Xác nhận kiểu trả về và Painless API trên Elasticsearch version thực tế.

Script field có chi phí tính toán. Nếu geo-distance sort đã là tiêu chí xếp hạng chính, lấy distance từ sort values thường tránh phải duy trì thêm một script field trùng lặp.

### 5.1. Khi nào nên dùng sort value, script field hoặc tính ở Java?

| Nhu cầu | Cách phù hợp |
|---|---|
| Sắp xếp gần nhất và trả khoảng cách | Geo-distance sort, đọc sort values |
| Sắp xếp theo giá nhưng vẫn trả khoảng cách | Script field hoặc tính từ tọa độ được trả về |
| Chỉ lọc trong bán kính, không cần distance | geo_distance query |
| Hiển thị khoảng cách cho số ít kết quả có tọa độ source | Tính ở Java bằng thư viện địa lý đã chọn |
| Tính khoảng cách trong aggregation theo dải | geo_distance aggregation |

Tính ở Java chỉ hợp lý khi ứng dụng có tọa độ của document và chấp nhận tự chịu trách nhiệm về công thức, đơn vị và sai số. Nếu dùng Elasticsearch làm nguồn sort/filter, hãy giữ cùng semantics distance để tránh kết quả hiển thị khác thứ tự.

## 6. Geo-distance aggregation: gom nhóm theo khoảng cách

geo_distance aggregation là bucket aggregation. Nó chia document thành các dải dựa trên khoảng cách từ một origin đến field geo_point.

Ví dụ thống kê số cửa hàng trong các dải:

- Dưới 1 km.
- Từ 1 km đến dưới 5 km.
- Từ 5 km đến dưới 20 km.
- Từ 20 km trở lên.

REST DSL:

~~~http
POST /stores/_search
{
  "size": 0,
  "aggs": {
    "stores_by_distance": {
      "geo_distance": {
        "field": "location",
        "origin": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "unit": "km",
        "ranges": [
          {
            "key": "under_1km",
            "to": 1
          },
          {
            "key": "1_to_5km",
            "from": 1,
            "to": 5
          },
          {
            "key": "5_to_20km",
            "from": 5,
            "to": 20
          },
          {
            "key": "20km_and_more",
            "from": 20
          }
        ]
      }
    }
  }
}
~~~

Mỗi bucket có key, from/to theo cấu hình và doc_count. Có thể dùng kết quả để hiển thị bộ lọc theo khoảng cách hoặc thống kê vùng phủ dịch vụ.

### 6.1. Quy tắc biên của range

Với range aggregation, from là biên bao gồm và to là biên không bao gồm. Các khoảng trên có semantics:

| Key | Khoảng |
|---|---|
| under_1km | distance < 1 km |
| 1_to_5km | 1 km <= distance < 5 km |
| 5_to_20km | 5 km <= distance < 20 km |
| 20km_and_more | distance >= 20 km |

Như vậy, một document đúng 1 km thuộc bucket 1_to_5km, không thuộc under_1km. Một document đúng 5 km thuộc 5_to_20km.

Hãy thiết kế ranges liền kề để tránh khoảng trống hoặc chồng lấn ngoài ý muốn. Nếu các range được cố tình chồng lấn, một document có thể được tính vào nhiều bucket và tổng doc_count có thể lớn hơn số document duy nhất.

### 6.2. Đếm và tính metric trong từng dải

Có thể lồng metric sub-aggregation:

~~~http
POST /stores/_search
{
  "size": 0,
  "aggs": {
    "stores_by_distance": {
      "geo_distance": {
        "field": "location",
        "origin": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "unit": "km",
        "ranges": [
          { "key": "under_1km", "to": 1 },
          { "key": "1_to_5km", "from": 1, "to": 5 },
          { "key": "5_to_20km", "from": 5, "to": 20 }
        ]
      },
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

Kết quả có cấu trúc:

~~~text
stores_by_distance
    |
    +-- under_1km
    |      +-- doc_count
    |      +-- by_category
    |
    +-- 1_to_5km
    |      +-- doc_count
    |      +-- by_category
    |
    +-- 5_to_20km
           +-- doc_count
           +-- by_category
~~~

Có thể thay terms aggregation bằng sum, avg, min, max hoặc metric phù hợp với dữ liệu. Ví dụ nếu Store có rating dạng số, có thể tính rating trung bình cho từng dải khoảng cách.

### 6.3. Filter trước khi tổng hợp

Nếu chỉ muốn thống kê cửa hàng đang hoạt động, dùng query/filter ở cấp request:

~~~http
POST /stores/_search
{
  "size": 0,
  "query": {
    "term": {
      "active": true
    }
  },
  "aggs": {
    "stores_by_distance": {
      "geo_distance": {
        "field": "location",
        "origin": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "unit": "km",
        "ranges": [
          { "key": "under_1km", "to": 1 },
          { "key": "1_to_5km", "from": 1, "to": 5 },
          { "key": "5_to_20km", "from": 5, "to": 20 }
        ]
      }
    }
  }
}
~~~

Query cấp cao giới hạn tập document được đưa vào aggregation. Nếu muốn có nhiều thống kê khác nhau trong cùng response, dùng filter aggregation hoặc filters aggregation làm các nhánh riêng.

### 6.4. Document có nhiều điểm địa lý

Nếu field location chứa nhiều geo_point, cần xác định semantics nghiệp vụ. Một cửa hàng có thể có nhiều chi nhánh hoặc một document có nhiều vị trí. Khi đó khoảng cách gần nhất, xa nhất hay việc document có điểm bất kỳ nằm trong range đều có thể dẫn tới cách diễn giải khác nhau.

Với dữ liệu nhiều điểm, hãy xác nhận hành vi của geo_distance aggregation trên phiên bản Elasticsearch đang dùng và cân nhắc mô hình hóa mỗi chi nhánh thành một document riêng nếu báo cáo cần đếm từng địa điểm. Tránh đếm một document nhiều lần ngoài ý muốn.

## 7. Khác nhau giữa geo_distance query, sort và aggregation

Ba tính năng cùng dùng khoảng cách nhưng có nhiệm vụ khác nhau:

| Tính năng | Câu hỏi trả lời | Kết quả |
|---|---|---|
| geo_distance query | Document có nằm trong bán kính không? | Tập document được lọc |
| _geo_distance sort | Document nào gần hơn? | Thứ tự hit và sort values |
| geo_distance aggregation | Có bao nhiêu document ở từng dải khoảng cách? | Bucket và doc_count/metric |

Một request có thể kết hợp cả ba:

- geo_distance query giới hạn cửa hàng trong 20 km.
- _geo_distance sort đưa cửa hàng gần nhất lên đầu.
- geo_distance aggregation đếm số cửa hàng theo các dải 0–1, 1–5, 5–20 km.

Ví dụ:

~~~http
POST /stores/_search
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
          "geo_distance": {
            "distance": "20km",
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
        "unit": "km",
        "distance_type": "arc"
      }
    },
    {
      "id.keyword": "asc"
    }
  ],
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
          { "key": "under_1km", "to": 1 },
          { "key": "1_to_5km", "from": 1, "to": 5 },
          { "key": "5_to_20km", "from": 5, "to": 20 }
        ]
      }
    }
  }
}
~~~

Trong ví dụ này, aggregation chạy trên tập document được query chọn, tức chỉ các cửa hàng active trong 20 km. Nếu muốn thống kê tất cả cửa hàng theo dải khoảng cách trong khi hits chỉ hiển thị một tập đã lọc khác, cần thiết kế aggregation scope phù hợp, chẳng hạn filter aggregation hoặc global aggregation có chủ đích.

## 8. NativeQuery với geo-distance sort trong Spring Data Elasticsearch

Với Spring Data Elasticsearch 5.x, NativeQuery dùng các kiểu từ Elasticsearch Java API Client. Geo-distance sort được biểu diễn bằng SortOptions và GeoLocation.

Ví dụ minh họa:

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch._types.DistanceUnit;
import co.elastic.clients.elasticsearch._types.GeoDistance;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.SortMode;
import co.elastic.clients.elasticsearch._types.GeoLocation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

double originLat = 10.7769;
double originLon = 106.7009;

GeoLocation origin = GeoLocation.of(g -> g
    .latlon(p -> p
        .lat(originLat)
        .lon(originLon)
    )
);

SortOptions distanceSort = SortOptions.of(s -> s
    .geoDistance(g -> g
        .field("location")
        .location(origin)
        .order(SortOrder.Asc)
        .unit(DistanceUnit.Kilometers)
        .distanceType(GeoDistance.Arc)
        .mode(SortMode.Min)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(activeAndNearbyQuery)
    .withSort(List.of(distanceSort))
    .build();

SearchHits<Store> hits =
    operations.search(nativeQuery, Store.class);
~~~

Đây là ví dụ theo thế hệ Spring Data Elasticsearch 5.x cùng Elasticsearch Java API Client. Package, overload location và builder method có thể khác giữa các minor version. Hãy dùng autocomplete/Javadoc của dependency thực tế để xác nhận chữ ký. Không trộn SortOptions của Elasticsearch Java API Client với Sort của Spring Data Commons trong cùng builder.

Nếu cần sort phụ ổn định, thêm SortOptions field sort sau distanceSort:

~~~java
SortOptions idSort = SortOptions.of(s -> s
    .field(f -> f
        .field("id.keyword")
        .order(SortOrder.Asc)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(activeAndNearbyQuery)
    .withSort(List.of(distanceSort, idSort))
    .build();
~~~

Distance vẫn là tiêu chí đầu tiên; ID chỉ phân xử khi khoảng cách bằng nhau.

## 9. NativeQuery với geo_distance aggregation

Elasticsearch Java API Client có kiểu builder cho geo_distance aggregation. Cấu trúc DSL cần tạo ra tương đương ví dụ REST:

~~~java
import co.elastic.clients.elasticsearch._types.DistanceUnit;
import co.elastic.clients.elasticsearch._types.GeoLocation;
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import co.elastic.clients.elasticsearch._types.aggregations.GeoDistanceAggregationRange;

GeoLocation origin = GeoLocation.of(g -> g
    .latlon(p -> p
        .lat(originLat)
        .lon(originLon)
    )
);

Aggregation distanceBands = Aggregation.of(a -> a
    .geoDistance(g -> g
        .field("location")
        .origin(origin)
        .unit(DistanceUnit.Kilometers)
        .ranges(
            GeoDistanceAggregationRange.of(r -> r
                .key("under_1km")
                .to(1.0)
            ),
            GeoDistanceAggregationRange.of(r -> r
                .key("1_to_5km")
                .from(1.0)
                .to(5.0)
            ),
            GeoDistanceAggregationRange.of(r -> r
                .key("5_to_20km")
                .from(5.0)
                .to(20.0)
            )
        )
    )
);
~~~

Sau đó gắn aggregation vào NativeQuery:

~~~java
NativeQuery aggregationQuery = NativeQuery.builder()
    .withQuery(activeQuery)
    .withAggregation("distance_bands", distanceBands)
    .withMaxResults(0)
    .build();
~~~

Tên kiểu GeoDistanceAggregationRange, overload ranges và cách đặt max results cần khớp với Elasticsearch Java API Client/Spring Data Elasticsearch version trong dự án. Nếu IDE không nhận một overload, kiểm tra Javadoc của Aggregation.Builder và GeoDistanceAggregation.Builder. REST DSL ở các ví dụ trước là chuẩn tham chiếu để xác nhận cấu trúc request cuối cùng.

## 10. Đọc geo-distance sort value từ SearchHit

Khi thực hiện search bằng Operations:

~~~java
SearchHits<Store> hits =
    operations.search(nativeQuery, Store.class);
~~~

Có thể đọc từng hit:

~~~java
for (SearchHit<Store> hit : hits) {
    String id = hit.getId();
    Store store = hit.getContent();
    List<Object> sortValues = hit.getSortValues();

    // Geo-distance sort value nằm tại vị trí của sort đó.
}
~~~

Nên tạo một hàm chuyển đổi riêng:

~~~java
private double readDistanceKm(SearchHit<?> hit, int sortIndex) {
    Object raw = hit.getSortValues().get(sortIndex);

    if (!(raw instanceof Number number)) {
        throw new IllegalStateException(
            "Geo-distance sort value is not numeric"
        );
    }

    return number.doubleValue();
}
~~~

Nếu project dùng Java thấp hơn 16, thay pattern matching instanceof bằng cách cast Number sau khi kiểm tra kiểu.

Không hard-code sortIndex = 0 ở nhiều nơi. Hãy định nghĩa thứ tự sort trong một chỗ và để mapper biết distance sort nằm ở vị trí nào. Khi thêm sort phụ ở trước, vị trí distance value có thể thay đổi.

### 10.1. Chuyển đổi sang mét hoặc kilômét

Nếu query khai báo unit km, sort value thường biểu diễn km. Nếu query khai báo unit m, sort value biểu diễn mét.

Có thể chuẩn hóa response:

~~~java
double distanceKm = distanceValueInMeters / 1000.0;
~~~

Không chuyển đổi hai lần. Nên đặt tên biến có đơn vị rõ ràng như distanceMeters hoặc distanceKm thay vì distance chung chung.

### 10.2. Định dạng khoảng cách để hiển thị

DTO nên giữ giá trị số để client có thể dùng cho logic hoặc bản đồ:

~~~java
public record NearbyStoreResponse(
    String id,
    String name,
    double distanceMeters,
    String distanceLabel
) {
}
~~~

Service có thể tạo label:

- 350 m
- 1.2 km
- 8.4 km

Quy tắc làm tròn nên thuộc tầng presentation hoặc API mapper. Không làm tròn trước khi sort hoặc tính bucket, vì điều đó có thể làm nhiều khoảng cách khác nhau trở thành cùng giá trị và gây sai thứ tự.

## 11. Geo bounds và các aggregation không gian liên quan

Ngoài geo_distance aggregation, Elasticsearch có các bucket/metric aggregation khác để phân tích vị trí:

- geo_bounds: trả bounding box bao quanh các điểm.
- geohash_grid: gom điểm theo ô geohash.
- geotile_grid: gom điểm theo tile của bản đồ.
- geo_centroid: tính tâm địa lý của các điểm.

Ví dụ geo_bounds:

~~~http
POST /stores/_search
{
  "size": 0,
  "aggs": {
    "store_bounds": {
      "geo_bounds": {
        "field": "location",
        "wrap_longitude": true
      }
    }
  }
}
~~~

geo_bounds hữu ích khi muốn xác định vùng bao quanh tập cửa hàng để điều chỉnh viewport bản đồ. Nó không trả khoảng cách từng cửa hàng tới origin.

Ví dụ geotile_grid:

~~~http
POST /stores/_search
{
  "size": 0,
  "aggs": {
    "stores_per_tile": {
      "geotile_grid": {
        "field": "location",
        "precision": 7
      }
    }
  }
}
~~~

geotile_grid gom điểm theo tile, hữu ích cho heatmap hoặc bản đồ có mật độ cao. Precision càng lớn thì tile càng nhỏ và số bucket có thể tăng.

Nếu câu hỏi nghiệp vụ là “bao nhiêu cửa hàng trong bán kính 1 km, 5 km, 20 km”, dùng geo_distance aggregation. Nếu câu hỏi là “cửa hàng tập trung ở vùng bản đồ nào”, xem xét geotile_grid hoặc geohash_grid.

## 12. Pagination khi sort theo khoảng cách

Có thể dùng from/size cho trang đầu và các trang tiếp theo:

~~~http
POST /stores/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "geo_distance": {
      "distance": "20km",
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
        "unit": "km"
      }
    },
    {
      "id.keyword": "asc"
    }
  ]
}
~~~

Với tập dữ liệu lớn, from/size sâu có chi phí. Có thể dùng search_after với sort values của hit cuối trang trước.

Ví dụ hit cuối có sort values:

~~~json
[2.75, "S-1020"]
~~~

Trang kế tiếp:

~~~http
POST /stores/_search
{
  "size": 20,
  "search_after": [2.75, "S-1020"],
  "query": {
    "geo_distance": {
      "distance": "20km",
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
        "unit": "km"
      }
    },
    {
      "id.keyword": "asc"
    }
  ]
}
~~~

Các quy tắc:

- Giữ nguyên query, origin, unit và sort giữa các trang.
- Truyền đúng sort values từ hit cuối trang trước.
- Thêm unique tie-breaker như id.keyword.
- Không tự tính lại sort value từ source.
- Nếu cần snapshot nhất quán trong khi index thay đổi, cân nhắc Point in Time (PIT) cùng search_after khi Elasticsearch version hỗ trợ.

Nếu origin thay đổi giữa các trang, distance sort values không còn cùng hệ quy chiếu. Vì vậy origin cần được giữ ổn định trong toàn bộ phiên phân trang.

## 13. Kết hợp relevance và khoảng cách

Một ứng dụng có thể tìm cửa hàng theo tên hoặc mô tả, nhưng muốn ưu tiên cửa hàng gần người dùng. Có nhiều chiến lược:

- Sort khoảng cách trước, relevance phân xử khi khoảng cách bằng nhau.
- Sort _score trước, khoảng cách phân xử khi score bằng nhau.
- Dùng function_score hoặc distance_feature để đưa độ gần vào score.
- Lọc bán kính bằng geo_distance, sau đó sort theo relevance.

Ví dụ khoảng cách là ưu tiên chính:

~~~http
POST /stores/_search
{
  "query": {
    "match": {
      "name": "coffee"
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
    {
      "_score": "desc"
    },
    {
      "id.keyword": "asc"
    }
  ]
}
~~~

Ví dụ relevance là ưu tiên chính:

~~~http
POST /stores/_search
{
  "query": {
    "match": {
      "name": "coffee"
    }
  },
  "sort": [
    {
      "_score": "desc"
    },
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
      "id.keyword": "asc"
    }
  ]
}
~~~

Thứ tự trong sort array là thứ tự ưu tiên. Không thể chỉ bật một tùy chọn để Elasticsearch tự hiểu rằng gần và liên quan cần cân bằng theo nghiệp vụ. Nếu muốn hai yếu tố cùng ảnh hưởng vào một score, cần thiết kế function_score/distance_feature và đánh giá ranking trên dữ liệu thực tế.

## 14. Distance feature và function score

Elasticsearch có query distance_feature để tăng score của document gần một origin hơn đối với một field date hoặc geo_point được hỗ trợ.

Ví dụ khái niệm:

~~~http
POST /stores/_search
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
      "should": [
        {
          "distance_feature": {
            "field": "location",
            "origin": {
              "lat": 10.7769,
              "lon": 106.7009
            },
            "pivot": "5km"
          }
        }
      ]
    }
  },
  "sort": [
    { "_score": "desc" }
  ]
}
~~~

distance_feature tạo tín hiệu score dựa trên khoảng cách. pivot điều khiển cách score giảm theo khoảng cách. Nó phù hợp khi muốn relevance và proximity cùng tác động vào thứ hạng thay vì sort theo một tiêu chí tuyệt đối.

Cần hiểu distance_feature là cơ chế ranking, không phải cách trả khoảng cách thực tế cho client. Nếu API cần con số km cụ thể, vẫn cần geo-distance sort value, script field hoặc tính toán từ tọa độ.

function_score linh hoạt hơn, có thể kết hợp query score với decay function trên geo_point hoặc các field khác. Cấu hình score có thể thay đổi mạnh thứ hạng; hãy kiểm tra bằng Explain và tập truy vấn đánh giá thay vì chọn pivot/weight theo cảm tính.

## 15. Hiệu năng và giới hạn

Geo-distance sort, aggregation và script field đều có chi phí. Các yếu tố ảnh hưởng:

- Số document ứng viên.
- Số shard và index được truy vấn.
- Số hit cần sort/trả về.
- Số field geo_point và số điểm trong mỗi document.
- Distance type và unit.
- Số bucket của geo_distance aggregation.
- Số tầng sub-aggregation.
- Script field có được tính trên nhiều hit hay không.
- Phân trang sâu.

Một số nguyên tắc:

- Giới hạn bán kính bằng geo_distance query khi nghiệp vụ có phạm vi cụ thể.
- Dùng filter cho điều kiện category, active, tenant và quyền truy cập.
- Giới hạn size/page size.
- Chỉ yêu cầu aggregation cần thiết.
- Giữ số range bucket vừa đủ cho UI.
- Dùng sort value thay script field khi đã sort theo distance.
- Thêm tie-breaker ổn định khi phân trang.
- Đo query với dữ liệu gần quy mô production.

Nếu aggregation lồng nhiều chiều, số bucket có thể tăng nhanh và bị giới hạn bởi search.max_buckets. Đừng tạo hàng nghìn dải khoảng cách khi UI chỉ cần vài nhóm.

## 16. Kiểm thử khoảng cách và thứ tự

Integration test nên tạo các điểm ở khoảng cách khác nhau quanh một origin. Không cần hard-code khoảng cách chính xác đến nhiều chữ số nếu test phụ thuộc cách tính và phiên bản; hãy kiểm tra thứ tự và bucket phù hợp.

Ví dụ dữ liệu:

~~~java
GeoPoint origin = new GeoPoint(10.7769, 106.7009);

Store near = new Store(
    "S-NEAR",
    "Nearby Store",
    "grocery",
    true,
    new GeoPoint(10.7770, 106.7010)
);

Store far = new Store(
    "S-FAR",
    "Far Store",
    "grocery",
    true,
    new GeoPoint(10.9000, 106.9000)
);
~~~

Lưu document và refresh index trong test trước khi search:

~~~java
operations.save(List.of(near, far));
operations.indexOps(Store.class).refresh();
~~~

Sau đó chạy geo-distance sort và xác nhận:

- S-NEAR đứng trước S-FAR.
- Sort value là số và có đơn vị đúng.
- Document thiếu location được xử lý theo chính sách.
- Kết quả ngoài bán kính bị geo_distance query loại.
- Sort phụ tạo thứ tự ổn định khi hai điểm có khoảng cách bằng nhau hoặc rất gần nhau.

Với geo_distance aggregation, tạo document ở mỗi phía của ranh giới, ví dụ 0.5 km, 1 km, 3 km và 7 km. Xác nhận doc_count ở đúng bucket. Test biên chính xác giúp phát hiện nhầm inclusive/exclusive.

## 17. Đọc aggregation và sort metadata trong Spring Data

Một search response có thể chứa cả hits và aggregations. SearchHit giữ content cùng metadata của từng document; SearchHits giữ danh sách hit và aggregation container.

Mẫu đọc sort values:

~~~java
for (SearchHit<Store> hit : searchHits) {
    Store store = hit.getContent();
    List<Object> sortValues = hit.getSortValues();

    // Map content and geo-distance value into response DTO.
}
~~~

Mẫu đọc aggregation:

~~~java
SearchHits<Store> searchHits =
    operations.search(aggregationQuery, Store.class);

AggregationsContainer<?> container =
    searchHits.getAggregations();
~~~

Trong Spring Data Elasticsearch 5.x với Elasticsearch Java API Client, container thường là ElasticsearchAggregations. Có thể lấy aggregate theo tên rồi đọc đúng variant geo-distance. Tên wrapper, accessor và kiểu bucket thay đổi theo client version.

Đối với geo_distance aggregation, response có bucket list với key, from, to và doc_count. Nếu lồng metric aggregation, mỗi bucket có thêm aggregate con. Hãy map kết quả thành DTO ứng dụng thay vì trả union type của Elasticsearch client trực tiếp qua REST API.

## 18. Lựa chọn cách trả khoảng cách phù hợp

| API cần | Nên dùng |
|---|---|
| Danh sách gần nhất và khoảng cách cho từng hit | _geo_distance sort + SearchHit sort values |
| Danh sách sắp xếp theo giá nhưng vẫn hiển thị khoảng cách | Script field hoặc tính từ tọa độ source |
| Chỉ lọc trong bán kính | geo_distance query |
| Đếm địa điểm theo dải khoảng cách | geo_distance aggregation |
| Phân tích mật độ theo vùng bản đồ | geotile_grid hoặc geohash_grid |
| Trả vùng bao quanh kết quả | geo_bounds |
| Kết hợp relevance và proximity | distance_feature/function_score hoặc sort nhiều tiêu chí |
| Phân trang sâu theo khoảng cách | search_after + sort ổn định, cân nhắc PIT |

Một endpoint tìm địa điểm thường nên trả một con số khoảng cách có đơn vị rõ ràng, ví dụ distanceMeters hoặc distanceKm. Đừng trả một số không có đơn vị rồi để frontend tự đoán.

## 19. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Geo-distance sort lỗi | location không phải geo_point | Kiểm tra mapping |
| Cửa hàng xa đứng trước | Dùng order desc thay vì asc | Dùng asc cho gần nhất trước |
| Sort đúng nhưng không giới hạn bán kính | Chỉ có sort, thiếu geo_distance query | Thêm geo_distance filter |
| Khoảng cách sai rất lớn | Đảo latitude và longitude | Kiểm tra quy ước constructor, JSON object và array |
| Khoảng cách hiển thị sai đơn vị | Query dùng km nhưng DTO ghi m hoặc ngược lại | Chuẩn hóa unit và tên field |
| Không đọc được distance từ entity | Distance nằm trong hit sort metadata | Đọc SearchHit.getSortValues() |
| Sort value đọc sai vị trí | Có nhiều tiêu chí sort | Dùng đúng index theo sort definition |
| Document nhiều location có thứ tự bất ngờ | Chưa xác định mode min/max/avg | Chọn mode theo nghiệp vụ |
| Aggregation thiếu bucket | Range không phủ hết khoảng hoặc document thiếu location | Kiểm tra ranges và dữ liệu |
| Tổng doc_count lớn hơn số document | Range chồng lấn hoặc document có nhiều điểm | Kiểm tra semantics và mapping |
| NativeQuery không biên dịch | API client version hoặc import khác | Kiểm tra Javadoc và package |
| search_after trùng/thiếu hit | Thiếu tie-breaker hoặc thay origin/sort | Giữ nguyên query và sort, thêm unique field |
| Script field chậm | Tính khoảng cách cho quá nhiều hit | Dùng sort values hoặc giới hạn hit |
| Aggregation vượt giới hạn bucket | Quá nhiều range hoặc nested bucket | Giảm bucket và phạm vi |

## 20. Quy trình thiết kế endpoint nearby

Một endpoint tìm cửa hàng gần người dùng có thể được thiết kế theo trình tự:

1. Nhận latitude và longitude từ client.
2. Validate tọa độ và xác định origin.
3. Xác định bán kính tối đa và đơn vị thống nhất.
4. Tạo bool filter cho trạng thái, category, tenant và quyền truy cập.
5. Thêm geo_distance query để giới hạn bán kính.
6. Thêm _geo_distance sort asc để xếp cửa hàng gần nhất trước.
7. Thêm unique keyword tie-breaker để thứ tự ổn định.
8. Giới hạn page size.
9. Đọc distance từ SearchHit sort values và map sang DTO.
10. Nếu UI cần thống kê, thêm geo_distance aggregation với các dải không chồng lấn.
11. Nếu phân trang sâu, dùng search_after và giữ origin/query/sort cố định.
12. Viết integration test cho tọa độ, đơn vị, ranh giới range và kết quả sort.

Một response DTO có thể như sau:

~~~java
public record NearbyStoreResponse(
    String id,
    String name,
    String category,
    double distanceMeters
) {
}
~~~

Nếu API cần nhãn hiển thị, có thể thêm distanceLabel ở tầng mapper. Giữ giá trị số gốc để client có thể sắp xếp hoặc xử lý chính xác.

## 21. Bảng tra cứu nhanh

| Mục đích | Elasticsearch |
|---|---|
| Lọc điểm trong bán kính | geo_distance query |
| Sắp xếp gần nhất trước | _geo_distance sort với order asc |
| Sắp xếp xa nhất trước | _geo_distance sort với order desc |
| Chọn cách tính địa lý | distance_type arc/plane |
| Chọn đơn vị | unit m/km/mi/... |
| Chọn điểm gần nhất trong field nhiều giá trị | mode min |
| Lấy khoảng cách của từng hit | sort values trong SearchHit |
| Trả khoảng cách dù sort theo field khác | script_fields hoặc tính từ tọa độ source |
| Gom nhóm theo dải khoảng cách | geo_distance aggregation |
| Tổng hợp theo danh mục trong từng dải | Sub-aggregation |
| Lấy bounding box | geo_bounds |
| Gom điểm theo tile bản đồ | geotile_grid |
| Kết hợp relevance và khoảng cách | distance_feature/function_score hoặc multi-sort |
| Phân trang sâu | search_after và unique tie-breaker |

Geo-distance query, sort và aggregation cùng dựa trên geo_point nhưng có nhiệm vụ riêng: query giới hạn phạm vi, sort xếp hạng theo khoảng cách và aggregation thống kê theo dải. Khi cần trả khoảng cách cho từng kết quả, geo-distance sort cung cấp sort value có đơn vị đã chọn; Spring Data giữ giá trị đó trong SearchHit metadata, không tự ghi vào entity. Hãy thống nhất origin, latitude/longitude, unit và distance semantics giữa query, sort, aggregation và DTO; thêm tie-breaker ổn định cho phân trang và chỉ dùng script field khi cần khoảng cách độc lập với sort.

