# List.sort với Comparator trong Java Collection

`List.sort(Comparator<? super E> c)` sắp xếp **chính danh sách đang có**, theo thứ tự mà `Comparator` xác định. Đây là phương thức mặc định của `List` từ Java 8, vẫn được hỗ trợ trong Java hiện đại. Kết quả sắp xếp là **stable**: hai phần tử được comparator coi là bằng nhau (`compare(a,b)==0`) giữ nguyên thứ tự tương đối của chúng trong danh sách trước khi sắp.

`List.sort` không tạo danh sách mới, không trả về danh sách mới mà trả `void`. Danh sách phải **modifiable**, tức hỗ trợ thay thế phần tử; không bắt buộc phải thêm/xóa được phần tử. Nếu chỉ muốn có kết quả đã sắp mà giữ nguyên thứ tự nguồn, hãy tạo một bản sao hoặc dùng `Stream.sorted` rồi thu thập kết quả.

Bài này tập trung vào cách sử dụng `List.sort` với `Comparator`: sắp tăng/giảm, nhiều tiêu chí, stability, giá trị null, khả năng sửa danh sách, hợp đồng so sánh, lỗi thường gặp và ví dụ Java chạy độc lập. Nội dung chỉ sử dụng các quy tắc và API **vẫn còn áp dụng hiện nay**; ví dụ chính dùng API có từ Java 8 và chạy được với JDK 17+.

## 1. Cú pháp `List.sort` và thứ tự tự nhiên

~~~java
void sort(Comparator<? super E> comparator)
~~~

`E` là kiểu phần tử của list. Khi truyền comparator khác null, Java dựa vào `compare` của comparator để quyết định thứ tự. Khi truyền `null`, Java dùng **natural ordering** của các phần tử, nghĩa là các phần tử phải thực hiện `Comparable` và so sánh được với nhau.

~~~java
List<Integer> numbers = new ArrayList<>(
    Arrays.asList(4, 1, 3, 2)
);
numbers.sort(Comparator.naturalOrder());
// [1, 2, 3, 4]

numbers.sort(Comparator.reverseOrder());
// [4, 3, 2, 1]

numbers.sort(null); // lại dùng natural ordering
// [1, 2, 3, 4]
~~~

Đây là đoạn **minh họa**, cần import `List`, `ArrayList`, `Arrays` và `Comparator`. Khi dùng `sort(null)`, **`null` là đối số comparator** (nghĩa là dùng natural order), không có nghĩa danh sách có thể chứa phần tử null và vẫn sắp được.

Một kiểu đối tượng tùy chỉnh `Employee` không cần triển khai `Comparable` nếu bạn cung cấp comparator:

~~~java
employees.sort(
    Comparator.comparingInt(Employee::getAge)
);
~~~

Đoạn này không độc lập: `employees` và `Employee` được định nghĩa trong ứng dụng (và trong ví dụ hoàn chỉnh ở phần sau).

### Lúc nào có thể ném lỗi?

- `UnsupportedOperationException`: List không cho sửa vị trí/thực hiện sort.
- `ClassCastException`: các phần tử không thể so sánh với nhau bằng comparator đã chọn hoặc không có natural order tương thích.
- `IllegalArgumentException`: có thể xảy ra nếu implementation phát hiện comparator vi phạm hợp đồng, **nhưng không phải mọi vi phạm đều bị phát hiện**.
- `NullPointerException`: có thể xảy ra khi danh sách có phần tử null nhưng comparator không hỗ trợ null, hoặc khi key extractor/comparator bên trong gặp null ngoài chính sách cho phép.

Nếu danh sách chứa nhiều kiểu dữ liệu không so sánh được theo comparator (chẳng hạn đối tượng không có `Comparable` khi `sort(null)`), hãy xác định tiêu chí và kiểu dữ liệu đúng từ đầu; không dựa vào ngoại lệ để đoán thứ tự.

