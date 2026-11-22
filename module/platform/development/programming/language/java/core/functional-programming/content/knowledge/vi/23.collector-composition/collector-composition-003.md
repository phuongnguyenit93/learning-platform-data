# Collectors.mapping(): biến đổi phần tử bên trong từng nhóm

## 1. Mục tiêu và bài toán

Khi xử lý dữ liệu bằng Java Stream, đôi khi ta không chỉ muốn **nhóm đối tượng theo khóa**, mà còn muốn **biến đổi dữ liệu được giữ trong mỗi nhóm**. Ví dụ từ danh sách nhân viên, cần một kết quả:

```text
Dev → ["Lan", "An", "Binh"]
Ops → ["Minh", "Hoa"]
```

Nguồn dữ liệu ban đầu là `Employee(name, team, active)`, nhưng giá trị trong từng nhóm chỉ còn là `String` tên nhân viên. Nếu viết `stream().map(Employee::name)` quá sớm, có thể mất luôn thuộc tính `team` dùng để tạo khóa nhóm.

Giải pháp thường gặp là **downstream collector** `Collectors.mapping(mapper, downstream)`, đặt **bên trong** `Collectors.groupingBy(...)`. Bằng cách này:

1. Bộ collector ngoài `groupingBy` vẫn nhận đối tượng `Employee` để quyết định nó thuộc nhóm nào.
2. Khi một phần tử đã được chuyển tới nhóm, `mapping` áp dụng hàm biến đổi, chẳng hạn `Employee::name`.
3. Collector con như `toList()`, `toSet()`, `joining()` hoặc `counting()` thu các giá trị **sau khi biến đổi** thành kết quả của từng nhóm.

Sơ đồ:

```text
                      Employee
                         │
                         ▼
                 groupingBy(team)
                  /            \
                 ▼              ▼
               Dev             Ops
                │               │
          mapping(name)    mapping(name)
                │               │
                ▼               ▼
             toList()         toList()
                │               │
                ▼               ▼
           List<String>     List<String>
```

Đây là một ứng dụng quan trọng của **collector kết hợp**: collector ngoài điều khiển cấu trúc nhóm; collector trong quyết định cách xử lý và thu phần tử của **mỗi** nhóm.

## 2. Chữ ký và cơ chế hoạt động của `Collectors.mapping`

API Java SE cung cấp phương thức static:

```java
public static <T, U, A, R> Collector<T, ?, R> mapping(
        Function<? super T, ? extends U> mapper,
        Collector<? super U, A, R> downstream)
```

Đây là chữ ký API để nghiên cứu, không phải một chương trình Java độc lập.

Ý nghĩa của các kiểu:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `T` | Kiểu phần tử **đi vào** collector `mapping`, ví dụ `Employee` |
| `U` | Kiểu phần tử **sau khi biến đổi**, ví dụ `String` |
| `A` | Kiểu tích lũy nội bộ của downstream collector; thường không cần tự khai báo |
| `R` | Kiểu **kết quả cuối cùng** của downstream, ví dụ `List<String>` hoặc `String` |
| `mapper` | Hàm biến đổi một `T` thành một `U` |
| `downstream` | Collector xử lý các giá trị `U` đã được biến đổi |

Ví dụ:

```java
Collectors.mapping(Employee::name, Collectors.toList())
```

Với `Employee::name` biến `Employee → String`, collector ở trên nhận `Employee` và trả kết quả dạng `List<String>`. Khi lồng vào `groupingBy(Employee::team, ...)`, kết quả cuối cùng thường là `Map<String, List<String>>`.

**Điểm mấu chốt:** `mapping` **không tự nhóm**. Nó chỉ biến đổi đầu vào rồi chuyển cho downstream. Việc phân nhóm do `groupingBy` thực hiện, phân thành hai vai trò độc lập.

## 3. Ví dụ Java 17 đầy đủ: lấy tên theo từng phòng ban

