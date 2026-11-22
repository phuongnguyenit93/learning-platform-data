# Comparator.naturalOrder, reverseOrder và reversed

## 1. Mục đích: điều khiển thứ tự so sánh

Trong Java, `Comparator<T>` mô tả **cách so sánh hai giá trị kiểu `T`**. Một comparator trả số âm, `0` hoặc số dương khi phần tử bên trái lần lượt đứng trước, tương đương hoặc đứng sau phần tử bên phải theo thứ tự đã định. Từ Java 8, `Comparator` có ba API đặc biệt tiện dụng:

- **`Comparator.naturalOrder()`**: tạo comparator xếp các đối tượng `Comparable` theo **thứ tự tự nhiên tăng dần**, ví dụ `1,2,3` hoặc thứ tự từ điển do `String.compareTo` định nghĩa.
- **`Comparator.reverseOrder()`**: tạo comparator xếp các đối tượng `Comparable` theo **thứ tự ngược với thứ tự tự nhiên**, ví dụ `3,2,1`.
- **`someComparator.reversed()`**: lấy một **comparator đã có** và tạo comparator với **thứ tự ngược lại** của chính comparator đó, kể cả khi nó là một quy tắc nhiều trường chứ không phải thứ tự tự nhiên.

Cả ba API đều được hỗ trợ trong Java hiện đại. Phạm vi bài là **ngữ nghĩa so sánh và lựa chọn thứ tự sắp xếp**, không phải cách tối ưu hóa thuật toán sort.

Ví dụ trực quan:

```java
List<Integer> nums = new ArrayList<>(Arrays.asList(4, 1, 3, 2));
nums.sort(Comparator.naturalOrder());
// nums = [1, 2, 3, 4]

nums.sort(Comparator.reverseOrder());
// nums = [4, 3, 2, 1]
```

Đây là **đoạn mã minh họa trong method**, cần import các lớp `java.util.*`. `List.sort` sửa trực tiếp danh sách. Ở mục 6 có chương trình biên dịch/chạy độc lập và kết quả stdout đã được kiểm tra.

## 2. Cơ chế của `Comparable` và thứ tự tự nhiên

### 2.1. Một kiểu phải có natural order mới dùng được `naturalOrder`

`Comparator.naturalOrder()` có ràng buộc generic đại ý:

```java
<T extends Comparable<? super T>> Comparator<T> naturalOrder()
```

Nó gọi hợp đồng so sánh tự nhiên của đối tượng `Comparable`. Những lớp thường gặp đã có `Comparable` gồm `Integer`, `Long`, `String`, `BigDecimal`, `LocalDate` và nhiều lớp giá trị khác. Với một lớp `Employee` tự tạo **không** triển khai `Comparable`, việc `employees.sort(Comparator.naturalOrder())` không được chấp nhận về mặt kiểu; lúc đó nên dùng `Comparator.comparing(...)` hoặc `comparingInt(...)` để định nghĩa thứ tự theo trường nghiệp vụ.

Ví dụ:

```java
Comparator<Integer> byNumber = Comparator.naturalOrder();
Comparator<String> byText = Comparator.naturalOrder();
Comparator<LocalDate> byDate = Comparator.naturalOrder();
```

Đây là snippet với các import `java.util.Comparator` và `java.time.LocalDate`. `naturalOrder` **không tự suy ra** rằng một đối tượng nghiệp vụ cần sắp theo tên, điểm hay ngày tạo.

### 2.2. Tự nhiên nghĩa là thứ tự do **kiểu** quy định

- `Integer.compareTo`: thứ tự số nguyên tăng dần.
- `LocalDate.compareTo`: thứ tự ngày sớm đến ngày muộn.
- `String.compareTo`: thứ tự từ điển theo giá trị **UTF-16 code unit** trong chuỗi, có phân biệt chữ hoa/thường; **không tự động** là sắp xếp ngôn ngữ tiếng Việt.
- `BigDecimal.compareTo`: so sánh theo **giá trị số**, có thể xem `1.0` và `1.00` tương đương mặc dù `BigDecimal.equals` trả `false`. Điều này đặc biệt quan trọng với `TreeSet`/`TreeMap`.

