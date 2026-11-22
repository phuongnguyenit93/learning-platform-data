# Trạng thái nút và vòng đời gia nhập, rời hoặc bị thay thế trong Apache Cassandra

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đọc đúng hai chiều **Status** và **State** của `nodetool status`: `U/D` phản ánh khả năng liên lạc, còn `N/J/L/M` phản ánh trạng thái thành viên của token ring.
2. Phân biệt node tạm thời mất liên lạc (`DN`) với node đã được **decommission**, **removenode** hoặc **replace**; hiểu vì sao Cassandra không tự xóa thành viên khỏi ring chỉ vì node bị DOWN.
3. Trình bày vòng đời của **node mới bootstrap**: khám phá cluster, nhận token/vnode, stream các token ranges, chuyển từ `UJ` sang `UN`.
4. Biết khi nào dùng `nodetool decommission` cho node **còn sống**, `nodetool removenode` cho node **đã chết**, và quy trình **replace** để đưa node mới vào vị trí node cũ.
5. Giải thích tác động của replication factor (RF), datacenter/rack, streaming, hints, repair và cleanup đối với tính sẵn sàng và tính nhất quán khi thay đổi topology.
6. Theo dõi tiến trình bằng `nodetool status`, `netstats`, logs, driver metadata và các chỉ số latency/timeout thay vì suy từ một flag duy nhất.
7. Thiết kế **runbook có điều kiện trước/sau, điểm dừng và kế hoạch xử lý lỗi**, không thực thi lệnh phá hủy trên production khi chưa xác minh node và phạm vi ảnh hưởng.
8. Hiểu ứng dụng Java Driver 4.x phản ứng ra sao với thay đổi topology, connection pool, token-aware routing và mức consistency.

Bài thuộc chương **Thay đổi topology** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Mô-đun tập trung vào kiến trúc phân tán và wide-column của Apache Cassandra: partition key, thiết kế bảng theo truy vấn, consistency đọc/ghi, CQL, replication, compaction, repair, sự cố và Java client. Bài này nói về **quản trị vòng đời node** chứ không phải thay đổi schema hoặc tối ưu một câu `SELECT` đơn lẻ.

> **Phạm vi an toàn:** Các lệnh `nodetool` thay đổi topology bên dưới là **ví dụ runbook để học và xét duyệt**, không phải hướng dẫn chạy trực tiếp trên một cluster chưa rõ trạng thái. Chỉ thao tác sau khi có quyền vận hành, xác minh phiên bản, RF/DC, tình trạng replica, backup/khả năng phục hồi và quy trình thay đổi được phê duyệt.

## 1. Vòng token và thành viên cluster

### 1.1. Từ partition key đến replica

Trong Cassandra:

- **Partition key** được partitioner chuyển thành **token**; token xác định vị trí logic trong token ring.
- Mỗi node có thể sở hữu **nhiều virtual nodes (vnodes)**, tức một tập token/ranges, tùy `num_tokens` và cách phân bổ token.
- **Replication strategy** và RF quyết định token range có những replica nào; ở nhiều DC, `NetworkTopologyStrategy` còn xét RF từng DC và cách bố trí rack.
- **Coordinator** nhận truy vấn, xác định replica phù hợp với partition key và consistency level, rồi điều phối đọc/ghi.

Mô hình đơn giản:

```text
                  Token ring (minh họa)
              +-----------------------+
              |                       |
        Node A (token ranges)    Node B (token ranges)
              |                       |
              +------ Node C ---------+
                     |
                     v
              Replica placement

Partition key (account_id, event_day)
              |
          hash/token
              |
       các replica theo RF/DC/rack
              |
        đọc/ghi qua coordinator
```

Đừng đồng nhất **“node giữ token range”** với **“node là bản sao duy nhất của dữ liệu range ấy”**. Một range có nhiều replica; việc node gia nhập hay rời khiến **replica placement** có thể thay đổi.

### 1.2. Gossip, failure detector và membership

Cassandra sử dụng cơ chế trao đổi trạng thái giữa node (gossip) và failure detector để đưa ra nhận định về khả năng liên lạc. Nhưng có **hai câu hỏi độc lập**:

1. **Node có thể liên lạc không?** Một node có thể được nhìn là Up hoặc Down **từ góc nhìn của node quan sát**.
2. **Node ở giai đoạn nào của vòng đời ring?** Joining, Normal, Leaving, Moving hoặc đã bị loại khỏi membership.

Khi node mất liên lạc:

```text
Normal + Up = UN
        |
        | mất heartbeat / không liên lạc được
        v
Normal + Down = DN
        |
        +--> phục hồi thành Up/Normal nếu không bị loại
        |
        +--> operator quyết định replace hoặc removenode
               sau khi xác định node thật sự không trở lại
```

**DN không có nghĩa node đã rời ring.** Cassandra không tự tái phân phối vĩnh viễn toàn bộ token ranges chỉ vì một node tạm thời DOWN: tránh di chuyển dữ liệu không cần thiết do sự cố mạng ngắn. Quyết định loại bỏ hoặc thay thế là **thao tác vận hành rõ ràng**.

**Tính cục bộ của Up/Down:** Hai node quan sát có thể tạm thời nhìn trạng thái Up/Down khác nhau, đặc biệt khi có network partition hoặc gossip chưa hội tụ. Vì vậy không kết luận toàn cluster từ `nodetool status` chạy trên đúng một máy khi nghi có sự cố mạng.

## 2. Đọc đúng nodetool status

Lệnh quan sát cơ bản:

```bash
nodetool status

# Có thể nêu keyspace để xem phần sở hữu hiệu dụng theo replication
# của keyspace ấy, tùy phiên bản Cassandra.
nodetool status app_events
```

Ví dụ **output giả lập**:

```text
Datacenter: dc1
====================
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address      Load      Tokens  Owns (effective)  Host ID          Rack
UN  10.1.0.11    78 GiB    16      55.0%             <uuid-node-a>    rack1
UN  10.1.0.12    84 GiB    16      50.0%             <uuid-node-b>    rack2
UJ  10.1.0.14    12 GiB    16      ?                 <uuid-node-d>    rack3
DN  10.1.0.13    81 GiB    16      48.0%             <uuid-node-c>    rack3
```

Các địa chỉ `10.1.0.x`, phần trăm và `<uuid-node-x>` ở trên là **minh họa**, không phải kết quả từ cluster đang chạy. Với `status` thật, dạng cột và cách hiển thị `Owns (effective)` khác nhau theo phiên bản/đối số keyspace.

### 2.1. Hai ký tự đầu được hiểu thế nào?

| Ký tự | Nhóm | Ý nghĩa |
| --- | --- | --- |
| `U` | Status | Up: node quan sát cho rằng endpoint liên lạc được. |
| `D` | Status | Down: node quan sát cho rằng endpoint không liên lạc được. |
| `N` | State | Normal: thành viên bình thường của ring. |
| `J` | State | Joining: node đang gia nhập/bootstrap. |
| `L` | State | Leaving: node đang rời ring/decommission. |
| `M` | State | Moving: node đang chuyển vị trí token, khi thao tác/phiên bản hỗ trợ. |

Các tổ hợp hay gặp:

