# Truy vấn lân cận bằng $near, $nearSphere và stage $geoNear trong MongoDB

## 1. Bài toán: tìm những địa điểm gần một vị trí

Giả sử một ứng dụng lưu vị trí các điểm nhận hàng trên bản đồ. Người dùng gửi tọa độ hiện tại và muốn tìm **10 điểm đang hoạt động gần nhất trong bán kính 3 km**, đồng thời hiển thị khoảng cách tới từng điểm.

Một document có thể được lưu như sau:

```javascript
{
  _id: ObjectId("66a000000000000000000295"),
  name: "Điểm nhận hàng A",
  category: "pickup",
  status: "OPEN",
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
```

Trong MongoDB, bài toán này không nên giải bằng cách đọc toàn bộ document lên ứng dụng, tự tính khoảng cách của từng điểm rồi sort. MongoDB có **geospatial indexes** và các cơ chế truy vấn lân cận:

- **`$near`**: toán tử điều kiện trong `find()`, chọn những vị trí gần điểm cho trước và tự sắp xếp từ gần đến xa.
- **`$nearSphere`**: toán tử điều kiện trong `find()`, nhấn mạnh tính khoảng cách theo hình học mặt cầu.
- **`$geoNear`**: một **stage của aggregation pipeline**, tìm gần nhất và có thể đưa khoảng cách tính được vào kết quả để xử lý tiếp bằng `$project`, `$group`, `$limit` và những stage khác.

Ba cơ chế phục vụ những cách xây API khác nhau. Với **GeoJSON Point + index `2dsphere`**, cả `$near` và `$nearSphere` đều dùng hình học cầu; không nên coi `$near` lúc nào cũng chỉ tính trên mặt phẳng.

Sau bài học thuộc chương **Dữ liệu địa lý** của MongoDB, bạn có thể:

1. Lưu GeoJSON Point đúng cấu trúc và thứ tự tọa độ.
2. Chọn geospatial index phù hợp với GeoJSON và legacy coordinate pairs.
3. Viết `$near`, `$nearSphere` với `$geometry`, `$minDistance` và `$maxDistance`.
4. Dùng `$geoNear` với `near`, `distanceField`, `spherical`, `key`, `query` và `distanceMultiplier`.
5. Phân biệt **mét**, **radian**, **độ tọa độ** và **km**.
6. Kết hợp điều kiện lọc, giới hạn kết quả và các bước aggregation khác.
7. Tránh lỗi thiếu index, dùng sai thứ tự stage hoặc nhầm phạm vi đường chim bay với khoảng cách di chuyển thực.
8. Đánh giá hiệu năng, bảo mật và xử lý kết quả trong API Node.js.

## 2. Biểu diễn tọa độ bằng GeoJSON

### 2.1. GeoJSON Point là một object có cấu trúc xác định

MongoDB có thể lưu một vị trí địa lý theo GeoJSON:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
```

Trong mảng `coordinates`:

```text
coordinates: [ longitude, latitude ]
                kinh độ      vĩ độ
```

Đây là điểm dễ nhầm: nhiều API bản đồ hoặc giao diện người dùng nhận tham số theo thứ tự **latitude, longitude**, nhưng GeoJSON phải lưu **longitude trước, latitude sau**.

Ví dụ:

```javascript
// ĐÚNG: [kinh độ, vĩ độ]
{ type: "Point", coordinates: [106.7009, 10.7769] }

// SAI trong ví dụ này: đảo thành [vĩ độ, kinh độ]
{ type: "Point", coordinates: [10.7769, 106.7009] }
```

Với GeoJSON địa lý, kinh độ nằm trong khoảng **-180 đến 180**, vĩ độ trong khoảng **-90 đến 90**. Dữ liệu đảo thứ tự có thể bị từ chối vì vĩ độ ngoài miền hợp lệ, hoặc tệ hơn: vẫn là hai số hợp lệ nhưng đại diện **một vị trí khác**.

Các tọa độ trong bài chỉ là **dữ liệu mô phỏng quanh một khu vực đô thị** phục vụ truy vấn; các tên điểm không đại diện cho cơ sở kinh doanh thực tế.

### 2.2. Tại sao dùng GeoJSON thay cho hai field riêng?

Một thiết kế ít thuận lợi cho geospatial queries:

```javascript
{
  latitude: 10.7769,
  longitude: 106.7009
}
```

Ứng dụng có thể lưu thêm hai số này để phục vụ giao diện hoặc tích hợp, nhưng nếu muốn dùng index `2dsphere` và những toán tử ở bài này, nên có một field GeoJSON rõ ràng:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
```

GeoJSON còn có các loại hình học khác như `LineString`, `Polygon` và `MultiPoint`. Tuy nhiên, tham số **điểm tham chiếu** của các truy vấn `$near`, `$nearSphere` và `$geoNear` trong những phiên bản MongoDB mới phải là **GeoJSON `Point`**, không phải tùy ý truyền Polygon làm tâm.

### 2.3. WGS84, độ và khoảng cách

Tọa độ GeoJSON địa lý thường được biểu diễn theo hệ WGS84 với longitude và latitude tính bằng **độ**. Nhưng trong truy vấn lân cận sử dụng `$geometry` là GeoJSON Point, các tham số `$minDistance` và `$maxDistance` sử dụng **mét**.

Do đó:

```text
coordinates: [106.7009, 10.7769]  -> độ kinh/vĩ
maxDistance: 3000                 -> 3.000 mét
distanceField: "distanceMeters"    -> khoảng cách tính bằng mét
```

Không dùng `0.03` độ để thay cho bán kính `3 km`. Một độ kinh độ không tương đương một khoảng cách mét cố định ở mọi vĩ độ.

### 2.4. Tọa độ không phải địa chỉ hoặc quãng đường đi

Khoảng cách geospatial tính từ tọa độ thường là **khoảng cách địa lý theo hình học** trên mặt cầu hoặc mặt phẳng theo loại index, không phải:

- quãng đường đi bộ theo đường phố;
- thời gian đi xe trong giờ cao điểm;
- khoảng cách tránh sông, cầu, đường một chiều;
- tuyến đường có thể đi theo mạng giao thông;
- độ cao/độ sâu trong một mô hình 3D tùy ý.

Nếu ứng dụng muốn “10 cửa hàng đi bộ tới nhanh nhất”, truy vấn MongoDB có thể lấy **tập ứng viên gần theo địa lý**, rồi dùng một **routing service** khác để tính thời gian/quãng đường thực trước khi xếp hạng cuối cùng.

## 3. Geospatial indexes: 2dsphere và 2d

### 3.1. Index `2dsphere` cho tọa độ địa lý

Tạo index:

```javascript
db.pickupPoints.createIndex({
  location: "2dsphere"
});
```

`2dsphere` hỗ trợ các truy vấn địa lý trên mô hình mặt cầu và hoạt động với GeoJSON objects hoặc legacy coordinate pairs trong các điều kiện phù hợp.

Đây là lựa chọn phổ biến cho:

- điểm giao nhận gần người dùng;
- địa điểm bán hàng gần tọa độ GPS;
- POI/địa điểm quan tâm;
- vị trí xe, thiết bị, điểm dịch vụ;
- vùng địa lý và các truy vấn không gian có ý nghĩa trên bề mặt Trái Đất.

Không tạo index `{location:1}` thông thường rồi kỳ vọng `$near` có thể sử dụng nó như geospatial index. Cần **đúng loại index**.

### 3.2. Index `2d` cho mặt phẳng và legacy coordinates

Legacy coordinate pair có dạng:

```javascript
{
  pos: [10, 20]
}
```

Nếu dữ liệu biểu diễn điểm trong một **mặt phẳng Cartesian** hoặc dự án cũ dùng hệ tọa độ legacy, có thể tạo:

```javascript
db.legacyPoints.createIndex({
  pos: "2d"
});
```

Với dữ liệu legacy, cách tính hình học và **đơn vị giới hạn khoảng cách** cần tuân thủ đúng cú pháp/toán tử/index của phiên bản MongoDB. Đừng chuyển nguyên tham số mét của truy vấn GeoJSON sang legacy pair mà giả định sẽ cho kết quả tương đương.

Nếu dữ liệu thực tế là vĩ độ/kinh độ trên Trái Đất, `2dsphere` và GeoJSON là hướng thiết kế dễ hiểu, tránh các sai số hình học mặt phẳng tại khoảng cách lớn hoặc vùng gần cực/đường đổi ngày.

### 3.3. So sánh nhanh

