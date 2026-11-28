# ID tự gán từ nghiệp vụ và ràng buộc duy nhất tương ứng

Trong nhiều hệ thống, mã định danh của một thực thể đã được cấp từ nghiệp vụ hoặc từ hệ thống nguồn. Ví dụ, khách hàng có `customerCode`, nhân viên có `employeeNumber`, sản phẩm có `sku`, còn người trong danh mục phim có `personId` do hệ thống quản lý nội dung cung cấp. Khi lưu các thực thể này vào Neo4j bằng Spring Data Neo4j (SDN), ứng dụng có thể dùng chính mã đó làm ID của node.

ID nghiệp vụ cần ổn định, được gán trước khi lưu và duy nhất trong phạm vi mà nghiệp vụ quy định. Ở phía Java, ta đánh dấu trường đó bằng `@Id` của Spring Data Commons và không dùng `@GeneratedValue` của SDN. Ở phía Neo4j, ta tạo uniqueness constraint trên label và property tương ứng để cơ sở dữ liệu bảo vệ tính duy nhất, kể cả khi có nhiều tiến trình ghi đồng thời.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung vào mô hình hóa node, ánh xạ định danh và quản lý dữ liệu đồ thị an toàn. Ví dụ dùng `Person` với mã `personId` do hệ thống nghiệp vụ cấp.

## 1. ID nghiệp vụ là gì?

ID nghiệp vụ là mã định danh có ý nghĩa trong miền nghiệp vụ hoặc được cấp bởi một hệ thống có thẩm quyền. Ví dụ:

| Thực thể | ID nghiệp vụ minh họa | Đặc điểm |
|---|---|---|
| Người | `P-1042` | Mã hồ sơ do hệ thống danh mục cấp |
| Khách hàng | `CUS-00871` | Mã khách hàng dùng trong CRM |
| Sản phẩm | `SKU-CHAIR-042` | Mã hàng trong hệ thống quản lý sản phẩm |
| Phim | `MOV-1999-001` | Mã phim từ nguồn dữ liệu nội dung |

ID nghiệp vụ thường có các đặc tính:

- Được tạo bởi một hệ thống hoặc quy trình nghiệp vụ có thẩm quyền.
- Có quy tắc định dạng và phạm vi duy nhất rõ ràng.
- Không thay đổi khi các thuộc tính mô tả thay đổi, chẳng hạn tên người hoặc tiêu đề phim.
- Được truyền nhất quán giữa API, dịch vụ và các hệ thống tích hợp.

Không nên dùng tên, email hoặc thuộc tính có thể thay đổi làm ID chỉ vì chúng đang có vẻ duy nhất. Ví dụ, `Person.name` có thể trùng hoặc đổi theo thời gian; mã `personId` được quản lý riêng thường phù hợp hơn để định danh node.

## 2. Phân biệt ID nghiệp vụ với internal ID của Neo4j

Neo4j quản lý định danh nội bộ cho node và relationship. Internal ID phục vụ việc quản lý dữ liệu bên trong database, nhưng không nên được xem là mã nghiệp vụ ổn định để lưu trong hệ thống bên ngoài hoặc công khai trong API. Việc xóa và tạo lại node, di chuyển dữ liệu hoặc thay đổi cách lưu trữ có thể làm giả định về internal ID trở nên không an toàn.

ID nghiệp vụ là property do ứng dụng quản lý, ví dụ `personId = "P-1042"`. Khi ánh xạ bằng SDN, property này có thể đồng thời là ID của entity Java. Cách tiếp cận đó giúp ứng dụng tìm node theo mã nghiệp vụ mà không phụ thuộc vào internal ID.

| Tiêu chí | Internal ID Neo4j | ID nghiệp vụ |
|---|---|---|
| Nguồn tạo | Neo4j | Hệ thống hoặc quy trình nghiệp vụ |
| Ý nghĩa | Định danh nội bộ của database | Định danh trong miền nghiệp vụ |
| Quản lý | Database | Ứng dụng và quy tắc nghiệp vụ |
| Dùng trong API/tích hợp | Không nên phụ thuộc | Phù hợp nếu được thiết kế ổn định |
| Ràng buộc duy nhất | Database quản lý nội bộ | Cần khai báo constraint trên property nghiệp vụ |

## 3. Ánh xạ ID được gán sẵn trong Spring Data Neo4j

