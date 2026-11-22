# Kết hợp điều kiện nghiệp vụ với truy vấn địa lý trong MongoDB

## Mục tiêu bài học

Ứng dụng có dữ liệu vị trí thường cần giải quyết các câu hỏi cụ thể hơn nhiều so với “tìm địa điểm gần tôi”. Ví dụ:

- Tìm những căn hộ **cách khách không quá 3 km**, thuộc **tenant hiện tại**, đang **được phép đăng**, có **giá dưới 1.200.000 VND/đêm**, đủ chỗ cho **hai người** và có **Wi-Fi**.
- Liệt kê điểm nhận hàng **trong khu vực bản đồ**, nhưng chỉ giữ những điểm đang hoạt động và còn hàng.
- Tìm cửa hàng **có vùng giao hàng bao phủ địa chỉ khách**, đồng thời đáp ứng số tiền đơn hàng tối thiểu và chính sách giao hàng.
- Tìm chỗ lưu trú ở gần vị trí mong muốn mà **không trùng lịch đặt phòng**, rồi bảo đảm hai khách không thể cùng xác nhận một phòng duy nhất.
- Xếp hạng các kết quả vừa hợp lệ về địa lý vừa đáp ứng điều kiện giá, đánh giá và độ sẵn sàng của dịch vụ.

MongoDB hỗ trợ dữ liệu địa lý qua **GeoJSON**, chỉ mục **`2dsphere`**, các toán tử **`$near`**, **`$geoWithin`**, **`$geoIntersects`** và aggregation stage **`$geoNear`**. Giá trị thực tế xuất hiện khi ta kết hợp chúng với **các predicate nghiệp vụ thông thường**, thay vì coi địa lý và logic nghiệp vụ là hai truy vấn không liên quan.

Bài thuộc **Database Engine Document MongoDB → Dữ liệu địa lý → Kết hợp điều kiện nghiệp vụ với truy vấn địa lý**. Sau bài, người học có thể:

1. Thiết kế document chứa GeoJSON Point hoặc Polygon đúng chuẩn tọa độ.
2. Phân biệt điều kiện **ở gần**, **nằm trong vùng**, và **giao với hình học**.
3. Viết query phối hợp điều kiện địa lý với `tenantId`, trạng thái, giá, sức chứa, tiện nghi, thời gian và quyền truy cập.
4. Chọn `find()` hay aggregation với `$geoNear` tùy việc cần distance field, ranking và xử lý nhiều collection.
5. Tạo compound `2dsphere` index và hiểu ảnh hưởng của dữ liệu thiếu location, selectivity và partial index.
6. Giải thích ý nghĩa khoảng cách tính bằng mét, radius tính bằng radian và thứ tự longitude/latitude.
7. Kết hợp địa lý với vùng giao hàng Polygon bằng `$geoIntersects`.
8. Phân biệt **khả dụng tại lúc tìm kiếm** và **đặt chỗ thành công dưới concurrency**.
9. Tối ưu giới hạn khoảng cách, bộ lọc nghiệp vụ, phân trang, sorting và query plan.
10. Xử lý trường hợp biên: polygon phức tạp, điểm ranh giới, tọa độ sai, múi giờ, độ chính xác, quyền riêng tư.
11. Triển khai truy vấn bằng mongosh và Java Sync Driver.
12. Kiểm thử business filters kết hợp geospatial queries và đọc chỉ số hiệu năng.

> **Nguyên tắc:** Điều kiện địa lý trả lời “vị trí có phù hợp không?”, còn điều kiện nghiệp vụ trả lời “đối tượng **được phép và đủ điều kiện** để xuất hiện hoặc được đặt không?”. Hai nhóm điều kiện cần được áp dụng nhất quán; kết quả gần nhất không có nghĩa là hợp lệ nhất.

---

## 1. Tình huống: tìm căn hộ gần điểm đón khách

Giả sử ứng dụng quản lý các listing lưu trú. Khách nhập:

~~~text
Tọa độ mong muốn: 106.70098, 10.77689
Bán kính:         3.000 m
Số khách:          2
Giá tối đa:        1.200.000 VND/đêm
Tiện nghi:         Wi-Fi
Chỉ hiển thị:      listing đang đăng và được xác minh
Tenant:            tenant-a (lấy từ ngữ cảnh được xác thực)
~~~

Một listing nên xuất hiện khi nó đáp ứng **đồng thời**:

\[
\text{Eligible} =
\text{Near} \land
\text{SameTenant} \land
\text{Published} \land
\text{Verified} \land
\text{PriceOK} \land
\text{CapacityOK} \land
\text{AmenityOK}
\]

Điều kiện này mô tả cách lọc kết quả, **chưa** xét booking theo thời gian. Nếu người dùng chọn ngày nhận/trả phòng, cần bổ sung tính khả dụng trong khoảng ngày đó.

### 1.1. Sai lầm của cách chỉ lọc khoảng cách

~~~javascript
db.listings.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  }
});
~~~

Truy vấn này có thể trả về listing đã ẩn, giá vượt ngân sách, không thuộc tenant hiện tại hoặc không đủ sức chứa.

### 1.2. Cách nghĩ đúng

~~~text
Điều kiện địa lý
    +
Điều kiện visibility/tenant
    +
Điều kiện nghiệp vụ
    +
Sắp xếp/phân trang
    +
Kiểm tra tính khả dụng cuối trước thao tác đặt
~~~

Không được xem geospatial index hoặc `$near` là cơ chế authorization. Quyền truy cập phải được áp dụng **bên cạnh** điều kiện địa lý.

---

## 2. Dữ liệu địa lý phù hợp với MongoDB

### 2.1. GeoJSON Point

Một listing có vị trí:

~~~javascript
{
  _id: "L-101",
  title: "Căn hộ trung tâm",
  location: {
    type: "Point",
    coordinates: [106.704, 10.776]
  }
}
~~~

GeoJSON dùng thứ tự:

~~~text
coordinates: [longitude, latitude]
               kinh độ    vĩ độ
~~~

**Không** đảo thành `[latitude, longitude]` chỉ vì nhiều API bản đồ hiển thị theo cặp lat/lng. Với hệ tọa độ WGS84 thông dụng:

- Longitude (kinh độ) thường trong khoảng **-180 đến 180**.
- Latitude (vĩ độ) trong khoảng **-90 đến 90**.

### 2.2. Vì sao phải xác thực tọa độ?

Ví dụ:

~~~javascript
coordinates: [10.776, 106.704]
~~~

Vĩ độ 106.704 nằm ngoài miền hợp lệ. Có dữ liệu bị từ chối hoặc gây lỗi index/query.

Một cặp khác cũng bị đảo nhưng vẫn nằm trong miền số hợp lệ thì nguy hiểm hơn: MongoDB có thể lưu một điểm ở nơi khác trên Trái Đất mà không báo rõ ý nghĩa sai.

### 2.3. GeoJSON Polygon

Dùng Polygon cho khu vực, ranh giới dịch vụ, vùng giao hàng hoặc geofence.

~~~javascript
{
  type: "Polygon",
  coordinates: [[
    [106.69, 10.77],
    [106.71, 10.77],
    [106.71, 10.79],
    [106.69, 10.79],
    [106.69, 10.77]
  ]]
}
~~~

Các điểm của vòng ngoài được đóng kín: điểm đầu và điểm cuối trùng nhau. Tọa độ chỉ để minh họa, **không phải ranh giới hành chính hoặc vùng kinh doanh thật**.

### 2.4. Point, Polygon, MultiPolygon

| Dạng dữ liệu | Trường hợp sử dụng |
|---|---|
| `Point` | Nhà/cửa hàng/trạm đón/điểm giao |
| `Polygon` | Một vùng phục vụ, một khu vực tìm kiếm |
| `MultiPolygon` | Nhiều vùng rời nhau được quản lý chung |
| `LineString` | Tuyến đường/tuyến giao nhận theo hình học |
| Một mảng Point | Nhiều vị trí thuộc cùng entity, nếu mô hình thực sự cần |

Không lưu vị trí bằng một string như `"10.776,106.704"` khi muốn dùng các toán tử GeoJSON có index. Phải chuyển thành cấu trúc dữ liệu đúng.

### 2.5. Hình học không thay lộ trình thực tế

Khoảng cách trong `$near` dựa trên hình học địa cầu, **không tự tính tuyến đường, thời gian đi xe, lưu lượng giao thông hoặc cước vận chuyển**. Một căn hộ cách 500 m theo đường chim bay có thể cần đi xa hơn vì sông, cầu hoặc đường một chiều.

Nếu nghiệp vụ cần travel time thực, có thể dùng kết quả MongoDB làm bước chọn ứng viên rồi gọi routing service, với giới hạn số lời gọi và chính sách xử lý dữ liệu ngoài.

---

## 3. Thiết kế collection mẫu cho bài học

Chúng ta dùng database `geo_business_lab`. Dữ liệu minh họa, không phải địa điểm hoặc giá niêm yết thực tế.

### 3.1. Các listing

~~~javascript
use geo_business_lab

db.listings.insertMany([
  {
    _id: "L-101",
    tenantId: "tenant-a",
    title: "Căn hộ gần trung tâm",
    status: "PUBLISHED",
    verified: true,
    location: {
      type: "Point",
      coordinates: [106.704, 10.776]
    },
    category: "APARTMENT",
    pricePerNight: NumberLong("850000"),
    capacity: 2,
    amenities: ["wifi", "parking"],
    rating: 4.7,
    instantBook: true
  },
  {
    _id: "L-102",
    tenantId: "tenant-a",
    title: "Căn hộ gia đình",
    status: "PUBLISHED",
    verified: true,
    location: {
      type: "Point",
      coordinates: [106.716, 10.785]
    },
    category: "APARTMENT",
    pricePerNight: NumberLong("1100000"),
    capacity: 4,
    amenities: ["wifi", "kitchen"],
    rating: 4.5,
    instantBook: false
  },
  {
    _id: "L-103",
    tenantId: "tenant-b",
    title: "Listing thuộc tenant khác",
    status: "PUBLISHED",
    verified: true,
    location: {
      type: "Point",
      coordinates: [106.702, 10.777]
    },
    category: "APARTMENT",
    pricePerNight: NumberLong("700000"),
    capacity: 2,
    amenities: ["wifi"],
    rating: 4.8,
    instantBook: true
  },
  {
    _id: "L-104",
    tenantId: "tenant-a",
    title: "Listing chưa công khai",
    status: "DRAFT",
    verified: false,
    location: {
      type: "Point",
      coordinates: [106.699, 10.778]
    },
    category: "APARTMENT",
    pricePerNight: NumberLong("650000"),
    capacity: 2,
    amenities: ["wifi"],
    rating: 0,
    instantBook: false
  },
  {
    _id: "L-105",
    tenantId: "tenant-a",
    title: "Biệt thự vượt ngân sách",
    status: "PUBLISHED",
    verified: true,
    location: {
      type: "Point",
      coordinates: [106.705, 10.779]
    },
    category: "VILLA",
    pricePerNight: NumberLong("3800000"),
    capacity: 8,
    amenities: ["wifi", "pool"],
    rating: 4.9,
    instantBook: true
  }
]);
~~~