## 2. Hợp đồng `Comparator.compare(a, b)`

`Comparator<T>` là **functional interface** với phương thức:

~~~java
int compare(T a, T b)
~~~

| Giá trị trả về | Ý nghĩa |
| --- | --- |
| Số **âm** | `a` đứng trước `b` |
| `0` | `a` và `b` bằng nhau theo **tiêu chí comparator** |
| Số **dương** | `a` đứng sau `b` |

Điều quan trọng là **dấu âm/dương/0**, không cần trả đúng -1, 0 hay 1. Một số quy tắc bắt buộc:

1. **Đối xứng về dấu**: `compare(a,b)` và `compare(b,a)` phải có dấu ngược nhau.
2. **Tính bắc cầu**: nếu `a > b` và `b > c` thì `a > c`; tương tự với quan hệ nhỏ hơn.
3. **Nhất quán khi hòa**: nếu `compare(a,b)==0`, so với mọi `c`, cả `a` và `b` phải có cùng quan hệ theo dấu.
4. **Không thay đổi bất thường**: không dùng random, thời điểm hiện tại, state ngoài đang thay đổi, I/O có side effect hoặc sửa list khi comparator chạy.

`Comparator` không bắt buộc cho kết quả `compare(a,b)==0` đúng khi và chỉ khi `a.equals(b)`. Ví dụ hai nhân viên khác ID cùng tuổi có thể được xem là bằng nhau theo comparator tuổi; `List.sort` vẫn giữ **cả hai phần tử**. Nhưng với `TreeSet`/`TreeMap`, comparator còn được dùng để quyết định quan hệ tương đương của khóa, có thể làm tập/map xử lý những đối tượng khác nhau như cùng khóa. Nếu dùng comparator cho sorted set/map, cân nhắc thêm tie-break bằng ID và tính nhất quán với equals.

## 3. Sắp tăng/giảm, so sánh số an toàn

### 3.1. Dùng lambda hoặc method reference

~~~java
Comparator<Integer> ascending = Integer::compare;
Comparator<Integer> descending = (a, b) ->
        Integer.compare(b, a);
~~~

Các phép so sánh số ở Java có phương thức tường minh `Integer.compare`, `Long.compare` và `Double.compare`.

**Không viết comparator bằng phép trừ**:

~~~java
// SAI: (a - b) có thể tràn int.
Comparator<Integer> wrong = (a, b) -> a - b;
~~~

Ví dụ `Integer.MAX_VALUE - (-1)` tràn int thành `Integer.MIN_VALUE`, số âm; comparator sai lệch, có thể cho rằng số lớn hơn đứng trước số nhỏ hơn. Dùng `Integer.compare(a,b)` để không bị tràn bởi phép trừ. Tương tự, không ép hiệu `long` về `int`.

### 3.2. Factory methods: `comparing` và so sánh primitive

~~~java
Comparator<Employee> byName =
    Comparator.comparing(Employee::getName);

Comparator<Employee> byAge =
    Comparator.comparingInt(Employee::getAge);

Comparator<Employee> bySalary =
    Comparator.comparingLong(Employee::getSalary);

Comparator<Product> byRating =
    Comparator.comparingDouble(Product::getRating);
~~~

Đây là các đoạn minh họa; `Employee`, `Product` và getters thuộc chương trình riêng. `comparingInt`/`comparingLong`/`comparingDouble` nhận các hàm lấy thuộc tính primitive, không cần boxing chỉ để truyền key qua `Integer`/`Long`/`Double`.

`Comparator.naturalOrder()` lấy natural ordering; `Comparator.reverseOrder()` lấy natural ordering đảo chiều. Với comparator đã có, `reversed()` đảo chiều toàn bộ comparator đó:

~~~java
Comparator<Employee> salaryDesc =
    Comparator.comparingLong(Employee::getSalary)
        .reversed();
~~~

### 3.3. Không tự dùng dấu trừ của `compare` để đảo chiều

