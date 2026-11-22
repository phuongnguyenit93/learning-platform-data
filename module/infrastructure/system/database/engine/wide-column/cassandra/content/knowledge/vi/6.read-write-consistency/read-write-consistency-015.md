# Thực nghiệm nhiều phiên và mất nút để kiểm chứng điều kiện đọc/ghi

Một câu hỏi quan trọng khi học **nhất quán đọc/ghi** của Apache Cassandra là: **Nếu một replica ngừng hoạt động giữa lúc hai client cùng đọc và ghi, thao tác nào vẫn thành công và dữ liệu nào có thể được quan sát?** Ta có thể học công thức `R + W > N` trên giấy, nhưng chỉ khi chạy qua nhiều phiên client, quan sát lỗi `Unavailable`/`Timeout` và khôi phục node, ý nghĩa của **ngưỡng ACK**, **đường đọc**, **phạm vi replica** và **kết quả ghi chưa xác định** mới trở nên rõ ràng.

Bài thực hành này thuộc chương **Nhất quán đọc/ghi** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nó kết nối kiến trúc phân tán và mô hình wide-column với partition key, thiết kế bảng theo truy vấn, CQL, replication, xử lý lỗi, hinted handoff, repair, compaction và ứng dụng Java. Mục tiêu không phải tạo ra sự cố cho bằng được, mà là **đặt giả thuyết, chạy phép thử có kiểm soát, phân biệt điều đã quan sát với điều được bảo đảm về mặt logic**.

> **Giới hạn an toàn:** Toàn bộ thao tác dừng node, tạo mạng chậm hoặc xóa dữ liệu trong bài **chỉ dùng trên cluster lab biệt lập và dữ liệu giả**. Không thực hiện `docker compose stop`, cấu hình lỗi mạng, `TRUNCATE` hoặc thử nghiệm làm gián đoạn dịch vụ trên cluster production.

## 1. Mục tiêu và kết quả cần nộp

Kết thúc bài, bạn sẽ có thể:

1. Mở **hai phiên `cqlsh` riêng biệt**, đặt CL độc lập và xác nhận mỗi phiên cần chọn CL của chính nó.
2. Tính ngưỡng của `ONE`, `TWO`, `QUORUM` và `ALL` với RF=3 trước khi dừng replica.
3. Quan sát hành vi khi **ba, hai hoặc một replica** của partition có thể phản hồi.
4. Giải thích tại sao `WriteTimeout`/`Unavailable` **không đồng nghĩa** với “mutation chắc chắn chưa được áp dụng”.
5. Kiểm chứng một **dự đoán về tập ACK/phản hồi giao nhau** khi `R + W > N`, đồng thời không nhầm một lần đọc tình cờ mới với bảo đảm tổng quát.
6. Minh họa sự khác biệt giữa **thứ tự request** và **timestamp thắng theo last-write-wins**.
7. Đối chiếu `LOCAL_QUORUM` cùng/khác DC, `QUORUM` và ghi `EACH_QUORUM` trong phần mở rộng nhiều datacenter.
8. Viết client Java Driver 4.x đặt CL trên từng statement và phân loại lỗi.
9. Lập bảng ghi nhận kết quả, nguyên nhân sai khác, cách khôi phục và điều gì thí nghiệm **chưa chứng minh được**.

**Sản phẩm học tập mong đợi:** một bảng kết quả “dự đoán → quan sát → giải thích”, sơ đồ topology, log những CL đã dùng và lời giải thích vì sao phép đếm phản hồi không thay thế kiến thức về timestamp, reconciliation hoặc LWT.

## 2. Mô hình lý thuyết trước khi chạy

### 2.1. Replication factor và partition

Cassandra phân bố dữ liệu theo **partition key**. Replication strategy, RF và token placement quyết định những **replica đích** của một partition. Node nhận request là **coordinator**, có thể là replica đích hoặc không.

Trong lab một datacenter với **ba node và RF=3**, mỗi partition có ba full replica. Gọi chúng là `R1`, `R2`, `R3`:

```text
                     Cqlsh A                 Cqlsh B
                        |                       |
                        v                       v
                 Coordinator R1          Coordinator R2
                         \                 /
                          \               /
                          +---------------+
                          |   Partition P |
                          +---------------+
                          /       |       \
                         v        v        v
                        R1       R2        R3

             Tập replica của P: S={R1,R2,R3}, N=3.
```

Hai phiên client có **coordinator khác nhau**, nhưng cùng truy vấn một partition nên vẫn hướng tới **cùng tập replica đích `S`** trong topology ổn định. Việc chạy hai phiên không tự tạo hai bản sao dữ liệu độc lập; hai phiên chỉ là hai người quan sát và điều khiển thao tác.

### 2.2. Mức nhất quán là ngưỡng phản hồi

Trong một DC RF=3:

| CL | Số phản hồi tối thiểu | Ví dụ khi một replica down |
| --- | ---: | --- |
| `ONE` | 1 | Có thể đáp ứng. |
| `TWO` | 2 | Có thể đáp ứng nếu hai replica còn lại kịp phản hồi. |
| `THREE` | 3 | Không đáp ứng. |
| `QUORUM` | `floor(3/2)+1=2` | Có thể đáp ứng nếu hai replica còn lại kịp phản hồi. |
| `ALL` | 3 | Không đáp ứng. |
| `LOCAL_ONE` | 1 replica local | Trong lab chỉ một DC, cùng phạm vi replica với `ONE`. |
| `LOCAL_QUORUM` | 2 replica local | Trong lab chỉ một DC, cùng ngưỡng với `QUORUM`. |

`ANY` là CL **chỉ dùng cho ghi**. Trong những trường hợp được hỗ trợ, ghi `ANY` có thể trả thành công chỉ nhờ coordinator lưu **hint** mà **chưa replica đích nào ACK**. Với một cluster chỉ có ba node và RF=3, nếu **cả ba replica đều down**, cũng không còn coordinator sống để thử trường hợp này; đừng suy ra “`ANY` luôn ghi được dù toàn cluster đã tắt”.

### 2.3. Điều kiện giao nhau

Giả sử một lần ghi **đã trả thành công** sau `W` ACK từ cùng tập `S` có `N` replica. Một lần đọc thành công sau đó nhận ít nhất `R` phản hồi hợp lệ từ cùng tập `S`. Khi:

\[
R + W > N
\]

hai tập replica **chắc chắn giao nhau ít nhất một phần tử**. Chứng minh ngắn gọn:

\[
|A \cap B| = |A|+|B|-|A\cup B|\ \ge\ R+W-N
\]

Với RF=3:

| CL ghi → CL đọc | `W` | `R` | `W+R>N`? | Kết luận |
| --- | ---: | ---: | --- | --- |
| `ONE` → `ONE` | 1 | 1 | `2>3`: sai | **Không bảo đảm** giao nhau. |
| `ONE` → `QUORUM` | 1 | 2 | `3>3`: sai | **Không bảo đảm** giao nhau. |
| `QUORUM` → `ONE` | 2 | 1 | `3>3`: sai | **Không bảo đảm** giao nhau. |
| `QUORUM` → `QUORUM` | 2 | 2 | `4>3`: đúng | **Bắt buộc giao nhau**. |
| `ALL` → `ONE` | 3 | 1 | `4>3`: đúng | Bắt buộc giao nhau, **nếu ghi `ALL` thực sự thành công**. |
| `ONE` → `ALL` | 1 | 3 | `4>3`: đúng | Bắt buộc giao nhau, **nếu đọc `ALL` thực sự thành công**. |