Nếu chạy lại trên cùng database, `_id` trùng sẽ gây lỗi duplicate key. Dùng database lab mới hoặc dọn dữ liệu có chủ đích; không chạy các lệnh xóa rộng trên production.

### 3.2. Index địa lý cơ bản

~~~javascript
db.listings.createIndex(
  {
    location: "2dsphere"
  },
  {
    name: "idx_listings_location_2dsphere"
  }
);
~~~

MongoDB dùng `2dsphere` index cho truy vấn spherical geometry với GeoJSON.

### 3.3. Compound index kết hợp nghiệp vụ

~~~javascript
db.listings.createIndex(
  {
    tenantId: 1,
    status: 1,
    location: "2dsphere"
  },
  {
    name: "idx_listings_tenant_status_geo"
  }
);
~~~

Đây là **một phương án index ứng viên**. Hiệu quả tùy filter selectivity, phân bố tenant, số listings, bán kính và query shape. Không mặc định index này luôn thắng các lựa chọn khác mà không kiểm tra explain.

### 3.4. Index cho bookings

~~~javascript
db.bookings.createIndex(
  {
    listingId: 1,
    status: 1,
    checkIn: 1,
    checkOut: 1
  },
  {
    name: "idx_bookings_listing_status_interval"
  }
);
~~~

Index này hỗ trợ một số phần của truy vấn tìm booking xung đột. Việc lọc hai điều kiện bất đẳng thức trên khoảng thời gian không có nghĩa index có thể giải quyết tối ưu mọi điều kiện; cần đo workload và cân nhắc mô hình calendar/availability được tiền tính.

---

## 4. `$near`: chọn các địa điểm hợp lệ và gần nhất

### 4.1. Truy vấn kết hợp nhiều điều kiện

~~~javascript
const origin = {
  type: "Point",
  coordinates: [106.70098, 10.77689]
};

db.listings.find(
  {
    tenantId: "tenant-a",
    status: "PUBLISHED",
    verified: true,
    capacity: { $gte: 2 },
    pricePerNight: {
      $lte: NumberLong("1200000")
    },
    amenities: "wifi",
    location: {
      $near: {
        $geometry: origin,
        $maxDistance: 3000
      }
    }
  },
  {
    title: 1,
    pricePerNight: 1,
    capacity: 1,
    amenities: 1,
    location: 1
  }
).limit(20);
~~~

Kết quả mong muốn là những documents đáp ứng **tất cả** predicate trên, được sắp theo độ gần với origin theo semantics của `$near`.

### 4.2. `$near` đảm nhiệm việc gì?

- Tìm những vị trí gần một điểm.
- Dùng geospatial index phù hợp.
- Kết quả được sắp xếp theo khoảng cách gần trước xa sau.
- Có thể giới hạn bán kính bằng `$maxDistance`.
- Có thể bỏ vùng quá gần bằng `$minDistance` khi bài toán cần.

### 4.3. `$maxDistance` tính bằng gì?

Khi dùng **GeoJSON Point với `2dsphere`** như trên, `$maxDistance` là khoảng cách tính bằng **mét**.

~~~javascript
$maxDistance: 3000
~~~

nghĩa là 3.000 m theo khoảng cách địa lý phù hợp, **không** phải 3.000 km và **không** phải số radian.

### 4.4. Điều kiện AND ngầm định

Document filter:

~~~javascript
{
  tenantId: "tenant-a",
  status: "PUBLISHED",
  verified: true,
  location: { $near: { ... } }
}
~~~

thể hiện **AND**: tất cả field-level predicates phải thỏa mãn. Không cần bọc trong `$and` nếu không có lý do đặc biệt.

### 4.5. Kết quả gần không nhất thiết rẻ

`$near` sắp theo khoảng cách. Nếu muốn “rẻ nhất trong 3 km”, đó là một **ranking khác**. Thêm `.sort({pricePerNight:1})` cần hiểu plan và có thể phát sinh chi phí sắp xếp; nếu muốn tính distance field và ranking đa tiêu chí, `$geoNear` aggregation thường rõ ràng hơn.

### 4.6. Khi không nên dùng `$near`

Nếu chỉ cần kiểm tra “điểm này có thuộc một vùng hay không” và **không cần khoảng cách/sort gần nhất**, `$geoWithin` hoặc `$geoIntersects` có thể phù hợp hơn.

Không sử dụng `$near` như phép kiểm tra authorization/booking. Điều kiện visibility và quyền truy cập vẫn bắt buộc.

---

## 5. `$nearSphere` và các phép đo khoảng cách

### 5.1. `$near` và `$nearSphere`

`$nearSphere` biểu diễn tìm gần trên hình cầu. Với GeoJSON và `2dsphere`, MongoDB cung cấp những cách query near với semantics spherical phù hợp. Không chọn toán tử chỉ theo tên “Sphere” rồi bỏ qua loại geometry/index và đơn vị.

Ví dụ:

~~~javascript
db.listings.find({
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  },
  tenantId: "tenant-a",
  status: "PUBLISHED"
});
~~~

### 5.2. Khoảng cách thẳng không phải quãng đường di chuyển

Độ gần mà geospatial query trả về có thể dùng làm pre-filter cho:

- Phân phối cửa hàng cho khách.
- Chọn căn hộ quanh một điểm đến.
- Chọn trạm đón xe.
- Gợi ý địa điểm trong bán kính.

Nhưng tuyến đường thực tế còn phụ thuộc giao thông/địa hình, nên không tự quy đổi 3 km gần nhất thành thời gian giao 5 phút.

### 5.3. Cùng khoảng cách, kết quả có thứ tự ổn định không?

Nhiều items có thể có khoảng cách gần như bằng nhau. Một query chỉ sắp theo distance có thể không có **stable tie-break** về ID khi dữ liệu thay đổi.

Nếu API có phân trang hoặc cần kết quả quyết định, nên định nghĩa thứ tự phụ (ví dụ `_id`) trong aggregation hoặc business ranking rõ ràng và kiểm thử. Không giả định vị trí thứ hai luôn xuất hiện cùng thứ tự khi khoảng cách bằng nhau.

---

## 6. `$geoWithin`: lọc điểm trong vùng, không cần nearest sort

### 6.1. Khu vực tìm kiếm dạng Polygon

Người dùng vẽ một khung trên bản đồ. Ta muốn tìm listings nằm **bên trong** vùng và đáp ứng chính sách kinh doanh:

~~~javascript
const area = {
  type: "Polygon",
  coordinates: [[
    [106.69, 10.77],
    [106.71, 10.77],
    [106.71, 10.79],
    [106.69, 10.79],
    [106.69, 10.77]
  ]]
};

db.listings.find({
  tenantId: "tenant-a",
  status: "PUBLISHED",
  verified: true,
  pricePerNight: {
    $lte: NumberLong("1200000")
  },
  location: {
    $geoWithin: {
      $geometry: area
    }
  }
});
~~~

### 6.2. Khác với `$near`

| Thuộc tính | `$near` | `$geoWithin` |
|---|---|---|
| Đối tượng đầu vào | Điểm origin | Hình học vùng |
| Mục tiêu chính | Gần một điểm | Nằm trong vùng |
| Tự sắp theo độ gần | Có | **Không** |
| Distance field trả về | Không tự tạo field đo khoảng cách | Không tự tạo |
| Sắp theo giá/rating | Cần xử lý ranking | Dễ thêm sort thông thường, nhưng cần plan |
| Trường hợp phổ biến | “Gần tôi” | “Trong khu vực bản đồ” |

### 6.3. Polygon phải hợp lệ

- GeoJSON dùng vòng tọa độ đóng.
- Thứ tự longitude/latitude.
- Không tạo vòng tự cắt nhau hoặc hình học không hợp lệ.
- Với Polygon/MultiPolygon phức tạp, cần quan tâm lỗ, hướng vòng, đường qua kinh tuyến 180°, vùng lớn hơn nửa bán cầu và semantics spherical của MongoDB.
- Với dữ liệu bản đồ từ nguồn ngoài, validate/normalize trước khi ghi.

### 6.4. Ranh giới vùng

Một điểm nằm sát ranh giới có thể gây vấn đề do độ chính xác tọa độ, semantics của toán tử hoặc polygon có nguồn dữ liệu chưa thống nhất. Đặc biệt với những quyết định có tính phí/quy định, hãy định nghĩa **boundary policy** và kiểm thử điểm trên cạnh/đỉnh; không dựa vào trực giác nhìn trên bản đồ.

### 6.5. Truy vấn trong vòng tròn bằng `$centerSphere`

Nếu chỉ cần danh sách trong 3 km và **không cần sắp nearest**, có thể dùng:

~~~javascript
const earthRadiusMeters = 6378137;
const radiusMeters = 3000;

db.listings.find({
  tenantId: "tenant-a",
  status: "PUBLISHED",
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.70098, 10.77689],
        radiusMeters / earthRadiusMeters
      ]
    }
  }
});
~~~

`$centerSphere` nhận **bán kính theo radian** — phép chia khoảng cách mét cho bán kính Trái Đất (giá trị tham khảo). Đây là điểm rất dễ nhầm với `$near.$maxDistance`, vốn nhận mét cho GeoJSON Point.

---

## 7. `$geoIntersects`: vùng dịch vụ chứa điểm khách hàng

### 7.1. Bài toán delivery coverage

Một nhà bán hàng có thể có một Polygon biểu diễn **vùng giao hàng**. Khách nhập địa điểm nhận. Cần tìm vùng dịch vụ:

- Đang hoạt động.
- Thuộc tenant thích hợp.
- Giao với vị trí khách.
- Cho phép dịch vụ STANDARD.
- Đơn hàng đáp ứng `minOrderAmount`.

