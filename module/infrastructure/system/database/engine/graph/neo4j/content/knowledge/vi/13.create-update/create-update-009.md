# Thiết kế cập nhật có tính lũy đẳng và ngăn dữ liệu trùng trong Neo4j

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một lệnh ghi có thể được thực thi nhiều lần khi ứng dụng retry, nhập lại dữ liệu hoặc nhận trùng thông điệp.
- Chọn **khóa định danh ổn định**, tạo **uniqueness constraint** và dùng `MERGE` đúng cách để cập nhật node/relationship.
- Phân biệt thao tác lũy đẳng với thao tác làm tăng bộ đếm, nối danh sách hoặc ghi thời gian hiện tại.
- Thiết kế xử lý sự kiện lặp, cập nhật sai thứ tự và ghi đồng thời; kiểm chứng rằng đồ thị không phát sinh bản ghi trùng.

Trong mô hình **property graph** của Neo4j, một thực thể thường là node, liên kết giữa các thực thể là relationship; cả hai có thể có thuộc tính. Chương **Tạo và cập nhật** tập trung vào việc ghi dữ liệu bằng Cypher sao cho các lần chạy lại không phá hỏng cấu trúc đồ thị.

## 1. Lũy đẳng nghĩa là gì?

Một phép ghi là **lũy đẳng** (*idempotent*) nếu thực hiện lại với **cùng đầu vào** cho cùng kết quả trạng thái logic như khi thực hiện một lần. Ký hiệu `G` là trạng thái đồ thị và `m` là thông điệp đầu vào:

\[
f(f(G,m),m)=f(G,m)
\]

Ví dụ, dịch vụ nhận lại cùng yêu cầu đồng bộ khách hàng do timeout, worker xử lý lại một bản tin từ hàng đợi, hoặc job import chạy lại sau khi bị ngắt. Nếu lần đầu đã tạo khách hàng `C-101`, lần sau phải tìm đúng node đó để cập nhật, thay vì tạo thêm một node cùng định danh.

| Cách ghi | Chạy lại cùng đầu vào | Có lũy đẳng? |
| --- | --- | --- |
| `CREATE (c:Customer {customerId: $id})` | Tạo thêm node | Không |
| `MERGE (c:Customer {customerId: $id})` | Khớp node có sẵn, nếu tìm thấy | Có trong điều kiện phù hợp; cần constraint để an toàn khi ghi đồng thời |
| `SET c.name = $name` | Gán lại cùng giá trị | Có |
| `SET c.points = c.points + 10` | Cộng thêm mỗi lần chạy | Không |
| `SET c.tags = c.tags + $tag` | Thêm phần tử lặp vào danh sách | Không |
| `SET c.updatedAt = datetime()` | Thay đổi thời gian sau mỗi lần retry | Không nếu xét toàn bộ thuộc tính |

**Lưu ý về phạm vi:** `MERGE` không tự biến mọi câu truy vấn thành lũy đẳng. Khóa nhận diện phải ổn định, các thao tác `SET` phải phù hợp, và cần tính đến nhiều transaction ghi cùng lúc.

## 2. Xác định danh tính trước khi viết câu truy vấn

Một node phải có **business key** — khóa định danh không đổi khi các thông tin khác được chỉnh sửa. Ví dụ:

- `Customer.customerId` là mã khách hàng từ hệ thống nguồn; tên và email chỉ là dữ liệu cập nhật.
- `Order.orderId` là mã đơn hàng; trạng thái đơn thay đổi nhưng định danh vẫn giữ nguyên.
- Với hệ thống nhiều tenant, cặp `(tenantId, customerId)` mới là danh tính duy nhất; hai tenant có thể dùng cùng mã khách hàng.
- Một sự kiện nhập từ hệ thống bên ngoài có `eventId` cố định, được gửi lại nguyên vẹn khi retry; không tạo UUID mới cho mỗi lần xử lý lại.

### Dùng uniqueness constraint để bảo vệ dữ liệu

Tạo constraint **trước khi** chạy nhiều job ghi. Cú pháp sau phù hợp với Cypher trên các phiên bản Neo4j hiện đại hỗ trợ ràng buộc duy nhất:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;

CREATE CONSTRAINT event_id_unique IF NOT EXISTS
FOR (e:OrderEvent)
REQUIRE e.eventId IS UNIQUE;
~~~

Nếu `customerId` chỉ duy nhất **trong từng tenant**, chọn constraint tổng hợp và sử dụng **cả hai** trường trong mọi lần nhận diện:

