# Decommission, removenode và lựa chọn theo trạng thái nút

## Mục tiêu bài học

Trong Apache Cassandra, mỗi node nắm giữ một phần các **token range** của vòng phân vùng; các bản sao được bố trí theo **replication strategy** và **replication factor (RF)**. Khi cần giảm số node hoặc một node hỏng vĩnh viễn, không thể đơn giản tắt máy rồi xóa cấu hình: cluster phải cập nhật **topology**, xác định lại replica nào chịu trách nhiệm dữ liệu và, khi cần, **stream dữ liệu** đến các node còn lại.

Hai thao tác quản trị dễ bị nhầm nhất là:

- **`nodetool decommission`:** rút **một node còn hoạt động, đủ khỏe để phối hợp** ra khỏi cluster một cách có kế hoạch.
- **`nodetool removenode <host_id>`:** loại bỏ **một node đã down, không thể decommission**, khỏi membership/token metadata của cluster; các node còn sống phải xử lý lại quyền sở hữu dữ liệu.

Đây là bài học thuộc chương **Thay đổi topology** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nội dung liên hệ mô hình wide-column, partition key, bảng thiết kế theo truy vấn, consistency level đọc/ghi, replication, compaction, repair, xử lý lỗi và cách ứng dụng Java phản ứng với sự thay đổi topology.

Sau bài này, bạn có thể:

1. Lựa chọn `decommission`, `removenode` hoặc **replace node** dựa trên trạng thái và mục tiêu vận hành.
2. Kiểm tra RF, số node còn sống, host ID, token ownership, dung lượng và khả năng duy trì quorum trước khi thay đổi.
3. Mô tả streaming, gossip/membership, sự thay đổi replica placement và chi phí I/O/network trong giai đoạn chuyển đổi.
4. Thực hành CQL và các lệnh `nodetool` theo **kịch bản lab**, có điểm dừng và kế hoạch phục hồi.
5. Phân biệt **lệnh kết thúc**, **node biến mất khỏi ring**, **dữ liệu truy vấn được**, và **các replica đã đồng bộ đầy đủ**.
6. Xác minh dữ liệu có marker ổn định và theo dõi tác động lên Java Driver.

> **Cảnh báo vận hành:** `decommission` và `removenode` là thao tác thay đổi topology có tác động lớn. **Không chạy trên môi trường production chỉ để thực hành.** Các lệnh trong bài hướng tới cluster lab có quyền quản trị và backup; tên DC, node, host ID và phương án thay thế phải kiểm tra lại trong môi trường thực tế.

## 1. Token ring, replica placement và yêu cầu trước khi rút node

Cassandra dùng **partition key** để tính token và xác định tập replica phụ trách partition. Với `NetworkTopologyStrategy`, các bản sao được phân phối theo RF cấu hình riêng cho từng datacenter, có xét topology/rack theo snitch. Node mới tham gia, node rời cluster hoặc node bị loại khỏi metadata sẽ thay đổi **tập endpoint được xem là replica hợp lệ** của một số token range.

Ví dụ một datacenter `datacenter1` có bốn node `cass-1`, `cass-2`, `cass-3`, `cass-4` và keyspace đặt **RF=3**. Mỗi partition có ba replica trong datacenter này; **không** có nghĩa tất cả bốn node đều lưu mỗi hàng. Khi một node rời ring, ba node còn lại có thể đảm nhận ba bản sao, **nếu có đủ dung lượng và dữ liệu cần thiết để phân phối lại**.

| Tình huống | Hệ quả |
| --- | --- |
| Bốn node sống, RF=3 | Mỗi partition có ba replica được placement chọn; một node có thể không là replica của partition cụ thể. |
| Một node xuống tạm thời | Metadata vẫn coi nó là thành viên; dữ liệu có thể được ghi ở replica khác/hints tùy CL và cấu hình. |
| Decommission một node sống | Node rời truyền dữ liệu cần thiết trong quá trình rút khỏi ring; placement thay đổi. |
| Removenode một node đã chết | Cluster loại host ID và tổ chức streaming/tái tạo dữ liệu từ **những bản sao còn tồn tại**. |
| Chỉ còn hai node trong DC nhưng RF=3 | Không còn đủ ba node riêng biệt để đặt ba replica; **không được coi là giảm node an toàn** nếu vẫn cần RF3. |

### Tính quorum trước khi bắt đầu

Ở một DC với RF=3:

| Consistency level | Số xác nhận/replica cần |
| --- | --- |
| `ONE` hoặc `LOCAL_ONE` | 1 |
| `LOCAL_QUORUM` | 2 |
| `ALL` | 3 |

