# Lập lịch theo dung lượng, tải và gc_grace của dữ liệu

> **Chương:** Repair  
> **Phạm vi:** Apache Cassandra — cơ sở dữ liệu phân tán theo mô hình *wide-column*. Bài tập trung vào lập lịch **anti-entropy repair** trên các replica dựa vào dung lượng dữ liệu, tải đọc/ghi, khoảng bảo vệ tombstone và khả năng hoàn tất sau sự cố. Các ví dụ dùng CQL, `nodetool` và bối cảnh ứng dụng Java.

## 1. Vì sao repair cần được lập lịch?

Cassandra phân phối partition theo token và giữ nhiều bản sao (*replica*) dựa vào replication factor (RF). Một lệnh ghi được client xác nhận ở consistency level (CL) `LOCAL_QUORUM`, `QUORUM` hoặc `ONE` **không nhất thiết đã đến tất cả replica**. Một replica có thể tạm ngoại tuyến, mạng bị gián đoạn hoặc việc truyền hint đã hết cửa sổ hỗ trợ.

**Repair** là cơ chế so sánh và đồng bộ dữ liệu giữa các replica chịu trách nhiệm cho cùng một dải token. Nó giúp đưa những replica bỏ lỡ mutation về trạng thái nhất quán hơn. Một lượt repair thường tiêu thụ tài nguyên để xây/so sánh dữ liệu kiểm tra (chẳng hạn Merkle tree) và **stream** dữ liệu khác biệt khi cần; nó không phải một lệnh `SELECT` thông thường.

Có ba mục tiêu phải đạt cùng lúc:

1. **An toàn dữ liệu:** các replica cần được đối soát trước khi tombstone được phép bị thu hồi, để tránh dữ liệu đã xóa sống lại.
2. **Khả năng hoàn tất:** lịch phải đủ thời gian cho dữ liệu hiện hữu, số node, số dải token, RF và tốc độ repair thực tế.
3. **Sức khỏe cluster:** repair không được cạnh tranh I/O, CPU, mạng và compaction tới mức làm API đọc/ghi vi phạm SLO.

Một lịch kiểu “chạy `nodetool repair` vào Chủ nhật” thiếu thời gian dự phòng, kiểm tra phạm vi và điều kiện hoàn tất có thể không đáp ứng được cả ba mục tiêu trên.

### Repair không thay thế cơ chế nào?

| Cơ chế | Mục đích chính | Vì sao chưa thay được repair định kỳ? |
| --- | --- | --- |
| Consistency level (`ONE`, `LOCAL_QUORUM`, …) | Quy định số replica cần phản hồi cho request | Replica không tham gia hoặc không trả lời vẫn có thể thiếu mutation |
| Hinted handoff | Chuyển tiếp mutation cho replica vắng mặt trong điều kiện/thời hạn cho phép | Không bảo đảm phục hồi mọi trường hợp node vắng lâu |
| Read repair | Xử lý sai khác nhận ra trong đường đọc theo cơ chế phiên bản hỗ trợ | Chỉ xảy ra trên các phạm vi thực sự được đọc; dữ liệu lạnh có thể không được truy cập |
| Compaction | Gom các SSTable và loại bỏ phiên bản/dấu xóa đủ điều kiện | Không đối soát tất cả replica của một dải token |
| Snapshot/backup | Khôi phục dữ liệu khi hỏng, xóa nhầm hoặc cần phục hồi toàn hệ thống | Bản sao lưu không tự kiểm tra sự khác biệt giữa replica đang phục vụ |

**Repair là công việc bảo trì phân tán**, không phải lệnh chạy một lần rồi cluster luôn đồng nhất trong tương lai.

## 2. Mối liên hệ trực tiếp giữa repair và `gc_grace_seconds`

Khi xóa một cột hoặc hàng, Cassandra ghi **tombstone**. TTL hết hạn cũng có ngữ nghĩa dữ liệu chết và metadata cần được xử lý an toàn. Tombstone mang thông tin rằng bản ghi có timestamp cũ hơn phải được xem là đã xóa.

Xem ví dụ RF=3, replica A/B/C:

```text
T0: A, B, C chứa bản ghi event=v1.

T1: C offline; client DELETE được A và B xác nhận.
    A và B có tombstone, C vẫn còn v1.

T2: Hết thời gian bảo vệ xóa (gc grace), A/B compaction
    và loại bỏ tombstone khi đủ điều kiện cục bộ.

T3: C trở lại khi chưa repair; C giữ v1.
    Nếu không còn dấu xóa phù hợp để chặn v1, dữ liệu
    có thể được truyền hoặc đọc như dữ liệu sống ("zombie").
```

Thuộc tính bảng `gc_grace_seconds` đặt khoảng thời gian bảo vệ cho tombstone trước khi đủ tuổi xem xét thu hồi. **Qua grace không có nghĩa tombstone được xóa ngay:** còn phụ thuộc compaction và SSTable chồng lấp. Nhưng người vận hành **không được dựa vào khả năng tombstone tình cờ tồn tại lâu hơn** để trì hoãn repair.

Mục tiêu lập lịch cần được phát biểu bằng điều kiện có thể kiểm tra:

> **Mọi dải token/replica liên quan phải được repair thành công đủ thường xuyên để một replica bỏ lỡ xóa không vượt qua cửa sổ `gc_grace_seconds` trước khi được đồng bộ.**

