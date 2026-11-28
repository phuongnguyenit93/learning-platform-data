# Ràng buộc tồn tại, kiểu property và node key theo edition/phiên bản

Neo4j là cơ sở dữ liệu graph có schema linh hoạt, nhưng linh hoạt không có nghĩa dữ liệu phải thiếu quy tắc. Trong ứng dụng Spring Data Neo4j (SDN), nhiều node có thể được tạo từ repository, `Neo4jTemplate`, `Neo4jClient`, script import hoặc một dịch vụ khác. Nếu mỗi đường ghi tự áp dụng quy ước riêng, graph dễ xuất hiện property bị thiếu, sai kiểu hoặc khóa định danh trùng lặp.

Neo4j cung cấp các **constraint** để database kiểm tra dữ liệu ngay tại thời điểm ghi. Bài này tập trung vào ba loại: **property existence constraint** bắt buộc property tồn tại, **property type constraint** giới hạn kiểu dữ liệu và **node key constraint** kết hợp tính bắt buộc với tính duy nhất. Các khả năng này phụ thuộc edition và phiên bản Neo4j, vì vậy cần xác minh môi trường triển khai trước khi viết migration.

## Constraint bảo vệ điều gì?

Giả sử hệ thống quản lý nhân viên và phòng ban. Mỗi node `Person` cần có mã nhân viên, email và tuổi:

~~~text
(:Person {
    employeeCode: "E-1042",
    email: "lan@example.test",
    age: 29
})
~~~

Các quy tắc dữ liệu có thể gồm:

- Mọi `Person` phải có `employeeCode`.
- `employeeCode` phải duy nhất trong các node mang label `Person`.
- `email`, nếu được lưu, phải là chuỗi.
- `age`, nếu được lưu, phải là số nguyên.
- Một node `Person` không được xóa thuộc tính bắt buộc hoặc cập nhật khóa thành giá trị đã được node khác sử dụng.

Nếu chỉ kiểm tra ở tầng Java, một script Cypher hoặc dịch vụ khác vẫn có thể ghi dữ liệu vi phạm. Constraint được database thực thi nên áp dụng cho mọi client có quyền ghi vào database đó.

Trong SDN, annotation như `@Id`, kiểu Java như `String` hoặc kiểm tra Bean Validation có ích ở tầng ứng dụng. Chúng không tự thay thế các constraint schema của Neo4j. `@Id` xác định cách SDN nhận diện entity; node key constraint xác định quy tắc toàn vẹn mà database áp dụng cho tất cả thao tác ghi.

## Phân biệt uniqueness, existence, type và node key

Bốn quy tắc thường bị nhầm lẫn:

| Constraint | Điều kiện được bảo đảm | Có bắt buộc property tồn tại? |
|---|---|---|
| Property uniqueness | Giá trị property hoặc tổ hợp property không trùng trong label/type được chỉ định | Không |
| Property existence | Property phải có trên mọi node của label hoặc relationship của type | Có |
| Property type | Nếu property có mặt, giá trị phải thuộc kiểu được khai báo | Không |
| Node key | Tất cả property trong key phải có và tổ hợp giá trị phải duy nhất trên label | Có |

Điểm quan trọng nhất là **uniqueness không đồng nghĩa với existence**. Với uniqueness constraint trên `Person.employeeCode`, các node `Person` không có `employeeCode` vẫn có thể tồn tại; constraint chỉ kiểm tra giá trị khi property được cung cấp. Node key constraint yêu cầu mỗi node `Person` phải có đủ các property trong key và không node nào có cùng tổ hợp giá trị.

Property type constraint cũng không tự bắt buộc property phải xuất hiện. Nếu một node không có `age`, nó không vi phạm constraint kiểu `INTEGER` trên `age`. Muốn `age` vừa bắt buộc vừa đúng kiểu, cần kết hợp existence constraint với type constraint, hoặc dùng một node key nếu thuộc tính đó cũng phải duy nhất.

## Khả năng theo edition và phiên bản Neo4j

Các constraint không có cùng mức hỗ trợ trên mọi edition. Bảng sau tóm tắt những mốc quan trọng trong dòng Neo4j 5.x:

| Khả năng | Community Edition | Enterprise Edition | Mốc phiên bản đáng chú ý |
|---|---|---|---|
| Node property uniqueness | Có | Có | Có từ các phiên bản Neo4j trước 5.x |
| Relationship property uniqueness | Có từ 5.7 | Có từ 5.7 | Neo4j 5.7 bổ sung constraint uniqueness cho relationship |
| Property existence | Không | Có | Có trong Neo4j 3.5 Enterprise và các bản sau |
| Property type | Không | Có | Giới thiệu từ Neo4j 5.9 |
| Node key | Không | Có | Có từ Neo4j 3.5 Enterprise |
| Relationship key | Không | Có | Giới thiệu từ Neo4j 5.7 |

Bảng này nói về các khả năng của Neo4j DBMS, không phải về annotation của SDN. Sản phẩm cloud hoặc gói dịch vụ được quản lý có thể đặt tên tier và quyền sử dụng khác nhau; hãy kiểm tra chính xác edition, license và phiên bản DBMS của môi trường thực tế.

Với Neo4j 5.x, property existence, property type và node key là các tính năng Enterprise. Community vẫn hỗ trợ property uniqueness constraint cho node và relationship; uniqueness cho relationship có từ Neo4j 5.7. Do đó, một migration tạo existence, type hoặc node key có thể chạy trên Enterprise nhưng thất bại trên Community. Tài liệu Neo4j 3.5 và 4.x nêu rõ database chứa existence constraint hoặc node key không thể mở bằng Community Edition; với bản 5.x hoặc dịch vụ managed, hãy xác nhận quy tắc tương thích trong hướng dẫn upgrade của phiên bản đích.

Property type constraint được bổ sung ở Neo4j 5.9; các kiểu LIST được hỗ trợ từ 5.10 và closed dynamic union từ 5.11. Hàm `valueType()` được bổ sung ở 5.13. Relationship key và relationship uniqueness được bổ sung ở Neo4j 5.7. Nếu hệ thống còn chạy Neo4j 4.x hoặc cũ hơn, cần dùng đúng cú pháp và khả năng của phiên bản đó; không sao chép cú pháp `FOR ... REQUIRE` của Neo4j 5 vào migration cũ mà chưa kiểm tra.

Khi nâng cấp hoặc chuyển edition:

1. Xác định phiên bản DBMS đang chạy, không chỉ phiên bản dependency của Neo4j Java Driver.
2. Xác nhận edition/license ở từng môi trường development, test, staging và production.
3. Kiểm tra constraint hiện hữu bằng `SHOW CONSTRAINTS`.
4. Xác minh target edition có thể mở database và hỗ trợ mọi constraint đã tạo.
5. Chạy migration trên database thử nghiệm có dữ liệu đại diện trước khi triển khai.

## Property existence constraint

Property existence constraint yêu cầu một property xuất hiện trên mọi node có label được chỉ định hoặc mọi relationship có type được chỉ định. Ví dụ, mọi `Person` phải có `employeeCode`:

~~~cypher
CREATE CONSTRAINT person_employee_code_exists
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.employeeCode IS NOT NULL;
~~~

Nếu một câu lệnh tạo `Person` không có `employeeCode`, database từ chối thao tác. Tương tự, thao tác xóa property này khỏi node cũng bị từ chối.

Có thể đặt existence constraint cho property trên relationship:

~~~cypher
CREATE CONSTRAINT works_on_role_exists
IF NOT EXISTS
FOR ()-[r:WORKS_ON]-()
REQUIRE r.role IS NOT NULL;
~~~

Mọi relationship `WORKS_ON` phải có property `role`. Constraint này không yêu cầu một node cụ thể phải có relationship `WORKS_ON`; nó chỉ áp dụng cho những relationship thuộc type đó khi chúng tồn tại.

Property existence constraint chỉ áp dụng cho một property trong mỗi constraint. Nếu cần bắt buộc nhiều property, tạo một constraint riêng cho từng property hoặc cân nhắc node key nếu các property cũng phải duy nhất theo tổ hợp.

### Kiểm tra dữ liệu trước khi thêm existence constraint

Constraint không tự điền dữ liệu còn thiếu. Trước khi tạo, hãy tìm node vi phạm:

~~~cypher
MATCH (p:Person)
WHERE p.employeeCode IS NULL
RETURN p;
~~~

Đếm số node thiếu property:

~~~cypher
MATCH (p:Person)
WHERE p.employeeCode IS NULL
RETURN count(p) AS missingEmployeeCode;
~~~

Sau khi tìm được dữ liệu thiếu, cần xác định nguồn giá trị chính xác. Có thể bổ sung dữ liệu bằng migration dựa trên nguồn nghiệp vụ đáng tin cậy. Không tạo mã giả ngẫu nhiên chỉ để câu lệnh constraint chạy thành công nếu mã đó sẽ được dùng làm định danh nghiệp vụ.

Khi dữ liệu đã được làm sạch, chạy lại truy vấn kiểm tra và sau đó mới tạo constraint. Đây là bước cần thiết vì Neo4j kiểm tra dữ liệu hiện có khi xây dựng constraint; nếu dữ liệu vi phạm, lệnh tạo constraint sẽ thất bại.

## Property type constraint

Property type constraint yêu cầu giá trị của một property, khi property xuất hiện, phải có kiểu Cypher đã chỉ định. Ví dụ `Person.age` nếu có phải là số nguyên:

~~~cypher
CREATE CONSTRAINT person_age_type
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.age IS :: INTEGER;
~~~

Ví dụ `Person.email` nếu có phải là chuỗi:

~~~cypher
CREATE CONSTRAINT person_email_type
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS :: STRING;
~~~

Cú pháp `IS :: INTEGER` là cú pháp property type constraint của Neo4j 5.9 trở lên. Tài liệu Cypher có thể mô tả các biến thể cú pháp tương đương theo phiên bản, chẳng hạn `IS TYPED`. Hãy dùng cú pháp được hỗ trợ bởi phiên bản target và giữ cú pháp thống nhất trong migration.

Property type constraint không có nghĩa mọi `Person` phải có `age` hoặc `email`. Node không có property đó không bị constraint kiểu này từ chối. Nếu property xuất hiện với kiểu khác, ví dụ `age: "29"` thay vì `age: 29`, thao tác ghi sẽ thất bại.

Các kiểu dữ liệu có thể dùng bao gồm những kiểu property của Cypher như `STRING`, `INTEGER`, `FLOAT`, `BOOLEAN`, các kiểu temporal, `POINT` và các dạng `LIST` được hỗ trợ. Danh sách kiểu và cấu trúc union phụ thuộc phiên bản. Đặc biệt, property type constraint có hỗ trợ thêm kiểu dữ liệu và closed union ở các bản Neo4j 5.x sau này; hãy tham chiếu tài liệu phiên bản cụ thể trước khi dùng cú pháp nâng cao.

### Kết hợp existence và type

Nếu `Person.email` vừa bắt buộc vừa phải là chuỗi, tạo cả hai constraint:

~~~cypher
CREATE CONSTRAINT person_email_exists
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS NOT NULL;

CREATE CONSTRAINT person_email_type
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS :: STRING;
~~~

Khi đó:

- Thiếu `email` vi phạm existence.
- `email: 12345` vi phạm type.
- `email: "lan@example.test"` thỏa cả hai điều kiện.

Nếu chỉ cần `email` đúng kiểu khi có giá trị, không tạo existence constraint. Việc bắt buộc property nên xuất phát từ quy tắc nghiệp vụ, không phải vì mọi field Java đều có getter.

## Node key constraint

Node key constraint kết hợp hai điều kiện trên một label:

1. Mọi node mang label đó phải có đủ các property thuộc key.
2. Tổ hợp giá trị của các property đó phải duy nhất.

Ví dụ, mã nhân viên phải có và không trùng:

~~~cypher
CREATE CONSTRAINT person_employee_code_key
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.employeeCode IS NODE KEY;
~~~

Nếu hai node `Person` có cùng `employeeCode`, database từ chối ghi node trùng. Nếu node không có `employeeCode`, database cũng từ chối.

Node key có thể gồm nhiều property. Ví dụ một mã nhân viên chỉ duy nhất trong từng tenant, nên khóa là tổ hợp `tenantId` và `employeeCode`:

~~~cypher
CREATE CONSTRAINT person_tenant_employee_key
IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.employeeCode) IS NODE KEY;
~~~

