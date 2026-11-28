# Điều chỉnh ID nội bộ, elementId và ID nghiệp vụ theo phiên bản

Khi nâng cấp Neo4j hoặc Spring Data Neo4j (SDN), cách ứng dụng nhận diện một node có thể thay đổi theo phiên bản. Một trường `@Id` kiểu `Long` được tạo từ ID nội bộ, một trường `String` được tạo từ `elementId` và một ID nghiệp vụ lưu thành property là ba loại định danh khác nhau. Chúng không thể thay thế cho nhau chỉ bằng cách đổi kiểu Java hoặc chuyển giá trị số thành chuỗi.

Vấn đề quan trọng nhất là phạm vi bảo đảm của từng ID. ID nội bộ và `elementId` do Neo4j quản lý để định vị graph element trong phạm vi transaction. Chúng không phải khóa lâu dài cho API, message queue, cache hay hệ thống bên ngoài. Nếu cần định danh ổn định qua nhiều transaction, lần restore, di chuyển database hoặc nhiều môi trường, hãy dùng khóa do ứng dụng quản lý: UUID hoặc business key thực sự bất biến.

Bài học này phân biệt `id()`, `elementId()` và business ID; giải thích cách SDN ánh xạ `@Id`/`@GeneratedValue` theo phiên bản; sau đó xây dựng quy trình chuyển dữ liệu cũ sang ID ổn định mà không làm mất liên kết với hệ thống đang sử dụng.

## Ba loại định danh cần phân biệt

Một graph có thể có cùng lúc ba lớp định danh:

| Loại | Nơi lưu | Ví dụ | Phạm vi sử dụng |
|---|---|---|---|
| Internal numeric ID | Metadata nội bộ của Neo4j | `id(n)` trả về số | Định vị node/relationship trong database, trong transaction |
| Element ID | Metadata nội bộ của Neo4j | `elementId(n)` trả về chuỗi | Định vị graph element trong transaction; opaque |
| Application ID / business ID | Property trên node hoặc relationship | `appId`, `employeeCode` | Định danh ứng dụng, API và tích hợp nếu được thiết kế ổn định |

Ví dụ:

~~~cypher
MATCH (p:Person {employeeCode: $employeeCode})
RETURN id(p) AS internalId,
       elementId(p) AS elementId,
       p.appId AS appId,
       p.employeeCode AS employeeCode;
~~~

Trong kết quả, `internalId` và `elementId` được Neo4j cung cấp. `appId` và `employeeCode` là property nghiệp vụ/ứng dụng do hệ thống lưu trên node.

Không suy luận loại ID chỉ từ kiểu dữ liệu. Một `String` có thể là business key, UUID do ứng dụng tạo, hoặc `elementId` nội bộ được SDN ánh xạ. Cần xem annotation, generator và schema thực tế.

## Internal ID và hàm id()

Neo4j cấp ID nội bộ cho node và relationship. Trong Cypher, `id(n)` trả về numeric ID. SDN có thể dùng giá trị này làm ID persistence cho entity khi trường `@Id` được khai báo kiểu `Long` cùng `@GeneratedValue`.

Ví dụ entity dùng internal ID:

~~~java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String fullName;

    protected Person() {
    }

    public Person(String fullName) {
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Dùng wrapper `Long` thay vì primitive `long` để `null` thể hiện entity chưa có ID được cấp. Với entity bất biến, SDN cần setter hoặc wither/constructor phù hợp để nhận ID sau khi lưu.

### Vì sao không dùng internal ID làm public ID?

Internal ID không được thiết kế để đại diện lâu dài cho một thực thể trong miền nghiệp vụ:

- Neo4j có thể tái sử dụng internal ID sau khi node hoặc relationship bị xóa.
- ID chỉ có bảo đảm duy nhất theo loại graph element và database trong phạm vi transaction; một node và một relationship có thể có cùng giá trị số.
- Internal ID không phải khóa toàn cục giữa các database hoặc giữa các loại graph element.
- Một giá trị số cũ có thể trỏ tới graph element khác sau khi xóa/tạo dữ liệu.
- Restore, import, export hoặc tạo database mới không bảo đảm giữ cùng ID nội bộ.
- Client bên ngoài không nên phụ thuộc vào cách Neo4j cấp hoặc lưu trữ ID.

Hàm `id()` đã bị đánh dấu deprecated trong Cypher hiện hành; tài liệu khuyến nghị `elementId()` cho việc định vị graph element. Tuy vậy, thay `id()` bằng `elementId()` không biến ID nội bộ thành khóa bền vững. Cả hai đều không phù hợp làm định danh công khai lâu dài.

Có thể dùng internal ID trong query nội bộ hoặc thao tác trong transaction khi cần. Không lưu nó vào URL, token, event, message queue, cache key, bảng tham chiếu của hệ thống khác hoặc file import/export làm khóa dài hạn.

## Element ID và thay đổi từ Neo4j 5

Neo4j 5 giới thiệu `elementId()` trả về chuỗi định danh cho node hoặc relationship. Trong SDN, với Neo4j 5 trở lên, trường `@Id @GeneratedValue` kiểu `String` được ánh xạ tới `elementId`; trường kiểu `Long` vẫn đại diện internal numeric ID.

Ví dụ truy vấn:

~~~cypher
MATCH (p:Person)
RETURN elementId(p) AS elementId,
       p.fullName AS fullName;
~~~

`elementId` là chuỗi opaque. Không phân tích các phần của chuỗi, không giả định độ dài hoặc thứ tự, và không dựa vào định dạng hiện tại để tạo thuật toán ứng dụng.

Neo4j bảo đảm element ID duy nhất giữa node và relationship trong các database thuộc cùng DBMS trong phạm vi một transaction. Ngoài phạm vi transaction đó, Neo4j không bảo đảm mapping giữa element ID và graph element. Vì vậy, một element ID đọc trong transaction hôm nay không phải khóa để dùng lại tùy ý trong transaction ngày mai.

### Bảng tương quan phiên bản và kiểu SDN

| Bối cảnh | `@Id @GeneratedValue Long` | `@Id @GeneratedValue String` | Khuyến nghị |
|---|---|---|---|
| Neo4j trước 5 | Internal numeric ID | Cần kiểm tra mapping của phiên bản SDN đang chạy; không suy luận từ mã mới | Không phát hành internal ID ra ngoài |
| Neo4j 5 và SDN hỗ trợ element ID | Internal numeric ID | `elementId` | Dùng UUID/business ID cho tham chiếu lâu dài |
| Hệ thống đang chuyển nhiều phiên bản | Mapping có thể khác theo SDN/Driver/server | Mapping có thể khác theo SDN/Driver/server | Kiểm tra đồng bộ cả server, SDN và Java Driver trước cutover |

Không thực hiện migration bằng cách đổi một field từ `Long` sang `String` rồi kỳ vọng các giá trị cũ tự chuyển thành business ID. `String` có thể chứa element ID do Neo4j cấp, không phải chuỗi biểu diễn của numeric ID cũ.

## ID do ứng dụng tạo: UUID hoặc surrogate key

Nếu cần định danh bền vững, hãy tạo property ID ở phía ứng dụng hoặc bằng generator được thiết kế để duy nhất trên toàn bộ các instance. SDN cung cấp `UUIDStringGenerator` để tạo UUID dạng chuỗi.

~~~java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;
import org.springframework.data.neo4j.core.schema.UUIDStringGenerator;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue(UUIDStringGenerator.class)
    @Property("appId")
    private String id;

    private String fullName;

    protected Person() {
    }

    public Person(String fullName) {
        this.fullName = fullName;
    }

    public String getId() {
        return id;
    }
}
~~~

Trong ví dụ này, `id` là tên field Java, còn `appId` là tên property trong Neo4j. Đây là ID do generator tạo và được lưu thành property trên node, khác với `elementId` vốn là metadata nội bộ.

