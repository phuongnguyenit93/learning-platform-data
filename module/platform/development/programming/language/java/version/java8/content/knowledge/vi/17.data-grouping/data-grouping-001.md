# groupingBy và classifier trong Java Stream

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích Collectors.groupingBy phân nhóm phần tử Stream thành Map như thế nào và vai trò của hàm classifier.
2. Chọn đúng một trong ba overload groupingBy để lấy nhóm, tính kết quả theo nhóm, hoặc chọn kiểu Map.
3. Dùng các downstream collector như counting, mapping, summingInt, averagingInt và groupingBy lồng nhau.
4. Thiết kế khóa phân nhóm ổn định, xử lý dữ liệu không chuẩn hóa, khóa null, thứ tự của Map và nhóm rỗng.
5. Phân biệt groupingBy với groupingByConcurrent, toMap, partitioningBy; tránh side effect và các giả định sai về khả năng chạy song song.
6. Viết và kiểm tra chương trình Java 17+ sử dụng các API này đúng hợp đồng.

**Phạm vi:** Nội dung tập trung vào groupingBy và classifier được giới thiệu trong Stream API của Java 8 và vẫn được sử dụng trong Java hiện đại. Một số tiện ích bổ sung, như Collectors.filtering (Java 9+) và Stream.toList() (Java 16+), được ghi rõ phiên bản để có thể dùng đúng trên JDK hiện hành.

## 1. Bài toán phân nhóm: từ phần tử thành các nhóm

Giả sử hệ thống có các đơn hàng, mỗi đơn chứa thành phố và số tiền. Muốn gom các đơn cùng thành phố vào một danh sách:

~~~text
Order("O1", "Ha Noi", 120)
Order("O2", "Da Nang",  80)
Order("O3", "Ha Noi",  60)
Order("O4", "Hue",     50)
Order("O5", "Da Nang",  40)

                  classifier = Order::city
                              |
                              v
Map<String, List<Order>>
  "Da Nang" -> [O2, O5]
  "Ha Noi"  -> [O1, O3]
  "Hue"     -> [O4]
~~~

Phần tử đầu vào có kiểu T (ở ví dụ là Order). Classifier biến mỗi phần tử thành một **khóa nhóm** K (ở đây là String chứa tên thành phố). Các phần tử có khóa được coi là cùng một nhóm sẽ được đưa vào cùng giá trị của Map.

Công thức thường gặp:

~~~java
Map<K, List<T>> result = source.stream()
        .collect(Collectors.groupingBy(classifier));
~~~

Đây là **mảnh mã tổng quát**, không phải chương trình biên dịch độc lập: T, K, source và classifier đại diện cho kiểu/biến cụ thể. collect là terminal operation, kích hoạt pipeline; groupingBy tạo một Collector mô tả cách gom dữ liệu.

### Classifier là gì?

Classifier là hàm nhận **một phần tử T** và trả **một khóa K**:

~~~text
Function<? super T, ? extends K>

T -> K
Order("O1", "Ha Noi", 120) -> "Ha Noi"
Order("O3", "Ha Noi",  60) -> "Ha Noi"
~~~

Các cách xác định khóa thường dùng:

- Method reference: Order::city, Employee::department.
- Lambda theo điều kiện: order -> order.amount() >= 100 ? "LARGE" : "SMALL".
- Chuẩn hóa chuỗi: name -> name.strip().toLowerCase(Locale.ROOT).
- Khóa tổng hợp: employee -> new DepartmentStatus(employee.department(), employee.active()).

Classifier **chỉ quyết định khóa**, không quyết định giá trị tổng hợp của từng nhóm. Phần giá trị sẽ do downstream collector đảm nhiệm; nếu không cung cấp downstream, mặc định là danh sách các phần tử đầu vào.

## 2. Ba overload chính của Collectors.groupingBy

Các chữ T, K, D, A, M dưới đây là tham số kiểu generic; A là trạng thái trung gian nội bộ của downstream collector.

| Dạng | Mục đích | Kiểu kết quả |
|---|---|---|
| groupingBy(classifier) | Gom phần tử của mỗi khóa vào List | Map<K, List<T>> |
| groupingBy(classifier, downstream) | Tổng hợp từng nhóm theo một Collector khác | Map<K, D> |
| groupingBy(classifier, mapFactory, downstream) | Vừa tổng hợp từng nhóm vừa chỉ định Map được tạo | M extends Map<K, D> |

