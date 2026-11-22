# Stream xử lý từng phần tử thay vì chạy từng bước trên toàn bộ tập

## 1. Ý tưởng trung tâm: pipeline thay vì các vòng lặp xử lý theo chặng

Khi mới học `Stream API`, một cách hiểu dễ sai là Java luôn thực hiện **toàn bộ `filter` trên mọi phần tử trước, sau đó toàn bộ `map` trên các phần tử đã lọc**, như thể mỗi phép toán tạo ra ngay một danh sách trung gian.

Với **pipeline tuần tự** gồm các *intermediate operation* **không lưu trạng thái** (*stateless*) như `map` và `filter`, mô hình dễ hiểu hơn là:

**Một phần tử đi qua những phép toán liên tiếp trong pipeline, rồi Java mới tiếp tục phần tử kế tiếp khi terminal operation cần kết quả.**

Ví dụ:

```java
List<String> result = Stream.of("a", "bb", "ccc")
        .filter(s -> s.length() >= 2)
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [BB, CCC]
```

Một cách hình dung cho pipeline tuần tự này:

```text
"a"   -> filter(false) -> bỏ, không gọi map
"bb"  -> filter(true)  -> map("BB")  -> đưa xuống kết quả
"ccc" -> filter(true)  -> map("CCC") -> đưa xuống kết quả
```

**Không nhất thiết** có một danh sách tạm chứa tất cả phần tử sau `filter` trước khi `map` bắt đầu. Đặc điểm này thường được gọi là **pipeline fusion** hoặc **vertical processing** cho các phép toán stateless.

Tuy nhiên, đây là **mô hình giải thích hữu ích**, không phải lời hứa rằng *mọi* Stream pipeline đều xử lý toàn bộ một phần tử từ đầu tới cuối trước khi đụng phần tử tiếp theo. Các phép toán có lưu trạng thái như `sorted`, `distinct`, một số trường hợp `limit` và việc xử lý song song làm hành vi quan sát phức tạp hơn. Bài học sẽ phân biệt chính xác từng trường hợp.

## 2. Phân biệt nguồn, intermediate operation và terminal operation

Một Stream pipeline có ba phần:

1. **Nguồn dữ liệu:** `List.stream()`, `Stream.of(...)`, `IntStream.range(...)`, `Files.lines(...)`, v.v.
2. **Intermediate operations:** `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`... thường trả stream mới, tạo mô tả xử lý và có tính *lazy*.
3. **Terminal operation:** `toList`, `collect`, `sum`, `reduce`, `forEach`, `findFirst`, `anyMatch`... khởi phát quá trình tiêu thụ pipeline để tạo kết quả hoặc thực hiện hành động.

Ví dụ:

```java
List<Integer> selected = List.of(1, 2, 3, 4, 5)
        .stream()                 // Nguồn
        .filter(n -> n % 2 == 0)  // Intermediate: chỉ lấy số chẵn
        .map(n -> n * 10)         // Intermediate: biến đổi
        .toList();                // Terminal: thu thập

System.out.println(selected); // [20, 40]
```

`filter` và `map` **không lập tức xây xong hai danh sách trung gian** ở thời điểm gọi. Thực thi thực tế được điều phối khi terminal cần kết quả.

Cần lưu ý `List.of` chứa nguồn có encounter order, nên `toList` trả kết quả theo thứ tự của các phần tử còn lại: số 2 trước số 4.

### Lười không đồng nghĩa không bao giờ chạy

`lazy` không có nghĩa pipeline chỉ là lời hứa không thực hiện. Nó nghĩa là công việc được **trì hoãn đến khi có nhu cầu tiêu thụ**, cho phép hệ thống phối hợp các phép biến đổi và tránh xử lý phần tử không cần thiết trong nhiều tình huống.

```java
Stream<String> pipeline = Stream.of("a", "b", "c")
        .map(String::toUpperCase);

// Chưa có terminal operation nên chưa tạo List kết quả.
List<String> values = pipeline.toList(); // [A, B, C]
```

Một stream chỉ được tiêu thụ một lần; sau `toList()` không được gọi lại `pipeline.toList()` hoặc thêm nhánh xử lý trên cùng stream đã sử dụng. Nếu muốn tính nhiều kết quả, hãy tạo các stream mới từ nguồn có khả năng duyệt lại.

## 3. Hai cách xử lý khác nhau dù kết quả giống nhau

Giả sử có bốn sản phẩm, mỗi sản phẩm có giá gốc. Yêu cầu:

- Tăng mỗi giá lên 10.
- Chỉ giữ sản phẩm có giá sau khi tăng **ít nhất 100**.
- Tạo nhãn `code=price` cho sản phẩm đạt ngưỡng.

### Cách vòng lặp theo chặng (*stage by stage*)

```java
List<Item> adjusted = new ArrayList<>();
for (Item item : items) {
    adjusted.add(new Item(item.code(), item.price() + 10));
}

List<Item> accepted = new ArrayList<>();
for (Item item : adjusted) {
    if (item.price() >= 100) {
        accepted.add(item);
    }
}

List<String> labels = new ArrayList<>();
for (Item item : accepted) {
    labels.add(item.code() + "=" + item.price());
}
```

Đoạn này là **minh họa**, `Item`, `items` và các import được khai báo đầy đủ trong chương trình ở phần 5. Cách này xử lý:

```text
Tất cả Item -> tăng giá mọi Item
Tất cả Item đã tăng -> kiểm tra ngưỡng
Tất cả Item đạt ngưỡng -> tạo nhãn
```