Cần tạo uniqueness constraint cho property ID. Annotation `@Id` không tự thay thế quy trình quản lý schema:

~~~cypher
CREATE CONSTRAINT person_app_id_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.appId IS UNIQUE;
~~~

UUID có xác suất trùng rất thấp khi được tạo bằng generator phù hợp, nhưng uniqueness constraint vẫn là lớp bảo vệ ở database. Với hệ thống nhiều instance, không dùng `AtomicInteger` cục bộ hoặc bộ đếm chỉ tồn tại trong một JVM làm generator toàn cục; hai instance có thể tạo cùng giá trị.

Nếu tự viết `IdGenerator`, cần kiểm tra tính duy nhất khi chạy đồng thời, restart, scale out và retry. Một generator gọi database để lấy sequence phải có thao tác cấp số nguyên tử; không đọc số lớn nhất rồi cộng một ở phía ứng dụng.

## Business ID và surrogate ID

Business ID là khóa mang ý nghĩa miền nghiệp vụ, chẳng hạn mã nhân viên, mã đơn hàng hoặc mã sản phẩm. Chỉ chọn nó làm `@Id` nếu nó thực sự duy nhất, bất biến và có vòng đời phù hợp với entity.

Ví dụ dùng employee code làm business ID:

~~~java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String fullName;

    @Version
    private Long version;

    protected Person() {
    }

    public Person(String employeeCode, String fullName) {
        this.employeeCode = employeeCode;
        this.fullName = fullName;
    }
}
~~~

Tạo constraint:

~~~cypher
CREATE CONSTRAINT person_employee_code_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.employeeCode IS UNIQUE;
~~~

Khi dùng business ID làm `@Id`, giá trị đã tồn tại ngay từ lúc tạo object. SDN không thể chỉ dựa vào việc ID có `null` hay không để phân biệt object mới với object đã lưu. Vì vậy, business ID cần đi cùng trường `@Version` để SDN nhận biết trạng thái persistence và hỗ trợ optimistic locking.

`@Version` kiểu `Long` được SDN quản lý: giá trị được khởi tạo khi insert và tăng sau mỗi lần update. Không tự đặt hoặc tăng version trong service. Nếu hai transaction cùng sửa entity từ version `x`, lần ghi đầu có thể thành công và chuyển version thành `x + 1`; lần ghi sau với version cũ sẽ nhận `OptimisticLockingFailureException`. Khi retry, phải tải entity mới nhất rồi áp dụng thay đổi, không chỉ lặp lại save trên object cũ.

### Khi nào không nên dùng business key làm @Id?

Không nên dùng business key làm primary ID nếu nó có thể đổi:

- Email có thể thay đổi khi người dùng cập nhật tài khoản.
- Số điện thoại có thể được cấp lại cho người khác.
- Mã nhân viên có thể đổi khi chuyển hệ thống hoặc thay đổi chính sách.
- Tên sản phẩm có thể được chuẩn hóa hoặc đổi theo thị trường.

Trong trường hợp này, dùng UUID bất biến làm `@Id` và tạo uniqueness constraint riêng cho business key. Business key vẫn được dùng để tra cứu, nhưng thay đổi nghiệp vụ không làm thay đổi identity của node.

Ví dụ tenant và mã nhân viên chỉ duy nhất trong từng tenant:

~~~cypher
CREATE CONSTRAINT person_tenant_employee_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.employeeCode) IS UNIQUE;
~~~

Không giả định `employeeCode` duy nhất toàn hệ thống nếu nó chỉ duy nhất trong phạm vi tenant.

## ID của relationship

Relationship cũng có internal identifier. Trong SDN, class dùng `@RelationshipProperties` có thể khai báo `@RelationshipId` để framework theo dõi relationship khi lưu aggregate.

~~~java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Membership {

    @RelationshipId
    private Long internalId;

    private String role;

    @TargetNode
    private Person person;

    public Membership(Person person, String role) {
        this.person = person;
        this.role = role;
    }
}
~~~

