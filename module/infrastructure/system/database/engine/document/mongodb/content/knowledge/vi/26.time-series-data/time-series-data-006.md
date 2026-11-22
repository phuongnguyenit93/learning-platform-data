# Tổng hợp theo cửa sổ thời gian và tạo dữ liệu thống kê trong MongoDB

## 1. Bài toán: từ dữ liệu đo liên tục đến thông tin có thể sử dụng

Một hệ thống giám sát nhiệt độ ghi số đo từ nhiều cảm biến. Mỗi bản ghi có thời điểm đo, mã cảm biến, nhiệt độ, độ ẩm và công suất điện:

~~~javascript
{
  ts: ISODate("2026-05-10T00:05:00Z"),
  meta: {
    sensorId: "S-01",
    site: "HCM"
  },
  temperatureC: 28,
  humidityPct: 70,
  powerW: 110
}
~~~

Lúc mới triển khai, dashboard có thể chỉ cần hiện **số đo mới nhất**. Sau một thời gian, các yêu cầu thường phức tạp hơn:

- Mỗi **15 phút** có bao nhiêu bản ghi?
- Nhiệt độ **trung bình theo giờ**, min, max là bao nhiêu?
- Có những giờ **không nhận được dữ liệu** từ cảm biến nào?
- Nhiệt độ trung bình trong **3 giờ gần nhất** thay đổi thế nào?
- Giá trị hiện tại lệch bao nhiêu so với **lần đo trước**?
- Tổng công suất hoặc lượng điện tiêu thụ theo ngày tính thế nào?
- Có thể tạo collection **sensor_hourly_stats** để dashboard đọc nhanh thay vì group hàng triệu measurements mỗi lần không?
- Nếu sự kiện ghi trễ hoặc cập nhật lại số liệu lịch sử, bảng thống kê cần được sửa ra sao?

MongoDB cung cấp **aggregation pipeline** với các toán tử thời gian và window functions để trả lời các câu hỏi này ngay tại database.

Mục tiêu quan trọng là phân biệt ba phép xử lý thường được gọi chung là *tổng hợp theo cửa sổ* nhưng không giống nhau:

1. **Tumbling / fixed time buckets:** gom những measurements vào các khoảng như từng giờ hoặc 15 phút, tính một kết quả cho mỗi bucket.
2. **Sliding / rolling windows:** tại mỗi hàng đã sắp xếp theo thời gian, tính thống kê dựa trên một tập các hàng hoặc khoảng thời gian lân cận.
3. **Materialization / downsampling:** lưu kết quả đã tổng hợp vào collection thống kê để tái sử dụng và giảm chi phí truy vấn.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Thiết kế dữ liệu chuỗi thời gian với **timeField** và **metaField**.
- Dùng **$dateTrunc + $group** để thống kê theo phút, giờ, ngày, tuần.
- Hiểu khác biệt giữa **documents window** và **range/time window** của **$setWindowFields**.
- Tính rolling average, rolling sum, cumulative total, min/max và biến động giữa hai số đo.
- Xử lý giờ thiếu dữ liệu với **$densify** và **$fill** mà không tùy tiện biến giá trị thiếu thành 0.
- Làm đúng với timezone, ngày có DST, dữ liệu lỗi, dữ liệu tới trễ và số đo không đều.
- Lưu bảng tổng hợp bằng **$merge** và thiết kế lịch backfill/recompute an toàn.
- Triển khai ví dụ mongosh, MongoDB Java Sync Driver và Spring Data MongoDB.
- Nhận biết giới hạn server version, index, memory, chi phí xử lý và độ chính xác thống kê.

## 2. Khái niệm nền tảng

### 2.1. Event time và processing time

Trong hệ thống IoT/log/telemetry có ít nhất hai loại thời gian:

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| **ts / eventTime** | Thời điểm sự kiện thực sự xảy ra hoặc được đo. | Cảm biến đo lúc 08:05. |
| **ingestedAt / processingTime** | Thời điểm backend nhận và lưu dữ liệu. | Do mất mạng, dữ liệu 08:05 được gửi lúc 09:20. |

Nếu câu hỏi là **“nhiệt độ trung bình từ 08:00 đến 09:00?”**, thường phải nhóm theo **event time**, không nhóm theo giờ dữ liệu đến server.

Nếu câu hỏi là **“mất bao lâu để một measurement tới hệ thống?”**, có thể dùng chênh lệch giữa ingestedAt và ts.

Không được dùng timestamp của request HTTP thay cho thời điểm đo mà không xác định semantics nghiệp vụ.

### 2.2. Fixed bucket và rolling window

Một chuỗi readings có thể trông như sau:

~~~text
00:05 --28°C
00:35 --30°C
01:10 --29°C
02:00 --(không có mẫu)
03:20 --31°C
03:50 --32°C
~~~

**Fixed hourly buckets**:

~~~text
[00:00,01:00) -> 28,30 -> average 29
[01:00,02:00) -> 29    -> average 29
[02:00,03:00) -> trống
[03:00,04:00) -> 31,32 -> average 31.5
~~~

**Rolling three-hour window** tại 03:50 có thể xem các readings trong khoảng 00:50–03:50; đó không phải cùng cách tính với “ba bucket quan sát gần nhất”.

### 2.3. Khoảng nửa mở

Để phân chia thời gian không chồng lấn, thường dùng:

~~~text
[start, end)
~~~

Nghĩa là:

- **start** được tính vào khoảng.
- **end** không được tính vào khoảng.

Trong MongoDB:

~~~javascript
{
  ts: {
    $gte: ISODate("2026-05-10T00:00:00Z"),
    $lt: ISODate("2026-05-10T01:00:00Z")
  }
}
~~~

Điều này giúp measurement đúng **01:00** chỉ thuộc bucket bắt đầu lúc 01:00, không bị đếm hai lần ở hai giờ liên tiếp.

### 2.4. Metric tổng hợp có thể ghép và metric không thể ghép tùy tiện

Các trường thống kê thường dùng:

| Metric | Ý nghĩa | Có thể ghép từ summary con? |
|---|---|---|
| **count** | Số mẫu hợp lệ hoặc số documents. | Cộng các counts. |
| **sum** | Tổng giá trị. | Cộng sums. |
| **min / max** | Nhỏ nhất/lớn nhất. | Min của mins, max của maxes. |
| **average** | Trung bình. | Phải giữ **sum và count** để tính trung bình có trọng số. |
| **percentile / median** | Phân vị/trung vị. | **Không** tính bằng trung bình các percentiles/medians con. |
| **stddev** | Độ lệch chuẩn. | Cần đủ moments/statistics trung gian hoặc tính lại đúng công thức. |
| **rate** | Thay đổi theo thời gian. | Cần hiểu khoảng thời gian, counter reset và boundary samples. |

Lỗi kinh điển là lấy trung bình của các hourly averages khi số samples mỗi giờ khác nhau. Bài này sẽ giữ **sum + count** để tạo thống kê ngày đúng.

## 3. Tạo dữ liệu thực hành

Chọn một database riêng trên MongoDB **5.0+** nếu muốn dùng các toán tử cửa sổ chính. Các stages mới hơn sẽ ghi rõ yêu cầu version.

~~~javascript
use mongo_timeseries_stats_lab
~~~

Tạo **time series collection**:

~~~javascript
db.createCollection("sensor_readings", {
  timeseries: {
    timeField: "ts",
    metaField: "meta",
    granularity: "minutes"
  }
});
~~~

**timeField** phải chứa BSON Date để tổ chức dữ liệu đo theo thời gian. **metaField** chứa thông tin tương đối ổn định của nguồn đo, ở đây là sensorId và site.

MongoDB lưu measurements của time series collection trong những **buckets nội bộ** để tận dụng compression và tối ưu truy vấn. Các buckets lưu trữ nội bộ **không phải** là những bucket 15 phút/1 giờ mà aggregation sẽ tạo ra.

### 3.1. Seed data

~~~javascript
db.sensor_readings.insertMany([
  {
    ts: ISODate("2026-05-10T00:05:00Z"),
    meta: { sensorId: "S-01", site: "HCM" },
    temperatureC: 28,
    humidityPct: 70,
    powerW: 110
  },
  {
    ts: ISODate("2026-05-10T00:35:00Z"),
    meta: { sensorId: "S-01", site: "HCM" },
    temperatureC: 30,
    humidityPct: 68,
    powerW: 125
  },
  {
    ts: ISODate("2026-05-10T01:10:00Z"),
    meta: { sensorId: "S-01", site: "HCM" },
    temperatureC: 29,
    humidityPct: 69,
    powerW: 118
  },
  {
    ts: ISODate("2026-05-10T03:20:00Z"),
    meta: { sensorId: "S-01", site: "HCM" },
    temperatureC: 31,
    humidityPct: 67,
    powerW: 130
  },
  {
    ts: ISODate("2026-05-10T03:50:00Z"),
    meta: { sensorId: "S-01", site: "HCM" },
    temperatureC: 32,
    humidityPct: 66,
    powerW: 132
  },
  {
    ts: ISODate("2026-05-10T00:20:00Z"),
    meta: { sensorId: "S-02", site: "HCM" },
    temperatureC: 26,
    humidityPct: 74,
    powerW: 95
  },
  {
    ts: ISODate("2026-05-10T01:30:00Z"),
    meta: { sensorId: "S-02", site: "HCM" },
    temperatureC: 27,
    humidityPct: 73,
    powerW: 98
  },
  {
    ts: ISODate("2026-05-10T02:40:00Z"),
    meta: { sensorId: "S-02", site: "HCM" },
    temperatureC: 28,
    humidityPct: 72,
    powerW: 101
  }
]);
~~~

**Chạy seed một lần trên collection mới.** Các lệnh minh họa dưới đây có thể được thử độc lập; nếu bạn bổ sung/xóa dữ liệu, kết quả dự kiến cũng thay đổi. Không chạy ví dụ tái tạo collection trên production.

### 3.2. Kiểm tra nguồn theo sensor và thời gian

~~~javascript
db.sensor_readings.find(
  {
    "meta.sensorId": "S-01",
    ts: {
      $gte: ISODate("2026-05-10T00:00:00Z"),
      $lt: ISODate("2026-05-11T00:00:00Z")
    }
  },
  {
    _id: 0,
    ts: 1,
    "meta.sensorId": 1,
    temperatureC: 1
  }
).sort({ ts: 1 });
~~~

S-01 có năm readings trong dữ liệu mẫu. Không có reading từ **02:00 đến trước 03:00**; điều này khác với “cảm biến đo 0°C trong giờ 02”.

### 3.3. Thiết kế metaField

Chọn metaField có giá trị tương đối ổn định, như sensor ID, loại thiết bị, địa điểm cố định. Tránh đưa **timestamp, requestId ngẫu nhiên hoặc giá trị thay đổi ở mỗi measurement** vào metaField vì có thể sinh quá nhiều buckets nhỏ và giảm hiệu quả nén.

Khi metaField là một object, truy vấn các scalar subfields như **meta.sensorId**, thay vì so sánh toàn object và phụ thuộc vào thứ tự key.

## 4. $dateTrunc: tạo khóa bucket thời gian

**$dateTrunc** (MongoDB 5.0+) đưa một timestamp về **đầu khoảng thời gian** mong muốn.

Ví dụ:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "hour",
    binSize: 1,
    timezone: "UTC"
  }
}
~~~

Với ts = 00:05 hoặc 00:35 UTC, cả hai đều trả **2026-05-10T00:00:00Z**. Giá trị này dùng được làm khóa group.

### 4.1. Tổng hợp nhiệt độ theo giờ bằng $group

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      "meta.sensorId": "S-01",
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        hourStart: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      samples: { $sum: 1 },
      sumTempC: { $sum: "$temperatureC" },
      avgTempC: { $avg: "$temperatureC" },
      minTempC: { $min: "$temperatureC" },
      maxTempC: { $max: "$temperatureC" }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      hourStart: "$_id.hourStart",
      samples: 1,
      sumTempC: 1,
      avgTempC: 1,
      minTempC: 1,
      maxTempC: 1
    }
  },
  {
    $sort: {
      sensorId: 1,
      hourStart: 1
    }
  }
]);
~~~

