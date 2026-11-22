# Phân biệt replica, snapshot và bản sao ngoài miền lỗi

> **Chương:** Sao lưu và phục hồi  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Phạm vi:** Apache Cassandra — cơ sở dữ liệu wide-column phân tán; liên hệ khóa phân vùng, thiết kế bảng theo truy vấn, consistency level, CQL, replication, compaction, repair, khắc phục sự cố và ứng dụng Java.

## 1. Vì sao replication không đồng nghĩa với backup?

Giả sử hệ thống đơn hàng dùng Cassandra với **replication factor (RF) = 3**. Một nhân viên vận hành vô tình chạy lệnh xóa sai dữ liệu. Sau vài giây, cả ba replica đều nhận cùng thao tác xóa. Cluster vẫn có ba bản sao được đồng bộ theo thiết kế, nhưng **cả ba cùng không còn phiên bản dữ liệu đúng mà ứng dụng cần**.

Nếu trước sự cố đã có một **snapshot** chưa bị xóa và bản snapshot đó được chuyển tới **kho lưu trữ độc lập với cluster**, đội vận hành có đường phục hồi dữ liệu cũ. Nếu chỉ có ba replica đang hoạt động, việc tăng consistency level hoặc chạy repair không thể tự tái tạo lại bản ghi bị xóa hợp lệ trên tất cả replica.

Ba cơ chế trả lời ba câu hỏi khác nhau:

1. **Replica:** dữ liệu còn phục vụ được khi một hoặc một số nút, ổ đĩa hoặc miền lỗi ngừng hoạt động không?
2. **Snapshot:** có giữ được một trạng thái dữ liệu trước thời điểm sự cố để khôi phục không?
3. **Bản sao ngoài miền lỗi:** khi cả cluster, vùng hạ tầng, tài khoản vận hành hoặc quyền quản trị gặp sự cố, bản backup có còn tồn tại và truy cập được không?

Mục tiêu của bài học là phân biệt rõ ba khái niệm, lựa chọn chúng theo **loại sự cố**, hiểu tác động lên **RPO/RTO**, thực hành các thao tác snapshot cơ bản và xây quy trình backup/restore có thể kiểm chứng.

## 2. Miền lỗi (failure domain) là gì?

**Miền lỗi** là một tập tài nguyên có thể cùng bị ảnh hưởng bởi một nguyên nhân: một ổ đĩa, một máy, rack, availability zone (AZ), datacenter, region, tài khoản cloud, hệ thống quản lý khóa hoặc tập quyền của người vận hành.

| Miền lỗi | Ví dụ | Biện pháp tương ứng |
|---|---|---|
| Ổ đĩa / node | SSD hỏng, JVM không khởi động, máy bị tắt | Replica trên node khác; thay node rồi đồng bộ dữ liệu |
| Rack / AZ | Mất nguồn hoặc mạng tại một khu | Đặt replica ở các rack/AZ khác nhau khi topology hỗ trợ |
| Datacenter / region | Sự cố diện rộng, mất mạng hoặc storage của cả region | Bản sao dữ liệu/cluster ở miền hạ tầng khác; kế hoạch chuyển lưu lượng |
| Logical / ứng dụng | CQL DELETE sai, TRUNCATE, bug ghi đè dữ liệu, TTL cấu hình sai | Backup có phiên bản từ **trước** thao tác sai và quy trình khôi phục |
| Quyền quản trị / bảo mật | Tài khoản bị chiếm quyền, xóa cả cluster và bucket backup cùng tài khoản | Bản sao có quyền, khóa mã hóa, retention và cơ chế xóa độc lập |
| Thảm họa kết hợp | Mất region trong lúc một snapshot đang tạo hoặc backup chưa tải xong | Nhiều bản khôi phục đã **hoàn tất và được xác minh** ở miền độc lập |

**“Ngoài miền lỗi” luôn phụ thuộc kịch bản:** một replica ở AZ khác có thể giúp chống lỗi AZ nhưng vẫn chịu rủi ro xóa dữ liệu logic. Một bucket object storage cùng region có thể tách lỗi ổ đĩa nhưng chưa đủ nếu mục tiêu là tồn tại sau sự cố toàn region. Bản sao ở region khác nhưng dùng chung quyền có thể xóa và chung khóa không truy cập được vẫn chưa độc lập về mặt quản trị.

## 3. Replica: phục vụ tính sẵn sàng và chịu lỗi đang diễn ra

### 3.1. Cassandra phân bố replica ra sao?

**Partition key** xác định token, rồi replication strategy và topology chọn các node lưu dữ liệu của phân vùng. Trong một datacenter, nhiều replica là các bản sao logic của cùng partition, không phải các mảnh dữ liệu được chia đều cho từng replica.

