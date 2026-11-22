# Chỉ mục không gian/vector và phạm vi sử dụng phù hợp

## 1. Vì sao NoSQL cần những chỉ mục chuyên biệt?

Trong chương **Chỉ mục và đường truy cập**, ta đã thấy một chỉ mục hữu ích khi nó giúp database tìm đúng tập bản ghi mà không phải quét toàn bộ dữ liệu. Với những điều kiện thông thường, một chỉ mục theo khóa hoặc thuộc tính có thể hỗ trợ:

- Tìm tài liệu có `productId = "P100"`.
- Lấy đơn hàng của `customerId = "U42"`.
- Lọc sự kiện trong khoảng `createdAt`.
- Sắp xếp theo `price` hoặc `updatedAt`.

Tuy nhiên, không phải câu hỏi nào cũng là so sánh bằng, lớn hơn hoặc nhỏ hơn trên một trường đơn lẻ.

Xét hai yêu cầu:

1. **Không gian:** “Tìm các điểm nhận hàng trong bán kính 3 km quanh vị trí người dùng, ưu tiên điểm gần nhất.”
2. **Ngữ nghĩa:** “Tìm các sản phẩm có mô tả gần nghĩa với câu *tai nghe đeo lâu không mỏi, cách âm tốt* dù không chứa đúng các từ ấy.”

Đối với yêu cầu thứ nhất, ta cần hiểu **tọa độ, khoảng cách và hình học**. Đối với yêu cầu thứ hai, ta cần hiểu **khoảng cách trong không gian vector nhiều chiều**. B-tree hoặc index theo một trường văn bản thông thường thường không đủ để đáp ứng hiệu quả cả hai.

Hai nhóm chỉ mục chuyên biệt:

- **Spatial/geospatial index:** tìm theo điểm, vùng, đường, đa giác và những quan hệ không gian.
- **Vector similarity index:** tìm các vector gần nhau theo một độ đo tương đồng hoặc khoảng cách, thường qua thuật toán approximate nearest neighbor (ANN).

Chúng giúp NoSQL phục vụ nhiều access pattern hơn, nhưng cũng có giới hạn. **Chỉ mục đúng loại không thay thế kiểm tra tính đúng của dữ liệu, quyền truy cập, trạng thái giao dịch hay định nghĩa nghiệp vụ.**

### 1.1. Mô hình minh họa

Một nền tảng giao hàng có:

~~~text
(:Store / document Store)
    storeId
    name
    location       -> tọa độ
    description    -> mô tả cửa hàng
    category
    isOpen
    tenantId

                    +------------------+
                    | Database nguồn   |
                    | Store / Catalog  |
                    +---------+--------+
                              |
               +--------------+--------------+
               |                             |
               v                             v
        Spatial index                  Vector index
         location                      embedding(description)
               |                             |
               v                             v
      "Cửa hàng trong 3 km"       "Cửa hàng bán đồ tương tự"
               |                             |
               +-------------+---------------+
                             |
                    Lọc quyền/trạng thái
                             |
                       Xếp hạng kết quả
~~~

Nếu người dùng hỏi “Trong bán kính 3 km, tìm cửa hàng bán đồ ăn thuần chay phù hợp với trẻ nhỏ”, ứng dụng có thể cần **kết hợp** chỉ mục không gian, từ khóa/metadata và vector. Đây là truy vấn hybrid, không phải bài toán mà một loại index duy nhất luôn giải quyết tốt.

## 2. Chỉ mục chuyên biệt khác chỉ mục thuộc tính thế nào?

Một chỉ mục truyền thống theo `storeId` trả lời:

> “Đối tượng mang đúng ID này ở đâu?”

Một chỉ mục theo `createdAt` trả lời:

> “Những bản ghi nằm trong khoảng thời gian này ở đâu?”

Chỉ mục không gian trả lời:

> “Những hình học nào nằm trong/giao với vùng này hoặc gần một tọa độ này?”

Chỉ mục vector trả lời:

> “Những vector nào giống vector truy vấn nhất theo metric đã chọn?”

| Khía cạnh | Index thuộc tính thường | Spatial index | Vector index |
|---|---|---|---|
| Dữ liệu chính | ID, số, ngày, chuỗi | Point, LineString, Polygon, GeoJSON... | Mảng số có số chiều xác định |
| Phép truy vấn | Bằng, khoảng, tiền tố, sort | Within, intersects, near, distance | Top-k nearest, similarity threshold |
| Kích thước tọa độ | Thường 1 hoặc vài trường | Thường 2D/3D hoặc hình học địa lý | Hàng chục đến hàng nghìn chiều |
| Bài toán | Tra cứu tài khoản, lọc trạng thái | Tìm địa điểm, vùng phủ, geofence | Semantic search, ảnh tương đồng |
| Chi phí đáng chú ý | Selectivity, read/write | Tính hình học và độ phủ cell | RAM, build, recall/latency |
| Bảo đảm phù hợp | Có thể lọc chính xác | Có thể cần lọc hình học chính xác sau candidate | ANN thường xấp xỉ top-k |
| Hạn chế | Không hiểu quan hệ hình học/ngữ nghĩa | Không hiểu ý nghĩa văn bản | Không tự biết ràng buộc kinh doanh |

Một hệ NoSQL có thể tích hợp tất cả ba nhóm index. Một hệ khác chỉ hỗ trợ một vài nhóm hoặc cần dịch vụ tìm kiếm riêng. **Không nên suy luận khả năng truy vấn chỉ từ nhãn “NoSQL”.**

## 3. Dữ liệu không gian: điểm, đường và vùng

### 3.1. Point

Một điểm đại diện vị trí:

~~~json
{
  "storeId": "S100",
  "location": {
    "type": "Point",
    "coordinates": [106.7009, 10.7769]
  }
}
~~~

Trong GeoJSON, thứ tự tọa độ thường là:

```text
[longitude, latitude]
[kinh độ, vĩ độ]
~~~

**Không được đảo thành [latitude, longitude].** Đây là lỗi rất phổ biến vì các ứng dụng bản đồ hoặc API khác có thể trả tham số theo thứ tự vĩ độ trước.

Đối với hệ tọa độ kinh-vĩ độ thông dụng:

- Kinh độ (longitude) nằm trong khoảng tương ứng từ −180° đến 180°.
- Vĩ độ (latitude) nằm trong khoảng từ −90° đến 90°.
- Giá trị cần được xác nhận theo quy tắc hệ dữ liệu và vị trí thực tế.

Cặp `[106.7009, 10.7769]` minh họa một vị trí ở Thành phố Hồ Chí Minh. Các con số này chỉ phục vụ ví dụ truy vấn, không đại diện một cửa hàng có thật.

### 3.2. LineString

Một đường biểu diễn tuyến đi, đoạn đường, hành trình hoặc đường biên:

~~~json
{
  "type": "LineString",
  "coordinates": [
    [106.7009, 10.7769],
    [106.7032, 10.7791],
    [106.7061, 10.7810]
  ]
}
~~~

Một truy vấn có thể hỏi tuyến đường có **giao với vùng cấm** hay không. Nhưng cần phân biệt **đường thẳng nối các tọa độ** và đường đi thực tế trên mạng giao thông. Spatial index không tự biết đường một chiều, cầu vượt, giới hạn tải trọng hoặc thời gian di chuyển.

### 3.3. Polygon và MultiPolygon

Một vùng phục vụ có thể được biểu diễn bằng đa giác:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.6900, 10.7700],
      [106.7100, 10.7700],
      [106.7100, 10.7900],
      [106.6900, 10.7900],
      [106.6900, 10.7700]
    ]
  ]
}
~~~

Trong GeoJSON, vòng ngoài là một mảng tọa độ **đóng**: điểm cuối trùng điểm đầu. Những quy tắc về hướng vòng, lỗ (holes) và hình học hợp lệ cần tuân thủ đặc tả và engine.

Một `MultiPolygon` phù hợp khi vùng gồm nhiều khu vực rời nhau. Ví dụ nhà cung cấp chỉ hoạt động ở một số quận không liền kề.

### 3.4. Các quan hệ không gian khác nhau

| Quan hệ | Câu hỏi nghiệp vụ |
|---|---|
| Within/contains | Điểm nhận hàng có nằm trong vùng phục vụ không? |
| Intersects | Đường vận chuyển có đi qua vùng hạn chế không? |
| Near/within distance | Điểm nào ở cách người dùng tối đa 3 km? |
| Nearest neighbor | 10 cửa hàng gần vị trí hiện tại nhất là gì? |
| Bounding box | Những đối tượng nằm trong khung nhìn bản đồ? |
| Overlaps | Hai vùng giao nhau một phần hay không? |
| Touches | Hai vùng có tiếp xúc biên theo định nghĩa hình học? |

Không phải database nào cũng hỗ trợ tất cả quan hệ hoặc biểu thức hình học với cùng độ chính xác. Một số hệ chủ yếu tối ưu **điểm và khoảng cách**, trong khi truy vấn đa giác phức tạp có thể cần công cụ địa lý chuyên sâu hơn.

## 4. Hệ tọa độ và đơn vị là một phần của tính đúng

### 4.1. Tọa độ địa lý khác tọa độ phẳng

Kinh độ/vĩ độ là tọa độ góc trên mô hình Trái Đất. Một độ kinh độ không tương đương số mét cố định trên mọi vĩ độ.

Nếu lấy:

\[
d = \sqrt{(\Delta longitude)^2 + (\Delta latitude)^2}
\]

thì `d` có đơn vị **độ**, không phải mét. Công thức này không tự cung cấp khoảng cách địa lý chính xác cho yêu cầu bán kính 3 km.

Một số engine có kiểu **geography** với tính khoảng cách trên bề mặt địa cầu, một số dùng hình học **geometry** phẳng theo hệ tọa độ đã xác định, và một số có operator riêng cho GeoJSON trên hình cầu.

### 4.2. WGS84 và CRS

Dữ liệu GPS phổ biến sử dụng hệ quy chiếu WGS84. Các hệ tọa độ có thể được biểu diễn bởi CRS/SRID tùy sản phẩm.

Khi đưa dữ liệu vào index phải biết:

- Field chứa longitude/latitude hay tọa độ phẳng?
- Engine mặc định dùng CRS nào?
- Đơn vị bán kính là mét, kilomet, độ hay đơn vị của CRS?
- Có biến đổi CRS trước khi ghi/truy vấn không?
- Có dữ liệu độ cao (altitude) và engine có sử dụng chiều đó không?

Một điểm ở Việt Nam với `longitude=106` và `latitude=10` nhưng bị đảo sẽ chỉ một nơi rất khác. Chỉ mục không gian không thể tự hiểu người nhập đã đổi thứ tự.

### 4.3. Bán kính trên bề mặt Trái Đất

Với khoảng cách địa lý trên hình cầu, công thức Haversine là một cách ước lượng thường gặp:

\[
a = \sin^2\left(\frac{\Delta\varphi}{2}\right)
+ \cos(\varphi_1)\cos(\varphi_2)
\sin^2\left(\frac{\Delta\lambda}{2}\right)
\]

\[
d = 2R\arcsin(\sqrt{a})
\]

Ở đây `\varphi` là vĩ độ theo radian, `\lambda` là kinh độ theo radian, `R` là bán kính Trái Đất được lựa chọn. Công thức giả định mô hình hình cầu; những phép tính ellipsoid/địa trắc chính xác hơn có thể cần thư viện chuyên dụng.

Trong ứng dụng, ưu tiên dùng operator không gian **đúng CRS, đúng đơn vị và tính toán của engine** thay vì tự biến đổi độ sang mét bằng một hằng số tùy tiện.

### 4.4. Khoảng cách đường chim bay khác thời gian di chuyển

Spatial index thường hỗ trợ khoảng cách địa lý/hình học, không nhất thiết hỗ trợ khoảng cách **trên mạng đường**.

Ví dụ:

- Hai điểm cách 700 m đường chim bay.
- Nhưng giữa chúng có sông hoặc đường cấm.
- Quãng đường lái xe có thể dài 5 km.

Cho câu hỏi “cửa hàng gần nhất theo thời gian giao hàng”, một pipeline có thể là:

1. Spatial index tìm 50 ứng viên gần theo đường chim bay.
2. Routing service tính thời gian/quãng đường thực tế cho ứng viên.
3. Xếp hạng theo thời gian di chuyển và điều kiện nghiệp vụ.

Không nên gọi kết quả `$near` theo tọa độ là “tuyến đường nhanh nhất”.

## 5. Spatial index tổ chức không gian như thế nào?

Một B-tree trên `longitude` riêng lẻ giúp lọc một khoảng kinh độ, nhưng một vùng hai chiều còn phải xét vĩ độ. Với polygon phức tạp, các điều kiện còn khó hơn.

Spatial index dùng cấu trúc có khả năng thu hẹp vùng tìm kiếm theo hình học.

### 5.1. R-tree và các biến thể

R-tree nhóm những hình học vào các **minimum bounding rectangle (MBR)** hoặc bounding box để tìm nhanh các vùng có thể giao nhau.

~~~text
                  Không gian tổng
                        |
           +------------+-------------+
           |                          |
      Bounding box A             Bounding box B
           |                          |
      +----+----+                +----+----+
      |         |                |         |
    Hình 1    Hình 2           Hình 3    Hình 4
~~~

Khi truy vấn một vùng nhỏ, engine chỉ cần đi sâu vào những nhánh có bounding box có khả năng giao với vùng đó.

**Bounding box lọc ứng viên, chưa chắc chứng minh giao nhau thật.** Một polygon hình chữ U có bounding box chứa nhiều điểm nằm trong khoảng rỗng; cần kiểm tra quan hệ hình học chính xác với geometry gốc.

R-tree là một họ cấu trúc quan trọng về mặt khái niệm. Không phải mọi NoSQL geospatial index đều dùng R-tree ở bên trong.

### 5.2. Quadtree

Quadtree chia không gian 2D thành bốn ô nhỏ theo từng cấp:

~~~text
+---------+---------+
|   NW    |   NE    |
|         |         |
+---------+---------+
|   SW    |   SE    |
|         |         |
+---------+---------+
~~~

Ô chứa nhiều dữ liệu có thể được chia nhỏ thêm. Cách phân vùng này phù hợp nhiều bài toán không gian, nhưng cần xử lý:

- Đối tượng nằm trên biên giữa ô.
- Mật độ dữ liệu không đều.
- Kích thước ô quá lớn hoặc quá nhỏ.
- Query đi qua nhiều ô.

### 5.3. Geohash và cell-based index

Geohash biến vị trí thành một mã biểu diễn các ô địa lý theo mức chính xác. Những điểm gần nhau đôi khi có prefix mã giống nhau.

~~~text
Tọa độ (lon, lat)
       |
       v
  cell/geohash
       |
       v
Chọn các ô giao với vùng truy vấn
       |
       v
Lấy ứng viên trong các ô
       |
       v
Kiểm tra khoảng cách/hình học thực
~~~

Geohash là kỹ thuật hữu ích cho phân vùng/tra cứu, nhưng **không được chỉ lấy một prefix geohash của tâm rồi kết luận đủ các điểm gần tâm**. Hai điểm rất gần nhau có thể nằm ở hai ô khác nhau ngay tại biên.

Một truy vấn bán kính cần xét các ô lân cận/cell covering đầy đủ và kiểm tra khoảng cách chính xác nếu cần.

### 5.4. S2, H3 và các hệ cell địa cầu

Những hệ phân chia bề mặt địa cầu thành cell như **S2** hoặc **H3** có thể dùng để xây bộ chỉ mục không gian, làm dữ liệu thống kê theo ô hoặc xác định vùng lân cận.

Đừng đồng nhất:

- “Hệ dùng S2/H3 để đánh mã cell”;
- “Database có một spatial index chính thức”;
- “Truy vấn point-in-polygon đã được kiểm tra chính xác”.

Cell thường tạo **tập ứng viên/coarse covering**. Nếu polygon hoặc khoảng cách ở biên yêu cầu đúng, phải xử lý phần sai số và bước refine theo engine/thuật toán.

### 5.5. Cấu trúc theo cây và các engine hiện đại

Một số search engine tối ưu index tọa độ với cấu trúc dạng BKD tree hoặc các tổ chức nhiều chiều riêng. Các hệ khác dùng các biến thể cây/hashing/cell indexing.

Người thiết kế ứng dụng không nhất thiết phải biết từng byte cấu trúc nội bộ, nhưng phải biết **operator được index hỗ trợ**, độ chính xác, giới hạn hình học và cách nó tác động đến plan.

## 6. Spatial query thường là lọc ứng viên rồi kiểm tra chính xác

Một chiến lược tổng quát:

~~~text
Yêu cầu: điểm trong bán kính 3 km
                |
                v
      Index chọn vùng/cell liên quan
                |
                v
        Candidate locations
                |
                v
    Tính khoảng cách đúng đơn vị/CRS
                |
                v
       distance <= 3.000 m
                |
                v
      Lọc tenant, quyền, trạng thái
                |
                v
       Sắp xếp và trả kết quả
~~~

Bước chọn ứng viên có thể tạo **false positives**: những điểm nằm trong bounding box nhưng ngoài bán kính. Khi cần độ chính xác của điều kiện bán kính, bước hình học chính xác phải loại chúng.

Một giải pháp cell-based ngây thơ còn có thể tạo **false negatives** nếu bỏ sót cell lân cận. Khi đó bước refine không thể cứu một đối tượng đã bị loại khỏi tập ứng viên từ đầu.

### 6.1. Bounding box trước, distance sau

Giả sử mục tiêu là tìm điểm cách vị trí người dùng tối đa 3 km. Truy vấn có thể dùng bounding box gần đúng để giới hạn ứng viên rồi lọc khoảng cách địa lý chính xác.

Điều này thường nhanh hơn việc tính khoảng cách tới mọi điểm trong toàn cơ sở dữ liệu, đặc biệt với lượng điểm lớn.

Tuy nhiên, nếu engine đã cung cấp operator `near` hoặc `geoWithin` có spatial index tốt, đừng tự dựng bounding box thiếu chính xác chỉ vì nghĩ nó sẽ nhanh hơn. Hãy xem query plan.

### 6.2. Polygon có lỗ và vùng nhiều mảnh

Ví dụ một khu giao hàng có một khu vực không phục vụ ở giữa. Bounding box có thể chứa cả vùng cấm. Nếu ứng dụng chỉ lọc bbox và bỏ qua polygon/hole thật, hệ thống sẽ nhận đơn ngoài phạm vi.

Điều kiện không gian là một **ràng buộc nghiệp vụ**, nên cần kiểm tra hình học phù hợp, không chỉ dựa vào một bộ lọc xấp xỉ.

## 7. MongoDB: chỉ mục 2dsphere và truy vấn địa lý

MongoDB có các loại chỉ mục geospatial như **`2dsphere`** và **`2d`**. Với tọa độ địa lý dạng GeoJSON, `2dsphere` là lựa chọn thường gặp.

### 7.1. Lưu Point dạng GeoJSON

```javascript
db.stores.insertMany([
  {
    storeId: "S100",
    tenantId: "T1",
    name: "Điểm nhận hàng A",
    status: "ACTIVE",
    location: {
      type: "Point",
      coordinates: [106.7009, 10.7769]
    }
  },
  {
    storeId: "S101",
    tenantId: "T1",
    name: "Điểm nhận hàng B",
    status: "ACTIVE",
    location: {
      type: "Point",
      coordinates: [106.7051, 10.7815]
    }
  }
]);
```

Trường `location` có GeoJSON `type` và `coordinates`. Thứ tự là **[longitude, latitude]**, không phải [latitude, longitude].

### 7.2. Tạo 2dsphere index

```javascript
db.stores.createIndex(
  { location: "2dsphere" },
  { name: "store_location_2dsphere" }
);
```

Index có thể hỗ trợ truy vấn không gian theo khả năng của MongoDB. Với truy vấn theo tenant/status, phải xem xét thêm cách đánh index và lọc, không mặc định spatial index đơn lẻ sẽ đáp ứng tối ưu mọi điều kiện.

### 7.3. Tìm điểm gần nhất trong bán kính

```javascript
const userLocation = {
  type: "Point",
  coordinates: [106.7000, 10.7770]
};

db.stores.find({
  tenantId: "T1",
  status: "ACTIVE",
  location: {
    $near: {
      $geometry: userLocation,
      $maxDistance: 3000
    }
  }
}).limit(20);
```

Trong ngữ cảnh `2dsphere` với điểm GeoJSON, `$maxDistance` được hiểu theo **mét**. `$near` tìm theo khoảng cách và có khả năng trả kết quả theo thứ tự gần hơn trước, nhưng hiệu năng/kế hoạch cần quan sát trên dữ liệu thật.

Một lưu ý: dùng đúng index và dạng dữ liệu cho operator. Không nên lấy một con số `3000` rồi mặc định mọi loại geospatial query trong mọi engine đều dùng mét.

### 7.4. Tìm điểm nằm trong polygon

```javascript
const serviceArea = {
  type: "Polygon",
  coordinates: [[
    [106.6900, 10.7700],
    [106.7100, 10.7700],
    [106.7100, 10.7900],
    [106.6900, 10.7900],
    [106.6900, 10.7700]
  ]]
};