Kết quả cho S-01 từ dữ liệu mẫu:

| hourStart (UTC) | samples | sumTempC | avgTempC | minTempC | maxTempC |
|---|---:|---:|---:|---:|---:|
| 00:00 | 2 | 58 | 29 | 28 | 30 |
| 01:00 | 1 | 29 | 29 | 29 | 29 |
| 03:00 | 2 | 63 | 31.5 | 31 | 32 |

Không có dòng **02:00** vì **$group không tự tạo bucket không có source document**.

### 4.2. Giải thích pipeline

1. **$match** giới hạn sensor và thời gian để giảm dữ liệu đưa vào aggregation.
2. **$group** dùng sensorId + hourStart làm composite key.
3. Các accumulators tính count/sum/avg/min/max trong mỗi bucket.
4. **$project** biến group key thành schema dễ dùng ở dashboard.
5. **$sort** bảo đảm thứ tự hiển thị; output của $group không tự có thứ tự.

### 4.3. Tổng hợp theo 15 phút

Đổi bucket expression:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "minute",
    binSize: 15,
    timezone: "UTC"
  }
}
~~~

Các khoảng được chia thành 00:00–00:15, 00:15–00:30, 00:30–00:45, 00:45–01:00 theo quy tắc alignment của $dateTrunc.

**binSize** phải là giá trị số dương phù hợp. Không tạo những khoảng dài 15 phút bằng cách làm tròn chuỗi timestamp thủ công trong ứng dụng khi MongoDB có thể biểu diễn trực tiếp.

### 4.4. Tổng hợp theo ngày, tuần, tháng

Bucket ngày tại timezone kinh doanh:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Bucket tuần bắt đầu thứ Hai:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "week",
    startOfWeek: "monday",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Bucket tháng:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "month",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Kết quả là **BSON Date đại diện đầu bucket**, lưu dưới dạng UTC; timezone chỉ quy định cách tìm ranh giới theo lịch địa phương. Đừng nhầm “trả về 00:00 UTC” với “ngày địa phương đã bắt đầu lúc 00:00 UTC”.

## 5. Thống kê có điều kiện, dữ liệu null và sample count

### 5.1. $avg bỏ qua giá trị không phải số

Khi một vài measurements thiếu nhiệt độ hoặc nhiệt độ null, **$avg** bỏ qua những giá trị không phải số. Vì vậy:

~~~javascript
{
  $group: {
    _id: "$meta.sensorId",
    totalDocuments: { $sum: 1 },
    avgTempC: { $avg: "$temperatureC" }
  }
}
~~~

thì **totalDocuments** chưa chắc bằng số readings hợp lệ được dùng tính avgTempC.

### 5.2. Đếm riêng valid measurements

~~~javascript
db.sensor_readings.aggregate([
  {
    $group: {
      _id: "$meta.sensorId",
      totalDocuments: { $sum: 1 },
      validTempSamples: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            1,
            0
          ]
        }
      },
      sumTempC: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            "$temperatureC",
            0
          ]
        }
      },
      avgTempC: { $avg: "$temperatureC" }
    }
  }
]);
~~~

Khi không có nhiệt độ dạng số, **validTempSamples = 0** và **avgTempC** có thể là null. Không thực hiện phép chia cho 0.

### 5.3. 0, null và không có document khác nhau

| Trạng thái | Ý nghĩa |
|---|---|
| temperatureC = **0** | Một phép đo nhiệt độ thực sự bằng 0°C. |
| temperatureC = **null** | Document có tồn tại nhưng giá trị chưa biết/không hợp lệ theo schema. |
| Thiếu temperatureC | Không được gửi giá trị trong document. |
| Không có document trong giờ | Không có measurement cho bucket đó. |

Chỉ thay null hoặc missing bằng 0 khi **domain chứng minh 0 là giá trị thay thế đúng**, ví dụ **event count** của một bucket rỗng. Với nhiệt độ, lấp missing bằng 0 sẽ làm sai biểu đồ và thống kê.

### 5.4. Làm tròn để hiển thị

~~~javascript
{
  $project: {
    avgTempC: {
      $round: ["$avgTempC", 2]
    }
  }
}
~~~

Giữ dữ liệu không làm tròn trong summary khi còn tính toán tiếp; chỉ làm tròn ở bước hiển thị hoặc theo quy ước nghiệp vụ để tránh sai số tích lũy.

## 6. Sự khác biệt giữa tumbling, hopping và sliding windows

### 6.1. Tumbling window

Một measurement thuộc **đúng một bucket** cho mỗi cách chia:

~~~text
00:00      01:00      02:00      03:00
  |----------|----------|----------|
   bucket 0   bucket 1   bucket 2
~~~

Trong MongoDB, thường dùng **$dateTrunc + $group**.

### 6.2. Hopping window

Một cửa sổ có độ dài cố định, nhưng cửa sổ mới bắt đầu theo **bước nhảy nhỏ hơn độ dài**:

~~~text
Window dài 60 phút, hop 15 phút:

00:00 ------ 01:00
  00:15 ------ 01:15
    00:30 ------ 01:30
      00:45 ------ 01:45
~~~

Một measurement có thể thuộc **nhiều windows**.

MongoDB không có một tùy chọn chung tên **hopSize** trong $group; có thể tạo các mốc windows và join/unwind thích hợp hoặc dùng window range analytics tùy mục tiêu. Việc materialize mọi cửa sổ chồng lấn có thể nhân lượng kết quả đáng kể.

### 6.3. Sliding window

Tại mỗi measurement hoặc mỗi bucket đã được sort, tính trên các hàng lân cận:

~~~text
S-01 observed hourly averages:
00:00 29
01:00 29
03:00 31.5

Rolling 2 observed rows:
00:00 -> [29]         -> 29
01:00 -> [29,29]      -> 29
03:00 -> [29,31.5]    -> 30.25
~~~

Đây là **hai hàng quan sát gần nhất**, không phải chắc chắn **hai giờ liên tiếp** khi 02:00 bị thiếu. Phải biết dùng **documents window** hay **range window**.

## 7. $setWindowFields: thống kê trên từng cửa sổ

**$setWindowFields** (MongoDB 5.0+) cho phép tạo các field thống kê dựa trên những documents nằm trong một **partition** và một **window**.

Khung cú pháp:

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$sensorId",
    sortBy: { hourStart: 1 },
    output: {
      metricName: {
        $avg: "$avgTempC",
        window: {
          documents: [-2, 0]
        }
      }
    }
  }
}
~~~

- **partitionBy:** độc lập tính cho từng sensor.
- **sortBy:** xác định trình tự thời gian trong partition.
- **output:** những chỉ số mới gắn vào từng row.
- **documents:** phạm vi số vị trí trước/sau hàng hiện tại.
- **range:** phạm vi dựa trên giá trị sortBy, có thể dùng đơn vị thời gian.

### 7.1. Rolling 3 hourly rows

Bắt đầu từ bảng hourly thống kê của S-01:

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        hourStart: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: 1 },
      avgTempC: { $avg: "$temperatureC" }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      hourStart: "$_id.hourStart",
      sampleCount: 1,
      avgTempC: 1
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$sensorId",
      sortBy: {
        hourStart: 1
      },
      output: {
        avgLast3ObservedHours: {
          $avg: "$avgTempC",
          window: {
            documents: [-2, 0]
          }
        },
        samplesCumulative: {
          $sum: "$sampleCount",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      hourStart: 1
    }
  }
]);
~~~

Với S-01, ở 03:00, **avgLast3ObservedHours** tính trên ba rows **00:00, 01:00 và 03:00**: (29 + 29 + 31.5) / 3 ≈ **29.8333**.

Đây **không phải rolling 3 giờ lịch liên tục**. Vì 02:00 không có bucket, documents window không biết khoảng trống đó.

### 7.2. Cumulative sum

~~~javascript
samplesCumulative: {
  $sum: "$sampleCount",
  window: {
    documents: ["unbounded", "current"]
  }
}
~~~

Đọc từ đầu partition tới hàng hiện tại. Với S-01:

~~~text
00:00 -> 2
01:00 -> 3
03:00 -> 5
~~~

Nếu không đặt **partitionBy**, một cumulative total có thể cộng chung tất cả sensors, sai mục tiêu báo cáo per-sensor.

### 7.3. Documents window và time-range window

**documents window**:

~~~javascript
window: {
  documents: [-2, 0]
}
~~~

Tính tối đa ba rows: hai trước và hàng hiện tại.

**time-range window**:

~~~javascript
window: {
  range: [-2, 0],
  unit: "hour"
}
~~~

Tính các hàng có timestamp thuộc **hai giờ trước đến thời điểm hàng hiện tại**, ranh giới bao gồm cả hai đầu theo semantics window. Khi dùng range có **unit**, sortBy phải là một date/time field thích hợp.

Đừng hiểu documents:[-2,0] luôn bằng range:[-2,0], unit:"hour". Chúng chỉ tương tự trong một số dữ liệu đều và quy tắc cửa sổ phù hợp.

### 7.4. Rolling 60 phút trên dữ liệu đo gốc

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      "meta.sensorId": "S-01",
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$meta.sensorId",
      sortBy: {
        ts: 1
      },
      output: {
        avgPrevious60Minutes: {
          $avg: "$temperatureC",
          window: {
            range: [-60, 0],
            unit: "minute"
          }
        },
        maxPrevious60Minutes: {
          $max: "$temperatureC",
          window: {
            range: [-60, 0],
            unit: "minute"
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      ts: 1,
      sensorId: "$meta.sensorId",
      temperatureC: 1,
      avgPrevious60Minutes: 1,
      maxPrevious60Minutes: 1
    }
  },
  {
    $sort: {
      ts: 1
    }
  }
]);
~~~

Tại 01:10 của S-01, cửa sổ [00:10,01:10] chứa 00:35 (30°C) và 01:10 (29°C), nhưng không chứa 00:05. Trung bình là **29.5°C**.

### 7.5. Tại sao nên $sort ở cuối?

**$setWindowFields không bảo đảm thứ tự của documents đầu ra**, dù có sortBy để tính window. Nếu dashboard/API cần thứ tự hiển thị, thêm **$sort** ở cuối.

### 7.6. Window boundaries và bản ghi đầu tiên

Với documents:[-2,0], hàng đầu tiên chưa có hai rows trước. MongoDB tính toán trên **các rows thực sự tồn tại trong window**, không tự thêm hai rows 0.

Nếu sản phẩm yêu cầu **chỉ xuất 3-hour average khi đủ 3 mẫu**, cần tính thêm số mẫu trong window và lọc/đánh dấu kết quả:

~~~javascript
output: {
  rollingAvg: {
    $avg: "$temperatureC",
    window: { documents: [-2, 0] }
  },
  rollingSampleCount: {
    $count: {},
    window: { documents: [-2, 0] }
  }
}
~~~

Sau stage này, có thể lọc **rollingSampleCount >= 3** hoặc trả **isCompleteWindow** cho UI. Không ép kết quả hàng đầu tiên thành một “trung bình đủ ba mẫu” khi chưa có đủ dữ liệu.

## 8. So sánh hai lần đo và phát hiện thay đổi đột ngột

Ngoài trung bình và tổng, hệ thống thường cần biết **biến động giữa hai readings liên tiếp**.

### 8.1. $shift để lấy giá trị trước đó

Trong **$setWindowFields**, **$shift** trả giá trị từ một row ở vị trí tương đối. **by:-1** chỉ hàng trước:

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      "meta.sensorId": "S-01",
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$meta.sensorId",
      sortBy: { ts: 1 },
      output: {
        previousTemperatureC: {
          $shift: {
            output: "$temperatureC",
            by: -1,
            default: null
          }
        },
        previousTs: {
          $shift: {
            output: "$ts",
            by: -1,
            default: null
          }
        }
      }
    }
  },
  {
    $set: {
      deltaTempC: {
        $subtract: ["$temperatureC", "$previousTemperatureC"]
      },
      elapsedMs: {
        $subtract: ["$ts", "$previousTs"]
      }
    }
  },
  {
    $project: {
      _id: 0,
      ts: 1,
      temperatureC: 1,
      previousTs: 1,
      previousTemperatureC: 1,
      deltaTempC: 1,
      elapsedMs: 1
    }
  },
  { $sort: { ts: 1 } }
]);
~~~

