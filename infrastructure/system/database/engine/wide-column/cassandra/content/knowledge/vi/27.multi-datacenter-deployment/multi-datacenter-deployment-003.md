# LOCAL_ONE, LOCAL_QUORUM và phạm vi phản hồi được tính

## Mục tiêu và ngữ cảnh

Khi Apache Cassandra triển khai trên **nhiều datacenter (DC)**, dữ liệu có thể có các replica ở nhiều khu vực địa lý. Để cân bằng độ trễ và khả năng chịu lỗi, ứng dụng thường chọn `LOCAL_ONE` hoặc `LOCAL_QUORUM` làm **consistency level (CL)** cho từng câu lệnh CQL. Từ khóa **LOCAL** có nghĩa rất cụ thể: **số phản hồi cần thiết được tính trong datacenter local của coordinator**, không phải từ tất cả replica thuộc mọi DC.

Đây là bài học thuộc chương **Nhiều trung tâm dữ liệu** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nội dung kết nối kiến trúc phân tán, mô hình wide-column, partition key, thiết kế bảng theo truy vấn, replication, mức nhất quán đọc/ghi, repair/compaction, xử lý lỗi và kết nối Java Driver.

Hoàn thành bài học, bạn có thể:

1. Tính đúng số replica phải phản hồi ở `LOCAL_ONE` và `LOCAL_QUORUM` khi mỗi DC có RF khác nhau.
2. Giải thích khác biệt giữa **ACK của thao tác ghi** và **phản hồi cần để hoàn thành thao tác đọc**.
3. Phân biệt `LOCAL_QUORUM`, `QUORUM`, `EACH_QUORUM` và `ALL` trong một cluster nhiều DC.
4. Giải thích vì sao ghi được xác nhận ở DC A **không tự bảo đảm** đọc ngay ở DC B đã thấy ghi đó.
5. Định tuyến Java client vào datacenter mong muốn, cấu hình consistency theo yêu cầu nghiệp vụ và kiểm chứng lỗi/độ trễ.
6. Thiết kế một lab dùng CQL, marker cố định và các tình huống lỗi DC có tiêu chí quan sát rõ ràng.

## 1. “Local” được xác định từ đâu?

Trước khi nói về consistency, phải tách ba khái niệm:

- **Datacenter của node**: được Cassandra xác định qua snitch/topology; ví dụ `dc_hn` (Hà Nội) và `dc_sg` (Sài Gòn).
- **Coordinator**: node tiếp nhận yêu cầu CQL từ client và điều phối đọc/ghi đến các replica.
- **Local DC của thao tác**: DC **của coordinator** đang phục vụ yêu cầu, không nhất thiết là nơi máy người dùng cuối hoặc server Java được triển khai.

Giả sử ứng dụng chạy ở Singapore nhưng kết nối đến coordinator tại `dc_hn`. Đối với yêu cầu này, `LOCAL_QUORUM` được tính ở **`dc_hn`**. Nó **không** được tính theo vị trí địa lý của JVM. Muốn thao tác dùng local DC là `dc_sg`, ứng dụng phải định tuyến đến các coordinator thuộc `dc_sg` và cấu hình driver tương ứng.

~~~mermaid
flowchart LR
    APP1["Java client dùng dc_hn"] --> C1["Coordinator tại dc_hn"]
    C1 --> H1["Replica H1"]
    C1 --> H2["Replica H2"]
    C1 --> H3["Replica H3"]
    C1 -. "Replication gửi tới remote DC" .-> S1["Replica S1"]
    C1 -.-> S2["Replica S2"]
    C1 -.-> S3["Replica S3"]
    APP2["Java client dùng dc_sg"] --> C2["Coordinator tại dc_sg"]
    C2 --> S1
    C2 --> S2
    C2 --> S3
~~~

Trong Cassandra, replica đặt ở DC khác vẫn là thành viên của **cùng cluster** và có thể nhận mutation khi ghi. Nhưng với `LOCAL_ONE` hoặc `LOCAL_QUORUM`, **ACK của replica remote không được cộng vào điều kiện thành công của local DC**. Điều này không đồng nghĩa Cassandra bỏ qua replication sang DC khác.

> Phân biệt quan trọng: **phạm vi phản hồi được tính** không phải **danh sách node duy nhất có thể được liên lạc**. Đường ghi có thể gửi mutation đến các replica remote, đường đọc có thể có công việc bổ sung tùy phiên bản/chiến lược; ngưỡng hoàn thành ở `LOCAL_*` vẫn được xét trong local DC.

## 2. Replication factor theo từng DC

Sử dụng `NetworkTopologyStrategy` để chỉ định số bản sao trong mỗi datacenter:

~~~sql
CREATE KEYSPACE IF NOT EXISTS mdc_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hn': 3,
    'dc_sg': 3
}
AND durable_writes = true;
~~~

Ví dụ này giả định **ít nhất ba node ở mỗi DC** có placement/rack phù hợp. Nếu cluster thực tế dùng tên `datacenter1`, `dc1` hoặc tên khác, phải dùng đúng **tên DC do `nodetool status` và topology trả về**. Không thay đổi keyspace sản xuất chỉ để làm bài thực hành.

Đọc lại cấu hình:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'mdc_lab';
~~~

Với ví dụ RF=3+3, mỗi partition có **tổng cộng 6 replica**: ba replica trong `dc_hn` và ba replica trong `dc_sg`. Các replica của cùng một partition có thể nằm ở những node khác nhau theo token, snitch và rack. Tất cả sáu replica không nhất thiết giống nhau tức thời khi có lỗi hoặc replication đang bắt kịp.

`IF NOT EXISTS` chỉ tránh lỗi tạo trùng, **không sửa keyspace đã tồn tại**. Nếu chạy lại lab, kiểm tra `replication` và `durable_writes` trước khi diễn giải số ACK.

### Ví dụ RF không đối xứng

Giả sử keyspace khác có `dc_hn: 3` và `dc_sg: 2`. Không có “LOCAL_QUORUM chung cho cả cluster”; ngưỡng quorum được tính **riêng theo RF của local DC**:

\[
\operatorname{localQuorum}(RF_{DC})=\left\lfloor\frac{RF_{DC}}{2}\right\rfloor+1
\]

| RF trong DC của coordinator | `LOCAL_ONE` | `LOCAL_QUORUM` |
| ---: | ---: | ---: |
| 1 | 1 | 1 |
| 2 | 1 | 2 |
| 3 | 1 | 2 |
| 4 | 1 | 3 |
| 5 | 1 | 3 |

Với RF=1, `LOCAL_QUORUM` chỉ cần một replica, **không tạo ra khả năng chịu lỗi thêm**. Với RF=2, quorum là hai, nên mất một replica có thể khiến `LOCAL_QUORUM` không còn đủ đáp ứng. RF=3 với quorum hai thường là ví dụ dễ học nhất.

## 3. LOCAL_ONE: chỉ cần một phản hồi local

### Khi ghi

Với coordinator ở `dc_hn` và keyspace `mdc_lab` RF=3+3, `LOCAL_ONE` yêu cầu ít nhất **một replica thuộc `dc_hn`** phản hồi thành công cho write.

~~~text
Client -> coordinator dc_hn
           |-- H1: ACK   <- đủ để trả thành công LOCAL_ONE
           |-- H2: có thể nhận nhưng chưa ACK
           |-- H3: có thể nhận nhưng chưa ACK
           |-- S1/S2/S3: replication remote, ACK không tính vào LOCAL_ONE
~~~

Coordinator vẫn có thể chuyển mutation tới các replica khác. `LOCAL_ONE` chỉ nói về **ngưỡng phản hồi mà client phải nhận**, không nói rằng đúng một bản sao được ghi, không nói tất cả replica đã cập nhật, và không cam kết dữ liệu đã được fsync trên mọi thiết bị lưu trữ.

### Khi đọc

`LOCAL_ONE` cần phản hồi đủ từ **một replica ở DC local** để có thể hoàn tất truy vấn. Nếu replica được dùng đang chậm cập nhật, kết quả có thể cũ hơn mutation mà replica khác đã lưu. Điều đó đặc biệt đáng chú ý khi vừa ghi ở DC khác, khi có node down hoặc khi các phiên đồng bộ chưa hoàn tất.

**Đánh đổi:** độ trễ và số phản hồi yêu cầu thấp, khả năng tiếp tục trả lời khi local DC chỉ còn một replica phù hợp. Đổi lại, khả năng đọc ngay đúng bản mới nhất yếu hơn `LOCAL_QUORUM` khi dữ liệu đang chưa hội tụ.

## 4. LOCAL_QUORUM: đa số replica trong DC local

Với `RF_dc_hn=3`, `LOCAL_QUORUM` cần **2 replica ở `dc_hn`** xác nhận. Với `RF_dc_sg=3`, yêu cầu tương tự ở `dc_sg` khi coordinator thuộc `dc_sg`.

### Khi ghi

