# Index 2dsphere, index 2d và tiêu chí lựa chọn

MongoDB hỗ trợ **geospatial indexes** để lưu và truy vấn dữ liệu có yếu tố vị trí: tìm cửa hàng gần người dùng, lọc địa điểm nằm trong khu vực giao hàng, tìm các vùng địa lý giao nhau hoặc tra cứu những điểm trên sơ đồ mặt bằng nhà kho. Hai loại index thường được nhắc đến là **`2dsphere`** và **`2d`**.

Mặc dù đều phục vụ bài toán “tọa độ”, hai index có **mô hình hình học khác nhau**:

- **`2dsphere`** dùng cho những phép tính địa lý trên **bề mặt gần hình cầu của Trái Đất**. Đây là lựa chọn phổ biến cho các vị trí theo kinh độ/vĩ độ (longitude/latitude), GeoJSON và ứng dụng bản đồ thực tế.
- **`2d`** dùng cho **tọa độ phẳng** và khoảng cách theo mô hình hình học Euclid. Nó thích hợp cho bản vẽ mặt bằng, lưới trò chơi hoặc dữ liệu legacy biểu diễn điểm bằng cặp tọa độ, khi nghiệp vụ thực sự cần phép đo phẳng.

Sự lựa chọn không chỉ dựa vào cú pháp `createIndex()`. Ta cần xác định **đơn vị đo, hệ tọa độ, kiểu geometry, toán tử truy vấn, kích thước vùng, mức chính xác, mẫu workload, compound index và tính hợp lệ của dữ liệu đầu vào**.

> **Nguyên tắc đầu tiên:** Vị trí thực trên Trái Đất được lưu bằng GeoJSON với cặp `[longitude, latitude]` và thường dùng **`2dsphere`**. Vị trí trên bản đồ phẳng có đơn vị X/Y của riêng ứng dụng và cần khoảng cách Euclid thì cân nhắc **`2d`**. Không đổi hai index cho nhau chỉ vì cả hai đều có chữ “2d”.

## 1. Trước khi chọn index: dữ liệu biểu diễn không gian nào?

Giả sử có hai collection.

Collection `geoPlaces` lưu địa điểm trên Trái Đất:

```javascript
{
  _id: "PLACE-01",
  name: "Điểm dịch vụ A",
  category: "service",
  location: {
    type: "Point",
    coordinates: [106.7000, 10.7760]
  }
}
```

Hai số ở `coordinates` là:

```text
[longitude, latitude]
[kinh độ,   vĩ độ]
```

Đây là một **GeoJSON Point**. Cặp tọa độ ví dụ nằm trong miền longitude/latitude hợp lệ, dùng làm dữ liệu minh họa; nó không phải một địa chỉ cụ thể.

Collection `floorPoints` lưu vị trí trên bản vẽ nhà kho:

```javascript
{
  _id: "SHELF-A01",
  floorId: "F1",
  name: "Kệ A01",
  xy: [125.5, 64.0]
}
```

Ở đây:

```text
x = 125.5 đơn vị mặt bằng
y = 64.0 đơn vị mặt bằng
```

Nếu mỗi đơn vị tương đương một mét, khoảng cách phẳng từ `[100,50]` đến `[125.5,64]` có thể tính bằng Euclid. Nếu đơn vị là pixel hoặc centimet, kết quả có **đơn vị đó**, không tự được MongoDB đổi sang mét.

Hai tài liệu có vẻ cùng là hai số, nhưng ý nghĩa vật lý của chúng khác nhau.

## 2. Bản chất của `2dsphere`

`2dsphere` là loại geospatial index phù hợp với mô hình hình học địa lý **Earth-like sphere**. Nó hỗ trợ dữ liệu GeoJSON và những biểu diễn legacy coordinate pairs được MongoDB cho phép.

Ví dụ tạo index:

```javascript
db.geoPlaces.createIndex({
  location: "2dsphere"
});
```

Sau khi có index, các truy vấn có thể dùng những toán tử địa lý như:

- `$near` / `$nearSphere` theo hình học được hỗ trợ;
- `$geoWithin` để kiểm tra vị trí nằm trong vùng;
- `$geoIntersects` để kiểm tra geometry giao nhau;
- Aggregation `$geoNear` để tìm lân cận kèm khoảng cách.

Tùy phép toán, MongoDB có thể dùng index để giảm vùng ứng viên, sau đó thực hiện kiểm tra hình học nhằm bảo đảm kết quả.

### 2.1. Vì sao không dùng khoảng cách Euclid trực tiếp cho kinh độ/vĩ độ?

Một độ kinh độ **không có cùng độ dài mặt đất ở mọi vĩ độ**. Gần xích đạo và gần cực, chênh lệch một độ longitude tương ứng những quãng đường khác nhau. Trái Đất cũng có đường cong bề mặt.

Nếu dùng phép tính phẳng đơn giản trên hai số longitude/latitude rồi coi kết quả là mét, ứng dụng có thể:

- Ước lượng sai khoảng cách;
- Xếp sai thứ tự các địa điểm lân cận;
- Sai vùng bán kính, đặc biệt ở vĩ độ cao;
- Sai với dữ liệu băng qua kinh tuyến ±180°;
- Khó mở rộng logic sang polygon hoặc đường đi.

`2dsphere` xử lý ngữ nghĩa địa lý trên mô hình hình cầu phù hợp hơn cho bài toán bản đồ.

### 2.2. 2dsphere không phải công cụ chỉ đường

Một phép tìm gần theo `2dsphere` thường dựa vào **khoảng cách địa lý ngắn nhất theo mô hình hình cầu**. Nó không biết:

- Đường một chiều;
- Cầu, phà hoặc khu vực cấm đi;
- Tắc đường;
- Độ cao, cầu thang hoặc thang máy;
- Thời gian di chuyển bằng xe máy, ô tô hay đi bộ.

Do đó, “địa điểm gần nhất về địa lý” không nhất thiết là “địa điểm có thời gian giao hàng nhanh nhất”. Nếu cần routing theo đường thực, dùng geospatial query để tạo **tập ứng viên**, rồi phối hợp một routing engine/dịch vụ bản đồ.

## 3. Bản chất của `2d`

`2d` là index dùng cho dữ liệu **tọa độ phẳng** theo các biểu diễn legacy coordinate pairs.

Ví dụ:

```javascript
db.floorPoints.createIndex({
  xy: "2d"
});
```

Tọa độ có thể được lưu như:

```javascript
{
  _id: "ROBOT-01",
  xy: [20.0, 45.0]
}
```

Các phép truy vấn phẳng thường gặp gồm:

- `$near` trên cặp X/Y để tìm các điểm gần nhất;
- `$geoWithin` kết hợp `$box`, `$center` hoặc `$polygon` theo biểu diễn legacy phù hợp;
- Một số biến thể geospatial khác có điều kiện hỗ trợ riêng.

Một hệ thống dùng sơ đồ sàn kho, vị trí robot, sân chơi 2D hoặc layout kỹ thuật có thể cần tính khoảng cách theo **mặt phẳng**. Nếu dữ liệu là X/Y thuần túy, ta không nên gắn chúng vào GeoJSON longitude/latitude giả tạo.

### 3.1. `2d` không phải 2dsphere phiên bản cũ tương đương

Cùng một điểm `[106.7,10.776]` có thể xuất hiện ở cả hai định dạng legacy, nhưng:

- Trong `2d`, các phép tính phẳng có thể coi đó như hai tọa độ X/Y trong hệ tọa độ đã chọn.
- Trong `2dsphere`, khi dùng dữ liệu địa lý phù hợp, ta đang làm việc với vị trí trên Trái Đất.

Vì thế, nếu dữ liệu thực là kinh/vĩ độ, chọn `2d` chỉ vì cấu trúc cũ dùng mảng `[x,y]` có thể gây **sai ngữ nghĩa khoảng cách**.

### 3.2. Miền tọa độ của index 2d

`2d` có các tùy chọn lập index như `min`, `max`, `bits` phục vụ miền tọa độ và độ phân giải không gian. Mặc định miền thường được dùng cho legacy geographic pairs; với tọa độ phẳng vượt miền mặc định, phải khai báo phạm vi thích hợp.

Ví dụ mặt bằng có tọa độ từ 0 đến dưới 500 đơn vị:

```javascript
db.floorPoints.createIndex(
  { xy: "2d" },
  {
    min: 0,
    max: 500
  }
);
```

Khi chọn `min`/`max`:

1. Cần hiểu **miền tọa độ thật** của ứng dụng;
2. Phải đủ chỗ cho tăng trưởng hoặc dịch chuyển mặt bằng;
3. Dữ liệu ngoài miền index có thể gây lỗi khi xây index hoặc ghi;
4. Một số tùy chọn cấu hình ảnh hưởng độ phân giải và chi phí;
5. Không coi chỉnh `bits` là cách tự biến tọa độ sai thành tọa độ đúng.

