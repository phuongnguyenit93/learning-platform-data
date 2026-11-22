# Ngày lịch, giờ địa phương, thời điểm và múi giờ

## Mục tiêu bài học

Sau bài này, bạn có thể phân biệt ngày lịch, giờ trong ngày, ngày giờ địa phương và thời điểm tuyệt đối; giải thích vai trò của múi giờ và độ lệch UTC; chọn cách lưu phù hợp cho sinh nhật, lịch hẹn, giao dịch và lịch lặp; đồng thời xử lý các trường hợp giờ không tồn tại hoặc xuất hiện hai lần khi đồng hồ đổi giờ.

Bạn cũng sẽ biết cách thiết kế hợp đồng API và schema cơ sở dữ liệu để tránh lỗi lệch ngày, sai thời điểm, mất thông tin múi giờ và diễn giải khác nhau giữa các hệ thống.

## 1. Vì sao thời gian dễ bị mô hình hóa sai?

Một giá trị như 21-11-2026 hoặc 09:30 trông đơn giản, nhưng có thể mang nhiều ý nghĩa:

- Ngày sinh của một người là ngày lịch, không phải một thời điểm xảy ra tại một múi giờ cụ thể.
- Cuộc họp lúc 09:30 tại Hà Nội là giờ địa phương gắn với múi giờ của địa điểm.
- Một giao dịch thanh toán được chấp nhận lúc 02:30 UTC là một thời điểm trên dòng thời gian.
- Báo cáo doanh thu ngày 21-11 có thể dùng ngày lịch theo múi giờ của cửa hàng.
- Lịch mở cửa 09:00–17:00 mỗi ngày là quy tắc giờ địa phương lặp lại, không phải một cặp thời điểm UTC cố định.

Nếu lưu tất cả bằng một kiểu timestamp, hệ thống có thể diễn giải sai. Ví dụ, lưu sinh nhật thành thời điểm UTC rồi đổi sang múi giờ khác có thể khiến ngày sinh hiển thị lùi hoặc tiến một ngày. Ngược lại, lưu thời điểm thanh toán như một chuỗi giờ địa phương không có múi giờ khiến hệ thống không biết giao dịch xảy ra trước hay sau một sự kiện ở nơi khác.

Bước đầu tiên khi thiết kế thuộc tính thời gian là hỏi: **giá trị này mô tả ngày lịch, giờ trên đồng hồ địa phương, hay một thời điểm xác định trên dòng thời gian?**

## 2. Bốn khái niệm cần phân biệt

### 2.1. Ngày lịch (calendar date)

Ngày lịch biểu diễn một ngày theo lịch, thường gồm năm, tháng và ngày. Nó không có giờ, phút hay múi giờ.

Ví dụ:

- ngày sinh: 2001-04-12;
- ngày bắt đầu hợp đồng: 2026-11-21;
- ngày nghỉ lễ của chi nhánh: 2027-01-01;
- ngày ghi nhận kỳ kế toán: 2026-11-30.

Ngày lịch không tự chỉ ra một thời điểm tuyệt đối. Ngày 2026-11-21 ở Việt Nam và ngày 2026-11-21 ở California là cùng nhãn ngày theo lịch, nhưng khoảng thời gian thực tế mà mỗi nơi gọi là ngày đó không trùng nhau.

Dùng kiểu DATE hoặc kiểu ngày tương đương khi nghiệp vụ chỉ quan tâm đến ngày. Không tự gắn 00:00 UTC vào ngày lịch nếu nghiệp vụ không quy định điều đó.

### 2.2. Giờ địa phương trong ngày (local time / wall-clock time)

Giờ địa phương trong ngày biểu diễn giờ trên đồng hồ, ví dụ 09:30 hoặc 17:45:20. Nó không có ngày và cũng không đủ thông tin để xác định thời điểm tuyệt đối.

Ví dụ:

- cửa hàng mở cửa lúc 09:00;
- cuộc gọi hỗ trợ bắt đầu lúc 08:30;
- chuông báo thức reo lúc 06:15.

Giờ 09:30 có thể xảy ra nhiều lần trong ngày và ở mọi múi giờ. Chỉ lưu giờ trong ngày khi ngày không quan trọng hoặc thuộc một quy tắc lặp lại.

### 2.3. Ngày giờ địa phương (local date-time / wall-clock date-time)