### 7.2. Data model cho vùng giao hàng

~~~javascript
db.deliveryZones.insertMany([
  {
    _id: "ZONE-A",
    tenantId: "tenant-a",
    name: "Vùng giao nội thành A",
    active: true,
    supportedServices: ["STANDARD", "EXPRESS"],
    minOrderAmount: NumberLong("150000"),
    area: {
      type: "Polygon",
      coordinates: [[
        [106.69, 10.77],
        [106.72, 10.77],
        [106.72, 10.80],
        [106.69, 10.80],
        [106.69, 10.77]
      ]]
    }
  },
  {
    _id: "ZONE-B",
    tenantId: "tenant-a",
    name: "Vùng ngừng hoạt động",
    active: false,
    supportedServices: ["STANDARD"],
    minOrderAmount: NumberLong("100000"),
    area: {
      type: "Polygon",
      coordinates: [[
        [106.68, 10.76],
        [106.73, 10.76],
        [106.73, 10.81],
        [106.68, 10.81],
        [106.68, 10.76]
      ]]
    }
  }
]);
~~~

### 7.3. Index vùng

~~~javascript
db.deliveryZones.createIndex(
  { area: "2dsphere" },
  { name: "idx_delivery_zone_area" }
);
~~~

### 7.4. Query vùng phù hợp

~~~javascript
const customerPoint = {
  type: "Point",
  coordinates: [106.70098, 10.77689]
};

const cartTotal = NumberLong("300000");

db.deliveryZones.find({
  tenantId: "tenant-a",
  active: true,
  supportedServices: "STANDARD",
  minOrderAmount: { $lte: cartTotal },
  area: {
    $geoIntersects: {
      $geometry: customerPoint
    }
  }
});
~~~

Query này hỏi: **stored Polygon `area` có giao với geometry của điểm khách hay không?** Với Polygon bao điểm và semantics phù hợp, kết quả là những vùng ứng viên đáp ứng business predicates.

### 7.5. Đừng đảo hướng của bài toán

- Listing location là **Point**; người dùng vẽ vùng **Polygon**: thường dùng `location:{$geoWithin:{$geometry:polygon}}`.
- Dịch vụ lưu vùng **Polygon**; khách là **Point**: dùng `area:{$geoIntersects:{$geometry:customerPoint}}`.

Không nhầm “Point trong Polygon” với “stored Polygon nằm hoàn toàn trong một Point”. `$geoWithin` không phải công thức thay thế trực tiếp cho mọi truy vấn coverage.

### 7.6. Coverage chưa đồng nghĩa giao hàng được ngay

Ngoài hình học cần kiểm tra:

- Chi nhánh/cửa hàng đang mở.
- Năng lực tài xế.
- Hàng tồn.
- Địa chỉ không bị hạn chế.
- Chính sách giao hàng theo ngày/giờ.
- Khoảng cách tuyến đường nếu đơn giá phụ thuộc quãng đường.
- Phí và minimum order.
- Quyền truy cập theo tenant/khu vực.

Vùng hình học chỉ là **một thành phần của quyết định nghiệp vụ**.

---

## 8. `$geoNear`: nhận khoảng cách và phối hợp aggregation

### 8.1. Khi nào dùng aggregation?

`$near` phù hợp khi chỉ cần danh sách gần nhất. Nếu cần:

- Trả về `distanceMeters`.
- Tính điểm xếp hạng.
- Join booking/calendar hoặc bảng metadata.
- Tạo facets/nhóm giá.
- Giới hạn, chiếu fields và xử lý tiếp bằng pipeline.

hãy dùng `$geoNear`.

### 8.2. `$geoNear` phải ở đầu pipeline

Ví dụ:

~~~javascript
const searchPoint = {
  type: "Point",
  coordinates: [106.70098, 10.77689]
};

db.listings.aggregate([
  {
    $geoNear: {
      near: searchPoint,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 5000,
      spherical: true,
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED",
        verified: true,
        capacity: { $gte: 2 },
        pricePerNight: {
          $lte: NumberLong("1200000")
        },
        amenities: "wifi"
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      pricePerNight: 1,
      capacity: 1,
      rating: 1,
      distanceMeters: 1
    }
  },
  {
    $limit: 20
  }
]);
~~~

`$geoNear` cho kết quả đã được sắp theo khoảng cách, tính field `distanceMeters`, và hỗ trợ business predicates trong `query`.

### 8.3. Vì sao dùng `query`?

Vì `$geoNear` phải là stage đầu, không viết:

~~~javascript
[
  { $match: { status: "PUBLISHED" } },
  { $geoNear: { ... } }
]
~~~

để “lọc trước rồi geoNear”. Cách đó không tuân theo yêu cầu vị trí stage tiêu chuẩn. Đưa những field-level business filters có thể đặt trong `$geoNear.query`.

### 8.4. `key` có ý nghĩa gì?

Nếu collection có nhiều geospatial indexes, `key:"location"` chỉ rõ field dùng để thực hiện `$geoNear`. Dù có một field, khai báo rõ giúp query dễ đọc và giảm mơ hồ.

### 8.5. `distanceField` và đơn vị

Với GeoJSON Point, `2dsphere` và `spherical:true` trong ví dụ này, khoảng cách thường theo **mét**. Có thể hiển thị km bằng cách chia cho 1000:

~~~javascript
db.listings.aggregate([
  {
    $geoNear: {
      near: searchPoint,
      key: "location",
      spherical: true,
      distanceField: "distanceMeters",
      maxDistance: 5000,
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED"
      }
    }
  },
  {
    $addFields: {
      distanceKm: {
        $divide: ["$distanceMeters", 1000]
      }
    }
  },
  {
    $project: {
      title: 1,
      distanceKm: 1,
      distanceMeters: 1
    }
  },
  {
    $limit: 20
  }
]);
~~~

Không tự coi khoảng cách đường chim bay là estimated driving distance hoặc ETA.

### 8.6. `$geoNear.query` không phải nơi lồng một `$near` thứ hai

Chỉ định geometry nguồn bằng `near` của `$geoNear`, rồi đặt các điều kiện **non-geospatial/business** phù hợp ở `query`. Không ghép thêm `$near` trong đó để tạo “double proximity”.

---

## 9. Ghép điều kiện theo logic boolean

### 9.1. AND

Khách cần giá tối đa, Wi-Fi, sức chứa phù hợp:

~~~javascript
{
  capacity: { $gte: 2 },
  pricePerNight: {
    $lte: NumberLong("1200000")
  },
  amenities: "wifi"
}
~~~

Các điều kiện field-level cùng xuất hiện thường mang logic AND.

### 9.2. `$in`: nhiều loại hình được chấp nhận

~~~javascript
{
  category: {
    $in: ["APARTMENT", "STUDIO"]
  }
}
~~~

Kết hợp điều kiện này với `location.$near` hoặc `$geoNear.query` khi phù hợp.

### 9.3. `$all`: tất cả tiện nghi yêu cầu

~~~javascript
{
  amenities: {
    $all: ["wifi", "parking"]
  }
}
~~~

Khác với:

~~~javascript
{
  amenities: {
    $in: ["wifi", "parking"]
  }
}
~~~

`$all` cần có cả hai; `$in` chỉ yêu cầu một giá trị trong tập.

### 9.4. `$or` cho các lựa chọn nghiệp vụ

Ví dụ chỉ chấp nhận listing **instantBook** hoặc **có quy trình duyệt được hỗ trợ**:

~~~javascript
{
  $or: [
    { instantBook: true },
    { manualApprovalAllowed: true }
  ]
}
~~~

Có thể kết hợp `$or` business filters trong pipeline/`$geoNear.query` theo giới hạn toán tử và query planner. Nhưng bản thân `$near` có các giới hạn khi kết hợp trực tiếp với `$or`; không tự ghép một `$near` vào mỗi nhánh `$or` và giả định plan giống một query nearest duy nhất.

### 9.5. Business rule phụ thuộc người dùng

Ví dụ:

- User VIP có thể xem listing PREMIUM.
- Khách nội địa có thể đặt sản phẩm cho thị trường nội địa.
- Tài khoản đã xác minh có thể thấy listing yêu cầu xác minh.

Hãy **xác thực và quyết định policy ở service layer**, sau đó truyền predicate được xây từ ngữ cảnh trusted. Không cho client tự đặt:

~~~json
{
  "tenantId": "tenant-admin",
  "includeUnpublished": true
}
~~~

để vượt quyền truy cập.

### 9.6. Không dùng business rules sai trong những predicate đơn giản

Ví dụ `rating:{$gte:4.5}` có thể loại listing mới chưa có review. Nếu nghiệp vụ muốn “rating >= 4.5 **hoặc chưa được đánh giá**”, phải mô hình hóa quy tắc đó rõ ràng; không tự suy từ một điều kiện đơn lẻ.

---

## 10. Danh sách gần nhất và điều kiện từ collection khác

Đôi khi một listing hợp lệ về vị trí/giá nhưng **bị đặt kín trong ngày người dùng yêu cầu**. Booking được lưu ở collection riêng:

~~~javascript
{
  _id: "B-1001",
  listingId: "L-101",
  status: "CONFIRMED",
  checkIn: ISODate("2026-12-10T00:00:00Z"),
  checkOut: ISODate("2026-12-13T00:00:00Z")
}
~~~

### 10.1. Quy tắc giao nhau của hai khoảng thời gian

Với quy ước khoảng nửa mở `[start, end)`, hai booking xung đột khi:

\[
\text{existing.checkIn} < \text{requested.checkOut}
\]

và

\[
\text{existing.checkOut} > \text{requested.checkIn}
\]

Ví dụ khách rời phòng ngày 13, khách tiếp theo nhận phòng từ ngày 13 có thể **không xung đột** nếu hệ thống dùng quy tắc checkout/checkin đúng và không có buffer bắt buộc.

### 10.2. Kiểm tra cho một listing

~~~javascript
const requestedCheckIn =
  ISODate("2026-12-10T00:00:00Z");

const requestedCheckOut =
  ISODate("2026-12-13T00:00:00Z");

db.bookings.find({
  listingId: "L-101",
  status: {
    $in: ["CONFIRMED", "HELD"]
  },
  checkIn: { $lt: requestedCheckOut },
  checkOut: { $gt: requestedCheckIn }
});
~~~

