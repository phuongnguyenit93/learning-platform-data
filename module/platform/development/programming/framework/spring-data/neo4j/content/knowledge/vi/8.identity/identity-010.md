# Đổi khóa nghiệp vụ, dữ liệu nhập ngoài và nguy cơ tạo node trùng

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vì sao khóa nghiệp vụ có thể thay đổi và ảnh hưởng của việc thay đổi khóa được dùng làm `@Id`.
- Phân biệt định danh của node với mã do hệ thống bên ngoài gửi đến.
- Thiết kế khóa có namespace khi nhập dữ liệu từ nhiều nguồn.
- Dùng `MERGE`, tham số và unique constraint để nhập dữ liệu theo cách có thể chạy lặp lại.
- Phát hiện, đánh giá và xử lý node trùng mà không làm mất các relationship đang tồn tại.

## 1. Khóa nghiệp vụ và định danh của node

Một entity trong Spring Data Neo4j cần một định danh để ánh xạ đối tượng Java với node trong Neo4j. Định danh thường được đánh dấu bằng `@Id`. Giá trị này giúp SDN tìm đúng node khi đọc hoặc cập nhật dữ liệu.

Khóa nghiệp vụ (business key) là mã có ý nghĩa với quy trình của tổ chức, chẳng hạn mã khách hàng, mã hợp đồng hoặc mã tài khoản. Khóa nghiệp vụ có thể được dùng làm định danh nếu nó ổn định và duy nhất trong phạm vi ứng dụng. Tuy nhiên, một số mã nghiệp vụ có thể thay đổi do sáp nhập, chuẩn hóa dữ liệu, chuyển hệ thống hoặc thay đổi quy tắc đánh số.

Ví dụ, một khách hàng ban đầu có mã `CUS-0018`, sau đó được đổi thành `CUS-1042`. Nếu mã khách hàng đồng thời là `@Id`, việc đổi mã có nghĩa là thay đổi định danh mà SDN dùng để tìm node.

Cần phân biệt ba loại giá trị:

| Loại | Ví dụ | Vai trò |
| --- | --- | --- |
| Định danh kỹ thuật ổn định | UUID | Nhận diện node xuyên suốt vòng đời dữ liệu |
| Khóa nghiệp vụ | `CUS-0018` | Mã người dùng hoặc hệ thống nghiệp vụ nhìn thấy |
| ID từ nguồn ngoài | `ERP-77` | Mã do một hệ thống tích hợp gửi đến; có thể chỉ duy nhất trong hệ thống nguồn |

Không nên mặc định ba giá trị này là một. Khi một mã có thể thay đổi, dùng nó làm định danh duy nhất của node sẽ khiến việc đổi mã trở thành một thao tác thay đổi identity, có ảnh hưởng đến ánh xạ, tham chiếu và tích hợp.

## 2. Chọn định danh ổn định khi khóa nghiệp vụ có thể đổi

Nếu mã nghiệp vụ có khả năng thay đổi, cách thiết kế thường an toàn hơn là dùng một ID kỹ thuật ổn định làm `@Id`, còn business key được lưu như property có unique constraint.

Ví dụ:

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;

@Node("Customer")
public class Customer {

    @Id
    private String id; // UUID ổn định

    @Property("customerCode")
    private String customerCode;

    @Version
    private Long version;

    private String displayName;

    protected Customer() {
    }