Lưu thành tệp `MappingGroupsDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MappingGroupsDemo {
    record Employee(String name, String team, boolean active) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("Lan", "Dev", true),
                new Employee("Minh", "Ops", false),
                new Employee("An", "Dev", true),
                new Employee("Hoa", "Ops", true),
                new Employee("Binh", "Dev", false)
        );

        Map<String, List<String>> namesByTeam = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                ));

        Map<String, String> joinedNamesByTeam = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.joining(" | ")
                        )
                ));

        System.out.println("teams=" + namesByTeam);
        System.out.println("joined=" + joinedNamesByTeam);
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac MappingGroupsDemo.java
java MappingGroupsDemo
```

Kết quả chính xác:

```text
teams={Dev=[Lan, An, Binh], Ops=[Minh, Hoa]}
joined={Dev=Lan | An | Binh, Ops=Minh | Hoa}
```

Giải thích từng tầng:

- `employees.stream()` phát ra năm đối tượng `Employee` theo thứ tự của `List`.
- `Employee::team` là **classifier**: mỗi đối tượng được chuyển vào nhóm khóa `Dev` hoặc `Ops`.
- `TreeMap::new` tạo Map có thứ tự khóa tăng dần, nên ví dụ hiển thị `Dev` trước `Ops`. Nếu dùng overload `groupingBy(classifier, downstream)` mặc định, không nên dựa vào thứ tự khóa khi in toàn bộ Map.
- Sau khi chọn nhóm, `mapping(Employee::name, toList())` lấy tên rồi thêm vào danh sách của nhóm đó. Phần tử đầu vào của `groupingBy` vẫn là `Employee`.
- Với collector khác, `mapping(Employee::name, joining(" | "))` trả **một String** cho mỗi khóa, không phải List.
- Những nhân viên trùng tên sẽ vẫn có thể xuất hiện lặp lại trong danh sách hoặc chuỗi vì `toList` và `joining` không tự loại trùng.

Kiểu kết quả cho thấy rõ sự khác nhau:

```text
groupingBy(team, mapping(name, toList()))
    → Map<String, List<String>>

groupingBy(team, mapping(name, joining(" | ")))
    → Map<String, String>
```

Mỗi lần gọi `collect` ở chương trình đều dùng một stream mới, tránh lỗi dùng lại Stream đã tiêu thụ.

## 4. Phân biệt `stream.map(...)` với `Collectors.mapping(...)`

Cả hai đều sử dụng một hàm biến đổi, nhưng **vị trí trong quá trình thu thập** khác nhau.

### 4.1. `map` ở upstream: biến đổi cả Stream trước khi collector ngoài nhìn thấy

```java
employees.stream()
        .map(Employee::name)
        .collect(Collectors.toList());
```

Sau `map(Employee::name)`, mỗi phần tử của Stream là `String`. Nếu tiếp tục dùng:

```java
// Phản ví dụ có chủ đích: không biên dịch.
employees.stream()
        .map(Employee::name)
        .collect(Collectors.groupingBy(Employee::team));
```

thì sẽ không hợp lệ về kiểu: `groupingBy` hiện nhận `String`, nhưng `Employee::team` là method reference dành cho `Employee`.

### 4.2. `mapping` ở downstream: classifier vẫn nhận đầu vào gốc

```java
employees.stream()
        .collect(Collectors.groupingBy(
                Employee::team,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        ));
```

Ở đây, `groupingBy` chọn khóa dựa trên `Employee` trước khi chuyển **giá trị của nhóm** cho `mapping`. Vì vậy không mất thuộc tính `team` khi cần tạo nhóm.

### 4.3. Có thể tạo DTO để `map` trước `groupingBy` hay không?

Có. Nếu phép biến đổi upstream **giữ lại đầy đủ khóa cần nhóm**, hai cách có thể cùng tạo kết quả theo một số quy tắc nghiệp vụ. Ví dụ DTO `NameByTeam(team, name)` vẫn giữ team; dùng `map(e -> new NameByTeam(e.team(), e.name()))` rồi `groupingBy(NameByTeam::team, mapping(NameByTeam::name, toList()))` có thể cho kết quả tên tương tự.

Tuy nhiên việc tạo object trung gian và chuyển kiểu không cần thiết có thể làm pipeline dài hơn. Khi đã có đầu vào gốc cùng classifier, dùng downstream `mapping` thường diễn đạt trực tiếp hơn: **giữ khóa gốc, chỉ biến đổi dữ liệu được thu trong nhóm**.

