# Kiểm tra dữ liệu tọa độ, hình học không hợp lệ và giới hạn index trong MongoDB

## 1. Vì sao dữ liệu địa lý hợp lệ quan trọng hơn việc chỉ tạo index?

Một ứng dụng tìm nhà cho thuê có thể lưu vị trí căn hộ, điểm giao dịch, ga tàu và ranh giới khu vực dưới dạng **GeoJSON**. Những truy vấn thường gặp:

- Tìm các căn hộ trong bán kính **3 km** từ một vị trí.
- Chỉ hiển thị tin đăng nằm trong **ranh giới khu vực** đã chọn.
- Tìm các địa điểm gần nhất của cùng **tenant** hoặc cùng nhóm dịch vụ.
- Kiểm tra điểm giao hàng có nằm trong vùng phục vụ hay không.
- Đồng bộ bản đồ khi có vị trí được cập nhật hoặc bị xóa.

Giả sử API nhận tọa độ:

~~~javascript
{
  type: "Point",
  coordinates: [10.776, 106.700]
}
~~~

Người dùng có thể nghĩ đây là **latitude = 10.776, longitude = 106.700**. Nhưng GeoJSON dùng thứ tự **[longitude, latitude]**, nên MongoDB sẽ diễn giải phần tử thứ hai là latitude **106.700**, nằm ngoài phạm vi địa lý hợp lệ. Một **2dsphere index** có thể từ chối hình học này.

Nguy hiểm hơn, một cặp như **[40, 10]** có cả hai số nằm trong các khoảng hợp lệ, dù có thể bị đảo từ **[latitude=40, longitude=10]**. Kiểm tra giới hạn số **không đủ** phát hiện mọi lỗi đảo trục.

Vì vậy, hệ thống đáng tin cậy cần nhiều lớp:

~~~text
Request từ client / hệ thống nhập liệu
                 |
                 v
        Parse và kiểm tra kiểu
                 |
                 v
       Xác thực CRS, thứ tự tọa độ
                 |
                 v
     Kiểm tra range và hình học/topology
                 |
                 v
       Quy tắc nghiệp vụ, tenant, khu vực
                 |
                 v
     MongoDB schema validation (nếu có)
                 |
                 v
       Ghi document + geospatial index
                 |
                 v
       Query, quan sát và đối soát dữ liệu
~~~

**Điểm mấu chốt:** index hỗ trợ tìm kiếm và có thể từ chối một số geometry không hợp lệ; nó **không** tự phát hiện điểm đặt sai thành phố nhưng vẫn là một GeoJSON Point hợp lệ, không xác thực quyền truy cập và không thay thế quy trình kiểm tra GIS.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc và kiểm tra tọa độ **longitude, latitude** trong hệ **WGS84**.
2. Phân biệt **GeoJSON Point, LineString, Polygon, MultiPolygon** và các lỗi cấu trúc phổ biến.
3. Hiểu **vòng Polygon khép kín, self-intersection, holes, antimeridian** và những giới hạn của việc kiểm tra tại ứng dụng.
4. Dùng **2dsphere index** cho dữ liệu địa lý trên Trái Đất; biết khi nào **2d index** không phù hợp.
5. Giải thích cách index xử lý **missing/null/empty location**, dữ liệu lỗi và compound index.
6. Viết truy vấn **$near, $geoWithin, $geoIntersects, $geoNear** đúng hình học và đơn vị.
7. Kiểm tra dữ liệu trước import, phát hiện dữ liệu cần quarantine và khắc phục index build thất bại.
8. Hiểu các giới hạn: **geospatial index không phải unique constraint, không phải shard key, không cover query tùy ý và có chi phí với geometry phức tạp**.
9. Dùng lab mongosh với dữ liệu cố định và giải thích kết quả query.

> Bài học thuộc **Database Engine Document MongoDB → Dữ liệu địa lý**. Những ví dụ dùng database **mongo_geo_validation_lab_298** và ID có prefix **geo298-**. Tọa độ thành phố trong lab là điểm xấp xỉ để học truy vấn, **không dùng để điều hướng hoặc xác định ranh giới pháp lý**.

## 2. GeoJSON và quy ước tọa độ phải thống nhất

### 2.1. Một GeoJSON Point hợp lệ

~~~javascript
{
  type: "Point",
  coordinates: [106.700, 10.776]
}
~~~

Hai giá trị trong Array:

- **coordinates[0] = 106.700**: longitude, kinh độ, đơn vị **độ**.
- **coordinates[1] = 10.776**: latitude, vĩ độ, đơn vị **độ**.

**Không** phải [latitude, longitude], **không** phải [x tính bằng mét, y tính bằng mét].

### 2.2. Giới hạn longitude và latitude

Trong biểu diễn kinh độ/vĩ độ WGS84 thông dụng:

| Đại lượng | Khoảng giá trị hợp lệ | Cách đọc |
| --- | --- | --- |
| **Longitude** | Từ **-180** đến **180** độ | Tây âm, Đông dương |
| **Latitude** | Từ **-90** đến **90** độ | Nam âm, Bắc dương |

Ví dụ:

~~~javascript
// Hợp lệ về kiểu và range:
[106.700, 10.776]
[-73.985, 40.758]
[0, 0]

// Sai nếu biểu diễn lon/lat WGS84:
[106.700, 95.000]     // latitude quá 90
[210.000, 10.776]     // longitude quá 180
["106.700", "10.776"] // String thay vì Number
[106.700]             // thiếu latitude
~~~

**Hợp lệ về range chưa có nghĩa đúng địa điểm.** [10.776, 40.758] có thể là một điểm hợp lệ trên bản đồ nhưng lại sai hoàn toàn nếu ứng dụng đã đảo trục từ nguồn dữ liệu khác.

### 2.3. Cặp tọa độ 0,0 không phải null

Điểm **[0,0]** ở gần vịnh Guinea là một tọa độ hợp lệ, thường được gọi không chính thức là “Null Island”. Nếu hệ thống dùng [0,0] làm giá trị mặc định khi thiếu vị trí, MongoDB có thể lưu và lập index nó như một địa điểm thật.

Nên phân biệt:

- **location không có**: chưa nhận vị trí.
- **location: null**: vị trí không xác định.
- **location: {type:"Point", coordinates:[0,0]}**: vị trí số học rõ ràng.

Đừng âm thầm đổi mọi dữ liệu thiếu sang [0,0]. Với nghiệp vụ chỉ chấp nhận vị trí trong Việt Nam, có thể thêm một kiểm tra phạm vi địa lý **riêng cho nguồn dữ liệu đó**, nhưng không nên áp dụng giới hạn Việt Nam cho một collection toàn cầu.

### 2.4. WGS84 khác hệ tọa độ phẳng

GeoJSON trong truy vấn **2dsphere** dùng tọa độ kinh độ/vĩ độ trên bề mặt Trái Đất, thường gắn với **WGS84**.

Đừng nhầm:

- **EPSG:4326**: kinh độ/vĩ độ theo độ.
- **EPSG:3857**: tọa độ Web Mercator tính bằng đơn vị phẳng gần mét, không phải longitude/latitude.
- **UTM**: các tọa độ phẳng theo zone; cần phép chuyển đổi thích hợp trước khi ghi GeoJSON Point cho 2dsphere.

Ví dụ một hệ GIS gửi tọa độ Web Mercator:

~~~javascript
{ x: 11877670, y: 1206650 }
~~~

Không thể đưa thẳng thành:

~~~javascript
{ type: "Point", coordinates: [11877670, 1206650] }
~~~

và mong MongoDB hiểu đó là vị trí trên Trái Đất. Phải xác định **CRS của nguồn** rồi chuyển đổi đúng sang kinh độ/vĩ độ.

### 2.5. Độ cao không được dùng như khoảng cách không gian ba chiều

Một số dữ liệu GeoJSON có thêm thành phần độ cao:

~~~javascript
{
  type: "Point",
  coordinates: [106.700, 10.776, 18]
}
~~~

Trong phạm vi truy vấn 2dsphere thông thường, MongoDB tính toán quan hệ địa lý dựa trên **kinh độ/vĩ độ**, không thực hiện tìm kiếm không gian ba chiều theo độ cao như một GIS 3D. Nếu ứng dụng cần độ cao:

- Lưu **altitudeMeters** với đơn vị và hệ quy chiếu rõ ràng.
- Xử lý logic độ cao riêng, ví dụ một tầng nhà hoặc khoảng độ cao.
- Không giả định $near có khoảng cách 3D chỉ vì coordinates chứa phần tử thứ ba.

Để lab và validator dễ hiểu, các ví dụ sử dụng **đúng hai tọa độ** cho Point.

## 3. Các loại hình học GeoJSON thường gặp

### 3.1. Point

Một điểm:

~~~javascript
{
  type: "Point",
  coordinates: [106.700, 10.776]
}
~~~

Phù hợp vị trí một căn hộ, trạm đo, chi nhánh hoặc điểm giao hàng.

### 3.2. LineString

Một đường gấp khúc với **ít nhất hai vị trí**:

~~~javascript
{
  type: "LineString",
  coordinates: [
    [106.700, 10.776],
    [106.706, 10.783],
    [106.715, 10.792]
  ]
}
~~~

Phù hợp đường đi hoặc một tuyến vận chuyển ở mức khái quát. Hình học này không tự giải quyết các vấn đề mạng lưới đường bộ, chiều đường hoặc thời gian di chuyển.

### 3.3. Polygon

Một vùng có vòng ngoài:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.695, 10.770],
      [106.730, 10.770],
      [106.730, 10.820],
      [106.695, 10.820],
      [106.695, 10.770]
    ]
  ]
}
~~~

**coordinates** là Array của các vòng (**linear rings**), không phải một Array phẳng các điểm. Vòng đầu là ranh giới ngoài. Những vòng tiếp theo, khi có, biểu diễn **holes** theo quy tắc GeoJSON và MongoDB.

### 3.4. Polygon có hole

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.690, 10.760],
      [106.750, 10.760],
      [106.750, 10.830],
      [106.690, 10.830],
      [106.690, 10.760]
    ],
    [
      [106.710, 10.785],
      [106.710, 10.800],
      [106.725, 10.800],
      [106.725, 10.785],
      [106.710, 10.785]
    ]
  ]
}
~~~

Ví dụ mô tả vùng lớn có một vùng loại trừ bên trong. Việc sử dụng hole đúng đòi hỏi các vòng hợp lệ, không tự cắt nhau, hole nằm trong vùng ngoài và tuân theo các quy tắc hướng vòng/diện tích của GeoJSON và hệ thống geospatial.

### 3.5. MultiPoint, MultiLineString và MultiPolygon

Các kiểu này chứa nhiều phần hình học cùng loại:

~~~javascript
// Nhiều điểm:
{
  type: "MultiPoint",
  coordinates: [
    [106.700, 10.776],
    [106.750, 10.850]
  ]
}

// Nhiều đường:
{
  type: "MultiLineString",
  coordinates: [
    [
      [106.700, 10.776],
      [106.706, 10.783]
    ],
    [
      [106.715, 10.792],
      [106.724, 10.807]
    ]
  ]
}

// Nhiều Polygon:
{
  type: "MultiPolygon",
  coordinates: [
    [
      [
        [106.690, 10.760],
        [106.710, 10.760],
        [106.710, 10.790],
        [106.690, 10.790],
        [106.690, 10.760]
      ]
    ],
    [
      [
        [106.725, 10.795],
        [106.750, 10.795],
        [106.750, 10.830],
        [106.725, 10.830],
        [106.725, 10.795]
      ]
    ]
  ]
}
~~~

Với MultiPolygon, số tầng Array tăng: **MultiPolygon → Polygon → ring → position → Number**. Một lỗi thiếu một cặp dấu ngoặc có thể biến dữ liệu thành cấu trúc khác, khiến MongoDB không thể lập index hoặc truy vấn đúng.

### 3.6. GeometryCollection

Một GeometryCollection chứa các đối tượng geometry:

~~~javascript
{
  type: "GeometryCollection",
  geometries: [
    {
      type: "Point",
      coordinates: [106.700, 10.776]
    },
    {
      type: "LineString",
      coordinates: [
        [106.700, 10.776],
        [106.706, 10.783]
      ]
    }
  ]
}
~~~

**GeometryCollection dùng trường geometries**, không phải một coordinates Array như Point hoặc Polygon. Khi ứng dụng chỉ cần vị trí một căn hộ, nên giới hạn schema vào Point thay vì chấp nhận mọi kiểu GeoJSON rồi phải xử lý nhiều trường hợp hiếm.

## 4. Phân loại lỗi: cú pháp, số học, cấu trúc và topology

| Mức lỗi | Ví dụ | Vì sao nguy hiểm |
| --- | --- | --- |
| **Sai kiểu** | coordinates: ["106.7", "10.77"] | String không phải kinh độ/vĩ độ số |
| **Thiếu phần tử** | coordinates: [106.7] | Không có latitude |
| **Thừa cấp Array** | coordinates: [[106.7, 10.77]] cho Point | Dữ liệu có hình dạng MultiPoint-like, không phải Point |
| **NaN/Infinity** | coordinates: [Infinity, 10.77] | Không là vị trí hữu hạn |
| **Ngoài phạm vi** | latitude 110 | Vượt range vĩ độ |
| **Đảo trục** | [10.776, 106.700] | Vĩ độ 106.700 ngoài range; hoặc có thể âm thầm sai nếu cả hai còn trong range |
| **Sai CRS** | [11877670, 1206650] | Tọa độ phẳng bị dùng như lon/lat |
| **Line quá ngắn** | Chỉ có một position | Không tạo LineString hợp lệ |
| **Polygon không đóng** | Điểm cuối khác điểm đầu | Vòng không khép kín |
| **Polygon thiếu đỉnh** | Hai điểm lặp thành vòng | Không có diện tích thực |
| **Self-intersection** | Vòng hình nơ (bow-tie) | Nội/ngoại vùng không rõ hoặc bị từ chối |
| **Hole sai** | Hole nằm ngoài vòng bao | Topology không hợp lệ |
| **Vùng qua antimeridian** | 179°E tới -179°W | Nếu xử lý như bounding box thông thường có thể chọn sai phần Trái Đất |
| **Địa điểm sai nhưng số hợp lệ** | Điểm ở thành phố khác | Index vẫn có thể lập thành công và trả kết quả sai nghiệp vụ |
| **Nhầm đơn vị** | $maxDistance: 3 nhưng muốn 3 km | Truy vấn GeoJSON sử dụng mét; chỉ tìm 3 m |

**Không gộp các lỗi này thành “MongoDB geospatial lỗi”.** Một phần cần được chặn ở input API, một phần ở thư viện GIS, một phần ở schema validation hoặc khi tạo 2dsphere index.

## 5. Kiểm tra Point ở tầng ứng dụng

### 5.1. Không dùng parseFloat một cách tùy tiện

Ví dụ:

~~~javascript
parseFloat("106.700abc"); // Cho kết quả 106.7
~~~

Đầu vào như trên thực chất là dữ liệu không hợp lệ nếu API quy định tọa độ phải là Number. Việc ép kiểu “dễ dãi” khiến lỗi upstream không bị phát hiện.

Hợp đồng đầu vào nên rõ:

- Client gửi JSON Number, không phải chuỗi có hậu tố.
- Xác định nguồn dùng **[longitude, latitude]**.
- Các giá trị phải **hữu hạn**, nằm trong range.
- Có quy ước về precision, geocoding quality và khu vực được phép.

### 5.2. Hàm kiểm tra Point

Ví dụ JavaScript chạy được trong mongosh hoặc Node.js cho dữ liệu JSON Number thông thường:

~~~javascript
function validateGeoPoint(geometry) {
  const errors = [];

  if (!geometry || typeof geometry !== "object" ||
      Array.isArray(geometry)) {
    return ["Geometry phải là object."];
  }

  if (geometry.type !== "Point") {
    errors.push("type phải là Point.");
  }

  const coordinates = geometry.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length !== 2) {
    errors.push("coordinates phải là [longitude, latitude].");
    return errors;
  }

  const longitude = coordinates[0];
  const latitude = coordinates[1];

  if (typeof longitude !== "number" ||
      !Number.isFinite(longitude)) {
    errors.push("longitude phải là Number hữu hạn.");
  } else if (longitude < -180 || longitude > 180) {
    errors.push("longitude phải trong [-180, 180].");
  }

  if (typeof latitude !== "number" ||
      !Number.isFinite(latitude)) {
    errors.push("latitude phải là Number hữu hạn.");
  } else if (latitude < -90 || latitude > 90) {
    errors.push("latitude phải trong [-90, 90].");
  }

  return errors;
}

const candidates = [
  { type: "Point", coordinates: [106.700, 10.776] },
  { type: "Point", coordinates: [10.776, 106.700] },
  { type: "Point", coordinates: ["106.700", 10.776] },
  { type: "Point", coordinates: [106.700] },
  { type: "Point", coordinates: [0, 0] }
];

for (const geometry of candidates) {
  printjson({
    geometry,
    errors: validateGeoPoint(geometry)
  });
}
~~~

Kết quả:

- Point [106.700, 10.776] qua kiểm tra cấu trúc/range.
- Point [10.776, 106.700] lỗi latitude.
- Point có tọa độ dạng String bị từ chối.
- Point chỉ có một phần tử bị từ chối.
- [0,0] qua kiểm tra số/range vì đó là một tọa độ thật.

**Phạm vi hàm:** đây là validator cho **JSON Number và GeoJSON Point hai chiều** theo một hợp đồng ứng dụng cụ thể, không phải một bộ phân tích GeoJSON đầy đủ. Nếu dùng BSON Decimal128, Long hoặc hỗ trợ altitude, cần mở rộng kiểu dữ liệu/semantics có chủ đích; không âm thầm bỏ qua giá trị ngoài phạm vi.

### 5.3. Domain validation có thể phát hiện lỗi đảo trục kín

Giả sử một app chỉ được nhập điểm ở một vùng nhỏ đã được định nghĩa đúng về pháp lý/kỹ thuật. Có thể thêm kiểm tra coarse bounding box:

~~~javascript
function inApproxHcmLabBox(longitude, latitude) {
  return longitude >= 106.55 &&
         longitude <= 106.90 &&
         latitude >= 10.65 &&
         latitude <= 10.95;
}
~~~

Đây là **bounding box xấp xỉ dùng riêng cho lab**, không phải ranh giới hành chính TP.HCM và không được dùng trong quyết định pháp lý.

Nếu ứng dụng hỗ trợ nhiều tỉnh/quốc gia, không thể áp dụng box này cho mọi dữ liệu. Hãy dùng **danh mục vùng hợp lệ theo tenant/country**, dữ liệu geofence đã kiểm định hoặc GIS dataset tin cậy.

### 5.4. Phát hiện lỗi khoảng cách bất thường

Giả sử một cảm biến cố định gửi vị trí mới cách vị trí cũ hàng nghìn km sau một phút. Về toán học, cả hai tọa độ có thể hợp lệ, nhưng đây là tín hiệu **data quality anomaly**:

~~~text
T0: tọa độ gần TP.HCM
T1: một phút sau ở châu Âu

=> Không nhất thiết vi phạm GeoJSON,
   nhưng vi phạm kỳ vọng nghiệp vụ của thiết bị cố định.
~~~

Có thể kiểm tra:

- Tốc độ dịch chuyển tối đa theo loại thiết bị.
- Độ chính xác GPS/hệ quy chiếu.
- Vị trí có ở trong khu vực được phép không.
- Nguồn dữ liệu có bị đảo trục, thiếu dấu âm hay đổi CRS không.

**Không để 2dsphere index thay thế các quy tắc này.**

## 6. Kiểm tra LineString, Polygon và MultiPolygon

### 6.1. Quy tắc cấu trúc tối thiểu

| Geometry | Điều kiện cấu trúc cơ bản |
| --- | --- |
| **Point** | Một position với lon/lat hợp lệ |
| **MultiPoint** | Một Array các positions |
| **LineString** | Ít nhất 2 positions |
| **MultiLineString** | Array các LineStrings |
| **Polygon** | Array các rings; mỗi ring tối thiểu 4 positions, điểm đầu = điểm cuối |
| **MultiPolygon** | Array các Polygons, mỗi Polygon chứa các rings |
| **GeometryCollection** | Array geometries với những type hợp lệ |

Các điều kiện này chỉ kiểm tra **cấu trúc**. Một Polygon có thể vượt qua kiểm tra số điểm/đóng vòng mà vẫn **tự cắt nhau** hoặc có hole đặt sai chỗ.

### 6.2. Ví dụ Polygon không đóng

Sai:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.690, 10.760],
      [106.720, 10.760],
      [106.720, 10.800],
      [106.690, 10.800]
      // Thiếu phần tử lặp lại [106.690, 10.760].
    ]
  ]
}
~~~

Đúng về điều kiện đóng vòng:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.690, 10.760],
      [106.720, 10.760],
      [106.720, 10.800],
      [106.690, 10.800],
      [106.690, 10.760]
    ]
  ]
}
~~~

Một vòng có **ít nhất bốn positions** vì ba đỉnh khác nhau cần thêm một position lặp lại điểm đầu để đóng. Vòng tạo bởi một hoặc hai vị trí lặp không phải polygon có diện tích hợp lệ.