Với composite node key, tất cả property trong tuple đều bắt buộc và tổ hợp giá trị phải duy nhất. Hai node có cùng `employeeCode` nhưng khác `tenantId` có thể cùng tồn tại; hai node có cùng cả `tenantId` và `employeeCode` thì không.

Node key thường phù hợp với định danh nghiệp vụ có phạm vi rõ ràng, đặc biệt khi hệ thống multi-tenant hoặc khi một node được định danh bởi nhiều thuộc tính. Nếu chỉ cần uniqueness mà property được phép vắng mặt, dùng uniqueness constraint. Nếu cần existence mà không cần uniqueness, dùng existence constraint.

### Node key và @Id trong SDN

Trong entity SDN, `@Id` đánh dấu property Java mà repository dùng làm ID entity. Điều đó không tự tạo node key constraint trong Neo4j:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String fullName;
}
~~~

Nếu nghiệp vụ yêu cầu `employeeCode` phải tồn tại và duy nhất trong database, cần tạo constraint bằng Cypher migration:

~~~cypher
CREATE CONSTRAINT person_employee_code_key
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.employeeCode IS NODE KEY;
~~~

Constraint được database áp dụng cho cả thao tác từ SDN lẫn Cypher trực tiếp. Khi repository lưu entity có `employeeCode` thiếu hoặc trùng, thao tác có thể thất bại do vi phạm constraint. Tầng service nên chuyển lỗi đó thành phản hồi nghiệp vụ phù hợp, nhưng không được giả định rằng validation phía Java là lớp bảo vệ duy nhất.

## Node key khác với uniqueness constraint như thế nào?

Ví dụ uniqueness constraint trên một property:

~~~cypher
CREATE CONSTRAINT person_employee_code_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.employeeCode IS UNIQUE;
~~~

Constraint này từ chối hai node `Person` có cùng giá trị `employeeCode`. Tuy nhiên, node `Person` không có property `employeeCode` vẫn không thuộc phạm vi kiểm tra uniqueness. Vì vậy, uniqueness phù hợp khi property có thể vắng mặt nhưng nếu có thì không được trùng.

Ví dụ hai node:

~~~cypher
CREATE (:Person {fullName: "Lan Nguyen"});
CREATE (:Person {fullName: "Minh Tran"});
~~~

Nếu chỉ có uniqueness constraint trên `employeeCode`, hai node không có property này không vi phạm uniqueness. Nếu có node key trên `employeeCode`, cả hai node đều vi phạm vì thiếu property.

Bảng sau tóm tắt:

| Tình huống | Uniqueness | Node key |
|---|---|---|
| Property bị thiếu | Có thể chấp nhận | Bị từ chối |
| Property có giá trị trùng | Bị từ chối | Bị từ chối |
| Property có giá trị khác | Chấp nhận | Chấp nhận |
| Composite properties | Hỗ trợ | Hỗ trợ |
| Có bảo đảm tồn tại và duy nhất cùng lúc | Không | Có |

Cả uniqueness và node key constraint đều được hỗ trợ bởi index. Neo4j tạo index cần thiết cùng constraint; không tạo thêm một range index trùng lặp trên cùng schema chỉ vì đã có uniqueness hoặc key constraint. Property existence và property type constraint không phải là index-backed constraint.

## Constraint trên relationship và node

Các constraint existence và type có thể áp dụng cho cả node và relationship. Node key được dùng để xác định danh tính node theo label và property; Neo4j 5.7 trở lên còn hỗ trợ relationship key cho định danh relationship theo type và property.

Ví dụ bắt buộc `role` trên relationship:

~~~cypher
CREATE CONSTRAINT works_on_role_exists
IF NOT EXISTS
FOR ()-[r:WORKS_ON]-()
REQUIRE r.role IS NOT NULL;
~~~

Ví dụ giới hạn kiểu của property trên relationship:

~~~cypher
CREATE CONSTRAINT works_on_since_type
IF NOT EXISTS
FOR ()-[r:WORKS_ON]-()
REQUIRE r.since IS :: DATE;
~~~

Nếu hệ thống cần nhận diện duy nhất từng relationship `WORKS_ON` theo một mã, có thể cân nhắc relationship key trên Neo4j 5.7 Enterprise trở lên:

~~~cypher
CREATE CONSTRAINT works_on_assignment_key
IF NOT EXISTS
FOR ()-[r:WORKS_ON]-()
REQUIRE r.assignmentId IS RELATIONSHIP KEY;
~~~

