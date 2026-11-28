# Tên tham số constructor và tùy chọn biên dịch -parameters

## Mục tiêu bài học

Spring Data Neo4j (SDN) có thể tạo object entity bằng cách gọi constructor. Để truyền đúng giá trị vào từng tham số, Spring Data cần biết tham số đó tương ứng với property nào của entity. Với class Java thông thường, tên tham số có thể không được giữ trong bytecode nếu dự án không bật tùy chọn biên dịch `-parameters`.

Bài học này giải thích cách constructor binding hoạt động, vì sao tên tham số cần khớp với tên property, cách bật `-parameters` trong Maven và Gradle, và cách kiểm tra metadata sau khi biên dịch. Bạn cũng sẽ biết khi nào cần `@PersistenceCreator`, `@ConstructorProperties` hoặc constructor của Java record.

## 1. Vì sao SDN cần tên tham số constructor?

Khi SDN đọc một node Neo4j và ánh xạ thành entity Java, framework phải tạo một object rồi gán các giá trị property. Với entity có constructor nhận tham số, Spring Data dùng thông tin về constructor để xác định giá trị nào được truyền vào từng tham số.

Ví dụ node có các property `id`, `name` và `age`. Entity Java tương ứng:

```java
@Node("Person")
public class Person {

    @Id
    private final String id;

    private final String name;

    private final int age;

    public Person(String id, String name, int age) {
        this.id = id;
        this.name = name;
        this.age = age;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }
}
```

Khi đọc node, SDN cần biết:

| Tham số constructor | Property của entity | Giá trị lấy từ node |
|---|---|---|
| `id` | `id` | Mã định danh |
| `name` | `name` | Tên người |
| `age` | `age` | Tuổi |

Spring Data ánh xạ tham số constructor theo tên property. Do đó, tên tham số cần tương ứng với tên property mà Spring Data nhận diện trong entity. Nếu tên tham số không thể được khám phá, framework có thể không xác định được giá trị nào cần truyền vào tham số đó và quá trình ánh xạ có thể thất bại.

Điều này đặc biệt quan trọng với entity bất biến (immutable entity), nơi các trường thường là `final` và chỉ được gán trong constructor. Framework không thể dựa vào setter để hoàn thiện object sau khi tạo.

## 2. Tên tham số trong bytecode Java

Tên tham số bạn viết trong mã nguồn không phải lúc nào cũng có sẵn khi ứng dụng chạy. Mặc định, trình biên dịch Java có thể không lưu tên tham số constructor vào metadata mà reflection đọc được. Khi đó, lời gọi reflection như `Parameter.getName()` có thể trả về tên tổng quát như `arg0`, `arg1`.

Tùy chọn `-parameters` yêu cầu `javac` ghi tên tham số vào class file. Nhờ vậy, reflection và các framework như Spring Data có thể khám phá đúng tên đã khai báo trong mã nguồn.

Ví dụ, khi biên dịch class bằng:

```bash
javac -parameters Person.java
```

metadata của constructor sẽ giữ các tên `id`, `name` và `age`. Nếu bỏ tùy chọn này, tên có thể không còn khả dụng qua Java reflection, trừ khi framework tìm được tên từ một nguồn metadata khác được hỗ trợ.

Lưu ý rằng `-parameters` là tùy chọn của trình biên dịch, không phải tham số JVM lúc chạy. Thêm nó vào lệnh `java` hoặc cấu hình VM của ứng dụng không thể khôi phục tên đã bị loại khỏi class file. Khi thay đổi cấu hình biên dịch, cần biên dịch lại các class chứa constructor được Spring Data ánh xạ.

## 3. Bật -parameters với Maven

Với dự án Maven, cấu hình `maven-compiler-plugin` để lưu tên tham số trong bytecode:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Có thể đặt cấu hình này trong `pom.xml` ở cấp module chứa entity hoặc trong cấu hình build dùng chung để các module Java liên quan đều nhận được tùy chọn. Nếu entity nằm trong một thư viện nội bộ được biên dịch riêng, cần bảo đảm module thư viện đó cũng lưu tên tham số.

Sau khi thay đổi cấu hình, chạy build lại để tạo class file mới. Chỉ sửa `pom.xml` mà vẫn chạy các class cũ trong thư mục output sẽ không làm metadata tự cập nhật.

Nếu dự án đã quản lý phiên bản plugin và các thuộc tính compiler ở parent POM, hãy đặt cấu hình trong đúng phần build kế thừa thay vì tạo thêm một khai báo plugin xung đột.

## 4. Bật -parameters với Gradle

Với Gradle Groovy DSL, cấu hình các task biên dịch Java:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}
```

Với Gradle Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
```

Cấu hình trên áp dụng cho các task `JavaCompile` trong project hiện tại. Trong multi-project build, nếu entity nằm ở subproject khác, hãy đặt cấu hình ở subproject đó hoặc cấu hình dùng chung tại root project để bảo đảm task biên dịch tương ứng nhận được tùy chọn.