### 2.1. groupingBy(classifier)

~~~java
Map<String, List<Order>> byCity = orders.stream()
        .collect(Collectors.groupingBy(Order::city));
~~~

Các phần tử có cùng giá trị city được đưa vào cùng danh sách. Dạng một tham số tương đương về ý nghĩa với groupingBy(classifier, Collectors.toList()).

**Quan trọng:** Java API không bảo đảm kiểu Map/List cụ thể, tính mutable, khả năng tuần tự hóa hoặc thread-safety của kết quả. Không thiết kế nghiệp vụ dựa vào suy đoán rằng groupingBy mặc định chắc chắn trả HashMap hay ArrayList.

### 2.2. groupingBy(classifier, downstream)

~~~java
Map<String, Long> countByCity = orders.stream()
        .collect(Collectors.groupingBy(
                Order::city,
                Collectors.counting()
        ));
~~~

Thay vì giữ các đối tượng Order, mỗi khóa chỉ giữ một Long biểu thị số lượng phần tử trong nhóm. Downstream cũng có thể tạo tổng, trung bình, tập tên, thống kê hoặc một Map lồng nhau.

### 2.3. groupingBy(classifier, mapFactory, downstream)

~~~java
Map<String, List<String>> idsByCity = orders.stream()
        .collect(Collectors.groupingBy(
                Order::city,
                TreeMap::new,
                Collectors.mapping(Order::id, Collectors.toList())
        ));
~~~

Đây là **mảnh mã minh họa** dùng biến orders và record Order ở chương trình mục 3. TreeMap::new là Supplier<Map> tạo Map có khóa sắp xếp theo thứ tự tự nhiên; mapping biến mỗi Order thành id trước khi thu thập vào List.

Hãy chọn mapFactory khi có yêu cầu cụ thể: TreeMap cho khóa được sắp xếp, LinkedHashMap khi muốn duy trì thứ tự chèn khóa trong một pipeline tuần tự có encounter order, EnumMap cho khóa enum với factory phù hợp. Với TreeMap, khóa cần so sánh được hoặc phải cung cấp Comparator phù hợp. Cần lưu ý quan hệ so sánh của Comparator vì TreeMap xác định hai khóa “cùng nhóm” qua phép so sánh, thay vì chỉ dùng equals/hashCode như Map dựa trên hashing.

## 3. Ví dụ hoàn chỉnh: nhóm đơn hàng theo thành phố

Lưu nội dung sau vào **GroupingByBasics.java**, sau đó dùng JDK 17+.

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupingByBasics {
    record Order(String id, String city, int amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O1", "Ha Noi", 120),
                new Order("O2", "Da Nang", 80),
                new Order("O3", "Ha Noi", 60),
                new Order("O4", "Hue", 50),
                new Order("O5", "Da Nang", 40)
        );

        Map<String, List<Order>> byCity = orders.stream()
                .collect(Collectors.groupingBy(Order::city));

        byCity.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> System.out.println(
                        entry.getKey() + " -> " +
                        entry.getValue().stream().map(Order::id).toList()
                ));

        Map<String, Long> counts = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::city,
                        Collectors.counting()
                ));

        System.out.println("counts=" + new TreeMap<>(counts));
        System.out.println("missing=" +
                byCity.getOrDefault("Can Tho", List.of()).size());
    }
}
~~~

Chạy:

~~~text
javac --release 17 GroupingByBasics.java
java GroupingByBasics
~~~

Kết quả:

~~~text
Da Nang -> [O2, O5]
Ha Noi -> [O1, O3]
Hue -> [O4]
counts={Da Nang=2, Ha Noi=2, Hue=1}
missing=0
~~~

**Vì sao in ra đúng thứ tự?**

- byCity là Map không có bảo đảm thứ tự khóa; mã chủ động sắp xếp entry bằng comparingByKey() trước khi in.
- Với nguồn List có encounter order, downstream toList() thu thập các phần tử trong từng nhóm theo encounter order; O1 đứng trước O3.
- new TreeMap<>(counts) tạo bản xem có thứ tự khóa để in; bản thân Map do groupingBy tạo không được giả định đã sắp xếp.
- Nhóm “Can Tho” không tồn tại: groupingBy không tự tạo khóa cho nhóm không có phần tử, nên dùng getOrDefault trả danh sách rỗng.

