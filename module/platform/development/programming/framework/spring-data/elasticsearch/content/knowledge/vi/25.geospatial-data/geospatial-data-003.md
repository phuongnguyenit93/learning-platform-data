# Kinh độ, vĩ độ, đơn vị khoảng cách và lỗi đảo tọa độ

Khi lưu và tìm kiếm vị trí trong Elasticsearch, hai giá trị cần được hiểu đúng là **latitude (vĩ độ)** và **longitude (kinh độ)**. Elasticsearch dùng tọa độ địa lý theo WGS 84 và biểu diễn vị trí bằng độ thập phân. Một lỗi phổ biến là đảo thứ tự latitude/longitude khi chuyển dữ liệu giữa Java, JSON, GeoJSON, cơ sở dữ liệu hoặc API bản đồ. Lỗi này đôi khi bị từ chối ngay vì tọa độ vượt miền hợp lệ, nhưng cũng có thể tạo ra một vị trí khác hoàn toàn mà không phát sinh exception.

Trong Spring Data Elasticsearch, kiểu GeoPoint nhận latitude trước longitude. Trong khi đó, array, GeoJSON và WKT của Elasticsearch thường dùng longitude trước latitude. Đơn vị khoảng cách cũng cần được khai báo nhất quán: geo query thường nhận khoảng cách dạng chuỗi như 5km, còn geo distance sort có tham số unit riêng. Bài học này giải thích hệ tọa độ, thứ tự tọa độ theo từng định dạng, cách chuyển đổi và kiểm tra dữ liệu, cách chọn đơn vị khoảng cách và cách tránh lỗi đảo tọa độ.

## 1. Latitude và longitude là gì?

Tọa độ địa lý xác định một điểm trên bề mặt Trái Đất bằng hai thành phần:

- **Latitude (vĩ độ):** vị trí theo hướng Bắc hoặc Nam so với đường xích đạo.
- **Longitude (kinh độ):** vị trí theo hướng Đông hoặc Tây so với kinh tuyến gốc Greenwich.

Miền giá trị hợp lệ:

| Thành phần | Miền giá trị | Ý nghĩa dấu |
|---|---:|---|
| Latitude | -90 đến +90 độ | Bắc là dương, Nam là âm |
| Longitude | -180 đến +180 độ | Đông là dương, Tây là âm |

Một số ví dụ:

| Địa điểm | Latitude | Longitude |
|---|---:|---:|
| Ho Chi Minh City, ví dụ gần trung tâm | 10.7769 | 106.7009 |
| Hanoi, ví dụ gần trung tâm | 21.0278 | 105.8342 |
| New York, ví dụ gần Manhattan | 40.7128 | -74.0060 |
| Sydney, ví dụ gần trung tâm | -33.8688 | 151.2093 |

Các giá trị trên là ví dụ tọa độ gần đúng, không đại diện cho một địa chỉ cụ thể. Với Việt Nam, latitude thường dương vì nằm ở Bắc bán cầu và longitude thường dương vì nằm ở Đông bán cầu.

### 1.1. Độ thập phân

Elasticsearch nhận tọa độ theo đơn vị độ. Ví dụ:

~~~json
{
  "lat": 10.7769,
  "lon": 106.7009
}
~~~

Đây là dạng decimal degrees (độ thập phân). Không truyền giá trị theo radians hoặc số mét của một hệ tọa độ chiếu vào field geo_point.

Nếu nguồn dữ liệu cung cấp độ-phút-giây (DMS), cần đổi sang độ thập phân:

~~~text
decimal degrees = degrees + minutes / 60 + seconds / 3600
~~~

Sau đó áp dụng dấu âm nếu hướng là Nam (S) hoặc Tây (W). Ví dụ 10°46'36.8"N tương đương khoảng 10.7769 độ Bắc. Không lấy trị tuyệt đối của tọa độ Nam/Tây vì làm vậy sẽ chuyển vị trí sang bán cầu khác.

### 1.2. Hệ tọa độ tham chiếu

Elasticsearch geo_point sử dụng hệ tọa độ địa lý WGS 84 (EPSG:4326). GPS, GeoJSON và nhiều API bản đồ phổ biến cũng trao đổi tọa độ theo WGS 84.