### 6.3. Self-intersection: hình nơ

Ví dụ khái niệm một vòng có các cạnh cắt nhau:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.690, 10.760],
      [106.730, 10.800],
      [106.690, 10.800],
      [106.730, 10.760],
      [106.690, 10.760]
    ]
  ]
}
~~~

Vòng này đi qua hai đường chéo cắt nhau. Việc diễn giải “bên trong” của một hình tự giao không còn là Polygon đơn giản hợp lệ theo kỳ vọng. MongoDB/2dsphere có thể từ chối geometry không hợp lệ khi build index hoặc ghi dữ liệu, tùy hình học cụ thể và phiên bản.

**Đừng chỉ kiểm tra điểm đầu = điểm cuối rồi kết luận Polygon hợp lệ.** Topology còn gồm self-intersection, degenerate edges, holes, quan hệ giữa các vòng và cách hình học đi qua bề mặt cầu.

### 6.4. Hole phải nằm trong vùng ngoài

Một hole không nên:

- Nằm hẳn bên ngoài vòng bao.
- Cắt xuyên qua vòng ngoài.
- Cắt những holes khác trái quy tắc hợp lệ.
- Có vòng tự cắt hoặc quá ít đỉnh.

Kiểm tra holes đáng tin cậy cần thuật toán topology phù hợp với **hệ tọa độ cầu/WGS84** và những quy tắc của MongoDB. Đừng tự tin dùng một hàm kiểm tra Polygon phẳng đơn giản cho các hình lớn hoặc cắt antimeridian.

### 6.5. Hàm kiểm tra cấu trúc ring

Đoạn sau giúp phát hiện sớm những lỗi đơn giản, **không phải GIS topology validator hoàn chỉnh**:

~~~javascript
function validLonLatPosition(position) {
  return Array.isArray(position) &&
    position.length === 2 &&
    typeof position[0] === "number" &&
    typeof position[1] === "number" &&
    Number.isFinite(position[0]) &&
    Number.isFinite(position[1]) &&
    position[0] >= -180 &&
    position[0] <= 180 &&
    position[1] >= -90 &&
    position[1] <= 90;
}

function samePosition(a, b) {
  return a[0] === b[0] && a[1] === b[1];
}

function validateRingStructure(ring) {
  const errors = [];
  if (!Array.isArray(ring) || ring.length < 4) {
    return ["Ring phải có ít nhất 4 positions."];
  }

  if (!ring.every(validLonLatPosition)) {
    errors.push("Có position không phải lon/lat hợp lệ.");
    return errors;
  }

  if (!samePosition(ring[0], ring[ring.length - 1])) {
    errors.push("Ring chưa đóng: đầu và cuối khác nhau.");
  }

  const distinctVertices = new Set(
    ring.slice(0, -1).map(p => p[0] + "," + p[1])
  );
  if (distinctVertices.size < 3) {
    errors.push("Ring có ít hơn 3 đỉnh phân biệt.");
  }

  return errors;
}

function validatePolygonStructure(geometry) {
  if (!geometry || geometry.type !== "Polygon") {
    return ["Geometry phải là Polygon."];
  }

  if (!Array.isArray(geometry.coordinates) ||
      geometry.coordinates.length === 0) {
    return ["Polygon cần ít nhất một ring."];
  }

  const errors = [];
  geometry.coordinates.forEach((ring, i) => {
    for (const error of validateRingStructure(ring)) {
      errors.push("Ring " + i + ": " + error);
    }
  });
  return errors;
}

printjson(
  validatePolygonStructure({
    type: "Polygon",
    coordinates: [
      [
        [106.69, 10.76],
        [106.72, 10.76],
        [106.72, 10.80],
        [106.69, 10.80]
      ]
    ]
  })
);
~~~

Kết quả sẽ có lỗi **ring chưa đóng**. Nhưng một vòng đã đóng **vẫn có thể sai topology**, ví dụ self-intersection. Đối với Polygon đầu vào từ file GIS hoặc người dùng vẽ trên bản đồ, nên dùng **thư viện GIS chuyên dụng** để kiểm tra tính hợp lệ, loại bỏ cạnh suy biến, chuẩn hóa vòng và xử lý hệ tọa độ.

### 6.6. Không sửa Polygon lỗi bằng cách đoán

Nếu nhận một Polygon tự cắt:

- Không tự sắp xếp tất cả điểm theo longitude rồi coi đó là “hình sửa”.
- Không tự thêm điểm đầu vào cuối và bỏ qua những vấn đề khác.
- Không đảo hướng rings tùy ý khi chưa hiểu quy tắc diện tích/holes.
- Không làm tròn tọa độ đến 1 chữ số rồi khiến biên hình học biến dạng.

Hướng tốt hơn:

1. Ghi lại **nguồn, CRS, ID geometry và nguyên nhân lỗi**.
2. Chặn/quarantine dữ liệu không thể chứng minh tính hợp lệ.
3. Nếu có công cụ GIS đáng tin cậy, repair và kiểm tra lại topology.
4. So sánh diện tích/vị trí trước và sau repair; những thay đổi lớn cần phê duyệt nghiệp vụ.
5. Chỉ đưa vào indexed collection khi geometry đạt hợp đồng dữ liệu.

## 7. Antimeridian, vùng lớn và winding

### 7.1. Vì sao đường 180° kinh độ dễ gây nhầm?

Một Polygon trải giữa **179°E và -179°W** có thể là một vùng nhỏ băng qua **antimeridian**, chứ không phải vùng kéo dài qua gần toàn bộ Trái Đất.

Một bounding box phẳng:

~~~text
minLongitude = -179
maxLongitude =  179
~~~

có thể đại diện vùng **rộng gần cả thế giới**, không phải vùng hẹp quanh đường đổi ngày. Vì vậy, xử lý GeoJSON qua antimeridian cần thuật toán spherical geography đúng; không được dùng một so sánh min/max longitude đơn giản trong mọi trường hợp.

### 7.2. Polygon lớn hơn một bán cầu

MongoDB có những quy tắc đặc biệt đối với **single-ringed GeoJSON Polygon** có diện tích lớn hơn một bán cầu; trên các phiên bản/đường truy vấn tương ứng có thể phải dùng **strict-winding coordinate reference system** của MongoDB để chỉ rõ cách diễn giải vùng.

Nếu sản phẩm vẽ một Polygon bao gần cả thế giới, việc chỉ đảo thứ tự các điểm có thể thay đổi ý nghĩa vùng được chọn. Hãy tham chiếu tài liệu về **Big Polygons** và phiên bản server trước khi dùng dữ liệu lớn.

### 7.3. Ranh giới hành chính cần dữ liệu chuẩn

Ranh giới pháp lý không nên được mô phỏng bằng bốn tọa độ tự đặt. Với bản đồ giao hàng hoặc địa giới hành chính:

- Dùng bộ dữ liệu có nguồn, ngày hiệu lực, độ phân giải và giấy phép phù hợp.
- Ghi nhận phiên bản ranh giới (ví dụ sau điều chỉnh địa giới).
- Kiểm tra các polygons/hole/antimeridian trước import.
- Không làm tròn hoặc đơn giản hóa quá mức nếu quyết định bị ảnh hưởng bởi điểm sát biên.
- Có quy tắc xử lý trường hợp **điểm nằm chính xác trên biên** thay vì đoán theo hình ảnh bản đồ.

**Geospatial index trả kết quả theo hình học được lưu**, không tự xác định bộ ranh giới có đúng theo quy định hiện hành hay không.

## 8. 2dsphere và 2d indexes: hai mô hình hình học khác nhau

### 8.1. 2dsphere cho dữ liệu trên Trái Đất

~~~javascript
db.places.createIndex({ location: "2dsphere" });
~~~

Index **2dsphere** hỗ trợ những truy vấn địa lý trên bề mặt cầu, gồm GeoJSON Point, LineString, Polygon và các loại hỗ trợ khác. Đây thường là lựa chọn phù hợp cho vị trí WGS84, tìm gần và quan hệ hình học trên bản đồ thực.

**Đơn vị khoảng cách:** khi dùng **GeoJSON Point** với $near/$geoNear trên 2dsphere, các ngưỡng/khoảng cách thường được biểu diễn bằng **mét** theo semantics của toán tử tương ứng.

### 8.2. 2d cho không gian phẳng/legacy coordinate pairs

~~~javascript
db.canvasPoints.createIndex({ position: "2d" });
~~~

**2d** là index cho phép tính phẳng trên các cặp tọa độ legacy. Nó phù hợp hơn với một số dữ liệu tọa độ phẳng và truy vấn không cần mô hình cầu, nhưng không nên mặc định dùng cho khoảng cách trên Trái Đất khi dữ liệu là GeoJSON lon/lat.

Ví dụ khác biệt trực giác:

~~~text
Một độ longitude ở gần xích đạo
khác khoảng cách thực tế một độ longitude ở vĩ độ cao.

Nếu dùng Euclidean distance trực tiếp trên degree
để thay thế khoảng cách trên bề mặt Trái Đất,
kết quả có thể sai đáng kể.
~~~

### 8.3. Bảng so sánh

| Tiêu chí | **2dsphere** | **2d** |
| --- | --- | --- |
| Mô hình | Hình học trên bề mặt cầu | Tọa độ phẳng/legacy |
| Dữ liệu điển hình | GeoJSON, WGS84 lon/lat | Legacy coordinate pairs |
| Điểm ứng dụng thực tế | Nhà, điểm giao hàng, geofencing, đường/vùng trên bản đồ | Canvas, tọa độ phẳng theo use case phù hợp |
| Query gần theo GeoJSON | Khoảng cách địa lý bằng mét | Không nên thay thế trực tiếp cho mô hình cầu |
| Hỗ trợ hình học phức tạp | Các GeoJSON types tương ứng | Hạn chế hơn và khác semantics |
| Có tự kiểm tra đúng địa điểm? | Không | Không |

**Đừng chỉ đổi loại index từ 2d sang 2dsphere để sửa một dữ liệu sai CRS.** Việc sửa đúng phải bắt đầu từ cách mã hóa tọa độ và hình học.

## 9. Hành vi geospatial index với dữ liệu thiếu và dữ liệu sai

### 9.1. 2dsphere có tính sparse mặc định

**2dsphere indexes có tính sparse theo bản chất**. Một document thiếu geo field hoặc geo field là null/empty array có thể **không được đưa vào index địa lý** theo quy tắc index này.

Ví dụ:

~~~javascript
// Không có location:
{ _id: "p01", name: "Chưa định vị" }

// location null:
{ _id: "p02", location: null }

// location rỗng:
{ _id: "p03", location: [] }
~~~