Nếu Stream đầu vào rỗng thì kết quả groupingBy là Map rỗng, không phải Map chứa mọi khóa “có thể có”.

## 4. Downstream collector: giá trị của mỗi nhóm không nhất thiết là List

Downstream nhận các phần tử trong từng nhóm và biến chúng thành kết quả D. Những lựa chọn quan trọng hiện nay:

| Downstream | Kết quả trong mỗi nhóm | Trường hợp dùng |
|---|---|---|
| Collectors.toList() | List<T> | Giữ phần tử gốc |
| Collectors.counting() | Long | Số lượng theo nhóm |
| Collectors.mapping(mapper, toList()) | List<U> | Chỉ lấy trường cần thiết |
| Collectors.mapping(mapper, toSet()) | Set<U> | Lấy các giá trị phân biệt |
| Collectors.summingInt(mapper) | Integer | Cộng trường kiểu int |
| Collectors.summingLong(mapper) | Long | Cộng trường kiểu long |
| Collectors.averagingInt(mapper) | Double | Trung bình một trường số |
| Collectors.summarizingInt(mapper) | IntSummaryStatistics | Đồng thời lấy count, sum, min, max, average |
| Collectors.maxBy(comparator) | Optional<T> | Chọn phần tử lớn nhất theo tiêu chí |
| Collectors.groupingBy(otherClassifier) | Map<K2, List<T>> | Phân nhóm nhiều cấp |

Ví dụ tổng số tiền theo thành phố:

~~~java
Map<String, Integer> totalAmountByCity = orders.stream()
        .collect(Collectors.groupingBy(
                Order::city,
                Collectors.summingInt(Order::amount)
        ));
~~~

Đây là **mảnh mã** dùng orders và Order như mục 3. Khi tổng có khả năng vượt int, nên chọn miền số thích hợp, chẳng hạn summingLong với phép chuyển phù hợp, hoặc BigInteger cho số nguyên chính xác lớn. Không nên chỉ chọn collector theo sự ngắn gọn cú pháp nếu nghiệp vụ cần chống tràn số.

### Phân biệt map với mapping downstream

~~~java
// Trường hợp 1: thay phần tử đầu vào bằng tên trước khi phân nhóm.
employees.stream()
        .map(Employee::name);
// Nếu tiếp tục tại đây, Stream chỉ còn tên, không còn team để nhóm.

// Trường hợp 2: nhóm Employee theo team rồi chỉ giữ tên trong mỗi nhóm.
employees.stream()
        .collect(Collectors.groupingBy(
                Employee::team,
                Collectors.mapping(Employee::name, Collectors.toList())
        ));
~~~

Hai đoạn trên là **mảnh mã mô tả**, dùng record Employee ở mục 5. Ở trường hợp 2, classifier vẫn được gọi trên Employee, còn mapping chỉ áp dụng cho những phần tử đã được đưa vào nhóm.

## 5. Phân nhóm nhiều cấp, khóa tổng hợp và lọc trong nhóm

Có thể nhóm nhân sự theo team, sau đó theo trạng thái active, hoặc tạo một khóa record gồm hai thuộc tính. Cách nào phù hợp phụ thuộc cách ứng dụng truy vấn kết quả:

- Map<String, Map<Boolean, Long>> phù hợp khi muốn truy vấn theo từng cấp.
- Map<DepartmentStatus, Long> phù hợp khi dùng tổ hợp hai thuộc tính như một khóa duy nhất.

record trong Java hiện đại tự sinh equals/hashCode dựa trên thành phần, nên thích hợp làm khóa bất biến. Nếu sử dụng class tự định nghĩa, cần triển khai equals/hashCode nhất quán và tránh thay đổi trạng thái tham gia định danh khóa sau khi đã đưa vào Map.

### Ví dụ thực hành với downstream và mapFactory

