# Định nghĩa thuộc tính bằng `@Property`

Trong Spring Data Neo4j (SDN), một thuộc tính của node được ánh xạ từ field hoặc property Java sang một property key của node trong Neo4j. Theo mặc định, SDN dùng tên thuộc tính Java làm tên property key. Khi tên trong mô hình Java cần khác tên lưu trong đồ thị, bạn có thể khai báo `@Property` để chỉ định tên cần ánh xạ.

Ví dụ, ứng dụng có thể dùng tên `fullName` trong Java nhưng lưu dữ liệu dưới key `full_name` trong Neo4j. Annotation `@Property("full_name")` mô tả ánh xạ này. Việc đổi tên key không làm đổi tên field Java, label của node hay cấu trúc relationship.

## 1. `@Property` giải quyết vấn đề gì?

Một mô hình Java thường ưu tiên cách đặt tên theo quy ước của ngôn ngữ, trong khi đồ thị Neo4j có thể đã sử dụng quy ước tên khác. Một số tình huống thường gặp:

- Java dùng camelCase, còn property key trong đồ thị dùng snake_case.
- Ứng dụng cần giữ tương thích với dữ liệu đã được tạo bởi một hệ thống khác.
- Tên thuộc tính trong mô hình miền rõ nghĩa hơn tên key cũ trong cơ sở dữ liệu.
- Nhiều thành phần ứng dụng cần dùng chung một quy ước key ổn định, dù tên field Java có thể được tái cấu trúc.

`@Property` cho phép tách tên thuộc tính trong mã nguồn khỏi tên key được lưu trong node. Nhờ vậy, bạn có thể đổi tên field Java mà vẫn giữ nguyên key trong đồ thị, miễn là cập nhật đúng phần tham chiếu trong mã nguồn và các truy vấn liên quan.

## 2. Cú pháp và cách ánh xạ

Annotation thuộc package `org.springframework.data.neo4j.core.schema`:

```java
import org.springframework.data.neo4j.core.schema.Property;

@Property("full_name")
private String fullName;
```

Trong ví dụ này:

- `fullName` là tên thuộc tính trong Java.
- `full_name` là property key được SDN sử dụng khi đọc hoặc ghi node.
- Kiểu dữ liệu vẫn là `String`; `@Property` không thay đổi kiểu dữ liệu.

Nếu không khai báo `@Property`, SDN mặc định ánh xạ thuộc tính theo tên Java. Chẳng hạn, field `active` thường được lưu dưới key `active`. Khi muốn chỉ rõ tên key, hãy dùng `@Property("key_name")` ngay trên thuộc tính cần ánh xạ.

## 3. Ví dụ entity có nhiều property key

Giả sử đồ thị lưu node `Person` với các key `full_name`, `email_address` và `active`. Entity có thể khai báo như sau:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;

@Node("Person")
public class Person {

    @Id
    private String id;

    @Property("full_name")
    private String fullName;

    @Property("email_address")
    private String email;

    private boolean active;

    protected Person() {
    }

    public Person(String id, String fullName, String email, boolean active) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
        this.active = active;
    }

    public String getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }
}
```

`@Node("Person")` xác định label của node. `@Property("full_name")` và `@Property("email_address")` chỉ định hai key tùy chỉnh. Thuộc tính `active` không có annotation nên sử dụng tên mặc định.

Một node tương ứng trong Neo4j có thể có hình dạng như sau:

```cypher
CREATE (:Person {
    id: 'person-1001',
    full_name: 'Nguyen An',
    email_address: 'an@example.com',
    active: true
});
```

`@Property` chỉ mô tả cách ánh xạ thuộc tính. Nó không tự tạo node, không khai báo label và cũng không tạo relationship. Các trách nhiệm đó thuộc về những phần khác của mô hình SDN và thao tác lưu dữ liệu.

## 4. Dùng property đã ánh xạ trong repository

Với derived query, tên thuộc tính trong tên phương thức repository là tên thuộc tính Java. SDN dựa vào metadata ánh xạ để tạo truy vấn tới key tương ứng trong Neo4j.

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    Optional<Person> findByFullName(String fullName);

    Optional<Person> findByEmail(String email);

    @Query("""
        MATCH (p:Person)
        WHERE p.full_name = $name
        RETURN p
        """)
    List<Person> findPeopleByStoredName(@Param("name") String name);
}
```

