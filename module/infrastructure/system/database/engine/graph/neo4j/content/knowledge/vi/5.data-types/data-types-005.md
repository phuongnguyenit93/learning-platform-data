# Ngày, giờ, ngày giờ, múi giờ và khoảng thời gian trong Cypher

Khi mô hình hóa dữ liệu liên kết bằng **Neo4j**, rất nhiều node và relationship cần ghi nhận thời gian: ngày đăng ký tài khoản, thời điểm xảy ra sự kiện, giờ hoạt động của cửa hàng, hạn sử dụng hay thời lượng của một phiên học. Cypher hỗ trợ các **kiểu dữ liệu thời gian (temporal types)** chuyên biệt để biểu diễn và truy vấn những thông tin đó.

Bài học thuộc chương **Kiểu dữ liệu** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Trọng tâm là chọn đúng kiểu cho từng yêu cầu nghiệp vụ, tạo giá trị bằng các hàm Cypher, hiểu múi giờ và offset, thực hiện phép toán với `DURATION`, truy vấn theo khoảng thời gian, rồi trao đổi dữ liệu với Java Driver và Spring Data Neo4j.

**Mục tiêu sau bài học:** phân biệt rõ *ngày lịch*, *giờ trong ngày*, *thời điểm có múi giờ* và *độ dài khoảng thời gian*; biết vì sao những khái niệm này không thể thay thế cho nhau.

## 1. Sáu kiểu thời gian cần nhận biết

Cypher có sáu nhóm kiểu temporal thường gặp:

| Kiểu Cypher | Hàm tạo | Chứa thông tin gì? | Dùng khi nào? |
| --- | --- | --- | --- |
| `DATE` | `date()` | Ngày lịch: năm, tháng, ngày | Sinh nhật, ngày mở khóa học, ngày hết hạn |
| `LOCAL TIME` | `localtime()` | Giờ, phút, giây; không có múi giờ/offset | Giờ mở cửa theo lịch địa phương |
| `ZONED TIME` | `time()` | Giờ trong ngày kèm UTC offset | Giờ hẹn kèm độ lệch UTC |
| `LOCAL DATETIME` | `localdatetime()` | Ngày và giờ; không có múi giờ/offset | Lịch hẹn có ngữ cảnh múi giờ do ứng dụng quản lý |
| `ZONED DATETIME` | `datetime()` | Ngày và giờ kèm offset hoặc định danh vùng múi giờ | Thời điểm thanh toán, tạo tài khoản, ghi log |
| `DURATION` | `duration()` | Khoảng thời gian gồm thành phần lịch và thời lượng | Thời gian làm bài, cộng hạn, tính khoảng cách giữa hai mốc |

> Từ “local” trong `LOCAL TIME` và `LOCAL DATETIME` có nghĩa là **không chứa thông tin múi giờ**, không có nghĩa Neo4j tự gắn múi giờ nơi đặt máy chủ vào giá trị được lưu.

Ví dụ trực quan:

```cypher
RETURN
  date('2026-11-25') AS ngay,
  localtime('09:30:00') AS gioDiaPhuong,
  time('09:30:00+07:00') AS gioCoOffset,
  localdatetime('2026-11-25T09:30:00') AS ngayGioDiaPhuong,
  datetime('2026-11-25T09:30:00+07:00') AS mocThoiGian,
  duration('PT1H30M') AS thoiLuong;
```

Các biểu thức trên đều tạo được giá trị trong truy vấn. Tương tự chuỗi, số và boolean, các kiểu temporal cũng có thể được lưu làm **property** của node hoặc relationship.

## 2. DATE: chỉ ghi nhận ngày lịch

`DATE` biểu diễn một ngày theo lịch, **không kèm giờ trong ngày hay múi giờ**. Ngày sinh, ngày xuất bản và ngày nhận bằng cấp là những trường hợp phù hợp.

### 2.1. Tạo ngày từ chuỗi hoặc các thành phần

```cypher
RETURN
  date('2026-11-25') AS fromIsoString,
  date({year: 2026, month: 11, day: 25}) AS fromComponents;
```

Các chuỗi theo định dạng ISO 8601 giúp tránh nhầm lẫn ngày/tháng. `'2026-11-25'` rõ ràng hơn `'25/11/2026'` vì định dạng có dấu gạch chéo phụ thuộc quy ước vùng.

Có thể lấy thành phần ngày:

```cypher
WITH date('2026-11-25') AS d
RETURN
  d.year AS nam,
  d.month AS thang,
  d.day AS ngay,
  d.dayOfWeek AS thuTrongTuan;
```

`dayOfWeek` thường tuân theo ISO: thứ Hai là `1`, Chủ nhật là `7`.

### 2.2. DATE khác với chuỗi trông giống ngày

```cypher
RETURN
  '2026-11-25' AS dateText,
  date('2026-11-25') AS actualDate;
```

`dateText` là `STRING`, trong khi `actualDate` là `DATE`. Nếu cần tính số ngày còn lại hoặc lọc theo khoảng ngày, nên lưu thành `DATE` thay vì chuỗi.

Ví dụ node chứa ngày xuất bản:

```cypher
CREATE (b:TemporalDemoBook {
  bookCode: 'B-001',
  title: 'Kiến trúc dữ liệu đồ thị',
  publishedOn: date('2026-11-25')
})
RETURN b.bookCode, b.publishedOn;
```