| Hiển thị | Cách diễn giải | Có thể làm gì tiếp? |
| --- | --- | --- |
| `UN` | Up/Normal | Trạng thái thường mong đợi của node đang phục vụ. |
| `UJ` | Up/Joining | Kiểm tra streaming/bootstrap, chưa coi là hoàn tất gia nhập. |
| `UL` | Up/Leaving | Decommission đang diễn ra; theo dõi stream và membership. |
| `UM` | Up/Moving | Có chuyển động token; kiểm tra phiên bản, tiến trình và mục đích. |
| `DN` | Down/Normal | Node được ghi nhận trong ring nhưng không liên lạc được theo góc nhìn hiện tại. |
| `DJ`/`DL` | Down/Joining hoặc Down/Leaving | Tác vụ bị gián đoạn hoặc không liên lạc; cần điều tra, không tự động force. |

Sau khi **rời ring thành công**, node cũ thường **không còn xuất hiện** như một thành viên trong output bình thường. Nó **khác** với `DN` — thành viên vẫn hiện diện nhưng đang Down.

### 2.2. Các cột còn lại cần đọc với ngữ cảnh

- **Address:** endpoint nội bộ; một cluster có thể dùng port/broadcast address riêng tùy phiên bản, không đồng nhất địa chỉ IP với Host ID.
- **Load:** lượng dữ liệu cục bộ được báo cáo, không phải số byte logic duy nhất của cluster.
- **Tokens:** số token/vnodes node giữ. Không coi đây là RF hoặc số partition.
- **Owns (effective):** phần sở hữu có tính đến replication và keyspace; không nhất thiết cộng 100% qua mọi node, nhất là khi RF lớn hơn một.
- **Host ID:** định danh node trong cluster; **khác IP**. Quan trọng với `removenode`.
- **Rack/DC:** vị trí logic dùng cho placement và network topology; cấu hình sai có thể ảnh hưởng replica diversity.

**Ví dụ sai:** nhìn `DN 10.1.0.13` rồi chạy ngay `nodetool removenode 10.1.0.13`. Trong các phiên bản phổ biến, `removenode` yêu cầu **Host ID**, không phải địa chỉ IP.

## 3. Sơ đồ vòng đời: joining, normal, leaving, dead/replaced

```text
       Cài node mới, cấu hình sạch
                  |
                  v
             Joining (UJ)
          chọn token, streaming
                  |
          bootstrap hoàn tất
                  v
             Normal (UN)
              /      \
             /        \ ngừng liên lạc
            /          v
     decommission    Down/Normal (DN)
          |               |
          v               +--> hồi phục --> UN
     Leaving (UL)         |
          |               +--> replace dead node
          |               |        |
          v               |        v
   Rời membership         |    node mới stream
   (không còn row)         |        |
                          |        v
                          |       UN
                          |
                          +--> removenode từ node sống
                                   |
                                   v
                          rút thành viên chết khỏi ring
```

Đây là **sơ đồ logic**, không hứa mọi phiên bản hiển thị đủ các trạng thái trung gian ở mọi thời điểm. Thao tác replace có các giai đoạn mà `status` từ các node khác có thể tạm cho thấy `DN`; `nodetool netstats` và logs trên node thay thế là nguồn tiến độ quan trọng.

### 3.1. Các thao tác không đồng nghĩa

| Hành động | Node đích | Mục đích | Có thay membership/token placement? |
| --- | --- | --- | --- |
| Restart Cassandra | Node hiện hữu | Khởi động lại dịch vụ | Thông thường **không**, nếu cấu hình/identity giữ nguyên. |
| `nodetool drain` | Node đang chạy | Flush/chuẩn bị dừng có kiểm soát | **Không phải decommission**. |
| Bootstrap | Node **mới** | Gia nhập ring và nhận range | **Có**. |
| `nodetool decommission` | Node **còn sống** | Rút hẳn khỏi cluster, stream dữ liệu | **Có**. |
| `nodetool removenode <host-id>` | Node **đã chết** | Loại membership của node chết, bù replica từ node còn sống | **Có**. |
| Replace node | Node mới thay node **đã chết** | Tiếp quản vị trí/tokens của node chết và stream dữ liệu | **Có**, nhằm thay thế vị trí đó. |
| `nodetool cleanup` | Các node còn giữ dữ liệu không thuộc ownership mới | Xóa dữ liệu cục bộ không còn thuộc node sau khi xác minh an toàn | **Không thay membership**. |
| `nodetool repair` | Node/replica theo scope repair | Đồng bộ dữ liệu giữa replica | **Không tự add/remove node**. |

Một node DOWN do bảo trì trong vài phút không trở thành node “bị loại” chỉ vì operator đã dừng Cassandra. Nếu đã định khởi động lại, **không chạy decommission/removenode/replace**.

## 4. An toàn trước mọi thay đổi topology

### 4.1. Preflight vận hành

Trước khi thêm/rút/thay node, cần xác minh:

1. **Đúng cluster:** cluster name, environment, datacenter, rack, endpoints; không thao tác nhầm lab/staging/production.
2. **Đúng node:** address **và** Host ID, chức năng node, node có thực sự còn sống hay mất liên lạc?
3. **Phiên bản/compatibility:** phiên bản Cassandra, phương thức thay node và chính xác các flags/`nodetool` được hỗ trợ.
4. **Replication:** mỗi keyspace dùng chiến lược gì, RF từng DC là bao nhiêu, còn đủ replica sống để đáp ứng consistency và streaming không?
5. **Dung lượng:** free disk, memory, CPU, network và dung lượng dự phòng trên các node sẽ nhận thêm ranges.
6. **Cluster health:** có các node khác DOWN, repair/compaction/streaming đang kéo dài hoặc pending tasks lớn không?
7. **Khả năng phục hồi:** snapshot/backup, restore runbook, monitoring, rollback/forward recovery và người phê duyệt.
8. **Ứng dụng:** p95/p99 đọc/ghi, timeout, retry, QPS và pool kết nối có ngân sách để chịu movement không?
9. **Thứ tự:** chỉ làm **một topology operation có liên quan tại một thời điểm** trừ khi có cơ chế orchestration được kiểm chứng; tránh nhiều range movement đồng thời làm replica thiếu dữ liệu.

Các lệnh quan sát phổ biến:

```bash
# CHỈ ĐỌC: chạy trên node phù hợp với quyền JMX.
nodetool status
nodetool describecluster
nodetool netstats
nodetool tpstats
nodetool compactionstats

# Có thể quan sát token/rack/host ID theo phiên bản:
nodetool ring
nodetool gossipinfo
```

Trong môi trường khóa JMX, `nodetool` cần thông tin host/port/credential. Không đưa mật khẩu trực tiếp lên command line nếu quy trình quản trị cung cấp password file hoặc secret manager phù hợp. Không lưu stdout chứa địa chỉ nội bộ/Host ID lên kho log công khai.

### 4.2. Dung lượng và RF là chốt chặn quan trọng

Giả sử DC `dc1` chỉ có **ba node** và một keyspace đặt `RF=3`. Nếu decommission vĩnh viễn một node mà không tăng capacity, DC còn hai node vật lý; không thể duy trì ba bản sao phân biệt cho mỗi partition. `nodetool decommission` ở phiên bản hiện đại có thể từ chối và hỗ trợ tùy chọn `--force`, nhưng **ép rút không tạo ra replica thứ ba**.

Nguyên tắc: **đảm bảo RF có thể đạt được sau thay đổi topology**, hoặc thay đổi RF theo phương án dữ liệu có kiểm soát. Không dùng `--force` để bỏ qua một bất biến về an toàn dữ liệu.

### 4.3. Metadata và quyền sở hữu có thể chưa hội tụ ngay

