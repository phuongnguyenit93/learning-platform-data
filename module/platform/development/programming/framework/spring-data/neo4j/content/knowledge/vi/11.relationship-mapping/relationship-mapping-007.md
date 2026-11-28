# Thêm, bỏ hoặc thay thế liên kết trong collection

Trong mô hình đồ thị, một node thường có nhiều relationship cùng kiểu. Ví dụ, một người có thể theo dõi nhiều người khác, một nhóm có nhiều thành viên hoặc một đơn hàng chứa nhiều sản phẩm. Trong Spring Data Neo4j, các liên kết này thường được ánh xạ vào một collection trên entity như `List`, `Set` hoặc collection các lớp relationship properties.

Khi nghiệp vụ thay đổi, ứng dụng cần thêm liên kết mới, bỏ một liên kết hoặc thay toàn bộ tập liên kết. Để thao tác đúng, cần hiểu collection Java biểu diễn trạng thái quan hệ như thế nào, cách `save` đồng bộ trạng thái đó xuống Neo4j và những rủi ro khi lưu entity chỉ được tải một phần.

## 1. Ánh xạ nhiều liên kết vào collection

Giả sử ứng dụng mạng xã hội có quan hệ theo dõi giữa người dùng. Một người có thể theo dõi nhiều người khác, được biểu diễn bằng relationship có hướng `FOLLOWS`:

```text
(Person)-[:FOLLOWS]->(Person)
```

Trong entity, khai báo collection bằng `@Relationship`:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String personKey;
    private String name;

    @Relationship(type = "FOLLOWS", direction = Relationship.Direction.OUTGOING)
    private List<Person> following = new ArrayList<>();

    public Long getId() {
        return id;
    }

    public String getPersonKey() {
        return personKey;
    }

    public String getName() {
        return name;
    }

    public List<Person> getFollowing() {
        return following;
    }
}
```

Trường `following` ánh xạ các relationship đi ra từ node `Person` hiện tại. Mỗi phần tử trong collection là node đích của một relationship `FOLLOWS`. Ví dụ, nếu An theo dõi Bình và Chi, đồ thị có hai cạnh:

```text
(An)-[:FOLLOWS]->(Bình)
(An)-[:FOLLOWS]->(Chi)
```

`direction = OUTGOING` mô tả hướng từ entity hiện tại đến các phần tử trong collection. Nếu muốn ánh xạ các relationship đi vào node hiện tại, dùng `Relationship.Direction.INCOMING`. Hướng này là hướng của relationship trong đồ thị, không phải thứ tự thêm phần tử vào collection.

## 2. Thêm một liên kết

Giả sử cần cho An theo dõi một người mới. Service đọc hai entity, thêm node đích vào collection và lưu entity nguồn:

```java
public interface PersonRepository extends Neo4jRepository<Person, Long> {
    Optional<Person> findByPersonKey(String personKey);
}
```

```java
@Service
public class FollowService {

    private final PersonRepository personRepository;

