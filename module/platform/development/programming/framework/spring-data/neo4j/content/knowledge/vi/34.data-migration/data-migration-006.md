# Dùng UNWIND với dữ liệu theo lô và ID ổn định

Khi nhập hàng nghìn hoặc hàng triệu bản ghi vào Neo4j, gửi một truy vấn cho từng bản ghi thường tạo nhiều round trip và làm tăng chi phí transaction. Cypher có `UNWIND` để biến một list tham số thành các hàng đầu vào; ứng dụng có thể gửi một batch gồm nhiều map trong một lần gọi, sau đó dùng `MERGE` và `SET` để tạo hoặc cập nhật node, relationship.

Để migration có thể chạy lại sau timeout, crash hoặc retry, mỗi bản ghi cần một định danh ổn định lấy từ nguồn dữ liệu. Dùng định danh đó làm khóa của `MERGE`, đặt uniqueness constraint tương ứng và thiết kế thao tác ghi theo hướng idempotent. Batch chỉ giúp giảm chi phí xử lý; ID ổn định và transaction boundary mới giúp quá trình migration có thể tiếp tục an toàn.

## 1. UNWIND biến list thành các hàng

`UNWIND` nhận một list và tạo một hàng cho mỗi phần tử. Mỗi phần tử được gán vào biến trong mệnh đề `AS`:

```cypher
UNWIND ["Lan", "Minh", "Hoa"] AS name
RETURN name;
```

Kết quả có ba hàng, mỗi hàng chứa một giá trị `name`. Với dữ liệu migration, list thường được truyền dưới dạng tham số thay vì viết trực tiếp vào Cypher:

```cypher
UNWIND $rows AS row
RETURN row.externalId AS externalId,
       row.name AS name;
```

`$rows` là tham số chứa danh sách map. `row` đại diện cho một phần tử, có thể đọc các key như `row.externalId`, `row.name` hoặc `row.email`.

`UNWIND` rất hữu ích khi ứng dụng đã đọc dữ liệu từ CSV, API hoặc hệ thống cũ và muốn gửi nhiều bản ghi trong một request Neo4j. Cần chia dữ liệu thành các batch vừa phải thay vì gửi một list không giới hạn.

## 2. Dùng ID ổn định làm khóa MERGE

Giả sử dữ liệu nguồn có bảng khách hàng với mã `legacyCustomerId`. Mã này ổn định qua các lần import và duy nhất trong hệ thống nguồn. Ta có thể ánh xạ nó thành `externalId` trên node `Customer`.

Trước khi import, tạo uniqueness constraint:

```cypher
CREATE CONSTRAINT customer_external_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.externalId IS UNIQUE;
```

Constraint bảo vệ invariant dữ liệu ngay cả khi hai transaction đồng thời ghi cùng một external ID. Kiểm tra dữ liệu hiện có trước khi tạo constraint nếu graph đã chứa Customer cũ.

Truy vấn upsert theo ID ổn định:

```cypher
UNWIND $rows AS row
MERGE (c:Customer {externalId: row.externalId})
SET c.name = row.name,
    c.email = row.email,
    c.sourceSystem = row.sourceSystem,
    c.updatedAt = datetime();
```

`MERGE` tìm node có cùng `externalId`; nếu chưa có thì tạo node mới. `SET` cập nhật các thuộc tính còn lại. Khi cùng batch được chạy lại, truy vấn tìm lại node cũ thay vì tạo một node mới.

Chỉ đưa khóa ổn định vào pattern `MERGE`. Không đưa các thuộc tính có thể thay đổi như tên, email hoặc địa chỉ vào pattern, vì khi chúng đổi, Neo4j có thể không tìm thấy node cũ và tạo node mới.

### Không dùng ID ngẫu nhiên mới ở mỗi lần retry

Ví dụ không an toàn:

```java
Map<String, Object> row = Map.of(
        "externalId", UUID.randomUUID().toString(),
        "name", source.name());
```

Nếu tạo UUID mới mỗi lần retry, cùng một bản ghi nguồn sẽ có ID khác nhau và `MERGE` không nhận ra nó là bản ghi cũ. Hãy dùng khóa nguồn ổn định hoặc tạo một UUID đúng một lần rồi lưu lại để tái sử dụng ở mọi lần thử.

