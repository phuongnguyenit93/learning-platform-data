# Khóa trùng, hàm gộp và lựa chọn loại Map khi thu thập Stream

## 1. Vấn đề thực tế: nhiều phần tử có thể tạo cùng một khóa

Khi thu thập kết quả từ Stream thành `Map<K,V>`, ta thường dùng `Collectors.toMap()`. Mỗi phần tử nguồn được chuyển thành một **khóa** và một **giá trị**:

```text
Person(name="An",  team="A", score=10) → key="A", value=10
Person(name="Binh",team="B", score=20) → key="B", value=20
Person(name="Chi", team="A", score=15) → key="A", value=15
                                           ↑ khóa "A" trùng
```

Hai đối tượng cùng khóa `"A"` đặt ra một câu hỏi nghiệp vụ: giữ `10`, giữ `15`, cộng thành `25`, gộp thành danh sách, hay báo lỗi?

**Không tồn tại chính sách đúng mặc định cho mọi bài toán.** `Collectors.toMap(keyMapper, valueMapper)` với hai tham số sẽ **ném `IllegalStateException` khi xuất hiện khóa trùng**. Đó là cách phát hiện va chạm, không phải tự động giữ bản ghi đầu hoặc cuối.

Đề bài này hướng dẫn ba quyết định riêng biệt cần đưa ra trước khi thu thập:

1. **Khóa được xác định như thế nào?** Các bản ghi nào được xem là cùng khóa?
2. **Khi trùng khóa, cần làm gì?** Báo lỗi, chọn giá trị, cộng dồn, kết hợp hay giữ tất cả?
3. **Map kết quả cần tính chất nào?** Không quan tâm thứ tự, giữ thứ tự chèn, sắp theo khóa, tối ưu khóa enum hay phục vụ thao tác đồng thời?

Đừng chọn merge function chỉ để “cho code hết lỗi” mà không trả lời đúng quy tắc nghiệp vụ.

## 2. Các overload của Collectors.toMap()

Các dạng API quan trọng trong Java 17:

```java
Collectors.toMap(keyMapper, valueMapper)

Collectors.toMap(keyMapper, valueMapper, mergeFunction)

Collectors.toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
```

Đây là chữ ký **rút gọn để đọc**; trong mã Java thực tế, `keyMapper`, `valueMapper`, `mergeFunction` và `mapFactory` phải là biểu thức/giao diện có kiểu generic thích hợp.

| Dạng | Khóa trùng | Kiểu Map cụ thể |
| --- | --- | --- |
| Hai tham số | Ném `IllegalStateException` | **Không được API cam kết** implementation cụ thể |
| Ba tham số | Dùng `BinaryOperator<U>` để kết hợp hai giá trị | **Không được API cam kết** implementation cụ thể |
| Bốn tham số | Dùng merge function | Lấy từ `Supplier<M>` do bạn truyền, ví dụ `LinkedHashMap::new`, `TreeMap::new` |

Khi dùng hai tham số, `keyMapper` chọn khóa và `valueMapper` chọn giá trị. Dù hai phần tử cho cùng khóa và **cùng giá trị** thì đó vẫn là khóa trùng; collector không tự xem điều đó là hợp lệ.

**Phân biệt collector và Stream:** `toMap` là collector truyền vào terminal operation `collect(...)`. Sau khi collect, Stream đã tiêu thụ và không được tái sử dụng. Muốn thử chính sách gộp khác, tạo stream mới từ cùng nguồn như `list.stream()`.

## 3. Hai tham số: khóa trùng gây IllegalStateException

Ví dụ ngắn:

```java
record Person(String name, String team, int score) {}
List<Person> people = List.of(
        new Person("An", "A", 10),
        new Person("Chi", "A", 15));
Map<String, String> byTeam = people.stream()
        .collect(Collectors.toMap(Person::team, Person::name));
```

Đây là đoạn **cố ý gây ngoại lệ khi chạy** (đặt các khai báo trong bối cảnh lớp/phương thức phù hợp, import `List`, `Map`, `Collectors`). Cả hai Person có cùng khóa `"A"`, lần thu thập sẽ phát sinh `IllegalStateException`. Chương trình hoàn chỉnh ở mục 8 bắt ngoại lệ để vẫn chạy tiếp.

Nếu hệ thống quy định **mỗi mã định danh phải duy nhất**, hành vi fail-fast này rất phù hợp: nó giúp phát hiện dữ liệu sai thay vì âm thầm ghi đè. Ví dụ lập map `userId → user` khi `userId` bắt buộc duy nhất là nơi không nên tự ý chọn phần tử đầu hoặc cuối.

**Không nhầm với Map.put:** `map.put(key, value)` thông thường thay giá trị đang gắn với khóa cũ. Nhưng `Collectors.toMap(k,v)` hai tham số có chính sách **báo lỗi** khi trùng; không phải thực hiện `put` ghi đè như người mới thường dự đoán.

## 4. Hàm gộp: giải quyết xung đột theo quy tắc nghiệp vụ

