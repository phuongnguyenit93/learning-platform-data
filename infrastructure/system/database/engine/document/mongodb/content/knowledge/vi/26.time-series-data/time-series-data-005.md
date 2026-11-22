# Truy vấn theo thời gian, metadata và thiết kế index trong MongoDB Time Series

## 1. Bài toán: dữ liệu đến liên tục nhưng truy vấn chỉ cần một lát cắt

Một hệ thống giám sát có 50.000 thiết bị. Mỗi thiết bị gửi công suất, nhiệt độ và trạng thái mỗi phút. Trong một ngày, hệ thống có thể thu hơn 70 triệu phép đo. Người dùng lại thường đặt những câu hỏi rất cụ thể:

- Thiết bị **meter-A** của tenant **t001** đã tiêu thụ bao nhiêu trong 30 phút gần nhất?
- Cho tôi **20 phép đo mới nhất** của một sensor.
- Vẽ đường công suất **theo từng giờ** của tất cả thiết bị tại một site.
- Trong khoảng thời gian được chọn, có bao nhiêu mẫu có **quality = "suspect"**?
- Vì sao truy vấn trên một khoảng hai giờ vẫn chậm dù đã tạo index trên timestamp?

Đây là dạng workload đặc trưng của **time-series data**: lượng ghi lớn, các phép đo mang thời điểm và định danh nguồn, còn truy vấn thường kết hợp **khoảng thời gian + thông tin thiết bị (metadata)**.

MongoDB hỗ trợ **time series collections** để tối ưu việc lưu trữ và truy cập chuỗi thời gian. Tuy nhiên, tạo collection với cấu hình time series **không tự bảo đảm mọi truy vấn nhanh**. Hiệu quả vẫn phụ thuộc cấu trúc metadata, khoảng thời gian lọc, cách sắp xếp, index và khả năng loại bỏ những bucket không liên quan.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **timeField**, **metaField** và các **measurement fields**.
2. Viết bộ lọc thời gian bằng **BSON Date**, dùng khoảng nửa mở **[start, end)**.
3. Kết hợp equality trên **metadata** với khoảng thời gian và sort.
4. Lấy mẫu mới nhất, tổng hợp theo thiết bị và nhóm theo giờ/ngày.
5. Chọn **compound index** dựa trên access patterns, thay vì index từng field một cách máy móc.
6. Hiểu vai trò của **buckets**, granularity và những stage đặc biệt trong explain.
7. Phân biệt index hỗ trợ **routing/loại bucket** với index cho filter trên measurement.
8. Thiết kế retention/TTL, sharding và kiểm soát tenant trong một hệ thống time series.
9. Xử lý sai lệch múi giờ, dữ liệu đến muộn, phép đo trùng và khoảng thời gian không có mẫu.
10. Có một lab mongosh tạo dữ liệu cố định, truy vấn, đọc explain và thực hành điều chỉnh index.

> Bài học đặt trong bối cảnh **Database Engine Document MongoDB → Chuỗi thời gian**, sử dụng **time series collection** thật. Một số tính năng index, cập nhật, TTL, resampling hoặc sharding có điều kiện theo phiên bản MongoDB. Khi triển khai production, phải đối chiếu tài liệu của **đúng phiên bản server** và kiểm tra query plan thực tế.

## 2. Mô hình time-series collection

### 2.1. Một phép đo gồm những gì?

Ví dụ một document:

~~~javascript
{
  _id: "ts-001",
  observedAt: ISODate("2026-01-15T00:30:00.000Z"),
  metadata: {
    tenantId: "t001",
    siteId: "hn",
    deviceId: "meter-A",
    metricType: "power"
  },
  watts: 12,
  temperatureC: 22.4,
  quality: "ok",
  seq: 2
}
~~~

Vai trò:

| Nhóm field | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **timeField** | observedAt | Thời điểm phép đo xảy ra; giá trị là **BSON Date** |
| **metaField** | metadata | Thông tin mô tả nguồn/phân loại chuỗi đo, thường ổn định theo thời gian |
| **measurement fields** | watts, temperatureC, quality | Những giá trị biến đổi theo từng phép đo |
| **Khóa và phụ trợ** | _id, seq | Định danh/nguồn gốc và phân biệt các mẫu khi cần |

Trong time series collection, trường metaField có thể là một object có nhiều thuộc tính. Nó không bắt buộc có tên **metadata**, nhưng tên này giúp dễ nhận diện trong bài.

### 2.2. Tạo collection

~~~javascript
db.createCollection("deviceMetrics", {
  timeseries: {
    timeField: "observedAt",
    metaField: "metadata",
    granularity: "seconds"
  }
});
~~~

Khai báo:

- **timeField: "observedAt"**: tên field phải có giá trị thời gian hợp lệ khi ghi phép đo.
- **metaField: "metadata"**: tên field được dùng để nhóm metadata.
- **granularity: "seconds"**: gợi ý độ hạt thời gian cho cách MongoDB quản lý bucket; không phải lệnh làm tròn timestamp của mỗi document.

Bạn vẫn thao tác qua collection logic **deviceMetrics** bằng insert, find và aggregate. Không cần tự xây Array chứa hàng nghìn phép đo trong một document.

### 2.3. Bucket là gì?

MongoDB có thể lưu nhiều measurement liên quan trong các **bucket** nội bộ để nén và tối ưu đọc/ghi:

~~~text
Document logic người dùng nhìn thấy:

  meter-A @ 00:00 -> 10 W
  meter-A @ 00:15 -> 11 W
  meter-A @ 00:30 -> 12 W
  meter-B @ 00:00 -> 20 W

Lưu trữ vật lý (mô hình khái niệm):

  Bucket A: metadata của meter-A, một khoảng thời gian,
            nhiều measurements được tổ chức/nén

  Bucket B: metadata của meter-B, một khoảng thời gian,
            nhiều measurements được tổ chức/nén
~~~

**Một bucket không phải một document nghiệp vụ được ứng dụng trực tiếp quản lý.** MongoDB tự quyết định bucket, mức nén và tổ chức vật lý theo cấu hình và dữ liệu thực tế.

Khi query:

~~~javascript
db.deviceMetrics.find({
  "metadata.deviceId": "meter-A",
  observedAt: {
    $gte: ISODate("2026-01-15T00:00:00Z"),
    $lt: ISODate("2026-01-15T01:00:00Z")
  }
});
~~~

MongoDB có thể **loại bỏ bucket không phù hợp trước khi giải nén/đọc measurements**, dựa trên metadata và giới hạn thời gian bucket. Đây là nền tảng của hiệu năng time-series collection.

### 2.4. Không thao tác trực tiếp với system.buckets

Trong một số công cụ quan sát/explain, bạn có thể thấy namespace nội bộ kiểu **system.buckets.deviceMetrics** hoặc stage liên quan tới bucket.

Đừng:

- Insert trực tiếp vào system.buckets.
- Sửa/delete trực tiếp bucket để “tối ưu nén”.
- Tự tạo một schema bucket vật lý mô phỏng rồi mong API thời gian làm việc tương tự.
- Dựa vào chi tiết nội bộ bucket như một hợp đồng ổn định giữa các phiên bản.

Ứng dụng phải truy cập qua **logical time series collection** và các API MongoDB được hỗ trợ.

## 3. Chọn metadata đúng ngay từ đầu

### 3.1. Những field phù hợp

Metadata thường mô tả nguồn dữ liệu và có khả năng lặp lại ở nhiều phép đo:

~~~javascript
metadata: {
  tenantId: "t001",
  siteId: "hn",
  deviceId: "meter-A",
  metricType: "power"
}
~~~

Các thông tin này giúp trả lời “phép đo thuộc chuỗi nào?”. Nếu deviceId/tenantId ổn định, MongoDB có cơ hội nhóm những phép đo cùng nguồn và tận dụng phép lọc theo metadata.

### 3.2. Những field không nên đặt vào metadata chỉ vì muốn index

Ví dụ kém:

~~~javascript
metadata: {
  tenantId: "t001",
  deviceId: "meter-A",
  watts: 12,
  temperatureC: 22.4,
  requestUuid: "new-id-for-every-sample"
}
~~~

Vì watts, temperatureC và requestUuid liên tục thay đổi, hai mẫu của cùng thiết bị có thể có các giá trị metadata khác nhau. Điều này làm giảm khả năng nhóm phép đo cùng metadata vào những bucket có ích và có thể làm tăng overhead lưu trữ.

**Metadata nên tương đối ổn định; measurements nên chứa giá trị thay đổi theo từng mẫu.**

### 3.3. Metadata không phải quyền truy cập

Filter:

~~~javascript
{ "metadata.tenantId": "t001" }
~~~

giúp thu hẹp kết quả nhưng không tự xác minh người gọi có quyền với tenant t001. API phải lấy tenant đã được xác thực từ security context và đưa vào truy vấn, không tin trực tiếp tenantId do client gửi.

Điều này đặc biệt quan trọng vì một time-series collection có thể chứa phép đo của nhiều tenant.

### 3.4. Nếu thiết bị chuyển site hoặc đổi cấu hình?

Giả sử meter-A chuyển từ site hn sang site dn vào ngày 20/01. Có hai hướng:

- **Metadata tại thời điểm đo**: những phép đo cũ tiếp tục mang siteId="hn"; mẫu mới có siteId="dn". Phù hợp báo cáo lịch sử “thiết bị thuộc site nào khi đo”.
- **Danh mục thiết bị riêng**: metadata chỉ lưu deviceId/tenantId ổn định, còn site hiện tại nằm ở collection devices. Phù hợp khi muốn tránh metadata thay đổi nhưng cần join/lookup để giải nghĩa site.

Không có lựa chọn đúng cho mọi nghiệp vụ. Cần xác định **câu hỏi lịch sử**, quy tắc cập nhật và access patterns trước khi chọn.

## 4. Lab mongosh: 24 phép đo có kết quả xác định

### 4.1. Tập dữ liệu

