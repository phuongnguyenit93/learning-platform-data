# Sử dụng cqlsh để chạy câu lệnh và script

## 1. Mục tiêu và vai trò của cqlsh

**cqlsh (Cassandra Query Language shell)** là công cụ dòng lệnh đi kèm Apache Cassandra, dùng để kết nối tới một node qua giao thức native (thường là cổng 9042), gửi câu lệnh CQL và xem kết quả. Đây là công cụ thuận tiện để học CQL, kiểm tra schema, thử truy vấn, chạy file khởi tạo và điều tra lỗi kết nối. Ứng dụng Java trong môi trường thực tế thường dùng **Apache Cassandra Java Driver** để quản lý phiên kết nối và thực thi truy vấn; cqlsh chủ yếu phục vụ thao tác thủ công và script quản trị đơn giản.

Sau bài này, người học có thể:

- Kết nối bằng cqlsh và phân biệt **câu lệnh CQL** với **lệnh riêng của cqlsh**.
- Tạo keyspace/bảng, ghi và đọc dữ liệu bằng truy vấn phù hợp với **partition key**.
- Chạy một lệnh bằng tùy chọn `-e`, chạy file bằng `-f` hoặc `SOURCE`.
- Điều chỉnh consistency của phiên, xuất/nhập CSV và xử lý các lỗi phổ biến khi chạy script.

**Ranh giới cần nhớ:** cqlsh kết nối tới một node đóng vai trò coordinator; việc dữ liệu được phân phối và nhân bản tới các node khác do Cassandra xử lý. Chạy được lệnh qua một node không có nghĩa là dữ liệu chỉ nằm trên node đó.

## 2. Chuẩn bị và kết nối

Điều kiện thực hành:

1. Đã có Cassandra đang hoạt động, biết địa chỉ node và cổng native transport (mặc định **9042**).
2. Có chương trình `cqlsh`, ưu tiên bản đi kèm cùng phiên bản Cassandra đang dùng để tránh lỗi tương thích.
3. Có tài khoản và thiết lập TLS nếu cluster bật xác thực hoặc mã hóa kết nối.
4. Dùng keyspace thử nghiệm riêng; không chạy lệnh thay đổi schema trên hệ thống sản xuất khi chưa biết tác động.

Mở terminal tại máy đã cài cqlsh:

~~~bash
# Kết nối tới node trên máy hiện tại.
cqlsh

# Chỉ rõ host và cổng (thay tên host theo môi trường).
cqlsh db.example.internal 9042

# Ví dụ khi server yêu cầu TLS và tên tài khoản.
cqlsh db.example.internal 9042 --ssl -u student

# Xem các tùy chọn mà phiên bản cqlsh của bạn hỗ trợ.
cqlsh --help
~~~

Nếu cqlsh chạy trong container, file script được đọc từ **hệ thống file của môi trường chạy cqlsh**. Chẳng hạn, chạy cqlsh trong container thì phải đặt file tại đường dẫn container có thể đọc, không chỉ ở máy host. Tùy môi trường có thể mở phiên bằng `docker exec -it <ten-container> cqlsh`.

Đối với cluster có xác thực, cấu hình chứng chỉ và thông tin đăng nhập theo chính sách của hệ thống. Tránh ghi mật khẩu trực tiếp vào tham số `-p` của shell vì có thể lộ qua lịch sử hoặc danh sách tiến trình. cqlsh hỗ trợ cấu hình `cqlshrc` và file credentials có phân quyền phù hợp; `--ssl` không thay thế yêu cầu kiểm tra chứng chỉ đúng cách.

Khi hiện dấu nhắc `cqlsh>`, thử:

~~~sql
SHOW VERSION;
SHOW HOST;
DESCRIBE KEYSPACES;
HELP;
~~~