| Tiêu chí | `2dsphere` | `2d` |
| --- | --- | --- |
| Mô hình chính | Hình học cầu | Hình học mặt phẳng |
| Dữ liệu | GeoJSON; có hỗ trợ legacy coordinates | Thường dùng legacy coordinate pairs |
| Dùng với GeoJSON `Point` trong `$near` | Có | Không; GeoJSON `$near` yêu cầu `2dsphere` |
| Truy vấn địa điểm GPS trên Trái Đất | Thường phù hợp | Không phải lựa chọn mặc định |
| Truy vấn tọa độ x-y của bản vẽ phẳng | Không phải mục tiêu chính | Phù hợp hơn |
| Đơn vị kết quả | Phụ thuộc toán tử và định dạng input; GeoJSON là mét trong ví dụ địa lý | Phụ thuộc ngữ nghĩa legacy/planar |

**Không đánh đồng index và toán tử**: `$nearSphere` không có nghĩa MongoDB có một loại index riêng tên `nearSphere`. Nó là **toán tử**, vẫn cần index geospatial tương thích.

### 3.4. Dữ liệu sai có thể làm tạo index thất bại

Các lỗi cần phát hiện trước khi tạo `2dsphere` index:

- Field `coordinates` không phải mảng đúng cấu trúc.
- Longitude/latitude ngoài khoảng hợp lệ.
- Dùng string thay vì số.
- GeoJSON `type` sai hoặc không tương thích.
- GeoJSON có tọa độ rỗng/mảng lồng sai.
- Trộn nhiều cách biểu diễn không được quản lý trong cùng field.

Ví dụ nên được từ chối tại tầng API:

```javascript
{ type: "Point", coordinates: ["106.7", "10.77"] }
{ type: "Point", coordinates: [106.7, 102.0] }
{ type: "Point", coordinates: [null, 10.77] }
{ type: "LineString", coordinates: [106.7, 10.77] }
```

Một field thiếu `location` có hành vi indexing khác một field **có giá trị nhưng malformed**. `2dsphere` indexes có tính chất sparse, nhưng điều đó không có nghĩa MongoDB tự sửa những GeoJSON invalid.

### 3.5. Compound geospatial indexes

Nếu phần lớn query vừa lọc trạng thái vừa tìm gần:

```javascript
db.pickupPoints.createIndex({
  status: 1,
  location: "2dsphere"
});
```

Hoặc với dữ liệu đa tenant:

```javascript
db.pickupPoints.createIndex({
  tenantId: 1,
  location: "2dsphere"
});
```

Compound index có thể giúp một số pattern lọc và truy vấn gần. Tuy nhiên, hiệu quả phụ thuộc **query, phân bố dữ liệu, thứ tự field, index planner và phiên bản MongoDB**. Không có quy tắc “cứ thêm mọi field vào compound index là nhanh hơn”.

Khi index geospatial có thêm các field thường, cần hiểu các quy tắc sparse và phạm vi index của MongoDB. Với dữ liệu đa tenant, đảm bảo filter truy vấn luôn có tenant đã xác thực, kể cả khi index không dùng đầy đủ mọi predicate.

## 4. Toán tử `$near`: tìm và tự xếp theo khoảng cách

### 4.1. Cú pháp GeoJSON

Giả sử collection có `location` là GeoJSON Point và index:

```javascript
db.pickupPoints.createIndex({
  location: "2dsphere"
});
```

Truy vấn:

```javascript
const center = {
  type: "Point",
  coordinates: [106.7009, 10.7769]
};

db.pickupPoints.find({
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
});
```

Ý nghĩa:

1. Lấy điểm tham chiếu `center`.
2. Xét vị trí các document thông qua index `2dsphere`.
3. Chỉ nhận những điểm ở trong phạm vi tối đa **3.000 mét**.
4. Trả document theo thứ tự **gần nhất đến xa nhất**.

Đối với GeoJSON, `$near` sử dụng **tính khoảng cách trên mặt cầu**, không phải phép trừ kinh độ/vĩ độ theo mặt phẳng.

### 4.2. Thêm khoảng cách tối thiểu

```javascript
db.pickupPoints.find({
  location: {
    $near: {
      $geometry: center,
      $minDistance: 500,
      $maxDistance: 3000
    }
  }
});
```

Kết quả thuộc một **vành đai** với khoảng cách ít nhất 500 m và nhiều nhất 3 km.

Trường hợp ứng dụng:

- bỏ qua các điểm quá gần nếu đã có một luồng dịch vụ khác;
- tìm tài nguyên gần nhưng không sát tọa độ người dùng;
- xây bộ lọc bán kính có min/max.

Với dữ liệu GPS, sai số định vị có thể lên đến vài mét hoặc hơn; không nên dùng biên khoảng cách cực nhỏ như một phép đo chính xác tuyệt đối.

### 4.3. Lọc thêm theo nghiệp vụ

```javascript
db.pickupPoints.find({
  status: "OPEN",
  category: "pickup",
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}).limit(10);
```

Điều kiện `status` và `category` không thay đổi ý nghĩa khoảng cách. MongoDB trả những document khớp điều kiện, được sắp xếp gần → xa.

Trong hệ đa tenant:

```javascript
db.pickupPoints.find({
  tenantId: authenticatedTenantId,
  status: "OPEN",
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}).limit(10);
```

**Không lấy `tenantId` từ một tham số client chưa xác thực** để phân vùng dữ liệu nhạy cảm. Index geospatial giúp tìm nhanh, nhưng authorization phải được áp dụng trong filter và tầng service.

### 4.4. `$near` có trả khoảng cách số học không?

`$near` trong `find()` đảm bảo **thứ tự theo khoảng cách** nhưng không tự gắn field `distanceMeters` vào mỗi document kết quả để ứng dụng hiển thị.

Nếu cần hiển thị:

```text
Điểm A     420 m
Điểm B     815 m
Điểm C   1.350 m
```

nên dùng **stage `$geoNear`** với `distanceField`, hoặc một cách tính khoảng cách rõ ràng khác được ứng dụng kiểm soát. Đừng suy ra khoảng cách chỉ từ thứ tự trong mảng.

### 4.5. Không cần `sort()` thứ hai để sắp theo khoảng cách

`$near` **đã sắp gần đến xa**. Ví dụ:

```javascript
// Thường không cần khi mục tiêu chỉ là "gần nhất".
db.pickupPoints.find({
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}).sort({ name: 1 });
```

Lệnh `sort({name:1})` làm **sắp lại kết quả theo tên**, không giữ nguyên mục tiêu “nearest first”. Nó còn có thể gây thêm chi phí sort.

Nếu cần ưu tiên theo nhiều tiêu chí như “mở cửa, gần, đánh giá cao”, nên thiết kế một scoring/pipeline minh bạch, với sự đánh đổi giữa sort geospatial, filter và giới hạn ứng viên.

### 4.6. Không dùng `$near` như một predicate bất kỳ trong aggregation

`$near` là **query predicate operator** cho các lệnh match như `find()`. MongoDB không cho dùng nó làm predicate `$match` trong aggregation theo cách tùy ý:

```javascript
// Không phải mẫu đúng cho truy vấn gần trong aggregation:
db.pickupPoints.aggregate([
  {
    $match: {
      location: {
        $near: {
          $geometry: center,
          $maxDistance: 3000
        }
      }
    }
  }
]);
```

Khi đã cần pipeline, hãy bắt đầu bằng `$geoNear`.

## 5. Toán tử `$nearSphere`: khoảng cách theo mặt cầu

### 5.1. Cú pháp với GeoJSON

```javascript
db.pickupPoints.find({
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 3000
    }
  }
});
```

Với GeoJSON Point và `2dsphere` index:

- `$nearSphere` sắp kết quả theo **khoảng cách mặt cầu**.
- `$maxDistance` và `$minDistance` biểu diễn **mét**.
- Có thể kết hợp các field filter khác.
- Các kết quả được sắp từ gần đến xa.

### 5.2. So sánh `$near` với `$nearSphere` trên GeoJSON

Nếu hai query dùng **cùng điểm tham chiếu**, **cùng `2dsphere` index**, **cùng filter** và **cùng giới hạn khoảng cách**, chúng có thể cho kết quả rất giống nhau vì với GeoJSON, `$near` cũng dùng hình học cầu.

```javascript
// Query A
{
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}

// Query B
{
  location: {
    $nearSphere: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}
```

Không nên dạy quy tắc sai “`$near` luôn đo đường thẳng trên mặt phẳng, `$nearSphere` mới đo theo cầu”. Quy tắc đó bỏ qua **loại đầu vào** và **loại index**.

### 5.3. Khác biệt chủ yếu khi dùng legacy coordinates

Khi dữ liệu và điểm tham chiếu là **legacy coordinate pairs**:

- `$near` với `2d` có semantics hình học mặt phẳng.
- `$nearSphere` yêu cầu tính khoảng cách trên cầu và có cú pháp/đơn vị legacy riêng.
- `$nearSphere` có thể dùng `2d` index cho legacy coordinate pairs trong những điều kiện được MongoDB hỗ trợ.
- Với `$nearSphere` legacy, các giới hạn khoảng cách thường được chỉ định bằng **radian**.

Ví dụ trong collection riêng có `2d` index:

```javascript
// Dữ liệu legacy, chỉ minh họa cú pháp.
db.legacyPlaces.createIndex({ pos: "2d" });

db.legacyPlaces.find({
  pos: {
    $nearSphere: [106.7009, 10.7769],
    $maxDistance: 0.0005
  }
});
```

`0.0005` ở ví dụ legacy **không phải 0,0005 mét**, mà phải hiểu theo ngữ nghĩa radian của truy vấn. Đối với một bài toán GPS mới, dùng GeoJSON Point với `2dsphere` để tránh trộn đơn vị không cần thiết.

### 5.4. Radian và phép đổi đơn vị

Khi cần minh họa gần đúng khoảng cách trên bề mặt cầu:

\[
d_{\text{mét}} \approx \theta_{\text{radian}} \times R_{\text{Trái Đất}}
\]

Với bán kính Trái Đất xấp xỉ:

\[
R \approx 6\,371\,000\ \text{m}
\]

Chẳng hạn `0.0005` radian tương ứng cỡ **3,2 km** theo giả định bán kính trên. Đây là phép xấp xỉ để hiểu đơn vị, **không phải** cách chuyển đổi được bảo đảm chính xác cho mọi mô hình geodesic hoặc bản đồ đường phố.

Đối với query `$nearSphere` **dùng `$geometry` GeoJSON**, truyền `$maxDistance: 3200` nếu muốn bán kính 3,2 km; **không tự chia 3.200 cho 6.371.000** rồi gửi kết quả như tham số GeoJSON.

## 6. Bảng quyết định `$near`, `$nearSphere` và `$geoNear`

| Nhu cầu | `$near` | `$nearSphere` | `$geoNear` |
| --- | --- | --- | --- |
| Tìm nearest trong `find()` | Phù hợp | Phù hợp | Không phải predicate của `find()` |
| GeoJSON Point, index `2dsphere` | Có | Có | Có |
| Trả kết quả từ gần tới xa | Có | Có | Có |
| Lọc theo khoảng cách min/max | Có | Có | Có |
| Tự thêm field khoảng cách vào output | Không | Không | **Có** qua `distanceField` |
| Kết hợp với `$project` / `$group` / `$lookup` | Không trực tiếp là pipeline stage | Không trực tiếp là pipeline stage | Có, sau stage `$geoNear` |
| Điểm tham chiếu là GeoJSON Point | Có | Có | Có |
| Mô hình legacy coordinate pairs | Có, tùy index | Có, semantics cầu | Có, tùy index/tùy chọn |
| Cần `$geoNear` ở đầu pipeline | Không áp dụng | Không áp dụng | **Bắt buộc** |
| Cần tính kết quả ra km bằng hệ số | Tự tính phía ứng dụng | Tự tính phía ứng dụng | Có `distanceMultiplier` |
| Muốn lọc vùng nhưng **không cần sort theo khoảng cách** | Có chi phí sort không cần thiết | Có chi phí sort không cần thiết | Có chi phí nearest sort | 

Nếu chỉ muốn “trong bán kính này có những điểm nào” mà **không cần thứ tự gần → xa**, cân nhắc `$geoWithin` với hình học phù hợp; vì `$near` và `$nearSphere` có semantics **sắp xếp khoảng cách** và có thể chịu chi phí không cần thiết.

## 7. Stage `$geoNear`: truy vấn lân cận trong aggregation pipeline

### 7.1. Khi nào nên dùng `$geoNear`?

Một API cần kết quả:

```javascript
{
  name: "Điểm nhận hàng A",
  distanceMeters: 420.7,
  distanceKm: 0.421,
  category: "pickup"
}
```

Nếu dùng `$near` trong `find()`, bạn nhận document đã sắp theo khoảng cách nhưng không có field `distanceMeters` tự động. `$geoNear` giải quyết bằng cách:

1. Tìm các document gần điểm.
2. Tính khoảng cách.
3. Ghi khoảng cách vào một field.
4. Trả kết quả theo thứ tự gần tới xa.
5. Cho các stage phía sau tiếp tục xử lý.

### 7.2. Cú pháp cơ bản

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      key: "location"
    }
  },
  { $limit: 10 },
  {
    $project: {
      _id: 1,
      name: 1,
      category: 1,
      status: 1,
      distanceMeters: 1,
      location: 1
    }
  }
]);
```

Ý nghĩa:

- `near`: điểm tham chiếu.
- `distanceField`: tên field kết quả chứa khoảng cách.
- `maxDistance`: giới hạn tối đa, **mét** khi `near` là GeoJSON Point.
- `spherical: true`: chủ động chọn tính theo hình học mặt cầu.
- `key: "location"`: chỉ rõ field geospatial index.
- `$limit`: giới hạn số kết quả gần nhất.
- `$project`: chỉ trả những field mà API cần.

### 7.3. `$geoNear` phải là stage đầu tiên

Đúng:

```javascript
db.pickupPoints.aggregate([
  { $geoNear: { near: center, key: "location",
                distanceField: "distanceMeters", spherical: true } },
  { $match: { status: "OPEN" } },
  { $limit: 10 }
]);
```

Sai:

```javascript
db.pickupPoints.aggregate([
  { $match: { status: "OPEN" } },
  { $geoNear: { near: center, key: "location",
                distanceField: "distanceMeters", spherical: true } }
]);
```

MongoDB yêu cầu `$geoNear` **là stage đầu tiên của pipeline chứa nó**. Nếu cần lọc dữ liệu trước về mặt ngữ nghĩa, sử dụng trường `query` **bên trong `$geoNear`** thay vì chèn `$match` phía trước.

Lưu ý: `$geoNear` cũng có thể xuất hiện là stage đầu của **một pipeline lồng** ở một số ngữ cảnh được hỗ trợ, ví dụ trong pipeline của `$lookup`. Quy tắc là stage đầu trong **pipeline tương ứng**, không phải lúc nào cũng đầu toàn bộ câu lệnh lớn nhất.

### 7.4. Filter đúng chỗ với `query`

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 3000,
      query: {
        status: "OPEN",
        category: "pickup"
      }
    }
  },
  { $limit: 10 }
]);
```

`query` có thể chứa những điều kiện MongoDB thông thường, nhưng **không được đưa một predicate `$near` khác vào `query`**. Nếu query chứa điều kiện tenant/quyền truy cập, giữ chúng ngay tại nguồn dữ liệu:

```javascript
query: {
  tenantId: authenticatedTenantId,
  status: "OPEN"
}
```

Không thể coi một `$match` đặt cuối pipeline sau khi đã xuất toàn bộ kết quả có cùng tính chất hiệu năng/đúng đắn như một query điều kiện đặt thích hợp trong `$geoNear`. Đặc biệt, nếu đặt `$limit` trước `$match`, bạn có thể trả thiếu điểm hợp lệ.

### 7.5. `distanceField` theo phiên bản MongoDB

`distanceField` giúp lấy số khoảng cách để hiển thị. Trong **MongoDB trước 8.1**, nó là field được yêu cầu trong cú pháp `$geoNear` thông thường. **Từ MongoDB 8.1**, field này có thể **không bắt buộc trên non-time-series collections**; nhưng các truy vấn `$geoNear` trên time-series vẫn yêu cầu `distanceField` theo tài liệu hiện hành.

Trong bài và trong hầu hết ứng dụng thực tế, nên **chỉ rõ `distanceField`** để:

- API có khoảng cách trả về;
- giữ khả năng tương thích với nhiều phiên bản;
- tránh nhầm ý nghĩa khi kết quả không có field khoảng cách.

Không suy luận rằng vì `distanceField` có thể optional ở một bản mới nên mọi phiên bản cũ cũng bỏ qua được.

### 7.6. `key` khi collection có nhiều geospatial index

Giả sử mỗi địa điểm có cả vị trí cửa hàng và vị trí điểm đỗ xe:

```javascript
db.pickupPoints.createIndex({
  location: "2dsphere"
});

db.pickupPoints.createIndex({
  parkingLocation: "2dsphere"
});
```