Một comparator do người khác cung cấp có thể trả một số âm khác -1, kể cả `Integer.MIN_VALUE`. Nếu dùng `-comparator.compare(a,b)`, số âm nhỏ nhất không thể chuyển thành dương trong `int`. Dùng `comparator.reversed()` hoặc đổi thứ tự hai đối số cho đúng hợp đồng.

## 4. Sắp theo nhiều tiêu chí với `thenComparing`

Ví dụ yêu cầu **tuổi tăng dần**, nếu bằng tuổi thì **tên tăng dần**, nếu tên vẫn trùng thì **ID tăng dần**:

~~~java
Comparator<Employee> byAgeNameId =
    Comparator.comparingInt(Employee::getAge)
        .thenComparing(Employee::getName)
        .thenComparingInt(Employee::getId);

employees.sort(byAgeNameId);
~~~

`thenComparing` chỉ xét tiêu chí tiếp theo nếu tiêu chí trước trả 0. Nó tránh chuỗi `if/else` so sánh thủ công và biểu đạt rõ mức ưu tiên.

Có thể dùng comparator cụ thể cho key:

~~~java
Comparator<Employee> byNameIgnoringCase =
    Comparator.comparing(
        Employee::getName,
        String.CASE_INSENSITIVE_ORDER
    ).thenComparingInt(Employee::getId);
~~~

Nếu hai tên chỉ khác chữ hoa/thường, `String.CASE_INSENSITIVE_ORDER` có thể đánh giá chúng bằng nhau; `thenComparingInt(id)` tạo thứ tự nhất quán khi cần.

### Vị trí `reversed()` quyết định tiêu chí nào bị đảo

**Lương giảm dần, tên tăng dần**:

~~~java
Comparator<Employee> salaryDescNameAsc =
    Comparator.comparingLong(Employee::getSalary)
        .reversed()
        .thenComparing(Employee::getName);
~~~

**Lương giảm dần, tên cũng giảm dần**:

~~~java
Comparator<Employee> salaryDescNameDesc =
    Comparator.comparingLong(Employee::getSalary)
        .thenComparing(Employee::getName)
        .reversed();
~~~

Hai comparator này **không tương đương**. Gọi `reversed()` ở cuối đảo **toàn bộ chuỗi tiêu chí**, không chỉ lương. Nếu cần mỗi trường có chiều khác nhau, có thể truyền comparator riêng cho từng `thenComparing`, nhưng phải viết rõ yêu cầu nghiệp vụ.

## 5. Stable sort: khóa bằng nhau không đổi thứ tự tương đối

`List.sort` có hợp đồng **stable**: nếu `compare(a,b)==0`, thứ tự giữa `a` và `b` vẫn giống lúc chưa sort. Điều này khác với việc comparator chỉ rõ cách sắp xếp mọi trường.

Giả sử thứ tự ban đầu:

~~~text
ID 101: tuổi 25
ID 102: tuổi 30
ID 103: tuổi 25
ID 104: tuổi 28
ID 105: tuổi 30
ID 106: tuổi 25
~~~

Sau khi:

~~~java
employees.sort(Comparator.comparingInt(Employee::getAge));
~~~

thứ tự ID là:

~~~text
[101, 103, 106, 104, 102, 105]
~~~

Nhóm tuổi 25 vẫn có ID theo thứ tự cũ `101 → 103 → 106`, nhóm tuổi 30 vẫn `102 → 105`. **Stable không có nghĩa tự sắp theo tên khi tuổi bằng nhau**. Nếu muốn tên tăng dần, thêm `thenComparing(Employee::getName)`; nếu muốn tính tái lập trên đầu vào từ database không bảo đảm thứ tự, nên thêm tie-break bằng ID/timestamp theo nghiệp vụ.

