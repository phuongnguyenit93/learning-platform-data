# Point, LineString, Polygon và các hình học được hỗ trợ trong MongoDB

## 1. Mở đầu: một vị trí, một tuyến đường và một vùng có gì khác nhau?

Hãy hình dung một ứng dụng vận chuyển muốn lưu:

- Vị trí hiện tại của tài xế.
- Một tuyến đường đã di chuyển qua nhiều tọa độ.
- Phạm vi giao hàng của một kho.
- Nhiều điểm nhận hàng thuộc cùng một đối tác.
- Hai tuyến đường không nối nhau.
- Một khu vực phục vụ gồm nhiều vùng tách biệt.
- Một đối tượng địa lý phức hợp vừa có trạm, vừa có tuyến và vùng.

Nếu chỉ lưu hai số `latitude` và `longitude` cho mọi thứ, ta không thể mô tả đầy đủ những hình học trên. MongoDB hỗ trợ **GeoJSON**, một cách biểu diễn hình học địa lý bằng document JSON/BSON. Những kiểu quan trọng gồm **Point**, **LineString**, **Polygon** và các biến thể **MultiPoint**, **MultiLineString**, **MultiPolygon**, **GeometryCollection**.

Bài học tập trung vào **hình học và cấu trúc dữ liệu**, sau đó liên hệ với các truy vấn địa lý của MongoDB để hiểu vì sao chọn đúng hình lại quan trọng.

### 1.1. Những câu hỏi cần trả lời

1. `Point` khác `LineString` và `Polygon` ở mức cấu trúc như thế nào?
2. Tại sao `coordinates: [106.7, 10.8]` **không** phải `[latitude, longitude]`?
3. Vì sao một polygon phải có **vòng khép kín**, còn một LineString thông thường không cần khép kín?
4. Một polygon có **lỗ** được biểu diễn bằng những mảng lồng nhau ra sao?
5. Khi nào dùng `MultiPolygon` thay vì một `Polygon`?
6. `GeometryCollection` khác việc có nhiều document địa lý ở điểm nào?
7. Những kiểu nào được MongoDB index/truy vấn bằng **`2dsphere`**?
8. Làm thế nào tránh lỗi polygon tự cắt, đảo thứ tự tọa độ, sai CRS hoặc hiểu sai địa hình hình cầu?

### 1.2. Bản đồ tư duy

```text
                           GEOJSON GEOMETRY
                                  |
          +-----------------------+----------------------+
          |                       |                      |
       Điểm đơn               Đường/ranh             Diện tích
          |                       |                      |
        Point                 LineString               Polygon
          |                       |                      |
      MultiPoint             MultiLineString          MultiPolygon
          \                       |                      /
           \______________________|_____________________/
                                  |
                         GeometryCollection
                       (trộn nhiều hình học)
```

Hình học GeoJSON không chỉ là để hiển thị trên bản đồ. Khi được biểu diễn đúng, MongoDB có thể dùng chúng để **tìm nơi gần nhất**, **kiểm tra vị trí nằm trong vùng** và **xác định các đối tượng giao nhau**.

## 2. Khung chung của một GeoJSON geometry

### 2.1. Hai trường cốt lõi

Với sáu kiểu geometry thông thường, dạng cơ bản là:

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.80]
}
```

Trong đó:

- `type` là **chuỗi tên kiểu hình học**, có phân biệt kiểu và cách viết hoa, như `"Point"`, `"LineString"`.
- `coordinates` là **tọa độ với độ sâu mảng khác nhau tùy kiểu**.

Riêng `GeometryCollection` dùng **`geometries`** để chứa danh sách những geometry con, không dùng một mảng `coordinates` chung.

### 2.2. Geometry thường nằm bên trong document nghiệp vụ

Ví dụ địa điểm:

```javascript
{
  _id: "hub-001",
  name: "Kho giao nhận thử nghiệm",
  category: "warehouse",
  location: {
    type: "Point",
    coordinates: [106.70, 10.80]
  }
}
```

`location` là **một trường geometry**. Các trường như `name`, `category`, `capacity` vẫn thuộc document nghiệp vụ bình thường.

MongoDB không bắt buộc toàn bộ document phải có cấu trúc GeoJSON ở top-level. Ta có thể lưu nhiều trường địa lý trong một document, chẳng hạn `pickupLocation` là Point và `deliveryArea` là Polygon, sau đó tạo index cho đường dẫn trường cần truy vấn.

### 2.3. GeoJSON geometry khác GeoJSON Feature

Trong hệ sinh thái GeoJSON rộng hơn có các đối tượng `Feature` và `FeatureCollection`:

```json
{
  "type": "Feature",
  "properties": {
    "name": "Kho A"
  },
  "geometry": {
    "type": "Point",
    "coordinates": [106.70, 10.80]
  }
}
```

Đây là cách gói **geometry + thuộc tính** theo chuẩn GeoJSON. Tuy nhiên, khi dùng **geospatial index** của MongoDB, nên index **trường geometry**, ví dụ `geometry`, **không** index nguyên Feature ở một field mà mong `2dsphere` tự hiểu các lớp bọc tùy ý.

Ví dụ:

```javascript
db.geoFeatures292.createIndex({
  "feature.geometry": "2dsphere"
});
```

Nếu lưu Feature ở `feature`, đường dẫn `feature.geometry` mới là nơi chứa geometry với `type: "Point"` hoặc kiểu khác.

## 3. Nguyên tắc tọa độ: kinh độ trước, vĩ độ sau

### 3.1. Cấu trúc `[longitude, latitude]`

Với GeoJSON trong MongoDB, một position có dạng:

```text
[ longitude, latitude ]
   kinh độ    vĩ độ
      x         y
```

Ví dụ:

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.80]
}
```

Trong ví dụ này:

- `106.70` là **kinh độ**, vị trí theo hướng đông/tây.
- `10.80` là **vĩ độ**, vị trí theo hướng bắc/nam.

Không đổi thành:

```javascript
{
  type: "Point",
  coordinates: [10.80, 106.70] // SAI: vĩ độ = 106.70, ngoài phạm vi.
}
```

### 3.2. Phạm vi giá trị

| Thành phần | Phạm vi hợp lệ thông thường | Ý nghĩa |
|---|---:|---|
| Longitude | -180 đến 180 độ | Tây ↔ Đông |
| Latitude | -90 đến 90 độ | Nam ↔ Bắc |

Các giá trị là **số**, không phải chuỗi tùy ý:

```javascript
// Đúng.
coordinates: [106.70, 10.80]

// Sai kiểu dữ liệu để làm geometry chuẩn.
coordinates: ["106.70", "10.80"]
```

### 3.3. Vì sao dễ bị đảo?

Một số API bản đồ hoặc giao diện người dùng thường trình bày tọa độ theo thứ tự **latitude trước, longitude sau**, ví dụ:

```text
lat = 10.80
lng = 106.70
```

Khi đưa vào GeoJSON, phải chuyển rõ ràng:

```javascript
const lat = 10.80;
const lng = 106.70;

const geometry = {
  type: "Point",
  coordinates: [lng, lat]
};
```

Nếu dữ liệu nằm ở một khu vực mà cả hai số khi đảo đều trong phạm vi hợp lệ, MongoDB **có thể không báo lỗi**, nhưng điểm lại nằm ở nơi khác trên Trái Đất. Do đó **kiểm tra phạm vi chưa đủ**; cần kiểm tra thứ tự từ nguồn và trực quan hóa trên bản đồ khi có thể.

### 3.4. Hệ quy chiếu WGS84

MongoDB sử dụng mô hình cầu với hệ quy chiếu địa lý **WGS84 / EPSG:4326** cho các truy vấn GeoJSON thông thường.

Các cặp số `[x, y]` trong một hệ tọa độ phẳng đo bằng mét (ví dụ dữ liệu GIS dùng một hệ chiếu địa phương) **không được đổi tên thành GeoJSON kinh độ/vĩ độ rồi đưa thẳng vào `2dsphere`**.

Nếu nguồn GIS dùng hệ quy chiếu khác:

1. Xác định **CRS đầu vào**.
2. Chuyển đổi tọa độ bằng thư viện GIS phù hợp sang longitude/latitude WGS84.
3. Kiểm tra thứ tự trục.
4. Ghi geometry sau chuyển đổi vào MongoDB.

### 3.5. Thành phần độ cao thứ ba

Trong chuẩn GeoJSON, position có thể mang phần tử thứ ba thể hiện độ cao:

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.80, 15.5]
}
```

Nhưng truy vấn địa lý `2dsphere` chủ yếu xét **hai chiều trên mặt cầu**, không nên mong MongoDB tự tính **khoảng cách 3D theo độ cao** hoặc kiểm tra hai vật thể ở hai tầng cao.

Nếu ứng dụng cần chiều cao chính xác, có thể lưu riêng:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.70, 10.80]
  },
  altitudeMeters: 15.5
}
```

rồi thiết kế logic ba chiều trong ứng dụng hoặc công cụ GIS chuyên dụng. Phải xác định rõ đơn vị và chuẩn cao độ, không dùng `15.5` mà thiếu ngữ nghĩa.

## 4. Bảy kiểu hình học GeoJSON mà MongoDB hỗ trợ

| Kiểu | Cấu trúc chính | Ý nghĩa | Ví dụ ứng dụng |
|---|---|---|---|
| `Point` | Một position | Một vị trí | Kho, cửa hàng, xe |
| `LineString` | Mảng các position | Một đường liên tục theo các đoạn | Tuyến đi, sông, ranh tuyến |
| `Polygon` | Mảng các vòng tọa độ | Một vùng, có thể có lỗ | Vùng giao hàng, công viên |
| `MultiPoint` | Mảng các position | Nhiều điểm thuộc một hình học | Tập trạm quan trắc |
| `MultiLineString` | Mảng các LineString | Nhiều đường tách biệt | Nhiều đoạn tuyến |
| `MultiPolygon` | Mảng các Polygon | Nhiều vùng tách biệt | Vùng phục vụ có nhiều phần |
| `GeometryCollection` | Mảng `geometries` | Trộn nhiều loại hình học | Một công trình có điểm, tuyến, vùng |

