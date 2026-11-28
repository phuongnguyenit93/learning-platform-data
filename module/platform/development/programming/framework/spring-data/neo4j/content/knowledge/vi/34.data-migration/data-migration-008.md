# Kiểm tra tính tương thích khi ứng dụng cũ và mới cùng hoạt động

Bài học này thuộc chương **Migration dữ liệu** của module **SPRING_DATA_NEO4J**. Khi triển khai phiên bản mới theo kiểu rolling deployment, blue-green hoặc canary, các instance ứng dụng cũ và mới có thể cùng kết nối vào một Neo4j database trong một khoảng thời gian. Cả hai phiên bản có thể đọc và ghi cùng graph, dù chúng hiểu cấu trúc node, property và relationship theo những cách khác nhau.

Vì vậy, migration dữ liệu cần giữ cho graph tương thích với mọi phiên bản ứng dụng còn đang hoạt động. Một thay đổi có vẻ đơn giản như đổi tên property, relationship type hoặc label có thể làm phiên bản cũ không đọc được dữ liệu mới, hoặc khiến phiên bản mới bỏ sót dữ liệu do phiên bản cũ vừa ghi.

Chiến lược phù hợp là **mở rộng cấu trúc trước, chuyển dữ liệu trong khi vẫn tương thích, rồi mới loại bỏ cấu trúc cũ**. Mẫu này thường được gọi là expand–migrate–contract hoặc parallel change. Nó chia một thay đổi phá vỡ tương thích thành nhiều bước nhỏ có thể triển khai và kiểm chứng độc lập.

## 1. Vì sao ứng dụng cũ và mới cần tương thích?

Giả sử ứng dụng v1 lưu tên người dùng trong property `fullName`:

```cypher
(:Person {id: 'p-42', fullName: 'Nguyen An'})
```

Phiên bản v2 muốn đổi property thành `displayName`:

```cypher
(:Person {id: 'p-42', displayName: 'Nguyen An'})
```

Nếu xóa `fullName` ngay khi triển khai v2, các instance v1 vẫn đang chạy sẽ không đọc được tên. Nếu chỉ ghi `displayName`, v1 có thể tạo hoặc cập nhật `fullName` mà v2 không nhìn thấy. Nếu backfill xong trước khi các instance v1 dừng, một lần ghi từ v1 có thể làm hai property lệch nhau.

Trong thời gian rollout, graph có thể được truy cập bởi:

- Instance v1 chỉ biết `fullName`.
- Instance v2 biết cả `fullName` và `displayName`.
- Job migration đang đọc và cập nhật các node cũ.
- Consumer hoặc batch job khác vẫn dùng query Cypher cũ.

Không chỉ web application mới cần tính tương thích. Scheduled job, worker, script import, report, integration service và truy vấn vận hành cũng có thể là writer hoặc reader của graph. Trước khi contract schema cũ, phải xác định toàn bộ client còn sử dụng nó.

## 2. Phân biệt migration ứng dụng với nâng cấp Neo4j DBMS

Bài học này tập trung vào **tính tương thích của graph data model khi nhiều phiên bản ứng dụng cùng hoạt động**. Đây là thay đổi ở label, property, relationship, constraint, index và cách mapping entity của ứng dụng.

Nâng cấp Neo4j DBMS là một quy trình riêng. Việc chuyển giữa các major version của Neo4j có thể yêu cầu rà soát cấu hình, application code và plugin. Hướng dẫn chính thức của Neo4j khuyến nghị thử nghiệm quá trình upgrade/migration và khả năng tương thích trong môi trường test trước khi thay đổi production. Không nên coi một migration property trong graph là thay thế cho quy trình nâng cấp server.

## 3. Những chiều tương thích cần đánh giá

Một thay đổi có thể tương thích ở một chiều nhưng phá vỡ chiều khác. Trước khi viết migration, đánh giá ít nhất các khía cạnh sau:

| Chiều tương thích | Câu hỏi cần trả lời |
|---|---|
| Reader compatibility | Ứng dụng cũ có đọc được graph sau khi mở rộng không? Ứng dụng mới có đọc được node chưa migration không? |
| Writer compatibility | Phiên bản cũ ghi dữ liệu có làm phiên bản mới bỏ sót hoặc đọc sai không? |
| Mapping compatibility | Entity SDN cũ và mới có thể lưu cùng graph mà không xóa hoặc ghi đè dữ liệu ngoài ý muốn không? |
| Query compatibility | Derived query, `@Query`, Cypher-DSL, report và batch job có còn chạy không? |
| Constraint/index compatibility | Dữ liệu hiện có có đáp ứng điều kiện trước khi thêm constraint mới không? Index đã sẵn sàng phục vụ query chưa? |
| API compatibility | DTO, JSON field và message gửi sang hệ thống khác có còn được client cũ hiểu không? |
| Rollback compatibility | Có thể quay lại phiên bản trước trong thời gian rollback mà không mất dữ liệu mới không? |

Một thay đổi chỉ được xem là an toàn khi các reader và writer đang hoạt động đều có hành vi xác định với graph ở từng giai đoạn.

## 4. Mẫu expand–migrate–contract

Quy trình tổng quát gồm ba pha:

1. **Expand:** thêm cấu trúc mới theo cách không làm hỏng ứng dụng cũ. Property hoặc relationship cũ vẫn tồn tại; trường mới có thể chưa được điền.
2. **Migrate:** cập nhật dữ liệu cũ theo lô, đồng thời giữ reader/writer tương thích. Kiểm tra số lượng bản ghi, dữ liệu thiếu và sai khác giữa cấu trúc cũ/mới.
3. **Contract:** sau khi tất cả ứng dụng và job cũ đã ngừng sử dụng cấu trúc cũ, chuyển sang cấu trúc mới hoàn toàn rồi mới xóa property, label hoặc relationship cũ.

```text
Graph ban đầu
  fullName
      |
      v
EXPAND
  fullName + displayName
  v1 vẫn đọc/ghi fullName
  v2 đọc fullName, ghi cả hai
      |
      v
MIGRATE
  backfill displayName từ fullName
  kiểm tra dữ liệu và đối soát sai khác
      |
      v
SWITCH READS
  v3 đọc displayName, fallback fullName
  v3 vẫn ghi cả hai trong thời gian rollback
      |
      v
CONTRACT
  v4 chỉ đọc/ghi displayName
  sau thời gian rollback mới xóa fullName
```

Pha contract là pha phá vỡ tương thích. Chỉ thực hiện khi không còn instance, worker hoặc consumer cần cấu trúc cũ và đã hết thời gian rollback cần giữ khả năng tương thích.

## 5. Ví dụ đổi tên property trong Spring Data Neo4j

Giả sử entity v1 ánh xạ property `fullName`:

```java
package com.example.graph.domain;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String fullName;

    // constructors, getters and setters
}
```

Phiên bản mới muốn dùng `displayName`. Không nên đổi mapping và xóa field cũ ngay trong một lần release. Thay vào đó, bản phát hành tương thích đầu tiên ánh xạ cả hai property:

```java
package com.example.graph.domain;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;

@Node("Person")
public class Person {

    @Id
    private String id;

    @Property("fullName")
    private String legacyFullName;

    private String displayName;

    public String getNameDuringCompatibility() {
        return legacyFullName;
    }

    public String getLegacyFullName() {
        return legacyFullName;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void rename(String name) {
        this.legacyFullName = name;
        this.displayName = name;
    }

    // constructors, getters and setters
}
```

Trong release tương thích này, `fullName` vẫn là nguồn đọc chính thức. Mọi thao tác đổi tên phải ghi cả hai property trong cùng một lần lưu. Điều đó giữ cho v1 tiếp tục đọc được `fullName`, đồng thời bảo đảm các ghi mới từ v2 tạo ra `displayName`.

Không chỉ sửa entity. Hãy rà soát tất cả writer như service, import job, custom repository fragment và câu Cypher trực tiếp để bảo đảm chúng tuân thủ quy tắc dual-write trong giai đoạn này.

## 6. Thứ tự rollout cho property rename

Một trình tự an toàn cho ví dụ `fullName` sang `displayName`:

| Giai đoạn | Phiên bản đang chạy | Reader | Writer |
|---|---|---|---|
| Ban đầu | v1 | v1 đọc `fullName` | v1 ghi `fullName` |
| Compatibility release | v1 + v2 | v1 đọc `fullName`; v2 vẫn đọc `fullName` | v1 ghi `fullName`; v2 ghi cả `fullName` và `displayName` |
| Backfill | v2 | v2 đọc `fullName` | v2 ghi cả hai; migration đồng bộ `displayName` từ `fullName` |
| Read switch | v2 + v3 | v2 đọc `fullName`; v3 đọc `displayName`, fallback `fullName` | Cả hai tiếp tục ghi cả hai |
| New-only release | v4 | v4 đọc `displayName` | v4 ghi `displayName`; chỉ thực hiện sau khi v1/v2 và rollback về các phiên bản chỉ đọc `fullName` đã hết hạn |

Lý do v2 vẫn đọc `fullName` trong lúc v1 còn chạy: v1 có thể cập nhật `fullName` sau khi v2 đã ghi `displayName`. Nếu v2 ưu tiên `displayName` quá sớm, giá trị mới có thể cũ hơn `fullName`. Giữ `fullName` làm nguồn đọc chính trong giai đoạn mixed-writer giúp tránh đọc một bản sao chưa được đồng bộ.

Chỉ chạy backfill cuối cùng sau khi tất cả v1 instance, worker và job cũ đã được dừng hoặc nâng cấp. Sau đó v3 có thể chuyển nguồn đọc sang `displayName` và vẫn fallback về `fullName` để xử lý các node chưa hoàn chỉnh. v3 vẫn dual-write nên rollback từ v3 về v2 còn đọc được `fullName`; trước khi v4 ngừng ghi property cũ, phải kết thúc rollback window của v1/v2. v3 có thể tiếp tục là phiên bản rollback được hỗ trợ vì nó đọc `displayName` làm nguồn chính.

## 7. Dual-write phải có tính nguyên tử và nhất quán

Trong compatibility release, hai property nên được cập nhật trong cùng một lần ghi entity hoặc cùng một transaction. Giả sử service đã inject `PersonRepository` và đang xử lý entity `Person`:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;

public void changeDisplayName(Person person, String newName) {
    person.rename(newName);
    personRepository.save(person);
}
```

Nếu ghi hai property bằng hai request độc lập, một request có thể thành công còn request kia thất bại. Khi đó graph rơi vào trạng thái lệch mà reader không thể dự đoán. Dùng một lần `save` hoặc một transaction bao trùm cả hai thay đổi.

Với custom Cypher, có thể đặt cả hai property trong cùng câu lệnh:

```cypher
MATCH (p:Person {id: $id})
SET p.fullName = $displayName,
    p.displayName = $displayName
RETURN p
```

Giữ parameter binding cho giá trị đầu vào. Không ghép chuỗi từ dữ liệu người dùng vào Cypher.

Nếu nhiều writer cùng cập nhật một entity, cần xác định nguồn dữ liệu có thẩm quyền và quy tắc xử lý xung đột. Dual-write không tự giải quyết lost update; nó chỉ bảo đảm một writer ghi cả hai trường theo cùng một giá trị trong cùng thao tác.

## 8. Backfill idempotent theo batch

Backfill là công việc chuyển dữ liệu đã tồn tại sang cấu trúc mới. Một migration tốt có thể chạy lại mà không tạo dữ liệu trùng hoặc ghi đè giá trị mới đã hợp lệ.

Sau khi mọi writer v1 đã ngừng hoạt động, có thể chạy từng batch để đồng bộ property:

```cypher
MATCH (p:Person)
WHERE p.fullName IS NOT NULL
  AND (p.displayName IS NULL OR p.displayName <> p.fullName)
