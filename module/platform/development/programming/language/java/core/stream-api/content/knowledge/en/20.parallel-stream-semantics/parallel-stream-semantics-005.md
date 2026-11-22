# Thứ tự kết quả với findAny, findFirst, forEach và forEachOrdered

## 1. Xử lý song song có đồng nghĩa với mất thứ tự không?

Trong **Java Stream API**, một pipeline gồm nguồn dữ liệu, các thao tác trung gian như `filter`, `map`, `sorted` và một thao tác kết thúc như `findFirst`, `findAny`, `forEach` hoặc `collect`. Khi chuyển pipeline sang `parallel()` hoặc tạo nguồn bằng `parallelStream()`, Stream có thể chia công việc cho nhiều tác vụ để xử lý đồng thời.

Nhưng **thứ tự thực thi** và **thứ tự kết quả** là hai khái niệm khác nhau:

- **Thứ tự thực thi:** tác vụ hoặc lambda nào chạy trước trên các thread. Với Stream song song, lịch chạy không cố định.
- **Encounter order:** thứ tự gặp phần tử được nguồn và pipeline định nghĩa về mặt logic.
- **Thứ tự kết quả:** một terminal operation có bảo toàn encounter order hay được phép bỏ qua nó.

Ví dụ:

```java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

List<Integer> doubled = numbers.parallelStream()
        .map(n -> n * 2)
        .toList();

System.out.println(doubled); // [2, 4, 6, 8, 10]
```

Các lời gọi `map` **có thể chạy trên các thread theo lịch khác nhau**, nhưng `toList()` bảo toàn encounter order của nguồn `List`. Vì vậy, chuyển sang song song **không tự động đảo thứ tự kết quả**.

Ở chương **Ngữ nghĩa xử lý song song**, bài này tập trung vào bốn terminal operation có hợp đồng thứ tự khác nhau:

- `findAny`: tìm **một phần tử bất kỳ**, không cam kết là phần tử đầu.
- `findFirst`: tìm **phần tử đầu tiên theo encounter order**, nếu Stream có thứ tự.
- `forEach`: thực hiện hành động cho từng phần tử nhưng **không cam kết thứ tự hành động** khi xử lý song song.
- `forEachOrdered`: thực hiện hành động **theo encounter order** nếu Stream có thứ tự, kể cả khi pipeline ở chế độ song song.

**Mục tiêu:** hiểu khi nào thứ tự được bảo toàn hoặc được nới lỏng, lựa chọn đúng thao tác kết thúc, tránh lỗi tác dụng phụ và trạng thái dùng chung, đồng thời đánh giá đánh đổi về hiệu năng, dừng sớm và khả năng chia công việc.

Các ví dụ sử dụng **Java 17+** để có `record` và `Stream.toList()`. Bốn terminal operation được trình bày đã có trong Stream API từ Java 8.

## 2. Encounter order đến từ nguồn nào?

Một Stream có thể **có** hoặc **không có** encounter order. Đây là thuộc tính logic của luồng, không phải việc JVM tình cờ trả dữ liệu theo một thứ tự trong một lần chạy.

| Nguồn hoặc thao tác | Thuộc tính thứ tự cần nhớ |
| --- | --- |
| `List.stream()` / `List.parallelStream()` | Có encounter order theo thứ tự các phần tử của List. |
| `Arrays.stream(array)` | Có encounter order theo chỉ số mảng. |
| `IntStream.range(...)` | Có encounter order theo dãy số tăng. |
| `LinkedHashSet.stream()` | Có encounter order theo thứ tự lặp do `LinkedHashSet` quy định. |
| `TreeSet.stream()` | Có encounter order theo thứ tự sắp xếp của Set. |
| `HashSet.stream()` | Không cam kết encounter order có ý nghĩa. |
| `HashMap.keySet().stream()` | Không cam kết encounter order từ `HashMap`. |
| `unordered()` | Bỏ ràng buộc encounter order của pipeline nếu trước đó có. |
| `parallel()` | Chọn chế độ xử lý song song; **không tự xóa encounter order**. |

Ví dụ nguồn có thứ tự:

```java
List<String> names = List.of("An", "Bình", "Chi", "Dũng");

String first = names.parallelStream()
        .findFirst()
        .orElseThrow();

System.out.println(first); // An
```

Điểm mấu chốt không phải danh sách được xử lý bởi thread nào, mà là `findFirst` phải tôn trọng **phần tử đầu tiên theo thứ tự của List**.

Ngược lại:

```java
Set<String> namesWithoutOrder =
        new java.util.HashSet<>(List.of("An", "Bình", "Chi"));

Optional<String> selected = namesWithoutOrder.parallelStream()
        .findFirst();

// Không có cam kết rằng "An" là phần tử đầu tiên.
```

`findFirst` không thể tự tạo một "đầu tiên" ổn định từ nguồn không có encounter order. Nếu cần kết quả mang tiêu chí "nhỏ nhất theo tên", phải **xác định thứ tự nghiệp vụ** hoặc dùng một terminal operation phù hợp như `min`.

## 3. Bảng so sánh hợp đồng của bốn terminal operation

Các chữ ký trên `Stream<T>`:

```java
Optional<T> findAny();
Optional<T> findFirst();
void forEach(Consumer<? super T> action);
void forEachOrdered(Consumer<? super T> action);
```

| Phương thức | Kết quả | Với Stream có encounter order | Có thể dừng sớm? |
| --- | --- | --- | --- |
| `findAny()` | `Optional<T>` | Không bắt buộc chọn phần tử đầu tiên | Có |
| `findFirst()` | `Optional<T>` | Chọn phần tử đầu tiên theo encounter order | Có |
| `forEach(action)` | `void` | Với song song, không cam kết thứ tự gọi action | Không, nhằm xử lý các phần tử |
| `forEachOrdered(action)` | `void` | Action được thực hiện theo encounter order | Không, nhằm xử lý các phần tử |

`findAny` và `findFirst` là **short-circuiting terminal operations**: chúng chỉ cần tìm một kết quả phù hợp và có thể tránh tiêu thụ toàn bộ luồng. Tuy nhiên, trong pipeline song song, một số phần tử khác **có thể vẫn được xử lý** trong quá trình phối hợp; không dùng chúng để bảo đảm rằng mapper chạy đúng một lần.

`forEach` và `forEachOrdered` là terminal operations dành cho **hành động**, không trả List hoặc giá trị kết quả. Nếu chỉ muốn biến dữ liệu thành một danh sách, `toList` hoặc `collect` thường diễn đạt mục tiêu tốt hơn.

Một Stream có thể rỗng sau `filter`. Khi đó cả `findAny` và `findFirst` trả `Optional.empty()`. `forEach` và `forEachOrdered` sẽ không gọi action cho phần tử nào.

## 4. findAny: phần tử nào cũng được, miễn thỏa điều kiện

`findAny` có thể chọn **bất kỳ phần tử nào còn lại trong Stream**. Thiết kế này cho phép JVM tận dụng kết quả từ một nhánh xử lý mà không phải chứng minh đó là phần tử đầu tiên toàn cục.

```java
List<Integer> numbers = List.of(10, 20, 30, 40, 50);

Optional<Integer> anyLarge = numbers.parallelStream()
        .filter(n -> n >= 30)
        .findAny();

System.out.println(anyLarge);
// Có thể là Optional[30], Optional[40] hoặc Optional[50].
```

Tất cả các kết quả trên đều hợp lệ. **Không được viết test yêu cầu `findAny` luôn trả `30`**, dù quan sát trên máy cụ thể nhiều lần thấy cùng một số.

### findAny có thể được dùng cả khi tuần tự

`findAny` **không đồng nghĩa** "chọn phần tử hoàn thành nhanh nhất", cũng không bảo đảm JVM phân tích hiệu năng để chọn kết quả tốt nhất. Nó chỉ nới lỏng hợp đồng lựa chọn. Trên pipeline tuần tự, kết quả thường trông giống phần tử đầu nhưng đó không phải điều kiện đúng đắn có thể dựa vào.

```java
Optional<String> any = names.stream()
        .filter(name -> !name.isBlank())
        .findAny();

// Không dựa vào any.orElseThrow().equals("An").
```

### Khi nào findAny là lựa chọn phù hợp?

`findAny` hợp lý khi **bất kỳ bản ghi nào thỏa điều kiện đều có thể được sử dụng như nhau**, ví dụ tìm một máy chủ khả dụng trong nhóm, một mẫu dữ liệu để kiểm tra hoặc một phần tử chứng minh rằng tập kết quả không rỗng.

Nếu chỉ cần biết **có tồn tại** phần tử thỏa điều kiện hay không, `anyMatch` rõ ý nghĩa và trả về `boolean`:

```java
boolean hasLarge = numbers.parallelStream()
        .anyMatch(n -> n >= 30);

System.out.println(hasLarge); // true
```

Không cần tạo `Optional` nếu nghiệp vụ không cần chính phần tử được chọn.

## 5. findFirst: ưu tiên phần tử đầu tiên theo encounter order

Với Stream có thứ tự, `findFirst` bắt buộc chọn phần tử đầu tiên của luồng **sau các thao tác trung gian**.

```java
List<Integer> samples = List.of(4, 9, 2, 7, 3);

int firstEven = samples.parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElseThrow();

System.out.println(firstEven); // 4
```

Số `2` cũng thỏa điều kiện nhưng xuất hiện **sau `4`** trong encounter order của List. Dù nhánh chứa số `2` hoàn thành sớm, `findFirst` vẫn phải trả `4`.

### Chạy song song không phải cách chọn phần tử ngẫu nhiên

Nếu business rule là "chọn đơn đầu tiên trong lịch sử đã được sắp đúng theo thời gian", `findFirst` là lựa chọn. Nếu không quan tâm đơn nào được chọn, `findAny` có thể cho framework nhiều quyền tối ưu hơn.

```java
record Request(String id, boolean ready) {}

List<Request> requests = List.of(
        new Request("R01", false),
        new Request("R02", true),
        new Request("R03", true),
        new Request("R04", true)
);

Request firstReady = requests.parallelStream()
        .filter(Request::ready)
        .findFirst()
        .orElseThrow();

System.out.println(firstReady.id()); // R02
```