`LOCAL_QUORUM` yêu cầu hai replica trong DC local; việc giảm số node, stream chưa xong hoặc đồng thời có lỗi khác có thể làm read/write timeout hoặc unavailable. `ALL` đặc biệt nhạy với bất kỳ replica không sẵn sàng.

**Giữ nguyên RF không tự bảo đảm giữ nguyên chất lượng dữ liệu.** Nếu một số mutation chỉ được xác nhận ở `ONE` và bản sao duy nhất còn giữ chúng nằm trên node đã chết, không có phép `removenode` nào có thể tạo lại những byte đã mất. Cần phân biệt **phục hồi topology** với **phục hồi dữ liệu** từ backup, log sự kiện hoặc các replica còn chứa dữ liệu.

## 2. Bảng quyết định: decommission, removenode hay replace?

| Trạng thái và mục tiêu | Lựa chọn thông thường | Vì sao |
| --- | --- | --- |
| Node `UN`, hoạt động ổn, muốn **giảm số node vĩnh viễn** | `nodetool decommission` trên **chính node rời cluster** | Node còn sống có thể phối hợp transfer ownership/streaming. |
| Node `UN` nhưng định thay phần cứng mà **giữ nguyên dung lượng cluster** | **Node replacement** theo quy trình phiên bản | Không nhất thiết phải giảm RF/công suất rồi bootstrap node mới từ đầu. |
| Node `DN` do sự cố tạm, dự kiến sửa và cho quay lại | **Khắc phục lỗi, restart**, không vội `removenode` | Tránh thay đổi ring khi membership chỉ gián đoạn tạm thời. |
| Node `DN` lâu dài, không thể chạy `decommission`, **quyết định loại bỏ vĩnh viễn** | `nodetool removenode <host_id>` từ node khỏe khác | Node đã chết không thể tự stream/rời ring có kiểm soát. |
| Node `DN` hỏng ổ nhưng cần **thay node cùng vị trí** và giữ capacity | **Replace/rebuild** theo hướng dẫn Cassandra và topology | Thường phù hợp hơn rút node khỏi cluster nếu thiếu dung lượng sau khi giảm. |
| Node bị split network, trạng thái `DN` chỉ từ một phía | **Điều tra mạng/quorum trước** | Node cũ có thể vẫn chạy ở phía khác; removenode rồi cho nó quay lại sẽ nguy hiểm. |
| Quá ít node/rack/DC còn lại để đạt RF hoặc SLA | **Dừng kế hoạch; bổ sung/khôi phục năng lực** | Stream không tự tạo thêm thiết bị lưu trữ hoặc dữ liệu nguồn. |

**Quy tắc cốt lõi:** `decommission` cho node **còn chạy và sẽ chủ động rời**; `removenode` cho node **đã ngừng và bị loại vĩnh viễn**. **Replace** là phương án riêng khi muốn **duy trì topology/công suất** thay vì giảm số node.

Không dùng `removenode` như một cách “tăng tốc” `decommission` của node khỏe. Cũng không cố khởi động `nodetool decommission` trên node đã down: không có tiến trình nào ở đó để thực hiện thao tác.

### Sơ đồ lựa chọn

~~~mermaid
flowchart TD
    A["Muốn thay đổi một node Cassandra"] --> B{"Node còn chạy và ổn định?"}
    B -->|Có| C{"Mục tiêu giảm số node vĩnh viễn?"}
    C -->|Có| D["Kiểm tra RF, disk, SLA\nDecommission trên node rời"]
    C -->|Không, thay phần cứng| E["Quy trình replace node"]
    B -->|Không| F{"Node sẽ trở lại an toàn?"}
    F -->|Có| G["Sửa lỗi mạng/máy\nKhởi động lại, kiểm tra hội tụ"]
    F -->|Không| H{"Có đủ replica/dung lượng\nvà nguồn dữ liệu còn tin cậy?"}
    H -->|Có| I{"Muốn giữ lại capacity?"}
    I -->|Có| E
    I -->|Không| J["Removenode bằng host ID\ntrên node còn sống"]
    H -->|Không| K["Dừng, lập kế hoạch restore\nhoặc bổ sung node"]
~~~

## 3. Phân biệt địa chỉ IP, host ID và token

Node trong Cassandra có nhiều định danh:

- **Địa chỉ IP/hostname:** dùng cho liên lạc hoặc hiển thị; có thể thay đổi khi thay máy.
- **Host ID:** UUID định danh node trong metadata cluster. `removenode` cần **host ID của node bị loại**, không phải IP, không phải token.
- **Token(s):** quyết định vị trí token range; với virtual nodes (*vnodes*), một node thường có nhiều token.

Trên một node khỏe, lấy thông tin topology:

~~~bash
nodetool status
nodetool describecluster
~~~

Ví dụ giả lập một phần `nodetool status`:

~~~text
Datacenter: datacenter1
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address       Load     Tokens  Owns (effective)  Host ID                               Rack
UN  10.0.0.11     ...      16      ...               11111111-1111-4111-8111-111111111111  rack1
UN  10.0.0.12     ...      16      ...               22222222-2222-4222-8222-222222222222  rack2
UN  10.0.0.13     ...      16      ...               33333333-3333-4333-8333-333333333333  rack3
DN  10.0.0.14     ...      16      ...               44444444-4444-4444-8444-444444444444  rack1
~~~

Các IP, host ID và token count ở trên **hoàn toàn minh họa**; không copy host ID giả vào môi trường thật. Cột `UN` nghĩa là *Up/Normal*, `DN` là *Down/Normal*, `UL` thường thể hiện *Up/Leaving* trong cách hiển thị trạng thái của `nodetool`. Nếu node đang ở trạng thái Joining/Leaving/Moving, không được tự khởi động một thay đổi topology thứ hai.

Một số phiên bản hỗ trợ cách xem token ownership hoặc endpoint cho khóa qua `nodetool ring` / `nodetool getendpoints`; kết quả placement không chứng minh các replica đã đồng bộ byte dữ liệu. Luôn xác nhận **host ID bằng ít nhất nguồn quản trị thích hợp** và lưu biên bản trước lệnh phá vỡ topology.

## 4. Checklist an toàn trước khi thay đổi

### 4.1. Điều kiện cần thỏa

1. **Mục tiêu rõ:** thu nhỏ cluster vĩnh viễn, thay phần cứng, hay xử lý node mất kết nối tạm?
2. **Topology chính xác:** node nào up/down, datacenter/rack, host ID, token placement, snitch và seed configuration.
3. **Replication:** kiểm tra mọi keyspace liên quan; `NetworkTopologyStrategy` có RF theo từng DC, không chỉ một RF chung.
4. **Dung lượng và thông lượng:** node còn lại có đủ disk headroom cho dữ liệu chuyển đến, compaction, commit log, streaming và mức tăng tải không?
5. **Khả năng sẵn sàng:** trong thời gian chuyển đổi và khi node khác cũng lỗi, CL ứng dụng (`LOCAL_QUORUM`, `ALL`...) có còn đáp ứng mục tiêu SLA?
6. **Dữ liệu đáng tin:** backup/snapshot được kiểm chứng, repair phù hợp, không có dữ liệu chỉ tồn tại trên node hỏng mà hệ thống vẫn cần.
7. **Sức khỏe cluster:** không có bootstrap/decommission/removenode/repair/streaming bất thường đang chạy hoặc có kế hoạch xung đột.
8. **Rollback thực tế:** có phương án thay/rebuild node, phục hồi dữ liệu và liên lạc với nhóm vận hành; không giả định có thể “undo” lệnh bằng một nút bấm.
9. **Quan sát:** có dashboard/log cho disk, network, streaming, pending compaction, p95/p99 read/write, timeout và lỗi.

~~~bash
# Lệnh chỉ đọc/quan sát (chạy trên các node sống phù hợp).
nodetool status
nodetool describecluster
nodetool netstats
nodetool compactionstats
nodetool tpstats
~~~

Xem cấu hình replication từ CQL:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces;
~~~

Khi chỉ có ba node trong một DC và một keyspace quan trọng yêu cầu **RF=3**, loại bỏ hẳn một node làm cluster chỉ còn hai node trong DC: **không tiếp tục quy trình thu nhỏ đơn thuần**. Cần bổ sung node, chọn replace hoặc đánh giá thay đổi RF theo kế hoạch riêng; không tự sửa RF để hợp thức hóa một thao tác khẩn cấp mà chưa đánh giá độ bền dữ liệu.

### 4.2. Ước lượng tải chuyển đổi

Việc giảm một node không làm tổng dữ liệu logic biến mất: các node khác phải giữ bản sao theo RF và token ownership mới. Vì vậy tài nguyên trên node còn lại **có thể tăng đáng kể** sau khi chuyển dữ liệu.

Ví dụ minh họa: bốn node có tải đĩa không đều, một node chứa hàng trăm GiB SSTable. Không thể đơn giản lấy “tổng tải/ba node” làm bảo đảm còn đủ chỗ vì streaming tính theo token/range, SSTable và phân bố nóng/lạnh khác nhau. Dung lượng đầu ra compaction có thể tồn tại song song đầu vào; snapshot cũng có thể giữ file cũ. Hãy đo **free space tối thiểu của từng node**, không dựa vào số trung bình.

## 5. Thực hành lab: chuẩn bị RF=3 trên bốn node