Các kiểu Multi* và GeometryCollection là những hình học GeoJSON được MongoDB hỗ trợ trong bối cảnh **`2dsphere`**. Điều đó **không có nghĩa mọi truy vấn địa lý nhận mọi kiểu hình làm tham số**. Ví dụ, truy vấn khoảng cách `$near` cần một **điểm làm tâm**, còn `$geoWithin` với `$geometry` nhận vùng như Polygon/MultiPolygon.

Quy tắc rất dễ nhớ:

```text
Point       -> [position]
LineString  -> [position, position, ...]
Polygon     -> [ring, ring, ...]
MultiPoint  -> [position, position, ...]
MultiLine   -> [line, line, ...]
MultiPoly   -> [polygon, polygon, ...]
Collection  -> geometries: [geometry, geometry, ...]
```

Chú ý dòng đầu chỉ là **mô hình khái niệm**. Giá trị `coordinates` của `Point` chính là một position `[lon, lat]`, không phải `[[lon, lat]]`.

## 5. Point: một vị trí cụ thể

### 5.1. Cú pháp

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.80]
}
```

`Point` chỉ có **một cặp tọa độ**, không phải nhiều cặp:

```javascript
// Không đúng cấu trúc Point.
{
  type: "Point",
  coordinates: [
    [106.70, 10.80],
    [106.72, 10.82]
  ]
}
```

Muốn lưu nhiều điểm trong một geometry, dùng **MultiPoint**; muốn lưu hành trình có thứ tự đi qua các điểm, dùng **LineString**.

### 5.2. Khi nào dùng Point?

- Vị trí một cửa hàng.
- Điểm giao/nhận hàng.
- Vị trí hiện tại của thiết bị.
- Tọa độ một trạm đo.
- Điểm xuất phát cho phép tìm địa điểm gần nhất.

### 5.3. Document MongoDB

```javascript
db.getSiblingDB("geo_training_292").sites292.insertOne({
  _id: "site-001",
  name: "Điểm tập kết A",
  active: true,
  location: {
    type: "Point",
    coordinates: [106.70, 10.80]
  }
});
```

### 5.4. Điểm không mô tả diện tích

Nếu một kho chiếm một vùng rộng, lưu một `Point` chỉ là **điểm đại diện** cho kho. Nó không mô tả ranh giới thật của kho.

Hai câu hỏi khác nhau:

```text
"Kho nằm ở đâu?"              -> Point
"Ranh đất của kho là gì?"      -> Polygon
```

Không nên dùng Point ở tâm vùng rồi giả định MongoDB biết bán kính hoặc biên của vùng đó. Nếu nghiệp vụ cần “trong bán kính 5 km”, hãy dùng truy vấn khoảng cách hoặc mô hình vùng riêng.

## 6. LineString: một tuyến nối nhiều điểm

### 6.1. Cú pháp

```javascript
{
  type: "LineString",
  coordinates: [
    [106.68, 10.78],
    [106.72, 10.80],
    [106.77, 10.83],
    [106.82, 10.86]
  ]
}
```

`coordinates` là một **mảng position**, cần ít nhất **hai position** để tạo một đường hợp lệ.

```text
 A ------- B ------ C ------ D
 106.68    106.72   106.77   106.82  (minh họa)
```

### 6.2. Điều gì được thể hiện?

- Danh sách các đỉnh của đường.
- Thứ tự nối đỉnh A → B → C → D.
- Các đoạn địa lý nối các cặp đỉnh liên tiếp theo cách MongoDB diễn giải trên mặt cầu.

Một LineString **không tự hàm ý** tốc độ xe, chiều đường, thời gian đến, đường được phép đi hoặc thứ tự tối ưu về giao thông.

### 6.3. LineString khác một mảng Point

Hai dữ liệu:

```javascript
// Có sự liên kết liên tiếp giữa các điểm.
{
  type: "LineString",
  coordinates: [
    [106.68, 10.78],
    [106.72, 10.80],
    [106.77, 10.83]
  ]
}

// Chỉ là nhiều vị trí, không xác định đoạn nối.
{
  type: "MultiPoint",
  coordinates: [
    [106.68, 10.78],
    [106.72, 10.80],
    [106.77, 10.83]
  ]
}
```

**LineString nối các vị trí theo thứ tự**; MultiPoint thể hiện một tập điểm. Dùng nhầm MultiPoint cho tuyến đường có thể khiến truy vấn giao cắt/hiển thị không mang ý nghĩa bạn mong đợi.

### 6.4. Một đường không cần khép kín

```javascript
{
  type: "LineString",
  coordinates: [
    [106.68, 10.78],
    [106.75, 10.80]
  ]
}
```

LineString như trên hợp lệ về số đỉnh cơ bản. Khác với một ring của Polygon, điểm cuối **không cần trùng** điểm đầu.

### 6.5. LineString có thể dùng làm ranh giới không?

Một LineString có thể biểu diễn **đường ranh** nhưng **không tự biến thành vùng có diện tích**.

Nếu ứng dụng cần truy vấn “điểm nào nằm trong khu giao hàng”, phải lưu **Polygon** hoặc **MultiPolygon** (cùng các ràng buộc tương ứng). Không dùng `$geoWithin` với một đường mở rồi mong nó tự tạo vùng kín.

### 6.6. Lưu ý đường trên mặt cầu

Các đoạn nối trên GeoJSON được MongoDB xem xét trong bối cảnh địa lý cầu; chúng **không phải** những đoạn Euclid trên một bản đồ phẳng bất kỳ. Với các đường dài, đặc biệt qua kinh tuyến đổi ngày hoặc gần cực, hình hiển thị và phép giao cắt có thể khác với việc vẽ đường thẳng trên màn hình theo một phép chiếu bản đồ.

## 7. Polygon: vùng được giới hạn bởi các vòng

### 7.1. Polygon không chỉ là một mảng các điểm

Một GeoJSON Polygon có:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.65, 10.75],
      [106.85, 10.75],
      [106.85, 10.90],
      [106.65, 10.90],
      [106.65, 10.75]
    ]
  ]
}
```

Độ lồng mảng ở đây là:

```text
Polygon.coordinates
  |
  +-- outer ring
        |
        +-- position [lon, lat]
        +-- position [lon, lat]
        +-- position [lon, lat]
        +-- position [lon, lat]
        +-- position [lon, lat] = vị trí đầu
```

Tại sao có **hai dấu `[`** sau `coordinates`? Dấu `[` bên ngoài chứa danh sách ring, dấu `[` tiếp theo chứa các position của ring đầu tiên.

### 7.2. LinearRing: vòng khép kín

Một **LinearRing** là một LineString khép kín dùng làm biên vùng:

- Có ít nhất **bốn position** tính cả phần tử lặp để khép kín.
- Position đầu và cuối **giống nhau**.
- Cần đủ đỉnh phân biệt để tạo một vùng có ý nghĩa.
- Không được có tự cắt gây hình học không hợp lệ theo các quy tắc liên quan.

Ví dụ tam giác:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.68, 10.78],
      [106.78, 10.78],
      [106.74, 10.86],
      [106.68, 10.78]
    ]
  ]
}
```

**Ba đỉnh khác nhau + lặp lại đỉnh đầu = bốn position.**

### 7.3. Sơ đồ đơn giản

```text
             D ----------------- C
             |                   |
             |      VÙNG         |
             |                   |
             A ----------------- B

Ring: [A, B, C, D, A]
```

Sơ đồ chỉ minh họa cách kết nối đỉnh; với khoảng cách lớn trên địa cầu, cần xét các cung địa lý theo bề mặt cầu.

### 7.4. Những lỗi cấu trúc phổ biến

**Lỗi 1 — quên lặp đỉnh đầu:**

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.65, 10.75],
      [106.85, 10.75],
      [106.85, 10.90],
      [106.65, 10.90]
      // Thiếu [106.65, 10.75] cuối.
    ]
  ]
}
```

**Lỗi 2 — thiếu lớp ring:**

```javascript
{
  type: "Polygon",
  coordinates: [
    [106.65, 10.75],
    [106.85, 10.75],
    [106.85, 10.90],
    [106.65, 10.75]
  ]
}
```

Mẫu trên trông giống `coordinates` của một LineString khép kín, **không đúng** cấu trúc Polygon có danh sách ring.

### 7.5. Polygon không tự tính đường đi bên trong

Biết một địa điểm nằm trong polygon giao hàng **không** có nghĩa có tuyến đường xe chạy được tới đó. Polygon kiểm tra **quan hệ không gian**, còn shortest path, mạng đường và thời gian vận chuyển cần dữ liệu/thuật toán khác.

## 8. Polygon có lỗ: outer ring và inner ring

### 8.1. Vì sao vùng có lỗ?

Một khu vực giao hàng có thể loại trừ:

- Một khu vực hạn chế.
- Một vùng không có dịch vụ.
- Một hồ nước hoặc vùng địa hình đặc biệt.
- Một vùng không thuộc quyền quản lý dù nằm bên trong biên ngoài.

Ta có thể dùng **Polygon với nhiều ring**.

### 8.2. Cấu trúc

```javascript
const deliveryArea292 = {
  type: "Polygon",
  coordinates: [
    // Ring 0: đường biên ngoài.
    [
      [106.65, 10.75],
      [106.85, 10.75],
      [106.85, 10.90],
      [106.65, 10.90],
      [106.65, 10.75]
    ],

    // Ring 1: lỗ nằm hoàn toàn bên trong.
    [
      [106.70, 10.78],
      [106.70, 10.82],
      [106.75, 10.82],
      [106.75, 10.78],
      [106.70, 10.78]
    ]
  ]
};
```

Ring **đầu tiên** là **outer ring**. Những ring tiếp theo biểu diễn **holes** ở bên trong.

### 8.3. Nhìn bằng sơ đồ

```text
        +-----------------------------------+
        |                                   |
        |     Vùng được phục vụ             |
        |                                   |
        |        +------------+             |
        |        |    HOLE    |             |
        |        | không tính |             |
        |        +------------+             |
        |                                   |
        +-----------------------------------+
```

Ví dụ:

- `[106.68, 10.78]` nằm trong biên ngoài và ngoài lỗ.
- `[106.72, 10.80]` nằm trong lỗ.
- `[106.90, 10.80]` nằm ngoài biên ngoài.

Các vị trí này được chọn để cách biên rõ ràng; những trường hợp **nằm chính xác trên đường biên** cần xem định nghĩa toán tử và xử lý sai số.