Lúc này `$geoNear` cần biết **dùng field nào để đo khoảng cách**:

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceToPickupMeters",
      spherical: true
    }
  }
]);
```

Nếu collection có nhiều index geospatial thích hợp mà không chỉ rõ `key`, MongoDB có thể trả lỗi do không xác định được index/field. Dùng `key` tường minh là cách viết dễ hiểu và giảm phụ thuộc vào việc collection hiện có bao nhiêu index.

### 7.7. `includeLocs`: điểm nào được dùng để tính?

Nếu một document có nhiều vị trí thuộc cùng field geospatial, MongoDB có thể tính theo vị trí gần nhất. Tùy chọn `includeLocs` có thể cho biết vị trí đã tham gia tính khoảng cách:

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "geo.distanceMeters",
      includeLocs: "geo.matchedLocation",
      spherical: true
    }
  },
  {
    $project: {
      name: 1,
      location: 1,
      geo: 1
    }
  }
]);
```

Không đặt các field output đè lên field nghiệp vụ quan trọng hoặc tạo đường dẫn field mâu thuẫn trong document. Tên `distanceField` và `includeLocs` nên được chuẩn hóa trong API response.

### 7.8. `distanceMultiplier`: chuyển mét thành km

Với GeoJSON Point + `2dsphere` index, distance được biểu diễn bằng **mét**. Muốn trả km:

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceKm",
      distanceMultiplier: 0.001,
      maxDistance: 3000,
      spherical: true
    }
  },
  { $limit: 10 }
]);
```

Ví dụ:

```text
Khoảng cách tính ban đầu:   1500 m
distanceMultiplier:         0.001
Giá trị distanceKm:          1.5
```

**Lưu ý:** `distanceMultiplier` thay **giá trị khoảng cách đưa ra output**; nó **không biến đơn vị của `maxDistance` thành km**. Trong ví dụ vẫn truyền `maxDistance: 3000` nếu muốn bán kính 3 km.

Với đầu vào **legacy coordinates**, khoảng cách có thể được trả/tính theo **radian** trong ngữ nghĩa spherical, và lúc đó hệ số chuyển đổi không phải `0.001`. Phải xác nhận định dạng input và đơn vị trước khi dùng multiplier.

### 7.9. `minDistance`, `maxDistance` và vùng hình vành khăn

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      minDistance: 1000,
      maxDistance: 5000,
      spherical: true
    }
  }
]);
```

Query chọn các điểm từ khoảng **1 km tới 5 km**, sắp từ gần tới xa trong tập hợp phù hợp. Điều này có thể hữu ích khi phân vùng mức độ phục vụ hoặc chia bán kính.

Khi có thêm chính sách theo vùng hành chính, khoảng cách hình học không thay thế các điều kiện “thuộc quận X”, “nằm trong vùng phục vụ” hoặc “qua cầu/đường cấm”. Có thể cần filter thêm hoặc một bước spatial intersection.

## 8. Thực hành `mongosh` trọn vẹn: điểm dịch vụ giả lập

### 8.1. Chuẩn bị database riêng

Các ví dụ chỉ dùng dữ liệu **giả lập**; không chứa tọa độ nhà người dùng hay địa điểm kinh doanh thực. Chạy trên MongoDB test được phép sửa.

Kết nối:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Trong shell:

```javascript
const lab = db.getSiblingDB("mongo_geo_row295_lab");
const places = lab.getCollection("places_demo");
const runId = "row295-" + new ObjectId().toHexString();

const center = {
  type: "Point",
  coordinates: [106.7009, 10.7769]
};

print("database=" + lab.getName());
print("collection=" + places.getName());
print("runId=" + runId);
```

`runId` giúp phạm vi truy vấn và dọn dữ liệu bám đúng những document của **lượt thực hành này**, tránh đụng dữ liệu của người khác.

### 8.2. Thêm các điểm mẫu

```javascript
const samples = [
  {
    _id: new ObjectId(),
    runId,
    code: "LAB-295-A",
    name: "Điểm mô phỏng A",
    category: "pickup",
    status: "OPEN",
    rating: 4.8,
    location: {
      type: "Point",
      coordinates: [106.7009, 10.7769]
    }
  },
  {
    _id: new ObjectId(),
    runId,
    code: "LAB-295-B",
    name: "Điểm mô phỏng B",
    category: "pickup",
    status: "OPEN",
    rating: 4.5,
    location: {
      type: "Point",
      coordinates: [106.7045, 10.7778]
    }
  },
  {
    _id: new ObjectId(),
    runId,
    code: "LAB-295-C",
    name: "Điểm mô phỏng C",
    category: "pickup",
    status: "CLOSED",
    rating: 4.9,
    location: {
      type: "Point",
      coordinates: [106.7080, 10.7750]
    }
  },
  {
    _id: new ObjectId(),
    runId,
    code: "LAB-295-D",
    name: "Điểm mô phỏng D",
    category: "locker",
    status: "OPEN",
    rating: 4.2,
    location: {
      type: "Point",
      coordinates: [106.6950, 10.7800]
    }
  },
  {
    _id: new ObjectId(),
    runId,
    code: "LAB-295-E",
    name: "Điểm mô phỏng E",
    category: "pickup",
    status: "OPEN",
    rating: 4.7,
    location: {
      type: "Point",
      coordinates: [106.7290, 10.7900]
    }
  }
];

const insertResult = places.insertMany(samples);
printjson(insertResult);
printjson(
  places.find(
    { runId },
    { code: 1, name: 1, status: 1, location: 1 }
  ).toArray()
);
```

Tọa độ là giá trị demo để so sánh logic near query; đừng diễn giải chúng như vị trí chính xác của bất cứ doanh nghiệp thật nào.

### 8.3. Tạo index `2dsphere`

```javascript
places.createIndex(
  { location: "2dsphere" },
  { name: "location_2dsphere" }
);

printjson(places.getIndexes());
```

Tạo index sau khi insert trong lab giúp thấy hai phần tách biệt: **dữ liệu GeoJSON** và **geospatial index**. Trong production, thứ tự tạo index, migration và tải hệ thống cần được lập kế hoạch; index build trên collection lớn có thể tốn I/O và thời gian.

### 8.4. Tìm gần nhất bằng `$near`

```javascript
const nearest = places.find(
  {
    runId,
    location: {
      $near: {
        $geometry: center,
        $maxDistance: 3000
      }
    }
  },
  {
    code: 1,
    name: 1,
    status: 1,
    location: 1
  }
).limit(10).toArray();

printjson(nearest);
```

Kết quả chỉ gồm những document của `runId` nằm trong bán kính yêu cầu, thứ tự gần tới xa; nhưng chưa có field khoảng cách định lượng.

### 8.5. Truy vấn tương tự bằng `$nearSphere`

```javascript
printjson(
  places.find({
    runId,
    status: "OPEN",
    location: {
      $nearSphere: {
        $geometry: center,
        $maxDistance: 3000
      }
    }
  }).limit(10).toArray()
);
```

Với GeoJSON và index `2dsphere`, kết quả thường gần tương đương `$near` khi filter giống nhau. Ở đây có thêm `status:"OPEN"`, nên đừng so sánh hai output khác filter rồi kết luận do hai toán tử tính khác.

### 8.6. Dùng `$geoNear` để lấy cả khoảng cách

```javascript
const nearbyOpen = places.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: {
        runId,
        status: "OPEN"
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      _id: 0,
      code: 1,
      name: 1,
      category: 1,
      status: 1,
      distanceMeters: { $round: ["$distanceMeters", 1] },
      distanceKm: {
        $round: [{ $divide: ["$distanceMeters", 1000] }, 3]
      }
    }
  }
]).toArray();

printjson(nearbyOpen);
```

Ở đây:

- `query` lọc theo runId và trạng thái.
- `distanceField` sinh khoảng cách tính bằng mét.
- `$limit` giới hạn số điểm gần nhất.
- `$project` biểu diễn cả mét và km sau khi đã tính.
- `$round` chỉ phục vụ hiển thị, không làm thay đổi cách MongoDB chọn điểm gần nhất.

Nếu `$project` loại bỏ field `distanceMeters` quá sớm, các stage sau sẽ không còn field để chuyển sang km hoặc lọc nâng cao.

### 8.7. Lọc vừa theo category, vừa theo khoảng cách

```javascript
printjson(
  places.aggregate([
    {
      $geoNear: {
        near: center,
        key: "location",
        distanceField: "distanceMeters",
        maxDistance: 5000,
        spherical: true,
        query: {
          runId,
          status: "OPEN",
          category: "pickup"
        }
      }
    },
    { $limit: 3 },
    {
      $project: {
        _id: 0,
        code: 1,
        name: 1,
        distanceMeters: 1
      }
    }
  ]).toArray()
);
```

