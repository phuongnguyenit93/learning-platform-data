# Đọc kiểu kết quả của các collector kết hợp trong Java Stream

Khi dùng **Stream.collect()**, một biểu thức nhìn đơn giản như **groupingBy(classifier, counting())** có thể trả **Map<String, Long>**, trong khi **groupingBy(classifier, toList())** lại trả **Map<String, List<Employee>>**. Nếu kết hợp thêm **mapping**, **filtering**, **flatMapping**, **partitioningBy**, **collectingAndThen** hoặc **teeing**, kiểu kết quả có thể trở thành Map lồng nhau, Set, List, Optional hay record tùy theo cấu trúc collector.

Điểm cần học không phải nhớ máy móc hàng chục mẫu cú pháp. Chỉ cần biết **đọc kiểu từ trong ra ngoài**: collector trong cùng quyết định kiểu dữ liệu mỗi nhóm trả về; collector bên ngoài quyết định dữ liệu đó được đặt dưới khóa nào hoặc được biến đổi thêm ra sao.

Bài này thuộc nhóm **Nhóm và phân vùng** của Java Core Functional Programming. Nội dung áp dụng cho Java 17 trở lên, giải thích generic **Collector<T,A,R>**, quy tắc suy kiểu bằng những ví dụ thực tế, phân biệt groupingBy/partitioningBy và các downstream collectors, phân tích lỗi biên dịch thường gặp và có chương trình hoàn chỉnh đã được kiểm thử.

## 1. Collector<T, A, R> — ba chữ cái phải biết

Interface Collector có dạng khái niệm:

~~~java
Collector<T, A, R>
~~~

Trong đó:

- **T — input element type:** kiểu từng phần tử được collector xử lý.
- **A — accumulation type:** kiểu container/trạng thái tích lũy trung gian trong quá trình thu thập.
- **R — result type:** kiểu kết quả sau khi collector hoàn tất.

Với mã:

~~~java
List<String> names = List.of("An", "Binh", "Mai");
List<String> result = names.stream()
    .collect(Collectors.toList());
~~~

Stream có kiểu phần tử **String** và kết quả collect có kiểu **List<String>**. Kiểu tích lũy A là chi tiết của collector và thường không xuất hiện trong khai báo biến kết quả.

Một cách suy luận tiện lợi:

~~~text
Stream<T>
    .collect(Collector<T, A, R>)
    └───────────────────────┘
              R

Kết quả lời gọi collect có kiểu R.
~~~

**Không tự cho rằng R = A hoặc R = T.** Ví dụ **counting()** xử lý các phần tử T tùy ý nhưng trả Long; **summingInt(mapper)** trả Integer; **averagingInt(mapper)** trả Double; **joining()** trả String.

### 1.1. Collector là mô tả phép thu thập, không phải kết quả

~~~java
Collector<String, ?, Long> collector = Collectors.counting();
Long count = names.stream().collect(collector);
~~~

Biến collector là **một đối tượng mô tả cách thu thập**. count là **giá trị kết quả**. Dấu ? trong kiểu Collector trên thể hiện trạng thái tích lũy trung gian không cần đặt tên ở đây; không nên tự đoán chính xác A của collector do JDK cung cấp.

Điều cần đọc khi sử dụng collector hợp thành là **R của collector con**, không phải nội dung nội bộ của accumulator A.

## 2. Phân biệt classifier, downstream và kết quả

Giả sử có dữ liệu nhân sự:

~~~java
record Employee(String department, String name,
                int salary, boolean active) {}
~~~

Và Stream<Employee> làm nguồn. Khi nhóm theo department, callback **Employee::department** có kiểu chức năng **Employee → String**. Nó trả **khóa phân nhóm**, không trả toàn bộ kết quả collect.

### 2.1. groupingBy(classifier) mặc định

~~~java
Map<String, List<Employee>> grouped = employees.stream()
    .collect(Collectors.groupingBy(Employee::department));
~~~

Đọc từ ngoài vào:

1. Stream cung cấp phần tử **Employee**.
2. Classifier biến **Employee → String**; khóa Map là String.
3. Không có downstream tường minh, **groupingBy** mặc định gom các phần tử Employee của mỗi nhóm thành List<Employee>.
4. Kiểu ngoài cùng là **Map<String, List<Employee>>**.

### 2.2. groupingBy(classifier, downstream)

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

Lúc này **downstream = counting()** trả Long. Do đó mỗi khóa String gắn với Long, **không phải List<Employee>**.

Công thức đọc kiểu:

~~~text
T = Employee
K = String do classifier
D = Long do counting()

groupingBy(classifier, downstream)
    -> Map<K, D>
    -> Map<String, Long>
~~~

Đây là quy tắc cốt lõi của bài: **thay downstream là có thể thay hoàn toàn kiểu giá trị của Map**.

### 2.3. groupingBy với map factory

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        TreeMap::new,
        Collectors.counting()
    ));
~~~

Ba đối số gồm classifier, **mapFactory** và downstream. TreeMap::new chọn kiểu Map cụ thể và thứ tự khóa; downstream vẫn quyết định loại giá trị Long.

Chữ ký ý nghĩa:

~~~java
groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
~~~

trả **M**, với ràng buộc M là một Map<K,D>. Ví dụ một Map được khai báo dưới interface Map<String,Long>, implementation thực tế có thể là TreeMap khi mapFactory chọn TreeMap.

**Không nhầm mapFactory với downstream:** TreeMap::new không biến mỗi nhóm thành TreeMap; nó quyết định map **bên ngoài** chứa các nhóm.

## 3. Mẫu đọc kiểu từ trong ra ngoài

Trước khi quan sát một collector kết hợp phức tạp, hãy làm theo bốn bước:

1. **Xác định T** từ Stream nguồn, chẳng hạn Stream<Employee>.
2. **Tính kết quả của collector trong cùng**, ví dụ counting() → Long.
3. **Áp dụng adapter downstream**, ví dụ mapping(Employee::name, toSet()) → Set<String>.
4. **Bọc bởi collector ngoài**, ví dụ groupingBy(Employee::department, ...) → Map<String, Set<String>>.