Các document như vậy vẫn có thể tồn tại trong collection theo schema và validation đang dùng, nhưng chúng không tự xuất hiện trong **$near** chỉ vì collection có index.

**Không nhầm sparse với “MongoDB âm thầm bỏ qua mọi GeoJSON lỗi”.**

### 9.2. Hình học không hợp lệ khác với thiếu vị trí

~~~javascript
// Có geo field nhưng kiểu/range sai:
{
  _id: "p04",
  location: {
    type: "Point",
    coordinates: [106.700, 106.700]
  }
}
~~~

Khi một 2dsphere index cần lập key cho document này, MongoDB có thể từ chối thao tác hoặc quá trình tạo index vì geometry không hợp lệ. Đây không phải một document “không có location” để sparse index bỏ qua.

Do đó, có hai nhóm cần xử lý tách biệt:

| Nhóm | Ý nghĩa | Chính sách đề xuất |
| --- | --- | --- |
| Missing/null location | Chưa có tọa độ | Quy định optional hay required; có thể lưu ngoài kết quả geo |
| Có location nhưng geometry sai | Có dữ liệu không thể diễn giải hợp lệ | Từ chối hoặc quarantine; không chờ index “sửa” |

### 9.3. Tạo index sau khi nhập dữ liệu cũ

Một collection đã có 1 triệu document mà chưa có geospatial index có thể chứa một số vị trí sai. Khi chạy:

~~~javascript
db.places.createIndex({ location: "2dsphere" });
~~~

server phải đi qua dữ liệu hiện có để tạo index. Nếu một document có geometry không index được, **index build có thể thất bại**. Việc lỗi không có nghĩa 999.999 document tốt tự động được index đầy đủ.

Vì vậy, trước khi tạo index cho legacy data, cần:

1. Đo tỷ lệ missing/null.
2. Quét định dạng GeoJSON và kiểu tọa độ.
3. Phát hiện hình học sai range/không đóng vòng/tự cắt bằng công cụ phù hợp.
4. Có chính sách sửa/quarantine dữ liệu lỗi.
5. Chạy index build trong cửa sổ và môi trường được chuẩn bị đúng.
6. Xác nhận kết quả index tồn tại bằng getIndexes/explain.

### 9.4. Ghi sau khi index đã tồn tại

Khi insert/update một document có location sai, 2dsphere index có thể khiến thao tác ghi thất bại. **Application phải bắt lỗi write**, trả thông điệp hữu ích và giữ input để người vận hành có thể xử lý; không chỉ nuốt lỗi rồi báo thành công.

Với bulkWrite, một số operation có thể đã thành công trước khi một geometry invalid khiến operation khác lỗi. **bulkWrite không phải transaction tự động.** Cần kiểm tra partial success, dùng request IDs và quyết định retry phù hợp.

## 10. Lab mongosh: điểm hợp lệ và truy vấn có kết quả đối chiếu được

### 10.1. Dữ liệu lab

Ta tạo tám địa điểm xấp xỉ để học query:

| ID | Tenant | Khu vực | Longitude | Latitude |
| --- | --- | --- | ---: | ---: |
| geo298-p01 | t001 | HCMC | 106.700 | 10.776 |
| geo298-p02 | t001 | HCMC | 106.705 | 10.782 |
| geo298-p03 | t001 | HCMC | 106.713 | 10.792 |
| geo298-p04 | t001 | HCMC | 106.724 | 10.807 |
| geo298-p05 | t001 | HCMC | 106.751 | 10.850 |
| geo298-p06 | t002 | HCMC | 106.660 | 10.760 |
| geo298-p07 | t001 | Hà Nội | 105.834 | 21.028 |
| geo298-p08 | t002 | Đà Nẵng | 108.202 | 16.054 |

Kết quả chỉ có ý nghĩa với tọa độ ví dụ, không phải tọa độ bưu chính của các địa điểm thực.

### 10.2. Seed có thể chạy lại

Chạy trong mongosh:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_geo_validation_lab_298");
  const places = lab.getCollection("lab_places");
  const tag = "geo-validation-v1";

  const rows = [
    ["geo298-p01", "t001", "hcm", "Central A", 106.700, 10.776],
    ["geo298-p02", "t001", "hcm", "Central B", 106.705, 10.782],
    ["geo298-p03", "t001", "hcm", "Central C", 106.713, 10.792],
    ["geo298-p04", "t001", "hcm", "North D",   106.724, 10.807],
    ["geo298-p05", "t001", "hcm", "East E",    106.751, 10.850],
    ["geo298-p06", "t002", "hcm", "West F",    106.660, 10.760],
    ["geo298-p07", "t001", "hanoi", "HN G",    105.834, 21.028],
    ["geo298-p08", "t002", "danang", "DN H",   108.202, 16.054]
  ];

  for (const row of rows) {
    const doc = {
      _id: row[0],
      labTag: tag,
      tenantId: row[1],
      city: row[2],
      name: row[3],
      location: {
        type: "Point",
        coordinates: [row[4], row[5]]
      }
    };

    places.replaceOne(
      { _id: doc._id, labTag: tag },
      doc,
      { upsert: true }
    );
  }

  places.createIndex(
    { location: "2dsphere" },
    { name: "ix_geo298_location" }
  );

  printjson({
    documents: places.countDocuments({ labTag: tag }),
    indexes: places.getIndexes().map(index => ({
      name: index.name,
      key: index.key
    }))
  });
})();
~~~

**Kết quả mong đợi:** 8 document mang labTag của bài; có geospatial index **ix_geo298_location**. Tái chạy script dùng replaceOne/upsert theo _id cố định để đưa dữ liệu mẫu về trạng thái gốc.

**Lưu ý về quyền sở hữu dữ liệu:** dùng database lab riêng và không xóa collection. Nếu một collection trùng tên đã chứa dữ liệu không thuộc bài hoặc một index cùng tên nhưng key khác, cần dừng để kiểm tra thay vì sửa/xóa các thành phần ấy.

### 10.3. Khai báo biến cho những ví dụ tiếp theo

~~~javascript
const lab = db.getSiblingDB("mongo_geo_validation_lab_298");
const places = lab.getCollection("lab_places");
const tag = "geo-validation-v1";
~~~

Nếu mở phiên mongosh mới, chạy lại ba dòng khai báo trên.

### 10.4. Kiểm tra tất cả tọa độ hiện có

~~~javascript
printjson(
  places.find(
    { labTag: tag },
    {
      _id: 1,
      tenantId: 1,
      city: 1,
      "location.coordinates": 1
    }
  )
  .sort({ _id: 1 })
  .toArray()
);
~~~

Kết quả nên khớp bảng tám địa điểm ở trên.

## 11. $near: tìm điểm gần một vị trí

### 11.1. Tìm địa điểm trong bán kính 3.000 mét

~~~javascript
const nearCenter = {
  type: "Point",
  coordinates: [106.700, 10.776]
};

const nearby = places.find(
  {
    labTag: tag,
    tenantId: "t001",
    location: {
      $near: {
        $geometry: nearCenter,
        $maxDistance: 3000
      }
    }
  },
  {
    _id: 1,
    name: 1,
    location: 1
  }
).toArray();

printjson(nearby);
~~~

Trong lab, các điểm **p01, p02, p03** ở gần tâm hơn 3 km, còn p04/p05 xa hơn; p06 thuộc tenant khác. Kết quả dự kiến có **3 document** (phụ thuộc thuật toán khoảng cách spherical và dữ liệu sample đúng như seed).

**Đơn vị $maxDistance là mét** khi dùng GeoJSON Point với $near và 2dsphere. Nếu truyền **3** với ý định “3 km”, bạn chỉ yêu cầu 3 mét.

### 11.2. $near có thứ tự theo khoảng cách

Một truy vấn $near thường trả các kết quả **theo khoảng cách tăng dần**. Với tâm đúng vị trí p01, p01 có khoảng cách gần 0 và thường đứng đầu.

Đừng thêm một sort khác mà vẫn giả định kết quả là nearest-first. Nếu muốn sắp theo giá thuê và chỉ giới hạn trong vùng, cần thiết kế query/order riêng.

### 11.3. $near không thay thế quyền truy cập

Filter **tenantId: "t001"** trong ví dụ là một điều kiện minh họa. Trong API thật, tenantId phải lấy từ thông tin xác thực của server, không tin tham số tự do từ request.

Không được đưa các kết quả của tenant khác vào response chỉ vì chúng gần hơn về địa lý.

### 11.4. Chỉ Point hợp lệ mới phù hợp làm tâm $near

~~~javascript
// Sai khi dùng làm tâm $near GeoJSON Point:
{
  type: "Polygon",
  coordinates: []
}
~~~

Với kiểu truy vấn $near/$geoNear thông dụng, tâm truy vấn là **Point**. Muốn tìm geometry giao/có trong một Polygon, dùng những toán tử như **$geoWithin** hoặc **$geoIntersects** phù hợp hơn.

## 12. $geoWithin: tìm điểm trong một vùng

### 12.1. Polygon hình chữ nhật cho lab

~~~javascript
const sampleArea = {
  type: "Polygon",
  coordinates: [
    [
      [106.695, 10.770],
      [106.730, 10.770],
      [106.730, 10.820],
      [106.695, 10.820],
      [106.695, 10.770]
    ]
  ]
};
~~~

Polygon này là một hình minh họa bao một phần vùng trung tâm TP.HCM, **không phải ranh giới hành chính**.

### 12.2. Truy vấn

~~~javascript
const withinArea = places.find(
  {
    labTag: tag,
    tenantId: "t001",
    location: {
      $geoWithin: {
        $geometry: sampleArea
      }
    }
  },
  { _id: 1, name: 1 }
)
.sort({ _id: 1 })
.toArray();

printjson(withinArea);
~~~

**Kết quả mong đợi:** **p01, p02, p03, p04**. p05 nằm xa về phía Đông/Bắc, p06 ở ngoài và khác tenant, p07 ở Hà Nội.

**$geoWithin không tự sắp kết quả theo khoảng cách.** Sort theo _id ở ví dụ chỉ để output ổn định cho người học.

### 12.3. Kiểm tra đầu vào Polygon trước khi query

Không đưa trực tiếp một Polygon do người dùng vẽ vào $geoWithin nếu chưa xác thực:

1. Có đúng **type: "Polygon"** hoặc loại hỗ trợ không?
2. Các rings có đủ điểm và khép kín không?
3. Có self-intersection/hole sai topology không?
4. Có crossing antimeridian hoặc area > bán cầu không?
5. Người dùng có quyền truy vấn vùng này không?
6. Hình học có quá phức tạp so với giới hạn thời gian/tài nguyên API không?

