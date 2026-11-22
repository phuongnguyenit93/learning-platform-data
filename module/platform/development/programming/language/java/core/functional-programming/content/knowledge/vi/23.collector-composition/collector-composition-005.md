# `Collectors.filtering()` phía sau `groupingBy()` khác lọc toàn pipeline

## 1. Vấn đề: lọc phần tử trước hay sau khi hình thành nhóm?

Khi thao tác với Stream, ta thường muốn **phân nhóm dữ liệu theo một khóa** rồi chỉ giữ những phần tử đáp ứng điều kiện trong từng nhóm. Hai cách viết tưởng như giống nhau nhưng có kết quả khác:

~~~java
// A: Lọc dữ liệu trước khi grouping.
employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.toList()));

// B: Grouping trước, lọc trong downstream collector.
employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));
~~~

**Khác biệt quan trọng:** Với cách A, một phòng ban mà **không có nhân viên active** sẽ không có phần tử nào tới `groupingBy`, nên **không có khóa phòng ban ấy trong Map kết quả**. Với cách B, `groupingBy` nhìn thấy mọi nhân viên, nên **phòng ban vẫn xuất hiện** nếu nó có ít nhất một nhân viên nguồn; downstream `filtering` chỉ loại các nhân viên không active khỏi **giá trị được gom cho phòng ban đó**. Giá trị của nhóm ấy có thể là danh sách rỗng.

Ví dụ:

~~~text
Nguồn:
Engineering: An(active), Binh(active)
Sales:       Chi(inactive)
Support:     Dung(inactive)

Lọc toàn Stream rồi groupingBy:
{Engineering=[An, Binh]}

groupingBy rồi downstream filtering:
{Engineering=[An, Binh], Sales=[], Support=[]}
~~~

Trên đây là sơ đồ rút gọn theo tên nhân viên, không phải cách in mặc định của `Employee`. Nếu cần Map có thứ tự ổn định để hiển thị, hãy yêu cầu `TreeMap` hoặc sắp xếp kết quả; `groupingBy` mặc định không cam kết loại Map hay thứ tự duyệt khóa.

Đó là ý nghĩa chính của bài: **vị trí đặt predicate so với bước phân nhóm thay đổi sự tồn tại của khóa nhóm**, ngay cả khi các giá trị không rỗng của hai cách có thể giống nhau.

## 2. Ôn nhanh: `Stream.filter` và `Collectors.groupingBy`

`Stream.filter` là một **thao tác trung gian (intermediate operation)**:

~~~java
Stream<T> filter(Predicate<? super T> predicate);
~~~

Nó kiểm tra từng phần tử mà pipeline thực sự xử lý và chỉ truyền những phần tử thỏa điều kiện sang các bước sau. Nếu phần tử không đi qua `filter`, những bước sau (kể cả `groupingBy`) không nhìn thấy nó.

`Collectors.groupingBy` là phương thức tạo **Collector** để nhóm phần tử theo khóa:

~~~java
static <T, K> Collector<T, ?, Map<K, List<T>>>
        groupingBy(Function<? super T, ? extends K> classifier);
~~~

Overload quan trọng hơn ở bài này nhận downstream collector:

~~~java
static <T, K, A, D> Collector<T, ?, Map<K, D>>
        groupingBy(
                Function<? super T, ? extends K> classifier,
                Collector<? super T, A, D> downstream);
~~~

Cách đọc:

- `classifier` tạo khóa `K` cho **mỗi phần tử đến được groupingBy**.
- `downstream` tạo giá trị `D` cho mỗi khóa.
- Với `toList()`, mỗi giá trị `D` là `List<T>`.
- Với `counting()`, mỗi giá trị `D` là `Long`.
- Với `mapping(..., toList())`, mỗi giá trị `D` là danh sách của kiểu được biến đổi.

Overload ba tham số cho phép chọn một factory của Map:

~~~java
groupingBy(classifier, TreeMap::new, downstream)
~~~

