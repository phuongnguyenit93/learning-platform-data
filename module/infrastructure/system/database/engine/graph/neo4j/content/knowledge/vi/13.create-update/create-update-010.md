# Kiểm tra thống kê cập nhật và xác minh trạng thái sau khi ghi trong Neo4j

## 1. Vì sao một truy vấn ghi chạy thành công vẫn cần được kiểm tra?

Neo4j tổ chức dữ liệu dưới dạng **property graph**: node mang label và property; relationship có hướng, loại quan hệ và property riêng. Các lệnh Cypher như `CREATE`, `MERGE`, `SET`, `REMOVE` và `DELETE` thay đổi đồ thị. Tuy nhiên, ứng dụng không nên kết luận “dữ liệu đã đúng” chỉ vì câu lệnh không báo lỗi.

Ví dụ, hệ thống quản lý người dùng gửi yêu cầu chuyển tài khoản `u-101` sang trạng thái `ACTIVE`. Có thể xảy ra các tình huống khác nhau:

- Truy vấn `MATCH` không tìm thấy node nên không cập nhật gì, dù thực thi thành công.
- `MERGE` tìm thấy node cũ nên không tạo node mới; đây có thể là kết quả đúng của thao tác idempotent.
- Lệnh `SET` được thực hiện, nhưng giá trị cuối cùng không đúng quy tắc nghiệp vụ.
- Ứng dụng đã nhận thống kê của truy vấn nhưng giao dịch chứa nó sau đó bị rollback.
- Giao dịch đã commit, song một lần đọc ở session khác trong cluster chưa được phối hợp bookmark, hoặc dữ liệu tiếp tục bị giao dịch khác cập nhật.

Vì vậy, cần kiểm tra **ba lớp thông tin khác nhau**:

| Lớp kiểm tra | Công cụ | Trả lời câu hỏi | Không tự bảo đảm |
| --- | --- | --- | --- |
| Kết quả thực thi | Kết quả truy vấn, exception, trạng thái transaction | Cypher có thực thi xong và giao dịch có commit thành công không? | Đúng node, đúng quan hệ, đúng giá trị nghiệp vụ |
| Thống kê cập nhật | Query counters trong Neo4j Browser hoặc `ResultSummary.counters()` của Java Driver | Câu truy vấn đã thực hiện bao nhiêu thao tác tạo, xóa, gán thuộc tính, thêm nhãn...? | Số bản ghi nghiệp vụ duy nhất, giá trị thực tế sau ghi, tính bền vững nếu chưa commit |
| Trạng thái sau ghi | Truy vấn `MATCH ... RETURN` sau khi commit, trong ngữ cảnh đọc nhất quán | Node, relationship, property và phiên bản dữ liệu hiện có đúng kỳ vọng không? | Dữ liệu sẽ không thay đổi trong tương lai bởi giao dịch khác |

**Nguyên tắc:** counters cho biết *hoạt động ghi của một truy vấn*; truy vấn đọc lại cho biết *trạng thái đồ thị được quan sát*; transaction quyết định *thao tác có được commit hay không*.

## 2. Đọc đúng các chỉ số cập nhật

Trong Neo4j Browser, sau khi chạy câu lệnh ghi, có thể xem thông báo số node/relationship được tạo, xóa, số property được đặt hoặc label được thêm. Khi dùng driver, các số liệu này có trong **query execution summary**.

| Counter trong Java Driver | Ý nghĩa | Điều dễ nhầm |
| --- | --- | --- |
| `nodesCreated()` | Số node được tạo | Không phải số node mà `MATCH` tìm thấy |
| `nodesDeleted()` | Số node bị xóa | `DETACH DELETE` có thể đồng thời xóa relationship |
| `relationshipsCreated()` | Số relationship được tạo | Không phải số đường đi mà truy vấn trả về |
| `relationshipsDeleted()` | Số relationship bị xóa | Không nhất thiết bằng số node bị xóa |
| `propertiesSet()` | Số thao tác đặt property trên node/relationship theo thống kê của Neo4j | Không phải số node được sửa hay số giá trị *thực sự khác trước* |
| `labelsAdded()` / `labelsRemoved()` | Số label thêm/bỏ | Khác với tạo/xóa node |
| `indexesAdded()` / `indexesRemoved()` | Thay đổi index của schema | Không phản ánh cập nhật dữ liệu người dùng |
| `constraintsAdded()` / `constraintsRemoved()` | Thay đổi constraint của schema | Không phản ánh số bản ghi chịu ràng buộc |
| `containsUpdates()` | Có ít nhất một cập nhật dữ liệu/schema được ghi nhận cho truy vấn hay không | Không chứng minh transaction ngoài cùng đã commit |
| `containsSystemUpdates()` / `systemUpdates()` | Thống kê thay đổi trên cơ sở dữ liệu `system` | Không thay thế counters của graph dữ liệu |