Không nên tự đưa tọa độ lon/lat vào `2d` với `min/max` tùy ý rồi kỳ vọng truy vấn theo mét giống GeoJSON `2dsphere`.

## 4. So sánh `2dsphere` và `2d`

| Tiêu chí | `2dsphere` | `2d` |
|---|---|---|
| Mô hình | Hình học trên bề mặt gần hình cầu | Hình học mặt phẳng |
| Use case điển hình | Bản đồ Trái Đất, kinh/vĩ độ | Sơ đồ mặt bằng, tọa độ X/Y |
| Dữ liệu nên dùng | GeoJSON Point/LineString/Polygon và kiểu hỗ trợ | Legacy coordinate pairs, hình dạng legacy phù hợp |
| GeoJSON geometry | **Hỗ trợ** | Không phải index cho GeoJSON geometry |
| `$near` | Hỗ trợ truy vấn lân cận địa lý | Hỗ trợ truy vấn lân cận phẳng |
| `$geoWithin` | Hỗ trợ các vùng spherical/GeoJSON phù hợp | Hỗ trợ các vùng planar legacy |
| `$geoIntersects` | **Index hỗ trợ geometry intersection** | Không phải lựa chọn cho intersection GeoJSON |
| `$geoNear` | Hỗ trợ khi có index phù hợp | Hỗ trợ với kiểu near và index phù hợp |
| Đơn vị khoảng cách | Với GeoJSON Point và cú pháp tương ứng thường là **mét** | Theo đơn vị tọa độ phẳng |
| Điểm gần với kinh/vĩ độ | Phù hợp | Không nên dùng thay cho spherical distance |
| Dữ liệu polygon trên bản đồ | Phù hợp | Giới hạn hơn, theo mô hình planar/legacy |
| Compound index | Có quy tắc cho compound 2dsphere | Có các giới hạn về vị trí field geo |
| Chi phí | Phụ thuộc loại geometry/index keys/query | Phụ thuộc miền X/Y và query |
| Nên chọn cho ứng dụng giao hàng thực tế | Thường chọn `2dsphere` | Chỉ khi cố ý dùng tọa độ phẳng nội bộ |

**Không có index nào “nhanh hơn mọi trường hợp”.** Cần so sánh **đúng phép toán**, dữ liệu và số document được xử lý, không chỉ đo một `find()` đơn lẻ trên các schema khác nhau.

## 5. GeoJSON: quy ước cần chính xác

GeoJSON dùng object có `type` và `coordinates` hoặc các field tương ứng với loại geometry.

### 5.1. Point

```javascript
{
  type: "Point",
  coordinates: [106.7000, 10.7760]
}
```

**Thứ tự bắt buộc theo GeoJSON là longitude trước, latitude sau.**

| Thành phần | Ý nghĩa | Miền địa lý thông thường |
|---|---|---|
| `coordinates[0]` | Kinh độ / longitude | −180 đến +180 độ |
| `coordinates[1]` | Vĩ độ / latitude | −90 đến +90 độ |

Sai thường gặp:

```javascript
{
  type: "Point",
  coordinates: [10.7760, 106.7000]
}
```

Ở đây vĩ độ bị đặt thành 106.7°, vượt miền latitude. MongoDB có thể từ chối geometry không hợp lệ khi index/query.

**Không kiểm tra tọa độ bằng cách chỉ đếm mảng có hai số.** Cần xác thực thứ tự và miền hợp lệ.

### 5.2. LineString

Một đường gồm nhiều điểm:

```javascript
{
  type: "LineString",
  coordinates: [
    [106.6900, 10.7700],
    [106.7000, 10.7760],
    [106.7100, 10.7850]
  ]
}
```

LineString biểu diễn **geometry đường**, không phải một tập điểm tùy tiện không có quan hệ. Khi hỏi đường có giao với một vùng không, `$geoIntersects` với 2dsphere có thể hữu ích.

### 5.3. Polygon

Một polygon GeoJSON có mảng các **linear rings**. Ring khép kín: tọa độ đầu và cuối trùng nhau.

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.6800, 10.7600],
      [106.7200, 10.7600],
      [106.7200, 10.8000],
      [106.6800, 10.8000],
      [106.6800, 10.7600]
    ]
  ]
}
```

Mảng lồng:

```text
coordinates
  └── danh sách rings
        └── danh sách [longitude, latitude]
```

Ring ngoài mô tả biên, các rings bổ sung có thể biểu diễn **holes** khi hợp lệ.

### 5.4. Kiểm tra tính hợp lệ của geometry

Trước khi đưa Polygon hoặc MultiPolygon vào collection lớn, cần xác thực:

- Ring được đóng đúng;
- Có đủ điểm phân biệt;
- Không tạo polygon tự cắt không mong muốn;
- Không đảo longitude/latitude;
- Có quy tắc nhất quán về winding và holes;
- Không vô tình dùng độ (degrees) như mét;
- Tránh geometry quá phức tạp không cần thiết;
- Kiểm tra các khu vực qua kinh tuyến ±180° và polygon lớn hơn nửa hình cầu theo quy tắc MongoDB.

Một GeoJSON object có cấu trúc JSON đúng chưa chắc **hình học** hợp lệ hoặc mang ý nghĩa nghiệp vụ đúng.

## 6. Dữ liệu mẫu cho bài toán địa điểm thật

Các lệnh sau dành cho **collection thử nghiệm** `geoPlacesLab`. `drop()` chỉ nên chạy khi chấp nhận xóa toàn bộ dữ liệu của collection thử nghiệm này.

```javascript
use geoIndexLab;

db.geoPlacesLab.drop();

db.geoPlacesLab.insertMany([
  {
    _id: "P01",
    name: "Điểm A",
    category: "service",
    tenantId: "T-01",
    location: {
      type: "Point",
      coordinates: [106.6950, 10.7760]
    }
  },
  {
    _id: "P02",
    name: "Điểm B",
    category: "service",
    tenantId: "T-01",
    location: {
      type: "Point",
      coordinates: [106.7050, 10.7790]
    }
  },
  {
    _id: "P03",
    name: "Điểm C",
    category: "shop",
    tenantId: "T-02",
    location: {
      type: "Point",
      coordinates: [106.7100, 10.7850]
    }
  },
  {
    _id: "P04",
    name: "Điểm D",
    category: "shop",
    tenantId: "T-02",
    location: {
      type: "Point",
      coordinates: [106.6800, 10.7650]
    }
  },
  {
    _id: "P05",
    name: "Chưa có tọa độ",
    category: "service",
    tenantId: "T-03"
  }
]);

db.geoPlacesLab.createIndex({
  location: "2dsphere"
});
```

Đây là tọa độ **minh họa cho truy vấn**, không phải danh sách địa điểm thương mại thực.

Document P05 thiếu `location`. Trường hợp này hữu ích khi bàn về sparse behavior của `2dsphere`.

### 6.1. Xem index đã tạo

```javascript
db.geoPlacesLab.getIndexes();
```

Kết quả có thể hiển thị tên index mặc định kiểu:

```text
location_2dsphere
```

Tên index phụ thuộc cách tạo và các tùy chọn. Dùng `getIndexes()` để xác nhận **thực tế**, không chỉ giả định lệnh trước đã thành công.

## 7. Tìm địa điểm gần nhất bằng `$near`

Với index `2dsphere`, dùng GeoJSON Point để làm tâm:

```javascript
db.geoPlacesLab.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $maxDistance: 3000
    }
  }
}).limit(10);
```

Ý nghĩa:

- Tâm truy vấn là GeoJSON Point `[106.7000,10.7760]`.
- `$maxDistance: 3000` là **3.000 mét** theo ngữ nghĩa `$near` với GeoJSON.
- Kết quả `$near` được **sắp theo khoảng cách gần trước**.
- `.limit(10)` chỉ lấy tối đa 10 điểm phù hợp.
- MongoDB cần geospatial index phù hợp cho loại near query này.

### 7.1. `$minDistance`

Có thể tìm các điểm cách tâm từ 1.000 đến 5.000 mét:

```javascript
db.geoPlacesLab.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $minDistance: 1000,
      $maxDistance: 5000
    }
  }
});
```

Đây là vùng dạng vòng/annulus về **khoảng cách địa lý** từ tâm, không phải một rectangle trên bản đồ.

### 7.2. `$near` không trả luôn trường distance

Một query `$near` sắp xếp kết quả theo khoảng cách, nhưng response document không tự thêm một field `distanceMeters` chỉ vì có `$near`.

Nếu ứng dụng cần **khoảng cách cho mỗi document**, dùng aggregation `$geoNear` hoặc tính ở tầng phù hợp.

### 7.3. Khi nào không dùng `$near`?

Nếu yêu cầu chỉ là “tất cả điểm nằm trong quận/vùng polygon” mà **không cần sort theo khoảng cách**, `$geoWithin` thường sát ngữ nghĩa hơn.

Đừng dùng `$near` cho một báo cáo lấy toàn bộ hàng trăm nghìn điểm rồi `.sort()` lại theo tên; quá trình near sorting có thể tạo chi phí không cần thiết.

## 8. Tìm điểm nằm trong Polygon bằng `$geoWithin`

Giả sử muốn lấy các vị trí nằm trong một vùng chữ nhật được biểu diễn bằng GeoJSON Polygon:

```javascript
const serviceArea = {
  type: "Polygon",
  coordinates: [
    [
      [106.6800, 10.7600],
      [106.7200, 10.7600],
      [106.7200, 10.8000],
      [106.6800, 10.8000],
      [106.6800, 10.7600]
    ]
  ]
};