Nếu yêu cầu là sắp xếp văn bản theo quy tắc ngôn ngữ, dùng `Collator` với `Locale` phù hợp sau khi kiểm thử quy tắc chuẩn hóa; đừng xem `String.compareTo` là thuật toán xếp thứ tự theo mọi ngôn ngữ.

### 2.3. Ý nghĩa số do comparator trả về

`Comparator.compare(a,b)` yêu cầu:

```text
< 0  : a đứng trước b
  0  : a và b tương đương theo comparator này
> 0  : a đứng sau b
```

Không yêu cầu trả chính xác `-1`, `0` hay `1`. Hợp đồng còn yêu cầu tính phản đối xứng về dấu, tính bắc cầu (transitivity), và sự nhất quán khi hai phần tử được xem là tương đương. Comparator sai hợp đồng có thể gây sắp xếp sai hoặc lỗi `IllegalArgumentException: Comparison method violates its general contract!` trong một số tình huống.

**Không** lấy phép trừ thô `a - b` để so sánh số nguyên tùy ý: phép trừ có thể tràn `int` và đảo dấu sai. Dùng `Integer.compare(a,b)` hoặc `Comparator.naturalOrder()`. Khi muốn đảo thứ tự, dùng `reversed()` thay vì tự viết `-compare(a,b)` (nếu compare có thể trả `Integer.MIN_VALUE`, phép đổi dấu cũng tràn).

## 3. `Comparator.naturalOrder()`: từ nhỏ đến lớn

Dạng sử dụng phổ biến:

```java
Comparator<Integer> ascending = Comparator.naturalOrder();

List<Integer> numbers = new ArrayList<>(
    Arrays.asList(6, 2, 4, 1));
numbers.sort(ascending);
// [1, 2, 4, 6]
```

Có thể truyền trực tiếp comparator vào những API nhận `Comparator`:

```java
Arrays.sort(integerArray, Comparator.naturalOrder());
list.sort(Comparator.naturalOrder());
stream.sorted(Comparator.naturalOrder());
new TreeSet<Integer>(Comparator.naturalOrder());
new TreeMap<Integer, String>(Comparator.naturalOrder());
```

Các dòng trên là **minh họa chữ ký/cách gọi**, không phải chương trình độc lập: cần định nghĩa trước `integerArray` kiểu `Integer[]`, `list`, `stream` và các import. `Arrays.sort(int[], Comparator)` **không tồn tại** vì mảng primitive `int[]` dùng overload sort riêng; khi cần comparator, dùng kiểu tham chiếu `Integer[]` hoặc cấu trúc tương ứng. Với `IntStream`, `sorted()` sắp tăng dần theo primitive; muốn thứ tự giảm, cần thiết kế đường đi khác, có thể boxing hoặc thao tác trên array primitive theo yêu cầu hiệu năng.

`List.sort` và `Arrays.sort` thao tác trực tiếp lên cấu trúc nguồn, còn `Stream.sorted(comparator)` là **intermediate operation** trả stream mới; phép sắp xếp diễn ra khi chạy terminal operation và không sửa danh sách gốc chỉ vì có `sorted`.

### 3.1. Thứ tự tự nhiên đối với string không phải “bảng chữ cái” đơn giản

```java
List<String> words = new ArrayList<>(
    Arrays.asList("java", "API", "stream", "Go"));
words.sort(Comparator.naturalOrder());
// [API, Go, java, stream]
```

Kết quả dựa trên `String.compareTo`, nên chữ hoa Latin và chữ thường Latin có thể nằm ở các vùng thứ tự khác nhau. Nếu nghiệp vụ muốn bỏ qua chữ hoa/thường, cần comparator riêng như `String.CASE_INSENSITIVE_ORDER` và cân nhắc việc hai chuỗi không bằng nhau theo `equals` lại có `compare == 0`.

## 4. `Comparator.reverseOrder()`: đảo thứ tự **tự nhiên**

Dạng khai báo:

```java
<T extends Comparable<? super T>> Comparator<T> reverseOrder()
```

