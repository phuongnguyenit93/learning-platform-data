# Phân biệt property đơn giản, map kết quả và đối tượng miền cần ánh xạ

Trong Spring Data Neo4j (SDN), dữ liệu Java có thể xuất hiện ở nhiều hình thức: thuộc tính đơn giản của node hoặc relationship, map được tạo ra trong kết quả Cypher, và đối tượng miền được ánh xạ thành node cùng các relationship. Các hình thức này có mục đích khác nhau. Một map trong kết quả truy vấn không tự động trở thành một property của node; một đối tượng Java cũng không thể được lưu nguyên khối như một property Neo4j.

Hiểu rõ sự khác biệt giúp chọn đúng kiểu entity, kiểu trả về của repository và cách viết Cypher. Bài học sử dụng ví dụ `Person` có tên, tuổi, nhãn sở thích và các mối quan hệ theo dõi.

## 1. Ba hình thức dữ liệu cần phân biệt

| Hình thức | Vai trò | Ví dụ |
| --- | --- | --- |
| Property đơn giản | Lưu một giá trị thuộc node hoặc relationship | `name`, `age`, `active`, `createdAt` |
| Map kết quả | Gom nhiều giá trị thành một cấu trúc tạm thời khi truy vấn | `RETURN {id: p.id, name: p.name} AS person` |
| Đối tượng miền | Mô hình hóa node, relationship và hành vi nghiệp vụ trong Java | `Person`, `Product`, `Order` |

Property đơn giản thuộc dữ liệu được lưu trong graph. Map kết quả thuộc hình dạng dữ liệu mà một câu truy vấn trả về. Đối tượng miền là mô hình Java mà SDN dùng để ánh xạ graph. Cùng một thông tin có thể xuất hiện trong cả ba hình thức, nhưng không nên coi chúng là tương đương.

## 2. Property đơn giản trong Neo4j và SDN

Neo4j lưu property dưới dạng cặp tên và giá trị trên node hoặc relationship. Các kiểu phổ biến gồm chuỗi, boolean, số, kiểu ngày giờ và một số kiểu không gian. Các collection property phải tuân theo giới hạn kiểu dữ liệu của Neo4j; chúng không phải danh sách object Java tùy ý.

Một entity đơn giản có thể khai báo như sau:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;

import java.time.LocalDate;
import java.util.List;

@Node("Person")
public class Person {
    @Id
    private String id;

    private String name;

    private Integer age;

    private Boolean active;

    private LocalDate birthDate;

    private List<String> interests;

    @Property("display_name")
    private String displayName;

    // Constructor, getter và setter được lược bỏ.
}
~~~

SDN ánh xạ các trường đơn giản thành property trên node `Person`. Trường `displayName` được lưu dưới tên property `display_name` nhờ `@Property`. Các trường còn lại dùng tên được suy ra theo quy ước mapping của SDN.

Ví dụ Cypher tương ứng với hình dạng dữ liệu có thể là:

~~~cypher
CREATE (p:Person {
  id: "person-100",
  name: "An",
  age: 28,
  active: true,
  birthDate: date("1998-03-12"),
  interests: ["graph", "java"],
  display_name: "An Nguyen"
})
~~~

Khi đọc node này thành `Person`, SDN chuyển các property sang kiểu Java tương ứng. Hãy chọn kiểu Java tương thích với kiểu property Neo4j và giữ quy ước tên property ổn định giữa các phiên bản ứng dụng.

### 2.1. Property đơn giản không phải object lồng nhau

Neo4j không lưu trực tiếp một object Java tùy ý hoặc một map lồng nhau thành một property đơn. Ví dụ, trường `Address` chứa `street`, `city`, `postalCode` không thể được coi như một property scalar chỉ bằng cách khai báo `private Address address;` rồi mong Neo4j tự lưu toàn bộ object.

Có ba cách thường dùng tùy ý nghĩa dữ liệu:

- Nếu các giá trị là những thuộc tính cố định của node, tách chúng thành các property đơn giản như `street`, `city`, `postalCode`.
- Nếu cần một nhóm thuộc tính động dạng map, cân nhắc `@CompositeProperty` để ánh xạ các mục trong map thành các property riêng trên node.
- Nếu đối tượng có định danh, vòng đời hoặc quan hệ riêng, mô hình hóa nó thành node và relationship.

Với kiểu Java đặc thù nhưng vẫn biểu diễn được thành một giá trị property, có thể đăng ký custom converter của SDN. Converter cần xác định rõ dạng lưu trữ và cách khôi phục kiểu Java khi đọc.

