# Xung đột ghi, deadlock và chiến lược giảm tranh chấp

Trong **Neo4j**, nhiều giao dịch có thể đồng thời đọc và thay đổi một **property graph** gồm node, relationship và property. Chẳng hạn, một yêu cầu đặt hàng cập nhật trạng thái đơn, ghi liên kết giữa khách hàng và sản phẩm, trong lúc các tác vụ khác đang ghi lịch sử thanh toán hoặc đồng bộ dữ liệu. Khi những giao dịch này cần sửa cùng tài nguyên, chúng có thể phải chờ khóa, mắc deadlock hoặc tạo ra sai lệch nghiệp vụ nếu chương trình đọc–ghi không đúng cách.

Bài học thuộc chương **Giao dịch** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Mục tiêu là nhận diện rõ **write contention**, **deadlock**, **lost update**, rồi chọn chiến lược phù hợp trong **Cypher**, **Neo4j Java Driver**, và ứng dụng dùng **Spring Data Neo4j**. Các ví dụ sử dụng node, relationship và khóa để minh họa; không cần cài đặt thêm thư viện ngoài Neo4j, trừ khi được nêu rõ.

## 1. Phân biệt ba hiện tượng dễ nhầm lẫn

| Hiện tượng | Điều gì xảy ra? | Hậu quả chính | Hướng xử lý |
|---|---|---|---|
| **Xung đột ghi / lock contention** | Giao dịch B cần tài nguyên đang bị giao dịch A giữ khóa | B **chờ** A hoàn thành, tăng độ trễ; chưa chắc có lỗi | Rút ngắn giao dịch, giảm số thao tác đụng một tài nguyên |
| **Deadlock** | A giữ khóa X, đợi Y; B giữ Y, đợi X (hoặc vòng dài hơn) | Không bên nào tự tiến lên; Neo4j phát hiện và hủy một giao dịch | Thống nhất thứ tự lấy khóa, hạn chế tập tài nguyên tranh chấp, retry lỗi tạm thời |
| **Lost update** | Nhiều giao dịch đọc cùng giá trị cũ, rồi cập nhật từ giá trị đó | Một cập nhật bị ghi đè dù không nhất thiết có deadlock | Đưa phép cập nhật phụ thuộc giá trị vào Cypher đúng cách; dùng khóa/chiến lược đồng bộ khi cần |

**Không phải mọi giao dịch chậm đều mắc deadlock.** Nếu chỉ có B đợi A, A vẫn có thể hoàn tất và giải phóng khóa. **Deadlock** cần có **vòng chờ**. Mặt khác, một giao dịch chạy thành công mà ghi sai tổng đếm vì *lost update* vẫn là lỗi, dù không có ngoại lệ nào được trả về.

## 2. Neo4j quản lý giao dịch và khóa ra sao?

### 2.1. Transaction là đơn vị ACID

Một transaction bao gồm các thay đổi được **commit toàn bộ** hoặc **rollback toàn bộ**. Neo4j cung cấp tính chất ACID; khi giao dịch gặp lỗi nghiêm trọng, các thay đổi chưa commit không được giữ lại một phần. Các thao tác trên graph, index và schema đều thực hiện trong transaction.

Mức cô lập mặc định của Neo4j là **read committed**:

- Các thay đổi chưa commit của giao dịch khác không được đọc như dữ liệu đã cam kết.
- Chỉ **đọc** node hoặc relationship thường **không** giữ khóa ghi để chặn giao dịch khác sửa nó. Vì vậy có thể xảy ra *non-repeatable read* — đọc cùng một thuộc tính hai lần trong cùng transaction nhưng gặp hai giá trị đã commit khác nhau.
- Các thao tác **ghi** yêu cầu khóa để bảo vệ nhất quán dữ liệu. Khóa thường được giữ đến khi transaction **commit** hoặc **rollback**.
- Read committed **không** tự động bảo vệ mọi quy tắc nghiệp vụ dạng “đọc điều kiện → tính toán → ghi kết quả” trước các cập nhật đồng thời.

Khi cần cô lập chặt hơn cho một chuỗi đọc–ghi, thiết kế phải chủ động giữ một khóa chung hoặc dùng cơ chế kiểm soát đồng thời phù hợp. Đừng mặc định rằng việc đặt nhiều truy vấn trong một transaction tương đương mức cô lập **serializable**.

### 2.2. Các thao tác ghi và khóa liên quan