Về semantics: trả tối đa **3 điểm pickup OPEN gần nhất** trong bán kính 5 km. Nếu thay thứ tự thành `$limit:3` **trước khi lọc category**, có thể lấy ba điểm gần nhất nói chung rồi lọc mất một số điểm và trả thiếu kết quả.

### 8.8. Đếm số điểm trong bán kính

`$geoNear` không còn có giới hạn mặc định 100 document như một số tài liệu/cơ chế cũ. Muốn đếm trong phạm vi:

```javascript
const counts = places.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: { runId }
    }
  },
  { $count: "totalWithin3Km" }
]).toArray();

printjson(counts);
```

Đây là cách đếm dùng `$geoNear` nhưng vẫn mang semantics tìm và tính khoảng cách. Nếu chỉ cần membership trong vùng, cân nhắc `$geoWithin` để tránh chi phí sắp xếp không cần thiết.

### 8.9. Dọn dữ liệu thử nghiệm an toàn

Trước khi dọn:

```javascript
print("database=" + lab.getName());
print("collection=" + places.getName());
print("runId=" + runId);

const ownDocs = places.find(
  { runId },
  { _id: 1, runId: 1, code: 1 }
).toArray();

printjson(ownDocs);
```

Chỉ khi `ownDocs` đúng các document do bạn tạo:

```javascript
for (const doc of ownDocs) {
  const removed = places.deleteOne({
    _id: doc._id,
    runId
  });
  print(doc.code + ": deleted=" + removed.deletedCount);
}

print("remaining=" + places.countDocuments({ runId }));
```

Không dùng `deleteMany({})`, `dropDatabase()` hoặc `drop()` trong môi trường chia sẻ. Index `location_2dsphere` có thể vẫn tồn tại trên collection demo sau khi xóa document; không tự drop index của người khác.

## 9. Bài thực hành nâng cao: xếp hạng theo khoảng cách và trạng thái

### 9.1. Mục tiêu: ưu tiên OPEN, gần, sau đó rating

Giả sử API muốn **chỉ điểm OPEN** trong bán kính 5 km, ưu tiên khoảng cách, nếu ngang khoảng cách thì ưu tiên rating.

Có thể:

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 5000,
      query: { status: "OPEN" }
    }
  },
  {
    $sort: {
      distanceMeters: 1,
      rating: -1,
      _id: 1
    }
  },
  { $limit: 20 }
]);
```

**Đánh đổi:** `$geoNear` đã có thứ tự gần đến xa, nhưng `$sort` thứ hai có thể tiêu tốn thêm tài nguyên; dùng nó khi cần **tie-breaker có quy tắc**. Với dữ liệu rất lớn, cần giới hạn khu vực, kiểm tra execution plan và xác định tính ổn định của cursor.

Không kỳ vọng MongoDB tính chính xác “hai khoảng cách bằng nhau” theo kinh nghiệm mắt nhìn trên bản đồ; hai giá trị float có thể khác rất nhỏ.

### 9.2. Chọn N ứng viên gần rồi tính ranking phức tạp

Một thuật toán gợi ý địa điểm có thể:

1. Dùng `$geoNear` lấy **N điểm hợp lệ trong bán kính**.
2. Tính điểm nghiệp vụ dựa trên tồn kho, thời gian mở cửa, đánh giá.
3. Chọn tối đa K kết quả.

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 5000,
      spherical: true,
      query: { status: "OPEN" }
    }
  },
  { $limit: 100 },
  {
    $addFields: {
      score: {
        $subtract: [
          { $multiply: ["$rating", 10] },
          { $divide: ["$distanceMeters", 100] }
        ]
      }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 10 }
]);
```

Đây là **công thức minh họa**, không phải hàm xếp hạng đề xuất cho production. Điểm cần thấy: `$limit:100` trước khi tính score tạo tập ứng viên **100 điểm gần nhất**, vì vậy một điểm thứ 101 nhưng rating rất cao sẽ **không có cơ hội** được chọn.

Để tối ưu công bằng giữa khoảng cách và chất lượng, cần xác định trade-off/tập ứng viên dựa trên nghiệp vụ; không vô tình làm `$limit` thay đổi định nghĩa của “top K” mà không thông báo.

### 9.3. Tìm gần nhất trong từng loại địa điểm

Ví dụ muốn tối đa ba điểm gần nhất **theo từng category**:

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 10000,
      spherical: true,
      query: { status: "OPEN" }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$category",
      sortBy: { distanceMeters: 1, _id: 1 },
      output: {
        rankInCategory: { $documentNumber: {} }
      }
    }
  },
  { $match: { rankInCategory: { $lte: 3 } } },
  {
    $project: {
      name: 1,
      category: 1,
      distanceMeters: 1,
      rankInCategory: 1
    }
  }
]);
```

`$setWindowFields` chỉ được dùng trên MongoDB version hỗ trợ stage này; nó có thể cần sort và bộ nhớ bổ sung. Nếu không cần top N mỗi nhóm, đừng đưa một stage phức tạp vào pipeline chỉ để tìm một điểm gần nhất nói chung.

## 10. `$geoNear` và `$lookup`: nguồn tham chiếu động

Một số ứng dụng muốn tìm địa điểm gần **nhiều vị trí xuất phát** khác nhau. MongoDB có khả năng dùng `$geoNear` trong **pipeline của `$lookup`** ở những phiên bản hỗ trợ, với `let` để truyền vị trí tham chiếu:

```javascript
db.deliveryRequests.aggregate([
  {
    $lookup: {
      from: "pickupPoints",
      let: {
        requestPoint: "$pickupLocation"
      },
      pipeline: [
        {
          $geoNear: {
            near: "$$requestPoint",
            key: "location",
            distanceField: "distanceMeters",
            maxDistance: 3000,
            spherical: true,
            query: {
              status: "OPEN"
            }
          }
        },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            name: 1,
            distanceMeters: 1
          }
        }
      ],
      as: "nearbyPickupPoints"
    }
  }
]);
```

Điểm cần nhớ:

- `$geoNear` vẫn là **stage đầu tiên trong nested lookup pipeline**.
- `near` có thể sử dụng biến được bind qua `let` trong phiên bản phù hợp.
- Mỗi input document có thể kích hoạt công việc tìm geospatial; với tập input lớn, chi phí có thể cao.
- Nếu dữ liệu yêu cầu tenant isolation, `query`/pipeline cũng phải chứa điều kiện tenant an toàn; không chỉ đặt điều kiện ở collection cha.
- Query ở hai collection phải dùng đúng field geospatial index và namespace.

Không dùng `$lookup` này thay thế hệ thống routing/phân bổ tối ưu phức tạp khi có hàng triệu yêu cầu với nhiều điểm; benchmark workload thực để chọn batch/cache/precomputed candidates.

## 11. Hiệu năng và execution plan

### 11.1. Không có geospatial index thì sao?

`$near`, `$nearSphere` và `$geoNear` đều yêu cầu **geospatial index phù hợp**. Nếu thiếu, server có thể trả lỗi kiểu không tìm được index hỗ trợ.

Ví dụ:

```javascript
// Điều kiện cần cho những ví dụ GeoJSON.
db.pickupPoints.createIndex({ location: "2dsphere" });
```

Đừng coi `$geoNear` là một cách thay cho index bằng việc tính khoảng cách trên mọi document; nó không chạy đúng contract nếu không có geospatial index phù hợp.

### 11.2. Bán kính càng lớn, tập ứng viên càng nhiều

Một query:

```javascript
{
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 5000000
    }
  }
}
```

có thể mở phạm vi tới hàng nghìn km. Với collection lớn, số document ứng viên, chi phí sort và tài nguyên có thể tăng đáng kể.

Trong API “near me”:

- Giới hạn `maxDistance` theo sản phẩm, ví dụ trong vài km hoặc vài chục km, không tin số tùy ý do client gửi.
- Giới hạn số kết quả/trang.
- Chỉ truy vấn field và category cần thiết.
- Hạn chế thực hiện query cực rộng liên tục từ một client.
- Quan sát index usage, P95/P99 latency và số document/index keys được xem xét.

Trong các phiên bản MongoDB mới có thêm các giới hạn bộ nhớ cho xử lý nearest query trong một số trường hợp; cần đối chiếu server version thay vì giả định một phép tìm gần có thể giữ vô hạn kết quả để sort.

### 11.3. `explain()` cho `find()`

```javascript
db.pickupPoints.find({
  status: "OPEN",
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}).explain("executionStats");
```

Khi đọc output, tìm:

- Index geospatial nào được sử dụng?
- Có dấu hiệu geospatial index scan không?
- Tổng document examined và keys examined?
- Thời gian thực thi của query?
- Có thêm sort stage hay không?
- Filter `status` được áp dụng ở đâu?

Tên stage nội bộ trong explain thay đổi theo MongoDB version/query engine; tránh viết monitoring parser phụ thuộc một chuỗi tên stage cố định.

### 11.4. `explain()` cho aggregation

```javascript
db.pickupPoints.explain("executionStats").aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: {
        status: "OPEN"
      }
    }
  },
  { $limit: 10 }
]);
```

Trên production, chạy explain phức tạp vẫn có chi phí. Thực hiện ở môi trường staging hoặc với query hợp lệ đã được kiểm soát; không chạy một truy vấn toàn thế giới lặp lại chỉ để lấy số liệu.

### 11.5. Chi phí index và write throughput

Index `2dsphere` có lợi cho near queries nhưng vẫn tiêu tốn storage và chi phí cập nhật index khi các document đổi vị trí.

Nếu một collection theo dõi vị trí xe cập nhật vài lần mỗi giây trên hàng triệu thiết bị:

- mỗi update location có thể làm thay đổi entry index;
- write throughput có thể trở thành bottleneck;
- TTL/lifecycle dữ liệu cần được cân nhắc;
- có thể cần tách current location khỏi historical location;
- việc đọc top nearest thường xuyên cần cache hoặc rate limiting phù hợp.

Không tạo geospatial indexes trên mọi trường vị trí mà không có nhu cầu truy vấn tương ứng.

### 11.6. Chọn index đa tenant

Đối với collection lớn nhiều tenant:

```javascript
db.pickupPoints.createIndex({
  tenantId: 1,
  location: "2dsphere"
});
```

Có thể là một lựa chọn để đánh giá nếu query luôn có `tenantId`. Nhưng cần đo sự tương quan giữa filter tenant, bounding distance và phân bố điểm.

Đặc biệt:

- Index không thay thế kiểm soát truy cập.
- Tạo nhiều compound indexes có thể tăng storage/write amplification.
- Có thể cần index riêng cho query không có geospatial predicate.
- Nếu collection sharded, query targeting còn phụ thuộc **shard key**, không chỉ `2dsphere` index.

### 11.7. Sharding và geospatial queries

Một sharded collection vẫn có thể có geospatial index và hỗ trợ truy vấn gần, nhưng:

- Geo index không tự là một shard key hợp lệ.
- `mongos` có thể phải tìm trên nhiều shard rồi gộp/sắp kết quả.
- Filter chứa shard key có thể giúp routing nếu thỏa quy tắc phiên bản.
- Số lượng shard và phân bố điểm ảnh hưởng latency.
- Zone và tenant policies vẫn phải được cưỡng chế.

Chọn shard key cho lookup theo vị trí là bài toán khác với chọn geospatial index. Không mặc định dùng `location:"2dsphere"` làm shard key của collection.

## 12. Phân trang và thứ tự ổn định

### 12.1. `limit` là điểm khởi đầu

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 10000
    }
  },
  { $limit: 20 }
]);
```

