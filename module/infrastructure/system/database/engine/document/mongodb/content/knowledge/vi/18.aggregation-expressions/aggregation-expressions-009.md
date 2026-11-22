# Tính toán ngày giờ, múi giờ, $dateTrunc, $dateAdd và $dateDiff trong MongoDB

Một ứng dụng thường lưu thời điểm xảy ra sự kiện, đặt lịch hẹn, tính hạn thanh toán, thống kê doanh thu theo ngày hoặc xác định thời gian xử lý yêu cầu. Những thao tác tưởng như đơn giản — “gộp đơn hàng theo ngày”, “cộng thêm một tháng”, “đếm số ngày giữa hai mốc” — lại dễ sai khi dữ liệu chứa **múi giờ**, lịch dương, tháng có số ngày khác nhau và thời điểm chuyển **giờ mùa hè (Daylight Saving Time, DST)**.

MongoDB có các **biểu thức aggregation ngày giờ** để xử lý trực tiếp trên BSON Date, trong đó ba toán tử quan trọng là:

- **$dateTrunc**: đưa một thời điểm về **đầu khoảng thời gian** chứa nó, chẳng hạn đầu ngày, đầu tuần hoặc đầu tháng theo một múi giờ.
- **$dateAdd**: cộng hoặc trừ **một lượng đơn vị lịch/thời gian** vào một thời điểm, có xét múi giờ khi được chỉ định.
- **$dateDiff**: tính **số ranh giới của đơn vị thời gian** giữa hai mốc, không đơn thuần là lấy số mili giây chia cho độ dài cố định của mọi đơn vị.

Bài học tập trung vào cách sử dụng đúng các biểu thức này trong MongoDB aggregation, phân biệt thời điểm tuyệt đối với lịch địa phương, tránh lỗi ở ranh giới ngày/tháng, phân tích hiệu năng và áp dụng trong Java/Spring Data MongoDB.

Các toán tử **$dateTrunc**, **$dateAdd** và **$dateDiff** được giới thiệu từ **MongoDB 5.0**. Hãy kiểm tra phiên bản thực tế của server trước khi áp dụng. Ví dụ bên dưới sử dụng **mongosh** và database dành riêng cho học tập.

## 1. Nền tảng: BSON Date, UTC và múi giờ

### 1.1. BSON Date biểu diễn một thời điểm

Trong MongoDB, BSON Date là một giá trị thời điểm được lưu theo số mili giây so với Unix epoch, dựa trên UTC. Ví dụ:

~~~javascript
{
  _id: "E01",
  occurredAt: ISODate("2026-11-14T18:30:00Z")
}
~~~

Hậu tố **Z** nghĩa là UTC. Đây là **một thời điểm tuyệt đối**. Nó có thể được hiển thị khác nhau tùy múi giờ:

| Múi giờ | Giờ địa phương ứng với thời điểm trên |
|---|---|
| UTC | 14/11/2026 lúc 18:30 |
| Asia/Ho_Chi_Minh (UTC+07:00) | 15/11/2026 lúc 01:30 |
| America/New_York (EST, UTC−05:00 vào thời điểm này) | 14/11/2026 lúc 13:30 |

**Điểm quan trọng:** giá trị BSON Date không mang theo tên múi giờ gốc của người dùng. Múi giờ được áp dụng **khi diễn giải hoặc tính toán**. Nếu ứng dụng cần ghi nhớ “cuộc hẹn lúc 9 giờ sáng theo giờ New York”, nên lưu thời điểm UTC đã quy đổi, đồng thời lưu thông tin múi giờ nghiệp vụ nếu cần tái diễn giải hoặc tính lịch.

Sự khác nhau về ngày giữa các múi giờ chính là lý do không được nhóm sự kiện chỉ theo ngày UTC khi báo cáo yêu cầu “ngày địa phương”.

### 1.2. ISODate() khác String chứa ngày

Hai giá trị sau không cùng kiểu:

~~~javascript
{ occurredAt: ISODate("2026-11-14T18:30:00Z") }

{ occurredAt: "2026-11-14T18:30:00Z" }
~~~

Giá trị đầu là BSON Date. Giá trị sau là BSON String. Không nên mặc định các toán tử ngày giờ sẽ tự chuyển mọi String thành Date.

Nếu nguồn dữ liệu đã lưu chuỗi ISO-8601, có thể cần chuyển đổi rõ ràng bằng **$toDate** hoặc **$dateFromString** sau khi xác định định dạng và chính sách lỗi. Về lâu dài, nên lưu trường thời điểm thống nhất dưới dạng BSON Date và kiểm soát kiểu bằng schema validation.

### 1.3. Múi giờ có thể là tên IANA hoặc UTC offset

Trong các biểu thức ngày giờ hỗ trợ tham số timezone, MongoDB chấp nhận những định danh múi giờ phù hợp, ví dụ:

~~~javascript
timezone: "Asia/Ho_Chi_Minh"
timezone: "America/New_York"
timezone: "UTC"
timezone: "+07:00"
~~~

Tên IANA như **America/New_York** giúp áp dụng quy tắc DST theo ngày được xét. Một offset cố định như **"-05:00"** không tự biết mùa hè tại New York có thể dùng UTC−04:00.

**Không nên lưu/nhập giờ địa phương không kèm múi giờ rồi mặc định MongoDB biết nó thuộc thành phố nào.** Nếu một ngày có giờ bị bỏ qua hoặc giờ xuất hiện hai lần khi đổi DST, ứng dụng cần quy định rõ cách diễn giải thời điểm địa phương.

### 1.4. Giờ Việt Nam và UTC

Với **Asia/Ho_Chi_Minh**, thời gian địa phương hiện tương ứng UTC+07:00 và không áp dụng DST. Ví dụ:

~~~text
UTC:                 2026-11-14 17:00:00Z
Asia/Ho_Chi_Minh:    2026-11-15 00:00:00+07:00
~~~

Vì vậy, “đầu ngày 15/11 theo giờ Việt Nam” là **17:00 UTC của ngày 14/11**. Nếu sử dụng ranh giới UTC 00:00 để tổng hợp một ngày tại Việt Nam, số liệu có thể đưa một số sự kiện sang ngày sai.

## 2. Chuẩn bị bộ dữ liệu thực hành

Chọn database riêng:

~~~javascript
use aggregation_dates_lab
~~~

Giả sử collection **events** chưa có document. Tạo dữ liệu với thời điểm UTC, trạng thái và số tiền để làm báo cáo:

~~~javascript
db.events.insertMany([
  {
    _id: "E01",
    type: "ORDER",
    amount: NumberDecimal("100.00"),
    occurredAt: ISODate("2026-11-13T16:30:00Z")
  },
  {
    _id: "E02",
    type: "ORDER",
    amount: NumberDecimal("200.00"),
    occurredAt: ISODate("2026-11-13T17:30:00Z")
  },
  {
    _id: "E03",
    type: "LOGIN",
    amount: NumberDecimal("0.00"),
    occurredAt: ISODate("2026-11-14T01:00:00Z")
  },
  {
    _id: "E04",
    type: "ORDER",
    amount: NumberDecimal("75.00"),
    occurredAt: ISODate("2026-11-14T16:59:59Z")
  },
  {
    _id: "E05",
    type: "ORDER",
    amount: NumberDecimal("50.00"),
    occurredAt: ISODate("2026-11-14T17:00:00Z")
  },
  {
    _id: "E06",
    type: "ORDER",
    amount: NumberDecimal("40.00"),
    occurredAt: ISODate("2026-11-15T03:15:00Z")
  },
  {
    _id: "E07",
    type: "LOGIN",
    amount: NumberDecimal("0.00"),
    occurredAt: ISODate("2026-11-15T16:00:00Z")
  },
  {
    _id: "E08",
    type: "ORDER",
    amount: NumberDecimal("90.00"),
    occurredAt: ISODate("2026-11-15T17:00:00Z")
  }
])
~~~

Những giá trị UTC này cố ý đặt gần **17:00Z**, tức thời điểm bắt đầu ngày mới ở Việt Nam.

| ID | Thời điểm UTC | Ngày địa phương Asia/Ho_Chi_Minh | Type | Amount |
|---|---|---|---|---:|
| E01 | 13/11 16:30 | 13/11 | ORDER | 100 |
| E02 | 13/11 17:30 | 14/11 | ORDER | 200 |
| E03 | 14/11 01:00 | 14/11 | LOGIN | 0 |
| E04 | 14/11 16:59:59 | 14/11 | ORDER | 75 |
| E05 | 14/11 17:00 | 15/11 | ORDER | 50 |
| E06 | 15/11 03:15 | 15/11 | ORDER | 40 |
| E07 | 15/11 16:00 | 15/11 | LOGIN | 0 |
| E08 | 15/11 17:00 | 16/11 | ORDER | 90 |

Xem dữ liệu theo thứ tự thời gian:

~~~javascript
db.events.find().sort({ occurredAt: 1 });
~~~

**Lưu ý:** các ví dụ này giả định collection chưa có dữ liệu và chạy insertMany một lần. Chạy lại sẽ gặp lỗi trùng _id. Những con số và ID dự kiến bên dưới dựa trên chính bộ dữ liệu vừa tạo, không dựa vào thứ tự mặc định của find().

## 3. Các biểu thức ngày giờ nằm ở đâu trong aggregation?

Cả ba toán tử đều là **aggregation expressions**, thường xuất hiện trong những stage như **$project**, **$set/$addFields**, **$group** và **$match kết hợp $expr**.

Ví dụ:

~~~javascript
db.events.aggregate([
  {
    $project: {
      _id: 1,
      occurredAt: 1,
      localDay: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

Trong aggregation:

- **"$occurredAt"** là một biểu thức tham chiếu trường occurredAt của document.
- **unit: "day"** là giá trị chuỗi chỉ đơn vị tính.
- **timezone** quy định lịch địa phương khi tính toán.
- Biểu thức **$dateTrunc** trả về **BSON Date**, không phải chuỗi “2026-11-14”.

Đừng nhầm cú pháp này với toán tử query trên field:

~~~javascript
// Đây là cú pháp không diễn tả phép so sánh ngày đơn giản.
// $dateTrunc thuộc ngữ cảnh biểu thức aggregation.
{ occurredAt: { $dateTrunc: { unit: "day" } } }
~~~

Nếu muốn filter dựa trên một phép tính, dùng **$expr** hoặc tính trường trước bằng một stage rồi **$match** ở stage sau. Nếu lọc được bằng khoảng BSON Date trực tiếp, cách đó thường thuận lợi hơn cho index.

## 4. $dateTrunc: đưa thời điểm về đầu khoảng

**$dateTrunc** xác định **đầu khoảng thời gian** chứa một thời điểm dựa trên đơn vị như ngày, tuần, tháng, giờ hoặc phút. Có thể hiểu là làm tròn **xuống ranh giới lịch** phù hợp, không phải làm tròn đến mốc gần nhất.

Cú pháp:

~~~javascript
{
  $dateTrunc: {
    date: <dateExpression>,
    unit: <timeUnit>,
    binSize: <positiveInteger>,    // tùy chọn, mặc định 1
    timezone: <timezone>,          // tùy chọn, mặc định UTC
    startOfWeek: <dayOfWeek>       // chỉ có tác dụng với unit: "week"
  }
}
~~~

Các giá trị đơn vị thường dùng gồm **"year"**, **"quarter"**, **"month"**, **"week"**, **"day"**, **"hour"**, **"minute"**, **"second"**, **"millisecond"**. Đơn vị **unit** cho biết cấp lịch muốn làm tròn về đầu; **binSize** cho phép gom thành các khối nhiều đơn vị như 15 phút hoặc 2 tháng.

### 4.1. So sánh với việc cắt chuỗi ngày

Không nên nghĩ $dateTrunc chỉ đơn giản là cắt chuỗi ISO:

~~~text
Thời điểm UTC:                 2026-11-13 17:30Z
Theo giờ Việt Nam:             2026-11-14 00:30+07
Đầu ngày theo giờ Việt Nam:    2026-11-14 00:00+07
Giá trị Date kết quả theo UTC: 2026-11-13 17:00Z
~~~

$dateTrunc trả về **Date tương ứng với ranh giới địa phương được quy đổi về UTC**. Nếu xem trực tiếp output bằng ISODate, giờ có thể trông như “17:00 của ngày trước”; đây là kết quả chính xác.

### 4.2. Ví dụ $dateTrunc theo UTC

~~~javascript
db.events.aggregate([
  {
    $project: {
      _id: 1,
      occurredAt: 1,
      utcDay: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day"
        }
      }
    }
  },
  { $sort: { occurredAt: 1 } }
])
~~~

Với E02 có occurredAt = **2026-11-13T17:30:00Z**, utcDay là **2026-11-13T00:00:00Z**. Đây là đầu ngày UTC, không phải đầu ngày theo múi giờ Việt Nam.

### 4.3. Ví dụ $dateTrunc theo Asia/Ho_Chi_Minh

~~~javascript
db.events.aggregate([
  {
    $project: {
      _id: 1,
      occurredAt: 1,
      vietnamDay: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  { $sort: { occurredAt: 1 } }
])
~~~

Một số giá trị:

| Document | occurredAt UTC | vietnamDay UTC | Ngày địa phương tương ứng |
|---|---|---|---|
| E01 | 13/11 16:30Z | 12/11 17:00Z | 13/11 lúc 00:00 |
| E02 | 13/11 17:30Z | 13/11 17:00Z | 14/11 lúc 00:00 |
| E04 | 14/11 16:59:59Z | 13/11 17:00Z | 14/11 lúc 00:00 |
| E05 | 14/11 17:00Z | 14/11 17:00Z | 15/11 lúc 00:00 |
| E08 | 15/11 17:00Z | 15/11 17:00Z | 16/11 lúc 00:00 |

Sự khác biệt giữa E04 và E05 rất đáng chú ý: chỉ cách nhau **một giây**, nhưng nằm ở **hai ngày địa phương khác nhau**.

### 4.4. Gom theo đầu giờ

~~~javascript
db.events.aggregate([
  {
    $project: {
      _id: 1,
      localHourStart: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "hour",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

Với E02 là 00:30 ngày 14/11 theo giờ Việt Nam, kết quả biểu diễn **00:00 địa phương** tương ứng UTC **2026-11-13T17:00:00Z**.

### 4.5. Dùng binSize để chia bucket 15 phút

~~~javascript
db.events.aggregate([
  {
    $project: {
      _id: 1,
      quarterHour: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "minute",
          binSize: 15,
          timezone: "UTC"
        }
      }
    }
  }
])
~~~

Một phép tính riêng:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      example: {
        $dateTrunc: {
          date: ISODate("2026-11-14T01:37:40Z"),
          unit: "minute",
          binSize: 15
        }
      }
    }
  }
])
~~~

Giá trị example là **2026-11-14T01:30:00Z**. Những thời điểm từ 01:30:00 đến trước 01:45:00 thuộc cùng bucket 15 phút.

**binSize là số lượng đơn vị trong một bucket**, không phải số lượng document mỗi nhóm. Kết hợp binSize với unit: "hour" để chia thành khối 2 giờ, unit: "month" để chia theo hai tháng, v.v.

### 4.6. startOfWeek khi unit là week

Một báo cáo tuần cần xác định **tuần bắt đầu thứ mấy**. Với $dateTrunc:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "week",
    timezone: "Asia/Ho_Chi_Minh",
    startOfWeek: "monday"
  }
}
~~~

Nếu không khai báo startOfWeek, MongoDB sử dụng **Sunday (chủ nhật)** làm đầu tuần cho $dateTrunc. Không nên mặc định kết quả là tuần ISO (bắt đầu thứ hai) trong mọi câu truy vấn.

Ví dụ với **2026-11-14T12:00:00Z** (thứ bảy):

| startOfWeek | Đầu tuần UTC nếu timezone = UTC |
|---|---|
| "sunday" | 2026-11-08T00:00:00Z |
| "monday" | 2026-11-09T00:00:00Z |

Khi dùng timezone **Asia/Ho_Chi_Minh**, hai mốc đầu tuần địa phương tương ứng với **17:00Z của ngày trước**. Tùy cách định nghĩa kỳ báo cáo, có thể phải kết hợp ISO week-year hoặc một quy tắc tuần riêng; $dateTrunc không tự bảo đảm tất cả quy định về “tuần tài chính”.

### 4.7. Lưu ý với binSize lớn hơn 1

Với binSize: 2 và unit: "month", các bucket không có nghĩa là lấy tháng hiện tại rồi luôn làm tròn về tháng trước nó theo một mốc ngẫu nhiên. MongoDB xác định các bucket dựa trên **mốc tham chiếu chuẩn của toán tử** (với các đơn vị thông thường gắn với thời điểm đầu năm 2000 và quy tắc riêng cho tuần). Vì vậy, khi tạo khối hai tháng hoặc nhiều tuần, cần hiểu lịch phân chia theo reference point, không chỉ nhìn một tháng lẻ.

Nếu doanh nghiệp dùng chu kỳ kế toán bắt đầu từ ngày 5 hoặc kỳ 4-4-5, $dateTrunc với các đơn vị lịch chuẩn có thể không đủ để biểu diễn trọn vẹn; khi đó cần thiết kế bảng lịch hoặc phép biến đổi bổ sung.

### 4.8. Null, field thiếu và dữ liệu sai kiểu

Trong nhiều biểu thức ngày giờ, đối số date null/không có hoặc đối số tùy chọn null/không có có thể làm kết quả là null theo quy tắc operator. Giá trị không phải ngày hợp lệ có thể phát sinh lỗi.

Đừng kỳ vọng đoạn sau tự hiểu String như Date:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "day"
  }
}
~~~

nếu occurredAt đang lưu dưới dạng String **"2026-11-14"**. Cần thống nhất schema hoặc chuyển đổi có kiểm soát. Khi đang xử lý dữ liệu import, nên phân loại record sai kiểu, ghi nhận lỗi và quyết định có bỏ qua hay chuyển đổi trước khi gom nhóm.

## 5. Dùng $dateTrunc để thống kê theo ngày địa phương

Yêu cầu: **đếm số sự kiện và cộng amount theo từng ngày Việt Nam**. Có thể đặt biểu thức $dateTrunc trực tiếp làm khóa $group:

~~~javascript
db.events.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      eventCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Kết quả logic theo ngày địa phương:

| Ngày VN | _id Date theo UTC | eventCount | totalAmount |
|---|---|---:|---:|
| 13/11/2026 | 12/11 17:00Z | 1 | 100.00 |
| 14/11/2026 | 13/11 17:00Z | 3 | 275.00 |
| 15/11/2026 | 14/11 17:00Z | 3 | 90.00 |
| 16/11/2026 | 15/11 17:00Z | 1 | 90.00 |

Tổng amount ngày 14/11 là 200 + 0 + 75 = **275**. Nếu chỉ muốn doanh thu ORDER, cần lọc type trước khi $group:

~~~javascript
db.events.aggregate([
  { $match: { type: "ORDER" } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      revenue: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Kết quả ORDER: ngày 13/11 có **1 đơn, 100.00**; 14/11 có **2 đơn, 275.00**; 15/11 có **2 đơn, 90.00**; 16/11 có **1 đơn, 90.00**.

### 5.1. Hiển thị nhãn ngày với $dateToString

Vì _id của nhóm là BSON Date theo UTC, phần hiển thị có thể trông như ngày hôm trước. Để xuất nhãn **YYYY-MM-DD** theo múi giờ Việt Nam:

~~~javascript
db.events.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      dayStartUtc: "$_id",
      dayLabel: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$_id",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: 1
    }
  },
  { $sort: { dayStartUtc: 1 } }
])
~~~

Ở output, **dayStartUtc** vẫn là BSON Date có ý nghĩa chuẩn; **dayLabel** là String dùng để hiển thị. Khi cần so sánh khoảng hoặc phân trang theo thời điểm, nên giữ Date thay vì chỉ còn chuỗi.

### 5.2. $dateTrunc không tự điền ngày không có sự kiện

Ví dụ collection không có sự kiện ngày 17/11, $group sẽ **không tạo một hàng tự động cho ngày đó**. Nếu biểu đồ cần hiển thị cả những ngày có count = 0, phải bổ sung cơ chế tạo trục ngày, chẳng hạn một bảng lịch ở ứng dụng hoặc những stage aggregation phù hợp với phiên bản MongoDB.

Không nên hiểu việc thiếu bucket là bằng chứng ứng dụng đã lưu một document có tổng 0; đó là hai trạng thái khác nhau.

## 6. $dateAdd: cộng hoặc trừ đơn vị thời gian

**$dateAdd** nhận một thời điểm và cộng vào đó **amount** đơn vị thời gian. Cú pháp:

~~~javascript
{
  $dateAdd: {
    startDate: <dateExpression>,
    unit: <timeUnit>,
    amount: <integerExpression>,
    timezone: <timezone>  // tùy chọn, mặc định UTC
  }
}
~~~

Các đơn vị thường dùng gồm **year, quarter, week, day, hour, minute, second, millisecond**. Giá trị amount là **số nguyên**: dương để đi tới tương lai và âm để lùi về quá khứ.

### 6.1. Cộng bảy ngày