### Dùng thời gian của *lần repair thành công*, không dùng giờ bắt đầu job

Một job khởi chạy mỗi tuần nhưng thường thất bại nửa chừng **không** đồng nghĩa dữ liệu được repair hằng tuần. Cần theo dõi:

- **Lần hoàn tất repair thành công gần nhất** theo keyspace/table và phạm vi token.
- Khoảng thời gian tối đa một phạm vi chưa được đối soát.
- Các dải token, node hoặc datacenter chưa được xử lý do job lỗi/bỏ sót.
- Thời gian phục hồi sau lỗi, tái chạy dải chưa thành công và khoảng trống lịch trình.

Nếu một bảng có `gc_grace_seconds` nhỏ nhất trong workload, lịch chung phải đủ an toàn cho bảng đó, hoặc xây **lịch riêng cho nhóm bảng**.

### Một cách tính ngân sách thời gian

Đặt:

- `G`: grace hiệu dụng cần bảo vệ, tính theo thời gian; ví dụ 10 ngày.
- `I`: khoảng cách dự kiến giữa các lần **bắt đầu** chu kỳ repair toàn phạm vi.
- `D`: thời gian dài nhất dự kiến để hoàn tất một chu kỳ (bao gồm phần tải cao).
- `F`: ngân sách cho node offline, job lỗi, retry hoặc thao tác khôi phục.
- `M`: khoảng đệm an toàn do số liệu đo chưa chắc chắn và các sự kiện không dự kiến.

Điều kiện lập kế hoạch bảo thủ:

```text
I + D + F + M < G
```

Đây là **quy tắc đặt ngân sách vận hành**, không phải thuật toán nội bộ của Cassandra. Nó cố ý đánh giá trường hợp có phạm vi được repair sớm trong một chu kỳ nhưng muộn trong chu kỳ sau. Khi lịch có nhiều worker, DC và dải token, cần theo dõi **khoảng cách thực giữa các lần thành công của từng phạm vi**, không chỉ thay tất cả bằng một con số bình quân.

Ví dụ `G = 10 ngày`:

| Thành phần | Ngân sách minh họa |
| --- | ---: |
| Chu kỳ khởi chạy `I` | 5 ngày |
| Hoàn tất repair `D` | 2 ngày |
| Xử lý lỗi/replica offline `F` | 1 ngày |
| Dự phòng `M` | 1 ngày |
| **Tổng** | **9 ngày** |

Lịch này để lại 1 ngày khoảng trống. Nếu thực tế repair mất 4 ngày, công thức không còn thỏa; phải **đổi lịch, tăng năng lực repair, giảm dữ liệu cần xử lý hoặc điều chỉnh grace theo kế hoạch đã kiểm chứng**.

Tình huống node ngoại tuyến lâu hơn `gc_grace_seconds` đặc biệt nguy hiểm: **không đơn giản đưa node cũ trở lại rồi mong một job repair trễ sẽ loại hết rủi ro zombie**. Cần đánh giá quy trình thay node/rebuild/khôi phục theo phiên bản Cassandra và trạng thái replica còn đáng tin cậy.

## 3. Dữ liệu nào thực sự phải repair?

Không thể lấy số row của một bảng rồi chia đều cho số node để kết luận lịch repair.

Cần xác định:

1. **Keyspace và replication strategy:** `NetworkTopologyStrategy` hay cơ chế khác; RF của **từng datacenter**.
2. **Phạm vi token:** vnodes, range ownership, số replica liên quan đến từng range và phạm vi primary range khi lập lịch.
3. **Dung lượng trên mỗi node:** bao gồm dữ liệu thực trong SSTable; nén, tombstone và các file liên quan làm số byte scan khác dữ liệu logic.
4. **Tốc độ thay đổi:** write throughput, update/delete, TTL và lượng mutation chưa có trên mọi replica.
5. **Kiểu repair và lịch trước đó:** incremental hay full; phần SSTable repaired/unrepaired ở phiên bản đang chạy.
6. **Topology đang thay đổi:** bootstrap, decommission, replace, move hoặc thêm DC có thể ảnh hưởng owner của token và phạm vi cần đối soát.

Ví dụ keyspace minh họa:

```cql
CREATE KEYSPACE IF NOT EXISTS app_repair_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
```

Nếu cụm thật có **hai datacenter**, hãy thiết kế chiến lược repair dựa trên RF mỗi DC và phạm vi repair thực tế; một lượt giới hạn ở DC1 **không tự chứng minh** dữ liệu ở DC2 đã được kiểm tra nếu chính sách cần bao phủ cả hai.

### Dung lượng logic, dung lượng trên replica và dữ liệu quét khác nhau

Giả sử một keyspace có 2 TiB dữ liệu logic được nhân bản RF=3. Con số khoảng 6 TiB dữ liệu nhân bản là **ước lượng đơn giản** trước khi tính nén, SSTable dư, compaction, tombstone và các bản sao snapshot.

Nhưng điều đó **không có nghĩa một lệnh repair sẽ truyền 6 TiB qua mạng**:

- Validation có thể phải đọc nhiều SSTable trên các replica.
- **Streaming** chủ yếu xảy ra khi phát hiện khác biệt; có thể rất ít nếu replica đồng nhất, hoặc rất lớn khi node bỏ lỡ nhiều mutation.
- Chi phí CPU/I/O của so sánh và chi phí network khi streaming là **hai thước đo khác nhau**.

