# Ghi lại câu lệnh, cấu hình phiên và kết quả để tái hiện thí nghiệm

## 1. Tái hiện thí nghiệm Cassandra nghĩa là gì?

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**. Một câu `SELECT` hay `INSERT` chạy qua `cqlsh` hoặc Java Driver không chỉ phụ thuộc vào câu CQL: kết quả còn liên quan **schema, partition key, dữ liệu đầu vào, replication factor (RF), consistency level (CL), coordinator, phiên bản Cassandra và trạng thái replica**. Vì vậy, ghi mỗi câu lệnh vào một đoạn chat không đủ để người khác tái hiện một thí nghiệm.

Trong chương **Công cụ và kết nối** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, kỹ năng này tạo nền tảng cho các bài thực hành CQL, chọn partition key, đánh giá mức nhất quán đọc/ghi, quan sát compaction/repair, xử lý timeout và kết nối ứng dụng Java.

Một thí nghiệm được xem là **có thể tái hiện** khi người khác nhận được thông tin cần thiết để:

1. Chuẩn bị **môi trường và trạng thái dữ liệu ban đầu** tương đương.
2. Chạy **đúng các thao tác theo đúng thứ tự**, với cấu hình phiên đã biết.
3. Thu được **kết quả dự kiến** hoặc biết rõ điều kiện chấp nhận sai khác.
4. Phân biệt sai khác do **lỗi thí nghiệm** với biến động bình thường của hệ phân tán.

Không phải mọi con số sẽ giống hệt sau khi chạy lại. Thời gian xử lý, coordinator được chọn, số SSTable, trạng thái cache, UUID của tracing session và tải nền có thể thay đổi. Điều cần tái hiện là **đầu vào, ngữ nghĩa và điều kiện đo**, còn các đại lượng biến động phải được mô tả cách đo và cách so sánh.

**Mục tiêu của bài:**

- Lưu lại script CQL, cấu hình cqlsh và phiên bản client/server/native protocol.
- Sử dụng `SHOW VERSION`, `SHOW HOST`, `CONSISTENCY`, `SERIAL CONSISTENCY`, `PAGING`, `TRACING`, `SOURCE`, `CAPTURE` và các tùy chọn `-f`/`-e` một cách có chủ đích.
- Thu thập đầu ra **cả thành công lẫn lỗi**, không nhầm `CAPTURE` với transcript đầy đủ.
- Dựng lab có **primary key cố định, timestamp rõ ràng, kết quả kỳ vọng có thể kiểm chứng**.
- Lưu manifest/run log/checksum, lọc thông tin nhạy cảm và hướng dẫn người khác chạy lại.
- Đối chiếu kết quả từ cqlsh với cách ghi nhận thí nghiệm trong Java Driver.

## 2. Các thành phần bắt buộc của một hồ sơ thí nghiệm

Một bản ghi tái hiện tốt gồm các nhóm sau:

| Nhóm | Thông tin cần ghi | Vì sao quan trọng? |
| --- | --- | --- |
| **Mục tiêu/giả thuyết** | Ví dụ “SELECT theo partition key trả 2 row, sắp theo clustering order DESC” | Biết đang kiểm tra điều gì, không chỉ chạy thử tùy ý. |
| **Môi trường** | Phiên bản Cassandra, cqlsh, native protocol, OS/container image, thời gian UTC | Giúp giải thích khác biệt cú pháp, giao thức và hành vi. |
| **Topology** | Cluster/DC, danh sách node phù hợp, RF của keyspace, trạng thái replica | Phân biệt sai khác do cluster một node hoặc nhiều node. |
| **Schema ban đầu** | `CREATE KEYSPACE`, `CREATE TABLE`, partition/clustering key, table options | Cùng một query trên bảng khác schema có thể cho hành vi khác. |
| **Dữ liệu đầu vào** | Giá trị, UUID, thời điểm, cách tạo fixture và cách reset lab | Tránh dữ liệu thừa của lần chạy trước. |
| **Phiên cqlsh** | Contact point, `USE`, `CONSISTENCY`, `SERIAL CONSISTENCY`, `PAGING`, `TRACING`, timezone, timeout | Không phụ thuộc mặc định ẩn của shell. |
| **Thao tác** | Script nguyên văn, thứ tự thực hiện, tham số, phiên bản tool | Cho phép chạy lại chính xác các bước. |
| **Quan sát** | stdout, stderr/lỗi, exit status, result, trace ID nếu bật tracing | Đủ để phân tích khi kỳ vọng không đạt. |
| **Đánh giá** | Expected vs actual, kiểm tra số row/giá trị, kết luận, giới hạn | Phân biệt “script chạy xong” với “thí nghiệm đạt”. |
| **Toàn vẹn và bảo mật** | Hash file, người/chạy máy, quyền truy cập artifact, bí mật được che | Tránh nhầm file và rò rỉ thông tin đăng nhập/dữ liệu. |

**Nguyên tắc:** một kết quả `SELECT` đúng không chứng minh cấu hình replication, trạng thái peer hay consistency đã đúng. Muốn khẳng định “đọc ở `LOCAL_QUORUM`” thì phải ghi **RF, DC và CL** chứ không chỉ chụp vài dòng output.

### 2.1. Mô hình đầu vào → thực thi → bằng chứng

~~~mermaid
flowchart TD
    ENV["Environment: version, topology, auth/TLS"] --> RUN["Phiên cqlsh hoặc Java"]
    SCHEMA["Schema + dữ liệu fixture"] --> RUN
    SESSION["CL, serial CL, paging, tracing, timeout"] --> RUN
    SCRIPT["Scripts theo thứ tự, hash đầu vào"] --> RUN
    RUN --> OUTPUT["stdout/stderr, kết quả CQL, trace"]
    OUTPUT --> CHECK["Đối chiếu expected/actual"]
    ENV --> MANIFEST["Run manifest + thời gian + checksums"]
    SCRIPT --> MANIFEST
    CHECK --> MANIFEST