**Quy tắc:** dùng `Stream.map` khi mọi thao tác về sau nên nhìn thấy kiểu đã biến đổi; dùng `Collectors.mapping` khi chỉ downstream collector cần kiểu biến đổi, còn collector bao quanh vẫn cần phần tử gốc.

## 5. Các downstream collector thường kết hợp với `mapping`

| Mục đích trong mỗi nhóm | Downstream | Kiểu giá trị của Map |
| --- | --- | --- |
| Lưu mọi tên | `mapping(Employee::name, toList())` | `List<String>` |
| Lưu tên khác nhau | `mapping(Employee::name, toSet())` | `Set<String>` |
| Tên không trùng, có thứ tự | `mapping(Employee::name, toCollection(TreeSet::new))` | `TreeSet<String>` |
| Ghép tên thành chuỗi | `mapping(Employee::name, joining(", "))` | `String` |
| Đếm số phần tử sau biến đổi | `mapping(Employee::name, counting())` | `Long` |
| Kiểm tra tên dài nhất | `mapping(Employee::name, maxBy(comparingInt(String::length)))` | `Optional<String>` |

Các collector ở bảng cần được gọi qua `Collectors` (ví dụ `Collectors.mapping(...)`, `Collectors.counting()`), hoặc import static thích hợp. Đó là **các biểu thức minh họa**, không phải một chương trình độc lập.

Quan trọng:

- `toList()` thường hữu ích nếu muốn giữ nhiều phần tử và thứ tự encounter order trong một pipeline ordered.
- `toSet()` loại phần tử trùng theo equality, nhưng **không bảo đảm loại Set cụ thể hay thứ tự duyệt**. Nếu cần danh sách tên có thứ tự rõ ràng, có thể dùng `toCollection(TreeSet::new)` với comparator/natural order thích hợp.
- `joining(", ")` chỉ áp dụng khi các giá trị do mapper phát ra tương thích `CharSequence`. Nếu mapper trả `Integer` hoặc một object, cần biến đổi sang String.
- `counting()` ở sau `mapping` thường không giúp ích khi mapper không lọc phần tử: nó đếm phần tử được chuyển, nhưng giá trị chuyển đổi không được dùng. Nếu chỉ cần đếm nhân viên mỗi nhóm, `groupingBy(Employee::team, counting())` đơn giản hơn.
- Collector như `maxBy(...)` trả `Optional` để biểu diễn trường hợp không có giá trị trong một nhóm sau các phép lọc có liên quan. Đừng gọi `get()` mà không xét nhóm rỗng.

Bản thân `mapping` **không lọc** và **không loại trùng**. Các tính chất đó do mapper và downstream collector quyết định.

## 6. Ví dụ: chuẩn hóa tên và loại trùng trong từng nhóm

Đặt yêu cầu: tên trong từng thành phố phải được viết hoa, không trùng, sắp tăng dần. Một kết hợp hữu ích là:

```java
Collectors.mapping(
        item -> item.name().toUpperCase(Locale.ROOT),
        Collectors.toCollection(TreeSet::new)
)
```

Ở đây:

1. `mapping` chuyển mỗi tên sang dạng chữ hoa trong phạm vi nhóm tương ứng.
2. `toCollection(TreeSet::new)` giữ tên dưới dạng tập hợp có thứ tự, loại trùng theo comparator/natural order của String.
3. `groupingBy` chọn khóa thành phố từ bản ghi gốc.

Lưu chương trình `MappingSetDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class MappingSetDemo {
    record Person(String city, String name) {}

    public static void main(String[] args) {
        List<Person> people = List.of(
                new Person("Hanoi", "Lan"),
                new Person("DaNang", "Minh"),
                new Person("Hanoi", "An"),
                new Person("DaNang", "Hoa"),
                new Person("Hanoi", "Lan")
        );

        Map<String, TreeSet<String>> normalized = people.stream()
                .collect(Collectors.groupingBy(
                        Person::city,
                        TreeMap::new,
                        Collectors.mapping(
                                p -> p.name().toUpperCase(Locale.ROOT),
                                Collectors.toCollection(TreeSet::new)
                        )
                ));

        System.out.println(normalized);
    }
}
```

Biên dịch/chạy:

```bash
javac MappingSetDemo.java
java MappingSetDemo
```