Tệp **GroupingByAnalytics.java** chạy trên JDK 17+:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupingByAnalytics {
    record Employee(String name, String team, int salary, boolean active) {}
    record DepartmentStatus(String team, boolean active) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("An", "Platform", 120, true),
                new Employee("Binh", "Platform", 150, false),
                new Employee("Chi", "Sales", 90, true),
                new Employee("Dung", "Sales", 110, true),
                new Employee("Ha", "HR", 100, false)
        );

        Map<String, List<String>> names = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name, Collectors.toList()
                        )
                ));

        Map<String, Integer> salaries = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::team,
                        Collectors.summingInt(Employee::salary)
                ));

        Map<String, Long> counts = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::team, Collectors.counting()
                ));

        Map<String, Map<Boolean, Long>> statusCounts = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::team,
                        Collectors.groupingBy(
                                Employee::active, Collectors.counting()
                        )
                ));

        Map<DepartmentStatus, Long> compositeKeyCounts = employees.stream()
                .collect(Collectors.groupingBy(
                        e -> new DepartmentStatus(e.team(), e.active()),
                        Collectors.counting()
                ));

        Map<String, List<String>> activeNames = employees.stream()
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.filtering(
                                Employee::active,
                                Collectors.mapping(
                                        Employee::name, Collectors.toList()
                                )
                        )
                ));

        Map<String, List<String>> filteredFirst = employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name, Collectors.toList()
                        )
                ));

        System.out.println("names=" + names);
        System.out.println("salaries=" + new TreeMap<>(salaries));
        System.out.println("counts=" + new TreeMap<>(counts));
        System.out.println("Platform.inactive=" +
                statusCounts.get("Platform").get(false));
        System.out.println("composite.Platform.inactive=" +
                compositeKeyCounts.get(
                        new DepartmentStatus("Platform", false)));
        System.out.println("activeNames=" + activeNames);
        System.out.println("filteredFirst=" + filteredFirst);
    }
}
~~~

Chạy:

~~~text
javac --release 17 GroupingByAnalytics.java
java GroupingByAnalytics
~~~

Kết quả:

~~~text
names={HR=[Ha], Platform=[An, Binh], Sales=[Chi, Dung]}
salaries={HR=100, Platform=270, Sales=200}
counts={HR=1, Platform=2, Sales=2}
Platform.inactive=1
composite.Platform.inactive=1
activeNames={HR=[], Platform=[An], Sales=[Chi, Dung]}
filteredFirst={Platform=[An], Sales=[Chi, Dung]}
~~~

**Các điểm cần hiểu:**

1. names sử dụng overload ba tham số: classifier Employee::team, mapFactory TreeMap::new và downstream mapping để chỉ giữ tên.
2. salaries dùng summingInt; counts dùng counting. Từng nhóm tạo ra một số, không phải danh sách nhân viên.
3. statusCounts có hai tầng phân nhóm; mỗi team có Map<Boolean, Long> chỉ với các trạng thái đã xuất hiện.
4. compositeKeyCounts dùng record DepartmentStatus làm khóa tổng hợp; truy vấn bằng record mới có cùng thành phần vẫn tìm đúng nhóm nhờ equals/hashCode.
5. activeNames dùng Collectors.filtering (có từ Java 9): tạo khóa cho **mọi team xuất hiện** rồi chỉ giữ nhân viên active trong mỗi nhóm. Vì HR có nhân viên nhưng không ai active, khóa HR vẫn tồn tại với danh sách rỗng.
6. filteredFirst lọc phần tử trước khi gom nhóm. Team HR bị loại hoàn toàn, nên kết quả không có khóa HR.

**Không nhầm hai phép lọc:** filter trước groupingBy thay đổi tập phần tử được classifier nhìn thấy, còn downstream filtering chỉ thay đổi nội dung của những nhóm đã được tạo. Đây là khác biệt quan trọng khi báo cáo cần hiển thị cả nhóm có giá trị bằng 0.

## 6. Thiết kế classifier đúng và an toàn

### 6.1. Khóa phải thể hiện đúng quan hệ “cùng nhóm”

Với Map dựa trên hashing, các khóa bằng nhau theo equals và hashCode được gom chung. String phân biệt chữ hoa/chữ thường: "Java" và "JAVA" là hai khóa khác nhau. Nếu muốn gộp chúng:

~~~java
List<String> languages = List.of("JAVA", "java", "Go", "go", "Rust");

Map<String, Long> byCanonicalName = languages.stream()
        .collect(Collectors.groupingBy(
                name -> name.strip().toLowerCase(java.util.Locale.ROOT),
                Collectors.counting()
        ));
~~~