    public FollowService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional
    public void follow(String sourceKey, String targetKey) {
        Person source = personRepository.findByPersonKey(sourceKey)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy người theo dõi"));

        Person target = personRepository.findByPersonKey(targetKey)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy người được theo dõi"));

        boolean alreadyFollowing = source.getFollowing().stream()
            .anyMatch(person -> targetKey.equals(person.getPersonKey()));

        if (!alreadyFollowing) {
            source.getFollowing().add(target);
            personRepository.save(source);
        }
    }
}
```

Khi lưu `source`, Spring Data Neo4j ánh xạ collection `following` thành các relationship `FOLLOWS`. Việc kiểm tra trước khi thêm giúp service thể hiện rõ quy tắc không tạo liên kết trùng theo khóa nghiệp vụ. `@Transactional` gom thao tác đọc và ghi trong một đơn vị công việc.

Ví dụ Cypher tương đương về mặt ý nghĩa:

```cypher
MATCH (source:Person {personKey: $sourceKey})
MATCH (target:Person {personKey: $targetKey})
MERGE (source)-[:FOLLOWS]->(target)
```

`MERGE` phù hợp khi muốn tạo liên kết nếu chưa có. Nếu dùng collection và `save`, hãy bảo đảm logic Java không thêm phần tử trùng và trạng thái collection phản ánh đúng những liên kết cần duy trì.

## 3. Bỏ một liên kết

Để An ngừng theo dõi Bình, bỏ Bình khỏi collection rồi lưu lại An:

```java
@Transactional
public void unfollow(String sourceKey, String targetKey) {
    Person source = personRepository.findByPersonKey(sourceKey)
        .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy người theo dõi"));

    boolean removed = source.getFollowing().removeIf(
        person -> targetKey.equals(person.getPersonKey())
    );

    if (removed) {
        personRepository.save(source);
    }
}
```

Sau khi lưu, liên kết tương ứng trong collection được đồng bộ theo trạng thái entity. Thao tác này chỉ bỏ relationship `FOLLOWS` giữa hai node. Node `Person` đại diện cho Bình vẫn tồn tại và các relationship khác của Bình vẫn được giữ.

Có thể hình dung thao tác ở mức Cypher:

```cypher
MATCH (source:Person {personKey: $sourceKey})
      -[r:FOLLOWS]->
      (target:Person {personKey: $targetKey})
