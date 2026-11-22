# Biến đổi đầu vào Collector bằng mapping

Trong chương **Collector nhiều tầng và tổng hợp** của **Java Stream API**, một phép tổng hợp thường không chỉ trả về một danh sách. Chẳng hạn, từ danh sách nhân viên, ứng dụng muốn nhóm theo phòng ban rồi **chỉ thu tên nhân viên**, hoặc nhóm đơn hàng theo khách hàng rồi **chỉ cộng thành tiền**. Khi ấy, ta cần vừa giữ được thông tin để chia nhóm, vừa biến đổi mỗi phần tử trước khi đưa vào phép thu thập của từng nhóm.

`Collectors.mapping(mapper, downstream)` giải quyết nhu cầu đó. Nó là **collector thích ứng** (*downstream collector adapter*): nhận phần tử kiểu `T`, dùng `mapper` chuyển thành `U` rồi giao giá trị `U` cho một collector khác. Khả năng ghép collector này đặc biệt hữu ích với `groupingBy`, `partitioningBy` và các phép thống kê/tổng hợp nhiều tầng.

Bài học giải thích kiểu dữ liệu, cách ghép collector, các ví dụ có thể chạy, sự khác biệt với `Stream.map`, cách phối hợp với `filtering` và `flatMapping`, cùng các vấn đề về `null`, thứ tự, hiệu năng và xử lý song song.

## 1. Vấn đề: vừa chia nhóm theo dữ liệu gốc, vừa thu dữ liệu đã biến đổi

Giả sử một nhân viên có mã, tên, phòng ban, trạng thái hoạt động và danh sách kỹ năng:

~~~java
record Employee(
        String id,
        String name,
        String department,
        boolean active,
        List<String> skills
) {}
~~~

Yêu cầu tạo kết quả kiểu:

~~~text
DEV -> [Lan, An, Huy]
QA  -> [Minh, Hạnh]
OPS -> [Bình]
~~~

Ta cần giữ `department` để tạo khóa, nhưng chỉ cần `name` trong danh sách kết quả. Nếu làm việc với `Collectors.groupingBy`, cách biểu đạt trực tiếp là:

~~~java
Map<String, List<String>> namesByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        ));
~~~

Đọc từ ngoài vào trong:

1. `employees.stream()` phát các phần tử `Employee`.
2. `groupingBy(Employee::department, ...)` xác định khóa nhóm từ **đối tượng Employee gốc**.
3. Với mỗi nhóm, `mapping(Employee::name, ...)` biến Employee thành `String`.
4. `Collectors.toList()` nhận những chuỗi tên và gom vào danh sách của nhóm.
5. `collect(...)` là terminal operation, kích hoạt toàn bộ pipeline và trả về `Map<String, List<String>>`.

Ở đây, **phép nhóm nhìn thấy `Employee`, còn collector bên trong nhận `String`**. Đó là giá trị thực tế của `mapping` trong collector nhiều tầng.

## 2. Chữ ký và hợp đồng của Collectors.mapping

Chữ ký tổng quát (có từ Java 8) là:

~~~java
public static <T, U, A, R> Collector<T, ?, R> mapping(
        Function<? super T, ? extends U> mapper,
        Collector<? super U, A, R> downstream)
~~~

Các ký hiệu:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu đầu vào mà collector ghép ngoài chuyển xuống | `Employee` |
| `U` | Kiểu sau khi áp dụng mapper | `String` |
| `A` | Kiểu vùng tích lũy nội bộ của downstream collector | Do collector quyết định |
| `R` | Kiểu kết quả cuối của downstream collector | `List<String>` |
| `mapper` | Hàm `T -> U`, được áp dụng cho từng phần tử | `Employee::name` |
| `downstream` | Collector xử lý các giá trị kiểu `U` | `Collectors.toList()` |

`mapping` **không phải terminal operation**. Nó tạo ra một đối tượng `Collector` để truyền vào `collect(...)` hoặc lồng vào collector khác. Chỉ khi pipeline chạy terminal operation, dữ liệu mới được chuyển đổi và tích lũy.

Một cách hình dung:

~~~text
                Employee
                   |
          groupingBy(department)
                   |
            Theo từng nhóm
                   |
          mapping(Employee::name)
                   |
                 String
                   |
          downstream: toList()
                   |
              List<String>
                   |
     Map<Department, List<String>>
~~~

Nhờ kiểu dữ liệu tổng quát, `mapping` có thể chuyển sang bất kỳ kiểu phù hợp với downstream collector: `Integer` để tính tổng độ dài tên, `BigDecimal` để tổng hợp tiền, một record DTO để xuất báo cáo hoặc khóa định danh để lấy tập giá trị phân biệt.

## 3. Ví dụ hoàn chỉnh chạy được trên Java 17+

