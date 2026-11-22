# Kiểm thử điểm biên, dữ liệu thiếu và độ chính xác địa lý

Các truy vấn địa lý thường có vẻ đơn giản: tìm địa điểm trong bán kính 5 km, tìm điểm nằm trong một hình chữ nhật hoặc kiểm tra một vị trí có thuộc vùng phục vụ hay không. Nhưng kết quả có thể sai nếu ứng dụng đảo thứ tự latitude/longitude, bỏ qua tọa độ thiếu, làm tròn tọa độ quá sớm hoặc giả định rằng một điểm nằm đúng biên luôn được xử lý giống nhau trên mọi phép toán không gian.

Khi dùng Spring Data Elasticsearch, cần kiểm thử cả dữ liệu đầu vào, mapping và kết quả query trên Elasticsearch thật. Các trường hợp quan trọng gồm:

- Điểm nằm bên trong, bên ngoài và đúng trên biên của vùng tìm kiếm.
- Field địa lý bị thiếu, có giá trị null, mảng rỗng hoặc tọa độ không hợp lệ.
- Tọa độ gần đường đổi ngày quốc tế, cực Bắc/Nam hoặc ranh giới vùng.
- Sai số do độ chính xác tọa độ, phép tính khoảng cách và cách làm tròn.
- Khác biệt giữa `geo_distance`, `geo_bounding_box` và `geo_shape`.

Bài học sử dụng `geo_point` làm ví dụ chính và áp dụng cho các bài kiểm thử địa lý trong Spring Data Elasticsearch.

## 1. Dữ liệu địa lý trong Elasticsearch

Elasticsearch hỗ trợ nhiều kiểu dữ liệu địa lý. Hai kiểu phổ biến là:

| Kiểu | Lưu trữ | Truy vấn thường dùng |
|---|---|---|
| `geo_point` | Một điểm latitude/longitude | Khoảng cách, bounding box, sort theo khoảng cách |
| `geo_shape` | Hình học như point, line, polygon, multipolygon | Giao nhau, nằm trong, chứa, disjoint |

Một cửa hàng thường chỉ cần một điểm tọa độ:

~~~json
{
  "storeId": "STORE-001",
  "name": "District 1 Store",
  "location": {
    "lat": 10.762622,
    "lon": 106.660172
  }
}
~~~

Một vùng giao hàng có thể cần polygon:

~~~json
{
  "serviceArea": {
    "type": "polygon",
    "coordinates": [
      [
        [106.65, 10.75],
        [106.68, 10.75],
        [106.68, 10.78],
        [106.65, 10.78],
        [106.65, 10.75]
      ]
    ]
  }
}
~~~

Với `geo_point`, thứ tự latitude và longitude là vấn đề thường gặp. Với GeoJSON và tọa độ trong mảng, thứ tự là **longitude trước, latitude sau**. Với object có tên thuộc tính, Elasticsearch dùng `lat` và `lon`. Không được suy luận thứ tự chỉ từ hai con số.

## 2. Khai báo geo_point trong Spring Data Elasticsearch

Có thể dùng kiểu `GeoPoint` của Spring Data Elasticsearch và khai báo field bằng `FieldType.GeoPoint`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "stores")
public class StoreDocument {

    @Id
    private String id;

    private String name;

    @Field(type = FieldType.GeoPoint)
    private GeoPoint location;

    // Constructors, getters and setters
}
~~~

Tạo điểm bằng constructor nhận latitude trước, longitude sau:

~~~java
GeoPoint location = new GeoPoint(10.762622, 106.660172);
~~~

Cần kiểm tra lại chữ ký constructor của kiểu GeoPoint theo phiên bản Spring Data Elasticsearch mà dự án đang dùng. Khi tự xây DTO hoặc parser, nên đặt tên tham số rõ ràng là `latitude` và `longitude`, tránh dùng hai biến chung chung như `x` và `y`.

Mapping Elasticsearch tương ứng có dạng:

~~~json
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
~~~

Không nên để field vị trí bị dynamic mapping suy luận thành object thông thường. Hãy khai báo `geo_point` rõ ràng trước khi ghi dữ liệu.

## 3. Các định dạng tọa độ và thứ tự latitude/longitude

Elasticsearch chấp nhận một số cách biểu diễn `geo_point`. Cần hiểu đúng thứ tự của từng định dạng.

| Định dạng | Ví dụ | Thứ tự |
|---|---|---|
| Object | `{"lat":10.76,"lon":106.66}` | Tên thuộc tính rõ ràng |
| Array | `[106.66,10.76]` | longitude, latitude |
| String | `"10.76,106.66"` | latitude, longitude |
| WKT | `"POINT (106.66 10.76)"` | longitude, latitude |
| GeoJSON Point | `{"type":"Point","coordinates":[106.66,10.76]}` | longitude, latitude |

Ví dụ hai cách biểu diễn cùng một điểm:

~~~json
{
  "location": {
    "lat": 10.762622,
    "lon": 106.660172
  }
}
~~~

