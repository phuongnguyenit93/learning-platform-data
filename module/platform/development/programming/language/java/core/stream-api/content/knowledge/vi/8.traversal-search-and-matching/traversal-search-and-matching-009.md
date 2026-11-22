# Chọn phép toán kết thúc theo mục đích và yêu cầu dừng sớm

Trong Java Stream API, các bước trung gian như `filter`, `map` và `sorted` chủ yếu mô tả **cách xử lý** phần tử; **phép toán kết thúc** (*terminal operation*) xác định chương trình cần **loại kết quả nào**. Chọn đúng terminal operation giúp code thể hiện rõ ý định, tránh duyệt dữ liệu không cần thiết và kiểm soát được những trường hợp pipeline có thể dừng sớm.

Bài học thuộc chương **Duyệt, tìm kiếm và đối sánh** của module **JAVA_STREAM_API**. Kiến thức này kết nối mô hình pipeline lười với các phép tổng hợp `reduce`, `collect`, các Collector để grouping, nguồn hữu hạn/vô hạn, xử lý song song và giới hạn hiệu năng. Trọng tâm là câu hỏi thực tế: *Muốn biết có phần tử phù hợp, lấy một phần tử, lấy tất cả, đếm, tính toán hay thực hiện một hành động?* Mỗi mục đích dẫn tới một terminal operation khác nhau.

## 1. Terminal operation quyết định yêu cầu tiêu thụ

Một pipeline thường gồm **source → zero hoặc nhiều intermediate operations → terminal operation**:

```java
List<String> names = Arrays.asList("An", "Binh", "Chi", "Dung");

boolean hasLongName = names.stream()            // Nguồn
    .map(String::trim)                           // Trung gian, lười
    .filter(name -> name.length() >= 4)         // Trung gian, lười
    .anyMatch(name -> name.startsWith("B"));     // Kết thúc: chỉ hỏi có hay không

System.out.println(hasLongName); // true
```

`anyMatch` không cần tạo danh sách những tên thỏa cả hai điều kiện. Một khi tìm thấy `Binh`, terminal đã đủ bằng chứng để trả về `true`. Với pipeline tuần tự, các phần tử còn lại không cần được kiểm tra. Đây là ví dụ của **dừng sớm** (*short-circuiting*).

Phân biệt hai ý:

- **Tính lười:** các phép toán trung gian thường chưa duyệt nguồn khi mới được ghép vào pipeline.
- **Dừng sớm:** sau khi terminal bắt đầu tiêu thụ, một số phép toán có thể trả kết quả **trước khi đọc hết nguồn**.

Không phải terminal nào cũng dừng sớm. `collect(toList())` cần thu thập mọi phần tử còn lại; `sum()` cần cộng mọi giá trị đầu ra của pipeline. Ngược lại, `findFirst`, `findAny` và ba phép `match` có thể kết thúc sau một phần nguồn khi điều kiện phù hợp.

> **Lưu ý về thuật ngữ:** `limit` và `takeWhile` là **phép toán trung gian có khả năng ngắn mạch**; chúng không phải terminal operation. Chúng có thể giúp terminal cần toàn bộ dữ liệu kết thúc trên một nguồn ban đầu rất dài hoặc vô hạn.

## 2. Bảng chọn nhanh theo mục tiêu