Ví dụ sau dùng `record` và `List.of`. `record` cần Java 16+, `List.of` có từ Java 9, còn `Collectors.mapping` đã có từ Java 8.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

public class MappingCollectorDemo {

    record Employee(
            String id,
            String name,
            String department,
            boolean active,
            List<String> skills
    ) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("E1", "Lan", "DEV", true,
                        List.of("Java", "SQL")),
                new Employee("E2", "Minh", "QA", true,
                        List.of("Testing", "Java")),
                new Employee("E3", "An", "DEV", false,
                        List.of("Spring")),
                new Employee("E4", "Huy", "DEV", true,
                        List.of("Docker", "Java")),
                new Employee("E5", "Hạnh", "QA", false,
                        List.of("SQL")),
                new Employee("E6", "Bình", "OPS", false,
                        List.of("Linux"))
        );

        // Mỗi phòng ban chỉ nhận danh sách tên.
        Map<String, List<String>> namesByDepartment = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                ));

        System.out.println(namesByDepartment.get("DEV"));
        // [Lan, An, Huy]
        System.out.println(namesByDepartment.get("QA"));
        // [Minh, Hạnh]
        System.out.println(namesByDepartment.get("OPS"));
        // [Bình]

        // Mỗi phòng ban nhận tập tên phân biệt.
        Map<String, Set<String>> uniqueNames = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::department,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toSet()
                        )
                ));

        System.out.println(uniqueNames.get("DEV").contains("Lan"));
        // true
    }
}
~~~

Để xem dữ liệu của từng nhóm, hãy truy cập bằng khóa như `get("DEV")`. Đừng phụ thuộc vào **thứ tự duyệt khóa** của `Map` do `groupingBy` mặc định tạo; API không cam kết một lớp Map hoặc thứ tự khóa cụ thể.

Trong ví dụ, dữ liệu `List` có encounter order và `toList` lưu thứ tự các phần tử được đưa vào nhóm, nên `DEV` thu được `[Lan, An, Huy]`. Ngược lại, `toSet` không cam kết thứ tự lặp của tập.

## 4. mapping khác gì Stream.map?

Hai cách đều biến đổi dữ liệu theo một hàm ánh xạ, nhưng **vị trí của phép biến đổi trong pipeline khác nhau**.

### 4.1. Stream.map biến đổi trước khi collector nhận phần tử

~~~java
List<String> names = employees.stream()
        .map(Employee::name)
        .collect(Collectors.toList());
~~~

Cách này phù hợp khi chỉ muốn danh sách tên của **toàn bộ** nhân viên. Sau `map`, kiểu phần tử của Stream là `String`; nó không còn trực tiếp cung cấp `Employee::department` cho bước nhóm phía sau.

Ví dụ này **không thể** phân loại theo `Employee::department` sau khi Stream đã trở thành `Stream<String>`:

~~~java
// Sai ý tưởng: sau map, phần tử chỉ còn là String.
// employees.stream()
//         .map(Employee::name)
//         .collect(Collectors.groupingBy(Employee::department));
~~~

Tất nhiên, có thể tạo DTO chứa cả tên và phòng ban trước rồi nhóm DTO. Nhưng nếu chỉ cần một thuộc tính để chia nhóm và một giá trị khác để thu vào nhóm, downstream `mapping` thường gọn và rõ hơn.

### 4.2. Collectors.mapping biến đổi bên trong collector được ghép

~~~java
Map<String, List<String>> namesByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(Employee::name, Collectors.toList())
        ));
~~~

`groupingBy` nhìn thấy Employee trước khi gọi downstream; `mapping` chỉ chuyển đổi **giá trị được thu cho từng khóa**.

### 4.3. Khi không lồng collector, hai cách thường tương đương về nội dung

~~~java
List<String> a = employees.stream()
        .map(Employee::name)
        .collect(Collectors.toList());

List<String> b = employees.stream()
        .collect(Collectors.mapping(
                Employee::name,
                Collectors.toList()
        ));
~~~

Cả hai cho cùng dãy tên với nguồn và mapper đã nêu. Trong trường hợp này, cách `stream.map(...).collect(toList())` thường dễ đọc hơn. Giá trị lớn nhất của `Collectors.mapping` là **khả năng ghép nó vào downstream của collector khác**, ví dụ `groupingBy` hoặc `partitioningBy`.

| Tiêu chí | `Stream.map` | `Collectors.mapping` |
| --- | --- | --- |
| Vị trí | Intermediate operation trong pipeline | Collector adapter, thường nằm trong downstream |
| Đầu ra trung gian | Một `Stream<U>` | Một `Collector<T, ?, R>` |
| Dùng khi | Muốn đổi kiểu phần tử cho các bước sau | Muốn một collector cha vẫn thấy `T`, nhưng collector con thu `U` |
| Tự kết thúc pipeline? | Không | Không; cần gọi `collect(...)` |
| Hữu ích với `groupingBy` | Có, khi đã giữ đủ dữ liệu để phân nhóm | Đặc biệt hữu ích để phân nhóm theo `T`, thu kết quả từ `U` |