### findFirst không tự hiểu "nhỏ nhất" hoặc "mới nhất"

`findFirst` chọn **theo thứ tự có sẵn trong pipeline**, chứ không tự tìm số nhỏ nhất hay timestamp mới nhất:

```java
List<Integer> scores = List.of(90, 70, 100, 80);

int first = scores.parallelStream()
        .findFirst()
        .orElseThrow(); // 90

int smallest = scores.parallelStream()
        .min(Integer::compareTo)
        .orElseThrow(); // 70

int sortedFirst = scores.parallelStream()
        .sorted()
        .findFirst()
        .orElseThrow(); // 70
```

`min` diễn đạt trực tiếp yêu cầu lấy giá trị nhỏ nhất mà không phải xây dựng một pipeline sắp xếp đầy đủ. `sorted().findFirst()` cũng cho kết quả nhỏ nhất ở ví dụ này, nhưng `sorted` là thao tác có trạng thái và có thể phải xử lý nhiều dữ liệu hơn.

Nếu có nhiều phần tử cùng giá trị ưu tiên, hãy xác định **quy tắc tie-break** để bảo đảm tính nhất quán của lựa chọn.

## 6. findFirst hay findAny khi nguồn không có thứ tự?

`findFirst` chỉ thể hiện "đầu tiên" khi luồng đã có encounter order. Nếu gọi `unordered()`, bạn chủ động bỏ cam kết thứ tự:

```java
List<Integer> values = List.of(10, 20, 30, 40);

Optional<Integer> noDefinedFirst = values.parallelStream()
        .unordered()
        .findFirst();

// Có thể là bất kỳ phần tử nào; không cam kết 10.
```

Đây là lời gọi `findFirst` hợp lệ, nhưng không mang ý nghĩa "phần tử đầu của List" sau khi đã bỏ order. `findAny` thường là cách diễn đạt rõ hơn khi bất kỳ phần tử nào cũng chấp nhận được.

### Muốn xác lập thứ tự trước khi chọn?

```java
Set<Integer> unorderedNumbers =
        new java.util.HashSet<>(List.of(40, 10, 30, 20));

int smallestBySort = unorderedNumbers.parallelStream()
        .sorted()
        .findFirst()
        .orElseThrow();

System.out.println(smallestBySort); // 10
```

`sorted` tạo dãy theo thứ tự so sánh; khi dùng cùng một tiêu chí ổn định, `findFirst` có một "đầu" có ý nghĩa. Tuy nhiên, nếu chỉ cần phần tử nhỏ nhất, `min` thường đơn giản hơn. Không thêm `sorted` máy móc vào mọi pipeline chỉ để lấy một kết quả.

## 7. forEach: xử lý mọi phần tử, không cam kết thứ tự hành động khi song song

`forEach` nhận một `Consumer<T>` và không trả về kết quả:

```java
List<String> letters = List.of("A", "B", "C", "D");

letters.parallelStream()
        .forEach(System.out::println);

// Có thể in theo bất kỳ thứ tự nào, ví dụ C, D, B, A.
// Không có một thứ tự in cố định được bảo đảm.
```

Nguồn là `List` có encounter order, nhưng `forEach` trên pipeline song song **được phép bỏ qua thứ tự khi gọi action**. Điều này tạo cơ hội cho các nhánh hoàn thành công việc độc lập hơn.

Với pipeline tuần tự đơn giản, `forEach` thường in đúng thứ tự gặp phần tử. Nhưng nếu hợp đồng nghiệp vụ **bắt buộc bảo toàn thứ tự** khi về sau thay `stream()` thành `parallelStream()`, hãy dùng `forEachOrdered` ngay từ đầu hoặc thiết kế lại để trả một Collection có thứ tự.

### forEach phù hợp với dạng tác vụ nào?

Chỉ sử dụng `forEach` cho hành động thực sự cần thực hiện trên mỗi phần tử, ví dụ gửi một phép xử lý độc lập hoặc ghi nhận kết quả bằng cấu trúc tích lũy hỗ trợ concurrency.

Không dùng `forEach` để tích lũy vào một `ArrayList` chia sẻ không đồng bộ:

```java
List<Integer> shared = new java.util.ArrayList<>();

// SAI: nhiều thread có thể gọi shared.add cùng lúc.
List.of(1, 2, 3, 4).parallelStream()
        .forEach(shared::add);

// Có thể mất dữ liệu, sai kích thước hoặc gặp lỗi do race condition.
```

Nếu mục tiêu là **thu thập** một danh sách, dùng terminal operation thu thập:

```java
List<Integer> collected = List.of(1, 2, 3, 4)
        .parallelStream()
        .toList();

System.out.println(collected); // [1, 2, 3, 4]
```

Vì `toList` tự thực hiện phần thu thập phù hợp với Stream, ta không cần tự dùng shared mutable List trong `forEach`.

## 8. forEachOrdered: giữ encounter order của hành động

Khi thứ tự của **hành động cuối cùng** là một phần của yêu cầu, dùng `forEachOrdered`:

```java
List<String> letters = List.of("A", "B", "C", "D");

letters.parallelStream()
        .forEachOrdered(System.out::println);

// In theo đúng thứ tự:
// A
// B
// C
// D
```

