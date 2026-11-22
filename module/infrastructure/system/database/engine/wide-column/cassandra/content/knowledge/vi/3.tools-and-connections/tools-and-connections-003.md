# CONSISTENCY, SERIAL CONSISTENCY, PAGING và TRACING trong cqlsh

## 1. Bốn lệnh giúp kiểm soát và quan sát điều gì?

Apache Cassandra là cơ sở dữ liệu wide-column phân tán: dữ liệu của một partition được đặt trên các replica theo cấu hình replication của keyspace. Một câu lệnh CQL được gửi đến **coordinator** (node nhận yêu cầu), rồi coordinator phối hợp các replica để đọc hoặc ghi. Trong mục **Công cụ và kết nối**, bốn lệnh của **cqlsh** giúp ta kiểm tra những phần khác nhau của đường đi này:

| Lệnh cqlsh | Câu hỏi cần trả lời | Phạm vi tác động |
| --- | --- | --- |
| `CONSISTENCY` | Cần bao nhiêu replica phản hồi khi đọc/ghi? | Mức consistency của các thao tác tiếp theo trong phiên cqlsh. |
| `SERIAL CONSISTENCY` | Pha đồng thuận của ghi có điều kiện `IF` cần mức nào? | Chỉ tác động đến **serial/Paxos phase** của lightweight transaction (LWT). |
| `PAGING` | Mỗi lần cqlsh lấy và hiển thị bao nhiêu hàng kết quả? | Cách phân trang của các truy vấn đọc trong phiên. |
| `TRACING` | Coordinator và replica đã thực hiện những bước nào? | Bật/tắt thu thập và in trace cho các truy vấn tiếp theo trong phiên. |

**Phân biệt ngay từ đầu:** `CONSISTENCY` và `SERIAL CONSISTENCY` liên quan đến *đảm bảo nhất quán*, `PAGING` liên quan đến *cách tải kết quả*, còn `TRACING` liên quan đến *quan sát và chẩn đoán*. Bật tracing hay giảm page size không làm tăng replication factor; nâng consistency cũng không sửa được partition key thiết kế sai.

Sau bài này, bạn có thể:

1. Chọn consistency phù hợp với replication factor, datacenter và nhu cầu đọc/ghi.
2. Chạy `INSERT ... IF NOT EXISTS` và `UPDATE ... IF ...` với serial consistency, đọc cột `[applied]`.
3. Dùng `PAGING` để duyệt kết quả từng trang, phân biệt page size và `LIMIT`.
4. Bật `TRACING` để xem luồng truy vấn, sau đó tắt và diễn giải được giới hạn của trace.
5. Kết nối các thao tác cqlsh với việc cấu hình truy vấn trong ứng dụng Java.

## 2. Chuẩn bị môi trường và dữ liệu lab

Yêu cầu: Cassandra đang chạy, cqlsh có thể kết nối tới native port (mặc định **9042**), và tài khoản có quyền tạo keyspace/bảng trong môi trường học tập. Ví dụ bên dưới dùng **một node với RF = 1** để có thể thực thi tại máy cá nhân; phần giải thích quorum nhiều replica sẽ dùng tình huống giả định riêng.

Từ terminal:

~~~bash
cqlsh 127.0.0.1 9042
~~~

Trong cqlsh:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS cqlsh_consistency_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE cqlsh_consistency_lab;

-- Bảng thiết kế cho truy vấn: sự kiện của 1 thiết bị trong 1 ngày.
CREATE TABLE IF NOT EXISTS events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  temperature_c decimal,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

-- Bảng nhỏ để minh họa cập nhật có điều kiện (LWT).
CREATE TABLE IF NOT EXISTS device_lease (
  device_id text PRIMARY KEY,
  holder text,
  generation int
);
~~~