~~~

Khi chia sẻ thí nghiệm, nên gửi **script và manifest** cùng kết quả đã lọc thông tin nhạy cảm. Không chỉ gửi ảnh chụp màn hình thiếu thời điểm, phiên bản và câu CQL đã chạy.

## 3. Tổ chức thư mục thí nghiệm mà không trộn đầu vào và kết quả

Một cấu trúc tham khảo:

~~~text
cassandra-experiment/
  README.md                # mục tiêu, yêu cầu, cách chạy và expected
  input/
    00-schema-and-seed.cql # tạo schema và dữ liệu fixture
    10-checks.cql          # cấu hình phiên và truy vấn kiểm tra
  runs/
    run-20261121T020000Z/
      manifest.yml         # phiên bản/topology/config (không có secrets)
      setup.log            # stdout+stderr khi chuẩn bị
      checks.log           # stdout+stderr khi kiểm tra
      query-results.txt    # kết quả do CAPTURE tạo (nếu dùng)
      expected-vs-actual.md
      checksums.sha256
~~~

Đây là **sơ đồ thư mục ví dụ**, không phải tệp được tạo tự động bởi Cassandra. Các file `input/*.cql` nên được review/version control; `runs/*` có thể lưu vào nơi lưu artifact có quyền truy cập giới hạn. Nếu kết quả chứa dữ liệu khách hàng, token, IP nội bộ hoặc username, cần **ẩn danh hoặc kiểm soát truy cập** trước khi chia sẻ.

Không ghi mật khẩu thật, private key, nội dung secret manager hay bản sao đầy đủ `credentials`/`cqlshrc` chứa bí mật vào hồ sơ. Với TLS, thường chỉ cần ghi **“TLS enabled, CA profile X”** và mã tham chiếu cấu hình được quản lý riêng.

### 3.1. Vì sao mỗi lần chạy cần một thư mục riêng?

- `CAPTURE` **ghi nối tiếp** vào file được chỉ định; tái sử dụng file cũ có thể trộn kết quả lần trước với lần mới.
- Log/trace và timestamp thay đổi theo lần chạy.
- So sánh lần chạy A/B dễ hơn nếu mỗi kết quả có manifest, checksum và điều kiện đo riêng.
- Để điều tra sự cố, cần biết output nào ứng với **script hash và cấu hình phiên nào**.

Nếu chọn chạy lại cùng tệp output, phải làm rõ thao tác **tạo file mới, lưu archive hoặc xóa output lab cũ** trước khi chạy. Không xóa dữ liệu/nhật ký production để dọn một bài thí nghiệm.

## 4. Ghi lại môi trường và phiên bản cqlsh

### 4.1. Thông tin từ phiên cqlsh

Mở shell trong lab:

~~~bash
# Mở cqlsh đến node lab trên native port mặc định.
cqlsh 127.0.0.1 9042
~~~

Trong cqlsh:

~~~sql
-- Lệnh riêng của cqlsh, không phải truy vấn CQL ứng dụng Java.
SHOW VERSION;
SHOW HOST;

SELECT cluster_name, data_center, rack, release_version
FROM system.local;
~~~

`SHOW VERSION` ghi **phiên bản cqlsh, Cassandra, CQL spec và native protocol được kết nối**. `SHOW HOST` chỉ rõ node/port mà **phiên cqlsh này** đang kết nối; kết quả không phải danh sách toàn cluster.

Trong trường hợp cqlsh hoặc server khác phiên bản, một số special commands và tham số có thể không tương thích. Theo tài liệu chính thức, cqlsh thường chỉ được **bảo đảm tương thích** với bản Cassandra đi kèm; vì thế nên ghi cả hai version thay vì chỉ “Cassandra 4.x”.

### 4.2. Metadata schema và topology

~~~sql
DESCRIBE KEYSPACES;
DESCRIBE KEYSPACE repro_lab;

-- Chạy sau khi đã tạo repro_lab ở phần 6.
SELECT keyspace_name, durable_writes, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'repro_lab';

SELECT cluster_name, data_center, rack, release_version, schema_version
FROM system.local;
~~~

`DESCRIBE KEYSPACE` trả DDL mô tả schema; `system_schema.keyspaces` cho thấy replication map, quan trọng khi muốn giải thích kết quả của `ONE`, `QUORUM` hay `LOCAL_QUORUM`. Nếu chạy các câu này **trước** bước tạo lab thì cần bỏ câu hỏi đến `repro_lab` hoặc ghi rõ `keyspace chưa tồn tại`; đừng giấu bước tạo schema.

Từ máy quản trị có quyền và có đường JMX, bổ sung:

~~~bash
# Thực hiện bằng nodetool trên node được cấp quyền, không phải bên trong cqlsh.
nodetool status
nodetool describecluster
~~~

`nodetool status` là **ảnh chụp trạng thái cluster** từ góc nhìn node được hỏi; nó không bảo đảm mọi replica đều đủ khả năng phục vụ request trong suốt thí nghiệm. Ghi thời điểm lấy snapshot, đặc biệt khi đang có bootstrap, repair hay thay đổi topology.

### 4.3. Những thông số môi trường dễ bị bỏ sót

