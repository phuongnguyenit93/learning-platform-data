# Dữ liệu không gian và các dạng truy vấn theo vị trí trong NoSQL

Nhiều hệ thống không chỉ cần biết **đối tượng là gì** mà còn cần biết **đối tượng ở đâu**, **gần vị trí nào**, **nằm trong khu vực nào** và **có giao với tuyến đường hoặc vùng nào không**. Ứng dụng giao hàng tìm tài xế gần điểm nhận, hệ thống IoT kiểm tra thiết bị trong vùng quản lý, bản đồ tìm cửa hàng trong khu vực và nền tảng vận tải phải xử lý những yêu cầu như vậy.

**Dữ liệu không gian** (*spatial/geospatial data*) biểu diễn vị trí và hình dạng của đối tượng. **Truy vấn không gian** sử dụng quan hệ hình học hoặc khoảng cách để tìm đối tượng phù hợp. Trong NoSQL, khả năng này có thể xuất hiện bên trong document database, công cụ tìm kiếm, hệ key–value có chỉ mục địa lý hoặc hệ dữ liệu chuyên biệt.

Điểm cần nhớ từ đầu: lưu hai trường `latitude` và `longitude` chỉ là **lưu tọa độ**. Muốn tìm điểm gần nhất hay kiểm tra điểm trong đa giác hiệu quả, ta còn cần **kiểu dữ liệu hình học, hệ tọa độ, chỉ mục không gian và ngữ nghĩa truy vấn chính xác**.

Bài học sử dụng ví dụ các trạm dịch vụ và khu vực hoạt động trên bản đồ, đồng thời hướng dẫn những truy vấn phổ biến với cú pháp MongoDB.

## 1. Dữ liệu không gian giải quyết bài toán gì?

Giả sử nền tảng cho thuê xe có các trạm và vùng cho phép nhận/trả xe. Những câu hỏi dưới đây đều liên quan vị trí nhưng không cùng một dạng toán học:

| Câu hỏi nghiệp vụ | Dạng truy vấn | Dữ liệu tối thiểu |
| --- | --- | --- |
| “Có trạm nào cách tôi dưới 2 km?” | **Tìm trong bán kính** (*radius/within-distance*) | Điểm người dùng, điểm trạm, đơn vị khoảng cách |
| “Trạm gần tôi nhất là trạm nào?” | **Láng giềng gần nhất** (*nearest neighbor, kNN*) | Điểm truy vấn và danh sách điểm ứng viên |
| “Các trạm nào nằm trong quận hoặc vùng phục vụ này?” | **Điểm trong đa giác** (*point-in-polygon*) | Điểm trạm, ranh giới khu vực |
| “Tuyến xe có cắt qua vùng hạn chế không?” | **Giao cắt hình học** (*intersects*) | Đường đi hình học, đa giác vùng hạn chế |
| “Xe vừa đi ra khỏi vùng cho thuê?” | **Geofencing theo thời gian** | Chuỗi vị trí cập nhật, vùng và trạng thái trước đó |
| “Tài xế mất bao lâu để tới nơi nhận?” | **Định tuyến trên mạng đường** (*routing*) | Vị trí đầu/cuối, đồ thị đường, tốc độ, quy tắc giao thông |
| “Những điểm nào cùng một ô bản đồ?” | **Phân nhóm không gian** (*spatial bucketing*) | Điểm và hệ chia ô như geohash/H3 |

Hai trạm có thể cách nhau 500 mét **theo đường thẳng** nhưng phải đi đường vòng 3 km mới tới được. Vì vậy, truy vấn bán kính trên bề mặt Trái Đất **không thay thế** công cụ tính đường đi hoặc thời gian di chuyển.

## 2. Các dạng hình học thường gặp

Dữ liệu không gian có thể được biểu diễn bằng những **geometry** khác nhau. Trong mô hình tài liệu, một cách biểu diễn phổ biến là **GeoJSON**.

| Geometry | Biểu diễn gì? | Ví dụ ứng dụng |
| --- | --- | --- |
| **Point** | Một vị trí | Trạm sạc, thiết bị, vị trí hiện tại của xe |
| **MultiPoint** | Tập nhiều vị trí trong một đối tượng | Các điểm khảo sát |
| **LineString** | Đường nối các điểm theo thứ tự | Tuyến đường, quỹ đạo đã ghi nhận |
| **MultiLineString** | Nhiều đường | Các đoạn tuyến của một mạng |
| **Polygon** | Vùng có ranh giới khép kín, có thể có lỗ | Khu vực giao hàng, vùng hạn chế |
| **MultiPolygon** | Nhiều vùng rời hoặc phức hợp | Nhiều vùng phục vụ thuộc cùng đơn vị |
| **GeometryCollection** | Tập các geometry có thể khác loại | Bộ đối tượng bản đồ dùng chung metadata |

Ví dụ một điểm trạm:

~~~json
{
  "type": "Point",
  "coordinates": [106.7000, 10.7760]
}
~~~

Ví dụ một tuyến đi qua ba tọa độ:

~~~json
{
  "type": "LineString",
  "coordinates": [
    [106.6990, 10.7750],
    [106.7040, 10.7800],
    [106.7100, 10.7850]
  ]
}
~~~

Ví dụ một vùng hình chữ nhật đơn giản:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.6950, 10.7730],
      [106.7110, 10.7730],
      [106.7110, 10.7880],
      [106.6950, 10.7880],
      [106.6950, 10.7730]
    ]
  ]
}
~~~

Trong GeoJSON, `Polygon.coordinates` là **mảng các vòng** (*rings*). Vòng ngoài mô tả ranh giới vùng; các vòng tiếp theo có thể mô tả lỗ bên trong. **Điểm cuối của mỗi vòng phải lặp lại điểm đầu để đóng vòng.** Hướng sắp xếp tọa độ của vòng cũng có quy tắc trong chuẩn GeoJSON; khi chuyển định dạng cần bảo toàn hướng và ý nghĩa vùng.

### 2.1. Tọa độ không phải tên đường hoặc địa chỉ

Địa chỉ “Số 10 đường A, phường B” là mô tả hành chính/ngôn ngữ tự nhiên; vị trí hình học là tọa độ. Hai quá trình khác nhau:

- **Geocoding:** chuyển địa chỉ văn bản thành tọa độ hoặc geometry, thường cần dịch vụ dữ liệu địa chỉ.
- **Reverse geocoding:** từ tọa độ tìm địa chỉ hoặc địa danh gần vị trí đó.

Geocoding có thể không chính xác đến từng lối vào tòa nhà; địa chỉ còn thay đổi theo dữ liệu hành chính. Khi thiết kế hệ thống, nên lưu **tọa độ có ngữ nghĩa rõ ràng** và **địa chỉ hiển thị** thành các thuộc tính riêng nếu cả hai đều cần.

## 3. Hệ tọa độ: phần bắt buộc để tránh trả kết quả sai

### 3.1. Kinh độ và vĩ độ

Vị trí phổ biến trên bản đồ dùng **kinh độ** (*longitude*) và **vĩ độ** (*latitude*).

- Longitude thường nằm trong khoảng −180° tới +180°.
- Latitude thường nằm trong khoảng −90° tới +90°.
- Trong **GeoJSON theo WGS 84**, thứ tự tọa độ là **[longitude, latitude]**.

