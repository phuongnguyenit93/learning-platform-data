# Kiến trúc cụm Neo4j theo phiên bản và edition được sử dụng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **Neo4j Community**, **Neo4j Enterprise tự quản**, các gói **Aura** và tính năng mở rộng chuyên biệt theo phiên bản/giấy phép.
- Giải thích sự thay đổi từ **Core/Read Replica** trong Neo4j 4.4 sang **primary/secondary database allocations** trong Neo4j 5.x và các phiên bản 2025–2026.
- Mô tả cơ chế **writer/leader**, Raft, **quorum**, đồng bộ giữa các primary và sao chép bất đồng bộ tới secondary.
- Chọn topology cho mục tiêu **high availability**, mở rộng đọc hoặc phân tán nhiều database; hiểu vì sao thêm primary **không làm số writer của một database tăng lên**.
- Sử dụng `SHOW DATABASES`, `SHOW SERVERS` và các câu lệnh `CREATE/ALTER DATABASE ... TOPOLOGY` trong môi trường Enterprise được cấp quyền.
- Cấu hình Neo4j Java Driver với **routing READ/WRITE** và **bookmark** khi cần *read-your-writes*.
- Lập kế hoạch cho lỗi một thành viên, mất quorum, bảo trì rolling, sao lưu, phân vùng mạng, theo dõi và kiểm thử khả năng phục hồi.
- Nhận diện **Infinigraph/property sharding** từ Neo4j 2025.12 là khả năng riêng có yêu cầu subscription, không nhầm với cụm Enterprise thông thường.

Bài thuộc chương **Cụm và mở rộng** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Neo4j tổ chức dữ liệu liên kết theo **property graph** (node, relationship, thuộc tính) và dùng **Cypher** cho các truy vấn quan hệ, đường đi. Khi có nhiều ứng dụng Java Driver/Spring Data Neo4j cùng truy cập graph, kiến trúc cụm cần bảo đảm **giao dịch đúng, dữ liệu bền vững và năng lực đọc/ghi** dưới tải hoặc khi một server gặp sự cố.

> **Phạm vi:** Bài sử dụng khái niệm và cú pháp phổ biến của **Neo4j 5.x, 5.26 LTS và các dòng 2025.x/2026.x**. Neo4j 4.4 có kiến trúc/cấu hình khác; các gói Aura có quyền quản trị bị giới hạn. **Không chạy lệnh đổi topology hoặc dừng server trên production** nếu chưa có kế hoạch thay đổi, backup và phương án khôi phục. Đối chiếu với tài liệu chính thức của **đúng version và edition** đang triển khai.

## 1. Cluster giải quyết bài toán nào?

Một server Neo4j đơn lẻ có thể phục vụ cả Cypher READ và WRITE. Khi hệ thống lớn hơn, nhóm vận hành thường có ba mục tiêu:

1. **High availability (HA):** nếu một máy hoặc một availability zone lỗi, hệ thống vẫn có thể phục vụ trong giới hạn chịu lỗi đã thiết kế.
2. **Read scalability:** phân phối truy vấn `MATCH`/traversal/path cho nhiều bản sao database để tăng thông lượng đọc.
3. **Operational scalability:** bổ sung server, phân bố nhiều database, bảo trì/upgrade theo từng thành viên và cô lập workload.

Các mục tiêu này **không giống nhau**:

| Mục tiêu | Cơ chế thường dùng | Không được mặc định |
| --- | --- | --- |
| Chịu lỗi một primary | **Ít nhất ba primary** cho database cần HA ghi | Hai primary đã đủ chịu lỗi một primary |
| Tăng thông lượng READ | Thêm **secondary** hoặc dùng các primary không làm writer để nhận đọc | Secondary có thể nhận WRITE |
| Giảm write latency | Tối ưu query/index, giao dịch và topology/vị trí địa lý | Thêm primary luôn làm WRITE nhanh hơn |
| Chứa nhiều graph độc lập | Nhiều database, allocator phân bố bản sao giữa server | Có một transaction ACID tự động xuyên các database |
| Graph quá lớn so với một host | Scale up, tách workload hoặc cơ chế sharding có điều kiện | Cluster replica mặc định chia nhỏ một graph thành nhiều shard |

**Nhận định cốt lõi:** Cluster tiêu chuẩn sao chép **bản đầy đủ của một database** đến các bản sao được phân bổ. Thêm replica chủ yếu bổ sung **HA và năng lực đọc**, không biến mỗi relationship thành một phần dữ liệu được chia ngẫu nhiên giữa các server.

## 2. Ma trận phiên bản, edition và môi trường

Neo4j thay đổi cách tổ chức cụm theo thời gian. Vì vậy một hướng dẫn ghi “Core server” hay cấu hình `causal_clustering.*` có thể đã lỗi thời đối với hệ thống mới.

| Phiên bản / sản phẩm | Khái niệm cụm | Hỗ trợ/giới hạn |
| --- | --- | --- |
| **Neo4j 4.4 Enterprise** | **Causal Cluster** với **Core servers** và **Read Replicas** | Kiến trúc cũ, không được áp dụng nguyên tệp cấu hình cho 5.x |
| **Neo4j 5.x Enterprise** | Cụm tái thiết kế: **servers và databases tách biệt**, mỗi database có **primary/secondary allocations** | Hỗ trợ quản lý topology của từng database, tự động phân bổ |
| **Neo4j 5.26 LTS Enterprise** | Kiến trúc 5.x, là mốc LTS quan trọng trong lộ trình nâng cấp | Cần theo hướng dẫn upgrade/migration cụ thể |
| **Neo4j 2025.x/2026.x Enterprise** | Tiếp tục mô hình **primary/secondary**, quản trị và tính năng bổ sung theo release | Dùng cú pháp/config đúng bản, không trộn với 4.4 |
| **Neo4j Community** | Triển khai một server database, **không có Enterprise clustering** | Không bật được cụm Enterprise chỉ bằng `neo4j.conf` |
| **AuraDB Business Critical / Virtual Dedicated Cloud** | Dịch vụ managed có **cụm ba node** theo thông tin dịch vụ hiện hành | Nhà cung cấp quản lý nhiều chi tiết cluster và failover |
| **Các gói AuraDB khác** | Có thể dùng kiến trúc **một node** với HA ở tầng hạ tầng | Không giả định người thuê được chọn `TOPOLOGY 3 PRIMARIES` |
| **Infinigraph từ 2025.12** | Khả năng **property sharding** riêng của Neo4j phân tán | **Không nằm trong Enterprise thông thường**; cần subscription riêng, không khả dụng trên Aura theo tài liệu hiện hành |

### Các mốc chuyển đổi cần nhớ

- **Neo4j 4.4 → 5:** tài liệu upgrade gọi rõ **Core → primary database copy**, **Read Replica → secondary database copy**. Đây không chỉ là đổi tên; cluster 5.x có allocator và cách tổ chức riêng, nên cần thiết kế/cấu hình lại thay vì sao chép nguyên bản thiết lập 4.4.
- **Neo4j 5.23:** discovery service v1 bị deprecate, v2 xuất hiện; từ **2025.01**, v1 đã bị loại bỏ. Cụm chạy bản cũ cần rà soát discovery trước khi nâng cấp.
- **Từ 2025.01:** server chuyển sang **Calendar Versioning (CalVer)** dạng `YYYY.MM.PATCH`; không nên suy luận tương thích chỉ từ tiền tố `5.`.
- **Từ 2025.12:** **Infinigraph property sharding** được giới thiệu như một khả năng khác với replication thông thường và có giấy phép riêng.