Với S-01:

~~~text
00:05 -> 28°C, previous=null
00:35 -> 30°C, delta=+2°C
01:10 -> 29°C, delta=-1°C
03:20 -> 31°C, delta=+2°C
03:50 -> 32°C, delta=+1°C
~~~

Nếu nhiều readings có **cùng timestamp**, sortBy chỉ có ts chưa xác định rõ row nào là trước. Cần thêm một trường sequence/tie-breaker ổn định khi phân tích phụ thuộc thứ tự chính xác.

### 8.2. Phát hiện ngưỡng biến động

Sau khi tính deltaTempC, có thể lọc:

~~~javascript
{
  $match: {
    $expr: {
      $gte: [
        { $abs: "$deltaTempC" },
        2
      ]
    }
  }
}
~~~

Nhưng measurement cách nhau 130 phút và cách nhau 5 phút có ý nghĩa khác nhau. Delta 2°C không tự phản ánh tốc độ tăng nhiệt.

### 8.3. Tốc độ thay đổi

~~~text
rateCPerHour =
  (currentTemperatureC - previousTemperatureC)
  / ((currentTs - previousTs) / 3_600_000)
~~~

Trong pipeline, kiểm tra elapsedMs để tránh chia cho 0:

~~~javascript
{
  $set: {
    changeRateCPerHour: {
      $cond: [
        { $gt: ["$elapsedMs", 0] },
        {
          $multiply: [
            "$deltaTempC",
            { $divide: [3600000, "$elapsedMs"] }
          ]
        },
        null
      ]
    }
  }
}
~~~

MongoDB cũng có các window operators **$derivative** và **$integral** khi phù hợp, nhưng cần hiểu định nghĩa window, đơn vị và những giá trị đầu/cuối. Không suy từ tên operator rằng nó tự xử lý sensor reset hay dữ liệu lỗi.

## 9. Moving average và exponential moving average

### 9.1. Trung bình động đơn giản

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$meta.sensorId",
    sortBy: { ts: 1 },
    output: {
      sma3: {
        $avg: "$temperatureC",
        window: { documents: [-2, 0] }
      }
    }
  }
}
~~~

**SMA** (simple moving average) gán trọng số như nhau cho các rows trong window. Nếu số đo không đều theo thời gian, SMA theo số rows **không phải** trung bình được lấy trọng số theo khoảng thời gian thực.

### 9.2. Exponential moving average

**$expMovingAvg** là một window operator giúp làm mượt và ưu tiên readings gần đây:

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$meta.sensorId",
    sortBy: { ts: 1 },
    output: {
      ema3: {
        $expMovingAvg: {
          input: "$temperatureC",
          N: 3
        }
      }
    }
  }
}
~~~

EMA này tính theo **thứ tự readings**, không tự hiểu mỗi reading cách nhau 1 phút hay 2 giờ. Nếu muốn xử lý theo khoảng thời gian đều, trước tiên cần đưa dữ liệu về grid thời gian theo quy tắc missing data rõ ràng.

### 9.3. Chọn phép thống kê

| Trường hợp | Hướng lựa chọn |
|---|---|
| Trung bình ba mẫu gần nhất | SMA theo documents. |
| Làm mượt ưu tiên mẫu mới | EMA. |
| Trung bình trong 60 phút thật | Time **range window**. |
| Trung bình ba bucket giờ liên tiếp | Hourly buckets, xử lý gap, rồi window. |
| Năng lượng từ công suất W không đều | Tích phân theo thời gian/định nghĩa phép đo phù hợp, không cộng powerW trực tiếp. |

## 10. $densify: thêm bucket thời gian bị thiếu

**$group** chỉ tạo dòng cho các bucket có measurements. Với S-01:

~~~text
00:00 -> average 29
01:00 -> average 29
02:00 -> (không có dòng)
03:00 -> average 31.5
~~~

Nếu dashboard cần trục X đều theo giờ, phải biểu diễn được giờ **02:00**.

**$densify** (MongoDB 5.1+) tạo documents ở những mốc số/thời gian còn thiếu trong một range.

### 10.1. Densify sau khi group hourly

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-10T05:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        hourStart: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: 1 },
      avgTempC: { $avg: "$temperatureC" }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      hourStart: "$_id.hourStart",
      sampleCount: 1,
      avgTempC: 1
    }
  },
  {
    $densify: {
      field: "hourStart",
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
      hourStart: 1
    }
  }
]);
~~~

Ở partition S-01, MongoDB tạo mốc **02:00** nhưng các field **sampleCount** và **avgTempC** chưa có vì không có measurement tương ứng.

### 10.2. bounds: "partition" khác "full"

| bounds | Phạm vi |
|---|---|
| **"partition"** | Từ nhỏ nhất đến lớn nhất trong từng partition. |
| **"full"** | Theo khoảng tổng thể của field trong tập dữ liệu. |
| **[lower, upper]** | Khoảng tường minh, lower inclusive và upper exclusive. |

Với bounds:"partition", S-01 không tự có bucket **04:00** khi reading cuối ở 03:50. Nếu muốn tất cả mốc 00–04, dùng explicit bounds hoặc tạo timeline.

### 10.3. Explicit bounds

~~~javascript
{
  $densify: {
    field: "hourStart",
    partitionByFields: ["sensorId"],
    range: {
      step: 1,
      unit: "hour",
      bounds: [
        ISODate("2026-05-10T00:00:00Z"),
        ISODate("2026-05-10T05:00:00Z")
      ]
    }
  }
}
~~~

Với mỗi partition có dữ liệu, có thể bổ sung các mốc từ 00 đến 04 UTC chưa hiện diện. **$densify không tự tạo partition cho sensor không có document đầu vào**; nếu cần biểu diễn cảm biến hoàn toàn offline, phải có danh mục sensors và một time grid riêng.

### 10.4. Chi phí sinh documents

Ví dụ 50.000 sensors × 24 giờ = 1,2 triệu rows/ngày trước khi làm thống kê tiếp. **$densify có giới hạn số documents được sinh** và có thể tăng CPU/memory đáng kể.

Không densify toàn bộ vài năm lịch sử chỉ để vẽ dashboard 24 giờ. Giới hạn **$match, time range và partition** trước.

### 10.5. Thứ tự sau $densify

**$densify không bảo đảm output sort order**. Thêm **$sort** khi cần hiển thị, fill theo thứ tự hoặc tính window.

## 11. $fill: xử lý dữ liệu thiếu một cách có trách nhiệm

**$fill** (MongoDB 5.3+) lấp các field null/missing theo một số phương pháp.

| Phương pháp | Cơ chế | Khi nào có thể phù hợp |
|---|---|---|
| **value** | Điền giá trị hoặc expression đã xác định. | sampleCount=0 cho bucket thực sự không có event. |
| **locf** | Dùng giá trị khác null gần nhất trước đó. | Giữ last-known-state nếu domain chấp nhận. |
| **linear** | Nội suy tuyến tính theo những điểm xung quanh. | Tín hiệu liên tục với khoảng thiếu ngắn, có cơ sở nội suy. |

### 11.1. Điền sampleCount=0 nhưng giữ temperature là unknown

Sau **$densify**:

~~~javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { hourStart: 1 },
    output: {
      sampleCount: {
        value: 0
      }
    }
  }
}
~~~

S-01 được biểu diễn:

| hourStart | sampleCount | avgTempC | Ý nghĩa |
|---|---:|---:|---|
| 00:00 | 2 | 29 | Có hai samples. |
| 01:00 | 1 | 29 | Có một sample. |
| 02:00 | 0 | *missing/null* | Không có measurement. |
| 03:00 | 2 | 31.5 | Có hai samples. |

Đây là cách hiển thị **không có dữ liệu**, thay vì nói 02:00 = 0°C.

### 11.2. Gắn nhãn gap trước khi fill

~~~javascript
{
  $set: {
    dataStatus: {
      $cond: [
        { $eq: ["$sampleCount", null] },
        "NO_SAMPLES",
        "OBSERVED"
      ]
    }
  }
}
~~~

Đặt stage **sau $densify nhưng trước $fill**, lúc sampleCount ở các rows mới còn missing.

### 11.3. Last observation carried forward

~~~javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { hourStart: 1 },
    output: {
      avgTempC: {
        method: "locf"
      }
    }
  }
}
~~~

Ở giờ 02 không có mẫu, **locf** có thể mang average từ giờ 01 sang. Đây là **giá trị ước lượng/giữ nguyên**, không phải phép đo. Nên thêm **isImputed** hoặc giữ raw average trong field khác để truy vết.

### 11.4. Nội suy tuyến tính

~~~javascript
{
  $fill: {
    partitionByFields: ["sensorId"],
    sortBy: { hourStart: 1 },
    output: {
      avgTempC: {
        method: "linear"
      }
    }
  }
}
~~~

Nếu 01:00 = 29°C và 03:00 = 31.5°C, nội suy 02:00 cho **30.25°C**. Nhưng điều đó chỉ đúng với giả định thay đổi gần tuyến tính; tuyệt đối không coi là số đo thực.

Không áp dụng nội suy một cách tùy tiện cho event count, transaction count, boolean state hoặc chỉ số không phù hợp với nội suy.

### 11.5. $densify và $fill làm hai việc khác nhau

~~~text
$densify
  -> Tạo documents ở các mốc thời gian/số còn thiếu.

$fill
  -> Điền field null/missing trong các documents đã có,
     kể cả documents mới do $densify sinh ra.
~~~

Nếu chỉ dùng **$fill** mà không có row 02:00, nó không tự tạo row 02:00. Nếu chỉ dùng **$densify**, row mới có timestamp nhưng các metrics có thể vẫn missing.

## 12. Rolling average sau khi bổ sung grid thời gian

Sau **$group → $densify → $fill**, có thể tính sliding window trên grid giờ.

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$sensorId",
    sortBy: { hourStart: 1 },
    output: {
      rolling3CalendarHours: {
        $avg: "$avgTempC",
        window: {
          documents: [-2, 0]
        }
      },
      hoursWithSamples: {
        $sum: {
          $cond: [
            { $gt: ["$sampleCount", 0] },
            1,
            0
          ]
        },
        window: {
          documents: [-2, 0]
        }
      }
    }
  }
}
~~~

Với S-01 ở giờ 03:

~~~text
hourStart 01:00, avg=29, sampleCount=1
hourStart 02:00, avg=null, sampleCount=0
hourStart 03:00, avg=31.5, sampleCount=2

rolling3CalendarHours = (29 + 31.5) / 2 = 30.25
hoursWithSamples = 2
~~~

Đây là **average của hourly averages có dữ liệu trong ba bucket lịch**, chưa phải average trên tất cả raw measurements vì số mẫu khác nhau.

### 12.1. Tính trung bình raw measurements qua nhiều buckets

Giả sử ta giữ **sumTempC** và **validTempSamples** cho từng giờ. Thay vì average các averages:

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$sensorId",
    sortBy: { hourStart: 1 },
    output: {
      rollingTempSum: {
        $sum: "$sumTempC",
        window: { documents: [-2, 0] }
      },
      rollingSampleCount: {
        $sum: "$validTempSamples",
        window: { documents: [-2, 0] }
      }
    }
  }
}
~~~

Sau đó:

~~~javascript
{
  $set: {
    rollingRawAverageC: {
      $cond: [
        { $gt: ["$rollingSampleCount", 0] },
        {
          $divide: [
            "$rollingTempSum",
            "$rollingSampleCount"
          ]
        },
        null
      ]
    }
  }
}
~~~

Tại 03:00 của S-01, trong ba giờ 01,02,03 có readings 29,31,32; kết quả **(29+31+32)/3 = 30.6667**, khác với 30.25 của trung bình các hourly averages.

### 12.2. Cửa sổ không đủ dữ liệu

Nếu muốn một giá trị “rolling 3 giờ” chỉ xuất hiện khi ít nhất **2 giờ có sample**, có thể kiểm tra **hoursWithSamples >= 2** và trả isCompleteWindow/dataQuality. Một giá trị average được MongoDB tính ra không có nghĩa độ phủ dữ liệu đã đủ tin cậy.

