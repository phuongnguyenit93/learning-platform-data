# Sắp xếp nhiều tiêu chí bằng Comparator

> **Chương:** Thứ tự, loại trùng và cắt lát  
> **Module:** JAVA_STREAM_API  
> **Mục tiêu:** Xây dựng bộ so sánh nhiều cấp với `Comparator`, áp dụng cho `Stream.sorted(...)`, kiểm soát thứ tự tăng/giảm, xử lý trường hợp bằng nhau và kết hợp an toàn với `distinct`, `skip`, `limit`.

Khi xử lý dữ liệu bằng **Java Stream API**, yêu cầu sắp xếp hiếm khi chỉ là “theo tên tăng dần”. Danh sách ứng viên có thể cần **điểm cao trước**, nếu bằng điểm thì **phòng ban theo bảng chữ cái**, nếu vẫn bằng thì **thời điểm đăng ký sớm trước**, cuối cùng **mã định danh** để thứ tự ổn định. Với đơn hàng, ta có thể ưu tiên trạng thái, tổng tiền rồi ngày tạo. Những yêu cầu này chính là **sắp xếp nhiều tiêu chí** (*multi-criteria sorting*).

Trong pipeline khai báo của module **JAVA_STREAM_API**, `sorted(comparator)` là phép toán trung gian có trạng thái. Để dùng nó đúng, phải hiểu hợp đồng của `Comparator`, thứ tự gặp phần tử (*encounter order*), hành vi lazy và ảnh hưởng tới hiệu năng, nhất là khi kết hợp lọc, phân trang, thu thập kết quả hoặc xử lý song song. Các kỹ năng này cũng cần thiết khi làm việc với grouping, collector tùy chỉnh, `Spliterator` và các phép biến đổi Stream nâng cao.

## 1. Từ yêu cầu nghiệp vụ đến chuỗi tiêu chí

Giả sử có năm hồ sơ cần xếp hạng:

| Mã hồ sơ | Tên | Điểm | Nhóm | Thứ tự đăng ký |
| --- | --- | ---: | --- | ---: |
| U04 | An | 90 | Backend | 100 |
| U02 | Bình | 95 | Mobile | 103 |
| U03 | Chi | 95 | Backend | 101 |
| U01 | Dung | 95 | Backend | 101 |
| U05 | Em | 95 | Mobile | 101 |

Quy tắc sắp xếp:

1. **Điểm giảm dần**: điểm cao đứng trước.
2. **Nhóm tăng dần** theo thứ tự từ điển: Backend trước Mobile.
3. **Thứ tự đăng ký tăng dần**: đăng ký trước đứng trước.
4. **Mã hồ sơ tăng dần** để loại bỏ tình huống nhiều phần tử có cùng ba khóa đầu.

Kết quả mong đợi:

```text
U01  Dung  95  Backend  101
U03  Chi   95  Backend  101
U05  Em    95  Mobile   101
U02  Bình  95  Mobile   103
U04  An    90  Backend  100
```

Ta có thể hình dung cách quyết định thứ tự giữa hai hồ sơ:

```text
So điểm:
  khác nhau? -> quyết định (điểm lớn hơn đứng trước)
       |
      bằng
       v
So nhóm:
  khác nhau? -> quyết định (nhóm A-Z)
       |
      bằng
       v
So thứ tự đăng ký:
  khác nhau? -> quyết định (số nhỏ hơn trước)
       |
      bằng
       v
So mã:
  khác nhau? -> quyết định (mã A-Z)
       |
      bằng
       v
Hai hồ sơ tương đương theo tất cả khóa sắp xếp
```

**Nguyên tắc:** tiêu chí đứng trước có độ ưu tiên cao hơn. Tiêu chí tiếp theo **chỉ được xét khi kết quả so sánh trước đó bằng 0**.

## 2. Comparator hoạt động như thế nào?

`Comparator<T>` là một functional interface trong `java.util`, có phương thức:

```java
int compare(T left, T right);
```

Ý nghĩa dấu của kết quả:

| `compare(a, b)` | Quan hệ sắp xếp |
| --- | --- |
| Âm (`< 0`) | `a` đứng trước `b`. |
| Bằng `0` | `a` và `b` tương đương **theo tiêu chí so sánh**. |
| Dương (`> 0`) | `a` đứng sau `b`. |

Giá trị trả về **không bắt buộc** là `-1`, `0` hoặc `1`; Java chỉ dùng dấu của nó.

Ví dụ:

```java
import java.util.Comparator;

Comparator<Integer> ascending = Integer::compare;
Comparator<Integer> descending = (a, b) -> Integer.compare(b, a);

System.out.println(ascending.compare(2, 9) < 0);  // true
System.out.println(descending.compare(2, 9) > 0); // true
```

Một bộ so sánh hợp lệ phải tuân thủ các thuộc tính quan trọng:

- **Đảo dấu hợp lý:** dấu của `compare(a,b)` là dấu đối nghịch với `compare(b,a)`.
- **Tính bắc cầu (transitivity):** nếu `a` trước `b` và `b` trước `c` thì `a` phải trước `c`.
- **Tính nhất quán khi bằng nhau theo Comparator:** nếu `compare(a,b) == 0`, kết quả so sánh `a` và `b` với cùng `c` phải có dấu giống nhau.
- Các khóa dùng để so sánh cần giữ ổn định trong quá trình sắp xếp; không thay đổi chúng giữa các lần gọi `compare`.

