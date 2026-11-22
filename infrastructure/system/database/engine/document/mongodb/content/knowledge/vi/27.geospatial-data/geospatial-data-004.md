# Truy vấn vùng bằng $geoWithin và $geoIntersects trong MongoDB

## 1. Hai câu hỏi địa lý tưởng giống nhau nhưng khác bản chất

Một hệ thống giao hàng, bản đồ bất động sản, quản lý tuyến đường hoặc cảnh báo thiên tai thường phải trả lời những câu hỏi như:

- Cửa hàng nào **nằm trong** phạm vi phục vụ của một khu vực?
- Bất động sản nào **nằm trọn trong** vùng tìm kiếm trên bản đồ?
- Tuyến đường vận chuyển nào **đi qua hoặc chạm vào** một vùng đang phong tỏa?
- Khu vực bán hàng nào **giao nhau** với vùng được chọn?
- Khi người dùng đứng tại một điểm, những polygon vùng phục vụ nào **chứa điểm đó**?

MongoDB cung cấp hai toán tử truy vấn không gian:

- **`$geoWithin`**: chọn document có hình học được lưu **nằm hoàn toàn trong** hình học vùng truy vấn.
- **`$geoIntersects`**: chọn document có hình học được lưu **giao với** hình học truy vấn, tức phần giao không rỗng.

Hai toán tử sử dụng hình học của MongoDB, đặc biệt GeoJSON và chỉ mục `2dsphere`. Chúng có thể cho kết quả khác nhau khi đối tượng được lưu là một `Polygon` hoặc `LineString` thay vì `Point`.

> **Nguyên tắc nhớ nhanh:** “Toàn bộ đối tượng phải nằm trong vùng” → `$geoWithin`; “chỉ cần có phần nào giao vùng” → `$geoIntersects`.

Chọn đúng toán tử chỉ là bước đầu. Phải hiểu thứ tự tọa độ, cấu trúc đa giác, mô hình hình học cầu, vùng biên, chiến lược index và chi phí query thực tế.

---

## 2. MongoDB lưu dữ liệu địa lý ở những dạng nào?

MongoDB hỗ trợ dữ liệu **GeoJSON** và các **legacy coordinate pairs**.

### 2.1. GeoJSON Point

Một địa điểm có `location`:

```javascript
{
  _id: "STORE-01",
  name: "Cửa hàng A",
  location: {
    type: "Point",
    coordinates: [106.7005, 10.7755]
  }
}
```

Thứ tự bắt buộc khi dùng kinh độ/vĩ độ:

```text
coordinates: [ longitude, latitude ]
                kinh độ    vĩ độ
```

Không đảo thành `[latitude, longitude]`, dù một số dịch vụ bản đồ/API đưa dữ liệu ở thứ tự khác.

Giới hạn chuẩn trong hệ tọa độ địa lý mà `2dsphere` sử dụng:

| Thành phần | Giá trị hợp lệ |
| --- | --- |
| Longitude (kinh độ) | Từ -180 đến 180, kể cả hai đầu |
| Latitude (vĩ độ) | Từ -90 đến 90, kể cả hai đầu |
| CRS mặc định của `$geometry` | WGS84 / EPSG:4326 |

Các cặp số trong bài chỉ minh họa dữ liệu. Không suy ra đường đi, địa giới hành chính hay khoảng cách thật từ tọa độ giả lập.

### 2.2. GeoJSON LineString

Một tuyến đường đơn giản:

```javascript
{
  _id: "ROUTE-01",
  route: {
    type: "LineString",
    coordinates: [
      [106.68, 10.77],
      [106.70, 10.78],
      [106.73, 10.80]
    ]
  }
}
```

Một `LineString` chứa ít nhất hai vị trí. Khi truy vấn giao vùng, MongoDB xét các đoạn hình học nối những vị trí này, không chỉ hai đầu tuyến.

### 2.3. GeoJSON Polygon

Một vùng hình chữ nhật giả lập quanh tọa độ nhỏ:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [4, 0],
      [4, 4],
      [0, 4],
      [0, 0]
    ]
  ]
}
```

Cấu trúc rất dễ nhầm:

```text
Polygon
  coordinates = [
    ring 1 = [
      position 1 = [longitude, latitude],
      position 2 = [longitude, latitude],
      ...
      position N = position 1
    ]
  ]
```

- `coordinates` của `Polygon` là **mảng các rings**, không phải danh sách position phẳng.
- Ring phải **đóng**: vị trí đầu và cuối bằng nhau.
- Ring bao ngoài cần tạo vùng không tự cắt; các ring bên trong có thể biểu diễn **lỗ**.
- Các polygon lớn hơn nửa bán cầu có yêu cầu CRS đặc biệt, được trình bày ở phần sau.

Ví dụ lỗi cấu trúc:

```javascript
// Sai: thiếu một lớp mảng ring.
{
  type: "Polygon",
  coordinates: [
    [0, 0],
    [4, 0],
    [4, 4],
    [0, 0]
  ]
}
```

Ví dụ đúng:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [4, 0],
      [4, 4],
      [0, 4],
      [0, 0]
    ]
  ]
}
```

### 2.4. GeoJSON MultiPolygon

Một đối tượng gồm nhiều miền tách rời:

```javascript
{
  type: "MultiPolygon",
  coordinates: [
    [
      [
        [0, 0], [2, 0], [2, 2], [0, 2], [0, 0]
      ]
    ],
    [
      [
        [6, 6], [8, 6], [8, 8], [6, 8], [6, 6]
      ]
    ]
  ]
}
```

`MultiPolygon` có thêm một lớp mảng so với `Polygon`: mảng các polygon; mỗi polygon lại chứa mảng các ring.

**Không** đặt `type: "MultiPolygon"` rồi chỉ cung cấp cấu trúc của một `Polygon` thông thường.

---

## 3. Hai toán tử dưới góc nhìn tập hợp

Gọi:

- `S` là tập điểm của **hình học lưu trong document**;
- `Q` là tập điểm của **hình học đưa vào truy vấn**.

Ý nghĩa khái niệm:

```text
$geoWithin:
  S nằm trong Q.

$geoIntersects:
  S giao Q khác rỗng.
```

Với một polygon nhỏ nằm trọn trong polygon query:

```text
Q:  +-------------------+
    |                   |
    |    +---------+    |
    |    |    S    |    |
    |    +---------+    |
    |                   |
    +-------------------+

$geoWithin:     Có
$geoIntersects: Có
```

Với polygon đi qua ranh giới:

```text
Q:  +-------------------+
    |               +---+-------+
    |               |   S       |
    |               +---+-------+
    +-------------------+

$geoWithin:     Không
$geoIntersects: Có
```

Với hai hình không giao:

```text
Q:  +------------+             S:  +--------+
    |            |                 |        |
    +------------+                 +--------+

$geoWithin:     Không
$geoIntersects: Không
```

### 3.1. Bảng quyết định

| Hình học được lưu | Quan hệ với vùng query | `$geoWithin` | `$geoIntersects` |
| --- | --- | --- | --- |
| Point | Nằm rõ bên trong | Khớp | Khớp |
| Point | Nằm rõ bên ngoài | Không | Không |
| Polygon | Nằm hoàn toàn bên trong | Khớp | Khớp |
| Polygon | Chỉ một phần nằm trong | Không | Khớp |
| Polygon | Bao chứa toàn bộ vùng query | Không | Khớp |
| LineString | Toàn bộ tuyến ở trong vùng | Khớp | Khớp |
| LineString | Chỉ đi qua vùng | Không | Khớp |
| Polygon/LineString | Hoàn toàn tách rời | Không | Không |
| Hình chỉ **chạm cạnh/đỉnh** | Tình huống suy biến | **Không bảo đảm như hình học lý tưởng** | **Không bảo đảm như hình học lý tưởng** |

**Quan trọng về ranh giới:** MongoDB ghi rõ các trường hợp *degenerate geometry* không được bảo đảm như cách diễn giải “điểm trên biên là ở trong”. Chẳng hạn, `$geoIntersects` không bảo đảm nhận diện một polygon giao chính cạnh/đỉnh của nó hoặc một polygon khác chỉ chia sẻ cạnh/đỉnh mà không có phần diện tích bên trong giao nhau. `$geoWithin` cũng không bảo đảm coi một hình chứa chính những thành phần biên của nó. Phải kiểm thử các điểm biên theo yêu cầu nghiệp vụ và không gán toàn bộ quy tắc topological GIS tổng quát cho server.

---

## 4. Chuẩn bị bộ dữ liệu thử nghiệm

Để tách việc hiểu hình học khỏi độ phức tạp của bản đồ thực, dùng các tọa độ **giả lập gần gốc [0, 0]**. Chúng hợp lệ theo WGS84, nhưng không đại diện một khu vực kinh doanh thực tế.

### 4.1. Các điểm địa lý

Tạo collection thử nghiệm mới, không xóa dữ liệu production:

```javascript
db.geoPoints294.insertMany([
  {
    _id: "P-IN-1",
    category: "store",
    name: "Điểm bên trong 1",
    location: {
      type: "Point",
      coordinates: [1, 1]
    }
  },
  {
    _id: "P-IN-2",
    category: "warehouse",
    name: "Điểm bên trong 2",
    location: {
      type: "Point",
      coordinates: [3, 2]
    }
  },
  {
    _id: "P-OUT",
    category: "store",
    name: "Điểm bên ngoài",
    location: {
      type: "Point",
      coordinates: [6, 6]
    }
  },
  {
    _id: "P-BOUNDARY",
    category: "store",
    name: "Điểm trên biên để kiểm thử",
    location: {
      type: "Point",
      coordinates: [4, 2]
    }
  }
]);
```

`P-BOUNDARY` được đưa vào cố ý để cho thấy **không nên viết test phụ thuộc vào một kết luận tuyệt đối tại biên** nếu chưa xác nhận behavior cụ thể.

### 4.2. Những polygon địa lý

Tạo collection khác để thấy rõ khác biệt giữa **chứa hoàn toàn** và **giao nhau**:

```javascript
db.geoAreas294.insertMany([
  {
    _id: "A-INNER",
    name: "Vùng hoàn toàn nằm trong",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [1, 1], [2, 1], [2, 2], [1, 2], [1, 1]
        ]
      ]
    }
  },
  {
    _id: "A-CROSS",
    name: "Vùng cắt qua mép phải",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [3, 1], [5, 1], [5, 3], [3, 3], [3, 1]
        ]
      ]
    }
  },
  {
    _id: "A-OUTER",
    name: "Vùng bao phủ vùng truy vấn",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-1, -1], [6, -1], [6, 6], [-1, 6], [-1, -1]
        ]
      ]
    }
  },
  {
    _id: "A-FAR",
    name: "Vùng tách rời",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [7, 7], [8, 7], [8, 8], [7, 8], [7, 7]
        ]
      ]
    }
  }
]);
```

Bốn polygon được đặt để không phải tranh luận về tiếp xúc biên trong các trường hợp chính.

### 4.3. Polygon truy vấn dùng chung

```javascript
const queryArea = {
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [4, 0],
      [4, 4],
      [0, 4],
      [0, 0]
    ]
  ]
};
```

Đây là **hình học query**, không phải document được insert vào collection. Mọi ví dụ bên dưới dùng `queryArea` này trong cùng phiên `mongosh`, trừ khi nói khác.

---

## 5. Dùng $geoWithin để tìm các Point nằm trong vùng

Cú pháp chuẩn:

```javascript
db.geoPoints294.find({
  location: {
    $geoWithin: {
      $geometry: queryArea
    }
  }
});
```

Hoặc viết đầy đủ:

```javascript
db.geoPoints294.find({
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [
          [
            [0, 0],
            [4, 0],
            [4, 4],
            [0, 4],
            [0, 0]
          ]
        ]
      }
    }
  }
});
```

**Kết quả chắc chắn theo cách bố trí điểm rõ bên trong/bên ngoài:**

- `P-IN-1` và `P-IN-2` phù hợp.
- `P-OUT` không phù hợp.
- `P-BOUNDARY` phải được kiểm thử riêng; không dùng nó để suy ra quy tắc biên tuyệt đối.

Truy vấn chỉ cần trả ID và tên:

```javascript
db.geoPoints294.find(
  {
    location: {
      $geoWithin: {
        $geometry: queryArea
      }
    }
  },
  {
    _id: 1,
    name: 1,
    category: 1
  }
).sort({ _id: 1 });
```

**`$geoWithin` không tự sắp xếp theo khoảng cách hay tên.** Nếu API cần thứ tự ổn định, phải thêm `sort()` hoặc `$sort` phù hợp.

### 5.1. Ghép điều kiện thông thường

```javascript
db.geoPoints294.find({
  category: "store",
  location: {
    $geoWithin: {
      $geometry: queryArea
    }
  }
});
```

Ý nghĩa: chỉ các cửa hàng nằm trong vùng. Điều kiện `category` là filter thông thường kết hợp theo AND, không ảnh hưởng cách định nghĩa hình học.

---

## 6. Dùng $geoWithin cho Polygon được lưu

Nếu field của document là một Polygon, `$geoWithin` yêu cầu **toàn bộ hình học đó** nằm trong vùng query:

```javascript
db.geoAreas294.find(
  {
    geometry: {
      $geoWithin: {
        $geometry: queryArea
      }
    }
  },
  {
    _id: 1,
    name: 1
  }
).sort({ _id: 1 });
```

Trong dữ liệu mẫu, trường hợp rõ ràng được chọn là:

```text
A-INNER
```

Giải thích:

- `A-INNER` nằm hoàn toàn trong `queryArea`.
- `A-CROSS` có phần nằm ngoài mép phải.
- `A-OUTER` lớn hơn và bao chứa chính vùng query, nên **không nằm trọn trong query**.
- `A-FAR` ở xa, không giao.

**Đặc biệt:** câu hỏi “polygon A có chứa polygon Q không?” không có cùng chiều với “polygon A có nằm trong polygon Q không?”. Trong cú pháp MongoDB, **field của document đứng bên ngoài toán tử** và **hình học đưa vào `$geometry` là vùng tham chiếu**. Muốn hỏi “vùng nào chứa một điểm”, thường chuyển sang `$geoIntersects` trên field polygon với Point query.

---

## 7. Dùng $geoIntersects để tìm đối tượng giao vùng

Cú pháp:

```javascript
db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: queryArea
    }
  }
});
```

Hoặc chỉ lấy ID:

```javascript
db.geoAreas294.find(
  {
    geometry: {
      $geoIntersects: {
        $geometry: queryArea
      }
    }
  },
  { _id: 1, name: 1 }
).sort({ _id: 1 });
```

Với bốn polygon mẫu, dự kiến:

```text
A-CROSS
A-INNER
A-OUTER
```

`A-FAR` không giao nên không có trong kết quả.

Sự khác biệt:

| Đối tượng | `$geoWithin` | `$geoIntersects` | Lý do |
| --- | --- | --- | --- |
| `A-INNER` | Có | Có | Nằm toàn bộ trong query. |
| `A-CROSS` | Không | Có | Có diện tích giao nhưng có phần ngoài. |
| `A-OUTER` | Không | Có | Bao phủ toàn bộ query; vẫn có giao. |
| `A-FAR` | Không | Không | Không giao. |

### 7.1. Dùng $geoIntersects với Point

Với Point nằm trong Polygon, phép giao không rỗng:

```javascript
db.geoPoints294.find({
  location: {
    $geoIntersects: {
      $geometry: queryArea
    }
  }
});
```

Với những Point không nằm trên biên, kết quả về mặt ý nghĩa giống truy vấn `$geoWithin` tìm điểm trong vùng.

Nhưng **đừng suy rộng hai toán tử là tương đương**. Khi document lưu LineString/Polygon, quan hệ “nằm trọn” và “có giao” khác nhau rất lớn.

### 7.2. Không phải toán tử tính khoảng cách

`$geoIntersects` trả về **boolean spatial relationship**, không trả con số khoảng cách đến tâm vùng. Nếu muốn tìm gần nhất và sắp xếp theo độ gần, dùng `$near`, `$nearSphere` hoặc `$geoNear` phù hợp.

---

## 8. Truy vấn ngược: tìm những vùng chứa một vị trí

Đây là tình huống cực kỳ phổ biến nhưng người mới thường viết sai chiều.

Giả sử collection `deliveryZones` lưu **các Polygon vùng giao hàng**, còn người dùng có một Point. Muốn tìm vùng nào bao chứa Point đó, truy vấn **trên field polygon** bằng `$geoIntersects` với Point:

```javascript
const customerPoint = {
  type: "Point",
  coordinates: [1.5, 1.5]
};

db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: customerPoint
    }
  }
});
```

Ở dữ liệu mẫu, các polygon có phần diện tích rõ chứa Point [1.5, 1.5] là `A-INNER` và `A-OUTER`.

### 8.1. Vì sao không dùng $geoWithin ở chiều này?

Sai về **ý nghĩa nghiệp vụ**:

```javascript
db.geoAreas294.find({
  geometry: {
    $geoWithin: {
      $geometry: customerPoint
    }
  }
});
```

Câu truy vấn trên đòi **toàn bộ polygon trong database nằm trong một điểm**. Nó không phải yêu cầu “điểm người dùng nằm trong polygon”.

Mẹo tư duy:

```text
Lưu STORE là Point, QUERY là Polygon:
  STORE nằm trong QUERY => $geoWithin.

Lưu ZONE là Polygon, QUERY là Point:
  ZONE giao Point => $geoIntersects.
```

### 8.2. Vùng chồng lấn

Nếu nhiều vùng cùng chứa customer Point, truy vấn có thể trả **nhiều document**. MongoDB không tự quyết định ưu tiên vùng rẻ nhất hoặc vùng của cửa hàng được chọn. Ứng dụng cần thêm:

- Tenant hoặc merchant ID.
- Trạng thái zone active.
- Zone priority.
- Thời gian hoạt động, điều kiện dịch vụ.
- Quy tắc phân xử khi nhiều zone cùng chứa một Point.