Relationship key yêu cầu property `assignmentId` tồn tại và duy nhất trong các relationship thuộc type `WORKS_ON`. Không nhầm relationship key với node key; chúng áp dụng lên hai loại graph element khác nhau. Nếu target version chưa hỗ trợ relationship key, cần thiết kế định danh qua node trung gian hoặc một mô hình khác được phiên bản đó hỗ trợ.

## Tạo, liệt kê và xóa constraint

Nên đặt tên rõ ràng cho constraint. Tên phải duy nhất trong phạm vi tên constraint và index của database. Ví dụ tên có thể chứa label/type, property và mục đích:

- `person_employee_code_key`
- `person_email_exists`
- `person_age_type`
- `works_on_role_exists`

`IF NOT EXISTS` giúp migration có thể chạy lại trong một số trường hợp:

~~~cypher
CREATE CONSTRAINT person_email_exists
IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email IS NOT NULL;
~~~

Tuy nhiên, `IF NOT EXISTS` không sửa constraint cũ có định nghĩa khác. Nếu đã có constraint cùng tên hoặc constraint cùng loại trên cùng schema, Neo4j không tạo constraint mới; từ Neo4j 5.17, trường hợp không thay đổi này có thể kèm informational notification. Một số loại constraint không thể cùng tồn tại trên cùng schema, chẳng hạn property uniqueness và key constraint; xung đột với index cũng cần được xử lý riêng. Vì vậy, cần kiểm tra schema trước và sau migration thay vì coi `IF NOT EXISTS` là công cụ đồng bộ định nghĩa.

Liệt kê constraint:

~~~cypher
SHOW CONSTRAINTS;
~~~

Xem đầy đủ cột kết quả:

~~~cypher
SHOW CONSTRAINTS YIELD *;
~~~

Có thể kiểm tra index được tạo kèm constraint bằng:

~~~cypher
SHOW INDEXES;
~~~

Xóa constraint bằng tên:

~~~cypher
DROP CONSTRAINT person_email_exists IF EXISTS;
~~~

Xóa constraint có thể làm database chấp nhận dữ liệu mà trước đó bị ngăn chặn. Trước khi drop, xác định lý do thay đổi schema và bảo đảm ứng dụng không còn phụ thuộc quy tắc đó. Nếu constraint uniqueness hoặc key đang sở hữu index, index liên quan cũng được quản lý cùng constraint; hãy kiểm tra nhu cầu truy vấn trước khi thay thế bằng index độc lập.

## Chuẩn bị dữ liệu trước khi tạo constraint

Tạo constraint trên graph đã có dữ liệu có thể thất bại nếu graph vi phạm quy tắc mới. Hãy chạy các truy vấn kiểm tra trước.

### Tìm property bị thiếu

~~~cypher
MATCH (p:Person)
WHERE p.employeeCode IS NULL
RETURN p;
~~~

### Tìm giá trị bị trùng

~~~cypher
MATCH (p:Person)
WHERE p.employeeCode IS NOT NULL
WITH p.employeeCode AS employeeCode, count(*) AS occurrences
WHERE occurrences > 1
RETURN employeeCode, occurrences
ORDER BY occurrences DESC;
~~~

### Tìm sai kiểu dữ liệu

Từ Neo4j 5.13, có thể kiểm tra giá trị trước migration bằng `valueType()`. Hàm trả về cả thông tin nullability, vì vậy một số nguyên có kiểu là `INTEGER NOT NULL`:

~~~cypher
MATCH (p:Person)
WHERE p.age IS NOT NULL
  AND valueType(p.age) <> "INTEGER NOT NULL"
RETURN p.employeeCode, p.age, valueType(p.age);
~~~

Nếu target thấp hơn Neo4j 5.13, không dùng truy vấn này; hãy kiểm tra kiểu bằng type predicate được hỗ trợ ở phiên bản đó hoặc đọc dữ liệu qua công cụ quản trị/script migration có kiểm soát. Với các kiểu phức tạp như LIST và union, kiểm tra cả kiểu phần tử theo đúng hợp đồng schema.

### Quy trình migration đề xuất