~~~json
{
  "type": "Point",
  "coordinates": [106.7000, 10.7760]
}
~~~

Ở ví dụ này, **106.7000 là kinh độ**, **10.7760 là vĩ độ**. Nhiều giao diện hiển thị vị trí theo thứ tự “latitude, longitude”, trong khi GeoJSON dùng “longitude, latitude”. Đảo ngược hai giá trị có thể khiến điểm nằm ở vùng hoàn toàn khác hoặc tạo tọa độ không hợp lệ.

Một số vị trí hoặc geometry ba chiều có thể có thành phần thứ ba, ví dụ độ cao, nhưng **không mặc định** rằng hệ chỉ mục hay phép tính khoảng cách sử dụng thành phần độ cao. Nhiều truy vấn địa lý vận hành trên mặt phẳng hoặc mặt cầu hai chiều.

### 3.2. CRS, WGS 84 và tọa độ phẳng

**Coordinate Reference System (CRS)** xác định cách các con số tọa độ ánh xạ ra vị trí trên Trái Đất hoặc trên một mặt phẳng.

- **WGS 84 / EPSG:4326:** được dùng rộng rãi để biểu diễn tọa độ kinh độ–vĩ độ.
- **Hệ tọa độ chiếu** như Web Mercator (EPSG:3857): biểu diễn vị trí theo một phép chiếu sang mặt phẳng; đơn vị có thể là mét trên mặt phẳng chiếu, nhưng khoảng cách trên bản đồ chiếu **không đồng nghĩa** khoảng cách thực địa ở mọi vĩ độ.
- **Hệ tọa độ địa phương:** có thể phù hợp cho các phép đo kỹ thuật trong phạm vi nhỏ nếu chọn phép chiếu đúng.

**Không tính mét bằng cách lấy hiệu longitude/latitude rồi dùng công thức khoảng cách Euclid trực tiếp.** Độ dài tương ứng với một độ kinh độ thay đổi theo vĩ độ, và đơn vị của vĩ độ–kinh độ là **độ góc**, không phải mét.

Đối với dữ liệu điểm trên phạm vi thành phố hoặc nhiều quốc gia, hãy hiểu rõ cách hệ quản trị tính khoảng cách trên Trái Đất và đơn vị mà mỗi toán tử trả về. Khi cần độ chính xác địa trắc cao, mô hình ellipsoid, phép chiếu phù hợp và phần mềm GIS chuyên dụng có thể cần thiết.

### 3.3. Khoảng cách đường chim bay

Một phép xấp xỉ phổ biến để đo khoảng cách trên mặt cầu là **Haversine**:

\[
a = \sin^2\left(\frac{\Delta\varphi}{2}\right)
  + \cos(\varphi_1)\cos(\varphi_2)
    \sin^2\left(\frac{\Delta\lambda}{2}\right)
\]

\[
d = 2R\arcsin(\sqrt{a})
\]

Trong đó \(\varphi\) là vĩ độ, \(\lambda\) là kinh độ **đã đổi sang radian**, \(R\) là bán kính cầu giả định. Đây là **khoảng cách cung lớn trên mặt cầu**, không phải quãng đường ô tô, và vẫn là xấp xỉ so với bề mặt ellipsoid thực tế.

Trong ứng dụng dùng MongoDB với GeoJSON và chỉ mục `2dsphere`, thường nên tận dụng toán tử truy vấn địa lý của database, thay vì tự lấy mọi điểm rồi tính Haversine trong application.

## 4. Lưu dữ liệu không gian trong NoSQL

Một document trạm dịch vụ có thể lưu cả metadata nghiệp vụ và geometry:

~~~json
{
  "_id": "station-A",
  "name": "Tram A",
  "category": "charging",
  "active": true,
  "capacity": 8,
  "location": {
    "type": "Point",
    "coordinates": [106.7000, 10.7760]
  }
}
~~~

Field `location` là một **đối tượng lồng nhau** dạng GeoJSON Point. Field `capacity` phục vụ nghiệp vụ nhưng không ảnh hưởng trực tiếp vị trí. Nhờ mô hình tài liệu, cùng một bản ghi có thể kết hợp thông tin không gian và phi không gian.

Dữ liệu không gian không bắt buộc phải là GeoJSON:

- Một số hệ lưu geometry bằng cấu trúc nội bộ hoặc dạng nhị phân chuyên dụng.
- Key–value store có thể cung cấp **kiểu lệnh geospatial** và chỉ mục cho điểm.
- Search engine có thể quản lý field **geo_point** hoặc **geo_shape**.
- Một số hệ dùng **geohash hoặc mã ô không gian** như giá trị khóa để phân vùng trước khi lọc hình học.

Điểm chung là ứng dụng phải phân biệt **geometry đúng về mặt ngữ nghĩa** và **chuỗi/mã dùng để tra cứu hoặc phân vùng**. Một ô geohash không tự đại diện chính xác cho toàn bộ đa giác nghiệp vụ.

## 5. Chỉ mục không gian: vì sao cần thiết?

Nếu có 10 triệu trạm, câu hỏi “trạm nào nằm cách tôi 2 km?” không nên buộc ứng dụng tải 10 triệu tọa độ về để tính lần lượt. **Spatial index** giúp hệ thống giảm tập ứng viên trước khi kiểm tra điều kiện không gian.

Khác với B-tree một chiều dùng cho giá trị có thứ tự, dữ liệu địa lý có hai hoặc nhiều chiều. Các cơ chế thường gặp:

| Cơ chế | Ý tưởng | Phạm vi cần hiểu |
| --- | --- | --- |
| **R-tree / R*-tree** | Nhóm geometry theo những hình bao tối thiểu | Hỗ trợ lọc vùng và giao cắt; ứng viên có thể cần kiểm tra hình học chính xác |
| **Quad-tree** | Chia không gian thành các ô nhỏ dần | Phù hợp một số thao tác phân cấp vùng |
| **Geohash** | Mã hóa vùng địa lý thành chuỗi theo mức phân giải | Hữu ích cho prefix, phân vùng hoặc tìm ứng viên gần; có hiệu ứng biên ô |
| **S2** | Chia bề mặt cầu thành các ô theo hệ phân cấp | Hỗ trợ các bài toán hình học cầu và lập chỉ mục dựa trên ô |
| **H3** | Chia không gian thành các ô phần lớn dạng lục giác theo độ phân giải | Hữu ích cho tổng hợp, phân nhóm và tìm ứng viên; ô không đồng nghĩa ranh giới chính xác |
| **2dsphere của MongoDB** | Chỉ mục địa lý trên bề mặt cầu, hỗ trợ GeoJSON | Dùng với các toán tử địa lý của MongoDB |

Không phải mọi database đều dùng thuật toán giống nhau. Chỉ mục không gian thường tìm **tập ứng viên** rồi hệ kiểm tra thêm các điều kiện hình học, metadata hoặc quyền truy cập.

### 5.1. Sai số do dùng ô không gian

Giả sử vùng bán kính 500 m nằm vắt qua ranh giới giữa hai ô geohash. Nếu chỉ tìm những điểm trong ô chứa tâm, ta có thể **bỏ sót điểm gần nằm ở ô bên cạnh**.

Một chiến lược đúng thường gồm:

1. Tìm **đủ những ô** có khả năng cắt vùng truy vấn.
2. Lấy các ứng viên từ những ô đó.
3. **Lọc lại theo geometry hoặc khoảng cách thực tế**.
4. Áp dụng thêm điều kiện nghiệp vụ và sắp xếp.

Nếu mở rộng phạm vi ô quá ít, xảy ra **false negative** (bỏ sót). Nếu lấy nhiều ô rồi không lọc chính xác, có **false positive** (trả điểm ở ngoài vùng). Việc lựa chọn độ phân giải ô phải cân đối chi phí và yêu cầu đúng.

## 6. Các dạng truy vấn vị trí: từ điểm gần tới vùng phức tạp

### 6.1. Radius query: mọi điểm trong bán kính

Cho tâm P và bán kính r, tìm các điểm Q thỏa:

\[
distance(P,Q) \le r
\]

Ứng dụng: tìm trạm sạc trong vòng 2 km. Kết quả có thể rỗng hoặc có hàng nghìn điểm. Cần thêm `limit`, phân trang hoặc lọc `active = true` nếu giao diện không thể hiển thị tất cả.

**Bán kính không giống số lượng kết quả.** “Trong 2 km” có thể trả nhiều điểm; “5 điểm gần nhất” có thể chứa điểm xa hơn 2 km nếu không kèm giới hạn bán kính.

### 6.2. Nearest-neighbor query: k điểm gần nhất

Truy vấn **kNN** lấy k điểm có khoảng cách nhỏ nhất từ một điểm truy vấn theo tiêu chí đã định. Ví dụ “lấy 10 trạm gần nhất đang hoạt động”.

Một index và thuật toán tốt có thể hỗ trợ sắp xếp theo khoảng cách. Tuy nhiên, nếu kết quả còn phải thỏa bộ lọc có độ chọn lọc thấp, cần xem kế hoạch truy vấn: một số ứng viên gần có thể bị loại vì ngừng hoạt động hoặc không có loại dịch vụ cần thiết.

Trong nhiều hệ thực, ràng buộc không gian chỉ là **bước đầu chọn ứng viên**, sau đó ứng dụng xếp hạng theo năng lực, giá, giờ mở cửa hoặc thời gian đi đường.

### 6.3. Point-in-polygon: điểm thuộc vùng

Cho đa giác G, tìm các điểm P nằm bên trong G theo ngữ nghĩa ranh giới của hệ.

Ví dụ khu vực giao hàng không nhất thiết là hình tròn: có thể là ranh giới hành chính hoặc một đa giác được vẽ trên bản đồ.

~~~text
        VÙNG PHỤC VỤ
      ┌────────────────┐
      │  A ●       ● B │
      │                │
      │       ● C      │
      └────────────────┘
                            ● D (ngoài vùng)
~~~

Với đa giác có lỗ, một điểm nằm trong vòng ngoài nhưng nằm trong **lỗ loại trừ** cần được xử lý theo ngữ nghĩa polygon (thường không thuộc phần diện tích được chọn).

### 6.4. Within, contains, intersects, touches

Các quan hệ hình học thường gặp:

| Quan hệ | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Within** | Geometry A có nằm trong geometry B? | Các trạm nằm trong vùng quản lý |
| **Contains** | Geometry A có chứa geometry B? | Vùng dịch vụ nào bao trùm một điểm |
| **Intersects** | Hai geometry có phần chung? | Tuyến đường có cắt vùng cấm? |
| **Disjoint** | Hai geometry không giao nhau? | Các vùng không chồng lấn |
| **Touches** | Chỉ tiếp xúc tại ranh giới theo ngữ nghĩa topology? | Hai khu vực giáp nhau |
| **Overlaps** | Có phần giao nhưng không chứa hoàn toàn nhau? | Hai vùng phục vụ giao nhau một phần |

Không phải công cụ NoSQL nào cũng hỗ trợ đủ mọi quan hệ topology. Cũng cần kiểm tra cách hệ xử lý **điểm đúng trên biên**, sai số số học và các geometry không hợp lệ. Có hệ dùng khái niệm vị trí trong không gian cầu; có hệ dùng mặt phẳng.

### 6.5. Bounding box: lọc vùng hình chữ nhật

**Bounding box** được xác định bằng giới hạn tối thiểu/tối đa của tọa độ trên các trục. Nó thường đơn giản và nhanh để tìm ứng viên trong một khung bản đồ.

~~~text
minLon, minLat ┌──────────────────────┐ maxLon, maxLat
               │         ●            │
               │  ●                   │
               │               ●      │
               └──────────────────────┘
~~~

Bounding box là **hình chữ nhật bao**; nếu vùng thực là hình đa giác lõm, kiểm tra bounding box sẽ có thể lấy thêm điểm ngoài đa giác. Sau đó cần lọc chính xác nếu nghiệp vụ yêu cầu ranh giới thật.

Ngoài ra, hình hộp bao theo longitude/latitude cần xử lý riêng vùng qua **kinh tuyến 180°**, vì khoảng longitude có thể bị ngắt ở ranh giới −180°/+180°.

### 6.6. Đường giao vùng và truy vấn tuyến

Cho một **LineString** đại diện quỹ đạo hoặc tuyến dự kiến, hỏi “đường này có giao vùng hạn chế không?”. Truy vấn cần xét geometry của đường và vùng, không chỉ các điểm đầu/cuối.

Nếu hai đầu đoạn thẳng đều ở ngoài vùng, **đoạn giữa vẫn có thể cắt xuyên qua vùng**. Kiểm tra chỉ điểm bắt đầu và kết thúc sẽ bỏ sót trường hợp này.

Cũng phải phân biệt đường hình học thẳng nối tọa độ với **đường đi thực trên mạng giao thông**. Muốn có quãng đường có thể đi được, luật cấm rẽ hoặc giờ cao điểm, cần dữ liệu và thuật toán routing.

## 7. Thực hành MongoDB: tạo dữ liệu điểm có chỉ mục 2dsphere

Sử dụng `mongosh` và một database riêng `nosql_geo_lab`. Những địa điểm dưới đây là **điểm giả định để thực hành truy vấn**, tọa độ minh họa thuộc khu vực TP. Hồ Chí Minh; không đại diện cho doanh nghiệp hay trạm thực tế.

Đoạn lệnh làm mới collection `stations` trong database thực hành. Không chạy trên collection chứa dữ liệu thật.

~~~javascript
const geoLab = db.getSiblingDB("nosql_geo_lab");

geoLab.stations.drop();

geoLab.stations.insertMany([
  {
    _id: "station-A",
    name: "Trạm A",
    category: "charging",
    active: true,
    capacity: 8,
    location: {
      type: "Point",
      coordinates: [106.7000, 10.7760]
    }
  },
  {
    _id: "station-B",
    name: "Trạm B",
    category: "charging",
    active: true,
    capacity: 4,
    location: {
      type: "Point",
      coordinates: [106.7065, 10.7801]
    }
  },
  {
    _id: "station-C",
    name: "Trạm C",
    category: "parking",
    active: true,
    capacity: 20,
    location: {
      type: "Point",
      coordinates: [106.7190, 10.7920]
    }
  },
  {
    _id: "station-D",
    name: "Trạm D",
    category: "charging",
    active: false,
    capacity: 2,
    location: {
      type: "Point",
      coordinates: [106.6970, 10.7850]
    }
  }
]);