Cách này hữu ích khi muốn duyệt khóa theo thứ tự của `TreeMap`, chẳng hạn để kết quả hiển thị và kiểm thử có thứ tự nhất quán. Khi key không có thứ tự tự nhiên thích hợp, cần cung cấp comparator phù hợp.

## 3. `Collectors.filtering`: lọc ở tầng downstream

`Collectors.filtering` được thêm vào Java 9, có sẵn trong Java 17+:

~~~java
static <T, A, R> Collector<T, ?, R> filtering(
        Predicate<? super T> predicate,
        Collector<? super T, A, R> downstream);
~~~

Nó nhận **hai đối số**:

1. `predicate`: điều kiện quyết định có chuyển phần tử đang xét cho collector phía trong hay không.
2. `downstream`: collector sẽ nhận những phần tử qua điều kiện và tổng hợp chúng.

Ví dụ dùng độc lập:

~~~java
List<Integer> even = Stream.of(1, 2, 3, 4)
        .collect(Collectors.filtering(
                n -> n % 2 == 0,
                Collectors.toList()));

System.out.println(even); // [2, 4]
~~~

Với một collector đơn lẻ như trên, kết quả về giá trị tương tự `stream.filter(predicate).collect(toList())`. **Sự khác biệt nổi bật xuất hiện khi `filtering` được đặt bên trong collector kết hợp**, cụ thể là downstream của `groupingBy`: khi đó danh sách rỗng vẫn có thể là giá trị của một khóa nhóm tồn tại.

**Không nhầm hai tên giống nhau:**

- `Stream.filter(predicate)` là thao tác của Stream, lọc **trước khi** dữ liệu đến collector.
- `Collectors.filtering(predicate, downstream)` tạo một **Collector** để lọc trong quá trình thu thập; ở trong `groupingBy`, nó áp dụng cho **phần giá trị downstream của mỗi nhóm**.

## 4. Cơ chế hình thành nhóm: vì sao khóa có thể được giữ lại?

Giả sử:

~~~java
record Employee(String name, String department, boolean active) {}

List<Employee> employees = List.of(
        new Employee("An", "Engineering", true),
        new Employee("Binh", "Engineering", true),
        new Employee("Chi", "Sales", false));
~~~

**Cách A — lọc trước grouping:**

~~~java
Map<String, List<Employee>> early = employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(Employee::department));
~~~

Luồng đến collector chỉ còn An và Binh. `classifier` không bao giờ được gọi cho Chi. Do đó, không có nhóm `Sales` trong Map `early`.

**Cách B — lọc trong nhóm:**

~~~java
Map<String, List<Employee>> late = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));
~~~

Mỗi Employee đến `groupingBy` trước tiên được phân loại theo department. Vì có Chi thuộc `Sales`, Map có khóa `Sales`. Downstream `filtering` không chuyển Chi cho `toList` vì `active == false`. Collector của Sales vẫn có thể hoàn tất với danh sách rỗng.

~~~java
System.out.println(early.containsKey("Sales")); // false
System.out.println(late.containsKey("Sales"));  // true
System.out.println(late.get("Sales").isEmpty()); // true
~~~

Đó là hai kiểu dữ liệu khác nhau về **ý nghĩa tồn tại nhóm**:

- Không có key: nguồn sau các bước upstream không đưa bất kỳ phần tử nào tới classifier cho key đó.
- Có key nhưng value rỗng: nguồn có phần tử thuộc key đó, nhưng không có phần tử nào đáp ứng predicate downstream.

**Giới hạn rất quan trọng:** downstream `filtering` không tự tạo những khóa không hề có trong nguồn. Nếu không có Employee nào thuộc `Legal`, cả hai cách đều không tự thêm khóa `Legal`. Muốn biểu diễn đầy đủ tất cả phòng ban theo danh mục độc lập, cần thêm bước khởi tạo/đối chiếu với danh mục phòng ban.

## 5. Sơ đồ pipeline: vị trí của bộ lọc quyết định điều gì

### 5.1. Lọc sớm — nhóm có thể biến mất

~~~text
Stream<Employee>
    |
    v
filter(Employee::active)
    |  bỏ Chi của Sales
    v
