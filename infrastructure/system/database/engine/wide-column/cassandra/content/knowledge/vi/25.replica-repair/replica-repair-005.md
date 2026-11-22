# Repair theo từng nút và phạm vi còn lại của toàn cụm trong Apache Cassandra

## 1. Bài toán: repair một node không có nghĩa toàn cluster đã được repair

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**. Mỗi partition được xác định bằng **partition key**, được ánh xạ tới **token range**, rồi được lưu trên một nhóm replica theo replication strategy của keyspace. Cách thiết kế bảng theo truy vấn giúp truy cập dữ liệu nhanh, nhưng cũng có nghĩa **trách nhiệm lưu trữ nằm rải trên nhiều node**.

Khi mạng chập chờn, node ngừng hoạt động, ghi chỉ đạt một consistency level thấp hơn số replica, hoặc hinted handoff không chuyển hết mutation, các replica có thể có dữ liệu khác nhau. **Anti-entropy repair** là cơ chế Cassandra dùng để đối chiếu và đồng bộ dữ liệu giữa các replica.

Vấn đề trọng tâm của chương **Repair** là phạm vi: khi một quản trị viên kết nối tới node A và chạy `nodetool repair`, Cassandra không tự bảo đảm mọi token range của mọi keyspace trên toàn cluster đã được sửa. Một lần repair do A khởi tạo thường xử lý **những phạm vi token mà A tham gia lưu trữ hoặc những primary range được chỉ định**, tùy tham số. Các range chỉ thuộc những replica khác vẫn có thể chưa được kiểm tra.

Vì vậy cần phân biệt ba câu hỏi:

1. **Node khởi tạo:** lệnh chạy từ A, B hay C?
2. **Phạm vi repair:** keyspace/table, token ranges, datacenter và nhóm replica nào tham gia?
3. **Độ bao phủ của cả chiến dịch:** mọi range cần thiết đã có repair thành công, hay còn khoảng chưa chạy, thất bại hoặc bị bỏ sót?

> Một dòng log “Repair completed” trên một node xác nhận **một công việc cụ thể** đã hoàn tất. Nó không mặc nhiên chứng minh **mọi replica của mọi partition trên toàn cluster đã hội tụ**.

## 2. Repair hoạt động ở đơn vị nào?

### 2.1. Token range và nhóm replica

Cassandra chia không gian token thành các khoảng. Với mỗi khoảng token của một keyspace, replication strategy xác định tập node chịu trách nhiệm lưu partition trong khoảng đó. Khi RF=3, một partition có ba replica trong topology tương ứng; với nhiều datacenter, mỗi DC có thể có RF riêng.

Một node có thể giữ bản sao của **nhiều range**, đồng thời **không giữ** một số range khác. Khi dùng virtual nodes (vnodes), quyền sở hữu còn được chia nhỏ thành nhiều khoảng; ví dụ dưới đây chỉ minh họa logic, không mô tả token ring thực của một cluster.

### 2.2. Anti-entropy repair làm gì?

Một repair session thông thường có thể được hiểu theo các bước logic:

1. Xác định keyspace/table, token ranges, các replica tham gia và loại repair được yêu cầu.
2. Các replica chuẩn bị dữ liệu cần so sánh, thường sử dụng cấu trúc **Merkle tree** hoặc cơ chế validation phù hợp với phiên bản.
3. So sánh nội dung các phạm vi để tìm khác biệt giữa replica.
4. **Streaming** các đoạn dữ liệu cần thiết giữa replica để hòa giải.
5. Cập nhật tiến độ/trạng thái phiên repair; với incremental repair, có thêm cơ chế đánh dấu và tổ chức SSTable liên quan đến trạng thái repaired.

~~~mermaid
flowchart TD
    A["Operator chọn keyspace, table, token ranges"] --> B["Một node điều phối repair"]
    B --> C["Xác định replica tham gia"]
    C --> D["Validation / Merkle comparison"]
    D --> E{"Có khác biệt?"}
    E -->|Có| F["Stream dữ liệu cần đồng bộ"]
    E -->|Không| G["Không cần stream dữ liệu khác biệt"]
    F --> H["Ghi nhận kết quả repair phạm vi đó"]
    G --> H
    H --> I["Cập nhật coverage toàn cluster"]
~~~