Ta dùng ba thiết bị, mỗi thiết bị có tám mẫu cách nhau 15 phút trong ngày 15/01/2026 (UTC).

| Tenant | Site | Device | Thời điểm UTC | watts |
| --- | --- | --- | --- | --- |
| t001 | hn | meter-A | 00:00 → 01:45, cách 15 phút | 10 → 17 |
| t001 | hn | meter-B | 00:00 → 01:45, cách 15 phút | 20 → 27 |
| t002 | dn | meter-C | 00:00 → 01:45, cách 15 phút | 30 → 37 |

Cụ thể, mỗi thiết bị có:

~~~text
00:00, 00:15, 00:30, 00:45,
01:00, 01:15, 01:30, 01:45 UTC
~~~

Tổng cộng: **3 × 8 = 24 measurements**.

### 4.2. Tạo collection và seed

Chạy trong mongosh. Script chủ động **không drop collection**, không xóa dữ liệu ngoài bài; nếu 24 phép đo lab đã có, nó không insert trùng lần nữa.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_ts_query_lab_285");
  const collName = "lab_metrics";
  const tag = "ts-index-lab-v1";

  const collectionInfo = lab.getCollectionInfos({
    name: collName
  });

  if (collectionInfo.length === 0) {
    lab.createCollection(collName, {
      timeseries: {
        timeField: "observedAt",
        metaField: "metadata",
        granularity: "seconds"
      }
    });
  } else {
    const options = collectionInfo[0].options || {};
    const ts = options.timeseries;
    if (
      !ts ||
      ts.timeField !== "observedAt" ||
      ts.metaField !== "metadata"
    ) {
      throw new Error(
        "lab_metrics đã tồn tại nhưng không đúng cấu hình time series."
      );
    }
  }

  const metrics = lab.getCollection(collName);
  const sources = [
    {
      tenantId: "t001", siteId: "hn",
      deviceId: "meter-A", wattsStart: 10
    },
    {
      tenantId: "t001", siteId: "hn",
      deviceId: "meter-B", wattsStart: 20
    },
    {
      tenantId: "t002", siteId: "dn",
      deviceId: "meter-C", wattsStart: 30
    }
  ];

  const rows = [];
  for (const source of sources) {
    for (let i = 0; i < 8; i++) {
      rows.push({
        _id: "ts285-" + source.deviceId + "-" + i,
        metadata: {
          lab: tag,
          tenantId: source.tenantId,
          siteId: source.siteId,
          deviceId: source.deviceId,
          metricType: "power"
        },
        observedAt: new Date(
          Date.UTC(2026, 0, 15, 0, i * 15, 0)
        ),
        watts: source.wattsStart + i,
        temperatureC: 20 + i / 2,
        quality: (
          source.deviceId === "meter-B" && i === 3
        ) ? "suspect" : "ok",
        seq: i
      });
    }
  }

  const existing = metrics.countDocuments({
    "metadata.lab": tag
  });

  if (existing === 0) {
    metrics.insertMany(rows);
  } else if (existing !== rows.length) {
    throw new Error(
      "Dataset lab đang có " + existing +
      "/24 mẫu. Không tự seed bổ sung để tránh dữ liệu trùng."
    );
  }

  printjson({
    collection: collName,
    existingBeforeSeed: existing,
    currentCount: metrics.countDocuments({
      "metadata.lab": tag
    }),
    collectionType: lab.getCollectionInfos({
      name: collName
    })[0].type
  });
})();
~~~

**Kết quả mong đợi lần đầu:** currentCount = **24**. Nếu chạy lại mà dữ liệu vẫn đầy đủ, existingBeforeSeed = 24 và currentCount = 24.

Điều kiện **count bằng 24** chỉ giúp script tránh insert trùng trong lab, không phải cơ chế phát hiện chỉnh sửa sai dữ liệu. Nếu bạn tự thay đổi/xóa một phần dữ liệu, cần dùng một database lab mới hoặc reset **có chủ đích** trên collection riêng thay vì âm thầm thêm những measurement có thể bị trùng.

### 4.3. Kiểm tra dữ liệu

~~~javascript
const metrics = db.getSiblingDB("mongo_ts_query_lab_285")
  .getCollection("lab_metrics");

printjson(
  metrics.find(
    { "metadata.lab": "ts-index-lab-v1" },
    {
      _id: 1,
      observedAt: 1,
      metadata: 1,
      watts: 1
    }
  )
  .sort({ "metadata.deviceId": 1, observedAt: 1 })
  .limit(5)
  .toArray()
);
~~~

Với thứ tự sort đó, năm dòng đầu thuộc **meter-A**, thời điểm từ 00:00 đến 01:00 UTC, watts từ 10 đến 14.

### 4.4. Quy ước cho các truy vấn phía dưới

Trong những đoạn code ở các mục tiếp theo, nếu không khai báo lại:

~~~javascript
const lab = db.getSiblingDB("mongo_ts_query_lab_285");
const metrics = lab.getCollection("lab_metrics");
const tag = "ts-index-lab-v1";
~~~

Hãy chạy ba dòng trên trong mongosh session của mình. Nếu một đoạn được chạy ở terminal mới, khai báo lại các biến trước khi chạy.

## 5. Truy vấn thời gian đúng kiểu dữ liệu

### 5.1. Sử dụng BSON Date, không dùng chuỗi để lọc Date

Đúng:

~~~javascript
metrics.find({
  observedAt: {
    $gte: ISODate("2026-01-15T00:30:00.000Z"),
    $lt: ISODate("2026-01-15T01:30:00.000Z")
  }
});
~~~

Sai ý nghĩa nếu observedAt được lưu dạng BSON Date:

~~~javascript
metrics.find({
  observedAt: {
    $gte: "2026-01-15T00:30:00.000Z",
    $lt: "2026-01-15T01:30:00.000Z"
  }
});
~~~

Các chuỗi trong ví dụ thứ hai thuộc kiểu BSON String, không phải Date. MongoDB so sánh theo quy tắc type/bracket tương ứng, nên không thể coi query trên String là một bộ lọc thời gian chuẩn cho BSON Date.

### 5.2. Khoảng nửa mở [start, end)

Mẫu nên dùng:

~~~javascript
const start = ISODate("2026-01-15T00:30:00.000Z");
const end = ISODate("2026-01-15T01:30:00.000Z");

metrics.find({
  "metadata.lab": tag,
  "metadata.tenantId": "t001",
  "metadata.deviceId": "meter-A",
  observedAt: {
    $gte: start,
    $lt: end
  }
})
.sort({ observedAt: 1 })
.toArray();
~~~

**Kết quả mong đợi:** bốn mẫu:

| observedAt (UTC) | watts |
| --- | ---: |
| 00:30 | 12 |
| 00:45 | 13 |
| 01:00 | 14 |
| 01:15 | 15 |

Mẫu lúc **01:30** không nằm trong khoảng vì điều kiện dùng **$lt: end**.

### 5.3. Tại sao [start, end) tốt hơn cả hai đầu inclusive?

Giả sử xử lý hai ca:

~~~text
Ca 1: [00:00, 01:00)
Ca 2: [01:00, 02:00)
~~~

Mẫu tại **01:00** chỉ thuộc ca 2. Nếu hai ca đều dùng **$lte** ở cuối, mẫu 01:00 có thể bị đếm hai lần.

Khoảng nửa mở dễ ghép nối, phân trang thời gian và tổng hợp theo bucket giờ/ngày. Nó không loại trừ việc dùng $lte khi hợp đồng nghiệp vụ thật sự cần inclusive endpoint, nhưng phải làm rõ quy tắc.

### 5.4. Dữ liệu đến muộn

Một phép đo có **observedAt = 00:15** nhưng được gửi lúc **02:30** vẫn thuộc khoảng 00:00–01:00 khi query lọc theo observedAt. Nếu hệ thống cũng cần phân tích thời điểm nhận dữ liệu, nên lưu riêng:

~~~javascript
{
  observedAt: ISODate("2026-01-15T00:15:00Z"),
  ingestedAt: ISODate("2026-01-15T02:30:00Z")
}
~~~

Đây là hai ý nghĩa khác nhau:

- **observedAt**: thời điểm sự kiện/đo đạc diễn ra.
- **ingestedAt**: thời điểm hệ thống nhận dữ liệu.

Nếu cảnh báo “dữ liệu đến muộn hơn 30 phút”, bạn có thể so sánh hai mốc. Nếu tính công suất trong giờ 00:00–01:00, thường dùng **observedAt**. Không dùng ingestedAt thay thế timeField một cách vô thức.

## 6. Kết hợp filter metadata và thời gian

### 6.1. Query theo một thiết bị

~~~javascript
metrics.find(
  {
    "metadata.lab": tag,
    "metadata.tenantId": "t001",
    "metadata.deviceId": "meter-A",
    observedAt: {
      $gte: ISODate("2026-01-15T00:00:00Z"),
      $lt: ISODate("2026-01-15T02:00:00Z")
    }
  },
  { _id: 0, observedAt: 1, watts: 1, quality: 1 }
)
.sort({ observedAt: 1 })
.toArray();
~~~

**Kết quả mong đợi:** tám mẫu của meter-A, watts 10 đến 17.

Metadata giúp thu hẹp **chuỗi đo**, thời gian giúp thu hẹp **đoạn dữ liệu trong chuỗi**.

### 6.2. Query nhiều thiết bị trong một site

~~~javascript
metrics.find(
  {
    "metadata.lab": tag,
    "metadata.tenantId": "t001",
    "metadata.siteId": "hn",
    observedAt: {
      $gte: ISODate("2026-01-15T00:00:00Z"),
      $lt: ISODate("2026-01-15T02:00:00Z")
    }
  },
  {
    _id: 0,
    "metadata.deviceId": 1,
    observedAt: 1,
    watts: 1
  }
)
.sort({ "metadata.deviceId": 1, observedAt: 1 })
.toArray();
~~~

**Kết quả mong đợi:** **16 mẫu** của meter-A và meter-B. Không có meter-C vì tenant/site khác.