`forEachOrdered` **không đòi hỏi toàn bộ pipeline phải chạy tuần tự**. Các bước trước nó vẫn có thể được thực thi song song, nhưng **các action** phải theo encounter order của Stream.

Theo hợp đồng của Java, việc thực hiện action cho một phần tử trong `forEachOrdered` **happens-before** việc thực hiện action cho phần tử tiếp theo. Tuy nhiên, action cho các phần tử khác nhau **không nhất thiết chạy trên cùng một thread**.

### So sánh trực tiếp

```java
List<Integer> ids = List.of(10, 20, 30, 40);

ids.parallelStream().forEach(System.out::println);
// Không cam kết thứ tự.

ids.parallelStream().forEachOrdered(System.out::println);
// In 10, 20, 30, 40 theo đúng encounter order.
```

Điều kiện là Stream **phải có encounter order**. Với nguồn không có thứ tự, `forEachOrdered` không thể tự biến dữ liệu thành một danh sách được sắp xếp:

```java
Set<Integer> hashNumbers =
        new java.util.HashSet<>(List.of(10, 20, 30, 40));

hashNumbers.parallelStream()
        .forEachOrdered(System.out::println);

// Không có cam kết in 10, 20, 30, 40.
```

Tên `forEachOrdered` không đồng nghĩa với `sorted`. Nó giữ **thứ tự gặp phần tử đã tồn tại**, không tạo thứ tự giá trị.

## 9. Thứ tự của map và peek khác thứ tự của forEachOrdered

Một lỗi rất phổ biến là cho rằng `forEachOrdered` sẽ khiến **mọi lambda trong pipeline** chạy lần lượt từ đầu đến cuối.

```java
List<Integer> numbers = List.of(1, 2, 3, 4);

numbers.parallelStream()
        .map(n -> {
            System.out.println("map " + n
                    + " bởi " + Thread.currentThread().getName());
            return n * 10;
        })
        .forEachOrdered(n ->
                System.out.println("output " + n));
```

Các dòng `output` được thực hiện theo thứ tự giá trị `10, 20, 30, 40`. Nhưng các dòng `map` **không có thứ tự thực thi được cam kết** và có thể xuất hiện xen kẽ với việc in output.

Điều `forEachOrdered` bảo đảm là **thứ tự thực hiện action terminal**, không phải thứ tự gọi của `map`, `filter` hay `peek` trước nó.

### peek không phải công cụ bảo đảm mỗi phần tử đều tạo tác dụng phụ

`peek` thường hữu ích để quan sát khi debug:

```java
Optional<Integer> found = numbers.parallelStream()
        .peek(n -> System.out.println("Thấy " + n))
        .findFirst();
```

Pipeline có thể xử lý một số phần tử không được chọn, hoặc được tối ưu để bỏ qua các thao tác trung gian không cần thiết đối với terminal operation. Không dùng `peek` hay `map` cho việc ghi log, gửi thông điệp hoặc tăng biến đếm **bắt buộc phải xảy ra đúng một lần cho mọi phần tử**.

### Khi cần danh sách đúng thứ tự

`forEachOrdered` hữu ích cho hành động cuối có tính thứ tự như viết tuần tự từng dòng ra một kênh. Nhưng nếu mục tiêu là **tạo dữ liệu có cấu trúc**, thu thập trước sẽ thường dễ kiểm tra hơn:

```java
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 10)
        .toList();

System.out.println(result); // [10, 20, 30, 40]
```

Ở đây không cần hành động phụ của consumer, cũng không cần tự phối hợp các thread.

## 10. Stateless, non-interfering và các lỗi trạng thái chia sẻ

Trong Stream, các lambda dùng cho `filter`, `map` và phần lớn thao tác trung gian nên **stateless** (không dựa vào trạng thái mutable bên ngoài) và **non-interfering** (không sửa nguồn đang được duyệt).

Ví dụ sai:

```java
List<Integer> mutableSource =
        new java.util.ArrayList<>(List.of(1, 2, 3, 4));

// SAI: sửa chính nguồn trong khi đang duyệt.
mutableSource.parallelStream()
        .forEach(value -> mutableSource.add(value * 10));
```

Nguồn như `ArrayList` không hỗ trợ kiểu thay đổi này trong lúc Stream đang duyệt. Kết quả có thể là `ConcurrentModificationException`, dữ liệu sai hoặc hành vi không đáng tin cậy.

Ngay cả việc đếm bằng biến thông thường cũng không an toàn:

```java
int[] counter = {0};

// SAI: cập nhật chung counter[0] không đồng bộ.
IntStream.range(0, 1_000).parallel()
        .forEach(n -> counter[0]++);

// Không thể tin rằng counter[0] == 1000.
```

Nếu chỉ cần số phần tử, `count()` mới là biểu thức phù hợp:

```java
long total = IntStream.range(0, 1_000)
        .parallel()
        .count();

System.out.println(total); // 1000
```

Nếu thực sự cần tích lũy một đại lượng trong các action độc lập, hãy chọn công cụ đồng bộ phù hợp. Ví dụ `LongAdder`:

```java
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.IntStream;

LongAdder sum = new LongAdder();

IntStream.rangeClosed(1, 1_000)
        .parallel()
        .forEach(sum::add);

System.out.println(sum.sum()); // 500500
```

Tuy nhiên, **để tính tổng**, dùng `IntStream.sum()` hoặc `mapToLong(...).sum()` vẫn đơn giản hơn và thường tránh được cập nhật vào một accumulator chia sẻ.

### forEachOrdered có làm mọi trạng thái bên ngoài thread-safe không?

Không. Thứ tự các action của **một lời gọi `forEachOrdered`** được ràng buộc, nhưng điều đó không bảo vệ biến khỏi những truy cập đồng thời **ngoài pipeline**, cũng không khiến các lambda trung gian vốn có trạng thái trở nên hợp lệ.

Ví dụ, hai lời gọi Stream khác nhau cùng ghi vào một danh sách chung vẫn cần phối hợp riêng. Còn nếu logic yêu cầu trạng thái của từng phần tử phụ thuộc phần tử trước, một vòng lặp tuần tự rõ ràng có thể đúng hơn cố ép pipeline song song.

## 11. unordered(): nới lỏng ràng buộc, không phải xáo trộn

`BaseStream.unordered()` trả về một Stream có thể được xử lý mà **không phải giữ encounter order**. Nó **không phải** `shuffle` và không hứa tạo một hoán vị ngẫu nhiên.

```java
List<String> ids = List.of("R01", "R02", "R03", "R04");

Optional<String> anyFirst = ids.parallelStream()
        .unordered()
        .findFirst();

// Không còn cam kết chọn "R01".
```

Một số thao tác song song đòi giữ encounter order có thể cần phối hợp tốn kém. Khi nghiệp vụ không quan tâm thứ tự, bỏ ràng buộc này **có thể** mở ra cơ hội tối ưu, nhưng hiệu quả phải đo thực tế.

Trái lại, khi kết quả là báo cáo cần tái lập chính xác theo thứ tự nguồn, **không gọi `unordered()` chỉ để mong chạy nhanh hơn**.

### forEachOrdered sau unordered()

```java
ids.parallelStream()
        .unordered()
        .forEachOrdered(System.out::println);

// Từ đây không có encounter order được bảo đảm để giữ.
```

`forEachOrdered` không thể phục hồi cam kết đã bỏ. Nếu cần thứ tự chữ cái, mã ID hoặc thời gian, phải thiết kế tiêu chí sắp xếp rõ ràng trước terminal operation.

## 12. Thao tác trung gian có thể thay đổi ý nghĩa "đầu tiên"

Ngay cả trên List có thứ tự, **thứ tự và nội dung sau các bước trung gian** mới quyết định kết quả `findFirst`.

### filter giữ thứ tự tương đối

```java
List<Integer> values = List.of(5, 2, 8, 1, 4);

int firstEven = values.parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElseThrow();

System.out.println(firstEven); // 2
```

`filter` giữ thứ tự tương đối của những phần tử được giữ trong Stream ordered. `findFirst` ở đây không trả `8` hay `4`, dù hai số đó cũng chẵn.

### sorted tạo thứ tự giá trị

```java
int smallestEven = values.parallelStream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .findFirst()
        .orElseThrow();

System.out.println(smallestEven); // 2
```

Kết quả tình cờ giống ví dụ trước nhưng hợp đồng khác. Nếu thay `values` bằng `List.of(8, 2, 4)`, `findFirst` sau `filter` sẽ trả `8`; có `sorted()` sẽ trả `2`.

### limit và takeWhile chịu tác động của encounter order

Các thao tác như `limit`, `skip`, `takeWhile` và `dropWhile` có ngữ nghĩa đặc biệt liên quan tới thứ tự. Với nguồn ordered, giữ một tiền tố chính xác có thể tốn công phối hợp trong pipeline song song:

```java
List<Integer> firstThree = IntStream.rangeClosed(1, 100)
        .parallel()
        .limit(3)
        .boxed()
        .toList();

System.out.println(firstThree); // [1, 2, 3]
```

Không đánh đồng việc dừng sớm hoặc cắt lát với "mọi tác vụ chỉ kiểm tra đúng ba phần tử". Đặc biệt, khi có `sorted` hoặc những thao tác stateful khác, framework có thể cần xử lý thêm dữ liệu để bảo toàn hợp đồng.

## 13. Null, Optional và trường hợp không tìm thấy

`findFirst` và `findAny` trả về `Optional<T>` vì Stream có thể rỗng sau các bộ lọc:

```java
Optional<Integer> noMatch = List.of(1, 3, 5)
        .parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(noMatch.isEmpty()); // true
```

Nếu không có kết quả, `orElse` hoặc `orElseThrow` thể hiện rõ chính sách:

```java
int fallback = noMatch.orElse(-1); // -1

// Nếu không tìm thấy là lỗi nghiệp vụ:
// int required = noMatch.orElseThrow(
//         () -> new IllegalStateException("Không có phần tử phù hợp"));
```

**Lưu ý null:** `Optional` không thể giữ `null`. Nếu phần tử được `findFirst` hoặc `findAny` chọn là `null`, thao tác có thể ném `NullPointerException`. Khi nguồn có thể chứa null, phải xử lý theo chính sách đầu vào:

```java
List<String> raw = java.util.Arrays.asList(null, "A", "B");

Optional<String> firstNonNull = raw.parallelStream()
        .filter(java.util.Objects::nonNull)
        .findFirst();

System.out.println(firstNonNull.orElseThrow()); // A
```

`List.of(...)` không cho phần tử null, nên ví dụ cố ý dùng `Arrays.asList`. Lọc null ở đây vẫn giữ encounter order của những phần tử còn lại.

## 14. Hiệu năng: trả giá cho việc giữ thứ tự

**Không có quy tắc "dùng parallel luôn nhanh hơn".** Khi chọn thao tác, cần cân nhắc yêu cầu nghiệp vụ trước, sau đó đo trên dữ liệu thật.

| Lựa chọn | Ưu điểm về ngữ nghĩa | Chi phí hoặc giới hạn có thể gặp |
| --- | --- | --- |
| `findAny` | Cho phép chọn bất kỳ phần tử phù hợp | Không có kết quả cố định nếu nhiều phần tử phù hợp |
| `findFirst` | Giữ phần tử đầu tiên của Stream ordered | Trong pipeline song song, có thể phải phối hợp để xác định không có phần tử phù hợp trước đó |
| `forEach` | Cho phép thực hiện action độc lập, không cần giữ order | Thứ tự tác dụng phụ không ổn định, cần bảo vệ trạng thái chia sẻ |
| `forEachOrdered` | Bảo toàn thứ tự action trên Stream ordered | Ràng buộc thứ tự có thể giảm khả năng khai thác song song |
| `unordered()` | Nới ràng buộc thứ tự khi không cần | Thay đổi ngữ nghĩa với `findFirst`, `limit`, `takeWhile` và các thao tác nhạy order |
| `sorted()` | Xác lập thứ tự theo comparator | Thao tác stateful, có thể cần giữ dữ liệu trung gian |

Các yếu tố ảnh hưởng tốc độ gồm kích thước nguồn, chi phí tính toán từng phần tử, khả năng chia nguồn (`Spliterator.trySplit`), số lượng phần tử đạt điều kiện, bộ đệm trung gian, fork/join scheduling và tài nguyên CPU thực tế.

### Khi nào cân nhắc findAny thay findFirst?

Nếu bài toán thực sự là "tìm **một** phần tử thỏa bất kỳ" và có nhiều phần tử phù hợp, `findAny` cho phép Stream dừng khi một nhánh có kết quả mà không cần chứng minh tính "đầu tiên" theo encounter order. Điều này **có thể** có lợi với nguồn lớn và xử lý song song. Không hứa tốc độ cải thiện với mọi nguồn hoặc điều kiện.

### Khi nào không nên sử dụng parallel?

Nếu nguồn nhỏ, mỗi mapper rất rẻ hoặc đầu ra buộc phải thực hiện action lần lượt qua `forEachOrdered`, chi phí điều phối có thể lớn hơn phần việc tiết kiệm được.

Nếu công việc chủ yếu là I/O blocking hoặc bị giới hạn bởi một tài nguyên chia sẻ, không mặc định `parallelStream` là giải pháp thích hợp. Nên dùng mô hình concurrency được thiết kế theo tài nguyên, giới hạn số tác vụ và cơ chế xử lý lỗi.

Trong Java, Stream song song thường tận dụng cơ chế fork/join của runtime; không nên giả định mỗi phần tử có một thread riêng hoặc dùng chính tên thread để làm một phần logic nghiệp vụ.

## 15. Ví dụ hoàn chỉnh: chọn và hiển thị công việc theo thứ tự

Một hệ thống quản lý công việc có danh sách theo **thứ tự nhập**, mỗi công việc có ID, độ ưu tiên và trạng thái sẵn sàng. Yêu cầu:

1. Chọn công việc sẵn sàng **đầu tiên theo thứ tự nhập**.
2. Khi không cần ưu tiên, chọn **một công việc sẵn sàng bất kỳ**.
3. Nếu muốn **công việc có độ ưu tiên cao nhất**, xác định tiêu chí sắp xếp và tie-break.
4. In danh sách ID công việc sẵn sàng **đúng thứ tự nhập** và thu thập chúng thành List.