Đoạn này là **mảnh mã**; kết quả theo cặp khóa/giá trị là go → 2, java → 2, rust → 1. Locale.ROOT giúp chuẩn hóa kỹ thuật ít phụ thuộc locale mặc định của máy; với tên riêng và quy tắc ngôn ngữ cụ thể, cần chính sách chuẩn hóa phù hợp nghiệp vụ. Nếu ký tự Unicode có nhiều biểu diễn tương đương, cân nhắc chuẩn hóa Unicode theo quy tắc dữ liệu của ứng dụng.

Classifier nên **thuần và ổn định**: cùng phần tử ở cùng trạng thái logic phải cho cùng khóa. Không dùng thời điểm hiện tại, số lần gọi, biến đếm toàn cục, dữ liệu chung có thể thay đổi hoặc random làm khóa nếu mục tiêu là phân nhóm có thể tái lập.

### 6.2. Không trả khóa null một cách tùy tiện

Trong các triển khai JDK thông dụng, Collectors.groupingBy ném NullPointerException nếu classifier trả null. Hợp đồng API không đưa ra lời hứa hỗ trợ khóa null; hãy biểu diễn dữ liệu thiếu bằng khóa **không null** theo quy ước:

~~~java
Map<String, List<Employee>> byTeam = employees.stream()
        .collect(Collectors.groupingBy(
                e -> e.team() == null ? "UNKNOWN" : e.team()
        ));
~~~

Đây là **mảnh mã** dùng Employee ở mục 5; các bản ghi thực hành ở đó đều có team không null. Với miền nghiệp vụ mà giá trị UNKNOWN có thể trùng dữ liệu thật, hãy dùng khóa kiểu enum hoặc một kiểu phân biệt “không xác định” riêng; đừng vô tình nhập hai trạng thái khác nhau vào một nhóm.

### 6.3. Khóa object phải ổn định sau khi thu thập

Nếu dùng đối tượng mutable làm khóa HashMap rồi thay đổi trường tham gia equals/hashCode, việc tìm nhóm bằng get có thể thất bại hoặc Map trở nên không nhất quán. Sử dụng String, enum, record chứa các thành phần bất biến hoặc value object bất biến. Với khóa tùy biến, kiểm tra đầy đủ equals/hashCode và quy tắc Comparator nếu dùng TreeMap.

### 6.4. Tránh stateful classifier và side effect

Phản ví dụ mang tính cảnh báo, **không dùng trong chương trình thực tế**:

~~~java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();

Map<Integer, List<Order>> unstable = orders.parallelStream()
        .collect(Collectors.groupingBy(
                order -> counter.getAndIncrement() % 2
        ));
~~~

Đây là **mảnh mã** với orders và Order ở mục 3. Classifier phụ thuộc thứ tự và số lần gọi thay vì thuộc tính của Order. Trong pipeline song song, lịch thực thi có thể khác nhau, nên một Order không có nhóm cố định. AtomicInteger chỉ tránh một số lỗi tranh chấp ở biến đếm; nó không biến quy tắc phân nhóm này thành nghiệp vụ có nghĩa và ổn định.

Ngoài ra, không sửa List nguồn trong classifier, không dùng forEach cộng phần tử vào HashMap chia sẻ để thay thế groupingBy và không giả định classifier được gọi tuần tự đúng encounter order.

## 7. Thứ tự và tính mutable của kết quả

Có ba thứ tự dễ bị lẫn:

1. **Thứ tự phần tử đầu vào (encounter order):** List có thứ tự xác định; một số nguồn khác như HashSet không có thứ tự duyệt được bảo đảm.
2. **Thứ tự phần tử trong List của mỗi nhóm:** downstream Collectors.toList() thu thập theo encounter order khi Stream có thứ tự. Nếu Stream không có thứ tự, không được suy ra thứ tự nhóm.
3. **Thứ tự duyệt các khóa trong Map:** groupingBy mặc định không bảo đảm; muốn duyệt ổn định thì chọn TreeMap hoặc sắp xếp entry trước khi trình bày.

Một collector dùng TreeMap::new làm rõ thứ tự khóa ngay ở lúc thu thập. LinkedHashMap::new phù hợp với ứng dụng muốn duyệt theo thứ tự khóa được chèn, thường kết hợp với một Stream tuần tự có thứ tự đầu vào xác định.