Ví dụ:

~~~java
Map<String, Set<String>> namesByDepartment =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.mapping(
                Employee::name,
                Collectors.toSet()
            )
        )
    );
~~~

Suy luận:

~~~text
Employee::name             : Employee -> String
toSet()                    : Collector<String, ?, Set<String>>
mapping(Employee::name, ..): Collector<Employee, ?, Set<String>>
Employee::department       : Employee -> String
groupingBy(.., ..)         : Collector<Employee, ?, Map<String, Set<String>>>
collect(..)                : Map<String, Set<String>>
~~~

Trong lời gọi thực tế có các tham số generic ẩn mà compiler tự suy luận. Cây suy luận trên mô tả kiểu cần hiểu, không phải tuyên bố một cách viết chính xác của loại A bên trong mọi collector.

### 3.1. Dấu mũi tên thể hiện biến đổi input, không phải sửa source

**mapping(Employee::name, toSet())** chuyển dữ liệu từng phần tử từ Employee sang String trước khi chuyển cho downstream toSet. Nó không thay đổi Employee ban đầu.

Không nên hiểu mapping trong Collector là Map<K,V>; đây là **phép adapter** bọc một downstream collector.

## 4. Các collector kết thúc thông dụng và kiểu R

| Collector | Kiểu R thông dụng | Ý nghĩa |
| --- | --- | --- |
| toList() | List<T> | Danh sách kết quả |
| toSet() | Set<T> | Tập hợp phần tử |
| toCollection(TreeSet::new) | TreeSet<T> | Collection do factory chỉ định |
| counting() | Long | Số phần tử |
| summingInt(mapper) | Integer | Tổng các giá trị int đã ánh xạ |
| summingLong(mapper) | Long | Tổng các giá trị long đã ánh xạ |
| averagingInt(mapper) | Double | Giá trị trung bình dạng double |
| summarizingInt(mapper) | IntSummaryStatistics | Count, sum, min, max, average |
| joining(delimiter) | String | Nối các CharSequence đầu vào |
| maxBy(comparator) | Optional<T> | Phần tử tối đa, có thể không tồn tại |
| minBy(comparator) | Optional<T> | Phần tử tối thiểu, có thể không tồn tại |
| reducing(identity, op) | T | Tổng hợp theo toán tử và identity |
| mapping(mapper, downstream) | R của downstream | Ánh xạ trước khi thu thập |
| filtering(predicate, downstream) | R của downstream | Lọc bên trong downstream |
| flatMapping(mapper, downstream) | R của downstream | Làm phẳng nhiều phần tử trước downstream |
| collectingAndThen(downstream, finisher) | RR của finisher | Hoàn thiện kết quả R thành RR |
| teeing(down1, down2, merger) | R của merger | Kết hợp hai kết quả downstream |

Kiểu R trong bảng là **kiểu giá trị kết quả** mà collector trả về; khi lồng dưới groupingBy, R trở thành **kiểu value của Map**.

Ví dụ:

~~~java
Map<String, Double> avgSalary = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.averagingInt(Employee::salary)
    ));
~~~

Vì averagingInt trả Double, Map không có kiểu Integer, dù mapper Employee::salary trả int.

## 5. mapping: đổi kiểu phần tử trước khi gom

Collector **mapping(mapper, downstream)** thích hợp khi muốn giữ grouping từ Employee nhưng bên trong mỗi nhóm chỉ lưu tên, mã, hoặc giá trị chuyển đổi.

~~~java
Map<String, List<String>> names =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.mapping(
                Employee::name,
                Collectors.toList()
            )
        )
    );
~~~

Kiểu của từng bước:

~~~text
Stream<Employee>
    |
groupingBy(Employee -> String)
    |
mapping(Employee -> String, toList())
    |
Map<String, List<String>>
~~~

**Không phải Map<String,List<Employee>>**, bởi mapping đã biến Employee thành String trước khi downstream toList.

Muốn loại tên trùng và có thứ tự từ điển:

~~~java
Map<String, TreeSet<String>> names =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            TreeMap::new,
            Collectors.mapping(
                Employee::name,
                Collectors.toCollection(TreeSet::new)
            )
        )
    );
~~~

Ở đây:

- TreeMap::new chọn **map bên ngoài** sắp khóa department.
- TreeSet::new chọn **collection của mỗi nhóm** sắp và loại trùng tên.
- Kết quả Map<String,TreeSet<String>>. Nếu khai báo Map<String,Set<String>> với kiểu collector được suy luận phù hợp, interface Set cũng có thể là một loại giá trị tổng quát hợp lệ ở điểm sử dụng.

### 5.1. Không nhầm mapping với Stream.map

Một cách viết khác:

~~~java
List<String> names = employees.stream()
    .map(Employee::name)
    .toList();
~~~

Khi map chạy **trước groupingBy**, stream đã thành Stream<String>, không còn Employee::department để nhóm, trừ khi giữ lại thông tin department dưới một kiểu trung gian.

Với groupingBy(Employee::department, mapping(Employee::name,...)), classifier vẫn nhìn thấy Employee, còn downstream nhận String. Đây là khác biệt cơ bản khi **cần phân nhóm theo thuộc tính A nhưng thu thập thuộc tính B**.

## 6. filtering: lọc bên trong nhóm và giữ kiểu downstream

Collector **filtering(predicate, downstream)** được thêm từ Java 9. Nó không thay đổi kiểu R của downstream; nó chọn phần tử nào đi tiếp vào collector đó.

~~~java
Map<String, Long> activeCounts =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.filtering(
                Employee::active,
                Collectors.counting()
            )
        )
    );
~~~

Kiểu:

~~~text
filtering(Employee -> boolean, counting())
    -> Collector<Employee, ?, Long>

groupingBy(Employee -> String, filtering(...))
    -> Collector<Employee, ?, Map<String, Long>>
~~~

### 6.1. Filtering bên trong grouping khác Stream.filter bên ngoài

Giả sử phòng HR có nhân viên nhưng **không ai active**.

Cách A — lọc trước:

~~~java
Map<String, Long> outerFiltered = employees.stream()
    .filter(Employee::active)
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

HR không có nhân viên đi đến groupingBy, nên **có thể không xuất hiện khóa HR** trong kết quả.

Cách B — gom trước, lọc trong downstream:

~~~java
Map<String, Long> innerFiltered = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.filtering(
            Employee::active, Collectors.counting())
    ));
~~~

Classifier đã tạo nhóm HR từ các phần tử nguồn. Downstream filtering chặn các phần tử inactive đi tới counting, nên **HR vẫn có thể xuất hiện với giá trị 0**. Đây là khác biệt ngữ nghĩa quan trọng, không phải chỉ là khác biệt cú pháp.

Các nhóm được tạo khi classifier thấy một phần tử nguồn; nếu nguồn không có phòng ban nào, filtering không tự tạo khóa cho phòng ban chưa tồn tại.

### 6.2. Kết hợp filtering và mapping

~~~java
Map<String, List<String>> activeNames =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.filtering(
                Employee::active,
                Collectors.mapping(
                    Employee::name, Collectors.toList())
            )
        )
    );
~~~

Suy từ trong ra ngoài:

1. toList() trên String → List<String>.
2. mapping Employee → String, giữ kết quả List<String>.
3. filtering giữ kết quả List<String>.
4. grouping theo department String → Map<String,List<String>>.

Nhóm có toàn nhân viên inactive có thể hiện diện với **List<String> rỗng**.

## 7. partitioningBy: Map<Boolean,D>, không phải Map<K,D>

**partitioningBy(predicate)** tách dữ liệu theo hai phía boolean: false và true. Collector mặc định dùng List<T> làm downstream:

~~~java
Map<Boolean, List<Employee>> byActive =
    employees.stream().collect(
        Collectors.partitioningBy(Employee::active)
    );
~~~

Thay downstream thành counting:

~~~java
Map<Boolean, Long> counts =
    employees.stream().collect(
        Collectors.partitioningBy(
            Employee::active,
            Collectors.counting()
        )
    );
~~~

Đọc kiểu:

~~~text
Employee::active : Employee -> boolean
counting()       : Long
partitioningBy   : Map<Boolean, Long>
~~~

**Khóa Boolean được quyết định bởi partitioningBy**, không phụ thuộc vào kiểu trả về của predicate; predicate trả boolean để chọn hai phía.

Đặc tính quan trọng: Map do partitioningBy trả có **hai khóa false và true**, kể cả khi một phía không có phần tử. Với counting, phía rỗng có giá trị 0; với toList, phía rỗng là danh sách rỗng.

~~~java
Map<Boolean, Long> counts = employees.stream().collect(
    Collectors.partitioningBy(Employee::active, Collectors.counting()));

System.out.println(counts.get(false));
System.out.println(counts.get(true));
~~~

Không nên dựa vào **thứ tự iteration của Map<Boolean,D>** khi in toàn bộ Map; muốn stdout có thứ tự chắc chắn, truy cập từng khóa bằng get(false)/get(true).

### 7.1. groupingBy boolean có tương đương partitioningBy không?

~~~java
Map<Boolean, List<Employee>> groupByBoolean =
    employees.stream().collect(
        Collectors.groupingBy(Employee::active)
    );
~~~

Về mặt loại giá trị, cả hai đều có thể là Map<Boolean,List<Employee>>. Nhưng **groupingBy không nhất thiết tạo khóa cho phía không xuất hiện**. partitioningBy được thiết kế cho hai phân vùng và cung cấp cả hai khóa.

Vì thế **kiểu Java giống nhau không chứng minh ngữ nghĩa giống nhau**. Cần xem cấu trúc collector và hợp đồng của nó.

## 8. Nhóm lồng nhóm: Map<K1,Map<K2,R>>

Một groupingBy có downstream là groupingBy khác tạo map lồng nhau:

~~~java
Map<String, Map<Boolean, List<Employee>>> nested =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.groupingBy(
                Employee::active
            )
        )
    );
~~~

Cách đọc:

1. Inner groupingBy(Employee::active) → Map<Boolean,List<Employee>>.
2. Outer groupingBy(Employee::department, inner) → Map<String,Map<Boolean,List<Employee>>>.

Nếu thay inner bằng partitioningBy và mapping tên:

~~~java
Map<String, Map<Boolean, List<String>>> nested =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.partitioningBy(
                Employee::active,
                Collectors.mapping(
                    Employee::name,
                    Collectors.toList()
                )
            )
        )
    );
~~~

Nhìn từ trong ra:

~~~text
toList()                             -> List<String>
mapping(Employee::name, ...)         -> List<String>
partitioningBy(Employee::active,...) -> Map<Boolean,List<String>>
groupingBy(Employee::department,...) -> Map<String,Map<Boolean,List<String>>>
~~~

Với mỗi department có dữ liệu đầu vào, partitioningBy bên trong luôn tạo cả false và true. Ví dụ một phòng ban chỉ có nhân viên inactive sẽ có List<String> rỗng tại khóa true.

### 8.1. Ba lớp Map không phải lúc nào cũng cần thiết

Một collector nhiều tầng có thể cho kết quả rất phức tạp:

~~~text
Map<String, Map<Boolean, Map<Integer, List<Employee>>>>
~~~

Để hiểu nó, đọc **từ lá vào gốc**, xác định mỗi classifier và downstream tương ứng. Khi API trở nên khó đọc, có thể:

- Tạo biến collector có kiểu đầy đủ.
- Tạo record cho nhóm kết quả quan trọng.
- Tách thành những bước xử lý có tên.
- Dùng DTO kết quả nếu cấu trúc Map lồng nhau không thể hiện nghiệp vụ rõ ràng.

Đừng cố tối ưu số dòng mã bằng cách làm người đọc phải giải mã một cây generic quá sâu.

## 9. flatMapping: một phần tử tạo nhiều giá trị downstream

Kể từ Java 9, **flatMapping(mapper, downstream)** cho phép mỗi input T tạo một Stream<U>, sau đó gom tất cả U vào downstream.