| Mục đích | Terminal operation nên chọn | Kiểu kết quả | Có thể dừng sớm? |
| --- | --- | --- | --- |
| Có **ít nhất một** phần tử thỏa điều kiện? | `anyMatch(predicate)` | `boolean` | Có, khi gặp phần tử đúng |
| **Tất cả** phần tử đều thỏa điều kiện? | `allMatch(predicate)` | `boolean` | Có, khi gặp phần tử sai |
| **Không có** phần tử nào thỏa điều kiện? | `noneMatch(predicate)` | `boolean` | Có, khi gặp phần tử đúng |
| Lấy **phần tử đầu tiên** theo thứ tự nguồn? | `findFirst()` | `Optional<T>` | Có, khi xác định được phần tử đầu |
| Chỉ cần **bất kỳ một** phần tử nào? | `findAny()` | `Optional<T>` | Có, khi tìm được một phần tử |
| Cần **toàn bộ** các phần tử sau lọc/biến đổi? | `collect(collector)`; hoặc `toList()` từ Java 16 | Collection hoặc giá trị thu thập | Thông thường phải xem hết đầu ra |
| Cần biết có **bao nhiêu** phần tử? | `count()` | `long` | Có thể tối ưu bằng kích thước đã biết; không phải terminal tìm kiếm ngắn mạch |
| Cần **nhỏ nhất/lớn nhất**? | `min(comparator)` / `max(comparator)` | `Optional<T>` | Thông thường phải xem hết đầu ra |
| Cần **tổng/tích lũy một giá trị**? | `sum()` trên primitive Stream, `reduce(...)` | Số, giá trị hoặc `Optional` | Thông thường phải xem hết đầu ra |
| Cần **gom nhóm, thống kê, cấu trúc đích**? | `collect(Collectors.groupingBy(...))`, `collect(...)` | `Map`, `List`, v.v. | Thông thường phải xem hết đầu ra |
| Cần **thực hiện hành động** trên phần tử? | `forEach(action)` / `forEachOrdered(action)` | `void` | Thông thường phải duyệt hết đầu ra |

**Quy tắc lựa chọn:** Nếu kết quả chỉ cần một **câu trả lời có/không**, hãy ưu tiên `anyMatch`, `allMatch`, `noneMatch` thay vì `filter(...).collect(...).isEmpty()`. Nếu kết quả cần **một phần tử**, ưu tiên `findFirst` hoặc `findAny` thay vì thu cả danh sách để lấy phần tử đầu.

## 3. anyMatch, allMatch và noneMatch: ba câu hỏi logic khác nhau

Các phép toán đối sánh nhận `Predicate<T>` và trả về một `boolean`:

```java
List<Integer> scores = Arrays.asList(45, 68, 82, 91);

boolean hasExcellent = scores.stream()
    .anyMatch(score -> score >= 90); // true: có 91

boolean allPassed = scores.stream()
    .allMatch(score -> score >= 50); // false: có 45

boolean noneNegative = scores.stream()
    .noneMatch(score -> score < 0); // true: không có số âm
```

| Phép toán | Khi nào có thể quyết định ngay? | Nếu duyệt hết mà không gặp điều kiện ngắt |
| --- | --- | --- |
| `anyMatch(p)` | Gặp **một phần tử đúng** → `true` | `false` |
| `allMatch(p)` | Gặp **một phần tử sai** → `false` | `true` |
| `noneMatch(p)` | Gặp **một phần tử đúng** → `false` | `true` |

Với **Stream rỗng**, không có phần tử nào để kiểm tra:

```java
boolean any = Stream.<Integer>empty()
    .anyMatch(n -> n > 0);  // false

boolean all = Stream.<Integer>empty()
    .allMatch(n -> n > 0);  // true

boolean none = Stream.<Integer>empty()
    .noneMatch(n -> n > 0); // true
```

`allMatch` trả về `true` trên Stream rỗng vì **không có phản ví dụ**; `noneMatch` cũng trả về `true` vì không có phần tử thỏa predicate. Đây là quy tắc logic (*vacuous truth*), không phải lỗi.

**Lỗi thường gặp:** dùng `allMatch` để kiểm tra “danh sách không rỗng và tất cả hợp lệ”. Chỉ `allMatch` thì **không kiểm tra được điều kiện không rỗng**. Nếu nguồn là `List`, có thể kết hợp `!list.isEmpty()` và `list.stream().allMatch(...)`; nếu nguồn là Stream dùng một lần, cần một thiết kế xử lý vừa xác định rỗng vừa kiểm tra điều kiện, chẳng hạn thu thập thông tin bằng một collector phù hợp.

## 4. findFirst và findAny: yêu cầu thứ tự quyết định lựa chọn

Cả hai phép toán tìm kiếm đều trả về `Optional<T>`, vì kết quả có thể không tồn tại.

```java
List<String> employees = Arrays.asList("An", "Binh", "Chi", "Duc");

Optional<String> firstMatching = employees.stream()
    .filter(name -> name.length() >= 3)
    .findFirst();
// Optional[Binh]

Optional<String> anyMatching = employees.parallelStream()
    .filter(name -> name.length() >= 3)
    .findAny();
// Có thể là Binh, Chi hoặc Duc; không dựa vào lựa chọn cụ thể.
```