Dạng ba hoặc bốn tham số nhận một **merge function** áp dụng lên hai giá trị cùng khóa:

```java
Map<String, Integer> totals = people.stream()
        .collect(Collectors.toMap(
                Person::team,
                Person::score,
                Integer::sum));
```

Đây là các lệnh minh họa với `people` và record `Person` ở mục 3 nhưng có thể dùng danh sách nhiều phần tử như chương trình chính. Đối với nhóm `"A"`, `10 + 15 = 25`; nhóm `"B"` có thể có `20 + 7 = 27`.

Khai báo `Integer::sum` tương đương về cách tính với `(a,b) -> a+b`. Hai tham số `a`, `b` là **giá trị đã ánh xạ**, không phải hai đối tượng `Person` ban đầu. Nếu cần tên, mã đơn, thời gian hay thuộc tính khác để chọn bản ghi, hãy thiết kế `valueMapper` tạo đối tượng có đủ thông tin rồi viết chính sách gộp phù hợp.

Các chính sách thường gặp:

| Chính sách | Merge function | Kết quả khi gặp giá trị cũ A, mới B |
| --- | --- | --- |
| Giữ giá trị đang có | `(oldValue, newValue) -> oldValue` | A |
| Dùng giá trị đến sau | `(oldValue, newValue) -> newValue` | B |
| Tổng điểm / số lượng | `Integer::sum` hoặc `Long::sum` | A + B |
| Chọn số lớn hơn | `Integer::max` | max(A,B) |
| Ghép mô tả | `(a,b) -> a + "+" + b` | Chuỗi kết hợp |
| Kết hợp đối tượng | `(a,b) -> combine(a,b)` | Theo hợp đồng `combine` do ứng dụng định nghĩa |

Các biểu thức trong bảng là mẫu cho **kiểu phù hợp** và không phải chương trình độc lập. `Integer::sum` chỉ hoạt động khi giá trị gộp tương thích `Integer`; `String` cần một hàm gộp khác.

**Giữ đầu / giữ cuối là khái niệm dễ gây nhầm trong parallel và unordered stream.** Với danh sách có encounter order, stream tuần tự và phép thu thập minh họa, các mẫu `oldValue`/`newValue` cho ra các kết quả rõ ràng. Nhưng trong bài toán cần chọn bản ghi “mới nhất theo thời gian”, hãy **so sánh trường thời gian trực tiếp** thay vì giả định phần tử đi sau trong cấu trúc thực thi chính là mới nhất.

## 5. Hợp đồng của merge function: nên kết hợp được, thuần và xác định

Trong quá trình thu thập, đặc biệt với **parallel streams**, các phần map có thể được tích lũy riêng rồi **kết hợp** lại. Merge function phải phù hợp với cách reducer/collector nhóm giá trị.

**Tính kết hợp (*associativity*):**

```text
merge(merge(a,b),c) == merge(a,merge(b,c))
```

Với `Integer::sum` khi không tràn, phép cộng nguyên có tính kết hợp. `Integer::max` cũng có tính kết hợp. Ngược lại, `(a,b) -> a-b` thường **không kết hợp**, nên kết quả có thể phụ thuộc cách nhóm. Đặc biệt với `double`, cộng số thực có sai số làm tròn nên không bảo đảm kết hợp chính xác theo biểu diễn, cần cân nhắc nếu kết quả tài chính/độ chính xác quan trọng.

Ngoài ra merge function nên:

- **Không có side effects** như ghi cơ sở dữ liệu, thanh toán hoặc sửa trạng thái dùng chung. Việc gọi hàm phụ thuộc va chạm, kế hoạch thực thi và cách merge map con.
- **Không dựa vào số lần được gọi** để làm thống kê nghiệp vụ. Collector được phép chia việc và gộp theo cấu trúc triển khai.
- **Không làm hỏng giá trị đầu vào** nếu đối tượng giá trị mutable được chia sẻ.
- Có quy tắc rõ với dữ liệu bất thường, trùng bản ghi, giá trị bằng nhau và nhu cầu xác định thứ tự.

Không phải mọi phép gộp cần **giao hoán** (`merge(a,b)==merge(b,a)`) để dùng về mặt ngữ nghĩa, nhưng nếu không giao hoán thì thứ tự có thể trở thành phần quan trọng của hợp đồng. Khi cần kết quả bất kể thứ tự xử lý, ưu tiên phép gộp vừa kết hợp vừa giao hoán hoặc thiết kế rõ thứ tự trước khi thu thập.

## 6. Lựa chọn loại Map: thứ tự duyệt và cách nhận biết khóa

API Map không mặc định bảo đảm thứ tự cho mọi implementation. Chọn loại Map dựa vào yêu cầu thực tế, không chỉ để một lần in kết quả “trông đúng”.

