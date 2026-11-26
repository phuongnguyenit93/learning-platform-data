# Đọc thông báo lỗi, cảnh báo và kết quả thống kê sau truy vấn Neo4j

> **Chương:** Công cụ làm việc  
> **Phạm vi:** Neo4j, mô hình property graph và truy vấn Cypher; quan sát kết quả qua Neo4j Browser, `cypher-shell`, Java Driver và ứng dụng Spring Data Neo4j.

Khi chạy Cypher trên Neo4j, kết quả không chỉ gồm các node, relationship hoặc giá trị của mệnh đề `RETURN`. Hệ thống còn có thể trả về **lỗi**, **thông báo chẩn đoán (notification)**, **thống kê thay đổi dữ liệu** và **kế hoạch thực thi**. Biết đọc đúng từng nhóm thông tin giúp phân biệt truy vấn sai cú pháp, truy vấn hợp lệ nhưng không tìm thấy dữ liệu, truy vấn có rủi ro hiệu năng và truy vấn đã thực sự sửa đồ thị.

## 1. Phân biệt bốn loại tín hiệu

| Tín hiệu | Ý nghĩa | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|---|
| **Error / exception** | Neo4j không hoàn thành thao tác theo yêu cầu; truy vấn hoặc giao dịch có thể bị hủy | Hỏng ở cú pháp, tham số, kiểu dữ liệu, ràng buộc, quyền hay kết nối? | Thiếu `$userId`; vi phạm uniqueness constraint |
| **Notification / warning** | Truy vấn thường vẫn chạy được, nhưng máy chủ phát hiện điều đáng lưu ý | Có lỗi gõ tên, mẫu đồ thị không kết nối, API sắp lỗi thời, hoặc kế hoạch tốn kém? | Nhãn chưa tồn tại; tích Descartes; cú pháp bị deprecated |
| **Result records** | Các bản ghi mà `RETURN`/`YIELD` thực sự trả về | Trả về bao nhiêu hàng, giá trị gì? | Một hàng `count = 0` hoặc 10 hàng chứa tên người dùng |
| **Summary / query statistics** | Thông tin sau khi tiêu thụ truy vấn: số thao tác ghi, thời gian và/hoặc metadata | Có tạo/xóa node, quan hệ, thuộc tính? | `nodesCreated = 2`, `relationshipsCreated = 1` |

**Ba nhận định dễ nhầm:**

- **Không có hàng trả về không đồng nghĩa có lỗi.** `MATCH` không tìm thấy mẫu phù hợp có thể trả về 0 hàng và không phát sinh exception.
- **Có cảnh báo không đồng nghĩa thất bại.** Truy vấn vẫn có thể thành công nhưng cần sửa vì tính đúng đắn hoặc hiệu năng.
- **Có hàng trả về không đồng nghĩa đã thay đổi dữ liệu.** `RETURN count(n)` có thể trả về một hàng dù không có thao tác ghi nào.

Vị trí và tên hiển thị của thông tin khác nhau theo Neo4j Browser, `cypher-shell`, Driver, cấu hình và phiên bản Neo4j. Vì vậy, nên dựa vào **ý nghĩa và trường dữ liệu**, không phụ thuộc nguyên văn một dòng thông báo minh họa.

## 2. Đọc lỗi: xác định nguyên nhân trước khi sửa

Thông báo lỗi thường cung cấp một số thành phần:

| Thành phần | Cách đọc |
|---|---|
| **Mã lỗi / mã trạng thái** | Giúp phân nhóm lỗi để tra cứu hoặc phân loại trong log; ở nhiều phiên bản có mã dạng `Neo.ClientError...`, `Neo.TransientError...` hoặc mã GQLSTATUS |
| **Thông điệp** | Mô tả nguyên nhân trực tiếp, ví dụ thiếu tham số, biến chưa được khai báo, vi phạm constraint |
| **Vị trí** | Dòng, cột hoặc đoạn Cypher gây vấn đề nếu Neo4j xác định được |
| **Ngữ cảnh** | Truy vấn, tham số được truyền, database, giao dịch và ngữ cảnh quyền của tài khoản thực thi |
| **Exception phía ứng dụng** | Driver có thể bọc lỗi máy chủ thành exception; lỗi mạng hoặc timeout đôi khi phát sinh trước khi máy chủ trả về mã Cypher |