Lưu ý cách diễn giải:

1. `CREATE (u:AppUser {id: 'u-101', name: 'Mai'})` tạo **một node**, nhưng đồng thời có thao tác thêm label và gán nhiều property.
2. `MERGE` khớp node sẵn có thường có `nodesCreated() == 0`. Nếu có `ON MATCH SET`, truy vấn vẫn có thể báo cập nhật property.
3. `SET u.status = 'ACTIVE'` có thể được tính là thao tác đặt property ngay cả khi giá trị đã là `ACTIVE`. Không dùng một counter để suy ra có “thay đổi giá trị nghiệp vụ” hay không.
4. `RETURN count(u)` đếm các dòng/node được truyền qua truy vấn theo ngữ nghĩa Cypher; nó **không phải** counter cập nhật. Nếu một node xuất hiện qua nhiều dòng do mở rộng quan hệ, cần cân nhắc `DISTINCT`.
5. Các counters là **thống kê của truy vấn**, không phải bảng lịch sử thay đổi lưu trong graph và không phải cơ chế audit dài hạn.

## 3. Quy trình kiểm tra bằng Cypher

Ví dụ xuyên suốt dùng label `AppUser` và khóa nghiệp vụ `id`. Chạy các câu lệnh theo thứ tự trên **database thử nghiệm** và quan sát cả phần kết quả lẫn thông báo thống kê. Với môi trường đã có constraint tương đương, không cần tạo thêm constraint.

### Bước 1: Bảo đảm định danh duy nhất

```cypher
CREATE CONSTRAINT app_user_id_unique IF NOT EXISTS
FOR (u:AppUser)
REQUIRE u.id IS UNIQUE;
```

Constraint duy nhất giúp `MERGE (u:AppUser {id: ...})` không tạo hai node có cùng `id` khi các giao dịch cạnh tranh. DDL có counters riêng: không gộp thống kê tạo constraint với thống kê ghi dữ liệu nghiệp vụ.

### Bước 2: Tạo nếu chưa có và xem counters

```cypher
MERGE (u:AppUser {id: 'u-101'})
ON CREATE SET
  u.name = 'Mai',
  u.status = 'PENDING',
  u.version = 0
RETURN u.id AS id, u.name AS name,
       u.status AS status, u.version AS version;
```

**Lần chạy đầu tiên** trên tập dữ liệu chưa có `u-101`: dự kiến `nodesCreated = 1`, thêm label và các property tương ứng. **Lần chạy thứ hai**: `MERGE` khớp node hiện có, không thực hiện nhánh `ON CREATE`, nên dự kiến không có cập nhật. Đây là tính idempotent chủ ý, không phải lỗi.

Nếu `RETURN` hiển thị một dòng nhưng `nodesCreated = 0`, điều đó chỉ nói rằng node **không được tạo trong lần chạy ấy**. Nó không bác bỏ khả năng node đã tồn tại.

### Bước 3: Cập nhật có điều kiện để tránh ghi thừa

```cypher
MATCH (u:AppUser {id: 'u-101'})
WHERE u.status IS NULL OR u.status <> 'ACTIVE'
SET u.status = 'ACTIVE',
    u.version = coalesce(u.version, 0) + 1
RETURN u.id AS id, u.status AS status,
       u.version AS version;
```