Giả sử Employee có List<String> skills:

~~~java
record Employee(String department, String name,
                int salary, boolean active, List<String> skills) {}
~~~

Lấy tập kỹ năng theo phòng:

~~~java
Map<String, Set<String>> skillsByDepartment =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.flatMapping(
                employee -> employee.skills().stream(),
                Collectors.toSet()
            )
        )
    );
~~~

Suy luận:

~~~text
T = Employee
mapper : Employee -> Stream<String>
downstream toSet() : Set<String>
outer grouping key : String
result : Map<String,Set<String>>
~~~

Nếu thay downstream thành **toCollection(TreeSet::new)**, kiểu value là TreeSet<String>, có thể dùng để in kết quả ổn định và theo thứ tự từ điển.

**Phân biệt mapping và flatMapping:**

- mapping(Employee::skills, toList()) sẽ tạo **List<List<String>>** cho mỗi nhóm.
- flatMapping(e -> e.skills().stream(), toList()) tạo **List<String>** đã làm phẳng.
- flatMapping(..., toSet()) tạo **Set<String>** đã làm phẳng và loại giá trị trùng theo equality.

FlatMapping quản lý việc đóng Stream con được mapper trả theo hợp đồng API khi xử lý xong. Dù vậy, callback không nên tạo các tài nguyên I/O cần sở hữu phức tạp mà không hiểu rõ vòng đời.

## 10. collectingAndThen: biến R thành kết quả sau cùng RR

**collectingAndThen(downstream, finisher)** là adapter thực hiện collector con, rồi áp dụng một Function lên kết quả:

~~~java
Collector<T, A, RR> wrapped =
    Collectors.collectingAndThen(
        downstream,
        result -> finish(result)
    );
~~~

Đây là **mã minh họa kiểu học thuật**, dùng T, A, RR, downstream và finish chưa khai báo trong lớp; không phải tệp chạy độc lập.

Kiểu R của collector con có thể **khác** kiểu RR của finisher. Ví dụ muốn mỗi nhóm có List<String> không thể chỉnh sửa:

~~~java
Map<String, List<String>> names =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.mapping(
                Employee::name,
                Collectors.collectingAndThen(
                    Collectors.toList(),
                    List::copyOf
                )
            )
        )
    );
~~~

Suy luận:

~~~text
toList()                     -> List<String>
collectingAndThen(...copyOf) -> List<String> không thể chỉnh sửa
mapping(Employee::name,...)  -> List<String>
groupingBy(department,...)   -> Map<String,List<String>>
~~~

Kiểu Java của kết quả **vẫn là List<String>**: Java generic **không thể hiện tính bất biến** của List. Tính không thể chỉnh sửa đến từ hợp đồng của List.copyOf, không phải từ type parameter.

Với một finisher trả **kiểu khác**, sự thay đổi kiểu dễ nhìn thấy hơn:

~~~java
Map<String, Integer> nameLengthsByDepartment =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.collectingAndThen(
                Collectors.mapping(Employee::name, Collectors.toList()),
                names -> names.stream().mapToInt(String::length).sum()
            )
        )
    );
~~~

Ở đây downstream trước finisher là List<String>, nhưng finisher tính tổng độ dài và trả Integer, nên value Map là Integer.

### 10.1. Chú ý null và tính bất biến

List.copyOf không chấp nhận phần tử null; nếu mapping có thể trả null, cần xử lý trước. Ngoài ra, copyOf chỉ bảo vệ **cấu trúc danh sách**; các object mutable bên trong (nếu có) vẫn có thể đổi trạng thái.

Collectors.toList **không cam kết một implementation cụ thể hoặc khả năng chỉnh sửa cố định**, còn Stream.toList() (Java 16+) bảo đảm trả List không thể chỉnh sửa. Nếu cần kiểu collection cụ thể hoặc bất biến ở ranh giới, hãy chọn collector hoặc finisher thích hợp.

## 11. teeing: hai downstream tạo một kết quả tổng hợp

Kể từ Java 12, **teeing(downstream1, downstream2, merger)** phân phối từng phần tử cho **hai collector** rồi ghép hai kết quả bằng merger.

Ví dụ đếm nhân viên và cộng tổng lương thành một record:

~~~java
record DeptStats(long count, int totalSalary) {}

Map<String, DeptStats> stats =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.teeing(
                Collectors.counting(),
                Collectors.summingInt(Employee::salary),
                DeptStats::new
            )
        )
    );
~~~

Đọc kiểu từng tầng:

~~~text
counting()                 -> Long
summingInt(Employee::salary) -> Integer
DeptStats::new             : (Long, Integer) -> DeptStats
teeing(...)                -> DeptStats
groupingBy(department,...) -> Map<String,DeptStats>
~~~

**Hai collector con không tạo Map<Long,Integer>.** Chúng tạo hai giá trị, rồi merger quyết định **R cuối cùng**. Với merger trả record DeptStats, giá trị mỗi nhóm là DeptStats.

### 11.1. Merger có thể trả kiểu khác

~~~java
Map<String, String> labels = employees.stream().collect(
    Collectors.groupingBy(
        Employee::department,
        Collectors.teeing(
            Collectors.counting(),
            Collectors.summingInt(Employee::salary),
            (count, total) -> count + " employees, salary=" + total
        )
    )
);
~~~

Bởi merger trả String, Map value là String.

Khi các kết quả tổng hợp cần nhiều trường dữ liệu, record thường dễ hiểu hơn một chuỗi đã format. Cần xét giới hạn int khi summingInt tính tiền/lương; với sản phẩm thật, có thể dùng summingLong hoặc BigDecimal theo yêu cầu độ chính xác.

## 12. summarizingInt, averagingInt, reducing và Optional

Có những collector trả kiểu không trực giác nếu chỉ nhìn đầu vào.

### 12.1. summarizingInt → IntSummaryStatistics

~~~java
Map<String, IntSummaryStatistics> salaries =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.summarizingInt(Employee::salary)
        )
    );
~~~

Mỗi value không phải Integer hay List<Integer> mà là **IntSummaryStatistics**, có các phương thức **getCount(), getSum(), getMin(), getMax(), getAverage()**. Một value có thể cung cấp nhiều chỉ số.