Các sự kiện cùng `(device_id, event_day)` thuộc cùng **partition logic**. `event_time` và `event_id` là **clustering columns**, giúp phân biệt và sắp thứ tự các row trong partition. Mẫu truy vấn của bài sẽ luôn lọc đủ partition key; tránh thêm `ALLOW FILTERING` để chữa một truy vấn không phù hợp với cấu trúc bảng.

Chèn sáu row để lát nữa thấy rõ phân trang:

~~~sql
INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:01:00Z',
        11111111-1111-4111-8111-111111111111, 25.1);

INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:02:00Z',
        22222222-2222-4222-8222-222222222222, 25.2);

INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:03:00Z',
        33333333-3333-4333-8333-333333333333, 25.3);

INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:04:00Z',
        44444444-4444-4444-8444-444444444444, 25.4);

INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        55555555-5555-4555-8555-555555555555, 25.5);

INSERT INTO events_by_device_day
  (device_id, event_day, event_time, event_id, temperature_c)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:06:00Z',
        66666666-6666-4666-8666-666666666666, 25.6);
~~~

Các UUID và thời điểm cố định giúp chạy lại lab không tạo thêm hàng mới do `INSERT` cùng primary key là thao tác **upsert**. Nếu bảng đã tồn tại nhưng có schema khác, `IF NOT EXISTS` không tự cập nhật schema đó; khi gặp lỗi, dùng `DESCRIBE TABLE` để kiểm tra.

## 3. CONSISTENCY: mức phản hồi cần thiết cho đọc và ghi

### 3.1. Cách đặt trong cqlsh

~~~sql
-- Thiết lập cho các thao tác tiếp theo trong phiên này.
CONSISTENCY ONE;

SELECT event_time, temperature_c
FROM cqlsh_consistency_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 6;

-- Ví dụ chỉ nên chọn sau khi xem RF/datacenter của cluster thực.
CONSISTENCY LOCAL_QUORUM;

-- Trở về mức phù hợp với lab đơn node.
CONSISTENCY ONE;
~~~

`CONSISTENCY` là **lệnh riêng của cqlsh**, đặt mức consistency cho thao tác đọc/ghi tiếp theo của **phiên cqlsh đang mở**. Nó không sửa keyspace, không đổi số replica, không tự tác động đến các phiên cqlsh khác hay ứng dụng Java. Để biết cú pháp mà bản cqlsh đang dùng hỗ trợ, chạy `HELP CONSISTENCY;`.

### 3.2. Replication factor và quorum

**Replication factor (RF)** mô tả số bản sao của một partition theo chiến lược replication của keyspace. **Consistency level (CL)** mô tả yêu cầu phản hồi cho *một thao tác*. Hai khái niệm độc lập:

- Với **RF = 3** trong một datacenter và `LOCAL_QUORUM`, một thao tác cần ít nhất **2 replica** trong datacenter đó phản hồi thành công.
- `LOCAL_ONE` và `ONE` thường chỉ yêu cầu **1 replica** phản hồi (khác nhau về phạm vi local datacenter).
- `ALL` yêu cầu tất cả các replica có liên quan phản hồi, nên một replica không sẵn sàng có thể làm thao tác thất bại.
- `QUORUM` tính quorum trên tổng số replica áp dụng; `LOCAL_QUORUM` tính trên các replica **của datacenter cục bộ**. Trong triển khai đa datacenter, khác biệt này quan trọng cho độ trễ và khả năng chịu lỗi.
- Mức `ANY` dành cho **ghi**, có thể chấp nhận hint khi replica không sẵn sàng; không dùng làm consistency level cho truy vấn đọc.

Ví dụ về lựa chọn (giả định RF = 3 ở một datacenter):

| Mức | Phản hồi cần thiết cho trường hợp RF = 3 | Đánh đổi |
| --- | --- | --- |
| `ONE` | 1 replica | Độ trễ thấp hơn, có thể đọc giá trị cũ khi replica khác chưa đồng bộ. |
| `LOCAL_QUORUM` | 2 replica cùng datacenter | Cân bằng độ sẵn sàng và tính nhất quán trong datacenter. |
| `ALL` | Cả 3 replica | Yêu cầu cao hơn, dễ thất bại nếu thiếu replica. |