Ví dụ:

```javascript
db.deliveryZones.find({
  tenantId: "T100",
  status: "ACTIVE",
  geometry: {
    $geoIntersects: {
      $geometry: customerPoint
    }
  }
}).sort({
  priority: -1,
  _id: 1
});
```

Với vùng chồng lấn, thứ tự nghiệp vụ là quy tắc của domain, không phải semantics của toán tử không gian.

---

## 9. LineString: tuyến đường nằm trọn hay chỉ đi qua vùng?

Lưu hai tuyến mẫu:

```javascript
db.geoRoutes294.insertMany([
  {
    _id: "R-IN",
    line: {
      type: "LineString",
      coordinates: [
        [1, 1], [2, 2], [3, 3]
      ]
    }
  },
  {
    _id: "R-CROSS",
    line: {
      type: "LineString",
      coordinates: [
        [-1, 2], [2, 2], [5, 2]
      ]
    }
  },
  {
    _id: "R-FAR",
    line: {
      type: "LineString",
      coordinates: [
        [7, 7], [8, 8]
      ]
    }
  }
]);
```

Tìm tuyến **nằm hoàn toàn trong** vùng:

```javascript
db.geoRoutes294.find({
  line: {
    $geoWithin: {
      $geometry: queryArea
    }
  }
});
```

Rõ ràng `R-IN` phù hợp. `R-CROSS` có đầu và cuối ngoài vùng; `R-FAR` tách rời.

Tìm tuyến **chạy qua hoặc giao** vùng:

```javascript
db.geoRoutes294.find({
  line: {
    $geoIntersects: {
      $geometry: queryArea
    }
  }
});
```

`R-IN` và `R-CROSS` đều phù hợp do có đoạn đường trong polygon.

### 9.1. Không chỉ kiểm tra tọa độ đầu và cuối

Một LineString có cả hai đầu ở ngoài nhưng đoạn giữa đi qua vùng vẫn có thể khớp `$geoIntersects`.

Ngược lại, một tuyến có điểm đầu và cuối nằm trong nhưng đi vòng ra ngoài giữa chừng không nằm hoàn toàn trong vùng query. `$geoWithin` là quan hệ của **toàn bộ đường**, không phải chỉ `coordinates[0]`.

### 9.2. Đây là hình học, không phải mạng giao thông

MongoDB không tính tới đường một chiều, giao lộ, cầu vượt, điều kiện giao thông hoặc kết nối graph. Một tuyến hình học giao vùng không chứng minh xe thật đi vào vùng đó nếu dữ liệu LineString chỉ là đường thẳng nối các điểm đo thưa.

Đối với geofencing có độ tin cậy cao, cần GPS sampling, map matching hoặc routing chuyên dụng.

---

## 10. Polygon có lỗ (holes)

Một polygon vùng giao hàng có thể bao phủ khu vực lớn nhưng loại trừ một vùng ở giữa:

```javascript
const zoneWithHole = {
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
      [0, 0]
    ],
    [
      [4, 4],
      [4, 6],
      [6, 6],
      [6, 4],
      [4, 4]
    ]
  ]
};
```

Ring đầu tiên là vùng ngoài; ring tiếp theo là **lỗ**. Việc định nghĩa phải tuân quy tắc GeoJSON, ring closure, không tự cắt và hướng winding phù hợp với geometry/CRS được sử dụng.

Các Point minh họa:

- `[2, 2]` nằm rõ trong vùng được bao phủ.
- `[5, 5]` nằm rõ trong lỗ, **không thuộc vùng phủ**.
- `[12, 12]` ở ngoài hoàn toàn.

Ví dụ dùng trực tiếp:

```javascript
db.geoPoints294.find({
  location: {
    $geoWithin: {
      $geometry: zoneWithHole
    }
  }
});
```

Đối với hệ giao hàng, khoanh vùng lỗ có thể mô tả công viên, hồ nước, khu vực bị cấm, hoặc một phần dịch vụ không nhận đơn.

**Đừng tự loại trừ lỗ bằng cách chỉ dùng vòng ngoài**: điểm nằm trong lỗ sẽ bị tính nhầm là được phục vụ. Nếu vùng được nhập từ GIS có nhiều lỗ, hãy dùng thư viện GeoJSON để validate trước khi ghi.

### 10.1. LineString giao vùng có lỗ

Một tuyến chỉ nằm trong **lỗ** có thể không giao phần diện tích của polygon; một tuyến băng qua vùng được phép rồi qua lỗ vẫn có giao với vùng được phép. Cần dùng `$geoIntersects` trên toàn bộ LineString, không chỉ `$geoWithin` trên bounding box của polygon.

### 10.2. MultiPolygon

Nếu một vùng phục vụ gồm nhiều “đảo” tách rời, dùng GeoJSON `MultiPolygon` thay vì tạo một vòng polygon tự cắt để nối các đảo. `$geoWithin` và `$geoIntersects` hỗ trợ hình học GeoJSON theo kiểu dữ liệu được phép, bao gồm các trường hợp dùng `MultiPolygon` làm vùng query.

---

## 11. Hình học legacy: $box, $polygon, $center và $centerSphere

`$geoWithin` không chỉ có cú pháp `$geometry`. MongoDB còn hỗ trợ các shape specifier dành cho **legacy coordinate pairs**:

| Shape specifier | Ý nghĩa | Phương pháp tính | Index phù hợp |
| --- | --- | --- | --- |
| `$geometry: {type:"Polygon",...}` | GeoJSON Polygon/MultiPolygon | Cầu (spherical) | `2dsphere` |
| `$box` | Hình chữ nhật theo hai góc | Phẳng (planar) | `2d` |
| `$polygon` | Đa giác legacy | Phẳng (planar) | `2d` |
| `$center` | Hình tròn legacy trên mặt phẳng | Phẳng (planar) | `2d` |
| `$centerSphere` | Hình tròn trên mặt cầu | Cầu (spherical) | `2dsphere` và `2d` theo điều kiện |

`$geoIntersects` **không** dùng `$box`, `$polygon` hay `$center` như một GeoJSON geometry query. Nó nhận đối tượng GeoJSON qua `$geometry`.

### 11.1. Dữ liệu legacy riêng

```javascript
db.geoLegacy294.insertMany([
  { _id: "L-IN", loc: [1, 1] },
  { _id: "L-OUT", loc: [6, 6] }
]);

db.geoLegacy294.createIndex({
  loc: "2d"
});
```

Ở đây `loc` là `[x, y]`, không phải:

```javascript
{
  type: "Point",
  coordinates: [x, y]
}
```

### 11.2. $box

```javascript
db.geoLegacy294.find({
  loc: {
    $geoWithin: {
      $box: [
        [0, 0],
        [4, 4]
      ]
    }
  }
});
```

`$box` sử dụng **hình học phẳng**, thích hợp bài toán tọa độ XY trên mặt phẳng. Nó không tự biến vùng hình chữ nhật kinh-vĩ độ thành polygon geodesic chính xác trên trái đất.

### 11.3. $polygon

```javascript
db.geoLegacy294.find({
  loc: {
    $geoWithin: {
      $polygon: [
        [0, 0],
        [4, 0],
        [2, 4]
      ]
    }
  }
});
```

`$polygon` legacy có cạnh cuối nối ngầm về điểm đầu và tính hình học **phẳng**. Nó không dùng cho GeoJSON Polygon với index `2dsphere` theo cùng cách `$geometry`.

### 11.4. $center

```javascript
db.geoLegacy294.find({
  loc: {
    $geoWithin: {
      $center: [
        [1, 1],
        2
      ]
    }
  }
});
```

Khoảng cách của `$center` tính theo **đơn vị phẳng của tọa độ**, không mặc nhiên là mét hoặc kilômét.

### 11.5. $centerSphere

Đối với bán kính thực tế tính trên mặt cầu:

```javascript
db.geoPoints294.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [1, 1],
        5 / 6378.1
      ]
    }
  }
});
```

Đây là ví dụ một hình tròn bán kính khoảng **5 km** quanh `[longitude=1, latitude=1]`, dùng bán kính trái đất xấp xỉ `6378.1 km`. **Tham số radius của `$centerSphere` là radians**, không phải mét hay độ.

Công thức:

```text
angularRadiusRadians = distanceKm / earthRadiusKm
                     ≈ distanceKm / 6378.1
```

Không truyền:

```javascript
$centerSphere: [[1, 1], 5000]
```

với ý nghĩ `5000` là 5.000 mét. Số này sai đơn vị và không thể biểu diễn cách tìm gần 5 km.

---

## 12. Truy vấn trong bán kính khác $near như thế nào?

Bài toán “những điểm nào **cách tâm không quá** 5 km” có ít nhất hai hướng:

1. **Chỉ cần biết có nằm trong hình tròn không** → `$geoWithin` với `$centerSphere`.
2. **Muốn sắp xếp gần nhất trước và/hoặc lấy khoảng cách** → `$near`, `$nearSphere` hoặc aggregation `$geoNear`.