### 12.3. Cắt quá sớm dữ liệu đầu vào

Nếu cần hiển thị rolling 3 giờ từ 12:00 tới 18:00, nên đọc thêm dữ liệu context trước 12:00 để tính các kết quả đầu. Sau khi tính window mới **lọc output về khoảng hiển thị**.

Lỗi thường gặp là $match chỉ lấy đúng 12:00–18:00 rồi mong tại 12:00 đã có hai giờ lịch sử của rolling window.

## 13. Timezone và giờ địa phương

### 13.1. Lưu timestamp UTC, nhóm theo timezone nghiệp vụ

Thực hành thông dụng là lưu timestamps bằng **BSON Date**, biểu diễn thời điểm tuyệt đối, rồi chọn timezone lúc tính ranh giới.

Ví dụ:

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Ngày 10/05 theo giờ Việt Nam bắt đầu từ **17:00 UTC của ngày 09/05**. Vì vậy BSON Date trả về cho đầu ngày địa phương có thể là ISODate ở ngày UTC trước đó.

### 13.2. Daylight saving time (DST)

Ở một số timezone, một ngày có thể có **23 hoặc 25 giờ** khi chuyển DST.

Do đó:

- Một ngày lịch địa phương **không luôn bằng 86.400 giây**.
- Có giờ địa phương bị bỏ qua hoặc xuất hiện hai lần.
- Group key tạo từ string **YYYY-MM-DD HH** không có offset có thể làm hai giờ khác nhau trùng nhãn.
- $dateTrunc với timezone Olson (ví dụ **America/New_York**) xử lý ranh giới theo timezone, nhưng giao diện vẫn phải thiết kế nhãn giờ lặp đúng.

Không tự cộng fixed offset vào timestamps cho tất cả site rồi cắt ngày bằng chuỗi nếu dữ liệu bao gồm nhiều timezone/DST.

### 13.3. Tuần bắt đầu thứ Hai

