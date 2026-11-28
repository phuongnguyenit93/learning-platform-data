# Backfill ID, version và thuộc tính mới

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Lập kế hoạch backfill dữ liệu cũ khi bổ sung ID nghiệp vụ, trường `@Version` hoặc property mới cho node và relationship.
- Phân biệt business ID với internal ID/element ID do Neo4j quản lý.
- Viết Cypher backfill có điều kiện để chạy lại an toàn.
- Chia dữ liệu lớn thành các batch transaction và tiếp tục sau khi một batch thất bại.
- Khởi tạo version cho entity cũ trước khi bật optimistic locking trong Spring Data Neo4j (SDN).
- Tính giá trị mặc định hoặc property dẫn xuất từ dữ liệu hiện có mà không ghi đè giá trị hợp lệ.
- Kiểm tra dữ liệu sau backfill, tạo constraint và triển khai thay đổi theo từng giai đoạn.

## 1. Vì sao cần backfill?

Neo4j là cơ sở dữ liệu đồ thị có schema linh hoạt. Node và relationship có thể được bổ sung property mà không cần khai báo trước cấu trúc cột như trong cơ sở dữ liệu quan hệ. Tuy vậy, ứng dụng Spring Data Neo4j vẫn có thể cần chuyển đổi dữ liệu khi domain model thay đổi.

Ví dụ, phiên bản đầu của ứng dụng có node:

```cypher
(:Person {
    legacyId: 101,
    name: "An",
    email: "an@example.com"
})
```

Phiên bản mới cần thêm:

- `publicId`: ID nghiệp vụ ổn định để dùng trong API và trao đổi giữa các hệ thống.
- `version`: trường optimistic locking của SDN.
- `normalizedEmail`: email đã chuẩn hóa để tìm kiếm.
- `status`: trạng thái nghiệp vụ mới.

Nếu chỉ sửa Java entity rồi triển khai, các node cũ vẫn thiếu property. Khi SDN đọc và ghi dữ liệu, ứng dụng có thể gặp null ngoài dự kiến, không nhận diện đúng entity mới/cũ hoặc không có version cần thiết để kiểm soát cập nhật đồng thời.

Backfill là quá trình cập nhật dữ liệu đã tồn tại để phù hợp với mô hình mới. Với Neo4j, phần lớn công việc được thực hiện bằng Cypher trên node và relationship.

## 2. Phân biệt business ID với ID nội bộ của Neo4j

Neo4j tự cấp internal ID cho node và relationship. Trong SDN, `@Id` kết hợp `@GeneratedValue` có thể dùng ID nội bộ hoặc `elementId` tùy kiểu và cơ chế sinh ID. Các ID này phục vụ việc định vị graph element trong mapping.

Không nên dùng `id()` hoặc `elementId()` làm khóa nghiệp vụ lâu dài. Neo4j không bảo đảm ánh xạ internal ID với graph element ổn định qua mọi transaction; internal ID có thể được tái sử dụng sau khi node hoặc relationship bị xóa. Neo4j khuyến nghị dùng application-generated ID cho định danh nghiệp vụ. <https://neo4j.com/docs/cypher-manual/current/functions/scalar/>

Một business ID thường là UUID hoặc mã nghiệp vụ do hệ thống kiểm soát. Nó được lưu như một property của node, ví dụ `publicId`.

Khi entity dùng business ID do ứng dụng gán, SDN yêu cầu trường `@Version` để phân biệt entity mới với entity đã được persist. <https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html>