Repair **không chỉ tải lại toàn bộ dữ liệu vào node nơi chạy lệnh**. Node khởi tạo có vai trò điều phối; các replica của range có thể trao đổi dữ liệu với nhau. Chi tiết bên trong tùy phiên bản và loại repair, nhưng phạm vi token/replica tham gia vẫn là yếu tố cần ghi lại.

### 2.3. Các lớp “đầy đủ” khác nhau

| Cụm từ | Ý nghĩa đúng | Điều không thể suy ra |
|---|---|---|
| Repair trên node A | A khởi tạo repair cho các range được chọn | Toàn bộ các range trên các node khác đã được kiểm tra |
| Repair một keyspace | Những table/range của keyspace trong phạm vi lệnh | Các keyspace khác đã được repair |
| Repair một table | Một table và các range được chọn | Các table cùng keyspace đã được xử lý |
| **Full repair** | Loại repair bao gồm dữ liệu không chỉ giới hạn phần chưa repaired theo cơ chế incremental | **Không** đồng nghĩa tự repair toàn cluster |
| **Primary-range repair** | Chỉ xử lý những range mà node được xem là primary owner theo cách phân bổ và tùy chọn lệnh | Những range node chỉ giữ với vai trò replica phụ đã được node đó khởi tạo repair |
| Cluster-wide repair coverage | Toàn bộ token ranges, keyspace/table và phạm vi DC mục tiêu đã có kết quả thành công | Chắc chắn tất cả request tương lai sẽ nhất quán hoặc không còn lỗi vận hành |

**Phân biệt quan trọng:** cờ `--full` nói về **loại dữ liệu/chu kỳ repair**, còn phạm vi toàn cụm phụ thuộc **các range đã thực sự được chạy thành công**.

## 3. Ví dụ: repair A xong, cụm vẫn còn range chưa xử lý

Giả sử một datacenter có năm node A, B, C, D, E, với RF=3. Để đơn giản, minh họa năm token range R1–R5; mỗi range có một primary owner và ba replica:

| Range | Primary owner (minh họa) | Ba replica lưu dữ liệu |
|---|---|---|
| R1 | A | A, B, C |
| R2 | B | B, C, D |
| R3 | C | C, D, E |
| R4 | D | D, E, A |
| R5 | E | E, A, B |

Trên thực tế, token ring còn nhiều khoảng hơn và phân bổ replica do partitioner, replication strategy, vnodes, rack/DC quyết định. Bảng chỉ phục vụ suy luận coverage.

### 3.1. Chạy một lần trên node A

Nếu repair A chọn **tất cả range mà A là replica**, phạm vi của A là `{R1, R4, R5}`. Các replica ở R1, R4, R5 có thể được đối chiếu theo đúng phạm vi đã chọn. Nhưng:

- **R2** chỉ nằm trên B, C, D.
- **R3** chỉ nằm trên C, D, E.

Do đó một lần repair từ A không bao phủ R2 hoặc R3.

Nếu từ A chạy **primary-range repair** với `-pr`, phạm vi còn hẹp hơn trong ví dụ: A chỉ khởi tạo cho **R1**. Đổi lại, có thể tổ chức một chiến dịch lần lượt chạy primary-range repair trên mỗi primary owner để tránh một số công việc trùng lặp.

~~~text
Tất cả range mục tiêu:      R1  R2  R3  R4  R5
Repair tất cả replica ở A:   X   -   -   X   X
Chưa được A bao phủ:         -   X   X   -   -

Repair -pr trên A:          X   -   -   -   -
Sau -pr trên A:              R2, R3, R4, R5 còn chờ
~~~

Tuy nhiên, **range R1 đã được repair từ A không có nghĩa chỉ dữ liệu tại A được xử lý**: repair có thể so sánh và chuyển dữ liệu giữa cả A, B, C, tùy thành phần tham gia và kết quả validation.

### 3.2. Kế hoạch primary-range trên toàn cluster

Một chu kỳ minh họa:

| Lượt | Node chạy `nodetool repair -pr` | Primary range mục tiêu | Coverage cộng dồn |
|---|---|---|---|
| 1 | A | R1 | R1 |
| 2 | B | R2 | R1, R2 |
| 3 | C | R3 | R1, R2, R3 |
| 4 | D | R4 | R1–R4 |
| 5 | E | R5 | R1–R5 |