Ví dụ minh họa keyspace:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS shop.orders_by_customer_month (
    customer_id uuid,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

**Giả định:** datacenter tên **dc1** có đủ node/rack phù hợp cho RF = 3; production cần cấu hình snitch, topology và số node thực tế cho đúng. Truy vấn theo **(customer_id, order_month)** giúp xác định một partition, còn **created_at/order_id** sắp thứ tự các đơn hàng trong partition. Việc chia bucket theo tháng chỉ là ví dụ, phải điều chỉnh nếu một khách hàng có quá nhiều đơn.

Với replica phân tán theo rack/AZ, một node mất dữ liệu cục bộ có thể thay thế rồi nhận dữ liệu từ replica còn hoạt động bằng các quy trình chuẩn như bootstrap/replace/streaming hoặc rebuild theo tình huống. **Không lấy bản SSTable của một node bất kỳ để giả định nó chứa toàn bộ keyspace**.

### 3.2. Consistency level liên quan thế nào?

Khi ghi, coordinator liên hệ các replica và chờ đủ số phản hồi theo **consistency level (CL)** của request. Với RF = 3 trong local datacenter:

- **ONE:** thông thường cần một replica xác nhận; latency/availability có thể tốt hơn nhưng ghi mới chưa chắc đã được xác nhận tại các replica khác nếu xảy ra lỗi ngay.
- **LOCAL_QUORUM:** cần đa số replica của local DC, tức **2/3**; phù hợp với nhiều yêu cầu đọc/ghi cần giao nhau trong local DC.
- **ALL:** yêu cầu phản hồi từ tất cả replica liên quan; tính sẵn sàng kém hơn khi node lỗi.

Ví dụ từ Java driver 4.x:

~~~java
BoundStatement write = preparedInsert.bind(
        customerId, orderMonth, createdAt, orderId, "PAID", amount)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(write);
~~~

Đây là đoạn sử dụng trong chương trình đã khởi tạo **session**, **preparedInsert** và các biến. Mức CL quyết định yêu cầu phản hồi, **không tạo bản backup có lịch sử phiên bản**. Một lệnh **UPDATE** hoặc **DELETE** hợp lệ cũng được replicate.

### 3.3. Replica không chống được mọi mất dữ liệu

- **Xóa/ghi đè sai:** thao tác sai được sao chép như thao tác đúng.
- **TTL:** giá trị hết hạn theo TTL trên các replica, không có chức năng “quay ngược thời gian”.
- **Lỗi ứng dụng:** ghi dữ liệu sai cấu trúc hoặc sai khóa phân vùng có thể lan sang các bản sao.
- **Sự cố đồng thời:** nếu quá nhiều replica trong một miền lỗi chung bị mất trước khi có bản khác chứa dữ liệu, recovery có thể không khả thi chỉ từ replication.
- **Sự cố bảo mật:** người có quyền xóa cluster có thể xóa tất cả replica.

**Repair** giúp đối chiếu và đồng bộ khác biệt dữ liệu giữa replica theo cơ chế Cassandra; nó **không phải backup** và có thể góp phần lan truyền thao tác xóa hợp lệ tới replica còn thiếu. **Hints** có thể giúp chuyển ghi còn thiếu trong giới hạn vận hành, nhưng cũng không lưu lịch sử đủ để thay backup.

## 4. Snapshot: bản chụp SSTable tại một thời điểm của từng node

### 4.1. Snapshot Cassandra thực chất là gì?

Cassandra lưu dữ liệu bền vững trên các **SSTable** bất biến. Khi tạo snapshot, Cassandra duy trì các tham chiếu tới tập tệp SSTable ở thời điểm đó, thường dưới dạng **hard link** trên hệ thống tệp node, thay vì sao chép tức thì toàn bộ byte sang ổ khác.

Thông thường **nodetool snapshot** sẽ flush memtable liên quan trước khi tạo snapshot để đưa dữ liệu trong bộ nhớ vào SSTable; các tùy chọn như **--skip-flush** (nếu phiên bản hỗ trợ) làm thay đổi phạm vi dữ liệu được chụp. Vì vậy, cần kiểm tra chính xác phiên bản và flags; **snapshot không tự mang theo nội dung commitlog để tạo point-in-time recovery hoàn chỉnh**.

~~~mermaid
flowchart TD
    M["Memtable chứa ghi chưa flush"] -->|Snapshot mặc định yêu cầu flush theo phiên bản| S["SSTable bất biến"]
    S --> L["Snapshot: hard link tới các tệp SSTable"]
    S --> C["SSTable đang được Cassandra sử dụng"]
    L --> D["Vẫn nằm trên storage của node"]
    L --> E["Sao chép đến kho backup độc lập"]
    E --> V["Xác minh và duy trì retention"]
~~~

**Điều snapshot thực sự bảo vệ:** sau đó compaction có thể thay thế SSTable đang hoạt động, nhưng hard link thuộc snapshot vẫn giữ các byte cũ cho tới khi snapshot được xóa. Snapshot cục bộ có thể phục hồi trạng thái SSTable trước một cập nhật/xóa sau đó, **nếu tệp snapshot vẫn tồn tại và đủ dữ liệu cần khôi phục**.

**Điều snapshot không bảo vệ:** hỏng hoàn toàn ổ đĩa/volume nơi snapshot nằm, xóa cả node/volume, thiếu các node/snapshot cần để khôi phục keyspace, thiếu schema hoặc mất quyền giải mã. Snapshot cục bộ cũng có thể cùng bị xóa bởi lệnh dọn snapshot hoặc kẻ có quyền kiểm soát máy.

### 4.2. CQL và nodetool minh họa

Ví dụ trên môi trường thử nghiệm, với keyspace **shop** đã tồn tại:

~~~bash
# Trên một node Cassandra, tạo snapshot với tag riêng.
# Không chỉ chạy một node nếu mục tiêu là backup dữ liệu toàn cluster.
nodetool snapshot -t shop_20261121T0400Z shop

# Xem snapshots trên chính node này.
nodetool listsnapshots
~~~

**Ý nghĩa thao tác:** lệnh thứ nhất tạo snapshot cục bộ trên **node mà nodetool kết nối**. Lệnh thứ hai liệt kê snapshot cục bộ và dung lượng liên quan. Với mục tiêu backup một keyspace phân tán, cần **điều phối snapshot trên mọi node/replica có dữ liệu nằm trong phạm vi cần bảo vệ**, hoặc một kế hoạch bao phủ token-range được chứng minh đầy đủ. Không suy ra “chạy trên một node là chụp toàn cluster”.

Tùy phiên bản Cassandra, đường dẫn dữ liệu thường chứa thư mục table kèm định danh và thư mục **snapshots/<tag>**. **Không hard-code đường dẫn** khi xây hệ thống backup: dùng cấu hình data directories và metadata của node, sau đó kiểm tra các tệp thực tế.

### 4.3. Snapshot có phải ảnh chụp đồng thời toàn cluster không?

**Không mặc nhiên.** Snapshot trên từng node được tạo ở những thời điểm khác nhau. Ghi đang diễn ra có thể được quan sát ở các node không đồng nhất về thời gian; một batch hoặc chuỗi thay đổi nghiệp vụ qua nhiều partition cũng không biến thành giao dịch toàn cluster chỉ nhờ dùng chung snapshot tag.

Nếu bài toán đòi hỏi **một ranh giới khôi phục nhất quán theo nghiệp vụ**:

1. Xác định các keyspace/table liên quan và yêu cầu về tính nhất quán giữa chúng.
2. Nếu khả thi, tạm dừng/quiesce ghi nghiệp vụ hoặc thiết kế một **barrier/cutoff** trong ứng dụng và lưu mốc rõ ràng.
3. Điều phối snapshot tại các node, xác nhận **tất cả** thành công và lưu thời điểm từng node.
4. Xác thực dữ liệu sau restore bằng invariant của nghiệp vụ; không chỉ kiểm tra một câu SELECT.

**RPO thực tế** phụ thuộc ranh giới được hỗ trợ bởi quy trình này và các phần dữ liệu đã được xác nhận trong bản backup; **tag giống nhau không chứng minh snapshot có tính atomic trên toàn hệ thống**.

### 4.4. Dung lượng snapshot và compaction

Snapshot dựa trên hard link nên ban đầu có thể tạo nhanh, nhưng **không miễn phí dung lượng**:

- Khi compaction tạo SSTable mới, các SSTable cũ còn được snapshot giữ lại không được giải phóng khỏi đĩa như khi không có snapshot.
- Snapshot lâu ngày không dọn có thể làm đĩa đầy dù lượng dữ liệu live không tăng.
- Dung lượng “tổng” được liệt kê theo tệp có thể khác lượng block vật lý thật sự duy nhất do hard link chia sẻ dữ liệu.
- Sau khi snapshot đã được chuyển ra ngoài miền lỗi và **xác minh**, cần thực hiện chính sách retention/dọn dẹp cục bộ có kiểm soát, tránh giữ mãi trên node.

## 5. Bản sao ngoài miền lỗi: backup có thể sống sót sau sự cố lớn hơn

Một bản sao chỉ thực sự đáp ứng mục tiêu “ngoài miền lỗi” khi **rủi ro đang xét không thể phá hủy hoặc vô hiệu hóa cả dữ liệu gốc lẫn bản backup theo cùng một cách**.

Ví dụ kiến trúc:

~~~mermaid
flowchart LR
    subgraph DC["Cụm Cassandra trong datacenter/region chính"]
        A["Replica 1"]
        B["Replica 2"]
        C["Replica 3"]
    end
    A --> SA["Snapshot node 1"]
    B --> SB["Snapshot node 2"]
    C --> SC["Snapshot node 3"]
    SA --> U["Quy trình copy, manifest, checksum"]
    SB --> U
    SC --> U
    U --> O["Object storage ở miền hạ tầng độc lập"]
    O --> P["Retention/versioning/immutability"]
    O --> K["Khóa giải mã và quyền restore được kiểm thử"]
    O --> T["Cluster khôi phục thử nghiệm tách biệt"]
~~~

Kho ngoài miền lỗi có thể là object storage, backup service hoặc kho chuyên dụng được thiết kế cho yêu cầu khôi phục. Những yếu tố cần xem cùng nhau:

| Lớp độc lập | Câu hỏi kiểm tra |
|---|---|
| **Hạ tầng** | Backup có cùng host/volume/AZ/region với cluster hay không? Kịch bản mất region cần kho ở đâu? |
| **Định danh/quyền** | Người hoặc automation có quyền xóa database có đồng thời xóa được toàn bộ backup không? |
| **Mã hóa/khóa** | Nếu KMS/secret trong region chính bị mất hoặc thu hồi, vẫn giải mã được backup không? |
| **Vòng đời** | Có versioning, retention, WORM/immutability hoặc khả năng giữ bản không thể xóa tùy chính sách không? |
| **Độ hoàn chỉnh** | Có đủ SSTable, schema, cấu hình, danh sách node/token, tệp phụ trợ và nhật ký mốc thời gian để restore không? |
| **Khả năng khôi phục** | Đã thực sự tải xuống, khôi phục và chạy kiểm thử nghiệp vụ ở miền độc lập chưa? |

**Copy tệp snapshot ra bucket chưa phải kết thúc backup.** Phải xác minh số lượng và checksum tệp, khả năng đọc chúng, khóa mã hóa, metadata và khả năng dựng lại schema/cluster. Backup có thể “thành công” về mặt upload nhưng không phục hồi được vì thiếu table schema hoặc sai phiên bản SSTable.

### 5.1. Off-site khác off-domain

“Off-site” thường nhấn mạnh **vị trí lưu trữ khác**. “Outside the failure domain” yêu cầu tách rủi ro tương ứng; đôi khi cần thêm tài khoản quản trị, quyền xóa, khóa và đường mạng độc lập.

- Backup trong một bucket **cùng account có quyền admin xóa cả cluster và bucket** có thể đủ để chống hỏng ổ đĩa nhưng yếu trước kịch bản tài khoản bị chiếm quyền.
- Backup sang region khác nhưng **chỉ dùng khóa KMS nằm trong region hỏng** có thể không đọc được trong thảm họa.
- Backup immutable giúp chống thao tác xóa/sửa trái phép, nhưng nếu chưa kiểm thử restore, vẫn có thể thiếu dữ liệu hoặc cấu hình.

Không có một sơ đồ lưu trữ duy nhất tối ưu cho mọi tổ chức; chọn theo **sự cố cần chịu được, RPO/RTO và chi phí**.

## 6. So sánh trực tiếp replica, snapshot và bản sao ngoài miền lỗi

| Tiêu chí | Replica | Snapshot cục bộ | Bản sao ngoài miền lỗi |
|---|---|---|---|
| **Mục đích chính** | Duy trì phục vụ khi replica hỏng | Giữ phiên bản SSTable tại một mốc | Khôi phục khi dữ liệu/nút/miền lỗi chính bị phá hủy |
| **Tạo bằng gì?** | Replication strategy + cơ chế ghi/đọc Cassandra | Snapshot các SSTable của node | Chuyển snapshot và metadata đến kho độc lập; có thể kết hợp incremental/PITR |
| **Trạng thái dữ liệu** | Diễn biến cùng ghi/xóa hiện tại | Đóng băng nội dung tệp đã chụp | Giữ bản đã bảo quản theo chính sách và mốc phục hồi |
| **Chống một node mất?** | Có thể, nếu còn replica hợp lệ và đủ điều kiện CL | Không nếu snapshot nằm trên node bị mất | Có, nếu backup đủ dữ liệu để tái dựng |
| **Chống xóa sai lan khắp replica?** | Không | Có thể, nếu snapshot được tạo trước và còn nguyên | Có thể, nếu giữ được bản sạch trước sự cố |
| **Chống mất cả region?** | Chỉ khi có replica ở miền còn sống và thiết kế failover phù hợp | Không nếu chỉ lưu trong region hỏng | Có nếu vị trí, quyền, khóa và restore đều độc lập |
| **Có tự phục hồi tức thì?** | Không hoàn toàn; node có thể cần replace/rebuild/repair | Không; cần quy trình restore | Không; cần tải, dựng schema/cluster, nạp dữ liệu, kiểm tra |
| **Có lịch sử phiên bản?** | Không phải cơ chế lịch sử | Có theo từng snapshot/tag còn giữ | Có theo retention các bản backup |
| **Rủi ro còn lại** | Lỗi logic, lỗi chung toàn miền, dữ liệu chưa replicate | Mất đĩa node, snapshot thiếu, hết dung lượng | Backup cũ/hỏng, thiếu khóa, quyền sai, RTO không đạt |

**Tách câu hỏi:** “Còn node nào phục vụ được?” thuộc **replication/failover**. “Quay về trạng thái nào?” thuộc **backup/restore**. “Bản quay về có sống sót cùng thảm họa với hệ chính không?” thuộc **thiết kế miền lỗi**.

## 7. RPO và RTO: tiêu chí lựa chọn thiết kế

- **RPO (Recovery Point Objective):** chấp nhận mất tối đa bao nhiêu dữ liệu theo thời gian khi phục hồi. Ví dụ RPO = 1 giờ nghĩa là tổ chức muốn khôi phục dữ liệu không cũ hơn 1 giờ trước sự cố, theo phạm vi và điều kiện đã cam kết.
- **RTO (Recovery Time Objective):** hệ thống được yêu cầu trở lại trạng thái phục vụ trong bao lâu sau sự cố.

Với snapshot hoàn chỉnh mỗi 24 giờ và không có cơ chế lưu/khôi phục thay đổi giữa các snapshot, RPO thực tế **có thể xấp xỉ 24 giờ hoặc hơn** nếu bản gần nhất bị thiếu/hỏng. Có **3 replica** không làm RPO của backup trở thành 0. Nếu hệ thống còn hoạt động trên các replica sau lỗi đơn lẻ, thường **không cần restore từ backup**; khi đó đánh giá availability/failover khác với phục hồi dữ liệu lịch sử.

### 7.1. Ví dụ một chính sách có số cụ thể

Giả sử:

- Snapshot toàn bộ các node liên quan bắt đầu mỗi ngày lúc **02:00 UTC**.
- Upload ra kho backup hoàn tất và xác minh lúc **02:30 UTC**.
- Lúc **16:00 UTC**, thao tác xóa nhầm lan sang mọi replica.
- Bản sạch gần nhất là backup ngày đó, có cutoff nghiệp vụ được ghi nhận khi chụp.

Nếu phục hồi chỉ từ bản này, có thể mất các thay đổi được xác nhận **sau cutoff** đến 16:00. **Không lấy 02:30 là thời điểm có đầy đủ dữ liệu đến 02:30** chỉ vì upload xong lúc đó. Nếu cutoff hợp lệ là 02:00, khoảng mất có thể khoảng **14 giờ**.

Muốn RPO gần hơn cần cân nhắc snapshot thường xuyên hơn, cơ chế incremental backups và/hoặc **lưu trữ, phát lại commitlog có kiểm soát** tới mốc phù hợp. Point-in-time recovery (PITR) cần một **chuỗi backup nền + thay đổi tiếp theo liên tục, có thứ tự và tương thích**, không đạt được chỉ bằng việc bật một flag.

RTO bao gồm:

~~~text
Phát hiện + ra quyết định + cấp tài nguyên khôi phục
+ khôi phục schema/cấu hình và dữ liệu
+ replay/đồng bộ/cân bằng khi cần
+ kiểm tra nhất quán, kiểm thử ứng dụng
+ chuyển lưu lượng và giám sát
= tổng thời gian phục hồi
~~~

Kích thước backup, tốc độ tải, số node, số SSTable, network, disk, compaction và repair có thể làm RTO dài hơn nhiều thời gian copy một vài tệp thử nghiệm.

## 8. Incremental backup và commitlog archiving có vai trò gì?

### 8.1. Incremental backup không tự thay thế baseline

Ở các phiên bản Cassandra có **incremental_backups**, tính năng này lưu thêm bản liên kết/copy cục bộ cho các **SSTable mới được flush/stream vào** theo cơ chế của phiên bản. Nó không có nghĩa mỗi câu INSERT được xuất liên tục thành một bản backup độc lập và cũng không bảo đảm khả năng khôi phục toàn bộ lịch sử khi chưa có baseline, retention và chuỗi dữ liệu đầy đủ.

Chuỗi khôi phục điển hình cần:

1. Một **snapshot baseline** có mốc và inventory rõ ràng.
2. Các **SSTable tăng thêm** hợp lệ sau mốc baseline, được chuyển ra kho độc lập.
3. Metadata về thứ tự/mốc, schema và chính sách tombstone/TTL để tái dựng dữ liệu đúng.
4. Kiểm thử restore đảm bảo không thiếu hoặc nhân đôi dữ liệu cần thiết.

Tập SSTable incremental cũng có thể **tăng nhanh dung lượng** ở node vì bản được giữ lại cản trở giải phóng block cũ, nên phải theo dõi và dọn dựa trên xác nhận offsite.

### 8.2. Commitlog archiving và PITR

Commitlog ghi thông tin mutation nhằm hỗ trợ độ bền ghi ở replica. Cơ chế **commitlog archiving** (nếu phiên bản/triển khai hỗ trợ) có thể chuyển các segment sang kho khác và phục vụ phát lại theo quy trình khôi phục. Nhưng:

- Segment cần được lưu **đầy đủ, đúng thứ tự và được xác minh**; việc archiving có thể có độ trễ.
- Replay sai mốc có thể **phát lại cả thao tác xóa lỗi** mà ta đang cố tránh; phải xác định thời điểm/cutoff phục hồi.
- Phải tương thích schema, topology, phiên bản và cơ chế restore; các bước phục hồi cụ thể cần runbook được thử nghiệm.
- Không được gộp nhầm **commitlog của node** với log thay đổi nghiệp vụ toàn cluster có một thứ tự toàn cục hoàn hảo.

**CDC (Change Data Capture)** cũng không mặc nhiên là một bản backup: nó phục vụ dòng thay đổi theo cấu hình, có giới hạn retention/disk và cần downstream/offsets đủ bền để tạo chức năng phục hồi. Muốn RPO nhỏ phải kiểm chứng cả **mức mất dữ liệu tối đa khi backup pipeline gặp sự cố**.

## 9. Quy trình backup định kỳ từ Cassandra

Một quy trình vận hành tin cậy nên định nghĩa rõ **phạm vi, mốc thời gian, độ hoàn chỉnh và kiểm chứng**.

### 9.1. Trước khi tạo snapshot

1. Ghi lại **cluster name, Cassandra version, JDK version, partitioner, token/vnode topology, snitch, DC/rack, replication strategy** và bảng/keyspace cần sao lưu.
2. Xuất **schema CQL** của keyspace/table, đồng thời lưu schema version và dữ liệu cấu hình cần cho phục hồi. Không giả định chỉ có SSTable là dựng được bảng.
3. Xác định có dữ liệu dạng đặc biệt như counter, materialized view, secondary index, UDT, TTL, LWT/transactional invariants hay không để chuẩn bị phương án restore đúng phiên bản.
4. Xác định **application cutoff** nếu cần một ranh giới dữ liệu nghiệp vụ nhất quán; điều phối với luồng ghi.
5. Kiểm tra đủ disk free để tạo snapshot, giữ hard link và đẩy dữ liệu ra ngoài, tránh full disk vì lịch backup.

### 9.2. Tạo snapshot và chuyển ra kho độc lập

~~~mermaid
flowchart TD
    A["Đặt backup ID và cutoff mục tiêu"] --> B["Ghi metadata và schema"]
    B --> C["Điều phối snapshot trên các node cần thiết"]
    C --> D{"Mọi node bắt buộc thành công?"}
    D -->|Không| X["Đánh dấu backup không hoàn chỉnh; xử lý lỗi"]
    D -->|Có| E["Liệt kê SSTable, tạo manifest và checksum"]
    E --> F["Upload/đồng bộ đến kho độc lập"]
    F --> G["Kiểm lại checksum, quyền đọc, khóa giải mã"]
    G --> H{"Bộ backup phục hồi được?"}
    H -->|Không| X
    H -->|Có| I["Đánh dấu COMPLETE và áp retention"]
    I --> J["Dọn snapshot local theo quy trình"]
~~~

Chỉ khi **tất cả bước bắt buộc và xác minh** thành công mới công bố một backup set **COMPLETE**. Một node lỗi không nên được che bằng việc upload thành công phần còn lại. Với backup dựa trên độ phủ token-range đặc biệt, phải có bằng chứng đầy đủ về replica dữ liệu tương ứng.

Tối thiểu manifest của một backup set nên chứa:

~~~json
{
  "backup_id": "shop_20261121T0400Z",
  "status": "COMPLETE",
  "cluster": "shop-prod-example",
  "cassandra_version": "<actual-version>",
  "scope": ["shop"],
  "application_cutoff_utc": "<recorded-if-enforced>",
  "snapshot_started_utc": "<actual-time>",
  "snapshot_finished_utc": "<actual-time>",
  "nodes": [
    {
      "node_id": "<stable-node-identifier>",
      "dc": "dc1",
      "rack": "<rack>",
      "token_coverage": "<recorded>",
      "snapshot_tag": "shop_20261121T0400Z",
      "files": [
        {
          "path": "<relative-path-in-backup>",
          "size_bytes": 123456,
          "sha256": "<verified-hex-digest>"
        }
      ]
    }
  ],
  "schema_location": "<object-key>",
  "encryption_key_reference": "<key-id-or-recovery-metadata>"
}
~~~

Đây là **minh họa định dạng manifest nội bộ**; Cassandra không tự tạo chính xác JSON này. Không lưu credentials hoặc secret thô vào manifest. Nếu không có cutoff do ứng dụng đảm bảo, phải ghi rõ **"not guaranteed"**, không giả tạo một mốc nhất quán.

### 9.3. Kiểm chứng backup thay vì chỉ kiểm chứng upload

- **Tệp:** đủ số node, table ID, SSTable components; size và cryptographic checksum khớp.
- **Metadata:** có schema, token/partitioner/topology và phiên bản cần để xây cluster tương thích.
- **Bảo mật:** backup được mã hóa, quyền đọc phục hồi hoạt động, khóa độc lập khả dụng.
- **Tính đầy đủ:** backup set chỉ được đánh dấu complete khi mọi thành phần bắt buộc đã xác minh.
- **Khả năng phục hồi:** định kỳ tạo một cluster thử nghiệm từ backup; kiểm tra dữ liệu, bảng, phân vùng mẫu và invariant nghiệp vụ.
- **Thời gian:** đo thời gian tải, nạp, khởi động, kiểm chứng và chuyển lưu lượng; đối chiếu RTO/RPO.

Bản backup được coi là **có ích** khi có bằng chứng phục hồi thực tế, không chỉ khi công cụ sao chép báo exit code 0.

## 10. Chọn phương án phục hồi theo loại sự cố

| Sự cố | Hành động ưu tiên | Khi nào dùng backup? |
|---|---|---|
| Mất một node, replica khác vẫn khỏe | Replace/bootstrap/streaming theo quy trình Cassandra; kiểm tra replication và repair | Khi không còn đủ bản dữ liệu hợp lệ hoặc có yêu cầu phục hồi lịch sử |
| Mất một AZ, còn replica ở AZ khác và CL vẫn đáp ứng | Phục vụ từ replica còn sống, khôi phục node/rack, bảo trì topology | Nếu dữ liệu bị mất vượt khả năng replica |
| Toàn bộ region hỏng, có datacenter thứ hai độc lập và còn hợp lệ | Kế hoạch chuyển truy cập sang DC thứ hai, sau đó dựng lại vùng bị mất | Nếu DC thứ hai không còn/không đủ dữ liệu hoặc yêu cầu trạng thái cũ |
| DELETE/UPDATE sai đã replicate | Dừng nguồn gây lỗi; xác định mốc sạch; restore có kiểm soát | **Cần bản backup trước lỗi** hoặc nguồn lịch sử độc lập |
| TRUNCATE sai | Dừng thay đổi; kiểm tra snapshot tự tạo trước TRUNCATE **nếu cấu hình có** | Dùng snapshot còn nguyên hoặc backup ngoài miền lỗi; không mặc định snapshot tự tạo luôn tồn tại |
| Các node/volume và snapshot local đều mất | Tạo hạ tầng thay thế theo runbook | Phục hồi từ bản ngoài miền lỗi có schema, dữ liệu, khóa và manifest |
| Tài khoản quản trị chính bị chiếm quyền | Cô lập quyền, điều tra và dựng môi trường tin cậy | Bản immutable/independent credentials, khóa còn khả dụng |

**Không tùy tiện phục hồi SSTable cũ trực tiếp vào cluster đang nhận ghi mới.** Điều này có thể trộn trạng thái khác thời điểm, gây lỗi tương thích schema hoặc **hồi sinh dữ liệu đã xóa** nếu xử lý tombstone/TTL, repair và gc_grace không đúng. Phương án an toàn thường là **khôi phục trước trong môi trường cô lập**, kiểm chứng, rồi chọn phương án cắt chuyển hoặc tái nhập dữ liệu.

### 10.1. Phục hồi từ snapshot: hai hướng triển khai

**Hướng A — Khôi phục node/cluster tương thích:** chuẩn bị node dừng ghi theo quy trình, dựng đúng schema/table ID và phiên bản SSTable, đặt đúng tệp cần thiết vào đúng vị trí và dùng thủ tục nhận diện SSTable của phiên bản đó. Việc copy, khởi động/refresh và repair phụ thuộc topology và phiên bản; **không coi một lệnh cp + restart là runbook phổ quát**.

**Hướng B — Nạp dữ liệu vào cluster mới:** tạo keyspace/table tương thích, dùng công cụ streaming như **sstableloader** (khi phiên bản hỗ trợ), hoặc quy trình nhập lại logic có kiểm soát. Nạp vào cluster mới có thể thuận lợi cho **phục hồi chọn lọc** và kiểm tra trước khi chuyển traffic, nhưng phải tính thời gian streaming, dữ liệu trùng và tương thích schema.

Trong cả hai hướng:

- Khôi phục schema và cấu hình replication đúng mục tiêu; **không transplant bừa bãi system keyspace**, token ownership hoặc system tables giữa cluster khác.
- Kiểm tra checksum, định dạng SSTable, compression, UDT và table ID; các yếu tố này không tùy ý thay đổi được.
- Xác minh phần dữ liệu đã được ghi sau snapshot có cần replay/nhập từ nguồn khác không.
- Với thao tác xóa/TTL, không trộn dữ liệu cũ và mới mà bỏ qua ngữ nghĩa tombstone, **gc_grace_seconds** và trạng thái repair.
- Kiểm tra cả dữ liệu lẫn chức năng ứng dụng trước khi mở lưu lượng ghi.

## 11. Ví dụ một runbook ngắn cho sự cố xóa nhầm

**Tình huống:** lúc 15:30 UTC, bản phát hành Java service lỗi khiến lệnh DELETE ảnh hưởng tới dữ liệu đơn hàng trong keyspace **shop**. Lệnh xóa đã replicate, còn backup ngoài miền lỗi được xác minh tại cutoff 14:00 UTC.

1. **Chặn nguồn lỗi:** dừng chức năng ghi/xóa sai, cô lập phiên bản ứng dụng gây sự cố; ghi lại mốc phát hiện và mốc bắt đầu có thể bị ảnh hưởng.
2. **Bảo tồn chứng cứ và backup:** giữ nguyên bản backup sạch, khóa retention phù hợp; không dọn snapshot hoặc xoá log liên quan.
3. **Xác định phạm vi:** bảng, partition key, loại DELETE/TTL, thời điểm bắt đầu, số lượng đơn và các thay đổi hợp lệ sau cutoff cần giữ lại.
4. **Chọn recovery point:** cutoff 14:00 an toàn trước xóa; xác định yêu cầu nghiệp vụ với các đơn mới từ 14:00 đến 15:30.
5. **Dựng cluster phục hồi cô lập:** nạp schema và dữ liệu từ backup; kiểm tra phiên bản và topology; **không viết đè trực tiếp cluster production**.
6. **Kiểm chứng dữ liệu:** đối chiếu số lượng đơn theo customer/month, các order ID quan trọng, tổng tiền nghiệp vụ và trạng thái giao dịch; đánh giá tombstone/TTL, replay nếu có.
7. **Hòa giải dữ liệu sau cutoff:** nếu cần, nhập các sự kiện hợp lệ từ nguồn dữ liệu độc lập, outbox hoặc log nghiệp vụ đã được xác minh. Không replay mù lệnh DELETE lỗi.
8. **Chuyển lưu lượng có kiểm soát:** cập nhật cấu hình app/driver và connection points sau khi kiểm tra read/write, consistency, latency và failover.
9. **Hậu kiểm:** ghi RPO thực tế, RTO thực tế, nguyên nhân gốc; sửa phân quyền, kiểm thử SQL/CQL destructive và cảnh báo xóa hàng loạt.

Nếu chưa có nguồn dữ liệu độc lập cho thay đổi hợp lệ sau 14:00, phải **công khai mức mất dữ liệu thực tế** thay vì tuyên bố RPO = 0. Không phải mọi dữ liệu bị mất trong cửa sổ này đều có thể tái dựng từ replica sau khi thao tác xóa đã lan truyền.

### 11.1. Kiểm tra một số dữ liệu bằng CQL và Java

Với bảng ví dụ:

~~~sql
SELECT created_at, order_id, status, amount
FROM shop.orders_by_customer_month
WHERE customer_id = ? AND order_month = ?
LIMIT ?;
~~~

Truy vấn ràng buộc **đủ composite partition key**, phù hợp mô hình wide-column, để kiểm tra các partition mẫu sau restore. Nên kết hợp kiểm tra checksum/tệp và invariant cấp nghiệp vụ ở nhiều partition, không chỉ thử một hàng.

Ví dụ Java driver 4.x rút gọn để đọc sau phục hồi:

~~~java
import java.net.InetSocketAddress;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public class VerifyRecoveredOrders {
    public static void main(String[] args) {
        UUID customerId =
            UUID.fromString("11111111-1111-4111-8111-111111111111");

        // Trỏ vào cluster PHỤC HỒI / KIỂM THỬ đã được phê duyệt.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement read = session.prepare(
                "SELECT created_at, order_id, status, amount " +
                "FROM shop.orders_by_customer_month " +
                "WHERE customer_id = ? AND order_month = ? LIMIT ?");

            ResultSet rows = session.execute(
                read.bind(customerId, "2026-11", 100)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM));

            rows.forEach(row ->
                System.out.println(
                    row.getUuid("order_id") + " " +
                    row.getString("status")));
        }
    }
}
~~~