Đây là truy vấn điển hình cho “top 20 gần nhất”.

### 12.2. `skip` có chi phí khi offset lớn

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 10000,
      spherical: true
    }
  },
  { $skip: 10000 },
  { $limit: 20 }
]);
```

Để bỏ qua 10.000 kết quả, server vẫn có thể phải xử lý một lượng kết quả lớn trước đó. Vì thế phân trang offset sâu thường không phù hợp với ứng dụng có hàng triệu điểm.

### 12.3. Dữ liệu chuyển động làm trang kết quả thay đổi

Nếu user đang di chuyển hoặc tài nguyên cập nhật vị trí liên tục:

```text
Page 1 tại T0: A, B, C
Page 2 tại T1: D, E, F
```

Giữa T0 và T1, điểm G chuyển đến gần hơn hoặc B bị xóa; thứ tự kết quả có thể thay đổi, gây trùng/bỏ sót giữa các trang.

Giải pháp tùy yêu cầu:

- Cố định tọa độ `center` và filter cho toàn bộ lượt phân trang.
- Giữ snapshot/cursor phù hợp nếu API có hỗ trợ.
- Dùng stable tie-breaker, ví dụ `distanceMeters` và `_id`, với chi phí sort cần đánh giá.
- Với dataset biến động cao, cân nhắc trả top-N “near me” thay vì hỗ trợ offset sâu.
- Nếu cần kết quả bất biến qua nhiều trang, có thể phải materialize danh sách ID ứng viên tại một thời điểm và quản lý TTL.

Không được dùng `_id` đơn lẻ làm continuation token của thứ tự **khoảng cách**, vì thứ tự theo `_id` không tương ứng với thứ tự địa lý.

## 13. API Node.js: validate đầu vào và truy vấn gần

### 13.1. Contract đề xuất

Ví dụ:

```text
GET /pickup-points/nearby?longitude=106.7009&latitude=10.7769&radiusMeters=3000&limit=10
```

Các tham số cần kiểm tra:

- `longitude`: số hữu hạn trong [-180, 180].
- `latitude`: số hữu hạn trong [-90, 90].
- `radiusMeters`: số hữu hạn không âm và không vượt giới hạn sản phẩm.
- `limit`: số nguyên dương không quá mức cho phép.
- `tenantId`/`userId`: lấy từ authentication, không từ query string tùy ý.

Không nhận nguyên một object MongoDB filter từ client rồi gắn vào `$geoNear.query`, vì có thể mở khả năng injection/đọc dữ liệu ngoài quyền.

### 13.2. Hàm service ví dụ

Giả sử `collection` là MongoDB Node.js driver collection, đã có index `2dsphere` trên `location`:

```javascript
function assertFiniteNumber(value, name) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    throw new Error("INVALID_" + name);
  }

  return number;
}

function parseNearbyInput(input) {
  const longitude = assertFiniteNumber(input.longitude, "LONGITUDE");
  const latitude = assertFiniteNumber(input.latitude, "LATITUDE");
  const radiusMeters = assertFiniteNumber(input.radiusMeters, "RADIUS");
  const limit = Number(input.limit ?? 10);

  if (longitude < -180 || longitude > 180) {
    throw new Error("LONGITUDE_OUT_OF_RANGE");
  }
  if (latitude < -90 || latitude > 90) {
    throw new Error("LATITUDE_OUT_OF_RANGE");
  }
  if (radiusMeters < 0 || radiusMeters > 20000) {
    throw new Error("RADIUS_OUT_OF_RANGE");
  }
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 50) {
    throw new Error("LIMIT_OUT_OF_RANGE");
  }

  return { longitude, latitude, radiusMeters, limit };
}

async function findNearbyPickupPoints(
  collection,
  input,
  authenticatedTenantId
) {
  const { longitude, latitude, radiusMeters, limit } =
    parseNearbyInput(input);

  const center = {
    type: "Point",
    coordinates: [longitude, latitude]
  };

  const pipeline = [
    {
      $geoNear: {
        near: center,
        key: "location",
        distanceField: "distanceMeters",
        spherical: true,
        maxDistance: radiusMeters,
        query: {
          tenantId: authenticatedTenantId,
          status: "OPEN",
          category: "pickup"
        }
      }
    },
    { $limit: limit },
    {
      $project: {
        _id: 1,
        name: 1,
        category: 1,
        distanceMeters: {
          $round: ["$distanceMeters", 1]
        },
        longitude: {
          $arrayElemAt: ["$location.coordinates", 0]
        },
        latitude: {
          $arrayElemAt: ["$location.coordinates", 1]
        }
      }
    }
  ];

  return collection.aggregate(pipeline).toArray();
}
```

Đây là **minh họa service**, không phải toàn bộ mã production. Ở request thực tế:

- Xác thực/ủy quyền tenant trước khi gọi hàm.
- Không dùng Number(undefined) hoặc Number(null) mà vô tình nhận 0: nên kiểm tra **tham số bắt buộc có mặt** trước khi parse nếu API không cho phép mặc định.
- Bắt lỗi validation và trả HTTP status rõ ràng.
- Thiết lập timeout, giới hạn rate và monitoring phù hợp.
- Nếu dùng dữ liệu nhạy cảm, giới hạn độ chính xác GPS được ghi log.

### 13.3. Ví dụ gọi service

```javascript
const results = await findNearbyPickupPoints(
  db.collection("pickupPoints"),
  {
    longitude: "106.7009",
    latitude: "10.7769",
    radiusMeters: "3000",
    limit: "10"
  },
  authenticatedTenantId
);