**Đừng giả định kết quả luôn mutable:** Tài liệu Java không bảo đảm cụ thể về tính sửa đổi được của Map/List trả từ Collectors.groupingBy hoặc Collectors.toList. Khi cần List cụ thể và có thể sửa, chọn Collectors.toCollection(ArrayList::new); khi cần List bất biến, dùng Collectors.toUnmodifiableList() (Java 10+) nếu phần tử không null. Nếu cần cấu trúc bất biến ở cả Map và các List bên trong, phải đóng băng từng List rồi tạo Map bất biến; Map.copyOf chỉ tạo lớp Map không sửa được, không tự biến những List lồng bên trong thành bất biến.

Lưu ý: Stream.toList() và Collectors.toList() là **hai API khác nhau**. Stream.toList() (Java 16+) trả List không sửa được, còn Collectors.toList() không có cam kết mutability giống như vậy.

## 8. groupingBy và groupingByConcurrent khi xử lý song song

groupingBy thông thường **không phải concurrent collector**. Một parallel stream vẫn có thể sử dụng nó; Java tạo và kết hợp các kết quả nhóm trung gian. Bước ghép Map theo khóa có thể tốn chi phí.

~~~java
Map<String, List<Order>> grouped = orders.parallelStream()
        .collect(Collectors.groupingBy(Order::city));
~~~

Đây là mảnh mã từ mục 3. Kết quả vẫn là kiểu Map bình thường; việc dùng parallelStream không biến Map thành một ConcurrentMap và không cho phép sửa kết quả từ nhiều thread một cách tùy tiện.

Khi dữ liệu lớn, việc giữ encounter order không cần thiết và việc thu thập đồng thời thực sự có lợi, có thể cân nhắc:

~~~java
ConcurrentMap<K, List<T>> grouped =
        source.parallelStream()
                .collect(Collectors.groupingByConcurrent(classifier));
~~~

Đây là **mẫu chữ ký mang tính khái quát**; cần thay T, K, source, classifier bằng kiểu và biến thực tế. groupingByConcurrent trả một **concurrent, unordered Collector** và kết quả là ConcurrentMap. Thứ tự phần tử trong List của mỗi nhóm không được bảo đảm; các List trả về **không được API bảo đảm thread-safe** cho việc ứng dụng tự ý sửa đồng thời sau khi đã collect xong.

### Ví dụ chạy được: nhóm song song theo độ dài chuỗi

Tệp **GroupingByConcurrentDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class GroupingByConcurrentDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "cat", "dog", "owl", "java", "code", "stream"
        );

        ConcurrentMap<Integer, List<String>> byLength =
                words.parallelStream()
                        .collect(Collectors.groupingByConcurrent(
                                String::length
                        ));

        byLength.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> System.out.println(
                        entry.getKey() + " -> " +
                        entry.getValue().stream().sorted().toList()
                ));
    }
}
~~~

Chạy:

~~~text
javac --release 17 GroupingByConcurrentDemo.java
java GroupingByConcurrentDemo
~~~

Kết quả sau khi **chủ động sắp xếp** khóa và phần tử của từng nhóm để in:

~~~text
3 -> [cat, dog, owl]
4 -> [code, java]
6 -> [stream]
~~~

Nếu bỏ bước sorted(), thứ tự List do groupingByConcurrent thu thập không được bảo đảm. Đầu ra ổn định ở ví dụ này là kết quả của bước sắp xếp bổ sung, không phải lời hứa về thứ tự từ groupingByConcurrent.

**Quy tắc chọn:** ưu tiên stream() và groupingBy cho trường hợp bình thường. Chỉ thử parallelStream hoặc groupingByConcurrent khi workload đủ lớn, công việc classifier/downstream phù hợp, thứ tự không phải yêu cầu nghiệp vụ và phép đo trên dữ liệu thực cho thấy lợi ích. ConcurrentMap cũng không có nghĩa toàn bộ các giá trị bên trong mặc nhiên an toàn trước mọi thao tác concurrent.

## 9. Phân biệt groupingBy, toMap và partitioningBy

