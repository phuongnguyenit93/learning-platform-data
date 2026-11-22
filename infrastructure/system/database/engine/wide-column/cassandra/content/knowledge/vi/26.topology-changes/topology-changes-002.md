# Bootstrap, nhận token và streaming dữ liệu ban đầu trong Apache Cassandra

## 1. Khi thêm node, chuyện gì thực sự xảy ra?

Trong Apache Cassandra, mỗi bảng được thiết kế theo **truy vấn cần phục vụ**, dữ liệu được phân phối bằng **partition key**, và các bản sao được đặt trên những node phù hợp với **replication strategy** của keyspace. Khi thêm node để tăng năng lực lưu trữ hoặc tải đọc/ghi, hệ thống phải thay đổi **topology**: node mới nhận trách nhiệm đối với một số khoảng token và cần lấy dữ liệu đang tồn tại từ các replica hiện hữu.

Quá trình này gọi là **bootstrap**. Một node mới không thể chỉ tham gia gossip rồi ngay lập tức sở hữu đầy đủ những partition được phân công. Nó cần nhận thông tin về cluster, nhận token, xác định phạm vi dữ liệu phải có và **stream dữ liệu ban đầu** từ các nguồn phù hợp trước khi chuyển sang trạng thái phục vụ bình thường.

Hãy hình dung một cluster đang lưu sự kiện thiết bị theo partition key `device_id`. Nếu ứng dụng vừa thêm node N4, các partition có token rơi vào vùng N4 sẽ được chuyển trách nhiệm từ một số node cũ sang N4. Replication factor của keyspace không tự tăng chỉ vì cụm thêm một máy; **mục tiêu là tái phân bố các bản sao** theo cách đặt replica mới.

Trong chương **Thay đổi topology** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài này giải thích ba giai đoạn nền tảng:

1. **Bootstrap**: node mới gia nhập và thông báo trạng thái tham gia cluster.
2. **Nhận token**: node nhận vị trí trong vòng token và các khoảng dữ liệu cần chịu trách nhiệm.
3. **Streaming ban đầu**: node lấy dữ liệu cần thiết từ các replica có sẵn, đồng thời cluster tiếp tục xử lý lưu lượng.

Nắm vững quá trình này giúp tránh hiểu nhầm rằng thêm node là cân bằng dữ liệu ngay lập tức, hoặc ứng dụng Java có thể tự đọc và chép dữ liệu sang node mới.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa trong quá trình thêm node |
|---|---|
| **Partition key** | Các cột dùng để xác định partition; giá trị được partitioner ánh xạ thành token |
| **Token** | Giá trị trong không gian token; dùng để xác định vị trí partition trên vòng |
| **Token range** | Khoảng token mà node tham gia lưu trữ theo placement của cluster |
| **Primary range** | Khoảng có node là chủ sở hữu chính theo thứ tự vòng trong mô hình đơn giản |
| **Replica set** | Tập node giữ các bản sao theo replication strategy và RF của keyspace |
| **Virtual nodes (vnodes)** | Một node vật lý có thể sở hữu nhiều token/range thay vì một khoảng lớn |
| **Seed node** | Điểm liên hệ ban đầu để khám phá cluster, không phải node điều khiển trung tâm |
| **Gossip** | Trao đổi metadata/trạng thái giữa các node, giúp khám phá topology |
| **Pending range / pending replica** | Phạm vi mà node đang gia nhập sẽ có trách nhiệm sau khi chuyển giao |
| **Streaming** | Truyền dữ liệu ở mức lưu trữ giữa các node cho các khoảng cần thiết |
| **Bootstrap hoàn tất** | Node đã hoàn thành những bước gia nhập theo phiên bản và chuyển sang trạng thái bình thường |

Với `Murmur3Partitioner`, Cassandra phổ biến dùng token trong không gian số nguyên 64 bit có dấu. **Token không phải ID của hàng**. Một partition key được băm ra token; nhiều partition có thể nằm trong cùng khoảng token, và một node có thể giữ nhiều khoảng khi dùng vnodes.

Trong keyspace áp dụng `NetworkTopologyStrategy`, danh sách replica còn phụ thuộc **datacenter**, số replica từng DC và bố trí rack/snitch. Vì vậy **sở hữu token không đồng nghĩa node đó là bản sao duy nhất**. Muốn biết dữ liệu chuyển từ đâu sang đâu, phải xét topology và replication strategy cụ thể.

## 3. Node mới tiến qua những giai đoạn nào?