Ví dụ trong vòng tròn:

```javascript
const center = [106.70, 10.78];
const radiusKm = 5;

db.places.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        center,
        radiusKm / 6378.1
      ]
    }
  }
});
```

Câu trên **không** tự sort theo khoảng cách.

Ví dụ tìm theo khoảng cách bằng GeoJSON point với radius mét:

```javascript
db.places.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: center
      },
      $maxDistance: 5000
    }
  }
});
```

`$near` yêu cầu geospatial index thích hợp và sắp xếp theo khoảng cách. Với GeoJSON và `2dsphere`, `$maxDistance` được hiểu theo **mét**, khác với radians của `$centerSphere`.

### 12.1. So sánh nhanh

| Mục tiêu | Dùng |
| --- | --- |
| Điểm nằm trong một đa giác hành chính | `$geoWithin` + Polygon |
| Một vùng polygon giao vùng tìm kiếm | `$geoIntersects` |
| Tuyến đường đi qua một khu vực | `$geoIntersects` |
| Điểm nằm trong bán kính 5 km, không cần sort | `$geoWithin` + `$centerSphere` |
| 10 điểm gần nhất theo khoảng cách | `$near` hoặc `$geoNear` |
| Tính thêm khoảng cách trong aggregation | `$geoNear` và các stage phù hợp |

**Khoảng cách hình học** không tương đương khoảng cách lái xe theo đường thực. MongoDB không thay một routing engine bằng những toán tử này.

---

## 13. Tạo 2dsphere index cho truy vấn vùng

MongoDB cho phép `$geoWithin` và `$geoIntersects` chạy **không có geospatial index** nhưng hiệu năng thường kém khi collection lớn. Với GeoJSON trên trái đất, index khuyến nghị là `2dsphere`.

```javascript
db.geoPoints294.createIndex({
  location: "2dsphere"
});

db.geoAreas294.createIndex({
  geometry: "2dsphere"
});

db.geoRoutes294.createIndex({
  line: "2dsphere"
});
```

### 13.1. Điều gì được index?

- `Point`: vị trí.
- `LineString`: hình học đường.
- `Polygon`: hình học vùng.
- `MultiPolygon`: nhiều vùng thuộc cùng field.

MongoDB dùng biểu diễn không gian nội bộ phục vụ chỉ mục spherical. Khi query, index giúp khoanh vùng ứng viên; server vẫn phải đánh giá quan hệ hình học phù hợp để trả kết quả đúng theo semantics.

### 13.2. $geoIntersects và index

Tài liệu server nêu:

- `$geoIntersects` **không bắt buộc** có geospatial index để chạy.
- Nhưng **chỉ `2dsphere` geospatial index** hỗ trợ tối ưu loại query này.
- `2d` index không phải lựa chọn thay thế cho `$geoIntersects` spherical geometry.

Điều tương tự với `$geoWithin` cần phân biệt: `$geoWithin` có thể dùng `2dsphere` cho GeoJSON spherical hoặc `2d` cho những shape legacy planar phù hợp.

### 13.3. 2dsphere index là sparse

MongoDB `2dsphere` index là **sparse theo bản chất**:

- Document không có field hình học không được thêm entry từ field này.
- Field địa lý là `null` hoặc mảng rỗng không được thêm entry.
- Với compound `2dsphere` index, việc field địa lý có dữ liệu quyết định document có được đưa vào index hay không, không phải chỉ các field thông thường.

Điều này quan trọng cho báo cáo “tìm mọi bản ghi trong khu vực”: document **không có tọa độ hợp lệ** không thể tự được xem là “nằm ngoài” hoặc “nằm trong” vùng; cần theo dõi dữ liệu thiếu vị trí riêng.

### 13.4. Dữ liệu sai kiểu có thể làm index build hoặc insert lỗi

Ví dụ sai schema:

```javascript
{
  _id: "BROKEN",
  location: "10.78,106.70"
}
```

Một string không phải GeoJSON geometry hoặc legacy pair hợp lệ. Nếu field được index bằng `2dsphere`, thao tác ghi hoặc tạo index có thể lỗi. Cần validate và migrate dữ liệu cũ trước khi tạo index production.

### 13.5. Chỉ mục không thể thay chính sách shard key

MongoDB **không cho dùng geospatial index làm shard key**. Có thể tạo `2dsphere` index trên sharded collection, nhưng shard key phải được chọn riêng theo quy tắc sharding. Không viết `sh.shardCollection("db.coll",{location:"2dsphere"})` như giải pháp shard theo vùng.

---

## 14. Compound index kết hợp filter nghiệp vụ và geospatial

Một collection của dịch vụ đa tenant:

```javascript
{
  _id: "STORE-100",
  tenantId: "T100",
  status: "ACTIVE",
  category: "pharmacy",
  location: {
    type: "Point",
    coordinates: [106.70, 10.78]
  }
}
```

Nhiều request có cả tenant/status/category và vùng:

```javascript
db.stores.find({
  tenantId: "T100",
  status: "ACTIVE",
  location: {
    $geoWithin: {
      $geometry: someRegion
    }
  }
});
```

Một compound index có thể đáng thử:

```javascript
db.stores.createIndex({
  tenantId: 1,
  status: 1,
  location: "2dsphere"
});
```

Lựa chọn thứ tự field và liệu có cần index riêng cho những query khác phải dựa trên **thống kê thực tế**, không chỉ một ví dụ.

### 14.1. Không phải cứ index compound là luôn được chọn

Query planner có thể chọn kế hoạch khác nếu:

- Một điều kiện quá rộng, ít chọn lọc.
- Phần geospatial tạo quá nhiều ứng viên.
- Có index khác rẻ hơn.
- Statistics/distribution thay đổi.
- Một `$sort` yêu cầu index phục vụ thứ tự khác.

Cần dùng `explain("executionStats")` và latency thật trước khi kết luận.

### 14.2. Geospatial index không cover query

MongoDB geospatial indexes không hỗ trợ **covered query** theo cách index B-tree thường có thể hoàn toàn thay thế đọc document. Đừng kỳ vọng chỉ `projection` vài field là server không cần fetch document.

---

## 15. Kiểm tra hiệu năng bằng explain

```javascript
db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: queryArea
    }
  }
}).explain("executionStats");
```

Điều quan sát:

- Có geospatial index phù hợp được sử dụng không?
- `totalKeysExamined`, `totalDocsExamined` bao nhiêu?
- `nReturned` có nhỏ hơn đáng kể số candidate documents không?
- Plan có các stage phục vụ geo matching/index hay phải scan rộng?
- Query có filter tenant/status làm giảm dữ liệu trước khi đánh giá hình học không?
- Tốc độ thay đổi thế nào nếu polygon query có nhiều đỉnh hoặc chiếm phần lớn thế giới?

Tên stage trong `explain` khác nhau theo MongoDB version và execution engine. Không hardcode một stage name như bằng chứng duy nhất.

### 15.1. $geoWithin và $geoIntersects không sort

Nếu client muốn trả kết quả theo tên hoặc ID:

```javascript
db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: queryArea
    }
  }
}).sort({
  name: 1,
  _id: 1
});
```

Sort có thể tốn tài nguyên khi dữ liệu trả nhiều. Nếu cần sort theo khoảng cách đến một Point, hãy thiết kế query dùng `$near`/`$geoNear` hoặc phương thức tính tương ứng, không giả định geoWithin/intersects có sẵn distance score.

### 15.2. $match trong aggregation

```javascript
db.geoAreas294.aggregate([
  {
    $match: {
      geometry: {
        $geoIntersects: {
          $geometry: queryArea
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1
    }
  },
  {
    $sort: {
      name: 1
    }
  }
]);
```

Khi có thể, đặt filter vùng và tenant sớm trong pipeline để giảm dữ liệu trung gian. Tuy nhiên optimizer và index selection còn phụ thuộc cụ thể vào các stage, nên vẫn cần phân tích explain.

---

## 16. Sử dụng $geoIntersects với GeoJSON Point query

Không phải query geospatial nào cũng phải là một Polygon.

Với collection lưu **vùng polygon**, cần tìm vùng nào bao một Point:

```javascript
db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [1.5, 1.5]
      }
    }
  }
});
```

Với collection lưu **tuyến đường**, có thể hỏi tuyến nào đi qua một vùng query bằng Polygon. Với collection lưu các polygon, có thể hỏi vùng nào giao với một **LineString** đi qua hành lang kiểm tra.

```javascript
const inspectionRoute = {
  type: "LineString",
  coordinates: [
    [-1, 1],
    [2, 2],
    [5, 3]
  ]
};

db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: inspectionRoute
    }
  }
});
```

Về nghĩa hình học, phép giao là quan hệ **đối xứng** giữa hai hình: đường giao polygon và polygon giao đường. Nhưng **vị trí field, index và loại collection đang truy vấn** quyết định câu query MongoDB nào phục vụ nghiệp vụ bạn muốn.

---

## 17. Polygon lớn hơn nửa bán cầu và strict winding CRS

