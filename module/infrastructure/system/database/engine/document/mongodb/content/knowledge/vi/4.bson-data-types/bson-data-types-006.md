# Date, Timestamp, múi giờ và biểu diễn thời gian trong MongoDB

## 1. Vì sao dữ liệu thời gian cần được mô hình hóa cẩn thận?

Trong ứng dụng thực tế, thời gian xuất hiện ở nhiều nghiệp vụ: thời điểm tạo tài khoản, lúc đặt hàng, ngày giao hàng, lịch hẹn, phiên đăng nhập, thời hạn khuyến mãi, log hệ thống và lịch sử thay đổi dữ liệu. Các giá trị này thoạt nhìn đều là “ngày giờ”, nhưng không nhất thiết có cùng ý nghĩa.

Ví dụ:

- “Đơn hàng được tạo lúc **08:30 ngày 14/11/2026 ở Việt Nam**” là một **thời điểm xác định** trên trục thời gian.
- “Hạn nộp hồ sơ là **ngày 14/11/2026**” có thể là một **ngày theo lịch**, chưa xác định giờ cụ thể.
- “Cửa hàng mở lúc **09:00 mỗi ngày**” là một **giờ địa phương lặp lại**, cần thêm múi giờ và quy tắc lịch.
- “Phiên bản sự kiện trong oplog” là thông tin dùng để sắp thứ tự sự kiện nội bộ, không nhất thiết là thời điểm nghiệp vụ mà người dùng nhìn thấy.

MongoDB cung cấp nhiều cách biểu diễn thời gian. Trong phần **BSON và kiểu dữ liệu**, hai kiểu đặc biệt cần phân biệt là **BSON Date** và **BSON Timestamp**. Sau đó, ta phải giải quyết vấn đề **múi giờ** và **định dạng hiển thị** ở tầng ứng dụng hoặc trong phép biến đổi truy vấn.

Mục tiêu của bài học:

1. Hiểu giá trị và giới hạn của BSON Date, BSON Timestamp.
2. Tạo, lưu, đọc và so sánh ngày giờ trong `mongosh`.
3. Phân biệt UTC, độ lệch UTC và tên múi giờ IANA.
4. Lọc dữ liệu theo khoảng thời gian, đặc biệt theo **ngày địa phương**.
5. Biết dùng toán tử MongoDB để parse, format, trích xuất, cộng/trừ và nhóm theo thời gian.
6. Tránh lỗi nhầm giây với mili giây, nhầm ngày địa phương với ngày UTC hoặc lưu thời gian thành chuỗi không thống nhất.

## 2. Mô hình tư duy: thời điểm, ngày theo lịch và múi giờ

### 2.1. Thời điểm tuyệt đối (instant)

Một **instant** là một điểm xác định trên trục thời gian. Cùng một instant có nhiều cách biểu diễn tùy múi giờ:

```text
2026-11-14 01:30:00 UTC
           ||
2026-11-14 08:30:00 Asia/Ho_Chi_Minh (UTC+07:00)
           ||
2026-11-14T08:30:00+07:00
           ||
2026-11-14T01:30:00Z
```

Các giá trị này chỉ **cùng một instant**. Chữ `Z` là ký hiệu của UTC (độ lệch `+00:00`), còn `+07:00` cho biết giờ hiển thị đi trước UTC bảy tiếng. Ở thời điểm ví dụ, `Asia/Ho_Chi_Minh` sử dụng độ lệch UTC+07:00.

**BSON Date** phù hợp để lưu instant. Giá trị Date không mang riêng tên múi giờ hay định dạng ban đầu; việc hiển thị “01:30 UTC” hay “08:30 ở Việt Nam” là cách diễn giải khi đọc.

### 2.2. Ngày theo lịch (calendar date)

Giá trị như `2026-11-14` chỉ xác định một ngày theo lịch. Nếu nghiệp vụ không có khái niệm giờ, việc tự gán nửa đêm UTC có thể gây nhầm lẫn: khi hiển thị ở múi giờ khác, ngày có thể thay đổi.

Ví dụ ngày sinh, ngày lễ, ngày chốt công hoặc ngày đến hạn đôi khi nên được lưu như chuỗi chuẩn `YYYY-MM-DD` hoặc dưới cấu trúc năm–tháng–ngày có quy ước rõ, thay vì giả vờ đây là một instant. Nếu nghiệp vụ cần cả thời điểm đến hạn, phải nêu múi giờ áp dụng cho ranh giới ngày đó.

### 2.3. Giờ địa phương lặp lại (local wall time)

“09:00 sáng thứ Hai hằng tuần ở Hà Nội” chưa phải một instant vì còn thiếu **ngày cụ thể**. Với lịch lặp lại, nên lưu thông tin như:

```javascript
{
  schedule: {
    localTime: "09:00",
    weekdays: ["MON"],
    timeZone: "Asia/Ho_Chi_Minh"
  }
}
```