Sắp ổn định có thể được dùng để phối hợp nhiều lần sort có chủ đích, nhưng một comparator nhiều tiêu chí thường ngắn gọn hơn, dễ kiểm thử và tránh lặp công việc.

## 6. Xử lý `null` ở đúng tầng

Có hai vấn đề khác nhau: **phần tử trong list là null** và **phần tử khác null nhưng thuộc tính sắp xếp là null**.

### 6.1. Phần tử null

~~~java
List<String> names = new ArrayList<>(
    Arrays.asList("B", null, "A")
);

names.sort(Comparator.nullsFirst(
    Comparator.naturalOrder()
));
// [null, A, B]
~~~

`Comparator.nullsFirst(c)` coi phần tử null đứng trước, `nullsLast(c)` coi phần tử null đứng sau. Nếu không cho phép null theo nghiệp vụ, hãy validate trước thay vì che lỗi bằng cách đẩy null sang đầu/cuối.

### 6.2. Khóa/thuộc tính null

~~~java
Comparator<Employee> departmentNullsLast =
    Comparator.comparing(
        Employee::getDepartment,
        Comparator.nullsLast(
            String.CASE_INSENSITIVE_ORDER
        )
    ).thenComparing(Employee::getName);
~~~

Ở đây `Employee` vẫn khác null, nhưng `getDepartment()` có thể trả null. Bộ so sánh null phải nằm **trong `Comparator.comparing(keyExtractor, keyComparator)`**.

So sánh với:

~~~java
Comparator<Employee> employeeNullsLast =
    Comparator.nullsLast(
        Comparator.comparing(Employee::getName)
    );
~~~

Trường hợp này xử lý **Employee null** ở tầng đối tượng, **không bảo vệ** tên null của một Employee có thật. Nếu cả Employee và getter đều có thể null, cần xử lý cả hai tầng hoặc từ chối dữ liệu thiếu bằng validation.

Với `String.CASE_INSENSITIVE_ORDER`, `"Java"` và `"java"` có thể được so sánh bằng nhau mặc dù `String.equals` khác nhau. `List.sort` vẫn giữ cả hai phần tử; nếu cần thứ tự phụ khi case khác nhau, thêm comparator natural order làm tie-break.

## 7. Danh sách nào hỗ trợ `sort`?

Danh sách phải hỗ trợ **sửa thứ tự các phần tử** nhưng không cần thay đổi số lượng phần tử.

| Loại List | Sắp tại chỗ? | Ghi chú |
| --- | --- | --- |
| `new ArrayList<>(...)` | Có | Có thể thêm/xóa và thay thế vị trí. |
| `new LinkedList<>(...)` | Có | Có thể sửa vị trí; chi phí triển khai có thể khác ArrayList. |
| `Arrays.asList(...)` | Có | Fixed-size nhưng hỗ trợ thay thế phần tử (`set`). |
| `Collections.unmodifiableList(...)` | Không | `sort` thường ném `UnsupportedOperationException`. |
| `List.of(...)` (Java 9+) | Không | Unmodifiable, không hỗ trợ thay đổi thứ tự. |
| `List.copyOf(...)` (Java 10+) | Không | Unmodifiable. |
| `Stream.toList()` (Java 16+) | Không | Trả danh sách unmodifiable, không thể sort tại chỗ. |

**Lưu ý về phiên bản:** `List.of`/`List.copyOf`/`Stream.toList` xuất hiện sau Java 8, nhưng là API hiện hành và được nhắc để tránh lỗi trong dự án JDK mới. Ví dụ chính phía dưới không dùng các phương thức này để vẫn chạy được trên Java 8.

Nếu không biết List có sửa được hay không, có thể tạo bản sao rõ ràng:

~~~java
List<String> sorted = new ArrayList<>(source);
sorted.sort(Comparator.naturalOrder());
~~~

Bản sao giúp giữ **thứ tự của List nguồn**; đây là *shallow copy*, nên nếu phần tử là đối tượng mutable, source và sorted vẫn có thể cùng tham chiếu đến đối tượng đó. Không giả định sao chép List tạo bản sao sâu của mỗi element.

