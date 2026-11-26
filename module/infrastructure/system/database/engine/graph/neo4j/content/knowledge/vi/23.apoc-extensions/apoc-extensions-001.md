# APOC là gì và khi nào cần mở rộng ngoài Cypher

**Cypher** là ngôn ngữ chính để truy vấn và cập nhật **property graph** trong Neo4j: node, relationship, label, relationship type và property. Những bài toán phổ biến như tìm mẫu liên kết, lọc theo thuộc tính, tổng hợp, tìm đường đi hay cập nhật đồ thị thường đã có cách giải trực tiếp bằng Cypher. Tuy nhiên, hệ thống thực tế còn gặp nhu cầu xử lý JSON, chuẩn hóa chuỗi, duyệt đồ thị theo quy tắc đặc biệt, tích hợp dữ liệu hoặc thực hiện tác vụ quản trị. **APOC** là một thư viện hàm và thủ tục mở rộng giúp giải quyết nhiều nhu cầu đó ngay từ câu truy vấn.

Bài thuộc chương **APOC và phần mở rộng** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Mục tiêu không phải dùng APOC cho mọi thao tác: cần biết **Cypher đã làm được gì**, **APOC bổ sung khả năng nào**, phiên bản/thành phần nào đang có và đánh đổi về vận hành, bảo mật, hiệu năng. Các ví dụ liên hệ với nhập dữ liệu, truy vấn quan hệ/đường đi, index, Java Driver và Spring Data Neo4j; các tính năng luôn phải đối chiếu với **phiên bản Neo4j, phiên bản APOC và phiên bản ngôn ngữ Cypher** đang chạy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích APOC là gì và phân biệt **function** với **procedure**.
2. Phân biệt **APOC Core** và **APOC Extended**; nhận biết giới hạn về triển khai và phiên bản.
3. Chọn giữa **Cypher thuần**, **APOC** và **xử lý bên ngoài Neo4j** cho từng yêu cầu.
4. Sử dụng những ví dụ nhỏ như `apoc.text.clean`, `apoc.convert.fromJsonMap` và `apoc.path.expandConfig`.
5. Kiểm tra thủ tục/hàm được phép dùng, nêu các rủi ro khi nạp dữ liệu từ URL, truy cập tệp và chạy câu lệnh động.
6. Đánh giá tác động hiệu năng, khả năng bảo trì và phương án thay thế bằng Cypher mới.

## 2. APOC là gì?

APOC là tên viết tắt thường được diễn giải là **Awesome Procedures On Cypher**. Đây là bộ phần mở rộng cung cấp các **user-defined procedures** và **user-defined functions** được triển khai bằng Java, để gọi từ Cypher. Neo4j cung cấp cơ chế gọi những chức năng như vậy, còn APOC đóng gói sẵn nhiều chức năng để người sử dụng không phải tự viết plugin Java từ đầu.

~~~text
        Ứng dụng Java / Spring Data Neo4j / Neo4j Browser
                            |
                            v
                     Truy vấn Cypher
                   /               \
      MATCH, WHERE, MERGE       Gọi phần mở rộng
      WITH, RETURN, CALL {}     apoc.* function/procedure
                   \               /
                    \             /
                        Neo4j
                Node --Relationship--> Node
~~~

APOC **không phải** một cơ sở dữ liệu riêng, **không thay thế** Cypher và cũng **không phải** Graph Data Science (GDS). Một câu truy vấn có thể kết hợp Cypher bình thường với hàm hoặc thủ tục APOC, nhưng mức độ tương thích sẽ phụ thuộc các thành phần đã cài đặt và quyền của tài khoản.

### Function và procedure khác nhau thế nào?

| Khái niệm | Cách dùng phổ biến | Ví dụ | Đặc điểm |
|---|---|---|---|
| **Function** | Trong biểu thức của `RETURN`, `WITH`, `WHERE`, ... | `apoc.text.clean('Hello World!')` | Nhận tham số, trả **một giá trị** có thể dùng trong biểu thức |
| **Procedure** | `CALL ... YIELD ...` | `CALL apoc.path.expandConfig(...) YIELD path` | Có thể trả **luồng hàng**; một số procedure có tác dụng đọc, ghi hoặc thao tác bên ngoài |

Ví dụ hàm chỉ xử lý một chuỗi, không thay đổi đồ thị:

~~~cypher
RETURN apoc.text.clean('Hello World!') AS normalized;
// Kỳ vọng: "helloworld"
~~~

Ví dụ thủ tục duyệt đường đi có thể sinh **nhiều hàng `path`**:

~~~cypher
MATCH (start:Person {personId: $personId})
CALL apoc.path.expandConfig(start, {
    relationshipFilter: 'FOLLOWS>',
    minLevel: 1,
    maxLevel: 2
})
YIELD path
RETURN path;
~~~

