# Thời gian chờ, giới hạn tài nguyên và hủy giao dịch trong Neo4j

Trong hệ thống Neo4j, một giao dịch có thể đọc và cập nhật nhiều **node**, **relationship** cùng các thuộc tính của property graph. Nếu giao dịch chạy quá lâu, chờ khóa của giao dịch khác hoặc tiêu thụ quá nhiều bộ nhớ, hệ thống có thể tăng độ trễ và làm ảnh hưởng những yêu cầu đang hoạt động. Người vận hành cần biết **khi nào giao dịch phải kết thúc**, **nguồn tài nguyên nào cần giới hạn** và **cách dừng một giao dịch có vấn đề mà vẫn hiểu đúng kết quả dữ liệu**.

Bài thuộc chương **Giao dịch** của module `DATABASE_ENGINE_GRAPH_NEO4J`, trong bối cảnh xây dựng dữ liệu liên kết và truy vấn quan hệ/đường đi bằng Cypher, tối ưu index/constraint, nhập dữ liệu, tích hợp Java Driver, Spring Data Neo4j và vận hành hệ thống đồ thị.

Sau bài này, bạn có thể:

- Phân biệt **transaction timeout**, **lock acquisition timeout** và thời gian chờ ở tầng ứng dụng/driver.
- Nhận diện các giới hạn **bộ nhớ** và **số giao dịch đồng thời**, cùng nguyên nhân tài nguyên bị giữ lâu.
- Quan sát giao dịch đang chạy bằng `SHOW TRANSACTIONS` và hủy đúng giao dịch bằng `TERMINATE TRANSACTIONS`.
- Hiểu việc **rollback**, **commit**, **retry**, hủy yêu cầu từ client và các batch đã commit riêng.
- Thiết kế giao dịch ngắn, có mục tiêu, dễ giám sát trong Java Driver và Spring Data Neo4j.

> **Phạm vi phiên bản:** Ví dụ Cypher và cấu hình tập trung vào Neo4j 5 và dòng Neo4j hiện hành. Tên một số cấu hình, quyền chạy lệnh và hành vi của driver có thể thay đổi theo phiên bản/edition. Khi triển khai, kiểm tra `SHOW SETTINGS` và tài liệu chính thức đúng phiên bản thay vì sao chép giá trị cấu hình của bài học như cấu hình production.

## 1. Vì sao một giao dịch cần có giới hạn?

Giả sử API tạo đơn hàng thực hiện ba việc trong một giao dịch:

1. Đọc sản phẩm và kiểm tra số lượng tồn kho.
2. Tạo `(:Order)` và `(:Order)-[:CONTAINS]->(:Product)`.
3. Cập nhật số lượng tồn kho.

Nếu một bước chờ khóa trên sản phẩm đang được giao dịch khác cập nhật, giao dịch có thể nằm ở trạng thái **chờ**, giữ các tài nguyên đã sử dụng và làm tăng thời gian phản hồi. Nếu lập trình viên đưa thêm tác vụ gọi HTTP đến dịch vụ thanh toán **khi giao dịch Neo4j vẫn mở**, thời gian chờ mạng còn khiến transaction kéo dài không cần thiết.

Mặt khác, một truy vấn duyệt đường đi không giới hạn độ sâu hoặc `collect()` một số lượng node rất lớn có thể tiêu tốn bộ nhớ đáng kể, dù không cần sửa dữ liệu.

Vì vậy cần hai nhóm biện pháp bổ sung nhau:

- **Giới hạn thực thi:** giới hạn thời gian, khóa, bộ nhớ hoặc số lượng giao dịch.
- **Thiết kế truy vấn và ứng dụng:** giảm số bản ghi phải xử lý, dùng index/constraint, thu nhỏ phạm vi ghi, đóng transaction đúng lúc, chia batch phù hợp.

Giới hạn bảo vệ hệ thống khi có vấn đề; chúng **không thay thế** việc sửa truy vấn hoặc thiết kế giao dịch.

## 2. Vòng đời và tính nguyên tử của transaction

Một transaction thông thường đi qua các giai đoạn:

```text
Client / Java Driver
        |
        v
   Bắt đầu transaction
        |
        v
 Chạy một hoặc nhiều truy vấn Cypher
        |
        +-------- Thành công --------> COMMIT ----> Thay đổi được xác nhận
        |
        +-------- Lỗi / rollback ----> ROLLBACK --> Hủy thay đổi chưa commit
        |
        +-------- Timeout / terminate
                                       |
                                       v
                            Đánh dấu cần kết thúc,
                            dừng công việc và rollback
                            khi quá trình xử lý hoàn tất
```

Trong mô hình giao dịch ACID, các thay đổi **chưa commit của một transaction** không trở thành một phần kết quả đã xác nhận nếu transaction đó rollback. Khi Neo4j kết thúc một transaction do timeout hoặc lệnh terminate trước khi commit thành công, ứng dụng cần xử lý lỗi và không được xem những lệnh ghi trước đó là đã hoàn tất.

Tuy nhiên, cần phân biệt ba tình huống:

| Tình huống | Điều ứng dụng có thể kết luận |
| --- | --- |
| Transaction bị rollback trước commit | Các thay đổi của **chính transaction đó** không được commit |
| Transaction đã commit, rồi client không nhận được phản hồi do mất kết nối | **Kết quả có thể chưa biết từ phía client**; không tự kết luận rollback |
| Công việc chia thành nhiều transaction/batch | Các transaction **đã commit trước** không tự rollback khi một batch sau thất bại |

Không nên đánh đồng thao tác **hủy một yêu cầu HTTP** với việc chắc chắn “không có dữ liệu nào đã ghi”. Cần xem transaction thực tế đã commit đến đâu và thiết kế xử lý yêu cầu lặp lại theo khóa nghiệp vụ khi cần.

### Ba cách ứng dụng thường chạy Cypher

- **Implicit/auto-commit transaction:** một câu lệnh được thực thi qua API truy vấn tự động, không phải transaction do người lập trình điều khiển trực tiếp.
- **Explicit transaction:** ứng dụng gọi begin, chạy một hoặc nhiều câu lệnh, rồi commit hoặc rollback.
- **Managed transaction:** Java Driver quản lý transaction và có thể tự retry với các lỗi transient nhất định khi dùng `executeRead()` / `executeWrite()`.

Giới hạn thời gian và cách kết thúc đều phải gắn với **transaction đang chạy thực tế**, chứ không chỉ với một dòng mã gọi `run()`.

## 3. Phân biệt các loại timeout

Có nhiều đồng hồ đo khác nhau, mỗi đồng hồ giới hạn một phần riêng của luồng xử lý.

| Cơ chế | Phạm vi được giới hạn | Điều xảy ra khi quá hạn |
| --- | --- | --- |
| `db.transaction.timeout` | Thời lượng tối đa của transaction do server quản lý, trừ trường hợp có timeout cụ thể khác | Server đánh dấu transaction quá hạn và kết thúc |
| Timeout riêng của transaction qua Java Driver | Thời lượng transaction được cấu hình cho yêu cầu cụ thể | Có thể ghi đè giá trị mặc định của server |
| `db.lock.acquisition.timeout` | Thời gian chờ để lấy một lock cụ thể | Transaction không lấy được lock trong thời hạn sẽ thất bại |
| Thời gian retry của Java Driver | Ngân sách thời gian cho việc thử lại các managed transaction sau lỗi transient | Driver ngừng retry và báo lỗi |
| Connection acquisition / network / HTTP request timeout | Thời gian chờ kết nối, phản hồi hoặc request ở tầng giao tiếp | Client có thể nhận lỗi; phải xác định riêng trạng thái transaction phía server |

Một timeout ở client **không đồng nghĩa** một timeout transaction phía server đã xảy ra. Chẳng hạn, nếu kết nối đứt ngay khi server đang commit, client có thể chưa biết giao dịch thành công hay chưa.

### 3.1. Transaction timeout của Neo4j

Cấu hình máy chủ:

```properties
# Ví dụ minh họa trong neo4j.conf
db.transaction.timeout=30s
```

Thiết lập này yêu cầu transaction hoàn thành trong khoảng thời gian tối đa đã cấu hình. Giá trị `0s` của setting này nghĩa là **không bật giới hạn transaction timeout mặc định**. Neo4j có cơ chế monitor kiểm tra timeout theo chu kỳ, vì vậy không nên hiểu giá trị `30s` là một bộ đếm có độ chính xác tuyệt đối đến từng mili giây.

Một transaction có timeout do client truyền riêng có thể **ghi đè timeout mặc định của server**. Do đó, khi thấy transaction lâu hơn kỳ vọng, cần kiểm tra cả cấu hình server và cấu hình của client đang gọi.

### 3.2. Thời gian chờ khóa

Giao dịch cập nhật cùng một node hoặc relationship có thể phải đợi transaction khác nhả lock.

```properties
# Ví dụ minh họa
db.lock.acquisition.timeout=10s
```

Giới hạn này áp dụng cho việc **lấy lock**, không phải tổng thời gian thực thi một transaction. Transaction có thể chạy nhanh nhưng thất bại vì chờ lock lâu; cũng có thể giữ lock lâu dù không chờ lock nào và vì vậy không bị cơ chế lock timeout ngăn lại.

Giá trị `0s` của setting này nghĩa là **tắt giới hạn chờ lock**. Nếu muốn giới hạn toàn bộ transaction, cần xem thêm `db.transaction.timeout` hoặc timeout trên từng transaction.

### 3.3. Timeout ở Java Driver

Neo4j Java Driver cung cấp `TransactionConfig` để đặt thời gian tối đa cho transaction cụ thể:

```java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.TransactionConfig;

// driver đã được khởi tạo và quản lý theo vòng đời ứng dụng
TransactionConfig txConfig = TransactionConfig.builder()
    .withTimeout(Duration.ofSeconds(5))
    .withMetadata(Map.of("operation", "find-related-products"))
    .build();

try (Session session = driver.session()) {
    var productCodes = session.executeRead(tx -> {
        var result = tx.run("""
            MATCH (p:Product {sku: $sku})-[:RELATED_TO]->(other:Product)
            RETURN other.sku AS sku
            LIMIT 20
            """, Map.of("sku", "SKU-001"));
        return result.list(r -> r.get("sku").asString());
    }, txConfig);

    productCodes.forEach(System.out::println);
}
```