Với `Collectors.toList()`, API không bảo đảm kiểu List, mutability hoặc thread-safety của kết quả. Nếu chắc chắn cần List sửa được, dùng `new ArrayList<>(result)` hoặc `Collectors.toCollection(ArrayList::new)`.

## 8. Chương trình Java hoàn chỉnh và đầu ra kiểm chứng

Lưu thành **`ListSortComparatorDemo.java`**, biên dịch/chạy trên JDK 17+; mọi API trong chương trình đều có từ Java 8.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class ListSortComparatorDemo {

    static final class Employee {
        private final int id;
        private final String name;
        private final String department;
        private final int age;
        private final long salary;

        Employee(int id, String name, String department,
                 int age, long salary) {
            this.id = id;
            this.name = name;
            this.department = department;
            this.age = age;
            this.salary = salary;
        }

        int getId() {
            return id;
        }

        String getName() {
            return name;
        }

        String getDepartment() {
            return department;
        }

        int getAge() {
            return age;
        }

        long getSalary() {
            return salary;
        }
    }

    private static List<Employee> employees() {
        return new ArrayList<>(Arrays.asList(
                new Employee(101, "Lan", "IT", 25, 1200L),
                new Employee(102, "An", "HR", 30, 1800L),
                new Employee(103, "Binh", "IT", 25, 1600L),
                new Employee(104, "Minh", null, 28, 1500L),
                new Employee(105, "Mai", "HR", 30, 1800L),
                new Employee(106, "An", "IT", 25, 1200L)
        ));
    }

    private static String ids(List<Employee> values) {
        return values.stream()
                .map(e -> Integer.toString(e.getId()))
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        List<Employee> stableAge = employees();
        stableAge.sort(
                Comparator.comparingInt(Employee::getAge));
        System.out.println("stableAge=" + ids(stableAge));

        List<Employee> ageNameId = employees();
        ageNameId.sort(
                Comparator.comparingInt(Employee::getAge)
                        .thenComparing(Employee::getName)
                        .thenComparingInt(Employee::getId));
        System.out.println("ageNameId=" + ids(ageNameId));

        List<Employee> salaryDescNameAsc = employees();
        salaryDescNameAsc.sort(
                Comparator.comparingLong(Employee::getSalary)
                        .reversed()
                        .thenComparing(Employee::getName)
                        .thenComparingInt(Employee::getId));
        System.out.println("salaryDescNameAsc="
                + ids(salaryDescNameAsc));

        List<Employee> departmentNullsLast = employees();
        departmentNullsLast.sort(
                Comparator.comparing(
                        Employee::getDepartment,
                        Comparator.nullsLast(
                                String.CASE_INSENSITIVE_ORDER))
                        .thenComparing(Employee::getName)
                        .thenComparingInt(Employee::getId));
        System.out.println("departmentNullsLast="
                + ids(departmentNullsLast));

        List<String> withNulls = new ArrayList<>(Arrays.asList(
                "bb", null, "aa", null, "cc"));
        withNulls.sort(
                Comparator.nullsFirst(Comparator.naturalOrder()));
        System.out.println("nullsFirst=" + withNulls);

        List<Integer> numbers =
                new ArrayList<>(Arrays.asList(3, 1, 2));
        numbers.sort(null);
        System.out.println("natural=" + numbers);
        Collections.sort(numbers, Comparator.reverseOrder());
        System.out.println("reverse=" + numbers);

        List<String> fixedSize = Arrays.asList("z", "a", "b");
        fixedSize.sort(Comparator.naturalOrder());
        System.out.println("fixedSize=" + fixedSize);

        List<String> readOnly = Collections.unmodifiableList(
                new ArrayList<>(Arrays.asList("b", "a")));
        try {
            readOnly.sort(Comparator.naturalOrder());
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "readOnly=UnsupportedOperationException");
        }

        List<String> source =
                new ArrayList<>(Arrays.asList("z", "b", "a"));
        List<String> sortedCopy = source.stream()
                .sorted()
                .collect(Collectors.toList());
        System.out.println("source=" + source);
        System.out.println("sortedCopy=" + sortedCopy);

        int bad = Integer.MAX_VALUE - (-1);
        int good = Integer.compare(Integer.MAX_VALUE, -1);
        System.out.println("subtractionSign="
                + Integer.signum(bad)
                + ", compareSign=" + Integer.signum(good));
    }
}
~~~