Khi một node đang Joining/Leaving, các node khác hoặc Java client có thể chưa quan sát cùng trạng thái tại cùng một mili-giây. Các command điều tra nên được thực hiện từ **nhiều node quan sát** khi nghi gossip/mạng bất thường; đồng thời đọc logs và tiến độ stream trên node đích.

Đừng đặt automation kiểu “thấy UN đúng một lần thì lập tức cleanup và đóng ticket”. Cần xác minh **streaming hoàn tất**, tính sẵn sàng ổn định, read/write lỗi trong ngưỡng và replica coverage phù hợp.

## 5. Thêm node mới: bootstrap và trạng thái UJ → UN

### 5.1. Khi nào cần thêm node?

- Dung lượng đĩa hoặc throughput đang tiến gần giới hạn an toàn.
- Cần phân phối thêm tải đọc/ghi hoặc mở rộng một DC hiện hữu.
- Triển khai capacity để sau đó decommission node cũ có kiểm soát.

Thêm node **không sửa được ngay một hot partition cực lớn** nếu khóa phân vùng của ứng dụng làm dữ liệu tập trung. Một partition vẫn được đặt vào các replica theo token của nó; scale-out có thể không chia nhỏ chính partition ấy.

### 5.2. Cấu hình cần chuẩn bị

Một node mới cần những giá trị phù hợp cluster thực, ví dụ:

```yaml
# ĐÂY LÀ TRÍCH ĐOẠN MINH HỌA, KHÔNG PHẢI cassandra.yaml hoàn chỉnh.
cluster_name: 'orders-prod'            # phải trùng tên cluster hiện hữu
listen_address: 10.1.0.14              # endpoint nội bộ thực của node mới
rpc_address: 0.0.0.0                    # cần kiểm soát firewall và broadcast_rpc_address
num_tokens: 16                         # ví dụ; chọn theo chiến lược/phiên bản thực
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "10.1.0.11,10.1.0.12"
endpoint_snitch: GossipingPropertyFileSnitch
```

Ví dụ trên **chỉ phục vụ đọc hiểu**; không chép nguyên vào production. Cần cấu hình chính xác `broadcast_address`, `broadcast_rpc_address`, DC/rack, TLS, authentication, encryption, ports, data/commitlog/cache paths, JVM và network policies theo bản cài.

Các điểm phải phân biệt:

- **Seed nodes** giúp **khám phá** cluster khi khởi động; chúng không phải “master” và không tự là replica duy nhất của mọi token.
- **Datacenter/rack** cần đúng để replication strategy đặt bản sao theo topology; sửa sai snitch/DC sau khi node đã chứa dữ liệu là tác vụ riêng có rủi ro.
- **`num_tokens`** quy định lượng vnode của node, không phải replication factor. Giá trị/tối ưu allocator phụ thuộc phiên bản và workload; không tự giả định tất cả cluster phải có 256 tokens.
- Node mới thường cần **data directory sạch và identity mới**. Không copy bừa `system` keyspace/Host ID từ node khác sang, tránh hai node mang cùng định danh.
- Đừng tự đặt `auto_bootstrap: false` để bỏ qua streaming; đó là chế độ chuyên biệt chỉ dùng theo runbook phục hồi/khởi tạo đặc thù.

### 5.3. Diễn tiến bootstrap

```text
Node mới chuẩn bị cấu hình / storage sạch
            |
            v
Kết nối seed/gossip, học topology/ring
            |
            v
Chọn token/vnodes và range mới phụ trách
            |
            v
Joining (UJ): nhận SSTable ranges qua streaming
            |
            v
Hoàn tất streaming, cập nhật ownership/replica placement
            |
            v
Up/Normal (UN), xác minh ổn định
```

Theo dõi:

```bash
# Trên node mới hoặc node quản trị phù hợp:
nodetool status
nodetool netstats

# Có thể dùng các command quan sát phụ để điều tra tải:
nodetool tpstats
nodetool compactionstats
```

`netstats` là nguồn thông tin quan trọng về các phiên streaming đang chạy. `status` cho thấy trạng thái membership, nhưng không nhất thiết trình bày đầy đủ tiến độ bootstrap/replace. Trong logs, tìm lỗi handshake, gossip, schema agreement, streaming failures, disk exhaustion hoặc endpoint/DC mismatch.

### 5.4. Sau khi node lên UN

Chỉ coi bootstrap hoàn tất sau khi:

1. `nodetool status` từ nhiều điểm quan sát cho thấy node mới `UN` ổn định.
2. `nodetool netstats` không còn transfer còn dang dở cho thao tác này.
3. Replica placement, RF/DC/rack và các keyspace mục tiêu đúng dự kiến.
4. Đọc/ghi thử có kiểm soát với consistency phù hợp thành công.
5. Latency, timeout, unavailable, pending tasks và disk load ở mức chấp nhận được.

Sau khi **range movement hoàn tất và được xác nhận**, một số node cũ có thể giữ dữ liệu cục bộ của ranges không còn thuộc chúng. Khi đó operator có thể lên lịch `nodetool cleanup` trên **các node mất quyền sở hữu ranges**, theo hướng dẫn phiên bản. **Không chạy cleanup khi bootstrap còn dở hoặc chưa xác minh coverage**, và không coi cleanup là bước tự động trên mọi node vô điều kiện.

### 5.5. Bootstrap thất bại hoặc bị gián đoạn

Nếu `UJ` kéo dài, đừng lập tức xóa data directory hay bắt đầu bootstrap lần hai:

- Kiểm tra `netstats`, logs, disk, network, nguồn stream và node đang DOWN.
- Đối chiếu phiên bản: `nodetool bootstrap resume` có thể hỗ trợ tiếp tục streaming.
- Với trạng thái bootstrap dở, `cassandra.reset_bootstrap_progress` có semantics nguy hiểm nếu dữ liệu stream trước đó còn trên đĩa; không bật `true`/`false` dựa trên phỏng đoán.
- Không vô hiệu hóa consistent range movement chỉ để “cho chạy tiếp” khi chưa đánh giá nguy cơ thiếu dữ liệu.

**Runbook khôi phục bootstrap phải theo phiên bản Cassandra đang dùng**, tốt nhất được thử trên staging có dữ liệu đại diện trước khi áp dụng production.

## 6. Rút một node còn sống: decommission và UL

### 6.1. Khi nào dùng decommission?

`nodetool decommission` dành cho **node đang chạy và có thể tham gia streaming**, khi operator muốn loại node ấy **vĩnh viễn** khỏi ring, ví dụ:

- Thu nhỏ cluster nhưng **vẫn đủ node cho RF** của mọi keyspace.
- Thay phần cứng theo kế hoạch bằng mô hình “thêm node trước, rút node cũ sau”.
- Đóng một node không còn cần thiết sau khi đảm bảo dữ liệu đã có replicas đích.

Không dùng để “restart service cho sạch” hoặc “tạm bảo trì hai phút”.

### 6.2. Quy trình logic

```text
Trước: Node A UN, Node B UN, Node C UN, Node D UN
                    |
          xác minh capacity/RF/health
                    |
             decommission Node D
                    |
             Node D chuyển UL
                    |
          stream data từ Node D theo ownership mới
                    |
          hoàn tất, rời token ring
                    |
          Node D không còn trong membership
```

Lệnh **chỉ minh họa**:

```bash
# NGUY HIỂM: thay đổi membership và dữ liệu.
# Chỉ chạy trên ĐÚNG node còn sống sẽ được rút (hoặc trỏ đúng -h),
# sau khi đã xác nhận RF/capacity, backup và phê duyệt.
nodetool decommission

# Quan sát từ các node CÒN ở lại:
nodetool status
nodetool netstats
```

Nếu dùng `nodetool -h <host> decommission`, `<host>` là **node sẽ được decommission**, không phải một "coordinator bất kỳ". Xác minh cẩn thận đích JMX trước khi chạy.

### 6.3. Điều gì thay đổi?

- Node đang rút có thể hiện `UL`.
- Dữ liệu cần thiết được stream từ node rút sang những node chịu trách nhiệm tiếp theo.
- Sau khi thành công, node đó **không còn trong ring**.
- **Dữ liệu cục bộ không tự bị xóa hết** sau decommission; không tái gia nhập cùng dữ liệu/identity cũ bằng cách khởi động tùy tiện.
- RF và lượng node còn lại quyết định cluster có duy trì được số replicas mong muốn không.

Nếu cần biến node cũ thành một node mới về sau, quy trình tái sử dụng ổ đĩa/cấu hình phải được chuẩn hóa; không mặc định “service đã tắt = node mới sạch”.

### 6.4. Khi decommission bị kẹt

Trước khi làm thao tác ép hoặc hủy, kiểm tra:

1. Source và target streaming có liên lạc, disk/network có đủ không?
2. Có node DOWN khiến việc chuyển ranges không hoàn thành không?
3. Replica target có đủ chỗ; RF có vượt số node còn lại không?
4. Logs đang báo lỗi gì? `nodetool netstats` còn transfer hay session lỗi nào?
5. Ứng dụng có đang gây tải lớn, khiến data movement không có băng thông?

**Không dùng `nodetool decommission --force` như cách xử lý mặc định.** Ở một số phiên bản, `--force` cho phép tiếp tục ngay cả khi số replica thấp hơn RF cấu hình; nó là một lựa chọn **giảm mức an toàn**, không phải phương pháp sửa vấn đề tải hoặc thiếu node.

## 7. Node DOWN: nên phục hồi, thay thế hay loại bỏ?

### 7.1. DN là triệu chứng cần điều tra, chưa phải quyết định

```text
nodetool status từ Node A:

DN  10.1.0.13  ...  <host-id-C>  rack3
```

Trước tiên phân biệt:

- **Tạm mất mạng / JMX / process:** node có thể trở lại cùng dữ liệu/Host ID, chưa cần thay đổi membership.
- **Mất hẳn máy/ổ đĩa:** cần replacement hoặc removal để phục hồi placement.
- **Network partition:** một số node thấy Down, số khác thấy Up; loại bỏ nhầm node còn sống có thể tạo xung đột hoặc mất dữ liệu.
- **Node dừng có kế hoạch:** cần biết runbook bảo trì, không tự chẩn đoán “đã chết vĩnh viễn”.

### 7.2. Bảng quyết định

| Tình huống | Phương án điển hình | Điều kiện bắt buộc |
| --- | --- | --- |
| Node tắt/restart ngắn, dữ liệu còn nguyên | **Khôi phục node cũ** | Identity và storage hợp lệ; gossip/replica được xác minh. |
| Muốn rút node **đang Up** vĩnh viễn | **Decommission** | Có đủ RF/capacity, streaming hoàn tất. |
| Node **chết hẳn**, muốn máy mới giữ vị trí node cũ | **Replace** | Node cũ không còn chạy, nguồn stream đủ, cấu hình/flag đúng phiên bản. |
| Node **chết hẳn**, không thay trực tiếp vị trí đó | **Removenode** | Đủ replica sống để re-replicate, Host ID đúng, có giám sát. |
| Node Down do split-brain, chưa rõ ai đang sống | **Dừng quyết định topology**, điều tra | Không thực hiện remove/replace khi còn nguy cơ node cũ quay lại. |
| Dữ liệu mất và chỉ còn một replica đang Down | **Quy trình khôi phục/backup**, không force removal | Đánh giá nguy cơ mất bản sao cuối cùng. |

Lựa chọn replace hay removenode phụ thuộc mục tiêu topology cuối, capacity, thời gian gián đoạn và yêu cầu consistency. **Không cộng cả hai thao tác cho cùng một node một cách tùy tiện**.

## 8. Loại node đã chết bằng removenode

### 8.1. Khác decommission ở chỗ nào?

Với `decommission`, **node rời còn sống** và tham gia gửi dữ liệu. Với `removenode`, **node đã chết không stream được**; Cassandra cần sử dụng các replica còn sống để bù dữ liệu và cập nhật membership.

Trước khi gọi removenode:

- Xác nhận node đích thực sự không còn có thể phục hồi.
- Ghi đúng **Host ID** từ `nodetool status` và kiểm tra trên nhiều node.
- Kiểm tra các replica khác còn đủ dữ liệu/health để tái sao chép.
- Dự trù disk/network và tác động consistency của việc mất một bản sao.
- Xác nhận **không có thao tác replacement cùng Host ID/token location đang chạy**.

### 8.2. Ví dụ runbook, không thực thi trên cluster thật

```bash
# ĐỌC: chạy từ một node đang sống có quyền quản trị.
nodetool status

# NGUY HIỂM: xóa thành viên đã chết khỏi ring.
# Thay chuỗi giả bằng Host ID THẬT của node đã chết.
nodetool removenode 00000000-0000-4000-8000-0000000000cc

# Theo dõi tiến độ removal/streaming:
nodetool removenode status
nodetool netstats
nodetool status
```

UUID trong lệnh trên là **giả lập**, không tương ứng một node nào của cluster. Cú pháp `removenode status` và `removenode force` phụ thuộc phiên bản nhưng được tài liệu chính thức mô tả ở nhiều bản hiện hành.

### 8.3. Rủi ro khi force hoặc dùng sai Host ID

Nếu node đã chết chứa những bản cập nhật chưa kịp chuyển tới replica sống, việc loại nó có thể làm thiếu dữ liệu. Trên một số bản, `removenode force` cưỡng bức kết thúc tiến trình removal, **không** bảo đảm đã re-replicate đủ dữ liệu.

**Không dùng `nodetool assassinate` như một “removenode nhanh”.** Đây là lựa chọn cuối cùng có thể xóa membership mà **không re-replicate**, chỉ phù hợp quy trình khẩn cấp có đánh giá mất dữ liệu và phê duyệt đặc biệt.

Nếu node cũ bất ngờ được bật lại **sau khi đã bị remove**, không kết nối nó vào cluster như một node bình thường với metadata cũ. Cần quy trình cách ly/khôi phục đúng phiên bản và kiểm tra Host ID/token ownership.

## 9. Thay thế node đã chết bằng một node mới

### 9.1. Thế nào là replacement?

**Replace** không đồng nghĩa add một node bất kỳ rồi delete node cũ. Trong trường hợp điển hình, node mới được cấu hình để **tiếp nhận vị trí/token ranges của node đã chết** và stream dữ liệu cần thiết từ replica khác.

Kịch bản:

```text
Trước:
   Node A UN
   Node B UN
   Node C DN   <-- máy C đã mất hẳn

Replacement:
   Xác minh C thực sự offline
   Chuẩn bị máy D với data directory sạch
   D bắt đầu với replacement address = C
   D bootstrap dữ liệu từ A/B theo ownership
   Theo dõi netstats / logs / gossip

Sau:
   Node A UN
   Node B UN
   Node D UN   <-- vị trí C được thay theo semantics phiên bản
   C không được phép khởi động lại vào cluster
```