Nếu query trả documents xung đột, listing có thể không còn phù hợp.

**Lưu ý:** Trong production, trạng thái `HELD` có thể hết hạn; cần kiểm tra `holdExpiresAt` hoặc cleanup đúng cách, không để hold cũ chặn chỗ vĩnh viễn.

### 10.3. Múi giờ rất quan trọng

Ngày nhận phòng được người dùng chọn theo **múi giờ của chỗ lưu trú/chính sách sản phẩm**, không nhất thiết là UTC midnight. Hãy chuẩn hóa từ ngày local sang khoảng thời gian lưu trữ phù hợp; không tùy ý convert một local date thành `00:00Z` nếu nghiệp vụ dùng timezone khác.

### 10.4. Tìm kiếm availability khác việc chốt booking

Một query địa lý kết hợp booking có thể trả listing khả dụng lúc 10:00:00. Hai khách có thể cùng nhìn thấy listing, rồi cả hai nhấn “Đặt” ngay sau đó.

Kết quả tìm kiếm là **thông tin tạm thời**. Để tránh overbooking phải dùng **conditional write, transaction, unique slot/hold hoặc cơ chế đồng bộ tương đương** khi xác nhận booking.

---

## 11. Aggregation: `$geoNear` kết hợp `$lookup` bookings

### 11.1. Bài toán

Tìm listing trong 5 km, công khai, thuộc tenant hiện tại, đáp ứng giá và sức chứa, **không có booking giao thời gian**.

### 11.2. Pipeline minh họa

~~~javascript
const point = {
  type: "Point",
  coordinates: [106.70098, 10.77689]
};

const checkIn = ISODate("2026-12-10T00:00:00Z");
const checkOut = ISODate("2026-12-13T00:00:00Z");

db.listings.aggregate([
  {
    $geoNear: {
      near: point,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 5000,
      spherical: true,
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED",
        verified: true,
        capacity: { $gte: 2 },
        pricePerNight: {
          $lte: NumberLong("1200000")
        }
      }
    }
  },
  {
    $lookup: {
      from: "bookings",
      let: {
        currentListingId: "$_id"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                {
                  $eq: [
                    "$listingId",
                    "$$currentListingId"
                  ]
                },
                {
                  $in: [
                    "$status",
                    ["CONFIRMED", "HELD"]
                  ]
                },
                {
                  $lt: ["$checkIn", checkOut]
                },
                {
                  $gt: ["$checkOut", checkIn]
                }
              ]
            }
          }
        },
        {
          $limit: 1
        }
      ],
      as: "conflictingBookings"
    }
  },
  {
    $match: {
      conflictingBookings: {
        $size: 0
      }
    }
  },
  {
    $project: {
      title: 1,
      pricePerNight: 1,
      capacity: 1,
      distanceMeters: 1
    }
  },
  {
    $limit: 20
  }
]);
~~~

### 11.3. Ý nghĩa

- `$geoNear`: ứng viên gần + business predicates cùng collection.
- `$lookup`: truy vấn bookings theo từng listing.
- `$match`: chỉ giữ listing không có booking xung đột.
- `$project`: trả fields cần thiết.
- `$limit`: giới hạn số kết quả sau khi kiểm tra availability.

### 11.4. Vì sao không đặt `$limit:20` ngay sau `$geoNear`?

Giả sử 20 căn gần nhất đều đã được đặt, nhưng căn thứ 21–30 còn trống. Nếu limit trước lookup, query chỉ xem 20 căn đó rồi trả 0, **bỏ sót những căn hợp lệ ở xa hơn**.

Đây là khác biệt giữa:

> “Lấy 20 căn gần nhất rồi bỏ căn không phù hợp.”

và:

> “Lấy 20 căn **phù hợp** gần nhất.”

Hai yêu cầu có thể cho kết quả khác nhau rất lớn.

### 11.5. Chi phí performance

Ngược lại, để lookup tất cả listings trong bán kính rồi mới limit có thể rất tốn kém. Những giải pháp có thể cân nhắc:

- Đặt radius hợp lý.
- Tăng selectivity của predicates trong `$geoNear.query`.
- Tạo index phù hợp cho bookings.
- Dùng availability calendar/summary tiền tính.
- Two-phase search: lấy candidates đủ lớn, kiểm tra availability theo batch, lấy thêm khi cần.
- Precomputed search view cho điều kiện availability phổ biến.
- Benchmark bằng dữ liệu tương tự production.

**Trade-off:** Two-phase lấy trước N candidates có thể không đảm bảo top K đầy đủ nếu không lặp tăng cửa sổ ứng viên cho đến khi đủ hoặc hết phạm vi tìm kiếm.

### 11.6. Nếu dữ liệu bookings thay đổi trong lúc query?

Ngay cả pipeline trả chính xác tại thời điểm đọc cũng không đồng nghĩa booking sẽ còn trống ở lúc người dùng xác nhận. Bước checkout cần bảo vệ invariant bằng atomic write/transaction.

---

## 12. Chặn overbooking khi xác nhận

### 12.1. Không tin kết quả search là một lock

Hai requests:

~~~text
Khách A: query thấy L-101 còn trống
Khách B: query thấy L-101 còn trống
Khách A: xác nhận
Khách B: xác nhận
~~~

Nếu code chỉ `insertOne` vào bookings mà không bảo vệ uniqueness của time slots, cả hai có thể cùng tạo booking xung đột.

### 12.2. Ví dụ night locks cho một đơn vị lưu trú

Với listing chỉ cho **một booking trong mỗi đêm**, có thể dùng collection `listingNightLocks` có unique `_id` cấu tạo từ listingId và ngày.

~~~javascript
{
  _id: "L-101:2026-12-10",
  listingId: "L-101",
  night: "2026-12-10",
  bookingId: "B-2001"
}
~~~

Nếu một booking cần các đêm 10, 11, 12, transaction cố insert cả ba night-lock documents cùng booking.

### 12.3. Java/Mongosh logic khái niệm

~~~text
startTransaction
    |
    +-- insert lock "L-101:2026-12-10"
    +-- insert lock "L-101:2026-12-11"
    +-- insert lock "L-101:2026-12-12"
    +-- insert booking B-2001
    |
commitTransaction
~~~

Nếu một night lock `_id` đã tồn tại, unique constraint sẽ làm transaction thất bại; phải abort theo chính sách. Nhờ đó, hai confirmations cho cùng listing-night không thể cùng được chấp nhận như hai lock duy nhất.

### 12.4. Giới hạn của night-lock pattern

- Cần định nghĩa đêm theo timezone của listing.
- Cần release locks theo trạng thái booking/cancellation.
- Hold tạm thời cần TTL/expiry và quy trình tranh chấp an toàn.
- Một listing có nhiều phòng/đơn vị có capacity >1 cần mô hình khác.
- Booking theo giờ cần time slots phù hợp.
- Phải xử lý unknown commit result/idempotency.
- Không bảo đảm mọi hạn chế kinh doanh khác chỉ bằng unique ID.

Đây là **ví dụ chống double-booking cho một loại capacity**, không phải mô hình chung cho mọi hệ thống đặt phòng.

---

## 13. Compound `2dsphere` indexes và business predicates

### 13.1. Index địa lý đơn

~~~javascript
db.listings.createIndex({
  location: "2dsphere"
});
~~~

Phù hợp với các query địa lý cơ bản.

### 13.2. Compound index

~~~javascript
db.listings.createIndex(
  {
    tenantId: 1,
    status: 1,
    location: "2dsphere"
  },
  {
    name: "idx_tenant_status_location"
  }
);
~~~

Một compound geospatial index có thể giúp planner xử lý cả điều kiện kinh doanh và vị trí khi query shape phù hợp.

### 13.3. Thêm nhiều fields không luôn tốt

Ví dụ:

~~~javascript
db.listings.createIndex({
  tenantId: 1,
  status: 1,
  location: "2dsphere",
  pricePerNight: 1,
  capacity: 1,
  rating: -1
});
~~~

Index này **không tự đảm bảo** rằng giá, capacity, rating đều được lọc và sort tối ưu đồng thời. Geospatial access, inequality predicates, multikey fields và sort có nhiều ràng buộc; index càng lớn càng tăng storage/write overhead.

Nên đề xuất một vài index candidates dựa trên workload rồi dùng `explain("executionStats")` để chọn.

### 13.4. Index cho tenant isolation

Một sản phẩm nhiều tenant thường truy vấn:

~~~javascript
{
  tenantId: trustedTenantId,
  status: "PUBLISHED",
  location: { $near: { ... } }
}
~~~

`tenantId` có selectivity tốt trong một số workload; đặt nó vào compound index có thể hữu ích. Tuy nhiên phải dựa trên phân bố tenant thực tế. Không biến index thành security boundary: query vẫn phải xác thực tenant.

### 13.5. Partial index cho listing công khai

Ví dụ chỉ lập index những listing đang công khai:

~~~javascript
db.listings.createIndex(
  {
    tenantId: 1,
    location: "2dsphere"
  },
  {
    name: "idx_public_tenant_location",
    partialFilterExpression: {
      status: "PUBLISHED"
    }
  }
);
~~~

Query muốn sử dụng partial index an toàn cần có predicate phù hợp, ví dụ `status:"PUBLISHED"`. Nếu query cần DRAFT, index này không bao phủ dữ liệu đó; query planner sẽ cần đường khác.

### 13.6. `2dsphere` index có tính sparse

`2dsphere` index có hành vi sparse: documents thiếu geospatial field hoặc có giá trị phù hợp quy tắc không thể được index như Point sẽ không nằm trong geospatial index bình thường. Với **compound `2dsphere` index**, việc một document thiếu location vẫn ảnh hưởng khả năng được geospatial index bao phủ dù các business fields có giá trị.

Đừng dựa vào `tenantId` trong compound geo index để tìm **tất cả** listings bao gồm listings chưa có location.

### 13.7. Cập nhật vị trí có chi phí

Mỗi khi listing đổi location, MongoDB phải cập nhật index geospatial. Với đối tượng di chuyển liên tục (shipper, taxi), write rate và index updates có thể cao; cần cân nhắc tần suất cập nhật, dữ liệu “last known location”, TTL/retention và kiến trúc real-time phù hợp.

---

## 14. `explain()`: kiểm tra query thật sự dùng index như thế nào

### 14.1. Ví dụ với find