~~~cypher
CREATE CONSTRAINT tenant_customer_unique IF NOT EXISTS
FOR (c:TenantCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

Constraint duy nhất ngăn hai node **cùng label** sử dụng chung giá trị khóa khi khóa đó hiện diện; đồng thời cung cấp cơ sở cho tra cứu hiệu quả. Nó **không mặc định bắt buộc thuộc tính phải tồn tại**. Hãy kiểm tra hoặc từ chối đầu vào thiếu khóa. Nếu đồ thị đang có bản ghi trùng, cần giải quyết dữ liệu cũ trước khi tạo constraint vì thao tác tạo có thể thất bại.

Không nên chọn tên, email dễ thay đổi, timestamp hoặc ID sinh ngẫu nhiên trong mỗi lần retry làm khóa để `MERGE`.

## 3. Upsert node bằng MERGE và SET

**Upsert** là tìm bản ghi bằng khóa: nếu chưa có thì tạo, nếu đã có thì cập nhật thông tin.

~~~cypher
MERGE (c:Customer {customerId: $customerId})
ON CREATE SET
    c.createdAt = datetime($createdAt),
    c.createdBy = $source
SET
    c.displayName = $displayName,
    c.email = $email
RETURN c.customerId AS customerId;
~~~

Ví dụ tham số:

~~~json
{
  "customerId": "C-101",
  "createdAt": "2026-11-25T08:00:00Z",
  "source": "crm",
  "displayName": "Nguyễn Lan",
  "email": "lan@example.org"
}
~~~

Khi chạy lại với cùng tham số:

1. `MERGE` tìm theo `Customer.customerId`, chỉ tạo node nếu chưa tìm thấy.
2. `ON CREATE SET` chỉ chạy khi node được tạo; thời điểm tạo gốc được giữ nguyên trong các lần retry.
3. `SET` gán cùng thông tin, không cộng dồn hoặc tạo bản ghi khác.

Một lỗi phổ biến là đưa thuộc tính **có thể đổi** vào mẫu nhận diện:

~~~cypher
// Sai: displayName không phải khóa.
MERGE (c:Customer {
  customerId: $customerId,
  displayName: $displayName
});
~~~

Khi tên đổi, Neo4j không còn khớp toàn bộ mẫu. Nếu chưa có constraint, một node khác có thể được tạo; nếu có constraint riêng trên `customerId`, câu ghi có thể báo xung đột. Cách đúng là `MERGE` **chỉ bằng khóa**, rồi `SET` các trường có thể cập nhật.

**Xử lý null:** `MERGE` không chấp nhận khóa có giá trị `null`; hãy kiểm tra `customerId` trước khi gọi truy vấn. Trong Neo4j, `SET c.email = null` xóa thuộc tính `email`: nếu `null` nghĩa là “không có dữ liệu mới” thì ứng dụng phải có chính sách bỏ qua trường đó, thay vì tự động ghi `null`. Tương tự, cần chuẩn hóa chữ hoa/thường, khoảng trắng, mã tenant theo quy tắc nghiệp vụ **trước khi định danh**; `C-101` và `c-101` là các giá trị khác nhau nếu chưa được chuẩn hóa.

### Tránh thao tác phụ làm mất lũy đẳng

Đoạn sau tuy dùng `MERGE` nhưng **không** lũy đẳng vì mỗi lần gọi tăng điểm:

~~~cypher
MERGE (c:Customer {customerId: $customerId})
SET c.points = coalesce(c.points, 0) + $earnedPoints;
~~~

Nếu điểm bắt nguồn từ một giao dịch đã có `transactionId` riêng, nên lưu sự kiện/giao dịch theo ID duy nhất rồi tính điểm từ các bản ghi đó. Đối với thuộc tính thời gian “lần nhận request gần nhất”, hãy xác định rõ đây là chủ đích theo dõi hoạt động (có thể thay đổi khi retry), không xem toàn bộ node là bất biến sau lần chạy đầu.

## 4. Upsert relationship mà không sinh cạnh trùng

Với cạnh `FOLLOWS`, cần nhận diện hai node đầu mút trước, sau đó mới `MERGE` relationship:

~~~cypher
MATCH (a:User {userId: $followerId})
MATCH (b:User {userId: $followeeId})
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.followedAt = datetime($followedAt)
RETURN r;
~~~

Cần đặt constraint riêng cho `User.userId`. Câu trên phù hợp khi hai user đã tồn tại và các thao tác diễn ra tuần tự. Nếu cần tạo cả hai user, dùng **hai `MERGE` node riêng** rồi mới `MERGE` cạnh. Tránh gộp tất cả thành một mẫu:

~~~cypher
// Khó kiểm soát: MERGE cả mẫu có thể cố tạo lại node đã có.
MERGE (a:User {userId: $followerId})
      -[:FOLLOWS]->
      (b:User {userId: $followeeId});
~~~

**Ghi đồng thời là trường hợp riêng:** `MERGE` trên cạnh, chỉ dựa vào hai đầu mút, không phải ràng buộc duy nhất ở mức database cho cặp node. Nếu nhiều transaction tạo cùng cạnh đúng lúc, cần bổ sung cơ chế bảo vệ khi yêu cầu không được có cạnh trùng ở mọi tình huống.

Một lựa chọn trên các phiên bản Neo4j hỗ trợ **relationship property uniqueness constraint** là gán `edgeId` ổn định và ràng buộc duy nhất:

~~~cypher
CREATE CONSTRAINT follows_edge_unique IF NOT EXISTS
FOR ()-[r:FOLLOWS]-()
REQUIRE r.edgeId IS UNIQUE;

MATCH (a:User {userId: $followerId})
MATCH (b:User {userId: $followeeId})
MERGE (a)-[r:FOLLOWS {edgeId: $edgeId}]->(b)
ON CREATE SET r.followedAt = datetime($followedAt);
~~~

Ứng dụng phải tạo `edgeId` xác định từ **loại quan hệ + định danh đầu nguồn + định danh đích** (hoặc dùng ID liên kết cố định từ nguồn), không sinh ngẫu nhiên trong mỗi retry. Với quan hệ có hướng, thứ tự hai đầu mút là một phần danh tính; với quan hệ vô hướng, cần chuẩn hóa thứ tự hai ID. Unique constraint giúp ngăn cạnh cùng `edgeId` được commit trùng, nhưng transaction thua cuộc có thể nhận lỗi xung đột và cần được xử lý/retry hợp lý. Nếu cùng `edgeId` lại chỉ đến hai đầu mút khác nhau, đó là lỗi dữ liệu nguồn cần phát hiện.

## 5. Nhận thông điệp nhiều lần: lưu sự kiện theo eventId

Với hệ thống đồng bộ, consumer thường phải chấp nhận cách giao thông điệp *at least once*: một bản tin có thể được phát lại. Ví dụ thông điệp “đơn `O-42` đã giao” có `eventId = EVT-9001`. Nếu mỗi lần nhận lại đều tạo sự kiện hoặc cộng vào tổng số lần giao, dữ liệu sẽ sai.

Mô hình nên dùng **node sự kiện có định danh duy nhất** và gắn với đơn:

~~~mermaid
flowchart LR
    M["Nhận eventId + payloadHash"] --> U["MERGE OrderEvent theo eventId"]
    U --> C{"Định danh và payload có khớp?"}
    C -->|Có| R["MERGE liên kết HAS_EVENT"]
    C -->|Không| X["Báo xung đột dữ liệu"]
    R --> OK["Hoàn tất; retry cho cùng trạng thái"]
~~~

~~~cypher
// Đã tạo constraint duy nhất cho OrderEvent.eventId.
MERGE (e:OrderEvent {eventId: $eventId})
ON CREATE SET
    e.orderId = $orderId,
    e.kind = $kind,
    e.payloadHash = $payloadHash,
    e.occurredAt = datetime($occurredAt)
WITH e
WHERE e.orderId = $orderId
  AND e.payloadHash = $payloadHash
MERGE (o:Order {orderId: $orderId})
MERGE (o)-[r:HAS_EVENT]->(e)
RETURN e.eventId AS acceptedEventId;
~~~

`payloadHash` là mã băm ổn định tính trên nội dung nghiệp vụ đã chuẩn hóa, **không** gồm các trường như thời gian consumer nhận bản tin. Nếu truy vấn không trả hàng vì cùng `eventId` nhưng khác đơn hàng/nội dung, ứng dụng phải coi đó là **xung đột**, không im lặng xác nhận thành công. Khi có khả năng ghi đồng thời tạo liên kết `HAS_EVENT`, có thể áp dụng thêm khóa duy nhất cho relationship như phần 4 (chẳng hạn `r.eventId`); cần cấu hình constraint và gán khóa đó nhất quán trong câu `MERGE`.

Thay vì mỗi lần nhận message lại chạy `SET o.deliveredCount = o.deliveredCount + 1`, có thể tính từ các sự kiện duy nhất:

~~~cypher
MATCH (o:Order {orderId: $orderId})-[:HAS_EVENT]->(e:OrderEvent)
WHERE e.kind = 'DELIVERED'
RETURN count(DISTINCT e) AS deliveredEvents;
~~~

Nếu bắt buộc duy trì bộ đếm vật lý để truy vấn nhanh, cần một quy trình **đánh dấu event đã áp dụng và cập nhật bộ đếm trong cùng transaction**, chỉ cộng khi thực sự xử lý một event mới. Đếm trực tiếp từ tập sự kiện thường dễ kiểm chứng và sửa lỗi hơn.

## 6. Chống bản cập nhật cũ ghi đè bản mới

Lũy đẳng với **cùng thông điệp** chưa đủ nếu hai thông điệp khác nhau đến sai thứ tự. Ví dụ bản `version=7` đến trước bản `version=6`; nếu ứng dụng ghi “last write wins” không kiểm soát, dữ liệu có thể lùi về version 6.

Nếu hệ thống nguồn cung cấp `sourceVersion` tăng đơn điệu theo từng khách hàng, chỉ áp dụng thông điệp mới hơn:

~~~cypher
MERGE (c:Customer {customerId: $customerId})
ON CREATE SET c.sourceVersion = -1
WITH c
WHERE coalesce(c.sourceVersion, -1) < $sourceVersion
SET
    c.displayName = $displayName,
    c.sourceVersion = $sourceVersion
RETURN c.customerId AS appliedCustomerId;
~~~

- Lần đầu với version 7: dữ liệu được áp dụng.
- Phát lại version 7: không cập nhật thêm và không có hàng trả về.
- Bản cũ version 6: không ghi đè.
- Bản mới version 8: cập nhật đúng trạng thái.

Quy ước ở đây là `sourceVersion` là số nguyên không âm. Khi câu truy vấn không trả hàng, ứng dụng có thể đọc lại version hiện tại để phân biệt “bản cũ/lặp” và “thông tin sai”. Hai bản tin có cùng version nhưng nội dung khác nhau phải được phát hiện là xung đột theo hợp đồng dữ liệu.

**Giới hạn concurrency:** kiểm tra version và ghi dữ liệu cần nằm trong transaction có chính sách xử lý ghi đồng thời. Với yêu cầu thứ tự rất nghiêm ngặt, hãy tuần tự hóa cập nhật theo business key, dùng optimistic locking hoặc chiến lược khóa phù hợp và retry toàn transaction khi phát sinh xung đột. Không giả định một điều kiện `WHERE` đơn lẻ sẽ xử lý mọi cuộc đua giữa các transaction.

## 7. Import theo lô và gọi từ Java

Khi đồng bộ nhiều ID, `UNWIND` kết hợp `DISTINCT` giúp bỏ trùng đầu vào **trước khi** thao tác lên từng node:

~~~cypher
UNWIND $customerIds AS customerId
WITH DISTINCT customerId
WHERE customerId IS NOT NULL
  AND trim(customerId) <> ''
MERGE (c:Customer {customerId: customerId})
RETURN count(c) AS processedCustomers;
~~~

Ở đây danh sách chỉ có ID. Khi import các bản ghi có cùng ID nhưng **khác dữ liệu**, `DISTINCT` trên cả hàng không giải quyết xung đột: cần quyết định quy tắc chọn bản ghi theo version/timestamp đáng tin cậy ở tầng nhập dữ liệu. Với dữ liệu lớn, chia lô phù hợp bộ nhớ và transaction; bảo đảm mỗi lô có thể được chạy lại an toàn.

Ví dụ ứng dụng Java dùng **Neo4j Java Driver** và truy vấn có tham số:

~~~java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

class CustomerSync {
    static String upsert(
            Driver driver, String customerId, String displayName) {
        var params = Map.of(
                "customerId", customerId,
                "displayName", displayName);

        try (Session session =
                     driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> tx.run(
                    """
                    MERGE (c:Customer {customerId: $customerId})
                    SET c.displayName = $displayName
                    RETURN c.customerId AS id
                    """,
                    params).single().get("id").asString());
        }
    }

    public static void main(String[] args) {
        try (Driver driver = GraphDatabase.driver(
                "bolt://localhost:7687",
                AuthTokens.basic("neo4j", "password-from-config"))) {
            upsert(driver, "C-101", "Nguyễn Lan");
            upsert(driver, "C-101", "Nguyễn Lan"); // Cùng một node.
        }
    }
}
~~~