### 9.2. Flags và cấu hình theo phiên bản

Trong tài liệu topology changes của Apache Cassandra 4.x/5.x, phương thức điển hình là khởi động **node mới** với JVM system property:

```text
-Dcassandra.replace_address_first_boot=<dead_node_ip>
```

Thay `<dead_node_ip>` bằng **địa chỉ thật của node đã chết** theo semantics phiên bản/config. Đây là **tham số startup** của Cassandra, không phải câu lệnh CQL và không phải lệnh chạy trên node còn sống.

Một số tài liệu cấu hình còn mô tả `cassandra.replace_address`; cách dùng chính xác phụ thuộc bản Cassandra. **Không thay thế hai tên cờ theo phỏng đoán**: xác minh release/config và runbook đang sử dụng trước khi khởi động.

**Điều kiện tối thiểu:**

1. Node C đã chết thực sự, không còn có thể chạy đồng thời với D.
2. D có môi trường/cấu hình đúng cluster, datacenter/rack, seed và storage **đúng tiêu chuẩn node mới**.
3. D không tái dùng bất cẩn dữ liệu `system`/Host ID của một node khác.
4. Những replica còn sống có thể cung cấp dữ liệu để stream.
5. Có phương án đối soát dữ liệu và repair khi cửa sổ mất node kéo dài.

### 9.3. Replacement có thể trông như DN trong một giai đoạn

Theo tài liệu vận hành Cassandra, node thay thế có thể bắt đầu ở trạng thái **hibernate**; các node khác thấy endpoint liên quan ở trạng thái Down/Normal trong một khoảng, trong khi node mới tự thấy mình Up. Do đó:

- Không đoán replacement “đứng im” chỉ từ một dòng `DN` trong `status` ở một node khác.
- Đọc `nodetool netstats` của node đang thay thế để xem tiến độ streaming.
- Xác minh logs, traffic và token ranges đang nhận.
- Chỉ đánh dấu hoàn tất khi bootstrap xong và trạng thái membership/traffic ổn định.

### 9.4. Same IP và different IP có rủi ro khác nhau

Theo tài liệu topology:

- Node thay thế bằng **IP khác** có thể nhận writes trong giai đoạn bootstrap theo điều kiện của phiên bản.
- Khi **tái sử dụng IP cũ**, hành vi nhận writes trong replacement có điểm khác; cửa sổ downtime kéo dài làm tăng nguy cơ bỏ sót write.
- Nếu node chết lâu hơn cửa sổ hints (`max_hint_window` theo tên cấu hình tương ứng phiên bản) hoặc replacement same-IP vượt khoảng đó, tài liệu yêu cầu **repair** để bù các write bị bỏ lỡ.

Vì thế phải xem **thời điểm node cũ chết, thời điểm replacement hoàn thành, thời gian hints giữ được và trạng thái repair**. Không nhận định “lên UN là dữ liệu chắc chắn đầy đủ” trong mọi trường hợp.

### 9.5. Sau replacement

Checklist:

1. Node D lên `UN` ổn định khi quan sát từ nhiều node.
2. `netstats` không còn streaming pending của replacement.
3. Kiểm tra RF/replica placement ở các keyspace và DC/rack mục tiêu.
4. Chạy **repair theo runbook** nếu có điều kiện bỏ lỡ writes/hints hoặc nghi dữ liệu chưa hội tụ; không dùng repair như cách sửa mọi vấn đề cấu hình.
5. Kiểm tra read/write bằng prepared queries/consistency của ứng dụng và các số liệu latency/timeout.
6. Chỉ sau đó mới cân nhắc cleanup tại các node mất ranges do movement, nếu áp dụng.
7. Đảm bảo **node cũ không thể khởi động lại** với identity/địa chỉ gây xung đột.

## 10. Streaming, hints, repair và cleanup: bốn việc khác nhau

### 10.1. Streaming chuyển dữ liệu thuộc ranges

Bootstrap, decommission, replacement và removal có thể khởi tạo **streaming** SSTable ranges để đặt dữ liệu vào đúng replica mới.

```text
Old replica(s)                  New responsible replica
      |                                  |
      |---- stream các token ranges ---->|
      |                                  |
      |    cập nhật ownership/membership |
      |--------------------------------->|
```

Streaming có thể ảnh hưởng network, disk, compaction/flush và client latency. Thời gian stream không chỉ phụ thuộc số GB lý thuyết: tombstones, SSTable fragmentation, checksum/transfer errors, scheduling và node chậm đều có thể làm lệch tiến độ.

### 10.2. Hints không thay repair

Trong một số đường ghi, Cassandra lưu **hints** cho replica đang tạm không sẵn sàng và cố gửi lại trong cửa sổ được cấu hình. Hints:

- Hỗ trợ một số tình huống mất replica ngắn hạn.
- Không phải lịch sử thay đổi vĩnh viễn hay bảo đảm lưu được **mọi** write trong mọi thời gian outage.
- Không thay thế repair sau downtime lâu hoặc replacement có nguy cơ bỏ lỡ writes.

Nếu operator không biết downtime/hints window, không nên đánh dấu replacement đã nhất quán chỉ dựa vào `nodetool status`.

### 10.3. Repair đối soát replica, không thay membership

Repair tìm và đồng bộ chênh lệch dữ liệu giữa replicas theo scope/phiên bản. Ví dụ command khái niệm:

```bash
# Có thể rất tốn I/O/network; thực thi theo lịch/runbook,
# không tự chạy trên toàn cluster ngay sau mọi tình huống.
nodetool repair <keyspace>
```

Cần định nghĩa keyspace, incremental/full repair, phạm vi DC, concurrency và sự tương thích version. Không viết “chạy repair ở một node là đủ cho toàn cluster” khi chưa có kế hoạch coverage cụ thể.

### 10.4. Cleanup thu hồi dữ liệu không còn thuộc ownership

Sau khi movement thành công, những node **mất** ranges có thể còn SSTables chứa dữ liệu thuộc ranges đó. `cleanup` dọn các dữ liệu không còn thuộc node:

```bash
# Chỉ làm SAU khi xác nhận placement/movement hoàn tất.
# Chạy trên node cần cleanup theo kế hoạch; tốn I/O.
nodetool cleanup <keyspace>
```

Không chạy cleanup trong lúc bootstrap/replace/decommission còn bất ổn, và không coi cleanup là đồng nghĩa repair. Xóa nhầm dữ liệu cần thiết trước khi placement an toàn có thể gây hậu quả nghiêm trọng.

## 11. Vùng nguy hiểm: những hành động không được làm theo phản xạ