Ứng dụng sau đó tính instant cho từng lần diễn ra. Cách này đặc biệt quan trọng tại các vùng áp dụng quy tắc giờ mùa hè (DST), nơi độ lệch UTC có thể thay đổi theo ngày.

## 3. BSON Date: một thời điểm tính bằng mili giây từ Unix epoch

### 3.1. BSON Date thực sự lưu gì?

BSON Date là một số nguyên **64 bit có dấu**, biểu diễn **số mili giây** trước hoặc sau Unix epoch `1970-01-01T00:00:00Z`.

```text
Unix epoch:         1970-01-01T00:00:00.000Z
                     |
                     + 1000 milliseconds = 1 second
                     |
Date value: milliseconds since epoch (signed 64-bit)
```

Điểm cần nhớ:

- Độ phân giải của BSON Date là **mili giây**, không phải nano giây.
- Giá trị có thể âm với instant trước epoch; không chỉ dành cho ngày hiện đại.
- MongoDB lưu thời điểm trên trục UTC; **không lưu kèm tên múi giờ** như `Asia/Ho_Chi_Minh` trong chính giá trị BSON Date.
- Trong `mongosh`, BSON Date thường được hiển thị bằng `ISODate("...Z")`. Đây là cách trình bày thân thiện; bản lưu trữ là giá trị BSON Date.
- Phạm vi giá trị BSON 64 bit rộng hơn phạm vi một số API ngày giờ ở client. Ví dụ, đối tượng JavaScript `Date` bị giới hạn bởi khoảng thời gian mà runtime hỗ trợ; không nên cho rằng mọi giá trị BSON Date đều tạo được thành một JavaScript Date hợp lệ.

### 3.2. Tạo Date trong `mongosh`

```javascript
// Lấy thời điểm hiện tại theo đồng hồ máy đang chạy mongosh.
const now = new Date();

// Viết rõ instant theo UTC.
const inUtc = ISODate("2026-11-14T01:30:00.000Z");

// Viết cùng instant bằng độ lệch UTC+07:00.
const inVietnam = ISODate("2026-11-14T08:30:00+07:00");

print(inUtc.getTime() === inVietnam.getTime()); // true
print(inVietnam.toISOString()); // 2026-11-14T01:30:00.000Z

// Giá trị số này là mili giây tính từ epoch.
print(inUtc.getTime());
```

`new Date()` tạo thời gian hiện tại dựa trên đồng hồ của **máy client chạy JavaScript**. `Date.now()` chỉ trả về **số mili giây**, chứ không tự trả về đối tượng BSON Date. Khi muốn ghi một trường ngày giờ, nên dùng một Date phù hợp thay vì lưu nhầm một con số không có quy ước kiểu.

**Cảnh báo về chuỗi thiếu thông tin múi giờ:** tránh viết `new Date("2026-11-14 08:30:00")` rồi trông đợi kết quả giống nhau trên mọi runtime. Dùng chuỗi ISO 8601 có `Z` hoặc độ lệch rõ ràng, hoặc parse theo múi giờ được chỉ định bằng thư viện/ngữ cảnh thích hợp.

### 3.3. Lưu và đọc BSON Date

Các lệnh sau dùng một database thử nghiệm riêng là `bson_time_lab`. Hãy chỉ chạy trên môi trường MongoDB mà bạn được phép ghi dữ liệu.

```javascript
const lab = db.getSiblingDB("bson_time_lab");
const events = lab.getCollection("events");
const runId = "time54-" + new ObjectId().toHexString();

const inserted = events.insertOne({
  runId: runId,
  eventType: "check-in",
  occurredAt: ISODate("2026-11-14T08:30:00+07:00"),
  createdAt: new Date(),
  sourceTimeZone: "Asia/Ho_Chi_Minh"
});

printjson(events.findOne({ _id: inserted.insertedId, runId: runId }));
```

Khi đọc document, trường `occurredAt` là BSON Date tương ứng instant `2026-11-14T01:30:00.000Z`. Chuỗi `sourceTimeZone` được lưu **riêng** vì BSON Date không nhớ rằng đầu vào ban đầu có `+07:00`. Nếu ứng dụng cần hiển thị theo múi giờ của nơi phát sinh sự kiện, việc lưu múi giờ gốc có thể là một quyết định nghiệp vụ đúng đắn.

MongoDB hỗ trợ nhiều kiểu dữ liệu cùng một collection; vì vậy cần tránh ghi `occurredAt` lúc là BSON Date, lúc là chuỗi ngày giờ. Hai giá trị trông giống nhau trên màn hình chưa chắc có cùng kiểu dữ liệu và hành vi so sánh.

## 4. BSON Timestamp: giây và bộ đếm, thường phục vụ cơ chế nội bộ

### 4.1. Cấu trúc khác BSON Date

