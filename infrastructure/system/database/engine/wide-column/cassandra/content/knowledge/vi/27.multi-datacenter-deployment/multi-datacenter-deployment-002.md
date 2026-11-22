# NetworkTopologyStrategy và RF riêng của từng datacenter

## 1. Tại sao Cassandra cần chiến lược sao chép theo từng datacenter?

**Apache Cassandra** là cơ sở dữ liệu wide-column phân tán: partition key được chuyển thành token, token và topology quyết định những node nào giữ bản sao của partition. Với một hệ thống chỉ có một trung tâm dữ liệu (*datacenter*, viết tắt **DC**), việc bố trí replica đã phải cân nhắc khả năng hỏng node và rack. Khi hệ thống phục vụ **nhiều DC**, các yêu cầu còn phức tạp hơn:

- DC gần người dùng cần phục vụ đọc/ghi với độ trễ thấp.
- Một DC có thể mất mạng hoặc ngừng hoạt động mà DC còn lại vẫn phục vụ một phần workload.
- Mỗi DC có số node, năng lực và yêu cầu phục hồi khác nhau.
- Dữ liệu mới có thể chưa đến DC ở xa tại thời điểm client nhận ACK ở DC gần.

`NetworkTopologyStrategy` (**NTS**) là replication strategy được dùng để chỉ định **replication factor (RF) riêng cho từng DC**. Ví dụ `dc1: 3` và `dc2: 2` có nghĩa mỗi partition có mục tiêu **ba full replica tại dc1 và hai full replica tại dc2**, nếu topology đáp ứng được.

**Các câu hỏi trọng tâm trong bài:**

1. NTS sử dụng DC/rack, token và RF để chọn replica như thế nào?
2. RF theo DC khác gì với consistency level như `LOCAL_QUORUM`, `QUORUM` và `EACH_QUORUM`?
3. Khi một DC hỏng hoặc mất liên kết liên DC, ứng dụng còn đọc/ghi được đến đâu?
4. Đổi RF hoặc thêm DC cần làm những gì ngoài việc sửa CQL?
5. Làm sao quan sát topology, thực hành CQL và sử dụng Java Driver đúng phạm vi?

**Mục tiêu học tập:** thiết kế được replication cho hai DC, giải thích các ngưỡng ACK cụ thể, hiểu giới hạn an toàn dữ liệu liên DC, lập checklist triển khai và tránh nhầm NTS với cơ chế repair, streaming hay tự động failover.

**Giả định:** ví dụ dùng full replica thông thường, `Murmur3Partitioner` và tên DC `dc1`/`dc2` trong lab. Hành vi chi tiết của snitch, công cụ quản trị, tham số cấu hình và thuật toán chọn replica có thể khác theo phiên bản Cassandra; không áp dụng lệnh lab trực tiếp lên production.

## 2. Bốn thành phần quyết định nơi một partition được lưu

Hãy nhìn từ khóa dữ liệu tới vị trí vật lý:

~~~mermaid
flowchart TD
    P["Partition key của một row"] --> T["Partitioner tính token"]
    T --> R["Token ring và metadata các node"]
    S["Snitch mô tả DC/rack của từng node"] --> N["NetworkTopologyStrategy"]
    RF["RF theo từng DC của keyspace"] --> N
    R --> N
    N --> A["Replica set tại dc1"]
    N --> B["Replica set tại dc2"]
    A --> C["Các bản sao phục vụ read/write"]
    B --> C
~~~

| Thành phần | Ý nghĩa | Điều không được nhầm |
| --- | --- | --- |
| **Partition key** | Dữ liệu dùng để hash thành token; mọi hàng cùng partition key đi cùng một nhóm replica. | Clustering column không tự chọn DC khác. |
| **Partitioner/token ring** | Cách biểu diễn vị trí các partition trên vòng; ví dụ Murmur3 token. | Token không phải thứ tự thời gian hay ID nghiệp vụ. |
| **Snitch/topology metadata** | Cho Cassandra biết node thuộc DC/rack nào; ảnh hưởng việc bố trí replica và giao tiếp. | Tên `dc1` trong CQL không tự tạo ra DC hoặc rack. |
| **NetworkTopologyStrategy + RF** | Chọn số replica mục tiêu trong **từng DC** và phân bố chúng theo topology. | RF không phải số node phải ACK ở mọi request. |

Với **virtual nodes (vnodes)**, một node có thể sở hữu nhiều token rải trên vòng. Số token không bằng số replica; **RF** mới xác định số node cần giữ một partition trong mỗi DC.

### Ví dụ trực giác với hai DC

Giả sử:

- `dc1`: các node A1, A2, A3, A4.
- `dc2`: các node B1, B2, B3.
- Keyspace có `NetworkTopologyStrategy` với RF `dc1: 3` và `dc2: 2`.

Một partition P có thể được lưu ở **A1, A3, A4** và **B1, B3**. Partition Q có thể được lưu ở các node khác. **Đây là ví dụ minh họa, không phải mapping thực tế**: replica cụ thể phụ thuộc token và topology/rack của cluster.

~~~text
              Datacenter dc1                  Datacenter dc2
        ┌────────────────────────┐       ┌──────────────────────┐
        │ A1  A2  A3  A4        │       │ B1  B2  B3          │
        │  ●       ●   ●        │       │  ●       ●          │
        │  P có 3 replica      │       │  P có 2 replica     │
        └────────────────────────┘       └──────────────────────┘

        Tổng mục tiêu của P = 3 + 2 = 5 full replica.