Một vùng bị nhập sai có thể làm query trả rỗng hoặc phạm vi rộng ngoài dự kiến, gây cả vấn đề hiệu năng và dữ liệu.

### 12.4. $geoWithin không luôn yêu cầu index

MongoDB có thể đánh giá một số truy vấn $geoWithin **khi không có geospatial index**, nhưng phải đọc/kiểm tra nhiều document hơn. Khi collection lớn, 2dsphere index thường rất hữu ích để thu hẹp tập ứng viên.

Đừng đánh đồng “query trả đúng trên 8 mẫu” với “query chắc chắn dùng index trên 8 triệu mẫu”.

## 13. $geoIntersects và vùng giao nhau

### 13.1. Khác nhau giữa within và intersects

**$geoWithin** hỏi liệu một geometry nằm trong vùng truy vấn theo semantics tương ứng.

**$geoIntersects** hỏi liệu geometry được index có **giao** với geometry truy vấn hay không.

Ví dụ một tuyến đường **cắt qua** khu vực nhưng không nằm hoàn toàn bên trong; nó có thể giao với Polygon dù không thể coi cả tuyến nằm trong Polygon.

~~~text
Polygon khu vực:  +----------------+
                  |                |
Tuyến đường: -----+----------------+-----
                  |                |
                  +----------------+

Tuyến giao Polygon nhưng không nằm trọn trong vùng.
~~~

### 13.2. Ví dụ geofence riêng

Giả sử một collection **lab_geofences** lưu geometry vùng:

~~~javascript
{
  _id: "geo298-fence-01",
  labTag: "geo-validation-v1",
  tenantId: "t001",
  name: "Area A",
  boundary: {
    type: "Polygon",
    coordinates: [
      [
        [106.695, 10.770],
        [106.730, 10.770],
        [106.730, 10.820],
        [106.695, 10.820],
        [106.695, 10.770]
      ]
    ]
  }
}
~~~

Trên một collection geofence riêng đã được nhập geometry hợp lệ và tạo index:

~~~javascript
db.getSiblingDB("mongo_geo_validation_lab_298")
  .getCollection("lab_geofences")
  .createIndex({ boundary: "2dsphere" });
~~~

Truy vấn geofence chứa/giao với Point:

~~~javascript
const geofences = db.getSiblingDB("mongo_geo_validation_lab_298")
  .getCollection("lab_geofences");

geofences.find({
  tenantId: "t001",
  boundary: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.705, 10.782]
      }
    }
  }
});
~~~

**Ví dụ này chỉ định schema và câu query**, chưa seed geofences trong mục 10. Muốn chạy để có kết quả, phải tạo document geofence hợp lệ trong collection lab của bạn. Không suy luận query rỗng là lỗi của toán tử nếu collection chưa có document.

### 13.3. Các đối tượng chạm biên

Một điểm nằm chính xác trên đường biên có thể là trường hợp nhạy cảm với biểu diễn tọa độ, precision và các quy tắc toán tử. Nếu kết quả ảnh hưởng **phân vùng giao hàng hoặc nghĩa vụ pháp lý**, hãy:

- Dùng hình học nguồn chất lượng cao.
- Thiết kế tolerance/buffer nghiệp vụ phù hợp.
- Kiểm thử những điểm ngay trên và ngay hai phía của ranh giới.
- Không dựa vào render pixel trên bản đồ để xác nhận quan hệ hình học chính xác.

## 14. $geoNear: đưa khoảng cách vào aggregation

### 14.1. Lấy khoảng cách để hiển thị

~~~javascript
const results = places.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.700, 10.776]
      },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: {
        labTag: tag,
        tenantId: "t001"
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      distanceMeters: 1
    }
  },
  { $limit: 10 }
]).toArray();

printjson(results);
~~~

Mục đích:

- **near**: tâm Point [lon,lat].
- **distanceField**: field kết quả chứa khoảng cách đến điểm.
- **maxDistance**: giới hạn 3.000 m trong ví dụ GeoJSON.
- **query**: thêm điều kiện tenant/lab.
- **key**: chỉ rõ geo field, đặc biệt hữu ích khi collection có nhiều geospatial indexes/fields.

### 14.2. Vị trí $geoNear trong pipeline

**$geoNear phải là stage đầu tiên** trong aggregation pipeline theo quy tắc MongoDB, không đặt một $match trước nó như pipeline aggregation thông thường.

Sai:

~~~javascript
db.places.aggregate([
  { $match: { tenantId: "t001" } },
  { $geoNear: { /* ... */ } }
]);
~~~

Đúng: đưa điều kiện tenant vào **$geoNear.query**, sau đó tiếp tục $project/$limit và các stage khác.

### 14.3. Index cần thiết

**$geoNear** và **$near** cần geospatial index phù hợp với query; nếu không, lệnh có thể lỗi. Trong lab, index **{location:"2dsphere"}** được tạo trước khi chạy.

Nếu collection có nhiều geo fields/indexes, chỉ định đúng **key** và kiểm tra planner; không để việc thêm một index thứ hai vô tình khiến aggregation bị nhập nhằng.

### 14.4. Khoảng cách là gần đúng theo mô hình địa lý

Distance tính từ điểm trên mô hình hình học Trái Đất không tương đương:

- Quãng đường lái xe.
- Quãng đường đi bộ thực tế.
- Thời gian di chuyển trên đường.
- Khoảng cách 3D có độ cao và tầng nhà.

Để tìm căn hộ “cách ga tàu 10 phút đi bộ”, 2dsphere $geoNear chỉ là bước lọc không gian ban đầu; việc tính quãng đường/thời gian cần dữ liệu mạng lưới giao thông phù hợp.

## 15. Compound 2dsphere index và các truy vấn nhiều điều kiện

### 15.1. Tại sao thêm tenantId vào index?

API thường truy vấn:

~~~javascript
{
  tenantId: "t001",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.700, 10.776]
      },
      $maxDistance: 3000
    }
  }
}
~~~

Trong collection đa tenant lớn, index chỉ trên location có thể tìm nhiều địa điểm gần đó của những tenant khác trước khi kết quả được filter. Một compound index **tenantId + location** là ứng viên:

~~~javascript
places.createIndex(
  {
    tenantId: 1,
    location: "2dsphere"
  },
  {
    name: "ix_geo298_tenant_location"
  }
);
~~~

Đây là một **index ứng viên**, không phải cam kết nó sẽ luôn được planner chọn hoặc tối ưu hơn index location cho mọi query. Cần dùng explain và đo trên dữ liệu đại diện.

### 15.2. Compound 2dsphere vẫn sparse theo geo field

Với compound index chứa **2dsphere** và những field thông thường, **sự hiện diện của geo field** quyết định document có được đưa vào index theo semantics sparse của 2dsphere.

Ví dụ document:

~~~javascript
{
  tenantId: "t001",
  name: "Chưa biết vị trí",
  location: null
}
~~~

không tự được đưa vào compound 2dsphere index chỉ vì tenantId có giá trị.

**Đừng xem index {tenantId:1, location:"2dsphere"} là một B-tree thông thường có thể thay thế mọi index tenantId cho những document không có location.**

### 15.3. Kết hợp status/loại đối tượng

Một workload:

~~~javascript
{
  tenantId: "t001",
  status: "active",
  category: "apartment",
  location: {
    $geoWithin: { $geometry: sampleArea }
  }
}
~~~

Ứng viên index có thể kết hợp equality fields và geo field theo những quy tắc được server hỗ trợ. Nhưng càng thêm field:

- Index càng tốn storage.
- Cost khi ghi/update tăng.
- Query planner có thể không chọn index ấy.
- Các prefix/sort semantics không hoàn toàn giống compound B-tree thuần số/chuỗi.

Với filter status/category thay đổi thường xuyên, cần cân nhắc liệu chúng nên ở index, truy vấn tiếp sau geo pruning hay một read model khác.

### 15.4. Không lấy một query hiếm để quyết định mọi index

Giả sử:

~~~text
Q1: tìm apartment trong 3 km theo tenant, 80% traffic
Q2: kiểm tra một Point thuộc geofence, 15%
Q3: report mọi Point toàn quốc, 5%
~~~

Ưu tiên thiết kế index phục vụ **Q1** trước. Với Q3 có thể cần batch/aggregation riêng. Tạo hàng chục index cho mọi cặp field thường khiến workload ghi nặng hơn mà không đem lại lợi ích tương xứng.

## 16. Những giới hạn quan trọng của geospatial index

### 16.1. Index không phải bộ phát hiện tất cả dữ liệu sai

Một Point nằm ở thành phố khác nhưng vẫn có lon/lat đúng phạm vi có thể được index bình thường. Một Polygon có cấu trúc hợp lệ nhưng ranh giới lỗi thời vẫn có thể được index.

Tính hợp lệ số học/hình học **khác với tính đúng đắn nghiệp vụ**.

### 16.2. Geospatial index không phải unique constraint

Hai cửa hàng khác nhau có thể ở cùng tọa độ. Một 2dsphere index không được dùng như một unique index thông thường để buộc chỉ một document tồn tại tại một vị trí.

Nếu nghiệp vụ yêu cầu mỗi **tenantId + locationId** là duy nhất:

~~~javascript
db.places.createIndex(
  { tenantId: 1, locationId: 1 },
  { unique: true }
);
~~~

Đây là **unique index riêng trên business key**, không phải unique constraint trên geometry. Trong sharded collection, các quy tắc unique index còn phụ thuộc shard key/phiên bản.

### 16.3. Geospatial index không dùng làm shard key

Không thể dùng **2dsphere index trực tiếp làm shard key index** theo cách một shard key thông thường hoạt động. Một **sharded collection có thể có geospatial index**, nhưng shard key phải tuân thủ các quy tắc sharding riêng.

Hệ quả: một truy vấn chỉ biết vị trí địa lý có thể cần scatter-gather qua nhiều shards nếu shard key không giúp mongos thu hẹp shard đích. Một 2dsphere index tốt **trên mỗi shard** không tự bảo đảm chỉ hỏi một shard.

### 16.4. Geospatial index không tạo covered query tùy ý

Geospatial indexes có những hạn chế so với B-tree thông thường, trong đó **không thể trông đợi chúng cover hoàn toàn một truy vấn** theo cách index chứa mọi field được filter/project.

Một phép $near có thể cần tính khoảng cách và đọc thông tin document; chỉ thấy IXSCAN trong explain **không** có nghĩa không hề đọc document.

### 16.5. Hình học phức tạp tạo nhiều công việc index/query

Một Polygon có hàng chục nghìn đỉnh hoặc MultiPolygon cực kỳ phức tạp có thể:

- Tạo chi phí xử lý hình học lớn.
- Tạo nhiều index keys/cells ở cấu trúc không gian nội bộ.
- Tăng storage và thời gian index build.
- Làm các query giao/bao chứa tốn CPU và latency.
- Vấp giới hạn kích thước document **16 MiB BSON** hoặc những giới hạn vận hành khác.

**Không có một số đỉnh tối đa đơn giản áp dụng cho mọi geometry/version/index settings** mà có thể dùng thay cho đo lường thực tế. Hãy đặt **giới hạn nghiệp vụ** về vertices/holes/complexity, simplification có kiểm soát và kiểm thử trên dữ liệu đại diện.

### 16.6. Geospatial index và dữ liệu dạng Array

Một location field có thể chứa cấu trúc MultiPoint/MultiPolygon hoặc những kiểu Array theo semantics được MongoDB hỗ trợ. Nhưng khi lưu nhiều geometry trong một document, bạn phải phân biệt:

- Một **MultiPoint** GeoJSON hợp lệ.
- Một **Array các GeoJSON Point documents**.
- Một **Array legacy coordinate pairs**.

Những dạng này không mặc nhiên được index/truy vấn như nhau và có thể làm tăng số index entries. Thiết kế schema rõ ràng theo use case; đừng dùng Array nhiều cấp không định nghĩa để “chứa được mọi thứ”.

### 16.7. Đơn vị khoảng cách và loại index không hoán đổi tự do

Với GeoJSON Point + 2dsphere:

~~~javascript
$maxDistance: 3000 // mét
~~~

Trong một số cú pháp legacy hoặc toán tử như **$centerSphere**, bán kính dùng **radian**, không phải mét. Ví dụ:

~~~javascript
const radiusKm = 3;
const earthRadiusKmApprox = 6378.1;

places.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.700, 10.776],
        radiusKm / earthRadiusKmApprox
      ]
    }
  }
});
~~~

Đây là ví dụ chuyển đổi **xấp xỉ 3 km thành radians** cho $centerSphere; không nhầm với cú pháp $near GeoJSON dùng $maxDistance mét.

### 16.8. Không kết hợp tùy tiện các toán tử geospatial với text/ranking

Một số query operators và aggregation stages có hạn chế về phối hợp với **$near**, **$geoNear**, **$text** hoặc logic sort/ranking. Nếu sản phẩm cần “tìm căn hộ theo keyword, rồi xếp vừa theo text relevance vừa theo khoảng cách”, phải thiết kế một pipeline/search engine phù hợp và kiểm tra hỗ trợ version; không giả định hai ranking khác nhau có thể gộp bằng cách thêm hai index.

### 16.9. Index không đảm bảo query trong thời gian hằng số

Ngay cả với index tốt, query:

~~~javascript
{
  location: {
    $geoWithin: {
      $geometry: hugePolygon
    }
  }
}
~~~

có thể trả hàng triệu document. Khi số kết quả lớn, chi phí đọc, network và serialize vẫn cao. Index giảm tập ứng viên, không làm biến mất chi phí xuất dữ liệu.

## 17. JSON Schema validation: chặn lỗi cấu trúc ở database

### 17.1. Tầng kiểm tra thứ hai

MongoDB hỗ trợ **schema validation** trên collection với **$jsonSchema**. Có thể dùng để chặn thiếu field hoặc sai cấu trúc, ngay cả khi một ứng dụng quên chạy validator phía client.

Ví dụ tạo một collection **Point-only** riêng:

~~~javascript
db.getSiblingDB("mongo_geo_validation_lab_298")
  .createCollection("lab_point_only", {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["tenantId", "location"],
        properties: {
          tenantId: {
            bsonType: "string"
          },
          location: {
            bsonType: "object",
            required: ["type", "coordinates"],
            properties: {
              type: {
                enum: ["Point"]
              },
              coordinates: {
                bsonType: "array",
                minItems: 2,
                maxItems: 2,
                items: {
                  bsonType: [
                    "double", "int", "long", "decimal"
                  ]
                }
              }
            }
          }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
~~~

**Chỉ chạy đoạn này một lần trên lab mới**; nếu collection đã tồn tại, createCollection sẽ lỗi thay vì âm thầm thay validator. Đây là ví dụ DDL, không thuộc seed bắt buộc ở mục 10.

### 17.2. JSON Schema kiểm tra được gì?

Ví dụ trên giúp kiểm tra:

- Document cần tenantId và location.
- location phải là object.
- type phải là Point.
- coordinates phải có đúng hai phần tử.
- Hai phần tử phải thuộc một trong các kiểu số BSON đã liệt kê.

Nhưng nó **chưa xác thực đầy đủ**:

- longitude trong [-180,180], latitude trong [-90,90] theo đúng vị trí.
- Không phải NaN/Infinity trong mọi nguồn/kiểu.
- Point có đúng thành phố không.
- CRS của hệ thống nhập liệu.
- Hình học Polygon phức tạp (vì schema này chỉ cho Point).

Khi cần phạm vi theo từng phần tử của Array, có thể dùng các quy tắc validation bổ sung hoặc kiểm tra application tùy khả năng biểu đạt của phiên bản. **Không nên tự cho rằng một JSON Schema đơn giản bằng toán tử homogeneous items đã kiểm tra đúng giới hạn khác nhau của longitude và latitude.**

### 17.3. Không dùng một schema Point-only cho collection hỗn hợp

Nếu cùng collection chứa Points, Lines và Polygons, ví dụ Point-only sẽ từ chối dữ liệu hợp lệ thuộc loại khác.

Tùy yêu cầu:

- Tách **places** (Point) và **geofences** (Polygon) thành hai collections.
- Dùng schema phân nhánh theo type với các quy tắc hỗ trợ.
- Chỉ chấp nhận một số GeoJSON types đã có consumer xử lý.

Không phải chấp nhận mọi loại GeometryCollection mới là “linh hoạt”. Một schema hẹp, nhất quán với ứng dụng thường dễ kiểm soát chất lượng hơn.

### 17.4. ValidationAction và dữ liệu cũ

Khi thay đổi validator trên collection đã có document cũ, cần đánh giá **validationLevel** và **validationAction**:

- Có thể chọn **error** để từ chối ghi không hợp lệ.
- Một số chiến lược chuyển tiếp có thể dùng warn/điều kiện xử lý dữ liệu cũ.
- Nếu đặt validator quá chặt ngay, những tác vụ cập nhật document legacy có thể bị chặn.

Phải có kế hoạch migration/cleanup trước khi siết validation ở production. **Schema validation không tự sửa dữ liệu cũ**.

## 18. Quarantine dữ liệu geometry lỗi trước khi tạo index

### 18.1. Không ghi dữ liệu sai rồi hy vọng index tự xử lý

Với CSV/JSON nhập từ bên ngoài, thiết kế pipeline:

~~~text
File nguồn / API ingestion
          |
          v
   Parse input thô
          |
          v
   Kiểm tra schema/range/CRS
          |
          v
  Kiểm tra geometry topology
          |
          +---------------------+
          |                     |
       HỢP LỆ                 KHÔNG HỢP LỆ
          |                     |
          v                     v
  Indexed collection     Quarantine records
          |              + reason + raw input
          v                     |
     API truy vấn         Sửa/đối soát thủ công
~~~

### 18.2. Mẫu dữ liệu quarantine

~~~javascript
{
  _id: "geo298-invalid-001",
  sourceId: "import-file-12-row-90",
  receivedAt: ISODate("2026-01-15T12:00:00Z"),
  rawLocation: {
    type: "Point",
    coordinates: [10.776, 106.700]
  },
  status: "quarantined",
  errors: [
    "latitude nằm ngoài [-90,90]",
    "nghi ngờ đảo trục"
  ]
}
~~~

Nếu rawLocation chứa dữ liệu rất lớn, nhạy cảm hoặc có payload độc hại, cần có kiểm soát retention, phân quyền và giới hạn kích thước. Không đẩy toàn bộ raw input không kiểm soát vào log production.

### 18.3. Ví dụ lọc đầu vào trước insert

~~~javascript
const candidateLocations = [
  {
    id: "candidate-good",
    location: {
      type: "Point",
      coordinates: [106.700, 10.776]
    }
  },
  {
    id: "candidate-swapped",
    location: {
      type: "Point",
      coordinates: [10.776, 106.700]
    }
  },
  {
    id: "candidate-text",
    location: {
      type: "Point",
      coordinates: ["106.700", "10.776"]
    }
  }
];

for (const row of candidateLocations) {
  const errors = validateGeoPoint(row.location);
  if (errors.length) {
    print("QUARANTINE " + row.id);
    printjson(errors);
    continue;
  }

  print("READY FOR INSERT " + row.id);
  // Chỉ sau các bước kiểm tra business/topology khác,
  // mới ghi vào collection đã có 2dsphere index.
}
~~~

Đoạn này giả định hàm **validateGeoPoint** đã được khai báo ở mục 5. Nó không ghi dữ liệu; nhằm minh họa việc từ chối trước khi index phải xử lý.

### 18.4. Không “auto swap” mọi cặp tọa độ

Nếu [10.776,106.700] bị lỗi latitude, hệ thống có thể nghi ngờ nguồn gửi đảo trục. Nhưng nếu [40,10] thì cả hai thứ tự đều nằm trong range hợp lệ. Auto swap dựa trên phạm vi có thể:

- Sửa đúng một số dữ liệu.
- Âm thầm làm sai những điểm vốn đã đúng.
- Làm mất bằng chứng lỗi nguồn.

Quy trình đúng nên biết **schema/CRS của từng nguồn**, ghi nhận transformation đã áp dụng và kiểm tra vị trí sau chuyển đổi.

## 19. Khi 2dsphere index build thất bại

### 19.1. Dấu hiệu điển hình

Ví dụ index build báo một lỗi về:

~~~text
Unable to extract geo keys
... invalid GeoJSON geometry ...
~~~

Thông điệp cụ thể có thể thay đổi giữa phiên bản/server; không parse cố định nội dung lỗi này để xác định loại lỗi nghiệp vụ.

### 19.2. Quy trình khắc phục

1. **Giữ nguyên log lỗi và phiên bản server/index.**
2. Kiểm tra collection đang chứa GeoJSON Point, Polygon, legacy pairs hay hỗn hợp.
3. Đo missing/null riêng với trường **có giá trị nhưng lỗi**.
4. Quét các lỗi cấu trúc/range bằng ứng dụng có khả năng xử lý BSON tương ứng.
5. Với Polygons, chạy bộ công cụ GIS để kiểm tra topology.
6. Sửa hoặc quarantine document được xác nhận sai theo chính sách dữ liệu.
7. Chạy lại index build trên môi trường/staging đúng quy trình.
8. Dùng **getIndexes()**, **explain()** và truy vấn mẫu để xác nhận index hoạt động.

**Không** vội drop collection hoặc bỏ toàn bộ location field để index build “xanh” nếu ứng dụng vẫn cần geospatial data. Việc xóa dữ liệu không đúng có thể làm mất thông tin cần thiết.

### 19.3. Chiến lược chuyển đổi schema cũ

Ví dụ nguồn cũ có:

~~~javascript
{
  _id: "old-001",
  lat: 10.776,
  lng: 106.700
}
~~~

Muốn chuyển sang:

~~~javascript
{
  _id: "old-001",
  lat: 10.776,
  lng: 106.700,
  location: {
    type: "Point",
    coordinates: [106.700, 10.776]
  }
}
~~~

Quy trình:

- Kiểm tra kiểu lat/lng, range và nguồn.
- Tạo location từ **[lng,lat]**, không [lat,lng].
- Đánh dấu version của migration hoặc trạng thái đã chuyển.
- Backfill theo batch có khả năng resume; log số hợp lệ/lỗi.
- Xác minh sample theo bản đồ/địa lý nghiệp vụ.
- Chỉ tạo/áp 2dsphere index sau khi đã xử lý những dữ liệu không index được.

Nếu collection đang phục vụ API production, cần thiết kế chiến lược **dual-read/dual-write hoặc migration window** theo khả năng tương thích, không sửa hàng triệu bản ghi không có checkpoint.

## 20. Explain và đo hiệu năng truy vấn địa lý

### 20.1. Xem index

~~~javascript
printjson(
  places.getIndexes().map(index => ({
    name: index.name,
    key: index.key
  }))
);
~~~

Mục tiêu: xác nhận có **location:"2dsphere"**, và biết có thêm compound index nào.

### 20.2. Explain một $near

~~~javascript
const nearPlan = places.find({
  labTag: tag,
  tenantId: "t001",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.700, 10.776]
      },
      $maxDistance: 3000
    }
  }
}).explain("executionStats");

