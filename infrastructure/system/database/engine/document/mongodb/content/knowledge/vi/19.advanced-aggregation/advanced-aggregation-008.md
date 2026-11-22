# Bổ sung khoảng trống với `$densify`, `$fill` và điều kiện hỗ trợ trong MongoDB

## 1. Hai kiểu khoảng trống khác nhau

Trong dữ liệu theo thời gian hoặc theo số thứ tự, “thiếu dữ liệu” có hai nghĩa quan trọng:

- **Thiếu cả document tại một mốc**: cảm biến có bản ghi 00:00 và 02:00 nhưng không có bản ghi 01:00.
- **Có document nhưng field giá trị đang `null` hoặc bị thiếu**: bản ghi 02:00 tồn tại với `temperature: null`.

MongoDB có hai aggregation stage để giải quyết đúng hai vấn đề này:

| Stage | Tác dụng | Không tự làm được |
| --- | --- | --- |
| **`$densify`** | Sinh thêm document cho các giá trị số hoặc thời gian còn thiếu theo bước nhảy đã chọn. | Không tự ước tính giá trị các field đo như nhiệt độ, doanh thu. |
| **`$fill`** | Điền field null/missing bằng giá trị cố định, LOCF hoặc nội suy tuyến tính. | Không tự tạo document ở timestamp chưa tồn tại. |

Ví dụ:

```text
Dữ liệu đầu:
00:00 -> temperature = 10
01:00 -> không có document
02:00 -> temperature = null
03:00 -> không có document
04:00 -> temperature = 18

Sau $densify từng giờ:
00:00 -> 10
01:00 -> field temperature thiếu
02:00 -> null
03:00 -> field temperature thiếu
04:00 -> 18

Sau $fill linear:
00:00 -> 10
01:00 -> 12
02:00 -> 14
03:00 -> 16
04:00 -> 18
```

Các giá trị 12, 14, 16 là **ước lượng**, không phải phép đo thực. Dữ liệu đã được tạo hoặc nội suy cần được phân biệt với dữ liệu gốc khi dùng cho monitoring, hóa đơn, báo cáo hoặc kiểm toán.

> **Quy tắc chính:** Nếu thiếu **mốc/document**, dùng `$densify`. Nếu thiếu **giá trị trong document**, dùng `$fill`. Nếu thiếu cả hai, thường dùng `$densify` rồi `$fill`, với chính sách rõ ràng về cách suy diễn giá trị.

## 2. Điều kiện hỗ trợ theo phiên bản MongoDB

| Tính năng | Phiên bản đầu tiên hoặc thay đổi | Ý nghĩa |
| --- | --- | --- |
| `$densify` | MongoDB **5.1** | Sinh các mốc numeric/Date bị thiếu. |
| `$fill` | MongoDB **5.3** | Điền giá trị null/missing trong chuỗi. |
| `$locf` window expression | MongoDB **5.2** | Mang giá trị không-null gần nhất trước đó trong `$setWindowFields`. |
| `$linearFill` window expression | MongoDB **5.3** | Nội suy trong `$setWindowFields`. |
| `$densify` với bounds bằng nhau | **8.0** | `[x, x]` là khoảng rỗng; trước 8.0 có thể sinh mốc x. |
| `$fill` linear: cùng sort key nhưng **khác partition** | **8.0.20** | Các partition khác nhau được phép có sort key giống nhau; trong cùng một partition vẫn cấm trùng. |
| `$densify.field` chia sẻ prefix với `partitionByFields` | **8.1** | Validation chặt hơn và trả lỗi với đường dẫn xung đột. |

Vì `$fill` xuất hiện từ 5.3, **server 5.1 hoặc 5.2 không đủ để chạy một pipeline dùng cả `$densify` và `$fill`**. Phiên bản Java driver không thay thế khả năng của server.

Kiểm tra:

```javascript
db.version();
```

Khi được cấp quyền phù hợp, có thể xem feature compatibility version (FCV):

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Trong hệ managed service, có thể lấy thông tin phiên bản/FCV từ công cụ quản trị thay vì cấp quyền admin cho tài khoản ứng dụng. Hãy đối chiếu phiên bản cụ thể trước khi triển khai, nhất là khi dùng những thay đổi 8.0, 8.0.20 hoặc 8.1.

## 3. Bộ dữ liệu thực hành

Giả sử collection thử nghiệm `sensorReadings207` chưa có các ID dưới đây:

```javascript
db.sensorReadings207.insertMany([
  {
    _id: "A-00",
    sensorId: "A",
    ts: ISODate("2026-11-14T00:00:00Z"),
    temperature: 10
  },
  {
    _id: "A-02",
    sensorId: "A",
    ts: ISODate("2026-11-14T02:00:00Z"),
    temperature: null
  },
  {
    _id: "A-04",
    sensorId: "A",
    ts: ISODate("2026-11-14T04:00:00Z"),
    temperature: 18
  },
  {
    _id: "A-06",
    sensorId: "A",
    ts: ISODate("2026-11-14T06:00:00Z"),
    temperature: 24
  },
  {
    _id: "B-01",
    sensorId: "B",
    ts: ISODate("2026-11-14T01:00:00Z"),
    temperature: 100
  },
  {
    _id: "B-03",
    sensorId: "B",
    ts: ISODate("2026-11-14T03:00:00Z"),
    temperature: 120
  },
  {
    _id: "B-06",
    sensorId: "B",
    ts: ISODate("2026-11-14T06:00:00Z"),
    temperature: 150
  }
]);
```

Dữ liệu đầu:

| Sensor | `ts` (UTC) | `temperature` |
| --- | --- | ---: |
| A | 00:00 | 10 |
| A | 02:00 | null |
| A | 04:00 | 18 |
| A | 06:00 | 24 |
| B | 01:00 | 100 |
| B | 03:00 | 120 |
| B | 06:00 | 150 |

Các mốc **thiếu document**: A thiếu 01, 03, 05; B thiếu 02, 04, 05; riêng B còn không có quan sát tại 00:00.

Để xem theo thứ tự ổn định:

```javascript
db.sensorReadings207.find(
  {},
  { sensorId: 1, ts: 1, temperature: 1 }
).sort({ sensorId: 1, ts: 1 });
```

Nếu chạy lại `insertMany` có thể nhận lỗi duplicate `_id`; hãy dùng collection thử nghiệm trống, không xóa dữ liệu production chỉ để chạy ví dụ.

---

## 4. Cú pháp `$densify`

Dạng khái quát:

```javascript
{
  $densify: {
    field: "ts",
    partitionByFields: ["sensorId"],
    range: {
      step: 1,
      unit: "hour",
      bounds: "partition"
    }
  }
}
```

| Thuộc tính | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| `field` | Có | Field chứa BSON Date hoặc số cần làm dày. |
| `partitionByFields` | Không | Danh sách field tạo nhóm độc lập. Bỏ đi sẽ có một partition chung. |
| `range` | Có | Các quy tắc sinh mốc. |
| `range.step` | Có | Khoảng cách số học giữa các mốc, cần là bước tăng hợp lệ. |
| `range.unit` | Có với Date; không dùng với numeric | Đơn vị thời gian. |
| `range.bounds` | Có | `"full"`, `"partition"` hoặc `[lower, upper]`. |

### 4.1. Các đơn vị ngày giờ được hỗ trợ

Nếu field là Date, giá trị `unit` thuộc tập:

```text
millisecond, second, minute, hour, day,
week, month, quarter, year
```

Khi có `unit`, `step` phải là **số nguyên**. Đối với field số không khai báo `unit`; `step` có thể là giá trị numeric phù hợp.

```javascript
// Date: bổ sung mốc mỗi 15 phút.
{
  $densify: {
    field: "ts",
    range: {
      step: 15,
      unit: "minute",
      bounds: "partition"
    }
  }
}

// Numeric: bổ sung số thứ tự cách nhau 1.
{
  $densify: {
    field: "sequence",
    range: {
      step: 1,
      bounds: "partition"
    }
  }
}
```

