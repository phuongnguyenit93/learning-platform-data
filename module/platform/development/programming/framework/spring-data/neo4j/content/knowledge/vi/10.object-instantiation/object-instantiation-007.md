# equals, hashCode, toString và nguy cơ đệ quy qua relationship

Entity trong Spring Data Neo4j thường chứa cả thuộc tính của node và các relationship tới entity khác. Khi Java tạo `equals()`, `hashCode()` hoặc `toString()` bằng cách xét tất cả field, những phương thức tưởng như đơn giản có thể đi qua cả đồ thị đối tượng. Nếu các relationship tạo thành chu trình, lời gọi có thể lặp vô hạn, gây `StackOverflowError`, hoặc làm thao tác trong `HashSet` và `HashMap` cho kết quả khó đoán.

Với mô hình đồ thị, một `Person` có thể tham gia nhiều `Movie`, còn mỗi `Movie` lại tham chiếu tới nhiều `Person`. Vì vậy, cần định nghĩa rõ danh tính của entity và kiểm soát field nào được dùng trong các phương thức của Java. Bài học này giải thích cách thiết kế `equals`, `hashCode`, `toString`, cách dùng Lombok an toàn và cách kiểm tra các chu trình relationship.

## 1. Vì sao entity đồ thị dễ gặp vấn đề?

Giả sử mô hình Java có hai lớp tham chiếu lẫn nhau:

```java
public class Person {
    private String code;
    private Set<Movie> movies;
}

public class Movie {
    private String code;
    private Set<Person> cast;
}
```

Một đối tượng `Person` giữ tập `Movie`; mỗi `Movie` trong tập lại giữ `Person` đó trong `cast`. Đây là một chu trình:

```text
Person -> Movie -> Person -> Movie -> ...
```

Nếu `Person.toString()` in toàn bộ `movies`, còn `Movie.toString()` in toàn bộ `cast`, lời gọi `toString()` sẽ quay lại đối tượng ban đầu và tiếp tục mãi. `equals()` hoặc `hashCode()` được sinh tự động từ tất cả field cũng có thể đi theo chu trình tương tự.

Đồ thị trong Neo4j vốn có thể chứa chu trình; điều đó hoàn toàn bình thường. Vấn đề xuất hiện khi mô hình Java duyệt đệ quy toàn bộ relationship mà không giới hạn phạm vi. Một entity thường chỉ cần biểu diễn danh tính và trạng thái của node; không nhất thiết mọi relationship phải tham gia so sánh hoặc biểu diễn chuỗi.

## 2. Vai trò của ba phương thức

| Phương thức | Mục đích | Rủi ro khi đưa toàn bộ relationship vào |
|---|---|---|
| `equals(Object)` | Xác định hai đối tượng có được xem là bằng nhau hay không | Duyệt sâu qua graph, đệ quy hoặc so sánh quá nhiều dữ liệu |
| `hashCode()` | Tạo mã băm để dùng trong `HashSet`, `HashMap` và cấu trúc tương tự | Đệ quy; mã băm thay đổi khi thuộc tính hoặc relationship thay đổi |
| `toString()` | Tạo chuỗi phục vụ log, debug và hiển thị | In cả graph, gây đệ quy, log quá lớn hoặc lộ dữ liệu không cần thiết |

Ba phương thức có mục đích khác nhau nên không nên dùng chung một danh sách field một cách máy móc. `equals` và `hashCode` phải tuân thủ hợp đồng của Java. `toString` nên ngắn gọn, tập trung vào các thuộc tính hữu ích khi debug.

## 3. Hợp đồng equals và hashCode của Java

Nếu hai đối tượng được xem là bằng nhau theo `equals`, chúng bắt buộc phải có cùng `hashCode`. Chiều ngược lại không bắt buộc: hai đối tượng khác nhau vẫn có thể có cùng mã băm.

Một số quy tắc quan trọng của `equals`:

- Phản xạ: `x.equals(x)` phải là `true`.
- Đối xứng: nếu `x.equals(y)` là `true`, thì `y.equals(x)` cũng phải là `true`.
- Bắc cầu: nếu `x.equals(y)` và `y.equals(z)` là `true`, thì `x.equals(z)` phải là `true`.
- Nhất quán: kết quả không thay đổi giữa các lần gọi nếu dữ liệu dùng để so sánh không đổi.
- So sánh với `null` phải trả về `false`.

`hashCode()` cũng phải nhất quán khi dữ liệu dùng để tính mã băm không đổi. Đặc biệt, nếu một đối tượng đã được thêm vào `HashSet` hoặc được dùng làm key trong `HashMap`, không được để `hashCode()` thay đổi trong thời gian nó đang nằm trong cấu trúc đó. Nếu mã băm thay đổi, collection có thể không tìm lại được phần tử ở bucket cũ.

