# Uniqueness constraint cho khóa nghiệp vụ

## Mục tiêu bài học

Trong một ứng dụng Spring Data Neo4j (SDN), mỗi node thường có một định danh để framework quản lý vòng đời entity. Tuy nhiên, nghiệp vụ có thể yêu cầu một thuộc tính khác phải duy nhất: mã khách hàng từ hệ thống ERP, mã đơn hàng bên ngoài, số đăng ký doanh nghiệp hoặc mã sản phẩm theo nhà cung cấp.

Đó là **khóa nghiệp vụ** (business key). Nếu chỉ kiểm tra trước khi tạo node trong Java, hai request đồng thời vẫn có thể cùng thấy dữ liệu chưa tồn tại rồi tạo hai node trùng nhau. Neo4j cần một uniqueness constraint để bảo vệ quy tắc này ngay tại database.

Bài học này hướng dẫn cách chọn khóa nghiệp vụ, tạo uniqueness constraint đơn và composite, phân biệt constraint với `@Id` và index, chuẩn bị dữ liệu trước khi triển khai constraint, kết hợp `MERGE` với constraint, và kiểm thử các tình huống ghi đồng thời trong ứng dụng SDN.

## 1. Khóa nghiệp vụ là gì?

Khóa nghiệp vụ là một hoặc nhiều thuộc tính giúp nhận diện một đối tượng theo quy tắc của miền nghiệp vụ. Ví dụ:

| Đối tượng | Khóa nghiệp vụ có thể dùng |
|---|---|
| Khách hàng trong một hệ thống | `customerCode` |
| Sản phẩm theo nhà cung cấp | `supplierId + supplierProductCode` |
| Khách hàng đồng bộ từ nhiều nguồn | `sourceSystem + externalId` |
| Tài khoản trong một tenant | `tenantId + accountNumber` |
| Đơn hàng từ hệ thống thương mại | `sourceSystem + externalOrderId` |

Một khóa nghiệp vụ tốt cần có quy tắc rõ ràng:

- Xác định chính xác phạm vi duy nhất: toàn hệ thống, theo tenant hay theo nguồn dữ liệu.
- Có giá trị khi tạo node và không bị bỏ trống.
- Ổn định trong vòng đời đối tượng.
- Có quy tắc chuẩn hóa nhất quán trước khi lưu.
- Được mọi luồng ghi dữ liệu tuân thủ, kể cả import, batch và custom Cypher.

Không nên chọn tên hiển thị, địa chỉ hoặc trạng thái làm khóa nếu chúng có thể thay đổi hoặc có thể trùng. Nếu mã từ hai hệ thống nguồn có thể giống nhau, hãy đưa nguồn vào khóa composite thay vì giả định mã đó duy nhất toàn graph.

## 2. Phân biệt @Id, khóa nghiệp vụ và uniqueness constraint

Ba khái niệm này có liên quan nhưng không thay thế nhau:

| Thành phần | Vai trò |
|---|---|
| `@Id` của SDN | Xác định property mà SDN dùng làm định danh persistence của entity |
| Khóa nghiệp vụ | Xác định đối tượng theo quy tắc nghiệp vụ, ví dụ mã khách hàng |
| Uniqueness constraint của Neo4j | Bắt buộc giá trị hoặc tổ hợp giá trị không trùng trong phạm vi label/type được khai báo |

