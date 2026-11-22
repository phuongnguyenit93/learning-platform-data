# Comparator trong Java: Kiểm thử khóa bằng nhau, null và dữ liệu biên

**Chủ đề cha:** Comparator — Java 8 và các phiên bản Java hiện đại. **Mục tiêu:** viết và kiểm thử `Comparator<T>` sao cho kết quả đúng khi nhiều đối tượng có **cùng khóa sắp xếp**, khi đối tượng/khóa có thể `null` và khi dữ liệu chạm các **giới hạn số học, giá trị số thực đặc biệt hoặc chuỗi khác biệt về chữ hoa–thường**. Kiến thức này vẫn áp dụng trên JDK hiện hành; các ví dụ độc lập bên dưới được thiết kế để biên dịch bằng **Java 17+**.

> Điểm cốt lõi: `compare(a, b) == 0` nghĩa là **hai đối tượng tương đương theo tiêu chí sắp xếp của comparator**, không nhất thiết là `a.equals(b)`. Điều này có thể vô hại với một phép **sort ổn định**, nhưng cực kỳ quan trọng với `TreeSet` và `TreeMap`.

## 1. Comparator trả về điều gì và “khóa bằng nhau” nghĩa là gì?

Chữ ký chức năng:

```java
int compare(T first, T second);
```

Đây là chữ ký API minh họa của `java.util.Comparator<T>`, không phải chương trình Java độc lập.

Hàm `compare` phải trả về:

| Kết quả | Diễn giải |
| --- | --- |
| Số âm | `first` đứng **trước** `second` |
| `0` | Hai giá trị **ngang hàng theo comparator** |
| Số dương | `first` đứng **sau** `second` |

**Không yêu cầu** giá trị trả về chỉ là `-1`, `0`, `1`. Khi kiểm thử, hãy kiểm tra **dấu** bằng `Integer.signum(...)` hoặc điều kiện `< 0` / `== 0` / `> 0`, không so sánh với một con số âm/dương cụ thể. Nếu dùng phép trừ số nguyên để tạo kết quả, còn có thể gặp overflow.

Ví dụ một bài toán xếp nhiệm vụ theo mức ưu tiên:

```java
Comparator<Task> byPriority =
        Comparator.comparingInt(Task::priority);
```

Đây là đoạn mã bên trong lớp có `record Task(int id, String name, int priority)` và import `java.util.Comparator`. Hai nhiệm vụ `Task(3, "C", 2)` và `Task(2, "B", 2)` có cùng `priority = 2` nên comparator trả `0`, mặc dù chúng là hai task khác nhau.

**Đừng đồng nhất:**

- Bằng nhau về **khóa sắp xếp**: `priority(a) == priority(b)`.
- Bằng nhau theo **Comparator**: `compare(a, b) == 0`.
- Bằng nhau theo **Object.equals**: `a.equals(b)`; đối với record, các component đều tham gia so sánh.
- Bằng nhau theo **khóa định danh nghiệp vụ**: ví dụ hai record cùng `id` — phụ thuộc invariant và cách model được thiết kế.

Bốn khái niệm có thể trùng nhau nhưng không tự động giống nhau.

## 2. Ma trận dữ liệu kiểm thử tối thiểu

Khi viết comparator, đừng chỉ thử dữ liệu có khóa khác nhau. Một bộ ca thử hữu ích gồm:

| Nhóm ca | Dữ liệu ví dụ | Kỳ vọng cần xác minh |
| --- | --- | --- |
| Khóa nhỏ hơn/lớn hơn | priority 1 so với 2 | Đúng dấu âm/dương |
| Khóa **bằng nhau** | priority 2 của hai task có id khác | `compare == 0` nếu chỉ so priority |
| Chính đối tượng đó | `compare(a, a)` | Trả `0` |
| Thứ tự đảo ngược | `compare(a, b)` và `compare(b, a)` | Dấu đối nhau |
| Nhiều khóa đều bằng nhau | Cùng priority, name | Tie-breaker tiếp theo hoặc equivalence được chủ ý |
| Đối tượng `null` | `null` so với Person | Theo chính sách nullsFirst/nullsLast, hoặc lỗi rõ ràng |
| Khóa được trích xuất `null` | `Person.name() == null` | Key comparator phải xử lý null |
| Hai khóa đều `null` | Hai Person khác id, cả hai name null | Có tie-breaker rõ hoặc cùng nhóm tương đương |
| Số nguyên cực trị | `Integer.MIN_VALUE`, `Integer.MAX_VALUE` | Không overflow phép so sánh |
| Số thực đặc biệt | `NaN`, `±Infinity`, `-0.0`, `+0.0` | Thứ tự nhất quán theo `Double.compare` |
| Chuỗi phân biệt hoa–thường | `"java"`, `"JAVA"` | Theo yêu cầu case-sensitive/case-insensitive |
| Giá trị tương đương nhưng `equals` khác | `BigDecimal("1.0")` vs `BigDecimal("1.00")` | Tác động lên `TreeSet`/`TreeMap` |
| Dữ liệu quy mô thực tế | Danh sách rỗng, 1 phần tử, nhiều phần tử trùng khóa | Không phụ thuộc vào một thứ tự may mắn |
| Dữ liệu bị sửa sau khi chèn | Thuộc tính dùng để so sánh thay đổi | Tránh làm hỏng invariant của sorted collection |

Tối thiểu nên có cả **kiểm thử từng cặp**, **kiểm thử trên bộ ba** (tính bắc cầu) và **kiểm thử hành vi collection** khi comparator được dùng trong `TreeSet`/`TreeMap`.

## 3. Khóa bằng nhau: sort ổn định và tie-breaker

### 3.1. Nếu comparator chỉ so sánh một khóa