Output:

```text
{DaNang=[HOA, MINH], Hanoi=[AN, LAN]}
```

Ở nhóm Hanoi có hai bản ghi tên `Lan`. Sau biến đổi thành `LAN` rồi đưa vào TreeSet, chỉ còn một phần tử `LAN`. Nếu thay downstream bằng `toList()`, hai tên `LAN` vẫn xuất hiện; nếu thay bằng `toSet()`, việc loại trùng vẫn diễn ra nhưng thứ tự khi in không được bảo đảm.

**Lưu ý locale:** `Locale.ROOT` cho chuyển đổi chữ hoa ổn định, không nhằm thực hiện sắp xếp từ vựng tiếng Việt theo quy tắc ngôn ngữ tự nhiên. Nếu nghiệp vụ yêu cầu collation địa phương hoặc chuẩn hóa Unicode, cần comparator/normalization riêng. Không cho rằng `TreeSet<String>` dùng natural order là thứ tự từ điển phù hợp mọi locale.

## 7. Kết hợp `filtering` và `mapping` trong từng nhóm

Một yêu cầu phổ biến là **vẫn giữ nhóm đã thấy, nhưng chỉ lấy tên của thành viên đang hoạt động**. Với Java 9+, `Collectors.filtering(predicate, downstream)` lọc các phần tử **trong downstream collector**, nên kết hợp được:

```java
Collectors.groupingBy(
        Employee::team,
        Collectors.filtering(
                Employee::active,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        )
)
```

Cần phân biệt hai vị trí lọc:

- **Lọc trước khi grouping:** `stream.filter(Employee::active).collect(groupingBy(...))`. Nếu không còn bản ghi nào của một team, khóa team đó **có thể không xuất hiện** trong kết quả.
- **Lọc trong downstream:** `stream.collect(groupingBy(team, filtering(active, mapping(name, toList()))))`. Bộ phân nhóm đã gặp team trước khi downstream từ chối bản ghi, nên nhóm đó có thể được giữ với danh sách rỗng.

Chương trình `MappingFilteringDemo.java` chứng minh khác biệt:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MappingFilteringDemo {
    record Employee(String name, String team, boolean active) {}

    public static void main(String[] args) {
        List<Employee> people = List.of(
                new Employee("Lan", "Dev", true),
                new Employee("An", "Dev", false),
                new Employee("Minh", "Ops", false),
                new Employee("Hoa", "QA", true)
        );

        Map<String, List<String>> filterBefore = people.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                ));

        Map<String, List<String>> filterWithin = people.stream()
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.filtering(
                                Employee::active,
                                Collectors.mapping(
                                        Employee::name,
                                        Collectors.toList()
                                )
                        )
                ));

        System.out.println("upstream=" + filterBefore);
        System.out.println("downstream=" + filterWithin);
    }
}
```

Biên dịch/chạy:

```bash
javac MappingFilteringDemo.java
java MappingFilteringDemo
```

Output:

```text
upstream={Dev=[Lan], QA=[Hoa]}
downstream={Dev=[Lan], Ops=[], QA=[Hoa]}
```

Giải thích: nhóm Ops có bản ghi Minh nhưng không hoạt động. Khi lọc trước, Minh bị loại trước khi `groupingBy` nhìn thấy team Ops nên không có khóa Ops. Khi lọc downstream, `groupingBy` nhìn thấy Ops và tạo nhóm, sau đó `filtering` không chuyển Minh cho `mapping`, dẫn đến danh sách rỗng.

Đây là lý do downstream `mapping` và `filtering` được thiết kế để **tổ hợp collector**, thay vì buộc tất cả thao tác diễn ra ở upstream.

**Chú ý thứ tự trong downstream:** `filtering(active, mapping(name, toList()))` có nghĩa kiểm tra `Employee::active` trước, sau đó chuyển `Employee → String`. Nếu đặt `mapping(Employee::name, filtering(Employee::active, toList()))` thì Predicate bên trong không còn nhận Employee mà nhận String, nên sai kiểu.

## 8. `partitioningBy` cũng có thể chứa `mapping`

Không chỉ `groupingBy`, `partitioningBy(predicate, downstream)` phân dữ liệu thành **hai nhánh true/false**, mỗi nhánh có collector riêng. Ví dụ:

```java
Map<Boolean, List<String>> namesByActive = employees.stream()
        .collect(Collectors.partitioningBy(
                Employee::active,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        ));
