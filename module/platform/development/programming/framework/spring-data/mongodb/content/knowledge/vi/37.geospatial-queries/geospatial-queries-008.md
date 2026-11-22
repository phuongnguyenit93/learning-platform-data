# Đối sánh vùng địa lý và kiểm thử tọa độ biên

## 1. Bài toán: một điểm có nằm trong vùng phục vụ?

Trong chương **Truy vấn không gian** của **Spring Data MongoDB**, ứng dụng thường cần xác định một địa điểm có thuộc **vùng giao hàng**, **khu vực quản lý**, **vùng ưu đãi** hoặc **geofence** hay không. Câu hỏi nghe đơn giản — “điểm P nằm trong vùng A?” — nhưng câu trả lời phụ thuộc định dạng tọa độ, hình học vùng, ranh giới và ngữ nghĩa của toán tử MongoDB.

Ví dụ một doanh nghiệp lưu cửa hàng với vị trí GeoJSON:

~~~json
{
  "_id": "store-101",
  "tenantId": "tenant-a",
  "status": "ACTIVE",
  "name": "Điểm giao nhận A",
  "location": {
    "type": "Point",
    "coordinates": [106.7000, 10.7800]
  }
}
~~~

Một vùng hình chữ nhật thử nghiệm có kinh độ từ `106.66` đến `106.74` và vĩ độ từ `10.74` đến `10.82`. Ta muốn tìm các cửa hàng thuộc vùng, nhưng đồng thời phải trả lời:

- Điểm nằm **rõ ràng bên trong** hay **rõ ràng bên ngoài**?
- Điểm nằm **rất gần** cạnh nhưng chưa chạm ranh giới?
- Điểm nằm **chính xác trên cạnh hoặc đỉnh** nên được coi là trong hay ngoài?
- Vùng có **lỗ** ở giữa, nhiều phần rời nhau hoặc cắt đường kinh tuyến ±180° thì sao?
- Một vùng có thể **chạm** vùng khác mà không có nội thất giao nhau không?
- Query có sử dụng **2dsphere index**, có giới hạn theo tenant, có đúng trường BSON không?

Mục tiêu bài học:

1. Mô hình hóa Point, Polygon, MultiPolygon và các vòng (rings) GeoJSON đúng cấu trúc.
2. Phân biệt `$geoWithin`, `$geoIntersects` và mục tiêu khác của `$near`.
3. Xây query tìm điểm trong vùng bằng MongoDB BSON và `MongoTemplate`.
4. Hiểu **đường biên là một trường hợp cần hợp đồng riêng**, không đoán từ một hình vẽ.
5. Lập bộ test **inside / outside / just-inside / just-outside / on-edge / on-vertex / hole**.
6. Kiểm tra trên MongoDB thật, xác minh GeoJSON/2dsphere index và hiệu năng bằng `explain`.
7. Tránh sai lệch do đảo longitude–latitude, độ chính xác, anti-meridian, projection hoặc tenant filtering.

> Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x và MongoDB có hỗ trợ toán tử GeoJSON/2dsphere. Các bài test về **điểm đúng trên biên** cần xác minh thực nghiệm trên server/version/geometry cụ thể: kết quả biên của truy vấn geospatial không nên bị coi là hợp đồng “đóng/mở” phổ quát nếu MongoDB không bảo đảm điều đó cho trường hợp đang xét.

## 2. Phân biệt tọa độ với đơn vị đo khoảng cách

GeoJSON Point biểu diễn:

~~~json
{
  "type": "Point",
  "coordinates": [106.70, 10.78]
}
~~~

Mảng `coordinates` theo thứ tự **[longitude, latitude]** — tức **[kinh độ, vĩ độ]**. Với các điểm ví dụ ở Việt Nam, số kinh độ khoảng 106.x và vĩ độ khoảng 10.x. Đảo hai số là lỗi thường gặp khi dữ liệu đầu vào dùng thứ tự “latitude, longitude”.

| Thành phần | Ý nghĩa | Phạm vi thông thường |
|---|---|---|
`longitude` | Kinh độ, hướng đông/tây | Từ −180° đến +180° |
`latitude` | Vĩ độ, hướng bắc/nam | Từ −90° đến +90° |
`coordinates[0]` | Kinh độ | Độ thập phân |
`coordinates[1]` | Vĩ độ | Độ thập phân |

Không sử dụng một cặp tọa độ tùy ý làm GeoJSON nếu chưa xác định hệ quy chiếu. MongoDB dùng hệ tọa độ cầu theo chuẩn GeoJSON cho các truy vấn hỗ trợ. `GeoJsonPoint(106.70, 10.78)` nghĩa là **x=longitude**, **y=latitude**.

### 2.1. Độ là góc, không phải mét

Một đoạn `0.001°` kinh độ không có cùng độ dài vật lý tại xích đạo và gần cực. Vì thế:

- Không chuyển một ngưỡng “cách biên 20 m” thành `±0.0002°` theo quy tắc cố định toàn thế giới.
- Không dùng khoảng cách Euclid trực tiếp trên cặp longitude/latitude để làm tiêu chuẩn pháp lý hoặc an toàn.
- Nếu cần “cách biên bao nhiêu mét”, hãy chọn một thuật toán tính khoảng cách địa lý/geodesic phù hợp, xác định tolerance và xác minh riêng.

Trong bài, các điểm *just-inside* và *just-outside* dùng tọa độ thập phân cách biên một khoảng hữu hạn để kiểm tra sự phân loại, **không ngầm tuyên bố khoảng cách đó bằng một số mét chuẩn**.

### 2.2. Tọa độ không tự chứng minh độ chính xác GPS

Thiết bị có thể cung cấp location có sai số vài mét hoặc lớn hơn. Một cặp số nhiều chữ số thập phân không đồng nghĩa đo được với độ chính xác tương ứng. Khi áp dụng geofence cho thanh toán, an toàn hoặc quyền truy cập, phải có chính sách:

~~~text
reported location + accuracy/uncertainty
          |
          v
candidate region matching
          |
          v
near-boundary confidence policy
          |
          v
accept / reject / request better evidence
~~~

MongoDB trả kết quả truy vấn hình học theo tọa độ đã lưu, không tự suy ra chất lượng nguồn GPS.

## 3. Tạo Polygon GeoJSON hợp lệ

Vùng thử nghiệm hình chữ nhật:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.66, 10.74],
      [106.74, 10.74],
      [106.74, 10.82],
      [106.66, 10.82],
      [106.66, 10.74]
    ]
  ]
}
~~~

GeoJSON Polygon có `coordinates` là **mảng các vòng**. Vòng đầu tiên diễn tả đường bao ngoài. Mỗi vòng có ít nhất bốn vị trí (tính cả điểm cuối lặp lại để đóng vòng).

Ở đây:

- Góc tây nam: `[106.66, 10.74]`.
- Góc đông nam: `[106.74, 10.74]`.
- Góc đông bắc: `[106.74, 10.82]`.
- Góc tây bắc: `[106.66, 10.82]`.
- Điểm cuối **trùng điểm đầu** để đóng vòng.

Sơ đồ mô hình trên mặt phẳng tọa độ nhỏ (chỉ minh họa, không phải bản đồ tỉ lệ):

~~~text
              latitude
                  ^
  10.82     NW +---------------+ NE
              |               |
              |     INSIDE    |
  10.78       |       •       |
              |               |
  10.74     SW +---------------+ SE
                  106.66      106.74  --> longitude
~~~

### 3.1. Không thiếu cấp lồng mảng

Sai:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [106.66, 10.74],
    [106.74, 10.74],
    [106.74, 10.82]
  ]
}
~~~

Đây là cấu trúc gần với `LineString`, **không phải** `Polygon.coordinates` hợp lệ. Cấu trúc đúng phải có dạng:

~~~text
Polygon.coordinates = [
  outerRing[ [lon,lat], [lon,lat], ... ],
  optionalHoleRing[ ... ],
  ...
]
~~~

### 3.2. Hướng vòng và quy tắc right-hand rule

Theo GeoJSON RFC 7946, vòng ngoài được khuyến nghị theo hướng **ngược chiều kim đồng hồ (CCW)** và vòng lỗ theo hướng **thuận chiều kim đồng hồ (CW)** khi xem trong hệ trục longitude–latitude thông thường.

Không được sửa hình học bằng cách đảo thứ tự điểm tùy ý khi vùng cắt antimeridian, bao phủ hơn một bán cầu hoặc dùng MongoDB `$geometry` với CRS đặc biệt. MongoDB có quy tắc diễn giải về winding/spherical polygons; dùng test và tài liệu đúng version khi khu vực lớn/phức tạp.

### 3.3. Hình học hợp lệ không chỉ là đóng vòng

Polygon có thể đóng vòng nhưng vẫn sai:

- Cạnh tự cắt thành hình “nơ”.
- Có cạnh độ dài bằng 0 hoặc nhiều đỉnh trùng làm topology mơ hồ.
- Hole nằm ngoài outer ring hoặc chạm/cắt outer boundary không hợp lệ.
- Vòng không theo quy tắc winding của hệ thống đang dùng.
- Polygon được dựng từ những tọa độ đảo lat/lon.

Một validator chỉ kiểm tra kinh/vĩ độ và điểm đầu/cuối **không phải công cụ kiểm chứng topology đầy đủ**. Đối với polygon nhập từ người dùng hoặc GIS, cần một bước kiểm tra geometry/topology chuyên dụng hoặc nguồn dữ liệu GIS đã được xác thực trước khi lưu.

## 4. Các toán tử tìm vùng và đối sánh hình học

Ba nhóm toán tử hay bị nhầm:

| Toán tử | Ý nghĩa chính | Dùng khi |
|---|---|---|
`$geoWithin` | Chọn geometry nằm trong vùng được đưa ra | Tìm các điểm cửa hàng **trong** Polygon |
`$geoIntersects` | Chọn geometry có giao với geometry truy vấn | Tìm vùng kho **giao** với vùng cấm; xét giao giữa geometries |
`$near`/`$nearSphere` | Sắp xếp theo khoảng cách gần một điểm, có thể giới hạn khoảng cách | Tìm cửa hàng gần khách hàng, **không** thay region inclusion |

Ví dụ MongoDB `$geoWithin`:

~~~javascript
db.geo_outlets.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.66, 10.74],
          [106.74, 10.74],
          [106.74, 10.82],
          [106.66, 10.82],
          [106.66, 10.74]
        ]]
      }
    }
  }
});
~~~

Đây là truy vấn **lấy document có location nằm trong Polygon** theo semantics của toán tử và hình học MongoDB. Không phải tính khoảng cách tới tâm; một điểm gần tâm vẫn có thể nằm ngoài polygon lõm hoặc nằm trong lỗ.