| Lệnh | Ý nghĩa |
| --- | --- |
| `SHOW VERSION` | Xem phiên bản cqlsh, Cassandra, CQL và giao thức đang sử dụng. |
| `SHOW HOST` | Xác nhận node và cluster mà phiên đang kết nối. |
| `DESCRIBE KEYSPACES` | Liệt kê các keyspace nhìn thấy từ phiên. |
| `DESCRIBE KEYSPACE <ten>` | Hiện định nghĩa schema của keyspace. |
| `HELP` hoặc `HELP <chu-de>` | Tra cú pháp và các lệnh hỗ trợ. |
| `EXIT` hoặc `QUIT` | Đóng phiên cqlsh. |

**Lưu ý về cú pháp:** CQL dùng dấu chấm phẩy (`;`) để kết thúc câu lệnh; lệnh của cqlsh như `SOURCE`, `SHOW` hay `CONSISTENCY` là tiện ích của shell, không phải câu lệnh CQL để gửi nguyên dạng từ Java Driver. Chuỗi CQL đặt trong dấu nháy đơn; muốn ghi nháy đơn bên trong chuỗi, nhân đôi nó (ví dụ `'I''m ready'`). Tên bảng/cột thông thường không cần đặt trong nháy kép; tránh tự ý dùng tên có chữ hoa phân biệt kiểu chữ.

## 3. Thực hành CQL: thiết kế bảng theo truy vấn

Giả sử hệ thống nhận sự kiện của thiết bị và cần tra **các sự kiện của một thiết bị trong một ngày, mới nhất trước**. Với Cassandra, ta thiết kế bảng theo truy vấn này thay vì bắt đầu từ mô hình quan hệ chuẩn hóa.

Tại dấu nhắc cqlsh, chạy:

~~~sql
-- Keyspace một node cho phòng lab, KHÔNG dùng cấu hình này để mô phỏng production.
CREATE KEYSPACE IF NOT EXISTS cqlsh_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE cqlsh_lab;

CREATE TABLE IF NOT EXISTS events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  event_note text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

DESCRIBE TABLE cqlsh_lab.events_by_device_day;
~~~

Trong khóa chính trên:

- `(device_id, event_day)` là **composite partition key**: những sự kiện cùng thiết bị và cùng ngày thuộc cùng partition logic. Tách theo ngày giúp giới hạn kích thước partition theo luồng sự kiện.
- `event_time` và `event_id` là **clustering columns**: quyết định thứ tự các row bên trong partition và giúp phân biệt các sự kiện cùng thời điểm.
- `CLUSTERING ORDER BY (event_time DESC, event_id ASC)` hỗ trợ đọc dữ liệu mới nhất trước mà không cần sắp xếp lại ở phía client.

`SimpleStrategy` với replication factor bằng 1 chỉ nhằm giúp ví dụ chạy trên môi trường đơn node. Với cluster nhiều node/đa datacenter, nên dùng `NetworkTopologyStrategy` và số replica phù hợp **tên datacenter thực tế**; việc chọn chiến lược và RF là quyết định kiến trúc riêng, không nên sao chép cấu hình lab.

Chèn hai bản ghi:

~~~sql
INSERT INTO cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
VALUES
  ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
   11111111-1111-4111-8111-111111111111, 'temperature', '25.1 C');

INSERT INTO cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
VALUES
  ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
   22222222-2222-4222-8222-222222222222, 'temperature', '25.3 C');

SELECT event_time, event_id, event_type, event_note
FROM cqlsh_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

Kỳ vọng: kết quả có **2 row**, sự kiện lúc `01:05:00Z` đứng trước sự kiện `01:00:00Z`. Truy vấn chỉ định đầy đủ partition key nên coordinator biết partition cần đọc. Ngược lại, truy vấn chỉ lọc `event_type = 'temperature'` không khớp mô hình truy vấn của bảng và có thể bị từ chối do cần quét/lọc dữ liệu rộng. Không nên thêm `ALLOW FILTERING` chỉ để bỏ qua vấn đề thiết kế; hãy thiết kế một bảng theo kiểu truy vấn khác khi cần.

Trong Cassandra, `INSERT` là thao tác **upsert**: ghi cùng primary key có thể cập nhật dữ liệu đang có. Vì vậy, chạy lại script seed với cùng key không tạo thêm bản ghi mới, nhưng cũng không nên coi mọi script ghi dữ liệu là an toàn để chạy lại (đặc biệt khi dùng TTL, timestamp ghi, `UPDATE` hoặc `DELETE`).