WITH p
ORDER BY p.id
LIMIT $batchSize
SET p.displayName = p.fullName
RETURN count(p) AS migrated
```

Migration runner lặp câu lệnh với `batchSize` phù hợp cho tới khi `migrated` bằng 0. Mỗi batch là một đơn vị commit riêng. Cách lọc theo điều kiện sai khác giúp chạy lại an toàn: node đã được đồng bộ không còn nằm trong tập dữ liệu cần sửa.

Nếu dùng `Neo4jClient` để thực thi batch, bind `batchSize` bằng parameter và đọc giá trị `migrated` từ kết quả. Không chạy một transaction khổng lồ cho hàng triệu node nếu có thể chia thành batch nhỏ, vì transaction quá lớn làm tăng bộ nhớ, thời gian lock và rủi ro rollback dài.

Với graph lớn, nên dùng cursor theo một ID ổn định hoặc checkpoint có lưu tiến độ. Migration runner cần có cơ chế tránh hai instance cùng chạy một job nếu thao tác không được thiết kế để chạy song song. Nếu job bị dừng giữa chừng, nó phải tiếp tục từ checkpoint hoặc chạy lại mà không gây hỏng dữ liệu.

## 9. Backfill trong khi vẫn có writer cũ

Không phải lúc nào cũng có thể dừng toàn bộ writer cũ trước khi bắt đầu chuyển dữ liệu. Khi đó, cần tách backfill ban đầu và lần đối soát cuối:

- Trong giai đoạn v1 và v2 cùng chạy, v2 vẫn đọc `fullName`; v2 ghi cả hai property. Backfill có thể chuẩn bị các node cũ, nhưng giá trị `displayName` chưa được coi là nguồn chính thức.
- Sau khi v1 đã rời khỏi hệ thống, chạy lại một lượt đối soát toàn bộ để đồng bộ các cập nhật cuối cùng mà v1 đã ghi vào `fullName`.
- Chỉ chuyển reader sang `displayName` khi lượt đối soát cuối không còn dữ liệu sai khác.

Nếu có writer ngoài ứng dụng không thể nâng cấp ngay, phải giữ quy tắc tương thích cho writer đó hoặc thay đổi luồng ingest trước khi chuyển reader. Một backfill hoàn tất tại một thời điểm không bảo đảm dữ liệu tiếp tục đúng nếu còn writer chỉ cập nhật property cũ.

## 10. Đọc tương thích trong giai đoạn chuyển đổi

Sau khi backfill và dừng v1, phiên bản v3 có thể ưu tiên property mới và fallback về property cũ:

```java
import com.example.graph.domain.Person;

