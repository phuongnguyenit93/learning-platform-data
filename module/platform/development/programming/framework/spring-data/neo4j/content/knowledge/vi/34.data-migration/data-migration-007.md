# Nhập dữ liệu lặp an toàn bằng MERGE kết hợp constraint

## Mục tiêu bài học

Một job nhập dữ liệu có thể bị chạy lại vì timeout, lỗi mạng, worker khởi động lại hoặc người vận hành cần nạp lại một file. Nếu mỗi lần chạy đều dùng `CREATE`, cùng một dòng nguồn có thể sinh thêm node và relationship trùng lặp. Điều này làm sai số liệu, tăng chi phí lưu trữ và khiến truy vấn graph trả về kết quả không mong muốn.

Trong Neo4j, `MERGE` là nền tảng để tìm hoặc tạo một pattern. Tuy nhiên, muốn nhập lặp an toàn trong môi trường có nhiều transaction đồng thời, cần kết hợp `MERGE` với khóa định danh ổn định và uniqueness constraint. Đồng thời phải chuẩn hóa dữ liệu đầu vào, tách bước nhập node và relationship, cập nhật có kiểm soát, và thiết kế batch có thể chạy lại.

Bài học này trình bày cách xây dựng một quy trình import có thể chạy lại nhiều lần mà không tạo dữ liệu trùng, cách tích hợp Cypher vào Spring Data Neo4j (SDN), và cách kiểm thử tính idempotent của toàn bộ job.

## 1. Idempotent import là gì?

Một thao tác import được xem là idempotent khi chạy lại cùng một dữ liệu nguồn không làm thay đổi kết quả graph đã đạt được sau lần chạy thành công đầu tiên. Nếu gọi `F_D` là thao tác import dữ liệu `D` lên graph, tính chất này có thể viết:

```text
F_D(F_D(G)) = F_D(G)
```

Ví dụ, file có một khách hàng với khóa `ERP_A + C-100`. Sau lần đầu, graph có một node Customer tương ứng. Khi chạy lại cùng file, job phải khớp node đó và cập nhật có kiểm soát; nó không tạo node thứ hai.

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Idempotency | Chạy lại cùng yêu cầu không tạo thêm hiệu ứng ngoài ý muốn |
| Upsert | Tìm bản ghi đã có để cập nhật, hoặc tạo mới nếu chưa có |
| Uniqueness constraint | Database từ chối dữ liệu vi phạm quy tắc duy nhất |

`MERGE` thường được dùng để triển khai upsert. Constraint bảo vệ khóa định danh khi có nhiều luồng ghi. Cả hai cùng hỗ trợ idempotency, nhưng không tự làm cho mọi câu lệnh trong job trở nên idempotent.

Ví dụ, `SET c.lastImportedAt = datetime()` làm thay đổi node ở mỗi lần chạy lại. `SET c.importCount = c.importCount + 1` cũng tạo hiệu ứng lặp. Nếu cần cùng đầu vào cho ra cùng trạng thái, hãy chỉ cập nhật property theo dữ liệu nguồn hoặc chỉ đặt metadata tạo mới bằng `ON CREATE`.

## 2. Chọn khóa định danh ổn định trước khi nhập

Mỗi loại node cần một khóa cho phép xác định cùng một thực thể qua các lần import. Khóa này thường là business key từ hệ thống nguồn.

Ví dụ:

| Node | Khóa định danh |
|---|---|
| Customer | `sourceSystem + externalId` |
| Product | `supplierId + productCode` |
| Order | `sourceSystem + externalOrderId` |
| Account | `tenantId + accountNumber` |

Không nên dùng tên hiển thị, địa chỉ hoặc trạng thái làm khóa nếu các thuộc tính đó có thể thay đổi. Cũng không nên đưa toàn bộ property của node vào pattern `MERGE`: một thay đổi nhỏ ở property mô tả có thể khiến pattern không còn khớp node cũ.