Không dùng `id(node)` hoặc `elementId(node)` làm khóa migration lâu dài. Internal ID do Neo4j quản lý, có ý nghĩa trong phạm vi database và vòng đời node; chúng không thay thế khóa nghiệp vụ ổn định từ hệ thống nguồn.

## 3. Chuẩn bị và kiểm tra dữ liệu trước khi gửi batch

Một batch nên có cấu trúc nhất quán. Ví dụ Java record cho dòng khách hàng nguồn:

```java
public record CustomerRow(
        String externalId,
        String name,
        String email,
        String sourceSystem) {
}
```

Trước khi chuyển record thành map để bind, kiểm tra:

- `externalId` không null, không rỗng và đúng định dạng.
- Các ID không bị trùng trong cùng batch.
- `sourceSystem` được lấy từ danh sách nguồn đã cấu hình.
- Các trường bắt buộc đã có giá trị.
- Các trường tùy chọn có quy tắc rõ ràng khi null hoặc rỗng.
- Dữ liệu được chuẩn hóa nhất quán, ví dụ trim mã nguồn hoặc chuẩn hóa chữ hoa/thường theo quy tắc nghiệp vụ.

Nếu một batch chứa hai hàng cùng `externalId` nhưng khác `name`, kết quả cuối có thể phụ thuộc thứ tự xử lý. Hãy loại trùng hoặc áp dụng quy tắc chọn bản ghi thắng trước khi gửi dữ liệu. Không dùng thứ tự đầu vào làm quy tắc ngầm cho dữ liệu xung đột.

## 4. Bind danh sách map bằng Neo4jClient

`Neo4jClient` cho phép bind một collection map vào named parameter `$rows`:

```java
import java.util.Collection;

import org.neo4j.driver.summary.ResultSummary;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerBatchWriter {

    private static final String UPSERT_CUSTOMERS = """
            UNWIND $rows AS row
            MERGE (c:Customer {externalId: row.externalId})
            SET c.name = row.name,
                c.email = row.email,
                c.sourceSystem = row.sourceSystem,
                c.updatedAt = datetime()
            """;

    private final Neo4jClient neo4jClient;

    public CustomerBatchWriter(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public ResultSummary writeBatch(Collection<Map<String, Object>> rows) {
        if (rows.isEmpty()) {
            throw new IllegalArgumentException("Batch must not be empty");
        }

        return neo4jClient.query(UPSERT_CUSTOMERS)
                .bind(rows).to("rows")
                .run();
    }
}
```

Mỗi lần gọi `writeBatch` gửi cả batch qua một truy vấn. `ResultSummary` cung cấp counter như số node tạo mới và số property được đặt. Đây là số liệu hữu ích để ghi log migration và phát hiện batch không tạo ra thay đổi như dự kiến.

Ví dụ giả định các map có key `externalId`, `name`, `email` và `sourceSystem` tương ứng với Cypher. Nên tập trung việc chuyển DTO thành map tại một mapper riêng và kiểm tra schema đầu vào trước khi gọi repository.

### Lưu ý về giá trị null

Trong Cypher, gán `null` cho property sẽ xóa property đó. Vì vậy, câu lệnh `SET c.email = row.email` có nghĩa là nếu `row.email` là null thì property `email` trên node sẽ bị gỡ bỏ. Điều này phù hợp nếu null trong nguồn có nghĩa là xóa giá trị; nếu null có nghĩa là “không cập nhật field này”, cần thiết kế query khác để giữ property cũ.

Không dùng `SET c += row` một cách máy móc nếu map có key không mong muốn hoặc null mang ý nghĩa không rõ ràng. Hãy whitelist các field được phép ghi và quy định rõ cách xử lý null cho từng field.

## 5. Chia dữ liệu thành batch trong Java

Batch size là số hàng được gửi trong một transaction hoặc một lần xử lý. Batch quá nhỏ làm tăng số round trip; batch quá lớn làm tăng bộ nhớ, thời gian giữ lock và lượng công việc phải rollback khi lỗi.

Có thể chia list thành các phần bằng nhau:

```java
import java.util.List;

public final class Batches {

    private Batches() {
    }

    public static <T> List<List<T>> split(List<T> items, int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be positive");
        }

        List<List<T>> batches = new java.util.ArrayList<>();
        for (int start = 0; start < items.size(); start += batchSize) {
            int end = Math.min(start + batchSize, items.size());
            batches.add(items.subList(start, end));
        }
        return batches;
    }
}
```