~~~json
{
  "location": [
    106.660172,
    10.762622
  ]
}
~~~

Nếu đảo thành `[10.762622, 106.660172]`, Elasticsearch vẫn có thể nhận vì cả hai con số đều nằm trong miền hợp lệ, nhưng điểm sẽ nằm ở vị trí địa lý hoàn toàn khác. Đây là lỗi nguy hiểm vì request không nhất thiết bị từ chối.

Nên chọn một định dạng thống nhất trong ứng dụng. Object có tên `lat` và `lon` thường dễ đọc và ít gây nhầm lẫn nhất khi lưu JSON.

## 4. Kiểm tra miền tọa độ hợp lệ

Với hệ tọa độ địa lý thông dụng:

- Latitude nằm trong khoảng từ -90 đến 90 độ.
- Longitude nằm trong khoảng từ -180 đến 180 độ.
- Latitude 0 và longitude 0 đều là giá trị hợp lệ.
- Điểm `(0, 0)` là một vị trí địa lý thực tế, không có nghĩa là dữ liệu bị thiếu.

Ví dụ validation trong Java:

~~~java
public record Coordinates(double latitude, double longitude) {

    public Coordinates {
        if (!Double.isFinite(latitude)
                || latitude < -90.0
                || latitude > 90.0) {
            throw new IllegalArgumentException(
                    "Latitude must be between -90 and 90"
            );
        }

        if (!Double.isFinite(longitude)
                || longitude < -180.0
                || longitude > 180.0) {
            throw new IllegalArgumentException(
                    "Longitude must be between -180 and 180"
            );
        }
    }
}
~~~

Cần kiểm tra cả `NaN`, `Infinity` và `-Infinity`. Chúng không phải tọa độ hợp lệ. Nếu nhận dữ liệu từ JSON, GPS hoặc một dịch vụ bản đồ, hãy validate ngay ở ranh giới hệ thống trước khi tạo entity.

Không nên tự động thay tọa độ sai bằng `(0, 0)`. Việc đó biến dữ liệu lỗi thành một điểm hợp lệ và làm kết quả tìm kiếm địa lý sai mà khó phát hiện.

## 5. Dữ liệu thiếu và ý nghĩa của exists query

Field địa lý có thể bị thiếu trong nhiều tình huống:

- Document không có thuộc tính `location`.
- JSON gửi `"location": null`.
- Giá trị được biểu diễn thành mảng rỗng.
- Dữ liệu bị bỏ qua trong quá trình lập chỉ mục do cấu hình mapping.
- Một index trong alias chưa có mapping cho field đó.

Với `geo_point`, exists query kiểm tra xem field có giá trị địa lý được lập chỉ mục hay không.

Tìm cửa hàng có tọa độ:

~~~json
{
  "query": {
    "exists": {
      "field": "location"
    }
  }
}
~~~

Tìm cửa hàng thiếu tọa độ:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "location"
          }
        }
      ]
    }
  }
}
~~~

Phân biệt các trường hợp:

| Dữ liệu | Kết quả exists trên location |
|---|---|
| Không có field | Không khớp |
| `"location": null` | Không khớp theo mặc định |
| Mảng rỗng | Không có giá trị để lập chỉ mục |
| Điểm `(0, 0)` | Khớp; đây là tọa độ hợp lệ |
| Một geo_point hợp lệ | Khớp |

Exists không kiểm tra thuộc tính có mặt trong JSON gốc. Nó kiểm tra giá trị có thể được tìm thấy trong cấu trúc lập chỉ mục hay không. Nếu mapping hoặc quá trình index bỏ qua giá trị, document có thể vẫn chứa dữ liệu trong `_source` nhưng không khớp exists.

### Kết hợp exists với truy vấn địa lý

Nếu chỉ muốn tìm cửa hàng có tọa độ và nằm trong bán kính, có thể thêm điều kiện tồn tại cùng query địa lý:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "exists": {
            "field": "location"
          }
        },
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.762622,
              "lon": 106.660172
            }
          }
        }
      ]
    }
  }
}
~~~

Trong ví dụ này, exists làm rõ điều kiện nghiệp vụ và giúp phân biệt document có vị trí với document không có vị trí. Bản thân geo query cũng chỉ có thể khớp những giá trị địa lý được lập chỉ mục.

## 6. Xử lý tọa độ không hợp lệ và ignore_malformed

Theo mặc định, một giá trị `geo_point` không hợp lệ có thể khiến thao tác index document thất bại. Mapping có thể cấu hình `ignore_malformed` để bỏ qua giá trị lỗi thay vì từ chối toàn bộ document:

~~~json
{
  "mappings": {
    "properties": {
      "location": {
        "type": "geo_point",
        "ignore_malformed": true
      }
    }
  }
}
~~~

Khi bật tùy chọn này, cần hiểu rằng dữ liệu vị trí sai có thể không được lập chỉ mục như mong đợi. Document vẫn có thể được lưu với các field khác, trong khi geo query không tìm thấy location của nó.