~~~javascript
db.listings.find({
  tenantId: "tenant-a",
  status: "PUBLISHED",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  }
}).explain("executionStats");
~~~

### 14.2. Ví dụ với aggregation

~~~javascript
db.listings.explain("executionStats").aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      key: "location",
      spherical: true,
      maxDistance: 3000,
      distanceField: "distanceMeters",
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED"
      }
    }
  },
  { $limit: 20 }
]);
~~~

### 14.3. Những chỉ số cần quan sát

| Chỉ số/thông tin | Ý nghĩa |
|---|---|
| `winningPlan` | Query plan được chọn |
| Geospatial index access | Có sử dụng chỉ mục địa lý phù hợp không |
| `totalKeysExamined` | Số index keys phải xét |
| `totalDocsExamined` | Số documents được kiểm tra |
| `nReturned` | Số documents trả |
| Execution time | Thời gian theo môi trường đo |
| Sort stage | Có sort tốn memory/CPU không |
| Rejected plans | Những phương án khác được planner cân nhắc |

Tên stages và cấu trúc explain output có thể thay đổi theo MongoDB version/engine. Không viết test production cứng theo một stage name duy nhất.

### 14.4. Selectivity của predicates

Nếu bán kính 50 km bao phủ 1 triệu listings nhưng chỉ 0,1% là active cho tenant hiện tại, query có thể phải xét nhiều ứng viên trước khi đủ kết quả. Compound index, partial index và filter strategy rất quan trọng.

Ngược lại, nếu bán kính 200 m chỉ có 10 listings, một geo-only index có thể đã đủ. Không có một index tuyệt đối tối ưu cho mọi bán kính.

### 14.5. Benchmark đúng dữ liệu

Dữ liệu lab vài documents không chứng minh query nhanh ở production. Cần đo với:

- Số lượng locations lớn.
- Spatial distribution thực tế.
- Tenant skew.
- Dữ liệu rải rác vs tập trung.
- Thời gian peak traffic.
- Bán kính 100 m, 3 km, 50 km.
- Những query trả rất ít và trả rất nhiều kết quả.
- Tỉ lệ listings thiếu geolocation.
- Giá và rating distribution.

---

## 15. Sorting: gần nhất, rẻ nhất hay phù hợp nhất?

### 15.1. Xác định ranking trước khi viết query

Ba yêu cầu khác nhau:

1. **Gần nhất:** sort theo distance.
2. **Rẻ nhất trong vùng:** lọc vùng + giá rồi sort theo price.
3. **Phù hợp nhất:** distance, giá, rating, xác minh, booking availability và business weights.

Đừng trả nearest list rồi gắn nhãn “phù hợp nhất” nếu chưa xác định business ranking.

### 15.2. `$geoNear` trả distance

Ví dụ thêm điểm xếp hạng minh họa:

~~~javascript
db.listings.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      distanceField: "distanceMeters",
      key: "location",
      spherical: true,
      maxDistance: 3000,
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED",
        verified: true
      }
    }
  },
  {
    $addFields: {
      rankingScore: {
        $subtract: [
          { $multiply: ["$rating", 1000] },
          "$distanceMeters"
        ]
      }
    }
  },
  {
    $sort: {
      rankingScore: -1,
      _id: 1
    }
  },
  { $limit: 20 },
  {
    $project: {
      title: 1,
      distanceMeters: 1,
      rating: 1,
      rankingScore: 1
    }
  }
]);
~~~

Công thức **chỉ là ví dụ kỹ thuật**, không phải thuật toán gợi ý tốt trong production. Hệ số 1000 là tùy ý; phải chuẩn hóa thang đo, fairness và business requirements.

### 15.3. Tại sao sort phải trước limit khi muốn global ranking?

Nếu lấy 20 listing gần nhất rồi mới sort theo giá/rating, listing thứ 21 gần hơn ít nhưng giá/rating xuất sắc có thể bị loại. Nếu yêu cầu “top 20 theo rankingScore trong bán kính 3 km”, cần tính/sort trên **tập ứng viên hợp lệ** trước khi limit, hoặc dùng thuật toán top-k có bảo đảm tương đương.

### 15.4. Giới hạn candidate set

Vì tính score/sort toàn bộ các điểm trong bán kính lớn có thể tốn tài nguyên, nên:

- Giới hạn hợp lý `maxDistance`.
- Lọc tenant/status/verified/price trước khi ranking.
- Giữ payload nhỏ.
- Tiền tính những tín hiệu ổn định.
- Có fallback nếu phạm vi quá lớn.
- Quan sát sort memory/spill và query latency.

---

## 16. Phân trang với kết quả địa lý

### 16.1. Cách đơn giản: `skip` và `limit`

~~~javascript
db.listings.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 5000,
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED"
      }
    }
  },
  { $skip: 40 },
  { $limit: 20 }
]);
~~~

Phù hợp minh họa page 3 với page size 20. Nhưng deep pagination với skip lớn thường tốn chi phí.

### 16.2. Định nghĩa thứ tự ổn định

Nếu có nhiều kết quả khoảng cách gần bằng nhau, nên có tie-breaker, ví dụ:

~~~javascript
{
  $sort: {
    distanceMeters: 1,
    _id: 1
  }
}
~~~

Stage sort có thể tốn thêm tài nguyên; nhưng thứ tự quyết định quan trọng với pagination.

### 16.3. Cursor/keyset pagination

Một cách nâng cao là dùng token chứa:

- Origin và radius đã cố định.
- Business filter signature.
- Distance/score cuối được trả.
- Tie-breaker `_id`.
- Optional version của snapshot/ranking.

Sau đó lấy các kết quả sau mốc đó. Tuy nhiên:

- Floating-point distance có vấn đề so sánh chính xác.
- User thay origin làm toàn bộ khoảng cách đổi.
- Listing bị thêm/xóa/cập nhật có thể làm thứ tự thay đổi giữa pages.
- `$geoNear` vẫn cần là stage đầu.
- Khi có booking availability thay đổi theo thời gian, pagination không đảm bảo snapshot bất biến giữa requests.

Không viết một token “distance+id” đơn giản rồi tuyên bố luôn không duplicate/skip trong dữ liệu động. Cần hợp đồng paging và test.

### 16.4. Map viewport thay đổi

Khi người dùng pan/zoom bản đồ:

- Origin hoặc Polygon có thể thay đổi.
- Radius/filters đổi.
- Pagination token cũ có thể không còn hợp lệ.

Trả trang đầu cho một query context mới. Caching phải có key theo tenant, tọa độ được chuẩn hóa, radius, filters và version phù hợp.

---

## 17. Tìm kiếm theo viewport: geoWithin hay near?

### 17.1. “Hiển thị tất cả trong hình chữ nhật bản đồ”

Dùng polygon/geometry biểu diễn viewport:

~~~javascript
db.listings.find({
  tenantId: "tenant-a",
  status: "PUBLISHED",
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.69, 10.77],
          [106.72, 10.77],
          [106.72, 10.80],
          [106.69, 10.80],
          [106.69, 10.77]
        ]]
      }
    }
  }
});
~~~

### 17.2. “Hiển thị 10 địa điểm gần trung tâm”

Dùng `$near` hoặc `$geoNear` với origin và bán kính.

### 17.3. Viewport lớn cần hạn chế số marker

Nếu map hiển thị hàng chục nghìn points, vấn đề không chỉ query speed mà còn rendering/client memory. Có thể:

- Chỉ lấy fields cần cho marker.
- Cluster points theo zoom/grid (thực hiện ở tầng ứng dụng hoặc pipeline phù hợp).
- Giới hạn/lấy mẫu theo business rules.
- Chia viewport thành tiles có cache.
- Trả tổng count/facet riêng nếu cần.

Không tự lấy 100 điểm gần nhất rồi hiển thị như thể “đó là tất cả listing trong viewport”.

### 17.4. Viewport vượt qua kinh tuyến 180°

Nếu ứng dụng toàn cầu, bounding box có thể vượt antimeridian. Một rectangle đơn giản nối từ longitude 179 sang -179 có thể bị hiểu sai nếu không xử lý spherical geometry thích hợp. Sử dụng dữ liệu Polygon/MultiPolygon được tạo đúng theo MongoDB semantics và test vùng biên.

---

## 18. Độ chính xác và bất biến nghiệp vụ

### 18.1. Tọa độ do người dùng nhập là đầu vào chưa đáng tin

Kiểm tra:

- longitude, latitude là số hữu hạn.
- Phạm vi hợp lệ.
- Không là null, NaN hoặc infinity.
- Đúng thứ tự.
- Không vượt radius tối đa.
- Không tạo Polygon tự cắt/cực lớn theo dữ liệu user chưa được kiểm soát.
- Giới hạn số vertices để tránh truy vấn quá nặng.

### 18.2. Radius của người dùng cần server-side cap

Ví dụ người dùng gửi radius 500.000 km. Dù API hỗ trợ một trường radius, server nên có max allowed radius và default rõ ràng:

~~~text
UI radius: 3 km
Backend validated radius: 3000 meters
Server maximum: do business define, ví dụ 50 km
~~~

Con số max ở đây chỉ minh họa, không phải MongoDB limit.

### 18.3. Đừng dùng geospatial result làm authorization

Một listing gần khách nhưng thuộc tenant khác phải bị loại. Tương tự, listing PRIVATE không được lộ chỉ vì nằm trong vùng.

Trusted predicates nên được tạo từ thông tin xác thực:

~~~javascript
{
  tenantId: requestAuth.tenantId,
  status: "PUBLISHED",
  verified: true,
  location: { $near: { ... } }
}
~~~

Mã chỉ minh họa nguồn trusted trong service; không lấy tenantId từ arbitrary client query khi tenant isolation là yêu cầu bảo mật.

### 18.4. Những field dễ bị stale

- `openNow`.
- `availableRooms`.
- `inventoryCount`.
- `estimatedDeliveryTime`.
- `rating` hoặc review count khi ingest chậm.

Nếu dùng denormalized field cho search, cần cơ chế cập nhật và chính sách nhất quán. Đừng dùng giá trị cached làm xác nhận booking cuối.

### 18.5. Vùng giao hàng không tự bảo đảm đủ công suất

`$geoIntersects` cho biết điểm khách nằm trong vùng đã khai báo, nhưng tài xế có thể không sẵn, cửa hàng có thể đóng hoặc đang quá tải. Quyết định final phải dựa trên business rules còn hiệu lực.