**Chọn `findFirst`** khi yêu cầu là “bản ghi đầu tiên theo một thứ tự có ý nghĩa”: giao dịch sớm nhất, lỗi đầu tiên trong tập đã sắp xếp, bản ghi đầu tiên của một `List`. `findFirst` tuân thủ **encounter order** nếu nguồn có thứ tự.

**Chọn `findAny`** khi chỉ cần **một phần tử bất kỳ** để xử lý tiếp. Nó được phép không giữ thứ tự, nhất là với pipeline song song, nên có thể mang lại lợi ích hiệu năng.

**Không suy ra “đầu tiên” trên nguồn không có encounter order.** Ví dụ `HashSet.stream()` không hứa thứ tự duyệt. Nếu muốn phần tử có giá trị nhỏ nhất, tốt hơn là dùng `min(comparator)` thay vì giả định `findFirst` trả phần tử nhỏ nhất.

### Xử lý Optional an toàn

```java
String result = employees.stream()
    .filter(name -> name.startsWith("Z"))
    .findFirst()
    .orElse("Không tìm thấy");

System.out.println(result); // Không tìm thấy
```

Các cách đọc `Optional` thường dùng:

- `isPresent()` và `get()` chỉ phù hợp khi đã kiểm tra chắc chắn; gọi `get()` trên `Optional.empty()` ném `NoSuchElementException`.
- `orElse(defaultValue)` cung cấp giá trị mặc định; biểu thức `defaultValue` được đánh giá trước khi gọi phương thức.
- `orElseGet(supplier)` chỉ tính giá trị thay thế khi `Optional` thực sự rỗng.
- `orElseThrow(...)` báo lỗi có chủ đích khi không có kết quả.

Stream chứa phần tử `null` có thể gây `NullPointerException` khi `findFirst` hoặc `findAny` chọn đúng phần tử `null` (vì `Optional` không biểu diễn giá trị hiện diện là `null`). Nếu dữ liệu có thể chứa `null`, lọc trước:

```java
Optional<String> first = Arrays.asList(null, "Binh", "Chi")
    .stream()
    .filter(Objects::nonNull)
    .findFirst(); // Optional[Binh]
```

## 5. Khi cần tất cả kết quả: collect, count, min, max và reduce

`findFirst` hay `anyMatch` không phù hợp nếu mục tiêu là xuất **danh sách đầy đủ**. Hãy chọn terminal thể hiện kết quả mà người dùng cần:

```java
List<Integer> prices = Arrays.asList(40, 120, 85, 200, 120);

List<Integer> expensive = prices.stream()
    .filter(price -> price >= 100)
    .collect(Collectors.toList()); // [120, 200, 120]

long expensiveCount = prices.stream()
    .filter(price -> price >= 100)
    .count(); // 3

Optional<Integer> highest = prices.stream()
    .max(Integer::compareTo); // Optional[200]

int total = prices.stream()
    .mapToInt(Integer::intValue)
    .sum(); // 565
```

Chỉ để **đếm**, dùng `count()` thay vì `collect(toList()).size()`: cách thứ hai tạo cấu trúc dữ liệu không cần thiết. Để **cộng số**, `mapToInt(...).sum()` thường rõ ý định hơn `reduce(0, Integer::sum)`, đồng thời tránh việc đóng/mở hộp ở bước tính tổng.

Khi yêu cầu một phép gộp tùy biến:

```java
int sumOfSquares = prices.stream()
    .map(price -> price * price)
    .reduce(0, Integer::sum);
```

`reduce` phải dùng phép kết hợp phù hợp hợp đồng Stream. Khi xử lý song song, toán tử tích lũy cần **kết hợp được** (*associative*), với giá trị đồng nhất (*identity*) đúng. Các phép phụ thuộc vào thứ tự như phép trừ không thể tùy tiện đem áp dụng như một phép reduce song song mà vẫn mong có nghĩa như vòng lặp tuần tự.

### collect để tạo cấu trúc hoặc tổng hợp phức tạp