### 4.1. Đối sánh một Point và một Polygon

Đối với các cửa hàng lưu `location: Point`, `$geoWithin` với Polygon là cách thể hiện trực tiếp bài toán point-in-region. Khi field là một Polygon hoặc MultiPolygon thay vì Point, quan hệ “geometry nằm trong vùng” khác với câu hỏi “hai vùng có giao nhau hay không”; lúc đó cân nhắc `$geoIntersects`.

### 4.2. Đối sánh vùng-vùng bằng $geoIntersects

Nếu một document lưu Polygon biểu diễn khu vực một đối tác hoạt động:

~~~javascript
db.partner_areas.find({
  tenantId: "tenant-a",
  coverage: {
    $geoIntersects: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.66, 10.74],
          [106.74, 10.74],
          [106.74, 10.82],
          [106.66, 10.82],
          [106.66, 10.74]
        ]]
      }
    }
  }
});
~~~

Kết quả quan hệ giao khác `$geoWithin`: hai vùng có thể chỉ giao một phần, không vùng nào chứa hoàn toàn vùng kia. Ngoài ra **đường biên chung** có thể là trường hợp cần test riêng; nếu nghiệp vụ cần diện tích giao dương chứ không chỉ có điểm chung, không coi một query intersects là phép tính diện tích.

### 4.3. $near không trả lời câu hỏi “trong vùng?”

Một điểm cách trung tâm vùng 100 m có thể nằm ngoài polygon rất hẹp; một điểm cách tâm xa nhưng thuộc cánh dài của polygon lõm vẫn nằm trong. Tìm `nearest N` và kiểm tra `maxDistance` chỉ phù hợp khi vùng chính là một đĩa bán kính tương ứng, không thay mọi vùng tùy ý.

### 4.4. Bounding box chỉ là một phép lọc khác

Điều kiện kinh/vĩ độ tối thiểu và tối đa có thể dùng để lọc ứng viên trong **một bounding box**. Nhưng với Polygon lõm, vùng có lỗ hoặc vùng cắt antimeridian, bounding box có thể chứa các điểm **nằm ngoài vùng thật**.

Vì vậy:

~~~text
bbox match != polygon match
~~~

Nếu dùng bbox để tăng tốc tiền lọc, phải kiểm tra geometry thật và đo xem MongoDB/index planner có cần bước tiền lọc đó hay không.

## 5. Tạo geospatial index phù hợp

Với GeoJSON `Point` trên field `location`, index thông dụng:

~~~javascript
db.geo_outlets.createIndex(
  { location: "2dsphere" },
  { name: "idx_outlet_location_2dsphere" }
);
~~~

`2dsphere` hỗ trợ các truy vấn không gian trên bề mặt cầu với những geometry hợp lệ. Không dùng `2d` một cách tùy tiện cho GeoJSON trên toàn thế giới và không suy rằng một index `2d` có cùng semantics với `2dsphere`.

### 5.1. Có bắt buộc index để $geoWithin chạy?

Một số geospatial predicates có thể chạy mà không có geospatial index, nhưng với dữ liệu lớn cần xét `2dsphere` index để giảm số document phải kiểm tra. Các yêu cầu index của toán tử khác nhau theo operation và phiên bản, do đó không suy “không có index thì mọi geo operator đều thất bại” hoặc “có index thì mọi query nhanh”.

Muốn biết query thực tế dùng index hay không, kiểm tra `explain("executionStats")` trên dataset đại diện và xem index name/stages.

### 5.2. Compound 2dsphere index cho tenant/status

Nếu workload luôn lọc theo tenant và trạng thái:

~~~javascript
db.geo_outlets.createIndex(
  { tenantId: 1, status: 1, location: "2dsphere" },
  { name: "idx_outlet_tenant_status_geo" }
);
~~~

Đây là **ứng viên thiết kế**, không phải lựa chọn tối ưu được bảo đảm cho mọi dataset. Cần kiểm tra selectivity, kích thước index, mức write load và query plans. Geospatial compound index có những quy tắc về geospatial field và document không có geometry; đừng tạo nhiều index trùng lặp mà chưa đo.

### 5.3. Index không bảo vệ tenant

`tenantId` trong compound index giúp truy vấn hiệu quả hơn nếu được sử dụng. Nó **không tự thêm tenantId vào filter**. Tầng service phải lấy tenant từ auth context đã kiểm chứng và đưa điều kiện vào **cùng query** với geospatial predicate.

### 5.4. Provisioning index là công việc có kiểm soát

Không mặc định `@GeoSpatialIndexed` sẽ tạo index trên database production ở mọi cấu hình. Spring Data MongoDB hiện đại có chính sách auto-index creation phụ thuộc cấu hình; cần quy trình migration/provisioning, kiểm tra index đã tồn tại và index build có ảnh hưởng đến hệ thống.

## 6. Polygon có lỗ: bên trong vòng ngoài chưa chắc đủ

Một vùng phục vụ có khu cấm ở giữa, ví dụ khuôn viên không được giao hàng:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.66, 10.74],
      [106.74, 10.74],
      [106.74, 10.82],
      [106.66, 10.82],
      [106.66, 10.74]
    ],
    [
      [106.69, 10.77],
      [106.69, 10.79],
      [106.71, 10.79],
      [106.71, 10.77],
      [106.69, 10.77]
    ]
  ]
}
~~~

Vòng ngoài bao vùng. Vòng thứ hai là **lỗ**. Trong ví dụ, các đỉnh lỗ được sắp theo hướng ngược vòng ngoài. Các kết quả mong muốn theo geometry:

| Điểm | Tọa độ [lon, lat] | Phân loại ý định |
|---|---|---|
Phía tây, trong outer | `[106.675, 10.78]` | Trong vùng có hiệu lực |
Chính giữa lỗ | `[106.700, 10.780]` | Ngoài vùng có hiệu lực |
Phía đông, trong outer | `[106.725, 10.78]` | Trong vùng có hiệu lực |
Ngoài outer | `[106.750, 10.78]` | Ngoài vùng |
Trên biên lỗ | `[106.690, 10.78]` | Trường hợp boundary cần policy/test riêng |

### 6.1. Không biến hole thành một Polygon độc lập trong cùng truy vấn

Nếu dùng `MultiPolygon` chứa cả outer ring và hole như hai polygon độc lập, phần “hole” có thể bị hiểu thành vùng **được bao gồm**. Một hole phải nằm ở **ring thứ hai** bên trong cùng một `Polygon.coordinates`, không phải một Polygon riêng được union vào vùng.

### 6.2. Ranh giới của hole là biên đặc biệt

Điểm đúng trên mép lỗ khác điểm rõ ràng bên trong lỗ. Nếu nghiệp vụ cần từ chối mọi điểm “trong lỗ hoặc chạm biên lỗ”, cần định nghĩa một **quy tắc bao gồm/exclude vùng đệm** thay vì mong một toán tử luôn có hành vi mong muốn tại mọi cạnh/đỉnh.

### 6.3. Không tự chấp nhận polygon tự cắt

Một polygon có hole chạm/cắt đường bao ngoài có thể không hợp lệ hoặc được diễn giải khác nhau theo thư viện GIS/server. Kiểm tra tính hợp lệ topology ở bước ingest trước khi tạo index và truy vấn.

## 7. MultiPolygon: vùng có nhiều mảng rời nhau

Một dịch vụ có hai cụm phục vụ cách xa nhau:

~~~json
{
  "type": "MultiPolygon",
  "coordinates": [
    [
      [
        [106.66, 10.74],
        [106.74, 10.74],
        [106.74, 10.82],
        [106.66, 10.82],
        [106.66, 10.74]
      ]
    ],
    [
      [
        [106.80, 10.74],
        [106.84, 10.74],
        [106.84, 10.78],
        [106.80, 10.78],
        [106.80, 10.74]
      ]
    ]
  ]
}
~~~

`MultiPolygon.coordinates` có **một cấp lồng mảng nữa** so với Polygon:

~~~text
Polygon      = [ ring, optionalHoleRing, ... ]
MultiPolygon = [ polygonRings, polygonRings, ... ]
~~~

Không nối hai vùng rời nhau thành một ring duy nhất, vì đường nối có thể làm xuất hiện phần diện tích không mong muốn hoặc polygon tự cắt.

### 7.1. Nhiều vùng và nhiều tenant

Nếu mỗi tenant có nhiều vùng, có thể:

- Lưu mỗi vùng trong một document `service_areas` với `tenantId` và `geometry`.
- Tìm vùng chứa một địa điểm bằng `$geoIntersects` hoặc `$geoWithin` tùy chiều của geometry/loại đối tượng.
- Hoặc lưu một MultiPolygon đã được chuẩn hóa nếu business muốn một vùng hợp nhất.

Khi mô hình hóa **cửa hàng Point** và **vùng Polygon**, chiều truy vấn cần rõ:

~~~text
store.location Point $geoWithin input Polygon
    => tìm các cửa hàng thuộc vùng truy vấn

service_area.geometry Polygon $geoIntersects input Point
    => tìm các vùng có giao với điểm truy vấn
~~~

Không hoán đổi `$geoWithin` và `$geoIntersects` chỉ vì cả hai đều dùng từ “địa lý”.

## 8. Đường biên: điều cần kiểm thử thay vì phỏng đoán

Một polygon có **nội thất**, **ngoại thất** và **ranh giới**. Theo toán học, người ta có thể định nghĩa tập “đóng” (bao gồm biên) hoặc “mở” (không gồm biên). Nhưng một hệ thống geospatial thực còn có:

- Quy tắc hình học trên mặt cầu, không phải mọi cạnh là đoạn thẳng Euclid trong ảnh màn hình.
- Số thực và độ chính xác tọa độ.
- Topology vòng ngoài, hole và những cạnh trùng.
- Kết quả của toán tử/cơ chế index mà MongoDB tài liệu hóa.
- Sai số cảm biến và chính sách nghiệp vụ khi điểm nằm sát biên.

**Không viết một test giả định cứng “`$geoWithin` luôn include mọi điểm đúng trên cạnh/đỉnh Polygon” hoặc “luôn exclude” cho mọi hình học và mọi MongoDB version.** MongoDB có các lưu ý về tính xác định/diễn giải của kết quả geospatial trên đường ranh giới; cần test query thực tế và contract của hệ thống.

### 8.1. Bộ trường hợp tối thiểu

Với vùng chữ nhật minh họa:

| Case | Tọa độ | Ý định kiểm thử |
|---|---|---|
Inside rõ ràng | `[106.70, 10.78]` | Mong match |
Outside rõ ràng | `[106.76, 10.78]` | Mong không match |
Just-inside cạnh tây | `[106.662, 10.78]` | Mong match |
Just-outside cạnh tây | `[106.658, 10.78]` | Mong không match |
Just-inside góc tây nam | `[106.662, 10.742]` | Mong match |
Just-outside góc tây nam | `[106.658, 10.738]` | Mong không match |
Exactly-on-edge | `[106.66, 10.78]` | Ghi nhận kết quả thực, so với policy |
Exactly-on-vertex | `[106.66, 10.74]` | Ghi nhận kết quả thực, so với policy |
Just outside edge epsilon rất nhỏ | `[106.65999999, 10.78]` | Stress-test precision, không tự làm acceptance criterion |

Các điểm “just-inside/outside” trong ví dụ cách cạnh **một lượng hữu hạn** để tránh nhầm với round-off khi dựng test. Các điểm cách chỉ vài phần rất nhỏ của độ là bài test độ chính xác riêng, không phải test ổn định bắt buộc trong mọi môi trường.

### 8.2. Tách quyết định geometry và quyết định business

Ví dụ doanh nghiệp quy định:

~~~text
P ở rõ trong vùng  -> ACCEPT
P ở rõ ngoài vùng  -> REJECT
P trên hoặc sát biên trong 15 mét -> REVIEW / REQUEST_PRECISE_LOCATION
~~~

MongoDB `$geoWithin` giúp tìm ứng viên theo geometry; nó không tự biết “sát biên 15 mét” là bao nhiêu, không đọc độ chính xác GPS và không trả một chứng nhận theo business policy. Bước phân loại near-boundary phải dùng thuật toán/khoảng cách thích hợp và dữ liệu sai số.

### 8.3. Biên chia sẻ giữa hai khu vực

Hai polygon liền kề có thể cùng chạm một cạnh. Nếu nghiệp vụ yêu cầu **một điểm chỉ thuộc đúng một vùng**, kết quả geospatial độc lập chưa đủ xác định vùng ưu tiên. Cần tie-breaking rõ:

- Ưu tiên khu có priority cao hơn.
- Ưu tiên vùng được khai báo trước theo immutable business key.
- Hoặc coi điểm sát biên là ambiguous và yêu cầu dữ liệu bổ sung.

Đừng dùng thứ tự trả về của query MongoDB không có `sort` làm tie-breaking chính sách.

## 9. Kiểm tra dữ liệu tọa độ đầu vào

Một endpoint nhận vị trí từ mobile app nên phân biệt:

1. **Dữ liệu syntactically hợp lệ:** hai con số, đúng cấu trúc GeoJSON.
2. **Dữ liệu tọa độ hợp lệ:** kinh độ/vĩ độ trong phạm vi, số hữu hạn.
3. **Hình học polygon hợp lệ:** đóng vòng, không tự cắt, hole đúng vị trí, winding/CRS đúng.
4. **Dữ liệu có ý nghĩa nghiệp vụ:** vùng thuộc đúng tenant, còn hiệu lực, được phê duyệt.
5. **Vị trí đáng tin:** nguồn vị trí và độ chính xác đáp ứng chính sách.

Một bộ kiểm tra chỉ hoàn thành (1) và (2) chưa chứng minh (3)–(5).

### 9.1. Tránh đảo latitude và longitude

Không dùng constructor có tên mơ hồ:

~~~java
// Đặt tên rõ trước khi dựng GeoJSON:
double longitude = 106.70;
double latitude = 10.78;

GeoJsonPoint point = new GeoJsonPoint(longitude, latitude);
~~~

`GeoJsonPoint` import từ `org.springframework.data.mongodb.core.geo.GeoJsonPoint`. Một API đầu vào đặt tên fields `lat`/`lng` phải chuyển đổi rõ trước khi tạo GeoJSON, không dựa vào vị trí constructor của một thư viện khác.

### 9.2. Không chấp nhận NaN, Infinity hay tràn phạm vi

~~~java
public static void validateCoordinates(
        double longitude, double latitude) {
    if (!Double.isFinite(longitude)
            || !Double.isFinite(latitude)
            || longitude < -180 || longitude > 180
            || latitude < -90 || latitude > 90) {
        throw new IllegalArgumentException("Tọa độ không hợp lệ");
    }
}
~~~

Đây là validation cho một cặp coordinate; khi nhập Polygon cần thực hiện trên **mọi vị trí ở mọi ring**. Dù một số định dạng hoặc CRS mở rộng có ngữ nghĩa khác, ví dụ của bài chỉ sử dụng GeoJSON longitude–latitude trong phạm vi trên.

### 9.3. Không tự sửa lỗi bằng cách đổi chỗ hai số

Một cặp `[10.78, 106.70]` vi phạm phạm vi latitude nếu được hiểu là [lon,lat]. Không âm thầm đảo hai số rồi tiếp tục như thể nguồn đã đúng: rất nhiều vị trí trên thế giới có cả hai giá trị nằm trong khoảng hợp lệ, nên heuristic đảo tự động có thể **sửa sai dữ liệu vốn đúng**.

Thay vào đó, định nghĩa API contract đầu vào và validation rõ; nếu upstream sử dụng `(latitude, longitude)`, chuyển đổi tại adapter dành riêng cho upstream đó.

## 10. Antimeridian, cực và những polygon lớn

Đường kinh tuyến ±180° (antimeridian) là trường hợp kinh độ đổi biểu diễn từ gần +180° sang gần −180° dù hai vị trí rất gần nhau trên địa cầu.

Ví dụ hai vị trí:

~~~text
P1 = [ 179.9, 10.0]
P2 = [-179.9, 10.0]
~~~

Về địa lý, chúng ở hai phía gần nhau của antimeridian, nhưng nếu xử lý longitude như trục số thông thường, khoảng cách số học là 359.8°. Một Polygon hoặc bounding box dựng từ `minLongitude=-179.9` tới `maxLongitude=179.9` có thể biểu diễn **gần toàn cầu** thay vì dải nhỏ mong muốn.

### 10.1. Quy trình khi vùng đi qua ±180°

1. Xác nhận dữ liệu nguồn thực sự cắt antimeridian.
2. Dùng cách mô hình hóa GeoJSON/MultiPolygon đã được GIS chuẩn hóa cho trường hợp này, hoặc chia vùng thành những phần hợp lệ ở hai phía.
3. Không tự lấy `min/max longitude` rồi coi đó là vùng.
4. Kiểm tra điểm ở hai phía `179.9` và `-179.9`, điểm ở kinh tuyến 0° và điểm gần biên.
5. Kiểm tra giải thích winding/spherical area của MongoDB với geometry cụ thể.
6. Xác minh `2dsphere` index và truy vấn trên server/version production.

Không đưa một mẹo “nối điểm từ +179 sang −179 là luôn tạo cạnh ngắn” thành quy tắc cho mọi geometry. Với spherical polygons và vòng lớn, kết quả phụ thuộc quy tắc diễn giải/hướng vòng.

### 10.2. Polygon lớn hơn bán cầu và winding

MongoDB có quy tắc riêng cho GeoJSON polygons với diện tích lớn, winding và trong một số trường hợp cho phép custom CRS `strictwinding`. Không tự thêm CRS không phải GeoJSON chuẩn vào mọi Polygon: đây là cơ chế chuyên biệt cần đúng cú pháp, server support và test.

Nếu dữ liệu bao phủ nhiều châu lục hoặc gần cực, hãy kiểm tra tài liệu MongoDB cho phiên bản đang dùng và sử dụng dữ liệu địa lý đã được xử lý bởi GIS chuyên dụng. **Bài này không dùng một vùng lớn làm acceptance test chung** vì nó có nhiều lựa chọn diễn giải.

### 10.3. Gần cực

Tại vĩ độ gần ±90°, các đường kinh tuyến hội tụ. Một polygon dựng như hình chữ nhật trên bản đồ 2D có thể tạo hình spherical không giống vùng nhìn thấy trên màn hình. Test phải dùng hình học cầu thực tế, không chỉ ảnh chụp từ bản đồ Web Mercator.

## 11. Entity Spring Data MongoDB cho địa điểm

Ta lưu các điểm giao nhận trong collection `geo_outlets` dưới dạng GeoJSON Point.

**GeoOutlet.java**

~~~java
package com.example.geo;

import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "geo_outlets")
public record GeoOutlet(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String status,
        String name,
        @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
        GeoJsonPoint location) {
}
~~~

Một instance:

~~~java
GeoOutlet outlet = new GeoOutlet(
        "store-101",
        "tenant-a",
        "ACTIVE",
        "Điểm giao nhận A",
        new GeoJsonPoint(106.7000, 10.7800));
~~~

MongoDB mapping converter của Spring Data lưu `GeoJsonPoint` thành GeoJSON `Point` với mảng `coordinates`, khi dùng đường persistence tương ứng.

### 11.1. @GeoSpatialIndexed không phải schema constraint

Annotation này mô tả một index mong muốn cho Spring Data; việc **index có thực sự được tạo trên MongoDB hay không** còn phụ thuộc cơ chế index provisioning. Không nghĩ “có annotation trong Java” là đã có index trên production.

### 11.2. @MongoId giữ _id String

Với ID `"store-101"`, ví dụ dùng `@MongoId(FieldType.STRING)` để tránh sự mơ hồ về chuyển đổi sang `ObjectId`. Khi viết query raw BSON, sử dụng `_id` dạng String như schema này; khi dùng typed Spring Data `Criteria.where("id")`, mapping có thể chuyển sang `_id` tương ứng.

### 11.3. Thiết kế entity vùng riêng

Nếu vùng được lưu bền vững:

~~~json
{
  "_id": "area-a1",
  "tenantId": "tenant-a",
  "status": "ACTIVE",
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [106.66, 10.74],
        [106.74, 10.74],
        [106.74, 10.82],
        [106.66, 10.82],
        [106.66, 10.74]
      ]
    ]
  }
}
~~~

Đừng dùng chung field `location` của cửa hàng Point với field `geometry` của vùng mà không rõ type. Hai collection có thể có chiến lược index/query khác nhau; mỗi geometry cần validation topology theo vai trò của nó.

## 12. MongoTemplate query bằng BSON rõ ràng

Với truy vấn Polygon phức tạp (đặc biệt có holes, MultiPolygon), có thể viết `$geoWithin` qua `BasicQuery` với BSON rõ. Điều này tránh phụ thuộc vào giả định rằng mọi biến thể geometry đều có một convenience method giống nhau trên mọi dòng Spring Data.

**GeoAreaService.java**

