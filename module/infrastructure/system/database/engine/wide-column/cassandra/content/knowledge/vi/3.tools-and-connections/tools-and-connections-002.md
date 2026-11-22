# DESCRIBE, USE, SOURCE và quản lý ngữ cảnh keyspace

## 1. Vì sao phải quản lý ngữ cảnh keyspace?

Trong Apache Cassandra, **keyspace** là không gian tên chứa bảng và các đối tượng schema, đồng thời khai báo chiến lược nhân bản (replication). Khi làm việc qua **cqlsh**, ta thường cần biết ba điều:

1. **Đang kết nối đến cluster/node nào?** Để tránh thao tác nhầm môi trường.
2. **Bảng và keyspace có cấu trúc gì?** Để viết CQL đúng khóa phân vùng, khóa clustering và kiểu dữ liệu.
3. **Câu lệnh không ghi tên keyspace sẽ tác động vào đâu?** Để tránh đọc hoặc ghi nhầm bảng trùng tên giữa các keyspace.

Ba công cụ quan trọng là:

- **`DESCRIBE`**: xem cấu trúc keyspace, bảng và các đối tượng CQL; rất hữu ích khi khảo sát schema và chẩn đoán lỗi.
- **`USE`**: chọn keyspace mặc định trong **phiên kết nối hiện tại**, để có thể viết tên bảng không kèm tiền tố keyspace.
- **`SOURCE`**: yêu cầu cqlsh đọc và thực thi các câu lệnh trong một file script có thể truy cập được từ máy đang chạy cqlsh.

Đây là một phần của chủ đề **Công cụ và kết nối** trong module Cassandra. Quản lý keyspace đúng giúp thực hành CQL, truy vấn theo partition key, kiểm tra replication và chuẩn bị kết nối từ ứng dụng Java an toàn, dễ kiểm tra.

**Mục tiêu:** sau bài học, bạn có thể mô tả ngữ cảnh của phiên cqlsh, dùng `DESCRIBE` để kiểm tra schema, chuyển keyspace bằng `USE`, chạy file `.cql` bằng `SOURCE`, và tránh lỗi do nhầm keyspace giữa các phiên hoặc script.

## 2. Ba lệnh và phạm vi tác dụng

| Lệnh | Cú pháp tiêu biểu | Tác dụng | Phạm vi |
| --- | --- | --- | --- |
| `DESCRIBE` / `DESC` | `DESCRIBE KEYSPACE demo;` | Hiển thị định nghĩa schema; không sửa dữ liệu. | Đọc thông tin schema mà phiên có thể truy cập. |
| `USE` | `USE demo;` | Chọn keyspace mặc định cho những tên bảng không đủ định danh. | Phiên kết nối hiện tại. |
| `SOURCE` | `SOURCE 'setup.cql';` | Đọc file và thực thi tuần tự các lệnh trong file. | Phiên cqlsh gọi `SOURCE`. |

`USE` là **câu lệnh CQL** về ngữ cảnh keyspace; `SOURCE` là **lệnh của cqlsh**, không phải câu lệnh CQL gửi nguyên dạng từ Java Driver. `DESCRIBE` là giao diện tra cứu schema rất tiện dụng trong cqlsh; khả năng xử lý `DESCRIBE` qua các client hoặc server có thể phụ thuộc phiên bản, vì vậy ứng dụng Java nên dùng API metadata của driver nếu cần khám phá schema.

Một số quy tắc nền tảng:

- Câu lệnh CQL dùng dấu chấm phẩy `;` để kết thúc. Ví dụ ở bài này cũng kết thúc lệnh cqlsh bằng `;` để nhất quán.
- Tên bảng đủ định danh có dạng `keyspace.table`. Tên này chỉ rõ đích, kể cả khi phiên đang `USE` một keyspace khác.
- Chuyển `USE` **không di chuyển dữ liệu**, không đổi replication của keyspace và không tự thay đổi consistency.
- Một phiên mới không kế thừa `USE` của phiên cũ. Với các script chạy độc lập, cần có `USE` phù hợp trong từng script hoặc ghi đầy đủ tên `keyspace.table`.
- Trong Cassandra, bảng thường được thiết kế **theo truy vấn**: `DESCRIBE TABLE` giúp kiểm tra partition key và clustering columns trước khi viết `SELECT`.