Chương trình Java 17+ có thể chạy độc lập:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class ParallelStreamOrderDemo {
    record Task(String id, int priority, boolean ready) {}

    public static void main(String[] args) {
        List<Task> tasks = List.of(
                new Task("T01", 5, false),
                new Task("T02", 2, true),
                new Task("T03", 9, true),
                new Task("T04", 7, false),
                new Task("T05", 9, true)
        );

        // 1. Chọn phần tử đầu trong List đáp ứng điều kiện.
        Task firstReady = tasks.parallelStream()
                .filter(Task::ready)
                .findFirst()
                .orElseThrow();
        System.out.println("First ready: " + firstReady.id());
        // First ready: T02

        // 2. Cho phép bất kỳ phần tử sẵn sàng nào.
        Optional<Task> anyReady = tasks.parallelStream()
                .filter(Task::ready)
                .findAny();

        anyReady.ifPresent(task ->
                System.out.println("Any ready: " + task.id()));
        // Có thể là T02, T03 hoặc T05.

        // 3. Chọn công việc ưu tiên cao nhất; tie-break theo ID tăng.
        Task highestPriority = tasks.parallelStream()
                .filter(Task::ready)
                .sorted(
                        Comparator.comparingInt(Task::priority)
                                .reversed()
                                .thenComparing(Task::id)
                )
                .findFirst()
                .orElseThrow();
        System.out.println("Highest priority: " + highestPriority.id());
        // Highest priority: T03

        // 4. forEachOrdered giữ thứ tự action trên nguồn List.
        System.out.println("Ready IDs in input order:");
        tasks.parallelStream()
                .filter(Task::ready)
                .map(Task::id)
                .forEachOrdered(System.out::println);
        // T02
        // T03
        // T05

        // 5. Thu thập List để sử dụng tiếp thay vì ghi vào List chung.
        List<String> readyIds = tasks.parallelStream()
                .filter(Task::ready)
                .map(Task::id)
                .toList();

        System.out.println(readyIds); // [T02, T03, T05]

        // 6. forEach không hứa thứ tự in.
        tasks.parallelStream()
                .filter(Task::ready)
                .map(Task::id)
                .forEach(id -> System.out.println("Unordered action: " + id));
        // Ba action được thực hiện, thứ tự không được cam kết.
    }
}
```

Phân tích hợp đồng:

1. `List.of(...)` tạo một nguồn có encounter order theo vị trí phần tử.
2. `filter(Task::ready)` giữ tương đối thứ tự của những công việc còn lại.
3. `findFirst` chọn `T02` một cách xác định từ nguồn đã có thứ tự; `findAny` chỉ bảo đảm chọn một trong các công việc sẵn sàng.
4. Bước `sorted` ở phần chọn độ ưu tiên cao nhất dùng độ ưu tiên giảm dần và ID tăng dần để xác định tie-break; vì `T03` và `T05` cùng độ ưu tiên 9, `T03` được chọn.
5. `forEachOrdered` in ID theo encounter order, dù các bước trung gian có thể được xử lý song song.
6. `toList` tạo một List kết quả có thứ tự; `forEach` không cam kết thứ tự in dù xử lý cùng dữ liệu.

Nếu danh sách công việc được lấy từ `HashSet` thay vì `List`, **thứ tự nhập không còn là hợp đồng của nguồn**. Khi đó yêu cầu "đầu tiên theo thứ tự nhập" phải được giải quyết bằng cách giữ một nguồn ordered hoặc lưu vị trí/thời gian nhập rồi sắp xếp có chủ đích.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `parallelStream().forEach(...)` in ngược hoặc lộn thứ tự | `forEach` không cam kết order của action | Dùng `forEachOrdered` khi nguồn có encounter order và action phải theo thứ tự |
| `findAny` chọn phần tử khác qua các lần chạy | Hợp đồng cho phép chọn bất kỳ phần tử phù hợp | Dùng `findFirst`/`min`/`max` nếu có tiêu chí lựa chọn |
| `findFirst` không trả "nhỏ nhất" | "Đầu tiên" không đồng nghĩa "nhỏ nhất" | Dùng `min` hoặc `sorted` với comparator đúng |
| `forEachOrdered` trên `HashSet` không cho thứ tự mong muốn | Nguồn không có encounter order | Chọn nguồn có thứ tự hoặc sắp xếp trước |
| Gọi `unordered()` rồi `findFirst` không ổn định | Pipeline đã bỏ ràng buộc order | Bỏ `unordered()` nếu cần đầu tiên theo nguồn |
| Các log trong `map` xuất hiện lộn xộn dù cuối dùng `forEachOrdered` | Chỉ terminal action được ràng buộc thứ tự | Không đặt tác dụng phụ bắt buộc trong mapper/peek |
| `ArrayList` bị thiếu phần tử khi `forEach(shared::add)` | Nhiều thread cùng thay đổi List không thread-safe | Sử dụng `toList`/`collect` hoặc container concurrent được thiết kế riêng |
| `counter++` cho số đếm sai | Race condition trên trạng thái chia sẻ | Dùng `count`, phép reduce hoặc `LongAdder` khi thật sự cần |
| `findFirst` trả `Optional.empty()` | Không có phần tử nào sau khi lọc | Dùng `ifPresent`, `orElse`, `orElseThrow` theo yêu cầu |
| `findFirst` ném `NullPointerException` | Phần tử được chọn là null | Xử lý null trước terminal operation |
| `findFirst` song song chậm hơn tuần tự | Cần phối hợp giữ encounter order, nguồn nhỏ hoặc chi phí quá thấp | Đo thực tế, cân nhắc `findAny` nếu nghiệp vụ cho phép |
| Không thể dùng lại Stream sau một terminal operation | Stream đã bị tiêu thụ | Tạo Stream mới từ nguồn cho phép duyệt lại |

## 17. Bài tập thực hành

Cho danh sách theo thứ tự nhập:

```java
record Job(String code, int duration, boolean eligible) {}