Ví dụ entity có ID nội bộ do Neo4j sinh và mã bên ngoài do hệ thống ERP cấp:

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

    // Constructor, getter và setter được lược bỏ.
}
```

Ở đây:

- `id` là định danh persistence của entity trong SDN.
- `sourceSystem + externalId` là khóa nghiệp vụ.
- Uniqueness constraint sẽ bảo vệ tổ hợp `sourceSystem + externalId` ở Neo4j.

Gắn `@Id` lên một field không tự tạo uniqueness constraint trong database. Tương tự, việc khai báo một field có tên `externalId` không làm giá trị của nó tự động duy nhất. Constraint phải được tạo trong schema Neo4j.

Nếu ứng dụng dùng chính business key làm `@Id`, vẫn cần tạo constraint tương ứng trong database để bảo vệ dữ liệu trước các đường ghi khác và các transaction đồng thời.

## 3. Tạo uniqueness constraint cho một property

Giả sử mỗi node `Customer` phải có một `customerCode` duy nhất. Tạo constraint:

```cypher
CREATE CONSTRAINT customer_code_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerCode IS UNIQUE;
```

Giải thích:

- `customer_code_unique` là tên constraint.
- `FOR (c:Customer)` giới hạn phạm vi vào các node mang label `Customer`.
- `REQUIRE c.customerCode IS UNIQUE` yêu cầu các giá trị `customerCode` hiện diện trên các node thuộc phạm vi đó không được trùng.

Sau khi constraint tồn tại, thao tác tạo hoặc cập nhật node làm vi phạm tính duy nhất sẽ thất bại. Quy tắc được database áp dụng cho mọi luồng ghi, không chỉ các thao tác đi qua repository.

Có thể kiểm tra constraint:

```cypher
SHOW CONSTRAINTS;
```

Dùng tên constraint có ý nghĩa và ổn định để migration dễ kiểm tra, triển khai và rollback. Tên constraint phải duy nhất trong phạm vi schema object của database.

### Phạm vi của uniqueness constraint

Constraint trên `Customer.customerCode` chỉ áp dụng cho các node có label `Customer`. Một node chỉ mang label `Supplier` có thể có cùng giá trị ở property `customerCode` mà không vi phạm constraint đó.

Nếu một node mang cả label `Customer` và label khác, nó vẫn thuộc phạm vi constraint vì có label `Customer`.

Uniqueness constraint cũng không có nghĩa là property bắt buộc phải tồn tại. Đây là điểm cần đặc biệt chú ý khi khóa nghiệp vụ không được phép rỗng.

## 4. Tạo composite uniqueness constraint

Một số khóa chỉ duy nhất khi kết hợp nhiều thuộc tính. Ví dụ, mã khách hàng từ hệ thống nguồn chỉ duy nhất trong từng hệ thống, nên cần cặp `sourceSystem + externalId`.

```cypher
CREATE CONSTRAINT customer_source_external_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.sourceSystem, c.externalId) IS UNIQUE;
```

Constraint này cho phép:

| sourceSystem | externalId | Kết quả |
|---|---|---|
| `ERP_A` | `C-100` | Hợp lệ |
| `ERP_A` | `C-101` | Hợp lệ |
| `ERP_B` | `C-100` | Hợp lệ |
| `ERP_A` | `C-100` lần nữa | Vi phạm uniqueness |

Tổ hợp property mới là khóa. Mỗi property riêng lẻ vẫn có thể trùng.

Composite constraint hữu ích trong các mô hình multi-tenant, đồng bộ dữ liệu từ nhiều nguồn, hoặc khi mã chỉ duy nhất trong một phạm vi nghiệp vụ.

### Khi nào dùng constraint đơn, khi nào dùng composite?

- Dùng constraint đơn nếu một property đã duy nhất trong phạm vi label.
- Dùng composite constraint nếu quy tắc nghiệp vụ xác định duy nhất bởi tổ hợp nhiều property.
- Không tạo nhiều constraint đơn nếu yêu cầu thật sự là tổ hợp duy nhất; hai constraint đơn sẽ cấm trùng từng property riêng lẻ và làm thay đổi quy tắc nghiệp vụ.
- Không đưa property mô tả hoặc mutable vào composite key chỉ để tránh trùng tạm thời.

Ví dụ, nếu hai tenant có thể có cùng `accountNumber`, constraint đơn trên `accountNumber` là quá chặt. Constraint đúng là `(tenantId, accountNumber)`.

## 5. Uniqueness không đồng nghĩa với property bắt buộc

Neo4j property uniqueness constraint chỉ kiểm tra các node có đủ property được khai báo. Với composite constraint, node phải có tất cả property trong tổ hợp thì mới thuộc phạm vi kiểm tra uniqueness.

Ví dụ:

```cypher
CREATE CONSTRAINT customer_source_external_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.sourceSystem, c.externalId) IS UNIQUE;
```

Các node sau có thể không bị constraint kiểm tra vì thiếu một hoặc cả hai property:

```cypher
CREATE (:Customer {sourceSystem: 'ERP_A'});
CREATE (:Customer {externalId: 'C-100'});
CREATE (:Customer {name: 'Khách chưa đồng bộ'});
```

Nếu nghiệp vụ yêu cầu mọi Customer phải có cả `sourceSystem` và `externalId`, có hai hướng:

1. Dùng node key constraint nếu Neo4j edition và phiên bản hỗ trợ. Node key bảo đảm đồng thời property tồn tại và tổ hợp giá trị duy nhất.
2. Nếu dùng property uniqueness constraint, xác thực hai property bắt buộc ở mọi luồng ghi; có thể bổ sung property existence constraint khi edition hỗ trợ.

Node key constraint:

```cypher
CREATE CONSTRAINT customer_business_key IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.sourceSystem, c.externalId) IS NODE KEY;
```

Node key constraint là tính năng Enterprise. Property existence constraint cũng phụ thuộc edition. Hãy kiểm tra edition của Neo4j trước khi dùng.

Với Neo4j Community không có node key constraint, property uniqueness constraint vẫn bảo vệ các giá trị hiện diện. Tuy nhiên, ứng dụng cần bảo đảm mọi node Customer đều có đủ hai property khóa nghiệp vụ. Validation trong service cần được áp dụng nhất quán cho repository, import job và custom Cypher.

## 6. Chuẩn hóa khóa trước khi lưu

Uniqueness constraint so sánh các giá trị được lưu trong Neo4j. Nó không tự hiểu hai chuỗi khác nhau về chữ hoa/thường hoặc khoảng trắng là cùng một định danh theo quy tắc nghiệp vụ của ứng dụng.

Ví dụ, nếu quy tắc ứng dụng xem mã `ab-100` và `AB-100` là một mã, hãy chuẩn hóa trước khi ghi:

```java
import java.util.Locale;