Với hệ thống đa datacenter, hãy xem đúng cấu hình `NetworkTopologyStrategy` và số replica **theo từng datacenter**, không áp dụng máy móc bảng RF = 3 này.

#### Đọc/ghi ở quorum không đồng nghĩa transaction SQL

Trong mô hình đơn datacenter RF = 3, nếu ghi với `W = 2` và đọc với `R = 2` thì `W + R = 4 > 3`. Tập replica phản hồi của hai thao tác phải giao nhau, giúp đạt mức bảo đảm đọc/ghi mạnh hơn trong các điều kiện phù hợp. Tuy nhiên:

- Cassandra vẫn dùng timestamp/version của cell để hòa giải phiên bản; các ghi đồng thời, clock skew, retry và xóa dữ liệu có thể ảnh hưởng hành vi thực tế.
- Quorum **không tạo transaction nhiều row**, không bảo đảm toàn bộ chuỗi truy vấn là nguyên tử và không thay thế **LWT** khi cần so sánh rồi cập nhật.
- `CONSISTENCY ONE` không tự động có nghĩa ghi thất bại khi replica khác chậm; độ sẵn sàng và khả năng nhìn thấy bản ghi tùy trạng thái replica và cơ chế đồng bộ.

**Với lab RF = 1:** `ONE` chỉ cần replica duy nhất. `LOCAL_QUORUM` với RF = 1 trong datacenter đó cũng chỉ cần một replica, nên không chứng minh được hành vi quorum giữa nhiều node. Không đặt `TWO` hoặc `THREE` rồi kỳ vọng lab đơn node đáp ứng được: số replica không đủ.

### 3.3. Khi nào thao tác thất bại?

Các lỗi có thể gặp gồm:

- `Unavailable`: hệ thống xác định không đủ replica đang sẵn sàng cho consistency yêu cầu.
- `ReadTimeout` hoặc `WriteTimeout`: không nhận đủ phản hồi trong thời gian quy định.
- `ReadFailure` hoặc `WriteFailure`: replica báo lỗi trong quá trình xử lý.

**Timeout của ghi không chứng minh dữ liệu chưa được ghi.** Một phần replica có thể đã thực hiện thao tác trước khi client nhận timeout; khi chạy lại cần hiểu idempotency của câu CQL. Với ghi có điều kiện, tránh tự động retry vô điều kiện nếu chưa kiểm tra kết quả và trạng thái dữ liệu.

## 4. SERIAL CONSISTENCY: pha Paxos của ghi có điều kiện

### 4.1. Vì sao cần ghi có điều kiện?

Ghi thông thường trong Cassandra có tính chất upsert theo primary key. Nếu hai client cùng cố giành quyền xử lý một thiết bị và chỉ kiểm tra bằng `SELECT` rồi `INSERT`, cả hai có thể đọc trạng thái trống trước khi ghi. Đây là tình huống cần **lightweight transaction (LWT)**: câu lệnh `INSERT ... IF NOT EXISTS` hoặc `UPDATE ... IF ...`.

LWT dùng cơ chế đồng thuận Paxos để thực hiện so sánh và thay đổi có điều kiện trên phạm vi điều kiện được hỗ trợ. So với ghi thường, LWT có thêm bước phối hợp và độ trễ; chỉ dùng khi cần semantics có điều kiện.

### 4.2. Hai mức SERIAL và LOCAL_SERIAL

~~~sql
-- Áp dụng mức thông thường cho pha ghi/learn.
CONSISTENCY ONE;

-- Áp dụng cho pha đồng thuận của LWT.
SERIAL CONSISTENCY SERIAL;

-- Hoặc dùng pha đồng thuận trong datacenter cục bộ khi kiến trúc cho phép.
SERIAL CONSISTENCY LOCAL_SERIAL;
~~~