### 2.2. Giá trị null

Neo4j không lưu một property có giá trị `null`. Trong Cypher, gán `null` cho property sẽ xóa property đó khỏi node hoặc relationship. Vì vậy, cần phân biệt property không tồn tại với một giá trị chuỗi rỗng hoặc giá trị mặc định như `0` và `false`.

Khi lưu entity, hãy xác định rõ ý nghĩa của trường Java có giá trị `null`. Nếu trường được ghi thành `null` trong Neo4j, property tương ứng có thể bị loại bỏ. Nếu nghiệp vụ cần phân biệt “chưa biết”, “không áp dụng” và “giá trị rỗng”, hãy biểu diễn các trạng thái đó bằng quy ước dữ liệu rõ ràng thay vì dựa vào một property `null` không tồn tại.

## 3. Map thuộc tính với @CompositeProperty

Một số domain có nhóm thuộc tính thay đổi theo loại node, ví dụ metadata tùy chọn hoặc các đặc điểm mở rộng của hồ sơ. Nếu những giá trị này vẫn là property đơn giản được Neo4j hỗ trợ, SDN có thể ánh xạ `Map` thành tập property phẳng bằng `@CompositeProperty`.

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.CompositeProperty;

import java.util.HashMap;
import java.util.Map;

@Node("Product")
public class Product {
    @Id
    private String id;

    private String name;

    @CompositeProperty(prefix = "metadata_")
    private Map<String, String> metadata = new HashMap<>();
}
~~~

Map `metadata` ở đây là cách tổ chức dữ liệu trong Java. SDN ánh xạ các entry thành những property riêng trên node với tiền tố đã cấu hình, thay vì lưu một map lồng nhau như một giá trị property Neo4j. Các giá trị trong map vẫn phải là kiểu property mà Neo4j hỗ trợ.

Ví dụ map có các entry `color = "blue"` và `material = "steel"` sẽ được biểu diễn thành những property phẳng có tiền tố `metadata_` theo quy tắc composite property. Tên key trở thành một phần tên property, vì vậy hãy kiểm soát key hợp lệ, cách đặt tên và nguy cơ trùng key với property cố định của entity.

`@CompositeProperty` phù hợp với nhóm thuộc tính mở rộng có cấu trúc tương đối đơn giản. Nó không biến map thành một node riêng và không tự biểu diễn quan hệ giữa các phần tử. Nếu mỗi phần tử cần định danh, liên kết hoặc truy vấn độc lập, hãy mô hình hóa bằng node và relationship.

## 4. Map kết quả từ Cypher là gì?

Cypher có thể tạo map tạm thời trong phần `RETURN`. Map này mô tả hình dạng kết quả của truy vấn; nó không có nghĩa map đó đã được lưu vào node.

~~~cypher
MATCH (p:Person {id: $personId})
OPTIONAL MATCH (p)<-[:FOLLOWS]-(follower:Person)
RETURN {
  id: p.id,
  name: p.name,
  followerCount: count(DISTINCT follower)
} AS profile
~~~

Biểu thức `{ id: ..., name: ..., followerCount: ... }` tạo một map trong kết quả. Map có thể gom property từ nhiều node, kết quả tổng hợp hoặc giá trị tính toán. Đây là cách hữu ích để trả dữ liệu theo hình dạng mà API hoặc màn hình cần.

Một truy vấn cũng có thể trả về từng cột riêng:

~~~cypher
MATCH (p:Person {id: $personId})
RETURN p.id AS id, p.name AS name
~~~

Trong trường hợp này, mỗi dòng kết quả có các cột `id` và `name`. Khi dùng `Neo4jClient`, các cột được trả về dưới dạng map có key là tên cột hoặc bí danh:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;

import java.util.Map;
import java.util.Optional;

public class PersonReadService {
    private final Neo4jClient neo4jClient;

    public PersonReadService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<Map<String, Object>> findProfile(String personId) {
        return neo4jClient.query("""
                MATCH (p:Person {id: $personId})
                OPTIONAL MATCH (p)<-[:FOLLOWS]-(follower:Person)
                RETURN p.id AS id,
                       p.name AS name,
                       count(DISTINCT follower) AS followerCount
                """)
            .bind(personId).to("personId")
            .fetch()
            .one();
    }
}
~~~