### 6.3. Dùng $in cho một nhóm thiết bị

~~~javascript
metrics.find({
  "metadata.lab": tag,
  "metadata.tenantId": "t001",
  "metadata.deviceId": { $in: ["meter-A", "meter-B"] },
  observedAt: {
    $gte: ISODate("2026-01-15T01:00:00Z"),
    $lt: ISODate("2026-01-15T02:00:00Z")
  }
}).toArray();
~~~

Kết quả là **8 mẫu**: bốn mốc từ 01:00 đến 01:45 cho mỗi thiết bị. Với một danh sách thiết bị quá dài, $in có thể tăng chi phí định tuyến/quét index; cần đo thay vì mở rộng danh sách vô hạn.

### 6.4. Query chỉ theo thời gian trên toàn hệ thống

~~~javascript
metrics.find({
  "metadata.lab": tag,
  observedAt: {
    $gte: ISODate("2026-01-15T01:00:00Z"),
    $lt: ISODate("2026-01-15T01:30:00Z")
  }
}).toArray();
~~~

**Kết quả mong đợi:** **6 mẫu** (ba thiết bị × hai mốc 01:00, 01:15).

Trong lab nhỏ, query này chạy dễ dàng. Với 50.000 thiết bị, chỉ lọc thời gian mà không giới hạn metadata có thể buộc server xét rất nhiều chuỗi/buckets. Một **time index** riêng có thể hữu ích cho một số workload toàn cục, nhưng không thay thế việc đánh giá cardinality và số bucket thực tế cần đọc.

## 7. Lấy N mẫu mới nhất

### 7.1. Mẫu mới nhất của một thiết bị

~~~javascript
metrics.find(
  {
    "metadata.lab": tag,
    "metadata.tenantId": "t001",
    "metadata.deviceId": "meter-A"
  },
  {
    _id: 0,
    observedAt: 1,
    watts: 1
  }
)
.sort({ observedAt: -1 })
.limit(3)
.toArray();
~~~

**Kết quả mong đợi:**

| Thứ tự | observedAt UTC | watts |
| ---: | --- | ---: |
| 1 | 01:45 | 17 |
| 2 | 01:30 | 16 |
| 3 | 01:15 | 15 |

Nếu truy vấn này xuất hiện liên tục trong API, compound index với **equality metadata prefix + observedAt descending** là ứng viên quan trọng.

### 7.2. Khi nhiều measurement cùng timestamp

Một thiết bị có thể gửi hai bản ghi cùng observedAt. Khi chỉ sort theo observedAt, thứ tự giữa hai bản ghi cùng timestamp **không được xác định đầy đủ**.

Nếu nghiệp vụ cần thứ tự ổn định, hãy lưu field như **sequence**, **eventId** hoặc một tiêu chí tie-break có ý nghĩa:

~~~javascript
metrics.find({
  "metadata.tenantId": "t001",
  "metadata.deviceId": "meter-A"
})
.sort({ observedAt: -1, seq: -1 })
.limit(20);
~~~

**Lưu ý:** sort hai trường có thể cần thêm index hoặc sort sau khi đọc; đừng giả định index chỉ có observedAt sẽ luôn đáp ứng tie-break bằng seq mà không phát sinh công việc bổ sung.

### 7.3. Mẫu mới nhất của từng thiết bị

Đây là câu hỏi khác với “ba mẫu mới nhất toàn site”. Một cách đơn giản:

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.siteId": "hn"
    }
  },
  {
    $sort: {
      "metadata.deviceId": 1,
      observedAt: -1,
      seq: -1
    }
  },
  {
    $group: {
      _id: "$metadata.deviceId",
      latestAt: { $first: "$observedAt" },
      latestWatts: { $first: "$watts" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

**Kết quả mong đợi:** meter-A latestWatts = **17**, meter-B latestWatts = **27**, cùng timestamp 01:45 UTC.

Đừng nhầm:

~~~javascript
{ $sort: { observedAt: -1 } },
{ $limit: 2 }
~~~

với **“mỗi thiết bị lấy 2 mẫu”**. Đó là 2 mẫu **tổng cộng** sau sort, không phải 2 mẫu mỗi nhóm.

### 7.4. Với tập thiết bị lớn

Pipeline sort→group có thể tốn tài nguyên nếu cần tìm latest trên hàng triệu chuỗi. Các lựa chọn cần đánh giá:

- Tối ưu index theo metadata và thời gian.
- Giới hạn site/tenant và khoảng thời gian khi nghiệp vụ cho phép.
- Dùng accumulator như **$top/$topN** trên phiên bản hỗ trợ nếu phù hợp.
- Duy trì **latest-reading collection** riêng được cập nhật an toàn, khi API yêu cầu cực nhanh.

Nếu cập nhật latest-reading dựa trên event đến muộn, cần điều kiện **chỉ thay khi observedAt mới hơn**; không phải phép đo đến sau cùng luôn có timestamp lớn nhất.

## 8. Tổng hợp theo khoảng thời gian

### 8.1. Tính số mẫu và trung bình trong một đoạn

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.deviceId": "meter-A",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: null,
      samples: { $sum: 1 },
      minWatts: { $min: "$watts" },
      maxWatts: { $max: "$watts" },
      avgWatts: { $avg: "$watts" },
      sumOfWattsSamples: { $sum: "$watts" }
    }
  },
  { $project: { _id: 0 } }
]).toArray();
~~~

**Kết quả mong đợi:** samples = **8**, minWatts = **10**, maxWatts = **17**, avgWatts = **13,5**, sumOfWattsSamples = **108**.

**Cảnh báo đơn vị:** sumOfWattsSamples = 108 là **tổng giá trị các mẫu công suất**, không tự động là điện năng 108 Wh/kWh. Nếu mỗi mẫu đại diện cho công suất trung bình trong 15 phút không chồng lấn, một ước tính điện năng có thể là:

\[
E_{\mathrm{Wh}} \approx \sum_{i=1}^{8} P_i\;(\mathrm{W}) \times 0{,}25\;(\mathrm{h})
\]

Với dữ liệu meter-A, giá trị ước tính là **27 Wh** theo giả định mỗi mẫu đại diện cho một khoảng 15 phút đầy đủ. Nếu đây chỉ là giá trị đo tức thời, cần phương pháp tích phân/nội suy phù hợp; không được tự nhân mọi mẫu với 15 phút nếu dữ liệu không đều hoặc mất mẫu.

### 8.2. Tổng hợp theo thiết bị

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$metadata.deviceId",
      sampleCount: { $sum: 1 },
      avgWatts: { $avg: "$watts" },
      maxWatts: { $max: "$watts" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

Kết quả:

| Device | sampleCount | avgWatts | maxWatts |
| --- | ---: | ---: | ---: |
| meter-A | 8 | 13,5 | 17 |
| meter-B | 8 | 23,5 | 27 |

### 8.3. Gộp theo giờ bằng $dateTrunc

Từ MongoDB 5.0 trở lên, **$dateTrunc** là một công cụ hữu ích để lấy mốc đầu của cửa sổ thời gian:

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.deviceId": "meter-A",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$observedAt",
          unit: "hour",
          timezone: "UTC"
        }
      },
      samples: { $sum: 1 },
      avgWatts: { $avg: "$watts" },
      maxWatts: { $max: "$watts" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
~~~

**Kết quả mong đợi:**

| Giờ bắt đầu UTC | samples | avgWatts | maxWatts |
| --- | ---: | ---: | ---: |
| 00:00 | 4 | 11,5 | 13 |
| 01:00 | 4 | 15,5 | 17 |

Phép nhóm này diễn ra trên các measurement đã được lọc, **không có nghĩa MongoDB tự lưu mỗi giờ thành một document nghiệp vụ**.

### 8.4. Nhóm theo thiết bị và giờ

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.siteId": "hn",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        deviceId: "$metadata.deviceId",
        hour: {
          $dateTrunc: {
            date: "$observedAt",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      samples: { $sum: 1 },
      avgWatts: { $avg: "$watts" }
    }
  },
  {
    $sort: {
      "_id.deviceId": 1,
      "_id.hour": 1
    }
  }
]).toArray();
~~~

Kết quả có **4 nhóm**:

| Device | Giờ UTC | samples | avgWatts |
| --- | --- | ---: | ---: |
| meter-A | 00:00 | 4 | 11,5 |
| meter-A | 01:00 | 4 | 15,5 |
| meter-B | 00:00 | 4 | 21,5 |
| meter-B | 01:00 | 4 | 25,5 |

### 8.5. Chỉ lấy phép đo đạt chất lượng

Nếu quality = "suspect" cần bỏ khỏi báo cáo:

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.deviceId": "meter-B",
      quality: "ok",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: null,
      samples: { $sum: 1 },
      avgWatts: { $avg: "$watts" }
    }
  }
]).toArray();
~~~

Trong lab, meter-B có một mẫu quality = "suspect" ở **00:45**, watts = 23. Vì vậy kết quả gồm **7 mẫu**, tổng watts = 188 - 23 = **165**, trung bình khoảng **23,5714**.

**Filter quality là measurement predicate** chứ không phải metadata predicate. Nó có thể cần xử lý ở mức measurement sau bucket pruning, trừ khi server/index hỗ trợ đẩy lọc thêm. Không giả định mọi predicate có độ chọn lọc như nhau.

## 9. Time zones, ngày theo địa phương và DST

### 9.1. Lưu mốc thời gian nhất quán

BSON Date là một điểm thời gian tuyệt đối với độ phân giải mili giây. Khi hiển thị, client có thể chuyển sang múi giờ người dùng.

Khuyến nghị:

- Ghi thời điểm từ nguồn có clock được quản lý đúng.
- Dùng UTC khi biểu diễn hoặc đối chiếu hệ thống.
- Chuyển ngày giờ địa phương sang UTC **trước khi tạo filter**.
- Xác định múi giờ báo cáo bằng tên vùng IANA khi cần xử lý DST, chẳng hạn **Asia/Ho_Chi_Minh** hoặc **America/New_York**.