## 5. mapping kết hợp với các downstream collector khác nhau

`mapping` không giới hạn ở `toList`. Collector phía trong quyết định hình dạng kết quả và cách tổng hợp.

### 5.1. Tập tên phân biệt

~~~java
Map<String, Set<String>> names = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(Employee::name, Collectors.toSet())
        ));
~~~

Đầu ra cho mỗi phòng ban là một `Set<String>`. Nếu hai nhân viên trùng tên, tập chỉ giữ một giá trị theo quy tắc bằng nhau của `Set`. Nếu muốn giữ cả hai nhân viên, hãy thu ID hoặc bản ghi có khóa duy nhất; không dùng tên người làm định danh khi tên có thể trùng.

### 5.2. Chuỗi tên dùng dấu phẩy làm dấu phân cách

~~~java
Map<String, String> joinedNames = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.joining(", ")
                )
        ));

System.out.println(joinedNames.get("DEV"));
// Lan, An, Huy
~~~

`joining` chỉ dùng trực tiếp với chuỗi (chính xác hơn là `CharSequence`). `mapping` biến `Employee` thành `String` để đáp ứng downstream.

### 5.3. Tính tổng độ dài tên theo phòng ban

~~~java
Map<String, Integer> charactersByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.summingInt(String::length)
                )
        ));

System.out.println(charactersByDepartment.get("DEV"));
// 8: Lan(3) + An(2) + Huy(3)
~~~

Ở đây `T = Employee`, `U = String` và kết quả downstream là `Integer`. Ví dụ này nhấn mạnh `mapping` không nhất thiết tạo một collection: nó có thể đưa giá trị được ánh xạ vào **một collector tổng hợp**.

Với phép tính chỉ phụ thuộc trực tiếp vào Employee, có thể viết ngắn hơn bằng `Collectors.summingInt(employee -> employee.name().length())`. `mapping` phù hợp hơn khi muốn tái sử dụng collector của kiểu `U` hoặc làm rõ các bước biến đổi.

### 5.4. Thu vào một loại collection đã chọn

Khi cần tập có thứ tự chèn trong từng nhóm và giữ tên phân biệt:

~~~java
import java.util.LinkedHashSet;

Map<String, LinkedHashSet<String>> orderedNames = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toCollection(LinkedHashSet::new)
                )
        ));
~~~

Với nguồn `List` có encounter order và pipeline tuần tự, `LinkedHashSet` giữ thứ tự chèn của các tên trong mỗi nhóm. Việc dùng `Collectors.toSet()` sẽ **không** bảo đảm thứ tự lặp. Đừng nhầm thứ tự của collection **bên trong mỗi nhóm** với thứ tự các **khóa của Map ngoài**.

## 6. mapping trong partitioningBy và groupingBy nhiều tầng

### 6.1. Chia thành hai nhóm theo điều kiện

`partitioningBy` phân chia dữ liệu theo predicate boolean. Downstream `mapping` cho phép mỗi nhánh chỉ giữ thông tin cần thiết:

~~~java
Map<Boolean, List<String>> namesByActivity = employees.stream()
        .collect(Collectors.partitioningBy(
                Employee::active,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        ));

System.out.println(namesByActivity.get(true));
// [Lan, Minh, Huy]
System.out.println(namesByActivity.get(false));
// [An, Hạnh, Bình]
~~~

Khác với `groupingBy`, `partitioningBy` luôn trả cả hai khóa `true` và `false`, ngay cả khi một nhánh không có phần tử. Khi đó downstream tạo kết quả rỗng theo cách của collector tương ứng.

### 6.2. Nhóm theo phòng ban, rồi theo trạng thái

~~~java
Map<String, Map<Boolean, List<String>>> nested = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.groupingBy(
                        Employee::active,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                )
        ));

System.out.println(nested.get("DEV").get(true));
// [Lan, Huy]
System.out.println(nested.get("DEV").get(false));
// [An]
~~~

Pipeline mang nhiều tầng collector:

~~~text
Stream<Employee>
    |
groupingBy(department)
    |
    +-- groupingBy(active)
            |
            +-- mapping(name)
                    |
                    +-- toList()
~~~

Kết quả là `Map<String, Map<Boolean, List<String>>>`. Nhánh `groupingBy` bên trong chỉ tạo khóa boolean **nếu có phần tử thuộc nhánh đó**; nếu muốn luôn có cả hai khóa boolean, hãy dùng downstream `partitioningBy(Employee::active, ...)`.