Ở đây:

- `withTimeout(Duration.ofSeconds(5))` giới hạn transaction trên server cho công việc này.
- `withMetadata(...)` giúp nhận diện nguồn gốc thao tác khi quan sát transaction và query log.
- `executeRead` quản lý transaction và có thể retry khi lỗi được phân loại là transient.
- `try-with-resources` đóng session sau khi sử dụng.

Không nên mặc định timeout 5 giây ở ví dụ là mức tối ưu cho mọi API; chọn theo SLA, độ phức tạp truy vấn, năng lực server và đặc điểm tải thực tế.

## 4. Nhóm giới hạn tài nguyên thường gặp

Neo4j cung cấp các setting kiểm soát lượng transaction đồng thời và bộ nhớ mà transaction có thể tiêu thụ. Các tên sau là những cấu hình cần biết trên hệ Neo4j có hỗ trợ:

| Setting | Ý nghĩa | Rủi ro nếu cấu hình không phù hợp |
| --- | --- | --- |
| `db.transaction.concurrent.maximum` | Số transaction đồng thời tối đa trên một database | Quá thấp gây từ chối tải hợp lệ; quá cao tăng cạnh tranh tài nguyên |
| `db.memory.transaction.max` | Bộ nhớ tối đa của **một transaction** | Một transaction lớn có thể thất bại do vượt giới hạn |
| `db.memory.transaction.total.max` | Tổng bộ nhớ transaction của **một database** | Nhiều transaction cùng chạy có thể đạt trần |
| `dbms.memory.transaction.total.max` | Tổng bộ nhớ transaction ở cấp instance | Cần phân chia hợp lý giữa nhiều database |
| `server.memory.heap.max_size` | Ngân sách Java heap của server | Heap thiếu có thể gây GC kéo dài và lỗi bộ nhớ |

Một số setting có giá trị `0` mang ý nghĩa tắt một giới hạn hoặc dùng giá trị tối đa có thể, nhưng **không phải mọi setting đều diễn giải 0 giống nhau**. Hãy xem mô tả chính thức của từng setting.

Ví dụ một cấu hình để thảo luận khi thiết kế năng lực:

```properties
# CHỈ LÀ VÍ DỤ: cần sizing theo RAM, workload, edition và phiên bản
db.transaction.timeout=30s
db.lock.acquisition.timeout=10s
db.transaction.concurrent.maximum=200
db.memory.transaction.max=256m
db.memory.transaction.total.max=1g
```

Các giới hạn này **không bảo đảm** tổng mức sử dụng RAM của Neo4j nằm trong những con số đó. Server còn sử dụng bộ nhớ cho heap, page cache, các cấu trúc khác và tác vụ nền. Cũng không nên giảm trần quá thấp chỉ để “giải quyết” lỗi tiêu thụ bộ nhớ: khi đó ứng dụng có thể bị lỗi sớm hơn nhưng vấn đề thực tế vẫn còn.

### Xem cấu hình đang có

Trên môi trường có quyền xem settings:

```cypher
SHOW SETTINGS
YIELD name, value, defaultValue, description
WHERE name IN [
  'db.transaction.timeout',
  'db.lock.acquisition.timeout',
  'db.transaction.concurrent.maximum',
  'db.memory.transaction.max',
  'db.memory.transaction.total.max',
  'dbms.memory.transaction.total.max'
]
RETURN name, value, defaultValue, description
ORDER BY name;
```

Các tên setting không được hỗ trợ ở một phiên bản cụ thể sẽ không hiển thị như mong đợi; quyền xem cấu hình cũng phụ thuộc phân quyền server. Việc thay `neo4j.conf` hoặc cấu hình qua môi trường triển khai phải tuân theo cơ chế vận hành hiện có; một số setting có thể thay đổi động, một số cần khởi động lại hoặc chỉnh theo node trong cluster.

## 5. Vì sao một truy vấn tốn tài nguyên?

Không phải mọi transaction lâu đều “bị khóa”. Có các nguyên nhân chính:

| Hiện tượng | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| `MATCH` mở rộng quá nhiều nhánh | Nhiều hàng trung gian, độ trễ cao | Ràng buộc nguồn/đích, hướng và loại quan hệ, giới hạn độ sâu |
| `collect()` / `ORDER BY` trên tập rất lớn | Tăng bộ nhớ xử lý, có thể chạm trần | Lọc sớm, giới hạn kết quả, phân trang/batch |
| Thiếu index cho thuộc tính tìm kiếm | Scan nhiều node/relationship | Tạo index/constraint phù hợp, xem execution plan |
| Một transaction nhập quá nhiều bản ghi | Ghi kéo dài, giữ lock và memory lâu | Chia thành batch với kích thước hợp lý |
| Nhiều giao dịch ghi cùng thực thể nóng | `waitTime` tăng, lock contention | Giảm điểm nóng, thay lịch/nhóm cập nhật, rút ngắn transaction |
| Gọi dịch vụ ngoài trong lúc transaction đang mở | Không làm gì với DB nhưng giữ transaction | Tách network I/O khỏi khoảng thời gian giữ transaction |
| Quá nhiều request đồng thời | Tăng số transaction, cạnh tranh CPU/RAM/connection | Giới hạn concurrency từ ứng dụng và server, kiểm tra pool |
| Giao dịch không đóng khi exception | Kéo dài vòng đời transaction hoặc session | Dùng transaction API đúng cách, `try-with-resources` |