| Loại Map | Đặc điểm nổi bật | Khi nào nên chọn |
| --- | --- | --- |
| `HashMap<K,V>` | Không bảo đảm thứ tự iteration, lookup trung bình nhanh | Khi **không quan tâm thứ tự** |
| `LinkedHashMap<K,V>` | Duy trì thứ tự chèn mặc định | Khi muốn **duyệt theo thứ tự chèn** sau khi collect |
| `TreeMap<K,V>` | Sắp khóa theo natural ordering hoặc `Comparator` | Khi muốn **map được sắp theo khóa** |
| `EnumMap<E,V>` | Khóa thuộc cùng một kiểu enum, trình tự enum được định nghĩa | Khi khóa là enum cố định |
| `ConcurrentHashMap<K,V>` | Map hỗ trợ truy cập/cập nhật đồng thời | Khi **thực sự cần** map được cập nhật đồng thời, không phải chỉ vì stream chạy parallel |

Dạng bốn tham số cho quyền chọn Map:

```java
Map<String, Integer> byTeam = people.stream()
        .collect(Collectors.toMap(
                Person::team,
                Person::score,
                Integer::sum,
                LinkedHashMap::new));
```

Cần đặt trong phương thức có import `Map`, `LinkedHashMap`, `Collectors` và lớp `Person`. `LinkedHashMap::new` là **map factory**. Nếu muốn sắp theo khóa: thay bằng `TreeMap::new`. Nếu không quan tâm kiểu cụ thể, có thể dùng overload ba tham số; API không hứa map mặc định luôn là `HashMap`, ngay cả khi một triển khai thường trả loại đó.

**Quan trọng với LinkedHashMap:** nó giữ **thứ tự chèn vào map**, không biến khóa trùng thành nhiều entry. Khi gặp khóa `"A"` lần hai và gộp giá trị, entry của `"A"` không tự tạo một vị trí mới ở cuối theo chế độ insertion-order mặc định. Muốn lưu **tất cả** các bản ghi với khóa `"A"`, phải dùng danh sách giá trị hoặc một cấu trúc khác.

## 7. Chọn TreeMap: thứ tự khóa và comparator có thể thay đổi “trùng khóa”

`TreeMap` phân biệt khóa dựa vào **comparator/natural ordering**. Hai khóa `a`, `b` được xem là tương đương trong TreeMap khi `compare(a,b) == 0`, kể cả khi `a.equals(b)` là `false`.

Ví dụ:

```java
Map<String, Integer> caseInsensitive =
        List.of("java", "Java").stream()
            .collect(Collectors.toMap(
                s -> s,
                String::length,
                Integer::sum,
                () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)));
```

Đây là các lệnh trong phương thức có import `Map`, `List`, `TreeMap`, `Collectors`. Dưới `String.CASE_INSENSITIVE_ORDER`, `"java"` và `"Java"` có comparator bằng `0`, do đó **cùng khóa đối với TreeMap**. Kết quả chỉ có một entry `{java=8}` trong lần chạy Java 17 của chương trình minh họa.

Ngược lại, `new TreeMap<>()` với thứ tự tự nhiên phân biệt chữ hoa/thường; hai khóa ấy có thể tồn tại riêng. Vì vậy **định nghĩa khóa trùng không chỉ nằm ở hàm `keyMapper` mà còn ở quy tắc so sánh khóa của Map**.

Khi dùng comparator không nhất quán với `equals`, hành vi của `TreeMap` vẫn theo comparator đối với thao tác tìm khóa, nhưng có thể khác trực giác về `Map`/set equality. Cần tài liệu hóa lựa chọn comparator, nhất là nếu dữ liệu được trao đổi với `HashMap` hoặc JSON.

## 8. Chương trình Java 17 đầy đủ: trùng khóa và các chính sách gộp

Lưu toàn bộ nội dung sau vào `ToMapDuplicateKeysDemo.java`:

```java
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;

public class ToMapDuplicateKeysDemo {
    record Person(String name, String team, int score) {}
    public static void main(String[] args) {
        List<Person> people = List.of(
            new Person("An", "A", 10),
            new Person("Binh", "B", 20),
            new Person("Chi", "A", 15),
            new Person("Dung", "B", 7));
        try {
            people.stream().collect(Collectors.toMap(Person::team, Person::name));
        } catch (IllegalStateException ex) {
            System.out.println("duplicate=" + ex.getClass().getSimpleName());
        }

        Map<String, Integer> totals = people.stream()
            .collect(Collectors.toMap(Person::team, Person::score, Integer::sum));
        System.out.println("totalsA=" + totals.get("A"));
        System.out.println("totalsB=" + totals.get("B"));

        Map<String, String> first = people.stream()
            .collect(Collectors.toMap(Person::team, Person::name,
                (oldValue, newValue) -> oldValue, LinkedHashMap::new));
        System.out.println("first=" + first);

        Map<String, String> last = people.stream()
            .collect(Collectors.toMap(Person::team, Person::name,
                (oldValue, newValue) -> newValue, LinkedHashMap::new));
        System.out.println("last=" + last);

        Map<String, String> merged = people.stream()
            .collect(Collectors.toMap(Person::team, Person::name,
                (a,b) -> a + "+" + b, TreeMap::new));
        System.out.println("mergedTree=" + merged);

        Map<String, List<String>> groups = people.stream()
            .collect(Collectors.groupingBy(Person::team,
                TreeMap::new, Collectors.mapping(Person::name, Collectors.toList())));
        System.out.println("groups=" + groups);

        Map<String, String> immutable = people.stream()
            .collect(Collectors.toUnmodifiableMap(Person::name, Person::team));
        System.out.println("immutableSize=" + immutable.size());
        try {
            immutable.put("New", "X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable=" + ex.getClass().getSimpleName());
        }

        Map<String, Integer> parallelTotals = people.parallelStream()
            .collect(Collectors.toMap(Person::team, Person::score,
                Integer::sum, TreeMap::new));
        System.out.println("parallelTotals=" + parallelTotals);

        Map<String, Integer> naturalSorted = people.stream().collect(
            Collectors.toMap(Person::name, Person::score,
                (a,b) -> a, TreeMap::new));
        System.out.println("naturalKeys=" + naturalSorted.keySet());

        Map<String, Integer> linkedOrder = people.stream().collect(
            Collectors.toMap(Person::name, Person::score,
                (a,b) -> a, LinkedHashMap::new));
        System.out.println("linkedKeys=" + linkedOrder.keySet());
    }
}
```

Chạy với JDK 17:

```bash
javac --release 17 -encoding UTF-8 ToMapDuplicateKeysDemo.java
java ToMapDuplicateKeysDemo
```

Đầu ra đã kiểm chứng:

```text
duplicate=IllegalStateException
totalsA=25
totalsB=27
first={A=An, B=Binh}
last={A=Chi, B=Dung}
mergedTree={A=An+Chi, B=Binh+Dung}
groups={A=[An, Chi], B=[Binh, Dung]}
immutableSize=4
unmodifiable=UnsupportedOperationException
parallelTotals={A=25, B=27}
naturalKeys=[An, Binh, Chi, Dung]
linkedKeys=[An, Binh, Chi, Dung]
```

Giải thích kết quả:

1. **`duplicate=IllegalStateException`:** overload hai tham số từ chối hai người cùng team.
2. **`totalsA=25`, `totalsB=27`:** gộp điểm bằng `Integer::sum` theo khóa team.
3. **`first` và `last`:** hai merge functions khác nhau. Vì đầu vào là List có encounter order và pipeline tuần tự, `first` giữ tên người xuất hiện trước cho mỗi team, `last` giữ người xuất hiện sau.
4. **`mergedTree`:** ghép tên vào chuỗi và dùng `TreeMap` để in khóa team theo thứ tự sắp xếp.
5. **`groups`:** muốn **giữ tất cả tên** trong mỗi team thì `groupingBy` + `mapping` thành danh sách phù hợp hơn.
6. **`immutableSize=4`:** `toUnmodifiableMap` khi key là tên đều khác nhau tạo map không chỉnh sửa được; thử `put` ném `UnsupportedOperationException`.
7. **`parallelTotals`:** phép cộng điểm tạo tổng theo team khi thu thập song song; Map kết quả được chọn là `TreeMap`.
8. **`naturalKeys` và `linkedKeys`:** ở dữ liệu này chúng trông giống nhau, nhưng nguyên nhân khác: TreeMap sắp khóa theo chữ cái, LinkedHashMap giữ thứ tự chèn. **Đừng suy ra hai loại Map có chung hợp đồng thứ tự.**

Chương trình chủ động **bắt lỗi trùng khóa để tiếp tục minh họa**. Trong ứng dụng mà khóa bắt buộc duy nhất, hãy coi ngoại lệ đó là lỗi dữ liệu cần được giải quyết, không mặc nhiên bắt rồi bỏ qua.

## 9. Khi nào dùng groupingBy() thay cho toMap()?

Nếu một khóa tương ứng **nhiều giá trị** và bạn cần giữ mọi bản ghi, cách tự viết merge function ghép list có thể phức tạp, đặc biệt trong parallel streams. Lúc đó `Collectors.groupingBy` thường rõ ý định hơn:

```java
Map<String, List<String>> peopleByTeam = people.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                TreeMap::new,
                Collectors.mapping(Person::name, Collectors.toList())));
```

Đây là các câu lệnh minh họa trong phương thức với record `Person` và import `Map`, `List`, `TreeMap`, `Collectors`. Kết quả ở dữ liệu chương trình chính: `{A=[An, Chi], B=[Binh, Dung]}`.

Chọn phương án theo **kiểu dữ liệu đích**:

| Mục tiêu | Collector đề xuất |
| --- | --- |
| Mỗi khóa phải duy nhất, trùng là lỗi | `toMap(key, value)` |
| Mỗi khóa lấy một giá trị bằng chính sách chọn | `toMap(key, value, merge)` |
| Mỗi khóa có tổng số/điểm | `toMap(key, number, Integer::sum)` hoặc `groupingBy(key, summingInt(...))` |
| Mỗi khóa có danh sách giá trị | `groupingBy(key, mapping(value, toList()))` |
| Muốn sắp theo khóa | Dùng `TreeMap::new` trong collector có mapFactory |
| Muốn Map bất biến, khóa duy nhất | `toUnmodifiableMap(key, value)` |