db.stores.find({
  tenantId: "T1",
  location: {
    $geoWithin: {
      $geometry: serviceArea
    }
  }
});
```

Truy vấn này hỏi các vị trí cửa hàng thuộc vùng đã cho. Với hình học lớn, polygon qua kinh tuyến 180° hoặc dữ liệu có nhiều vùng phức tạp, cần hiểu quy tắc xử lý hình học/cấu trúc của MongoDB và GeoJSON trước khi dùng trong nghiệp vụ quan trọng.

### 7.5. $geoNear và aggregation

MongoDB cũng có aggregation stage `$geoNear` phù hợp khi cần tính khoảng cách và đưa nó vào pipeline. Ví dụ dạng minh họa:

```javascript
db.stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7770]
      },
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: {
        tenantId: "T1",
        status: "ACTIVE"
      }
    }
  },
  { $limit: 20 },
  { $project: {
      _id: 0,
      storeId: 1,
      name: 1,
      distanceMeters: 1
  }}
]);
```

Việc sử dụng `$geoNear` có những điều kiện về vị trí trong pipeline/index và thay đổi theo phiên bản. Nên kiểm tra cú pháp chính xác của môi trường sử dụng; ở đây mục tiêu là minh họa **truy vấn khoảng cách + lọc metadata + trả khoảng cách**.

### 7.6. 2d và 2dsphere không hoán đổi tùy ý

`2d` phục vụ các loại truy vấn tọa độ phẳng/legacy phù hợp với khả năng của MongoDB; `2dsphere` xử lý dữ liệu địa lý theo ngữ nghĩa hình cầu và GeoJSON. Không nên chọn `2d` chỉ vì tọa độ có hai số nếu nhu cầu là khoảng cách địa lý trên Trái Đất.

### 7.7. Kiểm tra index có được dùng

Một truy vấn có thể được kiểm tra với `explain()`:

```javascript
db.stores.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7770]
      },
      $maxDistance: 3000
    }
  }
}).explain("executionStats");
```

Các chỉ số cần quan sát: plan sử dụng geospatial index nào, số candidate được xét, số document trả, thời gian và tài nguyên. Tên operator cụ thể có thể khác theo phiên bản.

## 8. Redis GEO: tìm vị trí gần theo key geospatial

Redis có nhóm lệnh geospatial dựa trên một sorted set với mã hóa vị trí thích hợp. Nó phù hợp với những bài toán điểm gần đơn giản, ví dụ điểm nhận hàng hoặc xe đang hoạt động.

### 8.1. Ghi vị trí

```redis
GEOADD stores:active 106.7009 10.7769 S100
GEOADD stores:active 106.7051 10.7815 S101
GEOADD stores:active 106.7120 10.7750 S102
```

Ở đây Redis dùng **longitude rồi latitude**.

### 8.2. Truy vấn bán kính

```redis
GEOSEARCH stores:active
  FROMLONLAT 106.7000 10.7770
  BYRADIUS 3 km
  ASC
  COUNT 20
  WITHDIST
```

Đây là cách biểu diễn nhiều dòng cho dễ đọc; khi thực thi Redis CLI, có thể gửi như một lệnh hoàn chỉnh. `GEOSEARCH` tìm những member gần vị trí, với đơn vị và thứ tự được khai báo.

Redis GEO phù hợp khi cần truy vấn điểm nhanh trên tập đã quản lý nhưng không tự mang đầy đủ:

- Quan hệ đa giác phức tạp;
- Hình học vùng có lỗ;
- Quy tắc multi-tenant;
- Trạng thái giao dịch;
- Bảo đảm dữ liệu vị trí luôn mới nhất.

Ứng dụng phải tự quản lý **điều kiện membership trong key**, xóa member khi không còn hoạt động và lọc thêm metadata nếu không được mã hóa ngay trong cách tổ chức tập.

### 8.3. Vị trí di động có vòng đời

Nếu vị trí xe thay đổi mỗi vài giây:

- `GEOADD` cập nhật vị trí member;
- Cần xử lý xe lâu không gửi vị trí;
- Có thể cần field `lastSeenAt` và TTL/cleanup riêng;
- Query geospatial không tự chứng minh xe đang hoạt động;
- Khi chốt đơn, cần kiểm tra trạng thái và vị trí phù hợp tại nguồn authoritative.

Một kết quả gần về tọa độ nhưng dữ liệu cũ 15 phút có thể không đáng dùng để điều phối xe.

## 9. Các khả năng spatial ở search/document/graph database khác

### 9.1. Elasticsearch/OpenSearch

Một document có thể chứa field kiểu `geo_point` để phục vụ truy vấn khoảng cách, bounding box và geo sorting; hình học phức tạp có thể dùng kiểu `geo_shape` theo khả năng phiên bản.

Ví dụ mapping khái niệm cho Elasticsearch:

```json
{
  "mappings": {
    "properties": {
      "storeId": {"type": "keyword"},
      "tenantId": {"type": "keyword"},
      "status": {"type": "keyword"},
      "location": {"type": "geo_point"}
    }
  }
}
```

Với `geo_point`, một truy vấn `geo_distance` có thể tìm các điểm trong bán kính:

```json
{
  "query": {
    "bool": {
      "filter": [
        {"term": {"tenantId": "T1"}},
        {"term": {"status": "ACTIVE"}},
        {
          "geo_distance": {
            "distance": "3km",
            "location": {
              "lat": 10.7770,
              "lon": 106.7000
            }
          }
        }
      ]
    }
  }
}
```

**Chú ý:** object ở ví dụ Elasticsearch dùng khóa `lat` và `lon` nên không nhập nhằng thứ tự mảng; trong GeoJSON, thứ tự là [lon, lat]. Mỗi API có hình thức truyền tọa độ riêng.

### 9.2. Neo4j

Neo4j property graph có thể lưu `point` và dùng point index/điều kiện khoảng cách cho những truy vấn phù hợp. Ví dụ điểm cửa hàng:

```cypher
CREATE (:Store {
  storeId: "S100",
  location: point({
    latitude: 10.7769,
    longitude: 106.7009
  })
});
```

Ví dụ point index:

```cypher
CREATE POINT INDEX store_location_idx IF NOT EXISTS
FOR (s:Store)
ON (s.location);
```

Graph database còn hữu ích khi sau khi tìm một nhóm nút theo vị trí, cần duyệt **quan hệ thực thể** như cửa hàng thuộc chuỗi nào hoặc kho giao cho chi nhánh nào. Nhưng point index không làm các phép duyệt hàng triệu cạnh tự động rẻ; phải xét fan-out và query plan.

### 9.3. Azure Cosmos DB for NoSQL

Cosmos DB có các khả năng lập chỉ mục và hàm truy vấn không gian theo GeoJSON trong những cấu hình hỗ trợ. Khi chọn, cần xác nhận policy spatial index, định dạng geometry, đơn vị hàm khoảng cách và RU của truy vấn.

Không nên giả định nó hoạt động y hệt MongoDB `2dsphere` hoặc Elasticsearch `geo_point` dù đều nhận GeoJSON.

### 9.4. Khi nào nên dùng hệ GIS chuyên sâu?

Nếu hệ thống cần:

- Topology phức tạp;
- Phép overlay trên đa giác rất lớn;
- Phân tích raster hoặc mạng đường;
- Chuyển hệ tọa độ nhiều loại;
- Độ chính xác địa trắc chuyên sâu;
- Nhiều toán tử hình học không được NoSQL hiện tại hỗ trợ;

thì một công cụ GIS/không gian chuyên dụng hoặc một database có extension GIS mạnh có thể phù hợp hơn. Spatial feature ở NoSQL đủ cho tìm điểm gần không có nghĩa nó là nền tảng GIS toàn diện.

## 10. Vector index là gì?

Vector là một dãy số:

\[
\mathbf{x}=(x_1,x_2,\ldots,x_d)
\]

Trong tìm kiếm ngữ nghĩa, vector thường được tạo từ **embedding model** trên văn bản, ảnh, âm thanh hoặc dữ liệu khác.

Ví dụ minh họa:

~~~text
"Tài liệu về chống ồn"  ──embedding model──> [0.12, -0.08, 0.31, ...]
"Tai nghe cách âm"      ──embedding model──> [0.11, -0.05, 0.29, ...]
"Bảng giá vận chuyển"   ──embedding model──> [-0.41, 0.27, 0.03, ...]
~~~

Đây chỉ là các số giả lập, không phải embedding thật từ một model. Trong hệ thống thực, vector có thể có 128, 384, 768, 1.536 hoặc những số chiều khác tùy mô hình.

Mục đích của **vector similarity search** là tìm những vector gần vector truy vấn nhất theo một metric được định nghĩa.

### 10.1. Sản phẩm nào cần vector search?

- Tìm tài liệu theo ngữ nghĩa.
- Tìm ảnh giống ảnh mẫu.
- Tìm sản phẩm tương tự dựa trên mô tả/hình ảnh.
- Gợi ý nội dung theo biểu diễn người dùng và item.
- Retrieval cho hệ hỏi đáp/RAG.
- Gom nhóm hoặc tìm những item tương đồng.
- Tìm các record “gần” nhau theo đặc trưng máy học.

Nhưng vector không tự chứng minh:

- Hai người là cùng danh tính;
- Sản phẩm còn hàng;
- Người dùng có quyền xem tài liệu;
- Một câu trả lời là sự thật;
- Hai tài liệu không bị vi phạm bản quyền;
- Tài liệu có cùng từ khóa chính xác.

Chỉ mục vector cung cấp **ứng viên tương đồng**, không thay các bước xác thực và kiểm tra nghiệp vụ.

## 11. Từ dữ liệu gốc tới embedding và vector index

Một pipeline thường gồm:

~~~text
Document / Product / Image
             |
             v
     Chọn trường nội dung
             |
             v
    Chuẩn hóa và chia chunk
             |
             v
       Embedding model
             |
             v
       Vector + metadata
             |
             v
        Vector index
             |
             v
    Top-k similarity search
~~~

### 11.1. Lưu ID và metadata cùng vector

Ví dụ một record vector khái niệm:

```json
{
  "id": "DOC100#chunk02",
  "documentId": "DOC100",
  "tenantId": "T1",
  "visibility": "PUBLIC",
  "sourceVersion": 7,
  "embeddingModelVersion": "model-v3",
  "chunkerVersion": "chunker-v2",
  "chunkIndex": 2,
  "embedding": [0.12, -0.08, 0.31, 0.17]
}
```

Vector 4 chiều trong ví dụ chỉ để trình bày JSON ngắn gọn. Thực tế độ dài phải khớp với số chiều mà index đã cấu hình.

Lý do lưu metadata:

- `documentId` để đi từ vector về dữ liệu nguồn.
- `tenantId` và `visibility` để lọc phạm vi được phép.
- `sourceVersion` để tránh dùng vector cũ.
- `embeddingModelVersion` để biết vector thuộc không gian nào.
- `chunkIndex` và `chunkerVersion` để quản lý nhiều vector của một tài liệu.

### 11.2. Tại sao phải chia chunk?

Một tài liệu dài có thể chứa nhiều chủ đề. Nếu biến toàn bộ thành một vector, kết quả có thể làm mất thông tin cục bộ. Chia tài liệu thành chunk cho phép truy xuất đoạn liên quan.

Nhưng chunking mang thêm vấn đề:

- Chunk quá ngắn có thể thiếu ngữ cảnh.
- Chunk quá dài có thể pha nhiều ý.
- Chunk overlap làm tăng số vector và chi phí.
- Số chunk thay đổi khi nội dung sửa.
- Cần ghép kết quả về document và tránh trả nhiều chunk trùng.
- Khi xóa document phải xóa **toàn bộ vector chunk** của nó.

Index vector thường chứa **bản sao dẫn xuất**, không phải nguồn sự thật của nội dung.

## 12. Độ đo khoảng cách và tương đồng vector

Chọn metric phải phù hợp embedding model và cách chuẩn hóa vector.

### 12.1. Euclidean distance (L2)

\[
d_{L2}(\mathbf{x},\mathbf{y})=
\sqrt{\sum_{i=1}^{d}(x_i-y_i)^2}
\]

Khoảng cách càng nhỏ, vector càng gần theo L2.

### 12.2. Dot product

\[
\mathbf{x}\cdot\mathbf{y}=
\sum_{i=1}^{d}x_i y_i
\]

Giá trị dot product phụ thuộc cả **hướng và độ lớn** của vector. Nếu embedding model được thiết kế cho dot product, engine cần dùng metric tương ứng.

### 12.3. Cosine similarity

\[
\cos(\mathbf{x},\mathbf{y})=
\frac{\mathbf{x}\cdot\mathbf{y}}
{\|\mathbf{x}\|\|\mathbf{y}\|}
\]

Với vector khác zero, cosine phản ánh mức gần nhau về **hướng**. Cosine càng lớn (thường càng gần 1), vector càng tương đồng theo metric này.

Với các vector đã chuẩn hóa norm bằng 1, cosine, dot product và L2 có liên hệ đơn điệu:

\[
\|\mathbf{x}-\mathbf{y}\|^2=2-2(\mathbf{x}\cdot\mathbf{y})
\]

Nhưng không nên suy rằng có thể đổi metric tùy ý khi vector không được chuẩn hóa hoặc model được huấn luyện theo metric khác.

### 12.4. Similarity score không phải xác suất đúng

Nếu một search engine trả score 0,82, không được tự diễn giải thành “82% chắc chắn tài liệu trả lời đúng câu hỏi”. Score là kết quả đo/biến đổi theo metric, index và engine; đôi khi được chuẩn hóa theo một cách riêng.

Để xác định ngưỡng chấp nhận, cần đánh giá trên tập truy vấn và nhãn phù hợp với ứng dụng.

### 12.5. Các trường hợp cần validation

- Vector thiếu hoặc sai số chiều.
- NaN/Infinity trong thành phần.
- Vector zero khi dùng cosine.
- Vector đã tính bởi model khác.
- Vector có norm bất thường.
- Metadata filter thiếu field.
- Kho dùng metric khác với pipeline embedding.

Một vector index không tự sửa các lỗi này. Hệ có thể từ chối ghi hoặc trả kết quả kém chất lượng.

## 13. Exact kNN và approximate nearest neighbor (ANN)

### 13.1. Exact kNN

Một cách tìm chính xác là tính khoảng cách từ query vector tới tất cả vector ứng viên rồi chọn k vector tốt nhất.

```text
Query vector
    |
    v