Đây là **kiểm tra minh họa**, không phải bộ kiểm thử phục hồi đầy đủ. Cần thay contact point/DC, bảo đảm số replica đáp ứng LOCAL_QUORUM và dùng tập mẫu khách hàng/đơn hàng đã biết trước khi xảy ra lỗi. Cần kiểm tra cả **đơn hàng đáng lẽ tồn tại nhưng đã mất**, chứ không chỉ các đơn hàng còn tìm thấy. Kết quả SELECT không tự xác nhận backup đủ cho mọi token range.

## 12. Sức khỏe của snapshot và backup trong vận hành

Để tránh trường hợp “có cấu hình backup nhưng không có bản khôi phục”, theo dõi:

| Tín hiệu | Mục đích |
|---|---|
| Lần backup **COMPLETE** cuối cùng, thời điểm dữ liệu thực của nó | Biết RPO hiện có, không nhầm thời gian upload và cutoff |
| Số node, số table, token ranges có đủ trong manifest | Phát hiện backup thiếu phần của cluster |
| Lỗi snapshot/flush, snapshot đang dang dở | Phát hiện nút hoặc scheduler thất bại |
| Thời gian backup và thời gian upload | Phát hiện pipeline chậm gây trễ RPO |
| Checksum failures / thiếu schema / thiếu khóa | Phát hiện bản không thể restore |
| Dung lượng snapshot local, free disk, compaction backlog | Tránh hard link giữ SSTable khiến ổ đĩa đầy |
| Backup retention, versioning, immutability, policy delete | Ngăn xóa nhầm và đáp ứng quy định lưu trữ |
| Kết quả diễn tập restore, RTO thực đo | Xác thực khả năng dùng backup thay vì chỉ có file |
| Repair status và replica health | Bảo đảm replication đang hoạt động theo kỳ vọng, tách khỏi chức năng backup |