### 18.6. Quy tắc ngày giờ

Có chỗ mở cửa theo giờ địa phương, lịch booking theo đêm, cutoff theo timezone. Nếu kết hợp thời gian với location, lưu timezone của entity một cách rõ ràng, chuyển các mốc thời gian đúng và test daylight-saving cho vùng có DST.

---

## 19. Quyền riêng tư và dữ liệu vị trí

### 19.1. Vị trí là dữ liệu nhạy cảm trong nhiều ngữ cảnh

Tọa độ chính xác có thể tiết lộ nhà riêng, nơi làm việc hoặc hành trình. Chỉ lưu độ chính xác cần thiết, giới hạn quyền đọc và áp dụng chính sách retention.

### 19.2. Không trả full document bừa bãi

Query có thể có projection:

~~~javascript
db.listings.find(
  { tenantId: "tenant-a", status: "PUBLISHED" },
  {
    title: 1,
    pricePerNight: 1,
    location: 1
  }
);
~~~

Nhưng với listings không được công khai vị trí chính xác, projection cần có cơ chế làm mờ hoặc chỉ trả vùng xấp xỉ theo chính sách. Không cho client tự yêu cầu field ownerPhone hoặc privateNotes.

### 19.3. Log request coordinates có giới hạn

Không log đầy đủ vị trí của mọi người dùng trong thời gian dài mà không có mục đích/chính sách phù hợp. Có thể làm tròn, băm theo ô lưới hoặc redaction trong monitoring, tùy nhu cầu và quy định.

### 19.4. Không dùng Polygon như security geofence duy nhất

Nếu một quy tắc bảo mật phụ thuộc việc người dùng thật sự đang ở trong khu vực, tọa độ do client tự báo có thể bị giả. GeoJSON query chỉ đánh giá dữ liệu được cung cấp, không chứng minh nguồn vị trí là đáng tin.

---

## 20. Java Sync Driver: kết hợp near với điều kiện nghiệp vụ

### 20.1. Tư duy dùng Filters API

MongoDB Java Sync Driver có các builders như `Filters.near`, `Filters.geoWithin` và `Aggregates.geoNear` theo API/version. Có thể dùng `Document` để minh họa query BSON trực tiếp khi muốn thấy hình dạng MongoDB rõ ràng.

### 20.2. Ví dụ dùng Document

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class GeoBusinessFindExample {

    public static void search(MongoClient client) {
        MongoDatabase database =
            client.getDatabase("geo_business_lab");

        MongoCollection<Document> listings =
            database.getCollection("listings");

        Document point = new Document(
            "type", "Point"
        ).append(
            "coordinates",
            List.of(106.70098, 10.77689)
        );

        Document near = new Document(
            "$near",
            new Document("$geometry", point)
                .append("$maxDistance", 3000)
        );

        Document filter = new Document(
            "tenantId", "tenant-a"
        )
            .append("status", "PUBLISHED")
            .append("verified", true)
            .append(
                "capacity",
                new Document("$gte", 2)
            )
            .append(
                "pricePerNight",
                new Document("$lte", 1200000L)
            )
            .append("amenities", "wifi")
            .append(
                "location",
                near
            );

        listings.find(filter)
            .projection(
                new Document("title", 1)
                    .append("pricePerNight", 1)
                    .append("capacity", 1)
                    .append("location", 1)
            )
            .limit(20)
            .forEach(System.out::println);
    }
}
~~~

### 20.3. Điểm quan trọng

- `coordinates` là `[longitude,latitude]`.
- `$maxDistance` của GeoJSON near được tính bằng mét.
- Filter tenant/status/verified/price/capacity/wifi nằm **cùng một query** với vị trí.
- `tenantId` trong code ví dụ là literal; trong thực tế lấy từ authenticated context.
- Projection giảm payload.
- Cần 2dsphere index.
- Java long `1200000L` tương ứng số nguyên 64-bit theo codec mặc định phù hợp.

### 20.4. Không tạo MongoClient trên mỗi query

Trong production, `MongoClient` thường được quản lý lifecycle dài hạn bởi application/dependency injection và dùng connection pooling. Không tạo/đóng client cho mỗi request bản đồ.

---

## 21. Java Sync Driver: aggregation có distance field

### 21.1. Dùng `Document` để biểu diễn pipeline

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class GeoBusinessAggregationExample {

    public static void run(MongoClient client) {
        MongoDatabase db =
            client.getDatabase("geo_business_lab");

        MongoCollection<Document> listings =
            db.getCollection("listings");

        Document point = new Document(
            "type", "Point"
        ).append(
            "coordinates",
            List.of(106.70098, 10.77689)
        );

        Document businessFilters = new Document(
            "tenantId", "tenant-a"
        )
            .append("status", "PUBLISHED")
            .append("verified", true)
            .append(
                "capacity",
                new Document("$gte", 2)
            )
            .append(
                "pricePerNight",
                new Document("$lte", 1200000L)
            );

        Document geoNear = new Document(
            "$geoNear",
            new Document("near", point)
                .append("key", "location")
                .append(
                    "distanceField",
                    "distanceMeters"
                )
                .append("maxDistance", 5000)
                .append("spherical", true)
                .append("query", businessFilters)
        );

        Document project = new Document(
            "$project",
            new Document("title", 1)
                .append("pricePerNight", 1)
                .append("capacity", 1)
                .append("distanceMeters", 1)
        );

        listings.aggregate(
            List.of(
                geoNear,
                project,
                new Document("$limit", 20)
            )
        ).forEach(System.out::println);
    }
}
~~~

### 21.2. Vì sao pipeline bắt đầu bằng `$geoNear`?

MongoDB yêu cầu `$geoNear` ở vị trí đầu pipeline trong trường hợp thông thường. Đưa filter vào `query`, không đặt `$match` trước `$geoNear`.

### 21.3. Nếu có nhiều điều kiện phức tạp?

Có thể dùng builder classes để tránh lắp ghép raw BSON ở những nơi nhiều filters, hoặc tách:

- Trusted filters.
- Validated geospatial input.
- Aggregation stage.
- Post-geospatial joins/ranking.
- Response projection.

Điều quan trọng là **không trộn input chưa xác thực của user vào một BSON query tùy ý**.

### 21.4. Không gọi external routing API cho hàng nghìn candidates

Nếu muốn tính ETA cho từng listing, nên lấy top N ứng viên địa lý và business trước, sau đó tính route/travel time cho một số lượng được kiểm soát. Nhưng phải chú ý việc chọn top N theo khoảng cách thẳng có thể loại listing có travel time tốt hơn do mạng lưới đường. Đây là trade-off hiệu năng/chất lượng tìm kiếm cần kiểm thử.

---

## 22. Trang bị khả năng tìm kiếm nhiều tiêu chí trong API

### 22.1. API input minh họa

~~~json
{
  "center": {
    "longitude": 106.70098,
    "latitude": 10.77689
  },
  "radiusMeters": 3000,
  "maxPrice": 1200000,
  "guests": 2,
  "requiredAmenities": ["wifi"],
  "sort": "DISTANCE_ASC",
  "pageSize": 20
}
~~~

### 22.2. Những gì server phải tự quyết định

- `tenantId` từ identity/authorization, không tin input tự khai.
- Listing visibility theo vai trò user.
- Chặn radius/pageSize vượt giới hạn sản phẩm.
- Xác thực giá, số khách và danh sách tiện nghi được hỗ trợ.
- Chuyển coordinates đúng thứ tự.
- Chính sách location precision và dữ liệu được phép trả.
- Timezone và khoảng ngày khi có booking.
- Default sort/ranking.

### 22.3. Query builder không nên biến thành JSON passthrough

Không để client gửi raw MongoDB query:

~~~json
{
  "$or": [
    {"status": "PUBLISHED"},
    {"tenantId": {"$ne": "tenant-a"}}
  ]
}
~~~

rồi đưa trực tiếp vào `find()`. Thay vào đó parse một whitelist input, validate và tạo query BSON từ những trường được phép.

### 22.4. Response nên nhất quán về đơn vị

Ví dụ:

~~~json
{
  "id": "L-101",
  "title": "Căn hộ gần trung tâm",
  "distanceMeters": 420,
  "pricePerNight": 850000,
  "currency": "VND",
  "capacity": 2
}
~~~

Khoảng cách là số minh họa cho response format, không phải kết quả đã chạy query. Không tự thêm thời gian di chuyển mà không dùng routing service.

---

## 23. Bài toán business khác: cửa hàng còn hàng trong bán kính

### 23.1. Document stores

~~~javascript
{
  _id: "STORE-101",
  tenantId: "tenant-a",
  active: true,
  storeType: "PICKUP_POINT",
  location: {
    type: "Point",
    coordinates: [106.701, 10.778]
  },
  stockBySku: {
    SKU101: 12,
    SKU102: 0
  }
}
~~~

### 23.2. Query kết hợp

~~~javascript
db.stores.find({
  tenantId: "tenant-a",
  active: true,
  storeType: "PICKUP_POINT",
  "stockBySku.SKU101": { $gte: 2 },
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 2000
    }
  }
});
~~~

### 23.3. Không nên nhét vô hạn SKU fields vào store

Nếu cửa hàng có hàng trăm nghìn SKU, dynamic fields như `stockBySku.SKU101` có thể làm document lớn và index phức tạp. Cân nhắc collection `storeInventory` riêng hoặc một search/materialized view tối ưu cho SKU + geospatial filter.

### 23.4. Indexing chiến lược

Nếu nhu cầu thường là “SKU cụ thể, còn hàng, gần user”, có thể tạo một **inventory availability search collection** với một document cho mỗi store-SKU, lưu hoặc tham chiếu store location, rồi index theo SKU/stock + location.

Đánh đổi: duplicated location cần cập nhật khi store chuyển vị trí. Đây là bài toán denormalization và consistency.

### 23.5. Xác nhận cuối

Stock 2 tại thời điểm tìm kiếm không bảo đảm vẫn là 2 khi khách đặt. Order/reservation phải dùng conditional update như `available:{$gte:quantity}` trong một transaction hoặc cơ chế tương đương.

---

## 24. Bài toán business khác: tìm tài xế hoặc điểm dịch vụ

### 24.1. Thêm trạng thái

Một driver có location gần khách nhưng `status:"OFFLINE"` hoặc đã nhận chuyến thì không hợp lệ.