Lệnh biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ListSortComparatorDemo.java
java ListSortComparatorDemo
~~~

**Đầu ra xác định:**

~~~text
stableAge=[101, 103, 106, 104, 102, 105]
ageNameId=[106, 103, 101, 104, 102, 105]
salaryDescNameAsc=[102, 105, 103, 104, 106, 101]
departmentNullsLast=[102, 105, 106, 103, 101, 104]
nullsFirst=[null, null, aa, bb, cc]
natural=[1, 2, 3]
reverse=[3, 2, 1]
fixedSize=[a, b, z]
readOnly=UnsupportedOperationException
source=[z, b, a]
sortedCopy=[a, b, z]
subtractionSign=-1, compareSign=1
~~~

Giải thích:

1. **`stableAge`**: những người cùng tuổi 25 giữ thứ tự ban đầu `101,103,106`; những người 30 tuổi giữ `102,105`.
2. **`ageNameId`**: cùng tuổi 25 được sắp theo tên `An(106), Binh(103), Lan(101)`. Sau đó tuổi 28, rồi nhóm tuổi 30.
3. **`salaryDescNameAsc`**: lương 1800 đứng trước, tiếp 1600, 1500 và 1200. Trong cùng lương, tên tăng dần.
4. **`departmentNullsLast`**: HR rồi IT, cuối cùng department null; trong từng nhóm tên tăng dần.
5. **`nullsFirst`** đưa các phần tử null lên đầu; số lượng phần tử và bản thân các phần tử khác được giữ.
6. **`sort(null)`** trên số nguyên dùng natural order, `Collections.sort` dùng comparator đảo cho kết quả giảm dần.
7. **`Arrays.asList`** fixed-size nhưng thay thế vị trí được. Wrapper unmodifiable ném lỗi khi sort.
8. **`Stream.sorted`** không đổi thứ tự `source`, còn `sortedCopy` là một danh sách khác.
9. **`Integer.MAX_VALUE - (-1)`** tràn sang giá trị âm, gây dấu sai. `Integer.compare` trả dấu dương đúng.

Không cần giả định các con số thời gian thực thi hay output phụ thuộc scheduler: chương trình không dùng concurrency và mọi tie-break cần thiết đã được chỉ rõ.

## 9. So sánh `List.sort`, `Collections.sort`, `Stream.sorted`

| API | Có thay đổi thứ tự List gốc? | Trả về | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `list.sort(comparator)` | **Có** | `void` | Đang có List sửa được và muốn sắp trực tiếp. |
| `Collections.sort(list, comparator)` | **Có** | `void` | Tiện ích tương đương về ý định, vẫn hợp lệ và được hỗ trợ. |
| `stream.sorted(comparator)` | **Không tự sửa nguồn** | `Stream<T>` | Muốn sắp trong pipeline rồi thu thập ra kết quả. |
| `new ArrayList<>(source)` rồi `sort` | Không sửa thứ tự source | `List<T>` sao chép | Cần giữ List gốc và có danh sách đã sắp sửa được. |

`Collections.sort` không phải API lỗi thời cần loại bỏ; trong triển khai JDK hiện đại nó chuyển tới `List.sort` để sắp danh sách. Chọn cách biểu đạt dễ đọc trong dự án.