**Alert nên kích hoạt khi không có bản COMPLETE mới trong ngưỡng RPO cho phép**, kể cả công cụ snapshot đã chạy nhưng job upload hoặc kiểm chứng thất bại. Thất bại của một lần backup không được khiến bộ backup sạch trước đó bị xóa vì retention vô điều kiện.

### 12.1. Liên hệ TTL, xóa dữ liệu và thời hạn giữ backup

Trong Cassandra, **TTL** và **tombstone** là một phần ngữ nghĩa dữ liệu. Backup cũ có thể chứa giá trị trước khi hết hạn hoặc trước khi xóa; sau restore cần tôn trọng timestamps/TTL và chính sách nghiệp vụ về dữ liệu được phép phục hồi. Nếu có yêu cầu xóa dữ liệu vì pháp lý/quyền riêng tư, không thể chỉ dựa vào việc xóa bản live mà bỏ qua retention của backup. Cần một chính sách lưu/xóa backup phù hợp quy định và kiểm soát quyền.

**gc_grace_seconds** ảnh hưởng cơ chế tombstone/repair, không phải thời hạn giữ backup. Giảm nó hoặc tự ý bỏ tombstone để tiết kiệm đĩa có thể gây hậu quả với replica chưa đồng bộ; không thay thế chính sách backup.