public String normalizeExternalId(String value) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException(
                "externalId must not be blank");
    }

    return value.trim().toUpperCase(Locale.ROOT);
}
```

Đây chỉ là ví dụ cho mã định danh được quy định không phân biệt hoa thường. Hãy dùng quy tắc chuẩn hóa phù hợp với loại khóa thực tế; không chuyển mọi chuỗi sang chữ hoa một cách máy móc.

Với email, nếu chính sách nghiệp vụ xem địa chỉ email là không phân biệt hoa thường, có thể lưu thêm property canonical như `emailCanonical` và tạo uniqueness constraint trên property đó. Cần thống nhất quy tắc xử lý khoảng trắng, Unicode và casing giữa mọi service.

Ví dụ:

```cypher
CREATE CONSTRAINT customer_email_canonical_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.emailCanonical IS UNIQUE;
```

Có thể giữ email gốc để hiển thị và dùng `emailCanonical` để tra cứu identity. Điều quan trọng là mọi luồng ghi phải tính canonical value theo cùng một quy tắc.

## 7. Uniqueness constraint được hỗ trợ bởi index

Property uniqueness constraint được Neo4j hỗ trợ bằng range index. Index này giúp database tìm nhanh giá trị cần kiểm tra và hỗ trợ các truy vấn tìm kiếm theo khóa.

Điều này có hai ý nghĩa:

- Constraint bảo vệ tính toàn vẹn dữ liệu.
- Backing index giúp kiểm tra uniqueness và truy vấn theo property hiệu quả hơn.

Không cần tạo thêm một range index trùng chính xác label/property đã được unique constraint bảo vệ. Việc tạo index cùng loại và cùng schema có thể xung đột với backing index của constraint.

Có thể kiểm tra index hiện có:

```cypher
SHOW INDEXES;
```

Nếu query tìm node theo business key, planner có thể sử dụng index tương ứng. Dùng `EXPLAIN` để xem kế hoạch mà không thực thi query, hoặc `PROFILE` để đo thực thi trên dữ liệu đại diện:

```cypher
EXPLAIN
MATCH (c:Customer {
    sourceSystem: $sourceSystem,
    externalId: $externalId
})
RETURN c;
```

Index giúp tăng tốc tìm kiếm, nhưng constraint mới là phần đảm bảo uniqueness. Một index thông thường không ngăn hai node có cùng giá trị.

## 8. Chuẩn bị dữ liệu trước khi tạo constraint

Nếu graph đã có dữ liệu trùng, lệnh tạo uniqueness constraint sẽ thất bại. Trước khi triển khai, cần kiểm tra dữ liệu hiện tại.

Tìm các khóa đơn bị trùng:

```cypher
MATCH (c:Customer)
WHERE c.customerCode IS NOT NULL
WITH c.customerCode AS customerCode,
     count(*) AS occurrences