// Chỉ mục địa lý hỗ trợ các truy vấn GeoJSON theo bề mặt cầu.
geoLab.stations.createIndex({ location: "2dsphere" });
~~~

Tạo index là bước quan trọng khi truy vấn dữ liệu lớn. Trong MongoDB, index `2dsphere` hỗ trợ các truy vấn hình học trên bề mặt cầu; tùy toán tử, kiểu geometry và yêu cầu chỉ mục có thể khác nhau. Ví dụ này lưu field `location` hợp lệ cho cả bốn document.

### 7.1. Truy vấn bán kính với $near

Mục tiêu: tìm các trạm **đang hoạt động** gần điểm [106.7010, 10.7770], tối đa 2.000 mét:

~~~javascript
const currentPosition = {
  type: "Point",
  coordinates: [106.7010, 10.7770]
};

geoLab.stations.find(
  {
    active: true,
    location: {
      $near: {
        $geometry: currentPosition,
        $maxDistance: 2000
      }
    }
  },
  {
    name: 1,
    category: 1,
    capacity: 1,
    location: 1
  }
).limit(10).toArray();
~~~

Với GeoJSON Point và `2dsphere`, `$maxDistance` trong ví dụ được hiểu bằng **mét**. `$near` sắp các kết quả phù hợp theo khoảng cách gần đến xa. Tham số `limit(10)` giới hạn số tài liệu trả về, không có nghĩa database đã tìm được đúng 10 trạm.

Điều kiện `active: true` giúp bỏ trạm D mặc dù D có thể nằm gần điểm truy vấn. Vì `station-C` nằm xa hơn hai trạm đầu, nó có thể không thuộc bán kính 2 km; hãy quan sát kết quả thực tế của MongoDB thay vì suy số khoảng cách từ cách vẽ.

Nếu chỉ cần “trong bán kính” mà không cần sắp theo khoảng cách, có thể dùng các phép truy vấn không gian khác phù hợp với hình tròn/vùng; lựa chọn phụ thuộc khả năng và hiệu năng của engine.

### 7.2. Tìm k trạm gần nhất, có kèm khoảng cách

Một cách là dùng aggregation `$geoNear`:

~~~javascript
geoLab.stations.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7010, 10.7770]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 2000,
      query: {
        active: true
      }
    }
  },
  {
    $project: {
      name: 1,
      category: 1,
      capacity: 1,
      distanceMeters: { $round: ["$distanceMeters", 0] }
    }
  },
  { $limit: 3 }
]).toArray();
~~~

`$geoNear` trả thêm field khoảng cách và sắp kết quả từ gần đến xa. `distanceField` là tên field do ta đặt. Trong nhiều phiên bản MongoDB, `$geoNear` phải ở **đầu pipeline** và dùng chỉ mục không gian phù hợp; ví dụ đặt nó ở stage đầu.

Đây là truy vấn **kNN có ngưỡng bán kính**: lấy tối đa 3 trạm phù hợp trong 2 km. Nếu bỏ `maxDistance`, có thể lấy các điểm xa hơn miễn thỏa các bộ lọc. Với nhiều loại điểm, chỉ mục/độ chọn lọc còn ảnh hưởng độ trễ.

### 7.3. Tìm trạm trong một Polygon

Tạo khu vực hoạt động giả định:

~~~javascript
const serviceZone = {
  type: "Polygon",
  coordinates: [[
    [106.6950, 10.7730],
    [106.7110, 10.7730],
    [106.7110, 10.7880],
    [106.6950, 10.7880],
    [106.6950, 10.7730]
  ]]
};

geoLab.stations.find(
  {
    location: {
      $geoWithin: {
        $geometry: serviceZone
      }
    }
  },
  {
    name: 1,
    active: 1,
    location: 1
  }
).toArray();
~~~

Trên dữ liệu minh họa, **A, B và D** có tọa độ trong hình chữ nhật đã khai báo; **C** nằm ngoài. Điều kiện hiện tại **không lọc `active`**, vì vậy D vẫn có thể xuất hiện dù đang tạm ngừng hoạt động.

Muốn chỉ lấy trạm hoạt động trong vùng, bổ sung `active: true` bên ngoài điều kiện `location`. Một phép tìm trong vùng và một phép lọc trạng thái là **hai điều kiện độc lập**, database sẽ kết hợp chúng theo toán tử AND của truy vấn.

### 7.4. Kết hợp điều kiện không gian và nghiệp vụ

Ví dụ chỉ lấy những trạm sạc **đang hoạt động** và có ít nhất 5 chỗ trong vùng:

~~~javascript
geoLab.stations.find({
  category: "charging",
  active: true,
  capacity: { $gte: 5 },
  location: {
    $geoWithin: {
      $geometry: serviceZone
    }
  }
}).toArray();
~~~

Ở bộ dữ liệu minh họa, trạm A đáp ứng toàn bộ điều kiện. B có `capacity = 4` nên không đạt ngưỡng; D `active = false`; C thuộc category khác và ở ngoài vùng.

Bài toán thực có thể thêm thuộc tính như số chỗ **đang trống**, loại sạc, trạng thái cập nhật và thời hạn hiệu lực. Các thuộc tính biến động nhanh cần có chiến lược ghi/cập nhật và tránh cache cũ.

## 8. Truy vấn hình học đường và giao vùng

Tạo collection lưu tuyến theo dạng `LineString`:

~~~javascript
geoLab.routes.drop();

geoLab.routes.insertMany([
  {
    _id: "route-1",
    name: "Tuyến 1",
    path: {
      type: "LineString",
      coordinates: [
        [106.6900, 10.7800],
        [106.7000, 10.7800],
        [106.7150, 10.7800]
      ]
    }
  },
  {
    _id: "route-2",
    name: "Tuyến 2",
    path: {
      type: "LineString",
      coordinates: [
        [106.7200, 10.7900],
        [106.7250, 10.7950]
      ]
    }
  }
]);

geoLab.routes.createIndex({ path: "2dsphere" });

geoLab.routes.find({
  path: {
    $geoIntersects: {
      $geometry: serviceZone
    }
  }
}).toArray();
~~~

**route-1** đi ngang qua đa giác nên giao với vùng; **route-2** nằm ngoài vùng minh họa. Phép `$geoIntersects` đánh giá **giao hình học**. Nó không trả lời tuyến có được phép đi qua vùng đó hay không; quyền đi lại là **quy tắc nghiệp vụ** cần kết hợp với dữ liệu vùng hạn chế, loại phương tiện và hiệu lực thời gian.

Nếu đường thực tế là các đoạn cong hoặc nhiều điểm GPS, cần đủ điểm để biểu diễn hình học mong muốn. Hai điểm đầu/cuối của tuyến **không đủ** để tái tạo chính xác một lộ trình thực có nhiều chỗ rẽ.

### 8.1. Truy vấn ngược: tìm vùng chứa một điểm

Một hệ thống có thể có nhiều vùng quản lý và cần biết vị trí thiết bị thuộc vùng nào. Mô hình lưu đa giác vào collection `zones`:

~~~javascript
geoLab.zones.drop();

geoLab.zones.insertOne({
  _id: "zone-1",
  name: "Vùng phục vụ thử nghiệm",
  geometry: serviceZone
});

geoLab.zones.createIndex({ geometry: "2dsphere" });

const devicePoint = {
  type: "Point",
  coordinates: [106.7000, 10.7760]
};