Nếu nhóm không rỗng thì thống kê có dữ liệu; trong groupingBy, một khóa nhóm chỉ được tạo nếu classifier đã thấy phần tử đầu vào.

### 12.2. averagingInt → Double

~~~java
Map<String, Double> averages = employees.stream().collect(
    Collectors.groupingBy(
        Employee::department,
        Collectors.averagingInt(Employee::salary)
    )
);
~~~

Dù Employee.salary là int, **average có thể có phần lẻ**, vì vậy downstream trả Double. Kết quả của nhóm rỗng được xử lý theo hợp đồng collector tương ứng, ví dụ averagingInt có thể cho 0.0 trong ngữ cảnh downstream được cấp một nhóm rỗng.

### 12.3. maxBy → Optional<Employee>

~~~java
Map<String, Optional<Employee>> highestPaid =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.maxBy(
                Comparator.comparingInt(Employee::salary)
            )
        )
    );
~~~

Downstream maxBy trả Optional<Employee>. Vì groupingBy đặt kết quả downstream dưới mỗi khóa department, kiểu Map value trở thành Optional<Employee>.

Có thể dùng collectingAndThen để đổi value sang một loại khác:

~~~java
Map<String, String> topNames =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.collectingAndThen(
                Collectors.maxBy(
                    Comparator.comparingInt(Employee::salary)),
                employee -> employee.map(Employee::name).orElse("none")
            )
        )
    );
~~~

**Optional của nhóm rỗng** có thể xuất hiện khi một downstream như filtering loại hết phần tử trong nhóm; không được tự động gọi Optional.get mà chưa kiểm tra.

### 12.4. reducing thay đổi overload là đổi kiểu

~~~java
Collectors.reducing(Integer::sum)
~~~

Overload không identity này trả **Optional<Integer>** khi thu các Integer.

~~~java
Collectors.reducing(0, Integer::sum)
~~~

Overload có identity trả **Integer**. Nếu dùng mapping để biến Employee thành salary trước:

~~~java
Map<String, Integer> totals = employees.stream().collect(
    Collectors.groupingBy(
        Employee::department,
        Collectors.mapping(
            Employee::salary,
            Collectors.reducing(0, Integer::sum)
        )
    )
);
~~~

Kiểu value là Integer. Nhưng khi chỉ tính tổng trường int, **summingInt(Employee::salary)** ngắn và rõ hơn.

## 13. Mẫu suy kiểu khi lồng nhiều collector

Giả sử cần “mỗi phòng có hai nhóm active và inactive; ở mỗi nhóm chỉ chứa tên nhân viên”. Biểu thức:

~~~java
Map<String, Map<Boolean, List<String>>> result =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department,
            Collectors.partitioningBy(
                Employee::active,
                Collectors.mapping(
                    Employee::name,
                    Collectors.toList()
                )
            )
        )
    );
~~~

Có thể đi từ trong ra ngoài:

| Bước | Kiểu kết quả R sau bước đó |
| --- | --- |
| toList cho String | List<String> |
| mapping(Employee::name, toList) | List<String> |
| partitioningBy(Employee::active, ...) | Map<Boolean,List<String>> |
| groupingBy(Employee::department, ...) | Map<String,Map<Boolean,List<String>>> |
| Stream<Employee>.collect(...) | Map<String,Map<Boolean,List<String>>> |

Chú ý: **Employee::name trả String, nhưng mapping vẫn là Collector cho input Employee**. Sau khi mapping áp dụng, downstream mới nhận String. Tương tự, partitioningBy không làm mất thông tin kiểu của collector kết quả; nó chỉ thêm một lớp Map<Boolean, ...>.

### 13.1. Cách đọc một generic type dài

~~~java
Map<String, Map<Boolean, List<String>>>
~~~

Tách thành lời nói:

- Map ngoài: **String department → ...**
- Map trong: **Boolean active → ...**
- List ở lá: **danh sách tên String**.

Nếu Map lồng ba hoặc bốn cấp, nên xem xét tạo kiểu record/DTO thể hiện nghiệp vụ thay vì cứ lồng Map. Không phải vì cú pháp generic sai, mà vì kiểu càng sâu càng dễ đọc nhầm dữ liệu đi cùng khóa nào.

## 14. Kết quả có nhiều hình dạng nhưng quy luật nhất quán

| Collector kết hợp | Kiểu kết quả dự đoán |
| --- | --- |
| groupingBy(department) | Map<String,List<Employee>> |
| groupingBy(department, counting()) | Map<String,Long> |
| groupingBy(department, averagingInt(salary)) | Map<String,Double> |
| groupingBy(department, summarizingInt(salary)) | Map<String,IntSummaryStatistics> |
| groupingBy(department, mapping(name,toSet())) | Map<String,Set<String>> |
| groupingBy(department, filtering(active,counting())) | Map<String,Long> |
| groupingBy(department, flatMapping(skills,toSet())) | Map<String,Set<String>> |
| partitioningBy(active) | Map<Boolean,List<Employee>> |
| partitioningBy(active,counting()) | Map<Boolean,Long> |
| groupingBy(department,partitioningBy(active)) | Map<String,Map<Boolean,List<Employee>>> |
| groupingBy(department,teeing(counting(),summingInt(salary),DeptStats::new)) | Map<String,DeptStats> |
| groupingBy(department,collectingAndThen(maxBy(bySalary),toName)) | Map<String,String> |

Trong bảng, department, active, salary, name và skills là **tên gợi nghĩa cho function/lambda tương ứng**, không phải Java syntax đầy đủ độc lập. Muốn kiểm chứng, xem chương trình Java hoàn chỉnh ở phần tiếp theo.

## 15. Chương trình Java 17+ hoàn chỉnh

Ví dụ sử dụng một record Employee và dữ liệu năm nhân viên, nhóm theo department. Ta dùng **TreeMap** và **TreeSet** tại các điểm cần thứ tự ổn định để stdout dễ kiểm chứng, thay vì dựa vào thứ tự mặc định không được bảo đảm của HashMap/HashSet.