Đừng lưu ngày giờ địa phương không kèm timezone như một String rồi coi nó là timestamp hoàn chỉnh.

### 9.2. Một ngày ở Việt Nam không bắt đầu lúc 00:00 UTC

Ví dụ ngày **15/01/2026** tại Việt Nam (UTC+07:00):

~~~text
Bắt đầu địa phương:
  2026-01-15 00:00:00 +07:00
=> UTC:
  2026-01-14 17:00:00Z

Kết thúc nửa mở địa phương:
  2026-01-16 00:00:00 +07:00
=> UTC:
  2026-01-15 17:00:00Z
~~~

Filter:

~~~javascript
metrics.find({
  "metadata.tenantId": "t001",
  observedAt: {
    $gte: ISODate("2026-01-14T17:00:00Z"),
    $lt: ISODate("2026-01-15T17:00:00Z")
  }
});
~~~

Tập dữ liệu lab đều nằm trong ngày 15/01 UTC từ 00:00 đến 01:45, nên đều thuộc ngày 15/01 theo giờ Việt Nam. Nhưng trong production, nếu chỉ thay ngày trong chuỗi UTC mà quên +07:00, báo cáo có thể sai ở đầu/cuối ngày.

### 9.3. $dateTrunc theo múi giờ

~~~javascript
{
  $dateTrunc: {
    date: "$observedAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Đoạn này nhóm theo **ngày lịch địa phương**, không đơn giản bằng cách trừ bảy giờ cho mọi timestamp. Một số múi giờ có thay đổi DST, dẫn tới ngày không phải lúc nào cũng dài đúng 24 giờ.

### 9.4. Không đo latency bằng cách trừ bừa clusterTime

Nếu hệ thống ingest từ thiết bị, hãy dùng **observedAt** và **ingestedAt** có ý nghĩa rõ để tính độ trễ dữ liệu. Timestamp logic của oplog hoặc các field replication khác không mặc nhiên là thời điểm thiết bị thực sự đo.

## 10. Thiết kế index bắt đầu từ query patterns

### 10.1. Một workload minh họa

Giả sử hệ thống có những truy vấn chính:

| ID | Câu hỏi | Điều kiện chủ yếu | Sort/Output |
| --- | --- | --- | --- |
| Q1 | Lịch sử một sensor | tenantId + deviceId + time range | observedAt tăng dần |
| Q2 | 20 mẫu mới nhất | tenantId + deviceId | observedAt giảm dần, limit 20 |
| Q3 | Đường biểu diễn một site | tenantId + siteId + time range | group theo device và giờ |
| Q4 | Thống kê toàn tenant theo một ngày | tenantId + time range | group và average |
| Q5 | Tổng toàn hệ thống theo giờ | time range | group theo giờ |
| Q6 | Mẫu bị lỗi chất lượng | tenantId + quality + time range | count/thiết bị |
| Q7 | Latest của mọi sensor tại site | tenantId + siteId | sort/group theo device |
| Q8 | Tra cứu một mẫu theo ID nghiệp vụ | tenantId + deviceId + observedAt + seq | trả một record |

Không nên tạo index chỉ vì một field xuất hiện trong document. Hãy ghi lại **tần suất, số dòng trả, khoảng thời gian, cardinality metadata và SLA** của từng Q.

### 10.2. Filter equality trước, thời gian range sau

Với Q1/Q2, index ứng viên:

~~~javascript
{
  "metadata.tenantId": 1,
  "metadata.deviceId": 1,
  observedAt: -1
}
~~~

Ý nghĩa:

1. **tenantId equality** thu hẹp tập dữ liệu.
2. **deviceId equality** xác định chuỗi đo.
3. **observedAt** giúp truy cập có thứ tự thời gian, đặc biệt cho latest-N hoặc time range.

Đây là vận dụng trực giác **equality trước, range/sort sau**, nhưng time series collection có hệ thống bucket và optimizer riêng, nên **không suy luận chắc chắn query plan chỉ từ lý thuyết B-tree trên collection thường**.

### 10.3. Với Q3 theo site

Một ứng viên khác:

~~~javascript
{
  "metadata.tenantId": 1,
  "metadata.siteId": 1,
  observedAt: -1
}
~~~

Nó có thể hỗ trợ filter theo tenant + site + time range. Nhưng query còn phải **group theo deviceId**, nên việc sort/group và giải nén measurements vẫn có chi phí.

Nếu Q7 “latest per device” rất thường xuyên, có thể cân nhắc index với **deviceId** trước observedAt trong nhóm site:

~~~javascript
{
  "metadata.tenantId": 1,
  "metadata.siteId": 1,
  "metadata.deviceId": 1,
  observedAt: -1
}
~~~

Không tạo đồng thời mọi biến thể ngay lập tức. Cần xác định query nào đáng tối ưu và lợi ích vượt chi phí index hay không.

### 10.4. Với Q5 chỉ theo thời gian

Một index trên:

~~~javascript
{ observedAt: -1 }
~~~

có thể giúp một số truy vấn dựa vào thời gian toàn cluster/collection, tùy phiên bản và plan. Nhưng nếu sản phẩm hầu như luôn yêu cầu tenant/device, index chỉ thời gian có thể kém hữu ích so với compound index metadata+time.

### 10.5. Với Q6 measurement filter

~~~javascript
{
  "metadata.tenantId": 1,
  quality: 1,
  observedAt: -1
}
~~~

là một ứng viên cần **xác minh hỗ trợ index trên measurement field** ở phiên bản time series collection đang chạy. Các đời MongoDB khác nhau có hạn chế khác nhau đối với secondary indexes, partial indexes và các loại index.

Nếu Q6 hiếm hoặc chỉ xét khoảng rất hẹp, trước tiên có thể dùng **metadata + time range** để giảm số bucket, rồi filter quality sau khi đọc measurements. Không nhất thiết tạo index riêng cho mọi quality/status field.

## 11. Default index và index tùy chỉnh trên time series

### 11.1. Time series collection có index mặc định gì?

Các phiên bản MongoDB hiện đại, đặc biệt **từ MongoDB 6.3**, có cơ chế tạo **compound index mặc định trên metaField và timeField** cho time series collection mới (hoặc index thích hợp theo cấu hình khi không có metaField).

Tuy nhiên:

- Không phải mọi collection lịch sử được tạo ở version cũ tự có cùng index sau nâng cấp.
- Không thể coi default index là phù hợp nhất cho mọi **metadata subfield** query.
- Một index trên toàn object **metadata** khác với một compound index trên **metadata.tenantId** và **metadata.deviceId**.
- Index được biểu diễn trên logical time series collection nhưng query planner có thể làm việc với **bucket-level** index nội bộ.

**Hãy kiểm tra thực tế bằng getIndexes()**, không đoán từ tên collection.

~~~javascript
printjson(metrics.getIndexes());
~~~

### 11.2. Tạo index theo Q1/Q2

Trên lab, nếu server/version hỗ trợ hình dạng index này:

~~~javascript
metrics.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.deviceId": 1,
    observedAt: -1
  },
  { name: "ix_ts_tenant_device_time_desc" }
);
~~~

Nếu createIndex báo không hỗ trợ trên version đó, **không sửa trực tiếp system.buckets**. Đọc tài liệu **time series secondary indexes** đúng server version, rồi thay đổi design hoặc cân nhắc nâng cấp theo quy trình.

### 11.3. Tạo index theo Q3

~~~javascript
metrics.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.siteId": 1,
    observedAt: -1
  },
  { name: "ix_ts_tenant_site_time_desc" }
);
~~~

Đây là ví dụ một bộ index nhỏ dựa trên hai access patterns chính: thiết bị cụ thể và nhóm thiết bị theo site.

### 11.4. Kiểm tra danh sách index

~~~javascript
printjson(
  metrics.getIndexes().map(i => ({
    name: i.name,
    key: i.key
  }))
);
~~~

Nếu một index có sẵn với cùng key pattern, không cần tạo index trùng lặp chỉ để đặt tên mới. Nếu một index không được planner dùng, kiểm tra query shapes trước khi kết luận “index sai”.

### 11.5. Index ascending hay descending?

Với truy vấn:

~~~javascript
{
  "metadata.tenantId": "t001",
  "metadata.deviceId": "meter-A"
}
~~~

và sort **observedAt:-1**, index có suffix descending là một ứng viên tự nhiên. Trong một số query shape, MongoDB có thể duyệt index theo hướng ngược để phục vụ sort tương ứng. Nhưng với compound index và điều kiện range/metadata phức tạp, cần xem kế hoạch thực tế, không chỉ đếm dấu +1/-1.

**Đừng tạo cả ascending và descending chỉ vì API có hai nút “cũ trước/mới trước”** khi một index có thể được duyệt ngược hiệu quả. Hãy xác minh explain và yêu cầu sort tổng thể.

## 12. Hiểu compound index và prefix

### 12.1. Prefix quan trọng

Index:

~~~javascript
{
  "metadata.tenantId": 1,
  "metadata.deviceId": 1,
  observedAt: -1
}
~~~

có thứ tự khóa:

~~~text
tenantId -> deviceId -> observedAt
~~~

Nó là ứng viên mạnh khi query có equality trên tenantId và deviceId, sau đó truy vấn/sort theo observedAt.

Nếu query chỉ có tenantId và khoảng observedAt mà **không có deviceId**, các key cho nhiều device xen giữa. Planner có thể không dùng suffix time như một khoảng duy nhất tối ưu. Trong trường hợp đó, một index **tenantId + observedAt** khác có thể đáng giá nếu workload Q4 quan trọng.

### 12.2. So sánh ba index theo query