Trong hệ thống thật, lấy URI và thông tin xác thực từ cấu hình an toàn; ví dụ trên chỉ minh họa luồng gọi. `executeWrite` thực thi managed write transaction và có thể thử lại khi gặp lỗi **có thể retry**. Vì vậy callback chỉ nên làm công việc giao dịch trên graph: không gửi email, trừ tiền, sinh ID ngẫu nhiên mới hay tạo hiệu ứng ngoài Neo4j ở bên trong callback. Không phải mọi lỗi (đặc biệt xung đột unique constraint) đều tự động được driver retry; ứng dụng cần phân loại lỗi và thiết kế cách đọc lại/xử lý trùng có kiểm soát.

Với **Spring Data Neo4j**, cần khai báo định danh thực thể ổn định (ví dụ field `@Id` ánh xạ `customerId`), cân nhắc `@Version` để phát hiện cập nhật cạnh tranh, và vẫn cần constraint ở database. Cấu hình repository hoặc phương thức `save` riêng lẻ không thay thế quy tắc deduplicate sự kiện hay ràng buộc danh tính.

## 8. Cách kiểm tra giải pháp

Sau khi tạo constraint và chạy câu upsert nhiều lần, kiểm tra số node theo cùng ID:

~~~cypher
MATCH (c:Customer {customerId: 'C-101'})
RETURN count(c) AS customerCount;
// Kỳ vọng: 1
~~~