~~~java
package com.example.geo;

import java.util.List;
import java.util.Objects;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import org.springframework.stereotype.Service;

@Service
public class GeoAreaService {

    private final MongoTemplate mongo;

    public GeoAreaService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<GeoOutlet> findInside(
            String authenticatedTenantId, Document inputPolygon) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant không hợp lệ");
        }

        Document polygon = validatedPolygon(inputPolygon);

        Document geometryFilter = new Document(
                "$geoWithin",
                new Document("$geometry", polygon));

        Document bsonQuery = new Document(
                "tenantId", authenticatedTenantId)
                .append("status", "ACTIVE")
                .append("location", geometryFilter);

        BasicQuery query = new BasicQuery(bsonQuery);
        query.with(Sort.by(Sort.Direction.ASC, "id"));
        query.limit(100);

        return mongo.find(query, GeoOutlet.class);
    }

    public static Document rectangle() {
        return Document.parse("""
            {
              "type": "Polygon",
              "coordinates": [[
                [106.66, 10.74],
                [106.74, 10.74],
                [106.74, 10.82],
                [106.66, 10.82],
                [106.66, 10.74]
              ]]
            }
            """);
    }

    /**
     * Chỉ xác minh cấu trúc/range/toạ độ đóng vòng.
     * KHÔNG thay thế kiểm tra GIS topology đầy đủ.
     */
    public static Document validatedPolygon(Document candidate) {
        if (candidate == null
                || !"Polygon".equals(candidate.getString("type"))
                || !(candidate.get("coordinates") instanceof List<?> rings)
                || rings.isEmpty() || rings.size() > 8) {
            throw new IllegalArgumentException(
                    "Geometry phải là Polygon có 1..8 rings");
        }

        for (Object ringObject : rings) {
            if (!(ringObject instanceof List<?> positions)
                    || positions.size() < 4
                    || positions.size() > 512) {
                throw new IllegalArgumentException("Vòng không hợp lệ");
            }
            for (Object positionObject : positions) {
                if (!(positionObject instanceof List<?> position)
                        || position.size() != 2
                        || !(position.get(0) instanceof Number lonNumber)
                        || !(position.get(1) instanceof Number latNumber)) {
                    throw new IllegalArgumentException(
                            "Tọa độ phải là [longitude, latitude]");
                }
                double lon = lonNumber.doubleValue();
                double lat = latNumber.doubleValue();
                if (!Double.isFinite(lon) || !Double.isFinite(lat)
                        || lon < -180 || lon > 180
                        || lat < -90 || lat > 90) {
                    throw new IllegalArgumentException(
                            "Tọa độ ngoài phạm vi");
                }
            }
            if (!Objects.equals(
                    positions.get(0),
                    positions.get(positions.size() - 1))) {
                throw new IllegalArgumentException(
                        "Vòng chưa đóng");
            }
        }

        // Không giữ các key do client đưa vào (vd $-operator).
        // Chỉ sao chép hai thuộc tính geometry đã được kiểm tra.
        return new Document("type", "Polygon")
                .append("coordinates", rings);
    }
}
~~~

### 12.1. Điều gì đã được bảo vệ?

- `tenantId` lấy từ tham số **đã được xác thực/ủy quyền** ở application boundary.
- `status = ACTIVE` tránh trả cửa hàng đã ngừng hoạt động.
- `location` được query bằng `$geoWithin/$geometry` trong cùng BSON filter.
- Input geometry chỉ được phép là Polygon, tối đa 8 rings và 512 positions/ring ở ví dụ.
- Mỗi position có hai số hữu hạn, longitude/latitude trong phạm vi.
- Các rings phải có đầu/cuối trùng nhau.
- Query giới hạn tối đa 100 kết quả và có sort ổn định theo ID.

**Phần chưa bảo vệ:** topology hình học hoàn chỉnh, hole hợp lệ, winding, antimeridian, phân quyền thực tế của tenant và độ chính xác GPS. Những điểm này thuộc các lớp validation/bảo mật khác.

### 12.2. Không đưa $-operators từ input thẳng vào query

Một API nhận raw JSON rồi gắn cả `Document` đó vào query có thể vô tình cho phép các operator không mong muốn. Ví dụ trên chỉ chấp nhận keys `type` và `coordinates`, rồi tự xây cấu trúc `$geoWithin`. Tuy nhiên khi input lớn/phức tạp, cần thêm giới hạn kích thước HTTP payload, JSON depth, tổng số vertices và CPU khi parse/validate.

### 12.3. Không dùng Doc parser để “xác thực topology”

`Document.parse(...)` chỉ đọc JSON/BSON hợp lệ. Một Polygon tự cắt nhưng đúng cú pháp vẫn có thể parse được. Các bước kiểm tra như “hole nằm trong outer”, “vòng không tự cắt” và quy tắc antimeridian phải được xử lý bằng geometry validation phù hợp trước khi chấp nhận vùng mới.

### 12.4. Loại kết quả không cho biết điểm cách biên bao nhiêu

`findInside` trả `List<GeoOutlet>` matching Polygon. Nó không trả:

- Khoảng cách ngắn nhất tới ranh giới.
- Độ chính xác tọa độ GPS.
- Phần trăm diện tích giao.
- Giải thích một điểm trên cạnh là trong hay ngoài.

Khi cần các giá trị đó, phải bổ sung phép đo geodesic/topological riêng, không tự tính từ số document match.

## 13. Spring Data Criteria và GeoJsonPolygon

Với polygon đơn giản, Spring Data cung cấp các lớp hình học để viết typed query.

~~~java
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.geo.GeoJsonPolygon;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

GeoJsonPolygon polygon = new GeoJsonPolygon(
        new Point(106.66, 10.74),
        new Point(106.74, 10.74),
        new Point(106.74, 10.82),
        new Point(106.66, 10.82),
        new Point(106.66, 10.74));

Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("ACTIVE")
                .and("location").within(polygon));

List<GeoOutlet> inside = mongo.find(
        query, GeoOutlet.class);
~~~

Đoạn này minh họa usage với `GeoJsonPolygon`, `Criteria.within(...)` và `MongoTemplate` ở dòng API hỗ trợ. `mongo` là biến `MongoTemplate` trong service. Điểm bắt đầu bằng kinh độ rồi vĩ độ — **không phải** constructor `Point(latitude, longitude)`.

### 13.1. Khi nào dùng typed geometry, khi nào dùng BSON?

| Tình huống | Lựa chọn |
|---|---|
Polygon đơn giản, kiểu dữ liệu tường minh | `GeoJsonPolygon` + `Criteria.within` |
Geometry động có holes, MultiPolygon hoặc được trao đổi giữa GIS systems | BSON `$geometry` đã validate hoặc API shape đúng version |
Muốn giải thích chính xác MongoDB operator | Raw query/BSON giúp đối chiếu với `mongosh` |
Query có nhiều điều kiện business | `Criteria`/`Query` hoặc `BasicQuery` có validation |
Muốn hỗ trợ thêm geometry mới | Thêm type whitelist, validation và tests theo geometry |

Không coi typed API và raw BSON là hai semantics khác nhau nếu chúng sinh **cùng một query BSON**. Khác biệt chủ yếu là cách diễn đạt, mapping và kiểm soát input ở Spring layer.

### 13.2. Tên field trong Criteria và BSON

Trong `Criteria.where("location")`, `"location"` là property Java của `GeoOutlet` và cũng là BSON field trong schema ví dụ. Nếu entity khai báo `@Field("geo_location")`, typed Spring Data mapping có thể map property `location` sang BSON `geo_location`. Với raw driver `Document`, phải dùng **tên BSON thực**.

Test quan sát raw BSON giúp phát hiện mapping sai trước khi debug geospatial mathematics.

## 14. Chiều truy vấn ngược: tìm vùng chứa một điểm

Giả sử MongoDB lưu `service_areas`, mỗi document có `geometry: Polygon`. Một input Point cần được so với các vùng đã lưu.

~~~javascript
db.service_areas.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.70, 10.78]
      }
    }
  }
});
~~~

Ý tưởng: geometry của vùng có giao với Point đầu vào. Query loại này có thể dùng `2dsphere` index trên `service_areas.geometry` khi được tạo phù hợp:

~~~javascript
db.service_areas.createIndex(
  { tenantId: 1, geometry: "2dsphere" },
  { name: "idx_area_tenant_geometry" }
);
~~~

### 14.1. Đừng đảo nhầm toán tử khi đổi hướng dữ liệu

Hai câu hỏi:

1. “Liệt kê các `GeoOutlet.location Point` trong `Polygon` input”.
2. “Liệt kê các `ServiceArea.geometry Polygon` chứa/giao với `Point` input”.

Không cùng chiều query field, và không nhất thiết cùng toán tử. Khi vùng có holes, boundaries hay MultiPolygon, test theo mục tiêu thật: **chọn điểm** hay **chọn vùng**.

### 14.2. Nhiều vùng khớp một điểm

Một điểm có thể giao với nhiều vùng thuộc cùng tenant. Nếu API cần một vùng duy nhất, nên có:

~~~text
match zones
  -> apply business priority
  -> tie-breaker stable zone ID
  -> return selected zone + reason
~~~

Không dùng thứ tự cursor mặc định của MongoDB làm priority. Nếu chính sách không cho phép vùng overlap, cần phát hiện overlap khi tạo/cập nhật polygons, không chỉ khi query.

## 15. Bảo mật và hiệu lực vùng

Một geofence thường được dùng để **xác định điều kiện nghiệp vụ**, không phải cơ chế authentication. Các invariant cần có:

- `tenantId` lấy từ identity/access policy, không tin tenant tùy ý client gửi.
- Vùng có trạng thái `ACTIVE`/`DRAFT`/`RETIRED` và thời điểm hiệu lực nếu nghiệp vụ cần.
- Nếu một vùng thay đổi sau khi đơn được tạo, cần lưu `regionVersion`/snapshot hoặc business decision ID để đối soát.
- Tọa độ do người dùng gửi có thể bị giả mạo; geospatial match không chứng minh user hiện diện vật lý.
- Nếu xét vùng quyết định phí/thuế/quyền, cần log input geometry version, timestamp, policy và lý do quyết định, nhưng tránh ghi dữ liệu vị trí nhạy cảm không cần thiết.

### 15.1. Query đúng hình học vẫn có thể sai nghiệp vụ

Ví dụ một cửa hàng `tenant-b` nằm bên trong Polygon của tenant-a. Nếu query chỉ chứa `location: {$geoWithin: ...}` mà không có `tenantId`, kết quả hình học đúng nhưng **rò dữ liệu tenant khác**.