Không dùng tên hàm như tên thủ tục, hoặc gọi thủ tục bằng cú pháp biểu thức. Các procedure đọc/ghi cũng có quyền thực thi và tác động giao dịch riêng cần kiểm tra.

## 3. APOC Core và APOC Extended

Từ Neo4j 5, APOC được chia thành hai bộ thư viện:

| Thành phần | Đặc điểm chính | Khi cần quan tâm |
|---|---|---|
| **APOC Core** | Tập chức năng thường dùng, được Neo4j hỗ trợ chính thức | Xử lý dữ liệu, hàm tiện ích, một số truy vấn đường đi và tác vụ trong đồ thị |
| **APOC Extended** | Bộ mở rộng bổ sung do cộng đồng duy trì, có chức năng phụ thuộc thư viện ngoài hoặc phục vụ tình huống chuyên biệt | Khi một thủ tục cần thiết **không nằm trong Core** và môi trường cho phép cài thêm |

Không có một gói **APOC Full** duy nhất cho Neo4j 5 tương tự cách tổ chức phiên bản cũ. **Extended không thay cho Core**; nếu cần hàm của cả hai, môi trường self-hosted có thể phải cài cả hai thành phần tương thích.

**Không suy ra khả năng dùng chỉ từ tên `apoc.*`.** Tên hàm không nói chắc nó thuộc Core hay Extended, có được nạp vào máy chủ, có sẵn trong Neo4j Aura, hoặc có bị giới hạn bởi quyền người dùng hay không. Hãy tra mục thủ tục/hàm tương ứng trong tài liệu **đúng phiên bản**.

### Vì sao phiên bản đặc biệt quan trọng?

- APOC liên quan đến API của Neo4j, nên phải dùng bản **tương thích** với phiên bản Neo4j đang chạy; chỉ nhìn số major `5` là chưa đủ để bảo đảm mọi bản phát hành tương thích.
- Từ thế hệ Neo4j **2025.06**, có hai phiên bản ngôn ngữ cần phân biệt: **Cypher 5** và **Cypher 25**. Các chức năng APOC bị deprecated hoặc thay thế có thể phụ thuộc phiên bản Cypher.
- Ở Neo4j **2026.02+**, Cypher 25 là mặc định cho database thuộc thế hệ phát hành phù hợp. Nếu tài liệu hoặc mã cũ sử dụng hành vi Cypher 5, cần kiểm tra hỗ trợ cụ thể và cú pháp chọn phiên bản.
- Các bản APOC mới tiếp tục chuyển nhiều chức năng trùng lặp sang **Cypher thuần**. Không nên khởi tạo dự án mới dựa vào một thủ tục APOC đã có phương án Cypher tương đương và đang bị deprecated.

Vì các phiên bản được phát hành thường xuyên, **không sao chép nguyên tắc cài đặt từ một bài viết cũ mà bỏ qua bảng tương thích trong tài liệu chính thức**.

## 4. Những nhóm nhu cầu thường khiến người dùng cân nhắc APOC

| Nhu cầu | Cypher thuần đã có gì? | APOC có thể bổ sung gì? | Quyết định ban đầu |
|---|---|---|---|
| Truy vấn node/relationship theo mẫu | `MATCH`, `WHERE`, `OPTIONAL MATCH`, subquery | Tiện ích duyệt đặc biệt | **Ưu tiên Cypher** khi mẫu đã rõ |
| Lọc, tổng hợp, sắp xếp | `WITH`, `count`, `sum`, `ORDER BY` | Hàm trên tập hợp và dữ liệu | Dùng Cypher nếu đủ và dễ tối ưu |
| Chuẩn hóa chuỗi | `trim`, `toLower`, `replace` và các biểu thức chuỗi được hỗ trợ | Nhiều thao tác tiện ích hơn, ví dụ `apoc.text.clean` | So sánh ngữ nghĩa trước khi chọn |
| Chuyển JSON sang cấu trúc Cypher | Xử lý đầu vào của ứng dụng, tham số map/list | `apoc.convert.fromJsonMap` | Hữu ích khi JSON xuất hiện dưới dạng **chuỗi** trong Cypher |
| Duyệt đồ thị theo điều kiện phức tạp | Mẫu đường đi, quantified path patterns, bộ lọc | `apoc.path.expandConfig` với filter, uniqueness, giới hạn | Cân nhắc APOC nếu Cypher khó diễn đạt hoặc khó bảo trì |
| Nhập/xuất dữ liệu | `LOAD CSV`, Java Driver, công cụ import | Procedure nạp JSON, xuất dữ liệu, tích hợp | Kiểm tra quyền mạng/tệp, lượng dữ liệu và schema |
| Cập nhật số lượng lớn | `CALL { ... } IN TRANSACTIONS` và khả năng đồng thời theo phiên bản | `apoc.periodic.iterate` trong các hệ thống cũ | **Ưu tiên tính năng Cypher mới** nếu tương đương |
| Thuật toán đồ thị chuyên sâu | Truy vấn đường đi và phép tổng hợp trong Cypher | Một số tiện ích đồ thị | Kiểm tra **Graph Data Science** khi cần thuật toán phân tích chuyên dụng |
| Hiển thị cấu trúc tạm | Trả node, relationship, map/path | Có chức năng tạo thực thể ảo cho biểu diễn | Chỉ dùng khi công cụ nhận kết quả hỗ trợ |