Một số nguồn dữ liệu GIS có thể dùng hệ tọa độ chiếu như UTM hoặc hệ quy chiếu địa phương như VN-2000. Những giá trị đó thường được biểu diễn bằng tọa độ phẳng theo mét, không phải latitude/longitude theo độ. Phải chuyển đổi sang WGS 84 trước khi ghi vào geo_point.

Không thể chỉ đổi tên hai cột X/Y thành latitude/longitude để chuyển CRS. Cần dùng phép biến đổi tọa độ phù hợp với vùng, múi chiếu, datum và tham số của nguồn dữ liệu. Nếu chuyển đổi sai CRS, kết quả có thể lệch hàng trăm mét hoặc nhiều kilomet dù hai con số vẫn nằm trong miền số hợp lệ.

## 2. Thứ tự tọa độ phụ thuộc định dạng

Đây là quy tắc quan trọng nhất khi làm việc với geo_point:

| Định dạng | Ví dụ | Thứ tự |
|---|---|---|
| JSON object | {"lat": 10.7769, "lon": 106.7009} | Ghi rõ tên lat và lon |
| Chuỗi Elasticsearch | "10.7769,106.7009" | latitude, longitude |
| Array Elasticsearch | [106.7009, 10.7769] | longitude, latitude |
| GeoJSON Point | {"type":"Point","coordinates":[106.7009,10.7769]} | longitude, latitude |
| WKT Point | "POINT (106.7009 10.7769)" | longitude, latitude |
| Spring Data GeoPoint | new GeoPoint(10.7769, 106.7009) | latitude, longitude |
| Spring Data GeoJsonPoint | GeoJsonPoint.of(106.7009, 10.7769) | longitude, latitude |
| Geohash | "w3gvk" | Mã hóa vị trí, không truyền cặp lat/lon |

Không có một quy tắc thứ tự duy nhất áp dụng cho mọi API. Hãy đọc định dạng cụ thể thay vì suy luận từ tên biến hoặc vị trí phần tử.

### 2.1. Dạng object: rõ ràng và dễ kiểm tra

Đây là dạng nên ưu tiên khi tự tạo JSON:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Tên thuộc tính giúp tránh nhầm lẫn. Khi đọc code, có thể nhận ra ngay con số nào là vĩ độ và con số nào là kinh độ.

### 2.2. Dạng string

Elasticsearch chấp nhận chuỗi latitude,longitude:

~~~json
{
  "location": "10.7769,106.7009"
}
~~~

Chuỗi này dùng latitude trước longitude, khác với array và GeoJSON. Vì vậy, chuyển chuỗi này thành array bằng cách tách dấu phẩy rồi giữ nguyên thứ tự là lỗi thường gặp.

### 2.3. Dạng array

Array dùng thứ tự longitude,latitude:

~~~json
{
  "location": [106.7009, 10.7769]
}
~~~

Phần tử thứ nhất là longitude (x), phần tử thứ hai là latitude (y). Đây là quy ước tọa độ GeoJSON và cũng là thứ tự thường dùng trong nhiều thư viện bản đồ.

### 2.4. GeoJSON

GeoJSON Point có cấu trúc:

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

GeoJSON định nghĩa tọa độ theo thứ tự x, y, tương ứng longitude, latitude đối với tọa độ địa lý. Không đổi thành [latitude, longitude] chỉ vì phần lớn API Java dùng constructor nhận vĩ độ trước.

### 2.5. WKT

Well-Known Text cũng dùng thứ tự x, y:

~~~text
POINT (106.7009 10.7769)
~~~

Trong WKT Point địa lý, giá trị đầu là longitude, giá trị thứ hai là latitude. Các geometry như LINESTRING và POLYGON cũng dùng cùng thứ tự tọa độ cho từng cặp.

## 3. Biểu diễn tọa độ trong Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp GeoPoint trong package org.springframework.data.elasticsearch.core.geo. Constructor nhận latitude trước, longitude sau:

~~~java
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

GeoPoint location = new GeoPoint(10.7769, 106.7009);
~~~

Đọc constructor theo thứ tự:

~~~text
new GeoPoint(latitude, longitude)
              10.7769, 106.7009
~~~

Có thể dùng GeoPoint làm thuộc tính của entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "places")
public class Place {

    @Id
    private String id;

    private String name;

    @GeoPointField
    private GeoPoint location;

    public Place() {
    }