Nếu `u-101` đang `PENDING`, truy vấn cập nhật `status` và `version`; kết quả `RETURN` cho biết giá trị *sau `SET` trong giao dịch hiện tại*. Chạy lại khi đã `ACTIVE`, điều kiện `WHERE` loại node ra, truy vấn không có dòng kết quả và counters cập nhật bằng 0.

Nếu không có node `u-101`, truy vấn cũng không tạo thay đổi. Vì vậy **counters bằng 0 có nhiều nguyên nhân**: chưa tìm thấy node, dữ liệu đã đúng, hoặc điều kiện cập nhật không được thỏa. Phải kiểm tra sự tồn tại và giá trị hiện tại để phân biệt.

### Bước 4: Đọc lại sau khi transaction commit

```cypher
OPTIONAL MATCH (u:AppUser {id: 'u-101'})
RETURN count(u) AS matchingNodes,
       head(collect(u.status)) AS actualStatus,
       head(collect(u.version)) AS actualVersion;
```

Với khóa duy nhất và kết quả mong đợi ở bước 3:

- `matchingNodes = 1`: có đúng một tài khoản theo khóa nghiệp vụ.
- `actualStatus = 'ACTIVE'`: trạng thái hiện tại đúng yêu cầu.
- `actualVersion = 1`: trên dữ liệu ví dụ mới khởi tạo, phiên bản đã tăng một lần.

Nếu `matchingNodes = 0`, không có node; nếu `actualStatus` sai, cập nhật chưa đạt yêu cầu. Giá trị `version` chỉ là cơ chế nghiệp vụ **do ứng dụng tự duy trì**, Neo4j không tự tăng nó cho mọi thao tác.

**Vị trí đọc lại rất quan trọng:** đọc trong cùng transaction có thể nhìn thấy các thay đổi chưa commit. Muốn kiểm tra kết quả đã lưu, cần để transaction ghi commit thành công rồi thực hiện lần đọc sau đó. Một session dùng Java Driver tự duy trì quan hệ nhân quả giữa các transaction kế tiếp; nếu đọc ở session khác hoặc cluster nhiều máy, cần chuyển bookmark hoặc dùng bookmark manager thích hợp.

### Bước 5: Xác minh cả relationship và thao tác xóa

Tạo thêm đối tượng đích và quan hệ:

```cypher
MERGE (u:AppUser {id: 'u-102'})
ON CREATE SET u.name = 'Nam';

MATCH (a:AppUser {id: 'u-101'})
MATCH (b:AppUser {id: 'u-102'})
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.createdAt = datetime()
RETURN type(r) AS relationshipType;
```

Trong lần đầu tạo quan hệ, quan sát `relationshipsCreated`. Kiểm tra cấu trúc thực:

```cypher
MATCH (a:AppUser {id: 'u-101'})-[r:FOLLOWS]->
      (b:AppUser {id: 'u-102'})
RETURN a.id AS follower, type(r) AS relation,
       b.id AS followed, r.createdAt AS createdAt;
```

Kết quả đọc lại cần có cạnh **đúng chiều, đúng loại và đúng hai đầu**, không chỉ `relationshipsCreated = 1`.

Khi xóa một node có relationship, có thể dùng:

```cypher
MATCH (u:AppUser {id: 'u-102'})
DETACH DELETE u;
```

Sau thao tác này, thống kê có thể bao gồm **cả** `nodesDeleted` và `relationshipsDeleted`. Đọc lại để xác nhận không còn node và quan hệ liên quan:

```cypher
OPTIONAL MATCH (u:AppUser {id: 'u-102'})
RETURN count(u) AS remainingUsers;

MATCH (a:AppUser {id: 'u-101'})-[r:FOLLOWS]->()
RETURN count(r) AS remainingOutgoingFollows;
```

Ở dữ liệu ví dụ chỉ có quan hệ vừa tạo, cả hai kết quả dự kiến bằng 0. Trong cơ sở dữ liệu thật, số `remainingOutgoingFollows` có thể lớn hơn 0 vì `u-101` còn theo dõi các tài khoản khác; khi ấy phải kiểm tra **đúng relationship đích** thay vì kỳ vọng xóa mọi quan hệ `FOLLOWS`.

## 4. Lấy thống kê và xác minh qua Java Driver