```

Đây là đoạn mã trong phương thức đã có `employees` kiểu `List<Employee>` và các import `Map`, `List`, `Collectors`.

- Khóa `true` chứa tên của nhân viên đang hoạt động.
- Khóa `false` chứa tên của nhân viên không hoạt động.
- `partitioningBy` cung cấp hai khóa `true` và `false` theo hợp đồng, ngay cả khi một nhánh không có phần tử.
- Không dựa vào thứ tự lặp của Map Boolean khi in trực tiếp; khi cần xuất kết quả có thứ tự cụ thể, truy cập `get(false)` / `get(true)` theo yêu cầu.

Với các nhóm theo khóa tùy ý, dùng `groupingBy`; khi chia đúng hai nhóm theo Predicate, `partitioningBy` có thể đơn giản hơn. Trong cả hai trường hợp, `mapping` vẫn biến đổi **phần tử trong collector con**, không thay đổi điều kiện chọn nhóm.

## 9. `mapping` và `flatMapping`: một giá trị so với nhiều giá trị

`Collectors.mapping(mapper, downstream)` gửi **một giá trị đầu ra từ mapper cho mỗi đầu vào**, dù giá trị đó có thể là một collection. Nếu mapper trả `List<String>`, downstream `toList()` sẽ tạo **List<List<String>>** trong nhóm, không tự làm phẳng.

Ví dụ:

```java
Collectors.mapping(
        Order::tags,
        Collectors.toList()
)
```

Giả sử `Order.tags()` trả `List<String>`; mỗi phần tử trong danh sách kết quả của nhóm là **một List tags của một Order**.

Nếu muốn gộp các tag **của mọi Order** thành một tập hợp, Java 9+ cung cấp `Collectors.flatMapping(mapperToStream, downstream)`. Ví dụ:

```java
Collectors.flatMapping(
        order -> order.tags().stream(),
        Collectors.toSet()
)
```

Nó chuyển mỗi Order thành **Stream<String>**, rồi gửi từng tag vào downstream, không giữ các list con. Về mặt kiểu:

```text
mapping(tags, toList()):
   Order → List<String> → List<List<String>> trong mỗi nhóm

flatMapping(tags.stream, toSet()):
   Order → Stream<String> → Set<String> trong mỗi nhóm
```

Hai API giải quyết hai ý định khác nhau. Nếu danh sách con có thể null, cần chọn chính sách xử lý rõ thay vì trực tiếp gọi `null.stream()`. Có thể dùng Stream rỗng để biểu diễn không có tag.

## 10. Đọc đúng kiểu generic của collector lồng nhau

Dưới đây là một chuỗi kiểu điển hình:

```text
Stream<Employee>
    └── collect(groupingBy(Employee::team,
                mapping(Employee::name, toList())))
        │
        ├── classifier: Employee → String
        ├── mapper:     Employee → String
        ├── downstream: Collector<String, ?, List<String>>
        └── kết quả:   Map<String, List<String>>
```

Dù classifier và mapper đều trả String trong ví dụ, **chúng có vai trò khác nhau**: classifier trả khóa map, mapper trả giá trị đưa vào collector con.

Có thể biến đổi sang kiểu số:

```java
Map<String, Integer> totalPoints = entries.stream()
        .collect(Collectors.groupingBy(
                Entry::team,
                Collectors.mapping(
                        Entry::points,
                        Collectors.reducing(0, Integer::sum)
                )
        ));
```

Đây là đoạn mã minh họa với kiểu `Entry` có `team()` trả String, `points()` trả int và collection `entries`. Kết quả của downstream reducing là Integer cho mỗi nhóm. Tuy vậy, khi phép tổng đơn giản, `Collectors.summingInt(Entry::points)` trực tiếp trong groupingBy thường ngắn gọn, tránh bước boxing và ý định rõ hơn:

```java
Map<String, Integer> totalPoints = entries.stream()
        .collect(Collectors.groupingBy(
                Entry::team,
                Collectors.summingInt(Entry::points)
        ));
