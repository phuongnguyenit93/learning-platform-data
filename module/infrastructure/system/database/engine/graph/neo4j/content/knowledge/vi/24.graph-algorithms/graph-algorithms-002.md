# Neo4j Graph Data Science và điều kiện cài đặt hoặc sử dụng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **Neo4j Graph Data Science (GDS)** giải quyết bài toán gì trong hệ sinh thái property graph và phân biệt GDS với Cypher thông thường.
- Xác định **nơi chạy**, **phiên bản Neo4j/GDS**, **edition/license**, quyền truy cập và tài nguyên cần thiết trước khi sử dụng.
- Cài đặt hoặc kích hoạt GDS trong Neo4j Desktop, Neo4j Server tự quản hoặc Docker; nhận biết lựa chọn dịch vụ được quản lý trên Aura.
- Kiểm tra plugin bằng `gds.version()`, ước lượng bộ nhớ, project một graph vào bộ nhớ, chạy thuật toán và giải phóng graph.
- Phân biệt các chế độ `stream`, `stats`, `mutate` và `write`; thiết kế luồng ứng dụng Java và Spring Data Neo4j gọi GDS an toàn.
- Chẩn đoán lỗi thiếu plugin, không tương thích version, thiếu license, quyền truy cập và vượt giới hạn heap.

Bài thuộc chương **Thuật toán đồ thị** trong module **DATABASE_ENGINE_GRAPH_NEO4J**. Neo4j lưu node, relationship và thuộc tính theo mô hình **property graph**, còn Cypher cho phép truy vấn quan hệ và đường đi. GDS mở rộng khả năng này bằng những **thuật toán phân tích đồ thị ở quy mô lớn** như PageRank, tìm thành phần liên thông, đường đi ngắn nhất, phát hiện cộng đồng, độ tương đồng và các quy trình machine learning dựa trên cấu trúc đồ thị.

> **Lưu ý về phiên bản:** Hướng dẫn này dùng cú pháp của Neo4j GDS hiện đại; các ví dụ tương thích khi database đã cài **GDS plugin phù hợp** và tài khoản có quyền. Neo4j đã có các dòng phiên bản 5.x, 2025.x và 2026.x. Không chọn ngẫu nhiên một file JAR chỉ vì tên gần giống: hãy kiểm tra [ma trận tương thích chính thức](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/) và tài liệu của đúng phiên bản đang vận hành.

## 1. GDS là gì, khác Cypher và APOC thế nào?

Với Cypher, ứng dụng có thể tìm một khách hàng và các đơn hàng liên quan:

~~~cypher
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId;
~~~

Đây là một **truy vấn mẫu dữ liệu**. Khi muốn xác định những node quan trọng nhất trong mạng lưới, chia đồ thị thành cộng đồng hoặc tính toán trên hàng triệu đỉnh/cạnh, cách giải thường là **thuật toán đồ thị**. GDS cung cấp các thuật toán và cơ chế quản lý graph chuyên dụng cho nhiệm vụ này.

| Thành phần | Vai trò chính | Ví dụ |
| --- | --- | --- |
| **Cypher lõi Neo4j** | Truy vấn và cập nhật property graph | `MATCH`, `CREATE`, `MERGE`, truy vấn đường đi |
| **GDS library** | Project graph vào bộ nhớ, chạy các thuật toán phân tích | `gds.pageRank.stream`, `gds.wcc.stream` |
| **APOC** | Bộ procedure/utility hỗ trợ xử lý và tích hợp dữ liệu | Các procedure `apoc.*` tùy plugin |
| **Java Driver / Spring Data Neo4j** | Kết nối, giao dịch, gọi Cypher/procedure từ ứng dụng | `executeRead`, `@Query` |
| **GDS Python Client** | API Python thuận tiện để điều khiển GDS và xử lý kết quả | `GraphDataScience`, `gds.page_rank.stream` |

**GDS không phải phần bắt buộc của Cypher lõi.** Một server Neo4j chạy bình thường vẫn có thể báo `Unknown function 'gds.version'` hoặc `There is no procedure with the name ...` nếu plugin chưa có hoặc chưa được cho phép. Cài Python Client **không tự cài plugin GDS phía server**.

### Các nhóm thuật toán thường gặp

| Nhóm | Bài toán | Thuật toán tiêu biểu |
| --- | --- | --- |
| **Centrality** | Node nào có ảnh hưởng/vị trí quan trọng? | PageRank, Degree Centrality, Betweenness |
| **Community detection** | Những nhóm node liên kết chặt với nhau? | Weakly Connected Components (WCC), Louvain, Leiden |
| **Path finding** | Đường đi nào nối hai node theo chi phí/ràng buộc? | Dijkstra, A* và các biến thể được hỗ trợ |
| **Similarity** | Hai node có mức tương đồng ra sao? | Node Similarity, KNN |
| **Embedding / ML** | Tạo đặc trưng và huấn luyện mô hình từ graph | FastRP, Node2Vec, pipeline phân loại hoặc dự đoán liên kết |

Không phải thuật toán nào cũng sử dụng cùng loại graph hoặc cùng tập thuộc tính. Ví dụ Dijkstra thường cần trọng số cạnh không âm cho bài toán đường đi có trọng số, còn PageRank đánh giá tầm quan trọng dựa trên cấu trúc liên kết. Luôn đọc **yêu cầu graph, orientation, thuộc tính và chế độ thực thi** của thuật toán cụ thể.