Với `Comparator.comparingInt(Task::priority)`, hai task có priority bằng nhau được xem là **equivalent for ordering**. Khi sắp xếp một nguồn **có encounter order**, các API sắp xếp ổn định như `List.sort`, `Arrays.sort` cho mảng đối tượng và `Stream.sorted` trên ordered stream sẽ **không đảo thứ tự tương đối** của những phần tử comparator coi là bằng nhau.

**Stable sort không có nghĩa phân biệt được các task**: hai task vẫn có `compare == 0`. Nếu yêu cầu đầu ra phải có thứ tự hoàn toàn xác định độc lập với thứ tự input, hãy thêm khóa phụ bằng `thenComparing`.

Ví dụ:

```java
Comparator<Task> byPriorityThenId =
        Comparator.comparingInt(Task::priority)
                .thenComparingInt(Task::id);
```

Thứ tự được quyết định bằng priority; nếu bằng nhau mới so id. `thenComparingInt` chỉ cần gọi key extractor thứ hai khi comparator đầu trả 0 theo hợp đồng của phép kết hợp. Phương thức này vẫn áp dụng trên các bản Java hiện đại.

### 3.2. Ví dụ đầy đủ: vì sao `TreeSet` có thể “mất” phần tử?

Tạo file **`ComparatorTieDemo.java`**:

```java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class ComparatorTieDemo {
    record Task(int id, String name, int priority) {}

    public static void main(String[] args) {
        List<Task> tasks = List.of(
                new Task(3, "C", 2),
                new Task(1, "A", 1),
                new Task(2, "B", 2),
                new Task(4, "D", 2)
        );

        Comparator<Task> byPriority =
                Comparator.comparingInt(Task::priority);
        Comparator<Task> byPriorityThenId =
                byPriority.thenComparingInt(Task::id);

        System.out.println("Equal priority: "
                + byPriority.compare(tasks.get(0), tasks.get(2)));

        System.out.println("Stable ids: "
                + tasks.stream()
                        .sorted(byPriority)
                        .map(Task::id)
                        .toList());

        System.out.println("Tie ids: "
                + tasks.stream()
                        .sorted(byPriorityThenId)
                        .map(Task::id)
                        .toList());

        TreeSet<Task> prioritySet = new TreeSet<>(byPriority);
        prioritySet.addAll(tasks);
        System.out.println("Priority set: "
                + prioritySet.stream().map(Task::id).toList());

        TreeSet<Task> fullSet = new TreeSet<>(byPriorityThenId);
        fullSet.addAll(tasks);
        System.out.println("Tie set: "
                + fullSet.stream().map(Task::id).toList());
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac --release 17 ComparatorTieDemo.java
java ComparatorTieDemo
```

**Stdout:**

```text
Equal priority: 0
Stable ids: [1, 3, 2, 4]
Tie ids: [1, 2, 3, 4]
Priority set: [1, 3]
Tie set: [1, 2, 3, 4]
```

Diễn giải:

1. Hai task đầu được đem so ở dòng `Equal priority` là task id 3 và id 2, cùng priority 2, nên comparator `byPriority` trả 0.
2. `Stream.sorted(byPriority)` là **stable** vì `tasks.stream()` là ordered stream. Sau task priority 1 (id 1), các task priority 2 vẫn giữ thứ tự input: id 3, id 2, id 4.
3. Khi thêm `thenComparingInt(Task::id)`, nhóm priority 2 được xếp theo id 2, 3, 4.
4. `TreeSet` dùng `compare == 0` để xác định **phần tử tương đương trong set**. `byPriority` xem ba task priority 2 là một nhóm duy nhất, vì vậy set chỉ có đại diện được thêm đầu tiên (id 3).
5. `TreeSet` với comparator có tie-breaker id giữ cả bốn task **trong bộ dữ liệu này**, vì mọi id là duy nhất.

**Điều kiện cần lưu ý:** `byPriorityThenId` không tự động nhất quán với `Task.equals` cho *mọi* đối tượng `Task`. Hai record có cùng priority và id nhưng tên khác nhau vẫn `compare == 0` và `equals == false`. Nếu comparator dùng cho sorted set/map mà yêu cầu tính nhất quán đầy đủ với equality, hãy định nghĩa khóa phân biệt dựa trên đúng invariant của domain hoặc thiết kế `equals/hashCode` cùng ngữ nghĩa. Một id duy nhất theo quy ước nghiệp vụ chỉ đảm bảo phân biệt trong miền dữ liệu thỏa quy ước ấy.

## 4. Comparator bằng nhau và `equals` — vấn đề riêng của TreeSet/TreeMap

Theo tài liệu Java, ordering của comparator **được khuyến nghị nhất quán với equals**, nhưng đây **không phải** điều kiện bắt buộc để một comparator dùng trong sort. Một comparator có thể hợp lệ về thứ tự nhưng `compare(a, b) == 0` khi `!a.equals(b)`.

Với `TreeSet` và `TreeMap`, điều này ảnh hưởng đến **bản sắc phần tử/key**:

- `TreeSet.add(x)` có thể không thêm `x` nếu nó so sánh bằng 0 với một phần tử đã có.
- `TreeMap.put(k, v)` có thể **thay value của một key đang được xem là equivalent theo comparator** thay vì thêm key mới.
- Kết quả `size()`, `containsKey`/`contains` và việc duyệt phụ thuộc equivalence của comparator; không hành xử như `HashMap`/`HashSet` dựa trên `equals/hashCode`.

Ví dụ đơn giản:

```java
TreeSet<String> tags =
        new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
tags.add("java");
tags.add("JAVA");

System.out.println(tags.size()); // 1
```