Có hai danh sách `adjusted` và `accepted` tồn tại ở giữa, nếu người lập trình xây chúng như trên.

### Cách Stream tuần tự với các phép toán stateless

```java
List<String> labels = items.stream()
        .map(item -> new Item(item.code(), item.price() + 10))
        .filter(item -> item.price() >= 100)
        .map(item -> item.code() + "=" + item.price())
        .toList();
```

Pipeline giúp mô tả quy tắc trên cùng một chuỗi, và các phép `map`/`filter` có thể được phối hợp theo từng phần tử trong quá trình duyệt.

Luồng khái niệm:

```text
Item A -> tăng giá -> kiểm tra không đạt -> bỏ qua map tạo nhãn
Item B -> tăng giá -> kiểm tra đạt      -> tạo nhãn B=...
Item C -> tăng giá -> kiểm tra không đạt -> bỏ qua map tạo nhãn
Item D -> tăng giá -> kiểm tra đạt      -> tạo nhãn D=...
```

Cả hai cách **được thiết kế để trả cùng dữ liệu**, nhưng **thứ tự thực hiện các công đoạn** khác nhau. Sự khác biệt này còn có thể quan trọng khi thao tác có side effect, gặp lỗi hoặc terminal chỉ cần một phần dữ liệu.

## 4. Vì sao các phép `map` và `filter` dễ phối hợp theo từng phần tử?

`map` có đầu vào một phần tử và trả một giá trị mới. `filter` nhận một phần tử và quyết định giữ/bỏ nó. Trong trường hợp điển hình, cả hai đều là thao tác **stateless**: cách xử lý phần tử này không cần nhớ tất cả phần tử trước đó.

Ví dụ:

```java
Stream.of("A", "BB", "CCC")
        .map(String::length)
        .filter(length -> length >= 2)
        .forEachOrdered(System.out::println);
```

Stdout:

```text
2
3
```

Khi xét `"A"`, `map` cho 1, `filter` loại 1. Java không cần lưu kết quả 1 trong một danh sách trung gian để rồi mới lọc toàn bộ ở lần duyệt khác.

**Điều kiện quan trọng:** `map` và `filter` nên là các hàm không phụ thuộc vào việc các phần tử khác đang/đã được xử lý ra sao. Nếu mapper sửa trạng thái dùng chung hoặc phụ thuộc thứ tự chạy của nhiều phần tử, việc thực thi lazy, tối ưu hóa hoặc song song hóa có thể khiến hành vi khó đoán.

### Loại phần tử sớm làm giảm việc phía sau

```java
List<String> labels = Stream.of("A", "BBBB", "CC")
        .filter(s -> s.length() >= 3)
        .map(s -> "Accepted " + s)
        .toList();

System.out.println(labels); // [Accepted BBBB]
```

`map` chỉ cần xử lý `"BBBB"` vì hai chuỗi còn lại đã bị `filter` loại. Điều này thường giúp tránh thao tác chuyển đổi không cần thiết.

Tuy nhiên không nên suy diễn rằng chỉ cần đảo thứ tự `filter` và `map` là kết quả luôn giống nhau. Nếu `filter` dựa trên giá trị **đã biến đổi**, thứ tự là một phần ngữ nghĩa:

```java
List<Integer> afterMap = Stream.of(9, 10)
        .map(n -> n + 1)
        .filter(n -> n >= 11)
        .toList();
// [11]

List<Integer> beforeMap = Stream.of(9, 10)
        .filter(n -> n >= 11)
        .map(n -> n + 1)
        .toList();
// []
```

Hai pipeline khác kết quả vì điều kiện lọc nhận giá trị ở các thời điểm khác nhau. Chỉ thay đổi thứ tự phép toán khi đã chứng minh được phép biến đổi tương đương về mặt logic.

## 5. Chương trình Java 17 hoàn chỉnh: quan sát cách thực thi

Chương trình dưới đây cho cùng dữ liệu đi qua hai đường:

- Stream tuần tự với các `map`/`filter` stateless và một terminal.
- Các vòng `for` theo chặng, có danh sách trung gian.
- Pipeline lazy chưa có terminal.
- Terminal `findFirst` ngắn mạch.
- Phép toán `sorted` và kết quả của parallel stream có encounter order.

Các thông điệp trace trong ví dụ được dùng **có kiểm soát để học** cách triển khai đường xử lý tuần tự. Trong ứng dụng thật, không nên viết logic nghiệp vụ phụ thuộc vào side effect của intermediate operation, vì Stream API có quyền tối ưu/bỏ qua một số invocation khi kết quả không thay đổi.