db.geoPlacesLab.find({
  location: {
    $geoWithin: {
      $geometry: serviceArea
    }
  }
});
```

Ý nghĩa: tìm location nằm **bên trong vùng geometry**.

### 8.1. `$geoWithin` và `$near` khác nhau

| Câu hỏi | Toán tử |
|---|---|
| “Đâu là 10 điểm gần tâm nhất trong 3 km?” | `$near` |
| “Những điểm nào nằm trong polygon giao hàng?” | `$geoWithin` |
| “Đường hoặc vùng nào có giao với vùng tìm kiếm?” | `$geoIntersects` |
| “Tìm gần và trả khoảng cách tính được?” | `$geoNear` |

`$geoWithin` **không tự sắp theo khoảng cách**. Nếu cần thứ tự ổn định cho phân trang, thêm sort thích hợp và cân nhắc index cũng như chi phí.

### 8.2. Index có phải luôn bắt buộc?

Một số truy vấn `$geoWithin` có thể thực thi mà không có geospatial index, nhưng với dataset lớn việc quét/kiểm tra nhiều geometry có thể rất tốn kém. `2dsphere` thường giúp hiệu quả hơn khi dữ liệu thực là GeoJSON Trái Đất.

Đừng suy từ “lệnh chạy được” thành “planner đã dùng index”. Luôn kiểm tra `explain()` trên workload thật.

## 9. `$geoIntersects`: khi geometry có giao nhau

Một nhu cầu khác:

> “Những tuyến vận chuyển nào có ít nhất một phần giao với vùng đang bảo trì?”

Collection `routes` có LineString:

```javascript
db.routesLab.insertMany([
  {
    _id: "R1",
    name: "Tuyến A",
    path: {
      type: "LineString",
      coordinates: [
        [106.6900, 10.7700],
        [106.7100, 10.7900]
      ]
    }
  },
  {
    _id: "R2",
    name: "Tuyến B",
    path: {
      type: "LineString",
      coordinates: [
        [106.7300, 10.8100],
        [106.7400, 10.8200]
      ]
    }
  }
]);

db.routesLab.createIndex({
  path: "2dsphere"
});
```

Query:

```javascript
const affectedArea = {
  type: "Polygon",
  coordinates: [
    [
      [106.6800, 10.7600],
      [106.7200, 10.7600],
      [106.7200, 10.8000],
      [106.6800, 10.8000],
      [106.6800, 10.7600]
    ]
  ]
};

db.routesLab.find({
  path: {
    $geoIntersects: {
      $geometry: affectedArea
    }
  }
});
```

Khác biệt:

- `$geoWithin`: geometry được lưu **nằm trong** geometry truy vấn.
- `$geoIntersects`: geometry được lưu **có giao nhau** với geometry truy vấn, dù không nằm trọn trong đó.

Ví dụ một tuyến đường cắt ngang polygon thường **giao nhau** nhưng không **nằm trọn trong** polygon.

`2dsphere` là index phù hợp cho bài toán intersection GeoJSON. Không chuyển nguyên query này sang một `2d` index phẳng và kỳ vọng tất cả ngữ nghĩa polygon/đường địa lý giữ nguyên.

## 10. `$geoNear` aggregation: lấy cả khoảng cách

Khi cần danh sách “gần nhất” kèm số mét để trả API, `$geoNear` là lựa chọn tự nhiên.

```javascript
db.geoPlacesLab.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 5000,
      query: {
        category: "service"
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      category: 1,
      distanceMeters: 1
    }
  },
  { $limit: 10 }
]);
```

Ý nghĩa:

- `near`: tâm tìm kiếm.
- `key`: trường geospatial index dùng để tính khoảng cách.
- `distanceField`: trường kết quả chứa khoảng cách theo ngữ nghĩa của index/cú pháp.
- `spherical: true`: dùng tính toán spherical theo cấu hình phù hợp.
- `maxDistance`: giới hạn bán kính.
- `query`: filter thêm thuộc tính.
- `$project`: chỉ trả field cần thiết.
- `$limit`: giới hạn số kết quả.

Với GeoJSON Point và 2dsphere, distance thường biểu diễn **mét**.

### 10.1. `$geoNear` phải ở vị trí đầu pipeline

Trong aggregation pipeline thông thường, **`$geoNear` phải là stage đầu tiên**. Không viết:

```javascript
db.geoPlacesLab.aggregate([
  { $match: { category: "service" } },
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      distanceField: "distanceMeters",
      spherical: true
    }
  }
]);
```

thay vì đó, đưa filter phù hợp vào `query` của `$geoNear`, như ví dụ đúng ở trên.

### 10.2. Vì sao khai báo `key`?

Nếu collection có nhiều geospatial indexes, router/planner cần biết trường nào đại diện vị trí cho `$geoNear`. Chỉ rõ `key` giúp tránh mơ hồ. Nó còn làm ý nghĩa truy vấn rõ ràng khi schema có:

```javascript
pickupLocation
deliveryLocation
warehouseLocation
```

Tính khoảng cách tới điểm nhận hàng và điểm giao hàng là hai bài toán khác nhau.

### 10.3. `$geoNear` không tạo tuyến đường

`distanceMeters` không phải quãng đường xe chạy. Nếu API hiển thị **thời gian đến dự kiến**, nên tính bằng routing/travel-time system. MongoDB trả khoảng cách địa lý, không tự áp dụng bản đồ giao thông.

## 11. Truy vấn phẳng với index `2d`

Bây giờ xây một collection dành cho tọa độ X/Y của mặt bằng.

```javascript
db.floorPointsLab.drop();

db.floorPointsLab.insertMany([
  {
    _id: "S1",
    floorId: "F1",
    xy: [10, 10],
    kind: "shelf"
  },
  {
    _id: "S2",
    floorId: "F1",
    xy: [30, 15],
    kind: "shelf"
  },
  {
    _id: "C1",
    floorId: "F1",
    xy: [80, 70],
    kind: "charger"
  },
  {
    _id: "S3",
    floorId: "F2",
    xy: [25, 25],
    kind: "shelf"
  }
]);

db.floorPointsLab.createIndex(
  { xy: "2d" },
  { min: 0, max: 500 }
);
```

Giả sử đơn vị X/Y là **mét** theo sơ đồ do ứng dụng thiết kế. Khi đó bán kính 30 mang đơn vị mét của hệ tọa độ này. Nếu lưu pixel thì bán kính 30 là pixel, không tự thành 30 mét.

### 11.1. `$near` trong không gian phẳng

```javascript
db.floorPointsLab.find({
  xy: {
    $near: [20, 20],
    $maxDistance: 30
  }
}).limit(10);
```

Query tìm các điểm gần `[20,20]` theo khoảng cách **phẳng** dựa trên tọa độ đã lưu.

### 11.2. `$geoWithin` với `$box`

```javascript
db.floorPointsLab.find({
  xy: {
    $geoWithin: {
      $box: [
        [0, 0],
        [50, 50]
      ]
    }
  }
});
```

`$box` là một vùng hình chữ nhật kiểu legacy: hai góc theo tọa độ phẳng. Hữu ích khi muốn tìm các robot/kệ nằm trong một khung của bản vẽ.

### 11.3. `$geoWithin` với `$center`

```javascript
db.floorPointsLab.find({
  xy: {
    $geoWithin: {
      $center: [
        [20, 20],
        25
      ]
    }
  }
});
```

`$center` dùng **bán kính phẳng** tính bằng cùng đơn vị tọa độ, khác với `$centerSphere` dùng bán kính góc trên bề mặt hình cầu.

### 11.4. Không trộn nhiều mặt bằng vào một hệ X/Y vô thức

Nếu Floor F1 và Floor F2 cùng có điểm `[25,25]`, một truy vấn chỉ theo vị trí có thể nhận dữ liệu cả hai tầng. Tùy nghiệp vụ nên thêm filter:

```javascript
db.floorPointsLab.find({
  floorId: "F1",
  xy: {
    $near: [20, 20],
    $maxDistance: 25
  }
});
```

Để tối ưu, cân nhắc compound index phù hợp với loại geo index, thay vì dựa hoàn toàn vào field `floorId` nếu workload lớn. Index `2d` có quy tắc về vị trí field địa lý trong compound index; phần sau sẽ trình bày.

## 12. Đơn vị đo: lỗi âm thầm rất dễ mắc

Một lỗi nguy hiểm là sử dụng đúng operator nhưng sai đơn vị.

| Cú pháp/trường hợp | Đơn vị thông dụng cần dùng |
|---|---|
| GeoJSON Point + `$near`/`$maxDistance` với `2dsphere` | Mét |
| GeoJSON Point + `$geoNear` trên `2dsphere` | Mét đối với distance được trả theo ngữ nghĩa GeoJSON |
| `$centerSphere` | **Radian** cho bán kính |
| `$center` trên cặp phẳng | Đơn vị tọa độ phẳng |
| `$near` với cặp phẳng và index `2d` | Đơn vị tọa độ phẳng |
| Longitude/latitude trong GeoJSON | **Độ (degrees)** cho vị trí, không phải mét |

### 12.1. `$centerSphere`: bán kính là radian

Ví dụ muốn kiểm tra các điểm nằm trong bán kính khoảng 2 km quanh một tọa độ trên Trái Đất bằng `$centerSphere`.

Công thức:

\[
\text{angularRadius (radian)} = \frac{\text{distanceMeters}}{\text{EarthRadiusMeters}}
\]

Code minh họa:

```javascript
const earthRadiusMeters = 6378100;
const targetRadiusMeters = 2000;
const angularRadius = targetRadiusMeters / earthRadiusMeters;

