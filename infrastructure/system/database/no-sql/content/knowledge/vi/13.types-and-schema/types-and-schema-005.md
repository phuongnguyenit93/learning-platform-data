# Ngày giờ, múi giờ, độ chính xác và thời điểm do client/server tạo

Trong một cơ sở dữ liệu NoSQL, ngày giờ thường xuất hiện ở mọi loại dữ liệu: thời điểm người dùng đặt hàng, sự kiện thiết bị gửi về, lần cập nhật cuối cùng, thời hạn phiên đăng nhập, lịch hẹn, mốc phân trang và khóa phân vùng theo ngày. Những trường trông đơn giản như `createdAt`, `updatedAt` hoặc `eventTime` lại có thể gây lỗi rất khó phát hiện nếu không phân biệt rõ **một thời điểm trên trục thời gian**, **giờ địa phương**, **múi giờ**, **độ chính xác lưu trữ** và **nguồn tạo timestamp**.

Ví dụ, một ứng dụng nhận thời gian `2026-11-14 09:30` từ người dùng. Nếu không biết địa phương hay múi giờ, hệ thống không thể xác định đó là 09:30 tại Việt Nam, Nhật Bản hay Mỹ. Nếu lưu bằng số nguyên giây, ứng dụng sẽ mất phần mili giây. Nếu dùng đồng hồ thiết bị để quyết định bản ghi nào mới hơn, hai thiết bị chỉnh giờ sai có thể đảo thứ tự sự kiện. Nếu dùng thời gian của database làm khóa sắp xếp mà không thêm ID phân biệt, hai sự kiện cùng mili giây có thể đụng cùng khóa.

Bài học giải thích cách biểu diễn và truy vấn dữ liệu thời gian đúng ngữ nghĩa trong NoSQL, minh họa với **MongoDB**, **Cassandra/CQL**, **DynamoDB**, **Redis** và ví dụ **Java**. Các hệ quản trị có kiểu và cách xử lý khác nhau; điều cần giữ nhất quán là **hợp đồng dữ liệu thời gian của ứng dụng**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `Instant`, ngày địa phương, giờ địa phương, ngày-giờ địa phương, UTC offset và múi giờ theo khu vực.
2. Chuẩn hóa thời điểm được client gửi thành dạng lưu trữ, so sánh và truy vấn nhất quán.
3. Chọn đơn vị **giây, mili giây, micro giây hoặc nano giây** theo độ chính xác và kiểu dữ liệu mà hệ quản trị thật sự hỗ trợ.
4. Thiết kế `occurredAt`, `receivedAt`, `createdAt`, `updatedAt`, `effectiveAt`, `expiresAt` với **nguồn tạo và ý nghĩa rõ ràng**.
5. Truy vấn khoảng thời gian đúng ở ranh giới ngày, múi giờ và phân vùng.
6. Xử lý dữ liệu đến muộn, đồng hồ client lệch, chuyển giờ mùa hè (*daylight saving time – DST*) và cập nhật đồng thời.
7. Viết API và bài kiểm tra để không phụ thuộc ngầm vào timezone của máy chạy chương trình.

## 2. Bài toán xuyên suốt: ghi nhận sự kiện đơn hàng

Giả sử nền tảng thương mại nhận một sự kiện `ORDER_PAID` từ thiết bị hoặc dịch vụ khách hàng:

~~~json
{
  "tenantId": "merchant-a",
  "eventId": "evt-9001",
  "orderId": "O900",
  "eventType": "ORDER_PAID",
  "occurredAt": "2026-11-14T09:30:00.123+07:00",
  "sourceZone": "Asia/Ho_Chi_Minh"
}
~~~

Các mốc liên quan:

| Dữ kiện | Giá trị minh họa | Câu hỏi mà nó trả lời |
| --- | --- | --- |
| `occurredAt` | `2026-11-14T09:30:00.123+07:00` | Sự kiện thực sự xảy ra khi nào, theo nguồn phát? |
| `receivedAt` | `2026-11-14T02:30:02.491Z` | API tiếp nhận sự kiện lúc nào? |
| `persistedAt` | Ví dụ `2026-11-14T02:30:02.505Z` | Lớp ghi dữ liệu ghi nhận mốc nào? |
| `effectiveAt` | Có thể khác `occurredAt` | Nghiệp vụ coi trạng thái có hiệu lực từ lúc nào? |
| `expiresAt` | Phụ thuộc chính sách | Dữ liệu hoặc phiên đăng nhập hết hạn lúc nào? |

`occurredAt` và `receivedAt` có thể khác nhau vì mạng, queue, xử lý batch hoặc đồng hồ nguồn lệch. Không nên tự coi chênh lệch hai timestamp là độ trễ mạng chính xác tuyệt đối nếu đồng hồ của hai hệ thống chưa được đồng bộ và kiểm soát.

Mục tiêu đầu tiên là xác định:

~~~text
2026-11-14T09:30:00.123+07:00
               cùng một instant với
2026-11-14T02:30:00.123Z
~~~

Giờ hiển thị khác nhau, nhưng đây là **cùng một thời điểm**.

## 3. Phân biệt các khái niệm ngày và giờ

### 3.1. Instant — một thời điểm tuyệt đối

**Instant** là một điểm trên trục thời gian, không phụ thuộc cách người dùng gọi tên giờ tại địa phương. Một cách biểu diễn phổ biến là thời gian tính từ mốc Unix epoch `1970-01-01T00:00:00Z`.

Ví dụ:

~~~text
2026-11-14T02:30:00Z
~~~

Khi cần so sánh sự kiện nào xảy ra trước, sau hoặc truy vấn toàn hệ thống theo thời gian, một **instant chuẩn hóa** thường là kiểu dữ liệu thích hợp.

### 3.2. LocalDate — một ngày trên lịch

`2026-11-14` là một **ngày**, không phải một instant. Ngày đó bắt đầu và kết thúc ở những thời điểm UTC khác nhau theo múi giờ của người dùng.

Ví dụ: ngày `2026-11-14` tại `Asia/Ho_Chi_Minh` tương ứng khoảng UTC:

~~~text
Từ: 2026-11-13T17:00:00Z (bao gồm)
Đến: 2026-11-14T17:00:00Z (không bao gồm)
~~~

Trong các nơi có DST, một ngày địa phương có thể dài **23 hoặc 25 giờ** chứ không nhất thiết 24 giờ. Vì vậy nếu nghiệp vụ hỏi “đơn trong ngày của cửa hàng”, phải biết **múi giờ của cửa hàng** rồi chuyển ranh giới ngày thành instant, không chỉ lấy `00:00Z` đến `24:00Z` một cách mặc định.

### 3.3. LocalTime và LocalDateTime

`09:30:00` là **giờ trong một ngày**, chưa có ngày hoặc múi giờ. `2026-11-14T09:30:00` là **ngày giờ địa phương**, có ngày nhưng **chưa xác định được instant** khi không biết nơi diễn ra.

Đây là những giá trị có ý nghĩa trong bài toán:

- “Cửa hàng mở lúc 09:00 theo giờ địa phương”.
- “Nhân viên họp lúc 08:30 thứ Hai hàng tuần”.
- “Thời gian đặt lịch do người dùng nhập trước khi chọn vùng”.

Không nên coi một `LocalDateTime` không có timezone là timestamp tuyệt đối để so sánh trên nhiều khu vực.

### 3.4. UTC offset và time zone khác nhau

**Offset** là độ lệch so với UTC tại một thời điểm, ví dụ `+07:00`, `-05:00`.

**Time zone theo khu vực** là một bộ quy tắc về giờ địa phương và lịch thay đổi offset theo thời gian, ví dụ:

~~~text
Asia/Ho_Chi_Minh
America/New_York
Europe/Paris
~~~

Ở một thời điểm nào đó, `America/New_York` có thể dùng offset `-05:00`; ở thời điểm khác lại dùng `-04:00`. Vì vậy **offset không thay thế hoàn toàn zone ID** khi ứng dụng phải tính lịch hẹn trong tương lai hoặc quy tắc lặp theo địa phương.

| Dạng giá trị | Xác định instant ngay chưa? | Trường hợp dùng |
| --- | --- | --- |
| `2026-11-14` | Chưa | Ngày trên lịch |
| `09:30` | Chưa | Giờ làm việc theo ngày |
| `2026-11-14T09:30:00` | Chưa | Ngày giờ chưa gắn zone |
| `2026-11-14T09:30:00+07:00` | **Có** | Thời điểm có offset |
| `2026-11-14T02:30:00Z` | **Có** | Thời điểm UTC |
| `2026-11-14T09:30` + `Asia/Ho_Chi_Minh` | Có thể xác định theo quy tắc zone | Lịch hẹn theo địa phương; cần xử lý DST nếu có |

### 3.5. Duration và Period không giống nhau

`Duration.ofHours(24)` nghĩa là **86.400 giây thực**. `Period.ofDays(1)` thường có ý nghĩa **chuyển sang cùng giờ của ngày lịch tiếp theo** khi áp dụng trong một múi giờ.

Ở vùng có DST, “sau 24 giờ” có thể khác “ngày mai lúc cùng giờ”. Hai yêu cầu:

~~~text
Phiên hết hạn sau đúng 24 giờ
Lịch giao hàng ngày mai lúc 09:00 theo giờ địa phương
~~~

cần các phép tính khác nhau. Chọn sai loại thời gian có thể làm việc giao hàng, nhắc lịch hoặc tính TTL lệch một giờ trong thời điểm DST.

## 4. Quy tắc lưu trữ: một instant, nhiều cách hiển thị

Với trường diễn tả **thời điểm đã xảy ra**, quy tắc thường an toàn là:

1. Nhận input có **offset hoặc zone rõ ràng**.
2. Parse và chuyển sang **instant UTC**.
3. Lưu bằng kiểu thời gian native, epoch có đơn vị rõ hoặc chuỗi UTC được chuẩn hóa.
4. Khi hiển thị, chuyển instant sang zone được chọn bởi người dùng hoặc chính sách nghiệp vụ.
5. Nếu cần giải thích cách người dùng đã nhập thời gian, lưu thêm **zone ID, offset gốc hoặc chuỗi gốc** theo nhu cầu kiểm toán, chứ không thay thế instant.