| Yếu tố | Cách ghi/đối chiếu | Hệ quả nếu quên |
| --- | --- | --- |
| Datacenter và RF | `system.local.data_center` + `system_schema.keyspaces.replication` | `LOCAL_QUORUM` có thể có số replica yêu cầu khác nhau. |
| Native endpoint | `SHOW HOST`, DNS/IP/port và TLS bật/tắt | Có thể đã kết nối nhầm cluster hoặc một node khác. |
| Timezone/locale | Cấu hình cqlshrc, thời điểm UTC, chuẩn timestamp trong input | String timestamp và kết quả hiển thị khác nhau. |
| Phiên bản driver/cqlsh | `SHOW VERSION`, dependency Java Driver | Khác biệt native protocol, serialization, paging. |
| Trạng thái schema | `DESCRIBE TABLE` + schema version/DDL hash | Query cũ có thể không tương thích schema mới. |
| Cache/compaction/repair | Metrics/log/snapshot có ghi thời điểm | Có thể làm latency biến động dù dữ liệu logic giống nhau. |
| Auth/TLS | Mode bảo mật và profile cấu hình **không lộ secret** | Lỗi handshake/auth không được giải thích chỉ bằng câu CQL. |

Đối với phân tích hiệu năng, bổ sung cấu hình tài nguyên/CPU/RAM/disk, số request đồng thời, page size, request timeout, tỷ lệ cache warm/cold và trạng thái background compaction; **một lần chạy đơn lẻ không đủ để kết luận benchmark**.

## 5. Ghi rõ cấu hình phiên: không phụ thuộc mặc định

Các lệnh cqlsh sau thay đổi **phiên đang chạy**:

~~~sql
-- Đặt session context một cách tường minh.
USE repro_lab;
CONSISTENCY ONE;
SERIAL CONSISTENCY SERIAL;
PAGING OFF;
TRACING OFF;
~~~

Ý nghĩa:

| Lệnh | Dùng để điều khiển | Phạm vi và lưu ý |
| --- | --- | --- |
| `USE repro_lab` | Keyspace mặc định khi tên bảng không có prefix | Chỉ trong session; dùng `repro_lab.table` để tránh lệ thuộc ngữ cảnh. |
| `CONSISTENCY ONE` | CL cho request cqlsh tiếp theo | Không sửa default của Java Driver hoặc session cqlsh khác. |
| `SERIAL CONSISTENCY SERIAL` | Serial CL cho câu ghi có `IF` (LWT/Paxos) | Không thay regular CL; không ảnh hưởng ý nghĩa của SELECT thường. |
| `PAGING OFF` | Không dùng trải nghiệm phân trang tương tác cho truy vấn nhỏ | Tránh prompt giữa lúc đọc một result nhỏ; không nên tắt paging với tập lớn. |
| `TRACING OFF` | Không in tracing mỗi query | Tracing khi bật có overhead, làm thay đổi đặc điểm đo latency. |

Với RF = 1 của lab dưới đây, `CONSISTENCY ONE` có ý nghĩa và thao tác đọc/ghi không cần nhiều replica. **Không thay CL production để so sánh chỉ nhằm “hết lỗi”** khi cluster không đạt quorum.

### 5.1. Ghi lại những gì CLI/cqlshrc quyết định

Ví dụ các tùy chọn có thể ảnh hưởng một lần chạy:

~~~bash
# Xem các tùy chọn mà bản cqlsh hiện tại hỗ trợ.
cqlsh --help
cqlsh --version

# Ví dụ gọi script và timeout tường minh trên phiên bản hỗ trợ.
cqlsh 127.0.0.1 9042 --no-color \
  --connect-timeout=5 \
  --request-timeout=10 \
  -f input/10-checks.cql
~~~

Các con số `5` và `10` chỉ là lựa chọn **minh họa**, không phải khuyến nghị chung cho production. Cần ghi lại cả CLI flags và đường dẫn đến file cấu hình cqlshrc sử dụng. File cấu hình mặc định thường nằm tại `~/.cassandra/cqlshrc`, nhưng có thể đặt qua `--cqlshrc`; username/password có thể đến từ file credentials riêng và phải được bảo vệ bằng quyền file.

**Không sao chép nguyên file chứa credentials** vào artifact để chứng minh khả năng tái hiện. Thay vào đó ghi “auth provider: PasswordAuthenticator; credential reference: secret-id (redacted)” và hướng dẫn người được ủy quyền tự cung cấp bí mật.

### 5.2. PAGING và TRACING có thể làm thay đổi quan sát

Ví dụ tương tác riêng:

~~~sql
PAGING 2;
TRACING ON;

SELECT event_time, value
FROM repro_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

TRACING OFF;
PAGING OFF;
~~~

`PAGING 2` lấy kết quả theo các trang nhỏ; khi chạy tương tác có thể xuất hiện yêu cầu người dùng lấy trang tiếp theo. Nếu dùng script tự động, cần kiểm tra liệu **toàn bộ trang đã được đọc** trước khi so sánh output. `TRACING ON` in thông tin thực thi và có thể sinh **trace session ID**; các thời gian và ID thay đổi mỗi lần chạy.

Do đó nên tách:

- **Functional run**: `PAGING OFF` cho dữ liệu nhỏ, `TRACING OFF`, đối chiếu giá trị.
- **Diagnostic run**: bật tracing hoặc page size đặc biệt và ghi rõ kết quả chỉ là quan sát, không so byte-for-byte với functional run.

## 6. Lab: script CQL với dữ liệu cố định và kết quả kỳ vọng

Toàn bộ phần này giả định **một Cassandra node lab, RF = 1, không có dữ liệu production**. Bạn sẽ tạo **hai file CQL** như mô tả dưới đây trong thư mục `input/` của thí nghiệm của chính mình.

### 6.1. File input/00-schema-and-seed.cql

~~~sql
-- 00-schema-and-seed.cql
-- Lab cô lập. RF=1 chỉ để thực hành trên một node.
CREATE KEYSPACE IF NOT EXISTS repro_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS repro_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  metric text,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

-- CẢNH BÁO: TRUNCATE xóa toàn bộ dữ liệu của bảng!
-- Chỉ được phép trong lab độc lập, khi chắc chắn đúng cluster/keyspace.
-- Đây là bước reset để mỗi lần chạy bắt đầu từ cùng dataset.
TRUNCATE repro_lab.events_by_device_day;