## 4. Chọn danh tính entity trước khi viết equals

Trước khi triển khai `equals` và `hashCode`, hãy quyết định điều gì làm cho một node đại diện cho cùng một thực thể.

### Dùng khóa nghiệp vụ bất biến

Nếu miền dữ liệu có một mã duy nhất và không đổi trong suốt vòng đời thực thể, có thể dùng mã đó làm khóa so sánh. Ví dụ `personCode` được ứng dụng cấp, không thay đổi sau khi tạo và có unique constraint trong Neo4j.

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

@Node("Person")
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    private final String personCode;
    private String name;

    @Relationship(type = "ACTED_IN", direction = Relationship.Direction.OUTGOING)
    private Set<ActingCredit> actingCredits = new HashSet<>();

    public Person(String personCode) {
        this.personCode = Objects.requireNonNull(personCode);
    }

    // equals và hashCode dựa trên personCode.
}
```

Trong cách này, hai object `Person` có cùng `personCode` được xem là đại diện cho cùng một người, kể cả khi chúng được tải trong hai lần truy vấn khác nhau. `personCode` phải thực sự duy nhất trong phạm vi áp dụng. Nếu mã chỉ duy nhất theo tenant hoặc hệ thống nguồn, khóa so sánh phải bao gồm namespace tương ứng.

Không dùng `name`, `email` hoặc một thuộc tính có thể đổi làm khóa so sánh. Khi thuộc tính đó thay đổi, hai object có thể đổi trạng thái bằng nhau và `hashCode` có thể thay đổi trong khi object đang nằm trong `HashSet`.

### Dùng ID do Neo4j sinh

Một lựa chọn khác là so sánh theo ID được sinh khi entity đã lưu. Tuy nhiên, ID của entity mới thường là `null` trước khi persistence hoàn tất. Nếu hai entity mới đều có `id == null`, cách viết đơn giản `Objects.equals(id, other.id)` sẽ khiến chúng bị xem là bằng nhau dù chúng là hai thực thể chưa lưu khác nhau.

Ngoài ra, nếu `hashCode()` dựa trên ID, giá trị mã băm sẽ thay đổi sau khi Neo4j gán ID. Đối tượng đã được thêm vào `HashSet` trước khi lưu có thể không còn được tìm thấy sau khi lưu.

Vì vậy, khóa nghiệp vụ bất biến thường dễ quản lý hơn nếu ứng dụng có sẵn khóa đó. Nếu buộc phải dùng ID sinh tự động, hãy thiết kế rõ hành vi của entity trước và sau khi lưu, tránh đưa entity chưa lưu vào cấu trúc dựa trên hash trong khi ID còn thay đổi.

## 5. Triển khai equals và hashCode bằng khóa bất biến

Ví dụ dưới đây dùng `personCode` làm danh tính. Phần relationship được loại khỏi cả hai phương thức:

```java
import java.util.Objects;
import java.util.Set;
import java.util.HashSet;

public class Person {
    private final String personCode;
    private String name;
    private Set<ActingCredit> actingCredits = new HashSet<>();

    public Person(String personCode, String name) {
        this.personCode = Objects.requireNonNull(personCode);
        this.name = name;
    }

    public String getPersonCode() {
        return personCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (other == null || getClass() != other.getClass()) return false;
        Person person = (Person) other;
        return personCode.equals(person.personCode);
    }

    @Override
    public int hashCode() {
        return personCode.hashCode();
    }
}
```

Đây là phần cốt lõi của một entity minh họa; khi dùng với SDN, bổ sung annotation `@Node`, `@Id`, các constructor và accessor theo mapping của dự án. Ví dụ dùng phép kiểm tra lớp chính xác trước khi ép kiểu để tránh so sánh không đối xứng nếu có lớp con định nghĩa thêm danh tính riêng.

`personCode` là `final`, nên không thể bị thay đổi sau khi tạo object. Cả `equals` và `hashCode` chỉ dựa trên cùng một khóa. Việc thêm hoặc xóa relationship, đổi `name` không làm thay đổi danh tính hoặc mã băm của `Person`.

Nếu dùng Lombok, có thể khai báo rõ field tham gia so sánh:

```java
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

@Getter
@Setter
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
public class Person {
    @EqualsAndHashCode.Include
    private final String personCode;

    private String name;

    private Set<ActingCredit> actingCredits = new HashSet<>();