### 3.1. Chuẩn bị một danh tính node mới

Trước bootstrap, node cần được cấu hình như một thành viên mới của cluster:

- `cluster_name` và các thiết lập giao tiếp phải tương thích cụm đang chạy.
- `listen_address` hoặc các địa chỉ/quy tắc kết nối phải tới được từ các node khác; cổng và chính sách TLS/xác thực phải phù hợp.
- `seed_provider`/seeds giúp node tìm cluster; seed không sở hữu mọi token và không thay thế đồng bộ dữ liệu.
- Datacenter, rack, snitch và topology phải đúng với chiến lược replica của keyspace.
- Thư mục dữ liệu, commit log và danh tính của node mới phải được chuẩn bị đúng theo hướng dẫn của phiên bản; **không sao chép nguyên dữ liệu hệ thống/danh tính node khác** để dựng một node mới.
- Cấu hình token/vnodes như `num_tokens` và cơ chế cấp token phải được xác định trước lần bootstrap đầu tiên.

Nên coi việc thêm node trống vào cluster có dữ liệu là một quy trình **bootstrap thật**. Không tùy tiện tắt `auto_bootstrap` chỉ để máy hiện trạng thái UP nhanh hơn; điều đó có thể bỏ qua việc tải dữ liệu cần thiết. Cách thiết lập chính xác thay đổi theo phiên bản Cassandra và phương thức provision.

### 3.2. Khám phá cluster và thống nhất metadata

Node mới liên hệ các seed node để tìm các thành viên khác, tham gia trao đổi gossip và học thông tin vòng token/placement. Seeds là **đầu mối khám phá**, không phải master node hoặc kho dữ liệu chuyên dụng. Streaming có thể lấy dữ liệu từ các replica khác hoàn toàn với các seed đã cấu hình.

Cassandra kiểm tra những điều kiện cần thiết về danh tính, cluster và khả năng kết nối. Nếu node bị cấu hình sai tên cluster, DC, rack hoặc một số định danh, quá trình gia nhập có thể bị từ chối, treo hoặc dẫn đến topology không như mong đợi.

### 3.3. Nhận token và xác định trách nhiệm mới

Node được cấp hoặc sử dụng token theo cơ chế đã cấu hình. Với vnodes, một node có nhiều token nên dữ liệu nhận về có thể đến từ nhiều khoảng và nhiều nguồn. Hệ thống xác định **replica set sau thay đổi** cho mỗi khoảng dựa trên RF, strategy, rack/DC và các node đang có mặt.

Cần phân biệt:

- **Được gán token**: biết các khoảng sẽ do node phụ trách.
- **Đã sở hữu dữ liệu tương ứng**: đã nhận và xử lý đủ dữ liệu cần thiết từ replica nguồn.
- **Đã sẵn sàng phục vụ như node bình thường**: hoàn tất bootstrap/streaming, có trạng thái phù hợp và đạt yêu cầu kiểm tra health.

Nhận token là **thay đổi trách nhiệm định tuyến**, còn streaming là **chuyển nội dung vật lý**. Không thể dùng riêng thông tin token để kết luận đã chuyển xong dữ liệu.

### 3.4. Lập kế hoạch streaming từ replica hiện hữu

Từ các khoảng đang chuyển giao, Cassandra xác định dữ liệu cần nhận và những replica nguồn thích hợp. Việc chọn nguồn/tập stream phụ thuộc topology, RF, DC, token ranges và triển khai streaming của phiên bản đang dùng.

Các node nguồn đọc dữ liệu trong phạm vi cần chuyển và gửi sang node mới qua cơ chế streaming. Dữ liệu được tạo thành các thành phần lưu trữ phù hợp phía đích; thao tác này có thể chiếm network, disk read/write, CPU và tài nguyên compaction.

### 3.5. Bắt kịp mutation mới và hoàn tất chuyển trạng thái

Trong lúc node mới streaming, ứng dụng **vẫn có thể tiếp tục ghi** vào cluster. Cassandra có cơ chế điều phối khi topology thay đổi để những mutation liên quan đến range đang chuyển giao không chỉ phụ thuộc bản snapshot ban đầu. Chi tiết xử lý pending replica, writes trong bootstrap và bước hoàn tất khác nhau theo phiên bản.

Node không được coi đã ổn định chỉ vì nhận được luồng dữ liệu đầu tiên. Cần kiểm tra trạng thái bootstrap, các phiên stream và tình trạng lỗi; sau đó node có thể chuyển từ **joining** sang **normal**.