console.log(results);
```

Kết quả có thể gồm một document như:

```javascript
{
  _id: ObjectId("66a000000000000000000295"),
  name: "Điểm nhận hàng A",
  category: "pickup",
  distanceMeters: 421.6,
  longitude: 106.7045,
  latitude: 10.7778
}
```

Khoảng cách trong ví dụ response chỉ minh họa hình dạng; số thực tế được MongoDB tính từ tọa độ và dữ liệu.

### 13.4. Phân biệt lỗi invalid input, lỗi index và timeout

Một API nên phân loại:

| Lỗi | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Longitude/latitude ngoài miền | Request sai | Trả lỗi validation, không truy vấn DB |
| `radiusMeters` vượt giới hạn | Request không được chấp nhận | Trả lỗi giới hạn radius |
| Thiếu `2dsphere` index | Lỗi schema/cấu hình | Sửa migration/index, không báo là không có điểm |
| GeoJSON malformed trong dữ liệu | Dữ liệu nguồn lỗi | Sửa/migrate dữ liệu, thêm schema validation |
| Query timeout | Tải, vùng tìm rộng hoặc sự cố | Giảm phạm vi, quan sát index/latency, retry có kiểm soát |
| Không có điểm phù hợp | Kết quả hợp lệ rỗng | Trả mảng rỗng và contract rõ |
| Không có quyền tenant | Authorization | Không tiết lộ điểm ngoài phạm vi |

Đừng trả “không có địa điểm gần bạn” khi thực tế server báo thiếu index hoặc pipeline invalid.

## 14. So sánh `$geoNear` với `$geoWithin` và `$geoIntersects`

### 14.1. Các toán tử phục vụ mục đích khác nhau

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Tìm 10 điểm gần nhất | `$near` / `$nearSphere` |
| Tìm gần nhất và trả khoảng cách trong pipeline | `$geoNear` |
| Kiểm tra những điểm **nằm trong vùng** | `$geoWithin` |
| Tìm hình học giao nhau với một hình khác | `$geoIntersects` |
| Đếm điểm trong vòng tròn mà không cần sắp khoảng cách | `$geoWithin` với vùng tròn phù hợp |
| Tính thời gian lái xe đến điểm | Không phải chỉ query geospatial MongoDB; cần routing/graph service |

### 14.2. `$geoWithin` cho vùng tròn khi không cần sort

MongoDB có hình học `$centerSphere` sử dụng tâm [longitude, latitude] và **bán kính theo radian**:

```javascript
const earthRadiusMeters = 6371000;
const radiusMeters = 3000;

db.pickupPoints.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7009, 10.7769],
        radiusMeters / earthRadiusMeters
      ]
    }
  }
});
```

Ví dụ này khác `$near`:

- Truy vấn xác định membership trong vòng tròn.
- **Không tự sắp gần tới xa**.
- Bán kính của `$centerSphere` là **radian**, không phải mét.

Vì vậy không được đưa `3000` trực tiếp vào tham số radius của `$centerSphere` và nghĩ đó là 3 km.

### 14.3. `$geoIntersects` cho vùng bao phủ

Nếu hệ thống lưu các khu vực giao hàng dạng GeoJSON Polygon:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.68, 10.76],
      [106.72, 10.76],
      [106.72, 10.79],
      [106.68, 10.79],
      [106.68, 10.76]
    ]
  ]
}
```

có thể cần truy vấn một vùng bao phủ hoặc giao cắt với điểm/đường. `$geoIntersects` giải quyết loại câu hỏi khác với “điểm nào gần nhất”. Polygon phải tuân thủ cấu trúc/ring closure/coordinate order; query muốn tìm service vùng phủ cần mô hình dữ liệu phù hợp.

### 14.4. Kết hợp near và vùng phục vụ

Một điểm nhận hàng gần người dùng chưa chắc **được phép phục vụ** người dùng đó do điều kiện hành chính hoặc hoạt động.

Một kiến trúc thường làm:

1. Tìm candidate gần bằng `$geoNear` và filter trạng thái.
2. Kiểm tra logic vùng phục vụ/geofencing.
3. Kiểm tra tồn kho và thời gian mở cửa.
4. Nếu cần, gọi hệ thống định tuyến để tính ETA thực.
5. Trả kết quả phù hợp theo contract.

Không lấy địa điểm gần nhất rồi tự động giả định nó là địa điểm tối ưu hoặc hợp lệ cho mọi giao dịch.

## 15. Độ chính xác, dữ liệu GPS và bảo mật vị trí

### 15.1. GPS có sai số

Một thiết bị có thể trả:

```javascript
{
  latitude: 10.7769,
  longitude: 106.7009,
  accuracyMeters: 40
}
```

Điều này có nghĩa vị trí đo có độ không chắc chắn; không nên diễn giải kết quả truy vấn “cách 2 m” là ranh giới chắc chắn giữa “trong vùng” và “ngoài vùng”.

Với ứng dụng giao hàng, có thể:

- dùng bán kính tìm rộng hơn sai số định vị;
- yêu cầu xác nhận địa chỉ;
- lưu cả accuracy để giải thích chất lượng GPS;
- không dùng khoảng cách GPS đơn lẻ để chứng minh người dùng thực tế có mặt tại địa điểm.

### 15.2. Kinh độ/vĩ độ không phải tọa độ pixel

Tọa độ bản đồ có thể trải qua các hệ quy chiếu/projection (ví dụ khi chuyển sang pixel web map). Không được lấy tọa độ tile/pixel rồi lưu như GeoJSON longitude/latitude và kỳ vọng `2dsphere` hiểu đúng.

Nếu nguồn dữ liệu ở một hệ tọa độ phẳng chuyên dụng, cần **chuyển hệ tọa độ** theo quy tắc thích hợp trước khi lưu GeoJSON địa lý.

### 15.3. Không phải mọi vòng tròn bản đồ đều là đường đi được

Một vòng tròn bán kính 3 km có thể cắt sông, hồ, đường cao tốc hoặc ranh giới hành chính. Khoảng cách gần theo cầu không phản ánh:

- tuyến đường thực có thể đi;
- thời gian vận chuyển;
- phí cầu đường;
- hạn chế phương tiện;
- điều kiện vận hành tại giờ cụ thể.

MongoDB hỗ trợ tìm **ứng viên địa lý**, còn route/ETA cần hệ thống khác phù hợp.

### 15.4. Quyền riêng tư và vị trí nhạy cảm

Tọa độ chính xác có thể là dữ liệu cá nhân hoặc dữ liệu kinh doanh nhạy cảm. Những điểm thiết kế:

- Chỉ thu thập vị trí khi có mục đích và quyền phù hợp.
- Không ghi chính xác GPS vào access logs theo mặc định.
- Giới hạn quyền đọc và thời gian lưu trữ.
- Chọn mức làm tròn/bucket khi UI không cần chính xác từng mét.
- Không cho API truy vấn vị trí người khác chỉ bằng thay đổi `tenantId`/`userId`.
- Thiết lập rate limit để giảm khả năng dò vị trí.
- Bảo vệ dữ liệu khi chuyển tới bên thứ ba (routing, analytics).

Tính đúng của geospatial index không thay thế chính sách bảo mật.

## 16. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Lưu `[latitude, longitude]` thay vì `[longitude, latitude]` | Sai vị trí hoặc lỗi tọa độ | Chuẩn hóa GeoJSON và validate |
| Truyền `$maxDistance: 3` với ý định 3 km | Chỉ tìm trong 3 mét cho GeoJSON | Dùng `3000` mét |
| Dùng `$near` không có geospatial index | Query lỗi | Tạo index `2dsphere` phù hợp |
| Tạo index thường `{location:1}` rồi gọi `$near` | Index không có semantics geo | Dùng `{location:"2dsphere"}` |
| Nghĩ `$near` luôn phẳng còn `$nearSphere` luôn cầu | Sai với GeoJSON và `2dsphere` | Xét đầu vào và loại index |
| Dùng legacy pair rồi diễn giải radius như GeoJSON mét | Sai bán kính | Hiểu đơn vị legacy/radian |
| Dùng `$near` bên trong `$match` aggregation | Không hỗ trợ | Dùng `$geoNear` làm stage đầu |
| Đặt `$match` trước `$geoNear` | Pipeline không hợp lệ | Đưa filter vào `$geoNear.query` |
| Quên `key` khi có nhiều geo indexes | Query có thể lỗi/mơ hồ | Chỉ rõ indexed field |
| Quên `distanceField` trong server cũ | Pipeline không hợp lệ | Chỉ rõ field khoảng cách |
| Dùng `distanceMultiplier:0.001` rồi đổi `maxDistance` sang km | Sai bán kính | Filter GeoJSON vẫn dùng mét |
| Dùng `sort({name:1})` sau `$near` và kỳ vọng nearest first | Mất thứ tự theo khoảng cách | Không sort lại trừ khi chủ đích |
| Áp `$limit` trước filter trạng thái/category | Có thể trả thiếu điểm hợp lệ | Lọc ở query trước limit |
| Coi khoảng cách cầu là quãng đường đi xe | ETA sai | Dùng routing service |
| Tin GPS tuyệt đối chính xác | Quyết định biên vùng không ổn | Xét accuracy/buffer |
| Trả tất cả điểm trong bán kính hàng nghìn km | Tốn CPU/bộ nhớ/network | Giới hạn radius và result count |
| Phân trang sâu bằng `$skip` trên tập gần nhất khổng lồ | Độ trễ lớn | Cân nhắc giới hạn top-N/cursor phù hợp |
| Coi `location:"2dsphere"` là shard key hợp lệ trực tiếp | Nhầm geo index với shard key | Thiết kế shard key riêng |
| Chỉ tạo geospatial index để đảm bảo tenant isolation | Lộ dữ liệu ngoài quyền | Bắt buộc filter authorization |
| Dùng `updateLookup` hoặc bản ghi stale làm vị trí hiện tại | Dữ liệu di chuyển có thể lỗi thời | Xác định TTL/độ mới theo nghiệp vụ |
| Xóa toàn collection sau bài lab | Có thể xóa dữ liệu của người khác | Dọn đúng `_id` + `runId` |