    public Customer(
            String id,
            String customerCode,
            String displayName) {
        this.id = id;
        this.customerCode = customerCode;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getCustomerCode() {
        return customerCode;
    }
}
```

Ở đây:

- `id` nhận diện node trong suốt vòng đời của entity.
- `customerCode` là property nghiệp vụ có thể được đổi theo quy trình.
- `version` hỗ trợ SDN nhận biết trạng thái entity và optimistic locking.

Unique constraint cho mã khách hàng:

```cypher
CREATE CONSTRAINT customer_code_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerCode IS UNIQUE
```

Khi khách hàng đổi mã, ứng dụng cập nhật `customerCode` trên cùng node. Giá trị `id` không thay đổi, do đó các relationship đang trỏ đến node vẫn kết nối với cùng thực thể.

Nếu hệ thống bắt buộc dùng business key làm `@Id`, hãy xem việc đổi khóa như một quy trình migration identity có kiểm soát. Không nên tạo một object mới mang mã mới rồi giả định rằng `save()` sẽ tự hiểu đó là cùng khách hàng. Với SDN, giá trị `@Id` mới có thể được xem là định danh của một entity khác; kết quả có thể là node mới hoặc lỗi khi trạng thái/version không khớp. Cần xác định rõ node hiện tại, kiểm tra khóa đích chưa được sử dụng, cập nhật định danh bằng quy trình có transaction và tải lại entity sau migration.

## 3. Khi dữ liệu đến từ hệ thống bên ngoài

Dữ liệu nhập từ ERP, CRM, nền tảng thanh toán hoặc tệp CSV thường có mã riêng. Một mã chỉ duy nhất trong hệ thống nguồn chưa chắc duy nhất trong toàn bộ đồ thị.

Ví dụ:

- ERP có khách hàng mã `10025`.
- CRM cũng có khách hàng mã `10025`.
- Hai bản ghi này có thể là hai khách hàng khác nhau, hoặc là cùng một khách hàng được biểu diễn trong hai hệ thống.

Nếu chỉ lưu `externalId = "10025"` và dùng property đó làm khóa toàn cục, dữ liệu có thể bị nhập nhầm hoặc ghi đè.

### 3.1. Đưa nguồn dữ liệu vào phạm vi định danh

Một khóa ngoài nên bao gồm namespace của nguồn, chẳng hạn `sourceSystem` cùng `externalId`. Với hệ thống nhiều tenant, phạm vi có thể cần thêm `tenantId`.

```text
sourceSystem = "ERP"
externalId   = "10025"
tenantId     = "tenant-a"
```

Đối với SDN, entity vẫn có thể dùng một ID kỹ thuật ổn định (chẳng hạn UUID) làm `@Id`, trong khi `sourceSystem` và `externalId` biểu diễn identity của bản ghi ở hệ thống nguồn. Tạo unique constraint trên các property thành phần để Neo4j bảo vệ tính duy nhất của khóa nguồn:

```cypher
CREATE CONSTRAINT customer_external_identity IF NOT EXISTS
FOR (c:ImportedCustomer)
REQUIRE (c.sourceSystem, c.externalId) IS UNIQUE
```

Nếu dữ liệu được phân vùng theo tenant, đưa `tenantId` vào constraint:

```cypher
CREATE CONSTRAINT customer_tenant_external_identity IF NOT EXISTS
FOR (c:ImportedCustomer)
REQUIRE (c.tenantId, c.sourceSystem, c.externalId) IS UNIQUE
```

Nếu ứng dụng cần một khóa tổng hợp dễ tra cứu, hãy thống nhất cách tạo nó để cùng một bộ giá trị luôn tạo ra cùng một khóa. Nếu ghép chuỗi bằng dấu phân cách, cần bảo đảm dữ liệu đầu vào không làm mơ hồ cách tách; có thể dùng định dạng mã hóa có cấu trúc hoặc hàm băm từ biểu diễn chuẩn hóa.

### 3.2. Chuẩn hóa trước khi xác định identity

Hai giá trị như `"erp-77"` và `" ERP-77 "` có thể là cùng một mã theo quy tắc nghiệp vụ. Trước khi tạo khóa, cần xác định quy tắc chuẩn hóa rõ ràng:

- Loại bỏ khoảng trắng đầu và cuối nếu nguồn cho phép.
- Quy định có phân biệt chữ hoa và chữ thường hay không.
- Giữ số 0 ở đầu nếu nó là một phần của mã.
- Chuẩn hóa Unicode nếu dữ liệu có thể chứa ký tự tương đương ở nhiều dạng.
- Không tự ý chuyển mã thành số nếu định dạng mã có thể chứa ký tự hoặc số 0 ở đầu.
- Xử lý giá trị null hoặc rỗng trước khi chạy truy vấn.

Chuẩn hóa phải nhất quán ở mọi đường nhập dữ liệu và ở các truy vấn tìm kiếm. Nếu lúc ghi dùng một quy tắc nhưng lúc tra cứu dùng quy tắc khác, ứng dụng có thể tạo bản ghi mới cho một thực thể đã tồn tại.

## 4. Vì sao dữ liệu nhập ngoài có thể tạo node trùng?

Một số nguyên nhân phổ biến:

1. **Dùng `CREATE` cho mọi dòng nhập:** mỗi lần chạy tạo node mới, kể cả khi cùng một thực thể đã tồn tại.
2. **Không có unique constraint:** hai thao tác đồng thời có thể cùng kiểm tra chưa có node rồi tạo hai node có cùng khóa.
3. **Dùng khóa không đủ phạm vi:** ID từ hai hệ thống khác nhau bị xem là cùng một khóa hoặc cùng một thực thể.
4. **Dùng thuộc tính thay đổi làm khóa:** thay đổi email, tên hoặc mã khách hàng khiến truy vấn không tìm được node cũ.
5. **Đặt cả thuộc tính biến động trong `MERGE`:** chỉ cần tên hoặc trạng thái khác, pattern không còn khớp và có thể tạo node mới.
6. **Dữ liệu đầu vào không được chuẩn hóa:** khác biệt về khoảng trắng, chữ hoa/thường hoặc định dạng tạo ra nhiều khóa.
7. **Nhập lại dữ liệu không có tính idempotent:** chạy lại cùng một tệp hoặc nhận lại cùng một message tạo thêm node.
8. **Gộp các nguồn không có quy tắc đối chiếu:** hai ID khác nhau của cùng một thực thể tạo ra hai node mà không có liên kết định danh nguồn.

Node trùng không chỉ làm dữ liệu phình to. Nó có thể làm sai số liệu tổng hợp, gợi ý, phân tích đường đi, phân quyền và các truy vấn tìm quan hệ. Nếu hai node trùng có các relationship khác nhau, việc xóa một node mà không hợp nhất các liên kết còn có thể làm mất dữ liệu nghiệp vụ.

## 5. Dùng MERGE để nhập dữ liệu có thể chạy lặp lại

Trong Cypher, `CREATE` luôn tạo node hoặc relationship mới. `MERGE` tìm một pattern khớp; nếu không tìm thấy, nó tạo pattern đó. Vì vậy, `MERGE` thường phù hợp với thao tác upsert dữ liệu nhập ngoài.

Ví dụ nhập khách hàng theo cặp nguồn và mã ngoài:

```cypher
MERGE (c:ImportedCustomer {
    sourceSystem: $sourceSystem,
    externalId: $externalId
})
ON CREATE SET
    c.displayName = $displayName,
    c.createdAt = datetime()
ON MATCH SET
    c.displayName = $displayName,
    c.updatedAt = datetime()
RETURN c
```

Cách đọc:

- `MERGE` tìm node có label `ImportedCustomer` và đúng cả `sourceSystem`, `externalId`.
- Nếu chưa có node, `ON CREATE SET` gán các thuộc tính khởi tạo.
- Nếu đã có node, `ON MATCH SET` cập nhật các thuộc tính được phép đồng bộ.
- `RETURN c` trả node được tạo hoặc tìm thấy.

Chỉ đưa các thuộc tính xác định identity vào pattern `MERGE`. Các thuộc tính thường thay đổi như tên hiển thị, địa chỉ hoặc trạng thái nên được đặt trong `ON CREATE` và `ON MATCH`, hoặc được xử lý theo chính sách đồng bộ riêng. Nếu đưa `displayName` vào map của `MERGE`, cùng một khách hàng nhưng tên đổi sẽ tạo ra một pattern khác.

`MERGE` giúp truy vấn có thể chạy lại mà không cố ý tạo node mới cho cùng khóa. Tuy nhiên, trong môi trường có nhiều giao dịch đồng thời, `MERGE` một mình không thay thế unique constraint. Constraint là hàng rào bảo vệ ở cấp cơ sở dữ liệu.

### 5.1. Đặt unique constraint trước khi nhập dữ liệu

Quy trình nhập nên tạo constraint trước khi chạy tải đồng thời. Nếu constraint được tạo sau khi dữ liệu đã nhập, cần kiểm tra và xử lý các bản ghi trùng trước.

Với khóa ngoài theo nguồn:

```cypher
CREATE CONSTRAINT imported_customer_identity IF NOT EXISTS
FOR (c:ImportedCustomer)
REQUIRE (c.sourceSystem, c.externalId) IS UNIQUE
```

Unique constraint chỉ áp dụng khi property có giá trị; nó không bắt buộc mọi node đều phải có đủ các property đó. Vì vậy, ứng dụng vẫn phải từ chối bản ghi thiếu `sourceSystem` hoặc `externalId` trước khi gọi `MERGE`.

Một quy trình nhập an toàn thường gồm:

1. Kiểm tra schema và constraint.
2. Xác thực, chuẩn hóa và loại bản ghi thiếu khóa.
3. Gom các dòng có cùng identity trong một batch.
4. Chạy upsert theo khóa đã chuẩn hóa.
5. Ghi nhận số lượng tạo mới, cập nhật, bỏ qua và lỗi.
6. Đối soát kết quả sau khi nhập.

### 5.2. Tránh MERGE trên toàn bộ pattern có nhiều node

Khi nhập cả node và relationship, nên tách việc tìm node theo identity khỏi việc tạo relationship:

```cypher
MERGE (customer:ImportedCustomer {
    sourceSystem: $sourceSystem,
    externalId: $externalId
})
MERGE (product:Product {productCode: $productCode})
MERGE (customer)-[r:PURCHASED]->(product)
ON CREATE SET r.firstSeenAt = datetime()
SET r.lastSeenAt = datetime()
```

Các node được xác định riêng theo khóa của chúng, sau đó relationship được nối giữa hai node đã tìm thấy hoặc tạo mới. Cách này làm rõ identity của từng thực thể và giảm nguy cơ tạo lại cả một pattern dài khi một phần của pattern không khớp.

Mỗi loại node cần có khóa và constraint phù hợp. Nếu `productCode` không duy nhất, việc `MERGE` product vẫn có thể khớp sai hoặc tạo thêm node. Nếu nghiệp vụ cho phép nhiều lần mua cùng sản phẩm, hãy quyết định relationship `PURCHASED` biểu diễn một quan hệ tổng hợp hay một sự kiện mua riêng; nếu là từng sự kiện, mỗi lần mua nên có identity riêng thay vì gộp tất cả vào một relationship.

## 6. Dùng Cypher trong Spring Data Neo4j

Có thể đặt truy vấn upsert trong repository bằng `@Query`. Các giá trị đầu vào được truyền qua tham số để không ghép trực tiếp dữ liệu vào chuỗi truy vấn.

```java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ImportedCustomerRepository
        extends Neo4jRepository<ImportedCustomer, String> {

    @Query("""
        MERGE (c:ImportedCustomer {
            sourceSystem: $sourceSystem,
            externalId: $externalId
        })
        ON CREATE SET
            c.id = $id,
            c.version = 0,
            c.displayName = $displayName,
            c.createdAt = datetime()
        ON MATCH SET
            c.displayName = $displayName,
            c.version = coalesce(c.version, 0) + 1,
            c.updatedAt = datetime()
        RETURN c
        """)
    ImportedCustomer upsertFromSource(
        @Param("id") String id,
        @Param("sourceSystem") String sourceSystem,
        @Param("externalId") String externalId,
        @Param("displayName") String displayName
    );
}
```

Ứng dụng tạo trước một UUID làm ID kỹ thuật cho lần gọi upsert, ví dụ `UUID.randomUUID().toString()`. Nếu node đã tồn tại, `MERGE` giữ nguyên ID cũ và bỏ qua giá trị `$id`; nếu node mới được tạo, ID và version ban đầu được ghi cùng node. Entity tương ứng:

```java
@Node("ImportedCustomer")
public class ImportedCustomer {