~~~mermaid
sequenceDiagram
    participant A as Java client
    participant C as Coordinator dc_hn
    participant H1 as H1 trong dc_hn
    participant H2 as H2 trong dc_hn
    participant H3 as H3 trong dc_hn
    participant S as Các replica dc_sg
    A->>C: INSERT (LOCAL_QUORUM)
    par Phân phối mutation
        C->>H1: Mutation
        C->>H2: Mutation
        C->>H3: Mutation
        C->>S: Mutation tới remote DC
    end
    H1-->>C: ACK
    H2-->>C: ACK
    C-->>A: Thành công: đủ 2/3 local ACK
    Note over S: Có thể nhận sau hoặc trước ACK local
~~~

Chỉ cần hai ACK **local**. Một ACK từ `dc_sg` **không thay thế** ACK còn thiếu của `dc_hn`. Điều này cho phép các request tiếp tục hoàn thành nhanh trong một DC khi liên kết WAN tới DC khác chậm, với điều kiện local DC còn đủ replica đáp ứng.

### Khi đọc

`LOCAL_QUORUM` yêu cầu đọc từ **quorum replica local** theo giao thức đọc và hòa giải Cassandra. Coordinator có thể thu nhận dữ liệu/digest, xử lý khác biệt và trả hàng hợp lệ theo quy tắc timestamp/tombstone. Không nên mô tả đây là phép “đọc đúng hai bản vật lý rồi so sánh byte”.

Một số phiên bản/cấu hình có thể gửi thêm request hoặc thực hiện read repair; **ngưỡng cần để trả lời vẫn là quorum local**. Một lần đọc thành công ở `LOCAL_QUORUM` cũng không chứng minh bản sao thứ ba của DC đã đồng bộ.

### Khi nào W + R > RF có ích?

Với một DC có RF=3:

\[
W_{\text{local}}=2,\qquad R_{\text{local}}=2,\qquad W+R=4>3
\]

Tập hai replica đã ACK ghi và tập hai replica trả lời đọc **bắt buộc giao nhau** ít nhất tại một replica. Với một bản ghi không có cập nhật/xóa cạnh tranh, không có các trường hợp sai lệch timestamp đặc biệt và hệ thống đáp ứng thành công, lập luận này giúp hiểu vì sao **ghi `LOCAL_QUORUM` rồi đọc `LOCAL_QUORUM` trong cùng DC** có bảo đảm mạnh hơn việc đọc ở `LOCAL_ONE`.

Tuy nhiên, **không suy diễn thành giao dịch tuyến tính hóa tùy ý**: Cassandra dùng reconciliation theo timestamp và còn có ghi cạnh tranh, tombstone, timeout và mô hình nhất quán theo operation. Khi phải kiểm tra “chỉ cập nhật nếu version chưa đổi”, cần **LWT/`IF`** và serial consistency tương ứng, không thay thế bằng phép tính `W+R>RF`.

## 5. Hai DC: local quorum ở DC A không phải quorum ở DC B

Đây là giới hạn quan trọng nhất của từ `LOCAL`.

Giả sử DC Hà Nội và DC Sài Gòn đều RF=3. Ứng dụng A gửi một `INSERT` ở `dc_hn` với `LOCAL_QUORUM` và nhận ACK từ H1, H2. Ngay lúc đó, ứng dụng B đọc tại `dc_sg` với `LOCAL_QUORUM`:

~~~text
dc_hn: H1 = new (ACK), H2 = new (ACK), H3 = maybe
dc_sg: S1 = old?, S2 = old?, S3 = old?

WRITE LOCAL_QUORUM tại dc_hn: THÀNH CÔNG
READ  LOCAL_QUORUM tại dc_sg: CHƯA BẢO ĐẢM thấy giá trị mới
~~~

Trong thực tế, các bản sao remote có thể cập nhật rất nhanh và lần đọc tại `dc_sg` **vẫn thấy dữ liệu mới**. Nhưng ACK tại `dc_hn` **không đòi** quorum `dc_sg` trả lời, nên không có bảo đảm chỉ từ CL local rằng dữ liệu đã tới đủ replica remote đúng thời điểm đó.

~~~mermaid
sequenceDiagram
    participant A as Client A ở dc_hn
    participant H as Coordinator dc_hn
    participant H2 as Quorum dc_hn
    participant S as Replica dc_sg
    participant B as Client B ở dc_sg
    A->>H: WRITE (LOCAL_QUORUM)
    H->>H2: Ghi vào replica local
    H-->>S: Mutation remote (chưa xác nhận trong điều kiện local)
    H2-->>H: 2 ACK local
    H-->>A: Success
    B->>S: READ (LOCAL_QUORUM tại dc_sg)
    Note over S: Có thể chưa đủ bản sao thấy ghi mới
    S-->>B: Kết quả tùy trạng thái đồng bộ của dc_sg
~~~

