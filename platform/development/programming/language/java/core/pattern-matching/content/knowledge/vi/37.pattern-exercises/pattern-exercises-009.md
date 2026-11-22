# Viết test cho mọi subtype trong Java Pattern Matching

**Chủ đề:** Java Core Pattern Matching — Thực hành tổng hợp. Bài dùng **Java 21 trở lên**, phiên bản mà **record patterns** (JEP 440) và **pattern matching for switch** (JEP 441) đã là tính năng chính thức. Mục tiêu là xây dựng bộ kiểm thử **không bỏ sót subtype**, đồng thời kiểm tra các nhánh hợp lệ, dữ liệu biên, guard, nested record, component null và null selector.

## 1. “Test cho mọi subtype” nghĩa là gì?

Khi một ứng dụng biểu diễn nhiều loại yêu cầu bằng một interface cha, ví dụ **Message**, có hai dạng thiếu sót thường bị trộn lẫn:

1. **Thiếu nhánh xử lý:** Code production không có case nào nhận một subtype. Với sealed hierarchy và switch expression không có default, compiler có thể phát hiện lỗi này.
2. **Thiếu kiểm thử hành vi:** Production có case của subtype, nhưng logic bên trong có thể trả sai kết quả, xử lý nhầm dữ liệu null, bỏ qua guard false, gọi nhầm service hoặc thay đổi trạng thái sai. Compiler **không chứng minh** những hành vi đó đúng.

Vì thế, chiến lược tốt sử dụng **hai lớp bảo vệ**:

- **Compile-time:** Khai báo miền kiểu đóng bằng sealed interface, dùng exhaustive switch expression, không thêm default chỉ để che subtype chưa được xử lý.
- **Runtime tests:** Cung cấp dữ liệu test cho **từng subtype**, kèm nhiều phân vùng giá trị có ý nghĩa; đối chiếu **actual với expected**, kiểm tra exception và side effect khi có.

Một case được khai báo trong switch **không phải bằng chứng** rằng code ở case đó đã được chạy thử. Tương tự, chỉ tạo một instance của subtype trong test **không phải bằng chứng** đã kiểm tra tất cả nhánh và điều kiện của subtype.

### Đặt tiêu chí hoàn thành rõ ràng

Với mô hình gồm **Created**, **Updated** và **Deleted**, một bộ kiểm thử tối thiểu có thể cam kết:

- Mỗi subtype trực tiếp **có ít nhất một fixture** được gửi vào handler.
- Mỗi subtype có **happy path** và ít nhất một **failure/edge case** tương ứng với contract.
- Các nhánh có guard phải thử cả **true** lẫn **false**.
- Record patterns lồng phải thử **record con tồn tại** và **record con null** nếu model cho phép.
- Selector null phải có test riêng theo hợp đồng API.
- Một thay đổi thêm subtype phải làm lộ yêu cầu cập nhật ở compile time hoặc trong phép kiểm tra tập fixture.
- Có test đầu ra/exception/side effect chứ không chỉ ghi nhận rằng code đã chạy qua.

Đây là một kế hoạch kiểm thử theo **nghĩa nghiệp vụ**, khác với việc chỉ cố đạt một tỷ lệ line coverage cao.

## 2. Mô hình thử nghiệm: ba subtype và record lồng

Xây dựng kiểu Message:

~~~java
sealed interface Message permits Created, Updated, Deleted {}

record Address(String city) {}
record User(String name, Address address) {}

record Created(long id, User user) implements Message {}
record Updated(long id, String label) implements Message {}
record Deleted(long id) implements Message {}
~~~

**Đây là đoạn khai báo mô hình**, code runnable hoàn chỉnh ở mục 6.

Ba subtype trực tiếp là record nên đều ngầm final. Bên trong **Created** có record **User**, tiếp tục chứa **Address**. Vì các record này chưa kiểm tra dữ liệu trong constructor, các tổ hợp như **new Created(1, null)** hoặc **new User("An", null)** vẫn tồn tại và cần test.

Giả định nghiệp vụ của ví dụ:

| Subtype | Thành công khi | Kết quả thành công | Kết quả không hợp lệ |
| --- | --- | --- | --- |
| **Created** | id dương, User tồn tại, name không blank, Address tồn tại, city không blank | **CREATE:id:name@city** | **REJECT:created** |
| **Updated** | id dương, label không blank | **UPDATE:id:label** | **REJECT:updated** |
| **Deleted** | id dương | **DELETE:id** | **REJECT:deleted** |
| **Selector null** | Không hợp lệ theo contract minh họa | Không có happy path | **REJECT:null** |

Mọi name, city và label hợp lệ đều được **trim** khi tạo chuỗi kết quả. Việc đưa trim vào hợp đồng có nghĩa test phải kiểm tra cả chuỗi chứa khoảng trắng ở đầu/cuối.

**Quy ước:** Trong bài này, dữ liệu không hợp lệ được chuyển thành chuỗi kết quả **REJECT** để dễ quan sát. Production code có thể chọn một sealed Result hierarchy hoặc exception chuyên biệt; không nên buộc tất cả dự án trả String.

## 3. Viết handler exhaustive để compiler hỗ trợ

Một triển khai rõ ràng của handler:

~~~java
static String dispatch(Message message) {
    return switch (message) {
        case Created(long id, User(String name, Address(String city)))
                when id > 0 && nonBlank(name) && nonBlank(city) ->
                "CREATE:" + id + ":" + name.trim() + "@" + city.trim();
        case Created(var id, var user) -> "REJECT:created";

        case Updated(long id, String label)
                when id > 0 && nonBlank(label) ->
                "UPDATE:" + id + ":" + label.trim();
        case Updated(var id, var label) -> "REJECT:updated";

        case Deleted(long id) when id > 0 -> "DELETE:" + id;
        case Deleted(var id) -> "REJECT:deleted";

        case null -> "REJECT:null";
    };
}
~~~

Đoạn trên là **phần lõi trích từ chương trình mục 6**. Helper **nonBlank** được khai báo trong bản hoàn chỉnh.

Các điểm quan trọng:

1. **Created với nested record pattern** chỉ khớp cấu trúc có User và Address để deconstruct. Nếu User hoặc Address null, nhánh hợp lệ không khớp.
2. **name/city String null** có thể được ràng buộc trong record pattern theo quy tắc unconditional component patterns; helper nonBlank phải tự kiểm tra null trước khi gọi isBlank.
3. **when** phân biệt dữ liệu hợp lệ với dữ liệu không hợp lệ. Khi guard false, switch tiếp tục tới case cùng subtype không guard.
4. **Created(var id, var user)** bảo đảm mọi Created còn lại có đường xử lý, kể cả record con null.
5. **Updated** và **Deleted** cũng có cặp case hợp lệ và fallback riêng, giúp có test cho cả hai phía của guard.
6. **case null** xử lý selector null. Nếu bỏ case null, subtype coverage vẫn có thể đầy đủ nhưng null selector sẽ có chính sách khác.
7. **Không có default**. Nếu thêm một subtype permitted mới vào Message và biên dịch lại, compiler sẽ báo switch expression chưa exhaustive.

### Đừng dùng default để che trường hợp còn thiếu

~~~java
// Anti-pattern nếu mỗi subtype mới phải được review nghiệp vụ.
return switch (message) {
    case Created c -> handleCreated(c);
    case Updated u -> handleUpdated(u);
    default -> "REJECT:unknown";
};
~~~

Khi thêm Deleted hoặc một subtype mới, default có thể khiến code vẫn biên dịch nhưng subtype mới được gom vào “unknown”. Với miền đóng và yêu cầu rõ **mỗi lệnh đều phải được xử lý riêng**, cách đó mất lợi ích của compiler.

Dù đã khai báo exhaustive, test vẫn cần kiểm tra xem **handleCreated**, **handleUpdated** và các case có thực hiện đúng yêu cầu hay không.

## 4. Thiết kế ma trận test theo subtype và phân vùng dữ liệu

Trước khi viết test code, xác định những giá trị có khả năng tạo đường đi khác nhau.

### 4.1. Created: cấu trúc lồng và các guard

| Test case | Đầu vào | Kết quả kỳ vọng |
| --- | --- | --- |
| created-valid | Created(1, User(" An ", Address(" Hue "))) | **CREATE:1:An@Hue** |
| created-zero-id | Created(0, User("An", Address("Hue"))) | **REJECT:created** |
| created-null-user | Created(1, null) | **REJECT:created** |
| created-null-name | Created(1, User(null, Address("Hue"))) | **REJECT:created** |
| created-null-address | Created(1, User("An", null)) | **REJECT:created** |
| created-null-city | Created(1, User("An", Address(null))) | **REJECT:created** |
| created-blank-city | Created(1, User("An", Address(" "))) | **REJECT:created** |

Các test này không chỉ đại diện cho subtype Created mà còn kiểm tra **từng tầng record lồng**. Chẳng hạn **Created(1, null)** khác **Created(1, User("An", null))**: cùng bị từ chối, nhưng nguyên nhân và pattern được thử không giống nhau.

Nếu API thật phải trả mã lỗi chi tiết cho từng field, hãy mở rộng expected thành **tên field lỗi** chứ không chỉ REJECT:created. Ở case study này, kết quả chung là hợp đồng cố ý lựa chọn để tập trung vào subtype coverage.

### 4.2. Updated: guard và null component

| Test case | Đầu vào | Kết quả kỳ vọng |
| --- | --- | --- |
| updated-valid | Updated(2, " Nova ") | **UPDATE:2:Nova** |
| updated-blank | Updated(2, " ") | **REJECT:updated** |
| updated-null-label | Updated(2, null) | **REJECT:updated** |
| updated-zero-id | Updated(0, "X") | **REJECT:updated** |

Nếu chỉ test Updated hợp lệ, nhánh **case Updated(var id, var label)** chưa được thử. Dữ liệu blank và null cũng không tương đương: cả hai đều bị từ chối nhưng có thể chạm những điểm kiểm tra khác nhau.

### 4.3. Deleted và selector null

| Test case | Đầu vào | Kết quả kỳ vọng |
| --- | --- | --- |
| deleted-valid | Deleted(3) | **DELETE:3** |
| deleted-bad-id | Deleted(-1) | **REJECT:deleted** |
| selector-null | null | **REJECT:null** |

**Deleted** không có component tham chiếu, nhưng vẫn cần test id hợp lệ và không hợp lệ. Test null selector không thuộc subtype nào: nó xác nhận riêng **hợp đồng đầu vào của handler**.

### 4.4. Tại sao không chỉ test một giá trị cho mỗi subtype?