`SERIAL CONSISTENCY` chỉ chấp nhận `SERIAL` hoặc `LOCAL_SERIAL`, không nhận `ONE` hay `LOCAL_QUORUM` làm giá trị serial. Theo tài liệu cqlsh, giá trị này áp dụng cho **các cập nhật có điều kiện** (`INSERT`, `UPDATE`, `DELETE` có `IF`). Trong một LWT có hai mức cần phân biệt:

| Thiết lập | Pha | Ý nghĩa |
| --- | --- | --- |
| `SERIAL CONSISTENCY SERIAL` / `LOCAL_SERIAL` | Serial/Paxos phase | Điều phối đồng thuận để quyết định điều kiện có được áp dụng hay không. |
| `CONSISTENCY ONE` / `LOCAL_QUORUM` / v.v. | Regular/learn phase | Yêu cầu phản hồi và khả năng nhìn thấy kết quả của ghi sau pha đồng thuận. |

`SERIAL` có phạm vi rộng hơn giữa các datacenter; `LOCAL_SERIAL` giới hạn phạm vi đồng thuận vào datacenter cục bộ phù hợp với kiến trúc. Trong hệ thống phân tán nhiều DC, cần chọn dựa trên yêu cầu điều phối và cấu hình replication; không tự giả định `LOCAL_SERIAL` phù hợp cho mọi ràng buộc duy nhất trên toàn hệ thống.

### 4.3. Thực hành INSERT IF NOT EXISTS

Trong lab, đảm bảo đang dùng keyspace phù hợp và đặt mức consistency:

~~~sql
USE cqlsh_consistency_lab;
CONSISTENCY ONE;
SERIAL CONSISTENCY SERIAL;

INSERT INTO device_lease (device_id, holder, generation)
VALUES ('sensor-01', 'worker-A', 1)
IF NOT EXISTS;
~~~

Nếu row chưa tồn tại, kết quả thường có dạng:

~~~text
 [applied]
-----------
      True
~~~

Chạy lại **chính xác câu lệnh đó** sẽ không tạo hoặc ghi đè row:

~~~sql
INSERT INTO device_lease (device_id, holder, generation)
VALUES ('sensor-01', 'worker-A', 1)
IF NOT EXISTS;

SELECT * FROM device_lease WHERE device_id = 'sensor-01';
~~~

Kết quả của lệnh lặp thường có `[applied] = False` kèm giá trị hiện có. Nếu lab từng có row trước đó, lần chạy đầu cũng có thể trả `False`; hãy đối chiếu trạng thái trước khi diễn giải.

### 4.4. UPDATE IF và optimistic concurrency

~~~sql
-- Thành công nếu generation thực tế đúng bằng 1.
UPDATE device_lease
SET holder = 'worker-B', generation = 2
WHERE device_id = 'sensor-01'
IF generation = 1;

-- Điều kiện cũ không còn đúng, lệnh này sẽ không ghi đè.
UPDATE device_lease
SET holder = 'worker-C', generation = 3
WHERE device_id = 'sensor-01'
IF generation = 1;

SELECT holder, generation
FROM device_lease
WHERE device_id = 'sensor-01';
~~~

Khi chỉ một client được cập nhật thế hệ từ 1 lên 2, `[applied] = True` xác nhận câu lệnh thỏa điều kiện. Client đến sau với `IF generation = 1` sẽ nhận `False`, cần đọc lại trạng thái và quyết định xử lý. Đừng coi `[applied] = False` là lỗi mạng; đó là **kết quả nghiệp vụ của điều kiện không thỏa**.

**Lưu ý:** RF = 1 đủ để diễn tập cú pháp, nhưng không mô phỏng tính chịu lỗi hoặc độ trễ Paxos trên cluster nhiều node. Trên môi trường thật, kiểm tra các mức consistency với RF và topology thực tế. `IF` không biến một quy trình nhiều partition thành transaction tổng quát.

