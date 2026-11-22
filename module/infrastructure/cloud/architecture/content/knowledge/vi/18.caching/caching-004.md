# Thiết kế khóa, phân vùng và phân bố tải bộ nhớ đệm

Cache có thể giảm độ trễ và tải lên database, nhưng hiệu quả phụ thuộc nhiều vào cách dữ liệu được định danh, đặt lên các node và phân phối yêu cầu. Nếu thiết kế khóa không nhất quán, cùng một dữ liệu có thể được lưu dưới nhiều key hoặc hai tenant vô tình dùng chung key. Nếu phân vùng kém, một node có thể quá tải trong khi các node khác còn rảnh. Nếu có một key được truy cập quá nhiều, hệ thống gặp **hot key** dù tổng dung lượng cache và số node vẫn còn đủ.

Thiết kế cache cho ứng dụng cloud vì thế cần giải quyết đồng thời ba câu hỏi:

- **Key design:** request nào ánh xạ tới cùng một mục cache, dữ liệu thuộc tenant/phạm vi nào, và làm sao quản lý version/invalidation?
- **Partitioning:** key được đặt trên node hoặc shard nào, hệ thống thêm/bớt node thì dữ liệu và request được phân bố lại ra sao?
- **Load distribution:** traffic có cân bằng giữa node và giữa key không, làm thế nào nhận diện và xử lý hot key, skew và burst?

Trong module **CLOUD_ARCHITECTURE**, những quyết định này phải gắn với latency SLO, tính nhất quán, khả năng mở rộng, bảo mật, chi phí và vận hành theo tư duy Well-Architected. Một cache cluster có nhiều node chưa chắc có throughput tốt nếu key phân bố lệch; một hash function tốt cũng không cứu được một key đơn lẻ có lượng truy cập vượt xa năng lực một shard.

## 1. Vai trò của cache key trong kiến trúc

Cache key là định danh của một mục dữ liệu được lưu hoặc tính toán lại. Với cache-aside, ứng dụng thường tạo key từ đầu vào của request, đọc cache, xử lý cache miss bằng cách truy vấn nguồn dữ liệu và lưu kết quả theo key.

~~~mermaid
flowchart LR
    CLIENT["Client request"] --> APP["Application"]
    APP --> KEY["Normalize + build cache key"]
    KEY --> CACHE["Cache cluster"]
    CACHE -->|Hit| RESULT["Return cached value"]
    CACHE -->|Miss| DB["Source database"]
    DB --> FILL["Validate + populate cache"]
    FILL --> CACHE
    FILL --> RESULT
~~~

Một key tốt cần có các thuộc tính:

1. **Deterministic:** cùng một biểu diễn logic của request tạo cùng key.
2. **Collision-safe at application level:** hai dữ liệu khác nhau không vô tình ánh xạ tới cùng key do thiếu thành phần phân biệt.
3. **Scoped:** phân biệt tenant, user, locale, permission hoặc phiên bản dữ liệu khi các yếu tố đó ảnh hưởng kết quả.
4. **Bounded:** chiều dài và cardinality được kiểm soát; tránh đưa input tùy ý làm key vô hạn.
5. **Observable:** có thể nhóm metric theo loại key/dataset mà không làm lộ dữ liệu nhạy cảm.
6. **Invalidatable:** có quy tắc để xóa hoặc làm hết hạn đúng các mục khi nguồn thay đổi.

### Cache key là một phần của contract dữ liệu

Giả sử API trả chi tiết sản phẩm theo product ID. Nếu kết quả giống nhau cho mọi người dùng, key có thể gồm loại dữ liệu, schema version và product ID. Nhưng nếu API trả giá theo vùng, ngôn ngữ hoặc nhóm khách hàng, key phải bao gồm các yếu tố ảnh hưởng kết quả. Nếu thiếu region hoặc customer tier, người dùng có thể nhận nhầm giá.

Không nên đưa mọi header/request field vào key một cách máy móc. Chỉ đưa những yếu tố thực sự làm thay đổi kết quả; các field không liên quan làm tăng cardinality và giảm hit ratio.

## 2. Xây dựng cấu trúc key có namespace

Một quy ước dễ vận hành là chia key thành các thành phần:

\[
\text{key}=\text{namespace}:\text{schemaVersion}:\text{scope}:\text{entity}:\text{variant}
\]

Ví dụ:

| Mục cache | Key minh họa | Ý nghĩa |
| --- | --- | --- |
| Chi tiết sản phẩm | product:v3:global:sku-1042 | Bản chi tiết theo schema v3 |
| Danh sách theo tenant | catalog:v2:tenant-17:category-8:page-1 | Kết quả riêng tenant |
| Hồ sơ theo locale | profile:v1:user-482:vi-VN | Hồ sơ hiển thị tiếng Việt |
| Quyền truy cập | authz:v4:tenant-17:user-482:resource-93 | Kết quả authorization theo scope |
| Tỷ giá theo ngày | fx:v1:USD-VND:2026-11-18 | Dữ liệu theo cặp tiền và ngày |

Các key trên chỉ là ví dụ; dữ liệu cá nhân hoặc bí mật không nên được đưa nguyên văn vào key vì key có thể xuất hiện trong log, metric hoặc công cụ quản trị cache. Có thể sử dụng identifier nội bộ hoặc hash ổn định nếu cần che bớt dữ liệu, đồng thời vẫn phải kiểm soát quyền truy cập cache.

### Tránh key collision do nối chuỗi tùy tiện

Nếu ghép các trường bằng dấu phân cách mà không escape hoặc length-prefix, hai bộ giá trị có thể tạo cùng chuỗi. Ví dụ (a, bc) và (ab, c) dễ bị nhập nhằng nếu nối trực tiếp. Cách an toàn:

- Chuẩn hóa kiểu dữ liệu và encoding.
- Dùng delimiter có quy tắc escaping rõ ràng hoặc serialization có cấu trúc.
- Có thể length-prefix từng thành phần trước khi hash.
- Dùng tên namespace và schema version cố định.
- Kiểm thử các giá trị chứa delimiter, Unicode, chuỗi rỗng, null và ký tự đặc biệt.

Hash key giúp có độ dài cố định nhưng không tự giải quyết collision logic; nếu hash rút gọn quá ngắn, hai đầu vào vẫn có thể trùng. Với dữ liệu quan trọng, có thể lưu key fingerprint và metadata kiểm tra hoặc dùng độ dài hash đủ lớn theo threat/performance model.

### Phân biệt cache key và partition key

Cache key định danh một entry. Partition key là thành phần/giá trị được dùng để quyết định entry thuộc shard nào. Nhiều hệ thống dùng chính cache key để hash sang partition; một số cho phép khai báo hash tag hoặc partition key riêng. Nếu dùng partition key khác key, cần chắc chắn các entry cần truy cập cùng nhau được đặt đúng nơi và hệ thống có thể định tuyến request chính xác.

Ví dụ một cache lưu dữ liệu giỏ hàng:

- Key entry: cart:{customer-42}:metadata.
- Các key liên quan: cart:{customer-42}:items, cart:{customer-42}:discount.
- Hash tag/customer ID có thể giữ các key cùng giỏ hàng trên một shard nếu nền tảng hỗ trợ.

Điều này giúp một số thao tác nhiều key được thực hiện cùng partition, nhưng cũng có thể tạo hot partition nếu một customer có traffic rất lớn hoặc hash tag chọn quá rộng.

## 3. Namespacing theo tenant, môi trường và phiên bản

Trong hệ thống multi-tenant, key cần phân biệt phạm vi dữ liệu để tránh rò rỉ chéo tenant. Tenant ID thường là một thành phần của key nếu cache chứa dữ liệu riêng theo tenant. Tuy nhiên, tenant ID không phải cơ chế authorization: vẫn phải kiểm tra quyền ở ứng dụng trước khi trả cache hit.

Các namespace hữu ích:

- **Environment:** prod, staging, dev để tránh chia sẻ cache ngoài ý muốn.
- **Application/domain:** catalog, booking, pricing, identity.
- **Schema version:** v1, v2 khi format hoặc semantics thay đổi.
- **Tenant/region/locale:** khi kết quả phụ thuộc phạm vi.
- **Data classification:** phân tách dữ liệu công khai và nhạy cảm theo policy.

### Versioning key khi thay đổi schema

Nếu cùng một key được dùng trước và sau khi đổi cấu trúc dữ liệu, instance cũ có thể deserialize payload mới hoặc ngược lại. Thêm schema version vào namespace cho phép triển khai từng bước:

1. Phiên bản ứng dụng mới ghi key v2.
2. Trong thời gian chuyển tiếp, có thể đọc v2 rồi fallback v1 nếu contract cho phép.
3. Khi toàn bộ consumer đã dùng v2, ngừng ghi/đọc v1.
4. Để TTL/lifecycle dọn key cũ hoặc xóa theo batch đã kiểm tra.

Không nên giữ logic dual-read vô thời hạn vì nó tăng độ phức tạp và làm khó xác định dữ liệu có thẩm quyền.

### Phân tách key không thay thế phân tách bảo mật

Đối với dữ liệu nhạy cảm, cân nhắc cache riêng, account/project riêng, key encryption, network boundary, IAM và TTL phù hợp. Nếu một cache instance chứa cả token xác thực và danh mục công khai, cần đánh giá liệu cùng operator, backup, debug dump và quyền admin có thể đọc toàn bộ dữ liệu hay không.

## 4. Chuẩn hóa đầu vào trước khi tạo key

Hai request tương đương về nghiệp vụ nhưng có biểu diễn khác nhau có thể tạo cache key khác nhau, làm giảm hit ratio. Trước khi tạo key nên chuẩn hóa:

- Chuẩn hóa chữ hoa/thường nếu hệ thống coi chúng tương đương.
- Chuẩn hóa Unicode cho tên hoặc chuỗi tìm kiếm nếu phù hợp.
- Chuẩn hóa ngày giờ về timezone/format đã quy định.
- Sắp xếp tập tham số không có thứ tự (ví dụ danh sách filter dạng set).
- Bỏ các query parameter không ảnh hưởng kết quả.
- Biểu diễn số, decimal và boolean nhất quán.
- Chuẩn hóa giá trị mặc định và null theo cùng contract.

Ví dụ hai URL:

- /products?category=books&sort=price
- /products?sort=price&category=books

Nếu thứ tự tham số không ảnh hưởng kết quả, hai request nên tạo cùng key. Nhưng với một danh sách có thứ tự như các bước workflow hoặc ranking rule, không được sort vì thứ tự có ý nghĩa.

### Không chuẩn hóa quá mức

Chuẩn hóa sai có thể làm hai request khác nhau dùng chung cache entry. Ví dụ:

- Gộp locale vi-VN và en-US dù response đã dịch.
- Làm tròn số tiền mà bỏ mất đơn vị/precision nghiệp vụ.
- Bỏ customer tier trong key giá theo hợp đồng.
- Bỏ permission scope trong key response có field bị ẩn theo quyền.
- Sort danh sách ID trong khi response giữ nguyên thứ tự đầu vào.

Nguyên tắc là: **chỉ coi hai input tương đương khi kết quả nghiệp vụ thực sự tương đương**.

## 5. TTL, invalidation và phiên bản dữ liệu trong key

TTL quyết định thời gian một cache entry được phép tồn tại kể từ lúc tạo hoặc cập nhật theo semantics của cache. TTL giúp giới hạn stale window khi không thể invalidate chính xác, nhưng không thay thế quy tắc consistency.

Một số chiến lược:

| Chiến lược | Mục tiêu | Lưu ý |
| --- | --- | --- |
| **TTL cố định** | Đơn giản, tự hết hạn | Nhiều key có thể hết hạn cùng lúc nếu cùng tạo theo batch |
| **TTL có jitter** | Phân tán thời điểm expire | Cần xác định min/max và tránh vượt stale tolerance |
| **Explicit invalidation** | Xóa key khi nguồn thay đổi | Race condition giữa read cũ và cache fill |
| **Versioned key** | Dữ liệu mới dùng namespace/version mới | Key cũ tồn tại đến khi TTL/lifecycle dọn |
| **Write-through/update** | Cập nhật cache cùng luồng write theo policy | Phức tạp khi nhiều cache consumer hoặc update thất bại |

### Version trong key

Với một catalog, metadata database có thể giữ version của sản phẩm. Key có thể gồm product ID và version hiện tại. Khi sản phẩm đổi, version tăng, nên các request tiếp theo tạo key mới; key cũ không còn được tham chiếu và tự hết hạn. Cách này giảm race giữa invalidate và cache fill, nhưng cần nguồn lấy version đáng tin cậy và kiểm soát số version.

Một cách khác là sử dụng namespace generation chung cho cả tập dữ liệu; tăng generation khi cần invalidate nhóm key. Không nên dùng một version toàn cục cho mọi dữ liệu nếu cập nhật nhỏ khiến toàn cache miss cùng lúc.

### TTL jitter và chống expiry storm

Nếu một batch ghi hàng triệu key cùng TTL 10 phút, chúng có thể hết hạn gần như cùng lúc và dồn request xuống database. Thêm jitter ngẫu nhiên trong giới hạn cho phép giúp phân tán expiration. Ví dụ TTL gốc 600 giây có thể cộng/trừ một khoảng nhỏ dựa trên stale tolerance. Jitter không nên làm dữ liệu nhạy cảm sống lâu hơn thời hạn nghiệp vụ cho phép.

## 6. Phân vùng cache: vì sao cần sharding?

Khi một cache node không đủ bộ nhớ, throughput hoặc connection capacity, hệ thống có thể chia dữ liệu qua nhiều node (**partitioning/sharding**). Mỗi shard chịu trách nhiệm một phần keyspace; client hoặc proxy định tuyến yêu cầu tới shard sở hữu key.

~~~mermaid
flowchart TB
    APP["Application / cache client"]
    ROUTER["Key routing"]
    S1["Shard A"]
    S2["Shard B"]
    S3["Shard C"]
    APP --> ROUTER
    ROUTER -->|Keys in range/hash A| S1
    ROUTER -->|Keys in range/hash B| S2
    ROUTER -->|Keys in range/hash C| S3
~~~

Sharding giúp:

- Tăng tổng dung lượng bằng cách cộng bộ nhớ của nhiều node.
- Tăng throughput khi các key phân bố và request độc lập.
- Cô lập một phần tải và lỗi theo shard.
- Mở rộng theo chiều ngang khi một node không còn đủ.

Nhưng sharding cũng làm tăng độ phức tạp:

- Client cần biết key nằm ở đâu hoặc dùng proxy/router.
- Thêm/bớt shard có thể làm thay đổi mapping và phải di chuyển dữ liệu.
- Multi-key operation có thể không thực hiện được nếu key nằm ở shard khác.
- Một shard nóng có thể quá tải dù tổng cluster còn capacity.
- Failover, backup, monitoring và resharding cần vận hành.

### Các chiến lược phân vùng

| Chiến lược | Cách phân bổ | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| **Range-based** | Phân key theo dải giá trị | Dễ truy vấn theo range và locality | Có thể skew nếu một dải hoạt động nhiều |
| **Hash-based** | Hash key rồi chọn shard | Phân bố đều hơn với hash tốt | Range query khó; đổi số shard có thể remap nhiều |
| **Directory-based** | Bảng tra cứu key/tenant tới shard | Kiểm soát placement linh hoạt | Directory cần HA, cache và consistency |
| **Tenant-based** | Mỗi tenant hoặc nhóm tenant gắn shard | Cô lập tenant lớn và dễ quota | Tenant lớn gây hot shard; tenant mới cần placement |
| **Composite** | Kết hợp tenant, hash hoặc range | Có thể cân bằng isolation và distribution | Phức tạp khi định tuyến và di chuyển |