Một bài test “có ít nhất một object mỗi subtype” kiểm tra **sự hiện diện trong fixture**, nhưng chưa bắt các lỗi:

- Guard viết **id >= 0** thay vì **id > 0**.
- Body quên trim name/city.
- Code gọi **name.trim()** khi name null.
- Nested Address null không được xử lý.
- Một nhánh trả **DELETE** cho Updated vì copy/paste sai.
- Fallback cho Deleted có kết quả sai.

Vì vậy nên kiểm thử theo **subtype × phân vùng hành vi có ý nghĩa**, không chỉ theo số lượng subtype.

## 5. Các thành phần cần có của test harness

Một test harness đơn giản không cần thư viện ngoài có thể biểu diễn mỗi ca bằng record:

~~~java
record TestCase(String name, Message input, String expected) {}
~~~

Mỗi TestCase có ba thông tin:

- **name:** tên ổn định để biết ca nào thất bại;
- **input:** giá trị Message cần đưa vào handler, có thể là null;
- **expected:** đầu ra chính xác theo hợp đồng.

Việc **TestCase** là record không tự cấm null ở component input. Vì vậy **new TestCase("selector-null", null, "REJECT:null")** hợp lệ. Khi lưu trong danh sách, bản thân TestCase là object khác null; không nên nhầm nó với việc **List.of(null)**, vốn bị từ chối.

Đối chiếu kết quả:

~~~java
String actual = dispatch(test.input());
if (!Objects.equals(test.expected(), actual)) {
    throw new AssertionError(test.name()
            + " expected=" + test.expected()
            + ", actual=" + actual);
}
~~~

Một test phải **thất bại thực sự** nếu expected khác actual, thay vì chỉ in output. **Objects.equals** xử lý trường hợp kết quả null an toàn; dù ở ví dụ expected đều là String không null, nó vẫn là cách so sánh rõ.

Khi test thất bại, in **tên test, expected và actual** giúp tìm nhanh điều kiện sai. Khi đã sử dụng JUnit, có thể dùng assertEquals để framework tự báo kết quả.

## 6. Chương trình Java 21 hoàn chỉnh, độc lập và chạy được

Lưu toàn bộ chương trình sau trong tệp **SubtypeCoverageTestDemo.java**. Nó sử dụng **sealed Message**, **nested record patterns**, **guard**, **null**, một danh sách 14 test case, và một kiểm tra bổ sung về tập subtype trực tiếp.

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class SubtypeCoverageTestDemo {
    sealed interface Message permits Created, Updated, Deleted {}

    record Address(String city) {}
    record User(String name, Address address) {}

    record Created(long id, User user) implements Message {}
    record Updated(long id, String label) implements Message {}
    record Deleted(long id) implements Message {}

    record TestCase(String name, Message input, String expected) {}

    static boolean nonBlank(String value) {
        return value != null && !value.isBlank();
    }

    static String dispatch(Message message) {
        return switch (message) {
            case Created(long id, User(String name, Address(String city)))
                    when id > 0 && nonBlank(name) && nonBlank(city) ->
                    "CREATE:" + id + ":" + name.trim() + "@" + city.trim();
            case Created(var id, var user) -> "REJECT:created";

            case Updated(long id, String label)
                    when id > 0 && nonBlank(label) ->
                    "UPDATE:" + id + ":" + label.trim();
            case Updated(var id, var label) -> "REJECT:updated";

            case Deleted(long id) when id > 0 -> "DELETE:" + id;
            case Deleted(var id) -> "REJECT:deleted";

            case null -> "REJECT:null";
        };
    }

    static List<TestCase> testCases() {
        var cases = new ArrayList<TestCase>();

        cases.add(new TestCase("created-valid",
                new Created(1, new User(" An ", new Address(" Hue "))),
                "CREATE:1:An@Hue"));

        cases.add(new TestCase("created-zero-id",
                new Created(0, new User("An", new Address("Hue"))),
                "REJECT:created"));

        cases.add(new TestCase("created-null-user",
                new Created(1, null),
                "REJECT:created"));

        cases.add(new TestCase("created-null-name",
                new Created(1, new User(null, new Address("Hue"))),
                "REJECT:created"));

        cases.add(new TestCase("created-null-address",
                new Created(1, new User("An", null)),
                "REJECT:created"));

        cases.add(new TestCase("created-null-city",
                new Created(1, new User("An", new Address(null))),
                "REJECT:created"));

        cases.add(new TestCase("created-blank-city",
                new Created(1, new User("An", new Address(" "))),
                "REJECT:created"));

        cases.add(new TestCase("updated-valid",
                new Updated(2, " Nova "),
                "UPDATE:2:Nova"));

        cases.add(new TestCase("updated-blank",
                new Updated(2, " "),
                "REJECT:updated"));

        cases.add(new TestCase("updated-null-label",
                new Updated(2, null),
                "REJECT:updated"));

        cases.add(new TestCase("updated-zero-id",
                new Updated(0, "X"),
                "REJECT:updated"));

        cases.add(new TestCase("deleted-valid",
                new Deleted(3),
                "DELETE:3"));

        cases.add(new TestCase("deleted-bad-id",
                new Deleted(-1),
                "REJECT:deleted"));

        cases.add(new TestCase("selector-null",
                null,
                "REJECT:null"));

        return cases;
    }

    public static void main(String[] args) {
        int passed = 0;
        Set<Class<?>> exercised = new HashSet<>();

        for (TestCase test : testCases()) {
            String actual = dispatch(test.input());
            if (!Objects.equals(test.expected(), actual)) {
                throw new AssertionError(test.name()
                        + " expected=" + test.expected()
                        + ", actual=" + actual);
            }

            if (test.input() != null) {
                exercised.add(test.input().getClass());
            }
            passed++;
            System.out.println("PASS " + test.name() + " => " + actual);
        }

        Class<?>[] direct = Message.class.getPermittedSubclasses();
        for (Class<?> subtype : direct) {
            if (!exercised.contains(subtype)) {
                throw new AssertionError(
                        "Missing test data for " + subtype);
            }
        }

        System.out.println("COVERED: " + exercised.size()
                + "/" + direct.length + " direct subtypes");
        System.out.println("ALL: " + passed + " tests passed");
    }
}
~~~