```

Chọn collector nhỏ nhất diễn đạt đúng nghiệp vụ; không dùng `mapping` trong mọi phép toán chỉ vì có thể.

## 11. Bản chất thực thi, thứ tự và side effect

`mapping` không chạy ở thời điểm chỉ tạo biểu thức lambda hay tham chiếu tới collector. Khi terminal operation `collect(...)` được thực thi, framework đưa phần tử vào bộ tích lũy, tại đó mapper được áp dụng trước khi chuyển giá trị cho downstream.

Cần lưu ý:

- **Encounter order:** Với stream ordered và downstream thích hợp như `toList()`, thứ tự phần tử trong mỗi nhóm phản ánh thứ tự encounter của các phần tử thuộc nhóm đó. Nhưng thứ tự **khóa** do Map quyết định; `HashMap` mặc định không hứa key order.
- **Không tự sort:** `mapping(Employee::name, toList())` không sắp tên. Nếu muốn sắp đầu ra mỗi nhóm, có thể dùng `TreeSet` hoặc áp dụng một bước sắp xếp kết quả phù hợp sau collect.
- **Không tự loại trùng:** chỉ `toSet`, `TreeSet` hoặc một bước đặc tả khác mới có nhiệm vụ đó.
- **Không thay đổi nguồn:** mapper chỉ trả kết quả thì collector không sửa đối tượng gốc. Nhưng nếu lambda có side effect, vẫn có thể làm biến đổi trạng thái bên ngoài; phải tránh hành vi đó trừ khi thực sự có hợp đồng rõ.
- **Parallel stream:** collector có thể dùng nhiều bộ tích lũy nội bộ và kết hợp các kết quả. Không dựa vào thứ tự ghi log bên trong mapper; trạng thái mutable dùng chung có thể tạo race.
- **Exception:** Nếu mapper ném runtime exception, terminal `collect(...)` có thể thất bại; collector không tự nuốt lỗi hoặc trả giá trị dự phòng.
- **Checked exception:** `Function.apply` dùng trong `mapping` không khai báo checked exception. Nếu mapper cần gọi API ném checked exception, phải xử lý phù hợp hoặc thiết kế API khác; không thể để checked exception chưa xử lý thoát trực tiếp qua lambda.

Với nguồn dữ liệu cố định và mapper thuần túy, kết quả dễ kiểm thử hơn khi logic nhóm, biến đổi và collector con được tách rõ ràng.

## 12. Null và dữ liệu không hợp lệ

Một mapper **có thể trả null**; `Collectors.mapping` không tự động chuyển null thành “không có phần tử”. Hậu quả phụ thuộc downstream:

- Với `Collectors.joining(", ")`, một phần tử null có thể xuất hiện dưới dạng văn bản `"null"`, thường không phải kết quả mong muốn.
- Với `Collectors.toUnmodifiableList()`, phần tử null **không được chấp nhận**.
- Với `toList`, thay vì phụ thuộc vào chính sách null của implementation, nên quyết định rõ nghiệp vụ và tránh đưa null vào nếu không cần.
- Nếu mapper gọi `e.name().toUpperCase(...)` trên tên null, sẽ phát sinh `NullPointerException` trước khi downstream xử lý.

Khi cần **bỏ qua kết quả mapping null**, có thể dùng kết hợp downstream `mapping` và `filtering` trên kiểu đã biến đổi:

```java
Collectors.mapping(
        Employee::name,
        Collectors.filtering(
                java.util.Objects::nonNull,
                Collectors.toList()
        )
)
```

Đoạn này là collector minh họa đặt trong ngữ cảnh `groupingBy(Employee::team, ...)`, yêu cầu Java 9+. Khác với `filtering(Employee::active, mapping(Employee::name, ...))`: ở đây filtering nhận **String** sau khi mapping, nên có thể kiểm tra null của tên.

Nếu khóa nhóm trả null, `groupingBy` của JDK không chấp nhận null classifier key; cần validate, lọc hoặc chuyển null thành một khóa đại diện rõ ràng trước khi phân nhóm. Không dùng `groupingBy(e -> e.team())` rồi giả định null là một nhóm hợp lệ.

Với dữ liệu nghiệp vụ cần đầy đủ, **báo lỗi/validate** có thể đúng hơn việc âm thầm bỏ phần tử. Việc chuyển đổi trong nhóm không thay thế cho quy tắc kiểm tra dữ liệu.

## 13. Kiểm thử logic collector theo từng lớp

Thay vì chỉ kiểm tra một Map lớn rồi tìm nguyên nhân khi sai, nên kiểm thử từng phần:

1. **Classifier:** `Employee::team` trả đúng team cho mỗi đối tượng, kể cả case biên không?
2. **Mapper:** `Employee::name`, uppercase hoặc chuyển sang DTO có đúng kiểu và dữ liệu không?
3. **Downstream:** dùng `toList`, `toSet`, `joining`, `reducing` có đúng ý nghĩa và xử lý trùng lặp không?
4. **Tổng hợp:** với một tập dữ liệu nhỏ, Map kết quả có đủ khóa và đúng danh sách/chuỗi trong từng nhóm không?
5. **Nhóm rỗng:** khi dùng `filtering` downstream, khóa có được giữ và giá trị nhóm rỗng có đúng không?
6. **Thứ tự:** nếu in toàn bộ Map làm output test, phải chọn Map có thứ tự hoặc so sánh nội dung theo khóa thay vì phụ thuộc HashMap.
7. **Null và exception:** mapper có xử lý được đầu vào không hợp lệ theo hợp đồng không?

Có thể tạo dữ liệu test tối giản với ít nhất hai nhóm, một nhóm chỉ có phần tử bị loại, và một nhóm có tên trùng. Kết quả sẽ cho thấy rõ tác dụng riêng của `groupingBy`, `filtering` và `mapping`.

## 14. Các lỗi thường gặp

1. **Đổi đối tượng thành tên ở upstream rồi vẫn dùng classifier trên object gốc.** Sau `stream.map(Employee::name)`, Stream có kiểu String; `groupingBy(Employee::team)` sẽ không hợp lệ.
2. **Tưởng `mapping` tự tạo nhóm.** Không; nó chỉ là downstream collector, cần một collector ngoài như `groupingBy` hoặc `partitioningBy` nếu muốn phân nhóm.
3. **Tưởng `mapping` làm phẳng List con.** Với mapper trả List, `mapping(..., toList())` tạo List<List<...>>. Dùng `flatMapping` khi cần gộp từng phần tử từ stream con.
4. **Tưởng `mapping` tự loại trùng hoặc sort.** Các tính chất đó thuộc downstream collector hoặc stage khác.
5. **Nhầm vị trí `filtering` và `mapping`.** Predicate cần Employee phải chạy trước mapper Employee→String; Predicate kiểm tra String phải chạy sau mapper.
6. **Sử dụng `toSet` rồi yêu cầu hiển thị đúng thứ tự.** Tập Set mặc định không bảo đảm thứ tự; chọn TreeSet/comparator khi thứ tự là yêu cầu.
7. **Cho rằng mọi nhóm phải xuất hiện sau upstream filter.** Nhóm không còn phần tử bị biến mất; downstream filtering có thể giữ khóa với giá trị rỗng khi đã có dữ liệu của nhóm.
8. **Đưa null qua mapper mà không xác định chính sách.** Một số downstream không chấp nhận null hoặc in thành “null”.
9. **Dùng `counting()` sau mapping một cách không cần thiết.** Nếu chỉ đếm phần tử, bỏ mapper và dùng counting trực tiếp.
10. **Gắn side effect vào mapper.** Với parallel stream, thứ tự và điều kiện đồng thời khó kiểm soát; nên dùng hàm biến đổi thuần túy.
11. **Nhầm khóa map với giá trị trong nhóm.** Classifier xác định khóa, mapping xác định giá trị, downstream xác định kết quả.
12. **Quên tạo stream mới khi thu nhiều kết quả.** Một Stream đã bị terminal operation tiêu thụ không thể tái sử dụng; tạo stream mới từ collection.
13. **Giả định `groupingBy` trả TreeMap.** Mặc định loại Map không được cam kết; dùng overload có mapFactory nếu cần Map có thứ tự.
14. **Bỏ qua hiệu năng của mapper.** Nếu mapper gọi network hoặc phép tính đắt đỏ trên từng phần tử, đặt nó trong collector không tự làm công việc nhẹ hơn; đo và thiết kế lại nguồn/logic khi cần.

## 15. Bài tập tự kiểm tra

Cho dữ liệu:

```java
record Task(String project, String owner, boolean done) {}