DELETE r
```

`DELETE r` xóa relationship đã tìm thấy. Không dùng `DETACH DELETE target` khi chỉ muốn bỏ một liên kết, vì lệnh đó xóa node đích cùng toàn bộ relationship gắn với node đó.

## 4. Thay thế toàn bộ collection

Một số nghiệp vụ cần thay toàn bộ tập liên kết, ví dụ quản trị viên cập nhật danh sách thành viên của nhóm hoặc người dùng chọn lại toàn bộ danh sách quan tâm. Khi đó, collection mới cần đại diện cho trạng thái cuối cùng mong muốn.

Ví dụ thêm phương thức thay thế danh sách theo khóa nghiệp vụ:

```java
public void replaceFollowing(List<Person> newFollowing) {
    following.clear();

    if (newFollowing != null) {
        for (Person candidate : newFollowing) {
            boolean exists = following.stream()
                .anyMatch(person -> person.getPersonKey().equals(candidate.getPersonKey()));

            if (!exists) {
                following.add(candidate);
            }
        }
    }
}
```

Service gọi phương thức rồi lưu entity:

```java
@Transactional
public void replaceFollowing(String sourceKey, List<String> targetKeys) {
    Person source = personRepository.findByPersonKey(sourceKey)
        .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy người dùng"));

    List<Person> targets = personRepository.findAllByPersonKeyIn(targetKeys);

    if (targets.size() != targetKeys.stream().distinct().count()) {
        throw new IllegalArgumentException("Danh sách chứa người dùng không tồn tại");
    }

    source.replaceFollowing(targets);
    personRepository.save(source);
}
```

Trong ví dụ cần khai báo thêm phương thức truy vấn phù hợp trên repository:

```java
List<Person> findAllByPersonKeyIn(Collection<String> personKeys);
```

Khi thay thế, các liên kết cũ không còn trong collection đích sẽ bị loại khỏi trạng thái quan hệ được lưu; các liên kết mới sẽ được tạo. Node người dùng không bị xóa chỉ vì nó không còn nằm trong collection.

Không nên gọi phương thức thay thế nếu ý định chỉ là thêm một phần tử. Hãy phân biệt rõ ba lệnh nghiệp vụ: thêm một liên kết, bỏ một liên kết và thay toàn bộ danh sách. API rõ ràng giúp tránh vô tình xóa nhiều relationship.

## 5. Lưu ý về collection và trạng thái entity

Collection trong Java là biểu diễn trạng thái mà ứng dụng đưa cho Spring Data Neo4j khi lưu entity. Vì vậy, cần quản lý collection có chủ đích.

### Tránh lưu entity chỉ được tải một phần

Khi thao tác với một collection relationship, cần biết collection hiện tại đã được nạp đầy đủ hay chỉ là một phần kết quả. Nếu entity được dựng thủ công, lấy từ projection, hoặc được nạp bằng truy vấn tùy chỉnh chỉ trả về một phần quan hệ, việc lưu entity đó có thể khiến trạng thái relationship trong database không còn như mong muốn.

Ví dụ rủi ro: An đang theo dõi 100 người, nhưng truy vấn tùy chỉnh chỉ nạp 5 người đầu tiên vào `following`. Nếu dùng entity một phần đó làm trạng thái đầy đủ rồi lưu, 95 liên kết còn lại có thể bị loại khỏi tập quan hệ được đồng bộ.

Để cập nhật an toàn:

- Đọc entity cùng collection relationship cần thay đổi bằng cách tải phù hợp.
- Chỉ dùng collection một phần cho mục đích đọc nếu không có ý định lưu lại entity đó.
- Dùng projection/DTO cho truy vấn trả dữ liệu rút gọn, thay vì chuyển DTO thành entity rồi gọi `save`.
- Nếu chỉ cần thêm hoặc xóa một cạnh trong đồ thị lớn, cân nhắc câu lệnh Cypher chuyên biệt để thao tác đúng relationship đó.

### Chọn List hay Set

| Collection | Đặc điểm | Điều cần chú ý |
|---|---|---|
| `List<T>` | Giữ thứ tự trong bộ nhớ và cho phép phần tử trùng | Cần tự kiểm tra trùng; thứ tự của list Java không tự trở thành thứ tự relationship trong Neo4j. |
| `Set<T>` | Biểu diễn tập phần tử duy nhất theo `equals`/`hashCode` | Cần triển khai equality ổn định; entity mới chưa có ID có thể gây vấn đề nếu dựa vào ID sinh tự động. |

Neo4j không bảo đảm thứ tự tự nhiên của relationship. Nếu nghiệp vụ cần thứ tự như vị trí thành viên, thứ tự bước trong quy trình hoặc thứ tự sản phẩm, hãy lưu `position` trên relationship hoặc một property phù hợp và truy vấn với `ORDER BY`.

Nếu dùng `Set`, tránh dựa vào `hashCode` thay đổi sau khi entity nhận ID sinh tự động. Một khóa nghiệp vụ ổn định có thể là cơ sở cho `equals`/`hashCode`, nhưng cần bảo đảm khóa đó duy nhất và bất biến.

## 6. Relationship có thuộc tính riêng trong collection

Khi liên kết mang dữ liệu riêng, chẳng hạn vai trò thành viên hoặc thời điểm bắt đầu theo dõi, không nên chỉ dùng collection node đích vì sẽ không có chỗ rõ ràng để ánh xạ thuộc tính trên relationship. Spring Data Neo4j hỗ trợ `@RelationshipProperties` và `@TargetNode`.

Ví dụ nhóm có nhiều thành viên, mỗi quan hệ `HAS_MEMBER` mang vai trò và ngày tham gia:

```java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@Node("Team")
public class Team {
    @Id
    private String teamKey;

    @Relationship(type = "HAS_MEMBER", direction = Relationship.Direction.OUTGOING)
    private List<TeamMembership> memberships = new ArrayList<>();
}

@RelationshipProperties
public class TeamMembership {
    @TargetNode
    private Person member;