### 6.1. Biên dịch và chạy

Dùng **JDK 21 hoặc mới hơn**, tại thư mục chứa file:

~~~bash
javac SubtypeCoverageTestDemo.java
java SubtypeCoverageTestDemo
~~~

**Đầu ra chính xác:**

~~~text
PASS created-valid => CREATE:1:An@Hue
PASS created-zero-id => REJECT:created
PASS created-null-user => REJECT:created
PASS created-null-name => REJECT:created
PASS created-null-address => REJECT:created
PASS created-null-city => REJECT:created
PASS created-blank-city => REJECT:created
PASS updated-valid => UPDATE:2:Nova
PASS updated-blank => REJECT:updated
PASS updated-null-label => REJECT:updated
PASS updated-zero-id => REJECT:updated
PASS deleted-valid => DELETE:3
PASS deleted-bad-id => REJECT:deleted
PASS selector-null => REJECT:null
COVERED: 3/3 direct subtypes
ALL: 14 tests passed
~~~

**Cách đọc:** 14 dòng PASS chứng minh từng cặp **input / expected** đang khớp **implementation hiện tại**. Dòng COVERED chứng minh các fixture đã gửi vào dispatch có xuất hiện đủ **Created, Updated, Deleted** trong tập kiểu trực tiếp được phép. Nó **không** khẳng định branch coverage hoặc mọi tổ hợp dữ liệu đã được thử.

Nếu có sai kết quả, chương trình ném **AssertionError** tại ca tương ứng và không in dòng tổng kết cuối một cách bình thường. Nếu thiếu fixture cho một subtype trong sealed hierarchy, vòng kiểm tra getPermittedSubclasses cũng ném AssertionError.

### 6.2. Tại sao dùng ArrayList cho các test case?

Danh sách chứa **record TestCase** khác null, trong đó một component input có thể null. Dùng ArrayList giúp thêm từng ca rõ ràng. Nếu viết **List.of(new TestCase(...), ...)** cũng hợp lệ vì **phần tử** TestCase khác null. Nhưng **List.of(null)** không được phép.

Một cách viết không an toàn là tạo ngay **List.of(new Created(...), null)** để làm danh sách đầu vào; lời gọi List.of sẽ ném NullPointerException trước khi test handler. Trong test null selector, cần đặt null **bên trong component TestCase** hoặc dùng collection cho phép null.

## 7. Kiểm tra tập subtype bằng getPermittedSubclasses()

Java cung cấp **Class.getPermittedSubclasses()** để lấy tập class/interface được phép trực tiếp kế thừa hoặc triển khai một sealed type. Trong ví dụ:

~~~java
Class<?>[] direct = Message.class.getPermittedSubclasses();
~~~

Với Message có ba record **Created**, **Updated**, **Deleted**, mảng trả về là danh sách ba subtype trực tiếp. Vì vậy test có thể so với những subtype thực sự xuất hiện trong dữ liệu:

~~~java
Set<Class<?>> exercised = new HashSet<>();

for (TestCase test : testCases()) {
    if (test.input() != null) {
        exercised.add(test.input().getClass());
    }
}

for (Class<?> subtype : Message.class.getPermittedSubclasses()) {
    if (!exercised.contains(subtype)) {
        throw new AssertionError("Missing test data for " + subtype);
    }
}
~~~

Đây là **test hiện diện của fixture**, không phải phép đo số case trong switch và cũng không phải phép đo line coverage.

### 7.1. Khi thêm subtype mới

Nếu hierarchy được cập nhật thành:

~~~java
// Phiên bản minh họa khác, không chép đè vào demo mà không
// đồng thời cập nhật permits, code dispatch và test.
sealed interface Message permits Created, Updated, Deleted, Archived {}
record Archived(long id) implements Message {}
~~~

Hai kiểm tra có thể nhắc bạn thay đổi:

1. **Compiler:** Nếu dispatch vẫn là switch expression không default và thiếu case Archived, build sẽ báo **không exhaustive**.
2. **Fixture coverage test:** Sau khi bạn thêm nhánh Archived để code biên dịch nhưng **chưa thêm test data cho Archived**, phép so sánh getPermittedSubclasses sẽ ném AssertionError vì chưa từng chạy một Archived.

Cơ chế bổ sung này giúp tránh trường hợp sửa code cho hết lỗi biên dịch rồi **quên test subtype mới**.

### 7.2. Giới hạn quan trọng của cách kiểm tra reflection