Vi phạm hợp đồng có thể khiến thuật toán sắp xếp trả kết quả không đáng tin cậy hoặc ném `IllegalArgumentException` trong một số trường hợp.

### 2.1. Comparator và Comparable khác nhau

- `Comparable<T>` định nghĩa **thứ tự tự nhiên** của một kiểu qua `compareTo`, ví dụ `String`, `Integer` và `LocalDate`.
- `Comparator<T>` là **thứ tự được cung cấp từ bên ngoài**, có thể tùy biến theo yêu cầu và kết hợp nhiều tiêu chí mà không sửa lớp dữ liệu.

`Stream.sorted()` không có tham số dùng thứ tự tự nhiên; phần tử phải so sánh được với nhau. `Stream.sorted(comparator)` dùng bộ so sánh đã truyền.

```java
List<String> names = List.of("Chi", "An", "Bình");

List<String> natural = names.stream()
    .sorted()
    .toList(); // [An, Bình, Chi]

List<String> byLength = names.stream()
    .sorted(Comparator.comparingInt(String::length))
    .toList(); // [An, Chi, Bình]
```

Nếu phần tử không có `Comparable` thích hợp, dùng `sorted()` có thể gây `ClassCastException` khi pipeline thực thi. Với các record hoặc đối tượng nghiệp vụ, nên truyền một `Comparator` rõ ràng.

## 3. Tạo tiêu chí đầu tiên với comparing

`Comparator` cung cấp các factory method và cách kết hợp để mô tả sắp xếp trực tiếp:

| Phương thức | Ý nghĩa |
| --- | --- |
| `Comparator.comparing(keyExtractor)` | So sánh theo khóa trích ra, dùng thứ tự tự nhiên của khóa. |
| `Comparator.comparing(keyExtractor, keyComparator)` | So sánh khóa theo Comparator được chỉ định. |
| `Comparator.comparingInt(...)` | So sánh khóa kiểu `int` mà không cần boxing trong quá trình trích khóa. |
| `Comparator.comparingLong(...)` | So sánh khóa kiểu `long`. |
| `Comparator.comparingDouble(...)` | So sánh khóa kiểu `double`. |
| `Comparator.naturalOrder()` | Thứ tự tự nhiên. |
| `Comparator.reverseOrder()` | Đảo thứ tự tự nhiên. |

Dùng record minh họa (Java 16+):

```java
record Candidate(
    String id,
    String name,
    int score,
    String team,
    long registeredOrder
) {}
```

Sắp xếp theo điểm tăng dần:

```java
Comparator<Candidate> byScoreAsc =
    Comparator.comparingInt(Candidate::score);
```

Sắp xếp điểm giảm dần:

```java
Comparator<Candidate> byScoreDesc =
    Comparator.comparingInt(Candidate::score).reversed();
```

Sắp xếp tên:

```java
Comparator<Candidate> byName =
    Comparator.comparing(Candidate::name);
```

Đối với kiểu nguyên thủy, ưu tiên `comparingInt`, `comparingLong` hoặc `comparingDouble` khi phù hợp. Cách này làm rõ loại khóa và tránh tạo wrapper chỉ để so sánh.

### 3.1. Tránh phép trừ trong compare

Không viết bộ so sánh số nguyên bằng cách lấy hiệu một cách tùy tiện:

```java
Comparator<Integer> unsafe = (a, b) -> a - b;
```

Ví dụ với `a = Integer.MAX_VALUE` và `b = -1`, phép trừ vượt giới hạn `int` có thể làm sai dấu. Điều đó phá hỏng ý nghĩa thứ tự.

Dùng:

```java
Comparator<Integer> safe = Integer::compare;

// Hoặc cho Candidate:
Comparator<Candidate> byScore =
    Comparator.comparingInt(Candidate::score);
```

Tương tự với `long`, dùng `Long.compare` hoặc `comparingLong`.

## 4. Ghép nhiều tiêu chí bằng thenComparing

Đây là kỹ thuật chính của bài học. `thenComparing` nhận một Comparator thứ cấp; nó chỉ được sử dụng nếu Comparator trước đó trả về `0`.

### 4.1. Ví dụ đủ bốn cấp

```java
Comparator<Candidate> ranking = Comparator
    .comparingInt(Candidate::score)
    .reversed()
    .thenComparing(Candidate::team)
    .thenComparingLong(Candidate::registeredOrder)
    .thenComparing(Candidate::id);
```

Đọc từ trên xuống:

- `comparingInt(Candidate::score).reversed()`: điểm cao trước.
- `thenComparing(Candidate::team)`: khi đồng điểm, nhóm theo thứ tự tự nhiên.
- `thenComparingLong(Candidate::registeredOrder)`: khi cùng điểm và nhóm, hồ sơ sớm trước.
- `thenComparing(Candidate::id)`: khóa cuối cùng giúp thứ tự có tính xác định nếu mã là duy nhất.

Áp dụng:

```java
List<Candidate> sorted = candidates.stream()
    .sorted(ranking)
    .toList();
```

`sorted(ranking)` là một **phép toán trung gian**. Đến `toList()`, Stream mới được đánh giá và trả danh sách theo thứ tự mới. `candidates` không bị sắp xếp tại chỗ.