Không nên giả định mọi lỗi đều có đủ các trường trên hoặc mọi phiên bản sẽ phát cùng một mã lỗi.

### 2.1. Lỗi cú pháp và tên biến

Ví dụ cố ý viết sai từ khóa:

~~~cypher
MATC (p:Person)
RETURN p.name;
~~~

Neo4j báo lỗi cú pháp và thường chỉ tới vùng bắt đầu bằng `MATC`. Sửa thành:

~~~cypher
MATCH (p:Person)
RETURN p.name;
~~~

Một lỗi khác là dùng biến chưa khai báo:

~~~cypher
MATCH (p:Person)
RETURN user.name;
~~~

Biến đã được đặt tên là `p`, không phải `user`. Khi đọc thông báo, kiểm tra chính xác tên biến, phạm vi sau `WITH` và vị trí do máy chủ chỉ ra. Tránh sửa mò toàn bộ câu truy vấn trước khi xác định token lỗi.

### 2.2. Lỗi thiếu tham số và sai kiểu dữ liệu

~~~cypher
MATCH (u:User)
WHERE u.id = $userId
RETURN u.name;
~~~

`$userId` là **tham số**, không phải chuỗi ký tự. Nếu client không truyền `userId`, Neo4j sẽ báo thiếu tham số. Khi chạy qua Java Driver, truyền dưới dạng map:

~~~java
Map<String, Object> params = Map.of("userId", "u-101");
session.run(
    "MATCH (u:User) WHERE u.id = $userId RETURN u.name AS name",
    params
);
~~~

Nếu giá trị lưu trong `u.id` là số nhưng ứng dụng truyền một chuỗi, truy vấn có thể chạy mà không khớp bản ghi; không phải mọi lỗi kiểu dữ liệu đều tạo exception. Khi nghi ngờ, kiểm tra schema, cách nhập dữ liệu và kiểu của tham số. Không ghép giá trị người dùng trực tiếp vào chuỗi Cypher; **tham số hóa** làm rõ kiểu dữ liệu và tránh injection.

### 2.3. Lỗi ràng buộc, giao dịch và quyền

Giả sử database có uniqueness constraint cho `User.id`:

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.id IS UNIQUE;
~~~

Hai lần `CREATE` một node có cùng `id` sẽ vi phạm ràng buộc:

~~~cypher
CREATE (:User {id: 'u-101'});
CREATE (:User {id: 'u-101'});
~~~

Nếu mỗi lệnh là một giao dịch riêng, lệnh đầu có thể đã commit còn lệnh thứ hai thất bại. Nếu cùng một giao dịch tường minh và một câu lệnh làm hỏng giao dịch, phải kiểm tra trạng thái giao dịch và rollback theo cơ chế client; **đừng suy luận rằng mọi lệnh trước đó đều đã commit**.

Nếu cần tìm hoặc tạo node theo khóa duy nhất, có thể dùng:

~~~cypher
MERGE (u:User {id: $userId})
ON CREATE SET u.createdAt = datetime()
RETURN u;
~~~

`MERGE` không thay thế việc thiết kế constraint phù hợp khi có nhiều phiên ghi đồng thời. Lỗi quyền cần kiểm tra role, database và quyền thao tác thực tế; không giải quyết bằng cách sửa cú pháp `MATCH` hay `CREATE`.

### 2.4. Phân loại để quyết định có retry hay không