Không nên bật `ignore_malformed` chỉ để tránh lỗi đầu vào. Với dữ liệu giao hàng, vị trí cửa hàng hoặc vùng phục vụ, một tọa độ bị bỏ qua có thể gây sai kết quả nghiệp vụ.

Nên có hai lớp kiểm soát:

1. Validate tọa độ trong ứng dụng và trả lỗi rõ ràng cho nguồn dữ liệu.
2. Dùng mapping để xác định Elasticsearch phải từ chối hay bỏ qua giá trị không hợp lệ.

Nếu cần giữ document nhưng đánh dấu vị trí chưa hợp lệ, lưu thêm trạng thái riêng như `locationStatus` hoặc `locationValidationError`. Không dùng một tọa độ giả để thay thế.

## 7. Kiểm thử điểm bên trong, bên ngoài và đúng biên geo_distance

Geo distance query tìm các document có điểm nằm trong một bán kính tính từ tâm.

Ví dụ:

~~~json
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.762622,
        "lon": 106.660172
      }
    }
  }
}
~~~

Với bán kính 5 km, cần có ít nhất ba nhóm test:

- Điểm chắc chắn nằm bên trong, ví dụ cách tâm 4,9 km.
- Điểm nằm đúng trên ngưỡng 5 km.
- Điểm chắc chắn nằm bên ngoài, ví dụ cách tâm 5,1 km.

Không nên chỉ kiểm tra một điểm ở rất gần tâm và một điểm ở rất xa. Lỗi biên thường xuất hiện do chuyển đổi đơn vị, làm tròn tọa độ hoặc cách xử lý khoảng cách.

### Bộ dữ liệu kiểm thử đề xuất

| Trường hợp | Vị trí so với tâm | Kết quả mong đợi |
|---|---|---|
| Tại tâm | 0 m | Khớp |
| Bên trong | Nhỏ hơn bán kính một khoảng rõ ràng | Khớp |
| Gần biên phía trong | Bán kính trừ epsilon | Khớp |
| Đúng biên | Bằng bán kính theo dữ liệu test | Xác nhận semantics của phiên bản |
| Gần biên phía ngoài | Bán kính cộng epsilon | Không khớp |
| Bên ngoài | Lớn hơn bán kính một khoảng rõ ràng | Không khớp |
| Thiếu location | Không có geo value | Không khớp |

Geo distance query thường được hiểu là khoảng cách không vượt quá bán kính. Tuy nhiên, test đúng biên cần dùng dữ liệu được tạo có kiểm soát và chạy trên đúng phiên bản Elasticsearch của dự án. Không nên dựa vào một tọa độ được làm tròn trên bản đồ rồi coi đó là chính xác tuyệt đối ở ngưỡng mét.

### Đừng dùng tọa độ làm tròn để tạo test biên

Một độ latitude xấp xỉ 111 km, nhưng độ longitude thay đổi theo vĩ độ. Nếu dùng một hằng số gần đúng để tạo điểm biên, điểm có thể thực tế nằm hơi trong hoặc ngoài bán kính.

Với test chính xác, có thể tạo điểm theo khoảng cách và bearing trên mô hình cầu, dùng cùng một quy ước đơn vị với test. Sau đó kiểm tra thêm hai điểm lệch vào trong và ngoài một epsilon đủ lớn so với sai số biểu diễn.

Một công thức tạo điểm đích trên mặt cầu với bán kính Trái Đất \(R\):

\[
\delta = \frac{d}{R}
\]

\[
\varphi_2 =
\arcsin(
\sin \varphi_1 \cos \delta +
\cos \varphi_1 \sin \delta \cos \theta
)
\]

\[
\lambda_2 =
\lambda_1 +
\operatorname{atan2}(
\sin \theta \sin \delta \cos \varphi_1,
\cos \delta - \sin \varphi_1 \sin \varphi_2
)
\]

Trong đó:

- \(\varphi_1, \lambda_1\) là latitude/longitude điểm đầu ở radian.
- \(d\) là khoảng cách mong muốn.
- \(R\) là bán kính mô hình Trái Đất được chọn.
- \(\theta\) là bearing.
- \(\varphi_2, \lambda_2\) là tọa độ điểm đích.

Công thức này tạo test data có kiểm soát. Kết quả Elasticsearch vẫn có thể chênh lệch nhỏ do mô hình khoảng cách, mã hóa tọa độ và quy tắc số học; vì vậy cần có test biên riêng và test epsilon.

## 8. Độ chính xác khoảng cách: arc và plane

Geo distance query hỗ trợ các kiểu tính khoảng cách. Với `geo_distance`, `arc` là cách tính mặc định trong Elasticsearch và phù hợp với phần lớn trường hợp cần khoảng cách địa lý trên bề mặt Trái Đất.

Có thể cấu hình:

~~~json
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "distance_type": "arc",
      "location": {
        "lat": 10.762622,
        "lon": 106.660172
      }
    }
  }
}
~~~