db.geoPlacesLab.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7000, 10.7760],
        angularRadius
      ]
    }
  }
});
```

**Không truyền `2000` trực tiếp làm bán kính `$centerSphere`** và nghĩ MongoDB hiểu đó là 2.000 mét. Ở đây radius theo radian; với `$near` sử dụng GeoJSON Point, `maxDistance` lại theo mét.

### 12.2. Cùng số 100, ý nghĩa khác hoàn toàn

```javascript
// 2dsphere / GeoJSON: khoảng 100 mét.
$maxDistance: 100

// 2d / X-Y: khoảng 100 đơn vị mặt bằng.
$maxDistance: 100
```

Dữ liệu kiểu `2d` có thể dùng pixel, centimet, mét hoặc tọa độ game; MongoDB không tự biết đơn vị đó.

### 12.3. Sai thứ tự lon/lat

Một vị trí thực `[106.7000,10.7760]` bị đổi thành `[10.7760,106.7000]` có vĩ độ vượt 90°. Nhưng một số cặp tọa độ đảo thứ tự vẫn **nằm trong miền hợp lệ**, khiến lỗi khó phát hiện vì index vẫn được tạo và query vẫn trả kết quả sai vị trí.

Cần schema validation và test bằng những điểm có tọa độ biết trước, không chỉ dựa vào lỗi server.

## 13. Geometry nào nên được lưu?

### 13.1. Điểm đơn lẻ

Cửa hàng, trạm giao hàng, điểm nhận khách, sensor location:

```javascript
{
  type: "Point",
  coordinates: [longitude, latitude]
}
```

Đây là mô hình phổ biến nhất cho các API near-search. Dùng `2dsphere`.

### 13.2. Đường

Tuyến xe, đoạn đường, tuyến vận hành:

```javascript
{
  type: "LineString",
  coordinates: [
    [106.69, 10.77],
    [106.70, 10.78]
  ]
}
```

Với câu hỏi “đường có giao với vùng nào không?”, dùng GeoJSON + `2dsphere` và operator phù hợp.

### 13.3. Vùng

Khu vực giao hàng, vùng phục vụ, địa bàn:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.68, 10.76],
      [106.72, 10.76],
      [106.72, 10.80],
      [106.68, 10.80],
      [106.68, 10.76]
    ]
  ]
}
```

Cần xem rõ quan hệ truy vấn:

- **Point nằm trong service area**;
- **Service area giao với một polygon khác**;
- **Một service area có chứa một điểm**.

Cách đặt **geometry được lưu ở field** và **geometry truyền vào query** có thể ảnh hưởng việc chọn `$geoWithin` hay `$geoIntersects`. Không tự đảo hai geometry mà mặc định kết quả giống nhau.

### 13.4. Mặt bằng X/Y

Robot, pallet, điểm kệ trong một map phẳng:

```javascript
{ xy: [125.5, 64.0] }
```

Nếu nghiệp vụ chỉ dùng khoảng cách Euclid trên mặt phẳng và không cần GeoJSON, `2d` là ứng viên. Nếu muốn biểu diễn đối tượng tuyến/đa giác phức tạp theo mô hình riêng, cần kiểm tra giới hạn các operator legacy hoặc cân nhắc lưu mô hình geometry thích hợp riêng.

## 14. Compound geospatial indexes

Vị trí thường không phải filter duy nhất. Ví dụ một ứng dụng tìm các điểm dịch vụ **cùng tenant** gần người dùng.

### 14.1. Compound `2dsphere`

Có thể tạo compound index kết hợp field thông thường với field địa lý:

```javascript
db.geoPlacesLab.createIndex({
  tenantId: 1,
  location: "2dsphere"
});
```

Một query có cả tenant và vị trí:

```javascript
db.geoPlacesLab.find({
  tenantId: "T-01",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $maxDistance: 5000
    }
  }
});
```

Compound index có thể giúp workload biết tenant trước khi tìm địa điểm gần, nhưng planner còn phụ thuộc selectivity, cấu trúc query và thống kê/index khác.

**Không có quy tắc “cứ thêm tenantId trước địa lý là mọi near query nhanh hơn”.** Nếu phần lớn query không có tenantId, một compound index chỉ tối ưu cho tenant-specific queries có thể không phải index duy nhất phù hợp.

### 14.2. Compound 2dsphere có nhiều field vị trí

Trong những trường hợp được MongoDB hỗ trợ, compound `2dsphere` có thể chứa nhiều field địa lý:

```javascript
db.shipments.createIndex({
  pickupLocation: "2dsphere",
  deliveryLocation: "2dsphere"
});
```

Nhưng thiết kế như vậy làm việc index hóa và lựa chọn trường cho geospatial query phức tạp hơn. Nếu dùng `$geoNear` trên collection có nhiều geospatial indexes/fields, khai báo `key` tường minh.

Không giả định một index với hai field vị trí tự tìm “điểm gần nhất theo cả pickup và delivery” cho mọi query.

### 14.3. Compound `2d` có giới hạn về field geo

Compound `2d` index có quy tắc chặt hơn: trường geospatial `2d` được đặt **đầu** trong key pattern, theo các điều kiện hỗ trợ.

Ví dụ:

```javascript
db.floorPointsLab.createIndex({
  xy: "2d",
  floorId: 1
});
```

Không đổi thứ tự một cách tùy tiện:

```javascript
// Không phải cấu hình compound 2d phù hợp.
db.floorPointsLab.createIndex({
  floorId: 1,
  xy: "2d"
});
```

Sự khác biệt này là một tiêu chí lựa chọn quan trọng nếu ứng dụng có nhiều filter bình thường cần đánh index.

### 14.4. Compound index không thay thế tất cả index khác

Ví dụ:

```javascript
db.geoPlacesLab.find({
  tenantId: "T-01",
  category: "service"
});
```

không có geo predicate. Query này có thể được phục vụ tốt hơn bởi một index thông thường:

```javascript
db.geoPlacesLab.createIndex({
  tenantId: 1,
  category: 1
});
```

Index geospatial được thiết kế để hỗ trợ những truy vấn địa lý, không phải thay thế toàn bộ B-tree indexes phục vụ danh sách, lọc và sắp xếp nghiệp vụ.

## 15. Sparse behavior của 2dsphere

Một điểm dễ bỏ qua: **2dsphere index có hành vi sparse cố hữu**. Document không có location hợp lệ theo quy tắc index, chẳng hạn field geo bị thiếu hoặc null, có thể **không có entry** trong index geospatial.

Ví dụ:

```javascript
{
  _id: "P05",
  name: "Chưa có tọa độ",
  tenantId: "T-03"
}
```

Với:

```javascript
db.geoPlacesLab.createIndex({
  location: "2dsphere"
});
```

document P05 không phải một điểm trên bản đồ, nên không tham gia các truy vấn tìm gần theo location.

### 15.1. Compound 2dsphere và missing location

Ví dụ:

```javascript
db.geoPlacesLab.createIndex({
  tenantId: 1,
  location: "2dsphere"
});
```

Trong compound 2dsphere, sự hiện diện/khả năng index hóa của field địa lý quyết định việc document có index entry địa lý, **không phải chỉ vì tenantId tồn tại**.