WHERE occurrences > 1
RETURN customerCode, occurrences
ORDER BY occurrences DESC;
```

Tìm các tổ hợp composite bị trùng:

```cypher
MATCH (c:Customer)
WHERE c.sourceSystem IS NOT NULL
  AND c.externalId IS NOT NULL
WITH c.sourceSystem AS sourceSystem,
     c.externalId AS externalId,
     count(*) AS occurrences
WHERE occurrences > 1
RETURN sourceSystem, externalId, occurrences
ORDER BY occurrences DESC;
```

Tìm node thiếu property khóa:

```cypher
MATCH (c:Customer)
WHERE c.sourceSystem IS NULL
   OR c.externalId IS NULL
RETURN c;
```

Sau khi tìm thấy dữ liệu vi phạm, không nên xóa node trùng một cách tự động. Các node có thể đang có relationship khác nhau. Quy trình xử lý nên:

1. Xác định node chuẩn cần giữ.
2. So sánh property và nguồn dữ liệu.
3. Chuyển hoặc hợp nhất relationship sang node chuẩn nếu cần.
4. Xử lý các khác biệt dữ liệu theo quy tắc nghiệp vụ.
5. Xóa node dư sau khi đã bảo toàn quan hệ.
6. Chạy lại truy vấn kiểm tra duplicate và missing property.
7. Tạo constraint và xác nhận constraint ở trạng thái hoạt động.

Tạo constraint có thể cần quét dữ liệu hiện có và mất thời gian tùy kích thước graph. Hãy thực hiện qua migration có kiểm soát, đánh giá ảnh hưởng lên môi trường đang chạy và chuẩn bị phương án phục hồi nếu migration thất bại.

## 9. Quản lý constraint bằng migration

Với Spring Data Neo4j hiện đại, schema database nên được quản lý riêng bằng migration. Các annotation `@Index`, `@CompositeIndex` và `@Required` thuộc cơ chế cũ của Neo4j-OGM đã bị loại khỏi SDN hiện đại; không dùng chúng để mong framework tự tạo uniqueness constraint.

Một migration có thể chứa:

```cypher
CREATE CONSTRAINT customer_source_external_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.sourceSystem, c.externalId) IS UNIQUE;
```

Có thể dùng công cụ migration cho Neo4j như Neo4j Migrations hoặc Liquigraph để version hóa thay đổi schema. Quy trình triển khai thường gồm:

- Migration kiểm tra và làm sạch dữ liệu.
- Migration tạo constraint.
- Ứng dụng triển khai code dựa trên business key.
- Kiểm tra trạng thái constraint sau triển khai.

Không nên để mỗi lần ứng dụng khởi động tự suy ra và thay đổi schema production từ entity model. Migration tường minh giúp review được thay đổi, kiểm soát thứ tự triển khai và phối hợp nhiều phiên bản ứng dụng.

Nếu cần bỏ constraint trong migration rollback:

```cypher
DROP CONSTRAINT customer_source_external_unique IF EXISTS;
```

Chỉ drop khi đã hiểu tác động. Trong khoảng thời gian constraint bị gỡ, các luồng ghi có thể tạo dữ liệu trùng. Nếu migration cần đổi business key, hãy thiết kế giai đoạn chuyển tiếp để constraint cũ và mới cùng bảo vệ dữ liệu khi có thể.

## 10. Kết hợp MERGE với uniqueness constraint

`MERGE` tìm pattern đã tồn tại hoặc tạo pattern nếu chưa có. Với node business key, dùng đúng property đã được constraint bảo vệ:

```cypher
MERGE (c:Customer {
    sourceSystem: $sourceSystem,
    externalId: $externalId
})
ON CREATE SET
    c.createdAt = datetime()