Sau khi chỉnh build script, chạy lại task biên dịch hoặc build của module chứa entity. Ví dụ:

```bash
./gradlew clean compileJava
```

Trên Windows có thể dùng `gradlew.bat clean compileJava`. Với Maven, có thể dùng `mvn clean compile`. Lệnh clean giúp loại bỏ class file cũ để kết quả kiểm tra phản ánh đúng cấu hình mới.

## 5. Tên tham số phải khớp property Java

Giả sử tên property trong Java là `fullName`, nhưng tên property lưu trong Neo4j là `full_name`. Có thể dùng `@Property` để đổi tên lưu trữ:

```java
@Node("Person")
public class Person {

    @Id
    private final String id;

    @Property("full_name")
    private final String fullName;

    @PersistenceCreator
    public Person(String id, String fullName) {
        this.id = id;
        this.fullName = fullName;
    }

    public String getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }
}
```

Trong trường hợp này, tham số constructor nên tên là `fullName`, tương ứng với property Java `fullName`. `@Property("full_name")` quy định tên property trong graph. Nó không làm tên tham số constructor đổi thành `full_name`.

Vì vậy, cần phân biệt ba tên có thể xuất hiện:

- Tên tham số constructor, ví dụ `fullName`.
- Tên persistent property của entity Java, ví dụ `fullName`.
- Tên property trong Neo4j, ví dụ `full_name`.

Thông thường, tên tham số constructor khớp với persistent property Java; annotation mapping quyết định tên lưu trữ trong graph.

## 6. Chọn constructor khi entity có nhiều constructor

Nếu entity chỉ có một constructor, Spring Data thường có thể chọn constructor đó để tạo object. Khi class có nhiều constructor, hãy đánh dấu constructor mà framework cần dùng bằng `@PersistenceCreator`:

```java
@Node("Person")
public class Person {

    @Id
    private final String id;

    private final String name;

    private final int age;

    public Person(String id, String name) {
        this(id, name, 0);
    }

    @PersistenceCreator
    public Person(String id, String name, int age) {
        this.id = id;
        this.name = name;
        this.age = age;
    }

    // Getter được lược bỏ.
}
```

Import annotation:

```java
import org.springframework.data.annotation.PersistenceCreator;
```

Constructor được đánh dấu là constructor mà Spring Data ưu tiên dùng cho persistence mapping. Các tham số của constructor này vẫn cần có tên mà framework có thể khám phá và khớp với property tương ứng. `@PersistenceCreator` giải quyết việc **chọn constructor**; nó không tự ghi hoặc cung cấp tên tham số.

Nếu class cần chỉ rõ tên tham số mà không phụ thuộc vào metadata do `-parameters` tạo ra, Java cung cấp annotation `@ConstructorProperties`:

```java
import java.beans.ConstructorProperties;

@ConstructorProperties({"id", "name", "age"})
public Person(String id, String name, int age) {
    this.id = id;
    this.name = name;
    this.age = age;
}
```

Danh sách tên trong `@ConstructorProperties` phải theo đúng thứ tự tham số constructor và khớp với property Java. Annotation này là metadata tường minh cho constructor; nó không thay thế việc chọn constructor khi class có nhiều lựa chọn. Trong dự án Java thông thường, bật `-parameters` thường là cách cấu hình đơn giản và nhất quán hơn.

## 7. Java record và constructor binding

Java record giữ tên component trong metadata của record. Spring Data có thể dùng canonical constructor để tạo record mà không cần khai báo thêm constructor khác:

```java
@Node("Person")
public record Person(
        @Id String id,
        String name,
        int age
) {
}
```

Các component `id`, `name` và `age` vừa xác định trạng thái của record, vừa là tham số của canonical constructor. Vì vậy, tên component có thể được sử dụng cho constructor binding. Với class Java thông thường, hãy cấu hình `-parameters` hoặc cung cấp metadata tên tham số phù hợp.

Record phù hợp với mô hình bất biến và dữ liệu có cấu trúc rõ ràng. Khi entity cần hành vi thay đổi trạng thái, collection relationship có thể cập nhật hoặc quy tắc khởi tạo phức tạp, class thông thường có constructor tường minh có thể phù hợp hơn. Dù dùng record hay class, kiểu dữ liệu và tên property vẫn cần khớp với mapping của SDN.

## 8. Kiểm tra metadata constructor