Đây là **đoạn mã trong một phương thức** cần import `java.util.TreeSet`. Hai chuỗi khác nhau theo `String.equals` nhưng so bằng 0 theo comparator không phân biệt hoa–thường. Đây là hành vi **được định nghĩa** của `TreeSet` với comparator đó, không phải lỗi của JVM.

**Kiểm thử quan trọng:** Nếu muốn dùng một comparator vừa để sort, vừa cho sorted set/map, hãy ghi rõ **equivalence của comparator có phải định nghĩa uniqueness của dữ liệu không**. Nếu không, không nên âm thầm tái sử dụng comparator bỏ qua các field cần phân biệt.

## 5. `null`: Phân biệt null **đối tượng** và null **khóa trích xuất**

Đây là một nguồn gây `NullPointerException` rất phổ biến.

### 5.1. Đối tượng trong danh sách có thể là `null`

Ví dụ `List<Person>` có một **phần tử null**:

```java
Comparator<Person> byName =
        Comparator.comparing(Person::name);

Comparator<Person> nullObjectsLast =
        Comparator.nullsLast(byName);
```

Đây là **đoạn code trong lớp có record Person(String name)** và import `Comparator`. `Comparator.nullsLast(byName)` bao bọc comparator để khi **cả object Person là null** thì được xếp sau object không null. Hai null được so là bằng nhau.

Tuy nhiên `byName` vẫn có thể NPE nếu **Person không null nhưng `Person.name()` trả null**, vì comparator của tên không được cung cấp cách so sánh null key.

### 5.2. Đối tượng không null, nhưng khóa `name` có thể là `null`

Dùng overload `Comparator.comparing(keyExtractor, keyComparator)` và đưa chính sách null vào **key comparator**:

```java
Comparator<Person> byNullableName =
        Comparator.comparing(
                Person::name,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
        );
```

Đây là **đoạn code trong lớp có record Person(int id, String name)**. Key `name` null được xếp sau key không null; hai tên null so bằng 0. Nếu muốn phân biệt hai person đều chưa có tên, thêm tie-breaker `thenComparingInt(Person::id)`.

### 5.3. Cần xử lý **cả hai tầng null** thì bao bọc toàn bộ comparator

Mẫu thường dễ đọc:

```java
Comparator<Person> nonNullPeople =
        Comparator.comparing(
                Person::name,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
        ).thenComparingInt(Person::id);

Comparator<Person> allPeople =
        Comparator.nullsLast(nonNullPeople);
```

Ở đây:

- `Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)` xử lý **null của trường name**.
- `thenComparingInt(Person::id)` phân biệt các person có cùng tên (bao gồm cả hai tên null).
- `Comparator.nullsLast(nonNullPeople)` ngoài cùng xử lý **phần tử Person null**.

**Thứ tự bọc rất quan trọng:** Nếu viết `Comparator.nullsLast(bySomeComparator).thenComparingInt(Person::id)`, khi so hai object đều null, comparator ngoài trả 0 khiến `thenComparingInt` có thể tiếp tục đọc `id` từ null và NPE. Muốn cả object null an toàn, hãy kết hợp các key comparator **trước**, rồi bọc `nullsFirst`/`nullsLast` ở lớp ngoài cuối cùng.

### 5.4. Ví dụ chạy được: null ở nhiều vị trí

Tạo file **`ComparatorNullDemo.java`**:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class ComparatorNullDemo {
    record Person(int id, String name) {}

    public static void main(String[] args) {
        List<Person> people = Arrays.asList(
                new Person(3, null),
                new Person(2, "bob"),
                new Person(1, "Ann"),
                new Person(4, null)
        );

        Comparator<Person> nonNullPeople = Comparator.comparing(
                Person::name,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
        ).thenComparingInt(Person::id);

        System.out.println("Null key ids: "
                + people.stream()
                        .sorted(nonNullPeople)
                        .map(Person::id)
                        .toList());

        List<Person> objects = Arrays.asList(
                new Person(5, "Zed"),
                null,
                new Person(6, "Alice")
        );

        Comparator<Person> nullObjectsLast =
                Comparator.nullsLast(nonNullPeople);

        System.out.println("Null object ids: "
                + objects.stream()
                        .sorted(nullObjectsLast)
                        .map(p -> p == null ? "null" : String.valueOf(p.id()))
                        .toList());

        System.out.println("Null before Bob: "
                + (Comparator.nullsFirst(String.CASE_INSENSITIVE_ORDER)
                        .compare(null, "bob") < 0));
    }
}
```

Chạy:

```bash
javac --release 17 ComparatorNullDemo.java
java ComparatorNullDemo
```

**Stdout:**

```text
Null key ids: [1, 2, 3, 4]
Null object ids: [6, 5, null]
Null before Bob: true
```

`Arrays.asList` ở đây cho phép phần tử null và giữ encounter order. **`List.of(null, ...)` và `List.copyOf` không cho phép phần tử null**; nếu dùng chúng để tạo test data chứa null, test sẽ lỗi ngay khi tạo danh sách trước khi comparator được chạy.

### 5.5. Các tình huống null khác cần kiểm tra

- `Comparator.naturalOrder()` và `Comparator.reverseOrder()` không nhận đối số null khi so sánh.
- `Comparator.nullsFirst(cmp)` coi null là nhỏ hơn nonnull; `nullsLast(cmp)` coi null là lớn hơn nonnull; hai null so là 0.
- Nếu bạn truyền **`null` làm comparator bên trong** `nullsFirst(null)` / `nullsLast(null)`, mọi giá trị **khác null đều được xem là ngang hàng**. Đây là hành vi được API định nghĩa nhưng hiếm khi là thứ tự bạn thật sự muốn cho set/map.
- `Comparator.nullsLast(cmp).reversed()` sẽ đảo **cả chính sách null**, khiến null đứng trước. Nếu chỉ muốn đảo thứ tự các giá trị khác null nhưng **vẫn để null cuối**, dùng `Comparator.nullsLast(cmp.reversed())`.
- `TreeSet` và `TreeMap` có thể có chính sách null phụ thuộc comparator/implementation; mặc định không nên suy luận cho phép null key/element nếu chưa có comparator và kiểm thử phù hợp.
- Những object không null nhưng có **field khác null** vẫn phải được từng key comparator xử lý. Không có một `nullsLast` toàn cục tự làm mọi field nullable an toàn.

## 6. Số nguyên ở biên: Tránh `a - b`

### 6.1. Sai vì overflow

`Comparator<Integer> bad = (a, b) -> a - b;` trông có vẻ hợp lý, nhưng phép trừ `int` có thể tràn:

```java
int actual = Integer.MAX_VALUE - (-1);
// actual == Integer.MIN_VALUE, là số âm dù MAX_VALUE > -1
```

Đây là **đoạn trong phương thức**. Comparator trên sẽ báo `Integer.MAX_VALUE` đứng **trước** `-1`, trái thứ tự số học. Tệ hơn, phép trừ còn có thể làm hỏng hợp đồng antisymmetry/transitivity trên bộ giá trị cực trị.

**Nên dùng:**

```java
Comparator<Integer> safe = Integer::compare;
Comparator<Task> byPriority =
        Comparator.comparingInt(Task::priority);