geoLab.zones.find({
  geometry: {
    $geoIntersects: {
      $geometry: devicePoint
    }
  }
}).toArray();
~~~

Đây là dạng **truy vấn từ điểm sang collection chứa polygon**, khác với việc lưu điểm trạm rồi truyền polygon vào điều kiện `$geoWithin`. Cả hai phục vụ câu hỏi về quan hệ hình học nhưng **hướng lưu dữ liệu và đối tượng được đánh chỉ mục** khác nhau.

Trong thực tế, một điểm có thể đồng thời thuộc **nhiều vùng** (ví dụ quận, thành phố, vùng giao hàng, vùng giá cước). Hệ thống phải nêu rõ chọn vùng nào khi có chồng lấn: ưu tiên vùng nhỏ nhất, vùng có mức ưu tiên cao hoặc trả danh sách tất cả.

## 9. Các trường hợp hình học dễ gây sai

### 9.1. Điểm nằm sát biên

Một GPS có sai số vài mét, trong khi vị trí báo cáo nằm sát đường ranh giới vùng. Tại những vị trí như vậy, kết quả “ở trong/ngoài” có thể dao động.

Không nên giải quyết bằng cách tùy tiện nới mọi polygon hoặc đo khoảng cách bằng độ tọa độ. Cần xác định **ngữ nghĩa đối với biên**, mức sai số cho phép và chính sách xử lý trạng thái không chắc chắn.

Ví dụ dùng **vùng đệm/hysteresis** cho geofence: yêu cầu xe đi sâu vào trong vùng một khoảng nhất định mới xác nhận “đã vào”; phải đi xa khỏi biên một khoảng khác mới xác nhận “đã ra”. Những ngưỡng này phải phù hợp sai số định vị và mục đích ứng dụng.

### 9.2. Polygon không hợp lệ

Một đa giác có thể có:

- Vòng chưa đóng.
- Tự giao nhau theo hình “nơ”.
- Vòng trong không nằm trong vòng ngoài.
- Thứ tự vòng sai hoặc geometry có các cạnh bất thường.
- Tọa độ đảo longitude/latitude.

Một file JSON hợp lệ về **cú pháp** chưa chắc là geometry hợp lệ về **topology**. Trước khi chèn dữ liệu vùng quan trọng, nên kiểm tra geometry bằng thư viện GIS hoặc validator tương ứng. Hệ quản trị có thể từ chối một số shape không hợp lệ hoặc xử lý theo quy tắc riêng.

### 9.3. Vùng vượt kinh tuyến 180° và gần hai cực

Đường kinh tuyến −180°/+180° là cùng một đường trên bản đồ Trái Đất, nhưng khác nhau trên trục số. Một hình chữ nhật từ longitude 179° tới −179° có thể biểu diễn vùng nhỏ cắt đường đổi ngày hoặc bị diễn giải thành một vùng rất lớn nếu thao tác không đúng.

Với dữ liệu toàn cầu, cần xử lý **antimeridian**, cực và quy tắc hình học cầu của engine. Không nên áp dụng thuật toán bounding box phẳng đơn giản cho mọi vị trí địa lý.

### 9.4. Trọng tâm và khoảng cách đến vùng

“Điểm gần một vùng” không phải lúc nào cũng là khoảng cách đến **tâm vùng**. Một vùng lớn hoặc kéo dài có tâm ở rất xa điểm truy vấn, trong khi một phần ranh giới lại nằm ngay gần đó.

Nếu nghiệp vụ hỏi “cách ranh giới vùng bao xa?”, phải tính theo geometry vùng/đường biên. Nếu hỏi “cách trụ sở đặt tại tâm bao xa?”, sử dụng vị trí tâm là một **quyết định nghiệp vụ khác**.

## 10. Geofencing: truy vấn vị trí kết hợp thời gian

**Geofence** là vùng không gian dùng để xác định khi nào thiết bị hoặc phương tiện **vào**, **ra** hoặc **ở lại** vùng. So với truy vấn point-in-polygon độc lập, geofencing cần **trạng thái theo thời gian**.

Ví dụ luồng vị trí xe:

~~~text
08:00:00 -> ngoài vùng
08:00:15 -> ngoài vùng
08:00:30 -> trong vùng    => có thể phát sinh ENTER
08:01:00 -> trong vùng
08:01:30 -> ngoài vùng    => có thể phát sinh EXIT
~~~

Sơ đồ xử lý:

~~~mermaid
flowchart TD
    A[Nhận vị trí mới] --> B[Kiểm tra timestamp, deviceId, độ tin cậy]
    B --> C[Truy vấn vùng chứa điểm]
    C --> D[Đối chiếu trạng thái trước đó]
    D --> E{Có chuyển trạng thái hợp lệ?}
    E -->|Có| F[Ghi sự kiện ENTER hoặc EXIT]
    E -->|Không| G[Cập nhật trạng thái nếu cần]
    F --> H[Phát sự kiện idempotent]
~~~

### 10.1. Vì sao không chỉ kiểm tra từng điểm?

Một thiết bị có thể gửi lại cùng gói tin, gửi dữ liệu trễ hoặc mất tín hiệu GPS. Nếu mỗi điểm ở trong vùng đều tạo sự kiện “ENTER”, ứng dụng sẽ gửi hàng chục thông báo trùng.

Thông thường cần:

1. **Khóa định danh thiết bị** và mốc thời gian vị trí.
2. **Trạng thái trước đó** của từng device–zone.
3. **Quy tắc chuyển trạng thái** outside → inside và inside → outside.
4. **Idempotency key** cho sự kiện để retry không tạo lặp.
5. **Chính sách lọc nhiễu** ở vùng biên và xử lý dữ liệu đến sai thứ tự.

Một cách biểu diễn sự kiện:

~~~json
{
  "eventId": "veh-15|zone-1|ENTER|2026-11-14T08:00:30Z",
  "deviceId": "veh-15",
  "zoneId": "zone-1",
  "eventType": "ENTER",
  "observedAt": "2026-11-14T08:00:30Z"
}
~~~

`eventId` là ví dụ khóa idempotency; trong hệ thật cần quy tắc duy nhất phù hợp với việc có thể **vào cùng vùng nhiều lần** tại các thời điểm khác nhau. Timestamp đơn lẻ không luôn đủ nếu hai sự kiện cùng thời điểm hoặc dữ liệu không có thứ tự ổn định.

### 10.2. Lưu vị trí hiện tại và lịch sử

Có hai loại dữ liệu khác nhau:

- **Vị trí mới nhất:** một document cho mỗi thiết bị, thường được cập nhật liên tục và dùng để hiển thị hiện trạng/tìm thiết bị gần.
- **Lịch sử vị trí:** nhiều mẫu đo có timestamp, dùng để vẽ quỹ đạo, phân tích di chuyển hoặc truy vết sự cố.

Với vị trí mới nhất, có thể lưu:

~~~json
{
  "_id": "veh-15",
  "location": {
    "type": "Point",
    "coordinates": [106.7010, 10.7770]
  },
  "observedAt": "2026-11-14T08:00:30Z",
  "status": "AVAILABLE"
}
~~~

Khi triển khai MongoDB, `observedAt` nên lưu dưới kiểu Date thực tế. Các bản cập nhật đến trễ cần tránh ghi đè một vị trí mới hơn; có thể dùng version/sequence tăng đơn điệu hoặc conditional update theo dấu thời gian có bảo đảm phù hợp.