Sự tồn tại của một thủ tục APOC **không chứng minh** thủ tục đó sẽ nhanh hơn Cypher. Nó giúp **biểu đạt thao tác khó hoặc thiếu sẵn** trong một môi trường xác định.

## 5. Ví dụ 1 — Chuẩn hóa chuỗi và nhận diện giới hạn

Giả sử ứng dụng nhập từ nhiều nguồn có tên không đồng nhất. Hàm sau loại ký tự không phải chữ/số rồi chuyển thành chữ thường:

~~~cypher
RETURN apoc.text.clean('Hello___World!') AS cleaned;
// cleaned = "helloworld"
~~~

Một cách xử lý **khác**, nhưng không hoàn toàn tương đương, bằng Cypher thuần:

~~~cypher
WITH '  Hello___World!  ' AS raw
RETURN toLower(trim(raw)) AS cleaned;
// cleaned = "hello___world!"
~~~

So sánh này cho thấy cần xác định đúng **quy tắc chuẩn hóa**: `trim` chỉ bỏ khoảng trắng ở hai đầu, `toLower` chuyển chữ thường; `apoc.text.clean` còn loại các ký tự không phải chữ/số. Chúng không thể được thay thế cho nhau một cách máy móc.

**Chú ý dữ liệu tiếng Việt:** trước khi áp dụng hàm “clean”, hãy thử thực tế với dấu, Unicode, khoảng trắng, dấu nối và yêu cầu tìm kiếm. Chuẩn hóa để lập **khóa tra cứu** có thể khác chính sách lưu **tên hiển thị**. Không ghi đè dữ liệu gốc khi chưa đánh giá những khác biệt đó.

**Khi nên dùng APOC:** cần một quy tắc chuẩn hóa cụ thể, hàm tương ứng đã được kiểm chứng trên dữ liệu thực và khả năng tương thích được chấp nhận. Nếu tác vụ là xử lý text chuyên sâu, có thể phù hợp hơn khi xử lý ở dịch vụ Java rồi truyền thuộc tính đã chuẩn hóa vào Neo4j.

## 6. Ví dụ 2 — Chuyển chuỗi JSON thành map Cypher

Ứng dụng Java Driver thường có thể truyền trực tiếp tham số kiểu `Map`/`List`. Nhưng trong dữ liệu cũ, đôi khi một thuộc tính chứa **chuỗi JSON**:

~~~text
{"orderId":"O-7","total":125000,"customer":{"id":"C-2"}}
~~~

`apoc.convert.fromJsonMap` có thể chuyển JSON object thành map Cypher:

~~~cypher
WITH apoc.convert.fromJsonMap(
    '{"orderId":"O-7","total":125000,"customer":{"id":"C-2"}}'
) AS doc
RETURN doc.orderId AS orderId,
       doc.total AS total,
       doc.customer.id AS customerId;
~~~

Kết quả mong đợi:

| orderId | total | customerId |
|---|---:|---|
| O-7 | 125000 | C-2 |

Trong ví dụ này, `fromJsonMap` chỉ **chuyển giá trị dữ liệu**, không tạo node hay relationship. Bạn vẫn cần `MERGE`/`CREATE` và kiểm tra khóa nếu quyết định ghi vào graph. Không nên gọi hàm chuyển JSON trên mỗi hàng cực lớn một cách mù quáng; đo chi phí và cân nhắc parse tại ứng dụng khi dữ liệu đến từ HTTP/API.

**Phân biệt** `apoc.convert.fromJsonMap` với `apoc.load.json`: hàm đầu nhận một **chuỗi JSON có sẵn**, còn thủ tục nạp JSON có thể đọc từ URL/nguồn tệp được phép. Thủ tục nạp dữ liệu kéo theo yêu cầu cấu hình, kiểm soát network và quyền truy cập.

## 7. Ví dụ 3 — Duyệt đường đi với quy tắc cấu hình

Cypher đã có nhiều cách mô tả đường đi. APOC hữu ích khi yêu cầu traversal gồm **bộ lọc loại quan hệ, chiều đi, giới hạn số hop và chiến lược không lặp node/relationship** trong một cấu hình.