INSERT INTO repro_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, metric, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'temperature', 25.1);

INSERT INTO repro_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, metric, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'temperature', 25.4);

INSERT INTO repro_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, metric, value)
VALUES ('sensor-02', '2026-11-21', '2026-11-21T01:02:00Z',
        33333333-3333-4333-8333-333333333333, 'humidity', 61.0);
~~~

Đặt **primary key và timestamp trong dữ liệu** cố định để tránh bản ghi “ngẫu nhiên”. `TRUNCATE` chỉ có mục đích **reset bảng lab** và **không an toàn trên bảng chia sẻ/production**. Trước khi chạy, xác minh `SHOW HOST`/cluster và tên bảng; nếu không có quyền `TRUNCATE` thì dùng một keyspace lab mới có chủ đích thay vì tự tăng quyền.

Lưu ý: `IF NOT EXISTS` **không sửa schema cũ đã khác**. Nếu bảng `repro_lab.events_by_device_day` đã có cấu trúc khác lần đầu, `CREATE TABLE IF NOT EXISTS` sẽ không sửa lại; cần so `DESCRIBE TABLE` với script. `TRUNCATE` xóa dữ liệu hiện có của bảng, không phải câu CQL tạo schema.

### 6.2. File input/10-checks.cql

~~~sql
-- 10-checks.cql
-- Explicit session config: tránh phụ thuộc default của cqlshrc.
USE repro_lab;
CONSISTENCY ONE;
SERIAL CONSISTENCY SERIAL;
PAGING OFF;
TRACING OFF;

SHOW HOST;
SHOW VERSION;

DESCRIBE TABLE repro_lab.events_by_device_day;

SELECT cluster_name, data_center, release_version
FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'repro_lab';

-- Truy vấn chính: chỉ định đủ composite partition key.
SELECT event_time, event_id, metric, value
FROM repro_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;

-- Kiểm tra số row của đúng một partition, không quét toàn bảng.
SELECT COUNT(*)
FROM repro_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

**Kết quả logic cần khớp:**

| Kiểm tra | Kỳ vọng sau khi reset/nạp thành công |
| --- | --- |
| Schema | Bảng có composite partition key `(device_id, event_day)` và clustering `event_time DESC, event_id ASC`. |
| Query `sensor-01` | Chính xác **2 row**, lần lượt `01:05:00Z / 25.4` và `01:00:00Z / 25.1`. |
| `COUNT(*)` trên `sensor-01`, ngày `2026-11-21` | Bằng **2**. |
| Query `sensor-02` nếu chạy thêm | Một row `humidity / 61.0` ở `01:02:00Z`. |
| Metadata | Keyspace `repro_lab` có `SimpleStrategy`, RF = 1. |
| `SHOW HOST` / `SHOW VERSION` | Chứa endpoint và version **thực tế**, không cố định giống máy của người viết bài. |

Không dùng `SELECT COUNT(*) FROM repro_lab.events_by_device_day` **toàn bảng** như phép xác minh mặc định cho dataset lớn: đếm toàn bảng có thể quét rất nhiều partition. Lab này chỉ đếm đúng partition nhỏ và có key.

### 6.3. Chạy hai file bằng cqlsh -f

Tại terminal **Linux/macOS** ở thư mục thí nghiệm đã chuẩn bị:

~~~bash
# Chạy từ đúng máy/container có cqlsh và các file input.
# Điều chỉnh tên run và thư mục output trước mỗi lần chạy.
mkdir -p runs/run-001

# Thu stdout VÀ stderr, kể cả lỗi ngoài kết quả CQL.
cqlsh 127.0.0.1 9042 --no-color \
  -f input/00-schema-and-seed.cql \
  > runs/run-001/setup.log 2>&1
setup_status=$?

cqlsh 127.0.0.1 9042 --no-color \
  -f input/10-checks.cql \
  > runs/run-001/checks.log 2>&1
checks_status=$?

printf 'setup_exit=%s\nchecks_exit=%s\n' "$setup_status" "$checks_status"
~~~

`-f` chạy các câu trong file rồi thoát; `-e` chạy một câu và thoát, ví dụ:

~~~bash
cqlsh 127.0.0.1 9042 -e "SHOW VERSION;"
cqlsh 127.0.0.1 9042 -e "SELECT data_center FROM system.local;"
~~~

Điều quan trọng khi đánh giá:

- Chỉ chạy `10-checks.cql` **sau khi** `00-schema-and-seed.cql` hoàn tất và đã kiểm tra log chuẩn bị.
- Đọc **cả setup.log và checks.log**, xác nhận không có `SyntaxException`, `Unauthorized`, `Unavailable`, `ReadTimeout` hoặc lỗi parse/kiểu dữ liệu.
- Ghi **exit status** nhưng **không coi exit status = 0 là bằng chứng duy nhất** rằng từng câu CQL hoặc từng điều kiện nghiệp vụ đều thành công. Tùy bản cqlsh/chế độ thực thi, log và kiểm tra dữ liệu vẫn rất cần thiết.
- File `-f` và các đường dẫn kết quả được giải quyết ở **máy chạy cqlsh**. Nếu cqlsh chạy trong container, các file phải ở trong container hoặc volume được mount.
- `-f`/`SOURCE` **không tạo transaction nhiều câu**. Nếu một câu trong file lỗi, những câu ghi thành công trước đó không tự rollback; cần chạy lại từ trạng thái có kiểm soát.
- Các tham số timeout/TLS/auth và quyền file log cần tương ứng với môi trường thật; không đưa password vào command line hay log.

Lệnh `SOURCE` là lựa chọn tương đương về ý tưởng trong một **phiên cqlsh tương tác**:

~~~sql
-- Chỉ làm ở môi trường lab và sau khi đã kiểm tra đúng cluster!
SOURCE 'input/00-schema-and-seed.cql';
SOURCE 'input/10-checks.cql';
~~~

`SOURCE` và `-f` giúp chạy lại **lệnh gốc**, còn `HISTORY` chỉ giúp nhớ câu đã gõ, không bảo đảm có đủ tham số/đầu vào để tái hiện.

## 7. CAPTURE, stdout/stderr và HISTORY: ba loại “ghi lại” khác nhau

### 7.1. CAPTURE không ghi toàn bộ transcript

Trong một phiên cqlsh tương tác:

~~~sql
CAPTURE 'runs/run-001/query-results.txt';

SELECT event_time, event_id, metric, value
FROM repro_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

CAPTURE OFF;
CAPTURE;
~~~

Theo tài liệu cqlsh:

1. `CAPTURE 'file';` bắt đầu **ghi nối tiếp** kết quả câu CQL vào file, **không thay thế** nội dung cũ.
2. Khi đang capture, đầu ra kết quả không xuất hiện bình thường ở terminal.
3. `CAPTURE OFF;` kết thúc và trả việc hiển thị output về shell.
4. `CAPTURE;` không có tham số kiểm tra trạng thái capture.
5. **Chỉ kết quả truy vấn được capture. Lỗi và đầu ra của các lệnh riêng cqlsh** (ví dụ `SHOW VERSION`, `CONSISTENCY`, `DESCRIBE`, `TRACING`) **không được lưu đầy đủ qua CAPTURE**; chúng vẫn có thể hiển thị ở phiên tương tác.

Vì thế, **file capture không phải log kiểm toán**. Để phục vụ thí nghiệm, cần lưu **script** và **transcript stdout/stderr** từ cách chạy non-interactive hoặc cơ chế logging được kiểm soát. Nếu gặp lỗi, đừng đưa ra kết luận “không có lỗi” chỉ vì `query-results.txt` không có dòng lỗi.

### 7.2. So sánh ba cách ghi kết quả

| Cách | Ghi được gì? | Không thay thế được gì? |
| --- | --- | --- |
| `CAPTURE 'path'` | Kết quả câu CQL được cqlsh in ra trong thời gian capture | Không ghi đủ lỗi, special commands hoặc script gốc. |
| Shell redirect `> run.log 2>&1` với `cqlsh -f` | Output ra stdout/stderr của **tiến trình cqlsh** | Không tự chứng minh expected/actual, không bảo toàn trạng thái server. |
| `HISTORY 20` / file cql history | Những lệnh tương tác trước đó (tùy phiên bản/cấu hình) | Không phải manifest, không có dữ liệu fixture, RF/CL hay stdout đầy đủ. |

Nếu cần transcript tương tác cả input và output, có thể dùng công cụ terminal recorder đã được phê duyệt, nhưng cần kiểm soát **credential prompts, bí mật và dữ liệu nhạy cảm**. Một video/terminal capture cũng cần đi kèm **script + manifest** để người khác có thể chạy lại không phụ thuộc thao tác gõ tay.

### 7.3. HISTORY và nguy cơ lộ bí mật

~~~sql
-- Xem một phần lịch sử lệnh theo phiên bản cqlsh hỗ trợ.
HISTORY 20;
~~~

Theo tài liệu hiện hành, cqlsh thường lưu lịch sử tại `~/.cassandra/cql_history`. Ở Cassandra 4.0 trở lên, có thể tắt tính năng ghi history bằng `--disable-history`, cấu hình `cqlshrc` hoặc chuyển `CQL_HISTORY` theo hệ điều hành/cấu hình; kiểm tra khả năng thật của phiên bản đang dùng.

**Lịch sử lệnh không an toàn để lưu password**. Đặc biệt các câu như `CREATE ROLE ... PASSWORD '...'` chứa secret trong văn bản CQL, có thể lộ trong history, log, clipboard hoặc artifact. Hãy quản lý role/credentials bằng quy trình bảo mật được phép, không đính kèm history thô vào kết quả thí nghiệm.

## 8. Tạo manifest và checksum để người khác biết đã chạy cái gì

Một manifest **tham khảo** cho run-001, không chứa secret:

~~~yaml
experiment_id: cassandra-repro-lab-001
purpose: "Kiểm chứng partition key và clustering order"
run_id: run-001
started_at_utc: "2026-11-21T02:00:00Z" # thời gian mẫu, thay bằng thực tế
client:
  tool: cqlsh
  version: "GHI_TU_SHOW_VERSION"
  native_protocol: "GHI_TU_SHOW_VERSION"
  contact_point: "127.0.0.1:9042"
  tls: false # chỉ ví dụ lab local
server:
  cassandra_release: "GHI_TU_SYSTEM_LOCAL"
  cluster_name: "GHI_TU_SYSTEM_LOCAL"
  datacenter: "GHI_TU_SYSTEM_LOCAL"
  replication: "SimpleStrategy/RF=1"
session:
  keyspace: repro_lab
  consistency: ONE
  serial_consistency: SERIAL
  paging: OFF
  tracing: OFF
files:
  schema_and_seed: input/00-schema-and-seed.cql
  checks: input/10-checks.cql
  setup_log: runs/run-001/setup.log
  checks_log: runs/run-001/checks.log
expected:
  sensor_01_rows: 2
  sensor_01_latest_value: 25.4
validation: "GHI_PASS_HOAC_FAIL_SAU_KHI_KIEM_TRA"
~~~

Các giá trị `GHI_TU_...` là **placeholder giải thích**, phải thay bằng thông tin thật trước khi công bố. `started_at_utc` ở trên không phải thời gian đã chạy một thí nghiệm thực. Nếu dùng công cụ tự sinh manifest, nó nên lưu **script hash, timestamp thực, client/server versions, exit codes và kết quả kiểm tra**.