Một vấn đề hiếm gặp nhưng nghiêm trọng là GeoJSON Polygon lớn hơn **một nửa diện tích trái đất**.

Với CRS mặc định, MongoDB có thể diễn giải polygon lớn hơn một bán cầu theo **hình học bổ sung nhỏ hơn** (*complementary geometry*). Kết quả có thể ngược với ý định truy vấn vùng rất lớn.

Đối với **single-ring GeoJSON Polygon** có diện tích ít nhất khoảng một bán cầu, MongoDB cung cấp custom CRS:

```javascript
const bigPolygon = {
  type: "Polygon",
  coordinates: [
    [
      [-100, 60],
      [-100, 0],
      [-100, -60],
      [100, -60],
      [100, 60],
      [-100, 60]
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

Cách dùng:

```javascript
db.worldRegions.find({
  geometry: {
    $geoIntersects: {
      $geometry: bigPolygon
    }
  }
});
```

hoặc:

```javascript
db.worldRegions.find({
  geometry: {
    $geoWithin: {
      $geometry: bigPolygon
    }
  }
});
```

### 17.1. Những điều kiện quan trọng

- CRS đặc biệt trên là cơ chế **MongoDB strict winding**.
- Nó dùng **hướng vòng ngược chiều kim đồng hồ** cho polygon một ring theo quy tắc.
- Không áp dụng cùng cơ chế cho mọi `MultiPolygon` hoặc polygon có nhiều rings có diện tích quá lớn rồi kỳ vọng behavior giống single-ring.
- Nếu một polygon lớn sử dụng CRS mặc định, query có thể tìm vùng **bổ sung nhỏ hơn** thay vì vùng định nghĩa lớn.

Với hệ thống thành phố/quận có polygon nhỏ, không nên thêm CRS đặc biệt vào mọi query chỉ vì thấy ví dụ trên internet. Chỉ dùng nó khi trường hợp hình học lớn và yêu cầu phù hợp.

### 17.2. Vùng gần đường đổi ngày và cực

Kinh độ `+179.9` và `-179.9` gần nhau trên trái đất, dù cách xa trên trục số tuyến tính. `2dsphere` hiểu hình học spherical. Một bounding box planar giả lập vùng “từ 179 đến -179” dễ tạo ra một rectangle sai hoặc không hợp lệ.

Nếu vùng query cắt **antimeridian** (đường đổi ngày), cần dữ liệu GeoJSON và chiến lược chia polygon thích hợp, không lấy `minLongitude=-179`, `maxLongitude=179` rồi coi đây là một viewport rộng 2 độ.

---

## 18. Ranh giới: tại sao không nên mặc định inclusive?

Trong hình học toán học thuần túy, ta thường hỏi một điểm nằm **trên cạnh** có được tính là bên trong hay không. Với geospatial MongoDB, tài liệu mô tả các trường hợp biên/suy biến có thể không được bảo đảm.

### 18.1. $geoWithin

MongoDB không bảo đảm coi một hình chứa chính hình học thành phần của nó hoặc polygon khác chỉ chia sẻ hình học thành phần. Vì vậy, đừng viết quy tắc “mọi Point trên vertex/edge đều thuộc zone” mà chưa kiểm chứng.

### 18.2. $geoIntersects

MongoDB không bảo đảm coi polygon là giao với:

- Cạnh của chính nó.
- Đỉnh của chính nó.
- Polygon khác chỉ chia sẻ cạnh/đỉnh, không có phần nội thất giao nhau.

### 18.3. Hệ quả với nghiệp vụ

- **Phí giao hàng trên ranh giới vùng:** cần quy tắc phân xử deterministic ở lớp nghiệp vụ.
- **Phân định địa giới pháp lý:** cần GIS system/geometry validation phù hợp, không chỉ dùng một predicate MongoDB.
- **Cảnh báo thiên tai:** có thể thêm buffer/biên an toàn có kiểm soát và xem xét độ chính xác GPS.
- **Thiết bị nằm sát polygon:** GPS jitter có thể làm trạng thái inside/outside thay đổi liên tục; nên có hysteresis hoặc nhiều mẫu liên tục.

Ví dụ “thêm 10 mét cho an toàn” không thể thực hiện bằng cách cộng cố định `0.0001` vào mọi longitude/latitude rồi xem đó là khoảng cách 10 mét toàn cầu. Đơn vị độ phụ thuộc vĩ độ và phép chiếu.

---

## 19. GeoJSON Polygon validation: dữ liệu hợp lệ trước khi query

MongoDB có một số kiểm tra schema/hình học, nhưng application nên validate đầu vào sớm để tránh lưu dữ liệu lỗi và trả thông báo rõ.

Một quy trình validation tốt:

1. Kiểm tra `type` nằm trong các GeoJSON geometry types mà feature hỗ trợ.
2. Kiểm tra `coordinates` có đúng số lớp mảng.
3. Kiểm tra mỗi Position gồm các số hữu hạn và kinh/vĩ độ hợp lệ.
4. Với Polygon: mỗi linear ring đóng, điểm đầu và cuối trùng, đủ số positions.
5. Kiểm tra không có self-intersection, ring trùng lặp hoặc lỗ nằm ngoài ring chính khi domain không cho phép.
6. Kiểm tra giới hạn số đỉnh, kích thước BSON, độ phức tạp hình học và tổng số polygon.
7. Chuẩn hóa CRS/coordinate convention một cách có chủ đích, không tự đoán vị trí lat/lon bị đảo.
8. Chọn chính sách xử lý gần antimeridian và vùng cực.
9. Xác nhận dữ liệu nằm trong tenant/namespace được phép.
10. Test các trường hợp vùng biên bằng bộ dữ liệu nghiệp vụ.

### 19.1. Không tự sửa polygon lỗi bằng thao tác đơn giản

Một polygon tự cắt kiểu “bow tie”:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [4, 4],
      [0, 4],
      [4, 0],
      [0, 0]
    ]
  ]
}
```

không phải một polygon đơn hợp lệ theo quy tắc vùng mong muốn. Không giải quyết bằng cách tự sort các vertex theo longitude, vì sẽ làm biến đổi hình dạng/ngữ nghĩa. Dùng thư viện GIS chuyên dụng để sửa, hoặc từ chối đầu vào và yêu cầu client gửi hình hợp lệ.

### 19.2. JSON Schema validation

Một schema MongoDB có thể yêu cầu field `location` tồn tại và là object, nhưng **không thay thế full geometry validation**:

```javascript
db.runCommand({
  collMod: "geoPoints294",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["location"],
      properties: {
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
              maxItems: 2
            }
          }
        }
      }
    }
  },
  validationAction: "error"
});
```

Ví dụ trên **chỉ minh họa document shape** và cố ý chưa kiểm tra từng tọa độ numeric/range. Trong production, không overwrite validator hiện tại mà chưa hợp nhất rule cũ; phải có validation ở API và/hoặc GIS layer.

---

## 20. Java Sync Driver: lưu GeoJSON và tạo index

MongoDB Java Sync Driver có các class GeoJSON tiện dụng:

- `com.mongodb.client.model.geojson.Point`
- `com.mongodb.client.model.geojson.Position`
- `com.mongodb.client.model.geojson.LineString`
- `com.mongodb.client.model.geojson.Polygon`

Ví dụ lưu Point:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.geojson.Point;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;

public final class StoreLocationRepository {

    public static void prepareIndex(
            MongoCollection<Document> stores
    ) {
        stores.createIndex(Indexes.geo2dsphere("location"));
    }

    public static void insertStore(
            MongoCollection<Document> stores,
            String id,
            double longitude,
            double latitude
    ) {
        if (!Double.isFinite(longitude) ||
            !Double.isFinite(latitude) ||
            longitude < -180.0 || longitude > 180.0 ||
            latitude < -90.0 || latitude > 90.0) {
            throw new IllegalArgumentException(
                "Invalid longitude/latitude"
            );
        }

        Point location = new Point(
            new Position(longitude, latitude)
        );

        stores.insertOne(
            new Document("_id", id)
                .append("location", location)
        );
    }
}
```

Đây là ví dụ Java driver hiện đại; `createIndex` nên được chạy ở migration/setup, không phải trong mỗi HTTP request.

**Chú ý:** caller truyền theo thứ tự `longitude` trước, `latitude` sau. Nếu dữ liệu từ thiết bị hoặc dịch vụ ngoài cung cấp ngược, chuyển đổi ở boundary layer có kiểm soát.

---

## 21. Java Sync Driver: truy vấn bằng Filters.geoWithin

Dữ liệu `geometry` hoặc `location` đã là GeoJSON và index thích hợp:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.geojson.Polygon;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;

public final class GeoWithinService {

    public static void findStoresInside(
            MongoCollection<Document> stores
    ) {
        Polygon searchArea = new Polygon(Arrays.asList(
            new Position(0, 0),
            new Position(4, 0),
            new Position(4, 4),
            new Position(0, 4),
            new Position(0, 0)
        ));

        Bson condition = Filters.geoWithin(
            "location",
            searchArea
        );

        stores.find(condition).forEach(
            doc -> System.out.println(doc.toJson())
        );
    }
}
```