~~~mermaid
flowchart LR
    A["Client: 09:30:00.123 +07:00"] --> B["Parse có offset"]
    B --> C["Instant: 02:30:00.123Z"]
    C --> D["NoSQL: thời điểm chuẩn hóa"]
    D --> E["Người ở Việt Nam: 09:30"]
    D --> F["Người ở UTC: 02:30"]
    D --> G["Người ở vùng khác: đổi theo zone"]
~~~

### 4.1. Không lưu timestamp thiếu ngữ cảnh

Tránh một JSON mơ hồ:

~~~json
{
  "createdAt": "2026-11-14 09:30:00"
}
~~~

Chuỗi trên không có offset và không nêu nơi diễn ra. Nếu server A mặc định UTC còn server B mặc định `Asia/Ho_Chi_Minh`, cùng dữ liệu có thể cách nhau **7 giờ**.

Nên dùng dạng có ý nghĩa rõ:

~~~json
{
  "createdAt": "2026-11-14T02:30:00.000Z"
}
~~~

Hoặc, nếu đây là lịch hẹn trong tương lai theo vùng:

~~~json
{
  "appointmentLocalTime": "2026-11-14T09:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

Hai schema biểu đạt **hai yêu cầu khác nhau**. Đừng ép một cuộc hẹn lặp theo giờ địa phương vào một instant duy nhất nếu ứng dụng phải tính các lần lặp trong tương lai theo quy tắc zone.

## 5. DST: thời gian không tồn tại và thời gian xuất hiện hai lần

Một múi giờ có chuyển giờ mùa hè sẽ có những thời điểm địa phương không ánh xạ đơn giản thành đúng một instant.

### 5.1. Khoảng không tồn tại (*gap*)

Ở `America/New_York`, trong ngày chuyển sang DST mùa xuân năm 2026, đồng hồ chuyển từ gần **02:00 lên 03:00**. Vì vậy:

~~~text
2026-03-08T02:30:00
Zone: America/New_York
~~~

là **giờ địa phương không tồn tại** theo quy tắc zone tương ứng. Nếu hệ thống lịch hẹn nhận 02:30, cần chính sách:

- Từ chối và yêu cầu chọn giờ hợp lệ.
- Hoặc dịch sang một giờ hợp lệ theo quy tắc nghiệp vụ đã công bố.

Không được âm thầm diễn giải thành UTC theo offset tự đoán rồi coi kết quả là thời điểm người dùng thực sự yêu cầu.

### 5.2. Khoảng nhập nhằng (*overlap*)

Ở `America/New_York`, ngày `2026-11-01` khi kết thúc DST, `01:30` xuất hiện **hai lần**:

~~~text
2026-11-01T01:30:00-04:00 = 2026-11-01T05:30:00Z
2026-11-01T01:30:00-05:00 = 2026-11-01T06:30:00Z
~~~

Hai instant cách nhau **một giờ** dù cùng hiển thị “01:30”. Khi tạo lịch hẹn, phải xác định muốn lần thứ nhất hay lần thứ hai, hoặc yêu cầu thêm offset để phân biệt.

### 5.3. Quy tắc cho ứng dụng lịch hẹn

Với lịch được định nghĩa theo giờ địa phương (ví dụ “09:00 thứ Hai tại Paris”), nên lưu:

~~~json
{
  "localTime": "09:00",
  "timeZone": "Europe/Paris",
  "recurrence": "MONDAY",
  "dstPolicy": "REJECT_OR_RESOLVE_EXPLICITLY"
}
~~~

`dstPolicy` là tên chính sách minh họa, không phải giá trị chuẩn của database. Mỗi lần lên lịch, ứng dụng dùng **IANA time zone rules** tương ứng để tính instant. Nếu chính sách pháp lý/nghiệp vụ yêu cầu giữ chính xác offset đã xác nhận, có thể phải lưu thêm instant đã hẹn và các thông tin gốc.

**Lưu ý:** dữ liệu quy tắc múi giờ có thể được cập nhật khi quốc gia thay đổi quy định. Những lịch hẹn xa trong tương lai nên có chính sách rõ về việc tính lại khi cập nhật time-zone database.

## 6. Độ chính xác và đơn vị của timestamp

Một timestamp có thể được biểu diễn theo nhiều cấp độ:

| Đơn vị | Ký hiệu | Số đơn vị trong 1 giây | Ví dụ epoch gần thời điểm năm 2026 |
| --- | --- | ---: | --- |
| Giây | s | 1 | Cỡ `1,8 × 10^9` |
| Mili giây | ms | 1.000 | Cỡ `1,8 × 10^12` |
| Micro giây | µs | 1.000.000 | Cỡ `1,8 × 10^15` |
| Nano giây | ns | 1.000.000.000 | Cỡ `1,8 × 10^18` |

Chỉ đổi số lượng số 0 đã thay đổi hoàn toàn ý nghĩa:

~~~text
epochSeconds = 1794623400
epochMillis  = 1794623400000
~~~

Đây là các giá trị minh họa cùng cấp độ; **không suy luận đơn vị từ độ dài chuỗi số trong code production**. Một API nên dùng tên trường có đơn vị rõ như `expiresAtEpochSeconds`, `occurredAtEpochMillis`, hoặc sử dụng ISO 8601.

### 6.1. Giây, mili, micro, nano khác nhau thế nào?

Một sự kiện diễn ra tại:

~~~text
2026-11-14T02:30:00.123456789Z
~~~

Nếu chỉ lưu đến mili giây, biểu diễn có thể trở thành:

~~~text
2026-11-14T02:30:00.123Z
~~~

Phần `456789` nano giây bên phải ba chữ số mili giây đã bị mất. Khi chuyển đổi, phải biết thư viện **cắt phần dư, làm tròn hay báo lỗi**; không được mặc định độ chính xác được bảo toàn.

### 6.2. Độ phân giải của đồng hồ khác độ chính xác của kiểu dữ liệu

Một kiểu dữ liệu hỗ trợ nano giây **không có nghĩa đồng hồ máy tính tạo mốc chính xác đến từng nano giây**. Các khái niệm cần tách:

- **Precision của representation:** số chữ số/phần lẻ có thể lưu.
- **Resolution của clock:** mức thay đổi nhỏ nhất mà đồng hồ tạo ra.
- **Accuracy của clock:** mức chênh lệch giữa đồng hồ và thời gian tham chiếu.
- **Consistency giữa các máy:** các đồng hồ có thể lệch nhau bao nhiêu.

Lưu `2026-11-14T02:30:00.123456789Z` không chứng minh hệ thống thật sự biết sự kiện diễn ra ở mức nano giây.

### 6.3. Vấn đề số nguyên và JavaScript

JavaScript `Number` biểu diễn số thực double; các số nguyên chỉ chính xác hoàn toàn trong khoảng:

\[
-(2^{53}-1) \ldots +(2^{53}-1)
\]

Epoch **mili giây** gần năm 2026 nằm trong khoảng an toàn này. Epoch **nano giây** gần năm 2026 lớn hơn nhiều, nên nếu truyền bằng JSON Number và parse thành JavaScript Number, các chữ số thấp có thể bị làm tròn.

Ví dụ không an toàn:

~~~javascript
const epochNanos = 1794623400123456789;
// Number không biểu diễn chính xác mọi số nguyên ở cỡ này.
~~~

Nếu thật sự cần nano giây, có thể dùng **chuỗi số thập phân**, một cặp `seconds + nanos` có ràng buộc hoặc kiểu số nguyên đủ lớn ở hai phía, thay vì tùy tiện gửi qua JSON Number.

### 6.4. Không dùng int32 cho epoch milliseconds

Epoch milliseconds hiện đại không vừa số nguyên có dấu 32-bit. Ngay cả epoch seconds có dấu 32-bit cũng có mốc tràn vào năm 2038.

Trong Java:

~~~java
long epochMillis = instant.toEpochMilli();
~~~

Không nên ép về `int`. Trong database, phải dùng Number 64-bit hoặc kiểu thời gian native phù hợp, đồng thời kiểm tra driver/serialization có giữ nguyên độ chính xác cần thiết không.

### 6.5. Giá trị bằng nhau không đồng nghĩa là cùng sự kiện

Nếu database lưu timestamp đến mili giây, hai event có thể có `occurredAt` bằng nhau:

~~~text
evt-A: 2026-11-14T02:30:00.123Z
evt-B: 2026-11-14T02:30:00.123Z
~~~

Vì vậy **timestamp không phải ID duy nhất đáng tin cậy**. Với bảng sắp theo thời gian, thường cần khóa phụ:

~~~text
(partitionKey, occurredAt, eventId)
~~~

Nhờ đó hai event cùng mili giây vẫn là hai hàng riêng, và `eventId` có thể làm tie-breaker khi sắp xếp/phân trang.

## 7. Kiểu dữ liệu thời gian ở các NoSQL khác nhau

Không nên giả định cùng một trường `timestamp` có kiểu, độ chính xác và phép toán giống hệt giữa các sản phẩm.

| Hệ quản trị | Cách biểu diễn thời gian thường gặp | Lưu ý quan trọng |
| --- | --- | --- |
| **MongoDB** | BSON `Date`, giá trị mili giây kể từ Unix epoch | Một instant với độ phân giải đến ms; không lưu kèm IANA zone trong kiểu Date |
| **Apache Cassandra (CQL)** | `timestamp`, `date`, `time`, `duration`, `timeuuid` | `timestamp` ở mức ms; `date` là ngày; `time` là giờ trong ngày; `timeuuid` không thay thế mọi timestamp |
| **DynamoDB** | `String`, `Number`, `Binary` cho dữ liệu thời gian do ứng dụng quy ước | Không có kiểu timestamp native chung; phải thống nhất ISO string hoặc epoch, nhất là sort key |
| **Redis** | String/Hash/Sorted Set chứa chuỗi hoặc số do ứng dụng chọn; TTL do server quản lý | TTL là cơ chế hết hạn, không phải lịch sử thời gian; sorted-set score dùng double |
| **Neo4j/Cypher** | `date`, `localtime`, `localdatetime`, `datetime`, `duration` tùy phiên bản | Phân biệt loại có/không có thông tin múi giờ và phép tính lịch |

Các hệ quản trị còn có khác biệt về **so sánh chuỗi, độ chính xác, chỉ mục, replication, TTL, serialization và timestamp gắn với phiên bản ghi**. Trước khi triển khai, hãy kiểm tra thông số đúng phiên bản đang sử dụng.

### 7.1. MongoDB BSON Date

MongoDB `Date` là một giá trị thời điểm, được biểu diễn bằng số nguyên 64-bit tính theo **mili giây** từ Unix epoch. Nó không lưu bản thân chuỗi `Asia/Ho_Chi_Minh` hoặc offset ban đầu.

Ví dụ mongosh:

~~~javascript
db.events.insertOne({
  tenantId: "merchant-a",
  eventId: "evt-9001",
  occurredAt: ISODate("2026-11-14T02:30:00.123Z"),
  sourceTimeZone: "Asia/Ho_Chi_Minh"
});
~~~

Giá trị `occurredAt` được lưu theo kiểu Date, còn `sourceTimeZone` là một **thuộc tính chuỗi riêng** phục vụ giải thích giờ gốc hoặc hiển thị theo chính sách.

Nếu API nhận thời điểm có micro/nano giây, khi đưa vào BSON Date cần **quy định rõ việc chuyển sang mili giây**; MongoDB không tự giữ phần nano giây như một phần của Date.

### 7.2. Cassandra timestamp, date, time và timeuuid

Trong Cassandra CQL:

- `timestamp`: biểu diễn thời điểm, ở mức **mili giây kể từ Unix epoch**.
- `date`: một ngày lịch, không tự chứa giờ hoặc timezone.
- `time`: giờ trong ngày với độ chính xác biểu diễn cao, không mang ngày và zone.
- `duration`: khoảng thời gian có thành phần tháng/ngày/nano giây, cần hiểu khác biệt giữa khoảng lịch và số giây cố định.
- `timeuuid`: UUID phiên bản 1 có thành phần thời gian, hữu ích trong một số thiết kế khóa/sắp xếp theo thời gian nhưng không phải một instant duy nhất với bảo đảm thứ tự toàn cục giữa mọi node.

**Rất dễ nhầm `timestamp` (một cột giá trị thời gian của ứng dụng) với write timestamp (metadata để Cassandra giải quyết xung đột phiên bản cell).** Chúng không phải một dữ kiện giống nhau.

### 7.3. DynamoDB

DynamoDB không cung cấp một kiểu `Date` native giống MongoDB BSON Date. Ứng dụng có thể lưu:

~~~json
{
  "occurredAtIso": "2026-11-14T02:30:00.123Z",
  "occurredAtEpochMillis": 1794623400123
}
~~~

Các số trên minh họa định dạng; khi đưa vào AWS SDK phải dùng đúng kiểu DynamoDB tương ứng `S` hoặc `N`. Trường thời gian dùng làm **sort key** phải được chuẩn hóa để thứ tự khóa có ý nghĩa; dùng nhiều dạng offset và độ dài phần lẻ khác nhau có thể tạo thứ tự chuỗi sai với thứ tự thời gian.

### 7.4. Redis

Redis có thể lưu epoch trong string hoặc score của sorted set:

~~~text
SET event:evt-9001:at 1794623400123
ZADD order:O900:events 1794623400123 evt-9001
~~~

Khi dùng sorted-set score, Redis lưu score theo kiểu số thực double. Epoch milliseconds ở giai đoạn hiện tại nằm trong khoảng nguyên an toàn, nhưng epoch nanoseconds ở cỡ `10^18` **không được bảo toàn từng chữ số** nếu dùng làm score.

Nếu cần thứ tự rất chính xác, có thể lưu khóa dạng chuỗi đã chuẩn hóa với tie-breaker hoặc chọn cấu trúc khác, thay vì ép nano giây vào score double.

## 8. Ai tạo timestamp: client, API server hay database server?

Một câu hỏi trọng yếu khi thiết kế schema là: **mốc thời gian này do bên nào chịu trách nhiệm xác định?**

### 8.1. Client-generated time

Client có thể là:

- Ứng dụng điện thoại.
- Trình duyệt.
- Thiết bị IoT.
- Một dịch vụ khác gửi event.
- Worker xử lý một công việc.

Client biết thời điểm **nó quan sát** sự kiện, đặc biệt khi hoạt động ngoại tuyến rồi đồng bộ sau. Nhưng đồng hồ có thể:

- Bị người dùng chỉnh sai.
- Lệch vài phút/giờ.
- Đang ở timezone khác hoặc chọn timezone sai.
- Có độ phân giải thấp.
- Bị một tác nhân ác ý sửa để thay đổi thứ tự nghiệp vụ.

Vì vậy `occurredAt` do client cung cấp rất hữu ích cho **lịch sử sự kiện**, nhưng không nên mặc định đủ tin cậy để quyết định thứ tự commit, điều kiện thanh toán hoặc quyền truy cập.

### 8.2. API server-generated time

API có thể gắn mốc `receivedAt` khi nhận request:

~~~text
Client event occurredAt = 09:30:00.123 +07
Network queue / offline
API receivedAt        = 02:30:02.491Z
~~~

Ưu điểm là nguồn thời gian nằm trong hạ tầng kiểm soát được, có thể giám sát đồng bộ đồng hồ. Nhưng nếu nhiều API server, đồng hồ của chúng vẫn có thể lệch. **API server time không phải bằng chứng về thứ tự tuyệt đối giữa các tiến trình phân tán.**

### 8.3. Database server-generated time

Một số engine cho phép tạo timestamp bằng hàm phía database hoặc phép cập nhật `$currentDate`. Điều này tránh việc mỗi client tùy ý tự gắn một số trường mốc cập nhật.

Tuy nhiên cần phân biệt:

- **Thời điểm câu lệnh dùng hàm thời gian của DB**.
- **Thời điểm mutation được commit/xác nhận**.
- **Thời điểm replica khác nhìn thấy mutation**.
- **Thời điểm nghiệp vụ có hiệu lực**.

Chúng không tự động đồng nhất trong hệ thống phân tán. Tên `persistedAt` hoặc `committedAt` chỉ nên dùng nếu triển khai thực sự xác định được mốc có ngữ nghĩa đó; nếu chỉ gọi `now()` trước khi ghi, nên đặt tên chính xác hơn như `writeRequestedAt`.

### 8.4. Quyết định theo ý nghĩa trường

| Trường | Nguồn đề xuất | Ý nghĩa và lưu ý |
| --- | --- | --- |
| `occurredAt` / `observedAt` | Nguồn phát sự kiện | Dùng cho lịch sử thế giới thực; cần xác minh/giới hạn độ tin cậy |
| `receivedAt` | API hoặc ingress của hệ thống | Thời điểm hệ thống nhận; hữu ích cho giám sát trễ |
| `createdAt` của bản ghi ứng dụng | Dịch vụ có quyền tạo hoặc DB theo hợp đồng | Nên bất biến sau khi tạo; định nghĩa rõ là tạo nghiệp vụ hay tạo record |
| `updatedAt` | Dịch vụ chủ sở hữu hoặc DB | Thời điểm cập nhật, không nên dùng duy nhất để chống lost update |
| `effectiveAt` | Quy tắc nghiệp vụ | Có thể là thời điểm do người dùng chọn và được kiểm tra |
| `expiresAt` | Chủ sở hữu chính sách hết hạn | Một instant tuyệt đối; khác với TTL vật lý của DB |
| `processedAt` | Worker | Thời điểm worker xử lý, không thay thế `occurredAt` |
| `deletedAt` | Dịch vụ xác nhận xóa | Có thể cần retention/tombstone để chống replay dữ liệu cũ |

**Nguyên tắc:** trường nào do client tạo phải được ghi rõ trong API; trường nào do server tạo thì client không được tùy ý quyết định chỉ bằng cách gửi một giá trị trùng tên.

## 9. Thiết kế schema sự kiện đầy đủ

Một schema sự kiện đơn giản nhưng rõ nghĩa:

~~~json
{
  "tenantId": "merchant-a",
  "eventId": "evt-9001",
  "orderId": "O900",
  "eventType": "ORDER_PAID",
  "occurredAt": "2026-11-14T02:30:00.123Z",
  "receivedAt": "2026-11-14T02:30:02.491Z",
  "sourceTimeZone": "Asia/Ho_Chi_Minh",
  "sourceOffset": "+07:00",
  "sourceClockQuality": "UNVERIFIED",
  "schemaVersion": 1
}
~~~

Ở đây:

- `occurredAt` là instant đã chuẩn hóa từ timestamp nguồn; vẫn phản ánh **lời khai về thời gian của nguồn** nếu nguồn không đáng tin.
- `receivedAt` là instant do ingress server tạo.
- `sourceTimeZone` và `sourceOffset` là ngữ cảnh bổ sung, **không phải hai giá trị thay thế occurredAt**.
- `sourceClockQuality` là một quy ước ứng dụng minh họa để biểu diễn mức tin cậy.
- `schemaVersion` giúp quản lý thay đổi hợp đồng JSON.

Nếu yêu cầu độ chính xác cao hơn mili giây, cần thiết kế biểu diễn khác và kiểm tra hệ lưu trữ có giữ phần bổ sung. **Không ghi 9 chữ số phần lẻ vào JSON rồi cho rằng BSON Date/CQL timestamp sẽ bảo toàn cả 9.**

### 9.1. Hợp đồng API nên quy định cụ thể

Một hợp đồng đầu vào có thể yêu cầu:

~~~text
occurredAt:
  type: ISO 8601 / RFC 3339 offset timestamp
  required: true
  examples:
    - 2026-11-14T09:30:00.123+07:00
    - 2026-11-14T02:30:00.123Z
  reject:
    - 2026-11-14 09:30
    - 14/11/2026 09:30
    - 2026-11-14T09:30:00  (không có offset)
storagePrecision: milliseconds
serverFields:
  - receivedAt
  - updatedAt
~~~

Các dạng ngày giờ không có offset chỉ nên được chấp nhận khi API **đồng thời cung cấp zone/định nghĩa timezone** và quy trình xử lý giờ nhập nhằng.

### 9.2. Không dùng thời gian client làm căn cứ bảo mật

Nếu một chương trình được phép gửi `expiresAt` tùy ý, nó có thể tạo phiên dài hàng năm. Nếu giao dịch chấp nhận `paidAt` từ trình duyệt để quyết định thời điểm thanh toán, client có thể giả mạo thời gian.

Hệ thống cần phân biệt:

- **Thời gian client khai báo** cho mục đích ghi nhận/hiển thị.
- **Thời gian server chấp nhận** theo chính sách.
- **Sự kiện nghiệp vụ có thẩm quyền** từ dịch vụ thanh toán/đơn hàng.

Timestamp chỉ là một thuộc tính; nguồn và quy trình xác nhận mới quyết định độ tin cậy.

## 10. Java: parse, chuẩn hóa, hiển thị và kiểm soát đồng hồ

Java `java.time` cung cấp những kiểu dữ liệu làm rõ khái niệm:

| Kiểu Java | Ý nghĩa |
| --- | --- |
| `Instant` | Một thời điểm tuyệt đối |
| `OffsetDateTime` | Ngày-giờ kèm UTC offset |
| `ZonedDateTime` | Ngày-giờ kèm ZoneId và quy tắc timezone |
| `LocalDate` | Ngày trên lịch, chưa có timezone |
| `LocalTime` | Giờ trong ngày |
| `LocalDateTime` | Ngày và giờ địa phương, chưa biết instant |
| `Duration` | Khoảng thời gian dựa trên giây/nano |
| `Period` | Khoảng lịch dựa trên năm/tháng/ngày |
| `Clock` | Nguồn thời gian có thể thay thế khi kiểm thử |

### 10.1. Chuyển offset time thành Instant

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class TimestampExample {
    public static void main(String[] args) {
        String fromClient = "2026-11-14T09:30:00.123+07:00";

        Instant instant = OffsetDateTime.parse(fromClient).toInstant();
        System.out.println(instant);
        // 2026-11-14T02:30:00.123Z

        ZonedDateTime inVietnam = instant.atZone(
            ZoneId.of("Asia/Ho_Chi_Minh")
        );
        System.out.println(inVietnam.toLocalDateTime());
        // 2026-11-14T09:30:00.123
    }
}
~~~

Nếu dùng `LocalDateTime.parse(fromClient)` với input có offset, parsing sẽ không tương đương; `LocalDateTime` không có khái niệm offset. Hãy chọn kiểu parse theo **hợp đồng của field**.

### 10.2. Dùng Clock để kiểm thử server-generated time

Thay vì gọi `Instant.now()` rải rác trong code nghiệp vụ, có thể đưa `Clock` vào service:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public final class EventClock {
    private final Clock clock;

    public EventClock(Clock clock) {
        this.clock = clock;
    }

    public Instant receivedAt() {
        // Chủ động thống nhất độ chính xác lưu trữ đến ms.
        return clock.instant().truncatedTo(ChronoUnit.MILLIS);
    }
}
~~~

Production:

~~~java
EventClock eventClock = new EventClock(Clock.systemUTC());
Instant receivedAt = eventClock.receivedAt();
~~~

Kiểm thử:

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-14T02:30:02.491Z"),
    java.time.ZoneOffset.UTC
);