Ví dụ entity:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String sourceSystem;

    private String externalId;

    private String name;

    private long sourceVersion;

    // Constructor, getter và setter được lược bỏ.
}
```

Trong ví dụ này:

- `id` là định danh persistence do SDN quản lý.
- `sourceSystem + externalId` là khóa nghiệp vụ của dữ liệu nhập.
- `sourceVersion` là phiên bản hoặc số thứ tự cập nhật từ hệ thống nguồn.

Nếu hệ thống nguồn không cung cấp version, có thể dùng timestamp cập nhật đáng tin cậy hoặc quy tắc ưu tiên nguồn. Không dùng thời gian nhận message ở worker làm version nếu các worker có thể xử lý sai thứ tự.

## 3. Tạo uniqueness constraint trước khi import

Tạo composite uniqueness constraint trên đúng khóa nghiệp vụ:

```cypher
CREATE CONSTRAINT customer_source_external_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.sourceSystem, c.externalId) IS UNIQUE;
```

Constraint bảo đảm hai node mang label `Customer` không thể có cùng tổ hợp `sourceSystem + externalId` khi cả hai property hiện diện. Constraint cũng tạo backing index để Neo4j tra cứu khóa hiệu quả hơn khi chạy `MERGE`.

Nếu mọi Customer bắt buộc phải có cả hai property, có thể dùng node key constraint khi edition và phiên bản Neo4j hỗ trợ:

```cypher
CREATE CONSTRAINT customer_business_key IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.sourceSystem, c.externalId) IS NODE KEY;
```

Node key constraint bảo đảm cả sự tồn tại và uniqueness của các property trong tổ hợp. Tính năng này phụ thuộc edition; nếu không khả dụng, hãy kết hợp uniqueness constraint với validation ở mọi luồng ghi.

Kiểm tra constraint sau khi triển khai:

```cypher
SHOW CONSTRAINTS;
```

Không đợi đến lúc import mới tạo constraint. Nếu graph đã có dữ liệu, hãy kiểm tra và xử lý duplicate trước khi tạo constraint. Dùng migration có version để quản lý schema, thay vì để từng job tự ý tạo hoặc xóa constraint khi chạy.

### Vì sao constraint cần thiết dù đã dùng MERGE?

`MERGE` tìm pattern rồi tạo nếu chưa có. Khi các transaction chạy tuần tự, cùng một pattern thường được khớp ở lần chạy tiếp theo. Nhưng nếu hai transaction đồng thời cùng tìm một khóa chưa tồn tại, `MERGE` riêng lẻ không bảo đảm node duy nhất.

Constraint là hàng rào ở database: nó bảo vệ identity kể cả khi có nhiều request, import worker hoặc ứng dụng khác cùng ghi. Vì vậy, quy tắc thực hành là tạo constraint trước, sau đó mới nhập dữ liệu bằng `MERGE`.

## 4. Chuẩn hóa và kiểm tra dữ liệu nguồn

`MERGE` so khớp theo giá trị và kiểu dữ liệu thực tế. Các giá trị sau có thể không được xem là cùng một khóa:

- `"C-100"` và `"C-100 "` (có khoảng trắng cuối).
- `"erp_a"` và `"ERP_A"` nếu quy tắc khóa phân biệt casing.
- Chuỗi `"00125"` và số nguyên `125`.
- Unicode có cách biểu diễn khác nhau dù nhìn giống nhau.

Hãy chuẩn hóa trước khi tạo pattern:

```java
import java.util.Locale;

public String normalizeExternalId(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException(
                "externalId must not be blank");
    }

    return raw.trim().toUpperCase(Locale.ROOT);
}
```

Đây là ví dụ cho mã được quy định không phân biệt hoa thường. Không chuyển mọi khóa sang chữ hoa một cách máy móc; dùng đúng quy tắc của hệ thống nguồn. Nếu số 0 ở đầu có ý nghĩa, giữ mã dưới dạng chuỗi và không ép sang số.

Kiểm tra các trường định danh bắt buộc trước khi chạy Cypher. `MERGE` không chấp nhận property null trong pattern. Với composite key, nếu thiếu một thành phần thì không được tự ý thay bằng chuỗi rỗng hoặc một giá trị giả, vì các bản ghi khác nhau có thể bị gộp thành cùng identity.

Nên tách dữ liệu đầu vào thành ba nhóm:

1. Hợp lệ và có thể nhập.
2. Trùng khóa trong cùng file, cần khử trùng hoặc xác định quy tắc ưu tiên.
3. Không hợp lệ, cần ghi nhận để sửa hoặc đưa vào vùng cách ly.

## 5. MERGE node theo khóa, cập nhật property bên ngoài pattern

Ví dụ import Customer:

```cypher
MERGE (c:Customer {
    sourceSystem: $sourceSystem,
    externalId: $externalId
})
ON CREATE SET
    c.createdAt = $sourceCreatedAt,
    c.name = $name,
    c.sourceVersion = $sourceVersion
SET
    c.name = $name,
    c.updatedAt = $sourceUpdatedAt