Giả định môi trường **lab bốn node `cass-1` đến `cass-4` cùng `datacenter1`**, version tương thích, đủ disk, và đã cho phép thao tác phá hủy topology. Không chuyển `datacenter1` từ ví dụ sang production nếu tên DC thực tế khác.

Tạo keyspace và bảng theo truy vấn một partition cụ thể:

~~~sql
CREATE KEYSPACE IF NOT EXISTS topology_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS topology_lab.probe_by_tenant (
    tenant_id text,
    bucket date,
    event_id uuid,
    marker text,
    payload text,
    PRIMARY KEY ((tenant_id, bucket), event_id)
);
~~~

- `(tenant_id, bucket)` là **composite partition key**; mọi lệnh đọc mẫu chỉ truy vấn một partition.
- `event_id` là clustering key có định danh UUID ổn định.
- `marker` giúp so kết quả với **manifest kỳ vọng lưu ngoài Cassandra**.
- Bảng không dùng TTL, `DELETE` hay cập nhật đồng thời trong thử nghiệm đầu, để dễ phân biệt mất hàng do topology với thay đổi nghiệp vụ.
- `IF NOT EXISTS` không sửa keyspace/bảng đã có. Nếu chạy lại, xác nhận RF và schema trước khi tiếp tục.

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'topology_lab';
~~~

Nạp dữ liệu trong lúc bốn node đều `UN`. Trong `cqlsh`, `CONSISTENCY` là **lệnh giao diện cqlsh**, không phải câu CQL:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO topology_lab.probe_by_tenant
    (tenant_id, bucket, event_id, marker, payload)
VALUES ('tenant-a', '2026-11-21',
    11111111-1111-4111-8111-111111111111,
    'baseline-A', 'first-known-event');

INSERT INTO topology_lab.probe_by_tenant
    (tenant_id, bucket, event_id, marker, payload)
VALUES ('tenant-a', '2026-11-21',
    22222222-2222-4222-8222-222222222222,
    'baseline-B', 'second-known-event');
~~~

`ALL` ở RF3 cần ba replica của mỗi partition xác nhận, **không** yêu cầu cả bốn node nếu node thứ tư không phải replica. Chỉ ghi nhận `ACK_ALL` cho từng câu lệnh nếu `cqlsh` trả về thành công. Timeout có nghĩa kết quả **chưa xác định**, không được tự xem là dữ liệu chưa ghi.

Đọc baseline:

~~~sql
SELECT event_id, marker, payload
FROM topology_lab.probe_by_tenant
WHERE tenant_id = 'tenant-a' AND bucket = '2026-11-21';
~~~

Biên bản kỳ vọng cho `tenant-a/2026-11-21`:

| event_id | marker | Kết quả ghi |
| --- | --- | --- |
| `11111111-1111-4111-8111-111111111111` | `baseline-A` | ACK/UNKNOWN thực nhận |
| `22222222-2222-4222-8222-222222222222` | `baseline-B` | ACK/UNKNOWN thực nhận |

Lưu manifest và timestamp, keyspace, RF/CL, topology, host ID, lỗi vào **log ngoài cluster**. Mỗi lần chạy lại cần đổi tenant/bucket hoặc event ID và manifest để không dùng lại dữ liệu của lần trước.

## 6. Kịch bản A: decommission node khỏe

### 6.1. Điều kiện

Node `cass-4` đang **`UN`**, lưu trữ hoạt động, có kết nối mạng tốt; ba node `cass-1..3` đủ tài nguyên giữ RF3 sau khi `cass-4` rời. Không có thay đổi topology hoặc repair lớn khác đang tranh tài nguyên. Mục tiêu là **giảm từ bốn xuống ba node**, không phải thay một node bằng node mới.

### 6.2. Các bước

Trên node còn sống, lưu baseline:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
~~~

Sau đó, **chạy lệnh trên chính node `cass-4` dự định rời ring**:

~~~bash
# Chạy bên trong cass-4 của LAB, KHÔNG chạy trên cass-1/2/3.
nodetool decommission
~~~

Quá trình này thường liên quan đến thay đổi trạng thái ring/gossip và **truyền các dữ liệu cần thiết đến những node sẽ nhận ownership**. Đợi công việc quản trị hoàn tất theo logs và trạng thái cluster. Một lệnh chạy lâu không có nghĩa đã treo; cũng không tự ý kill tiến trình hoặc chạy lệnh decommission lần nữa khi chưa xác định trạng thái.