- **Chỉ là permitted trực tiếp:** getPermittedSubclasses không tự duyệt đệ quy mọi subtype lá. Nếu một permitted subtype tiếp tục là sealed và có nhiều nhánh con, cần định nghĩa chính sách bao phủ các lá hoặc duyệt cây có kiểm soát.
- **Nhánh non-sealed:** có thể có nhiều subclass xuất hiện sau này, không thể xem tập permitted trực tiếp là tất cả các concrete descendants sẽ tồn tại.
- **Class thực tế khác kiểu permitted:** Nếu permitted subtype là sealed/abstract class trung gian, **input.getClass()** có thể là một descendant khác. So bằng Class trực tiếp như demo chỉ thích hợp khi permitted subtype chính là những record final được khởi tạo.
- **Fixture có đại diện không đồng nghĩa đầy đủ nhánh:** Nếu chỉ một input Created hợp lệ, reflection vẫn báo Created đã được thử dù nhánh REJECT:created chưa chạy.
- **Không thay thế test hành vi:** Cần kiểm tra expected outputs, exceptions và side effects chứ không chỉ Set<Class<?>>.

Vì thế hãy ghi tên phép kiểm tra là **direct-subtype fixture coverage**, không gọi nó là “100% branch coverage”.

## 8. Thử nghiệm âm tính: compiler phải phát hiện subtype bị bỏ sót

Xét một kiểu khác để minh họa:

~~~java
// Mã âm tính: biên dịch lỗi có chủ đích để chứng minh exhaustiveness.
sealed interface Event permits Added, Changed, Removed {}

record Added() implements Event {}
record Changed() implements Event {}
record Removed() implements Event {}

class MissingSubtypeExample {
    static String classify(Event event) {
        return switch (event) {
            case Added a -> "ADDED";
            case Changed c -> "CHANGED";
        };
    }
}
~~~

**Đoạn mã này cố ý không chạy được.** Switch expression thiếu nhánh cho Removed. Compiler Java 21+ có thể thông báo:

~~~text
the switch expression does not cover all possible input values
~~~

Cách sửa đúng là bổ sung nhánh dành cho Removed với hành vi nghiệp vụ tương ứng, **không phải thêm default để làm mất yêu cầu xem xét subtype**.

### Exhaustiveness không loại bỏ mọi bug

Bạn có thể viết:

~~~java
case Removed r -> "ADDED";
~~~

Switch lúc ấy có thể exhaustive nhưng vẫn **sai kết quả**. Chỉ một test với input Removed và expected "REMOVED" mới bắt được bug này. Đó là lý do cần cả compiler **và** runtime tests.

Khi có guard:

~~~java
case Deleted(long id) when id > 0 -> "DELETE:" + id;
~~~

nhánh này **không** xử lý Deleted với id <= 0. Một case cùng subtype không guard như **case Deleted(var id) -> "REJECT:deleted"** bảo đảm có đường đi cho giá trị còn lại và tạo điểm đặt test âm.

**Lưu ý về binary:** Phân tích exhaustive dựa trên class có mặt lúc **biên dịch**. Nếu một module hoặc library được thay sau khi consumer đã được biên dịch, binary cũ có thể gặp một subtype mới mà nó chưa từng biết. Khi không có nhánh phù hợp, switch pattern có thể ném **MatchException** ở runtime. Cần rebuild và triển khai các module phụ thuộc nhất quán.

## 9. Viết cùng bộ test với JUnit 5

Khi đưa code vào dự án thật, **JUnit 5** giúp báo cáo từng ca rõ ràng và tích hợp CI. Đoạn sau giả định **JUnit Jupiter + junit-jupiter-params** đã được khai báo ở test dependencies và đã bật JUnit Platform trong build.