~~~mermaid
flowchart TD
    A["Cấu hình node mới và kiểm tra kết nối"] --> B["Tìm cluster qua seed / gossip"]
    B --> C["Nhận token hoặc vnode theo cấu hình"]
    C --> D["Tính các khoảng và replica set sau thay đổi"]
    D --> E["Chọn replica nguồn và lập stream"]
    E --> F["Stream SSTable / dữ liệu của các khoảng cần nhận"]
    F --> G["Xử lý chuyển giao và mutation phát sinh trong lúc join"]
    G --> H{"Bootstrap và stream đã hoàn tất?"}
    H -->|Chưa| I["Kiểm tra netstats, lỗi, disk và network"]
    I --> F
    H -->|Rồi| J["Node bình thường; kiểm chứng phân bố và sức khỏe"]
    J --> K["Cleanup dữ liệu thừa trên node cũ theo runbook"]
~~~

Sơ đồ phản ánh **chuỗi logic**, không phải một lịch gọi API cố định. Node có thể thực hiện các bước đồng thời, và các trạng thái/cơ chế tối ưu thay đổi theo Cassandra release.

## 4. Minh họa token ring trước và sau khi thêm node

Để dễ hình dung, giả sử một vòng token nhỏ giả lập từ `0` đến `99` (đây **không** phải toàn bộ không gian token thật của Murmur3). Một datacenter có bốn node:

~~~text
                 Vòng token giả lập
          A(10) → B(40) → C(75) → D(90) → A(10)

Mỗi partition được gắn token bằng cách hash partition key.
Trong mô hình đơn giản, token ở khoảng (10,40] đi tới B.
~~~

Giả sử thêm node **E** tại token `30`:

~~~text
Trước:  A(10) ------- B(40) ------- C(75) --- D(90)
Sau:    A(10) --- E(30) --- B(40) --- C(75) --- D(90)
                    ^
               Vị trí mới
~~~

Với cách minh họa theo thứ tự vòng, trước khi E xuất hiện, khoảng `(10,40]` có node B là chủ chính. Sau khi E được đưa vào, khoảng này chia thành:

- `(10,30]`: E trở thành node chủ chính của khoảng.
- `(30,40]`: B tiếp tục là node chủ chính.

Nếu minh họa replication factor 2 và bỏ qua quy tắc rack/DC phức tạp, replica set cho một token `25` có thể thay đổi từ **B + C** sang **E + B**. E phải lấy dữ liệu của khoảng đó từ replica nguồn phù hợp; C có thể còn giữ dữ liệu cũ cho tới khi chạy cleanup theo quy trình.

**Giới hạn của ví dụ:** Cassandra thực tế có vòng token lớn, nhiều vnode, replication strategy và lựa chọn replica theo rack/DC. Không thể áp dụng trực tiếp “node liền kề luôn là nguồn streaming duy nhất” cho mọi keyspace.

### 4.1. Tác động của vnodes

Khi một node có nhiều vnodes, nó không nhận một dải token đơn độc. Thay vào đó, nó có nhiều khoảng rải trong vòng. Ưu điểm có thể là phân phối tải đều hơn và linh hoạt hơn khi mở rộng cluster; đổi lại quá trình tính placement, streaming và quản trị token phức tạp hơn.

- `num_tokens` là một phần cấu hình liên quan số token của node trong các cấu hình vnode.
- Một số phiên bản/cấu hình hỗ trợ cơ chế lựa chọn token có cân nhắc replication để cải thiện phân phối.
- Không tự sửa token/vnode count của node **đã có dữ liệu** như thể đó là tham số hiệu năng bình thường: thay đổi token ownership là thay đổi topology và cần quy trình riêng.

Việc dự kiến node mới nhận bao nhiêu dữ liệu cần dựa vào **dung lượng từng keyspace, RF theo DC và phân bố token hiện tại**, không chỉ lấy dung lượng cluster chia cho số node.

## 5. Streaming dữ liệu ban đầu thực sự chuyển gì?

### 5.1. Streaming không phải ứng dụng Java đọc rồi INSERT lại

Bootstrap là hoạt động giữa các node ở tầng storage. Node nguồn chuyển dữ liệu của các khoảng đã xác định, thường dựa trên SSTable hoặc đơn vị lưu trữ được engine hỗ trợ. Node đích nhận và tích hợp dữ liệu vào bộ lưu trữ Cassandra.