`@RelationshipId` phục vụ cơ chế persistence của SDN, không phải mã membership công khai. Nếu một relationship cần identity nghiệp vụ riêng (ví dụ hợp đồng, tư cách thành viên hoặc lần phân công), hãy lưu property `membershipId` do ứng dụng cấp và thiết kế constraint phù hợp với phiên bản/edition Neo4j đang dùng.

Không dùng ID nội bộ của relationship để tham chiếu từ hệ thống ngoài hoặc để quyết định nghiệp vụ. Nếu cần tìm relationship theo khóa nghiệp vụ, query theo property đó cùng các endpoint/điều kiện miền nghiệp vụ.

## Kiểm kê trước khi chuyển ID

Trước khi đổi mapping, lập danh sách mọi nơi đang dùng ID cũ:

- Entity field có `@Id` và `@GeneratedValue`.
- Cypher dùng `id(n)` hoặc `elementId(n)`.
- REST/GraphQL endpoint trả internal ID.
- Cache key, event payload, message queue, audit log và job lưu ID.
- Database khác hoặc file CSV đang tham chiếu node bằng ID nội bộ.
- Code Java dùng `Node.id()` hoặc `Relationship.id()` của Driver.
- Integration test giả định numeric ID bắt đầu từ 0 hoặc tăng tuần tự.

Kiểm tra số lượng node có property mới, ví dụ:

~~~cypher
MATCH (p:Person)
RETURN count(p) AS totalPeople,
       count(p.appId) AS peopleWithAppId;
~~~

Tìm node còn thiếu ID:

~~~cypher
MATCH (p:Person)
WHERE p.appId IS NULL
RETURN count(p) AS missingAppId;
~~~

Kiểm tra trùng business key trước khi tạo constraint:

~~~cypher
MATCH (p:Person)
WHERE p.employeeCode IS NOT NULL
WITH p.employeeCode AS employeeCode, count(*) AS copies
WHERE copies > 1
RETURN employeeCode, copies
ORDER BY copies DESC;
~~~

Nếu có node thiếu business key hoặc duplicate, xử lý theo quy tắc nghiệp vụ trước. Không tự gán một mã dựa trên `id(n)` hoặc `elementId(n)` để che lấp dữ liệu không hợp lệ.

## Chiến lược migration từ internal ID sang application ID

Với hệ thống đang chạy, chuyển ID nên theo mô hình expand–migrate–contract. Mục tiêu là thêm property ID ổn định, backfill dữ liệu cũ, chuyển dần code và chỉ ngừng dùng ID cũ sau khi mọi consumer đã chuyển.

~~~mermaid
flowchart TD
    A["Kiểm kê cách dùng ID cũ"] --> B["Mở rộng schema: appId + uniqueness constraint"]
    B --> C["Deploy code ghi appId cho node mới"]
    C --> D["Backfill node cũ còn thiếu appId"]
    D --> E["Xác minh đủ ID và không trùng"]
    E --> F["Chuyển SDN @Id sang appId + @Version"]
    F --> G["Chuyển API, cache, event và consumer"]
    G --> H["Ngừng đọc/phát internal ID"]
    H --> I["Xóa tương thích tạm sau thời gian quan sát"]
~~~

### Giai đoạn 1: Mở rộng schema

Trước khi tạo constraint, kiểm tra các giá trị appId đã có sẵn để phát hiện duplicate:

~~~cypher
MATCH (p:Person)
WHERE p.appId IS NOT NULL
WITH p.appId AS appId, count(*) AS copies
WHERE copies > 1
RETURN appId, copies;
~~~

Xử lý mọi duplicate trước khi tạo constraint. Sau đó tạo uniqueness constraint trước khi backfill để database bảo vệ các giá trị mới:

~~~cypher
CREATE CONSTRAINT person_app_id_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.appId IS UNIQUE;
~~~