Ngày giờ địa phương kết hợp ngày lịch và giờ đồng hồ, ví dụ 2026-11-21 09:30. Giá trị này mô tả điều người dùng nhìn thấy trên lịch hoặc đồng hồ tại một địa điểm, nhưng chưa xác định duy nhất một thời điểm nếu thiếu múi giờ hoặc độ lệch UTC.

Ví dụ: “Cuộc họp bắt đầu lúc 09:30 ngày 21-11 tại Thành phố Hồ Chí Minh.” Để chuyển thành thời điểm trên dòng thời gian, cần biết múi giờ áp dụng tại địa điểm và ngày đó.

### 2.4. Thời điểm tuyệt đối (instant)

**Instant** là một điểm xác định trên dòng thời gian, không phụ thuộc vào cách hiển thị theo múi giờ. Cùng một instant có thể được hiển thị thành các giờ địa phương khác nhau.

Ví dụ, thời điểm 2026-11-21T02:30:00Z có thể được hiển thị là 09:30 tại một địa điểm đang dùng UTC+07:00. Giá trị instant không đổi khi người xem đổi múi giờ; chỉ cách hiển thị thay đổi.

Các sự kiện như thanh toán được chấp nhận, message được phát hành, file được tải lên hoặc máy chủ ghi nhận request thường cần instant.

### 2.5. Bảng so sánh

| Khái niệm | Ví dụ | Có múi giờ? | Có xác định một instant? |
|---|---|---|---|
| Ngày lịch | 2026-11-21 | Không | Không |
| Giờ trong ngày | 09:30:00 | Không | Không |
| Ngày giờ địa phương | 2026-11-21 09:30 | Chưa có | Không, trừ khi bổ sung zone/offset và quy tắc |
| Ngày giờ kèm offset | 2026-11-21T09:30:00+07:00 | Có độ lệch UTC | Có |
| Instant | 2026-11-21T02:30:00Z | Được biểu diễn theo UTC | Có |

Độ lệch UTC cho phép xác định instant tại thời điểm đó. Tuy nhiên, nó không cho biết toàn bộ quy tắc múi giờ của một địa điểm trong quá khứ hoặc tương lai.

## 3. Múi giờ, UTC và độ lệch UTC

### 3.1. UTC

**UTC (Coordinated Universal Time)** là chuẩn thời gian tham chiếu được dùng rộng rãi để trao đổi và lưu trữ thời điểm. Khi biểu diễn timestamp ở UTC, ký hiệu hậu tố thường là Z.

Ví dụ:

~~~text
2026-11-21T02:30:00Z
~~~

Chữ Z có nghĩa là độ lệch UTC bằng 00:00. Đây là một cách biểu diễn instant.

UTC giúp các hệ thống ở nhiều khu vực so sánh thứ tự sự kiện mà không phải đoán múi giờ địa phương.

### 3.2. Độ lệch UTC (UTC offset)

Độ lệch UTC là chênh lệch giữa giờ địa phương và UTC tại một thời điểm cụ thể, ví dụ:

- +07:00: giờ địa phương nhanh hơn UTC bảy giờ;
- -05:00: giờ địa phương chậm hơn UTC năm giờ;
- +05:30: giờ địa phương nhanh hơn UTC năm giờ ba mươi phút.

Ví dụ hai biểu diễn sau cùng chỉ một instant:

~~~text
2026-11-21T02:30:00Z
2026-11-21T09:30:00+07:00
~~~

Offset đủ để đổi một ngày giờ cụ thể thành instant. Nhưng offset chỉ là con số tại thời điểm đó. Nó không chứa quy tắc đổi giờ theo mùa, lịch sử thay đổi chính sách hoặc tên địa điểm.

### 3.3. Múi giờ theo vùng (time zone)

Một múi giờ theo vùng là tập quy tắc xác định offset áp dụng theo địa điểm và thời gian. Hệ thống thường dùng tên trong cơ sở dữ liệu múi giờ IANA, chẳng hạn:

- Asia/Ho_Chi_Minh;
- Asia/Tokyo;
- Europe/Paris;
- America/New_York.

Tên vùng giúp xác định quy tắc lịch sử và quy tắc có hiệu lực trong tương lai theo dữ liệu múi giờ được cài đặt.

Không nên thay tên vùng bằng một offset cố định nếu nghiệp vụ cần giữ giờ địa phương qua các thay đổi giờ mùa hè hoặc thay đổi chính sách của địa phương.

### 3.4. Offset khác zone ID như thế nào?