| Thao tác | Khóa đáng chú ý |
|---|---|
| Sửa thuộc tính hoặc nhãn của node | Khóa ghi **NODE** |
| Sửa thuộc tính của relationship | Khóa ghi **RELATIONSHIP** |
| Xóa node | Khóa **NODE** và các kiểm tra tính toàn vẹn liên quan |
| Tạo hoặc xóa relationship | Có thể cần khóa/đồng bộ trên cả hai node đầu–cuối và cấu trúc relationship |
| Tạo/sửa dữ liệu có index hoặc constraint | Có thể phát sinh khóa bổ sung để duy trì các cấu trúc nội bộ |

**Không giả định mọi thao tác tạo/xóa quan hệ đều độc quyền khóa node giống nhau.** Neo4j có chiến lược khác nhau cho node *sparse* và *dense*; trong những trường hợp node dense, cập nhật relationship có thể được đồng bộ chi tiết hơn. Chi tiết khóa nội bộ có thể thay đổi theo phiên bản và định dạng lưu trữ. Bài học tập trung vào **cùng tài nguyên và cùng thứ tự thay đổi** thay vì phụ thuộc vào một danh sách khóa nội bộ cố định.

### 2.3. Vì sao transaction càng lâu thì càng dễ nghẽn?

Giả sử giao dịch T1 khóa node A rồi thực hiện thêm một yêu cầu HTTP trước khi commit. Trong thời gian chờ mạng, các giao dịch khác muốn sửa A có thể bị giữ lại. Khóa được nhả khi transaction kết thúc, không phải ngay sau từng lệnh **SET**.

Các nguyên nhân kéo dài transaction thường gặp gồm: gọi API ngoài khi đang giữ transaction; xử lý danh sách khổng lồ trong một lần ghi; quét quá nhiều node trước khi cập nhật; chờ input; hoặc giữ session/transaction không đóng đúng cách.

Trong ứng dụng Java, thiết kế transaction chỉ chứa thao tác database cần tính nguyên tử và phần tính toán ngắn gọn. Thực hiện gọi HTTP, gửi email, xử lý file lớn và các bước không cần giữ khóa **bên ngoài** callback transaction.

## 3. Minh họa một xung đột ghi thông thường

Tạo dữ liệu một lần trên **database thử nghiệm**:

~~~cypher
CREATE CONSTRAINT demo_txn_account_id IF NOT EXISTS
FOR (a:DemoTxnAccount)
REQUIRE a.id IS UNIQUE;
~~~

~~~cypher
CREATE
  (:DemoTxnAccount {id: 'A', counter: 0}),
  (:DemoTxnAccount {id: 'B', counter: 0});
~~~

Hai phiên làm việc cùng cập nhật tài khoản A:

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
SET a.counter = a.counter + 1
RETURN a.counter;
~~~

Nếu T1 chưa hoàn tất và T2 cần cập nhật A, T2 có thể đợi khóa do T1 giữ. Khi T1 commit hoặc rollback, T2 tiếp tục. Đây là **lock contention**; **không** phải deadlock vì T1 không cần khóa nào do T2 đang giữ.

Khi giao dịch chỉ tăng bộ đếm theo kiểu **SET a.counter = a.counter + 1**, Cypher nhìn thấy sự phụ thuộc trực tiếp giữa giá trị đọc và giá trị ghi trên cùng node; Neo4j tự lấy khóa ghi **trước khi đọc giá trị dùng để cập nhật**. Cách này bảo vệ trường hợp tăng đếm đơn giản khỏi *lost update*. Cần kiểm tra tính đúng đắn cho biểu thức phức tạp hoặc trường hợp giá trị được lấy ra sớm ở nơi khác.

## 4. Deadlock: đồ thị chờ tạo thành một vòng

Một deadlock có thể hình thành qua bốn bước:

1. T1 sửa **A**, giữ khóa A.
2. T2 sửa **B**, giữ khóa B.
3. T1 tiếp tục cần B, nhưng B đang do T2 giữ.
4. T2 tiếp tục cần A, nhưng A đang do T1 giữ.

~~~mermaid
flowchart LR
  T1["Transaction T1 giữ khóa A"] -->|"đợi khóa B"| T2["Transaction T2 giữ khóa B"]
  T2 -->|"đợi khóa A"| T1
~~~