Lệnh `CREATE` tạo node mới mỗi lần chạy. Khi thực hành lặp lại, cần chú ý tránh tạo dữ liệu demo trùng.

## 3. LOCAL TIME và ZONED TIME: giờ trong ngày

### 3.1. LOCAL TIME chỉ mô tả giờ

`LOCAL TIME` lưu thời gian trong ngày mà không gắn UTC offset:

```cypher
RETURN
  localtime('08:00:00') AS openingTime,
  localtime('17:30:00') AS closingTime,
  localtime({hour: 9, minute: 15, second: 0}) AS meetingTime;
```

Một cửa hàng mở cửa lúc 08:00 mỗi ngày theo giờ địa phương có thể lưu `openingTime: localtime('08:00:00')`. Đây là giờ lặp theo lịch, **không đại diện một thời điểm duy nhất trên trục thời gian toàn cầu**.

### 3.2. ZONED TIME chứa độ lệch UTC

`time()` tạo giá trị giờ kèm offset:

```cypher
RETURN
  time('09:30:00+07:00') AS morningAtUtcPlus7,
  time('02:30:00Z') AS morningAtUtc,
  time({hour: 18, minute: 0, timezone: '+07:00'}) AS eveningAtUtcPlus7;
```

Ký hiệu `Z` nghĩa là offset `+00:00` so với UTC. `+07:00` là UTC cộng bảy giờ; các offset ghi được vào `ZONED TIME` gắn với giờ trong ngày, nhưng không cung cấp một ngày lịch cụ thể để xác định các quy tắc đổi giờ theo mùa.

**Không nên nhầm `ZONED TIME` với một mốc sự kiện:** chỉ có giờ và offset vẫn chưa đủ để xác định một sự kiện đã xảy ra vào ngày nào. Nếu cần một thời điểm phát sinh giao dịch, hãy dùng `ZONED DATETIME`.

### 3.3. Khi nào chọn LOCAL TIME?

Giả sử cửa hàng mở lúc 09:00 tại thành phố nơi cửa hàng tọa lạc, quanh năm theo giờ địa phương. Có thể lưu:

```cypher
CREATE (s:TemporalDemoStore {
  storeId: 'ST-001',
  city: 'Hồ Chí Minh',
  timeZoneId: 'Asia/Ho_Chi_Minh',
  opensAt: localtime('09:00:00'),
  closesAt: localtime('21:00:00')
})
RETURN s.storeId, s.opensAt, s.closesAt, s.timeZoneId;
```

Ở đây `opensAt` là giờ trong ngày; `timeZoneId` là thông tin **nghiệp vụ lưu riêng** để ứng dụng xác định giờ đó thuộc vùng nào. Với lịch nhiều ngày trong tuần, ca qua nửa đêm hoặc quốc gia có giờ mùa hè, cần thêm quy tắc lịch hoạt động thay vì chỉ hai thuộc tính giờ.

## 4. LOCAL DATETIME và ZONED DATETIME: ngày kết hợp giờ

### 4.1. LOCAL DATETIME không mang múi giờ

`localdatetime()` tạo một giá trị ngày và giờ:

```cypher
RETURN
  localdatetime('2026-11-25T14:30:00') AS meetingLocal,
  localdatetime({
    year: 2026,
    month: 11,
    day: 25,
    hour: 14,
    minute: 30
  }) AS fromComponents;
```

Giá trị này cho biết **ngày 25-11-2026 lúc 14:30**, nhưng không cho biết 14:30 thuộc TP. Hồ Chí Minh, Tokyo hay Paris. Nếu hai hệ thống ở hai múi giờ khác nhau cùng đọc giá trị này, chúng cần **quy ước bên ngoài** để xác định thời điểm thực tế.

`LOCAL DATETIME` phù hợp khi ứng dụng lưu một giờ hẹn “theo lịch địa phương” cùng ngữ cảnh múi giờ ở một trường khác. Nó không nên được mặc định coi là UTC.

### 4.2. ZONED DATETIME biểu diễn thời điểm có ngữ cảnh múi giờ

`datetime()` tạo giá trị ngày giờ kèm offset hoặc định danh vùng múi giờ:

```cypher
RETURN
  datetime('2026-11-25T14:30:00+07:00') AS withOffset,
  datetime('2026-11-25T07:30:00Z') AS inUtc,
  datetime({
    year: 2026,
    month: 11,
    day: 25,
    hour: 14,
    minute: 30,
    timezone: 'Asia/Ho_Chi_Minh'
  }) AS withNamedZone;
```

Trong ví dụ này, 14:30 tại UTC+07 và 07:30 tại UTC+00 đại diện cùng một thời điểm trên trục thời gian. Khi hiển thị, ứng dụng có thể cần quy đổi sang múi giờ của người dùng.

**Ghi nhớ cách chọn kiểu:**

- Lịch trình chỉ cần ngày → `DATE`.
- Giờ mở cửa lặp theo ngày → `LOCAL TIME`, có thể kết hợp thông tin vùng múi giờ.
- Lịch hẹn địa phương chưa xác định vùng → `LOCAL DATETIME`.
- Thời điểm sự kiện đã xảy ra, log hệ thống, thanh toán → `ZONED DATETIME`.

## 5. Múi giờ: UTC, offset và định danh vùng