`Comparator.reverseOrder()` tạo comparator so sánh ngược với `Comparable.compareTo`. Nó không nhận một comparator khác làm tham số; nó giả định phần tử có **natural order**.

```java
List<String> words = new ArrayList<>(
    Arrays.asList("java", "API", "stream", "Go"));
words.sort(Comparator.reverseOrder());
// [stream, java, Go, API]
```

Về **thứ tự so sánh** đối với cùng các giá trị `Comparable` không null, hai lựa chọn sau tương đương:

```java
Comparator<String> a = Comparator.reverseOrder();
Comparator<String> b = Comparator.<String>naturalOrder().reversed();
```

Đây là **tương đương về thứ tự**, không có cam kết `a == b` hay `a.equals(b)`. Nếu đầu vào là một kiểu không có `Comparable` nhưng có comparator riêng, hãy lấy **comparator riêng đó** rồi gọi `reversed()`; `reverseOrder()` không giúp tự động đảo một quy tắc tùy biến.

### 4.1. Không nhầm với `Collections.reverse(list)`

`Collections.reverse(list)` **đảo thứ tự hiện có của các phần tử trong list**, không so sánh lại chúng:

```java
List<Integer> values = new ArrayList<>(Arrays.asList(3, 1, 2));
Collections.reverse(values);
// [2, 1, 3], không phải thứ tự giảm [3, 2, 1]
```

Ngược lại, `values.sort(Comparator.reverseOrder())` sẽ sắp xếp thật sự thành `[3, 2, 1]`. Chỉ có thể coi “đảo list” là đảo chiều sắp xếp khi list **đã được sắp** theo thứ tự thích hợp và không có yêu cầu phụ về tính ổn định với các phần tử tương đương.

## 5. `Comparator.reversed()`: đảo comparator **đang có**

`reversed()` là một **default method** của `Comparator<T>`:

```java
Comparator<T> reversed()
```

Nó trả về một comparator diễn giải thứ tự **ngược với comparator gốc**. Điều này có nghĩa đảo cả quy tắc đang được biểu diễn, không tự biết “trường nào quan trọng” đối với ứng dụng.

Ví dụ sắp nhân viên theo điểm:

```java
Comparator<Employee> byScoreAscending =
    Comparator.comparingInt(Employee::score);

Comparator<Employee> byScoreDescending =
    byScoreAscending.reversed();
```

Đoạn này giả định lớp `Employee` có method `int score()` như ví dụ mục 6. Không bắt buộc `Employee implements Comparable`, vì `comparingInt` đã có cách trích khóa số.

### 5.1. Đảo cả comparator ghép nhiều mức

Giả sử muốn **điểm giảm dần, tên tăng dần**. Cách viết:

```java
Comparator<Employee> byScoreDescNameAsc =
    Comparator.comparingInt(Employee::score)
        .reversed()
        .thenComparing(Employee::name);
```

`reversed()` đặt **trước** `thenComparing`, nên chỉ comparator điểm ở mức đầu được đảo. Nếu hai nhân viên cùng điểm, tên được so sánh **tăng dần** theo natural order.

Trong khi đó:

```java
Comparator<Employee> bothDescending =
    Comparator.comparingInt(Employee::score)
        .thenComparing(Employee::name)
        .reversed();
```

`reversed()` đặt **sau** `thenComparing`, nên **toàn bộ comparator ghép** bị đảo: điểm giảm dần, và khi cùng điểm thì **tên giảm dần**. Đây là một khác biệt quan trọng khi review code.

| Quy tắc | Biểu thức | Thứ tự nhóm cùng điểm |
| --- | --- | --- |
| Điểm tăng, tên tăng | `comparingInt(score).thenComparing(name)` | Tên tăng |
| Điểm giảm, tên tăng | `comparingInt(score).reversed().thenComparing(name)` | Tên tăng |
| Điểm giảm, tên giảm | `comparingInt(score).thenComparing(name).reversed()` | Tên giảm |
| Điểm tăng, tên giảm | `comparingInt(score).thenComparing(comparing(name).reversed())` | Tên giảm |