Ví dụ entity sau khi chuyển sang business ID:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String publicId;

    @Version
    private Long version;

    private String name;

    private String email;

    private String normalizedEmail;

    private String status;

    protected Person() {
    }
}
```

Ở đây `publicId` là property được lưu trên node vì `@Id` không đi kèm `@GeneratedValue`. Nếu dùng `@GeneratedValue` mặc định, SDN có thể dùng ID nội bộ hoặc `elementId`, không phải property business ID vừa backfill.

Nếu chỉ cần thêm ID nghiệp vụ mà chưa muốn thay đổi định danh repository, có thể giữ `@Id` hiện tại và thêm field `publicId` riêng. Chỉ chuyển `@Id` sau khi đã kiểm tra các quan hệ tham chiếu, API, repository và các hệ thống tích hợp.

### 2.1. ID của relationship

Relationship có thể mang property riêng. SDN dùng `@RelationshipId` để nhận diện internal relationship ID khi ánh xạ `@RelationshipProperties`. Giá trị này là định danh kỹ thuật do SDN/Neo4j quản lý, không phải business ID.

Nếu nghiệp vụ cần một mã ổn định cho quan hệ, hãy thêm property riêng như `membershipKey`:

```java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Membership {

    @RelationshipId
    private Long relationshipId;

    private String membershipKey;

    private String role;

    @TargetNode
    private Department department;
}
```

Backfill `membershipKey` nếu cần định danh nghiệp vụ cho relationship. Không tự điền `@RelationshipId` bằng UUID.

## 3. Chuẩn bị trước khi backfill

Trước khi cập nhật dữ liệu thật, cần biết chính xác tập graph bị ảnh hưởng.

Một quy trình chuẩn bị nên gồm:

1. Xác định label node và relationship type cần thay đổi.
2. Đếm số node/relationship đang tồn tại.
3. Đếm số phần tử thiếu property sẽ backfill.
4. Kiểm tra nguồn dữ liệu để tạo ID hoặc tính property mới.
5. Tìm giá trị trùng trước khi tạo unique constraint.
6. Chụp backup hoặc xác nhận khả năng khôi phục theo quy trình vận hành.
7. Xác định các phiên bản ứng dụng nào đang ghi vào cùng graph.
8. Chọn cách chạy migration và batch size phù hợp.

Ví dụ đếm node Person thiếu business ID:

```cypher
MATCH (p:Person)
WHERE p.publicId IS NULL
RETURN count(p) AS missingPublicId
```

Kiểm tra các giá trị legacy ID có bị trùng không:

```cypher
MATCH (p:Person)
WHERE p.legacyId IS NOT NULL
WITH p.legacyId AS legacyId, count(*) AS occurrences
WHERE occurrences > 1
RETURN legacyId, occurrences
ORDER BY occurrences DESC
```

Không tạo unique constraint trước khi hiểu và xử lý dữ liệu trùng. Nếu có nhiều node cùng một legacy ID, việc chuyển trực tiếp legacy ID thành business ID sẽ làm migration thất bại hoặc tạo ra định danh không đáng tin cậy.

## 4. Thiết kế backfill có thể chạy lại

Một migration tốt cần có tính idempotent: chạy lại không làm thay đổi những record đã được xử lý thành công.

Mẫu quan trọng là chỉ cập nhật phần tử đang thiếu property:

```cypher
MATCH (p:Person)
WHERE p.publicId IS NULL
SET p.publicId = randomUUID()
```

Nếu query bị gián đoạn sau khi một số node đã được cập nhật, lần chạy tiếp theo chỉ chọn các node vẫn thiếu `publicId`. UUID đã tạo không bị sinh lại.

Nếu có legacy ID ổn định và duy nhất, có thể ưu tiên dùng nó:

```cypher
MATCH (p:Person)
WHERE p.publicId IS NULL
SET p.publicId = coalesce(
    toString(p.legacyId),
    randomUUID()
)
```

Trong ví dụ này:

- Nếu `legacyId` có giá trị, chuyển nó thành chuỗi.
- Nếu `legacyId` là null, tạo UUID mới.
- Chỉ node thiếu `publicId` mới được cập nhật.

Trước khi dùng legacy ID làm business ID, cần xác nhận nó không trùng và không thay đổi theo thời gian. Nếu không có khóa nguồn đáng tin cậy, UUID ngẫu nhiên là lựa chọn phù hợp hơn.

Không nên viết query không có điều kiện rồi gán lại UUID cho mọi node mỗi lần chạy. Điều đó sẽ thay đổi ID đã được API hoặc relationship khác tham chiếu.

## 5. Backfill dữ liệu lớn theo batch transaction

Một câu lệnh cập nhật toàn bộ graph trong một transaction có thể giữ nhiều transaction state trong bộ nhớ, chạy lâu và khó phục hồi khi lỗi. Neo4j hỗ trợ `CALL { ... } IN TRANSACTIONS` để chia các hàng đầu vào thành những transaction con có commit độc lập.

Ví dụ backfill business ID theo batch 500 node:

```cypher
MATCH (p:Person)
WHERE p.publicId IS NULL
CALL {
    WITH p
    SET p.publicId = coalesce(
        toString(p.legacyId),
        randomUUID()
    )
} IN TRANSACTIONS OF 500 ROWS
```

Các bước thực hiện:

1. `MATCH` và `WHERE` ở bên ngoài chọn những node cần xử lý.
2. Mỗi node được đưa vào subquery.
3. Subquery gán ID cho node.
4. Sau mỗi 500 hàng, transaction con commit.
5. Các batch tiếp theo tiếp tục cho đến khi hết dữ liệu.

Nếu không chỉ định batch size, Neo4j mặc định nhóm 1.000 hàng cho mỗi transaction con. Batch size cần được điều chỉnh theo số thao tác trên mỗi hàng, dung lượng transaction state, lock contention và thời gian xử lý. <https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/>

### 5.1. Lưu ý về implicit transaction

`CALL { ... } IN TRANSACTIONS` chỉ được phép chạy trong implicit transaction. Không chạy query này bên trong explicit transaction, ví dụ một method SDN đang được bao bởi `@Transactional` hoặc một transaction function như `executeWrite()`.

Trong Neo4j Browser, cần dùng `:auto` trước câu query:

```text
:auto
MATCH (p:Person)
WHERE p.publicId IS NULL
CALL {
    WITH p
    SET p.publicId = randomUUID()
} IN TRANSACTIONS OF 500 ROWS
```

Với Neo4j Java Driver, có thể gửi query bằng `Session.run()` ở chế độ auto-commit và tiêu thụ kết quả:

```java
try (var session = driver.session()) {
    var result = session.run("""
        MATCH (p:Person)
        WHERE p.publicId IS NULL
        CALL {
            WITH p
            SET p.publicId = randomUUID()
        } IN TRANSACTIONS OF 500 ROWS
        """);

    result.consume();
}
```

Không bọc lời gọi này trong transaction tường minh. Nếu migration runner tự mở explicit transaction cho mỗi script, hãy tách bước backfill batch ra và chạy qua cơ chế auto-commit phù hợp. Neo4j Migrations có thể quản lý, theo dõi và áp dụng các migration Cypher; cần kiểm tra cách runner thực thi script trước khi dùng nó cho câu lệnh có `IN TRANSACTIONS`. <https://neo4j.com/labs/neo4j-migrations/>

## 6. Backfill version cho entity cũ

SDN hỗ trợ optimistic locking bằng field kiểu `Long` được đánh dấu `@Version`. Giá trị khởi tạo là 0 và SDN tự tăng version khi cập nhật thành công. Không tự tăng version trong logic nghiệp vụ. <https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html>

Khi thêm `@Version` vào entity đã có dữ liệu, các node cũ cần có property version. Có thể khởi tạo các node chưa có version:

```cypher
MATCH (p:Person)
WHERE p.version IS NULL
CALL {
    WITH p
    SET p.version = 0
} IN TRANSACTIONS OF 500 ROWS
```

Sau backfill, entity cũ có version 0. Lần cập nhật tiếp theo qua SDN sẽ kiểm tra version và tăng nó tự động.

### 6.1. Vì sao phải backfill trước khi bật @Version?

Nếu code mới đã ánh xạ `@Version` nhưng node cũ vẫn thiếu property, SDN không có version đã lưu để đối chiếu khi persist. Đặc biệt với business ID, version còn được dùng để phân biệt entity mới và entity đã tồn tại.

Vì vậy, cần điều phối các writer trong lúc chuyển đổi:

- Bảo đảm các luồng tạo mới đã ghi version theo chính sách mới.
- Tạm dừng writer cũ không biết đến version, hoặc dùng một giai đoạn tương thích có kiểm soát.
- Backfill version cho toàn bộ node hiện hữu.
- Kiểm tra không còn node thuộc tập entity cần quản lý bị thiếu version.
- Sau đó mới triển khai mapping `@Version` cho toàn bộ writer.

Không để phiên bản ứng dụng cũ tiếp tục ghi đè entity theo cách bỏ qua version trong lúc phiên bản mới đang dựa vào optimistic locking.

### 6.2. Custom Cypher cũng phải tôn trọng version

Optimistic locking của SDN được áp dụng trong các thao tác persist entity có `@Version`. Một custom Cypher cập nhật trực tiếp node không tự chạy cơ chế version của repository.

Nếu custom query cần cập nhật entity có version, hãy kiểm tra version mong đợi và tăng version trong cùng câu lệnh:

```cypher
MATCH (p:Person {publicId: $publicId})
WHERE p.version = $expectedVersion
SET p.status = $status,
    p.version = p.version + 1