| Index | Q1 một thiết bị | Q3 một site | Q4 cả tenant |
| --- | --- | --- | --- |
| tenantId, deviceId, time | Rất phù hợp làm ứng viên | Thiếu siteId trong prefix | Suffix time sau deviceId có thể kém thuận lợi |
| tenantId, siteId, time | Không tối ưu riêng cho deviceId nếu site không được lọc | Phù hợp làm ứng viên | Time sau siteId có thể kém thuận lợi |
| tenantId, time | Có thể dùng, nhưng đọc nhiều devices trong tenant | Có thể dùng, nhưng lọc site thêm | Phù hợp hơn cho Q4 |

Đây là **phân tích thiết kế**, không phải một bảng đảm bảo kế hoạch thực thi. Time series planner xét bucket metadata, thống kê và chi phí riêng.

### 12.3. Không kết luận overlap đơn giản như collection thường

Với collection thường, index compound có thể bao phủ một số prefix của index ngắn hơn, nhưng đối với time series collection:

- Index được ánh xạ và sử dụng qua cấu trúc bucket.
- Các trường metaField con và cả metaField object có thể có semantics khác nhau.
- Một số loại index bị hạn chế theo version.
- Query shape có thể thay đổi việc optimizer đẩy filter.

Vì vậy, việc drop một index đang có cần **getIndexes, $indexStats (nếu hỗ trợ), explain, workload thực và quy trình rollback**, không xóa theo trực giác “tên nhìn giống nhau”.

### 12.4. Chi phí của nhiều index

Mỗi index thêm có thể:

- Chiếm disk/memory.
- Tăng I/O và công việc bảo trì khi ghi measurements/buckets.
- Tốn thời gian build, ảnh hưởng tài nguyên.
- Làm query planning phức tạp khi có nhiều ứng viên.
- Có chi phí vận hành khi nâng cấp, retention hoặc dữ liệu tăng nhanh.

Với time series ingest liên tục, **over-indexing** có thể tác động trực tiếp tới throughput. Hãy bắt đầu với những query chiếm lưu lượng/SLA chính, rồi đo trước khi mở rộng.

## 13. Đọc explain trên time series collection

### 13.1. Explain của truy vấn một thiết bị

~~~javascript
const plan = metrics.find({
  "metadata.lab": tag,
  "metadata.tenantId": "t001",
  "metadata.deviceId": "meter-A",
  observedAt: {
    $gte: ISODate("2026-01-15T00:30:00Z"),
    $lt: ISODate("2026-01-15T01:30:00Z")
  }
})
.sort({ observedAt: -1 })
.explain("executionStats");

printjson(plan);
~~~

Đọc các nhóm thông tin:

| Thông tin | Câu hỏi cần trả lời |
| --- | --- |
| **winningPlan / stages** | Query đang thực thi qua những stage nào? |
| **IXSCAN/COLLSCAN** | Có truy cập bucket theo index hay quét rộng? |
| **$_internalUnpackBucket** hoặc stage tương tự | Có bước giải nén/chuyển bucket thành measurement không? |
| **totalKeysExamined** | Bao nhiêu index keys được xét? |
| **totalDocsExamined** | Bao nhiêu document/bucket được xét ở phần kế hoạch tương ứng? |
| **nReturned** | Bao nhiêu measurement cuối cùng được trả? |
| **SORT** | Có cần sort ngoài index? |
| **executionTimeMillis** | Độ trễ của lần thực thi được đo trong bối cảnh explain |

**Không nhất thiết nhìn thấy cùng stage name** giữa các phiên bản MongoDB, query engine hoặc loại filter. Mô tả trực giác về bucket pruning vẫn hữu ích, nhưng hãy để explain thực tế xác nhận.

### 13.2. Vì sao đọc 10 bucket khác đọc 10 measurements?

Một bucket có thể chứa nhiều measurements. Nếu explain báo:

~~~text
totalDocsExamined = 10
~~~

trong phần scan bucket nội bộ, **không được kết luận** chỉ có 10 measurements được đọc/đánh giá. Một số metric đếm bucket-level document, trong khi **nReturned** sau unpack/filter phản ánh số measurement được trả.

Để đánh giá hiệu quả, nhìn tổng thể:

- Bao nhiêu buckets được duyệt và unpack?
- Bao nhiêu measurements thực sự khớp?
- Bao nhiêu bytes được đọc/giải nén?
- Có sort/group lớn sau unpack không?
- Có dùng index phù hợp với metadata/time range không?

### 13.3. Bucket pruning

Với filter:

~~~javascript
{
  "metadata.deviceId": "meter-A",
  observedAt: {
    $gte: ISODate("2026-01-15T00:30:00Z"),
    $lt: ISODate("2026-01-15T01:30:00Z")
  }
}
~~~

MongoDB có thể dùng metadata và min/max time của bucket để loại những bucket chắc chắn không thể chứa dữ liệu khớp.

Tuy nhiên, một bucket có minTime/maxTime giao với khoảng query vẫn có thể chứa **nhiều measurements ngoài khoảng**. Bộ lọc trên individual measurement vẫn cần thiết sau unpack. Do đó, loại bucket không tương đương phép lọc chính xác mọi measurement chỉ bằng metadata.

### 13.4. So sánh hai query shapes

~~~javascript
const filterByDevice = {
  "metadata.lab": tag,
  "metadata.tenantId": "t001",
  "metadata.deviceId": "meter-A",
  observedAt: {
    $gte: ISODate("2026-01-15T00:00:00Z"),
    $lt: ISODate("2026-01-15T02:00:00Z")
  }
};

const filterGlobal = {
  "metadata.lab": tag,
  observedAt: {
    $gte: ISODate("2026-01-15T00:00:00Z"),
    $lt: ISODate("2026-01-15T02:00:00Z")
  }
};

printjson(
  metrics.find(filterByDevice).explain("executionStats")
);

printjson(
  metrics.find(filterGlobal).explain("executionStats")
);
~~~

Trong lab chỉ có 24 measurement, thời gian chạy nhỏ và thống kê optimizer có thể chưa mang ý nghĩa benchmark. Ở production với hàng triệu devices, query có metadata hẹp thường có cơ hội loại nhiều bucket hơn. Dùng dữ liệu đại diện để đo sự khác biệt.

### 13.5. Dùng hint có điều kiện

Với MongoDB version và index hỗ trợ hint trên time series query, có thể thử đối chiếu một index cụ thể:

~~~javascript
const result = metrics.find(filterByDevice)
  .hint("ix_ts_tenant_device_time_desc")
  .explain("executionStats");

printjson(result);
~~~

Đoạn này yêu cầu index **ix_ts_tenant_device_time_desc** đã được tạo thành công ở mục 11. Nếu index chưa tồn tại hoặc version hạn chế hint, lệnh có thể lỗi; đó là điều kiện môi trường, không phải chứng minh workload không dùng index.

**Hint là công cụ chẩn đoán**, không nên hardcode cho mọi query production chỉ sau một lần explain trên 24 mẫu.

## 14. Granularity, bucket span và hiệu năng

### 14.1. Granularity không làm thay timestamp

~~~javascript
timeseries: {
  timeField: "observedAt",
  metaField: "metadata",
  granularity: "seconds"
}
~~~

**granularity** giúp MongoDB chọn chính sách bucket/nhóm dữ liệu theo tần suất thời gian của workload. Nó **không** chuyển:

~~~text
00:15:30 -> 00:00:00
~~~

trong logical result. Thời điểm measurement vẫn là giá trị đã ghi.

### 14.2. Chọn độ hạt theo chu kỳ dữ liệu

Khái quát:

| Loại chuỗi | Tần suất đo | Độ hạt cần cân nhắc |
| --- | --- | --- |
| Telemetry mỗi vài giây | Dày | "seconds" |
| Dữ liệu mỗi phút/giờ | Trung bình | "minutes" hoặc theo cấu hình phù hợp |
| Một vài phép đo mỗi ngày | Thưa | "hours" hoặc thiết kế phù hợp |

Đây là **gợi ý thiết kế**, không phải công thức cứng. Cấu hình bucket span và rounding có những khả năng/giới hạn theo phiên bản. Nên thử trên dữ liệu gần production và kiểm tra mục tiêu nén, query pruning và ingest.

### 14.3. Buckets quá nhỏ hoặc quá rộng

Bucket quá phân mảnh có thể gây:

- Nhiều bucket documents và metadata overhead.
- Tốn thêm index entries và công việc đọc.
- Nén kém nếu số measurement trong mỗi bucket rất ít.

Bucket quá rộng có thể gây:

- Đọc/giải nén nhiều measurement ngoài khoảng truy vấn.
- Khó loại bucket theo time range ngắn.
- Chi phí với late-arriving data hoặc retention trong một số trường hợp.

Hãy đo trade-off theo **query window phổ biến**. Nếu API thường xem 5 phút dữ liệu, tổ chức bucket chỉ tối ưu cho báo cáo một năm có thể không phù hợp.

### 14.4. Cardinality metadata ảnh hưởng bucket

Nếu mỗi phép đo có metadata hoàn toàn mới, MongoDB khó tận dụng một bucket dài cho chuỗi ổn định. Với 1 triệu phép đo đều có requestUuid khác nhau trong metadata, số nhóm metadata có thể rất lớn.

Chọn metadata ít thay đổi nhưng vẫn đủ để **phân biệt các nguồn cần truy vấn**. Không gộp tất cả thiết bị vào một metadata object giống nhau chỉ để tiết kiệm bucket, vì mất khả năng lọc chuỗi.

### 14.5. Không sửa bucket vật lý để tối ưu

Nếu muốn thay cấu hình granularity/bucket span, làm theo **API và quy tắc phiên bản MongoDB**. Một số thay đổi có hạn chế chiều thay đổi hoặc yêu cầu collection mới/migration. Không chỉnh trực tiếp namespace system.buckets.

## 15. TTL và retention ảnh hưởng truy vấn

### 15.1. Retention là yêu cầu nghiệp vụ

Telemetry có thể có vòng đời:

~~~text
Raw measurements: lưu 30 ngày
Hourly aggregates: lưu 1 năm
Daily aggregates: lưu 5 năm
~~~