Nếu mọi phiên hoàn tất thành công với topology ổn định và phạm vi DC/replica đúng yêu cầu, chiến dịch có thể bao phủ toàn bộ R1–R5 theo primary owner. Không được đánh đồng ví dụ “một range trên một node” với cluster thật: **vnodes có nhiều range mỗi node**, và chiến dịch cần theo dõi các range thực tế từ token metadata.

### 3.3. Cách nghĩ bằng tập hợp coverage

Gọi `U` là tập token ranges mục tiêu của một keyspace/table/DC. Gọi `S(A)` là các range đã repair **thành công** trong những job do A khởi tạo.

~~~text
U = {R1, R2, R3, R4, R5}

Sau repair A:
S(A) = {R1, R4, R5}

Remaining = U - S(A) = {R2, R3}
~~~

Nếu repair từ B bổ sung R2 nhưng cũng chạy lại R1, thì coverage mới chỉ tăng thêm R2; **lặp công việc không có nghĩa tăng coverage tương ứng**. Khi tính phạm vi còn lại phải lấy **hợp các range đã hoàn tất**, loại bỏ công việc thất bại/hủy và so đúng keyspace, table, DC.

## 4. Những tùy chọn `nodetool repair` cần phân biệt

Cú pháp và mặc định thay đổi theo **phiên bản Cassandra**. Các lệnh dưới đây là ví dụ về ý nghĩa vận hành; trước khi chạy trên production, cần xem `nodetool help repair` của phiên bản đang dùng.

~~~bash
# Phạm vi repair do phiên bản quyết định nếu không truyền thêm cờ.
# Không giả định mặc định giống nhau giữa mọi phiên bản.
nodetool repair my_keyspace

# Chỉ các primary ranges của node hiện tại.
nodetool repair -pr my_keyspace

# Chỉ một table trong keyspace; tên table truyền sau keyspace.
nodetool repair -pr my_keyspace orders_by_id

# Full repair (khác với incremental); vẫn chỉ xử lý phạm vi được chọn.
nodetool repair --full my_keyspace

# Kết hợp loại full với phạm vi primary, nếu bản Cassandra hỗ trợ.
nodetool repair --full -pr my_keyspace
~~~

| Tùy chọn | Chọn cái gì? | Lưu ý |
|---|---|---|
| Không có `-pr` | Thường phạm vi replica ranges mà node chịu trách nhiệm, tùy loại repair | Có thể trùng range khi chạy lặp trên các node |
| `-pr` / `--primary-range` | Primary token ranges của node | Dùng để xây lịch bao phủ với nhiều node; không đồng nghĩa một node đã phủ cả cluster |
| `--full` | Full repair, đối lập incremental repair | Chữ “full” nói về phương thức, không nói số node |
| Repair không `--full` | Có thể dùng incremental làm mặc định ở nhiều phiên bản hiện đại | Kiểm tra phiên bản và tác động repaired/unrepaired SSTables |
| Phạm vi table | Hạn chế repair tới table được chọn | Các table bị bỏ qua vẫn cần lịch riêng |
| Phạm vi DC/host, ví dụ `-local` hoặc `-dc` | Hạn chế replica tham gia theo topology | Chỉ đủ để đáp ứng mục tiêu tương ứng, không mặc nhiên sửa sai lệch xuyên DC |

### Incremental và full repair

**Incremental repair** thường chỉ xét dữ liệu thuộc phần chưa được đánh dấu repaired theo cơ chế phiên bản và sau khi thành công cập nhật trạng thái liên quan. Nó có thể giảm lượng dữ liệu phải kiểm tra lặp lại ở những chu kỳ tiếp theo, nhưng cũng có các cơ chế xử lý SSTable như anti-compaction và điều kiện phức tạp hơn khi repair bị gián đoạn.

**Full repair** xét phạm vi rộng hơn của dữ liệu cho các range đã chọn, và có thể tốn nhiều I/O/network hơn. Full repair cũng chỉ sửa **phạm vi thực sự được chọn**.

Không tự đổi từ incremental sang full hoặc phối hợp hai loại thiếu kế hoạch. Sau lỗi một phiên incremental, cần xem **trạng thái repair thực tế**, log và hướng dẫn theo đúng Cassandra version; không suy luận mọi range đã sạch chỉ vì tiến trình kết thúc.

