# Theo dõi dung lượng dữ liệu, chỉ mục và transaction log

Một cơ sở dữ liệu Neo4j có thể vẫn trả lời Cypher bình thường trong khi phân vùng lưu trữ đang gần đầy, một index chưa xây xong hoặc các tệp transaction log tăng nhanh hơn kế hoạch. Đến khi ứng dụng bắt đầu gặp lỗi ghi, thời gian truy vấn tăng mạnh hay backup thất bại thì khoảng thời gian xử lý an toàn có thể đã rất ngắn. **Giám sát dung lượng phải phân biệt rõ phần dữ liệu bền vững, chỉ mục, transaction log và tài nguyên hạ tầng; không chỉ nhìn tổng số node.**

Bài thuộc chương **Giám sát** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Neo4j tổ chức dữ liệu liên kết theo **property graph**, hỗ trợ truy vấn node, relationship và đường đi bằng Cypher, sử dụng index/constraint để phục vụ tìm kiếm, Java Driver và Spring Data Neo4j để tích hợp ứng dụng. Những công cụ này tạo ra các mẫu đọc, ghi và tăng trưởng dữ liệu khác nhau; vì vậy người vận hành cần theo dõi **store size, trạng thái và kích thước index, transaction logs, tốc độ tăng, dung lượng đĩa còn lại và mức độ sẵn sàng để phục hồi**.

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa **data store**, **index**, **transaction log**, **query log** và bộ nhớ **page cache**.
- Thu thập chỉ số dung lượng trên bản tự quản lý và hiểu giới hạn giám sát của các gói Neo4j được quản lý.
- Dùng `SHOW INDEXES` theo dõi `ONLINE`/`POPULATING`/`FAILED`, kết hợp `EXPLAIN`/`PROFILE` để đánh giá index thực sự phục vụ truy vấn.
- Đọc và kiểm tra chính sách **rotation/retention** transaction log mà không xóa tệp log thủ công.
- Thiết kế biểu đồ, ngưỡng cảnh báo, dự báo thời điểm hết dung lượng và runbook ứng phó sự cố.
- Kiểm thử một hệ thống giám sát có dữ liệu thật, log phát sinh và tình huống thiếu quyền hoặc thiếu metrics.

> **Phạm vi phiên bản:** Tên setting, metric, quyền và dashboard thay đổi theo phiên bản Neo4j, Community/Enterprise Edition, mô hình cluster và gói Aura. Các ví dụ Cypher dùng cho dòng Neo4j 5.x/những dòng mới có hỗ trợ lệnh tương ứng. Hãy kiểm tra phiên bản và tài liệu triển khai trước khi sao chép lệnh quản trị lên production.

## 1. Ba thành phần dung lượng quan trọng

Mô hình đơn giản:

~~~text
Ứng dụng Java / Spring Data Neo4j
                 |
                 v
          Cypher đọc / ghi
                 |
        +--------+----------+
        |                   |
        v                   v
    Data store           Index store
  node, relation,      range, lookup,
  property, metadata   text, point,
                      full-text, vector...
        |                   |
        +--------+----------+
                 |
         Transaction commit
                 |
                 v
       Transaction log files
           rotation / pruning
                 |
                 v
     Khả năng recovery, backup,
      catch-up tùy triển khai
~~~

| Thành phần | Chứa gì? | Vì sao có thể tăng? | Có thể xóa trực tiếp để giải phóng đĩa? |
| --- | --- | --- | --- |
| **Data store** | Cấu trúc node, relationship, property và metadata bền vững. | Nạp node/relationship, tăng property, thay đổi mô hình. | **Không.** Phải dùng thao tác dữ liệu được hỗ trợ và quy trình vận hành đúng. |
| **Index store** | Cấu trúc tra cứu cho label/type, property, full-text, vector và index phục vụ constraint. | Tạo index, thêm dữ liệu được đánh chỉ mục, thay đổi giá trị, rebuild. | **Không.** Quản lý bằng schema command và quy trình được hỗ trợ. |
| **Transaction log** | Bản ghi các thay đổi giao dịch cần cho khôi phục và các cơ chế theo dõi tiến trình, tùy cấu hình. | Tốc độ ghi cao, transaction lớn, rotation/retention, yêu cầu recovery/backup/catch-up. | **Không bao giờ xóa bằng file manager khi database đang vận hành.** |

Trong bản Neo4j tự quản lý, các tệp này có thể nằm ở những đường dẫn hoặc volume khác nhau. **Tổng dung lượng của database không nhất thiết bằng tổng mọi tệp bên dưới một thư mục duy nhất.** Cần biết cấu hình vị trí store, transaction logs và nơi giữ backup của triển khai cụ thể.

### 1.1. Transaction log không phải query log

- **Transaction log** là thành phần của cơ chế giao dịch và phục hồi cơ sở dữ liệu; liên quan đến tính bền vững sau commit.
- **Query log** là nhật ký quan sát những câu Cypher đã chạy theo chính sách ghi log, thường dùng chẩn đoán hiệu năng và vận hành.
- **Security/debug/server log** dùng cho xác thực, lỗi hoặc sự kiện vận hành theo khả năng của phiên bản/edition.

Không dùng chính sách rotation của `query.log` để suy ra thời hạn giữ transaction log. Không dùng tổng kích thước transaction log để ước lượng trực tiếp số query đọc; một truy vấn chỉ đọc không tạo lượng bản ghi thay đổi dữ liệu giống một transaction ghi.

### 1.2. Dung lượng trên đĩa khác bộ nhớ làm việc

Neo4j còn dùng **page cache** để giữ các trang dữ liệu/index thường truy cập trong bộ nhớ. Dung lượng page cache không phải bản sao tệp phải cộng vào disk usage; một trang được cache không khiến data store trên đĩa tự nhân đôi.

Ngoài ra còn có **heap**, bộ nhớ native, bộ nhớ của transaction/query, và bộ nhớ đồ thị chiếu vào **Graph Data Science** nếu triển khai GDS. Tệp store có thể lớn hơn RAM rất nhiều và vẫn chạy được, nhưng hiệu năng tùy theo working set, hit/miss page cache và thông lượng I/O.

**Nguyên tắc:** khi điều tra lỗi “hết dung lượng”, xem disk/volume. Khi điều tra truy vấn chậm dù còn nhiều đĩa, xem page cache, CPU, I/O, query plan, locking và cấu trúc đồ thị. Hai nhóm tín hiệu liên quan nhưng không đồng nghĩa.

## 2. Xác định phạm vi và đơn vị đo trước khi lập dashboard

Trước khi xem chỉ số, ghi lại:

1. **Deployment:** self-managed hay Aura, Community hay Enterprise, single instance hay cluster.
2. **Database và instance:** tên database nào, có bao nhiêu server lưu bản sao, leader/follower ra sao?
3. **Volume:** data store, transaction logs, backup, OS logs và filesystem tạm có chung ổ không?
4. **Đơn vị:** byte, MiB/GiB theo lũy thừa 1024 hay MB/GB theo lũy thừa 1000.
5. **Thời điểm đo:** các giá trị có được lấy trong cùng cửa sổ thời gian/instance không?
6. **Chất lượng thu thập:** có mất mẫu, metrics bị chặn quyền, instance restart hoặc collector ngừng hoạt động không?

Một số phân biệt cần giữ nguyên:

| Thước đo | Ý nghĩa | Có thể hiểu sai như thế nào? |
| --- | --- | --- |
| Tổng byte tệp store | Dung lượng vật lý hiện dùng bởi phần store được đo. | Không phải tổng số byte nội dung nghiệp vụ còn “sống”. |
| Dung lượng index | Byte trên đĩa dành cho index được đo. | Không có quan hệ tuyến tính cố định với số node. |
| Byte transaction logs | Byte các tệp log giao dịch hiện giữ. | Không bằng toàn bộ lịch sử thay đổi của hệ thống. |
| Disk free bytes | Byte hệ thống tệp còn cấp phát được ở volume đó. | Một database có thể dùng volume khác hoặc quota riêng. |
| Dữ liệu logical | Số node, relationship hoặc record đáp ứng một bộ lọc. | Không suy ra trực tiếp bao nhiêu GB trên đĩa. |
| Tốc độ ghi | Transaction/giây, byte ghi/giây, các thay đổi theo thời gian. | Ghi liên tục ít byte và ghi burst lớn gây áp lực khác nhau. |

**Không lấy kích thước từng bản sao cluster cộng lại rồi gọi là “kích thước một database logic”.** Nếu ba server giữ ba bản sao, chi phí hạ tầng có thể là tổng ba bản sao, nhưng dung lượng logic của database vẫn là một tập dữ liệu được sao chép. Dashboard nên có cả góc nhìn **theo database** và **theo từng instance/volume**.

## 3. Nguồn đo trên self-managed và Aura

| Nguồn | Self-managed | Managed/Aura | Ghi chú |
| --- | --- | --- | --- |
| Số liệu OS/filesystem | Disk free/used, latency, inode, dung lượng thư mục khi có quyền. | Thường không có quyền trực tiếp vào hệ điều hành máy chủ. | Cần xem volume thật, không chỉ ổ chứa ứng dụng. |
| Neo4j metrics / monitoring endpoint | Có thể xuất qua cơ chế monitoring phù hợp edition/version, kết hợp Prometheus/JMX/CSV nếu hỗ trợ. | Dashboard/metrics và khả năng export do dịch vụ/gói cung cấp. | **Tên metric thay đổi giữa phiên bản**; không tự dựng tên. |
| Cypher admin commands | `SHOW DATABASES`, `SHOW INDEXES`, `SHOW SETTINGS`, `SHOW TRANSACTIONS` theo quyền. | Các lệnh được dịch vụ cho phép; có thể hạn chế. | Không phải mọi lệnh đều trả byte size. |
| Neo4j logs | Quan sát lỗi, index population, transaction/backup theo khả năng ghi log. | Những log dịch vụ có thể truy xuất qua console/API theo gói. | Log có thể thiếu hoặc bị trễ; bảo vệ thông tin nhạy cảm. |
| Backup service / object storage | Kích thước backup, thời điểm backup thành công, khả năng restore. | Dashboard/backup policy do nhà cung cấp hỗ trợ. | Backup hoàn tất không có nghĩa đã kiểm thử restore. |

### 3.1. Không mặc định có một metric chung cho mọi bản

Ví dụ, một hệ thống Prometheus có thể lưu các nhóm số liệu sau:

~~~text
neo4j_database=neo4j
instance=graph-01
measure=store_bytes | index_bytes | tx_log_bytes
sample_time=...
value_bytes=...
~~~

Đây là **mô hình tên/nhãn nội bộ minh họa**, không phải bộ tên metric Prometheus có sẵn của Neo4j. Khi cấu hình thật, lấy danh mục metric **từ endpoint/exporter của đúng phiên bản** và lập bảng ánh xạ thành các tên dashboard thống nhất. Nếu exporter không có một trường, có thể bổ sung một collector filesystem hoặc một phép đo khác có nguồn và quyền hợp lệ.

Đối với Aura, không giả định có thể chỉnh `neo4j.conf` hoặc truy cập thư mục dữ liệu. Hãy dùng metrics, alert và quy trình tăng tài nguyên do gói dịch vụ cho phép; nếu cần chi tiết chưa được cung cấp, phải ghi nhận khoảng trống khả năng quan sát thay vì bịa số.

## 4. Đo dung lượng store và lượng dữ liệu logic

### 4.1. Quan sát disk/volume trên hệ thống tự quản lý

Ví dụ shell **trên máy Linux tự quản lý** với quyền phù hợp, sau khi người vận hành đã kiểm tra đúng đường dẫn từ cấu hình hiện tại:

~~~bash
# Thay các đường dẫn ví dụ bằng đường dẫn thực tế đã xác minh.
df -h /var/lib/neo4j/data
du -sh /var/lib/neo4j/data/databases/neo4j
du -sh /var/lib/neo4j/data/transactions/neo4j
~~~

Phần trên chỉ minh họa cách đo bằng hệ điều hành, **không phải lệnh để chạy trong Cypher**. Vị trí transaction log có thể được cấu hình sang volume khác; một số triển khai dùng container, Kubernetes, Windows hoặc storage mạng với cách mount khác. Hãy lấy đường dẫn từ cài đặt thực thay vì đoán theo mặc định.

Các sai số cần xét:

- `du` đo dung lượng tệp đang hiện hữu trong cây thư mục, còn `df` đo không gian còn lại của filesystem. Hai số không nhất thiết cộng trừ trực tiếp vì metadata, snapshot, reserved blocks, các tệp khác và tệp đã xóa nhưng vẫn được process mở.
- Tệp lớn bị xóa khỏi namespace nhưng còn file handle đang mở có thể khiến `df` chưa tăng free space như dự tính.
- Filesystem nén, thin provisioning, snapshot hoặc storage quota có thể làm “dung lượng logic”, “dung lượng cấp phát” và “dung lượng vật lý” khác nhau.
- Index có thể nằm trong thư mục store hoặc được tính cùng tổng store, nên **không cộng hai metric nếu nguồn đo đã bao hàm nhau**.
- Disk usage của log ứng dụng/backup có thể cạnh tranh trực tiếp với phần data dù bản thân database store không tăng.

**Tuyệt đối không sửa hoặc xóa tệp database/log bằng lệnh hệ điều hành** để “dọn” trong một Neo4j đang hoạt động. Những thao tác thay đổi file-level database cần quy trình backup/restore hoặc công cụ Neo4j được hỗ trợ.

### 4.2. Quan sát database đang chạy

Lệnh kiểm tra trạng thái database:

~~~cypher
SHOW DATABASES
YIELD name, currentStatus, requestedStatus
RETURN name, currentStatus, requestedStatus
ORDER BY name;
~~~

Lệnh này cho biết trạng thái **không phải byte size**. Không lấy `currentStatus = 'online'` làm bằng chứng rằng còn đủ dung lượng để commit một transaction lớn.

Các truy vấn số lượng logic:

~~~cypher
MATCH (n:Customer)
RETURN count(n) AS customerCount;
~~~

~~~cypher
MATCH ()-[r:PLACED]->()
RETURN count(r) AS placedRelationships;
~~~

Hai ví dụ trên giả định label/type `Customer` và `PLACED` tồn tại; chúng không thay đổi dữ liệu. Kết quả giúp theo dõi tăng trưởng theo **thực thể nghiệp vụ**, nhưng không thay thế kích thước store/index trên đĩa.

Trong một số mẫu `count` đơn giản, Neo4j có thể tận dụng thống kê count store; với bộ lọc phức tạp, traversal hoặc `DISTINCT`, truy vấn kiểm kê có thể rất tốn tài nguyên. Đừng chạy toàn bộ kiểm kê bằng cách scan đồ thị mỗi vài giây trên production. Có thể ưu tiên metric chi phí thấp, báo cáo định kỳ và thống kê đã được duy trì đáng tin cậy.

### 4.3. Đọc tốc độ tăng theo lớp dữ liệu

Theo dõi ít nhất:

- `storeBytes`: dung lượng phần store theo nguồn đo cố định.
- `indexBytes`: kích thước index, tránh cộng đúp vào store.
- `txLogBytes`: tổng transaction log đang giữ.
- `freeBytes`: dung lượng còn lại của filesystem tương ứng.
- `nodeCount` và `relationshipCount` theo label/type quan trọng nếu có nguồn thống kê đủ rẻ.
- Tốc độ ghi mới, transaction commit và lượng dữ liệu import theo thời gian.