Ví dụ chọn 500 hàng mỗi batch:

```java
for (List<CustomerRow> batch : Batches.split(rows, 500)) {
    writer.writeBatch(toParameterMaps(batch));
}
```

`500` chỉ là giá trị khởi đầu để thử nghiệm, không phải giới hạn tối ưu cho mọi graph. Hãy đo thời gian mỗi batch, heap, transaction duration, lock contention và kích thước payload trên dữ liệu gần production. Có thể bắt đầu với batch nhỏ rồi tăng dần cho đến khi throughput ổn định.

Nếu nguồn dữ liệu lớn, không cần tải toàn bộ file vào `List` trước khi chia. Hãy đọc theo stream hoặc page từ nguồn và chỉ giữ một batch trong bộ nhớ tại một thời điểm.

## 6. Đặt transaction boundary theo từng batch

Với migration dài, thường nên commit từng batch để có thể tiếp tục từ batch đã hoàn tất nếu batch sau gặp lỗi. Mỗi batch là một transaction độc lập; batch thành công được giữ lại, batch lỗi được retry hoặc xử lý riêng.

Trong Spring, có thể đặt method ghi một batch ở một bean riêng và đánh dấu `@Transactional`:

```java
import java.util.Collection;
import java.util.Map;

import org.neo4j.driver.summary.ResultSummary;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransactionalCustomerBatchWriter {

    private final CustomerBatchWriter writer;

    public TransactionalCustomerBatchWriter(CustomerBatchWriter writer) {
        this.writer = writer;
    }

    @Transactional
    public ResultSummary writeOneBatch(Collection<Map<String, Object>> rows) {
        return writer.writeBatch(rows);
    }
}
```

Orchestrator gọi `writeOneBatch` qua bean Spring cho từng batch:

```java
for (List<CustomerRow> batch : batches) {
    transactionalWriter.writeOneBatch(toParameterMaps(batch));
    checkpointStore.markCompleted(batch.get(batch.size() - 1).externalId());
}
```

Không đặt `@Transactional` trên toàn bộ orchestrator nếu mục tiêu là mỗi batch commit riêng; khi đó mọi lời gọi repository có thể tham gia cùng transaction dài của orchestrator. Cũng tránh self-invocation: gọi method transactional qua một bean khác để lời gọi đi qua Spring proxy.

Nếu checkpoint nằm trong cùng Neo4j database và cần tính nguyên tử với dữ liệu batch, hãy cập nhật checkpoint trong cùng transaction với batch. Nếu checkpoint ở hệ thống ngoài, có thể có cửa sổ crash sau khi batch commit nhưng trước khi checkpoint được ghi; khi chạy lại, batch đó sẽ được gửi lại. `MERGE` theo stable ID và phép `SET` xác định giúp lần chạy lại không tạo node trùng.

## 7. Dùng CALL { ... } IN TRANSACTIONS cho import lớn

Cypher hỗ trợ `CALL { ... } IN TRANSACTIONS OF n ROWS` để xử lý các hàng đầu vào theo các transaction con. Cách này hữu ích khi dữ liệu được đưa vào bởi một truy vấn lớn hoặc `LOAD CSV`:

```cypher
UNWIND $rows AS row
CALL {
    WITH row
    MERGE (c:Customer {externalId: row.externalId})
    SET c.name = row.name,
        c.email = row.email,
        c.sourceSystem = row.sourceSystem
} IN TRANSACTIONS OF 500 ROWS;
```

Neo4j gom các hàng đầu vào thành nhóm 500 và chạy phần subquery trong các transaction con. Mỗi nhóm commit độc lập; nếu một nhóm lỗi, các nhóm đã commit trước đó không tự rollback theo nhóm lỗi.

**Quan trọng:** `CALL { ... } IN TRANSACTIONS` chỉ chạy trong implicit transaction (auto-commit). Không chạy câu lệnh này bên trong explicit transaction như `Driver.executeWrite(...)` hoặc một phương thức SDN `@Transactional` đang mở transaction. Khi gọi từ Neo4j Browser, cần dùng chế độ auto-commit phù hợp; khi gọi qua driver, dùng `session.run(...)` trực tiếp thay vì transaction callback tường minh. Kiểm tra execution mode của client đang sử dụng trước khi áp dụng.