### Primary-range không phải lúc nào cũng là kế hoạch duy nhất

Chạy repair **không có `-pr` lần lượt ở tất cả node** có thể tạo công việc trùng trên những range cùng nhóm replica. Trong khi đó, chiến dịch **`-pr` trên các owner** giúp phân chia phạm vi khởi tạo có hệ thống, nhưng phải xét DC, topology, keyspace/table và đặc điểm phiên bản.

Nếu tổ chức dùng phần mềm repair orchestrator, quy trình của công cụ đó có thể chia theo token ranges và điều phối khác hẳn mô hình “mỗi node chạy một lệnh”. Điều cần bảo toàn vẫn là **coverage thành công toàn bộ range mục tiêu**.

## 5. Phạm vi datacenter và replication trong cluster nhiều DC

Giả sử `NetworkTopologyStrategy` có hai datacenter:

~~~cql
CREATE KEYSPACE app_data
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

Mỗi token range có replica ở cả `dc1` và `dc2`. Một lần repair chỉ giữa các replica trong `dc1` có thể giúp các replica dc1 đồng bộ với nhau, nhưng **không bảo đảm chúng được đối chiếu với dc2**.

### Local repair và repair bao phủ toàn cluster là hai phạm vi khác nhau

- **Repair giới hạn một DC:** phù hợp khi chủ đích chỉ đồng bộ replica trong datacenter đó; giảm trao đổi xuyên DC.
- **Repair có replica từ nhiều DC tham gia:** cần xem xét khi yêu cầu là đồng bộ dữ liệu xuyên DC; tốn băng thông liên DC và chịu tác động network latency.
- **Chạy `-pr` trên mọi node của một DC:** cần hiểu cách phân bổ primary range tại DC đó; không mặc định điều này đủ cho những replica của DC khác.

Ví dụ cờ `-local` hoặc `-dc` có ý nghĩa và sự kết hợp thay đổi theo phiên bản. Đối với cluster đa DC, lập sơ đồ **range × DC × replica tham gia** rồi xác định chính xác chiến dịch đang muốn xử lý lệch **nội DC** hay **xuyên DC**. Không coi “đã chạy repair đủ số node” là bằng chứng nếu các DC quan trọng không tham gia validation/streaming.

| Câu hỏi cần xác định | Nếu bỏ qua |
|---|---|
| Keyspace dùng replication strategy nào, RF mỗi DC bao nhiêu? | Có thể thiếu replica cần so sánh |
| Network giữa các DC có cho phép repair xuyên DC không? | Job có thể nghẽn hoặc thất bại |
| Có DC bị tách mạng dài hơn hint window/grace không? | Dữ liệu và tombstone có thể thiếu |
| Chính sách bảo vệ replication có yêu cầu hội tụ xuyên DC không? | Local repair xong nhưng cụm vẫn sai lệch xuyên DC |

## 6. Lập bảng theo dõi phạm vi còn lại

Chạy một lệnh rồi nhìn exit code là chưa đủ để biết toàn cluster được repair. Một lịch repair rõ ràng cần danh sách range mục tiêu và kết quả thực tế.

### 6.1. Gợi ý cấu trúc coverage ledger

| Trường | Ý nghĩa |
|---|---|
| `cluster_id`, `topology_epoch` | Cluster/topology tại thời điểm lập kế hoạch |
| `keyspace`, `table` | Đối tượng dữ liệu được repair |
| `token_start`, `token_end` | Khoảng token; chú ý vòng token ring và boundary |
| `dc_scope`, `replica_set` | DC và replica thực sự tham gia |
| `repair_kind` | Full hay incremental, các tùy chọn liên quan |
| `coordinator`, `job_id` | Node khởi tạo và mã phiên/job |
| `started_at`, `finished_at` | Dấu thời gian thực tế |
| `result` | Thành công, thất bại, hủy, chưa bắt đầu |
| `verified_source` | Nguồn log/metrics/tool dùng để xác nhận |

Không cần ứng dụng riêng để lưu ledger: trong tổ chức có thể dùng công cụ lập lịch repair và lưu kết quả có sẵn. Yêu cầu quan trọng là **phân biệt “đã lên lịch”, “đang chạy” và “thành công”**. Chỉ những range có bằng chứng hoàn tất mới được tính vào coverage.