Có thể kiểm tra tên tham số bằng Java reflection để xác nhận class file đã lưu metadata:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ConstructorMetadataCheck {

    public static void main(String[] args) throws Exception {
        Constructor<Person> constructor =
                Person.class.getDeclaredConstructor(
                        String.class, String.class, int.class);

        for (Parameter parameter : constructor.getParameters()) {
            System.out.println(
                    parameter.getName() + ": " + parameter.isNamePresent());
        }
    }
}
```

Khi class được biên dịch với `-parameters`, kết quả mong đợi là các tên tham số thật cùng trạng thái `true`, ví dụ:

```text
id: true
name: true
age: true
```

Nếu kết quả hiện `arg0: false`, `arg1: false`..., hãy kiểm tra:

1. Cấu hình compiler có áp dụng cho module biên dịch entity hay không.
2. IDE có dùng cấu hình build riêng và bỏ qua Maven/Gradle hay không.
3. Class file đang chạy có phải class file vừa được biên dịch lại hay không.
4. Constructor được kiểm tra có đúng là constructor mà Spring Data chọn hay không.
5. Nếu dùng `@ConstructorProperties`, danh sách tên có đúng thứ tự và đúng property hay không.

Có thể dùng `javap -v` trên class file để xem metadata `MethodParameters`. Ví dụ:

```bash
javap -v target/classes/com/example/Person.class
```

Tìm phần mô tả constructor và mục `MethodParameters`. Với Gradle, đường dẫn class thường nằm trong `build/classes/java/main`; với Maven, thường nằm trong `target/classes`.

## 9. Kiểm thử ánh xạ entity với Neo4j

Kiểm tra reflection xác nhận metadata của class, nhưng chưa chứng minh toàn bộ quá trình mapping hoạt động. Nên có integration test đọc node qua repository để xác nhận Spring Data tạo được entity với các giá trị đúng:

```java
@DataNeo4jTest
class PersonRepositoryTest {

    @Autowired
    private PersonRepository personRepository;

    @Test
    void shouldInstantiatePersonFromNodeProperties() {
        // Tạo node Person có id, name và age trong Neo4j.
        // Đọc lại qua personRepository.findById(...).
        // Xác nhận các property được truyền đúng vào constructor.
    }
}
```

Phần thiết lập dữ liệu có thể dùng Neo4j Testcontainer, test database hoặc cơ chế test phù hợp với dự án. Điều quan trọng là bài kiểm thử phải đi qua repository mapping thực tế thay vì chỉ gọi constructor trực tiếp.

Khi kiểm thử thất bại, hãy đọc nguyên nhân theo thứ tự: constructor nào được chọn, tham số có tên được khám phá không, tên đó có khớp persistent property không, và kiểu dữ liệu từ Neo4j có thể chuyển đổi sang kiểu tham số không. Lỗi chuyển đổi kiểu là vấn đề khác với lỗi thiếu tên tham số.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tham số reflection có tên `arg0`, `arg1` | Class được biên dịch mà không lưu tên tham số | Bật `-parameters` và biên dịch lại |
| Không tạo được entity bất biến | Spring Data không xác định được tham số constructor tương ứng với property | Kiểm tra tên tham số và persistent property |
| Framework chọn nhầm constructor | Entity có nhiều constructor nhưng chưa đánh dấu constructor persistence | Dùng `@PersistenceCreator` cho constructor phù hợp |
| Đổi tên property graph rồi đổi luôn tên tham số | Nhầm tên property lưu trong Neo4j với tên property Java | Giữ tham số theo tên property Java; dùng `@Property` cho tên lưu trữ |
| Đã thêm `@PersistenceCreator` nhưng vẫn lỗi tên tham số | Annotation chỉ chọn constructor | Bật `-parameters` hoặc cung cấp `@ConstructorProperties` |
| Build đã cấu hình nhưng runtime vẫn báo thiếu tên | Ứng dụng đang dùng class file cũ hoặc IDE có cấu hình biên dịch riêng | Clean và build lại đúng module, kiểm tra `isNamePresent()` |
| Constructor nhận sai kiểu dữ liệu | Giá trị property không chuyển đổi được sang kiểu tham số | Kiểm tra kiểu property, converter và kiểu tham số |

## 11. Tự kiểm tra

1. Vì sao Spring Data cần tên tham số constructor khi tạo entity?
2. Tùy chọn `-parameters` thay đổi metadata nào trong class file?
3. Với Maven, cần đặt cấu hình compiler nào để giữ tên tham số?
4. Với Gradle, task `JavaCompile` được cấu hình ra sao?
5. `@PersistenceCreator` giải quyết vấn đề gì và không giải quyết vấn đề gì?
6. Nếu Java property là `fullName` nhưng Neo4j lưu thành `full_name`, tham số constructor nên có tên nào?
7. Có thể dùng reflection để kiểm tra tên tham số đã được lưu hay chưa bằng cách nào?
8. Vì sao cần integration test qua repository ngoài việc kiểm tra metadata?

Hãy tạo một entity `Person` có constructor nhận `id`, `name` và `age`. Tắt `-parameters`, kiểm tra metadata bằng reflection, sau đó bật tùy chọn này và biên dịch lại. Cuối cùng đọc node qua repository để xác nhận constructor binding hoạt động đúng.