Nếu cần xem lại dữ liệu từ sáu tháng trước, nhưng raw measurements chỉ giữ 30 ngày, truy vấn sẽ trả rỗng dù index rất tốt. **Index không thể phục hồi dữ liệu đã bị retention xóa.**

### 15.2. TTL trên time series collection

MongoDB hỗ trợ TTL/retention cho time series collection, ví dụ cấu hình ở thời điểm tạo collection:

~~~javascript
// VÍ DỤ THIẾT KẾ CHO COLLECTION MỚI, KHÔNG CHẠY TRÊN LAB 24 MẪU.
db.createCollection("metricsRetained30Days", {
  timeseries: {
    timeField: "observedAt",
    metaField: "metadata",
    granularity: "minutes"
  },
  expireAfterSeconds: 30 * 24 * 60 * 60
});
~~~

**expireAfterSeconds** biểu thị khoảng tuổi tối đa mong muốn của dữ liệu theo semantics TTL time-series collection. Việc cleanup là **bất đồng bộ** và có liên quan tới bucket, nên không thể coi thời điểm hết hạn là một thao tác xóa đồng bộ chính xác đến từng mili giây.

### 15.3. Một bucket chứa nhiều timestamp

Khi bucket chứa các mẫu ở nhiều thời điểm, MongoDB phải xét điều kiện hết hạn theo cơ chế bucket. Vì vậy dữ liệu có thể còn tồn tại một khoảng sau khi một measurement riêng lẻ đã vượt tuổi TTL mong muốn.

Nếu sản phẩm yêu cầu dữ liệu biến mất **ngay tại một mili giây chính xác**, TTL time series không phải một giao thức xóa theo deadline tuyệt đối; cần thiết kế policy truy vấn/xóa và xác minh quy tắc server.

### 15.4. Partial TTL theo metadata

Trên những phiên bản hỗ trợ, time series có thể có những dạng **partial TTL index** gắn điều kiện metadata, hữu ích khi các nhóm thiết bị có thời hạn lưu khác nhau. Tuy nhiên, cú pháp và giới hạn hỗ trợ bị ràng buộc bởi version/field types.

Không tùy tiện tạo TTL index trên một measurement field rồi kỳ vọng nó hoạt động như một TTL thông thường của collection. Khi cần retention khác nhau theo tenant, hãy cân nhắc **collection separation, chính sách retention rõ ràng hoặc partial TTL được phiên bản hỗ trợ**.

### 15.5. Raw vs downsampled data

Một thiết kế phổ biến:

~~~text
lab_metrics_raw
   mỗi 15 phút một mẫu
       |
       | job aggregation
       v
lab_metrics_hourly
   mỗi giờ một document/tổ hợp thống kê
       |
       | job aggregation
       v
lab_metrics_daily
~~~

Nếu cần biểu đồ một năm, query daily/hourly aggregates thường rẻ hơn việc đọc toàn bộ raw measurements. Nhưng phải xác định:

- Có cần min/max hay chỉ average?
- Cách xử lý missing/late data.
- Timezone của cửa sổ ngày.
- Có cần cập nhật lại aggregate khi mẫu cũ đến muộn?
- Tính toán điện năng có dùng chu kỳ lấy mẫu đúng không?

Đừng lưu mỗi average mà sau đó cố suy ra tổng sản lượng chính xác khi thiếu **sampleCount** hoặc thông tin diện tích thời gian.

## 16. Khoảng thời gian không có mẫu và resampling

### 16.1. $group không tự tạo bucket thời gian rỗng

Nếu meter-A có mẫu lúc 00:00, 00:15, 00:45 nhưng **thiếu 00:30**, một pipeline group theo khung 15 phút có thể không có hàng cho 00:30.

Không có hàng là **khác với watts = 0**.

Trong monitoring:

- **watts=0:** thiết bị có phép đo xác nhận 0 W.
- **missing:** không có phép đo; có thể thiết bị offline hoặc lỗi ingest.
- **null:** giá trị thiếu/không hợp lệ tùy schema.

Không nội suy missing thành zero nếu yêu cầu nghiệp vụ không cho phép.

### 16.2. $densify và $fill

Các phiên bản MongoDB hỗ trợ những stage như **$densify** và **$fill** để tạo/làm đầy những khoảng bị thiếu trong pipeline; hãy kiểm tra version và khả năng sử dụng với time series collection trước khi triển khai.

Ví dụ minh họa ý định resampling, sau bước lọc một device:

~~~javascript
metrics.aggregate([
  {
    $match: {
      "metadata.lab": tag,
      "metadata.tenantId": "t001",
      "metadata.deviceId": "meter-A",
      observedAt: {
        $gte: ISODate("2026-01-15T00:00:00Z"),
        $lt: ISODate("2026-01-15T02:00:00Z")
      }
    }
  },
  { $sort: { observedAt: 1 } },
  {
    $densify: {
      field: "observedAt",
      range: {
        step: 15,
        unit: "minute",
        bounds: [
          ISODate("2026-01-15T00:00:00Z"),
          ISODate("2026-01-15T02:00:00Z")
        ]
      }
    }
  },
  {
    $project: {
      _id: 0,
      observedAt: 1,
      watts: 1
    }
  }
]).toArray();
~~~

Lab gốc đã có đủ tám mốc của meter-A, nên ví dụ không chứng minh interpolation; nó minh họa cú pháp tạo mốc chuẩn. Với dữ liệu không đều hoặc missing thật, có thể có những document sinh thêm **không có watts**.

**Ranh giới bounds của $densify có semantics riêng**, không được mặc định chính xác giống filter [start,end) cho mọi phiên bản. Nếu ứng dụng cần tám mốc và không muốn 02:00, hãy kiểm tra output và thêm $match cuối theo khoảng nửa mở phù hợp.

### 16.3. Nội suy có thể làm sai dữ liệu

Một biểu đồ có thể dùng:

- **Forward-fill**: lấy giá trị gần nhất đã biết.
- **Linear interpolation**: nội suy theo các điểm hai bên.
- **Null gap**: để đường biểu đồ đứt.
- **Zero-fill**: chỉ khi nghiệp vụ cho phép.

Một trường nhiệt độ và một trường công suất có thể cần cách xử lý khác nhau. Đừng để lựa chọn $fill tạo ra thông tin giả mà người dùng hiểu như phép đo thật.

## 17. Sharding time series và truy vấn theo metadata

### 17.1. Shard key cho time series có giới hạn riêng

Time series collection có khả năng sharding trên các phiên bản MongoDB hỗ trợ, nhưng **các thành phần được dùng trong shard key và các loại shard key được phép thay đổi theo phiên bản**.

Đặc biệt, các lựa chọn về **metaField**, subfield của metaField, timeField và hashed key cần kiểm tra tài liệu chính thức hiện hành. Không bê nguyên shard key của collection thường vào time series mà chưa xác minh hỗ trợ.

### 17.2. Query target được shard nào?

Nếu shard key tận dụng **metadata.tenantId/deviceId** và query có filter tương ứng, mongos có thể định tuyến hẹp theo metadata/range.

Nếu API chỉ gửi:

~~~javascript
{ observedAt: { $gte: start, $lt: end } }
~~~

trong khi shard key dựa trên metadata, request có thể phải **scatter-gather** qua nhiều shards.

### 17.3. Vấn đề hot shard

Chọn shard key **chỉ dựa trên thời gian tăng đều** có thể dồn mọi phép đo mới vào một vùng dữ liệu nóng; lựa chọn này còn có ràng buộc/hướng dẫn phiên bản đối với time series. Một metadata field cardinality thấp cũng có thể làm tải không đều.

Hãy đánh giá:

- Số chuỗi đo hoạt động đồng thời.
- Thiết bị/tenant nào chiếm ingest nhiều nhất.
- Query thường biết metadata đến mức nào.
- Phân bố dữ liệu theo thời gian.
- Chi phí khi query toàn tenant/toàn cluster.

### 17.4. Replica set và index trên từng shard

Trong sharded cluster, một shard thường là một replica set. **Mỗi shard lưu phần dữ liệu time series được phân công và những index liên quan**. mongos định tuyến/hợp nhất request.

Không thể suy luận “một time index toàn cluster” như một index B-tree vật lý duy nhất chứa tất cả document ở mọi shard.

### 17.5. Query rộng vẫn có giá

Một dashboard đòi so sánh mọi thiết bị ở mọi tenant trong một năm có thể cần scan/group dữ liệu trải nhiều shards. Khi tần suất cao, cân nhắc **summary collection** hoặc kho phân tích riêng, thay vì buộc raw time-series collection trả một query toàn cầu quá lớn sau mỗi vài giây.

## 18. Measurement update, delete và dữ liệu chỉnh sửa

### 18.1. Dữ liệu time series thường append-heavy

Thiết kế time series thích hợp nhất khi **ghi thêm measurements theo thời gian**. Những thao tác update/delete trên time series có các giới hạn và khả năng khác nhau theo phiên bản; một số đời MongoDB hạn chế update/delete theo metadata hoặc có quy định riêng về loại field được chỉnh.

**Không giả định** time series có đầy đủ semantics updateOne/replaceOne/upsert như một collection thông thường trong mọi bản MongoDB.

### 18.2. Nếu cảm biến gửi lại một mẫu bị sai

Các chiến lược thường gặp:

- Ghi bản correction event với **originalSampleId, correctedValue, correctedAt**.
- Dùng cơ chế sửa dữ liệu được phiên bản time series hỗ trợ, khi hợp đồng cho phép.
- Lưu dữ liệu raw bất biến và áp correction khi tổng hợp.
- Sửa dữ liệu ở một collection staging/normalized nếu yêu cầu cập nhật thường xuyên.

Ví dụ một document correction logic:

~~~javascript
{
  originalSampleId: "ts285-meter-A-3",
  observedAt: ISODate("2026-01-15T00:45:00Z"),
  correctedAt: ISODate("2026-01-15T03:00:00Z"),
  oldWatts: 13,
  newWatts: 12.8,
  reason: "sensor-calibration"
}
~~~