Tạo một đồ thị ví dụ trên **database thực hành riêng**. Các `MERGE` sau có thể chạy lại mà không tự tạo trùng mẫu node/relationship khi dữ liệu ban đầu nhất quán:

~~~cypher
CREATE CONSTRAINT demo_person_id IF NOT EXISTS
FOR (p:DemoPerson)
REQUIRE p.personId IS UNIQUE;
~~~

~~~cypher
MERGE (a:DemoPerson {personId: 'A'})
MERGE (b:DemoPerson {personId: 'B'})
MERGE (c:DemoPerson {personId: 'C'})
MERGE (d:DemoPerson {personId: 'D'})
MERGE (a)-[:FOLLOWS]->(b)
MERGE (a)-[:FOLLOWS]->(d)
MERGE (b)-[:FOLLOWS]->(c)
MERGE (c)-[:FOLLOWS]->(a);
~~~

Đồ thị chứa vòng `A → B → C → A`. Truy vấn từ `A` theo quan hệ `FOLLOWS` đi ra ngoài, từ 1 đến 2 hop:

~~~cypher
MATCH (a:DemoPerson {personId: 'A'})
CALL apoc.path.expandConfig(a, {
    relationshipFilter: 'FOLLOWS>',
    minLevel: 1,
    maxLevel: 2,
    uniqueness: 'NODE_PATH',
    bfs: true,
    limit: 20
})
YIELD path
RETURN [n IN nodes(path) | n.personId] AS route,
       length(path) AS hops
ORDER BY hops;
~~~

Trên đồ thị mẫu (chỉ chứa các cạnh đã tạo), các đường đi mong đợi có thể gồm `A → B`, `A → D` và `A → B → C`. `NODE_PATH` bảo đảm **không lặp một node bên trong cùng đường đi**, nhưng vẫn có thể trả nhiều đường khác nhau dẫn đến cùng node khi đồ thị phức tạp. Nếu nghiệp vụ muốn mỗi node chỉ được thăm một lần **trên toàn bộ traversal**, cần tìm hiểu `NODE_GLOBAL` và tác động tới các đường đi được trả.

| Tham số | Ý nghĩa |
|---|---|
| `relationshipFilter: 'FOLLOWS>'` | Chỉ đi theo `FOLLOWS` theo chiều ra |
| `minLevel`, `maxLevel` | Số relationship tối thiểu và tối đa trên đường đi |
| `uniqueness: 'NODE_PATH'` | Tránh lặp node **trong từng path** |
| `bfs: true` | Duyệt theo chiều rộng |
| `limit: 20` | Giới hạn số path được trả; **không đồng nghĩa** giới hạn tuyệt đối mọi công việc traversal |

**Lưu ý:** cấu hình khác đi có thể đổi cả **tập kết quả**, không chỉ tốc độ. Chẳng hạn `NODE_GLOBAL` và `NODE_PATH` khác nhau về ngữ nghĩa; không thay chúng chỉ để “tăng hiệu năng” mà không kiểm tra yêu cầu nghiệp vụ. Với đồ thị nhiều nhánh, luôn định rõ giới hạn hop và đo số đường đi/nút được mở rộng. Tài liệu APOC cũng lưu ý `apoc.path.expandConfig` không hỗ trợ dùng trong **parallel runtime** vì đặc điểm an toàn khi chạy đa luồng.

## 8. Ví dụ 4 — Công việc cập nhật theo lô: APOC hay Cypher?

Một số hệ thống cũ dùng `apoc.periodic.iterate` để chọn các hàng bằng câu Cypher thứ nhất rồi cập nhật theo từng lô bằng câu Cypher thứ hai:

~~~cypher
// Ví dụ bảo trì trên database thực hành, có tác dụng GHI dữ liệu.
CALL apoc.periodic.iterate(
    'MATCH (p:DemoPerson) RETURN p',
    'SET p.isActive = true',
    {batchSize: 1000, parallel: false}
)
YIELD batches, total, failedBatches
RETURN batches, total, failedBatches;
~~~

Tùy số bản ghi, procedure sẽ phân batch và trả các thống kê. **Không suy ra** `total` luôn là số node **mới** hoặc số node **đã đổi giá trị**: ở ví dụ này nó là số hàng nguồn được xử lý theo procedure.

Tuy nhiên, **đừng vội lấy APOC làm lựa chọn mặc định cho code mới**:

- Neo4j đã hỗ trợ `CALL { ... } IN TRANSACTIONS` để xử lý truy vấn cập nhật theo lô (cú pháp phụ thuộc phiên bản; cần chạy trong **implicit transaction**).
- Với **Neo4j 2026.04 và Cypher 25**, `apoc.periodic.iterate` đã được đánh dấu **deprecated**; tài liệu hướng tới `CALL { ... } IN CONCURRENT TRANSACTIONS` khi cần xử lý giao dịch đồng thời.
- Các câu Cypher truyền dưới dạng **chuỗi** cho thủ tục như `apoc.periodic.iterate` cần được xây dựng cẩn thận: không nối trực tiếp đầu vào không đáng tin thành câu lệnh Cypher.
- Bất kỳ cách chia lô nào cũng cần thiết kế **idempotency**, kiểm soát lỗi, quan sát commit và kích thước batch trước khi chạy trên dữ liệu quan trọng.

Như vậy, giá trị chính của APOC trong trường hợp này có thể là **bảo trì hệ thống cũ** hoặc sử dụng tùy chọn procedure mà một phiên bản Neo4j cụ thể chưa thay thế phù hợp; khi môi trường đã có cú pháp Cypher tương đương, ưu tiên thử cách thuần Cypher.

## 9. Kiểm tra APOC đã có và có quyền gọi hay chưa

Không đủ cơ sở để khẳng định máy chủ đã có APOC chỉ từ tài liệu. Kiểm tra **trên chính database và bằng tài khoản sử dụng thực tế**:

~~~cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name
LIMIT 30;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name
LIMIT 30;
~~~

Trong môi trường có quản lý quyền, có thể kiểm tra procedure mà tài khoản hiện tại có thể thực thi:

~~~cypher
SHOW PROCEDURES EXECUTABLE BY CURRENT USER
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name;
~~~

Danh sách procedure và function có thể khác nhau. Khi chạy `CALL apoc.path.expandConfig(...)` mà nhận thông báo “procedure not found”, hãy kiểm tra:

1. Tên và cú pháp có đúng **procedure/function** theo tài liệu phiên bản không?
2. Neo4j đã nạp **đúng bản APOC Core hoặc Extended** chưa?
3. Quyền thực thi, allowlist và giới hạn an toàn có cho phép gọi thủ tục không?
4. Tài khoản đang kết nối **đúng DBMS** và chọn đúng database chưa?
5. Chức năng đó đã bị deprecated/removed ở **Cypher 25** hoặc phiên bản cài đặt hiện tại chưa?

Thiếu procedure trên server và thiếu quyền thực thi là **hai nguyên nhân khác nhau**; không tự cấp quyền cao hơn cho ứng dụng chỉ để thử một câu lệnh.

## 10. Nguyên tắc cài đặt và cấu hình an toàn

### 10.1. Cài đúng thành phần

Ở môi trường **self-hosted**, APOC Core có thể được cung cấp trong thư mục `labs` của bản phân phối Neo4j. Quy trình thường là đặt JAR tương thích vào `plugins` rồi **khởi động lại** Neo4j; cách kích hoạt qua Neo4j Desktop hoặc Docker phụ thuộc cách triển khai. APOC Extended cần gói phát hành phù hợp và có thể có dependency bổ sung. Trước khi triển khai, hãy đọc hướng dẫn cài đặt cho **đúng release**.

Ở **Neo4j Aura**, APOC Core có sẵn ở phạm vi được nền tảng hỗ trợ, nhưng người dùng không tự cài một JAR Extended tùy ý. Vì vậy, một giải pháp phụ thuộc Extended trên máy riêng có thể **không chuyển thẳng sang Aura**.

### 10.2. Phân biệt cấu hình Neo4j với cấu hình APOC

Trong Neo4j 5 trở lên, những tùy chọn có tiền tố `apoc.*` thuộc tệp `apoc.conf` (cùng thư mục cấu hình với `neo4j.conf`), hoặc biến môi trường tương ứng; không tiếp tục đặt các khóa `apoc.*` vào `neo4j.conf` theo hướng dẫn cũ. Các tùy chọn quản lý nạp và quyền của procedure thuộc cấu hình bảo mật Neo4j, ví dụ `dbms.security.procedures.allowlist` hay `dbms.security.procedures.unrestricted`, theo phiên bản hỗ trợ.

Ví dụ cấu hình thể hiện **mặc định hạn chế truy cập file**:

~~~properties
# apoc.conf: giá trị minh họa bảo thủ
apoc.import.file.enabled=false
apoc.export.file.enabled=false
~~~

Không bật đọc/ghi toàn bộ hệ thống tệp chỉ để chạy một ví dụ. Nếu cần đọc file thật, cấu hình nơi được phép truy cập phải được giới hạn đúng thư mục và quyền hệ điều hành của tài khoản chạy Neo4j. Tách rõ nguồn dữ liệu **local file**, **HTTPS URL** và **chuỗi JSON đang có sẵn**: mỗi loại có rủi ro và cơ chế cấp quyền khác nhau.