Với ID do nghiệp vụ cấp, dùng `@Id` và bỏ `@GeneratedValue`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Version
    private Long version;

    private String name;
    private Integer born;

    public Person(String personId, String name, Integer born) {
        this.personId = personId;
        this.name = name;
        this.born = born;
    }

    public String getPersonId() {
        return personId;
    }

    public String getName() {
        return name;
    }
}
```

Trong ví dụ:

- `@Node("Person")` ánh xạ lớp thành node có label `Person`.
- `@Id` đến từ `org.springframework.data.annotation.Id` và đánh dấu trường định danh entity.
- `personId` được gán từ nghiệp vụ trước khi gọi repository.
- Không có `@GeneratedValue`, vì SDN không cần sinh mã này.
- `@Version` là metadata Spring Data Commons dùng cho optimistic locking và cũng giúp Spring Data nhận diện trạng thái mới của entity khi trường version dạng đối tượng còn `null`.

Với cách ánh xạ mặc định, tên property trong Neo4j trùng với tên trường Java, do đó node có property `personId`. Nếu cần tên property khác, có thể dùng `@Property` của SDN để chỉ định rõ tên lưu trữ; khi đó uniqueness constraint phải dùng đúng tên property thực tế trong Neo4j.

Repository khai báo kiểu ID khớp với kiểu trường `@Id`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

Ứng dụng có thể tạo đối tượng với mã đã được cấp và lưu:

```java
Person person = new Person("P-1042", "Nguyen An", 1992);
personRepository.save(person);
```

`findById("P-1042")` sẽ tìm entity theo trường ID mà SDN ánh xạ. Hãy bảo đảm mã đã được xác thực, chuẩn hóa và không rỗng trước khi tạo entity.

### 3.1. Lưu ý về nhận diện entity mới

Với ID tự gán, trường `@Id` đã có giá trị ngay cả trước lần lưu đầu tiên. Cơ chế nhận diện entity mới mặc định của Spring Data có thể dựa trên giá trị ID; vì vậy một ID khác `null` có thể khiến entity bị xem là đã tồn tại. Nếu không cấu hình trạng thái mới phù hợp, thao tác `save` có thể đi theo nhánh cập nhật thay vì tạo node mới.

Trong ví dụ trên, `@Version` dùng kiểu đối tượng `Long` và để `null` trước lần lưu đầu. Cơ chế nhận diện trạng thái mới dựa trên version có thể xác định entity chưa được lưu; SDN quản lý giá trị version trong quá trình ghi và dùng nó để phát hiện cập nhật cạnh tranh. Không tự gán hoặc tự tăng version trong logic nghiệp vụ.

Một lựa chọn khác là triển khai `Persistable<ID>` và cung cấp `isNew()` theo vòng đời entity. Cách này phù hợp khi ứng dụng có quy tắc quản lý trạng thái mới riêng, nhưng cần bảo đảm cờ `isNew` được chuyển đúng sau khi lưu và khi tải entity từ database. Không nên chỉ dựa vào một cờ boolean khởi tạo `true` mà không có cơ chế cập nhật trạng thái sau persistence.

## 4. Tạo uniqueness constraint trong Neo4j

`@Id` giúp SDN xác định trường định danh của entity, nhưng không thay thế ràng buộc duy nhất trong database. Hãy tạo constraint trên đúng label và property mà entity sử dụng:

```cypher
CREATE CONSTRAINT person_person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Constraint này bảo đảm không có hai node mang label `Person` cùng một giá trị `personId` khác `null`. Neo4j tạo index hỗ trợ cho uniqueness constraint, giúp tra cứu theo property đó hiệu quả hơn.

Phạm vi của constraint gắn với label. Ví dụ, `Person.personId = "P-1042"` và `Movie.movieId = "P-1042"` có thể cùng tồn tại nếu hai label có constraint riêng; chúng thuộc hai loại thực thể khác nhau. Nếu nghiệp vụ yêu cầu duy nhất toàn cục giữa nhiều loại node, cần thiết kế một miền định danh chung hoặc mô hình hóa quy tắc đó bằng kiến trúc dữ liệu phù hợp.

Tạo constraint một lần qua quy trình migration hoặc triển khai schema có kiểm soát. Không chạy lệnh tạo constraint trong mỗi request. Nếu database đã có dữ liệu trùng, lệnh tạo constraint sẽ thất bại; cần kiểm tra và xử lý dữ liệu trước khi áp dụng.

### 4.1. Kiểm tra dữ liệu trước khi tạo constraint

Tìm các mã `personId` bị trùng:

```cypher
MATCH (p:Person)
WHERE p.personId IS NOT NULL
WITH p.personId AS personId, count(*) AS occurrences
WHERE occurrences > 1
RETURN personId, occurrences
ORDER BY occurrences DESC;
```