Đối với lịch sử rất lớn, không nên nhúng **mọi điểm GPS vô hạn** vào một mảng trong document thiết bị. Có thể dùng collection time-series hoặc dữ liệu sự kiện riêng, chính sách lưu giữ và index phù hợp. Truy vấn vị trí “hiện tại” và phân tích quỹ đạo nhiều tháng có nhu cầu rất khác nhau.

## 11. Dữ liệu vị trí kết hợp truy vấn thời gian

Nhiều bài toán là **spatiotemporal**: đồng thời có điều kiện không gian và thời gian.

Ví dụ: “Tìm các chuyến xe đi qua vùng A **từ 08:00 đến 09:00** hôm qua”.

Nếu chỉ lưu một LineString tổng hợp cho cả ngày, ta có thể biết tuyến đi qua vùng nhưng **không biết lúc nào**. Cần gắn timestamp với từng vị trí hoặc phân đoạn tuyến, hoặc lưu sự kiện từng thời điểm để chọn đúng khoảng.

Một bản ghi vị trí:

~~~json
{
  "_id": "veh-15|2026-11-14T08:00:30Z",
  "vehicleId": "veh-15",
  "observedAt": "2026-11-14T08:00:30Z",
  "location": {
    "type": "Point",
    "coordinates": [106.7010, 10.7770]
  }
}
~~~

Những câu hỏi cần đặt khi thiết kế:

| Câu hỏi | Ảnh hưởng thiết kế |
| --- | --- |
| Lấy vị trí hiện tại hay lịch sử? | Một document cập nhật hoặc nhiều điểm có timestamp |
| Chỉ cần vùng hay cả thời gian vào/ra? | Spatial predicate và trạng thái sự kiện |
| Dữ liệu đến muộn được chấp nhận bao lâu? | Watermark, version, chính sách tính lại sự kiện |
| Cần đọc theo thiết bị hay theo vùng? | Index/partition khác nhau |
| Có xóa lịch sử sau một thời hạn không? | TTL, phân vùng thời gian, chính sách retention |
| Có cần dựng quỹ đạo liên tục? | Độ dày mẫu GPS, nội suy và giới hạn sai số |

Một chỉ mục không gian không tự giải quyết mọi truy vấn thời gian. Cần đánh giá **truy vấn kết hợp**, bộ lọc thời gian, phân vùng dữ liệu, chỉ mục ghép và chi phí đọc trên từng nền tảng.

## 12. So sánh một số hướng công nghệ NoSQL hỗ trợ không gian

“Có GeoJSON” và “có truy vấn địa lý” là hai mức năng lực khác nhau. Trước khi lựa chọn công nghệ, hãy kiểm tra toán tử và kiểu geometry mà hệ thực sự hỗ trợ.

| Nhóm công nghệ | Ví dụ | Khả năng điển hình | Điều cần kiểm tra |
| --- | --- | --- | --- |
| **Document database** | MongoDB | GeoJSON, chỉ mục `2dsphere`, gần nhất, trong vùng, giao hình học | Quy tắc geometry, index và giới hạn từng toán tử |
| **Search engine** | Elasticsearch/OpenSearch | Field điểm và hình dạng, lọc theo vị trí, khoảng cách và tích hợp tìm kiếm văn bản | Ngữ nghĩa geo_shape, tính cập nhật và độ trễ index |
| **Key–value có geospatial** | Redis GEO | Lưu vị trí điểm theo khóa và tìm kiếm gần trong bán kính/hộp qua lệnh GEO | Không mặc định hỗ trợ đầy đủ polygon topology |
| **Kho dữ liệu phân tích** | Hệ dùng H3/S2/geohash hoặc hàm GIS | Tổng hợp dữ liệu theo ô, phân tích mật độ và không gian theo lô | Cần lọc chính xác sau bước chia ô; năng lực geometry mỗi engine khác nhau |
| **Graph database / routing engine** | Hệ đồ thị quan hệ đường | Tìm tuyến theo mạng cạnh và chi phí | Có cần chỉ mục điểm để chọn đỉnh đầu/cuối hay không |

Chẳng hạn, Redis có những lệnh như `GEOADD` và `GEOSEARCH` để lưu/tìm các **điểm** theo khoảng cách hoặc khu vực dạng hộp. Đó là khả năng hữu ích, nhưng không nên tự suy ra Redis GEO xử lý được mọi bài toán giao hai đa giác phức tạp.

Một nền tảng có thể dùng **nhiều hệ bổ trợ**: MongoDB lưu vị trí trạm và metadata; search engine tìm trạm theo tên cộng khoảng cách; graph/routing engine tính thời gian đi đường; streaming pipeline phát sự kiện geofence. Việc chia vai trò phải dựa trên workload, chi phí đồng bộ và yêu cầu nhất quán, không phải nhãn NoSQL chung chung.

## 13. Mở rộng: phân vùng không gian, vùng nóng và tìm kiếm hai giai đoạn

### 13.1. Phân vùng theo địa lý

Khi dữ liệu phân tán trên nhiều nút, có thể dùng **khóa vùng**, ô không gian hoặc kết hợp tenant/time để định tuyến. Ví dụ:

~~~text
deviceId -> vị trí mới nhất
geocell  -> danh sách ứng viên gần khu vực
day      -> phân vùng thời gian của lịch sử vị trí
~~~

Các khóa này phục vụ **những đường truy cập khác nhau**. Nếu dùng một geohash cell làm khóa phân vùng chính, một khu vực trung tâm đông xe có thể thành **hot partition**, trong khi vùng ít xe gần như không có tải.

Cũng có thể gặp hiện tượng một thiết bị di chuyển liên tục qua biên ô, làm thay đổi key phân vùng hoặc gây nhiều lần cập nhật index. Cần cân đối độ phân giải ô, vùng đệm, khả năng di chuyển và tần suất đọc/ghi.

### 13.2. Tìm ứng viên trước, xếp hạng sau

Một quy trình tìm tài xế gần khách thường không dừng ở phép tìm điểm gần:

~~~text
Vị trí khách
    |
    v
[1] Spatial index: tài xế trong bán kính ban đầu
    |
    v
[2] Lọc: đang rảnh, đúng loại xe, được phép nhận cuốc
    |
    v
[3] Routing: ước tính thời gian tiếp cận theo đường thực
    |
    v
[4] Xếp hạng: ETA, độ tin cậy, tải công việc
    |
    v
Danh sách đề xuất
~~~

Bước 1 giúp giảm số lượng ứng viên cho bước routing tốn kém hơn. Kết quả “tài xế gần nhất theo đường chim bay” có thể khác với “tài xế đến sớm nhất”. Vì vậy, cần ghi rõ **hàm mục tiêu** khi đánh giá thuật toán và hiệu năng.

### 13.3. Tính đúng trên phạm vi rộng

Nếu tìm “10 điểm gần nhất” trên toàn cầu, không nên chỉ truy vấn ô hiện tại rồi trả 10 điểm đầu tiên nếu chưa bảo đảm không có điểm gần hơn ở ô khác. Thuật toán tìm kiếm theo ô thường phải mở rộng ra các ô lân cận đến khi có bằng chứng về giới hạn khoảng cách.