Không dùng `step: 0` hoặc bước âm với ý định sinh chuỗi đảo ngược. Muốn trả kết quả theo thứ tự giảm dần, sinh mốc bằng bước dương rồi dùng `$sort: { ts: -1 }` ở cuối.

---

## 5. `bounds: "partition"`: tự làm dày trong từng nhóm

```javascript
db.sensorReadings207.aggregate([
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "partition"
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: 1,
      ts: 1,
      temperature: 1
    }
  }
]);
```

`partitionByFields: ["sensorId"]` giữ dữ liệu A và B thành hai chuỗi độc lập.

Với `"partition"`:

- Sensor A có miền quan sát **00:00–06:00**.
- Sensor B có miền quan sát **01:00–06:00**.

MongoDB sinh các mốc còn thiếu của từng miền:

```javascript
// Mốc sinh thêm cho A:
{ sensorId: "A", ts: ISODate("2026-11-14T01:00:00Z") }
{ sensorId: "A", ts: ISODate("2026-11-14T03:00:00Z") }
{ sensorId: "A", ts: ISODate("2026-11-14T05:00:00Z") }

// Mốc sinh thêm cho B:
{ sensorId: "B", ts: ISODate("2026-11-14T02:00:00Z") }
{ sensorId: "B", ts: ISODate("2026-11-14T04:00:00Z") }
{ sensorId: "B", ts: ISODate("2026-11-14T05:00:00Z") }
```

Các document tổng hợp trên **chưa có `temperature`**. Document A-02 vốn tồn tại với `temperature: null` vẫn tồn tại; `$densify` không tự điền field đo.

Các document do `$densify` sinh thường chỉ có mốc và key partition cần thiết; chúng không tự kế thừa `_id`, metadata thiết bị, giá trị đo hay toàn bộ field từ những document hàng xóm.

### 5.1. Không gộp nhiều lần đo trong một bucket

Nếu sensor có hai lần đo `01:10` và `01:40`, `$densify` không tự biến chúng thành một điểm `01:00`. Muốn báo cáo mỗi giờ một mốc, hãy chuẩn hóa bằng `$dateTrunc` và tổng hợp theo bucket trước khi densify.

### 5.2. `partition` không tự sinh mốc ngoài khoảng quan sát

Nếu B chưa từng có dữ liệu trước 01:00, `bounds: "partition"` không tự tạo B 00:00. Nếu báo cáo đòi đủ khung giờ 00–06 cho mọi sensor, cần dùng `bounds: "full"` hoặc explicit bounds thích hợp.

---

## 6. `bounds: "full"`: cùng miền chung

Khi có nhiều partition, `"full"` áp dụng miền đầy đủ của field densify trên toàn bộ tập đầu vào, cho phép sinh mốc trong mỗi partition trên miền chung.

```javascript
db.sensorReadings207.aggregate([
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "full"
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  }
]);
```

Với dữ liệu mẫu, miền chung bắt đầu ở **A 00:00** và kết thúc ở **06:00**. Vì vậy B có thể được sinh thêm mốc 00:00, khác với `bounds: "partition"`.

| Nhóm | `partition` | `full` |
| --- | --- | --- |
| A | 00:00 tới 06:00 | Trong miền chung 00:00 tới 06:00 |
| B | 01:00 tới 06:00 | Trong miền chung 00:00 tới 06:00 |

**Đừng nhầm `"full"` với “tới hiện tại” hoặc “tới hết kỳ báo cáo”.** Nó dựa trên dữ liệu đi vào stage. Nếu một `$match` trước đó rút gọn đầu vào thì miền chung cũng thay đổi.

### 6.1. Rủi ro sinh quá nhiều tài liệu

Với hàng nghìn thiết bị, nếu một thiết bị có lịch sử nhiều năm còn một thiết bị chỉ vừa hoạt động, `bounds: "full"` có thể mở rộng cả thiết bị mới lên miền dài. Điều đó làm số mốc tạo mới tăng mạnh và có thể mang ý nghĩa sai: mốc trước khi thiết bị được kích hoạt không nhất thiết là “bị mất dữ liệu”.

Nên chọn `"full"` khi yêu cầu thật sự là so sánh các nhóm trên cùng trục thời gian, không chỉ vì dễ viết.

---

## 7. Explicit bounds: `[lower, upper]`

Có thể khai báo giới hạn cụ thể:

```javascript
const start = ISODate("2026-11-14T00:00:00Z");
const end   = ISODate("2026-11-14T07:00:00Z");

db.sensorReadings207.aggregate([
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: [start, end]
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  }
]);
```

Quy tắc quan trọng:

- Lower bound **inclusive**: mốc `start` có thể được sinh.
- Upper bound **exclusive**: mốc `end` không được sinh chỉ vì nằm ở giới hạn trên.
- Mốc sinh bắt đầu từ lower bound, không phụ thuộc mốc đầu tiên đã có trong dữ liệu.
- Kiểu dữ liệu của bounds phải tương ứng với kiểu field: Date cho Date, numeric cho numeric.
- **Document nguồn nằm ngoài bounds không bị `$densify` tự động loại bỏ.**

Với `[00:00, 07:00)` và bước một giờ, các mốc cần có là 00, 01, 02, 03, 04, 05, 06. Không sinh 07:00 vì upper bound exclusive.

### 7.1. Muốn giới hạn kết quả, thêm `$match`

```javascript
db.sensorReadings207.aggregate([
  {
    $match: {
      ts: {
        $gte: start,
        $lt: end
      }
    }
  },
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: [start, end]
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  }
]);
```

Nếu cần dùng một quan sát ngay **trước `start`** làm điểm neo cho LOCF, không nên `$match` quá sớm đến mức loại luôn quan sát đó. Phải thiết kế cách lấy điểm neo hoặc mở rộng khoảng đọc hợp lý.

### 7.2. Trường hợp hai bounds bằng nhau

```javascript
{
  $densify: {
    field: "sequence",
    range: {
      step: 1,
      bounds: [10, 10]
    }
  }
}
```

- **Từ MongoDB 8.0**: đây là khoảng rỗng; không sinh thêm document.
- **Trước 8.0**: hành vi với bounds bằng nhau có thể sinh document ở 10 nếu chưa tồn tại.

Nếu cần tạo một slot, dùng phạm vi có độ rộng đúng một bước như `[10, 11]`, thay vì dựa vào hành vi khác nhau giữa các phiên bản.

---

## 8. `$densify` với trường số

Collection có số thứ tự:

```javascript
db.sequence207.insertMany([
  { _id: "X1", channel: "X", seq: 1, value: 100 },
  { _id: "X3", channel: "X", seq: 3, value: 140 },
  { _id: "X5", channel: "X", seq: 5, value: 180 },
  { _id: "Y2", channel: "Y", seq: 2, value: 50 },
  { _id: "Y4", channel: "Y", seq: 4, value: 70 }
]);
```

Pipeline:

```javascript
db.sequence207.aggregate([
  {
    $densify: {
      field: "seq",
      partitionByFields: ["channel"],
      range: {
        step: 1,
        bounds: "partition"
      }
    }
  },
  {
    $sort: {
      channel: 1,
      seq: 1
    }
  }
]);
```

Các document được thêm:

```javascript
{ channel: "X", seq: 2 }
{ channel: "X", seq: 4 }
{ channel: "Y", seq: 3 }
```

Không khai báo `unit` vì `seq` là numeric, không phải Date.

### 8.1. Bước số thập phân

Với `step: 0.1`, các giá trị Double có thể chịu sai số biểu diễn nhị phân. Nếu cần giá trị thập phân chính xác hoặc mốc có độ chính xác tuyệt đối, nên thiết kế dạng integer scaled units hoặc Decimal128 phù hợp và kiểm thử trên phiên bản đang chạy. Không tạo khoảng rất rộng với step cực nhỏ: chi phí sinh document có thể bùng nổ.

---

## 9. Những giới hạn của `$densify`

### 9.1. Kiểu dữ liệu

Field densify phải chứa giá trị số hoặc Date phù hợp. Nếu là Date nhưng không khai báo `unit`, stage báo lỗi. Nếu là numeric nhưng khai báo `unit`, stage cũng báo lỗi. Không giả định chuỗi ISO date tự được chuyển thành BSON Date.