Ba khái niệm cần phân biệt:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| UTC | `2026-11-25T07:30:00Z` | Mốc thời gian theo UTC |
| UTC offset | `+07:00`, `-05:00` | Độ lệch cố định tại mốc được biểu diễn |
| Vùng múi giờ | `Asia/Ho_Chi_Minh`, `Europe/Paris` | Quy tắc múi giờ theo vùng địa lý và thời gian |

Một **offset** như `+07:00` chỉ cho biết lệch UTC bảy giờ tại thời điểm đó. Một **vùng** như `Europe/Paris` có quy tắc lịch sử và có thể đổi offset theo mùa. Vì vậy, offset và định danh vùng không phải hai tên gọi tương đương.

### 5.1. Giờ mùa hè (DST) và giờ địa phương mơ hồ

Ở các vùng áp dụng daylight saving time (DST), một giờ địa phương có thể:

- **Không tồn tại** khi đồng hồ nhảy tới.
- **Xuất hiện hai lần** khi đồng hồ lùi lại, dẫn tới hai thời điểm UTC khác nhau.

Ví dụ chuỗi `'2026-10-25T02:30:00'` ở một vùng châu Âu có đổi giờ theo mùa có thể là thời gian mơ hồ. Không thể tự suy ra thời điểm UTC duy nhất chỉ từ `LOCAL DATETIME`.

Quy tắc thực hành:

1. Lưu thời điểm sự kiện bằng `ZONED DATETIME`, tốt nhất có đủ offset/zone cần thiết.
2. Nếu cần bảo toàn cách đặt lịch theo vùng địa lý, lưu **định danh vùng múi giờ** thay vì chỉ offset.
3. Khi chuyển thời gian do người dùng nhập thành thời điểm UTC, xác thực các trường hợp giờ không tồn tại hoặc lặp do DST.
4. Không tự cộng hoặc trừ `7` giờ cho mọi nơi và mọi ngày; hãy dùng hệ thư viện thời gian có hiểu timezone.

### 5.2. Độ chính xác đến phần nhỏ của giây

Cypher hỗ trợ các thành phần thời gian có độ chính xác cao, bao gồm phần nhỏ của giây:

```cypher
RETURN
  datetime('2026-11-25T14:30:00.123456789+07:00') AS eventMoment,
  localtime('09:15:30.500') AS localTimeWithMillis;
```

Phần `.123456789` thể hiện nanosecond trong biểu diễn thời gian tương ứng. Tuy nhiên, **độ chính xác dữ liệu đầu vào thực tế** còn tùy nguồn: cảm biến đo millisecond không trở nên chính xác tới nanosecond chỉ vì được lưu trong một kiểu có thể chứa nanosecond.

## 6. DURATION: khoảng thời gian có ý nghĩa lịch

`DURATION` mô tả một khoảng thời gian, khác với một mốc ngày hoặc ngày giờ. Nó có thể chứa thành phần tháng, ngày, giây và phần nhỏ của giây; những thành phần này không phải lúc nào cũng quy đổi thành một số giây cố định.

### 6.1. Cú pháp thời lượng ISO 8601

`duration()` chấp nhận chuỗi theo cú pháp ISO 8601 với tiền tố `P`. Phần sau `T` biểu diễn đơn vị thời gian trong ngày:

| Giá trị | Ý nghĩa |
| --- | --- |
| `duration('P7D')` | 7 ngày |
| `duration('P2W')` | 2 tuần |
| `duration('P1M')` | 1 tháng lịch |
| `duration('P1Y')` | 1 năm lịch |
| `duration('PT1H30M')` | 1 giờ 30 phút |
| `duration('PT45S')` | 45 giây |
| `duration('P2DT3H')` | 2 ngày và 3 giờ |
| `duration('PT1M')` | 1 phút |

**Chú ý chữ `M`:** trong `P1M`, `M` là **tháng**; trong `PT1M`, chữ `M` đứng sau `T` nên là **phút**. Nhầm lẫn này có thể gây lỗi nghiệp vụ nghiêm trọng.

Ví dụ:

```cypher
RETURN
  duration('P1M') AS oneCalendarMonth,
  duration('PT1M') AS oneMinute,
  duration('P3DT2H15M') AS courseDuration;
```

### 6.2. Tạo duration từ thành phần

Có thể tạo `DURATION` bằng map:

```cypher
RETURN
  duration({days: 7, hours: 2}) AS weekAndTwoHours,
  duration({hours: 1, minutes: 45, seconds: 30}) AS lessonLength;
```

Giá trị `duration({days: 7})` mang thành phần **ngày lịch**. Trên một thời điểm ở vùng có DST, “cộng một ngày lịch” và “cộng 24 giờ thực” có thể cho giờ hiển thị khác nhau. Vì vậy cần xác định mục tiêu là *dịch lịch* hay *cộng thời lượng thực*.

### 6.3. Một tháng không phải luôn 30 ngày

Tháng lịch có thể dài 28, 29, 30 hoặc 31 ngày. Do đó:

- `duration('P1M')` là **một tháng lịch**.
- `duration('P30D')` là **ba mươi ngày**.
- `duration('PT720H')` là **720 giờ**.

Ba khái niệm không được mặc định tương đương, nhất là khi có DST hoặc khi cộng từ ngày gần cuối tháng.