Không có chiến lược phân vùng tốt nhất. Chọn theo query pattern, key cardinality, tenant distribution, số lượng key, truy vấn nhiều key và tốc độ tăng trưởng.

## 7. Hash-based partitioning

Một cách đơn giản là hash cache key rồi lấy phần dư theo số shard:

\[
\text{shard}(key)=H(key)\bmod N
\]

Trong đó H là hàm hash và N là số shard. Nếu hash phân bố đều và key có phân bố hợp lý, số key có thể được chia tương đối đều.

### Hạn chế của modulo khi thêm node

Giả sử ban đầu có 4 shard. Khi tăng lên 5 shard, phần dư theo N thay đổi cho hầu hết key; nhiều key phải chuyển node dù dữ liệu chưa thay đổi. Điều này có thể gây:

- Cache miss hàng loạt và tăng tải lên database.
- Chi phí copy/rehydrate dữ liệu.
- Tăng network traffic và latency trong giai đoạn chuyển tiếp.
- Nhiều client dùng mapping khác nhau nếu rollout không đồng bộ.

Modulo hashing phù hợp với một số cluster nhỏ hoặc hệ thống chấp nhận flush cache khi topology thay đổi. Nếu cần giảm lượng key bị remap, hãy xem consistent hashing hoặc thuật toán placement khác.

### Hash function và phân bố

Hash function cần phân bố tốt cho bộ key thực tế, nhanh và ổn định giữa các client/runtime. Tránh dùng hash mặc định của ngôn ngữ nếu giá trị hash có thể thay đổi giữa process, phiên bản runtime hoặc không được thiết kế cho distributed routing. Tất cả client phải có cùng thuật toán, seed, encoding và mapping version.

Không dùng hash không có kiểm soát trên dữ liệu input do người dùng cung cấp nếu kẻ tấn công có thể tạo nhiều key collision có chủ đích; lựa chọn hash và giới hạn key phải xét threat model.

## 8. Consistent hashing và virtual nodes

Consistent hashing đặt node và key lên một vòng hash. Mỗi key được gán cho node kế tiếp theo chiều vòng. Khi thêm/bớt node, chỉ một phần keyspace quanh vị trí node thay đổi owner, thay vì toàn bộ mapping như modulo hashing đơn giản.

~~~mermaid
flowchart LR
    subgraph RING["Hash ring (minh họa tuyến tính)"]
      direction LR
      P0["0"] --> A["Node A"]
      A --> P1["Token 25"]
      P1 --> B["Node B"]
      B --> P2["Token 50"]
      P2 --> C["Node C"]
      C --> P3["Token 75"]
      P3 --> D["Node D"]
      D --> P4["100 / vòng"]
    end
~~~

Hình minh họa vị trí trên ring; trong triển khai thực, hash space thường là vòng số và node có một hoặc nhiều token. Một key được gán theo quy tắc successor đã định nghĩa.

### Thêm node mới

Khi thêm Node E ở một vị trí trên vòng, E chỉ nhận một phần đoạn keyspace trước đó thuộc node successor. Các node còn lại tiếp tục sở hữu phần lớn key cũ. Vì vậy lượng dữ liệu cần di chuyển thường nhỏ hơn đáng kể so với remap toàn bộ.

### Virtual nodes (vnodes)

Nếu mỗi physical node chỉ có một token, phân bố key có thể lệch do vị trí token. Virtual nodes cho mỗi physical node nhiều token trên ring, giúp phân chia keyspace thành nhiều đoạn nhỏ:

- Giảm ảnh hưởng của một vị trí token xấu.
- Cải thiện cân bằng dung lượng và request khi số key lớn.
- Có thể hỗ trợ điều chỉnh trọng số bằng cách cấp nhiều vnode hơn cho node mạnh.
- Cho phép node tham gia/loại khỏi ring theo nhiều phần nhỏ hơn.

Vnodes không tự bảo đảm cân bằng request. Hash key có thể đều nhưng một số key nóng vẫn chi phối tải; node có nhiều vnode cũng có thể nhận workload không tương xứng. Cần đo cả dung lượng, operations/second, CPU, network và latency.

### Consistent hashing không miễn phí

- Cần lưu/đồng bộ ring membership và topology version.
- Node join/leave có giai đoạn chuyển tiếp, nơi key có thể chưa được copy.
- Cache miss có thể tăng trên vùng key chuyển owner.
- Client cũ và mới phải dùng routing map tương thích.
- Failover cần phân biệt node tạm mất kết nối với node bị loại khỏi ring để tránh churn.

Một số cache service quản lý sharding phía server; client chỉ dùng endpoint cluster. Những dịch vụ khác yêu cầu client library hoặc proxy hỗ trợ hash slot/partition. Phải hiểu vị trí thực hiện routing và cách cập nhật topology.

## 9. Hash slot và partition topology do dịch vụ quản lý

Một số cache cluster không dùng ring trực tiếp trong client mà chia keyspace thành **hash slot**. Ví dụ, một cluster có số slot cố định; key được hash để chọn slot, rồi slot được gán cho node. Khi mở rộng, hệ thống chuyển một số slot giữa node.

Ưu điểm của slot:

- Số đơn vị phân vùng cố định giúp quản lý placement.
- Có thể chuyển một nhóm slot mà không cần thay đổi hash function.
- Cluster client có thể nhận topology map để định tuyến.
- Có thể kiểm soát multi-key operation khi các key thuộc cùng slot, tùy dịch vụ.

Nhược điểm:

- Thay đổi topology cần phối hợp client và server.
- Chuyển slot có thể gây latency/cross-node redirect hoặc cache miss.
- Một slot nóng vẫn có thể tạo hotspot trên node sở hữu.
- Multi-key transaction thường yêu cầu các key cùng slot hoặc cùng partition.

Một số hệ thống hỗ trợ hash tag: phần nằm trong dấu ngoặc theo quy tắc dịch vụ được dùng làm cơ sở hash, giúp các key có cùng tag nằm cùng slot. Điều đó thuận tiện cho thao tác nhiều key thuộc cùng một giỏ hàng, nhưng nếu chọn tenant lớn làm tag cho tất cả dữ liệu sẽ tạo hot slot.

Đừng tự giả định syntax hash tag dùng chung giữa các sản phẩm. Hãy kiểm tra thuật toán chính xác, quy tắc escape và cách xử lý key không có tag.

## 10. Phân bố tải và đo độ cân bằng

Phân bố số key không đồng nghĩa phân bố tải. Một shard có thể chứa 20% số key nhưng nhận 70% request vì các key có tần suất truy cập khác nhau. Do đó cần quan sát ít nhất ba chiều:

1. **Data distribution:** số key, dung lượng bytes, số item theo shard.
2. **Request distribution:** hits, misses, reads, writes, deletes và operations/second theo shard/key class.
3. **Resource distribution:** CPU, memory, network, connection count, eviction và latency theo node.

### Chỉ số quan trọng

| Metric | Dùng để phát hiện |
| --- | --- |
| Keys/bytes per shard | Lệch dung lượng |
| Ops/sec per shard | Lệch request/throughput |
| p95/p99 latency per shard | Một shard chậm hơn phần còn lại |
| CPU và network per node | Node quá tải tính toán hoặc truyền tải |
| Memory fragmentation/used memory | Sức chứa thực và khả năng cấp phát |
| Evictions per shard | Thiếu memory hoặc TTL/eviction policy không phù hợp |
| Hit ratio theo namespace | Key design hoặc TTL không hiệu quả |
| Connection count/queue depth | Client fan-in hoặc điểm nghẽn giao tiếp |

### Độ lệch (skew)

Skew xảy ra khi một nhóm key, tenant hoặc partition chiếm phần lớn dữ liệu/tải. Có thể phát sinh từ:

- Tenant lớn vượt xa median.
- Key theo ngày/giờ hiện tại nhận nhiều request hơn các key lịch sử.
- Một sản phẩm nổi bật được truy cập nhiều lần.
- Một prefix/range tăng nhanh theo thời gian.
- Partition key thiếu thành phần phân tán khiến mọi ghi rơi vào một shard.