### 4.2. thenComparing có những overload nào?

| Dạng | Mục đích |
| --- | --- |
| `thenComparing(Comparator<? super T>)` | Ghép Comparator thứ cấp đã có. |
| `thenComparing(keyExtractor)` | Sắp xếp theo khóa kiểu object với thứ tự tự nhiên. |
| `thenComparing(keyExtractor, keyComparator)` | Sắp xếp theo khóa kiểu object với Comparator riêng. |
| `thenComparingInt(keyExtractor)` | So sánh khóa `int` thứ cấp. |
| `thenComparingLong(keyExtractor)` | So sánh khóa `long` thứ cấp. |
| `thenComparingDouble(keyExtractor)` | So sánh khóa `double` thứ cấp. |

Ví dụ tái sử dụng các Comparator có tên:

```java
Comparator<Candidate> byTeam =
    Comparator.comparing(Candidate::team);

Comparator<Candidate> byTime =
    Comparator.comparingLong(Candidate::registeredOrder);

Comparator<Candidate> byId =
    Comparator.comparing(Candidate::id);

Comparator<Candidate> ranking = Comparator
    .comparingInt(Candidate::score).reversed()
    .thenComparing(byTeam)
    .thenComparing(byTime)
    .thenComparing(byId);
```

Cách tách biến hữu ích nếu một tiêu chí có logic phức tạp, cần tái sử dụng hoặc kiểm thử riêng.

## 5. Đảo chiều từng tiêu chí: lỗi reversed() rất dễ gặp

`Comparator.reversed()` đảo **toàn bộ Comparator hiện tại**, không chỉ bước so sánh viết sát cạnh nó trong chuỗi logic.

Giả sử muốn **điểm giảm dần**, nhưng **tên tăng dần**.

**Đúng:**

```java
Comparator<Candidate> correct = Comparator
    .comparingInt(Candidate::score)
    .reversed()                        // Chỉ đảo comparator theo điểm.
    .thenComparing(Candidate::name);   // Tên vẫn tăng dần.
```

**Sai nếu mục tiêu chỉ là đảo điểm:**

```java
Comparator<Candidate> wrong = Comparator
    .comparingInt(Candidate::score)
    .thenComparing(Candidate::name)
    .reversed(); // Đảo cả điểm VÀ tên.
```

Khi muốn đảo **riêng tiêu chí thứ hai**, tạo Comparator phụ rồi đảo nó:

```java
Comparator<Candidate> scoreAscNameDesc = Comparator
    .comparingInt(Candidate::score)
    .thenComparing(
        Comparator.comparing(Candidate::name).reversed()
    );
```

Hoặc cung cấp Comparator dành riêng cho khóa:

```java
Comparator<Candidate> scoreAscNameDesc2 = Comparator
    .comparingInt(Candidate::score)
    .thenComparing(
        Candidate::name,
        Comparator.reverseOrder()
    );
```

Hai cách trên đều sắp theo **điểm tăng dần, tên giảm dần**.

### 5.1. Khi cả hai tiêu chí đều giảm dần

```java
Comparator<Candidate> scoreDescNameDesc = Comparator
    .comparingInt(Candidate::score)
    .reversed()
    .thenComparing(
        Comparator.comparing(Candidate::name).reversed()
    );
```

Việc viết rõ hướng cho từng cấp giúp ngăn thay đổi ngoài ý muốn khi yêu cầu nghiệp vụ được sửa sau này.

### 5.2. Comparator cho ngày và thời gian

`LocalDate`, `Instant` và nhiều kiểu `java.time` có thứ tự tự nhiên. Ví dụ ưu tiên hạn xử lý gần nhất:

```java
record Task(String id, int priority, java.time.LocalDate dueDate) {}

Comparator<Task> byPriorityDescDueAsc = Comparator
    .comparingInt(Task::priority)
    .reversed()
    .thenComparing(Task::dueDate)
    .thenComparing(Task::id);
```

Nếu ngày muộn nhất cần đứng trước:

```java
Comparator<Task> byPriorityDescDueDesc = Comparator
    .comparingInt(Task::priority)
    .reversed()
    .thenComparing(
        Task::dueDate,
        Comparator.reverseOrder()
    )
    .thenComparing(Task::id);
```

Tư duy nhất quán: mỗi cấp có một **khóa** và một **hướng**. Không phụ thuộc vào cảm giác của tên `reversed` ở cuối chuỗi.

## 6. Một ví dụ Java chạy độc lập

Ví dụ sau dùng Java 17+, kết hợp đúng bốn tiêu chí nêu đầu bài. Lưu vào `MultiCriteriaSortDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class MultiCriteriaSortDemo {
    record Candidate(
        String id,
        String name,
        int score,
        String team,
        long registeredOrder
    ) {}

    public static void main(String[] args) {
        List<Candidate> candidates = List.of(
            new Candidate("U04", "An", 90, "Backend", 100),
            new Candidate("U02", "Bình", 95, "Mobile", 103),
            new Candidate("U03", "Chi", 95, "Backend", 101),
            new Candidate("U01", "Dung", 95, "Backend", 101),
            new Candidate("U05", "Em", 95, "Mobile", 101)
        );

        Comparator<Candidate> ranking = Comparator
            .comparingInt(Candidate::score).reversed()
            .thenComparing(Candidate::team)
            .thenComparingLong(Candidate::registeredOrder)
            .thenComparing(Candidate::id);

        List<Candidate> ranked = candidates.stream()
            .filter(candidate -> candidate.score() >= 90)
            .sorted(ranking)
            .toList();

        ranked.forEach(candidate -> System.out.printf(
            "%s | %-4s | %d | %-7s | %d%n",
            candidate.id(),
            candidate.name(),
            candidate.score(),
            candidate.team(),
            candidate.registeredOrder()
        ));
    }
}
```

