# Thiết kế entity bất biến và phương thức wither

Trong Spring Data Neo4j (SDN), entity là mô hình Java đại diện cho node và các relationship trong đồ thị. Theo cách thông thường, một entity có constructor rỗng cùng setter để framework gán dữ liệu sau khi tạo đối tượng. Tuy nhiên, thiết kế này cho phép nhiều nơi thay đổi trạng thái entity và đôi khi làm đối tượng rơi vào trạng thái chưa hoàn chỉnh.

Một lựa chọn khác là thiết kế **entity bất biến** (*immutable entity*): các trường được khai báo **final**, đối tượng được khởi tạo đầy đủ qua constructor và không cung cấp setter. Khi cần thay đổi một thuộc tính, ứng dụng tạo một instance mới. Spring Data hỗ trợ kiểu thiết kế này bằng cơ chế **constructor materialization** và **wither method**. Với SDN, wither đặc biệt hữu ích khi Neo4j sinh ID hoặc cập nhật một thuộc tính sau khi entity ban đầu đã được tạo.

Sau bài học, bạn có thể:

- Giải thích cách Spring Data tạo entity bất biến từ dữ liệu đọc được.
- Chọn constructor phù hợp và sử dụng **@PersistenceCreator**.
- Viết wither theo quy ước **with<Property>** để cập nhật thuộc tính mà không sửa instance hiện tại.
- Ánh xạ ID do Neo4j sinh và nhận biết vì sao cần dùng entity được repository trả về.
- Thiết kế collection và relationship sao cho không làm mất tính bất biến của object graph.

## 1. Entity bất biến là gì?

Một đối tượng bất biến có trạng thái không đổi sau khi constructor hoàn tất. Trong Java, cách triển khai phổ biến là:

- Khai báo lớp **final** nếu không cần kế thừa.
- Khai báo các trường trạng thái là **private final**.
- Khởi tạo mọi trường trong constructor.
- Không cung cấp setter có thể thay đổi trạng thái.
- Khi cần một trạng thái mới, trả về một đối tượng mới chứa các giá trị đã cập nhật.

Ví dụ, một **Person** bất biến có thể có ID và tên:

~~~java
public final class Person {

    private final Long id;
    private final String name;