printjson(nearPlan);
~~~

Tùy phiên bản/query engine, bạn có thể thấy những stage/chi tiết liên quan đến **GEO_NEAR_2DSPHERE**, index scan và số lượng document đã xét. Không viết code cứng dựa trên một tên stage duy nhất; output explain thay đổi theo phiên bản.

### 20.3. Explain $geoWithin

~~~javascript
const withinPlan = places.find({
  labTag: tag,
  tenantId: "t001",
  location: {
    $geoWithin: {
      $geometry: sampleArea
    }
  }
}).explain("executionStats");

printjson(withinPlan);
~~~

Trong session này, **sampleArea** phải được khai báo như mục 12. Nếu chuyển sang terminal mới, khai báo lại.

### 20.4. Những câu hỏi cần trả lời

| Metric/điểm quan sát | Câu hỏi |
| --- | --- |
| **winningPlan** | Server có dùng geospatial index mong muốn không? |
| **totalKeysExamined** | Có bao nhiêu index entries/cells được xét? |
| **totalDocsExamined** | Bao nhiêu document thực sự được đọc/xét? |
| **nReturned** | Cuối cùng trả bao nhiêu document? |
| **executionTimeMillis** | Lần chạy explain mất bao lâu? |
| **FETCH / filters bổ sung** | Có phải lọc status, tenant, category sau geo index không? |
| **Sort/limit** | Có cần thêm sort tốn kém hoặc trả quá nhiều kết quả không? |

Một query trả 5 document nhưng examined hàng triệu candidates có thể cần tối ưu. Ngược lại, query trả hàng triệu document có thể chậm vì **output volume**, dù index đã loại bỏ nhiều candidate.

### 20.5. Không dùng 8 Point làm benchmark

Lab có đúng tám Point, nên:

- Latency rất nhỏ và dễ bị ảnh hưởng bởi cache/optimizer.
- Query planner có thể chọn kế hoạch không đại diện production.
- Geometry đều đơn giản, không phản ánh cost Polygon phức tạp.

Muốn benchmark, cần dữ liệu phân bố thực tế theo địa lý, cardinality tenant, bán kính tìm kiếm, kích thước polygons, mật độ điểm, chỉ số write rate và resource limits.

## 21. Chặn truy vấn địa lý quá rộng hoặc quá phức tạp

### 21.1. Giới hạn bán kính

Ví dụ application nhận **radiusMeters**:

~~~javascript
function validateRadiusMeters(value) {
  if (!Number.isFinite(value) ||
      value <= 0 ||
      value > 50000) {
    throw new Error(
      "Bán kính phải > 0 và <= 50.000 mét."
    );
  }
  return value;
}
~~~

Ngưỡng **50.000 m** chỉ là chính sách giả định của một API, không phải giới hạn chung của MongoDB.

Nếu khách hàng có thể gửi bán kính hàng nghìn km tới collection hàng chục triệu địa điểm, index không thể ngăn một request tạo ra khối lượng kết quả quá lớn.

### 21.2. Giới hạn geometry input

Với Polygon do người dùng vẽ, có thể đặt:

- Số tối đa **vertices**.
- Số tối đa **rings/holes**.
- Số tối đa Polygons trong MultiPolygon.
- Kích thước request JSON/BSON.
- Diện tích/extent giới hạn theo quyền truy vấn.
- Deadline/maxTimeMS cho truy vấn.

Các giới hạn này nên dựa trên benchmark và mức độ chính xác cần thiết, không chỉ dựa vào khả năng lưu tối đa của BSON.

### 21.3. Pagination và thứ tự

~~~javascript
places.find({
  tenantId: "t001",
  location: {
    $geoWithin: {
      $geometry: sampleArea
    }
  }
})
.sort({ _id: 1 })
.limit(50);
~~~

Sort theo _id trong ví dụ nhằm tạo thứ tự ổn định, không sắp theo khoảng cách. Nếu muốn **nearest-first**, dùng $near/$geoNear và chính sách pagination tương ứng. Với tập lớn, skip lớn có chi phí; keyset pagination theo nhiều tiêu chí (distance, id) cũng cần cân nhắc khi vị trí/geometry thay đổi.

### 21.4. MaxTimeMS và kiểm soát chi phí

Ví dụ:

~~~javascript
places.find({
  tenantId: "t001",
  location: {
    $geoWithin: {
      $geometry: sampleArea
    }
  }
})
.maxTimeMS(3000)
.limit(100)
.toArray();
~~~

**maxTimeMS** giúp áp deadline xử lý lệnh khi được hỗ trợ; nó không thay thế rate limiting, giới hạn số kết quả và kiểm tra geometry input.

## 22. Những sai lầm thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Point bị từ chối với latitude > 90 | Gửi [lat,lon] thay vì [lon,lat] | Chuẩn hóa nguồn và validate |
| Point đã vào index nhưng ở quốc gia khác | Đảo trục kín hoặc sai geocoding | Kiểm tra CRS/khu vực nghiệp vụ |
| Tất cả tin “chưa định vị” hiện ở biển | Dùng [0,0] làm default | Để missing/null với policy rõ |
| 2dsphere index build thất bại | Một số document có GeoJSON sai | Quét, quarantine, sửa rồi build |
| Tạo Polygon nhưng query lỗi | Ring chưa đóng/Array sai cấp | Validate structure và topology |
| Polygon hình nơ cho kết quả bất thường | Self-intersection | Dùng GIS validator/repair có kiểm soát |
| Polygon hole bao vùng ngoài | Hole sai topology hoặc winding | Chuẩn hóa rings đúng quy tắc |
| Polygon qua 180° cho vùng khổng lồ | Xử lý antimeridian sai | Dùng thuật toán spherical đúng |
| Vùng hơn bán cầu diễn giải sai | Không xét strict winding/CRS đặc biệt | Xem Big Polygons docs của version |
| Query chỉ thấy địa điểm có tọa độ | 2dsphere sparse, null/missing không index | Hiểu semantics missing location |
| Query gần không trả gì khi maxDistance=3 | Nghĩ 3 là km nhưng thực là m | Dùng 3000 cho 3 km với GeoJSON |
| $geoWithin trả điểm không theo nearest-first | Toán tử không sắp theo khoảng cách | Dùng $near/$geoNear khi cần |
| $geoNear không chạy | Thiếu geo index, stage sai vị trí hoặc key nhập nhằng | Tạo index, đặt stage đầu, chọn key |
| $near trả cả tenant khác | Filter tenant không đúng | Lấy tenant từ auth context |
| Compound geo index không dùng cho doc thiếu location | Tính sparse theo geo field | Index non-geo riêng khi cần |
| Unique yêu cầu một điểm duy nhất không hiệu lực | Geospatial index không phải unique business key | Unique index trên ID nghiệp vụ |
| Tưởng geospatial index là shard key | 2dsphere không đóng vai trò shard key | Thiết kế shard key theo quy tắc sharding |
| Query toàn khu vực vẫn chậm | Geometry/quy mô kết quả quá lớn | Giới hạn vùng, pagination, cache |
| Hình học lớn tiêu tốn tài nguyên | Nhiều vertices/rings/cells | Giới hạn độ phức tạp, simplify hợp lệ |
| Query trả đúng nhưng sai đường thực tế | Khoảng cách địa lý khác route distance | Dùng routing engine khi cần |
| Phép đo thuộc tầng nhà sai | 2dsphere không phải 3D index | Lưu/check altitude/tầng riêng |
| Dữ liệu địa giới lỗi thời | Polygon hợp lệ nhưng nguồn đã cũ | Theo dõi phiên bản nguồn và hiệu lực |
| $jsonSchema cho Point làm fail Polygon | Validator cố định type Point | Tách collection hoặc schema phân nhánh |
| Auto swap tạo nhiều điểm sai | Dựa vào range để đoán CRS | Dùng metadata nguồn/transform rõ |
| Dùng $near để tìm Polygon chứa Point | Sai toán tử/hình học tâm | Dùng $geoIntersects/$geoWithin đúng |
| Chạy explain trên 8 điểm thấy nhanh rồi kết luận production nhanh | Lab quá nhỏ | Benchmark trên dữ liệu đại diện |

## 23. Checklist nhập liệu và thiết kế geospatial

### 23.1. Trước khi nhận Point

1. Biết chính xác **CRS** của nguồn.
2. Chuẩn hóa theo **[longitude,latitude]**, đơn vị độ.
3. Chặn String tùy tiện, NaN, Infinity, sai số phần tử và ngoài range.
4. Xác định missing/null khác [0,0].
5. Kiểm tra region/accuracy theo hợp đồng nghiệp vụ.
6. Ghi nhận provenance và nguồn geocoding khi cần truy vết.
7. Không tin tenantId từ request nếu chưa xác thực.

### 23.2. Trước khi nhận Polygon/MultiPolygon