~~~mermaid
sequenceDiagram
    participant Ops as Người vận hành
    participant N4 as cass-4 (đang sống)
    participant Cluster as Cluster
    participant Dest as Node nhận token range
    Ops->>Cluster: Kiểm tra RF/disk/topology
    Ops->>N4: nodetool decommission
    N4->>Cluster: Bắt đầu rời membership
    N4->>Dest: Stream dữ liệu cần chuyển
    Dest-->>N4: Nhận dữ liệu / tiến độ
    N4-->>Cluster: Hoàn tất rời ring theo cơ chế phiên bản
    Cluster-->>Ops: Kiểm tra trạng thái và dữ liệu sau thay đổi
~~~

Trong lúc thực hiện, quan sát từ **các node vẫn ở lại**:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
~~~

Điều mong đợi sau khi hoàn tất:

- `cass-4` không còn là thành viên bình thường của ring; **ba node còn lại `UN`**.
- Schema/replication của keyspace vẫn có RF3 và placement mới chỉ định ba node còn lại.
- Các truy vấn có partition key vẫn trả dữ liệu kỳ vọng khi những replica còn sống đáp ứng CL.
- Dung lượng các node còn lại tăng phù hợp với streaming; không có bất thường kéo dài về timeout, pending compaction và ổ đĩa.

**Không coi việc `nodetool decommission` trả về thành công là bằng chứng toàn bộ dữ liệu nghiệp vụ đã được kiểm chứng.** Phải kiểm tra manifest, RF/CL, trạng thái streaming/compaction và sức khỏe sau thay đổi. Việc rút một node không tự thực hiện đối soát nguồn ngoài cluster.

## 7. Kịch bản B: removenode khi node đã chết vĩnh viễn

### 7.1. Tình huống và điều kiện

Bắt đầu từ **một bản sao lab độc lập ban đầu** bốn node `UN`, RF3; **không chạy ngay sau kịch bản A** khi cluster chỉ còn ba node. Giả sử `cass-4` mất hoàn toàn do hỏng phần cứng, không thể restart hoặc phối hợp `decommission`. Cluster cần giảm về ba node mà không thay máy.

Trước khi chọn `removenode`:

1. Xác nhận `cass-4` thực sự **không thể/sẽ không được quay lại**, không chỉ bị phân vùng mạng.
2. Kiểm tra số replica còn đủ dữ liệu nguồn; nếu không còn bản sao đáng tin, cần restore/backfill thay vì giả định có thể stream từ node đã chết.
3. Lưu host ID **đúng** của `cass-4` từ `nodetool status` và tài liệu quản trị.
4. Xác minh ba node khác khỏe, đủ disk và throughput cho RF3.
5. Có kế hoạch ngăn node cũ với dữ liệu/host ID cũ tham gia ring sau khi bị loại.

### 7.2. Mô phỏng trong lab

Trên host Docker lab, giả sử container tên `cass-4`:

~~~bash
# Chỉ dừng node trong lab; không tạo tình huống split-brain sản xuất.
docker kill --signal=KILL cass-4
~~~

Trên một node sống, quan sát:

~~~bash
nodetool status
~~~

Chờ cho `cass-4` hiện `DN` (*Down/Normal*). Lưu cột **Host ID** của nó. Nếu chưa rõ host ID, dừng lại: `removenode` nhận host ID, **không nhận IP hoặc nickname cass-4**.

Chạy lệnh từ **một node khỏe khác, chẳng hạn `cass-1`**, với host ID thực lấy từ trạng thái:

~~~bash
# Thay <HOST_ID_CASS_4> bằng UUID thật, tuyệt đối không dùng giá trị ví dụ.
nodetool removenode <HOST_ID_CASS_4>
~~~

Ví dụ `nodetool status` ở mục 3 hiển thị một UUID giả; **không đưa UUID giả đó vào lệnh thật**. Khi removenode diễn ra, Cassandra thay đổi metadata/token ownership và **các replica còn sống** xử lý dữ liệu cần được chuyển sang node có trách nhiệm mới. Vì node đích bị loại đã down, nó không thể là nguồn streaming.

Theo dõi trong lúc chạy:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats

# Trên các phiên bản nodetool có hỗ trợ cú pháp này:
nodetool removenode status
~~~

`removenode status` có thể phản ánh tiến độ thao tác remove; trạng thái chi tiết và tham số CLI phụ thuộc phiên bản, nên cần kiểm tra trợ giúp `nodetool help removenode` nếu khác. Nếu phiên xử lý báo lỗi hoặc treo, **không dùng tùy chọn force/assassinate theo thói quen**: phải đánh giá streaming, nguồn replica, tài nguyên và hướng dẫn xử lý sự cố cho đúng phiên bản trước khi ép xóa metadata.

### 7.3. Không đưa node cũ quay lại