RETURN p
```

Nếu không có node phù hợp với version mong đợi, ứng dụng cần phân biệt xung đột version với trường hợp không tìm thấy node. Không để một writer bỏ qua version trong khi writer khác dùng optimistic locking.

## 7. Backfill property mới với giá trị mặc định

Khi thêm property mới, trước tiên cần xác định ý nghĩa của giá trị mặc định. Không nên gán một trạng thái như `ACTIVE` cho mọi node nếu dữ liệu cũ không đủ căn cứ để kết luận chúng đang hoạt động.

Ví dụ, ứng dụng bổ sung `status` và muốn đánh dấu các node cũ chưa được phân loại:

```cypher
MATCH (p:Person)
WHERE p.status IS NULL
CALL {
    WITH p
    SET p.status = 'PENDING_REVIEW'
} IN TRANSACTIONS OF 500 ROWS
```

Chỉ property đang null được gán giá trị. Những node đã có status sẽ được giữ nguyên.

Nếu nghiệp vụ thực sự quy định mọi node cũ mặc định là `ACTIVE`, có thể thay giá trị trong query. Tuy nhiên, hãy xác nhận quy tắc đó với chủ sở hữu dữ liệu trước khi chạy.

## 8. Backfill property dẫn xuất từ dữ liệu hiện có

Property mới đôi khi được tính từ các property cũ. Ví dụ `normalizedEmail` được tạo bằng cách bỏ khoảng trắng ở hai đầu và chuyển email thành chữ thường:

```cypher
MATCH (p:Person)
WHERE p.normalizedEmail IS NULL
  AND p.email IS NOT NULL