SET
    c.name = $name,
    c.updatedAt = datetime()
RETURN c;
```

Trong ví dụ:

- `sourceSystem + externalId` là identity.
- `createdAt` chỉ được thiết lập khi node mới được tạo.
- `name` và `updatedAt` được cập nhật cho cả node mới lẫn node đã tồn tại.

Không đưa property có thể thay đổi như `name`, `status` hoặc `updatedAt` vào pattern identity. Nếu pattern chứa cả khóa nghiệp vụ và thuộc tính mutable, lần gọi sau có thể không khớp node cũ khi thuộc tính thay đổi, khiến query cố tạo pattern khác và có thể vi phạm constraint.

### MERGE một mình chưa bảo đảm uniqueness dưới concurrent writes

Một quy trình `MATCH` rồi `CREATE` có race condition: hai transaction có thể cùng không tìm thấy node rồi cùng tạo mới. `MERGE` diễn tả tìm-hoặc-tạo, nhưng để bảo đảm node business key không bị tạo trùng khi có ghi đồng thời, cần uniqueness constraint trên đúng property hoặc tổ hợp property trong pattern.

Khi constraint tồn tại, Neo4j dùng backing index để bảo vệ việc tạo node theo khóa. Nếu thao tác ghi vi phạm một constraint khác hoặc dữ liệu đầu vào không tuân thủ hợp đồng, query vẫn có thể thất bại. Ứng dụng cần xử lý lỗi theo nghiệp vụ và không giả định mọi lỗi ghi đều là transient.

## 11. Tích hợp business key vào repository SDN

Entity và repository có thể được khai báo như sau:

```java
import java.util.Optional;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.repository.Neo4jRepository;

@Node("Customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String sourceSystem;

    private String externalId;

    private String name;

    // Constructor, getter và setter được lược bỏ.
}

public interface CustomerRepository
        extends Neo4jRepository<Customer, Long> {

    Optional<Customer> findBySourceSystemAndExternalId(
            String sourceSystem,
            String externalId);

    boolean existsBySourceSystemAndExternalId(
            String sourceSystem,
            String externalId);
}
```

Derived query dùng property Java của entity. Uniqueness constraint trong Neo4j dùng tên property được lưu trong graph; nếu entity ánh xạ property bằng `@Property`, hãy bảo đảm migration sử dụng đúng tên lưu trữ.

Vì business key được bảo vệ bởi composite constraint, repository method có thể biểu diễn kết quả bằng `Optional<Customer>` theo hợp đồng tối đa một node. Nếu dữ liệu cũ hoặc một luồng ghi khác tạo duplicate trước khi constraint tồn tại, method có thể gặp lỗi cardinality khi trả về nhiều node. Không dùng kiểu trả về đơn để che giấu dữ liệu trùng.

### Custom query dùng MERGE

Có thể khai báo upsert bằng `@Query`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends Neo4jRepository<Customer, Long> {

    @Query("MERGE (c:Customer {sourceSystem: $sourceSystem, " +
           "externalId: $externalId}) " +
           "ON CREATE SET c.createdAt = datetime() " +
           "SET c.name = $name, c.updatedAt = datetime() " +
           "RETURN c")
    Customer upsert(
            @Param("sourceSystem") String sourceSystem,
            @Param("externalId") String externalId,
            @Param("name") String name);
}
```

Query này cần uniqueness constraint trên đúng tổ hợp `sourceSystem + externalId`. Cũng cần validate các tham số khóa trước khi gọi query vì `MERGE` không chấp nhận property null trong pattern.

Nếu một nghiệp vụ gồm nhiều thao tác graph cần thành công hoặc rollback cùng nhau, đặt transaction boundary ở service bằng `@Transactional`. Transaction giúp nhóm các thay đổi, còn uniqueness constraint bảo vệ khóa nghiệp vụ; hai cơ chế giải quyết hai mục tiêu khác nhau.