Ví dụ gói thuê bao hết hạn sau một tháng lịch nên dùng độ dài tháng theo quy tắc nghiệp vụ, còn timeout 90 phút cần sử dụng thời lượng phút/giây.

## 7. Tính toán với DATE, DATETIME và DURATION

### 7.1. Cộng/trừ duration vào ngày

```cypher
WITH date('2026-11-25') AS startDate
RETURN
  startDate + duration('P7D') AS afterSevenDays,
  startDate - duration('P1D') AS previousDay;
```

Kết quả lần lượt là ngày `2026-12-02` và `2026-11-24`.

Ví dụ tính hạn đọc tài liệu theo ngày lịch:

```cypher
WITH date('2026-11-25') AS borrowedOn
RETURN
  borrowedOn,
  borrowedOn + duration('P14D') AS dueOn;
```

Nếu hạn tính theo **ngày làm việc**, phép cộng 14 ngày lịch chưa đủ: ứng dụng còn phải xét thứ Bảy, Chủ nhật và ngày nghỉ lễ theo quy định.

### 7.2. Cộng/trừ duration vào ngày giờ

```cypher
WITH datetime('2026-11-25T09:00:00+07:00') AS startedAt
RETURN
  startedAt,
  startedAt + duration('PT90M') AS endedAt;
```

`PT90M` là 90 phút. Vì giá trị gốc có offset UTC+07, kết quả tính toán giữ được ngữ cảnh thời gian cần thiết để diễn giải mốc kết thúc.

### 7.3. Đo khoảng cách giữa hai mốc

`duration.between(start, end)` tính khoảng thời gian từ thời điểm bắt đầu đến kết thúc:

```cypher
WITH
  datetime('2026-11-25T09:00:00+07:00') AS startedAt,
  datetime('2026-11-25T10:30:00+07:00') AS finishedAt
RETURN duration.between(startedAt, finishedAt) AS elapsed;
```

Kết quả tương ứng khoảng 1 giờ 30 phút.

Cypher còn có các hàm chọn đơn vị để diễn giải chênh lệch:

```cypher
WITH
  date('2026-11-25') AS fromDate,
  date('2026-12-02') AS toDate
RETURN
  duration.inDays(fromDate, toDate) AS daysBetween,
  duration.inMonths(fromDate, toDate) AS monthsComponent;
```

`duration.inDays()` và `duration.inMonths()` không chỉ khác cách hiển thị: chúng phục vụ các phép tính có ý nghĩa đơn vị lịch khác nhau. Khi cần kết quả dạng *tổng số giây* hoặc *tổng số phút*, phải kiểm soát rõ đơn vị và quy tắc làm tròn. Đừng dùng số tháng để suy ra số giây bằng một hằng số.

### 7.4. So sánh đúng cùng loại thời gian

```cypher
WITH
  date('2026-11-25') AS today,
  date('2026-12-01') AS deadline
RETURN
  today < deadline AS beforeDeadline,
  today = deadline AS onDeadline;
```

Không nên trộn `DATE`, `LOCAL DATETIME` và `ZONED DATETIME` trong điều kiện với giả định chúng tự quy đổi giống nhau. Hãy chọn kiểu lưu trữ nhất quán và chuyển đổi có chủ đích ở biên ứng dụng/truy vấn.

## 8. Lấy thành phần ngày giờ và tạo giá trị hiện tại

### 8.1. Truy cập thành phần trong giá trị temporal

Cypher cho phép truy cập các thành phần thông qua dấu chấm:

```cypher
WITH datetime('2026-11-25T14:30:45+07:00') AS eventAt
RETURN
  eventAt.year AS eventYear,
  eventAt.month AS eventMonth,
  eventAt.day AS eventDay,
  eventAt.hour AS eventHour,
  eventAt.minute AS eventMinute,
  eventAt.second AS eventSecond;
```

Việc trích năm/tháng/ngày giúp tạo nhãn thống kê, nhưng với truy vấn lọc nhiều bản ghi, thường nên lọc bằng **khoảng mốc thời gian** trên property gốc thay vì luôn trích `eventAt.year` trên từng dòng.

### 8.2. Hàm lấy ngày giờ hiện tại

`date()`, `time()`, `localtime()`, `datetime()` và `localdatetime()` có thể được gọi không tham số để lấy giá trị từ đồng hồ của hệ thống thực thi.

```cypher
RETURN
  date() AS currentDate,
  localtime() AS currentLocalTime,
  datetime() AS currentDateTime;
```

Các kết quả này **thay đổi theo thời điểm chạy** và chịu ảnh hưởng của quy tắc đồng hồ/múi giờ của môi trường thực thi. Khi cần xử lý thời điểm giao dịch nhất quán, sử dụng cùng nguồn thời gian trong một đơn vị công việc và xác định rõ quy tắc timezone. Neo4j hỗ trợ các chế độ đồng hồ liên quan transaction, statement và realtime cho nhóm hàm temporal; ứng dụng nên chọn chế độ theo yêu cầu tính nhất quán thay vì mặc định mọi lời gọi là độc lập như nhau.

Nếu muốn lấy thời gian hiện tại trong vùng đã chỉ định, có thể truyền timezone qua map:

```cypher
RETURN datetime({timezone: 'Asia/Ho_Chi_Minh'}) AS nowInHoChiMinh;
```

Kết quả là một mốc thời gian có ngữ cảnh vùng được yêu cầu. Đây là ví dụ động nên không có giá trị cố định để đối chiếu.