List<Task> tasks = List.of(
        new Task("A", "Lan", true),
        new Task("B", "Minh", false),
        new Task("A", "An", false),
        new Task("B", "Hoa", false),
        new Task("A", "Lan", true)
);
```

Các đoạn này đặt trong class/phương thức Java 17 với import `List`.

Hãy tự xây collector để có:

1. Map từ project sang **list tên owner**, giữ những tên trùng.
2. Map từ project sang **tập owner không trùng**.
3. Map từ project sang danh sách **owner của task đã hoàn thành**, nhưng vẫn giữ khóa B với danh sách rỗng.
4. Giải thích tại sao `tasks.stream().map(Task::owner).collect(groupingBy(Task::project))` sai kiểu.
5. Nêu khi nào dùng `flatMapping` thay cho `mapping`.

**Đáp án tham khảo** (đặt trong phương thức, import `Map` và `Collectors`):

```java
Map<String, List<String>> all = tasks.stream()
        .collect(Collectors.groupingBy(
                Task::project,
                Collectors.mapping(Task::owner, Collectors.toList())
        ));

Map<String, java.util.Set<String>> unique = tasks.stream()
        .collect(Collectors.groupingBy(
                Task::project,
                Collectors.mapping(Task::owner, Collectors.toSet())
        ));