Ví dụ đường đi biến độ dài vô hạn có thể làm không gian ứng viên tăng rất nhanh:

```cypher
// Ví dụ không nên dùng tùy tiện trên đồ thị lớn:
MATCH p = (a:Person {personId: $id})-[:KNOWS*]->(b)
RETURN p;
```

Hãy xác định đúng bài toán trước, chẳng hạn chỉ xét tối đa 3 bước:

```cypher
MATCH p = (a:Person {personId: $id})-[:KNOWS*1..3]->(b)
WHERE b.active = true
RETURN b.personId AS relatedId,
       length(p) AS hops
LIMIT 100;
```

Độ sâu và `LIMIT` chỉ là một phần biện pháp bảo vệ: truy vấn vẫn có thể tạo rất nhiều ứng viên trước khi ra kết quả. Dùng `EXPLAIN` để xem kế hoạch **mà không thực thi**, còn `PROFILE` **thực thi truy vấn** và thu số liệu thực tế; tránh chạy `PROFILE` cho truy vấn ghi nguy hiểm trên production.

## 6. Theo dõi transaction đang chạy

Cypher cung cấp lệnh quản trị:

```cypher
SHOW TRANSACTIONS;
```

Để quan sát các trường cần thiết:

```cypher
SHOW TRANSACTIONS
YIELD transactionId, database, username, elapsedTime,
      waitTime, status, currentQuery
RETURN transactionId, database, username, elapsedTime,
       waitTime, status, currentQuery
ORDER BY elapsedTime DESC
LIMIT 20;
```

Các cột có ý nghĩa:

- `transactionId`: định danh transaction đang tồn tại, ví dụ `neo4j-transaction-123`.
- `database`: database liên quan; cần nhận diện đúng trong môi trường nhiều database.
- `username`: người dùng thực thi; hữu ích khi rà soát quyền và workload.
- `elapsedTime`: thời gian từ lúc transaction bắt đầu.
- `waitTime`: thời gian chờ đã ghi nhận; có thể gợi ý tình trạng cạnh tranh.
- `status`: trạng thái được server báo cáo.
- `currentQuery`: câu Cypher đang thực thi, nếu có.

Một transaction vừa bắt đầu để chạy chính lệnh `SHOW TRANSACTIONS` cũng có thể xuất hiện trong danh sách. Điều này bình thường: danh sách là **ảnh chụp tại thời điểm truy vấn**, không phải lịch sử bất biến.

**Phân tích đúng:** `elapsedTime` cao chưa chắc do CPU cao; có thể transaction đang chờ lock hoặc client giữ mở. `waitTime` cao gợi ý tranh chấp nhưng cần xem thêm query, các transaction giữ khóa và tải hệ thống.

Quyền quan sát transaction của người khác phụ thuộc quyền `SHOW TRANSACTION` và chính sách bảo mật của instance. Người dùng thường luôn có thể xem transaction do mình sở hữu. Không in toàn bộ `currentQuery` ra log công khai nếu nội dung có thể chứa thông tin nhạy cảm.

## 7. Hủy giao dịch bằng `TERMINATE TRANSACTIONS`

Khi xác định được transaction gây vấn đề và có quyền phù hợp, có thể yêu cầu server dừng nó theo transaction ID.

### 7.1. Xác minh ID trước khi hủy

```cypher
SHOW TRANSACTIONS $transactionId
YIELD transactionId, username, database, elapsedTime,
      status, currentQuery
RETURN transactionId, username, database, elapsedTime,
       status, currentQuery;
```

Với tham số `$transactionId` chứa giá trị thực nhận từ `SHOW TRANSACTIONS`. Có thể kiểm tra thêm phiên ứng dụng đang dùng và tác động nghiệp vụ của thao tác bị dừng.

### 7.2. Gửi lệnh hủy

```cypher
TERMINATE TRANSACTIONS $transactionId
YIELD transactionId, username, message
RETURN transactionId, username, message;
```

Server trả thông báo về kết quả xử lý yêu cầu terminate. Giao dịch có thể đã kết thúc giữa lúc bạn xem và lúc gửi lệnh, vì vậy cần đọc `message` thay vì giả định ID vẫn còn hiệu lực. Người dùng được phép hủy transaction của chính mình; hủy transaction của người khác đòi hỏi quyền phù hợp (`TERMINATE TRANSACTION`).

Đừng hủy theo “transaction lâu nhất” một cách máy móc. Có giao dịch sao lưu, quản trị hoặc tác vụ theo lô được thiết kế chạy lâu. Cần xem người sở hữu, câu truy vấn, trạng thái, thời gian chờ và mức ảnh hưởng.

### 7.3. Điều gì xảy ra sau lệnh terminate?