| Tình huống | Phản xạ nguy hiểm | Vì sao |
| --- | --- | --- |
| Một node hiện `DN` vài phút | `removenode` ngay | Có thể chỉ là mất mạng; loại membership khi node có thể hồi phục. |
| Node mới bootstrap chậm | Xóa data directory rồi start lại | Có thể làm mất tiến độ/dữ liệu, tạo trạng thái bootstrap dở nguy hiểm. |
| Còn 2 node với `RF=3` | Decommission node thứ ba bằng `--force` | Không thể duy trì ba replica phân biệt, tăng rủi ro mất dữ liệu. |
| Node replace chưa xong | Cho node cũ khởi động lại | Nguy cơ xung đột ownership/identity và inconsistency. |
| Không biết Host ID | Dùng IP làm đối số `removenode` | Sai semantics của lệnh, có thể nhầm node/đích. |
| Dữ liệu mới vừa stream | Cleanup tất cả ngay | Chưa xác minh đủ replicas và range ownership. |
| Hints window đã hết | Tin rằng node mới UN đồng nghĩa đủ mọi write | Các write bỏ lỡ cần đối soát/repair. |
| Một trace/trạng thái nhìn từ một node | Kết luận toàn cluster thống nhất | Up/Down là đánh giá cục bộ; gossip có thể chưa hội tụ. |
| Đang có bootstrap/decommission | Chạy thêm movement không liên quan tùy ý | Nhiều movement đồng thời có thể đè tải và nguy hiểm cho replica coverage. |
| Query ứng dụng timeout | Chỉ tăng timeout/retry | Nếu streaming/cluster quá tải, retry gây khuếch đại tải. |

**Điểm dừng vận hành:** khi không thể xác minh điều kiện “node cũ thật sự chết”, “RF đủ”, “streaming không mất nguồn” hoặc “backup/restore đã thử”, **dừng thao tác phá hủy** và điều tra/đưa lên quy trình sự cố.

## 12. Quan sát thay đổi topology: một dashboard tối thiểu

### 12.1. Các công cụ quan sát

| Công cụ | Câu hỏi giúp trả lời |
| --- | --- |
| `nodetool status` | Node Up/Down, Joining/Normal/Leaving; host ID, rack/DC? |
| `nodetool netstats` | Streaming ranges đang gửi/nhận, tiến độ và network work? |
| `nodetool describecluster` | Cluster name, schema versions, metadata overview? |
| `nodetool gossipinfo` | Gossip application states giữa các endpoint? |
| `nodetool ring` | Token placement/ownership theo cách nhìn công cụ? |
| `nodetool tpstats` | Pending/blocked work ở các thread pools? |
| `nodetool compactionstats` | Compaction đang làm gì, có backlog lớn không? |
| Cassandra system/debug logs | Lỗi bootstrap/streaming, gossip, seed, disk, schema, transport? |
| Client + server metrics | p95/p99 latency, retries, timeouts, unavailable, pending reads/writes? |

**Ví dụ thực hành quan sát không phá hủy:**

```bash
# Chạy từ node phù hợp, có quyền JMX và log access.
nodetool status
nodetool netstats
nodetool describecluster
nodetool tpstats
```

Lặp quan sát ở các thời điểm trong quá trình, không lấy một ảnh chụp `status` duy nhất. Với các node không đồng ý nhau về Up/Down, kiểm tra DNS/broadcast address, firewall, internode TLS, port, clock và logs thay vì ép membership.

### 12.2. Ví dụ bảng theo dõi tiến độ

| Thời điểm | Node | Status/State | Streaming | p99 API | Quyết định |
| --- | --- | --- | --- | --- | --- |
| T0 | D | Chưa có trong ring | Chưa chạy | Baseline | Cho phép chuẩn bị |
| T1 | D | `UJ` | Đang nhận | Theo dõi | Tiếp tục giám sát |
| T2 | D | `UN` | Đã hoàn tất | Trong ngưỡng | Bắt đầu kiểm chứng |
| T3 | D | `UN` ổn định | Không còn pending | Trong ngưỡng | Đóng thay đổi/cleanup có điều kiện |

T0–T3 là **mốc logic**, không có thời lượng định sẵn; không bịa tốc độ stream hoặc SLA dựa vào kích thước token. Một node nhận vài GB và một node nhận hàng TB có yêu cầu thời gian/tài nguyên rất khác nhau.

### 12.3. Ngưỡng và rollback/forward recovery

Trước khi bắt đầu, định nghĩa:

- Ngưỡng p95/p99, read/write timeout và unavailable cho ứng dụng.
- Dung lượng trống an toàn và tối đa streaming throughput.
- Concurrency limit cho bootstrap/repair/cleanup; kế hoạch giảm tải ghi/đọc nếu bão retry.
- Tiêu chí **pause**/dừng thao tác trước những bước không thể đảo chiều.
- Kế hoạch **forward recovery** khi decommission/removenode đã cập nhật membership: không mặc định có thể “undo” như transaction SQL.

**Một số lệnh topology không có rollback một bước**. Thao tác khôi phục có thể yêu cầu bootstrap/replacement mới hoặc restore từ backup, không chỉ restart node cũ.

## 13. Tác động tới Java Driver và truy vấn đang chạy

### 13.1. Driver quan sát topology, nhưng không thay operator quyết định

Java Driver 4.x có metadata các node và cơ chế khám phá topology. Khi node joining/leaving hoặc bị down:

- Driver có thể cập nhật topology và connection pools theo sự kiện từ Cassandra.
- Token-aware routing tìm replica cho partition key khi metadata đầy đủ.
- In-flight requests có thể timeout/unavailable nếu replica hoặc coordinator thay đổi khả năng phục vụ.
- Prepared statements và metadata có thể cần cập nhật theo cơ chế driver; ứng dụng không tự quản lý cluster bằng cách cố gắng gọi lại một IP cứng duy nhất.

Tuy nhiên, **driver metadata không phải nguồn chuẩn để ra lệnh removenode/decommission**. Operator vẫn cần quan sát Cassandra ring/streaming/host ID bằng công cụ vận hành.

### 13.2. Ví dụ Java: xem metadata node

Ví dụ **Java 17 + Apache Cassandra Java Driver 4.x**:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.net.InetSocketAddress;

// Ví dụ minh họa kết nối, không phải cấu hình production hoàn chỉnh.
try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("10.1.0.11", 9042))
        .withLocalDatacenter("dc1")
        .build()) {

    // Driver metadata có thể cập nhật bất đồng bộ sau topology changes.
    for (Node node : session.getMetadata().getNodes().values()) {
        System.out.printf(
            "id=%s dc=%s rack=%s state=%s endpoint=%s%n",
            node.getHostId(),
            node.getDatacenter(),
            node.getRack(),
            node.getState(),
            node.getEndPoint());
    }
}
```

**Chú ý:** Driver's `NodeState` (ví dụ Up/Down/Unknown) không phải tổ hợp hai ký tự `UN/UJ/UL` của `nodetool status`. Đừng lấy `node.getState()` để suy bootstrap đã hoàn tất và trực tiếp điều khiển topology.

Production cần nhiều contact points, TLS/authentication, retry policy, timeout và monitoring đúng topology; đoạn code trên chỉ minh họa việc đọc metadata.

### 13.3. Ví dụ query Java khi node đang chuyển

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

// Giả định đã có session hợp lệ và keyspace "app_events".
PreparedStatement query = session.prepare("""
    SELECT occurred_at, event_id, event_type
    FROM events_by_account_day
    WHERE account_id = ? AND event_day = ?
    """);

BoundStatement bound = query.bind(
    UUID.fromString("11111111-1111-4111-8111-111111111111"),
    LocalDate.parse("2026-11-20")
).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setIdempotent(true);

Row first = session.execute(bound).one();
if (first != null) {
    System.out.println(first.getUuid("event_id"));
}
```

Đoạn này minh họa prepared SELECT theo **full partition key**. Không bảo đảm `LOCAL_QUORUM` sẽ khả dụng nếu RF/DC và số replica sống không đáp ứng yêu cầu. `setIdempotent(true)` nói với retry policy về tính chất truy vấn, **không** cho phép retry vô hạn hoặc biến toàn bộ chuỗi đọc thành transaction.