```

Dòng thứ hai là đoạn mã trong lớp đã có `Task::priority`. `Integer.compare` so sánh theo thứ tự số nguyên mà không gây lỗi overflow do phép trừ. `Comparator.comparingInt` sử dụng khóa nguyên thủy và phù hợp khi không cần nhận `null` ở chính primitive key.

Với khóa `long`, dùng `Long.compare(a, b)` hoặc `Comparator.comparingLong(...)`; không viết `(int)(longA - longB)` vì vừa overflow, vừa thu hẹp kiểu. Với khóa `double`, dùng `Double.compare` hoặc `Comparator.comparingDouble(...)` thay vì ép hiệu về `int`.

### 6.2. Ví dụ số cực trị

```java
System.out.println("Wrong sign: "
        + (Integer.MAX_VALUE - (-1) < 0));
System.out.println("Correct sign: "
        + (Integer.compare(Integer.MAX_VALUE, -1) > 0));
```

Đây là đoạn mã trong phương thức, stdout:

```text
Wrong sign: true
Correct sign: true
```

Kết quả `Wrong sign: true` chứng minh phép trừ bị overflow: nó cho dấu âm **sai**. Kết quả `Correct sign: true` khẳng định comparator dùng `Integer.compare` xác định đúng rằng MAX_VALUE > -1.

## 7. Số thực: NaN, infinity và signed zero

Phép so sánh trực tiếp bằng `<` hoặc `>` trên `double` không tạo thứ tự toàn phần khi có `NaN`. Ví dụ `NaN < 1.0`, `NaN > 1.0` và `NaN == 1.0` đều false. Comparator kiểu:

```java
Comparator<Double> unsafe =
        (a, b) -> a < b ? -1 : a > b ? 1 : 0;
```

Đây là **đoạn mã trong phương thức** và không nên dùng cho mọi `double`: nó xem `NaN` ngang hàng với mọi số vì hai phép so sánh đều false. Điều đó gây ra quan hệ `compare == 0` không tương thích với kết quả so các phần tử khác, vi phạm hợp đồng Comparator.

**Hãy dùng `Double.compare` hoặc `Comparator.comparingDouble(...)`**. Chúng cung cấp thứ tự nhất quán theo quy tắc Java:

| Cặp | Kết quả so sánh theo `Double.compare` |
| --- | --- |
| `-Infinity` với số hữu hạn | `-Infinity` đứng trước |
| Số hữu hạn với `+Infinity` | Số hữu hạn đứng trước |
| `+Infinity` với `NaN` | `+Infinity` đứng trước `NaN` |
| `-0.0` với `+0.0` | `-0.0` đứng trước `+0.0` |
| `NaN` với `NaN` | Xem như ngang hàng |
| `+0.0 == -0.0` bằng toán tử `==` | **true**, nhưng `Double.compare(-0.0, +0.0) < 0` |

Nếu nghiệp vụ không cho phép `NaN`/Infinity, phải **validate trước** thay vì giả định chúng không xuất hiện. Thứ tự của `Double.compare` là lựa chọn API được định nghĩa, không phải quy tắc nghiệp vụ phù hợp với mọi phép đo.

### 7.1. `BigDecimal`: compareTo có thể bằng 0 nhưng equals false

`new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0`, vì giá trị số học bằng nhau. Nhưng `BigDecimal.equals` còn xét scale nên trả false.

Nếu đưa hai giá trị này vào `TreeSet<BigDecimal>` theo natural ordering, set có thể chỉ lưu **một** phần tử. Với phép sort ổn định, cả hai vẫn còn; đây là khác biệt bản chất giữa **sắp xếp** và **collection dùng comparator để xác định tương đương**.

### 7.2. Ví dụ số liệu biên chạy được

Tạo file **`ComparatorNumericDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.TreeSet;