Document không có field densify có thể đi qua pipeline không đổi; stage không có đủ thông tin để tự gán timestamp cho document vốn không có timestamp.

### 9.2. Trường partition

Tên field trong `partitionByFields` phải là tên field hợp lệ, không bắt đầu bằng `$`. `field` cũng không được bắt đầu bằng `$`.

**Từ MongoDB 8.1**, nếu `field` trùng hoặc có quan hệ tiền tố với một field trong `partitionByFields` thì stage báo lỗi, chẳng hạn:

```javascript
// Đường dẫn xung đột từ MongoDB 8.1:
{
  $densify: {
    field: "timestamp",
    partitionByFields: ["timestamp.hours"],
    range: {
      step: 1,
      unit: "hour",
      bounds: "partition"
    }
  }
}
```

Giải pháp: tách đường field cần densify (`timestamp`) khỏi field định danh partition (`sensorId`, `siteId`).

### 9.3. Giới hạn số document sinh

MongoDB giới hạn số document do `$densify` tạo ra qua tham số server `internalQueryMaxAllowedDensifyDocs`. Theo tài liệu chính thức, giới hạn mặc định là **500.000 document sinh thêm**; vượt giới hạn sẽ báo lỗi.

Không nên xem việc tăng tham số nội bộ này là giải pháp đầu tiên. Việc tăng còn phụ thuộc quyền quản trị/managed service và **không loại bỏ CPU, RAM, I/O, network** tiêu tốn khi sinh nhiều document. Ưu tiên giảm thời gian, tăng độ lớn step, chia batch và giảm số partition.

### 9.4. Thứ tự đầu ra

`$densify` **không bảo đảm output đã sort**. Nếu downstream yêu cầu thứ tự, thêm `$sort` tường minh hoặc dùng `sortBy` thích hợp trong `$fill`. Nếu API yêu cầu mốc tăng dần, đặt `$sort` ở cuối pipeline.

---

## 10. Cú pháp `$fill`

`$fill` điền các field `null` hoặc missing trong những document đi qua pipeline:

```javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { ts: 1 },
    output: {
      temperature: { method: "linear" },
      status: { method: "locf" },
      requestCount: { value: 0 }
    }
  }
}
```

| Thuộc tính | Điều kiện | Tác dụng |
| --- | --- | --- |
| `output` | Bắt buộc | Danh sách field cần điền. |
| `output.<field>.value` | Một lựa chọn | Dùng hằng số hoặc một expression để điền. |
| `output.<field>.method` | Một lựa chọn | Chỉ nhận `"linear"` hoặc `"locf"`. |
| `sortBy` | Bắt buộc khi có method | Thứ tự dùng tìm giá trị trước/sau. |
| `partitionBy` | Tùy chọn | Biểu thức tạo khóa nhóm. |
| `partitionByFields` | Tùy chọn | Danh sách field tạo khóa nhóm. |

`partitionBy` và `partitionByFields` **không dùng đồng thời**. Nếu bỏ cả hai, toàn bộ document được xem như **một partition**, dễ làm trộn dữ liệu các thiết bị khác nhau.

### 10.1. `$fill` không tạo document mới

```javascript
db.sensorReadings207.aggregate([
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "linear" }
      }
    }
  }
]);
```

Pipeline có thể điền A-02 vốn tồn tại với temperature null, nhưng **không sinh A-01, A-03 hay A-05**. Cần `$densify` nếu muốn có những mốc đó.

### 10.2. `$fill` chỉ thay giá trị null/missing

Một field đã có giá trị không-null như `temperature: 18` thường được giữ lại, không bị ghi đè bởi giá trị nội suy khác. Nếu muốn tính lại tất cả giá trị theo công thức, dùng `$set`/`$project` và logic riêng, không dùng `$fill` như phép cập nhật đại trà.

---

## 11. Điền giá trị cố định: `output.<field>.value`

Khi domain khẳng định field thiếu tương đương **không phát sinh sự kiện**, có thể điền 0.

```javascript
db.dailySales207.insertMany([
  {
    _id: 1,
    day: ISODate("2026-11-01T00:00:00Z"),
    bootsSold: 12,
    sandalsSold: 5
  },
  {
    _id: 2,
    day: ISODate("2026-11-02T00:00:00Z"),
    sandalsSold: 9
  },
  {
    _id: 3,
    day: ISODate("2026-11-03T00:00:00Z"),
    bootsSold: null
  }
]);
```

Pipeline:

```javascript
db.dailySales207.aggregate([
  {
    $fill: {
      output: {
        bootsSold: { value: 0 },
        sandalsSold: { value: 0 }
      }
    }
  },
  {
    $sort: { day: 1 }
  }
]);
```

Kết quả:

```text
01/11: bootsSold=12, sandalsSold=5
02/11: bootsSold=0,  sandalsSold=9
03/11: bootsSold=0,  sandalsSold=0
```

Với `value: 0`, không cần `sortBy`, vì thay bằng hằng số không phụ thuộc thứ tự document.

### 11.1. `value` có thể là biểu thức

```javascript
{
  $fill: {
    output: {
      discount: { value: "$defaultDiscount" }
    }
  }
}
```

Nếu field `discount` thiếu hoặc null, expression sẽ cung cấp giá trị thay thế. Cần chắc chắn `defaultDiscount` được validate và quy tắc nghiệp vụ cho phép sử dụng nó.

### 11.2. Zero không giống missing

- `value: 0`: có thể là số đo hợp lệ bằng 0.
- `value: null`: chưa có số đo hữu ích.
- Field `value` không tồn tại: có thể là record thiếu thông tin.

Điền 0 cho dữ liệu cảm biến mất tín hiệu có thể tạo cảnh báo sai, làm lệch trung bình hoặc che giấu lỗi ingestion. Chỉ điền 0 khi **nghiệp vụ xác nhận không có record = số lượng bằng 0**.

---

## 12. LOCF — `method: "locf"`

**Last Observation Carried Forward** lấy giá trị không-null gần nhất trước đó trong partition theo `sortBy`.

```javascript
db.sensorReadings207.aggregate([
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "locf" }
      }
    }
  },
  {
    $sort: { sensorId: 1, ts: 1 }
  }
]);
```

Với các document hiện có của A:

```text
00:00 -> 10
02:00 -> null  => 10 (mang từ 00:00)
04:00 -> 18
06:00 -> 24
```

Mốc 01:00 vẫn chưa tồn tại, vì `$fill` không sinh document. Sau khi có `$densify` trước stage này, LOCF cũng có thể điền những mốc tổng hợp.

### 12.1. Không có quan sát trước

Nếu đầu partition là null/missing, không có giá trị trước để mang sang. Những mốc đầu này vẫn null. Nếu cả partition không có giá trị hợp lệ, LOCF không tự tạo giá trị thật.

### 12.2. LOCF có thể làm dữ liệu quá cũ trông như mới

Giả sử cảm biến ghi 25°C lúc 00:00 rồi ngừng truyền hai tuần. Nếu densify tới hiện tại và LOCF, biểu đồ có thể hiển thị 25°C suốt hai tuần. Đây là một **giả định** không đáng tin đối với nhiệt độ.

Muốn giới hạn thời gian giá trị còn hiệu lực, cần một chính sách như `maxStalenessMinutes` và tính độ tuổi của quan sát thực gần nhất. `$fill` không tự từ chối những giá trị quá cũ theo ngưỡng nghiệp vụ.

### 12.3. Tránh làm lẫn partition

Với nhiều sensor hoặc tenant, luôn partition theo đầy đủ định danh nguồn, ví dụ `tenantId`, `siteId`, `sensorId`. Nếu thiếu partition, LOCF của sensor A có thể trở thành giá trị của sensor B, tạo kết quả sai về bản chất.

---

## 13. Linear — `method: "linear"`

**Linear interpolation** dùng các giá trị không-null ở hai phía để ước lượng những vị trí thiếu ở giữa.

Chuỗi đồng đều:

```text
0 -> 10
1 -> null
2 -> null
3 -> null
4 -> 18
```