**Điều quan trọng:** `R+W>N` là **điều kiện đủ** về mặt tập hợp, không phải điều kiện cần của mọi lần chạy cụ thể. Khi `R+W≤N`, hai tập **có thể rời nhau**, nhưng nếu client tình cờ hỏi trúng replica vừa ghi thì vẫn đọc được dữ liệu mới.

Điều kiện giao nhau cũng **không tự bảo đảm linearizability** cho mọi cập nhật cạnh tranh; timestamp, xóa/tombstone, TTL và thứ tự thực thi vẫn quyết định giá trị logic trả về.

## 3. Dựng một cluster lab ba node, một DC

Bạn có thể dùng một cluster Cassandra 4.x/5.x đã có sẵn với ba node thuộc cùng DC. Để bài thực hành tự chứa, đây là cấu hình **Docker Compose minh họa** cho Cassandra 4.1. Cần Docker với đủ CPU/RAM cho ba JVM; không chạy cùng cluster production.

Tạo file `compose.yaml` trong **một thư mục lab tạm riêng** (không phải thư mục bài học này):

```yaml
services:
  cass1:
    image: cassandra:4.1
    environment:
      CASSANDRA_CLUSTER_NAME: rw-consistency-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack1
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cass1
    ports:
      - "9042:9042"

  cass2:
    image: cassandra:4.1
    environment:
      CASSANDRA_CLUSTER_NAME: rw-consistency-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack2
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cass1
    depends_on:
      - cass1

  cass3:
    image: cassandra:4.1
    environment:
      CASSANDRA_CLUSTER_NAME: rw-consistency-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack3
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cass1
    depends_on:
      - cass1
```

Khởi động seed node trước; chỉ cho các node còn lại tham gia khi seed đã sẵn sàng:

```bash
# Terminal điều khiển, tại thư mục chứa compose.yaml
docker compose up -d cass1

# Xác nhận cass1 đã khởi động đủ để nodetool hoạt động.
docker compose exec cass1 nodetool status

# Sau đó thêm hai node còn lại.
docker compose up -d cass2 cass3

# Kiểm tra ring từ một node đang sống.
docker compose exec cass1 nodetool status
```

Đợi `nodetool status` hiển thị **ba node `UN` (Up/Normal)** trong cùng `dc1`, và kiểm tra schema đã ổn định trước khi thử ghi. `depends_on` chỉ bảo đảm thứ tự khởi tạo container, **không** bảo đảm Cassandra bên trong đã sẵn sàng nhận CQL. Nếu image, bộ nhớ hoặc network của môi trường khác nhau, cần điều chỉnh cách khởi động phù hợp. **Không tính thời gian cố định** rồi mặc định node đã UP.

### Những điều cần xác nhận trước khi thử

| Mục kiểm tra | Trạng thái mong đợi |
| --- | --- |
| Cluster name | `rw-consistency-lab`, không phải cluster thật. |
| Datacenter | Chỉ một DC `dc1`. |
| Node | `cass1`, `cass2`, `cass3` cùng ở trạng thái `UN`. |
| CQL | `cqlsh` kết nối được vào mỗi node. |
| Dữ liệu | Chỉ dùng các ID giả trong namespace lab. |
| Quyền thao tác | Được phép stop/start container lab, không ảnh hưởng người dùng thật. |

**Lưu ý về độ tin cậy:** Đây là cấu hình lab tối giản, không phải mẫu triển khai production. Nó không bổ sung authentication, TLS, persistent volume, healthcheck hoặc giám sát. Khi dùng dịch vụ Cassandra được quản lý, hãy thay các bước Docker bằng cơ chế fault injection được môi trường test cho phép.

## 4. Chuẩn bị bảng và hai phiên `cqlsh` độc lập

### 4.1. Mở ba terminal

Mở ba cửa sổ terminal **trên cùng máy lab**:

**Terminal A — phiên client ghi chính, coordinator `cass1`:**

```bash
docker compose exec cass1 cqlsh
```

**Terminal B — phiên client đọc/ghi cạnh tranh, coordinator `cass2`:**

```bash
docker compose exec cass2 cqlsh
```

**Terminal C — điều khiển lỗi và quan sát ring:**

```bash
docker compose exec cass1 nodetool status
```

Giữ hai phiên `cqlsh` A/B mở khi thực nghiệm; mỗi phiên lưu **consistency setting của chính nó**. Khi dừng node đang chứa một phiên `cqlsh`, phiên đó có thể mất kết nối; hãy mở lại trên node còn hoạt động.

### 4.2. Tạo keyspace RF=3 và bảng theo partition key

Tại **Terminal A**, chạy:

```sql
CREATE KEYSPACE IF NOT EXISTS session_failure_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS session_failure_lab.order_state_by_id (
  order_id uuid PRIMARY KEY,
  state text,
  operation_id uuid,
  updated_at timestamp
);

CREATE TABLE IF NOT EXISTS session_failure_lab.seat_by_key (
  seat_key text PRIMARY KEY,
  owner_id uuid,
  operation_id uuid
);
```

`order_id` và `seat_key` lần lượt là **partition key**. Việc chọn `WHERE order_id = ?` cho đường đọc giúp hai phiên đi tới đúng tập replica của cùng partition. Không thay bằng truy vấn quét toàn bảng hoặc hai bảng denormalized khác nhau rồi áp dụng phép chứng minh giao nhau.

Tại **Terminal B**, kiểm tra schema đã được nhìn thấy:

```sql
DESCRIBE KEYSPACE session_failure_lab;
```

Chỉ tiếp tục khi các node đã có schema thống nhất. Trong lab **ba node RF=3**, mọi node của DC là replica của mỗi partition; ở cluster nhiều node hơn RF, phải xác minh **replica placement của đúng partition**, không lấy bất kỳ node down nào làm một “replica bị mất”.

### 4.3. Ghi nhận CL riêng của mỗi phiên

Tại A:

```sql
CONSISTENCY QUORUM;
CONSISTENCY;
```

Tại B:

```sql
CONSISTENCY ONE;
CONSISTENCY;
```

Lệnh `CONSISTENCY` là lệnh của **`cqlsh`**, không phải mệnh đề ghép vào `SELECT` hoặc `UPDATE`. A đang dùng `QUORUM` không làm CL của B thay đổi. Sau mỗi bước, nên ghi **CL thực tế ở cả hai phiên**, không suy ra từ lần chọn trước đó của một phiên khác.

## 5. Thí nghiệm 1 — Cluster khỏe, hai phiên đọc và ghi

**Giả thuyết:** Với RF=3 và cả ba replica khỏe, ghi `QUORUM` (W=2) và đọc `QUORUM` (R=2) có giao nhau; đọc `ONE` không có bảo đảm giao nhau nhưng vẫn thường thấy giá trị mới khi replication hoạt động bình thường.