| Nhóm vấn đề | Dấu hiệu thường gặp | Hành động ưu tiên |
|---|---|---|
| Cú pháp, biến, tham số | Query không parse được; thiếu tên biến/param | Sửa Cypher hoặc map tham số |
| Schema / constraint | Khóa trùng, dữ liệu vi phạm quy tắc | Kiểm tra giá trị và constraint, cân nhắc `MERGE` |
| Quyền / database | Không được phép đọc/ghi hoặc chọn nhầm database | Kiểm tra quyền, tên database và thông tin kết nối |
| Mạng, leader chuyển đổi, lỗi tạm thời | Connection bị gián đoạn, transaction không thể hoàn tất tạm thời | Xác định khả năng retry; áp dụng cơ chế retry có kiểm soát cho giao dịch phù hợp |
| Sai kỳ vọng nhưng không có exception | Trả về 0 hàng hoặc 0 lần cập nhật | Kiểm tra dữ liệu, hướng quan hệ, label và giá trị tham số |

Mã thuộc nhóm `TransientError` có thể giúp xác định lỗi tạm thời, nhưng **không retry mù quáng** một thao tác ghi không có tính an toàn khi chạy lại. Với Java Driver, các transaction function như `executeRead`/`executeWrite` hỗ trợ retry cho các trường hợp đủ điều kiện; callback phải phù hợp với khả năng được gọi lại. Lỗi cú pháp hay vi phạm constraint thường cần sửa nguyên nhân thay vì lặp lại cùng truy vấn.

## 3. Đọc cảnh báo và notification

**Notification** là chẩn đoán của Neo4j đối với một truy vấn hợp lệ hoặc quá trình lập kế hoạch/thực thi. Tùy phiên bản, mỗi notification có thể chứa:

- **Severity:** mức nghiêm trọng, chẳng hạn `WARNING` hoặc `INFORMATION`.
- **Code / GQLSTATUS:** định danh cho hệ thống hoặc nhóm công cụ.
- **Title và description:** tên ngắn và phần giải thích.
- **Position:** vị trí liên quan trong Cypher, nếu có.
- **Category / classification:** nhóm như hiệu năng, kiểu truy vấn, deprecation, schema; tên và cách tổ chức thay đổi theo phiên bản.

Đừng chỉ dựa vào màu sắc biểu tượng trên giao diện. Mức severity và phần mô tả mới là cơ sở để xử lý.

### 3.1. Nhãn, loại quan hệ hoặc thuộc tính chưa có

~~~cypher
MATCH (u:Uesr)
RETURN u.name;
~~~

Nếu thực tế chỉ có nhãn `User`, đây có thể là lỗi gõ. Neo4j có thể thông báo nhãn chưa tồn tại, và truy vấn thường cho 0 hàng. Tuy nhiên, một nhãn mới dùng cho chức năng chưa có dữ liệu cũng là trường hợp hợp lệ. Hãy xác minh tên dự kiến và dữ liệu đã nạp trước khi đổi query.

Tương tự, gõ sai loại quan hệ:

~~~cypher
MATCH (u:User)-[:PURCHASEDD]->(o:Order)
RETURN o.id;
~~~

có thể không khớp gì dù đồ thị đang có `:PURCHASED`. Trong property graph, **nhãn, loại quan hệ và hướng mũi tên** đều quyết định cách khớp mẫu. Đọc cảnh báo cùng với kết quả thực tế để không bỏ sót sự cố.

### 3.2. Tích Descartes và mẫu đồ thị không liên kết

~~~cypher
MATCH (u:User), (p:Product)
RETURN u.id, p.id;
~~~

Hai mẫu `u` và `p` không có điều kiện kết nối. Nếu có 1.000 `User` và 2.000 `Product`, số cặp lý thuyết lên tới 2.000.000; điều này có thể được phản ánh qua cảnh báo Cartesian product và kế hoạch thực thi. Nếu mục đích là tìm sản phẩm mà người dùng đã xem, mô tả quan hệ:

~~~cypher
MATCH (u:User)-[:VIEWED]->(p:Product)
RETURN u.id, p.id;
~~~

Tích Descartes không luôn sai: đôi khi nghiệp vụ cố ý kết hợp mọi cặp. Khi đó phải ước lượng kích thước tập trung gian, áp dụng bộ lọc phù hợp và có chủ đích về chi phí.