### 8.1. Hash file đầu vào

Trên Linux (hoặc macOS đã cài GNU coreutils), sau khi đã tạo file thí nghiệm:

~~~bash
# Hash chứng minh những byte đầu vào nào đã được dùng.
sha256sum input/00-schema-and-seed.cql input/10-checks.cql \
  > runs/run-001/checksums.sha256

# Khi cần đối chiếu, thực thi trong cùng bố cục đường dẫn.
sha256sum -c runs/run-001/checksums.sha256
~~~

Với macOS mặc định không có GNU `sha256sum`, có thể thay bằng `shasum -a 256`:

~~~bash
shasum -a 256 input/00-schema-and-seed.cql input/10-checks.cql \
  > runs/run-001/checksums.sha256
shasum -a 256 -c runs/run-001/checksums.sha256
~~~

Trên Windows PowerShell, có thể dùng:

~~~powershell
Get-FileHash -LiteralPath .\input\00-schema-and-seed.cql -Algorithm SHA256
Get-FileHash -LiteralPath .\input\10-checks.cql -Algorithm SHA256
~~~

Hash giúp phát hiện file input bị sửa, nhưng **không chứng minh dữ liệu trong cluster không đổi**. Để đảm bảo tái hiện, manifest còn phải ghi trạng thái nguồn dữ liệu, schema, reset policy và điều kiện thao tác. Khi tập dữ liệu nhập đến từ CSV lớn, nên hash **tệp CSV nguồn và script mapping**.

### 8.2. Đối chiếu expected vs actual

Ví dụ một ghi chép sau khi đã chạy:

~~~text
Run: run-001 (lab local)
Input: 00-schema-and-seed.cql + 10-checks.cql
Session: ONE / SERIAL / PAGING OFF / TRACING OFF
Expected: 2 rows for (sensor-01, 2026-11-21)
Observed: 2 rows, 01:05Z=25.4; 01:00Z=25.1
Result: PASS
Notes: Không đo latency; chưa kiểm chứng replication đa node.
~~~

Đây là **mẫu ghi chép**, không phải kết quả từ Cassandra đã thực sự chạy trong bài viết này. Nếu quan sát chỉ có 1 row, không được tự sửa `expected` cho khớp: hãy điều tra log nhập liệu, schema, primary key, timezone, lỗi ghi và kết nối nhầm cluster.

## 9. Tái hiện thí nghiệm về consistency, paging và tracing

Một báo cáo chỉ ghi “`SELECT` thành công” sẽ thiếu ý nghĩa nếu mục tiêu là khảo sát tính nhất quán phân tán. Cần phân loại:

### 9.1. Thí nghiệm đọc ở consistency khác nhau

| Biến cần giữ ổn định | Cách ghi |
| --- | --- |
| Keyspace + RF/DC | `DESCRIBE KEYSPACE` hoặc `system_schema.keyspaces` |
| Dataset + partition | Primary key và giá trị fixture đã biết |
| Query text | Script CQL đúng phiên bản |
| CL | `CONSISTENCY ONE`, `QUORUM`, `LOCAL_QUORUM`... |
| Số node/replica sẵn sàng | `nodetool status` cùng thời điểm và log |
| Thời điểm, số lần chạy | Timestamp UTC và run ID |

**Ví dụ lý thuyết:** với một datacenter RF = 3, `LOCAL_QUORUM` cần 2 replica phản hồi. Với lab RF = 1, `LOCAL_QUORUM` chỉ cần 1 replica trong DC đó. Nếu muốn đo tình huống một replica không khả dụng, cần **cluster lab nhiều node** và thí nghiệm lỗi có kiểm soát; không tắt node production để tạo biểu đồ cho bài học.

### 9.2. Thí nghiệm LWT cần ghi hai mức consistency

~~~sql
-- Cài đặt dùng cho các truy vấn LWT nếu có IF.
CONSISTENCY ONE;
SERIAL CONSISTENCY SERIAL;
~~~

**Regular consistency** và **serial consistency** là hai giá trị khác nhau. `SERIAL CONSISTENCY` chỉ áp dụng phần serial/Paxos của những thao tác điều kiện `IF`. Khi so sánh LWT, còn phải ghi **trạng thái ban đầu của row** vì `INSERT ... IF NOT EXISTS` trả `[applied] = true` lần đầu và có thể trả `false` ở lần chạy lại. Không thể tuyên bố “không tái hiện” chỉ vì đã thay đổi chính điều kiện đầu vào.

### 9.3. Paging và đo thời gian

Với `PAGING 2`, cqlsh có thể hỏi người dùng có lấy trang kế không. Nếu chỉ ghi trang đầu thì kết quả có thể **thiếu row** chứ không phải dữ liệu mất. Để đo thời gian, phải phân biệt:

- **Thời gian request ở coordinator**.
- **Thời gian từ client** (bao gồm mạng, deserialize, các page và thời gian chờ prompt).
- **Thời gian toàn script** (gồm thiết lập kết nối, tạo schema, dữ liệu và in ra terminal).

`TRACING ON` có overhead và trace events phụ thuộc coordinator/replica đang xử lý. So sánh latency nên dùng nhiều lần chạy, warm-up nếu thích hợp, percentile và cấu hình nền tương đương. **Không so trực tiếp một truy vấn bật tracing với một truy vấn không tracing như benchmark khách quan.**

## 10. Ghi lại khi thí nghiệm thất bại

### 10.1. Lỗi cũng là một quan sát hợp lệ

Nếu mục tiêu thử `CONSISTENCY TWO` trên lab RF = 1, kết quả `Unavailable` là một quan sát **dự kiến**, không phải bằng chứng script bị hỏng. Ngược lại, nếu `SELECT` theo partition key đáng ra thành công nhưng nhận `Unauthorized` thì thí nghiệm không đạt điều kiện đăng nhập/quyền.