Ứng dụng Java không cần chạy vòng lặp `SELECT *` rồi `INSERT` sang IP node mới. Làm vậy bỏ qua mô hình replica/ownership và có thể tạo lượng ghi, tombstone, timestamp hoặc mức tải khó kiểm soát. **Nút thắt của bootstrap nằm ở network và storage giữa các node**, không nằm ở việc viết logic chuyển row trong application.

### 5.2. Những tài nguyên cần dự phòng

| Tài nguyên | Tại node nguồn | Tại node đích |
|---|---|---|
| **Network** | Gửi khối dữ liệu qua streaming | Nhận dữ liệu, chịu giới hạn băng thông |
| **Disk I/O** | Đọc SSTable và dữ liệu liên quan | Ghi các tệp nhận, có thể cùng lúc tạo compaction |
| **CPU** | Xử lý stream, nén/giải nén tùy cấu hình | Xử lý stream và SSTable nhận |
| **Disk space** | Có thể chưa được thu hồi dữ liệu không còn sở hữu | Cần đủ chỗ cho dữ liệu mới, overhead và công việc nền |
| **Đường đọc/ghi** | Tranh I/O với client requests | Vừa nhận stream vừa có thể nhận mutation liên quan |

Một phiên streaming lớn có thể làm tăng p95/p99 latency của các truy vấn vẫn đang chạy. Do đó việc thêm node cần cân nhắc thời điểm, throughput và headroom, dù thao tác bootstrap không phải “downtime toàn cluster”.

### 5.3. Tốc độ và thời gian hoàn tất

Ví dụ minh họa, nếu cần truyền **300 GiB dữ liệu thực tế** và throughput end-to-end duy trì ở mức **50 MiB/s**:

~~~text
300 GiB = 300 x 1024 = 307.200 MiB
Thời gian truyền lý tưởng = 307.200 / 50
                         = 6.144 giây
                         ≈ 102,4 phút
~~~

Con số này **chỉ là cận ước lượng lý tưởng theo lưu lượng được giả định**. Thời gian thực tế còn chịu ảnh hưởng lựa chọn nguồn, giới hạn stream, TLS, network contention, disk, xử lý SSTable, retry và lượng mutation đồng thời. Không cam kết thời gian hoàn tất từ một phép chia dung lượng/băng thông đơn giản.

### 5.4. Dữ liệu nhận được có thể chưa tương đương “dữ liệu cuối cùng”

Trong lúc chuyển giao, mutation mới vẫn có thể đi tới những replica chịu trách nhiệm. Cassandra tổ chức các bước pending range và giao tiếp phù hợp để chuyển tiếp trách nhiệm, nhưng khi có network failure, node reboot hoặc stream retry, cần kiểm tra thực tế tình trạng bootstrap và sau đó duy trì lịch repair.

**Streaming phục vụ bootstrap** nhằm đặt dữ liệu ban đầu ở node mới. **Repair** là cơ chế chống entropy để so sánh và sửa khác biệt giữa các replica; hai việc có thể cùng sử dụng network và I/O nhưng khác mục tiêu.

## 6. Replication factor không tăng khi thêm node

Đây là điểm dễ nhầm trong capacity planning.

Giả sử keyspace có RF=2 trong một DC với ba node ban đầu. Mỗi partition được giữ trên **hai** replica theo placement. Thêm node thứ tư:

- RF của keyspace vẫn là **2**, trừ khi có thao tác thay đổi cấu hình riêng.
- Dữ liệu được **phân phối lại** để mỗi partition vẫn có hai replica nhưng vị trí thay đổi theo token ownership.
- Node mới phải nhận phần dữ liệu thuộc replica set mới.
- Một số bản sao ở node cũ có thể trở thành dữ liệu **không còn thuộc trách nhiệm** sau khi topology ổn định.

### Ví dụ cân bằng dung lượng

Giả sử dữ liệu logic của keyspace là **600 GiB**, RF=2, mỗi node cùng DC đủ điều kiện và phân bố token/tải hoàn toàn đều.

| Giai đoạn | Tổng bản sao logic | Trung bình node cũ | Node mới |
|---|---:|---:|---:|
| Trước thêm node: 3 node | 1.200 GiB | ~400 GiB/node | Chưa có |
| Sau cân bằng hoàn chỉnh: 4 node | 1.200 GiB | ~300 GiB/node | ~300 GiB |
| Trong quá trình bootstrap | Có thể tạm lớn hơn 1.200 GiB | Dữ liệu cũ chưa được dọn hết | Đang tăng dần tới phần cần giữ |