Neo4j có **deadlock detection**. Khi phát hiện vòng chờ, hệ thống kết thúc một trong các giao dịch liên quan để vòng chờ được tháo gỡ; giao dịch đó bị rollback. Lỗi deadlock có mã kiểu cũ:

~~~text
Neo.TransientError.Transaction.DeadlockDetected
~~~

Trong các bản Neo4j từ **5.25**, thông báo còn có thể đi kèm **GQLSTATUS 50N05**. Đây là lỗi **tạm thời có thể retry**, nhưng retry không sửa được nguyên nhân nếu mọi lần chạy vẫn tranh nhau cùng các tài nguyên theo thứ tự ngược.

### 4.1. Tái hiện deadlock trong hai phiên Cypher Shell

**Chỉ thực hiện trong database thử nghiệm** đã tạo A, B ở mục 3. Mở hai terminal **cypher-shell** riêng; **:begin**, **:commit**, **:rollback** là lệnh điều khiển của client, không phải cú pháp Cypher thuần.

**Phiên 1 — T1:**

~~~text
:begin
~~~

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
SET a.counter = a.counter + 1;
~~~

**Phiên 2 — T2:**

~~~text
:begin
~~~

~~~cypher
MATCH (b:DemoTxnAccount {id: 'B'})
SET b.counter = b.counter + 1;
~~~

**Trở lại T1**, yêu cầu cập nhật B:

~~~cypher
MATCH (b:DemoTxnAccount {id: 'B'})
SET b.counter = b.counter + 1;
~~~

Lệnh này sẽ chờ T2 còn giữ khóa B. **Sau đó ở T2**, yêu cầu cập nhật A:

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
SET a.counter = a.counter + 1;
~~~

Khi cả hai khóa còn được giữ và hai lệnh đang chờ nhau, một giao dịch sẽ bị từ chối vì deadlock. Bên bị hủy cần kết thúc/rollback transaction theo trạng thái client; bên còn lại có thể tiếp tục và commit. Dọn sạch mọi transaction mở bằng **:commit** hoặc **:rollback** phù hợp. Kết quả thời điểm và bên bị hủy phụ thuộc lịch chạy, vì thế đây là bài mô phỏng có điều kiện, không phải kiểm thử luôn sinh cùng một thông báo.

**Cách ngăn vòng chờ:** mọi luồng nghiệp vụ cùng cần sửa A và B đều sửa A **trước** B. Khi đó một giao dịch phải đợi ở A ngay từ đầu; nó chưa giữ B để tạo vòng chờ ngược. Tuy nhiên, những khóa nội bộ do Neo4j tạo ra (đặc biệt qua **MERGE** và cập nhật index/relationship) có thể phức tạp hơn, nên thống nhất thứ tự **giảm rủi ro mạnh** chứ không phải bảo đảm tuyệt đối không bao giờ deadlock.

## 5. Lost update: dữ liệu sai ngay cả khi không có deadlock

### 5.1. Sai lầm: đưa giá trị cũ ra khỏi đường cập nhật có khóa

Một ví dụ dễ mắc:

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
WITH a, a.counter AS oldCounter
// Các bước tính toán khác có thể diễn ra tại đây.
SET a.counter = oldCounter + 1
RETURN a.counter;
~~~

Nếu hai giao dịch cùng đọc **oldCounter = 0** rồi mới chờ đến bước ghi, cả hai có thể cố ghi lại **1** thay vì kết quả mong muốn **2**. Lý do là biểu thức **SET** không còn phụ thuộc trực tiếp vào việc đọc **a.counter** ở lúc cập nhật: giá trị cũ đã được lấy trước vào biến. Vấn đề tương tự xảy ra khi Java đọc giá trị, tính toán ở ứng dụng rồi gửi **SET a.counter = $newValue**.

Đối với phép tăng đơn giản, ưu tiên:

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
SET a.counter = a.counter + 1
RETURN a.counter AS counter;
~~~

Neo4j nhận biết phép đọc phụ thuộc trực tiếp trong **SET** và khóa node trước khi đọc để cập nhật. Với dữ liệu có thể thiếu thuộc tính, xác định giá trị ban đầu rõ ràng và kiểm chứng biểu thức trên phiên bản đang dùng, ví dụ **coalesce(a.counter, 0) + 1**.

### 5.2. Khi phải đọc–tính–ghi nhiều bước