Vì vậy, không coi compound index này là index hoàn chỉnh cho mọi document của tenant nếu một số record không có vị trí.

### 15.2. Vì sao điều này quan trọng?

Giả sử business có 1 triệu địa điểm, trong đó 100.000 record chưa được xác minh tọa độ. Một báo cáo “bao nhiêu điểm của tenant đang hoạt động” không nên dựa hoàn toàn vào scan trên index 2dsphere rồi tin rằng nó chứa mọi document.

Sự khác biệt giữa **tất cả record** và **record có vị trí được index** cần được thể hiện rõ trong logic/metrics.

### 15.3. Phân biệt missing với tọa độ sai

Document thiếu location có thể đơn giản không tạo entry geospatial. Document có `location` nhưng GeoJSON sai, longitude/latitude ngoài miền hoặc polygon không hợp lệ có thể làm **thao tác tạo index hoặc ghi dữ liệu lỗi**.

Không dùng sparse behavior như lời hứa MongoDB sẽ “tự bỏ qua tất cả dữ liệu địa lý sai”.

## 16. Dữ liệu không hợp lệ và schema validation

Chất lượng dữ liệu địa lý ảnh hưởng trực tiếp tới kết quả truy vấn.

Ví dụ sai:

```javascript
// Sai thứ tự lat/lon.
{
  location: {
    type: "Point",
    coordinates: [10.776, 106.700]
  }
}

// Thiếu một tọa độ.
{
  location: {
    type: "Point",
    coordinates: [106.700]
  }
}

// String thay vì số.
{
  location: {
    type: "Point",
    coordinates: ["106.700", "10.776"]
  }
}

// Polygon ring không đóng.
{
  area: {
    type: "Polygon",
    coordinates: [
      [
        [106.68, 10.76],
        [106.72, 10.76],
        [106.72, 10.80]
      ]
    ]
  }
}
```

Một schema validator có thể kiểm tra:

- Field bắt buộc/optional;
- `type: "Point"` cho những collection chỉ nhận điểm;
- `coordinates` là array;
- Đúng hai phần tử;
- Phần tử là numeric;
- Longitude/latitude nằm trong miền được phép.

Với polygons, việc kiểm tra **hình học topo** còn phức tạp hơn validation cơ bản của JSON schema; cân nhắc một thư viện GeoJSON/geometry chuyên dụng khi ingest.

### 16.1. Ví dụ validator chỉ cho Point

```javascript
db.createCollection(
  "validatedPlacesLab",
  {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["name", "location"],
        properties: {
          name: {
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
                  bsonType: ["double", "int", "long", "decimal"]
                }
              }
            }
          }
        }
      }
    }
  }
);
```

Validator này là **một lớp kiểm tra dạng dữ liệu**. Nó chưa chứng minh longitude thuộc [−180,180] và latitude thuộc [−90,90], vì hai phần tử cần ràng buộc theo vị trí mảng. Có thể thực hiện validation trong API hoặc bổ sung biểu thức kiểm tra phù hợp.

Không trình bày một validator sơ lược như thể nó đã giải quyết mọi lỗi hình học.

## 17. Các trường hợp biên của geometry

### 17.1. Kinh tuyến ±180° (antimeridian)

Một vùng nằm quanh kinh tuyến 180° có thể chứa những điểm với longitude gần +179° và −179°. Nếu biểu diễn một polygon bằng một dãy cặp số mà không hiểu wrap-around, vùng chọn có thể khác hoàn toàn điều mong muốn.

Với dữ liệu gần antimeridian, cần:

- Thiết kế polygon với đường đi trên hình cầu;
- Xác định đúng interpretation của GeoJSON;
- Kiểm tra kết quả bằng các điểm thử ở hai phía ±180°;
- Tránh dùng bounding box phẳng tùy tiện trên raw longitude;
- Xem yêu cầu winding và geometry lớn theo MongoDB.

### 17.2. Vùng lớn hơn một bán cầu

Với một số polygon lớn, hướng vòng/winding và quy tắc interior/complement trên sphere có thể ảnh hưởng vùng được hiểu là “bên trong”. MongoDB có cơ chế biểu diễn GeoJSON CRS/winding cho những trường hợp đặc biệt theo tài liệu phiên bản.

Không dùng một Polygon lớn vượt nửa Trái Đất mà không kiểm tra semantics; với vùng rất lớn, đôi khi cách mô hình hóa bằng nhiều Polygon nhỏ hoặc MultiPolygon rõ ràng hơn.

### 17.3. Cực và vĩ độ cao

Khoảng cách giữa hai kinh độ giống nhau không có cùng số mét ở mọi vĩ độ. Đây là lý do không nên tính gần đúng `deltaLongitude * hằng số` trên toàn Trái Đất rồi coi kết quả là chuẩn.

### 17.4. Độ cao

GeoJSON Position có thể có phần tử thứ ba trong những ngữ cảnh, nhưng không nên giả định `2dsphere` query tự giải một bài toán khoảng cách 3D theo độ cao như trong không gian Euclid ba chiều.

Nếu hệ thống cần tầng lầu, cao độ drone hoặc độ sâu biển, hãy thiết kế **mô hình 3D/vertical** và thuật toán riêng hoặc filter bổ sung; `2dsphere` chủ yếu phục vụ các phép hình học địa lý 2D trên bề mặt hình cầu.

## 18. Tối ưu query và đọc explain

Một collection có geospatial index vẫn có thể chậm nếu:

- Vùng tìm kiếm quá lớn;
- Gần như mọi document nằm trong polygon;
- Query cần sort/phân trang phức tạp;
- Geometry quá phức tạp;
- Có nhiều điểm/đường trong một document;
- Kết quả quá nhiều;
- Query thiếu filter tenant/category phù hợp;
- Truy vấn chưa dùng index mong muốn;
- Index cục bộ và dữ liệu bị phân tán trên nhiều shard.

### 18.1. Xem executionStats

```javascript
db.geoPlacesLab.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $maxDistance: 5000
    }
  }
}).limit(10).explain("executionStats");
```

Các điểm cần quan sát:

| Thông tin | Ý nghĩa |
|---|---|
| `winningPlan` | Query planner đã chọn đường đọc nào |
| Geospatial index stage | Có dùng index thích hợp không |
| `totalKeysExamined` | Số index entries đã duyệt |
| `totalDocsExamined` | Số document phải kiểm tra |
| `nReturned` | Số kết quả trả ra |
| `executionTimeMillis` | Thời gian thực thi theo ngữ cảnh explain |
| Filter/FETCH | Chi phí kiểm tra document ngoài index |
| Sort/merge | Chi phí sắp/gộp kết quả nếu có |

Tên stage/format khác theo version và query engine; có thể gặp những stage liên quan geo near hoặc index scan. Không viết code monitoring phụ thuộc cứng vào một tên stage duy nhất.

### 18.2. Thử với dữ liệu có phân bố thực

Một benchmark 100 document gần nhau không đại diện collection 30 triệu điểm phân bố toàn quốc.

Nên thử:

1. Tâm query ở khu vực đông điểm;
2. Tâm query ở khu vực thưa điểm;
3. Bán kính nhỏ và lớn;
4. Polygon đơn giản và polygon phức tạp;
5. Query theo tenant/category;
6. Các trường hợp có nhiều document thiếu location;
7. Kết quả chỉ vài record và kết quả hàng trăm nghìn record;
8. Concurrent requests ở peak load.

### 18.3. `$near` vốn có thứ tự khoảng cách

Nếu API cần 10 điểm gần nhất, để `$near`/`$geoNear` thực hiện nearest selection rồi limit thích hợp. Đừng thêm một sort không cần thiết theo thuộc tính khác khiến ưu thế nearest order bị thay đổi.

Nếu cần “10 địa điểm gần nhất có rating trên 4, rồi ưu tiên rating cao hơn”, cần định nghĩa rõ thứ tự ưu tiên: **lọc rating trước khi tìm gần** khác với **lấy 10 gần nhất rồi sort rating**. Hai truy vấn trả tập kết quả khác nhau.

### 18.4. Bán kính và kết quả phải có giới hạn

Một endpoint “tìm địa điểm gần tôi” không nên nhận `$maxDistance` không giới hạn do client tự chọn rồi trả hàng triệu record. Cần:

- Giới hạn radius theo use case;
- Giới hạn số kết quả;
- Xác thực tọa độ;
- Có index phù hợp;
- Pagination/continuation strategy có chủ đích;
- Timeouts, rate limits và monitoring.

## 19. Quy tắc chọn index theo use case

### 19.1. Cửa hàng quanh người dùng