Tạo tệp **`StreamExecutionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamExecutionDemo {
    record Item(String code, int price) {}

    static List<Item> sample() {
        return List.of(
                new Item("A", 40),
                new Item("B", 120),
                new Item("C", 80),
                new Item("D", 150)
        );
    }

    static List<String> withStream(
            List<Item> items, List<String> trace) {
        return items.stream()
                .map(item -> {
                    trace.add("adjust:" + item.code());
                    return new Item(
                            item.code(), item.price() + 10);
                })
                .filter(item -> {
                    trace.add("check:" + item.code());
                    return item.price() >= 100;
                })
                .map(item -> {
                    trace.add("label:" + item.code());
                    return item.code() + "=" + item.price();
                })
                .toList();
    }

    static List<String> withLoops(
            List<Item> items, List<String> trace) {
        List<Item> adjusted = new ArrayList<>();
        for (Item item : items) {
            trace.add("adjust:" + item.code());
            adjusted.add(new Item(
                    item.code(), item.price() + 10));
        }

        List<Item> accepted = new ArrayList<>();
        for (Item item : adjusted) {
            trace.add("check:" + item.code());
            if (item.price() >= 100) {
                accepted.add(item);
            }
        }

        List<String> labels = new ArrayList<>();
        for (Item item : accepted) {
            trace.add("label:" + item.code());
            labels.add(item.code() + "=" + item.price());
        }
        return labels;
    }

    public static void main(String[] args) {
        List<Item> items = sample();

        List<String> streamTrace = new ArrayList<>();
        List<String> streamResult = withStream(items, streamTrace);
        System.out.println("Stream trace: " + streamTrace);
        System.out.println("Stream result: " + streamResult);

        List<String> loopTrace = new ArrayList<>();
        List<String> loopResult = withLoops(items, loopTrace);
        System.out.println("Loop trace: " + loopTrace);
        System.out.println("Loop result: " + loopResult);

        // Tạo intermediate pipeline chưa kích hoạt xử lý.
        List<String> lazyTrace = new ArrayList<>();
        Stream<String> lazy = items.stream()
                .map(item -> {
                    lazyTrace.add("code:" + item.code());
                    return item.code();
                });
        System.out.println("Before terminal: " + lazyTrace);
        List<String> codes = lazy.toList();
        System.out.println("After terminal: " + lazyTrace);
        System.out.println("Codes: " + codes);

        // Terminal short-circuit chỉ yêu cầu phần tử đủ dùng.
        List<String> shortTrace = new ArrayList<>();
        Optional<Integer> firstEven = Stream.of(1, 2, 3, 4, 5)
                .filter(n -> {
                    shortTrace.add("test:" + n);
                    return n % 2 == 0;
                })
                .map(n -> {
                    shortTrace.add("transform:" + n);
                    return n * 10;
                })
                .findFirst();
        System.out.println("Short trace: " + shortTrace);
        System.out.println("First even x10: "
                + firstEven.orElse(-1));

        // sorted là phép có trạng thái: cần xét dữ liệu
        // từ nhiều phần tử để quyết định thứ tự.
        List<Integer> sorted = Stream.of(3, 1, 2)
                .sorted()
                .toList();
        System.out.println("Sorted: " + sorted);

        List<Integer> firstTwoEvens = IntStream.rangeClosed(1, 20)
                .filter(n -> n % 2 == 0)
                .limit(2)
                .boxed()
                .toList();
        System.out.println("First two evens: " + firstTwoEvens);

        // Kết quả có encounter order vẫn giữ thứ tự,
        // dù mapper trong parallel pipeline có thể chạy khác thứ tự.
        List<String> parallel = IntStream.rangeClosed(1, 4)
                .parallel()
                .mapToObj(n -> "X" + n)
                .toList();
        System.out.println("Parallel result: " + parallel);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 StreamExecutionDemo.java
java StreamExecutionDemo
```

**Stdout của chương trình với các stream tuần tự trong phần trace:**

```text
Stream trace: [adjust:A, check:A, adjust:B, check:B, label:B, adjust:C, check:C, adjust:D, check:D, label:D]
Stream result: [B=130, D=160]
Loop trace: [adjust:A, adjust:B, adjust:C, adjust:D, check:A, check:B, check:C, check:D, label:B, label:D]
Loop result: [B=130, D=160]
Before terminal: []
After terminal: [code:A, code:B, code:C, code:D]
Codes: [A, B, C, D]
Short trace: [test:1, test:2, transform:2]
First even x10: 20
Sorted: [1, 2, 3]
First two evens: [2, 4]
Parallel result: [X1, X2, X3, X4]
```

**Cách đọc và kiểm tra:**

- Với A, bước tăng giá tạo 50, sau đó `filter` thấy 50 nhỏ hơn 100 và loại; vì thế không có `label:A`.
- Với B, giá thành 130, qua `filter` rồi tạo nhãn `B=130`.
- Với C, giá thành 90 nên bị loại.
- Với D, giá thành 160 nên tạo nhãn `D=160`.
- Stream trace được tổ chức xen kẽ theo từng phần tử: `adjust:A, check:A` rồi đến B; còn trace vòng `for` có bốn lần `adjust` trước khi bước `check` nào được chạy.
- Hai kết quả đều là `[B=130, D=160]`. Thứ tự logic của các bước không thay đổi mục tiêu khi các phép chuyển đổi được định nghĩa nhất quán.
- `lazyTrace` rỗng trước terminal: mới xây pipeline thì chưa cần áp dụng `map`. Sau `toList`, bốn mã đã được tạo.
- `findFirst` trên Stream tuần tự chỉ cần số chẵn đầu tiên là 2: kiểm tra 1, kiểm tra 2, rồi biến đổi 2 thành 20. Nó không cần xét 3,4,5.
- `sorted` tạo `[1,2,3]` từ `3,1,2`; đây là ví dụ cho một thao tác không hoàn toàn mô tả được bằng ý tưởng “một phần tử qua hết mọi bước ngay”.
- `limit(2)` áp dụng sau `filter` nên lấy đúng hai số chẵn đầu `[2,4]`.
- `parallel` có thể xử lý các phần tử trên nhiều thread, nhưng `toList` giữ encounter order của nguồn `IntStream.rangeClosed`, nên kết quả vẫn là `[X1,X2,X3,X4]`.