**BSON Timestamp** là một kiểu BSON riêng biệt với BSON Date. Nó gồm hai phần 32 bit:

| Phần | Ý nghĩa |
| --- | --- |
| `t` | Phần thời gian, biểu diễn giây tính từ Unix epoch |
| `i` | Bộ đếm/tăng dần (*increment*) dùng để phân biệt hoặc sắp thứ tự các sự kiện trong cùng đơn vị thời gian |

Khái niệm:

```text
BSON Timestamp (64 bit)
┌──────────────────────────┬──────────────────────────┐
│  t: seconds (32 bits)    │  i: increment (32 bits)  │
└──────────────────────────┴──────────────────────────┘
```

MongoDB sử dụng kiểu Timestamp trong một số cơ chế nội bộ, điển hình là các vị trí thời gian trong **oplog** phục vụ replication. Bộ đếm `i` không đại diện cho mili giây, micro giây hoặc phần thập phân của giây. Hai Timestamp có thể chứa cùng `t` nhưng khác `i`.

Ví dụ thao tác trong `mongosh`:

```javascript
const ts1 = Timestamp({ t: 1760000000, i: 1 });
const ts2 = Timestamp({ t: 1760000000, i: 2 });
printjson(ts1);
printjson(ts2);
```

Ví dụ trên minh họa **cách tạo giá trị BSON Timestamp**, không phải khuyến nghị tự cấp Timestamp cho thời điểm tạo đơn hàng. Để lưu ngày giờ nghiệp vụ và lọc theo thời gian thông thường, **ưu tiên BSON Date**.

### 4.2. Vì sao không thay Date bằng Timestamp?

| Tiêu chí | BSON Date | BSON Timestamp |
| --- | --- | --- |
| Mục đích phổ biến | Thời điểm nghiệp vụ: tạo, cập nhật, thanh toán, hết hạn | Dấu mốc thứ tự/thời gian cho cơ chế MongoDB nội bộ |
| Độ phân giải | Mili giây | Phần thời gian ở cấp giây; phần `i` là bộ đếm |
| Cấu trúc | Một giá trị 64 bit có dấu chứa số mili giây từ epoch | Hai thành phần `t` và `i`, mỗi thành phần 32 bit |
| Lưu múi giờ trong giá trị? | Không | Không |
| Dùng cho lịch hẹn, hóa đơn, báo cáo theo ngày? | Thường phù hợp | Không nên dùng thay thế Date |
| Dùng trong oplog? | Có thể có các trường Date ở metadata khác | Timestamp có vai trò đặc biệt |

**Một Timestamp không có ý nghĩa “chính xác hơn Date”.** Nếu đọc `Timestamp({ t: ..., i: 7 })` rồi coi `i = 7` là 7 mili giây sẽ làm sai dữ liệu.

### 4.3. Hai dạng Extended JSON cũng khác nhau

Khi đi qua file JSON hoặc API xuất/nhập dữ liệu, MongoDB có cách biểu diễn đặc biệt gọi là **Extended JSON** (*EJSON*). Ví dụ:

```json
{
  "createdAt": {
    "$date": "2026-11-14T01:30:00.000Z"
  },
  "oplogPosition": {
    "$timestamp": {
      "t": 1760000000,
      "i": 7
    }
  }
}
```

Đây là dạng minh họa EJSON *relaxed* cho Date trong phạm vi thời gian phổ biến và cấu trúc đặc thù cho Timestamp. Dạng *canonical* của Date có thể sử dụng `{"$date":{"$numberLong":"..."}}` để biểu diễn chính xác giá trị mili giây. Cả hai đều khác JSON chuỗi thường và giúp giữ thông tin **kiểu BSON** khi xuất/nhập đúng cách.

Không nên coi `{"$date":"..."}` là một document lồng nhau thông thường nếu đang xử lý EJSON; phần ký hiệu này có ý nghĩa kiểu dữ liệu trong ngữ cảnh giải mã Extended JSON.

## 5. UTC, UTC offset và múi giờ IANA

### 5.1. Ba khái niệm dễ nhầm

**UTC** là hệ tham chiếu thời gian dùng để xác định instant. **UTC offset** là độ lệch tại một thời điểm, ví dụ `+07:00`. **Múi giờ IANA** như `Asia/Ho_Chi_Minh` hoặc `America/New_York` là tên vùng chứa các quy tắc lịch sử và hiện hành về độ lệch UTC, kể cả thay đổi giờ mùa hè ở một số nơi.

| Biểu diễn | Mô tả | Có đủ để tính giờ địa phương trong tương lai không? |
| --- | --- | --- |
| `2026-11-14T01:30:00Z` | Instant theo UTC | Có instant, nhưng chưa biết người dùng muốn hiển thị ở vùng nào |
| `2026-11-14T08:30:00+07:00` | Instant kèm offset tại lúc biểu diễn | Không mô tả đầy đủ quy tắc múi giờ qua các năm |
| `Asia/Ho_Chi_Minh` | Tên vùng múi giờ IANA | Cần đi kèm instant/ngày và giờ để xác định kết quả cụ thể |
| `2026-11-14 08:30` | Giờ địa phương chưa kèm offset hoặc vùng | Không đủ để xác định instant duy nhất |