| Thông tin | Ví dụ | Điều nó cho biết |
|---|---|---|
| Offset | +07:00 | Chênh lệch UTC tại một thời điểm |
| Zone ID | Asia/Ho_Chi_Minh | Quy tắc thời gian của một vùng địa lý |
| Local date-time | 2026-11-21 09:30 | Giờ lịch mà người dùng muốn thấy |
| Instant | 2026-11-21T02:30:00Z | Điểm xác định trên dòng thời gian |

Một offset như +01:00 có thể được dùng ở nhiều vùng có quy tắc khác nhau. Một zone ID có thể có offset khác nhau ở các thời điểm khác nhau.

Với sự kiện đã xảy ra, lưu instant thường là nền tảng quan trọng nhất. Nếu cần giữ ngữ cảnh địa điểm hoặc cách người dùng đã nhập giờ, lưu thêm zone ID và/hoặc offset gốc theo yêu cầu kiểm toán.

## 4. Chọn kiểu dữ liệu theo ý nghĩa nghiệp vụ

Không có một kiểu thời gian phù hợp cho mọi thuộc tính. Hãy chọn theo câu hỏi mà dữ liệu cần trả lời.

| Nhu cầu nghiệp vụ | Kiểu khái niệm phù hợp | Ví dụ |
|---|---|---|
| Ngày sinh, ngày nghỉ, ngày hiệu lực | Date | 2001-04-12 |
| Giờ mở cửa mỗi ngày | Local time | 09:00 |
| Thời gian người dùng nhập cho một lịch hẹn | Local date-time + zone ID | 2026-11-21 09:30, Asia/Ho_Chi_Minh |
| Sự kiện đã xảy ra | Instant | 2026-11-21T02:30:00Z |
| Khoảng thời gian thực đã trôi qua | Duration | 90 phút |
| Khoảng thời gian theo lịch | Period | 1 tháng, 1 năm |
| Lịch lặp theo địa phương | Recurrence rule + local time + zone ID | Mỗi thứ Hai lúc 09:00 tại một vùng |

### 4.1. Ngày lịch không phải timestamp lúc nửa đêm

Ví dụ, ngày sinh 2001-04-12 nên được lưu là một giá trị date. Nếu lưu thành 2001-04-12T00:00:00Z rồi hiển thị ở múi giờ UTC-07:00, người dùng có thể nhìn thấy ngày 2001-04-11.

Việc gắn một instant vào ngày sinh đã tạo thêm thông tin không tồn tại trong nghiệp vụ và có thể gây lỗi khi chuyển múi giờ.

### 4.2. Giờ địa phương không phải instant

Giờ mở cửa 09:00 là một quy tắc đồng hồ địa phương. Nếu lưu nó thành 02:00 UTC, quy tắc sẽ không còn đúng khi áp dụng ở một vùng khác hoặc khi offset thay đổi.

Hãy lưu giờ trong ngày và zone ID ở cấp chi nhánh nếu cần xác định địa điểm. Nếu cửa hàng có lịch mở cửa theo từng ngày trong tuần, lưu cả quy tắc thứ trong tuần và khoảng giờ.

### 4.3. Ngày giờ địa phương cần ngữ cảnh để đổi thành instant

Một form đặt lịch có thể nhận:

~~~json
{
  "localDateTime": "2026-11-21T09:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

Backend dùng zone ID và quy tắc thời gian tại ngày đó để xác định instant. Nếu thời điểm địa phương không hợp lệ hoặc mơ hồ do đổi giờ, hệ thống phải có chính sách xử lý rõ ràng.

### 4.4. Sự kiện đã xảy ra nên lưu instant

Ví dụ, hệ thống nhận được xác nhận thanh toán. Sự kiện cần có thời điểm để sắp xếp, đối chiếu và điều tra.

~~~json
{
  "eventType": "PaymentAccepted",
  "occurredAt": "2026-11-21T02:30:00Z"
}
~~~

Có thể lưu thêm thời điểm nhận ở hệ thống và nguồn gửi để phân biệt lúc sự kiện xảy ra với lúc hệ thống biết về sự kiện đó.

## 5. Lưu ngày giờ trong cơ sở dữ liệu

Các hệ quản trị cơ sở dữ liệu có tên kiểu dữ liệu và ngữ nghĩa hơi khác nhau. Cần đọc tài liệu của hệ quản trị đang dùng thay vì chỉ dựa vào tên kiểu.

### 5.1. DATE

DATE lưu ngày lịch, thường gồm năm, tháng và ngày. Nó phù hợp cho ngày sinh, ngày ký hợp đồng, ngày nghỉ hoặc ngày hạch toán.

~~~sql
CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    birth_date DATE
);
~~~