EventClock eventClock = new EventClock(fixed);
System.out.println(eventClock.receivedAt());
// 2026-11-14T02:30:02.491Z
~~~

Lợi ích là test không phụ thuộc giờ thật của máy, zone mặc định hoặc thời gian trôi giữa các câu lệnh.

### 10.3. Phát hiện DST overlap trong Java

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public class DstExample {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);

        List<ZoneOffset> offsets =
            zone.getRules().getValidOffsets(local);

        System.out.println(offsets); // [-04:00, -05:00]
        // Hai offset: người dùng phải xác nhận lựa chọn.
    }
}
~~~

Nếu `getValidOffsets(local)` trả:

- **0 offset:** thời gian địa phương rơi vào khoảng không tồn tại.
- **1 offset:** có một instant hợp lệ theo zone.
- **2 offset:** thời gian bị nhập nhằng vì DST overlap.

Trường hợp ứng dụng tự chọn offset sớm/muộn phải được **định nghĩa rõ trong hợp đồng lịch hẹn**.

### 10.4. Tính khoảng ngày theo timezone

Ví dụ API muốn lọc đơn trong ngày `2026-11-14` của một cửa hàng ở Việt Nam:

~~~java
import java.time.*;

ZoneId shopZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.parse("2026-11-14");

Instant from = day.atStartOfDay(shopZone).toInstant();
Instant to = day.plusDays(1).atStartOfDay(shopZone).toInstant();