`Filters.geoWithin(fieldName, polygon)` dựng predicate tương ứng với `$geoWithin + $geometry`. Không cần tự viết toàn bộ BSON khi dùng GeoJSON classes.

### 21.1. Kết hợp filter tenant

```java
Bson filter = Filters.and(
    Filters.eq("tenantId", tenantId),
    Filters.eq("status", "ACTIVE"),
    Filters.geoWithin("location", searchArea)
);

stores.find(filter)
    .projection(new Document("_id", 1)
        .append("name", 1))
    .limit(100)
    .forEach(doc -> System.out.println(doc.toJson()));
```

Các biến `tenantId`, `searchArea` được cung cấp từ service và cần validation. `limit(100)` chỉ giới hạn số document trả, **không tự bảo đảm truy vấn rẻ** nếu filter quá rộng hoặc index không phù hợp.

---

## 22. Java Sync Driver: truy vấn bằng Filters.geoIntersects

Tìm các khu vực polygon giao với polygon query:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.geojson.Polygon;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;

public final class GeoIntersectionService {

    public static void findIntersectingAreas(
            MongoCollection<Document> areas
    ) {
        Polygon query = new Polygon(Arrays.asList(
            new Position(0, 0),
            new Position(4, 0),
            new Position(4, 4),
            new Position(0, 4),
            new Position(0, 0)
        ));

        Bson filter = Filters.geoIntersects(
            "geometry",
            query
        );

        areas.find(filter)
            .forEach(doc -> System.out.println(doc.toJson()));
    }
}
```

### 22.1. Java: tìm zone chứa customer Point

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.geojson.Point;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;
import org.bson.conversions.Bson;

public final class DeliveryZoneLookup {

    public static void lookup(
            MongoCollection<Document> zones,
            String tenantId,
            double longitude,
            double latitude
    ) {
        Point customer = new Point(
            new Position(longitude, latitude)
        );

        Bson filter = Filters.and(
            Filters.eq("tenantId", tenantId),
            Filters.eq("active", true),
            Filters.geoIntersects("geometry", customer)
        );

        zones.find(filter).forEach(
            zone -> System.out.println(zone.toJson())
        );
    }
}
```

Ở đây field `geometry` của document là Polygon/MultiPolygon, trong khi đối tượng query là Point. Đó là cách đặt đúng chiều cho bài toán “zone nào chứa customer point”.

Với Java driver, `Filters.geoIntersects` yêu cầu đối tượng hình học phù hợp như `Point` hoặc `Polygon`. Driver chỉ giúp dựng BSON; server mới là nơi đánh giá quan hệ hình học.

---

## 23. Khi không dùng GeoJSON class của Java

Một số ứng dụng đã có dữ liệu GeoJSON như `Document` hoặc nhận shape từ API JSON. Có thể dựng trực tiếp filter BSON:

```java
import org.bson.Document;
import org.bson.conversions.Bson;

Document polygon = new Document("type", "Polygon")
    .append("coordinates", java.util.List.of(
        java.util.List.of(
            java.util.List.of(0.0, 0.0),
            java.util.List.of(4.0, 0.0),
            java.util.List.of(4.0, 4.0),
            java.util.List.of(0.0, 4.0),
            java.util.List.of(0.0, 0.0)
        )
    ));

Bson withinFilter = new Document(
    "location",
    new Document(
        "$geoWithin",
        new Document("$geometry", polygon)
    )
);

Bson intersectsFilter = new Document(
    "geometry",
    new Document(
        "$geoIntersects",
        new Document("$geometry", polygon)
    )
);
```

Không lưu chuỗi `"{type:'Polygon',...}"` rồi truyền vào `$geometry` dưới dạng string. MongoDB cần **BSON object với cấu trúc GeoJSON hợp lệ**.

### 23.1. Khi nhận polygon từ HTTP API

- Giới hạn số vertex/size/depth trước khi gửi MongoDB.
- Không cho phép request tự chỉ định field query hoặc operator khác tùy ý.
- Dùng BSON builders/data structure, không nối JSON query bằng string.
- Validate quyền tenant và khu vực được phép.
- Quy định rõ hệ tọa độ và cách nhập longitude/latitude.
- Bảo vệ pagination, timeout, query memory và số kết quả.

---

## 24. Một use case hoàn chỉnh: tìm delivery zones có giao với vùng sự cố

Giả sử `deliveryZones` lưu các polygon vùng phục vụ; một khu vực đang bị cấm đi lại được phát thành Polygon `incidentArea`.

Mục tiêu: **tìm tất cả zones bị ảnh hưởng, dù chỉ giao một phần**.

```javascript
const incidentArea = {
  type: "Polygon",
  coordinates: [
    [
      [106.70, 10.77],
      [106.73, 10.77],
      [106.73, 10.80],
      [106.70, 10.80],
      [106.70, 10.77]
    ]
  ]
};

db.deliveryZones.find({
  tenantId: "T100",
  status: "ACTIVE",
  geometry: {
    $geoIntersects: {
      $geometry: incidentArea
    }
  }
});
```

Vì câu hỏi là “có phần nào bị ảnh hưởng”, dùng `$geoIntersects`. Nếu dùng `$geoWithin`, các vùng chỉ bị ảnh hưởng một phần sẽ **bị loại** — một lỗi nghiệp vụ nghiêm trọng.

### 24.1. Nếu muốn vùng nằm trọn trong vùng sự cố?

Khi yêu cầu chuyển thành “những zones **bị phủ hoàn toàn** bởi incident polygon”, dùng:

```javascript
db.deliveryZones.find({
  geometry: {
    $geoWithin: {
      $geometry: incidentArea
    }
  }
});
```

Đây là câu hỏi khác, không phải bước tối ưu tùy ý.

### 24.2. Không tự suy ra phần trăm diện tích giao

`$geoIntersects` trả kết quả **có/không**. Nó không trả tỷ lệ diện tích giao, độ dài tuyến bị ảnh hưởng hoặc phần polygon cần cắt.

Nếu muốn “vùng bị ảnh hưởng trên 30% diện tích”, phải dùng công cụ tính giao/diện tích của GIS hoặc một kiến trúc phân tích không gian tương ứng, không chỉ cộng `$geoIntersects` với `$size`.

---

## 25. Use case bản đồ: bounding box thay vì khu vực nghiệp vụ

Frontend thường gửi viewport:

```json
{
  "west": 106.65,
  "south": 10.73,
  "east": 106.75,
  "north": 10.83
}
```

Nếu dataset lưu GeoJSON points, có thể dựng Polygon để tìm điểm trong vùng bản đồ:

```javascript
const viewport = {
  type: "Polygon",
  coordinates: [
    [
      [106.65, 10.73],
      [106.75, 10.73],
      [106.75, 10.83],
      [106.65, 10.83],
      [106.65, 10.73]
    ]
  ]
};

db.stores.find({
  location: {
    $geoWithin: {
      $geometry: viewport
    }
  }
}).limit(200);
```

**Khác biệt giữa viewport và service zone:**

- Viewport là phần bản đồ người dùng đang nhìn; có thể thay đổi liên tục khi pan/zoom.
- Service zone là polygon nghiệp vụ thường được lưu với version và policy.
- Nếu viewport cắt đường đổi ngày, không dựng polygon bằng west/east theo cách đơn giản.
- MongoDB spherical polygon không đồng nhất hoàn toàn với ô viewport pixel của bản đồ theo phép chiếu Web Mercator. Với zoom thấp/vùng rất lớn, cần kiểm chứng hình dạng gần poles/antimeridian.

### 25.1. API có nhiều request khi kéo bản đồ

Không thực hiện full collection scan cho mỗi lần pan một vài pixels. Nên:

1. Dùng `2dsphere` index.
2. Debounce/throttle request ở client.
3. Giới hạn số kết quả và có chiến lược clustering ở zoom thấp.
4. Cache theo viewport/grid khi hợp lý.
5. Dùng query predicate/filters theo category/status.
6. Đo p95/p99 latency, số docs scanned và response bytes.

`limit(200)` giới hạn response, không thay index hay query planning.

---

## 26. Use case: kiểm tra tuyến vận chuyển có đi qua vùng cấm

Dữ liệu:

```javascript
{
  _id: "ROUTE-204",
  tenantId: "T100",
  route: {
    type: "LineString",
    coordinates: [
      [106.68, 10.75],
      [106.71, 10.78],
      [106.74, 10.81]
    ]
  }
}
```

Predicate:

```javascript
db.routes.find({
  tenantId: "T100",
  route: {
    $geoIntersects: {
      $geometry: incidentArea
    }
  }
});
```

Khi cần biết tuyến **nằm toàn bộ trong** vùng cho phép:

```javascript
db.routes.find({
  tenantId: "T100",
  route: {
    $geoWithin: {
      $geometry: allowedArea
    }
  }
});
```

Hai câu này khác nhau về chính sách:

- **Chạm hoặc đi qua vùng cấm** → loại/đánh dấu route bằng `$geoIntersects`.
- **Tuyến phải hoàn toàn nằm trong vùng cho phép** → dùng `$geoWithin`.