Khi tính lịch, cần dựa trên **thời gian và tải của các lần repair đo được**, không suy ra số byte truyền bằng `logical_data × RF`.

## 4. Ước lượng thời gian chạy theo dung lượng và tốc độ thực tế

Một mô hình công suất đơn giản:

```text
T_ước_lượng = D_cần_kiểm_tra / V_hiệu_dụng + T_overhead
```

Trong đó:

- `D_cần_kiểm_tra`: số byte dự kiến phải đọc/đối chiếu trong phạm vi repair đã chọn; thu từ dữ liệu và lần chạy thử trên chính cluster.
- `V_hiệu_dụng`: thông lượng kiểm tra hiệu quả dưới **tải đọc/ghi bình thường**, không phải tốc độ tối đa của SSD khi chạy benchmark độc lập.
- `T_overhead`: trao đổi metadata, khởi động session, xử lý SSTable, đợi tài nguyên, anti-compaction và streaming phần khác biệt.

Đây là mô hình để **ước tính ngân sách**, không phải công thức đo chính xác thời gian repair của Cassandra. Các range được xử lý đồng thời có thể tranh chấp I/O; tăng parallelism không làm thời gian giảm tuyến tính.

### Ví dụ số liệu để dựng lịch

Một cluster minh họa có **6 node trong một datacenter**, RF=3. Số liệu telemetry từ thử nghiệm cho thấy mỗi node lưu khoảng **1,2 TiB** SSTable thuộc keyspace cần repair; trong một cửa sổ tải thấp, một lượt repair primary range trên một node thường mất **12–18 giờ**.

Chọn cách thử **tối đa 2 repair coordinator đồng thời**, hạn chế các primary range trùng lặp và kiểm soát tác động đến replica đang phục vụ truy vấn.

Một ước lượng sơ bộ, nếu phân thành ba lượt hai node và chờ từng lượt hoàn tất:

```text
3 đợt × 18 giờ = 54 giờ ≈ 2,25 ngày
Thêm overhead, retry và lịch ít tải -> dành 3 ngày hoàn tất.
```

Đây **không phải lời khẳng định** mỗi repair chỉ chạm dữ liệu trên node ra lệnh; repair còn tương tác với các replica khác giữ cùng dải token. Kết quả đo có thể thay đổi mạnh nếu repair coordinator của hai đợt cùng kích hoạt validation/streaming trên những replica trùng nhau.

Nếu `G = 10 ngày`, lên lịch mỗi 5 ngày nhưng mỗi chu kỳ đôi khi mất 3 ngày, cộng một ngày xử lý lỗi và một ngày dự phòng thì:

```text
5 + 3 + 1 + 1 = 10 ngày
```

**Không đạt điều kiện bảo thủ `< G`.** Lịch phải được sửa, chẳng hạn giảm khoảng khởi chạy xuống 4 ngày, rút thời gian chạy an toàn bằng tối ưu hiệu năng hoặc tăng grace khi có căn cứ và không tạo rủi ro khác. Không nên sửa bằng cách mở tất cả repair cùng lúc nếu cluster đang sát ngưỡng CPU/đĩa.

## 5. Tải read/write và giới hạn concurrency

Repair tốn tài nguyên giống và khác truy vấn ứng dụng:

| Tài nguyên | Repair sử dụng để làm gì? | Điều gì xảy ra nếu cạnh tranh quá mạnh? |
| --- | --- | --- |
| CPU | Xây/so sánh cấu trúc kiểm tra, nén/giải nén, xử lý SSTable và stream | p95/p99 đọc/ghi tăng, thread bị xếp hàng |
| Disk I/O | Đọc SSTable, validation, anti-compaction/ghi SSTable và dữ liệu stream | Read latency, pending compactions và thời gian flush tăng |
| Network | Trao đổi dữ liệu kiểm tra và streaming giữa replica | Băng thông ứng dụng bị tranh chấp, timeout |
| Disk space | SSTable được ghi hoặc phân tách lại trong quá trình repair/compaction | Disk headroom giảm; thiếu chỗ có thể khiến job thất bại |
| Memory/GC | Buffer, metadata, cây so sánh và kết quả streaming | GC pause, OOM hoặc chậm dịch vụ nếu cấu hình không phù hợp |

### Cửa sổ ít tải không phải “giờ đĩa rảnh”

Một bảng có ghi liên tục, compaction backlog, backup và repair dùng chung I/O. Chọn cửa sổ có **dung lượng dự phòng thực tế**: CPU, disk IOPS/throughput, network, heap và tail latency vẫn trong ngân sách.

Ví dụ:

- API cần p99 đọc dưới 120 ms.
- Khi không repair, p99 khoảng 75 ms.
- Khi chạy hai repair phối hợp, p99 lên 95 ms, pending compactions ổn định: có thể chấp nhận.
- Khi chạy bốn repair, p99 lên 220 ms, queue I/O tăng liên tục: không đạt SLO, dù job repair chạy nhanh hơn.

Các con số minh họa cách đánh giá; mỗi cluster cần SLO và ngưỡng kiểm soát riêng.

### Nút thắt thường ít rõ ràng