1. **Inventory:** liệt kê constraint và index hiện tại bằng `SHOW CONSTRAINTS` và `SHOW INDEXES`.
2. **Preflight:** tìm property thiếu, giá trị trùng và giá trị sai kiểu.
3. **Data cleanup:** chuẩn hóa hoặc bổ sung dữ liệu dựa trên nguồn nghiệp vụ đáng tin cậy.
4. **Create:** tạo constraint có tên rõ ràng bằng migration versioned.
5. **Verify:** chạy lại truy vấn kiểm tra và `SHOW CONSTRAINTS`.
6. **Application test:** thử ghi hợp lệ, ghi thiếu property, ghi sai kiểu và ghi trùng.
7. **Deployment:** xác nhận edition và phiên bản ở môi trường đích hỗ trợ constraint trước khi triển khai.
8. **Rollback plan:** chuẩn bị cách khôi phục schema và dữ liệu nếu migration cần được đảo ngược.

Không xóa hoặc thay đổi dữ liệu vi phạm một cách tự động nếu chưa biết giá trị đúng. Ví dụ, hai nhân viên trùng mã có thể là dữ liệu import sai hoặc là hai người thuộc hai tenant khác nhau; giải pháp đúng có thể là composite node key chứ không phải xóa một node.

## Tương tác với MERGE và thao tác ghi từ SDN

`MERGE` tìm hoặc tạo pattern, nhưng không thay thế constraint. Trong môi trường có nhiều transaction đồng thời, `MERGE` một pattern mà không có constraint phù hợp không tự bảo đảm dữ liệu không bị tạo trùng trong mọi tình huống cạnh tranh. Constraint uniqueness hoặc node key giúp database bảo vệ định danh và từ chối ghi trùng.

Ví dụ:

~~~cypher
MERGE (p:Person {employeeCode: $employeeCode})
ON CREATE SET p.fullName = $fullName
ON MATCH SET p.fullName = $fullName;
~~~

Nếu `employeeCode` là định danh bắt buộc và duy nhất, tạo node key constraint tương ứng. Khi đó mọi đường ghi, kể cả repository SDN và Cypher trực tiếp, phải tuân theo cùng một quy tắc.

Trong SDN, một entity có thể được lưu qua repository:

~~~java
Person saved = personRepository.save(person);
~~~

Nếu thao tác này tạo node không thỏa constraint, Neo4j từ chối transaction. Ứng dụng cần xử lý lỗi database một cách phù hợp. Không nên bắt lỗi rồi tiếp tục coi entity đã được lưu thành công. Đối với bulk import, hãy xác thực và làm sạch dữ liệu trước khi gửi nhiều batch để tránh một constraint violation khiến batch hoặc transaction thất bại.

## Lựa chọn constraint theo quy tắc nghiệp vụ

| Quy tắc nghiệp vụ | Constraint nên xem xét |
|---|---|
| Mỗi Person phải có `employeeCode` | Existence |
| `employeeCode` không được trùng nhưng có thể thiếu ở một số loại node | Uniqueness |
| Mỗi Person bắt buộc có `employeeCode` và mã phải duy nhất | Node key |
| `age`, nếu có, phải là INTEGER | Property type |
| `email` bắt buộc và phải là STRING | Existence + property type |
| Một Person được định danh bởi `tenantId` và `employeeCode` | Composite node key |
| Mọi relationship `WORKS_IN` phải có `role` | Relationship existence |
| `since`, nếu có trên `WORKS_IN`, phải là DATE | Relationship property type |
| Mỗi assignment relationship có `assignmentId` duy nhất và bắt buộc | Relationship key nếu Neo4j 5.7+ Enterprise hỗ trợ |