Một cách đánh chỉ mục cung cấp khả năng lọc ứng viên nhanh không đồng nghĩa với bảo đảm kết quả **nearest neighbor toàn cục** nếu các bước cắt nhánh không được thiết kế đúng.

## 14. Hiệu năng và quan sát truy vấn trong MongoDB

Không thể kết luận truy vấn không gian nhanh chỉ vì tạo được `2dsphere` index. Nên quan sát execution plan và dữ liệu thực.

### 14.1. Quan sát truy vấn trong vùng

~~~javascript
geoLab.stations.find({
  location: {
    $geoWithin: {
      $geometry: serviceZone
    }
  }
}).explain("executionStats");
~~~

Tùy phiên bản MongoDB, `winningPlan` có thể hiển thị các stage liên quan chỉ mục không gian. Những thông tin đáng theo dõi:

- **`nReturned`:** số document cuối cùng trả về.
- **`totalKeysExamined`:** số index entry được xem xét.
- **`totalDocsExamined`:** số document được kiểm tra.
- **`executionTimeMillis`:** thời gian thực thi được báo cáo cho phép explain.
- **`winningPlan`:** đường truy cập thực tế của bộ tối ưu.

Với collection chỉ có bốn trạm, truy vấn có thể quá nhỏ để kết luận về khả năng mở rộng. Để đo ở quy mô lớn, cần bộ dữ liệu có phân bố điểm thực tế, vùng truy vấn khác nhau (trung tâm dày đặc và ngoại ô thưa), số người dùng đồng thời và tần suất thay đổi vị trí.

### 14.2. Một số phép đo nên tách riêng

| Workload | Đại lượng nên đo |
| --- | --- |
| Tìm trong 500 m / 2 km / 10 km | Latency p50/p95/p99, số ứng viên, docs/keys examined |
| Tìm 10 trạm gần nhất đang hoạt động | Độ trễ kết hợp lọc trạng thái, số kết quả thực có |
| Điểm trong đa giác lớn hoặc phức tạp | Số cạnh/ring của polygon, độ chọn lọc, CPU |
| Tuyến giao vùng | Kích thước LineString, số vùng, số geometry được kiểm tra |
| Cập nhật vị trí xe 1 lần/giây | Thông lượng ghi, chi phí cập nhật index, dữ liệu đến muộn |
| Geofencing | Độ trễ phát sự kiện, số sự kiện trùng, sai số vùng biên |
| Tìm tài xế theo ETA | Chi phí geospatial filter và chi phí routing tách biệt |

Nên kiểm tra cả **chất lượng kết quả**: có bỏ sót điểm gần biên, có trả nhầm điểm ngoài polygon, tọa độ có bị đảo và dữ liệu timestamp có bị dùng sai thứ tự không. Một hệ trả kết quả sai rất nhanh vẫn không đạt yêu cầu.

### 14.3. Chỉ mục không gian có chi phí ghi

Mỗi lần xe thay đổi vị trí, chỉ mục địa lý có thể cần cập nhật. Với hàng trăm nghìn xe gửi vị trí liên tục, chi phí ghi, replication và cập nhật các cấu trúc chỉ mục có thể đáng kể.

Một số chiến lược có thể cân nhắc tùy yêu cầu:

- Không lưu lịch sử GPS vô hạn trong tài liệu xe hiện tại.
- Giảm tần suất cập nhật nếu yêu cầu nghiệp vụ cho phép, nhưng tránh mất những sự kiện quan trọng.
- Tách luồng vị trí thời gian thực với lưu trữ lịch sử.
- Có cơ chế xử lý batch và áp dụng backpressure khi nguồn gửi quá nhanh.
- Chỉ lập chỉ mục trên những trường có truy vấn thực tế.

Cần thử những chiến lược đó bằng workload đại diện, vì giảm tần suất cập nhật có thể làm **vị trí hiển thị cũ** hoặc bỏ qua thời điểm xe đi qua geofence.

## 15. Thiết kế API truy vấn vị trí

Một API tìm trạm gần có thể được định nghĩa như:

~~~http
GET /stations/nearby?lat=10.7770&lon=106.7010&radiusMeters=2000&limit=10
~~~

Mặc dù URL dùng thứ tự tham số `lat` rồi `lon`, khi tạo GeoJSON cần chuyển thành:

~~~json
{
  "type": "Point",
  "coordinates": [106.7010, 10.7770]
}
~~~

Ứng dụng cần kiểm tra:

1. **Phạm vi giá trị:** latitude nằm trong [−90, 90], longitude trong [−180, 180]; các giá trị phải là số hữu hạn.
2. **Đơn vị:** `radiusMeters` thực sự được hiểu bằng mét và có giới hạn phù hợp.
3. **Số kết quả:** `limit` có ngưỡng trên để tránh một request lấy quá nhiều điểm.
4. **Lọc nghiệp vụ:** loại trạm, tình trạng, quyền truy cập, tenant và điều kiện hợp lệ.
5. **Tính cập nhật:** thời điểm vị trí được ghi nhận; dữ liệu cũ có được dùng không?
6. **Ngữ nghĩa kết quả:** khoảng cách đường chim bay, theo đường đi hay ETA; cách sắp xếp.
7. **Quyền riêng tư:** tọa độ thiết bị có thể là dữ liệu nhạy cảm; phân quyền, giảm độ chính xác nếu phù hợp và lưu giữ có thời hạn.

Ví dụ phản hồi API:

~~~json
{
  "origin": {
    "latitude": 10.7770,
    "longitude": 106.7010
  },
  "distanceUnit": "meter",
  "distanceType": "geodesicApproximation",
  "stations": [
    {
      "id": "station-A",
      "name": "Tram A",
      "distanceMeters": 150,
      "active": true
    }
  ]
}
~~~

**`distanceMeters: 150` trong ví dụ phản hồi chỉ minh họa định dạng**, không phải giá trị đo đã chạy qua MongoDB. API thực phải dùng kết quả tính toán từ engine hoặc thuật toán đã chọn, ghi rõ loại khoảng cách và chính sách làm tròn.

## 16. Các lỗi thường gặp khi xử lý vị trí

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Đảo longitude/latitude | Điểm sai vị trí hoặc không hợp lệ | Quy ước rõ `[lon, lat]` cho GeoJSON, kiểm tra range và ví dụ |
| Dùng độ tọa độ như mét | Bán kính sai theo vĩ độ | Dùng operator có đơn vị xác định hoặc phép đo địa lý thích hợp |
| Chỉ lưu lat/lon mà không tạo spatial index | Quét nhiều dữ liệu khi tìm gần | Tạo index phù hợp với kiểu geometry/toán tử |
| Tìm theo ô geohash hiện tại duy nhất | Bỏ sót điểm gần ở ô bên | Mở rộng ô ứng viên và lọc theo khoảng cách thật |
| Dùng bbox thay polygon rồi không lọc lại | Trả điểm ngoài vùng bất quy tắc | Kiểm tra geometry chính xác |
| Chỉ kiểm tra hai đầu LineString | Bỏ sót đường cắt ngang vùng | Dùng phép giao toàn tuyến |
| Coi gần theo mét là gần theo thời gian lái xe | Xếp hạng tài xế sai | Dùng routing/ETA cho tiêu chí thời gian |
| Bỏ qua biên và nhiễu GPS | Geofence phát ENTER/EXIT liên tục | Chính sách biên, hysteresis, độ tin cậy và trạng thái |
| Dữ liệu GPS đến trễ ghi đè vị trí mới | Hiện vị trí cũ làm “mới nhất” | So phiên bản/sequence/timestamp theo quy tắc đáng tin |
| Chỉ giới hạn kết quả mà không giới hạn vùng | Truy vấn quá tốn tài nguyên | Giới hạn bán kính, vùng, timeout và thông lượng |
| Nhầm Polygon và MultiPolygon | Mất vùng rời hoặc lỗ | Xác thực geometry và kiểm tra cấu trúc ring |
| Không giới hạn quyền truy cập vị trí | Rò rỉ thông tin di chuyển | Phân quyền, audit, retention, độ chính xác phù hợp |