## 9. Lưu thời gian trên node và relationship

Cả node và relationship đều có thể sở hữu property thuộc các kiểu temporal.

Giả sử nền tảng học tập cần lưu ngày phát hành khóa học và thời điểm ghi danh của người học:

```cypher
CREATE
  (learner:TemporalDemoLearner {
    learnerId: 'L-100',
    name: 'Hà',
    registeredOn: date('2026-11-01')
  }),
  (course:TemporalDemoCourse {
    courseId: 'C-NEO-01',
    title: 'Neo4j với Cypher',
    publishedOn: date('2026-10-25'),
    typicalLessonLength: duration('PT45M')
  })
CREATE (learner)-[:ENROLLED_IN {
  enrolledAt: datetime('2026-11-25T09:15:00+07:00')
}]->(course);
```

Trong mô hình này:

- `registeredOn`, `publishedOn` là `DATE` vì nghiệp vụ chỉ cần ngày.
- `typicalLessonLength` là `DURATION` vì biểu thị **thời lượng**, không phải mốc bắt đầu.
- `enrolledAt` là `ZONED DATETIME` vì cần xác định mốc đăng ký cụ thể.
- Relationship `ENROLLED_IN` là liên kết thực giữa người học và khóa học; property `enrolledAt` ghi thời điểm của chính quan hệ này.

Truy vấn đọc:

```cypher
MATCH (l:TemporalDemoLearner)-[r:ENROLLED_IN]->(c:TemporalDemoCourse)
RETURN
  l.name,
  c.title,
  l.registeredOn,
  r.enrolledAt,
  c.typicalLessonLength;
```

Không nên lưu dữ liệu thời gian dưới dạng một map như `{year: 2026, month: 11, day: 25}` làm **giá trị property**, vì Neo4j không lưu trực tiếp map thành một property. Hãy dùng kiểu `DATE`/`DATETIME` hoặc các trường đơn có chủ đích.

## 10. Lọc theo khoảng thời gian và ảnh hưởng đến hiệu năng

Một truy vấn thực tế thường cần lấy các bản ghi trong một ngày hoặc một khoảng ngày.

### 10.1. Khoảng nửa mở [start, end)

Dùng cận dưới **bao gồm** và cận trên **không bao gồm**:

```cypher
MATCH (e:TemporalDemoEvent)
WHERE e.occurredAt >= datetime('2026-11-25T00:00:00+07:00')
  AND e.occurredAt < datetime('2026-11-26T00:00:00+07:00')
RETURN e.eventId, e.occurredAt
ORDER BY e.occurredAt;
```

Đây là cách biểu diễn ngày 25-11-2026 theo offset UTC+07, dành cho dữ liệu `occurredAt` được lưu thống nhất theo `ZONED DATETIME`.

Dùng cận trên là **đầu ngày kế tiếp** tránh phải tự đoán “giây cuối ngày” hoặc độ chính xác tối đa của phần nhỏ giây. Khoảng dạng `[start, end)` cũng dễ ghép thành các khoảng liên tiếp mà không đếm trùng mốc ranh giới.

### 10.2. Tìm ngày đến hạn

```cypher
MATCH (task:TemporalDemoTask)
WHERE task.dueOn IS NOT NULL
  AND task.dueOn < date('2026-12-01')
RETURN task.taskId, task.dueOn
ORDER BY task.dueOn;
```

`dueOn` ở đây là `DATE`. Nếu chuyển thành chuỗi `'2026-12-01'` mà không khai báo kiểu đúng, điều kiện thời gian sẽ không có ngữ nghĩa như mong muốn.

### 10.3. Property temporal và index

Neo4j có thể sử dụng **range index** để hỗ trợ các điều kiện so sánh hoặc lọc theo khoảng trên property temporal khi cấu trúc index và kế hoạch truy vấn phù hợp.

Ví dụ cú pháp tạo index:

```cypher
CREATE RANGE INDEX temporal_event_at_idx IF NOT EXISTS
FOR (e:TemporalDemoEvent)
ON (e.occurredAt);
```

Không phải mọi truy vấn có index đều bắt buộc dùng index. Hãy kiểm tra kế hoạch `EXPLAIN` hoặc `PROFILE` với dữ liệu đủ đại diện:

```cypher
EXPLAIN
MATCH (e:TemporalDemoEvent)
WHERE e.occurredAt >= datetime('2026-11-25T00:00:00+07:00')
  AND e.occurredAt < datetime('2026-11-26T00:00:00+07:00')
RETURN e.eventId;
```

Một chiến lược thường hữu ích là **so sánh trực tiếp property với cận thời gian** thay vì viết `WHERE e.occurredAt.year = 2026` rồi mong cùng hiệu quả. Khả năng dùng index phụ thuộc phiên bản Neo4j, loại index, số lượng bản ghi và cấu trúc điều kiện cụ thể.

## 11. Nhập dữ liệu từ chuỗi và kiểm soát lỗi

CSV, HTTP payload và nhiều nguồn tích hợp ban đầu chứa ngày giờ dưới dạng chuỗi. Cần xác định định dạng và chuyển sang kiểu temporal phù hợp trước khi ghi.

### 11.1. Chuyển đổi đầu vào hợp lệ