Dữ liệu:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7000, 10.7760]
  }
}
```

Nhu cầu:

```text
Tìm 20 cửa hàng gần người dùng trong bán kính 5 km.
```

Lựa chọn: **`2dsphere`** với GeoJSON, dùng `$near` hoặc `$geoNear`.

### 19.2. Phạm vi giao hàng dạng Polygon

Dữ liệu:

```javascript
{
  serviceArea: {
    type: "Polygon",
    coordinates: [
      [
        [106.68, 10.76],
        [106.72, 10.76],
        [106.72, 10.80],
        [106.68, 10.80],
        [106.68, 10.76]
      ]
    ]
  }
}
```

Nhu cầu:

```text
Tìm những vùng giao hàng giao với khu vực yêu cầu.
```

Lựa chọn: **`2dsphere`**, toán tử `$geoIntersects` thích hợp.

### 19.3. Robot trên sơ đồ nhà kho

Dữ liệu:

```javascript
{
  floorId: "F1",
  xy: [34.5, 72.0]
}
```

Nhu cầu:

```text
Tìm các robot trong vòng 20 mét trên cùng mặt sàn,
dùng hệ tọa độ phẳng của bản vẽ.
```

Lựa chọn: **`2d`** nếu hệ X/Y thật sự là mặt phẳng và đơn vị được thống nhất, cộng filter `floorId`.

### 19.4. Dữ liệu GPS dạng legacy `[lon,lat]`

Dữ liệu cũ:

```javascript
{
  loc: [106.7000, 10.7760]
}
```

Nếu nhu cầu là địa điểm Trái Đất và khoảng cách mét, nên cân nhắc **chuyển sang GeoJSON + `2dsphere`**.

MongoDB 2dsphere cũng có hỗ trợ legacy coordinate pairs trong những trường hợp, nhưng modernizing schema có lợi cho tính rõ ràng và hỗ trợ các geometry mở rộng. Không đổi index chỉ dựa vào tên field mà chưa kiểm tra query behavior.

### 19.5. Bản đồ phẳng nhưng lại cần vùng đa giác phức tạp

Nếu nghiệp vụ cần intersection đa giác phức tạp trên một hệ tọa độ **không phải Trái Đất**, đừng mặc định `2dsphere` sẽ xử lý đúng vì nó hỗ trợ GeoJSON. Có thể cần một engine geometry phẳng chuyên dụng, hoặc chuẩn hóa hệ tọa độ/quy tắc phép toán trước khi lựa chọn MongoDB index.

`2d` hỗ trợ các phép tìm kiếm planar legacy có giới hạn, không phải bộ máy GIS phẳng đầy đủ cho mọi operation.

## 20. Thứ tự lon/lat, hệ tọa độ và phép biến đổi

Ứng dụng có thể nhận tọa độ từ nhiều hệ thống:

- GPS: kinh/vĩ độ WGS84;
- Web map hiển thị dữ liệu qua projection;
- Bản vẽ CAD: tọa độ X/Y có gốc tự chọn;
- Robot: tọa độ local trong phòng;
- Hệ thống cảm biến: đơn vị centimet hoặc milimet.

Không được trộn những giá trị này vào một field `location` rồi lập index, vì cùng mảng hai số nhưng ý nghĩa khác nhau.

### 20.1. Tọa độ bản đồ web không phải lúc nào là longitude/latitude thô

Một web map có thể dùng projection để hiển thị trên màn hình. Nếu API cung cấp X/Y theo một projected coordinate system, phải chuyển về longitude/latitude GeoJSON trước khi dùng `2dsphere` theo WGS84.

Không lấy tọa độ pixel của viewport rồi lưu vào `[longitude, latitude]`.

### 20.2. Metadata hệ tọa độ

Với dữ liệu phẳng:

```javascript
{
  floorId: "F1",
  xy: [34.5, 72.0],
  unit: "meter",
  coordinateSystem: "WAREHOUSE-F1-V2"
}
```

Metadata giúp khi bản vẽ thay đổi hoặc các tầng có gốc tọa độ khác nhau. Nhưng index `2d` chỉ nhìn field vị trí theo schema; nó không tự chuyển giữa các coordinate systems.

Nếu nhiều floor sử dụng các coordinate systems không tương thích, query cần lọc đúng floor/map version.

## 21. 2dsphere và arrays/multikey

Một document có thể chứa nhiều vị trí hoặc một GeoJSON geometry phức tạp, tùy cấu trúc được MongoDB hỗ trợ:

```javascript
{
  _id: "DELIVERY-01",
  stops: [
    {
      type: "Point",
      coordinates: [106.6900, 10.7700]
    },
    {
      type: "Point",
      coordinates: [106.7100, 10.7900]
    }
  ]
}
```

Tạo index:

```javascript
db.deliveries.createIndex({
  stops: "2dsphere"
});
```

Cách index sinh các key và hỗ trợ arrays phụ thuộc loại geometry/index. Một document có nhiều điểm có thể tạo nhiều index entries và gây chi phí lưu trữ/ghi lớn hơn một Point đơn.

### 21.1. Không lưu 100.000 tọa độ GPS vào một document tùy tiện

Nếu một chuyến xe có 100.000 vị trí, đưa toàn bộ points vào một document có thể:

- Tiệm cận giới hạn kích thước BSON;
- Làm document và index cập nhật nhiều;
- Tạo nhiều index entries;
- Gây write amplification;
- Khó truy vấn time windows của từng điểm.

Cân nhắc **mỗi điểm/event là document** (hoặc thiết kế time-series phù hợp), LineString rút gọn cho mục tiêu geometry, hay lưu raw track ngoài collection truy vấn lân cận.

### 21.2. 2dsphere GeoJSON không phải array X/Y tùy ý

Một field:

```javascript
[
  [106.6900, 10.7700],
  [106.7100, 10.7900]
]
```

không nên được coi tự động tương đương một GeoJSON `LineString`. Khi cần biểu diễn đường, hãy dùng object có `type: "LineString"` và `coordinates` đúng cấu trúc.

## 22. Geospatial trong sharded collection

Khi collection được shard, cần phân biệt:

1. **Shard key**: dùng để route document/query giữa các shards.
2. **Geospatial index**: giúp thực thi geo query trong các shards có liên quan.

Một geospatial index không mặc nhiên là shard key phù hợp. MongoDB có những giới hạn riêng về việc **dùng geospatial index làm shard key**: không thể đơn giản chọn `{location:"2dsphere"}` làm shard key như chọn một B-tree index thông thường.

### 22.1. Query chỉ có geo predicate có thể fan-out

Giả sử collection shard theo:

```javascript
{ tenantId: 1 }
```

nhưng có index:

```javascript
{ location: "2dsphere" }
```

Query:

```javascript
db.geoPlaces.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $maxDistance: 3000
    }
  }
});
```

không cung cấp tenantId, nên router có thể phải liên hệ nhiều shard để tìm các điểm gần trên toàn cluster. Mỗi shard có geo index tốt **không tự ngăn fan-out**.

### 22.2. Tenant filter thay đổi routing

```javascript
db.geoPlaces.find({
  tenantId: "T-01",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $maxDistance: 3000
    }
  }
});
```

Khi `tenantId` là shard key và query có đủ điều kiện, mongos có thể target tập shards phù hợp hơn. `2dsphere` lúc này phục vụ **lọc không gian bên trong shard**.

Cần kiểm tra query planner và các giới hạn geo/sharding cụ thể của phiên bản MongoDB đang dùng.

## 23. Java MongoDB Driver: tạo 2dsphere và query gần

Ví dụ Java Sync Driver dùng collection chứa `org.bson.Document`.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

import java.util.Arrays;

MongoDatabase database = mongoClient.getDatabase("geoIndexLab");

MongoCollection<Document> places =
    database.getCollection("geoPlacesLab");

// Tạo index geospatial cho GeoJSON.
places.createIndex(Indexes.geo2dsphere("location"));

Document center = new Document("type", "Point")
    .append("coordinates", Arrays.asList(106.7000, 10.7760));

Document nearSpec = new Document("$geometry", center)
    .append("$maxDistance", 3000);

Document filter = new Document(
    "location",
    new Document("$near", nearSpec)
);

for (Document place : places.find(filter).limit(10)) {
    System.out.println(place.toJson());
}
```

Code trên minh họa cách tạo BSON query để quan sát trực tiếp cấu trúc MongoDB. Trong production cần:

- Quản lý `MongoClient` lifecycle;
- Đọc tọa độ từ input có validation;
- Dùng tên field thống nhất;
- Xử lý exceptions/timeouts;
- Kiểm soát số kết quả;
- Không log tọa độ cá nhân tùy tiện.

### 23.1. Java: `$geoNear` aggregation

```java
import org.bson.Document;

import java.util.Arrays;

Document center = new Document("type", "Point")
    .append("coordinates", Arrays.asList(106.7000, 10.7760));

Document geoNear = new Document(
    "$geoNear",
    new Document("near", center)
        .append("key", "location")
        .append("distanceField", "distanceMeters")
        .append("spherical", true)
        .append("maxDistance", 3000)
        .append("query", new Document("category", "service"))
);

Document limit = new Document("$limit", 10);

for (Document result : places.aggregate(Arrays.asList(
        geoNear,
        limit))) {
    System.out.println(result.toJson());
}
```