### Bước 1 — A ghi trạng thái ban đầu

Tại A:

```sql
CONSISTENCY QUORUM;

INSERT INTO session_failure_lab.order_state_by_id
  (order_id, state, operation_id, updated_at)
VALUES (
  11111111-1111-4111-8111-111111111111,
  'CREATED',
  22222222-2222-4222-8222-222222222222,
  '2026-11-21 08:00:00+0000'
);
```

Đây là mutation trên một partition có RF=3; nếu `INSERT` trả thành công, ghi đã nhận đủ ACK theo `QUORUM`. Không suy từ đó rằng mọi replica đã có dữ liệu cùng lúc.

### Bước 2 — B đọc ở ONE

Tại B:

```sql
CONSISTENCY ONE;

SELECT order_id, state, operation_id
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

**Quan sát dự kiến:** thường trả `CREATED`. Điều này **không chứng minh `ONE` có read-after-write bảo đảm**: trong một cluster khỏe, mutation thường đến đủ replica rất nhanh, nên ngay cả mức yếu cũng có thể thấy bản mới.

### Bước 3 — A cập nhật; B đọc ở QUORUM

Tại A:

```sql
CONSISTENCY QUORUM;

UPDATE session_failure_lab.order_state_by_id
SET state = 'PAID',
    operation_id = 33333333-3333-4333-8333-333333333333,
    updated_at = '2026-11-21 08:05:00+0000'
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Sau khi A nhận thành công, tại B:

```sql
CONSISTENCY QUORUM;

SELECT state, operation_id, WRITETIME(state)
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

**Quan sát dự kiến:** `PAID` và operation ID mới. `WRITETIME(state)` biểu diễn timestamp của **cell đang thắng**, không phải toàn bộ lịch sử mutation hoặc bằng chứng mọi replica đã flush SSTable.

### Bước 4 — Đối chiếu lý thuyết

Tập ACK ghi `A` có ít nhất 2 trong 3 replica; tập phản hồi đọc `B` có ít nhất 2 trong 3. Do `2+2>3`, hai tập giao nhau. Khi không có cập nhật cạnh tranh thắng theo timestamp và đường đọc hoàn tất, đây là lý do có thể dựa vào cặp quorum để kỳ vọng **đọc thấy mutation vừa ghi**.

**Không được suy:** đây là bằng chứng Cassandra linearizable cho mọi ghi cạnh tranh, hoặc đọc `ONE` cũng có cùng bảo đảm. Bước 2 chỉ thể hiện một quan sát trên dữ liệu đã kịp lan truyền.

## 6. Thí nghiệm 2 — Dừng một replica và thử từng CL

**Giả thuyết:** Khi `cass3` down, `cass1` và `cass2` còn sống, với RF=3:

- `ONE`, `TWO` và `QUORUM` **có thể** hoàn tất vì còn 2 replica phản hồi.
- `THREE` hoặc `ALL` **không đủ** phản hồi.
- Một thất bại ở `ALL` có thể là `Unavailable` hoặc timeout tùy thời điểm liveness được cập nhật.

### Bước 1 — Dừng đúng replica trong lab

Tại **Terminal C** (shell máy lab, không phải trong `cqlsh`):

```bash
docker compose stop cass3

docker compose exec cass1 nodetool status
```

Đợi cơ chế failure detection phản ánh `cass3` không còn phục vụ, thường `DN` (*Down/Normal*) nếu node vẫn thuộc ring. **Không mặc định một node được đánh dấu DOWN ngay tại thời điểm container vừa dừng.** Khi node vẫn tạm được coi là UP, thao tác có thể timeout trước khi failure detector cập nhật.

### Bước 2 — A ghi ở QUORUM

Tại A:

```sql
CONSISTENCY QUORUM;

UPDATE session_failure_lab.order_state_by_id
SET state = 'PACKED',
    operation_id = 44444444-4444-4444-8444-444444444444,
    updated_at = '2026-11-21 08:10:00+0000'
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Nếu cả `cass1` và `cass2` kịp ACK, ghi **có thể thành công** ở quorum dù `cass3` down. Cassandra không cần mọi replica ACK cho `QUORUM`.

### Bước 3 — B đọc ở QUORUM

Tại B:

```sql
CONSISTENCY QUORUM;

SELECT state, operation_id
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Trong topology này, hai replica khỏe là `cass1` và `cass2`, nên lần đọc `QUORUM` có thể lấy đủ phản hồi. Kết quả mong đợi là `PACKED`. Bước này cho thấy **một replica down không bắt buộc làm ngừng hoạt động của cặp `QUORUM`/`QUORUM` với RF=3**.

### Bước 4 — Thử ALL

Tại A:

```sql
CONSISTENCY ALL;

SELECT state
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

`ALL` cần 3/3 replica. Khi `cass3` down, thao tác **không thể đáp ứng ngưỡng**, nên không trả về một kết quả đọc thành công `ALL`. Tùy thời điểm phát hiện node down, client có thể thấy `Unavailable` hoặc `ReadTimeout`; hãy **ghi loại lỗi thực tế**, không cố “chuẩn hóa” mọi sự cố thành một loại.

Nếu muốn kiểm chứng ở đường ghi `ALL`, hãy dùng **một partition lab mới** (không ghi đè dữ liệu đang dùng làm mốc quan sát), vì một số replica có thể áp dụng mutation dù ghi thất bại ở CL:

```sql
CONSISTENCY ALL;

INSERT INTO session_failure_lab.order_state_by_id
  (order_id, state, operation_id, updated_at)
VALUES (
  55555555-5555-4555-8555-555555555555,
  'ALL_TEST',
  66666666-6666-4666-8666-666666666666,
  '2026-11-21 08:15:00+0000'
);
```

**Dự đoán:** không thể nhận xác nhận ghi `ALL` khi một replica đích đã DOWN; nhưng **không được tự kết luận không replica nào đã nhận mutation** nếu yêu cầu thất bại trong quá trình xử lý.

### Vì sao không đổi RF từ 3 xuống 2 để “cứu” thử nghiệm?

Thay RF sẽ thay **tập replica và ngưỡng quorum**, nên làm mất ý nghĩa so sánh với bước trước. Bài này đo phản ứng khi **node lỗi trên cùng topology**, không phải thử nghiệm reconfiguration. Hãy giữ keyspace RF=3 xuyên suốt các bước.

## 7. Thí nghiệm 3 — Chỉ còn một replica của partition

**Giả thuyết:** Với RF=3 nhưng chỉ `cass1` còn chạy, `ONE` có thể hoàn tất; `QUORUM` và `ALL` không đủ số replica sống.

### Bước 1 — Dừng thêm cass2

Tại Terminal C:

```bash
docker compose stop cass2
docker compose exec cass1 nodetool status
```

Phiên B gắn với `cass2` sẽ mất kết nối; điều đó **không phải bằng chứng dữ liệu biến mất**. Chỉ dùng phiên A trên `cass1` trong giai đoạn này và ghi nhận khi `cass2` được xem là DOWN.