## 3. Kiểm tra kết nối và khám phá schema với DESCRIBE

### 3.1. Xác định điểm kết nối

Mở phiên cqlsh (ví dụ Cassandra đang lắng nghe ở `127.0.0.1:9042`):

~~~bash
cqlsh 127.0.0.1 9042
~~~

Tại dấu nhắc `cqlsh>`, thử:

~~~sql
SHOW HOST;
SHOW VERSION;
DESCRIBE KEYSPACES;
~~~

`SHOW HOST` giúp xác nhận kết nối hiện tại, `SHOW VERSION` giúp phát hiện chênh lệch phiên bản và `DESCRIBE KEYSPACES` liệt kê các keyspace có thể nhìn thấy. Một cluster thường có các keyspace nội bộ như `system` hoặc `system_schema`; **không chỉnh sửa các bảng hệ thống để thực hành**.

**Phân biệt node và keyspace:** cqlsh kết nối tới một node làm coordinator. Keyspace là không gian tên logic và cấu hình replication; việc chọn một keyspace không đồng nghĩa với việc chỉ truy cập dữ liệu trên một node cụ thể.

### 3.2. Những dạng DESCRIBE thường dùng

~~~sql
-- Liệt kê các keyspace có thể truy cập.
DESCRIBE KEYSPACES;

-- Khi keyspace đã tồn tại, xem câu lệnh định nghĩa của nó.
DESCRIBE KEYSPACE cql_context_lab;

-- Xem cấu trúc một bảng bằng tên đủ định danh.
DESCRIBE TABLE cql_context_lab.events_by_device;

-- Xem danh sách bảng; cách hiển thị có thể tùy phiên bản cqlsh.
DESCRIBE TABLES;

-- Xem hướng dẫn lệnh từ cqlsh khi cần xác nhận biến thể cú pháp.
HELP DESCRIBE;
~~~

`DESCRIBE KEYSPACE` thường hiển thị cấu hình `replication` và các đối tượng trong keyspace, trong khi `DESCRIBE TABLE` giúp kiểm tra tên cột, kiểu dữ liệu, `PRIMARY KEY`, clustering order và tùy chọn bảng. Kết quả cụ thể phụ thuộc phiên bản Cassandra/cqlsh và quyền truy cập.

**Ví dụ:** với `PRIMARY KEY ((device_id), event_time)`, `device_id` là partition key và `event_time` là clustering column. Truy vấn theo một thiết bị có `WHERE device_id = 'sensor-01'` là mẫu truy vấn tự nhiên; tìm tất cả các bản ghi theo một cột thường khác nếu không có mô hình dữ liệu/index thích hợp.

## 4. Lab: hai keyspace có bảng cùng tên

Ví dụ này sử dụng **hai keyspace thử nghiệm độc lập** để chỉ ra tác động của `USE`. Các ví dụ giả định Cassandra đơn node, có quyền tạo schema. Nếu thực hành trên cluster tổ chức, hãy dùng keyspace/tài khoản lab được cấp phép.

### 4.1. Tạo keyspace và bảng

Tại cqlsh, chạy:

~~~sql
-- Chỉ dùng SimpleStrategy, RF=1 cho lab đơn node.
CREATE KEYSPACE IF NOT EXISTS cql_context_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE KEYSPACE IF NOT EXISTS cql_context_staging
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS cql_context_lab.events_by_device (
  device_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  details text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS cql_context_staging.events_by_device (
  device_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  details text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Ở cả hai bảng, partition key là `device_id`; trong một partition, row được sắp theo `event_time` giảm dần, tiếp theo là `event_id`. Cùng tên bảng **không có nghĩa là cùng bảng**: `cql_context_lab.events_by_device` và `cql_context_staging.events_by_device` là hai đối tượng riêng.

`SimpleStrategy` với RF = 1 chỉ giúp lab chạy đơn giản. Với hệ thống thật, thường cấu hình `NetworkTopologyStrategy` và replication factor theo datacenter thực tế; đây là quyết định vận hành cần cân nhắc khả năng chịu lỗi và mức consistency.

### 4.2. Ghi dữ liệu vào hai bảng riêng biệt

~~~sql
INSERT INTO cql_context_lab.events_by_device
  (device_id, event_time, event_id, event_type, details)
VALUES (
  'sensor-01', '2026-11-21T01:00:00Z',
  11111111-1111-4111-8111-111111111111,
  'temperature', 'lab: 25.1 C'
);

INSERT INTO cql_context_staging.events_by_device
  (device_id, event_time, event_id, event_type, details)
VALUES (
  'sensor-01', '2026-11-21T01:00:00Z',
  22222222-2222-4222-8222-222222222222,
  'temperature', 'staging: 24.8 C'
);
~~~

Hai lệnh `INSERT` dùng tên bảng đầy đủ để xác định đích. Giá trị `device_id` và `event_time` giống nhau, nhưng dữ liệu ở **hai keyspace khác nhau**.

### 4.3. Chuyển ngữ cảnh với USE

~~~sql
USE cql_context_lab;

-- Tên bảng ngắn: cql_context_lab.events_by_device.
SELECT device_id, event_time, details
FROM events_by_device
WHERE device_id = 'sensor-01';

DESCRIBE TABLE events_by_device;

USE cql_context_staging;

-- Cùng câu SELECT, nhưng lần này lấy dữ liệu từ staging.
SELECT device_id, event_time, details
FROM events_by_device
WHERE device_id = 'sensor-01';

-- Bỏ qua ngữ cảnh staging bằng cách chỉ rõ keyspace.
SELECT device_id, event_time, details
FROM cql_context_lab.events_by_device
WHERE device_id = 'sensor-01';
~~~

Kết quả kỳ vọng:

| Câu truy vấn | Keyspace thực sự truy cập | Giá trị `details` |
| --- | --- | --- |
| `SELECT ... FROM events_by_device` ngay sau `USE cql_context_lab` | `cql_context_lab` | `lab: 25.1 C` |
| Cùng truy vấn ngay sau `USE cql_context_staging` | `cql_context_staging` | `staging: 24.8 C` |
| `SELECT ... FROM cql_context_lab.events_by_device` khi đang `USE` staging | `cql_context_lab` | `lab: 25.1 C` |

Trên nhiều phiên bản cqlsh, dấu nhắc đổi từ `cqlsh>` thành dạng `cqlsh:cql_context_lab>` khi `USE` thành công. **Không nên chỉ dựa vào dấu nhắc**: với script, việc ghi `keyspace.table` trong truy vấn quan trọng giúp người đọc biết chắc đích thao tác.

### 4.4. Điều gì xảy ra khi chưa chọn hoặc chọn nhầm keyspace?

Nếu mở một phiên cqlsh mới rồi chạy `SELECT ... FROM events_by_device` trước khi `USE`, cqlsh thường báo lỗi do chưa chỉ định keyspace. Một bảng không đủ định danh chỉ được phân giải khi có keyspace mặc định.

Nếu `USE cql_context_staging` đang có hiệu lực, mọi lệnh `SELECT`, `INSERT`, `UPDATE` hay `DELETE` dùng tên `events_by_device` sẽ hướng vào bảng staging. Đây là nguy cơ lớn hơn lỗi cú pháp: **câu lệnh vẫn có thể chạy thành công nhưng tác động sai đối tượng**.

Để kiểm tra nhanh:

~~~sql
SHOW HOST;
DESCRIBE KEYSPACES;
DESCRIBE TABLE cql_context_lab.events_by_device;
DESCRIBE TABLE cql_context_staging.events_by_device;
~~~

## 5. SOURCE: đưa các câu lệnh vào file .cql

`SOURCE` nhận tên file (hoặc đường dẫn) trên **máy/môi trường đang chạy cqlsh**, đọc nội dung và thực thi trong **phiên cqlsh hiện tại**. Nhờ đó, các lệnh `USE` trong file ảnh hưởng tới những lệnh tiếp theo trong chính phiên đó.

Ví dụ tạo hai file (nội dung hiển thị dưới đây là các file **người học tự tạo**, không yêu cầu thay đổi file ngoài bài học).

### 5.1. File 01_setup.cql

~~~sql
-- Khởi tạo độc lập, không phụ thuộc keyspace mặc định của cqlsh.
CREATE KEYSPACE IF NOT EXISTS cql_context_lab
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE KEYSPACE IF NOT EXISTS cql_context_staging
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS cql_context_lab.events_by_device (
  device_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  details text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CREATE TABLE IF NOT EXISTS cql_context_staging.events_by_device (
  device_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  details text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO cql_context_lab.events_by_device
  (device_id, event_time, event_id, event_type, details)
VALUES ('sensor-01', '2026-11-21T01:00:00Z',
  11111111-1111-4111-8111-111111111111, 'temperature', 'lab: 25.1 C');

INSERT INTO cql_context_staging.events_by_device
  (device_id, event_time, event_id, event_type, details)
VALUES ('sensor-01', '2026-11-21T01:00:00Z',
  22222222-2222-4222-8222-222222222222, 'temperature', 'staging: 24.8 C');
~~~

Các thao tác tạo schema sử dụng `IF NOT EXISTS` để chạy lại không gặp lỗi chỉ vì keyspace/bảng đã tồn tại; tuy nhiên `IF NOT EXISTS` **không cập nhật cấu trúc đã tồn tại** nếu schema hiện tại khác file. `INSERT` trong Cassandra có tính chất upsert theo primary key, nên chạy lại dữ liệu mẫu với cùng primary key không tạo thêm row mới.

### 5.2. File 02_inspect.cql

~~~sql
-- SOURCE dùng chính phiên cqlsh đang gọi nó.
USE cql_context_lab;
DESCRIBE TABLE events_by_device;
SELECT event_time, details
FROM events_by_device
WHERE device_id = 'sensor-01';

USE cql_context_staging;
SELECT event_time, details
FROM events_by_device
WHERE device_id = 'sensor-01';
~~~

Hai lần `SELECT` truy vấn hai bảng khác nhau, dù đều có `FROM events_by_device`. Khi `SOURCE` chạy xong, **keyspace mặc định còn lại trong phiên** là `cql_context_staging`, vì đó là lệnh `USE` cuối cùng.

### 5.3. Thực thi tại dấu nhắc cqlsh

~~~sql
SOURCE '01_setup.cql';
SOURCE '02_inspect.cql';

-- Sau SOURCE, tên không đủ định danh vẫn trỏ vào staging.
DESCRIBE TABLE events_by_device;

-- Chủ động đặt lại ngữ cảnh nếu tiếp tục làm việc ở lab.
USE cql_context_lab;
~~~

Bạn cũng có thể truyền đường dẫn tuyệt đối khi cần, ví dụ `SOURCE '/workspace/scripts/01_setup.cql';` trên môi trường hỗ trợ đường dẫn này. Nếu cqlsh nằm trong container, file phải được mount/copy vào **container**, không chỉ nằm trên máy host. Với đường dẫn tương đối, hãy kiểm tra thư mục làm việc mà **tiến trình cqlsh** sử dụng; không giả định nó là thư mục của server Cassandra.

### 5.4. So sánh SOURCE, -f và -e

Ngoài `SOURCE` trong phiên tương tác, ta có thể khởi chạy cqlsh từ terminal:

~~~bash
# Mỗi lần chạy lệnh dưới đây là một phiên cqlsh độc lập.
cqlsh 127.0.0.1 9042 -f 01_setup.cql
cqlsh 127.0.0.1 9042 -f 02_inspect.cql

# Truy vấn ngắn: chỉ rõ tên keyspace để không phụ thuộc ngữ cảnh.
cqlsh 127.0.0.1 9042 -e "SELECT event_time, details FROM cql_context_lab.events_by_device WHERE device_id = 'sensor-01';"
~~~

| Cách chạy | Phiên thực thi | Hệ quả với `USE` |
| --- | --- | --- |
| Nhập trực tiếp tại `cqlsh>` | Phiên hiện tại | Có hiệu lực cho những lệnh sau trong phiên. |
| `SOURCE 'script.cql';` | Phiên hiện tại | `USE` bên trong file còn hiệu lực sau khi file chạy xong. |
| `cqlsh ... -f script.cql` | Phiên mới, chạy file rồi thoát | `USE` chỉ tồn tại trong phiên chạy file, không truyền cho lệnh `-f` khác. |
| `cqlsh ... -e "CQL"` | Phiên mới, chạy câu lệnh rồi thoát | Dùng `keyspace.table` cho thao tác độc lập để tránh phụ thuộc ngữ cảnh. |

**Lưu ý về lỗi một phần:** `SOURCE` hoặc `-f` không biến toàn bộ file thành một transaction. Nếu một câu lệnh lỗi, các thay đổi đã thành công trước đó không được rollback tự động. Hãy kiểm tra thông báo, kết quả và trạng thái schema/dữ liệu trước khi chạy lại. Không dựa vào `SOURCE` để bảo đảm migration nguyên tử.

## 6. Chiến lược quản lý ngữ cảnh keyspace

### 6.1. Đặt tên đầy đủ khi câu lệnh có tác động quan trọng

Trong script dùng chung cho nhiều môi trường, ưu tiên ghi:

~~~sql
-- Rõ ràng đích đến, bất kể phiên đang USE keyspace nào.
SELECT event_time, details
FROM cql_context_lab.events_by_device
WHERE device_id = 'sensor-01';
~~~

Nhờ đó, code review có thể xác định nơi truy vấn mà không cần lần ngược mọi `USE` phía trên. Điều này đặc biệt hữu ích khi script có nhiều `SOURCE` hoặc được chia thành các file.

### 6.2. Nếu dùng USE, hãy chủ động thiết lập ở đầu file

~~~sql
-- Ví dụ file chỉ phục vụ một keyspace cụ thể.
USE cql_context_lab;

SELECT event_time, details
FROM events_by_device
WHERE device_id = 'sensor-01';
~~~

Thực hành này giúp file chạy độc lập, song vẫn cần kiểm soát môi trường kết nối. Với script tạo keyspace, cần tạo nó trước khi `USE`. Nếu có nguy cơ dùng lại file ở nhiều cluster, **xác thực endpoint và quyền** trước khi thực thi.

### 6.3. Phân biệt keyspace mặc định, replication và consistency

| Khái niệm | Ví dụ | Tác dụng |
| --- | --- | --- |
| Keyspace mặc định | `USE cql_context_lab;` | Chọn cách phân giải tên bảng không đủ định danh trong phiên. |
| Replication của keyspace | `replication_factor: 3` trong định nghĩa keyspace | Xác định số replica theo chiến lược replication; là cấu hình schema. |
| Consistency của thao tác | `CONSISTENCY LOCAL_QUORUM;` trong cqlsh | Đặt yêu cầu phản hồi đọc/ghi của phiên cqlsh, phụ thuộc số replica và datacenter. |
| Partition key | `PRIMARY KEY ((device_id), ...)` | Quyết định partition dữ liệu và đường đi chính của truy vấn. |

Chẳng hạn, dù chạy `USE cql_context_lab`, câu `SELECT` theo `device_id` vẫn được Cassandra định tuyến tới các replica chịu trách nhiệm cho partition đó. `USE` **không** chọn node để lưu dữ liệu và cũng không thay thế việc thiết kế khóa phân vùng hợp lý.

## 7. Liên hệ với ứng dụng Java

Trong cqlsh, `USE` giúp thử câu lệnh nhanh. Với Apache Cassandra Java Driver, nên xác định keyspace bằng cấu hình phiên hoặc dùng tên bảng đầy đủ trong câu CQL. Ví dụ minh họa với DataStax/Apache Cassandra Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.CqlIdentifier;
import java.net.InetSocketAddress;

try (CqlSession session = CqlSession.builder()
    .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
    .withLocalDatacenter("datacenter1") // Thay bằng datacenter thực tế.
    .withKeyspace(CqlIdentifier.fromCql("cql_context_lab"))
    .build()) {

    // Có keyspace mặc định ở cấu hình session.
    var rows = session.execute(
        "SELECT event_time, details " +
        "FROM events_by_device WHERE device_id = 'sensor-01'");
    rows.forEach(row -> System.out.println(row.getString("details")));
}
~~~

`withKeyspace` thuộc cấu hình phiên Java Driver, không phụ thuộc vào bất kỳ `USE` nào từng được chạy trong cqlsh. Tên datacenter phải khớp cấu hình cluster đang kết nối. Với ứng dụng thực tế, dùng **prepared statements** cho tham số truy vấn, và có thể ghi tên `keyspace.table` để làm rõ đích của các lệnh quan trọng. Muốn kiểm tra schema từ Java, ưu tiên metadata API của driver thay vì giả định mọi lệnh tiện ích cqlsh đều có thể gửi qua `session.execute()`.

## 8. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| `No keyspace has been specified` hoặc thông báo tương đương | Truy vấn tên bảng ngắn trước khi `USE` | Chạy `USE <keyspace>;` hoặc đổi thành `keyspace.table`. |
| `Keyspace ... does not exist` | Sai tên, chưa tạo keyspace hoặc kết nối nhầm cluster | `SHOW HOST;`, `DESCRIBE KEYSPACES;`, kiểm tra script tạo schema. |
| `Table ... does not exist` | Bảng không có trong keyspace hiện tại hoặc script tạo chưa chạy | `DESCRIBE TABLE keyspace.table;`, dùng tên đủ định danh. |
| Kết quả đúng cú pháp nhưng sai dữ liệu | `USE` đã chuyển sang keyspace khác, có bảng trùng tên | Kiểm tra mọi `USE` trong phiên/file và thử truy vấn `keyspace.table`. |
| `SOURCE` báo không tìm thấy file | Sai đường dẫn hoặc cqlsh chạy trong container/working directory khác | Chuyển sang đường dẫn tuyệt đối, kiểm tra quyền đọc và vị trí file trong môi trường cqlsh. |
| `SOURCE` chạy một phần rồi lỗi | Lỗi cú pháp, thứ tự schema trước dữ liệu, thiếu quyền hoặc cluster lỗi | Tìm câu lệnh lỗi, xem các câu đã thành công và thử lại từng phần. |
| `DESCRIBE` không thấy đối tượng | Nhầm tên/keyspace, quyền hạn, hoặc khác biệt phiên bản | Dùng tên đầy đủ, kiểm tra `HELP DESCRIBE` và schema hiện có. |
| `Unauthorized` | Tài khoản thiếu quyền xem/sửa schema hoặc dữ liệu | Kiểm tra role và cấp quyền phù hợp cho keyspace/bảng. |
| `Unavailable` / timeout | Replica không đủ hoặc hệ thống gặp vấn đề theo consistency yêu cầu | Kiểm tra cluster, replication factor, consistency và node; không quy lỗi vội cho `USE`. |

Trong môi trường có nhiều cluster (local, staging, production), quy tắc kiểm tra nên theo thứ tự: **endpoint → keyspace → schema → câu lệnh → dữ liệu**. Trước thao tác ghi hoặc thay đổi schema, xác minh đủ cả endpoint và keyspace.

## 9. Bài tập tự thực hành

1. Kết nối cqlsh, chạy `SHOW HOST`, `DESCRIBE KEYSPACES` và giải thích vì sao chọn keyspace không đồng nghĩa chọn node lưu dữ liệu.
2. Tạo hai keyspace và hai bảng cùng tên theo mục 4, rồi dùng `DESCRIBE KEYSPACE` và `DESCRIBE TABLE` để tìm partition key, clustering columns.
3. Chạy hai truy vấn `SELECT ... FROM events_by_device` sau hai lệnh `USE` khác nhau. Giải thích vì sao kết quả đổi dù câu SQL/CQL giữ nguyên.
4. Tạo `01_setup.cql` và `02_inspect.cql`, chạy qua `SOURCE`; kiểm tra keyspace còn hiệu lực sau khi file `02_inspect.cql` kết thúc.
5. Chạy hai file bằng hai lệnh `cqlsh -f` riêng. Giải thích vì sao `USE` từ file đầu không truyền sang phiên chạy file tiếp theo.
6. Sửa truy vấn trong file thứ hai thành `FROM cql_context_lab.events_by_device`; xác nhận nó đọc bảng lab ngay cả khi `USE cql_context_staging` đã chạy.

**Đạt yêu cầu khi:** bạn có thể tự kiểm tra schema bằng `DESCRIBE`, chỉ ra chính xác keyspace của một truy vấn, phân biệt hiệu lực của `USE` qua `SOURCE` và `-f`, và giải thích cách hạn chế thao tác nhầm keyspace trong cqlsh cũng như ứng dụng Java.

## Tài liệu tham khảo

- [Apache Cassandra — cqlsh: the CQL shell](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): lệnh cqlsh, chạy file và kiểm tra schema.
- [Apache Cassandra — Cassandra Query Language (CQL)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): schema, keyspace, khóa chính và câu lệnh CQL.
- [Apache Cassandra Java Driver](https://docs.datastax.com/en/developer/java-driver/4.17/): cấu hình phiên, keyspace và truy vấn từ Java.