Tạo tệp **CollectorTypeDemo.java**:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class CollectorTypeDemo {
    record Employee(String department, String name,
                    int salary, boolean active, List<String> skills) {}
    record DeptStats(long count, int totalSalary) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
            new Employee("Tech", "An", 100, true, List.of("Java", "SQL")),
            new Employee("Tech", "Binh", 200, false, List.of("Java", "Cloud")),
            new Employee("Sales", "Chi", 80, true, List.of("CRM")),
            new Employee("Sales", "Dung", 120, true, List.of("CRM", "SQL")),
            new Employee("HR", "Em", 90, false, List.of("Excel"))
        );

        Map<String, Long> counts = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.counting()));
        System.out.println("counts=" + counts);

        Map<String, Long> activeCounts = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.filtering(Employee::active, Collectors.counting())));
        System.out.println("activeCounts=" + activeCounts);

        Map<String, TreeSet<String>> names = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.mapping(Employee::name,
                    Collectors.toCollection(TreeSet::new))));
        System.out.println("names=" + names);

        Map<Boolean, Long> activePartitions = employees.stream().collect(
            Collectors.partitioningBy(Employee::active, Collectors.counting()));
        System.out.println("partitions=false:" + activePartitions.get(false)
            + ",true:" + activePartitions.get(true));

        Map<String, DeptStats> stats = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.teeing(
                    Collectors.counting(),
                    Collectors.summingInt(Employee::salary),
                    DeptStats::new)));
        System.out.println("stats=" + stats);

        Map<String, TreeSet<String>> skills = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.flatMapping(
                    e -> e.skills().stream(),
                    Collectors.toCollection(TreeSet::new))));
        System.out.println("skills=" + skills);

        Map<String, List<String>> immutableNames = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.mapping(Employee::name,
                    Collectors.collectingAndThen(
                        Collectors.toList(), List::copyOf))));
        System.out.println("immutableNames=" + immutableNames);
        try {
            immutableNames.get("HR").add("Someone");
        } catch (UnsupportedOperationException ex) {
            System.out.println("immutableList=true");
        }

        Map<String, Double> averages = employees.stream().collect(
            Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.averagingInt(Employee::salary)));
        System.out.println("averages=" + averages);

        Map<String, IntSummaryStatistics> summaries =
            employees.stream().collect(Collectors.groupingBy(
                Employee::department,
                TreeMap::new,
                Collectors.summarizingInt(Employee::salary)));
        System.out.println("hrMin=" + summaries.get("HR").getMin());

        Map<String, Map<Boolean, List<String>>> nested =
            employees.stream().collect(
                Collectors.groupingBy(Employee::department, TreeMap::new,
                    Collectors.partitioningBy(Employee::active,
                        Collectors.mapping(Employee::name, Collectors.toList()))));
        System.out.println("techInactive=" + nested.get("Tech").get(false));
        System.out.println("hrActive=" + nested.get("HR").get(true));

        Map<String, Long> upstreamFilter = employees.stream()
            .filter(Employee::active)
            .collect(Collectors.groupingBy(Employee::department, TreeMap::new,
                Collectors.counting()));
        System.out.println("upstreamHasHR=" + upstreamFilter.containsKey("HR"));
        System.out.println("downstreamHasHR=" + activeCounts.containsKey("HR"));
    }
}
~~~

Biên dịch và chạy (JDK 17+):

~~~bash
javac CollectorTypeDemo.java
java CollectorTypeDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
counts={HR=1, Sales=2, Tech=2}
activeCounts={HR=0, Sales=2, Tech=1}
names={HR=[Em], Sales=[Chi, Dung], Tech=[An, Binh]}
partitions=false:2,true:3
stats={HR=DeptStats[count=1, totalSalary=90], Sales=DeptStats[count=2, totalSalary=200], Tech=DeptStats[count=2, totalSalary=300]}
skills={HR=[Excel], Sales=[CRM, SQL], Tech=[Cloud, Java, SQL]}
immutableNames={HR=[Em], Sales=[Chi, Dung], Tech=[An, Binh]}
immutableList=true
averages={HR=90.0, Sales=100.0, Tech=150.0}
hrMin=90
techInactive=[Binh]
hrActive=[]
upstreamHasHR=false
downstreamHasHR=true
~~~

### 15.1. Đọc từng kiểu từ kết quả

- **counts:** groupingBy(..., counting()) → Map<String,Long>. Long values là 1, 2, 2.
- **activeCounts:** groupingBy(..., filtering(active,counting())) → Map<String,Long>. HR vẫn có khóa nhưng giá trị 0.
- **names:** groupingBy(..., mapping(name,toCollection(TreeSet))) → Map<String,TreeSet<String>>. Tên trong từng nhóm được sắp xếp.
- **partitions:** partitioningBy(active,counting()) → Map<Boolean,Long>. Có hai giá trị false=2 và true=3.
- **stats:** groupingBy(...,teeing(counting(),summingInt(salary),DeptStats::new)) → Map<String,DeptStats>. Từng record chứa hai kết quả tổng hợp.
- **skills:** flatMapping từng List<String> skills thành Stream<String>, rồi thu về TreeSet<String>; Map value không phải List<List<String>>.
- **immutableNames:** mapping(name,collectingAndThen(toList,List::copyOf)) → List<String> không thể chỉnh sửa. Test add phát sinh UnsupportedOperationException.
- **averages:** averagingInt trả Double, không phải Integer; HR 90.0, Sales 100.0, Tech 150.0.
- **hrMin:** summarizingInt trả IntSummaryStatistics, getMin() cho HR = 90.
- **nested:** groupingBy(...,partitioningBy(...,mapping(name,toList()))) → Map<String,Map<Boolean,List<String>>>. Tech inactive có Binh; HR active không có ai nên List rỗng.
- **upstreamHasHR=false:** lọc active trước grouping làm HR không còn phần tử để tạo khóa.
- **downstreamHasHR=true:** filtering bên trong downstream vẫn giữ nhóm HR với kết quả counting=0.

