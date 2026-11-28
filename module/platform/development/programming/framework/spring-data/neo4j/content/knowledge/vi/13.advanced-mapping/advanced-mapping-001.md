# @DynamicLabels và tập label được quản lý khi đọc–ghi

Trong Neo4j, một node có thể mang nhiều label. Label tĩnh thường xác định loại thực thể, chẳng hạn `Person` hoặc `Product`. Ngoài ra, ứng dụng có thể cần gắn thêm label theo trạng thái hoặc phân loại tại thời điểm chạy, ví dụ `VIP`, `Moderator` hoặc `Featured`. Khi dùng Spring Data Neo4j, annotation `@DynamicLabels` cho phép ánh xạ tập label bổ sung này vào một collection trên entity.

Điểm quan trọng của annotation nằm ở cả hai chiều đọc và ghi: khi đọc, Spring Data Neo4j thu thập các label không được khai báo tĩnh vào collection; khi ghi entity, tập label trên node được thay bằng label tĩnh cộng với các giá trị trong collection. Vì vậy, collection này là nguồn sự thật cho các dynamic label mà entity quản lý. Hiểu đúng hành vi đó giúp cập nhật label có chủ đích và tránh xóa nhầm label do hệ thống khác quản lý.

## 1. Label tĩnh và label động trong Neo4j

Neo4j cho phép một node có nhiều label cùng lúc:

```text
(:Person:VIP:Moderator {
    personKey: 'P-100',
    name: 'An'
})
```

Trong ví dụ này:

- `Person` xác định loại node trong mô hình miền.
- `VIP` và `Moderator` là các phân loại bổ sung có thể thay đổi theo nghiệp vụ.
- `personKey` và `name` là property chứa dữ liệu của node.

Với Spring Data Neo4j, các label được khai báo ngầm từ tên lớp hoặc khai báo rõ qua `@Node` và class hierarchy được xem là **label tĩnh**. Chúng thuộc metadata của mô hình Java và không được thay đổi tùy ý qua collection dynamic labels.

**Dynamic label** là label bổ sung được quản lý tại thời điểm chạy. Ví dụ, một người có thể được gắn `VIP` sau khi đạt điều kiện thành viên, hoặc bỏ label `Moderator` khi vai trò quản trị kết thúc.

Label và property phục vụ hai mục đích khác nhau:

| Thành phần | Dùng để biểu diễn | Ví dụ |
|---|---|---|
| Label tĩnh | Loại node theo mô hình entity | `Person`, `Product` |
| Dynamic label | Phân loại bổ sung có thể thay đổi | `VIP`, `Featured` |
| Property | Dữ liệu mô tả từng node | `name`, `createdAt`, `score` |

Không nên biến mọi giá trị nghiệp vụ thành label. Những dữ liệu như tên, email, số điểm hoặc thời điểm cập nhật phù hợp với property. Label phù hợp hơn với các nhóm phân loại có ý nghĩa khi truy vấn theo pattern, ví dụ tìm tất cả `Person` có label `VIP`.

## 2. Khai báo @DynamicLabels trong entity

`@DynamicLabels` thuộc package `org.springframework.data.neo4j.core.schema` và được đặt ở cấp field. Field được đánh dấu phải có kiểu `Collection<String>`; các kiểu như `List<String>` hoặc `Set<String>` đều là lựa chọn hợp lệ.

Ví dụ entity `Person`:

```java
import java.util.HashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.DynamicLabels;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personKey;

    private String name;

    @DynamicLabels
    private Set<String> dynamicLabels = new HashSet<>();

    public String getPersonKey() {
        return personKey;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Set<String> getDynamicLabels() {
        return dynamicLabels;
    }
}
```

Trong ví dụ:

- `@Node("Person")` xác định label tĩnh của entity.
- `personKey` là định danh nghiệp vụ của node.
- `dynamicLabels` là nguồn label động do entity quản lý.
- `HashSet` giúp tránh phần tử trùng trong bộ nhớ; thứ tự label không mang ý nghĩa nghiệp vụ.

Tên field `dynamicLabels` chỉ là tên thuộc tính Java. Vì field được đánh dấu `@DynamicLabels`, collection này được dùng để quản lý label của node, không được lưu như một property dạng danh sách có tên `dynamicLabels`.

## 3. Hành vi khi đọc entity

Khi Spring Data Neo4j tải một node và ánh xạ thành `Person`, framework xác định các label tĩnh từ class hierarchy và `@Node`. Những label còn lại trên node sẽ được thu thập vào collection được đánh dấu `@DynamicLabels`.

Giả sử Neo4j có node:

```cypher
CREATE (:Person:VIP:Moderator {
    personKey: 'P-100',
    name: 'An'
})
```