```java
Map<Integer, Long> countsByLength = Arrays.asList(
        "An", "Binh", "Chi", "Dung", "Minh")
    .stream()
    .collect(Collectors.groupingBy(
        String::length,
        Collectors.counting()
    ));
// {2=1, 3=1, 4=3} (không dựa vào thứ tự duyệt khóa của Map).
```

`collect` hợp với việc xây danh sách, tập hợp, nhóm hoặc kết quả thống kê. Từ Java 16 có `stream.toList()`, trả về một List **không thể sửa đổi**. `Collectors.toList()` không hứa loại List cụ thể hay tính có thể sửa đổi. Khi cần đích có thể thêm/xóa, dùng `collect(Collectors.toCollection(ArrayList::new))`.

**Quan trọng về dừng sớm:** đa số phép tổng hợp trên cần tất cả phần tử đầu ra để xác định kết quả. `count()` có thể là ngoại lệ về **tối ưu hóa**: nếu nguồn có kích thước đã biết và các bước trung gian không thay đổi số lượng, Java có thể trả kết quả mà không duyệt từng phần tử. Vì vậy, dù có terminal, đừng dựa vào tác dụng phụ trong `peek` hay `map` để chắc chắn mọi lambda đã chạy.

## 6. forEach/forEachOrdered: dùng khi mục tiêu là hành động

`forEach` và `forEachOrdered` có kiểu trả về `void`: chúng dành cho trường hợp cần thực hiện hành động ở ranh giới tiêu thụ, chẳng hạn in kết quả, ghi đến một đầu ra do chương trình quản lý hoặc gửi từng phần tử cho một thành phần khác.

```java
List<String> messages = Arrays.asList("A", "B", "C");

messages.stream().forEach(System.out::println);
// Với Stream tuần tự có thứ tự: A, B, C.

messages.parallelStream().forEach(System.out::println);
// Thứ tự in không được bảo đảm.

messages.parallelStream().forEachOrdered(System.out::println);
// Giữ encounter order: A, B, C.
```

`forEachOrdered` giữ thứ tự **thực hiện hành động** khi Stream có encounter order, nhưng có thể thêm chi phí phối hợp. Nó không biến toàn bộ các phép toán trung gian phía trước thành xử lý tuần tự.

Nếu cần **tạo danh sách**, hãy dùng `collect` thay vì sửa một List bên ngoài từ `forEach`:

```java
List<Integer> input = Arrays.asList(1, 2, 3, 4);

// Không an toàn nếu dùng trên parallelStream:
// List<Integer> shared = new ArrayList<>();
// input.parallelStream().forEach(n -> shared.add(n * 2));

List<Integer> doubled = input.parallelStream()
    .map(n -> n * 2)
    .collect(Collectors.toList()); // [2, 4, 6, 8]
```

`ArrayList` không hỗ trợ nhiều luồng ghi đồng thời theo cách trên. Mặt khác, `peek` là phép toán **trung gian**, không phải công cụ bảo đảm mọi thao tác ghi log/kiểm toán sẽ thực thi. Với mã có tác dụng phụ, cần thiết kế tính an toàn luồng, khả năng thất bại và thứ tự thực thi phù hợp.

## 7. Dừng sớm phụ thuộc cả phần trước terminal

Một terminal có khả năng ngắn mạch **không bảo đảm** luôn trả kết quả nhanh. Hãy xét các bước trước nó.

```java
int firstEven = IntStream.rangeClosed(1, 1_000_000)
    .filter(n -> n % 2 == 0)
    .findFirst()
    .orElse(-1); // 2
```

Trên nguồn tuần tự có thứ tự, `findFirst` chỉ cần đi tới số `2`. Nhưng nếu thêm bước phải nhận toàn bộ nguồn trước khi xuất kết quả:

```java
int smallest = IntStream.rangeClosed(1, 1_000_000)
    .sorted()
    .findFirst()
    .orElse(-1); // 1
```

Với một bước `sorted` thông thường trên nguồn chưa biết đã sắp xếp, việc duyệt và sắp xếp thường cần toàn bộ đầu vào. Ví dụ trên là `IntStream.rangeClosed` vốn có thứ tự sắp xếp; một triển khai có thể tận dụng đặc tính nguồn để tối ưu. **Không dùng riêng ví dụ này làm phép đo chi phí sắp xếp.** Điều cần nhớ là việc có `findFirst` phía cuối không tự xóa chi phí của một bước có trạng thái phía trước.