Kiểm tra node chưa có mã:

```cypher
MATCH (p:Person)
WHERE p.personId IS NULL
RETURN count(p) AS peopleWithoutBusinessId;
```

Uniqueness constraint không buộc mọi node phải có property. Các node thiếu `personId` không vi phạm uniqueness constraint, vì vậy ứng dụng cần xác thực mã bắt buộc ở tầng nghiệp vụ. Nếu edition và phiên bản Neo4j hỗ trợ node key hoặc property existence constraint, có thể dùng thêm loại constraint đó để buộc property phải tồn tại.

## 5. ID duy nhất theo tenant hoặc hệ thống nguồn

Không phải ID nào cũng duy nhất trên toàn bộ hệ thống. Ví dụ, hai tenant có thể cùng cấp mã `A-100`, hoặc hai hệ thống nguồn có thể cùng phát hành mã `P-001`. Khi đó, khóa nghiệp vụ thực tế là tổ hợp nhiều thuộc tính, chẳng hạn `(tenantId, externalId)` hoặc `(sourceSystem, sourceId)`.

Neo4j hỗ trợ uniqueness constraint trên nhiều property:

```cypher
CREATE CONSTRAINT person_tenant_external_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.externalId) IS UNIQUE;
```

Constraint này bảo đảm không có hai node `Person` cùng tổ hợp giá trị. Tuy nhiên, uniqueness constraint cho phép property bị thiếu hoặc `null`; nếu cần cả tính bắt buộc tồn tại, hãy kiểm tra hỗ trợ của node key/property existence constraint trong edition Neo4j đang triển khai.

SDN repository có một trường `@Id` làm định danh entity. Nếu khóa nghiệp vụ là tổ hợp, đừng tùy tiện đánh dấu riêng `externalId` làm `@Id` khi nó chỉ duy nhất trong từng tenant. Có thể tạo một khóa đơn đã chuẩn hóa, ví dụ `personKey` được tạo từ tenant và mã nguồn, dùng nó làm `@Id`, đồng thời vẫn giữ `tenantId` và `externalId` như các property riêng để truy vấn nghiệp vụ. Hoặc dùng truy vấn tùy chỉnh theo cả hai property thay vì giả định một thành phần đơn lẻ là ID toàn cục.

Khi tạo khóa ghép thành chuỗi, cần dùng quy tắc mã hóa không nhập nhằng. Ghép bằng dấu phân cách tùy tiện có thể tạo va chạm nếu thành phần cũng chứa dấu đó. Có thể dùng UUID xác định từ cặp giá trị đã chuẩn hóa, hoặc một định dạng length-prefix có quy tắc rõ ràng.

## 6. Dùng MERGE với ID nghiệp vụ

`MERGE` phù hợp khi cần tìm node theo ID nghiệp vụ hoặc tạo node nếu chưa tồn tại:

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET
    p.name = $name,
    p.born = $born
ON MATCH SET
    p.name = $name,
    p.born = $born
RETURN p;
```

`$personId`, `$name` và `$born` là tham số. Mẫu `MERGE` chỉ chứa khóa định danh ổn định `personId`; thuộc tính mô tả được cập nhật riêng. Cách này tránh vô tình tạo node mới khi tên hoặc năm sinh thay đổi.

Nếu dùng các thuộc tính thay đổi được trong mẫu `MERGE`, chẳng hạn `MERGE (p:Person {personId: $personId, name: $name})`, một lần gọi với tên mới có thể không khớp node cũ và dẫn đến xung đột uniqueness hoặc tạo dữ liệu không như mong muốn. Hãy xác định rõ property nào thực sự tạo thành identity.

`MERGE` giúp câu lệnh có tính upsert theo mẫu, nhưng không thay thế uniqueness constraint. Constraint là lớp bảo vệ cuối cùng ở database, đặc biệt quan trọng khi nhiều request hoặc service có thể ghi cùng một ID đồng thời. Dùng cả `MERGE` và constraint để bảo vệ tính duy nhất ở tầng truy vấn lẫn tầng lưu trữ.

## 7. Kết hợp repository và constraint

Một repository dùng ID kiểu `String` có thể cung cấp các thao tác tìm kiếm cơ bản:

```java
public interface PersonRepository extends Neo4jRepository<Person, String> {

    Optional<Person> findByName(String name);
}
```

Ví dụ service nhận ID từ nghiệp vụ:

```java
@Service
public class PersonService {