### 3.3. Cảnh báo về hiệu năng hoặc tính tương thích

Các nhóm cần lưu ý gồm truy vấn dùng cấu trúc bị deprecated, kế hoạch quét nhiều node, thiếu điều kiện liên kết hoặc một gợi ý/hint không áp dụng được. Tuy nhiên, **không có cảnh báo không có nghĩa truy vấn nhanh**, và một node scan không tự động là vấn đề: scan có thể hợp lý khi cần đọc phần lớn dữ liệu.

Ví dụ khi truy cập người dùng theo email:

~~~cypher
MATCH (u:User)
WHERE u.email = $email
RETURN u.name;
~~~

Để xem database có index phù hợp hay không, người học có thể dùng:

~~~cypher
SHOW INDEXES;
~~~

Kiểm tra các index liên quan đến label `User` và property `email`, rồi xem kế hoạch `EXPLAIN`/`PROFILE`. Không nên mặc định tạo index cho mọi property: việc tạo và duy trì index có chi phí, và nhu cầu phụ thuộc khối lượng dữ liệu, độ chọn lọc, loại truy vấn.

**Lưu ý phiên bản:** Từ các bản Neo4j/Driver mới, các đối tượng trạng thái theo chuẩn GQLSTATUS ngày càng được dùng để biểu diễn cả trạng thái thành công, không có dữ liệu, cảnh báo và ngoại lệ. Tên API và các notification hiển thị có thể thay đổi. Một số client còn cho phép lọc mức severity hoặc loại notification, nên **không thấy thông báo trên client không khẳng định server chưa từng phát ra thông báo**.

## 4. Đọc thống kê sau truy vấn

Neo4j có thể báo **query statistics** hoặc **summary counters** cho thao tác đã thực thi. Với câu lệnh ghi, những trường sau đặc biệt hữu ích:

| Counter | Cách hiểu |
|---|---|
| `nodesCreated` | Số node được tạo |
| `nodesDeleted` | Số node bị xóa |
| `relationshipsCreated` | Số relationship được tạo |
| `relationshipsDeleted` | Số relationship bị xóa |
| `propertiesSet` | Số thao tác đặt/cập nhật property được thống kê |
| `labelsAdded` / `labelsRemoved` | Số thao tác thêm/bỏ nhãn |
| `indexesAdded` / `indexesRemoved` | Số index được thêm/bỏ bởi câu lệnh schema |
| `constraintsAdded` / `constraintsRemoved` | Số constraint được thêm/bỏ |
| `containsUpdates` | Có phát sinh cập nhật dữ liệu hay không |
| `containsSystemUpdates` | Có cập nhật metadata/system được nhận diện hay không, nếu API hỗ trợ |

Tên trường ở đây là dạng API Java Driver; Browser hay `cypher-shell` có thể trình bày bằng từ ngữ khác. Counter thể hiện **thao tác được hệ thống ghi nhận**, không phải bằng chứng một quy tắc nghiệp vụ đã đạt đúng kết quả. Chẳng hạn, `propertiesSet` không cho biết tên thuộc tính nào được đổi hay giá trị cũ/mới.

### 4.1. Thực hành: đọc và ghi là hai loại kết quả khác nhau

Đọc số node:

~~~cypher
MATCH (p:Person)
RETURN count(p) AS total;
~~~

Kết quả là **một hàng** có cột `total`, kể cả khi `total = 0`. Vì câu lệnh chỉ đọc, các counter ghi thường bằng 0. Giá trị `total = 100` **không có nghĩa** đã tạo 100 node.

Ghi dữ liệu:

~~~cypher
MATCH (p:Person)
WHERE p.active IS NULL
SET p.active = true
RETURN count(p) AS matched;
~~~