Khoảng tăng từ 10 đến 18 là 8 qua bốn bước:

```text
1 -> 10 + 8 × 1/4 = 12
2 -> 10 + 8 × 2/4 = 14
3 -> 10 + 8 × 3/4 = 16
```

Pipeline:

```javascript
db.sensorReadings207.aggregate([
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "linear" }
      }
    }
  }
]);
```

Với data gốc, A-02 được điền bằng **14**, dựa trên A-00=10 và A-04=18. Các mốc A-01, A-03 chưa có document, nên chưa có giá trị nào được tạo tại đó.

### 13.1. Chỉ nội suy khi có đủ điểm neo

Nếu một trường null ở đầu hoặc cuối partition mà không có cả giá trị trước và sau, linear không tự ngoại suy.

```text
Đầu vào:
0 -> null
1 -> 10
2 -> null
3 -> 18
4 -> null

Sau linear:
0 -> null
1 -> 10
2 -> 14
3 -> 18
4 -> null
```

Nếu cần dự báo trước điểm đầu hoặc sau điểm cuối, đó là **extrapolation**, cần mô hình/phương pháp riêng, không phải công việc của `$fill` linear.

### 13.2. Điều kiện quan trọng đối với `sortBy`

Khi dùng linear:

1. **Phải khai báo `sortBy`.**
2. `sortBy` chỉ được có **đúng một field**.
3. **Không được có hai document trong cùng partition mang cùng giá trị `sortBy`**.

Không hợp lệ:

```javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: {
      ts: 1,
      _id: 1
    },
    output: {
      temperature: { method: "linear" }
    }
  }
}
```

Dù thêm `_id` để phá hòa thường có ích cho sort, linear không cho hai sort fields. Cần chuẩn hóa dữ liệu thành **mỗi partition có một document trên một mốc**, bằng aggregation hoặc dedup có quy tắc, trước khi dùng linear.

### 13.3. Sort key giống nhau ở partition khác nhau

A và B có thể cùng timestamp. Theo tài liệu MongoDB, **từ 8.0.20**, linear cho phép các partition khác nhau có cùng sort key. Phiên bản cũ hơn có thể báo lỗi trong trường hợp đó. Nhưng trong **cùng partition** vẫn không được trùng.

### 13.4. Timestamp không đều và giá trị nội suy

Linear fill dựa trên chuỗi document theo `sortBy` và các vị trí thiếu được bao quanh bởi giá trị hợp lệ. Nếu dữ liệu có thời điểm không đều, đừng mặc định kết quả tương ứng với một công thức nội suy đúng theo **độ dài thời gian thực tế** mà domain yêu cầu.

Ví dụ có 00:00 = 10, 09:00 = null, 10:00 = 20. Một giá trị null nằm giữa hai giá trị có thật không có nghĩa pipeline đã sử dụng tỉ lệ 9/10 về giờ. Nếu mục tiêu là chuỗi **mỗi giờ một điểm**, densify thành grid giờ trước khi fill.

### 13.5. Không nội suy dữ liệu phân loại

`status: "ON"/"OFF"`, `paymentState`, `deviceMode` hoặc các trường chuỗi không có ý nghĩa cộng/trừ số học. LOCF có thể phù hợp với một số trạng thái kéo dài, nhưng linear interpolation không áp dụng về mặt nghiệp vụ.

---

## 14. Pipeline hoàn chỉnh: `$densify` rồi `$fill`

```javascript
db.sensorReadings207.aggregate([
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "partition"
      }
    }
  },
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "linear" }
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: 1,
      ts: 1,
      temperature: 1
    }
  }
]);
```

Kết quả tính toán mong đợi:

| Sensor | Mốc UTC | Nhiệt độ | Loại dữ liệu |
| --- | --- | ---: | --- |
| A | 00:00 | 10 | Quan sát gốc |
| A | 01:00 | 12 | Mốc sinh, giá trị nội suy |
| A | 02:00 | 14 | Document gốc có null, nay được nội suy |
| A | 03:00 | 16 | Mốc sinh, giá trị nội suy |
| A | 04:00 | 18 | Quan sát gốc |
| A | 05:00 | 21 | Mốc sinh, giá trị nội suy |
| A | 06:00 | 24 | Quan sát gốc |
| B | 01:00 | 100 | Quan sát gốc |
| B | 02:00 | 110 | Mốc sinh, giá trị nội suy |
| B | 03:00 | 120 | Quan sát gốc |
| B | 04:00 | 130 | Mốc sinh, giá trị nội suy |
| B | 05:00 | 140 | Mốc sinh, giá trị nội suy |
| B | 06:00 | 150 | Quan sát gốc |

Giữa A04=18 và A06=24 có một mốc thiếu, nên A05=(18+24)/2=21. Với B03=120 đến B06=150 có hai mốc thiếu, nên B04=130, B05=140.

**Đừng dùng những giá trị dự đoán này thay quan sát thật trong báo cáo yêu cầu dữ liệu nguyên thủy.** Cần thêm cờ nguồn dữ liệu khi xuất kết quả.

### 14.1. Chuyển sang LOCF

Thay stage fill bằng:

```javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { ts: 1 },
    output: {
      temperature: { method: "locf" }
    }
  }
}
```

Khi đó:

```text
A01=10, A02=10, A03=10, A05=18
B02=100, B04=120, B05=120
```

Chọn linear, LOCF hay 0 theo **ý nghĩa dữ liệu**, không theo mong muốn đơn giản là “biểu đồ hết lỗ trống”.

---

## 15. Giữ dấu vết dữ liệu tổng hợp

Nếu không có cờ, một giá trị 12 được nội suy tại A01 có thể trông giống quan sát thật. Có thể đánh dấu tài liệu đầu vào trước `$densify`:

```javascript
db.sensorReadings207.aggregate([
  {
    $set: {
      wasObserved: true,
      hadValue: {
        $ne: [
          { $ifNull: ["$temperature", null] },
          null
        ]
      }
    }
  },
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "partition"
      }
    }
  },
  {
    $set: {
      wasObserved: {
        $ifNull: ["$wasObserved", false]
      },
      hadValue: {
        $ifNull: ["$hadValue", false]
      }
    }
  },
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "linear" }
      }
    }
  },
  {
    $set: {
      valueWasFilled: {
        $and: [
          { $not: ["$hadValue"] },
          { $ne: ["$temperature", null] }
        ]
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: 1,
      ts: 1,
      temperature: 1,
      wasObserved: 1,
      valueWasFilled: 1
    }
  }
]);
```

Cách đọc:

- `wasObserved: true`: document đã có trong đầu vào.
- `wasObserved: false`: document do densify sinh.
- `valueWasFilled: true`: giá trị ban đầu null/missing và sau fill có giá trị.
- A-02 có `wasObserved: true`, `valueWasFilled: true`.
- A-01 có `wasObserved: false`, `valueWasFilled: true`.

Nếu linear không có đủ điểm neo, giá trị vẫn null và `valueWasFilled` nên false, không đánh dấu “đã nội suy thành công”.

Trong hệ thống thật, dữ liệu có NaN, Infinity, string lỗi hoặc các kiểu ngoài schema cần validation riêng; `!= null` không chứng minh đây là số đo hợp lệ.

---

## 16. `partitionBy` và `partitionByFields` của `$fill`

Có hai cách tạo partition.

### 16.1. Danh sách field

```javascript
{
  $fill: {
    partitionByFields: ["tenantId", "sensorId"],
    sortBy: { ts: 1 },
    output: {
      temperature: { method: "locf" }
    }
  }
}
```

Mỗi tổ hợp `tenantId + sensorId` là một chuỗi độc lập. Đây là cách phù hợp khi các field nhóm có sẵn.

### 16.2. Expression

```javascript
{
  $fill: {
    partitionBy: {
      tenant: "$tenantId",
      sensor: "$sensorId"
    },
    sortBy: { ts: 1 },
    output: {
      temperature: { method: "locf" }
    }
  }
}
```