- **Replica được mời tham gia** repair có thể xử lý nhiều session từ các coordinator khác nhau. Không chỉ nhìn CPU của node phát lệnh.
- **SSTable chồng lấp, tombstone và compaction backlog** ảnh hưởng lượng dữ liệu phải quét và khối lượng anti-compaction.
- **Đường mạng giữa datacenter** có thể có chi phí/băng thông khác nội bộ DC.
- **Partition quá lớn hoặc hot partition** có thể làm các thao tác validation kéo dài bất cân xứng.
- **Ghi liên tục** tạo thêm dữ liệu mới; một repair hoàn tất không có nghĩa tất cả mutation xảy ra sau snapshot/điểm bắt đầu repair đều được đối soát.

Nên giới hạn số công việc đồng thời, tốc độ streaming và throughput compaction theo khả năng cấu hình của phiên bản. Không sao chép giá trị throttle từ cluster khác mà chưa đo.

## 6. Chọn incremental hay full repair

Cassandra có các phương thức repair khác nhau; cơ chế và giá trị mặc định thay đổi theo phiên bản. Hai khái niệm cần biết:

| Kiểu | Ý tưởng | Đổi lại |
| --- | --- | --- |
| **Incremental repair** | Nhắm vào dữ liệu chưa được đánh dấu repaired ở cơ chế phiên bản tương ứng, có thể dùng anti-compaction để quản lý trạng thái | Giảm công việc lặp lại trong một số workload nhưng cần quản lý trạng thái và lỗi repair kỹ |
| **Full repair** | Đối soát đầy đủ dữ liệu trong phạm vi đã chọn, không chỉ tập chưa repaired | Thường tốn thêm tài nguyên và thời gian, hữu ích khi cần kiểm tra/khôi phục độ bao phủ rộng |

Không được giả định rằng **một lượt incremental repair thành công trên một node = toàn bộ keyspace trên tất cả replica đã đồng nhất**. Phải xác nhận phạm vi token, các node tham gia, DC, trạng thái repaired/unrepaired và lần chạy đầy đủ trước đó.

Trong một số phiên bản Cassandra, `nodetool repair` mặc định là incremental, còn `-full` chọn full repair. Tùy phiên bản và công cụ điều phối, cách đặt cờ/tương tác giữa full và incremental có thể khác; cần kiểm tra tài liệu tương ứng và chính sách đang vận hành.

### Lịch có thể kết hợp các kiểu repair không?

Có, nếu người vận hành hiểu quy trình của phiên bản Cassandra, khả năng recovery và cách theo dõi. Ví dụ một hệ thống có thể chọn incremental repair thường xuyên theo từng primary range, đồng thời lên kế hoạch full repair định kỳ hoặc khi cần kiểm tra một trạng thái nghi ngờ. Nhưng **không có tỷ lệ cố định** như “7 lần incremental thì bắt buộc 1 full” dùng chung cho mọi cluster.

Tiêu chí đánh giá vẫn là **đã đối soát đủ các replica và dải token trong thời gian an toàn hay chưa**, với chi phí tài nguyên và xác suất hoàn tất chấp nhận được.

## 7. Chia phạm vi repair theo node, token range, bảng và datacenter

Một lịch tốt phải đảm bảo coverage và tránh phát động các session sửa cùng phạm vi cùng lúc.

### Primary range

Tùy phiên bản, tùy chọn `-pr`/`--partitioner-range` yêu cầu repair những **primary ranges** gắn với node đang chạy lệnh. Khi tổ chức lượt chạy phù hợp trên các node cần thiết, cách này giúp hạn chế xử lý lặp các dải token.

Ví dụ trên cluster lab:

```bash
nodetool repair -pr app_repair_lab
```

Không được chạy một lần trên một node rồi tuyên bố toàn cluster đã được repair. Phải có **kế hoạch bao phủ các primary ranges** trên các node/DC theo chiến lược replication và phiên bản đang dùng.

### Phạm vi bảng

Khi keyspace có nhiều bảng với grace khác nhau, chia lịch theo lớp dữ liệu có thể hợp lý hơn việc chạy cả keyspace với một tần suất:

| Loại dữ liệu | Ví dụ đặc tính | Chiến lược lịch |
| --- | --- | --- |
| Bảng có nhiều DELETE, `gc_grace_seconds` thấp | Tombstone có thể đủ tuổi GC sớm | Repair thành công thường xuyên hơn, tăng ưu tiên theo rủi ro zombie |
| Bảng sự kiện append-only có TTL đều | Dữ liệu thường ít cập nhật | Vẫn đảm bảo coverage theo grace và đặc tính replica; tối ưu theo cửa sổ compaction/streaming |
| Bảng có dung lượng lớn nhưng thay đổi ít | Scan nhiều, ít khác biệt | Chia dải và cửa sổ; không đồng nhất “ít stream” với “không tốn validation” |
| Bảng nóng, write throughput lớn | Dữ liệu mới phát sinh liên tục | Chọn concurrency/throttle theo SLO và theo dõi tiến độ thường xuyên |

### Datacenter

Ở cụm nhiều datacenter, repair theo DC cần phù hợp với replication policy và mục tiêu nhất quán giữa DC. **Repair cục bộ mỗi DC** có thể cần cho replica nội bộ, nhưng chưa chắc xử lý toàn bộ sai lệch chéo DC tùy quy trình và phạm vi sửa.

Không tự phát động cùng một schedule trên mọi node của mọi DC vào cùng thời điểm. Cần xét băng thông liên DC, mức tải của replica và phạm vi token; nếu dùng công cụ orchestrator, một nơi phải sở hữu lịch và chống chạy trùng.