groupingBy(Employee::department)
    |
    +--- Engineering --> [An, Binh]
    |
    +--- Sales không tồn tại
~~~

Ở đây `groupingBy` **không nhận** phần tử bị loại. Vì vậy khóa dựa trên phần tử đó cũng không được hình thành.

### 5.2. Lọc trong downstream — nhóm có thể tồn tại nhưng rỗng

~~~text
Stream<Employee>
    |
    v
groupingBy(Employee::department)
    |
    +--- Engineering --- filtering(active) ---> [An, Binh]
    |
    +--- Sales --------- filtering(active) ---> []
~~~

Classifier thấy Chi của Sales và xây dựng nhóm. Downstream lọc thành viên nhưng không bảo rằng phải xóa key của nhóm khỏi Map.

Sự khác biệt này ảnh hưởng đến báo cáo, giao diện, dashboard, kiểm kê và các bài toán cần phân biệt “không có nhóm” với “nhóm có dữ liệu nguồn nhưng không có mục đạt yêu cầu”.

## 6. Một ví dụ đặc biệt dễ hiểu: `counting()`

Nếu downstream là `Collectors.counting()` thì việc giữ nhóm rỗng sẽ xuất hiện dưới dạng **giá trị 0**, thay vì danh sách rỗng.

~~~java
Map<String, Long> countAfterEarlyFilter = employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.counting()));

Map<String, Long> countWithDownstreamFilter = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.counting())));
~~~

Với `Engineering` có 2 người active và `Sales` chỉ có người inactive:

~~~text
countAfterEarlyFilter:
Engineering -> 2
Sales       -> không có key

countWithDownstreamFilter:
Engineering -> 2
Sales       -> 0
~~~

Tư duy đúng:

- Dùng `filter` **trước collector** nếu kết quả chỉ cần chứa những nhóm **có ít nhất một phần tử phù hợp**.
- Dùng downstream `filtering(..., counting())` nếu kết quả cần chứa **mọi nhóm đã xuất hiện trong nguồn**, kể cả khi số phần tử phù hợp bằng 0.

Đừng viết `map.get("Sales") == 0L` như một cách kiểm tra nhóm rỗng ở phía lọc sớm; `get` có thể trả `null` khi key không tồn tại, và việc unboxing hoặc so sánh sai kiểu có thể gây lỗi. Hãy dùng `containsKey` hoặc `getOrDefault("Sales", 0L)` với ý nghĩa rõ ràng.

### 6.1. Ứng dụng cho thống kê theo phòng ban

Giả sử tổng số nhân viên và số nhân viên active cần được hiển thị cho cùng một tập phòng ban. Với downstream filtering, những phòng ban có 0 nhân viên active vẫn hiện trong thống kê. Đây là một thuộc tính **dữ liệu đầu ra**, không chỉ là “cách viết cho đẹp”.

Nếu muốn hiển thị cả phòng ban có **0 nhân viên tổng cộng**, grouping trên danh sách Employee vẫn không đủ; phải bắt đầu từ danh sách phòng ban hoặc ghép kết quả với danh mục phòng ban đầy đủ.

## 7. Kết hợp `filtering` với `mapping`

Bên cạnh `counting` và `toList`, downstream collector thường được lồng để **vừa lọc vừa chuyển đổi** phần tử giữ lại.

Ví dụ chỉ lấy tên nhân viên active trong từng nhóm:

~~~java
Map<String, List<String>> activeNames = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()))));
~~~

Luồng kiểu:

~~~text
Stream<Employee>
   |
   v
groupingBy(Employee::department)
   |
   +--- downstream filtering(Employee::active)
                  |
                  +--- mapping(Employee::name)
                              |
                              +--- toList() -> List<String>
~~~

Map kết quả có kiểu `Map<String, List<String>>`. Trong nhóm Sales có nhân viên nguồn nhưng không ai active, giá trị là `List<String>` rỗng.

Có thể đảo thứ tự nesting của `filtering` và `mapping` **chỉ khi predicate được viết cho đúng kiểu**:

~~~java
// Sau mapping Employee -> String,
// filtering nhận String chứ không còn Employee.
Collectors.mapping(
        Employee::name,
        Collectors.filtering(
                name -> !name.isBlank(),
                Collectors.toList()))
~~~

Không thể viết `Collectors.mapping(Employee::name, Collectors.filtering(Employee::active, toList()))` vì downstream filtering lúc này nhận `String`, không còn nhận `Employee`. **Đọc thứ tự nesting từ ngoài vào trong và suy ra kiểu input của từng collector** để tránh lỗi generic.

### 7.1. Cùng lúc lọc theo hai điều kiện

~~~java
Collectors.filtering(
        e -> e.active() && e.name() != null,
        Collectors.mapping(Employee::name, Collectors.toList()))
~~~

Trong code trên, predicate nhận `Employee` và ngăn tên null được chuyển cho downstream. Điều kiện cần phản ánh chính sách nghiệp vụ, không nên chỉ thêm lọc null vì muốn giấu dữ liệu thiếu.

## 8. Tình huống trước–sau trong báo cáo nghiệp vụ

Hãy hình dung bảng dữ liệu:

| Phòng ban | Nhân viên | Active |
| --- | --- | --- |
| Engineering | An | true |
| Engineering | Binh | true |
| Sales | Chi | false |
| Support | Dung | false |

Nhu cầu 1: “Hiển thị **những phòng ban có nhân viên active**, kèm danh sách người active.” Khi đó lọc upstream là hợp lý.

~~~java
employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(Employee::department));
~~~

Nhu cầu 2: “Hiển thị **tất cả phòng ban từng xuất hiện trong danh sách Employee**, kể cả phòng ban không có nhân viên active, để hiển thị trạng thái trống.” Khi đó lọc downstream là hợp lý.

~~~java
employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));
~~~

Nếu hiển thị đầy đủ các phòng ban được khai báo trong hệ thống, kể cả **không có Employee nào**, hai pipeline trên đều chưa đủ. Có thể bắt đầu từ danh mục phòng ban rồi lấy nhóm tương ứng với `getOrDefault`, hoặc dùng một bước hợp nhất với các key cần có.

**Không có cách nào “luôn tốt hơn”**: vị trí của `filter`/`filtering` phải đến từ câu hỏi dữ liệu mà API hoặc báo cáo cần trả lời.

## 9. Trường hợp nguồn rỗng và nguồn có nhóm nhưng không có kết quả

Ba tình huống phải phân biệt:

1. Stream nguồn rỗng hoàn toàn.
2. Stream có nhóm `A` nhưng tất cả phần tử của A bị lọc ở downstream.
3. Stream có nhóm A và có một số phần tử được giữ lại.

~~~java
List<Employee> emptySource = List.of();

Map<String, List<Employee>> emptyResult = emptySource.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));

System.out.println(emptyResult.isEmpty()); // true
~~~

**Không** có key nào được tạo vì không có Employee nào để phân loại. Downstream `filtering` không tự sinh khóa từ khoảng trống.

~~~java
List<Employee> inactiveOnly = List.of(
        new Employee("Chi", "Sales", false));

Map<String, List<Employee>> result = inactiveOnly.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));

System.out.println(result.containsKey("Sales")); // true
System.out.println(result.get("Sales").isEmpty()); // true
~~~

Đây là cách kiểm tra trực tiếp, ổn định hơn so với in toàn bộ Map rồi phụ thuộc vào thứ tự duyệt hoặc `toString()` của các đối tượng.

## 10. `null` và lỗi classifier: downstream filtering không phải tấm chắn

Một điểm rất dễ sai: trong `groupingBy(classifier, filtering(...))`, **classifier phải xử lý phần tử trước khi downstream biết có giữ phần tử hay không**. Vì vậy, bộ lọc downstream không bảo vệ classifier khỏi dữ liệu không hợp lệ.

Giả sử một Employee không active có `department == null`:

~~~java
List<Employee> source = List.of(
        new Employee("An", "Engineering", true),
        new Employee("Unknown", null, false));
~~~

Lọc upstream:

~~~java
Map<String, List<Employee>> early = source.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(Employee::department));

// Thành công: phần tử inactive với department null bị lọc trước.
~~~

Lọc downstream:

~~~java
// Có thể ném NullPointerException vì groupingBy phải lấy
// key = null từ Employee "Unknown" trước khi filtering bỏ người này.
Map<String, List<Employee>> late = source.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));
~~~

Các overload `Collectors.groupingBy` của JDK không chấp nhận classifier trả khóa null; nếu classifier trả null, chúng ném `NullPointerException`. Do đó **chọn vị trí lọc cũng ảnh hưởng đến validation và nơi phát sinh lỗi**, không chỉ tập key kết quả.

Nếu dữ liệu có thể chứa phần tử nguồn null, `Employee::department` cũng có thể ném lỗi ngay khi được áp dụng lên reference null. Hãy xử lý `Objects::nonNull` upstream khi đó là điều kiện cho phép lọc, hoặc thực hiện validation rõ ràng nếu dữ liệu null là lỗi cần báo.

### 10.1. Null trong downstream value

`Collectors.filtering` không có nhiệm vụ biến kết quả null thành giá trị hợp lệ. Nếu `mapping(Employee::name, toList())` trả tên null, danh sách tạo bởi `Collectors.toList()` có thể chứa null; những downstream khác như `toUnmodifiableList()` từ chối null và có thể ném `NullPointerException`. Phải xét chính **collector bên trong** và yêu cầu dữ liệu của nó.

## 11. `groupingBy` không cam kết Map hay thứ tự duyệt

`groupingBy(classifier, downstream)` trả `Map<K,D>`, nhưng hợp đồng API không bảo đảm Map cụ thể như `HashMap` hoặc `LinkedHashMap`, cũng không cam kết iteration order. Nếu hiển thị kết quả theo thứ tự phòng ban, có thể dùng overload ba tham số:

~~~java
Map<String, List<Employee>> grouped = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                java.util.TreeMap::new,
                Collectors.filtering(
                        Employee::active,
                        Collectors.toList())));
~~~

`TreeMap` giúp các key `String` được sắp xếp theo thứ tự tự nhiên. Thứ tự các phần tử **trong từng List** phụ thuộc encounter order của nguồn và hợp đồng của downstream collector; với nguồn `List` và pipeline tuần tự, `toList` phản ánh thứ tự gặp các phần tử của nhóm.

Không nên suy rằng `Collectors.filtering` luôn trả ra List: **kiểu kết quả thuộc về downstream**. Ví dụ:

~~~java
Collectors.filtering(Employee::active, Collectors.counting())
~~~

trả một Collector có kết quả `Long`, còn:

~~~java
Collectors.filtering(Employee::active, Collectors.mapping(
        Employee::name, Collectors.toSet()))
~~~

trả một Collector có kết quả `Set<String>`. Với `toSet`, thứ tự duyệt của Set không được cam kết.

## 12. Chương trình Java 17+ hoàn chỉnh với stdout xác định