public String getEffectiveDisplayName(Person person) {
    if (person.getDisplayName() != null) {
        return person.getDisplayName();
    }
    return person.getLegacyFullName();
}
```

Fallback hữu ích cho dữ liệu chưa được migration hoặc record được tạo bởi một luồng ingest chưa cập nhật. Tuy nhiên, fallback không nên trở thành giải pháp vĩnh viễn để che giấu migration thiếu hoàn chỉnh. Theo dõi số lượng record còn phải fallback và đặt điều kiện rõ ràng trước khi loại bỏ property cũ.

Nếu một property mới có thể mang giá trị rỗng hợp lệ, phân biệt rõ `null`, chuỗi rỗng và giá trị không hợp lệ theo quy tắc nghiệp vụ. Không dùng toán tử fallback tùy tiện khiến dữ liệu hợp lệ bị thay bằng giá trị legacy.

## 11. Thay đổi label của node

Label cũng là một phần của graph schema. Giả sử v1 truy vấn `:Customer` còn v2 muốn dùng `:Client`. Nếu đổi label ngay lập tức, query của v1 sẽ không còn tìm thấy node.

Một cách chuyển đổi tương thích là giữ cả hai label trong thời gian chuyển tiếp:

```cypher
MATCH (c:Customer)
SET c:Client
RETURN count(c) AS updated
```

Trong giai đoạn này:

- v1 tiếp tục match `:Customer`.
- v2 có thể match `:Client`.
- Writer mới cần gắn cả hai label cho node mới trong thời gian v1 còn hoạt động.
- Sau khi mọi reader/writer cũ đã dừng và dữ liệu được kiểm tra, contract mới có thể loại bỏ label `Customer`.

Với Spring Data Neo4j, mapping `@Node` quyết định label mà repository sử dụng. Nếu entity mới chỉ khai báo label mới, cần xác nhận mọi node đã được gắn label đó trước khi chuyển toàn bộ query. Các custom Cypher, relationship traversal, index và constraint gắn với label cũ cũng cần được rà soát.

## 12. Thay đổi relationship type hoặc cấu trúc quan hệ

Đổi relationship type, ví dụ `MEMBER_OF` thành `PARTICIPATES_IN`, cũng có thể làm reader cũ mất cạnh. Trong giai đoạn chuyển tiếp, giữ relationship cũ và tạo relationship mới với một khóa migration ổn định để tránh nhân đôi khi chạy lại.

Ví dụ giả định mỗi relationship cũ có property `migrationKey` duy nhất và không null:

```cypher
MATCH (p:Person)-[old:MEMBER_OF]->(g:Group)
WHERE old.migrationKey IS NOT NULL
MERGE (p)-[current:PARTICIPATES_IN {migrationKey: old.migrationKey}]->(g)
SET current += properties(old)
RETURN count(current) AS processed
```

`MERGE` với endpoint và khóa ổn định giúp migration có thể chạy lại mà không tạo thêm relationship tương ứng. Nếu relationship cũ chưa có khóa ổn định, phải xác định danh tính cạnh theo nghiệp vụ trước khi migration; không mặc định rằng một cặp node chỉ có một relationship giữa chúng.

Reader v2 có thể đọc cả hai relationship type trong query Cypher:

```cypher
MATCH (p:Person)-[r:MEMBER_OF|PARTICIPATES_IN]->(g:Group)
RETURN DISTINCT p, g
```

Nếu SDN entity đang dùng `@Relationship(type = "MEMBER_OF")`, annotation đó chỉ mô tả mapping theo type đã khai báo. Muốn đọc cả hai type trong giai đoạn chuyển tiếp, dùng custom Cypher hoặc thiết kế mapping tạm thời rõ ràng. Tránh để cùng một cạnh được ánh xạ hai lần vào collection mà không có quy tắc deduplicate.

Chỉ xóa relationship cũ sau khi mọi query, service, job và phiên bản ứng dụng đã chuyển sang type mới. Kiểm tra cả relationship properties, direction và cardinality; migration đúng type nhưng mất property hoặc đảo chiều cạnh vẫn là migration sai.

## 13. Thêm property bắt buộc và constraint mới

Một thay đổi additive như thêm property `tenantId` có thể vẫn phá vỡ ứng dụng nếu code mới giả định property luôn tồn tại trong khi graph cũ chưa được backfill.

Trình tự nên là:

1. Thêm property vào mapping mới dưới dạng nullable hoặc có fallback.
2. Triển khai writer mới để mọi node tạo mới có `tenantId`.
3. Backfill `tenantId` cho node cũ bằng quy tắc nghiệp vụ xác định.
4. Kiểm tra không còn node thiếu hoặc có giá trị sai.
5. Thêm constraint hoặc chuyển code sang yêu cầu giá trị mới.

Ví dụ kiểm tra dữ liệu thiếu:

```cypher
MATCH (p:Person)
WHERE p.tenantId IS NULL
RETURN count(p) AS missingTenantId
```

Nếu `externalId` cần duy nhất trong phạm vi label `Person`, chỉ tạo uniqueness constraint sau khi đã kiểm tra và xử lý dữ liệu trùng. `tenantId` trong ví dụ vẫn là property bắt buộc, nhưng không nhất thiết duy nhất:

```cypher
CREATE CONSTRAINT person_external_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.externalId IS UNIQUE
```

`IF NOT EXISTS` giúp tránh lỗi khi constraint tương ứng đã tồn tại, nhưng không làm dữ liệu vi phạm trở nên hợp lệ. Neo4j có thể từ chối tạo constraint nếu graph hiện tại chứa giá trị trùng hoặc vi phạm điều kiện của constraint. Vì vậy, hãy chạy truy vấn kiểm tra trước và theo dõi kết quả tạo constraint.

## 14. Index mới phải sẵn sàng trước khi chuyển query

Nếu v2 chuyển truy vấn sang property mới, hãy tạo index tương ứng trong pha expand trước khi bật query mới ở production:

```cypher
CREATE INDEX person_display_name IF NOT EXISTS
FOR (p:Person)
ON (p.displayName)
```

Index có thể cần thời gian để population. Trong khi index còn ở trạng thái `POPULATING`, query chưa thể sử dụng index đó. Kiểm tra trạng thái:

```cypher
SHOW INDEXES
```

Chỉ chuyển traffic sang truy vấn phụ thuộc index sau khi index ở trạng thái `ONLINE`. Nếu tạo uniqueness constraint, Neo4j cũng tạo index backing tương ứng; không cần tạo thêm một range index trùng schema. Kiểm tra `SHOW CONSTRAINTS` và `SHOW INDEXES` để xác nhận trạng thái thực tế.

## 15. Migration phải có thể chạy lại và có thể quan sát

Migration job thường chạy lâu hơn một request thông thường. Thiết kế nó như một công việc vận hành có trạng thái rõ ràng:

- **Idempotent:** chạy lại không tạo relationship trùng, không ghi đè dữ liệu đã đúng và không làm mất cập nhật mới.
- **Batch:** chia thành lô nhỏ, mỗi lô có ranh giới commit và giới hạn thời gian hợp lý.
- **Checkpoint:** lưu tiến độ hoặc dùng điều kiện lọc để xác định record chưa được xử lý.
- **Single owner hoặc coordination:** tránh nhiều runner cùng thực hiện một job nếu không có chiến lược concurrency.
- **Metrics:** ghi số record đã xử lý, còn thiếu, sai khác, lỗi và thời gian mỗi batch.
- **Retry có giới hạn:** retry lỗi tạm thời, nhưng không retry vô hạn lỗi dữ liệu hoặc lỗi constraint.
- **Dry run:** cho phép đếm và xem trước phạm vi thay đổi trước khi ghi production.

Không nên để mọi instance ứng dụng tự chạy cùng migration nặng khi khởi động. Một deployment job hoặc migration runner được điều phối riêng giúp kiểm soát thứ tự, quyền ghi, concurrency và audit log tốt hơn.

## 16. Theo dõi mức độ tương thích trong lúc rollout

Không chuyển sang pha tiếp theo chỉ dựa vào việc deployment báo thành công. Cần theo dõi cả trạng thái ứng dụng lẫn trạng thái dữ liệu.

Với property rename, có thể đo số node còn thiếu hoặc lệch:

```cypher
MATCH (p:Person)
WHERE p.fullName IS NOT NULL
  AND (p.displayName IS NULL OR p.displayName <> p.fullName)