Đây là schema nghiệp vụ tham khảo, không phải format MongoDB bắt buộc.

### 18.3. Trùng phép đo

Nếu sensor retry một lệnh insert khi mạng lỗi, có thể xuất hiện mẫu trùng theo **(deviceId, observedAt, seq)**. Với time series collection, các hạn chế của unique index có thể khiến bạn **không dùng được một unique constraint tùy ý trên bộ field** như collection thường.

Hãy thiết kế idempotency ở tầng ingest:

- Khóa business sampleId do thiết bị/ingest tạo ổn định.
- Collection tiếp nhận có unique index nếu cần kiểm tra cứng.
- Dedup trong pipeline nhập liệu.
- Quy trình đối soát những mẫu trùng đã lưu.

Không cho rằng **_id trong time series** luôn có cùng unique-index behavior như một collection thường ở mọi phiên bản.

### 18.4. Dữ liệu đến muộn và bucket

Late-arriving measurements có timestamp cũ so với thời điểm ingest. Điều này có thể tác động lựa chọn bucket và hiệu quả nén/lưu trữ. Khi dữ liệu đến quá lệch thời gian:

- Theo dõi tỷ lệ late arrivals.
- Xác định retention dựa trên observedAt hay ingestedAt theo nghiệp vụ.
- Cập nhật lại các hourly/daily aggregates nếu cần.
- Tránh dựa vào thời gian nhận để quyết định “đây là mẫu mới nhất”.

## 19. Lựa chọn index theo một ma trận workload

### 19.1. Bảng đề xuất ban đầu

| Workload | Filter | Index ứng viên | Ghi chú |
| --- | --- | --- | --- |
| Q1: đọc lịch sử device | tenant + device + time | tenant, device, observedAt | Ưu tiên |
| Q2: latest 20 | tenant + device | tenant, device, observedAt desc | Có thể dùng cùng Q1 |
| Q3: site chart | tenant + site + time | tenant, site, observedAt | Cân nhắc nếu Q3 thường xuyên |
| Q4: tenant hourly rollup | tenant + time | tenant, observedAt | Nếu Q4 đủ lớn/tần suất cao |
| Q5: global time report | time | observedAt | Có thể vẫn rất rộng, cân nhắc rollup |
| Q6: quality errors | tenant + quality + time | tùy version, tenant + quality + time | Chỉ khi tỷ lệ/chi phí xứng đáng |
| Q7: latest mỗi device | tenant + site, sort theo device/time | tenant, site, device, observedAt | Đo so với materialized latest view |
| Q8: event ID lookup | device + timestamp + seq | index theo khóa nghiệp vụ/collection riêng | Time series không nên thay thế key-value store |

### 19.2. Bộ index tối giản cho lab

Trong lab, tạo hai index phục vụ workload phổ biến:

~~~javascript
metrics.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.deviceId": 1,
    observedAt: -1
  },
  {
    name: "ix_ts_tenant_device_time_desc"
  }
);

metrics.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.siteId": 1,
    observedAt: -1
  },
  {
    name: "ix_ts_tenant_site_time_desc"
  }
);
~~~

Đây là các ví dụ **khi version server hỗ trợ**. Nếu lệnh báo index đã tồn tại với cùng tên, không cần tạo lại; nếu nó báo index đã có khác key, hãy kiểm tra bằng getIndexes thay vì drop một cách mù quáng.

### 19.3. Khi nào thêm index thứ ba?

Không trả lời bằng cảm giác. Hãy lập:

~~~text
Q4 tenant+time chiếm:
  35% tổng lượt query
  p95 latency 800 ms
  target SLA p95 150 ms

Index hiện tại:
  tenant+device+time
  tenant+site+time

Thử ứng viên:
  tenant+time

So sánh:
  executionStats, số bucket/keys examined,
  latency, ingest throughput và disk footprint.
~~~

Nếu index mới giúp Q4 nhưng làm ingest chậm quá mức, có thể **pre-aggregate hourly** thay vì giữ index mới. Một quyết định hiệu năng tốt tối ưu **tổng chi phí hệ thống**, không chỉ một truy vấn.

## 20. Kiểm tra query và vận hành production

### 20.1. Luôn có giới hạn thời gian hợp lý

Một API được dùng bởi hàng nghìn request/giây không nên cho client tùy ý query từ MinKey đến MaxKey hoặc cả mười năm dữ liệu raw.

Ví dụ phía ứng dụng:

~~~javascript
function buildRange(start, end, maxDays = 31) {
  const startMs = start.getTime();
  const endMs = end.getTime();
  const maxMs = maxDays * 24 * 60 * 60 * 1000;

  if (
    !Number.isFinite(startMs) ||
    !Number.isFinite(endMs) ||
    endMs <= startMs ||
    endMs - startMs > maxMs
  ) {
    throw new Error("Khoảng thời gian không hợp lệ/quá rộng");
  }

  return {
    $gte: start,
    $lt: end
  };
}
~~~

Đây là hàm JavaScript chung; khi chạy với Date object hợp lệ, nó trả MongoDB query range. Nó không phải cơ chế bảo mật duy nhất; tenant và device filter vẫn phải được xác thực.

### 20.2. Projection và giới hạn số kết quả

~~~javascript
metrics.find(
  {
    "metadata.tenantId": "t001",
    "metadata.deviceId": "meter-A",
    observedAt: {
      $gte: ISODate("2026-01-15T00:00:00Z"),
      $lt: ISODate("2026-01-15T02:00:00Z")
    }
  },
  {
    _id: 0,
    observedAt: 1,
    watts: 1
  }
)
.sort({ observedAt: -1 })
.limit(100)
.toArray();
~~~

Projection giúp giảm dữ liệu truyền qua mạng, nhưng không mặc nhiên khiến query **covered** nếu phải unpack bucket hoặc đọc các field khác nội bộ. Hãy kiểm tra explain trước khi khẳng định không cần fetch dữ liệu.

### 20.3. Phân trang theo thời gian

Với lịch sử dài, **skip rất lớn** có thể tốn công vì phải đi qua nhiều kết quả trước khi trả trang sau. Khi dữ liệu có timestamp và tie-breaker ổn định, có thể dùng **keyset pagination**:

~~~text
Trang 1:
  filter tenant/device
  sort observedAt DESC, seq DESC
  limit 50

Trang 2:
  thêm điều kiện:
    observedAt < lastObservedAt
    OR (observedAt == lastObservedAt AND seq < lastSeq)
~~~

Điều kiện này cần:

- Khóa sort ổn định và phù hợp schema.
- Index/plan được đo đối với OR/range.
- Tham số trang được ký/kiểm tra để không sửa tenant/scope.
- Quy ước khi dữ liệu mới đến hoặc late-arriving data được thêm.

Không hứa rằng keyset pagination cho một tập time-series đang thay đổi luôn tạo **snapshot bất biến** giữa các trang, trừ khi ứng dụng có cơ chế snapshot/mốc dữ liệu riêng.

### 20.4. Khi đọc nhiều sensors

Một API nhận danh sách 10.000 deviceIds có thể dùng $in lớn, nhưng:

- Kích thước BSON command có giới hạn.
- Số index ranges cần xét có thể lớn.
- Thời gian merge/sort tăng.
- Có thể quá tải một shard/site.

Tùy SLA, nên giới hạn số device/query, phân nhóm theo site hoặc tạo summary collection đã được tối ưu cho dashboard.

### 20.5. Mối quan hệ giữa index và compression

Time series compression giúp giảm kích thước lưu trữ, nhưng nhiều index vẫn có chi phí riêng. Không thể suy luận “vì dữ liệu nén rất tốt nên thêm 20 index sẽ miễn phí”.

Những dashboard nên theo dõi:

- Ingest measurements/second.
- Average document/bucket size và compression ratio (khi công cụ hỗ trợ).
- Bucket count/creation rate.
- Storage/index size và cache pressure.
- Query p50/p95/p99 theo query shape.
- Buckets unpacked, keys/docs examined.
- Late arrival rate và data quality.
- TTL cleanup/retention progress.
- CPU/IOPS và replication lag.

### 20.6. Đo trên dữ liệu đại diện

Với lab 24 mẫu:

- Query nào cũng có thể hoàn tất gần như tức thì.
- Optimizer có thể chọn plan khác production.
- Số bucket, độ nén và cardinality không đại diện cho 50.000 thiết bị.

Vì vậy, dùng lab để **hiểu semantics và cú pháp**; dùng staging có phân bố dữ liệu tương tự production để **đánh giá hiệu năng**.