Không nên thêm múi giờ vào một thuộc tính ngày lịch nếu nghiệp vụ không yêu cầu.

### 5.2. TIME

TIME lưu giờ trong ngày. Trong nhiều hệ quản trị, TIME không gắn với một ngày hay múi giờ cụ thể.

~~~sql
CREATE TABLE store_opening_hours (
    store_id BIGINT NOT NULL,
    day_of_week SMALLINT NOT NULL,
    opens_at TIME NOT NULL,
    closes_at TIME NOT NULL
);
~~~

Với lịch mở cửa, cần xác định múi giờ của cửa hàng ở nơi khác trong mô hình. Cũng cần xử lý ca qua nửa đêm, ngày nghỉ và nhiều khoảng mở cửa trong cùng một ngày.

### 5.3. TIMESTAMP không có múi giờ

Kiểu timestamp không có múi giờ thường lưu ngày giờ dạng lịch mà không tự xác định instant. Nó phù hợp khi muốn giữ nguyên giờ địa phương như người dùng nhập, nhưng phải lưu zone ID riêng nếu cần chuyển thành instant.

Tên kiểu có thể gây hiểu nhầm: một timestamp không có zone không tự biết giá trị đó là UTC hay giờ địa phương. Không được mặc định rằng giá trị thiếu offset có nghĩa là UTC.

### 5.4. TIMESTAMP có múi giờ hoặc kiểu tương đương

Một số hệ quản trị cung cấp kiểu timestamp có ngữ nghĩa instant hoặc kiểu lưu offset. Cách lưu và hiển thị khác nhau giữa sản phẩm:

- Có hệ quản trị chuẩn hóa instant về UTC và hiển thị theo timezone của session.
- Có kiểu giữ offset gốc nhưng không giữ toàn bộ quy tắc IANA của vùng.
- Có hệ quản trị dùng tên kiểu giống nhau nhưng hành vi chuyển đổi khác nhau.

Ví dụ với PostgreSQL, TIMESTAMP WITH TIME ZONE (timestamptz) biểu diễn instant; PostgreSQL chuyển đổi đầu vào có zone sang UTC nội bộ và hiển thị theo timezone session. Nó không giữ lại tên zone ban đầu như Asia/Ho_Chi_Minh. Nếu cần giữ zone ID, hãy lưu thêm cột riêng.

### 5.5. Lưu instant và zone ID riêng khi cần

Một bảng lịch hẹn có thể cần cả thời điểm đã xác định và ngữ cảnh người dùng đặt lịch:

~~~sql
CREATE TABLE appointments (
    appointment_id BIGINT PRIMARY KEY,
    starts_at_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    time_zone_id VARCHAR(100) NOT NULL,
    local_start TIMESTAMP NOT NULL
);
~~~

Trong ví dụ này:

- starts_at_utc là instant dùng cho so sánh, nhắc lịch và tích hợp;
- time_zone_id là vùng quy tắc để hiển thị và diễn giải theo địa điểm;
- local_start giữ giờ địa phương đã được xác nhận nếu cần audit hoặc giữ nguyên ý định người đặt.

Không phải ứng dụng nào cũng cần lưu cả ba trường. Tránh lưu nhiều bản sao nếu không có nhu cầu cụ thể; nếu lưu, hãy xác định trường nào là nguồn chuẩn và cách kiểm tra chúng nhất quán.

## 6. Giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần

Ở những vùng áp dụng giờ mùa hè (DST), đồng hồ địa phương có thể được chỉnh tiến hoặc lùi. Khi đó, chuyển từ local date-time sang instant không phải lúc nào cũng là phép ánh xạ một-một.

### 6.1. Khoảng giờ không tồn tại (gap)

Khi đồng hồ được chỉnh tiến, một khoảng giờ địa phương bị bỏ qua. Ví dụ minh họa, đồng hồ chuyển từ 01:59 sang 03:00, nên 02:30 không tồn tại trong ngày đó tại vùng đó.

Nếu người dùng đặt lịch lúc 02:30 trong khoảng gap, hệ thống không thể tự suy ra instant hợp lệ. Cần quyết định:

- báo lỗi và yêu cầu người dùng chọn giờ khác;
- tự dịch tới giờ hợp lệ tiếp theo;
- hoặc áp dụng một quy tắc nghiệp vụ đã công bố.

Với lịch hẹn quan trọng, yêu cầu người dùng xác nhận thường dễ hiểu và tránh dịch lịch âm thầm.