| Lỗi | Ghi thêm bằng chứng gì? | Tránh làm gì? |
| --- | --- | --- |
| `SyntaxException`, `InvalidRequest` | Query, line/token, `DESCRIBE TABLE`, version | Không sửa query mà không cập nhật hash/version script. |
| `AuthenticationException` | Cấu hình TLS/auth đã được lọc secret, role name nếu được phép, endpoint | Không ghi password ra run log, không thử brute force. |
| `Unauthorized` | Permission đã cấp, role thực đang chạy, bảng/command | Không tắt authorizer hoặc chạy bằng admin để giả vờ PASS. |
| `Unavailable` | CL, RF, DC, số replica cần/sẵn sàng, `nodetool status` | Không hạ CL production chỉ để làm báo cáo đẹp. |
| `ReadTimeout` | Request timeout, CL, query pattern, tombstone/latency, trạng thái replica | Không xem timeout là “0 row”. |
| `WriteTimeout` | Primary key, idempotency, số replica phản hồi, dữ liệu đã đọc lại | Không retry mù; thao tác có thể đã ghi một phần/toàn bộ. |
| `AllNodesFailedException` | Contact points, địa chỉ peer, DNS/TCP/TLS/native protocol, local DC | Không suy là lỗi truy vấn CQL khi session chưa kết nối. |

Khi một run thất bại, lưu **script gốc bất biến** và tạo **run mới** sau khi sửa, thay vì sửa file rồi ghi kết quả vào cùng thư mục cũ. Ghi rõ “thử lần 1 gặp lỗi X; lần 2 sửa Y; kết quả Z”.

### 10.2. Quy trình phân tích sai khác

~~~mermaid
flowchart TD
    A["Kết quả chạy lại khác kỳ vọng"] --> B{"Script và dữ liệu ban đầu giống nhau?"}
    B -->|"Không"| C["Kiểm tra hash, fixture, reset, keyspace"]
    B -->|"Có"| D{"Phiên bản/schema/session giống?"}
    D -->|"Không"| E["Đối chiếu SHOW VERSION, DDL, CL, paging, timeout"]
    D -->|"Có"| F{"Lỗi permission/TLS hoặc replica?"}
    F -->|"Có"| G["Kiểm tra auth, node status, RF, internode"]
    F -->|"Không"| H{"Chênh lệch logic hay chỉ latency/trace?"}
    H -->|"Logic"| I["Điều tra dữ liệu ghi đồng thời, TTL, timestamp, LWT"]
    H -->|"Latency"| J["Lặp lại có kiểm soát, metrics, GC, compaction, tải"]
~~~

Đối với Cassandra, **schema giống nhau** chưa bảo đảm dữ liệu giống nhau: replica có thể ở trạng thái khác, có concurrent writers, TTL/tombstones hoặc thay đổi topology. Không can thiệp trực tiếp `system_schema`/`system` để “đồng bộ” thử nghiệm.

## 11. Java Driver: ghi thí nghiệm ở cấp statement

Các lệnh `CONSISTENCY`, `PAGING`, `CAPTURE` và `SHOW VERSION` thuộc **cqlsh**, không tự áp dụng cho session Java khác. Trong Java Driver 4.x, mỗi statement có thể chỉ định consistency, page size và timeout để thí nghiệm không phụ thuộc default.

Ví dụ dùng **bảng và fixture** đã tạo ở mục 6; cần dependency `com.datastax.oss.driver` tương thích Cassandra/Java của dự án:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;

public class ReproduceCassandraQuery {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        Instant startedAt = Instant.now();
        System.out.println("started_at_utc=" + startedAt);
        System.out.println("contact_point=" + host + ":9042");
        System.out.println("local_dc=" + dc);

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT event_time, event_id, metric, value " +
                "FROM repro_lab.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ?");

            BoundStatement statement = prepared.bind(
                    "sensor-01", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(100)
                .setTimeout(Duration.ofSeconds(5));

            int count = 0;
            for (Row row : session.execute(statement)) {
                count++;
                System.out.println(
                    row.getInstant("event_time") + "," +
                    row.getUuid("event_id") + "," +
                    row.getString("metric") + "," +
                    row.getDouble("value"));
            }
            System.out.println("row_count=" + count);
            if (count != 2) {
                throw new IllegalStateException("Expected 2 rows");
            }
        }
    }
}
~~~

**Chú ý khi so sánh với cqlsh:**

- `datacenter1` là **ví dụ**; xác định tên datacenter thực bằng `SELECT data_center FROM system.local;` rồi đặt `CASSANDRA_DC` đúng.
- Java Driver có thể chọn coordinator khác cqlsh, và có thể khám phá các peer native khác contact point; log/metric cần ghi endpoint thích hợp khi điều tra vấn đề topology.
- `setConsistencyLevel(ONE)`, `setPageSize(100)`, `setTimeout(5 giây)` được đặt ở **statement Java**. Chúng **không lấy** cấu hình từ phiên cqlsh khác.
- Code ví dụ không cấu hình auth/TLS; với server yêu cầu, phải thêm auth provider và SSL context tin cậy CA, không tắt bảo mật để chạy demo.
- `Instant.now()` ghi **thời gian thực chạy**, không phải giá trị kết quả logic cần giống hệt lần trước.
- Việc kiểm tra `count == 2` chỉ xác minh một điều kiện; trong thực tế cần kiểm tra **giá trị, thứ tự, metadata và lỗi** theo mục tiêu.
- Đoạn code chưa phải benchmark. Với nhiều page, phải đảm bảo đã đọc **tất cả page** mong đợi; với test hiệu năng, cần chạy nhiều lần và thu percentile.