`Stream.sorted(...)` là thao tác **trung gian**; phải có terminal operation mới thực hiện và nhận kết quả. Với stream có encounter order, sort là stable; với nguồn unordered, stability không được bảo đảm tương tự. Khi yêu cầu giữ nguồn, dùng `sorted` hoặc sao chép rồi sort; không mong `List.sort` âm thầm tạo List mới.

## 10. Lỗi thường gặp

### Lỗi A: Dùng phép trừ làm comparator

~~~java
// Sai với số có thể gây overflow:
Comparator<Employee> bad =
    (a, b) -> a.getAge() - b.getAge();
~~~

Dùng `Integer.compare`, `Long.compare` hoặc `Comparator.comparingInt` để so sánh an toàn, tránh tràn và ép kiểu.

### Lỗi B: Thay chiều toàn bộ chuỗi tiêu chí

~~~java
// Đảo lương lẫn tên, không phải lương giảm tên tăng:
Comparator<Employee> bothDesc =
    Comparator.comparingLong(Employee::getSalary)
        .thenComparing(Employee::getName)
        .reversed();
~~~

Đảo đúng trường chính rồi mới thêm tiêu chí phụ nếu muốn chiều khác nhau.

### Lỗi C: Không xác định rõ việc xử lý null

`Comparator.naturalOrder()` không tự xử lý phần tử null. `Comparator.nullsLast(comparator)` ở cấp object không đồng nghĩa thuộc tính của object cũng được phép null. Cần phân biệt hai tầng hoặc validate dữ liệu lỗi.

### Lỗi D: Sắp list không cho chỉnh sửa

~~~java
List<String> unmodifiable = Collections.unmodifiableList(
    Arrays.asList("b", "a")
);
// unmodifiable.sort(Comparator.naturalOrder()); // UOE
~~~

Tạo `new ArrayList<>(unmodifiable)` trước khi sort. `Arrays.asList` khác với wrapper unmodifiable: nó cho thay thế phần tử nhưng không cho thay đổi kích thước.

### Lỗi E: Tưởng stable nghĩa là tự có tie-break

Nếu comparator chỉ dùng `age`, những người cùng tuổi giữ thứ tự ban đầu; **không tự sắp theo tên**. Thêm `thenComparing` nếu yêu cầu có quy tắc thứ hai.

### Lỗi F: Comparator vi phạm hợp đồng

Dùng random hoặc state ngoài thay đổi giữa các lần `compare` có thể phá bắc cầu/nhất quán. Sort có thể báo `IllegalArgumentException` hoặc tạo thứ tự không đáng tin; cần comparator thuần, có tính so sánh xác định.

### Lỗi G: Nhầm `compare==0` với `equals==true`

Trong List, các phần tử cùng tuổi nhưng ID khác nhau vẫn còn. Trong `TreeSet`, comparator coi 0 có thể làm phần tử mới được xem là trùng. Khi comparator dùng ở sorted set/map, cần xem xét ID, equals và quan hệ khóa.

### Lỗi H: Sửa List hoặc khóa sắp xếp từ code comparator

Không mutate List hay trường mà comparator đang đọc khi `List.sort` chạy; đừng để thread khác sửa cùng List thiếu đồng bộ. Kết quả có thể không ổn định, phát sinh lỗi hoặc vi phạm hợp đồng.

### Lỗi I: Key extractor tốn nhiều chi phí hoặc side effect

`Comparator.comparing(Employee::getName)` có thể gọi getter nhiều lần cho mỗi phần tử; API **không hứa chỉ gọi một lần**. Không gọi DB/network từ getter dùng trong sort. Nếu khóa đắt để tính, có thể tạo snapshot/DTO lưu sẵn khóa trước khi sắp.

### Lỗi J: Phụ thuộc input order vốn không ổn định

