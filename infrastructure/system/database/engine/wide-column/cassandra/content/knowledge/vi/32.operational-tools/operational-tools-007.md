# nodetool repair/rebuild/cleanup và phạm vi dữ liệu tác động

> **Chương:** Công cụ vận hành  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — kiến trúc phân tán và mô hình wide-column của Apache Cassandra, thiết kế bảng theo truy vấn, khóa phân vùng, nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và kết nối ứng dụng Java.

Một node Cassandra có thể chứa dữ liệu **đúng quyền sở hữu**, **thiếu dữ liệu cần có**, hoặc **còn dữ liệu không còn thuộc quyền sở hữu** sau khi topology thay đổi. Ba lệnh `nodetool repair`, `nodetool rebuild` và `nodetool cleanup` đều liên quan dữ liệu trên node, nhưng xử lý **ba bài toán khác nhau**:

- **`repair`:** đối chiếu dữ liệu giữa các replica và đồng bộ những khác biệt, phục vụ tính nhất quán lâu dài.
- **`rebuild`:** dùng streaming để nạp những token range mà **node hiện tại cần giữ** từ các node nguồn; thường gặp khi bổ sung một datacenter.
- **`cleanup`:** loại bỏ dữ liệu của các token range mà **node hiện tại không còn cần giữ** sau khi thay đổi quyền sở hữu.

Chọn sai lệnh có thể vừa gây tải lớn vừa không giải quyết lỗi: chạy `cleanup` không “sửa” replica thiếu dữ liệu, còn `repair` không nhất thiết dọn dữ liệu thừa sau bootstrap. Không lệnh nào thay thế thiết kế partition key, replication factor (RF) hợp lý, consistency level (CL) thích hợp hoặc quy trình sao lưu/khôi phục.

**Phạm vi phiên bản:** các nguyên tắc áp dụng cho Apache Cassandra 4.x–5.x và nhiều phiên bản trước, nhưng tham số CLI, lựa chọn mặc định của `repair`, phạm vi streaming và cơ chế theo dõi có thể thay đổi theo phiên bản/bản phân phối. Trước khi chạy trên hệ thống thật, lấy `nodetool help repair`, `nodetool help rebuild`, `nodetool help cleanup` trên **đúng bản đang cài**, cùng runbook topology của cụm. Mọi lệnh thao tác trong bài dùng cho **cluster lab cô lập**; các ví dụ tải lớn chỉ có giá trị minh họa.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác biệt giữa **logical token ownership**, **replica placement**, **dữ liệu vật lý đang lưu** và **độ đồng bộ giữa replica**.
2. Chọn chính xác `repair`, `rebuild` hoặc `cleanup` cho một tình huống, chỉ ra dữ liệu của node nào bị tác động.
3. Giải thích phạm vi theo node, keyspace, table, token range, datacenter và replica liên quan, thay vì hiểu sai rằng một lần gọi `nodetool` áp dụng toàn cluster.
4. Phân biệt repair thông thường, **incremental repair** và **full repair**, cũng như mục đích của giới hạn phạm vi repair.
5. Mô tả yêu cầu trước/sau khi rebuild một node ở datacenter mới hoặc cleanup sau thay đổi topology.
6. Theo dõi streaming, repair, compaction, dung lượng và tính sẵn sàng; diễn giải timeout, tombstone, compaction và yêu cầu Java client trong quá trình bảo trì.

## 2. Bốn khái niệm phải kiểm tra trước khi chọn lệnh

### 2.1. Token ownership không đồng nghĩa dữ liệu vật lý

Cassandra ánh xạ **partition key → token → replica endpoints** dựa trên partitioner, vị trí token của node và replication strategy của keyspace. Với `NetworkTopologyStrategy`, RF được khai báo theo datacenter. Mỗi node chỉ cần lưu các partition thuộc những token range mà nó làm replica theo topology hiện tại.

Tuy nhiên, sau sự cố hoặc thay đổi topology, trạng thái vật lý có thể lệch khỏi trạng thái mong muốn:

| Trạng thái | Ví dụ | Việc phải làm |
|---|---|---|
| Node **được chọn** làm replica nhưng thiếu mutation mới | Node Down trong khi các replica khác nhận ghi thành công | Đối soát và đồng bộ replica bằng repair theo quy trình |
| Node mới trong một DC **cần nhận** các token range của mình | Mở rộng sang DC thứ hai và nạp dữ liệu cho replica mới | Streaming/bootstrap/rebuild đúng kịch bản |
| Node **không còn được chọn** làm replica cho một số range | Thêm node làm token ownership dịch chuyển | Cleanup dữ liệu thừa **sau** khi xác nhận chủ sở hữu mới đã nhận |
| Node vừa giữ dữ liệu đúng vừa có dữ liệu thừa | Sau thay đổi topology chưa cleanup | Tiếp tục phục vụ range đúng; cleanup range không còn thuộc node |

Lưu ý: `nodetool status` thể hiện trạng thái và mức sở hữu token, nhưng **không chứng minh một partition cụ thể đã đủ dữ liệu hoặc mọi replica đã đồng bộ**. Danh sách endpoint dự kiến đến từ metadata; nội dung dữ liệu thực phải được kiểm chứng bằng repair/streaming metrics và truy vấn phù hợp.

### 2.2. Khác biệt ba lệnh trên một sơ đồ