Nếu có 3 người phù hợp, `matched` có thể là 3 và `propertiesSet` thường phản ánh ba thao tác đặt `active`. Nếu không có node phù hợp, câu lệnh vẫn hợp lệ, `matched = 0` và không có cập nhật. Khi kết quả khác kỳ vọng, kiểm tra cả **số hàng/bản ghi** lẫn **counter**.

Tạo một cạnh trong đồ thị:

~~~cypher
CREATE (a:City {name: 'Hà Nội'})
CREATE (b:City {name: 'Đà Nẵng'})
CREATE (a)-[:CONNECTED_TO]->(b);
~~~

Với database và quyền ghi bình thường, ví dụ này tạo 2 node, 1 relationship và các property `name` tương ứng. Kết quả sau câu lệnh có thể không có bản ghi trả về vì không có `RETURN`, nhưng counters vẫn cho biết các thao tác đã thực hiện. **Không chạy lặp lại vô ý** trên database dùng chung: `CREATE` tạo phần tử mới mỗi lần.

### 4.2. Khi summary và kết quả có vẻ mâu thuẫn

| Quan sát | Giải thích thường gặp | Bước kiểm tra |
|---|---|---|
| 0 rows, counters = 0 | `MATCH` không khớp hoặc query không có `RETURN` và cũng không ghi | Dữ liệu, label, chiều quan hệ, `WHERE`, tham số |
| 1 row chứa `count = 0` | Hàm tổng hợp `count()` trả về một hàng cho tập rỗng | Phân biệt số hàng với giá trị cột |
| 0 rows, `nodesCreated > 0` | Query `CREATE` không dùng `RETURN` | Kiểm tra counters, sau đó xác nhận dữ liệu nếu cần |
| Nhiều rows, counters = 0 | Query đọc thuần túy | Đây là kết quả bình thường |
| `propertiesSet > 0` nhưng giá trị nghiệp vụ không như mong đợi | Truy vấn ghi property, nhưng logic `WHERE`/`SET` hoặc kỳ vọng dữ liệu có thể sai | Kiểm tra một số bản ghi đại diện và logic ứng dụng |

Khi có exception, không nên suy diễn counters của một query chưa hoàn tất thành bằng chứng dữ liệu đã được commit. Cần xem ranh giới transaction và trạng thái commit/rollback.

## 5. Dùng EXPLAIN và PROFILE để hiểu cảnh báo hiệu năng

### 5.1. EXPLAIN: xem kế hoạch mà chưa chạy truy vấn

~~~cypher
EXPLAIN
MATCH (u:User)
WHERE u.email = $email
RETURN u.name;
~~~

`EXPLAIN` yêu cầu lập **execution plan**: operator nào sẽ quét nhãn, dùng index, mở rộng relationship, sắp xếp hay kết hợp dữ liệu. Vì không thực thi phần truy vấn, `EXPLAIN` không dùng để kết luận số hàng thực tế hoặc số lần ghi đã xảy ra. Nó hữu ích để kiểm tra ý định trước một câu lệnh ghi tốn kém.

### 5.2. PROFILE: thực thi và đo trên dữ liệu thực

~~~cypher
PROFILE
MATCH (u:User)
WHERE u.email = $email
RETURN u.name;
~~~

`PROFILE` thực sự chạy truy vấn và bổ sung số liệu theo operator, chẳng hạn:

- **Rows:** số hàng đi qua operator, cần đối chiếu ước lượng và số thực tế.
- **DB Hits:** chỉ dấu lượng truy cập dữ liệu của operator; giá trị cao ở phần dữ liệu lớn có thể gợi ý điểm nghẽn.
- **Operator:** `NodeByLabelScan`, `NodeIndexSeek`, `Expand`, `Filter`, `Sort`, `CartesianProduct`… tên cụ thể tùy phiên bản và kế hoạch.
- **Thời gian / bộ nhớ / page cache:** một số phiên bản hoặc môi trường có thêm số liệu; không mặc định mọi trường đều hiện diện.