```cypher
WITH {
  birthDateText: '2001-07-18',
  eventTimeText: '2026-11-25T09:15:00+07:00',
  openingTimeText: '08:30:00',
  lessonLengthText: 'PT1H20M'
} AS raw
RETURN
  date(raw.birthDateText) AS birthDate,
  datetime(raw.eventTimeText) AS eventAt,
  localtime(raw.openingTimeText) AS opensAt,
  duration(raw.lessonLengthText) AS lessonLength;
```

Khi đọc ngày giờ do người dùng nhập, cần quyết định:

1. Có chấp nhận chuỗi thiếu timezone cho sự kiện hay không?
2. Chuỗi có theo ISO 8601 không?
3. Đầu vào có thể có `null` hoặc chuỗi rỗng không?
4. Múi giờ và quy tắc DST được xử lý ở tầng nào?
5. Một ngày không hợp lệ như `2026-02-29` sẽ bị từ chối ra sao?

### 11.2. Tránh để dữ liệu sai làm hỏng pipeline

Các constructor temporal yêu cầu giá trị hợp lệ. Chuỗi ngày không hợp lệ có thể gây lỗi khi chuyển đổi; đừng mặc định mọi trường hợp sai định dạng sẽ tự trả về `null`.

Ví dụ chỉ gọi `date()` khi chuỗi khác null và đúng mẫu hình thức:

```cypher
WITH '2026-11-25' AS rawDate
RETURN
  CASE
    WHEN rawDate IS NOT NULL
      AND rawDate =~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    THEN date(rawDate)
    ELSE null
  END AS parsedDate;
```

**Giới hạn của ví dụ:** regex chỉ kiểm tra hình thức `YYYY-MM-DD`, **không xác nhận ngày có thực**. `2026-02-29` vẫn khớp regex nhưng không phải ngày hợp lệ. Với dữ liệu hàng loạt, cần thêm bước xác thực ngày thật ở ứng dụng hoặc cơ chế xử lý lỗi riêng trước khi tạo transaction ghi Neo4j.

### 11.3. Không gán trực tiếp giá trị null khi chưa rõ ý định

Khi `SET n.publishedOn = null`, Neo4j **xóa property** đó. Nếu API hiểu “trường ngày không gửi” là “giữ giá trị cũ” nhưng lại chuyển thành `null`, cập nhật có thể xóa dữ liệu ngoài ý muốn.

Với tham số hóa:

```cypher
MATCH (e:TemporalDemoEvent {eventId: $eventId})
SET e.occurredAt = $occurredAt
RETURN e.eventId, e.occurredAt;
```

Hãy đảm bảo `$occurredAt` là giá trị temporal được ứng dụng kiểm tra, và quy tắc đối với `null` được định nghĩa rõ. Nếu hệ thống chỉ cần lưu ngày giờ thì ưu tiên truyền một đối tượng temporal từ driver thay vì chuyển đi chuyển lại qua chuỗi.

## 12. Java Driver và Spring Data Neo4j: ánh xạ thời gian

### 12.1. Truyền kiểu java.time qua Java Driver

Thư viện `java.time` của Java cung cấp các kiểu gần với ngữ nghĩa temporal của Neo4j:

| Ý nghĩa | Kiểu Java thường dùng | Kiểu Cypher |
| --- | --- | --- |
| Ngày lịch | `LocalDate` | `DATE` |
| Giờ không có offset | `LocalTime` | `LOCAL TIME` |
| Giờ kèm offset | `OffsetTime` | `ZONED TIME` |
| Ngày giờ không có timezone | `LocalDateTime` | `LOCAL DATETIME` |
| Ngày giờ có timezone | `ZonedDateTime` / `OffsetDateTime` | `ZONED DATETIME` |
| Thời lượng | `Duration` hoặc `Period` tùy loại | `DURATION` |

`Duration` của Java biểu diễn thời lượng dựa trên giây/nanosecond; `Period` biểu diễn các thành phần năm/tháng/ngày. Đừng tùy tiện chuyển `Period.ofMonths(1)` thành một số giây cố định.

Ví dụ truyền một `ZonedDateTime` qua map tham số:

```java
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public class TemporalEventWriter {
    public static void saveEvent(Driver driver) {
        ZonedDateTime occurredAt = ZonedDateTime.of(
            2026, 11, 25, 9, 30, 0, 0,
            ZoneId.of("Asia/Ho_Chi_Minh")
        );

        String cypher = """
            MERGE (e:TemporalDemoEvent {eventId: $eventId})
            SET e.occurredAt = $occurredAt
            RETURN e.eventId
            """;

        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run(cypher, Map.of(
                    "eventId", "EV-001",
                    "occurredAt", occurredAt
                )).consume();
                return null;
            });
        }
    }
}
```

Trong thực tế, cần unique constraint trên `eventId` khi muốn đảm bảo định danh sự kiện duy nhất khi có các request đồng thời. Đoạn Java minh họa cơ chế parameter binding; việc cấu hình Driver, authentication và xử lý lỗi là trách nhiệm ứng dụng.

Đọc giá trị temporal có kiểu:

```java
// Với truy vấn RETURN e.occurredAt AS occurredAt:
ZonedDateTime eventTime =
    record.get("occurredAt").asZonedDateTime();
```

Biến `record` ở ví dụ thứ hai giả định đã nhận từ kết quả truy vấn Java Driver và cột `occurredAt` có giá trị không null thuộc kiểu phù hợp. Nếu property có thể thiếu, cần kiểm tra `record.get("occurredAt").isNull()` trước khi đọc.