System.out.println(from); // 2026-11-13T17:00:00Z
System.out.println(to);   // 2026-11-14T17:00:00Z
~~~

Tính **hai đầu ngày riêng theo quy tắc zone** an toàn hơn lấy `from.plus(24, HOURS)` đối với các zone có DST.

## 11. MongoDB: lưu Date, tạo mốc thời gian và truy vấn range

Ví dụ collection sự kiện:

~~~javascript
db.events.insertOne({
  tenantId: "merchant-a",
  eventId: "evt-9001",
  orderId: "O900",
  occurredAt: ISODate("2026-11-14T02:30:00.123Z"),
  receivedAt: ISODate("2026-11-14T02:30:02.491Z"),
  sourceTimeZone: "Asia/Ho_Chi_Minh"
});
~~~

### 11.1. Tạo index cho đường truy cập

Giả sử API tìm 20 sự kiện mới nhất của một tenant:

~~~javascript
db.events.createIndex({
  tenantId: 1,
  occurredAt: -1,
  eventId: 1
});
~~~

Truy vấn ngày UTC `2026-11-14`:

~~~javascript
const from = ISODate("2026-11-14T00:00:00.000Z");
const to = ISODate("2026-11-15T00:00:00.000Z");

db.events.find({
  tenantId: "merchant-a",
  occurredAt: { $gte: from, $lt: to }
})
.sort({ occurredAt: -1, eventId: 1 })
.limit(20);
~~~

Sử dụng khoảng **đóng bên trái, mở bên phải**: `[from, to)`. Một event nằm đúng `to` thuộc ngày tiếp theo, không nằm đồng thời trong cả hai ngày. Cách này cũng tránh phải đoán “mili giây cuối cùng của ngày”.

Nếu ngày hỏi là ngày địa phương của shop, **chuyển ranh giới sang UTC ở lớp ứng dụng** rồi đưa hai instant vào query. Không nên gắn `Z` vào giờ địa phương một cách tùy tiện.

### 11.2. Server-generated updatedAt

MongoDB cho phép gắn thời điểm máy chủ khi cập nhật:

~~~javascript
db.orders.updateOne(
  { tenantId: "merchant-a", orderId: "O900" },
  {
    $set: { status: "SHIPPED" },
    $currentDate: { updatedAt: true }
  }
);
~~~

`$currentDate` với giá trị `true` đặt trường thành kiểu Date theo thời gian máy chủ MongoDB. Đây phù hợp với **thời điểm cập nhật**, nhưng không phải bằng chứng rằng mọi replica đã nhận ghi ngay lúc đó, hay rằng `updatedAt` là một thứ tự tuyệt đối có thể giải quyết mọi ghi đồng thời.

Đối với `createdAt`, cần tạo **một lần tại thời điểm tạo đối tượng theo hợp đồng**, không cập nhật lại ở mỗi lần sửa. Nếu cần tạo mốc trong database, dùng cơ chế server-side phù hợp với phiên bản MongoDB và đặt rõ ngữ nghĩa trường.

### 11.3. Sắp xếp nhiều event cùng millisecond

Nếu `occurredAt` giống nhau, cần một khóa phụ `eventId` để tạo thứ tự ổn định. Khi phân trang, cursor nên chứa cả:

~~~text
lastOccurredAt
lastEventId
~~~

chứ không chỉ lưu timestamp. Nếu chỉ dùng một `occurredAt`, trang tiếp theo có thể **bỏ sót hoặc lặp** các event cùng milli giây.

### 11.4. MongoDB TTL index

Một collection session có trường `expiresAt` kiểu BSON Date:

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

`expireAfterSeconds: 0` biểu thị hết hạn dựa trên chính giá trị thời điểm `expiresAt`. Nhưng TTL cleanup của MongoDB diễn ra **bất đồng bộ**, không cam kết document biến mất đúng mili giây được chỉ định.

Nếu bảo mật yêu cầu token không còn hợp lệ ngay sau `expiresAt`, API phải **tự kiểm tra thời gian hết hạn khi xác thực**. TTL index chỉ là cơ chế dọn dữ liệu nền, không thay thế kiểm tra quyền và hạn token.

## 12. Cassandra: timestamp, partition theo thời gian và clustering order

Trong mô hình wide-column, thời gian còn ảnh hưởng trực tiếp tới **khóa phân vùng và thứ tự đọc**.

Giả sử một thiết bị IoT gửi dữ liệu liên tục. Ta muốn đọc dữ liệu của thiết bị theo ngày và thời gian giảm dần.