`findByFullName` tham chiếu thuộc tính Java `fullName`; khi thực thi, SDN sử dụng key `full_name` theo khai báo `@Property`. Tương tự, `findByEmail` sử dụng key `email_address`. Bạn không cần đổi tên phương thức thành `findByFull_name`.

Với truy vấn Cypher viết thủ công bằng `@Query`, như phương thức `findPeopleByStoredName` trong ví dụ trên, bạn phải dùng tên key thực tế trong Neo4j. `p.full_name` là property key của node. Viết `p.fullName` sẽ tìm một key khác và không khớp với dữ liệu được lưu theo ví dụ trên. Hãy phân biệt rõ tên thuộc tính Java và tên key trong câu truy vấn thủ công.

## 5. Kiểm tra dữ liệu trực tiếp bằng Cypher

Bạn có thể xác nhận cách ánh xạ bằng cách đọc node trong Neo4j Browser hoặc công cụ chạy Cypher:

```cypher
MATCH (p:Person {id: 'person-1001'})
RETURN p.full_name, p.email_address, p.active;
```

Kết quả mong đợi gồm ba giá trị tương ứng với `fullName`, `email` và `active` trong entity. Để kiểm tra toàn bộ property key đang có trên node, dùng:

```cypher
MATCH (p:Person {id: 'person-1001'})
RETURN properties(p) AS personProperties;
```

Hãy dùng truy vấn kiểm tra này khi tích hợp với dữ liệu cũ hoặc khi đổi tên field. Nó giúp phát hiện trường hợp ứng dụng vô tình ghi thêm một key mới trong khi key cũ vẫn tồn tại.

## 6. `@Property` không tạo index hoặc constraint

`@Property` chỉ định tên key dùng trong mapping. Annotation này không tự tạo index, uniqueness constraint hay quy tắc xác thực dữ liệu ở Neo4j.

Nếu ứng dụng thường tìm người theo email và cần bảo đảm email là duy nhất, hãy quản lý constraint bằng Cypher hoặc công cụ migration schema phù hợp. Ví dụ:

```cypher
CREATE CONSTRAINT person_email_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.email_address IS UNIQUE;
```

Key trong constraint phải là `email_address`, vì đó là tên được lưu trong đồ thị. Tên field Java `email` không xuất hiện trong cú pháp schema của Neo4j.

Tương tự, khi tối ưu truy vấn theo `full_name`, index cũng phải được tạo trên key thực tế:

```cypher
CREATE INDEX person_full_name IF NOT EXISTS
FOR (p:Person)
ON (p.full_name);
```

Hãy cân nhắc truy vấn thường dùng, kích thước dữ liệu và kế hoạch thực thi trước khi tạo index. Không nên tạo index cho mọi property vì mỗi index đều có chi phí lưu trữ và cập nhật.

## 7. Kiểu dữ liệu và giá trị property

Neo4j lưu property dưới dạng các kiểu giá trị được cơ sở dữ liệu hỗ trợ, chẳng hạn chuỗi, số, boolean, giá trị ngày giờ và danh sách các giá trị phù hợp. `@Property` không biến một object Java bất kỳ thành một node con hay một relationship.

Khi thuộc tính Java có kiểu mà Neo4j không hỗ trợ trực tiếp, hãy cấu hình cơ chế chuyển đổi của Spring Data phù hợp để chuyển kiểu miền nghiệp vụ sang kiểu property mà driver và Neo4j hỗ trợ. Việc đổi tên key bằng `@Property` và việc chuyển đổi kiểu dữ liệu là hai trách nhiệm riêng.