### 8.4. Quy tắc topology của hole

Một hole hợp lệ:

- Phải nằm **bên trong** outer ring.
- Không được giao nhau hoặc chồng lên hole khác.
- Không được chia sẻ cạnh với hole khác.
- Không được làm outer ring tự cắt.
- Phải khép kín như mọi ring của Polygon.

Nếu một inner ring bị đặt ra ngoài outer ring, hình học có thể bị từ chối hoặc không phản ánh vùng nghiệp vụ định nghĩa. Không xem “mảng đúng số tầng” là đã đủ để chứng minh polygon hợp lệ.

### 8.5. Hướng đi của vòng

Chuẩn GeoJSON hiện đại mô tả **right-hand rule**: outer ring thường được định hướng ngược chiều kim đồng hồ khi biểu diễn trên mặt phẳng kinh/vĩ độ, còn hole theo chiều kim đồng hồ.

MongoDB có những quy tắc hình học cầu và cách diễn giải riêng, nhất là với **đa giác rất lớn**. Không tùy tiện đảo chiều ring để “chữa lỗi” mà không biết polygon đại diện vùng nào trên Trái Đất; cần kiểm tra theo chuẩn dữ liệu và quy tắc MongoDB cụ thể.

### 8.6. Hole không tạo thêm một Polygon độc lập

Đây là khác biệt:

```text
Polygon có hai ring:
  outer region - inner hole

MultiPolygon có hai polygon:
  region A + region B
```

Nếu muốn **hai vùng cùng được phục vụ**, hãy dùng **MultiPolygon**, không đưa vùng thứ hai vào vị trí inner ring và vô tình tạo một **vùng bị loại trừ**.

## 9. MultiPoint: nhiều vị trí trong một geometry

### 9.1. Cấu trúc

```javascript
{
  type: "MultiPoint",
  coordinates: [
    [106.67, 10.77],
    [106.71, 10.79],
    [106.78, 10.84]
  ]
}
```

Đây là một geometry chứa **nhiều Point**, không có ý nghĩa nối thành tuyến.

### 9.2. Khi nào dùng?

- Một nhóm điểm đo trong cùng đối tượng GIS.
- Những vị trí quan trắc thuộc cùng một chiến dịch.
- Các điểm tham chiếu của một đối tượng nhiều vị trí.

### 9.3. Khi nào không dùng?

Nếu ba trạm có tên, giờ mở cửa, trạng thái và vị trí cập nhật độc lập, thường hợp lý hơn khi tạo **ba document Point riêng**:

```javascript
{ _id: "station-A", name: "A", location: { type: "Point", coordinates: [106.67, 10.77] } }
{ _id: "station-B", name: "B", location: { type: "Point", coordinates: [106.71, 10.79] } }
{ _id: "station-C", name: "C", location: { type: "Point", coordinates: [106.78, 10.84] } }
```

**MultiPoint** phù hợp khi các vị trí là thành phần của **một thực thể hình học**. Nhiều document Point phù hợp khi mỗi điểm là **một thực thể nghiệp vụ** cần CRUD và index độc lập.

## 10. MultiLineString: nhiều tuyến không cần nối liền

### 10.1. Cú pháp

```javascript
{
  type: "MultiLineString",
  coordinates: [
    [
      [106.65, 10.76],
      [106.69, 10.79],
      [106.73, 10.82]
    ],
    [
      [106.80, 10.84],
      [106.83, 10.88]
    ]
  ]
}
```

Lớp lồng:

```text
MultiLineString.coordinates
  |
  +-- LineString 1
  |     +-- position A
  |     +-- position B
  |     +-- position C
  |
  +-- LineString 2
        +-- position D
        +-- position E
```

### 10.2. Khi nào dùng?

- Nhiều đoạn đường của cùng một tuyến nhưng bị tách.
- Một dòng sông được biểu diễn bằng nhiều nhánh.
- Hệ thống tuyến cáp có nhiều đoạn.

### 10.3. MultiLineString khác LineString

LineString duy nhất:

```text
A --- B --- C --- D --- E
```

MultiLineString gồm hai phần:

```text
A --- B --- C            D --- E
```

Không tự vẽ thêm đoạn **C → D** khi geometry là MultiLineString hai thành phần. Nếu nối hai phần thành một LineString, bạn đã **thay đổi ý nghĩa không gian**.

## 11. MultiPolygon: nhiều vùng tách biệt

### 11.1. Cú pháp và độ lồng mảng

```javascript
{
  type: "MultiPolygon",
  coordinates: [
    // Polygon A -> danh sách ring của A.
    [
      [
        [106.60, 10.70],
        [106.65, 10.70],
        [106.65, 10.74],
        [106.60, 10.74],
        [106.60, 10.70]
      ]
    ],

    // Polygon B -> danh sách ring của B.
    [
      [
        [106.80, 10.85],
        [106.85, 10.85],
        [106.85, 10.89],
        [106.80, 10.89],
        [106.80, 10.85]
      ]
    ]
  ]
}
```

Độ lồng cần phân biệt:

```text
MultiPolygon
  |
  +-- Polygon A
  |     +-- outer ring
  |           +-- position
  |           +-- position
  |
  +-- Polygon B
        +-- outer ring
              +-- position
              +-- position
```

Mỗi Polygon con **tự có danh sách ring**, và có thể tự có hole.

### 11.2. Use case

- Một công ty có hai vùng giao hàng không liền kề.
- Một khu hành chính có những phần lãnh thổ tách rời.
- Một vùng bảo tồn gồm nhiều khu vực.

### 11.3. Đừng nhầm MultiPolygon với Polygon có nhiều ring

```text
Polygon:
  coordinates: [outerRing, holeRing]
  => một vùng có một lỗ.

MultiPolygon:
  coordinates: [
    [outerRingA],
    [outerRingB]
  ]
  => hai vùng riêng.
```

Đây là một trong những nhầm lẫn gây sai truy vấn địa lý nghiêm trọng nhất khi nhập dữ liệu GIS.

### 11.4. Kiểm tra các polygon con

Một MultiPolygon vẫn phải đáp ứng các ràng buộc geometry tương ứng. Không phải chỉ đặt hai polygon bất kỳ trong array là đã tạo một hình học hợp lệ:

- Mỗi ring con phải khép kín.
- Các phần không được có topology sai như tự cắt hoặc chồng chéo không phù hợp.
- Các hole phải ở trong polygon tương ứng.
- Phải hiểu cách MongoDB diễn giải biên trên mặt cầu.

Nếu hai polygon gần nhau nhưng thực ra chỉ là một vùng duy nhất, có thể thiết kế thành Polygon có biên tổng hợp; điều đó còn phụ thuộc yêu cầu dữ liệu và tính hợp lệ của ranh giới.

## 12. GeometryCollection: trộn các hình học

### 12.1. Đây là trường hợp đặc biệt về cấu trúc

Không dùng `coordinates` ở top-level:

```javascript
{
  type: "GeometryCollection",
  geometries: [
    {
      type: "Point",
      coordinates: [106.70, 10.80]
    },
    {
      type: "LineString",
      coordinates: [
        [106.68, 10.78],
        [106.75, 10.83]
      ]
    },
    {
      type: "Polygon",
      coordinates: [
        [
          [106.66, 10.76],
          [106.80, 10.76],
          [106.80, 10.88],
          [106.66, 10.88],
          [106.66, 10.76]
        ]
      ]
    }
  ]
}
```

### 12.2. Ý nghĩa

Một GeometryCollection chứa **nhiều geometry có thể khác type**. Nó hữu ích khi một đối tượng địa lý được mô tả bởi:

- Một vị trí trung tâm.
- Một đường kết nối.
- Một vùng chiếm dụng.

Các geometry con nằm trong mảng `geometries`, chứ không phải ba trường nghiệp vụ tự do mang tên `point`/`route`/`area`.

### 12.3. Khi nào không nên dùng?

Nếu ứng dụng cần:

- Tìm kho gần nhất bằng `$near`.
- Tìm tuyến đường cắt qua vùng.
- Tìm vùng chứa điểm.

và mỗi hình học có ý nghĩa truy vấn độc lập, việc lưu **những trường geometry riêng** thường giúp index và truy vấn rõ ràng hơn:

```javascript
{
  _id: "facility-A",
  center: {
    type: "Point",
    coordinates: [106.70, 10.80]
  },
  route: {
    type: "LineString",
    coordinates: [
      [106.68, 10.78],
      [106.75, 10.83]
    ]
  },
  serviceArea: {
    type: "Polygon",
    coordinates: [
      [
        [106.66, 10.76],
        [106.80, 10.76],
        [106.80, 10.88],
        [106.66, 10.88],
        [106.66, 10.76]
      ]
    ]
  }
}
```

Sau đó có thể tạo index chính xác trên `center`, `route` hoặc `serviceArea` theo workload.

**GeometryCollection không phải lời giải tối ưu cho mọi dữ liệu có nhiều geometry.** Nó là một kiểu hình học cụ thể, không thay thế thiết kế schema nghiệp vụ.

## 13. Tại sao cấu trúc mảng rất quan trọng?

Cùng một dãy cặp tọa độ có thể mang **ba ý nghĩa khác nhau**:

```javascript
const a = [106.70, 10.80];

const point = {
  type: "Point",
  coordinates: a
};

const line = {
  type: "LineString",
  coordinates: [
    [106.70, 10.80],
    [106.75, 10.85]
  ]
};

const polygon = {
  type: "Polygon",
  coordinates: [
    [
      [106.70, 10.80],
      [106.80, 10.80],
      [106.80, 10.88],
      [106.70, 10.80]
    ]
  ]
};
```

Những dấu `[` không chỉ là cú pháp JSON. Chúng mô tả:

- Cấp **position**.
- Cấp **đường**.
- Cấp **ring**.
- Cấp **polygon**.
- Cấp **tập các geometry**.

### 13.1. Bảng so sánh chính xác

| Type | Độ lồng dễ nhớ của `coordinates` | Mẫu ngắn |
|---|---|---|
| Point | Position | `[x, y]` |
| MultiPoint | Các position | `[[x,y],[x,y]]` |
| LineString | Các position | `[[x,y],[x,y]]` |
| MultiLineString | Các LineString | `[[[x,y],[x,y]],[[x,y],[x,y]]]` |
| Polygon | Các ring | `[[[x,y],[x,y],[x,y],[x,y]]]` |
| MultiPolygon | Các polygon | `[[[[x,y],...]],[[[x,y],...]]]` |
| GeometryCollection | Không có `coordinates` tổng | `geometries: [{type,...}, ...]` |