- Transaction được đánh dấu cần kết thúc và các thao tác chưa hoàn tất sẽ bị dừng tại điểm có thể xử lý hủy.
- Những thay đổi **chưa commit** của transaction bị hủy sẽ rollback.
- Lock do transaction giữ sẽ được giải phóng khi quá trình kết thúc/rollback hoàn tất; việc thu hồi không nhất thiết xảy ra tức thời đúng vào lúc gửi lệnh.
- Client nhận lỗi/điều kiện kết thúc liên quan đến transaction và phải đóng hoặc xử lý lại tài nguyên phiên theo API.
- Nếu một transaction **đã commit** trước khi lệnh hủy có hiệu lực, terminate không “hoàn tác” lịch sử đã commit đó.
- Lệnh terminate một transaction không chủ động rollback những transaction **khác** đã commit trước đó.

Điều này giải thích vì sao người vận hành vừa cần giám sát tác dụng của lệnh, vừa cần cơ chế nghiệp vụ để đối chiếu trạng thái sau sự cố.

## 8. Timeout, deadlock và hủy giao dịch khác nhau thế nào?

Ba tình huống đều có thể khiến transaction thất bại nhưng không nên được xử lý như cùng một lỗi:

| Hiện tượng | Nguyên nhân gần | Biện pháp phù hợp |
| --- | --- | --- |
| Transaction timeout | Transaction tồn tại quá lâu so với giới hạn | Tối ưu truy vấn, rút ngắn transaction hoặc điều chỉnh timeout có cơ sở |
| Lock acquisition timeout | Chờ lock quá hạn | Giảm cạnh tranh cùng thực thể, thu nhỏ phạm vi và thời gian giữ lock |
| Deadlock | Các transaction giữ lock và chờ nhau theo vòng | Để server phát hiện/giải quyết, thiết kế thứ tự cập nhật nhất quán, retry có kiểm soát |
| Vượt giới hạn transaction memory | Công việc tiêu thụ quá nhiều bộ nhớ được theo dõi | Lọc sớm, chia nhỏ batch, tránh giữ tập dữ liệu lớn trong transaction |
| Bị terminate thủ công | Người vận hành/client yêu cầu ngừng transaction | Kiểm tra nguyên nhân, không tự động lặp vô hạn |
| Client timeout hoặc mất kết nối | Giới hạn/tình trạng ở tầng client/network | Xác minh kết quả commit và dùng cơ chế idempotency khi cần |

Một số lỗi có thể được driver coi là **transient** và retry được; một số khác là lỗi về dữ liệu, cú pháp, quyền hoặc cấu hình. Không nên dùng `catch (Exception)` rồi tự động gửi lại toàn bộ câu lệnh không giới hạn số lần.

## 9. Thiết kế transaction ngắn và có chủ đích

### 9.1. Định vị node bằng index hoặc constraint

Giả sử API cập nhật trạng thái đơn hàng theo mã:

```cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
```

Một transaction cập nhật ngắn:

```cypher
MATCH (o:Order {orderId: $orderId})
SET o.status = 'CANCELLED'
RETURN o.orderId AS orderId, o.status AS status;
```

Khi định vị node bằng khóa duy nhất có index hỗ trợ, hệ thống giảm công việc tìm kiếm. Việc đặt `o.status = 'CANCELLED'` nhiều lần cũng không tạo thêm một giá trị trạng thái khác, hữu ích khi thiết kế thao tác có thể được thực hiện lại. Tuy nhiên, **idempotency của cả một quy trình** còn phụ thuộc các thay đổi khác như khấu trừ kho, gửi email hay gọi cổng thanh toán.

### 9.2. Không giữ transaction mở để chờ dịch vụ bên ngoài

Thiết kế không nên:

```text
BEGIN Neo4j transaction
  -> cập nhật Order
  -> gọi HTTP sang cổng thanh toán (chờ không xác định)
  -> tiếp tục ghi dữ liệu
COMMIT
```

Thay vào đó, có thể thiết kế các bước có trạng thái rõ ràng:

```text
Transaction A: tạo yêu cầu thanh toán PENDING -> COMMIT
   -> gọi dịch vụ ngoài với idempotency key
Transaction B: cập nhật kết quả PAID/FAILED -> COMMIT
```

Quy trình nhiều bước này **không còn là một transaction Neo4j duy nhất**. Nó cần quy tắc xử lý thất bại, retry và đối soát. Đổi lại, mỗi transaction ngắn hơn, ít giữ lock và dễ quan sát.

### 9.3. Chia nhập liệu lớn thành batch

Nếu nhập hàng trăm nghìn node trong một transaction, bộ nhớ và thời gian giữ lock có thể tăng cao. Cypher hỗ trợ xử lý hàng loạt bằng các transaction con/batch, ví dụ:

```cypher
UNWIND $rows AS row
CALL {
  WITH row
  MERGE (u:User {userId: row.userId})
  SET u.displayName = row.displayName
} IN TRANSACTIONS OF 500 ROWS;
```

Lưu ý quan trọng:

1. `CALL { ... } IN TRANSACTIONS` cần được thực thi ở **implicit transaction**, không lồng tùy tiện trong một explicit/managed transaction của Java Driver.
2. Các batch **commit độc lập**. Nếu batch sau thất bại, các batch đã commit trước đó không tự rollback.
3. `500 ROWS` là kích thước ví dụ; cần thử nghiệm theo kích thước row, số thuộc tính/relationship, contention và năng lực máy.
4. Với nhập lại sau lỗi, thiết kế khóa định danh duy nhất và `MERGE` phù hợp giúp tránh tạo bản ghi trùng. Cẩn thận nếu mỗi row còn thực hiện cộng dồn số lượng hoặc gửi hiệu ứng ra ngoài.
5. Theo dõi số batch thành công, dữ liệu bị từ chối và vị trí resume; **không** coi trạng thái “truy vấn thất bại” là “chưa có batch nào commit”.

Một số phiên bản Cypher mới cho phép cách viết nhập biến rõ ràng hơn, như `CALL (row) { ... } IN TRANSACTIONS ...`. Chọn cú pháp tương ứng với phiên bản Neo4j đang dùng.

## 10. Java Driver: timeout, rollback và retry

### 10.1. Managed transaction với timeout

```java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionConfig;

TransactionConfig config = TransactionConfig.builder()
    .withTimeout(Duration.ofSeconds(8))
    .withMetadata(Map.of("operation", "cancel-order"))
    .build();

try (Session session = driver.session(
        SessionConfig.builder().withDatabase("neo4j").build())) {

    String newStatus = session.executeWrite(tx -> {
        var record = tx.run("""
            MATCH (o:Order {orderId: $orderId})
            SET o.status = 'CANCELLED'
            RETURN o.status AS status
            """, Map.of("orderId", "ORD-123")).single();

        return record.get("status").asString();
    }, config);

    System.out.println(newStatus);
}
```

Ở ví dụ này:

- Callback `executeWrite` được Driver quản lý: thành công thì commit, gặp lỗi thì transaction không được commit.
- Timeout 8 giây là cấu hình riêng của transaction.
- Nếu không tồn tại node `Order` tương ứng, `single()` không có bản ghi để đọc và callback sẽ thất bại; ứng dụng cần chuyển lỗi thành phản hồi nghiệp vụ phù hợp.
- Driver có thể **chạy lại callback** sau lỗi transient. Do đó, callback không nên phát email, gọi thanh toán hay thực hiện hiệu ứng bên ngoài không kiểm soát.

Cũng cần nhớ thời gian retry toàn bộ request **có thể lớn hơn timeout của một lần transaction**. Timeout của một transaction không phải SLA duy nhất cho toàn bộ HTTP request.

### 10.2. Explicit transaction và rollback chủ động

Khi muốn quyết định commit/rollback trực tiếp:

```java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.Transaction;
import org.neo4j.driver.TransactionConfig;

try (Session session = driver.session();
     Transaction tx = session.beginTransaction(
         TransactionConfig.builder()
             .withTimeout(Duration.ofSeconds(5))
             .build())) {

    tx.run("""
        MATCH (o:Order {orderId: $orderId})
        SET o.status = 'PROCESSING'
        """, Map.of("orderId", "ORD-123")).consume();

    boolean businessRuleAllowsCommit = true; // Thay bằng kiểm tra thực tế

    if (businessRuleAllowsCommit) {
        tx.commit();
    } else {
        tx.rollback();
    }
}
// Nếu tx đóng mà chưa commit, Driver xử lý rollback theo contract.
```

Trong thực tế, phần kiểm tra nghiệp vụ phải được thiết kế cùng điều kiện cạnh tranh đồng thời; một cờ `true` cố định ở trên chỉ minh họa nhánh commit/rollback. Sau khi `commit()` thành công, không có thao tác `rollback()` nào trên cùng transaction để “quay lại” dữ liệu đã commit.

### 10.3. Retry có giới hạn và idempotency

Với các lỗi transient như deadlock hoặc tạm thời không liên lạc được với một thành viên cluster, một số cách thực thi của Driver hỗ trợ retry. Cần:

- Đặt ngân sách retry tổng thể phù hợp với deadline của API.
- Dùng **request ID/idempotency key** cho thao tác có thể nhận lại nhiều lần.
- Không để callback transaction phát sinh hiệu ứng bên ngoài không thể rollback.
- Với kết quả commit không rõ do mất kết nối, tra cứu bằng khóa nghiệp vụ trước khi tạo dữ liệu mới.
- Ghi nhận số lần retry, mã lỗi và độ trễ, tránh retry vô hạn khi server đang quá tải.

Ví dụ nghiệp vụ “tạo đơn hàng” thường nên có `orderId` duy nhất. Khi API được gọi lại vì timeout mạng, hệ thống có thể tìm trạng thái đơn đã tạo thay vì mặc định tạo thêm một đơn mới.

## 11. Spring Data Neo4j và ranh giới giao dịch