    private String role;
    private LocalDate joinedOn;
}
```

Collection `memberships` chứa các đối tượng quan hệ, không phải trực tiếp các node `Person`. Mỗi phần tử xác định node đích qua `@TargetNode` và các property của relationship như `role`, `joinedOn`.

Thêm thành viên lúc này cần tạo đối tượng `TeamMembership` với node đích và các thuộc tính quan hệ. Bỏ thành viên là bỏ đối tượng membership tương ứng khỏi collection. Thay collection là thay tập membership, bao gồm cả dữ liệu vai trò và ngày tham gia.

Nếu cần định danh riêng cho relationship trong những thao tác phức tạp, có thể dùng cơ chế ID relationship được Spring Data Neo4j hỗ trợ theo phiên bản đang sử dụng. Chỉ bổ sung khi có nhu cầu thực tế; với một quan hệ đơn giản có thuộc tính, `@RelationshipProperties` và `@TargetNode` đã thể hiện được mô hình.

## 7. Khi nào nên cập nhật bằng Cypher trực tiếp?

Collection mapping thuận tiện khi nghiệp vụ làm việc với một aggregate có số lượng quan hệ vừa phải và cần lưu trạng thái của entity. Nhưng nếu một node có hàng trăm nghìn relationship, việc nạp toàn bộ collection chỉ để thêm hoặc bỏ một cạnh có thể tốn bộ nhớ và thời gian.

Trong trường hợp đó, có thể dùng Cypher chuyên biệt qua `Neo4jClient`:

```java
neo4jClient.query("""
    MATCH (source:Person {personKey: $sourceKey})
    MATCH (target:Person {personKey: $targetKey})
    MERGE (source)-[:FOLLOWS]->(target)
    """)
    .bind(sourceKey).to("sourceKey")
    .bind(targetKey).to("targetKey")
    .run();
```

Để bỏ một cạnh:

```java
neo4jClient.query("""
    MATCH (source:Person {personKey: $sourceKey})
          -[r:FOLLOWS]->
          (target:Person {personKey: $targetKey})
    DELETE r
    """)
    .bind(sourceKey).to("sourceKey")
    .bind(targetKey).to("targetKey")
    .run();