Con số chỉ là mô hình lý tưởng, không tính SSTable overhead, tombstone, metadata, nhiều keyspace, replication theo rack, dữ liệu nóng, compaction và skew của partition.

**Điểm vận hành quan trọng:** Sau khi node mới bootstrap, dữ liệu cũ trên node trước đây có thể vẫn chiếm đĩa. Thao tác **cleanup** trên các node cũ, theo đúng runbook và sau khi xác minh bootstrap, giúp loại bỏ dữ liệu không còn thuộc token ranges của chúng. Đừng giả định đĩa node cũ được giải phóng tự động đúng lúc node mới hiện `UN`.

Như vậy trong quá trình mở rộng cụm, cần dự phòng **chỗ trên node mới để nhận stream** và **headroom trên node cũ cho dữ liệu tồn tại tạm cùng hoạt động nền**.

## 7. Quan sát tiến độ bootstrap bằng công cụ Cassandra

### 7.1. Trạng thái node không phải chỉ số duy nhất

Một số mã trạng thái thường thấy khi chạy `nodetool status`:

| Trạng thái minh họa | Diễn giải |
|---|---|
| `UJ` | Node UP và đang **joining**; thường gắn với bootstrap chưa hoàn tất |
| `UN` | Node UP và ở trạng thái **normal** |
| `DN` | Node DOWN, trạng thái normal được biết trong ring |
| Trạng thái khác | Có thể gắn với leaving/moving hoặc tình trạng khác tùy phiên bản |

`UJ` không được xem là `UN`. Ngược lại, chỉ nhìn thấy `UN` là **cần thiết nhưng chưa đủ** để khẳng định mọi dịch vụ khỏe mạnh, read/write latency ổn định và công việc sau bootstrap như cleanup đã được hoàn tất.

### 7.2. Các lệnh đọc trạng thái

Trên node có quyền vận hành và đúng phiên bản:

~~~bash
# Xem topology, DC, rack, trạng thái UP/JOINING/NORMAL.
nodetool status

# Xem các phiên streaming, tiến độ và tình trạng transfer.
nodetool netstats

# Kiểm tra metadata gossip để điều tra thông tin thành viên.
nodetool gossipinfo

# Thông tin cluster / topology mà node đang quan sát.
nodetool describecluster

# Xem compaction đang cạnh tranh I/O với bootstrap.
nodetool compactionstats

# Xem mức lưu trữ và các chỉ số bảng (cú pháp theo phiên bản).
nodetool tablestats
~~~

`nodetool netstats` thường hữu ích để biết node đang gửi/nhận bao nhiêu dữ liệu qua streaming. Tuy nhiên không nên dựa vào một lần `netstats` rỗng để tuyên bố bootstrap hoàn tất: phải đối chiếu **trạng thái node, logs, lỗi streaming, lượng dữ liệu nhận và metadata**.

### 7.3. Metrics nên theo dõi cùng nhau

| Nhóm | Chỉ số/quan sát | Mục đích |
|---|---|---|
| **Bootstrap** | `UJ → UN`, log gia nhập, stream session success/failure | Xác nhận node vượt qua giai đoạn khởi tạo |
| **Streaming** | Bytes còn lại, bytes đã nhận/gửi, transfer rate, retry/error | Phát hiện stream tắc hoặc quá chậm |
| **Network** | Băng thông, lỗi/timeout kết nối, RTT giữa nguồn và đích | Tách nghẽn mạng khỏi nghẽn lưu trữ |
| **Disk** | Free bytes, IOPS, throughput, latency từng data directory | Tránh node đích đầy đĩa khi nhận stream |
| **Compaction** | Pending tasks, bytes rewritten, read/write latency | Phát hiện streaming tranh I/O |
| **Client workload** | p95/p99 latency, write timeout, read timeout, unavailable | Xác định ảnh hưởng đến ứng dụng |
| **Topology** | DC/rack, tokens/vnodes, phân bố dữ liệu theo node | Phát hiện sai placement hoặc mất cân bằng |
| **Sau bootstrap** | Dung lượng node cũ, kế hoạch cleanup/repair | Hoàn tất tái phân phối và đối soát |

Hệ thống giám sát phải so sánh theo **từng node**, tránh chỉ xem tổng bytes streaming toàn cluster. Một node nguồn nghẽn đĩa có thể quyết định tốc độ bootstrap dù các node khác còn rảnh.

## 8. Quy trình thêm node có kiểm soát

### Bước 1 — Kiểm tra cluster trước thay đổi