Với ứng dụng Java, API quan trọng là `ResultSummary.counters()` trả về `SummaryCounters`. Đoạn ví dụ sau dùng Java Driver với transaction được quản lý; thay URI, mật khẩu và database bằng cấu hình của môi trường chạy:

```java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.summary.ResultSummary;
import org.neo4j.driver.summary.SummaryCounters;

public class VerifyNeo4jWrite {
    public static void main(String[] args) {
        try (
            Driver driver = GraphDatabase.driver(
                "neo4j://localhost:7687",
                AuthTokens.basic("neo4j", "change-me")
            );
            Session session = driver.session(SessionConfig.forDatabase("neo4j"))
        ) {
            Map<String, Object> params = Map.of(
                "id", "u-101",
                "name", "Mai",
                "status", "ACTIVE"
            );

            // executeWrite chỉ trả về sau khi giao dịch ghi commit thành công.
            ResultSummary summary = session.executeWrite(tx ->
                tx.run("""
                    MERGE (u:AppUser {id: $id})
                    ON CREATE SET u.name = $name, u.status = $status
                    ON MATCH SET u.status = $status
                    """, params).consume()
            );

            SummaryCounters counters = summary.counters();
            System.out.printf(
                "created=%d, propertiesSet=%d, updated=%s%n",
                counters.nodesCreated(),
                counters.propertiesSet(),
                counters.containsUpdates()
            );

            // Đọc bằng transaction mới, trong cùng session.
            String actualStatus = session.executeRead(tx ->
                tx.run("""
                    MATCH (u:AppUser {id: $id})
                    RETURN u.status AS status
                    """, Map.of("id", "u-101"))
                  .single()
                  .get("status")
                  .asString()
            );

            if (!"ACTIVE".equals(actualStatus)) {
                throw new IllegalStateException(
                    "Trạng thái sau ghi không khớp: " + actualStatus
                );
            }

            System.out.println("Đã xác minh: status = " + actualStatus);
        }
    }
}
```

Các chi tiết cần hiểu rõ:

- `consume()` trả về `ResultSummary` **và tiêu thụ phần còn lại của result stream**. Nếu cần cả record từ `RETURN` lẫn thống kê, phải đọc các record cần thiết **trước khi** gọi `consume()`, hoặc dùng API `Driver.executableQuery(...).execute()` rồi lấy `records()` và `summary()` từ kết quả.
- `executeWrite(...)` thực hiện transaction được quản lý, có thể thử lại callback khi gặp lỗi tạm thời. Vì vậy logic bên trong callback nên **idempotent**, không gửi thông báo ra hệ thống ngoài, cộng biến toàn cục hoặc tạo hiệu ứng không thể hoàn tác ở mỗi lần thử.
- `containsUpdates() == false` không có nghĩa là thất bại: một `MERGE` khớp dữ liệu hiện có hoặc một truy vấn lọc hết đối tượng có thể không tạo cập nhật nào.
- `single()` sẽ báo lỗi nếu không có record hoặc có nhiều hơn một record; đây là kiểm tra hữu ích khi khóa định danh phải xác định chính xác một node. Constraint duy nhất vẫn nên được thiết lập trước.
- Cùng một session, các transaction nối tiếp được Neo4j Driver điều phối bookmark để lần đọc sau thấy kết quả đã commit của lần ghi trước, kể cả khi hệ thống chạy cluster.

Trong Spring Data Neo4j, `repository.save(...)` cho phép thao tác qua entity và `@Transactional` quản lý ranh giới transaction ở service. Tuy nhiên, object trả về từ `save` **không thay thế bước xác minh cơ sở dữ liệu sau commit** và không trực tiếp cung cấp bộ counters như `ResultSummary`. Khi bài toán cần đếm chính xác các thao tác Cypher, có thể dùng Java Driver để lấy summary; khi cần xác minh nghiệp vụ, đọc lại theo khóa duy nhất qua repository hoặc `Neo4jClient` trong một transaction đọc **sau khi transaction ghi hoàn tất**. Chú ý giới hạn của cơ chế transaction proxy trong Spring: một phương thức tự gọi phương thức `@Transactional` khác trong cùng object thường không tạo ranh giới transaction mới.

