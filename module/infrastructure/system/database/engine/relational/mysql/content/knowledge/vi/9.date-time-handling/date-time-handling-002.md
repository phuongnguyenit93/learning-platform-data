# DATE, DATETIME, TIMESTAMP và miền giá trị theo phiên bản

Ngày giờ là dữ liệu nền tảng trong hầu hết ứng dụng: ngày sinh, ngày giao hàng, thời điểm tạo đơn hàng, lịch hẹn, thời gian đăng nhập và thời điểm ghi nhận sự kiện. Chọn sai kiểu dữ liệu có thể làm mất phần giờ, giới hạn ngày trong tương lai, gây sai lệch khi ứng dụng chạy ở nhiều múi giờ hoặc khiến dữ liệu không thể biểu diễn sau khi hệ thống hoạt động đủ lâu.

MySQL cung cấp ba kiểu thường dùng để lưu ngày và thời điểm:

- **DATE** lưu ngày lịch, không có giờ.
- **DATETIME** lưu ngày và giờ như một giá trị lịch, không tự chuyển đổi theo múi giờ.
- **TIMESTAMP** lưu một thời điểm và chuyển đổi giữa múi giờ phiên kết nối với UTC khi ghi và đọc.

Miền giá trị của ba kiểu này khác nhau. Đặc biệt, TIMESTAMP trong các dòng MySQL phổ biến vẫn có giới hạn đến năm 2038, kể cả MySQL 8.x. Vì vậy, việc chọn kiểu phải dựa trên ý nghĩa nghiệp vụ, phạm vi thời gian, múi giờ và phiên bản MySQL triển khai.

## 1. Phân biệt ngày lịch và thời điểm

Trước khi chọn kiểu dữ liệu, hãy xác định dữ liệu cần biểu diễn là loại nào.

**Ngày lịch** là một ngày theo lịch, không nhất thiết gắn với thời điểm cụ thể. Ví dụ:

- Ngày sinh của khách hàng.
- Ngày ký hợp đồng.
- Ngày nghỉ lễ.
- Ngày hẹn giao hàng nếu nghiệp vụ chỉ quan tâm ngày.

**Thời điểm** là một khoảnh khắc xác định trên dòng thời gian. Ví dụ:

- Thời điểm đơn hàng được tạo.
- Thời điểm thanh toán thành công.
- Thời điểm máy chủ ghi nhận một sự kiện.
- Thời điểm người dùng đăng nhập.

Một **giờ địa phương** như “09:00 tại Hà Nội” lại có ý nghĩa khác: nó là giờ trên đồng hồ tại một địa điểm, có thể cần giữ nguyên theo lịch ngay cả khi quy tắc múi giờ thay đổi. Ví dụ lịch khám, giờ mở cửa hoặc lịch học thường cần cả ngày giờ địa phương và múi giờ IANA của địa điểm.

Không nên dùng một kiểu ngày giờ cho mọi trường hợp. DATE, DATETIME và TIMESTAMP giải quyết các nhu cầu khác nhau.

## 2. Kiểu DATE

### 2.1. Ý nghĩa và miền giá trị

DATE lưu năm, tháng và ngày. Kiểu này không lưu giờ, phút, giây hoặc múi giờ.

Trong MySQL 5.7, 8.0 và 8.4, miền giá trị DATE thông thường là:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất |
|---|---|---|
| DATE | 1000-01-01 | 9999-12-31 |

Một giá trị DATE được hiển thị theo dạng YYYY-MM-DD.

Ví dụ:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    birth_date  DATE,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

INSERT INTO customers (full_name, birth_date)
VALUES ('Nguyễn An', '1995-08-21');
~~~

### 2.2. Khi nào dùng DATE?

Dùng DATE khi nghiệp vụ chỉ quan tâm ngày lịch và không cần thời điểm trong ngày. Không nên lưu ngày sinh dưới dạng DATETIME với phần giờ mặc định 00:00:00, vì phần giờ không mang ý nghĩa và có thể gây nhầm lẫn khi xử lý.

DATE phù hợp với:

- Ngày sinh, ngày thành lập.
- Ngày hiệu lực hợp đồng nếu chỉ có hiệu lực theo ngày.
- Ngày hạch toán hoặc ngày làm việc.
- Ngày nghỉ phép, ngày lễ.

Nếu nghiệp vụ cần biết chính xác thời điểm một sự kiện xảy ra, DATE không đủ thông tin.

## 3. Kiểu DATETIME

### 3.1. Ý nghĩa và miền giá trị

DATETIME lưu cả ngày và giờ dưới dạng giá trị lịch. Nó không lưu múi giờ và MySQL không tự chuyển đổi giá trị DATETIME khi session time zone thay đổi.

Miền giá trị thông thường trong MySQL 5.7, 8.0 và 8.4:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất |
|---|---|---|
| DATETIME | 1000-01-01 00:00:00 | 9999-12-31 23:59:59 |

Giá trị có thể có phần giây thập phân nếu khai báo fractional seconds precision:

~~~sql
CREATE TABLE appointments (
    appointment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    starts_at      DATETIME(6) NOT NULL,
    ends_at        DATETIME(6) NOT NULL,
    PRIMARY KEY (appointment_id)
) ENGINE = InnoDB;
~~~

DATETIME(6) lưu đến microsecond. Nếu không ghi fsp, độ chính xác mặc định là 0, nghĩa là không có phần giây thập phân.

### 3.2. DATETIME không tự chuyển đổi theo múi giờ

Giả sử lưu:

~~~sql
INSERT INTO appointments (starts_at, ends_at)
VALUES (
    '2026-11-20 09:00:00',
    '2026-11-20 10:00:00'
);
~~~

Giá trị DATETIME được lưu và đọc như chính các thành phần ngày giờ đã nhập. Nếu session time zone thay đổi từ +07:00 sang +00:00, giá trị DATETIME vẫn là 2026-11-20 09:00:00.

Đặc điểm này hữu ích khi cần giữ giờ địa phương hoặc khi hệ thống có quy ước tự quản lý việc lưu UTC. Tuy nhiên, DATETIME không tự nói cho người đọc biết giá trị là giờ địa phương ở đâu hay UTC. Nếu ứng dụng lưu UTC trong DATETIME, cần thống nhất quy ước đó ở mọi tầng và ghi rõ trong tài liệu/schema.

### 3.3. Khi nào dùng DATETIME?

DATETIME phù hợp khi:

- Cần miền năm rộng đến 9999.
- Cần lưu ngày giờ tương lai vượt giới hạn TIMESTAMP.
- Cần giữ nguyên giờ trên đồng hồ địa phương.
- Hệ thống tự quản lý chuyển đổi múi giờ và có quy ước lưu UTC trong DATETIME.

Ví dụ lịch đặt phòng, lịch học hoặc lịch khám có thể cần giữ giờ địa phương. Nếu lịch gắn với một địa điểm, nên lưu thêm tên múi giờ IANA, chẳng hạn Asia/Ho_Chi_Minh, để có thể diễn giải đúng khi quy tắc múi giờ thay đổi.

## 4. Kiểu TIMESTAMP

### 4.1. Ý nghĩa và miền giá trị

TIMESTAMP biểu diễn một thời điểm. Khi ghi, MySQL chuyển giá trị từ múi giờ của session sang UTC để lưu; khi đọc, MySQL chuyển từ UTC sang múi giờ của session hiện tại.

Miền giá trị của TIMESTAMP trong MySQL 5.7, 8.0 và 8.4 phổ biến vẫn bị giới hạn bởi biểu diễn 32-bit:

| Kiểu | Miền giá trị theo UTC |
|---|---|
| TIMESTAMP | 1970-01-01 00:00:01 đến 2038-01-19 03:14:07 |

Giới hạn này tương ứng với phạm vi thời gian của Unix timestamp 32-bit có dấu. Không nên mặc định rằng MySQL 8.x đã mở rộng TIMESTAMP để lưu ngày đến năm 9999.

Ví dụ:

~~~sql
CREATE TABLE audit_events (
    event_id   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB;
~~~

### 4.2. Chuyển đổi giữa session time zone và UTC

TIMESTAMP chịu ảnh hưởng của biến time_zone trong session. Ví dụ, nếu session đang dùng +07:00 và chèn:

~~~sql
SET time_zone = '+07:00';

INSERT INTO audit_events (event_type, created_at)
VALUES ('LOGIN', '2026-11-20 09:00:00');
~~~

MySQL hiểu giá trị nhập là 09:00 theo múi giờ +07:00, chuyển về UTC để lưu. Khi đọc ở session +00:00, giá trị được hiển thị là 02:00; khi đọc ở session +07:00, nó được hiển thị lại là 09:00.

Như vậy, các session khác múi giờ có thể nhìn thấy cách hiển thị khác nhau của cùng một thời điểm TIMESTAMP. Đây là hành vi có chủ đích.

### 4.3. So sánh DATETIME và TIMESTAMP qua hai session

Ví dụ sau minh họa sự khác biệt:

~~~sql
CREATE TEMPORARY TABLE datetime_timestamp_demo (
    dt DATETIME,
    ts TIMESTAMP
);

SET time_zone = '+07:00';

INSERT INTO datetime_timestamp_demo (dt, ts)
VALUES ('2026-11-20 09:00:00', '2026-11-20 09:00:00');

-- Cùng session +07:00: cả hai hiển thị 09:00:00
SELECT dt, ts FROM datetime_timestamp_demo;

SET time_zone = '+00:00';

-- DATETIME giữ nguyên 09:00; TIMESTAMP hiển thị 02:00
SELECT dt, ts FROM datetime_timestamp_demo;

SET time_zone = '+07:00';
~~~

DATETIME giữ nguyên giá trị lịch; TIMESTAMP giữ nguyên thời điểm và chuyển đổi cách hiển thị theo session time zone.

### 4.4. Khi nào dùng TIMESTAMP?

TIMESTAMP phù hợp với các thời điểm sự kiện nằm trong miền giá trị hỗ trợ và cần được diễn giải nhất quán qua nhiều múi giờ:

- Thời điểm tạo hoặc cập nhật bản ghi.
- Thời điểm thanh toán hoặc nhận sự kiện.
- Thời điểm đăng nhập, ghi log.
- Thời điểm đồng bộ dữ liệu giữa các hệ thống.

Nếu nghiệp vụ cần lưu thời điểm sau năm 2038, hãy xem xét DATETIME với quy ước UTC rõ ràng hoặc mô hình lưu trữ khác phù hợp.

## 5. Bảng so sánh DATE, DATETIME và TIMESTAMP

| Đặc điểm | DATE | DATETIME | TIMESTAMP |
|---|---|---|---|
| Lưu ngày | Có | Có | Có |
| Lưu giờ | Không | Có | Có |
| Lưu múi giờ | Không | Không | Không lưu tên múi giờ; chuyển đổi theo session time zone |
| Tự chuyển đổi qua UTC khi ghi/đọc | Không | Không | Có |
| Miền năm phổ biến | 1000–9999 | 1000–9999 | 1970–2038 |
| Fractional seconds | Không | Có, fsp 0–6 | Có, fsp 0–6 |
| Phù hợp | Ngày lịch | Ngày giờ theo lịch, UTC theo quy ước ứng dụng, lịch tương lai | Thời điểm sự kiện trong miền hỗ trợ |

Lưu ý: TIMESTAMP không lưu tên múi giờ như Asia/Ho_Chi_Minh. Nó lưu thời điểm đã được chuẩn hóa và việc chuyển đổi khi đọc dựa vào time zone của session. Nếu cần tái hiện giờ địa phương gắn với một địa điểm, hãy lưu tên múi giờ riêng.

## 6. Fractional seconds precision (fsp)

### 6.1. Phạm vi

DATETIME và TIMESTAMP hỗ trợ phần giây thập phân với độ chính xác từ 0 đến 6:

| Khai báo | Độ chính xác |
|---|---|
| DATETIME hoặc TIMESTAMP | 0, không lưu phần giây thập phân |
| DATETIME(3) | 3 chữ số thập phân, đến millisecond |
| TIMESTAMP(6) | 6 chữ số thập phân, đến microsecond |

Có thể dùng fsp từ 0 đến 6. Nếu bỏ qua, MySQL mặc định là 0.

Ví dụ:

~~~sql
CREATE TABLE job_runs (
    job_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    started_at  DATETIME(3) NOT NULL,
    recorded_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (job_id)
) ENGINE = InnoDB;
~~~

### 6.2. Hàm thời gian phải cùng độ chính xác mong muốn

Có thể chỉ định fsp cho các hàm hiện tại:

~~~sql
SELECT
    CURRENT_TIMESTAMP(6),
    NOW(6),
    UTC_TIMESTAMP(6);
~~~

Với cột TIMESTAMP(6), có thể khai báo:

~~~sql
created_at TIMESTAMP(6)
    NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
~~~

Nếu cột chỉ có độ chính xác 0 nhưng ứng dụng truyền phần microsecond, phần lẻ sẽ không được lưu đầy đủ. Quy tắc làm tròn hoặc cắt phần lẻ có thể chịu ảnh hưởng của SQL mode TIME_TRUNCATE_FRACTIONAL; hãy kiểm tra cấu hình và kiểm thử hành vi thực tế nếu độ chính xác là yêu cầu nghiệp vụ.

### 6.3. Lưu trữ vật lý

Với định dạng thời gian hiện đại từ MySQL 5.6.4 trở lên, kích thước cơ bản:

| Kiểu | Kích thước cơ bản |
|---|---:|
| DATE | 3 byte |
| DATETIME | 5 byte |
| TIMESTAMP | 4 byte |

DATETIME và TIMESTAMP có thêm byte để lưu phần giây thập phân: fsp 1–2 thêm 1 byte, fsp 3–4 thêm 2 byte và fsp 5–6 thêm 3 byte. Trước MySQL 5.6.4, DATETIME dùng định dạng lưu trữ cũ với kích thước 8 byte và chưa hỗ trợ fractional seconds theo cách hiện đại.

Không nên chọn kiểu dữ liệu chỉ dựa trên chênh lệch một byte. Ý nghĩa thời gian, miền giá trị, múi giờ và khả năng tương thích quan trọng hơn.

## 7. Múi giờ trong MySQL

### 7.1. time_zone của server và session

MySQL có biến time_zone ở phạm vi GLOBAL và SESSION:

~~~sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone;
~~~

- @@GLOBAL.time_zone là múi giờ mặc định server dùng để khởi tạo session mới.
- @@SESSION.time_zone là múi giờ áp dụng cho kết nối hiện tại.
- @@system_time_zone cho biết múi giờ hệ điều hành mà MySQL nhận diện khi khởi động.

Giá trị mặc định của time_zone thường là SYSTEM, nghĩa là dùng múi giờ hệ thống. Có thể đặt múi giờ cho phiên:

~~~sql
SET time_zone = '+00:00';
~~~

Hoặc:

~~~sql
SET time_zone = '+07:00';
~~~

Thay đổi SET GLOBAL time_zone ảnh hưởng đến các kết nối mới sau đó; session đang tồn tại vẫn giữ giá trị SESSION của nó cho đến khi được thay đổi riêng.

### 7.2. Dùng tên múi giờ thay cho offset cố định

MySQL có thể dùng tên múi giờ IANA như Asia/Ho_Chi_Minh:

~~~sql
SET time_zone = 'Asia/Ho_Chi_Minh';
~~~

Để dùng tên múi giờ, các bảng timezone của MySQL phải được nạp và cập nhật phù hợp. Nếu chưa có dữ liệu timezone, lệnh có thể báo lỗi múi giờ không xác định. Trên máy chủ được quản trị, cần đồng bộ timezone tables khi quy tắc múi giờ của hệ điều hành thay đổi.

Offset cố định như +07:00 biểu diễn độ lệch cố định so với UTC. Tên IANA có thể phản ánh quy tắc lịch sử và thay đổi giờ mùa hè (DST) của một khu vực. Với hệ thống hoạt động ở nhiều quốc gia, tên IANA thường phù hợp hơn khi cần chuyển đổi theo quy tắc địa phương.

### 7.3. CURRENT_TIMESTAMP, NOW và UTC_TIMESTAMP

Các hàm thường dùng:

| Hàm | Ý nghĩa |
|---|---|
| NOW() hoặc CURRENT_TIMESTAMP | Thời điểm hiện tại theo session time zone |
| UTC_TIMESTAMP() | Thời điểm hiện tại theo UTC |
| CURDATE() hoặc CURRENT_DATE | Ngày hiện tại theo session time zone |
| UTC_DATE() | Ngày hiện tại theo UTC |

Ví dụ:

~~~sql
SELECT
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now,
    CURDATE() AS session_date,
    UTC_DATE() AS utc_date;
~~~

NOW() và CURRENT_TIMESTAMP trả về thời điểm theo session time zone. Nếu ghi kết quả đó vào DATETIME, MySQL lưu chính giá trị ngày giờ được trả về; DATETIME không tự chuyển sang UTC. Nếu ghi vào TIMESTAMP, giá trị được hiểu theo session time zone rồi chuyển đổi sang UTC để lưu.

## 8. Chọn kiểu dữ liệu theo nghiệp vụ

### 8.1. Ngày sinh

Dùng DATE:

~~~sql
birth_date DATE
~~~

Ngày sinh là ngày lịch; không cần múi giờ hoặc thời điểm trong ngày.

### 8.2. Thời điểm tạo bản ghi

Có thể dùng TIMESTAMP nếu thời điểm nằm trong miền hỗ trợ và ứng dụng muốn MySQL tự chuyển đổi theo UTC:

~~~sql
created_at TIMESTAMP(6)
    NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
~~~

Nếu hệ thống cần lưu thời điểm vượt năm 2038, có thể dùng DATETIME(6) với quy ước luôn lưu UTC:

~~~sql
created_at DATETIME(6) NOT NULL
~~~

Ứng dụng phải bảo đảm mọi writer chuyển đổi về UTC trước khi lưu và mọi reader hiểu giá trị đó là UTC.

### 8.3. Lịch hẹn tại một địa điểm

Với lịch hẹn, giờ trên đồng hồ địa phương có thể là một phần của nghiệp vụ. Mô hình có thể gồm:

~~~sql
CREATE TABLE appointments (
    appointment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    starts_at      DATETIME(6) NOT NULL,
    time_zone_name VARCHAR(64) NOT NULL,
    PRIMARY KEY (appointment_id)
) ENGINE = InnoDB;
~~~

Ví dụ starts_at = '2026-11-20 09:00:00' cùng time_zone_name = 'Asia/Ho_Chi_Minh' có nghĩa lịch hẹn lúc 09:00 theo giờ khu vực đó. Khi cần xác định thời điểm UTC, ứng dụng hoặc MySQL có thể chuyển đổi bằng dữ liệu timezone tương ứng.

Với khu vực có DST, một giờ địa phương có thể bị lặp hoặc không tồn tại khi đồng hồ chuyển đổi. Hệ thống đặt lịch cần xác định cách xử lý giờ mơ hồ hoặc không hợp lệ, và có thể lưu thêm thời điểm UTC đã được xác nhận để tránh diễn giải khác nhau về sau.

### 8.4. Thời điểm hết hạn

Nếu thời điểm hết hạn là một instant độc lập với nơi người dùng đang ở, nên lưu theo UTC. Có thể dùng TIMESTAMP nếu miền thời gian phù hợp; nếu thời hạn có thể vượt năm 2038, dùng DATETIME với quy ước UTC hoặc một biểu diễn khác phù hợp.

Không nên lưu “hết hạn sau 30 ngày” chỉ bằng một ngày giờ địa phương mà không xác định chính sách múi giờ và DST. Cần làm rõ 30 ngày lịch hay 720 giờ thực tế.

## 9. Miền giá trị và khác biệt theo phiên bản MySQL

### 9.1. Bảng tổng hợp

| Phiên bản | DATE | DATETIME | TIMESTAMP | Fractional seconds |
|---|---|---|---|---|
| MySQL 5.5 và cũ hơn | 1000–9999 | 1000–9999 | 1970–2038 | Chưa hỗ trợ theo định dạng hiện đại |
| MySQL 5.6.4 trở lên | 1000–9999 | 1000–9999 | 1970–2038 | Hỗ trợ fsp 0–6 |
| MySQL 5.7 | 1000–9999 | 1000–9999 | 1970–2038 | Hỗ trợ fsp 0–6 |
| MySQL 8.0 | 1000–9999 | 1000–9999 | 1970–2038 | Hỗ trợ fsp 0–6 |
| MySQL 8.4 LTS | 1000–9999 | 1000–9999 | 1970–2038 | Hỗ trợ fsp 0–6 |

Các miền DATE và DATETIME được viết rút gọn theo năm; giới hạn đầy đủ của DATE là 1000-01-01 đến 9999-12-31, còn DATETIME là 1000-01-01 00:00:00 đến 9999-12-31 23:59:59. Miền TIMESTAMP ở bảng trên là theo UTC.

### 9.2. Những thay đổi quan trọng

- **Trước MySQL 5.6.4:** DATETIME dùng định dạng lưu trữ cũ, chiếm 8 byte và các kiểu thời gian chưa hỗ trợ fractional seconds theo cách hiện đại.
- **Từ MySQL 5.6.4:** DATETIME có định dạng lưu trữ gọn hơn và TIME, DATETIME, TIMESTAMP hỗ trợ fractional seconds với độ chính xác đến 6 chữ số.
- **MySQL 5.7, 8.0 và 8.4:** miền TIMESTAMP phổ biến vẫn kết thúc ở năm 2038; nâng cấp lên 8.x không tự mở rộng miền này.

Khi nâng cấp server hoặc chuyển dữ liệu giữa phiên bản, hãy kiểm tra DDL, giá trị biên, fractional seconds và SQL mode. Không nên chỉ dựa trên việc migration chạy thành công; cần kiểm thử các giá trị sát giới hạn.

## 10. Giá trị ngày giờ không hợp lệ và SQL mode

MySQL kiểm tra tính hợp lệ của giá trị ngày giờ khi insert, update và chuyển đổi. Cách xử lý một số giá trị không hợp lệ còn phụ thuộc SQL mode.

Ví dụ về giá trị không hợp lệ:

- 2026-02-30: ngày không tồn tại trong lịch.
- 2026-13-01: tháng nằm ngoài phạm vi.
- 0000-00-00: zero date.
- 2026-00-15: tháng bằng 0.

Các SQL mode có liên quan:

- **STRICT_TRANS_TABLES** hoặc **STRICT_ALL_TABLES**: ảnh hưởng cách xử lý dữ liệu không hợp lệ; trong chế độ strict, thao tác thường bị từ chối thay vì âm thầm điều chỉnh.
- **NO_ZERO_DATE**: kiểm soát việc chấp nhận zero date trong các phiên bản có hỗ trợ mode này.
- **NO_ZERO_IN_DATE**: kiểm soát ngày có phần năm hợp lệ nhưng tháng hoặc ngày bằng 0.
- **ALLOW_INVALID_DATES**: nới lỏng một phần kiểm tra ngày trong một số trường hợp; không nên dùng để hợp thức hóa dữ liệu ngày sai trong ứng dụng.

Có thể xem cấu hình:

~~~sql
SELECT @@SESSION.sql_mode;
SELECT @@GLOBAL.sql_mode;
~~~

Các mode NO_ZERO_DATE và NO_ZERO_IN_DATE đã được đánh dấu deprecated trong MySQL 8.0.2; hành vi cụ thể còn phụ thuộc phiên bản và các mode strict đang bật. Hãy tham khảo tài liệu đúng phiên bản và tránh lưu zero date hoặc ngày không hợp lệ như một cách biểu diễn “chưa biết”.

Nếu ngày chưa biết, hãy dùng NULL nếu nghiệp vụ cho phép, hoặc mô hình trạng thái riêng. Không nên dùng 0000-00-00 để thay thế NULL vì các phép so sánh, hàm ngày giờ và chuyển dữ liệu có thể cho kết quả khó dự đoán.

## 11. Hàm chuyển đổi và truy vấn ngày giờ

### 11.1. Chuyển đổi giữa múi giờ

CONVERT_TZ() chuyển một giá trị ngày giờ từ múi giờ nguồn sang múi giờ đích:

~~~sql
SELECT CONVERT_TZ(
    '2026-11-20 09:00:00',
    'Asia/Ho_Chi_Minh',
    '+00:00'
);
~~~

Khi dùng tên múi giờ, timezone tables phải được nạp. Nếu không, CONVERT_TZ có thể trả về NULL.

### 11.2. Chuyển đổi giữa DATE và DATETIME

Có thể lấy phần ngày từ DATETIME:

~~~sql
SELECT DATE('2026-11-20 09:15:30');
~~~

Có thể ghép ngày với giờ:

~~~sql
SELECT TIMESTAMP('2026-11-20', '09:15:30');
~~~

Kết quả là một giá trị DATETIME; hàm TIMESTAMP(date, time) ở đây là hàm ghép thành phần ngày và giờ, không phải phép ép sang kiểu cột TIMESTAMP có chuyển đổi múi giờ.

### 11.3. Tránh so sánh chuỗi tùy tiện

Nên dùng literal ngày giờ theo định dạng rõ ràng và tham số hóa truy vấn:

~~~sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= ?
  AND occurred_at < ?;
~~~

Khoảng nửa mở [start, end) thường thuận tiện khi truy vấn theo ngày hoặc tháng vì tránh phải đoán giá trị phần giây cuối cùng. Ví dụ, lấy sự kiện trong ngày 20/11/2026:

~~~sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= '2026-11-20 00:00:00'
  AND occurred_at <  '2026-11-21 00:00:00';
~~~

Với TIMESTAMP, hai mốc được diễn giải theo session time zone. Hãy đặt session timezone hoặc chuyển mốc đầu vào về cùng quy ước với dữ liệu trước khi truy vấn.

## 12. Lưu ý khi làm việc với ứng dụng và connection pool

Một ứng dụng có thể kết nối đến MySQL từ nhiều máy chủ ở các múi giờ khác nhau. Nếu mỗi kết nối dùng time_zone khác nhau, TIMESTAMP vẫn đại diện cùng instant nhưng hiển thị khác nhau; các biểu thức NOW(), CURDATE() và literal ghi vào TIMESTAMP cũng chịu ảnh hưởng của session.

Các nguyên tắc vận hành:

1. Chọn một chính sách thống nhất, thường là đặt session time_zone về UTC cho dịch vụ backend.
2. Cấu hình time_zone trên mọi kết nối vật lý trong connection pool.
3. Không thay đổi session time_zone tùy tiện rồi trả kết nối về pool mà không reset.
4. Khi lưu giờ địa phương, lưu thêm tên múi giờ IANA và xác định cách xử lý DST.
5. Dùng DATETIME nếu cần lưu lịch giờ địa phương hoặc thời gian vượt giới hạn TIMESTAMP; ghi rõ quy ước UTC hay local time.
6. Kiểm thử các giá trị sát miền nhỏ nhất/lớn nhất và các giá trị có fractional seconds.

Ví dụ khởi tạo session theo UTC:

~~~sql
SET time_zone = '+00:00';
~~~

Có thể đặt giá trị mặc định cho các kết nối mới bằng cấu hình server hoặc thiết lập của nền tảng triển khai. Tuy nhiên, ứng dụng vẫn nên xác minh @@SESSION.time_zone trên kết nối thực tế.

## 13. Checklist chọn kiểu và kiểm thử

Trước khi thiết kế cột ngày giờ, hãy trả lời:

1. Dữ liệu là ngày lịch, giờ địa phương hay một thời điểm trên UTC timeline?
2. Có cần phần giờ hay chỉ cần ngày?
3. Có cần độ chính xác millisecond hoặc microsecond không?
4. Dữ liệu có thể vượt năm 2038 không?
5. Ứng dụng có chạy ở nhiều múi giờ không?
6. Nếu lưu giờ địa phương, có cần lưu tên múi giờ IANA không?
7. SQL mode có từ chối ngày không hợp lệ và zero date không?
8. Connection pool có thiết lập và reset session time_zone nhất quán không?

Các trường hợp kiểm thử tối thiểu:

- Ngày hợp lệ ở đầu và cuối miền DATE.
- DATETIME ở đầu và cuối miền hỗ trợ.
- TIMESTAMP ở sát hai đầu miền UTC.
- Giá trị có phần giây .123456 với cột fsp 0, 3 và 6.
- Đọc cùng một TIMESTAMP qua session UTC và session địa phương.
- Ghi và đọc DATETIME qua hai session time zone khác nhau để xác nhận giá trị không bị chuyển đổi.
- Ngày không hợp lệ, zero date và NULL theo SQL mode thực tế.
- Thời điểm trong vùng có quy tắc DST nếu ứng dụng phục vụ khu vực đó.

## 14. Những nhầm lẫn thường gặp

**“DATETIME và TIMESTAMP giống nhau, chỉ khác cách viết.”** Không. TIMESTAMP chuyển đổi theo session time zone và có miền giá trị hẹp hơn; DATETIME giữ nguyên giá trị lịch và có miền năm rộng hơn.

**“TIMESTAMP lưu tên múi giờ.”** Không. Nó lưu thời điểm và MySQL chuyển đổi theo múi giờ session khi ghi/đọc. Tên múi giờ địa điểm cần được lưu riêng nếu nghiệp vụ cần.

**“MySQL 8.x đã loại bỏ giới hạn năm 2038 của TIMESTAMP.”** Không. Các dòng 5.7, 8.0 và 8.4 phổ biến vẫn có miền TIMESTAMP kết thúc ở 2038-01-19 03:14:07 UTC.

**“DATETIME tự động lưu UTC.”** Không. DATETIME lưu đúng giá trị lịch được đưa vào. Nếu chọn quy ước UTC, ứng dụng phải chuyển đổi trước khi ghi và diễn giải nhất quán khi đọc.

**“DATE có thể lưu thời điểm bằng cách đặt giờ bằng 0.”** Không. DATE chỉ lưu ngày; giờ bị loại bỏ.

**“Tăng fractional seconds precision làm miền ngày rộng hơn.”** Không. FSP chỉ tăng độ chính xác phần giây, không mở rộng miền năm của kiểu dữ liệu.

**“Zero date là cách chuẩn để biểu diễn ngày chưa biết.”** Không. Dùng NULL hoặc trạng thái nghiệp vụ rõ ràng.

## Kết luận

DATE dành cho ngày lịch; DATETIME lưu ngày giờ không tự chuyển đổi múi giờ và có miền năm rộng; TIMESTAMP biểu diễn thời điểm, chuyển đổi giữa session time zone và UTC nhưng bị giới hạn đến năm 2038 trong các phiên bản MySQL phổ biến. DATETIME và TIMESTAMP hỗ trợ fractional seconds từ 0 đến 6 chữ số trong MySQL 5.6.4 trở lên.

Hãy chọn kiểu theo ý nghĩa nghiệp vụ, không chỉ theo tên cột. Dùng DATE cho ngày, TIMESTAMP cho thời điểm nằm trong miền hỗ trợ và cần chuyển đổi múi giờ, DATETIME cho giờ lịch hoặc thời điểm cần miền rộng hơn với quy ước UTC rõ ràng. Kết hợp chính sách time_zone, SQL mode và kiểm thử giá trị biên để dữ liệu ngày giờ nhất quán qua các phiên bản MySQL và môi trường triển khai.