Chọn một trong hai cách chia batch:

- **Chia batch ở ứng dụng:** ứng dụng gửi mỗi list qua một transaction SDN riêng. Cách này dễ tích hợp với repository, checkpoint và xử lý lỗi theo từng batch.
- **Chia transaction trong Cypher:** một truy vấn đầu vào lớn dùng `CALL { ... } IN TRANSACTIONS`. Cách này giảm orchestration ở ứng dụng nhưng yêu cầu implicit transaction và cần hiểu rõ hành vi commit từng nhóm.

Không lồng cả hai cách mà không có lý do; transaction boundary phải rõ ràng để tránh tưởng rằng toàn bộ migration là nguyên tử trong khi một phần đã commit.

## 8. Dùng UNWIND để tạo relationship theo ID ổn định

Migration thường cần tạo node trước rồi nối chúng bằng relationship. Ví dụ mỗi hàng chứa `customerExternalId` và `orderExternalId`. Cả hai node được tìm theo khóa ổn định, sau đó relationship được `MERGE`:

```cypher
UNWIND $rows AS row
MATCH (c:Customer {externalId: row.customerExternalId})
MATCH (o:Order {externalId: row.orderExternalId})
MERGE (c)-[r:PLACED {sourceRelationId: row.relationId}]->(o)
SET r.createdAt = datetime(row.createdAt);
```

`sourceRelationId` là ID ổn định của liên kết trong nguồn dữ liệu. Nếu không có ID quan hệ riêng, có thể dùng cặp khóa nguồn cùng loại relationship làm identity khi nghiệp vụ bảo đảm mỗi cặp chỉ có một liên kết. Nếu cùng hai node có thể có nhiều relationship cùng loại nhưng khác ý nghĩa, cần một khóa quan hệ rõ ràng.

`MATCH` không tìm thấy một trong hai node thì hàng đó không tạo relationship. Vì vậy, migration nên có bước kiểm tra các endpoint bị thiếu và ghi lại số hàng không được nối; không âm thầm coi batch đã hoàn tất nếu số lượng relationship tạo ra thấp hơn dự kiến.

## 9. UNWIND không bảo đảm thứ tự hàng

Neo4j không bảo đảm các hàng do `UNWIND` tạo ra được xử lý theo thứ tự của list đầu vào. Nếu kết quả cần thứ tự xác định, hãy dùng `ORDER BY`:

```cypher
UNWIND $rows AS row
WITH row
ORDER BY row.externalId
MERGE (c:Customer {externalId: row.externalId})
SET c.name = row.name;
```

Sắp xếp theo stable key còn hữu ích khi nhiều batch hoặc transaction cạnh tranh cập nhật cùng tập node. Tuy nhiên, `ORDER BY` chỉ kiểm soát thứ tự hàng trong luồng truy vấn đó; nó không thay thế thiết kế transaction và không bảo đảm mọi luồng ghi khác trong hệ thống cũng dùng cùng thứ tự.

Nếu một batch có nhiều hàng cùng external ID, hãy loại trùng hoặc gom chúng theo quy tắc nghiệp vụ trước khi chạy. Không dựa vào thứ tự `UNWIND` để quyết định hàng nào ghi đè hàng nào.

## 10. Thiết kế migration có thể tiếp tục sau sự cố

Một migration có thể dừng do network timeout, process crash, lỗi dữ liệu hoặc Neo4j tạm thời quá tải. Hãy lưu tiến độ và thiết kế mỗi batch có thể chạy lại.

Các nguyên tắc:

1. Mỗi hàng có stable ID được giữ nguyên giữa mọi lần chạy.
2. `MERGE` chỉ dựa trên khóa ổn định, được bảo vệ bằng uniqueness constraint.
3. Các phép `SET` gán giá trị xác định từ nguồn thay vì cộng dồn ngoài ý muốn.
4. Mỗi batch có transaction boundary rõ ràng.
5. Checkpoint chỉ được ghi sau khi batch commit; nếu có thể, ghi checkpoint cùng transaction với dữ liệu.
6. Lưu số hàng đọc, số hàng hợp lệ, số hàng bị bỏ qua, số node/relationship tạo mới và số hàng cập nhật.
7. Ghi lại ID hoặc nguyên nhân của hàng lỗi để có thể sửa dữ liệu và chạy lại.