**MultiPoint và LineString có cùng độ lồng mảng nhưng khác `type` và ngữ nghĩa liên kết.** Polygon và MultiLineString cũng có thể trông gần giống nhau nếu chỉ nhìn độ lồng; **type quyết định cách hiểu**.

### 13.2. Các cấp mảng không tự mô tả ý nghĩa

Nếu một API chỉ trả:

```javascript
[
  [106.70, 10.80],
  [106.75, 10.85]
]
```

ta chưa biết nó là hai điểm độc lập, một tuyến đường hay dữ liệu bản đồ theo format khác. Cần **type và contract API rõ ràng** trước khi lưu MongoDB.

## 14. Polygon trên mặt cầu: geodesic, đường đổi ngày và vùng lớn

### 14.1. Bản đồ phẳng không phải Trái Đất

Trong hình vẽ 2D, hai điểm được nối bằng đoạn thẳng. Trên Trái Đất, đường nối địa lý có thể được hiểu theo **đường trắc địa (geodesic)** trên bề mặt cầu.

Với đoạn ngắn trong một thành phố, sự khác biệt có thể nhỏ. Với các đoạn rất dài, cách hiển thị trên projection bản đồ và cách MongoDB tính quan hệ địa lý có thể khác đáng kể.

### 14.2. Kinh tuyến đổi ngày

Hai kinh độ:

```text
179.9° E
-179.9° W
```

ở gần nhau qua đường đổi ngày, không phải cách nhau gần 360° trên Trái Đất.

Đừng tự sửa chúng bằng phép lấy trị tuyệt đối:

```javascript
Math.abs(179.9 - (-179.9)) // 359.8: không là khoảng cách địa lý đúng.
```

Đối với geometry cắt kinh tuyến đổi ngày, nên kiểm tra dữ liệu trên công cụ GIS hiểu WGS84 và xác nhận MongoDB diễn giải đúng vùng mong muốn.

### 14.3. Vùng lớn hơn một bán cầu

MongoDB có quy tắc đặc biệt với các polygon GeoJSON **lớn hơn một bán cầu**. Với CRS mặc định, truy vấn có thể diễn giải **vùng bù nhỏ hơn** thay vì vùng lớn mà người dùng dự định.

Đối với **single-ring Polygon** trong các toán tử được hỗ trợ như `$geoWithin` hoặc `$geoIntersects`, MongoDB có một CRS mở rộng **strict-winding** để phân biệt ý nghĩa vùng lớn:

```javascript
const largePolygonQuery = {
  type: "Polygon",
  coordinates: [
    [
      [-100,  60],
      [-100,   0],
      [-100, -60],
      [ 100, -60],
      [ 100,  60],
      [-100,  60]
    ]
  ],
  crs: {
    type: "name",
    properties: {
      name: "urn:x-mongodb:crs:strictwinding:EPSG:4326"
    }
  }
};
```

**Quan trọng:** đây không phải cách tùy tiện gán CRS khác cho mọi GeoJSON. CRS strict-winding của MongoDB có **phạm vi hỗ trợ cụ thể**, đặc biệt gắn với single-ring polygon và các toán tử tương ứng. Không tự dùng nó cho MultiPolygon/hole rồi mặc định ngữ nghĩa tương tự.

### 14.4. Polygon nhỏ vẫn cần kiểm tra

Ngay cả khi vùng chỉ vài km²:

- Ring có thể tự cắt.
- Hole có thể nằm ngoài.
- Biên có thể đi qua vị trí không hợp lệ.
- Vị trí trên biên có thể bị ảnh hưởng bởi sai số/tolerance.

Không lấy việc `insertOne()` thành công trên document không có index làm bằng chứng geometry hợp lệ về topology.

## 15. Chỉ số `2dsphere`: nền tảng truy vấn GeoJSON

### 15.1. Tạo index

Cho collection:

```javascript
{
  _id: "shop-A",
  location: {
    type: "Point",
    coordinates: [106.70, 10.80]
  }
}
```

Tạo index:

```javascript
db.shops.createIndex({
  location: "2dsphere"
});
```

`2dsphere` phục vụ các truy vấn hình học trên một mặt cầu gần giống Trái Đất, phù hợp cho dữ liệu GeoJSON/WGS84.

### 15.2. Tại sao không dùng index thường?

Một index:

```javascript
db.shops.createIndex({ "location.coordinates": 1 });
```

không có cùng năng lực với `2dsphere` để trả lời:

- Vị trí nào nằm trong một Polygon?
- Geometry nào giao nhau với tuyến đường?
- Những điểm nào ở gần vị trí hiện tại nhất?

Index thường chỉ sắp thứ tự BSON/giá trị theo cơ chế thông thường; nó không thay thế cấu trúc không gian.

### 15.3. Các kiểu GeoJSON và `2dsphere`

`2dsphere` là lựa chọn cho **Point, LineString, Polygon** và các kiểu **MultiPoint, MultiLineString, MultiPolygon, GeometryCollection** trong những điều kiện được hỗ trợ.

Khi index những geometry phức tạp, MongoDB cần tạo biểu diễn không gian nội bộ; một document có polygon rất nhiều đỉnh hoặc nhiều geometry con có thể làm chi phí index và cập nhật tăng mạnh.

### 15.4. Index không phải bộ sửa dữ liệu

Một geospatial index có thể **từ chối** xây dựng nếu một document trong field indexed chứa dữ liệu geometry sai kiểu hoặc tọa độ không hợp lệ.

Ví dụ:

```javascript
{
  location: {
    type: "Point",
    coordinates: ["abc", "def"]
  }
}
```

Đừng dựa vào MongoDB để tự sửa những chuỗi đó thành tọa độ hoặc đoán CRS. Cần validate đầu vào trước khi lưu.

### 15.5. `2dsphere` không phải shard key

Trong sharded cluster, **geospatial index không được dùng trực tiếp làm shard key**. Một collection sharded có thể có index geospatial để truy vấn, nhưng **shard key** phải được thiết kế bằng các trường và index phù hợp với quy tắc sharding.

Không chọn `{ location: "2dsphere" }` làm shard key chỉ vì các truy vấn đều theo địa lý.

## 16. `2d` và legacy coordinate pairs khác GeoJSON `2dsphere`

MongoDB hỗ trợ **legacy coordinate pairs**:

```javascript
{
  loc: [106.70, 10.80]
}
```

và những chỉ số như:

```javascript
db.legacyPlaces.createIndex({
  loc: "2d"
});
```

Nhưng cần phân biệt:

| Khía cạnh | `2d` | `2dsphere` |
|---|---|---|
| Mô hình hình học | Phẳng, phù hợp các tọa độ phẳng theo yêu cầu | Cầu, dành cho dữ liệu địa lý Trái Đất |
| Dữ liệu điển hình | Legacy coordinate pairs | GeoJSON geometry hoặc legacy coordinate pairs |
| Polygon/hình cầu | Không thay thế được GeoJSON spherical semantics | Hỗ trợ geometry GeoJSON phù hợp |
| Quan hệ gần khoảng cách | Cần hiểu đơn vị và operator | Với GeoJSON Point, khoảng cách thường tính mét |
| Dùng cho vị trí GPS | Không phải lựa chọn mặc định | Thường nên chọn `2dsphere` |

**Không chuyển legacy coordinate pair sang GeoJSON Point chỉ bằng cách thêm `type` nếu không biết các giá trị có thật là longitude/latitude WGS84 hay không.**

### 16.1. Không trộn hai biểu diễn trong cùng đường dẫn thiếu kiểm soát

Đừng lưu:

```javascript
{
  location: {
    lat: 10.80,
    lng: 106.70,
    coordinates: [106.70, 10.80],
    type: "Point"
  }
}
```

rồi để nhiều hệ thống tự chọn nguồn ưu tiên. Nếu cần hỗ trợ API cũ, nên có **một trường canonical geometry** và quy tắc chuyển đổi rõ ràng.

### 16.2. GeoJSON không tự lưu mọi thuộc tính bản đồ

GeoJSON mô tả **hình học**, không tự chứa:

- Mã EPSG khác được chuyển đổi chính xác.
- Đồ thị đường giao thông.
- Tốc độ và thời gian vận chuyển.
- Cao độ dùng để tính khoảng cách 3D.
- Lịch sử thay đổi vùng.
- Phân giải biên giới chính trị theo ngày.

Những dữ liệu này cần các trường/schema hoặc hệ thống GIS khác.

## 17. Bộ dữ liệu thực hành: điểm và vùng

Các ví dụ dùng database **`geo_training_292`**. Tọa độ trong bài chỉ là **dữ liệu giả lập để học cấu trúc**, không tuyên bố ranh giới hành chính hoặc vùng giao hàng thật ở bất kỳ thành phố nào.

### 17.1. Tạo các Point

Trong `mongosh`:

```javascript
const demo = db.getSiblingDB("geo_training_292");
const points = demo.points292;

// Chỉ dùng collection lab mới/rỗng.
if (points.countDocuments({}) !== 0) {
  throw new Error("points292 da co du lieu; dung collection lab rong");
}

points.insertMany([
  {
    _id: "P-A",
    name: "Điểm A: trong vùng",
    location: {
      type: "Point",
      coordinates: [106.68, 10.78]
    }
  },
  {
    _id: "P-B",
    name: "Điểm B: trong lỗ loại trừ",
    location: {
      type: "Point",
      coordinates: [106.72, 10.80]
    }
  },
  {
    _id: "P-C",
    name: "Điểm C: ngoài vùng",
    location: {
      type: "Point",
      coordinates: [106.90, 10.80]
    }
  },
  {
    _id: "P-D",
    name: "Điểm D: trong vùng",
    location: {
      type: "Point",
      coordinates: [106.81, 10.85]
    }
  }
]);

points.createIndex({ location: "2dsphere" });
```

### 17.2. Tạo geometry của một vùng và một lỗ