**Cảnh báo quan trọng:** `PROFILE` **thực thi cả truy vấn ghi**. Vì vậy, `PROFILE CREATE ...`, `PROFILE SET ...` hoặc `PROFILE DELETE ...` có thể thay đổi dữ liệu thật. Nên dùng `EXPLAIN` trước; chỉ đo bằng `PROFILE` với query ghi khi đã chủ động kiểm soát transaction, dữ liệu kiểm thử và khả năng hoàn tác.

Đọc execution plan từ operator có chi phí lớn, xem đó là quét toàn tập có hợp lý không, liệu filter được áp dụng đủ sớm không, có nhiều hàng trung gian hoặc Cartesian product không. Một kế hoạch khác đi không tự động đồng nghĩa nhanh hơn: cần so sánh trên cùng dữ liệu, tham số và điều kiện tải.

## 6. Quan sát thông báo trong các công cụ

| Công cụ | Nơi cần tìm | Lưu ý |
|---|---|---|
| **Neo4j Browser** | Khung kết quả, danh sách cảnh báo/thông tin và phần query statistics hoặc plan | Một truy vấn có thể xem dạng table/graph/text; muốn xem chi tiết tối ưu dùng `EXPLAIN`/`PROFILE` |
| **cypher-shell** | Dữ liệu in ra terminal, lỗi ở stderr và các dòng thống kê/thông báo khi chế độ/phiên bản hỗ trợ | Nội dung và cách format phụ thuộc cờ chạy, phiên bản shell và máy chủ |
| **Neo4j Java Driver** | `Result`, `ResultSummary`, `SummaryCounters`, notification hoặc GQL status; exception | Phải tiêu thụ kết quả để truy cập summary cuối cùng và xử lý exception |
| **Spring Data Neo4j** | Entity/DTO/repository result, exception và logging; dùng Driver khi cần summary chi tiết | Repository thường ưu tiên ánh xạ dữ liệu; đừng mặc định nó trả về toàn bộ counters/notifications |

### 6.1. Ví dụ Java Driver: đọc bản ghi, cảnh báo và counter

Ví dụ sau minh họa API thông dụng của Java Driver 5.x. Khi dùng một bản Driver mới hơn, kiểm tra API trạng thái GQLSTATUS của phiên bản đó; các phương thức notification cũ có thể bị deprecated hoặc thay đổi.

~~~java
import java.util.Map;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.exceptions.Neo4jException;
import org.neo4j.driver.summary.ResultSummary;
import org.neo4j.driver.summary.SummaryCounters;

public class QueryFeedbackExample {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String user = System.getenv("NEO4J_USER");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver =
                     GraphDatabase.driver(uri, AuthTokens.basic(user, password));
             Session session = driver.session(
                     SessionConfig.forDatabase("neo4j"))) {

            Result result = session.run(
                    "MATCH (p:Person) WHERE p.city = $city " +
                    "RETURN p.name AS name LIMIT 10",
                    Map.of("city", "Hà Nội")
            );

            int rows = 0;
            while (result.hasNext()) {
                var record = result.next();
                System.out.println(record.get("name").isNull()
                        ? "(null)" : record.get("name").asString());
                rows++;
            }

            ResultSummary summary = result.consume();
            SummaryCounters counters = summary.counters();
            System.out.println("Returned rows: " + rows);
            System.out.println("Has updates: " + counters.containsUpdates());
            System.out.println("Nodes created: " + counters.nodesCreated());
            System.out.println("Relations created: "
                    + counters.relationshipsCreated());
            System.out.println("Properties set: " + counters.propertiesSet());

            for (var notification : summary.notifications()) {
                System.out.println("[" + notification.severity() + "] "
                        + notification.code() + " - "
                        + notification.description());
            }
        } catch (Neo4jException e) {
            System.err.println("Neo4j error code: " + e.code());
            System.err.println("Message: " + e.getMessage());
            throw e;
        }
    }
}
~~~