## 12. Xử lý khi hai request ghi cùng business key

Giả sử hai request cùng gửi:

```text
sourceSystem = ERP_A
externalId   = C-100
```

Nếu cả hai gọi upsert theo cùng một pattern và composite uniqueness constraint đã tồn tại, database bảo vệ để không tạo hai node Customer có cùng tổ hợp khóa.

Ứng dụng nên xác định rõ cách xử lý:

- Nếu hai request có cùng business key và payload tương đương, có thể trả về cùng node đã được upsert.
- Nếu payload khác nhau, cần quy định nguồn dữ liệu nào được quyền cập nhật hoặc request nào mới hơn.
- Nếu thao tác ghi vi phạm constraint, đọc lại node theo business key để xác định trạng thái hiện tại hoặc trả conflict phù hợp.
- Nếu lỗi được xác định là transient, chỉ retry theo chính sách có giới hạn và bảo đảm thao tác idempotent.

Không dùng kiểm tra tồn tại ở service làm hàng rào duy nhất:

```java
if (!customerRepository
        .existsBySourceSystemAndExternalId(source, externalId)) {
    customerRepository.save(customer);
}
```

Đoạn code trên có thể hoạt động trong tải tuần tự nhưng không an toàn trước hai request đồng thời. Cả hai có thể cùng nhận `false` rồi cùng lưu. Constraint ở database mới là lớp bảo vệ cuối cùng.

## 13. Phân biệt uniqueness constraint với index thông thường

| Đặc điểm | Index thông thường | Uniqueness constraint |
|---|---|---|
| Tăng tốc tìm kiếm theo property | Có | Có, thông qua backing index |
| Ngăn giá trị trùng | Không | Có |
| Dùng làm rào chắn cho concurrent writes | Không | Có |
| Có thể tạo index trùng schema với unique constraint | Không nên | Constraint đã có backing index |
| Phù hợp | Tìm kiếm/filter theo property không cần duy nhất | Khóa nghiệp vụ cần duy nhất |

Không tạo unique constraint chỉ vì một property thường xuyên được tìm kiếm. Nếu property được phép trùng, dùng index phù hợp với truy vấn. Ngược lại, nếu nghiệp vụ yêu cầu duy nhất, index thông thường không đủ.

## 14. Kiểm thử uniqueness constraint

Nên kiểm thử ở hai cấp độ: schema constraint và hành vi repository.

### Kiểm thử constraint ở database

Sau khi tạo constraint, thử tạo hai node có cùng business key:

```cypher
CREATE (:Customer {
    sourceSystem: 'ERP_A',
    externalId: 'C-100'
});

CREATE (:Customer {
    sourceSystem: 'ERP_A',
    externalId: 'C-100'
});
```

Lệnh thứ hai phải thất bại vì vi phạm composite uniqueness constraint.

Thử cùng `externalId` nhưng khác `sourceSystem`:

```cypher
CREATE (:Customer {
    sourceSystem: 'ERP_B',
    externalId: 'C-100'
});
```

Lệnh này hợp lệ vì tổ hợp hai property khác nhau.

### Kiểm thử repository

Với SDN, integration test nên xác nhận:

1. Lưu một Customer với business key hợp lệ thành công.
2. Tìm lại bằng derived query trả đúng node.
3. Upsert cùng business key không tạo node thứ hai.
4. Thay đổi `name` không tạo node mới vì name không nằm trong pattern identity.
5. Hai tenant hoặc nguồn dữ liệu khác nhau được phép dùng cùng external ID nếu composite key cho phép.
6. Thiếu property khóa bị từ chối bởi validation hoặc key/existence constraint.
7. Hai transaction độc lập ghi cùng business key không tạo duplicate.
8. Dữ liệu duplicate hiện có khiến migration constraint thất bại cho đến khi được xử lý.

Khung test repository:

```java
@DataNeo4jTest
class CustomerBusinessKeyTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldFindCustomerByCompositeBusinessKey() {
        // Lưu Customer với sourceSystem = ERP_A, externalId = C-100.
        // Gọi findBySourceSystemAndExternalId("ERP_A", "C-100").
        // Xác nhận đúng Customer được trả về.
    }

    @Test
    void shouldUpsertWithoutCreatingDuplicate() {
        // Gọi upsert hai lần với cùng business key.
        // Dùng Cypher count để xác nhận chỉ có một node Customer.
    }
}
```

Đối với test concurrency, cần dùng hai transaction độc lập hoặc hai subscription/connection phù hợp. Không bọc toàn bộ test trong một transaction duy nhất rồi gọi hai thao tác tuần tự, vì như vậy không mô phỏng được race condition.

## 15. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ `@Id` tự tạo business uniqueness | Nhầm mapping identity với database constraint | Tạo uniqueness constraint riêng |
| Dùng index thường cho khóa nghiệp vụ | Index không ngăn giá trị trùng | Dùng property uniqueness constraint |
| Dùng constraint đơn trong khi khóa có phạm vi tenant | Phạm vi duy nhất quá rộng | Dùng composite constraint |
| Dùng composite constraint nhưng bỏ qua property null | Node thiếu một property có thể nằm ngoài phạm vi uniqueness | Validation hoặc node key/existence constraint |
| Đưa tên hoặc trạng thái vào pattern `MERGE` | Property mutable làm thay đổi identity | Chỉ dùng khóa ổn định trong pattern |
| Chỉ dùng `existsBy...` trước khi save | Race condition giữa check và create | Dùng `MERGE` cùng uniqueness constraint |
| Tạo constraint khi graph đang có duplicate | Migration thất bại | Phát hiện, hợp nhất và làm sạch dữ liệu trước |
| Tạo thêm index trùng với backing index | Constraint đã tạo index tương ứng | Kiểm tra `SHOW INDEXES` trước |
| Dùng `@Index(unique = true)` trong SDN hiện đại | Annotation thuộc cơ chế cũ Neo4j-OGM | Quản lý schema bằng migration Cypher |
| Không chuẩn hóa khóa | Giá trị khác casing/khoảng trắng có thể được xem là khác nhau | Áp dụng canonicalization theo quy tắc nghiệp vụ |
| Bắt mọi lỗi ghi rồi retry | Constraint violation cố định không tự biến mất | Phân loại lỗi và chỉ retry transient failures |

## 16. Tự kiểm tra

1. Khóa nghiệp vụ khác `@Id` của SDN như thế nào?
2. Vì sao một business key cần uniqueness constraint ở database?
3. Khi nào dùng uniqueness constraint đơn và khi nào dùng composite?
4. Composite uniqueness constraint có kiểm tra node thiếu một property không?
5. Node key constraint khác property uniqueness constraint ở điểm nào?
6. Vì sao uniqueness constraint vừa bảo vệ dữ liệu vừa có backing index?
7. Vì sao không nên tạo index thông thường trùng với backing index của constraint?
8. Vì sao `MERGE` cần đi cùng uniqueness constraint khi có concurrent writes?
9. Vì sao property mutable không nên nằm trong pattern identity?
10. Cần kiểm tra dữ liệu nào trước khi tạo constraint trên graph đang hoạt động?
11. Tại sao SDN hiện đại khuyến nghị quản lý constraint bằng migration thay vì annotation entity?
12. Làm thế nào kiểm thử hai transaction cùng ghi một business key?

Hãy tạo entity `Customer` có ID nội bộ và business key `sourceSystem + externalId`. Tạo composite uniqueness constraint, viết repository finder và upsert bằng `MERGE`. Thử tạo hai khách hàng cùng khóa trong cùng nguồn dữ liệu, sau đó thử cùng external ID từ hai nguồn khác nhau. Tiếp theo kiểm tra trường hợp thiếu một property, chuẩn hóa khóa theo quy tắc nghiệp vụ và chạy hai transaction độc lập để xác nhận graph không có node trùng.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Cypher Manual — Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual — Constraint syntax](https://neo4j.com/docs/cypher-manual/current/schema/syntax/)
- [Spring Data Neo4j — Migrating from SDN+OGM](https://docs.spring.io/spring-data/neo4j/reference/appendix/migrating.html)