`groupingBy` không phải cách “tự động loại trùng”. Nó **nhóm toàn bộ các phần tử** theo khóa; số phần tử trong mỗi List có thể lớn hơn một. Nếu bạn chỉ cần một tổng, dùng reducer trực tiếp có thể tránh tạo các List không cần thiết.

## 10. EnumMap và khóa enum

Khi khóa là một enum, `EnumMap` có thể mang lại cách lưu trữ phù hợp và thứ tự iteration theo **thứ tự khai báo các hằng enum**:

```java
enum Level { LOW, MEDIUM, HIGH }

EnumMap<Level, Integer> levels = tickets.stream()
    .collect(Collectors.toMap(
        Ticket::level, Ticket::points, Integer::sum,
        () -> new EnumMap<>(Level.class)));
```

Đây là các dòng minh họa cần nằm trong lớp có enum `Level`, record `Ticket` phù hợp và import `EnumMap`, `Collectors`. Ví dụ đầy đủ ở mục 11 định nghĩa các kiểu này. Việc chỉ định `Level.class` cho factory làm rõ kiểu enum mà Map sử dụng.

Không chọn `EnumMap` cho một khóa `String` hoặc `Integer`; khóa bắt buộc thuộc kiểu enum phù hợp. `EnumMap` không chấp nhận **null key**. Nếu nghiệp vụ có trường hợp khóa chưa xác định, hãy xử lý trước khi thu thập thay vì dựa vào hành vi ngẫu nhiên.

## 11. Ví dụ Java 17 đầy đủ: EnumMap, comparator, null merge và groupingBy

Tạo file `MapTypeChoiceDemo.java`:

```java
import java.util.*;
import java.util.stream.Collectors;

public class MapTypeChoiceDemo {
    enum Level { LOW, MEDIUM, HIGH }
    record Ticket(Level level, int points) {}

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
            new Ticket(Level.LOW, 3),
            new Ticket(Level.HIGH, 7),
            new Ticket(Level.LOW, 4));

        EnumMap<Level, Integer> levels = tickets.stream()
            .collect(Collectors.toMap(Ticket::level, Ticket::points,
                Integer::sum, () -> new EnumMap<>(Level.class)));
        System.out.println("enumMap=" + levels);
        System.out.println("enumType=" + (levels instanceof EnumMap));

        Map<String, Integer> caseSensitive = List.of("java","Java").stream()
            .collect(Collectors.toMap(s -> s, String::length,
                (a,b)->a, TreeMap::new));
        System.out.println("caseSensitiveSize=" + caseSensitive.size());

        Map<String, Integer> caseInsensitive = List.of("java","Java").stream()
            .collect(Collectors.toMap(s -> s, String::length,
                Integer::sum, () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)));
        System.out.println("caseInsensitive=" + caseInsensitive);

        Map<String, Integer> mergedNull = List.of("x", "x").stream()
            .collect(Collectors.toMap(s -> s, s -> 1,
                (a,b) -> null, LinkedHashMap::new));
        System.out.println("nullMergeRemoves=" + mergedNull);

        Map<String, List<Integer>> multiValue = List.of(1,2,3,4).stream()
            .collect(Collectors.groupingBy(n -> n % 2 == 0 ? "even":"odd",
                LinkedHashMap::new, Collectors.toList()));
        System.out.println("multiValue=" + multiValue);

        System.out.println("type=" + levels.getClass().getSimpleName());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 MapTypeChoiceDemo.java
java MapTypeChoiceDemo
```

Đầu ra đã kiểm chứng:

```text
enumMap={LOW=7, HIGH=7}
enumType=true
caseSensitiveSize=2
caseInsensitive={java=8}
nullMergeRemoves={}
multiValue={odd=[1, 3], even=[2, 4]}
type=EnumMap
```

Điểm nổi bật:

- Hai ticket có khóa `LOW` được cộng điểm `3+4=7`; ticket `HIGH` có `7`; `EnumMap` iterates theo thứ tự khai báo `LOW, MEDIUM, HIGH` (khóa `MEDIUM` không có nên không in).
- Natural `TreeMap` xem `java` và `Java` là hai khóa khác nhau; comparator bỏ qua hoa/thường khiến chúng **trùng khóa** và được cộng thành `8`.
- Merge function trả `null` làm mapping bị **loại bỏ** theo ngữ nghĩa của `Map.merge`. Trường hợp hai khóa `"x"` và hàm `(a,b) -> null` thu được map rỗng. Đây là một tính chất cần biết để tránh lỗi, **không khuyến nghị dùng như quy tắc xóa dữ liệu ngầm**.
- `groupingBy` cùng `LinkedHashMap::new` thể hiện cách giữ danh sách nhóm `odd`, `even` trong ví dụ tuần tự.