`partitionBy` chấp nhận expression tạo khóa nhóm, không chỉ danh sách field. Không khai báo **cả `partitionBy` và `partitionByFields`** trong cùng `$fill`.

**Khác biệt với `$densify`:** `$densify` dùng `partitionByFields` mà không cung cấp cùng tùy chọn `partitionBy` expression. Nếu cần partition theo khóa tính toán, tạo field khóa bằng `$set` trước khi densify.

---

## 17. Giữ nguyên field gốc với `$setWindowFields`

`$fill` thay trực tiếp field được chỉ định trong `output`. Nếu cần giữ trường đo gốc và tạo **hai cột ước lượng** để so sánh, có thể dùng:

```javascript
db.sensorReadings207.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$sensorId",
      sortBy: { ts: 1 },
      output: {
        linearTemperature: {
          $linearFill: "$temperature"
        },
        carriedTemperature: {
          $locf: "$temperature"
        }
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  }
]);
```

- `$linearFill` và `$locf` là **window expression**, không phải `$fill` stage.
- Chúng chỉ sử dụng được trong `$setWindowFields` theo quy tắc của operator.
- Field kết quả có thể khác field nguồn, ví dụ `linearTemperature` khác `temperature`.
- Cần chú ý các yêu cầu sort và uniqueness của `$linearFill`.

Nếu cần thêm mốc trước khi tính window, có thể đặt `$densify` trước `$setWindowFields` thay vì `$fill`.

| Mục tiêu | Công cụ |
| --- | --- |
| Sinh document 01:00 | `$densify` |
| Điền null ngay trong `temperature` | `$fill` |
| Tạo `temperatureLinear` mà vẫn giữ `temperature` gốc | `$setWindowFields` + `$linearFill` |
| Tạo `temperatureLocf` riêng | `$setWindowFields` + `$locf` |
| Vừa đều mốc vừa có nhiều phương án | `$densify` + các window expression hoặc fill theo nhu cầu |

---

## 18. Chuẩn hóa timestamp và xử lý trùng trước linear

Raw sensor có thể gửi 2 phép đo trong cùng giờ:

```javascript
{
  sensorId: "A",
  ts: ISODate("2026-11-14T01:10:00Z"),
  temperature: 10
}
{
  sensorId: "A",
  ts: ISODate("2026-11-14T01:40:00Z"),
  temperature: 12
}
```

Nếu báo cáo yêu cầu một điểm lúc **01:00**, `$densify` không tự gộp hai document ở 01:10 và 01:40 về bucket 01:00.

Một pipeline điển hình:

```javascript
db.rawSensorReadings.aggregate([
  {
    $set: {
      hourStart: {
        $dateTrunc: {
          date: "$ts",
          unit: "hour",
          timezone: "UTC"
        }
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$sensorId",
        hour: "$hourStart"
      },
      temperature: {
        $avg: "$temperature"
      },
      sampleCount: {
        $sum: 1
      }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      ts: "$_id.hour",
      temperature: 1,
      sampleCount: 1
    }
  },
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "partition"
      }
    }
  },
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: { ts: 1 },
      output: {
        temperature: { method: "linear" }
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      ts: 1
    }
  }
]);
```

Ý nghĩa:

```text
Raw events
   |
   v
$dateTrunc: đưa timestamp về ranh giới giờ
   |
   v
$group: gộp các lần đo cùng sensor + giờ
   |
   v
$densify: sinh giờ thiếu
   |
   v
$fill: nội suy giá trị thiếu
   |
   v
$sort: định thứ tự đầu ra
```

`$avg` chỉ là **quy tắc thống kê minh họa**. Với dữ liệu tích lũy hoặc trạng thái máy, dùng average có thể không đúng; có thể cần giá trị cuối theo timestamp, tổng, max/min hoặc một quy tắc khác.

Không chỉ dùng `$first` trên dữ liệu chưa sort rồi gọi đó là “bản mới nhất”. Nếu hai document có timestamp trùng là retry duplicate, phải xác định cách dedup theo định danh event/version.

---

## 19. Tạo doanh thu ngày với `$densify` và `$fill: 0`

Dữ liệu sự kiện bán hàng:

```javascript
db.salesEvents207.insertMany([
  {
    _id: "S1",
    shopId: "SHOP-1",
    occurredAt: ISODate("2026-11-01T05:00:00Z"),
    amountMinor: 120000
  },
  {
    _id: "S2",
    shopId: "SHOP-1",
    occurredAt: ISODate("2026-11-01T12:00:00Z"),
    amountMinor: 80000
  },
  {
    _id: "S3",
    shopId: "SHOP-1",
    occurredAt: ISODate("2026-11-03T09:00:00Z"),
    amountMinor: 300000
  }
]);
```

Báo cáo doanh thu từ 01/11 đến hết 04/11 theo UTC:

```javascript
const start = ISODate("2026-11-01T00:00:00Z");
const end   = ISODate("2026-11-05T00:00:00Z");

db.salesEvents207.aggregate([
  {
    $match: {
      occurredAt: {
        $gte: start,
        $lt: end
      }
    }
  },
  {
    $set: {
      day: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "UTC"
        }
      }
    }
  },
  {
    $group: {
      _id: {
        shopId: "$shopId",
        day: "$day"
      },
      revenueMinor: {
        $sum: "$amountMinor"
      },
      transactionCount: {
        $sum: 1
      }
    }
  },
  {
    $project: {
      _id: 0,
      shopId: "$_id.shopId",
      day: "$_id.day",
      revenueMinor: 1,
      transactionCount: 1
    }
  },
  {
    $densify: {
      field: "day",
      partitionByFields: ["shopId"],
      range: {
        step: 1,
        unit: "day",
        bounds: [start, end]
      }
    }
  },
  {
    $fill: {
      output: {
        revenueMinor: { value: 0 },
        transactionCount: { value: 0 }
      }
    }
  },
  {
    $sort: {
      shopId: 1,
      day: 1
    }
  }
]);
```

Kết quả kỳ vọng:

| Ngày | Doanh thu minor units | Số giao dịch |
| --- | ---: | ---: |
| 01/11 | 200000 | 2 |
| 02/11 | 0 | 0 |
| 03/11 | 300000 | 1 |
| 04/11 | 0 | 0 |

Điền 0 chỉ phù hợp nếu nguồn dữ liệu và thời điểm báo cáo đã đủ tin cậy: không thấy sự kiện nghĩa là không có giao dịch. Nếu ingestion mất kết nối hoặc sự kiện tới muộn, ngày không có document **chưa chắc là doanh thu 0**. Với báo cáo tài chính, cần cơ chế chốt kỳ và đối soát.

### 19.1. Partition chưa từng xuất hiện

Nếu SHOP-2 không có bất cứ document nào trong tập đầu vào, `$densify` không tự biết phải tạo chuỗi cho SHOP-2. Muốn bao phủ **mọi cửa hàng kể cả cửa hàng không có event**, cần cung cấp danh sách các cửa hàng/partition từ nguồn tham chiếu, hoặc dựng calendar grid riêng.

---

## 20. Calendar, timezone và timestamp không chuẩn

BSON Date lưu một **thời điểm**; “mỗi ngày” lại là khái niệm theo **múi giờ và lịch**.

Ví dụ, ngày của cửa hàng tại Việt Nam thường không đồng nhất với ngày UTC:

```javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
```

Bước này giúp đưa sự kiện về bucket ngày theo múi giờ nghiệp vụ. Bounds dùng cho densify phải được thiết kế tương thích với các ranh giới Date thực tế, không tự đặt các mốc UTC midnight khi nghiệp vụ lấy ngày địa phương.

Ở những khu vực có daylight saving time (DST), một ngày lịch có thể dài 23 hoặc 25 giờ. `unit: "day"` mang ý nghĩa lịch khác với tự cộng cố định `86_400_000` milliseconds cho mọi trường hợp. Cần kiểm thử chuyển DST nếu ứng dụng hoạt động ở những timezone đó.

### 20.1. Không tự chuẩn hóa 10:17 thành 10:00

Nếu dữ liệu đến 10:17 và 12:17, `$densify` không tự đổi chúng thành 10:00 và 12:00. Muốn grid theo đầu giờ, dùng `$dateTrunc` rồi `$group` trước.