Tính distance tới tất cả N vector
    |
    v
Sắp xếp/chọn top-k
    |
    v
Kết quả chính xác theo metric và tập dữ liệu được xét
~~~

Với N lớn, số chiều d cao, nhiều request đồng thời, cách này có thể tốn CPU/GPU/băng thông nhớ. Tuy vậy, nếu sau filter chỉ còn vài trăm vector, **exact search có thể rất hợp lý**.

### 13.2. ANN

ANN dùng cấu trúc index để tìm **những vector rất gần** mà không cần so với mọi vector:

~~~text
Query vector
    |
    v
Duyệt cấu trúc ANN
    |
    v
Lấy tập ứng viên gần
    |
    v
Tính/ước lượng độ tương đồng
    |
    v
Top-k gần đúng
~~~

Ưu điểm:

- Thường có latency thấp hơn với tập lớn.
- Có thể mở rộng cho hàng triệu vector hoặc hơn, tùy hạ tầng.
- Phù hợp truy vấn tương đồng tương tác.

Đánh đổi:

- Có thể bỏ sót một vài neighbor thực sự gần nhất.
- Index xây dựng/tái cấu trúc tốn tài nguyên.
- Cần tuning và đo recall.
- Insert/update/delete có thể ảnh hưởng chất lượng/chí phí.
- Metadata filter có thể làm ANN khó tối ưu.

ANN không đồng nghĩa với sai dữ liệu; nó có nghĩa hệ chọn **giới hạn về recall để lấy hiệu năng** theo hợp đồng tìm kiếm gần đúng.

## 14. HNSW: chỉ mục đồ thị lân cận cho vector

**HNSW (Hierarchical Navigable Small World)** là một thuật toán ANN rất phổ biến. Nó xây cấu trúc **đồ thị lân cận** giữa những vector, tổ chức thành nhiều tầng để việc tìm kiếm đi từ vùng rộng đến vùng gần query.

```text
Tầng cao:       A -------- B
                 \        /
                  \      /
Tầng giữa:      C --- D --- E
                 \   / \   /
                  \ /   \ /
Tầng thấp:       F-G-H-I-J-K-L
                       ^
                  Query đến gần H/I
~~~

Đây là sơ đồ ý tưởng; cấu trúc thực tế có các cạnh liên kết theo khoảng cách và quy tắc xây dựng, không phải graph thực thể `User-Follows-User`.

### 14.1. HNSW không phải graph database nghiệp vụ

Mặc dù HNSW dùng đồ thị nội bộ, các cạnh của nó biểu diễn **mối gần nhau trong không gian vector**, không biểu diễn quan hệ nghiệp vụ như:

```text
(User)-[:BOUGHT]->(Product)
~~~

Không thể dùng một HNSW index để thay thế graph traversal cần ngữ nghĩa quan hệ, ràng buộc cạnh hoặc thuật toán đường đi trên entity graph.

### 14.2. Những tham số thường gặp

Tên và phạm vi tham số tùy engine, nhưng trong nhiều triển khai HNSW có:

- **M:** số liên kết lân cận mong muốn hoặc giới hạn bậc theo cấu trúc.
- **efConstruction:** độ rộng tìm kiếm khi xây index, ảnh hưởng chất lượng và chi phí build.
- **efSearch:** độ rộng tìm kiếm khi query, ảnh hưởng recall và latency.

Ý tưởng đánh đổi:

| Điều chỉnh | Xu hướng thường gặp |
|---|---|
| Tăng M | Tốn thêm bộ nhớ/index, có thể cải thiện tìm kiếm |
| Tăng efConstruction | Build chậm hơn, có thể tăng chất lượng graph |
| Tăng efSearch | Nhiều phép duyệt hơn, thường cải thiện recall nhưng tăng latency |

Đây là xu hướng, không phải bảo đảm tuyến tính. Mỗi sản phẩm có default, giới hạn và cơ chế tự tuning khác nhau.

### 14.3. Delete/update trong HNSW

Một số triển khai đánh dấu xóa rồi dọn sau; một số có thể cập nhật động, rebuild từng phần hoặc tạo segment mới. Việc ghi đè vector cùng ID có thể không có cùng chi phí với thay đổi một thuộc tính trong document database.

Nếu nội dung thay đổi thường xuyên, cần tính **tần suất cập nhật index và khả năng phục hồi** thay vì chỉ benchmark các truy vấn trên tập vector tĩnh.

## 15. IVF, PQ và các hướng ANN khác

### 15.1. IVF (Inverted File Index)

IVF chia không gian vector thành các nhóm/cluster. Khi query, hệ tìm một số cluster gần query rồi tìm vector trong những cluster đó.

```text
Tập vector lớn
       |
       v
Chia thành cluster theo centroid
       |
  +----+----+----+
  | C1 | C2 | C3 |
  +----+----+----+
          ^
      Query gần C2
          |
    Tìm trong những cluster được chọn
~~~

Một tham số thường thấy là số cluster được probe (`nprobe` hoặc tương đương). Probe nhiều cluster hơn có thể tăng recall nhưng làm nhiều việc hơn.

### 15.2. Product Quantization (PQ)

PQ và các dạng nén vector chia vector thành những phần rồi biểu diễn bằng mã ngắn từ codebook, giảm nhu cầu lưu trữ và băng thông bộ nhớ.

Đánh đổi:

- Tiết kiệm RAM/disk.
- Có thể tăng quy mô dữ liệu trên hạ tầng cho trước.
- Khoảng cách tính từ vector nén có sai số.
- Có thể cần rerank bằng vector gốc để tăng chất lượng.

### 15.3. Exact flat và ANN có thể cùng tồn tại

Một hệ có thể lưu vector gốc và index ANN. Pipeline truy vấn:

1. ANN tìm 100–200 ứng viên;
2. Lấy vector chính xác của ứng viên;
3. Rerank theo metric chuẩn;
4. Trả top 10.

Điều này cải thiện thứ tự **trong tập ứng viên đã lấy**, nhưng không thể cứu một true nearest neighbor bị ANN bỏ sót từ bước candidate retrieval.

### 15.4. Khi nào không cần ANN?

- Tổng số vector rất nhỏ.
- Filter theo tenant/metadata làm tập ứng viên chỉ còn vài trăm phần tử.
- Batch job có thể chấp nhận latency dài.
- Cần exact top-k tuyệt đối trên một tập có thể tính trực tiếp.
- Chi phí xây ANN cao hơn lợi ích với workload hiện tại.

Đừng chọn HNSW chỉ vì tên phổ biến; hãy đo exact baseline trước.

## 16. Recall, precision, latency và chi phí

### 16.1. Recall@k

Khi đánh giá ANN, có thể lấy exact kNN làm ground truth theo metric và tập dữ liệu cố định.

Ví dụ:

```text
Exact top-5: [A, B, C, D, E]
ANN top-5:   [A, C, E, F, G]
~~~

Có 3 trong 5 neighbor đúng:

\[
Recall@5 = \frac{3}{5}=0.6
\]

Đây là ví dụ. Trong thực tế, cần đo recall@k trên **tập query đại diện**, các segment/tenant và điều kiện filter khác nhau, không chỉ một truy vấn.

### 16.2. Precision và độ phù hợp nghiệp vụ

Recall@k so ANN với exact ranking theo metric; nó **không đo trực tiếp chất lượng ngữ nghĩa**.

Nếu embedding model đánh giá nhầm hai tài liệu là gần nhau, ANN tìm đúng top-k của model vẫn có thể cho kết quả không hữu ích.

Cần hai tầng đánh giá:

1. **Index quality:** ANN có tìm gần kết quả exact theo metric không?
2. **Retrieval relevance:** kết quả đó có phù hợp nhu cầu người dùng không?

Tầng hai có thể dùng nhãn con người, click feedback được xử lý cẩn thận, MRR, nDCG, precision@k hoặc kết quả nghiệp vụ phù hợp.

### 16.3. Latency và throughput

Theo dõi:

- p50/p95/p99 query latency;
- QPS/throughput;
- Số distance computations hoặc index visits nếu engine có metric;
- RAM/index size;
- Build time;
- Insert/update/delete latency;
- CPU/GPU usage;
- Recall@k dưới cùng mức tải;
- Latency/recall khi có metadata filter.

Tuning ANN là bài toán **nhiều mục tiêu**, không chỉ tìm latency thấp nhất bằng cách giảm số ứng viên.

### 16.4. Ước lượng bộ nhớ thô

Một vector `d` chiều lưu bằng float32 cần khoảng:

\[
4d\text{ bytes}
\]

Với 1 triệu vector 768 chiều:

\[
1{,}000{,}000 \times 768 \times 4
\approx 3.072\text{ GB}
\]

Đây chỉ là kích thước **mảng số thô** theo hệ thập phân, chưa gồm HNSW links, metadata, index overhead, replicas, compression, cache hoặc cấu trúc lưu khác.