Ở Việt Nam, múi giờ hiện hành là UTC+07:00 và hiện không áp dụng DST. Tuy vậy, với các hệ thống đa quốc gia, không nên gán một độ lệch cố định cho mọi vùng và mọi ngày. Ví dụ `America/New_York` có thể dùng UTC−05:00 hoặc UTC−04:00 tùy thời điểm trong năm.

### 5.2. Nguyên tắc lưu trữ và hiển thị

Với một **sự kiện đã xảy ra**, thường lưu:

```javascript
{
  occurredAt: ISODate("2026-11-14T01:30:00Z"),
  sourceTimeZone: "Asia/Ho_Chi_Minh"
}
```

Trong đó:

- `occurredAt` dùng để so sánh chính xác, sắp xếp, đặt index, tính khoảng thời gian.
- `sourceTimeZone` chỉ lưu khi nghiệp vụ cần biết vùng địa lý hoặc cách hiển thị theo nơi phát sinh sự kiện.
- Nếu cần giữ nguyên cách nhập ban đầu vì yêu cầu kiểm toán, có thể lưu riêng chuỗi/offset gốc có chủ đích; không nên bắt các trường này thay thế instant chính.

Với **lịch tương lai hoặc lịch lặp lại**, thường lưu giờ địa phương, ngày/quy tắc lịch và tên múi giờ. Sau đó mới xác định instant của từng lần hẹn. Tại nơi có DST, một giờ địa phương có thể không tồn tại trong ngày chuyển giờ hoặc xuất hiện hai lần; nghiệp vụ phải có chính sách xử lý trường hợp đó.

### 5.3. Chú ý múi giờ khi hiển thị

MongoDB không tự chọn múi giờ hiển thị phù hợp cho mọi người dùng. Shell thường thể hiện Date dưới dạng UTC, còn ứng dụng web/mobile có thể format theo múi giờ thiết bị, múi giờ tài khoản hoặc múi giờ nghiệp vụ.

Ví dụ cùng BSON Date:

```text
UTC:                 2026-11-14 01:30
Asia/Ho_Chi_Minh:    2026-11-14 08:30
```

Nếu một màn hình hiển thị “01:30” và màn hình khác hiển thị “08:30”, trước tiên cần kiểm tra **quy tắc format và múi giờ đầu ra**, không mặc định dữ liệu trong database sai.

## 6. Lọc theo thời gian: khoảng nửa mở và ranh giới ngày

### 6.1. Khoảng thời gian [bắt đầu, kết thúc)

Khi lọc các sự kiện trong một khoảng, cách diễn đạt rõ ràng là:

```text
start <= occurredAt < end
```

Trong MongoDB:

```javascript
const lab = db.getSiblingDB("bson_time_lab");
const events = lab.getCollection("events");

const start = ISODate("2026-11-14T00:00:00Z");
const end = ISODate("2026-11-15T00:00:00Z");

events.find({
  occurredAt: {
    $gte: start,
    $lt: end
  }
});
```

Sử dụng `$gte` (lớn hơn hoặc bằng) với mốc đầu và `$lt` (nhỏ hơn) với mốc cuối giúp các khoảng liên tiếp không bị đếm trùng ở điểm giao. Không cần tự tìm “mili giây cuối cùng của ngày” bằng `23:59:59.999`; cách đó dễ gây lỗi khi chuyển kiểu hoặc thay đổi độ phân giải.

### 6.2. Ngày địa phương tại Việt Nam khác ngày UTC

Giả sử báo cáo yêu cầu **mọi sự kiện trong ngày 14/11/2026 theo giờ Việt Nam**. Khoảng địa phương là:

```text
[2026-11-14T00:00:00+07:00,
 2026-11-15T00:00:00+07:00)
```

Đổi sang UTC:

```text
[2026-11-13T17:00:00Z,
 2026-11-14T17:00:00Z)
```

Truy vấn MongoDB:

```javascript
events.find({
  occurredAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
});
```

Tương đương có thể viết trực tiếp bằng chuỗi ISO kèm offset:

```javascript
events.find({
  occurredAt: {
    $gte: ISODate("2026-11-14T00:00:00+07:00"),
    $lt: ISODate("2026-11-15T00:00:00+07:00")
  }
});
```

Cả hai đều mô tả cùng một khoảng. Nếu lọc bằng `2026-11-14T00:00:00Z` đến `2026-11-15T00:00:00Z`, ta đang chọn **ngày UTC**, bao gồm 07:00 ngày 14/11 đến 07:00 ngày 15/11 theo giờ Việt Nam, và do đó trả về kết quả khác.