## 13. Bài tập tình huống

### Bài 1 — Ba replica còn nguyên nhưng mất dữ liệu

Một bảng có RF = 3, mọi truy vấn ghi/xóa dùng **LOCAL_QUORUM**. Một lệnh DELETE sai được áp dụng thành công, sau đó repair hoàn tất.

**Câu hỏi:**

1. Đọc LOCAL_QUORUM có tự lấy lại bản ghi đã xóa không?
2. Vì sao tăng RF từ 3 lên 5 sau khi xóa không giúp khôi phục?
3. Muốn quay lại trước DELETE cần gì?

**Gợi ý:** Replica sao chép trạng thái hiện tại, không cung cấp lịch sử thay đổi để undo. Repair không thể suy luận DELETE là lỗi nghiệp vụ. Cần snapshot/backup sạch trước khi xóa hoặc nguồn lịch sử độc lập, cùng quy trình restore.

### Bài 2 — Snapshot còn trên node nào?

Cluster có ba node, tất cả cùng ổ đĩa lưu dữ liệu và snapshot cục bộ. Công việc backup chỉ chạy **nodetool snapshot** trên node A. Sau đó toàn bộ ba node/volume bị mất vì sự cố storage region.

**Câu hỏi:**

1. Bản snapshot của node A có còn không?
2. Nếu chỉ node A còn sống, có thể mặc định snapshot của A chứa mọi partition không?
3. Cần thay đổi kiến trúc thế nào để đáp ứng thảm họa region?