RETURN count(p) AS pendingMigration
```

Đo riêng các trường hợp không có giá trị cũ nhưng đã có giá trị mới, hoặc các node được tạo mới sau khi rollout. Nếu nghiệp vụ cho phép `fullName` null, không tự suy ra giá trị mới; cần quy tắc chuyển đổi rõ ràng.

Các tín hiệu vận hành cần quan sát:

- Số instance theo phiên bản và số request còn đến từ v1.
- Số worker, cron job và consumer vẫn dùng property/relationship cũ.
- Tỷ lệ đọc phải fallback từ property mới sang property cũ.
- Số node còn thiếu property mới hoặc có giá trị khác nhau.
- Lỗi mapping, lỗi constraint và lỗi query sau khi chuyển reader.
- Thời gian query, index state và query plan sau khi đổi property hoặc label.

Chỉ chuyển reader khi dữ liệu đã được đối soát và mọi writer cũ đã dừng. Chỉ contract khi không còn reader cũ và rollback window đã kết thúc.

## 17. Kiểm thử ma trận phiên bản cũ/mới

Trước khi rollout, tạo test matrix mô phỏng những tổ hợp có thể xảy ra trong production:

| Reader | Writer | Graph state | Kết quả cần xác nhận |
|---|---|---|---|
| v1 | v1 | Chỉ có property cũ | Hành vi hiện tại vẫn đúng |
| v1 | v2 | Có cả property cũ và mới | v1 vẫn đọc được dữ liệu do v2 ghi |
| v2 | v1 | v1 chỉ cập nhật property cũ | v2 vẫn đọc giá trị mới nhất theo nguồn canonical cũ |
| v2 | v2 | Dual-write | Hai property được cập nhật cùng giá trị |
| v3 | v2 | Đã backfill | v3 đọc property mới; v2 vẫn đọc property cũ |
| v3 | v3 | Dual-write | Có thể rollback về v2 trong thời gian cho phép |
| v4 | v4 | Chỉ dùng property mới | Không còn phụ thuộc property cũ sau contract |

Các integration test nên lưu dữ liệu bằng entity v1, đọc bằng entity v2; sau đó lưu bằng entity v2 và xác nhận v1 vẫn đọc được property cũ. Kiểm tra cả custom Cypher, derived query và relationship mapping, vì chúng có thể không đi qua cùng một đường code.

Kiểm thử migration job với dữ liệu đã chuyển một phần, chạy lại nhiều lần, dừng giữa batch và chạy tiếp. Xác nhận tổng số node/relationship, property quan trọng và tính duy nhất vẫn đúng. Một test chỉ chạy migration từ graph rỗng không thể phát hiện các vấn đề tương thích của dữ liệu production cũ.

## 18. Kế hoạch rollback

Rollback không chỉ là deploy lại binary cũ. Phiên bản cũ cần một graph state mà nó hiểu được.

Trong thời gian rollback:

- Giữ property hoặc relationship cũ và tiếp tục dual-write nếu phiên bản cũ cần đọc chúng.
- Không xóa label hoặc constraint mà query cũ còn phụ thuộc.
- Không đổi semantics của field cũ trong khi vẫn tuyên bố nó tương thích.
- Giữ migration script có thể chạy lại và có cách đối soát ngược nếu nghiệp vụ cho phép.
- Xác định rõ thời điểm rollback không còn được hỗ trợ; sau mốc đó mới thực hiện contract.

Nếu v4 ngừng ghi property cũ, không thể giả định rollback về v1/v2 vẫn an toàn: các phiên bản chỉ đọc `fullName` có thể thấy giá trị lỗi thời. Vì vậy, phải kết thúc rollback window của những phiên bản đó trước khi triển khai v4. v3 vẫn có thể là rollback target nếu nó đọc `displayName` trước và chỉ dùng `fullName` làm fallback. Sau khi xóa property cũ và gỡ mapping legacy, rollback về phiên bản còn phụ thuộc property đó không còn được hỗ trợ nếu không có migration ngược hoặc restore backup đã kiểm chứng.

## 19. Những thay đổi thường phá vỡ tương thích

| Thay đổi | Rủi ro khi old/new cùng chạy | Cách chuyển đổi an toàn |
|---|---|---|
| Đổi tên property | Code cũ không thấy field mới; code mới không thấy field cũ | Thêm property mới, dual-write, backfill, switch read, rồi xóa field cũ |
| Đổi label | Query theo label cũ bỏ sót node | Gắn cả label cũ và mới, chuyển reader, rồi gỡ label cũ |
| Đổi relationship type | Traversal cũ không còn thấy cạnh | Tạo type mới song song, giữ khóa cạnh ổn định, chuyển reader và writer |
| Thêm property bắt buộc | Node cũ chưa có giá trị | Nullable/fallback, backfill, kiểm tra rồi mới enforce |
| Thay kiểu dữ liệu | Parser hoặc mapping cũ không đọc được kiểu mới | Thêm property chuyển đổi riêng, chuẩn hóa dữ liệu và kiểm tra trước khi switch |
| Thay hướng relationship | Traversal cũ không tìm được quan hệ | Tạo quan hệ mới đúng hướng, giữ quan hệ cũ trong giai đoạn chuyển tiếp |
| Xóa enum hoặc đổi giá trị trạng thái | Code cũ không nhận ra giá trị mới | Mở rộng tập giá trị trước, triển khai reader tương thích rồi mới thu hẹp |
| Xóa index/constraint cũ | Query chậm hoặc mất bảo vệ dữ liệu | Tạo và xác minh index/constraint mới trước khi gỡ cấu trúc cũ |

## 20. Phân biệt tương thích dữ liệu và tương thích API

Ứng dụng thường đồng thời cung cấp REST API, message event hoặc file export. Graph migration an toàn chưa chắc API an toàn.

Nếu JSON v1 trả `fullName`, API v2 có thể thêm `displayName` nhưng vẫn giữ `fullName` trong thời gian client cũ còn sử dụng. Tương tự, khi phát event, producer mới không nên xóa field mà consumer cũ còn đọc. Dùng versioning hoặc schema registry nếu hệ thống message cần hợp đồng rõ ràng.

Tách DTO API khỏi entity SDN giúp thay đổi graph mapping mà không buộc response contract đổi cùng lúc. Một entity có thể chứa cả property legacy và mới trong thời gian migration, trong khi DTO quyết định field nào được public cho từng API version.

## 21. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| v1 không tìm thấy node sau deployment | Đã xóa property hoặc label cũ quá sớm | Expand trước và giữ cấu trúc cũ đến khi mọi reader cũ dừng |
| v2 hiển thị dữ liệu cũ | v1 ghi property cũ sau khi backfill | Giữ field cũ làm nguồn canonical trong giai đoạn mixed-writer; đối soát sau khi v1 dừng |
| Migration chạy hai lần tạo relationship trùng | Không có khóa migration ổn định hoặc không dùng thao tác idempotent | Dùng khóa nghiệp vụ và `MERGE` có định danh rõ |
| Constraint không tạo được | Graph hiện có dữ liệu trùng hoặc vi phạm điều kiện | Kiểm tra và làm sạch dữ liệu trước khi tạo constraint |
| Query mới vẫn chậm | Index còn `POPULATING` hoặc query chưa dùng index | Kiểm tra `SHOW INDEXES`, chờ `ONLINE` và xem query plan |
| Rollback binary thành công nhưng dữ liệu lỗi | Contract đã xóa field cũ hoặc ngừng dual-write | Giữ cấu trúc cũ trong rollback window và định nghĩa rõ mốc contract |
| Node mới không được backfill | Migration chỉ quét một lần trong lúc writer cũ vẫn hoạt động | Chạy lượt đối soát cuối sau khi old writer đã dừng |
| Entity SDN lưu làm mất dữ liệu không mong muốn | Mapping hoặc relationship persistence có semantics khác kỳ vọng | Kiểm tra Cypher được sinh ra và integration test với entity cũ/mới |
| Hai migration runner cùng sửa một tập dữ liệu | Không có coordination hoặc checkpoint | Dùng một runner được điều phối hoặc thiết kế migration an toàn khi chạy song song |

## 22. Checklist trước khi contract schema cũ

Chỉ loại bỏ property, label hoặc relationship cũ khi các điều kiện sau đã được xác nhận:

- [ ] Không còn instance ứng dụng cũ đang chạy.
- [ ] Không còn worker, cron, import, report hoặc consumer dùng cấu trúc cũ.
- [ ] Writer mới đã ghi cấu trúc mới đầy đủ trong thời gian cần thiết.
- [ ] Backfill và lượt đối soát cuối đã hoàn tất.
- [ ] Không còn record thiếu hoặc sai khác theo quy tắc nghiệp vụ.
- [ ] Query mới đã được kiểm thử và index cần thiết ở trạng thái `ONLINE`.
- [ ] Constraint mới đã được tạo và xác minh nếu nghiệp vụ cần.
- [ ] Rollback window đã kết thúc hoặc đã có kế hoạch phục hồi được phê duyệt.
- [ ] Dashboard và log không còn fallback hoặc truy cập cấu trúc cũ ngoài dự kiến.
- [ ] Migration contract có thể chạy an toàn và được ghi nhận trong lịch sử triển khai.

## 23. Nguyên tắc cần nhớ

- Xem graph schema là hợp đồng giữa tất cả phiên bản ứng dụng, worker và query đang truy cập Neo4j.
- Dùng expand–migrate–contract cho thay đổi phá vỡ tương thích.
- Giữ property/label/relationship cũ trong khi reader cũ còn hoạt động.
- Dual-write các giá trị cũ và mới trong cùng transaction hoặc cùng thao tác ghi.
- Giữ nguồn canonical rõ ràng khi old và new writer cùng tồn tại.
- Chạy backfill idempotent theo batch và đối soát cuối sau khi old writer đã dừng.
- Chuyển reader sau khi dữ liệu mới đầy đủ; contract sau khi reader cũ và rollback window kết thúc.
- Tạo index/constraint mới trước khi query hoặc writer mới phụ thuộc vào chúng; kiểm tra trạng thái và dữ liệu hiện tại.
- Kiểm thử ma trận phiên bản, entity mapping, custom Cypher, job migration và rollback.
- Tách migration graph data model khỏi quy trình nâng cấp Neo4j DBMS.

Khi nhiều phiên bản Spring Data Neo4j cùng hoạt động, an toàn migration phụ thuộc vào thứ tự triển khai và cách từng phiên bản đọc/ghi graph. Giữ cấu trúc cũ trong giai đoạn chuyển tiếp, thêm cấu trúc mới theo cách tương thích, chuyển dữ liệu có kiểm soát và chỉ contract khi không còn consumer cũ là cách giảm rủi ro mất dữ liệu và gián đoạn dịch vụ.

## Tài liệu tham khảo

- [Neo4j Upgrade and Migration Guide – Introduction and preparation](https://neo4j.com/docs/upgrade-migration-guide/current/)
- [Neo4j Cypher Manual – Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Cypher Manual – Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Cypher Manual – Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Spring Data Neo4j – Object mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping.html)
- [Spring Data Neo4j – Persisting entities](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