Nếu collection có nhiều geospatial fields/indexes, `key` giúp chọn field cần dùng. Kết quả của GeoJSON + 2dsphere được đọc với distance theo mét.

### 23.2. Java: compound geospatial index

```java
places.createIndex(
    Indexes.compoundIndex(
        Indexes.ascending("tenantId"),
        Indexes.geo2dsphere("location")
    )
);
```

Không tạo thêm nhiều index trùng mục đích trên production nếu chưa đo write overhead và query plan.

### 23.3. Java: biểu diễn 2d planar

Đối với mặt bằng phẳng, có thể dùng BSON Document:

```java
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

MongoCollection<Document> floorPoints =
    database.getCollection("floorPointsLab");

// MongoDB field type "2d" được biểu diễn tường minh.
floorPoints.createIndex(
    new Document("xy", "2d"),
    new IndexOptions()
);

Document xyFilter = new Document(
    "xy",
    new Document("$near", Arrays.asList(20.0, 20.0))
        .append("$maxDistance", 30.0)
);

for (Document point : floorPoints.find(xyFilter).limit(10)) {
    System.out.println(point.toJson());
}
```

Để khai báo `min` và `max` cho 2d index, sử dụng options/API/BSON command phù hợp với phiên bản driver. Tránh trộn dữ liệu GeoJSON với index `2d` chỉ vì dùng cùng Java `Document`.

## 24. Migration từ 2d sang 2dsphere

Giả sử hệ thống cũ lưu:

```javascript
{
  _id: 1,
  loc: [106.7000, 10.7760]
}
```

và có index:

```javascript
db.places.createIndex({
  loc: "2d"
});
```

Business bắt đầu yêu cầu khoảng cách theo mét trên Trái Đất, polygon giao hàng và đường đi.

Một migration an toàn nên:

1. **Xác nhận miền và thứ tự tọa độ** cũ thực sự là `[lon,lat]`, không phải `[lat,lon]`.
2. Đếm record có tọa độ null/missing/không hợp lệ.
3. Tạo field mới `location` dưới dạng GeoJSON Point.
4. Điền dữ liệu theo batch với điều kiện bảo vệ.
5. Đồng bộ write path mới để ghi `location` đúng.
6. Tạo `2dsphere` index trên field mới.
7. Chạy query song song trên staging, kiểm tra khoảng cách/targeting.
8. Chuyển read path theo feature flag hoặc rollout có quan sát.
9. Sau khi ổn định, cân nhắc bỏ index/field legacy khi không còn consumer dùng.

### 24.1. Không chỉ drop 2d rồi create 2dsphere trên cùng field

Nếu data cũ có cặp X/Y không thực sự là kinh/vĩ độ, đổi index sẽ làm **thay đổi ý nghĩa phép toán** và có thể gây lỗi dữ liệu.

Nếu data đúng là lon/lat legacy pairs, MongoDB có thể hỗ trợ tạo 2dsphere index trên biểu diễn legacy phù hợp, nhưng ứng dụng nên cân nhắc chuyển sang **GeoJSON chuẩn** để tránh mơ hồ và hỗ trợ Point/Line/Polygon rõ ràng.

### 24.2. Backfill dữ liệu theo batch

Ý tưởng dùng aggregation update pipeline trên collection thử nghiệm:

```javascript
db.places.updateMany(
  {
    loc: { $type: "array" },
    location: { $exists: false }
  },
  [
    {
      $set: {
        location: {
          type: "Point",
          coordinates: "$loc"
        }
      }
    }
  ]
);
```

**Cảnh báo:** đoạn này chỉ an toàn khi `loc` luôn là **mảng đúng hai số `[lon,lat]` hợp lệ**. Nếu có dữ liệu legacy sai, hãy làm sạch trước; đừng chạy `updateMany` toàn production chỉ vì field có type array.

Cần xem tăng dung lượng index, oplog, replication lag và write traffic trong thời gian backfill.

## 25. Tiêu chí lựa chọn: quy trình quyết định

Hãy đi theo các câu hỏi theo thứ tự sau.

### Câu hỏi 1 — Mô hình hình học là gì?

- Vị trí thực trên Trái Đất, kinh/vĩ độ, spherical distance → ưu tiên **`2dsphere`**.
- Tọa độ X/Y trên mặt phẳng nội bộ, khoảng cách Euclid → cân nhắc **`2d`**.
- Không gian 3D hoặc projected CRS có quy tắc riêng → xác định mô hình trước, có thể cần engine khác.

### Câu hỏi 2 — Dữ liệu có dạng nào?

- GeoJSON Point/LineString/Polygon hoặc loại GeoJSON được hỗ trợ → **`2dsphere`**.
- Legacy coordinate pairs phẳng → **`2d`**.
- Legacy `[lon,lat]` dùng cho Trái Đất → xem **`2dsphere`** hoặc migration GeoJSON.

### Câu hỏi 3 — Query dùng toán tử nào?

- Nearest trên Trái Đất → `2dsphere` + `$near`/`$geoNear`.
- Nằm trong polygon Trái Đất → `2dsphere` + `$geoWithin`.
- Đường/vùng giao nhau → `2dsphere` + `$geoIntersects`.
- Nearest trên mặt bằng → `2d` + `$near` planar.
- Rectangle/circle phẳng → `2d` + `$geoWithin` legacy.

### Câu hỏi 4 — Đơn vị cần trả là gì?

- Mét trong bài toán địa lý → GeoJSON + 2dsphere.
- Đơn vị CAD/pixel/mét nội bộ trên mặt phẳng → 2d và schema unit rõ.
- Travel time/road distance → không index nào tự giải quyết; cần routing layer.

### Câu hỏi 5 — Filter và dữ liệu có đặc điểm gì?

- Có tenantId/category/status không?
- Có nhiều document không có location không?
- Có nhiều loại geometry trong một field không?
- Có rất nhiều điểm trong một document không?
- Có cần compound index không?
- Có chạy trên sharded collection không?

### Câu hỏi 6 — Đã đo hiệu năng chưa?

- Dùng `explain("executionStats")`;
- Thử queries ở dense/sparse areas;
- Đo p95/p99 và CPU/IOPS;
- Kiểm tra index size;
- Thử maxDistance nhỏ/lớn;
- Kiểm tra số shard tham gia nếu có sharding.

### Câu hỏi 7 — Có các trường hợp biên không?

- Antimeridian;
- Vĩ độ cao;
- Polygon có holes;
- Polygon lớn;
- Dữ liệu đảo lat/lon;
- Nhiều tầng hoặc nhiều mặt bằng;
- Geometry không hợp lệ;
- Tọa độ thiếu hoặc null.

Chỉ khi trả lời được những câu hỏi này mới nên chốt index cho production.

## 26. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hậu quả | Cách hiểu đúng |
|---|---|---|
| “2d và 2dsphere đều là index hai số nên tương đương.” | Sai khoảng cách/hình học | Chọn theo planar hay spherical |
| “GeoJSON Point lưu `[lat,lon]`.” | Điểm sai hoặc lỗi index | GeoJSON là `[lon,lat]` |
| “Tọa độ degrees là mét.” | Sai radius và khoảng cách | Phân biệt đơn vị theo operator |
| “`$centerSphere` nhận bán kính mét.” | Vùng truy vấn sai nghiêm trọng | Radius là radian |
| “2d phù hợp mọi polygon GeoJSON.” | Không hỗ trợ semantics cần thiết | Dùng 2dsphere cho GeoJSON geographic |
| “`$near` cần thêm sort theo distance.” | Sort thừa hoặc đổi order | `$near` đã trả nearest order |
| “`$geoWithin` tự sort gần nhất.” | Kết quả không có thứ tự mong muốn | Dùng `$near`/`$geoNear` |
| “`$geoNear` có thể đặt ở bất kỳ stage nào.” | Pipeline lỗi | Đặt `$geoNear` đầu pipeline |
| “`$near` luôn trả field khoảng cách.” | API thiếu distance | Dùng `$geoNear` nếu cần distance field |
| “Không có geo index nhưng `$near` vẫn hoạt động như query thông thường.” | Query lỗi | Tạo geo index phù hợp |
| “2dsphere index bao gồm mọi document dù không có location.” | Báo cáo sai số record | 2dsphere sparse behavior |
| “Missing location và invalid GeoJSON giống nhau.” | Index build/write lỗi | Validate đúng schema |
| “Một tọa độ gần trên sphere nghĩa là đi đường gần.” | ETA sai | Routing engine riêng |
| “Compound index tùy ý đặt 2d sau tenant.” | Cấu hình sai | Geo field `2d` phải đứng đầu trong compound |
| “Có 2dsphere thì query tenant-only luôn nhanh.” | Sai query plan | Cần index thường phù hợp |
| “Geometry chứa mọi điểm nên rẻ hơn một Point.” | Index keys/payload lớn | Đo đa điểm, array, document size |
| “Chỉ cần thay `2d` thành `2dsphere` là migration xong.” | Sai unit và schema | Kiểm tra CRS, dữ liệu, query |
| “Geo index tự route trên sharded cluster.” | Scatter-gather bất ngờ | Shard key khác geospatial index |
| “`explain` chỉ cần xem nReturned.” | Bỏ qua scan/CPU | Xem keys/docs examined và plan |
| “Tọa độ web map pixel là longitude/latitude.” | Sai vị trí | Chuyển projection đúng |