CALL {
    WITH p
    SET p.normalizedEmail = toLower(trim(p.email))
} IN TRANSACTIONS OF 500 ROWS
```

Query bỏ qua node không có email. Đây là lựa chọn có chủ đích: dữ liệu thiếu nguồn không nên tự động biến thành một giá trị giả.

Sau backfill, cần quyết định cách xử lý node không có email:

- Cho phép `normalizedEmail` tiếp tục null.
- Yêu cầu người dùng bổ sung email.
- Đánh dấu node ở trạng thái cần rà soát.
- Loại node khỏi nhóm dữ liệu cần tính năng mới.

Nếu muốn chuẩn hóa toàn bộ dữ liệu, phải xác định rõ quy tắc với null, chuỗi rỗng, ký tự Unicode và dữ liệu sai định dạng.

### 8.1. Backfill nhiều property trong cùng batch

Nếu các property thuộc cùng một node và có cùng phạm vi xử lý, có thể cập nhật chúng trong cùng một subquery:

```cypher
MATCH (p:Person)
WHERE p.publicId IS NULL
   OR p.version IS NULL
   OR p.status IS NULL
   OR (p.normalizedEmail IS NULL AND p.email IS NOT NULL)
CALL {
    WITH p
    SET p.publicId = coalesce(
            p.publicId,
            coalesce(toString(p.legacyId), randomUUID())
        ),
        p.version = coalesce(p.version, 0),
        p.status = coalesce(p.status, 'PENDING_REVIEW'),
        p.normalizedEmail = coalesce(
            p.normalizedEmail,
            toLower(trim(p.email))
        )
} IN TRANSACTIONS OF 500 ROWS
```

Cách này giảm số lần quét node. Các biểu thức `coalesce()` giữ lại giá trị đã có và chỉ bổ sung giá trị khi property còn null.

Nếu property dẫn xuất có quy tắc tính toán phức tạp hoặc cần xử lý lỗi riêng, nên tách thành migration riêng để dễ kiểm tra và chạy lại.

## 9. Backfill property trên relationship

Relationship cũng có thể thiếu property sau khi domain model được mở rộng. Ví dụ, ứng dụng cần thêm `membershipKey` cho relationship `MEMBER_OF`:

```cypher
MATCH ()-[r:MEMBER_OF]-()
WHERE r.membershipKey IS NULL
CALL {
    WITH r
    SET r.membershipKey = randomUUID()
} IN TRANSACTIONS OF 500 ROWS
```

Nếu relationship có property mới như `roleStatus`, có thể backfill theo quy tắc nghiệp vụ:

```cypher
MATCH ()-[r:MEMBER_OF]-()
WHERE r.roleStatus IS NULL
CALL {
    WITH r
    SET r.roleStatus = 'PENDING_REVIEW'
} IN TRANSACTIONS OF 500 ROWS
```

Với SDN, các property này có thể được ánh xạ trong class `@RelationshipProperties`. Hãy phân biệt property nghiệp vụ như `membershipKey` với `@RelationshipId` là internal relationship identifier.

## 10. Kiểm tra dữ liệu sau backfill

Không nên coi việc query chạy thành công là bằng chứng dữ liệu đã đúng. Cần xác minh số lượng thiếu, trùng và giá trị dẫn xuất.

### 10.1. Kiểm tra property bắt buộc đã được điền

```cypher
MATCH (p:Person)
WHERE p.publicId IS NULL
   OR p.version IS NULL
   OR p.status IS NULL