> **Quan trọng về trace:** quy tắc nền tảng là kết quả của các phép toán Stream, không phải số lần/thứ tự thực thi tác dụng phụ tùy ý trong mọi intermediate operation. Với pipeline tuần tự stateless cụ thể ở trên, trace thể hiện cách Java xử lý xuyên qua các bước. Nhưng code sản xuất không nên phụ thuộc việc `map`, `filter` hay `peek` được gọi chính xác bao nhiêu lần trong mọi trường hợp tối ưu hóa.

## 6. Thao tác kết thúc mới khiến pipeline được thực thi

`Stream` sử dụng cơ chế lazy đối với phần lớn phép toán trung gian:

```java
Stream<Integer> pipeline = Stream.of(1, 2, 3)
        .map(n -> n * n)
        .filter(n -> n > 2);

// Chưa lấy danh sách hay in dữ liệu tại thời điểm khai báo.
List<Integer> result = pipeline.toList();
System.out.println(result); // [4, 9]
```

Lưu ý: việc gọi `map` trong đoạn đầu tạo một pipeline; `toList` mới yêu cầu kết quả.

Các terminal operation khác nhau có thể yêu cầu số phần tử khác nhau:

| Terminal | Mục tiêu | Có cần duyệt hết nguồn không? |
| --- | --- | --- |
| `toList()` | Thu thập các phần tử kết quả | Thường cần toàn bộ kết quả, trừ khi có giới hạn upstream |
| `collect(...)` | Thu thập/nhóm/tổng hợp | Phụ thuộc collector; thường xử lý hết các phần tử |
| `forEach(...)` | Thực hiện action | Thường duyệt hết phần tử còn lại |
| `sum()` trên primitive stream | Tính tổng | Thông thường cần tất cả phần tử |
| `findFirst()` | Lấy phần tử đầu theo encounter order | Có thể kết thúc sớm |
| `findAny()` | Lấy một phần tử bất kỳ | Có thể kết thúc sớm |
| `anyMatch(...)` | Có ít nhất một phần tử thỏa? | Có thể dừng khi tìm thấy true |
| `allMatch(...)` | Tất cả đều thỏa? | Có thể dừng khi tìm thấy false |
| `noneMatch(...)` | Không phần tử nào thỏa? | Có thể dừng khi tìm thấy true |
| `count()` | Đếm phần tử | Có thể được tối ưu từ kích thước nguồn mà không áp dụng mọi bước trung gian |

**Đặc biệt `count()`:** với một số nguồn đã biết kích thước và pipeline không làm thay đổi số phần tử, JDK có thể tính số lượng mà không đi qua mọi intermediate operation. Ví dụ không nên dùng một `map` chỉ để ghi log và mong `count` luôn gọi nó:

```java
long count = List.of("A", "B", "C").stream()
        .map(s -> {
            System.out.println("map " + s);
            return s;
        })
        .count();

System.out.println("Count: " + count);
```

`count` phải cho kết quả `3`, nhưng không nên khẳng định ba dòng `map A`, `map B`, `map C` chắc chắn được in. Đây là minh họa cho lý do **side effect trong intermediate operation không phải hợp đồng ứng dụng**.

## 7. Short-circuit: có thể dừng trước khi duyệt tất cả phần tử

Một lợi ích quan trọng của cách xây pipeline lazy là terminal không cần lúc nào cũng xử lý toàn bộ nguồn. Nếu chỉ cần biết “có phần tử phù hợp hay không”, `anyMatch` có thể dừng ngay khi gặp phần tử thỏa.

Ví dụ:

```java
boolean exists = Stream.of(1, 3, 4, 6)
        .map(n -> n * 2)
        .anyMatch(n -> n >= 8);

System.out.println(exists); // true
```

Giải thích trong stream tuần tự:

- Số 1 → 2, chưa đạt 8.
- Số 3 → 6, chưa đạt 8.
- Số 4 → 8, `anyMatch` thấy true và có thể dừng.
- Không cần biến đổi số 6.

Không nên dựa vào việc mọi mapper đã chạy như vòng lặp đầy đủ. Cũng không nên cho rằng `findAny` chọn phần tử đầu: `findAny` có thể trả bất kỳ phần tử nào, đặc biệt khi thực thi song song; dùng `findFirst` khi thứ tự đầu là yêu cầu.

### `filter` trước `limit`

```java
List<Integer> evens = IntStream.rangeClosed(1, 100)
        .filter(n -> n % 2 == 0)
        .limit(3)
        .boxed()
        .toList();

System.out.println(evens); // [2, 4, 6]
```

`limit(3)` đếm **các phần tử đã qua filter**, không phải ba số đầu của nguồn. Điều này minh họa thao tác phía sau có thể làm pipeline ngừng đòi thêm phần tử từ nguồn khi đã nhận đủ kết quả.

Đảo `limit` và `filter` cho kết quả khác:

```java
List<Integer> other = IntStream.rangeClosed(1, 100)
        .limit(3)
        .filter(n -> n % 2 == 0)
        .boxed()
        .toList();

System.out.println(other); // [2]
```

Giữ nguyên logic nghiệp vụ khi chọn thứ tự thao tác.

## 8. Stateful intermediate operation: khi cần xem nhiều phần tử

Mô hình “mỗi phần tử đi qua hết pipeline rồi đến phần tử kế” đúng nhất với chuỗi thao tác **stateless**. Một số phép toán cần trạng thái hoặc thông tin từ các phần tử khác.

### `sorted()`: thường cần biết tất cả dữ liệu trước khi phát kết quả