Trong chương trình, Map bên ngoài được tạo bằng TreeMap để in khóa HR, Sales, Tech theo thứ tự có thể kiểm chứng. Với partitioningBy, thay vì in map trực tiếp và dựa vào thứ tự triển khai, chương trình truy cập từng Boolean key.

## 16. Những lỗi đọc kiểu và thiết kế thường gặp

### 16.1. Gán sai kiểu vì chỉ nhìn Stream<T>

~~~java
// SAI: counting() trả Long chứ không phải List<Employee>.
Map<String, List<Employee>> counts =
    employees.stream().collect(
        Collectors.groupingBy(
            Employee::department, Collectors.counting()));
~~~

Cách sửa:

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department, Collectors.counting()));
~~~

Compiler sẽ báo lỗi ràng buộc generic nếu loại value Map không khớp downstream. Hãy đọc kết quả collector con trước.

### 16.2. Nhầm số lượng với tổng lương

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department, Collectors.counting()));
~~~

Đây là **số nhân viên**. Muốn tổng lương:

~~~java
Map<String, Integer> totals = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.summingInt(Employee::salary)));
~~~

Tên tổng lương không biến kết quả counting thành tổng số. Xem chữ ký downstream và mapper cụ thể.

### 16.3. Tưởng groupingBy trả TreeMap theo mặc định

groupingBy(classifier,downstream) mặc định không bảo đảm kiểu Map cụ thể hoặc iteration order. Nếu cần TreeMap:

~~~java
Map<String, Long> ordered = employees.stream().collect(
    Collectors.groupingBy(Employee::department,
        TreeMap::new, Collectors.counting()));
~~~

Không nên phụ thuộc vào cách Map.toString tình cờ sắp khóa ở một lần chạy.

### 16.4. Nhầm HashSet/TreeSet với List

Collectors.toSet không bảo đảm thứ tự iteration; một tập hợp không có khái niệm vị trí lặp như List. Nếu cần sắp xếp, dùng toCollection(TreeSet::new) với key Comparable hoặc Comparator phù hợp.

### 16.5. Quên downstream filtering khác upstream filter

Đặt Stream.filter(active) trước grouping loại cả khóa của nhóm không còn phần tử; Collectors.filtering(active,counting()) bên trong grouping có thể giữ khóa với 0. Hai kết quả đều Map<String,Long> nhưng **không tương đương về tập khóa**.

### 16.6. Tưởng collectingAndThen luôn giữ kiểu R

Finisher có thể biến List<T> thành Integer, Optional<T> thành String, hoặc một thống kê thành DTO. **Kiểu cuối cùng là kiểu trả về finisher**, không nhất thiết là kiểu của downstream nguyên gốc.

### 16.7. Tưởng teeing trả cặp giá trị tự động

teeing yêu cầu merger để tạo **một kết quả R**. Nó không tự trả Pair, Map hoặc List; kiểu cuối cùng do merger chỉ định.

### 16.8. Tưởng partitioningBy chỉ chứa khóa xuất hiện

partitioningBy có cả false và true. Trường hợp một phía rỗng vẫn có giá trị do downstream tạo, ví dụ 0, List rỗng hoặc Optional.empty.

### 16.9. Dùng List.copyOf với null

List.copyOf không chấp nhận phần tử null. Nếu mapper có thể trả null, phải lọc, thay thế hoặc thiết kế giá trị biểu diễn thiếu một cách tường minh.

### 16.10. Nhầm kiểu khai báo với runtime class

~~~java
Map<String, List<String>> names = ...;
~~~

Kiểu khai báo này không chứng minh map ngoài là HashMap, TreeMap, hay danh sách bên trong là ArrayList. Tương tự, Map<String,Double> cho biết kiểu value là Double, không đảm bảo thứ tự, mức làm tròn hoặc tất cả khóa có mặt.

### 16.11. Dùng raw type để né compiler

~~~java
// Tránh: mất thông tin generic.
Map grouped = employees.stream().collect(...);
~~~

Đây là biểu thức minh họa với dấu ba chấm, không phải chương trình biên dịch độc lập. Raw type che thông tin về K và D, làm lỗi dễ xuất hiện khi lấy giá trị từ Map. Dùng **Map<String,Long>**, **Map<String,Set<String>>**, **var** khi biểu thức sáng rõ, hoặc tách biến collector có kiểu đầy đủ.

### 16.12. Collector thích hợp cho song song không đồng nghĩa biến bên ngoài được chia sẻ an toàn

Collectors.groupingBy và Collectors.groupingByConcurrent khác nhau về hợp đồng và đặc tính. Không nên tự ý cập nhật Map mutable bên ngoài từ lambda để “tự dựng collector”, nhất là khi parallelStream. Sử dụng Collectors phù hợp và đọc các đặc tính như CONCURRENT, UNORDERED, IDENTITY_FINISH khi thiết kế collector tùy chỉnh.

Không suy ra rằng Stream.parallel tự biến mọi downstream List/Set thành concurrent collection cho caller tự do chỉnh sửa. Kết quả thu xong còn phải dùng đúng hợp đồng mutability của nó.

## 17. Quy trình đọc lỗi suy luận generic

Khi compiler báo không thể suy luận type variables T, K, A, D, M, hãy phân tích theo thứ tự:

1. **Xác định Stream<T> thực tế.** Employee hay String? Một Stream đã map trước đó có thể đổi T.
2. **Xác định classifier T → K.** Kiểu khóa Map là gì?
3. **Xác định downstream đang nhận T hay U.** mapping đổi kiểu phần tử, filtering giữ kiểu phần tử, flatMapping tạo nhiều U từ một T.
4. **Xác định kiểu R cuối của downstream.** counting → Long, averagingInt → Double, toSet → Set<T>, teeing → kết quả merger, collectingAndThen → kết quả finisher.
5. **Bọc Map ngoài.** groupingBy → Map<K,R>, partitioningBy → Map<Boolean,R>.
6. **Đối chiếu với kiểu biến bên trái.** Nếu không tương thích, sửa logic collector hoặc kiểu biến; không vội cast sang raw Map.
7. **Kiểm tra null và mutability.** Dù generic đúng, dữ liệu có thể gây NullPointerException hoặc UnsupportedOperationException.
8. **Đảm bảo có chiến lược về thứ tự.** Nếu test stdout, chọn TreeMap/TreeSet hoặc truy cập rõ khóa thay vì dựa vào HashMap iteration.