## 5. Khi cần kiểm tra số bản ghi đã cập nhật

Query counters không có chỉ số chung “số đối tượng nghiệp vụ thực sự được cập nhật” cho mọi câu Cypher. Trong trường hợp cần biết bao nhiêu node thỏa điều kiện ghi, hãy biểu diễn điều đó trực tiếp trong truy vấn.

Ví dụ cập nhật trạng thái cho các đơn hàng quá hạn:

```cypher
MATCH (o:Order)
WHERE o.status = 'PENDING'
  AND o.expiredAt < datetime()
WITH DISTINCT o
SET o.status = 'EXPIRED'
RETURN count(o) AS affectedOrders;
```

`affectedOrders` là số node `Order` duy nhất đi qua bước cập nhật trong **truy vấn này**. `propertiesSet` lại biểu thị số thao tác gán property, nên không được đánh đồng hai số. Kết quả `affectedOrders = 0` có thể là bình thường nếu không còn đơn cần hết hạn.

Khi cập nhật một bản ghi dựa trên phiên bản hiện tại (optimistic locking), dùng điều kiện `version`:

```cypher
MATCH (o:Order {id: $orderId, version: $expectedVersion})
SET o.status = $newStatus,
    o.version = o.version + 1
RETURN count(o) AS updatedOrders;
```

Nếu khóa `Order.id` là duy nhất và `updatedOrders = 1`, truy vấn đã khớp đúng phiên bản kỳ vọng và thực hiện nhánh ghi. Nếu bằng 0, **không kết luận ngay rằng đơn không tồn tại**: có thể phiên bản đã thay đổi do một request khác. Ứng dụng nên đọc lại `id` và `version` (hoặc trả về lỗi xung đột), rồi chỉ thông báo thành công sau khi transaction commit.

Với truy vấn có nhiều phép `MATCH` hoặc mở rộng path, số dòng có thể bị nhân lên. Dùng `WITH DISTINCT target` trước `SET` khi nghiệp vụ muốn mỗi node đích được xử lý một lần. Khi kiểm tra quan hệ, xác minh cả hướng và type của relationship.

## 6. Ranh giới transaction và những tình huống dễ kết luận sai

| Hiện tượng quan sát | Cách giải thích đúng | Cách xác minh tiếp |
| --- | --- | --- |
| Query chạy xong, counters đều bằng 0 | Không có thao tác cập nhật được ghi nhận; có thể do `MATCH` rỗng hoặc không cần sửa | Đọc theo khóa và so sánh trạng thái mong muốn |
| `nodesCreated = 0` sau `MERGE` | Không có node mới được tạo trong lần chạy này | Kiểm tra node đã tồn tại và thuộc tính đúng chưa |
| `propertiesSet > 0` | Có thao tác đặt property | Đọc lại giá trị; không suy ra số node hoặc sự khác biệt so với giá trị cũ |
| `RETURN count(*)` trả về giá trị `1` | Có một dòng đầu vào được hàm `count(*)` đếm (tùy truy vấn) | Xác định `count` đang đếm gì; xem counters và truy vấn kiểm tra |
| Có counters nhưng transaction sau đó rollback | Số liệu mô tả truy vấn đã chạy, không chứng minh dữ liệu được commit | Kiểm tra commit thành công rồi đọc lại |
| Đọc trong cùng transaction thấy dữ liệu mới | Transaction nhìn thấy chính thay đổi của nó | Đọc lại trong transaction mới sau commit |
| Đọc từ session khác ở cluster thấy dữ liệu cũ | Có thể chưa bảo đảm quan hệ nhân quả giữa các transaction/session | Truyền bookmark hoặc dùng bookmark manager; xác nhận đúng database |
| Một lệnh `DETACH DELETE` xóa nhiều relationship | Xóa node kèm toàn bộ relationship gắn với node | So sánh `nodesDeleted`, `relationshipsDeleted` và đồ thị đích |
| Chạy `CALL { ... } IN TRANSACTIONS` theo lô rồi gặp lỗi | Các lô đã commit trước đó có thể vẫn tồn tại | Kiểm tra từng batch và tổng kết dữ liệu thực tế; không mặc định toàn bộ import là một transaction |