### 6.2. Tính remaining scope

Một tập kiểm tra cho một chiến dịch có thể biểu diễn như sau:

~~~text
Mục tiêu:           tất cả ranges của app_data.orders_by_id trong phạm vi yêu cầu

Đã hoàn tất:
  R1: SUCCESS
  R2: SUCCESS
  R3: FAILED
  R4: NOT_STARTED
  R5: SUCCESS

Remaining / cần xử lý lại:
  R3 (thất bại)
  R4 (chưa chạy)
~~~

Khi gặp lỗi trên một range, không được đánh dấu cả node là “repaired” nếu công việc chỉ chạy một phần. Sau khi xử lý nguyên nhân, lặp lại đúng phạm vi bị ảnh hưởng theo cơ chế hỗ trợ của version/công cụ.

### 6.3. Topology thay đổi làm kế hoạch cũ mất hiệu lực

Bootstrap, decommission, replace, move token hoặc thay đổi RF làm **replica ownership** thay đổi. Nếu kế hoạch coverage được tạo từ trước thay đổi đó, danh sách primary owner hoặc nhóm replica có thể không còn đúng.

Trước mỗi chiến dịch lớn, chụp thông tin topology. Nếu topology đổi giữa chừng, phải tái xác định ownership, phân loại range cần repair lại và tránh ghi nhận kết quả dưới topology cũ như bằng chứng cho phạm vi mới.

## 7. Công cụ thu thập bằng chứng trước và trong repair

Với quyền phù hợp, trước khi bắt đầu hãy kiểm tra health cluster và topology. Ví dụ các lệnh trên node Cassandra:

~~~bash
# Trạng thái node và datacenter.
nodetool status

# Mô tả token range và endpoint theo keyspace, tùy phiên bản hỗ trợ.
nodetool describering app_data

# Thông tin các hoạt động streaming (không thay cho repair log).
nodetool netstats

# Tác vụ compaction có thể cạnh tranh I/O với repair.
nodetool compactionstats

# Kiểm tra tùy chọn đúng của phiên bản.
nodetool help repair
~~~

Sau khi khởi tạo, xem output/exit code của lệnh, log server và các metric repair/validation/streaming mà phiên bản cung cấp. Khi sử dụng công cụ repair orchestrator, xem task/session IDs và token ranges thành công theo chính công cụ đó.

**Không dùng `nodetool status` để tuyên bố data synchronized.** Một node `UN` (Up/Normal) chỉ là tình trạng node ở mức membership, không chứng minh các range đã được anti-entropy repair.

### Dấu hiệu cần quan tâm

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra tiếp |
|---|---|---|
| Repair trên một node báo SUCCESS nhưng các node khác chưa có lịch | Còn nhiều range ngoài phạm vi | Đối chiếu token map và ledger |
| Repair dừng khi validation/streaming | Network, disk, heap, SSTable, node down | Đọc session/log, xử lý nguyên nhân rồi chạy lại scope lỗi |
| Pending compactions và latency tăng | Repair tranh I/O với traffic/compaction | Giảm concurrency, chia phạm vi, điều tiết lịch |
| Một DC có repair hoàn tất nhưng DC kia vẫn lệch | Scope chỉ nội DC | Xem lại kế hoạch inter-DC và replication |
| Repair xong vẫn thấy dữ liệu cũ “sống lại” | Có thể liên quan tombstone bị purge quá sớm | Điều tra `gc_grace_seconds`, outage và repair history; đánh giá rebuild |
| Repair kế hoạch cũ sau thay node | Token ownership đổi | Tính lại range và replica set |

## 8. Repair và khả năng chịu lỗi: hints, tombstone, gc_grace_seconds

### 8.1. Hinted handoff không thay repair

Hinted handoff có thể lưu mutation cho replica vắng mặt tạm thời và phát lại khi replica quay lại. Nhưng **hint window, khả năng lưu hints và replay** đều có giới hạn. Khi node vắng mặt lâu, không có gì bảo đảm mọi mutation trong khoảng mất kết nối đều được phục hồi bằng hints.

Repair so sánh dữ liệu thực tế giữa replica, nên cần trong kế hoạch chống entropy lâu dài. Cần chọn lịch sao cho mọi phạm vi được đối soát trước khi trở nên rủi ro đối với dấu xóa.

