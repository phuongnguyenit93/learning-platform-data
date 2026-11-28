# Phát hiện entity mới và vai trò của @Version với ID tự gán

Khi gọi `save()` trong Spring Data Neo4j (SDN), framework cần xác định entity đang đại diện cho một node mới hay node đã tồn tại. Quyết định này ảnh hưởng trực tiếp đến cách SDN ghi dữ liệu: tạo node mới hay cập nhật node hiện có.

Với ID do ứng dụng tự gán, trường định danh thường đã có giá trị ngay từ lúc tạo object. Nếu chỉ dựa vào ID, SDN có thể xem entity đó là entity đã tồn tại dù node chưa được tạo trong Neo4j. Thuộc tính `@Version` giải quyết tình huống này đồng thời cung cấp cơ chế optimistic locking để phát hiện cập nhật cạnh tranh.

## 1. Vì sao SDN cần phát hiện entity mới?

Xét một entity `Person` có ID do ứng dụng cấp:

~~~java
@Node("Person")
public class Person {
    @Id
    private String id;

    private String name;
}
~~~

Ứng dụng có thể tạo object với ID ngay từ đầu:

~~~java
Person person = new Person("person-100", "An");
personRepository.save(person);
~~~

Trước khi gọi `save`, object đã có `id = "person-100"`, nhưng node tương ứng có thể chưa tồn tại trong database. SDN cần biết phải thực hiện thao tác tạo mới hay cập nhật. Đây là khái niệm *entity state detection* hay phát hiện trạng thái mới của entity.

Trong Spring Data, chiến lược phát hiện trạng thái thường ưu tiên thuộc tính được đánh dấu `@Version` nếu entity có thuộc tính này. Nếu không có version property, framework dựa vào ID:

| Entity | Cách phát hiện trạng thái mặc định |
| --- | --- |
| Có `@Version` dạng tham chiếu và giá trị `null` | Entity mới |
| Có `@Version` đã có giá trị | Entity đã tồn tại |
| Không có `@Version`, ID là `null` | Entity mới |
| Không có `@Version`, ID khác `null` | Entity đã tồn tại |

Quy tắc này giải thích vì sao ID tự gán cần được quan tâm: ID khác `null` ngay khi khởi tạo không chứng minh node đã tồn tại trong Neo4j.

## 2. Vấn đề khi dùng ID tự gán mà không có @Version

Nếu entity dùng ID do ứng dụng cấp và không có thuộc tính version, ID đã có giá trị khiến entity được nhận diện là entity đã tồn tại. Khi gọi `save`, SDN có thể đi theo luồng cập nhật node hiện có. Nếu node chưa được tạo, kết quả không phải là thao tác tạo mới mà ứng dụng mong muốn; tùy truy vấn và phiên bản, việc cập nhật có thể không tác động node nào hoặc dẫn đến lỗi khi xử lý kết quả.

Không nên dùng việc truy vấn database trước mỗi lần lưu để tự đoán trạng thái nếu có thể giải quyết bằng cơ chế state detection. Cách kiểm tra trước rồi mới ghi còn tạo ra khoảng thời gian giữa hai thao tác; một request khác có thể thay đổi dữ liệu trong khoảng đó.

## 3. Dùng @Version với ID tự gán

Khai báo thuộc tính version bằng annotation `@Version` của Spring Data. Với ID tự gán, một kiểu tham chiếu như `Long` cho phép trạng thái `null` biểu thị entity mới:

~~~java
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String name;

    @Version
    private Long version;

    public Person(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public Long getVersion() { return version; }
    public void setName(String name) { this.name = name; }
}
~~~

Khi tạo object mới, `id` đã có giá trị nhưng `version` vẫn là `null`. SDN sử dụng version property để nhận diện entity mới và thực hiện thao tác tạo node. Sau khi lưu, SDN quản lý version được khởi tạo trong entity. Khi entity được đọc lại, version có giá trị và được dùng trong các lần cập nhật tiếp theo.

Ví dụ sử dụng repository:

~~~java
Person person = new Person("person-100", "An");
Person created = personRepository.save(person);

created.setName("An Nguyen");
Person updated = personRepository.save(created);
~~~

Không tự đặt version thành một giá trị tùy ý trước khi lưu. Hãy để SDN quản lý version property. Nếu entity mới có version khác `null`, framework có thể xem nó là entity đã tồn tại; điều này làm sai mục đích phát hiện entity mới.

`Long` được dùng trong ví dụ vì có trạng thái `null` rõ ràng. Với kiểu version nguyên thủy, không có trạng thái null; chiến lược phát hiện newness có thể dựa trên giá trị mặc định của kiểu đó. Đối với entity dùng ID tự gán, kiểu tham chiếu nullable giúp thể hiện trạng thái ban đầu rõ ràng hơn.

## 4. @Version còn cung cấp optimistic locking

`@Version` không chỉ giúp phát hiện entity mới. Với entity đã tồn tại, SDN dùng version hiện tại để kiểm soát cập nhật đồng thời. Cơ chế này thường được gọi là optimistic locking.

Giả sử hai request cùng đọc một node có `version = 3`:

1. Request A đọc entity với version 3.
2. Request B cũng đọc entity với version 3.
3. Request A cập nhật và lưu thành công; version được tăng lên 4.
4. Request B vẫn giữ object cũ với version 3 và cố gắng lưu.
5. SDN phát hiện version trong database không còn khớp với version mà Request B đã đọc, nên cập nhật của B bị từ chối.

Nhờ đó, thay đổi của Request B không âm thầm ghi đè thay đổi mới hơn của Request A. Ứng dụng có thể xử lý xung đột bằng cách tải lại dữ liệu mới nhất, kết hợp thay đổi theo quy tắc nghiệp vụ rồi thử lại nếu phù hợp.

Khi phát hiện version không khớp, Spring Data thường báo lỗi thuộc nhóm `OptimisticLockingFailureException`. Hãy xử lý lỗi ở tầng nghiệp vụ hoặc API để trả về thông báo xung đột phù hợp, thay vì tự động thử lại vô hạn.

## 5. Ràng buộc duy nhất cho ID nghiệp vụ

ID tự gán thường là mã nghiệp vụ như `person-100`, mã khách hàng hoặc UUID do ứng dụng tạo. Để bảo đảm không có hai node cùng nhãn mang cùng mã, hãy tạo uniqueness constraint trong Neo4j:

~~~cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (person:Person)
REQUIRE person.id IS UNIQUE
~~~

Ràng buộc này được database thực thi, bảo vệ dữ liệu ngay cả khi nhiều instance ứng dụng cùng tạo node. `@Version` và uniqueness constraint giải quyết hai vấn đề khác nhau:

- `@Version` hỗ trợ nhận diện trạng thái entity và phát hiện cập nhật dựa trên version.
- Uniqueness constraint ngăn nhiều node cùng nhãn có chung giá trị thuộc tính ID nghiệp vụ.

Không nên nhầm ID nghiệp vụ với internal ID của Neo4j. Với mô hình cần định danh ổn định qua các lần triển khai hoặc trao đổi với hệ thống khác, nên dùng thuộc tính định danh do ứng dụng quản lý và tạo constraint phù hợp.

## 6. So sánh các cách phát hiện entity mới

| Cách tiếp cận | Phù hợp khi | Điểm cần chú ý |
| --- | --- | --- |
| ID do SDN/Neo4j sinh và ban đầu là `null` | Ứng dụng chấp nhận ID được sinh khi lưu | ID chỉ có sau khi entity được tạo; cần chọn generator phù hợp với mô hình |
| ID do ứng dụng gán kết hợp `@Version` | Cần có ID ngay khi tạo object và muốn optimistic locking | Giữ version `null` cho entity mới; không tự cập nhật version |
| Triển khai `Persistable` | Có quy tắc xác định trạng thái mới riêng ngoài ID/version | Phải quản lý chính xác cờ `isNew()` sau khi tạo và tải entity |