Sau khi `removenode` thành công, metadata cluster không còn chấp nhận node cũ như một thành viên bình thường. **Không chỉ `docker start cass-4` với dữ liệu/hệ thống cũ**, vì danh tính và token của nó đã bị loại khỏi ring. Nếu cần bốn node trở lại, hãy đi theo **bootstrap node mới hoặc replace/rebuild** phù hợp topology/phiên bản, với dữ liệu được đồng bộ an toàn.

Nếu node bị loại từng bỏ lỡ tombstone lâu hơn `gc_grace_seconds`, việc cho trở lại với SSTable cũ còn tạo nguy cơ **zombie data**. Không giải quyết bằng cách tự xóa vài file metadata/SSTable rồi thử lại.

## 8. Khi nào nên replace thay vì giảm node?

**Replace** phù hợp khi node hỏng nhưng cluster **vẫn cần cùng số node và năng lực**. Ví dụ:

- RF=3 trên **đúng ba node**: loại bỏ vĩnh viễn một node để còn hai node thường không phải phương án duy trì RF3 hợp lệ.
- Ba node còn lại sau lỗi đã gần đầy đĩa hoặc CPU cao: `removenode` có thể không đủ headroom.
- Yêu cầu rack/DC placement không thể đáp ứng nếu bỏ một node: cần giữ vị trí replica.

Với node down cần thay, quy trình replacement sẽ phụ thuộc phiên bản, seed/snitch, IP/host ID và cấu hình startup; một số phiên bản dùng cơ chế `replace_address_first_boot` hoặc lựa chọn thay node tương đương. **Không sao chép một flag khởi động duy nhất cho mọi phiên bản Cassandra.** Phải dùng tài liệu đúng phiên bản, kiểm soát danh tính node cũ và xác minh data streaming/bảo toàn replication.

| Mục đích | Rút node ra | Duy trì số node/capacity |
| --- | --- | --- |
| Node khỏe | `decommission` có thể phù hợp | Lập kế hoạch replace, không nhất thiết decommission |
| Node hỏng vĩnh viễn | `removenode` nếu RF/disk còn đủ | Replacement/rebuild từ replica khỏe hoặc backup |
| Node hỏng tạm, có thể sửa | Không vội đổi ring | Khôi phục node, kiểm tra hints/repair |

**Thay IP không đồng nghĩa cần `removenode`.** Có thể cần thay node, cập nhật cấu hình mạng hoặc xử lý gossip; hãy xác định mục tiêu membership và dữ liệu trước khi chọn thao tác.

## 9. Xác minh sau decommission/removenode

### 9.1. Không đồng nhất năm mốc hoàn thành

| Mốc quan sát | Đúng là đã biết | Chưa đủ chứng minh |
| --- | --- | --- |
| Công cụ `nodetool` trả về thành công | Thao tác quản trị báo hoàn tất theo cơ chế CLI | Toàn bộ dữ liệu nghiệp vụ không thiếu |
| `nodetool status` không còn node cũ | Membership/token metadata đã thay đổi | Mọi replica mới đã được đối soát byte dữ liệu |
| `netstats` không còn streaming | Không còn streaming được quan sát tại mốc kiểm tra | Không còn khác biệt replica hoặc mất dữ liệu lịch sử |
| `SELECT` trả marker ở `LOCAL_QUORUM` | Truy vấn đáp ứng CL và trả marker đúng | Mọi replica đều đã có marker |
| Repair hoàn tất phạm vi liên quan + đối soát manifest | Có bằng chứng mạnh hơn về hội tụ và dữ liệu kỳ vọng | Event chưa từng ghi ở bất kỳ nguồn tin cậy sẽ được repair sinh ra |

### 9.2. Kiểm tra trạng thái, tải và dữ liệu

Trên node còn sống:

~~~bash
nodetool status
nodetool describecluster
nodetool netstats
nodetool compactionstats
~~~

Trong `cqlsh`:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT event_id, marker, payload
FROM topology_lab.probe_by_tenant
WHERE tenant_id = 'tenant-a'
  AND bucket = '2026-11-21';
~~~

So từng cặp `event_id/marker` với manifest **đã lưu bên ngoài Cassandra**. Với một cluster production, cần đối soát có giới hạn theo các partition/bucket quan trọng thay vì `SELECT COUNT(*)` toàn bảng, vì truy vấn toàn tập có thể rất tốn tài nguyên.

Sau thay đổi topology, lập kế hoạch **repair theo hướng dẫn phiên bản và phạm vi keyspace/range cần đồng bộ**. Repair có chi phí CPU, network, disk, streaming và compaction; một lệnh chạy trên một node không tự chứng minh cả cluster đã repair toàn bộ. Không tự động chạy full repair cùng lúc nhiều node trong giờ tải cao.

### 9.3. Hành vi đọc/ghi ở các CL

Với bốn node ban đầu RF3, sau khi rút đúng một node để còn ba node khỏe và vẫn RF3:

- `LOCAL_QUORUM` cần **2/3 ACK**; nên kiểm chứng read/write latency và timeout ở tải thực.
- `ALL` cần **3/3 ACK**; trong giai đoạn node/streaming chưa sẵn sàng, có thể giảm availability. Không mặc định tăng CL lên ALL là “cách chứng minh mọi dữ liệu đã an toàn”.
- `LOCAL_ONE` có thể trả dữ liệu từ một replica; nó không phải cách kiểm tra hội tụ trên mọi bản sao.

Nếu một write trước đây **timeout**, sự kiện vẫn có thể đã tới một số replica. Đừng tính timeout thành sự kiện mất dữ liệu hoặc tự retry non-idempotent. Các giá trị `marker` đã ACK và nguồn sự kiện nghiệp vụ cần được lưu riêng để quyết định backfill an toàn.

## 10. Ảnh hưởng lên Java Driver và xử lý sự cố ứng dụng

Ứng dụng Java dùng Cassandra Java Driver 4.x thường có cơ chế khám phá topology, metadata, token-aware routing và connection pools. Khi node rời ring:

1. Driver có thể tạm nhận lỗi kết nối hoặc thay đổi route trong lúc topology cập nhật.
2. Đường đọc/ghi ở CL yêu cầu có thể timeout khi streaming/compaction tranh tài nguyên.
3. Các prepared statement và session có thể được tái sử dụng; **không cần tự xây danh sách node tĩnh cho từng truy vấn** nếu đã cấu hình discovery/load balancing đúng.
4. Không coi mọi timeout là `NOT_WRITTEN`: nếu thao tác không idempotent hoặc tạo side effect ngoài Cassandra, retry có thể gây sai nghiệp vụ.
5. Theo dõi latency, unavailable, timeout, node availability và tốc độ cập nhật metadata của driver.

Mẫu Java dưới đây chỉ xác minh **các event ID đã biết**, tránh quét toàn bảng:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.Map;
import java.util.UUID;

public final class TopologyVerification {
    public enum Result { MATCH, MISSING, MISMATCH, READ_ERROR }

    private final CqlSession session;
    private final PreparedStatement select;

    public TopologyVerification(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT marker FROM topology_lab.probe_by_tenant " +
            "WHERE tenant_id = ? AND bucket = ? AND event_id = ?");
    }

    public Result check(String tenantId, LocalDate bucket,
                        UUID eventId, String expectedMarker) {
        BoundStatement stmt = select.bind(tenantId, bucket, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        try {
            Row row = session.execute(stmt).one();
            if (row == null) {
                return Result.MISSING;
            }
            return expectedMarker.equals(row.getString("marker"))
                ? Result.MATCH : Result.MISMATCH;
        } catch (RuntimeException error) {
            System.err.printf(
                "READ_ERROR event=%s type=%s%n",
                eventId, error.getClass().getSimpleName());
            return Result.READ_ERROR;
        }
    }

    public void verifyManifest(String tenantId, LocalDate bucket,
                               Map<UUID, String> expected) {
        for (Map.Entry<UUID, String> item : expected.entrySet()) {
            Result result = check(
                tenantId, bucket, item.getKey(), item.getValue());
            System.out.printf("event=%s result=%s%n",
                item.getKey(), result);
        }
    }
}
~~~

Phân biệt rõ:

- `MATCH`: giá trị đọc được ở `LOCAL_QUORUM` khớp marker mong đợi.
- `MISSING`: truy vấn thành công nhưng không trả hàng cho khóa đó.
- `MISMATCH`: trả hàng nhưng marker sai; phải điều tra ghi đè, timestamp, keyspace hoặc nguồn expected.
- `READ_ERROR`: timeout, unavailable hoặc lỗi khác; **không** cộng vào số hàng bị thiếu.

Code không tự khẳng định dữ liệu per-replica đã đồng bộ hoàn toàn. Với manifest lớn, cần giới hạn tốc độ và concurrency; số lần gọi CQL có thể lớn nếu kiểm tra từng event. Khi mục tiêu là chứng minh độ đầy đủ nghiệp vụ, đối soát phải dựa trên nguồn sự kiện đáng tin, không chỉ các hàng có mặt trong Cassandra.

## 11. Rủi ro đặc biệt và cách dừng an toàn