Các bước khác cần xét:

- `filter(p)`: dừng sớm chỉ có ích khi phần tử phù hợp xuất hiện. Nếu không bao giờ có phần tử phù hợp trên nguồn vô hạn, `filter(p).findFirst()` không kết thúc.
- `distinct()`: có thể cần ghi nhận các giá trị đã gặp; kết hợp `limit(n)` chỉ dừng khi có đủ `n` giá trị phân biệt.
- `sorted()`: thường là bước chặn cần quan sát toàn bộ đầu vào trước khi phát phần tử đã sắp xếp; đặc biệt nguy hiểm với nguồn vô hạn.
- `limit(n)`: là bước trung gian giúp các terminal cần toàn bộ phần còn lại xử lý tối đa `n` phần tử **sau giới hạn**, miễn các bước trước cung cấp đủ dữ liệu.
- `takeWhile(p)` (Java 9+): trên nguồn có encounter order, dừng tại phần tử đầu tiên không thỏa; với nguồn vô hạn mà `p` luôn đúng thì không giúp kết thúc.

| Pipeline | Có thể trả kết quả? | Giải thích |
| --- | --- | --- |
| `Stream.generate(() -> "x").findAny()` | Có | Nguồn có thể cung cấp ngay một phần tử. |
| `IntStream.iterate(1, n -> n + 1).anyMatch(n -> n == 5)` | Có | Gặp giá trị `5` sau một đoạn hữu hạn. |
| `Stream.generate(() -> 1).allMatch(n -> n == 1)` | Không kết thúc theo cách duyệt thông thường | Không gặp phản ví dụ và nguồn không có điểm kết thúc. |
| `Stream.generate(() -> 1).anyMatch(n -> n == 2)` | Không kết thúc theo cách duyệt thông thường | Không xuất hiện phần tử làm predicate đúng. |
| `Stream.generate(() -> 1).limit(5).count()` | Có | Pipeline được giới hạn; terminal cũng có thể tối ưu khi biết kích thước. |
| `Stream.generate(() -> 1).distinct().limit(2).count()` | Không kết thúc theo cách duyệt thông thường | Chỉ có một giá trị khác nhau nên không đủ hai phần tử. |

Khi làm việc với nguồn vô hạn, chỉ nên chạy terminal cần toàn bộ dữ liệu như `collect`, `count`, `sum` hoặc `reduce` **sau khi bảo đảm pipeline có điểm dừng**. Dù vậy, `limit(10)` không phải timeout: nếu nguồn chặn ở một lần lấy dữ liệu hoặc không cho đủ phần tử vượt qua các bước lọc, pipeline vẫn có thể chờ vô hạn.

## 8. Khi chạy song song: hiệu năng, thứ tự và tác dụng phụ

Stream song song có thể xử lý nhiều phần tử đồng thời. `anyMatch`/`allMatch`/`noneMatch` vẫn có hợp đồng kết quả tương tự tuần tự, nhưng có thể nhiều predicate đã được gọi trên các phần tử khác nhau trước khi công việc ngắn mạch dừng. **Không bảo đảm** mỗi lambda chỉ được gọi đến đúng phần tử quyết định kết quả.

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6);

boolean hasEven = numbers.parallelStream()
    .anyMatch(n -> n % 2 == 0); // true

Optional<Integer> firstEven = numbers.parallelStream()
    .filter(n -> n % 2 == 0)
    .findFirst(); // Optional[2]

Optional<Integer> anyEven = numbers.parallelStream()
    .filter(n -> n % 2 == 0)
    .findAny(); // Một trong 2, 4, 6