Chọn constraint theo yêu cầu dữ liệu thực tế. Không biến mọi property thành bắt buộc nếu domain cho phép giá trị chưa biết. Ví dụ `middleName` có thể không có; tạo existence constraint cho field này sẽ buộc mọi writer phải cung cấp một giá trị không có ý nghĩa.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nhầm uniqueness với node key | Node thiếu property vẫn có thể được tạo | Dùng node key khi vừa cần tồn tại vừa cần duy nhất |
| Cho rằng property type bắt buộc property xuất hiện | Node thiếu property vẫn không vi phạm type constraint | Kết hợp existence với type khi cần |
| Tạo existence/type/key trên Community | Lệnh không được hỗ trợ | Kiểm tra edition/license; các loại này cần Enterprise trong Neo4j 5.x |
| Dùng property type constraint trên Neo4j trước 5.9 | Phiên bản không hỗ trợ cú pháp | Nâng phiên bản hoặc kiểm tra dữ liệu ở tầng ứng dụng |
| Dùng relationship key trước Neo4j 5.7 | Không có khả năng constraint tương ứng | Dùng mô hình khác hoặc nâng phiên bản |
| Tạo constraint khi dữ liệu cũ còn vi phạm | Migration thất bại | Chạy preflight, sửa dữ liệu rồi tạo constraint |
| Dùng `IF NOT EXISTS` như công cụ sửa schema | Constraint xung đột vẫn có thể còn nguyên | Kiểm tra `SHOW CONSTRAINTS` và so sánh định nghĩa |
| Tạo index riêng trùng với index do key/uniqueness sở hữu | Schema dư thừa hoặc tạo index thất bại | Kiểm tra index được constraint quản lý |
| Cho rằng `@Id` tự tạo node key | Database không được bảo vệ như mong đợi | Tạo constraint bằng Cypher migration |
| Tin rằng `MERGE` thay thế uniqueness | Có nguy cơ duplicate dưới tải đồng thời | Kết hợp MERGE với constraint phù hợp |
| Xóa constraint mà không đánh giá writer | Dữ liệu không hợp lệ có thể được ghi trở lại | Có kế hoạch thay thế và giám sát trước khi drop |

## Bài tập thực hành

Với graph quản lý `Person`, `Department` và relationship `WORKS_IN`, hãy thực hiện:

1. Tạo node Person có `employeeCode`, `email`, `age`; thử ghi một node thiếu `employeeCode`.
2. Tạo property uniqueness constraint cho `employeeCode` và thử tạo hai Person cùng mã.
3. Tạo existence constraint cho `employeeCode`; so sánh hành vi với uniqueness constraint.
4. Tạo property type constraint để `age`, nếu có, phải là INTEGER; thử ghi `age: "29"`.
5. Kết hợp existence và type cho `email`; thử ghi node thiếu email và node có email dạng số.
6. Tạo node key constraint trên `employeeCode` và xác nhận nó bảo đảm cả existence lẫn uniqueness.
7. Tạo composite node key trên `(tenantId, employeeCode)`; thử hai node cùng employeeCode nhưng khác tenant.
8. Tạo existence/type constraint cho property `role` và `since` của relationship `WORKS_IN`.
9. Chạy `SHOW CONSTRAINTS` và `SHOW INDEXES`, xác định constraint nào có index đi kèm.
10. Trên một database test có dữ liệu thiếu, trùng và sai kiểu, chạy preflight rồi làm sạch trước khi tạo constraint.
11. Kiểm tra edition và phiên bản DBMS; ghi lại loại constraint nào chạy được trên Community và loại nào yêu cầu Enterprise.
12. Lưu một Person bằng `Neo4jRepository` và một Person bằng Cypher trực tiếp; xác nhận database constraint áp dụng giống nhau cho cả hai.

Khi thiết kế schema cho ứng dụng SDN, hãy mô tả rõ property nào bắt buộc, property nào phải đúng kiểu và thuộc tính nào tạo thành định danh duy nhất. Dùng existence, type hoặc node key đúng với quy tắc nghiệp vụ; kiểm tra edition/phiên bản trước khi migration và làm sạch dữ liệu cũ trước khi bật constraint. Các quy tắc được thực thi ở Neo4j sẽ bảo vệ graph nhất quán qua repository, template, Cypher và những client khác.

Tài liệu tham khảo chính thức:

- [Neo4j Cypher Manual - Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Constraint syntax and version notes](https://neo4j.com/docs/cypher-manual/5/constraints/syntax/)
- [Neo4j 4.4 - Constraints and edition support](https://neo4j.com/docs/cypher-manual/4.4/constraints/)
- [Neo4j 3.5 - Constraints](https://neo4j.com/docs/cypher-manual/3.5/schema/constraints/)
- [Cypher scalar functions - valueType()](https://neo4j.com/docs/cypher-manual/current/functions/scalar/)
- [Neo4j MERGE and constraints](https://neo4j.com/docs/cypher-manual/5/clauses/merge/)