~~~javascript
db.drivers.find({
  tenantId: "tenant-a",
  status: "AVAILABLE",
  vehicleType: "BIKE",
  capacityKg: { $gte: 5 },
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  }
}).limit(20);
~~~

### 24.2. Vị trí có độ mới

Nếu vị trí được gửi cách đây 30 phút, driver có thể không còn ở tọa độ lưu. Có thể yêu cầu:

~~~javascript
{
  lastLocationAt: {
    $gte: ISODate("2026-11-14T04:00:00Z")
  }
}
~~~

Mốc thời gian cần tính dựa trên hiện tại và SLA thật; ở đây là ví dụ. Đừng cố định ngày giờ minh họa trong ứng dụng production.

### 24.3. Tính trạng thái ở thời điểm gán

Hai đơn có thể đồng thời nhìn thấy cùng một driver AVAILABLE. Phải dùng atomic conditional update hoặc transaction để chuyển driver từ AVAILABLE sang ASSIGNED cho đúng một request.

### 24.4. Vị trí cập nhật rất thường xuyên

Nếu tài xế cập nhật location mỗi giây, index geospatial phải được sửa liên tục. Tùy scale có thể cần chia:

- Vị trí real-time với TTL.
- Dữ liệu profile lâu dài.
- Work assignment/availability state.
- Geospatial candidate search.
- Final assignment transaction.

Không xem một collection có mọi field là thiết kế bắt buộc.

---

## 25. Đánh giá hiệu năng bằng mô hình hai giai đoạn

Một mô hình dễ suy nghĩ:

~~~text
Giai đoạn 1:
  Tìm ứng viên phù hợp về địa lý và những business filters
  có thể push down vào query/index.

Giai đoạn 2:
  Xử lý những điều kiện tốn kém (lịch booking, rating ranking,
  routing ETA, dynamic inventory) trên tập ứng viên đã thu hẹp.
~~~

### 25.1. Lợi ích

- Giảm số documents phải join.
- Giảm số calls đến dịch vụ ngoài.
- Giảm payload.
- Dễ quan sát bottleneck riêng.

### 25.2. Rủi ro tính đúng

Nếu cắt candidates quá sớm, có thể bỏ các kết quả business hợp lệ ở xa hơn. Ví dụ lấy 20 gần nhất rồi check availability và còn 2 căn; không đồng nghĩa chỉ có 2 căn khả dụng trong bán kính.

### 25.3. Cách cân bằng

- Chọn radius theo nhu cầu.
- Query với business filters càng sớm càng tốt.
- Over-fetch candidates vừa đủ, sau đó fetch thêm nếu thiếu.
- Có giới hạn latency/cost và trả thông tin paging rõ.
- Khi cần top K chính xác, duyệt đủ candidate space hoặc dùng data model/index phù hợp.
- Khi dùng approximate candidate selection, API phải nêu rõ đây là kết quả gợi ý/xấp xỉ, không tuyên bố exhaustiveness.

---

## 26. Những lỗi thường gặp

**“GeoJSON dùng [lat,lng].”** Sai. Dùng `[longitude,latitude]`.

**“Khoảng cách `$maxDistance` là km.”** Sai với GeoJSON Point/2dsphere trong ví dụ; dùng mét.

**“`$centerSphere` nhận mét.”** Sai. Bán kính của `$centerSphere` được truyền bằng radian.

**“Chỉ có `$near` là đủ cho search.”** Sai. Cần tenant, visibility, price, capacity, amenities và các quy tắc khác.

**“`$geoWithin` tự sort gần trước.”** Sai. Nó kiểm tra nằm trong vùng, không tự sort theo distance.

**“Stored Polygon chứa khách thì dùng `$geoWithin` với query Point.”** Không đúng cách biểu đạt thường dùng; với stored area Polygon và query Point, dùng `$geoIntersects`.

**“`$geoNear` có thể đặt sau `$match` đầu pipeline.”** Không đúng yêu cầu vị trí stage tiêu chuẩn.

**“`$geoNear.query` có thể chứa một `$near` thứ hai.”** Không nên; `near` của stage đã định nghĩa proximity.

**“Có geo index thì mọi business filter tự tối ưu.”** Sai. Cần xem compound indexes, selectivity và explain.

**“Đưa mọi field vào compound geo index sẽ nhanh nhất.”** Sai. Index lớn và sort/inequality/geospatial trade-offs phải đo.

**“Partial index cho PUBLISHED vẫn trả DRAFT.”** Không; partial index chỉ bao những documents thỏa filter của index.

**“2dsphere compound index luôn chứa documents thiếu location.”** Sai; địa lý sparse behavior rất quan trọng.

**“20 gần nhất rồi lọc booking là 20 listing khả dụng gần nhất.”** Sai. Filtering sau limit có thể làm mất kết quả hợp lệ.

**“Một listing được search trả về tức là khóa phòng đã được giữ.”** Sai. Phải xác nhận availability nguyên tử khi booking.

**“Tính giờ nhận/trả phòng bằng UTC midnight cho mọi listing.”** Sai. Cần timezone và quy tắc local date.

**“Đường chim bay 1 km = lái xe 1 km.”** Sai. Routing distance/ETA khác geospatial distance.

**“Một điểm trong vùng giao hàng nghĩa là chắc giao được.”** Sai. Còn business conditions, capacity và thời gian.

**“TenantId do client gửi là đủ bảo mật.”** Sai. Tenant từ authenticated context; validate field-level visibility.

**“Location precision có thể trả cho mọi user.”** Không; cần policy privacy.

**“Deep pagination với skip không có chi phí.”** Sai. Skip lớn có thể khiến planner thực hiện nhiều work.

**“Một query location lúc 10:00 luôn đúng khi confirm lúc 10:05.”** Sai. Dữ liệu location, stock, booking và availability có thể đổi.

---

## 27. Quy trình thiết kế truy vấn kết hợp địa lý và nghiệp vụ

### Bước 1 — Viết yêu cầu thành các predicate rõ ràng

Ví dụ:

~~~text
Trong 3 km quanh địa điểm khách
AND thuộc tenant hiện tại
AND trạng thái PUBLISHED
AND verified = true
AND giá <= 1.200.000
AND capacity >= 2
AND amenities chứa Wi-Fi
AND không có booking overlap
~~~

### Bước 2 — Phân loại dữ liệu

- Location Point/Polygon.
- Business fields trong cùng collection.
- Dynamic fields/related collections.
- Quyền và policy.
- Thời gian và timezone.
- Eventual/strong consistency requirements.

### Bước 3 — Chọn toán tử địa lý

| Câu hỏi | Toán tử |
|---|---|
| Gần một Point, tự sắp theo khoảng cách | `$near` |
| Gần một Point và cần distance field/pipeline | `$geoNear` |
| Stored Point nằm trong Polygon hoặc vùng tròn | `$geoWithin` |
| Stored Polygon có giao với Point/hình học khách | `$geoIntersects` |

### Bước 4 — Đưa business filters vào cùng query

Tenant, status, price, category, capacity, amenities, verification. Đảm bảo filters từ trusted context khi liên quan authorization.

### Bước 5 — Chọn index candidates

Tạo `2dsphere` index và một số compound/partial indexes theo workload, tránh index inflation.

### Bước 6 — Xác định ranking và pagination

Nearest vs price vs blended ranking; tie-break, radius, page size, dynamic updates.

### Bước 7 — Tối ưu related-data checks

Availability lookup, stock join, delivery zone matching, routing ETA — chỉ làm trên ứng viên hợp lý nhưng không hy sinh completeness không được phép.

### Bước 8 — Bảo vệ thao tác cuối

Booking/stock/driver assignment cần conditional write, unique constraint hoặc transaction. Search là giai đoạn khám phá, không phải lock.

### Bước 9 — Đo với production-like data

Explain, query latency, documents examined, index selection, disk/memory, các bán kính và tenant skew.

### Bước 10 — Kiểm thử trường hợp biên

Tọa độ sai thứ tự, vị trí thiếu, Polygon lỗi, ranh giới, timezone, stale availability, concurrent bookings, chính sách riêng tư và request không được cấp quyền.

---

## 28. Ma trận kiểm thử

| Test | Dữ liệu/đầu vào | Kết quả cần kiểm tra |
|---|---|---|
| T1 | Listing gần nhưng `DRAFT` | Không xuất hiện ở public search |
| T2 | Listing gần nhưng tenant khác | Không xuất hiện |
| T3 | Listing có giá vượt max | Không xuất hiện |
| T4 | Capacity nhỏ hơn guests | Không xuất hiện |
| T5 | Thiếu Wi-Fi | Không xuất hiện khi yêu cầu Wi-Fi |
| T6 | Point ở trong search Polygon | Được chọn nếu các rules khác đúng |
| T7 | Point ở ngoài Polygon | Không được chọn |
| T8 | Stored service area giao Point khách | Vùng giao hàng là ứng viên |
| T9 | Vùng giao inactive | Bị loại dù geometry phù hợp |
| T10 | GeoJSON đảo lat/lng | Validation từ chối hoặc test phát hiện tọa độ sai |
| T11 | Radius 3 km vs 30 km | Query chọn phạm vi phù hợp |
| T12 | Bounding Polygon có ring chưa đóng | Validation thất bại hoặc được xử lý rõ |
| T13 | Listings nhiều vị trí cách gần bằng nhau | Tie-break/pagination ổn định theo policy |
| T14 | Booking overlap chính xác | Listing bị loại khỏi kết quả khả dụng |
| T15 | Checkout = checkin của booking tiếp theo | Không overlap theo khoảng `[start,end)` |
| T16 | Hai khách confirm cùng night | Chỉ một booking giữ lock thành công |
| T17 | Một tenant có hàng triệu listings | Explain/index và query latency vẫn đạt SLO |
| T18 | Booking lookup sau limit | Kiểm tra trường hợp bỏ sót listing hợp lệ |
| T19 | Location field thiếu | Xử lý theo geo index/data quality policy |
| T20 | Người dùng pan map | Token paging cũ được reset đúng |
| T21 | Client cố gửi tenantId khác | Backend không chấp nhận bypass quyền |
| T22 | Listing chứa tọa độ private | API không lộ precision vượt policy |

---

## 29. Bài tập thực hành

### Bài tập 1 — Thiết kế GeoJSON

Tạo ba GeoJSON Point tương ứng ba listing, xác minh thứ tự kinh độ/vĩ độ. Tạo một Polygon hình chữ nhật có vòng ngoài đóng.