Unique constraint cho phép nhiều node chưa có property này; nó bảo vệ uniqueness cho các giá trị được gán. Với mỗi label/entity, tạo constraint phù hợp. Nếu ID là composite business key, khai báo đúng các property tham gia.

### Giai đoạn 2: Deploy code ghi ID mới

Trong thời gian chuyển tiếp, có thể giữ internal ID làm mapping key SDN và thêm `appId` như property thường. Ứng dụng tạo ID mới cho node mới:

~~~java
import java.util.UUID;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long internalId;

    private String appId;

    private String fullName;

    public Person(String fullName) {
        this.appId = UUID.randomUUID().toString();
        this.fullName = fullName;
    }
}
~~~

Đây là mô hình chuyển tiếp. Chỉ dùng khi mọi instance tạo node mới đã được nâng cấp để ghi `appId`. Trong rolling deployment, instance cũ vẫn có thể tạo node thiếu property mới; cần drain instance cũ hoặc giữ bước backfill lặp lại cho đến khi không còn writer cũ.

### Giai đoạn 3: Backfill node cũ

Với dữ liệu vừa phải, có thể tạo UUID cho mọi node còn thiếu:

~~~cypher
MATCH (p:Person)
WHERE p.appId IS NULL
SET p.appId = randomUUID()
RETURN count(p) AS updated;
~~~

Điều kiện `WHERE p.appId IS NULL` khiến lệnh có thể chạy lại mà không thay ID đã cấp. Với graph lớn, không nên gom toàn bộ dữ liệu vào một transaction dài. Chạy migration job theo batch có transaction riêng, lặp đến khi không còn node thiếu:

~~~cypher
MATCH (p:Person)
WHERE p.appId IS NULL
WITH p
LIMIT $batchSize
SET p.appId = randomUUID()
RETURN count(p) AS updated;
~~~

Ứng dụng migration lặp query với batch size phù hợp cho đến khi `updated` bằng 0. Theo dõi thời gian transaction, memory, tải ghi và replication lag. Không tăng batch chỉ để hoàn tất nhanh nếu làm ảnh hưởng workload trực tuyến.

Nếu entity sẽ chuyển sang business ID cùng `@Version`, cần chuẩn bị version cho các node đã tồn tại. Ví dụ, sau khi xác minh chưa có quy tắc version khác:

~~~cypher
MATCH (p:Person)
WHERE p.version IS NULL
SET p.version = 0
RETURN count(p) AS initializedVersions;
~~~

`version` là property do SDN quản lý sau cutover. Không cập nhật nó thủ công trong hoạt động ứng dụng thường ngày.

### Giai đoạn 4: Xác minh trước cutover

Kiểm tra không còn node thiếu ID:

~~~cypher
MATCH (p:Person)
WHERE p.appId IS NULL
RETURN count(p) AS missing;
~~~

Kiểm tra uniqueness:

~~~cypher
MATCH (p:Person)
WITH p.appId AS appId, count(*) AS copies
WHERE appId IS NULL OR copies > 1
RETURN appId, copies;
~~~

Kiểm tra constraint đã online:

~~~cypher
SHOW CONSTRAINTS;
~~~

Kiểm tra số lượng tổng và số lượng có ID phải bằng nhau. Thực hiện kiểm thử đọc/ghi bằng phiên bản ứng dụng mới trên bản sao dữ liệu trước khi chuyển production.

### Giai đoạn 5: Chuyển mapping SDN

Sau khi toàn bộ node đã có `appId` và code cũ không còn ghi node mới thiếu ID, chuyển field `@Id` sang property mới:

~~~java
@Node("Person")
public class Person {

    @Id
    @Property("appId")
    private String id;

    @Version
    private Long version;

    private String fullName;

    protected Person() {
    }

    public String getId() {
        return id;
    }
}
~~~

Nếu muốn SDN tự tạo ID cho entity mới sau cutover, có thể dùng `@GeneratedValue(UUIDStringGenerator.class)` thay cho ID được gán sẵn, đồng thời giữ uniqueness constraint trên property tương ứng. Chọn một cách cấp ID nhất quán cho toàn bộ writer.