public class ComparatorNumericDemo {
    public static void main(String[] args) {
        System.out.println("Overflow wrong: "
                + (Integer.MAX_VALUE - (-1)));
        System.out.println("Integer.compare: "
                + Integer.compare(Integer.MAX_VALUE, -1));

        System.out.println("Signed zero: "
                + Double.compare(-0.0, +0.0));
        System.out.println("NaN last: "
                + (Double.compare(Double.NaN,
                        Double.POSITIVE_INFINITY) > 0));

        List<Double> values = Arrays.asList(
                Double.NaN, +0.0, Double.POSITIVE_INFINITY, -0.0
        );
        values.sort(Double::compare);
        System.out.println("Double order: " + values);

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println("Decimal compare zero: "
                + (x.compareTo(y) == 0));
        System.out.println("Decimal equals: " + x.equals(y));

        TreeSet<BigDecimal> decimals = new TreeSet<>();
        decimals.add(x);
        decimals.add(y);
        System.out.println("Decimal set size: " + decimals.size());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ComparatorNumericDemo.java
java ComparatorNumericDemo
```

**Stdout:**

```text
Overflow wrong: -2147483648
Integer.compare: 1
Signed zero: -1
NaN last: true
Double order: [-0.0, 0.0, Infinity, NaN]
Decimal compare zero: true
Decimal equals: false
Decimal set size: 1
```

Đây là những ca kiểm thử hữu ích cho comparator số học hoặc khóa điểm số, giá, thời điểm dạng số. Với tiền tệ, `BigDecimal` giải quyết nhiều vấn đề biểu diễn thập phân nhưng vẫn cần **chính sách scale/equality** nhất quán khi dùng nó làm key trong sorted collection.

## 8. Hợp đồng Comparator phải được kiểm thử thành các tính chất

Ngoài vài kết quả ví dụ cụ thể, Comparator hợp lệ phải thỏa các tính chất **cho mọi phần tử thuộc miền dữ liệu được hỗ trợ**:

### 8.1. Reflexivity theo quan hệ so sánh

Với đối tượng `a` hợp lệ: `compare(a, a) == 0`.

### 8.2. Antisymmetry về dấu

`signum(compare(a, b)) == -signum(compare(b, a))`.

Không viết `compare(a,b) == -compare(b,a)` bằng số nguyên nguyên dạng: kết quả comparator không bắt buộc là ±1, và phép phủ định `Integer.MIN_VALUE` có thể overflow. Dùng `Integer.signum` để so dấu đúng hợp đồng.

### 8.3. Transitivity

Nếu `compare(a, b) > 0` và `compare(b, c) > 0`, thì phải có `compare(a, c) > 0`. Nhánh nhỏ hơn cũng suy ra tương tự từ các luật. Nếu vi phạm, kết quả sort có thể bất thường và một số thuật toán có thể ném `IllegalArgumentException`, nhưng **không bảo đảm runtime phát hiện được** comparator sai.

### 8.4. Bằng nhau theo comparator phải thay thế được trong mọi so sánh khác

Nếu `compare(a, b) == 0` thì với mọi `z`, `signum(compare(a, z)) == signum(compare(b, z))`.

Đây là luật dễ bị quên khi xây comparator có nhánh điều kiện đặc biệt (ví dụ một nhóm dữ liệu dùng case-insensitive, nhóm khác lại case-sensitive). Hai phần tử đã được coi ngang hàng phải có quan hệ so sánh **cùng dấu với phần tử thứ ba**.

### 8.5. Nhất quán với equals — nên kiểm tra riêng

Tài liệu Java **khuyến nghị** (không ép buộc với mọi comparator) mệnh đề:

```text
compare(a, b) == 0  <=>  a.equals(b)
```

Nếu comparator cố ý chỉ so một khóa (priority, name không phân biệt chữ hoa–thường, giá BigDecimal bỏ qua scale), điều này có thể **không đúng**. Hãy ghi rõ quyết định đó và đặc biệt cân nhắc trước khi truyền comparator vào `TreeSet` hoặc `TreeMap`.

## 9. Mẫu kiểm thử contract tự động trên bộ dữ liệu nhỏ

Tạo file **`ComparatorContractDemo.java`**. Hàm kiểm tra dưới đây duyệt mọi cặp và mọi bộ ba trong một tập mẫu hữu hạn. Đây là **kiểm thử có tính xác định**, không phải bằng chứng toán học rằng comparator đúng trên mọi input.

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class ComparatorContractDemo {
    static <T> void check(
            List<T> samples,
            Comparator<? super T> cmp
    ) {
        for (T a : samples) {
            if (cmp.compare(a, a) != 0) {
                throw new AssertionError("reflexivity");
            }
            for (T b : samples) {
                int ab = Integer.signum(cmp.compare(a, b));
                int ba = Integer.signum(cmp.compare(b, a));
                if (ab != -ba) {
                    throw new AssertionError("antisymmetry");
                }

                for (T c : samples) {
                    int bc = Integer.signum(cmp.compare(b, c));
                    int ac = Integer.signum(cmp.compare(a, c));

                    if (ab > 0 && bc > 0 && ac <= 0) {
                        throw new AssertionError("transitivity");
                    }
                    if (ab == 0 && ac != bc) {
                        throw new AssertionError("equal-key substitution");
                    }
                }
            }
        }
    }

    public static void main(String[] args) {
        List<Integer> extreme = List.of(
                Integer.MIN_VALUE, -1, 0, 1, Integer.MAX_VALUE
        );
        check(extreme, Integer::compare);
        System.out.println("Integer comparator: PASS");

        List<Integer> nullable = Arrays.asList(null, -1, 0, 1);
        check(nullable,
                Comparator.nullsFirst(Comparator.naturalOrder()));
        System.out.println("Nullable comparator: PASS");

        Comparator<Integer> bad = (a, b) -> a - b;
        System.out.println("Wrong overflow sign: "
                + (bad.compare(Integer.MAX_VALUE, -1) < 0));
    }
}
```

Chạy:

```bash
javac --release 17 ComparatorContractDemo.java
java ComparatorContractDemo
```

**Stdout:**

```text
Integer comparator: PASS
Nullable comparator: PASS
Wrong overflow sign: true
```

**Vì sao chương trình này có giá trị?**

- Thử `Integer.MIN_VALUE` và `Integer.MAX_VALUE` bắt được những sai lầm mà dữ liệu nhỏ không thể hiện.
- Thêm `null` kiểm tra liệu comparator khai báo “nullsFirst” có thực sự hoạt động như một total ordering trên miền đã cho.
- Duyệt mọi bộ ba có độ phức tạp `O(n³)`, hợp lý cho **tập mẫu nhỏ trong unit test**, nhưng không phải một phép thử nên chạy với hàng triệu bản ghi.
- Mã chỉ in `PASS` cho các comparator đã qua các điều kiện trong tập mẫu. Nó **không kiểm thử tính nhất quán với `equals`** vì điều đó có thể là một quyết định thiết kế, không phải yêu cầu cứng của Comparator.
- Comparator `bad` được minh họa bằng dấu sai trên cặp cực trị; không chạy nó vào `sort` trên production data.

Khi cần kiểm thử sâu hơn, có thể dùng **property-based testing** (sinh nhiều bộ dữ liệu cùng các phần tử biên), kiểm thử metamorphic hoặc mẫu ngẫu nhiên với seed cố định. Vẫn phải review logic và invariant vì chạy nhiều lần không chứng minh được mọi trường hợp.

## 10. Kiểm thử thứ tự phân cấp và dữ liệu null qua ví dụ nghiệp vụ

Một danh sách nhân viên cần:

1. Xếp điểm đánh giá giảm dần.
2. Nếu điểm bằng nhau, xếp theo tên tăng dần, cho phép tên null ở cuối.
3. Nếu vẫn hòa, xếp theo ID để giữ thứ tự đầu ra nhất quán.

Mẫu xây comparator (đoạn mã trong phương thức, giả sử `Employee` có `score()` kiểu `int`, `name()` kiểu `String` và `id()` kiểu `long`):

```java
Comparator<Employee> employeeOrder =
        Comparator.comparingInt(Employee::score)
                .reversed()
                .thenComparing(
                        Employee::name,
                        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
                )
                .thenComparingLong(Employee::id);
```

Giải thích chính xác:

- `reversed()` ngay sau `comparingInt(score)` **chỉ đảo phần điểm** trước khi gắn các tie-breakers.
- `thenComparing(Employee::name, ...)` chỉ so tên khi điểm bằng nhau.
- `nullsLast(String.CASE_INSENSITIVE_ORDER)` là chính sách **null key**, không phải null Employee.
- `thenComparingLong(Employee::id)` là khóa phụ nếu điểm và tên còn ngang nhau.
- Nếu cần cả **phần tử Employee null**, bọc `Comparator.nullsLast(employeeOrder)` **sau khi đã ghép đủ các khóa**.

Nếu viết:

```java
Comparator<Employee> different =
        Comparator.comparingInt(Employee::score)
                .thenComparing(Employee::name)
                .reversed();
```

thì `reversed()` ở cuối đảo **toàn bộ thứ tự nhiều khóa**, không chỉ đảo điểm. Hai ý định khác nhau tạo ra kết quả khác nhau; phải có test dữ liệu có điểm bằng nhau để phát hiện sai sót.

### 10.1. Thử mọi dạng hòa khóa

Với comparator nhiều khóa, cần các cặp:

- Điểm khác nhau → kiểm tra khóa chính.
- Điểm bằng, tên khác → kiểm tra khóa thứ hai.
- Điểm bằng, tên đều null → kiểm tra khóa ID.
- Điểm bằng, tên cùng chữ nhưng khác hoa/thường → tùy case-insensitive comparator, kiểm tra tie-breaker.
- Mọi khóa comparator đều ngang → kiểm tra hành vi sort ổn định hoặc tính uniqueness trong sorted collection.

Không chỉ thử “mỗi người một điểm khác nhau”, vì như thế `thenComparing` có thể sai hoàn toàn mà unit test vẫn xanh.

## 11. Chuỗi, Unicode và quy tắc nghiệp vụ

### 11.1. Case-sensitive và case-insensitive

`String::compareTo` phân biệt hoa–thường theo quy tắc sắp xếp của `String`, không phải **ngữ nghĩa ngôn ngữ tự nhiên**. `String.CASE_INSENSITIVE_ORDER` bỏ qua nhiều khác biệt hoa–thường theo các quy tắc Java tương ứng, nhưng **không phải một thứ tự ngôn ngữ địa phương đầy đủ** cho mọi locale và trường hợp Unicode.

Ví dụ:

```java
Comparator<String> insensitive = String.CASE_INSENSITIVE_ORDER;

System.out.println(insensitive.compare("Java", "java") == 0);
// true
```

Đây là đoạn mã trong phương thức; import `java.util.Comparator`. Một `TreeSet<String>` sử dụng comparator này có thể coi hai chuỗi là cùng key khi bỏ qua hoa–thường. Nếu đây là *đúng* định nghĩa duy nhất của tên mã, có thể chấp nhận; nếu không, cần tie-breaker khác.

### 11.2. Locale và dữ liệu thực tế

Đối với tên người, địa chỉ hoặc dữ liệu đa ngôn ngữ, việc sắp xếp có thể phải theo quy tắc locale đã chọn. `java.text.Collator` vẫn có trong Java SE và có thể dùng để xây comparator locale-aware, nhưng phải cấu hình và kiểm thử trên các chuỗi Unicode cụ thể, dấu và quy tắc normalization mong muốn.

Không giả định cách sắp xếp mặc định của máy chủ sẽ thỏa yêu cầu mọi quốc gia. Nếu dùng comparator dựa vào locale, hãy chốt locale và quy tắc trong hợp đồng ứng dụng, tránh thay đổi do thiết lập môi trường. Với các object/ký tự Unicode đặc biệt, có thể cần chuẩn hóa đầu vào rõ ràng khi nghiệp vụ yêu cầu.

## 12. Các tình huống biên khác

### 12.1. Dữ liệu rỗng và danh sách một phần tử

Sort một danh sách rỗng hoặc một phần tử không chứng minh comparator đúng: comparator có thể không được gọi. Vì vậy phải có test **hai phần tử trái thứ tự**, **hai phần tử khóa bằng nhau** và **ba phần tử để kiểm tra tính bắc cầu**.

### 12.2. Khóa mutable trong TreeSet/TreeMap

Đừng dùng một trường **có thể thay đổi trong khi phần tử đang nằm trong sorted collection** làm cơ sở comparator. Nếu chỉnh sửa priority của object đã chèn vào `TreeSet`, cấu trúc cây không tự sắp xếp lại, khiến `contains/remove` và thứ tự duyệt có thể trở nên không còn phù hợp với comparator. Cách an toàn là dùng key bất biến hoặc remove theo trạng thái cũ rồi cập nhật và chèn lại bằng quy trình có kiểm soát.

### 12.3. Thứ tự có ổn định không?

- `List.sort` và `Arrays.sort(Object[], comparator)` bảo đảm **stable**.
- `Stream.sorted(comparator)` ổn định khi stream có **encounter order**; với **unordered stream**, độ ổn định không được bảo đảm.
- `TreeSet`/`TreeMap` là cấu trúc dựa trên thứ tự comparator; không phải “sort ổn định giữ tất cả phần tử dù comparator trả 0”.
- `HashSet`/`HashMap` không dùng Comparator để xác định uniqueness và không có cam kết thứ tự iteration như `TreeSet`/`TreeMap`.
- Đừng lấy việc “sort ổn định giữ thứ tự khi hòa” làm chính sách thứ tự đầu ra cho hệ thống phân trang phân tán nếu dữ liệu đến từ nhiều nguồn theo thứ tự không ổn định. Khi cần phân trang ổn định, thêm khóa phụ có tính quyết định như ID, và đảm bảo invariant cần thiết.

### 12.4. Comparator dựa trên trạng thái bên ngoài

Ví dụ comparator đọc một `Map` priority có thể bị cập nhật từ thread khác trong lúc sort: một đối tượng có thể được đánh giá khác nhau giữa các lần `compare`, làm mất tính nhất quán của thứ tự ngay trong một lần sắp xếp. Nên lấy snapshot ổn định hoặc thiết kế comparator dựa trên thuộc tính bất biến trong thời gian sort.

### 12.5. Tránh dùng kết quả số học của comparator như khoảng cách

`compare(a,b)` chỉ mang ý nghĩa dấu âm, bằng 0, dương. Không dùng trị tuyệt đối của kết quả để nói “a khác b bao nhiêu điểm” hoặc để tính khoảng cách. Nếu cần metric khoảng cách, hãy tính từ thuộc tính số bằng công thức riêng, có xử lý overflow/precision.

## 13. Bộ test gợi ý cho các tình huống production

Một tập kiểm thử thực tế cho comparator dùng trong nghiệp vụ có thể tổ chức như sau:

| Nhóm test | Ví dụ assertion |
| --- | --- |
| Khóa chính | `compare(low, high) < 0` |
| Khóa bằng nhau | `compare(samePrimaryA, samePrimaryB) == 0` nếu không có tie-breaker |
| Tie-breaker | `compare(samePrimaryLowerId, samePrimaryHigherId) < 0` |
| Reflexivity | `compare(x, x) == 0` |
| Antisymmetry | `signum(ab) == -signum(ba)` |
| Transitivity | Nếu a ≤ b và b ≤ c thì a ≤ c |
| Equal-key substitution | Nếu a ~ b thì với mọi c, hai phép so với c có cùng dấu |
| Null object | Bao bọc comparator ngoài cùng hoặc xác nhận lỗi theo contract |
| Null field | `comparing(keyExtractor, nullsFirst/Last(...))` |
| Hai null keys | Hai field null có so tiếp khóa phụ không? |
| Overflow | `MIN_VALUE` và `MAX_VALUE` |
| Floating point | `-0.0`, `+0.0`, `NaN`, `±Infinity` |
| Text equivalence | `"abc"` vs `"ABC"`, text Unicode theo contract |
| Sorted collection | `TreeSet`/`TreeMap` có collapse key ngoài ý muốn không? |
| Stable sort | Với equal keys, ordered source có giữ thứ tự tương đối không? |
| Mutability | Key object có bất biến trong suốt vòng đời trong tree không? |

**Những kiểm thử nên được tự động hóa ở hai tầng:** (a) test trực tiếp comparator trên mẫu cụ thể và tính chất, (b) test tích hợp với `List.sort` / `Stream.sorted` / `TreeSet` / `TreeMap` theo đúng cách production sử dụng. Một comparator hợp lệ trên phần tử thường vẫn có thể không phù hợp với mục tiêu **uniqueness** của dữ liệu.

## 14. Các lỗi phổ biến cần tránh

1. **Chỉ test khóa khác nhau:** không kiểm được `thenComparing` hay cách xử lý hòa khóa.
2. **Nghĩ `compare == 0` luôn là `equals == true`:** hai khái niệm không tương đương nếu comparator chỉ dùng một số field.
3. **Dùng Comparator có nhiều khóa trùng làm TreeSet rồi thắc mắc mất phần tử:** set lấy comparator làm quan hệ tương đương.
4. **Quên tie-breaker khi cần kết quả ổn định độc lập input:** stable sort vẫn phụ thuộc thứ tự ban đầu của các phần tử hòa.
5. **Chỉ bọc `Comparator.nullsLast(byName)` nhưng key name null:** wrapper ngoài xử lý null **object**, không xử lý null **field**.
6. **Chỉ xử lý null key nhưng list chứa null object:** key extractor vẫn có thể NPE.
7. **Bọc nullsLast trước thenComparing rồi cho hai object null:** comparator phụ có thể bị chạy trên null.
8. **Quên rằng `nullsLast(cmp).reversed()` sẽ đổi null thành đứng đầu:** đảo thứ tự trong comparator bên trong khi muốn giữ null cuối.
9. **Dùng `nullsFirst(null)` và nghĩ các object khác null được so tự nhiên:** theo API, chúng đều ngang nhau.
10. **Dùng `(a,b) -> a-b` cho số nguyên:** overflow ở dữ liệu biên phá thứ tự.
11. **Dùng `(int)(longA-longB)` cho timestamp:** overflow/ép kiểu phá thứ tự; dùng `Long.compare`.
12. **Dùng so sánh `<`/`>` cho double rồi coi NaN bằng tất cả:** vi phạm luật thứ tự; dùng `Double.compare`.
13. **Không xét `-0.0` và `+0.0`:** `Double.compare` phân biệt chúng dù toán tử == không phân biệt.
14. **Tưởng `BigDecimal.compareTo` bằng 0 thì `equals` true:** scale có thể khác; sorted set/map có thể gộp hai key khác theo equals.
15. **Test bằng `List.of(null, ...)`:** lỗi xảy ra khi tạo list, không chứng minh comparator null-safe.
16. **So sánh chính xác giá trị âm trả về của compare:** hợp đồng chỉ quy định dấu.
17. **Dùng comparator có logic không bắc cầu:** có thể khiến sort không đáng tin; JVM không bắt buộc phát hiện mọi lỗi.
18. **Đổi trạng thái đối tượng trong TreeSet sau khi chèn:** comparator thấy khóa mới nhưng cây không tái sắp xếp.
19. **Đọc trạng thái mutable ngoài comparator khi sort:** có thể làm một cặp giá trị được so khác nhau ở hai thời điểm.
20. **Dùng comparator locale-sensitive mà không chốt locale:** kết quả có thể không phù hợp hợp đồng nhất quán của ứng dụng.

## 15. Câu hỏi tự kiểm tra

1. Hai task khác ID nhưng cùng priority được so bởi `Comparator.comparingInt(Task::priority)`: kết quả `compare` là gì? `equals` nhất thiết có cùng kết quả không?
2. Vì sao `Stream.sorted` có thể giữ cả hai task cùng priority còn `TreeSet` dùng comparator đó có thể chỉ giữ một?
3. Khi nào cần `thenComparingInt(Task::id)`? Điều gì vẫn cần đảm bảo nếu dùng comparator trong TreeSet?
4. `Comparator.nullsLast(Comparator.comparing(Person::name))` đã an toàn khi `Person` khác null nhưng `name` null chưa?
5. Tại sao `Comparator.nullsLast(cmp).thenComparingInt(Person::id)` có thể NPE nếu so hai phần tử null?
6. Vì sao `(a,b) -> a-b` sai với `Integer.MAX_VALUE` và `-1`?
7. `Double.compare(-0.0, +0.0)` âm hay dương? `Double.compare(Double.NaN, Double.POSITIVE_INFINITY)` âm hay dương?
8. `new BigDecimal("1.0").compareTo(new BigDecimal("1.00"))` bằng 0, nhưng `equals` trả gì?
9. Ba luật hợp đồng quan trọng nhất của comparator là gì? Nếu `compare(a,b)==0`, phải có quan hệ gì với một phần tử thứ ba c?
10. Vì sao không nên dùng field mutable làm khóa comparator cho object đã nằm trong TreeSet?

**Gợi ý:** (1) 0, không nhất thiết bằng nhau theo equals. (2) sort giữ các phần tử còn TreeSet xác định tương đương bằng comparator. (3) khi cần phân biệt hòa khóa; đồng thời phải thỏa uniqueness/equality theo domain. (4) chưa; cần null key comparator. (5) comparator phụ có thể truy cập field trên null sau khi comparator đầu trả 0. (6) overflow. (7) âm và dương. (8) false vì scale. (9) antisymmetry về dấu, transitivity, equal-key substitution. (10) cây không tự tái cấu trúc sau khi key thay đổi.

**Kết luận:** Kiểm thử Comparator không dừng ở việc hai số khác nhau được xếp đúng chiều. Phải thử **khóa bằng nhau**, phân biệt `compare == 0` với `equals`, chủ động quy định **null object và null extracted key**, đưa vào **giới hạn số và giá trị số thực đặc biệt**, và xác minh những luật thứ tự trên các **cặp/bộ ba**. Khi comparator được dùng trong `TreeSet`/`TreeMap`, tiêu chí `compare == 0` còn quyết định việc phần tử/key có bị gộp, nên cần thiết kế equivalence theo ý nghĩa nghiệp vụ.

## Tài liệu chính thức (API vẫn được hỗ trợ trên JDK hiện đại)

- `Comparator<T>` — hợp đồng thứ tự, `comparing`, `thenComparing`, `nullsFirst`, `nullsLast`, `reversed`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html
- `TreeSet` — quan hệ `compare == 0` với uniqueness và equals: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html
- `TreeMap` — comparator quyết định thứ tự và tương đương key: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html
- `List.sort` — stable sort: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html
- `Arrays.sort` — stable sorting cho mảng đối tượng: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html
- `Stream.sorted` — ổn định đối với ordered streams: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- `Double.compare` — quy tắc NaN và signed zero: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html
- `BigDecimal.compareTo` và `equals`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html