## 5. PAGING: đọc từng trang kết quả

### 5.1. Cú pháp và trải nghiệm trong cqlsh

~~~sql
-- Kích hoạt paging nếu đang tắt.
PAGING ON;

-- Mỗi lượt lấy tối đa 2 hàng để dễ quan sát.
PAGING 2;

SELECT event_time, temperature_c
FROM cqlsh_consistency_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Với 6 row của lab, cqlsh hiển thị khoảng **2 row/trang**, rồi chờ người dùng yêu cầu trang tiếp theo. Do bảng có `CLUSTERING ORDER BY (event_time DESC, event_id ASC)`, ta dự kiến thấy thời điểm mới trước. Dạng nhắc chuyển trang tùy phiên bản và terminal.

~~~sql
-- Trở về kích thước trang mặc định của cqlsh.
PAGING ON;

-- Tắt paging cho truy vấn nhỏ nếu thực sự cần.
PAGING OFF;

-- Nên bật lại trước khi xem tập kết quả lớn.
PAGING ON;
~~~

`PAGING <n>` đặt số row mục tiêu mỗi page; phía client/driver sử dụng paging state để lấy tiếp các kết quả. Đây **không phải** số bản sao và cũng không phải số row Cassandra lưu trong một partition.

### 5.2. PAGING khác LIMIT như thế nào?

| Cơ chế | Điều khiển | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| `PAGING 2` | Số row trong mỗi lần lấy/hiển thị | Query có 6 row → khoảng 3 trang | Có thể tiếp tục lấy các trang cho tới khi hết kết quả. |
| `LIMIT 3` | Tổng số row tối đa mà câu SELECT trả về | Query có 6 row → tối đa 3 row | Không thể lấy row thứ 4 từ chính câu truy vấn đó. |
| `PAGING OFF` | Không phân trang tương tác trong cqlsh | Có thể in nhiều row một lượt | Dễ tạo output lớn hoặc gây tốn bộ nhớ khi truy vấn có kết quả lớn. |

Bạn có thể dùng cả hai:

~~~sql
PAGING 2;
SELECT event_time, temperature_c
FROM cqlsh_consistency_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 3;
~~~

Ở đây số row trả về tối đa là **3**; cqlsh có thể lấy và in qua hai trang. `LIMIT` không luôn là công cụ kiểm soát toàn bộ chi phí truy vấn: truy vấn thiếu partition key có thể gây quét rộng dù `LIMIT` nhỏ. Phải thiết kế truy vấn phù hợp với khóa chính trước.

### 5.3. Chọn kích thước trang

Page size quá nhỏ tạo nhiều lượt trao đổi client–server; page size quá lớn tăng dữ liệu giữ trong bộ nhớ, băng thông mỗi lượt và thời gian chờ trang. Kích thước phù hợp tùy độ rộng row, truy vấn, mạng và tài nguyên client.

**Một số lưu ý:**

- Paging là thao tác **lấy kết quả từng phần**, không cung cấp ảnh chụp nhất quán của cả truy vấn qua các thời điểm khi dữ liệu có ghi đồng thời.
- Paging không sửa được hot partition hoặc partition quá lớn; cần chọn partition key và bucket kích thước thích hợp.
- Không sử dụng `PAGING OFF` cho việc xuất dữ liệu sản xuất có hàng triệu row. Các bài toán bulk export/import và backup có công cụ vận hành riêng.
- Trong ứng dụng Java, paging được điều khiển qua driver (fetch size, paging state, reactive/async iteration), không bị ảnh hưởng bởi lệnh `PAGING` ở một phiên cqlsh khác.

## 6. TRACING: quan sát đường đi của truy vấn

### 6.1. Bật và tắt tracing đúng cách

~~~sql
-- Chỉ bật khi cần điều tra truy vấn cụ thể.
TRACING ON;

SELECT event_time, temperature_c
FROM cqlsh_consistency_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 3;