Trên cluster có RF=3 trong DC đang đọc, `LOCAL_QUORUM` thường cần **2 replica** phản hồi phù hợp; nếu chỉ một replica sống, request có thể báo `Unavailable`. Trong replacement/bootstrap, mức consistency và tình trạng replica có thể ảnh hưởng latency; không thay đổi consistency tùy tiện chỉ để tắt lỗi mà không hiểu yêu cầu dữ liệu.

### 13.4. Những điều ứng dụng cần theo dõi

| Tín hiệu ứng dụng | Điều có thể xảy ra khi topology đổi | Cách phản ứng |
| --- | --- | --- |
| p99 đọc/ghi tăng | Streaming cạnh tranh disk/network hoặc coordinator/replica bị tải | Giảm concurrency batch, giám sát, điều chỉnh lịch thay đổi. |
| `Unavailable` | Không đủ replica đạt consistency | Kiểm tra RF, node health, không retry mù quáng. |
| `ReadTimeout`/`WriteTimeout` | Replica chậm, tắc hoặc đang movement | Backoff có giới hạn, tránh retry storm. |
| Prepared query theo keyspace lỗi | Schema agreement/config chưa hội tụ hoặc lỗi query | Kiểm tra schema/driver, không coi là tự động sửa bằng bootstrap. |
| Driver thấy node vừa xuất hiện | Discovery/metadata cập nhật | Xác minh node thực sự `UN` bằng nodetool/netstats. |
| Lỗi ảnh hưởng một tenant/hot partition | Một token/range cụ thể bị tác động | Dùng partition key, token routing và metrics xác định phạm vi. |

Không nên hardcode một endpoint duy nhất làm “node master” cho ứng dụng: Cassandra không có single-master node theo nghĩa đó. Cũng không nên tự gọi `nodetool` từ request HTTP ứng dụng để “chữa” node down.

## 14. Thực hành theo kịch bản: đọc trước, quyết định sau

### Kịch bản A — Thấy DN khi trực bảo trì

**Bối cảnh:** `nodetool status` cho thấy một node `DN`, nhưng đội vận hành thông báo đang restart service.

**Các bước suy luận:**

1. Xác minh thay đổi bảo trì đã được đăng ký, node có đang restart không.
2. Xem `status` từ vài node khác; kiểm tra gossip, network và logs.
3. Theo dõi node quay lại `UN` và đọc/ghi phục hồi ở consistency ứng dụng.
4. **Không** chạy `decommission` hoặc `removenode` cho một lần restart dự kiến.

**Kết quả đúng:** DN có thể là sự kiện tạm thời, membership không nhất thiết đổi.

### Kịch bản B — Cần thêm một node vì disk cao

**Bối cảnh:** Một DC còn đủ RF, tất cả node `UN`, cần tăng capacity.

**Các bước suy luận:**

1. Đo capacity, bố trí rack/DC, lựa chọn vnodes và cấu hình node mới.
2. Khởi động node sạch với bootstrap bình thường; theo dõi `UJ`, `netstats` và logs.
3. Khi `UN`, kiểm tra replica placement, metrics read/write, consistency.
4. Lên lịch cleanup **có điều kiện** trên các node giữ ranges thừa.
5. Giám sát sau thay đổi, ghi nhận Host ID mới và version/topology baseline.

**Điểm dừng:** một replica nguồn không khả dụng, streaming không tiến hoặc disk đích thiếu chỗ.

### Kịch bản C — Muốn rút một node còn sống

**Bối cảnh:** Có bốn node trong DC với keyspace RF=3; muốn giảm còn ba node.

**Các bước suy luận:**

1. Xác minh từng keyspace/DC vẫn đủ ba node và capacity sau rút.
2. Xác minh node đích `UN`, cluster không có movement/song song bất thường.
3. Chỉ trên node đích, decommission theo runbook.
4. Theo dõi `UL`, `netstats`, lỗi/latency và trạng thái membership.
5. Khi hoàn tất, node đã rời không còn trong `status`; xử lý dữ liệu cục bộ theo quy định.

**Điểm dừng:** decommission làm thiếu replica, stream failures hoặc không có khả năng phục hồi.

### Kịch bản D — Node chết vĩnh viễn

**Bối cảnh:** Server và storage của node C hỏng, không thể bật lại.

**Các bước suy luận:**

1. Xác minh identity, cách ly node C, ghi lại thời điểm outage, RF/consistency và hints window.
2. Quyết định **replace** nếu muốn capacity ở vị trí cũ; **removenode** nếu muốn loại membership và redistribution từ replicas còn sống.
3. Chỉ thực hiện **một** hướng đã phê duyệt; theo dõi streaming và phạm vi dữ liệu.
4. Sau hoàn tất, kiểm tra replica placement/repair khi cần và test ứng dụng.

**Điểm dừng:** không còn đủ replicas làm nguồn hoặc chưa chắc node C thật sự không thể quay lại.

## 15. Bài tập và lời giải

### Bài 1. Phân biệt UN, UJ, UL và DN

**Đề:** Một status mẫu có:

```text
UN  10.1.0.11
UJ  10.1.0.14
UL  10.1.0.12
DN  10.1.0.13
```

Giải thích bốn dòng và cho biết dòng nào **chứng minh node đã hoàn toàn rời ring**.

**Đáp án:** `UN` Up/Normal; `UJ` Up/Joining; `UL` Up/Leaving; `DN` Down/Normal. **Không dòng nào** chứng minh node đã rời ring hoàn toàn; khi membership đã được loại, node cũ không còn xuất hiện như thành viên trong status thường.

### Bài 2. Down có tự động bị remove không?

**Đề:** Một node bị Down 10 phút do lỗi mạng rồi kết nối lại. Cassandra có bắt buộc phải bootstrap lại một node mới không?

**Đáp án:** **Không.** Failure detector đánh giá khả năng liên lạc, không tự xóa membership vì outage ngắn. Nếu node cũ và dữ liệu/identity còn hợp lệ, có thể phục hồi về `UN`. Remove/replace chỉ khi operator xác định điều kiện phù hợp.

### Bài 3. RF=3 trên ba node

**Đề:** Keyspace `NetworkTopologyStrategy`, DC `dc1` có RF=3 và đúng ba node. Muốn decommission một node, không thêm node khác. Có an toàn để giữ đủ ba replica không?

**Đáp án:** **Không**: còn hai node vật lý trong DC thì không thể duy trì ba bản sao phân biệt. Cần bổ sung capacity hoặc thay đổi thiết kế RF theo quy trình; `--force` không sinh thêm replica.

### Bài 4. Chọn đúng công cụ

**Đề:** Ghép tình huống với lệnh/quy trình:

1. Node khỏe nhưng sẽ nghỉ hẳn.
2. Node chết, muốn loại membership, không có máy thay đúng vị trí.
3. Node chết, có máy mới cần tiếp quản.
4. Node vừa mất liên lạc do restart có kế hoạch.

**Đáp án:** (1) `decommission`; (2) `removenode <host-id>` sau kiểm tra source replicas; (3) **replace** theo startup flag/runbook đúng phiên bản; (4) theo dõi **restart**, không remove membership.

### Bài 5. Host ID có bằng IP không?

**Đề:** Operator thấy node chết có `Address=10.1.0.13` và `Host ID=1234...`. Lệnh `removenode` cần giá trị nào?