**Commit và kiểm tra lại có giới hạn thời gian:** xác minh thành công tại thời điểm đọc không khóa trạng thái đó vĩnh viễn. Nếu nhiều request có thể cùng sửa một node, cần constraint, transaction phù hợp và kiểm tra phiên bản/điều kiện cạnh tranh. Nếu cần truy vết *ai* sửa *khi nào*, cần thiết kế audit log hoặc sự kiện nghiệp vụ; query counters chỉ mô tả một lần thực thi.

### `EXPLAIN` và `PROFILE` không thay thế kiểm tra dữ liệu

- `EXPLAIN <query>` xây dựng kế hoạch thực thi **mà không chạy câu lệnh**; không dùng kết quả đó để khẳng định đã có ghi.
- `PROFILE <query>` **chạy thật câu lệnh** để thu thập số rows, DbHits và thông tin kế hoạch. Với truy vấn ghi, `PROFILE` cũng có thể thay đổi dữ liệu; chỉ sử dụng khi thực sự muốn thực thi.
- Rows, DbHits và thời gian trong kế hoạch chủ yếu phục vụ **tối ưu truy vấn**, không thay thế kiểm tra counters hoặc giá trị sau commit. Khi truy vấn cập nhật chậm, kiểm tra index/constraint trên khóa tìm kiếm và lượng node/relationship bị chạm tới.

## 7. Bài thực hành và tiêu chí hoàn thành

Trên database thử nghiệm, thực hiện lại các thao tác sau:

1. Tạo constraint duy nhất cho `AppUser.id`, sau đó chạy `MERGE` tài khoản `u-101` hai lần. Ghi nhận sự khác biệt của `nodesCreated` giữa hai lần.
2. Chạy lệnh chuyển trạng thái sang `ACTIVE` và tăng `version` hai lần. Giải thích vì sao lần thứ hai không cập nhật gì.
3. Đọc lại node, kiểm tra `id`, `status` và `version`; thử đổi `id` sang mã không tồn tại để quan sát kết quả rỗng.
4. Tạo quan hệ `FOLLOWS`, kiểm tra thống kê và truy vấn lại đúng hướng quan hệ. Xóa node đích bằng `DETACH DELETE` rồi xác minh node đích và cạnh liên quan đã biến mất.
5. Trong ứng dụng Java, thu thập `SummaryCounters` và đọc lại dữ liệu **sau khi** `executeWrite` hoàn tất; thử một request hợp lệ và một request không tìm được đối tượng.

Một thao tác ghi được xem là đã **được xác minh theo yêu cầu nghiệp vụ** khi đáp ứng đồng thời:

- Transaction ghi hoàn tất và commit thành công; exception không bị bỏ qua.
- Truy vấn chọn đúng database, label/type và khóa nhận diện; các ràng buộc định danh cần thiết đã được tạo.
- Counters hợp lý với dạng thao tác (tạo, sửa, xóa, idempotent), không bị dùng thay cho giá trị nghiệp vụ.
- Truy vấn đọc sau commit xác nhận đúng số đối tượng, property, hướng relationship và phiên bản kỳ vọng.
- Có cách xử lý rõ ràng cho trường hợp không tìm thấy đối tượng, dữ liệu đã đúng sẵn, xung đột cập nhật hoặc đọc thiếu quan hệ nhân quả.

## Tài liệu tham khảo chính thức

- [Neo4j Java Driver — Explore the query execution summary](https://neo4j.com/docs/java-manual/current/result-summary/): lấy `ResultSummary`, đọc counters và hiểu `consume()`.
- [Neo4j Java Driver — Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/): transaction được quản lý, commit/rollback và callback có thể được thử lại.
- [Neo4j Java Driver — Coordinate parallel transactions](https://neo4j.com/docs/java-manual/current/bookmarks/): session, bookmark và quan hệ nhân quả giữa các lần ghi/đọc.
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/): ngữ nghĩa `MERGE`, `ON CREATE`, `ON MATCH` và constraint duy nhất.
- [Neo4j Query API — Retrieve query counters](https://neo4j.com/docs/query-api/current/query-counters/): tên và ý nghĩa các trường thống kê trong response của Query API.