List<Job> jobs = List.of(
        new Job("J01", 5, false),
        new Job("J02", 7, true),
        new Job("J03", 3, true),
        new Job("J04", 9, false),
        new Job("J05", 3, true)
);
```

**Yêu cầu:**

1. Dùng `parallelStream`, `filter` và `findFirst` lấy job `eligible` đầu tiên theo thứ tự nhập.
2. Dùng `findAny` lấy một job `eligible` bất kỳ. Liệt kê các ID có thể nhận được thay vì dự đoán một ID cố định.
3. So sánh `forEach` và `forEachOrdered` khi in ID các job `eligible`.
4. Lấy job `eligible` có `duration` nhỏ nhất; nếu bằng nhau, chọn job có `code` nhỏ hơn.
5. Sau khi thêm `unordered()` trước `findFirst`, có còn bảo đảm chọn `J02` không? Giải thích.
6. Không dùng `forEach` để thêm vào một `ArrayList` chia sẻ. Hãy thu thập mã job `eligible` thành một List giữ thứ tự nhập.

### Lời giải tham khảo

```java
Job first = jobs.parallelStream()
        .filter(Job::eligible)
        .findFirst()
        .orElseThrow();
System.out.println(first.code()); // J02

Optional<Job> any = jobs.parallelStream()
        .filter(Job::eligible)
        .findAny();
// Có thể là J02, J03 hoặc J05.

jobs.parallelStream()
        .filter(Job::eligible)
        .map(Job::code)
        .forEach(System.out::println);
// Thứ tự in không được cam kết.

jobs.parallelStream()
        .filter(Job::eligible)
        .map(Job::code)
        .forEachOrdered(System.out::println);
// J02, J03, J05 theo thứ tự.

Job shortest = jobs.parallelStream()
        .filter(Job::eligible)
        .min(Comparator.comparingInt(Job::duration)
                .thenComparing(Job::code))
        .orElseThrow();
System.out.println(shortest.code()); // J03

List<String> orderedCodes = jobs.parallelStream()
        .filter(Job::eligible)
        .map(Job::code)
        .toList();
System.out.println(orderedCodes); // [J02, J03, J05]
```

`J03` và `J05` cùng có `duration == 3`; quy tắc tie-break theo `code` tăng dần chọn `J03`. `unordered()` làm mất cam kết về phần tử đầu tiên theo List, nên `findFirst` sau nó không nhất thiết chọn `J02`.

**Thử nghiệm mở rộng:** Gọi `findFirst` và `findAny` trên một `HashSet<Job>` rồi phân tích vì sao không được dựa vào thứ tự in của Set. Nếu muốn lựa chọn mang tính quyết định, hãy xác lập comparator và dùng `min`/`max` hoặc sắp xếp theo yêu cầu.

## 18. Checklist chọn thao tác kết thúc

Trước khi viết một pipeline song song, tự trả lời:

1. **Nguồn có encounter order không?** Nếu không, "đầu tiên" có thực sự được xác định?
2. **Cần một phần tử bất kỳ hay phần tử đầu tiên?** Chọn `findAny` hoặc `findFirst` theo đúng yêu cầu.
3. **Chỉ cần tồn tại phần tử phù hợp?** Ưu tiên `anyMatch` thay cho tìm rồi kiểm tra Optional.
4. **Cần hành động trên mọi phần tử?** Dùng `forEach` nếu các action độc lập và thứ tự không quan trọng.
5. **Cần thứ tự thực hiện action?** Dùng `forEachOrdered` với nguồn ordered, nhưng cân nhắc chi phí phối hợp.
6. **Cần một Collection kết quả?** Dùng `toList`, `collect` hoặc collector phù hợp thay cho mutable List bên ngoài.
7. **Lambda có sửa nguồn hoặc đọc/ghi trạng thái dùng chung không?** Loại tác dụng phụ không cần thiết và thiết kế xử lý thread-safe khi thật sự cần.
8. **Có gọi `unordered()` hoặc `sorted()` không?** Xác định lại ý nghĩa của "đầu tiên" và thứ tự trong pipeline.
9. **Nguồn có phần tử null hoặc có thể rỗng không?** Xử lý chính sách `Optional`/null rõ ràng.
10. **Có bằng chứng hiệu năng không?** So sánh tuần tự và song song với dữ liệu, terminal operation và nguồn thực tế; đừng dự đoán bằng tên phương thức.

## Ghi nhớ

Chế độ **song song** thay đổi cách công việc có thể được thực thi, nhưng không tự xóa **encounter order**. Trên Stream có thứ tự, `findFirst` chọn phần tử đầu tiên còn lại sau pipeline; `findAny` được phép chọn bất kỳ phần tử phù hợp. `forEach` không cam kết thứ tự action khi song song, còn `forEachOrdered` thực hiện action theo encounter order mà không bảo đảm mọi mapper trước đó chạy theo thứ tự ấy.

Không dùng `unordered()` khi nghiệp vụ cần thứ tự nguồn; không dùng `forEach(sharedList::add)` để thu thập dữ liệu vào cấu trúc mutable không thread-safe. Chọn `min`/`max` cho tiêu chí cực trị, `toList`/`collect` cho dữ liệu kết quả, `count`/`reduce` cho số tổng hợp. Giữ pipeline stateless, non-interfering và chỉ tối ưu song song sau khi đã chứng minh tính đúng đắn của kết quả.