| Kiểu | Đặc điểm | Lưu ý |
|---|---|---|
| `arc` | Tính khoảng cách theo cung trên mô hình cầu | Phù hợp hơn cho khoảng cách địa lý nói chung |
| `plane` | Xấp xỉ trên mặt phẳng | Có thể nhanh hơn nhưng sai số tăng theo khoảng cách và vị trí |

Không chọn `plane` chỉ vì muốn truy vấn nhanh mà chưa đo sai số trong khu vực dữ liệu thật. Ở khoảng cách ngắn và khu vực nhỏ, sai số có thể chấp nhận được; ở khoảng cách dài, gần cực hoặc vùng trải rộng, kết quả có thể khác đáng kể.

### Đơn vị khoảng cách

Elasticsearch hỗ trợ các đơn vị như:

- `m`: mét.
- `km`: kilomet.
- `cm`: centimet.
- `mm`: millimet.
- `mi`: mile.
- `yd`: yard.
- `ft`: foot.
- `nmi`: nautical mile.

Ví dụ `5000m` và `5km` biểu diễn cùng một bán kính. Hãy dùng đơn vị rõ ràng trong query và thống nhất đơn vị trong API ứng dụng.

Không nên chuyển đổi thủ công khoảng cách thành độ latitude/longitude rồi dùng range query nếu mục tiêu nghiệp vụ là bán kính địa lý. Một độ longitude không tương đương cùng một khoảng cách ở mọi vĩ độ.

## 9. Kiểm thử geo_bounding_box tại các cạnh

Geo bounding box tìm các điểm nằm trong hình chữ nhật được xác định bởi góc trên trái và góc dưới phải.

~~~json
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.80,
          "lon": 106.60
        },
        "bottom_right": {
          "lat": 10.70,
          "lon": 106.72
        }
      }
    }
  }
}
~~~

Cần kiểm tra các trường hợp:

- Điểm nằm sâu bên trong.
- Điểm nằm ngoài cạnh bắc, nam, đông và tây.
- Điểm đúng trên mỗi cạnh.
- Điểm đúng tại bốn góc.
- Điểm thiếu location.
- Bounding box có kinh độ đi qua đường đổi ngày quốc tế.

Với bounding box thông thường, các cạnh được xác định bởi tọa độ min/max. Hãy tạo fixture ngay trên từng cạnh và xác nhận hành vi của phiên bản Elasticsearch đang chạy. Không nên suy ra kết quả chỉ từ cách vẽ hình chữ nhật trên bản đồ, vì bản đồ có thể hiển thị phép chiếu khác với tọa độ địa lý.

### Đường đổi ngày quốc tế

Một bounding box gần kinh độ +180° và -180° cần được kiểm tra riêng. Hai kinh độ này nằm gần nhau về địa lý dù chênh lệch số học gần 360 độ.

Nếu ứng dụng phục vụ dữ liệu toàn cầu, nên có test cho:

- Điểm ngay phía đông đường đổi ngày.
- Điểm ngay phía tây đường đổi ngày.
- Điểm nằm xa vùng bounding box.
- Hình chữ nhật cắt qua đường đổi ngày.

Không nên tự chuẩn hóa một bounding box qua đường đổi ngày bằng cách sắp xếp longitude tăng dần mà không xét semantics của geo query.

## 10. Kiểm thử geo_shape và quan hệ hình học

Với `geo_shape`, Elasticsearch hỗ trợ các quan hệ không gian như:

| Relation | Ý nghĩa tổng quát |
|---|---|
| `intersects` | Hai hình học có phần giao nhau |
| `within` | Hình học truy vấn nằm trong hình học được index |
| `contains` | Hình học được index chứa hình học truy vấn |
| `disjoint` | Hai hình học không giao nhau |

Ví dụ vùng phục vụ được lưu dưới dạng polygon:

~~~json
{
  "mappings": {
    "properties": {
      "serviceArea": {
        "type": "geo_shape"
      }
    }
  }
}
~~~

Document:

~~~json
{
  "serviceArea": {
    "type": "polygon",
    "coordinates": [
      [
        [106.65, 10.75],
        [106.68, 10.75],
        [106.68, 10.78],
        [106.65, 10.78],
        [106.65, 10.75]
      ]
    ]
  }
}
~~~

Khi kiểm thử polygon, cần có các điểm:

- Nằm sâu bên trong polygon.
- Nằm ngoài polygon.
- Nằm đúng trên cạnh.
- Nằm đúng tại đỉnh.
- Nằm trong lỗ (hole) nếu polygon có lỗ.
- Nằm trên hoặc gần ranh giới giữa hai vùng phục vụ.

Với các quan hệ `within`, `contains` và `intersects`, ý nghĩa được áp dụng theo thứ tự giữa hình học truy vấn và hình học đã index. Cần đọc đúng chiều quan hệ. Một lỗi đảo chiều có thể trả kết quả ngược với mong muốn nghiệp vụ.