    public Place(String id, String name, double latitude, double longitude) {
        this.id = id;
        this.name = name;
        this.location = new GeoPoint(latitude, longitude);
    }

    public GeoPoint getLocation() {
        return location;
    }
}
~~~

Annotation @GeoPointField cho biết thuộc tính được ánh xạ thành Elasticsearch geo_point. Có thể kiểm tra mapping sau khi tạo index:

~~~http
GET places/_mapping
~~~

Kết quả cần thể hiện field location có type geo_point. Nếu index đã tồn tại với mapping khác, thay annotation trong Java không tự sửa mapping của index; cần tạo index mới và chuyển dữ liệu nếu kiểu field phải thay đổi.

### 3.1. GeoJsonPoint dùng thứ tự khác

Khi làm việc với GeoJSON, Spring Data có GeoJsonPoint. Factory method nhận x trước y sau, tương ứng longitude rồi latitude:

~~~java
import org.springframework.data.elasticsearch.core.geo.GeoJsonPoint;

GeoJsonPoint point = GeoJsonPoint.of(106.7009, 10.7769);
~~~

So sánh hai cách:

~~~java
GeoPoint geoPoint = new GeoPoint(10.7769, 106.7009);
GeoJsonPoint geoJsonPoint = GeoJsonPoint.of(106.7009, 10.7769);
~~~

Hai object biểu diễn cùng một vị trí. Điểm khác nhau là thứ tự tham số của API. Đừng đổi thứ tự chỉ để làm hai dòng code trông giống nhau.

## 4. Ghi tọa độ vào Elasticsearch

Với REST API, dạng object giúp thể hiện rõ ý nghĩa:

~~~http
PUT places/_doc/place-1
{
  "name": "Central Store",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Với Spring Data Elasticsearch:

~~~java
Place place = new Place(
        "place-1",
        "Central Store",
        10.7769,   // latitude
        106.7009   // longitude
);

placeRepository.save(place);
~~~

Spring Data dùng mapping metadata và converter để chuyển GeoPoint thành dữ liệu Elasticsearch. Ứng dụng nên giữ tên biến rõ nghĩa, ví dụ latitude và longitude, thay vì dùng lat1, x, y hoặc coordinate1 khi chưa xác định quy ước.

## 5. Đơn vị khoảng cách

Latitude và longitude được lưu theo độ. Khoảng cách địa lý được tính và trả về theo đơn vị chiều dài như mét hoặc kilomet. Không nhầm đơn vị tọa độ với đơn vị khoảng cách:

- Latitude/longitude: độ góc.
- Distance: mét, kilomet, mile hoặc đơn vị chiều dài khác.

Các đơn vị thường dùng trong Elasticsearch:

| Đơn vị | Ký hiệu |
|---|---|
| Millimeter | mm |
| Centimeter | cm |
| Meter | m |
| Kilometer | km |
| Inch | in |
| Feet | ft |
| Yard | yd |
| Mile | mi |
| Nautical mile | nmi |

Một số quy đổi:

| Quy đổi | Giá trị |
|---|---:|
| 1 kilometer | 1.000 meters |
| 1 mile | 1.609,344 meters |
| 1 nautical mile | 1.852 meters |
| 1 meter | 100 centimeters |
| 1 kilometer | khoảng 0,621371 mile |

Nếu không khai báo đơn vị trong geo distance sort, Elasticsearch mặc định dùng mét. Trong ứng dụng, nên thống nhất đơn vị từ query đến DTO và giao diện hiển thị.

### 5.1. Khoảng cách trong geo_distance query

Geo distance query nhận khoảng cách trong thuộc tính distance. Có thể truyền số cùng đơn vị trong một chuỗi:

~~~http
GET places/_search
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

Query trên chọn document có location nằm trong bán kính 5 km tính từ điểm tham chiếu. Có thể dùng 5000m thay cho 5km; hai cách biểu diễn có cùng độ dài.

Một vài ví dụ khác:

~~~json
{
  "distance": "500m"
}
~~~

~~~json
{
  "distance": "3mi"
}
~~~

~~~json
{
  "distance": "2nmi"
}
~~~

Giá trị distance cần có đơn vị được hỗ trợ hoặc dùng đơn vị mặc định theo API. Trong code ứng dụng, nên luôn ghi rõ đơn vị để người đọc không phải suy đoán.

### 5.2. Đơn vị trong geo distance sort

Geo distance sort dùng thuộc tính unit riêng:

~~~http
GET places/_search
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
    }
  ]
}
~~~