**Sai lầm phổ biến:** “Ghi `LOCAL_QUORUM` ở bất kỳ nơi nào thì đọc `LOCAL_QUORUM` ở mọi nơi đều mới ngay.” Lập luận `W+R>RF` không áp dụng khi **write quorum và read quorum nằm ở hai tập replica của hai DC khác nhau**; chúng không bắt buộc giao nhau.

Nếu ứng dụng cần hành vi đọc-sau-ghi (*read-your-writes*) ngay cho người dùng, có thể ưu tiên các lượt đọc tiếp theo qua **cùng DC** nơi write được ACK; hoặc thiết kế cơ chế xác nhận/đồng bộ xuyên DC theo yêu cầu nghiệp vụ. Không khẳng định chọn `QUORUM` trong mọi trường hợp sẽ cho “strong consistency” tuyệt đối, và không đánh đổi latency WAN mà chưa đo.

## 6. So sánh LOCAL_ONE, LOCAL_QUORUM và các CL khác

Giả sử `NetworkTopologyStrategy` cấu hình `dc_hn:3` và `dc_sg:3`, tổng RF=6.

| Consistency level | Số phản hồi cần cho **write** | Số phản hồi cần cho **read** | Phạm vi |
| --- | --- | --- | --- |
| `LOCAL_ONE` | 1 replica ở local DC | 1 replica ở local DC | Local theo coordinator |
| `LOCAL_QUORUM` | 2/3 ở local DC | 2/3 ở local DC | Đa số trong local DC |
| `ONE` | 1 replica | 1 replica | Không quy định bắt buộc thuộc local DC trong ngữ nghĩa CL |
| `QUORUM` | 4/6 replica | 4/6 replica | Đa số tính trên **tổng RF của keyspace** |
| `EACH_QUORUM` | 2/3 **ở mỗi DC**: tổng 4 ACK | **Không dùng cho read thông thường** | Quorum từng DC; chủ yếu cho write |
| `ALL` | 6/6 replica | 6/6 replica | Mọi replica được cấu hình |

**QUORUM toàn cluster không giống EACH_QUORUM:** `QUORUM` cần 4/6 phản hồi tổng, có thể là 3 ở `dc_hn` và 1 ở `dc_sg`; `EACH_QUORUM` yêu cầu ít nhất 2 từ **mỗi** DC. `EACH_QUORUM` dùng cho ghi, không phải lựa chọn thay thế của `LOCAL_QUORUM` khi đọc.

**ALL giảm availability khi có replica không sẵn sàng.** Trong multi-DC, điều này còn phụ thuộc chất lượng kết nối WAN. Nếu ứng dụng chỉ cần hiệu năng local và chấp nhận việc dữ liệu remote hội tụ sau, `LOCAL_QUORUM` thường dễ vận hành hơn các CL đòi phản hồi nhiều DC; nhưng lựa chọn cuối cùng phải theo mục tiêu nghiệp vụ, mức chấp nhận stale và yêu cầu lỗi.

Với keyspace RF không đối xứng, cần **tính lại từ từng RF**, không sao chép các con số 2/3 và 4/6 trong bảng.

## 7. Tình huống sự cố và phạm vi đáp ứng

### Sự cố 1: WAN giữa hai DC chậm hoặc gián đoạn

Nếu `dc_hn` còn đủ hai replica khỏe và client dùng coordinator tại `dc_hn`, `LOCAL_QUORUM` có thể vẫn thành công **mà không cần ACK của `dc_sg`**. Tuy nhiên, mutation đến remote DC có thể chậm/thiếu; cần theo dõi hints, ghi timeout và repair sau khi mạng phục hồi.

**Không xem ACK local là xác nhận remote đã bền vững**. Nếu ứng dụng có yêu cầu DR (disaster recovery) phải chịu được mất toàn bộ DC ngay sau ACK, cần đánh giá consistency/replication trên nhiều DC, RPO/RTO, khôi phục và lịch kiểm chứng riêng.

### Sự cố 2: local DC còn hai node sống ở RF=3

`LOCAL_ONE` vẫn có thể thành công với một phản hồi, `LOCAL_QUORUM` cần cả hai replica sống cho partition; mọi sự cố thứ hai có thể khiến quorum local không thể trả lời. `ALL` không thể thành công nếu replica thứ ba của partition đã down.

### Sự cố 3: local DC chỉ còn một replica sống ở RF=3

`LOCAL_ONE` có thể tiếp tục đáp ứng, nhưng `LOCAL_QUORUM` **không thể đạt 2/3**. Dù DC remote còn ba replica khỏe, các ACK remote không được đem cộng thay quorum local. Muốn chuyển dịch vụ sang DC remote, phải thay **coordinator local** và định tuyến lại client; đồng thời đánh giá dữ liệu remote có bắt kịp và yêu cầu nghiệp vụ hay chưa.