### 6.3. Thu kết quả theo khóa đã sắp xếp

Nếu cần thứ tự phòng ban được sắp xếp theo khóa, có thể chọn factory tạo Map ngoài:

~~~java
import java.util.TreeMap;

Map<String, List<String>> sortedDepartments = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                TreeMap::new,
                Collectors.mapping(Employee::name, Collectors.toList())
        ));
~~~

Trong ví dụ, `TreeMap` sắp xếp khóa phòng ban theo thứ tự tự nhiên của `String`. Collector `mapping` chỉ quyết định **giá trị của từng nhóm**, không quyết định cách sắp xếp các khóa.

## 7. Kết hợp filtering với mapping: phân biệt vị trí của bộ lọc

Từ **Java 9**, `Collectors.filtering(predicate, downstream)` cho phép lọc phần tử **bên trong một nhóm đã được tạo**.

Giả sử yêu cầu: “Mỗi phòng ban có danh sách tên nhân viên đang hoạt động; ngay cả phòng ban chỉ có nhân viên ngừng hoạt động vẫn phải xuất hiện với danh sách rỗng”.

Đưa `filter` lên trước `groupingBy` sẽ **loại hẳn** những phòng ban không còn nhân viên hoạt động:

~~~java
Map<String, List<String>> onlyActiveDepartments = employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(Employee::name, Collectors.toList())
        ));

System.out.println(onlyActiveDepartments.containsKey("OPS"));
// false
~~~

Với downstream `Collectors.filtering`, classifier của `groupingBy` vẫn thấy mọi Employee. Nhóm `OPS` được tạo, rồi nhân viên không hoạt động không được đưa vào downstream `mapping`:

~~~java
Map<String, List<String>> allDepartments = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                )
        ));

System.out.println(allDepartments.get("DEV"));
// [Lan, Huy]
System.out.println(allDepartments.get("QA"));
// [Minh]
System.out.println(allDepartments.get("OPS"));
// []
~~~

Hai kết quả **không tương đương** vì yêu cầu “phải giữ tất cả khóa phòng ban” khác với “chỉ xét các nhân viên hoạt động”.

### mapping trước hay sau filtering?

Có thể chọn thứ tự dựa trên kiểu dữ liệu mà predicate cần:

~~~java
// Lọc theo Employee trước khi chuyển thành String:
Collectors.filtering(
        Employee::active,
        Collectors.mapping(Employee::name, Collectors.toList())
)
~~~

Ngược lại:

~~~java
// Chuyển thành String trước, lọc theo tên đã ánh xạ:
Collectors.mapping(
        Employee::name,
        Collectors.filtering(
                name -> name.length() >= 3,
                Collectors.toList()
        )
)
~~~

Trong cách thứ hai, downstream của `mapping` nhận `String` nên predicate chỉ thấy tên, không còn truy cập trực tiếp trạng thái `active` của Employee. Thiết kế thứ tự collector cần phù hợp với **kiểu và ngữ nghĩa** của mỗi bước.

## 8. mapping và flatMapping: giữ nguyên một giá trị hay làm phẳng nhiều giá trị?

`Collectors.mapping` chuyển **mỗi phần tử `T` thành đúng một giá trị `U`** rồi chuyển tiếp cho downstream. Nếu `mapper` trả về một `List<String>`, downstream sẽ nhận **cả List**, không tự trải các phần tử của List.

Ví dụ sai mục tiêu nếu muốn tập kỹ năng riêng lẻ:

~~~java
// Tập các DANH SÁCH kỹ năng, không phải tập tên kỹ năng:
Map<String, Set<List<String>>> skillListsByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::skills,
                        Collectors.toSet()
                )
        ));
~~~

Nếu yêu cầu là “mỗi phòng ban có một tập các kỹ năng phân biệt”, dùng `Collectors.flatMapping` (Java 9+) để chuyển mỗi Employee thành một `Stream<String>` rồi làm phẳng vào downstream:

~~~java
Map<String, Set<String>> skillsByDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.flatMapping(
                        employee -> employee.skills().stream(),
                        Collectors.toSet()
                )
        ));

System.out.println(skillsByDepartment.get("DEV"));
// Tập gồm Java, SQL, Spring, Docker (thứ tự không bảo đảm).
~~~

Bảng phân biệt:

| Collector adapter | Hàm đầu vào | Số phần tử đưa xuống downstream cho mỗi đầu vào |
| --- | --- | --- |
| `mapping(mapper, downstream)` | `T -> U` | Đúng một giá trị `U`, kể cả khi đó là collection hoặc `null` |
| `flatMapping(mapper, downstream)` | `T -> Stream<U>` | Không, một hoặc nhiều giá trị `U` |
| `filtering(predicate, downstream)` | `T -> boolean` | Không hoặc một phần tử `T` |