Nếu một quy tắc cần đọc thuộc tính, gọi nhiều phép tính rồi mới cập nhật, không nên suy ra rằng việc đưa chúng vào cùng **MATCH** là đủ. Các lựa chọn gồm:

- Viết lại thành phép cập nhật trực tiếp trên thuộc tính đang đọc, để Neo4j nhận biết phụ thuộc và tự khóa đúng thời điểm.
- Khi thực sự cần bảo vệ chuỗi đọc–ghi, chủ động lấy khóa ghi **trước khi đọc**. Tài liệu Neo4j mô tả kỹ thuật ghi một thuộc tính tạm rồi xóa ngay trong cùng transaction, nhưng đây là một cơ chế đặc biệt có chi phí ghi và cần kiểm thử; không nên lạm dụng.
- Thiết kế **optimistic concurrency control** với cột phiên bản và xử lý xung đột ở ứng dụng, kèm cơ chế xác nhận điều kiện được kiểm tra đúng trong vùng khóa. Chỉ so sánh phiên bản trong một phép đọc không khóa rồi ghi sau đó **chưa đủ** để bảo đảm không lost update.

Ví dụ kỹ thuật **ghi khóa tạm** theo tài liệu Neo4j, chỉ dùng nếu mô hình thực sự cần giữ khóa trước khi lấy giá trị:

~~~cypher
MATCH (a:DemoTxnAccount {id: 'A'})
SET a._lockMarker = true
REMOVE a._lockMarker
WITH a, a.counter AS oldCounter
// Chỉ tính toán ngắn gọn trong transaction hiện tại.
SET a.counter = oldCounter + 1
RETURN a.counter;
~~~

Việc xóa thuộc tính tạm **không thả khóa sớm**: khóa ghi được giữ đến khi transaction kết thúc. Nếu cập nhật nhiều tài nguyên, vẫn cần thứ tự khóa ổn định. Đừng dùng mẫu này cho một phép cộng đơn giản vốn đã có **SET a.counter = a.counter + 1**.

## 6. MERGE, constraint và tranh chấp khi ghi dữ liệu liên kết

**MERGE** là lệnh tìm hoặc tạo một mẫu graph. Dưới ghi đồng thời, cần phân biệt **định danh node** với **tạo relationship**:

~~~cypher
CREATE CONSTRAINT demo_txn_customer_id IF NOT EXISTS
FOR (c:DemoTxnCustomer)
REQUIRE c.id IS UNIQUE;
~~~

~~~cypher
MERGE (c:DemoTxnCustomer {id: $customerId})
ON CREATE SET c.createdAt = datetime()
RETURN c;
~~~

**Uniqueness constraint** bảo vệ định danh node khi nhiều giao dịch cùng tạo khách hàng. **MERGE** tự nó không thay thế một ràng buộc duy nhất trên thuộc tính định danh; nếu thiếu constraint, có thể xuất hiện các node trùng khóa nghiệp vụ trong tải đồng thời.

Khi **hai node đầu–cuối đã được xác định**, mẫu:

~~~cypher
MATCH (c:DemoTxnCustomer {id: $customerId})
MATCH (p:DemoTxnProduct {sku: $sku})
MERGE (c)-[:DEMO_FOLLOWS]->(p);
~~~

có cơ chế khóa nhằm ngăn hai giao dịch cùng lúc tạo trùng **relationship của mẫu đó** giữa hai node đã tìm thấy. Nhưng việc MERGE phải tìm rồi có thể lấy thêm khóa và kiểm tra lại, nên trong workload ghi lớn, **MERGE phức tạp có thể tăng contention hoặc deadlock**.

**Không thay MERGE thành CREATE một cách máy móc**: CREATE tạo mới vô điều kiện nên chỉ phù hợp khi dữ liệu đầu vào chắc chắn phải tạo mới, hoặc có cơ chế chống trùng bên ngoài. Một chiến lược thực tế:

1. **MERGE node** theo khóa nghiệp vụ có uniqueness constraint để tránh tạo node trùng.
2. **MATCH** các node nguồn và đích đã tồn tại bằng index/constraint.
3. **MERGE relationship** khi cần hành vi idempotent; dùng **CREATE** khi yêu cầu là ghi một relationship mới và nghiệp vụ cho phép nhiều quan hệ.
4. Với danh sách lớn, chia batch và xử lý endpoint theo thứ tự nhất quán để giảm số transaction cạnh tranh trên cùng node.