### 17.1. Dùng var có giúp không?

~~~java
var grouped = employees.stream().collect(
    Collectors.groupingBy(
        Employee::department,
        Collectors.counting()));
~~~

Compiler có thể suy ra kiểu biểu thức mà không cần bạn viết Map<String,Long>. Nhưng điều đó **không thay đổi kiểu thực tế** hoặc giải quyết thiết kế sai. Với logic public API hoặc đoạn khó đọc, khai báo kiểu đầy đủ đôi khi giúp người đọc nhanh nhận ra cấu trúc kết quả.

### 17.2. Đọc kiểu tại ranh giới phương thức

Một phương thức dịch vụ có thể khai báo:

~~~java
static Map<String, Long> countByDepartment(List<Employee> employees) {
    return employees.stream()
        .collect(Collectors.groupingBy(
            Employee::department, Collectors.counting()));
}
~~~

Khi business logic có ý nghĩa rõ, đặt tên phương thức **countByDepartment** giúp người gọi không phải hiểu hết cây collector tại mỗi điểm sử dụng.

## 18. Checklist suy luận nhanh

| Câu hỏi | Gợi ý trả lời |
| --- | --- |
| Stream xử lý phần tử kiểu gì? | T trong Stream<T> |
| groupingBy lấy khóa kiểu gì? | K là kết quả classifier |
| partitioningBy lấy khóa kiểu gì? | Boolean |
| counting trả gì? | Long |
| summingInt trả gì? | Integer |
| averagingInt trả gì? | Double |
| summarizingInt trả gì? | IntSummaryStatistics |
| mapping thay đổi gì? | Đổi input T thành U cho downstream |
| filtering thay đổi gì? | Giữ kiểu input, chọn phần tử vào downstream |
| flatMapping thay đổi gì? | Tạo Stream<U> rồi đưa nhiều U vào downstream |
| collectingAndThen trả gì? | Kiểu sau finisher |
| teeing trả gì? | Kiểu kết quả merger |
| groupingBy bọc kiểu nào? | Map<K, downstream result> |
| partitioningBy bọc kiểu nào? | Map<Boolean, downstream result> |
| toList/toSet có bất biến không? | Đọc hợp đồng cụ thể; không đoán theo kiểu |
| Có cần thứ tự kết quả xác định? | Chọn mapFactory/collectionFactory phù hợp |

## 19. Câu hỏi tự kiểm tra

1. Vì sao groupingBy(Employee::department) cho Map<String,List<Employee>> nhưng thêm counting lại cho Map<String,Long>?
2. Trong Collector<T,A,R>, chữ A mô tả gì và vì sao thường không cần nêu khi đọc kết quả collect?
3. mapping(Employee::name,toSet()) nhận kiểu đầu vào gì và trả kết quả kiểu gì?
4. groupingBy(department,mapping(name,toList())) khác Stream.map(name) trước groupingBy(department) thế nào?
5. Vì sao filtering(active,counting()) trong groupingBy có thể tạo HR=0, còn Stream.filter(active) trước groupingBy không có khóa HR?
6. partitioningBy(active,counting()) trả kiểu gì? Có cả false và true khi không có nhân viên active không?
7. groupingBy(department,partitioningBy(active,mapping(name,toList()))) có mấy lớp Map và mỗi khóa có nghĩa gì?
8. flatMapping(e -> e.skills().stream(),toSet()) khác mapping(Employee::skills,toList()) ra sao về kiểu và độ sâu List?
9. Nếu teeing(counting(),summingInt(salary),DeptStats::new), value của Map nhóm là kiểu gì?
10. collectingAndThen(toList(),List::copyOf) thay đổi generic type hay chỉ thay đổi hợp đồng không thể chỉnh sửa?
11. summarizingInt(salary) trả IntSummaryStatistics hay Integer? Truy cập trung bình bằng phương thức nào?
12. maxBy(comparator) nằm trong groupingBy trả Map<K,Optional<T>>; tại sao Optional xuất hiện?
13. Nếu finisher của collectingAndThen trả String thì vì sao Map value cuối cùng có thể là String dù downstream tạo List?
14. Trong mã nguồn nhóm theo department, mapFactory TreeMap::new quyết định map ngoài hay list bên trong?
15. Khi Java báo incompatible types giữa Map<String,List<Employee>> và Map<String,Long>, bạn kiểm tra phần nào của collector đầu tiên?
16. Vì sao hai kết quả có cùng kiểu Map<Boolean,List<T>> từ groupingBy(Boolean) và partitioningBy có thể khác nhau về tập khóa?
17. Vì sao một kiểu Map<String,List<String>> không chứng minh List bên trong mutable?
18. Muốn các kết quả nhóm có thứ tự in ổn định, nên xác định factory ở tầng nào?
19. Nếu Stream đã thành Stream<String> sau map, vì sao Employee::department không còn là classifier hợp lệ?
20. Khi lồng thêm một collector groupingBy, làm thế nào cập nhật kiểu generic Map<K1,Map<K2,R>> mà không đoán?

**Kết luận:** Để đọc kiểu kết quả của collector kết hợp, trước hết xác định **Stream<T>**, tiếp theo xác định **kiểu R của collector sâu nhất**, rồi lần lượt áp dụng **mapping/filtering/flatMapping**, **collectingAndThen/teeing**, và cuối cùng bọc bởi **groupingBy → Map<K,R>** hoặc **partitioningBy → Map<Boolean,R>**. Đừng nhầm kiểu của phần tử nguồn với kiểu value của kết quả Map. Cần nhớ thêm sự khác nhau giữa lọc ngoài/lọc trong nhóm, Boolean partition, Optional, khả năng bất biến và thứ tự của collection để code vừa biên dịch đúng vừa đúng ngữ nghĩa.