**Gợi ý:** Snapshot chỉ lưu trên volume node; khi volume mất, snapshot cũng mất. Một node thường chỉ chứa replica của một phần token ranges. Cần snapshot đủ phạm vi, chuyển bản hoàn chỉnh tới kho độc lập region, xác minh schema/checksum/khóa và diễn tập restore.

### Bài 3 — Tính khoảng mất dữ liệu tiềm năng

Một ứng dụng tạo snapshot hoàn chỉnh vào **00:00** và chuyển đến kho ngoài miền lỗi lúc **00:45**. Không có incremental/commitlog archive. Sự cố xảy ra lúc **09:00**, các replica cùng bị phá hủy.

**Câu hỏi:** Nếu cutoff hợp lệ của snapshot là 00:00, khoảng thời gian thay đổi có nguy cơ mất là bao lâu? Có được dùng 00:45 làm recovery point không?

**Gợi ý:** Khoảng **9 giờ**. 00:45 là lúc hoàn tất chuyển bản, không có nghĩa dữ liệu đến 00:45 nằm trong bản snapshot.

### Bài 4 — Bucket ở region khác đã đủ chưa?

Bản snapshot được upload sang một region khác. Tuy nhiên, cùng service account có quyền xóa cả database và bucket, và chỉ khóa KMS ở region chính có quyền giải mã.