Repository đọc node:

```java
public interface PersonRepository extends Neo4jRepository<Person, String> {
}
```

```java
Person person = personRepository.findById("P-100")
    .orElseThrow();

System.out.println(person.getDynamicLabels());
// [VIP, Moderator] (thứ tự không được bảo đảm khi dùng Set)
```

`Person` là label tĩnh được ánh xạ từ `@Node`, vì vậy nó không nằm trong `dynamicLabels`. Các label `VIP` và `Moderator` là label bổ sung nên được đưa vào collection.

Để xem toàn bộ label trực tiếp từ Neo4j, có thể chạy:

```cypher
MATCH (p:Person {personKey: $personKey})
RETURN labels(p) AS allLabels
```

Hàm `labels(p)` trả về cả label tĩnh lẫn label động. Khi so sánh với `getDynamicLabels()`, cần loại các label tĩnh đã được khai báo qua entity.

## 4. Hành vi khi ghi entity: collection là nguồn sự thật

Khi lưu một entity có `@DynamicLabels`, Spring Data Neo4j ghi tập label của node dựa trên hai nguồn:

1. Các label tĩnh được xác định bởi class hierarchy và `@Node`.
2. Tất cả giá trị hiện có trong collection được đánh dấu `@DynamicLabels`.

Tập label trên node được thay thế bằng hợp của hai nhóm đó. Những label khác không thuộc class hierarchy, `@Node` hoặc collection sẽ bị loại khỏi node khi ghi.

Ví dụ, entity sau khi đọc có:

```java
person.getDynamicLabels(); // [VIP, Moderator]
```

Nếu ứng dụng bỏ `Moderator` rồi lưu:

```java
person.getDynamicLabels().remove("Moderator");
personRepository.save(person);
```

Node sau khi lưu sẽ có label tĩnh `Person` và dynamic label `VIP`. Label `Moderator` bị gỡ khỏi node.

Nếu collection rỗng và entity được lưu, các dynamic label được quản lý sẽ bị loại bỏ; label tĩnh `Person` vẫn được giữ:

```java
person.getDynamicLabels().clear();
personRepository.save(person);
```

Đây là điểm khác biệt quan trọng so với việc chỉ thêm label bằng một câu Cypher. `@DynamicLabels` quản lý toàn bộ tập label bổ sung của node theo collection, không chỉ thêm những giá trị mới.

## 5. Thêm, bỏ và thay thế dynamic labels

Có thể đóng gói các thao tác cập nhật label vào service để kiểm tra quy tắc nghiệp vụ trước khi lưu.

```java
@Service
public class PersonLabelService {

    private static final Set<String> ALLOWED_LABELS = Set.of(
        "VIP",
        "MODERATOR",
        "BETA_TESTER"
    );

    private final PersonRepository personRepository;

    public PersonLabelService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional
    public Person addLabel(String personKey, String label) {
        validateLabel(label);

        Person person = load(personKey);
        person.getDynamicLabels().add(label);
        return personRepository.save(person);
    }

    @Transactional
    public Person removeLabel(String personKey, String label) {
        Person person = load(personKey);
        person.getDynamicLabels().remove(label);
        return personRepository.save(person);
    }

    @Transactional
    public Person replaceLabels(String personKey, Set<String> labels) {
        labels.forEach(this::validateLabel);

        Person person = load(personKey);
        person.getDynamicLabels().clear();
        person.getDynamicLabels().addAll(labels);
        return personRepository.save(person);
    }

    private Person load(String personKey) {
        return personRepository.findById(personKey)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy người dùng"));
    }

    private void validateLabel(String label) {
        if (!ALLOWED_LABELS.contains(label)) {
            throw new IllegalArgumentException("Dynamic label không được hỗ trợ");
        }
    }
}
```

Trong ví dụ, allowlist giới hạn những label mà nghiệp vụ cho phép. Danh sách này giúp tránh việc một request tùy ý gắn các phân loại không được thiết kế vào node. Các label được chọn cần thống nhất với truy vấn, phân quyền và quy ước đặt tên của ứng dụng.

Ba thao tác có ý nghĩa khác nhau:

| Nghiệp vụ | Thao tác trên collection | Kết quả sau `save` |
|---|---|---|
| Thêm label | `add("VIP")` | Node có thêm `VIP` nếu chưa có |
| Bỏ label | `remove("VIP")` | Node không còn `VIP` |
| Thay toàn bộ | `clear()` rồi `addAll(labels)` | Tập dynamic label bằng đúng tập mới |

Không dùng `clear()` khi chỉ muốn bỏ một label. Vì collection là nguồn sự thật cho toàn bộ dynamic label, `clear()` sẽ yêu cầu loại bỏ tất cả label động khi lưu.