Đối với điểm đúng trên biên polygon, đừng tự giả định mọi relation xử lý giống nhau. Xác định relation cần dùng và tạo test riêng cho điểm trên cạnh, đỉnh và điểm cách biên một epsilon. Nếu nghiệp vụ cần tính bao gồm biên, hãy chọn quan hệ và quy tắc hình học thể hiện rõ yêu cầu đó.

## 11. Kiểm thử dữ liệu ở cực và vùng tọa độ đặc biệt

Tọa độ địa lý không hoạt động như hệ trục Cartesian thông thường ở mọi nơi. Một số vùng cần test riêng:

- Gần latitude +90° hoặc -90°.
- Gần longitude +180° hoặc -180°.
- Hai điểm nằm hai phía của đường đổi ngày.
- Điểm rất gần nhau ở vĩ độ cao.
- Vùng polygon cắt qua cực hoặc đường đổi ngày.

Ở gần cực, thay đổi longitude nhỏ không tương ứng với cùng khoảng cách như ở xích đạo. Nếu ứng dụng tính khoảng cách thủ công bằng công thức phẳng, kết quả có thể sai.

Một bộ test địa lý toàn cầu nên bao gồm ít nhất một trường hợp gần xích đạo, một trường hợp ở vĩ độ cao và một trường hợp qua đường đổi ngày. Nếu sản phẩm chỉ phục vụ một khu vực, vẫn cần kiểm tra các tọa độ biên của khu vực đó và xác nhận hệ thống từ chối dữ liệu nằm ngoài phạm vi nghiệp vụ.

## 12. Sai số tọa độ và chiến lược tolerance

Tọa độ từ GPS, thiết bị di động hoặc dịch vụ bản đồ vốn đã có sai số. Ngoài sai số đo, kết quả còn chịu ảnh hưởng bởi:

- Độ chính xác đầu vào và số chữ số thập phân được lưu.
- Phép mã hóa tọa độ trong cấu trúc index.
- Mô hình tính khoảng cách.
- Cách chuyển đổi đơn vị.
- Việc làm tròn khi hiển thị.
- Chất lượng và độ chính xác của nguồn GPS.

Không nên kiểm tra khoảng cách bằng phép so sánh số thực chính xác tuyệt đối trong code:

~~~java
if (actualDistance == expectedDistance) {
    // Không nên dựa vào so sánh double tuyệt đối.
}
~~~

Thay vào đó, dùng sai số cho phép phù hợp nghiệp vụ:

~~~java
double toleranceMeters = 2.0;

assertThat(Math.abs(actualDistanceMeters - expectedDistanceMeters))
        .isLessThanOrEqualTo(toleranceMeters);
~~~

Giá trị tolerance không có một con số chung cho mọi ứng dụng. Một ứng dụng hiển thị cửa hàng gần nhất có thể chấp nhận sai số vài mét; ứng dụng xác định vùng an toàn hoặc tính phí theo ranh giới cần quy tắc chặt chẽ hơn và có thể phải dùng nguồn dữ liệu địa chính chuyên dụng.

Cần phân biệt:

- **Precision**: độ chi tiết mà dữ liệu và hệ thống có thể biểu diễn.
- **Accuracy**: mức gần đúng so với vị trí thực tế.
- **Tolerance**: sai số mà test hoặc nghiệp vụ chấp nhận.

Tăng số chữ số thập phân không tự động làm GPS chính xác hơn. Đừng lưu hoặc hiển thị độ chính xác giả tạo chỉ vì tọa độ có nhiều chữ số.

## 13. Làm tròn tọa độ ở đâu?

Không nên làm tròn tọa độ trước khi lưu hoặc trước khi truy vấn nếu nghiệp vụ cần khoảng cách chính xác. Ví dụ, làm tròn latitude/longitude đến hai chữ số thập phân có thể làm thay đổi vị trí hàng trăm mét đến hơn một kilomet tùy vĩ độ.

Nên phân chia:

- Lưu tọa độ gốc với độ chính xác mà nguồn cung cấp và nghiệp vụ cho phép.
- Dùng tọa độ chưa làm tròn trong geo query.
- Chỉ làm tròn số khoảng cách khi hiển thị.
- Nếu cần chuẩn hóa đầu vào, xác định rõ quy tắc và lưu lại độ chính xác nguồn (nếu có).

Ví dụ response API có thể hiển thị khoảng cách `1.23 km`, nhưng phép lọc bán kính nên sử dụng dữ liệu tọa độ đầy đủ hơn và khoảng cách chưa làm tròn.

Nếu dữ liệu đầu vào có độ chính xác thấp, có thể lưu thêm `accuracyMeters` từ thiết bị. Khi đó, ứng dụng có thể quyết định cách xử lý điểm nằm gần biên dựa trên độ không chắc chắn của phép đo thay vì chỉ dựa vào một tọa độ đơn lẻ.

## 14. Kiểm thử bằng Spring Data Elasticsearch và NativeQuery

Có thể xây dựng geo query bằng Elasticsearch Java API Client rồi đóng gói vào `NativeQuery`.

Ví dụ tìm cửa hàng trong bán kính 5 km:

~~~java
import co.elastic.clients.elasticsearch._types.GeoLocation;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