## 4. Ba cách chạy câu lệnh và script

### 4.1. Tương tác trực tiếp

Nhập từng câu CQL ở dấu nhắc `cqlsh>`; một câu lệnh có thể trải nhiều dòng và kết thúc bằng `;`. Phù hợp khi khám phá schema hoặc thử truy vấn trước khi lưu thành file.

~~~sql
USE cqlsh_lab;
SELECT event_time, event_note
FROM events_by_device_day
WHERE device_id = 'sensor-01' AND event_day = '2026-11-21';
~~~

### 4.2. Chạy một câu và thoát bằng `-e`

`-e` hữu ích cho kiểm tra đơn giản trong terminal hay automation nhẹ:

~~~bash
cqlsh 127.0.0.1 9042 -e "SHOW VERSION;"

cqlsh 127.0.0.1 9042 -e "SELECT event_time, event_note FROM cqlsh_lab.events_by_device_day WHERE device_id = 'sensor-01' AND event_day = '2026-11-21' LIMIT 10;"
~~~

Chuỗi truyền cho `-e` chịu quy tắc dấu nháy của shell đang dùng. Câu CQL dài hoặc gồm nhiều thao tác nên để trong file `.cql` để dễ kiểm tra, lưu phiên bản và chạy lại.

### 4.3. Chạy file `.cql` bằng `-f` hoặc `SOURCE`

Ví dụ chia thành hai file có **nội dung minh họa** như sau.

File `01_schema.cql`:

~~~sql
-- Tạo cấu trúc phục vụ truy vấn sự kiện theo thiết bị/ngày.
CREATE KEYSPACE IF NOT EXISTS cqlsh_lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS cqlsh_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  event_note text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

File `02_seed.cql`:

~~~sql
-- Luôn ghi rõ keyspace để không phụ thuộc lệnh USE ở phiên khác.
INSERT INTO cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
VALUES
  ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
   11111111-1111-4111-8111-111111111111, 'temperature', '25.1 C');

INSERT INTO cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
VALUES
  ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
   22222222-2222-4222-8222-222222222222, 'temperature', '25.3 C');
~~~

Từ terminal, đứng tại thư mục có hai file:

~~~bash
cqlsh 127.0.0.1 9042 -f 01_schema.cql
cqlsh 127.0.0.1 9042 -f 02_seed.cql
~~~

Hoặc từ phiên cqlsh đang mở:

~~~sql
SOURCE '01_schema.cql';
SOURCE '02_seed.cql';
~~~

| Cách thực thi | Nên dùng khi | Điều cần nhớ |
| --- | --- | --- |
| Nhập tại `cqlsh>` | Thử từng câu, kiểm tra kết quả ngay | Phải giữ đúng ngữ cảnh keyspace của phiên. |
| `-e "..." ` | Một truy vấn/lệnh ngắn | Cẩn thận quy tắc escape của terminal. |
| `-f path/file.cql` | Khởi tạo schema, seed dữ liệu, thao tác lặp lại | cqlsh chạy các câu trong file rồi thoát. |
| `SOURCE 'path/file.cql'` | Chạy file ngay trong phiên tương tác | Đường dẫn phải truy cập được từ nơi cqlsh đang chạy. |

**Thứ tự có ý nghĩa:** cần tạo keyspace và bảng trước khi chèn dữ liệu. Hai lệnh `cqlsh -f` ở ví dụ chạy trong **hai phiên độc lập**, nên file seed dùng tên bảng đầy đủ. Một file script gồm nhiều lệnh **không phải transaction toàn cục**: nếu lệnh sau lỗi, những lệnh trước có thể đã hoàn tất và không tự rollback. Khi đưa vào quy trình triển khai, hãy quản lý version schema, log kết quả và kiểm tra dữ liệu sau khi chạy; `IF NOT EXISTS` không tự sửa schema cũ nếu định nghĩa đã thay đổi.

## 5. Các lệnh cqlsh hỗ trợ kiểm tra và chẩn đoán