Vì dữ liệu GPS thưa, một LineString nối thẳng giữa hai điểm có thể đi qua khu vực mà xe thực tế không đi. Trong bài toán an toàn, nên dùng hình học tuyến thực và quy tắc khoảng đệm thích hợp.

---

## 27. Các giới hạn khi chạy trên sharded cluster

Trong sharded cluster:

- Có thể tạo `2dsphere` index trên collection đã shard.
- Geospatial index **không thể làm shard key**.
- `mongos` định tuyến theo shard key và metadata placement.
- Query chỉ có geospatial predicate nhưng **thiếu shard key filter** có thể cần truy cập nhiều shards.
- Index `2dsphere` giúp xử lý địa lý **trên từng shard**, không tự bảo đảm query chỉ chạm một shard.

Ví dụ shard key theo `tenantId` (chỉ minh họa thiết kế):

```javascript
db.places.find({
  tenantId: "T100",
  location: {
    $geoWithin: {
      $geometry: viewport
    }
  }
});
```

Điều kiện `tenantId` có thể giúp router giảm số shards cần hỏi, còn `2dsphere` index giúp xử lý geometry trên shard đã target.

Không dùng direct query vào một shard riêng để thay cho `mongos` khi cần câu trả lời toàn cluster; có thể bỏ sót dữ liệu ở shards khác.

---

## 28. Dữ liệu địa lý không hợp lệ hoặc thiếu location

Một số document có:

```javascript
{ _id: "X1", name: "No location" }
{ _id: "X2", location: null }
{ _id: "X3", location: [] }
```

Với `2dsphere` sparse semantics, các document này không có entry index từ field địa lý. Chúng cũng không thể được xem là có hình học hợp lệ bên trong vùng query.

Nếu cần dashboard “bao nhiêu điểm đã có tọa độ?” và “bao nhiêu điểm chưa xác định vị trí?”, đây là **hai bài toán**:

```javascript
// Những document có trường location:
db.places.countDocuments({
  location: {
    $exists: true
  }
});

// Những document có vị trí thực sự khớp vùng:
db.places.countDocuments({
  location: {
    $geoWithin: {
      $geometry: viewport
    }
  }
});
```

`$exists: true` **không chứng minh** field chứa GeoJSON hợp lệ: nó vẫn có thể là null hoặc dữ liệu hỏng. Có thể yêu cầu `location.type: "Point"` và validation/schema strict nếu domain đảm bảo chuẩn.

### 28.1. Không trộn các coordinate conventions

Các dạng:

```javascript
{ loc: [106.70, 10.78] }                 // legacy pair
{ loc: { type: "Point", coordinates: [106.70, 10.78] } } // GeoJSON
{ lat: 10.78, lon: 106.70 }             // hai scalar riêng
```

không phải lúc nào cũng có cùng behavior và index support. Đặc biệt, chỉ lưu hai scalar `lat`/`lon` rồi tạo compound index B-tree không biến chúng thành một `2dsphere` geometry field.

Hãy chọn schema rõ ràng và migrate nhất quán.

---

## 29. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Query không tìm được điểm rõ ở gần | Đảo longitude/latitude | Kiểm tra `[lon,lat]` và validation. |
| Polygon báo lỗi | Thiếu lớp mảng `coordinates` | GeoJSON Polygon cần mảng các rings. |
| Polygon không hợp lệ | Ring chưa đóng hoặc tự cắt | Đóng ring, validate GIS. |
| `$geoWithin` bỏ qua vùng chạm một phần | Bạn đang yêu cầu chứa **toàn bộ** | Dùng `$geoIntersects` nếu chỉ cần giao. |
| `$geoIntersects` trả vùng lớn bao phủ query | Đây vẫn là giao nhau | Cần `$geoWithin` nếu muốn nằm trọn trong. |
| Dùng `$geoWithin` tìm zone chứa Point không ra | Đặt ngược chiều hình học | Query polygon field bằng `$geoIntersects` với Point. |
| Vùng biên cho kết quả bất ngờ | Degenerate geometry | Không dựa vào guarantee biên tuyệt đối; test/policy riêng. |
| Dùng `$box` trên GeoJSON `2dsphere` kỳ vọng spherical | `$box` legacy planar | Dùng `$geometry` Polygon cho GeoJSON. |
| `$geoIntersects` không dùng `2d` index | Chỉ `2dsphere` hỗ trợ operator | Tạo index spherical đúng field. |
| Query chậm | Thiếu geospatial index, vùng quá rộng | Tạo `2dsphere`, filter sớm, explain. |
| Query không sort gần nhất | Operator không tính/sort khoảng cách | Dùng `$near`/`$geoNear`. |
| Circle bán kính sai lớn | Truyền km hoặc mét trực tiếp cho `$centerSphere` | Đổi sang radians: km / 6378.1. |
| Polygon lớn cho kết quả đối ngược | CRS mặc định diễn giải complement | Xét strict winding CRS cho single-ring big polygon. |
| Không tìm được near antimeridian | Xử lý longitude như trục XY liên tục | Thiết kế GeoJSON spherical/split vùng. |
| Đã tạo index nhưng insert fail | Field có string hoặc geometry sai kiểu | Dọn/migrate dữ liệu, validate đầu vào. |
| Có Geo index nhưng query nhiều shard | Thiếu shard key filter | Kết hợp shard key và 2dsphere theo access patterns. |
| `$geoIntersects` trả quá nhiều vùng | Bất kỳ giao nào cũng match | Thêm filter nghiệp vụ, cần diện tích giao thì dùng GIS khác. |
| Sắp xếp không ổn định | Không có `sort` | Thêm sort rõ và phân trang. |
| Kết quả bị nhân đôi ở vùng chồng | Nhiều zone cùng match | Thêm precedence/priority và policy. |
| Polygon chứa hole nhưng vẫn chọn điểm trong hole | Sai mảng rings hoặc bỏ hole | Validate GeoJSON Polygon có inner rings. |
| Query vùng cực có kết quả khác phẳng | `2dsphere` spherical | Không thay bằng `2d` một cách tùy tiện. |

---

## 30. Bài tập thực hành có đáp án

### Bài 1 — Chọn toán tử

Có collection `stores` lưu Point; muốn tìm các cửa hàng trong một Polygon quận. Dùng gì?

**Đáp án:** `$geoWithin` với `$geometry` Polygon trên field Point. `$geoIntersects` cũng có thể tìm Point có giao nhưng `$geoWithin` diễn đạt trực tiếp nghiệp vụ “điểm nằm trong vùng”.

### Bài 2 — Vùng giao một phần

Collection `deliveryZones` lưu Polygon; một vùng sự cố cắt 20% polygon zone. Dùng gì?

**Đáp án:** `$geoIntersects`; `$geoWithin` sẽ bỏ zone vì nó không nằm trọn trong vùng sự cố.

### Bài 3 — Vùng bao phủ query

Một Polygon A lớn hơn và bao chứa toàn bộ Polygon Q. Có match `$geoWithin` khi field lưu A, query Q không?

**Đáp án:** Không; A không nằm trong Q. `$geoIntersects` có match vì A và Q giao nhau.

### Bài 4 — Truy vấn ngược

Collection lưu polygon vùng giao hàng. Query là Point vị trí khách. Muốn tìm những vùng chứa Point đó?

**Đáp án:** Dùng `$geoIntersects` trên field Polygon với `$geometry` là Point.

### Bài 5 — Tọa độ

API trả latitude=10.78, longitude=106.70. GeoJSON Point đúng?