### Bước 2 — Đọc/ghi ở ONE

Tại A:

```sql
CONSISTENCY ONE;

UPDATE session_failure_lab.order_state_by_id
SET state = 'SHIPPED',
    operation_id = 77777777-7777-4777-8777-777777777777,
    updated_at = '2026-11-21 08:20:00+0000'
WHERE order_id = 11111111-1111-4111-8111-111111111111;

SELECT state, operation_id
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Nếu `cass1` khỏe và coordinator xử lý được request, `ONE` có thể thành công. Với chỉ một replica khả dụng, lần đọc tiếp theo cũng có thể lấy giá trị từ `cass1`.

**Tinh tế quan trọng:** dù `R=1, W=1, N=3` nên **`R+W≤N`**, trong **lần chạy cụ thể khi chỉ cass1 sống**, hai tập ACK/phản hồi có thể đều là `{cass1}` và vì thế vẫn giao nhau. Điều kiện `R+W>N` là **điều kiện đủ bảo đảm với mọi tập phản hồi hợp lệ**, không phải điều kiện bắt buộc để có giao nhau trong mọi lần chạy.

### Bước 3 — Kiểm tra QUORUM không còn khả dụng

Tại A:

```sql
CONSISTENCY QUORUM;

SELECT state
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Với RF=3, quorum cần 2 replica. `cass1` là replica duy nhất còn hoạt động nên `QUORUM` **không thể được xác nhận**. Lỗi thực tế thường là `Unavailable` khi failure detector đã cập nhật; vẫn có thể gặp timeout nếu quan sát liveness chưa phản ánh sự cố hoặc replica khác phản hồi trễ.

**Không retry vô hạn hoặc tự hạ CL ở ứng dụng production** chỉ vì lab cho thấy `ONE` còn hoạt động. Hạ từ `QUORUM` xuống `ONE` là thay đổi hợp đồng ACK; nghiệp vụ phải chủ động quyết định có chấp nhận hay không.

## 8. Thí nghiệm 4 — Khôi phục replica và đối chiếu độ mới

**Giả thuyết:** Sau khi hai node trở lại, Cassandra có thể đưa chúng bắt kịp qua đường ghi, hinted handoff và repair, nhưng **không có một thời hạn cố định bảo đảm chúng lập tức đồng nhất**.

### Bước 1 — Khởi động lại các node bị dừng

Tại Terminal C:

```bash
docker compose start cass2 cass3
docker compose exec cass1 nodetool status
```

Đợi `cass1`, `cass2`, `cass3` đều trở lại `UN`. Việc node UP nghĩa là node có thể tham gia ring, **không trực tiếp chứng minh mọi mutation bỏ lỡ đã được nhận đủ**.

### Bước 2 — Mở lại phiên B

Tại Terminal B:

```bash
docker compose exec cass2 cqlsh
```

Trong `cqlsh` của B:

```sql
CONSISTENCY ONE;

SELECT state, operation_id
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

**Kết quả có thể gặp:** `SHIPPED` nếu replica đã bắt kịp hoặc read coordinator chọn replica có dữ liệu mới; cũng có thể có quan sát cũ trong khoảng chưa hội tụ, tùy đường đọc/replication và thời điểm. Chỉ từ việc đọc `ONE` trả `SHIPPED` **không thể kết luận cả ba replica đồng nhất**.

### Bước 3 — Đọc ở QUORUM và quan sát đường sửa sai

Tại A hoặc B:

```sql
CONSISTENCY QUORUM;

SELECT state, operation_id, WRITETIME(state)
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Khi các replica có phiên bản khác nhau, coordinator có thể so sánh **data/digest**, lấy thêm dữ liệu và **reconcile** theo timestamp/tombstone. Tùy phiên bản và cấu hình, đường đọc còn có thể kích hoạt **read repair** cho replica phát hiện không đồng nhất.

**Không gộp ba khái niệm:**

- **Hinted handoff:** giữ và phát lại mutation bị replica bỏ lỡ, trong phạm vi giới hạn cấu hình và **best effort**.
- **Read reconciliation/read repair:** xử lý sai khác được đường đọc phát hiện, thường trong phạm vi dữ liệu được hỏi.
- **Anti-entropy repair:** đối chiếu dữ liệu replica ở phạm vi rộng hơn, dùng trong quy trình vận hành định kỳ/sau sự cố khi cần.

**Compaction** quản lý SSTable và tombstone, **không thay thế anti-entropy repair**. Nếu node down lâu, hint hết hạn hoặc dữ liệu xóa liên quan tombstone, phải xem chiến lược repair và cấu hình `gc_grace_seconds` của phiên bản.

### Bước 4 — Không nhầm đọc được với mọi thao tác ghi trước đó đã thành công

Ở Thí nghiệm 2, một lần ghi `ALL` đã không nhận xác nhận thành công. Sau khi node trở lại, đọc thấy giá trị của ghi đó (nếu có) chỉ cho biết mutation **đã tồn tại/được truyền tới một số replica**; điều này **không biến response `ALL` thất bại trước đó thành một thành công đã ACK**.

## 9. Thí nghiệm 5 — Ghi đồng thời từ hai phiên và quy tắc timestamp

**Mục tiêu:** Chứng minh giao nhau quorum không đồng nghĩa “request gửi sau luôn thắng” hoặc “hai client không thể cùng cập nhật cùng cell”.

### 9.1. Hai lần ghi tuần tự nhưng timestamp đảo ngược

Sử dụng **một partition mới** để không bị ảnh hưởng bởi timestamp của các bước trước. Tại A:

```sql
CONSISTENCY QUORUM;

INSERT INTO session_failure_lab.order_state_by_id
  (order_id, state, operation_id, updated_at)
VALUES (
  88888888-8888-4888-8888-888888888888,
  'VALUE_A',
  99999999-9999-4999-8999-999999999999,
  '2026-11-21 09:00:00+0000'
) USING TIMESTAMP 2000000;
```

Chỉ sau khi A nhận thành công, tại B:

```sql
CONSISTENCY QUORUM;

UPDATE session_failure_lab.order_state_by_id
USING TIMESTAMP 1000000
SET state = 'VALUE_B'
WHERE order_id = 88888888-8888-4888-8888-888888888888;

SELECT state, WRITETIME(state)
FROM session_failure_lab.order_state_by_id
WHERE order_id = 88888888-8888-4888-8888-888888888888;
```

**Kết quả dự kiến:** `state='VALUE_A'` với `WRITETIME(state)=2000000`. Cả hai request có thể đạt `QUORUM`, nhưng Cassandra hòa giải **cell theo timestamp** nên mutation `VALUE_B@1000000` không thắng mutation `VALUE_A@2000000`, dù B được gửi sau theo thời gian thực.

**Chú ý:** `USING TIMESTAMP` nhận đơn vị **microsecond** và các giá trị nhỏ ở đây chỉ dùng với partition hoàn toàn mới trong lab. Không sao chép các timestamp thủ công này vào dữ liệu production; việc tự chọn timestamp bất thường có thể khiến cập nhật hợp lệ về sau không thắng như dự đoán.