RETURN c;
```

Pattern `MERGE` chỉ chứa các property định danh. Các property mô tả được cập nhật ở `ON CREATE` hoặc `SET`.

Tuy nhiên, query trên vẫn ghi đè `name` theo mỗi lần chạy. Nếu dữ liệu nguồn có thể đến sai thứ tự, một bản ghi cũ được import sau có thể ghi đè dữ liệu mới. Để tránh việc này, dùng version hoặc timestamp có thứ tự rõ ràng.

### Chỉ áp dụng bản cập nhật mới hơn

Ví dụ `sourceVersion` là số nguyên tăng dần ở hệ thống nguồn:

Quy ước trong ví dụ là version không âm; giá trị `-1` được dùng làm mốc cho node cũ chưa có version.

```cypher
MERGE (c:Customer {
    sourceSystem: $sourceSystem,
    externalId: $externalId
})
ON CREATE SET
    c.createdAt = $sourceCreatedAt,
    c.name = $name,
    c.sourceVersion = $sourceVersion
WITH c
WHERE $sourceVersion > coalesce(c.sourceVersion, -1)
SET
    c.name = $name,
    c.sourceVersion = $sourceVersion,
    c.updatedAt = $sourceUpdatedAt
RETURN c;
```

Cách hoạt động:

- Node mới được tạo với version và dữ liệu của dòng nguồn.
- Dòng có version lớn hơn cập nhật node hiện tại.
- Dòng có version bằng hoặc nhỏ hơn không thay đổi node.
- Chạy lại cùng một dòng không làm thay đổi trạng thái sau lần ghi đầu tiên.

Nếu hai dòng cùng version nhưng có payload khác nhau, đó là xung đột dữ liệu nguồn. Hãy phát hiện và xử lý theo quy tắc nghiệp vụ thay vì để kết quả phụ thuộc thứ tự dòng.

### Cập nhật một phần property bằng SET +=

Khi dữ liệu đầu vào là map và chỉ muốn cập nhật các key được cung cấp:

```cypher
MATCH (c:Customer {
    sourceSystem: $sourceSystem,
    externalId: $externalId
})
SET c += $properties;
```

`SET c += map` chỉ áp dụng các key trong map; property khác được giữ nguyên. Ngược lại, `SET c = map` thay thế toàn bộ property map và có thể xóa các property không có trong map. Với import tăng dần, `+=` thường an toàn hơn.

Không đưa các property định danh như `sourceSystem` và `externalId` vào map cập nhật nếu chúng không được phép thay đổi. Hãy tạo map từ danh sách field được phép ghi để tránh một payload ngoài ý muốn sửa khóa nghiệp vụ.

Lưu ý: giá trị null trong map có thể xóa property tương ứng. Hãy xác định rõ null nghĩa là “xóa dữ liệu”, “không cập nhật” hay “dữ liệu nguồn không biết”. Nếu null nghĩa là không cập nhật, hãy loại key đó khỏi map trước khi bind hoặc xử lý bằng điều kiện Cypher rõ ràng.

## 6. Khử trùng các dòng nguồn trước khi ghi

Ngay cả khi database có constraint, một file có thể chứa nhiều dòng cùng business key. Nếu các dòng đó có payload khác nhau, việc xử lý tuần tự có thể khiến dòng sau ghi đè dòng trước.

Trước khi import, kiểm tra duplicate trong nguồn. Với danh sách đã được bind vào Cypher:

```cypher
UNWIND $rows AS row
WITH row.sourceSystem AS sourceSystem,
     row.externalId AS externalId,
     count(*) AS occurrences