| Tình huống | Nên chọn | Khác biệt |
|---|---|---|
| Nhiều phần tử có thể cùng khóa, muốn giữ danh sách | groupingBy(classifier) | Mỗi khóa ánh xạ tới nhiều phần tử |
| Nhiều phần tử cùng khóa, muốn count/sum | groupingBy(classifier, downstream) | Tổng hợp độc lập trong mỗi nhóm |
| Mỗi khóa phải có duy nhất một phần tử | toMap(keyMapper, valueMapper) | Nếu trùng khóa, overload hai tham số ném IllegalStateException |
| Trùng khóa nhưng có quy tắc hợp nhất rõ ràng | toMap(keyMapper, valueMapper, mergeFunction) | Tạo một giá trị hợp nhất theo chính sách |
| Chia thành đúng hai nhánh true/false | partitioningBy(predicate) | Kết quả luôn có cả khóa true và false, kể cả khi một nhóm rỗng |

### Nhóm theo Boolean khác phân hoạch Boolean

~~~java
Map<Boolean, List<Employee>> grouped = employees.stream()
        .collect(Collectors.groupingBy(Employee::active));

Map<Boolean, List<Employee>> partitioned = employees.stream()
        .collect(Collectors.partitioningBy(Employee::active));
~~~

Hai mảnh mã này dùng Employee ở mục 5. Nếu tất cả nhân viên đều active, groupingBy có thể chỉ chứa khóa true; partitioningBy luôn chứa khóa true và false, trong đó false nhận danh sách rỗng. Khi giao diện luôn cần hai nhóm “đang hoạt động / không hoạt động”, partitioningBy thể hiện ý định rõ hơn.

### Khi nào toMap phù hợp?

Nếu cần Map<OrderId, Order> với mỗi id phải duy nhất, toMap giúp phát hiện dữ liệu id trùng và buộc người viết quyết định cách xử lý. groupingBy sẽ tạo Map<OrderId, List<Order>> và giữ mọi bản ghi trùng id; cách này có thể che giấu lỗi ràng buộc duy nhất nếu nghiệp vụ không cho phép trùng.

## 10. Chi phí, lỗi phổ biến và cách kiểm tra

### Chi phí bộ nhớ

- groupingBy mặc định giữ toàn bộ phần tử trong các List nhóm, vì vậy dữ liệu được lưu trong kết quả tăng theo số phần tử n.
- groupingBy với counting hay summing chỉ giữ giá trị tổng hợp theo từng khóa, nên dữ liệu tổng hợp thường tăng theo số khóa phân biệt k, cộng chi phí của Map.
- Chi phí tính toán phụ thuộc số lượng nhóm, cách tính hash/comparator và downstream. Không mặc định kết luận parallel nhanh hơn; đặc biệt khi merge nhiều Map trung gian.

### Các lỗi cần tránh

1. **Chọn sai khóa:** nhóm theo tên chưa chuẩn hóa trong khi nghiệp vụ coi “Java” và “JAVA” như nhau.
2. **Classifier trả null:** phụ thuộc vào hỗ trợ không được cam kết, dễ gặp NullPointerException; dùng khóa thay thế có nghĩa.
3. **Dựa vào thứ tự HashMap:** output in đúng trong vài lần chạy không chứng minh có bảo đảm thứ tự.
4. **Dùng khóa mutable:** sửa trường khóa sau collect làm Map khó truy vấn đúng.
5. **Nhầm downstream filtering với filter trước groupingBy:** một bên có thể giữ nhóm rỗng, bên kia loại luôn nhóm.
6. **Nhầm Collectors.toList với Stream.toList:** khác hợp đồng về mutability.
7. **Gắn side effect vào classifier:** số đếm ngoài, random, thao tác I/O hoặc cập nhật Map chia sẻ khiến kết quả thiếu ổn định và khó tối ưu.
8. **Nhầm groupingByConcurrent với dữ liệu có thứ tự:** collector này unordered; phải sắp xếp sau nếu cần cách hiển thị ổn định.
9. **Chọn sai collector số học:** summingInt có thể tràn int, còn averagingInt trả double với giới hạn độ chính xác của số thực.
10. **Bỏ qua nhóm không tồn tại:** get(key) có thể trả null; dùng getOrDefault hoặc kiểm tra chứa khóa trước khi truy vấn tiếp.

### Cách tự kiểm chứng