Tương tự, một cửa hàng đã `INACTIVE` vẫn nằm trong Polygon; nếu thiếu filter `status`, API có thể đề xuất địa điểm ngừng phục vụ.

### 15.2. Không tự tin vào input Polygon không giới hạn

Một request có hàng triệu vertices có thể tốn CPU, memory và tạo tải server bất thường. Đặt giới hạn:

~~~text
request size
  + geometry type whitelist
  + max rings/polygons
  + max points
  + topological validity check
  + tenant ownership
  + query timeout/limit
~~~

Chính sách ở ví dụ `validatedPolygon` chỉ là **validation cấu trúc tối thiểu**; với vùng sản xuất nên chuẩn hóa geometry trước, giới hạn độ phức tạp và có thể cache những vùng đã được chấp nhận.

## 16. Thiết kế ma trận tọa độ và kỳ vọng kiểm thử

Để tránh viết test dựa trên một vài điểm dễ chọn, cần xác định **nhóm vị trí** và kỳ vọng trước khi viết Java. Với vùng thử nghiệm:

| Nhóm | Case ID | Tọa độ [lon,lat] | Kỳ vọng |
|---|---|---|---|
Inside rõ | `inside` | `[106.700,10.780]` | Match |
Outside rõ | `outside` | `[106.760,10.780]` | Không match |
Trong gần biên tây | `west-in` | `[106.662,10.780]` | Match |
Ngoài gần biên tây | `west-out` | `[106.658,10.780]` | Không match |
Trong gần góc tây nam | `corner-in` | `[106.662,10.742]` | Match |
Ngoài gần góc tây nam | `corner-out` | `[106.658,10.738]` | Không match |
Trên cạnh tây | `edge` | `[106.660,10.780]` | Ghi nhận, không áp đặt |
Tại đỉnh tây nam | `vertex` | `[106.660,10.740]` | Ghi nhận, không áp đặt |
Thuộc tenant khác | `foreign-tenant` | `[106.700,10.780]` | Không trả khi lọc tenant-a |
INACTIVE trong vùng | `inactive` | `[106.700,10.780]` | Không trả nếu filter ACTIVE |
Trong hole | `hole-in` | `[106.699,10.780]` | Không match với Polygon có hole |
Ngoài hole, trong outer | `hole-out` | `[106.675,10.780]` | Match với Polygon có hole |

`inside` nằm trong Polygon đơn nhưng cũng nằm **bên trong lỗ** nếu bổ sung hole ở mục 6. Không được kỳ vọng cùng một điểm luôn match hai vùng có cấu trúc khác nhau.

### 16.1. Test rõ trong/ngoài trước test đúng đường biên

Với polygon nhỏ và đúng topology:

~~~text
Rõ trong                   -> true
Rõ ngoài                   -> false
Ngay phía trong            -> true
Ngay phía ngoài            -> false
Trong hole                 -> false
Ngoài hole, trong outer    -> true
Sai tenant                 -> không xuất hiện
INACTIVE                   -> không xuất hiện
~~~

Đây là các assertions có ý nghĩa ổn định hơn việc ép điểm **chính xác trên cạnh** có một kết quả không được định nghĩa trong hợp đồng của hệ thống.

### 16.2. Test gần đường biên phải có business policy

Nếu sản phẩm yêu cầu vùng bất định, có thể định nghĩa:

~~~text
raw MongoDB geometry match
    + khoảng cách geodesic tới boundary
    + bán kính sai số GPS
    + version của vùng/policy
    -> INSIDE / OUTSIDE / UNCERTAIN
~~~

MongoDB `$geoWithin` không tự tính khoảng cách ngắn nhất tới biên hay sai số GPS. Một policy “sát biên 15 mét” phải có phép đo bằng mét và quy tắc riêng; không suy ra trực tiếp từ boolean match.

### 16.3. Không hard-code inclusion trên exact boundary khi chưa xác minh

Test sau là một giả định không an toàn nếu contract chưa quy định:

~~~java
// Tránh đưa điều này thành mặc định cho mọi GeoJSON/driver:
assertThat(ids).contains("edge");
~~~

Nên ghi nhận outcome edge/vertex riêng trong báo cáo kiểm thử trên MongoDB version cụ thể; assertion cứng tập trung vào những điểm nằm **cách biên rõ ràng**. Nếu sản phẩm phải xử lý chính xác boundary, bổ sung boundary classification có tests độc lập.

## 17. Integration test trên MongoDB thật

Mock `MongoTemplate` không thể xác minh server hiểu GeoJSON Polygon, hole và spherical index như mong đợi. Cần MongoDB test thực (ví dụ Testcontainers hoặc database test chạy riêng).

Spring Boot `@DataMongoTest` tạo test slice, **không tự khởi động MongoDB server**. Trước khi chạy, cung cấp URI tới MongoDB test được cô lập. Các lệnh `remove`/`insert` sau đây không được dùng với database production.

### 17.1. Seed các điểm có kỳ vọng

**GeoAreaServiceIntegrationTest.java**

~~~java
package com.example.geo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(GeoAreaService.class)
class GeoAreaServiceIntegrationTest {

    @Autowired MongoTemplate mongo;
    @Autowired GeoAreaService service;

    private GeoOutlet outlet(
            String id, String tenant,
            String status, double lon, double lat) {
        return new GeoOutlet(
                id, tenant, status, "Điểm " + id,
                new GeoJsonPoint(lon, lat));
    }

    @BeforeEach
    void seed() {
        // Chỉ thao tác trên database test độc lập.
        mongo.remove(new Query(), GeoOutlet.class);

        // Tạo index rõ ràng, không phụ thuộc auto-index.
        mongo.getCollection("geo_outlets")
                .createIndex(new Document("location", "2dsphere"));

        List<GeoOutlet> fixtures = List.of(
                outlet("inside", "tenant-a", "ACTIVE",
                        106.700, 10.780),
                outlet("outside", "tenant-a", "ACTIVE",
                        106.760, 10.780),
                outlet("west-in", "tenant-a", "ACTIVE",
                        106.662, 10.780),
                outlet("west-out", "tenant-a", "ACTIVE",
                        106.658, 10.780),
                outlet("corner-in", "tenant-a", "ACTIVE",
                        106.662, 10.742),
                outlet("corner-out", "tenant-a", "ACTIVE",
                        106.658, 10.738),
                outlet("edge", "tenant-a", "ACTIVE",
                        106.660, 10.780),
                outlet("vertex", "tenant-a", "ACTIVE",
                        106.660, 10.740),
                outlet("foreign-tenant", "tenant-b", "ACTIVE",
                        106.700, 10.780),
                outlet("inactive", "tenant-a", "INACTIVE",
                        106.700, 10.780),
                outlet("hole-out", "tenant-a", "ACTIVE",
                        106.675, 10.780),
                outlet("hole-in", "tenant-a", "ACTIVE",
                        106.699, 10.780)
        );

        for (GeoOutlet point : fixtures) {
            mongo.insert(point);
        }
    }

    private Set<String> insideIds(Document polygon) {
        return service.findInside("tenant-a", polygon)
                .stream()
                .map(GeoOutlet::id)
                .collect(Collectors.toSet());
    }

    @Test
    void clearlyInsideOutsideAndNearEdgeAreClassified() {
        Set<String> ids = insideIds(GeoAreaService.rectangle());

        assertThat(ids)
                .contains("inside", "west-in", "corner-in")
                .doesNotContain("outside", "west-out", "corner-out");
    }

    @Test
    void tenantAndStatusAreFilteredWithGeometry() {
        Set<String> ids = insideIds(GeoAreaService.rectangle());
        assertThat(ids)
                .contains("inside")
                .doesNotContain("foreign-tenant", "inactive");
    }

    @Test
    void exactEdgeAndVertexAreObservedNotAssumed() {
        Set<String> ids = insideIds(GeoAreaService.rectangle());

        assertThat(ids).contains("inside");
        assertThat(ids).doesNotContain("outside");

        // Diagnostic cho version MongoDB của môi trường test.
        System.out.printf(
                "GeoJSON boundary outcome: edge=%s, vertex=%s%n",
                ids.contains("edge"),
                ids.contains("vertex"));
    }

    @Test
    void aHoleExcludesItsInterior() {
        Document polygonWithHole = Document.parse("""
            {
              "type": "Polygon",
              "coordinates": [
                [
                  [106.66, 10.74],
                  [106.74, 10.74],
                  [106.74, 10.82],
                  [106.66, 10.82],
                  [106.66, 10.74]
                ],
                [
                  [106.69, 10.77],
                  [106.69, 10.79],
                  [106.71, 10.79],
                  [106.71, 10.77],
                  [106.69, 10.77]
                ]
              ]
            }
            """);

        Set<String> ids = insideIds(polygonWithHole);
        assertThat(ids)
                .contains("hole-out", "west-in")
                .doesNotContain("inside", "hole-in", "outside");
    }