-- Tắt ngay sau truy vấn cần xem.
TRACING OFF;
~~~

Khi tracing được bật, cqlsh in các sự kiện theo dõi sau khi truy vấn hoàn thành. Các trường có thể xuất hiện gồm **activity** (hoạt động), **timestamp**, **source** (node thực hiện) và **source_elapsed** (thời gian tính tại nguồn). Tùy phiên bản, cqlsh cũng hiển thị ID của tracing session. Đừng coi các dòng trace hoặc con số độ trễ dưới đây là hằng số: chúng thay đổi theo cluster và tải.

Ví dụ dạng thông tin cần đọc:

~~~text
Tracing session: <uuid-phien-trace>
activity                  | source       | source_elapsed
--------------------------+--------------+---------------
Preparing statement ...   | <node-A>     | ...
Executing ...             | <node-A>     | ...
Sending message to ...    | <node-A>     | ...
Received response from ...| <node-B>     | ...
~~~

Nội dung sự kiện cụ thể không cố định và trên lab một node có thể không có bước gửi mạng giữa nhiều node. Từ trace, ta chủ yếu quan sát **coordinator làm gì, replica nào tham gia, giai đoạn nào tiêu tốn thời gian và có dấu hiệu fan-out bất thường hay không**.

### 6.2. Xem lại tracing session

Một số phiên bản cqlsh hỗ trợ xem lại trace đã ghi:

~~~sql
-- Thay UUID dưới đây bằng session id THỰC hiển thị ở trace trước đó.
SHOW SESSION 123e4567-e89b-12d3-a456-426614174000;
~~~

Lệnh trên minh họa **cú pháp**, UUID là placeholder và sẽ không có dữ liệu nếu chưa phát sinh session tương ứng. Tracing events được Cassandra lưu trong các bảng hệ thống dùng cho tracing với thời gian tồn tại hữu hạn; dữ liệu trace có thể chưa đầy đủ hoặc đã hết hạn. Nếu dùng cqlsh khác phiên bản, xem `HELP SHOW`/tài liệu phiên bản tương ứng.

### 6.3. Khi nào tracing hữu ích?

| Hiện tượng | Câu hỏi có thể điều tra bằng TRACING | Điều TRACING không thay thế |
| --- | --- | --- |
| SELECT theo partition key chậm | Có trao đổi với nhiều replica? Bước nào có độ trễ cao? | Metrics server, log, profiling, kiểm tra hạ tầng. |
| Read timeout khi nâng consistency | Coordinator đã chờ phản hồi từ những replica nào? | Kiểm tra node/down state, RF và mạng. |
| Query trả nhiều row | Có dấu hiệu nhiều page hoặc nhiều hoạt động đọc? | Thiết kế schema/partition key và phân tích phân phối dữ liệu. |
| LWT chậm | Có thể thấy các giai đoạn liên quan đến điều phối? | Đo tỷ lệ tranh chấp, phân tích retry và tải hệ thống. |

**Chi phí tracing:** kích hoạt thu thập sự kiện trên các node, làm tăng overhead và ghi dữ liệu truy vết. Chỉ bật cho truy vấn cần điều tra, rồi `TRACING OFF`; không để bật suốt bài test tải. Nội dung trace có thể chứa thông tin kỹ thuật hoặc truy vấn, nên xử lý theo chính sách vận hành của môi trường.

## 7. Kết hợp bốn lệnh trong một buổi chẩn đoán

Giả sử có yêu cầu: “Đọc sự kiện của thiết bị hơi chậm và có lúc client báo timeout”. Thứ tự thực hành hợp lý:

~~~sql
SHOW HOST;
DESCRIBE KEYSPACE cqlsh_consistency_lab;
DESCRIBE TABLE cqlsh_consistency_lab.events_by_device_day;

-- Lab RF=1: lựa chọn đọc/ghi an toàn để minh họa.
CONSISTENCY ONE;
PAGING 2;