Không chỉ đo trung bình. Hãy theo dõi p95/p99 giữa các shard, max/median và phân bố tải theo tenant/key class.

## 11. Hot key và hot partition

**Hot key** là một key nhận lượng truy cập hoặc ghi vượt xa các key còn lại. Vì key thường được định tuyến tới một shard, mọi request cho key đó có thể dồn vào cùng một node. Thêm node vào cluster không tự phân tán một key đơn lẻ nếu thuật toán vẫn ánh xạ key đó tới một partition.

Ví dụ một trang sản phẩm nổi bật nhận 40.000 request/giây, trong khi các sản phẩm còn lại nhận tổng 20.000 request/giây. Hash function vẫn có thể phân bố đều hàng triệu key, nhưng node chứa key nổi bật phải chịu phần lớn tải.

### Dấu hiệu nhận biết

- Một key/namespace/tenant có request rate cao bất thường.
- Một shard CPU/network/latency cao trong khi các shard khác bình thường.
- Hit ratio toàn cluster tốt nhưng p99 của một số request vẫn tăng.
- Connection/queue tại node nóng cao; eviction hoặc timeout tập trung.
- Tỉ lệ request lặp tới một resource như product detail, configuration hoặc global counter tăng đột biến.

### Cách xử lý

| Biện pháp | Cách làm | Đánh đổi |
| --- | --- | --- |
| **Local/in-process cache** | Giữ bản sao read-only gần application instance cho key công khai, cập nhật không quá nhạy | Có nhiều bản sao và invalidation phức tạp hơn |
| **Replicate hot key** | Tạo nhiều bản read replica/copy và phân phối client đọc | Ghi và invalidation cần fan-out; đọc phải chọn bản đủ mới |
| **Key salting** | Thêm suffix/bucket để chia một nhóm request qua nhiều key | Không phù hợp nếu cần cập nhật/đọc một giá trị duy nhất; phải merge hoặc fan-in |
| **Request coalescing** | Nhiều cache miss cùng key gộp thành một lần gọi nguồn | Một request chậm có thể làm nhiều caller cùng chờ; cần timeout |
| **Rate limiting** | Giới hạn request theo key/tenant/user | Có thể làm giảm trải nghiệm nếu threshold sai |
| **TTL/stale serving** | Trả bản cũ trong khoảng cho phép, refresh nền | Chỉ phù hợp dữ liệu chấp nhận stale |
| **Pre-warming** | Nạp trước key phổ biến trước chiến dịch | Cần dự báo và bảo trì danh sách key nóng |

### Local cache cho dữ liệu đọc nhiều

Một cấu trúc nhiều tầng:

~~~mermaid
flowchart LR
    APP["Application instance"]
    L1["L1 local cache"]
    L2["L2 distributed cache"]
    DB["Source database"]
    APP --> L1
    L1 -->|Miss| L2
    L2 -->|Miss| DB
    DB --> L2
    L2 --> L1
~~~

Local cache giảm network hop và giảm tải distributed cache cho key nóng. Nhưng cần TTL ngắn, invalidation/pub-sub hoặc version check; nếu không, từng app instance có thể trả phiên bản khác nhau. Với dữ liệu nhạy cảm hoặc authorization, phải đánh giá stale permission và không chia sẻ L1 giữa tenant/request context không an toàn.

### Replicate hot key để đọc

Một key read-only có thể được nhân thành nhiều physical key (ví dụ một số replica/copy) rồi request chọn một trong số đó. Khi cập nhật, hệ thống ghi đồng bộ hoặc bất đồng bộ tới các copy. Cần định nghĩa:

- Khi nào write được xem là hoàn thành?
- Có thể trả một copy cũ trong bao lâu?
- Làm sao đảm bảo copy mới đã nhận version?
- Khi một copy mất kết nối, router chọn copy nào?
- Có thể bỏ qua copy stale và đọc primary không?

Không nên replicate một counter cần increment chính xác rồi cộng dồn tùy ý nếu chưa định nghĩa semantics; có thể mất update hoặc đếm trùng.

### Key salting và giới hạn của nó

Salting có thể chia một counter số lượt xem thành nhiều bucket:

\[
\text{key}_i=\text{views}:\text{product-42}:\text{bucket-}i
\]

Mỗi writer chọn một bucket, và khi đọc hệ thống tổng hợp các bucket. Điều này giảm điểm ghi nóng nhưng tăng chi phí fan-out khi đọc và cần xử lý retry idempotently để không cộng một event nhiều lần. Không dùng salting tùy tiện cho state cần một giá trị duy nhất như available inventory hoặc permission state.

## 12. Request coalescing, stampede và thundering herd

Cache stampede xảy ra khi một key hết hạn hoặc bị evict, nhiều request đồng thời cùng cache miss và cùng gọi nguồn. Nếu key phổ biến, database nhận burst lớn dù bình thường cache hit ratio rất cao.

### Các cơ chế giảm stampede

- **Single-flight/request coalescing:** chỉ một worker fetch dữ liệu cho key; các request khác chờ cùng kết quả.
- **Refresh-ahead:** refresh cache trước thời điểm hết hạn dự kiến.
- **Stale-while-revalidate:** tiếp tục trả dữ liệu cũ trong khoảng cho phép, một worker refresh nền.
- **TTL jitter:** phân tán thời điểm hết hạn giữa các key.
- **Negative caching:** cache kết quả không tồn tại trong thời gian ngắn để ngăn request lặp tới nguồn.
- **Rate limit/cache miss admission:** giới hạn số lượt fetch đồng thời khi nguồn đang quá tải.

### Negative caching cần cẩn trọng

Nếu một ID không tồn tại, cache kết quả not-found có thể giảm tải khi bot hoặc client liên tục hỏi cùng ID. Nhưng nếu resource vừa được tạo, kết quả not-found cũ có thể che dữ liệu mới. TTL nên ngắn, invalidation sau create rõ ràng và không cache lỗi 5xx như thể resource không tồn tại.

### Stale-while-revalidate

Một entry có thể có hai mốc: fresh-until và stale-until. Trước fresh-until, trả bình thường; giữa hai mốc, có thể trả stale và khởi chạy refresh; sau stale-until, phải lấy dữ liệu mới hoặc trả lỗi/fallback theo policy. Cần có giới hạn số refresh đồng thời cho key và timeout để tránh worker refresh tạo tải vô hạn.

### Thundering herd khi failover

Nếu một cache shard bị failover hoặc toàn bộ node mất dữ liệu warm cache, hàng triệu key có thể cùng miss. Biện pháp:

- Ramp-up traffic theo tỷ lệ, không chuyển toàn bộ workload ngay.
- Warm key phổ biến có giới hạn tốc độ.
- Thêm jitter TTL và giới hạn miss concurrency.
- Dùng circuit breaker/admission control để bảo vệ database.
- Có thể phục vụ stale data với nhóm dữ liệu được phép.
- Theo dõi database connections, CPU, IOPS và queue trong quá trình warm-up.

## 13. Load distribution ở lớp client và proxy

Cache cluster cần phân bố request giữa node. Cách định tuyến ảnh hưởng đến latency, connection count, topology churn và failure handling.

| Cách định tuyến | Cơ chế | Lợi ích | Rủi ro |
| --- | --- | --- | --- |
| **Client-side sharding** | Client library tính key → shard | Ít hop, có thể định tuyến trực tiếp | Mọi client phải cập nhật topology và thuật toán đồng nhất |
| **Proxy-based routing** | Client gửi tới proxy; proxy định tuyến tới shard | Che topology, tập trung policy và telemetry | Proxy có thể thành bottleneck hoặc failure domain |
| **Managed cluster endpoint** | Dịch vụ cung cấp endpoint và client protocol quản lý routing | Giảm tự quản trị topology | Phụ thuộc semantics/SDK của provider |
| **Consistent-hash load balancer** | Chọn backend theo key/affinity | Giữ locality cho key hoặc session | Key nóng vẫn dồn vào một backend nếu không replicate |