Với business ID làm `@Id`, khai báo `@Version` và uniqueness constraint tương ứng. Đảm bảo mọi node hiện hữu có version hợp lệ trước khi chạy code mới.

### Giai đoạn 6: Chuyển consumer và ngừng dùng ID cũ

Cập nhật API và tích hợp để gửi `appId` hoặc business ID ổn định. Trong giai đoạn tương thích, có thể nhận ID cũ để tra mapping tạm thời, nhưng không tạo mới tham chiếu internal ID.

Nếu hệ thống bên ngoài đang lưu numeric ID cũ, cần xuất bảng ánh xạ từ snapshot dữ liệu nhất quán trước cutover. Ví dụ, trong một lần migration có kiểm soát:

~~~cypher
MATCH (p:Person)
RETURN id(p) AS legacyInternalId,
       p.appId AS appId,
       p.employeeCode AS employeeCode;
~~~

`id(p)` ở đây chỉ phục vụ đối chiếu một lần với dữ liệu cũ, không phải thiết kế ID mới. Việc ánh xạ chỉ đúng nếu ID cũ vẫn xác định đúng node tại thời điểm snapshot. Nếu internal ID đã bị tái sử dụng sau các lần xóa trước đó, không thể suy ra một cách chắc chắn tham chiếu cũ của hệ thống ngoài đang chỉ tới thực thể nào; phải đối chiếu thêm dữ liệu nghiệp vụ.

Khi xuất mapping cho nhiều loại node hoặc nhiều database, lưu kèm label/loại entity và database scope. Numeric ID của node có thể trùng numeric ID của relationship hoặc một node ở database khác. Để mapping không đổi trong lúc export, dùng một lần migration có kiểm soát: tạm dừng thao tác xóa/tạo liên quan hoặc xuất từ snapshot/transaction nhất quán; tránh chia việc đọc ID cũ thành nhiều transaction độc lập rồi ghép kết quả sau.

Chuyển các tham chiếu trong database ngoài, cache, queue, webhook và URL sang ID mới. Theo dõi tỷ lệ request còn dùng ID cũ trước khi gỡ compatibility layer.

### Giai đoạn 7: Thu hẹp schema và code

Sau khi tất cả consumer đã chuyển:

- Ngừng trả internal ID trong response và event.
- Xóa code fallback đọc ID cũ.
- Xóa field internal ID khỏi entity nếu không còn cần cho ứng dụng.
- Giữ property `appId` và uniqueness constraint.
- Xóa mapping tạm hoặc cột lưu legacy ID sau khi hết thời gian tương thích và đã kiểm tra log truy cập.
- Cập nhật tài liệu API, data contract và runbook.

Không xóa `appId` chỉ vì đã chuyển field Java; đó là property định danh mới được lưu trên graph.

## Chuyển hàm id() sang elementId() trong Cypher và Driver

Nếu query nội bộ hiện đang dùng `id(p)`, có thể đổi sang `elementId(p)` khi mục tiêu là lấy element ID trong phạm vi transaction:

~~~cypher
MATCH (p:Person)
WHERE elementId(p) = $elementId
RETURN p;
~~~

Đổi tham số Java sang `String` nếu query cần nhận element ID. Tuy nhiên, không thay API công khai bằng chuỗi element ID rồi coi đó là migration hoàn tất. Nếu API cần định danh ổn định, query theo property:

~~~cypher
MATCH (p:Person {appId: $appId})
RETURN p;
~~~

Trong Java Driver, các API numeric ID như `Node.id()`/`Relationship.id()` đã bị deprecated trong các phiên bản Driver hiện hành và được thay bằng `elementId()`. Việc đổi API Driver chỉ giải quyết tương thích truy cập metadata; nó không biến element ID thành public key. Nếu cần trả định danh cho client, đọc property `appId` hoặc business key từ node.