    @Test
    void invalidLatitudeAndOpenRingAreRejected() {
        Document badLatitude = Document.parse("""
            {
              "type": "Polygon",
              "coordinates": [[
                [106.66, 10.74],
                [106.74, 10.74],
                [106.74, 106.82],
                [106.66, 10.74]
              ]]
            }
            """);

        assertThatThrownBy(() ->
                GeoAreaService.validatedPolygon(badLatitude))
                .isInstanceOf(IllegalArgumentException.class);

        Document openRing = Document.parse("""
            {
              "type": "Polygon",
              "coordinates": [[
                [106.66, 10.74],
                [106.74, 10.74],
                [106.74, 10.82],
                [106.66, 10.82]
              ]]
            }
            """);

        assertThatThrownBy(() ->
                GeoAreaService.validatedPolygon(openRing))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

### 17.2. Đọc đúng ý nghĩa bài test

`exactEdgeAndVertexAreObservedNotAssumed` **không tuyên bố** server luôn include hoặc exclude điểm đúng trên ranh giới; đó là diagnostic giúp nắm hành vi của phiên bản đang dùng. Nếu sản phẩm cần quyết định theo boundary tolerance, hãy kiểm tra policy ở một lớp riêng và thêm acceptance tests.

### 17.3. Tách test topology/geometry khỏi test business

Test geospatial nhằm chứng minh MongoDB thực hiện đúng query với fixtures. Test policy nhằm chứng minh các tình huống near-boundary được phân loại theo yêu cầu nghiệp vụ. Không để một test mang giả định mơ hồ thay cho cả hai.

### 17.4. Database phải được cô lập

`mongo.remove(new Query(), GeoOutlet.class)` xóa toàn bộ dữ liệu collection đích. Không chạy trên production hoặc database dùng chung. Nếu test song song, cần collection/database riêng để tránh fixture bị xóa bởi test khác.

## 18. Xác minh raw BSON và index trên MongoDB test

Khi `$geoWithin` trả rỗng bất ngờ, kiểm tra MongoDB thực sự lưu **GeoJSON Point**, thay vì đoán rằng hình học sai.

### 18.1. Kiểm tra thứ tự kinh/vĩ độ trong raw document

Thêm method vào `GeoAreaServiceIntegrationTest`:

~~~java
@Test
void mappedLocationIsGeoJsonWithLongitudeFirst() {
    Document raw = mongo.getCollection("geo_outlets")
            .find(new Document("_id", "inside"))
            .first();

    assertThat(raw).isNotNull();
    Document location = raw.get("location", Document.class);
    assertThat(location).isNotNull();
    assertThat(location.getString("type")).isEqualTo("Point");

    List<?> coordinates =
            location.getList("coordinates", Object.class);
    assertThat(coordinates).hasSize(2);

    assertThat(((Number) coordinates.get(0)).doubleValue())
            .isEqualTo(106.7);
    assertThat(((Number) coordinates.get(1)).doubleValue())
            .isEqualTo(10.78);
}
~~~

Nếu `coordinates[0] = 10.78` và `coordinates[1] = 106.7`, dữ liệu đã bị đảo thứ tự và latitude không hợp lệ; cần sửa dữ liệu/mapping đầu vào trước khi kiểm tra toán tử địa lý.

### 18.2. Xác minh index thật

~~~java
@Test
void twoDSphereIndexExists() {
    List<Document> indexes = mongo
            .getCollection("geo_outlets")
            .listIndexes()
            .into(new java.util.ArrayList<>());

    assertThat(indexes).anySatisfy(index -> {
        Document key = index.get("key", Document.class);
        assertThat(key).isNotNull();
        assertThat(key.getString("location"))
                .isEqualTo("2dsphere");
    });
}
~~~

Test này chỉ xác nhận **index metadata** có key `location: "2dsphere"`. Nó không chứng minh query planner chọn index cho mọi query. Phải dùng `explain("executionStats")` với data volume đại diện.

### 18.3. Đối chiếu BSON query trong mongosh

~~~javascript
db.geo_outlets.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.66, 10.74],
          [106.74, 10.74],
          [106.74, 10.82],
          [106.66, 10.82],
          [106.66, 10.74]
        ]]
      }
    }
  }
});
~~~

Nếu raw query trả điểm nhưng Spring Data query không trả, kiểm tra:

- MongoTemplate đang kết nối đúng database/collection hay không.
- Entity `@Document(collection = "geo_outlets")` có đúng.
- `@Field`/`@MongoId` và converter có ánh xạ đúng.
- Tenant/status được truyền đúng.
- Mã đang dùng Polygon hay một geometry khác.
- JSON number precision và ring closure.

## 19. Kiểm thử MultiPolygon và chiều query ngược

`GeoAreaService.validatedPolygon` ở mục 12 chỉ chấp nhận `Polygon` để giới hạn input endpoint. Muốn kiểm thử `MultiPolygon`, có thể chạy BSON query nội bộ trên fixture riêng mà **không** tự mở rộng API public.

### 19.1. MultiPolygon với hai mảng rời

~~~java
import org.springframework.data.mongodb.core.query.BasicQuery;

Document multiPolygon = Document.parse("""
    {
      "type": "MultiPolygon",
      "coordinates": [
        [[
          [106.66, 10.74],
          [106.74, 10.74],
          [106.74, 10.82],
          [106.66, 10.82],
          [106.66, 10.74]
        ]],
        [[
          [106.80, 10.74],
          [106.84, 10.74],
          [106.84, 10.78],
          [106.80, 10.78],
          [106.80, 10.74]
        ]]
      ]
    }
    """);

// Seed thêm điểm ở cụm thứ hai và khoảng trống giữa hai cụm
// TRƯỚC khi truy vấn.
mongo.insert(outlet("second-zone", "tenant-a",
        "ACTIVE", 106.82, 10.76));
mongo.insert(outlet("between-zones", "tenant-a",
        "ACTIVE", 106.77, 10.76));

Document filter = new Document("tenantId", "tenant-a")
        .append("status", "ACTIVE")
        .append("location", new Document(
                "$geoWithin",
                new Document("$geometry", multiPolygon)));

List<GeoOutlet> matches = mongo.find(
        new BasicQuery(filter), GeoOutlet.class);

Set<String> ids = matches.stream()
        .map(GeoOutlet::id)
        .collect(Collectors.toSet());

assertThat(ids).contains("second-zone");
assertThat(ids).doesNotContain("between-zones");
~~~

Đoạn code là fragment của `GeoAreaServiceIntegrationTest`, dùng `mongo`, helper `outlet` và imports tương ứng. **Seed trước khi query** để biến `matches` phản ánh cả hai nhóm. Nếu tách snippet thành một test method mới, cần import `BasicQuery` và kiểm tra collection/database test được cô lập.

### 19.2. Test vùng chứa Point

Khi collection lưu Polygon và nhận query Point, chiều đối sánh thường là:

~~~javascript
db.service_areas.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.70, 10.78]
      }
    }
  }
});
~~~

Phải có geometry/`2dsphere` index phù hợp trên `service_areas.geometry` và kiểm tra trường hợp point nằm trong hole, vùng chồng lấp hoặc đúng biên.

### 19.3. Một Point có thể thuộc hai vùng

Nếu hai zones giao nhau, query có thể trả **hai document vùng**. Business policy cần quyết định:

~~~text
matched zones: [zone-a, zone-b]
select by: active + priority DESC + stable zoneId ASC
~~~

Không mặc nhiên chọn phần tử đầu tiên của cursor. Nếu yêu cầu hai vùng không được overlap, kiểm tra topology trước khi publish vùng mới.

### 19.4. Không coi missing location là outside đã được xác minh

Một document không có `location` có thể bị bỏ qua bởi geospatial predicate/index. Nhưng nó không phải dữ liệu “tọa độ đã biết và nằm ngoài vùng”.

Một API cần phân biệt:

- `INSIDE_REGION`: tọa độ hợp lệ match.
- `OUTSIDE_REGION`: tọa độ hợp lệ không match.
- `MISSING_LOCATION`: chưa có tọa độ.
- `INVALID_LOCATION`: tọa độ không hợp lệ hoặc đã bị từ chối.
- `UNCERTAIN`: độ chính xác/tolerance khiến quyết định chưa chắc chắn.

Một query `$geoWithin` chỉ trả tập match, không trực tiếp trả lý do mọi document còn lại bị loại.

## 20. Khoảng cách tới biên và kiểm thử với sai số GPS

Nếu sản phẩm cần biết “địa điểm cách biên dưới 15 m”, không dùng công thức:

~~~java
// Anti-pattern: sai với nhiều vĩ độ và cạnh nghiêng/hole.
boolean isNearBoundary =
        Math.abs(longitude - westEdgeLongitude) < 0.00015;
~~~

Thứ này đo chênh lệch kinh độ **đơn vị độ**, không phải khoảng cách ngắn nhất tới toàn boundary **đơn vị mét**. Nó bỏ qua những cạnh nghiêng, vòng lỗ, khu vực gần cực và hệ quy chiếu.

### 20.1. Chính sách ba trạng thái

| Điều kiện đã được xác minh | Quyết định |
|---|---|
Rõ trong vùng và cách mọi biên hơn tolerance | `INSIDE` |
Rõ ngoài vùng và cách mọi biên hơn tolerance | `OUTSIDE` |
Điểm sát biên hoặc bán kính sai số vị trí quá lớn | `UNCERTAIN` |

MongoDB `$geoWithin` giúp chọn ứng viên hình học. Khoảng cách ngắn nhất tới ranh giới không được `$geoWithin` tự trả. Muốn phân loại `UNCERTAIN`, cần:

1. Phép đo geodesic/geometry đúng với hệ quy chiếu và Polygon.
2. Accuracy radius/timestamp/nguồn của vị trí.
3. Chính sách tolerance theo mét và quy tắc xử lý hole.
4. Version của vùng và version của policy.
5. Cách phản hồi khi thiếu bằng chứng: từ chối, kiểm tra lại hoặc chuyển duyệt thủ công.

### 20.2. Tách unit test policy khỏi integration test MongoDB

Ví dụ dữ liệu test business classifier:

~~~text
Given:
  distanceToBoundaryMeters = 7
  accuracyMeters = 10
  toleranceMeters = 15

When:
  apply policy version v3

Then:
  UNCERTAIN
~~~

Trong unit test policy, có thể dùng một distance input đã được tính chính xác bởi geometry service. Integration test GIS riêng xác minh thuật toán tính khoảng cách. Không giả định một kết quả `$geoWithin` cung cấp trực tiếp `distanceToBoundaryMeters`.

### 20.3. Độ chính xác qua serialize/deserialize

Một điểm ở đúng biên có thể thay đổi kết quả khi định dạng/rounding khác giữa mobile JSON, Spring API, storage và GIS renderer. Cần kiểm tra:

- Round-trip JSON của tọa độ.
- Parse thành `double` hoặc kiểu số đã quy định.
- Cách lưu BSON của `GeoJsonPoint`.
- Cách xuất điểm sang UI và nhận lại.
- Sai số thực của thiết bị; không ngụy tạo độ chính xác bằng số chữ số thập phân.

Đừng dùng chính xác một điểm đang hiển thị trên ảnh bản đồ làm golden truth nếu ảnh dùng phép chiếu và làm tròn khác với GeoJSON.

### 20.4. Sai số không đồng nghĩa hành vi gian lận

GPS có sai số hoặc điểm nằm sát biên là một **trạng thái bất định**, không tự chứng minh client giả mạo tọa độ. Nếu một hệ thống an ninh cần chống spoofing, phải có biện pháp xác minh độc lập và chính sách dữ liệu vị trí/privacy thích hợp.

## 21. Hiệu năng: explain, index và giới hạn kết quả

Một truy vấn hình học đúng vẫn có thể chậm khi số địa điểm lớn hoặc polygons phức tạp.

### 21.1. Giải thích executionStats trên truy vấn đại diện

~~~javascript
db.geo_outlets.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.66, 10.74],
          [106.74, 10.74],
          [106.74, 10.82],
          [106.66, 10.82],
          [106.66, 10.74]
        ]]
      }
    }
  }
}).limit(100).explain("executionStats");
~~~

Quan sát:

- `queryPlanner.winningPlan` và geospatial index/stages được dùng.
- `totalKeysExamined` và `totalDocsExamined`.
- `nReturned`.
- `executionTimeMillis` (trên hệ thống/test tải đại diện).
- Index build/write overhead, số vùng/đỉnh.

Không tự điền một con số “10x nhanh hơn” nếu chưa benchmark. Một vùng chứa gần hết dữ liệu có thể trả nhiều document dù đã có index. Một Polygon phức tạp có hàng nghìn vertices có thể tạo chi phí tính toán cao hơn vùng đơn giản.

### 21.2. Limit và sort có vai trò riêng

`query.limit(100)` trong `GeoAreaService` giới hạn số document trả về; nó không bảo đảm 100 địa điểm “tốt nhất” nếu chưa định nghĩa tiêu chí sort. Bài dùng `id ASC` làm thứ tự ổn định cho tập ít thay đổi. Nếu cần “gần khách nhất”, phải tính thêm khoảng cách/sắp xếp theo yêu cầu riêng; `$geoWithin` không tự sort theo khoảng cách.

### 21.3. Keyset paging và dữ liệu cập nhật đồng thời

Nếu có hàng chục nghìn cửa hàng trong vùng, không tải hết vào `List`. Có thể dùng keyset cursor theo `_id` hoặc một khóa sắp xếp ổn định; nhưng khi document di chuyển hoặc bị xóa/thêm đồng thời, các trang không tự đại diện cho một snapshot bất biến.

Đối với báo cáo cần snapshot nhất quán, định nghĩa read concern/session/transaction hoặc batch versioning tùy yêu cầu. Đừng cố đạt snapshot consistency chỉ bằng một `sort(id)`.

### 21.4. Compound index cần được benchmark

Chỉ số:

~~~javascript
{ tenantId: 1, status: 1, location: "2dsphere" }
~~~

có thể hợp lý với query có cả tenant, status và geometry, nhưng không chắc tốt hơn index `{location:"2dsphere"}` cho mọi distribution. Test với tenant lớn/nhỏ, ACTIVE/INACTIVE ratios khác nhau và Polygon nhỏ/lớn trước khi chọn chiến lược production.

## 22. Lỗi thường gặp khi đối sánh vùng và kiểm thử biên

| Biểu hiện hoặc sai lầm | Nguyên nhân có thể | Hướng kiểm tra/sửa |
|---|---|---|
Điểm trong vùng trên bản đồ nhưng query không match | Đảo lat/lon | Kiểm tra BSON `coordinates[0]=longitude` |
MongoDB từ chối tọa độ | Latitude ngoài ±90° hoặc number không hợp lệ | Validate từng position |
Polygon không match gì | Thiếu cấp lồng ring hoặc vòng chưa đóng | Kiểm tra `Polygon.coordinates` |
Vùng bị đảo sang phần khác địa cầu | Winding hoặc polygon quá lớn | Chuẩn hóa geometry, test spherical semantics |
Vùng có hình nơ | Ring tự cắt | GIS topology validation trước ingest |
Điểm trong hole vẫn match | Hole bị lưu thành polygon riêng | Đặt hole là ring tiếp theo của cùng Polygon |
MultiPolygon không nhận phần thứ hai | Sai cấp lồng mảng | Kiểm tra `MultiPolygon.coordinates` |
Một vùng vượt antimeridian bao gần toàn cầu | Dùng min/max longitude sai | Chuẩn hóa/chia vùng, test ±180° |
Hình trên Web Mercator khác GeoJSON | Nhầm projection và geometry | Quy đổi CRS và kiểm tra dữ liệu gốc |
Điểm trên cạnh trả kết quả bất ngờ | Boundary semantics và precision | Không hard-code nếu chưa có policy/test |
Hai vùng cùng trả một điểm biên | Chạm biên/overlap | Stable priority hoặc UNCERTAIN |
Tọa độ gần cạnh lúc đúng lúc sai | Precision/rounding, GPS accuracy | Khoảng cách tới biên và tolerance có đơn vị mét |
`$near` cho cửa hàng gần nhưng ngoài vùng | Nearest không phải within | `$geoWithin` với Polygon |
Bounding box match nhưng polygon không match | Vùng lõm/hole | Kiểm tra point-in-polygon thật |
Query trả cửa hàng tenant khác | Không có tenant filter | Tenant từ auth context trong BSON query |
Query trả điểm INACTIVE | Thiếu status predicate | Filter trạng thái tại database |
Annotation `@GeoSpatialIndexed` nhưng index không có | Auto-index chưa được bật/provision | List indexes và migration rõ |
Đã có index nhưng query vẫn chậm | Vùng lớn, filter thiếu index, polygon phức tạp | `explain("executionStats")`/benchmark |
`BasicQuery` trả khác typed `Criteria` | Khác query BSON/mapping field | Log command an toàn/đối chiếu raw BSON |
Đọc file JSON hợp lệ mà polygon sai | Parse không kiểm tra topology | GIS geometry validator |
API nhận Polygon với hàng triệu vertices | Thiếu limit/DoS guard | Max payload, rings, vertices, timeout |
Test Mockito pass, MongoDB thật trả khác | Mock không có spherical engine | Integration test với 2dsphere |
Test biên thất bại khi đổi version server | Assumption tại exact boundary | Định nghĩa policy, tách diagnostic |
`$geoWithin` trả rỗng nhưng không có location | Missing field khác outside | Data quality state riêng |
Đọc raw BSON ra Point sai loại | Mapper field type không đúng | Kiểm tra `GeoJsonPoint`, `@Document`, raw BSON |
Sort không ổn định giữa các lần gọi | Không có tie-breaker | Sort theo khóa duy nhất |
Count đúng nhưng trả một số cửa hàng không hợp lệ | Tenant/status hoặc policy ngoài geometry | Test toàn bộ filter |
Transaction/geofence state thay đổi giữa hai lần truy vấn | Không có region version/snapshot | Snapshot/version ở decision record |
Thử query tập dữ liệu production với delete/seed test | Kết nối sai database | Database test cô lập và URI guard |

### 22.1. Quy trình chẩn đoán một điểm bị phân loại sai

1. **Lấy tọa độ gốc** và nguồn dữ liệu; xác minh thứ tự lon/lat, đơn vị và CRS.
2. **Kiểm tra độ chính xác** GPS và thao tác rounding/serialization.
3. **Đọc raw BSON `location`** của document và xác minh GeoJSON Point.
4. **Đọc geometry vùng thực tế** và version; kiểm tra Polygon/MultiPolygon/hole/ring closure.
5. **Chạy cùng BSON query trong mongosh** với tenant/status như request thật.
6. **Ghi nhận trường hợp boundary** riêng nếu điểm nằm sát cạnh hoặc đỉnh.
7. **Kiểm tra 2dsphere index** và executionStats khi kết quả đúng nhưng chậm.
8. **Đối chiếu policy**: vùng có còn ACTIVE, user có quyền, geofence có tolerance?
9. **Kiểm tra các hệ khác**: mobile map projection, GIS import, geocoding.
10. **Tạo một regression fixture** với tọa độ và geometry version đã gây lỗi.

Không chỉ nhìn ảnh bản đồ và kết luận MongoDB sai; vị trí hiển thị có thể được bo tròn hoặc phép chiếu khác với dữ liệu đang query.

## 23. Thiết kế hệ thống quản lý vùng bền vững

Khi quản lý hàng nghìn vùng giao hàng, dữ liệu Polygon cần có vòng đời riêng:

~~~mermaid
flowchart TD
    A["GIS / admin tạo vùng"] --> B["Kiểm tra cấu trúc GeoJSON"]
    B --> C["Kiểm tra topology, winding, CRS"]
    C --> D["Kiểm tra tenant ownership + business rules"]
    D --> E["Lưu version vùng"]
    E --> F["Provision/index 2dsphere"]
    F --> G["Publish ACTIVE"]
    G --> H["Query điểm/đối sánh vùng"]
    H --> I["Boundary tolerance + accuracy policy"]
    I --> J["Decision + version + audit metadata"]
~~~

### 23.1. Lưu version vùng để đối soát

Ví dụ một document vùng:

~~~json
{
  "_id": "delivery-area-101",
  "tenantId": "tenant-a",
  "status": "ACTIVE",
  "revision": 12,
  "policyVersion": "2026-11",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[
      [106.66, 10.74],
      [106.74, 10.74],
      [106.74, 10.82],
      [106.66, 10.82],
      [106.66, 10.74]
    ]]
  }
}
~~~

Khi xử lý đơn hàng, lưu `areaId`, `revision`, `decision`, timestamp và request ID để có thể giải thích tại sao đơn được chấp nhận theo vùng **ở thời điểm đó**, kể cả khi admin thay đổi polygon một ngày sau.

### 23.2. Không lấy kết quả query làm audit history

Truy vấn `$geoWithin` hôm nay không nhất thiết tái tạo kết quả **hôm qua** nếu hình học vùng, điểm cửa hàng hoặc chính sách đã đổi. Muốn đối soát cần snapshot/version hoặc event log bền vững, có quyền đọc thích hợp.

### 23.3. Không lưu vị trí quá mức cần thiết

Vị trí có thể là dữ liệu nhạy cảm. Một hệ thống chỉ cần xác nhận “thuộc vùng giao hàng” có thể không cần giữ lịch sử GPS chính xác của khách hàng quá lâu. Cần phân biệt vị trí của **cửa hàng công khai** và vị trí của **người dùng cá nhân**, từ đó xác định retention, access control và audit logging phù hợp.

### 23.4. Xử lý thay đổi vùng đồng thời

Nếu admin cập nhật vùng trong khi khách hàng đặt hàng, có thể xảy ra:

~~~text
T0: đơn được kiểm tra theo region revision=11
T1: admin publish revision=12
T2: đơn được tạo nhưng không lưu revision đã dùng
~~~

Hệ thống không thể giải thích nhất quán tại sao đơn hợp lệ hay không. Có thể thiết kế quyết định gắn revision cố định, hoặc transaction/state machine phù hợp khi nhiều document phải thay đổi cùng nhau. Một phép query geospatial **không tự tạo snapshot cho toàn workflow**.

### 23.5. Tách geometry validation khỏi business validation

| Nhóm | Ví dụ |
|---|---|
Geometry | Ring đóng, không tự cắt, hole hợp lệ, winding, CRS |
Data ingestion | Kinh/vĩ độ đúng nguồn, không NaN, chuẩn hóa JSON |
Access control | Tenant sở hữu vùng, role được sửa/publish |
Business policy | ACTIVE, thời gian hiệu lực, priority, tolerance |
Persistence | Document mapping, unique ID, `2dsphere` index |
Operations | Monitoring, version, rollback/migration, backup |