    public Person(String personCode) {
        this.personCode = Objects.requireNonNull(personCode);
    }
}
```

Với `onlyExplicitlyIncluded = true`, chỉ field có `@EqualsAndHashCode.Include` tham gia. Cách này giảm nguy cơ relationship hoặc field có thể thay đổi bị đưa nhầm vào phép so sánh. Hãy xác nhận khóa được chọn thực sự bất biến và duy nhất.

## 6. Khi dùng ID sinh tự động: xử lý entity chưa lưu

Nếu không có khóa nghiệp vụ thích hợp và cần so sánh entity theo ID do Neo4j cấp, phải xử lý trường hợp ID chưa được gán. Một mẫu thường dùng là chỉ xem hai object khác instance là bằng nhau khi ID đã có giá trị, đồng thời giữ `hashCode` ổn định theo lớp:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (other == null || getClass() != other.getClass()) return false;

    Person person = (Person) other;
    return id != null && id.equals(person.id);
}

@Override
public int hashCode() {
    return getClass().hashCode();
}
```

Với cách này, hai entity chưa lưu có ID `null` không bị xem là bằng nhau trừ khi chúng là cùng một instance. Sau khi ID được gán, các entity cùng ID sẽ bằng nhau. `hashCode` không thay đổi trong quá trình lưu, nhưng nhiều instance cùng lớp sẽ có cùng mã băm, làm tăng va chạm trong hash collection. Đây là một đánh đổi cần hiểu rõ, không phải giải pháp mặc định cho mọi mô hình.

Ngoài ra, kết quả `equals` có thể thay đổi khi ID chuyển từ `null` sang giá trị được sinh. Vì vậy, tránh đưa entity chưa lưu vào `HashSet` hoặc dùng làm key `HashMap` trước khi persistence hoàn tất. Nếu collection cần chứa entity trước khi lưu, khóa nghiệp vụ bất biến thường phù hợp hơn.

## 7. Không đưa relationship vào equals và hashCode

Xét ví dụ `Person` có `actingCredits`, mỗi `ActingCredit` lại trỏ tới `Movie`, còn `Movie` có thể chứa danh sách `Person` hoặc các relationship quay lại người ban đầu. Nếu `equals` hoặc `hashCode` duyệt các field này, thao tác so sánh một người có thể đi qua gần như toàn bộ graph.

Những vấn đề có thể xảy ra:

- `StackOverflowError` do chu trình tham chiếu.
- So sánh hoặc tính hash chậm khi graph lớn.
- Kết quả bằng nhau thay đổi khi thêm/xóa relationship.
- `HashSet` không tìm thấy phần tử sau khi các field tham gia hash thay đổi.
- Hai entity đại diện cùng node có thể bị xem là khác nhau chỉ vì một tập relationship được tải khác nhau.

Giữ `equals` và `hashCode` tập trung vào danh tính node. Nếu một nghiệp vụ cần so sánh hai tập quan hệ, hãy viết hàm riêng cho nghiệp vụ đó, giới hạn rõ loại relationship và thuộc tính cần so sánh. Không biến phép so sánh danh tính entity thành phép so sánh toàn bộ graph.

## 8. Thiết kế toString không đi qua graph

`toString()` chủ yếu phục vụ debug và log. Một chuỗi ngắn chứa ID, mã nghiệp vụ và một vài thuộc tính mô tả thường đủ hữu ích.

```java
@Override
public String toString() {
    return "Person{" +
        "personCode='" + personCode + '\'' +
        ", name='" + name + '\'' +
        '}';
}
```

Không in `actingCredits`, `movies` hoặc object relationship lồng nhau. Nếu cần biết số quan hệ để debug, có thể in số lượng thay vì in toàn bộ graph:

```java
@Override
public String toString() {
    return "Person{" +
        "personCode='" + personCode + '\'' +
        ", name='" + name + '\'' +
        ", actingCreditCount=" + actingCredits.size() +
        '}';
}
```

Ngay cả việc gọi `actingCredits.size()` cũng chỉ nên làm khi collection đã được khởi tạo và việc truy cập nó an toàn trong ngữ cảnh hiện tại. Với entity có graph lớn, có thể bỏ hẳn số lượng để giữ `toString` rẻ và dự đoán được.

Chỉ đưa vào `toString` những thuộc tính được phép xuất hiện trong log. Không in mật khẩu, token, dữ liệu cá nhân nhạy cảm hoặc thông tin mà người đọc log không cần để chẩn đoán.

## 9. Dùng Lombok an toàn với entity SDN

`@Data` của Lombok tổng hợp getter, setter, `equals`, `hashCode` và `toString`. Mặc định, `equals`, `hashCode` và `toString` xét nhiều field của lớp, bao gồm cả relationship. Trên entity đồ thị, điều này dễ gây đệ quy và so sánh graph ngoài ý muốn.

Ví dụ cần tránh:

```java
@Data
@Node("Person")
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    private final String personCode;

    @Relationship(type = "ACTED_IN")
    private Set<ActingCredit> actingCredits = new HashSet<>();
}
```