```javascript
const deliveryArea292 = {
  type: "Polygon",
  coordinates: [
    [
      [106.65, 10.75],
      [106.85, 10.75],
      [106.85, 10.90],
      [106.65, 10.90],
      [106.65, 10.75]
    ],
    [
      [106.70, 10.78],
      [106.70, 10.82],
      [106.75, 10.82],
      [106.75, 10.78],
      [106.70, 10.78]
    ]
  ]
};
```

### 17.3. Có thể lưu vùng thành document riêng

```javascript
demo.areas292.insertOne({
  _id: "ZONE-A",
  name: "Vùng phục vụ giả lập",
  geometry: deliveryArea292
});

demo.areas292.createIndex({ geometry: "2dsphere" });
```

**Chú ý:** Ví dụ `demo.areas292.insertOne()` dành cho collection rỗng. Nếu đã chạy, đừng insert cùng `_id` lần hai rồi coi duplicate key là lỗi của geospatial.

## 18. Truy vấn `$geoWithin`: nằm trọn trong một vùng

### 18.1. Bài toán

Tìm các điểm có `location` thuộc vùng giao hàng, **trừ lỗ loại trừ**.

```javascript
points.find({
  location: {
    $geoWithin: {
      $geometry: deliveryArea292
    }
  }
}, {
  _id: 1,
  name: 1
});
```

Với các điểm được chọn rõ ràng không nằm trên biên, mong đợi `P-A` và `P-D` là những điểm trong vùng. `P-B` nằm trong hole, còn `P-C` nằm ngoài outer ring.

### 18.2. Vì sao dùng `$geometry`?

`$geometry` cho MongoDB biết hình bên phải là **GeoJSON query geometry**:

```javascript
{
  $geoWithin: {
    $geometry: {
      type: "Polygon",
      coordinates: [
        [
          [106.65, 10.75],
          [106.85, 10.75],
          [106.85, 10.90],
          [106.65, 10.90],
          [106.65, 10.75]
        ]
      ]
    }
  }
}
```

Đừng nhầm tham số query geometry với một document business hoàn chỉnh có `_id`, `name`, `createdAt`.

### 18.3. `$geoWithin` không giống `$geoIntersects`

`$geoWithin` hỏi: geometry ở field của document có **nằm trọn bên trong** hình được chỉ định hay không?

`$geoIntersects` hỏi: geometry ở field của document có **giao nhau** với hình được chỉ định hay không?

Với một đường xuyên qua vùng nhưng có đoạn nằm ngoài, có thể **intersect** mà **không within**.

### 18.4. Chỉ số và kết quả

`$geoWithin` không tự trả các điểm theo khoảng cách hoặc thứ tự tên. Nếu cần thứ tự ổn định, dùng `sort()` rõ ràng.

`$geoWithin` không phải lúc nào cũng bắt buộc geospatial index để chạy, nhưng tạo `2dsphere` trên field đúng giúp tối ưu truy vấn hình cầu ở workload phù hợp.

## 19. Truy vấn `$geoIntersects`: hình học có giao nhau

### 19.1. Lưu một tuyến đường

```javascript
const shapes = demo.shapes292;

shapes.insertOne({
  _id: "ROUTE-A",
  kind: "route",
  geometry: {
    type: "LineString",
    coordinates: [
      [106.60, 10.78],
      [106.72, 10.81],
      [106.90, 10.86]
    ]
  }
});

shapes.createIndex({ geometry: "2dsphere" });
```

Đây là một LineString đi qua vùng thử nghiệm và có đỉnh ở ngoài vùng, thích hợp để minh họa **giao cắt**.

### 19.2. Tìm route giao vùng

```javascript
shapes.find({
  kind: "route",
  geometry: {
    $geoIntersects: {
      $geometry: deliveryArea292
    }
  }
});
```

Truy vấn tìm các geometry route có **giao** với polygon chỉ định.

### 19.3. Tìm các vùng giao một tuyến

Nếu database chứa nhiều vùng `geometry: Polygon` và muốn tìm vùng nào tuyến đường đi qua, có thể đảo ngược phía lưu và phía query:

```javascript
const routeGeometry292 = {
  type: "LineString",
  coordinates: [
    [106.60, 10.78],
    [106.72, 10.81],
    [106.90, 10.86]
  ]
};

demo.areas292.find({
  geometry: {
    $geoIntersects: {
      $geometry: routeGeometry292
    }
  }
});
```

### 19.4. Giao nhau không đồng nghĩa đi qua đường công cộng

Một route có thể cắt ranh giới Polygon về mặt hình học, nhưng tuyến thực tế có thể:

- Băng qua khu vực cấm.
- Đi trên cầu.
- Đi trong hầm.
- Nằm ở cao độ khác.

MongoDB đánh giá quan hệ không gian **2D trên bề mặt cầu**, không tự suy luận quyền đi lại hoặc giao thông 3D.

### 19.5. Trường hợp biên

Giao tại đúng một đỉnh/đường biên có thể có chi tiết toán học/tolerance khác với một đường xuyên rõ trong nội vùng. Nếu nghiệp vụ phân biệt **touches**, **crosses**, **overlaps** theo chuẩn GIS nâng cao, cần kiểm tra khả năng operator và có thể dùng công cụ GIS bổ sung.

## 20. Truy vấn `$near`: khoảng cách tới một Point

### 20.1. Tìm các địa điểm gần điểm gốc

```javascript
const pickupPoint292 = {
  type: "Point",
  coordinates: [106.70, 10.80]
};

points.find({
  location: {
    $near: {
      $geometry: pickupPoint292,
      $maxDistance: 15000
    }
  }
}, {
  _id: 1,
  name: 1
});
```

Với GeoJSON + `2dsphere`, khoảng cách `$maxDistance`/`$minDistance` được diễn giải theo **mét** theo ngữ nghĩa toán tử. Kết quả `$near` thông thường được sắp theo khoảng cách tới điểm chỉ định.

### 20.2. Vì sao tâm phải là Point?

`$near` trả lời “geometry nào gần **vị trí này** nhất?”. Tham số truy vấn phải là một **điểm**, không đưa cả Polygon vào `$geometry` rồi kỳ vọng hệ thống tự chọn “tâm polygon”.

Nếu cần điểm đại diện cho polygon, ứng dụng phải xác định **centroid hoặc một điểm bên trong** theo quy tắc phù hợp; centroid hình học có thể nằm ngoài polygon lõm hoặc nằm trong hole, nên không phải lúc nào cũng là vị trí nghiệp vụ tốt.

### 20.3. Index cần thiết

Các truy vấn proximity như `$near`/`$nearSphere` cần **geospatial index** phù hợp. Với dữ liệu GeoJSON địa lý, tạo:

```javascript
points.createIndex({ location: "2dsphere" });
```

Nếu collection có nhiều geospatial index, một số API như `$geoNear` cần chỉ rõ field/index bằng `key` để tránh mơ hồ.

## 21. `$geoNear` trong aggregation

### 21.1. Khi cần đưa khoảng cách vào kết quả

`$geoNear` có thể tạo trường khoảng cách và tiếp tục aggregation:

```javascript
points.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70, 10.80]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 15000
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
]);
```

### 21.2. Những chú ý

- Thường đặt `$geoNear` làm **stage đầu tiên** của pipeline theo quy tắc MongoDB.
- Cần geospatial index thích hợp.
- `distanceField` là đường dẫn field kết quả do bạn đặt, không cần tồn tại sẵn trong document nguồn.
- `near` là Point (hoặc biểu diễn tương thích được hỗ trợ), không phải một Polygon tùy ý.
- Với geometry trên mặt cầu, giữ `spherical: true` theo use case và cú pháp version.

### 21.3. `$near` khác `$geoNear`

| Nhu cầu | Công cụ thường dùng |
|---|---|
| Chỉ lọc điểm gần và nhận kết quả theo khoảng cách | `$near` trong `find()` |
| Muốn có field distance để tính tiếp bằng aggregation | `$geoNear` |
| Tìm điểm trong vùng Polygon | `$geoWithin` |
| Tìm hình giao với vùng/tuyến | `$geoIntersects` |

Không lấy `$geoNear` để thay thế bài toán network routing/travel time; khoảng cách địa lý không phải thời gian lái xe.

## 22. Chọn đúng operator cho từng geometry

### 22.1. Một bảng quyết định

| Câu hỏi nghiệp vụ | Dữ liệu lưu | Geometry của query | Operator gợi ý |
|---|---|---|---|
| Cửa hàng nào nằm trong vùng giao hàng? | `Point` | `Polygon` | `$geoWithin` |
| Các tuyến nào cắt khu vực cấm? | `LineString` | `Polygon` | `$geoIntersects` |
| Vùng nào chứa vị trí khách? | `Polygon` | `Point` | `$geoIntersects` |
| Tìm mười trạm gần nhất | `Point` | `Point` | `$near` hoặc `$geoNear` |
| Khu đất nào giao ranh vùng quy hoạch? | `Polygon`/`MultiPolygon` | `Polygon` | `$geoIntersects` |
| Một tuyến có nằm trọn vùng không? | `LineString` | `Polygon` | `$geoWithin`, khi topology phù hợp |
| Nhiều vị trí quan trắc có giao vùng? | `MultiPoint` | `Polygon` | Chọn operator theo nghĩa “có điểm giao” hay “mọi điểm nằm trong” |

### 22.2. “Một phần” và “toàn bộ” khác nhau

Với MultiPoint có hai điểm, một ở trong và một ở ngoài polygon:

```javascript
{
  type: "MultiPoint",
  coordinates: [
    [106.68, 10.78], // trong
    [106.90, 10.80]  // ngoài
  ]
}
```

- Nếu hỏi **có giao vùng hay không**, tập điểm có thể giao vùng vì có ít nhất một điểm thuộc vùng.
- Nếu hỏi **toàn bộ hình có nằm trong vùng hay không**, không thể coi toàn MultiPoint nằm trọn trong vùng.

Đây là lý do chọn `$geoIntersects` hay `$geoWithin` dựa trên **ngữ nghĩa nghiệp vụ**, không chỉ vì cả hai đều cho phép truyền Polygon làm tham số.

## 23. Kiểm tra dữ liệu GeoJSON trước khi ghi

### 23.1. Kiểm tra position

Một hàm JavaScript đơn giản:

```javascript
function isPosition(value) {
  return Array.isArray(value) &&
    (value.length === 2 || value.length === 3) &&
    value.every(v => typeof v === "number" && Number.isFinite(v)) &&
    value[0] >= -180 && value[0] <= 180 &&
    value[1] >= -90 && value[1] <= 90;
}

print(isPosition([106.70, 10.80]));       // true
print(isPosition(["106.70", "10.80"]));   // false
print(isPosition([10.80, 106.70]));       // false
print(isPosition([181, 10]));            // false
```

Đây chỉ là **kiểm tra cơ bản về kiểu và phạm vi**, không xác nhận tọa độ nằm ở nơi người dùng định, hay xử lý CRS/độ cao chính xác.

### 23.2. Kiểm tra LineString

```javascript
function isBasicLineStringCoordinates(coords) {
  return Array.isArray(coords) &&
    coords.length >= 2 &&
    coords.every(isPosition);
}

print(isBasicLineStringCoordinates([
  [106.70, 10.80],
  [106.75, 10.85]
])); // true
```

Hàm kiểm tra **số lượng và cấu trúc**, không xác định hai điểm có trùng nhau hay đường có ý nghĩa địa lý.

### 23.3. Kiểm tra ring khép kín

```javascript
function samePosition(a, b) {
  return Array.isArray(a) &&
    Array.isArray(b) &&
    a.length === b.length &&
    a.every((value, i) => value === b[i]);
}

function isBasicLinearRing(ring) {
  if (!Array.isArray(ring) || ring.length < 4) {
    return false;
  }

  if (!ring.every(isPosition)) {
    return false;
  }

  return samePosition(ring[0], ring[ring.length - 1]);
}

print(isBasicLinearRing([
  [106.65, 10.75],
  [106.85, 10.75],
  [106.85, 10.90],
  [106.65, 10.75]
])); // true về cấu trúc cơ bản
```

### 23.4. Kiểm tra Polygon cơ bản

```javascript
function isBasicPolygonCoordinates(coords) {
  return Array.isArray(coords) &&
    coords.length >= 1 &&
    coords.every(isBasicLinearRing);
}

print(isBasicPolygonCoordinates(deliveryArea292.coordinates));
// true nếu biến đã được khai báo từ ví dụ trước.
```

**Đừng hiểu `true` là polygon hợp lệ đầy đủ!** Hàm trên chưa kiểm tra:

- Self-intersection.
- Hole ở ngoài outer ring.
- Các hole chồng nhau.
- Số đỉnh phân biệt.
- Hướng vòng và cách diễn giải trên cầu.
- Ranh vượt kinh tuyến đổi ngày.
- Sai CRS hoặc sai hình học nghiệp vụ.

Để validate dữ liệu địa lý production, sử dụng công cụ GIS/geometry validation phù hợp và các kiểm tra của MongoDB index, thay vì tự viết một hàm năm dòng rồi coi đủ.

### 23.5. Vì sao phải validate trước?

Nếu một batch chứa 100.000 hình, một document sai có thể:

- Khiến thao tác index/insert thất bại.
- Tạo vùng phủ sai khiến kết quả tìm kiếm thiếu hoặc thừa.
- Làm diện tích/tính giao không như mong đợi.
- Khiến ứng dụng vẽ bản đồ hỏng hoặc tạo đường bất thường.

Việc kiểm tra hình học là **yêu cầu chất lượng dữ liệu đầu vào**, không phải việc có thể thay bằng tăng tài nguyên MongoDB.

## 24. Những nhầm lẫn phổ biến khi chuyển dữ liệu từ GIS/API

### 24.1. Hệ tọa độ phẳng bị hiểu nhầm thành lon/lat

Một file GIS có tọa độ:

```text
x = 689000
y = 1192000
```

có thể đang dùng đơn vị mét của hệ chiếu nào đó. Những giá trị này không phải kinh độ/vĩ độ hợp lệ và cần chuyển về WGS84 trước.

### 24.2. String chứa JSON không phải BSON geometry

Sai:

```javascript
{
  location: '{"type":"Point","coordinates":[106.70,10.80]}'
}
```

`location` là **String**, không phải embedded document GeoJSON. Một `2dsphere` index trên field đó không xử lý như hình học Point.

Đúng:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.70, 10.80]
  }
}
```

### 24.3. GeoJSON FeatureCollection không phải một GeometryCollection

Ví dụ FeatureCollection:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "name": "A" },
      "geometry": {
        "type": "Point",
        "coordinates": [106.70, 10.80]
      }
    }
  ]
}
```

Nó **khác**:

```javascript
{
  type: "GeometryCollection",
  geometries: [
    {
      type: "Point",
      coordinates: [106.70, 10.80]
    }
  ]
}
```

Nếu import GeoJSON từ file chứa FeatureCollection, cần tách geometry tương ứng vào field MongoDB được index, hoặc lưu cấu trúc Feature ở nơi được thiết kế rõ ràng.

### 24.4. Polygon có hole nhập thành MultiPolygon

Một file có outer ring và inner hole không nên được chuyển thành hai polygon độc lập chỉ vì “có hai dãy tọa độ”. Việc đó đảo ngược ý nghĩa **loại trừ** thành **bao gồm thêm vùng**.

### 24.5. Đường tuyến nhập thành MultiPoint

Nếu một tuyến có bốn waypoint, lưu MultiPoint làm mất ngữ nghĩa **các đoạn nối**. Truy vấn giao với polygon có thể chỉ xét các điểm, không phản ánh đường tuyến đi qua giữa hai waypoint theo cách bạn cần.

### 24.6. Ranh giới quá đơn giản

Một vùng được vẽ bằng bốn đỉnh có thể bỏ qua các khúc cong quan trọng. Nếu ứng dụng dùng cho pháp lý/an toàn, cần nguồn ranh giới có độ chính xác và phiên bản phù hợp.

Ngược lại, polygon với hàng trăm nghìn đỉnh có thể làm query/index tốn kém. Nên đánh giá độ chi tiết cần thiết theo sai số cho phép và use case.

## 25. Java Sync Driver: tạo Point và truy vấn Polygon

### 25.1. Sử dụng các lớp GeoJSON của driver

MongoDB Java Sync Driver có các lớp như `Position`, `Point`, `LineString`, `Polygon` trong package `com.mongodb.client.model.geojson`.

Ví dụ đọc/ghi Point:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.geojson.Point;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;

public class GeoPointExample {
    public static void main(String[] args) {
        try (MongoClient client =
                 MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase database =
                client.getDatabase("geo_training_292");
            MongoCollection<Document> collection =
                database.getCollection("javaPoints292");

            collection.createIndex(
                Indexes.geo2dsphere("location"));

            // Position nhận longitude trước, latitude sau.
            Point point = new Point(new Position(106.70, 10.80));

            Document doc = new Document("_id", "JAVA-P-01")
                .append("name", "Trạm Java")
                .append("location", point);

            collection.replaceOne(
                new Document("_id", "JAVA-P-01"),
                doc,
                new com.mongodb.client.model.ReplaceOptions()
                    .upsert(true));
        }
    }
}
```

### 25.2. Tạo Polygon và `geoWithin()`

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.geojson.Polygon;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;

public class PolygonQueryExample {
    public static void main(String[] args) {
        try (MongoClient client =
                 MongoClients.create("mongodb://localhost:27017")) {

            MongoCollection<Document> points =
                client.getDatabase("geo_training_292")
                      .getCollection("points292");

            Polygon area = new Polygon(Arrays.asList(
                new Position(106.65, 10.75),
                new Position(106.85, 10.75),
                new Position(106.85, 10.90),
                new Position(106.65, 10.90),
                new Position(106.65, 10.75)
            ));

            Bson filter = Filters.geoWithin("location", area);

            for (Document doc : points.find(filter)) {
                System.out.println(doc.toJson());
            }
        }
    }
}
```

**Lưu ý:** ví dụ Java Polygon thứ hai dùng **vùng ngoài không có hole**, khác `deliveryArea292` trước đó. Vì vậy điểm `P-B` nằm trong vùng ngoài và có thể được trả về trong truy vấn này; đừng dùng kết quả đó làm bằng chứng hole hoạt động sai.

### 25.3. Java driver không tự đảo thứ tự tọa độ

```java
new Position(106.70, 10.80);  // longitude, latitude
```

Nếu nhận đầu vào ở dạng:

```java
double latitude = 10.80;
double longitude = 106.70;
```

hãy chủ động tạo:

```java
Point point = new Point(new Position(longitude, latitude));
```

Driver không thể đoán rằng lập trình viên đã đảo các tham số.

### 25.4. Khi cần Polygon có hole trong Java

Driver cung cấp những API cấu trúc polygon/hole theo phiên bản. Khi use case cần phức tạp hơn một outer ring:

1. Tạo các vị trí ở vòng ngoài và vòng trong.
2. Đảm bảo closure và tính hợp lệ topology.
3. Dùng constructor/API hỗ trợ hole của phiên bản driver, hoặc tạo `BsonDocument`/`Document` GeoJSON đúng định dạng.
4. Gửi query và kiểm tra kết quả trên dữ liệu mẫu có điểm nằm trong hole.

Không lấy cấu trúc Java `List<Position>` của một ring đơn rồi dùng thay cho toàn bộ `MultiPolygon` nhiều lớp.

## 26. Hiệu năng và quyết định schema

### 26.1. Shape càng phức tạp, index có thể càng tốn

Một polygon có 5 đỉnh khác polygon có 50.000 đỉnh. Với `2dsphere`, MongoDB tạo các key/biểu diễn không gian cho geometry; những shape cực kỳ chi tiết có thể làm index lớn và thao tác ghi/cập nhật đắt hơn.

Không tự kết luận “cứ thêm đỉnh là query chính xác và nhanh hơn”. Cần cân bằng:

- Độ chính xác ranh giới.
- Tài nguyên lưu trữ.
- Chi phí xây index.
- Chi phí cập nhật geometry.
- Kích thước document và mạng.
- Kết quả query ở các trường hợp biên.

### 26.2. Khu vực ít thay đổi và vị trí cập nhật liên tục

Ví dụ:

- `deliveryArea: Polygon` cập nhật mỗi tháng.
- `driverLocation: Point` cập nhật mỗi vài giây.

Nếu đặt chung trong một document lớn và cập nhật Point liên tục, ứng dụng có thể phát sinh chi phí ghi document và index không cần thiết theo kiến trúc thực tế.