`fetch().one()` trả về một kết quả tùy chọn; `fetch().all()` có thể dùng khi truy vấn trả về nhiều dòng. Kiểu giá trị trong map phụ thuộc vào biểu thức Cypher được trả về: có thể là chuỗi, số, boolean, danh sách, map lồng nhau hoặc kiểu dữ liệu graph mà Driver cung cấp.

Hãy dùng bí danh rõ ràng và ổn định. Khi đổi tên `followerCount` trong Cypher, các đoạn code đọc map theo key đó cũng cần được cập nhật. Với map động, nên kiểm tra kiểu và xử lý trường hợp key không có trong kết quả trước khi ép kiểu.

## 5. Phân biệt map kết quả với map được lưu thành property

Hai ví dụ sau có ý nghĩa khác nhau:

~~~cypher
// Tạo map chỉ trong kết quả truy vấn
MATCH (p:Person {id: $id})
RETURN {id: p.id, name: p.name} AS person
~~~

~~~cypher
// Ghi từng entry của map tham số thành property trên node
MATCH (p:Person {id: $id})
SET p += $properties
RETURN p
~~~

Trong truy vấn thứ nhất, map là một giá trị kết quả tạm thời. Trong truy vấn thứ hai, `SET p += $properties` áp dụng các cặp key-value của map vào property của node. Nó không tạo một property duy nhất tên `properties` chứa map lồng nhau.

Không dùng dạng `SET p.metadata = $properties` để lưu map tùy ý thành một property đơn; Neo4j property model không hỗ trợ map lồng nhau như một property value. Nếu muốn gom nhiều thuộc tính động trên node, hãy dùng composite property hoặc cập nhật từng property. Nếu muốn lưu cấu trúc lồng nhau có ý nghĩa miền, hãy cân nhắc các node và relationship riêng.

Khi dùng map làm tham số ghi, cần kiểm soát các key được phép cập nhật. Không nên cho phép dữ liệu đầu vào tùy ý ghi đè những property hệ thống như ID, version hoặc trường kiểm soát quyền truy cập.

## 6. Đối tượng miền cần ánh xạ thành node và relationship

Khi một khái niệm có định danh và quan hệ trong miền nghiệp vụ, hãy biểu diễn nó bằng entity SDN. Ví dụ `Person` có thể theo dõi nhiều người khác:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.HashSet;
import java.util.Set;

@Node("Person")
public class Person {
    @Id
    private String id;

    private String name;

    @Relationship(type = "FOLLOWS", direction = Relationship.Direction.OUTGOING)
    private Set<Person> follows = new HashSet<>();

    // Constructor, getter và setter được lược bỏ.
}
~~~

SDN dùng `@Node` để xác định nhãn node, `@Id` để xác định thuộc tính định danh của entity và `@Relationship` để mô tả quan hệ. Khi lưu entity, SDN ánh xạ mô hình Java thành cấu trúc graph tương ứng. Khi đọc node được trả về, SDN có thể tạo lại object domain theo mapping metadata.

Repository có thể trả về entity khi truy vấn trả về node tương ứng:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("MATCH (p:Person {id: $id}) RETURN p")
    Optional<Person> findPerson(@Param("id") String id);
}
~~~

Ở đây, `RETURN p` trả về node `Person` để SDN ánh xạ thành entity. Nếu truy vấn chỉ trả về `p.id AS id` và `p.name AS name`, đó là kết quả projection hoặc map theo cột; SDN không thể tự suy ra toàn bộ quan hệ của entity chỉ từ vài scalar này.

Nếu entity có các trường `@Relationship` và cần chúng được ánh xạ trong kết quả tùy chỉnh, truy vấn phải trả về dữ liệu graph cần thiết theo hình dạng mà SDN mapper có thể xử lý, chẳng hạn node, relationship hoặc path liên quan. Đừng giả định `RETURN p` sẽ tải mọi tầng quan hệ của graph; chỉ dữ liệu truy vấn trả về và mapping được cấu hình mới có thể được ánh xạ.

### 6.1. Relationship có thuộc tính riêng

Nếu relationship cũng có dữ liệu miền như thời điểm bắt đầu theo dõi hoặc nguồn tạo quan hệ, hãy mô hình hóa relationship properties:

Trong entity `Person`, trường quan hệ lúc này tham chiếu đến lớp chứa thuộc tính relationship:

~~~java
@Relationship(type = "FOLLOWS", direction = Relationship.Direction.OUTGOING)
private Set<FollowRelationship> follows = new HashSet<>();
~~~