~~~javascript
{
  $dateTrunc: {
    date: "$ts",
    unit: "week",
    startOfWeek: "monday",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Nếu không chỉ định startOfWeek, ranh giới tuần có thể khác business calendar. Ghi convention vào schema report để tránh dashboard doanh thu lệch nhau.

### 13.4. Tính độ trễ ingest

Với:

~~~javascript
{
  ts: ISODate("2026-05-10T00:05:00Z"),
  ingestedAt: ISODate("2026-05-10T00:06:15Z")
}
~~~

hiệu hai BSON Dates trả milliseconds:

~~~javascript
{
  $subtract: ["$ingestedAt", "$ts"]
}
~~~

Kết quả ví dụ là **75.000 ms**. **$dateDiff** phù hợp khi đếm ranh giới đơn vị lịch, không nên mặc định thay thế tính elapsed milliseconds chính xác trong mọi tình huống.

### 13.5. Schema summary cần ghi timezone/granularity

~~~javascript
{
  sensorId: "S-01",
  bucketStart: ISODate("2026-05-09T17:00:00Z"),
  timezone: "Asia/Ho_Chi_Minh",
  granularity: "day",
  validSamples: 123
}
~~~

Khi lưu summary của nhiều timezone, **timezone, granularity và site/sensor** có thể cần là một phần của business key. Không gộp nhầm hai ngày địa phương khác timezone chỉ vì cùng một UTC timestamp.

## 14. Tính phân vị, độ lệch chuẩn và chỉ số chất lượng

### 14.1. Một số accumulators hữu ích trong $group

~~~javascript
{
  $group: {
    _id: {
      sensorId: "$meta.sensorId",
      hourStart: {
        $dateTrunc: {
          date: "$ts",
          unit: "hour"
        }
      }
    },
    sampleCount: { $sum: 1 },
    avgTempC: { $avg: "$temperatureC" },
    stdDevPopTempC: { $stdDevPop: "$temperatureC" },
    minTempC: { $min: "$temperatureC" },
    maxTempC: { $max: "$temperatureC" }
  }
}
~~~

**$stdDevPop** tính population standard deviation, trong khi **$stdDevSamp** dùng mẫu thống kê. Phải chọn đúng định nghĩa và giải thích ý nghĩa. Với chỉ một mẫu, stddev sample có thể không xác định theo công thức.

### 14.2. Percentiles (MongoDB 7.0+)

Ví dụ p50 và p95:

~~~javascript
{
  $group: {
    _id: "$meta.sensorId",
    percentiles: {
      $percentile: {
        input: "$temperatureC",
        p: [0.5, 0.95],
        method: "approximate"
      }
    }
  }
}
~~~

Kết quả **percentiles** là array ứng với các xác suất được yêu cầu. Theo semantics của phương thức approximate, không dùng nó làm lời hứa rằng p95 luôn là một giá trị raw sample chính xác.

Không lấy “trung bình các hourly p95” để suy p95 của một ngày; percentiles không cộng gộp theo cách đó.

### 14.3. Kiểm tra số mẫu hợp lệ

Một bucket có thể có 100 measurements nhưng chỉ 15 readings chứa temperatureC hợp lệ. Vì vậy report nên tách:

~~~text
totalReadings
validTempReadings
missingTempReadings
avgTempC
coverage
~~~

Nếu mỗi sensor **dự kiến** có một mẫu mỗi 5 phút, một giờ kỳ vọng 12 mẫu. Có thể tính:

~~~text
coverage = actualValidSamples / expectedSamples
~~~

Nhưng expectedSamples phụ thuộc lịch đo, downtime, DST và loại sensor. Không dùng mẫu số cố định 12 cho mọi thiết bị khi lịch lấy mẫu khác nhau.

## 15. Tổng hợp nhiều cấp: từ hourly statistics sang daily statistics

Một dashboard thường có nhiều mức zoom:

~~~text
Raw measurements (seconds/minutes)
             |
             v
Hourly statistics
             |
             v
Daily statistics
             |
             v
Weekly / Monthly statistics
~~~

Thay vì mỗi request tuần đều quét toàn bộ raw readings, có thể tính daily stats từ hourly summary nếu summary giữ đủ thông tin.

### 15.1. Trung bình của trung bình có thể sai

Giả sử:

| Giờ | Số samples | Nhiệt độ trung bình |
|---|---:|---:|
| 00:00 | 2 | 29 |
| 01:00 | 1 | 29 |
| 03:00 | 2 | 31.5 |

Trung bình đơn giản của ba hourly averages:

~~~text
(29 + 29 + 31.5) / 3
= 29.8333
~~~

Nhưng trung bình trên **tất cả 5 raw readings**:

~~~text
(28 + 30 + 29 + 31 + 32) / 5
= 30
~~~

Tại sao khác? Giờ 01 có một sample nhưng đang được cho trọng số **bằng cả giờ có hai samples**.

### 15.2. Lưu sum và valid count

Hourly summary nên có:

~~~javascript
{
  sensorId: "S-01",
  bucketStart: ISODate("2026-05-10T00:00:00Z"),
  sampleCount: 2,
  sumTempC: 58,
  validTempSamples: 2,
  avgTempC: 29,
  minTempC: 28,
  maxTempC: 30
}
~~~

Khi group lên ngày:

~~~javascript
db.sensor_hourly_stats.aggregate([
  {
    $match: {
      sensorId: "S-01",
      bucketStart: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$sensorId",
        dayStart: {
          $dateTrunc: {
            date: "$bucketStart",
            unit: "day",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: "$sampleCount" },
      sumTempC: { $sum: "$sumTempC" },
      validTempSamples: { $sum: "$validTempSamples" },
      minTempC: { $min: "$minTempC" },
      maxTempC: { $max: "$maxTempC" }
    }
  },
  {
    $set: {
      avgTempC: {
        $cond: [
          { $gt: ["$validTempSamples", 0] },
          {
            $divide: [
              "$sumTempC",
              "$validTempSamples"
            ]
          },
          null
        ]
      }
    }
  }
]);
~~~

**Chỉ tổng hợp lại chính xác khi các hourly fields có nghĩa và đơn vị nhất quán.** Với timezone ngày địa phương, phải dùng timezone tương ứng và chọn đúng time range. Không vô tình tạo một ngày UTC rồi hiển thị như ngày địa phương.

### 15.3. Min/max và stddev

Từ hourly summary:

- **daily min** = min(hourly min).
- **daily max** = max(hourly max).
- **daily sum** = sum(hourly sum).
- **daily count** = sum(hourly count).

Nhưng **daily stddev** không bằng average(hourly stddev). Muốn ghép đúng cần lưu đủ thống kê như count, sum và sum of squares hoặc chạy lại từ raw data.

### 15.4. Percentiles không ghép như mean

Không thể suy chính xác p95 toàn ngày chỉ từ các hourly p95 và counts thông thường. Nếu downstream yêu cầu percentile chuẩn theo toàn bộ raw population, cần:

- Tính lại từ raw measurements.
- Hoặc thiết kế một cơ chế thống kê có cấu trúc mergeable, ví dụ sketch/histogram được xác nhận phù hợp.

### 15.5. Nhiều đại lượng có đơn vị khác nhau

**temperatureC** và **powerW** có semantics khác:

- Nhiệt độ trung bình theo samples là một measurement statistic.
- Công suất trung bình (W) không đồng nghĩa năng lượng tiêu thụ (Wh).
- Năng lượng đòi tích phân công suất theo thời gian; với dữ liệu không đều phải lựa chọn quy tắc nội suy/integration và đơn vị.

Đừng cộng một giờ powerW=100 và giờ sau powerW=150 rồi gắn nhãn **250 kWh**. Sai cả phép tính lẫn đơn vị.

## 16. Tạo materialized statistics collection với $merge

Khi raw collection có hàng triệu readings, việc quét và group lại trên mỗi HTTP request có thể đắt. Một cách giảm tải là **materialized view**: lưu kết quả tổng hợp để query lại.

~~~text
sensor_readings (time series raw)
        |
        v
Aggregation by hour
        |
        v
$merge into sensor_hourly_stats
        |
        v
Dashboard queries summary collection
~~~

### 16.1. Tạo collection summary thông thường

Không cần tạo một **time series collection** cho bảng summary; sử dụng collection bình thường giúp quản lý upserts/replacement/unique index dễ hơn:

~~~javascript
db.createCollection("sensor_hourly_stats");

db.sensor_hourly_stats.createIndex(
  {
    sensorId: 1,
    bucketStart: 1
  },
  {
    unique: true,
    name: "uq_sensor_hour"
  }
);
~~~

**$merge on các field được chỉ định phải có index unique tương ứng theo quy định server**, và không được vô tình tạo nhiều summary cho cùng sensor/giờ.

### 16.2. Recompute một ngày và $merge

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        bucketStart: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      sampleCount: { $sum: 1 },
      validTempSamples: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            1,
            0
          ]
        }
      },
      sumTempC: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            "$temperatureC",
            0
          ]
        }
      },
      minTempC: { $min: "$temperatureC" },
      maxTempC: { $max: "$temperatureC" }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      bucketStart: "$_id.bucketStart",
      granularity: { $literal: "hour" },
      timezone: { $literal: "UTC" },
      sampleCount: 1,
      validTempSamples: 1,
      sumTempC: 1,
      minTempC: 1,
      maxTempC: 1,
      avgTempC: {
        $cond: [
          { $gt: ["$validTempSamples", 0] },
          {
            $divide: [
              "$sumTempC",
              "$validTempSamples"
            ]
          },
          null
        ]
      }
    }
  },
  {
    $merge: {
      into: "sensor_hourly_stats",
      on: ["sensorId", "bucketStart"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
~~~

### 16.3. Vì sao có $project _id:0?

Đầu ra của **$group** có _id dạng composite object. Nhưng **$merge** đang định danh tài liệu summary theo **sensorId + bucketStart**. Nếu gửi một field _id khác với _id có sẵn, một replacement có thể gặp lỗi immutable _id.

Vì vậy **loại bỏ _id của kết quả group trước $merge** khi dùng on fields riêng. MongoDB có thể quản lý _id của document summary mới/tồn tại theo quy tắc $merge.

### 16.4. Ý nghĩa whenMatched

| Chọn | Hành vi |
|---|---|
| **replace** | Thay nội dung summary đang có bằng kết quả tính lại; hữu ích cho recompute. |
| **merge** | Cập nhật/ghép các field được xuất từ pipeline. |
| **keepExisting** | Giữ summary cũ nếu đã tồn tại; không phù hợp khi cần sửa late data. |
| **fail** | Báo lỗi khi có trùng key. |
| **custom pipeline** | Xử lý theo logic được MongoDB hỗ trợ, cần thiết kế cẩn thận. |

Trong bài toán dữ liệu đến trễ, **replace** thường đơn giản hơn “cộng thêm 1 sample” vì pipeline tính lại số liệu đúng từ nguồn, tránh tăng trùng khi job được chạy lại.

### 16.5. $merge là write side effect

Aggregation có **$merge** là pipeline **ghi dữ liệu vào collection đích**. Khi chạy xong, nó không trả các summary rows như pipeline chỉ đọc.

Các updates của $merge trên nhiều documents **không phải một transaction nguyên tử toàn bộ lô**. Nếu job lỗi giữa chừng, một số bucket đã được cập nhật và một số bucket chưa. Thiết kế job **idempotent/recomputable** và có checkpoints, trạng thái run hoặc partition-level publishing khi yêu cầu consistency nghiêm ngặt.

### 16.6. Không chạy nhiều job ghi đè lẫn nhau thiếu điều phối

Nếu một job backfill cũ và một job near-real-time cùng $merge cùng key, job hoàn thành sau có thể thay summary mới bằng kết quả tính từ snapshot cũ hơn.

Có thể:

1. Chỉ có một writer cho mỗi partition/time range.
2. Dùng watermark/version/CAS để kiểm soát publishing.
3. Ghi vào versioned staging collections rồi chuyển view/pointer theo kế hoạch.
4. Tính lại và reconcile sau khi các jobs chồng lấn.

Đừng mặc định $merge whenMatched:"replace" tự giải quyết mọi race giữa nhiều pipelines.

## 17. Dashboard đọc materialized summary

Sau materialization:

~~~javascript
db.sensor_hourly_stats.find(
  {
    sensorId: "S-01",
    bucketStart: {
      $gte: ISODate("2026-05-10T00:00:00Z"),
      $lt: ISODate("2026-05-11T00:00:00Z")
    }
  },
  {
    _id: 0,
    sensorId: 1,
    bucketStart: 1,
    sampleCount: 1,
    avgTempC: 1,
    minTempC: 1,
    maxTempC: 1
  }
).sort({
  bucketStart: 1
});
~~~

Dashboard đọc một summary document mỗi giờ thay vì tất cả raw readings. Nhưng summary có thể **eventually consistent** với nguồn; phải có SLA về lần materialization cuối và cách xử lý stale data.

### 17.1. Một collection hay nhiều collections cho các độ phân giải?

Có thể:

~~~text
sensor_5m_stats
sensor_hourly_stats
sensor_daily_stats
~~~

hoặc:

~~~javascript
{
  sensorId: "S-01",
  bucketStart: ISODate("..."),
  granularity: "hour",
  timezone: "UTC",
  ...
}
~~~

Lựa chọn phụ thuộc schema, index, TTL, retention và query patterns. Nếu dùng chung collection nhiều granularities/timezones, unique key phải bao gồm **granularity, timezone** khi chúng ảnh hưởng ý nghĩa bucket.

### 17.2. Timestamp của summary

Thường lưu:

- **bucketStart**: thời điểm bắt đầu khoảng dữ liệu.
- **bucketEnd** hoặc granularity: xác định khoảng [start,end).
- **computedAt**: lần job tạo/cập nhật summary.
- **sourceWatermark**: mốc dữ liệu nguồn mà job đã xử lý/đảm bảo.
- **dataQuality** hoặc coverage: độ tin cậy của dữ liệu.

**computedAt khác bucketStart**: dữ liệu đo lúc 00:00 có thể được tính lại vào 08:30 sau khi một sensor gửi bù readings.

### 17.3. Kết hợp summary và realtime

Một dashboard có thể đọc:

~~~text
Các giờ đã đóng/sẵn sàng -> sensor_hourly_stats
Giờ hiện tại             -> raw readings / realtime aggregation
~~~

Khi giờ hiện tại kết thúc và đủ late-arrival allowance, pipeline chuyển sang summary ổn định. Nếu dùng cả hai nguồn, định nghĩa rõ ranh giới để tránh hiển thị trùng một giờ.

## 18. Dữ liệu đến trễ, backfill và watermark

### 18.1. Sự kiện xảy ra trước nhưng được lưu sau

Ví dụ:

~~~javascript
{
  ts: ISODate("2026-05-10T01:20:00Z"),
  ingestedAt: ISODate("2026-05-10T04:05:00Z"),
  meta: { sensorId: "S-01", site: "HCM" },
  temperatureC: 35
}
~~~

Dữ liệu này thuộc **bucket 01:00 theo event time**, không phải bucket 04:00.

Nếu hourly summary được tạo lúc 02:10, nó thiếu reading đến trễ trên. Một job chỉ tính bucket của **giờ hiện tại** sẽ không tự sửa kết quả 01:00.

### 18.2. Recompute cửa sổ gần đây

Một chiến lược đơn giản:

~~~text
Mỗi 5 phút:
  Tính lại những buckets của 24 giờ gần nhất.
  Ghi bằng $merge whenMatched:"replace".

Mỗi đêm:
  Reconcile lại những ngày còn trong retention/backfill SLA.
~~~

Số 24 giờ chỉ là ví dụ. Chọn theo **độ trễ thực tế của nguồn và SLA nghiệp vụ**. Nếu readings thường tới trễ 48 giờ thì 24 giờ là không đủ.

### 18.3. Watermark và bucket completeness

Trong stream processing, **watermark** là khái niệm biểu diễn mức event time mà hệ thống tin rằng dữ liệu đến đủ theo giả định cho phép. Ví dụ:

~~~text
Current processing time: 12:00
Allowed lateness: 2 hours
Watermark: 10:00
~~~

Bucket kết thúc trước 10:00 có thể được coi là tương đối hoàn chỉnh **theo SLA 2 giờ**, nhưng không phải bằng chứng dữ liệu không thể tới trễ hơn.

MongoDB aggregation **không tự tạo và duy trì watermark nghiệp vụ** cho bạn. Ứng dụng/job scheduler phải quản lý dữ liệu nguồn, thời gian đến, trạng thái bucket và cách sửa số liệu muộn.

### 18.4. Backfill lịch sử

Nếu cần sửa một tháng lịch sử, hãy chạy aggregation theo **partition/time ranges** đủ nhỏ:

~~~text
Backfill 2026-05:
  Day 01 -> recompute hourly -> merge
  Day 02 -> recompute hourly -> merge
  ...
  Day 31 -> recompute hourly -> merge
~~~

Mỗi partition cần logging, retry và khả năng kiểm tra tổng count/sum. Không tạo một pipeline khổng lồ không thể khôi phục chỉ vì bộ dữ liệu dài.

### 18.5. Delete hoặc correction

Nếu raw measurement bị xóa hoặc sửa, strategy chỉ cộng thêm delta có thể làm lệch summary.

Ví dụ một mẫu 35°C bị xóa:

~~~text
Old bucket: sampleCount=3, sumTempC=95
New bucket: sampleCount=2, sumTempC=60
~~~

**Recompute từ raw dữ liệu hiện tại** rồi replace summary xử lý tốt thay đổi này trong các bucket được tính lại. Với immutable raw events, có thể dùng correction records/compensating data theo kiến trúc được định nghĩa rõ.

### 18.6. Lỗi kinh điển: incremental $inc không idempotent

Nếu consumer nhận một event insert rồi:

~~~javascript
db.sensor_hourly_stats.updateOne(
  { sensorId: "S-01", bucketStart: hourStart },
  {
    $inc: {
      sampleCount: 1,
      sumTempC: temperatureC
    }
  }
);
~~~

thì **replay cùng event** có thể cộng trùng. Muốn incremental processing chính xác cần event deduplication, ordering, transactional checkpoint hoặc phương án khác.

Với lượng dữ liệu vừa phải, **recompute overlap + $merge replace** thường dễ vận hành và phục hồi hơn.

## 19. Tối ưu aggregation trên time series collection

### 19.1. $match càng sớm càng tốt

Một truy vấn phổ biến:

~~~javascript
{
  $match: {
    "meta.sensorId": "S-01",
    ts: {
      $gte: ISODate("2026-05-10T00:00:00Z"),
      $lt: ISODate("2026-05-11T00:00:00Z")
    }
  }
}
~~~

Đặt filter theo **metaField subfield** và **timeField range** sớm để MongoDB có thể tận dụng index/bucket pruning và giảm documents đi qua stages nặng như group, densify, window và merge.

Không bắt đầu bằng một $setWindowFields trên toàn bộ raw collection rồi mới lọc sensor, trừ khi window thực sự cần dữ liệu ngoài phạm vi và bạn đã kiểm soát chi phí.

### 19.2. Chọn indexes theo pattern

Với queries hay lọc theo sensor và time:

~~~javascript
db.sensor_readings.createIndex(
  {
    "meta.sensorId": 1,
    ts: 1
  }
);
~~~

Time series indexes có các quy tắc và khác biệt theo phiên bản server. **Từ MongoDB 6.3, time series collection có thể được tạo sẵn index trên timeField/metaField**, nên cần kiểm tra indexes thực tế trước khi tạo trùng.

Việc một index có ích hay không phụ thuộc cardinality, selectivity, bucket layout và query patterns, không chỉ cú pháp.

### 19.3. metaField ổn định và granularity phù hợp

Time series collection tổ chức measurements vào những storage buckets dựa trên metaField và thời gian.

Best practices:

- Đưa sensorId, site cố định hoặc device type vào metaField nếu dùng thường xuyên để lọc.
- Tránh metadata thay đổi theo từng reading, như requestId ngẫu nhiên.
- Chọn granularity **seconds/minutes/hours** theo khoảng cách measurements.
- Nếu cần custom bucketing theo MongoDB version phù hợp, xem **bucketMaxSpanSeconds / bucketRoundingSeconds**.
- Không nhầm granularity của **storage buckets** với bucket kích thước 15 phút tạo bằng $dateTrunc.

### 19.4. Giới hạn output cardinality

Nếu có:

~~~text
100.000 sensors
12 buckets mỗi giờ cho thống kê 5 phút
24 giờ/ngày
~~~

số bucket output tiềm năng là:

~~~text
100000 × 12 × 24 = 28.800.000 rows/ngày
~~~

Đó là lượng dữ liệu rất lớn ngay cả trước khi densify thêm gaps. Cần giới hạn scope/time range, downsampling theo nhu cầu hiển thị và tránh tạo grid quá chi tiết trên nhiều năm lịch sử.

### 19.5. Quản lý memory và disk spill

**$group**, **$sort** và **$setWindowFields** có thể dùng nhiều memory tùy số partitions và lượng dữ liệu. Khi phù hợp với server version và giới hạn stage, có thể xem **allowDiskUse**:

~~~javascript
db.sensor_readings.aggregate(
  [
    {
      $match: {
        "meta.sensorId": "S-01",
        ts: {
          $gte: ISODate("2026-05-10T00:00:00Z"),
          $lt: ISODate("2026-05-11T00:00:00Z")
        }
      }
    },
    {
      $group: {
        _id: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour"
          }
        },
        avgTempC: { $avg: "$temperatureC" }
      }
    }
  ],
  {
    allowDiskUse: true
  }
);
~~~

Cho phép disk spill **không phải cách sửa một pipeline không giới hạn**. Nó có thể làm tăng disk I/O và latency. Nên ưu tiên giảm input bằng match, partition, indexes và materialization.

### 19.6. Explain và metrics

Để hiểu query plan, có thể dùng:

~~~javascript
db.sensor_readings.explain("executionStats").aggregate([
  {
    $match: {
      "meta.sensorId": "S-01",
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$ts",
          unit: "hour"
        }
      },
      n: { $sum: 1 }
    }
  }
]);
~~~

Quan sát documents/buckets examined, execution time, index usage, sort/group costs và disk spill theo thông tin server cung cấp. Không mặc định output explain có cùng schema giữa các phiên bản MongoDB.