~~~mermaid
flowchart TB
    R["Nhiều replica có cùng token range"] --> Q["repair: so sánh và đồng bộ khác biệt"]
    S["Node mới / DC mới cần dữ liệu cho range được giao"] --> T["rebuild: stream dữ liệu từ nguồn sang node hiện tại"]
    U["Node cũ còn dữ liệu của range đã chuyển chủ"] --> V["cleanup: loại bỏ dữ liệu thừa ở node hiện tại"]
    Q --> W["Mục tiêu: replica thống nhất"]
    T --> X["Mục tiêu: node có dữ liệu cần sở hữu"]
    V --> Y["Mục tiêu: node giải phóng dung lượng không còn cần"]
~~~

| Thuộc tính | `nodetool repair` | `nodetool rebuild` | `nodetool cleanup` |
|---|---|---|---|
| Câu hỏi chính | Replica của cùng range có khác nhau không? | Node này lấy dữ liệu cần có từ đâu? | Node này còn giữ range không thuộc mình không? |
| Tác động cốt lõi | So sánh hash/range, stream dữ liệu khác biệt giữa các replica | Stream dữ liệu phù hợp ownership về **node nhận** | Loại bỏ dữ liệu vật lý **không còn thuộc node chạy lệnh** |
| Vùng ảnh hưởng | Range thuộc phạm vi repair trên node điều phối và các peer tham gia | Range mà node hiện tại cần nhận | Range node hiện tại **không** còn là replica |
| Phát sinh network I/O | Có, và có thể lớn | Có, thường lớn khi nạp dữ liệu | Chủ yếu scan/rewrite local SSTable; không phải công cụ cấp bản sao cho node mới |
| Phát sinh disk/CPU I/O | Có: đọc dữ liệu, Merkle tree, streaming, compaction liên quan | Có: nhận/ghi SSTable, validation/index và compaction liên quan | Có: quét/viết lại SSTable và giải phóng file |
| Dùng để xử lý node Down lâu rồi quay lại | Có thể cần, nếu còn trong điều kiện an toàn; xem `gc_grace_seconds` | Chỉ khi nằm trong quy trình nạp lại phù hợp | Không giải quyết dữ liệu bỏ lỡ |
| Dùng sau thêm node | Có thể theo runbook để xác minh/sửa chênh lệch | Không mặc định phải chạy trên mọi node cũ | Thường chạy trên node cũ sau khi streaming và topology ổn định |
| Dùng khi thêm datacenter mới | Cần thiết về sau theo lịch consistency | Là một bước streaming phổ biến cho node mới trong DC mới | Chỉ khi node có range không còn thuộc mình |

**Phạm vi thao tác luôn gắn với keyspace và topology.** Có keyspace RF=3 ở `dc1` và RF=0 ở `dc2` thì khái niệm “replica cần chứa dữ liệu” khác keyspace RF=3 ở cả hai DC. Không dùng một lệnh cho toàn bộ keyspace rồi cho rằng mọi datacenter có cùng tác động.

## 3. nodetool repair: đối soát các bản sao cùng token range

### 3.1. Repair giải quyết vấn đề gì?

Giả sử một partition được sao chép tại ba replica A, B, C (RF=3). A và B ghi nhận mutation mới, C đã mất kết nối nên vẫn giữ giá trị cũ. Sau khi C quay lại, **hinted handoff** có thể bổ sung một số mutation bị lỡ, nhưng hints có giới hạn lưu trữ/thời gian và không bảo đảm mọi sai lệch đều được khắc phục.

**Anti-entropy repair** kiểm tra dữ liệu giữa replica cho các token range được chọn. Nó dùng cơ chế như so sánh Merkle tree và streaming các range khác nhau để sửa chênh lệch. Thuật toán và cách phân nhóm/giữ trạng thái repair thay đổi theo phiên bản, nhưng mục đích là **làm cho các replica liên quan chứa dữ liệu phù hợp**.

~~~text
Trước repair:
  Replica A: K = V2
  Replica B: K = V2
  Replica C: K = V1 (đã lỡ mutation)

Repair trên token range chứa K:
  kiểm tra khác biệt -> truyền dữ liệu/cập nhật bị thiếu

Sau repair thành công và xác minh:
  A, B, C có trạng thái dữ liệu phù hợp
~~~

**Repair không “đưa dữ liệu mới nhất của node gọi lệnh đi ghi đè toàn bộ node khác”.** Cassandra phải so sánh các phiên bản, timestamp và tombstone theo quy tắc giải quyết xung đột. Với concurrent writes và timestamp khác nhau, “mới nhất” theo đồng hồ ứng dụng chưa chắc trùng với phiên bản thắng trong Cassandra.

### 3.2. Phạm vi của một lần gọi repair

Ví dụ lệnh minh họa:

~~~bash
# Repair theo mặc định của phiên bản đang chạy (kiểm tra trước bằng help).
nodetool repair operational_lab

# Full repair cho một bảng trong keyspace, trong cluster lab.
nodetool repair --full operational_lab events_by_device
~~~

Khi gọi `nodetool repair` trên node X:

1. Node X là **điểm khởi xướng** phiên repair; nó lựa chọn range nằm trong phạm vi được lệnh/chế độ repair xác định.
2. Các replica khác của những range đó **có thể tham gia**, tiêu thụ CPU, I/O và network để đối chiếu/stream dữ liệu.
3. Những token range **không thuộc phạm vi được chọn** sẽ không tự nhiên được repair chỉ vì có cùng tên keyspace.
4. Trong một cluster nhiều node, chạy một lệnh trên **một node bất kỳ** không đồng nghĩa đã bao phủ toàn bộ dữ liệu của toàn cluster. Muốn phủ đủ token ranges cần kế hoạch theo ownership và phiên bản.