Tạo tệp **`GroupingFilteringDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupingFilteringDemo {
    record Employee(String name, String department, boolean active) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("An", "Engineering", true),
                new Employee("Binh", "Engineering", true),
                new Employee("Chi", "Sales", false),
                new Employee("Dung", "Support", false));

        Map<String, List<String>> earlyNames = employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::department,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList())));

        Map<String, List<String>> lateNames = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        TreeMap::new,
                        Collectors.filtering(
                                Employee::active,
                                Collectors.mapping(
                                        Employee::name,
                                        Collectors.toList()))));

        System.out.println("earlyNames=" + earlyNames);
        System.out.println("lateNames=" + lateNames);
        System.out.println("earlyHasSales="
                + earlyNames.containsKey("Sales"));
        System.out.println("lateHasSales="
                + lateNames.containsKey("Sales"));
        System.out.println("lateSalesEmpty="
                + lateNames.get("Sales").isEmpty());

        Map<String, Long> earlyCounts = employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::department,
                        TreeMap::new,
                        Collectors.counting()));

        Map<String, Long> lateCounts = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        TreeMap::new,
                        Collectors.filtering(
                                Employee::active,
                                Collectors.counting())));

        System.out.println("earlyCounts=" + earlyCounts);
        System.out.println("lateCounts=" + lateCounts);

        Map<String, List<Employee>> emptyGroups =
                List.<Employee>of().stream()
                        .collect(Collectors.groupingBy(
                                Employee::department,
                                Collectors.filtering(
                                        Employee::active,
                                        Collectors.toList())));
        System.out.println("emptySourceMap=" + emptyGroups.isEmpty());

        List<Employee> withNullGroup = List.of(
                new Employee("An", "Engineering", true),
                new Employee("Unknown", null, false));

        Map<String, Long> earlyNull = withNullGroup.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::department,
                        Collectors.counting()));
        System.out.println("earlyNullSize=" + earlyNull.size());

        try {
            withNullGroup.stream()
                    .collect(Collectors.groupingBy(
                            Employee::department,
                            Collectors.filtering(
                                    Employee::active,
                                    Collectors.counting())));
        } catch (NullPointerException ex) {
            System.out.println("downstreamCannotHideNullGroup=true");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac GroupingFilteringDemo.java
java GroupingFilteringDemo
~~~

**Stdout:**

~~~text
earlyNames={Engineering=[An, Binh]}
lateNames={Engineering=[An, Binh], Sales=[], Support=[]}
earlyHasSales=false
lateHasSales=true
lateSalesEmpty=true
earlyCounts={Engineering=2}
lateCounts={Engineering=2, Sales=0, Support=0}
emptySourceMap=true
earlyNullSize=1
downstreamCannotHideNullGroup=true
~~~

Giải thích:

1. `earlyNames` chỉ có Engineering vì phòng ban Sales và Support không có nhân viên active nào còn tồn tại sau `Stream.filter`.
2. `lateNames` chứa Sales và Support với List rỗng, vì classifier đã tạo những nhóm đó từ dữ liệu nguồn trước khi filtering quyết định giữ phần tử.
3. `earlyHasSales` và `lateHasSales` cho thấy sự khác biệt bằng `containsKey`, không chỉ bằng cách so sánh danh sách rỗng.
4. `earlyCounts` bỏ những key không có người active; `lateCounts` giữ chúng với số đếm 0.
5. Với stream nguồn rỗng hoàn toàn, `groupingBy` không có key để tạo, nên Map vẫn rỗng.
6. Khi phần tử inactive mang khóa null, `Stream.filter` upstream loại phần tử trước classifier; trong dạng downstream filtering, classifier gặp null và ném `NullPointerException`.

Cả hai Map in ra được yêu cầu dùng `TreeMap::new` nên thứ tự khóa có thể đối chiếu một cách xác định. Tên nhân viên được gom vào các `List` theo encounter order của nguồn `List` tuần tự. Không có tác vụ bất đồng bộ nên stdout không phụ thuộc lịch thực thi.

## 13. Khi nào chọn cách nào trong thực tế?

### Dùng `stream.filter(...).collect(groupingBy(...))` khi:

- Chỉ muốn nhóm những bản ghi hợp lệ hoặc thỏa điều kiện.
- Muốn các nhóm **không còn phần tử phù hợp** biến mất khỏi kết quả.
- Cần chặn dữ liệu không đủ điều kiện trước khi chạy classifier (ví dụ các bản ghi thử nghiệm không được phép đi vào báo cáo chính).
- Muốn giảm lượng dữ liệu đến bước phân nhóm, nếu điều đó phù hợp ngữ nghĩa và có lợi về hiệu năng.

~~~java
Map<String, List<Employee>> activeDepartments =
        employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(Employee::department));
~~~

### Dùng `groupingBy(..., filtering(..., downstream))` khi:

- Cần giữ mọi khóa **đã xuất hiện trong dữ liệu nguồn**, kể cả khi không có phần tử phù hợp.
- Cần báo cáo theo từng nhóm với count 0, sum 0 theo một downstream thích hợp, hoặc danh sách rỗng.
- Muốn giữ cấu trúc nhóm độc lập với một điều kiện cụ thể của downstream.
- Cần kết hợp `filtering` với `mapping` hoặc những collector khác để tạo nhiều kiểu giá trị trong nhóm.

~~~java
Map<String, Long> activeCounts =
        employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        Collectors.filtering(
                                Employee::active,
                                Collectors.counting())));
~~~

**Đừng chọn dựa trên vẻ ngắn của cú pháp.** Hai pipeline giải quyết các yêu cầu khác nhau; khác biệt có thể trở thành bug khó thấy trong trường hợp một nhóm chỉ có phần tử không thỏa điều kiện.

## 14. Đặc tính song song và yêu cầu về side effect

Cả `Stream.filter` và `Collectors.filtering` đều nhận `Predicate<T>`. Predicate nên không phụ thuộc trạng thái mutable bên ngoài và không can thiệp nguồn. Dùng callback có side effect để đếm chính xác số lần chạy là không an toàn vì:

- Stream là pipeline lazy và một số terminal có thể dừng sớm hoặc được tối ưu hóa.
- Parallel stream có thể gọi predicate từ nhiều luồng, không theo thứ tự mong đợi.
- Collector kết hợp có thể phân chia và gộp các kết quả trung gian theo cơ chế triển khai.

Đối với `groupingBy`, downstream filtering không đảm bảo một nhóm sẽ được xử lý tuần tự ở mọi mô hình thực thi; hãy tuân thủ hợp đồng non-interference/stateless của Stream và collector.

Lưu ý `groupingByConcurrent` có mục tiêu và đặc điểm khác `groupingBy`; không tự giả định thay tên collector là vô hại đối với encounter order hoặc các cấu trúc kết quả. Nếu cần song song và thứ tự/kiểu Map cụ thể, hãy kiểm tra hợp đồng API và đo hiệu năng bằng dữ liệu đại diện.

## 15. Những lỗi thường gặp

| Nhận định/cách dùng sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Hai cách filtering là tương đương mọi lúc” | Khác việc giữ khóa không có phần tử phù hợp | Kiểm tra `containsKey` và nghiệp vụ muốn giữ key hay không |
| Dùng upstream `filter` nhưng muốn hiển thị nhóm với 0 kết quả | Nhóm chỉ có phần tử bị lọc sẽ không được tạo | Đưa `filtering` vào downstream của `groupingBy` |
| Dùng downstream filtering nhưng muốn xóa hẳn nhóm rỗng | Downstream thường chỉ tạo giá trị rỗng, không xóa key | Dùng upstream filter hoặc hậu xử lý Map một cách có chủ đích |
| Cho rằng downstream filtering tạo tất cả khóa từ danh mục | Nó chỉ giữ các khóa xuất hiện trong nguồn đến classifier | Dùng danh mục khóa độc lập nếu cần nhóm không có dữ liệu nguồn |
| Cho rằng filtering bảo vệ classifier khỏi khóa null | Classifier chạy trước khi downstream filtering quyết định giữ/bỏ | Validation/lọc upstream hoặc định nghĩa quy tắc key |
| Dùng `get(key).isEmpty()` với Map upstream mà key có thể vắng | `get` có thể null | Kiểm tra `containsKey` hoặc `getOrDefault` |
| Nhầm `Collectors.filtering` là terminal độc lập | Nó tạo Collector, được truyền vào `collect` | Phân biệt Collector với Stream operation |
| In Map thường để nghiệm thu thứ tự khóa | `groupingBy` không cam kết iteration order | Chọn `TreeMap::new` hoặc kiểm tra theo key |
| Dùng `Employee::active` sau `mapping(Employee::name,...)` | Downstream lúc đó đã có kiểu `String` | Đặt filtering trước mapping hoặc đổi predicate đúng kiểu |
| Nghĩ downstream luôn tạo `List` | Kiểu kết quả tùy collector phía trong | Xem `counting`, `toSet`, `mapping`, v.v. |
| Đặt side effect để suy luận số lần gọi predicate | Parallel/lazy pipeline không cam kết kiểu đếm ấy | Dùng thống kê/collector có hợp đồng cụ thể |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Nhóm Sales có một nhân viên nhưng `active=false`. Hai pipeline dưới đây khác gì?

~~~java
employees.stream().filter(Employee::active)
        .collect(groupingBy(Employee::department));

employees.stream()
        .collect(groupingBy(Employee::department,
                filtering(Employee::active, toList())));
~~~

**Đáp án:** Pipeline đầu không có key `Sales` nếu Sales không có nhân viên active. Pipeline sau có key `Sales` với danh sách rỗng, vì nguồn có nhân viên Sales để hình thành nhóm.

**Câu 2.** Nếu downstream đổi sang `counting()`, nhóm không có phần tử phù hợp biểu diễn thế nào?

**Đáp án:** Nhóm được giữ với value `0L` trong Map downstream filtering. Với upstream filter, key có thể không tồn tại.

**Câu 3.** Nếu không có Employee nào thuộc `Legal` trong stream nguồn, downstream filtering có tự tạo key Legal không?

**Đáp án:** Không. `groupingBy` chỉ biết những khóa classifier trả ra từ phần tử nguồn đến được collector. Muốn có Legal phải xuất phát từ danh mục phòng ban hoặc thêm logic hợp nhất.

**Câu 4.** Nếu một Employee inactive có `department=null`, downstream filtering có chặn được `groupingBy` ném lỗi không?

**Đáp án:** Không. Classifier phải được gọi để xác định key trước khi downstream quyết định giữ phần tử; classifier trả null bị `groupingBy` từ chối. Lọc upstream có thể loại phần tử ấy trước khi classifier chạy.

**Câu 5.** Muốn `Map<String,List<String>>` giữ nhóm rỗng và chỉ lấy tên nhân viên active thì làm gì?

**Đáp án:**

~~~java
employees.stream().collect(groupingBy(
        Employee::department,
        filtering(
                Employee::active,
                mapping(Employee::name, toList()))));
~~~

Để biên dịch đoạn này khi dùng static import, cần `import static java.util.stream.Collectors.*;`. Đây là đoạn minh họa cách lồng collectors; chương trình đầy đủ ở phần 12 dùng tên `Collectors` tường minh.

**Câu 6.** Lọc upstream có luôn “nhanh hơn” downstream filtering không?

**Đáp án:** Không thể kết luận chung. Upstream filter có thể giảm lượng phần tử tới classifier, nhưng hai cách có ngữ nghĩa khác nhau và hiệu năng phụ thuộc đặc điểm nguồn/predicate/collector. Ưu tiên đúng yêu cầu dữ liệu, chỉ tối ưu sau khi đo.

## 17. Ghi nhớ

**`Stream.filter` loại phần tử trước khi chúng tới `groupingBy`; `Collectors.filtering` đặt trong downstream của `groupingBy` loại phần tử khỏi kết quả của từng nhóm sau khi khóa nhóm đã được nhận diện.** Vì vậy:

- `stream.filter(p).collect(groupingBy(key))`: nhóm không có phần tử thỏa `p` có thể **biến mất hoàn toàn**.
- `stream.collect(groupingBy(key, filtering(p, downstream)))`: nhóm đã xuất hiện trong nguồn thường **vẫn có key**, nhưng kết quả downstream có thể là `[]`, `0L` hoặc giá trị trung hòa khác theo collector.
- Nhóm không hề xuất hiện trong nguồn sẽ **không được tự tạo**.
- Lọc downstream không tránh được lỗi của `classifier`, chẳng hạn khóa null.
- Có thể lồng `filtering` với `mapping`, `counting` và các collector khác; phải theo dõi kiểu dữ liệu qua từng lớp.
- Không giả định thứ tự duyệt của Map do `groupingBy` mặc định trả về; yêu cầu Map factory hoặc truy vấn theo key khi cần kết quả ổn định.

Chọn **vị trí của phép lọc** theo câu hỏi nghiệp vụ: “chỉ lấy nhóm có kết quả” hay “giữ mọi nhóm đã gặp, kể cả kết quả bằng không”.