Ở đây unit: km quy định đơn vị của sort value. Document gần nhất đứng trước vì order là asc. Nếu bỏ unit, sort value mặc định tính bằng mét.

Trong Spring Data Elasticsearch, GeoDistanceOrder cho phép chỉ định đơn vị:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;

GeoDistanceOrder distanceOrder = new GeoDistanceOrder(
        "location",
        new GeoPoint(10.7769, 106.7009))
        .with(Sort.Direction.ASC)
        .withUnit("km");
~~~

Constructor của GeoDistanceOrder nhận property và GeoPoint. GeoPoint vẫn dùng thứ tự latitude, longitude; withUnit chỉ chọn đơn vị khoảng cách.

## 6. Phân biệt khoảng cách địa lý và khoảng cách di chuyển

Elasticsearch geo_distance tính khoảng cách địa lý trực tiếp giữa các tọa độ, thường được hiểu là khoảng cách đường chim bay trên bề mặt Trái Đất. Đây không phải khoảng cách theo đường bộ, thời gian lái xe hoặc quãng đường đi bộ.

Ví dụ hai địa điểm có thể cách nhau 2 km theo đường thẳng nhưng phải đi vòng qua sông, đường một chiều hoặc khu vực không có cầu nên quãng đường thực tế dài hơn nhiều.

Chọn công cụ theo yêu cầu:

| Nhu cầu | Cách xử lý |
|---|---|
| Tìm địa điểm trong bán kính 5 km | Elasticsearch geo_distance |
| Xếp cửa hàng gần người dùng nhất theo đường thẳng | Elasticsearch _geo_distance sort |
| Tính khoảng cách lái xe hoặc đi bộ | Routing/directions service |
| Ước lượng thời gian di chuyển | Routing service có thông tin đường và phương tiện |
| Tìm vùng địa lý giao nhau | geo_shape query |

Không dùng kết quả geo_distance để hiển thị như quãng đường lái xe nếu ứng dụng chưa tính route.

## 7. Lỗi đảo latitude và longitude

Giả sử vị trí đúng là:

~~~text
latitude  = 10.7769
longitude = 106.7009
~~~

Trong constructor Spring Data, cách viết đúng:

~~~java
new GeoPoint(10.7769, 106.7009);
~~~

Nếu đảo:

~~~java
new GeoPoint(106.7009, 10.7769);
~~~

thì giá trị latitude trở thành 106.7009, vượt miền -90 đến 90. Dữ liệu thường bị từ chối hoặc gây lỗi khi ghi/convert.

### 7.1. Trường hợp đảo tọa độ vẫn hợp lệ về mặt số học

Không phải mọi lỗi đảo tọa độ đều bị phát hiện bằng kiểm tra miền giá trị.

Ví dụ vị trí gần New York:

~~~text
Đúng:  latitude = 40.7128, longitude = -74.0060
Sai:   latitude = -74.0060, longitude = 40.7128
~~~

Cả hai giá trị latitude và longitude trong trường hợp sai vẫn nằm trong miền cho phép. Elasticsearch có thể chấp nhận tọa độ sai và lưu nó như một vị trí hợp lệ ở nơi khác trên Trái Đất.

Vì vậy, chỉ kiểm tra latitude trong [-90, 90] và longitude trong [-180, 180] là chưa đủ để phát hiện mọi trường hợp đảo tọa độ. Cần thêm kiểm tra theo vùng địa lý dự kiến, nguồn dữ liệu và các vị trí mẫu đã biết.

### 7.2. Vì sao lỗi này khó tìm?

Lỗi đảo tọa độ có thể không gây exception vì:

- Cả hai số vẫn nằm trong miền hợp lệ.
- JSON vẫn hợp lệ về cú pháp.
- Mapping vẫn là geo_point.
- Elasticsearch vẫn tính được khoảng cách tới vị trí sai.
- Query vẫn trả kết quả, nhưng thứ tự hoặc phạm vi địa lý không đúng.

Kết quả thường biểu hiện như cửa hàng gần nhất ở một thành phố/quốc gia khác, tìm kiếm quanh vị trí người dùng trả về rỗng, hoặc khoảng cách lớn bất thường.

### 7.3. Những nơi dễ đảo thứ tự