Các biểu thức trong bảng là **ký pháp rút gọn**, còn code Java đầy đủ có tên lớp/kiểu phù hợp nằm ở mục 6. Đối với key extractor cần tránh boxing, `comparingInt`, `comparingLong`, `comparingDouble` hữu ích, nhưng chỉ tối ưu sau khi đảm bảo thứ tự đúng nghiệp vụ.

### 5.2. Đảo hai lần và so sánh comparator

`cmp.reversed().reversed()` **áp đặt cùng thứ tự so sánh** như `cmp`. Nhưng không nên suy ra hai object comparator giống hệt nhau về identity hoặc `equals`. Mục đích của Comparator là mô tả quan hệ thứ tự; hãy kiểm tra kết quả sắp xếp hoặc các dấu của `compare` khi cần xác minh.

Chú ý: `reversed()` trả comparator mới về mặt hợp đồng API, song không bắt buộc mọi lần gọi phải cấp phát một đối tượng mới vật lý; không dùng identity làm điều kiện nghiệp vụ.

## 6. Chương trình Java hoàn chỉnh: ba phương thức và thứ tự nhiều tiêu chí

Lớp sau là chương trình chạy độc lập, dùng **chỉ API tương thích Java 8**. Ví dụ kiểm tra số nguyên, chữ, comparator nhiều cấp, `null` và tác động của comparator đến `TreeSet`.