### Kết nối và pooling

Khi có nhiều application instance và nhiều cache node, số connection có thể tăng theo tích số. Nếu 100 application replicas mỗi replica mở 20 connection tới 12 cache nodes, cần hiểu thư viện phân bổ connection thực tế; không mặc định mỗi app mở đúng 20 connection tổng cho toàn cluster. Quản lý pool, timeout, keepalive, max connections và reconnect backoff để tránh connection storm khi node thay đổi.

### Topology refresh

Client-side routing cần cập nhật khi cluster thêm/bớt node, chuyển slot hoặc failover. Cần:

- Cơ chế khám phá topology và thời gian refresh phù hợp.
- Hành vi khi nhận redirect/cluster map mới.
- Xử lý request đang chạy khi shard chuyển owner.
- Retry chỉ khi thao tác an toàn và còn deadline.
- Hạn chế mọi instance refresh cùng lúc gây tải lên control endpoint.
- Version topology để phát hiện client dùng map cũ.

## 14. Rebalancing và thêm/bớt shard

Rebalancing là quá trình thay đổi cách phân phối key/data giữa các shard để đáp ứng dung lượng, hiệu năng hoặc thay đổi topology.

### Vì sao rebalance rủi ro?

- Di chuyển dữ liệu tiêu thụ network và CPU, cạnh tranh với request người dùng.
- Trong thời gian chuyển, client có thể đọc từ node cũ hoặc mới.
- Key đang được ghi có thể cần dual-write, forwarding hoặc khóa tạm theo cơ chế dịch vụ.
- Client cũ có thể định tuyến tới owner cũ.
- Cache miss tăng làm nguồn dữ liệu chịu tải thêm.
- Rollback topology không đơn giản nếu data movement đã hoàn tất một phần.

### Quy trình mở rộng có kiểm soát

1. **Đo baseline:** bytes/key count, ops/sec, p99, CPU, memory, network và eviction từng shard.
2. **Dự báo:** xác định node nào thiếu dung lượng/throughput; không chỉ nhìn tổng cluster.
3. **Chọn thuật toán:** consistent hashing, slot migration, range split, tenant move hoặc managed reshard.
4. **Chuẩn bị capacity:** node mới, connection quota, replication và network path.
5. **Canary:** chuyển một phần nhỏ keyspace hoặc một nhóm tenant.
6. **Giám sát:** data integrity, hit ratio, latency, error/redirect, source database load.
7. **Mở rộng dần:** tăng tỷ lệ chuyển sau khi các chỉ số ổn định.
8. **Hoàn tất và cleanup:** loại ownership cũ, cập nhật topology, thu hồi tài nguyên không còn dùng.

~~~mermaid
flowchart TD
    BASE["Baseline + capacity forecast"] --> PREP["Provision shard mới"]
    PREP --> CANARY["Move một phần keyspace"]
    CANARY --> OBS["Đo hit/miss, latency, integrity"]
    OBS --> OK{"Ổn định?"}
    OK -->|Không| PAUSE["Pause / rollback theo plan"]
    OK -->|Có| EXPAND["Mở rộng migration"]
    EXPAND --> VERIFY["Verify ownership + data"]
    VERIFY --> CLEAN["Cập nhật topology và cleanup"]
~~~

Với cache thuần túy và dữ liệu có thể tái tạo, có thể chấp nhận flush hoặc lazy rewarming thay vì copy toàn bộ. Nhưng nếu cache chứa session, coordination state hoặc dữ liệu không thể tái tạo nhanh, không được đối xử như cache disposable; cần đánh giá storage/database phù hợp hơn.

## 15. Replication, failover và phân phối tải khi node lỗi

Sharding chia keyspace; replication tạo nhiều bản sao của shard hoặc key. Hai cơ chế giải quyết các mục tiêu khác nhau:

- Sharding chủ yếu tăng dung lượng và tổng throughput bằng cách phân phối dữ liệu.
- Replication chủ yếu tăng khả năng đọc, dự phòng và khả năng phục hồi theo semantics của hệ thống.

Một cluster có 6 shard và mỗi shard có 1 replica có thể có 12 node, nhưng không có nghĩa capacity ghi tăng gấp đôi. Ghi thường vẫn đi qua primary/owner của shard; replica nhận bản sao theo cơ chế đồng bộ hoặc bất đồng bộ.

### Primary-replica

Với mô hình primary-replica, write gửi tới primary, read có thể gửi tới primary hoặc replica. Khi failover, một replica có thể được promote. Cần xác định:

- Replication lag và read consistency.
- Điều kiện promote và cơ chế fencing primary cũ.
- Khả năng mất các write chưa sao chép.
- Client topology refresh và redirect.
- Read từ replica có thể trả stale tới mức nào.

Đối với cache dữ liệu có thể tái tạo, stale read đôi khi chấp nhận được. Với cache chứa state quan trọng hoặc dùng để quyết định quyền, phải cân nhắc nguồn mạnh hơn và contract cụ thể.

### Failover tạo hot shard mới

Khi một node mất, một node khác có thể nhận thêm traffic từ shard failover. Nếu node dự phòng vốn đang gần đầy, failover có thể tạo một đợt quá tải thứ hai. Capacity plan phải giả định ít nhất một failure domain mất và phân phối tải còn lại.

### Split brain và stale topology

Trong một số sự cố mạng, client có thể nghĩ primary cũ vẫn còn hoạt động trong khi cluster đã promote primary mới. Nếu hệ thống không có fencing/epoch/term hoặc cơ chế chống dual-primary phù hợp, ghi có thể phân nhánh. Không tự xây failover chỉ bằng cách đổi DNS tới một node khác nếu dịch vụ cache có cluster protocol riêng.

## 16. Multi-key operation và locality

Nhiều thao tác cache cần đọc/ghi nhiều key:

- Lấy metadata và items của một giỏ hàng.
- Cập nhật session cùng index phụ.
- Kiểm tra rate limit nhiều dimension.
- Lưu dữ liệu người dùng và danh sách truy cập gần đây.

Nếu các key nằm ở nhiều shard, thao tác atomic hoặc transaction có thể không hỗ trợ, hoặc cần fan-out qua nhiều node. Điều này có thể tăng latency và tạo partial failure.

### Colocation theo aggregate

Một chiến lược là đặt các key cần thao tác cùng nhau vào một partition bằng aggregate ID hoặc hash tag. Ví dụ các key cart của customer 42 cùng nằm trên shard theo cart ID. Nó giảm cross-shard operation nhưng cần kiểm tra phân bố tenant và nguy cơ hot aggregate.

### Không colocate quá rộng

Nếu dùng tenant ID làm partition key cho mọi dữ liệu của tenant, tenant lớn có thể khiến một shard nóng. Có thể kết hợp tenant với subpartition (ví dụ tenant + category hoặc tenant + hash bucket) nhưng khi thao tác cần truy vấn nhiều subpartition, ứng dụng phải fan-out và tổng hợp.

### Thiết kế theo query pattern

Trước khi chọn partition key, lập danh sách thao tác:

| Operation | Key cần đọc/ghi | Có cần atomic? | Ảnh hưởng placement |
| --- | --- | --- | --- |
| Lấy cart | metadata + items | Có thể cần snapshot nhất quán | Có thể colocate theo cart ID |
| Đọc product detail | Một key | Không thường xuyên ghi | Có thể replicate hot key |
| Kiểm tra tồn kho | Một aggregate inventory | Cần atomic/strong source | Không salting tùy tiện |
| Đếm page views | Nhiều bucket counter | Có thể eventual | Shard counter rồi aggregate |
| Xóa dữ liệu tenant | Nhiều key/prefix | Cần hoàn tất theo lô | Directory/namespace theo tenant giúp quản lý |

Không thiết kế partition key chỉ theo cấu trúc dữ liệu. Hãy bắt đầu từ access pattern và consistency requirement.

## 17. Bảo mật và bảo vệ tenant trong cache