Stability bảo toàn tie **theo input cụ thể**, nhưng nếu dữ liệu từ database không có `ORDER BY`, thứ tự tie giữa các lần đọc có thể khác nhau. Thêm ID/timestamp theo nghiệp vụ làm tie-break để có kết quả tái lập.

## 11. Hiệu năng và kiểm thử

- Với `n` phần tử và comparator hợp lệ, sort kiểu so sánh có chi phí khoảng `O(n log n)` trong trường hợp tổng quát. Dữ liệu gần sắp sẵn có thể được implementation tận dụng để giảm số phép so sánh, nhưng **không cam kết số lời gọi comparator chính xác**.
- `List.sort` được bảo đảm **stable**, nhưng không nên ràng buộc nghiệp vụ vào một thuật toán cụ thể (ghi chú triển khai hiện hành có thể đề cập adaptive mergesort/TimSort).
- Các implementation khác nhau như `ArrayList` và `LinkedList` có chi phí lưu trữ/truy cập khác nhau. `List.sort` có thể dùng mảng trung gian; không mặc định phụ phí bộ nhớ là `O(1)` cho mọi trường hợp.
- Chi phí lấy khóa, locale-aware string comparison, cấp phát, số trường tie-break và dữ liệu thực tế ảnh hưởng tốc độ. Với danh sách lớn, đo CPU/thời gian/bộ nhớ ở môi trường mục tiêu.
- Nếu dữ liệu không vừa bộ nhớ, có thể cần sắp tại database bằng `ORDER BY`, phân trang hoặc external sort; `List.sort` là sắp trên List đang ở trong JVM.

**Bộ test thiết yếu**: List rỗng, một phần tử, số lượng lớn, nhiều phần tử cùng khóa, null element, null key, mixed-case strings, số nguyên tại min/max, nhiều tiêu chí tăng/giảm khác nhau, List fixed-size, List unmodifiable, và input order thay đổi. Kiểm tra đúng thứ tự phần tử chứ không chỉ kích thước List.

## 12. Checklist trước khi dùng

1. Cần sắp **List gốc** hay giữ nguyên nguồn và tạo List mới?
2. List có hỗ trợ thay thế vị trí không? `Arrays.asList` được; unmodifiable List không.
3. Dùng natural order hay comparator riêng? Với `List.sort(null)`, dữ liệu phải có `Comparable` tương thích.
4. Comparator trả dấu âm/0/dương đúng và đáp ứng đối xứng dấu, bắc cầu và tính nhất quán khi hòa không?
5. Đã tránh `a - b` và thay bằng `Integer.compare`/`Long.compare`/`comparingInt` chưa?
6. Đã đặt `reversed()` đúng chỗ khi có `thenComparing` chưa?
7. Có null element hay null key không? Bộ so sánh `nullsFirst/nullsLast` nằm đúng tầng chưa?
8. Nếu có nhiều phần tử comparator coi là bằng nhau, stability có đủ hay cần thêm ID làm tie-break?
9. Có dữ liệu thay đổi trong khi sort, getter có side effect hoặc tốn I/O không?
10. Đã phân biệt `List.sort` với `Stream.sorted` và `Collections.sort`, đúng theo nhu cầu mutation chưa?
11. Đã test dữ liệu biên và so sánh output thật với kết quả mong đợi chưa?

**Kết luận:** `List.sort` và `Comparator` vẫn là cách sắp xếp List hiện hành, súc tích và ổn định. Các factory method như `comparing`, `comparingInt`, `thenComparing`, `reversed` và `nullsFirst/nullsLast` giúp diễn đạt chính xác quy tắc nhiều tiêu chí, nhưng tính đúng của comparator và tính modifiable của List là điều kiện bắt buộc.

## Tài liệu chính thức

- [Oracle Java SE 27 — List.sort](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html)
- [Oracle Java SE 27 — Comparator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Comparator.html)
- [Oracle Java SE 27 — Collections.sort](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html)
- [Oracle Java SE 27 — Stream.sorted](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html)