Trong một service production, dùng logging/correlation ID theo chính sách, có giới hạn cardinality và tránh log toàn bộ bind values, user data, credentials hoặc stack trace chứa thông tin nhạy cảm. `CqlSession` nên được tái sử dụng trong vòng đời service thay vì tạo một session trên mỗi request.

## 12. Checklist trước khi công bố hoặc chuyển thí nghiệm cho người khác

| Kiểm tra | Đạt khi |
| --- | --- |
| **Phạm vi lab** | Xác minh cluster/keyspace đúng, dữ liệu không phải production, thao tác `TRUNCATE` được phép. |
| **Mục tiêu** | Có giả thuyết hoặc expected output cụ thể, đo được. |
| **Môi trường** | Có Cassandra/cqlsh/native protocol versions, endpoint, DC, RF, ghi thời điểm UTC. |
| **Schema** | Có DDL/script và `DESCRIBE` khớp với schema trước khi chạy. |
| **Dữ liệu** | Có fixture hoặc hướng dẫn reset an toàn; không phụ thuộc UUID ngẫu nhiên hay row từ lần cũ. |
| **Session** | Ghi CL, serial CL, paging, tracing, timezone, timeout và TLS/auth mode (đã che secret). |
| **Lệnh** | Script có thứ tự, file được hash, không phải chỉ ảnh chụp màn hình. |
| **Output** | Có stdout+stderr, exit status, result, số row và lỗi nếu có. |
| **So sánh** | Có expected vs actual và phân loại số liệu được phép dao động. |
| **Bảo mật** | Không lộ password, private key, token hay dữ liệu nhạy cảm trong repo/artifact. |
| **Vận hành** | Không chạy lệnh xóa/repair/compact hoặc fault injection trên production không có quy trình được duyệt. |

### 12.1. Năm lỗi thường khiến thí nghiệm không thể tái hiện

1. **Chỉ chụp kết quả SELECT** nhưng không lưu DDL, dữ liệu nguồn hoặc consistency.
2. **Dùng `CAPTURE` làm log duy nhất**, trong khi errors và nhiều special commands không được capture.
3. **Không tách output giữa các run** nên file append làm kết quả trông nhiều row hơn thực tế.
4. **Quên stateful operations**: LWT `IF NOT EXISTS`, counter, TTL, dữ liệu cũ và cache khiến lần thứ hai khác lần đầu.
5. **Không bảo vệ secrets**: commit file `cqlshrc` có password hoặc lịch sử lệnh tạo role có mật khẩu vào repository.

## 13. Bài tự thực hành

1. Ghi mục tiêu “đọc đúng 2 row của `sensor-01` trong ngày `2026-11-21` theo `event_time DESC`”, rồi liệt kê tối thiểu sáu thành phần phải lưu để người khác tái hiện.
2. Tạo hai file `input/00-schema-and-seed.cql` và `input/10-checks.cql` như bài, chạy bằng `cqlsh -f` trong **cluster lab**. Xác minh trước khi script có `TRUNCATE`.
3. Dùng `SHOW VERSION`, `SHOW HOST`, `system.local` và `system_schema.keyspaces` để điền manifest bằng giá trị thực.
4. Chạy lại trong một run mới, kiểm tra hai row bằng primary key, đối chiếu giá trị/ordering và hash input với run trước.
5. Dùng `CAPTURE` cho một `SELECT` rồi gây lỗi cú pháp có chủ đích trong lab. Giải thích vì sao file capture có thể không chứa lỗi.
6. Dùng `HISTORY 20` để tìm lệnh đã gõ, rồi giải thích vì sao không nên lưu history thô hoặc dùng nó thay cho CQL script.
7. Thay `PAGING OFF` bằng `PAGING 2` với một partition có nhiều hơn hai row. Xác minh có đọc hết trang trước khi so sánh tổng row.
8. Bật `TRACING ON` cho một query nhỏ rồi tắt. Liệt kê những thông tin tracing ID/latency khác nhau giữa hai lần chạy và vì sao.
9. Trong cluster lab nhiều node, thử `LOCAL_QUORUM` với RF phù hợp rồi ghi snapshot `nodetool status`. Giải thích vì sao không thể suy luận CL từ screenshot SELECT đơn thuần.
10. Dùng Java Driver với statement `ONE`, page size/timeout cố định và log số row. Phân biệt cấu hình của Java với các lệnh cqlsh trong một terminal khác.
11. Giả sử báo cáo lần 1 có hai row, lần 2 có ba. Đưa ra quy trình kiểm tra lần lượt fixture, script hash, schema, reset, key và connection endpoint.
12. Thiết kế một phiên bản manifest không chứa dữ liệu nhạy cảm nhưng vẫn đủ thông tin để kỹ sư được cấp quyền tái chạy trên staging.

**Tiêu chí hoàn thành:** có một bộ script đầu vào, cấu hình phiên được ghi rõ, log/manifest/checksum được phân biệt, kết quả expected/actual được kiểm chứng và không lộ secrets; hiểu rõ rằng **tái hiện dữ liệu logic** khác với việc đòi hỏi **timing/trace giống hệt** trong hệ phân tán.

## Tài liệu tham khảo

- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `SOURCE`, `CAPTURE`, `HISTORY`, `SHOW VERSION`, `SHOW HOST`, `CONSISTENCY`, `SERIAL CONSISTENCY`, `PAGING`, `TRACING`, `-f`/`-e` và cqlshrc.
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): DDL, partition key, clustering order, `SELECT`, `INSERT` và kiểu dữ liệu.
- [Apache Cassandra — Architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/overview.html): coordinator, replica, replication và cluster topology.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): `status`, `describecluster` và quan sát node.
- [Apache Cassandra Java Driver 4.x — Core](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/index.html): statement-level consistency, paging, timeout, session và metadata.