Kết quả:

```text
U01 | Dung  | 95 | Backend | 101
U03 | Chi  | 95 | Backend | 101
U05 | Em   | 95 | Mobile  | 101
U02 | Bình | 95 | Mobile  | 103
U04 | An   | 90 | Backend | 100
```

Vì các mã hồ sơ duy nhất, tiêu chí cuối cùng phân biệt được mọi cặp hồ sơ. Đây là một cách thực tế để bảo đảm thứ tự nhất quán giữa những lần xử lý cùng một bộ dữ liệu, đặc biệt khi phân trang.

Nếu chỉ muốn lấy mã hồ sơ sau sắp xếp:

```java
List<String> rankedIds = candidates.stream()
    .sorted(ranking)
    .map(Candidate::id)
    .toList();

// [U01, U03, U05, U02, U04]
```

Trong trường hợp tổng quát, hãy đặt `sorted` trước `map` nếu ánh xạ bỏ đi thông tin cần dùng để sắp xếp. Nếu ánh xạ thành một đối tượng vẫn giữ đủ khóa và đáp ứng cùng quy tắc, có thể thiết kế thứ tự khác; điều quan trọng là đảm bảo tính tương đương về ngữ nghĩa.

## 7. Xử lý null ở khóa sắp xếp và ở chính phần tử

### 7.1. Khóa có thể null

`Comparator.comparing(Candidate::team)` mặc định sử dụng thứ tự tự nhiên của `String` và sẽ không xử lý được khóa `null` khi cần so sánh nó với khóa khác.

Nếu yêu cầu là “nhóm chưa biết xếp cuối”, viết:

```java
Comparator<Candidate> byNullableTeam = Comparator.comparing(
    Candidate::team,
    Comparator.nullsLast(Comparator.naturalOrder())
);
```

Nếu “nhóm chưa biết xếp đầu”:

```java
Comparator<Candidate> byNullableTeamFirst = Comparator.comparing(
    Candidate::team,
    Comparator.nullsFirst(Comparator.naturalOrder())
);
```

Có thể ghép vào chuỗi:

```java
Comparator<Candidate> rankingWithNullTeam = Comparator
    .comparingInt(Candidate::score).reversed()
    .thenComparing(
        Candidate::team,
        Comparator.nullsLast(Comparator.naturalOrder())
    )
    .thenComparing(Candidate::id);
```

`nullsLast(...)` ở đây áp dụng cho **giá trị khóa `team`**, không phải toàn bộ `Candidate`.

### 7.2. Toàn bộ phần tử có thể null

Nếu Stream có phần tử `null` (ví dụ một nguồn cho phép điều đó), cần bọc comparator dùng cho cả phần tử:

```java
Comparator<Candidate> nonNullComparator =
    Comparator.comparing(Candidate::name);

Comparator<Candidate> wholeElementComparator =
    Comparator.nullsLast(nonNullComparator);

List<Candidate> sorted = candidatesWithNulls.stream()
    .sorted(wholeElementComparator)
    .toList();
```

`candidatesWithNulls` là danh sách minh họa cần có trong chương trình sử dụng đoạn mã này.

Hai tình huống khác nhau:

- `Candidate` tồn tại nhưng `candidate.team() == null`: xử lý **khóa null**.
- Bản thân phần tử `Candidate` là `null`: xử lý **phần tử null**.

Không dùng `nullsLast` ở lớp ngoài rồi kỳ vọng nó tự xử lý khóa có thể null bên trong đối tượng.

### 7.3. Đảo chiều và vị trí null

`Comparator.nullsLast(Comparator.reverseOrder())` có nghĩa **giá trị khác null giảm dần, null vẫn ở cuối**. Nhưng gọi `reversed()` trên **toàn bộ** Comparator có `nullsLast` sẽ đảo cả vị trí null thành đầu.

Ví dụ:

```java
Comparator<String> descendingButNullLast =
    Comparator.nullsLast(Comparator.reverseOrder());
```

Chọn chính sách null theo nghiệp vụ, sau đó mới chọn hướng sắp xếp cho giá trị khác null.

## 8. Comparator bằng 0, stability và thứ tự gặp phần tử

Hai phần tử được coi là **bằng nhau theo Comparator** nếu `compare(a,b) == 0`. Điều đó **không có nghĩa** `a.equals(b)` là `true`.

Ví dụ chỉ sắp xếp theo điểm:

```java
Comparator<Candidate> byScoreOnly =
    Comparator.comparingInt(Candidate::score);
```

Hai hồ sơ `U01` và `U03` đều có điểm 95, vì vậy `byScoreOnly.compare(u01, u03) == 0`, dù mã, tên và đối tượng khác nhau.

### 8.1. sorted có ổn định không?

Theo hợp đồng `Stream.sorted(...)`:

- Với Stream **có thứ tự gặp phần tử** (*ordered stream*), việc sắp xếp **ổn định** (*stable*): các phần tử bằng nhau theo Comparator vẫn giữ thứ tự tương đối như ở nguồn.
- Với Stream **không có thứ tự gặp phần tử** (*unordered stream*), **không có bảo đảm ổn định** cho các phần tử có khóa bằng nhau.

Ví dụ:

```java
record Item(String id, int score) {}

List<Item> items = List.of(
    new Item("A", 5),
    new Item("B", 2),
    new Item("C", 5)
);

List<String> ids = items.stream()
    .sorted(Comparator.comparingInt(Item::score))
    .map(Item::id)
    .toList();

// [B, A, C] — A và C bằng điểm, giữ thứ tự tương đối từ List.
```

Nếu lấy phần tử từ một nguồn không bảo đảm thứ tự, chẳng hạn một `HashSet`, đừng dựa vào vị trí gốc để quyết định ai đứng trước khi bằng khóa.

### 8.2. Thêm tie-breaker để kết quả có tính xác định

Thêm khóa thứ cấp:

```java
Comparator<Item> byScoreThenId = Comparator
    .comparingInt(Item::score)
    .thenComparing(Item::id);
```

Với mã `id` duy nhất và bất biến trong quá trình sắp xếp, các cặp phần tử khác nhau sẽ được phân biệt. Khi đó việc xếp hạng không phụ thuộc vào thứ tự nguồn giữa các khóa bằng nhau.

Đặc biệt quan trọng với kết quả hiển thị cho người dùng, thống kê cần tái lập và phân trang. Nếu mã không duy nhất, cần một khóa cuối cùng có khả năng phân biệt các bản ghi theo yêu cầu nghiệp vụ.

### 8.3. Comparator khác distinct và equals

`Stream.distinct()` loại trùng dựa trên `Object.equals`, **không sử dụng Comparator truyền cho `sorted`**.

```java
record Entry(String id, int score) {}

List<Entry> entries = List.of(
    new Entry("A", 5),
    new Entry("B", 5)
);

List<Entry> result = entries.stream()
    .sorted(Comparator.comparingInt(Entry::score))
    .distinct()
    .toList();

// Giữ cả A và B: hai record khác nhau theo equals.
```

Một `TreeSet` hoặc `TreeMap` lại dùng Comparator (hoặc thứ tự tự nhiên) để quyết định tính tương đương của khóa; nếu Comparator trả về 0 cho hai khóa khác nhau theo `equals`, cấu trúc này có thể xem chúng là cùng một khóa. Vì thế, **không thay thế `distinct()` bằng `collect(toCollection(() -> new TreeSet<>(byScoreOnly)))`** nếu mục tiêu là giữ các bản ghi khác mã nhưng đồng điểm.

## 9. Sắp xếp chuỗi: phân biệt chữ hoa, chuẩn hóa và ngôn ngữ

`Comparator.comparing(Candidate::name)` dựa trên `String.compareTo`, so sánh thứ tự mã UTF-16. Đó không phải lúc nào cũng là thứ tự tên hiển thị tự nhiên theo tiếng Việt.

### 9.1. So sánh không phân biệt hoa thường

```java
Comparator<Candidate> byNameIgnoringCase = Comparator.comparing(
    Candidate::name,
    String.CASE_INSENSITIVE_ORDER
);
```

Nếu các tên chỉ khác kiểu chữ (chẳng hạn `"an"` và `"An"`), Comparator này có thể trả 0. Khi cần thứ tự nhất quán cho cả hai:

```java
Comparator<Candidate> byNameIgnoringCaseThenId = Comparator
    .comparing(Candidate::name, String.CASE_INSENSITIVE_ORDER)
    .thenComparing(Candidate::id);
```

### 9.2. So sánh theo ngôn ngữ

Để xếp tên theo quy tắc ngôn ngữ địa phương, có thể cân nhắc `java.text.Collator`:

```java
import java.text.Collator;
import java.util.Comparator;
import java.util.Locale;

Collator viCollator = Collator.getInstance(
    Locale.forLanguageTag("vi-VN")
);

Comparator<Candidate> byVietnameseName = Comparator.comparing(
    Candidate::name,
    viCollator
);
```

`Collator` cung cấp quy tắc so sánh tùy locale và có thể tùy chỉnh mức độ phân biệt chữ. Kết quả cụ thể phụ thuộc cấu hình, dữ liệu và môi trường. Với pipeline song song, cần lưu ý `Collator` là đối tượng có trạng thái cấu hình; đừng chia sẻ một instance đang bị thay đổi giữa các luồng.

Một quy tắc chuẩn hóa (trim, chuyển hoa/thường, chuẩn hóa Unicode) cần phù hợp nghiệp vụ. **Không tùy ý bỏ dấu tiếng Việt** nếu hệ thống cần phân biệt những tên khác nhau.

## 10. Kết hợp sorted với filter, skip và limit

Pipeline phổ biến cho danh sách tìm kiếm:

```java
List<Candidate> page = candidates.stream()
    .filter(c -> c.score() >= 90)
    .sorted(ranking)
    .skip(2)
    .limit(2)
    .toList();
```

Đọc theo thứ tự logic:

1. `filter` chọn tập bản ghi hợp lệ.
2. `sorted` thiết lập thứ tự xếp hạng nhiều tiêu chí.
3. `skip(2)` bỏ qua hai bản ghi đầu **theo thứ tự đã sắp**.
4. `limit(2)` lấy tối đa hai bản ghi tiếp theo.
5. `toList()` đánh giá và trả kết quả.

Với bộ dữ liệu của mục 6, `page` chứa `U05` rồi `U02`.

### 10.1. Đổi chỗ sorted và limit có thể đổi kết quả

```java
// Lấy hai hồ sơ đầu của nguồn, sau đó mới sắp xếp:
List<Candidate> firstTwoSorted = candidates.stream()
    .limit(2)
    .sorted(ranking)
    .toList();
```

Kết quả chỉ được chọn từ hai phần tử đầu nguồn (`U04` và `U02`); hồ sơ `U01` có thứ hạng cao nhất không thể xuất hiện.

Ngược lại:

```java
// Xếp hạng toàn bộ rồi lấy hai hồ sơ tốt nhất:
List<Candidate> topTwo = candidates.stream()
    .sorted(ranking)
    .limit(2)
    .toList();

// [U01, U03] theo thứ tự mã hồ sơ.
```

Nếu yêu cầu là **top N toàn bộ dữ liệu**, phải sắp theo tiêu chí trước rồi cắt lát, hoặc sử dụng thuật toán top-K chuyên dụng bảo toàn đúng kết quả.

### 10.2. Phân trang ổn định cần khóa cuối cùng

Nếu nhiều bản ghi có cùng điểm, nhóm và ngày đăng ký mà nguồn không có thứ tự ổn định, phân trang bằng `skip` và `limit` có thể phân bố những bản ghi đồng hạng vào các trang khác nhau qua các lần truy vấn. Thêm tiêu chí khóa duy nhất vào Comparator giúp quyết định thứ tự giữa chúng.

Tuy nhiên, **Comparator đầy đủ không thể bảo đảm phân trang nhất quán khi tập dữ liệu thay đổi giữa các lần tải trang**. Với hệ thống cập nhật liên tục, cần chiến lược phù hợp như snapshot hoặc phân trang dựa trên khóa (*keyset pagination*) ở nguồn dữ liệu.

## 11. Hiệu năng: sorted là phép toán có trạng thái

`filter` và `map` thường có thể xử lý từng phần tử khi cần. `sorted` là phép toán **stateful**: muốn biết phần tử đầu tiên theo thứ tự sắp xếp toàn cục, nó thông thường phải xem toàn bộ đầu vào hữu hạn và giữ dữ liệu cần thiết để sắp xếp.

Giả sử:

```java
long count = candidates.stream()
    .filter(c -> c.score() >= 90)
    .sorted(ranking)
    .count();
```

Vì chỉ cần đếm và việc sắp xếp không làm thay đổi số phần tử, triển khai Stream có thể tối ưu bỏ qua việc thực hiện sắp xếp trong một số trường hợp. **Không dùng tác động phụ trong Comparator như một việc bắt buộc phải xảy ra**.

### 11.1. Chi phí thường gặp

Với `n` phần tử hữu hạn:

- Việc sắp xếp so sánh thông thường có chi phí thời gian khoảng `O(n log n)`.
- Sắp xếp trên Stream thường cần bộ đệm `O(n)` để phục vụ thứ tự toàn cục.
- Mỗi lần so sánh có thể trích xuất lại các khóa, đặc biệt khi dùng phương thức tính toán phức tạp.
- Chuỗi `thenComparing` thường giúp tránh tính các khóa phụ với những cặp phần tử đã khác nhau ở khóa chính, nhưng không bảo đảm mỗi khóa chỉ được tính một lần cho một phần tử.

Không có kết luận rằng Stream nhanh hơn hay chậm hơn mọi cách sắp xếp khác: `List.sort(comparator)` có thể phù hợp khi muốn sửa thứ tự chính collection, trong khi `stream().sorted(...).toList()` phù hợp khi cần kết quả mới và kết hợp phép lọc/biến đổi.

### 11.2. Chọn đúng thứ tự các phép toán

Thông thường, lọc trước khi sắp xếp sẽ giảm lượng dữ liệu cần xử lý:

```java
List<Candidate> eligible = candidates.stream()
    .filter(c -> c.score() >= 90)
    .sorted(ranking)
    .toList();
```

Nếu điều kiện lọc không phụ thuộc thứ tự, cách này tương đương về tập kết quả với việc sắp rồi lọc, và thường có thể giảm công sắp xếp. Nhưng không thể tự do đổi chỗ `limit` hoặc `skip` như đã minh họa.

Đặc biệt, trên nguồn có khả năng **vô hạn**, `sorted()` toàn cục thường không thể phát ra kết quả vì không có thời điểm hoàn tất thu thập các phần tử. Cần giới hạn nguồn theo yêu cầu bài toán **trước** khi sắp xếp hoặc dùng một phương án xử lý dòng dữ liệu chuyên biệt.

### 11.3. Khi cần top K trên dữ liệu lớn

`stream().sorted(comparator).limit(k)` rất dễ đọc và phù hợp cho nhiều bài toán dữ liệu vừa. Nếu `n` rất lớn còn `k` nhỏ, cấu trúc như **priority queue kích thước K** có thể giảm độ phức tạp xuống khoảng `O(n log k)` cùng bộ nhớ `O(k)`, miễn là cài đặt đúng tiêu chí và xử lý đồng hạng.