### 9.2. Thử cuộc đua kiểm tra-rồi-ghi

Giả sử hai phiên A/B cùng đọc trạng thái `FREE` ở `QUORUM` rồi đều chạy `UPDATE` thường. Hai mutation đều có thể được ACK thành công vì **`SELECT` và `UPDATE` là hai lệnh riêng**, không phải một phép so sánh-và-ghi nguyên tử.

Để thực sự bảo vệ ghế duy nhất, dùng LWT trên cùng partition `seat_key`:

Tại A:

```sql
CONSISTENCY QUORUM;

INSERT INTO session_failure_lab.seat_by_key
  (seat_key, owner_id, operation_id)
VALUES (
  'show-42:A07',
  11111111-1111-4111-8111-111111111111,
  22222222-2222-4222-8222-222222222222
) IF NOT EXISTS;
```

Tại B, thử cùng `seat_key` với khách khác:

```sql
CONSISTENCY QUORUM;

INSERT INTO session_failure_lab.seat_by_key
  (seat_key, owner_id, operation_id)
VALUES (
  'show-42:A07',
  33333333-3333-4333-8333-333333333333,
  44444444-4444-4444-8444-444444444444
) IF NOT EXISTS;
```

**Dự kiến:** với hai request được xử lý thành công và cùng phạm vi Paxos, một lần tạo hàng có `[applied]=true`; request còn lại `[applied]=false` vì khóa đã tồn tại. Nếu thử “đồng thời” thật sự, có thể gặp contention/retry hoặc lỗi, nên không tự suy hai response phải luôn đến đúng cùng lúc.

LWT sử dụng **Paxos**. `SERIAL`/`LOCAL_SERIAL` quy định phạm vi đồng thuận, là một trục khác với normal CL như `QUORUM`/`LOCAL_QUORUM`. Đừng dùng `QUORUM` thường rồi khẳng định nó đã tạo compare-and-set.

## 10. Bật tracing và đọc bằng chứng từ nhiều phiên

Khi cần biết coordinator gửi request/nhận phản hồi ra sao trong **lab**, `cqlsh` hỗ trợ tracing:

```sql
TRACING ON;

CONSISTENCY QUORUM;

SELECT state
FROM session_failure_lab.order_state_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;

TRACING OFF;
```

Trace có thể cho biết coordinator, một số replica được liên hệ, độ trễ và các giai đoạn nội bộ. Dữ liệu tracing phụ thuộc phiên bản, tối ưu đọc, digest, speculative retry và trạng thái cluster:

- **Không được** mặc định một request `QUORUM` luôn gửi đúng hai thông điệp.
- Không được kết luận từ một digest response rằng client đã tải toàn bộ hàng từ replica đó.
- Không dùng trace của **một** lần đọc để suy “`ONE` lúc nào cũng đọc node R3”.
- Không bật tracing tràn lan trên production vì có chi phí và tạo dữ liệu quan sát.

### Mẫu phiếu ghi kết quả

| Lần thử | Coordinator/phiên | Node UP | CL ghi | CL đọc | Dự đoán | Kết quả/loại lỗi thực tế |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | A ghi, B đọc | 3/3 | `QUORUM` | `QUORUM` | Cùng RF=3, có giao nhau. | *Điền sau khi chạy* |
| T2 | A ghi, B đọc | 2/3 | `QUORUM` | `QUORUM` | Có thể thành công. | *Điền sau khi chạy* |
| T3 | A đọc | 2/3 | — | `ALL` | Không đủ phản hồi. | *Điền sau khi chạy* |
| T4 | A ghi/đọc | 1/3 | `ONE` | `ONE` | Có thể thành công trên replica còn khỏe. | *Điền sau khi chạy* |
| T5 | A đọc | 1/3 | — | `QUORUM` | Không đủ phản hồi. | *Điền sau khi chạy* |
| T6 | B sau khôi phục | 3/3 | — | `ONE` | Có thể mới/cũ tùy hội tụ và chọn replica. | *Điền sau khi chạy* |
| T7 | A ghi, B ghi/đọc | 3/3 | `QUORUM` | `QUORUM` | Timestamp lớn thắng trong cell. | *Điền sau khi chạy* |
| T8 | A/B LWT | 3/3 | `QUORUM` + serial | — | Một tạo khóa `[applied]=true`. | *Điền sau khi chạy* |

Để kết luận, hãy đối chiếu **ba thông tin**: *mức phản hồi yêu cầu*, *số replica còn có thể phản hồi*, và *đường đi/timestamp của request*. Một lần chạy cụ thể là **bằng chứng quan sát**, không phải thay thế chứng minh cho mọi lịch sử thao tác.

## 11. Vì sao mất node có thể tạo Unavailable hoặc Timeout?

Khi coordinator nhận request, nó dựa trên liveness/failure detector để đánh giá số replica có thể phục vụ CL. Có hai tình huống khác nhau:

1. **`UnavailableException`:** coordinator đánh giá **không đủ replica được coi là sống** để đáp ứng CL. Ví dụ RF=3, `ALL` khi `cass3` đã được đánh dấu DOWN.
2. **`ReadTimeoutException` / `WriteTimeoutException`:** coordinator đã gửi request hoặc còn xem replica là UP, nhưng **không thu đủ phản hồi hoặc hoàn tất đường dữ liệu trước deadline**.

Ngoài ra có thể gặp:

| Lỗi | Ý nghĩa thực tế cần ghi nhận |
| --- | --- |
| `UnavailableException` | Thiếu replica theo CL, từ góc nhìn coordinator. |
| `ReadTimeoutException` | Chưa hoàn tất điều kiện phản hồi/dữ liệu của đọc đúng hạn. |
| `WriteTimeoutException` | Không được xác nhận đủ ghi theo CL trước deadline; **mutation có thể đã được áp dụng ở một số replica**. |
| `ReadFailureException` / `WriteFailureException` | Replica báo lỗi xử lý request; có thể vẫn có replica khác đã xử lý. |
| `DriverTimeoutException` | Driver hết hạn đợi; server có thể đã hoàn tất nhưng phản hồi không tới client. |
| Mất kết nối với coordinator | Có thể là lỗi mạng/host, không chứng minh tất cả replica đều chết. |

**Đặc biệt với ghi:** không nhận ACK thành công **không chứng minh mutation chưa được ghi**. Retry phải cân nhắc primary key, timestamp, tính idempotent, counter, TTL, LWT và các side effect ngoài Cassandra. Không âm thầm hạ từ `QUORUM` xuống `ONE` rồi mô tả response như một ghi đã đạt quorum.

## 12. Phần mở rộng: hai datacenter và các phạm vi LOCAL

Thí nghiệm Docker ba node ở trên kiểm chứng **ngưỡng trong một DC**; nó không đủ để kết luận về `LOCAL_QUORUM` xuyên DC hoặc `EACH_QUORUM`. Nếu có **một lab riêng gồm sáu node** ở hai DC `dc1` và `dc2`, có thể tiến hành thêm các phép tính/kiểm thử sau.

### 12.1. RF=3+3