GeoLocation center = GeoLocation.of(g -> g
        .latlon(point -> point
                .lat(10.762622)
                .lon(106.660172)
        )
);

Query distanceQuery = Query.of(q -> q
        .geoDistance(g -> g
                .field("location")
                .distance("5km")
                .location(center)
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(distanceQuery)
        .build();

SearchHits<StoreDocument> hits =
        operations.search(nativeQuery, StoreDocument.class);
~~~

Trong ví dụ:

- `GeoLocation` biểu diễn tọa độ tâm.
- `lat(...)` nhận latitude.
- `lon(...)` nhận longitude.
- `geoDistance(...)` tạo geo distance query.
- `field("location")` chỉ định field `geo_point`.
- `distance("5km")` chỉ định bán kính.
- `NativeQuery` cho phép đưa query DSL của Java Client vào Spring Data.
- `SearchHits` giữ kết quả đã được chuyển đổi thành entity.

Các builder method có thể khác nhẹ theo phiên bản Elasticsearch Java API Client. Dùng dependency tương thích với Spring Data Elasticsearch của dự án và kiểm tra Javadoc tương ứng nếu chữ ký không khớp.

### Tìm document thiếu tọa độ

~~~java
Query missingLocation = Query.of(q -> q
        .bool(b -> b
                .mustNot(mn -> mn
                        .exists(e -> e.field("location"))
                )
        )
);

NativeQuery missingLocationQuery = NativeQuery.builder()
        .withQuery(missingLocation)
        .build();

SearchHits<StoreDocument> storesWithoutLocation =
        operations.search(
                missingLocationQuery,
                StoreDocument.class
        );
~~~

Query này tìm document không có giá trị được lập chỉ mục cho `location`. Nó không kiểm tra chuỗi JSON gốc có chứa thuộc tính hay không.

### Kết hợp exists và geo_distance

~~~java
Query hasLocation = Query.of(q -> q
        .exists(e -> e.field("location"))
);

Query nearby = Query.of(q -> q
        .geoDistance(g -> g
                .field("location")
                .distance("5km")
                .location(center)
        )
);

Query validNearby = Query.of(q -> q
        .bool(b -> b
                .filter(hasLocation)
                .filter(nearby)
        )
);
~~~

Sau đó gắn `validNearby` vào `NativeQuery` và thực thi như ví dụ trước.

## 15. Tạo bộ dữ liệu kiểm thử có chủ đích

Một integration test nên index document đại diện cho từng trường hợp thay vì chỉ dùng dữ liệu ngẫu nhiên.

Ví dụ fixture:

| ID | location | Mục đích |
|---|---|---|
| `CENTER` | Tọa độ tâm | Kiểm tra khoảng cách 0 |
| `INSIDE` | Cách tâm rõ ràng dưới bán kính | Kiểm tra điểm bên trong |
| `NEAR_EDGE_IN` | Ngay phía trong biên | Kiểm tra epsilon trong |
| `ON_EDGE` | Tạo theo khoảng cách đúng bằng bán kính | Kiểm tra semantics biên |
| `NEAR_EDGE_OUT` | Ngay phía ngoài biên | Kiểm tra epsilon ngoài |
| `OUTSIDE` | Cách tâm lớn hơn bán kính | Kiểm tra điểm bên ngoài |
| `NO_LOCATION` | Không có field location | Kiểm tra dữ liệu thiếu |
| `NULL_LOCATION` | location null | Kiểm tra null |
| `ZERO_POINT` | Latitude 0, longitude 0 | Tránh coi 0,0 là missing |
| `INVALID_POINT` | Tọa độ vượt miền hợp lệ | Kiểm tra validation/mapping |

Không nên index `INVALID_POINT` vào cùng test case đang dùng mapping mặc định nếu mục đích là kiểm tra truy vấn; thao tác ghi có thể thất bại trước khi query chạy. Tách test validation/indexing lỗi thành test riêng.

Sau khi ghi fixture, phải refresh index trước khi chạy search trong test. Có thể dùng API refresh của `IndexOperations` hoặc Elasticsearch Refresh API. Không dựa vào việc chờ một khoảng thời gian cố định bằng `Thread.sleep`.

## 16. Kiểm thử integration với Elasticsearch thật

Mock `ElasticsearchOperations` chỉ kiểm tra service có gọi đúng phương thức hay không. Nó không kiểm tra được cách Elasticsearch diễn giải geo query, mapping, thứ tự tọa độ, sai số hoặc biên hình học.

Nên có integration test với Elasticsearch thật. Testcontainers là một lựa chọn phổ biến để chạy container Elasticsearch trong quá trình test.

Ví dụ dependency Gradle (dùng version được quản lý thống nhất trong dự án):

~~~kotlin
dependencies {
    testImplementation("org.testcontainers:elasticsearch")
    testImplementation("org.testcontainers:junit-jupiter")
}
~~~

Ví dụ container:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.elasticsearch.ElasticsearchContainer;

@Testcontainers
class GeoSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    "docker.elastic.co/elasticsearch/elasticsearch:<compatible-version>"
            );

    @Test
    void containerStarts() {
        // Tạo Spring client trỏ tới endpoint của container,
        // tạo index và thực hiện các geo query cần kiểm thử.
    }
}
~~~