Trong Spring Data Neo4j, `@Transactional` thường khai báo ranh giới giao dịch ở tầng service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void cancelOrder(String orderId) {
        Order order = orderRepository.findByOrderId(orderId)
            .orElseThrow(() -> new IllegalArgumentException("Order not found"));
        order.setStatus("CANCELLED");
        orderRepository.save(order);
    }
}
```

Đây là ví dụ cấu trúc ứng dụng: `Order`, `OrderRepository`, phương thức `findByOrderId()` và entity mapping là các thành phần phải được định nghĩa riêng trong project.

Một số lưu ý quan trọng:

- `@Transactional` xác định phạm vi công việc Neo4j tham gia transaction, nhưng không nên mặc định một thuộc tính timeout của framework **luôn tương đương chính xác** với `TransactionConfig.withTimeout()` ở mọi phiên bản. Cần kiểm chứng với Spring transaction manager và Neo4j Driver đang dùng.
- Tránh gọi HTTP, chờ người dùng hoặc chạy tác vụ tính toán dài trong phương thức `@Transactional`.
- Spring proxy có quy tắc riêng về lời gọi nội bộ giữa các phương thức cùng class; cần hiểu khi kỳ vọng annotation tạo transaction mới.
- Không lồng câu `CALL { ... } IN TRANSACTIONS` vào một managed transaction được tạo bởi `@Transactional` nếu chế độ thực thi yêu cầu implicit transaction.
- Đặt `@Transactional(readOnly = true)` cho các luồng đọc phù hợp giúp diễn đạt ý định và phối hợp với transaction manager, nhưng vẫn cần tối ưu Cypher khi truy vấn đọc rất nặng.

## 12. Xử lý sự cố trong vận hành

Giả sử API tìm đường đi đột ngột chậm và nhiều request bị timeout. Một quy trình điều tra có kiểm soát:

1. **Xác nhận triệu chứng:** độ trễ tăng, lỗi client, transaction timeout hay lock timeout? Thu thập thời điểm và request ID.
2. **Quan sát transaction hiện hành:** dùng `SHOW TRANSACTIONS`, xem `elapsedTime`, `waitTime`, `currentQuery`, `username`, database và số transaction đồng thời.
3. **Đối chiếu truy vấn:** dùng `EXPLAIN`/`PROFILE` theo mức rủi ro cho phép, quan sát index, row mở rộng và độ sâu đường đi.
4. **Kiểm tra tài nguyên:** heap/GC, transaction memory, CPU, I/O, connection pool, timeout và cấu hình concurrency.
5. **Xác định tác động:** transaction bị treo có phải batch import, job phân tích hay request tương tác? Có hiệu ứng bên ngoài và các batch đã commit trước không?
6. **Hủy có chọn lọc nếu cần:** lấy đúng transaction ID, dùng `TERMINATE TRANSACTIONS` với quyền phù hợp, quan sát kết quả và việc giải phóng tài nguyên.
7. **Khắc phục nguyên nhân:** rút ngắn transaction, chọn index/constraint phù hợp, giới hạn truy vấn, đổi thiết kế batch, giảm tranh chấp điểm nóng hoặc điều chỉnh cấu hình có cơ sở.
8. **Kiểm chứng sau thay đổi:** đo p95/p99 latency, số transaction chờ, lỗi timeout, transaction memory và mức sử dụng hệ thống trong workload tương đương.

### Kịch bản minh họa

Một job nhập liệu cập nhật 200.000 sản phẩm trong một transaction duy nhất. Trong lúc đó, API cập nhật sản phẩm cùng vùng dữ liệu thường xuyên bị chờ khóa.

| Phương án | Hiệu quả dự kiến | Giới hạn cần biết |
| --- | --- | --- |
| Tăng timeout lên 10 phút | Job có thêm thời gian | Có thể kéo dài lock contention; không giải quyết nguyên nhân |
| Hủy ngay mọi transaction quá 30 giây | Chặn công việc chạy lâu | Có thể dừng job hợp lệ, ảnh hưởng người dùng |
| Chia import thành batch 500–1000 row | Giảm phạm vi một transaction | Batch commit riêng; cần xử lý resume và dữ liệu trùng |
| Lập lịch import ngoài giờ cao điểm | Giảm cạnh tranh với API | Không thay thế tối ưu truy vấn và cơ chế backpressure |
| Định vị sản phẩm bằng index duy nhất | Giảm chi phí tìm node trước khi cập nhật | Các cập nhật vào cùng node nóng vẫn tranh chấp |

Giải pháp thường là **kết hợp** mô hình dữ liệu, kích thước batch, giới hạn tải, cơ chế quan sát và timeout hợp lý.

## 13. Những hiểu nhầm phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Đặt transaction timeout 10 giây thì mọi request kết thúc đúng trong 10 giây.” | Server kiểm tra theo chu kỳ; client, network và retry còn có đồng hồ riêng |
| “Lock timeout là giới hạn thời gian transaction.” | Nó giới hạn thời gian **chờ lấy lock**, không phải toàn bộ transaction |
| “Hủy request HTTP đồng nghĩa rollback chắc chắn.” | Transaction có thể đã commit hoặc đang ở trạng thái client chưa xác nhận |
| “`TERMINATE TRANSACTIONS` hoàn tác các batch import trước.” | Chỉ transaction chưa commit bị hủy; batch đã commit vẫn còn |
| “Tăng bộ nhớ transaction sẽ chữa truy vấn duyệt đồ thị vô hạn.” | Có thể chỉ trì hoãn lỗi; phải sửa truy vấn và phạm vi xử lý |
| “`LIMIT 10` luôn ngăn quét và xử lý quá nhiều hàng.” | Còn phụ thuộc thứ tự operator và execution plan |
| “Managed transaction callback chỉ chạy đúng một lần.” | Driver có thể retry callback khi gặp lỗi transient |
| “`@Transactional` giúp truy vấn chậm tự trở nên nhanh.” | Annotation xác định ranh giới transaction; truy vấn vẫn cần tối ưu |
| “`SHOW TRANSACTIONS` là lịch sử mọi transaction.” | Nó quan sát transaction **đang tồn tại** tại thời điểm chạy |
| “Gặp timeout thì cứ tự động retry.” | Cần phân loại lỗi, giới hạn retry và bảo đảm idempotency |

## 14. Bài tập và câu hỏi kiểm tra

### Bài tập 1 — Phân biệt hai timeout

Server cấu hình `db.transaction.timeout=30s` và `db.lock.acquisition.timeout=5s`. Một transaction chờ lock trên một node `:Product` trong 7 giây.

1. Giới hạn nào có thể làm transaction thất bại trước?
2. Nếu giảm `db.transaction.timeout` xuống `3s`, hành vi có thể thay đổi thế nào?
3. Tại sao không nên tăng mọi timeout lên giá trị thật lớn?

*Gợi ý:* lock timeout giới hạn thời gian đợi từng lock, transaction timeout giới hạn tuổi của transaction; thời điểm phát hiện còn phụ thuộc cơ chế giám sát và môi trường.

### Bài tập 2 — Phát hiện giao dịch kéo dài

Viết câu `SHOW TRANSACTIONS` hiển thị `transactionId`, `username`, `elapsedTime`, `waitTime` và `currentQuery`, sắp xếp theo `elapsedTime` giảm dần. Nêu thêm thông tin cần xác minh trước khi chọn một giao dịch để terminate.

### Bài tập 3 — Kiểm tra tính nguyên tử

Có 3 batch import độc lập: A đã commit, B đã commit, C đang chạy và bị terminate. Những thay đổi nào sẽ còn lại? Nếu muốn chạy lại import, phải thiết kế idempotency theo khóa nào?

### Bài tập 4 — Java Driver

Thêm `TransactionConfig.withTimeout(Duration.ofSeconds(4))` vào một managed transaction. Giải thích sự khác nhau giữa timeout của một transaction và tổng ngân sách retry cho cả một yêu cầu HTTP.

### Bài tập 5 — Tìm nguyên nhân

Một truy vấn không bị lock contention nhưng tiêu tốn transaction memory rất lớn. Truy vấn chứa `collect()` trên toàn bộ quan hệ của một mạng xã hội. Hãy đề xuất cách sửa truy vấn, cách kiểm tra execution plan và cách đo lại sau tối ưu.

### Checklist triển khai

- [ ] Có timeout phù hợp cho giao dịch tương tác và công việc chạy lâu.
- [ ] Hiểu rõ sự khác nhau giữa timeout transaction, lock, driver và request.
- [ ] Có giới hạn transaction đồng thời và bộ nhớ theo workload, giám sát được khi đạt trần.
- [ ] Truy vấn dùng index/constraint phù hợp, hạn chế duyệt đường đi hoặc tập trung gian quá lớn.
- [ ] Transaction đóng đúng cách; không giữ transaction mở trong lúc gọi dịch vụ ngoài.
- [ ] Với import batch, biết rõ các batch đã commit và cơ chế tiếp tục sau lỗi.
- [ ] Có quy trình `SHOW TRANSACTIONS`, xác minh ID và terminate theo quyền.
- [ ] Retry có giới hạn, thao tác quan trọng có khóa idempotency.
- [ ] Đã đo độ trễ, wait time, contention và memory trên workload gần thực tế.

## 15. Tài liệu đối chiếu

Những tài liệu chính thức của Neo4j dùng để đối chiếu tên lệnh và cơ chế vận hành (hãy chọn đúng phiên bản đang triển khai):

- [Operations Manual — Transaction management](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/): timeout mặc định và cấu hình transaction.
- [Operations Manual — Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/): danh sách setting timeout, giới hạn concurrency và transaction memory.
- [Operations Manual — Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/): cú pháp quản trị, quyền và thông tin transaction.
- [Operations Manual — Concurrent data access](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/): cơ chế khóa và lock acquisition timeout.
- [Java Driver Manual — Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/): `TransactionConfig`, transaction function và retry.

**Ghi nhớ:** Timeout xác định **khi nào giao dịch phải dừng**, giới hạn tài nguyên xác định **transaction có thể tiêu thụ bao nhiêu**, còn thao tác terminate cho phép **can thiệp khi transaction đã trở thành vấn đề**. Độ tin cậy của hệ thống Neo4j phụ thuộc đồng thời vào truy vấn Cypher hợp lý, transaction ngắn, theo dõi tài nguyên, rollback đúng nghĩa và khả năng xử lý kết quả commit chưa rõ ở tầng ứng dụng.