**Đáp án:** **Host ID** đầy đủ được `nodetool status` cung cấp. IP chỉ là endpoint, không phải Host ID và không nên dùng thay thế. Xác minh danh tính từ nhiều node nếu nghi network partition.

### Bài 6. Node mới hiện UJ suốt nhiều giờ

**Đề:** Có nên bật ngay `auto_bootstrap: false` rồi restart để nó thành UN nhanh hơn?

**Đáp án:** **Không.** Bỏ bootstrap có thể khiến node chưa có dữ liệu ranges được giao. Kiểm tra `netstats`/logs, nguồn stream, disk/network, RF và phiên bản; xử lý resume/khôi phục theo runbook.

### Bài 7. Cleanup chạy lúc nào?

**Đề:** Vừa thêm node, thấy `UJ`. Muốn thu hồi disk trên các node cũ, có được gọi `nodetool cleanup` ngay không?

**Đáp án:** **Không.** Đợi movement/streaming hoàn tất, xác minh new node `UN` và replica placement an toàn. Chỉ cleanup trên những node/ranges phù hợp theo kế hoạch, có giám sát I/O.

### Bài 8. Repair sau replace

**Đề:** Một node chết vượt cửa sổ hints, replacement đã lên UN. Có thể kết luận dữ liệu luôn đầy đủ không?

**Đáp án:** **Không.** Theo hướng dẫn topology, outage vượt hints window có thể để lại writes bị bỏ lỡ; cần repair/đối soát theo runbook và xác minh consistency. `UN` phản ánh trạng thái node, không là chứng nhận mọi replica có cùng tập cell.

### Bài 9. Mất một node với LOCAL_QUORUM

**Đề:** RF=3 trong cùng DC; một node Down, hai node còn Up. Về số replica, `LOCAL_QUORUM` thường yêu cầu bao nhiêu phản hồi?

**Đáp án:** Thông thường cần `floor(3/2)+1 = 2` replica. Nếu hai replica phù hợp còn sống và đáp ứng, request có **khả năng** thành công, nhưng vẫn phụ thuộc token/placement, network và timeout. Một node Up nhìn trong status không chứng minh mọi truy vấn thành công.

### Bài 10. Vì sao status từ hai node khác nhau?

**Đề:** Node A nhìn Node C là DN, Node B nhìn Node C là UN. Nên chạy removenode ngay từ A không?

**Đáp án:** **Không.** Up/Down là đánh giá cục bộ; cần điều tra mạng, gossip và logs, xác minh node C thực sự sống hay bị phân vùng trước khi loại. Remove nhầm node có thể khiến dữ liệu/ownership bất ổn.

### Bài 11. Java Driver báo timeout khi bootstrap

**Đề:** Trong lúc thêm node, p99 tăng và Java thấy một số `ReadTimeout`. Có nên retry không giới hạn và tăng page size tối đa?

**Đáp án:** **Không.** Streaming có thể đang cạnh tranh I/O/network; retry không giới hạn khuếch đại tải. Dùng retry/backoff có giới hạn, giám sát consistency/replica và điều chỉnh concurrency/throttling của công việc topology.

### Bài 12. Decommission hay drain?

**Đề:** Bạn cần tắt một node để thay RAM, sẽ khởi động lại cùng ổ đĩa/config. Nên gọi `nodetool decommission` hay quy trình dừng có kiểm soát?

**Đáp án:** Quy trình **dừng/restart có kiểm soát** phù hợp; `nodetool drain` có thể là một bước theo runbook dừng. **Không decommission**, vì nó xóa membership và chuyển dữ liệu, trái mục tiêu bảo trì tạm thời.

## 16. Checklist triển khai và hậu kiểm

### Trước khi đổi topology

- [ ] Đã xác minh cluster, environment, DC/rack, version, node address **và Host ID**.
- [ ] Đã đối chiếu `nodetool status` từ nhiều điểm quan sát khi có bất thường.
- [ ] Đã xác định chính xác mục tiêu: **add**, **restart**, **decommission**, **replace** hay **removenode**.
- [ ] Đã bảo đảm RF/keyspace/DC, đủ replica sống và dung lượng trống sau thay đổi.
- [ ] Đã có backup/restore, runbook, lịch thay đổi, điểm dừng, người chịu trách nhiệm và liên lạc sự cố.
- [ ] Đã xác minh không có streaming/movement/repair bất thường đồng thời.
- [ ] Đã đo baseline p95/p99, timeouts, disk/network và client retry rate.

### Trong khi thay đổi

- [ ] Giám sát `status`, `netstats`, logs, compaction/threads và data movement.
- [ ] Không nhầm `UJ`/`UL` với `UN`, không nhầm `DN` với node đã rời ring.
- [ ] Không chạy `--force`/`assassinate`/`auto_bootstrap: false` vì muốn “đi nhanh”.
- [ ] Không khởi động lại node chết sau khi replacement đã tiếp quản mà chưa có kế hoạch cách ly.
- [ ] Kiểm soát concurrency, traffic, retries và điểm dừng nếu lỗi tăng.

### Sau thay đổi

- [ ] Membership/tokens/DC/rack đúng, không còn node cũ xuất hiện ngoài dự kiến.
- [ ] Node mới/thay thế `UN` ổn định; `netstats` không còn streaming chưa hoàn tất.
- [ ] Replica placement và consistency trên các keyspace trọng yếu được xác minh.
- [ ] Đã xác định có cần **repair** do outage/hints gap hay không.
- [ ] **Cleanup** chỉ được lên lịch sau khi ownership và dữ liệu đã an toàn.
- [ ] API Java, prepared queries, read/write thử, p95/p99 và error rate đạt điều kiện chấp nhận.
- [ ] Cập nhật inventory node, Host ID, topology baseline, logs và biên bản kết quả.

**Ghi nhớ:** `Up/Down` trả lời “node hiện liên lạc được không”, còn `Normal/Joining/Leaving/Moving` trả lời “node đang ở giai đoạn nào trong vòng đời ring”. **Node DOWN không tự động bị loại.** Thêm node cần bootstrap/streaming; rút node còn sống dùng decommission; node chết cần quyết định giữa replace và removenode dựa trên replica coverage. Mọi thay đổi topology phải được kiểm chứng bằng **membership, streaming, replication/consistency và metrics ứng dụng**, không chỉ bằng một dòng `UN`.

## Tài liệu tham khảo

- [Apache Cassandra — Adding, replacing, moving and removing nodes](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/topo_changes.html)
- [Apache Cassandra — Use Nodetool: status, gossip và các lệnh chẩn đoán](https://cassandra.apache.org/doc/latest/cassandra/troubleshooting/use_nodetool.html)
- [Apache Cassandra — nodetool status](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/status.html)
- [Apache Cassandra — nodetool netstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/netstats.html)
- [Apache Cassandra — nodetool decommission](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/decommission.html)
- [Apache Cassandra — nodetool removenode](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/removenode.html)
- [Apache Cassandra — nodetool cleanup](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/cleanup.html)
- [Apache Cassandra — nodetool bootstrap: resume](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/bootstrap.html)
- [Apache Cassandra — Architecture: Dynamo and failure detection](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html)
- [Apache Cassandra — cassandra-env.sh startup properties](https://cassandra.apache.org/doc/latest/cassandra/managing/configuration/cass_env_sh_file.html)
- [Apache Cassandra Java Driver 4.x — Manual](https://docs.datastax.com/en/developer/java-driver/4.17/manual/)