### 19.7. Raw TTL và summary retention

Time series collection có thể cấu hình **expireAfterSeconds** để tự xóa raw measurements đã hết retention:

~~~javascript
db.createCollection("sensor_readings_ttl_demo", {
  timeseries: {
    timeField: "ts",
    metaField: "meta",
    granularity: "minutes"
  },
  expireAfterSeconds: 2592000
});
~~~

Ví dụ này đặt retention khoảng **30 ngày** cho raw data trong collection riêng. Xóa expired data có độ trễ và được tổ chức theo storage buckets; đừng dựa vào một timestamp vừa hết hạn để khẳng định document biến mất tức thì.

Nếu business cho phép corrections sau 60 ngày nhưng raw TTL chỉ 30 ngày, job không thể recompute từ raw cho một bucket cách đây 45 ngày. **Raw retention phải phù hợp late-arrival/backfill SLA**, hoặc cần archive dài hơn.

### 19.8. Dùng materialized summaries để downsample

Một retention strategy:

~~~text
Raw measurements:          30 ngày
5-minute summary:          90 ngày
Hourly summary:             2 năm
Daily summary:              5 năm
~~~

Các mốc trên chỉ minh họa. Quan trọng là:

- Biết thông tin nào mất sau downsampling.
- Giữ enough statistics cho calculations cần thiết.
- Dùng retention phù hợp với privacy/data governance.
- Có biện pháp backfill trước khi raw data hết hạn.

## 20. Java Sync Driver: tổng hợp theo giờ

MongoDB Java Sync Driver cho phép truyền các pipeline stages dưới dạng **Bson**.

### 20.1. Ví dụ Java hoàn chỉnh

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.Date;
import java.util.List;

public final class SensorHourlyStats {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException("MONGODB_URI is required");
        }

        Date from = Date.from(
                Instant.parse("2026-05-10T00:00:00Z")
        );
        Date to = Date.from(
                Instant.parse("2026-05-11T00:00:00Z")
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase(
                    "mongo_timeseries_stats_lab"
            );
            MongoCollection<Document> readings =
                    database.getCollection("sensor_readings");

            Bson match = Aggregates.match(
                    Filters.and(
                            Filters.eq("meta.sensorId", "S-01"),
                            Filters.gte("ts", from),
                            Filters.lt("ts", to)
                    )
            );

            Document dateTrunc = new Document(
                    "$dateTrunc",
                    new Document("date", "$ts")
                            .append("unit", "hour")
                            .append("timezone", "UTC")
            );

            Bson group = new Document(
                    "$group",
                    new Document("_id", dateTrunc)
                            .append(
                                    "sampleCount",
                                    new Document("$sum", 1)
                            )
                            .append(
                                    "avgTempC",
                                    new Document("$avg", "$temperatureC")
                            )
                            .append(
                                    "minTempC",
                                    new Document("$min", "$temperatureC")
                            )
                            .append(
                                    "maxTempC",
                                    new Document("$max", "$temperatureC")
                            )
            );

            List<Bson> pipeline = List.of(
                    match,
                    group,
                    new Document("$sort", new Document("_id", 1))
            );

            readings.aggregate(pipeline)
                    .allowDiskUse(true)
                    .forEach(System.out::println);
        }
    }
}
~~~

Giải thích:

- **Filters.gte/lt** tạo khoảng [from,to).
- **$dateTrunc** định tuyến timestamp vào hourly bucket.
- **$group** tạo một result document cho mỗi giờ.
- **$sort** giúp output ổn định theo giờ.
- **allowDiskUse(true)** chỉ nên dùng khi biết rõ workload; không thay thế index và filter.

Đây là **query-only aggregation**: nó trả summaries ra Java, chưa ghi materialized collection.

### 20.2. Chạy $merge từ Java

Nếu đã tạo unique index và muốn ghi summary, thêm stage:

~~~java
Document mergeStage = new Document(
        "$merge",
        new Document("into", "sensor_hourly_stats")
                .append("on", List.of("sensorId", "bucketStart"))
                .append("whenMatched", "replace")
                .append("whenNotMatched", "insert")
);
~~~

Trước khi append stage này, pipeline cần **$project hoặc $set** để output có đúng fields **sensorId**, **bucketStart** và bỏ group _id như mục $merge ở trên. Không dùng trực tiếp Java pipeline nhóm theo _id chỉ là một Date rồi gắn $merge on hai field chưa tồn tại.

Khi aggregation có $merge, nó **thực hiện writes** và không trả một list summaries như pipeline read-only. Đừng dùng mã xử lý HTTP request đồng bộ kỳ vọng một kết quả JSON lớn từ stage $merge.

### 20.3. Java dữ liệu Date và timezone

Java **Instant** biểu diễn thời điểm tuyệt đối; Date.from(Instant) lưu thành BSON Date. Khi group theo ngày kinh doanh, timezone nên truyền vào **$dateTrunc** như một string Olson, không cộng offset thủ công trên Java Date.

### 20.4. Quản lý dữ liệu số

Với tiền/tài chính, tránh dùng Double để lưu khoản tiền cần chính xác; với readings, double có thể chấp nhận theo precision thiết bị. Nếu sử dụng **Decimal128**, cần nhất quán BSON type và kiểm tra phép tích lũy.

Java code trên chỉ minh họa, production cần timeout, exception handling, pagination/batch logic, authentication và resource budgets.

## 21. Spring Data MongoDB: xây aggregation pipeline

Spring Data MongoDB hỗ trợ **MongoTemplate.aggregate()** và builders cho các stages phổ biến. Với các operators nâng cao hoặc mới như dateTrunc/densify/fill, có thể dùng **AggregationOperation** để cung cấp một stage BSON chính xác theo phiên bản Spring Data.

### 21.1. Ví dụ dùng MongoTemplate

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.query.Criteria;

import java.time.Instant;
import java.util.Date;
import java.util.List;

public final class SpringHourlyStatsService {

    private final MongoTemplate template;

    public SpringHourlyStatsService(MongoTemplate template) {
        this.template = template;
    }

    public List<Document> hourly(String sensorId) {
        Date from = Date.from(
                Instant.parse("2026-05-10T00:00:00Z")
        );
        Date to = Date.from(
                Instant.parse("2026-05-11T00:00:00Z")
        );

        AggregationOperation match = Aggregation.match(
                Criteria.where("meta.sensorId").is(sensorId)
                        .and("ts").gte(from).lt(to)
        );

        AggregationOperation group = context -> new Document(
                "$group",
                new Document(
                        "_id",
                        new Document(
                                "$dateTrunc",
                                new Document("date", "$ts")
                                        .append("unit", "hour")
                                        .append("timezone", "UTC")
                        )
                )
                        .append(
                                "sampleCount",
                                new Document("$sum", 1)
                        )
                        .append(
                                "avgTempC",
                                new Document("$avg", "$temperatureC")
                        )
        );

        AggregationOperation sort = context ->
                new Document("$sort", new Document("_id", 1));

        Aggregation aggregation = Aggregation.newAggregation(
                match,
                group,
                sort
        );

        return template.aggregate(
                aggregation,
                "sensor_readings",
                Document.class
        ).getMappedResults();
    }
}
~~~

Trong ví dụ:

- **Aggregation.match(Criteria)** giới hạn sensor/time sớm.
- **AggregationOperation lambda** tạo stages raw Document.
- **MongoTemplate.aggregate** trả các group results.

Không dùng cùng một Java DTO cứng nếu output _id/group fields khác schema của raw measurement. Có thể tạo DTO chuyên cho hourly summary và map rõ ràng.

### 21.2. Spring Data mapping lưu ý

Khi viết raw **AggregationOperation**, các field names bên trong Document phải tương ứng tên field **thực tế đã lưu trong MongoDB**. Nếu entity dùng annotation **@Field** đổi tên thuộc tính, cần kiểm tra mapping context và dùng typed builders hoặc reference field names chính xác.

### 21.3. ReactiveMongoTemplate

Với reactive stack, có thể dùng **ReactiveMongoTemplate.aggregate()** trả một **Flux** những kết quả aggregate. Tuy nhiên:

- Flux không làm phép $group miễn phí ở server.
- Consumer cần backpressure và không block event-loop.
- Các queries kéo dài vẫn có resource limits và timeout.
- Pipeline $merge là **write side effect**, không phải nguồn dữ liệu để stream như query-only aggregate.

Không tạo aggregation nặng cho mỗi WebSocket subscriber mà không kiểm soát caching/concurrency.

### 21.4. Version compatibility

Operators $dateTrunc, $setWindowFields, $densify, $fill và $percentile có mốc server version khác nhau. Spring Data MongoDB version cũng quyết định mức độ hỗ trợ builder API.

Nếu builder cho một operator chưa có, có thể cung cấp BSON stage qua AggregationOperation, nhưng server vẫn phải hỗ trợ operator đó. **Raw Document không làm một MongoDB 4.4 hiểu $dateTrunc**.

## 22. Pipeline đầy đủ: hourly summary, gap detection và rolling average

Phần này kết hợp các khái niệm vào một pipeline **chỉ đọc**, hữu ích để hiển thị một đồ thị theo giờ có độ phủ dữ liệu.

Mục tiêu:

1. Tính hourly sum/count/avg cho S-01.
2. Bổ sung giờ thiếu giữa bucket đầu và bucket cuối.
3. Phân biệt **NO_SAMPLES** và **OBSERVED**.
4. Fill counts/sums của giờ thiếu bằng 0.
5. Tính rolling mean của **các raw samples trong ba bucket lịch gần nhất**.
6. Trả các rows theo thứ tự thời gian.