Đó là một lựa chọn thuật toán khác, không đơn thuần là hoán đổi `sorted` và `limit`. Chỉ tối ưu theo hướng này khi kích thước dữ liệu và phép đo hiệu năng cho thấy cần thiết.

## 12. Sắp xếp song song và thứ tự gặp phần tử

`sorted(comparator)` hoạt động với cả Stream tuần tự và song song:

```java
List<Candidate> rankedInParallel = candidates.parallelStream()
    .sorted(ranking)
    .toList();
```

Với `List` là nguồn ordered, thứ tự kết quả vẫn phải tuân thủ Comparator, và các phần tử đồng hạng giữ tính ổn định theo hợp đồng `sorted`. Tuy nhiên:

- Sắp xếp là phép toán có trạng thái; quá trình chia/ghép việc và bộ đệm có chi phí.
- Comparator phải **không gây tác động phụ làm thay đổi dữ liệu** và phải nhất quán giữa các lần gọi.
- Comparator có thể được gọi nhiều lần và không có bảo đảm số lần, thứ tự hay luồng thực hiện.
- Với Stream không có thứ tự gặp phần tử, `sorted` không bảo đảm ổn định cho các phần tử mà Comparator xem là bằng nhau.
- `forEach` khi chạy song song không bảo đảm thứ tự in; nếu cần xuất đúng thứ tự gặp phần tử, cân nhắc `forEachOrdered` hoặc thu danh sách bằng `toList()`.

Ví dụ tránh nhầm lẫn:

```java
// Không dựa vào thứ tự được in trong forEach của parallel stream:
candidates.parallelStream()
    .sorted(ranking)
    .forEach(c -> System.out.println(c.id()));

// Thu kết quả rồi duyệt theo List để bảo toàn thứ tự:
List<Candidate> ranked = candidates.parallelStream()
    .sorted(ranking)
    .toList();

ranked.forEach(c -> System.out.println(c.id()));
```

Thực thi song song **không tự bảo đảm tăng tốc**. Cần xét kích thước dữ liệu, chi phí so sánh, đặc tính `Spliterator`, băng thông bộ nhớ, số lõi và tải thực tế.

## 13. Cách kiểm tra một Comparator nhiều cấp

Với một bộ so sánh xếp hạng, nên tự kiểm tra ba trường hợp: **khác khóa chính**, **bằng khóa chính nhưng khác khóa phụ**, và **bằng mọi khóa ngoại trừ khóa cuối**.

Ví dụ có thể đặt cùng `record Candidate` và `Comparator<Candidate> ranking` của mục 6:

```java
Candidate a = new Candidate("U10", "A", 95, "Backend", 101);
Candidate b = new Candidate("U11", "B", 90, "Backend", 101);
Candidate c = new Candidate("U12", "C", 95, "Mobile", 101);
Candidate d = new Candidate("U13", "D", 95, "Backend", 102);
Candidate e = new Candidate("U14", "E", 95, "Backend", 101);

assert ranking.compare(a, b) < 0; // Điểm cao trước.
assert ranking.compare(a, c) < 0; // Cùng điểm, Backend trước Mobile.
assert ranking.compare(a, d) < 0; // Cùng điểm/nhóm, đăng ký sớm trước.
assert ranking.compare(a, e) < 0; // Các khóa trước bằng, id nhỏ hơn trước.
```

Trong Java, `assert` bị tắt theo mặc định; chạy chương trình với `-ea` nếu muốn các điều kiện `assert` được kiểm tra. Trong kiểm thử tự động thực tế, có thể dùng assertion của framework kiểm thử.

Ngoài ra, với logic Comparator tự viết, cần kiểm tra tính bắc cầu và các trường hợp biên: số âm, giá trị lớn, khóa `null`, chuỗi khác hoa/thường, nguồn không có thứ tự. Một Comparator ghép bằng factory methods chuẩn thường dễ đọc và ít lỗi hơn thuật toán so sánh nhiều nhánh viết tay.

## 14. Những lỗi thường gặp