Tạo tệp **ComparatorDirectionsDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class ComparatorDirectionsDemo {
    static final class Employee {
        private final String name;
        private final int score;

        Employee(String name, int score) {
            this.name = name;
            this.score = score;
        }

        String name() {
            return name;
        }

        int score() {
            return score;
        }

        @Override
        public String toString() {
            return name + ":" + score;
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers =
            Arrays.asList(4, 1, 3, 2);

        List<Integer> asc = new ArrayList<>(numbers);
        asc.sort(Comparator.naturalOrder());

        List<Integer> desc = new ArrayList<>(numbers);
        desc.sort(Comparator.reverseOrder());

        List<Integer> reversed = new ArrayList<>(numbers);
        reversed.sort(Comparator.<Integer>naturalOrder().reversed());

        System.out.println("Natural: " + asc);
        System.out.println("Reverse: " + desc);
        System.out.println("Reversed natural: " + reversed);

        List<String> words =
            Arrays.asList("java", "API", "stream", "Go");
        List<String> naturalWords = new ArrayList<>(words);
        naturalWords.sort(Comparator.naturalOrder());
        List<String> reverseWords = new ArrayList<>(words);
        reverseWords.sort(Comparator.reverseOrder());

        System.out.println("Words natural: " + naturalWords);
        System.out.println("Words reverse: " + reverseWords);

        List<Employee> employees = Arrays.asList(
            new Employee("Lan", 90),
            new Employee("Binh", 90),
            new Employee("An", 95),
            new Employee("Hoa", 88)
        );

        Comparator<Employee> descScoreAscName =
            Comparator.comparingInt(Employee::score)
                .reversed()
                .thenComparing(Employee::name);

        Comparator<Employee> reverseWhole =
            Comparator.comparingInt(Employee::score)
                .thenComparing(Employee::name)
                .reversed();

        List<Employee> mixed = new ArrayList<>(employees);
        mixed.sort(descScoreAscName);
        List<Employee> allReverse = new ArrayList<>(employees);
        allReverse.sort(reverseWhole);

        System.out.println("Score desc, name asc: " + mixed);
        System.out.println("Reverse whole chain: " + allReverse);

        List<String> withNull =
            Arrays.asList("Java", null, "SQL", "API");
        List<String> nullLast = new ArrayList<>(withNull);
        nullLast.sort(Comparator.nullsLast(
            Comparator.naturalOrder()));
        List<String> nullLastDesc =
            new ArrayList<>(withNull);
        nullLastDesc.sort(Comparator.nullsLast(
            Comparator.reverseOrder()));
        List<String> reverseNullPolicy =
            new ArrayList<>(withNull);
        reverseNullPolicy.sort(Comparator.<String>nullsLast(
            Comparator.naturalOrder()).reversed());

        System.out.println("Null last asc: " + nullLast);
        System.out.println("Null last desc: " + nullLastDesc);
        System.out.println("Reversed null policy: " + reverseNullPolicy);

        TreeSet<Employee> byScoreOnly =
            new TreeSet<>(Comparator.comparingInt(Employee::score));
        byScoreOnly.addAll(employees);
        System.out.println("TreeSet score-only size: "
            + byScoreOnly.size());

        int smallestByReverse = numbers.stream()
            .max(Comparator.reverseOrder())
            .orElseThrow(IllegalStateException::new);
        System.out.println("Max(reverseOrder): " + smallestByReverse);
    }
}
```

Biên dịch và chạy ở thư mục chứa tệp:

```bash
javac -encoding UTF-8 ComparatorDirectionsDemo.java
java ComparatorDirectionsDemo
```

**Stdout chính xác:**

```text
Natural: [1, 2, 3, 4]
Reverse: [4, 3, 2, 1]
Reversed natural: [4, 3, 2, 1]
Words natural: [API, Go, java, stream]
Words reverse: [stream, java, Go, API]
Score desc, name asc: [An:95, Binh:90, Lan:90, Hoa:88]
Reverse whole chain: [An:95, Lan:90, Binh:90, Hoa:88]
Null last asc: [API, Java, SQL, null]
Null last desc: [SQL, Java, API, null]
Reversed null policy: [null, SQL, Java, API]
TreeSet score-only size: 3
Max(reverseOrder): 1
```

**Giải thích:**

1. Cùng dãy số `[4,1,3,2]`, `naturalOrder` xếp tăng; `reverseOrder` và `naturalOrder().reversed()` cho cùng thứ tự giảm.
2. `String.compareTo` phân biệt hoa/thường; vì vậy `API`, `Go` nằm trước `java`, `stream` theo natural order.
3. Với điểm `90`, `Binh` đứng trước `Lan` nếu **chỉ đảo điểm rồi thêm tiêu chí tên tăng**; nhưng `Lan` đứng trước `Binh` nếu **đảo toàn bộ chuỗi so sánh**.
4. `nullsLast(naturalOrder())` đặt null cuối và sắp các chuỗi không null tăng dần. `nullsLast(reverseOrder())` giữ null cuối nhưng sắp các chuỗi khác theo giảm dần.
5. Gọi `reversed()` cho comparator **đã bọc `nullsLast`** đảo **cả quan hệ thứ tự**, nên null chuyển lên **đầu**.
6. `TreeSet` dùng `compare(a,b)==0` để xác định hai phần tử tương đương; khi chỉ so theo `score`, `Binh:90` và `Lan:90` bị coi là một nhóm, nên kích thước chỉ còn 3. Đây có thể là lỗi mất dữ liệu nếu ứng dụng dùng so điểm làm định danh.
7. `Stream.max(comparator)` chọn phần tử lớn **theo comparator được truyền**. Khi dùng `reverseOrder` cho số, “lớn nhất theo comparator” chính là `1`, phần tử nhỏ nhất theo natural order.

## 7. `null` và cách kết hợp với đảo thứ tự

`Comparator.naturalOrder()` và `Comparator.reverseOrder()` không cho phép so sánh `null`; việc sắp danh sách chứa `null` với hai comparator đó có thể ném `NullPointerException`. Nếu null là dữ liệu hợp lệ, chọn quy tắc đặt null **một cách tường minh**:

```java
Comparator<String> ascendingNullLast =
    Comparator.nullsLast(Comparator.naturalOrder());

Comparator<String> descendingNullLast =
    Comparator.nullsLast(Comparator.reverseOrder());

Comparator<String> descendingNullFirst =
    Comparator.nullsFirst(Comparator.reverseOrder());
```

Các phương thức `nullsFirst`, `nullsLast` trả comparator có thể xử lý null bên ngoài; `Comparator.nullsLast(Comparator.naturalOrder())` **không thay đổi** cách so sánh những giá trị khác null.

**Bẫy thứ tự phương thức:**

```java
Comparator<String> a = Comparator.nullsLast(
    Comparator.<String>naturalOrder().reversed()
); // null vẫn cuối

Comparator<String> b = Comparator.<String>nullsLast(
    Comparator.naturalOrder()
).reversed(); // null lên đầu
```

Trong `a`, đảo comparator **bên trong** rồi mới bọc quy tắc null-last; trong `b`, đảo **toàn bộ** comparator đã bọc. Cả hai đều hợp lệ nhưng mang nghĩa khác nhau.

Nếu dữ liệu không chấp nhận `null` theo yêu cầu nghiệp vụ, nên validate và báo lỗi đầu vào thay vì tùy tiện cho null lên đầu/cuối; chọn null policy là một quyết định của domain.

## 8. Liên hệ với `List.sort`, `Stream.sorted` và cấu trúc sắp thứ tự

### 8.1. `List.sort` thay đổi danh sách; `Stream.sorted` thì không

```java
List<Integer> original = Arrays.asList(3, 1, 2);

List<Integer> sortedCopy = original.stream()
    .sorted(Comparator.reverseOrder())
    .collect(Collectors.toList());
// sortedCopy = [3, 2, 1]
// original vẫn là [3, 1, 2]
```

Đây là snippet cần import `Arrays`, `List`, `Comparator`, `Collectors`. `Stream.sorted` là intermediate operation, còn `collect` tạo danh sách kết quả. Tùy pipeline, việc dùng stream có thêm overhead; nếu mục tiêu chỉ là sắp lại chính list hiện có, `list.sort(comparator)` trực tiếp hơn.

### 8.2. Tính ổn định (stability) của sort

`List.sort` là phép sắp xếp **ổn định (stable)** theo hợp đồng: các phần tử mà comparator xem là bằng nhau (trả `0`) giữ tương quan thứ tự ban đầu. `Stream.sorted` cũng ổn định **đối với ordered stream**; với unordered stream không có cam kết này.

Ví dụ nếu chỉ sort theo `score`, hai nhân viên cùng điểm có thể giữ thứ tự đầu vào trong `List.sort`; nhưng nếu nghiệp vụ yêu cầu thứ tự tên xác định trong mọi trường hợp, thêm `thenComparing(Employee::name)` rõ ràng hơn là dựa vào thứ tự ban đầu không chắc chắn.

### 8.3. `TreeSet` và `TreeMap` coi `compare(a,b)==0` là cùng khóa

Đây là điểm khác biệt có thể ảnh hưởng **dữ liệu**, không chỉ cách hiển thị:

```java
Comparator<Employee> byScoreOnly =
    Comparator.comparingInt(Employee::score);

Set<Employee> employeesByScore = new TreeSet<>(byScoreOnly);
```

Khi hai nhân viên khác nhau có cùng điểm, `TreeSet` có thể chỉ giữ một phần tử theo comparator. `TreeMap` cũng dùng comparator để xác định tương đương khóa. Nếu muốn phân biệt mọi nhân viên, cần tie-breaker bằng **ID duy nhất ổn định**, và nên cân nhắc quan hệ comparator với `equals` để tránh vi phạm kỳ vọng của các interface `Set`/`Map`.

Ví dụ ý tưởng:

```java
Comparator<Employee> byScoreThenUniqueId =
    Comparator.comparingInt(Employee::score)
        .thenComparing(Employee::id);
```

Đây là snippet mô tả thiết kế **có method `id()` riêng**, không phải code của lớp `Employee` trong chương trình mục 6 (lớp đó chỉ có `name()` và `score()`). Khi cần khóa định danh, mô hình Employee thực tế phải có ID bất biến và phương thức truy cập tương ứng.

## 9. Quy tắc lựa chọn API cho đúng yêu cầu

| Yêu cầu nghiệp vụ | Nên dùng | Lý do |
| --- | --- | --- |
| Số, ngày, chuỗi theo thứ tự tự nhiên tăng | `Comparator.naturalOrder()` | Dựa vào `Comparable` của chính giá trị. |
| Số, ngày, chuỗi theo thứ tự tự nhiên giảm | `Comparator.reverseOrder()` | Đảo natural order trực tiếp. |
| Kiểu nghiệp vụ tự tạo, theo một trường | `Comparator.comparing(...)` / `comparingInt(...)` | Không cần `Comparable` trên cả đối tượng. |
| Đảo thứ tự của comparator tùy biến | `existingComparator.reversed()` | Đảo đúng quan hệ so sánh hiện có. |
| Điểm giảm, tên tăng | `comparingInt(score).reversed().thenComparing(name)` | Chỉ đảo tiêu chí điểm. |
| Điểm giảm, tên giảm | `comparingInt(score).thenComparing(name).reversed()` | Đảo cả chuỗi comparator. |
| Giá trị null cuối, các giá trị khác giảm | `Comparator.nullsLast(Comparator.reverseOrder())` | Giữ chính sách null cuối. |
| Đảo thứ tự phần tử list đã có, không sort | `Collections.reverse(list)` | Đổi vị trí, không so sánh. |
| Giữ nguyên list gốc, tạo kết quả đã sort | `list.stream().sorted(cmp).collect(...)` | Không mutate list gốc. |
| Dùng comparator làm key order của set/map | `TreeSet`/`TreeMap` với comparator có tie-breaker rõ | Tránh coi các đối tượng khác nhau là trùng khóa ngoài ý muốn. |

Một cách phân loại nhanh:

```text
Dữ liệu có natural order cần dùng?
  |
  +-- Có, tăng   -> naturalOrder()
  |
  +-- Có, giảm   -> reverseOrder()
  |
  +-- Không hoặc quy tắc khác
        |
        +-- tạo comparator theo trường: comparing()/comparingInt()...
        |
        +-- muốn đảo quy tắc đã tạo: comparator.reversed()
```

## 10. Những lỗi phổ biến cần tránh

### 10.1. Đặt `reversed()` sai vị trí

```java
// Điểm giảm, tên tăng:
Comparator<Employee> desired =
    Comparator.comparingInt(Employee::score)
        .reversed()
        .thenComparing(Employee::name);

// Điểm giảm, tên giảm:
Comparator<Employee> different =
    Comparator.comparingInt(Employee::score)
        .thenComparing(Employee::name)
        .reversed();
```

Không có biểu thức nào “sai cú pháp”; lỗi là **sai quy tắc nghiệp vụ**. Test dữ liệu có ít nhất hai phần tử **bằng nhau theo tiêu chí đầu tiên** để thấy sự khác biệt.

### 10.2. Dùng `reverseOrder()` với kiểu không có `Comparable`

`Comparator.reverseOrder()` chỉ phù hợp với kiểu có natural order. Nếu `Employee` không triển khai `Comparable<Employee>`, hãy xây comparator:

```java
Comparator<Employee> byScoreDescending =
    Comparator.comparingInt(Employee::score).reversed();
```

Đây là cách tránh biến mọi class nghiệp vụ thành `Comparable` chỉ để hỗ trợ một màn hình.

### 10.3. So sánh bằng phép trừ và đảo dấu thô

```java
Comparator<Integer> wrong = (a, b) -> b - a; // có thể tràn
Comparator<Integer> safe = Comparator.reverseOrder();

// Khi dùng primitive int trong một comparator tùy biến:
Comparator<Integer> safeToo = (a, b) -> Integer.compare(b, a);
```

Một giá trị comparator trả về có thể là số âm lớn (đến `Integer.MIN_VALUE`); dùng `-cmp.compare(a,b)` không an toàn về tràn. `reversed()` là công cụ rõ nghĩa cho việc đảo quan hệ.

### 10.4. Nhầm `Comparator.reverseOrder` với “đảo list”

Không dùng `Collections.reverse` như thay thế cho sort khi list chưa được sắp. `reverse` chỉ đảo thứ tự hiện có.

### 10.5. Không định nghĩa cách xử lý null

Khi có null, `naturalOrder`/`reverseOrder` không dùng trực tiếp. Lựa chọn `nullsFirst`/`nullsLast` phải phản ánh chính sách nghiệp vụ; đặt `reversed` ngoài wrapper null có thể đảo luôn chính sách null.

### 10.6. Comparator không nhất quán với `equals` trong sorted map/set

Ví dụ comparator chỉ so theo độ dài chuỗi: hai chuỗi khác nhau nhưng cùng chiều dài bị coi là cùng khóa trong `TreeSet`. Thêm tie-breaker hoặc thiết kế khóa thích hợp; không coi đây chỉ là vấn đề trình bày.

### 10.7. Tưởng `max(reverseOrder())` vẫn tìm số lớn tự nhiên nhất

`max(cmp)` chọn phần tử **lớn nhất theo thứ tự của cmp**. Khi comparator đảo chiều, tối đa theo comparator bằng **tối thiểu theo natural order**. Nếu mục tiêu là tìm số lớn nhất thông thường, dùng `max(Comparator.naturalOrder())` hoặc `IntStream.max()`.

### 10.8. Dùng natural order như quy tắc locale

`String.compareTo` không có hợp đồng sắp tiếng Việt theo bảng chữ cái. Nếu sản phẩm cần sắp chuỗi theo ngôn ngữ cụ thể, dùng `Collator` được cấu hình đúng locale và kiểm thử những chuỗi có dấu/case khác nhau.

## 11. Tự luyện và kiểm tra

1. **Dãy `[5,1,4]`:** `naturalOrder` cho gì? **Đáp án:** `[1,4,5]`; `reverseOrder` cho `[5,4,1]`.
2. **Một comparator theo tuổi tăng:** gọi `reversed()` tạo thứ tự gì? **Đáp án:** tuổi giảm; không cần lớp Person triển khai `Comparable`.
3. **`byAge.reversed().thenComparing(name)` khác `byAge.thenComparing(name).reversed()` như thế nào?** **Đáp án:** cả hai tuổi giảm; biểu thức đầu tên tăng khi trùng tuổi, biểu thức sau tên giảm.
4. **`Comparator.nullsLast(Comparator.naturalOrder()).reversed()` đặt null ở đâu?** **Đáp án:** lên đầu, vì đảo cả comparator đã xử lý null.
5. **Có thể dùng `Comparator.reverseOrder()` trực tiếp cho lớp custom không triển khai `Comparable` không?** **Đáp án:** không; tạo comparator từ thuộc tính rồi `reversed`.
6. **Vì sao `TreeSet` có thể mất một nhân viên nếu comparator chỉ theo điểm?** **Đáp án:** hai nhân viên cùng điểm có `compare==0`, bị coi là tương đương key/element.
7. **Dùng `Collections.reverse` có sắp được `[3,1,2]` thành giảm dần không?** **Đáp án:** không; kết quả là `[2,1,3]`.
8. **Vì sao không dùng `(a,b)->b-a`?** **Đáp án:** có thể tràn số và vi phạm thứ tự; dùng `Integer.compare(b,a)`.
9. **Với `Stream.max(Comparator.reverseOrder())` trên `[4,1,3]`, kết quả là gì?** **Đáp án:** `1`.
10. **Một kiểu có `compareTo` nhưng không consistent với `equals` có được naturalOrder không?** **Đáp án:** có thể dùng comparator, nhưng các sorted set/map có thể xem hai khóa `equals` khác nhau là tương đương hoặc ngược lại; cần hiểu chính sách dữ liệu.

## 12. Tham khảo API chính thức

Những API này xuất hiện từ Java 8 và tiếp tục được duy trì trong Java hiện đại:

- [`Comparator` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html): `naturalOrder`, `reverseOrder`, `reversed`, `thenComparing`, `nullsFirst`, `nullsLast`, hợp đồng so sánh và tính nhất quán với `equals`.
- [`Comparable` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Comparable.html): thứ tự tự nhiên do chính kiểu định nghĩa.
- [`List.sort` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): sort tại chỗ, ổn định.
- [`Stream.sorted` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): sort theo comparator trên Stream, quy tắc ổn định theo encounter order.
- [`TreeSet` và `TreeMap` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html): cấu trúc tập/map được sắp theo comparator, trùng khóa theo `compare==0`.
- [`Collator` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Collator.html): so sánh chuỗi theo locale khi cần.