### 20.2. `linear` sau densify là một giả định

Với grid đều mốc một phút, hai điểm cách 10 phút và thiếu 9 mốc sẽ được nội suy theo các vị trí đều nhau; điều này có thể phù hợp cho hình ảnh hóa. Nhưng vẫn phải quyết định **khoảng mất dữ liệu tối đa** trước khi cho phép nội suy, nhất là với thiết bị vật lý có thể thay đổi đột ngột.

---

## 21. Hiệu năng và giới hạn sinh document

Giả sử:

```text
500 sensor
30 ngày
24 giờ/ngày
60 phút/giờ
```

Số slot tiềm năng:

```text
500 × 30 × 24 × 60 = 21.600.000 slot
```

Đây là số mốc lý thuyết **trước khi trừ các document gốc đã có**. Nếu phần lớn chưa có, số document `$densify` sinh sẽ rất lớn, có thể vượt giới hạn 500.000 mặc định và gây lỗi.

### 21.1. Những cách giới hạn chi phí

1. `$match` sớm theo `sensorId` và khoảng thời gian cần dùng.
2. Chọn granularity theo nhu cầu: 5 phút, 15 phút, một giờ hoặc ngày.
3. Chia báo cáo theo từng batch thời gian/partition.
4. Chỉ densify những nhóm mà người dùng cần.
5. Tránh `"full"` trên tập có một partition sống quá lâu.
6. Giữ index phù hợp cho `$match` đầu pipeline.
7. Với báo cáo lặp lại, cân nhắc materialized reporting series có kiểm soát.
8. Kiểm tra số document trả, dung lượng BSON, latency và memory của driver.

`allowDiskUse` có thể hỗ trợ một số thao tác nặng về bộ nhớ, nhưng **không tự bỏ giới hạn số document được sinh bởi `$densify`**.

### 21.2. Các stage đều có chi phí

- `$group` có thể phải đọc và tổng hợp nhiều raw events.
- `$densify` có thể làm tăng số document trung gian lên hàng nghìn lần.
- `$fill` phải xử lý các partition theo thứ tự, đặc biệt khi nội suy.
- `$sort` cuối có thể phải sắp xếp tập lớn.
- Java driver phải tải, decode và chuyển kết quả, có thể làm chậm API.

Vì vậy, một collection chỉ có vài nghìn document nguồn vẫn có thể tạo response rất lớn sau densify.

### 21.3. Index cho đường đọc nguồn

Nếu query thường lọc theo sensor và thời gian:

```javascript
db.sensorReadings207.createIndex({
  sensorId: 1,
  ts: 1
});
```

Index này có thể giúp `$match` trước densify. Nhưng nó **không loại bỏ chi phí sinh thêm document hoặc nội suy**.

Có thể phân tích pipeline bằng:

```javascript
db.sensorReadings207.explain("executionStats").aggregate([
  {
    $match: {
      sensorId: "A",
      ts: {
        $gte: ISODate("2026-11-14T00:00:00Z"),
        $lt: ISODate("2026-11-14T07:00:00Z")
      }
    }
  },
  {
    $densify: {
      field: "ts",
      partitionByFields: ["sensorId"],
      range: {
        step: 1,
        unit: "hour",
        bounds: "partition"
      }
    }
  }
]);
```

Ngoài `IXSCAN`/`COLLSCAN`, cần xem số document sau stage, thời gian và kích thước kết quả. Cấu trúc explain có thể khác theo phiên bản MongoDB.

---

## 22. Chỉ đọc kết quả hay lưu lại?

Aggregation với `$densify`/`$fill` mặc định **không sửa dữ liệu nguồn**. Nó tạo kết quả tạm đi qua pipeline.

```javascript
db.sensorReadings207.aggregate([
  // Các stage tạo chuỗi báo cáo...
]);
```

không tự insert mốc A-01 vào collection.

Nếu cần **materialize** kết quả để phục vụ dashboard, hãy thiết kế collection đích có schema, unique key và chính sách cập nhật dữ liệu đến muộn. Ví dụ khóa `(sensorId, ts)`:

```javascript
db.denseReadings207.createIndex(
  {
    sensorId: 1,
    ts: 1
  },
  {
    unique: true
  }
);
```

Việc lưu bằng `$merge` cần chọn `on`, `whenMatched`, `whenNotMatched` và xử lý `_id` phù hợp, không chỉ gắn một stage ghi vào pipeline đang thử nghiệm.

Với dữ liệu nguồn tới muộn, giá trị đã nội suy hôm nay có thể cần tính lại vào ngày mai. **Đừng ghi đè dữ liệu quan sát thật bằng một giá trị nội suy** mà không giữ provenance và khả năng tái dựng.

Ví dụ một record báo cáo:

```javascript
{
  sensorId: "A",
  ts: ISODate("2026-11-14T01:00:00Z"),
  temperature: 12,
  origin: "synthetic",
  fillMethod: "linear"
}
```

Một document dạng này phải được hiểu là **giá trị phân tích**, không phải cảm biến thực sự đã gửi 12.

---

## 23. Dùng MongoDB Java Sync Driver

Có thể dựng các stage bằng `org.bson.Document` để giữ cú pháp gần với mongosh:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

public final class DenseSensorService {

    public static void showSeries(
            MongoCollection<Document> readings,
            String sensorId
    ) {
        Bson match = new Document(
            "$match",
            new Document("sensorId", sensorId)
        );

        Document range = new Document("step", 1)
            .append("unit", "hour")
            .append("bounds", "partition");

        Bson densify = new Document(
            "$densify",
            new Document("field", "ts")
                .append("partitionByFields", List.of("sensorId"))
                .append("range", range)
        );

        Bson fill = new Document(
            "$fill",
            new Document("partitionByFields", List.of("sensorId"))
                .append("sortBy", new Document("ts", 1))
                .append(
                    "output",
                    new Document(
                        "temperature",
                        new Document("method", "linear")
                    )
                )
        );

        Bson sort = new Document(
            "$sort",
            new Document("sensorId", 1)
                .append("ts", 1)
        );

        List<Bson> pipeline = Arrays.asList(
            match,
            densify,
            fill,
            sort
        );

        readings.aggregate(pipeline).forEach(
            document -> System.out.println(document.toJson())
        );
    }
}
```

Đoạn code minh họa BSON pipeline trên server hỗ trợ `$densify` và `$fill` (MongoDB 5.3+ cho cả hai). Không gọi stage khi server cũ hơn rồi trông chờ driver tự mô phỏng.

### 23.1. Truyền explicit bounds là BSON Date

```java
import java.time.Instant;
import java.util.Date;
import org.bson.Document;

Date start = Date.from(
    Instant.parse("2026-11-14T00:00:00Z")
);

Date end = Date.from(
    Instant.parse("2026-11-14T07:00:00Z")
);

Document dateRange = new Document("step", 1)
    .append("unit", "hour")
    .append("bounds", List.of(start, end));
```

Không truyền chuỗi ISO date thay Date rồi kỳ vọng `$densify` tự đổi kiểu. Validate `start < end`, giới hạn độ dài kỳ báo cáo, số sensor và granularity trước khi gửi pipeline.

### 23.2. Chọn DTO phù hợp document tổng hợp

Document do `$densify` sinh thường không có `_id`, metadata hay `temperature` trước fill. Model Java được định nghĩa cứng mọi field luôn khác null có thể không phù hợp.

Có thể dùng `Document` rồi mapping sang DTO báo cáo với nullable fields và provenance. Một số trường hợp linear vẫn để null tại đầu/cuối chuỗi, nên không nên dùng primitive `double` cho trường có thể thiếu/null.

### 23.3. Tránh materialize hàng triệu document trong RAM

```java
// Không phù hợp cho pipeline có kết quả khổng lồ:
readings.aggregate(pipeline)
    .into(new java.util.ArrayList<>());
