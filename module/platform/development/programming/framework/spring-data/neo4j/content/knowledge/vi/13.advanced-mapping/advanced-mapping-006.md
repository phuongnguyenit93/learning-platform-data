# Đánh giá phạm vi hỗ trợ interface theo phiên bản SDN

Trong Spring Data Neo4j (SDN), từ **interface** có thể chỉ nhiều vai trò khác nhau: interface repository, interface projection hoặc interface được dùng làm kiểu trong hệ phân cấp domain. Ba vai trò này có phạm vi hỗ trợ và giới hạn riêng. Một repository được khai báo bằng interface không có nghĩa SDN cho phép dùng chính interface đó làm kiểu entity đại diện cho node.

Khi đánh giá hỗ trợ interface, cần đối chiếu đúng phiên bản SDN đang chạy và xác định mục đích sử dụng. SDN 5.x dựa trên Neo4j-OGM với mô hình `@NodeEntity`; từ SDN 6.x, mapping được xây dựng trực tiếp trên Neo4j Java Driver với annotation `@Node`. Tài liệu SDN 6.0.x đã ghi nhận hỗ trợ interface trong một số domain-class hierarchy, nhưng interface không phải entity type hợp lệ cho repository vì không thể khai báo field định danh. Interface projection vẫn là một khả năng riêng và được hỗ trợ ở cả các dòng phiên bản này.

## 1. Ba nghĩa khác nhau của interface

| Vai trò | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Repository interface | `PersonRepository extends Neo4jRepository<Person, String>` | Khai báo API truy cập dữ liệu; Spring tạo implementation lúc chạy |
| Projection interface | `PersonSummary` có `getName()` và `getEmail()` | Mô tả một góc nhìn chỉ đọc gồm một phần thuộc tính của entity |
| Domain interface | `PaymentMethod` được `CardPayment` và `BankTransfer` triển khai | Cho phép một thuộc tính quan hệ hoặc tham chiếu dùng kiểu hợp đồng chung cho nhiều entity cụ thể |

Đây là các cơ chế độc lập. Repository interface là phần của Spring Data Repository abstraction. Projection interface là kiểu trả về của query method. Domain interface là một phần của mô hình đối tượng được SDN ánh xạ vào graph. Không nên dùng tài liệu về một vai trò để suy ra rằng các vai trò còn lại cũng được hỗ trợ theo cùng cách.

## 2. Phạm vi theo các dòng phiên bản

Bảng dưới đây tóm tắt những gì tài liệu chính thức của từng dòng phiên bản xác nhận. Đây là đánh giá theo tài liệu tham chiếu, không thay thế việc kiểm tra patch version và dependency thực tế của dự án.

| Dòng SDN | Công nghệ mapping và annotation | Interface trong domain hierarchy | Interface projection |
| --- | --- | --- | --- |
| 5.3.x | Neo4j-OGM; dùng `@NodeEntity`, `@RelationshipEntity` và API OGM | OGM có quy tắc kế thừa `@NodeEntity` qua supertype/interface. Đây là mô hình cũ, không đồng nhất với domain-interface mapping của SDN 6+ | Có projection interface. Tài liệu 5.3.x ghi closed projection chưa tối ưu việc giới hạn trường đọc; truy vấn nhạy hiệu năng có thể cần custom query hoặc `@QueryResult` |
| 6.0.x | Mapping native dựa trên Neo4j Java Driver; dùng `@Node`, `@Relationship` và `@RelationshipProperties` | Được hỗ trợ trong một số tình huống. Interface có thể là kiểu tham chiếu trong hierarchy, nhưng không phải domain type hợp lệ cho repository | Có proxy projection, closed/open projection, nested và dynamic projection; SDN dùng projection để giới hạn dữ liệu cần truyền |
| 6.1.x–7.x | Tiếp tục mô hình mapping native | Tài liệu tiếp tục mô tả interface hierarchy và giới hạn interface không có ID | Interface projection và DTO projection tiếp tục được hỗ trợ |
| 8.x | Mô hình mapping native hiện hành | Tài liệu 8.1/8.2 tiếp tục xác nhận hỗ trợ có giới hạn trong domain hierarchy; interface không phải repository entity type | Tiếp tục hỗ trợ proxy projection, multi-level projection và dynamic projection |

Điểm mốc có thể xác nhận từ tài liệu là: interface trong domain-class hierarchy đã được SDN 6.0.x mô tả rõ; tài liệu SDN 8.2.0 hiện hành vẫn giữ cách hỗ trợ có giới hạn này. Không nên diễn giải thành “mọi interface đều là entity” hoặc “có thể tạo repository cho interface”.