### Sự cố 4: client từ DC A chuyển qua DC B sau failover

Nếu write cuối cùng chỉ ACK tại `dc_hn` trước khi cả DC này ngừng hoạt động, `dc_sg` **không được bảo đảm** đã có dữ liệu mới nhất. Khi chuyển Java client sang `dc_sg`, `LOCAL_QUORUM` mới sẽ tính trên `dc_sg`, chứ không làm các write trước đó “tự động trở thành quorum ở B”.

Sự kiện có thể cần được khôi phục từ các replica còn sống, event log, outbox hoặc backup. Thay đổi driver local DC **không phải** cơ chế phục hồi dữ liệu đã không còn ở bất cứ replica nào.

### Sự cố 5: đọc/ghi timeout

`WriteTimeout` có thể xảy ra sau khi một số replica đã xử lý mutation; trạng thái nghiệp vụ **chưa xác định**. `ReadTimeout` hoặc `Unavailable` không có nghĩa hàng không tồn tại. Ứng dụng phải phân biệt:

- **ACKNOWLEDGED**: client nhận thành công ở CL đã yêu cầu.
- **UNKNOWN_WRITE**: lỗi/timeout khi ghi, không biết mutation đã tới bao nhiêu replica.
- **FOUND / MISSING / READ_ERROR**: kết quả đọc theo khóa/CL đã định; read error không được tính như missing.

Không retry phép tăng counter hoặc side effect ngoài database chỉ vì lần gọi trước timeout.

## 8. Lab CQL: tự kiểm chứng ở hai datacenter

### 8.1. Chuẩn bị topology

Lab lý tưởng có ít nhất **ba node ở mỗi DC**, ví dụ `dc_hn` gồm H1/H2/H3 và `dc_sg` gồm S1/S2/S3. Đừng dùng cluster production để tạo lỗi có chủ đích.

~~~bash
# Chạy trên node có nodetool tương ứng.
nodetool status
~~~