### 12.2. Khi dùng Spring Data Neo4j

Với Spring Data Neo4j, có thể khai báo property thời gian trên entity bằng các kiểu `java.time` thích hợp. Tùy phiên bản framework, cấu hình converter và mapping, cần kiểm tra rằng kiểu Java được ánh xạ sang kiểu Neo4j mong muốn.

Ví dụ một trường trên entity Java:

```java
import java.time.LocalDate;
import java.time.ZonedDateTime;

public class CourseTimeFields {
    private LocalDate publishedOn;
    private ZonedDateTime updatedAt;

    // Getter/setter hoặc cấu hình entity phù hợp dự án.
}
```

Đây là **minh họa lựa chọn kiểu trường**, chưa phải một entity Spring Data Neo4j đầy đủ. Các annotation và phương thức lưu dữ liệu phụ thuộc mô hình entity trong ứng dụng. Cần tránh chuyển toàn bộ trường thời gian thành `String` nếu hệ thống cần so sánh, cộng thời lượng hoặc tìm kiếm theo khoảng.

Khi thiết kế JSON API, thường nên xuất ngày giờ theo ISO 8601, gồm offset hoặc vùng thích hợp. Nếu client chỉ cần ngày, trả `YYYY-MM-DD` để tránh nhầm sang thời điểm cụ thể.

## 13. Tình huống thực tế: nhật ký sự kiện và hạn xử lý

Một hệ thống học tập cần ghi lại sự kiện bắt đầu phiên học. Từ đó tính hạn hoàn thành sau 90 phút và tìm các phiên quá hạn.

### 13.1. Tạo sự kiện mẫu

```cypher
CREATE (e:TemporalDemoEvent {
  eventId: 'EV-001',
  startedAt: datetime('2026-11-25T09:00:00+07:00'),
  allowedDuration: duration('PT90M')
})
SET e.dueAt = e.startedAt + e.allowedDuration
RETURN e.eventId, e.startedAt, e.allowedDuration, e.dueAt;
```

`startedAt` và `dueAt` là **mốc thời gian có offset**; `allowedDuration` là **độ dài thời gian**. Lưu `dueAt` sẽ thuận tiện cho truy vấn quá hạn, nhưng cần duy trì tính nhất quán khi sửa `startedAt` hoặc `allowedDuration`.

### 13.2. Tìm các phiên đã đến hạn

```cypher
WITH datetime('2026-11-25T11:00:00+07:00') AS checkAt
MATCH (e:TemporalDemoEvent)
WHERE e.dueAt IS NOT NULL
  AND e.dueAt <= checkAt
RETURN e.eventId, e.dueAt
ORDER BY e.dueAt;
```

Ví dụ dùng `checkAt` cố định để có thể tự đối chiếu kết quả. Khi triển khai, thay bằng tham số do ứng dụng cung cấp hoặc gọi hàm lấy thời gian hiện tại theo chính sách hệ thống.

### 13.3. Phân biệt ngày hạn với thời điểm hạn

Nếu quy tắc là “nộp trước cuối ngày 25-11-2026 theo múi giờ người học”, một property `DATE` như `dueOn` **không tự chỉ rõ thời điểm hết hạn**. Ứng dụng cần biết timezone của người học và quy định “cuối ngày” theo lịch tương ứng trước khi tính thời điểm khóa nộp bài.

Nếu quy tắc là “90 phút kể từ khi bắt đầu phiên”, dùng `ZONED DATETIME` kết hợp `DURATION` biểu thị thời lượng phút/giây sẽ rõ ràng hơn.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Rủi ro | Cách giải quyết |
| --- | --- | --- |
| Lưu `'2026-11-25'` như `STRING` cho mọi trường ngày | Khó kiểm soát tính hợp lệ và phép tính ngày | Dùng `DATE` khi dữ liệu là ngày lịch |
| Dùng `LOCAL DATETIME` để ghi thời điểm toàn cầu | Không có timezone để xác định mốc duy nhất | Dùng `ZONED DATETIME` kèm offset hoặc zone |
| Chỉ lưu `09:00` để xác định một sự kiện đã xảy ra | Thiếu ngày và timezone | Dùng `ZONED DATETIME` cho thời điểm |
| Xem `+07:00` và `Asia/Ho_Chi_Minh` là hai khái niệm như nhau | Mất thông tin quy tắc vùng, nhất là ở vùng có DST | Phân biệt fixed offset với timezone ID |
| Cho rằng `P1M` nghĩa là một phút | `M` trước `T` là tháng | Dùng `PT1M` cho một phút |
| Cho rằng một tháng luôn 30 ngày | Sai ở nhiều tháng, năm nhuận | Sử dụng lịch và quy tắc nghiệp vụ |
| Dùng `LOCAL DATETIME` cho giờ DST mơ hồ mà không có zone | Không xác định mốc UTC duy nhất | Xác định vùng và cách xử lý giờ lặp/không tồn tại |
| Dùng cận trên `23:59:59` khi lọc một ngày | Bỏ sót phần nhỏ giây cuối ngày | Dùng khoảng nửa mở đến 00:00 ngày sau |
| Chuyển đổi `date('2026-02-29')` | Ngày không có thật | Kiểm tra ngày hợp lệ, xử lý lỗi nhập |
| Mặc định `SET e.at = null` là “không cập nhật” | Neo4j xóa property | Phân biệt giữ nguyên và xóa trường |
| Tính `DATEDIFF` bằng phép chia số tháng cho ngày cố định | Không bảo toàn ngữ nghĩa lịch | Dùng `duration.between` / `duration.inDays` theo yêu cầu |
| So sánh `STRING` với temporal và mong tự chuyển kiểu | Kết quả/lỗi không theo mong đợi | Chuẩn hóa cùng kiểu trước khi so sánh |