### 10.3. Nguyên tắc quyền tối thiểu và truy cập URL

Một số procedure có khả năng đọc/ghi tệp, gọi URL hoặc thực thi Cypher động. Những khả năng này có thể ảnh hưởng **bảo mật dữ liệu, tài nguyên máy chủ và mạng nội bộ**. Khi dùng các procedure nạp URL như `apoc.load.json`:

- Chỉ cho phép những nguồn dữ liệu cần thiết; cân nhắc hạn chế địa chỉ mạng nội bộ, tránh **SSRF** (server-side request forgery).
- Không đưa URL, tên file hoặc chuỗi Cypher từ người dùng vào procedure nhạy cảm mà thiếu quy tắc xác thực và giới hạn.
- Dùng allowlist/quyền thực thi cụ thể; chỉ unrestrict những procedure thực sự cần.
- Bảo vệ credential ở tầng cấu hình/quản lý bí mật; tránh ghi token trực tiếp vào query được log.
- Giới hạn kích thước payload, timeout và số lượng yêu cầu; xử lý dữ liệu từ nguồn ngoài như dữ liệu **không đáng tin**.

Điều kiện “có thể gọi được” không tương đương “phù hợp để mở trong production”.

## 11. So sánh giải pháp: Cypher, APOC hay Java?

Một ví dụ thực tế: ứng dụng Spring Data Neo4j nhận danh sách đơn hàng từ REST API dạng JSON, muốn chuẩn hóa tên khách hàng, gắn mối quan hệ `PLACED` và tính tổng tiền.

**Phương án Cypher + ứng dụng Java**

1. Ứng dụng gọi API, xác thực response và parse JSON thành DTO/Map.
2. Ứng dụng chuẩn hóa kiểu giá tiền, định danh khách hàng và các trường nghiệp vụ.
3. Java Driver hoặc Spring Data Neo4j truyền tham số vào Cypher, dùng `UNWIND` + `MERGE` với constraint phù hợp.
4. Tổng hợp doanh thu bằng `sum` hoặc truy vấn có subquery khi cần.

Phương án này thường rõ về biên kiểm soát giữa dữ liệu ngoài và cơ sở dữ liệu; việc kiểm thử logic chuyển đổi cũng thuận tiện trong Java.

**Phương án có APOC**

Nếu nguồn JSON đã được lưu trong một property dưới dạng **chuỗi**, `apoc.convert.fromJsonMap` giúp parse ngay trong Cypher. Nếu nghiệp vụ cần duyệt theo label filter và uniqueness phức tạp, `apoc.path.expandConfig` có thể giúp giảm số lượng nhánh truy vấn tự viết. Khi thao tác yêu cầu Core/Extended, cần bảo đảm môi trường triển khai có đúng chức năng.

| Tiêu chí | Cypher thuần | APOC | Java / dịch vụ ứng dụng |
|---|---|---|---|
| Truy vấn quan hệ và tổng hợp | Lựa chọn cơ bản, được planner hiểu trực tiếp | Bổ sung thao tác chuyên biệt | Có thể điều phối, nhưng nên tránh kéo quá nhiều dữ liệu ra ứng dụng |
| Xử lý JSON/API ngoài | Có thể nhận tham số map/list; không phải công cụ ETL tổng quát | Có hàm parse và procedure nạp dữ liệu | Linh hoạt về validation, retry, schema và bảo mật tích hợp |
| Duyệt đường đi có quy tắc đặc biệt | Tùy khả năng phiên bản Cypher | Có cấu hình traversal chi tiết | Thường khó hơn nếu phải tải đồ thị lớn về client |
| Vận hành, nâng cấp | Ít dependency bổ sung | Phải theo phiên bản, Core/Extended và quyền | Có dependency ứng dụng và hạ tầng riêng |
| Kiểm soát quyền dữ liệu ngoài | Theo role và cách triển khai | Cần chú ý procedure truy cập mạng/tệp | Có thể quản lý token, whitelist URL và rate limit ở tầng dịch vụ |

Không có một phương án thắng cho mọi tình huống. **Chọn giải pháp theo vị trí xử lý dữ liệu, tính đúng đắn, khả năng hỗ trợ phiên bản và chi phí vận hành**, sau đó mới tối ưu hiệu năng.

## 12. Hiệu năng và cách kiểm chứng

APOC chạy bên trong Neo4j, nhưng không có nghĩa rằng mọi procedure luôn nhanh hơn giải pháp thuần Cypher. Một số thao tác APOC là “hộp đen” đối với planner: bộ tối ưu Cypher có thể không nhìn sâu vào logic bên trong procedure như khi phân tích biểu thức/mẫu Cypher thuần.

Khi so sánh hai phương án:

1. **Bảo đảm cùng kết quả nghiệp vụ.** Một traversal dùng `NODE_GLOBAL` có thể khác kết quả của traversal dùng `NODE_PATH`; không được so tốc độ mà bỏ qua khác biệt này.
2. **Giữ cùng dữ liệu và tham số** trong các lần đo; tránh thay cả schema/index và query cùng lúc.
3. Dùng `EXPLAIN`, `PROFILE` cho phần Cypher phù hợp để xem kế hoạch, `Rows` và `DB Hits`. Thống kê của các toán tử ngoài procedure có thể không thể hiện chi tiết mọi bước diễn ra bên trong APOC.
4. Đo độ trễ nhiều lượt sau warm-up tương đương; xem bộ nhớ, số hàng trả về và tài nguyên khi traversal/ETL lớn.
5. Với procedure có **tác dụng ghi**, chỉ kiểm thử `PROFILE` trên database thử nghiệm: `PROFILE` **có thực thi** query, nên có thể gây thay đổi dữ liệu thật.
6. Kiểm tra tính tương thích khi nâng Neo4j/APOC/Cypher, nhất là các function/procedure đã deprecated.

Ví dụ theo dõi bước tìm node ban đầu rồi mở đường đi:

~~~cypher
PROFILE
MATCH (a:DemoPerson {personId: 'A'})
CALL apoc.path.expandConfig(a, {
    relationshipFilter: 'FOLLOWS>',
    minLevel: 1,
    maxLevel: 2,
    uniqueness: 'NODE_PATH'
})
YIELD path
RETURN length(path) AS hops, count(*) AS paths
ORDER BY hops;
~~~

Constraint `:DemoPerson(personId)` giúp phần `MATCH` tìm node đầu có khả năng dùng index. Chi phí traversal có thể vẫn lớn nếu node có nhiều relationship; hãy kiểm tra `maxLevel`, `relationshipFilter` và số đường đi trả về. Đừng đánh đồng việc truy vấn **tìm node bắt đầu nhanh** với việc **toàn bộ duyệt đồ thị đã tối ưu**.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra và xử lý |
|---|---|---|
| `Unknown function 'apoc....'` | Thiếu Core/Extended, sai tên hoặc không tương thích | `SHOW FUNCTIONS`; tra đúng tài liệu phiên bản |
| `There is no procedure with the name ...` | Procedure không được nạp hoặc bị giới hạn | `SHOW PROCEDURES`, plugin, allowlist và quyền |
| Chạy được local nhưng không chạy trên Aura | Khả năng cài plugin/permissions khác nhau | Kiểm tra danh sách APOC được Aura hỗ trợ |
| Import file báo bị từ chối | `apoc.import.file.enabled` mặc định hạn chế hoặc đường dẫn không hợp lệ | Kiểm tra `apoc.conf`, import directory và quyền hệ điều hành |
| Duyệt graph quá lâu, quá nhiều path | `maxLevel` không giới hạn rõ, nhánh mở rộng lớn | Giảm hop, lọc hướng/type/label, đo số path |
| Kết quả traversal khác truy vấn Cypher | `uniqueness` và bộ lọc khác ngữ nghĩa | So path cụ thể trên graph nhỏ, chọn đúng quy tắc |
| Hàm cũ bị deprecated hoặc không còn chạy | Nâng Neo4j/Cypher/APOC | Xem migration guide, ưu tiên Cypher tương đương |
| Xử lý JSON làm sai kiểu thuộc tính | JSON, map và property types không tương thích tuyệt đối | Chuẩn hóa số/ngày/id, kiểm tra schema trước `SET`/`MERGE` |
| Job cập nhật theo lô ghi không như mong đợi | Rollback, retry, duplicate hoặc sai ranh giới transaction | Theo dõi commit, kiểm tra idempotency, so số liệu nguồn/đích |

## 14. Bài tập thực hành

### Bài 1 — Khi nào chưa cần APOC?

Bạn cần lấy tất cả sản phẩm có `price >= 100000`, sắp theo giá tăng và trả tối đa 20 hàng. Có nên dùng APOC vì dự án đã cài sẵn Core?

<details>
<summary>Đáp án gợi ý</summary>

Chưa cần. `MATCH (p:Product) WHERE p.price >= 100000 RETURN p ORDER BY p.price LIMIT 20` đã giải được bài toán bằng Cypher. Hãy thiết kế index phù hợp và kiểm tra `EXPLAIN`/`PROFILE` nếu cần tối ưu; APOC không mang lại nhu cầu mở rộng rõ ràng ở đây.

</details>

### Bài 2 — Giải thích kết quả hàm

So sánh:

~~~cypher
RETURN apoc.text.clean('Hello___World!') AS apocValue,
       toLower(trim('Hello___World!')) AS cypherValue;