## 3. Repository interface: interface là API, entity vẫn là lớp có định danh

Repository của Spring Data được khai báo bằng interface. Generic type đầu tiên là domain type mà repository quản lý; generic type thứ hai là kiểu ID của domain type.

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

`PersonRepository` là interface để Spring tạo proxy implementation. `Person` mới là domain entity được ánh xạ thành node và có định danh. Ví dụ:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String name;

    private boolean active;
}
```

Một interface nghiệp vụ như `PersonView` hoặc `PaymentMethod` không thể thay thế `Person` trong khai báo `Neo4jRepository<PaymentMethod, ...>`. SDN ghi rõ interface không thể định nghĩa field identifier; vì vậy interface không phải entity type hợp lệ cho repository. Hãy dùng lớp cụ thể có `@Node` và `@Id`, hoặc một abstract base class được mapping phù hợp.

Các interface dùng để mở rộng repository cũng là một trường hợp riêng. Chẳng hạn, custom repository fragment có thể khai báo API bằng interface và được triển khai bằng một Spring bean:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonSearch {
    List<Person> findPeopleBySkill(String skill);
}

public interface PersonRepository
        extends Neo4jRepository<Person, String>, PersonSearch {
}
```

Trong trường hợp này `PersonSearch` là một phần API repository, không phải domain entity. Phần triển khai custom fragment cung cấp logic thực thi. Nếu tạo interface cơ sở chỉ để tái sử dụng và không muốn Spring tạo repository instance trực tiếp, dùng `@NoRepositoryBean` theo quy tắc của Spring Data.

## 4. Interface projection: lấy một phần dữ liệu của entity

Interface projection phù hợp khi API chỉ cần một số thuộc tính của aggregate. SDN tạo proxy runtime cho interface và chuyển lời gọi getter sang property của domain object tương ứng.

```java
import java.util.Optional;

public interface PersonSummary {

    String getName();

    Optional<String> getEmail();
}
```

Repository có thể trả projection này:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    List<PersonSummary> findByActiveTrue();
}
```

Tên getter phải khớp property của domain type: `getName()` ánh xạ tới `name`, `getEmail()` ánh xạ tới `email`. Projection không cần khai báo tất cả field của entity. Nó cũng không cần kế thừa entity hoặc triển khai interface của domain type.

Projection interface là proxy đọc dữ liệu từ đối tượng đích. Nó không phải một entity độc lập có ID và vòng đời persistence riêng. Nếu cần sửa dữ liệu, hãy cập nhật entity thực hoặc dùng cơ chế lưu projection có chủ đích của `Neo4jTemplate`; không coi setter trên một projection interface là cách cập nhật entity tự động.

### Closed và open projection

Closed projection chỉ khai báo accessor tương ứng với property đã biết của domain type:

```java
public interface PersonName {
    String getName();
}
```

Vì SDN biết trước tập thuộc tính cần thiết, closed projection có thể giúp giới hạn property và relationship được lấy từ database. Đây là điểm khác biệt hiệu năng cần lưu ý khi so sánh tài liệu SDN 5.3 với các dòng 6.x trở đi: tài liệu 5.3 ghi rõ cơ chế tối ưu trường của closed projection chưa được triển khai ở thời điểm đó.

Open projection có thể tính giá trị mới bằng `@Value` và SpEL:

```java
import org.springframework.beans.factory.annotation.Value;

public interface PersonLabel {

    String getName();

    @Value("#{target.name + ' (' + target.email + ')'}")
    String getDisplayLabel();
}
```

Vì SpEL có thể truy cập các thuộc tính khác của target, SDN không thể suy ra chính xác trước những trường nào cần đọc để tính kết quả. Do đó, open projection không có cùng lợi ích tối ưu truy vấn như closed projection. Với logic tính toán phức tạp, nên chuyển phần xử lý sang service hoặc bean chuyên trách thay vì đặt biểu thức dài trong annotation.

### Nested và dynamic projection

Projection có thể lồng nhau để giới hạn dữ liệu ở nhiều cấp:

```java
public interface PersonProfile {

    String getName();

    AddressSummary getAddress();

    interface AddressSummary {
        String getCity();
        String getCountry();
    }
}
```

Dynamic projection cho phép chọn kiểu kết quả tại thời điểm gọi:

```java
import java.util.Collection;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    <T> Collection<T> findByNameContaining(String fragment, Class<T> projectionType);
}
```

```java
Collection<Person> fullEntities =
    repository.findByNameContaining("An", Person.class);