Việc chia theo tenant, nhãn, loại quan hệ hoặc ngày nhập dữ liệu giúp tìm nguồn tăng trưởng, nhưng **Neo4j không mặc nhiên cung cấp byte size chính xác theo từng label**. Một node chứa property lớn có thể chiếm nhiều byte hơn hàng trăm node nhỏ. Nếu cần phân bổ chi phí chính xác theo tenant, phải xây cách đo/ước lượng riêng và ghi rõ sai số.

## 5. Theo dõi index: tồn tại, trạng thái và hiệu quả

Một index không chỉ “có hoặc không”. Nó còn có trạng thái xây dựng, loại, phạm vi node/relationship và tác động lên tốc độ truy vấn cũng như dung lượng đĩa.

### 5.1. Liệt kê và theo dõi trạng thái

~~~cypher
SHOW INDEXES
YIELD name, type, entityType,
      labelsOrTypes, properties,
      state, populationPercent
RETURN name, type, entityType,
       labelsOrTypes, properties,
       state, populationPercent
ORDER BY name;
~~~

Các trường này được dùng trong các phiên bản Neo4j có `SHOW INDEXES`. Tùy version, edition và trạng thái index, có thể có các cột bổ sung như provider, owning constraint, lý do lỗi, số lần đọc hoặc lần đọc cuối. **Đừng giả định mọi cột bổ sung đều có ở tất cả bản.**

| Trạng thái thường gặp | Diễn giải | Cách phản ứng |
| --- | --- | --- |
| `ONLINE` | Index đã sẵn sàng phục vụ theo cách database hỗ trợ. | Kiểm tra query plan để biết truy vấn thực tế có dùng hay không. |
| `POPULATING` | Neo4j đang xây/populate index. | Theo dõi tiến độ, thời gian, CPU/I/O và dung lượng; không coi là đã sẵn sàng. |
| `FAILED` | Index không hoàn tất hoặc gặp lỗi không sử dụng được. | Thu thập lý do, log và tình trạng tài nguyên; xử lý theo runbook. |

Index có thể thuộc các nhóm **lookup, range, text, point, full-text, vector** theo tính năng của phiên bản. Mỗi loại phục vụ mẫu truy vấn khác nhau; không có một index tối ưu mọi thao tác Cypher.

### 5.2. Kết hợp index với constraint

Một uniqueness constraint có thể sử dụng index để thực thi. Ví dụ khóa khách theo tenant và customer ID:

~~~cypher
CREATE CONSTRAINT mon_demo_customer_unique IF NOT EXISTS
FOR (c:MonDemoCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

Lệnh này **thay đổi schema**; chỉ chạy ở database học tập có quyền phù hợp. Nếu schema chứa constraint/index hỗ trợ khóa nghiệp vụ, không được xóa index chỉ vì cho rằng nó “ít lượt đọc”. Việc xóa constraint có thể làm mất bảo vệ tính duy nhất và thay đổi phương án thực thi truy vấn.

Đối với index do constraint sở hữu, hãy kiểm tra quan hệ sở hữu trong `SHOW INDEXES`/`SHOW CONSTRAINTS` theo phiên bản, đánh giá các query quan trọng và chi phí ghi trước khi quyết định thay đổi.

### 5.3. Có index chưa chắc query đã dùng

Ví dụ tìm một khách trong tenant:

~~~cypher
EXPLAIN
MATCH (c:MonDemoCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c.customerId AS id, c.displayName AS name;
~~~

Nếu cần biết chi phí chạy thật:

~~~cypher
PROFILE
MATCH (c:MonDemoCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c.customerId AS id, c.displayName AS name;
~~~

`EXPLAIN` tạo kế hoạch dự kiến nhưng không thực thi; `PROFILE` **thực thi truy vấn** và hiển thị thống kê như `Rows`, `DB Hits` theo khả năng của phiên bản/runtime. Chỉ chạy `PROFILE` với các truy vấn đọc đại diện trong điều kiện an toàn; không bật với lệnh ghi/destructive trên production một cách tùy tiện.

Quan sát:

1. Truy vấn có bắt đầu từ index seek/scan phù hợp hay quét nhiều node?
2. Các bộ lọc theo tenant được áp dụng ở đâu?
3. Có mở rộng hàng triệu relationship sau khi đã tìm đúng node bắt đầu không?
4. Có `Sort`/`Aggregation` lớn ở cuối không?
5. Index đang `ONLINE` nhưng chậm do dữ liệu, fan-out, network hay page cache?

**Một index mới có thể tăng kích thước lưu trữ và chi phí ghi**, nhưng không giúp query nếu không dùng đúng predicate. Ngược lại, một query đã tìm chính xác một node nhờ index mà chậm ở traversal nên cần xem mô hình dữ liệu/thuật toán thay vì thêm index vô tội vạ.

## 6. Giám sát quá trình tạo và rebuild index

Với database lớn, tạo range/full-text/vector index có thể tiêu thụ nhiều **CPU, I/O, bộ nhớ và dung lượng đĩa tạm thời** trong giai đoạn population. Theo dõi cả **trạng thái** lẫn **nguồn lực**.

| Chỉ số | Đọc ra điều gì? |
| --- | --- |
| Trạng thái `POPULATING`, tỷ lệ `populationPercent` | Biết index đang xây và tiến độ được công bố. |
| Thời gian kể từ khi bắt đầu | Index có kéo dài bất thường so với tập dữ liệu và cấu hình? |
| Free bytes và tốc độ thay đổi dung lượng | Còn đủ chỗ cho index mới, dữ liệu phát sinh và log cùng lúc? |
| CPU/I/O và page-cache pressure | Có đang làm giảm SLO truy vấn ứng dụng không? |
| Database/log errors liên quan index | Có nguyên nhân cụ thể cho `FAILED` hoặc population không tiến triển? |
| Transaction write rate | Dữ liệu đang thay đổi trong khi xây index, ảnh hưởng tiến độ? |

### 6.1. Khi index ở POPULATING quá lâu

Không lập tức drop/recreate theo phản xạ. Trước tiên:

- Xác minh index thật sự đang tăng tiến độ hay chỉ cập nhật chậm.
- Đọc thông báo lỗi và log hệ thống được phép truy cập.
- Xác minh không gian đĩa còn đủ và không có I/O saturation.
- Kiểm tra node/relationship nào được index, kích thước property, sự tương thích type, phiên bản/provider.
- Đánh giá tác động của import và ghi đồng thời.
- Chọn cửa sổ thay đổi, rollback và backup phù hợp trước khi tạo lại.

Mỗi lần rebuild có thể tự tạo **đỉnh sử dụng đĩa** và làm lại công việc tốn kém. Một index `FAILED` cần được khắc phục nguyên nhân trước khi thử lại để không lặp sự cố.

### 6.2. Không coi ít lượt đọc là đủ lý do xóa

Một index có thể phục vụ một job định kỳ rất quan trọng nhưng ít được gọi; một index khác có thể bảo vệ constraint. Nếu phiên bản cung cấp `readCount`, `lastRead` hoặc metric tương tự, hãy kết hợp **tần suất truy vấn, SLO, quyền bảo toàn dữ liệu và chi phí ghi**. Tránh đưa kết luận từ một tuần quan sát không chứa kỳ cao điểm hoặc kỳ báo cáo.

## 7. Transaction log: vai trò và vòng đời

Transaction log ghi thông tin thay đổi để Neo4j phục vụ **durability/recovery** và những cơ chế phối hợp khác khi được hỗ trợ. Nó liên quan trực tiếp đến:

- Khôi phục trạng thái sau crash hoặc restart bất thường.
- Quản lý tiến trình giao dịch và khả năng áp dụng thay đổi.
- Backup/restore và nhu cầu giữ lịch sử phục hồi theo tính năng và kiến trúc.
- Trong cluster, nhu cầu catch-up/sao chép phụ thuộc trạng thái các thành viên và cách Neo4j lưu/giữ dữ liệu; không tự lấy một policy từ single instance áp nguyên xi cho cluster.

### 7.1. Rotation và retention là hai việc khác nhau

**Rotation** tạo tệp log mới theo chính sách (ví dụ ngưỡng kích thước của tệp). **Retention/pruning** quyết định tệp cũ được phép giữ lại/xóa theo chính sách và những ràng buộc an toàn của engine.

~~~text
Transaction commits
       |
       v
 tx-log-file-N      (đang ghi)
       |
       +--- rotation --->
       |
 tx-log-file-N+1    (đang ghi)
       |
  các file cũ
       |
 retention / safe pruning
       |
  có thể xóa khi engine cho phép
~~~

Vì vậy:

- Rotation diễn ra **không đồng nghĩa** disk usage transaction log sẽ giảm ngay.
- Retention đặt ngắn hơn **không đảm bảo** mọi file cũ bị xóa ngay thời điểm cấu hình thay đổi.
- Giữ nhiều transaction logs hơn hỗ trợ một số kịch bản phục hồi/catch-up nhưng tăng nhu cầu đĩa.
- Chính sách quá ngắn có thể làm giảm khả năng phục hồi từ nguồn log hoặc buộc phải sử dụng lại backup/snapshot theo kiến trúc.

**Không xóa, đổi tên hoặc nén tệp transaction log đang do Neo4j quản lý bằng thao tác filesystem.** Điều đó có thể khiến database không khởi động, không phục hồi, mất khả năng catch-up hoặc làm hỏng chuỗi log cần thiết.

### 7.2. Xem setting hiện hành

Với phiên bản có `SHOW SETTINGS` và tài khoản có quyền:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name STARTS WITH 'db.tx_log.'
RETURN name, value
ORDER BY name;
~~~

Những dòng Neo4j hiện đại có các setting tương ứng với **rotation size** và **rotation retention policy** (ví dụ `db.tx_log.rotation.size` và `db.tx_log.rotation.retention_policy`). Bản cũ có thể dùng tiền tố khác. Nếu setting không xuất hiện, kiểm tra tài liệu đúng phiên bản và quyền; không tự kết luận rằng retention bị tắt.

Một ví dụ định dạng chính sách trong tài liệu cấu hình của các dòng hỗ trợ:

~~~properties
# Ví dụ học tập: CHƯA phải giá trị khuyến nghị cho production.
db.tx_log.rotation.retention_policy=7 days
~~~

Giá trị `7 days` là minh họa cú pháp chính sách. **Không có số ngày giữ log đúng cho mọi hệ thống.** Quyết định phải xét backup, mục tiêu khôi phục (RPO/RTO), write rate, downtime dài nhất của các thành viên cần catch-up, dung lượng đĩa và yêu cầu vận hành.

Không suy ra rằng chỉnh setting động có hiệu lực ngay trên mọi thành viên cluster hoặc tồn tại sau restart; kiểm tra cơ chế cập nhật, mức động/tĩnh và điểm áp dụng thực tế.

### 7.3. Tại sao transaction log phình to?

| Tình huống | Điều cần xác minh |
| --- | --- |
| Import, backfill hoặc job update số lượng lớn | Tốc độ ghi và byte log tăng có đúng cửa sổ import? |
| Các transaction rất lớn | Batch có kích thước hợp lý hay một transaction kéo dài quá lâu? |
| Chính sách retention giữ lâu | Dung lượng log dự kiến có khớp write rate và số ngày giữ? |
| Pruning chưa tiến hành hoặc đang bị trì hoãn | Có điều kiện recovery/backup/cluster cần giữ log, trạng thái checkpoint hay lỗi hệ thống? |
| Server/volume gần hết không gian | File system có thể ghi log mới và checkpoint an toàn không? |
| Tăng trưởng không rõ lý do | Có job ghi lặp, retry sai, batch bất thường hoặc ứng dụng mới tạo nhiều cập nhật hơn? |

Không coi mọi trường hợp “log nhiều” là lỗi. Trong quá trình nạp dữ liệu đã được phê duyệt, log tăng nhanh có thể hoàn toàn dự kiến; vấn đề là **đỉnh nhu cầu có được dành đủ headroom và trở lại nhịp ổn định sau job hay không**.

## 8. Kiểm tra transaction và các yếu tố vận hành liên quan

Với tài khoản quản trị/giám sát được cấp phép theo phiên bản:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, database, username, elapsedTime, status
RETURN transactionId, database, username,
       elapsedTime, status
ORDER BY elapsedTime DESC
LIMIT 20;
~~~

Lệnh có thể hỗ trợ điều tra **transaction tồn tại lâu**, nhưng không phải công cụ đo tổng kích thước transaction log. Trường được hiển thị và quyền xem transaction thay đổi theo Neo4j. Không log thô `currentQuery` hoặc parameter nếu có nguy cơ chứa dữ liệu nhạy cảm.

Các chỉ số phụ trợ đáng theo dõi:

- Số transaction đang hoạt động, commit/rollback theo thời gian.
- Thời gian transaction kéo dài và tình trạng wait/lock nếu metric hỗ trợ.
- Tốc độ append transaction log, tốc độ rotation và khoảng thời gian giữa các lần pruning nếu có nguồn tin cậy.
- Thời gian/checkpoint, thời gian backup và trạng thái backup gần nhất.
- Trong cluster, lag/catch-up, trạng thái thành viên và rủi ro thành viên dừng quá lâu so với chuỗi log còn giữ.
- Disk latency, fsync/write latency, IOPS và disk free trên volume chứa log.

Một transaction lâu không nhất thiết là lý do duy nhất ngăn pruning; cần kiểm tra chính xác thông tin và log của phiên bản đang dùng. Không vội `TERMINATE TRANSACTIONS` trên production chỉ vì thấy một transaction dài: nó có thể là job nghiệp vụ đang thực hiện và dừng giữa chừng có thể làm trễ một quá trình quan trọng.

## 9. Tính tốc độ tăng và dự báo hết dung lượng

Một dashboard hữu ích không chỉ hiển thị “còn 20 GiB”. Nó phải cho biết **20 GiB đó đủ trong bao lâu với tốc độ tăng thực tế và các đỉnh tải dự kiến**.

Giả sử:

- Volume dành cho store và transaction log còn **120 GiB**.
- Chọn giữ một **quỹ dự phòng vận hành 40 GiB** để database, backup/checkpoint, log và hệ điều hành vẫn có không gian hoạt động.
- Trong giai đoạn gần đây, mức sử dụng tăng ròng trung bình **8 GiB/ngày**.

Dung lượng có thể dùng trước khi chạm quỹ dự phòng là `120 - 40 = 80 GiB`. Với tốc độ giả định không đổi, thời gian đến ngưỡng dự phòng khoảng `80 / 8 = 10 ngày`. Đây là **ví dụ**, không phải cam kết hệ thống có thể chạy thêm đúng 10 ngày; hoạt động import, index build, snapshot và thay đổi retention có thể tạo đỉnh đột xuất.

### 9.1. Công thức theo cửa sổ đo

Với hai lần đo đủ tin cậy:

\[
\text{growthBytesPerDay} =
\frac{\text{usedBytes}_{t_2}-\text{usedBytes}_{t_1}}
{t_2-t_1\text{ (ngày)}}.
\]

Với tốc độ tăng ròng dương và có quỹ dự phòng:

\[
\text{daysToHeadroom} \approx
\frac{\text{freeBytes}-\text{reserveBytes}}
{\text{growthBytesPerDay}}.
\]

Nếu tốc độ tăng bằng 0 hoặc âm, không chia cho 0 hay báo “vô hạn ngày” mà nên nêu rằng phép ngoại suy hiện tại **không ước lượng được thời điểm hết dung lượng**. Nếu `freeBytes <= reserveBytes`, hệ thống đã ở vùng cảnh báo cần xử lý.

### 9.2. Đo tăng trưởng theo nhiều cửa sổ

| Cửa sổ | Dùng để phát hiện | Rủi ro nếu chỉ nhìn cửa sổ này |
| --- | --- | --- |
| 5–15 phút | Burst ghi dữ liệu, tăng log bất thường, đỉnh I/O. | Nhạy với biến động ngắn hạn, dễ báo giả. |
| 24 giờ | Tăng ròng hàng ngày, job đêm và chu kỳ backup. | Chưa đại diện một tuần hoặc kỳ báo cáo. |
| 7 ngày | Mẫu theo ngày trong tuần, xu thế tăng trưởng. | Bỏ sót thời điểm có sự kiện đặc biệt hàng tháng. |
| 30–90 ngày | Dự báo dung lượng/ngân sách và khuynh hướng lâu dài. | Có thể phản ứng chậm với lỗi mới phát sinh. |

Nên đo **delta riêng** cho store, index và transaction log. Ví dụ tổng disk usage tăng 100 GiB sau tạo vector index khác hoàn toàn với transaction log tăng 100 GiB do replay job. Cách xử lý và rủi ro cũng khác nhau.

**Dự báo cần bao gồm đỉnh tải**: trước khi import 500 GiB dữ liệu mới, phải ước lượng cả data, index, transaction logs, overhead population, backup tạm và phần dự phòng; không chỉ xét lượng node dự kiến.

## 10. Dashboard tối thiểu cho Neo4j

Một dashboard vận hành nên có các biểu đồ bên dưới, phân nhãn theo **database, instance, cluster/region và volume** khi dữ liệu hỗ trợ:

| Nhóm | Biểu đồ/chỉ số | Câu hỏi cần trả lời |
| --- | --- | --- |
| Dung lượng | Used/free bytes từng volume; phần trăm sử dụng | Đang gần giới hạn nào? |
| Tăng trưởng | Store size theo ngày, tốc độ tăng GiB/ngày | Nhu cầu tăng đều hay đang có burst? |
| Index | Tổng kích thước index, trạng thái `ONLINE/POPULATING/FAILED` | Có index không phục vụ được hoặc đang xây quá lâu? |
| Transaction log | Tổng log bytes, rotation/pruning và tốc độ log tăng khi có nguồn đo | Log đang giữ theo dự kiến hay tăng không kiểm soát? |
| Giao dịch | Commit/rollback rate, long transactions, lock wait | Mức ghi hay transaction dài có bất thường? |
| Tài nguyên | Disk latency, CPU, memory/page-cache pressure | Nút thắt có phải I/O hoặc bộ nhớ chứ không phải dung lượng? |
| Sẵn sàng | Database status, cluster health, thành viên lag | Mọi bản sao còn phục vụ và bắt kịp thay đổi? |
| Phục hồi | Backup gần nhất thành công, tuổi backup, restore drill | Có đường phục hồi đáng tin cậy khi sự cố xảy ra? |
| Thu thập | Scrape success, collector lag, dữ liệu metric quá cũ | Chỉ số “bình thường” có phải do collector đã dừng? |

**Phải theo dõi tình trạng thiếu dữ liệu giám sát.** Một đường biểu đồ không cập nhật có thể là exporter bị lỗi, không phải database không tăng dung lượng.

### 10.1. Ví dụ bảng số liệu mỗi lần thu thập

~~~text
timestamp_utc | database | instance | store_bytes |
index_bytes | tx_log_bytes | volume_free_bytes |
db_status | index_failed_count | backup_age_hours
~~~

Đây là **schema nội bộ minh họa**, không phải đầu ra trực tiếp của Neo4j. Các thành phần lấy từ nhiều nguồn cần ghi cả `source` và thời gian đo; không trộn byte size của instance A với disk free của instance B rồi dự báo sai.

### 10.2. Quan sát từ Java Driver và Spring Data Neo4j

Trong ứng dụng Java, nên theo dõi thêm:

- Thời gian request và p95/p99 của các query Cypher quan trọng.
- Tốc độ mutation/import, số bản ghi cập nhật, thời gian batch commit.
- Số lỗi `TransientException`, timeout và retry theo loại nguyên nhân.
- Connection pool, thời gian chờ lấy connection nếu driver/instrumentation hỗ trợ.
- Độ trễ giữa dữ liệu nguồn và lúc ghi vào graph với pipeline CDC.

Đây là **metrics ứng dụng bổ sung**, không thay thế disk metrics từ Neo4j hoặc hạ tầng. Đừng cấp đặc quyền quản trị cho mọi instance ứng dụng chỉ để gọi `SHOW INDEXES`; hãy dùng một tài khoản/cơ chế giám sát tách biệt có quyền tối thiểu.

Một ví dụ Java Driver đọc trạng thái index theo quyền monitor:

~~~java
import java.util.List;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jIndexMonitor {
    private final Driver monitoringDriver;

    public Neo4jIndexMonitor(Driver monitoringDriver) {
        this.monitoringDriver = monitoringDriver;
    }

    public List<Record> indexStates() {
        try (Session session = monitoringDriver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.run("""
                SHOW INDEXES
                YIELD name, type, state, populationPercent
                RETURN name, type, state, populationPercent
                ORDER BY name
                """).list();
        }
    }
}
~~~

Đây là mẫu đọc cho Java Driver dòng hiện đại. Trong sản phẩm thật, hãy ánh xạ sang DTO/metrics không chứa thông tin nhạy cảm, định nghĩa database mục tiêu, cấp quyền đúng, kiểm tra schema của `SHOW INDEXES` và không giữ kết nối theo một `Session` dùng chung giữa các thread.

## 11. Ngưỡng cảnh báo: đủ sớm để hành động

Ngưỡng chỉ mang tính **định hướng**; phải hiệu chỉnh theo khối lượng ghi, tốc độ tăng, nguồn dự phòng, SLA, kiểu storage và chi phí mở rộng.

| Cảnh báo | Điều kiện minh họa | Hành động đầu tiên |
| --- | --- | --- |
| Disk warning | Free space dưới 25% **và** xu hướng còn giảm. | Xác định volume nào và phần store/index/log/backup đang tăng. |
| Dự báo hết headroom | `daysToHeadroom < 7` theo cửa sổ đáng tin cậy. | Lên kế hoạch tăng dung lượng/giảm tăng trưởng trước sự cố. |
| Disk critical | Free space dưới quỹ dự phòng tối thiểu được phê duyệt. | Kích hoạt runbook sự cố, bảo vệ ghi và khả năng recovery. |
| Index FAILED | Số index `FAILED` lớn hơn 0. | Xác định index ảnh hưởng truy vấn/constraint nào và thu thập nguyên nhân. |
| POPULATING kéo dài | Thời gian tạo index vượt baseline theo loại và kích thước dữ liệu. | Kiểm tra tiến độ, disk/CPU/I/O và lỗi population. |
| Transaction log tăng bất thường | Tốc độ tăng log vượt baseline đã tính, không trùng job được phê duyệt. | So sánh write rate, retention, pruning và trạng thái cluster/backup. |
| Backup quá hạn | Tuổi backup thành công vượt RPO/chính sách vận hành. | Kiểm tra pipeline backup, dung lượng và khả năng restore. |
| Collector mất dữ liệu | Metric thiếu trong nhiều chu kỳ scrape. | Xử lý giám sát, không suy ra database “ổn định”. |

Ví dụ `25%` hay `7 ngày` **không phải giá trị mặc định hoặc khuyến nghị chính thức cho mọi hệ thống Neo4j**. Một volume 100 TiB còn 10% có thể dư rất nhiều tuyệt đối; ngược lại volume 20 GiB còn 30% vẫn có thể không đủ cho một import đã lên lịch. Nên kết hợp **phần trăm, số byte tuyệt đối, đỉnh workload và thời gian đến ngưỡng**.

### 11.1. Cảnh báo có ngữ cảnh và chống nhiễu

Một quy tắc hợp lý nên bao gồm:

- Thời gian duy trì vượt ngưỡng để tránh cảnh báo từ một mẫu bị nhiễu.
- Ngoại lệ/cửa sổ đã lên lịch cho index build hoặc bulk import, **nhưng không tắt cảnh báo disk critical**.
- Mức độ theo tác động: index tìm kiếm của API chính lỗi khác với index phục vụ báo cáo phụ.
- Nhãn instance/database/volume và liên kết runbook cụ thể.
- Escalation nếu cảnh báo không được xử lý, và cảnh báo riêng cho monitoring pipeline bị mất.

## 12. Runbook A — Volume gần hết dung lượng

**Triệu chứng:** disk free giảm nhanh, transaction lỗi, index không hoàn tất, hoặc thông lượng ghi chậm bất thường.

### 12.1. Xác nhận và khoanh vùng

1. Xác định **volume, instance và database** bị ảnh hưởng; kiểm tra còn bao nhiêu byte thực sự khả dụng.
2. So sánh xu hướng `storeBytes`, `indexBytes`, `txLogBytes` và các dữ liệu khác cùng ổ (backup, OS logs, snapshot).
3. Xác nhận thời điểm bắt đầu tăng, có trùng import, migration, dựng index hoặc tải bất thường không.
4. Kiểm tra trạng thái database/cluster, lỗi disk và thời điểm backup gần nhất.
5. Đánh giá khoảng thời gian đến quỹ dự phòng với **tốc độ tăng gần đây**, không chỉ trung bình tháng.

### 12.2. Hành động ưu tiên an toàn

- Nếu hạ tầng cho phép, **mở rộng volume/quota** theo quy trình đã được kiểm chứng, phối hợp giữa storage và database.
- Điều tiết hoặc tạm dừng các job import/backfill không thiết yếu để giảm tốc độ ghi, có tính đến yêu cầu nghiệp vụ và thứ tự xử lý sự kiện.
- Dọn các tệp **ngoài vùng dữ liệu Neo4j** chỉ khi xác định đúng chủ sở hữu và có quy trình xóa an toàn; ví dụ archive log/backup đã hết retention theo chính sách.
- Kiểm tra backup gần nhất và khả năng restore; không tạo một thay đổi rủi ro lớn chỉ để lấy thêm vài GB.
- Nếu dịch vụ quản lý, thực hiện scaling/request support theo cơ chế Aura hoặc nhà cung cấp tương ứng.

**Không thực hiện:** xóa file store, index hoặc transaction log; dừng tiến trình bằng cách bất thường để “giải phóng”; thay retention xuống mức quá ngắn mà chưa tính recovery/backup/cluster; hoặc `DETACH DELETE` hàng triệu node mà không có kế hoạch giao dịch, index và log.

### 12.3. Khi đã qua ngưỡng nguy hiểm

Nếu database bắt đầu từ chối ghi hoặc volume quá đầy:

1. Kích hoạt quy trình incident, điều tiết request ghi tại tầng ứng dụng.
2. Giữ các tệp database/log nguyên vẹn và liên hệ người vận hành có quyền xử lý storage.
3. Đảm bảo vùng đĩa cần cho recovery/checkpoint được bảo vệ theo hướng dẫn của Neo4j.
4. Sau khi tăng headroom, xác nhận database online, giao dịch mới thành công, index không FAILED và backup/replication bình thường.
5. Điều tra nguyên nhân gốc và cập nhật dự báo/cảnh báo để tránh lặp lại.

Không tuyên bố khôi phục chỉ vì `df` lại báo còn trống: ứng dụng và Neo4j cần được kiểm tra về **tính nhất quán, khả năng đọc/ghi và tiến trình backup/cluster**.

## 13. Runbook B — Index FAILED hoặc population không tiến triển

**Triệu chứng:** `SHOW INDEXES` báo `FAILED`, `POPULATING` rất lâu hoặc truy vấn tăng DB Hits/latency bất thường sau migration.

1. Ghi nhận tên, loại, label/type, property, trạng thái và phần trăm xây index.
2. Đọc thông báo lỗi khả dụng và log hệ thống theo quyền; không giả định nguyên nhân chỉ từ `FAILED`.
3. Kiểm tra **dung lượng đĩa** và I/O lúc index population; có thể là vấn đề tài nguyên chứ không phải Cypher.
4. Xác định index có phục vụ **constraint** hoặc truy vấn cốt lõi không; xem `EXPLAIN`/`PROFILE` trên truy vấn đọc an toàn.
5. Chọn biện pháp được hỗ trợ theo phiên bản: sửa điều kiện dữ liệu/cấu hình hoặc rebuild/recreate đúng cửa sổ thay đổi.
6. Chừa đủ headroom cho quá trình xây mới; theo dõi hệ thống trong lúc thay đổi.
7. Sau khi index `ONLINE`, kiểm tra truy vấn nghiệp vụ, uniqueness/constraint và độ trễ trên dữ liệu đại diện.

**Không** drop một index mà chưa xác minh nó có gắn với uniqueness constraint. **Không** tạo lại liên tục trong khi volume đang thiếu chỗ hoặc nguyên nhân lỗi chưa được xử lý.

## 14. Runbook C — Transaction log tăng bất thường

**Triệu chứng:** dung lượng transaction log tăng liên tục, rotation diễn ra nhanh hơn bình thường hoặc phần log chiếm hầu hết volume.

### 14.1. Phân biệt tăng có kế hoạch và tăng bất thường

| Quan sát | Giả thuyết đầu tiên | Kiểm chứng |
| --- | --- | --- |
| Log tăng đúng giờ nhập dữ liệu | Bulk import/backfill đã lên lịch. | Đối chiếu job, write rate và lượng ghi. |
| Log tăng sau thay đổi mã ứng dụng | Retry/loop cập nhật, write amplification. | So sánh phiên bản deploy, lỗi và số transaction. |
| Log nhiều dù tốc độ ghi hiện thấp | Retention giữ lâu, pruning bị trì hoãn hoặc logs phát sinh trước đó còn tồn. | Kiểm tra setting, mốc rotation/pruning và tình trạng recovery/backup. |
| Log tăng cùng replica/catch-up lag | Thành viên cluster tụt hậu có thể cần log để bắt kịp theo cơ chế deployment. | Kiểm tra health/catch-up và hướng dẫn vận hành cluster phiên bản đó. |
| Log tăng, database chậm/timeout | Disk I/O, transaction quá lớn hoặc vấn đề tài nguyên. | Theo dõi disk latency, transaction duration và ghi log. |

### 14.2. Trình tự khắc phục

1. Xác định đường dẫn volume transaction log và tốc độ tăng thực tế, tránh nhầm với `query.log`.
2. Ghi lại trạng thái database, phiên bản, các setting rotation/retention hiện hành.
3. Xác minh import/replay/deploy gần đây, transaction dài và lượng ghi không mong muốn.
4. Kiểm tra backup/recovery/cluster catch-up và những điều kiện khiến pruning không giải phóng tệp như kỳ vọng.
5. Đảm bảo **không gian đĩa an toàn trước**, bằng mở rộng hoặc điều tiết ghi nếu cần.
6. Chỉ thay retention theo chính sách đã đánh giá RPO/RTO, backup và cluster, bằng cơ chế cấu hình được hỗ trợ.
7. Quan sát việc log ổn định sau chu kỳ thích hợp và xác nhận restore/catch-up vẫn đạt.

**Không xóa file transaction log thủ công**, kể cả file có timestamp cũ; đừng dùng tác vụ OS để sửa chuỗi log của database. Nếu retention đã phù hợp nhưng log vẫn không được dọn, cần điều tra nguyên nhân thay vì ép xóa.

## 15. Đặt giám sát cạnh backup và chiến lược phục hồi

Dung lượng đủ ở thời điểm hiện tại chưa đồng nghĩa hệ thống có thể phục hồi sau sự cố. Cần theo dõi:

| Yếu tố | Câu hỏi |
| --- | --- |
| Tần suất backup và RPO | Nếu mất database bây giờ, có thể mất tối đa bao nhiêu dữ liệu? |
| Tốc độ restore và RTO | Thử restore toàn bộ có phù hợp thời gian khôi phục cam kết không? |
| Dung lượng backup | Backup có chiếm chung volume với store/log và đẩy hệ thống vào nguy cơ đầy đĩa không? |
| Transaction log retention | Có đủ lịch sử cần cho quy trình phục hồi/catch-up đã thiết kế không? |
| Cluster lag | Thành viên bị gián đoạn có thể bắt kịp trong giới hạn log/tài nguyên hiện có không? |
| Index rebuild sau restore | Dung lượng và thời gian xây index có nằm trong kế hoạch khôi phục không? |

Trên một số hình thức triển khai, backup online, full/incremental backup hoặc point-in-time recovery có điều kiện và công cụ riêng. **Không hứa khôi phục đến một thời điểm bất kỳ chỉ vì còn tệp transaction log.** Khả năng restore phải được chứng minh bằng tài liệu đúng version/edition và **thực hành khôi phục có kiểm tra tính nhất quán**.

### 15.1. Khi xóa dữ liệu không làm store giảm ngay

Neo4j có thể tái sử dụng những vùng lưu trữ đã giải phóng sau khi xóa node/relationship, thay vì ngay lập tức thu nhỏ mọi tệp store vật lý. Vì vậy:

- Số node logic giảm **không bảo đảm** `du` của store giảm ngay.
- Xóa hàng triệu node cũng phát sinh các transaction/log và cập nhật index; có thể làm **dung lượng tạm thời tăng**.
- Muốn giảm kích thước vật lý có thể cần quy trình tái cấu trúc/export/import/rebuild được hỗ trợ, tùy phiên bản và mục tiêu.
- Đừng khởi động “dọn dữ liệu” khối lượng lớn khi disk đã gần đầy nếu chưa ước lượng peak transaction log và tài nguyên cần thiết.

Giám sát cần phân biệt **khả năng tái sử dụng không gian bên trong store** với **free bytes của filesystem**. Hai loại không gian không đồng nhất.

## 16. Tình huống phân tích tổng hợp

Giả sử ngày thứ hai hệ thống có:

| Chỉ số | Giá trị minh họa |
| --- | ---: |
| Data store | 280 GiB |
| Index size | 55 GiB |
| Transaction logs | 22 GiB |
| Free space của volume dữ liệu | 160 GiB |

Ngày thứ ba, sau một import:

| Chỉ số | Giá trị minh họa |
| --- | ---: |
| Data store | 350 GiB |
| Index size | 76 GiB |
| Transaction logs | 96 GiB |
| Free space của volume dữ liệu | 15 GiB |

Đây là **số giả định**; bảng dùng để luyện phân tích. Ngoài việc free space giảm mạnh, transaction logs tăng rất nhiều và index cũng tăng do import. Không thể kết luận “lỗi transaction log retention” chỉ từ hai snapshot, bởi log có thể tăng đúng khối lượng import.

Thứ tự điều tra hợp lý:

1. Xác minh các chỉ số có cùng nguồn đo, cùng instance, cùng volume và không cộng đúp store/index.
2. Kiểm tra import còn chạy không, write rate và dự báo thời gian hết headroom.
3. Theo dõi status của các index vừa tạo/populate.
4. Kiểm tra policy rotation/retention, trạng thái backup và replication/catch-up nếu có.
5. Vì chỉ còn 15 GiB, cân nhắc kích hoạt runbook disk capacity trước khi chạy thêm những bước tốn đĩa như rebuild index hoặc xóa hàng loạt.
6. Sau khi ổn định, lấy chuỗi thời gian chi tiết hơn để phân biệt đỉnh tăng tạm thời với xu hướng dài hạn.

Một kết luận vận hành hợp lệ cần kèm **bằng chứng và tác động**: index nào, volume nào, khối lượng ghi từ job nào và khả năng recovery còn đúng chính sách hay không.

## 17. Kiểm thử quy trình giám sát

Không cần gây đầy đĩa hoặc xóa log thật để chứng minh dashboard hoạt động. Có thể kiểm thử bằng môi trường cô lập, dữ liệu giả, bản ghi metric mô phỏng và một số thay đổi schema an toàn.

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| M01 | Database online nhưng free space giảm dưới ngưỡng. | Cảnh báo storage phát ra dù `SHOW DATABASES` vẫn ONLINE. |
| M02 | Một index đang POPULATING. | Dashboard ghi nhận state/percent và không đánh dấu đã sẵn sàng. |
| M03 | Metric index FAILED được giả lập trong collector/test. | Cảnh báo kèm tên index, database, instance và runbook. |
| M04 | Bulk import test làm transaction log tăng. | Thấy tăng trưởng log, liên kết tới job và không tự coi là lỗi nếu nằm trong kế hoạch. |
| M05 | Collector metric bị dừng. | Có cảnh báo thiếu dữ liệu; biểu đồ không âm thầm coi mẫu cũ là hiện tại. |
| M06 | Backup job test thất bại. | Cảnh báo tuổi backup vượt ngưỡng và báo rủi ro RPO. |
| M07 | Data store tăng nhưng count node gần như không đổi. | Điều tra property/relationship/index, không suy luận chỉ từ node count. |
| M08 | Xóa dữ liệu test nhưng store file không thu nhỏ. | Dashboard phân biệt logical count với physical bytes. |
| M09 | Chạy query sử dụng index và query không dùng index trên fixture. | `EXPLAIN`/`PROFILE` giúp phân biệt query plan; không đánh giá chỉ qua index ONLINE. |
| M10 | Giả lập 1 instance trong cluster bị mất scrape. | Không tổng hợp sai hoặc bỏ sót free space riêng của instance đó. |
| M11 | Tốc độ tăng cao trong 15 phút nhưng ổn định 7 ngày. | Cảnh báo burst và dự báo được phân loại riêng, tránh kết luận thiếu capacity dài hạn từ một đỉnh ngắn. |
| M12 | Log/tracing bị đặt tham số nhạy cảm ở fixture. | Monitoring không đưa dữ liệu nhạy cảm lên dashboard hoặc alert. |

### 17.1. Đoạn script kiểm tra khái niệm về ngưỡng

Đây là **pseudocode**, không phải tên metric hoặc API Neo4j:

~~~text
if no_recent_samples(instance, volume):
    alert("MONITORING_DATA_MISSING")

if free_bytes < reserved_bytes:
    alert("DISK_CRITICAL")

growth = moving_growth_bytes_per_day(used_bytes, window="7d")
if growth > 0:
    days_to_reserve = max(0, free_bytes - reserved_bytes) / growth
    if days_to_reserve < planning_days:
        alert("DISK_CAPACITY_PLANNING")

if any(index.state == "FAILED"):
    alert("NEO4J_INDEX_FAILED")

if tx_log_growth_unexpected and not approved_bulk_job:
    alert("NEO4J_TX_LOG_GROWTH")
~~~

Mỗi nhánh cảnh báo cần sử dụng số liệu **cùng volume, đủ mới và có đơn vị rõ ràng**. `approved_bulk_job` chỉ là ngữ cảnh cho phân loại cảnh báo, không được làm tắt các cảnh báo thiếu đĩa hoặc database unavailable.

## 18. Sai lầm thường gặp

| Nhận định sai | Thực tế cần nhớ |
| --- | --- |
| “Node count không tăng thì database size phải ổn định.” | Property lớn, relationship, index và log vẫn có thể tăng. |
| “Index ONLINE thì query chắc chắn nhanh.” | Query có thể không dùng index hoặc tốn phần lớn chi phí ở traversal/tổng hợp. |
| “Transaction log chính là query log.” | Transaction log phục vụ giao dịch/phục hồi; query log phục vụ quan sát câu lệnh. |
| “Log rotate rồi phải lập tức giảm byte trên đĩa.” | Rotation tách tệp; pruning còn phụ thuộc retention và điều kiện an toàn. |
| “Xóa file tx log cũ là cách khắc phục đầy đĩa.” | Có thể phá hỏng recovery, backup hoặc catch-up. Không can thiệp file thủ công. |
| “Xóa node sẽ làm `df` tăng free space tương ứng.” | Store có thể tái sử dụng không gian nội bộ, file vật lý chưa thu nhỏ; xóa còn sinh log. |
| “Cộng store bytes và index bytes luôn đúng.” | Một metric store có thể đã bao gồm index; cần định nghĩa nguồn đo. |
| “Dùng ngưỡng 80% disk cho mọi hệ thống.” | Cần absolute headroom, growth rate, kích thước volume và workload đỉnh. |
| “Snapshot dashboard hôm nay đủ dự báo sáu tháng.” | Cần chuỗi thời gian đủ dài, tính seasonality và kế hoạch import/index. |
| “Aura cũng đọc thư mục data bằng SSH.” | Dịch vụ được quản lý giới hạn quyền OS; dùng nguồn metrics/console hỗ trợ. |
| “Đã backup thành công thì chắc chắn restore được.” | Phải kiểm tra định kỳ việc restore và tính nhất quán. |
| “Không có điểm trên biểu đồ nghĩa là metric bằng 0.” | Có thể exporter/collector mất kết nối hoặc quyền đọc bị thu hồi. |
| “Một cluster có ba replica nên nhân cả ba khi đánh giá database logic size.” | Cần tách dung lượng logic và chi phí vật lý từng replica. |

## 19. Bài tập áp dụng

**Bài 1 — Phân loại tài nguyên.** Một database Neo4j dùng 90 GiB data store, 28 GiB index và 12 GiB transaction log theo các nguồn báo cáo khác nhau. Hãy trình bày khi nào phép cộng thành 130 GiB hợp lệ, khi nào gây đếm trùng. Bổ sung cách đo free bytes ở filesystem.

**Bài 2 — Trạng thái index.** Trên database thực hành, tạo uniqueness constraint cho `MonDemoCustomer(tenantId, customerId)`, chạy `SHOW INDEXES`, xác định index phục vụ constraint và dùng `EXPLAIN`/`PROFILE` để xác minh một truy vấn tìm theo hai khóa. Giải thích vì sao không nên drop index đó chỉ vì thống kê đọc thấp.

**Bài 3 — Dự báo dung lượng.** Volume còn 200 GiB, quy định cần giữ tối thiểu 50 GiB, và mức tăng ròng trung bình là 12 GiB/ngày. Tính số ngày tới quỹ dự phòng theo công thức mục 9. Sau đó giả lập một index rebuild cần thêm 80 GiB trong một ngày và giải thích vì sao dự báo trung bình có thể sai.

**Bài 4 — Log growth sau import.** Một job nạp dữ liệu vào Neo4j khiến transaction log tăng 40 GiB sau ba giờ. Viết checklist điều tra để phân biệt tăng trưởng dự kiến, transaction lỗi retry, pruning bị trì hoãn và thiếu headroom; nêu hành động **không được** thực hiện.

**Bài 5 — Cảnh báo cluster.** Một cluster có ba instance; hai instance còn 35% disk free, instance thứ ba chỉ còn 7%. Hãy thiết kế dashboard và alert để không bỏ qua rủi ro chỉ vì trung bình cả cluster vẫn cao.

**Bài 6 — Chạy lại backup.** Giả sử backup gần nhất đã quá hạn RPO và transaction log retention đang được đề xuất giảm từ 7 ngày xuống 1 ngày. Những điều kiện gì về backup, restore, catch-up và khối lượng ghi cần xác minh trước khi đổi?

**Bài 7 — Logical vs physical storage.** Xóa 100.000 node trên môi trường test, số node giảm nhưng filesystem free bytes gần như giữ nguyên. Giải thích khác biệt giữa không gian nội bộ có thể tái sử dụng và việc thu nhỏ file store. Nêu vì sao chạy xóa thật trên hệ thống đầy đĩa có thể phản tác dụng.

**Bài 8 — Dữ liệu metric mất mẫu.** Một exporter chỉ còn gửi mẫu mỗi mười phút thay vì mỗi 15 giây, khiến biểu đồ transaction log có những đoạn phẳng giả. Hãy mô tả cách phát hiện, giữ nguyên trạng thái “không đủ dữ liệu” và khôi phục pipeline monitoring mà không tự điền giá trị 0.

## 20. Checklist vận hành

1. **Biết chính xác phạm vi:** database, instance, edition, version, cluster/replica, volume, quota và môi trường.
2. **Phân biệt dung lượng:** store, index, transaction log, backup, server logs; tránh đếm trùng.
3. **Có chuỗi thời gian:** byte dùng/còn, tốc độ tăng theo nhiều cửa sổ, dự báo tới ngưỡng dự phòng.
4. **Theo dõi index:** state, tiến độ population, lỗi, workload và query plan; không xóa index thuộc constraint tùy tiện.
5. **Theo dõi transaction logs:** rotation, retention, write rate, pruning, backup và cluster catch-up theo khả năng của triển khai.
6. **Đủ headroom:** có dự phòng cho import, index build, recovery, peak transaction logs và các tệp khác cùng volume.
7. **Cảnh báo nhiều lớp:** ngưỡng byte/%, thời gian tới ngưỡng, lỗi index, backup và sự cố collector.
8. **Có runbook an toàn:** tuyệt đối không xóa store/index/transaction logs bằng OS để “cứu” database đang chạy.
9. **Kiểm thử khả năng phục hồi:** backup thành công được kiểm chứng bằng restore, có phương án cluster/node thất bại.
10. **Kết nối hiệu năng với capacity:** phân tích `PROFILE`, page cache, I/O, transaction duration cùng bức tranh lưu trữ.
11. **Bảo vệ telemetry:** account giám sát quyền tối thiểu, log/tracing không lộ PII, monitoring pipeline có cảnh báo mất dữ liệu.
12. **Đo lại sau thay đổi:** xác nhận index ONLINE, log growth trở về nhịp dự kiến, disk headroom đủ và query nghiệp vụ vẫn đáp ứng SLO.

**Kết luận:** giám sát dung lượng Neo4j không phải nhìn một con số “database size”. Cần kết hợp **data store, index, transaction log, disk/volume, tốc độ ghi, backup và tình trạng cluster** để hiểu nhu cầu thực tế. `SHOW INDEXES` giúp phát hiện index chưa sẵn sàng; `EXPLAIN`/`PROFILE` giúp kiểm tra hiệu quả; chính sách rotation/retention transaction log phải giữ đúng yêu cầu recovery thay vì dọn tệp thủ công. Một hệ thống giám sát tốt dự báo rủi ro **trước khi hết chỗ**, có cảnh báo thiếu dữ liệu và dẫn đội vận hành tới runbook an toàn.