Các biến môi trường phải được cấu hình trước khi chạy; tên database `neo4j` trong ví dụ phải được thay bằng database thực tế nếu khác. Ví dụ dùng truy vấn chỉ đọc nên các counter cập nhật thường bằng 0. Vòng lặp tiêu thụ records trước `result.consume()` để không vô tình bỏ qua dữ liệu cần xử lý; `consume()` cho phép lấy summary sau khi đọc xong.

**Khi ghi log ở ứng dụng:** nên lưu mã lỗi, loại exception, tên truy vấn hoặc mã định danh truy vấn, database, thời gian và số liệu phù hợp. Tránh ghi mật khẩu, token, toàn bộ tham số chứa dữ liệu cá nhân hay thông tin nhạy cảm. Với lỗi phát sinh khi kết nối, có thể không có mã lỗi do server cung cấp; khi đó ghi exception category và thông tin kết nối đã loại bỏ bí mật.

### 6.2. Ứng dụng Spring Data Neo4j

Khi gọi repository như `findById` hoặc một phương thức dùng `@Query`, kết quả thường là entity, projection, số lượng hoặc ngoại lệ của tầng persistence. Nếu bài toán yêu cầu đọc **notification, execution plan hoặc summary counters** ở mức chi tiết, hãy thiết kế một luồng truy vấn chuyên biệt có truy cập Java Driver/Neo4jClient phù hợp với kiến trúc ứng dụng. Đặc biệt, không mở một `Session` riêng bên trong một service đang dùng transaction do Spring quản lý rồi mặc định coi cả hai nằm trong cùng giao dịch; cần kiểm tra cách tích hợp transaction của dự án.

## 7. Quy trình chẩn đoán một kết quả bất thường

1. **Ghi nhận đúng hiện tượng.** Có exception, notification, 0 hàng, counter lạ hay chạy chậm? Đừng gộp tất cả thành “truy vấn lỗi”.
2. **Cố định ngữ cảnh.** Xác định database, phiên bản Neo4j/Driver, câu Cypher, tham số và kiểu dữ liệu, tài khoản thực thi, transaction; che thông tin nhạy cảm.
3. **Nếu có lỗi, đọc mã, message và vị trí trước.** Sửa syntax/param/constraint/quyền; quyết định retry dựa trên loại lỗi và tính an toàn của thao tác.
4. **Nếu không lỗi mà sai dữ liệu, kiểm tra mẫu đồ thị.** Đối chiếu tên label, relationship type, hướng relationship, điều kiện `WHERE` và dữ liệu thật bằng một truy vấn đọc nhỏ.
5. **Nếu có warning hoặc truy vấn chậm, dùng `EXPLAIN` rồi `PROFILE` cho truy vấn an toàn.** Tìm scan không cần thiết, Cartesian product, lượng rows trung gian và DB Hits bất thường.
6. **Nếu có thao tác ghi, kiểm tra counters rồi xác minh mục tiêu nghiệp vụ.** Số node/relationship/property thay đổi cần phù hợp kỳ vọng; dùng query đọc để xác nhận dữ liệu được tạo/cập nhật.
7. **Sau khi sửa, chạy lại với cùng tham số và so sánh.** So kết quả, counter, notification và plan; ghi lại nguyên nhân để tránh tái diễn.

### Ví dụ A: truy vấn chạy thành công nhưng không tìm thấy đơn hàng

~~~cypher
MATCH (u:User {id: $userId})-[:PLACED]->(o:Order)
RETURN o.id AS orderId;
~~~

Nếu trả về 0 hàng và không báo lỗi: kiểm tra `$userId` có đúng kiểu/giá trị không, `User` có tồn tại không, loại quan hệ có thực sự là `PLACED` không, cạnh có hướng từ `User` sang `Order` không. Có thể tách thành truy vấn nhỏ:

~~~cypher
MATCH (u:User {id: $userId})
RETURN u.id;
~~~

Sau đó tìm riêng quan hệ của node. Không tự đổi thành truy vấn quét toàn bộ đồ thị trên môi trường dữ liệu lớn để “tìm thử”.

### Ví dụ B: thấy Cartesian product và số bản ghi rất lớn