Tạo file **SubtypeCoverageJUnitTest.java** trong test source set **cùng package** với SubtypeCoverageTestDemo. Mã dùng lại testCases() và dispatch() từ demo. Nếu demo được chuyển vào package riêng, cần khai báo package/import và điều chỉnh visibility phù hợp.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class SubtypeCoverageJUnitTest {

    static Stream<Arguments> samples() {
        return SubtypeCoverageTestDemo.testCases().stream()
                .map(tc -> Arguments.of(
                        tc.name(), tc.input(), tc.expected()));
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("samples")
    void dispatchMatchesExpected(
            String label,
            SubtypeCoverageTestDemo.Message input,
            String expected) {

        assertEquals(expected,
                SubtypeCoverageTestDemo.dispatch(input),
                label);
    }

    @Test
    void fixturesCoverEveryDirectSubtype() {
        Set<Class<?>> exercised = SubtypeCoverageTestDemo
                .testCases().stream()
                .map(tc -> tc.input())
                .filter(Objects::nonNull)
                .map(Object::getClass)
                .collect(Collectors.toSet());

        for (Class<?> subtype : SubtypeCoverageTestDemo
                .Message.class.getPermittedSubclasses()) {
            assertTrue(exercised.contains(subtype),
                    "Missing fixture for " + subtype.getSimpleName());
        }
    }
}
~~~

**Đây là code dành cho project đã có JUnit 5**, không thể biên dịch chỉ bằng JDK nếu chưa thêm dependencies. Chương trình **SubtypeCoverageTestDemo.java ở mục 6** mới là ví dụ hoàn chỉnh độc lập để chạy trực tiếp với javac/java.

Các lợi ích của parameterized test:

- Mỗi tên ca được hiển thị riêng trong test report.
- Chỉ cần thêm một TestCase vào matrix để JUnit tạo thêm một lần chạy.
- Có thể giữ logic assert trong một chỗ, giảm copy/paste.
- Một test riêng phát hiện subtype trực tiếp chưa xuất hiện trong fixture.

**Lưu ý về test discovery:** JUnit nhận các test trong test source set khi build được cấu hình đúng. Nếu chạy Gradle, cần dependencies phù hợp, dùngJUnitPlatform() khi cần và Java toolchain/source level 21. Lệnh Maven/Gradle của project thực tế có thể khác; đừng nhầm một file test có annotation với việc nó chắc chắn đã được CI chạy.

### 9.1. Khi nào dùng @Test riêng thay vì @ParameterizedTest?

Dùng **@ParameterizedTest** cho nhiều input đi qua cùng logic xử lý; dùng **@Test** riêng nếu cần kiểm tra:

- Exception đặc thù của một constructor hoặc service;
- Side effects trong database/repository;
- Transaction rollback;
- Một chuỗi hành động có state, chẳng hạn Created → Updated → Deleted;
- Kiểm tra tập subtype ở mức reflection;
- Concurrency, retry hoặc idempotency.

Một bài test đủ ý nghĩa phải kiểm tra **trạng thái sau lệnh**, không chỉ một String trả về, nếu method thật có side effect.

## 10. Test null, guard và record patterns theo đúng ngữ nghĩa Java

### 10.1. Selector null

Với pattern switch, null cần một chính sách tường minh. Demo dùng:

~~~java
case null -> "REJECT:null";
~~~

Nếu xóa case null, switch có thể vẫn exhaustive theo ba subtype **Created**, **Updated**, **Deleted**, nhưng null selector có thể ném NullPointerException. Test **selector-null** giúp phát hiện thay đổi contract khi refactor.

**Đừng giả định default thường sẽ bắt null.** Tùy cú pháp và thứ tự nhãn, case null phải được xử lý riêng hoặc dùng một chính sách từ chối rõ ràng như Objects.requireNonNull trước switch.

### 10.2. Component String null

Record pattern **Updated(long id, String label)** có thể ràng buộc label null khi kiểu component là String theo một pattern không điều kiện. Vì vậy helper:

~~~java
static boolean nonBlank(String value) {
    return value != null && !value.isBlank();
}
~~~

dùng short-circuit để không gọi isBlank trên null. Test **updated-null-label** xác nhận handler trả REJECT thay vì ném NPE. Đồng thời test **updated-blank** bắt lỗi nghiệp vụ khi label chỉ toàn khoảng trắng.

### 10.3. Nested record null

Mẫu:

~~~java
Created(long id, User(String name, Address(String city)))
~~~

đòi hỏi component User và Address là các record có thể deconstruct. Nếu User hoặc Address null, mẫu lồng **không khớp**; nhánh **case Created(var id, var user)** tiếp nhận trường hợp còn lại.

Test cần có cả:

- **new Created(1, null)**;
- **new Created(1, new User("An", null))**;
- **new Created(1, new User(null, new Address("Hue")))**;
- **new Created(1, new User("An", new Address(null)))**.

Chúng cùng ra REJECT:created trong ví dụ nhưng khác đường matching và guard. Nếu ứng dụng cần trả mã lỗi theo field, test phải xác nhận từng field path.

### 10.4. Guard false khác exception

Khi **when** trả false, switch tiếp tục thử những case phù hợp phía sau. Khi guard **ném exception**, switch kết thúc bất thường; nó không giả định guard false và bỏ qua lỗi.

Ví dụ không nên viết:

~~~java
// Anti-pattern: có thể gọi isBlank trên String null.
case Updated(var id, var label)
        when label.isBlank() -> "REJECT:updated";
~~~

Nếu label null, guard ném NPE. Dùng helper null-safe hoặc kiểm tra rõ trong case body theo hợp đồng.

### 10.5. Thứ tự case và dominance

Trong handler, nhánh **case Updated(var id, var label)** không guard phải đứng **sau** case Updated có guard. Nếu đặt nhánh tổng quát trước, nhánh hẹp có thể bị dominated và compiler báo không thể tới được.

Test nhiều input giúp phát hiện thứ tự nghiệp vụ sai; compiler giúp ngăn một số lỗi dominance về cấu trúc nhưng không biết expected output nào mới đúng với domain.

## 11. Coverage ở ba tầng: subtype, branch, nghiệp vụ

Để không bị đánh lừa bởi một con số coverage, tách các câu hỏi:

| Tầng | Câu hỏi | Phương pháp |
| --- | --- | --- |
| **Subtype fixture coverage** | Có ít nhất một instance được test cho mỗi subtype trực tiếp? | Kiểm tra getPermittedSubclasses đối chiếu tập fixture |
| **Branch/condition coverage** | Các đường case/guard true/false có được thực thi? | Test matrix, coverage report, kiểm tra điều kiện |
| **Behavior coverage** | Kết quả, trạng thái và exception có đúng contract? | assertEquals, assertThrows, assertions trạng thái |

Một bộ test có thể đạt **3/3 subtype** nhưng vẫn bỏ sót nhánh REJECT của Updated. Ngược lại, branch coverage 100% trong vài hàm chưa chứng minh mọi trạng thái dữ liệu của ứng dụng được test.

Với hierarchy lớn, không nhất thiết chạy **tích Descartes của mọi giá trị**. Hãy chọn phân vùng theo:

1. subtype;
2. nhánh hợp lệ và không hợp lệ;
3. điều kiện biên, ví dụ id = -1, 0, 1;
4. null ở từng tầng record;
5. các tương tác thật sự làm thay đổi hành vi;
6. các bug đã từng xảy ra hoặc có khả năng cao.

**Property-based tests** có thể bổ trợ bằng cách sinh nhiều giá trị theo các bất biến, chẳng hạn “mọi Created có id không dương đều bị từ chối”. Tuy nhiên, các bộ sinh dữ liệu cần biết cấu trúc từng subtype và test vẫn phải có expected behavior có ý nghĩa. Sinh ngẫu nhiên đơn thuần không đảm bảo mỗi subtype hoặc mỗi guard đã được thử.

## 12. Test cho exception, constructor validation và side effect

Demo chủ động dùng record **raw** không có validation constructor, nên có thể test những trường hợp Created(null user), Updated(null label) tại handler. Trong một domain khác, compact constructor có thể từ chối dữ liệu sai **trước khi handler được gọi**:

~~~java
// Mô hình thay thế, không ghép trực tiếp vào demo mục 6.
record StrictDeleted(long id) {
    StrictDeleted {
        if (id <= 0) {
            throw new IllegalArgumentException("id");
        }
    }
}
~~~

Nếu dùng model ấy, test **new StrictDeleted(0)** phải assertThrows cho constructor. Không cố truyền một object mà constructor đã từ chối vào handler: test sẽ thất bại ở bước tạo dữ liệu, trước logic dispatch.

### 12.1. Hai test khác trách nhiệm

- **Constructor test:** Giá trị domain bất hợp lệ bị từ chối đúng loại exception.
- **Handler test:** Một command/event đã xây dựng hợp lệ được xử lý đúng và tạo kết quả hoặc side effect.

Nếu dùng factory trả Result thay vì ném exception, test cần xác nhận subtype Result và error code, không ép mọi cơ chế validation phải ném ngoại lệ.

### 12.2. Nếu handler có trạng thái

Với một command handler sửa kho dữ liệu, mỗi subtype cần test cả:

- response trả về;
- trạng thái trước/sau;
- số lần gọi repository;
- hành vi khi retry;
- tác vụ phụ (audit/event) nếu bắt buộc;
- không có side effect khi lệnh bị từ chối.

Exhaustive switch không biết transaction, quyền truy cập hay kết nối mạng. Việc test mọi subtype **không thay** kiểm thử tích hợp nếu tính đúng phụ thuộc hạ tầng.

## 13. Khi hierarchy có subtype trung gian hoặc không phải sealed

Demo chỉ có các subtype record final trực tiếp. Nếu hierarchy phức tạp hơn:

~~~java
// Minh họa cấu trúc mở rộng, không ghép vào demo.
sealed interface Input permits UserInput, SystemInput {}

sealed interface UserInput extends Input permits SignIn, SignOut {}

record SignIn(String name) implements UserInput {}
record SignOut(String name) implements UserInput {}

non-sealed interface SystemInput extends Input {}
~~~

**getPermittedSubclasses()** của Input chỉ trả các subtype trực tiếp **UserInput** và **SystemInput**, không tự liệt kê SignIn/SignOut và mọi triển khai tương lai của SystemInput. Một bộ test chỉ đối chiếu class thực tế với hai type trực tiếp ấy có thể **báo thiếu sai cách**.

Ở hierarchy đó cần thiết kế rõ mục tiêu:

- Bao phủ **từng nhánh trực tiếp** ở mức dispatch;
- Bao phủ **các subtype lá** được công nhận trong sản phẩm;
- Hoặc bao phủ những plugin/implementations được đăng ký trong runtime.

Với nhánh **non-sealed**, các triển khai mới có thể được thêm ngoài mô-đun gốc. Khi đó không thể dùng riêng phép liệt kê permitted để chứng minh “mọi class tồn tại trên thế giới” đều được test. Registry, contract tests hoặc discovery theo cơ chế extension có thể phù hợp hơn.

**Giới hạn cốt lõi:** “Mọi subtype” phải được định nghĩa theo **miền kiểu và ranh giới sản phẩm**. Trong sealed hierarchy đóng gồm record final, việc liệt kê đơn giản. Trong hệ thống plugin mở, cần một chiến lược kiểm thử khác.

## 14. Tích hợp vào quy trình build và CI

Một quy trình áp dụng cho project Java 21:

1. **Chốt Java source/toolchain 21+:** Record patterns và switch patterns chính thức từ Java 21, không cần enable-preview.
2. **Build sạch:** biên dịch lại toàn bộ module có sealed hierarchy để compiler phát hiện các switch thiếu subtype.
3. **Chạy test matrix:** dùng một test riêng cho mỗi phân vùng đầu vào có ý nghĩa.
4. **Chạy test fixture coverage:** so tập subtype trực tiếp với tập fixture hoặc bộ test được khai báo rõ.
5. **Xem branch coverage:** xác nhận guard true/false, fallback và throw paths được thử.
6. **Chạy integration tests:** nếu mỗi subtype có side effect, kiểm tra transaction, permission, repository và event emission.
7. **Giữ pipeline bắt lỗi:** không dùng default để bỏ qua lỗi compiler nếu lệnh mới cần được review.
8. **Review thay đổi model và test cùng một pull request:** thêm subtype, handler case, dữ liệu test và contract docs đồng thời.

Với Gradle hoặc Maven, cần khai báo JUnit 5 và cấu hình test discovery tương ứng. Lệnh chạy cụ thể phụ thuộc project; ví dụ Gradle wrapper có thể dùng:

~~~bash
./gradlew clean test
~~~

Hoặc Maven trong project có các test plugin tương thích:

~~~bash
mvn clean test
~~~

Những lệnh này dành cho **dự án đã cấu hình build và JUnit**, không phải lệnh để chạy trực tiếp file demo độc lập. Để chạy file demo chỉ dùng javac/java ở mục 6.

### Kiểm tra tên test trong CI

Tên như **created-null-address** hữu ích hơn **testCase7** khi một pipeline bị lỗi. Một chiến lược thường dùng là **subtype-trạng_thái/điều_kiện**, ví dụ:

- created-valid;
- created-null-user;
- updated-zero-id;
- deleted-bad-id.

Khi test fail, có thể định vị ngay subtype và phân vùng dữ liệu nào bị ảnh hưởng.

## 15. Những lỗi phổ biến khi viết test cho subtype

**Lỗi 1 — Chỉ test một object mỗi subtype.** Có thể đạt đủ fixture nhưng bỏ qua guard false, component null và ngoại lệ.

**Lỗi 2 — Chỉ tin compiler.** Compiler chỉ kiểm tra exhaustiveness/dominance, không xác nhận body trả đúng giá trị hoặc side effect đúng.

**Lỗi 3 — Luôn thêm default cho switch.** Default làm subtype mới tự lọt qua fallback; compile-time không còn nhắc nơi cần xem lại.

**Lỗi 4 — Chỉ nhìn line coverage.** Cùng một dòng có thể được chạy nhưng thiếu tình huống tạo ra kết quả sai, đặc biệt với điều kiện logic.

**Lỗi 5 — Tưởng case null kiểm tra mọi component null.** Selector null và nested component null là những đường thực thi khác nhau.

**Lỗi 6 — Test dữ liệu không thể tạo.** Nếu constructor cấm id âm, việc tạo object sai thất bại trước handler; hãy đặt test đúng ở constructor/factory.

**Lỗi 7 — Dùng List.of(null) cho fixture.** Test bị lỗi ở khâu tạo collection, không kiểm tra handler. Bọc null trong TestCase record hoặc chọn collection cho phép null.

**Lỗi 8 — Reflection coverage bị diễn giải quá rộng.** getPermittedSubclasses chỉ cho subtype trực tiếp; với hierarchy lồng/non-sealed, cần chính sách riêng.

**Lỗi 9 — Không assert actual.** Chạy mọi subtype rồi chỉ in output không tự phát hiện regression; phải có expected và assertion.

**Lỗi 10 — Bỏ quên tên và nguyên nhân test fail.** Một tên ca rõ và assertion báo expected/actual giảm đáng kể thời gian chẩn đoán.

**Lỗi 11 — Không xem xét compatibility khi thêm subtype.** Binary cũ hoặc test module chưa biên dịch lại có thể bỏ sót thay đổi; build và deploy phụ thuộc phải nhất quán.

**Lỗi 12 — Cố chạy tất cả tổ hợp vô nghĩa.** Test quá nhiều mẫu trùng lặp có thể làm CI chậm và khó bảo trì. Chọn phân vùng theo ý nghĩa nghiệp vụ, biên và rủi ro.

## 16. Checklist code review cho bài thực hành tổng hợp

- [ ] Đã liệt kê rõ những subtype nào thuộc miền cần kiểm thử?
- [ ] Model sealed và các subtype final/record có phù hợp với kiến trúc hiện tại?
- [ ] Handler dùng switch expression exhaustive không default khi cần kiểm tra compile-time?
- [ ] Có ít nhất một fixture cho từng subtype trực tiếp và test kiểm tra tập fixture?
- [ ] Mỗi subtype có happy path và edge/failure path quan trọng?
- [ ] Các guard có test true lẫn false, đặc biệt ở giá trị biên?
- [ ] Selector null và component null của nested record có test riêng?
- [ ] Có assert expected output/exception/side effect, không chỉ chạy method?
- [ ] Tên ca kiểm thử có giúp truy ra subtype và điều kiện thất bại?
- [ ] Nếu thêm subtype mới, compile, fixture coverage test và behavior tests có buộc xem lại đầy đủ?
- [ ] Với hierarchy non-sealed hoặc phân nhánh nhiều tầng, định nghĩa coverage có được điều chỉnh?
- [ ] Test dùng JDK 21+ và có được CI thực sự phát hiện/chạy bằng đúng framework không?

**Kết luận:** Để **viết test cho mọi subtype**, không chỉ cần một instance của mỗi kiểu. Hãy kết hợp **sealed hierarchy + exhaustive switch** để compiler phát hiện thiếu nhánh, **test matrix theo subtype và phân vùng dữ liệu** để xác nhận hành vi, cùng **fixture coverage test** để nhắc khi mô hình được mở rộng mà chưa có dữ liệu kiểm thử. Khi record có component null, guard, subtype lồng hoặc side effect, cần thêm những test đúng ngữ nghĩa. Một suite đáng tin phải chứng minh **đúng hành vi**, không chỉ **có nhánh**.