~~~

Tại sao hai giá trị khác nhau? Khi nào bạn không nên dùng `apoc.text.clean` cho tên người dùng?

<details>
<summary>Đáp án gợi ý</summary>

APOC loại các ký tự không phải chữ/số và chuyển chữ thường nên trả `helloworld`; `trim` không loại dấu gạch dưới nên biểu thức Cypher trả `hello___world!`. Với tên hiển thị, việc loại dấu hoặc ký tự có thể làm mất thông tin; cần phân biệt thuộc tính gốc và khóa tra cứu đã chuẩn hóa.

</details>

### Bài 3 — Thiết kế traversal

Graph có quan hệ `FOLLOWS` nhiều vòng. Bạn muốn lấy các path từ node `A`, tối đa 3 hop, tránh lặp node **trong từng path**. Hãy viết truy vấn dùng `apoc.path.expandConfig`. Nếu thay `NODE_PATH` bằng `NODE_GLOBAL`, điều gì cần kiểm lại?

<details>
<summary>Đáp án gợi ý</summary>

~~~cypher
MATCH (a:DemoPerson {personId: 'A'})
CALL apoc.path.expandConfig(a, {
    relationshipFilter: 'FOLLOWS>',
    minLevel: 1,
    maxLevel: 3,
    uniqueness: 'NODE_PATH'
})
YIELD path
RETURN path;
~~~

`NODE_PATH` kiểm soát lặp node trên mỗi path. `NODE_GLOBAL` kiểm soát việc thăm node trên toàn bộ traversal nên có thể làm thay đổi các path được trả; phải kiểm tra kết quả theo yêu cầu nghiệp vụ trước khi chọn.

</details>

### Bài 4 — Tư duy lựa chọn công cụ

Một service Java nhận JSON từ API ngoài, lưu các node `Order` vào Neo4j và định kỳ cần cập nhật hàng triệu bản ghi. Đề xuất nơi parse JSON, cách chạy import theo lô và trường hợp thật sự cần APOC.

<details>
<summary>Đáp án gợi ý</summary>

Có thể parse/validate JSON trong Java và truyền `Map`/`List` làm tham số; dùng Cypher `UNWIND`, `MERGE` với constraint để ghi. Với dữ liệu lớn, dùng giao dịch theo lô hoặc `CALL { ... } IN TRANSACTIONS` phù hợp phiên bản. Chỉ dùng APOC nếu có yêu cầu cụ thể như dữ liệu đang lưu dạng chuỗi JSON cần parse trong Cypher, traversal có cấu hình riêng, hoặc đang bảo trì một pipeline APOC cũ. Với Cypher 25 mới, kiểm tra deprecation của `apoc.periodic.iterate`.

</details>

## 15. Tài liệu chính thức để đối chiếu phiên bản

- [Neo4j APOC Core — Giới thiệu và phạm vi hỗ trợ](https://neo4j.com/docs/apoc/current/introduction/)
- [Cài đặt APOC Core](https://neo4j.com/docs/apoc/current/installation/) và [APOC Extended](https://neo4j.com/labs/apoc/5/installation/)
- [APOC và phiên bản Cypher](https://neo4j.com/docs/apoc/current/apoc-and-cypher/cypher-versions/)
- [Chuyển các chức năng APOC sang Cypher thuần](https://neo4j.com/docs/apoc/current/apoc-and-cypher/cypher-migration/)
- [Danh mục function/procedure APOC Core](https://neo4j.com/docs/apoc/current/overview/)
- [Cấu hình APOC](https://neo4j.com/docs/apoc/current/config/)

Các trang `current` thay đổi theo release. Khi học hoặc triển khai, chọn đúng phiên bản trên trang tài liệu và kiểm tra chức năng đã được nạp trên máy chủ của mình.

## 16. Ghi nhớ

- **APOC là bộ functions và procedures mở rộng Cypher**, không phải ngôn ngữ hay database thay thế Neo4j.
- **Cypher thuần là lựa chọn đầu tiên** cho những mẫu đọc/ghi và phép tổng hợp mà nó đã hỗ trợ rõ ràng; APOC có giá trị khi giải quyết nhu cầu bổ sung có thực.
- **Core và Extended có phạm vi, mức hỗ trợ và cách triển khai khác nhau**. Cần kiểm tra phiên bản, quyền và giới hạn của môi trường (đặc biệt Aura).
- **APOC gắn với tiến hóa của Cypher**: nhiều chức năng có tương đương trong Cypher 25 và một số đã deprecated; kiểm tra migration guide khi viết mã mới.
- **Đúng kết quả, quyền tối thiểu, khả năng vận hành và dữ liệu đo thực tế** quan trọng hơn việc một câu truy vấn có dùng APOC hay không.