```

Nếu endpoint chỉ cần một trang báo cáo, giới hạn khoảng đầu vào và chia batch/streaming hợp lý. Tránh `println` từng document trong benchmark vì logging có thể làm số đo latency sai lệch đáng kể.

---

## 24. Hai tình huống ứng dụng

### 24.1. Báo cáo downtime thiết bị

Dữ liệu heartbeat:

```text
12:00 có heartbeat
12:01 thiếu document
12:02 thiếu document
12:03 có heartbeat
```

`$densify` có thể sinh 12:01 và 12:02. Đánh dấu bản ghi gốc bằng `wasObserved: true` trước densify, rồi đặt false cho bản ghi mới:

```javascript
{
  $set: { wasObserved: true }
},
{
  $densify: {
    field: "ts",
    partitionByFields: ["deviceId"],
    range: {
      step: 1,
      unit: "minute",
      bounds: "partition"
    }
  }
},
{
  $set: {
    heartbeatPresent: {
      $ifNull: ["$wasObserved", false]
    }
  }
}
```

Kết quả:

```text
12:00 heartbeatPresent=true
12:01 heartbeatPresent=false
12:02 heartbeatPresent=false
12:03 heartbeatPresent=true
```

`false` ở đây có nghĩa **không có record trong tập dữ liệu**, không nhất thiết thiết bị mất điện. Có thể còn lỗi mạng hoặc ingestion trễ. Không dùng LOCF để làm các mốc thiếu thành heartbeat=true, vì điều đó che giấu khoảng cần quan sát.

### 24.2. Trạng thái tồn kho

Một thay đổi tồn kho là một event:

```javascript
{
  sku: "P100",
  warehouseId: "W1",
  changedAt: ISODate("2026-11-14T08:00:00Z"),
  onHandAfterChange: 42
}
```

Để có snapshot mỗi giờ, LOCF có thể phù hợp nếu hệ thống ghi **mọi sự kiện thay đổi tồn kho** và không có sự kiện mới nghĩa là trạng thái không đổi. Linear lại có thể tạo ra số lượng trung gian chưa từng tồn tại.

Cần chuẩn hóa theo khóa `(warehouseId, sku)`, chọn event mới nhất trong từng giờ theo quy tắc rõ ràng, densify các giờ thiếu rồi LOCF. Nếu event history không đầy đủ, ngay cả LOCF cũng có thể sai.

---

## 25. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `$densify` không tạo mốc đúng giờ | Timestamp 10:17 chưa được bucket | `$dateTrunc`/`$group` trước densify. |
| `$densify` Date báo lỗi | Thiếu `unit` hoặc field sai kiểu | Dùng BSON Date, khai báo đơn vị. |
| `$densify` numeric báo lỗi | Khai báo `unit` hoặc dữ liệu trộn kiểu | Bỏ `unit`, validate số. |
| Document ngoài bounds vẫn xuất hiện | Bounds chỉ điều khiển sinh thêm | Dùng `$match` cho khoảng báo cáo. |
| `$densify` trả kết quả không theo thứ tự | Stage không bảo đảm order | `$sort` cuối. |
| `$fill` không sinh ngày thiếu | `$fill` không tạo document | `$densify` trước. |
| `$fill` làm dữ liệu tenant A lẫn B | Partition thiếu khóa phân biệt | Partition theo đầy đủ identity. |
| `$fill` linear báo `sortBy` có nhiều field | Linear chỉ cho một sort field | Chuẩn hóa một khóa thời gian duy nhất. |
| `$fill` linear gặp timestamp trùng | Trùng trong cùng partition | Dedup/aggregate dữ liệu trước. |
| Linear null đầu/cuối không đổi | Không có điểm neo hai phía | Chấp nhận null hoặc dùng chính sách khác. |
| LOCF đầu chuỗi vẫn null | Không có giá trị trước | Cấp điểm neo nếu hợp lệ. |
| Pipeline lỗi vì sinh quá nhiều document | Range dài, step nhỏ, nhiều partition | Thu hẹp range, chia batch, tăng granularity. |
| Báo cáo có toàn số 0 dù sensor hỏng | Điền 0 sai ý nghĩa | Phân biệt missing và measured zero. |
| Từ 8.1 báo lỗi về path | `field` chia sẻ prefix với partition path | Chọn field độc lập. |
| Kết quả khác giữa MongoDB patch versions | Thay đổi `[x,x]` ở 8.0 hoặc linear ở 8.0.20 | Kiểm tra phiên bản và tài liệu. |

### 25.1. Đừng đặt hai điều kiện sort cho linear

```javascript
// Sai với method "linear":
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { ts: 1, _id: 1 },
    output: {
      temperature: { method: "linear" }
    }
  }
}
```

Không có cách “chỉ thêm `_id` cho chắc” ở đây. Cần làm rõ vì sao cùng sensor có nhiều document trùng `ts` rồi áp quy tắc hợp nhất phù hợp.

### 25.2. Không có partition nguồn thì không thể tự phát minh tenant

Nếu một tenant chưa có bất kỳ record nào trong tập đưa vào stage, không có khóa để tự sinh chuỗi thời gian cho tenant đó. Muốn báo cáo toàn bộ tenant kể cả không hoạt động, phải thêm danh sách tenant và calendar grid từ nguồn tham chiếu hoặc logic khác.

---

## 26. Bài tập và đáp án

### Bài 1 — Mốc thiếu so với giá trị thiếu

Đầu vào:

```javascript
[
  { seq: 0, value: 10 },
  { seq: 2, value: null },
  { seq: 4, value: 18 }
]
```

**Hỏi:** Densify step 1 tạo gì? Linear sau đó cho các mốc 1,2,3 bao nhiêu?

**Đáp án:** Tạo document ở 1 và 3; mốc 2 vốn có. Linear điền lần lượt 12, 14, 16.

### Bài 2 — LOCF đầu chuỗi

```text
0 -> null
1 -> 10
2 -> null
3 -> null
4 -> 18
5 -> null
```

**Đáp án:** `null, 10, 10, 10, 18, 18`. Mốc đầu chưa có điểm quan sát trước nên vẫn null.

### Bài 3 — Linear không ngoại suy

```text
0 -> null
1 -> 10
2 -> null
3 -> 20
4 -> null
```

**Đáp án:** `null, 10, 15, 20, null`.

### Bài 4 — Upper exclusive

```javascript
range: {
  step: 1,
  bounds: [2, 5]
}
```

**Đáp án:** Mốc cần sinh trong phạm vi là 2,3,4; 5 là upper exclusive. Densify không tự loại document nguồn nằm ngoài khoảng.

### Bài 5 — Partition và full

```text
A: seq 1, 3
B: seq 2, 4
```

Step 1. **Hỏi:** `"full"` có thể thêm mốc nào ngoài `"partition"`?

**Đáp án gợi ý:** `"full"` dùng miền chung 1–4, nên có thể sinh mốc 1 cho B và mốc 4 cho A; `"partition"` chỉ dùng miền riêng của từng nhóm.

### Bài 6 — Trùng timestamp

Một sensor có hai document cùng `ts`, linear báo lỗi. **Cách giải quyết?**

**Gợi ý:** Xác định đó là duplicate do retry, hai phép đo hợp lệ hay các version khác nhau. Sau đó dedup hoặc `$group` theo `(sensorId, ts)` với chính sách được phê duyệt trước khi nội suy.

### Bài 7 — Báo cáo doanh thu

Một cửa hàng có 500 nghìn đồng doanh thu ngày 01/11 và 700 nghìn ngày 03/11; ngày 02/11 không có giao dịch, dữ liệu đã chốt.

**Gợi ý:** Điền 0 cho ngày 02/11 thường đúng hơn linear 600 nghìn hay LOCF 500 nghìn — hai cách sau tạo doanh thu không phát sinh.

### Bài 8 — Chọn partition

Có `tenantId`, `warehouseId`, `sku`. Snapshot hàng tồn phải tách theo từng SKU trong mỗi kho của mỗi tenant.

**Đáp án:** partition theo đủ ba field. Chỉ theo `sku` có thể trộn tồn kho giữa các tenant/kho khác nhau.

### Bài 9 — Tính độ lớn

1.000 thiết bị, 24 giờ, một slot/phút.

```text
1.000 × 24 × 60 = 1.440.000 slot
```

Nếu phần lớn slot thiếu, densify có thể sinh quá giới hạn mặc định 500.000 document. Cần giảm phạm vi/chia batch/thay granularity.

### Bài 10 — Version

Server MongoDB 5.2 hỗ trợ `$densify` và `$fill` chưa?

**Đáp án:** Có `$densify` (5.1+), nhưng **chưa có `$fill` stage** (5.3+). Cần upgrade hoặc thiết kế lại bước điền bằng công cụ được hỗ trợ trên phiên bản thực tế.

### Bài 11 — Dấu vết nội suy

A02 là document gốc có `temperature: null`, sau linear thành 14. A01 là document mới sinh có value 12.

**Hỏi:** Cả hai có giống nhau về nguồn dữ liệu không?

**Đáp án:** Không. A02 có document nguồn nhưng field null; A01 không có document nguồn. Cần giữ ít nhất hai cờ `wasObserved` và `valueWasFilled` nếu muốn phân biệt chính xác.

### Bài 12 — Chỉ dùng `$fill`

Sensor A có 00:00=10 và 04:00=18, **không có document 01–03**. Dùng `$fill` linear trực tiếp có tạo 01/02/03 không?

**Đáp án:** Không. Phải có document ở các mốc trung gian; dùng `$densify` trước hoặc tạo grid bằng phương pháp khác.

---

## 27. Checklist trước khi triển khai

1. Dữ liệu đang thiếu **document** hay thiếu **field**?
2. Field densify là numeric hay BSON Date, có lẫn string/null sai kiểu không?
3. Server version/FCV có hỗ trợ `$densify`, `$fill` và các behavior đang dùng không?
4. Partition có tách đủ tenant, sensor, site hoặc entity ID?
5. Có duplicate sort keys trong một partition không?
6. `step` và `unit` đã khớp đơn vị đo mong muốn chưa?
7. Dùng `partition`, `full` hay explicit `[lower, upper)`? Upper bound đã hiểu là exclusive chưa?
8. Có cần bucket bằng `$dateTrunc` và tổng hợp `$group` trước densify?
9. Có giá trị neo ở đầu/cuối để LOCF/linear hoạt động không?
10. Giá trị thiếu nên để null, dùng 0, LOCF hay linear theo **domain**?
11. Có giới hạn khoảng thiếu dài nhất được phép nội suy không?
12. Có giữ cờ phân biệt observed, synthetic và filled không?
13. Có đủ ngân sách số slot/partition và tránh vượt giới hạn 500.000 document sinh mặc định không?
14. Có `$match` sớm và index phù hợp cho đường đọc không?
15. Kết quả được trả tạm thời hay lưu, và cách cập nhật khi dữ liệu tới muộn?
16. Java DTO có chấp nhận `null` và document thiếu `_id` không?
17. Có `$sort` cuối khi API yêu cầu thứ tự không?
18. Khi đo hiệu năng, có tính cả số document được sinh và kích thước response không?

Sơ đồ triển khai:

```text
Raw events
   |
   v