    public Person(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Sau khi tạo **Person**, mã bên ngoài chỉ đọc được ID và tên. Không thể gọi **setName()** để thay đổi trực tiếp instance đó. Điều này làm cho trạng thái đối tượng dễ dự đoán hơn, đặc biệt khi cùng một instance được truyền qua nhiều tầng của ứng dụng.

Tính bất biến cũng giúp phân biệt rõ hai trạng thái: đối tượng ban đầu và đối tượng mới sau một thay đổi. Đổi lại, ứng dụng phải sử dụng instance mới sau mỗi lần cập nhật. Nếu một trường chứa collection, chỉ khai báo trường là **final** là chưa đủ; cần sao chép collection và không để lộ một tham chiếu có thể sửa đổi.

## 2. Spring Data tạo entity bất biến như thế nào?

Khi SDN đọc một node từ Neo4j, Spring Data cần chuyển dữ liệu thuộc tính và relationship thành một object graph Java. Với entity bất biến, framework không thể tạo đối tượng rỗng rồi gọi setter. Thay vào đó, nó chọn một **persistence constructor** và truyền các giá trị đã ánh xạ vào constructor đó.

Quá trình này thường gồm các bước:

1. Đọc metadata của entity, bao gồm label, property, ID và relationship.
2. Chọn constructor dùng để materialize đối tượng.
3. Ghép giá trị trong kết quả Neo4j với các tham số constructor tương ứng.
4. Tạo instance mới bằng constructor.
5. Nếu còn thuộc tính cần được điền sau khi tạo, Spring Data tìm cách cập nhật qua wither hoặc cơ chế truy cập thuộc tính phù hợp.

Với một lớp chỉ có duy nhất một constructor, Spring Data thường có thể chọn constructor đó. Nếu lớp có nhiều constructor, hãy đánh dấu constructor dùng để đọc dữ liệu bằng **@PersistenceCreator**:

~~~java
import org.springframework.data.annotation.PersistenceCreator;

public final class Person {

    private final Long id;
    private final String name;

    public Person(String name) {
        this(null, name);
    }

    @PersistenceCreator
    public Person(Long id, String name) {
        this.id = id;
        this.name = name;
    }
}
~~~

Trong ví dụ, constructor một tham số thuận tiện cho mã nghiệp vụ tạo người mới; constructor có **@PersistenceCreator** được Spring Data dùng để materialize dữ liệu, bao gồm cả ID. Các tham số constructor phải tương ứng với tên property và kiểu dữ liệu mà framework ánh xạ. Hãy giữ tên tham số trùng với tên thuộc tính và bật tùy chọn biên dịch lưu metadata tên tham số (**-parameters**) khi cần để Spring Data khám phá chính xác tên đó.

**@PersistenceCreator** không thay thế việc thiết kế constructor đúng. Nếu constructor thiếu một thuộc tính bắt buộc mà lớp cũng không có setter, wither hoặc cơ chế truy cập thích hợp để điền thuộc tính đó, việc ánh xạ có thể thất bại hoặc tạo ra trạng thái không đầy đủ.

## 3. Wither method: thay đổi bằng cách tạo instance mới

**Wither** là phương thức có tên theo quy ước **with<Property>**, nhận giá trị mới và trả về một instance mới của cùng kiểu. Phương thức không thay đổi instance hiện tại. Ví dụ:

~~~java
public Person withName(String newName) {
    return new Person(this.id, newName);
}
~~~

Nếu gọi:

~~~java
Person original = new Person(10L, "An");
Person renamed = original.withName("Bình");
~~~

**original** vẫn có tên **An**; **renamed** là instance mới có tên **Bình**. Hai đối tượng có thể chia sẻ các giá trị bất biến, nhưng không có thao tác nào sửa trạng thái của **original**.

Quy ước tên rất quan trọng. Với property **id**, Spring Data có thể nhận diện phương thức **withId(Long id)** là wither cho property đó. Với property **version**, phương thức tương ứng sẽ là **withVersion(...)**. Kiểu tham số phải phù hợp với kiểu property và phương thức cần trả về một đối tượng mới có cùng kiểu entity.

Một wither điển hình:

~~~java
public Person withId(Long newId) {
    return new Person(newId, this.name);
}
~~~

Trong trường hợp property được tạo sau khi đối tượng ban đầu đã tồn tại, Spring Data gọi wither và tiếp tục làm việc với instance mà phương thức trả về. Vì vậy, wither phải bảo toàn mọi trường khác; nếu bỏ sót một property, dữ liệu đó có thể bị mất trong instance mới.

## 4. ID do Neo4j sinh và wither withId

Một tình huống phổ biến trong SDN là node mới chưa có ID trước khi lưu. Khi khai báo **@Id** cùng **@GeneratedValue**, SDN yêu cầu Neo4j cung cấp định danh cho node. Với entity bất biến, framework không thể gán ID bằng setter. Hãy cung cấp wither **withId** để nhận ID được sinh:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public final class Person {

    @Id
    @GeneratedValue
    private final Long id;

    private final String name;

    @PersistenceCreator
    public Person(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Person withId(Long newId) {
        return new Person(newId, this.name);
    }

    public Person withName(String newName) {
        return new Person(this.id, newName);
    }
}
~~~

Khi tạo node mới, ứng dụng có thể khởi tạo entity với **id == null**. Sau khi lưu, SDN nhận ID được Neo4j sinh và dùng **withId** để tạo instance mang ID đó. Do đó, hãy giữ lại giá trị trả về từ **save()**:

~~~java
Person candidate = new Person(null, "An");
Person saved = personRepository.save(candidate);

Long generatedId = saved.getId();
~~~

**candidate** vẫn là instance ban đầu với ID **null**; **saved** là instance đại diện cho trạng thái đã được lưu và có ID. Nếu bỏ qua giá trị trả về, mã gọi có thể tiếp tục dùng instance chưa có định danh và đưa ra quyết định sai trong các thao tác tiếp theo.

**@GeneratedValue** trong ví dụ dùng cơ chế sinh ID mặc định của SDN. Nếu hệ thống cần mã nghiệp vụ ổn định để trao đổi với dịch vụ khác, hãy lưu mã đó thành một property riêng và đặt uniqueness constraint phù hợp. Không nên xem ID nội bộ do cơ sở dữ liệu sinh là mã nghiệp vụ công khai.

## 5. Entity bất biến có relationship

Entity trong SDN thường chứa các trường relationship để biểu diễn object graph. Các trường này cũng có thể là **final**. Hãy nhận collection qua constructor, sao chép nó thành collection không thể sửa đổi và dùng wither hoặc phương thức miền để tạo graph mới khi cần.

Ví dụ, một người có thể tham gia nhiều bộ phim:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public final class Person {

    @Id
    @GeneratedValue
    private final Long id;

    private final String name;

    @Relationship(
        type = "ACTED_IN",
        direction = Relationship.Direction.OUTGOING
    )
    private final List<Movie> actedIn;

    @PersistenceCreator
    public Person(Long id, String name, List<Movie> actedIn) {
        this.id = id;
        this.name = Objects.requireNonNull(name);
        this.actedIn = actedIn == null
            ? List.of()
            : List.copyOf(actedIn);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<Movie> getActedIn() {
        return actedIn;
    }

    public Person withId(Long newId) {
        return new Person(newId, name, actedIn);
    }

    public Person withMovie(Movie movie) {
        List<Movie> updated = new ArrayList<>(actedIn);
        updated.add(Objects.requireNonNull(movie));
        return new Person(id, name, updated);
    }
}
~~~

**List.copyOf** tạo bản sao không thể sửa đổi của collection đầu vào. Phương thức **withMovie** tạo một danh sách mới, thêm phim rồi trả về một **Person** mới. Không có thay đổi nào tác động đến danh sách hoặc entity ban đầu.

Node đích cũng cần được mô hình hóa thành entity SDN:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public final class Movie {

    @Id
    @GeneratedValue
    private final Long id;

    private final String title;

    @PersistenceCreator
    public Movie(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Movie withId(Long newId) {
        return new Movie(newId, title);
    }
}
~~~

Khi SDN materialize **Person**, constructor nhận danh sách **actedIn** đã được ánh xạ. Khi lưu graph, ID của node mới có thể được sinh trong quá trình ghi; mỗi entity bất biến có ID được sinh cần có cách tạo instance mới tương ứng, như **withId**. Đối với relationship có property riêng, hãy áp dụng cùng nguyên tắc: constructor nhận các property cần thiết và wither xử lý định danh relationship nếu mapping cần framework gán định danh đó.

## 6. Phối hợp constructor và wither

Constructor và wither giải quyết hai thời điểm khác nhau trong vòng đời object:

| Cơ chế | Vai trò |
|---|---|
| Constructor được chọn để persistence | Tạo entity từ các property và relationship đã đọc |
| **@PersistenceCreator** | Chỉ rõ constructor dùng để materialize khi có nhiều constructor |
| **withId(...)** | Tạo instance mới sau khi Neo4j sinh ID |
| **withVersion(...)** | Tạo instance mới khi framework cập nhật property phiên bản, nếu entity dùng optimistic locking |
| **withName(...)** hoặc wither miền khác | Tạo trạng thái mới theo yêu cầu nghiệp vụ |

Hãy đưa các property đã biết vào constructor persistence. Chỉ dựa vào wither cho những property cần được điền hoặc cập nhật sau khi constructor đã chạy. Cách này làm rõ nguồn dữ liệu của từng trường và giảm số lần tạo object không cần thiết.

Nếu entity có **@Version**, property version cũng phải được ánh xạ theo kiểu dữ liệu phù hợp với SDN. Với entity bất biến, cung cấp một wither tương ứng nếu phiên bản được framework cập nhật sau khi tạo instance. Không tự tăng version trong mã nghiệp vụ; version được dùng để kiểm soát optimistic locking và phát hiện cập nhật cạnh tranh.

Một lưu ý quan trọng là wither không phải setter. Phương thức **withId** phải trả về instance mới; nếu nó sửa field bằng reflection hoặc trả về **this** trong khi giá trị cần đổi, thiết kế bất biến không còn đúng và framework không nhận được object mới như mong đợi.

## 7. Những lỗi thường gặp

**Thiếu constructor phù hợp.** Spring Data không tìm được constructor có thể nhận các property cần ánh xạ. Hãy kiểm tra tên tham số, kiểu dữ liệu và **@PersistenceCreator** khi có nhiều constructor.

**Không có wither cho ID được sinh.** Entity có **@Id @GeneratedValue** nhưng chỉ có trường **final** và không có **withId**. SDN không thể cập nhật định danh vào một instance bất biến. Hãy bổ sung wither đúng quy ước.

**Wither làm mất thuộc tính khác.** **withId** chỉ truyền ID mới và bỏ quên **name** hoặc relationship. Mỗi wither phải dựng lại đối tượng với toàn bộ trạng thái cần giữ.

**Tiếp tục dùng instance trước khi lưu.** Mã gọi bỏ qua đối tượng được **repository.save()** trả về. Với entity bất biến, hãy gán kết quả trả về vào biến mới hoặc thay thế tham chiếu đang quản lý.

**Collection vẫn có thể bị sửa đổi.** Trường **final List<Movie>** chỉ ngăn thay thế tham chiếu; nó không ngăn thêm hoặc xóa phần tử. Hãy dùng bản sao không thể sửa đổi như **List.copyOf** và không trả về collection mutable.

**Dùng wither như một setter.** Không đặt logic sửa trạng thái tại chỗ trong wither. Hãy tạo instance mới và giữ nguyên đối tượng ban đầu.

**Không lưu lại entity mới sau khi cập nhật.** Các phương thức miền như **withMovie** trả về object mới. Nếu không nhận kết quả, thay đổi không xuất hiện trong graph được gửi tới repository.

## 8. Tự kiểm tra

1. Vì sao constructor materialization phù hợp với entity có các trường **final**?
2. Khi nào cần đánh dấu constructor bằng **@PersistenceCreator**?
3. Vì sao entity có **@Id @GeneratedValue** nên cung cấp **withId** nếu ID là trường bất biến?
4. Sau khi gọi **repository.save(candidate)**, vì sao cần dùng instance được trả về?
5. Vì sao khai báo collection là **final** chưa đủ để bảo đảm tính bất biến?

**Bài tập thực hành:** Thiết kế entity bất biến **Author** có ID được Neo4j sinh, tên tác giả và danh sách **Book** mà tác giả viết. Tạo constructor persistence nhận đủ các thuộc tính, thêm **withId** để nhận ID sinh ra và **withBook** để trả về một **Author** mới có danh sách sách đã cập nhật. Viết repository lưu tác giả mới, sau đó dùng instance trả về để đọc ID. Kiểm tra rằng entity ban đầu vẫn giữ ID **null** và danh sách sách cũ không thay đổi.