Những lệnh dưới đây chạy trong cqlsh:

~~~sql
-- Quan sát cấu trúc đang tồn tại.
DESCRIBE KEYSPACE cqlsh_lab;
DESCRIBE TABLE cqlsh_lab.events_by_device_day;

-- Mỗi trang tối đa 20 row; giữ phân trang khi xem dữ liệu lớn.
PAGING 20;

-- Hiện từng row theo dạng dọc nếu nhiều cột hoặc giá trị dài.
EXPAND ON;
SELECT event_time, event_note
FROM cqlsh_lab.events_by_device_day
WHERE device_id = 'sensor-01' AND event_day = '2026-11-21';
EXPAND OFF;

-- Bật tracing tạm thời để xem đường đi thực thi của truy vấn.
TRACING ON;
SELECT event_time, event_note
FROM cqlsh_lab.events_by_device_day
WHERE device_id = 'sensor-01' AND event_day = '2026-11-21'
LIMIT 10;
TRACING OFF;
~~~

`TRACING` chỉ nên bật khi cần điều tra vì có chi phí xử lý và lưu thông tin truy vết. `PAGING` giúp cqlsh không tải và in toàn bộ kết quả trong một lần, nhưng nó **không biến một truy vấn quét rộng thành truy vấn tốt**.

### 5.1. Điều chỉnh consistency cho phiên

~~~sql
-- Phù hợp với lab chỉ có một replica.
CONSISTENCY ONE;

-- Ví dụ khi chạy trên cluster phù hợp, có đủ replica trong datacenter.
CONSISTENCY LOCAL_QUORUM;

-- Cho cập nhật có điều kiện IF (lightweight transaction) khi cần.
SERIAL CONSISTENCY LOCAL_SERIAL;
~~~

`CONSISTENCY` thay đổi mức nhất quán cho những thao tác tiếp theo **trong phiên cqlsh hiện tại**, không thay đổi replication factor của keyspace và không tự tác động tới mọi Java client. Ở mức `LOCAL_QUORUM`, với RF = 3 trong một datacenter thì thông thường cần phản hồi từ ít nhất **2 replica** của datacenter đó. Trên cluster lab RF = 1, `ONE` là đủ để thực hành; tăng consistency không thể tạo thêm replica còn thiếu. `SERIAL CONSISTENCY` chỉ liên quan tới pha điều phối của thao tác ghi có điều kiện `IF`.

### 5.2. Lưu kết quả và xuất/nhập CSV

~~~sql
-- Chỉ ghi phần kết quả truy vấn vào file ở phía máy chạy cqlsh.
CAPTURE 'query-output.txt';
SELECT event_time, event_note
FROM cqlsh_lab.events_by_device_day
WHERE device_id = 'sensor-01' AND event_day = '2026-11-21';
CAPTURE OFF;

-- Xuất dữ liệu bảng sang CSV, có hàng tiêu đề.
COPY cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
TO 'events.csv' WITH HEADER = TRUE;

-- Nhập CSV vào bảng đã tồn tại với schema tương thích.
COPY cqlsh_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, event_note)
FROM 'events.csv' WITH HEADER = TRUE;
~~~

`CAPTURE` ghi **output của truy vấn**, không phải mọi thông báo lỗi hay output của lệnh đặc biệt. `COPY TO` đọc dữ liệu toàn bảng và có thể tốn tài nguyên; `COPY FROM` ghi dữ liệu từ CSV vào bảng hiện có. Hãy kiểm tra thứ tự cột, kiểu dữ liệu, giá trị rỗng, định dạng ngày giờ và file lỗi khi nhập. `COPY` phù hợp dữ liệu nhỏ và mục đích thử nghiệm; với lượng dữ liệu lớn nên cân nhắc công cụ bulk chuyên dụng (ví dụ DSBulk) và quy trình backup/restore riêng. Xuất CSV không thay thế bản sao lưu đầy đủ của cluster.