## 2. GDS xử lý graph như thế nào?

GDS tạo một **named in-memory graph** trong **graph catalog** từ Neo4j database hoặc nguồn được hỗ trợ. Graph này là **bản biểu diễn trong bộ nhớ phục vụ tính toán**, không đồng nghĩa toàn bộ database được chuyển sang một loại database khác.

~~~mermaid
flowchart LR
    DB[("Neo4j database<br/>node + relationship")] --> P["Graph projection<br/>label, type, properties"]
    P --> MEM[("In-memory graph<br/>GDS catalog")]
    MEM --> ALG["PageRank / WCC / Paths"]
    ALG --> STREAM["stream / stats"]
    ALG --> MUTATE["mutate trong graph catalog"]
    ALG --> WRITE["write trở lại Neo4j"]
~~~

Một vòng làm việc thường gồm:

1. Xác định node label, relationship type, hướng cạnh và thuộc tính cần dùng.
2. **Estimate** dung lượng bộ nhớ cho projection và thuật toán.
3. Project graph vào catalog bằng `gds.graph.project` hoặc cơ chế projection tương ứng.
4. Chạy thuật toán với chế độ phù hợp.
5. Kiểm tra kết quả, đối chiếu ngữ nghĩa nghiệp vụ và cân nhắc ghi trở lại database.
6. **Drop named graph** khi không cần để giải phóng bộ nhớ.

**Lưu ý dữ liệu thay đổi:** Named graph đã project **không tự đồng bộ từng cập nhật** từ database nguồn. Nếu application tạo/xóa node hoặc relationship sau projection, graph trong catalog có thể cũ. Cần xây dựng chính sách tạo lại, lọc hoặc cập nhật graph theo cơ chế GDS hỗ trợ; không xem kết quả thuật toán là dữ liệu giao dịch luôn mới nhất.

## 3. Phân biệt Neo4j edition, GDS edition và các lựa chọn trên Aura

Đây là ba khái niệm cần kiểm tra **riêng**:

1. **Neo4j Database edition:** Community hoặc Enterprise của database.
2. **GDS library edition:** Community Edition (CE) hoặc Enterprise Edition (EE) của **thư viện GDS**.
3. **Môi trường phân phối:** Neo4j Desktop, server tự quản, Docker/Kubernetes, AuraDS hoặc Aura Graph Analytics.

### 3.1. GDS Community và GDS Enterprise

Theo tài liệu GDS hiện hành, GDS Community có sẵn **các thuật toán**, nhưng giới hạn một số khả năng vận hành; GDS Enterprise dùng license riêng để mở các giới hạn và tính năng bổ sung.

| Tiêu chí | GDS Community | GDS Enterprise |
| --- | --- | --- |
| Chạy thuật toán đồ thị | Có | Có |
| Giới hạn concurrency GDS | Tối đa **4** luồng xử lý theo chính sách GDS CE | Không có giới hạn concurrency cố định của CE; vẫn phụ thuộc tài nguyên thực |
| Model catalog | Tối đa **3** model | Có khả năng quản lý nhiều model hơn và lưu/chia sẻ model |
| Quản lý graph nâng cao, backup/restore graph catalog, Apache Arrow | Hạn chế theo tính năng | Có tính năng bổ sung |
| GDS write workload trong Neo4j cluster | Có giới hạn | Được hỗ trợ theo điều kiện EE và cấu hình |
| License key GDS | Không cần license Enterprise | **Cần license GDS Enterprise hợp lệ** khi tự quản |

**Điểm dễ nhầm:** **Neo4j Database Enterprise không tự động có nghĩa GDS Enterprise đã được kích hoạt.** Một plugin GDS có thể chạy ở chế độ Community nếu chưa cấu hình license GDS hợp lệ. Ngược lại, giới hạn concurrency **4** của GDS CE xuất phát từ **GDS license**, không đơn thuần từ edition của Neo4j Database.