Nếu dữ liệu biểu diễn một thực thể độc lập hoặc một quan hệ giữa các node, hãy mô hình hóa nó bằng `@Node` và `@Relationship`. Không nên gom dữ liệu có cấu trúc đồ thị vào một field rồi kỳ vọng `@Property` tự tạo ra cấu trúc tương ứng.

Neo4j không lưu một property có giá trị `null` như một giá trị thông thường. Trong Cypher, phép gán `null` cho một key sẽ loại bỏ key đó khỏi node. Vì vậy, khi cập nhật entity có thuộc tính null, hãy hiểu rõ hành vi ghi của ứng dụng để tránh nhầm lẫn giữa key không tồn tại và key có giá trị rỗng.

## 8. Những lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Repository derived query không tìm thấy dữ liệu | Dùng tên thuộc tính Java không khớp với property trong mô hình hoặc khai báo mapping sai | Kiểm tra field Java và `@Property`, sau đó kiểm tra dữ liệu trong node |
| Cypher thủ công trả về rỗng | Truy vấn dùng `p.fullName` trong khi key thực tế là `full_name` | Dùng đúng key Neo4j trong câu Cypher |
| Dữ liệu xuất hiện thành hai key khác nhau | Một phần ứng dụng ghi `fullName`, phần khác ghi `full_name` | Chuẩn hóa mapping và di chuyển dữ liệu cũ nếu cần |
| Tưởng annotation đã tạo index | Nhầm metadata mapping với schema của Neo4j | Tạo index hoặc constraint bằng migration/schema management |
| Gán object Java phức tạp vào `@Property` | Cho rằng annotation tự ánh xạ object thành node hoặc relationship | Dùng custom conversion cho kiểu giá trị phù hợp hoặc mô hình hóa node/relationship riêng |

Khi đổi tên key trong một hệ thống đã có dữ liệu, cần lập kế hoạch di chuyển dữ liệu. Chỉ thay annotation có thể khiến ứng dụng đọc key mới trong khi các node hiện tại vẫn chỉ có key cũ. Một đợt chuyển đổi an toàn cần xác định key cũ, key mới, cách chuyển giá trị, thời điểm cập nhật truy vấn và khả năng tương thích trong giai đoạn triển khai.

## 9. Quy trình áp dụng `@Property`

Khi thêm hoặc thay đổi mapping một thuộc tính, hãy thực hiện theo trình tự:

1. Xác định label node và property key đang được lưu trong Neo4j.
2. Chọn tên field Java phù hợp với mô hình miền nghiệp vụ.
3. Thêm `@Property("key_name")` nếu tên field Java khác key trong đồ thị.
4. Kiểm tra derived query bằng tên thuộc tính Java và kiểm tra Cypher thủ công bằng key Neo4j.
5. Kiểm tra index, constraint và các ứng dụng khác đang đọc hoặc ghi key đó.
6. Thử lưu entity rồi đọc lại; đồng thời kiểm tra `properties(node)` để xác nhận key thực tế.

## 10. Tự kiểm tra

1. Với field Java `fullName` được khai báo `@Property("full_name")`, key nào được dùng trong node Neo4j?
2. Khi viết `findByFullName`, bạn dùng tên field Java hay tên property key trong cơ sở dữ liệu?
3. Khi viết Cypher thủ công, vì sao điều kiện `p.fullName = $name` có thể không tìm thấy node?
4. `@Property` có tự tạo index hoặc uniqueness constraint hay không? Bạn quản lý các thành phần đó ở đâu?
5. Nếu đổi key từ `full_name` sang `display_name`, những dữ liệu và truy vấn nào cần được rà soát?

Khi nắm được sự khác nhau giữa tên thuộc tính Java và property key của Neo4j, bạn có thể dùng `@Property` để giữ mô hình mã nguồn rõ ràng mà vẫn tương thích với cấu trúc dữ liệu đồ thị.