Đây là khung minh họa vòng đời container. Trong dự án Spring Boot, cần cấu hình connection URI và credentials từ container trước khi khởi tạo Elasticsearch client. Dùng image version tương thích với phiên bản Spring Data Elasticsearch và Java API Client mà dự án đang quản lý.

### Các bước trong integration test

1. Khởi động Elasticsearch container.
2. Tạo index với mapping `geo_point` hoặc `geo_shape` rõ ràng.
3. Index fixture cho điểm trong, ngoài, biên và dữ liệu thiếu.
4. Refresh index.
5. Chạy geo query qua service hoặc `ElasticsearchOperations`.
6. Kiểm tra tập ID được trả về.
7. Kiểm tra kết quả khi đổi bán kính và distance type.
8. Kiểm tra document có location null hoặc thiếu field.
9. Kiểm tra tọa độ đảo thứ tự.
10. Xóa index hoặc để container kết thúc theo vòng đời test.

Test cần chạy trên phiên bản Elasticsearch gần với production. Một embedded mock hoặc fake repository không thay thế được hành vi geo engine thực tế.

## 17. Ma trận kiểm thử nên có

Một ma trận giúp tránh bỏ sót trường hợp:

| Nhóm | Trường hợp | Điều cần xác nhận |
|---|---|---|
| Coordinate | Latitude = -90 hoặc 90 | Chấp nhận đúng miền |
| Coordinate | Longitude = -180 hoặc 180 | Chấp nhận đúng miền |
| Coordinate | Vượt miền latitude/longitude | Validation hoặc mapping từ chối/bỏ qua đúng cấu hình |
| Coordinate | NaN/Infinity | Bị từ chối ở ứng dụng |
| Coordinate | Đảo lat/lon | Test phát hiện vị trí sai |
| Missing | Field bị bỏ qua | Không khớp exists |
| Missing | Null | Không khớp exists theo mặc định |
| Missing | (0, 0) | Vẫn được xem là điểm hợp lệ |
| Distance | Tại tâm | Khớp |
| Distance | Bên trong bán kính | Khớp |
| Distance | Đúng bán kính | Kiểm tra biên |
| Distance | Ngoài bán kính | Không khớp |
| Bounding box | Bốn cạnh và bốn góc | Xác nhận semantics biên |
| Global | Qua đường đổi ngày | Không bỏ sót điểm gần nhau |
| Global | Gần cực | Không dùng phép tính phẳng sai |
| Shape | Bên trong, ngoài, trên cạnh, tại đỉnh | Xác nhận relation |
| Precision | Tọa độ nhiều chữ số và đã làm tròn | Đo ảnh hưởng sai số |
| Mapping | `ignore_malformed` | Hành vi bỏ qua hoặc từ chối đúng cấu hình |
| Multi-index | Một index thiếu geo mapping | Kiểm tra `ignore_unmapped` hoặc lỗi mong muốn |

## 18. Kiểm thử sort theo khoảng cách

Ứng dụng tìm cửa hàng gần nhất thường không chỉ lọc theo bán kính mà còn sắp xếp theo khoảng cách từ điểm người dùng.

Cần kiểm tra:

- Cửa hàng gần nhất đứng đầu khi sort tăng dần.
- Hai cửa hàng có khoảng cách gần bằng nhau.
- Document thiếu location được xử lý theo missing policy.
- Khoảng cách trả về dùng đúng đơn vị.
- Thứ tự không thay đổi bất ngờ khi query cùng dữ liệu.
- Khi nhiều document cùng khoảng cách, có tie-breaker ổn định nếu dùng phân trang.

Không nên chỉ kiểm tra rằng danh sách có đúng số lượng phần tử. Hãy xác nhận ID theo thứ tự và khoảng cách của các kết quả đầu.

Nếu ứng dụng dùng `search_after` cho kết quả sort theo địa lý, cần giữ nguyên các sort values trả về và sort definition giữa các trang. Không tự tính lại sort values từ tọa độ trong entity.

## 19. Xử lý nhiều index và ignore_unmapped

Một alias có thể trỏ đến nhiều index. Trong quá trình migration, một index cũ có thể chưa có field `location` hoặc mapping chưa phải `geo_point`.

Một geo query chạy trên tập index không đồng nhất có thể gặp lỗi nếu field không được mapping trên một index. Một số query hỗ trợ `ignore_unmapped` để bỏ qua index không có field tương ứng.

Ví dụ về mặt DSL:

~~~json
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "ignore_unmapped": true,
      "location": {
        "lat": 10.762622,
        "lon": 106.660172
      }
    }
  }
}
~~~

Dùng `ignore_unmapped` chỉ khi bỏ qua index chưa có mapping là hành vi nghiệp vụ được chấp nhận. Nếu index đó lẽ ra phải chứa location, bỏ qua có thể che giấu lỗi migration.