## Rủi ro khi đổi ID trong hệ thống phân tán

Một ID có thể được sử dụng ngoài database ở nhiều thời điểm khác nhau. Trước cutover, kiểm tra:

| Nơi dùng ID | Rủi ro | Hành động |
|---|---|---|
| REST/GraphQL URL | Client lưu ID cũ trong bookmark hoặc link | Có endpoint tương thích tạm và chuyển sang appId |
| Event/message queue | Message cũ đến sau khi mapping đổi | Consumer hỗ trợ schema/version event và tra mapping tạm |
| Cache | Key cũ giữ dữ liệu sai hoặc stale | Version namespace/cache key mới và invalidate có kiểm soát |
| Database khác | Foreign key chứa internal ID | Backfill bảng mapping và cập nhật tham chiếu |
| Search index | Document lưu elementId/internal ID | Reindex bằng appId |
| Audit log | Không thể truy ngược ID cũ sau cutover | Giữ bảng mapping legacy có thời hạn và scope rõ |
| Import/export | ID nội bộ thay đổi khi nạp sang database khác | Export appId/business key cùng dữ liệu |
| Multi-database/tenant | Numeric ID có thể trùng giữa database | Dùng UUID toàn cục hoặc key gồm tenant + business key |

Không giả định một UUID tự động là đủ nếu nhiều hệ thống cùng tạo ID. Mỗi writer phải tuân theo cùng quy tắc sinh ID và database phải có uniqueness constraint. Nếu ID chỉ duy nhất trong tenant, mọi truy vấn và constraint cần bao gồm tenant scope.

## Kiểm thử migration và mapping ID

Kiểm thử nên xác minh tính ổn định của identity, không chỉ xác minh field Java có giá trị.

### Kiểm thử entity mới và entity đã tồn tại

Với UUID ID:

1. Tạo entity mới và lưu bằng repository.
2. Xác minh ID được gán.
3. Tải lại entity bằng ID trong transaction mới.
4. So sánh ID sau reload với ID ban đầu.
5. Cập nhật property rồi lưu lại.
6. Xác minh entity vẫn có cùng ID.

Ví dụ assertion:

~~~java
Person saved = repository.save(new Person("Lan Nguyen"));

String appId = saved.getId();

Person reloaded = repository.findById(appId).orElseThrow();

assertThat(reloaded.getId()).isEqualTo(appId);
~~~

### Kiểm thử business ID và optimistic locking

Tạo entity với business key và `@Version`. Sau insert, đọc version được SDN quản lý. Tải hai bản sao trong hai transaction khác nhau; lưu bản thứ nhất rồi thử lưu bản thứ hai với version cũ. Xác minh lần ghi sau thất bại với `OptimisticLockingFailureException` và luồng retry tải lại bản mới nhất.

Không kiểm thử bằng cách tự tăng version trước khi save; như vậy sẽ che giấu cơ chế optimistic locking.

### Kiểm thử dữ liệu đã backfill

Trên bản sao database hoặc môi trường staging:

- Tổng node theo label trước/sau phải khớp.
- Không còn `appId IS NULL`.
- Không có duplicate ID.
- Relationship count và endpoint không thay đổi do migration ID.
- Tất cả node có business ID phải đáp ứng uniqueness constraint.
- API đọc bằng appId trả cùng thực thể trước/sau cutover.
- Consumer cũ được xử lý theo thời gian tương thích đã định.
- Import/export sang database khác vẫn tìm được entity bằng appId.