Thay vào đó, khai báo rõ những hành vi cần sinh:

```java
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

@Getter
@Setter
@ToString(onlyExplicitlyIncluded = true)
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
@Node("Person")
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    @EqualsAndHashCode.Include
    @ToString.Include
    private final String personCode;

    @ToString.Include
    private String name;

    @Relationship(type = "ACTED_IN")
    private Set<ActingCredit> actingCredits = new HashSet<>();

    public Person(String personCode) {
        this.personCode = Objects.requireNonNull(personCode);
    }
}
```

Ví dụ này giả định `personCode` là khóa bất biến, duy nhất và được gán ngay khi tạo entity. Relationship không có `@EqualsAndHashCode.Include` hoặc `@ToString.Include`, nên bị loại khỏi các phương thức được Lombok sinh. Nếu khóa của entity là ID sinh sau khi lưu, hãy áp dụng chiến lược riêng ở phần trước thay vì mặc định include một ID có thể đang `null`.

Một cách khác là giữ `@Data` nhưng gắn `@EqualsAndHashCode.Exclude` và `@ToString.Exclude` trên mọi relationship. Tuy nhiên, cách khai báo rõ getter/setter và chỉ include field cần thiết thường dễ kiểm soát hơn khi entity có nhiều quan hệ.

## 10. Kiểm tra nguy cơ đệ quy và hash collection

Tạo một graph nhỏ trong bộ nhớ hoặc từ dữ liệu thử nghiệm:

Đoạn kiểm tra giả định các lớp thử nghiệm có phương thức `addMovie` và `addActor` để nối hai object; các phương thức này chỉ minh họa việc tạo chu trình tham chiếu trong bộ nhớ.

```java
Person person = new Person("PER-001", "An");
Movie movie = new Movie("MOV-001", "Example");

person.addMovie(movie);
movie.addActor(person);

System.out.println(person);
System.out.println(person.hashCode());
```

Nếu `toString` hoặc `hashCode` đi qua relationship theo cả hai chiều, lời gọi có thể quay lại object ban đầu. Sau khi sửa phương thức để chỉ dùng khóa node, các lời gọi này không còn phụ thuộc vào cấu trúc graph.

Kiểm tra tính ổn định của hash khi thêm relationship:

```java
Set<Person> people = new HashSet<>();
Person person = new Person("PER-001", "An");

people.add(person);
int hashBefore = person.hashCode();

person.addMovie(new Movie("MOV-001", "Example"));

int hashAfter = person.hashCode();
boolean stillFound = people.contains(person);
```

Với khóa bất biến, `hashBefore` và `hashAfter` bằng nhau, đồng thời `stillFound` là `true`. Bài kiểm tra này giúp phát hiện việc vô tình đưa relationship hoặc field có thể thay đổi vào `hashCode`.

## 11. Quy tắc thực hành

1. Xác định danh tính entity trước khi viết `equals` và `hashCode`.
2. Ưu tiên khóa nghiệp vụ bất biến, duy nhất và được cấp ngay khi tạo nếu miền dữ liệu có khóa phù hợp.
3. Nếu dùng ID sinh tự động, xử lý riêng entity chưa lưu và giữ `hashCode` ổn định trong vòng đời collection.
4. Không đưa relationship hoặc collection mutable vào `equals` và `hashCode`.
5. Chỉ in ID, khóa nghiệp vụ và một vài thuộc tính ngắn gọn trong `toString`.
6. Tránh dùng `@Data` trên entity SDN nếu không kiểm soát các phương thức được sinh.
7. Với Lombok, dùng `onlyExplicitlyIncluded = true` và đánh dấu rõ field cần thiết.
8. Kiểm tra `HashSet`/`HashMap` sau khi entity được lưu và sau khi relationship thay đổi.

## 12. Tự kiểm tra

1. Vì sao hai entity `Person` có cùng dữ liệu relationship nhưng được tải trong hai lần khác nhau vẫn có thể đại diện cho cùng một node?
2. Hợp đồng nào yêu cầu hai object bằng nhau phải có cùng `hashCode`?
3. Vì sao dùng ID sinh tự động trong `hashCode` có thể làm `HashSet` không tìm thấy entity sau khi lưu?
4. Chu trình `Person -> Movie -> Person` ảnh hưởng thế nào tới `toString()` được sinh tự động?
5. Vì sao `@Data` có thể không phù hợp với entity SDN có nhiều relationship?
6. `@EqualsAndHashCode(onlyExplicitlyIncluded = true)` giúp kiểm soát những field nào?
7. Khi cần debug số lượng relationship, vì sao in `actingCredits.size()` an toàn hơn in toàn bộ collection, và khi nào vẫn nên bỏ cả số lượng?