**Node nhiều relationship không mặc nhiên là “hotspot không thể tối ưu”.** Neo4j có chiến lược khóa cho dense node và quan hệ theo định dạng lưu trữ. Vấn đề cần đo là những transaction có thật sự đụng cùng node/relationship, cùng cấu trúc bên trong hoặc cùng dữ liệu định danh hay không.

## 7. Những chiến lược giảm tranh chấp hiệu quả

| Chiến lược | Cách áp dụng | Đánh đổi / giới hạn |
|---|---|---|
| **Thứ tự ghi cố định** | Khi sửa nhiều tài khoản, xếp theo ID rồi cập nhật theo cùng thứ tự ở mọi luồng | Giảm vòng chờ; không kiểm soát được mọi khóa Neo4j tự lấy |
| **Transaction ngắn** | Chỉ giữ các thao tác ghi và tính toán cần tính nguyên tử; đóng transaction ngay | Phải tách logic ngoài database ra khỏi vùng transaction |
| **Giảm số giao dịch chạm “hot node”** | Phân phối công việc theo khóa nghiệp vụ; hàng đợi đơn cho cùng ID | Có thể tăng độ trễ hàng đợi nhưng giảm tranh khóa và retry |
| **Bước ghi hẹp, có index** | Dùng uniqueness constraint/range index để xác định node nhanh trước khi ghi | Index cũng có chi phí cập nhật và lưu trữ |
| **Batch có kích thước phù hợp** | Chia nạp hàng triệu dòng thành các transaction vừa phải | Quá lớn giữ khóa lâu; quá nhỏ tăng overhead commit |
| **Ghi nhận sự kiện thay vì sửa một counter trung tâm** | Tạo event riêng rồi tổng hợp định kỳ, hoặc chia counter thành nhiều shard | Đọc tổng phức tạp hơn; cần chấp nhận mô hình nhất quán tương ứng |
| **Retry có giới hạn** | Retry deadlock/transient error với backoff và jitter | Giảm lỗi nhất thời, nhưng retry liên tục có thể làm quá tải tăng thêm |
| **Điều tiết mức song song** | Giới hạn worker theo partition/key, điều chỉnh số transaction ghi đồng thời | Tổng thông lượng có thể tăng dù số worker giảm; cần đo thực tế |

### 7.1. Sắp thứ tự tài nguyên trước khi cập nhật

Khi giao dịch cập nhật nhiều node, dùng khóa nghiệp vụ **ổn định** (ví dụ accountId) để đưa các thao tác về một thứ tự nhất quán:

~~~cypher
UNWIND $accountIds AS accountId
WITH DISTINCT accountId
ORDER BY accountId
MATCH (a:DemoTxnAccount {id: accountId})
SET a.counter = a.counter + 1
RETURN a.id AS id, a.counter AS counter;
~~~

Lưu ý: **ORDER BY** sắp xếp dòng đi vào mệnh đề tiếp theo theo ID; việc triển khai khóa nội bộ, thống kê và query planner vẫn phải được kiểm tra khi chạy thực tế. Nếu yêu cầu chặt chẽ về thứ tự lấy khóa, một cách rõ ràng hơn là ứng dụng sắp ID và thực hiện từng cập nhật tuần tự trong **cùng transaction**, đồng thời thống nhất quy tắc cho **mọi** luồng ghi liên quan. Đừng dùng thứ tự ID nội bộ của Neo4j làm khóa nghiệp vụ lâu dài.

### 7.2. Rút ngắn thời gian giữ khóa

Chọn ranh giới transaction theo một **invariant nghiệp vụ**: ví dụ “trừ điểm và ghi bản ghi thay đổi điểm phải cùng commit”. Không kéo theo việc gọi API thanh toán, gửi email hay chờ phản hồi người dùng trong transaction. Với batch dữ liệu rất lớn, chia theo nhóm hợp lý; các batch cần đảm bảo có thể chạy lại an toàn.

### 7.3. Giảm hotspot thay vì chỉ tăng retry

Nếu mọi request cùng sửa node **(:Statistics {id: 'global'})**, mọi transaction vẫn phải gặp một điểm nóng dù hệ thống có hàng triệu node khác. Có thể dùng sharded counter, event log hoặc tổng hợp theo khoảng thời gian; mỗi cách có đánh đổi về tốc độ đọc, tính nhất quán và độ phức tạp.