## 21. Các lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query Date không trả kết quả | Lọc bằng String thay vì BSON Date | Dùng ISODate/new Date, kiểm tra type |
| Báo cáo sai ngày | Dùng ngày UTC thay vì ngày ở múi giờ nghiệp vụ | Chuyển boundary sang UTC đúng timezone |
| Mẫu 01:00 bị đếm hai lần | Hai cửa sổ cùng dùng $lte end | Dùng khoảng [start,end) |
| Query đọc mọi tenant | Thiếu điều kiện metadata.tenantId | Ràng buộc tenant từ auth context |
| Có time index nhưng query sensor vẫn chậm | Không lọc metadata hoặc index không hợp query shape | Đo metadata+time compound index |
| Index tenant/device/time không tối ưu query cả tenant | Thiếu equality device, time nằm sau device trong key | Xem tenant/time hoặc rollup |
| Mẫu mới nhất không đúng khi timestamp trùng | Sort thiếu tie-breaker | Thêm seq/eventId và index phù hợp |
| Lấy hai mẫu tổng cộng thay vì hai mẫu mỗi device | $limit trước khi group từng device | Group/topN theo device |
| Trung bình sai khi có mẫu lỗi | Không lọc quality hoặc missing | Định nghĩa valid sample và filter |
| Sum watts bị hiểu là Wh | Nhầm tổng công suất với điện năng | Xác định chu kỳ đo/tích phân |
| $dateTrunc cho ngày sai | Sai timezone | Dùng timezone IANA phù hợp |
| Bucket pruning kém | Query không có metadata hoặc range quá rộng | Thu hẹp scope và thời gian |
| Mỗi mẫu tạo metadata riêng | Đưa giá trị thay đổi/UUID vào metaField | Giữ metadata ổn định |
| Đọc explain tưởng 10 bucket = 10 mẫu | Metrics ở tầng bucket | Xem unpack và nReturned tổng thể |
| Tạo index đo nhiệt độ bị lỗi | Version hạn chế secondary index trên measurement | Kiểm tra time series index support |
| Tạo index trùng làm ingest chậm | Over-indexing | Xem getIndexes, workload, remove có kiểm soát |
| TTL xóa “chậm” so với deadline | Cleanup theo bucket/bất đồng bộ | Thiết kế retention SLA thực tế |
| Report năm trước rỗng | Raw measurements đã hết retention | Dùng hourly/daily rollups |
| Missing sample bị coi thành 0 | Densify/fill sai semantics | Phân biệt null/missing với zero |
| Dữ liệu đến muộn không xuất hiện trên latest view | Dùng ingestedAt như observedAt hoặc điều kiện update sai | So sánh timestamp nghiệp vụ |
| Có trùng mẫu sau retry | Ingest không có idempotency/dedup | Dùng business sampleId/pipeline dedup |
| Query toàn time-series trên shards chậm | Thiếu shard key targeting/scatter-gather | Xem shard key và read model |
| Không tạo được index/TTL mong muốn | Khác version/cú pháp/giới hạn collection | Dựa vào tài liệu của server version |
| 24 mẫu lab rất nhanh nên nghĩ production nhanh | Dataset quá nhỏ | Benchmark theo dữ liệu thật |

## 22. Bài tập thực hành

### Bài 1 — Nhận diện timeField/metaField

Từ một measurement có observedAt, metadata.tenantId, metadata.deviceId, watts, temperatureC, hãy phân loại field theo vai trò. Giải thích vì sao watts không nên đưa vào metaField khi công suất thay đổi liên tục.

### Bài 2 — Tạo collection

Viết lệnh db.createCollection cho collection **sensorMetrics** với timeField "measuredAt", metaField "source" và granularity "seconds". Nêu điều gì xảy ra nếu ứng dụng gửi measuredAt dạng String thay vì BSON Date.

### Bài 3 — Range nửa mở

Với meter-A, lọc từ 00:30 đến trước 01:30 UTC. Dự đoán bốn kết quả watts và giải thích vì sao mẫu 01:30 bị loại.

### Bài 4 — Metadata và multi-tenant

Viết query lấy mọi measurement của meter-A trong t001, từ 00:00 đến 02:00. Vì sao chỉ dựa trên deviceId mà bỏ tenantId có thể gây lỗi dữ liệu/bảo mật?

### Bài 5 — Site chart

Lọc t001/site hn trong hai giờ. Tổng cộng có bao nhiêu measurements? Tại sao không thấy meter-C? Giải thích vai trò của index tenantId/siteId/time.

### Bài 6 — Latest N

Lấy ba mẫu mới nhất của meter-A. Dự đoán observedAt/watts. Nếu hai mẫu có cùng observedAt, cần bổ sung điều gì để đảm bảo thứ tự ổn định?

### Bài 7 — Latest per device

Viết aggregation lấy một mẫu mới nhất cho từng device trong t001/site hn. Giải thích vì sao một $limit:2 toàn pipeline không tương đương một mẫu cho mỗi device.

### Bài 8 — Average và energy

Với meter-A watts 10..17, tính avg, min, max và sum. Nếu mỗi phép đo được hiểu là công suất trung bình trong một khoảng 15 phút, ước tính điện năng Wh. Nêu khi nào phép ước tính này không còn hợp lệ.

### Bài 9 — Group theo giờ

Dùng $dateTrunc theo timezone UTC để tổng hợp avgWatts của meter-B theo giờ. Dự đoán avg lúc 00:00 và 01:00.

### Bài 10 — Quality filter

Trong lab, meter-B có một mẫu suspect ở 00:45 với watts=23. Tính lại trung bình sau khi loại suspect. Phân tích lựa chọn index khi filter quality là measurement field.

### Bài 11 — Ngày theo Việt Nam

Một báo cáo cần ngày 15/01/2026 ở Asia/Ho_Chi_Minh. Tính start/end UTC cho khoảng nửa mở đó. Vì sao dùng 00:00Z–00:00Z của ngày UTC có thể sai?

### Bài 12 — Thiết kế index

Từ Q1/Q2/Q3/Q4, chọn tối đa hai index ban đầu khi 70% lưu lượng là đọc một device và 20% là site chart. Giải thích những query còn lại có thể chưa tối ưu.

### Bài 13 — Prefix và sort

Index có các key **tenantId, deviceId, observedAt:-1**. Query chỉ có tenantId + time range thì có dùng toàn bộ suffix time thuận lợi như query có cả deviceId không? Nêu cách dùng explain để kiểm chứng.

### Bài 14 — Đọc executionStats

Chạy explain("executionStats") cho query một device và query chỉ theo thời gian. Ghi các stage, keys/docs examined và nReturned. Giải thích vì sao totalDocsExamined ở bucket-level không phải số measurement.

### Bài 15 — Granularity

Hệ A gửi mỗi giây, hệ B gửi hai lần mỗi ngày. Bạn cân nhắc granularity thế nào? Những yếu tố nào khiến chọn cùng cấu hình cho cả hai hệ không tối ưu?

### Bài 16 — Dữ liệu đến muộn

Một measurement observedAt=00:15, ingestedAt=03:00. Nó thuộc nhóm giờ nào khi báo cáo theo observedAt? Nếu latest view đang lưu mẫu lúc 01:45, vì sao không được ghi đè latest bằng mẫu đến muộn?

### Bài 17 — Missing và zero

Thiết bị thiếu dữ liệu lúc 00:30 nhưng có mẫu 00:15=5 W và 00:45=7 W. So sánh zero-fill, forward-fill và interpolation. Trường hợp nào tạo ra kết luận sai nếu coi dữ liệu được fill như phép đo thật?

### Bài 18 — Retention

Thiết kế giữ raw 30 ngày và hourly aggregate 365 ngày. Nếu query lịch sử 90 ngày, ứng dụng nên dùng collection nào? Vì sao TTL cleanup không luôn diễn ra đúng mili giây hết hạn?

### Bài 19 — Sharding

Ứng dụng lọc tenantId/deviceId ở phần lớn request. Bạn chọn shard key theo những nguyên tắc nào? Vì sao query toàn hệ thống chỉ theo time range có thể scatter-gather?

### Bài 20 — Index quá nhiều

Một nhóm tạo 12 indexes trên time-series collection có 10 triệu inserts/ngày. Chỉ hai index xuất hiện trong query plans thường xuyên. Hãy đề xuất quy trình đánh giá chi phí ghi, disk, query p95 và gỡ index không cần thiết theo chính sách vận hành.

### Bài 21 — Dữ liệu trùng

Cảm biến retry cùng một phép đo ba lần. Nếu time series không có unique index phù hợp theo business key, hệ thống có thể phát sinh kết quả gì? Thiết kế một ingest pipeline có sampleId và dedup.

### Bài 22 — Bảo mật tenant

Một API nhận deviceId và khoảng thời gian từ frontend. Hãy nêu cách ràng buộc tenantId từ thông tin xác thực, validate start/end và giới hạn maximum window. Vì sao index không thay thế authorization?

### Bài 23 — So sánh kiến trúc

So sánh hai thiết kế:

1. Mọi request dashboard đọc raw measurements của một năm.
2. API chi tiết đọc raw theo thời gian hẹp; dashboard dùng hourly/daily summaries.

Phân tích latency, độ mới, chi phí storage, khả năng dữ liệu đến muộn và cơ chế rebuild/đối soát.

### Bài 24 — Đo hiệu quả thực tế

Thiết kế benchmark production-like với 50.000 devices và các query Q1-Q7. Chọn metric throughput, bucket count, p95/p99, keys/docs examined, compression và ingestion latency. Nêu vì sao không thể kết luận hiệu năng từ lab 24 mẫu.

## 23. Tài liệu tham khảo MongoDB

- MongoDB Manual — [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/).
- MongoDB Manual — [Create and Query Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/).
- MongoDB Manual — [Time Series Secondary Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-secondary-index/).
- MongoDB Manual — [Time Series Best Practices](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-best-practices/).
- MongoDB Manual — [Time Series Granularity](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-granularity/).
- MongoDB Manual — [Time Series TTL](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/).
- MongoDB Manual — [Time Series Sharding](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-shard-collection/).
- MongoDB Manual — [$dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/).
- MongoDB Manual — [$densify](https://www.mongodb.com/docs/manual/reference/operator/aggregation/densify/).
- MongoDB Manual — [$fill](https://www.mongodb.com/docs/manual/reference/operator/aggregation/fill/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/).

**Kết luận:** Truy vấn time series hiệu quả thường bắt đầu từ **metadata đúng nguồn + khoảng thời gian nửa mở đủ hẹp**. Time-series collection lưu dữ liệu theo **buckets** để tối ưu nén và pruning, nhưng không thay thế việc chọn index. Hãy thiết kế bộ index theo **query patterns**: equality trên tenant/device/site rồi range hoặc sort theo **timeField**; kiểm tra **getIndexes** và **explain** để hiểu số bucket cần đọc, tránh lẫn bucket scan với số measurement. Đối với dữ liệu lịch sử rộng, ưu tiên **hourly/daily rollups** khi phù hợp; với dữ liệu realtime, xử lý **múi giờ, late arrivals, missing samples, retention và idempotency** rõ ràng. Một cấu trúc metadata ổn định và một bộ index nhỏ, được đo trên workload đại diện, thường có giá trị hơn nhiều index tạo theo cảm tính.