## 15. Bài tập thực hành và đáp án

### Bài 1 — Chọn kiểu dữ liệu

Chọn kiểu thích hợp cho bốn trường:

1. Ngày sinh của người học.
2. Giờ bắt đầu ca làm việc tại cửa hàng.
3. Thời điểm hệ thống xác nhận giao dịch.
4. Thời lượng video hướng dẫn 75 phút.

**Đáp án:** lần lượt là `DATE`, `LOCAL TIME`, `ZONED DATETIME` và `DURATION`. Với ca làm việc, còn phải quản lý timezone hoặc ngữ cảnh cửa hàng ở cấp ứng dụng/mô hình.

### Bài 2 — Tạo ngày giờ có offset

Tạo giá trị ngày 25-11-2026 lúc 09:30 với offset UTC+07:

```cypher
RETURN datetime('2026-11-25T09:30:00+07:00') AS eventAt;
```

### Bài 3 — Tính hạn sau ba ngày

Cho `startedOn = date('2026-11-25')`, tính ngày đến hạn sau ba ngày lịch.

**Đáp án:**

```cypher
WITH date('2026-11-25') AS startedOn
RETURN startedOn + duration('P3D') AS dueOn;
```

Kết quả: `2026-11-28`.

### Bài 4 — Tính thời lượng cuộc họp

Cuộc họp bắt đầu lúc 14:00, kết thúc 15:45 cùng ngày và cùng offset UTC+07. Tính thời lượng:

```cypher
WITH
  datetime('2026-11-25T14:00:00+07:00') AS startedAt,
  datetime('2026-11-25T15:45:00+07:00') AS finishedAt
RETURN duration.between(startedAt, finishedAt) AS meetingLength;
```

Kết quả tương đương **1 giờ 45 phút**.

### Bài 5 — Tìm sự kiện trong một ngày

Viết điều kiện lọc các node `TemporalDemoEvent` có `occurredAt` nằm trong ngày 25-11-2026 theo UTC+07.

**Đáp án:**

```cypher
MATCH (e:TemporalDemoEvent)
WHERE e.occurredAt >= datetime('2026-11-25T00:00:00+07:00')
  AND e.occurredAt < datetime('2026-11-26T00:00:00+07:00')
RETURN e.eventId, e.occurredAt;
```

### Bài 6 — Giải thích DST

Vì sao lưu duy nhất `localdatetime('2026-10-25T02:30:00')` không đủ để xác định thời điểm của một cuộc họp tại khu vực đổi giờ mùa hè?

**Đáp án:** vì `LOCAL DATETIME` không mang thông tin timezone, và trong một số vùng/ngày chuyển DST, giờ 02:30 có thể xuất hiện hai lần với hai offset khác nhau. Cần định danh vùng cùng quy tắc xử lý mốc giờ mơ hồ, hoặc lưu thời điểm đã xác định dưới dạng `ZONED DATETIME`.

## 16. Checklist triển khai temporal trong Neo4j

1. Trường này biểu thị **ngày**, **giờ lặp theo lịch**, **thời điểm sự kiện**, hay **thời lượng**?
2. Đã chọn `DATE`, `LOCAL TIME`, `ZONED DATETIME` hoặc `DURATION` theo ngữ nghĩa chưa?
3. Với ngày giờ người dùng nhập, timezone/offset lấy ở đâu và được xác thực thế nào?
4. Ứng dụng có hỗ trợ các trường hợp DST chuyển giờ không?
5. Thời lượng nghiệp vụ là tháng/ngày lịch hay số giờ/giây thực?
6. Dữ liệu từ CSV/API đã được chuyển thành kiểu temporal trước khi ghi chưa?
7. Điều kiện truy vấn theo ngày có dùng khoảng `[start, end)` thay vì tự đoán thời điểm cuối ngày không?
8. Trường thời gian được ánh xạ sang kiểu `java.time` phù hợp khi dùng Java Driver/Spring Data Neo4j chưa?
9. Các bản cập nhật có phân biệt “không gửi giá trị” với “gửi null để xóa property” không?
10. Với truy vấn thời gian trên lượng dữ liệu lớn, đã xem `EXPLAIN`/`PROFILE` và cân nhắc range index chưa?

---

**Ghi nhớ:** `DATE` diễn tả ngày lịch; `LOCAL TIME` và `LOCAL DATETIME` không chứa timezone; `ZONED TIME` và `ZONED DATETIME` mang thông tin offset/zone phù hợp; `DURATION` diễn tả khoảng thời gian. Khi lưu và truy vấn dữ liệu liên kết trong Neo4j, hãy tách bạch **mốc thời gian**, **giờ theo lịch** và **thời lượng**, xử lý rõ ngữ nghĩa múi giờ/DST, và dùng kiểu temporal cùng tham số hóa để truy vấn Cypher nhất quán.