Khi đánh giá nhu cầu thương mại, cần kiểm tra lại điều kiện license, khả năng chạy trên cluster và các giới hạn sản phẩm mới nhất. Chi tiết chính thức: [GDS Introduction — Editions](https://neo4j.com/docs/graph-data-science/current/introduction/), [GDS Enterprise Edition](https://neo4j.com/docs/graph-data-science/current/installation/installation-enterprise-edition/).

### 3.2. Chọn cách triển khai

| Môi trường | Cách có GDS | Điều cần kiểm tra |
| --- | --- | --- |
| **Neo4j Desktop** | Cài plugin **Graph Data Science** từ tab Plugins | Version DB/GDS, trạng thái database, quyền procedure |
| **Neo4j Server tự quản** | Đặt JAR tương thích vào thư mục `plugins`, chỉnh cấu hình rồi restart | License GDS EE nếu dùng, JVM, heap, quyền và bản plugin |
| **Neo4j Docker** | Khai báo plugin `graph-data-science` qua `NEO4J_PLUGINS` | Image Neo4j được ghim version, persistence, bộ nhớ container |
| **Neo4j cluster / Kubernetes** | Cấu hình plugin trên các thành viên theo hướng dẫn sản phẩm/Helm | License, resource, routing, hạn chế workload GDS CE/EE |
| **AuraDS** | Dịch vụ GDS Enterprise được quản lý sẵn | Khả năng mở/mua dịch vụ và quota của tenant |
| **Aura Graph Analytics** | Session phân tích theo nhu cầu, không cài plugin trực tiếp vào DB nguồn | Nguồn dữ liệu, quyền tạo session, dung lượng session, chi phí và write-back |
| **Neo4j Data Science Sandbox** | Môi trường học thử có GDS Community dựng sẵn | Giới hạn thời gian/tài nguyên của sandbox |

Với AuraDB thông thường, **không mặc định** có thể chép JAR vào database được quản lý như máy tự quản. Nếu cần thuật toán đồ thị, hãy kiểm tra khả năng dùng **Aura Graph Analytics** hoặc dịch vụ phù hợp. Theo tài liệu hiện hành, Aura Graph Analytics sử dụng **session tính toán tạm thời**, với luồng *load/projection → run algorithms → tùy chọn write-back → xóa session*. API trên session khác với việc gọi plugin local vào database tùy ý.

Tham khảo [GDS Installation](https://neo4j.com/docs/graph-data-science/current/installation/) và [Aura Graph Analytics](https://neo4j.com/docs/graph-data-science/current/aura-graph-analytics/).

## 4. Điều kiện tương thích phiên bản

GDS là plugin phụ thuộc chặt vào phiên bản Neo4j. **Không chọn GDS mới nhất để cài lên Neo4j cũ** nếu cặp đó không được hỗ trợ.

Một vài **ví dụ phiên bản đã có trong ma trận tương thích chính thức**:

| Neo4j Database | Neo4j GDS tương ứng |
| --- | --- |
| `5.26` | `2.13` |
| `2025.12.1` | `2.25` |
| `2026.02.0` | `2.27` |
| `2026.10.0` | `2026.10` |

Đây là **mốc tham khảo**, không thay cho bảng đầy đủ và không ngụ ý mọi patch version được hỗ trợ như nhau. Từ các bản 2026 mới hơn, tên version GDS cũng chuyển sang dạng `2026.xx`, thay vì chỉ dùng dạng `2.x`. Trước khi cài đặt hoặc nâng cấp:

1. Xác định **version Neo4j Database** đang thực sự chạy.
2. Đối chiếu **Supported Neo4j versions** ở tài liệu GDS đúng thời điểm.
3. Chọn JAR GDS được bundling hoặc liệt kê tương thích với bản database.
4. Kiểm tra JVM, RAM, quyền cấu hình, kế hoạch restart và release notes khi nâng cấp.
5. Đối với Python Client, kiểm tra thêm **ma trận phiên bản client ↔ GDS ↔ Neo4j Python Driver**. Với Java, kiểm tra **Java Driver ↔ Neo4j** riêng; Java Driver không quyết định plugin đã cài hay chưa.

Tài liệu tham khảo: [Supported Neo4j versions](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/), [System Requirements](https://neo4j.com/docs/graph-data-science/current/installation/System-requirements/) và [GDS Python Client Installation](https://neo4j.com/docs/graph-data-science-client/current/installation/).

## 5. Cài GDS trên Neo4j Desktop hoặc Neo4j Server

### 5.1. Neo4j Desktop

Với môi trường học tập:

1. Mở Neo4j Desktop và chọn database instance cần sử dụng.
2. Tìm tab **Plugins**, chọn **Graph Data Science**, cài bản plugin được Desktop cung cấp cho database đó.
3. Kiểm tra phần **Settings**; các cấu hình procedure cần thiết có thể được Desktop thêm tự động.
4. Restart database nếu cần rồi chạy kiểm tra `RETURN gds.version();`.

Không cần tự đặt GDS JAR vào mọi project Java: plugin chạy **phía Neo4j server**, còn ứng dụng kết nối qua driver.

### 5.2. Neo4j Server tự quản

Trên các bản Neo4j hiện đại, gói server thường cung cấp JAR GDS tương thích trong thư mục `products`. Theo hướng dẫn cài trên Neo4j Server:

~~~text
NEO4J_HOME/
  products/neo4j-graph-data-science-<version>.jar
  plugins/
  conf/neo4j.conf
~~~

Các bước chính:

1. Dừng service Neo4j theo quy trình vận hành.
2. Sao chép hoặc chuyển file `neo4j-graph-data-science-<version>.jar` **phù hợp** từ `products` sang `plugins` (hoặc tải bản được hỗ trợ từ nguồn chính thức).
3. Trong `conf/neo4j.conf`, cấu hình procedure:

~~~properties
dbms.security.procedures.unrestricted=gds.*
dbms.security.procedures.allowlist=gds.*
~~~

4. Nếu allowlist **không được bật** hoặc hệ thống có quy tắc riêng, điều chỉnh theo tài liệu Neo4j của bản đang chạy. Nếu đã có allowlist/unrestricted dành cho các procedure khác, **gộp** thêm `gds.*` phù hợp, không vô tình ghi đè các entry hiện hữu.
5. Nếu dùng **GDS Enterprise**, cấu hình **license key riêng** ở đường dẫn tuyệt đối mà Neo4j có thể đọc:

~~~properties
gds.enterprise.license_file=/path/to/gds-license-file
~~~

6. Start/restart Neo4j và kiểm tra version + license + procedure GDS.

**Bảo mật:** Cấu hình `unrestricted=gds.*` cho phép thư viện truy cập chức năng nội bộ cần thiết; đó là cấu hình **máy chủ** do quản trị viên kiểm soát, không có nghĩa mọi user đều cần quyền thực thi mọi procedure. Phân quyền `EXECUTE PROCEDURE`, graph access và các quyền GDS theo tài liệu edition/version.

Nếu cấu hình license chỉ tới file không đọc được, không hợp lệ hoặc đã hết hạn, các lệnh GDS có thể lỗi thay vì âm thầm chuyển về Community. Kiểm tra đường dẫn, quyền file và trạng thái license.

Nguồn: [Neo4j Server GDS installation](https://neo4j.com/docs/graph-data-science/current/installation/neo4j-server/), [GDS Enterprise License](https://neo4j.com/docs/graph-data-science/current/installation/installation-enterprise-edition/).

## 6. Cài GDS trong Docker/Kubernetes

Neo4j Docker hỗ trợ biến môi trường `NEO4J_PLUGINS` nhận danh sách plugin dạng JSON. Ví dụ **chỉ dùng cho môi trường học tập**:

~~~bash
docker run --rm \
  --name neo4j-gds-lab \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH='neo4j/change-this-password' \
  -e NEO4J_PLUGINS='["graph-data-science"]' \
  neo4j:latest
~~~

Trong production, **ghim image tag theo version đã kiểm tra tương thích**, dùng secrets, persistent volume và giới hạn tài nguyên. Không dùng `neo4j:latest` để xây dựng môi trường tái lập dài hạn; tag này có thể chuyển sang phiên bản khác ở lần khởi động tiếp theo.

Biến `NEO4J_PLUGINS` dùng tên **`graph-data-science`**, không phải `gds`. Phần plugin có thể yêu cầu container truy cập mạng để tải gói. Trên Kubernetes, cài plugin qua **Helm chart hoặc cơ chế cấu hình chính thức**, đồng thời bảo đảm các pod cần chạy GDS nhận đúng plugin/config và tài nguyên. Tránh thay đổi phiên bản plugin chỉ trên một thành viên cluster.

Khi dùng GDS Enterprise trong Docker, còn cần **cấp license file** vào container và khai báo đường dẫn qua cấu hình phù hợp, đồng thời tuân thủ license Neo4j Database nếu sử dụng bản Enterprise.

Nguồn: [GDS Docker](https://neo4j.com/docs/graph-data-science/current/installation/installation-docker/), [Neo4j Docker Plugins](https://neo4j.com/docs/operations-manual/current/docker/plugins/).

## 7. Xác minh cài đặt và quyền sử dụng

Sau khi server đã chạy, mở Neo4j Browser hoặc kết nối qua driver đến **database đích**.

~~~cypher
RETURN gds.version() AS gdsVersion;
~~~

Nếu thành công, hàm trả về version GDS đã nạp. Nếu xuất hiện thông báo `Unknown function`, hãy kiểm tra plugin, bản tương thích, cấu hình procedure và tiến trình restart.

Xem các procedure/hàm mà GDS cung cấp:

~~~cypher
CALL gds.list();
~~~

Kiểm tra chế độ license:

~~~cypher
RETURN gds.isLicensed() AS enterpriseLicensed;

CALL gds.license.state();
~~~

`gds.isLicensed() = false` có thể là trạng thái **GDS Community bình thường**. Nếu bạn dự kiến dùng GDS Enterprise thì cần kiểm tra lại license; không tự coi `false` là lỗi cài plugin.

### Checklist xác minh cơ bản

| Câu kiểm tra | Kết quả mong muốn |
| --- | --- |
| Neo4j đang chạy version nào? | Có bản cụ thể từ thông tin DBMS/quản trị |
| JAR/plugin tương thích? | Khớp ma trận Neo4j ↔ GDS |
| `RETURN gds.version()`? | Trả chuỗi version, không báo thiếu hàm |
| `CALL gds.list()`? | Có danh sách procedure/hàm GDS |
| GDS EE cần license? | `gds.isLicensed()` và trạng thái license phù hợp |
| User có quyền chạy procedure? | Có quyền thực thi và truy cập graph cần thiết |
| Có đủ RAM/CPU? | Ước lượng projection và thuật toán đáp ứng tài nguyên |

Lưu ý khi sử dụng **Aura Graph Analytics session**: quy trình tính toán diễn ra trên session được quản lý và có cơ chế API/endpoint riêng; đừng dùng kiểm tra plugin local như yêu cầu cài JAR lên AuraDB nguồn.

## 8. Thực hành: project graph và chạy PageRank

Ví dụ dưới đây dành cho **Neo4j database đã cài plugin GDS**, không phải một session Aura Graph Analytics. Dùng node label và relationship type riêng để tránh nhầm với dữ liệu nghiệp vụ. Chỉ chạy trên database thực hành.

### 8.1. Chuẩn bị dữ liệu thử

~~~cypher
MERGE (an:GdsPracticePerson {personId: 'AN'})
MERGE (binh:GdsPracticePerson {personId: 'BINH'})
MERGE (chi:GdsPracticePerson {personId: 'CHI'})
MERGE (dung:GdsPracticePerson {personId: 'DUNG'})
MERGE (an)-[:GDS_KNOWS]->(binh)
MERGE (an)-[:GDS_KNOWS]->(chi)
MERGE (binh)-[:GDS_KNOWS]->(chi)
MERGE (chi)-[:GDS_KNOWS]->(dung)
MERGE (dung)-[:GDS_KNOWS]->(chi);
~~~

Sơ đồ:

~~~mermaid
flowchart LR
    A["AN"] --> B["BINH"]
    A --> C["CHI"]
    B --> C
    C --> D["DUNG"]
    D --> C
~~~

Lệnh `MERGE` giúp chạy lại tuần tự trên dữ liệu demo. Với hệ thống thật có ghi đồng thời, cần **uniqueness constraint** trên business key và chính sách quản lý relationship để tránh dữ liệu trùng.

### 8.2. Ước lượng bộ nhớ cho projection

~~~cypher
CALL gds.graph.project.estimate(
  'GdsPracticePerson',
  'GDS_KNOWS',
  {}
)
YIELD nodeCount, relationshipCount, requiredMemory
RETURN nodeCount, relationshipCount, requiredMemory;
~~~

`.estimate` dự đoán bộ nhớ; **không tạo** named graph. Dung lượng thực tế phụ thuộc số node, số relationship, orientation, các thuộc tính được project và cấu hình. Nên estimate trước khi tải graph lớn, tránh khiến tiến trình DBMS thiếu heap.

### 8.3. Project graph vào catalog

~~~cypher
CALL gds.graph.project(
  'gdsPractice',
  'GdsPracticePerson',
  'GDS_KNOWS'
)
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

`gdsPractice` là **tên graph trong GDS catalog**, không phải tên database. Graph này chỉ chứa các node nhãn `GdsPracticePerson` và relationship `GDS_KNOWS` trong phạm vi projection.

Nếu đã có graph tên `gdsPractice` của user/session theo quy tắc catalog, lệnh tạo có thể báo lỗi trùng tên. Kiểm tra trước khi project lại:

~~~cypher
CALL gds.graph.list('gdsPractice')
YIELD graphName, nodeCount, relationshipCount
RETURN graphName, nodeCount, relationshipCount;
~~~

### 8.4. Estimate rồi chạy PageRank

~~~cypher
CALL gds.pageRank.stream.estimate('gdsPractice', {})
YIELD requiredMemory
RETURN requiredMemory;
~~~

Sau khi đáp ứng điều kiện bộ nhớ:

~~~cypher
CALL gds.pageRank.stream('gdsPractice', {
  dampingFactor: 0.85,
  maxIterations: 20
})
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).personId AS personId, score
ORDER BY score DESC, personId;
~~~

`PageRank` đánh giá độ quan trọng dựa vào **cấu trúc hướng liên kết** và sự lan truyền điểm. Sơ đồ demo có cạnh ngược giữa `CHI` và `DUNG`, nên việc giải thích kết quả cần nhìn hướng cạnh, không chỉ đếm số lượng neighbor. `gds.util.asNode(nodeId)` ánh xạ ID node trong GDS về node Neo4j trong trường hợp projection từ database nguồn; nếu dùng graph import ngoài Neo4j hoặc session từ xa, cơ chế trả metadata node có thể khác.

### 8.5. Chạy một thuật toán khác

~~~cypher
CALL gds.wcc.stream('gdsPractice')
YIELD nodeId, componentId
RETURN gds.util.asNode(nodeId).personId AS personId, componentId
ORDER BY componentId, personId;
~~~

**WCC (Weakly Connected Components)** gom những node liên thông nếu bỏ qua hướng quan hệ để xác định thành phần yếu. Trong graph demo, tất cả node được kết nối theo đường đi khi không xét hướng nên thường thuộc cùng một thành phần. **Giá trị số của `componentId` không có ý nghĩa nghiệp vụ ổn định**; so sánh việc hai node thuộc cùng component thay vì gắn ý nghĩa vào ID số.

### 8.6. Giải phóng bộ nhớ khi xong

~~~cypher
CALL gds.graph.drop('gdsPractice')
YIELD graphName
RETURN graphName;
~~~

`gds.graph.drop` xóa **named in-memory graph**, không xóa các node `GdsPracticePerson` hay relationship `GDS_KNOWS` đã lưu trong Neo4j. Đây là bước vận hành quan trọng để tránh graph catalog giữ heap sau khi thuật toán đã xong.

## 9. Các execution mode: stream, stats, mutate, write

GDS cung cấp các chế độ kết quả tùy thuật toán. Không phải thuật toán nào cũng hỗ trợ tất cả mode hoặc cùng tên trường output; hãy xem reference của thuật toán cụ thể.

| Chế độ | Tác dụng | Có ghi Neo4j database? | Khi nên chọn |
| --- | --- | --- | --- |
| **`stream`** | Trả kết quả theo các hàng | Không (thuật toán không ghi DB qua mode này) | Khám phá, phân tích, chuyển kết quả ra ứng dụng |
| **`stats`** | Trả thống kê tổng quan từ thuật toán | Không | Đánh giá nhóm/kết quả mà chưa cần từng node |
| **`mutate`** | Ghi kết quả vào **in-memory graph** trong catalog | Không | Chuẩn bị feature cho thuật toán/pipeline tiếp theo |
| **`write`** | Ghi thuộc tính/relationship kết quả về **Neo4j database** | **Có** | Lưu điểm xếp hạng, community, embedding vào graph thật |

Ví dụ `write` của PageRank (chỉ thực hiện khi muốn **thay đổi database**):

~~~cypher
// CẢNH BÁO: Ghi thuộc tính vào các node thật của Neo4j database.
CALL gds.pageRank.write('gdsPractice', {
  writeProperty: 'pageRankScore'
})
YIELD nodePropertiesWritten, writeMillis
RETURN nodePropertiesWritten, writeMillis;
~~~

Khi dùng `write` trong production:

- Kiểm tra user có quyền ghi và workload GDS write mode được **edition/cluster** hỗ trợ.
- Chọn tên thuộc tính output không ghi đè giá trị nghiệp vụ ngoài ý muốn.
- Đánh giá khóa ghi, transaction, tác động đến index, nhu cầu tính lại sau khi graph thay đổi.
- Nên có chiến lược phân quyền, giao dịch và rollback/khôi phục phù hợp.

**Tính toán PageRank không khiến đồ thị nguồn tự thay đổi** khi chỉ gọi `stream`. Đây là khác biệt quan trọng giữa phân tích dữ liệu và cập nhật database.

## 10. Bộ nhớ, CPU, page cache và điều kiện vận hành

GDS dùng **in-memory graph** và trạng thái thuật toán, vì vậy rất nhạy với **heap** của JVM chạy Neo4j. Cần phân biệt:

| Tài nguyên | Vai trò với GDS | Rủi ro |
| --- | --- | --- |
| **Heap JVM** | Lưu graph projection và trạng thái thuật toán | Thiếu heap, lỗi memory, GC kéo dài |
| **Page cache** | Hỗ trợ đọc dữ liệu Neo4j khi project graph và ghi kết quả trở lại | Thiếu page cache làm I/O nhiều; quá lớn có thể cạnh tranh RAM với heap |
| **CPU/concurrency** | Chạy projection và thuật toán song song | Số luồng vượt tài nguyên làm tranh chấp, ảnh hưởng workload giao dịch |
| **Disk/transaction log** | Nơi lưu database, kết quả `write` và log thay đổi | Ghi kết quả lớn gây I/O và tăng dung lượng |
| **Network / driver** | Chuyển kết quả khi dùng `stream` từ xa | Trả hàng triệu score gây áp lực serialization và kết nối |

Trên một máy vừa phục vụ **OLTP** (giao dịch sản xuất) vừa chạy GDS, không nên cấp gần hết RAM cho heap của GDS và giảm page cache vô tội vạ. Tài liệu GDS có hướng dẫn bộ nhớ riêng cho môi trường **phân tích thuần túy**; những đề xuất đó **không tự áp dụng nguyên trạng** lên server giao dịch hỗn hợp.

**Quy trình khuyến nghị:**

1. Chỉ project các label, type và thuộc tính thực sự cần thiết.
2. Dùng `gds.graph.project.estimate` và `gds.<algorithm>.<mode>.estimate`.
3. Ghi nhận `nodeCount`, `relationshipCount`, `requiredMemory`, dung lượng heap khả dụng và tải chung.
4. Chạy thử trên graph nhỏ; đo runtime, CPU, GC, heap và ảnh hưởng truy vấn giao dịch.
5. Giảm `concurrency` hoặc kích thước graph nếu tài nguyên không đủ; đặt lịch các workload phân tích lớn.
6. Drop graph catalog sau khi dùng; lên kế hoạch giải phóng model/graph khác khi không cần.

GDS CE có giới hạn concurrency tối đa 4 theo tài liệu hiện hành, nhưng **đặt concurrency=4 không có nghĩa hệ thống luôn sử dụng 4 lõi trọn vẹn**. Số luồng hiệu dụng, bottleneck và lợi ích song song phụ thuộc thuật toán, phần cứng và dữ liệu.

Nguồn: [GDS Memory Estimation](https://neo4j.com/docs/graph-data-science/current/common-usage/memory-estimation/), [GDS System Requirements](https://neo4j.com/docs/graph-data-science/current/installation/System-requirements/).

## 11. Gọi GDS từ Java Driver và Spring Data Neo4j

Ứng dụng Java **không cần thư viện GDS Java cục bộ để gọi các procedure Cypher** nếu server đã cài plugin; chỉ cần driver Neo4j tương thích. Ví dụ đọc điểm PageRank của một graph đã project:

~~~java
import java.util.List;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class GdsPageRankReader {
    public record Score(String personId, double score) {}

    public static List<Score> readScores(Driver driver) {
        try (Session session =
                     driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> tx.run("""
                    CALL gds.pageRank.stream('gdsPractice')
                    YIELD nodeId, score
                    RETURN gds.util.asNode(nodeId).personId AS personId, score
                    ORDER BY score DESC
                    """).list(row -> new Score(
                    row.get("personId").asString(),
                    row.get("score").asDouble())));
        }
    }
}
~~~

**Điều kiện:** `gdsPractice` đã được project và còn tồn tại trong **graph catalog khả dụng cho user**; bản plugin đã nạp, database đúng và user được cấp quyền gọi GDS. `executeRead` phù hợp với `stream` chỉ đọc; dùng `executeWrite`/transaction thích hợp cho việc project/drop hoặc `write` khi phiên bản/semantics yêu cầu. Một result có nhiều triệu node có thể khiến `list()` dùng nhiều RAM ở phía ứng dụng; nên giới hạn output, xử lý theo luồng hoặc phân trang theo khả năng API khi cần.

Với **Spring Data Neo4j**, có thể gọi Cypher `CALL gds.*` thông qua `Neo4jClient` hoặc repository `@Query` khi kết quả có mapping phù hợp. Nhưng:

- Spring Data Neo4j **không tự cài GDS**; graph projection vẫn nằm ở server/GDS catalog.
- GDS graph catalog là trạng thái analytics trong bộ nhớ, có **vòng đời riêng** với entity `@Node` được repository lưu.
- Chạy `gds.graph.project` và `gds.pageRank.stream` qua hai transaction cần chú ý user, database, định danh graph và quyền; không mặc định graph catalog là session SQL thông thường.
- Kết quả `write` có thể làm thay đổi các property được Spring Data Neo4j đọc lại; cần kiểm soát cache/entity state và policy cập nhật.

Nếu dùng **GDS Python Client**, đó là SDK riêng có yêu cầu version Python, GDS và Neo4j Python Driver; nó chủ yếu giúp thao tác graph catalog, thuật toán và kết quả từ Python. **Không phải** một điều kiện bắt buộc để sử dụng GDS từ Cypher hoặc Java.

## 12. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `Unknown function 'gds.version'` | Plugin chưa nạp, JAR sai chỗ, chưa restart hoặc chặn procedure | Kiểm tra `plugins`, version, cấu hình và log khởi động |
| `There is no procedure with the name gds.graph.project` | Plugin không khả dụng cho DB/user hoặc version/cú pháp khác | `gds.version()`, `gds.list()` và tài liệu đúng bản |
| Lỗi tương thích plugin/server | GDS JAR không khớp Neo4j | Đối chiếu ma trận, dùng JAR đi kèm server hoặc bản hỗ trợ |
| Lỗi license Enterprise | License không hợp lệ, hết hạn, file không đọc được | `gds.isLicensed()`, `gds.license.state()`, đường dẫn và quyền file |
| `Graph with name ... does not exist` | Chưa project, đã drop hoặc không đúng user/database catalog | Kiểm tra `gds.graph.list()`, scope và vòng đời graph |
| `Graph already exists` | Tên graph đã có trong catalog | Dùng tên riêng hoặc drop graph cũ có chủ đích |
| Memory estimation báo vượt giới hạn | Projection/thuật toán cần nhiều heap | Giảm dữ liệu/thuộc tính, tăng tài nguyên phù hợp hoặc tách analytics |
| Algorithm từ chối loại quan hệ/thuộc tính | Projection không phù hợp yêu cầu algorithm | Đọc traits, orientation, weight property và missing values |
| Lỗi quyền | User thiếu quyền gọi procedure hoặc quyền đọc/ghi graph | Kiểm tra roles, quyền thực thi và môi trường quản trị |
| Không thấy thay đổi mới trong kết quả | Graph đã project từ trước, chưa refresh | Project lại/đổi graph theo chính sách cập nhật analytics |

### Checklist kiểm tra khi nhận lỗi trên server

1. Xác minh **database instance nào** đang nhận request từ Java Driver/Browser.
2. Kiểm tra version Neo4j và phiên bản **GDS thực sự đang nạp**.
3. Xem lại file cấu hình `neo4j.conf` và vị trí plugin, các thông báo khởi động.
4. Kiểm tra license và user có quyền.
5. Kiểm tra catalog graph đúng tên, đúng scope, đúng label/type.
6. Estimate bộ nhớ và đánh giá cấu hình heap/page cache/concurrency.
7. Chạy một ví dụ nhỏ bằng `stream` trước khi tăng kích thước hoặc dùng `write`.

## 13. Bài tập tình huống: lựa chọn cách chạy GDS

**Tình huống A:** Nhóm học dùng Neo4j Desktop và muốn thử PageRank trên 1.000 node. Chọn cài plugin tương thích trong Desktop, kiểm tra `gds.version()`, ước lượng bộ nhớ, project subset rồi chạy `stream`; GDS CE thường đủ cho bước học thử.

**Tình huống B:** Dịch vụ production Neo4j Community tự quản có 200 triệu relationship, muốn chạy phân tích đồng thời 32 luồng. GDS CE có giới hạn concurrency 4; chỉ nâng server RAM không bỏ được hạn chế license. Cần đánh giá **GDS EE và điều kiện database/cluster**, hoặc tách workload phân tích sang môi trường/dịch vụ phù hợp, sau đó đo memory và throughput thực tế.

**Tình huống C:** Một doanh nghiệp dùng AuraDB có dữ liệu giao dịch nhưng không thể cài plugin tùy ý. Cần kiểm tra **Aura Graph Analytics** (hoặc AuraDS nếu môi trường đang có và được hỗ trợ) để project dữ liệu vào session phân tích, chạy thuật toán và thiết kế write-back phù hợp. Không dựa vào mẹo chép JAR vào host AuraDB.

**Tình huống D:** Một ứng dụng Spring cần gợi ý quan hệ dựa trên điểm similarity cập nhật mỗi đêm. Có thể tạo job tính GDS theo lịch, ghi kết quả có chủ đích trở lại Neo4j, rồi để API Spring đọc các kết quả đã được kiểm chứng; cần quản lý **freshness** giữa hai lần chạy và tránh để job phân tích lớn cạnh tranh tài nguyên với truy vấn giao dịch.

### Câu hỏi tự kiểm tra

**1. Cài GDS Python Client có làm `RETURN gds.version()` xuất hiện trên Neo4j Server không?**

Không. Plugin GDS cần được cài/có sẵn **phía server** hoặc dùng môi trường GDS service hỗ trợ; Python Client chỉ là client.

**2. Neo4j Database Enterprise đã đủ để sử dụng mọi tính năng GDS Enterprise chưa?**

Chưa. GDS Enterprise self-managed cần license GDS hợp lệ; cần đối chiếu edition sản phẩm và điều kiện triển khai thực tế.

**3. `gds.pageRank.stream` khác `gds.pageRank.write` ở điểm nào?**

`stream` trả kết quả mà không ghi property thuật toán vào database; `write` ghi kết quả trở lại graph trong database.

**4. Graph catalog đã project có tự nhận relationship mới trong Neo4j không?**

Không mặc định. Cần có chính sách cập nhật/reproject graph phù hợp.

**5. Vì sao cần `.estimate` trước khi project graph lớn?**

Vì graph projection và trạng thái thuật toán dùng heap, nếu vượt khả năng bộ nhớ sẽ gây lỗi hoặc áp lực GC cho hệ thống.

**6. Chạy `gds.graph.drop('gdsPractice')` có xóa node gốc không?**

Không. Lệnh drop giải phóng named graph trong catalog GDS; dữ liệu nguồn Neo4j vẫn tồn tại.

## 14. Checklist trước khi sử dụng GDS trong dự án

- [ ] Xác định bài toán thuật toán rõ ràng: centrality, community, path, similarity hay ML.
- [ ] Chọn **môi trường chạy GDS**: plugin Desktop/server/Docker hay Aura analytics service.
- [ ] Xác nhận **Neo4j version ↔ GDS version** trong ma trận hỗ trợ.
- [ ] Phân biệt **Neo4j Database edition** với **GDS CE/EE license**, số luồng và các tính năng nâng cao.
- [ ] Cài plugin đúng nơi, cấu hình procedure và restart khi cần; không cài tùy ý vào database được quản lý.
- [ ] Kiểm tra `gds.version()`, danh sách procedure, license và quyền user.
- [ ] Xác định label, relationship type, orientation và thuộc tính để project graph đúng.
- [ ] Ước lượng **heap, CPU, page cache**, chạy thử trên graph nhỏ và theo dõi GC.
- [ ] Chọn `stream`/`stats`/`mutate`/`write` theo mức thay đổi dữ liệu mong muốn.
- [ ] Lên kế hoạch refresh graph khi dữ liệu nguồn thay đổi, kiểm soát freshness của kết quả.
- [ ] Drop graph không còn dùng, quản lý quyền thao tác và quan sát tải phân tích lên database.
- [ ] Tích hợp Java Driver/Spring Data Neo4j theo mô hình giao dịch/đồng bộ phù hợp.

## Tài liệu tham khảo chính thức

- [Neo4j Graph Data Science — Introduction](https://neo4j.com/docs/graph-data-science/current/introduction/)
- [GDS Installation — Các phương thức triển khai](https://neo4j.com/docs/graph-data-science/current/installation/)
- [Supported Neo4j versions — Ma trận tương thích](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/)
- [GDS Neo4j Server installation](https://neo4j.com/docs/graph-data-science/current/installation/neo4j-server/)
- [GDS Docker installation](https://neo4j.com/docs/graph-data-science/current/installation/installation-docker/)
- [GDS Enterprise Edition — License](https://neo4j.com/docs/graph-data-science/current/installation/installation-enterprise-edition/)
- [Aura Graph Analytics](https://neo4j.com/docs/graph-data-science/current/aura-graph-analytics/)
- [Creating graphs — Projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/)
- [GDS Memory Estimation](https://neo4j.com/docs/graph-data-science/current/common-usage/memory-estimation/)
- [PageRank — Thuật toán và các mode](https://neo4j.com/docs/graph-data-science/current/algorithms/page-rank/)

**Kết luận:** Neo4j Graph Data Science bổ sung một lớp tính toán thuật toán đồ thị mạnh mẽ trên **in-memory projection** của property graph. Muốn sử dụng đúng và an toàn, cần kiểm tra **môi trường triển khai, tương thích phiên bản, license/edition, quyền và tài nguyên**, sau đó mới project graph và chọn mode chạy thuật toán. GDS phát huy giá trị khi kết quả phân tích được gắn với mục tiêu nghiệp vụ, có vòng đời dữ liệu rõ ràng và không làm ảnh hưởng ngoài ý muốn tới các transaction Neo4j đang phục vụ ứng dụng.