## 6. Label tĩnh không bị thay đổi bởi collection

Label tĩnh đến từ `@Node` hoặc class hierarchy. Ví dụ:

```java
@Node("Person")
public class Person {
    // ...
}
```

`Person` là label tĩnh. Nếu collection chỉ chứa `VIP`, node sau khi lưu có các label `Person` và `VIP`.

Nếu entity dùng kế thừa, các label được xác định bởi class hierarchy cũng thuộc nhóm tĩnh. Không đưa các label tĩnh vào collection với mục đích bật/tắt chúng tại runtime. Muốn thay đổi cách phân loại động, hãy thêm hoặc bỏ các label bổ sung; muốn thay đổi loại entity, cần xem lại mô hình class và mapping.

Ví dụ một truy vấn có thể tìm theo label tĩnh và label động cùng lúc:

```cypher
MATCH (p:Person:VIP)
RETURN p.personKey AS personKey, p.name AS name
```

Label `Person` xác định loại entity; `VIP` lọc nhóm người có phân loại động đó.

## 7. Rủi ro khi nhiều ứng dụng cùng sửa label

Vì collection `@DynamicLabels` là nguồn sự thật khi ghi, không nên dùng annotation này nếu ứng dụng khác có thể tự do thêm label vào cùng node mà không cập nhật collection.

Ví dụ:

1. Spring Data Neo4j đọc node và thấy dynamic labels `[VIP]`.
2. Một ứng dụng bên ngoài thêm label `Imported` trực tiếp bằng Cypher.
3. Entity Spring Data Neo4j vẫn giữ collection `[VIP]`.
4. Khi entity được lưu, framework ghi lại tập label tĩnh cộng `[VIP]`; `Imported` có thể bị loại bỏ.

Đây không phải lỗi ngẫu nhiên: đó là hành vi quản lý label được quy định bởi `@DynamicLabels`. Tài liệu Spring Data Neo4j cũng khuyến cáo không dùng annotation này khi các ứng dụng khác tự thêm label vào node, vì tập label do entity quản lý sẽ trở thành tập label được ghi xuống database.

Nếu nhiều thành phần cùng sở hữu label, nên chọn một trong các hướng:

- Chỉ định một service làm chủ toàn bộ tập dynamic labels và các thành phần khác gửi yêu cầu cập nhật đến service đó.
- Không dùng `@DynamicLabels` trên entity được nhiều ứng dụng cập nhật label độc lập; quản lý từng label bằng các thao tác Cypher chuyên biệt.
- Tách loại phân loại do từng hệ thống sở hữu thành property hoặc mô hình node/relationship riêng nếu chúng không thực sự cần là label.

Ngoài ra, cần chú ý cập nhật đồng thời. Hai request cùng đọc một tập label cũ rồi lần lượt lưu hai thay đổi có thể khiến thay đổi của request sau ghi đè tập label của request trước. Với nghiệp vụ quan trọng, hãy dùng transaction, optimistic locking bằng `@Version` khi phù hợp, hoặc thiết kế thao tác cập nhật tập label có kiểm soát ở một nơi. `@Version` chỉ bảo vệ các luồng ghi tuân theo cơ chế version của Spring Data; các cập nhật Cypher bên ngoài không tự động tham gia cơ chế đó.

## 8. Không nhầm dynamic label với property hoặc relationship type

`@DynamicLabels` chỉ quản lý label của node. Nó không ánh xạ property, không thay thế `@Relationship`, và không làm thay đổi relationship type.

| Nhu cầu | Cách mô hình hóa |
|---|---|
| Phân loại node theo nhóm có ý nghĩa truy vấn | Label, có thể quản lý động bằng `@DynamicLabels` |
| Lưu trạng thái như `status = "ACTIVE"` | Property `status` |
| Lưu điểm, thời gian, tên hoặc mã định danh | Property có kiểu phù hợp |
| Mô tả liên kết giữa hai node | `@Relationship` với relationship type |
| Lưu dữ liệu riêng trên relationship | `@RelationshipProperties` và `@TargetNode` |

Ví dụ, trạng thái đơn hàng thay đổi liên tục thường phù hợp với property:

```cypher
MATCH (o:Order {orderNumber: $orderNumber})
SET o.status = 'PAID'
```

Không nhất thiết phải biến mỗi trạng thái thành label `PENDING`, `PAID`, `CANCELLED`. Nếu dùng label để phân loại, cần cân nhắc số lượng nhóm, cách truy vấn và tác động đến những ứng dụng khác cùng đọc node.

## 9. Kiểm tra label trước và sau khi lưu

Khi triển khai `@DynamicLabels`, nên có integration test xác nhận cả chiều đọc lẫn chiều ghi.