Kiểm tra dữ liệu cũ có ID trùng (trước khi tạo constraint) và liên kết trùng:

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IS NOT NULL
WITH c.customerId AS id, count(*) AS copies
WHERE copies > 1
RETURN id, copies;

MATCH (a:User)-[r:FOLLOWS]->(b:User)
WITH a.userId AS fromId, b.userId AS toId, count(r) AS copies
WHERE copies > 1
RETURN fromId, toId, copies;
~~~

Một bộ kiểm thử có ý nghĩa nên bao gồm các trường hợp sau:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Gửi cùng lệnh tạo/cập nhật node 2–10 lần | Vẫn chỉ có một node theo business key và thuộc tính đúng |
| Phát lại cùng `eventId` và payload | Chỉ có một sự kiện logic, không cộng dồn ngoài ý muốn |
| Cùng `eventId` nhưng payload khác | Phát hiện và báo xung đột |
| Gửi version 8 rồi version 7 | Trạng thái cuối giữ version 8 |
| Gửi hai yêu cầu tạo cùng ID đồng thời | Không commit hai node trùng; xử lý lỗi cạnh tranh phù hợp |
| Thiếu ID hoặc khóa `null` | Từ chối đầu vào rõ ràng, không ghi node sai |
| Retry sau timeout ở giữa job import | Chạy lại lô vẫn cho đồ thị logic đúng |