### 6.2. Khoảng giờ lặp lại (overlap)

Khi đồng hồ được chỉnh lùi, một khoảng giờ địa phương xuất hiện hai lần. Ví dụ, 01:30 có thể xảy ra hai lần với hai offset khác nhau.

Local date-time và zone ID lúc này vẫn có thể chưa đủ để chọn một instant. Hệ thống cần:

- yêu cầu chọn lần thứ nhất hoặc lần thứ hai;
- nhận offset cụ thể từ client sau khi xác thực;
- hoặc áp dụng quy tắc mặc định đã được nghiệp vụ chấp thuận.

Không nên tự chọn một instant mà không có chính sách, nhất là với thanh toán, giao dịch tài chính hoặc lịch hẹn có hậu quả lớn.

### 6.3. Vì sao zone ID quan trọng?

Một offset cố định không cho biết có gap hoặc overlap ở ngày đó hay không. Zone ID kết hợp dữ liệu quy tắc múi giờ mới có thể xác định:

- local date-time hợp lệ hay không;
- có một hay hai instant tương ứng;
- offset nào áp dụng;
- quy tắc lịch sử và tương lai theo dữ liệu timezone.

Dữ liệu quy tắc múi giờ có thể được cập nhật khi chính quyền thay đổi chính sách. Ứng dụng nên cập nhật timezone database và xác định cách xử lý lịch hẹn tương lai khi quy tắc thay đổi.

## 7. Lịch hẹn, sự kiện và lịch lặp

### 7.1. Lịch hẹn một lần

Một lịch hẹn do người dùng chọn theo giờ địa phương thường cần:

- local date-time mà người dùng đã chọn;
- zone ID của địa điểm hoặc người tổ chức;
- instant đã được xác nhận;
- chính sách giải quyết gap/overlap;
- thông tin người tạo và thời điểm tạo nếu cần audit.

Khi lịch hẹn đã được xác nhận, instant giúp gửi nhắc lịch đúng thời điểm. Zone ID giúp hiển thị theo vùng mong muốn và giữ ngữ cảnh lịch.

Nếu lịch hẹn được dời do thay đổi timezone rule, cần quyết định mục tiêu nghiệp vụ là giữ nguyên instant hay giữ nguyên giờ địa phương. Hai lựa chọn này có thể dẫn đến giờ hiển thị khác nhau.

### 7.2. Sự kiện đã xảy ra

Với sự kiện đã xảy ra như thanh toán, đăng nhập, giao hàng hoặc nhận message, instant là thông tin chính để sắp xếp trên dòng thời gian.

Có thể cần các trường:

- occurred_at: thời điểm nghiệp vụ xảy ra theo nguồn;
- received_at: thời điểm hệ thống nhận dữ liệu;
- recorded_at: thời điểm ghi vào kho dữ liệu;
- source_time_zone hoặc source_offset: ngữ cảnh nguồn nếu cần.

Không nên gộp các thời điểm này vào một cột created_at nếu chúng có ý nghĩa khác nhau.

### 7.3. Lịch lặp theo giờ địa phương

Ví dụ: “Cửa hàng mở cửa lúc 09:00 mỗi ngày” hoặc “Cuộc họp nhóm diễn ra vào 09:00 thứ Hai tại Paris”.

Đây là quy tắc theo giờ địa phương. Nên lưu:

- ngày/tuần hoặc recurrence rule;
- giờ địa phương;
- zone ID;
- ngày bắt đầu và ngày kết thúc nếu có;
- ngoại lệ, ngày nghỉ hoặc lần bị hủy;
- chính sách gap/overlap.

Không nên tạo lịch lặp bằng cách lấy instant lần trước cộng 24 giờ nếu mục tiêu là giữ giờ đồng hồ địa phương. Khi offset thay đổi, giờ địa phương có thể bị lệch một giờ.

Ví dụ, lịch họp 09:00 tại một vùng có DST phải tiếp tục diễn ra lúc 09:00 theo đồng hồ địa phương sau khi chuyển mùa, dù instant UTC của nó thay đổi.

### 7.4. Ngày sự kiện cả ngày (all-day event)

Một sự kiện “ngày nghỉ 21-11” có thể là ngày lịch, không phải khoảng instant từ 00:00 đến 23:59 UTC.

Thường biểu diễn bằng ngày bắt đầu và ngày kết thúc theo quy ước rõ ràng. Với nhiều lịch, khoảng ngày dùng đầu bao gồm và cuối không bao gồm:

~~~text
start_date = 2026-11-21
end_date_exclusive = 2026-11-22
~~~

Cách biểu diễn này giúp tính số ngày và nối các sự kiện liền kề mà không phải giả định một ngày luôn có đúng 24 giờ. Nếu sự kiện cả ngày gắn với một địa điểm, zone ID có thể cần để chuyển thành khoảng thời gian khi đồng bộ với hệ thống khác.

## 8. Duration và Period: khoảng thời gian không phải ngày giờ

Hai khái niệm thường bị nhầm:

- **Duration:** khoảng thời gian đo bằng lượng thời gian đã trôi qua, thường là giây hoặc nano giây.
- **Period:** khoảng thời gian theo lịch, như 1 ngày, 1 tháng hoặc 1 năm.

Ví dụ:

- Timeout 30 giây là duration.
- Hạn thanh toán sau 3 ngày lịch là period hoặc quy tắc ngày làm việc tùy nghiệp vụ.
- Hợp đồng có hiệu lực 1 năm kể từ ngày ký có thể cần phép cộng theo lịch.
- Một request chạy trong 500 mili giây là duration đo bằng đồng hồ đơn điệu (monotonic clock), không nên dựa vào đồng hồ lịch có thể bị điều chỉnh.

Một ngày lịch không phải lúc nào cũng dài đúng 24 giờ ở vùng có thay đổi offset. Một tháng cũng không có số ngày cố định. Hãy chọn phép toán phù hợp với ngữ nghĩa.

### 8.1. Hạn theo ngày lịch và hạn theo thời lượng

So sánh:

- “Hạn vào cuối ngày 21-11 theo giờ địa phương”: cần date, zone ID và quy tắc chốt ngày.
- “Hạn sau đúng 48 giờ kể từ lúc thanh toán”: cần instant bắt đầu cộng duration 48 giờ.

Hai quy tắc có thể tạo ra thời điểm khác nhau khi có chuyển đổi múi giờ.

### 8.2. Đồng hồ đơn điệu cho đo thời lượng

Khi đo thời gian chạy trong cùng một tiến trình hoặc thiết bị, đồng hồ hệ thống có thể bị đồng bộ lại hoặc điều chỉnh. Để đo duration chính xác, nên dùng monotonic clock, vốn chỉ bảo đảm thứ tự tăng trong quá trình đo.

Timestamp UTC phù hợp để ghi nhận thời điểm bắt đầu/kết thúc phục vụ audit; monotonic clock phù hợp để đo khoảng chạy. Hai công cụ phục vụ hai mục đích khác nhau.

## 9. Định dạng trao đổi và hợp đồng API

### 9.1. Dùng định dạng ISO 8601 rõ ràng

Một số biểu diễn phổ biến:

~~~text
2026-11-21
09:30:00
2026-11-21T09:30:00
2026-11-21T09:30:00+07:00
2026-11-21T02:30:00Z
~~~

Ý nghĩa lần lượt là ngày, giờ, ngày giờ địa phương không có zone, ngày giờ có offset và instant biểu diễn theo UTC.

Không nên gửi ngày giờ không có offset rồi kỳ vọng mọi bên hiểu đó là UTC. Hợp đồng phải nói rõ đó là local date-time cần zone ID hay giá trị UTC theo quy ước.

### 9.2. API cho instant

Với sự kiện đã xảy ra, payload có thể dùng UTC:

~~~json
{
  "paymentId": "PAY-9001",
  "acceptedAt": "2026-11-21T02:30:00Z"
}
~~~

Tên trường nên nói rõ ngữ nghĩa. Nếu trường là instant, yêu cầu offset hoặc Z trong định dạng. Client có thể chuyển sang múi giờ người dùng để hiển thị.

### 9.3. API cho giờ địa phương

Với lịch hẹn, payload cần local date-time và zone ID:

~~~json
{
  "localStart": "2026-11-21T09:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

Backend cần kiểm tra tính hợp lệ của giờ trong zone đó, rồi xác định instant. Nếu giờ rơi vào overlap, hợp đồng có thể yêu cầu thêm offset hoặc lựa chọn lần xuất hiện.

### 9.4. Không dùng tên múi giờ viết tắt làm định danh

Các chuỗi như CST, IST hoặc PST có thể mang nhiều ý nghĩa tùy vùng và thời điểm. Chúng không phải lúc nào cũng xác định duy nhất một zone ID.

Ưu tiên tên vùng IANA như America/Chicago hoặc Asia/Kolkata khi cần quy tắc địa lý. Nếu chỉ cần một instant, offset cụ thể hoặc UTC có thể đủ.

### 9.5. Độ chính xác và làm tròn

Các hệ thống có thể hỗ trợ độ chính xác khác nhau: giây, mili giây, micro giây hoặc nano giây. Cần thống nhất:

- độ chính xác của trường;
- cách làm tròn hoặc cắt phần thập phân;
- cách so sánh hai timestamp;
- định dạng khi serialize;
- cách xử lý dữ liệu nguồn có độ chính xác cao hơn database đích.

Không dùng timestamp làm khóa duy nhất nếu độ chính xác hoặc nguồn sinh thời gian không bảo đảm duy nhất. Nhiều sự kiện có thể xảy ra trong cùng một mili giây.

## 10. Ví dụ với Java Time API

Trong Java, package java.time cung cấp các kiểu riêng cho từng ngữ nghĩa:

| Kiểu Java | Ý nghĩa |
|---|---|
| LocalDate | Ngày lịch |
| LocalTime | Giờ trong ngày |
| LocalDateTime | Ngày giờ địa phương, chưa có zone |
| Instant | Thời điểm tuyệt đối |
| ZoneId | Quy tắc múi giờ theo vùng |
| ZonedDateTime | Ngày giờ gắn với zone |
| OffsetDateTime | Ngày giờ gắn với offset cụ thể |
| Duration | Khoảng thời gian đã trôi qua |
| Period | Khoảng thời gian theo lịch |

Ví dụ:

~~~java
import java.time.*;

LocalDate birthday = LocalDate.of(2001, 4, 12);
LocalTime openingTime = LocalTime.of(9, 0);

LocalDateTime localMeeting =
    LocalDateTime.of(2026, 11, 21, 9, 30);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime meetingInZone = localMeeting.atZone(zone);

Instant meetingInstant = meetingInZone.toInstant();
OffsetDateTime utcRepresentation =
    meetingInstant.atOffset(ZoneOffset.UTC);
~~~

Ở đây:

- birthday không có múi giờ;
- openingTime chỉ là giờ trên đồng hồ;
- localMeeting chưa xác định instant;
- zone bổ sung quy tắc vùng;
- meetingInZone biểu diễn ngày giờ theo vùng;
- meetingInstant là thời điểm có thể trao đổi giữa các hệ thống.

### 10.1. Kiểm tra giờ địa phương mơ hồ

Khi xử lý giờ địa phương tại một zone, có thể hỏi zone có bao nhiêu offset hợp lệ cho local date-time:

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);

var validOffsets = zone.getRules().getValidOffsets(local);

if (validOffsets.isEmpty()) {
    // Local time is in a gap: no corresponding instant.
} else if (validOffsets.size() == 1) {
    // Exactly one valid offset.
} else {
    // Overlap: two valid offsets; ask for or apply a policy.
}
~~~

Đoạn mã minh họa nguyên tắc. Kết quả cụ thể phụ thuộc ngày, zone ID và phiên bản dữ liệu timezone. Không nên hard-code giả định rằng một giờ cụ thể luôn là gap hoặc overlap ở mọi năm.

### 10.2. Chọn kiểu theo mục đích

Không nên dùng LocalDateTime cho mọi trường thời gian chỉ vì nó dễ tạo. Nếu cần một instant, dùng Instant hoặc kiểu có offset/zone phù hợp. Nếu cần giữ ngày sinh, dùng LocalDate. Nếu cần lịch lặp tại địa phương, giữ cả quy tắc lặp và ZoneId.

## 11. Kiểm chứng mô hình thời gian

Dùng các tình huống dưới đây để kiểm tra schema và API:

1. Ngày sinh được xem ở UTC-08:00 và UTC+09:00 vẫn giữ nguyên ngày.
2. Một giao dịch xảy ra lúc 02:30 UTC được hiển thị đúng giờ địa phương ở hai quốc gia.
3. Một lịch hẹn ở giờ bình thường chuyển thành đúng instant theo zone ID.
4. Một lịch hẹn rơi vào khoảng giờ không tồn tại được xử lý theo chính sách.
5. Một lịch hẹn rơi vào khoảng giờ xuất hiện hai lần yêu cầu lựa chọn hoặc áp dụng quy tắc rõ ràng.
6. Lịch họp hàng tuần giữ nguyên giờ địa phương sau khi khu vực đổi DST.
7. Sự kiện đến trễ vẫn giữ cả occurred_at và received_at.
8. Một sự kiện cả ngày không bị lùi hoặc tiến ngày khi hiển thị ở vùng khác.
9. Phép cộng 1 ngày lịch và 24 giờ duration cho kết quả đúng theo yêu cầu.
10. Timestamp có độ chính xác khác nhau giữa nguồn và đích không gây so sánh sai ngoài ý muốn.