Các adapter có thể lồng nhau, nhưng không nên dùng `mapping` để giả vờ thay cho `flatMapping`. Hãy nhìn **kiểu dữ liệu thật sự đi vào downstream** để biết kết quả có một tầng hay nhiều tầng.

`flatMapping` có trách nhiệm đóng Stream do mapper trả về sau khi nội dung của Stream đó được chuyển xuống downstream. Tuy nhiên, nếu nguồn chính gắn với I/O như `Files.lines`, vẫn cần quản lý vòng đời nguồn chính bằng `try-with-resources`.

## 9. mapping với phép tính BigDecimal và tổng hợp chính xác

Collector không chỉ thu tên hay danh sách. Trong một ứng dụng bán hàng, có thể dùng `mapping` để tính tổng tiền theo khách hàng trong cùng pipeline.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String customerId, long quantity, BigDecimal unitPrice) {}

List<Sale> sales = List.of(
        new Sale("C-01", 2, new BigDecimal("12.50")),
        new Sale("C-02", 1, new BigDecimal("8.75")),
        new Sale("C-01", 3, new BigDecimal("2.40"))
);

Map<String, BigDecimal> exactRevenue = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::customerId,
                Collectors.mapping(
                        sale -> sale.unitPrice()
                                .multiply(BigDecimal.valueOf(sale.quantity())),
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                BigDecimal::add
                        )
                )
        ));

System.out.println(exactRevenue.get("C-01")); // 32.20
System.out.println(exactRevenue.get("C-02")); // 8.75
~~~

Các bước:

1. `groupingBy(Sale::customerId, ...)` phân loại theo mã khách.
2. `mapping` biến mỗi `Sale` thành thành tiền kiểu `BigDecimal`.
3. `reducing(BigDecimal.ZERO, BigDecimal::add)` cộng các khoản trong từng nhóm, không làm tròn trung gian.
4. Kết quả là `Map<String, BigDecimal>`, mỗi khóa lưu một tổng tiền chính xác.

`2 × 12.50 + 3 × 2.40 = 25.00 + 7.20 = 32.20`. Trong các hệ thống tiền tệ, chính sách scale và làm tròn thuộc nghiệp vụ: nếu cần làm tròn tổng theo từng khách hoặc từng hóa đơn, hãy chỉ làm tròn **ở đúng ranh giới** đã quy định, không mặc định dùng `setScale` ở mỗi lần accumulator cộng tiền.

Nếu chỉ cần một phép tính đơn giản, `Collectors.reducing(identity, mapper, op)` cũng có thể kết hợp bước ánh xạ và reduction, nhưng `mapping(..., reducing(...))` đặc biệt dễ mở rộng khi muốn đổi downstream sang loại collector khác.

## 10. Xử lý null và dữ liệu không hợp lệ

`Collectors.mapping` **không tự kiểm tra null**, không sửa dữ liệu nguồn và không đảm bảo downstream chấp nhận mọi giá trị mapper trả về.

Ví dụ tên có thể `null`:

~~~java
record Person(String team, String name) {}

List<Person> persons = java.util.Arrays.asList(
        new Person("DEV", "Lan"),
        new Person("DEV", null)
);
~~~

Nếu dùng `Collectors.mapping(Person::name, Collectors.toList())`, một số triển khai collector danh sách có thể lưu `null`; hợp đồng về kiểu collection kết quả của `Collectors.toList` không nên được dùng để suy ra chính sách kiểm tra dữ liệu nghiệp vụ. Nếu dùng `Collectors.toUnmodifiableList()` (Java 10+), phần tử `null` **bị từ chối** và quá trình thu có thể ném `NullPointerException`.

Cách xử lý nên xuất phát từ yêu cầu:

~~~java
Map<String, List<String>> validNames = persons.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                Collectors.mapping(
                        person -> java.util.Objects.requireNonNull(
                                person.name(), "name is required"
                        ),
                        Collectors.toList()
                )
        ));
// Trường name null gây lỗi tường minh.
~~~

Nếu nghiệp vụ cho phép bỏ tên thiếu mà vẫn giữ khóa nhóm, dùng `Collectors.filtering` trước `mapping` trong downstream:

~~~java
Map<String, List<String>> nonNullNames = persons.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                Collectors.filtering(
                        person -> person.name() != null,
                        Collectors.mapping(
                                Person::name,
                                Collectors.toList()
                        )
                )
        ));
~~~

Với cách thứ hai, nhóm `DEV` vẫn tồn tại, danh sách chỉ có `Lan`. Nếu tất cả thành viên trong một nhóm có tên `null`, nhóm vẫn có danh sách rỗng.