~~~javascript
db.sensor_readings.aggregate([
  {
    $match: {
      "meta.sensorId": "S-01",
      ts: {
        $gte: ISODate("2026-05-10T00:00:00Z"),
        $lt: ISODate("2026-05-10T05:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        sensorId: "$meta.sensorId",
        hourStart: {
          $dateTrunc: {
            date: "$ts",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      documentCount: {
        $sum: 1
      },
      validTempSamples: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            1,
            0
          ]
        }
      },
      sumTempC: {
        $sum: {
          $cond: [
            { $isNumber: "$temperatureC" },
            "$temperatureC",
            0
          ]
        }
      },
      minTempC: { $min: "$temperatureC" },
      maxTempC: { $max: "$temperatureC" }
    }
  },
  {
    $project: {
      _id: 0,
      sensorId: "$_id.sensorId",
      hourStart: "$_id.hourStart",
      documentCount: 1,
      validTempSamples: 1,
      sumTempC: 1,
      minTempC: 1,
      maxTempC: 1
    }
  },
  {
    $densify: {
      field: "hourStart",
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
      dataStatus: {
        $cond: [
          { $eq: ["$documentCount", null] },
          "NO_SAMPLES",
          "OBSERVED"
        ]
      }
    }
  },
  {
    $fill: {
      partitionByFields: ["sensorId"],
      sortBy: {
        hourStart: 1
      },
      output: {
        documentCount: { value: 0 },
        validTempSamples: { value: 0 },
        sumTempC: { value: 0 }
      }
    }
  },
  {
    $set: {
      avgTempC: {
        $cond: [
          { $gt: ["$validTempSamples", 0] },
          {
            $divide: [
              "$sumTempC",
              "$validTempSamples"
            ]
          },
          null
        ]
      }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$sensorId",
      sortBy: {
        hourStart: 1
      },
      output: {
        rolling3hTempSum: {
          $sum: "$sumTempC",
          window: {
            documents: [-2, 0]
          }
        },
        rolling3hValidSamples: {
          $sum: "$validTempSamples",
          window: {
            documents: [-2, 0]
          }
        },
        cumulativeSampleCount: {
          $sum: "$documentCount",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $set: {
      rolling3hRawAvgTempC: {
        $cond: [
          { $gt: ["$rolling3hValidSamples", 0] },
          {
            $divide: [
              "$rolling3hTempSum",
              "$rolling3hValidSamples"
            ]
          },
          null
        ]
      }
    }
  },
  {
    $sort: {
      sensorId: 1,
      hourStart: 1
    }
  }
]);
~~~

Kết quả chính trên dữ liệu mẫu S-01:

| Giờ UTC | documentCount | avgTempC | dataStatus | rolling3hRawAvgTempC |
|---|---:|---:|---|---:|
| 00:00 | 2 | 29 | OBSERVED | 29 |
| 01:00 | 1 | 29 | OBSERVED | 29 |
| 02:00 | 0 | null | NO_SAMPLES | 29 |
| 03:00 | 2 | 31.5 | OBSERVED | 30.6667 |

Giải thích:

- 02:00 không có mẫu, nên avgTempC = null nhưng **rolling 3 giờ** vẫn có thể tính từ các giờ 00 và 01 (vì window [00,02] có dữ liệu).
- 03:00 dùng các bucket 01,02,03; sumTempC = 29+0+63=92, validTempSamples=1+0+2=3; kết quả **92/3 ≈ 30.6667**.
- **cumulativeSampleCount** cuối cùng = 5.

### 22.1. Nếu muốn trả giờ 04:00 dù chưa có mẫu

Đổi **bounds** từ "partition" sang explicit date range với upper exclusive 05:00 như mục $densify. Khi đó row 04:00 có thể được sinh cho S-01 dù reading cuối ở 03:50.

### 22.2. Nếu cần dữ liệu mọi sensor kể cả sensor offline hoàn toàn

Pipeline bắt đầu từ readings chỉ biết những sensor có ít nhất một source document trong khoảng được match. Một sensor hoàn toàn offline không có partition đầu vào, nên không được tự tạo.

Giải pháp là dùng **sensors inventory** (danh mục nguồn đo) và tạo/lấy time grid cho mỗi sensor theo yêu cầu, rồi left-join/lookup summary. Điều này quan trọng đối với báo cáo SLA, vì “sensor offline hoàn toàn” không được biến mất khỏi dashboard chỉ do nó không gửi readings.

### 22.3. Không thay thế raw values bằng giá trị nội suy trong thống kê chính

Pipeline giữ **avgTempC=null** ở 02:00. Nếu UI cần đường biểu diễn liền mạch, có thể tạo thêm một field **displayTempC** bằng nội suy hoặc locf. Nên để dataStatus cho biết đâu là giá trị thật và đâu là giá trị dự đoán.

## 23. Độ tin cậy, tính nhất quán và giới hạn của materialization

### 23.1. $merge không xóa summary khi bucket không còn source reading

Đây là trường hợp đặc biệt rất quan trọng:

1. Ban đầu bucket 01:00 có ba readings nên summary đã được tạo.
2. Sau đó cả ba readings bị xóa/corrected ở raw source.
3. Pipeline chạy lại **$group → $merge**.
4. Vì không còn source readings cho bucket 01:00, **$group không tạo row cho bucket đó**.
5. **$merge không tự xóa** document summary cũ không có row đầu vào tương ứng.

Vậy summary 01:00 có thể **bị stale** dù các buckets khác đã được replace.

Các cách xử lý:

- Tạo time grid cố định cho các buckets cần publish, cả bucket count 0.
- Rebuild một partition/range vào staging collection rồi thay tập summaries tương ứng có kiểm soát.
- Reconciliation tìm summary keys không còn trong raw-derived keys và xóa/đánh dấu stale.
- Nếu không cho phép physical deletes của raw data, dùng immutable correction events với business semantics rõ.

Không coi $merge replace là phép “đồng bộ hoàn chỉnh hai chiều” giữa source và output collection.

### 23.2. Out-of-order/late arrival

Late readings có thể làm thay average/min/max của một bucket đã được dashboard xem là finalized. Nên có trạng thái:

~~~text
OPEN
  -> PROVISIONAL
  -> FINALIZED
  -> CORRECTED (nếu có backfill)
~~~

Các trạng thái do ứng dụng quyết định, không phải trường tự động MongoDB aggregation sinh ra.

### 23.3. Độ mới của bảng thống kê

Dashboard cần biết:

- Summary được tính **khi nào**?
- Nguồn dữ liệu đã đầy đủ **tới mốc event time nào**?
- Có backlog từ ingestion không?
- Raw retention có còn đủ để recompute không?
- Có jobs nào thất bại hoặc đang backfill không?

Trả mỗi **avgTempC** mà không có freshness metadata có thể gây hiểu nhầm rằng dữ liệu đang realtime.

### 23.4. Các writes cạnh tranh

Nếu batch job và realtime job cùng ghi summary key, **last writer wins** có thể làm một summary mới bị thay bằng số liệu cũ. Cần điều phối job, version guard hoặc storage versioning; $merge tự nó không thực thi mọi business constraints.

### 23.5. Multi-tenant data

Nếu sensors thuộc tenants khác nhau, summary key cần bao gồm **tenantId** hoặc một sensor ID toàn hệ thống được chứng minh unique. Nếu chỉ group theo một sensorId có thể lặp giữa tenants, hai tenant có thể bị gộp dữ liệu.

Ví dụ đúng hơn trong multi-tenant system:

~~~javascript
_id: {
  tenantId: "$meta.tenantId",
  sensorId: "$meta.sensorId",
  hourStart: {
    $dateTrunc: {
      date: "$ts",
      unit: "hour",
      timezone: "UTC"
    }
  }
}
~~~

Index unique summary nên phản ánh cùng business key. Quyền truy cập và query filters của API vẫn phải kiểm tra tenant từ context xác thực.

### 23.6. Dữ liệu số bất thường

Phân biệt:

- **Sensor outage:** không có readings.
- **Bad value:** có reading nhưng temperatureC ngoài khoảng vật lý.
- **Duplicate event:** cùng measurement bị ghi lặp.
- **Calibration correction:** giá trị cũ được thay/sửa theo luật.

Không coi mọi con số là hợp lệ chỉ vì BSON type là numeric. Validation/calibration chính xác cần quy tắc nghiệp vụ (ví dụ temperatureC trong khoảng thiết bị đo được), và deduplication theo event ID nếu cần.

## 24. Checklist triển khai production

### 24.1. Thiết kế dữ liệu

1. Xác định chính xác **event time** và **ingestion time**.
2. Chọn BSON Date/UTC và timezone dùng khi báo cáo.
3. Tạo time series collection có **timeField** và **metaField** ổn định.
4. Chọn granularity lưu trữ, indexes và raw retention.
5. Định nghĩa schema cho metrics: đơn vị, kiểu số, null, missing, outliers.
6. Có deduplication key nếu ingestion có thể replay.

### 24.2. Thiết kế aggregation

1. Đưa **$match** theo tenant/sensor/time lên sớm.
2. Dùng **$dateTrunc** đúng binSize/timezone/startOfWeek.
3. Xác định metric là raw sample average hay average của bucket averages.
4. Dùng **$setWindowFields** với partition/sort/window boundaries đúng.
5. Dùng **$densify/$fill** nếu cần, không biến missing measurement thành 0 sai ngữ nghĩa.
6. Bảo đảm timestamps trùng có tie-breaker nếu phép tính phụ thuộc thứ tự.
7. Bổ sung **$sort** ở cuối khi response cần order.
8. Phân biệt output provisional và finalized khi có late data.

### 24.3. Materialization và lifecycle

1. Chọn output collection thường, unique business key cho $merge.
2. Giữ **sum, count, min/max**, không chỉ average.
3. Cân nhắc timezone và granularity trong summary key.
4. Có overlap recompute cho late arrivals.
5. Có full backfill/reconciliation khi raw correction/delete.
6. Xử lý summary không còn source data.
7. Không để concurrent jobs ghi đè snapshot cũ lên kết quả mới.
8. Theo dõi computedAt, watermark, dataQuality và last successful run.

### 24.4. Hiệu năng và vận hành

1. Đo index usage, input rows và output cardinality.
2. Giới hạn số partitions và output rows của densify.
3. Không để một dashboard request chạy $group toàn lịch sử hàng năm.
4. Theo dõi memory/disk spill của group/sort/window.
5. Có timeout, retry policy và backoff theo loại lỗi.
6. Không bật allowDiskUse để che mọi vấn đề thiết kế.
7. Raw TTL phải phù hợp độ trễ/backfill SLA.
8. Có test với dữ liệu không đều, nulls, timezone DST và late data.

## 25. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Hướng sửa |
|---|---|---|
| Dùng average của các hourly averages | Sai khi sample count khác nhau. | Giữ sum+validCount, tính weighted mean. |
| Dùng documents:[-2,0] và gọi là 3 giờ | Bỏ qua gaps, có thể phủ nhiều giờ hơn. | Dùng time range hoặc densify bucket grid. |
| Chỉ dùng $fill, không có row bị thiếu | Không tạo được giờ trống. | $densify trước, hoặc time grid riêng. |
| Fill nhiệt độ thiếu bằng 0 | Biểu đồ có nhiệt độ giả. | Null + dataStatus hoặc interpolation minh bạch. |
| Dùng local time string làm group key | DST có giờ trùng, timezone sai. | BSON Date + $dateTrunc timezone rõ. |
| Dùng $merge mà không có unique index theo on | $merge fail hoặc summary duplicate/conflict. | Unique index và business key thống nhất. |
| Chỉ lưu avg, không lưu sum/count | Không thể tính average ngày đúng từ các giờ. | Lưu các sufficient statistics. |
| Chỉ tính bucket mới nhất | Late data không sửa được bucket cũ. | Overlap recompute/backfill. |
| Xóa hết source của một bucket | $merge không xóa summary cũ. | Reconciliation, grid 0-count hoặc rebuild range. |
| Densify toàn lịch sử | Số rows và tải tăng rất lớn. | Giới hạn sensor/time, downsample. |
| TTL raw ngắn hơn backfill SLA | Không thể tái tính sau khi data hết hạn. | Chọn retention/archive phù hợp. |
| Không lọc tenant trong group | Có nguy cơ gộp dữ liệu giữa tenants. | Group theo tenant+sensor+bucket. |
| Dùng sum powerW làm kWh | Sai đơn vị và phương pháp tích phân. | Định nghĩa sampling/integration của năng lượng. |
| Đọc một summary vừa được tính rồi coi là realtime | Báo cáo có thể stale. | Watermark/computedAt + SLA. |

## 26. Bài thực hành

### Bài 1 — Xác định event time và ingestion time

Một cảm biến đo lúc 10:05 nhưng do mất kết nối, server nhận dữ liệu lúc 11:50. Hãy cho biết:

1. Measurement thuộc bucket giờ nào nếu thống kê nhiệt độ tại thời điểm đo?
2. Measurement thuộc bucket giờ nào nếu thống kê lưu lượng dữ liệu được server nhận?
3. Vì sao hai báo cáo không nên dùng cùng trường timestamp một cách mặc định?

### Bài 2 — Tổng hợp theo giờ

Từ collection sensor_readings, viết pipeline group theo **meta.sensorId** và đầu giờ UTC. Kết quả có:

~~~text
sensorId, hourStart, sampleCount, avgTempC, minTempC, maxTempC
~~~

Kiểm tra S-01 ở giờ 00:00 có hai samples 28°C và 30°C, average = 29°C.

### Bài 3 — Bucket 15 phút

Viết lại expression **$dateTrunc** để tạo bucket 15 phút. Hai readings lúc 00:05 và 00:35 thuộc những buckets nào?

### Bài 4 — Group theo ngày Việt Nam

Viết pipeline group theo **dayStart** với timezone **Asia/Ho_Chi_Minh**. Giải thích vì sao dayStart cho một ngày địa phương có thể hiển thị thuộc ngày UTC trước đó.

### Bài 5 — Tuần bắt đầu thứ Hai

Viết expression dùng **$dateTrunc** với unit:"week", startOfWeek:"monday" và timezone mong muốn.

### Bài 6 — Count hợp lệ khác count documents

Giả sử một giờ có 12 documents, trong đó 3 documents thiếu temperatureC. Hãy viết:

~~~text
totalDocuments = 12
validTempSamples = 9
avgTempC dựa trên 9 mẫu hợp lệ
~~~

Sử dụng **$isNumber**, **$cond**, **$sum**, **$avg**.

### Bài 7 — Documents window và time-range window

Với measurements:

~~~text
00:05 -> 28
00:35 -> 30
01:10 -> 29
03:20 -> 31
~~~

Ở reading lúc 03:20, hãy liệt kê những readings nào nằm trong:

- documents:[-2,0]
- range:[-60,0], unit:"minute"

Tại sao kết quả hai cửa sổ có thể khác nhau?

### Bài 8 — Cumulative sample count

Từ hourly summaries của S-01 có counts 2,1,2, hãy dùng **$setWindowFields** tạo cumulative count 2,3,5 theo thứ tự giờ.

### Bài 9 — $shift và delta

Viết pipeline lấy previousTemperatureC và previousTs cho mỗi sensor theo ts, rồi tính deltaTempC. Giải thích cách xử lý row đầu tiên khi previous=null.

### Bài 10 — Tính rate

Ở 00:05 nhiệt độ 28°C, 00:35 nhiệt độ 30°C. Hãy tính rate theo °C/giờ với giả định biến thiên tuyến tính trong khoảng đó. Vì sao phải kiểm tra elapsedMs > 0?

### Bài 11 — EMA

Viết $setWindowFields với **$expMovingAvg** dùng N=3 cho từng sensor. Vì sao EMA trên measurements không đều không tự trở thành trung bình của ba giờ lịch?

### Bài 12 — Thêm giờ thiếu bằng $densify

S-01 không có readings trong giờ 02:00. Từ hourly summaries, viết $densify với partitionByFields:["sensorId"], step=1, unit:"hour", bounds:"partition".

### Bài 13 — Điền count nhưng không điền nhiệt độ

Sau densify, dùng $fill để đưa sampleCount ở giờ 02 thành 0. Giữ avgTempC là null/missing. Vì sao không nên gán 0°C?

### Bài 14 — Nội suy tuyến tính

Giờ 01 có avgTempC = 29, giờ 03 có avgTempC = 31.5, giờ 02 thiếu dữ liệu. Dùng $fill method:"linear" rồi giải thích kết quả 30.25 và giả định nội suy.

### Bài 15 — Sự khác nhau giữa hai moving averages

Tại 03:00, S-01 có:

~~~text
01:00 -> 1 sample: 29
02:00 -> 0 sample
03:00 -> 2 samples: 31,32
~~~

Tính:

1. Trung bình của hai hourly averages có dữ liệu.
2. Trung bình trên ba raw samples.
3. Giải thích vì sao hai kết quả khác nhau.

### Bài 16 — Daily mean từ hourly summary

Cho bảng:

| Hour | count | sumTempC | avgTempC |
|---|---:|---:|---:|
| 00 | 2 | 58 | 29 |
| 01 | 1 | 29 | 29 |
| 03 | 2 | 63 | 31.5 |

Viết pipeline tính daily average đúng bằng **150 / 5 = 30**, không dùng average của ba averages.

### Bài 17 — Percentile

Dùng **$percentile** (MongoDB 7.0+) để tính p50 và p95 của temperatureC theo sensor. Vì sao p95 của một ngày không bằng average các hourly p95?

### Bài 18 — Materialized summary

Tạo collection sensor_hourly_stats và unique index trên sensorId+bucketStart. Viết pipeline group hourly rồi **$merge** với whenMatched:"replace", whenNotMatched:"insert".

### Bài 19 — Vì sao bỏ group _id trước $merge?

Phân tích trường hợp summary đã có _id ObjectId do MongoDB tạo, nhưng đầu vào của $merge còn _id composite object từ $group. Rủi ro immutable _id là gì?

### Bài 20 — Late arrival

Một reading lúc 01:20 đến database lúc 04:05, sau khi summary 01:00 đã được tạo. Thiết kế một lịch recompute overlap và giải thích vì sao chỉ xử lý giờ hiện tại làm số liệu sai.

### Bài 21 — Bucket bị xóa hết raw readings

Summary 02:00 đã tồn tại. Sau đó tất cả raw readings thuộc giờ 02 bị xóa. Chạy lại $group → $merge replace có tự xóa summary cũ không? Đề xuất cơ chế reconciliation.

### Bài 22 — Timezone có DST

Một dashboard ở America/New_York phân nhóm ngày và giờ. Giải thích vì sao một ngày có thể 23 hoặc 25 giờ và tại sao không nên dùng string HH không có offset làm khóa duy nhất.

### Bài 23 — TTL và backfill

Raw data được giữ 30 ngày nhưng business cho phép correction sau 45 ngày. Điều gì có thể xảy ra? Đề xuất một chính sách retention hoặc archive hợp lý.

### Bài 24 — Java Sync Driver

Viết Java aggregation bằng **Filters.gte/lt** theo ts, **$dateTrunc** theo giờ và **$group** tính average. Trả kết quả thành Document list mà không materialize.

### Bài 25 — Spring Data MongoDB

Dùng **MongoTemplate.aggregate()** kết hợp Aggregation.match và AggregationOperation raw Document cho $dateTrunc. Nếu project có **@Field** đổi tên field lưu trữ, cần lưu ý điều gì?

### Bài 26 — Multi-tenant aggregation

Hai tenants đều có sensorId "S-01". Viết group key và unique index summary sao cho readings không trộn lẫn giữa tenants.

### Bài 27 — Đánh giá độ phủ dữ liệu

Một sensor dự kiến gửi một reading mỗi 5 phút, nhưng một giờ chỉ có 7 readings hợp lệ. Tính coverage và đề xuất cách thể hiện với UI: dữ liệu đầy đủ, thiếu một phần hay không đủ tin cậy.

### Bài 28 — Sizing $densify

Một hệ thống có 100.000 sensors, cần điểm thống kê mỗi 5 phút cho 24 giờ. Tính số rows lý thuyết và giải thích vì sao không nên densify tất cả sensors trên mỗi HTTP request.

## 27. Câu hỏi ôn tập

1. Time series collection lưu measurements theo những thành phần nào?
2. metaField khác timeField như thế nào?
3. Storage buckets có đồng nghĩa với các hourly aggregation buckets không?
4. Tại sao nên lưu event time và ingestion time riêng?
5. Vì sao thường dùng khoảng [start,end) khi lọc thời gian?
6. $dateTrunc giải quyết bài toán gì?
7. binSize và unit được dùng thế nào để tạo bucket 15 phút?
8. Khi nào startOfWeek quan trọng?
9. Vì sao $group không tạo hourly bucket không có raw readings?
10. $avg có tự đếm missing/null numeric fields như số 0 không?
11. $isNumber và validSampleCount giúp gì?
12. Documents window khác range window ra sao?
13. $setWindowFields partitionBy giúp tránh lỗi gì?
14. Vì sao phải $sort cuối pipeline khi cần thứ tự kết quả?
15. $shift được dùng trong tính toán nào?
16. EMA theo readings có phải EMA theo thời gian đều không?
17. $densify và $fill có vai trò khác nhau thế nào?
18. Khi nào được phép điền 0 vào một bucket thiếu dữ liệu?
19. Nội suy tuyến tính có thể dẫn tới hiểu nhầm nào?
20. Trung bình của hourly averages có luôn bằng daily average không?
21. Vì sao phải giữ sum + count khi materialize summary?
22. Có thể tính daily percentile chỉ bằng average(hourly percentile) không?
23. $merge cần unique index như thế nào khi dùng custom on fields?
24. Vì sao loại group _id trước $merge whenMatched:"replace"?
25. $merge có bảo đảm toàn bộ buckets được update atomically không?
26. Nếu một bucket không còn source readings, $merge có tự xóa summary cũ không?
27. Late-arriving data làm số liệu cũ bị sai như thế nào?
28. Watermark có phải một field MongoDB aggregation tự tạo sẵn không?
29. Timestamp ở timezone có DST ảnh hưởng ranh giới ngày/giờ như thế nào?
30. Khi nào nên dùng raw aggregation, khi nào nên dùng materialized summary?
31. Time series index/metaField/granularity ảnh hưởng query performance như thế nào?
32. Điều gì xảy ra nếu raw TTL ngắn hơn backfill SLA?
33. Java Sync Driver truyền BSON stages tới aggregate() như thế nào?
34. Spring Data có thể dùng AggregationOperation để thêm stage chưa có builder ra sao?
35. Vì sao cần kiểm tra server version trước khi dùng $densify hoặc $fill?

## 28. Tổng kết

Tổng hợp chuỗi thời gian trong MongoDB không chỉ là tính một phép trung bình. Một pipeline thống kê đúng cần xác định **thời gian, độ phân giải, partition, vùng dữ liệu, cách xử lý missing values và phương pháp tổng hợp**.

Ba mô hình chính:

~~~text
FIXED / TUMBLING BUCKETS
  $match -> $dateTrunc -> $group
  Ví dụ: trung bình từng giờ.

SLIDING / ROLLING WINDOWS
  $setWindowFields
  Ví dụ: moving average, cumulative sum, previous reading.

MATERIALIZED SUMMARIES
  $match -> $group -> $project -> $merge
  Ví dụ: sensor_hourly_stats phục vụ dashboard.
~~~

Khi thời gian không đều:

~~~text
Observed buckets
    |
    v
 $densify
    |
    v
Rows tại mốc thời gian còn thiếu
    |
    v
 $fill có kiểm soát
    |
    v
Window calculations trên time grid
~~~

Các điểm cần nhớ:

1. **$dateTrunc** tạo bucket key theo unit, binSize, timezone và startOfWeek.
2. **$group** chỉ tạo kết quả cho groups có source documents; không tự tạo khoảng rỗng.
3. **$setWindowFields** hỗ trợ rolling/cumulative computations; **documents window** khác **time range window**.
4. **$densify** tạo mốc thiếu, **$fill** điền field thiếu; không giả định missing measurement = 0.
5. **Trung bình có trọng số** từ raw measurements phải được tính bằng tổng sums chia tổng valid counts, không phải trung bình các bucket averages.
6. **$merge** giúp lưu summary có unique key và chạy lại được, nhưng không tự xóa stale buckets hoặc bảo đảm atomicity toàn bộ batch.
7. **Late data, corrections và TTL** cần kế hoạch recompute, backfill và reconciliation.
8. **Timezone/DST** là một phần của business semantics khi thống kê theo ngày/tuần địa phương.
9. **metaField/timeField indexes, filter sớm, output cardinality và allowDiskUse** quyết định chi phí.
10. **Java Driver và Spring Data** có thể xây các aggregation pipelines tương tự mongosh, với yêu cầu server-version compatibility.

### Tài liệu MongoDB chính thức

- [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — timeField, metaField và storage buckets.
- [Best Practices for Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-best-practices/) — metadata, granularity, indexes và ingest/query performance.
- [$dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/) — fixed time buckets, timezone, startOfWeek.
- [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — count/sum/min/max/average và accumulators.
- [$setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/) — documents/range windows, cumulative và moving statistics.
- [$shift](https://www.mongodb.com/docs/manual/reference/operator/aggregation/shift/) — previous/next row.
- [$expMovingAvg](https://www.mongodb.com/docs/manual/reference/operator/aggregation/expMovingAvg/) — exponential moving average.
- [$densify](https://www.mongodb.com/docs/manual/reference/operator/aggregation/densify/) — tạo mốc thời gian/số bị thiếu.
- [$fill](https://www.mongodb.com/docs/manual/reference/operator/aggregation/fill/) — constant, locf và linear interpolation.
- [$percentile](https://www.mongodb.com/docs/manual/reference/operator/aggregation/percentile/) — percentiles và phương thức tính.
- [$merge](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/) — materialized results, on fields và unique index.
- [MongoDB Java Sync Driver Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/) — tạo và thực thi pipelines trong Java.
- [Spring Data MongoDB Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — MongoTemplate, Aggregation và AggregationOperation.

Khi xây một hệ thống thống kê chuỗi thời gian, hãy bắt đầu bằng câu hỏi **“mỗi con số đại diện cho khoảng thời gian nào, trên những measurements nào và với mức độ đầy đủ dữ liệu ra sao?”**. Từ câu trả lời đó, chọn bucket/window đúng, bảo toàn metadata về độ phủ và thiết kế materialization có thể tái tính. Cách này giúp báo cáo nhanh hơn nhưng vẫn có khả năng giải thích và kiểm chứng khi dữ liệu đến trễ hoặc thay đổi.