**Câu hỏi:** Kiến trúc này chịu được những loại lỗi nào, còn rủi ro nào?

**Gợi ý:** Có thể chịu được mất ổ đĩa/region nếu bucket và quyền giải mã vẫn tồn tại, nhưng còn điểm yếu quyền quản trị chung và phụ thuộc KMS. Cần tách quyền, bảo vệ retention/immutability theo yêu cầu và kiểm thử giải mã/restore khi region chính không khả dụng.

### Bài 5 — Chọn hành động trong ba sự cố

| Sự cố | Chọn cơ chế ưu tiên |
|---|---|
| Một node hỏng, RF còn hai replica khỏe và dữ liệu hợp lệ | **Replication + replace/streaming**, kiểm tra replica và CL |
| TRUNCATE nhầm đã tới mọi replica | **Snapshot/backup trước sự cố** và restore có kiểm soát |
| Mất toàn bộ region, chỉ còn bản trên object storage độc lập | **Backup ngoài miền lỗi**, dựng cluster mới và kiểm thử chuyển lưu lượng |

Giải thích vì sao **không phải mọi sự cố đều nên khôi phục từ snapshot**: với lỗi node đơn lẻ, thay node và đồng bộ từ replica còn tốt thường phù hợp hơn và giữ được dữ liệu mới nhất.