- Chạy trên input rỗng, một phần tử, nhiều phần tử có khóa trùng và dữ liệu có khóa chưa được chuẩn hóa.
- So sánh với vòng lặp đơn giản: duyệt từng phần tử, xác định khóa, cập nhật Map hoặc tổng theo khóa. Hai cách phải cho cùng tập khóa và giá trị theo tiêu chí nghiệp vụ.
- Test classifier với cùng một phần tử nhiều lần: khóa cần ổn định.
- Nếu có downstream lọc, test nhóm toàn phần tử không đạt điều kiện để kiểm tra còn xuất hiện với kết quả rỗng hay không.
- Nếu thêm parallelStream/groupingByConcurrent, đối chiếu **nội dung** nhóm sau khi chuẩn hóa thứ tự, không dựa vào thứ tự ngẫu nhiên của Map hay các List concurrent.
- Nếu có khóa object, test equals/hashCode (hoặc Comparator đối với TreeMap) và bảo đảm khóa không bị sửa trong thời gian dùng Map.

## 11. Bài tập tự kiểm tra

**Bài 1.** Với List<String> = ["JAVA", "java", "Go", "go", "Rust"], viết classifier để đếm số phần tử theo tên không phân biệt hoa/thường.

*Định hướng:* name -> name.toLowerCase(Locale.ROOT), kết hợp Collectors.counting(). Kết quả theo tập cặp là java=2, go=2, rust=1; nếu cần in đúng thứ tự khóa, cung cấp TreeMap hoặc sort sau.

**Bài 2.** Cho danh sách đơn hàng (city, amount), tạo Map<String, Integer> tổng amount theo city, không giữ toàn bộ Order.

*Định hướng:* groupingBy(Order::city, summingInt(Order::amount)).

**Bài 3.** Cho nhân viên theo team, cần kết quả chứa mọi team có nhân viên nhưng chỉ hiển thị tên nhân viên active. Dùng filter trước groupingBy hay downstream filtering?

*Định hướng:* downstream Collectors.filtering với Collectors.mapping vì team chỉ có nhân viên inactive vẫn phải xuất hiện với danh sách rỗng. Nhớ rằng filtering là API Java 9+.

**Bài 4.** Vì sao dùng mapFactory TreeMap::new không làm các phần tử trong List nhóm tự động được sắp xếp theo tên?

*Định hướng:* TreeMap chỉ quy định thứ tự **khóa**. Muốn sắp xếp phần tử mỗi nhóm, dùng downstream thích hợp, sorted trước collect khi có ý nghĩa, hoặc sắp xếp các giá trị sau thu thập.

**Bài 5.** groupingByConcurrent có bảo đảm các List kết quả luôn giữ thứ tự phần tử đầu vào không?

*Định hướng:* Không. Đó là concurrent và unordered collector. Nếu cần encounter order, sử dụng chiến lược giữ thứ tự phù hợp; không lấy thứ tự ngẫu nhiên trong một lần chạy làm hợp đồng API.

## 12. Checklist áp dụng trong dự án

Trước khi dùng groupingBy, hãy trả lời:

1. T là gì, mỗi nhóm được định danh bởi khóa K nào, khóa có ý nghĩa nghiệp vụ rõ ràng không?
2. Cần List<T> hay chỉ cần count, sum, max hoặc dữ liệu đã chuyển đổi?
3. Classifier có stateless, non-interfering, trả khóa không null và ổn định không?
4. Khóa có equals/hashCode/Comparator đúng và không bị đổi trạng thái sau khi collect không?
5. Có cần sắp xếp khóa, thứ tự phần tử trong nhóm hoặc Map triển khai cụ thể không?
6. Nhóm rỗng có phải xuất hiện trong báo cáo không? Filter trước hay sau bước phân nhóm?
7. Dùng groupingBy, groupingByConcurrent, partitioningBy hay toMap mới thể hiện đúng quan hệ dữ liệu?
8. Kiểu dữ liệu cho số đếm/tổng/trung bình có an toàn trước overflow hoặc sai số không?
9. Có test input rỗng, khóa trùng, khóa thiếu, dữ liệu không chuẩn hóa và đối chiếu sequential/parallel khi cần không?

## Tài liệu tham khảo API đang được duy trì

- Oracle Java SE 25, Collectors: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html
- Oracle Java SE 25, Stream package: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- Oracle Java SE 25, Function: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html
- Oracle Java SE 25, Map: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html

Những điểm cốt lõi — classifier chọn khóa, downstream tính giá trị mỗi nhóm, các overload groupingBy, quy tắc trạng thái an toàn và semantics của collector song song — vẫn là kiến thức thực hành hiện hành của Java Streams.