1. Kiểm tra type và đúng số tầng Array.
2. Kiểm tra tất cả positions là lon/lat hợp lệ.
3. Kiểm tra rings tối thiểu bốn positions, đóng vòng.
4. Kiểm tra topology: tự cắt, hole, degenerate edges, quan hệ các polygons.
5. Xử lý antimeridian/vùng lớn/strict winding khi liên quan.
6. Đối chiếu ranh giới với nguồn dữ liệu và độ chính xác.
7. Đặt giới hạn vertices/holes/diện tích và giữ bản gốc phục vụ đối soát.

### 23.3. Trước khi tạo 2dsphere index

1. Đếm số document có geo field hợp lệ, missing/null và lỗi.
2. Kiểm tra schema có Point-only hay hỗn hợp geometry.
3. Quarantine dữ liệu không index được.
4. Lựa chọn index theo query shape (geo đơn hay tenant + geo).
5. Dự trù dung lượng/index build/impact ghi.
6. Không tạo unique/shard-key semantics sai trên geospatial index.
7. Dùng getIndexes/explain sau khi hoàn tất.

### 23.4. Trước khi đưa API địa lý vào production

1. Validate bán kính và geometry input.
2. Ràng buộc tenant, status, category bằng security context.
3. Giới hạn số kết quả/pagination.
4. Đặt deadline và rate limit.
5. Đo query p95/p99 theo radius, density, complexity.
6. Ghi log lỗi GeoJSON an toàn, có IDs để tra cứu.
7. Theo dõi tỷ lệ điểm thiếu vị trí, lỗi import và outliers.
8. Có quy trình cập nhật geofence/biên giới và kiểm thử sát ranh.

## 24. Bài tập thực hành

### Bài 1 — Phân biệt longitude và latitude

Cho cặp dữ liệu nguồn **latitude=10.776, longitude=106.700**. Hãy viết GeoJSON Point đúng. Giải thích vì sao [10.776,106.700] sai và vì sao một cặp đảo trục khác có thể vẫn qua kiểm tra range.

### Bài 2 — Validate kiểu tọa độ

Viết một hàm từ chối:

~~~javascript
[106.700, 10.776]
["106.700", "10.776"]
[Infinity, 10.776]
[106.700]
[106.700, 120]
~~~

Trong danh sách trên, cặp nào đúng về cấu trúc/range? Khi nào cần kiểm tra thêm business bounds?

### Bài 3 — Null và 0,0

So sánh missing location, location:null và GeoJSON Point [0,0]. Một API nên biểu diễn “chưa có vị trí” theo cách nào để không làm sai bản đồ?

### Bài 4 — CRS

Một hệ thống gửi tọa độ Web Mercator, nhưng MongoDB collection dùng 2dsphere. Vì sao không thể lưu trực tiếp x/y vào GeoJSON lon/lat? Cần làm gì trước khi tạo index?

### Bài 5 — Ring Polygon

Viết một Polygon hình chữ nhật có bốn đỉnh khác nhau và vòng đóng hợp lệ. Giải thích vì sao ring cần ít nhất bốn positions.

### Bài 6 — Polygon tự cắt

Cho vòng hình nơ ở mục 6.3. Hàm kiểm tra đóng vòng có phát hiện lỗi không? Vì sao cần kiểm tra topology bên cạnh kiểm tra cấu trúc?

### Bài 7 — Hole

Một Polygon có hole nằm hoàn toàn bên ngoài vòng ngoài. Nêu nguyên nhân không hợp lệ và cách xử lý trong pipeline nhập liệu.

### Bài 8 — Antimeridian

Một vùng nhỏ nằm giữa 179°E và -179°W. Vì sao filter longitude đơn giản từ -179 đến 179 không đúng ý định? Hãy mô tả cách cần tới xử lý spherical geography.

### Bài 9 — Kiểu index

So sánh **2d** và **2dsphere** cho ứng dụng tìm căn hộ ở các thành phố khác nhau. Giải thích vai trò spherical geometry và đơn vị khoảng cách.

### Bài 10 — Tạo lab

Chạy script seed mục 10. Xác nhận 8 Point, getIndexes và một truy vấn read lại tất cả tọa độ.

### Bài 11 — $near

Tìm địa điểm tenant t001 trong 3.000 mét tính từ [106.700,10.776]. Dự đoán ba Point gần nhất trong lab và vì sao p06 không xuất hiện.

### Bài 12 — $geoWithin

Dùng Polygon sampleArea ở mục 12. Lấy các địa điểm thuộc tenant t001 trong vùng. Dự đoán bốn _id và giải thích tại sao $geoWithin không tự sort theo khoảng cách.

### Bài 13 — $geoIntersects

Tạo một geofence Polygon trên collection lab riêng, lập 2dsphere index cho boundary. Viết query tìm vùng có giao với một Point. So sánh câu hỏi này với “những Point nằm trong một Polygon”.

### Bài 14 — $geoNear

Viết aggregation trả name và distanceMeters, lọc tenant t001 và maxDistance 3000. Vì sao $geoNear phải đứng đầu pipeline, và key có vai trò gì khi có nhiều geospatial fields?

### Bài 15 — Sparse index

Một collection có 100 document; 20 document thiếu location, 10 document location:null, còn lại có Point hợp lệ. Vì sao geospatial index không mặc nhiên tham chiếu cả 100 document? Điều gì khác nếu 5 Point có latitude ngoài range?

### Bài 16 — Index build lỗi

Collection legacy chứa một Polygon chưa khép kín và một Point hợp lệ. Khi tạo 2dsphere index báo lỗi, bạn cần làm gì? Đề xuất quy trình scan, quarantine, repair và build lại, không drop toàn collection.

### Bài 17 — Compound geospatial index

API nhận tenantId và vị trí tâm, luôn tìm trong bán kính 5 km. So sánh index **{location:"2dsphere"}** và **{tenantId:1,location:"2dsphere"}**. Cách đo hiệu quả trên dataset thực là gì?

### Bài 18 — Unique business key

Hai căn hộ ở cùng một tòa nhà có chung tọa độ. Nếu nghiệp vụ chỉ yêu cầu listingId duy nhất trong tenant, bạn sẽ dùng index nào? Vì sao không dùng 2dsphere như unique index?

### Bài 19 — Sharding

Một sharded collection có 2dsphere index trên location và shard key theo tenantId. Query chỉ có $near nhưng không có tenantId có thể phải tiếp xúc nhiều shard như thế nào? Vì sao không thể dùng 2dsphere index thay shard key index?

### Bài 20 — Read query explain

Chạy explain("executionStats") cho $near và $geoWithin ở lab. Ghi những trường/stages thể hiện geospatial index, số keys/documents examined và nReturned. Vì sao một lần chạy trên tám document không thể chứng minh production latency?

### Bài 21 — Hạn chế số vertices

API nhận MultiPolygon có 50.000 đỉnh. Bạn cần kiểm tra điều gì trước khi cho query? Phân tích giới hạn BSON, index cost, topology và việc simplify theo mức sai số nghiệp vụ.

### Bài 22 — Data quality

Một thiết bị cố định ở TP.HCM bỗng báo Point hợp lệ ở châu Âu. Index có phát hiện dữ liệu sai không? Đề xuất kiểm tra nguồn/CRS, geofence, tốc độ di chuyển và retention lỗi.

### Bài 23 — Đơn vị đo

So sánh **$near với GeoJSON $maxDistance: 3000** và **$centerSphere với radius radians**. Vì sao không được dùng số 3 trực tiếp ở cả hai để biểu diễn 3 km?

### Bài 24 — Validation nhiều lớp

Thiết kế hợp đồng API nhận GeoJSON Point cho tin đăng: kiểu Number, lon/lat bounds, tenant, required/optional location, schema validator, 2dsphere index và quarantine. Phân biệt lỗi nên trả về client với lỗi cần điều tra vận hành.

### Bài 25 — Chuyển đổi từ lat/lng cũ

Collection cũ lưu lat/lng ở hai field riêng và đôi khi là String. Hãy mô tả pipeline chuyển sang location GeoJSON có checkpoint, chuyển đổi CRS/kiểu đúng cách, phát hiện lỗi và tạo index an toàn.

### Bài 26 — Query theo danh sách địa điểm có và không có vị trí

UI cần hiển thị cả tin chưa geocode và các tin trong bán kính 3 km. Vì sao không nên cố dùng duy nhất một $near query để lấy cả hai nhóm? Hãy thiết kế hai bước truy vấn hoặc read model rõ ràng.

### Bài 27 — Ranh giới pháp lý

Một điểm nằm sát ranh giới giao hàng. Polygon được vẽ sơ sài trên bản đồ và có sai số GPS. Bạn cần quy tắc nào trước khi quyết định phí/khả năng giao hàng? Vì sao hình học hợp lệ không đồng nghĩa dữ liệu đủ chính xác về pháp lý?

### Bài 28 — Đối soát sau migration

Sau khi backfill một triệu GeoJSON Points và tạo geospatial index, hãy đề xuất báo cáo: tổng document, missing/null, valid/invalid, tỷ lệ outlier, số lỗi index build, phân bố theo thành phố, sample queries và performance p95.

## 25. Tài liệu tham khảo chính thức

- MongoDB Manual — [Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/).
- MongoDB Manual — [2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/).
- MongoDB Manual — [2d Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2d/).
- MongoDB Manual — [GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/).
- MongoDB Manual — [$near](https://www.mongodb.com/docs/manual/reference/operator/query/near/).
- MongoDB Manual — [$geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/).
- MongoDB Manual — [$geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/).
- MongoDB Manual — [$geoNear](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/).
- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).
- MongoDB Manual — [$jsonSchema](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/).
- MongoDB Manual — [Geospatial Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/restrictions/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- GeoJSON — [RFC 7946](https://www.rfc-editor.org/rfc/rfc7946).

**Điều cần nhớ:** **GeoJSON Point dùng [longitude,latitude] theo WGS84**, với giá trị số hữu hạn và phạm vi địa lý hợp lệ. **Polygon còn phải hợp lệ về ring và topology**, không chỉ có đúng type và số đỉnh. **2dsphere index** giúp tìm kiếm trên bề mặt cầu nhưng **không sửa CRS, không phát hiện mọi điểm sai nghiệp vụ, không thay unique index hoặc shard key**, và có thể từ chối index build khi dữ liệu GeoJSON hiện có không hợp lệ. Muốn hệ thống tin cậy, hãy **kiểm tra đầu vào theo nhiều lớp, quarantine geometry lỗi, dùng $near/$geoWithin/$geoIntersects đúng semantics, đo explain và giới hạn độ phức tạp truy vấn**. Một geospatial query nhanh chỉ có ý nghĩa khi **tọa độ đúng, hình học đúng và người dùng được phép xem kết quả**.