```text
dc1: A1 A2 A3  (RF=3)
dc2: B1 B2 B3  (RF=3)

Tổng RF = 6
QUORUM          = floor(6/2)+1 = 4
LOCAL_QUORUM    = 2 tại DC coordinator
EACH_QUORUM ghi = 2 ACK dc1 VÀ 2 ACK dc2
```

| Ghi | Đọc | Dự đoán giao nhau |
| --- | --- | --- |
| `QUORUM` toàn cụm (4) | `QUORUM` toàn cụm (4) | **Có:** `4+4>6`, nếu cùng tập replica. |
| `LOCAL_QUORUM` dc1 (2/3) | `LOCAL_QUORUM` dc1 (2/3) | **Có:** `2+2>3` trong dc1. |
| `LOCAL_QUORUM` dc1 (2/3) | `LOCAL_QUORUM` dc2 (2/3) | **Không bảo đảm:** hai tập khác DC. |
| Ghi `EACH_QUORUM` (2 mỗi DC) | `LOCAL_QUORUM` dc2 (2/3) | **Có:** trong dc2 có quorum ACK ghi và quorum phản hồi đọc. |
| `QUORUM` toàn cụm (4) | `LOCAL_QUORUM` dc1 (2/3) | **Không bảo đảm:** có thể ACK ghi tại A1+B1+B2+B3, đọc từ A2+A3. |

**Thí nghiệm gợi ý:** mở một phiên `cqlsh` tại node ở `dc1`, một phiên tại node ở `dc2`, đặt `CONSISTENCY LOCAL_QUORUM;` riêng trong cả hai. Ghi từ dc1 rồi đọc ngay từ dc2. **Không bảo đảm quan sát stale data**: replication qua WAN có thể rất nhanh. Nếu đọc mới, điều đó chỉ cho thấy **lần chạy ấy** đã nhận được mutation, không làm hai tập local quorum ở khác DC trở thành giao nhau bắt buộc.

### 12.2. Dừng toàn bộ DC xa trong lab riêng

Nếu coordinator ở dc1 và toàn bộ dc2 không liên lạc:

- `LOCAL_ONE`/`LOCAL_QUORUM` trong dc1: có thể thành công khi đủ replica local.
- `QUORUM` của RF=3+3: cần 4/6, dc1 tối đa 3 nên không đủ.
- Ghi `EACH_QUORUM`: thiếu quorum ở dc2, không đủ.
- `ALL`: không đủ.

**Không áp dụng máy móc cho RF lệch.** Nếu `dc1 RF=5` và `dc2 RF=1`, `QUORUM` toàn cục của sáu replica cần 4 và **có thể đạt chỉ tại dc1** khi dc1 còn khỏe. Ghi `EACH_QUORUM` vẫn cần một ACK ở dc2.

### 12.3. Điều kiện cần trước khi mở rộng lab

Xác minh chính xác:

- Keyspace dùng `NetworkTopologyStrategy` với RF từng DC đã khai báo.
- Coordinator của hai phiên thực sự thuộc DC định thử (không suy từ vị trí của terminal).
- Hai truy vấn dùng **cùng partition key** và cùng tập replica được xác định từ topology.
- Trong thời gian thử không bootstrap/decommission, đổi RF, chuyển token hoặc đổi topology.
- Chỉ gây lỗi ở cluster lab đã được phép, có hướng khôi phục và dữ liệu giả.

## 13. Java Driver 4.x: tái tạo các phép thử từ ứng dụng

`cqlsh` giúp quan sát từng câu lệnh, còn Java Driver 4.x thường dùng `PreparedStatement` và `BoundStatement`. Ví dụ sau giả định đã có `CqlSession` kết nối đúng tới cluster lab và cấu hình `local datacenter=dc1`. Với Docker nhiều node, ứng dụng chạy ngoài network container còn cần **contact points/routing có thể kết nối được tới những địa chỉ được Cassandra quảng bá**; chỉ ánh xạ cổng `9042` của một container không bảo đảm Java trên host truy cập được mọi node.

### 13.1. Repo tối giản chọn CL trên mỗi statement

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.time.Instant;
import java.util.UUID;

public final class ConsistencyLabRepository {
    private final CqlSession session;
    private final PreparedStatement write;
    private final PreparedStatement read;

    public ConsistencyLabRepository(CqlSession session) {
        this.session = session;
        this.write = session.prepare(
            "UPDATE session_failure_lab.order_state_by_id " +
            "SET state = ?, operation_id = ?, updated_at = ? WHERE order_id = ?");
        this.read = session.prepare(
            "SELECT state FROM session_failure_lab.order_state_by_id " +
            "WHERE order_id = ?");
    }