Nên có test cho cả hai chính sách:

- Strict: thiếu mapping làm request thất bại để phát hiện cấu hình sai.
- Lenient: index không mapping được bỏ qua có chủ đích.

## 20. Những lỗi thường gặp

### Đảo latitude và longitude

Array và GeoJSON dùng longitude trước latitude; object dùng tên `lat` và `lon`. Hai số đều có thể hợp lệ sau khi đảo, nên test bằng vị trí đã biết.

### Coi (0, 0) là dữ liệu thiếu

(0, 0) là tọa độ hợp lệ. Dùng null hoặc trạng thái riêng để biểu diễn chưa có vị trí.

### Chỉ test điểm ở rất xa hoặc rất gần

Test không chạm biên sẽ không phát hiện lỗi làm tròn, đơn vị hoặc semantics boundary. Thêm điểm ngay trong, đúng trên và ngay ngoài ngưỡng.

### Làm tròn trước khi query

Làm tròn latitude/longitude có thể đẩy điểm qua ranh giới bán kính hoặc vùng phục vụ. Giữ độ chính xác đầu vào trong query và chỉ làm tròn khi hiển thị.

### Dùng plane cho vùng rộng

Phép tính phẳng có thể tạo sai số đáng kể ở khoảng cách lớn, vĩ độ cao hoặc vùng địa lý rộng. Dùng arc trừ khi đã đo và chấp nhận sai số của plane.

### Dùng exists để kiểm tra chất lượng vị trí

Exists chỉ kiểm tra có giá trị được lập chỉ mục. Nó không xác minh điểm nằm trong khu vực kinh doanh hoặc tọa độ có đúng địa chỉ.

### Bật ignore_malformed và quên theo dõi

Document có thể được lưu trong khi location không được lập chỉ mục. Cần log, metric hoặc trạng thái dữ liệu để phát hiện.

### Chỉ mock Elasticsearch trong unit test

Mock không thể xác nhận hành vi geo query và mapping. Cần integration test với phiên bản Elasticsearch tương thích.

### Kiểm thử bằng khoảng cách đã làm tròn

Nếu tính khoảng cách rồi làm tròn trước khi so sánh, test có thể cho kết quả sai ở ngưỡng. So sánh bằng tolerance phù hợp và kiểm tra response thật.

## 21. Quy trình triển khai và kiểm thử

Khi phát triển tính năng địa lý:

1. Chọn kiểu dữ liệu `geo_point` hay `geo_shape` dựa trên mô hình nghiệp vụ.
2. Khai báo mapping tường minh trong Spring Data hoặc quy trình provisioning.
3. Chuẩn hóa thứ tự tọa độ và định dạng đầu vào.
4. Validate miền latitude/longitude, giá trị hữu hạn và dữ liệu thiếu.
5. Quy định rõ cách xử lý null, mảng rỗng và tọa độ không hợp lệ.
6. Chọn distance type và đơn vị khoảng cách phù hợp.
7. Xác định semantics cho điểm đúng trên biên bán kính, bounding box và polygon.
8. Tạo fixture có điểm trong, ngoài, đúng biên và epsilon hai phía.
9. Bổ sung test cho (0, 0), cực và đường đổi ngày nếu phạm vi dữ liệu cần hỗ trợ.
10. Chạy integration test trên Elasticsearch thật.
11. Dùng tolerance phù hợp cho phép tính số thực và nguồn dữ liệu.
12. Kiểm tra alias nhiều index và mapping không đồng nhất.
13. Theo dõi document có vị trí bị bỏ qua hoặc sai định dạng.
14. Không dùng tọa độ giả để che giấu dữ liệu thiếu.

## Tài liệu tham khảo

- [Elasticsearch — Geo-point field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-point.html)
- [Elasticsearch — Geo-shape field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-shape.html)
- [Elasticsearch — Geo-distance query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-geo-distance-query.html)
- [Elasticsearch — Geo-bounding box query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-geo-bounding-box-query.html)
- [Elasticsearch — Geo-shape query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-geo-shape-query.html)
- [Spring Data Elasticsearch — Reference documentation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html)
- [Testcontainers — Elasticsearch module](https://java.testcontainers.org/modules/elasticsearch/)

## Kết luận

Kiểm thử địa lý cần bao phủ cả tọa độ hợp lệ, dữ liệu thiếu, dữ liệu sai định dạng, điểm nằm bên trong/bên ngoài/đúng biên và sai số khoảng cách. Với Spring Data Elasticsearch, hãy khai báo mapping địa lý tường minh, tạo query bằng `NativeQuery` khi cần DSL địa lý, và xác nhận hành vi bằng integration test trên Elasticsearch thật. Phân biệt đúng latitude/longitude, không coi (0, 0) là missing, giữ độ chính xác tọa độ khi truy vấn và dùng tolerance dựa trên yêu cầu nghiệp vụ thay vì so sánh số thực tuyệt đối.