## 17. Bài tập tư duy và thực hành

### Bài 1: nhận diện dạng truy vấn

Ghép yêu cầu với phép toán không gian:

1. “Tìm 5 trạm gần tôi nhất.”
2. “Tìm trạm nằm trong vùng phục vụ hình đa giác.”
3. “Kiểm tra tuyến xe có cắt vùng cấm.”
4. “Phát hiện xe vừa ra khỏi bãi.”
5. “Tính tuyến đi nhanh nhất qua đường một chiều.”

**Gợi ý:** (1) nearest neighbor; (2) point-in-polygon/within; (3) intersects; (4) point-in-polygon kết hợp trạng thái thời gian (geofencing); (5) routing trên đồ thị đường, thường sau bước xác định vị trí đầu/cuối.

### Bài 2: thứ tự tọa độ

Cho địa điểm với latitude 10.78 và longitude 106.70. Viết GeoJSON Point.

**Đáp án:**

~~~json
{
  "type": "Point",
  "coordinates": [106.70, 10.78]
}
~~~

Nếu người học viết `[10.78, 106.70]`, trường latitude 106.70 vượt khoảng vĩ độ hợp lệ; đây là lỗi đảo thứ tự.

### Bài 3: thay bán kính không đổi kNN

API được gọi với `limit = 5` và `maxDistance = 500`. Trong bán kính chỉ có hai điểm hợp lệ. API nên trả bao nhiêu điểm?

**Gợi ý:** Trả **hai điểm**, không ép đủ năm bằng cách lấy điểm nằm ngoài bán kính. `limit` là ngưỡng số kết quả tối đa, không phải cam kết số lượng điểm.

### Bài 4: vùng và trạng thái

Với dữ liệu MongoDB thực hành, trạm A, B và D nằm trong `serviceZone`. Nếu thêm điều kiện `active: true`, trạm nào bị loại?

**Gợi ý:** **D** bị loại vì `active = false`. Geometry không thay đổi nhưng điều kiện nghiệp vụ làm thay đổi kết quả.

### Bài 5: đường đi xuyên đa giác

Một tuyến có điểm đầu và điểm cuối đều nằm ngoài polygon nhưng đoạn nối đi xuyên qua vùng. Kiểm tra hai điểm đầu/cuối có đủ để quyết định `intersects` không?

**Gợi ý:** Không. Phải xét **toàn bộ hình học đường**; hai endpoint ngoài không loại trừ việc đường cắt vùng ở giữa.

### Bài 6: geofence trùng sự kiện

Thiết bị gửi cùng một điểm ở trong vùng ba lần do retry. Hệ thống gửi ba thông báo “đã vào vùng”. Vấn đề nằm ở đâu?

**Gợi ý:** Thiếu lưu trạng thái trước đó và idempotency của sự kiện. Chỉ nên tạo ENTER khi xác nhận chuyển trạng thái từ ngoài vào trong theo chính sách thiết kế.

### Bài 7: tìm kiếm theo ô

Hai điểm cách nhau 50 m nhưng nằm hai bên ranh giới geohash cell. Vì sao chỉ truy vấn cell chứa tâm có thể bỏ sót điểm?

**Gợi ý:** Ranh giới ô do hệ chia lưới quyết định, không trùng với vòng tròn bán kính. Cần xét các ô có khả năng cắt vùng và dùng khoảng cách thực để lọc lại.

### Bài 8: chọn công nghệ

Hệ thống có hai yêu cầu: truy vấn trạm trong bán kính 2 km và tính đường đi nhanh nhất từ người dùng tới mỗi trạm. Chỉ mục `2dsphere` có giải quyết đủ không?

**Gợi ý:** Không. `2dsphere` giúp tìm ứng viên theo vị trí/khoảng cách địa lý. Để tối ưu **đường đi theo giao thông**, cần đồ thị đường và thuật toán routing hoặc dịch vụ chuyên dụng, có tính tới luật giao thông và thời gian nếu cần.

### Bài 9: truy vấn polygon trên MongoDB

Dùng collection và biến `serviceZone` từ phần thực hành để tìm **trạm sạc đang hoạt động** trong vùng, chỉ trả `_id` và `name`.

**Một cách viết:**

~~~javascript
geoLab.stations.find(
  {
    category: "charging",
    active: true,
    location: {
      $geoWithin: {
        $geometry: serviceZone
      }
    }
  },
  {
    _id: 1,
    name: 1
  }
).toArray();
~~~

### Bài 10: kiểm tra hiệu năng

Chạy `explain("executionStats")` cho truy vấn `$geoWithin` trên dữ liệu thực hành; sau đó mô tả vì sao không thể kết luận rằng thời gian đo trên **4 document** đại diện cho truy vấn **10 triệu document**.

**Gợi ý:** Số lượng dữ liệu, phân bố điểm, chỉ mục, cache, mật độ vùng, độ phức tạp polygon và concurrency khác nhau rất lớn. Dùng explain để xem **đường truy cập**, và đánh giá hiệu năng trên workload cùng phân bố dữ liệu thực tế.

## 18. Từ tọa độ đến truy vấn có ý nghĩa nghiệp vụ

Khi xây dựng chức năng vị trí trong NoSQL, cần xác định lần lượt:

1. **Đối tượng hình học:** điểm, đường, vùng hay chuỗi vị trí theo thời gian?
2. **Hệ tọa độ và đơn vị:** GeoJSON longitude–latitude, khoảng cách tính theo mét hay theo quy tắc khác?
3. **Quan hệ cần hỏi:** gần nhất, trong bán kính, nằm trong vùng, giao cắt, hoặc di chuyển vào/ra?
4. **Chỉ mục và đường truy cập:** database có toán tử/geometry index phù hợp không, và truy vấn có cần lọc chính xác sau tìm ứng viên?
5. **Ràng buộc nghiệp vụ:** trạng thái trạm, quyền sử dụng, dữ liệu mới nhất, phân quyền tenant, số kết quả?
6. **Giới hạn và độ đúng:** sai số GPS, vùng biên, thời gian dữ liệu, giới hạn bán kính, timeout và tải đồng thời?

Một document có GeoJSON Point là **điểm bắt đầu để biểu diễn vị trí**. Giá trị thực sự của dữ liệu không gian xuất hiện khi hệ thống kết hợp geometry đúng, chỉ mục phù hợp và câu hỏi nghiệp vụ rõ ràng — để trả lời không chỉ “đối tượng đang ở đâu” mà còn “đối tượng nào thuộc phạm vi, tương tác với vùng hoặc có thể đến được theo tiêu chí cần thiết”.