## 17. Bài tập tự luyện

### Bài A. Chọn đúng thứ tự tọa độ

Một điểm có:

```text
latitude  = 10.7769
longitude = 106.7009
```

Viết GeoJSON Point chính xác và giải thích vì sao `[10.7769, 106.7009]` không phù hợp.

### Bài B. `$near` trong bán kính 2 km

Collection `shops` có field `location` là GeoJSON Point và index `2dsphere`. Viết `find()`:

- Tâm `[106.7009,10.7769]`.
- Bán kính 2 km.
- Chỉ `status:"OPEN"`.
- Lấy tối đa 15 document gần nhất.

### Bài C. So sánh `$near` và `$nearSphere`

Trên cùng `2dsphere` index và cùng GeoJSON input:

1. Có đúng rằng `$near` luôn tính phẳng không?
2. Vì sao `$nearSphere` hữu ích khi đọc code liên quan spherical geometry?
3. Khi chuyển sang legacy pair + `2d` index, cần xem lại điều gì?

### Bài D. `$geoNear` và khoảng cách km

Viết pipeline:

- `$geoNear` là stage đầu.
- Lọc `category:"locker"`.
- Giới hạn trong 5 km.
- Trả `name`, `distanceMeters` và `distanceKm`.
- Lấy 5 điểm gần nhất.

Giải thích tại sao `maxDistance` vẫn cần là `5000` nếu dùng `distanceMultiplier:0.001`.

### Bài E. Pipeline sai thứ tự

Đoạn code:

```javascript
db.shops.aggregate([
  { $match: { status: "OPEN" } },
  {
    $geoNear: {
      near: center,
      distanceField: "d",
      spherical: true
    }
  }
]);
```

Hãy viết lại để pipeline đúng cú pháp và giữ nguyên mục tiêu lọc chỉ cửa hàng OPEN.

### Bài F. Nhiều geospatial indexes

Collection có:

```javascript
db.shops.createIndex({ storeLocation: "2dsphere" });
db.shops.createIndex({ parkingLocation: "2dsphere" });
```

Muốn lấy khoảng cách tới cửa hàng chứ không phải bãi xe, stage `$geoNear` cần thêm tùy chọn gì? Vì sao?

### Bài G. Đơn vị legacy

Một developer lấy cú pháp `$nearSphere` với legacy coordinate pairs và đặt `$maxDistance:3000` để tìm trong 3 km. Hãy tìm lỗi trong lập luận đó; đưa ra cách thiết kế GeoJSON + `2dsphere` giúp tránh nhầm đơn vị.

### Bài H. Tìm vùng nhưng không sắp khoảng cách

Một job thống kê chỉ muốn đếm các shop nằm trong vòng tròn 10 km; thứ tự không quan trọng. Nên đánh giá `$near`, `$geoNear` hay `$geoWithin`? Giải thích đánh đổi về sorting.

### Bài I. Tối ưu query cho nhiều tenant

Một collection có 20 triệu điểm, trong đó mỗi tenant có vài trăm nghìn điểm. API luôn gửi `tenantId` xác thực, `status:"OPEN"` và vị trí.

Hãy đề xuất:

- Cách đặt filter trong `$geoNear`.
- Hai index candidates cần benchmark.
- Giới hạn `radiusMeters` và `limit`.
- Metric từ `explain("executionStats")` cần quan sát.
- Vì sao không thể coi index là toàn bộ cơ chế bảo vệ tenant.

### Bài J. Khoảng cách địa lý khác ETA

Hai điểm:

```text
Điểm A: cách đường chim bay 700 m, cần vòng qua sông.
Điểm B: cách đường chim bay 900 m, đường đi trực tiếp.
```

Ứng dụng muốn giao hàng nhanh nhất. Dùng `$geoNear` ở bước nào, sau đó cần thêm nguồn dữ liệu/cách tính nào để quyết định?

## 18. Tài liệu tham khảo chính thức

Các tính năng geospatial có chi tiết khác nhau theo **MongoDB server version** và định dạng dữ liệu; luôn đối chiếu tài liệu phiên bản đang chạy:

- [MongoDB Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/) — tổng quan GeoJSON, indexes và toán tử.
- [`$near` query operator](https://www.mongodb.com/docs/manual/reference/operator/query/near/) — cú pháp, index và đơn vị cho GeoJSON/legacy.
- [`$nearSphere` query operator](https://www.mongodb.com/docs/manual/reference/operator/query/nearSphere/) — spherical distance và cú pháp legacy.
- [`$geoNear` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/) — `distanceField`, `distanceMultiplier`, `includeLocs`, `key` và thứ tự stage.
- [`2dsphere` Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/) — cách lưu GeoJSON và tạo index địa lý.
- [`2d` Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2d/) — dữ liệu legacy/mặt phẳng.
- [Query Locations Near a Point on a Sphere](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/query/proximity-to-geojson/) — ví dụ tìm gần GeoJSON.
- [`$geoWithin`](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/) — truy vấn trong vùng.
- [`$geoIntersects`](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/) — truy vấn giao nhau.
- [`$centerSphere`](https://www.mongodb.com/docs/manual/reference/operator/query/centerSphere/) — hình tròn trên mặt cầu, bán kính radian.

Tùy phiên bản, MongoDB đã thay đổi một số giới hạn, ví dụ việc yêu cầu GeoJSON `Point` cho input của các truy vấn lân cận từ dòng MongoDB 8.0 và việc `distanceField` trở nên optional cho non-time-series `$geoNear` từ 8.1. Vì vậy cần kiểm tra chính sách version/FCV trước khi chuyển code mẫu vào production.

## 19. Kết luận

Để tìm những địa điểm lân cận trong MongoDB, hãy bắt đầu bằng **GeoJSON Point** với tọa độ `[longitude, latitude]` và một **geospatial index `2dsphere`** phù hợp. Dùng **`$near`** hoặc **`$nearSphere`** khi cần `find()` trả document từ gần tới xa; với GeoJSON, cả hai sử dụng hình học cầu và khoảng cách giới hạn tính bằng **mét**. Khi cần field khoảng cách và khả năng xử lý thêm trong aggregation, sử dụng **`$geoNear` làm stage đầu pipeline**, kết hợp `query`, `distanceField`, `maxDistance`, `key` và những stage sau.

Hiểu đúng **đơn vị** là điều kiện bắt buộc: GeoJSON point dùng kinh/vĩ độ tính bằng độ nhưng radius của near query là mét; legacy coordinates có semantics riêng, thường cần radian cho spherical queries. `distanceMultiplier` đổi khoảng cách **đưa ra kết quả**, không tự đổi đơn vị của bộ lọc `maxDistance`.

Cuối cùng, một truy vấn địa lý đúng phải tính cả **dữ liệu đầu vào, index, phạm vi lọc nghiệp vụ, hiệu năng, độ chính xác GPS và quyền riêng tư**. MongoDB giỏi chọn những điểm **gần theo địa lý**, nhưng **không tự tính thời gian di chuyển, quy tắc tuyến đường hoặc điều kiện phục vụ**. Chọn đúng toán tử chỉ là bước đầu; kết quả hữu ích phụ thuộc vào cách thiết kế toàn bộ luồng ứng dụng.