### 8.2. Tombstone và rủi ro zombie data

Một delete trên Cassandra tạo tombstone để che các phiên bản cũ. Nếu replica C bị mất kết nối và bỏ lỡ delete, trong khi các replica khác đã loại tombstone đủ điều kiện khỏi SSTable, khi C trở lại có thể xảy ra **zombie data**: dữ liệu tưởng đã xóa xuất hiện lại.

`gc_grace_seconds` liên quan đến thời gian giữ tombstone nhằm giảm rủi ro đó, nhưng không phải công tắc bảo đảm an toàn trong mọi topology. Việc purge còn phụ thuộc dữ liệu chồng lấn, compaction và điều kiện phiên bản. Lịch repair phải được thiết kế phù hợp thời gian grace và outage thực tế.

**Không coi “repair hoàn tất sau khi tombstone đã mất” là bằng chứng chắc chắn zombie được ngăn.** Với node offline quá lâu hoặc có nghi ngờ mất delete, phải xem xét phương án rebuild/replace từ nguồn dữ liệu khỏe theo runbook.

### 8.3. Repair theo từng node cần hoàn thành chu kỳ

Giả sử `gc_grace_seconds` được đặt cho một cửa sổ an toàn hữu hạn. Nếu chỉ repair A mỗi tuần nhưng B/C/D/E chưa bao giờ nằm trong lịch đầy đủ, các range ngoài A có thể không được đối soát trước khi tombstone được phép purge. **Khoảng giữa hai lần repair thành công của từng range** là yếu tố cần theo dõi, không phải chỉ số “số node đã chạy lệnh” riêng lẻ.

Mục tiêu vận hành nên là **chu kỳ repair có phạm vi và bằng chứng rõ ràng**, phù hợp loại dữ liệu, uptime, retention, TTL và chính sách recovery.

## 9. Runbook: tổ chức repair theo node và xác định phần còn lại

### Bước 1 — Xác định mục tiêu

Lập danh sách keyspace/table cần repair, replication strategy, RF từng DC, topology hiện tại và yêu cầu đồng bộ nội DC/xuyên DC. Loại trừ hoặc phân loại đối tượng theo chính sách có chủ đích; không vô tình bỏ table chỉ vì lệnh không liệt kê.

### Bước 2 — Chia token range thành phạm vi không bỏ sót

Dùng token metadata và công cụ orchestration để lập worklist. Nếu triển khai dựa trên primary-range repair, phân bổ range theo owner và xác minh mọi range đều có owner trong lịch. Nếu chọn repair toàn bộ replica ranges theo từng node, nhận biết phần trùng để kiểm soát tải.

### Bước 3 — Kiểm tra điều kiện an toàn và capacity

Trước khi chạy, xem node up/down, disk free, compaction backlog, read/write latency, network, phiên bản Cassandra và các job streaming khác. Repair có thể cần validation, streaming dữ liệu và compaction/anti-compaction, vì vậy cần dự phòng dung lượng và I/O.

### Bước 4 — Chạy có điều tiết

Không tự chạy song song trên mọi node nếu chưa chứng minh đủ tài nguyên. Chọn concurrency và giờ vận hành theo workload. Chia nhóm range/node để hạn chế số job cùng tranh đĩa và mạng, nhất là ở cluster nhiều datacenter.

### Bước 5 — Ghi nhận từng kết quả

Thu thập output/logs/metrics, cập nhật ledger với `SUCCESS`, `FAILED` hoặc `NOT_STARTED` cho range và table tương ứng. Một job bị hủy không được xem là thành công chỉ vì đã chạy một phần.

### Bước 6 — Xử lý remaining scope

Tính hiệu của tập tất cả phạm vi mục tiêu trừ những phạm vi đã thành công. Chạy lại range lỗi, phạm vi chưa chạy và những phần cần đánh giá lại sau khi topology đổi. Đừng lặp toàn bộ một chu kỳ chỉ vì dễ viết script nếu công cụ cho phép sửa chính xác phần còn lại.

### Bước 7 — Xác nhận và hẹn chu kỳ kế tiếp

Kiểm tra mọi target range/table/DC đạt coverage mục tiêu, các job kết thúc hợp lệ, không có session treo, node ổn định và metrics quay lại trạng thái bình thường. Lưu mốc hoàn tất cuối cùng theo **range**, không chỉ theo node; lập lịch chu kỳ tiếp theo đủ sớm so với chính sách tombstone/repair.