Cache thường được xem là lớp hiệu năng nên có thể bị bỏ qua trong review bảo mật. Nhưng cache có thể chứa PII, session token, quyền truy cập, giá theo hợp đồng hoặc dữ liệu riêng tenant.

### Key scoping và authorization

- Đưa tenant/scope vào key khi output phụ thuộc tenant.
- Kiểm tra authorization trước khi trả cache hit; không coi key namespace là quyền truy cập.
- Không dùng raw access token hoặc dữ liệu nhạy cảm làm key.
- Dùng namespace tách prod/staging và môi trường khách hàng.
- Cân nhắc instance/cache database riêng cho tenant có yêu cầu cách ly cao.
- Đặt TTL ngắn hoặc invalidation rõ cho quyền truy cập và dữ liệu nhạy cảm.

### Cache poisoning

Nếu input chưa validate được dùng để tạo key hoặc nội dung cache, attacker có thể ghi dữ liệu không hợp lệ làm ảnh hưởng người dùng khác. Cần validate input, bind cache entry với scope/version, bảo vệ write path và không cho client tự chọn cache key tùy ý.

### Resource exhaustion

Attacker có thể tạo nhiều key ngẫu nhiên để làm tăng cardinality, memory usage và eviction. Biện pháp:

- Giới hạn chiều dài key và số key theo tenant.
- Rate limit miss và write.
- Giới hạn kích thước value.
- Quota namespace/tenant.
- Theo dõi key creation rate và eviction.
- Không cache mọi query parameter tùy ý.

### Encryption và network

Dùng TLS khi truyền qua network không tin cậy, private network/security group, authentication/ACL cho cache service và secret rotation. Nếu cache chứa dữ liệu nhạy cảm, đánh giá encryption at rest, quyền admin, snapshot/backup và debug tooling. Không để cache endpoint mở public chỉ vì dữ liệu có TTL ngắn.

## 18. Chi phí và sizing cache cluster

Cache sizing cần xét cả dung lượng dữ liệu và overhead:

- Value payload và key bytes.
- Object/header/allocator overhead.
- Replication copies.
- Fragmentation và reserved memory.
- Eviction headroom.
- Connection buffer và replication backlog.
- Hot key replication/local cache nếu dùng.

### Ước lượng dung lượng sơ bộ

Giả sử có 4 triệu entries, trung bình value 1,5 KiB, key 100 byte và overhead 30%:

\[
\text{Raw estimate}
=4.000.000\times(1.536+100)\times1{,}30
\]

\[
\approx8{,}51\times10^9\text{ bytes}\approx7{,}93\text{ GiB}.
\]

Đây là ước lượng sơ bộ, chưa bao gồm fragmentation thực tế, replication, connection buffers, metadata riêng của engine và headroom. Nếu có một replica đầy đủ cho mỗi shard, dung lượng vật lý tổng có thể tăng tương ứng. Nên đo memory usage thực với key/value representative thay vì dựa vào payload thuần.

### Hit ratio và chi phí nguồn

Hit ratio cao có thể giảm query database, nhưng không phải mục tiêu duy nhất:

- Hit ratio tăng do TTL quá dài có thể làm stale data vượt yêu cầu.
- Hit ratio thấp ở key high-cardinality có thể không phải lỗi.
- Key nóng cần local cache có thể giảm chi phí network và node nhưng tăng memory ở app.
- Cache quá lớn có thể tốn nhiều hơn so với database query tối ưu.

Theo dõi chi phí theo **cache hit/miss, bytes stored, ops, network, node-hours, replication và nguồn database giảm tải được bao nhiêu**.

### Eviction policy

Khi hết memory, cache có thể evict entry theo policy như LRU, LFU, TTL-based hoặc no-eviction tùy hệ thống. Policy ảnh hưởng trực tiếp hit ratio và workload:

- LRU phù hợp khi truy cập gần đây là chỉ báo tốt cho tương lai.
- LFU có ích khi một nhóm key được truy cập thường xuyên trong thời gian dài.
- TTL expiration phù hợp dữ liệu có thời hạn nghiệp vụ.
- No-eviction có thể làm write fail khi đầy; phù hợp khi cần kiểm soát chặt, nhưng ứng dụng phải xử lý.

Không chọn eviction policy chỉ theo tên. Đo access pattern, memory pressure, churn và tail latency.

## 19. Vận hành: metrics, logs và runbook

### Dashboard tối thiểu

| Nhóm | Metric |
| --- | --- |
| Hit/miss | Hit ratio, miss rate theo namespace, negative cache hit |
| Capacity | Memory used/free, fragmentation, keys, bytes, evictions |
| Throughput | Ops/sec, reads/writes, bandwidth, commands latency |
| Distribution | Per-shard CPU/memory/ops/p99, max-to-median ratio |
| Hot key | Top key class/hashed key fingerprint, request rate |
| Connection | Active clients, connection errors, reconnect storm |
| Topology | Slot ownership, ring version, shard health, migration progress |
| Replication | Lag, link status, failover/promote events |
| Source pressure | Database QPS, connection pool, queue, fallback rate |
| Cost | Node-hours, storage bytes, network transfer, backup/replication |

Không ghi full cache key có PII hoặc token vào metric label. Dùng key fingerprint hoặc namespace/tenant tier đã được kiểm soát; truy vấn chi tiết qua log/trace có quyền phù hợp.

### Runbook tình huống

**Một shard nóng:** xác định namespace/key class, đo ops và resource, kiểm tra tenant/hot key, áp rate limit hoặc local/replicated read cache nếu dữ liệu cho phép; không rebalance mù khi vấn đề là một key.

**Eviction tăng:** xem memory, value size, TTL, cardinality và leak. Phân biệt cache đang đầy do tăng traffic hay do key không bao giờ hết hạn; điều chỉnh capacity hoặc lifecycle theo policy.

**Cache miss storm:** giới hạn concurrency tới database, bật coalescing/stale serving cho dataset phù hợp, warm key theo đợt và theo dõi connection/IOPS downstream.

**Node failover:** xác minh topology mới, client refresh, primary/replica role và replication lag; giảm traffic ramp nếu database nguồn đang chịu tải rehydrate.

**Resharding kéo dài:** pause khi p99 hoặc error rate vượt ngưỡng, kiểm tra network/CPU và tỷ lệ chuyển, tránh thay topology đồng thời với upgrade client.

**Một tenant gây skew:** kiểm tra quota, hot key và access pattern; cân nhắc tách tenant lớn sang shard riêng hoặc subpartition nếu thao tác hỗ trợ.

## 20. Quy trình thiết kế cache key và partition

Một quy trình thực tế có thể tiến hành theo tám bước:

### Bước 1 — Phân loại dữ liệu

Ghi rõ dữ liệu công khai, theo tenant, theo user, dữ liệu nhạy cảm, cache có thể tái tạo và state không thể mất. Nêu nguồn dữ liệu authoritative, owner và thời hạn stale chấp nhận được.

### Bước 2 — Lập access pattern

Với mỗi loại dữ liệu, đo hoặc ước lượng read/write ratio, key cardinality, value size, request rate, multi-key operation, range query và fan-out. Tách traffic bình thường khỏi chiến dịch/burst.

### Bước 3 — Định nghĩa key contract

Chọn namespace, scope, schema version, identifier, các biến thể ảnh hưởng response và canonicalization. Xác định key max length, encoding, hash và quy tắc tránh collision.

### Bước 4 — Chọn partition key

Đánh giá hash distribution, tenant skew, hot key, locality cho multi-key operation và khả năng query. Mô phỏng phân bố trên dữ liệu thật hoặc synthetic representative; tránh dùng một trường có giá trị tập trung như region hoặc tenant lớn làm partition duy nhất.

### Bước 5 — Chọn thuật toán routing

Modulo, consistent hashing, hash slot, range hoặc directory-based. Xác định ai giữ topology map, cách client refresh, cách node join/leave và mức độ remap chấp nhận được.

### Bước 6 — Định nghĩa load strategy