**Tăng số luồng vô hạn** thường làm tăng thời gian chờ và deadlock chứ không bảo đảm tăng thông lượng. Thử các mức concurrency khác nhau và đo throughput, p95/p99 latency, tỷ lệ retry, thời gian chờ khóa trước khi chọn cấu hình.

## 8. Retry đúng cách trong Neo4j Java Driver

### 8.1. Managed transaction với executeWrite

Java Driver hỗ trợ **Session.executeWrite()** để chạy transaction có cơ chế **tự retry khi gặp lỗi tạm thời**; sau khoảng retry tối đa cấu hình, driver trả ngoại lệ nếu vẫn không thành công. Ví dụ minh họa dành cho Neo4j Java Driver đời mới:

~~~java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionConfig;

// Driver được tạo một lần và có thể dùng chung giữa các luồng.
long increment(Driver driver, String accountId) {
    var txConfig = TransactionConfig.builder()
        .withTimeout(Duration.ofSeconds(5))
        .withMetadata(Map.of("operation", "increment-account-counter"))
        .build();

    try (var session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        return session.executeWrite(tx -> {
            var result = tx.run("""
                MATCH (a:DemoTxnAccount {id: $id})
                SET a.counter = a.counter + 1
                RETURN a.counter AS counter
                """, Map.of("id", accountId));
            return result.single().get("counter").asLong();
        }, txConfig);
    }
}
~~~

Điểm cần chú ý:

- **Driver** có thể chia sẻ giữa các luồng, nhưng **Session không thread-safe**; tạo session riêng cho mỗi luồng/yêu cầu và đóng bằng **try-with-resources**.
- Trong callback, thực hiện **Cypher**, tiêu thụ **Result** và trả về giá trị thuần. Không trả một **Result** chưa tiêu thụ ra ngoài transaction.
- Driver có thể **chạy lại callback**. Vì vậy không gửi email, gọi hệ thống thanh toán hoặc cập nhật trạng thái bộ nhớ bên ngoài trong callback; tránh thao tác phụ không thể rollback.
- Transaction đã bị phát hiện deadlock sẽ bị **rollback**, nên khi retry thành công, phép tăng trực tiếp được áp dụng vào giao dịch mới. Tuy nhiên, với các thao tác nghiệp vụ không được phép thực hiện hai lần khi kết quả commit không rõ, cần **idempotency key** và cơ chế chống trùng trong dữ liệu.
- **Transaction timeout** trong ví dụ giới hạn thời gian transaction; nó không bảo đảm loại trừ mọi deadlock hay thay thế việc thiết kế thứ tự cập nhật.

Với **explicit transaction** qua **session.beginTransaction()**, Java Driver **không tự retry callback giống executeWrite**. Nếu tự xây retry, phải khởi tạo **transaction mới** cho từng lần thử, chỉ bắt các lỗi phù hợp (chẳng hạn **RetryableException**), dùng số lần thử giới hạn và **backoff + jitter**; không lặp vô hạn hoặc retry lỗi cú pháp và lỗi ràng buộc dữ liệu không tạm thời.

### 8.2. Giao dịch có thể thử lại và tác dụng ngoài database

Giả sử callback giao dịch vừa ghi đơn hàng vừa gọi cổng thanh toán. Khi deadlock khiến transaction rollback, driver retry callback và gọi cổng thanh toán lần nữa: phía thanh toán có thể nhận hai yêu cầu trong khi Neo4j chỉ commit một đơn. Vì vậy:

1. Transaction Neo4j chỉ ghi thông tin cần tính nguyên tử, ví dụ đơn hàng và trạng thái xử lý.
2. Dùng **mã yêu cầu duy nhất** hoặc **idempotency key** có constraint để nhận diện yêu cầu đã xử lý.
3. Điều phối side effect bên ngoài bằng cách xử lý sau commit hoặc **transactional outbox** cùng cơ chế giao nhận có thể lặp, idempotent ở bên nhận.

Nếu yêu cầu đảm bảo “đúng một lần” ở cấp nghiệp vụ, **tự động retry không đủ**: phải thiết kế phát hiện trùng và xử lý trường hợp kết quả commit chưa rõ vì mất kết nối.

### 8.3. Spring Data Neo4j và Spring Transaction

Trong **Spring Data Neo4j**, có thể đặt các thay đổi liên quan trong service method được quản lý bởi **@Transactional**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class AccountService {
    private final AccountRepository repository;

    AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void updateBoth(String firstId, String secondId) {
        // Repository hoặc Neo4jClient thực hiện thao tác ghi
        // trong transaction của Spring.
        // Mọi luồng cần thống nhất thứ tự khóa theo ID.
    }
}
~~~