    private final PersonRepository personRepository;

    public PersonService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    public Person registerPerson(String personId, String name, Integer born) {
        if (personId == null || personId.isBlank()) {
            throw new IllegalArgumentException("personId is required");
        }

        Person person = new Person(personId, name, born);
        return personRepository.save(person);
    }
}
```

Đây là ví dụ rút gọn; constructor, getter, cấu hình transaction và xử lý lỗi nghiệp vụ cần được hoàn thiện theo ứng dụng. Nếu một ID đã tồn tại, nghiệp vụ phải quyết định đó là yêu cầu cập nhật hợp lệ, bản ghi gửi lặp cần trả lại kết quả cũ hay một xung đột cần báo lỗi. Không nên âm thầm ghi đè dữ liệu chỉ vì `save` được gọi.

Khi dùng `save` với entity ID tự gán, hãy kiểm tra chiến lược nhận diện entity mới như phần trước. Nếu ứng dụng muốn upsert theo ID bằng Cypher, có thể khai báo `@Query` trên repository hoặc dùng `Neo4jClient`; cần ánh xạ kết quả về kiểu phù hợp và quản lý transaction nhất quán.

## 8. Các nguyên tắc thiết kế ID

1. **Chọn nguồn cấp mã có thẩm quyền.** Mỗi loại ID cần một nơi chịu trách nhiệm phát hành để các service không tự tạo mã trùng nhau.
2. **Giữ mã ổn định.** Không dùng tên hiển thị, email có thể đổi hoặc thuộc tính mô tả làm khóa nếu nghiệp vụ không cam kết chúng bất biến.
3. **Chuẩn hóa trước khi lưu.** Quy định chữ hoa/thường, khoảng trắng, Unicode, tiền tố và cách xử lý mã cũ. Neo4j so sánh giá trị property theo kiểu và giá trị được lưu; chuẩn hóa không nhất quán có thể tạo nhiều mã nhìn giống nhau.
4. **Tạo constraint đúng phạm vi.** Dùng label và property đúng với mô hình; nếu ID chỉ duy nhất theo tenant hoặc nguồn, dùng composite uniqueness constraint hoặc khóa đơn được tạo từ toàn bộ phạm vi.
5. **Kiểm tra null và dữ liệu cũ.** Uniqueness constraint không tự buộc property xuất hiện trên mọi node; kiểm tra và làm sạch dữ liệu trước khi triển khai.
6. **Dùng tham số và MERGE theo khóa.** Không ghép dữ liệu người dùng vào chuỗi Cypher và không đưa thuộc tính thay đổi vào mẫu identity.
7. **Xử lý xung đột có chủ đích.** Khi constraint từ chối một lần ghi trùng, chuyển lỗi thành kết quả nghiệp vụ phù hợp như conflict hoặc trả về bản ghi đã tồn tại.
8. **Không nhầm ID node với ID relationship.** Nếu một relationship có mã nghiệp vụ riêng, hãy mô hình hóa mã đó như property trên relationship và thiết kế constraint tương ứng theo khả năng của phiên bản Neo4j; `@RelationshipId` của SDN là metadata nội bộ, không mặc nhiên là mã nghiệp vụ.

## 9. Bài tập thực hành

1. Thiết kế entity `Person` có `personId` kiểu `String` được cấp từ hệ thống danh mục; ánh xạ bằng `@Id` và không dùng `@GeneratedValue`.
2. Tạo uniqueness constraint cho `Person.personId` và giải thích vì sao `@Id` trong Java không tự thay thế constraint ở Neo4j.
3. Viết truy vấn Cypher tìm các `personId` trùng và các node chưa có `personId` trước khi triển khai constraint.
4. Viết `MERGE` theo `personId`, sau đó cập nhật `name` và `born` mà không đưa hai thuộc tính này vào mẫu identity.
5. Thiết kế khóa cho trường hợp hai tenant cùng có `externalId = "A-100"`; so sánh composite constraint với một `personKey` đơn.
6. Giải thích vai trò của `@Version` khi ID đã được gán trước lúc lưu và nêu lựa chọn thay thế bằng `Persistable`.

Khi hoàn thành, bạn cần phân biệt được ID nghiệp vụ với internal ID, biết ánh xạ ID tự gán vào entity SDN, tạo constraint đúng phạm vi và viết truy vấn upsert an toàn. Đây là nền tảng để các repository và dịch vụ Spring Data Neo4j duy trì danh tính node nhất quán khi dữ liệu đến từ nhiều nguồn hoặc được cập nhật đồng thời.