~~~javascript
db.events.aggregate([
  { $match: { _id: "E02" } },
  {
    $project: {
      _id: 1,
      occurredAt: 1,
      afterSevenDays: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "day",
          amount: 7,
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

E02 = **2026-11-13T17:30:00Z**, tương ứng 00:30 ngày 14/11 tại Việt Nam. Sau bảy ngày địa phương là 00:30 ngày 21/11, tương ứng **2026-11-20T17:30:00Z**.

### 6.2. Cộng 90 phút

~~~javascript
db.events.aggregate([
  { $match: { _id: "E02" } },
  {
    $project: {
      _id: 1,
      plusNinetyMinutes: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "minute",
          amount: 90
        }
      }
    }
  }
])
~~~

Kết quả: **2026-11-13T19:00:00Z**. Với các khoảng thời gian ở cấp phút/giây, ta thường nghĩ đến khoảng thời gian thực đã trôi qua; với ngày/tháng/năm và múi giờ có DST, phải xét quy tắc lịch.

### 6.3. Amount âm tương ứng phép trừ

~~~javascript
db.events.aggregate([
  { $match: { _id: "E02" } },
  {
    $project: {
      _id: 1,
      threeDaysEarlier: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "day",
          amount: -3,
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

E02 trừ ba ngày địa phương trả về **2026-11-10T17:30:00Z**.

MongoDB cũng có biểu thức **$dateSubtract** cho phép viết phép trừ một cách tường minh. Bài này tập trung vào $dateAdd; amount âm thường thuận tiện khi công thức cần tham số có dấu.

### 6.4. Cộng một tháng không tương đương cộng 30 ngày

Tháng có thể có 28, 29, 30 hoặc 31 ngày. MongoDB dùng quy tắc lịch cho các đơn vị tháng/quý/năm và xử lý tình huống ngày đích không tồn tại bằng cách chọn ngày hợp lệ cuối cùng của tháng đích.

Ví dụ năm nhuận:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      oneMonthAfterJan31: {
        $dateAdd: {
          startDate: ISODate("2024-01-31T12:00:00Z"),
          unit: "month",
          amount: 1
        }
      },
      thirtyDaysAfterJan31: {
        $dateAdd: {
          startDate: ISODate("2024-01-31T12:00:00Z"),
          unit: "day",
          amount: 30
        }
      }
    }
  }
])
~~~

Kết quả:

| Biểu thức | Thời điểm UTC |
|---|---|
| Cộng 1 month | 2024-02-29T12:00:00Z |
| Cộng 30 day | 2024-03-01T12:00:00Z |

Nếu bắt đầu từ **2025-01-31T12:00:00Z** rồi cộng một tháng, kết quả rơi vào **2025-02-28T12:00:00Z** vì năm 2025 không phải năm nhuận.

Đây là lý do một yêu cầu như “gia hạn gói thuê một tháng” không nên được tự động hiện thực thành cộng 30 × 24 giờ. Hãy xác định quy tắc nghiệp vụ khi ngày gốc là 29, 30 hoặc 31, đặc biệt khi cần gia hạn liên tiếp.

### 6.5. Cộng nhiều tháng liên tiếp có thể khác cộng một lần

Từ ngày **31/01/2025**, cộng một tháng cho ra **28/02/2025**; cộng thêm một tháng từ ngày 28/02 có thể cho **28/03/2025**. Nhưng cộng trực tiếp hai tháng vào ngày 31/01 có thể cho **31/03/2025**.

Điều này không phải sai số của MongoDB mà là hệ quả của quy tắc lịch và việc **điều chỉnh về cuối tháng ở bước trung gian**. Với hợp đồng và chu kỳ thanh toán, nên định nghĩa rõ:

- Hạn tiếp theo được tính từ **hạn hiện tại** hay từ **ngày gốc + N tháng**?
- Có cần giữ quy tắc “ngày cuối cùng của tháng” hay không?
- Nếu ngày kỷ niệm không tồn tại trong tháng đích, xử lý thế nào?

Không nên để cách gọi $dateAdd ngẫu nhiên quyết định những quy tắc nghiệp vụ quan trọng.

### 6.6. Leap year và ngày 29/02

Ví dụ:

~~~javascript
{
  $dateAdd: {
    startDate: ISODate("2024-02-29T09:00:00Z"),
    unit: "year",
    amount: 1
  }
}
~~~

Ngày 29/02/2025 không tồn tại, nên phép tính lịch được điều chỉnh về **2025-02-28T09:00:00Z**. Muốn quy tắc khác cho “sinh nhật ngày 29/02” hoặc “gia hạn thuê hàng năm”, phải quy định riêng ở tầng nghiệp vụ.

## 7. $dateAdd và giờ mùa hè (DST)

Các múi giờ như **America/New_York** có thời điểm chuyển sang giờ mùa hè, khiến một ngày địa phương có thể chỉ dài **23 giờ** hoặc dài **25 giờ**. Vì thế phải phân biệt:

- **Cộng một ngày theo lịch địa phương**: giữ ý nghĩa “cùng giờ đồng hồ trong ngày kế tiếp” khi có thể.
- **Cộng 24 giờ thời gian thực**: tiến thêm đúng 24 giờ trên trục UTC.

Ví dụ New York chuyển sang DST ngày **10/03/2024**. Trước khi chuyển, 12 giờ trưa ngày 09/03 ở EST (UTC−05:00) là **2024-03-09T17:00:00Z**. Sau khi chuyển, 12 giờ trưa ngày 10/03 ở EDT (UTC−04:00) là **2024-03-10T16:00:00Z**.

### 7.1. Cộng 1 day và 24 hour cho kết quả khác nhau

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      calendarNextDay: {
        $dateAdd: {
          startDate: ISODate("2024-03-09T17:00:00Z"),
          unit: "day",
          amount: 1,
          timezone: "America/New_York"
        }
      },
      after24Hours: {
        $dateAdd: {
          startDate: ISODate("2024-03-09T17:00:00Z"),
          unit: "hour",
          amount: 24,
          timezone: "America/New_York"
        }
      }
    }
  }
])
~~~

Ý nghĩa:

| Phép cộng | Kết quả UTC | Giờ tại New York |
|---|---|---|
| 1 day theo lịch NY | 2024-03-10T16:00:00Z | 10/03 lúc 12:00 EDT |
| 24 hour | 2024-03-10T17:00:00Z | 10/03 lúc 13:00 EDT |

Khoảng UTC giữa 12 giờ trưa hai ngày này chỉ có **23 giờ**. Với các đơn vị **day hoặc lớn hơn**, cách tính có timezone gắn với lịch địa phương và quy tắc DST; với giờ nhỏ hơn, cần hiểu theo các đơn vị thời gian tương ứng. Đây là khác biệt nghiệp vụ rất quan trọng.

### 7.2. Khi nào cần “24 giờ thực”, khi nào cần “ngày mai cùng giờ”?

| Yêu cầu | Hướng tính phù hợp |
|---|---|
| Token chỉ có hiệu lực đúng 24 giờ | Dựa vào khoảng thời gian tuyệt đối, ví dụ 24 hour trên UTC |
| Nhắc nhở vào 09:00 địa phương ngày mai | Tính theo lịch địa phương với timezone |
| Hạn trả phòng lúc 12:00 ngày tiếp theo | Lịch tại địa điểm lưu trú, không mặc định 24 giờ |
| Báo cáo doanh thu mỗi ngày theo thành phố | $dateTrunc với timezone thành phố |
| Cảnh báo sau đúng 15 phút | Cộng 15 minute từ thời điểm hiện tại |
| Kỳ thuê một tháng | Đơn vị month với quy tắc xử lý cuối tháng được thống nhất |

Nếu ứng dụng chỉ lưu offset cố định "-05:00" cho New York, phép tính ngày 10/03 có thể không phản ánh thay đổi sang UTC−04:00. Hãy ưu tiên tên vùng IANA nếu nghiệp vụ cần quy tắc múi giờ theo lịch.

### 7.3. Múi giờ cũng quan trọng khi trừ ngày

Nếu muốn thời điểm tương ứng “cùng giờ hôm qua”, dùng $dateAdd với **unit: "day", amount: -1** và múi giờ nghiệp vụ. Nếu muốn một khoảng cách chính xác 24 giờ trước, dùng đơn vị hour với amount -24 hoặc phép tính trên thời điểm UTC theo yêu cầu.

Không nên dùng những phép cộng/trừ ngày một cách mơ hồ trong ứng dụng liên quan đến đặt phòng, hóa đơn, lịch hẹn hoặc thời hạn bảo mật.

## 8. $dateDiff: đếm ranh giới đơn vị giữa hai mốc

**$dateDiff** nhận **startDate**, **endDate**, **unit** và có thể nhận **timezone** cùng **startOfWeek**:

~~~javascript
{
  $dateDiff: {
    startDate: <dateExpression>,
    endDate: <dateExpression>,
    unit: <timeUnit>,
    timezone: <timezone>,        // tùy chọn, mặc định UTC
    startOfWeek: <dayOfWeek>    // sử dụng khi unit: "week"
  }
}
~~~

Các đơn vị thời gian gồm những đơn vị như **year, quarter, month, week, day, hour, minute, second, millisecond**. Kết quả là **số nguyên có dấu** theo chiều từ startDate đến endDate.

Điểm quan trọng nhất: **$dateDiff đo số ranh giới của đơn vị thời gian đã đi qua**, không nhất thiết đo số khoảng thời gian trọn vẹn đã trôi qua theo nghĩa toán học.

### 8.1. Ví dụ hai phút nhưng khác ngày

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      daysAcrossMidnight: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T23:59:00Z"),
          endDate: ISODate("2026-11-15T00:01:00Z"),
          unit: "day",
          timezone: "UTC"
        }
      },
      minutesElapsed: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T23:59:00Z"),
          endDate: ISODate("2026-11-15T00:01:00Z"),
          unit: "minute",
          timezone: "UTC"
        }
      }
    }
  }
])
~~~

Kết quả:

| Biểu thức | Giá trị | Lý do |
|---|---:|---|
| dateDiff unit day | 1 | Vượt qua ranh giới ngày 15/11 lúc 00:00 UTC |
| dateDiff unit minute | 2 | Vượt qua hai ranh giới phút |

Không nên lấy kết quả **1 day** rồi khẳng định có đúng 24 giờ trôi qua. Thời gian thực giữa hai mốc chỉ là **2 phút**.

### 8.2. Thậm chí một giây cũng có thể khác ngày

Hai document của bộ dữ liệu mẫu:

~~~text
E04: 2026-11-14T16:59:59Z
E05: 2026-11-14T17:00:00Z
~~~

Theo UTC+07, đây là:

~~~text
E04: 14/11/2026 23:59:59
E05: 15/11/2026 00:00:00
~~~

Tính:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      localDayDifference: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T16:59:59Z"),
          endDate: ISODate("2026-11-14T17:00:00Z"),
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      utcDayDifference: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T16:59:59Z"),
          endDate: ISODate("2026-11-14T17:00:00Z"),
          unit: "day",
          timezone: "UTC"
        }
      }
    }
  }
])
~~~