## 10. Ví dụ CQL và Java: dữ liệu đọc được không chứng minh cluster đã repair

### 10.1. Tạo keyspace và bảng phục vụ truy vấn

Giả sử một DC tên `dc1` có RF=3. Khi triển khai thực tế, tên datacenter phải khớp topology:

~~~cql
CREATE KEYSPACE app_data
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE app_data.orders_by_id (
    order_id uuid PRIMARY KEY,
    state text,
    updated_at timestamp
);

INSERT INTO app_data.orders_by_id (order_id, state, updated_at)
VALUES (
    11111111-1111-1111-1111-111111111111,
    'PAID',
    '2026-11-21T08:00:00Z'
);
~~~

Đọc theo partition key:

~~~cql
CONSISTENCY LOCAL_QUORUM;

SELECT state, updated_at
FROM app_data.orders_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

Một query `LOCAL_QUORUM` thành công có thể giúp ứng dụng nhìn thấy trạng thái phù hợp với mức nhất quán đang dùng. Nhưng **nó không kiểm tra tất cả token range**, không chứng minh replica còn lại đã bắt kịp mọi mutation, và không thay anti-entropy repair.

### 10.2. Java Driver 4.x đặt read consistency rõ ràng

Giả sử `CqlSession session` đã kết nối đúng DC và bảng tồn tại:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

PreparedStatement lookup = session.prepare(
    "SELECT state, updated_at FROM app_data.orders_by_id " +
    "WHERE order_id = ?"
);

UUID orderId =
    UUID.fromString("11111111-1111-1111-1111-111111111111");