    public void writeQuorum(
            UUID orderId, String state, UUID operationId, Instant at) {
        BoundStatement statement = write
            .bind(state, operationId, at, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        try {
            session.execute(statement);
        } catch (UnavailableException e) {
            // Không đủ replica được coi là sống theo CL tại coordinator.
            throw e;
        } catch (WriteTimeoutException | DriverTimeoutException e) {
            // Một số replica có thể đã áp dụng mutation hoặc ACK bị mất.
            // Tầng nghiệp vụ cần đối soát với operationId.
            throw e;
        }
    }

    public String readQuorum(UUID orderId) {
        BoundStatement statement = read.bind(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        try {
            Row row = session.execute(statement).one();
            return row == null ? null : row.getString("state");
        } catch (UnavailableException | ReadTimeoutException e) {
            // Lỗi đọc không phải bằng chứng "không có order".
            throw e;
        }
    }

    public String readOne(UUID orderId) {
        BoundStatement statement = read.bind(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE);

        Row row = session.execute(statement).one();
        return row == null ? null : row.getString("state");
    }
}
```

Trong lab **chỉ một DC RF=3**, `LOCAL_QUORUM` có cùng ngưỡng 2 replica với `QUORUM`, còn `LOCAL_ONE` có ngưỡng 1 như `ONE`. Khi mở rộng sang nhiều DC, cách chọn `LOCAL_*` phải được đánh giá theo **DC coordinator**.

### 13.2. Không chạy hai ghi cạnh tranh rồi kết luận theo thứ tự hoàn tất

Nếu hai thread đồng thời ghi cùng cell bằng `UPDATE` thường, Cassandra có thể ACK cả hai ở quorum rồi hòa giải theo **timestamp**. Muốn kiểm tra bất biến **“chỉ một người tạo được ghế”**, dùng LWT và kiểm tra `[applied]`:

```java
PreparedStatement reserve = session.prepare(
    "INSERT INTO session_failure_lab.seat_by_key " +
    "(seat_key, owner_id, operation_id) VALUES (?, ?, ?) IF NOT EXISTS");

BoundStatement request = reserve.bind(seatKey, ownerId, operationId)
    .setConsistencyLevel(DefaultConsistencyLevel.QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL);

boolean applied = session.execute(request).wasApplied();
```

`SERIAL`/`LOCAL_SERIAL` điều khiển **pha Paxos**, khác normal CL. Nếu LWT timeout, retry có thể trả `[applied]=false` vì lần thử đầu đã tạo hàng; cần kiểm tra **operation ID** trước khi coi người khác đã thắng.

### 13.3. Đánh giá retry cho đúng loại dữ liệu

| Dạng mutation | Đặc điểm khi bị timeout |
| --- | --- |
| `UPDATE` giá trị cố định, khóa và timestamp ổn định | Có thể thiết kế idempotent, nhưng cần xét ghi cạnh tranh. |
| `INSERT` giữ nguyên primary key và event ID | Giúp tránh tạo nhiều hàng cho cùng sự kiện. |
| Counter increment | **Không idempotent**: retry có thể tăng hai lần. |
| Collection append, TTL | Không mặc định an toàn khi retry; cần xét ngữ nghĩa cụ thể. |
| LWT có điều kiện | Cần phân biệt `[applied]=false` với timeout **chưa biết kết quả**. |
| Mutation kèm email/publish event bên ngoài Cassandra | Cần workflow/outbox/deduplication, không chỉ retry database. |

Không tự động hạ `QUORUM` sang `ONE` khi lỗi để đổi lấy response thành công nếu nghiệp vụ vẫn yêu cầu số ACK ban đầu. `setIdempotent(true)` trong driver **chỉ là khai báo** cho retry policy, không tự biến mutation thành idempotent.

## 14. Phân tích kết quả: điều gì được kiểm chứng, điều gì chưa?

Sau lab, hãy tách ba nhóm kết luận.

### 14.1. Có thể kiểm chứng trực tiếp

- Số replica còn sống/được xem là sống trong `nodetool status`.
- `CONSISTENCY` được đặt **riêng** trong các phiên `cqlsh`.
- Thao tác ở `QUORUM` khi còn 2/3 replica **có thể** thành công, `ALL` không đủ ngưỡng.
- Với chỉ 1/3 replica, `ONE` có thể thành công nhưng `QUORUM` không đủ ngưỡng.
- Ghi với timestamp nhỏ hơn có thể không thắng giá trị có timestamp lớn hơn, dù được gửi sau.
- Một LWT `IF NOT EXISTS` thành công sẽ trả kết quả điều kiện theo `[applied]`, khác ghi thường.

### 14.2. Không thể khẳng định chỉ từ một lần quan sát

- “Đọc `ONE` luôn cũ” hoặc “đọc `ONE` luôn mới” — replica được hỏi và replication timing thay đổi.
- “Đọc `QUORUM` luôn là giá trị ghi gần nhất theo thời gian thực” — timestamp và ghi cạnh tranh còn ảnh hưởng kết quả.
- “Ghi bị `WriteTimeout` chắc chắn chưa đến replica nào” — ACK có thể đến muộn hoặc bị mất.
- “Node đã UP nên mọi mutation đã đồng bộ” — hinted handoff/repair có thể còn đang xử lý.
- “Đọc `QUORUM` một lần có nghĩa tất cả replica đã được repair” — phạm vi read repair phụ thuộc phiên bản/cấu hình/truy vấn.
- “Trên lab một DC, `LOCAL_QUORUM` giống `QUORUM` nên trên hai DC cũng vậy” — sai vì phạm vi khác nhau.

### 14.3. Một kết luận phải ghi đủ giả định

Ví dụ câu trả lời tốt:

> Với RF=3 **trong một DC**, topology ổn định, một lần ghi `QUORUM` **đã được xác nhận thành công**, một lần đọc `QUORUM` bắt đầu **sau** ghi, cùng partition và không có mutation cạnh tranh thắng theo timestamp, thì `R+W=2+2>3` buộc tập ACK ghi và tập phản hồi đọc giao nhau. Cassandra reconciliation trên đường đọc cho cơ sở để đọc thấy phiên bản vừa ghi. Điều này **không** chứng minh mọi cập nhật đồng thời là linearizable.

Đây là kiểu phát biểu có thể bảo vệ về mặt kỹ thuật, hơn hẳn câu ngắn “quorum luôn mới”.

## 15. Những bẫy khiến thí nghiệm cho kết luận sai

1. **Chỉ có hai node nhưng cấu hình RF=3**, rồi kỳ vọng kết quả như cluster ba replica khỏe. Hãy kiểm tra `UN` và số replica thực.
2. **Dừng nhầm coordinator đang giữ phiên `cqlsh`**, sau đó coi lỗi mất kết nối là lỗi `QUORUM`. Hai lỗi thuộc những tầng khác nhau.
3. **Dùng node không phải replica của partition** trong cluster có nhiều node hơn RF. Phải xác minh placement.
4. **Không ghi CL riêng ở từng phiên.** `CONSISTENCY QUORUM` ở A không thay đổi CL của B.
5. **Đổi RF trong khi thử node failure.** Điều kiện `N` không còn cố định.
6. **Thấy đọc `ONE` mới rồi kết luận đủ bảo đảm.** Đây chỉ là một quan sát; `R+W≤N` vẫn không bắt buộc giao nhau.
7. **Tắt rồi bật node và cố ép stale read phải xuất hiện.** Hints có thể được phát lại rất nhanh; đọc cũ không phải kết quả tất yếu.
8. **Coi `WriteTimeout` là rollback.** Cassandra không thực hiện rollback toàn bộ những mutation đã tới replica vì client không nhận ACK.
9. **Thử nhiều mutation lên cùng partition nhưng không kiểm soát timestamp.** Last-write-wins có thể che nguyên nhân cần quan sát.
10. **Đánh đồng read repair và compaction/repair toàn cụm.** Đây là những cơ chế khác nhau.
11. **Gây mạng chậm/tắt node trên production.** Thí nghiệm lỗi chỉ hợp lệ trong lab được quản lý.
12. **Dùng retry policy đổi CL âm thầm.** Response đã thay đổi hợp đồng độ mới/ACK mà không ai biết.

## 16. Bài tập mở rộng và đáp án

### Bài 1 — Ngưỡng sau khi một node down

RF=3, `cass3` down, `cass1` và `cass2` hoạt động tốt. `ONE`, `QUORUM`, `ALL` có thể đạt không?

**Đáp án:** `ONE` cần 1 nên có thể; `QUORUM` cần 2 nên có thể; `ALL` cần 3 nên không đạt.

### Bài 2 — Dừng thêm một node

RF=3, chỉ `cass1` còn sống. Tại sao `QUORUM` không thể thành công, nhưng `ONE` có thể?

**Đáp án:** `QUORUM=2` trong ba replica, còn `ONE=1`. Chỉ có một replica đích phản hồi.

### Bài 3 — R+W không lớn hơn N

RF=3, ghi `ONE` và đọc `ONE` đều thành công khi chỉ `cass1` còn sống. Hai tập thực tế có thể giao nhau không?

**Đáp án:** Có, cả hai có thể là `{cass1}`. `R+W>N` là điều kiện **đủ để đảm bảo giao nhau cho mọi tập hợp hợp lệ**, không phải điều kiện cần cho mọi lần chạy.

### Bài 4 — Ghi QUORUM, đọc ONE

RF=3, ghi `QUORUM` thành công ở `R1,R2`, đọc `ONE` từ `R3` chưa bắt kịp. Có thể nhận dữ liệu cũ không?

**Đáp án:** Có. `W=2`, `R=1`, `R+W=3≤3`; hai tập có thể rời nhau.

### Bài 5 — Không thấy stale read

Trong cluster khỏe, bạn chạy một nghìn lần đọc `ONE` sau ghi `QUORUM` mà không thấy dữ liệu cũ. Có thể tuyên bố `ONE` bảo đảm read-after-write không?

**Đáp án:** Không. Kết quả thực nghiệm chỉ cho thấy những lần đã quan sát. Phép tính `2+1≤3` vẫn không bắt buộc giao nhau trong trường hợp xấu nhất.

### Bài 6 — ALL lỗi khi dừng node

Một replica down. Ghi `ALL` trả `Unavailable`. Có chắc tất cả replica còn sống chưa nhận mutation không?

**Đáp án:** Không nên khẳng định theo cách tổng quát. Lỗi cho biết request không được xác nhận đạt CL; trong các đường lỗi/timing khác mutation vẫn có thể đã tới một số replica. Phải phân loại lỗi cụ thể và đối soát.

### Bài 7 — Timeout khác unavailable

Ba replica được đánh dấu UP nhưng một ACK tới quá muộn; với `QUORUM`, lỗi có thể là gì? Nếu coordinator đã biết chỉ một replica UP thì sao?

**Đáp án:** Trường hợp đầu có thể `ReadTimeout`/`WriteTimeout` tùy thao tác; trường hợp sau có thể `Unavailable` vì không đủ hai replica được coi là sống.

### Bài 8 — Local quorum ở hai DC

RF=3+3, ghi `LOCAL_QUORUM` ở dc1 và đọc `LOCAL_QUORUM` ở dc2. Hai thao tác có buộc giao nhau không?

**Đáp án:** Không. Hai tập phản hồi nằm ở hai DC khác nhau, dù mỗi tập đều là đa số local.

### Bài 9 — Ghi EACH_QUORUM

RF=3+3. Ghi `EACH_QUORUM` thành công, đọc `LOCAL_QUORUM` ở dc2 có giao nhau không?

**Đáp án:** Có, ghi đã có ít nhất hai ACK trong dc2 và đọc cần hai phản hồi trong ba replica của dc2; `2+2>3`.

### Bài 10 — QUORUM toàn cụm khi mất DC

RF=5+1, DC có RF=1 down, DC RF=5 vẫn khỏe. Ghi `QUORUM` toàn cụm có thể thành công không?

**Đáp án:** Có thể. Tổng RF=6, global quorum=4 và DC lớn có năm replica. Ghi `EACH_QUORUM` vẫn không đạt vì phải có một ACK từ DC nhỏ.

### Bài 11 — Timestamp đảo thứ tự

Client A ghi `VALUE_A@2000000` rồi client B ghi `VALUE_B@1000000` sau đó, cả hai `QUORUM` thành công. `SELECT` trả gì nếu không có mutation khác?

**Đáp án:** `VALUE_A` do timestamp 2000000 lớn hơn 1000000. Đây không phải vi phạm điều kiện giao nhau quorum.

### Bài 12 — Hai client đặt cùng một ghế

Hai phiên đều chạy `SELECT QUORUM` rồi `UPDATE QUORUM` khi ghế còn trống. Có bảo đảm chỉ một phiên ghi thành công không? Nếu không, giải pháp nào?

**Đáp án:** Không. Cặp đọc-kiểm-tra-ghi không nguyên tử. Dùng `INSERT ... IF NOT EXISTS` (LWT/Paxos) trên cùng `seat_key` và kiểm tra `[applied]`.

### Bài 13 — Khôi phục node và dữ liệu

Hai node vừa khởi động lại và xuất hiện `UN`. `SELECT ONE` thấy `SHIPPED`. Có thể kết luận toàn bộ replica đã có `SHIPPED` không?

**Đáp án:** Không. `ONE` chỉ cần một phản hồi; cần kiểm tra quá trình hội tụ và repair phù hợp nếu muốn đánh giá tình trạng replica rộng hơn.

### Bài 14 — Retry một ghi chưa rõ kết quả

Ghi `QUORUM` bị `WriteTimeout`. Client lập tức sinh một UUID mới rồi ghi lại cùng sự kiện. Rủi ro chính là gì?

**Đáp án:** Lần đầu có thể đã được một số replica áp dụng; retry với UUID mới có thể tạo **hai sự kiện**. Giữ event/operation ID ổn định và thiết kế idempotency/đối soát.

## 17. Dọn dẹp và khôi phục lab

Sau khi hoàn thành, đảm bảo **tất cả node lab** đã được phục hồi trước khi kết thúc:

```bash
docker compose start cass1 cass2 cass3
docker compose exec cass1 nodetool status
```

Nếu môi trường cần giữ lại lab để học tiếp, chỉ thoát `cqlsh` và ghi kết quả. Nếu chắc chắn đây là cụm **tạm, không có dữ liệu quan trọng**, có thể xóa tài nguyên Docker Compose:

```bash
# Chỉ tại đúng thư mục compose.yaml của lab thử nghiệm.
docker compose down

# Chỉ khi chắc chắn muốn xóa cả volumes/dữ liệu lab:
# docker compose down --volumes
```

Không chạy lệnh xóa dữ liệu/volume khi cùng Compose project còn phục vụ bài thực hành của người khác. Việc khởi động lại node không tự thay thế lịch vận hành **anti-entropy repair** nếu có replica down lâu hoặc bỏ lỡ mutation ngoài cửa sổ hint.

## 18. Tổng kết

Thử nghiệm hai phiên `cqlsh` cho thấy **CL là thuộc tính của từng request/phiên**, còn điều kiện thành công phụ thuộc số replica **thực sự có thể phản hồi theo phạm vi CL**. Với một DC RF=3, còn hai replica thì `QUORUM` có thể thành công, `ALL` không đủ ngưỡng; còn một replica thì `ONE` có thể thành công, `QUORUM` không đủ. Khi node phục hồi, dữ liệu có thể hội tụ qua những cơ chế riêng, nhưng **node UP không đồng nghĩa mọi bản sao đã đồng bộ**.

Phép toán **`R+W>N`** giúp chứng minh **giao nhau bắt buộc** giữa tập ACK của **ghi đã thành công** và tập phản hồi của **đọc đã thành công** trên **cùng tập replica**. Nó không khiến đọc `ONE` luôn cũ hay luôn mới, không biến timeout thành rollback và không thay thế LWT cho cập nhật có điều kiện. **Đọc kết quả thí nghiệm đúng nghĩa** là ghi đủ topology, CL, trạng thái node, loại lỗi, timestamp, thứ tự thao tác và giới hạn suy luận.

### Tài liệu tham khảo

- [Apache Cassandra — Dynamo / Tunable Consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): replication, ngưỡng đọc/ghi, coordinator và replica.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT`, `UPDATE`, `SELECT`, `USING TIMESTAMP` và câu lệnh có điều kiện.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `CONSISTENCY` và `TRACING` trong shell.
- [Apache Cassandra — Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff khi replica bỏ lỡ mutation.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): vai trò anti-entropy repair và hội tụ sau node failure.