Một phản ví dụ dễ bỏ sót: nếu ba bản ghi liên tiếp có cùng khóa và merge trả `null` sau lần va chạm thứ hai, bản ghi thứ ba có thể tạo lại mapping mới. Do đó `(a,b)->null` **không phải** một cơ chế “xóa vĩnh viễn mọi khóa trùng”.

## 12. Null key, null value và null merge result

Ba chuyện khác nhau:

1. **Khóa `null`:** hỗ trợ hay không phụ thuộc Map cụ thể và collector; `HashMap` chấp nhận null key nhưng `TreeMap` theo natural order thường không và `EnumMap` không. Các collector cũng có thể áp đặt ràng buộc khác. Không nên dựa vào `null` key nếu chưa xác định rõ hợp đồng.
2. **Giá trị `null` từ `valueMapper`:** các triển khai `Collectors.toMap` dùng cơ chế merge/kiểm tra có thể ném `NullPointerException`; `toUnmodifiableMap` **không cho phép null key/value** theo hợp đồng. Nếu giá trị có thể vắng mặt, hãy `filter` hoặc dùng đại diện phi null như `Optional`/record phù hợp.
3. **Giá trị trả về `null` từ merge function:** theo `Map.merge`, khi remapping function trả `null`, mapping hiện tại **bị xóa**, khác với việc gán `null` làm giá trị map.

Có thể thấy ba khái niệm này khác nhau ngay cả khi kết quả trong debugger đều có chữ “null”. Để rõ ý định, hãy kiểm tra null ở ranh giới chuyển đổi dữ liệu và hạn chế side effects.

Ví dụ tốt hơn khi thiếu mã team: quyết định mã team bắt buộc và fail-fast bằng validation; hoặc lọc record chưa có mã; hoặc gán một mã đại diện phi null có ý nghĩa rõ ràng. Đừng mặc định khóa null là một nhóm “khác” an toàn trên mọi implementation.

## 13. toUnmodifiableMap() và yêu cầu bất biến

Từ Java 10, `Collectors.toUnmodifiableMap` tạo Map không hỗ trợ thao tác sửa đổi:

```java
Map<String, Integer> scores = people.stream()
        .collect(Collectors.toUnmodifiableMap(
                Person::name, Person::score));
```

Đây là các lệnh minh họa trong phương thức với `people` và `Person` phù hợp. Khi các tên duy nhất, collector trả map không chỉnh sửa được; `scores.put("New", 42)` sẽ ném `UnsupportedOperationException`.

Điểm cần ghi nhớ:

- Bản hai tham số của `toUnmodifiableMap` vẫn **báo lỗi khi trùng khóa**.
- Bản ba tham số có thể nhận merge function để xử lý trùng khóa.
- `toUnmodifiableMap` **không chấp nhận null key/value**.
- Không nên giả định một thứ tự iteration cụ thể cho kết quả.
- Bất biến cấu trúc Map **không làm các object value mutable tự bất biến**; nếu `V` là đối tượng có thể thay đổi, bản thân đối tượng vẫn có thể bị sửa qua tham chiếu khác.

`Map.copyOf(map)` cũng tạo một Map không chỉnh sửa được từ map đã có với ràng buộc null; nhưng việc chọn một collector sớm thường rõ hơn nếu bạn muốn kết quả bất biến ngay sau `collect`.

## 14. Parallel stream, combiner và ConcurrentMap

Khi gọi:

```java
Map<String, Integer> totals = people.parallelStream()
        .collect(Collectors.toMap(
                Person::team,
                Person::score,
                Integer::sum,
                TreeMap::new));
```

Trong bối cảnh ví dụ hoàn chỉnh, kết quả `{A=25, B=27}` đã được kiểm thử. Phép cộng `Integer::sum` thuận tiện vì kết hợp được và không phụ thuộc thứ tự với những số nhỏ không gây vấn đề tràn.

**Nhưng `parallelStream()` không tự biến map đích thành một Map cập nhật đồng thời.** Collector `toMap` thông thường là collector **không concurrent**; framework có thể tạo map cục bộ rồi kết hợp thông qua combiner. Đây có thể là công việc tốn chi phí khi có nhiều khóa, vì phải merge các map trung gian.

Nếu thật sự muốn collector concurrent, Java cung cấp `Collectors.toConcurrentMap`. Nó tạo `ConcurrentMap` theo hợp đồng, thường dùng với pipeline có thể xử lý song song, nhưng **không bảo đảm thứ tự chèn** theo encounter order như `LinkedHashMap`.

Lưu ý:

- Không tự ý chuyển `toMap` sang `toConcurrentMap` nếu nghiệp vụ cần “giữ giá trị đầu tiên/cuối cùng” theo thứ tự xuất hiện.
- Merge function vẫn phải tuân thủ hợp đồng thích hợp và tránh side effects.
- `ConcurrentHashMap` không chấp nhận null key/value; chọn kiểu Map theo ràng buộc thật.
- Một Map thread-safe không làm các bước **ngoài Map** (gửi email, DB, tính toán mutable shared state) trở thành thread-safe hay exactly-once.
- Đừng tăng tốc mặc định bằng parallel: với dữ liệu nhỏ, số khóa ít và chi phí merge cao, tuần tự có thể hiệu quả hơn.

## 15. Hiểu đúng thứ tự duyệt Map

Có ba khái niệm khác nhau dễ bị trộn lẫn:

1. **Encounter order của Stream**: thứ tự phần tử nguồn do pipeline xác định.
2. **Thứ tự chèn của LinkedHashMap**: thứ tự một khóa được thêm vào map lần đầu theo chế độ mặc định.
3. **Thứ tự khóa của TreeMap**: được quyết định bởi comparator/natural ordering, không phải thứ tự xuất hiện trong stream.

Ví dụ source tuần tự `["B", "A", "C"]`: đưa vào `LinkedHashMap` thường cho key order `B, A, C`; đưa vào `TreeMap` theo natural ordering cho `A, B, C`. `HashMap` không hứa thứ tự nào, kể cả khi một lần chạy nhìn tình cờ trùng thứ tự chèn.

Khi cần *vừa* chọn bản ghi mới nhất *vừa* duy trì key order, hãy tách hai quyết định: merge function chọn theo `timestamp` (hoặc tiêu chí có total ordering), còn map factory quyết định thứ tự duyệt map kết quả. Đừng dùng `newValue` như từ đồng nghĩa với “mới nhất”.

Một Map có thứ tự không tự bảo đảm **giá trị của từng khóa được gộp theo đúng thứ tự mong muốn** trong những chế độ xử lý khác. Nếu bạn ghép chuỗi hoặc danh sách theo thứ tự, hãy kiểm tra encounter order và lựa chọn collector/parallel có phù hợp không.

## 16. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `toMap(key,value)` với khóa thực tế không duy nhất | `IllegalStateException` | Định nghĩa merge hoặc dùng `groupingBy` |
| Nghĩ `toMap` mặc định “giữ phần tử cuối” | Không đúng với overload hai tham số | Chỉ định chính sách rõ |
| Dùng `(a,b)->b` để chọn bản ghi mới nhất | Không xét timestamp/ưu tiên thực tế | So sánh trường nghiệp vụ |
| Dùng merge function có side effect | Số lần/thứ tự gọi phụ thuộc pipeline | Hàm gộp thuần, đúng hợp đồng |
| Dùng phép trừ làm merge trong parallel | Phụ thuộc cách nhóm | Chọn phép gộp có tính kết hợp |
| Nghĩ `HashMap` giữ thứ tự đầu vào | Không có cam kết iteration order | `LinkedHashMap` nếu cần insertion order |
| Nghĩ `TreeMap` chỉ nhận khóa trùng theo `equals()` | Comparator quyết định tính tương đương khóa | Kiểm tra `compare(a,b)==0` |
| Trả `null` từ merge để “giữ null” | `Map.merge` có thể **xóa mapping** | Trả kết quả phi null, xử lý xóa tường minh |
| Mong `toMap` hỗ trợ null value mọi nơi | Có thể `NullPointerException` | Làm sạch dữ liệu trước |
| Dùng `EnumMap` với khóa không phải enum | Không phù hợp kiểu khóa | Chọn Map phù hợp hoặc đổi mô hình khóa |
| Nghĩ `toUnmodifiableMap` làm value mutable trở thành bất biến | Chỉ bảo vệ cấu trúc Map | Dùng value type bất biến hoặc defensive copy |
| Dùng `toConcurrentMap` và vẫn dựa vào thứ tự | Concurrent collector không giữ insertion order | Thiết kế order riêng, tránh phụ thuộc thứ tự concurrent |

## 17. Bài tập thực hành có đáp án

**Bài 1 — Nhận biết trùng khóa.** Với hai người `("An","A")` và `("Chi","A")`, lệnh `toMap(Person::team,Person::name)` có hợp lệ khi chạy không?

Đáp án: **Không**, vì cả hai khóa đều là `"A"`. Overload hai tham số ném `IllegalStateException`.

**Bài 2 — Tính tổng.** Có điểm theo team: `A:10`, `B:20`, `A:15`. Viết merge function để Map có `A=25`, `B=20`.

Đáp án: `Integer::sum` với `toMap(Person::team,Person::score,Integer::sum)` nếu đầu vào là `Person` như chương trình.

**Bài 3 — Chọn thứ tự khóa.** Cần iteration order của khóa theo alphabet, không theo vị trí xuất hiện. Chọn map factory nào?

Đáp án: `TreeMap::new` với khóa `String` và natural ordering. Nếu cần sắp không phân biệt hoa/thường, truyền factory tạo `TreeMap<>(String.CASE_INSENSITIVE_ORDER)`, đồng thời hiểu nó có thể coi một số khóa là trùng.