## 8. Mẫu CQL và lệnh quan sát trước khi lập lịch

Các ví dụ dành cho cluster **thử nghiệm**. Chúng không phải hướng dẫn thay đổi repair policy trên production khi chưa xác nhận phiên bản, topology và tác động.

### Bước A — Xác định dữ liệu có tombstone risk

Giả sử có keyspace `app_repair_lab` và bảng giao dịch trạng thái:

```cql
CREATE TABLE IF NOT EXISTS app_repair_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    state text,
    updated_at timestamp
) WITH gc_grace_seconds = 864000;
```

`864000` giây là **10 ngày** dùng làm ví dụ. Nếu nghiệp vụ có xóa thường xuyên, lịch repair phải đảm bảo các replica có cơ hội nhận tombstone trong khoảng thời gian này, đồng thời lưu ý quy trình repair/GC của phiên bản thực tế.

Một vài mutation để thảo luận:

```cql
INSERT INTO app_repair_lab.orders_by_id (order_id, state, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'PENDING',
    '2026-11-21T03:00:00Z'
);

UPDATE app_repair_lab.orders_by_id
SET state = 'DONE'
WHERE order_id = 11111111-1111-4111-8111-111111111111;

DELETE FROM app_repair_lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Sau `DELETE`, truy vấn không trả hàng ở trạng thái logic tại các replica đã nhận tombstone, nhưng dấu xóa có thể còn phải tồn tại để hòa giải replica khác.

### Bước B — Quan sát mức tải và tình trạng node

Trên node được phép truy cập:

```bash
nodetool status
nodetool tablestats app_repair_lab.orders_by_id
nodetool compactionstats
nodetool tpstats
nodetool netstats
```

Mỗi lệnh trả khía cạnh khác nhau: node đang hoạt động hay offline, kích thước dữ liệu/bộ nhớ và số SSTable theo bảng, công việc compaction, hàng đợi thread và trạng thái streaming. Tên/số liệu cụ thể có thể khác theo phiên bản Cassandra.

Bổ sung telemetry từ monitoring: p95/p99 read/write, I/O, network saturation, disk headroom, heap/GC, hinted handoff, số node trạng thái bất thường và **kết quả từng repair session/range**. Không thể đánh giá an toàn repair chỉ từ lệnh `nodetool status` thấy node đều `UN`.

### Bước C — Repair thử có kiểm soát

Ví dụ thao tác một phạm vi primary range cho keyspace lab:

```bash
nodetool repair -pr app_repair_lab
```

Ví dụ full repair cho keyspace lab khi cần đánh giá theo phiên bản:

```bash
nodetool repair -full app_repair_lab
```

**Không chạy hai lệnh này đồng thời**, không khởi động full repair trên mọi node cùng lúc và không thử trên production chỉ để quan sát nhanh. Cần có kế hoạch phạm vi, cửa sổ tải, tài nguyên, theo dõi tiến độ, retry các phần lỗi và người chịu trách nhiệm kết thúc lượt chạy.

### Bước D — Đọc kết quả theo phạm vi thành công

Sau mỗi lượt, lưu:

- Thời điểm bắt đầu/kết thúc, node điều phối, danh sách keyspace/table và range.
- Kiểu repair, cờ chạy, phiên bản Cassandra, RF và DC tham gia.
- Thành công/thất bại ở cấp job **và cấp range/session**.
- Thời gian, lượng stream, validation, CPU/I/O/network và ảnh hưởng p95/p99.
- Ranges còn thiếu và lịch retry tương ứng.

Job không có lỗi trong terminal vẫn cần xác minh các range dự kiến đã được xử lý đúng lịch. Ngược lại, một phần job thất bại không có nghĩa mọi range trong job đều chưa từng repair; cần lưu bằng chứng tiến độ để chạy lại có kiểm soát.

## 9. Thiết kế lịch theo ngày và cửa sổ tải

Giả sử cluster có 6 node trong một DC, keyspace RF=3, grace nhỏ nhất 10 ngày, mục tiêu hoàn tất coverage mỗi 5 ngày. Qua kiểm thử, repair đủ phạm vi ở hai node đồng thời không vượt ngưỡng p99 và disk I/O.

Một lịch minh họa theo đợt:

| Đợt | Khung công việc | Điều kiện chuyển sang đợt tiếp theo |
| --- | --- | --- |
| 1 | Primary ranges do N1/N2 điều phối | Cả hai phạm vi hoàn tất, không tăng backlog vượt ngưỡng |
| 2 | Primary ranges do N3/N4 điều phối | Xác nhận không bỏ sót ranges và throughput còn ổn |
| 3 | Primary ranges do N5/N6 điều phối | Hoàn tất coverage, lưu mốc thành công từng range |
| Dự phòng | Retry các session/range lỗi | Không vượt ngân sách thời gian an toàn trước `gc_grace_seconds` |

Ví dụ tổ chức để người vận hành hiểu logic. Trong thực tế, repair N1 và N2 có thể chạm cùng replica; cần orchestrator hiểu token ownership và giới hạn đồng thời theo **replica chịu tải**, không chỉ theo số coordinator.

### Khi nào giảm song song hoặc tạm hoãn?

Tạm giảm tốc khi:

- API p99, timeout hoặc error rate vượt SLO đã định.
- Pending compactions, disk queue hoặc GC pause liên tục tăng.
- Streaming làm network saturation trên một node/DC.
- Disk headroom giảm dưới ngưỡng an toàn.
- Node bị down hoặc topology thay đổi khiến session hiện tại không còn hợp lệ.

Tuy nhiên, **hoãn không được biến thành bỏ lịch vô hạn**. Mỗi lần hoãn phải cập nhật ngày coverage gần nhất và ngân sách grace còn lại; nếu không đủ thời gian, kích hoạt quy trình khắc phục/sắp xếp lại workload và nâng cấp năng lực thay vì chỉ tắt repair.

## 10. Monitoring: những số liệu bắt buộc để xác nhận lịch đúng

| Nhóm | Chỉ số nên có | Câu hỏi vận hành |
| --- | --- | --- |
| **Coverage** | Lần repair thành công cuối trên mỗi table/range/DC | Có range nào đã sát hoặc vượt grace? |
| **Runtime** | Median/p95 thời gian mỗi range, tổng thời gian chu kỳ | Lịch có hoàn tất trong budget khi dữ liệu tăng? |
| **Sự cố** | Failed/cancelled sessions, retry backlog, node offline | Có việc bỏ sót lặp lại theo tuần? |
| **Network** | Bytes streamed, stream throughput, errors | Replica đã lệch nhiều? Băng thông có nghẽn? |
| **Storage** | Disk used, free space, SSTable count, compaction backlog | Validation/anti-compaction có cạnh tranh quá mức? |
| **API** | p95/p99 read/write, timeout rate, throughput | Repair có làm ảnh hưởng người dùng? |
| **Tombstone/TTL** | Tombstones scanned, nhiều bảng grace thấp, tần suất delete | Có bảng nào cần lịch gấp hơn vì purge risk? |
| **Topology** | RF/DC, token ownership, node/bootstrap/decommission events | Lịch cũ có còn bao phủ đúng replicas? |

### Ba cảnh báo thiết yếu

1. **Grace budget:** có range/table còn ít thời gian trước khi vượt cửa sổ an toàn, tính từ **thành công gần nhất**, không chỉ từ đầu job.
2. **Repair duration drift:** thời gian chạy tăng qua các chu kỳ, dự báo kỳ sau không hoàn tất trước deadline.
3. **Resource degradation:** repair đang tăng latency hoặc áp lực disk/network quá mức, khiến cả mục tiêu an toàn và sẵn sàng đều bị đe dọa.

Một dashboard “repair chạy 1 lần mỗi ngày” vẫn chưa đủ. Nó cần hiển thị **đã repair được phần nào, còn phần nào, thất bại ở đâu và còn bao nhiêu thời gian an toàn**.

## 11. Khi dung lượng tăng nhanh hơn tốc độ repair

Ví dụ:

```text
Tháng 1: 0,8 TiB dữ liệu trên mỗi node, repair cycle 24 giờ.
Tháng 3: 1,4 TiB/node, repair cycle 44 giờ.
Tháng 6: 2,5 TiB/node, repair cycle 86 giờ.
```

Nếu vẫn giữ một cửa sổ ít tải 48 giờ và grace không đổi, lịch sẽ dần **không thể hoàn tất**.

Các hướng xử lý cần cân nhắc theo nguyên nhân:

- **Tăng năng lực:** thêm node, điều chỉnh lưu trữ hoặc tài nguyên CPU/network; sau topology change cần cập nhật ownership và đo lại.
- **Giảm dữ liệu mỗi phạm vi repair:** tách keyspace/table phù hợp với access pattern, thiết kế TTL và retention có kiểm soát; không dùng nhiều partition nhỏ một cách máy móc.
- **Tối ưu lịch:** chia ranges, điều phối concurrency, chọn cửa sổ ít tải hơn; tối ưu không được khiến quá nhiều session đánh vào cùng replica.
- **Giảm chi phí dữ liệu chết:** điều chỉnh compaction/TTL khi phù hợp và an toàn; không ép GC tombstone để làm repair nhanh.
- **Tách lớp dữ liệu:** bảng critical grace thấp được ưu tiên lịch riêng; bảng ít thay đổi vẫn phải có quy trình bao phủ.
- **Xem lại grace:** nếu có căn cứ vận hành và phiên bản hỗ trợ, tăng `gc_grace_seconds` cho bảng cần thêm thời gian sửa có thể mở rộng cửa sổ an toàn, nhưng làm tombstone tồn tại lâu hơn và tăng chi phí đọc/lưu trữ. Không tự động giảm grace để “tiết kiệm disk”.

**RF cao hơn** tăng khả năng phục vụ khi mất node nhưng cũng tăng số bản sao cần quản lý; không coi tăng RF là cách tự động giải quyết scheduling và gc grace.

## 12. Phân biệt một số sự cố với lỗi lập lịch

### Tình huống A — Repair hoàn tất muộn hơn grace

**Dấu hiệu:** hàng loạt phạm vi chưa được sửa trong khoảng dài hơn grace; có replica từng mất kết nối.

**Rủi ro:** tombstone có thể đã bị purge trên replica lành trước khi replica cũ nhận dấu xóa. Dữ liệu cũ có cơ hội xuất hiện lại.

**Hành động:** điều tra phạm vi và dữ liệu bị ảnh hưởng; xem lịch tombstone/compaction, backup và repair. Khi node ở trạng thái quá cũ, đánh giá quy trình rebuild/replace từ nguồn đáng tin cậy thay vì chỉ khởi động repair trễ và coi như đã an toàn.

### Tình huống B — Incremental repair chạy thường xuyên nhưng dữ liệu vẫn khác

**Dấu hiệu:** dashboard cho thấy nhiều job thành công, một số range/DC lại không được bao phủ hoặc lưu trạng thái repaired/unrepaired có bất thường.

**Hướng kiểm tra:** xác minh chính xác phạm vi token, node/DC, job type, phiên bản và lịch full/incremental. Chạy kiểm chứng theo quy trình phù hợp; không đồng nhất thành công của một session với sức khỏe cả cluster.

### Tình huống C — Cứ chạy repair là p99 tăng rất cao

**Dấu hiệu:** CPU/disk đang gần bão hòa trước khi repair; lúc chạy, compaction backlog và timeout tăng.

**Hướng xử lý:** giảm concurrency/throttle, dời cửa sổ, tối ưu nguyên nhân I/O và dung lượng; vẫn giữ deadline về coverage. Thao tác tăng song song để “xong nhanh” có thể làm cả repair và dịch vụ chậm hơn.

### Tình huống D — Node offline nhiều ngày

**Dấu hiệu:** node không nhận mutation, hints chỉ phủ được một cửa sổ, repair chưa thể hoàn tất.

**Hướng xử lý:** tính thời gian vắng mặt so với grace nhỏ nhất của dữ liệu node quản lý. Nếu vượt cửa sổ an toàn, dùng runbook thay/rebuild/khôi phục phù hợp; không khởi động lại mù quáng và coi mọi giá trị cũ là đáng tin.

### Tình huống E — Vừa đổi replication factor hoặc thêm DC

**Dấu hiệu:** ownership và số replica thay đổi, lịch primary range cũ không còn khớp.

**Hướng xử lý:** hoàn tất các bước topology/streaming theo quy trình, cập nhật schedule, rồi kiểm tra coverage mới theo DC và token. Repair vẫn cần được lập lịch theo cấu trúc replica hiện tại.

## 13. Liên hệ đến ứng dụng Java và consistency level

Trong ứng dụng Java, một request ghi có thể hoàn tất theo CL trước khi tất cả replica nhận được mutation. Ví dụ dùng Java Driver 4.x:

```java
import java.util.UUID;
import java.time.Instant;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class OrderRepository {
    private final CqlSession session;
    private final PreparedStatement insert;

    public OrderRepository(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO app_repair_lab.orders_by_id " +
            "(order_id, state, updated_at) VALUES (?, ?, ?)"
        );
    }

    public void save(UUID orderId, String state, Instant updatedAt) {
        BoundStatement statement = insert.bind(orderId, state, updatedAt)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        session.execute(statement);
    }
}
```

`LOCAL_QUORUM` là mức nhất quán **cho request này**, không phải lời hứa mọi replica đã đồng bộ vĩnh viễn. Lịch repair là trách nhiệm vận hành cluster, thường không phải công việc chạy trong mỗi lần gọi repository.

Ứng dụng vẫn cần:

- Thiết kế partition key phù hợp truy vấn, tránh partition quá lớn và hotspot.
- Dùng retry và idempotency có kiểm soát khi mất kết nối; timeout không chứng minh không replica nào đã nhận ghi.
- Quan sát latency và error rate khi repair chạy để phản hồi nếu vượt SLO.
- Định nghĩa chính sách TTL, DELETE, backup và retention phối hợp với lịch repair.

Việc tăng consistency level trên Java **không thay thế** repair toàn bộ replica. Ngược lại, repair đúng lịch cũng **không tự biến hai thao tác CQL thành giao dịch nguyên tử**; nếu nghiệp vụ cần compare-and-set, cần xem xét LWT theo access pattern thích hợp.

## 14. Mẫu runbook lập lịch có thể áp dụng

Trước mỗi chu kỳ, người vận hành nên có:

| Mục | Cần ghi rõ |
| --- | --- |
| Phạm vi | Keyspace/table, datacenter, token ranges, danh sách node |
| Kiểu repair | Full/incremental và cờ công cụ đúng phiên bản |
| Grace | `gc_grace_seconds` nhỏ nhất, các bảng/TTL/delete workload có rủi ro cao |
| Deadline | Thời điểm phải hoàn tất trước khi vượt cửa sổ an toàn |
| Capacity | Dung lượng SSTable, thời gian repair gần nhất, streaming và disk headroom |
| Concurrency | Số coordinator/range chạy đồng thời, giới hạn trên replica, throttle |
| SLO bảo vệ | Ngưỡng p99, timeout, disk queue, GC, network, compaction |
| Retry | Ai xử lý range lỗi, chạy lại trong bao lâu, quy trình node offline |
| Audit | Lưu kết quả thành công theo range/DC và báo cáo các khoảng trống |

### Quy trình ngắn

1. **Inventory:** xác nhận RF, token ranges, tables, grace, dữ liệu và tình trạng node.
2. **Budget:** tính deadline theo lần repair thành công và ngưỡng grace nhỏ nhất.
3. **Capacity test:** ước tính runtime từ lần chạy gần nhất trong tải đại diện; dành margin cho streaming và failover.
4. **Schedule:** phân đợt theo phạm vi ít trùng, chọn cửa sổ có năng lực, giới hạn tác động lên replica.
5. **Execute:** theo dõi phạm vi đã hoàn tất, không chỉ thời gian lệnh trên terminal.
6. **Recover:** retry phần lỗi và xử lý node offline trước khi hết grace.
7. **Review:** so sánh runtime, tải và coverage sau mỗi chu kỳ; cập nhật lịch khi dữ liệu tăng hoặc topology đổi.

## 15. Những sai lầm phổ biến

**“`nodetool repair` chạy không báo lỗi, vậy cả cluster an toàn.”** Không chắc. Cần xem phạm vi lệnh và những token ranges/DC/table đã hoàn tất.

**“Chạy repair mỗi 10 ngày đủ cho bảng có grace 10 ngày.”** Không có dự phòng cho runtime, outage, retry và sai lệch lịch; thường không an toàn.

**“Dữ liệu ít thay đổi thì không cần repair.”** Replica vẫn có thể bỏ lỡ mutation hiếm gặp, đặc biệt xóa; ít thay đổi không đồng nghĩa đã đồng nhất.

**“Dùng `LOCAL_QUORUM` là mọi replica đều nhận DELETE.”** Sai nếu RF=3: phản hồi từ quorum không bắt buộc replica thứ ba đã đồng bộ.

**“Tăng concurrency luôn giảm thời gian repair.”** Chỉ tới khi chạm I/O, network, CPU, compaction hoặc memory; vượt ngưỡng có thể khiến repair và ứng dụng chậm hơn.

**“Có nhiều node thì chỉ việc chạy `-pr` trên một node.”** Sai. Primary range của một node không đại diện toàn bộ token của cluster.

**“Compaction xóa tombstone vì đã qua grace, nên repair lúc nào cũng được.”** Sai. Nếu replica cũ chưa nhận tombstone, việc thu hồi quá sớm có thể gây zombie data.

**“Sao lưu đủ thì không cần repair.”** Backup và repair giải quyết hai mục tiêu khác nhau: phục hồi từ bản lưu và đối soát replica đang phục vụ.

**“Chỉ đo bytes streamed là biết repair nhanh hay chậm.”** Không chính xác. Validation vẫn có thể phải đọc nhiều SSTable dù lượng khác biệt cần stream gần bằng 0.

## 16. Câu hỏi thực hành

1. Một bảng có grace 7 ngày; chu kỳ khởi chạy mỗi 5 ngày, mỗi lượt tốn 2 ngày, cần 1 ngày retry. Vì sao lịch này không đủ an toàn?
2. Cluster RF=3, ghi `LOCAL_QUORUM` thành công khi một replica offline. Repair còn cần làm gì?
3. Giải thích khác nhau giữa *job repair bắt đầu*, *session hoàn tất* và *tất cả token ranges cần thiết đã được repair thành công*.
4. Hai nhóm repair coordinator khác nhau đều kéo cùng replica vào validation. Vì sao concurrency tính theo số coordinator dễ gây nhầm?
5. SSTable dung lượng lớn nhưng lượng streamed rất nhỏ. Repair vẫn có thể mất lâu vì sao?
6. Bảng A có `gc_grace_seconds=864000`, bảng B có `gc_grace_seconds=259200`. Lịch repair hàng tuần cho cả keyspace có điều gì đáng lo?
7. Khi thấy node offline lâu hơn grace rồi trở lại, tại sao không thể coi một lần `nodetool repair` muộn là đủ xử lý mọi rủi ro?
8. So sánh mục đích `compaction`, `repair` và `read repair`.
9. Trước khi nâng repair concurrency từ 2 lên 4, bạn sẽ đo những metrics nào?
10. Khi thêm datacenter mới hoặc thay RF, những thành phần nào của lịch repair phải xem lại?

## 17. Bảng quyết định ngắn

| Nếu vấn đề chính là… | Việc cần làm trước |
| --- | --- |
| **Grace sắp hết, repair chưa hoàn tất** | Xác định ranges chưa thành công, ưu tiên xử lý an toàn và phục hồi node; tránh bỏ deadline |
| **Dung lượng tăng, thời gian repair dài** | Đo bytes scan/stream, compaction và thời gian mỗi range; tăng năng lực hoặc chia lịch đúng cách |
| **Repair làm API quá chậm** | Giảm concurrency/throttle, đặt cửa sổ có headroom, theo dõi deadline |
| **Node mất kết nối lâu** | Đánh giá tuổi dữ liệu và `gc_grace_seconds` trước khi cho node tham gia lại |
| **Nhiều bảng có grace khác nhau** | Lập lịch theo bảng/nhóm rủi ro; dùng ngưỡng grace nhỏ nhất khi gộp chung |
| **Chạy full/incremental nhưng coverage không rõ** | Ghi log kết quả theo range, đối chiếu topology và chính sách phiên bản |

**Ghi nhớ:** Repair là lịch bảo trì phải **hoàn tất trên đúng replica và phạm vi token**, không đơn thuần là một dòng cron. Hãy đo dung lượng và thời gian chạy thực, giới hạn tải theo SLO, rồi đảm bảo **khoảng cách giữa các lần repair thành công cộng thời gian phục hồi/dự phòng nhỏ hơn cửa sổ `gc_grace_seconds` áp dụng**. Một lịch có thể kiểm chứng và xử lý được thất bại mới giúp Cassandra giữ tính nhất quán replica mà không đẩy cả cluster vào nghẽn tài nguyên.