RETURN count(p) AS incompletePeople
```

Nếu `normalizedEmail` là bắt buộc với mọi node có email:

```cypher
MATCH (p:Person)
WHERE p.email IS NOT NULL
  AND p.normalizedEmail IS NULL
RETURN count(p) AS missingNormalizedEmail
```

### 10.2. Kiểm tra business ID bị trùng

```cypher
MATCH (p:Person)
WHERE p.publicId IS NOT NULL
WITH p.publicId AS publicId, count(*) AS occurrences
WHERE occurrences > 1
RETURN publicId, occurrences
ORDER BY occurrences DESC
```

Nếu kết quả còn dòng, cần xử lý trùng trước khi tạo uniqueness constraint. Không tự động đổi ID của các node trùng mà chưa xác định các quan hệ và hệ thống bên ngoài đang tham chiếu ID nào.

### 10.3. Kiểm tra property dẫn xuất

```cypher
MATCH (p:Person)
WHERE p.email IS NOT NULL
  AND p.normalizedEmail <> toLower(trim(p.email))
RETURN p.publicId, p.email, p.normalizedEmail
LIMIT 50
```

Truy vấn này giúp phát hiện các giá trị không khớp quy tắc chuẩn hóa đã thống nhất.

### 10.4. Tạo constraint sau khi dữ liệu hợp lệ

Sau khi xác nhận ID không null và không trùng, có thể tạo uniqueness constraint:

```cypher
CREATE CONSTRAINT person_public_id_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.publicId IS UNIQUE
```

Uniqueness constraint bảo đảm giá trị đã có không trùng nhau; nó không tự bắt buộc mọi node phải có property. Nếu cần cả tồn tại và duy nhất, cân nhắc node key constraint hoặc existence constraint phù hợp với phiên bản và edition Neo4j đang triển khai.

## 11. Tính idempotent và khả năng tiếp tục sau lỗi

Với `CALL { ... } IN TRANSACTIONS`, mỗi batch có transaction riêng và commit độc lập. Nếu một batch sau thất bại, các batch đã commit trước đó vẫn được giữ lại. Điều này cho phép chạy lại query nếu điều kiện backfill chỉ chọn dữ liệu còn thiếu.

Ví dụ:

```cypher
MATCH (p:Person)
WHERE p.publicId IS NULL
CALL {
    WITH p
    SET p.publicId = randomUUID()
} IN TRANSACTIONS OF 500 ROWS
```

Lần chạy đầu có thể cập nhật 10.000 node rồi thất bại ở batch tiếp theo. Khi chạy lại, những node đã có `publicId` không được chọn nữa; query tiếp tục xử lý node còn thiếu.

Tính idempotent cần được bảo đảm trong cả logic dữ liệu:

- Chỉ chọn record chưa được xử lý.
- Không sinh lại ID đã tồn tại.
- Không ghi đè property mới đã có giá trị hợp lệ.
- Giá trị mặc định phải có ý nghĩa ổn định.
- Không tạo relationship hoặc node trùng bằng `CREATE` mỗi lần chạy lại.
- Nếu migration dùng dữ liệu ngoài, phải có khóa nguồn ổn định để nhận diện từng hàng.

Neo4j Data Ingestion Guide mô tả cách dùng batch transaction và trạng thái xử lý để xác định điểm tiếp tục sau lỗi. <https://neo4j.com/docs/data-ingestion-guide/best-practices/resuming-failed-ingestions/>

## 12. Chọn batch size và kiểm soát tác động vận hành

Batch size quá lớn có thể làm transaction state tăng, giữ lock lâu và vượt giới hạn thời gian hoặc bộ nhớ. Batch quá nhỏ tạo nhiều commit, làm tăng overhead và transaction log.

Có thể bắt đầu với 500 hoặc 1.000 node mỗi batch, sau đó đo đạc trên môi trường staging với dữ liệu gần production.

Theo dõi:

- Thời gian của từng batch.
- Số node/relationship được cập nhật.
- Transaction state và heap usage.
- Lock wait và deadlock.
- Dung lượng transaction log.
- Tải CPU và I/O của database.
- Số lượng record còn thiếu sau mỗi lần chạy.

Không nên bật `IN CONCURRENT TRANSACTIONS` ngay từ đầu. Backfill relationship hoặc node có nhiều liên kết có thể khiến nhiều batch tranh chấp cùng node đầu mút và phát sinh deadlock. Chỉ tăng concurrency khi các batch thực sự độc lập hoặc đã có chiến lược phân vùng dữ liệu.

## 13. Triển khai theo mô hình expand, migrate, contract

Thay đổi dữ liệu và ứng dụng nên được triển khai theo từng giai đoạn để giảm thời gian hệ thống ở trạng thái không tương thích.

| Giai đoạn | Công việc |
| --- | --- |
| 1. Inventory | Đếm dữ liệu cũ, kiểm tra null, duplicate và nguồn ID |
| 2. Expand | Thêm mapping/property mới theo hướng tương thích; writer mới bắt đầu ghi property mới |
| 3. Backfill | Chạy Cypher theo batch để điền ID, version và property mới |
| 4. Validate | Kiểm tra null, duplicate, giá trị dẫn xuất và relationship |
| 5. Constrain | Tạo uniqueness/key/existence constraint phù hợp |
| 6. Switch | Chuyển ứng dụng đọc và ghi theo model mới |
| 7. Contract | Loại bỏ field cũ sau khi không còn phiên bản ứng dụng phụ thuộc |

Riêng với `@Version`, phải bảo đảm dữ liệu đã có version trước khi code mới dựa vào optimistic locking. Nếu còn writer cũ không ghi hoặc không kiểm tra version, hãy dừng writer đó trong giai đoạn backfill hoặc triển khai một bước tương thích được kiểm soát.

Không xóa field cũ ngay sau khi backfill. Giữ nó trong thời gian rollback và xác minh các consumer đã chuyển sang property mới.

## 14. Quản lý migration có phiên bản

Migration cần được lưu dưới dạng script có version và được áp dụng có kiểm soát giữa môi trường local, test, staging và production.

Neo4j Migrations là một lựa chọn để theo dõi và áp dụng thay đổi schema/data bằng Cypher script hoặc Java migration. Công cụ này tích hợp với Spring Boot và Neo4j Java Driver. <https://neo4j.com/labs/neo4j-migrations/>

Nên tách migration thành các bước có mục đích rõ:

- Thêm constraint hoặc index.
- Backfill business ID.
- Backfill version.
- Tính property mới.
- Xác minh và tạo constraint cuối cùng.

Với batch query dùng `CALL ... IN TRANSACTIONS`, phải bảo đảm migration runner gửi query bằng implicit transaction. Nếu runner bao toàn bộ script trong explicit transaction, câu lệnh sẽ không hợp lệ; hãy chạy batch backfill qua auto-commit execution riêng.

Mỗi migration nên có mô tả về tập node/relationship tác động, điều kiện lọc, batch size, cách kiểm tra sau khi chạy và cách tiếp tục khi thất bại.

## 15. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `elementId()` làm business ID | Internal element ID không có bảo đảm ổn định ngoài transaction | Backfill application-generated ID |
| Gán UUID cho mọi node mỗi lần chạy | Query không lọc node thiếu ID | Dùng `WHERE publicId IS NULL` |
| Dùng legacy ID mà chưa kiểm tra trùng | Dữ liệu nguồn không bảo đảm uniqueness | Kiểm tra duplicate trước khi chuyển |
| Thêm `@Version` nhưng node cũ chưa có version | SDN không có giá trị version đã lưu để đối chiếu | Backfill version trước khi bật mapping mới |
| Tự tăng version trong service | Can thiệp vào cơ chế optimistic locking của SDN | Để SDN quản lý; custom Cypher phải kiểm tra và tăng version có chủ đích |
| Chạy backfill lớn trong một transaction | Transaction state lớn, khó tiếp tục sau lỗi | Dùng `CALL ... IN TRANSACTIONS` |
| Bọc `CALL ... IN TRANSACTIONS` bằng `@Transactional` | Câu lệnh chỉ chạy trong implicit transaction | Gửi bằng auto-commit |
| Gán default cho mọi node | Ghi đè giá trị hoặc tạo dữ liệu sai nghĩa nghiệp vụ | Chỉ cập nhật property null và chọn default đúng |
| Tạo unique constraint khi còn duplicate | Constraint không thể được tạo | Làm sạch và xác minh dữ liệu trước |
| Chỉ kiểm tra query chạy thành công | Không phát hiện record còn thiếu hoặc giá trị sai | Chạy các query validate sau migration |
| Backfill relationship bằng `@RelationshipId` | Nhầm internal ID với business property | Tạo property riêng nếu relationship cần business key |
| Xóa field cũ ngay sau migration | Phiên bản ứng dụng cũ có thể còn sử dụng | Dùng expand-contract và giữ rollback window |

## 16. Quy trình thực hành

Giả sử cần chuyển node Person từ `legacyId` sang `publicId`, thêm version, status và normalized email.

**Bước 1: Kiểm tra dữ liệu hiện tại**

```cypher
MATCH (p:Person)
RETURN
    count(p) AS total,
    count(p.publicId) AS withPublicId,
    count(p.version) AS withVersion,
    count(p.status) AS withStatus,
    count(p.normalizedEmail) AS withNormalizedEmail