Đặc biệt, `groupingBy` tiêu chuẩn không chấp nhận **khóa classifier bằng `null`**. Hãy chuẩn hóa hoặc kiểm tra giá trị `department`/`team` trước khi thu; đừng nhầm chính sách khóa ngoài của `groupingBy` với chính sách giá trị bên trong `mapping`.

## 11. Hợp đồng thứ tự và khả năng sửa đổi của kết quả

Một collector lồng nhau có **nhiều cấp cấu trúc dữ liệu**, mỗi cấp có hợp đồng riêng. Ví dụ:

~~~java
Map<String, List<String>> result = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(Employee::name, Collectors.toList())
        ));
~~~

- `Map` ngoài ánh xạ mỗi khóa phòng ban đến một danh sách.
- `List` trong giữ các tên mà downstream collector thu được.
- `groupingBy` mặc định không cam kết kiểu Map, thứ tự lặp hoặc tính thread-safe.
- `Collectors.toList()` không cam kết lớp List, khả năng sửa đổi, serialization hay thread-safety.
- Với Stream có encounter order và các collector không đánh dấu unordered, thứ tự gặp phần tử là yếu tố cần tôn trọng khi thu vào danh sách.
- Nếu cần **một kiểu cụ thể** hoặc **thứ tự cụ thể**, hãy chọn supplier/collector phù hợp thay vì dựa vào triển khai mặc định.

Ví dụ yêu cầu cả khóa nhóm theo thứ tự chèn và mỗi nhóm là một `ArrayList` có thể sửa:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;

Map<String, ArrayList<String>> editableByDepartment =
        employees.stream().collect(Collectors.groupingBy(
                Employee::department,
                LinkedHashMap::new,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toCollection(ArrayList::new)
                )
        ));
~~~

Ví dụ này dùng nguồn `List` tuần tự và `LinkedHashMap` nên giữ thứ tự xuất hiện lần đầu của phòng ban khi duyệt. Mỗi giá trị có kiểu `ArrayList<String>` rõ ràng. Nếu kết quả cần **không sửa đổi được** và không chấp nhận `null`, dùng `Collectors.toUnmodifiableList()` ở downstream, nhưng vẫn phải xem riêng cách bảo vệ Map ngoài.

Một danh sách không sửa đổi được cũng **không làm các đối tượng phần tử tự bất biến**: khi mapper trả về đối tượng mutable, tham chiếu bên ngoài vẫn có thể thay đổi nội dung đối tượng đó.

## 12. Parallel stream: mapping không tự bảo đảm hiệu năng và thread safety

Một pipeline có thể dùng `parallelStream()`:

~~~java
Map<String, List<String>> parallelNames = employees.parallelStream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.toList()
                )
        ));
~~~

Collector chuẩn phải hỗ trợ cách chia nguồn, tích lũy các phần riêng và kết hợp đúng hợp đồng. Tuy nhiên, **mapper do người viết cung cấp** phải tránh phụ thuộc vào trạng thái mutable dùng chung:

~~~java
// Sai ý tưởng: biến đếm dùng chung gây tác dụng phụ trong mapper.
int[] counter = {0};

Map<String, List<String>> broken = employees.parallelStream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        employee -> employee.name() + "-" + (++counter[0]),
                        Collectors.toList()
                )
        ));
~~~

Lời gọi `++counter[0]` không an toàn khi nhiều tác vụ chạy đồng thời, và nội dung tên có thể phụ thuộc lịch thực thi. Nếu cần thứ tự hoặc số thứ tự ổn định, hãy tạo chỉ số từ nguồn có thứ tự **trước khi** chạy pipeline, hoặc thiết kế bước đánh số riêng có hợp đồng rõ.

Đối với `groupingBy` thông thường trên parallel stream, bước ghép các Map con có thể tốn chi phí; `groupingByConcurrent` có thể phù hợp khi xử lý không phụ thuộc thứ tự encounter và downstream đáp ứng yêu cầu. Nhưng `groupingByConcurrent` không phải cách tăng tốc mặc định: kết quả và hiệu năng phụ thuộc số lượng khóa, cạnh tranh giữa tác vụ, thứ tự, kích thước dữ liệu và phần tích lũy bên trong.

Với `mapping(..., reducing(...))`, phép gộp như `BigDecimal::add` chính xác có tính kết hợp và dễ chia song song; nếu làm tròn sau mỗi lần cộng, kết quả có thể phụ thuộc cách phân chia. Bảo đảm tính đúng đắn trước khi đo hiệu năng.

## 13. Mẫu thiết kế và những lỗi hay gặp