Kết quả **localDayDifference = 1**, còn **utcDayDifference = 0**. Thời gian thực trôi qua trong cả hai cách là **1 giây**, nhưng ranh giới ngày phụ thuộc timezone.

### 8.3. dateDiff theo tháng và năm

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      monthBoundary: {
        $dateDiff: {
          startDate: ISODate("2025-01-31T23:59:00Z"),
          endDate: ISODate("2025-02-01T00:01:00Z"),
          unit: "month"
        }
      },
      yearBoundary: {
        $dateDiff: {
          startDate: ISODate("2025-12-31T23:59:00Z"),
          endDate: ISODate("2026-01-01T00:01:00Z"),
          unit: "year"
        }
      }
    }
  }
])
~~~

Hai kết quả đều bằng **1** vì mỗi khoảng vượt một ranh giới của đơn vị tương ứng. Dù mỗi khoảng chỉ kéo dài hai phút, chúng đã đi sang tháng hoặc năm mới.

Vì thế, **$dateDiff unit: "year" không phải phép tính tuổi chính xác cho mọi ngày sinh** nếu ứng dụng cần số lần sinh nhật đã diễn ra. Nó đếm ranh giới năm, không tự kiểm tra ngày sinh trong năm hiện tại.

### 8.4. startDate sau endDate: kết quả âm

~~~javascript
{
  $dateDiff: {
    startDate: ISODate("2026-11-15T00:00:00Z"),
    endDate: ISODate("2026-11-12T00:00:00Z"),
    unit: "day",
    timezone: "UTC"
  }
}
~~~

Kết quả **-3**. Dấu âm cho biết endDate nằm trước startDate theo thứ tự thời gian.

Nếu nghiệp vụ muốn khoảng cách không âm, cần xác định dùng trị tuyệt đối hay hoán đổi hai mốc. Đừng tự âm thầm đổi thứ tự nếu dấu âm mang ý nghĩa như “đã quá hạn” hoặc “còn bao nhiêu ngày”.

### 8.5. dateDiff theo tuần và startOfWeek

Xét thời điểm thứ bảy **14/11/2026 12:00Z** đến chủ nhật **15/11/2026 12:00Z**:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      sundayWeek: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T12:00:00Z"),
          endDate: ISODate("2026-11-15T12:00:00Z"),
          unit: "week",
          timezone: "UTC",
          startOfWeek: "sunday"
        }
      },
      mondayWeek: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T12:00:00Z"),
          endDate: ISODate("2026-11-15T12:00:00Z"),
          unit: "week",
          timezone: "UTC",
          startOfWeek: "monday"
        }
      }
    }
  }
])
~~~

Kết quả: **sundayWeek = 1** vì đi qua mốc đầu tuần chủ nhật; **mondayWeek = 0** vì chưa đi qua đầu tuần thứ hai.

Nếu không cung cấp startOfWeek khi unit là week, MongoDB dùng Sunday. Hãy thiết lập tường minh khi hệ thống định nghĩa tuần bắt đầu vào thứ hai hoặc một ngày khác.

### 8.6. dateDiff không có kết quả phân số

~~~javascript
{
  $dateDiff: {
    startDate: ISODate("2026-11-14T00:00:00Z"),
    endDate: ISODate("2026-11-14T12:30:00Z"),
    unit: "day",
    timezone: "UTC"
  }
}
~~~

Kết quả là **0**, không phải 0,5208 ngày. Chưa có ranh giới ngày UTC nào bị vượt qua. Khi cần giá trị thời lượng có phần thập phân, hãy tính từ **mili giây tuyệt đối** rồi chia cho mẫu số phù hợp với yêu cầu.

## 9. dateDiff theo lịch và thời lượng thực tế là hai câu hỏi khác nhau

Để tránh sai, cần xác định câu hỏi nghiệp vụ đang nói tới **ranh giới lịch** hay **thời lượng đã trôi qua**.

| Câu hỏi | Cách nghĩ đúng | Ví dụ |
|---|---|---|
| Hai thời điểm thuộc hai ngày khác nhau không? | Ranh giới ngày theo timezone | $dateDiff unit day |
| Đã trôi qua đúng bao nhiêu phút? | Khoảng mili giây giữa hai thời điểm | $subtract hai Date và chia 60.000 |
| Cuộc họp diễn ra bao nhiêu giờ thực? | Số mili giây thực trôi qua | $subtract và chia 3.600.000 |
| Đã vượt qua bao nhiêu mốc tháng? | Ranh giới tháng | $dateDiff unit month |
| Gia hạn đến cùng giờ vào ngày kế tiếp? | Phép cộng lịch địa phương | $dateAdd unit day |
| Token có hiệu lực chính xác 24 giờ? | Phép cộng khoảng thời gian thực | $dateAdd 24 hour hoặc tính theo UTC |

### 9.1. Trừ hai BSON Date để lấy mili giây

MongoDB cho phép trừ hai giá trị Date trong aggregation:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      elapsedMs: {
        $subtract: [
          ISODate("2026-11-14T23:59:00Z"),
          ISODate("2026-11-14T23:58:30Z")
        ]
      },
      elapsedSeconds: {
        $divide: [
          {
            $subtract: [
              ISODate("2026-11-14T23:59:00Z"),
              ISODate("2026-11-14T23:58:30Z")
            ]
          },
          1000
        ]
      }
    }
  }
])
~~~

Kết quả là **elapsedMs = 30000**, **elapsedSeconds = 30**.

Với khoảng thời gian thực theo giờ:

~~~javascript
{
  $divide: [
    { $subtract: ["$endedAt", "$startedAt"] },
    3600000
  ]
}
~~~

Biểu thức này trả về số giờ có thể có phần thập phân. Hai field phải là BSON Date hợp lệ, và cần quyết định cách xử lý null/missing trước khi tính.

### 9.2. $dateDiff theo hour có thể khác giờ thực đã trôi qua

Ví dụ đi từ **12:59:59Z** đến **13:00:01Z**:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      hourBoundaries: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T12:59:59Z"),
          endDate: ISODate("2026-11-14T13:00:01Z"),
          unit: "hour"
        }
      },
      actualHours: {
        $divide: [
          {
            $subtract: [
              ISODate("2026-11-14T13:00:01Z"),
              ISODate("2026-11-14T12:59:59Z")
            ]
          },
          3600000
        ]
      }
    }
  }
])
~~~

**hourBoundaries = 1**, vì một ranh giới giờ đã bị vượt qua; **actualHours** xấp xỉ **0,00000056**, vì thực tế chỉ có hai giây.

Do đó, để đo thời gian xử lý request, thời gian chạy job hoặc SLA tính bằng số giờ thực, thông thường cần phép tính dựa trên duration chứ không lấy $dateDiff unit hour làm số giờ phân số.

### 9.3. dateDiff và DST

Xét hai mốc 12 giờ trưa tại New York ở hai ngày liên tiếp khi bắt đầu DST năm 2024:

~~~javascript
db.events.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      calendarDays: {
        $dateDiff: {
          startDate: ISODate("2024-03-09T17:00:00Z"),
          endDate: ISODate("2024-03-10T16:00:00Z"),
          unit: "day",
          timezone: "America/New_York"
        }
      },
      elapsedHours: {
        $divide: [
          {
            $subtract: [
              ISODate("2024-03-10T16:00:00Z"),
              ISODate("2024-03-09T17:00:00Z")
            ]
          },
          3600000
        ]
      }
    }
  }
])
~~~

Kết quả: **calendarDays = 1** theo lịch New York, nhưng **elapsedHours = 23**. Đây là ví dụ rõ ràng cho việc một ngày lịch không nhất thiết chứa 24 giờ thực khi múi giờ áp dụng DST.

### 9.4. Tính tuổi: cần xác định sinh nhật đã qua chưa

Nếu chỉ viết:

~~~javascript
{
  $dateDiff: {
    startDate: "$birthDate",
    endDate: "$asOfDate",
    unit: "year",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

thì kết quả đếm **ranh giới đầu năm dương lịch**, không phải số sinh nhật đã diễn ra. Một người sinh vào tháng 12 có thể chưa đến sinh nhật nhưng dateDiff đã tăng khi bước sang 01/01.

Muốn tính tuổi theo ngày sinh, cần định nghĩa:

1. Độ chênh lệch năm giữa hai ngày.
2. Trong năm hiện tại, sinh nhật đã đến hay chưa.
3. Cách xử lý ngày 29/02 ở năm không nhuận.
4. Múi giờ dùng để xác định “hôm nay”.

Không nên dùng **$dateDiff unit year** làm công thức tuổi pháp lý hay tuổi nghiệp vụ nếu chưa thực hiện các bước điều chỉnh phù hợp.

## 10. Kết hợp $dateTrunc, $dateAdd và $dateDiff trong một pipeline

Giả sử mỗi sự kiện cần các trường dẫn xuất:

- **localDayStart**: đầu ngày theo giờ Việt Nam.
- **nextLocalDayStart**: đầu ngày địa phương tiếp theo.
- **daysSinceEvent**: số ranh giới ngày địa phương từ lúc xảy ra tới một mốc báo cáo cố định.
- **expiresAt**: thời điểm sự kiện hết hiệu lực sau bảy ngày lịch.

Có thể viết:

~~~javascript
db.events.aggregate([
  {
    $set: {
      localDayStart: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  {
    $set: {
      nextLocalDayStart: {
        $dateAdd: {
          startDate: "$localDayStart",
          unit: "day",
          amount: 1,
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      expiresAt: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "day",
          amount: 7,
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      daysSinceEvent: {
        $dateDiff: {
          startDate: "$occurredAt",
          endDate: ISODate("2026-11-17T00:00:00Z"),
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      occurredAt: 1,
      localDayStart: 1,
      nextLocalDayStart: 1,
      expiresAt: 1,
      daysSinceEvent: 1
    }
  },
  { $sort: { occurredAt: 1 } }
])
~~~

Với document **E02**:

| Trường | Giá trị UTC |
|---|---|
| occurredAt | 2026-11-13T17:30:00Z |
| localDayStart | 2026-11-13T17:00:00Z |
| nextLocalDayStart | 2026-11-14T17:00:00Z |
| expiresAt | 2026-11-20T17:30:00Z |

Giá trị **daysSinceEvent** ở E02 được tính từ ngày địa phương 14/11 đến mốc 17/11 07:00 tại Việt Nam (tức 00:00Z), nên đi qua **3 ranh giới ngày địa phương**: 15/11, 16/11 và 17/11.

### 10.1. Vì sao tách pipeline thành hai stage $set?

Stage đầu tính **localDayStart**. Stage thứ hai dùng kết quả đó trong **nextLocalDayStart**. Việc tách thành hai stage giúp rõ ràng rằng biểu thức sau đọc **giá trị đã được tạo ở stage trước**.

Không nên giả định hai field mới trong **cùng một stage $set** có thể tham chiếu lẫn nhau theo thứ tự bạn khai báo. Mỗi stage có ngữ nghĩa đánh giá trên document đầu vào của stage đó.

### 10.2. Không nhất thiết phải lưu tất cả trường dẫn xuất vào collection

Trong pipeline đọc, $set chỉ thêm trường vào các document **đang đi qua pipeline**. Nó không tự ghi thay đổi trở lại collection. Nếu nhu cầu chỉ là báo cáo, giữ phép tính trong aggregation thường là hợp lý.

Nếu ứng dụng thường xuyên filter theo **expiresAt** hoặc **localDayStart**, có thể cân nhắc lưu trường dẫn xuất khi ghi và tạo index, nhưng phải thiết kế cách cập nhật nhất quán khi timezone/giá trị gốc thay đổi.

### 10.3. Tính theo timezone riêng của từng document

Trong ứng dụng đa quốc gia, mỗi đơn hàng có thể mang một trường timezone như:

~~~javascript
{
  _id: "BOOKING-1",
  occurredAt: ISODate("2026-11-14T18:30:00Z"),
  businessTimezone: "America/New_York"
}
~~~

Thay vì hard-code một timezone cho toàn bộ collection, biểu thức có thể đọc tên múi giờ từ field:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "day",
    timezone: "$businessTimezone"
  }
}
~~~

Nếu field timezone có thể null/missing hoặc không hợp lệ, cần có chiến lược validation, fallback hoặc phân loại lỗi. Ví dụ fallback an toàn về mặt cú pháp:

~~~javascript
timezone: {
  $ifNull: ["$businessTimezone", "UTC"]
}
~~~

Nhưng chọn UTC làm fallback có thể **sai nghiệp vụ** nếu bản ghi bắt buộc phải dùng timezone của địa điểm. Đừng mặc định fallback là quyết định đúng cho mọi ứng dụng.

Với báo cáo đa timezone, nên đưa timezone hoặc mã khu vực vào **khóa nhóm** khi cần phân biệt hai nhóm có cùng mốc UTC nhưng thuộc những lịch địa phương khác nhau.

## 11. Lọc dữ liệu theo ngày địa phương mà vẫn tận dụng index

Giả sử cần lấy **tất cả sự kiện ngày 14/11/2026 theo giờ Việt Nam**. Một cách tự nhiên là tính ngày bằng $dateTrunc trong $expr:

~~~javascript
db.events.find({
  $expr: {
    $eq: [
      {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      ISODate("2026-11-13T17:00:00Z")
    ]
  }
});
~~~

Điều kiện logic đúng cho ngày 14/11 tại Việt Nam, nhưng **phép tính trên field xảy ra trong biểu thức**, vì vậy không nên mặc định một index thường trên occurredAt có thể trực tiếp hỗ trợ nó như một range query.

Một cách thường tốt hơn cho filter cố định theo ngày địa phương là chuyển **đầu ngày** và **đầu ngày kế tiếp** sang UTC ở phía ứng dụng, rồi dùng khoảng **[start, end)** trên BSON Date:

~~~javascript
db.events.find({
  occurredAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
}).sort({ occurredAt: 1 });
~~~

Kết quả: **E02, E03 và E04**.

### 11.1. Vì sao dùng $lt ở biên trên?

Sự kiện E05 có occurredAt = **2026-11-14T17:00:00Z**, tức đúng **00:00 ngày 15/11** ở Việt Nam. Nếu viết $lte ở biên trên, E05 sẽ lọt vào báo cáo ngày 14/11, gây đếm trùng ở ranh giới.

Mẫu phổ biến:

~~~javascript
{
  occurredAt: {
    $gte: startOfLocalDayAsUtcDate,
    $lt: startOfNextLocalDayAsUtcDate
  }
}
~~~

Điều này cũng tránh phải tự chọn “mili giây cuối ngày” như 23:59:59.999.

### 11.2. Một ngày địa phương không nhất thiết dài 24 giờ

Nếu timezone là America/New_York, đầu ngày địa phương và đầu ngày tiếp theo có thể cách nhau **23 hoặc 25 giờ UTC** quanh DST. Vì thế, không nên xây biên trên bằng cách luôn cộng chính xác **86.400.000 mili giây** vào biên dưới nếu yêu cầu là “ngày lịch địa phương”.

Thay vào đó:

1. Xác định ngày và timezone nghiệp vụ.
2. Lấy **đầu ngày địa phương**.
3. Lấy **đầu ngày địa phương kế tiếp**, theo timezone đó.
4. Quy đổi cả hai mốc thành BSON Date/Instant UTC.
5. Query occurredAt với **$gte startUtc, $lt endUtc**.

Đây cũng là quy tắc hữu ích cho báo cáo theo tháng: dùng mốc đầu tháng và đầu tháng kế tiếp, không cộng 30 ngày cố định.

### 11.3. Tạo index cho filter thời gian

~~~javascript
db.events.createIndex(
  { occurredAt: 1 },
  { name: "idx_occurredAt" }
);
~~~

Truy vấn range:

~~~javascript
db.events.find({
  occurredAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
}).sort({ occurredAt: 1 });
~~~

có cấu trúc thuận lợi để MongoDB quét một đoạn index occurredAt. Nếu thường lọc type rồi lấy khoảng occurredAt:

~~~javascript
db.events.createIndex({
  type: 1,
  occurredAt: 1
});

db.events.find({
  type: "ORDER",
  occurredAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
}).sort({ occurredAt: 1 });
~~~

index ghép **{type:1, occurredAt:1}** có thể phù hợp hơn vì type là equality và occurredAt là range kiêm khóa sort.

**Có index không bảo đảm query planner luôn chọn nó**, đặc biệt với collection chỉ có tám document. Hãy đo trên dữ liệu đại diện và xem explain().

## 12. Những bài toán nghiệp vụ điển hình

### 12.1. Hạn thanh toán sau 48 giờ thực

Nếu hợp đồng ghi rõ “sau đúng 48 giờ kể từ khi tạo”, biểu thức:

~~~javascript
{
  $dateAdd: {
    startDate: "$createdAt",
    unit: "hour",
    amount: 48
  }
}
~~~

diễn đạt khoảng thời gian tuyệt đối. Múi giờ không cần thiết nếu chỉ quan tâm chính xác 48 giờ thực trôi qua.

### 12.2. Hạn thanh toán cuối ngày địa phương

Giả sử đơn được tạo ngày 14/11 theo giờ Việt Nam, hạn là **đầu ngày 15/11 địa phương** (tức kết thúc khoảng ngày 14/11, theo quy ước biên trên không bao gồm):

~~~javascript
{
  $dateAdd: {
    startDate: {
      $dateTrunc: {
        date: "$createdAt",
        unit: "day",
        timezone: "Asia/Ho_Chi_Minh"
      }
    },
    unit: "day",
    amount: 1,
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

Cách viết có nghĩa **đầu ngày kế tiếp**, khác với cộng 24 giờ vào createdAt. Nếu deadline thực tế là “23:59:59 ngày 14/11”, nên thận trọng với độ chính xác mili giây và ưu tiên biểu diễn thời hạn như một biên độc quyền.

### 12.3. Đơn thuê có thời hạn một tháng

~~~javascript
{
  $dateAdd: {
    startDate: "$rentalStart",
    unit: "month",
    amount: 1,
    timezone: "$locationTimezone"
  }
}
~~~

Hãy xác định chính sách xử lý cuối tháng và việc gia hạn từ ngày gốc hay ngày hết hạn trước đó. Với hợp đồng phức tạp, biểu thức chỉ là công cụ tính lịch; nó không thay thế định nghĩa pháp lý/nghiệp vụ của kỳ thuê.

### 12.4. Tính số ngày lịch từ khi tạo đơn đến khi thanh toán

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      calendarDaysToPay: {
        $dateDiff: {
          startDate: "$createdAt",
          endDate: "$paidAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

Nếu tạo lúc 23:59 và thanh toán lúc 00:01 hôm sau, kết quả ngày có thể là 1 mặc dù mới hai phút trôi qua. Nếu muốn đo **thời lượng xử lý**, dùng chênh lệch mili giây và đơn vị cần hiển thị.

### 12.5. Phát hiện đã quá hạn bằng so sánh Date

Nếu mỗi document đã có **expiresAt** là BSON Date, câu hỏi “đã hết hạn tại thời điểm này chưa?” thường viết trực tiếp:

~~~javascript
db.subscriptions.find({
  expiresAt: { $lt: new Date() }
});
~~~

Đây là kiểm tra **thời điểm tuyệt đối** và có thể tận dụng index trên expiresAt. Không nên thay bằng:

~~~javascript
{
  $dateDiff: {
    startDate: "$expiresAt",
    endDate: "$$NOW",
    unit: "day"
  }
}
~~~

rồi mặc định giá trị ngày lớn hơn 0 mới là đã hết hạn: một record có thể quá hạn nhiều giờ nhưng chưa vượt qua ranh giới ngày.

Khi cần thời điểm hết hạn được tính từ startDate theo quy tắc nghiệp vụ, có thể tính expiresAt lúc ghi để truy vấn nhanh, đồng thời đảm bảo cập nhật trường dẫn xuất nếu hợp đồng hoặc timezone thay đổi.

### 12.6. Báo cáo 7 ngày lịch gần nhất

“Bảy ngày” có ít nhất hai cách hiểu:

- **168 giờ gần nhất** kể từ thời điểm hiện tại.
- **Bảy ngày lịch địa phương**, có thể gồm ngày hôm nay và sáu ngày trước.

Ví dụ với ngày báo cáo **17/11/2026 tại Việt Nam**, nếu lấy **7 ngày lịch từ 11 đến hết 17/11**, biên theo múi giờ địa phương là:

~~~text
Start: 11/11/2026 00:00+07 = 10/11/2026 17:00Z
End:   18/11/2026 00:00+07 = 17/11/2026 17:00Z
~~~

Query:

~~~javascript
db.events.find({
  occurredAt: {
    $gte: ISODate("2026-11-10T17:00:00Z"),
    $lt: ISODate("2026-11-17T17:00:00Z")
  }
});
~~~

Đừng gọi khoảng này là “168 giờ gần nhất” trong hệ thống có DST. Biên ngày theo lịch và khoảng thời gian thực có thể khác nhau.

### 12.7. Đếm số ngày giữa hai mốc của một đặt phòng

Trong hệ thống đặt phòng, số **đêm lưu trú** có thể dựa trên ngày check-in/check-out tại địa điểm:

~~~javascript
{
  $dateDiff: {
    startDate: "$checkInAt",
    endDate: "$checkOutAt",
    unit: "day",
    timezone: "$propertyTimezone"
  }
}
~~~

Tuy nhiên, nếu check-in/check-out được lưu là thời điểm thực với giờ bất kỳ, biểu thức này đếm ranh giới ngày theo timezone. Hãy xác định nghiệp vụ có cần số đêm, số ngày lưu trú theo lịch, hay số giờ thực tế. Những quy tắc về check-out muộn, nhận phòng sớm hoặc đêm miễn phí phải được xử lý riêng.

## 13. Xử lý trường null, thiếu và thời điểm nhập từ String

Trong dữ liệu thực tế, không phải document nào cũng đã có paidAt hoặc completedAt. Biểu thức ngày giờ cần chính sách phù hợp.

### 13.1. Lọc những document có đủ hai mốc

Ví dụ chỉ tính thời gian xử lý cho các job đã hoàn tất:

~~~javascript
db.jobs.aggregate([
  {
    $match: {
      startedAt: { $type: "date" },
      endedAt: { $type: "date" }
    }
  },
  {
    $project: {
      _id: 1,
      elapsedMinutes: {
        $divide: [
          { $subtract: ["$endedAt", "$startedAt"] },
          60000
        ]
      },
      minuteBoundaries: {
        $dateDiff: {
          startDate: "$startedAt",
          endDate: "$endedAt",
          unit: "minute"
        }
      }
    }
  }
])
~~~

Điều kiện $type giúp chọn những document có BSON Date. Nếu mô hình dữ liệu cho phép Timestamp hoặc kiểu ngày giờ khác được operator hỗ trợ, cần thiết kế filter/validation tương ứng; không nên mặc định mọi kiểu có chữ “date” đều tương đương.

### 13.2. Dữ liệu String cần chuyển đổi rõ ràng

Giả sử một nguồn nhập cũ chứa:

~~~javascript
{
  createdAtText: "2026-11-14T08:30:00Z"
}
~~~

Biểu thức có thể chuyển đổi bằng $dateFromString:

~~~javascript
{
  $dateFromString: {
    dateString: "$createdAtText",
    onError: null,
    onNull: null
  }
}
~~~

**onError** và **onNull** giúp tránh làm hỏng cả pipeline khi gặp một số dữ liệu không đúng định dạng, nhưng chúng cũng có thể che dấu bản ghi lỗi nếu chỉ bỏ qua kết quả null. Khi import dữ liệu thực, nên đếm hoặc ghi nhận các trường hợp chuyển đổi thất bại để sửa dữ liệu nguồn.

Nếu chuỗi giờ **không kèm offset/múi giờ**, có thể cần chỉ định timezone khi parse. Nếu chuỗi đã chứa thông tin múi giờ, cần tuân theo quy tắc của operator thay vì vô tình khai báo timezone xung đột.

### 13.3. Dùng schema validation để ngăn sai kiểu

Một collection mới có thể yêu cầu occurredAt là BSON Date:

~~~javascript
db.createCollection("validatedEvents", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["occurredAt"],
      properties: {
        occurredAt: {
          bsonType: "date"
        },
        type: {
          bsonType: "string"
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Validator không tự chuyển dữ liệu cũ sang Date; muốn áp dụng cho collection đã tồn tại cần rà soát, migration và kế hoạch triển khai phù hợp.

## 14. MongoDB Java Sync Driver: xây dựng aggregation ngày giờ

Trong Java sử dụng **MongoDB Sync Driver**, có thể tạo các biểu thức aggregation bằng **org.bson.Document** và đưa vào pipeline **MongoCollection.aggregate()**. Điều quan trọng là giữ các mốc dưới dạng BSON Date thay vì vô tình truyền String.

Giả sử project có dependency **mongodb-driver-sync** tương thích và biến môi trường **MONGODB_URI**.

### 14.1. Báo cáo số event theo ngày Việt Nam

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

public class EventDailyReport {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Bson localDayExpression = new Document(
                "$dateTrunc",
                new Document("date", "$occurredAt")
                        .append("unit", "day")
                        .append("timezone", "Asia/Ho_Chi_Minh")
        );

        List<Bson> pipeline = Arrays.asList(
                Aggregates.group(
                        localDayExpression,
                        Accumulators.sum("eventCount", 1),
                        Accumulators.sum("totalAmount", "$amount")
                ),
                Aggregates.sort(Sorts.ascending("_id"))
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> events = client
                    .getDatabase("aggregation_dates_lab")
                    .getCollection("events");

            try (MongoCursor<Document> cursor = events
                    .aggregate(pipeline)
                    .iterator()) {

                while (cursor.hasNext()) {
                    System.out.println(cursor.next().toJson());
                }
            }
        }
    }
}
~~~

Trong code:

1. **Document("$dateTrunc", ...)** tạo biểu thức BSON giống cú pháp mongosh.
2. **Aggregates.group(...)** dùng Date đã truncate làm khóa nhóm.
3. **Accumulators.sum** đếm document và cộng trường amount.
4. **Aggregates.sort** sắp theo thời điểm bắt đầu bucket.
5. **try-with-resources** đóng cursor sau khi đọc xong hoặc khi có ngoại lệ.

Kết quả về mặt nghiệp vụ gồm **bốn ngày địa phương 13–16/11** với eventCount lần lượt **1, 3, 3, 1** như phần trước.

### 14.2. Tạo $dateAdd và $dateDiff bằng Document

Ví dụ một job có startedAt, endedAt:

~~~java
import org.bson.Document;
import org.bson.conversions.Bson;

Bson dueAtExpression = new Document(
        "$dateAdd",
        new Document("startDate", "$startedAt")
                .append("unit", "day")
                .append("amount", 7)
                .append("timezone", "Asia/Ho_Chi_Minh")
);

Bson calendarDaysExpression = new Document(
        "$dateDiff",
        new Document("startDate", "$startedAt")
                .append("endDate", "$endedAt")
                .append("unit", "day")
                .append("timezone", "Asia/Ho_Chi_Minh")
);
~~~

Hai đối tượng trên chỉ là **biểu thức BSON**, chưa tự chạy query. Chúng có thể được sử dụng làm giá trị cho stage $project hoặc $set:

~~~java
import java.util.Arrays;
import java.util.List;

List<Bson> pipeline = Arrays.asList(
        new Document("$project",
                new Document("_id", 1)
                        .append("dueAt", dueAtExpression)
                        .append("calendarDays", calendarDaysExpression)
        )
);
~~~

Trong một method có MongoCollection<Document> jobs, có thể gọi **jobs.aggregate(pipeline)** rồi đọc kết quả. Nếu startedAt/endedAt có thể null hoặc thiếu, phải xác định chính sách hiển thị null và xử lý record sai kiểu trước khi áp dụng vào nghiệp vụ.

### 14.3. Tạo Date boundary bằng java.time

Nhiều query lọc ngày địa phương sẽ hiệu quả hơn khi chuyển hai biên sang UTC ở Java. Thư viện **java.time** giúp thực hiện đúng quy tắc múi giờ:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 11, 14);

Instant startInstant = day.atStartOfDay(zone).toInstant();
Instant endInstant = day.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();

Date startUtc = Date.from(startInstant);
Date endUtc = Date.from(endInstant);
~~~

Kết quả:

~~~text
startInstant = 2026-11-13T17:00:00Z
endInstant   = 2026-11-14T17:00:00Z
~~~

Chú ý **day.plusDays(1).atStartOfDay(zone)** chứ không phải **startInstant.plus(24, HOURS)**. Khi zone có DST, hai cách có thể cho biên trên khác nhau.

### 14.4. Kết hợp boundary và Filters trong Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

Bson dayFilter = Filters.and(
        Filters.gte("occurredAt", startUtc),
        Filters.lt("occurredAt", endUtc)
);

// events là MongoCollection<Document> đã được khởi tạo.
try (MongoCursor<Document> cursor = events.find(dayFilter)
        .sort(Sorts.ascending("occurredAt"))
        .iterator()) {

    while (cursor.hasNext()) {
        System.out.println(cursor.next().toJson());
    }
}
~~~

Đoạn code giả định biến **events**, **startUtc**, **endUtc** đã được định nghĩa như các phần ngay trước đó. MongoDB nhận hai giá trị BSON Date và có thể sử dụng index trên occurredAt để thực hiện range query.

### 14.5. Không chuyển Instant thành String khi query

Nếu field occurredAt được lưu là BSON Date, tránh:

~~~java
// SAI về kiểu so sánh nếu occurredAt trong DB là BSON Date.
Filters.gte("occurredAt", startInstant.toString());
~~~

Thay vào đó, truyền **Date**, hoặc dùng codec/mapping được cấu hình đúng cho Instant:

~~~java
Filters.gte("occurredAt", Date.from(startInstant));
~~~

Một chuỗi ISO nhìn giống timestamp không tự trở thành BSON Date chỉ vì tên field là occurredAt.

## 15. Spring Data MongoDB: dùng MongoTemplate và aggregation expression

Với **Spring Data MongoDB**, ứng dụng có thể dùng **MongoTemplate** và các API aggregation. Cú pháp builder cụ thể cho toán tử ngày có thể thay đổi theo phiên bản Spring Data; khi cần minh họa cú pháp MongoDB rõ ràng và không phụ thuộc nhiều vào bộ builder, có thể dùng **AggregationOperation** xây dựng stage BSON.

### 15.1. Tạo trường localDayStart

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;

public class EventCalendarService {
    private final MongoTemplate mongoTemplate;

    public EventCalendarService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> listLocalDays() {
        AggregationOperation projectLocalDay = context ->
                new Document("$project",
                        new Document("_id", 1)
                                .append("occurredAt", 1)
                                .append(
                                        "localDayStart",
                                        new Document("$dateTrunc",
                                                new Document(
                                                        "date",
                                                        "$occurredAt")
                                                        .append("unit", "day")
                                                        .append(
                                                                "timezone",
                                                                "Asia/Ho_Chi_Minh")
                                        )
                                )
                );

        Aggregation aggregation = Aggregation.newAggregation(
                projectLocalDay,
                Aggregation.sort(Sort.by("localDayStart"))
        );

        return mongoTemplate.aggregate(
                aggregation,
                "events",
                Document.class
        ).getMappedResults();
    }
}
~~~

Ví dụ này giả định MongoTemplate trỏ vào database **aggregation_dates_lab**. Với một Spring Data version cụ thể, có thể thay raw Document bằng API biểu thức ngày có sẵn nếu hỗ trợ đúng tính năng và timezone cần dùng.

### 15.2. Kết hợp Query và Criteria cho range đã chuyển UTC

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import java.util.List;

import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class EventRangeService {
    private final MongoTemplate mongoTemplate;

    public EventRangeService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> findByLocalDay(
            LocalDate localDate,
            ZoneId timezone) {

        Date start = Date.from(
                localDate.atStartOfDay(timezone).toInstant()
        );

        Date end = Date.from(
                localDate.plusDays(1)
                        .atStartOfDay(timezone)
                        .toInstant()
        );

        Query query = Query.query(
                Criteria.where("occurredAt")
                        .gte(start)
                        .lt(end)
        );

        return mongoTemplate.find(
                query,
                Document.class,
                "events"
        );
    }
}
~~~

Hàm tìm các event trong một ngày địa phương bất kỳ: người gọi truyền LocalDate và ZoneId, Java tính hai ranh giới UTC, MongoDB lọc theo khoảng Date. Đây là ví dụ sự phân chia trách nhiệm hợp lý: **ứng dụng biết timezone nghiệp vụ**, còn **database thực hiện range scan có thể dùng index**.

### 15.3. Khi kết quả cần định dạng ngày theo locale

API không bắt buộc phải trả chuỗi ngày thay cho Date. Có thể trả BSON Date/Instant hoặc mốc bucket UTC cho client, rồi định dạng theo locale/timezone của người dùng.

Nếu báo cáo cần nhãn sẵn từ MongoDB, có thể sử dụng **$dateToString** với timezone tương ứng. Dù chọn cách nào, tránh đánh mất timezone nghiệp vụ hoặc trộn nhãn String với các giá trị Date trong cùng một field.

## 16. Hiệu năng và kế hoạch thực thi

Các biểu thức ngày giờ rất linh hoạt nhưng có thể tốn tài nguyên khi phải tính cho mọi document. Một pipeline đọc hàng triệu event nên ưu tiên **lọc sớm**, **dùng index khi có thể** và **chỉ tính những field cần thiết**.

### 16.1. $match sớm bằng khoảng thời điểm

Thay vì nhóm toàn bộ collection rồi chỉ lấy vài ngày báo cáo:

~~~javascript
db.events.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: { $sum: 1 }
    }
  },
  {
    $match: {
      _id: {
        $gte: ISODate("2026-11-13T17:00:00Z"),
        $lt: ISODate("2026-11-16T17:00:00Z")
      }
    }
  }
])
~~~

có thể chuyển điều kiện thời gian thành một **$match trên occurredAt trước bước $group**:

~~~javascript
db.events.aggregate([
  {
    $match: {
      occurredAt: {
        $gte: ISODate("2026-11-13T17:00:00Z"),
        $lt: ISODate("2026-11-16T17:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Đoạn thứ hai có điều kiện rõ trên field BSON Date gốc, tạo cơ hội sử dụng index theo khoảng thời gian. Điều kiện ví dụ lấy các ngày địa phương từ **14/11 đến hết 16/11** ở Việt Nam. Khoảng trước khi group phải bao phủ chính xác các bucket cần tổng hợp; không được tùy tiện chọn ranh giới UTC khiến dữ liệu nhóm bị cắt mất một phần.

### 16.2. Xem explain() của pipeline

~~~javascript
db.events.explain("executionStats").aggregate([
  {
    $match: {
      occurredAt: {
        $gte: ISODate("2026-11-13T17:00:00Z"),
        $lt: ISODate("2026-11-16T17:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: { $sum: 1 }
    }
  }
]);
~~~

Khi xem output, quan sát **winningPlan**, **IXSCAN/COLLSCAN**, **totalKeysExamined**, **totalDocsExamined** và những stage xử lý phía sau. Tùy phiên bản MongoDB và execution engine, cấu trúc explain aggregation có thể khác nhau.

Trên tám document mẫu, COLLSCAN có thể là lựa chọn hợp lý. Không suy ra hiệu năng production từ collection nhỏ; cần dùng dữ liệu và độ chọn lọc gần với workload thật.

### 16.3. Khi nào nên materialize bucket ngày?

Nếu hàng triệu report cùng tính đầu ngày của một timezone cố định, có thể cân nhắc lưu một trường dẫn xuất, ví dụ:

~~~javascript
{
  occurredAt: ISODate("2026-11-13T17:30:00Z"),
  localDayStart: ISODate("2026-11-13T17:00:00Z"),
  businessTimezone: "Asia/Ho_Chi_Minh"
}
~~~

Khi đó có thể tạo index trên localDayStart hoặc một compound index cùng tenant/type. Nhưng cần đảm bảo:

- localDayStart được tạo từ occurredAt và timezone đúng.
- Khi timezone hoặc occurredAt thay đổi, field dẫn xuất được tính lại.
- Dữ liệu lịch sử được backfill nếu triển khai sau khi đã có document.
- Với nhiều timezone, tên timezone cần được bảo toàn hoặc nằm trong khóa nhóm khi cần.

Không nên materialize một field chỉ vì một ví dụ explain trên ít dữ liệu trông chậm; lợi ích phải được xác nhận từ tần suất truy vấn và chi phí ghi/index.

## 17. Những lỗi thường gặp với $dateTrunc, $dateAdd và $dateDiff

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Sự kiện 00:30 ngày 14/11 bị nhóm vào 13/11 | Truncate theo UTC, trong khi báo cáo cần UTC+07 | Khai báo timezone: "Asia/Ho_Chi_Minh" |
| Kết quả $dateTrunc hiển thị 17:00Z của ngày trước | BSON Date lưu thời điểm UTC | Hiển thị bằng timezone địa phương, không sửa giá trị Date |
| Báo cáo tuần bắt đầu chủ nhật thay vì thứ hai | Không chỉ định startOfWeek cho unit week | Đặt startOfWeek: "monday" nếu nghiệp vụ yêu cầu |
| Bucket 15 phút bị hiểu thành 15 record | Nhầm binSize với số document | binSize là số đơn vị thời gian mỗi bucket |
| Khoảng ngày có thêm record đầu ngày kế tiếp | Dùng $lte cho biên trên | Dùng [start, nextStart) với $lt |
| Cộng một tháng từ 31/01 cho ngày không tồn tại | Tháng có số ngày khác nhau | Hiểu quy tắc chọn ngày cuối tháng và xác định chính sách hợp đồng |
| Cộng hai lần một tháng khác cộng thẳng hai tháng | Điều chỉnh cuối tháng ở bước trung gian | Xác định mốc gốc khi tính chu kỳ |
| “Ngày mai cùng giờ” lệch một tiếng ở New York | Cộng 24 giờ thực thay vì một ngày lịch có timezone | Dùng $dateAdd day với tên múi giờ IANA |
| Múi giờ New York luôn là -05:00 | Offset cố định không có DST | Dùng America/New_York khi cần lịch địa phương |
| $dateDiff day trả 1 dù cách nhau vài giây | Toán tử đếm ranh giới ngày | Dùng $subtract Date nếu cần elapsed duration |
| $dateDiff year dùng làm tuổi và trả quá cao | Đếm ranh giới năm mới, không phải số sinh nhật | Kiểm tra ngày/tháng sinh và quy tắc 29/02 |
| $dateDiff week trả 0 hoặc 1 khác kỳ vọng | Khác định nghĩa đầu tuần | Đồng bộ startOfWeek và timezone |
| dateAdd/dateTrunc lỗi với String ngày | Field lưu sai BSON type | Parse/chuyển đổi tường minh hoặc sửa schema |
| Tính ngày cho paidAt chưa có | Field thiếu/null | Định nghĩa xử lý giá trị chưa hoàn tất; lọc/kiểm tra kiểu |
| Truy vấn theo $expr tính ngày rất chậm | Phải tính biểu thức trên nhiều document | Chuyển biên địa phương sang UTC rồi lọc range field gốc |
| Đầu ngày UTC bị nhầm với đầu ngày kinh doanh | Chưa xác định timezone của địa điểm | Lưu businessTimezone, tính theo timezone đó |
| Biểu đồ thiếu cột ngày không có dữ liệu | $group chỉ tạo nhóm có document | Tạo trục lịch và bổ sung bucket rỗng nếu cần |
| Tổng số ngày thành 0 ở khoảng 12 giờ | $dateDiff day chưa vượt mốc nửa đêm | Chọn duration hay calendar boundary đúng nghiệp vụ |
| Sắp xếp theo chuỗi ngày bị sai | Trộn format, timezone hoặc dữ liệu String | Giữ Date, chỉ format ở lớp hiển thị |
| Index có nhưng explain vẫn COLLSCAN trên dữ liệu thử | Collection quá nhỏ hoặc filter ít chọn lọc | Đánh giá trên workload đại diện |

### 17.1. Phân biệt Date, LocalDate và timezone

Trong thiết kế Java:

- **Instant:** một thời điểm tuyệt đối trên trục UTC.
- **LocalDate:** một ngày theo lịch, không tự chứa timezone.
- **LocalDateTime:** ngày giờ địa phương, chưa xác định thời điểm UTC nếu thiếu timezone/offset.
- **ZonedDateTime:** ngày giờ gắn với ZoneId và quy tắc timezone.
- **BSON Date:** biểu diễn thời điểm; không lưu riêng tên vùng IANA.

Nếu chỉ truyền LocalDate "2026-11-14" vào truy vấn mà không xác định ZoneId, ứng dụng không biết ngày 14/11 bắt đầu và kết thúc ở thời điểm UTC nào. Đây là lỗi thiết kế dữ liệu, không phải riêng lỗi của MongoDB.

### 17.2. Câu hỏi cần xác định trước khi chọn toán tử

Hãy diễn đạt chính xác yêu cầu:

1. “Lấy sự kiện trong ngày 14/11” là ngày **UTC**, **Việt Nam** hay múi giờ của người dùng?
2. “Cộng một ngày” là **ngày lịch** hay **24 giờ thực**?
3. “Chênh lệch hai ngày” là số **lần qua nửa đêm** hay số **giờ chia cho 24**?
4. “Một tháng” là một tháng lịch với xử lý cuối tháng hay một chu kỳ cố định 30 ngày?
5. “Bắt đầu tuần” là **chủ nhật**, **thứ hai**, hay một ngày khác?
6. Có xử lý trường **null**, timestamp sai kiểu hoặc ngày nhập từ nguồn cũ không?

Trả lời được sáu câu hỏi này thường giúp tránh phần lớn lỗi ngày giờ do diễn giải khác nhau giữa database, backend và người dùng.

## 18. Bài tập thực hành

Các bài tập dùng database **aggregation_dates_lab** và collection **events** đã tạo ở phần 2. Những bài dùng collection khác chỉ là ví dụ schema giả định; không cần chạy thao tác ghi nào trên dữ liệu sản xuất.

### Bài 1. Xác định ngày Việt Nam

Cho hai thời điểm:

~~~text
A = 2026-11-13T16:59:59Z
B = 2026-11-13T17:00:00Z
~~~

Hãy xác định ngày địa phương Asia/Ho_Chi_Minh của A và B. Sau đó viết biểu thức $dateTrunc để đưa chúng về đầu ngày.

**Định hướng:**

- A là **13/11/2026 lúc 23:59:59+07**, đầu ngày tương ứng **12/11 17:00Z**.
- B là **14/11/2026 lúc 00:00:00+07**, đầu ngày tương ứng **13/11 17:00Z**.

Biểu thức:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

### Bài 2. Bucket 15 phút

Truy vấn thời điểm:

~~~text
2026-11-14T01:37:40Z
~~~

Hãy đưa nó về đầu bucket 15 phút theo UTC.

~~~javascript
{
  $dateTrunc: {
    date: ISODate("2026-11-14T01:37:40Z"),
    unit: "minute",
    binSize: 15,
    timezone: "UTC"
  }
}
~~~

**Đáp án:** **2026-11-14T01:30:00Z**. Nếu thời điểm là 01:45:00Z, nó nằm trong bucket mới bắt đầu lúc 01:45:00Z.

### Bài 3. Tổng doanh thu ORDER theo ngày địa phương

Yêu cầu: chỉ tính những document type = ORDER, nhóm theo ngày tại Việt Nam rồi tính **orderCount** và **revenue**.

~~~javascript
db.events.aggregate([
  { $match: { type: "ORDER" } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      revenue: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

**Kết quả dự kiến:** ngày 13/11 có 100, 14/11 có 275, 15/11 có 90, 16/11 có 90. Hãy giải thích tại sao ngày 14/11 có **hai** đơn chứ không phải một hoặc ba.

### Bài 4. Dùng timezone khi xác định đầu tuần

Viết biểu thức nhóm sự kiện theo tuần bắt đầu **thứ hai**, tại múi giờ Việt Nam:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "week",
    timezone: "Asia/Ho_Chi_Minh",
    startOfWeek: "monday"
  }
}
~~~

Nếu bỏ startOfWeek, liệu kết quả vẫn dùng thứ hai không? **Không**. Mặc định của $dateTrunc khi tính tuần là chủ nhật.

### Bài 5. So sánh cộng một tháng và cộng 30 ngày

Bắt đầu tại **2024-01-31T12:00:00Z**. Hãy tính:

1. $dateAdd amount 1, unit month.
2. $dateAdd amount 30, unit day.
3. Giải thích vì sao kết quả khác nhau.

~~~javascript
{
  $dateAdd: {
    startDate: ISODate("2024-01-31T12:00:00Z"),
    unit: "month",
    amount: 1
  }
}

{
  $dateAdd: {
    startDate: ISODate("2024-01-31T12:00:00Z"),
    unit: "day",
    amount: 30
  }
}
~~~

**Đáp án:** 29/02/2024 lúc 12:00 UTC và 01/03/2024 lúc 12:00 UTC. Một tháng lịch và ba mươi ngày không tương đương.

### Bài 6. Tính hạn sau bảy ngày

Giả sử một sự kiện E02 phải hết hạn sau **bảy ngày lịch tại Việt Nam**, tính từ occurredAt.

~~~javascript
db.events.aggregate([
  { $match: { _id: "E02" } },
  {
    $project: {
      _id: 1,
      expiresAt: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "day",
          amount: 7,
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

**Kết quả:** **2026-11-20T17:30:00Z**. Hãy trình bày giờ địa phương tương ứng và phân biệt với “đầu ngày hết hạn”.

### Bài 7. Ngày lịch và thời lượng thực

Hai thời điểm:

~~~text
Start: 2026-11-14T23:59:00Z
End:   2026-11-15T00:01:00Z
~~~

1. $dateDiff unit day, timezone UTC trả bao nhiêu?
2. Có bao nhiêu phút thực trôi qua?
3. Có thể lấy kết quả (1) nhân 24 giờ để kết luận thời lượng không?

**Đáp án:** **1 ngày theo ranh giới UTC**, **2 phút thực**, và **không thể** dùng 1 × 24 giờ làm thời lượng.

### Bài 8. $dateDiff theo ngày Việt Nam

Từ E04 đến E05 chỉ cách một giây:

~~~javascript
db.events.aggregate([
  { $match: { _id: "E05" } },
  {
    $project: {
      _id: 1,
      localDaysSinceE04: {
        $dateDiff: {
          startDate: ISODate("2026-11-14T16:59:59Z"),
          endDate: "$occurredAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
])
~~~

**Đáp án:** **1**, do đi qua ranh giới nửa đêm 15/11 theo giờ Việt Nam.

### Bài 9. Phân biệt 1 day và 24 hour qua DST

Bắt đầu lúc **2024-03-09T17:00:00Z** tại New York (12:00 EST). Hãy dự đoán:

~~~javascript
{
  $dateAdd: {
    startDate: ISODate("2024-03-09T17:00:00Z"),
    unit: "day",
    amount: 1,
    timezone: "America/New_York"
  }
}

{
  $dateAdd: {
    startDate: ISODate("2024-03-09T17:00:00Z"),
    unit: "hour",
    amount: 24,
    timezone: "America/New_York"
  }
}
~~~

**Đáp án:** lần lượt **2024-03-10T16:00:00Z** (12:00 EDT) và **2024-03-10T17:00:00Z** (13:00 EDT). Giải thích điều gì đã xảy ra khi New York chuyển sang DST.

### Bài 10. Lọc đúng ngày địa phương bằng range có index

Yêu cầu: lấy tất cả event **ngày 14/11/2026 tại Việt Nam**, sắp theo occurredAt tăng dần.

~~~javascript
db.events.createIndex({ occurredAt: 1 });

db.events.find({
  occurredAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
}).sort({ occurredAt: 1 });
~~~

**Kết quả:** E02, E03, E04. Hãy giải thích vì sao E05 ở biên trên bị loại và vì sao range trên Date gốc thường thuận lợi cho index hơn filter phải tính $dateTrunc trên mỗi document.

### Bài 11. Khi nào $dateDiff không phù hợp?

Một hệ thống thanh toán có yêu cầu: “đã quá hạn khi thời điểm hiện tại lớn hơn expiresAt dù chỉ một mili giây”. Có nên lấy $dateDiff unit day giữa expiresAt và NOW, rồi kiểm tra kết quả > 0 không?

**Đáp án:** Không. Nếu quá hạn trong cùng một ngày, $dateDiff day có thể vẫn bằng 0. So sánh hai BSON Date trực tiếp:

~~~javascript
db.subscriptions.find({
  expiresAt: { $lt: new Date() }
});
~~~

Cách này cũng thuận tiện hơn để sử dụng index trên expiresAt.

### Bài 12. Dữ liệu import chứa String

Giả sử có ba record:

~~~javascript
{ _id: 1, occurredAt: ISODate("2026-11-14T08:00:00Z") }
{ _id: 2, occurredAt: "2026-11-14T08:00:00Z" }
{ _id: 3, occurredAt: null }
~~~

Hãy đề xuất cách thống nhất dữ liệu trước khi lập báo cáo:

1. Xác định BSON type bằng $type hoặc kiểm tra schema.
2. Chuyển chuỗi theo định dạng xác định bằng $toDate/$dateFromString, quản lý onError/onNull nếu cần.
3. Xác định chính sách đối với null/missing.
4. Chuyển dữ liệu cũ và đặt validator để hạn chế tái diễn.

**Không nên** mặc định ba giá trị trên đều có thể dùng trực tiếp làm date cho mọi phép tính mà không cần xử lý.

## 19. Bảng chọn toán tử theo yêu cầu

| Yêu cầu | Toán tử/cách thực hiện nên xem xét |
|---|---|
| Lấy đầu ngày, đầu tuần, đầu tháng | $dateTrunc |
| Gom dữ liệu vào bucket 15 phút | $dateTrunc unit minute, binSize 15 |
| Xác định tuần bắt đầu thứ hai | $dateTrunc với startOfWeek monday |
| Cộng 7 ngày lịch địa phương | $dateAdd unit day, amount 7, timezone |
| Cộng đúng 48 giờ | $dateAdd unit hour, amount 48 |
| Gia hạn một tháng | $dateAdd unit month và quy tắc cuối tháng |
| Đếm số ranh giới ngày/tháng đã vượt | $dateDiff với unit và timezone phù hợp |
| Đo thời gian thực trôi qua chính xác | $subtract giữa hai BSON Date |
| Hiển thị nhãn ngày địa phương | $dateToString với timezone |
| Lọc toàn bộ sự kiện trong một ngày địa phương | Chuyển hai biên địa phương thành Date UTC, dùng $gte/$lt |
| Sắp xếp/lọc theo thời điểm nhanh | Index trên BSON Date gốc hoặc field dẫn xuất được quản lý nhất quán |
| Đảm bảo field có đúng kiểu ngày | $jsonSchema với bsonType: "date" |

## 20. Kết luận

Ba toán tử có vai trò bổ sung nhau:

~~~text
BSON Date (thời điểm UTC)
          |
          +------ $dateTrunc -----> Đầu bucket theo lịch địa phương
          |
          +------ $dateAdd -------> Thời điểm mới sau khi cộng/trừ đơn vị
          |
          +------ $dateDiff ------> Số ranh giới đơn vị đã đi qua
          |
          +------ $subtract -----> Thời lượng thực theo mili giây
~~~

**Những nguyên tắc quan trọng cần ghi nhớ:**

1. **BSON Date là thời điểm tuyệt đối**, không tự lưu timezone ban đầu. Khi báo cáo theo ngày địa phương, phải cung cấp timezone.
2. **$dateTrunc trả về đầu khoảng dưới dạng Date**, không phải tên ngày hay chuỗi. Kết quả có thể hiển thị là 17:00Z ngày trước nếu timezone là Asia/Ho_Chi_Minh.
3. **$dateAdd với ngày/tháng/năm là phép tính lịch**, không phải lúc nào cũng tương đương cộng số giờ hoặc số ngày cố định. DST và cuối tháng có thể làm kết quả khác nhau.
4. **$dateDiff đếm ranh giới đơn vị**, không tự trả độ dài thời gian có phần thập phân. Muốn elapsed duration, thường dùng phép trừ hai Date.
5. **Dùng [startUtc, endUtc) khi lọc ngày địa phương** để tránh đếm trùng ranh giới và tận dụng index trên field Date.
6. **Kiểu BSON nhất quán quan trọng không kém công thức.** Cần kiểm soát chuỗi thời gian, null/missing và timezone nghiệp vụ ngay từ lúc ghi.
7. **Phân biệt công cụ tính lịch với định nghĩa hợp đồng**: kỳ thuê một tháng, số đêm lưu trú, hạn thanh toán, ngày sinh hoặc SLA cần chính sách nghiệp vụ rõ ràng.

Khi tách bạch **thời điểm UTC**, **lịch theo múi giờ** và **thời lượng thực**, bạn có thể dùng $dateTrunc, $dateAdd và $dateDiff để xây dựng báo cáo MongoDB chính xác, đồng thời viết các câu truy vấn và ứng dụng Java dễ kiểm tra, dễ mở rộng hơn khi dữ liệu trải qua nhiều khu vực và múi giờ.