## 14. Checklist tự đánh giá thiết kế

- [ ] Đã định nghĩa các **miền lỗi** cần chịu được: node, AZ, region, thao tác sai, chiếm quyền.
- [ ] Replication strategy, RF, topology và consistency level được thiết kế và giám sát.
- [ ] Snapshot bao phủ **đủ node, keyspace, bảng, token range**; ghi được ranh giới mốc dữ liệu có thể khôi phục.
- [ ] Có schema, thông tin phiên bản/partitioner/table IDs và metadata cần thiết.
- [ ] Bản backup **ra khỏi miền lỗi mục tiêu**, checksum khớp và có quyền/khóa giải mã độc lập thích hợp.
- [ ] Có retention, chống xóa nhầm và chính sách dọn snapshot local sau khi xác minh.
- [ ] Có kế hoạch incremental/commitlog archive **nếu** RPO yêu cầu, đã thử replay đến mốc hợp lệ.
- [ ] Có runbook cho lỗi node, xóa logic và mất region; biết cách khôi phục vào môi trường cô lập.
- [ ] Diễn tập restore đủ dung lượng thực tế, đo RPO/RTO và xác minh bằng invariant ứng dụng Java.
- [ ] Theo dõi bản backup **COMPLETE** cuối cùng và cảnh báo khi thời điểm dữ liệu quá cũ.

## 15. Tổng kết

**Replica** là công cụ giữ Cassandra tiếp tục phục vụ khi thành phần hạ tầng gặp lỗi, được điều khiển bởi partition key, replication strategy và consistency level. **Snapshot** giữ các tệp SSTable tại một mốc trên từng node, giúp có dữ liệu lịch sử để phục hồi nhưng vẫn nằm trong miền lỗi của storage cục bộ. **Bản sao ngoài miền lỗi** chuyển tập snapshot đầy đủ cùng schema, metadata và phương tiện giải mã đến nơi có thể tồn tại sau thảm họa đã xác định.

Thiết kế đúng cần phối hợp cả ba: replication cho tính sẵn sàng; snapshot cho mốc dữ liệu có thể quay lại; kho backup độc lập cho khả năng sống sót khi các bản gốc cùng mất. Điều quyết định không chỉ là có bao nhiêu file backup, mà là **đã biết recovery point, xác minh dữ liệu/khóa và diễn tập khôi phục để đạt RPO/RTO thực tế hay chưa**.