Thiết kế local L1 cache, hot key replication, request coalescing, TTL jitter, stale-while-revalidate, rate limit và admission control theo từng nhóm dữ liệu. Chỉ bật biện pháp stale serving khi nghiệp vụ chấp nhận.

### Bước 7 — Lập kế hoạch capacity/failure

Sizing memory, CPU, network, connection, replication và headroom khi mất node/AZ. Ước lượng cache warm-up, database fallback và chi phí resharding. Xác định quota và ngưỡng auto scale/alert.

### Bước 8 — Kiểm thử và vận hành

Test skew, hot key, miss storm, failover, topology refresh, resharding, multi-tenant isolation và invalidation race. Dùng dashboard theo shard/key class, có runbook và owner.

~~~mermaid
flowchart TD
    DATA["Phân loại dữ liệu + nguồn authoritative"] --> ACCESS["Access pattern + tải"]
    ACCESS --> KEY["Key contract + namespace"]
    KEY --> PART["Partition key + routing"]
    PART --> LOAD["Hot key / coalescing / TTL"]
    LOAD --> CAP["Sizing + failure capacity"]
    CAP --> TEST["Test skew / failover / rebalance"]
    TEST --> OPS["Dashboard + runbook"]
    OPS --> ACCESS
~~~

## 21. Case study: catalog cache cho nền tảng đặt chỗ

Một nền tảng đặt chỗ có API catalog với yêu cầu giả định:

- 8 triệu sản phẩm/dịch vụ.
- 70% request đọc chi tiết sản phẩm; 20% đọc danh sách theo category; 10% đọc giá theo region/customer tier.
- Một số sản phẩm nổi bật có thể nhận 15.000 request/giây.
- Giá hợp đồng thay đổi theo tenant và nhóm khách hàng.
- Product detail có thể stale tối đa 30 giây; giá cần stale window ngắn hơn và được kiểm tra lại khi booking.
- Cache cluster bắt đầu với 6 shard, có khả năng mở rộng.

### Bước 1 — Key design

Một thiết kế mẫu:

| Dataset | Key format | Thành phần quan trọng |
| --- | --- | --- |
| Product detail | product:v3:{productId} | Product ID, schema version |
| Category page | category:v2:{region}:{categoryId}:{page}:{filterHash} | Region, category, page, filter canonicalized |
| Contract price | price:v5:{tenantId}:{customerTier}:{productId}:{currency} | Tenant, tier, product, currency |
| Availability display | availability:v2:{slotId}:{date} | Slot/date; chỉ phục vụ hiển thị |

Availability hiển thị có thể stale theo policy, nhưng khi booking phải dùng nguồn ghi authoritative kiểm tra lại chỗ trống. Giá theo hợp đồng phải có tenant/tier/currency trong key để tránh trả sai giá giữa tenant.

### Bước 2 — Partitioning

Product detail có thể hash theo key để phân bố đều. Category page cũng có thể hash theo full key; nhưng một category lớn có thể có page đầu rất nóng. Nếu cần cache category page riêng, cần đo hot key và có thể replicate read-only. Contract price có cardinality lớn hơn và cần quota theo tenant để tenant lớn không chiếm hết cache.

Chọn consistent hashing hoặc hash slot tùy cache service; mọi client phải dùng cùng topology/routing contract. Không dùng modulo node count nếu reshard thường xuyên và không có cơ chế warm-up chịu được remap lớn.

### Bước 3 — Hot key

Với sản phẩm nổi bật:

1. Local L1 cache TTL ngắn cho dữ liệu công khai, nếu stale window 30 giây cho phép.
2. Request coalescing ở mỗi application instance để gộp miss.
3. Có thể tạo read replicas/copies nếu một shard vẫn nóng; refresh các copy theo product version.
4. Rate limit request bất thường theo product/tenant.
5. Pre-warm product hot list trước chiến dịch.

Không nhân bản contract price nếu mỗi tenant có quy tắc quyền truy cập riêng mà chưa đảm bảo key scope và cache isolation. Không dùng local cache cũ cho booking commit.

### Bước 4 — Invalidation và version

Khi product update, source tăng version. Cache key có thể dùng product version hoặc event invalidation. Event publisher dùng outbox để tránh mất invalidate event sau commit; consumer idempotent và có replay. Trong khoảng propagation, L1 cache có thể trả stale tới tối đa window được phép. Với giá, TTL nhỏ hơn và booking xác nhận lại ở nguồn.

### Bước 5 — Capacity và phân bố tải

Đo bytes và ops theo shard; không chỉ chia 8 triệu key cho 6 shard. Kiểm tra product hot list, category page, tenant lớn và payload price. Cần capacity để khi một shard mất, các node còn lại chịu tải hoặc một số endpoint giảm cấp. Warm-up sau failover phải giới hạn database fallback.

### Bước 6 — Tiêu chí chấp nhận

| Mục tiêu | Bằng chứng |
| --- | --- |
| Product detail stale không quá 30 giây theo policy | Version/TTL/lag telemetry và test invalidation |
| Không lẫn giá tenant/tier | Test cross-tenant, key canonicalization và authorization |
| Hot product không làm shard quá tải | Per-key class ops, local cache effectiveness, p99 |
| Reshard không gây miss storm vượt ngưỡng | Canary migration, database fallback load test |
| Cache failover không làm booking sai | Booking revalidates authoritative availability/price |

## 22. Case study: counter và rate limit có partition key

Một API ghi nhận lượt xem sản phẩm và giới hạn request theo user/tenant. Hai use case có đặc tính khác nhau:

- Page view có thể chấp nhận eventual aggregation và sai số nhỏ trong cửa sổ ngắn.
- Rate limit cần kiểm soát số request trong một khoảng thời gian; việc chia counter phải giữ đúng semantics giới hạn.

### Page view

Một key duy nhất product:42:views có thể trở thành hot key khi sản phẩm viral. Có thể chia thành nhiều bucket theo hash của application instance hoặc request ID, sau đó tổng hợp:

\[
\text{views}_{42}=\sum_{i=1}^{k}\text{views}_{42,i}.
\]

Consumer/aggregator cần dedupe event nếu counter cập nhật từ event có thể được giao lặp. Kết quả tổng hợp eventual và có thể chậm vài giây.

### Rate limit

Rate limit theo user có thể dùng key theo user ID và time window. Nếu một user phát rất nhiều request, key đó nóng; nhưng chia thành nhiều counter rồi tổng hợp trước mỗi request có thể phức tạp và tạo race. Cần chọn thuật toán như token bucket hoặc leaky bucket, xác định mức chính xác và có thể dùng một partition owner/atomic script nếu cache service hỗ trợ.

Nếu yêu cầu hard limit không được vượt, không được salt counter rồi cho phép mỗi bucket tự nhận hết quota. Có thể chia quota có kiểm soát (quota leasing) giữa các bucket hoặc dùng một điểm tuần tự hóa. Nếu chấp nhận approximate rate limit để bảo vệ service, có thể dùng local counters cộng tổng định kỳ nhưng phải mô tả sai số.

### Bài học từ hai use case

Partitioning không thể tách rời consistency. Cùng một hot key:

- Với view counter, chia bucket và eventual aggregation có thể phù hợp.
- Với giới hạn chi tiêu hoặc số lượt đặt cuối cùng, chia bucket độc lập có thể phá invariant.

Phải xác định trước **điều gì cần chính xác** rồi mới chọn cách phân tải.

## 23. Bài tập thực hành và đáp án định hướng

Một cache cluster có 4 shard phục vụ ba nhóm key:

| Nhóm | Số key | Request rate | Đặc điểm |
| --- | ---: | ---: | --- |
| Product detail | 2 triệu | 30.000 ops/s | Có 5 key nổi bật chiếm 40% traffic |
| Tenant configuration | 50.000 | 8.000 ops/s | Một tenant lớn chiếm 35% traffic |
| Session | 1 triệu | 12.000 ops/s | Key cần riêng theo user/session, TTL 30 phút |