```

Cypher trực tiếp chỉ tác động relationship được match. Tuy nhiên, entity đang nằm trong persistence context hoặc đã được đọc trước đó có thể không tự phản ánh thay đổi này trong bộ nhớ. Sau thao tác, hãy đọc lại dữ liệu khi cần trạng thái mới; tránh lưu một entity cũ với collection lỗi thời.

Khi dùng Cypher trực tiếp để thêm hoặc xóa relationship, cần kiểm tra node nguồn và đích tồn tại, xử lý trường hợp không match, và đặt thao tác trong transaction phù hợp. Dùng tham số có tên thay vì nối chuỗi đầu vào vào câu Cypher.

## 8. Quy tắc nghiệp vụ và tính nhất quán

Thêm hoặc bỏ relationship thường có quy tắc nghiệp vụ đi kèm. Ví dụ, một người không được tự theo dõi chính mình; thành viên không thể được thêm hai lần vào cùng nhóm; người dùng bị khóa không thể tạo liên kết mới.

Nên kiểm tra các quy tắc này ở service trước khi lưu:

```java
if (sourceKey.equals(targetKey)) {
    throw new IllegalArgumentException("Không thể tự theo dõi chính mình");
}
```

Nếu có nhiều request đồng thời cùng thêm một liên kết, kiểm tra trong Java có thể không đủ để chống race condition. Có thể dùng `MERGE` trong Cypher cho thao tác tạo cạnh và/hoặc thiết kế constraint, khóa nghiệp vụ và transaction phù hợp. Neo4j cho phép nhiều relationship cùng loại giữa cùng hai node, vì vậy uniqueness của cặp đầu-cuối cần được bảo đảm bằng thiết kế thao tác hoặc mô hình dữ liệu.

Với relationship có thuộc tính, cần xác định khóa nghiệp vụ của liên kết. Ví dụ, nếu một thành viên có thể tham gia cùng nhóm ở nhiều giai đoạn khác nhau, việc chỉ xác định theo cặp `(Team, Person)` có thể chưa đủ; có thể cần mô hình hóa kỳ tham gia hoặc trạng thái membership rõ ràng.

## 9. Kiểm thử thêm, bỏ và thay thế liên kết

Integration test nên kiểm tra trạng thái đồ thị sau mỗi thao tác, không chỉ kiểm tra collection trong bộ nhớ.

Một kịch bản kiểm thử cho `FOLLOWS`:

1. Tạo ba node người dùng An, Bình và Chi.
2. Thêm Bình vào `following` của An rồi lưu; truy vấn Cypher xác nhận có một relationship `FOLLOWS`.
3. Gọi thao tác thêm Bình lần nữa; xác nhận không phát sinh liên kết trùng theo quy tắc ứng dụng.
4. Thêm Chi; xác nhận An có hai người được theo dõi.
5. Bỏ Bình; xác nhận cạnh An → Bình không còn, nhưng node Bình và cạnh An → Chi vẫn tồn tại.
6. Thay collection bằng danh sách chỉ có Bình; xác nhận trạng thái cuối cùng chỉ còn cạnh An → Bình.

Các truy vấn xác minh có thể dùng:

```cypher
MATCH (source:Person {personKey: $sourceKey})-[r:FOLLOWS]->(target:Person)
RETURN target.personKey AS targetKey, count(r) AS relationshipCount
ORDER BY targetKey
```

Để kiểm tra node đích vẫn còn sau khi bỏ relationship:

```cypher
MATCH (target:Person {personKey: $targetKey})
RETURN count(target) AS targetStillExists
```

Test nên chạy trên database cô lập và dọn dữ liệu sau mỗi trường hợp. Khi kiểm thử logic thay collection, cần xác nhận cả các liên kết bị loại lẫn liên kết được giữ lại.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Thêm phần tử nhưng không thấy relationship mới | Chưa gọi `save`, hướng relationship không đúng hoặc node đích không được nhận diện | Kiểm tra repository save, `direction` và node đích. |
| Một người xuất hiện nhiều lần trong collection | List cho phép trùng hoặc kiểm tra equality không đúng | Kiểm tra theo khóa nghiệp vụ ổn định trước khi thêm. |
| Bỏ liên kết nhưng node đích biến mất khỏi kết quả khác | Nhầm xóa relationship với xóa node hoặc dùng `DETACH DELETE` | Chỉ xóa relationship cần bỏ; giữ nguyên node đích. |
| Thay danh sách làm mất nhiều liên kết ngoài dự kiến | Lưu entity với collection chưa được nạp đầy đủ | Đọc đầy đủ collection cần thay đổi hoặc dùng Cypher chuyên biệt. |
| Thứ tự quan hệ thay đổi sau khi đọc | Neo4j không bảo đảm thứ tự tự nhiên của relationship | Lưu property thứ tự và dùng `ORDER BY`. |
| Thêm cạnh trùng khi có request đồng thời | Kiểm tra trùng chỉ thực hiện ở Java | Dùng `MERGE` và thiết kế transaction/constraint phù hợp. |
| Relationship có role nhưng entity không lưu role | Ánh xạ trực tiếp node đích, bỏ qua dữ liệu trên cạnh | Dùng `@RelationshipProperties` và `@TargetNode`. |

## 11. Ghi nhớ

Collection được ánh xạ bằng `@Relationship` biểu diễn các node liên kết với entity theo một kiểu và hướng relationship cụ thể. Để thêm, bỏ hoặc thay thế liên kết, hãy cập nhật collection theo đúng ý định nghiệp vụ rồi lưu entity trong transaction phù hợp. Việc bỏ phần tử khỏi collection chỉ loại bỏ liên kết tương ứng; node đích vẫn tồn tại.

Hãy bảo đảm collection được nạp đầy đủ trước khi lưu, tránh dùng entity hoặc projection một phần làm trạng thái ghi. Với quan hệ có thuộc tính riêng, dùng `@RelationshipProperties` và `@TargetNode`. Khi số lượng liên kết lớn hoặc chỉ cần thay đổi một cạnh, Cypher trực tiếp qua `Neo4jClient` có thể phù hợp hơn, nhưng cần đọc lại trạng thái để tránh ghi đè bằng entity cũ. Các quy tắc này giúp ánh xạ quan hệ trong Spring Data Neo4j rõ ràng, an toàn và nhất quán với mô hình đồ thị.