### 6.3. Vùng có DST: không luôn cộng thêm 24 giờ

Với múi giờ có chuyển giờ mùa hè, một ngày địa phương có thể dài **23 giờ hoặc 25 giờ**. Khi lấy báo cáo theo ngày ở vùng như `America/New_York`, cần tính mốc đầu và cuối theo **hai nửa đêm địa phương** với múi giờ đó, rồi đổi thành instant. Không mặc định `end = start + 24 giờ`.

Trong ứng dụng, một thư viện thời gian có hỗ trợ IANA time zone có thể giúp tạo hai ranh giới chính xác. Ở phía MongoDB, các toán tử như `$dateFromString`, `$dateTrunc` và `$dateAdd` có tham số `timezone` để làm việc theo lịch địa phương.

### 6.4. Index cho truy vấn khoảng thời gian

Nếu tập dữ liệu có nhiều document và lọc theo `occurredAt` thường xuyên, có thể tạo index:

```javascript
events.createIndex({ occurredAt: 1 });

events.find({
  occurredAt: {
    $gte: ISODate("2026-11-14T00:00:00+07:00"),
    $lt: ISODate("2026-11-15T00:00:00+07:00")
  }
}).sort({ occurredAt: 1 });
```

Đối với các truy vấn có thêm điều kiện `userId`, `tenantId` hoặc `status`, có thể cân nhắc index ghép dựa trên truy vấn thực tế. Mục tiêu là dùng phép so sánh trực tiếp trên trường BSON Date đã được index, tránh phải chuyển toàn bộ giá trị ngày sang chuỗi rồi mới lọc.

## 7. Parse, format và biến đổi thời gian trong aggregation

MongoDB hỗ trợ nhiều toán tử biểu thức ngày giờ. Các ví dụ dưới đây minh họa những thao tác thường gặp khi tổng hợp dữ liệu.

### 7.1. `$dateToString`: hiển thị Date theo múi giờ

```javascript
db.getSiblingDB("bson_time_lab").events.aggregate([
  {
    $project: {
      _id: 0,
      occurredAt: 1,
      timeInVietnam: {
        $dateToString: {
          format: "%Y-%m-%d %H:%M:%S",
          date: "$occurredAt",
          timezone: "Asia/Ho_Chi_Minh",
          onNull: null
        }
      }
    }
  }
]);
```

Nếu `occurredAt` là `ISODate("2026-11-14T01:30:00Z")`, `timeInVietnam` sẽ là chuỗi `"2026-11-14 08:30:00"`. Trường kết quả là **string** để hiển thị; trường `occurredAt` gốc vẫn là BSON Date.

Định dạng như `%Y`, `%m`, `%d`, `%H`, `%M`, `%S` là các chỉ thị format của MongoDB. Khi tạo chuỗi hiển thị, cần thống nhất cách dùng múi giờ của ứng dụng.

### 7.2. `$dateFromString`: parse ngày giờ từ chuỗi

Giả sử nguồn dữ liệu nhận được giờ địa phương `"2026-11-14 08:30:00"` và biết đây là giờ Việt Nam:

```javascript
db.getSiblingDB("bson_time_lab").getCollection("imports").aggregate([
  {
    $project: {
      eventAt: {
        $dateFromString: {
          dateString: "$localDateTime",
          format: "%Y-%m-%d %H:%M:%S",
          timezone: "Asia/Ho_Chi_Minh",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Ví dụ giả định collection `imports` có trường `localDateTime` chứa đúng định dạng chuỗi trên. Kết quả `eventAt` là Date tương ứng `2026-11-14T01:30:00Z`.

Nếu chuỗi đầu vào đã chứa ký hiệu múi giờ/offset theo định dạng được parser nhận diện, không chỉ định thêm `timezone` mâu thuẫn với thông tin đó. `onError` hữu ích để xử lý dữ liệu bẩn mà không khiến toàn bộ pipeline dừng vì một giá trị parse thất bại; tuy vậy ứng dụng cần thống kê và xử lý các dòng lỗi thay vì im lặng bỏ qua.

### 7.3. `$dateTrunc`: nhóm sự kiện theo ngày địa phương

Ví dụ đếm số sự kiện theo **ngày Việt Nam**:

```javascript
db.getSiblingDB("bson_time_lab").events.aggregate([
  {
    $match: {
      occurredAt: { $type: "date" }
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
      total: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Kết quả `_id` của `$dateTrunc` vẫn là **BSON Date**, đại diện instant tương ứng **đầu ngày địa phương**. Vì thế, đầu ngày 14/11/2026 tại Việt Nam có thể hiển thị trong shell dưới dạng `2026-11-13T17:00:00Z`; đây không phải lỗi một ngày, mà là cùng một ranh giới được trình bày theo UTC.

Nếu báo cáo chỉ cần nhãn ngày theo lịch, có thể dùng thêm `$dateToString` với cùng `timezone` để tạo nhãn `YYYY-MM-DD`.

### 7.4. `$dateAdd`, `$dateSubtract` và `$dateDiff`

MongoDB hỗ trợ cộng, trừ và tính chênh lệch các đơn vị thời gian trong aggregation. Ví dụ tính thời điểm của **ngày kế tiếp theo lịch địa phương**:

```javascript
db.getSiblingDB("bson_time_lab").events.aggregate([
  {
    $project: {
      occurredAt: 1,
      nextLocalDay: {
        $dateAdd: {
          startDate: "$occurredAt",
          unit: "day",
          amount: 1,
          timezone: "America/New_York"
        }
      }
    }
  }
]);
```

Ở vùng có DST, cộng một **ngày lịch** theo múi giờ có thể cho ra khoảng mili giây khác 24 giờ. Ngược lại, nếu yêu cầu thực sự là “sau đúng 24 giờ tính từ sự kiện”, hãy biểu đạt theo đơn vị giờ hoặc khoảng thời gian tuyệt đối thích hợp. `$dateDiff` hữu ích khi cần tính số ranh giới đơn vị thời gian giữa hai Date, nhưng phải đọc đúng ý nghĩa của `unit` và `timezone`; kết quả ngày lịch không luôn đồng nghĩa số mili giây chia cho 86.400.000.

### 7.5. Trích xuất năm, tháng, ngày theo múi giờ

```javascript
db.getSiblingDB("bson_time_lab").events.aggregate([
  {
    $project: {
      yearVN: {
        $year: { date: "$occurredAt", timezone: "Asia/Ho_Chi_Minh" }
      },
      monthVN: {
        $month: { date: "$occurredAt", timezone: "Asia/Ho_Chi_Minh" }
      },
      dayVN: {
        $dayOfMonth: {
          date: "$occurredAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
```

Nếu không chỉ định `timezone`, nhiều toán tử ngày giờ dùng UTC làm mặc định. Vì thế các báo cáo thống kê theo ngày/tháng của người dùng ở nhiều vùng phải nêu rõ múi giờ áp dụng.

## 8. Chuỗi ISO 8601, EJSON và timestamp dạng số

Trong quá trình đi từ client → API → MongoDB → báo cáo, cùng một instant có thể xuất hiện ở nhiều hình thức.

| Hình thức | Ví dụ | Kiểu/ý nghĩa | Lưu ý |
| --- | --- | --- | --- |
| BSON Date | `ISODate("2026-11-14T01:30:00Z")` trong shell | Instant, mili giây | Dùng cho trường ngày giờ nghiệp vụ |
| ISO 8601 UTC | `"2026-11-14T01:30:00.000Z"` | Chuỗi | Có thể parse thành Date, nhưng tự lưu chuỗi không biến nó thành BSON Date |
| ISO 8601 có offset | `"2026-11-14T08:30:00+07:00"` | Chuỗi có thông tin offset | Tương ứng cùng instant với ví dụ UTC |
| Unix time (seconds) | Số giây từ 1970-01-01 UTC | Number | Phổ biến trong API/log, cần biết đơn vị |
| Unix time (milliseconds) | Số mili giây từ epoch | Number | Trùng đơn vị với BSON Date nhưng kiểu Number khác Date |
| Extended JSON Date | `{"$date":"2026-11-14T01:30:00Z"}` | Ký hiệu có kiểu trong EJSON | Nên dùng parser EJSON tương ứng nếu cần giữ kiểu |
| BSON Timestamp | `Timestamp({t: ..., i: ...})` | Giây + bộ đếm | Dành cho ngữ cảnh đặc biệt; không thay Date |

### 8.1. Lỗi rất phổ biến: giây và mili giây

Nhiều API trả về **Unix timestamp theo giây**, còn JavaScript `Date` nhận **mili giây** khi khởi tạo từ số:

```javascript
// Giá trị 1_700_000_000 là giây, không phải mili giây.
const epochSeconds = 1700000000;

// Đúng: chuyển seconds -> milliseconds.
const dateFromSeconds = new Date(epochSeconds * 1000);

// Sai ngữ nghĩa nếu API cung cấp seconds mà lại truyền trực tiếp.
const mistaken = new Date(epochSeconds);

print(dateFromSeconds.toISOString());
print(mistaken.toISOString());
```

Khi thấy thời gian bị lệch về khoảng năm 1970 hoặc sang một mốc rất xa tương lai, cần kiểm tra đơn vị của số epoch trước tiên.

### 8.2. ObjectId có thể cho biết thời điểm tạo gần đúng

Một `ObjectId` có thành phần timestamp với độ phân giải cấp **giây**. Trong `mongosh`:

```javascript
const id = new ObjectId();
print(id.getTimestamp());
```

Giá trị này có thể hữu ích trong một số thao tác quan sát, nhưng không nên mặc định dùng thay `createdAt` vì ObjectId có thể được tạo ở phía client, được cấp trước lúc insert, được nhập từ nguồn khác và chỉ có độ phân giải giây. Khi ứng dụng cần thời điểm nghiệp vụ chính xác, lưu trường Date rõ ràng.

### 8.3. Sự khác nhau giữa giờ client và giờ server

`new Date()` ở `mongosh` lấy giờ từ máy chạy shell. Nếu ứng dụng nhiều máy có đồng hồ lệch nhau, trường thời gian do client tạo có thể lệch. Với một số thao tác cập nhật theo pipeline, MongoDB hỗ trợ biến hệ thống `$$NOW` để lấy thời gian hiện tại do server cung cấp trong ngữ cảnh biểu thức:

```javascript
db.getSiblingDB("bson_time_lab").events.updateOne(
  { _id: inserted.insertedId, runId: runId },
  [
    {
      $set: {
        processedAt: "$$NOW"
      }
    }
  ]
);
```

Đoạn ví dụ dùng lại biến `inserted` và `runId` từ mục 3.3 trong **cùng phiên shell**. `$$NOW` là giá trị Date nhất quán trong ngữ cảnh pipeline tương ứng; đây không phải cách lưu tên múi giờ. Cả đồng hồ client và server đều cần được vận hành, đồng bộ phù hợp với yêu cầu hệ thống.

## 9. Những thiết kế dễ gây lỗi

### 9.1. Lưu thời gian thành chuỗi địa phương không có múi giờ

**Dữ liệu dễ gây nhầm:**

```javascript
{ createdAt: "14/11/2026 08:30" }
```

Chuỗi này thiếu offset/múi giờ và không phải BSON Date; truy vấn sắp xếp dạng chuỗi còn phụ thuộc vào định dạng. Nếu đây là một sự kiện đã xảy ra, tốt hơn là lưu Date như `ISODate("2026-11-14T01:30:00Z")` và múi giờ nguồn riêng khi cần.

### 9.2. Dùng một offset cố định để thay toàn bộ quy tắc múi giờ

`+07:00` cho biết độ lệch ở một thời điểm; `Asia/Ho_Chi_Minh` cho biết tên vùng. Với lịch tương lai ở các vùng có DST hoặc thay đổi quy định giờ địa phương, tên IANA giúp hệ thống vận dụng quy tắc tương ứng. Cần quản lý phiên bản dữ liệu múi giờ ở các hệ thống có yêu cầu lịch lâu dài hoặc độ chính xác cao.

### 9.3. Tính cuối ngày bằng “23:59:59”

Sự kiện ở `23:59:59.500` sẽ bị bỏ sót nếu lọc `$lte` đến `23:59:59.000`. Thay vì cố tìm cuối ngày, dùng khoảng `[đầu ngày, đầu ngày kế tiếp)` với `$gte` và `$lt`.

### 9.4. Trộn Date, Timestamp và string trong một trường

```javascript
// Ba kiểu khác nhau, không nên trộn vào cùng một trường nghiệp vụ.
{ occurredAt: ISODate("2026-11-14T01:30:00Z") }
{ occurredAt: "2026-11-14T01:30:00Z" }
{ occurredAt: Timestamp({ t: 1760000000, i: 1 }) }
```

Cấu trúc này làm phức tạp lọc, sắp xếp và aggregation vì MongoDB nhận diện các **kiểu BSON khác nhau**. Nên quy định schema/validation cho các trường ngày giờ quan trọng và chuyển đổi dữ liệu cũ có kiểm soát.

### 9.5. Lịch nhắc hẹn chỉ lưu instant mà bỏ ngữ nghĩa địa phương

Nếu người dùng muốn “09:00 sáng thứ Hai hằng tuần” thì mỗi lần thực thi là một instant khác nhau. Một lần chuyển múi giờ hoặc thay đổi DST có thể khiến phép cộng `7 * 24 giờ` không còn khớp 09:00 địa phương. Cần lưu quy tắc lịch và múi giờ IANA, rồi tạo occurrence kế tiếp theo lịch.

### 9.6. Nghĩ rằng Timestamp mang độ chính xác micro/nano giây

BSON Timestamp có `t` và `i`; `i` là bộ đếm sắp thứ tự, không phải số mili giây. Nếu nghiệp vụ cần theo dõi sự kiện với độ chính xác cao hơn mili giây, phải thiết kế thêm trường biểu diễn độ phân giải thích hợp; không “nâng cấp” BSON Date sang BSON Timestamp rồi coi đó là nano timestamp.

## 10. Bài thực hành tổng hợp

### Bài A: Tìm sự kiện theo ngày Việt Nam

Giả sử collection `events` có các document:

```javascript
[
  { _id: "A", occurredAt: ISODate("2026-11-13T16:59:59.999Z") },
  { _id: "B", occurredAt: ISODate("2026-11-13T17:00:00.000Z") },
  { _id: "C", occurredAt: ISODate("2026-11-14T01:30:00.000Z") },
  { _id: "D", occurredAt: ISODate("2026-11-14T17:00:00.000Z") }
]
```

Theo ngày **14/11/2026 tại Việt Nam**, document **B** và **C** thuộc khoảng; **A** thuộc cuối ngày 13 và **D** đúng điểm đầu ngày 15. Hãy dùng truy vấn ở mục 6.2 để kiểm chứng nếu tạo một collection thử nghiệm riêng. Không cần dùng `$lte` với mốc cuối.

### Bài B: Dự đoán kết quả biểu diễn múi giờ

Một ứng dụng lưu `ISODate("2026-11-14T01:30:00Z")`. Hãy trả lời:

1. Người dùng tại Việt Nam nhìn thấy mấy giờ?
2. Giá trị BSON Date có tự chứa chuỗi `Asia/Ho_Chi_Minh` không?
3. Nếu cần nhóm sự kiện theo **ngày địa phương**, nên chỉ định `timezone` ở toán tử nào?
4. Nếu ứng dụng nhận chuỗi `"2026-11-14 08:30:00"` từ hệ thống nguồn, cần biết thêm thông tin gì để biến thành instant?

### Bài C: Quan sát kiểu dữ liệu, rồi dọn bản ghi đã tạo

Nếu đã chạy phần insert ở mục 3.3, kiểm tra kiểu của trường vừa ghi:

```javascript
events.aggregate([
  { $match: { _id: inserted.insertedId, runId: runId } },
  {
    $project: {
      occurredAt: 1,
      occurredAtType: { $type: "$occurredAt" },
      vietnamTime: {
        $dateToString: {
          date: "$occurredAt",
          format: "%Y-%m-%d %H:%M:%S",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
```

Kết quả mong đợi ở trường `occurredAtType` là `"date"`. Sau khi thử xong, **xem lại đúng document của lượt này**, rồi xóa theo cả `_id` và `runId`:

```javascript
const exactFilter = { _id: inserted.insertedId, runId: runId };
printjson(events.findOne(exactFilter));

const removed = events.deleteOne(exactFilter);
printjson(removed);
print("remaining=" + events.countDocuments(exactFilter));
```

Ví dụ dùng lại `events`, `inserted`, `runId` trong cùng phiên shell; nếu mở phiên mới cần dùng lại đúng giá trị đã lưu, không đoán `_id` hoặc xóa rộng. Với kết quả xóa thông thường, `deletedCount` là `1` và `remaining` là `0`.

## 11. Ghi nhớ khi thiết kế dữ liệu thời gian

| Nhu cầu | Biểu diễn nên cân nhắc | Điều cần quyết định rõ |
| --- | --- | --- |
| Thời điểm sự kiện đã xảy ra | BSON Date | Dùng một instant; format theo múi giờ hiển thị |
| Sự kiện có ý nghĩa theo vùng địa phương | BSON Date + field tên múi giờ IANA | Giữ vùng nguồn hoặc vùng nghiệp vụ nếu cần |
| Ngày sinh/ngày lễ không có giờ | Ngày lịch dưới dạng chuỗi `YYYY-MM-DD` hoặc cấu trúc year/month/day | Không tự áp múi giờ nếu nghiệp vụ chỉ có ngày |
| Lịch hẹn/lịch lặp lại | Ngày, giờ địa phương, múi giờ IANA và quy tắc lặp | Chính sách DST, lần diễn ra, thay đổi múi giờ |
| Lọc báo cáo theo ngày địa phương | BSON Date + khoảng `[start, end)` | Tính hai ranh giới ở múi giờ mong muốn |
| Oplog/vị trí thời gian nội bộ | BSON Timestamp trong ngữ cảnh MongoDB tương ứng | Không dùng bộ đếm `i` như mili giây |
| Tích hợp API dùng Unix epoch | Xác định rõ seconds hay milliseconds rồi chuyển kiểu | Kiểm soát đơn vị và kiểu của trường |
| Xuất/nhập JSON mà cần bảo toàn BSON | Extended JSON và parser tương ứng | Phân biệt string JSON với biểu diễn có kiểu |

Khi làm việc với MongoDB, hãy bắt đầu bằng việc hỏi **“giá trị này là một instant, một ngày theo lịch hay một giờ địa phương?”**. Sau đó chọn kiểu BSON phù hợp, lưu múi giờ khi nghiệp vụ cần, và xác định ranh giới truy vấn bằng các instant rõ ràng. Tư duy đó giúp tránh lỗi lệch ngày, lệch giờ và hiểu sai BSON Timestamp trong ứng dụng.