## 27. Bài tập thực hành

### Bài 1 — Chọn index đúng

Cho bốn bài toán:

1. Tìm cửa hàng trong bán kính 2 km quanh khách hàng.
2. Tìm robot cách `[100,200]` không quá 15 đơn vị trong một bản vẽ nhà kho.
3. Tìm đường tàu cắt qua một Polygon địa lý.
4. Tìm điểm kệ bên trong hình chữ nhật X/Y của một mặt bằng.

Với mỗi bài, hãy chọn `2dsphere` hay `2d`, loại geometry, toán tử và đơn vị.

### Bài 2 — GeoJSON coordinate order

Cho:

```javascript
{ type: "Point", coordinates: [10.776, 106.700] }
```

1. Giá trị nào đang được hiểu là longitude?
2. Giá trị nào là latitude?
3. Vấn đề cụ thể là gì?
4. Sửa thành GeoJSON hợp lệ.
5. Giải thích trường hợp đảo lon/lat nhưng cả hai giá trị vẫn thuộc miền hợp lệ.

### Bài 3 — `$near` với 2dsphere

Dùng `geoPlacesLab`:

1. Tạo `2dsphere` index trên `location`.
2. Tìm tối đa 10 điểm trong bán kính 3.000 mét.
3. Thêm `$minDistance: 500`.
4. Quan sát thứ tự của kết quả.
5. Dùng `explain` xác nhận index có tham gia.

### Bài 4 — `$geoWithin` và Polygon

1. Tạo Polygon khép kín quanh bốn điểm.
2. Query các điểm nằm trong Polygon.
3. Đảo thứ tự của một vài điểm và kiểm tra hình dạng.
4. Thử một Polygon thiếu điểm khép kín.
5. Giải thích vì sao GeoJSON valid JSON chưa chắc hợp lệ về geometry.

### Bài 5 — `$geoIntersects`

Tạo hai LineStrings và một Polygon.

1. Tìm những đường giao Polygon.
2. So sánh với câu hỏi “đường nằm trọn trong Polygon”.
3. Vì sao `$geoWithin` và `$geoIntersects` có thể trả tập kết quả khác nhau?
4. Index nào phù hợp nhất?

### Bài 6 — `$geoNear` và khoảng cách

Viết aggregation trả:

- Tên điểm;
- Category;
- Khoảng cách tính bằng mét;
- Giới hạn 5.000 mét;
- Tối đa 10 kết quả.

Giải thích vì sao `$geoNear` thường đứng đầu pipeline và khi nào cần `key`.

### Bài 7 — 2d X/Y

Tạo `floorPointsLab` và index `2d` với miền 0–500.

1. Tìm các điểm gần `[20,20]`.
2. Tìm các điểm trong `$box` `[[0,0],[50,50]]`.
3. Tìm các điểm trong `$center` bán kính 25.
4. Giả sử đơn vị tọa độ là pixel, kết quả radius có ý nghĩa gì?
5. Thêm `floorId` filter để không trộn các tầng.

### Bài 8 — `$centerSphere`

Một ứng dụng muốn tìm những điểm trong vòng 2.000 mét quanh một vị trí GeoJSON.

1. Viết công thức chuyển mét thành radian.
2. Viết query `$geoWithin` + `$centerSphere`.
3. Giải thích sự khác biệt với `$near` + `$maxDistance: 2000`.
4. Nếu truyền thẳng 2000 làm radius của centerSphere thì có gì sai?

### Bài 9 — Sparse behavior

Collection có:

```javascript
[
  { _id: 1, location: { type: "Point", coordinates: [106.7,10.77] } },
  { _id: 2, location: null },
  { _id: 3 }
]
```

1. Record nào có vị trí địa lý phù hợp cho index?
2. Vì sao không thể dùng một geospatial index để tự đếm mọi record?
3. Compound `{tenantId:1,location:"2dsphere"}` có thay đổi quy tắc index docs thiếu location không?
4. Phân biệt missing field với field chứa GeoJSON sai.

### Bài 10 — Migration legacy

Từ:

```javascript
{ loc: [106.7, 10.77] }
```

sang:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7, 10.77]
  }
}
```

Hãy xây kế hoạch kiểm tra lon/lat, backfill, tạo index, thử query, rollout và rollback. Vì sao không nên chạy `drop()` index legacy trước khi mọi consumer chuyển xong?

### Bài 11 — Compound index và workload

Ứng dụng có:

```javascript
db.places.find({
  tenantId: "T-01",
  location: {
    $near: {
      $geometry: { type: "Point", coordinates: [106.7,10.77] },
      $maxDistance: 2000
    }
  }
});
```

1. So sánh index `{location:"2dsphere"}` với `{tenantId:1,location:"2dsphere"}`.
2. Nếu phần lớn query không có tenantId, điều gì cần đo?
3. Vì sao compound `2d` không có cùng tự do thứ tự key như compound 2dsphere?
4. Index `tenantId` thuần có còn cần không?

### Bài 12 — Antimeridian

Một service area chứa cả điểm gần +179.8° và −179.8°.

1. Vì sao bounding box phẳng trên longitude có thể sai?
2. Nên kiểm tra polygon theo hệ hình học nào?
3. Cần những test points nào?
4. Vì sao không nên tự cộng 360° cho mọi longitude mà không hiểu CRS?

### Bài 13 — Sharded cluster

Collection shard theo `tenantId` nhưng có `location` 2dsphere.

1. Geo query chỉ theo location có thể đi tới bao nhiêu shard?
2. Thêm `tenantId` vào filter thay đổi việc route ra sao?
3. Vì sao 2dsphere index không tự thay thế shard key?
4. Cần xem thông tin gì trong explain trên từng shard?

### Bài 14 — Bảo vệ API gần tôi

Thiết kế endpoint:

```text
GET /places/nearby?lon=...&lat=...&radiusMeters=...
```

Xác định:

- Validation longitude/latitude;
- Giá trị radius tối đa;
- Kiểu index;
- Query `$near` hoặc `$geoNear`;
- Giới hạn kết quả;
- Cache strategy;
- Rate limiting;
- Khi nào gọi routing engine để tính ETA;
- Các metric p95/p99 cần theo dõi.

## 28. Tài liệu MongoDB tham khảo

- [Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/)
- [2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/)
- [2d Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2d/)
- [GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/)
- [Geospatial Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query-geospatial/)
- [$near](https://www.mongodb.com/docs/manual/reference/operator/query/near/)
- [$nearSphere](https://www.mongodb.com/docs/manual/reference/operator/query/nearSphere/)
- [$geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/)
- [$geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/)
- [$geoNear Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/)
- [$centerSphere](https://www.mongodb.com/docs/manual/reference/operator/query/centerSphere/)
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)

## Kết luận

**`2dsphere`** là lựa chọn mặc định hợp lý cho phần lớn ứng dụng có **tọa độ địa lý trên Trái Đất**, GeoJSON Point/LineString/Polygon và các truy vấn như tìm địa điểm gần, nằm trong vùng hoặc giao với vùng. Với GeoJSON Point, hãy lưu theo thứ tự **`[longitude, latitude]`**, xác thực miền và hiểu đơn vị khoảng cách (thường là mét ở các toán tử nearest dùng GeoJSON).

**`2d`** phù hợp khi dữ liệu là **tọa độ phẳng X/Y** và ứng dụng muốn các phép đo Euclid trong một hệ mặt bằng có đơn vị rõ ràng. Đây không phải giải pháp thay thế tương đương cho mọi geometry và khoảng cách địa lý.

Ngoài mô hình hình học, hãy kiểm tra **query patterns, compound index, sparse behavior, GeoJSON validity, kích thước geometry, antimeridian, sharding, độ trễ và giới hạn API**. Đừng chọn index chỉ vì tên gọi hoặc vì truy vấn chạy được trên vài document thử nghiệm.

**Lựa chọn đúng bắt đầu bằng việc trả lời: “Hai con số này nằm trên một mặt phẳng nội bộ hay mô tả một vị trí trên Trái Đất, và ứng dụng thật sự cần hỏi câu gì về chúng?”**