### Phân biệt thao tác idempotent và không idempotent

Idempotent:

```cypher
MERGE (c:Customer {externalId: row.externalId})
SET c.name = row.name,
    c.email = row.email;
```

Chạy lại với cùng row sẽ đưa node về cùng trạng thái mong muốn.

Không idempotent:

```cypher
MATCH (c:Customer {externalId: row.externalId})
SET c.importCount = coalesce(c.importCount, 0) + 1;
```

Mỗi lần retry lại tăng `importCount`; kết quả thay đổi theo số lần chạy. Nếu cần đếm số lần nguồn phát event, dùng event ID riêng và deduplicate trước khi tăng bộ đếm.

## 11. Retry transaction và xử lý lỗi theo batch

Với transient error như mất kết nối tạm thời hoặc deadlock, có thể retry batch. Nếu dùng Neo4j Java Driver managed transaction, callback của `executeWrite` có thể được gọi lại bởi Driver. Vì vậy, callback chỉ nên chứa thao tác database và phải an toàn khi chạy lại:

```java
try (var session = driver.session()) {
    ResultSummary summary = session.executeWrite(tx ->
            tx.run(UPSERT_CUSTOMERS, Map.of("rows", rows))
                    .consume());

    log.info("Created nodes: {}", summary.counters().nodesCreated());
}
```

Không gửi email, publish message hoặc cập nhật hệ thống ngoài trong callback transaction có thể retry. Nếu cần side effect, ghi outbox trong cùng transaction rồi xử lý sau commit.

Phân loại lỗi:

- **Transient:** deadlock, lỗi tạm thời về kết nối hoặc leader/server có thể phục hồi; retry với giới hạn và backoff.
- **Permanent:** ID thiếu, dữ liệu sai định dạng, constraint violation do dữ liệu trùng; ghi nhận hàng lỗi và sửa nguồn trước khi retry.
- **Unknown outcome:** client timeout sau khi server có thể đã commit; chạy lại batch an toàn nhờ stable ID và idempotent upsert.

Không retry vô hạn. Ghi nhận số lần thử, thời gian, batch ID và nguyên nhân lỗi. Khi vượt ngưỡng, chuyển batch sang trạng thái cần can thiệp để tránh làm nghẽn toàn bộ migration.

## 12. Đo hiệu năng và chọn batch size

Không có một batch size tối ưu cho mọi graph. Cần đo trên dữ liệu và hạ tầng gần production. Các yếu tố ảnh hưởng:

- Kích thước mỗi map và tổng payload gửi qua Bolt.
- Số property cập nhật và số relationship tạo ra trên mỗi hàng.
- Index/constraint được dùng để tìm node khi `MERGE`.
- Mức độ nhiều batch cùng cập nhật một node hoặc vùng graph.
- Thời gian transaction, lock contention và lượng heap phía ứng dụng.
- Chi phí retry khi một batch lỗi.

Quy trình thực nghiệm:

1. Bắt đầu với batch nhỏ, ví dụ 100 hoặc 250 hàng.
2. Đo throughput, latency và bộ nhớ.
3. Tăng dần batch size khi transaction ổn định.
4. Theo dõi lock contention và thời gian rollback khi cố ý tạo lỗi trong môi trường test.
5. Chọn kích thước cân bằng throughput, khả năng retry và thời gian phục hồi.