WHERE occurrences > 1
RETURN sourceSystem, externalId, occurrences
ORDER BY occurrences DESC;
```

Nếu có duplicate, chọn một trong các chính sách:

- Khử trùng trước khi gửi vào database, giữ dòng có version mới nhất.
- Từ chối cả nhóm khóa có xung đột và ghi vào báo cáo lỗi.
- Nếu nhiều dòng đại diện cho các sự kiện khác nhau, mô hình hóa từng sự kiện thành node riêng có event ID thay vì gộp thành một Customer.

Không dùng `DISTINCT` một cách tùy tiện để che duplicate. Hai dòng có cùng khóa nhưng dữ liệu khác nhau cần một quy tắc nghiệp vụ xác định dòng nào có quyền cập nhật.

## 7. Nhập node trước, relationship sau

Với graph có Customer, Order và relationship `PLACED`, nên chia import thành các pha:

1. Tạo hoặc cập nhật Customer.
2. Tạo hoặc cập nhật Order.
3. Sau khi hai loại node đã tồn tại, tạo relationship giữa chúng.

Không gộp toàn bộ node và relationship vào một pattern `MERGE` dài nếu từng node có identity độc lập. Nếu một phần pattern không khớp, Cypher có thể cố tạo toàn bộ pattern và gây xung đột với node đã tồn tại hoặc tạo node ngoài ý muốn.

### Import Customer và Order

```cypher
UNWIND $customers AS row
MERGE (c:Customer {
    sourceSystem: row.sourceSystem,
    externalId: row.externalId
})
SET c.name = row.name;
```

```cypher
UNWIND $orders AS row
MERGE (o:Order {
    sourceSystem: row.sourceSystem,
    externalOrderId: row.externalOrderId
})
SET o.status = row.status,
    o.total = row.total;
```

Mỗi loại node cần uniqueness constraint trên khóa riêng. Các câu lệnh này có thể chạy lại mà không tạo node mới cho cùng identity.

## 8. MERGE relationship theo hai endpoint đã tồn tại

Sau khi node được nhập, dùng `MATCH` để tìm hai endpoint rồi `MERGE` relationship:

```cypher
MATCH (c:Customer {
    sourceSystem: $customerSource,
    externalId: $customerId
})
MATCH (o:Order {
    sourceSystem: $orderSource,
    externalOrderId: $orderId
})
MERGE (c)-[r:PLACED]->(o)
ON CREATE SET r.createdAt = $createdAt
SET r.channel = $channel;
```

`MATCH` xác định rõ Customer và Order đã tồn tại. `MERGE` tạo relationship nếu chưa có, hoặc khớp cạnh đã có nếu pattern tương ứng tồn tại.

Nếu một cặp Customer và Order chỉ được có một relationship `PLACED`, pattern trên biểu đạt quy tắc đó. Nếu cùng hai endpoint có thể có nhiều sự kiện đặt hàng, hãy đưa định danh sự kiện ổn định vào relationship:

```cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (o:Order {orderId: $orderId})
MERGE (c)-[r:PLACED {eventId: $eventId}]->(o)
ON CREATE SET r.createdAt = $createdAt
SET r.channel = $channel;
```

Nếu `eventId` phải duy nhất trên toàn bộ relationship `PLACED`, hãy dùng relationship uniqueness constraint khi phiên bản và edition Neo4j hỗ trợ, hoặc mô hình hóa sự kiện thành node có uniqueness constraint. Nếu không có ràng buộc phù hợp, bảo đảm uniqueness ở tầng import và kiểm thử mọi luồng ghi.

Neo4j có cơ chế khóa riêng cho `MERGE` relationship giữa hai endpoint đã được bind trước: khi pattern chưa tồn tại, database khóa các endpoint rồi kiểm tra lại để tránh hai transaction đồng thời tạo cùng relationship theo pattern đó. Đây là hành vi của mẫu relationship MERGE cụ thể; không thay thế constraint cho identity của node.

## 9. Kiểm tra endpoint bị thiếu trước khi nhập relationship

Một `MATCH` không tìm thấy endpoint sẽ làm dòng đó không đi tiếp đến `MERGE`. Vì vậy, relationship có thể bị bỏ qua mà query không báo lỗi theo cách người viết mong đợi.

Trước khi tạo cạnh, kiểm tra các dòng có Customer hoặc Order chưa tồn tại:

```cypher
UNWIND $rows AS row
OPTIONAL MATCH (c:Customer {
    sourceSystem: row.customerSource,
    externalId: row.customerId
})
OPTIONAL MATCH (o:Order {
    sourceSystem: row.orderSource,
    externalOrderId: row.orderId
})
WITH row, c, o
WHERE c IS NULL OR o IS NULL
RETURN row, c IS NULL AS missingCustomer,
       o IS NULL AS missingOrder;