-- Chỉ bật trace cho truy vấn mục tiêu.
TRACING ON;
SELECT event_time, temperature_c
FROM cqlsh_consistency_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 3;
TRACING OFF;

-- Thiết lập này chỉ có tác dụng với LWT tiếp theo.
SERIAL CONSISTENCY SERIAL;
~~~

Đọc kết quả theo thứ tự:

1. Xác nhận endpoint/cluster hiện tại qua `SHOW HOST`; xác nhận replication của keyspace.
2. Kiểm tra `WHERE` có đủ partition key và điều kiện clustering phù hợp không.
3. Kiểm tra consistency yêu cầu có được **RF và các replica đang hoạt động** đáp ứng không.
4. Xem phân trang để tránh nhầm “đợi trang tiếp theo” với truy vấn treo.
5. Quan sát trace một truy vấn đại diện; kết hợp metrics và log khi phân tích nguyên nhân gốc.

**Đừng thử tăng hoặc giảm consistency trên production chỉ vì một trace bất thường.** Thay đổi CL là thay đổi hợp đồng đọc/ghi, có thể ảnh hưởng tính nhất quán của chức năng và lỗi khi replica không sẵn sàng. Nếu yêu cầu mức nhất quán mạnh hơn, phải đánh giá replication, topology, concurrency và nhu cầu nghiệp vụ.

## 8. Liên hệ với ứng dụng Java

Các lệnh cqlsh ở trên chỉ có hiệu lực đối với phiên shell đó. Trong **Apache Cassandra Java Driver 4.x**, application đặt consistency và serial consistency trên từng statement, hoặc qua cấu hình/profile mặc định của driver.

Ví dụ dùng statement có điều kiện; giả định `CqlSession session` đã được tạo và kết nối đúng datacenter:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

// Thí dụ minh họa cho cluster có topology phù hợp.
SimpleStatement statement = SimpleStatement.builder(
    "INSERT INTO cqlsh_consistency_lab.device_lease " +
    "(device_id, holder, generation) " +
    "VALUES ('sensor-02', 'worker-A', 1) IF NOT EXISTS")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .build();

ResultSet result = session.execute(statement);
boolean applied = result.wasApplied();
System.out.println("Condition applied: " + applied);
~~~

Trong ví dụ này:

- `setConsistencyLevel` tương ứng với vai trò của `CONSISTENCY` trong cqlsh; `setSerialConsistencyLevel` tương ứng với `SERIAL CONSISTENCY` cho LWT.
- `result.wasApplied()` thể hiện kết quả điều kiện trong LWT; khi `false`, ứng dụng cần kiểm tra dữ liệu hiện tại và quyết định retry hay báo xung đột.
- Trên lab RF = 1, `LOCAL_QUORUM` của datacenter duy nhất vẫn chỉ cần 1 replica; ví dụ driver không ngầm tạo thêm replica.
- Paging của Java Driver dùng fetch size và paging state; hãy quản lý thời điểm lấy page, tránh biến kết quả lớn thành một danh sách trong bộ nhớ.
- Bật tracing bằng cqlsh không bật tracing cho các session Java khác. Để điều tra ứng dụng, dùng tracing/observability của driver và cluster có kiểm soát.

Ứng dụng thực tế nên dùng **prepared statement + bind parameters** thay vì chèn trực tiếp chuỗi dữ liệu vào CQL. Mẫu trên chỉ trình bày cách gắn consistency và serial consistency với statement.