## 9. Checklist áp dụng trong dự án

1. Chọn business key không đổi; chuẩn hóa khóa và bảo đảm không thiếu thành phần định danh.
2. Đặt uniqueness constraint cho node hoặc relationship cần bảo vệ, trước khi chạy ghi đồng thời.
3. `MERGE` theo **khóa**, `SET` thuộc tính thay đổi; tránh `CREATE` vô điều kiện trong luồng retry.
4. Với số đếm, danh sách hoặc sự kiện, dùng ID thao tác/sự kiện ổn định; không cộng dồn khi phát lại.
5. Với nhiều bản cập nhật khác nhau, dùng version hoặc quy tắc xử lý thứ tự và phát hiện payload mâu thuẫn.
6. Đưa các ghi liên quan vào cùng transaction; kiểm thử retry, concurrency và dữ liệu trùng thực tế.

**Kết luận:** Một luồng cập nhật Neo4j an toàn cần kết hợp **định danh ổn định + constraint ở database + truy vấn Cypher đúng ngữ nghĩa + xử lý retry/transaction**. `MERGE` là công cụ trung tâm để upsert, nhưng tính lũy đẳng của toàn quy trình phụ thuộc cả cách thiết kế sự kiện, thứ tự cập nhật và quy tắc xử lý ghi đồng thời.