```

Quy trình import nên có báo cáo số lượng:

- Số dòng nguồn đọc được.
- Số dòng hợp lệ.
- Số node tạo mới.
- Số node khớp/cập nhật.
- Số relationship tạo mới.
- Số dòng bị bỏ qua do thiếu endpoint.
- Số dòng lỗi hoặc xung đột khóa.

Nếu không có báo cáo này, job có thể kết thúc thành công về mặt kỹ thuật nhưng graph vẫn thiếu relationship.

## 10. Dùng LOAD CSV cho file nhỏ và vừa

`LOAD CSV` là cơ chế tích hợp của Neo4j để đọc CSV từ đường dẫn local hoặc URL. Trước khi ghi, hãy chạy dry-run để xác nhận header, delimiter và kiểu dữ liệu:

```cypher
LOAD CSV WITH HEADERS
FROM 'file:///customers.csv' AS row
RETURN row
LIMIT 5;
```

Đếm số dòng:

```cypher
LOAD CSV WITH HEADERS
FROM 'file:///customers.csv' AS row
RETURN count(row) AS totalRows;
```

Neo4j đọc giá trị CSV dưới dạng chuỗi. Cần chuyển đổi có chủ đích các trường số, ngày giờ và boolean. Ví dụ:

```cypher
LOAD CSV WITH HEADERS
FROM 'file:///customers.csv' AS row
RETURN row.externalId AS externalId,
       toIntegerOrNull(row.sourceVersion) AS sourceVersion,
       row.name AS name
LIMIT 10;
```

Dùng `linenumber()` để tìm dòng lỗi:

```cypher
LOAD CSV WITH HEADERS
FROM 'file:///customers.csv' AS row
WITH row, linenumber() AS line
WHERE row.externalId IS NULL
   OR trim(row.externalId) = ''
   OR toIntegerOrNull(row.sourceVersion) IS NULL
RETURN line, row;
```

Với Neo4j tự quản lý, file local thường phải nằm trong thư mục import được phép. Neo4j Aura không truy cập filesystem local của máy người dùng; hãy đặt file ở nơi instance có thể truy cập qua URL được hỗ trợ.

### Import Customer bằng MERGE

```cypher
LOAD CSV WITH HEADERS
FROM 'file:///customers.csv' AS row
WITH row,
     trim(row.sourceSystem) AS sourceSystem,
     trim(row.externalId) AS externalId,
     toIntegerOrNull(row.sourceVersion) AS sourceVersion
WHERE sourceSystem <> ''
  AND externalId <> ''
  AND sourceVersion IS NOT NULL