Vì vậy, chọn số chiều/model ảnh hưởng lớn đến chi phí. Có hệ dùng float16, int8, PQ hoặc các kiểu nén khác với đánh đổi chất lượng và khả năng hỗ trợ.

## 17. Lọc metadata kết hợp ANN: bài toán khó hơn top-k thuần túy

Giả sử kho có 10 triệu tài liệu thuộc 1.000 tenant, nhưng mỗi request chỉ được tìm trong **một tenant**. Nếu ANN tìm top 100 trên toàn bộ 10 triệu rồi mới lọc `tenantId = T42`, rất có thể không còn đủ 10 kết quả.

### 17.1. Post-filter

~~~text
ANN top-100 toàn kho
       |
       v
Filter tenant=T42
       |
       v
Chỉ còn 0..3 kết quả
~~~

Post-filter dễ triển khai nhưng có thể dẫn đến:

- Không đủ k kết quả.
- Recall trong tenant thấp.
- Tốn tài nguyên cho candidate không được phép dùng.
- Rủi ro nếu có nội dung nhạy cảm được xử lý/trả ra trước bước lọc.

Nếu muốn lấy đúng top-k trong tenant, không thể mặc định **top-k toàn cục rồi filter** tương đương với **top-k có điều kiện**.

### 17.2. Pre-filter / filtered ANN

Một số vector engine hỗ trợ filter được tích hợp trong quá trình ANN. Ví dụ:

~~~text
Query embedding + tenant=T42
          |
          v
Filtered ANN / engine planning
          |
          v
Top-k gần đúng trong phạm vi được phép
~~~

Hiệu năng và recall phụ thuộc cách engine áp dụng filter. Với bộ lọc cực chọn lọc, có thể rẻ hơn khi **lọc chính xác theo metadata trước** rồi tính khoảng cách exact cho tập nhỏ.

### 17.3. Namespace/partition per tenant

Một lựa chọn khác là chia index theo tenant hoặc nhóm tenant:

- Phạm vi tìm kiếm và bảo mật dễ cô lập hơn.
- Có thể tối ưu query với tập nhỏ.
- Nhưng 1.000 tenant nhỏ có thể tạo nhiều index/namespace, tăng chi phí quản lý.
- Tenant quá lớn vẫn cần sharding.
- Di chuyển tài liệu giữa tenant hoặc thay ACL cần xử lý đồng bộ.

Không có thiết kế tối ưu cho mọi quy mô. Cần xem số tenant, kích thước phân phối và tần suất truy vấn.

### 17.4. Quyền truy cập không chỉ là metadata tùy chọn

Một document `visibility=PRIVATE` không được trả cho người không có quyền, kể cả nó rất gần query vector.

Backend cần:

1. Xác thực người dùng.
2. Tính phạm vi tenant/ACL được phép.
3. Áp dụng filter theo cơ chế của engine phù hợp.
4. Kiểm tra quyền ở thời điểm trả nội dung nếu có yêu cầu bảo mật mạnh.
5. Xử lý trường hợp quyền bị thu hồi nhưng vector index chưa cập nhật.

**Vector index có thể cập nhật trễ**, nên quyền truy cập nhạy cảm cần nguồn authoritative hoặc cơ chế nhất quán phù hợp; không thể chỉ tin một metadata stale.

## 18. MongoDB Atlas Vector Search: truy vấn bằng embedding

Một số dịch vụ document database tích hợp vector search. Với MongoDB Atlas Vector Search, một truy vấn có thể dùng aggregation stage `$vectorSearch`, khi index vector đã được tạo đúng số chiều, metric và filter fields theo cấu hình hỗ trợ.

### 18.1. Tài liệu minh họa

```javascript
db.productEmbeddings.insertOne({
  productId: "P100",
  tenantId: "T1",
  status: "ACTIVE",
  sourceVersion: 7,
  embeddingModelVersion: "model-v3",
  embedding: [/* vector 384 chiều thật được cung cấp khi ghi */]
});
```

Biểu thức array trên là placeholder để diễn giải schema. Muốn chạy, phải ghi vector số hợp lệ với số chiều index; comment không thay thế dữ liệu.

### 18.2. Query vector tương đồng

Ví dụ JavaScript dạng minh họa:

```javascript
// queryEmbedding: mảng 384 số từ cùng embedding model.
const queryEmbedding = getEmbeddingForUserQuery();

db.productEmbeddings.aggregate([
  {
    $vectorSearch: {
      index: "product_vector_idx",
      path: "embedding",
      queryVector: queryEmbedding,
      numCandidates: 200,
      limit: 10,
      filter: {
        tenantId: "T1",
        status: "ACTIVE"
      }
    }
  },
  {
    $project: {
      _id: 0,
      productId: 1,
      sourceVersion: 1,
      score: { $meta: "vectorSearchScore" }
    }
  }
]);
```

Hàm `getEmbeddingForUserQuery()` là hàm ứng dụng phải triển khai; đây không phải hàm có sẵn của MongoDB.

Trong những phiên bản Atlas hỗ trợ, `numCandidates` điều khiển tập ứng viên cho ANN, `limit` là số kết quả trả và `filter` cần các trường đã được cấu hình đúng khả năng filter của vector index.

### 18.3. Những điểm phải xác nhận trước khi dùng

- Hệ đang dùng MongoDB Atlas Search/Vector Search hay MongoDB tự triển khai với khả năng khác?
- Cú pháp index vector và supported filters của phiên bản?
- Metric similarity và số chiều đã khai báo?
- Một stage có yêu cầu vị trí đặc biệt trong aggregation không?
- ANN có thông số numCandidates nào được hỗ trợ?
- Trường `tenantId`/`status` có được index để pre-filter đúng không?
- Quy trình update/delete vector và độ trễ visibility thế nào?

Không nên giả định một collection có field array số là đã tự có vector index.

## 19. Elasticsearch/OpenSearch: vector field và kNN

Search engine có thể vừa phục vụ từ khóa vừa tìm kiếm vector. Ví dụ Elasticsearch hiện đại hỗ trợ kiểu `dense_vector` có index kNN trong những cấu hình phù hợp.

### 19.1. Mapping minh họa

```json
{
  "mappings": {
    "properties": {
      "productId": {"type": "keyword"},
      "tenantId": {"type": "keyword"},
      "status": {"type": "keyword"},
      "embedding": {
        "type": "dense_vector",
        "dims": 384,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
```

Cấu hình/kiểu index, default quantization và các tùy chọn có thể khác theo phiên bản Elasticsearch. OpenSearch có API kNN và cấu hình vector riêng; **không được coi hai hệ có cú pháp đồng nhất**.

### 19.2. Truy vấn kNN

Ví dụ cấu trúc Elasticsearch, với `query_vector` phải chứa đủ 384 số:

```json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.31],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "bool": {
        "filter": [
          {"term": {"tenantId": "T1"}},
          {"term": {"status": "ACTIVE"}}
        ]
      }
    }
  }
}
```

Array 3 phần tử trên **chỉ minh họa hình dạng request**, không chạy được với mapping `dims = 384`. Khi triển khai, ứng dụng phải thay bằng vector đúng 384 chiều và kiểm tra cú pháp theo phiên bản được sử dụng.

### 19.3. Kết hợp với spatial filter

Nếu document có cả `location: geo_point` và `embedding: dense_vector`, nhu cầu có thể là:

> “10 cửa hàng có mô tả gần với nhu cầu, nhưng chỉ trong bán kính 3 km và thuộc tenant T1.”

Tùy engine, có thể dùng filter không gian trong query kNN hoặc thực hiện retrieval nhiều bước. Cần xác định:

- Spatial filter xảy ra **trước hay sau ANN**?
- Có đủ 10 kết quả hợp lệ không?
- Tăng `num_candidates` có cải thiện recall không?
- Nếu radius rất nhỏ, exact distance trên tập geo candidates có tốt hơn không?
- Các kết quả có cần kiểm tra quyền/trạng thái mới nhất không?

Không thể chỉ đưa hai index vào schema rồi mặc định query planner kết hợp chúng tối ưu trong mọi trường hợp.

## 20. Chỉ mục vector có cần nguồn dữ liệu riêng không?

Nhiều hệ sử dụng **database nguồn + vector store dẫn xuất**:

~~~text
Product Database (source of truth)
          |
          v
Change event / CDC / outbox
          |
          v
Embedding pipeline
          |
          v
Vector index / store
          |
          v
Retrieval API
          |
          v
Kiểm tra quyền, giá, tồn kho từ nguồn
~~~

### 20.1. Version của vector

Một vector phụ thuộc:

- Nội dung gốc;
- Embedding model;
- Cách chunk;
- Chuẩn hóa văn bản/ảnh;
- Metadata liên quan.

Nếu product description đổi từ v7 sang v8, vector v7 không còn biểu diễn nội dung mới.

Metadata có thể gồm:

```json
{
  "productId": "P100",
  "sourceVersion": 8,
  "embeddingModelVersion": "model-v3",
  "chunkerVersion": "split-v2"
}
```

Consumer cần ngăn job embedding cũ hoàn thành muộn ghi đè vector mới. Một cách là ghi vector theo phiên bản và công bố **active version** sau khi mọi chunk sẵn sàng, với cơ chế chuyển phiên bản được bảo vệ phù hợp.

### 20.2. Khi đổi embedding model

Không nên mặc định vector do model A tạo có thể tìm chung với vector model B, ngay cả khi cả hai có cùng số chiều. Hai mô hình có thể học các không gian không tương thích.

Một kế hoạch:

1. Tạo index/namespace mới.
2. Chụp nguồn có mốc thay đổi.
3. Tính embedding mới toàn bộ dữ liệu cần thiết.
4. Bắt kịp sự kiện đang phát sinh.
5. Đo recall/relevance, latency và chi phí.
6. Chuyển query embedding + vector index sang cùng model.
7. Dọn index cũ khi an toàn.

### 20.3. Xóa dữ liệu và vector mồ côi

Một tài liệu dài sinh 12 chunk. Khi nguồn xóa tài liệu, xóa một vector ID không đủ.

Cần xóa:

- Toàn bộ chunk thuộc document;
- Những phiên bản embedding cũ;
- Metadata/cache liên quan;
- Bản sao ở các hệ khác theo chính sách.

Nếu pipeline dùng at-least-once events, phải có cơ chế ngăn một event upsert cũ làm sống lại vector đã xóa. Một version marker/tombstone hoặc quy trình replay đúng thứ tự có thể cần thiết.

## 21. Hybrid search: spatial, vector và từ khóa

Một trường hợp thực tế:

> “Tìm điểm bảo dưỡng xe máy gần vị trí hiện tại, có hỗ trợ sửa xe điện, đang hoạt động và phù hợp mô tả sự cố *xe khó khởi động sau mưa*.”

Yêu cầu bao gồm:

- **Không gian:** trong bán kính 5 km.
- **Text/semantic:** nội dung sửa chữa gần với câu hỏi.
- **Metadata:** hỗ trợ xe điện.
- **Trạng thái:** đang hoạt động.
- **Authorization/tenant:** chỉ đối tác được phép hiển thị.

### 21.1. Filter-first