Trước khi tối ưu batch size, bảo đảm `MERGE` có thể tìm node bằng index hoặc uniqueness constraint phù hợp. Nếu không, mỗi batch có thể quét nhiều node và throughput sẽ giảm khi graph lớn dần.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `CREATE` khi migration có thể chạy lại | Tạo node trùng sau retry | Dùng `MERGE` theo stable ID và uniqueness constraint |
| Dùng UUID mới ở mỗi lần chạy | Cùng bản ghi nguồn trở thành nhiều node | Giữ external ID hoặc UUID đã lưu từ lần đầu |
| Đưa thuộc tính mutable vào pattern `MERGE` | Thay đổi thuộc tính có thể tạo node mới | Chỉ dùng khóa identity trong `MERGE`, cập nhật field bằng `SET` |
| Không tạo uniqueness constraint | Các transaction cạnh tranh có thể tạo dữ liệu trùng | Tạo constraint trước migration và xử lý duplicate hiện có |
| Gửi toàn bộ dữ liệu trong một batch | Payload lớn, transaction dài và khó retry | Chia batch, commit từng phần |
| Batch quá nhỏ | Nhiều round trip và overhead transaction | Đo và tăng batch size phù hợp |
| Nghĩ `UNWIND` giữ thứ tự list | Kết quả hoặc thứ tự ghi không xác định | Dùng `ORDER BY` nếu thứ tự quan trọng |
| Không quy định null semantics | Property cũ có thể bị xóa ngoài ý muốn | Chuẩn hóa dữ liệu và thiết kế quy tắc null rõ ràng |
| Ghi checkpoint trước khi commit | Có thể bỏ qua batch chưa lưu thành công | Ghi checkpoint sau commit hoặc cùng transaction |
| Dùng `CALL { ... } IN TRANSACTIONS` trong `@Transactional` | Lỗi vì subquery transaction cần implicit transaction | Chạy bằng auto-commit hoặc chia batch ở ứng dụng |
| Retry cả lỗi dữ liệu cố định | Tốn tài nguyên mà không thể thành công | Phân loại transient và permanent error |
| Đặt side effect bên ngoài trong retry callback | Email/message có thể bị gửi nhiều lần | Dùng transactional outbox và consumer idempotent |

## 14. Bài tập thực hành

Giả sử file nguồn có các dòng khách hàng:

```json
[
  {"externalId":"LEG-001","name":"Lan","email":"lan@example.test","sourceSystem":"CRM"},
  {"externalId":"LEG-002","name":"Minh","email":"minh@example.test","sourceSystem":"CRM"},
  {"externalId":"LEG-003","name":"Hoa","email":null,"sourceSystem":"CRM"}
]
```

Thực hiện các yêu cầu:

1. Tạo uniqueness constraint cho `Customer.externalId`.
2. Viết truy vấn `UNWIND $rows` để `MERGE` Customer theo external ID và cập nhật tên, email.
3. Bind một collection map bằng `Neo4jClient`.
4. Chia 1.000 hàng thành các batch 100 hoặc 250 hàng và ghi từng batch.
5. Chạy lại cùng batch hai lần; xác nhận số node không tăng sau lần chạy thứ hai.
6. Thử một hàng thiếu external ID và xác nhận validation từ chối trước khi ghi.
7. Thử email null và xác định property có được xóa hay cần giữ giá trị cũ theo chính sách migration.
8. Tạo relationship từ Customer đến Order bằng ID ổn định của hai endpoint và relation ID.
9. Mô phỏng crash sau khi batch commit nhưng trước checkpoint; chạy lại và xác nhận dữ liệu không trùng.
10. So sánh chia batch ở Java với `CALL { ... } IN TRANSACTIONS` chạy trong implicit transaction.

Sau bài tập, hãy giải thích được vai trò của `UNWIND`, `MERGE`, stable ID, uniqueness constraint, transaction boundary, checkpoint và vì sao một batch cần có khả năng chạy lại an toàn.

## Kết luận

`UNWIND` biến list tham số thành các hàng để Neo4j xử lý nhiều bản ghi trong một truy vấn. Dùng `MERGE` theo stable ID và uniqueness constraint để tránh tạo node trùng khi retry; cập nhật thuộc tính bằng `SET` xác định để thao tác có thể chạy lại. Chia dữ liệu thành batch có transaction boundary và checkpoint rõ ràng, kiểm soát null, loại trùng đầu vào và không dựa vào thứ tự mặc định của `UNWIND`. Với import lớn, chọn chia batch ở ứng dụng hoặc `CALL { ... } IN TRANSACTIONS` theo đúng execution mode. Đo batch size trên dữ liệu thực tế và thiết kế retry chỉ cho lỗi có thể phục hồi.

## Tài liệu tham khảo

- [Neo4j Cypher Manual – UNWIND](https://neo4j.com/docs/cypher-manual/current/clauses/unwind/)
- [Neo4j Cypher Manual – MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual – CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Neo4j Java Driver Manual – Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Spring Data Neo4j – Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