**Đáp án:**

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.78]
}
```

### Bài 6 — Ring closure

Polygon có:

```javascript
coordinates: [
  [[0, 0], [4, 0], [4, 4], [0, 4]]
]
```

Thiếu gì?

**Đáp án:** Lặp lại `[0,0]` ở cuối ring để đóng polygon.

### Bài 7 — LineString

Một đường đi từ [-1,2] tới [5,2], đi xuyên Polygon từ [0,0] tới [4,4]. `$geoWithin` và `$geoIntersects` khác gì?

**Đáp án:** `$geoWithin` không match vì tuyến có phần ngoài; `$geoIntersects` match vì tuyến đi qua interior.

### Bài 8 — Vùng có lỗ

Point [5,5] nằm trong outer ring [0,0]–[10,10] nhưng nằm trong inner hole [4,4]–[6,6]. Có thuộc polygon không?

**Đáp án:** Không thuộc phần diện tích được polygon biểu diễn, nếu rings được định nghĩa đúng theo GeoJSON.

### Bài 9 — $centerSphere

Tìm trong bán kính 10 km với `$centerSphere`, radius truyền vào là gì?

**Đáp án:** Khoảng `10 / 6378.1` radians, không phải 10 hoặc 10000.

### Bài 10 — Index

Muốn dùng `$geoIntersects` hiệu quả với Polygon GeoJSON nên tạo index gì?

**Đáp án:** `{ geometry: "2dsphere" }`. Server có thể chạy không index nhưng `2d` không hỗ trợ tối ưu `$geoIntersects`.

### Bài 11 — Sharding

Có `2dsphere` index trên `location`, query chỉ `location` mà không có shard key filter. Có chắc chỉ truy cập một shard?

**Đáp án:** Không. Router có thể cần hỏi nhiều shard; index địa lý hoạt động trên các shards được target.

### Bài 12 — Boundary

Một LineString chạm đúng một vertex của Polygon nhưng không đi vào interior. Có được MongoDB bảo đảm `$geoIntersects` match không?

**Đáp án:** Không; đây là trường hợp suy biến mà MongoDB không bảo đảm theo tài liệu. Cần policy/test hoặc GIS chuyên dụng cho yêu cầu exact boundary semantics.

### Bài 13 — Big polygon

Một single-ring Polygon bao phủ 75% diện tích trái đất và query mặc định trả phần 25% còn lại. Vì sao?

**Đáp án:** CRS mặc định có behavior complementary geometry cho polygon lớn hơn một bán cầu. Với single-ring lớn, dùng custom MongoDB strict winding CRS phù hợp.

### Bài 14 — Sort gần nhất

Query `$geoWithin` trả 100 points. Chúng có được tự sort theo khoảng cách đến tâm vùng không?

**Đáp án:** Không. Nếu cần gần nhất trước, dùng `$near`/`$geoNear` với index và đơn vị đúng.

### Bài 15 — Legacy vs GeoJSON

`$box` với `2d` có thay thế hoàn toàn GeoJSON Polygon với `2dsphere` cho khu vực trên trái đất không?

**Đáp án:** Không. `$box` tính theo planar grid; `$geometry` với `2dsphere` sử dụng spherical geometry.

### Bài 16 — Kết quả chứa toàn bộ polygon

Một business rule yêu cầu tài sản nằm **trọn trong** vùng đăng ký. Document lưu Polygon footprint của tài sản.

**Đáp án:** Dùng `$geoWithin`. Nếu dùng `$geoIntersects`, tài sản chỉ chồng lấn một phần cũng được nhận.

### Bài 17 — Kích thước kết quả

API có filter Polygon rộng gần toàn bộ khu vực, `limit(20)`. Có nghĩa query chắc chắn rẻ?

**Đáp án:** Không. Index và độ chọn lọc, filter bổ sung, sort/pagination, phần giao hình học và chi phí tài nguyên vẫn quan trọng.

### Bài 18 — Bản đồ có tọa độ thiếu

Một record không có `location`. Có nên tự coi nó nằm ngoài mọi vùng?

**Gợi ý:** Về query nó không match vùng, nhưng nghiệp vụ cần trạng thái “chưa biết vị trí” riêng, không đánh đồng với “xác nhận đang ở ngoài”.

---

## 31. Checklist trước khi đưa query địa lý vào production

1. Field lưu Point, LineString hay Polygon?
2. Đang cần **chứa toàn bộ** hay **chỉ cần giao**?
3. Thứ tự tọa độ đã là `[longitude,latitude]`?
4. CRS có phải WGS84/EPSG:4326 hợp lệ?
5. GeoJSON Polygon có đúng mảng rings, đóng ring và không tự cắt?
6. Có lỗ hoặc MultiPolygon cần bảo toàn không?
7. Có vùng lớn hơn nửa bán cầu/antimeridian/cực không?
8. Có quy tắc riêng cho Point nằm đúng biên không?
9. Có `2dsphere` index đúng field và datatype?
10. Có dữ liệu sai kiểu/null/missing cần làm sạch không?
11. Truy vấn có filter tenant/status/category để giảm dữ liệu?
12. Có compound index phù hợp query shapes không?
13. Nếu sharded cluster, có shard key predicate hỗ trợ targeting không?
14. Đã dùng `explain("executionStats")` để xem docs/keys examined?
15. Có cần sort kết quả, pagination và limit?
16. Đang tìm khoảng cách hay quan hệ hình học? Đã chọn đúng toán tử?
17. `$centerSphere` đã đổi bán kính sang radians?
18. Có cần tính phần trăm diện tích hoặc độ dài giao thay vì boolean match không?
19. Có kiểm thử các tình huống polygon chồng, holes và boundary không?
20. Có validate hình học do user gửi và giới hạn độ phức tạp query không?
21. Tài liệu version MongoDB/Java driver có khớp môi trường triển khai?
22. API có giới hạn latency, tài nguyên và số request khi pan/zoom bản đồ không?

Sơ đồ quyết định:

```text
Dữ liệu MongoDB có hình học
              |
              v
Document lưu Point hay Polygon/LineString?
              |
              v
Mục tiêu của truy vấn là gì?
       /            |              \
      v             v               v
Nằm trọn       Chỉ cần giao      Gần nhất/
trong vùng       vùng           khoảng cách
      |             |               |
      v             v               v
 $geoWithin   $geoIntersects     $near /
                                    $geoNear
      \             /
       \           /
        v         v
     GeoJSON hợp lệ?
           |
           v
     2dsphere index
           |
           v
  Filter tenant/status, explain
           |
           v
   Kiểm tra boundary và
   ràng buộc nghiệp vụ
```

---

## 32. Tài liệu chính thức MongoDB

- [`$geoWithin` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/query/geowithin/): định nghĩa chứa hoàn toàn, GeoJSON, legacy shapes, index, degenerate geometry và big polygons.
- [`$geoIntersects` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/query/geointersects/): định nghĩa giao nhau, GeoJSON, index, degenerate geometry và strict winding CRS.
- [`$geometry` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/query/geometry/): EPSG:4326, cấu trúc GeoJSON và thứ tự longitude/latitude.
- [Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/): so sánh toán tử không gian và hệ tọa độ.
- [2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/): index spherical, sparse behavior, compound indexes.
- [Geospatial Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/restrictions/): shard key, supported data types, covered query.
- [Query for Locations Bound by a Polygon](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/query/geojson-bound-by-polygon/): ví dụ Polygon và cách đóng ring.
- [`$box`](https://www.mongodb.com/docs/manual/reference/operator/query/box/): bounding box legacy trên mặt phẳng.
- [`$polygon`](https://www.mongodb.com/docs/manual/reference/operator/query/polygon/): planar legacy polygon.
- [`$center`](https://www.mongodb.com/docs/manual/reference/operator/query/center/): planar circle.
- [`$centerSphere`](https://www.mongodb.com/docs/manual/reference/operator/query/centersphere/): hình tròn spherical, bán kính radians.
- [`$near`](https://www.mongodb.com/docs/manual/reference/operator/query/near/): truy vấn gần và sắp xếp theo khoảng cách.
- [`$geoNear`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/): aggregation cho khoảng cách.
- [Java Sync Driver — Search Geospatially](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/geo/): `Filters.geoWithin`, GeoJSON classes và index qua Java.
- [MongoDB GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/): các kiểu hình học và quy tắc lưu trữ.
- [GeoJSON RFC 7946](https://www.rfc-editor.org/rfc/rfc7946): cấu trúc ring, polygon và các yêu cầu GeoJSON.

**Lưu ý phiên bản:** Các hành vi index/geospatial và chi tiết của driver có thể thay đổi theo MongoDB server/FCV/Java driver. Hãy đối chiếu tài liệu của phiên bản đang vận hành, đặc biệt khi làm việc với legacy coordinates, big polygons hoặc dữ liệu bản đồ nhập từ hệ GIS khác.

## 33. Kết luận

`$geoWithin` và `$geoIntersects` khác nhau ở quan hệ mà chúng kiểm tra:

- **`$geoWithin`:** toàn bộ hình học trong document phải nằm bên trong vùng query. Hữu ích cho tài sản nằm trọn trong khu vực, tuyến đường hoàn toàn nằm trong vùng cho phép hoặc tìm Point nằm trong Polygon.
- **`$geoIntersects`:** chỉ cần hình học document và query có phần giao. Hữu ích để tìm các vùng giao nhau, tuyến đường đi qua khu vực, hoặc tìm những polygon vùng phục vụ chứa một customer Point.

Với dữ liệu trên trái đất, nên lưu **GeoJSON đúng chuẩn**, dùng tọa độ **[longitude, latitude]** và chỉ mục **`2dsphere`** khi truy vấn cần hiệu năng. Đối với bán kính dùng `$centerSphere`, phải chuyển khoảng cách sang **radians**. Cần phân biệt sự khác nhau giữa các legacy planar shapes và GeoJSON spherical geometry.

Cuối cùng, các trường hợp **đụng cạnh/đỉnh, polygon có lỗ, polygon quá lớn, đường đổi ngày và đối tượng không có tọa độ** đều có thể thay đổi ý nghĩa nghiệp vụ. Hãy validate hình học, kiểm tra query plan, bổ sung filter và viết test cho biên theo yêu cầu thật.

**`$geoWithin` trả lời “nằm trọn trong không?”, còn `$geoIntersects` trả lời “có giao với nhau không?”. Hiểu đúng câu hỏi trước khi viết toán tử giúp tránh sai dữ liệu dù truy vấn chạy rất nhanh.**