Với ID tự gán, `@Version` thường là lựa chọn phù hợp vì vừa giải quyết newness detection vừa bảo vệ cập nhật đồng thời. `Persistable` là phương án khi ứng dụng cần kiểm soát trạng thái mới theo quy tắc riêng; không nên thêm cơ chế này nếu version property đã đáp ứng yêu cầu.

## 7. Lưu ý khi dùng truy vấn Cypher tùy chỉnh

Các thao tác lưu entity qua repository hoặc template có thể áp dụng cơ chế mapping và version của SDN. Với truy vấn Cypher tùy chỉnh tự ghi node, không nên mặc định rằng mọi câu lệnh đều tự động thực hiện optimistic locking như thao tác lưu entity thông thường.

Ví dụ, nếu một lệnh cập nhật trực tiếp một node có version, logic nghiệp vụ cần kiểm tra version mong đợi và tăng version một cách nguyên tử. Một dạng Cypher minh họa:

~~~cypher
MATCH (person:Person {id: $id})
WHERE person.version = $expectedVersion
SET person.name = $name,
    person.version = person.version + 1
RETURN person.id AS id, person.version AS version
~~~

Nếu không có node khớp version, truy vấn không trả về bản ghi. Ứng dụng cần diễn giải trường hợp đó thành xung đột hoặc entity không tồn tại theo quy tắc nghiệp vụ. Với các truy vấn custom trong `@Query`, `Neo4jClient` hoặc `Neo4jTemplate`, hãy kiểm tra rõ cách version được xử lý trong phiên bản SDN đang dùng và tự triển khai kiểm tra nếu câu lệnh bỏ qua cơ chế lưu entity tiêu chuẩn.

## 8. Kiểm thử trạng thái mới và cập nhật đồng thời

Nên kiểm thử ít nhất các trường hợp sau:

1. **Tạo mới với ID tự gán:** khởi tạo entity có ID và version `null`, gọi `save`, xác nhận node được tạo và version được khởi tạo.
2. **Lưu lại entity đã tạo:** thay đổi một thuộc tính rồi lưu, xác nhận node được cập nhật và version thay đổi.
3. **ID đã tồn tại:** thử tạo một entity khác với cùng ID nghiệp vụ; uniqueness constraint phải ngăn dữ liệu trùng.
4. **Cập nhật cạnh tranh:** tải cùng một entity ở hai transaction, lưu transaction thứ nhất, sau đó thử lưu bản cũ từ transaction thứ hai; xác nhận lỗi optimistic locking được phát hiện.
5. **Custom Cypher:** nếu ứng dụng có lệnh ghi trực tiếp, kiểm tra rằng truy vấn xử lý version và tình huống xung đột theo thiết kế.

Khi kiểm thử optimistic locking, cần dùng hai bản entity độc lập cùng đọc một version ban đầu. Nếu chỉ lưu một object tuần tự, bài kiểm thử chưa mô phỏng được tình huống hai request cùng cập nhật.

## 9. Bài tập tự kiểm tra

1. Vì sao entity có ID tự gán khác `null` có thể bị nhận diện là entity đã tồn tại?
2. Khi entity có `@Version` và version đang `null`, SDN hiểu trạng thái của entity như thế nào?
3. `@Version` khác uniqueness constraint ở điểm nào?
4. Mô tả tình huống hai request cùng đọc version 3 và vì sao một lần cập nhật phải bị từ chối.
5. Vì sao không nên tự đặt lại version trước mỗi lần gọi `save()`?
6. Nếu dùng Cypher tùy chỉnh để cập nhật node có version, cần bổ sung logic gì để phát hiện xung đột?

Khi hoàn thành bài học, bạn cần phân biệt được ID định danh node với version kiểm soát trạng thái cập nhật, biết cách dùng `@Version` cho entity có ID tự gán và hiểu optimistic locking giúp bảo vệ dữ liệu trước các cập nhật cạnh tranh trong ứng dụng Spring Data Neo4j.