Validate kiểu và khóa partition
   |
   v
$dateTrunc + $group nếu cần bucket/dedup
   |
   v
$match theo entity và thời gian cần thiết
   |
   v
Đánh dấu document nguồn
   |
   v
$densify tạo mốc thiếu
   |
   v
$fill theo policy nghiệp vụ
   |
   v
Đánh dấu giá trị ước tính
   |
   v
$sort / $project
   |
   v
API response hoặc materialized reporting series
```

---

## 28. Những ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| "`$densify` tự đoán giá trị nhiệt độ." | Nó tạo document tại mốc thiếu; cần `$fill` hoặc logic khác để điền giá trị. |
| "`$fill` tự sinh ngày chưa có document." | Nó chỉ điền field trong document hiện có. |
| "`$densify` giống `$dateTrunc`." | `dateTrunc` tạo bucket, `densify` sinh slot còn thiếu. |
| "`$densify` giống `$group`." | Nó không tổng hợp các raw events trùng bucket. |
| "`bounds: full` luôn tới hiện tại." | Nó phụ thuộc miền dữ liệu đầu vào. |
| "`bounds: partition` phủ mọi sensor cùng thời gian." | Mỗi partition chỉ dùng miền riêng. |
| "Upper bound là inclusive." | Upper bound là exclusive. |
| "Densify lọc hết document nằm ngoài explicit bounds." | Không; cần `$match` riêng. |
| "Densify bảo đảm kết quả đã sort." | Không; dùng `$sort` tường minh. |
| "Densify Date không cần `unit`." | Date cần `range.unit`. |
| "Densify numeric cũng nên có `unit`." | Numeric không dùng `unit`. |
| "`$fill` sẽ luôn hết null." | Linear/LOCF có thể giữ null khi không đủ điểm neo. |
| "Linear cho phép `sortBy` nhiều field." | Không, chỉ đúng một field. |
| "Linear cho phép timestamp trùng trong cùng partition." | Không; trùng gây lỗi. |
| "Timestamp trùng giữa các partition luôn lỗi." | Hành vi đã thay đổi từ MongoDB 8.0.20. |
| "LOCF đúng cho mọi loại dữ liệu." | Có thể giữ giá trị quá cũ và che giấu mất dữ liệu. |
| "Không có đo nhiệt độ nghĩa là nhiệt độ bằng 0." | Missing khác measured zero. |
| "Giá trị nội suy tương đương quan sát thật." | Cần provenance và chính sách sử dụng khác nhau. |
| "`allowDiskUse` làm densify không còn giới hạn." | Không tự bỏ giới hạn số document sinh. |
| "Không có dữ liệu của partition X thì densify sẽ tạo X." | Không tự phát minh partition chưa có đầu vào. |
| "MongoDB 5.1 có cả hai stage." | `$fill` mới có từ 5.3. |
| "Aggregation fill đã sửa collection." | Không, trừ khi có bước ghi phù hợp như `$merge`. |

---

## 29. Tài liệu MongoDB chính thức

- [`$densify` — Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/densify/): cú pháp, bounds, partition, giới hạn số document và thay đổi từ 8.0/8.1.
- [`$fill` — Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/fill/): constant, linear, LOCF, sortBy, partitions, thay đổi ở 8.0.20.
- [`$linearFill` — Window Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/linearFill/): nội suy trong `$setWindowFields`.
- [`$locf` — Window Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/locf/): last-observation-carried-forward.
- [`$setWindowFields`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/): phân vùng và tính toán theo cửa sổ.
- [`$dateTrunc`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/): chuẩn hóa timestamps về bucket.
- [`$dateDiff`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateDiff/): tính chênh thời gian khi triển khai max-gap.
- [`$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/): tổng hợp theo bucket.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/): khả năng tối ưu và dùng index.
- [MongoDB 8.2 Compatibility Changes](https://www.mongodb.com/docs/manual/release-notes/8.2-compatibility/): các thay đổi behavior liên quan tới densify/fill.
- [Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/): gửi pipeline từ ứng dụng Java.

Khi triển khai, hãy đối chiếu tài liệu với **phiên bản MongoDB server và Java driver thực tế**, nhất là với thay đổi ở các bản patch và điều kiện của `linear`.

## 30. Kết luận

`$densify` và `$fill` không thay thế nhau: một stage tạo **mốc/document**, stage kia điền **giá trị null/missing**. Khi dùng cùng nhau, chúng giúp xây chuỗi thời gian hoặc dãy số liên tục để vẽ biểu đồ và phân tích.

Nhưng một chuỗi trông đầy đủ chưa chắc là **dữ liệu quan sát đầy đủ**. Phải chọn đúng partition, bounds, step, chuẩn hóa timestamp, giải quyết duplicate, kiểm soát giới hạn sinh document, chọn phương pháp điền theo nghiệp vụ và giữ dấu vết giá trị tổng hợp.

**Tạo đúng mốc chỉ là bước đầu; điền đúng ý nghĩa và giữ khả năng phân biệt dữ liệu thật với dữ liệu suy diễn mới làm kết quả đáng tin cậy.**