~~~

**Tổng số node trong DC không bằng RF:** `dc1` có bốn node nhưng partition P chỉ cần ba full replica ở đây. Một node không lưu P vẫn có thể nhận request làm **coordinator** và chuyển yêu cầu tới các replica của P.

## 3. NetworkTopologyStrategy khác SimpleStrategy

Hai chiến lược có cùng mục đích chung là xác định replica, nhưng chúng phù hợp hoàn cảnh khác nhau:

| Tiêu chí | `SimpleStrategy` | `NetworkTopologyStrategy` |
| --- | --- | --- |
| Cấu hình RF | Một RF chung cho keyspace. | RF khai báo riêng theo tên DC, ví dụ `dc1: 3`, `dc2: 2`. |
| Nhận thức về DC/rack | Không phải chiến lược dùng để chủ động tối ưu phân bố replica theo DC/rack. | Dùng topology DC/rack từ snitch trong việc bố trí replica. |
| Phù hợp | Lab/khái niệm đơn giản hoặc trường hợp hạn chế. | Triển khai nhiều DC và thông thường cũng là lựa chọn thực tế cho một DC production. |
| Quản lý khi thêm DC | Không có khai báo RF độc lập theo từng DC. | Có thể khai báo RF cho DC mới và thực hiện quy trình chuyển/đồng bộ dữ liệu. |
| Rủi ro cấu hình | Không kiểm soát bố trí replica theo fault domain như mong muốn. | Sai tên DC/snitch/rack hoặc RF cao hơn năng lực vẫn gây placement/availability xấu. |

NTS ưu tiên phân tán replica giữa các **rack khác nhau khi có thể** trong mỗi DC, nhằm giảm nguy cơ một lỗi rack làm mất nhiều bản sao. Nhưng:

- RF = 3 **không tự tạo ra ba rack**. Nếu DC chỉ có hai rack, Cassandra phải làm việc trong các giới hạn vật lý của topology.
- Cấu hình snitch sai có thể khiến các node được gắn nhầm DC/rack; việc chọn replica theo metadata sai không giải quyết lỗi vật lý.
- RF lớn hơn số node thích hợp trong DC là thiết kế không thỏa được số replica mục tiêu như mong muốn.
- Khi RF hoặc topology thay đổi, cần xác minh **dữ liệu thật** đã đến các replica mới; chỉ nhìn metadata chưa đủ.

**Quy tắc thiết kế:** chọn rack/DC theo những fault domain thực sự độc lập: máy chủ, rack, vùng mạng, nguồn điện hoặc vùng hạ tầng. Các tên DC và rack logic cần phản ánh cách muốn cô lập sự cố.

## 4. CQL: định nghĩa RF riêng cho từng DC

### 4.1. Tạo keyspace NTS

Trong một lab có hai DC đã được đặt tên đúng và có đủ node phù hợp:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_geo
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 2
}
AND durable_writes = true;
~~~

Ý nghĩa của từng thành phần:

| CQL | Ý nghĩa |
| --- | --- |
| `'class': 'NetworkTopologyStrategy'` | Dùng chiến lược replication nhận biết topology. |
| `'dc1': 3` | Mục tiêu ba full replica của mỗi partition ở DC tên **chính xác** là `dc1`. |
| `'dc2': 2` | Mục tiêu hai full replica của mỗi partition ở DC `dc2`. |
| `durable_writes = true` | Bật cơ chế ghi bền mặc định qua commit log; **không** làm RF hoặc CL tăng. |

Tên DC phải khớp tên Cassandra thực sự nhận từ snitch. `dc1`, `DC1` và `us-east` không được coi là cùng tên chỉ vì con người hiểu chúng giống nhau.

**Không chạy `CREATE KEYSPACE` này với kỳ vọng `dc2` sẽ tự xuất hiện.** Nếu DC chưa có node hoặc chưa được cấu hình đúng, các request cần xác nhận từ `dc2` có thể không đáp ứng được. Bước khai báo RF thuộc kế hoạch rollout, không thay thế việc dựng và kết nối các node.

### 4.2. Tạo bảng theo truy vấn