## 9. Lỗi và hiểu nhầm thường gặp

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `CONSISTENCY TWO` trên keyspace RF = 1 gây lỗi | Yêu cầu nhiều replica hơn số replica có thể đáp ứng | Xem `DESCRIBE KEYSPACE` và chọn CL phù hợp; cần RF/topology tương ứng nếu muốn quorum thực sự. |
| Chuyển `SERIAL CONSISTENCY` nhưng `SELECT` thường không đổi | Serial consistency không phải thiết lập thay thế CL của truy vấn thông thường | Dùng `CONSISTENCY` cho đọc/ghi thường; serial cho LWT. |
| `INSERT ... IF NOT EXISTS` trả `[applied] = False` | Row đã tồn tại nên điều kiện không thỏa | Đọc trạng thái hiện tại; phân biệt xung đột nghiệp vụ với lỗi kết nối. |
| `UPDATE ... IF generation = 1` không cập nhật | Giá trị thế hệ hiện tại đã thay đổi | Đọc lại và áp dụng optimistic concurrency theo yêu cầu nghiệp vụ. |
| Kết quả `PAGING 2` chỉ hiện hai row trước tiên | cqlsh đang chờ yêu cầu trang tiếp theo | Yêu cầu trang sau hoặc tăng page size nếu phù hợp. |
| `LIMIT 3` không trả đủ toàn bộ bảng | `LIMIT` giới hạn tổng số row trả về | Bỏ/tăng `LIMIT` chỉ nếu truy vấn phù hợp và phạm vi dữ liệu kiểm soát được. |
| `TRACING ON` làm truy vấn chậm thêm | Có chi phí thu thập/ghi sự kiện trace | Tắt ngay sau khi điều tra; so sánh với metrics khi tracing tắt. |
| Không thấy sự kiện trace mong đợi | Cluster một node, trace chưa ghi đủ, session hết hạn hoặc khác biệt phiên bản | Thử truy vấn đơn giản, kiểm tra phiên bản và log/metrics liên quan. |
| Timeout khi ghi LWT | Đồng thuận hoặc pha ghi không trả đủ phản hồi | Kiểm tra trạng thái trước khi retry, replica và log; tránh tạo thao tác lặp mơ hồ. |

## 10. Bài thực hành kiểm tra hiểu biết

1. Dựng lab RF = 1, chèn 6 sự kiện rồi chạy `CONSISTENCY ONE` và đọc theo đủ partition key. Giải thích vì sao `LOCAL_QUORUM` trên RF = 1 không có ý nghĩa “hai replica”.
2. Giả định một datacenter RF = 3. Tính số replica tối thiểu cho `ONE`, `LOCAL_QUORUM`, `ALL`; dự đoán trạng thái khi một replica không sẵn sàng.
3. Thử `INSERT ... IF NOT EXISTS` hai lần và quan sát `[applied]`. Đổi `generation` bằng `UPDATE ... IF generation = ...` và giải thích kết quả khi điều kiện cũ không còn đúng.
4. Chạy `PAGING 2` để lần lượt đọc 6 row. So sánh với truy vấn `LIMIT 3` và mô tả điều gì khác nhau khi hết trang thứ hai.
5. Bật `TRACING ON` cho một truy vấn có partition key đầy đủ, ghi lại ít nhất ba trường của trace có ý nghĩa; tắt `TRACING OFF` ngay sau đó.
6. Diễn giải vì sao chuyển `CONSISTENCY` trong cqlsh không làm thay đổi mức consistency của một ứng dụng Java đang chạy, và chỉ ra API của Java Driver để cài đặt trên statement.

**Tiêu chí hoàn thành:** phân biệt được regular và serial consistency, dự đoán mức phản hồi trong ví dụ RF = 3, đọc được kết quả `[applied]`, giải thích page size so với `LIMIT`, và biết bật/tắt tracing để điều tra có kiểm soát.

## Tài liệu tham khảo

- [Apache Cassandra — cqlsh: the CQL shell](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): cú pháp và hành vi của `CONSISTENCY`, `SERIAL CONSISTENCY`, `PAGING`, `TRACING`, `SHOW SESSION`.
- [Apache Cassandra — Architecture: Dynamo](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): replication, mức nhất quán và định tuyến request.
- [Apache Cassandra — CQL documentation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): `INSERT`, `UPDATE`, `IF`, primary key và mô hình bảng.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): per-statement consistency, serial consistency, paging và result-set API.