~~~text
Spatial + metadata filter
        |
        v
200 cửa hàng hợp lệ
        |
        v
Exact/vector similarity trên 200 cửa hàng
        |
        v
Top 10
~~~

Phù hợp nếu spatial filter rất chọn lọc và engine có thể tính similarity trên tập nhỏ mà không tốn nhiều chi phí.

### 21.2. Vector-first

~~~text
ANN top-500 cửa hàng gần nghĩa
        |
        v
Spatial + metadata + ACL filter
        |
        v
Có thể còn rất ít cửa hàng
~~~

Hạn chế là top-500 toàn cục có thể không chứa đủ các cửa hàng trong bán kính. Kết quả sau filter có thể thiếu, dù quanh người dùng có nhiều cửa hàng phù hợp.

Vector-first phù hợp hơn khi filter ít chọn lọc hoặc engine hỗ trợ **filtered ANN** đúng phạm vi, với recall đã được đo.

### 21.3. Parallel retrieval + fusion

~~~text
                  User query
                      |
          +-----------+------------+
          |                        |
          v                        v
   Keyword/spatial query      Vector query
          |                        |
          v                        v
   Candidate set A           Candidate set B
          |                        |
          +-----------+------------+
                      |
           Merge + dedup + rerank
                      |
            Apply strict constraints
                      |
                   Top 10
~~~

Một kỹ thuật hợp nhất phổ biến là **Reciprocal Rank Fusion (RRF)**, dựa trên thứ hạng từ các bộ truy xuất thay vì cộng trực tiếp những score có thang đo khác nhau.

Công thức ý tưởng:

\[
RRF(d)=\sum_{r\in R}\frac{1}{k+\operatorname{rank}_r(d)}
\]

Trong đó `R` là tập danh sách ranking, `k` là hằng số làm mượt do hệ thống chọn. Không nên nhầm `k` của RRF với số kết quả top-k.

### 21.4. Các ràng buộc cứng phải được áp dụng đúng

Một document rất giống về ngữ nghĩa nhưng:

- Ngoài vùng phục vụ;
- Không thuộc tenant;
- Bị khóa;
- Đã hết quyền hiển thị;
- Không còn hàng;

không nên được trả chỉ vì vector score cao.

Cần phân biệt:

- **Hard filter:** điều kiện bắt buộc, không được vi phạm.
- **Soft relevance:** tiêu chí xếp hạng có thể đánh đổi.
- **Post-validation:** kiểm tra lại dữ liệu mới nhất khi chuẩn bị thực hiện hành động quan trọng.

Nếu post-filter nghiêm ngặt làm còn ít hơn k kết quả, hệ có thể cần mở rộng candidate retrieval hoặc chạy phương án khác, không được tự bỏ qua hard filter để đủ số lượng.

## 22. Khi nào spatial index phù hợp?

### 22.1. Phù hợp

- Tìm các địa điểm trong một radius.
- Tìm nhà hàng, cửa hàng, điểm nhận hàng gần người dùng.
- Kiểm tra điểm thuộc vùng phục vụ.
- Geofencing cơ bản.
- Tìm sự kiện/thiết bị trong bounding box bản đồ.
- Tính thống kê theo cell hoặc khu vực.
- Chọn ứng viên cho routing hoặc tối ưu hành trình.

### 22.2. Cần cân nhắc giải pháp khác

- Routing theo mạng đường, giao thông thời gian thực.
- Quy hoạch địa lý/địa chính chuyên sâu.
- Phân tích đa giác phức tạp số lượng lớn.
- Dữ liệu raster, ảnh vệ tinh.
- Tính toán hình học đòi hỏi CRS/chuyển đổi chính xác đặc biệt.
- Bài toán theo không gian–thời gian cần đánh giá cả time index và chính sách lưu.

Spatial index hỗ trợ **tra cứu đối tượng liên quan tới hình học**, không tự giải bài toán tối ưu tuyến đường, điều phối đội xe hoặc quy tắc pháp lý vùng.

### 22.3. Khi không cần spatial index

Nếu ứng dụng chỉ có 20 địa điểm cố định, tính khoảng cách trực tiếp với từng điểm có thể đơn giản hơn triển khai một database geospatial. Index hữu ích khi tập dữ liệu/tần suất truy vấn đủ lớn hoặc cần nhiều điều kiện hình học.

Một bài toán “địa điểm cùng quận” có thể được giải bằng field `districtId` nếu đó là định nghĩa nghiệp vụ mong muốn. Không cần polygon point-in-polygon trong mọi trường hợp.

## 23. Khi nào vector index phù hợp?

### 23.1. Phù hợp

- Tìm kiếm ngữ nghĩa khi từ ngữ khác nhưng nội dung giống.
- Tìm ảnh/audio tương tự.
- Retrieval tài liệu cho hỏi đáp.
- Khám phá sản phẩm tương đồng.
- Recommendation khi có embedding phù hợp.
- Tìm các đối tượng gần nhau theo đặc trưng ML.

### 23.2. Không phù hợp làm nguồn quyết định cuối

- Tra cứu ID chính xác;
- Kiểm tra tính duy nhất;
- So sánh giá tiền chính xác;
- Phân quyền;
- Kiểm tra hàng tồn kho;
- Xác nhận dữ liệu pháp lý/giao dịch;
- Tính tổng/số lượng chính xác;
- Tìm văn bản bắt buộc chứa một mã định danh cụ thể.

Nếu query là “tài liệu có mã hồ sơ `INV-2026-001`”, một **term/keyword index chính xác** thường phù hợp hơn vector. Vector có thể xếp gần các mã trông tương tự nhưng sai một ký tự, điều không thể chấp nhận với tra cứu định danh.

### 23.3. Khi không cần vector index

Nếu có vài trăm sản phẩm, hoặc chỉ cần tìm từ khóa rõ ràng, full-text/keyword search có thể đủ. Embedding và ANN thêm:

- Pipeline tạo vector;
- Chi phí tính embedding;
- Chi phí index/RAM;
- Versioning;
- Đánh giá relevance;
- Khả năng stale và đồng bộ xóa.

Không nên dùng vector search chỉ vì nó là công nghệ mới nếu truy vấn có thể giải quyết rẻ hơn và chính xác hơn bằng cách khác.

## 24. Spatial và vector đều có “nearest neighbor” nhưng khác ý nghĩa

Hai câu hỏi có vẻ giống nhau:

1. “Địa điểm nào **gần tôi** nhất?”
2. “Tài liệu nào **gần câu hỏi** nhất?”

Nhưng ý nghĩa của “gần” hoàn toàn khác.

| Thuộc tính | Spatial nearest | Vector nearest |
|---|---|---|
| Không gian | Vị trí địa lý/hình học | Đặc trưng nhiều chiều |
| Đơn vị | Mét/km hoặc đơn vị CRS | Metric vector, thường không có đơn vị vật lý |
| Input | Tọa độ hoặc geometry | Embedding của query |
| Chất lượng | Độ chính xác tọa độ, CRS, tính toán khoảng cách | Model relevance, metric, ANN recall |
| Sai lệch thường gặp | Đảo lat/lon, sai CRS, bbox false positives | Model drift, dimension sai, ANN miss |
| Kiểm tra sau | Distance/geometry exact, trạng thái | ACL, keyword/metadata, nguồn dữ liệu |
| Ví dụ | 10 cây ATM gần nhất | 10 câu hỏi tương tự |

Không được diễn giải cosine similarity 0,9 như “địa điểm cách 0,9 km”. Đó là hai hệ đo khác nhau.

## 25. Thiết kế dữ liệu và partition/shard key

### 25.1. Spatial index không thay partition key

Giả sử 30 triệu điểm giao hàng thuộc 2.000 tenant. Một truy vấn chỉ cần các điểm của tenant T1 trong bán kính 3 km.

Nếu dữ liệu được phân vùng theo tenant, database có thể thu hẹp phạm vi trước khi xử lý không gian. Nhưng nếu một tenant có hàng triệu điểm tập trung ở một khu vực, có nguy cơ hot partition hoặc chênh lệch tải.

Cần thiết kế theo:

- Tần suất truy vấn theo tenant;
- Phân phối tọa độ;
- Nhu cầu khu vực địa lý;
- Mật độ điểm không đều;
- Khả năng engine kết hợp shard key và spatial index;
- Vùng dữ liệu/địa lý cần lưu;
- Chi phí ghi vị trí cập nhật liên tục.

### 25.2. Geohash/cell làm partition key

Một ứng dụng có thể tổ chức dữ liệu theo mã cell:

```text
PK = REGION#cellId
SK = locationId
~~~

Ưu điểm: tìm các điểm cùng vùng cell. Nhưng có vấn đề:

- Truy vấn radius cắt nhiều cell;
- Điểm ngay biên có hàng xóm ở partition khác;
- Cell trung tâm đô thị có thể rất nóng;
- Đổi vị trí giữa cell cần xóa khóa cũ và thêm khóa mới;
- Các mức zoom cần kích thước cell khác nhau.

Đây là một giải pháp access pattern cụ thể, không phải thay thế tổng quát cho spatial index gốc của engine.

### 25.3. Vector sharding

Nếu vector store có hàng trăm triệu vector, cần xét:

- Partition theo tenant/model;
- Phân phối embedding không đều;
- Chi phí truy vấn fan-out và merge top-k;
- Replicas cho QPS cao;
- Rebuild hoặc chuyển model;
- Có cần lọc geo/ACL xuyên shard không;
- Recall khi tìm ANN độc lập từng shard rồi merge.

Lấy top-k mỗi shard rồi merge có thể phù hợp trong một số cấu hình, nhưng chi phí/recall tùy candidate count và thuật toán. Không nên mặc định một `k=10` ở mỗi shard luôn đủ cho mọi kiểu filter/re-ranking.

## 26. Cập nhật, xóa, TTL và tính nhất quán của chỉ mục

### 26.1. Read model dẫn xuất có thể trễ

Một product đổi mô tả:

~~~text
Source product v8
       |
       v
Outbox / CDC
       |
       v
Embedding job
       |
       v
Vector index v8
~~~

Trong khoảng giữa source commit và vector visibility, query có thể còn trả vector v7. Một spatial index nội bộ cập nhật cùng transaction nguồn có thể có thời điểm nhìn thấy khác với search index bên ngoài.

Ứng dụng cần nêu **freshness SLO** cho từng read model, không gộp mọi chỉ mục dưới lời hứa nhất quán tức thì.

### 26.2. Metadata cập nhật mà không đổi embedding

Nếu `price` hoặc `status` thay đổi nhưng nội dung dùng để embedding không đổi, có thể chỉ cần cập nhật metadata hoặc lookup mới nhất từ nguồn. Việc re-embed mọi lần đổi giá thường tốn tài nguyên mà không cải thiện ngữ nghĩa.

Ngược lại, nếu `description` đổi, vector cũ có thể không còn phù hợp. Nên lưu content hash/sourceVersion để xác định lúc nào phải tính lại.

### 26.3. Spatial data cập nhật liên tục

Một vị trí xe thay đổi nhiều lần/giây. Cập nhật index không gian quá thường xuyên có thể làm tăng write amplification hoặc tạo độ trễ.

Các lựa chọn:

- Chỉ cập nhật khi xe di chuyển quá một ngưỡng.
- Batch thay đổi theo khoảng rất ngắn.
- Lưu latest location ở nguồn nhanh, index phục vụ coarse candidate.
- Đọc lại vị trí hiện tại khi chốt tác vụ.
- Dùng TTL/lastSeen để loại xe không còn hoạt động.

Ngưỡng cập nhật phụ thuộc độ chính xác nghiệp vụ. Không được tự giảm tần suất nếu hệ cần an toàn hoặc điều khiển thời gian thực.

### 26.4. Xóa và chống hồi sinh

Nếu document bị xóa nhưng event upsert cũ đến sau, vector hoặc spatial read model có thể tạo lại đối tượng. Cần ID ổn định, version guard/tombstone hoặc cơ chế replay đúng thứ tự.

TTL ở database nguồn không tự xóa bản sao search/vector nếu pipeline không truyền sự kiện xóa hoặc có quy trình đối soát tương ứng.

## 27. Đánh giá một thiết kế spatial index

Giả sử yêu cầu:

> “Hiển thị tối đa 30 điểm nhận hàng đang mở, thuộc tenant T1, trong bán kính 5 km, sắp gần nhất trước.”

Hãy viết ra hợp đồng:

- Input: tenantId, tọa độ người dùng, radiusMeters.
- Hard filters: tenant, trạng thái được phép, radius.
- Sort: khoảng cách tăng dần, có tie-break bằng storeId nếu cần ổn định.
- Output: storeId, tên, vị trí, khoảng cách.
- Freshness: điểm mở/đóng cửa thay đổi nhanh thế nào?
- Index: location + metadata filters được hỗ trợ ra sao?
- Phân trang: engine hỗ trợ geo-near cursor nào? Có thể thay đổi dữ liệu giữa các trang không?
- Limit: tối đa 30.
- Boundary: điểm đúng trên bán kính xử lý thế nào?

### 27.1. Trường hợp thiếu chỉ mục

Nếu tập có 10 triệu store, truy vấn tính khoảng cách đến mọi store sẽ tốn kém. Spatial index có thể giảm candidate.

### 27.2. Trường hợp index có nhưng lọc kém

Nếu 99% store đã đóng cửa, tìm 30 store mở có thể cần xem nhiều candidate. Cần xem engine có hỗ trợ filter status hiệu quả cùng spatial index hay cần thay đổi cách lưu active stores.

### 27.3. Trường hợp vị trí hợp lệ nhưng dữ liệu cũ

Nếu store đã ngừng hoạt động nhưng index chưa nhận event mới, query có thể trả nó. Trước khi tạo đơn, kiểm tra trạng thái ở nguồn authoritative.

### 27.4. Trường hợp vượt biên kinh độ

Vùng quanh kinh tuyến ±180° không thể luôn biểu diễn bằng một điều kiện `minLongitude <= lon <= maxLongitude` đơn giản. Nếu vùng băng qua đường đổi ngày, cần query geometry/cell covering đúng, không dùng bounding box ngây thơ.

## 28. Đánh giá một thiết kế vector index

Giả sử yêu cầu:

> “Tìm 10 hướng dẫn sửa lỗi tương đồng với câu hỏi của người dùng, chỉ từ bộ tài liệu họ có quyền xem.”

Hợp đồng:

- Dữ liệu: chunk nội dung tài liệu, metadata ACL.
- Query: embedding từ cùng model.
- Metric: cosine/dot/L2 theo model.
- Filter: user/tenant/role/document visibility.
- Top-k: 10.
- SLO: p95 latency, freshness sau khi cập nhật.
- Quality: recall@10 so exact baseline và relevance với câu hỏi thật.
- Index: HNSW/IVF/flat theo khả năng sản phẩm.
- Đồng bộ: CDC/outbox; re-embed khi nội dung/model đổi.
- Security: kiểm tra lại quyền tại thời điểm trả nội dung.
- Failure: vector index chưa sẵn sàng hoặc trả không đủ ứng viên.

### 28.1. Khi metadata filter rất chọn lọc

Nếu một người chỉ có quyền trên 200 chunk, exact search sau khi lấy đúng 200 vector có thể hiệu quả và có recall tuyệt đối theo metric. ANN toàn kho rồi lọc sau có thể tệ hơn.

### 28.2. Khi metadata filter ít chọn lọc

Nếu 90% tài liệu được phép xem, ANN toàn corpus với pre-filter thích hợp có thể rất hiệu quả. Vẫn cần đo recall, không suy từ kết quả trung bình.

### 28.3. Khi embedding kém

Nếu model không hiểu thuật ngữ chuyên môn, tuning `efSearch` lên rất cao chỉ giúp tìm chính xác hơn **những hàng xóm theo một không gian embedding chưa phù hợp**. Cần cải thiện dữ liệu/model/chunking hoặc kết hợp lexical search.

### 28.4. Khi cần nguồn trích dẫn

Vector index có thể trả chunk gần nhất; API cần lấy nội dung gốc, đường dẫn, version, metadata nguồn và quyền truy cập để trình bày đúng. Không nên coi một vector hay score là bằng chứng đầy đủ về độ tin cậy của câu trả lời.

## 29. Theo dõi query plan và chỉ số vận hành

### 29.1. Với chỉ mục không gian

Quan sát:

- Có dùng spatial index hay full scan?
- Số candidate từ bounding box/cell.
- Số candidate bị loại ở bước exact geometry.
- Khoảng cách được tính bao nhiêu lần?
- Số partition/shard cần đọc?
- Chi phí sort theo distance.
- Tỷ lệ query theo radius 100 m, 1 km, 10 km, 100 km.
- Phân phối mật độ địa lý: đô thị với nông thôn.
- Latency p95/p99.
- Chi phí cập nhật vị trí.

Một radius 100 km có thể chạm phần lớn dữ liệu, khiến index ít có tác dụng hơn radius 1 km. Index chỉ hữu ích khi nó thu hẹp phạm vi đủ đáng kể.

### 29.2. Với vector index

Quan sát:

- Recall@k với bộ query kiểm chứng.
- p50/p95/p99 theo k và filter selectivity.
- Candidate count, efSearch/nprobe hoặc cấu hình tương tự.
- Bộ nhớ, kích thước index, cache hit.
- Thời gian build/rebuild.
- Chi phí insertion/deletion.
- Số vector theo embeddingModelVersion.
- Tỷ lệ vector nguồn đã stale/thiếu.
- Số chunk orphan.
- Thời gian end-to-end từ nguồn sửa đến index nhìn thấy.
- Tỷ lệ search trả ít hơn k kết quả sau hard filters.

### 29.3. Tránh đo mỗi một query

Một benchmark tốt phải có truy vấn:

- Vùng thưa và vùng cực dày.
- Radius nhỏ/lớn.
- Polygon đơn giản/phức tạp.
- Tenant rất nhỏ và rất lớn.
- Filter metadata chọn lọc cao/thấp.
- Dữ liệu mới và dữ liệu lâu năm.
- Query vector thuộc chủ đề phổ biến/hiếm.
- Delete/update đang diễn ra.
- Tải nhiều client đồng thời.

Tối ưu theo truy vấn “đẹp” nhất có thể khiến p99 ở workload thật rất tệ.

## 30. Những lỗi thiết kế thường gặp

### 30.1. Spatial

**Đảo longitude và latitude.** GeoJSON dùng [lon, lat]; nhiều API khác có tham số `lat/lon` rõ ràng.

**Coi độ là mét.** Khoảng cách dựa trên CRS phải dùng đơn vị chính xác.

**Chỉ kiểm tra bounding box rồi coi là trong polygon.** Bounding box có false positives.

**Chỉ xét một geohash cell.** Các điểm sát biên nằm ở cell khác có thể bị bỏ sót.

**Coi khoảng cách đường chim bay là thời gian đi xe.** Cần routing nếu nghiệp vụ cần đường đi thật.

**Chọn index mà bỏ qua tenant/status.** Candidate có thể rất nhiều hoặc trả dữ liệu không được phép.

**Để điểm stale đại diện cho vị trí live.** Phải quản lý lastSeen và nguồn cập nhật.

**Tưởng spatial index thay thế GIS đầy đủ.** Một số phân tích topology/raster/CRS cần hệ chuyên dụng.

### 30.2. Vector

**Cho rằng vector gần nhau đồng nghĩa câu trả lời đúng.** Similarity không phải xác minh sự thật.

**Dùng score như xác suất.** Score phụ thuộc metric/model/engine.

**Trộn vector của hai model.** Có thể khác không gian dù cùng số chiều.

**Dùng ANN cho lookup chính xác.** Mã đơn hàng và ID cần exact index.

**Tìm top-k toàn cục rồi lọc ACL.** Có thể còn ít kết quả và không đạt recall trong tập được phép.

**Chỉ đo latency mà không đo recall.** ANN có thể rất nhanh vì bỏ qua nhiều hàng xóm.

**Dùng vector index mà không theo dõi source version.** Nội dung và embedding có thể lệch nhau.

**Đổi chunking mà không dọn chunk cũ.** Có thể trả nội dung đã lỗi thời.

**Coi HNSW là graph database nghiệp vụ.** Các cạnh HNSW biểu diễn similarity, không phải quan hệ domain.

### 30.3. Chung cho cả hai

**Index không thay thế nguồn sự thật.** Dữ liệu vị trí, giá, tồn kho và quyền truy cập cần authoritative validation theo yêu cầu.

**Index luôn hỗ trợ mọi operator.** Chức năng phụ thuộc engine, phiên bản và cấu hình.

**Chỉ tạo index là đủ tối ưu.** Phải xét query plan, filter, shard, dữ liệu và tải ghi.

**Không cần đối soát vì có CDC.** Pipeline có thể bỏ sót, xử lý trùng hoặc đến sai thứ tự; cần đo freshness và reconciliation.

## 31. Quy trình lựa chọn chỉ mục phù hợp

### Bước 1: Viết query như một câu hỏi nghiệp vụ

Ví dụ:

> “Người dùng muốn 10 cửa hàng gần nhất trong 3 km, thuộc danh mục sửa xe, còn mở cửa.”

Tách ra tọa độ, radius, hard filter, sort, số kết quả và độ mới.

Hoặc:

> “Người dùng muốn 10 tài liệu tương tự câu hỏi, trong những tài liệu họ có quyền xem.”

Tách ra embedding, metric, ACL, top-k, model version và relevance.

### Bước 2: Phân loại điều kiện

| Điều kiện | Loại đường truy cập thường phù hợp |
|---|---|
| `id = X` | Exact/key index |
| `createdAt BETWEEN A AND B` | Range/index theo thời gian |
| Có chứa từ khóa chính xác/phrase | Full-text/keyword |
| Tọa độ nằm trong bán kính | Spatial index |
| Geometry giao với polygon | Spatial geometry index |
| Ngữ nghĩa gần mô tả | Vector index |
| Quan hệ nhiều bước giữa thực thể | Graph traversal/index anchor |
| Tổng doanh thu theo tháng | OLAP/aggregate |

Một query có thể có nhiều điều kiện thuộc nhiều nhóm. Cần chọn **kế hoạch kết hợp** dựa trên độ chọn lọc, không luôn đưa mọi thứ vào một vector.

### Bước 3: Xác định độ chọn lọc của hard filters

Nếu spatial radius lọc từ 10 triệu cửa hàng còn 200, spatial-first có thể rất hợp lý. Nếu radius phủ 9 triệu cửa hàng nhưng semantic query chỉ có vài nghìn candidate gần, vector-first/filtered ANN có thể đáng thử.

Tuy nhiên, chọn thứ tự retrieval phải giữ **đúng tập kết quả yêu cầu**: post-filter từ tập ANN quá nhỏ có thể thiếu các ứng viên phù hợp.

### Bước 4: Xác định mức chính xác

- Cần **đúng tuyệt đối** điểm nằm trong vùng?
- Có chấp nhận ANN recall@10 là 0,95?
- Có cần snapshot của tập kết quả?
- Có chấp nhận vị trí cũ 5 giây?
- Bắt buộc không lộ tài liệu ngoài ACL?

Độ chính xác địa lý, chất lượng ANN và tính đúng của quyền truy cập là các mục tiêu khác nhau.

### Bước 5: Chọn sản phẩm theo khả năng thật

Kiểm tra:

- Kiểu dữ liệu và CRS.
- Operator point/geometry.
- Geo sorting, radius units.
- ANN metric và dimension.
- Pre-filter/metadata filter.
- Khả năng kết hợp spatial + vector + keyword.
- Partition/shard support.
- Update/delete behavior.
- Query consistency/freshness.
- Khả năng rebuild/reindex.
- Giới hạn index size, memory, throughput và chi phí.

### Bước 6: Đo trên dữ liệu đại diện

Chạy plan/benchmark cho trường hợp dễ, khó và vùng dữ liệu dày đặc. Đo:

- Latency;
- Recall/relevance nếu là vector;
- Exact geometry correctness nếu là spatial;
- Memory/disk/RU/DB hits;
- Chi phí cập nhật;
- Sai lệch do nguồn thay đổi.

### Bước 7: Thiết kế vận hành và sửa sai

Cần event/CDC, idempotent upsert, version, xóa/tombstone, giám sát lag, đối soát và rebuild. Một index được benchmark nhanh trên dữ liệu tĩnh nhưng không thể cập nhật an toàn theo nguồn sẽ khó dùng trong production.

## 32. Bài tập thực hành

### Bài tập 1: thứ tự tọa độ

Một ứng dụng ghi GeoJSON:

```json
{
  "type": "Point",
  "coordinates": [10.7769, 106.7009]
}
```

**Câu hỏi:** Vấn đề ở đâu?

**Gợi ý:** Trong GeoJSON, thứ tự thường là [longitude, latitude]. Vĩ độ 106.7009° không hợp lệ đối với hệ kinh-vĩ độ. Cần [106.7009, 10.7769].

### Bài tập 2: radius khác bounding box

Có một cửa hàng nằm trong hình chữ nhật bao quanh hình tròn bán kính 3 km nhưng ở một góc hình chữ nhật, cách tâm 3,8 km.

**Câu hỏi:** Có được coi cửa hàng nằm trong bán kính không?

**Gợi ý:** Không. Bounding box chỉ là lọc thô; cần kiểm tra khoảng cách đúng theo CRS và đơn vị.

### Bài tập 3: điểm ở biên geohash

Hai cửa hàng cách nhau 30 m nhưng nằm ở hai cell geohash khác nhau. Truy vấn chỉ kiểm tra cell chứa tâm.

**Câu hỏi:** Rủi ro gì?

**Gợi ý:** False negative — cửa hàng gần có thể bị bỏ sót. Cần bao phủ cell lân cận và refine bằng khoảng cách/hình học.

### Bài tập 4: vị trí gần và thời gian di chuyển

Cửa hàng A cách 900 m theo đường chim bay nhưng phải đi 6 km qua cầu. Cửa hàng B cách 1,5 km và có đường đi 2 km.

**Câu hỏi:** Spatial nearest theo tọa độ có chọn điểm giao nhanh nhất không?

**Gợi ý:** Không chắc. Có thể dùng spatial index tạo candidate rồi tính routing time.

### Bài tập 5: cosine và dot product

Hai vector không được chuẩn hóa có cùng hướng nhưng độ lớn rất khác nhau.

**Câu hỏi:** Dot product và cosine có nhất thiết xếp hạng ứng viên giống nhau không?

**Gợi ý:** Không. Dot chịu ảnh hưởng norm, cosine chủ yếu đo hướng; chỉ có quan hệ thứ tự tương đương trong những điều kiện chuẩn hóa phù hợp.

### Bài tập 6: recall@5

Exact top-5 là `[A,B,C,D,E]`. ANN trả `[A,C,E,F,G]`.

**Câu hỏi:** Recall@5 là bao nhiêu?

**Gợi ý:** Có ba phần tử trùng trong top-5: 3/5 = 0,6.

### Bài tập 7: lọc tenant sau ANN

Toàn kho có 10 triệu vector nhưng chỉ 1.000 vector thuộc tenant T1. ANN lấy top-50 toàn cục rồi lọc T1, còn 0 kết quả.

**Câu hỏi:** Có thể kết luận T1 không có tài liệu tương tự không?

**Gợi ý:** Không. Top-50 toàn cục không phải top-k trong tập T1. Cần filtered ANN, namespace theo tenant hoặc exact search trên tập tenant nếu đủ nhỏ.

### Bài tập 8: dùng vector tìm ID

Ứng dụng muốn tìm chính xác hóa đơn có mã `INV-2026-1001`.

**Câu hỏi:** Có nên dùng vector similarity làm phương án chính?

**Gợi ý:** Không. Dùng exact index cho ID. Vector có thể trả hóa đơn mã gần giống nhưng không đúng.

### Bài tập 9: HNSW tuning

Một hệ tăng `efSearch` và thấy recall@10 tăng từ 0,92 lên 0,98, nhưng p95 latency tăng từ 40 ms lên 85 ms.

**Câu hỏi:** Nên quyết định thế nào?

**Gợi ý:** So với SLO latency, yêu cầu recall và workload thật. Không có tham số tốt nhất độc lập với mục tiêu sản phẩm.

### Bài tập 10: embedding version

Một nửa document dùng embedding model A, nửa còn lại dùng model B, cả hai 768 chiều.

**Câu hỏi:** Có được đưa vào một index và dùng query model A để tìm toàn bộ không?

**Gợi ý:** Không mặc định. Cùng số chiều không đảm bảo không gian tương thích; nên tách/di chuyển model và kiểm chứng chất lượng.

### Bài tập 11: xóa chunk

Một tài liệu từng có 8 vector chunk, sau cập nhật chỉ còn 5 chunk.

**Câu hỏi:** Upsert 5 vector mới đã đủ chưa?

**Gợi ý:** Chưa. Cần dọn 3 chunk cũ hoặc dùng quản lý active version/manifest để chúng không còn được truy vấn.

### Bài tập 12: store không còn mở

Spatial index trả cửa hàng cách 200 m nhưng trạng thái mở cửa ở index chậm 10 phút; nguồn đã đóng.

**Câu hỏi:** Khi chốt đơn nên dựa vào đâu?

**Gợi ý:** Query spatial để tìm candidate, nhưng phải kiểm tra trạng thái giao dịch/khả năng phục vụ tại nguồn authoritative.

### Bài tập 13: không gian + ngữ nghĩa

Yêu cầu tìm 10 cửa hàng trong 1 km có mô tả gần câu “sửa máy ảnh film”, nhưng radius chỉ còn 120 cửa hàng từ 5 triệu cửa hàng.

**Câu hỏi:** Hướng retrieval nào đáng benchmark?

**Gợi ý:** Spatial/metadata-first rồi exact vector similarity trên 120 ứng viên có thể rất phù hợp. So với filtered ANN và đo latency/relevance.

### Bài tập 14: index versus graph

Một ứng dụng tìm các cửa hàng gần người dùng, sau đó tìm những nhà cung cấp liên kết với từng cửa hàng qua quan hệ `SUPPLIED_BY`.

**Câu hỏi:** Spatial index có tự tìm nhà cung cấp qua quan hệ không?

**Gợi ý:** Không. Spatial index tìm cửa hàng theo vị trí; graph traversal hoặc query dữ liệu quan hệ thực hiện phần liên kết.

### Bài tập 15: thiết kế đánh giá

Một team báo “vector search trả top 10 chỉ mất 12 ms”.

**Câu hỏi:** Còn thiếu những thông số nào trước khi kết luận hệ tốt?

**Gợi ý:** Recall@10, relevance, filter selectivity, p95/p99, RAM/index size, throughput, update/delete cost, model version, dữ liệu đại diện và khả năng kiểm soát ACL.

### Bài tập 16: query mất kết quả do post-filter

ANN top 100 toàn bộ kho, lọc `isOpen=true` và `distance<=2km` chỉ còn 2 record. Nhưng trong vùng có 50 cửa hàng đang mở.

**Câu hỏi:** Có nên bỏ filter để đủ 10 kết quả?

**Gợi ý:** Không. Filter là yêu cầu bắt buộc. Cần retrieval/filtering đúng phạm vi: geo-first, filtered ANN hoặc tăng candidate có kiểm chứng, không trả kết quả sai nghiệp vụ.

## 33. Tổng kết

**Chỉ mục không gian** phù hợp với những truy vấn phụ thuộc tọa độ và hình học: điểm gần, đối tượng trong vùng, đường giao với polygon, bounding box hoặc geofence. Để dùng đúng, cần biết **CRS, thứ tự latitude/longitude, đơn vị khoảng cách, cấu trúc hình học và bước refine chính xác**. Một bounding box hoặc cell covering chỉ là cách thu hẹp ứng viên, không tự chứng minh mọi quan hệ không gian.

**Chỉ mục vector** phù hợp với truy vấn gần nhau trong không gian embedding, đặc biệt semantic search và retrieval đa phương tiện. ANN như HNSW/IVF/PQ giúp cải thiện latency/khả năng mở rộng nhưng có đánh đổi về **recall, tài nguyên và chi phí cập nhật**. Phải chọn metric đúng với embedding model, giữ phiên bản vector, đo recall@k và bảo vệ metadata filters/ACL.

Trong NoSQL, cả hai nhóm chỉ mục chỉ hữu ích khi được đặt trong **đường truy cập hoàn chỉnh**: lọc tenant, trạng thái, quyền truy cập, phân vùng, sắp xếp, phân trang, đồng bộ dữ liệu nguồn và xử lý xóa. Với truy vấn kết hợp vị trí và ngữ nghĩa, hãy đo các phương án **spatial-first, filtered vector search và hybrid retrieval**, thay vì giả định một chỉ mục có thể tối ưu mọi điều kiện.

Nguyên tắc quan trọng nhất là: **hãy chọn chỉ mục dựa trên phép truy vấn và mức độ chính xác cần đạt, không chọn dựa trên độ phổ biến của công nghệ**. Bảo đảm tính đúng của điều kiện địa lý, quyền truy cập và giao dịch luôn quan trọng hơn việc nhận một tập ứng viên gần đúng thật nhanh.