Một kịch bản kiểm thử:

1. Tạo node `Person` có label tĩnh `Person` và dynamic labels `VIP`, `Moderator`.
2. Đọc qua `PersonRepository` và xác nhận collection chứa `VIP`, `Moderator` nhưng không chứa `Person`.
3. Bỏ `Moderator`, lưu entity.
4. Chạy `labels(p)` và xác nhận node còn `Person`, `VIP`.
5. Xóa toàn bộ collection, lưu entity.
6. Xác nhận node chỉ còn label tĩnh `Person`.
7. Thêm một label ngoài collection bằng Cypher, sau đó lưu entity đã đọc trước đó và xác nhận label ngoài tập quản lý bị loại bỏ theo quy tắc của `@DynamicLabels`.

Ví dụ truy vấn kiểm tra:

```cypher
MATCH (p:Person {personKey: $personKey})
RETURN labels(p) AS labels
```

Do thứ tự label không phải một phần của mô hình nghiệp vụ, hãy so sánh dưới dạng tập hợp trong test thay vì so sánh thứ tự của danh sách.

Kiểm thử cũng nên bao gồm trường hợp collection rỗng, thêm label đã tồn tại, bỏ label không có và cập nhật đồng thời. Chạy test trên Neo4j cô lập để tránh thay đổi label của dữ liệu dùng chung.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Collection không nhận label mong đợi | Label đó thực tế là label tĩnh từ `@Node` hoặc class hierarchy | Phân biệt label tĩnh và label động; kiểm tra `labels(node)`. |
| Lưu entity làm mất label do ứng dụng khác thêm | `@DynamicLabels` ghi lại toàn bộ tập label theo collection | Không dùng annotation khi nhiều ứng dụng tự quản lý label độc lập; thống nhất quyền sở hữu. |
| Collection rỗng làm mất các label bổ sung | Collection rỗng có nghĩa không quản lý dynamic label nào | Chỉ clear khi thực sự muốn bỏ toàn bộ dynamic labels. |
| Label bị trùng trong collection | Dùng `List` hoặc logic thêm không kiểm tra | Dùng `Set<String>` hoặc chuẩn hóa collection trước khi lưu. |
| Không thể thay đổi label `Person` | Đây là label tĩnh từ `@Node("Person")` | Thay đổi dynamic labels chỉ tác động đến label bổ sung; xem lại class mapping nếu muốn đổi label tĩnh. |
| Label được tạo từ đầu vào không hợp lệ | Thiếu allowlist hoặc quy ước tên | Kiểm tra label tại service và chỉ cho phép nhóm đã định nghĩa. |
| Mất cập nhật khi có hai request đồng thời | Hai entity cũ ghi đè toàn bộ tập label | Kiểm soát transaction, version hoặc tập trung hóa thao tác cập nhật. |

## 11. Quy trình thiết kế và vận hành

1. Xác định label tĩnh cho từng entity bằng `@Node` và class hierarchy.
2. Chọn những phân loại bổ sung thực sự cần là label; dữ liệu mô tả thông thường nên là property.
3. Khai báo một collection `Collection<String>` với `@DynamicLabels` và khởi tạo collection rỗng.
4. Xác định rõ service nào sở hữu tập dynamic labels; tránh để ứng dụng khác sửa label độc lập.
5. Kiểm tra giá trị label theo allowlist hoặc quy tắc nghiệp vụ.
6. Thêm, bỏ hoặc thay collection trong service và lưu entity trong transaction phù hợp.
7. Xác minh `labels(node)` sau khi đọc và ghi; kiểm thử cả collection rỗng và cập nhật đồng thời.

## 12. Ghi nhớ

`@DynamicLabels` đánh dấu một field kiểu `Collection<String>` làm nguồn quản lý label động của node. Khi đọc, Spring Data Neo4j đưa vào collection những label không được định nghĩa tĩnh bởi class hierarchy và `@Node`. Khi ghi, tập label của node được thay bằng label tĩnh cộng với nội dung collection.

Điều đó khiến thao tác thêm, bỏ hoặc thay dynamic label rất trực tiếp, nhưng cũng có nghĩa label ngoài collection sẽ bị loại khỏi node khi entity được lưu. Chỉ dùng annotation khi ứng dụng sở hữu toàn bộ tập label bổ sung của node. Nếu nhiều ứng dụng cùng thêm label độc lập, hãy chọn cơ chế quản lý khác hoặc tập trung quyền sở hữu để tránh mất dữ liệu.

## Tài liệu tham khảo

- [Spring Data Neo4j – DynamicLabels API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/schema/DynamicLabels.html)
- [Spring Data Neo4j – Metadata-based Mapping, mục Dynamic or runtime managed labels](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)