Xác nhận cluster đang ổn định: không có node down bất thường, không có repair/streaming/bootstrap ngoài dự kiến, còn đủ disk headroom, network capacity và khả năng xử lý tải.

Kiểm tra replication của các keyspace, cấu hình `NetworkTopologyStrategy`, datacenter, rack, snitch, phân bố token, dung lượng trên từng node và loại workload đang chạy. Một node mới thêm vào DC thiếu rack phù hợp có thể không mang lại replica placement như kỳ vọng.

### Bước 2 — Chuẩn bị node mới

Cấu hình đúng cluster identity, network, auth/TLS, snitch và datacenter/rack. Xác định chính sách token/vnodes, bảo đảm data/commit log directory phù hợp với một **node mới**. Phải kiểm tra khả năng kết nối tới cluster và dung lượng để nhận dữ liệu ban đầu.

**Không tái sử dụng host ID hoặc dữ liệu hệ thống của một node đang tồn tại** để “tiết kiệm thời gian” bootstrap. Thao tác thay thế một node cũ là một quy trình khác với thêm node mới.

### Bước 3 — Khởi động và theo dõi trạng thái joining

Khởi động node theo runbook của phiên bản, quan sát log bootstrap, `nodetool status` và `nodetool netstats`. Node nhận token và bắt đầu stream các khoảng phù hợp; xác nhận nguồn/destination và lượng dữ liệu đang di chuyển.

Trong lúc này, theo dõi free bytes, mức tăng disk và latency tại cả node nguồn lẫn node đích. Nếu stream rất chậm, xác định rõ do mạng, disk, compaction, lỗi giao tiếp hay giới hạn cấu hình trước khi can thiệp.

### Bước 4 — Kiểm chứng hoàn tất

Sau khi không còn hoạt động bootstrap đang dang dở, xác nhận trạng thái node `UN`, logs không còn lỗi liên quan, replication/token assignment đúng kỳ vọng và read/write health ổn định. Không dừng kiểm tra ở chỗ node “UP”.

### Bước 5 — Dọn dữ liệu cũ và đối soát

Sau khi topology ổn định, các node cũ có thể giữ SSTable chứa dữ liệu không còn chịu trách nhiệm. Xem xét **cleanup** trên đúng node/keyspace theo runbook và khả năng disk/I/O. Cleanup cũng tạo tải và có thể cần dung lượng tạm, nên không chạy ồ ạt khi node mới vừa làm tài nguyên căng.

Duy trì **repair định kỳ** và kiểm tra sự chênh lệch replica nếu có gián đoạn. Cleanup là thao tác dọn dữ liệu **không còn thuộc vùng sở hữu**, không thay thế repair.

### Bước 6 — Đo kết quả mở rộng

So sánh dung lượng phân bố thực tế, token balance, throughput và latency trước/sau. Nếu hotspot do một partition key quá nóng, việc thêm node chỉ giúp khi placement và pattern lưu lượng thật sự phân tán được tải. Một **hot partition** đơn lẻ vẫn nằm trong một replica set hữu hạn; có thể cần chỉnh mô hình partition/bucketing chứ không chỉ thêm máy.

## 9. Những lỗi thường gặp trong bootstrap

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách tiếp cận |
|---|---|---|
| Node không tìm thấy cluster | Seeds sai, firewall, port, TLS/auth, routing | Xác minh kết nối và log thay vì thay token tùy tiện |
| Node thấy cluster nhưng không join | `cluster_name`, identity, DC/rack, config không tương thích, phiên bản | So cấu hình và metadata với topology dự kiến |
| `UJ` kéo dài, streaming không tiến triển | Nguồn không sẵn sàng, network nghẽn, stream fail, disk đích đầy | Xem `netstats`, logs, filesystem, disk latency |
| Stream có tiến độ nhưng p99 tăng mạnh | Nguồn/đích tranh I/O với compaction và client traffic | Quan sát tài nguyên, điều chỉnh lịch/tốc độ theo runbook |
| Node `UN` nhưng nhận ít dữ liệu bất thường | Token/placement, RF/DC, token distribution hoặc volume dữ liệu không đều | Kiểm tra các khoảng và replication từng keyspace |
| Node cũ không giảm dung lượng | Data ngoài ownership còn tồn tại, chưa cleanup, snapshot hoặc dữ liệu mới | Đánh giá cleanup và những thành phần giữ SSTable |
| Sau join thấy read/write timeout | Node chưa ổn định, network, skew, replica placement, tải compaction | Đối chiếu logs/metrics toàn cụm, không đổ lỗi mỗi bootstrap |
| Bootstrap bị ngắt giữa chừng | Restart, lỗi ổ, mất mạng, stream failure | Dùng quy trình resume/recovery phù hợp phiên bản, giữ nguyên dữ liệu để điều tra |