Xác nhận node phân thành đúng hai DC, đa số đang `UN`, không có bootstrap/decommission/repair lớn đang chạy. Trên `cqlsh` kết nối **một node `dc_hn`**:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` phản ánh **node đang trả lời**. Nếu ứng dụng hoặc `cqlsh` chuyển coordinator, cần kiểm tra lại DC thực tế. Tên `dc_hn`/`dc_sg` trong ví dụ phải trùng hoàn toàn với giá trị snitch.

### 8.2. Tạo bảng theo truy vấn

Sử dụng keyspace `mdc_lab` ở mục 2. Bảng có partition key phục vụ kiểm chứng có giới hạn:

~~~sql
CREATE TABLE IF NOT EXISTS mdc_lab.events_by_run (
    run_id text,
    event_id uuid,
    marker text,
    payload text,
    source_dc text,
    PRIMARY KEY ((run_id), event_id)
);
~~~

`run_id` là **partition key**, `event_id` là clustering key. Mỗi lượt thử nên dùng `run_id` mới, `event_id` cố định và `marker` dự kiến được ghi trong **manifest ngoài Cassandra**. Đừng dùng `COUNT(*)` trên toàn cluster hoặc quét nhiều partition để kiểm tra đơn giản một event.

### 8.3. Ghi ở local DC Hà Nội

Kết nối `cqlsh` đến một node ở `dc_hn`. `CONSISTENCY` bên dưới là **lệnh cqlsh**, không phải câu CQL:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO mdc_lab.events_by_run
    (run_id, event_id, marker, payload, source_dc)
VALUES (
    'mdc-trial-01',
    11111111-1111-4111-8111-111111111111,
    'expected-A',
    'written-from-dc-hn',
    'dc_hn'
);
~~~

Nếu thành công, lưu ở manifest: **ACK_LOCAL_QUORUM**, coordinator `dc_hn`, timestamp, `run_id`, `event_id`, `marker`. Nếu timeout, ghi **UNKNOWN**; đừng biến một lần đọc về sau thành bằng chứng rằng client đã nhận ACK trước đó.

### 8.4. Đọc ở cùng DC với hai CL

~~~text
CONSISTENCY LOCAL_ONE
~~~

~~~sql
SELECT event_id, marker, payload, source_dc
FROM mdc_lab.events_by_run
WHERE run_id = 'mdc-trial-01';
~~~

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT event_id, marker, payload, source_dc
FROM mdc_lab.events_by_run
WHERE run_id = 'mdc-trial-01';
~~~

Khi cluster khỏe, cả hai truy vấn rất có thể trả marker `expected-A`. **Kết quả giống nhau trong lần thử không làm hai CL có bảo đảm giống nhau**. Mục tiêu là ghi nhận CL đã yêu cầu và điều kiện mà một lần đọc phải thỏa, không cố tạo ra kết quả sai bằng cách đọc liên tục.

### 8.5. Đọc ở DC Sài Gòn ngay sau write

Kết nối **một phiên `cqlsh` riêng** đến node `dc_sg`, đặt:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT event_id, marker, payload, source_dc
FROM mdc_lab.events_by_run
WHERE run_id = 'mdc-trial-01';
~~~

Điều quan trọng cần ghi trong báo cáo:

- Nếu thấy `expected-A`: **đã quan sát dữ liệu** tại local quorum ở `dc_sg`, không có nghĩa ACK ghi ban đầu đã cần phản hồi từ remote DC.
- Nếu không thấy: điều này có thể phù hợp với việc remote chưa nhận mutation; kiểm tra log, thời điểm, topology và các lần ghi/xóa khác.
- Nếu timeout/unavailable: ghi `READ_ERROR`, **không** tính là dữ liệu đã mất.
- Nếu remote nhận nhanh đến mức không thể tái hiện đọc cũ, **không** được sửa diễn giải lý thuyết thành “LOCAL_QUORUM xuyên DC”.

Để kiểm tra hệ thống sau outage/replication lag, theo dõi logs/metrics hints/repair và đối soát một tập marker ổn định. Tránh cố gián đoạn mạng WAN trên hạ tầng thật chỉ để chứng minh cơ chế.

## 9. Java Driver 4.x: local datacenter và consistency

Với Java Driver 4.x, ứng dụng nên cấu hình **local datacenter** và contact point phù hợp. Tên DC trong `withLocalDatacenter(...)` phải đúng topology mà driver nhìn thấy. Ví dụ hai dịch vụ triển khai theo khu vực sẽ có **cấu hình session khác nhau**, không tùy ý thay local DC trên một session đang dùng cho toàn bộ workload.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;

import java.net.InetSocketAddress;

public final class CassandraSessionFactory {
    public static CqlSession connectHanoi() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.20.0.11", 9042))
            .withLocalDatacenter("dc_hn")
            .withKeyspace("mdc_lab")
            .build();
    }

    public static CqlSession connectSaigon() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.30.0.11", 9042))
            .withLocalDatacenter("dc_sg")
            .withKeyspace("mdc_lab")
            .build();
    }
}
~~~

Các IP trên **chỉ là địa chỉ minh họa** trong một mạng lab; phải thay bằng contact point thật. Tùy môi trường, driver còn cần authentication, TLS, cấu hình profile và nhiều contact point để tránh phụ thuộc một node. Driver phát hiện topology và điều phối load balancing; đừng tự xây vòng chọn IP ngẫu nhiên giữa hai DC khi cần ý nghĩa `LOCAL_*` nhất quán.

### Ví dụ ghi rồi đọc với CL tường minh

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

public final class LocalConsistencyProbe {
    public enum WriteResult { ACKNOWLEDGED, UNKNOWN }
    public enum ReadResult { FOUND_MATCH, MISSING, MISMATCH, READ_ERROR }

    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement read;

    public LocalConsistencyProbe(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO mdc_lab.events_by_run " +
            "(run_id, event_id, marker, payload, source_dc) " +
            "VALUES (?, ?, ?, ?, ?)");
        this.read = session.prepare(
            "SELECT marker FROM mdc_lab.events_by_run " +
            "WHERE run_id = ? AND event_id = ?");
    }

    public WriteResult insertAtLocalQuorum(
            String runId, UUID eventId, String marker,
            String payload, String sourceDc) {
        try {
            session.execute(insert.bind(
                    runId, eventId, marker, payload, sourceDc)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotence(false));
            System.out.printf("ACK LOCAL_QUORUM run=%s id=%s%n",
                runId, eventId);
            return WriteResult.ACKNOWLEDGED;
        } catch (RuntimeException error) {
            System.err.printf("UNKNOWN_WRITE run=%s cause=%s%n",
                runId, error.getClass().getSimpleName());
            return WriteResult.UNKNOWN;
        }
    }

    public ReadResult verify(
            String runId, UUID eventId, String expectedMarker,
            DefaultConsistencyLevel readCl) {
        try {
            Row row = session.execute(read.bind(runId, eventId)
                    .setConsistencyLevel(readCl))
                .one();
            if (row == null) return ReadResult.MISSING;
            return expectedMarker.equals(row.getString("marker"))
                ? ReadResult.FOUND_MATCH : ReadResult.MISMATCH;
        } catch (RuntimeException error) {
            System.err.printf("READ_ERROR CL=%s id=%s cause=%s%n",
                readCl, eventId, error.getClass().getSimpleName());
            return ReadResult.READ_ERROR;
        }
    }
}
~~~

Sử dụng:

~~~java
// Hai session trỏ tới hai local DC khác nhau; đóng session khi kết thúc.
try (CqlSession hn = CassandraSessionFactory.connectHanoi();
     CqlSession sg = CassandraSessionFactory.connectSaigon()) {

    UUID eventId = UUID.fromString(
        "11111111-1111-4111-8111-111111111111");
    LocalConsistencyProbe writer = new LocalConsistencyProbe(hn);
    LocalConsistencyProbe remoteReader = new LocalConsistencyProbe(sg);

    writer.insertAtLocalQuorum(
        "mdc-trial-java-01", eventId, "expected-A", "demo", "dc_hn");

    LocalConsistencyProbe.ReadResult result = remoteReader.verify(
        "mdc-trial-java-01", eventId, "expected-A",
        DefaultConsistencyLevel.LOCAL_QUORUM);
    System.out.println("dc_sg read=" + result);
}
~~~

**Điểm cần tránh khi diễn giải ví dụ:**

- `insertAtLocalQuorum` ghi nhận ACK khi `execute` trả thành công. Kết quả `UNKNOWN` không chứng minh mutation không tồn tại; production cần phân loại timeout, unavailable và lỗi cấu hình.
- `remoteReader` dùng local DC `dc_sg`, nên `LOCAL_QUORUM` của **lần đọc** tính tại `dc_sg`. Điều này khác `LOCAL_QUORUM` của **lần ghi** tại `dc_hn`.
- `FOUND_MATCH` chỉ là giá trị đọc được tại CL đang chọn, **không** xác nhận từng replica remote đã có dữ liệu vật lý hoặc write ACK ban đầu đã bao gồm remote.
- `MISSING` cần được phân biệt `READ_ERROR`. Khi log manifest nguồn, chỉ coi một sự kiện là “ghi đã ACK” nếu client đã thực sự nhận thành công.
- `setIdempotence(false)` thể hiện chính sách thận trọng trong lab trước retry tự động khi kết quả chưa xác định. Với `INSERT` thuần dùng khóa/giá trị ổn định, ứng dụng có thể xây chính sách idempotent riêng sau khi cân nhắc timestamp, TTL và thao tác cạnh tranh.
- Một ứng dụng production không nên mở/đóng `CqlSession` mỗi request; hai session ở trên chỉ để minh họa ranh giới DC trong một chương trình lab ngắn.

## 10. Giám sát và xác minh replication xuyên datacenter

**Không đo độ hội tụ bằng việc thử `COUNT(*)` toàn bảng ở hai DC.** Thay vào đó, chuẩn bị marker/event ID từ nguồn độc lập, truy vấn theo partition key hoặc khóa chính, và theo dõi tiến độ vận hành:

| Chỉ số/thông tin | Vì sao hữu ích? | Giới hạn |
| --- | --- | --- |
| `nodetool status` theo DC | Xác nhận số node `UN`/`DN` và topology | Node `UN` không chứng minh mọi replica đã bắt kịp |
| Logs/metrics về hints | Nhận biết mutation chờ giao, giao thất bại hoặc đã giao | Không có hints không chứng minh dữ liệu hoàn toàn giống nhau |
| `nodetool netstats` | Quan sát streaming trong các trường hợp repair/bootstrap | Không phải đồng hồ đo tất cả mutation remote |
| Repair sessions/coverage | Kiểm tra range/replica được đối chiếu thành công | Một phiên repair chưa chắc bao phủ toàn cluster/DC |
| p50/p95/p99 và timeout theo DC | Phát hiện ảnh hưởng WAN, DC lỗi, CL quá mạnh | Latency không chứng minh dữ liệu đã đầy đủ |
| Manifest expected so với actual | Phát hiện event thiếu hoặc marker khác | Manifest phải đáng tin cậy, tránh nhầm lỗi đọc với thiếu dữ liệu |
| Lag đồng bộ theo pipeline nghiệp vụ | Biết độ mới dữ liệu mà DC dự phòng phục vụ | Cần nguồn sự thật, checkpoint và định nghĩa watermark |

Các công cụ cơ bản:

~~~bash
# Chạy trên node phù hợp trong lab; một lệnh không tự thay cho kiểm tra cả cụm.
nodetool status
nodetool netstats
nodetool compactionstats
~~~

Sau mạng/replica outage, cần đánh giá **repair** theo phiên bản, phạm vi token range, keyspace, DC và lịch vận hành. Repair sử dụng tài nguyên mạng, disk I/O và compaction; không chạy indiscriminately trong giờ cao điểm. Repair không tạo ra sự kiện đã mất trên **mọi** replica và nguồn dữ liệu, nên với yêu cầu RPO nghiêm ngặt cần nguồn log/backup/outbox đáng tin.

### Hai lỗi suy luận cần tránh

**Lỗi 1:** “Đọc ở `dc_sg` thấy dữ liệu nên lệnh ghi `LOCAL_QUORUM` trước đó chắc chắn đợi ACK `dc_sg`.” **Sai**: có thể replication tới remote trước lúc đọc; điều kiện ACK ban đầu vẫn chỉ tính `dc_hn`.

**Lỗi 2:** “`LOCAL_QUORUM` ở `dc_sg` không thấy dữ liệu nên Cassandra chắc chắn đã mất dữ liệu.” **Sai**: có thể là replication lag, topology/CL khác, thao tác cạnh tranh, xóa/TTL, hoặc vấn đề đọc. Phải kiểm tra nguồn expected, thời gian, CL/RF, logs và repair.

## 11. Bài thực hành và câu hỏi kiểm tra

**Bài 1 — Tính quorum trong hai DC.** Với `dc_hn:3` và `dc_sg:3`, tính số ACK cần cho `LOCAL_ONE`, `LOCAL_QUORUM`, `QUORUM`, `EACH_QUORUM` và `ALL`. Giải thích vì sao `QUORUM=4/6` không đồng nghĩa `EACH_QUORUM=2+2`.

**Bài 2 — RF không đối xứng.** Một keyspace có `dc_hn:3` và `dc_sg:2`. Truy vấn `LOCAL_QUORUM` do coordinator ở `dc_sg` thực hiện cần bao nhiêu replica local? Khi một replica `dc_sg` down, có còn đủ `LOCAL_QUORUM` không? Vì sao các replica `dc_hn` không giúp đạt ngưỡng local này?

**Bài 3 — Đọc-sau-ghi.** Client A ghi `LOCAL_QUORUM` tại `dc_hn` và được ACK. Client B lập tức đọc `LOCAL_QUORUM` tại `dc_sg`. Điều kiện `W+R>RF` có bảo đảm B phải thấy bản ghi mới không? Phác thảo phương án định tuyến/đồng bộ nếu sản phẩm đòi hỏi read-your-writes.

**Bài 4 — Sự cố WAN.** Liên kết `dc_hn` ↔ `dc_sg` bị gián đoạn, cả ba replica của `dc_hn` còn sống. Dự đoán kết quả write `LOCAL_ONE` và `LOCAL_QUORUM` qua coordinator `dc_hn`, lưu ý tình trạng remote và rủi ro nếu DC này mất hoàn toàn trước khi đồng bộ.

**Bài 5 — Failover.** `dc_hn` chỉ còn một replica local, `dc_sg` có ba replica khỏe. Tại sao `LOCAL_QUORUM` qua coordinator `dc_hn` không thành công? Cần đổi gì ở driver/định tuyến để thao tác ở `dc_sg`, và còn rủi ro gì về dữ liệu chưa kịp replicate?

**Bài 6 — Java kiểm chứng.** Tạo hai `CqlSession` với local DC khác nhau, ghi event có marker ổn định ở `dc_hn` rồi đọc ở cả hai DC. Ghi kết quả `ACKNOWLEDGED`, `FOUND_MATCH`, `MISSING`, `READ_ERROR` theo mốc thời gian. Vì sao một lần đọc đúng ở DC remote không thay đổi định nghĩa của ACK ghi local?

**Bài 7 — Phân biệt LWT.** Một nhóm phát triển đề xuất dùng `LOCAL_QUORUM` thay cho `IF version = ?` để chống cập nhật đồng thời. Giải thích vì sao đây là hai bài toán khác nhau, và serial consistency `LOCAL_SERIAL`/`SERIAL` là một cấu hình bổ sung khi dùng LWT.

## Ghi nhớ

**`LOCAL_ONE` cần một phản hồi và `LOCAL_QUORUM` cần đa số phản hồi trong DC của coordinator; không tính ACK ở DC khác để đạt ngưỡng local.** Với RF3 mỗi DC, `LOCAL_QUORUM` là 2/3 **trong từng DC tùy nơi điều phối yêu cầu**, không phải 2/6 toàn cluster. Ghi thành công ở `dc_hn` không tự bảo đảm đọc ngay ở `dc_sg` nhìn thấy dữ liệu; quản lý ranh giới local bằng routing/Java Driver, đo độ trễ replication, đối soát marker, và chuẩn bị repair/failover theo yêu cầu RPO/RTO của hệ thống.