Nguồn: [Neo4j clustering introduction](https://neo4j.com/docs/operations-manual/current/clustering/introduction/), [Breaking changes 4.4 → 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/breaking-changes/), [Versioning/upgrade guide](https://neo4j.com/docs/upgrade-migration-guide/current/), [Infinigraph overview](https://neo4j.com/docs/operations-manual/current/scalability/sharded-property-databases/overview/).

### 2.1. Kiểm tra bản đang chạy

Trên môi trường có quyền phù hợp:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Không dùng **version của Neo4j Browser**, **version của Java Driver** hay việc xuất hiện một procedure nào đó để suy ra edition DBMS. Với Aura, xem **tên dịch vụ và gói** ở giao diện quản trị; một số lệnh DBMS có thể không được cấp cho tài khoản tenant.

## 3. Kiến trúc 5.x/2025–2026: server không đồng nhất với database role

Trong Neo4j Enterprise cluster hiện đại:

- **Server** là một tiến trình Neo4j trên máy vật lý, VM hoặc container.
- **Database** là tập graph và metadata được tổ chức riêng theo tên; một cluster có thể phục vụ nhiều database.
- **Allocation** là một bản sao của một database được đặt lên một server.
- **Primary**/**secondary** là **vai trò của bản sao database**, không phải nhãn cố định cho cả server.
- **Writer/leader** là một primary được bầu làm nơi điều phối ghi **cho database đó**.
- **Allocator** phân bố database allocations trên những server thỏa ràng buộc.

Một server có thể giữ **primary của database A** và **secondary của database B** nếu cấu hình cho phép. Hai database có thể chọn **hai writer khác nhau**.

~~~mermaid
flowchart TB
    APP["Ứng dụng Java / Spring"] --> R["Routing driver"]
    R --> DB1["Database orders<br/>quorum riêng"]
    R --> DB2["Database network<br/>quorum riêng"]
    subgraph S["Pool server Enterprise"]
      A["Server A<br/>orders: primary/writer<br/>network: secondary"]
      B["Server B<br/>orders: primary/follower<br/>network: primary/writer"]
      C["Server C<br/>orders: primary/follower<br/>network: primary/follower"]
      D["Server D<br/>orders: secondary<br/>network: primary/follower"]
    end
    DB1 --> A
    DB1 --> B
    DB1 --> C
    DB1 --> D
    DB2 --> A
    DB2 --> B
    DB2 --> C
    DB2 --> D
~~~

Sơ đồ minh họa **vai trò có thể khác theo database**; nó không phải ảnh chụp trạng thái thực tế của một cluster. Việc một server được phép host loại allocation nào còn phụ thuộc `modeConstraint`, tài nguyên, quyền và topology.

### 3.1. Phân biệt `modeConstraint` với role đang có

Một server có thể được đặt ràng buộc:

| `modeConstraint` | Ý nghĩa |
| --- | --- |
| `PRIMARY` | Server chỉ đủ điều kiện chứa các allocation **primary** |
| `SECONDARY` | Server chỉ đủ điều kiện chứa các allocation **secondary** |
| `NONE` | Server có thể chứa **cả primary lẫn secondary**, tùy allocator |

`modeConstraint=PRIMARY` không có nghĩa server đang là writer của mọi database. **Writer là vai trò được bầu bên trong Raft group của từng database**. Ràng buộc này cũng không tự tạo thêm bản sao; phải có số server đủ điều kiện để đáp ứng topology.

## 4. Primary, leader, Raft và quorum

Với một database có **ba primary**:

~~~mermaid
flowchart LR
    API["Write transaction"] --> L["Primary A<br/>Leader/Writer"]
    L -->|Raft / replication| B["Primary B<br/>Follower"]
    L -->|Raft / replication| C["Primary C<br/>Follower"]
    B -.->|ACK| L
    C -.->|ACK| L
    L -->|Commit sau đủ xác nhận| API
    L -.->|Log shipping bất đồng bộ| S["Secondary D<br/>Read-only"]
~~~

Các bước khái niệm:

1. Routing driver tìm được **write route** cho database đích.
2. Giao dịch ghi được điều phối bởi **writer/leader** hiện tại.
3. Leader sắp xếp các transaction vào thứ tự thống nhất bằng cơ chế Raft và sao chép tới follower primary.
4. Giao dịch chỉ được xem là commit bền vững theo chính sách cụm khi đạt số xác nhận **quorum** cần thiết.
5. Secondary cập nhật qua **sao chép bất đồng bộ/transaction log shipping** để phục vụ READ.

**Không có nhiều writer đồng thời cho cùng một standard database** chỉ vì có ba primary. Các primary còn lại là thành viên có thể được bầu khi cần, đồng thời cung cấp khả năng đọc.

### 4.1. Tính quorum

Với `M` primary tham gia Raft, số xác nhận đa số đơn giản là:

\[
Q = \left\lfloor \frac{M}{2}\right\rfloor + 1
\]

Số lỗi primary tối đa có thể chịu mà vẫn giữ được **quorum ghi** (trong điều kiện các thành viên còn lại và mạng hoạt động) là:

\[
F = M - Q = \left\lfloor \frac{M-1}{2}\right\rfloor
\]

| Số primary | Quorum ghi | Chịu mất tối đa | Ghi chú |
| ---: | ---: | ---: | --- |
| 1 | 1 | 0 | Write latency thấp, không chịu lỗi primary |
| 2 | 2 | 0 | Mất 1 → không còn quorum; không giải quyết HA ghi |
| 3 | 2 | 1 | Lựa chọn HA thông dụng |
| 4 | 3 | 1 | Không chịu được 2 lỗi; thường không lợi như 3 hoặc 5 |
| 5 | 3 | 2 | Chịu 2 lỗi primary, chi phí ghi/tài nguyên cao hơn |

Vì vậy quy tắc thường dùng để **chịu F lỗi** là `M = 2F + 1`. Theo tài liệu hiện hành, Neo4j cho phép tối đa 11 primary allocations cho một database tiêu chuẩn nhưng **không khuyến nghị tăng tùy ý**: số bên phải xác nhận và ảnh hưởng network có thể làm latency ghi tăng.

### 4.2. Mất quorum không đồng nghĩa mất toàn bộ dữ liệu

Với ba primary, nếu hai primary không thể liên lạc, database mất khả năng **commit WRITE mới**, nhưng một thành viên còn giữ được bản sao dữ liệu có thể vẫn phục vụ **một số READ** tùy trạng thái, routing và quyền. Không kết luận cả graph đã bị xóa chỉ vì write fail.

Ngược lại, **vẫn đọc được** không đồng nghĩa sẽ bảo toàn mọi write cuối cùng trong mọi thảm họa. Cần sao lưu và mô hình failure domain: nếu tất cả các bản chứa transaction đã commit bị phá hủy, replication không thay cho backup.

## 5. Secondary: mở rộng đọc, không tham gia quorum ghi

**Secondary** là bản sao database nhận transaction **bất đồng bộ** từ upstream, thường dùng để phân phối các truy vấn chỉ đọc.

| Đặc điểm | Primary | Secondary |
| --- | --- | --- |
| Có thể trở thành writer của database? | **Có**, nếu được bầu làm leader | **Không** |
| Tham gia quorum ghi? | Có, với topology nhiều primary | Không |
| Phục vụ `MATCH`/traversal chỉ đọc? | Có | Có |
| Nhận thay đổi từ writer | Sao chép đồng thuận giữa các primary | Transaction log shipping bất đồng bộ |
| Có thể tạm thấy dữ liệu cũ? | Tùy trạng thái/đường đọc, nhưng primary đồng thuận phục vụ commit mới | **Có thể trễ** do asynchronous replication |
| Mất một bản sao ảnh hưởng gì? | Có thể giảm khả năng chịu lỗi ghi | Chủ yếu giảm thông lượng đọc; không thay đổi quorum primary |

Ví dụ ứng dụng gợi ý sản phẩm có lượng truy vấn READ lớn: có thể dùng **3 primary + 2 secondary**, gửi nhiều truy vấn `MATCH`/path cho secondary, còn các giao dịch `MERGE`/`SET` được điều phối qua writer của database.

Đừng xem secondary như cache HTTP dùng chung dữ liệu tùy ý. Nó là **bản sao graph** có storage, CPU, RAM, page cache, connection và chi phí vận hành thực. Thêm nhiều secondary có lợi khi **workload đọc thực sự có thể chia tải** và bottleneck không nằm ở một thành phần khác như API, mạng hay index thiếu.

### 5.1. Read consistency

Vì secondary có thể nhận log muộn, một request đọc ngay sau khi ghi có nguy cơ **chưa thấy dữ liệu mới** nếu application không thiết kế nhân quả:

~~~text
T1: executeWrite() tạo Order O-901 tại writer
T2: commit thành công
T3: request READ tới secondary chưa replay transaction
T4: secondary cập nhật log, Order mới xuất hiện
~~~

Để đảm bảo **read-your-writes** khi cần, dùng **bookmark/causal consistency** của Neo4j Driver (phần 8). Đừng tự thêm `Thread.sleep(1000)` làm “giải pháp nhất quán”; độ trễ sao chép thay đổi theo tải và lỗi mạng.

## 6. Chọn topology theo bài toán

| Topology của **một database** | Mục đích | Write HA | Read scaling | Cảnh giác |
| --- | --- | --- | --- | --- |
| **1 primary, 0 secondary** | Lab, workload nhỏ, tối ưu latency ghi đơn giản | Không | Giới hạn | Một host hỏng → không phục vụ |
| **1 primary, N secondary** | Phân tích/đọc nhiều, chấp nhận không HA ghi | Không | Có | Primary hỏng → read có thể tiếp tục, write dừng |
| **3 primary, 0 secondary** | HA ghi và đọc thông thường | Chịu lỗi 1 primary | Có đọc từ primary không làm writer | Đồng bộ Raft, chi phí 3 bản đầy đủ |
| **3 primary, N secondary** | HA ghi + mở rộng đọc lớn | Chịu lỗi 1 primary | Có, bằng secondary | Cần quản lý lag, cost, router |
| **5 primary, N secondary** | Yêu cầu chịu lỗi 2 primary | Chịu lỗi 2 primary | Có | Cao hơn về đồng bộ, I/O, tài nguyên |

**Chỉ có 1 primary + nhiều secondary không tương đương HA ghi.** Secondary không tự được nâng lên làm writer mới của Raft group để tiếp tục commit khi primary duy nhất mất. Muốn ghi liên tục khi lỗi một primary bất kỳ, chọn **3 primary** đặt ở các failure domain độc lập phù hợp.

### 6.1. Multi-database allocation

Trong cluster 6 server, có thể đặt:

- `orders_graph`: 3 primary trên A/B/C; 2 secondary trên D/E.
- `recommendation_graph`: 3 primary trên B/D/F; một secondary trên A.
- `system`: topology do quy tắc riêng quản lý, không giống cách tùy ý cấp số primary bằng `CREATE DATABASE`.

Đây là phân bổ mẫu; **allocator** và các ràng buộc server quyết định placement thực tế. Mục tiêu là giảm tải nóng trên một host, bảo vệ HA và đặt workload đọc gần mạng ứng dụng nếu phù hợp.

**Không có transaction nguyên tử xuyên hai database** chỉ vì cùng cluster. Nếu nghiệp vụ cần thay đổi đồng thời hai graph, cần thiết kế ranh giới transaction và quy trình nhất quán liên hệ thống riêng.

## 7. Quản trị topology bằng Cypher

Các lệnh trong phần này dành cho **Neo4j Enterprise tự quản**, chạy bằng account quản trị trong **database `system`**. Không tự dùng trên production hay Aura tenant nếu dịch vụ không cho phép.

### 7.1. Xem server và database allocations

~~~cypher
SHOW SERVERS;
~~~

~~~cypher
SHOW DATABASES
YIELD name, address, role, writer,
      requestedStatus, currentStatus, statusMessage
RETURN name, address, role, writer,
       requestedStatus, currentStatus, statusMessage
ORDER BY name, address;
~~~

Trong các version hỗ trợ các cột trên:

- `name`: database được cấp phát.
- `address`: endpoint của bản sao tương ứng.
- `role`: `primary` hoặc `secondary` trên allocation.
- `writer`: bản sao primary đang được chọn làm writer cho database.
- `requestedStatus` vs `currentStatus`: trạng thái mong muốn so với hiện tại.
- `statusMessage`: gợi ý khi có lỗi allocation/recovery.

Nếu client không nhìn thấy một cột hoặc procedure, hãy kiểm tra **quyền và version**; không tự suy rằng cluster không có writer. Một bản ghi `writer=false` trên secondary là trạng thái **bình thường**.

### 7.2. Tạo database với topology cụ thể

~~~cypher
// CHỈ LÀM TRÊN CLUSTER LAB ĐƯỢC PHÉP.
// Cần ít nhất 5 server enabled đủ điều kiện.
CREATE DATABASE graph_lab
TOPOLOGY 3 PRIMARIES 2 SECONDARIES;
~~~

Mỗi allocation cần một server đủ điều kiện theo `modeConstraint` và placement rules. Với chỉ ba server, câu lệnh trên có thể lỗi vì thiếu chỗ đặt cả năm bản sao. Việc tăng topology không tự sinh thêm server vật lý.

Nếu chưa cần secondary:

~~~cypher
CREATE DATABASE graph_lab
TOPOLOGY 3 PRIMARIES;
~~~

Hai ví dụ trên là **hai lựa chọn thay thế**, không chạy nối tiếp trên cùng một cluster nếu database đã tồn tại.

### 7.3. Thay topology và đọc lại trạng thái

~~~cypher
// Giả định graph_lab đã có và cluster đủ tài nguyên.
ALTER DATABASE graph_lab
SET TOPOLOGY 3 PRIMARIES 2 SECONDARIES;
~~~

Sau đó dùng `SHOW DATABASES` kiểm tra số primary/secondary thực tế đã online. Yêu cầu thay topology có thể mất thời gian vì cần tạo/reallocate bản sao và chuyển dữ liệu.

**Lưu ý rất quan trọng:** Tài liệu Neo4j hiện hành không cho chuyển **tự động từ nhiều primary về một primary** bằng `ALTER DATABASE ... SET TOPOLOGY 1 PRIMARY`. Quy trình này có thể phải backup, drop/recreate hoặc seed theo hướng dẫn chính thức; **không dùng thử trên dữ liệu thật**.

### 7.4. Bổ sung một server mới

Trong cluster 5.x/2025–2026, server mới tham gia discovery **không mặc nhiên được allocator dùng để host database ngay**. Nó có thể ở trạng thái **`Free`**, và quản trị viên cần:

~~~cypher
// Placeholder: thay bằng ID server lấy từ SHOW SERVERS.
ENABLE SERVER 'server-id-from-show-servers';
~~~

Đối với placement, có thể khai báo `OPTIONS {modeConstraint: 'SECONDARY'}` trong cú pháp `ENABLE SERVER` nếu phù hợp version và mục tiêu. **Đừng tự đặt PRIMARY/SECONDARY cho cả server như một role Raft cố định**; đây là ràng buộc allocation, không phải chỉ định leader.

Tham khảo [Managing databases in a cluster](https://neo4j.com/docs/operations-manual/current/clustering/databases/) và [Managing servers](https://neo4j.com/docs/operations-manual/current/clustering/servers/).

## 8. Java Driver: định tuyến READ/WRITE và causal consistency

Ứng dụng Java không nên lưu thủ công địa chỉ “leader hiện tại” để phát WRITE: leader **có thể thay đổi khi bầu cử hoặc failover**. Dùng scheme **routing** `neo4j://` hoặc `neo4j+s://` trên các endpoint được cluster cung cấp.

| URI | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `neo4j://host:7687` | Routing driver lấy routing table để chọn read/write route | Cluster self-managed theo đúng network/TLS policy |
| `neo4j+s://host:7687` | Routing với TLS và xác minh chứng chỉ tin cậy | Production có CA/chứng chỉ phù hợp |
| `neo4j+ssc://host:7687` | Routing TLS với chế độ chấp nhận chứng chỉ tự ký theo driver | Chỉ khi chính sách bảo mật cho phép, không thay xác minh chuẩn |
| `bolt://host:7687` | Kết nối trực tiếp một endpoint | Môi trường single-server hoặc khi thực sự cần direct connection |

Khi dùng routing, **`executeRead`** tạo READ transaction, còn **`executeWrite`** tạo WRITE transaction. Driver gửi transaction tới server thích hợp dựa trên routing table và trạng thái cluster; ứng dụng không trực tiếp biến một secondary thành writable.

### 8.1. Ví dụ Java Driver có read-after-write

~~~java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class ClusterRoutingDemo {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        // Ví dụ URI: neo4j+s://cluster.example.com
        // Cần CA/chứng chỉ hợp lệ và account được cấp quyền.
        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password));
             Session session = driver.session(
                SessionConfig.forDatabase("graph_lab"))) {

            // Chỉ chạy trên database lab đã có constraint phù hợp.
            session.executeWriteWithoutResult(tx ->
                    tx.run("""
                        MERGE (c:ClusterLabCustomer {
                          customerId: $id
                        })
                        SET c.displayName = $name
                        """, Map.of(
                                "id", "C-LAB-01",
                                "name", "Lan")).consume());

            String name = session.executeRead(tx ->
                    tx.run("""
                        MATCH (c:ClusterLabCustomer {
                          customerId: $id
                        })
                        RETURN c.displayName AS name
                        """, Map.of("id", "C-LAB-01"))
                      .single()
                      .get("name")
                      .asString());

            System.out.println(name);
        }
    }
}
~~~

Trong **một Session**, Java Driver quản lý bookmark để các transaction sau có thể quan sát các thay đổi trước đó theo **causal consistency**. Trên cluster, READ có thể đợi thành viên được chọn bắt kịp bookmark; điều đó có thể tăng latency hoặc gây timeout nếu replication trễ.

**Giới hạn phạm vi:** Nếu request HTTP A ghi bằng Session A, rồi request B mở Session B trên ứng dụng khác, **không tự có cùng causal chain**. Khi cần đảm bảo read-after-write xuyên Session hoặc luồng xử lý, dùng **BookmarkManager**, chuyển bookmark hoặc chọn chiến lược truy cập nhất quán theo driver/version. Đọc không phụ thuộc hoặc báo cáo analytics có thể chọn cho phép độ trễ secondary.

### 8.2. Lỗi retry và transaction callback

Managed transaction `executeRead` / `executeWrite` có cơ chế retry **những lỗi transient mà driver nhận diện**. Khi cluster bầu leader mới, transaction có thể bị retry, nhưng **không phải mọi lỗi đều được retry** hoặc luôn phục hồi trước timeout.

Quy tắc:

- Callback có thể chạy lại: dùng business ID ổn định, constraint và logic **idempotent**.
- Không gọi payment gateway, gửi email, phát message broker trực tiếp trong callback có thể retry.
- Chỉ trả response thành công **sau khi `executeWrite` hoàn tất và commit được xác nhận**.
- Đo lỗi routing, transaction timeout, retry rate, read/write latency và queue pool; không giấu sự cố sau trung bình p50.

Với Spring Data Neo4j, repository/`Neo4jClient` hoạt động trong transaction manager của Spring; cấu hình connection/routing phù hợp, tránh giả định hai repository trên hai database có cùng transaction ACID.

Nguồn: [Java Driver transactions](https://neo4j.com/docs/java-manual/current/transactions/), [Coordinate parallel transactions with bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/).

## 9. Cấu hình discovery và mạng cụm

Để các server Enterprise tìm nhau, cần một cơ chế **cluster discovery** được cấu hình nhất quán. Trong bản mới, Neo4j hỗ trợ các resolver theo môi trường (danh sách endpoint, DNS, Kubernetes...). Không copy nguyên setting Neo4j 4.4 `causal_clustering.*` sang Neo4j 5/2025+.

Ví dụ **một fragment** của `neo4j.conf` theo Neo4j hiện đại, với các DNS name chỉ mang tính minh họa:

~~~properties
# Áp dụng cho từng server với advertised address riêng.
server.default_listen_address=0.0.0.0
server.default_advertised_address=neo4j-a.internal.example
dbms.cluster.discovery.resolver_type=LIST
dbms.cluster.endpoints=neo4j-a.internal.example:6000,neo4j-b.internal.example:6000,neo4j-c.internal.example:6000
server.cluster.system_database_mode=PRIMARY
~~~

**Đây không phải cấu hình cluster đầy đủ để deploy ngay.** Còn yêu cầu edition/license, TLS, certificate, Bolt listen/advertised addresses, firewall, volume, failure domains, đồng bộ thời gian, quyền filesystem, CPU/RAM và các port intra-cluster phụ thuộc version.

Không dùng cùng một `server.default_advertised_address` trên ba máy. DNS name phải được resolve **từ các server khác và client cần thiết**; nếu advertised Bolt route trỏ tới địa chỉ private không truy cập được từ client, handshake ban đầu có thể thành công nhưng query vẫn lỗi vì routing table chứa endpoint unreachable.

### 9.1. Phân biệt discovery và data traffic

| Nhóm kết nối | Vai trò | Cách bảo vệ |
| --- | --- | --- |
| Discovery/management | Giúp các server tìm nhau và quản lý topology | Chỉ mạng cluster tin cậy, ACL/TLS phù hợp |
| Intra-cluster replication / Raft | Đồng bộ primary và log tới secondary | Network latency ổn định, encryption, không mở Internet |
| Bolt client | Java Driver, Spring Data Neo4j, query | Routing URI, TLS, RBAC, connection pool |
| Backup/monitoring | Backup/metrics riêng | Endpoint nội bộ, tài khoản và retention riêng |

Với Docker/Kubernetes, không giả định port container giống endpoint mà client bên ngoài có thể dùng. Cần cân nhắc host port, Service/Ingress, DNS, NetworkPolicy và cấu hình advertised address.

### 9.2. Khác biệt cụ thể giữa discovery v1 và v2

Theo hướng dẫn migration, **discovery v1 bị deprecate ở 5.23 và bị bỏ ở 2025.01**. Khi có cluster 5.x cũ:

1. Kiểm tra version chính xác của tất cả server.
2. Xác định discovery implementation hiện hành.
3. Lập kế hoạch chuyển sang cơ chế được phiên bản đích hỗ trợ.
4. Kiểm thử cluster restart/rejoin, failover và routing trong staging.
5. Không nâng cấp toàn bộ binary trước rồi mới kiểm tra setting v1.

Nguồn: [Neo4j 5 migration guidance](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/planning/), [Neo4j cluster deployment](https://neo4j.com/docs/operations-manual/current/clustering/setup/deploy/).

## 10. `system` database và quản lý server khác database nghiệp vụ

Neo4j dùng **`system` database** để lưu thông tin DBMS như databases, server allocations, users và roles trong phạm vi sản phẩm hỗ trợ. Khi cluster có nhiều database:

- Mỗi **standard database** có topology primary/secondary và Raft group riêng.
- `system` database có cấu hình placement/primary/secondary riêng; theo tài liệu hiện đại, `server.cluster.system_database_mode` ảnh hưởng tới vai trò bản sao `system` trên server.
- Các lệnh như `SHOW SERVERS`, `ENABLE SERVER`, `CREATE DATABASE` hoặc `ALTER DATABASE` cần ngữ cảnh quản trị/phân quyền thích hợp.
- Phân bổ database có thể cần **reallocation** để cân bằng sau nhiều thay đổi topology, nhưng không phải cứ thêm server là tự chuyển toàn bộ dữ liệu.

### 10.1. Tại sao cần bảo vệ `system`?

Giả sử graph nghiệp vụ có 3 primary khỏe, nhưng metadata điều phối cluster có sự cố nghiêm trọng. Một số thao tác quản trị/topology có thể bị ảnh hưởng, dù một phần READ/WRITE của database nghiệp vụ vẫn đang chạy. Vì thế cần giám sát **health của `system` và của từng user database**, không chỉ một trạng thái “cluster online”.

Với máy chủ ổn định lâu dài, thường ưu tiên primary `system`. Máy ephemeral chỉ dùng analytics có thể phù hợp với secondary `system` theo kiến trúc vận hành. Tham khảo hướng dẫn chính thức để chọn topology; đừng đặt `system` trên một server duy nhất mà vẫn tuyên bố có HA quản trị.

## 11. Từ cluster HA đến mở rộng hiệu năng: điều gì thật sự tăng?

### 11.1. READ scale-out

Trên graph quan hệ lớn, nhiều truy vấn `MATCH` có thể thực thi song song ở các secondary. Ví dụ:

~~~cypher
MATCH (c:Customer {customerId: $id})
      -[:PLACED]->(o:Order)
RETURN o.orderId, o.status
ORDER BY o.orderId
LIMIT 20;
~~~

Nếu truy vấn có index/constraint phù hợp, nhiều secondary giúp chia request **đọc độc lập**. Nhưng một query duy nhất tạo 10 triệu hàng trung gian **không tự được chia thành 10 phần giữa 10 secondary**; mỗi query vẫn chạy trên một bản sao, trừ khả năng phân tán riêng được thiết kế rõ.

### 11.2. WRITE không scale tuyến tính bằng số primary

Một standard database có **một writer tại một thời điểm**. Tăng từ 3 lên 5 primary chủ yếu tăng khả năng chịu lỗi, **không nhân đôi số writer**. Quorum và network replication còn có thể tăng latency commit.

Nếu nghẽn WRITE:

1. Kiểm tra plan Cypher và index/constraint trên business key.
2. Đo lock contention, transaction duration, batch size, CPU, disk và transaction log I/O.
3. Dùng `UNWIND`/managed transaction để batch hợp lý, nhưng không tạo transaction quá dài.
4. Phân biệt load đọc đang tranh tài nguyên với writer; cân nhắc secondary để offload READ.
5. Nếu cần nhiều write domains thật sự độc lập, cân nhắc **nhiều database/partition theo nghiệp vụ**, đồng thời chấp nhận không có ACID tự động xuyên database.

### 11.3. Graph size không giảm trên mỗi replica

Trong cluster tiêu chuẩn, **bản sao đầy đủ** của database cần storage tương ứng. Một graph nguồn 500 GB không trở thành 100 GB trên mỗi host khi phân bổ 5 replica; phần dữ liệu store của mỗi bản sao vẫn có thể xấp xỉ toàn bộ database, chưa kể transaction log, index, backup và overhead.

Để dự trù:

- Disk theo **store + logs + free space + tăng trưởng + recovery headroom** trên từng host.
- RAM cho **page cache + heap + native memory/OS** theo workload từng bản sao.
- Network throughput cho **replication** và kết quả truy vấn đến client.
- SLO theo **p95/p99** và tỷ lệ lỗi, không chỉ theo số node/relationship tổng cộng.

### 11.4. Analytics và GDS

Job Graph Data Science (GDS) có thể dùng nhiều RAM/CPU cho graph projection trong bộ nhớ. Các **named GDS graphs trong catalog in-memory không tự biến thành database replica hay được sao chép như dữ liệu store thông thường**. Đặt analytics lên server hoặc cluster phù hợp, quản lý graph lifecycle và tránh job nặng gây tăng p99 giao dịch quan trọng.

## 12. Kiến trúc đa vùng và failure domains

**Failure domain** là nhóm thành phần có thể cùng lỗi: một host, rack, availability zone, data center hoặc region. Mỗi primary có thể nằm trên host khác nhau nhưng vẫn cùng một ổ storage hay cùng một AZ; khi đó “3 primary” chưa chứng minh chịu lỗi vùng.

### 12.1. Mẫu ba primary ở ba zone

~~~mermaid
flowchart LR
    AZ1["Zone A<br/>Primary 1"] <--> AZ2["Zone B<br/>Primary 2"]
    AZ2 <--> AZ3["Zone C<br/>Primary 3"]
    AZ1 <--> AZ3
    APP["Client routing"] --> AZ1
    APP --> AZ2
    APP --> AZ3
~~~

Trong điều kiện network ổn định, mất một zone chứa một primary vẫn còn **hai primary = quorum 2/3**. Nhưng:

- Độ trễ giữa các primary ảnh hưởng write commit latency vì có trao đổi đồng thuận.
- Nếu hai zone mất hoặc network partition làm nhóm còn lại không đạt quorum, WRITE phải dừng để giữ an toàn.
- Chỉ một zone còn primary không được tự “force writer” mà bỏ cơ chế đồng thuận.
- Có thể đặt secondary gần nơi đọc để giảm latency, nhưng data trên secondary có thể trễ.

### 12.2. Khi nào không nên kéo primary qua nhiều region xa?

Raft yêu cầu xác nhận từ quorum trước commit. Network giữa các region xa có RTT cao làm tăng độ trễ và nhạy với partition. Nếu ứng dụng đòi write latency cực thấp, hãy:

- Đặt quorum primary trong các zone có latency phù hợp theo hướng dẫn Neo4j.
- Dùng secondary hoặc chiến lược dữ liệu khác để đáp ứng read locality.
- Đặt SLO và disaster recovery policy riêng cho kịch bản mất cả region.
- Thử nghiệm leader election/failover, replication lag và network partition **trong môi trường kiểm soát**.

Không có topology nào đồng thời bảo đảm latency tối thiểu, chịu mọi partition, zero downtime và zero data loss trong tất cả thảm họa. Cần ưu tiên dựa trên bài toán nghiệp vụ.

## 13. Infinigraph và property sharding từ Neo4j 2025.12

Đến đây, cần phân biệt **hai dạng “mở rộng ngang”**:

| Cơ chế | Bản chất | Điều kiện |
| --- | --- | --- |
| **Enterprise standard clustering** | Sao chép toàn bộ một standard database sang primary/secondary | Neo4j Enterprise, topology và tài nguyên phù hợp |
| **Infinigraph property sharding** | Tách **cấu trúc graph** và **dữ liệu thuộc tính** sang các shard chuyên biệt trong kiến trúc distributed graph | Được giới thiệu từ **2025.12**, **subscription Infinigraph riêng**, không có mặc định trong Enterprise và **không khả dụng trên Aura** theo tài liệu hiện hành |

Với Infinigraph property sharding:

- **Graph shard** lưu **cấu trúc node/relationship**, bảo toàn góc nhìn graph logic.
- **Property shards** lưu các thuộc tính của node/relationship trên các thành viên phân tán.
- Query được xử lý như làm việc với một logical graph, nhưng chi phí truy cập thuộc tính, network và placement cần đo riêng.
- Không nên mô tả đây là “shard mọi node và relationship tùy ý theo customerId” hay mặc định mọi Cypher đều scale write tuyến tính.
- Tính năng, giới hạn procedure/security, Cypher version và topology có ràng buộc riêng. Tài liệu yêu cầu **Cypher 25** cho sharded property databases; nhiều tiện ích của standard database không được sao chép nguyên xi.

**Điểm kiểm tra trước khi kiến trúc hóa:** Dự án thật có subscription Infinigraph không? Phiên bản đang chạy có hỗ trợ cấu hình shard tương ứng không? Deployment có phải Aura (không hỗ trợ tính năng này theo tài liệu hiện tại) không? Nếu câu trả lời không phù hợp, hãy thiết kế theo **standard clustering** thay vì giả định có phân mảnh tự động.

Nguồn: [Scaling with Neo4j](https://neo4j.com/docs/operations-manual/current/scalability/scaling-with-neo4j/), [Infinigraph overview](https://neo4j.com/docs/operations-manual/current/scalability/sharded-property-databases/overview/), [Infinigraph requirements](https://neo4j.com/docs/operations-manual/current/scalability/sharded-property-databases/configuration/).

## 14. Aura: cluster do dịch vụ quản lý khác với tự quản

Neo4j Aura trừu tượng hóa nhiều chi tiết vận hành. Theo thông tin hỗ trợ dịch vụ Neo4j năm 2026:

- **AuraDB Business Critical** và **AuraDB Virtual Dedicated Cloud** sử dụng kiến trúc **three-node causal cluster** cho các instance tương ứng.
- Các gói khác có thể dựa trên **single-node architecture** với khả năng HA ở tầng hạ tầng; **không được suy ra** người thuê luôn có quyền lựa chọn số primary/secondary.
- Nhà cung cấp quản lý nhiều thành phần như placement, upgrade, cơ chế failover và một phần hạ tầng; người thuê dùng API/dashboard của gói để quan sát.

Điều ứng dụng vẫn phải chịu trách nhiệm:

1. Sử dụng URI Aura được cấp với scheme TLS/routing theo hướng dẫn.
2. Cấu hình timeout, retry, pool và database name bằng Java Driver/Spring Data Neo4j.
3. Đặt SLI cho READ/WRITE latency, error rate và khả năng xử lý transaction.
4. Chọn gói dung lượng/khả năng sẵn sàng dựa trên yêu cầu, kiểm tra snapshot/backup, retention và hạn chế dịch vụ.
5. Không dùng `SHOW SERVERS`, `ENABLE SERVER` hay chỉnh `neo4j.conf` như một runbook chung cho mọi tenant Aura nếu API dịch vụ không hỗ trợ.

**Phân biệt:** “Dịch vụ cloud có HA” không có nghĩa **người thuê có quyền điều khiển quorum Raft** hoặc có thể đặt primary across regions tùy ý. Cần xem hợp đồng/SLA tính sẵn sàng của **gói cụ thể**, không chỉ đọc kiến trúc Enterprise self-managed.

Tham khảo [Neo4j Aura Manual](https://neo4j.com/docs/aura/) và [Neo4j Support — Aura CPU usage & architecture](https://support.neo4j.com/s/article/1500013066801-Monitoring-a-Neo4j-AuraDB-Instance-CPU-usage).

## 15. Giám sát, lỗi phổ biến và runbook

### 15.1. Theo dõi từ nhiều tầng

| Tầng | Chỉ số/kiểm tra | Lý do |
| --- | --- | --- |
| **Database** | `SHOW DATABASES`: status, role, writer, địa chỉ allocation | Phát hiện thiếu writer, database offline |
| **Cluster/server** | `SHOW SERVERS`: enabled/free/cordoned, điều kiện allocation | Phát hiện server không nhận allocation, phân bố không đều |
| **Replication** | Lag của secondary, chậm áp dụng transaction, routing failures | Đánh giá freshness của READ |
| **Consensus** | Writer election/quorum availability, lỗi liên lạc primary | Giải thích WRITE unavailable |
| **Neo4j process** | CPU, heap, GC, page cache, disk, transaction log, I/O | Xác định saturation |
| **Client** | READ/WRITE requests, retry, pool pending, Bolt TLS/handshake, p95/p99 | Phản ánh trải nghiệm ứng dụng |
| **Business** | Tỷ lệ tạo đơn commit thành công, truy vấn đường đi đúng | Không đánh đồng health process với health nghiệp vụ |

### 15.2. Runbook A — Mất một primary trong topology 3

1. Xác định **database nào** mất allocation, server và failure domain.
2. `SHOW DATABASES` xem writer/role/status của các bản sao còn lại; xác minh quorum 2/3.
3. Đo lại synthetic WRITE và READ ở ứng dụng; một cuộc bầu leader có thể gây lỗi transient/latency ngắn.
4. Điều tra mạng, disk, process/GC và log của server mất; không tự động gỡ member nếu chưa biết nguyên nhân.
5. Khôi phục/rejoin hoặc thêm server mới theo hướng dẫn version; xác nhận dữ liệu sync.
6. Chỉ đóng incident sau khi **đã phục hồi khả năng chịu thêm lỗi**, không chỉ sau khi WRITE chạy lại.

### 15.3. Runbook B — Mất quorum

- Triệu chứng: READ có thể còn từ một số replica nhưng WRITE commit lỗi, không có writer hữu dụng.
- Kiểm tra số primary đang online **và khả năng liên lạc lẫn nhau**; ba process “running” trên ba subnet bị chia cắt không nhất thiết tạo quorum.
- Kiểm tra partition mạng, TLS nội bộ, cluster discovery và thay đổi cấu hình.
- Khôi phục đủ primary có trạng thái tương thích; không tự “force leader” bằng việc phá dữ liệu hoặc xóa cluster state.
- Nếu phải tái tạo cluster từ backup, làm theo **kịch bản recovery do Neo4j hỗ trợ** và đánh giá RPO thực tế.

### 15.4. Runbook C — Đọc trên secondary bị trễ

- Xác định operation nào cần read-your-writes và operation nào chấp nhận eventual reads.
- Kiểm tra replication lag, mạng, disk I/O và tải query trên secondary.
- Xác minh bookmark có được truyền đúng giữa Session liên quan không.
- Tránh xử lý bằng sleep cố định; cân nhắc đi read tới đường thích hợp hoặc đợi bookmark **có timeout**.
- Đặt cảnh báo về freshness theo yêu cầu nghiệp vụ; không chỉ theo ping tới port 7687.

### 15.5. Runbook D — Thêm server nhưng không tăng throughput

1. Kiểm tra server mới đã **enabled** chưa; có modeConstraint và đủ điều kiện allocation không.
2. Database có được cấu hình thêm secondary không, hay server vẫn trống?
3. Driver có nhận routing table mới và phân bổ READ ra secondary không?
4. Query có dùng index/constraint, hay bottleneck ở writer/disk/lock?
5. Đo p95/p99, throughput, CPU từng host và replication lag trước/sau.

**Thêm node hạ tầng không tự động chữa query chậm.** Cần thấy rõ workload được phân bố và hệ thống thật sự bớt nghẽn.

## 16. Backup, bảo trì rolling và an toàn dữ liệu

### 16.1. Cluster không thay thế backup

Replication đồng bộ có thể sao chép **một lệnh xóa nhầm** tới toàn bộ primary; secondary cũng áp dụng thay đổi đó. Vì thế:

- Dùng **online backup** khi edition/phiên bản hỗ trợ, hoặc snapshot do Aura quản lý.
- Đặt RPO/RTO, retention, lưu bản ngoài failure domain và **restore drill** định kỳ.
- Bảo vệ backup metadata của **`system` database** và các user database theo policy.
- Kiểm tra tương thích backup/restore khi nâng phiên bản Neo4j.
- Đối soát dữ liệu sau restore, đặc biệt nếu còn PostgreSQL/Kafka/CDC và những hệ thống khác.

### 16.2. Rolling upgrade

Với topology đủ quorum và tài liệu cho phép, có thể upgrade thành viên theo đợt:

1. Đánh giá **version compatibility** và hướng dẫn nâng cấp từ bản hiện tại tới bản đích.
2. Backup và xác nhận khả năng restore, xem cluster đang đủ quorum.
3. Lập kế hoạch ngừng/rút một thành viên tại một thời điểm theo quy trình version, đảm bảo không mất quá nhiều primary đồng thời.
4. Kiểm tra database allocation online, writer/routing, replication lag trước khi tiếp tục member sau.
5. Sau mỗi bước, chạy synthetic READ/WRITE, theo dõi p99/timeout/driver retry.
6. Có phương án rollback **theo quy trình restore/migration được hỗ trợ**, không giả định mọi downgrade được hỗ trợ.

**Chú ý về migration 4.4 → 5:** Đây là thay đổi lớn về cơ chế clustering, không chỉ rolling restart binary của cluster cũ. Tài liệu Neo4j khuyến nghị **cấu hình cluster 5 mới rồi migrate**; không dùng hướng dẫn rolling upgrade minor trong cùng dòng version để thay thế quy trình này.

Nguồn: [Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/), [Cluster introduction](https://neo4j.com/docs/operations-manual/current/clustering/introduction/).

### 16.3. Bảo mật giữa các thành viên

- Chỉ cho phép cluster ports giữa các server được tin cậy; không phơi discovery/Raft ra Internet.
- Dùng TLS/certificates và secret management theo hướng dẫn phiên bản.
- Bảo vệ `server.default_advertised_address` và DNS khỏi cấu hình nhầm endpoint không truy cập được.
- Không cấp tài khoản API quyền quản trị server/allocation chỉ để kiểm tra health.
- Cách ly backup, monitoring exporter và dữ liệu log chứa thông tin topology; phân quyền đọc phù hợp.

## 17. Thực hành thiết kế và kiểm tra topology

### 17.1. Bối cảnh

Một ứng dụng quản lý mạng lưới `Customer -[:PLACED]-> Order`, dùng Java Driver để ghi đơn và Cypher để đọc hành vi mua hàng. Nhóm dự định triển khai 5 server Neo4j Enterprise:

- Server A/B/C đặt tại ba availability zone.
- Server D/E dành phần lớn năng lực cho READ/traversal.
- Yêu cầu: mất **một** primary vẫn có WRITE; tăng lượng READ độc lập; read-your-writes phải đúng với luồng tạo đơn.

### 17.2. Chọn topology

Đề xuất: **3 primary + 2 secondary** cho database `graph_lab`, vì ba primary giữ quorum khi lỗi một thành viên và hai secondary chia READ. Đặt **`system` primary** và discovery đúng khả năng của các server được phân bổ, không chỉ database nghiệp vụ.

Trên cluster **lab đã dựng sẵn, có quyền quản trị**, có thể tạo database:

~~~cypher
CREATE DATABASE graph_lab
TOPOLOGY 3 PRIMARIES 2 SECONDARIES;
~~~

Kiểm tra:

~~~cypher
SHOW DATABASES
YIELD name, address, role, writer, currentStatus
WHERE name = 'graph_lab'
RETURN name, address, role, writer, currentStatus
ORDER BY role, address;
~~~

Kỳ vọng có **ba dòng primary** và **hai dòng secondary** khi allocator hoàn thành và cả năm allocations online; trong ba primary **một** writer tại thời điểm bình thường.

### 17.3. Thử truy vấn đọc/ghi an toàn

Tạo constraint trên database `graph_lab`, không phải `system`:

~~~cypher
CREATE CONSTRAINT cluster_lab_customer_unique IF NOT EXISTS
FOR (c:ClusterLabCustomer)
REQUIRE c.customerId IS UNIQUE;
~~~

Chạy Java Demo phần 8 với account được cấp quyền. Nếu cả WRITE và READ trong **một Session** thành công, ghi lại latency và xác minh read-your-writes. Sau đó mở hai Session không chia sẻ bookmark để quan sát lý do cần quản lý causal dependency khi đọc từ các replica bất đồng bộ; không cố ép hệ thống phải trễ để “chứng minh” lỗi.

### 17.4. Thử lỗi có kiểm soát

Chỉ trên lab không chứa dữ liệu nghiệp vụ:

1. Ghi lại writer và trạng thái trước thử nghiệm.
2. Theo runbook lab, dừng **một primary**; không đồng thời dừng member khác.
3. Đợi cơ chế bầu chọn/routing ổn định theo tài liệu; chạy synthetic WRITE bằng ID khác và kiểm tra commit.
4. READ từ client routing, chú ý lỗi transient và retry.
5. Khôi phục member, theo dõi rejoin và catch-up trước khi thử tiếp.

**Không diễn tập mất quorum bằng cách dừng hai primary trên production.** Với bài lab, có thể **thảo luận** tình huống 2/3 primary lỗi dựa trên bảng quorum thay vì gây phân vùng mạng nguy hiểm.

### 17.5. So sánh mở rộng READ

Thử một workload có nhiều truy vấn `MATCH` độc lập:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId, o.status
LIMIT 50;
~~~

Chạy ở cùng mức concurrency với hai cấu hình được phép:

- **A:** 3 primary, 0 secondary.
- **B:** 3 primary, 2 secondary.

Đo **READ throughput, p50/p95/p99, CPU per-server, pool pending, secondary lag và tỷ lệ lỗi**. Không tự coi B nhanh hơn nếu client đang dùng `bolt://` trỏ một server, routing chưa cập nhật hoặc query không thể chia tải hiệu quả. Dữ liệu và môi trường test phải đại diện cho production.

### 17.6. Câu hỏi tự kiểm tra

**Câu 1.** Cụm có 3 primary nhưng 2 primary ngừng. Có thể commit WRITE mới không?

**Đáp án:** Không đủ quorum 2/3, nên không thể tiếp tục commit WRITE theo cơ chế chuẩn. Có thể còn khả năng READ trên bản sao còn hoạt động theo trạng thái cụ thể.

**Câu 2.** Thêm 3 secondary làm hệ thống có 3 writer không?

**Đáp án:** Không. Secondary chỉ dành cho sao chép bất đồng bộ và phục vụ READ; một standard database có một writer tại một thời điểm.

**Câu 3.** Có thể gọi toàn bộ Server B là “secondary server” không?

**Đáp án:** Trong Neo4j 5.x/2025+, vai trò primary/secondary thuộc **database allocation**. Server có thể bị ràng buộc `modeConstraint`, nhưng vẫn có thể mang vai trò khác nhau với các database nếu cho phép.

**Câu 4.** Tại sao `READ` trên secondary có thể không thấy transaction vừa commit?

**Đáp án:** Secondary nhận transaction log bất đồng bộ. Nếu READ phụ thuộc WRITE trước, cần bookmark/causal consistency hoặc chiến lược đọc phù hợp.

**Câu 5.** Neo4j Community bản mới có thể cluster nếu copy `neo4j.conf` từ Enterprise không?

**Đáp án:** Không. Khả năng cluster phụ thuộc edition/license, không chỉ cấu hình.

**Câu 6.** Cụm 5 primary chắc chắn write throughput gấp đôi cụm 3 primary không?

**Đáp án:** Không. Một database vẫn có một writer; tăng primary chủ yếu tăng chịu lỗi, có thể tăng latency đồng bộ.

**Câu 7.** Có thể coi Infinigraph property sharding như chức năng mặc định của Enterprise hoặc Aura không?

**Đáp án:** Không. Nó xuất hiện từ 2025.12, yêu cầu subscription riêng và theo tài liệu hiện hành không có trên Aura.

**Câu 8.** Cluster có thể thay thế backup sau lỗi xóa nhầm dữ liệu không?

**Đáp án:** Không. Thay đổi sai có thể được sao chép tới tất cả replica; cần bản backup/snapshot độc lập và restore drill.

## 18. Các hiểu lầm và anti-pattern

| Hiểu lầm | Điều cần sửa |
| --- | --- |
| “Có 3 Neo4j server là cluster chịu lỗi 1 máy” | Phải có **3 primary allocations của database cần HA**, ở failure domains thích hợp và cluster quorum hoạt động |
| “Primary là vai trò cố định của server” | Role thuộc **database copy**; server còn có `modeConstraint` |
| “Nhiều primary = multi-writer cho cùng database” | **Một writer/leader** tại một thời điểm cho standard database |
| “Thêm secondary giúp commit WRITE nhanh hơn” | Secondary chủ yếu tăng **READ capacity**, không tham gia quorum |
| “Quorum mất thì nên force leader ngay” | Có nguy cơ phá tính an toàn/nhất quán; phải dùng runbook khôi phục chính thức |
| “Read-only replica luôn thấy dữ liệu mới nhất” | Replication bất đồng bộ có lag; dùng bookmark nếu cần read-your-writes |
| “Cluster tự chia dung lượng graph giữa các server” | Standard replica chứa store đầy đủ; property sharding là cơ chế riêng |
| “Community có clustering nếu đủ RAM và chỉnh setting” | Enterprise clustering phụ thuộc edition |
| “Cấu hình 4.4 chạy nguyên trên 2025.x” | Kiến trúc và discovery/settings đã thay đổi |
| “Có cluster nên không cần sao lưu” | Backup vẫn cần để phục hồi thao tác sai và thảm họa |
| “Driver chỉ cần một bolt:// leader hard-coded” | Leader đổi khi failover; ưu tiên routing URI và bookmark đúng |
| “Aura cho thuê VM nên người dùng quản lý được SHOW SERVERS/topology” | Managed service có giới hạn quản trị theo gói |

## 19. Checklist triển khai và vận hành

- [ ] Xác định **version Neo4j, edition/gói Aura, license** và tài liệu tương ứng.
- [ ] Nếu nâng từ 4.4, xem **migration 4.4 → 5**; không chép nguyên `causal_clustering.*` sang bản mới.
- [ ] Định nghĩa yêu cầu **READ availability, WRITE availability, RPO, RTO và latency SLO** theo nghiệp vụ.
- [ ] Chọn topology mỗi database theo **quorum**: 3 primary chịu 1 lỗi; 5 primary chịu 2 lỗi.
- [ ] Dùng **secondary** khi thực sự cần scale out READ; theo dõi lag và dung lượng per replica.
- [ ] Hiểu rõ **một writer cho một standard database**, không tự coi thêm primary là tăng write parallelism.
- [ ] Lập placement phân tán failure domains, không gom primary cùng một vùng lỗi.
- [ ] Bảo vệ và cấu hình **`system` database**, cluster discovery, TLS, advertised addresses và intra-cluster networking.
- [ ] Kiểm tra server `enabled` và allocation đủ điều kiện trước khi thay topology.
- [ ] Dùng `SHOW SERVERS` và `SHOW DATABASES` để kiểm chứng topology thực thay vì suy từ số container.
- [ ] Cấu hình Java Driver dùng routing READ/WRITE; dùng bookmarks khi cần causal read-after-write.
- [ ] Không chia sẻ một `Session` giữa các thread; quản lý pool, timeout và retry theo SLO.
- [ ] Đo p95/p99, throughput, error rate, page cache, disk, GC, routing và replication lag.
- [ ] Tối ưu index/Cypher/transaction trước khi thêm hàng loạt replica.
- [ ] Lập kế hoạch rolling maintenance theo phiên bản; không làm mất quorum do bảo trì đồng thời.
- [ ] Có **online backup/snapshot** và diễn tập restore, không coi replication là bản sao lưu.
- [ ] Khi dùng Infinigraph, xác nhận **subscription, phiên bản, Cypher 25 và giới hạn**; không giả định có trên Aura.
- [ ] Có runbook cho mất primary, mất quorum, leader election, secondary lag và routing fail.
- [ ] Kiểm thử cả tình huống failover, tăng trưởng dữ liệu, node bậc cao và tải WRITE/READ pha trộn.

## Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Introduction to clustering](https://neo4j.com/docs/operations-manual/current/clustering/introduction/)
- [Neo4j Operations Manual — Deploy a basic cluster](https://neo4j.com/docs/operations-manual/current/clustering/setup/deploy/)
- [Neo4j Operations Manual — Managing databases](https://neo4j.com/docs/operations-manual/current/clustering/databases/)
- [Neo4j Operations Manual — Managing servers](https://neo4j.com/docs/operations-manual/current/clustering/servers/)
- [Neo4j Operations Manual — Leadership, routing, load balancing](https://neo4j.com/docs/operations-manual/current/clustering/setup/routing/)
- [Neo4j Operations Manual — Scaling with Neo4j](https://neo4j.com/docs/operations-manual/current/scalability/scaling-with-neo4j/)
- [Neo4j Operations Manual — Infinigraph property sharding](https://neo4j.com/docs/operations-manual/current/scalability/sharded-property-databases/overview/)
- [Neo4j Upgrade/Migration — Breaking changes from 4.4 to 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/breaking-changes/)
- [Neo4j Upgrade/Migration — Versioning and upgrade paths](https://neo4j.com/docs/upgrade-migration-guide/current/)
- [Neo4j Java Driver — Routing, session and transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver — Bookmarks and causal consistency](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Neo4j Aura Manual](https://neo4j.com/docs/aura/)

**Kết luận:** Kiến trúc cụm Neo4j phải được lựa chọn theo **phiên bản, edition, gói dịch vụ và mục tiêu vận hành**. Với Enterprise 5.x/2025–2026, mỗi database tiêu chuẩn có **primary/secondary allocations**, một **writer/leader**, quorum Raft để bảo đảm ghi bền vững và các secondary để mở rộng đọc. Ba primary giúp chịu lỗi một thành viên; thêm secondary không tạo thêm writer. Hãy kết hợp placement theo failure domain, routing/bookmark của Java Driver, giám sát quorum và replication lag, kế hoạch nâng cấp cùng backup/restore. **Không nhầm cluster replication với sharding**, và chỉ thiết kế Infinigraph khi sản phẩm/giấy phép thực tế hỗ trợ.