Có thể tách:

```text
deliveryZones292
  zoneId, name, geometry: Polygon

driverLocations292
  driverId, location: Point, updatedAt
```

để mỗi collection có index và vòng đời riêng.

### 26.3. Một collection trộn nhiều kiểu geometry?

MongoDB có thể lưu các GeoJSON geometry khác nhau trong cùng field `geometry` nếu dữ liệu hợp lệ:

```javascript
{ _id: "A", geometry: { type: "Point", coordinates: [106.70,10.80] } }
{ _id: "B", geometry: { type: "LineString", coordinates: [[106.70,10.80],[106.80,10.85]] } }
```

Nhưng nên tự hỏi:

- Mọi document có cùng contract truy vấn không?
- Có cần lọc `kind` trước khi chạy operator?
- Có index phù hợp với các query thường dùng không?
- Khi trả geometry về client, client có hỗ trợ mọi type không?

Trong nhiều hệ thống, tách Point/Route/Area thành collection riêng giúp code và index rõ ràng hơn.

### 26.4. Kết hợp bộ lọc nghiệp vụ với địa lý

Ví dụ tìm kho đang hoạt động trong vùng:

```javascript
db.warehouses.find({
  active: true,
  location: {
    $geoWithin: {
      $geometry: deliveryArea292
    }
  }
});
```

Có thể xem xét compound index kết hợp trường lọc và geospatial field theo query pattern:

```javascript
db.warehouses.createIndex({
  active: 1,
  location: "2dsphere"
});
```

Đây là **index ứng viên**, không phải bảo đảm optimizer sẽ chọn nhanh nhất cho mọi dữ liệu. Hãy dùng `explain("executionStats")` trên workload đại diện để kiểm chứng.

### 26.5. Không index mọi field hình học chỉ vì có thể

Mỗi index thêm:

- Tốn dung lượng.
- Tăng chi phí ghi/update.
- Cần bảo trì khi dữ liệu lớn.

Thiết kế index theo **truy vấn được dùng thực tế**, không chỉ theo số lượng trường geometry trong schema.

## 27. Các tình huống ứng dụng chi tiết

### 27.1. Cửa hàng gần vị trí khách hàng

**Dữ liệu:** `location: Point`.

**Truy vấn:** `$near` từ tọa độ khách.

**Không cần:** Polygon nếu chỉ tìm khoảng cách tới điểm đại diện của cửa hàng.

**Lưu ý:** khoảng cách trực tiếp không phải khoảng cách đường bộ.

### 27.2. Kho có vùng giao hàng đặc biệt

**Dữ liệu:** `serviceArea: Polygon` hoặc `MultiPolygon`.

**Truy vấn:** Điểm khách hàng có giao/thuộc vùng.

**Lưu ý:** nếu có vùng loại trừ, dùng **hole**, không tạo một polygon thứ hai để tính thêm diện tích.

### 27.3. Tuyến xe giao hàng

**Dữ liệu:** `route: LineString`.

**Truy vấn:** Đường có giao với vùng hạn chế hay không?

**Lưu ý:** LineString biểu diễn đường hình học, không đảm bảo có đường giao thông khả dụng giữa các waypoint.

### 27.4. Tuyến xe gồm các đoạn rời

**Dữ liệu:** `route: MultiLineString`.

**Truy vấn:** Các đoạn có giao một vùng hay không?

**Lưu ý:** không tự nối các đoạn rời thành một tuyến liên tục.

### 27.5. Dịch vụ có các vùng khác nhau

**Dữ liệu:** `serviceArea: MultiPolygon`.

**Truy vấn:** Khách nằm trong một trong các vùng hợp lệ?

**Lưu ý:** đừng biểu diễn phần thứ hai thành inner ring của Polygon.

### 27.6. Tập điểm đo của một đợt khảo sát

**Dữ liệu:** `samples: MultiPoint` nếu mọi điểm là thành phần của một geometry.

**Lưu ý:** nếu từng điểm cần cập nhật/định danh độc lập, cân nhắc nhiều document Point.

### 27.7. Công trình hạ tầng có nhiều thành phần

**Dữ liệu:** `GeometryCollection`, hoặc nhiều field geometry nếu từng thành phần cần index/query riêng.

**Lưu ý:** collection hình học không tự tổ chức domain model; vẫn cần ID, quan hệ, quyền truy cập và vòng đời rõ ràng.

## 28. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `[lat, lon]` | Điểm bị đặt sai hoặc invalid | Chuẩn hóa `[lon, lat]` |
| Truyền tọa độ String | Index/query geometry lỗi | Dùng số BSON |
| Lưu Point bằng `[[x,y]]` | Sai độ lồng | Point dùng `[x,y]` |
| Lưu Polygon như LineString | Không có danh sách ring | Bọc thêm lớp ring |
| Ring không khép kín | Polygon không hợp lệ | Lặp position đầu ở cuối |
| Ring có ít hơn 4 position | Không đủ hình học vùng | Có tối thiểu 3 đỉnh phân biệt + closure |
| Hole nằm ngoài outer ring | Sai topology | Xác minh containment |
| Polygon tự cắt | Vùng không hợp lệ/khó diễn giải | Sửa biên bằng GIS |
| Nhiều vùng đưa thành nhiều ring | Vùng thứ hai bị hiểu là hole | Dùng MultiPolygon |
| Tuyến dùng MultiPoint | Mất ý nghĩa đoạn nối | Dùng LineString |
| Đoạn tuyến rời nối thành LineString | Xuất hiện đoạn nối giả | Dùng MultiLineString |
| GeometryCollection dùng `coordinates` cấp ngoài | Sai cấu trúc | Dùng `geometries` |
| Index nguyên Feature thay vì geometry | Không đúng đường dẫn geometry | Index `feature.geometry` |
| Chọn index `2d` cho dữ liệu GPS dạng GeoJSON | Không đúng hình học cầu | Dùng `2dsphere` |
| Dùng `$near` với Polygon làm tâm | Sai loại query geometry | Dùng Point làm tâm |
| Coi `$geoWithin` là có giao một phần | Có thể bỏ sót tuyến chỉ cắt qua vùng | Chọn `$geoIntersects` |
| Coi `updateLookup`/dữ liệu ứng dụng là công cụ GIS | Phụ thuộc chức năng ngoài phạm vi | Dùng GIS khi cần |
| Dùng `_id` document thay điều kiện không gian | Không trả lời quan hệ địa lý | Dùng operator địa lý |
| Hiểu `$maxDistance` là km khi truyền 5000 | Sai đơn vị | Với GeoJSON spherical, thường là mét |
| Dùng một polygon quá lớn không xét vùng bù | Query nhắm vùng ngoài ý muốn | Kiểm tra hemisphere/CRS strict-winding |
| Coi geometry có altitude là query 3D | Kết quả không xét độ cao như mong muốn | Thiết kế xử lý cao độ riêng |
| Kết quả nằm trên biên luôn nhất quán với phép kiểm tra phẳng | Sai số/định nghĩa biên khác | Xác định yêu cầu boundary và test |
| Một Polygon mô tả đường đi tối ưu | Không có mạng đường | Dùng routing engine khi cần |
| Index geospatial là shard key | Vi phạm giới hạn sharding | Chọn shard key riêng |
| Không kiểm tra CRS đầu vào | Các vùng sai hoàn toàn | Chuyển về WGS84 trước |

## 29. Bài tập thực hành

### Bài 1 — Nhận diện kiểu hình học

Cho:

```javascript
const A = { type: "Point", coordinates: [106.70, 10.80] };
const B = {
  type: "LineString",
  coordinates: [[106.70,10.80],[106.75,10.82]]
};
const C = {
  type: "MultiPoint",
  coordinates: [[106.70,10.80],[106.75,10.82]]
};
```

Hãy trả lời: B và C giống nhau ở cấu trúc `coordinates` nhưng khác nhau ở ngữ nghĩa gì? A khác chúng ở độ lồng mảng nào?

### Bài 2 — Sửa thứ tự tọa độ

Một API trả:

```javascript
{
  latitude: 10.81,
  longitude: 106.71
}
```

Viết GeoJSON Point hợp lệ. Tại sao không truyền `[latitude, longitude]`? Điều gì xảy ra nếu cả hai giá trị vô tình nằm trong phạm vi kinh/vĩ độ hợp lệ?

### Bài 3 — Tạo LineString

Cho ba waypoint:

```text
A = [106.65, 10.76]
B = [106.70, 10.80]
C = [106.75, 10.85]
```

Viết một LineString từ A → B → C. Nếu đảo thứ tự thành C → B → A, hình học tuyến có thay đổi vị trí hình vẽ không? Ý nghĩa hướng di chuyển ở ứng dụng có thể thay đổi không?

### Bài 4 — Đóng vòng Polygon

Một polygon được gửi từ frontend:

```javascript
[
  [106.65, 10.75],
  [106.85, 10.75],
  [106.85, 10.90],
  [106.65, 10.90]
]
```

Hãy chuyển thành `{ type: "Polygon", coordinates: ... }` hợp lệ. Vì sao cần lặp đỉnh đầu? Có bao nhiêu **đỉnh phân biệt** và bao nhiêu **position trong ring**?

### Bài 5 — Polygon có hole

Tạo Polygon gồm:

- Vòng ngoài hình chữ nhật từ longitude 106.60 tới 106.90 và latitude 10.70 tới 10.90.
- Vùng lỗ ở giữa từ longitude 106.70 tới 106.75 và latitude 10.78 tới 10.82.

Viết đúng độ lồng mảng, giữ các ring khép kín. Điểm `[106.72, 10.80]` thuộc phần diện tích phục vụ không?

### Bài 6 — MultiPolygon hay Polygon nhiều ring?

Một công ty phục vụ hai khu vực:

```text
Khu A: [106.60..106.65] × [10.70..10.74]
Khu B: [106.80..106.85] × [10.85..10.89]
```

Hãy chọn Polygon, MultiPolygon hay GeometryCollection và giải thích. Viết JSON/BSON geometry cho lựa chọn đó.

### Bài 7 — MultiLineString

Một tuyến vận tải có hai phần:

```text
Đoạn 1: A -> B -> C
Đoạn 2: D -> E
```