~~~cypher
MATCH (u:User), (o:Order)
WHERE u.region = 'VN'
RETURN u.id, o.id;
~~~

Điều kiện `u.region` không liên kết `o` với `u`. Kiểm tra xem bài toán cần mọi cặp hay đơn hàng của người dùng. Nếu cần đơn hàng thật sự của mỗi người:

~~~cypher
MATCH (u:User)-[:PLACED]->(o:Order)
WHERE u.region = 'VN'
RETURN u.id, o.id;
~~~

Kiểm tra kế hoạch mới để xác nhận số rows trung gian đã phù hợp.

### Ví dụ C: muốn cập nhật 10 node, counters báo 0

~~~cypher
MATCH (p:Person)
WHERE p.status = 'PENDING'
SET p.status = 'ACTIVE'
RETURN count(p) AS updated;
~~~

Nếu `updated = 0` và `propertiesSet = 0`, khả năng cao không có node khớp `Person` + `status = 'PENDING'`. Hãy chạy bản chỉ đọc:

~~~cypher
MATCH (p:Person)
RETURN p.status AS status, count(*) AS total
ORDER BY total DESC;
~~~

Nhờ vậy có thể phát hiện dữ liệu đang lưu `'pending'`, property bị thiếu hoặc label không đúng. Nếu `updated > 0`, so sánh counters và đọc lại dữ liệu để xác minh yêu cầu nghiệp vụ.

## 8. Bài tập tự kiểm tra

**Bài 1.** Truy vấn `MATCH (n:Person) RETURN count(n) AS total` trả về một hàng với `total = 0`, không có notification, mọi counter ghi bằng 0. Có lỗi không?  
**Đáp án:** Không. Truy vấn tổng hợp đã thực thi thành công trên tập rỗng; một hàng `count` khác với số node tìm thấy.

**Bài 2.** `EXPLAIN CREATE (:City {name: 'Huế'})` có tạo node không? `PROFILE` với cùng lệnh thì sao?  
**Đáp án:** `EXPLAIN` chỉ lập kế hoạch nên không tạo node; `PROFILE` thực thi nên có thể tạo node thật.

**Bài 3.** Một query `MATCH (u:User), (p:Product) RETURN count(*)` bị cảnh báo Cartesian product. Có thể xóa cảnh báo bằng cách bỏ `RETURN` không?  
**Đáp án:** Không giải quyết nguyên nhân. Cần xác định quan hệ/điều kiện nối hai tập hoặc chấp nhận tích Descartes nếu đó thực sự là yêu cầu nghiệp vụ.

**Bài 4.** Ứng dụng nhận exception vi phạm uniqueness constraint khi tạo `User`, sau đó tự retry nguyên câu `CREATE` nhiều lần. Cách xử lý đúng là gì?  
**Đáp án:** Xác minh khóa trùng và ý định insert hay upsert, dùng khóa duy nhất/`MERGE` hoặc cơ chế kiểm soát phù hợp; retry mù quáng không sửa lỗi dữ liệu và có thể gây tải thừa.

## 9. Checklist khi làm việc với Neo4j

- Đọc **exception code + message + position** khi query thất bại.
- Đọc **severity + description** khi xuất hiện notification, đối chiếu với dữ liệu và execution plan.
- Tách bạch **returned records**, giá trị tổng hợp `count()` và **summary counters**.
- Dùng **`EXPLAIN` để khảo sát**, **`PROFILE` để đo truy vấn được phép thực thi**.
- Kiểm tra label, relationship type, hướng cạnh, property, index/constraint và tham số trước khi tối ưu.
- Với Java/Spring, xử lý transaction đúng ranh giới, chỉ retry lỗi thích hợp và không để lộ bí mật trong log.

Đọc đủ các lớp thông tin trên giúp người phát triển đưa ra kết luận có căn cứ: **truy vấn có chạy thành công không, kết quả có đúng không, đồ thị có thay đổi không và chi phí thực thi có phù hợp không**.