**Bài 4 — Giữ thứ tự chèn.** Cần duyệt các khóa theo thứ tự được thêm lần đầu trong một pipeline tuần tự. Chọn loại Map nào?

Đáp án: `LinkedHashMap::new`, với insertion-order mặc định. Khóa trùng thay/merge giá trị nhưng không tự tạo một entry thứ hai.

**Bài 5 — Giữ mọi phần tử.** Với team `A` có hai người, vì sao `groupingBy(Person::team, mapping(Person::name,toList()))` thích hợp hơn `toMap(...,(old,new)->old)`?

Đáp án: `groupingBy` giữ **cả hai tên**; merge giữ đầu chỉ cho một người và mất thông tin bản ghi còn lại.

**Bài 6 — Comparator.** `"java"` và `"Java"` có thể thành trùng khóa trong TreeMap không?

Đáp án: **Có**, nếu dùng `String.CASE_INSENSITIVE_ORDER`. TreeMap dùng kết quả comparator bằng `0` để coi hai khóa tương đương.

**Bài 7 — Merge trả null.** Với `toMap(s->s,s->1,(a,b)->null,LinkedHashMap::new)` trên hai chuỗi `"x"`, kết quả là gì?

Đáp án: Map rỗng `{}` trong chương trình kiểm thử, vì merge trả `null` khiến entry đang tồn tại bị xóa. Không dùng cách này nếu chỉ muốn “giữ một giá trị null”.

**Bài 8 — Parallel.** Một merge function `(a,b)->a-b` có phù hợp để tổng hợp song song một cách ổn định không?

Đáp án: **Không** theo nghĩa reduction cần kết quả không phụ thuộc cách nhóm, vì phép trừ không có tính kết hợp. Chọn một phép gộp phù hợp hoặc chuyển sang một thiết kế collector khác.

**Bài 9 — Enum.** Khóa của bạn là enum `Level` và cần Map tối ưu cho enum, duyệt theo thứ tự khai báo. Chọn gì?

Đáp án: `EnumMap<Level,V>`, truyền factory `() -> new EnumMap<>(Level.class)` vào overload bốn tham số.

## 18. Checklist trước khi đưa vào hệ thống

1. Xác minh **tính duy nhất** của key; nếu trùng là dữ liệu sai, dùng overload không merge để fail-fast.
2. Nếu trùng là hợp lệ, viết ra **chính sách gộp nghiệp vụ**; nó nhận hai **value đã ánh xạ**, không nhận hai phần tử nguồn gốc.
3. Xác định có cần **giữ tất cả giá trị** không; nếu có, xem `groupingBy` + downstream collector.
4. Xác định **Map implementation**: `HashMap` khi không cần thứ tự, `LinkedHashMap` khi cần thứ tự chèn, `TreeMap` khi cần thứ tự khóa, `EnumMap` cho enum.
5. Kiểm tra **comparator**: khi so sánh trả 0, TreeMap xem như khóa tương đương, dù `equals` khác.
6. Xử lý **null key/value** và không để merge vô tình trả null xóa mapping.
7. Nếu chạy **parallel**, kiểm tra tính kết hợp, side effects, thứ tự và chi phí combiner.
8. Nếu cần bất biến kết quả, cân nhắc `toUnmodifiableMap`/immutable value objects và hiểu rõ hợp đồng null.
9. Kiểm thử ít nhất: **không có trùng**, **hai khóa trùng**, **ba khóa trùng**, **trùng khi giá trị bằng nhau**, **trùng do comparator**, **thứ tự chèn vs sắp xếp**, và **parallel** khi áp dụng.

## 19. Ghi nhớ

- `Collectors.toMap(keyMapper,valueMapper)` **ném IllegalStateException** khi trùng khóa; không tự chọn giá trị đầu/cuối.
- Overload ba/bốn tham số nhận **merge function** để định nghĩa cách gộp; hàm đó nên thuần, kết hợp được và phù hợp nhu cầu xử lý song song.
- `LinkedHashMap` giữ **thứ tự chèn**, `TreeMap` sắp theo **khóa**, `EnumMap` phù hợp **khóa enum**; overload mặc định không cam kết một implementation cụ thể.
- `TreeMap` xác định khóa tương đương bằng comparator, điều này có thể **tạo va chạm mới**.
- `groupingBy` là lựa chọn tự nhiên nếu cần **một khóa → nhiều giá trị**; không mất dữ liệu vì chỉ chọn đầu hoặc cuối.
- Merge function trả `null` có thể **xóa mapping**; không nên làm như vậy nếu không có quy tắc rõ.
- `toUnmodifiableMap` bảo vệ cấu trúc Map, không tự làm bất biến object value và không chấp nhận null key/value.
- Khi xử lý concurrent/parallel, đừng đánh đổi tính đúng đắn về thứ tự hoặc quy tắc chọn giá trị chỉ để tăng tốc.

Tài liệu chính thống: [Java SE 17 Collectors.toMap/toUnmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html), [Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)), [LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html), [TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html), [EnumMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html).