Không thực hiện các thao tác xóa data directory, đặt lại token/host ID hoặc rebootstrap tùy tiện trên một node đã bắt đầu nhận dữ liệu. Quy trình resume, rebuild, replace hay remove thay đổi theo phiên bản và trạng thái node; cần xác định node đang thuộc trường hợp nào rồi mới xử lý.

## 10. Bootstrap khác gì các thao tác topology khác?

| Thao tác | Khi sử dụng | Dữ liệu di chuyển như thế nào? |
|---|---|---|
| **Bootstrap / add node** | Đưa một node mới vào cluster có sẵn | Node nhận token và stream dữ liệu ban đầu của phạm vi sẽ sở hữu |
| **Decommission** | Chủ động loại một node còn hoạt động | Chuyển trách nhiệm/dữ liệu sang replica còn lại theo topology mới |
| **Removenode** | Loại node đã không thể tham gia lại theo quy trình phù hợp | Cluster điều phối khôi phục trách nhiệm từ replica còn lại |
| **Replace node** | Thay node hỏng bằng máy khác theo quy trình nhận diện thay thế | Tái tạo dữ liệu thuộc trách nhiệm node bị thay |
| **Rebuild** | Lấy lại dữ liệu phù hợp từ DC/replica nguồn trong ngữ cảnh được hỗ trợ | Streaming phục hồi theo topology, không phải join node mới thông thường |
| **Repair** | Đồng bộ các replica đã tồn tại | So sánh và sửa khác biệt dữ liệu trên các khoảng |
| **Cleanup** | Loại dữ liệu ngoài trách nhiệm node sau thay đổi ownership | Dọn SSTable cục bộ, không phải stream sang node khác |

Các lệnh điều khiển có thể khác nhau giữa phiên bản Cassandra. Bảng nhấn mạnh **mục đích**; không tráo `cleanup`, `repair`, `replace` với `bootstrap` chỉ vì chúng đều liên quan đến di chuyển hoặc hòa giải dữ liệu.

## 11. CQL và Java: ứng dụng vẫn nên dùng partition key, CL phù hợp

### 11.1. Keyspace và bảng minh họa

Giả sử cluster có một datacenter tên `dc1` và muốn giữ ba replica trong datacenter ấy:

~~~cql
CREATE KEYSPACE telemetry_demo
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE telemetry_demo.measurements_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    temperature double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Partition key là `(device_id, event_day)`, không phải mỗi `device_id`. Khi thêm node, Cassandra phân phối lại **token của partition key kết hợp**, và replication được tính theo RF=3 cho DC `dc1`. Cấu hình topology của node mới cần nhất quán với datacenter/rack đã định nghĩa.

Truy vấn giữ đúng khóa định tuyến:

~~~cql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, temperature
FROM telemetry_demo.measurements_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

`LOCAL_QUORUM` là lựa chọn minh họa cho một DC có RF=3; yêu cầu thực tế phụ thuộc latency, consistency và topology. Nó không ra lệnh stream hay quyết định token allocation.

### 11.2. Java Driver 4.x sử dụng metadata cluster

Với Java driver, ứng dụng nên giao việc định tuyến và khám phá topology cho driver đã cấu hình datacenter đúng, thay vì hardcode IP node đang sở hữu partition.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

// contact point và DC chỉ là ví dụ; thay bằng giá trị của cluster.
try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("dc1")
        .build()) {

    PreparedStatement query = session.prepare(
        "SELECT event_time, temperature " +
        "FROM telemetry_demo.measurements_by_device_day " +
        "WHERE device_id = ? AND event_day = ? LIMIT 50"
    );

    BoundStatement statement = query.bind(
            UUID.fromString("11111111-1111-1111-1111-111111111111"),
            LocalDate.of(2026, 11, 21))
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

    for (Row row : session.execute(statement)) {
        System.out.println(row.getInstant("event_time")
            + " " + row.getDouble("temperature"));
    }
}
~~~

Driver có cơ chế theo dõi metadata/topology và định tuyến token-aware khi đủ thông tin và cấu hình phù hợp. **Ứng dụng không tự stream dữ liệu** khi node mới xuất hiện. Trong lúc cluster thay đổi, vẫn phải xử lý timeout, unavailable, retry có kiểm soát và idempotency cho những thao tác ghi có tác dụng phụ.