Viết MultiLineString. Nếu đổi thành LineString A → B → C → D → E, hệ thống đã thêm một đoạn giả nào?

### Bài 8 — GeometryCollection

Tạo một GeometryCollection chứa:

1. Điểm trạm trung tâm.
2. Một LineString lộ trình.
3. Một Polygon phạm vi.

Vì sao `GeometryCollection` dùng `geometries` thay vì `coordinates` ở cấp cao nhất? Khi nào có thể dùng ba field geometry riêng thay thế?

### Bài 9 — Import một GeoJSON Feature

Cho:

```json
{
  "type": "Feature",
  "properties": { "name": "Kho A" },
  "geometry": {
    "type": "Point",
    "coordinates": [106.70, 10.80]
  }
}
```

Thiết kế document MongoDB với `name` và `location`. Tạo `2dsphere` index trên đường dẫn thích hợp. Vì sao không index vào field String chứa JSON serialized?

### Bài 10 — Tìm điểm trong vùng

Sử dụng dữ liệu `points292` và `deliveryArea292`:

1. Viết truy vấn `$geoWithin`.
2. Dự đoán những Point trong vùng, ngoài vùng và trong hole.
3. Giải thích vì sao không được coi điểm nằm trong hole là hợp lệ.
4. Kết quả `$geoWithin` có tự sắp theo khoảng cách không?

### Bài 11 — Tuyến cắt vùng

Cho route:

```javascript
{
  type: "LineString",
  coordinates: [
    [106.60, 10.78],
    [106.72, 10.81],
    [106.90, 10.86]
  ]
}
```

Hãy viết query `$geoIntersects` với `deliveryArea292`. Vì sao `$geoWithin` có thể không phù hợp khi một phần route nằm ngoài vùng?

### Bài 12 — Tìm vị trí gần nhất

Tạo `2dsphere` index trên `location` và tìm những Point trong bán kính 5.000 mét từ `[106.70, 10.80]`. Dùng `$near` với `$geometry`. Phân biệt khoảng cách địa lý và thời gian lái xe.

### Bài 13 — `$geoNear` trong aggregation

Viết pipeline:

1. Lấy khoảng cách từ một Point.
2. Đặt tên field `distanceMeters`.
3. Chỉ trả `_id`, `name` và `distanceMeters`.
4. Giới hạn 10 kết quả.

Giải thích vai trò của `key` nếu collection có nhiều geospatial index.

### Bài 14 — Validate geometry

Viết hàm kiểm tra:

- Position là mảng 2 số hữu hạn trong phạm vi lon/lat.
- LineString có ít nhất 2 position.
- Polygon có ít nhất một ring.
- Ring có ít nhất 4 position và đầu/cuối trùng nhau.

Sau đó nêu **ít nhất bốn lỗi topology/CRS** mà các hàm trên không thể phát hiện.

### Bài 15 — Sai CRS

Một nguồn dữ liệu GIS dùng tọa độ mét:

```text
x = 689000
y = 1192000
```

Đội lập trình định ghi:

```javascript
{
  type: "Point",
  coordinates: [689000, 1192000]
}
```

Hãy giải thích vấn đề và các bước chuyển về GeoJSON/WGS84. Vì sao không chỉ chia các số cho một hệ số tùy ý?

### Bài 16 — Vùng qua đường đổi ngày

Một LineString đi từ `[179.9, 10]` tới `[-179.9, 10]`. Khoảng chênh kinh độ tính bằng phép trừ thông thường gần 360 độ. Điều đó có nghĩa đường phải chạy gần một vòng Trái Đất không? Nêu vì sao geometry cầu và phép chiếu bản đồ ảnh hưởng cách hiểu.

### Bài 17 — Vùng lớn hơn bán cầu

Tại sao một Polygon rất lớn dùng CRS mặc định có thể bị hiểu thành vùng bù? `strictwinding` của MongoDB liên quan những truy vấn nào và có thể áp dụng tùy ý cho MultiPolygon không?

### Bài 18 — Thiết kế schema giao vận

Ứng dụng có:

- 20.000 tài xế cập nhật vị trí mỗi 3 giây.
- 200 kho có ranh giới giao hàng thay đổi mỗi quý.
- 10.000 tuyến đường được tính lại hằng ngày.

Hãy đề xuất collection và kiểu GeoJSON cho từng nhóm. Chọn index geospatial theo truy vấn dự kiến, cân nhắc chi phí cập nhật, dung lượng và việc một geometry quá nhiều đỉnh.

### Bài 19 — Bản đồ đúng nhưng truy vấn sai

Một polygon hiển thị có vẻ đúng nhưng `$geoWithin` trả thiếu điểm. Hãy liệt kê nguyên nhân có thể:

- Đảo lon/lat.
- Polygon có hole hoặc vòng tự cắt.
- Dữ liệu dùng CRS khác.
- Định nghĩa vùng lớn/bán cầu.
- Giá trị geometry sai kiểu.
- Query field/index sai đường dẫn.
- Sai khác ở đường biên.

Với mỗi nguyên nhân, đề xuất cách kiểm tra bằng dữ liệu hoặc công cụ phù hợp.

### Bài 20 — Lựa chọn đúng 7 kiểu geometry

Phân loại:

1. Một nhà ga.
2. Một tuyến tàu đơn.
3. Một công viên có hồ ở giữa không thuộc công viên.
4. Nhiều điểm cảm biến trong cùng một bộ đo.
5. Ba tuyến cáp không liên thông.
6. Một khu bảo tồn gồm hai vùng tách biệt.
7. Một công trình gồm điểm trung tâm, tuyến nối và vùng phụ trợ.

Hãy chọn giữa `Point`, `LineString`, `Polygon`, `MultiPoint`, `MultiLineString`, `MultiPolygon` và `GeometryCollection`. Giải thích khi nào lưu nhiều document độc lập tốt hơn một hình học Multi*.

## 30. Quy trình thiết kế dữ liệu địa lý đáng tin cậy

Khi nhận một yêu cầu lưu hình học vào MongoDB, hãy đi từ **ý nghĩa nghiệp vụ** đến **cấu trúc geometry**, rồi mới quyết định index/truy vấn.

1. **Xác định đơn vị dữ liệu:** điểm, tuyến, vùng, nhiều thành phần cùng loại hay tập hình trộn?
2. **Xác định CRS:** dữ liệu nguồn có thực sự là longitude/latitude WGS84 không?
3. **Chuẩn hóa vị trí:** `[longitude, latitude]`, kiểu số hữu hạn và phạm vi hợp lệ.
4. **Chọn type đúng:** không đổi LineString thành MultiPoint hoặc Polygon có hole thành MultiPolygon.
5. **Kiểm tra topology:** khép ring, thứ tự ring, hole containment, self-intersection, overlapping shapes và vùng lớn.
6. **Thiết kế field:** `location`, `route`, `serviceArea` hoặc `geometry` theo query pattern, tránh trường String chứa JSON.
7. **Tạo index đúng:** `2dsphere` trên **field geometry thực tế** khi cần truy vấn không gian.
8. **Chọn operator theo câu hỏi:** within, intersects hay near; hiểu sự khác biệt “toàn bộ nằm trong” và “có giao”.
9. **Kiểm tra trường hợp biên:** điểm trong hole, đường cắt ranh, qua kinh tuyến đổi ngày, tọa độ gần cực và Polygon lớn.
10. **Đo trên dữ liệu thật:** dùng `explain()`, index size và độ trễ; polygon nhiều đỉnh có thể tốn tài nguyên.
11. **Theo dõi chất lượng nguồn:** geometry lỗi/CRS sai cần được phát hiện trước khi gây sai kết quả nghiệp vụ.
12. **Tài liệu hóa hợp đồng:** tên trường, kiểu geometry cho phép, độ chính xác, version dữ liệu, đơn vị khoảng cách.

## 31. Tổng kết

**GeoJSON mô tả hình học bằng `type` và cấu trúc tọa độ tương ứng.** `Point` là một vị trí `[lon, lat]`; `LineString` là chuỗi đỉnh có ý nghĩa nối thành tuyến; `Polygon` là vùng được giới hạn bởi các **LinearRing khép kín**, có thể có **holes**. Ba kiểu này giải quyết ba bài toán hình học khác nhau, không nên hoán đổi.

**Các kiểu mở rộng có ý nghĩa riêng:** `MultiPoint` cho nhiều điểm, `MultiLineString` cho nhiều tuyến, `MultiPolygon` cho nhiều vùng tách biệt, và `GeometryCollection` chứa nhiều geometry khác loại thông qua trường `geometries`. Polygon có nhiều ring không giống MultiPolygon: ring bên trong thường là **lỗ bị loại trừ**, chứ không phải một vùng được cộng thêm.

**MongoDB xử lý GeoJSON theo ngữ nghĩa địa lý cầu WGS84.** Đúng thứ tự **kinh độ trước, vĩ độ sau**, đúng CRS, đúng topology và hiểu cách diễn giải polygon rất lớn là điều kiện căn bản. `2dsphere` giúp truy vấn hình học phù hợp; `$geoWithin`, `$geoIntersects` và `$near` trả lời **những câu hỏi không gian khác nhau**.

**Index không sửa được geometry sai, còn geometry đúng không thay thế logic nghiệp vụ.** Một Point không tự biểu diễn ranh giới, một LineString không phải mạng giao thông có shortest path, và một Polygon không tự hiểu quy tắc vận hành của kho. Khi lựa chọn đúng hình học, validate cấu trúc và giữ hợp đồng dữ liệu rõ ràng, MongoDB có thể hỗ trợ tốt các nhu cầu tìm kiếm vị trí, tuyến và vùng trong những ứng dụng thực tế.

## Tài liệu tham khảo

- [MongoDB Database Manual — GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/): bảy dạng geometry, độ lồng tọa độ, Polygon và hole.
- [MongoDB Database Manual — Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/): mô hình dữ liệu và các truy vấn không gian.
- [MongoDB Database Manual — 2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/): tạo và sử dụng chỉ số hình học cầu.
- [MongoDB Database Manual — $geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/): within, vùng lớn và các ràng buộc.
- [MongoDB Database Manual — $geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/): truy vấn giao nhau.
- [MongoDB Java Sync Driver — Geospatial Queries](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/geo/): các kiểu GeoJSON và builder cho Java.