```

Trên `List` có thứ tự, `findFirst` phải bảo toàn khái niệm “đầu tiên”; `findAny` có thể trả một phần tử phù hợp bất kỳ, nên thường có nhiều tự do tối ưu song song hơn. `forEachOrdered` bảo toàn thứ tự hành động, còn `forEach` không.

Một số nguyên tắc:

1. Lambda trong pipeline nên **không sửa trạng thái dùng chung** và không dựa vào lịch chạy của các luồng.
2. Đừng gọi `unordered()` nếu kết quả nghiệp vụ yêu cầu “đầu tiên”, chẳng hạn phần tử đầu theo thời gian.
3. Đừng mặc định `parallelStream()` nhanh hơn: chi phí chia việc, hủy tác vụ, ràng buộc thứ tự và bước có trạng thái có thể lớn hơn lợi ích.
4. Nếu hiệu năng quan trọng, đo trên dữ liệu và môi trường đại diện; với danh sách rất nhỏ, tuần tự thường đơn giản hơn.

## 9. Ví dụ hoàn chỉnh: mỗi yêu cầu chọn đúng terminal

Đoạn mã dưới đây chạy được với Java 8+, dùng cùng một nguồn `List` và tạo **Stream mới cho từng truy vấn**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public class TerminalChoiceDemo {
    public static void main(String[] args) {
        List<String> products = Arrays.asList(
            "pen", "book", "ruler", "eraser"
        );

        // Có ít nhất một tên dài từ 5 ký tự không?
        boolean hasLongName = products.stream()
            .anyMatch(name -> name.length() >= 5);

        // Có phải mọi tên đều không rỗng?
        boolean allNamed = products.stream()
            .allMatch(name -> !name.isEmpty());

        // Không có tên nào chứa chữ số?
        boolean noDigit = products.stream()
            .noneMatch(name -> name.matches(".*\\d.*"));

        // Tên dài từ 5 ký tự đầu tiên theo List.
        Optional<String> firstLong = products.stream()
            .filter(name -> name.length() >= 5)
            .findFirst();

        // Có bao nhiêu tên dài hơn 3 ký tự?
        long count = products.stream()
            .filter(name -> name.length() > 3)
            .count();

        // Thu toàn bộ tên dài hơn 3 ký tự, giữ thứ tự List.
        List<String> selected = products.stream()
            .filter(name -> name.length() > 3)
            .collect(Collectors.toList());

        // Tổng số ký tự trong các tên.
        int totalLength = products.stream()
            .mapToInt(String::length)
            .sum();

        System.out.println("Có tên dài: " + hasLongName);
        System.out.println("Tất cả có tên: " + allNamed);
        System.out.println("Không có chữ số: " + noDigit);
        System.out.println("Tên dài đầu tiên: " + firstLong.orElse("Không có"));
        System.out.println("Số tên > 3 ký tự: " + count);
        System.out.println("Tên đã chọn: " + selected);
        System.out.println("Tổng ký tự: " + totalLength);
    }
}
```

Đầu ra:

```text
Có tên dài: true
Tất cả có tên: true
Không có chữ số: true
Tên dài đầu tiên: ruler
Số tên > 3 ký tự: 3
Tên đã chọn: [book, ruler, eraser]
Tổng ký tự: 18
```

Mỗi terminal trả về đúng loại dữ liệu cần thiết: `boolean` cho câu hỏi logic, `Optional` cho tìm kiếm, `long` cho đếm, `List` cho thu thập và `int` cho tổng.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều cần làm |
| --- | --- |
| Dùng `filter(p).collect(toList()).isEmpty()` chỉ để hỏi có hay không | Dùng `anyMatch(p)` (hoặc `noneMatch(p)` cho câu hỏi phủ định) |
| Dùng `filter(p).count() > 0` để tìm phần tử phù hợp | Dùng `anyMatch(p)` để có cơ hội dừng sớm |
| Dùng `findAny` rồi coi kết quả là phần tử đầu tiên | Dùng `findFirst` trên nguồn có encounter order phù hợp |
| Dùng `findFirst` trên `HashSet` để lấy giá trị nhỏ nhất | Dùng `min(comparator)` hoặc thiết lập thứ tự rõ ràng |
| Mong `allMatch` trên nguồn rỗng trả `false` | Nhớ rằng `allMatch` trên rỗng trả `true` |
| Gọi `Optional.get()` mà không kiểm tra | Dùng `orElse`, `orElseGet` hoặc `orElseThrow` phù hợp |
| Dùng `forEach` để thêm vào `ArrayList` chung trong parallel stream | Dùng `collect` với cơ chế tích lũy được thư viện quản lý |
| Nghĩ mọi terminal đều tự dừng sớm | Xem hợp đồng từng terminal và các bước có trạng thái ở phía trước |
| Nghĩ `count()` chắc chắn gọi mọi `peek` | Không dựa vào tác dụng phụ trong bước trung gian |
| Chạy `allMatch` vô hạn khi mọi phần tử đều đúng | Đặt giới hạn hữu hạn hoặc một điều kiện dừng có thể đạt |
| Dùng lại một Stream cho nhiều terminal | Tạo Stream mới từ nguồn cho từng phép tính |