    @Id
    private String id;

    @Version
    private Long version;

    private String sourceSystem;
    private String externalId;
    private String displayName;

    protected ImportedCustomer() {
    }
}
```

Trong hệ thống thực tế, hãy kiểm tra kiểu kết quả của custom query và các trường bắt buộc của entity. Ví dụ này tăng `version` khi cập nhật để entity trả về có version mới, nhưng custom Cypher không tự áp dụng optimistic locking như thao tác `save()` tiêu chuẩn; cần bổ sung điều kiện version hoặc chính sách so sánh timestamp nguồn nếu các luồng ghi có thể cạnh tranh. Các node cũ phải được backfill ID và version trước khi ánh xạ thành entity theo cấu trúc này.

Khi dữ liệu nhập được xử lý theo batch lớn, có thể dùng `Neo4jClient` hoặc `Neo4jTemplate` để kiểm soát kết quả và cách chia batch. Dù dùng API nào, nguyên tắc identity vẫn giống nhau: tham số hóa đầu vào, tìm theo khóa ổn định, đặt constraint và xác định rõ thuộc tính nào được phép cập nhật.

## 7. Đổi khóa nghiệp vụ đang được dùng làm @Id

Nếu hệ thống hiện tại dùng mã nghiệp vụ làm `@Id`, thay đổi mã cần được xử lý như một thay đổi định danh. Không nên chỉ sửa một trường trên object rồi gọi `save()` mà không kiểm tra node đích, trạng thái version và các hệ thống đang tham chiếu mã cũ.

Giả sử `customerCode` hiện là `@Id` và cần đổi từ `CUS-0018` sang `CUS-1042`. Quy trình an toàn:

1. Xác nhận đây là cùng một khách hàng, không phải hai hồ sơ cần hợp nhất.
2. Kiểm tra mã mới chưa thuộc về node khác.
3. Kiểm tra unique constraint và các tham chiếu bên ngoài đang lưu mã cũ.
4. Thực hiện migration trong transaction phù hợp để cập nhật property định danh trên đúng node.
5. Nếu entity dùng `@Version`, bảo đảm migration phối hợp với version; sau migration, tải lại entity để tránh dùng object cũ có version hoặc ID lỗi thời.
6. Cập nhật hệ thống nguồn, API, cache, message và các bảng đối chiếu theo kế hoạch chuyển đổi.
7. Đối soát số node và quan hệ trước khi kết thúc migration.

Ví dụ kiểm tra mã đích đã tồn tại:

```cypher
MATCH (c:Customer {customerCode: $newCode})
RETURN c
```

Nếu có kết quả, phải xác định chủ sở hữu của mã đó trước khi đổi. Không được ghi đè hoặc gộp hai khách hàng chỉ vì chúng có thông tin tên hoặc địa chỉ giống nhau.

Khi cập nhật trực tiếp property đang được dùng làm `@Id`, cần phối hợp với cơ chế version và trạng thái của các entity trong ứng dụng. Tùy cách triển khai, có thể thực hiện migration bằng truy vấn Cypher được quản lý rõ ràng, sau đó đọc lại entity. Với hệ thống có thể thiết kế lại, chuyển sang một UUID ổn định làm `@Id` và giữ business key ở property riêng sẽ giúp các lần đổi mã tiếp theo đơn giản hơn.

## 8. Phát hiện và xử lý node trùng

Trước khi hợp nhất dữ liệu hoặc tạo constraint, cần tìm các node có cùng khóa nguồn:

```cypher
MATCH (c:ImportedCustomer)
WHERE c.sourceSystem IS NOT NULL
  AND c.externalId IS NOT NULL
WITH c.sourceSystem AS source,
     c.externalId AS externalId,
     collect(c) AS nodes
WHERE size(nodes) > 1
RETURN source,
       externalId,
       size(nodes) AS duplicateCount,
       [n IN nodes | elementId(n)] AS nodeIds
ORDER BY duplicateCount DESC
```

Truy vấn này nhóm node theo identity nguồn và hiển thị nhóm có nhiều hơn một node. Nó chỉ phục vụ kiểm tra; không tự xóa dữ liệu.

Không nên xử lý node trùng bằng cách xóa tùy tiện một node. Trước khi hợp nhất, cần:

- Xác định node chuẩn dựa trên nguồn có thẩm quyền và quy tắc nghiệp vụ.
- So sánh các property, lịch sử thay đổi và nguồn gốc dữ liệu.
- Kiểm tra toàn bộ relationship đi vào và đi ra của từng node.
- Chuyển các relationship cần giữ sang node chuẩn; kiểm tra relationship trùng sau khi chuyển.
- Ghi lại mapping từ ID cũ sang ID chuẩn để cập nhật tham chiếu bên ngoài.
- Chỉ xóa node dư sau khi đối soát và có thể khôi phục theo chính sách vận hành.

Với dữ liệu lớn, nên chạy quy trình hợp nhất theo batch, có log, checkpoint và khả năng tiếp tục sau lỗi. Tránh thực hiện một truy vấn xóa hàng loạt chỉ dựa trên việc hai node có cùng tên.

## 9. Tính idempotent và đồng bộ nhiều lần

Một quy trình nhập là idempotent khi chạy lại cùng một đầu vào không tạo thêm thực thể hoặc làm thay đổi kết quả ngoài chính sách đã định. Tính idempotent rất quan trọng vì message có thể được gửi lại, batch có thể chạy lại sau sự cố hoặc hệ thống nguồn có thể phát lại dữ liệu. `MERGE` giúp tránh tạo thêm node theo cùng identity, nhưng một câu lệnh vẫn có thể tạo side effect mỗi lần chạy nếu `ON MATCH` luôn đổi timestamp, bộ đếm hoặc version.

Để đạt được điều này:

- Xác định identity ổn định và chuẩn hóa trước khi ghi.
- Dùng `MERGE` theo identity, không dùng các thuộc tính biến động trong khóa.
- Đặt unique constraint tương ứng.
- Tách thuộc tính chỉ được đặt lúc tạo khỏi thuộc tính được phép cập nhật khi đồng bộ.
- Lưu nguồn và thời điểm đồng bộ để có thể truy vết.
- Xác định quy tắc xử lý dữ liệu cũ đến muộn: dùng timestamp/version từ nguồn để tránh ghi đè dữ liệu mới hơn.
- Xử lý lỗi unique constraint bằng cách đọc lại node theo khóa chuẩn và quyết định retry phù hợp; không tự động chuyển sang `CREATE`.

Ví dụ, nếu nguồn gửi một bản ghi có `updatedAt` cũ hơn dữ liệu đang có, `ON MATCH SET` không nên ghi đè thông tin mới nhất. Có thể so sánh timestamp hoặc source version trong truy vấn hoặc xử lý quy tắc đồng bộ ở service trước khi cập nhật. Nếu cần chống phát lại cùng một sự kiện, hãy lưu event ID hoặc source version đã áp dụng và chỉ cập nhật property cùng version khi nhận được sự kiện mới hơn; không tăng version cho một message đã được xử lý.

## 10. Những lỗi thường gặp

| Lỗi | Cách phòng tránh |
| --- | --- |
| Dùng mã nghiệp vụ có thể đổi làm `@Id` | Dùng surrogate ID ổn định và giữ mã nghiệp vụ ở property riêng nếu có thể |
| Dùng ID ngoài mà không kèm namespace | Kết hợp nguồn, tenant và external ID theo phạm vi duy nhất thực tế |
| Đưa tên hoặc trạng thái vào map của `MERGE` | Chỉ dùng thuộc tính identity trong pattern; cập nhật thuộc tính biến động bằng `ON MATCH SET` |
| Dùng `CREATE` khi nhập lại cùng dữ liệu | Dùng `MERGE` theo khóa chuẩn và unique constraint |
| Nghĩ rằng `MERGE` tự bảo đảm duy nhất khi có ghi đồng thời | Tạo unique constraint ở Neo4j |
| Cho phép external ID null hoặc rỗng | Xác thực đầu vào trước khi gọi Cypher |
| Xóa node trùng trước khi chuyển relationship | Lập kế hoạch hợp nhất, chuyển liên kết và đối soát trước |
| Đổi `@Id` rồi tiếp tục dùng entity cũ | Tải lại entity và đồng bộ version sau migration |
| Ghi đè dữ liệu mới bằng bản tin cũ | So sánh timestamp hoặc version của nguồn |

## 11. Câu hỏi tự kiểm tra

1. Vì sao một business key có thể không phù hợp làm `@Id`?
2. Khi nào nên dùng UUID ổn định làm định danh và giữ business key thành property?
3. Vì sao external ID cần namespace của hệ thống nguồn hoặc tenant?
4. Khác biệt giữa `CREATE` và `MERGE` trong quy trình nhập dữ liệu là gì?
5. Vì sao unique constraint vẫn cần thiết khi truy vấn đã dùng `MERGE`?
6. Thuộc tính nào nên nằm trong pattern `MERGE`, thuộc tính nào nên cập nhật bằng `ON MATCH SET`?
7. Cần làm gì trước khi đổi business key đang được dùng làm `@Id`?
8. Vì sao không nên xóa node trùng trước khi kiểm tra các relationship của chúng?
9. Một quy trình nhập dữ liệu idempotent giúp hệ thống xử lý việc phát lại message như thế nào?

## Kết luận

Khóa nghiệp vụ và ID từ hệ thống ngoài là dữ liệu quan trọng, nhưng không phải lúc nào cũng là định danh ổn định của node. Khi business key có thể thay đổi, dùng một ID kỹ thuật ổn định làm `@Id` và lưu mã nghiệp vụ thành property riêng sẽ giúp việc cập nhật ít ảnh hưởng đến identity và relationship.

Với dữ liệu nhập ngoài, cần xác định namespace, chuẩn hóa khóa, kiểm tra dữ liệu thiếu, dùng `MERGE` theo các thuộc tính identity và tạo unique constraint ở Neo4j. Khi phát hiện node trùng, phải đối chiếu nguồn, hợp nhất property và relationship có kiểm soát trước khi xóa dữ liệu dư. Những nguyên tắc này giúp quy trình đồng bộ có thể chạy lặp lại và giảm nguy cơ tạo bản ghi trùng trong tầng dữ liệu đồ thị.