Với một keyspace có nhiều bảng, tùy cách gọi lệnh có thể áp dụng mọi bảng được chọn mặc định hoặc chỉ những bảng được chỉ định. Phạm vi **keyspace/table** giúp giảm khối lượng công việc nhưng không thay đổi chủ đề cơ bản: repair phải bao phủ các **range và replica** liên quan.

### 3.3. Incremental repair, full repair và repaired SSTables

| Chế độ | Mục tiêu | Hạn chế/điểm cần nhớ |
|---|---|---|
| **Incremental repair** | Theo dõi/đánh dấu phạm vi dữ liệu đã repair để các lần tiếp theo tập trung vào dữ liệu chưa repair | Có trạng thái phiên repair và phân loại repaired/unrepaired; cần nhất quán lịch vận hành |
| **Full repair** | Đối soát mọi dữ liệu trong phạm vi đã chọn, không giới hạn chỉ dữ liệu chưa repaired | Chi phí có thể lớn; không phải lựa chọn chạy liên tục trên mọi node |
| **Preview repair** (nếu phiên bản hỗ trợ) | Ước lượng/kiểm tra tình trạng lệch dữ liệu mà không thực hiện cùng dạng sửa như repair thực | Không thay thế repair hoàn tất; hành vi/flag cần xác minh bằng `help` |

Trong Cassandra 4.x/5.x, `nodetool repair` thường có **incremental repair mặc định** và `--full` để chọn full repair. Các tùy chọn và khả năng của phiên bản 3.x hoặc bản phân phối khác có thể khác; đừng đọc một runbook cũ rồi suy rằng lời gọi không có flag là full repair.

Không nên phối hợp incremental/full repair tùy hứng trong một topology đang thay đổi. Incremental repair có metadata/trạng thái và quy tắc khôi phục khi phiên bị ngắt; lịch phải bao phủ đúng range, DC và tables, kiểm tra kết quả thành công thực tế.

### 3.4. Giới hạn phạm vi theo datacenter và primary range

Tùy phiên bản, `nodetool repair` có các lựa chọn như:

- `--full`: chế độ full.
- `-pr` hoặc `--partitioner-range` trong một số bản: chỉ repair **primary ranges** của node, thường dùng trong lịch chạy trên nhiều node để giảm công việc trùng nhau; kiểm tra tên flag cụ thể.
- `-local` hoặc lựa chọn datacenter tương ứng: hạn chế tập tham gia trong **DC cục bộ** theo semantics của phiên bản, có thể không sửa được lệch dữ liệu giữa các DC.
- Các tùy chọn giới hạn keyspace, table, token ranges, nodes hoặc mức song song, tùy bản phát hành.

**Đừng suy rằng chạy `-pr` trên một node là repair tất cả replicas của keyspace**, hoặc `-local` đã đồng bộ liên DC. Với multi-DC, phải hiểu rõ phạm vi người tham gia, replication strategy và mục tiêu repair trước khi lập lịch.

### 3.5. Tombstone, `gc_grace_seconds` và nguy cơ zombie

Một replica có thể lỡ thao tác `DELETE` rồi giữ dữ liệu cũ. Tombstone trên các replica còn lại giữ vai trò che dữ liệu ấy khi đồng bộ, nhưng tombstone có thể được thu hồi qua compaction **sau khi qua cửa sổ `gc_grace_seconds`** và đủ điều kiện cục bộ.

Nếu node bỏ lỡ delete quay lại **sau khi tombstone ở các replica khác đã bị purge**, dữ liệu cũ có thể phát tán lại thành **zombie data**. Vì vậy:

- Repair cần được thực hiện đủ thường xuyên và **hoàn thành**, với thời gian dự phòng so với cửa sổ grace.
- Không rút ngắn `gc_grace_seconds` chỉ để giảm dung lượng khi chưa có lịch repair, kiểm tra node Down và quy trình khôi phục tin cậy.
- Node mất kết nối lâu hơn grace có thể cần **rebuild/replace từ nguồn sạch** theo runbook, thay vì đơn giản đưa trở lại vòng và repair như bình thường.
- `nodetool cleanup` không phải cơ chế xử lý zombie; nó không biết bên nào có tombstone lịch sử nếu phạm vi dữ liệu vẫn thuộc node.

## 4. nodetool rebuild: nạp dữ liệu cần sở hữu bằng streaming

### 4.1. Mục đích và nguồn dữ liệu

`nodetool rebuild` điều khiển **node đang gọi lệnh** nhận dữ liệu từ những node nguồn cho các token ranges mà nó cần giữ theo replication metadata hiện tại. Kịch bản thường gặp là **mở rộng sang một datacenter mới**: các node DC mới đã tham gia cluster nhưng chưa có bản sao dữ liệu đầy đủ; chúng lấy dữ liệu từ DC hiện hữu.

Ví dụ cấu trúc logic:

~~~text
Trước mở rộng:
  dc1: A, B, C; keyspace RF dc1 = 3

Sau khi topology mới được cấu hình đúng:
  dc1: A, B, C
  dc2: D, E, F; keyspace RF dc1 = 3, dc2 = 3

Đích:
  D, E, F (dc2) nhận dữ liệu cho range mà từng node cần giữ.
  Bản sao ở dc1 tiếp tục phục vụ ứng dụng theo CL/định tuyến phù hợp.
~~~

Một ví dụ CLI thường gặp:

~~~bash
# Chạy trên node mới tại dc2; "dc1" là tên DC nguồn thực tế.
nodetool rebuild dc1
~~~

Nhiều phiên bản hỗ trợ đối số datacenter nguồn ở cuối lệnh; cách chỉ định keyspace, tokens hoặc filters (nếu có) khác theo phiên bản. Chạy `nodetool help rebuild` tại node mục tiêu trước khi áp dụng. **Không chạy đồng loạt trên mọi node trong mọi DC** vì tưởng đây là lệnh “làm mới toàn cluster”.

### 4.2. Phạm vi cụ thể của rebuild

| Khía cạnh | Phạm vi cần hiểu |
|---|---|
| **Đích** | **Node hiện tại** nơi gọi `nodetool rebuild` |
| **Nguồn** | Các node nguồn có dữ liệu cần stream, có thể giới hạn theo DC nguồn |
| **Token ranges** | Những ranges mà node nhận phải sở hữu theo topology/keyspace |
| **Dữ liệu** | Dữ liệu của các keyspace/tables trong phạm vi rebuild được phiên bản hỗ trợ |
| **Đường dữ liệu** | Streaming qua network, ghi SSTable/disk trên node nhận |
| **Tác động** | Nguồn chịu disk/network read; đích chịu network/disk write và công việc nền |

**Rebuild không phải khôi phục snapshot toàn bộ cluster.** Nó không tự động chụp backup, không bảo đảm sửa mọi dữ liệu cũ nếu chính nguồn đã thiếu/sai, và không thể chọn “node bất kỳ” làm đích theo tên nếu bạn đang gọi CLI trên node khác. Đích của lệnh là **node mà `nodetool` đang điều khiển**.

### 4.3. Rebuild khác bootstrap và replace node

Các quy trình này có liên hệ nhưng **không đồng nhất**:

- **Bootstrap**: node mới tham gia ring và nhận các range cần thiết theo quy trình tham gia cluster.
- **Rebuild**: node đã nằm trong topology nhận/nhận lại dữ liệu range của mình qua streaming; thường là lựa chọn trong quy trình thêm DC.
- **Replace**: thay một node chết bằng node mới theo cơ chế replacement/bootstrapping và cấu hình phù hợp; không nên mặc định gọi `rebuild` là đủ thay toàn bộ runbook replacement.

Việc thêm DC mới cần thứ tự cẩn trọng giữa cấu hình snitch/DC/rack, replication strategy, số node, bootstrapping và streaming. Không tự sửa tên DC/rack của node đang phục vụ production rồi chạy rebuild để “chuyển” node sang nơi khác.

### 4.4. Vì sao rebuild thành công vẫn phải xác minh?

Một phiên streaming kết thúc thành công nghĩa là tiến trình streaming của phạm vi đã chạy xong, **không tự bảo đảm**:

- Đúng tất cả keyspace đang phục vụ đã khai báo RF ở DC đích.
- Mọi client đã chọn local datacenter và CL phù hợp cho hoạt động multi-DC.
- Dữ liệu trên các replica nguồn đã đồng bộ trước khi stream.
- Dữ liệu còn đến mới trong quá trình chuyển đổi không tạo chênh lệch cần repair/đối soát thêm.

Do đó, sau rebuild cần xác minh schema, endpoint của partition mẫu, tình trạng stream, số liệu bảng, đọc ở CL dự kiến và lịch repair tiếp theo.

## 5. nodetool cleanup: bỏ range không còn thuộc node

### 5.1. Khi nào xuất hiện dữ liệu thừa?

Giả sử `dc1` có A, B, C, mỗi node đang là replica của các range theo RF/topology cũ. Thêm D thành công sẽ làm phân bố token/ranges thay đổi; một số range được chuyển sang D hoặc được gán lại. Cassandra có thể stream dữ liệu cần thiết đến D, nhưng các SSTable cũ trên A/B/C vẫn có thể còn chứa partition mà theo ring mới chúng không cần giữ nữa.

`nodetool cleanup` kiểm tra ownership hiện tại và **loại bỏ dữ liệu vật lý không còn thuộc phạm vi replica của node chạy lệnh**. Đây là công tác thu hồi dung lượng sau thay đổi topology.

~~~bash
# Ví dụ chỉ trong cluster lab đã hoàn tất streaming/topology.
nodetool cleanup operational_lab

# Chỉ bảng mục tiêu:
nodetool cleanup operational_lab events_by_device
~~~

Trong môi trường thực, lệnh này có thể tốn disk I/O đáng kể do phải đọc/viết lại SSTable; kiểm tra scope và khả năng tác động dịch vụ trước khi dùng.

### 5.2. Phạm vi dữ liệu cleanup

| Câu hỏi | Trả lời |
|---|---|
| Cleanup chạy trên node nào? | Node được `nodetool` điều khiển; không tự dọn các node khác |
| Xóa những dữ liệu nào? | Phần dữ liệu thuộc **ranges không còn là trách nhiệm replica của node đó** trong phạm vi keyspace/table |
| Có gửi dữ liệu sang owner mới không? | **Không**: cleanup chỉ dọn bản thừa; owner mới phải nhận dữ liệu qua bootstrap/streaming trước |
| Có xóa các hàng mà client vừa `DELETE` không? | Không theo logic nghiệp vụ đó; thu hồi tombstone thuộc compaction và điều kiện riêng |
| Có sửa dữ liệu thiếu trên replica khác không? | Không; dùng streaming/rebuild/repair phù hợp |
| Vì sao disk chưa giảm tức thì? | File có thể được viết lại/giải phóng theo tiến trình compaction và quản lý SSTable; còn snapshot hoặc file khác giữ dung lượng |