| Lỗi | Vì sao sai hoặc rủi ro | Hướng sửa |
| --- | --- | --- |
| Dùng `(a,b) -> a.score() - b.score()` | Có thể tràn số nguyên. | `comparingInt(Candidate::score)` hoặc `Integer.compare`. |
| Viết `.thenComparing(...).reversed()` khi chỉ muốn đảo khóa chính | Đảo toàn bộ chuỗi đã tạo. | Gọi `reversed()` trước `thenComparing` hoặc đảo riêng Comparator phụ. |
| Chỉ sắp theo điểm khi cần phân trang ổn định | Nhiều bản ghi bằng điểm có thứ tự chưa được quyết định nếu nguồn unordered. | Thêm khóa cuối xác định như mã duy nhất. |
| Dùng `limit(k).sorted(...)` để lấy top K toàn bộ nguồn | Đã bỏ các phần tử đứng sau `k` phần tử nguồn. | `sorted(...).limit(k)` hoặc thuật toán top-K chuyên dụng. |
| Nghĩ `distinct()` dùng Comparator của `sorted` | `distinct` dựa trên `equals`. | Tách yêu cầu loại trùng khỏi yêu cầu sắp xếp. |
| Dùng `TreeSet` với Comparator chỉ theo điểm | Những phần tử khác nhau có điểm bằng nhau có thể bị xem như trùng. | Dùng Comparator đầy đủ theo định danh hoặc chọn cấu trúc phù hợp. |
| Không xử lý khóa nullable | Có thể ném `NullPointerException`. | `nullsFirst` / `nullsLast` ở đúng lớp khóa. |
| Viết Comparator phụ thuộc biến thay đổi trong lúc sắp | Quan hệ thứ tự không nhất quán. | Giữ khóa và quy tắc so sánh ổn định. |
| Ghi log hoặc đếm trong `compare` rồi dựa vào số lần gọi | Số lần/đường thực thi do thuật toán quyết định và có thể được tối ưu. | Tách logic nghiệp vụ khỏi Comparator. |
| Nghĩ `parallelStream().sorted(...)` luôn nhanh hơn | Chi phí chia/ghép và lưu trữ có thể lớn hơn lợi ích. | Đo hiệu năng bằng dữ liệu thực. |
| Sắp xếp nguồn vô hạn bằng `sorted()` rồi `limit()` | `sorted()` cần biết thứ tự toàn cục trước khi có thể phát phần tử. | Giới hạn phần tử đầu vào hoặc thay thuật toán. |

## 15. Bài tập tự thực hành

**Bài 1 – Xếp hạng nhân viên.** Có `Employee(String id, String department, int performance, long joinedAt)`. Sắp theo hiệu suất giảm dần, phòng ban tăng dần, ngày gia nhập tăng dần, mã tăng dần. Hãy tạo Comparator bằng `comparingInt` và các overload `thenComparing`.

**Bài 2 – Điều khiển chiều thứ cấp.** Từ comparator của Bài 1, thay quy tắc phòng ban thành **giảm dần** nhưng giữ hiệu suất giảm dần và các tiêu chí khác tăng dần. Xác định tại sao đặt `reversed()` ở cuối toàn bộ chuỗi không đúng.

**Bài 3 – Dữ liệu khuyết thiếu.** Với `Ticket(String id, Integer severity, String owner)`, `owner` có thể `null`. Sắp theo `severity` giảm dần, rồi `owner` tăng dần nhưng `null` ở cuối, cuối cùng theo `id`. Xử lý thêm tình huống `severity` cũng có thể `null` nếu yêu cầu.

**Bài 4 – Lấy top N.** Từ 10.000 bản ghi, lọc trạng thái hợp lệ, lấy 5 bản ghi có điểm cao nhất. Viết pipeline đúng và giải thích vì sao `limit(5).sorted(...)` không đạt yêu cầu.

**Bài 5 – Comparator và trùng lặp.** Tạo hai record khác nhau cùng điểm rồi so sánh kết quả của `sorted(...).distinct()` với việc thu vào `TreeSet` chỉ so sánh theo điểm. Giải thích vì sao số phần tử có thể khác nhau.

Gợi ý cho Bài 1:

```java
Comparator<Employee> ranking = Comparator
    .comparingInt(Employee::performance).reversed()
    .thenComparing(Employee::department)
    .thenComparingLong(Employee::joinedAt)
    .thenComparing(Employee::id);
```

Đoạn này giả định `Employee` là record được định nghĩa trong bài tập; nếu `department` có thể `null`, bổ sung bộ so sánh cho khóa nullable như mục 7.

## 16. Tóm tắt kiến thức cần nhớ

- **`Comparator<T>` quyết định thứ tự bằng dấu của `compare(a,b)`**. Thứ tự đúng cần nhất quán và có tính bắc cầu.
- **`comparing(...)`, `comparingInt(...)`, `comparingLong(...)`, `comparingDouble(...)`** tạo tiêu chí chính; **`thenComparing(...)`** xây dựng các tiêu chí ưu tiên thấp hơn.
- **`reversed()` đảo toàn bộ Comparator tại vị trí được gọi**; muốn đảo riêng một khóa, hãy đảo Comparator của khóa đó trước khi ghép.
- **`nullsFirst` và `nullsLast`** xử lý giá trị `null`; phân biệt khóa null với cả phần tử null.
- **`Stream.sorted(comparator)` là phép trung gian có trạng thái và lazy**. Với nguồn ordered, sắp xếp ổn định cho các phần tử bằng khóa; với nguồn unordered, không bảo đảm ổn định.
- **`sorted(...).skip(...).limit(...)`** biểu diễn phân trang sau xếp hạng; **`limit(...).sorted(...)`** là bài toán khác. Thêm khóa định danh duy nhất khi cần thứ tự xác định.
- **Comparator không quyết định quy tắc `distinct()`**; phép loại trùng dựa trên `equals`, còn một số cấu trúc sorted set/map dùng Comparator để phân biệt khóa.
- **Chi phí của `sorted` có thể đáng kể**, đặc biệt với dữ liệu lớn, nguồn vô hạn và xử lý song song. Đo đạc và chọn thuật toán theo nhu cầu thực tế.
- Hiểu rõ thứ tự, đặc tính của nguồn `Spliterator`, tính thuần của lambda và hành vi `collect` sẽ giúp sử dụng hiệu quả các kỹ thuật khác trong **JAVA_STREAM_API**, từ grouping đến collector tùy chỉnh và Stream Gatherers.