~~~sql
CREATE TABLE events_by_device_day (
    tenant_id text,
    device_id text,
    day_utc date,
    occurred_at timestamp,
    event_id uuid,
    received_at timestamp,
    payload text,
    PRIMARY KEY (
        (tenant_id, device_id, day_utc),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

- `(tenant_id, device_id, day_utc)` là **partition key**.
- `occurred_at` là clustering column đầu tiên, sắp theo thời gian giảm dần.
- `event_id` phân biệt những sự kiện trùng mốc mili giây.
- `received_at` giúp biết lúc hệ thống nhận, nhưng không quyết định thứ tự đọc ở bảng này.

### 12.1. Quy ước bucket UTC

Một sự kiện có:

~~~text
occurredAt = 2026-11-14T00:15:00+07:00
           = 2026-11-13T17:15:00Z
~~~

Nếu bucket được định nghĩa theo **ngày UTC**, `day_utc` phải là `2026-11-13`, **không phải** `2026-11-14`. Ghi theo ngày local nhưng đọc theo ngày UTC sẽ khiến ứng dụng tìm sai partition.

Đây là quyết định schema cần ghi rõ:

~~~text
day_utc := UTC_DATE(occurred_at)
~~~

Nếu mục tiêu nghiệp vụ là hiển thị dữ liệu theo **ngày của từng shop**, có thể xây một đường truy cập khác dựa trên ngày local của shop, nhưng cần lưu zone/quy tắc định ngày và xử lý thay đổi cấu hình zone một cách có chủ đích.

### 12.2. Ghi với offset rõ ràng

~~~sql
INSERT INTO events_by_device_day (
    tenant_id, device_id, day_utc, occurred_at,
    event_id, received_at, payload
) VALUES (
    'merchant-a',
    'sensor-17',
    '2026-11-14',
    '2026-11-14T02:30:00.123Z',
    85c1bdc5-9367-4648-a283-408cfc74e5db,
    '2026-11-14T02:30:02.491Z',
    '{"temperatureC":28.4}'
);
~~~

Trong ví dụ này, `occurred_at` được lưu bằng `timestamp` với độ chính xác mili giây. Nếu nguồn gửi nano giây, phải có quy tắc chuyển đổi trước khi bind vào CQL.

### 12.3. Truy vấn một partition

~~~sql
SELECT occurred_at, event_id, received_at, payload
FROM events_by_device_day
WHERE tenant_id = 'merchant-a'
  AND device_id = 'sensor-17'
  AND day_utc = '2026-11-14'
LIMIT 20;
~~~

Kết quả nằm trong **một ngày UTC và một thiết bị**, theo clustering order đã khai báo. `LIMIT 20` không có nghĩa là top-20 toàn bộ lịch sử nếu giờ/ngày hiện tại có ít hơn 20 sự kiện. Ứng dụng có thể phải đọc ngày trước.

### 12.4. Truy vấn xuyên ranh giới ngày

Ví dụ tìm sự kiện từ `2026-11-13T23:50Z` đến `2026-11-14T00:10Z`. Ứng dụng cần đọc **hai partition ngày**:

~~~text
Partition day_utc = 2026-11-13
  occurred_at >= 23:50Z và < 00:00Z ngày sau

Partition day_utc = 2026-11-14
  occurred_at >= 00:00Z và < 00:10Z
~~~

Sau đó kết hợp dữ liệu theo `occurred_at` và `event_id`. Clustering order chỉ sắp bên trong một partition, không tự sắp toàn bộ các partition.

### 12.5. CQL timestamp khác write timestamp

Trong Cassandra, giá trị cột `occurred_at` trả lời **sự kiện xảy ra khi nào**. Metadata write timestamp (*microseconds*) được Cassandra dùng trong quy tắc giải quyết xung đột cell trả lời câu hỏi khác: **phiên bản ghi nào có precedence khi nhiều mutation cùng tác động lên cell**.

Không nên:

~~~text
Giả định occurred_at lớn hơn
  -> Cassandra tự chọn hàng này là bản cập nhật đúng nhất
~~~

Trong hệ phân tán, các writer có thể sử dụng write timestamp khác nhau, kể cả có thể do client cung cấp tùy cấu hình; đồng hồ lệch có thể ảnh hưởng đến giải quyết xung đột. Với cập nhật nghiệp vụ cần kiểm soát phiên bản, hãy sử dụng **conditional update/CAS hoặc transaction phù hợp**, không dùng sự tình cờ của timestamp để thay thế quy tắc nghiệp vụ.

### 12.6. TTL trong Cassandra

CQL có thể gắn TTL theo **số giây** cho dữ liệu:

~~~sql
INSERT INTO events_by_device_day (
    tenant_id, device_id, day_utc, occurred_at,
    event_id, payload
) VALUES (
    'merchant-a', 'sensor-17', '2026-11-14',
    '2026-11-14T02:30:00.123Z',
    12345678-1234-4234-8234-1234567890ab,
    '{"temperatureC":28.4}'
) USING TTL 2592000;
~~~

`2592000` giây tương đương 30 ngày × 24 giờ × 3.600 giây, nhưng TTL được gắn với **thời điểm ghi theo cơ chế của DB**, không tự là “30 ngày kể từ occurredAt”. Nếu event được gửi muộn 10 ngày, chính sách giữ theo occurredAt sẽ khác TTL 30 ngày áp lúc ingest.

Cassandra cũng có tombstone sau TTL/xóa và cơ chế compaction/repair tương ứng. Không xem một TTL là bằng chứng dữ liệu sẽ biến mất vật lý đúng một thời điểm.

## 13. DynamoDB: ISO string, epoch number và TTL

Trong DynamoDB, ứng dụng phải **tự chuẩn hóa schema cho dữ liệu thời gian**, vì không có kiểu timestamp native theo cùng nghĩa BSON Date.

### 13.1. Chuỗi ISO cho sort key

Ví dụ thiết kế:

~~~text
PK = TENANT#merchant-a#ORDER#O900
SK = EVENT#2026-11-14T02:30:00.123Z#evt-9001
~~~

Nếu mọi timestamp đều được viết dạng **UTC `Z` và phần mili giây cố định 3 chữ số**, thứ tự từ điển của chuỗi ISO theo cấu trúc này phù hợp thứ tự thời gian trong phạm vi biểu diễn, với `eventId` làm tie-breaker.

Ngược lại, không trộn các giá trị như:

~~~text
2026-11-14T09:30:00+07:00
2026-11-14T02:30:00Z
2026-11-14T02:30:00.123Z
~~~

vào cùng một sort key rồi mặc định thứ tự chuỗi là thứ tự instant. Các chuỗi dùng **offset và độ dài phần lẻ khác nhau**, khiến sắp xếp theo ký tự không nhất thiết phản ánh thời gian thực.

### 13.2. Lưu bằng Number

Có thể lưu:

~~~json
{
  "eventId": "evt-9001",
  "occurredAtEpochMillis": 1794623400123
}
~~~

Khi query theo Number sort key, DynamoDB so giá trị số theo kiểu dữ liệu và quy tắc của nó. Phải thống nhất **đơn vị** giữa tất cả writer và query. Nếu một service dùng epoch seconds và service khác epoch milliseconds, index sẽ bị trộn hai thang thời gian khác nhau.

### 13.3. TTL của DynamoDB

Thuộc tính TTL của DynamoDB dùng **số epoch giây** trên trường Number được cấu hình. Ví dụ:

~~~text
expiresAtEpochSeconds = 1794709800
~~~

Đây không phải epoch milliseconds; đưa số mili giây vào trường TTL theo giây có thể khiến dữ liệu được coi là còn rất lâu mới hết hạn.

Việc xóa item hết hạn diễn ra **bất đồng bộ, thường không ngay tức thì**, nên ứng dụng vẫn cần tự kiểm tra `expiresAt` nếu quyền truy cập không được phép vượt quá hạn. Chính sách TTL cũng phải đi cùng quy định xóa trên GSI, backup, cache và bản sao dữ liệu phụ nếu có.

## 14. Redis: thời điểm tuyệt đối khác cơ chế hết hạn

Redis cung cấp `EXPIRE` và `PEXPIRE` để đặt **thời gian sống tương đối** tính bằng giây hoặc mili giây. Nó cũng hỗ trợ đặt thời điểm hết hạn tuyệt đối bằng các lệnh tương ứng với đơn vị giây/mili giây.

Ví dụ qua redis-cli:

~~~text
SET session:abc active EX 1800
TTL session:abc
PTTL session:abc
~~~

`EX 1800` nghĩa là đặt thời hạn **30 phút** tính từ lúc Redis xử lý lệnh theo cơ chế server. `TTL` trả giây còn lại; `PTTL` trả mili giây còn lại.

Điều này khác dữ kiện:

~~~json
{
  "sessionIssuedAt": "2026-11-14T02:30:00Z",
  "sessionExpiresAt": "2026-11-14T03:00:00Z"
}
~~~

Thuộc tính `sessionExpiresAt` mô tả **chính sách thời hạn**. TTL Redis giúp dọn khóa, nhưng nếu có yêu cầu bảo mật, code xác thực vẫn phải kiểm tra hiệu lực theo dữ kiện được tin cậy.

### 14.1. TTL không thay thế truy vấn theo thời gian

Một key còn tồn tại không bảo đảm nghiệp vụ vẫn hợp lệ nếu chính sách thay đổi. Một key đã biến mất vì eviction cũng không có nghĩa sự kiện đã hết hiệu lực. Phải tách **lớp cache và TTL** khỏi **nguồn dữ liệu chuẩn** quyết định trạng thái nghiệp vụ.

### 14.2. ZSET score và độ chính xác

Ví dụ:

~~~text
ZADD events:O900 1794623400123 evt-9001
ZRANGEBYSCORE events:O900 1794623400000 1794623500000
~~~

Ở đây score biểu diễn epoch milliseconds. Nếu cố dùng epoch nanoseconds `~1,8e18`, số double không giữ được mọi chữ số; các event rất gần nhau có thể có cùng score sau làm tròn. Khi cần thứ tự chính xác tới nano giây, hãy dùng biểu diễn khác hoặc tie-breaker phù hợp.

## 15. Truy vấn khoảng thời gian: dùng [from, to)

Một thói quen tốt là định nghĩa mọi truy vấn theo khoảng:

\[
[\,\text{from},\ \text{to}\,)
\]

Nghĩa là **bao gồm from** và **không bao gồm to**.

Ví dụ:

~~~text
Ngày UTC 2026-11-14:
  from = 2026-11-14T00:00:00.000Z
  to   = 2026-11-15T00:00:00.000Z

Điều kiện:
  occurredAt >= from
  occurredAt < to
~~~

Lợi ích:

- Hai khoảng ngày liên tiếp **không chồng lên nhau**.
- Không cần đoán timestamp cuối ngày như `23:59:59.999`.
- Ít phụ thuộc độ chính xác mili/micro/nano của engine.
- Dễ chia bucket ngày/giờ và ghép kết quả.

### 15.1. Vì sao tránh `<= 23:59:59.999`?

Nếu engine hỗ trợ micro giây, một sự kiện lúc:

~~~text
2026-11-14T23:59:59.999500Z
~~~

vẫn thuộc ngày 14 nhưng lớn hơn `23:59:59.999Z`. Khoảng `< 2026-11-15T00:00:00Z` bao gồm đúng sự kiện đó mà không phụ thuộc số chữ số phần lẻ.

### 15.2. Ngày địa phương phải đổi biên trước khi query

Người dùng chọn `2026-11-14` ở `Asia/Ho_Chi_Minh`. API:

1. Lấy `LocalDate` và `ZoneId`.
2. Tính đầu ngày ở zone.
3. Tính đầu ngày **tiếp theo** ở zone.
4. Đổi cả hai sang `Instant`.
5. Gửi query `occurredAt >= fromUtc AND occurredAt < toUtc`.

Với nhiều zone, hai biên UTC có thể không cách nhau đúng 86.400 giây vì DST. Không tính `to = from + 24h` khi yêu cầu là **một ngày lịch**.

### 15.3. Dữ liệu partition theo ngày

Nếu NoSQL phân vùng theo `day_bucket`, ứng dụng còn phải xác định **tất cả partition giao với [from, to)**. Một query qua nửa đêm có thể cần hai partition, kể cả khi chỉ có vài phút dữ liệu.

Không dựa vào một phép `ORDER BY` để suy ra thứ tự toàn cục của những hàng nằm ở nhiều partition. Phải merge theo timestamp và khóa phụ.

## 16. Sắp xếp, phân trang và cùng timestamp

Giả sử ba sự kiện:

~~~text
2026-11-14T02:30:00.123Z | evt-001
2026-11-14T02:30:00.123Z | evt-002
2026-11-14T02:30:00.122Z | evt-003
~~~

Một query chỉ `ORDER BY occurredAt DESC` không nhất thiết có thứ tự ổn định **giữa evt-001 và evt-002** nếu thiếu tie-breaker. Dùng:

~~~text
ORDER BY occurredAt DESC, eventId ASC
~~~

Theo thứ tự đó, cursor sau `evt-001` phải lưu cả:

~~~json
{
  "lastOccurredAt": "2026-11-14T02:30:00.123Z",
  "lastEventId": "evt-001"
}
~~~

Điều kiện tiếp tục phù hợp với thứ tự là:

~~~text
occurredAt < lastOccurredAt
OR (
  occurredAt = lastOccurredAt
  AND eventId > lastEventId
)
~~~

Đây là **mô tả điều kiện logic**; cách mã hóa query cụ thể phụ thuộc khả năng của engine. Nó giúp tránh bỏ qua các event trùng timestamp.

Nếu dữ liệu tiếp tục được ghi/xóa trong lúc phân trang, cần thêm chiến lược snapshot hoặc **high-water mark** cho tập kết quả nếu sản phẩm yêu cầu ổn định; tie-breaker chỉ giải quyết vấn đề thứ tự của các giá trị bằng nhau.

## 17. Thời gian sự kiện và thời gian tiếp nhận: dữ liệu đến muộn

Một thiết bị IoT mất mạng từ 10:00 tới 10:30, sau đó tải các sự kiện cũ lên:

~~~text
Event A:
  occurredAt = 10:02
  receivedAt = 10:31

Event B:
  occurredAt = 10:25
  receivedAt = 10:31

Event C:
  occurredAt = 10:31
  receivedAt = 10:31
~~~

Nếu ứng dụng hiển thị lịch sử đo theo lúc sự kiện **xảy ra**, thứ tự là C, B, A. Nếu cần màn hình “dữ liệu **vừa được nhận**”, các sự kiện có thể được xếp khác theo `receivedAt`, cần khóa phụ cho các mốc giống nhau.

Đây là hai đường truy cập khác nhau:

| Đường đọc | Khóa sắp xếp | Ý nghĩa |
| --- | --- | --- |
| Lịch sử thực tế | `occurredAt` | Thứ tự theo nguồn quan sát |
| Nhật ký nhập hệ thống | `receivedAt` | Thứ tự tiếp nhận của hạ tầng |
| Trạng thái nghiệp vụ mới nhất | `version/sequence` hợp lệ | Thứ tự thay đổi đã được chấp nhận |

**Không dùng một trường `timestamp` mơ hồ để phục vụ cả ba mục tiêu.**

### 17.1. Watermark và dữ liệu đến muộn

Trong xử lý luồng, một **watermark** thường biểu diễn ước lượng/khẳng định rằng hệ thống đã tiến đến một mốc event-time với mức chấp nhận dữ liệu đến muộn theo chính sách. Nó không có nghĩa mọi thiết bị đều luôn đúng giờ.

Ví dụ dashboard tổng hợp theo giờ:

~~~text
Window theo occurredAt: 10:00–11:00
Chấp nhận event đến muộn: 15 phút sau khi đóng window
~~~

Khi event lúc 10:25 được nhận lúc 11:05, hệ thống có thể cập nhật tổng hợp của window 10:00–11:00. Nếu nhận lúc 13:00, chính sách có thể:

- Bỏ qua khỏi tổng hợp nhanh nhưng lưu lịch sử.
- Gửi vào luồng sửa kết quả/backfill.
- Ghi nhận ngoại lệ cần đối soát.

Watermark, lateness và correction policy phải được định nghĩa cùng nhau; không thể suy ra đúng sai chỉ từ `receivedAt > occurredAt`.

### 17.2. Đồng hồ client lệch

Một event có:

~~~text
occurredAt = 15:00 UTC
receivedAt = 12:00 UTC
~~~

Nếu không có cơ chế time travel, có thể client đang chạy **nhanh hơn ba giờ** hoặc bản ghi được gán tương lai. Một pipeline có thể:

1. Giữ nguyên giá trị nguồn để điều tra, nếu chính sách cho phép.
2. Gắn cờ `CLOCK_SKEW_SUSPECTED`.
3. Không cho timestamp client tự điều khiển quyền hoặc hạn tài chính.
4. Dùng sequence/version nghiệp vụ khi cần xác định thứ tự xử lý.
5. Áp dụng ngưỡng lệch tối đa theo loại thiết bị hoặc sự kiện.

Không được tự động sửa mọi `occurredAt` bằng `receivedAt`, vì như vậy dữ liệu offline hợp lệ sẽ mất thời gian quan sát gốc.

## 18. Cập nhật đồng thời: đừng dùng updatedAt làm phiên bản duy nhất

Giả sử hai client cùng đọc đơn O900:

~~~text
Client A đọc: status=PAID, updatedAt=12:00:00.123
Client B đọc: status=PAID, updatedAt=12:00:00.123
~~~

A cập nhật `READY_TO_SHIP`, B cập nhật `CANCELLED`. Nếu chỉ dùng thời điểm cập nhật để đoán lần nào hợp lệ, có những rủi ro:

- Cả hai ghi trong cùng mili giây và có timestamp bằng nhau.
- Đồng hồ hai máy lệch nhau.
- Event từ hệ thống khác đến muộn.
- Một request retry tạo timestamp mới dù tác động nghiệp vụ đã xảy ra.

Hãy dùng **version hoặc điều kiện trạng thái có thẩm quyền**:

~~~text
UPDATE Order O900
IF version = 4 AND status = PAID
SET status = READY_TO_SHIP,
    version = 5,
    updatedAt = serverClockNow()
~~~

Đây là pseudocode. Tùy engine có thể dùng compare-and-set, conditional writes, transaction hoặc cơ chế tương ứng.

Trong một lần cập nhật thành công:

- `version` giúp phân biệt và kiểm soát thứ tự thay đổi nghiệp vụ.
- `updatedAt` giúp hiển thị/quan sát thời điểm ghi nhận.
- `eventId` hoặc idempotency key giúp phân biệt **một ý định được retry** với hai ý định khác nhau.

Ba trường phục vụ những mục đích khác nhau.

### 18.1. Last-write-wins không thay thế nghiệp vụ

Một số NoSQL dùng quy tắc giải quyết xung đột dựa trên timestamp hoặc cơ chế ưu tiên phiên bản. Điều đó bảo đảm hệ thống có quy tắc chọn một giá trị, **không bảo đảm giá trị được chọn là kết quả nghiệp vụ đúng**.

Ví dụ một đồng hồ writer chạy nhanh bất thường có thể tạo timestamp có ưu thế dù sự kiện được gửi sớm; hoặc một trạng thái `CANCELLED` được ghi sau một giao dịch hoàn tất nhưng không được phép theo state machine.

Với dữ liệu quan trọng, hãy xác định transition hợp lệ, writer authority, version và cơ chế xử lý xung đột thay vì mặc định “timestamp lớn hơn là đúng”.

### 18.2. Thời gian và thứ tự sự kiện là hai khái niệm riêng

Một luồng sự kiện có thể có:

~~~text
eventId=E10, version=10, occurredAt=12:00:02
eventId=E11, version=11, occurredAt=12:00:01
~~~

Nếu sự kiện version 11 được chấp nhận sau version 10 nhưng client gửi timestamp sớm hơn, **thứ tự nghiệp vụ** vẫn có thể là E10 rồi E11. `occurredAt` phản ánh thời gian nguồn khai báo, còn `version` phản ánh thứ tự được authority xác nhận.

## 19. TTL, thời hạn hiệu lực và thời gian lưu trữ

Không nên đồng nhất ba khái niệm:

1. **Business expiration:** thời điểm token, ưu đãi hoặc phiên trở nên không hợp lệ.
2. **Database TTL:** cơ chế xóa/dọn dữ liệu mà database thực thi.
3. **Retention policy:** quy định cần giữ dữ liệu bao lâu cho vận hành, phân tích, pháp lý hoặc quyền riêng tư.

Ví dụ:

~~~text
Token issuedAt  = 2026-11-14T02:30:00Z
Token expiresAt = 2026-11-14T03:00:00Z
DB TTL          = 1800 giây, nếu được đặt cùng lúc với mốc issue
~~~

Nếu token được tạo từ một nơi nhưng ghi cache sau 10 phút rồi mới đặt TTL 1800 giây, cache có thể tồn tại **40 phút tính từ issuedAt**, trừ khi chính sách dùng deadline tuyệt đối hoặc tính lại TTL còn lại.

### 19.1. Chọn absolute deadline hay relative TTL?

| Yêu cầu | Biểu diễn nên ưu tiên |
| --- | --- |
| “Hết hạn đúng lúc 03:00 UTC” | `expiresAt` là instant tuyệt đối |
| “Hết hạn 30 phút sau lúc tạo ở server” | Tính `expiresAt = createdAt + 30 phút`, có thể đặt TTL tương ứng |
| “Chỉ giữ log 30 ngày từ occurredAt” | Retention theo event time, có quy tắc cho dữ liệu đến muộn |
| “Xóa cache 30 phút sau lần ghi cuối” | TTL tương đối tại cache |
| “Giữ hồ sơ theo lịch địa phương đến hết ngày cuối tháng” | Quy tắc lịch + timezone + chính sách retention |

Nếu dữ liệu cần **xóa pháp lý hoặc bí mật ngay khi hết hạn**, không chỉ trông chờ job TTL không đồng bộ. Quyền đọc phải được kiểm tra tại request và cần cơ chế xóa/ẩn trên các bản sao liên quan.

### 19.2. TTL không phải lịch sử kiểm toán

TTL có thể khiến dữ liệu bị xóa, nhưng không chứng minh sự kiện đó **chưa từng xảy ra**. Nếu cần điều tra hoạt động, có thể cần một log kiểm toán riêng với chính sách lưu trữ và bảo vệ tương ứng.

Ngược lại, không được tự giữ dữ liệu vô thời hạn “để tiện đối soát” nếu chính sách dữ liệu yêu cầu xóa sau một khoảng cụ thể.

## 20. Clock skew, NTP và đo độ trễ

### 20.1. Đồng hồ tường (*wall clock*) có thể nhảy

Đồng hồ hệ thống dùng để tạo `Instant.now()` có thể bị chỉnh, đồng bộ lại hoặc chịu ảnh hưởng cấu hình. Khi đo thời gian một thao tác, nếu lấy:

~~~java
long start = System.currentTimeMillis();
doWork();
long elapsed = System.currentTimeMillis() - start;
~~~

kết quả có thể bị ảnh hưởng bởi việc wall clock bị điều chỉnh.

Đo khoảng thời gian thực thi trong **cùng tiến trình JVM**, nên ưu tiên đồng hồ đơn điệu:

~~~java
long start = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - start;
~~~

`System.nanoTime()` thích hợp để đo **elapsed time**, nhưng giá trị nó trả về **không phải timestamp UTC để lưu vào database hoặc gửi qua API**. Không được trộn đơn vị và mốc của hai loại đồng hồ.

### 20.2. Đồng bộ thời gian giữa các node

NTP hoặc cơ chế đồng bộ phù hợp giúp giảm sai lệch đồng hồ, nhưng **không biến nhiều máy thành một clock hoàn toàn chính xác và đồng nhất trong mọi tình huống**. Các chỉ số hữu ích:

- Độ lệch clock so với nguồn tham chiếu.
- Tuổi của lần đồng bộ cuối.
- Nguồn thời gian bị mất kết nối hay không.
- Chênh lệch `receivedAt - occurredAt` theo loại thiết bị.
- Tỷ lệ event có timestamp ở tương lai bất thường.

Khi thứ tự cập nhật có ý nghĩa quan trọng, cần cơ chế **logical version, sequence hoặc transaction**; không chỉ dựa vào đồng bộ đồng hồ.

### 20.3. Đo thời gian xuyên dịch vụ

Nếu request đi qua service A → B → C, không thể chỉ lấy:

~~~text
C.receivedAt - A.sentAt
~~~

rồi chắc chắn đó là latency chính xác nếu hai máy lệch clock. Hệ thống tracing phân tán thường dùng nhiều mốc quan sát và thông tin về span; cần hiểu hạn chế clock skew khi phân tích timestamp liên dịch vụ.

Để đo thời gian một bước bên trong một service, dùng monotonic clock tại đó. Để suy luận tổng latency nhiều bước, cần telemetry và cơ chế đo phù hợp với hệ thống phân tán.

## 21. Thiết kế API ingest minh họa bằng Java

Ví dụ sử dụng `Clock` để phân biệt thời gian client khai báo và thời gian ingress server tạo.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

record ClientEvent(
    String tenantId,
    String eventId,
    String orderId,
    String occurredAt
) {}

record StoredEvent(
    String tenantId,
    String eventId,
    String orderId,
    Instant occurredAt,
    Instant receivedAt
) {}

public class EventIngestService {
    private final Clock clock;

    public EventIngestService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public StoredEvent toStoredEvent(ClientEvent input) {
        Objects.requireNonNull(input);

        // Client bắt buộc gửi timestamp có offset.
        Instant observed = OffsetDateTime
            .parse(input.occurredAt())
            .toInstant();

        // Server xác định thời điểm ingress. Cố ý làm tròn xuống ms
        // để khớp nơi lưu chỉ hỗ trợ millisecond.
        Instant received = clock.instant()
            .truncatedTo(ChronoUnit.MILLIS);
        Instant occurred = observed
            .truncatedTo(ChronoUnit.MILLIS);

        return new StoredEvent(
            input.tenantId(),
            input.eventId(),
            input.orderId(),
            occurred,
            received
        );
    }
}
~~~

Cách dùng:

~~~java
var service = new EventIngestService(Clock.systemUTC());

var input = new ClientEvent(
    "merchant-a",
    "evt-9001",
    "O900",
    "2026-11-14T09:30:00.123+07:00"
);

StoredEvent stored = service.toStoredEvent(input);
System.out.println(stored.occurredAt());
// 2026-11-14T02:30:00.123Z
~~~

**Trong ứng dụng thật**, cần thêm:

- Kiểm tra quyền `tenantId` từ danh tính xác thực; không tin client tự đặt tenant.
- Kiểm tra ID và schema trước khi ghi.
- Giới hạn timestamp ở quá khứ/tương lai theo chính sách.
- Xử lý sai định dạng và trả lỗi API có ý nghĩa.
- Ghi **eventId ổn định** để chống xử lý lặp khi retry.
- Quy tắc khi timestamp đầu vào có precision cao hơn ms.
- Lưu trên cùng metric/kiểu thời gian đã xác định.

Đoạn mã chỉ minh họa **phân tách nguồn thời gian và chuẩn hóa**; nó không tự thực hiện giao dịch, idempotency hay kiểm tra quyền.

### 21.1. Vì sao không tự động thay occurredAt bằng receivedAt?

Nếu một người dùng ghi sự kiện khi offline và đồng bộ sau một giờ, thay `occurredAt` bằng `receivedAt` sẽ làm sai lịch sử. Hợp đồng nên giữ cả hai nếu nghiệp vụ cần phân biệt **lúc quan sát** và **lúc hệ thống biết tới**.

Nếu dữ liệu client không đáng tin, vẫn có thể giữ timestamp nguồn như một giá trị khai báo có cờ tin cậy, đồng thời dùng server time hoặc sequence cho những quyết định cần thẩm quyền.

## 22. Kiểm thử các góc cạnh ngày giờ

Một bài kiểm thử ngày giờ có ý nghĩa phải bao gồm nhiều hơn “parse một chuỗi ISO hợp lệ”.

| Tình huống | Input hoặc điều kiện | Điều cần kiểm chứng |
| --- | --- | --- |
| Cùng instant, khác offset | `09:30+07:00`, `02:30Z` | So sánh bằng nhau sau chuẩn hóa |
| Ngày địa phương | Ngày 14/11 ở Việt Nam | Biên UTC đúng ngày local |
| Timezone mặc định thay đổi | JVM chạy UTC vs một zone khác | Kết quả lưu instant không thay đổi |
| DST gap | New York `2026-03-08 02:30` | Reject hoặc resolve theo chính sách |
| DST overlap | New York `2026-11-01 01:30` | Bắt buộc xử lý hai offset hợp lệ |
| Hai event trùng mili giây | Cùng timestamp, khác eventId | Không ghi đè, sort/paging ổn định |
| Precision cao | Input có 9 chữ số phần lẻ | Có quy tắc cắt/làm tròn rõ ràng |
| Đơn vị nhầm | Epoch ms được parse như giây | Trả lỗi hoặc phát hiện sai đơn vị |
| Đồng hồ client nhanh | occurredAt nằm xa trong tương lai | Gắn cờ/áp chính sách, không tin mù |
| Offline/backfill | receivedAt muộn hơn occurredAt nhiều giờ | Giữ lịch sử và thứ tự event time |
| Timeout + retry | Gửi lại cùng eventId | Không tạo thêm sự kiện nghiệp vụ |
| Hai writer đồng thời | Cùng updatedAt | Version/condition ngăn lost update |
| TTL hết hạn | Token đến hạn nhưng record chưa bị DB xóa | API vẫn từ chối truy cập |
| Ranh giới bucket | `23:59:59.999` và `00:00:00.000` | Thuộc đúng partition |
| Đọc nhiều ngày | Query qua midnight | Ghép đủ partition và sort đúng |

### 22.1. Kiểm thử chuyển đổi timezone không phụ thuộc môi trường

Với Java:

~~~java
Instant a = OffsetDateTime.parse(
    "2026-11-14T09:30:00.123+07:00"
).toInstant();

Instant b = Instant.parse(
    "2026-11-14T02:30:00.123Z"
);

if (!a.equals(b)) {
    throw new AssertionError("Hai biểu diễn phải cùng instant");
}
~~~

### 22.2. Kiểm thử “ngày lịch” ở vùng có DST

Với `America/New_York`, ngày bắt đầu DST có thể không dài đúng 24 giờ. Khi tính khoảng ngày bằng `LocalDate.atStartOfDay(zone)` và ngày tiếp theo, hãy kiểm tra số giờ chênh lệch theo quy tắc zone, thay vì luôn assert `24`.

### 22.3. Kiểm thử không mất bản ghi khi trùng timestamp

Tạo 1.000 event với cùng `occurredAt` nhưng khác `eventId`. Ghi vào bảng/index theo thiết kế. Truy vấn phân trang toàn bộ và xác nhận:

~~~text
Số event duy nhất đọc được = 1.000
Không có ID trùng giữa các trang
Không thiếu ID do điều kiện cursor chỉ dùng timestamp
~~~

Đây là một bài test quan trọng hơn việc chỉ kiểm tra `LIMIT 20` trả đúng 20 dòng.

## 23. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng hơn |
| --- | --- | --- |
| Lưu `2026-11-14 09:30` không có offset/zone | Không xác định được instant | Dùng offset timestamp hoặc local time + IANA zone |
| Xem offset `+07:00` là zone ID đầy đủ | Sai lịch lặp/DST ở những khu vực đổi offset | Lưu zone theo khu vực khi cần lịch tương lai |
| Lấy ngày UTC thay cho ngày của shop | Đơn gần nửa đêm rơi vào ngày sai | Chuyển biên LocalDate theo zone shop |
| Dùng `<= 23:59:59.999` cho mọi engine | Thiếu sự kiện có precision cao hơn ms | Dùng khoảng `[from, to)` |
| Lưu epoch nanoseconds bằng JS Number | Mất chữ số thấp | Dùng biểu diễn số nguyên an toàn/chuỗi/cặp giây+nano |
| Dùng `int` cho epoch milliseconds | Tràn số | Dùng `long`/Number 64-bit |
| Coi UUID/ID có timestamp là đồng hồ tuyệt đối | Thứ tự không được bảo đảm giữa mọi writer | Có timestamp + tie-breaker hoặc sequence/version |
| Dùng `updatedAt` làm điều kiện chống concurrent writes duy nhất | Đồng hồ lệch hoặc timestamp trùng | Conditional update theo version/state |
| Coi `receivedAt` bằng `occurredAt` | Sai lịch sử offline | Lưu hai mốc có ý nghĩa riêng |
| Tin thời gian client để xác nhận hết hạn/giá trị tài chính | Có thể bị giả mạo hoặc sai clock | Kiểm tra bằng nguồn server/nghiệp vụ có thẩm quyền |
| Dùng TTL DB thay kiểm tra token expiry | Record có thể chưa bị xóa đúng lúc | Kiểm tra `expiresAt` tại API, TTL để dọn |
| Trộn ISO strings khác offset trong sort key | Thứ tự từ điển khác thứ tự instant | Chuẩn hóa UTC và độ dài phần lẻ |
| Chỉ dùng timestamp làm khóa duy nhất | Hai event trùng thời gian đè nhau | Thêm eventId/tie-breaker |
| Dùng `Instant.now()` trong mọi test | Test phụ thuộc clock thật, khó tái lập | Inject `Clock.fixed` |
| Dùng `System.nanoTime()` làm timestamp DB | Không có mốc Unix epoch | Chỉ dùng đo elapsed trong cùng tiến trình |

## 24. Bài tập vận dụng

### Bài 1 — Chuẩn hóa hai múi giờ

Client A gửi:

~~~text
2026-11-14T09:30:00.123+07:00
~~~

Client B gửi:

~~~text
2026-11-14T02:30:00.123Z
~~~

Hãy chỉ ra hai giá trị có cùng instant không, chọn biểu diễn lưu trữ và giải thích vì sao không được so trực tiếp hai chuỗi trên theo từ điển.

### Bài 2 — Truy vấn ngày địa phương

Một cửa hàng ở `Asia/Ho_Chi_Minh` muốn thống kê đơn ngày `2026-11-14`. Hãy tính `fromUtc`, `toUtc` và viết điều kiện `createdAt >= fromUtc AND createdAt < toUtc`. Nêu vì sao dùng ngày `2026-11-14T00:00:00Z` đến ngày sau là sai với yêu cầu.

### Bài 3 — DST và lịch hẹn

Người dùng đặt lịch `2026-11-01T01:30` ở `America/New_York`. Hãy tìm các offset hợp lệ và hai instant tương ứng. Đề xuất UX yêu cầu người dùng xác định lựa chọn, sau đó mô tả dữ liệu cần lưu.

### Bài 4 — Mất precision

Một thiết bị gửi:

~~~text
2026-11-14T02:30:00.123456789Z
~~~

MongoDB BSON Date và Cassandra CQL timestamp trong ngữ cảnh bài này lưu đến mili giây. Hãy nêu phần thông tin bị mất nếu chuyển sang `02:30:00.123Z`. Nếu ứng dụng bắt buộc phân biệt thứ tự giữa nhiều sự kiện trong cùng mili giây, những lựa chọn mô hình khóa nào phù hợp?

### Bài 5 — TTL và truy cập

Token có `expiresAt = 03:00:00Z`, nhưng bản ghi Redis/MongoDB vẫn còn lúc `03:00:03Z`. API có được chấp nhận token không? Giải thích khác biệt giữa thời hạn nghiệp vụ và cơ chế dọn dữ liệu.

### Bài 6 — Event time so với ingest time

Ba sự kiện có:

~~~text
E1: occurredAt=10:00, receivedAt=10:30
E2: occurredAt=10:20, receivedAt=10:21
E3: occurredAt=10:10, receivedAt=10:40
~~~

Hãy đưa ra thứ tự cho màn hình **“sự kiện thực tế mới nhất”** và màn hình **“bản ghi được hệ thống tiếp nhận mới nhất”**. Nêu cách xây đường truy cập và phân trang nếu nhiều event có timestamp bằng nhau.

### Bài 7 — Cập nhật đồng thời

Hai request cùng đọc `Order.version = 7`, mỗi request muốn chuyển đơn sang một trạng thái khác. Hãy thiết kế cách dùng conditional write/version; sau đó giải thích vai trò của `updatedAt` và vì sao không được coi nó là khóa chống xung đột duy nhất.

### Bài 8 — Thiết kế schema đa hệ quản trị

Một ứng dụng cùng cần:

- MongoDB để lưu document và query lịch sử.
- Cassandra để đọc event theo thiết bị/ngày.
- Redis để lưu session có hạn.
- DynamoDB để lưu trạng thái workflow với TTL.

Hãy lập bảng cho từng trường thời gian: ý nghĩa, nơi tạo, kiểu lưu trữ, precision, timezone và cách hết hạn. Sau đó đề xuất các test chung để phát hiện nhầm giây/mili giây và sai ranh giới ngày.

## Kết luận

**Ngày giờ là dữ liệu có ngữ nghĩa, không chỉ là một chuỗi hoặc một số.** Trong NoSQL, lựa chọn kiểu, cách đặt khóa và nguồn tạo timestamp có thể ảnh hưởng đồng thời tới độ chính xác, thứ tự truy vấn, cập nhật đồng thời, TTL, bảo mật và khả năng đối soát.

Những nguyên tắc cần giữ:

- **Instant** dùng cho thời điểm đã xảy ra và so sánh toàn hệ thống; **LocalDate/LocalTime + IANA zone** dùng khi nghiệp vụ nói về lịch và giờ địa phương.
- **UTC offset không thay thế time zone** trong những quy tắc lịch có DST; xử lý minh bạch các giờ không tồn tại hoặc xuất hiện hai lần.
- **Precision phải khớp hệ lưu trữ**: không mặc định nano giây của client được giữ trong BSON Date hoặc CQL timestamp; tránh trộn đơn vị epoch.
- **Timestamp do client tạo và server tạo trả lời câu hỏi khác nhau**: `occurredAt` cho sự kiện nguồn, `receivedAt` cho lúc tiếp nhận, `version` cho thứ tự nghiệp vụ.
- **Truy vấn ngày dùng khoảng [from, to)** và tính biên theo múi giờ đúng; với partition theo thời gian cần đọc đủ bucket và dùng ID để xử lý trùng timestamp.
- **TTL chỉ là cơ chế hết hạn/dọn dữ liệu của storage**; quyền truy cập và thời hạn nghiệp vụ phải được thực thi ở lớp có thẩm quyền.
- **Không dùng wall-clock timestamp để thay CAS/version hoặc đo elapsed giữa các tiến trình**; thời gian và thứ tự cập nhật là hai vấn đề khác nhau.

Một schema thời gian tốt sẽ nói rõ **mốc thời gian đại diện cho điều gì, ai có quyền xác định nó, đơn vị/độ chính xác ra sao và sẽ được dùng để đọc hoặc quyết định nghiệp vụ như thế nào**. Khi các câu hỏi này được trả lời ngay từ thiết kế, dữ liệu sẽ dễ truy vấn, dễ kiểm thử và ít gây sự cố khi hệ thống mở rộng ra nhiều múi giờ, nhiều thiết bị và nhiều cơ sở dữ liệu.