Không đặt mọi thứ trong một callback Spring Data hoặc một method `containsPoint`. Những trách nhiệm độc lập cần test độc lập và một integration test xuyên pipeline.

## 24. Chiến lược kiểm thử từ unit đến production-like

Một bộ test hợp lý có nhiều tầng:

| Tầng | Nội dung | Công cụ |
|---|---|---|
Unit validation | Range lon/lat, ring closure, giới hạn vertices | JUnit/AssertJ |
Unit policy | Quyết định INSIDE/OUTSIDE/UNCERTAIN từ distance/accuracy đã tính | JUnit |
Geometry/topology | Holes, self-intersection, antimeridian, winding, distance geodesic | Thư viện GIS có hỗ trợ CRS phù hợp |
MongoDB integration | `$geoWithin`/`$geoIntersects` với GeoJSON, 2dsphere | MongoDB thật, `@DataMongoTest` |
Security integration | Tenant/status filter, quyền vùng | Spring Security + database test |
Contract/API | Lon/lat order, JSON DTO, error semantics | HTTP integration test |
Load/performance | Vùng lớn/nhỏ, số đỉnh, index, p95/CPU | Benchmark + `explain` |
Regression | Fixtures từ lỗi thực đã được làm sạch dữ liệu nhạy cảm | Versioned test fixtures |

### 24.1. Nhóm test tọa độ biên nên mở rộng

Ngoài đúng cạnh tây và góc tây nam trong ví dụ, nên test:

- Cạnh bắc, nam, đông và mỗi đỉnh.
- Điểm trong/ngoài **với offset hữu hạn** quanh từng cạnh.
- Một điểm gần lỗ, trong lỗ, trên mép lỗ.
- Hai polygon chồng nhau hoặc có cạnh chung.
- Một MultiPolygon có hai mảng rời và một điểm nằm giữa chúng.
- Vùng rất hẹp và vùng concave.
- Tọa độ sát ±180°, gần ±90°.
- Không có location, location sai loại hoặc dữ liệu legacy.
- Cùng điểm ở tenant-a/tenant-b.
- Vùng DRAFT/EXPIRED không được sử dụng cho quyết định ACTIVE.

Không cần ép mỗi test đơn vị phải chạy toàn bộ những biến thể này; gom thành bộ regression cho geometry và integration trên server.

### 24.2. Metamorphic tests với ràng buộc rõ

Một cách tăng chất lượng kiểm thử là áp dụng phép biến đổi **bảo toàn ý nghĩa hình học**:

- Thêm một điểm **nội thất** xa biên và kiểm tra vẫn match khi lưới test được mở rộng.
- Thêm một cửa hàng ngoài vùng và kiểm tra tập matching cũ không thay đổi.
- Thêm cửa hàng tenant-b cùng tọa độ và kiểm tra query tenant-a không lộ.
- Đổi `status` của cửa hàng từ ACTIVE sang INACTIVE và kiểm tra nó bị loại.
- Dùng cùng Polygon cho typed query và raw BSON query và so sánh các IDs (với MongoDB version hỗ trợ cả hai đường).

Không tự coi phép **đảo thứ tự tất cả vertices** hoặc **dịch toàn bộ polygon qua ±180°** là biến đổi bảo toàn semantics trong mọi hệ cầu. Chúng có thể thay winding/định nghĩa vùng và cần được đánh giá riêng.

### 24.3. Fail-fast cho geometry ingest

Input Polygon tự cắt, cực lớn, không đóng vòng hoặc chứa NaN nên bị từ chối ở bước nhập dữ liệu với lỗi có ý nghĩa, thay vì chỉ phát hiện trong lúc client đặt hàng. Nhưng đừng đánh đồng:

~~~text
malformed geometry -> HTTP 400 / validation error
no matching region -> business OUTSIDE_REGION
point near boundary -> business UNCERTAIN
MongoDB timeout -> infrastructure error / retry policy
wrong tenant -> authorization failure
~~~

Năm trạng thái trên có nguyên nhân và hướng xử lý khác nhau. Không dùng `onErrorResume` hoặc catch-all để biến mọi lỗi thành “ngoài vùng”.

## 25. Bài tập vận dụng

**Bài 1 — Thứ tự tọa độ.** Nhập `[106.70,10.78]` và `[10.78,106.70]`. Viết validator kiểm tra lon/lat; giải thích vì sao không tự đảo khi cả hai số cùng nằm trong phạm vi hợp lệ.

**Bài 2 — GeoJSON Polygon.** Tạo hình chữ nhật với bốn góc và điểm cuối lặp lại điểm đầu. Phân biệt cấu trúc `Polygon.coordinates` với `LineString.coordinates`.

**Bài 3 — $geoWithin.** Seed 6 cửa hàng có điểm inside/outside/near-edge. Viết MongoDB query và `MongoTemplate` service để lấy điểm trong vùng theo tenant-a và status ACTIVE.

**Bài 4 — GeoJsonPolygon typed.** Chuyển BSON query sang `GeoJsonPolygon` và `Criteria.within`. So sánh IDs và raw BSON query trên MongoDB test.

**Bài 5 — Cạnh và đỉnh.** Viết fixtures nằm trên mỗi cạnh và mỗi đỉnh, ghi kết quả MongoDB theo version. Giải thích vì sao các test này chưa thay business policy boundary.

**Bài 6 — Offset trong/ngoài.** Tạo hai điểm cách biên tây theo hai phía với offset hữu hạn, assert một match và một không. Tách khỏi test điểm exact-edge.

**Bài 7 — Polygon có hole.** Thêm lỗ hình chữ nhật, seed một điểm giữa lỗ và một điểm chỉ nằm trong outer ring; assert khác nhau.

**Bài 8 — MultiPolygon.** Tạo hai mảng rời nhau, seed 3 điểm: trong vùng một, trong vùng hai, giữa hai vùng. Dùng `$geoWithin` để kiểm tra.

**Bài 9 — $geoIntersects.** Lưu các service areas dưới dạng Polygon rồi tìm những vùng giao với một Point, kiểm tra trường hợp nhiều vùng cùng match.

**Bài 10 — Zone priority.** Thiết kế rule khi một điểm thuộc hai vùng: priority giảm dần, zone ID tăng dần. Test tie-breaking độc lập với thứ tự cursor.

**Bài 11 — Antimeridian.** Tạo một vùng đã được GIS xác nhận qua kinh tuyến ±180°, test điểm ở +179.x và −179.x, cùng một điểm ở 0°. Giải thích vì sao min/max longitude thông thường sai.

**Bài 12 — Vĩ độ cực.** Kiểm tra validator với latitude +90, −90 và giá trị nằm ngoài phạm vi. Đánh giá vì sao hình hộp 2D không tương đương spherical polygon gần cực.

**Bài 13 — Topology.** Tạo một Polygon tự cắt hoặc hole nằm ngoài outer ring. Chỉ ra vì sao `Document.parse` và kiểm tra ring closure không đủ; tích hợp validator GIS phù hợp.

**Bài 14 — Index.** Tạo `2dsphere` index ở field `location`, kiểm tra `listIndexes`. So sánh query executionStats khi index tồn tại và khi index không phù hợp.

**Bài 15 — Compound index.** Benchmark hai index `{location:"2dsphere"}` và `{tenantId:1,status:1,location:"2dsphere"}` theo dataset có nhiều tenant; không kết luận từ ví dụ 12 document.

**Bài 16 — Bảo mật tenant.** Seed cùng tọa độ cho tenant-a/tenant-b và một record INACTIVE; assert query tenant-a chỉ trả ACTIVE tenant-a. Test actor không được tự chọn tenant ID từ query string nếu chưa được authorize.

**Bài 17 — Missing vs outside.** Tạo một document thiếu location và một document có Point hợp lệ ngoài Polygon. Thiết kế API trả data quality reason khác nhau mà không gán cả hai thành OUTSIDE_REGION.

**Bài 18 — Location accuracy.** Mô phỏng point cách biên 7 m, accuracy radius 10 m, tolerance 15 m. Unit test business classifier trả UNCERTAIN mà không dùng phép so sánh chênh lệch longitude.

**Bài 19 — Concurrency và version.** Admin cập nhật region revision từ 11 sang 12 khi có đơn hàng đang kiểm tra. Thiết kế record lưu revision đã dùng và test khả năng đối soát quyết định sau này.

**Bài 20 — Regression test.** Xây fixture JSON versioned chứa inside, outside, boundary, holes, multipolygon, antimeridian và tenant cases. Tổ chức nhóm test nào dùng assertions cứng, nhóm nào chỉ quan sát server geometry behavior.

## 26. Ghi nhớ

**Đối sánh vùng địa lý trong MongoDB không chỉ là kiểm tra hai con số có nằm giữa min/max.** GeoJSON dùng thứ tự **[longitude, latitude]**, Polygon gồm các **vòng đóng**, MultiPolygon gồm nhiều polygon, và vùng có lỗ phải biểu diễn hole ở đúng cấp ring. Cần xác minh topology, winding, CRS, antimeridian và kích thước hình học trước khi chạy truy vấn quan trọng.

**`$geoWithin`** phù hợp khi tìm các `Point` nằm trong một `Polygon`; **`$geoIntersects`** phù hợp khi hỏi các geometry có giao nhau, chẳng hạn một document vùng `Polygon` với điểm truy vấn. `$near` trả lời bài toán khoảng cách gần điểm, không thay thế point-in-region. `2dsphere` index giúp truy vấn không gian có cơ hội hiệu quả hơn, nhưng cần provisioning thật và kiểm tra `explain("executionStats")`, không suy từ annotation.

**Đường biên phải là một phần của hợp đồng và bộ kiểm thử.** Assert chắc chắn cho điểm rõ trong, rõ ngoài và cách biên theo hai phía; ghi nhận riêng những điểm đúng trên cạnh/đỉnh hoặc mép hole. Nếu nghiệp vụ cần ngưỡng khoảng cách tới biên, hãy dùng phép đo phù hợp bằng **mét**, xét sai số GPS và trả trạng thái `UNCERTAIN` khi thiếu bằng chứng, thay vì ép một boolean hình học làm quyết định an toàn.

Cuối cùng, **geometry đúng không tự bảo đảm bảo mật hay tính nhất quán nghiệp vụ**. Query phải có tenant/status, vùng cần revision và policy rõ, input geometry phải được kiểm tra giới hạn/topology, và cả tọa độ, mapped BSON, index lẫn kết quả server phải được xác minh bằng integration test trên MongoDB thật. Các test sát biên cùng dữ liệu vùng/version phải được lưu làm regression fixtures trước khi triển khai production.