| Nhu cầu hoặc triệu chứng | Nguyên nhân / lựa chọn | Hướng thực hiện |
| --- | --- | --- |
| Muốn nhóm theo phòng ban nhưng chỉ giữ tên | `Stream.map` trước khi nhóm làm mất thông tin phòng ban | `groupingBy(Employee::department, mapping(Employee::name, toList()))`. |
| `mapping(Employee::skills, toSet())` tạo tập danh sách | Một Employee sinh một `List<String>`, không có bước làm phẳng | Dùng `flatMapping(e -> e.skills().stream(), toSet())`. |
| Không thấy khóa nhóm chỉ có phần tử bị lọc | `stream.filter` chạy trước `groupingBy` | Dùng `groupingBy(..., filtering(..., mapping(...)))` khi cần giữ nhóm rỗng. |
| Muốn tập phần tử phân biệt | Downstream đang dùng `toList()` | Chọn `toSet()` hoặc `toCollection(LinkedHashSet::new)`. |
| Muốn danh sách từng nhóm có thể sửa | `Collectors.toList()` không cam kết tính mutable | Dùng `toCollection(ArrayList::new)` ở downstream. |
| Cần danh sách không sửa được và không có null | Mapper có thể trả `null` | Kiểm tra nguồn, dùng `toUnmodifiableList()` sau khi bảo đảm hợp lệ. |
| Sai kiểu dữ liệu khi ghép nhiều collector | Mapper trả kiểu `U` khác kiểu downstream yêu cầu | Xem chữ ký `T -> U` và kiểu đầu vào của downstream. |
| Tổng tiền khác khi chạy song song | Làm tròn trong combiner hoặc có side effect | Tổng hợp `BigDecimal` chính xác; làm tròn ở bước nghiệp vụ đã xác định. |
| Thứ tự khóa Map bất ngờ | `groupingBy` không bảo đảm thứ tự khóa | Cung cấp `LinkedHashMap::new` hoặc `TreeMap::new` theo nhu cầu. |
| Bộ nhớ cao với số nhóm lớn | Tích lũy nhiều danh sách/tập vào Map | Giảm số nhóm/giá trị lưu, tổng hợp trực tiếp hoặc xử lý theo lô. |

Có thể sử dụng các collector adapter như các khối xây dựng nhỏ: `groupingBy` quyết định **cấp nhóm**, `filtering` quyết định **giữ phần tử nào trong nhóm**, `mapping` quyết định **biến đổi thành giá trị gì**, còn downstream cuối cùng quyết định **thu hoặc tổng hợp theo cách nào**. Mỗi tầng có vai trò độc lập và có thể kiểm tra bằng kiểu dữ liệu.

## 14. Hiệu năng, tài nguyên và tính lazy

`Collectors.mapping` là một phần mô tả phép thu thập; nó **không tự duyệt Stream**. Các thao tác trung gian như `filter` và `map` thường lazy. Chỉ khi gọi `collect(...)`, các phần tử mới được xử lý theo pipeline.

Khả năng phối hợp không làm giảm chi phí vốn có của kết quả:

- `groupingBy(..., mapping(..., toList()))` cần lưu các phần tử được thu vào các danh sách của từng nhóm; bộ nhớ tăng theo số phần tử kết quả.
- `groupingBy(..., mapping(..., toSet()))` cần lưu các giá trị phân biệt, có thể tiết kiệm phần tử trùng nhưng phải quản lý cấu trúc tập.
- `groupingBy(..., mapping(..., reducing(...)))` chỉ lưu một kết quả tổng hợp cho mỗi nhóm (cùng các cấu trúc điều phối), phù hợp nếu không cần giữ mọi phần tử.
- Mapper quá nặng, thao tác I/O trong mapper hoặc việc tạo nhiều DTO có thể chi phối thời gian chạy, bất kể lựa chọn collector.
- Nguồn vô hạn không giới hạn không thể thu vào Map/danh sách hữu hạn nếu collector cần xử lý đến hết nguồn. Cần có giới hạn đầu vào hoặc luồng kết thúc đúng hợp đồng.
- Với Stream từ tài nguyên như `Files.lines`, phải dùng `try-with-resources` để đóng nguồn; `collect` không tự bảo đảm đóng tài nguyên bên ngoài.

Dù API còn hỗ trợ Spliterator, parallel stream và Stream Gatherers, việc dùng các tính năng đó không thay đổi nhiệm vụ chính của downstream `mapping`: chuyển từng phần tử sang kiểu mà collector tiếp theo có thể xử lý. Vòng đời nguồn, điều kiện kết thúc và giới hạn tài nguyên vẫn phải được xem xét riêng.

## 15. Bài tập thực hành

### Bài 1 — Đọc kiểu kết quả

Cho:

~~~java
Map<String, Set<Integer>> lengths = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        e -> e.name().length(),
                        Collectors.toSet()
                )
        ));
~~~