Collection<PersonSummary> summaries =
    repository.findByNameContaining("An", PersonSummary.class);
```

Cùng một query method có thể trả entity đầy đủ hoặc projection được chọn. Hãy kiểm tra quy tắc dynamic projection và kiểu tham số `Class<T>` của phiên bản Spring Data đang dùng nếu chính method đó cần truyền một giá trị `Class` như tham số truy vấn thông thường.

## 5. Interface trong domain-class hierarchy

Từ SDN 6.0.x, interface có thể tham gia domain-class hierarchy trong một số tình huống. Mục đích là cho phép một property hoặc relationship tham chiếu đến một hợp đồng chung, trong khi object thực tế được dựng thành một trong các lớp cụ thể.

Điểm quan trọng: interface không tự trở thành entity độc lập. Lớp triển khai cụ thể vẫn phải là kiểu được SDN ánh xạ và mang định danh.

### Một implementation

Khi chỉ có một implementation, có thể dùng interface làm kiểu tham chiếu và đặt `@Node` trên lớp triển khai với primary label phù hợp:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

public interface PaymentMethod {
    String getDisplayName();
}

@Node("PaymentMethod")
public class CardPayment implements PaymentMethod {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;

    @Override
    public String getDisplayName() {
        return displayName;
    }
}
```

Một entity khác có thể tham chiếu tới interface:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("PurchaseOrder")
public class PurchaseOrder {

    @Id
    private String orderNumber;

    @Relationship(type = "PAID_WITH")
    private PaymentMethod paymentMethod;
}
```

Khi SDN đọc relationship `PAID_WITH`, nó có thể dựng implementation cụ thể tương ứng với label và mapping metadata. Trong mẫu một implementation, tài liệu SDN minh họa việc đồng bộ primary label của implementation với tên interface; nếu cần tách tên Java khỏi label graph, có thể khai báo label tường minh theo cơ chế `@Node` được tài liệu phiên bản đó hỗ trợ.

### Nhiều implementation và polymorphism

Nếu cùng một interface có nhiều lớp triển khai, SDN cần đủ label để nhận diện cả nhóm interface lẫn loại cụ thể. Tài liệu SDN yêu cầu tối thiểu hai label: một label xác định interface và một label xác định implementation.

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("PaymentMethod")
public interface PaymentMethod {
    String getDisplayName();
}

@Node("CardPayment")
public class CardPayment implements PaymentMethod {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;

    @Override
    public String getDisplayName() {
        return displayName;
    }
}

@Node("BankTransfer")
public class BankTransfer implements PaymentMethod {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;

    @Override
    public String getDisplayName() {
        return displayName;
    }
}
```

Node cụ thể cần mang label interface và label implementation, ví dụ:

```cypher
(:PaymentMethod:CardPayment {displayName: "Visa ending 1234"})
(:PaymentMethod:BankTransfer {displayName: "Bank account"})
```

Entity cha có thể khai báo field kiểu `PaymentMethod` mà không phải biết implementation cụ thể. Khi đọc, SDN dựa trên label để xác định `CardPayment` hay `BankTransfer`.

Không được chỉ đặt một label chung `PaymentMethod` cho mọi implementation rồi mong SDN tự đoán lớp cụ thể từ các property. Cần label riêng cho từng implementation theo mô hình polymorphic được tài liệu mô tả. Nếu hai implementation không có khác biệt label, SDN thiếu thông tin để chọn kiểu đích.

### Abstract base class là lựa chọn khác

Nếu các implementation chia sẻ ID và state chung, abstract class có thể phù hợp hơn interface:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("PaymentMethod")
public abstract class PaymentMethodBase {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;
}