Để sắp xếp chính xác toàn bộ một stream hữu hạn theo comparator, `sorted` thường phải **tập hợp và sắp xếp các phần tử** trước khi downstream nhận kết quả đầu tiên. Ví dụ:

```java
List<Integer> result = Stream.of(3, 1, 2)
        .map(n -> n * 10)
        .sorted()
        .map(n -> n + 1)
        .toList();

System.out.println(result); // [11, 21, 31]
```

Một sơ đồ trực quan:

```text
Nguồn 3, 1, 2
  -> map(*10): 30, 10, 20
  -> sorted: phải quyết định thứ tự 10, 20, 30
  -> map(+1): 11, 21, 31
  -> toList
```

Không nên hình dung `3` có thể ngay lập tức đi tới `toList` trước khi biết liệu `1` hay `2` nhỏ hơn nó.

Một stream không giới hạn đặt trước `sorted().toList()` có thể không kết thúc, vì không có cách tổng quát sắp xếp hoàn toàn một dãy vô hạn theo tiêu chí thông thường rồi trả toàn bộ kết quả.

### `distinct()`: cần biết phần tử đã gặp

`distinct` dùng thông tin về các phần tử đã xuất hiện để loại trùng:

```java
List<String> unique = Stream.of("A", "B", "A", "C", "B")
        .distinct()
        .toList();

System.out.println(unique); // [A, B, C]
```

Nó có thể giữ trạng thái theo dõi những giá trị đã thấy. Vì thế `distinct` không giống `map` hay `filter` thuần túy xử lý từng phần tử độc lập với các phần tử khác. Trên ordered stream, `distinct` ổn định theo thứ tự gặp: giữ lần xuất hiện đầu tiên của mỗi giá trị.

Với dữ liệu lớn, nhất là parallel ordered stream, chi phí duy trì trạng thái và thứ tự của `distinct` có thể cao. Không suy ra Stream **luôn tiết kiệm bộ nhớ** hơn vòng lặp tự viết.

### `limit()` và `skip()`: trạng thái về số lượng

`limit(n)` đếm số phần tử đã được chấp nhận ở vị trí của nó trong pipeline và dừng sau n. `skip(n)` bỏ n phần tử đầu. Các thao tác này có trạng thái liên quan tới thứ tự/số lượng, dù thường không cần gom toàn bộ nguồn như `sorted`.

```java
List<Integer> result = IntStream.rangeClosed(1, 7)
        .skip(2)
        .limit(3)
        .boxed()
        .toList();

System.out.println(result); // [3, 4, 5]
```

Khi kết hợp `skip`/`limit` với parallel ordered stream, Java có thể cần phối hợp để bảo toàn đúng encounter order.

## 9. `flatMap()`: một phần tử đầu vào có thể sinh nhiều kết quả

`flatMap` không phải `map` một-đầu-vào-một-đầu-ra. Nó biến một phần tử cha thành **một stream con**, rồi nối các phần tử từ các stream con vào pipeline đầu ra.

```java
List<List<String>> groups = List.of(
        List.of("A", "B"),
        List.of(),
        List.of("C", "D")
);

List<String> flat = groups.stream()
        .flatMap(List::stream)
        .toList();

System.out.println(flat); // [A, B, C, D]
```

Trong stream tuần tự, có thể hình dung xử lý nhóm đầu, đưa A và B qua downstream, rồi nhóm rỗng phát không phần tử nào, cuối cùng nhóm C,D. Tuy nhiên mỗi phần tử cha có thể sinh 0, 1 hoặc nhiều phần tử con, nên không thể diễn đạt đơn giản rằng “mỗi phần tử đầu vào ứng với đúng một phần tử đầu ra”.

`flatMap` còn liên quan vòng đời các stream con; khi mapper tạo stream chứa tài nguyên như tệp, cần thiết kế quản lý I/O cẩn thận. Chỉ coi nó là một phép biến đổi thuần nếu chính mapper/nguồn con không thực hiện side effect nguy hiểm.

## 10. Stream tuần tự và Stream song song khác nhau

### Tuần tự: mô hình theo từng phần tử thường trực quan

`List.stream()` tạo stream tuần tự theo mặc định. Với nguồn ordered và các intermediate stateless đơn giản, một phần tử thường đi qua pipeline theo encounter order, như ví dụ `withStream`.

### Song song: có nhiều phần tử được xử lý đồng thời

`List.parallelStream()` hoặc `stream.parallel()` cho phép chia công việc giữa nhiều thread. Ví dụ:

```java
List<Integer> result = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(n -> n * 10)
        .boxed()
        .toList();

System.out.println(result); // [10, 20, 30, 40, 50]
```

`toList` giữ encounter order của nguồn `IntStream.rangeClosed`. Nhưng `map(n -> n * 10)` **không nhất thiết được gọi theo thứ tự n=1,2,3,4,5**, cũng không nhất thiết trên một thread.

Có ba loại thứ tự cần tách biệt:

1. **Encounter order:** thứ tự logic của phần tử từ nguồn hoặc được tạo bởi `sorted`.
2. **Execution order:** thứ tự thực tế các lambda được gọi; có thể thay đổi trong parallel pipeline.
3. **Result order:** thứ tự các phần tử kết quả của terminal có hợp đồng giữ encounter order, ví dụ `toList` từ nguồn ordered.

Không được lấy kết quả `[10,20,30,40,50]` làm bằng chứng rằng mọi phép nhân đã thực thi lần lượt theo thứ tự ấy.

### `forEach` khác `forEachOrdered`

`forEach` không đảm bảo hành động theo encounter order, đặc biệt trên parallel stream:

```java
IntStream.rangeClosed(1, 5)
        .parallel()
        .forEach(System.out::println);
```

Không có stdout cố định được bảo đảm cho đoạn này.

Nếu hành động ở cuối phải theo encounter order:

```java
IntStream.rangeClosed(1, 5)
        .parallel()
        .forEachOrdered(System.out::println);
```

Kết quả được bảo đảm về thứ tự hành động là:

```text
1
2
3
4
5
```

`forEachOrdered` không ép tất cả phép toán upstream trở thành tuần tự. Nó chỉ ràng buộc hành động terminal theo encounter order của stream.

## 11. Tại sao tránh side effect trong intermediate operation?

Dù ví dụ trace trong bài ghi vào `ArrayList` để minh họa, code sản xuất nên tránh phụ thuộc vào các hành động ngoài luồng trong `map`, `filter` hoặc `peek`.

Ví dụ nguy hiểm khi chạy song song:

```java
List<String> messages = new ArrayList<>();

// Phản ví dụ: ArrayList không thread-safe.
IntStream.rangeClosed(1, 1000)
        .parallel()
        .mapToObj(n -> {
            messages.add("N" + n);
            return "N" + n;
        })
        .toList();
```

Dù `toList()` giữ thứ tự kết quả, việc nhiều thread cùng gọi `messages.add(...)` có thể gây data race, thiếu phần tử hoặc hỏng dữ liệu. Không dùng một danh sách mutable bên ngoài để ghi log bắt buộc từ mapper song song.

Cách rõ ràng hơn:

```java
List<String> messages = IntStream.rangeClosed(1, 1000)
        .parallel()
        .mapToObj(n -> "N" + n)
        .toList();
```

Kết quả do Stream API thu thập, không cần tự cập nhật shared mutable list. Nếu có nhu cầu ghi database, audit, gửi message hoặc gọi API, tách giai đoạn tính dữ liệu khỏi giai đoạn xử lý side effect với một contract phù hợp, bao gồm retry/idempotency và quản lý lỗi.

### Không dựa vào `peek` để ép một bước chạy

`peek` thường hữu ích khi debug, nhưng là intermediate operation. Nếu downstream không đòi phần tử hoặc JDK có thể tối ưu mà không đổi kết quả, không được khẳng định `peek` luôn chạy một lần cho mọi phần tử.

```java
long count = List.of("a", "b", "c").stream()
        .peek(System.out::println)
        .count();

System.out.println("Count: " + count);
```

`Count: 3` là kết quả cần tin; việc có in a,b,c hay không không nên được đưa thành điều kiện đúng/sai của chương trình. Hành động bắt buộc phải chạy không nên bị giấu trong `peek`.

## 12. Ngoại lệ và việc dừng pipeline

Giả sử mapper ném ngoại lệ với phần tử thứ ba:

```java
List<Integer> values = List.of(1, 2, 3, 4);

try {
    values.stream()
            .map(n -> {
                if (n == 3) {
                    throw new IllegalArgumentException("bad 3");
                }
                return n * 10;
            })
            .forEachOrdered(System.out::println);
} catch (IllegalArgumentException ex) {
    System.out.println("Caught: " + ex.getMessage());
}
```

Với pipeline tuần tự và nguồn ordered ở đây, stdout:

```text
10
20
Caught: bad 3
```

Phần tử 4 không được in sau khi mapper của phần tử 3 ném. Các hành động đã xảy ra với 1 và 2 (in ra console) **không tự rollback**. Với pipeline song song, có thể có phần tử khác đang/đã được xử lý khi lỗi xuất hiện; không được dùng luồng xử lý parallel để giả định tất cả công việc sẽ dừng tức thời mà không tạo side effect.

Một exception trong `map` cũng có thể bị truyền qua pipeline khi terminal chạy, chứ không nhất thiết bị ném **ngay lúc viết câu lệnh `map(...)`**, bởi việc đánh giá mapper là lazy.

## 13. Tối ưu hóa: không đồng nghĩa mọi phép toán luôn gọi đúng một lần

Stream API bảo đảm **ngữ nghĩa kết quả** của pipeline theo các contract của nguồn, intermediate và terminal operation. Nó có thể thực hiện tối ưu hóa hợp lệ như bỏ qua những bước không ảnh hưởng đến kết quả.

Vì vậy, những phát biểu sau **không đúng trong mọi trường hợp**:

- “Mỗi phần tử nguồn luôn đi qua đúng một lần mọi phép toán.”
- “Mọi phần tử đều chạy `map` rồi mới chạy `filter`.”
- “Chỉ cần tạo stream là mapper đã thực thi.”
- “`count` luôn gọi `map` trên từng phần tử.”
- “Parallel stream vẫn chạy mapper theo encounter order.”
- “Đặt `sorted` giữa pipeline vẫn xử lý xong từng phần tử ngay trước khi chuyển sang phần tử kế.”
- “Dùng `forEachOrdered` là tất cả bước trước nó đều chạy tuần tự.”

Mô hình đúng là: Stream **đánh giá lazy**, phối hợp các phép toán khi terminal yêu cầu kết quả, có thể **fuse** các thao tác stateless theo phần tử, nhưng cũng có thể **lưu trạng thái, short-circuit, tối ưu hóa hoặc song song hóa** theo quy tắc của pipeline.

### Có phải luôn tiết kiệm bộ nhớ hơn vòng lặp?

Không. Với các phép `map`/`filter` stateless, Stream thường tránh xây các danh sách trung gian mà người lập trình có thể đã tạo trong cách xử lý theo chặng. Nhưng:

- `sorted` có thể phải đệm nhiều phần tử để sắp xếp.
- `distinct` cần giữ dấu vết các giá trị đã gặp.
- `toList` vẫn cần chứa kết quả cuối trong bộ nhớ.
- `flatMap` có thể tạo các stream con và có chi phí riêng.
- Parallel stream có thêm chi phí phối hợp, phân tách nguồn và hợp nhất kết quả.

Nên chọn cách viết theo **độ rõ ràng, tính đúng đắn và ràng buộc hiệu năng thực tế**. Đừng tuyên bố Stream luôn nhanh hoặc luôn ít bộ nhớ hơn mọi vòng `for`; với yêu cầu hiệu năng, cần benchmark trên dữ liệu và JDK đại diện.

## 14. Stream nguồn vô hạn và giới hạn kết thúc

Ví dụ `Stream.iterate(1, n -> n + 1)` có nguồn về nguyên tắc không giới hạn. Nếu bạn gọi `toList` mà không có điểm dừng, pipeline có thể không hoàn tất và tiêu tốn tài nguyên:

```java
// KHÔNG CHẠY: thiếu điểm dừng cho nguồn không giới hạn.
// Stream.iterate(1, n -> n + 1).toList();
```

Có thể thêm `limit`:

```java
List<Integer> values = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(values); // [1, 2, 3, 4, 5]
```

Hoặc dùng overload Java 9+ với predicate:

```java
List<Integer> values = Stream.iterate(
        1,
        n -> n <= 5,
        n -> n + 1
).toList();

System.out.println(values); // [1, 2, 3, 4, 5]
```

Hai đoạn ở trên là **hai phương án độc lập** với cùng tên biến `values`; không ghép trong một scope mà không đổi tên. Điểm cần nhớ là một pipeline lazy vẫn có thể **không kết thúc** nếu terminal phải duyệt một nguồn không giới hạn và không có điều kiện dừng.

`filter` đơn thuần không khiến một nguồn vô hạn kết thúc: nó loại phần tử không thỏa chứ không đánh dấu điểm dừng. `takeWhile` hoặc `limit` mới là những thao tác phù hợp khi logic dừng cho phép.

## 15. So sánh pipeline theo từng phần tử và xử lý theo chặng

| Tiêu chí | Pipeline Stream stateless tuần tự | Vòng lặp theo chặng có danh sách tạm |
| --- | --- | --- |
| Cách biểu đạt | Chuỗi `filter`/`map`/terminal | Nhiều vòng `for` và các danh sách trung gian |
| Khi thực thi | Thường phối hợp theo từng phần tử | Một chặng hoàn thành trên cả tập rồi mới sang chặng sau |
| Khi tính toán bắt đầu | Khi terminal tiêu thụ | Ngay lúc vòng lặp được gọi |
| Danh sách trung gian | Không bắt buộc tạo cho mỗi phép stateless | Do code chủ động tạo |
| Dừng sớm | `findFirst`/`anyMatch`/`limit` hỗ trợ | Phải viết logic `break`/`return` rõ |
| Thứ tự bước | Theo thứ tự các phép toán trong pipeline | Theo thứ tự các vòng lặp riêng |
| Stateful/short circuit | Cần phân tích riêng | Thể hiện qua code tự viết |
| Đồng thời | `parallel()` có thể phân công nhiều thread | Vòng lặp thường tuần tự nếu không tự song song hóa |
| Tác dụng phụ | Nên hạn chế trong intermediate operations | Có thể kiểm soát tường minh nhưng vẫn cần quản lý |
| Tối ưu hóa | Thư viện/JVM có quyền phối hợp và bỏ qua bước hợp lệ | Người viết kiểm soát cấu trúc và vòng lặp |

**Không nhất thiết** Stream tốt hơn vòng lặp trong mọi trường hợp. Vòng `for` có thể phù hợp hơn khi có trạng thái tiến hóa phức tạp, cần dừng/tiếp tục với nhiều nhánh logic hoặc thực hiện I/O cần kiểm soát cẩn thận. Stream phù hợp khi xử lý tập dữ liệu có thể diễn đạt rõ bằng chuỗi các phép biến đổi, lọc và thu thập.

## 16. Lỗi phổ biến

| Sai lầm | Vấn đề | Sửa thế nào |
| --- | --- | --- |
| Nghĩ `filter` tạo danh sách trước khi `map` chạy | Không đúng với mô hình lazy/stateless điển hình | Hiểu pipeline được tiêu thụ khi terminal yêu cầu |
| Nghĩ pipeline luôn chạy từng bước trên toàn bộ tập | Không phải cách điển hình với stateless operations | Vẽ luồng đi qua từng phần tử |
| Nghĩ luôn xử lý trọn một phần tử qua mọi operation | `sorted`/`distinct`/parallel/short circuit làm phức tạp | Phân biệt stateless và stateful |
| Mong code trong `map` chạy ngay lúc khai báo | Intermediate thường lazy | Thêm terminal phù hợp |
| Dùng lại stream sau terminal | Stream chỉ tiêu thụ một lần | Tạo stream mới |
| Đổi `filter` và `map` tùy ý | Có thể thay giá trị mà predicate thấy | Kiểm chứng tương đương về logic |
| Cho rằng `count` bắt buộc gọi mọi `peek`/`map` | Có thể tối ưu không cần chạy các phép đó | Không dựa side effect ở intermediate |
| Dùng `peek` để audit bắt buộc | Số lần thực thi không là hợp đồng chắc chắn | Đặt audit ở ranh giới chuyên trách |
| `parallel()` rồi thêm vào `ArrayList` ngoài | Race, thứ tự execution không xác định | Dùng collector/toList hoặc đồng bộ hợp lý |
| Mong `findAny` là phần tử đầu | Có thể trả phần tử bất kỳ | Dùng `findFirst` nếu cần encounter order |
| Dùng `sorted` trên nguồn vô hạn rồi `toList` | Có thể không kết thúc/đệm vô hạn | Giới hạn nguồn trước khi cần sort |
| Nghĩ Stream luôn giảm bộ nhớ | Stateful operations và terminal vẫn có bộ đệm | Phân tích pipeline, đo hiệu năng |
| Bỏ qua side effect trước exception | Không có rollback tự động | Thiết kế transaction/idempotency/compensation |