Map<String, List<String>> completed = tasks.stream()
        .collect(Collectors.groupingBy(
                Task::project,
                Collectors.filtering(
                        Task::done,
                        Collectors.mapping(
                                Task::owner,
                                Collectors.toList()
                        )
                )
        ));
```

Nội dung theo từng khóa (không dựa vào thứ tự lặp của Map):

```text
all.get("A")       = [Lan, An, Lan]
all.get("B")       = [Minh, Hoa]
unique.get("A")    = {Lan, An}  (thứ tự Set không cam kết)
unique.get("B")    = {Minh, Hoa}
completed.get("A") = [Lan, Lan]
completed.get("B") = []
```

Lời giải câu 4: sau `map(Task::owner)`, Stream mang kiểu String, không còn đủ dữ liệu để gọi `Task::project` làm classifier. Câu 5: dùng `flatMapping` khi một Task tạo **nhiều** phần tử thông qua Stream con cần ghép vào cùng nhóm, chẳng hạn mỗi task có nhiều tag và muốn thu chung từng tag.

## 16. Quy tắc ghi nhớ

Khi cần “**nhóm theo A nhưng lấy B trong từng nhóm**”, hãy hình dung:

```java
Map<Key, List<Value>> result = source.stream()
        .collect(Collectors.groupingBy(
                item -> keyOf(item),
                Collectors.mapping(
                        item -> valueOf(item),
                        Collectors.toList()
                )
        ));
```

Đây là **mẫu minh họa**: cần định nghĩa `Key`, `Value`, `source`, `keyOf`, `valueOf` phù hợp trong chương trình thật.

**Phân biệt ba vai trò:**

- **Classifier (ngoài):** xác định phần tử thuộc nhóm nào.
- **Mapper (trong):** xác định thông tin nào của phần tử được đưa vào nhóm.
- **Downstream collector (trong cùng):** quyết định kết quả của mỗi nhóm là List, Set, String, tổng, thống kê hay cấu trúc khác.

Nếu upstream vẫn cần trường của object gốc để xác định khóa, đừng biến đổi mất trường đó quá sớm. `Collectors.mapping` giúp thiết kế pipeline nhóm theo dữ liệu gốc nhưng lưu đầu ra đã biến đổi, gọn, rõ kiểu và có thể tổ hợp tiếp với `filtering`, `flatMapping` và các collector khác.

**Tài liệu tham khảo:** Java SE API `java.util.stream.Collectors.mapping`, `Collectors.groupingBy`, `Collectors.partitioningBy`, `Collectors.filtering`, `Collectors.flatMapping`, `Collectors.toCollection`, `Collectors.joining` và `java.util.stream.Stream.collect`.