### 11.1. Checklist trước khi chốt schema

- [ ] Đã xác định trường là date, local time, local date-time hay instant.
- [ ] Nếu cần zone, đã chọn zone ID có quy tắc rõ ràng.
- [ ] Đã phân biệt offset với zone ID.
- [ ] Đã thống nhất cách lưu và trao đổi instant.
- [ ] Đã định nghĩa gap và overlap policy.
- [ ] Đã xác định mục tiêu của lịch tương lai: giữ instant hay giữ giờ địa phương.
- [ ] Đã phân biệt duration với period.
- [ ] Đã thống nhất độ chính xác và cách làm tròn.
- [ ] Đã kiểm tra cách hệ quản trị lưu và hiển thị kiểu timestamp.
- [ ] Đã có test cho nhiều múi giờ, ngày biên và quy tắc DST.

## 12. Những sai lầm thường gặp

- **Lưu ngày sinh thành timestamp UTC:** khi chuyển múi giờ, ngày có thể bị lệch. Hãy dùng kiểu ngày lịch.
- **Coi giờ địa phương là instant:** 09:30 không đủ thông tin nếu chưa có ngày và zone.
- **Chỉ lưu offset cho lịch lặp:** offset có thể thay đổi theo quy tắc vùng. Hãy lưu zone ID khi cần giữ giờ địa phương.
- **Lưu local date-time mà không lưu zone:** không thể xác định instant hoặc diễn giải địa điểm một cách chắc chắn.
- **Dùng tên viết tắt múi giờ:** tên có thể mơ hồ. Hãy dùng UTC offset hoặc zone ID rõ ràng tùy mục đích.
- **Giả định một ngày luôn dài 24 giờ:** ngày địa phương có thể dài ngắn khác nhau khi đồng hồ đổi giờ.
- **Cộng 24 giờ để tạo lịch tuần:** giờ địa phương có thể bị lệch sau DST. Hãy tính từng lần theo recurrence rule và zone.
- **Bỏ qua gap và overlap:** một giờ địa phương có thể không tồn tại hoặc xảy ra hai lần.
- **Dùng một cột created_at cho mọi thời điểm:** event time, received time và recorded time có ý nghĩa khác nhau.
- **Dùng timestamp làm ID duy nhất:** nhiều sự kiện có thể cùng timestamp ở độ chính xác hiện có.
- **Không cập nhật timezone database:** quy tắc địa phương có thể thay đổi theo quyết định chính quyền.

## 13. Kết luận

Ngày lịch, giờ trong ngày, ngày giờ địa phương và instant là những khái niệm khác nhau. UTC và offset giúp biểu diễn hoặc chuyển đổi thời điểm; zone ID cung cấp quy tắc theo địa điểm và thời gian. Duration đo thời gian đã trôi qua, còn Period mô tả khoảng theo lịch.

Khi mô hình hóa, hãy xác định ý nghĩa nghiệp vụ trước khi chọn kiểu dữ liệu. Dùng date cho ngày lịch, local time cho giờ trên đồng hồ, local date-time kèm zone cho lịch địa phương và instant cho sự kiện đã xảy ra. Với lịch tương lai hoặc lịch lặp, hãy xác định rõ cần giữ thời điểm tuyệt đối hay giờ địa phương và cách xử lý các trường hợp đổi giờ.

## Tự kiểm tra

1. Vì sao ngày sinh nên dùng date thay vì timestamp UTC?
2. Phân biệt UTC offset và IANA Zone ID.
3. Local date-time có đủ để xác định instant không? Cần bổ sung gì?
4. Vì sao một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần?
5. Với lịch họp mỗi thứ Hai lúc 09:00 tại một vùng có DST, nên lưu những thành phần nào?
6. Phân biệt Duration và Period bằng ví dụ hạn thanh toán.
7. Một hệ thống nhận sự kiện từ đối tác trễ. Nên lưu những mốc thời gian nào để giữ được thời điểm xảy ra và thời điểm nhận?
8. Hãy chọn ba trường thời gian trong một hệ thống bạn biết, xác định ngữ nghĩa, kiểu dữ liệu, zone cần thiết và tình huống kiểm thử.