**@Transactional** quyết định ranh giới commit/rollback của giao dịch Spring; nó **không tự mang đến retry deadlock** như callback **executeWrite()** của Java Driver. Nếu thêm cơ chế retry ở tầng Spring (chẳng hạn Spring Retry), cần cấu hình để **mỗi lần thử có transaction mới**, bắt đúng loại ngoại lệ tạm thời sau khi được dịch bởi tầng dữ liệu, và tránh retry lồng nhau không kiểm soát. Cũng cần nhớ lời gọi nội bộ trong cùng instance có thể không đi qua proxy áp dụng **@Transactional**, tùy cấu hình Spring.

## 9. Quan sát và chẩn đoán giao dịch bị chờ

### 9.1. Xem giao dịch đang chạy

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, username, status, currentQueryId,
      currentQuery, elapsedTime, waitTime, activeLockCount
RETURN transactionId, username, status, currentQueryId,
       currentQuery, elapsedTime, waitTime, activeLockCount
ORDER BY waitTime DESC;
~~~

Một số dấu hiệu:

- **status = Blocked** hoặc **waitTime** tăng: transaction có thể đang chờ tài nguyên.
- **elapsedTime** lớn nhưng **waitTime** nhỏ: có thể tốn CPU, I/O, xử lý dữ liệu hoặc đang chờ lý do khác; không vội kết luận deadlock.
- **activeLockCount** lớn: transaction giữ nhiều khóa, nhưng số lượng khóa **không** tự nó chứng minh có sự cố.
- **currentQueryId** giúp xác định truy vấn để kiểm tra active locks ở môi trường có quyền phù hợp.

Để xem khóa đang giữ của một truy vấn:

~~~cypher
CALL dbms.listActiveLocks($queryId)
YIELD mode, resourceType, resourceId
RETURN mode, resourceType, resourceId;
~~~

Tham số **$queryId** lấy từ **currentQueryId** của **SHOW TRANSACTIONS**. Thủ tục này cần quyền quản trị thích hợp và có thể có khác biệt nhỏ tùy bản Neo4j. Không mặc định mọi vai trò ứng dụng đều xem được giao dịch của người dùng khác; khả năng xem phụ thuộc quyền **SHOW TRANSACTION**. Chỉ dùng **TERMINATE TRANSACTIONS** khi đã đánh giá được tác động đến công việc đang chạy và có quyền vận hành hợp lệ.

### 9.2. Phân biệt lỗi và cấu hình timeout

| Dấu hiệu | Ý nghĩa | Việc nên làm |
|---|---|---|
| **DeadlockDetected** | Neo4j phát hiện vòng chờ, hủy giao dịch để giải phóng tiến trình | Retry có giới hạn; tìm chuỗi cập nhật ngược thứ tự |
| **Lock acquisition timeout** | Giao dịch chờ một khóa quá thời hạn | Tìm transaction giữ khóa lâu; rút ngắn vùng ghi |
| **Transaction timeout** | Transaction vượt giới hạn thực thi | Tối ưu truy vấn, chia batch và kiểm tra giới hạn phù hợp |
| **Constraint violation** | Ghi vi phạm quy tắc duy nhất/tồn tại/kiểu | Sửa dữ liệu hoặc logic; không retry mù như lỗi transient |
| **Wait time cao, không báo lỗi** | Giao dịch có thể hoàn tất sau khi chờ | Đo độ trễ và thông lượng, xác định hotspot |

Trong cấu hình server Neo4j, **db.transaction.timeout** giới hạn thời gian giao dịch (giá trị **0** thường nghĩa là không bật giới hạn mặc định); **db.lock.acquisition.timeout** giới hạn thời gian chờ lấy từng khóa (giá trị **0** mặc định vô hiệu hóa cơ chế timeout khóa). Các giá trị này khác nhau, và transaction có timeout do driver chỉ định có thể ghi đè timeout mặc định của server. Chỉnh sửa cấu hình cần dựa vào phiên bản và quy trình vận hành, **không tăng timeout như giải pháp chính cho deadlock**.

### 9.3. Thiết lập quan sát trước/sau thay đổi

Ghi lại theo khoảng tải đại diện:

- Tỷ lệ transaction thành công/thất bại; số deadlock và số lần retry do lỗi transient.
- **p50/p95/p99** độ trễ giao dịch ghi và thông lượng commit/giây.
- **waitTime**, số giao dịch blocked, các transaction lâu nhất và nhóm khóa tranh chấp.
- Các truy vấn viết phổ biến, số node/relationship mỗi transaction, kích thước batch.
- Thời gian quét, **DB Hits**, khả năng dùng index qua **EXPLAIN/PROFILE** và tần suất chạm cùng entity.

Theo dõi thêm metadata transaction và request ID để liên hệ log ứng dụng với log database. Chỉ ghi thông tin cần thiết, tránh phát tán tham số chứa dữ liệu nhạy cảm trong log giám sát.

## 10. Bài thực hành xử lý tranh chấp

### Bài 1 — Đọc biểu đồ chờ

Cho T1 giữ khóa A và đợi B, T2 giữ B và đợi C, T3 giữ C và đợi A.

**Hỏi:** có deadlock không? Nếu T3 không còn đợi A mà commit được thì sao?

*Gợi ý:* vẽ cạnh **T1 → T2**, **T2 → T3**, **T3 → T1** để xác định vòng. Khi một cạnh chờ biến mất, cần đánh giá lại việc các giao dịch có tiến lên được hay không.

### Bài 2 — Sửa phép tăng mất cập nhật

Tìm lỗi trong mẫu:

~~~cypher
MATCH (n:DemoTxnAccount {id: 'A'})
WITH n, n.counter AS oldValue
SET n.counter = oldValue + 1;
~~~

Viết lại thành một phép tăng trực tiếp và giải thích vì sao **giữ giá trị cũ trong biến** có thể làm mất cập nhật dưới ghi đồng thời.

### Bài 3 — Thiết kế thứ tự ghi

Một nhóm service chuyển trạng thái đồng thời trên hai node Account với các ID **A**, **B**; service S1 cập nhật A trước B, service S2 cập nhật B trước A.

**Yêu cầu:** đề xuất thứ tự cập nhật chung, vị trí commit, chính sách retry và kế hoạch kiểm thử với tải đồng thời. Giải thích vì sao chỉ tăng transaction timeout là không đủ.

### Bài 4 — Quyết định về MERGE và constraint

Một tác vụ nhập dữ liệu gọi **MERGE (c:Customer {id: $id})** đồng thời trên nhiều worker nhưng chưa có uniqueness constraint. Hãy xác định nguy cơ dữ liệu trùng và soạn lệnh tạo constraint phù hợp trước khi chạy import, có xét dữ liệu trùng sẵn có.

### Bài 5 — Quy trình xử lý sự cố

Trong production, số transaction **Blocked** tăng, **waitTime** tăng, p95 ghi tăng nhưng chưa có lỗi **DeadlockDetected**. Trình bày ba phép quan sát để xác định nguyên nhân và hai thay đổi ít rủi ro có thể thử trước khi thay đổi cấu trúc graph.

## Tổng kết

Khi nhiều giao dịch ghi cùng một graph, **lock contention** có thể làm chậm hệ thống, **deadlock** cần vòng chờ và thường dẫn đến rollback một giao dịch, còn **lost update** có thể gây dữ liệu sai mà không cần deadlock. Với Neo4j, cách xử lý hiệu quả là:

1. Nhận diện chính xác điều kiện chạm cùng node/relationship và đường đi của các khóa.
2. Viết phép cập nhật phụ thuộc giá trị theo cách Cypher có thể bảo vệ; đặt constraint cho định danh nghiệp vụ.
3. Giữ transaction ngắn, nhất quán thứ tự ghi và phân phối các thao tác trên hotspot.
4. Dùng managed transaction của Java Driver để retry lỗi transient có giới hạn, với callback an toàn khi chạy lại; kiểm soát việc retry riêng nếu ứng dụng dùng Spring Data Neo4j.
5. Đo **waitTime**, lỗi, throughput và p95 trước khi kết luận cần đổi mô hình hoặc cấu hình timeout.

### Tài liệu tham khảo chính thức

- [Neo4j Operations Manual – Concurrent data access: locking, deadlocks và lost updates](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Neo4j Operations Manual – Database transactions](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/)
- [Neo4j Operations Manual – Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/)
- [Neo4j Java Driver Manual – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Cypher Manual – MERGE and concurrent relationship merges](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