## 11. Câu hỏi tự kiểm tra

**Bài 1 — Chọn phép toán.** Có một triệu đơn hàng, chỉ cần biết liệu **có bất kỳ đơn nào** vượt 10 triệu đồng. Chọn `count() > 0`, `collect(toList()).isEmpty()` hay `anyMatch`?

```java
boolean hasLargeOrder = amounts.stream()
    .anyMatch(amount -> amount > 10_000_000L);
```

**Đáp án:** `anyMatch` thể hiện trực tiếp câu hỏi tồn tại và có khả năng dừng sớm khi gặp một đơn phù hợp. `count` phải xác định số phần tử sau bộ lọc trong trường hợp tổng quát.

**Bài 2 — Kết quả trên Stream rỗng.** Dự đoán:

```java
boolean a = Stream.<Integer>empty().anyMatch(n -> n > 0);
boolean b = Stream.<Integer>empty().allMatch(n -> n > 0);
boolean c = Stream.<Integer>empty().noneMatch(n -> n > 0);
Optional<Integer> d = Stream.<Integer>empty().findFirst();
```

**Đáp án:** `a = false`, `b = true`, `c = true`, `d = Optional.empty()`.

**Bài 3 — Tìm kiếm có thứ tự.** Với `List<Integer> values = Arrays.asList(9, 4, 6, 2);`, lấy **số chẵn đầu tiên theo vị trí List**; khi chạy song song cần terminal nào?

```java
Optional<Integer> first = values.parallelStream()
    .filter(n -> n % 2 == 0)
    .findFirst(); // Optional[4]
```

**Đáp án:** `findFirst` giữ encounter order; `findAny` được phép trả `4`, `6` hoặc `2`.

**Bài 4 — Nguồn vô hạn.** `Stream.generate(() -> 1).noneMatch(n -> n == 2)` có kết thúc không? Làm sao kiểm tra 100 giá trị đầu?

```java
boolean noneInSample = Stream.generate(() -> 1)
    .limit(100)
    .noneMatch(n -> n == 2); // true
```

**Đáp án:** Không có điều kiện ngắt trên nguồn vô hạn ban đầu, vì không có `2`; terminal không thể biết đã duyệt hết. `limit(100)` thu hẹp câu hỏi thành một mẫu hữu hạn.

**Bài 5 — Thu thập và hành động.** Để tạo `List<String>` chứa tên viết hoa từ một `List` lớn chạy song song, nên dùng `forEach` thêm vào List chung hay `collect`?

```java
List<String> upperNames = names.parallelStream()
    .map(String::toUpperCase)
    .collect(Collectors.toList());
```

**Đáp án:** Dùng `collect` để tạo dữ liệu đầu ra. Việc cùng thêm vào một `ArrayList` từ nhiều luồng có thể gây race condition và sai kết quả.

## Ghi nhớ

Trong **JAVA_STREAM_API**, hãy bắt đầu từ **câu hỏi nghiệp vụ** để chọn terminal: `anyMatch`/`allMatch`/`noneMatch` cho câu trả lời logic; `findFirst`/`findAny` cho một phần tử; `collect` cho cấu trúc kết quả; `count`, `min`/`max`, `sum` hoặc `reduce` cho phép tổng hợp; `forEach` khi mục đích thực sự là một hành động. Khả năng dừng sớm chỉ có ích khi pipeline có thể cung cấp đủ bằng chứng và không bị bước trước đó chặn lại. Khi chuyển sang Stream song song, phải giữ đúng yêu cầu thứ tự, không phụ thuộc vào trạng thái chia sẻ và đánh giá hiệu năng bằng phép đo thực tế.