```

**Bước 2: Kiểm tra legacy ID**

```cypher
MATCH (p:Person)
WHERE p.legacyId IS NOT NULL
WITH p.legacyId AS legacyId, count(*) AS occurrences
WHERE occurrences > 1
RETURN legacyId, occurrences
```

**Bước 3: Backfill theo batch**

```cypher
MATCH (p:Person)
WHERE p.publicId IS NULL
   OR p.version IS NULL
   OR p.status IS NULL
   OR (p.normalizedEmail IS NULL AND p.email IS NOT NULL)
CALL {
    WITH p
    SET p.publicId = coalesce(
            p.publicId,
            coalesce(toString(p.legacyId), randomUUID())
        ),
        p.version = coalesce(p.version, 0),
        p.status = coalesce(p.status, 'PENDING_REVIEW'),
        p.normalizedEmail = coalesce(
            p.normalizedEmail,
            toLower(trim(p.email))
        )
} IN TRANSACTIONS OF 500 ROWS
```

**Bước 4: Xác minh dữ liệu**

```cypher
MATCH (p:Person)
WHERE p.publicId IS NULL
   OR p.version IS NULL
   OR p.status IS NULL
RETURN count(p) AS incompletePeople
```

**Bước 5: Tìm business ID trùng**

```cypher
MATCH (p:Person)
WHERE p.publicId IS NOT NULL
WITH p.publicId AS publicId, count(*) AS occurrences
WHERE occurrences > 1
RETURN publicId, occurrences
```

**Bước 6: Tạo uniqueness constraint**

Chỉ chạy sau khi dữ liệu đã hợp lệ:

```cypher
CREATE CONSTRAINT person_public_id_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.publicId IS UNIQUE
```

**Bước 7: Chuyển mapping SDN**

Sau khi xác nhận dữ liệu đã được backfill và writer tương thích, ánh xạ entity bằng `@Id`, `@Version` và các property mới. Đọc thử các entity cũ, tạo entity mới và cập nhật một entity đã tồn tại để xác minh mapping.

## 17. Câu hỏi tự kiểm tra

1. Vì sao không nên dùng internal ID hoặc `elementId()` làm business ID lâu dài?
2. Khi nào nên backfill một property ID riêng thay vì thay đổi `@Id` hiện tại?
3. Vì sao business ID trong SDN yêu cầu trường `@Version`?
4. Giá trị khởi tạo của `@Version Long` là bao nhiêu?
5. Vì sao không được tự tăng version trong service?
6. Điều kiện `WHERE p.publicId IS NULL` giúp migration có tính idempotent như thế nào?
7. `CALL { ... } IN TRANSACTIONS OF 500 ROWS` chia công việc thành những đơn vị nào?
8. Vì sao câu lệnh `CALL ... IN TRANSACTIONS` không được chạy bên trong `@Transactional`?
9. Khi batch sau thất bại, các batch đã commit trước đó có bị rollback không?
10. Vì sao cần kiểm tra duplicate trước khi tạo uniqueness constraint?
11. Khi backfill property dẫn xuất, nên xử lý node thiếu dữ liệu nguồn thế nào?
12. `@RelationshipId` khác business property của relationship ra sao?
13. Vì sao cần kiểm tra writer cũ trước khi bật `@Version`?
14. Expand-migrate-contract giúp giảm rủi ro triển khai như thế nào?

## Tài liệu tham khảo

- [Neo4j Cypher Manual – CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Neo4j Data Ingestion Guide – Resuming a failed ingestion](https://neo4j.com/docs/data-ingestion-guide/best-practices/resuming-failed-ingestions/)
- [Neo4j Cypher Manual – Scalar functions: elementId() và randomUUID()](https://neo4j.com/docs/cypher-manual/current/functions/scalar/)
- [Spring Data Neo4j – Metadata-based Mapping và @Version](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Neo4j Migrations](https://neo4j.com/labs/neo4j-migrations/)

## Kết luận

Backfill ID, version và property mới là bước chuyển đổi dữ liệu cần được lập kế hoạch trước khi ứng dụng sử dụng domain model mới. Với SDN, business ID cần được quản lý ổn định và entity dùng business ID phải có `@Version`; version của dữ liệu cũ cần được khởi tạo trước khi bật optimistic locking.

Hãy viết Cypher backfill theo điều kiện, chỉ cập nhật property còn thiếu và chia dữ liệu lớn thành các batch transaction. Sau khi chạy, kiểm tra null, duplicate, dữ liệu dẫn xuất và constraint trước khi chuyển ứng dụng sang mapping mới. Kết hợp migration có phiên bản, writer tương thích và quy trình expand-migrate-contract sẽ giúp thay đổi dữ liệu đồ thị có thể tiếp tục sau lỗi và dễ kiểm soát trong quá trình triển khai.