### Bài tập 2 — Index 2dsphere

Tạo index trên `listings.location`. Kiểm tra hành vi khi document không có location.

### Bài tập 3 — Tìm listings gần

Dùng `$near` tìm trong 2.000 m quanh một Point, giới hạn 10 kết quả. Giải thích thứ tự và đơn vị của `$maxDistance`.

### Bài tập 4 — Kết hợp trạng thái và tenant

Chỉ trả listings thuộc tenant-a, PUBLISHED, verified và trong bán kính 3 km. Thử thêm listing DRAFT nằm ngay gần origin, xác minh nó bị loại.

### Bài tập 5 — Budget và capacity

Thêm filter `pricePerNight <= 1000000` và `capacity >= 2`. Giải thích vì sao bộ lọc này cần áp dụng trước bước ra quyết định business.

### Bài tập 6 — Tiện nghi

Viết hai query: cần cả wifi và parking bằng `$all`; hoặc chấp nhận wifi hoặc parking bằng `$in`.

### Bài tập 7 — Vùng địa lý

Dùng `$geoWithin` với Polygon do người dùng vẽ. So sánh với query `$near` quanh tâm vùng.

### Bài tập 8 — Radius radian

Dùng `$geoWithin + $centerSphere` với radius 5 km. Chuyển đổi sang radian dựa trên bán kính Trái Đất đã chọn và giải thích tại sao không nhập trực tiếp số 5000.

### Bài tập 9 — Vùng giao hàng

Lưu deliveryZones dưới dạng Polygon và truy vấn `$geoIntersects` với khách hàng Point. Bổ sung active, tenant và minOrderAmount.

### Bài tập 10 — Aggregation distance

Viết `$geoNear` trả `distanceMeters`, price và rating. Chuyển khoảng cách sang km và giới hạn kết quả.

### Bài tập 11 — Pipeline order

Giải thích vì sao đặt `$match` trước `$geoNear` không phù hợp. Đưa filter vào `$geoNear.query`.

### Bài tập 12 — Booking intervals

Viết `bookings.find` kiểm tra interval overlap theo công thức:

~~~text
existing.checkIn < requested.checkOut
AND
existing.checkOut > requested.checkIn
~~~

### Bài tập 13 — GeoNear + booking lookup

Viết pipeline `$geoNear → $lookup → $match → $limit` tìm listing gần không trùng booking. Nêu hiệu năng và false-negative khi limit trước lookup.

### Bài tập 14 — Chống overbooking

Thiết kế unique night locks cho một listing một phòng. Mô phỏng hai booking đồng thời và giải thích vai trò transaction/unique constraint.

### Bài tập 15 — Compound geospatial index

Đề xuất hai index candidates cho queries nhiều tenant, status và near. So sánh bằng explain, không đoán theo số fields.

### Bài tập 16 — Partial index

Chỉ index các PUBLISHED listings. Viết query có thể dùng index đó và query DRAFT không được index bao phủ.

### Bài tập 17 — Ranking

Xây aggregation vừa có `distanceMeters` vừa sắp theo một score minh họa dựa trên distance và rating. Giải thích vì sao sort phải trước limit nếu muốn top K theo score.

### Bài tập 18 — Phân trang

So sánh skip/limit và cursor pagination khi user pan map. Nêu vấn đề floating-point distances, tie-break và dữ liệu động.

### Bài tập 19 — Java Sync Driver

Viết Java `find` kết hợp tenant/status/price/capacity với `$near`. Chuyển sang aggregation có `$geoNear` và distance field.

### Bài tập 20 — Security và data quality

Lập checklist validate tọa độ, radius, Polygon, quyền tenant, private location và timezones. Viết test client cố truy vấn listing thuộc tenant khác.

### Bài tập 21 — Bán hàng còn hàng gần nhất

Đề xuất schema cho store inventory khi một chuỗi có 10.000 cửa hàng và 100.000 SKU. So sánh nhúng stockBySku với tách storeInventory/materialized search view.

### Bài tập 22 — Kết quả gần nhất nhưng không khả dụng

Tạo 25 listings với 20 căn gần nhất đã booking. Chứng minh limit trước availability lookup trả ít kết quả và đề xuất chiến lược không bỏ sót top K hợp lệ.

---

## 30. Câu hỏi ôn tập

1. Vì sao query địa lý thường phải kết hợp business filters?
2. GeoJSON Point lưu tọa độ theo thứ tự nào?
3. GeoJSON Polygon phải đóng vòng tọa độ như thế nào?
4. `2dsphere` index phục vụ loại truy vấn gì?
5. `$near` tự sắp kết quả theo tiêu chí gì?
6. `$maxDistance` dùng đơn vị nào với GeoJSON Point và 2dsphere?
7. `$near` có tự trả field distance không?
8. Khi nào nên dùng `$geoNear`?
9. `$geoNear` phải đứng vị trí nào trong pipeline?
10. `$geoNear.query` dùng để làm gì?
11. Vì sao không nên lồng một `$near` khác trong `$geoNear.query`?
12. `$geoWithin` khác `$near` ở đâu?
13. `$centerSphere` nhận bán kính theo đơn vị gì?
14. Khi stored Polygon là vùng giao hàng, truy vấn khách là Point thường dùng toán tử nào?
15. `$geoIntersects` có tự xác nhận cửa hàng còn giao hàng được không?
16. `$all` và `$in` khác nhau ra sao với amenities?
17. Vì sao tenantId từ client không đủ bảo mật?
18. Compound `2dsphere` index kết hợp business fields mang lại lợi ích gì?
19. Vì sao không thêm mọi business field vào một geo index thật lớn?
20. Partial index theo `status:"PUBLISHED"` có bao phủ DRAFT không?
21. `2dsphere` index xử lý documents thiếu location thế nào?
22. `$geoWithin` có tự sort theo distance không?
23. Vì sao một listing có thể gần nhưng không đủ điều kiện?
24. Vì sao không được limit 20 trước khi kiểm tra bookings nếu muốn 20 căn khả dụng gần nhất?
25. Công thức hai booking intervals overlap là gì?
26. Vì sao dùng khoảng `[start,end)` cho booking?
27. Tại sao ngày local phải được chuyển timezone đúng?
28. Kết quả search còn phòng có phải là lock đặt phòng không?
29. Unique night-lock giúp chống overbooking như thế nào?
30. Nếu listing có nhiều phòng, night-lock một slot phải thay đổi thế nào?
31. Vì sao road distance khác geospatial distance?
32. Khi nào cần routing service?
33. Vì sao deep skip pagination có thể tốn kém?
34. Vì sao cần tie-break khi sort distance?
35. Khi người dùng thay origin, có thể dùng tiếp pagination token cũ không?
36. Các metric explain nào cần đọc?
37. Vì sao benchmark cần dữ liệu theo phân bố thực tế?
38. Location liên tục thay đổi ảnh hưởng index thế nào?
39. Vùng giao hàng bao điểm khách nhưng store đang đóng phải xử lý sao?
40. Làm sao ngăn lộ tọa độ chính xác của listing không công khai?

---

## 31. Tổng kết

Truy vấn địa lý trong MongoDB không chỉ là một phép tính khoảng cách. Trong ứng dụng thực tế, một kết quả chỉ có giá trị khi **cả geometry và điều kiện nghiệp vụ đều phù hợp**.

Các công cụ chính:

- **GeoJSON + `2dsphere`:** biểu diễn và index vị trí/hình học trên bề mặt Trái Đất.
- **`$near` / `$nearSphere`:** tìm địa điểm gần một Point, thường ưu tiên gần trước.
- **`$geoWithin`:** kiểm tra một Point/hình học nằm trong vùng, không tự sắp khoảng cách.
- **`$geoIntersects`:** kiểm tra hình học giao nhau, ví dụ stored delivery Polygon bao phủ điểm khách.
- **`$geoNear`:** aggregation stage đầu pipeline, trả distance field để tiếp tục join/ranking/filter nghiệp vụ.
- **Business predicates:** tenant, visibility, verification, price, capacity, amenities, inventory, time/availability và policy.

Những nguyên tắc vận hành:

1. **Luôn kiểm tra longitude/latitude và đơn vị khoảng cách.**
2. **Không bỏ các điều kiện bảo mật/tenant khi áp dụng geo filter.**
3. **Đưa predicates đơn giản vào query/`$geoNear.query` sớm để thu hẹp ứng viên.**
4. **Chọn compound/partial geo indexes theo workload thực, dùng explain đo thay vì đoán.**
5. **Đừng limit trước điều kiện business tốn kém nếu điều đó gây bỏ sót kết quả hợp lệ.**
6. **Kết quả search không phải cam kết inventory/booking còn sẵn:** lúc xác nhận cần transaction/conditional write/unique constraint.
7. **Khoảng cách địa lý không phải ETA hoặc quãng đường giao thông.**
8. **Thiết kế ranking và phân trang có tie-break rõ ràng, đặc biệt khi dữ liệu động.**
9. **Định nghĩa policy cho Polygon boundaries, timezone và privacy.**
10. **Kiểm thử cả tính đúng nghiệp vụ lẫn hiệu năng khi bán kính/dữ liệu thay đổi.**

Câu hỏi hữu ích nhất khi thiết kế một tính năng “gần tôi” không chỉ là **“chạy `$near` thế nào?”**, mà còn là **“ai được nhìn thấy đối tượng, đối tượng có đáp ứng yêu cầu hiện tại không, và bằng cách nào bảo đảm quyết định cuối không bị sai khi dữ liệu thay đổi?”**

## Tài liệu tham khảo

- [MongoDB Manual — Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/)
- [MongoDB Manual — GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/)
- [MongoDB Manual — 2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/)
- [MongoDB Manual — Geospatial Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/restrictions/)
- [MongoDB Manual — Compound Geospatial Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/create/)
- [MongoDB Manual — $near](https://www.mongodb.com/docs/manual/reference/operator/query/near/)
- [MongoDB Manual — $nearSphere](https://www.mongodb.com/docs/manual/reference/operator/query/nearSphere/)
- [MongoDB Manual — $geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/)
- [MongoDB Manual — $geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/)
- [MongoDB Manual — $centerSphere](https://www.mongodb.com/docs/manual/reference/operator/query/centerSphere/)
- [MongoDB Manual — $geoNear](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/)
- [MongoDB Manual — Query Plans and Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Java Sync Driver — Geospatial Search](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/geo/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