- Đọc cột database tên longitude trước latitude rồi truyền vào GeoPoint theo cùng thứ tự.
- Chuyển GeoJSON array [lon, lat] thành constructor GeoPoint mà không đảo lại.
- Dùng GeoJsonPoint.of theo thứ tự lat, lon thay vì lon, lat.
- Tách chuỗi "lat,lon" rồi xử lý như array [lon,lat].
- Đọc giá trị x/y từ thư viện GIS nhưng giả định x là latitude.
- Dùng một DTO chỉ có hai trường number mà không ghi rõ tên.
- Chép tọa độ từ một API có thứ tự khác mà không đọc tài liệu.

## 8. Xác thực tọa độ ở biên ứng dụng

Nên xác thực tọa độ trước khi tạo entity hoặc gọi Elasticsearch. Ví dụ một value object Java:

~~~java
public record GeographicCoordinates(
        double latitude,
        double longitude) {

    public GeographicCoordinates {
        if (!Double.isFinite(latitude) || !Double.isFinite(longitude)) {
            throw new IllegalArgumentException("Coordinates must be finite numbers");
        }

        if (latitude < -90.0 || latitude > 90.0) {
            throw new IllegalArgumentException("Latitude must be between -90 and 90");
        }

        if (longitude < -180.0 || longitude > 180.0) {
            throw new IllegalArgumentException("Longitude must be between -180 and 180");
        }
    }

    public org.springframework.data.elasticsearch.core.geo.GeoPoint toGeoPoint() {
        return new org.springframework.data.elasticsearch.core.geo.GeoPoint(
                latitude,
                longitude);
    }
}
~~~

Value object này giúp tên tham số và constructor luôn theo thứ tự latitude, longitude. Nó cũng từ chối NaN và Infinity, vốn không phải tọa độ địa lý hợp lệ.

### 8.1. Kiểm tra vùng địa lý nghiệp vụ

Với một ứng dụng chỉ phục vụ một vùng nhất định, có thể kiểm tra tọa độ nằm trong bounding box của vùng đó. Ví dụ minh họa một vùng bao quanh miền Nam Việt Nam:

~~~java
public static boolean isWithinExpectedRegion(GeographicCoordinates point) {
    return point.latitude() >= 8.0
            && point.latitude() <= 13.0
            && point.longitude() >= 102.0
            && point.longitude() <= 110.0;
}
~~~

Đây chỉ là bounding box kiểm tra sơ bộ, không phải ranh giới hành chính chính xác. Trong hệ thống thực tế, dùng polygon hoặc geofence đúng với vùng nghiệp vụ nếu cần xác thực chính xác.

Không nên tự động đảo tọa độ khi thấy một giá trị vượt miền. Hãy trả lỗi validation và yêu cầu sửa nguồn dữ liệu. Tự động hoán đổi có thể làm dữ liệu lỗi trở nên khó truy vết, và cũng không phát hiện được trường hợp cả hai giá trị đều hợp lệ.

### 8.2. Không thể suy ra thứ tự chỉ từ hai số

Nếu nhận hai số không có tên như:

~~~json
{
  "x": 40.7128,
  "y": -74.0060
}
~~~

thì không thể biết chắc x là latitude hay longitude nếu không có hợp đồng API. Hãy thiết kế DTO có tên rõ ràng:

~~~json
{
  "latitude": 40.7128,
  "longitude": -74.0060
}
~~~

Với GeoJSON, tuân thủ quy tắc coordinates [longitude, latitude]. Không dùng một cấu trúc DTO chung cho cả hai quy ước mà không có chuyển đổi rõ ràng.

## 9. Chuyển đổi an toàn giữa định dạng

Khi chuyển từ object Java sang JSON object, giữ nguyên tên field:

~~~java
GeoPoint point = new GeoPoint(latitude, longitude);
~~~

Khi chuyển sang array/GeoJSON, đổi thứ tự có chủ đích:

~~~java
double[] coordinates = {
        point.getLon(),
        point.getLat()
};
~~~

Đoạn code minh họa ý nghĩa của phép chuyển đổi: array GeoJSON là longitude trước, latitude sau. Kiểm tra tên accessor trong đúng phiên bản Spring Data đang dùng nếu triển khai trực tiếp.

Một hàm chuyển đổi có tên rõ ràng giảm nguy cơ nhầm:

~~~java
public static double[] toGeoJsonCoordinates(GeographicCoordinates point) {
    return new double[] {
            point.longitude(),
            point.latitude()
    };
}
~~~

Và chuyển ngược từ GeoJSON array:

~~~java
public static GeographicCoordinates fromGeoJsonCoordinates(double[] coordinates) {
    if (coordinates == null || coordinates.length < 2) {
        throw new IllegalArgumentException("GeoJSON Point needs [longitude, latitude]");
    }

    return new GeographicCoordinates(
            coordinates[1],
            coordinates[0]);
}
~~~

Hai hàm này đặt quy ước thứ tự ngay tại tên và implementation, thay vì để từng caller tự nhớ.

## 10. Sử dụng tọa độ trong geo_distance query

Khi tìm các địa điểm trong bán kính, dùng tọa độ tham chiếu theo định dạng object để tránh nhầm:

~~~http
GET places/_search
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

Spring Data Elasticsearch có thể xây query tương ứng bằng Criteria:

~~~java
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

GeoPoint origin = new GeoPoint(10.7769, 106.7009);

Criteria criteria = Criteria.where("location")
        .within(origin, "5km");

CriteriaQuery query = new CriteriaQuery(criteria);
~~~

Trong ví dụ, GeoPoint nhận latitude trước longitude; chuỗi "5km" chỉ định bán kính. Criteria biểu diễn điều kiện tìm kiếm, còn Elasticsearch thực hiện phép tính khoảng cách.

## 11. Sử dụng tọa độ trong geo distance sort

Nếu cần sắp xếp kết quả gần nhất trước, khai báo sort riêng:

~~~http
GET places/_search
{
  "query": {
    "match_all": {}
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

Hai vị trí dùng cùng tọa độ tham chiếu và cùng quy ước thứ tự:

- Geo distance query: distance: "5km" để giới hạn bán kính.
- Geo distance sort: unit: "km" để trả sort value theo kilomet.

Query và sort có thể được kết hợp nếu muốn vừa giới hạn bán kính vừa sắp xếp gần nhất trước. Chỉ sort không tự loại các địa điểm xa.

## 12. Arc, plane và ý nghĩa của khoảng cách

Elasticsearch hỗ trợ hai distance type phổ biến cho geo distance sort:

| Distance type | Ý nghĩa |
|---|---|
| arc | Tính khoảng cách theo cung trên bề mặt Trái Đất; mặc định và chính xác hơn |
| plane | Dùng phép tính phẳng gần đúng; có thể nhanh hơn trong phạm vi nhỏ nhưng sai số tăng khi khoảng cách dài hoặc gần cực |

Ví dụ:

~~~json
{
  "_geo_distance": {
    "location": [106.7009, 10.7769],
    "order": "asc",
    "unit": "km",
    "distance_type": "arc"
  }
}
~~~

Với tìm kiếm cửa hàng, bệnh viện hoặc dịch vụ quanh người dùng, thường giữ arc. Chỉ dùng plane sau khi đo hiệu năng và xác nhận độ sai lệch chấp nhận được.

Khoảng cách geo được tính là khoảng cách địa lý, không tính đường đi theo mạng lưới đường phố. Nếu giao diện cần khoảng cách lái xe hoặc thời gian di chuyển, phải dùng routing service.

## 13. Các lỗi liên quan đến đơn vị

### 13.1. Dùng mét nhưng hiển thị kilomet

Nếu sort không đặt unit, sort value mặc định là mét. Giao diện hiển thị trực tiếp con số đó với nhãn km sẽ khiến khoảng cách lớn gấp 1.000 lần.

Ví dụ giá trị 2.400 mét phải hiển thị là 2,4 km nếu muốn dùng kilomet. Tốt hơn là khai báo unit: km trong sort và giữ hợp đồng DTO nhất quán.

### 13.2. Nhầm đơn vị tọa độ với đơn vị khoảng cách

Không có chuyện latitude/longitude được lưu bằng kilomet hoặc mét. Chúng là độ góc. Chỉ kết quả khoảng cách mới có đơn vị chiều dài.

### 13.3. Gửi radians thay cho degrees

Elasticsearch geo_point mong đợi tọa độ theo độ. Nếu nguồn dữ liệu dùng radians, cần đổi sang độ trước khi ghi:

~~~text
degrees = radians * 180 / pi
~~~

Không tự đổi tọa độ từ độ sang radians chỉ vì một thư viện tính toán khác sử dụng radians.

### 13.4. Dùng dấu phẩy thập phân theo locale

JSON number dùng dấu chấm thập phân:

~~~json
{
  "lat": 10.7769,
  "lon": 106.7009
}
~~~

Không ghi 10,7769 như số thập phân trong JSON. Dấu phẩy là dấu phân tách phần tử/thuộc tính, không phải dấu thập phân. Khi parse dữ liệu theo locale, chuyển sang numeric value trước khi serialize JSON.

### 13.5. Không thống nhất đơn vị giữa query và response

Nếu geo_distance query dùng 5km nhưng geo distance sort trả mét, kết quả lọc vẫn đúng nhưng DTO có thể hiển thị sai nếu giả định cả hai cùng đơn vị. Hãy khai báo và lưu rõ unit cho sort value.

## 14. Kiểm tra dữ liệu tọa độ sai

Khi nghi ngờ tọa độ bị đảo hoặc lệch, có thể kiểm tra theo các bước:

1. Đọc tên field và hợp đồng API của nguồn gửi tọa độ.
2. Xác nhận CRS là WGS 84 hay hệ chiếu khác.
3. Kiểm tra latitude có nằm trong [-90, 90] và longitude trong [-180, 180].
4. So sánh một số tọa độ với vị trí đã biết hoặc bản đồ đáng tin cậy.
5. Kiểm tra thứ tự của JSON object, array, GeoJSON hoặc WKT.
6. Kiểm tra constructor Java và mapper có đổi thứ tự đúng không.
7. Kiểm tra đơn vị distance query và sort value.
8. Chạy truy vấn quanh một điểm tham chiếu đã biết và xác nhận kết quả có ở đúng khu vực.
9. Kiểm tra mapping Elasticsearch và document _source.
10. Sửa ở nguồn hoặc bước chuyển đổi, sau đó reindex dữ liệu sai nếu cần.

Có thể xem một document:

~~~http
GET places/_doc/place-1
~~~

Kiểm tra mapping:

~~~http
GET places/_mapping
~~~

Nếu _source chứa đúng số nhưng vị trí hiển thị sai, kiểm tra thứ tự tọa độ trong consumer hoặc frontend. Nếu _source đã sai, kiểm tra ingest/DTO/converter trước khi dữ liệu được ghi.

## 15. Thiết kế DTO và API rõ nghĩa

Tránh API nhận hai số không tên:

~~~java
public record LocationRequest(double first, double second) {
}
~~~

Ưu tiên:

~~~java
public record LocationRequest(
        double latitude,
        double longitude) {
}
~~~

Nếu API cần GeoJSON, giữ cấu trúc GeoJSON đúng chuẩn:

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

Khi chuyển từ LocationRequest sang GeoJSON, viết mapper rõ ràng:

~~~java
public static double[] toGeoJson(LocationRequest request) {
    return new double[] {
            request.longitude(),
            request.latitude()
    };
}
~~~

Tên trường có ý nghĩa giúp người gọi API và người bảo trì code nhận biết thứ tự mà không phải đoán. Với hệ thống có nhiều nguồn dữ liệu, ghi rõ CRS, đơn vị và thứ tự tọa độ trong hợp đồng API.

## 16. Kiểm thử tọa độ và khoảng cách

Nên kiểm thử cả validation ở Java và kết quả thực tế trên Elasticsearch.

### 16.1. Unit test cho miền tọa độ

~~~java
@Test
void rejectsLatitudeOutsideValidRange() {
    assertThatThrownBy(() ->
            new GeographicCoordinates(106.7009, 10.7769))
            .isInstanceOf(IllegalArgumentException.class);
}

@Test
void acceptsValidLatitudeAndLongitude() {
    GeographicCoordinates point =
            new GeographicCoordinates(10.7769, 106.7009);

    assertThat(point.latitude()).isEqualTo(10.7769);
    assertThat(point.longitude()).isEqualTo(106.7009);
}
~~~

Test đầu phát hiện ví dụ đảo tọa độ làm latitude vượt miền. Tuy nhiên, cần thêm test cho một cặp đảo mà cả hai giá trị vẫn hợp lệ, bởi validation miền số không thể phát hiện trường hợp đó.

### 16.2. Unit test cho GeoJSON order

~~~java
@Test
void convertsLatitudeLongitudeToGeoJsonOrder() {
    GeographicCoordinates point =
            new GeographicCoordinates(10.7769, 106.7009);

    double[] coordinates = toGeoJsonCoordinates(point);

    assertThat(coordinates).containsExactly(106.7009, 10.7769);
}
~~~

Test này xác nhận phần tử đầu của array là longitude, phần tử thứ hai là latitude.

### 16.3. Integration test với Elasticsearch

Với Elasticsearch thật hoặc Testcontainers, nên:

- Tạo index với field geo_point.
- Ghi một vài document ở tọa độ đã biết.
- Tìm trong một bán kính có đơn vị rõ ràng.
- Sort tăng dần và kiểm tra địa điểm gần nhất đứng trước.
- Đọc sort value và xác nhận đơn vị.
- Thử một document thiếu tọa độ.
- Thử dữ liệu sai miền và xác nhận ingest bị từ chối theo cấu hình.

Không chỉ mock repository nếu mục tiêu là xác nhận Elasticsearch tính geo distance và sort đúng. Integration test giúp phát hiện lỗi mapping, converter và thứ tự tọa độ trong request thực tế.

## 17. Checklist tránh lỗi đảo tọa độ

Trước khi đưa dữ liệu vị trí vào Elasticsearch, hãy xác nhận:

- [ ] Nguồn dữ liệu dùng WGS 84 hoặc đã chuyển CRS chính xác.
- [ ] Latitude là giá trị Bắc/Nam, nằm trong [-90, 90].
- [ ] Longitude là giá trị Đông/Tây, nằm trong [-180, 180].
- [ ] Java GeoPoint được tạo bằng new GeoPoint(latitude, longitude).
- [ ] GeoJSON và array dùng [longitude, latitude].
- [ ] Chuỗi Elasticsearch dạng lat,lon được parse đúng thứ tự.
- [ ] Dấu âm của tọa độ Nam/Tây được giữ nguyên.
- [ ] Tọa độ dùng decimal degrees, không phải radians hay mét.
- [ ] Distance query có đơn vị như 5km.
- [ ] Geo distance sort khai báo unit rõ ràng.
- [ ] DTO ghi rõ tên latitude và longitude.
- [ ] Có test cho trường hợp đảo tọa độ nhưng cả hai số vẫn nằm trong miền hợp lệ.

## 18. Tổng kết

Elasticsearch geo_point dùng tọa độ địa lý WGS 84 theo độ thập phân. Latitude nằm trong [-90, 90], longitude nằm trong [-180, 180]. Thứ tự tọa độ phụ thuộc định dạng: JSON object ghi rõ lat/lon; chuỗi Elasticsearch dùng latitude,longitude; array, GeoJSON và WKT dùng longitude,latitude. Spring Data GeoPoint constructor nhận latitude trước longitude, còn GeoJsonPoint.of nhận longitude trước latitude.

Đơn vị khoảng cách là đơn vị chiều dài, tách biệt với độ góc của tọa độ. Geo distance query dùng giá trị như 5km; geo distance sort dùng thuộc tính unit như km và mặc định mét nếu bỏ qua. Arc là cách tính mặc định phù hợp cho khoảng cách địa lý; plane là xấp xỉ phẳng và cần được cân nhắc theo phạm vi.

Lỗi đảo tọa độ có thể bị phát hiện khi latitude vượt miền hợp lệ, nhưng cũng có trường hợp cả hai giá trị vẫn hợp lệ và Elasticsearch âm thầm lưu sai vị trí. Hãy dùng tên field rõ ràng, value object có validation, mapper riêng cho GeoJSON, kiểm tra CRS và test với các vị trí đã biết. Nếu cần khoảng cách theo đường đi, dùng routing service thay vì coi geo distance là quãng đường di chuyển.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – GeoPoint API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/geo/GeoPoint.html)
- [Spring Data Elasticsearch – GeoJsonPoint API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/geo/GeoJsonPoint.html)
- [Elasticsearch – Geo point field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-point)
- [Elasticsearch – Geo distance query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-geo-distance-query)
- [Elasticsearch – Sort search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/sort-search-results)
- [RFC 7946 – The GeoJSON Format](https://www.rfc-editor.org/rfc/rfc7946)