CALL (row, sourceSystem, externalId, sourceVersion) {
    MERGE (c:Customer {
        sourceSystem: sourceSystem,
        externalId: externalId
    })
    ON CREATE SET
        c.name = row.name,
        c.sourceVersion = sourceVersion,
        c.createdAt = datetime()
    WITH c, row, sourceVersion
    WHERE sourceVersion > coalesce(c.sourceVersion, -1)
    SET c.name = row.name,
        c.sourceVersion = sourceVersion,
        c.updatedAt = datetime()
} IN TRANSACTIONS OF 1000 ROWS;
```

Ví dụ dùng `sourceVersion` để không cho bản ghi cũ ghi đè bản ghi mới. Trước khi chạy, phải kiểm tra và báo cáo các dòng bị loại bởi điều kiện `WHERE`; không nên âm thầm bỏ qua dữ liệu thiếu khóa hoặc sai kiểu.

## 11. Chia batch và xử lý import lớn

Một câu `UNWIND $rows` quá lớn có thể giữ nhiều trạng thái transaction trong bộ nhớ. Với import lớn, chia dữ liệu thành các batch vừa phải và commit từng batch.

Ví dụ:

```cypher
UNWIND $rows AS row
CALL (row) {
    MERGE (c:Customer {
        sourceSystem: row.sourceSystem,
        externalId: row.externalId
    })
    SET c.name = row.name
} IN TRANSACTIONS OF 1000 ROWS;
```

`CALL { ... } IN TRANSACTIONS` tạo transaction con và commit theo batch. Kích thước mặc định là 1000 dòng; có thể điều chỉnh theo số thao tác mỗi dòng, kích thước property, thời gian transaction và giới hạn bộ nhớ.

Cú pháp `CALL (row) { ... }` là variable scope clause của các phiên bản Neo4j mới. Nếu phiên bản đang dùng chưa hỗ trợ, hãy dùng dạng importing `WITH row` bên trong `CALL { ... }` theo tài liệu Cypher của phiên bản đó.

Có một giới hạn quan trọng: `CALL { ... } IN TRANSACTIONS` chỉ chạy trong implicit transaction. Không bọc câu lệnh này bên trong explicit transaction do `@Transactional` hoặc một transaction driver đã mở. Với Neo4j Browser, dùng chế độ `:auto` cho câu lệnh phù hợp; với Java Driver, chạy bằng auto-commit `session.run(...)` thay vì `executeWrite(...)`.

Mỗi batch đã commit sẽ vẫn tồn tại nếu batch sau thất bại. Đây là lý do job cần có khả năng chạy lại an toàn. Khi chạy lại từ đầu, `MERGE` và constraint giúp các batch đã hoàn tất được khớp lại thay vì tạo node trùng.

### Batch bằng Spring Data Neo4j

Với batch được gửi từ ứng dụng, có thể dùng `Neo4jClient` để bind danh sách map vào tham số `$rows`:

```java
import java.util.List;
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerBatchWriter {

    private final Neo4jClient neo4jClient;

    public CustomerBatchWriter(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public void writeBatch(List<Map<String, Object>> rows) {
        neo4jClient.query("""
                UNWIND $rows AS row
                MERGE (c:Customer {
                    sourceSystem: row.sourceSystem,
                    externalId: row.externalId
                })
                SET c.name = row.name
                """)
                .bind(rows).to("rows")
                .run();
    }
}
```

Một coordinator chia danh sách thành các batch, sau đó gọi `writeBatch()` qua bean Spring cho từng batch. Không đặt một transaction ngoài bao trùm toàn bộ vòng lặp nếu mục tiêu là commit độc lập từng batch. Nếu cần bảo đảm mỗi lần gọi tạo transaction riêng, hãy để lời gọi đi qua proxy của bean writer hoặc dùng `TransactionTemplate` cho từng batch.

`Neo4jClient` tích hợp với transaction management của Spring và hỗ trợ bind tham số. Không nối trực tiếp giá trị CSV vào chuỗi Cypher; dùng parameter binding để tránh lỗi quoting và injection.

## 12. Có nên nhập song song không?

Sau khi quy trình tuần tự hoạt động ổn định, có thể cân nhắc `IN CONCURRENT TRANSACTIONS` để tăng throughput. Tuy nhiên, các batch song song có thể cùng cập nhật node nóng hoặc cùng tạo relationship đến một node có rất nhiều cạnh. Điều này làm tăng lock contention và nguy cơ deadlock.

Bắt đầu bằng batch tuần tự. Chỉ bật concurrency khi đã đo được nút thắt và có test dữ liệu đại diện. Khi nhập song song:

- Tạo trước các node danh mục được nhiều dòng tham chiếu, chẳng hạn Country hoặc Category.
- Phân vùng hoặc sắp xếp dữ liệu theo endpoint thường xuyên bị ghi để giảm tranh chấp.
- Chọn batch size dựa trên số thao tác mỗi dòng và mức độ tranh chấp.
- Dùng chính sách retry dành cho lỗi transient/deadlock; không retry lỗi dữ liệu cố định như vi phạm constraint.
- Theo dõi trạng thái batch và lưu lại lỗi theo dòng nguồn.

Các cú pháp `IN CONCURRENT TRANSACTIONS`, `ON ERROR RETRY` và `REPORT STATUS` phụ thuộc phiên bản Neo4j. Hãy kiểm tra Cypher Manual của phiên bản triển khai trước khi dùng.

## 13. Xử lý lỗi và chạy lại job

Một job import an toàn cần phân loại lỗi:

| Loại lỗi | Hành động |
|---|---|
| Thiếu business key | Đưa dòng vào báo cáo lỗi, không tạo node |
| Trùng key nhưng payload xung đột | Áp dụng quy tắc ưu tiên hoặc cách ly |
| Vi phạm uniqueness constraint | Kiểm tra identity, chuẩn hóa và dữ liệu hiện có |
| Sai kiểu dữ liệu | Sửa hoặc loại dòng nguồn theo chính sách |
| Thiếu endpoint khi nhập relationship | Đưa vào danh sách chờ hoặc chạy lại sau khi node được nhập |
| Deadlock/transient error | Retry batch theo giới hạn và backoff |
| Cypher syntax/authentication error | Dừng job và sửa cấu hình/query |

Nếu job dừng sau một số batch, có thể chạy lại toàn bộ file khi các bước ghi đã idempotent. Với dữ liệu rất lớn, có thể lưu checkpoint gồm file ID, checksum, batch range, trạng thái và thời điểm commit. Checkpoint giúp tiếp tục từ phần chưa hoàn thành; nó không thay thế tính idempotent vì batch có thể đã commit nhưng worker chưa kịp ghi checkpoint.

Không retry vô hạn. Lỗi constraint hoặc dữ liệu không hợp lệ sẽ không tự biến mất sau vài lần chạy lại.

## 14. Những trường hợp MERGE chưa đủ

`MERGE` giải quyết việc tìm hoặc tạo pattern theo identity. Nó không tự xử lý mọi yêu cầu đồng bộ:

- **Xóa dữ liệu đã biến mất khỏi nguồn:** MERGE không xóa node không còn xuất hiện. Cần tombstone, trạng thái inactive hoặc quy trình đối soát snapshot riêng.
- **Cập nhật bản ghi theo thứ tự sự kiện:** cần source version hoặc timestamp đáng tin cậy.
- **Một khóa có nhiều sự kiện:** mô hình hóa event riêng thay vì gộp vào một node.
- **Side effect ngoài Neo4j:** gửi email hoặc gọi payment không được rollback cùng transaction graph. Dùng outbox và consumer idempotent.
- **Payload thay đổi cùng một identity:** cần quy tắc nguồn nào có quyền ghi và cách xử lý version conflict.

Nếu nguồn là snapshot đầy đủ, có thể dùng một `importRunId` để đánh dấu node được nhìn thấy trong lần chạy. Sau khi import hoàn tất và xác minh đủ dữ liệu, job mới xử lý node không được đánh dấu. Không xóa ngay khi một batch kết thúc vì các batch sau có thể chưa được xử lý.

## 15. Kiểm thử tính idempotent

Một test chỉ xác nhận lần đầu tạo được node chưa đủ. Cần chạy lại cùng dữ liệu và so sánh trạng thái graph.

### Kiểm thử node

1. Tạo uniqueness constraint.
2. Import một batch Customer.
3. Đếm số node theo business key.
4. Chạy lại chính batch đó.
5. Đếm lại node và so sánh property.
6. Xác nhận không có node trùng và metadata tạo mới không bị thay đổi.

Query kiểm tra:

```cypher
MATCH (c:Customer {
    sourceSystem: $sourceSystem,
    externalId: $externalId
})
RETURN count(c) AS count;
```

Kỳ vọng `count = 1` sau cả lần đầu và lần chạy lại.

### Kiểm thử relationship

1. Tạo trước hai endpoint.
2. Import relationship theo stable pattern.
3. Chạy lại cùng batch.
4. Đếm relationship theo hai endpoint và event ID.
5. Xác nhận không phát sinh cạnh trùng.

### Kiểm thử cập nhật đến sai thứ tự

1. Import Customer với `sourceVersion = 5`.
2. Import lại version 5 với cùng payload.
3. Import version 4 sau đó.
4. Xác nhận node vẫn giữ version 5.
5. Import version 6 và xác nhận node được cập nhật.

### Kiểm thử concurrent import

Dùng hai transaction độc lập cùng import một business key. Sau khi cả hai hoàn tất, xác nhận constraint không cho phép hai node trùng. Kiểm tra ứng dụng xử lý conflict hoặc đọc lại node theo business key đúng cách.

Integration test nên chạy trên Neo4j thật hoặc Testcontainers/Test Harness tương thích. Test mock repository không chứng minh constraint và transaction locking thực sự hoạt động.

## 16. Quy trình triển khai thực tế

Một quy trình import có thể chạy lại an toàn thường đi theo thứ tự:

1. Xác định business key cho từng loại node và relationship/event.
2. Chuẩn hóa casing, khoảng trắng, Unicode và kiểu dữ liệu.
3. Kiểm tra dòng thiếu key, sai kiểu và duplicate trong file.
4. Làm sạch dữ liệu cũ và tạo uniqueness constraint.
5. Kiểm tra index và dùng `EXPLAIN` cho các pattern `MERGE`.
6. Nhập node theo từng loại trước.
7. Xác minh số lượng node và các khóa bị bỏ qua.
8. Nhập relationship bằng cách MATCH endpoint rồi MERGE cạnh.
9. Chia batch và ghi checkpoint nếu quy mô yêu cầu.
10. Chỉ bật import song song sau khi đo throughput và lock contention.
11. Chạy lại cùng dữ liệu để xác nhận không tạo duplicate.
12. Ghi báo cáo import, lỗi và version nguồn để có thể truy vết.

Hãy lưu lại checksum hoặc version của file nguồn. Điều đó giúp phân biệt “chạy lại cùng snapshot” với “nhập một snapshot mới có thay đổi”. Khi nguồn thay đổi, job cần chính sách update và delete rõ ràng; không nên coi mọi lần chạy lại là cùng một dữ liệu.

## 17. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `CREATE` cho job sẽ chạy lại | Mỗi lần chạy tạo thêm node/cạnh | Dùng `MERGE` theo khóa ổn định |
| Chỉ dùng `MERGE` mà không có constraint | Concurrent transactions có thể tạo duplicate | Tạo uniqueness/key constraint trước import |
| Đưa mọi property vào pattern `MERGE` | Property thay đổi làm pattern không khớp | Chỉ merge theo identity |
| Không chuẩn hóa khóa | Casing, whitespace hoặc kiểu dữ liệu khác nhau | Canonicalize và validate trước khi bind |
| Dùng `datetime()` hoặc counter ở mọi lần chạy | Tạo side effect khi replay | Dùng `ON CREATE` hoặc timestamp/version từ nguồn |
| Dòng trùng trong cùng file có payload khác nhau | Kết quả phụ thuộc thứ tự xử lý | Deduplicate hoặc quy định precedence |
| Nhập relationship cùng lúc tạo endpoint bằng full pattern | Có thể tạo node ngoài ý muốn | Nhập node trước, MATCH endpoint rồi MERGE relationship |
| Bỏ qua endpoint không tồn tại | `MATCH` không trả dòng nên cạnh không được tạo | Kiểm tra missing endpoint và báo cáo |
| Dùng `SET n = map` cho import tăng dần | Property không có trong map bị xóa | Dùng `SET n += map` khi cần cập nhật một phần |
| Dùng `CALL IN TRANSACTIONS` trong `@Transactional` | Subquery yêu cầu implicit transaction | Chạy bằng auto-commit/implicit transaction |
| Một transaction chứa toàn bộ file lớn | Transaction state có thể tiêu tốn nhiều bộ nhớ | Chia batch và commit từng phần |
| Bật concurrent import quá sớm | Lock contention và deadlock | Đo trước, phân vùng và retry có giới hạn |
| Retry lỗi constraint như transient | Lỗi dữ liệu lặp lại mãi | Phân loại lỗi trước khi retry |
| Xóa node vắng khỏi một batch | Batch chưa đại diện snapshot hoàn chỉnh | Chỉ đối soát delete sau khi toàn bộ snapshot hoàn tất |

## 18. Tự kiểm tra

1. Idempotent import khác upsert như thế nào?
2. Vì sao `MERGE` cần đi cùng uniqueness constraint?
3. Tại sao business key phải ổn định và được chuẩn hóa?
4. Vì sao không nên đưa `name` hoặc `status` vào pattern `MERGE`?
5. `ON CREATE` và `ON MATCH` giúp kiểm soát việc chạy lại như thế nào?
6. Làm sao tránh bản ghi nguồn cũ ghi đè dữ liệu mới?
7. Vì sao nên khử trùng dòng nguồn trước khi ghi?
8. Tại sao nhập node trước relationship?
9. Vì sao phải MATCH endpoint trước khi MERGE relationship?
10. `SET +=` khác `SET =` như thế nào?
11. `CALL { ... } IN TRANSACTIONS` có giới hạn transaction nào?
12. Vì sao batch đã commit vẫn cần được thiết kế để chạy lại?
13. Khi nào nên bật concurrent transactions?
14. Làm thế nào kiểm thử cùng một file chạy hai lần mà graph không tăng node/cạnh trùng?

Hãy tạo Customer với khóa `sourceSystem + externalId`, tạo composite uniqueness constraint và nhập dữ liệu bằng `MERGE`. Chạy cùng batch hai lần rồi xác nhận chỉ có một node cho mỗi khóa. Tiếp theo nhập Order, sau đó tạo `PLACED` relationship bằng cách MATCH hai endpoint và MERGE cạnh. Thử đưa vào dòng trùng, khóa có khoảng trắng, version cũ và endpoint không tồn tại; ghi nhận cách job xử lý từng trường hợp.

## Tài liệu tham khảo

- [Neo4j Data Ingestion Guide — Optimized Cypher patterns for ingestion](https://neo4j.com/docs/data-ingestion-guide/best-practices/optimized-cypher/)
- [Neo4j Data Ingestion Guide — Schema and indexes](https://neo4j.com/docs/data-ingestion-guide/best-practices/schema-and-indexes/)
- [Neo4j Data Ingestion Guide — LOAD CSV](https://neo4j.com/docs/data-ingestion-guide/ingestion-methods/load-csv/)
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Spring Data Neo4j — Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Spring Data Neo4j — FAQ](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