## 6. Lỗi thường gặp khi chạy cqlsh và script

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| Không kết nối được tới host/cổng 9042 | Node chưa sẵn sàng, sai host/port, DNS hoặc firewall, cấu hình native transport | Kiểm tra dịch vụ Cassandra, endpoint và khả năng kết nối mạng từ máy chạy cqlsh. |
| Lỗi xác thực, không đủ quyền | Sai thông tin đăng nhập hoặc tài khoản chưa được cấp quyền CQL | Kiểm tra cấu hình auth, role và quyền truy cập keyspace/bảng. |
| Lỗi TLS/SSL handshake | Server yêu cầu TLS, cấu hình tin cậy CA/chứng chỉ không khớp | Dùng đúng chế độ `--ssl` và cấu hình chứng chỉ tương ứng với cluster. |
| `SyntaxException` | Thiếu `;`, sai nháy đơn, sai tên cột hoặc cú pháp CQL | Chạy lại từng câu; xem `HELP`, `DESCRIBE TABLE` và kiểm tra chuỗi literal. |
| Bảng/keyspace không tồn tại | Chạy seed trước schema, nhầm môi trường, quên `USE` | Xem `SHOW HOST` và `DESCRIBE`; dùng tên bảng `keyspace.table`. |
| Truy vấn không thể thực hiện nếu thiếu lọc bổ sung | `WHERE` không bám partition key/clustering columns | Điều chỉnh mẫu truy vấn và thiết kế bảng theo truy vấn cần phục vụ. |
| `Unavailable`, `ReadTimeout`, `WriteTimeout` | Không đủ replica phản hồi theo consistency hoặc node/mạng đang quá tải | Kiểm tra trạng thái replica, RF, consistency và nguyên nhân hệ thống; tránh chỉ tăng timeout. |
| `SOURCE`/`-f` không tìm thấy file | File không nằm trong môi trường/đường dẫn mà cqlsh đọc được | Xác nhận working directory, quyền đọc và đường dẫn trên host/container thực thi. |
| Lỗi khi import CSV | Sai header, thứ tự cột, kiểu dữ liệu, timestamp/UUID | Đối chiếu schema, xem file lỗi import và thử ít dòng trước. |

Nếu script chạy được một phần rồi lỗi, hãy xác định **câu lệnh nào đã thành công** trước khi chạy lại. Đối chiếu `DESCRIBE`, `SELECT` theo partition key và thông báo của cqlsh; không giả định mọi thay đổi sẽ được hoàn tác.

## 7. Bài tự thực hành

1. Kết nối và ghi lại kết quả `SHOW HOST` cùng `SHOW VERSION`. Giải thích node nhận kết nối có đồng nghĩa node lưu toàn bộ dữ liệu hay không.
2. Tạo hai file `01_schema.cql` và `02_seed.cql` theo nội dung trên, chạy bằng `-f`, rồi kiểm chứng kết quả bằng `-e`.
3. Chạy lại `01_schema.cql` và giải thích tác dụng của `IF NOT EXISTS`. Chạy lại seed và kiểm tra vì sao số row không tăng nếu primary key không thay đổi.
4. Trong cqlsh, chạy cùng truy vấn với `PAGING 20`, `EXPAND ON`; dùng `TRACING ON` tạm thời và tắt ngay sau khi quan sát.
5. Xuất bảng sang CSV, xem tiêu đề/cột; chỉ thử import vào môi trường lab có bảng tương thích. Giải thích vì sao `COPY TO` không phải là backup cluster.

**Tiêu chí hoàn thành:** đọc/ghi được hai sự kiện đúng partition, thực thi script bằng cả `-f` và `SOURCE`, phân biệt được lệnh cqlsh với CQL, hiểu tác động của consistency và có thể nêu nguyên nhân phổ biến khi script thất bại.

## Tài liệu tham khảo

- [Apache Cassandra — cqlsh: the CQL shell](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): tùy chọn kết nối, `SOURCE`, `CONSISTENCY`, `COPY`, `CAPTURE`, `PAGING` và `TRACING`.
- [Apache Cassandra — Cassandra Query Language (CQL)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): cú pháp schema, kiểu dữ liệu, khóa chính và truy vấn.