**Câu hỏi:** `T`, `U` và kết quả nhóm `DEV` có ý nghĩa gì?

**Đáp án:** `T = Employee`; `U = Integer` vì mapper lấy độ dài tên. Downstream tạo `Set<Integer>` gồm các độ dài tên **phân biệt** trong mỗi phòng ban. Với `Lan`, `An`, `Huy`, nhóm `DEV` có tập số `{2, 3}`; thứ tự in phần tử của Set không được bảo đảm.

### Bài 2 — Giữ nhóm chỉ có người không hoạt động

Tập nhân viên có phòng `OPS` chỉ gồm `Bình` với `active = false`. Có nên dùng `employees.stream().filter(Employee::active).collect(groupingBy(...))` nếu phải giữ khóa `OPS`?

**Đáp án:** Không. Dùng `groupingBy(Employee::department, filtering(Employee::active, mapping(Employee::name, toList())))` để giữ `OPS -> []`.

### Bài 3 — Dữ liệu con nhiều phần tử

Mỗi `Employee` có `List<String> skills`. Cần kết quả `Map<String, Set<String>>` gồm tập kỹ năng theo phòng ban, không cần giữ ranh giới từng người.

**Đáp án:**

~~~java
Map<String, Set<String>> skills = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.flatMapping(
                        employee -> employee.skills().stream(),
                        Collectors.toSet()
                )
        ));
~~~

`mapping(Employee::skills, toSet())` sẽ thu các **List** thay vì từng kỹ năng.

### Bài 4 — Viết báo cáo tên nối chuỗi

Yêu cầu `DEV -> "Lan, An, Huy"`. Dùng collector nào?

**Đáp án:**

~~~java
Map<String, String> names = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.mapping(
                        Employee::name,
                        Collectors.joining(", ")
                )
        ));
~~~

`mapping` biến Employee thành String, còn `joining` ghép chuỗi trong từng nhóm theo encounter order.

### Bài 5 — Tổng hợp theo khóa

Cho `Stream<Sale>` có `customerId`, `quantity` và `unitPrice`. Cần tổng doanh thu chính xác theo từng khách, không cần danh sách `Sale`.

**Đáp án:** Dùng `groupingBy(Sale::customerId, mapping(sale -> sale.unitPrice().multiply(BigDecimal.valueOf(sale.quantity())), reducing(BigDecimal.ZERO, BigDecimal::add)))`. Cách này gom các số tiền chính xác trong từng nhóm. Thêm bước làm tròn **sau khi** đã xác định chính sách tại cấp báo cáo phù hợp.

### Bài 6 — Kết quả của partitioningBy

Nếu mọi nhân viên đều `active = true`, kết quả của `partitioningBy(Employee::active, mapping(Employee::name, toList()))` có chứa khóa `false` không?

**Đáp án:** Có. `partitioningBy` luôn trả cả `true` và `false`. Khi không có nhân viên thuộc nhánh `false`, downstream `toList` tạo danh sách rỗng cho nhánh đó.

## 16. Ghi nhớ

- `Collectors.mapping(mapper, downstream)` là một **Collector adapter** từ Java 8, biến từng phần tử `T` thành `U` trước khi downstream thu hoặc tổng hợp.
- Khi lồng trong `groupingBy`, classifier có thể tiếp tục dùng dữ liệu gốc `T`, còn danh sách/tập/kết quả tổng hợp của từng nhóm được tạo từ `U`.
- Chọn downstream theo mục đích: `toList` để giữ mọi giá trị, `toSet` để lấy giá trị phân biệt, `joining` để ghép chuỗi, `summingInt` hoặc `reducing` để tổng hợp.
- `Collectors.filtering` có thể giữ khóa nhóm ngay cả khi mọi phần tử của nhóm bị loại bởi predicate ở downstream; `stream.filter` trước `groupingBy` không có tính chất đó.
- `Collectors.flatMapping` nhận một Stream cho mỗi phần tử và làm phẳng; `mapping` chỉ chuyển một phần tử thành một giá trị, ngay cả khi giá trị đó là List.
- Kiểm tra `null`, encounter order, kiểu collection cụ thể, side effect và khả năng kết hợp khi dùng collector trong pipeline song song.
- `mapping` là bước thiết lập Collector, còn `collect` mới kích hoạt terminal operation; bộ nhớ và tài nguyên phải được quản lý theo kích thước và loại nguồn.

**Ý chính:** Dùng `Collectors.mapping` khi muốn **giữ nguyên thông tin để nhóm ở tầng ngoài, nhưng chuyển đổi thành kiểu cần thu ở tầng trong**. Kết hợp rõ ràng các collector giúp pipeline vẫn khai báo, dễ đọc và dễ mở rộng từ danh sách đơn giản sang báo cáo tổng hợp nhiều tầng.