| Dấu hiệu/rủi ro | Cách đánh giá | Hành động ưu tiên |
| --- | --- | --- |
| Đang `DN` nhưng chưa chắc chết vĩnh viễn | Kiểm tra network partition, disk, dịch vụ và plan restart | Đừng `removenode` vội; sửa lỗi và khôi phục |
| Một DC còn ít node hơn RF | Placement không còn đáp ứng cấu hình | Dừng kế hoạch thu nhỏ; bổ sung node hoặc replace |
| Tụt dung lượng đĩa khi streaming | SSTable mới, compaction, snapshot giữ dữ liệu | Giảm tải, đánh giá headroom; không ép major compaction khi thiếu disk |
| Pending compaction/streaming kéo dài | I/O/network nghẽn, repair khác chạy cùng | Điều chỉnh lịch bảo trì, kiểm tra lỗi; không force remove thiếu căn cứ |
| Hints còn tồn tại cho node bị loại | Mutation chưa được phát lại hoặc hết khả năng phát lại | Xem logs, repair/đối soát; không xem hints là nguồn sao lưu |
| Replica cũ bỏ lỡ xóa quá `gc_grace_seconds` | Tombstone có thể đã bị purge, nguy cơ zombie | Đánh giá rebuild/replace, không để node stale tự rejoin |
| Một marker đã ACK nhưng đọc thiếu sau đổi topology | Nguồn replica, routing, timestamp, lỗi streaming/repair | Dừng rollout, giữ bằng chứng, kiểm tra manifest và logs |
| `removenode` thất bại | Thiếu source replica, lỗi stream, coordinator/node hỏng | Điều tra theo phiên bản; không dùng force/assassinate tùy tiện |

**Rollback không phải luôn đảo chiều được.** Sau decommission/removenode, host ID/token placement đã đổi và một phần dữ liệu có thể được stream sang nơi khác. Để trở lại bốn node, thường phải **thêm/bootstrap/replace node** theo quy trình mới, không đơn giản khởi động lại máy cũ với data directory/identity trước đó.

Không chạm thủ công các bảng hệ thống hoặc file token/SSTable để ép node “quay về” ring. Nếu thao tác đang dở và cluster không ổn định, cần lưu logs/traces/metrics và tham chiếu quy trình recovery của đúng Cassandra version.

## 12. Bài thực hành và câu hỏi tự kiểm tra

**Bài 1 — Chọn lệnh.** Với RF3 và bốn node khỏe, công ty muốn giảm một node. Bạn chọn `decommission` hay `removenode`? Lệnh chạy trên node nào? Điều kiện nào phải đạt về disk, streaming và read/write CL?

**Bài 2 — Node DN tạm thời.** Một node `DN` do mất kết nối trong 10 phút nhưng vẫn có thể hoạt động lại. Vì sao `removenode` là lựa chọn quá sớm? Hãy lập checklist network, gossip, disk, logs và hints trước khi phục hồi node.

**Bài 3 — Node hỏng hoàn toàn.** Một node `DN` không còn đĩa/không thể startup. Giải thích vì sao `nodetool decommission` không phù hợp và `nodetool removenode <host_id>` phải chạy trên node còn sống. Nêu cách xác thực host ID trước thao tác.

**Bài 4 — Giới hạn RF.** Ba node một DC đều là replica ở RF3; muốn giảm còn hai node. Tại sao không thể giữ nguyên cả năng lực đặt ba replica sau đó? Lựa chọn an toàn hơn là gì?

**Bài 5 — Tiến độ và dữ liệu.** Khi `nodetool status` không còn cass-4 và `nodetool netstats` không có streaming, đã đủ khẳng định toàn bộ dữ liệu nghiệp vụ không thiếu chưa? Thiết kế manifest expected, truy vấn theo partition key, repair coverage và báo cáo `MATCH/MISSING/MISMATCH/READ_ERROR`.

**Bài 6 — Ứng dụng Java.** Khi driver nhận write timeout trong lúc removenode, có được ghi log `NOT_WRITTEN` và phát lại mọi request không? Hãy phân biệt `ACKNOWLEDGED`, `UNKNOWN` và cách dùng operation ID để kiểm tra tính idempotent.

**Bài 7 — Đổi topology kết hợp tombstone.** Node bỏ lỡ `DELETE` quá lâu và có nguy cơ zombie. Nếu muốn thay node này, cần lưu ý gì về `gc_grace_seconds`, repair, rebuild và việc không cho data directory cũ quay lại?

## Ghi nhớ

**`decommission` dùng để cho node còn sống chủ động rời ring; `removenode <host_id>` dùng để loại bỏ node đã down và không thể trở lại, với công việc tái phân phối trên các replica còn sống.** Khi mục tiêu là duy trì capacity, hãy đánh giá **replace** thay vì giảm số node. Trước mọi thay đổi, kiểm tra topology, RF theo DC, CL, dung lượng, bản sao dữ liệu và khả năng stream; sau thay đổi, xác minh cả membership, latency và **marker dữ liệu kỳ vọng**. Một lệnh `nodetool` hoàn tất không thay thế việc đối soát và bảo trì replica.