BoundStatement statement = lookup.bind(orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

Row row = session.execute(statement).one();
if (row != null) {
    String state = row.getString("state");
    // Dùng giá trị cho nghiệp vụ. Đây không phải kết quả repair.
}
~~~

Ứng dụng Java cần thiết kế partition key, write/read CL, retry và xử lý timeout theo yêu cầu nghiệp vụ. **Quản lý repair là công việc vận hành phân tán**, không thể kết luận toàn cluster đã repair từ kết quả một `SELECT` hoặc do Java driver kết nối thành công.

### 10.3. Chạy repair cho bảng này

Ví dụ chạy trên từng node được chọn:

~~~bash
# Phạm vi primary range của node hiện tại cho table mục tiêu.
nodetool repair -pr app_data orders_by_id
~~~

Sau lệnh này trên A, operator vẫn phải đánh dấu những range chưa được A khởi tạo và tiếp tục lịch trên các node còn lại. Nếu chọn full repair:

~~~bash
nodetool repair --full -pr app_data orders_by_id
~~~

Cần kiểm tra **phiên bản Cassandra, tùy chọn cờ và chính sách repair** trước khi áp dụng. Hai lệnh minh họa khác nhau về loại repair; cả hai vẫn bị giới hạn ở primary ranges của node đang chạy và phạm vi table được chỉ định.

## 11. Tình huống sự cố: repair A thành công, dữ liệu B/C/D vẫn lệch

Một cluster 5 node, RF=3, chạy repair từ A sau một outage. Lệnh báo SUCCESS; vài ngày sau ứng dụng đọc một partition mà primary/replica set là B, C, D và thấy dữ liệu khác nhau.

**Điều tra theo từng giả thuyết:**

1. **Range của partition có được A sửa không?** Trong ví dụ R2 chỉ có B, C, D nên không thuộc phạm vi của A; sửa A không liên quan.
2. **Lệnh có giới hạn table/keyspace hoặc primary range không?** Một repair `-pr` trên A không tự bao phủ R2.
3. **Job có thực sự SUCCESS cho tất cả range nó nhận không?** Có session lỗi nhưng chỉ nhìn exit/console không đầy đủ?
4. **Có datacenter khác ngoài phạm vi được sửa không?** Local repair có thể không giải quyết lệch xuyên DC.
5. **Topology có đổi sau repair không?** Ownership/replica set có thể đã khác; cần cập nhật coverage.
6. **Có outage rất dài hoặc tombstone bị purge?** Nếu có rủi ro zombie data, phải đánh giá an toàn repair/rebuild.

**Hướng xử lý:** xác định token range của partition bị ảnh hưởng, replica set hiện tại và phiên repair trước; đánh dấu R2 là chưa được bao phủ hoặc đã thất bại, rồi lập phiên repair phù hợp cho R2 và các range còn lại. Song song, kiểm tra lịch toàn cluster để không chỉ chữa riêng một partition dễ nhìn thấy.

Không sửa trực tiếp một replica bằng lệnh ghi tùy tiện với hy vọng tự đồng bộ toàn bộ: CQL ghi thường chỉ tác động các mutation được yêu cầu và có thể che mất dấu hiệu lỗi gốc.

## 12. Bài tập thực hành có đáp án

**Câu 1.** Có năm range R1–R5. Node A lưu R1, R4, R5. Repair từ A với phạm vi tất cả replica ranges hoàn tất. Phần nào còn chưa được A bao phủ?

**Đáp án:** R2 và R3. Một lần repair thành công của A không đồng nghĩa hoàn thành toàn cluster.

**Câu 2.** A chạy `nodetool repair --full -pr app_data orders_by_id`. Có thể gọi đây là “full cluster repair” không?

**Đáp án:** Không. `--full` nói về loại repair; `-pr` hạn chế phạm vi primary range của A; table cũng được chỉ định riêng. Các node/range khác cần lịch tương ứng.

**Câu 3.** Sau khi A/B/C hoàn tất theo lịch, job của D thất bại và E chưa chạy. Báo cáo “5/5 node đã khởi tạo repair” có đủ chứng minh coverage không?

**Đáp án:** Không. Cần kết quả **thành công theo range**. Các range chỉ do D hoặc E phụ trách trong lịch vẫn là remaining scope.

**Câu 4.** Cluster có dc1 và dc2. Mọi node dc1 hoàn tất local repair, nhưng dc2 từng bị tách mạng lâu. Có thể kết luận mọi replica trên toàn cluster giống nhau không?

**Đáp án:** Không. Cần đánh giá các range/replica ở dc2 và mục tiêu đối soát xuyên DC, không chỉ số node của dc1.

**Câu 5.** Node C down vượt giai đoạn an toàn tombstone; những replica khác đã compact và loại một số dấu xóa. Có nên coi repair đơn giản từ C luôn là phương án an toàn?

**Đáp án:** Không. Phải đánh giá rủi ro zombie data, lịch repair và có thể dùng rebuild/replace theo runbook khi dữ liệu cũ không đáng tin.

**Câu 6.** Sau một đợt bootstrap, lịch dựa vào primary owner cũ vẫn đang chạy. Cần làm gì?

**Đáp án:** Cập nhật token ownership/replica set theo topology mới, xác minh range đã hoàn tất hợp lệ và lập lại những phần còn thiếu.

## 13. Tổng kết

Trong Cassandra, **repair được điều phối từ một node nhưng có phạm vi theo token range, keyspace/table và replica tham gia**. Do đó:

- **Một node repair thành công** chỉ xác nhận các phạm vi mà lệnh đã chọn và hoàn tất, không xác nhận toàn bộ cluster.
- **Full repair** và **primary-range repair** trả lời hai câu hỏi khác nhau: loại repair và các range được chọn.
- **Chạy `-pr` lần lượt theo kế hoạch** có thể phân chia coverage, nhưng cần tính đủ owner và xét topology/DC thực tế.
- **Remaining scope** là hợp của các range chưa được repair thành công, gồm job thất bại, chưa chạy, bị giới hạn sai DC/table hoặc thay đổi ownership.
- **Anti-entropy repair** khác hinted handoff, read repair và compaction; repair phải được lập lịch trước khi mất an toàn tombstone, nhất là sau outage dài.
- **Đo coverage theo range, table và DC** đáng tin hơn đếm số node đã chạy lệnh hoặc đọc một partition thành công từ Java.

Khi vận hành, hãy bắt đầu từ **danh sách phạm vi mục tiêu**, điều phối repair có kiểm soát theo node/range, giữ bằng chứng hoàn tất và xử lý những phạm vi còn lại. Chỉ khi các phạm vi yêu cầu đều có kết quả thành công mới có cơ sở nói chiến dịch repair toàn cluster đã đạt mục tiêu; điều đó vẫn không thay thế giám sát lỗi, lịch repair định kỳ và thực hành quản lý replication an toàn.