Ví dụ dịch vụ cần lấy sự kiện theo **tài khoản và ngày**:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_geo.events_by_account_day (
    account_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((account_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Partition key `(account_id, event_day)` xác định token; RF NTS của **keyspace** quyết định bộ replica cho **toàn bộ partition** đó ở `dc1` và `dc2`. Clustering columns `event_time`, `event_id` giúp đọc các hàng theo thời gian **trong partition**.

~~~sql
SELECT event_time, event_id, payload
FROM telemetry_geo.events_by_account_day
WHERE account_id = 'acct-7'
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Đây là đọc **một partition** theo query-driven data modeling. NTS thay đổi **vị trí các replica**, không biến truy vấn thiếu partition key thành phép quét rẻ.

### 4.3. Xem replication hiện có

Trong `cqlsh`:

~~~sql
DESCRIBE KEYSPACE telemetry_geo;
~~~

`DESCRIBE` là lệnh hỗ trợ của **cqlsh**. Để xem metadata bằng CQL:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'telemetry_geo';
~~~

Kết quả hiển thị mapping replication và RF theo DC; nó **không chứng minh** các SSTable của toàn bộ dữ liệu cũ đã được streaming tới node mới.

## 5. RF theo DC và ngưỡng consistency level

Điểm then chốt: **replication factor (RF)** và **consistency level (CL)** có vai trò khác nhau.

- RF cho biết **bao nhiêu replica mục tiêu** được bố trí ở mỗi DC.
- CL quyết định **bao nhiêu phản hồi replica** coordinator phải nhận trước khi trả thành công cho một read/write.
- Với `NetworkTopologyStrategy`, các CL có tiền tố **`LOCAL_`** tính ngưỡng tại **DC cục bộ của coordinator/request**; không có nghĩa dữ liệu chỉ được gửi tới DC đó.

### 5.1. Tính ngưỡng khi `dc1: 3`, `dc2: 2`

Keyspace có mục tiêu tổng **5 full replica** cho mỗi partition.

| CL | Nếu coordinator ở `dc1` | Nếu coordinator ở `dc2` | Điều kiện cốt lõi |
| --- | --- | --- | --- |
| `ONE` | 1 replica phù hợp (không nhất thiết chỉ `dc1`) | 1 replica phù hợp | Một phản hồi. |
| `LOCAL_ONE` | 1 replica ở `dc1` | 1 replica ở `dc2` | Một phản hồi **trong local DC**. |
| `LOCAL_QUORUM` | `floor(3/2)+1 = 2` ở `dc1` | `floor(2/2)+1 = 2` ở `dc2` | Quorum **riêng của local DC**. |
| `QUORUM` | 3 trong tổng 5 replica | 3 trong tổng 5 replica | Quorum trên **toàn bộ replica**, không ép mỗi DC có quorum riêng. |
| `EACH_QUORUM` (**write**) | 2 ở `dc1` **và** 2 ở `dc2` | Như nhau | Quorum tại **từng DC được replication**. |
| `ALL` | 5 | 5 | Toàn bộ năm full replica phản hồi. |

**Vì sao `LOCAL_QUORUM` ở `dc2` vẫn cần 2 ACK?** Với RF = 2, quorum theo công thức `floor(2/2)+1 = 2`; một replica `dc2` hỏng làm request tại `LOCAL_QUORUM` ở DC này không đạt quorum. Không phải mọi DC đều chịu được một node hỏng chỉ vì chọn `LOCAL_QUORUM`.

**Vì sao `QUORUM` không đồng nghĩa `EACH_QUORUM`?** Tổng RF = 5 nên `QUORUM` cần **3** ACK. Chẳng hạn cả ba ACK có thể đến từ `dc1`, còn `dc2` chưa có ACK. `EACH_QUORUM` cho write cần **2 ACK ở từng DC**, tổng ít nhất bốn phản hồi với cấu hình này.

### 5.2. Ví dụ write ở DC1 khi DC2 đang chậm

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng ở dc1
    participant C as Coordinator dc1
    participant A1 as dc1: A1
    participant A2 as dc1: A2
    participant A3 as dc1: A3
    participant B as dc2 replicas
    App->>C: INSERT, CL=LOCAL_QUORUM
    C->>A1: Mutation
    C->>A2: Mutation
    C->>A3: Mutation
    C->>B: Gửi tới remote replicas
    A1-->>C: ACK
    A2-->>C: ACK
    C-->>App: Success: 2/3 ACK ở dc1
    Note over B: Có thể chưa nhận/áp dụng khi client thấy success
~~~

Các thao tác ghi thông thường được phối hợp tới tập replica phù hợp, nhưng **ACK thành công ở `LOCAL_QUORUM` không đợi quorum remote**. Nếu `dc1` mất hoàn toàn ngay sau khi trả success và trước khi mutation đến `dc2`, không thể khẳng định `dc2` đã có bản ghi ấy.

### 5.3. Giao nhau của quorum chỉ có nghĩa khi xét cùng nhóm replica

Trong **một DC** có RF = 3, read/write `LOCAL_QUORUM` đều cần hai replica. Do `2 + 2 > 3`, tập replica đã ACK write và tập tham gia read phải giao nhau, **nếu** cùng partition/nhóm replica và các giả định về trạng thái dữ liệu, timestamp, không có ghi cạnh tranh và lỗi còn trong giới hạn.

Nhưng write `LOCAL_QUORUM` ở `dc1` và read `LOCAL_QUORUM` ở `dc2` thuộc **hai tập replica khác nhau**: **không có giao nhau bắt buộc**. Đây là một nguyên nhân có thể xảy ra **stale read liên DC**, ngay cả khi cả hai phía đều dùng CL tên là QUORUM.

CL không tạo transaction serializable xuyên nhiều partition, không giải quyết tự động xung đột ghi đồng thời và không có nghĩa mọi replica đã được sửa sai lệch. Những chức năng đó phải được xử lý ở mô hình dữ liệu, logic ứng dụng và quy trình repair thích hợp.

## 6. Khi một node, rack hoặc cả DC bị lỗi

NTS bố trí nhiều bản sao theo DC/rack để tăng khả năng phục hồi, nhưng **tính sẵn sàng phụ thuộc CL**.

### 6.1. Tình huống RF `dc1: 3`, `dc2: 2`

| Sự cố | Ứng dụng ở `dc1`, CL `LOCAL_QUORUM` | Ứng dụng ở `dc2`, CL `LOCAL_QUORUM` | `EACH_QUORUM` write |
| --- | --- | --- | --- |
| Một replica của partition ở `dc1` không khả dụng | Có thể thành công nếu còn 2 replica dc1 phản hồi. | Có thể thành công nếu còn 2 replica dc2 phản hồi. | Có thể thành công nếu đủ 2 ở dc1 và 2 ở dc2. |
| Một replica của partition ở `dc2` không khả dụng | Có thể thành công nếu dc1 còn tối thiểu 2 replica phản hồi. | **Không đủ quorum dc2** (chỉ còn 1/2). | **Không đủ** 2 ACK dc2. |
| Toàn bộ `dc2` không khả dụng | Vẫn có thể thành công nếu dc1 còn tối thiểu 2 replica phản hồi. | Không thể đạt local quorum tại dc2. | Không thể đạt quorum dc2. |
| Toàn bộ `dc1` không khả dụng | Không thể phục vụ local quorum tại dc1. | Có thể thành công nếu 2 replica dc2 phản hồi. | Không thể đạt quorum dc1. |

Đây là mô hình ngưỡng ACK, không phải lời bảo đảm dữ liệu remote đã nhận đủ những write vừa thành công tại local DC. Khả năng chịu lỗi rack còn phụ thuộc replica có thực sự được bố trí trên rack độc lập và tổng số node/rack.

### 6.2. Availability khác durability và RPO

- **Availability:** hiện tại có đủ replica sống để đáp ứng CL của request không?
- **Durability:** mutation đã xác nhận có còn trên thiết bị lưu trữ/replica còn sống sau sự cố không?
- **RPO (Recovery Point Objective):** khi phải phục vụ từ DC dự phòng, có thể mất tối đa bao nhiêu dữ liệu mới nhất theo mục tiêu nghiệp vụ?
- **RTO (Recovery Time Objective):** cần bao lâu để chuyển tải, kiểm tra tính nhất quán và khôi phục khả năng phục vụ?

Một hệ thống chọn `LOCAL_QUORUM` vì độ trễ thấp và khả năng phục vụ khi remote DC đứt kết nối phải **chấp nhận rằng ACK local không tương đương xác nhận đã ghi ở DC dự phòng**. Nếu nghiệp vụ đòi bằng chứng đã được xác nhận tại cả hai DC, write CL như `EACH_QUORUM` có thể phù hợp hơn nhưng làm tính sẵn sàng phụ thuộc liên kết liên DC và replica ở cả hai bên.

**RF không thay backup.** Xóa nhầm dữ liệu hoặc mutation sai có thể được sao chép tới mọi DC; cần snapshot/backup, khả năng restore và runbook phục hồi thảm họa.

## 7. Chọn RF theo DC: không phải “càng nhiều càng tốt”

### 7.1. Ba ví dụ thiết kế

| Thiết kế | Trường hợp cân nhắc | Lợi ích | Đánh đổi |
| --- | --- | --- | --- |
| `dc1: 3`, `dc2: 3` | Hai DC có vai trò phục vụ chủ động và muốn quorum chịu được một replica lỗi ở mỗi DC | `LOCAL_QUORUM = 2` tại cả hai DC; thuận tiện khi cần chuyển lưu lượng | Tổng sáu bản sao, tăng chi phí lưu trữ/ghi/repair. |
| `dc1: 3`, `dc2: 2` | DC chính lớn hơn, DC phụ có năng lực khác và chấp nhận quorum ở DC phụ cần cả hai replica | Giảm một bản sao ở DC phụ | `LOCAL_QUORUM = 2` tại dc2, không chịu được lỗi một replica của partition. |
| `dc1: 3`, `dc2: 1` | Chỉ có một bản sao ở DC phụ cho mục đích hạn chế, không coi là kiến trúc HA đầy đủ | Ít bản sao và chi phí hơn | Mất node dc2 có thể khiến dữ liệu không còn replica tại dc2; local quorum tại dc2 cần 1 nhưng không có dự phòng trong DC. |

Không lựa chọn RF chỉ bằng số lượng server:

1. **Số full replica mong muốn trong từng DC** phải phù hợp khả năng chịu lỗi.
2. **Số rack/fault domains** phải phản ánh lỗi chung dự kiến; RF = 3 trên ba node cùng một rack khác RF = 3 phân tán được trên nhiều rack.
3. **Sức chứa:** mỗi replica thêm dung lượng dữ liệu, write I/O, repair và streaming.
4. **CL ứng dụng:** RF = 2 đi với `LOCAL_QUORUM` có tính sẵn sàng khác RF = 3.
5. **Nhu cầu data residency:** không sao chép sang DC không được phép; tuy nhiên lưu trữ, đường truyền, backup và truy vấn còn cần kiểm soát riêng.

### 7.2. Quy tắc gần đúng về độ bền và chi phí

Nếu tổng dữ liệu logic là **D byte**, các bản sao lý tưởng có thể tạo tải lưu trữ xấp xỉ **D × tổng RF** trên toàn bộ DC trước khi tính SSTable overhead, compaction, snapshot, tombstone và cách phân bố. Đây chỉ là ước lượng lập kế hoạch, **không phải số byte disk chính xác**.

Tăng RF không làm một câu `SELECT` tự đọc nhanh hơn. Đọc một partition vẫn cần thiết kế partition key tốt, giới hạn clustering range, kiểm soát kích thước partition và consistency level phù hợp. Việc có nhiều replica có thể hỗ trợ cân bằng tải hoặc chịu lỗi, nhưng cũng phát sinh thêm công việc bảo trì.

## 8. Thực hành CQL: hai cách ghi và các ACK khác nhau

Trên lab có đủ replica ở cả hai DC:

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

INSERT INTO telemetry_geo.events_by_account_day
  (account_id, event_day, event_time, event_id, payload)
VALUES
  ('acct-7', '2026-11-21', '2026-11-21T03:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'registered');

TRACING OFF;
~~~

Trong `cqlsh` kết nối tới coordinator ở `dc1`, `LOCAL_QUORUM` cần hai ACK tại `dc1`. Nếu coordinator thuộc `dc2`, cùng từ khóa đó yêu cầu hai ACK tại `dc2` vì RF dc2 = 2.

Để minh họa một write chờ quorum **ở mỗi DC**:

~~~sql
CONSISTENCY EACH_QUORUM;
TRACING ON;

INSERT INTO telemetry_geo.events_by_account_day
  (account_id, event_day, event_time, event_id, payload)
VALUES
  ('acct-7', '2026-11-21', '2026-11-21T03:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'verified');

TRACING OFF;
~~~

`EACH_QUORUM` ở đây là **CL cho write**, yêu cầu hai ACK từ `dc1` **và** hai ACK từ `dc2`. Nếu một replica dc2 không khả dụng, write có thể thất bại tại CL này, dù cùng write ở `LOCAL_QUORUM` dc1 có thể đã thành công.

Trả CL về chế độ phục vụ read phù hợp:

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, event_id, payload
FROM telemetry_geo.events_by_account_day
WHERE account_id = 'acct-7'
  AND event_day = '2026-11-21';
~~~

`CONSISTENCY` và `TRACING` là **lệnh của cqlsh**, không phải CQL gửi nguyên văn qua Java Driver. Trace có thể giúp quan sát coordinator, endpoint và hành vi giao tiếp; **một trace thành công không chứng nhận mọi replica trong các DC đã hội tụ**.

## 9. Java Driver 4.x: local DC và CL trên statement

Trong Apache Cassandra Java Driver 4.x, ứng dụng thường khai báo **local datacenter** để driver ưu tiên node cục bộ và quản lý đường kết nối. Nó **không** đồng nghĩa replication strategy hoặc RF của keyspace được đổi trong ứng dụng.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class MultiDatacenterEvents {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO telemetry_geo.events_by_account_day " +
                "(account_id, event_day, event_time, event_id, payload) " +
                "VALUES (?, ?, ?, ?, ?)");

            BoundStatement write = insert.bind(
                    "acct-7",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T03:02:00Z"),
                    UUID.fromString("123e4567-e89b-42d3-a456-426614174003"),
                    "confirmed")
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
            session.execute(write);

            PreparedStatement select = session.prepare(
                "SELECT event_time, event_id, payload " +
                "FROM telemetry_geo.events_by_account_day " +
                "WHERE account_id = ? AND event_day = ?");

            BoundStatement read = select.bind(
                    "acct-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(read)) {
                System.out.println(row.getInstant("event_time")
                    + " -> " + row.getString("payload"));
            }
        }
    }
}
~~~

**Giải thích từng quyết định:**

1. `withLocalDatacenter("dc1")` chỉ định DC cục bộ của driver. Tên phải khớp DC trong cluster; `127.0.0.1` chỉ minh họa lab, không phải contact point production.
2. Prepared statement có đầy đủ partition key kép `(account_id, event_day)`, giúp driver tính routing key để ưu tiên replica phù hợp khi token-aware routing được hỗ trợ.
3. `LOCAL_QUORUM` cho write/read yêu cầu đủ **2/3 ACK ở dc1** với RF `dc1: 3`. Nó không chờ quorum ở `dc2`.
4. Khi ứng dụng thật được triển khai tại `dc2`, nó nên dùng cấu hình kết nối/local DC tương ứng; `LOCAL_QUORUM` ở đây yêu cầu **2/2** replica dc2.
5. **Driver không tự biến request sang remote DC thành failover an toàn** chỉ vì cluster có replication ở đó. Chuyển DC cần thiết kế routing, kết nối, CL, quan sát độ trễ/staleness và quy trình ứng dụng cụ thể.
6. Với write timeout, một số replica có thể đã áp dụng mutation; retry phải cân nhắc idempotency, khóa sự kiện ổn định và xung đột timestamp.

Muốn bảo đảm một **write** được ACK ở cả hai DC (với chi phí tương ứng), có thể cân nhắc `DefaultConsistencyLevel.EACH_QUORUM` cho statement ghi khi phiên bản/cluster hỗ trợ. **Không dùng EACH_QUORUM như CL đọc thông thường.**

### 9.1. Active-active: cùng một khóa được ghi từ hai DC

Cassandra không cung cấp transaction serializable tự động cho mọi phép `UPDATE` ở nhiều DC. Các phiên bản mutation được hòa giải theo write timestamp và tombstone; **ghi từ hai DC vào cùng một cell** có thể có xung đột hoặc kết quả không đúng với thứ tự người dùng kỳ vọng, đặc biệt khi đồng hồ lệch hoặc ứng dụng tự cấp timestamp.

Đối với nghiệp vụ quan trọng:

- Chọn **khóa sự kiện/idempotency key** để retry không vô tình nhân bản hoặc ghi đè dữ liệu.
- Tránh mô hình **read-modify-write** không đồng bộ khi nhiều writer cùng sửa một giá trị.
- Xác định quy tắc **phân quyền ghi**, thứ tự, partition ownership logic hoặc công cụ điều kiện phù hợp với yêu cầu.
- Đối với dữ liệu cần nhất quán mạnh/điều kiện, nghiên cứu cơ chế LWT với giới hạn và chi phí của nó thay vì chỉ tăng CL thông thường.

## 10. Thêm DC mới hoặc thay RF: thay metadata chưa phải xong

Giả sử đang có `dc1: 3` và tổ chức muốn thêm `dc2: 2`. Có hai lớp công việc:

1. **Topology vật lý:** triển khai node ở dc2, cấu hình snitch/rack đúng, kết nối mạng và bảo mật, bảo đảm node gia nhập cluster ổn định.
2. **Replication dữ liệu:** cập nhật RF của keyspace, chuyển/đồng bộ dữ liệu tới các replica mới, xác nhận dữ liệu và tombstone được bảo toàn.

Một câu CQL đổi replication metadata:

~~~sql
ALTER KEYSPACE telemetry_geo
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

Ví dụ đổi RF của dc2 từ 2 lên 3 **chỉ cập nhật mục tiêu bố trí replica**. Nó không bảo đảm một full replica thứ ba ở dc2 đã nhận tất cả partition/tombstone cũ. Cần làm theo quy trình được phê duyệt cho phiên bản Cassandra: kiểm tra đủ node, streaming/rebuild/repair đúng phạm vi, xác minh kết quả và điều chỉnh lịch bảo trì.

**Một chuỗi rollout an toàn ở mức khái niệm:**

1. **Đánh giá trước thay đổi:** dung lượng, băng thông WAN, RF hiện tại, rack/DC, client CL, backup/restore và giới hạn lỗi.
2. **Chuẩn bị DC/nodes:** snitch trả về đúng DC/rack; liên kết cluster, xác thực/TLS và firewall phù hợp.
3. **Lập kế hoạch thay RF:** chọn thời điểm, thứ tự tạo DC và cập nhật keyspace theo hướng dẫn phiên bản; dự đoán availability khi RF mục tiêu chưa có đủ replica.
4. **Đưa dữ liệu tới replica mới:** theo dõi streaming/rebuild/repair đúng keyspace và DC; đừng suy từ `ALTER KEYSPACE` rằng dữ liệu đã đầy đủ.
5. **Kiểm chứng:** topology ổn định, token ownership phù hợp, đọc dữ liệu mẫu tại từng DC, xác nhận repair/missing data/tombstone theo quy trình.
6. **Điều chỉnh ứng dụng:** local DC, CL, route/failover, timeout và giám sát liên DC; rollout dần với traffic kiểm soát.
7. **Dọn dữ liệu cũ nếu cần:** sau khi replica mới an toàn và ownership thay đổi, xem xét cleanup ở node không còn trách nhiệm giữ dữ liệu. Không xóa dữ liệu thủ công trước khi streaming hoàn tất.

### Cảnh báo khi giảm RF hoặc loại bỏ DC

Giảm RF có thể làm mất bản sao dự phòng. Xóa một DC khỏi metadata trước khi đảm bảo dữ liệu được lưu tại nơi còn lại, hoặc chạy cleanup quá sớm, có thể gây thiếu dữ liệu/giảm khả năng chịu lỗi. Đây phải là thay đổi có kế hoạch **chuyển dữ liệu, bảo vệ tombstone, kiểm tra replica và phục hồi**, không chỉ là sửa một dòng CQL.

## 11. Repair, hinted handoff và bảo vệ dữ liệu xóa giữa các DC

**NTS quyết định bản sao phải tồn tại ở đâu; nó không tự bảo đảm mọi bản sao luôn giống nhau.**

| Cơ chế | Mục đích | Giới hạn trong multi-DC |
| --- | --- | --- |
| **Ghi theo CL** | Quyết định số replica ACK trước khi client thấy success | `LOCAL_QUORUM` không đợi remote quorum. |
| **Hinted handoff** | Tạm ghi nhận một số mutation bị bỏ lỡ để chuyển lại replica | Có giới hạn thời gian/cấu hình; không thay thế repair nếu DC offline lâu. |
| **Read repair** | Đối chiếu/sửa dữ liệu bị lệch trong phạm vi được đọc, tùy phiên bản | Read local không buộc sửa mọi partition ở remote DC. |
| **Anti-entropy repair** | Đối chiếu những vùng token giữa các replica tham gia | Cần kế hoạch bao phủ **đúng DC/replica** và theo dõi hoàn tất. |
| **Compaction** | Hợp nhất SSTable và purge dữ liệu đủ điều kiện trên từng node | Không truyền mutation sang DC khác. |
| **Backup/snapshot** | Cung cấp lịch sử để restore khi xóa sai/hỏng hàng loạt | Không đồng nghĩa remote replicas đã nhận write mới nhất. |

### 11.1. Tombstone và `gc_grace_seconds`

Giả sử `dc2` mất kết nối dài ngày. Một `DELETE` thành công tại `LOCAL_QUORUM` của `dc1` có thể **chưa tới** những replica ở dc2. Nếu tombstone ở các replica đã nhận được purge trước khi DC bị lỡ delete được đồng bộ an toàn, dữ liệu cũ có nguy cơ xuất hiện lại (*zombie data*).

`gc_grace_seconds` liên quan tới thời gian bảo vệ tombstone; **nó không tự chạy repair**. Việc vận hành cần bảo đảm repair/khôi phục các DC sau sự cố, xử lý replica offline quá hạn và không giảm grace tùy tiện chỉ vì dung lượng đĩa.

### 11.2. Local repair và cross-DC repair không giống nhau

Chạy các tác vụ repair **chỉ trong dc1** có thể giúp hội tụ giữa các replica dc1, nhưng **không chứng minh dc2 đã nhận mọi update/delete**. Khi lập lịch, phải kiểm tra các tùy chọn phạm vi `-local`, `-dc`, `-hosts` và chiến lược repair của **phiên bản đang sử dụng**; tính rõ những DC/replica nào tham gia, yêu cầu truyền dữ liệu và việc bảo vệ tombstone.

Repair xuyên DC có thể dùng nhiều băng thông, CPU và I/O; cần theo dõi kết quả, không chỉ dựa vào việc lệnh `nodetool repair` đã được khởi chạy.

## 12. Quan sát và chẩn đoán topology thực tế

### 12.1. Các lệnh `nodetool` thường dùng

Trên node Cassandra có quyền vận hành trong lab/staging:

~~~bash
nodetool status
nodetool ring
nodetool netstats
nodetool compactionstats
~~~

- `status`: xem node đang `UN`/down/joining, tên DC/rack và các thông tin topology.
- `ring`: quan sát token ownership, nhất là khi dùng vnodes.
- `netstats`: theo dõi streaming/reception khi thao tác thay đổi topology hoặc chuyển dữ liệu.
- `compactionstats`: nhận biết công việc nền có thể tranh I/O với repair/streaming.

Với partition key kép, việc xác định natural endpoints chính xác cần sử dụng công cụ/topology metadata đúng schema và partitioner. `nodetool ring` cho cái nhìn các dải token, nhưng **không phải bằng chứng mọi SSTable đã được đồng bộ** sau khi tăng RF.

### 12.2. Checklist chẩn đoán khi read ở DC2 khác DC1

1. **Kiểm tra keyspace:** `system_schema.keyspaces` có khai báo RF đúng tên các DC không?
2. **Kiểm tra snitch:** node nào đang được gắn `dc1`/`dc2` và rack nào, có nhầm tên/cấu hình không?
3. **Kiểm tra CL và coordinator:** request thực sự dùng `LOCAL_ONE`, `LOCAL_QUORUM` hay `QUORUM`? Driver đang chọn local DC nào?
4. **Kiểm tra replica health:** node down, network partition, pending streaming, write timeout, hints/repair thất bại?
5. **Kiểm tra timestamp và ghi đồng thời:** hai DC có thể ghi khác nhau vào cùng khóa; không chỉ do replication chậm.
6. **Kiểm tra repair scope:** các token ranges và DC tham gia repair đã được xác minh hoàn tất chưa?
7. **Kiểm tra delete/TTL:** tombstone có được đồng bộ trước khi purge; có replica offline quá hạn hay không?

**Không chữa mọi sai khác bằng cách tăng RF, tăng CL hoặc ép compaction.** Mỗi công cụ giải quyết một lớp vấn đề khác nhau; trước hết cần xác định phần nào của write/replication/repair đã thiếu.

## 13. Lỗi suy luận thường gặp

| Nhận định | Kết luận | Giải thích |
| --- | --- | --- |
| “`dc1: 3, dc2: 2` nghĩa Cassandra lấy ngẫu nhiên năm node bất kỳ.” | **Sai** | RF được thực hiện **theo từng DC** dựa vào token/rack/topology. |
| “Nếu cluster có 10 node tại dc1 thì mỗi partition có 10 replica.” | **Sai** | RF dc1 mới là số replica mục tiêu, không phải số node của DC. |
| “`LOCAL_` nghĩa commit log đã fsync tại node.” | **Sai** | `LOCAL_` chỉ phạm vi DC của CL, không phải cơ chế local durability. |
| “`LOCAL_QUORUM` luôn chịu được lỗi một node.” | **Sai** | Với RF dc2 = 2, cần cả hai replica để đạt local quorum. |
| “`QUORUM` = `EACH_QUORUM`.” | **Sai** | Quorum tổng có thể đến từ một DC; EACH_QUORUM write đòi quorum từng DC. |
| “Write thành công tại dc1/LOCAL_QUORUM nghĩa dc2 đã có write đó.” | **Sai** | Không phải chờ remote ACK. |
| “NTS tự repair mọi replica lệch sau mất mạng.” | **Sai** | Cần cơ chế hội tụ và repair/khôi phục thích hợp. |
| “Đổi `ALTER KEYSPACE` sang RF cao là đủ để có bản sao mới.” | **Sai** | Phải chuyển và xác minh dữ liệu cũ trên replica mới. |
| “Tăng RF làm CQL quét toàn bảng rẻ hơn.” | **Sai** | RF không thay thiết kế partition key hay chi phí query. |
| “Hai DC có nhiều replica là không cần backup.” | **Sai** | Xóa nhầm/corruption có thể lan truyền; backup phục vụ mục tiêu khác. |

## 14. Bài tập tự kiểm tra có đáp án

**Bài 1.** Keyspace có `NetworkTopologyStrategy`, `dc1: 3`, `dc2: 2`. Mỗi partition có mục tiêu bao nhiêu full replica toàn cluster, giả sử đủ node?

**Đáp án:** **Năm full replica**, gồm ba tại dc1 và hai tại dc2. Không tính node chỉ làm coordinator là replica bổ sung.

**Bài 2.** Với RF `dc1: 3`, `dc2: 2`, write `EACH_QUORUM` cần bao nhiêu ACK?

**Đáp án:** **Hai tại dc1 và hai tại dc2**, tổng ít nhất bốn ACK, không phải ba ACK bất kỳ.

**Bài 3.** Một node là replica của partition ở dc2 bị down, còn lại một replica dc2. Ứng dụng tại dc2 dùng `LOCAL_QUORUM`. Write có thể thành công không?

**Đáp án:** **Không đạt `LOCAL_QUORUM` dc2** vì RF dc2 = 2 nên quorum yêu cầu cả hai replica. Tùy yêu cầu nghiệp vụ, hạ CL có thể tăng availability nhưng thay đổi cam kết nhất quán, không phải sửa sự cố node.

**Bài 4.** Ghi tại dc1 `LOCAL_QUORUM` đã thành công, ngay sau đó đọc tại dc2 `LOCAL_QUORUM` không thấy giá trị. Có mâu thuẫn với công thức `R + W > RF` không?

**Đáp án:** **Không.** Hai local quorum được tính trên **hai tập replica ở hai DC khác nhau**; không có giao nhau bắt buộc. Cần xét độ trễ truyền mutation, sức khỏe DC, repair và write cạnh tranh.

**Bài 5.** Đổi RF của dc2 từ 2 thành 3 rồi lập tức cho ứng dụng đọc tại `LOCAL_QUORUM`. Có thể khẳng định replica thứ ba chứa đủ lịch sử dữ liệu không?

**Đáp án:** **Không.** RF metadata mới không tự stream toàn bộ dữ liệu cũ. Cần quy trình transfer/rebuild/repair và xác minh đúng phạm vi trước khi tin tưởng topology mới.

**Bài 6.** Tại sao RF = 3 ở một DC có ba node nhưng chỉ một rack vẫn chưa phải kiến trúc chịu lỗi rack tốt?

**Đáp án:** Vì cả ba node cùng phụ thuộc một fault domain. Nếu rack/mạng/nguồn chung lỗi, nhiều replica có thể mất đồng thời. Cần bố trí rack và snitch phản ánh fault domain thật.

**Bài 7.** Khi remote DC đã offline lâu hơn thời gian có thể lưu hint, có thể chỉ bật lại DC và trông chờ hints đầy đủ?

**Đáp án:** **Không.** Hints có giới hạn. Cần đánh giá repair/rebuild theo runbook, đặc biệt các tombstone và thời gian `gc_grace_seconds`, trước khi xem dữ liệu đã hội tụ.

**Bài 8.** Hai ứng dụng tại hai DC cùng sửa `account_id='acct-7'` với timestamp không đáng tin. Chỉ đổi write CL thành `EACH_QUORUM` có ngăn lost update không?

**Đáp án:** **Không.** CL điều khiển ngưỡng ACK, không biến read-modify-write thành giao dịch cách ly. Phải xem xét mô hình dữ liệu, đồng hồ/timestamp, idempotency và cơ chế điều kiện thích hợp.

## 15. Sơ đồ quyết định cấu hình NTS

~~~mermaid
flowchart TD
    A["Ứng dụng cần Cassandra nhiều DC"] --> B["Xác định fault domains, rack/DC và RPO/RTO"]
    B --> C["Chọn RF riêng cho từng DC theo chịu lỗi và capacity"]
    C --> D["Kiểm tra snitch, token map và số node/rack"]
    D --> E{"Có DC mới hoặc thay RF?"}
    E -->|Có| F["Lên kế hoạch streaming/rebuild/repair và xác minh"]
    E -->|Không| G["Giữ topology, giám sát replica"]
    F --> H["Chọn CL cho workload và failover"]
    G --> H
    H --> I{"Chỉ cần local ACK hay cả remote ACK?"}
    I -->|Local| J["LOCAL_QUORUM/LOCAL_ONE theo mục tiêu"]
    I -->|Mỗi DC| K["Cân nhắc EACH_QUORUM cho write"]
    J --> L["Giám sát latency, dữ liệu remote, repair và backup"]
    K --> L
~~~

**Ghi nhớ cốt lõi:** `NetworkTopologyStrategy` xác định **bao nhiêu replica của một partition được bố trí trong từng DC**; `LOCAL_QUORUM`, `QUORUM`, `EACH_QUORUM` quyết định **những replica nào phải xác nhận trước khi client thấy thành công**. Cấu hình RF không tự stream dữ liệu cũ, local ACK không thay cross-DC ACK, và replication không thay repair hay backup. Một hệ thống multi-DC đúng cần đồng thời thiết kế **partition key, topology/rack, RF per-DC, CL, cơ chế đồng bộ, bảo vệ tombstone và kế hoạch failover/restore**.