Không dùng cleanup khi cluster vẫn đang chuyển trạng thái, khi node mới chưa hoàn tất streaming hoặc khi một replica vẫn có nguy cơ mất bản sao duy nhất của range. **Cần xác nhận node sở hữu mới đã Up/Normal và nhận dữ liệu đúng trước khi dọn node cũ.**

### 5.3. Sau cleanup vẫn có thể thấy disk đầy vì sao?

Nên kiểm tra:

1. SSTable chứa nhiều ranges, quá trình rewrite/compaction vẫn đang chạy hoặc giữ file tạm.
2. Snapshot/hard-link hoặc backup ở filesystem vẫn chiếm dung lượng mặc dù file live đã được thay thế.
3. Dữ liệu mà node vẫn còn sở hữu theo RF/topology là rất lớn; cleanup không thể xóa dữ liệu đúng quyền sở hữu.
4. Commit log, hints, transaction logs hoặc compaction backlog chiếm disk.
5. Thêm node chưa thật sự thay đổi replica placement như dự kiến; với RF và số node cụ thể, nhiều range vẫn thuộc node cũ.

Số disk bytes giải phóng **không thể tính chính xác** từ một tỷ lệ “ownership 40% → 30%”: vnodes, nén, phân bố partition/hot keys, snapshot và RF khiến dữ liệu vật lý không tỷ lệ hoàn toàn với token ownership.

## 6. Câu chuyện vận hành: ba tình huống dễ nhầm

### 6.1. Tình huống A — Một replica Down 24 giờ

**Hiện trạng:** RF=3, một node tạm Down, các ghi ở `LOCAL_QUORUM` tiếp tục thành công trên hai replica còn lại. Sau khi khôi phục node:

1. Kiểm tra `nodetool status`, log, thời gian Down và cấu hình `gc_grace_seconds` của các bảng quan trọng.
2. Kiểm tra hints có hoạt động đúng nhưng **không chỉ dựa vào hints**.
3. Lập repair cho các ranges/tables bị ảnh hưởng theo runbook; quan sát repair session, stream và trạng thái hoàn tất.
4. Kiểm chứng đọc dữ liệu mẫu từ ứng dụng/CL phù hợp và theo dõi read-repair/consistency symptoms nếu có.

**Lệnh chính cần cân nhắc:** `nodetool repair`. Không dùng `cleanup` vì replica không bị thay đổi ownership, và không mặc định `rebuild` nếu node chỉ bỏ lỡ một khoảng ghi ngắn trong điều kiện còn an toàn repair.

### 6.2. Tình huống B — Mở datacenter mới

**Hiện trạng:** cluster `dc1` ổn định; thêm `dc2` gồm D/E/F để phục vụ đọc/ghi cục bộ.

1. Xác nhận topology thực tế, snitch/rack và RF theo DC, đủ node/đĩa/network; chuẩn bị quy trình mở DC đúng phiên bản.
2. Đưa node mới vào trạng thái phù hợp theo runbook (bootstrap/initialization), tránh tự suy thứ tự chỉ từ một lệnh.
3. Rebuild/stream trên **từng node nhận** trong `dc2` từ DC nguồn hợp lệ; giám sát `nodetool netstats` và dung lượng.
4. Đối chiếu endpoint/partition mẫu, kiểm tra CL `LOCAL_QUORUM` ở `dc2` chỉ sau khi replica đã sẵn sàng; lập repair/đối soát tiếp theo.

**Lệnh chính cần cân nhắc:** `nodetool rebuild dc1` trên node nhận. `repair` đóng vai trò duy trì/đối soát, `cleanup` chỉ khi có dữ liệu thừa do ownership thay đổi; **không** là bước thay cho streaming.

### 6.3. Tình huống C — Thêm node trong DC rồi disk cũ vẫn đầy

**Hiện trạng:** cụm một DC thêm node D, D đã Up/Normal và hoàn tất streaming. Các node cũ vẫn chứa nhiều SSTable range mà chúng không còn sở hữu.

1. Kiểm tra tất cả node ổn định và streaming kết thúc, replica placement của keyspace đúng với thiết kế.
2. Xác nhận không có job topology đang chạy; kiểm tra snapshot/backup và tài nguyên trống đủ để chạy rewrite.
3. Chạy `nodetool cleanup <keyspace>` **trên từng node cũ cần dọn**, theo lịch bảo trì, tránh dồn I/O đồng thời.
4. Đo disk usage trước/sau, SSTable count, compaction backlog, latency của ứng dụng; kiểm tra dữ liệu ở owner mới.

**Lệnh chính cần cân nhắc:** `nodetool cleanup`. Không thay nó bằng `repair` với kỳ vọng dung lượng tự giảm, và không cleanup node D chỉ vì D vừa được thêm mà chưa chứng minh nó có data out-of-range.

## 7. Lab CQL và quan sát phạm vi lệnh

### 7.1. Chuẩn bị và tạo dữ liệu mẫu

Thực hành trên **cluster Cassandra thử nghiệm có ít nhất ba node** thuộc datacenter thật sự tên `dc1`, với `nodetool` và `cqlsh`. Nếu lab có topology khác, sửa RF/DC/CL cho phù hợp; kiểm tra trước bằng:

~~~bash
nodetool status
nodetool describecluster
nodetool help repair
nodetool help rebuild
nodetool help cleanup
~~~

Trong `cqlsh`:

~~~sql
SELECT release_version FROM system.local;

CREATE KEYSPACE IF NOT EXISTS operational_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS operational_lab.events_by_device (
    device_id uuid,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO operational_lab.events_by_device
    (device_id, event_time, event_id, payload)
VALUES (
    d654b0fe-7357-497f-8db4-59b165d58a0f,
    '2026-11-21T09:00:00Z',
    80aaeac3-1f11-4f66-877f-d9ccfca2216d,
    'sample-event'
);

SELECT device_id, event_time, event_id, payload
FROM operational_lab.events_by_device
WHERE device_id = d654b0fe-7357-497f-8db4-59b165d58a0f;
~~~

**Lưu ý:** `IF NOT EXISTS` không thay thế cấu hình/key schema của đối tượng đã tồn tại. Nếu tên `operational_lab` đã được sử dụng, kiểm tra `DESCRIBE KEYSPACE` và `DESCRIBE TABLE`; chọn tên lab khác nếu cần để tránh nhầm RF/table cũ. Dữ liệu mẫu chỉ để kiểm tra truy vấn, **không** đủ để benchmark repair/streaming.

### 7.2. Kiểm tra replica placement của partition mẫu

Trên một node:

~~~bash
nodetool getendpoints operational_lab events_by_device d654b0fe-7357-497f-8db4-59b165d58a0f
nodetool tablestats operational_lab.events_by_device
nodetool netstats
nodetool compactionstats
~~~

Đối chiếu `getendpoints` với `nodetool status`. Với RF=3 và đủ node vật lý, danh sách endpoint theo metadata thường có ba node khác nhau. **Endpoint được liệt kê không chứng minh** node đã stream xong, đang Up hay có bản sao dữ liệu đầy đủ.

Ghi lại trước khi chọn lệnh:

| Bằng chứng | Quan sát cần lưu | Ý nghĩa |
|---|---|---|
| `nodetool status` | Node UN/DN, DC/rack, tokens, ownership | Tình trạng topology của mỗi node |
| `getendpoints` | Danh sách replica của partition mẫu | Ai **nên** giữ dữ liệu của khóa đó |
| `tablestats` | SSTable/disk size/read-write latency theo bảng | Tài nguyên và thay đổi storage |
| `netstats` | Streaming sessions và trạng thái transfers | Rebuild/repair có streaming hay đã hoàn tất |
| `compactionstats` | Công việc compaction đang/pending | Dự báo khả năng tranh chấp I/O |
| Repair logs/metrics | Range/table, session và kết quả | Chứng cứ repair thành công, không chỉ lệnh đã khởi chạy |

### 7.3. Thử repair trên phạm vi nhỏ

Chọn một bảng lab, ghi lại thời điểm và tải nền. Nếu cluster có đủ node và ngân sách tài nguyên:

~~~bash
# Full repair đúng một bảng trong lab; có thể tạo tải đáng kể.
nodetool repair --full operational_lab events_by_device
~~~

Trong khi chạy, theo dõi trên node điều phối **và peer tham gia**:

~~~bash
nodetool netstats
nodetool compactionstats
nodetool tpstats
~~~

Sau đó, đọc log/session hoàn tất, đối chiếu lỗi/timeout, node trạng thái UN và truy vấn mẫu ở CL phù hợp. **Không** suy ra “toàn cluster đã được repair” khi chỉ chạy một lệnh trên một node và một table.

### 7.4. Rebuild và cleanup là lab topology riêng

Không thể biểu diễn chính xác tác động của `rebuild` hay `cleanup` chỉ bằng `INSERT`/`SELECT`. Cần **thực sự có thay đổi topology trong môi trường cô lập**:

| Lab | Điều kiện bắt buộc | Lệnh có thể sử dụng | Bằng chứng thành công |
|---|---|---|---|
| Rebuild DC mới | Node đích đã được khởi tạo theo runbook, metadata DC/RF và nguồn đúng | `nodetool rebuild dc1` trên node đích | Stream hoàn tất, endpoints đúng, dữ liệu mẫu đọc được ở DC mới |
| Cleanup sau mở rộng node | Chủ mới đã nhận range, mọi node ổn định | `nodetool cleanup operational_lab` trên node cũ cần dọn | Disk/SSTable thay đổi, các range còn được sở hữu tiếp tục đọc được |
| Repair replica lệch | Replica đã từng bỏ lỡ mutation, chưa quá hạn xử lý an toàn | `nodetool repair --full operational_lab events_by_device` theo phạm vi | Repair thành công, log/metrics đồng bộ; không xuất hiện dữ liệu cũ |

**Không dựng tình huống “thiếu bản sao” bằng cách xóa file SSTable thủ công.** Cách đó gây hỏng dữ liệu và làm sai điều kiện thử nghiệm. Dùng sự cố node có kiểm soát/backup snapshot trong lab và tuân thủ thao tác bootstrap/replace của đúng phiên bản.

## 8. Khi nào phải dừng hoặc hoãn bảo trì?

Repair, rebuild và cleanup đều có thể chạy dài, tiêu tốn tài nguyên và ảnh hưởng p95/p99 của ứng dụng. Trước mỗi lần thao tác:

1. **Xác nhận đúng node và cụm:** IP/host, DC, phiên bản, keyspace/table, token ranges, trạng thái cluster. Không chạy bằng nhầm môi trường.
2. **Kiểm tra RF/CL và dữ liệu sống:** có đủ replica khả dụng để ứng dụng tiếp tục đọc/ghi; nhận diện node vừa Down và tombstone grace.
3. **Kiểm tra tài nguyên:** disk còn đủ cho streaming và temporary SSTable, network bandwidth, compaction backlog, CPU/GC, lỗi I/O.
4. **Đặt phạm vi và mức song song:** chọn từng keyspace/table/node hoặc nhóm nhỏ theo runbook; không khởi chạy đồng loạt toàn cụm mà không dự toán I/O.
5. **Có phương án khôi phục:** snapshot/backup, inventory token và topology trước thay đổi; xác định ai chịu trách nhiệm hủy/tiếp tục job theo phiên bản.
6. **Theo dõi cả client:** application p50/p95/p99, timeout/Unavailable, retry rate của Java driver và queue ở ingress.

**Hoãn cleanup** nếu streaming của node sở hữu mới chưa xong hoặc topology đang dịch chuyển. **Hoãn rebuild diện rộng** nếu DC nguồn đã bão hòa hoặc thiếu disk đích. **Lập lịch repair phù hợp cửa sổ grace**; không bỏ repair triền miên cho đến khi tombstone có nguy cơ bị purge.

### 8.1. Phân biệt ba kết quả quan sát

| Kết quả | Điều nó chứng minh | Điều chưa chứng minh |
|---|---|---|
| Lệnh trả exit code 0 | Operation hoàn tất ở phạm vi lệnh theo công cụ | Mọi keyspace/node ngoài phạm vi đã nhất quán |
| `netstats` không còn stream | Không có phiên streaming đang hiện ở thời điểm đọc | Dữ liệu thiếu từ nguồn đã được nhận đầy đủ trong mọi trường hợp |
| Query mẫu đọc được ở CL=ONE | Một replica phục vụ giá trị tại thời điểm đó | Các replica khác không lệch hoặc không có zombie |
| `nodetool status` toàn UN | Các node đang Up/Normal theo nhận thức node hỏi | SSTable không hỏng, repair đã đủ hoặc ownership vật lý sạch |
| Disk giảm sau cleanup | Dữ liệu/file được thu hồi | Replicas mới đã đầy đủ nếu chưa kiểm tra streaming/CL |

Kết luận tốt nhất dựa vào **nhiều lớp bằng chứng cùng nhau**: metadata đúng, job log/metrics hoàn tất, không lỗi, dữ liệu quan trọng đọc/ghi đúng ở CL dự kiến, disk/network trở về nền.

## 9. Hệ quả đối với ứng dụng Java và consistency level

Ứng dụng Java chọn CL theo nhu cầu nhất quán và routing theo datacenter; nó không trực tiếp điều khiển sửa range của `nodetool`. Một request ghi thành công tại `LOCAL_QUORUM` với RF=3 thường cần hai replica trong DC cục bộ phản hồi — **không bảo đảm replica thứ ba đã nhận mọi mutation**. Một node phục hồi sau sự cố vẫn cần chiến lược hints/repair.

Ví dụ Java Driver 4.x cho một truy vấn kiểm chứng, giả định đã có `CqlSession session` với local datacenter được cấu hình đúng:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

PreparedStatement ps = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM operational_lab.events_by_device WHERE device_id = ?");

BoundStatement statement = ps.bind(
        UUID.fromString("d654b0fe-7357-497f-8db4-59b165d58a0f"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(100);

ResultSet results = session.execute(statement);
for (Row row : results) {
    UUID eventId = row.getUuid("event_id");
    // Đối chiếu eventId và payload với dữ liệu kiểm chứng.
}
~~~

Thay đổi topology có thể làm phân bố request giữa các node và độ trễ thay đổi. Trong giai đoạn rebuild/cleanup/repair, theo dõi **request timeout, host errors, latency, retry, pool saturation**, và đảm bảo driver biết local DC chính xác. Tăng retry vô hạn khi server đang stream/repair có thể đẩy hệ thống vào quá tải. Khi write timeout xảy ra, mutation có thể đã ghi ở một số replica; không coi timeout là rollback chắc chắn.

Truy vấn kiểm chứng nên sử dụng nhiều partition và biên token, đồng thời không bỏ qua giới hạn của CL. Với nhu cầu xác minh đồng bộ dữ liệu giữa replica, dựa vào repair/status metrics và công cụ kiểm tra đúng runbook, không kết luận chỉ từ một lần `SELECT` ở `ONE`.

## 10. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Cách hiểu đúng |
|---|---|---|
| “Repair chạy một node là repair toàn cluster” | Sai nói chung | Chỉ bao phủ ranges và participants thuộc phạm vi lệnh; cần kế hoạch bao phủ |
| “Repair giống copy nguyên keyspace từ coordinator sang node khác” | Sai | Repair so sánh dữ liệu replica và stream những khác biệt cần thiết |
| “Rebuild sẽ tự tìm và sửa tất cả dữ liệu sai ở mọi node” | Sai | Rebuild nhắm tới việc nạp ranges mà **node hiện tại cần sở hữu** |
| “Cleanup thay cho repair sau replica Down” | Sai | Cleanup dọn dữ liệu **không còn thuộc node**; không đồng bộ replica |
| “Sau khi thêm node, cleanup luôn có thể chạy ngay” | Sai | Chờ topology và streaming hoàn tất, kiểm tra owner mới |
| “Cleanup xóa tombstone hết hạn” | Sai mục đích | Tombstone purge thuộc compaction và điều kiện an toàn riêng |
| “Rebuild chỉ cần chạy trên một node bất kỳ rồi DC mới đủ dữ liệu” | Sai | Từng node nhận phải thực hiện đúng bước streaming cần thiết |
| “Full repair luôn tốt hơn chạy incremental thường xuyên” | Quá mức | Full tốn tài nguyên; chọn lịch/mô hình theo phiên bản và vận hành |
| “-local đã sửa mọi lệch dữ liệu giữa các DC” | Sai | Giới hạn participant cục bộ không bảo đảm anti-entropy liên DC |
| “Hinted handoff thay repair hoàn toàn” | Sai | Hints có giới hạn; vẫn cần anti-entropy repair |
| “Disk giảm nghĩa mọi dữ liệu đã an toàn” | Không đủ | Cần kiểm tra replica/streaming/CL và tình trạng ứng dụng |
| “Runbook 3.x dùng nguyên flags cho 5.x” | Nguy hiểm | Xác minh `nodetool help` và tài liệu đúng release |

## 11. Tình huống tự kiểm tra

**Tình huống A — replica mất kết nối:** RF=3, một replica Down trong khi các ghi ở QUORUM vẫn thành công, rồi node quay lại sau hai ngày. Cluster không đổi topology; cần ưu tiên lệnh nào?

**Gợi ý:** xác minh thời gian Down so với `gc_grace_seconds`, tình trạng hints và repair coverage. Ưu tiên lập **repair** theo phạm vi node/ranges; không cleanup. Nếu Down vượt cửa sổ an toàn, cần quy trình rebuild/replace thích hợp thay vì repair mù quáng.

**Tình huống B — mở DC mới:** `dc1` đang chứa đủ dữ liệu, `dc2` có ba node mới đã vào topology theo runbook, nhưng chưa hoàn tất nhận dữ liệu. Lệnh nào nạp range về D/E/F?

**Gợi ý:** trên **từng node đích** chạy quy trình **rebuild/streaming** từ nguồn hợp lệ, ví dụ `nodetool rebuild dc1` nếu đúng cú pháp phiên bản. Kiểm tra RF per DC, netstats và đọc ở CL cục bộ sau khi hoàn tất.

**Tình huống C — mở rộng một DC:** sau khi thêm node D, topology ổn định và D đã nhận ranges; A/B/C vẫn giữ disk cũ lớn. Lệnh nào và chạy ở đâu?

**Gợi ý:** **cleanup trên các node cũ cần dọn** theo phạm vi keyspace/table, theo dõi disk và compaction, không chỉ cleanup D. Không chạy khi streaming vẫn diễn ra.

**Tình huống D — repair một bảng:** chạy `nodetool repair --full operational_lab events_by_device` trên node A thành công. Có thể tuyên bố mọi bảng trong mọi DC đều được repair?

**Gợi ý:** **không**. Lệnh chỉ chọn bảng cụ thể và phạm vi token/participants theo node và options. Cần kế hoạch riêng để bao phủ các bảng/ranges/DC khác.

**Tình huống E — dọn tombstone:** một bảng có rất nhiều tombstone và p99 cao nhưng topology không đổi. `cleanup` có phù hợp không?

**Gợi ý:** không phải công cụ chính. Điều tra TTL/DELETE, partition size, SSTable overlap, `gc_grace_seconds`, repair và compaction strategy; cleanup chỉ xử lý range không còn thuộc node.

### Checklist kết thúc bài

- [ ] Phân biệt logical ownership, replica placement và dữ liệu SSTable thực tế.
- [ ] Phân biệt được kết quả repair, rebuild và cleanup theo **hướng dữ liệu tác động**.
- [ ] Mô tả được keyspace/table, token range, node và datacenter trong scope từng lệnh.
- [ ] Biết tại sao một lệnh repair trên một node không mặc nhiên phủ toàn cluster.
- [ ] Phân biệt full/incremental repair và vai trò của `gc_grace_seconds`.
- [ ] Biết rebuild thường dùng khi thêm DC và khác bootstrap/replace.
- [ ] Chỉ cleanup sau khi owner mới đã nhận dữ liệu và topology ổn định.
- [ ] Biết thu thập `status`, `getendpoints`, `netstats`, `tablestats`, `compactionstats` và logs trước/sau.
- [ ] Phân biệt sự thành công của lệnh với bằng chứng về tính nhất quán dữ liệu và SLO ứng dụng.
- [ ] Không chạy các lệnh I/O nặng đồng loạt khi chưa có giới hạn scope và kế hoạch hồi phục.

## 12. Tài liệu tham khảo

1. Apache Cassandra Documentation — [nodetool repair](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/repair.html): cú pháp, chế độ và phạm vi repair.
2. Apache Cassandra Documentation — [nodetool rebuild](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/rebuild.html): streaming dữ liệu về node.
3. Apache Cassandra Documentation — [nodetool cleanup](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/cleanup.html): loại bỏ dữ liệu không còn thuộc ownership hiện tại.
4. Apache Cassandra Documentation — [Anti-entropy repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): mục đích repair, lịch repair và bảo vệ tombstone.
5. Apache Cassandra Documentation — [Adding a datacenter](https://cassandra.apache.org/doc/stable/cassandra/operating/topo_changes.html): tổng quan thay đổi topology và streaming.
6. Apache Cassandra Documentation — [nodetool status](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/status.html), [netstats](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/netstats.html), [tablestats](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/tablestats.html): công cụ kiểm tra.