## 17. Bài tập thực hành

1. Với `Stream.of("a","bb","ccc").filter(s -> s.length() >= 2).map(String::toUpperCase).toList()`, hãy vẽ đường đi qua các bước của từng phần tử. Kết quả cuối là gì?
2. Viết ba vòng `for` để tăng giá, lọc theo ngưỡng, tạo nhãn cho `Item`. Sau đó thay bằng một Stream pipeline. So sánh số danh sách trung gian.
3. Trong `StreamExecutionDemo`, vì sao trace của Stream bắt đầu `adjust:A, check:A, adjust:B` nhưng trace vòng `for` bắt đầu `adjust:A, adjust:B, adjust:C`?
4. Dự đoán `Stream.of(9,10).map(n -> n+1).filter(n -> n>=11).toList()` và pipeline đảo `filter`/`map`. Giải thích khác biệt.
5. Tạo pipeline có `map` rồi `filter`, nhưng chưa gọi terminal. Viết code kiểm tra một biến trace còn rỗng; sau đó dùng `toList` và quan sát kết quả trong luồng tuần tự.
6. Cho `Stream.of(1,2,3,4,5).filter(n -> n%2==0).map(n -> n*10).findFirst()`. Giải thích tại sao không cần xử lý 3,4,5 trong pipeline tuần tự.
7. Dùng `IntStream.rangeClosed(1,100).filter(n -> n%2==0).limit(3)`. So sánh với phiên bản `limit(3).filter(...)`.
8. Giải thích tại sao `sorted` có thể cần thu thập nhiều phần tử, trong khi `map` và `filter` không nhất thiết cần toàn bộ nguồn.
9. Viết `Stream.of("A","B","A").distinct().toList()`. Vì sao `distinct` cần nhớ giá trị đã gặp?
10. Cho `IntStream.rangeClosed(1,5).parallel().map(n -> n*2).boxed().toList()`, xác định thứ tự kết quả và phân biệt với thứ tự thread gọi mapper.
11. Chạy `List.of("A","B","C").stream().peek(System.out::println).count()` rồi giải thích vì sao không được coi số dòng log là contract.
12. Thiết kế một unit test cho tính đúng đắn của pipeline mà **không** phụ thuộc vào số lần/thứ tự side effect trong intermediate operations.
13. Khi nào vòng `for` trực tiếp sẽ dễ hiểu hơn Stream? Nêu một trường hợp có tài nguyên I/O hoặc nhiều nhánh xử lý lỗi.
14. Với nguồn `Stream.iterate(1,n -> n+1)`, dùng `limit(5)` hoặc predicate Java 9+ để đảm bảo terminal `toList` kết thúc.
15. Với `parallelStream` và `forEachOrdered`, giải thích vì sao thứ tự action cuối được đảm bảo nhưng không được suy diễn tất cả thao tác upstream đều tuần tự.

## 18. Checklist tự kiểm tra khi đọc pipeline

- Đã xác định **nguồn**, **intermediate operations**, **terminal operation** chưa?
- Trước khi terminal chạy, có phép toán trung gian nào thực sự cần tính ngay không?
- Mỗi phép toán **stateless** hay **stateful**? Có `sorted`, `distinct`, `skip` hoặc `limit` không?
- Có thao tác **short-circuit** khiến pipeline không cần mọi phần tử không?
- Có đang hiểu nhầm “thứ tự các phép toán” với “thực hiện xong một phép trên toàn bộ tập” không?
- Có phụ thuộc vào **side effect** của `map`, `filter`, `peek` hoặc thread scheduling không?
- Nguồn có encounter order không? Kết quả cần giữ thứ tự hay có thể unordered?
- Pipeline chạy **sequential** hay **parallel**? Nếu parallel, đã bảo vệ shared mutable state chưa?
- Có nguy cơ source vô hạn nhưng terminal đòi toàn bộ dữ liệu không?
- Đã test cả dữ liệu không thỏa filter, dữ liệu rỗng, dừng sớm và thao tác stateful chưa?

**Ghi nhớ:** Với pipeline Stream tuần tự gồm các phép toán **stateless**, Java thường xử lý phần tử bằng cách đưa nó qua các bước liên tiếp theo nhu cầu của terminal, **không phải** mặc định hoàn thành một bước trên cả tập trước khi chạy bước sau. Tính lazy giúp kết hợp thao tác và dừng sớm. Nhưng `sorted`, `distinct`, `limit`, terminal tối ưu hóa và `parallel()` tạo những ngoại lệ quan trọng cho mô hình đơn giản này. Hãy dựa vào **ngữ nghĩa kết quả** của Stream API, không dựa vào thứ tự side effect trong các intermediate operation.