~~~java
import java.time.LocalDate;

import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class FollowRelationship {
    @RelationshipId
    private Long id;

    private String source;

    private LocalDate followedAt;

    @TargetNode
    private Person person;
}
~~~

`@RelationshipProperties` đánh dấu lớp chứa thuộc tính của relationship; `@TargetNode` chỉ node ở đầu đích của quan hệ được ánh xạ. Kiểu định danh relationship và cách sinh ID cần tuân theo yêu cầu của phiên bản SDN đang dùng. Những thuộc tính như `source` và `followedAt` thuộc relationship, không phải property của node `Person`.

## 7. Khi nào chọn entity, projection hay map?

| Nhu cầu | Kiểu trả về nên cân nhắc | Lý do |
| --- | --- | --- |
| Đọc hoặc lưu một node theo mô hình miền | Entity `@Node` | SDN quản lý mapping và định danh |
| Cần quan hệ graph đã mô hình hóa | Entity có `@Relationship` hoặc relationship properties | Giữ được ngữ nghĩa graph trong domain |
| Màn hình chỉ cần một số trường cố định | Interface projection hoặc DTO | Hợp đồng dữ liệu rõ và dễ kiểm tra |
| Kết quả tổng hợp hoặc hình dạng động | `Map<String, Object>` từ `Neo4jClient` | Phù hợp với cột và map do Cypher tạo ra |
| Nhóm thuộc tính mở rộng trên một node | Map với `@CompositeProperty` | Các entry được ánh xạ thành property phẳng |
| Cấu trúc lồng nhau có định danh hoặc quan hệ riêng | Nhiều entity `@Node` và `@Relationship` | Mô hình hóa đúng cấu trúc graph |

Không nên chọn map chỉ vì nó linh hoạt nếu cấu trúc kết quả đã ổn định và được dùng ở nhiều nơi. Projection hoặc DTO giúp tên trường và kiểu dữ liệu được kiểm tra rõ hơn. Ngược lại, không cần tạo entity chỉ cho một kết quả thống kê tạm thời không có định danh hoặc vòng đời miền riêng.

## 8. Lỗi thường gặp khi ánh xạ property và kết quả

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không lưu được trường object phức tạp | Neo4j không hỗ trợ object tùy ý làm property value | Tách thành property, dùng converter, composite property hoặc mô hình hóa thành node |
| Truy vấn trả về map nhưng repository mong entity | Hình dạng kết quả không chứa node mà mapper cần | Trả node/path phù hợp hoặc dùng projection/map |
| Không đọc được key trong map | Bí danh Cypher khác key Java đang truy cập | Chuẩn hóa alias và kiểm tra key trước khi ép kiểu |
| Map động ghi đè dữ liệu không mong muốn | Dùng `SET n += $map` với key đầu vào không được kiểm soát | Whitelist key và loại bỏ trường hệ thống khỏi payload |
| Property không xuất hiện sau khi lưu | Giá trị `null` làm property bị xóa hoặc tên property mapping sai | Kiểm tra giá trị, `@Property` và dữ liệu trong Neo4j |
| Dữ liệu miền bị dẹt thành nhiều property dù cần quan hệ | Dùng map cho dữ liệu có định danh và liên kết riêng | Thiết kế node và relationship tương ứng |

## 9. Bài tập tự kiểm tra

1. Phân biệt property `name` của node với map được tạo bởi `RETURN {id: p.id, name: p.name}`.
2. Vì sao một object Java tùy ý không thể được lưu trực tiếp thành một property Neo4j?
3. `@CompositeProperty` giải quyết trường hợp nào và các entry trong map được biểu diễn ra sao?
4. Khi nào nên dùng `Neo4jClient` trả về `Map<String, Object>` thay vì repository trả về entity?
5. Vì sao `RETURN p` và `RETURN p.id AS id, p.name AS name` có hình dạng dữ liệu khác nhau đối với SDN?
6. Nếu một cấu trúc có định danh và relationship riêng, vì sao nên mô hình hóa nó thành node thay vì map?

Khi hoàn thành bài học, bạn cần nhận diện được dữ liệu nào là property lưu trữ, dữ liệu nào chỉ là map kết quả của Cypher và dữ liệu nào cần một entity miền được SDN ánh xạ. Việc chọn đúng hình thức giúp mô hình graph rõ ràng, truy vấn dễ kiểm soát và API chỉ nhận dữ liệu cần thiết.