Nếu migration thay đổi `@Id` của entity, chạy kiểm thử integration với chính phiên bản Neo4j, SDN và Java Driver dự kiến triển khai. Không chỉ kiểm tra bằng mock repository.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đổi `Long` thành `String` rồi giữ nguyên logic | String có thể là elementId chứ không phải business ID | Chọn generator/property rõ ràng và migrate dữ liệu |
| Dùng `elementId()` thay `id()` rồi lưu lâu dài | Tham chiếu có thể không còn trỏ cùng graph element ở transaction sau | Dùng application ID |
| Dùng internal ID trong URL hoặc event | Xóa node và tái sử dụng ID có thể làm tham chiếu sai | Phát hành appId/business key |
| Tạo UUID nhưng không có uniqueness constraint | Lỗi generator hoặc import có thể tạo duplicate | Tạo constraint ở Neo4j |
| Dùng sequence cục bộ trong từng JVM | Nhiều instance có thể cấp trùng | Dùng UUID hoặc sequence tập trung, atomic |
| Dùng business key có thể đổi làm `@Id` | Đổi khóa có thể phá identity và quan hệ tham chiếu | Dùng surrogate ID bất biến |
| Business ID không có `@Version` | SDN khó phân biệt entity mới/đã lưu và thiếu optimistic locking | Thêm version field kiểu Long |
| Tự gán `@Version` trong service | Bỏ qua kiểm soát version của SDN | Để framework quản lý |
| Backfill trong một transaction rất lớn | Tăng lock, memory, transaction log và ảnh hưởng workload | Chạy batch có transaction riêng |
| Backfill không idempotent | Retry có thể thay ID đã cấp | Chỉ cập nhật node còn thiếu property |
| Backfill trước khi mọi writer mới được triển khai | Instance cũ tiếp tục tạo node không có appId | Drain writer cũ hoặc chạy backfill lặp lại |
| Xóa mapping ID cũ quá sớm | Client, event hoặc job cũ không tìm được node | Duy trì compatibility theo thời hạn đo được |
| Dùng `id(n)` để tạo business ID | ID nội bộ không ổn định và có thể tái sử dụng | Tạo UUID/business ID riêng |
| Quên constraint khi chuyển sang property ID | Hai node có thể mang cùng appId | Tạo và xác minh uniqueness constraint |
| Chỉ đổi code mà không backfill graph cũ | Entity cũ không tải được bằng mapping mới | Migrate dữ liệu trước cutover |

## Checklist chuyển đổi ID

1. Liệt kê mọi cách dùng internal ID và element ID trong Cypher, Java Driver, API và tích hợp.
2. Xác định ID mới là UUID surrogate hay business key bất biến.
3. Tạo uniqueness constraint cho property mới.
4. Deploy writer có khả năng gán ID mới cho node tạo sau cutover.
5. Backfill node cũ theo batch và transaction idempotent.
6. Kiểm tra node thiếu ID, duplicate và version field.
7. Chuyển mapping SDN sang property ID mới.
8. Chuyển API, event, cache, job và database ngoài sang ID mới.
9. Theo dõi fallback và consumer cũ trước khi gỡ compatibility.
10. Kiểm thử restore/import trên database khác để chứng minh ID mới vẫn ổn định.
11. Xóa phụ thuộc internal ID sau khi mọi tham chiếu đã chuyển.
12. Lưu kế hoạch rollback, snapshot và số liệu đối chiếu trước/sau.

Khi nâng cấp Neo4j và SDN, cần xem ID nội bộ, element ID và application ID là các hợp đồng khác nhau. `id()` và `elementId()` phục vụ việc định vị graph element trong database; UUID hoặc business key được lưu thành property mới có thể làm định danh lâu dài. Chuyển đổi an toàn đòi hỏi schema mở rộng, backfill có thể chạy lại, uniqueness constraint, version handling và chuyển mọi consumer trước khi ngừng hỗ trợ ID cũ.

Tài liệu tham khảo chính thức:

- [Spring Data Neo4j 8.2 - Handling and provisioning of unique IDs](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/mapping-ids.html)
- [Spring Data Neo4j 8.2 - Metadata-based mapping, @Id and @Version](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Neo4j Cypher Manual - elementId() and id()](https://neo4j.com/docs/cypher-manual/current/functions/scalar/)
- [Neo4j Java Driver Manual - Data types and mapping](https://neo4j.com/docs/java-manual/current/data-types/)