Một câu SELECT như trên cũng không chứng minh toàn bộ streaming đã hoàn tất. Trạng thái bootstrap cần được xác nhận bằng **nodetool, logs và metrics của cluster**.

## 12. Bài tập tình huống

**Tình huống A.** Cluster có ba node, RF=2. Thêm node thứ tư. Có phải sau đó mọi partition được lưu trên ba replica?

**Trả lời:** Không. Thêm node không tự đổi RF; mỗi partition vẫn có hai bản sao theo keyspace replication. Số replica chỉ thay đổi nếu có thao tác cấu hình RF riêng.

**Tình huống B.** Node mới thấy được seed và xuất hiện ở trạng thái `UJ`. Có thể xem đã bootstrap xong chưa?

**Trả lời:** Chưa. `UJ` cho biết node đang joining. Cần theo dõi streaming, logs và chuyển sang trạng thái bình thường theo phiên bản.

**Tình huống C.** Sau khi node mới `UN`, các node cũ vẫn dùng gần như cùng dung lượng đĩa. Có phải bootstrap thất bại?

**Trả lời:** Không nhất thiết. Dữ liệu cũ ngoài trách nhiệm có thể còn tồn tại cho tới khi cleanup; ngoài ra snapshot, compaction và load mới cũng giữ dung lượng.

**Tình huống D.** Stream cần truyền 300 GiB, đo 50 MiB/s. Thời gian lý tưởng khoảng bao lâu?

**Trả lời:** Khoảng 102,4 phút, chưa tính retry, overhead, disk, network contention và dữ liệu mới phát sinh.

**Tình huống E.** Nhóm vận hành muốn copy toàn bộ data directory từ một node đang chạy sang node mới, sửa IP rồi khởi động để “bỏ qua streaming”. Điều gì sai?

**Trả lời:** Danh tính node và metadata topology không thể được nhân bản tùy tiện. Điều đó có thể gây xung đột identity/token hoặc dữ liệu không đúng ownership. Thêm node mới phải theo bootstrap đúng quy trình; thay node hỏng có quy trình riêng.

**Tình huống F.** Sau khi thêm node, một partition `device_id` nóng vẫn gây timeout trên đúng replica set. Vì sao thêm node chưa chắc sửa được?

**Trả lời:** Một partition vẫn được đặt tại số replica hữu hạn theo RF. Thêm tổng node không chia nhỏ nội dung của một partition. Cần xem mô hình khóa/bucketing, phân bố tải và pattern truy vấn.

## 13. Những điều cần nhớ

**Bootstrap là quá trình thay đổi trách nhiệm dữ liệu của cluster**, không chỉ là khởi động một máy Cassandra mới:

- **Token allocation** quyết định các khoảng partition mà node mới sẽ chịu trách nhiệm; **replication strategy** quyết định những replica thực sự giữ dữ liệu.
- **Streaming ban đầu** đưa dữ liệu hiện có từ replica nguồn tới node mới; seed chỉ giúp khám phá cluster, không mặc định là nguồn dữ liệu.
- **Vnodes** khiến node nhận nhiều khoảng token, có thể stream từ nhiều nguồn và cần phân tích placement theo từng keyspace.
- **`UJ` và `UN` khác nhau**: node đang joining chưa được coi là thành viên bình thường; kể cả sau `UN` vẫn cần xác minh health, dung lượng và công việc hậu bootstrap.
- **Dung lượng đĩa node cũ không tự giảm ngay**: cần xem xét cleanup, snapshot và các thao tác nền sau khi topology ổn định.
- **Java client** nên giữ định tuyến theo partition key và consistency thích hợp; Cassandra chịu trách nhiệm chuyển dữ liệu, ứng dụng theo dõi lỗi và latency.
- **Repair, cleanup, replace và rebuild** có mục đích khác bootstrap và phải dùng đúng tình huống.

Khi lên kế hoạch mở rộng Apache Cassandra, hãy kiểm tra **DC/rack, RF, token ownership, disk headroom và network I/O**, sau đó theo dõi **streaming + trạng thái node + ảnh hưởng ứng dụng** cho tới khi phân bố dữ liệu ổn định. Một node xuất hiện trong danh sách cluster mới chỉ là bước đầu; chỉ khi dữ liệu cần thiết đã được chuyển giao và mọi bước hậu bootstrap được kiểm chứng, việc mở rộng mới đạt mục tiêu.