@Node("CardPayment")
public class CardPayment extends PaymentMethodBase {
    private String lastFourDigits;
}
```

SDN hỗ trợ polymorphic mapping qua abstract base class được đánh dấu `@Node`. Label của base class được dùng như label bổ sung cùng label của implementation cụ thể. `@Node` không tự được kế thừa từ superclass hoặc interface, vì vậy hãy khai báo annotation trên các cấp domain class theo đúng mô hình và phiên bản.

## 6. Các giới hạn cần ghi nhớ

| Tình huống | Phạm vi hỗ trợ và lưu ý |
| --- | --- |
| Repository có kiểu `Neo4jRepository<SomeInterface, ID>` | Không được hỗ trợ như entity repository domain type; interface không định nghĩa ID field |
| Repository interface quản lý entity class | Được hỗ trợ và là cách khai báo repository tiêu chuẩn |
| Interface projection trả một phần field | Được hỗ trợ; getter phải khớp property của domain type |
| Interface projection có SpEL `@Value` | Được hỗ trợ như open projection, nhưng không có cùng khả năng tối ưu tập field |
| Interface dùng làm kiểu relationship/thuộc tính trong domain hierarchy | Được hỗ trợ trong các kịch bản được tài liệu SDN 6+ mô tả; implementation cụ thể phải có mapping và label phù hợp |
| Interface tự khai báo ID và được lưu như entity độc lập | Không được hỗ trợ; dùng lớp cụ thể hoặc abstract base class |
| Nhiều implementation nhưng chỉ có một label chung | Không đủ thông tin để phân biệt kiểu cụ thể; cần label interface và label implementation |

Một số giới hạn khác cũng phụ thuộc loại projection. Interface projection là proxy dựa trên entity đích; DTO projection dùng constructor hoặc property mapping; projection interface không tự cung cấp lifecycle như entity. Với custom query, result shape phải khớp kiểu projection/DTO. Nếu query trả scalar, không nên mong SDN tự dựng một entity graph đầy đủ từ dữ liệu thiếu.

## 7. Cách xác định đúng hỗ trợ trong dự án

Không thể kết luận phiên bản chỉ từ tên Spring Boot hoặc từ một bài viết cũ. Hãy kiểm tra dependency `org.springframework.data:spring-data-neo4j` thực tế được resolve trong build. Nếu dùng Spring Boot dependency management, version SDN có thể được quản lý gián tiếp qua BOM. Sau đó mở tài liệu tham chiếu đúng dòng phiên bản, kiểm tra mục *Metadata-based Mapping*, *Class hierarchies* và *Projections*.

Khi nâng cấp qua ranh giới SDN 5.x sang 6.x, cần xem đây là thay đổi mô hình mapping lớn: SDN 5.x dựa trên Neo4j-OGM và dùng `@NodeEntity`; SDN 6.x dùng mapping native với `@Node` và Neo4j Java Driver. Interface hierarchy của OGM và interface hierarchy trong native mapping không nên được coi là cùng một contract. Hãy kiểm tra lại annotation, label, ID, repository domain type, query và dữ liệu graph sau migration.

Quy trình đánh giá thực tế:

1. Xác định chính xác phiên bản SDN và Neo4j Java Driver đang được resolve.
2. Xác định interface cần dùng là repository API, projection hay domain hierarchy.
3. Nếu là repository, bảo đảm generic domain type là một entity có ID.
4. Nếu là projection, kiểm tra getter, nested property, closed/open projection và result shape.
5. Nếu là domain hierarchy, xác định concrete implementation, `@Node` và label phân biệt từng kiểu.
6. Viết kiểm thử mapping cho từng implementation và relationship tham chiếu interface.
7. Khi nâng cấp, đối chiếu lại tài liệu của đúng version và kiểm tra behavior bằng integration test với Neo4j phù hợp.

## Kết luận

SDN hỗ trợ interface theo nhiều cách, nhưng không đồng nghĩa interface nào cũng là entity. Repository interface là API truy cập dữ liệu; interface projection là proxy cung cấp góc nhìn một phần; domain interface trong SDN 6.x trở đi có thể dùng trong một số hierarchy để hỗ trợ polymorphism, nhưng interface không thể làm repository domain type vì không có ID field. SDN 5.x dùng mô hình Neo4j-OGM và có quy tắc kế thừa/projection riêng. Hãy xác định đúng phiên bản và vai trò của interface trước khi chọn thiết kế, sau đó kiểm tra bằng mapping test thay vì suy luận từ tên annotation.

## Tài liệu tham khảo

- [Spring Data Neo4j 5.3.x Reference — Projections và Neo4j-OGM](https://docs.spring.io/spring-data/neo4j/docs/5.3.x/reference/html/)
- [Spring Data Neo4j 6.0.x Reference — Interface trong domain hierarchy và Projections](https://docs.spring.io/spring-data/neo4j/docs/6.0.x/reference/html/)
- [Spring Data Neo4j 6.1.3 Reference](https://www.springframework.org/spring-data/neo4j/docs/6.1.3/reference/html/)
- [Spring Data Neo4j 7.0.0 Reference](https://docs.spring.io/spring-data/neo4j/docs/7.0.0/reference/html/)
- [Spring Data Neo4j 8.2.0 — Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
- [Spring Data Neo4j 8.2.0 — Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