Trong một đợt chiến dịch, cache shard thứ 2 có p99 tăng cao và eviction tăng; ba shard còn lại còn capacity. Database phía sau bắt đầu nhận nhiều query hơn vì cache miss.

### Câu 1 — Có nên thêm shard ngay?

**Đáp án định hướng:** Chưa. Phải xác định shard 2 nóng do nhiều key/bytes hay một/few hot keys. Nếu hot key chiếm 40% traffic, thêm node không tự tách key. Nếu tenant lớn tập trung vào một partition key, cần xem lại tenant/subpartition strategy. Thêm shard có thể chỉ giúp nếu bottleneck là capacity tổng hoặc dữ liệu phân vùng chưa cân bằng.

### Câu 2 — Đề xuất xử lý 5 product hot keys.

**Đáp án:** Xem xét local L1 cache TTL ngắn, request coalescing, pre-warming, rate limit và replicate read-only copies nếu dữ liệu công khai/chấp nhận stale. Update/invalidation dùng version/event và đo lag; booking vẫn xác nhận giá/tồn kho ở nguồn mạnh.

### Câu 3 — Làm sao xử lý tenant lớn?

**Đáp án:** Đo số key, bytes và ops của tenant. Có thể tách tenant lớn sang shard riêng bằng directory mapping, hoặc subpartition theo domain/category nếu query hỗ trợ. Cần quota và plan migration. Không tách chỉ dựa trên traffic tổng nếu các thao tác nhiều key cần colocate.

### Câu 4 — Session có nên replicate qua nhiều shard tùy ý?

**Đáp án:** Session cần scoping và lifecycle rõ; nếu replicate read replicas, phải hiểu consistency của update/logout/permission. Khi logout hoặc thu hồi quyền, session stale có thể tạo rủi ro bảo mật. Có thể dùng TTL, version/revocation state và nguồn authoritative cho thao tác nhạy cảm.

### Câu 5 — Vì sao shard 2 eviction tăng trong khi tổng memory cluster còn trống?

**Đáp án:** Vì eviction xảy ra theo node/shard hoặc capacity domain; memory rảnh ở shard khác không tự chuyển sang shard 2. Cần xem distribution bytes, TTL, skew, placement và khả năng rebalance.

### Câu 6 — Chiến lược reshard nào phù hợp?

**Đáp án định hướng:** Nếu dùng hash slot/consistent hashing, chuyển một phần keyspace theo canary, theo dõi p99, hit ratio, integrity và database fallback. Nếu key nóng là nguyên nhân, xử lý hot key trước. Topology/client refresh phải phối hợp để không có map cũ kéo dài.

### Câu 7 — Điều gì cần test trước khi failover shard?

**Đáp án:** Ownership map, role primary/replica, replication lag, fencing, client redirect/topology refresh, request retry/idempotency, hit/miss storm, database fallback và thời gian phục hồi. Kiểm tra cả lỗi khi một node không thực sự chết mà chỉ mất network.

## 24. Những sai lầm thường gặp

1. **Key thiếu tenant hoặc permission scope:** trả nhầm dữ liệu giữa tenant hoặc giữa người có quyền khác nhau.
2. **Key chứa mọi query parameter:** cardinality tăng và hit ratio giảm dù nhiều request tương đương.
3. **Nối key không có quy tắc escaping:** hai input khác nhau có thể thành cùng key.
4. **Không version hóa key khi đổi schema:** instance cũ và mới đọc payload không tương thích.
5. **Dùng modulo hashing khi thường xuyên tăng node:** remap gần như toàn bộ key và tạo miss storm.
6. **Hash đều nhưng không đo traffic:** một key nóng vẫn dồn vào một shard.
7. **Chọn tenant làm partition key duy nhất:** tenant lớn có thể trở thành hot shard.
8. **Dùng key salting cho dữ liệu cần atomic single value:** update/read phải fan-in và có thể sai invariant.
9. **Thêm shard để giải quyết hot key:** key vẫn ánh xạ một shard nếu không replicate hoặc chia key có chủ đích.
10. **Replicate hot key mà không có version/invalidation:** các copy trả giá trị khác nhau quá lâu.
11. **Không request coalescing:** cache miss của key phổ biến tạo hàng loạt query tới database.
12. **TTL giống nhau cho cả batch:** nhiều key hết hạn cùng lúc và gây thundering herd.
13. **Local cache thiếu invalidation:** app instances nhìn thấy các phiên bản khác nhau.
14. **Reshard toàn cluster cùng một lúc:** client topology, database fallback và network cùng chịu spike.
15. **Không dự phòng khi mất shard:** node còn lại không đủ capacity để gánh traffic.
16. **Metric dùng raw cache key:** lộ dữ liệu và tạo cardinality quá lớn.
17. **Chỉ đo hit ratio toàn cluster:** bỏ sót shard/key class có p99 và eviction rất cao.
18. **Coi cache là nơi giữ trạng thái không thể mất:** cache eviction/failover làm mất dữ liệu nghiệp vụ.

## 25. Checklist review thiết kế cache

- Key có deterministic, canonical, bounded và tránh collision không?
- Namespace có phân biệt môi trường, domain, schema version và tenant scope không?
- Có đưa mọi yếu tố ảnh hưởng response vào key mà không làm cardinality tăng quá mức không?
- Input có được chuẩn hóa theo semantics nghiệp vụ không?
- Cache key và partition key có được phân biệt rõ không?
- Partition strategy có phù hợp access pattern, multi-key operation và tenant distribution không?
- Hash function/mapping có đồng nhất giữa mọi client không?
- Khi thêm/bớt node, bao nhiêu key bị remap và client cập nhật topology thế nào?
- Hot key, hot tenant và skew có được đo theo shard/key class không?
- Có local cache, replication, request coalescing hoặc salting khi thực sự phù hợp không?
- TTL, jitter, stale-while-revalidate và invalidation có khớp stale tolerance không?
- Cache miss/failover có thể làm database quá tải không?
- Replication/failover có xử lý lag, fencing và stale topology không?
- IAM, TLS, key scope và quota có bảo vệ tenant và dữ liệu nhạy cảm không?
- Dashboard có per-shard latency, memory, eviction, ops, replication và migration metrics không?
- Có canary, rollback, runbook và restore/warm-up drill không?
- TCO đã tính node, replication, network, memory overhead và vận hành chưa?

## 26. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi chính | Bằng chứng cần có |
| --- | --- | --- |
| **Độ tin cậy** | Một shard/node lỗi hoặc topology thay đổi thì cache và nguồn dữ liệu có phục hồi được không? | Replication/failover test, miss storm test, database headroom |
| **Bảo mật** | Key có phân tách tenant và quyền; cache endpoint, credential, log có an toàn không? | IAM, TLS, namespace, negative permission test |
| **Hiệu năng** | Key/partition có phân bố traffic và dữ liệu hợp lý? Hot key có được xử lý? | Per-shard p95/p99, ops, bytes, hot-key metrics |
| **Tối ưu chi phí** | Có giữ key không cần thiết, replicate quá mức hoặc provision shard dư thừa? | Hit ratio, cost per operation, memory/egress, eviction |
| **Vận hành xuất sắc** | Thêm/bớt shard, refresh topology, invalidate và xử lý miss storm có quy trình không? | IaC/config, canary, dashboard, runbook, owner |
| **Tính bền vững** | Cache có giảm tài nguyên nguồn và tránh sao chép dữ liệu không cần thiết không? | Database offload, TTL/lifecycle, right-sizing |

Một thiết kế cache tốt không chỉ phân phối đều số key. Nó phải phân phối **dung lượng và tải thực**, giữ đúng ranh giới dữ liệu, xử lý được key nóng và topology thay đổi, đồng thời bảo vệ database khi cache miss hoặc failover. Hãy chọn key và partition theo access pattern cùng invariant nghiệp vụ; sau đó dùng metric và thử nghiệm để chứng minh cache đáp ứng SLO, chi phí và khả năng vận hành.
