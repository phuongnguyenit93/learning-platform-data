# Đánh giá ngay và đánh giá trì hoãn trong Java

**Đánh giá ngay (eager evaluation)** là tính toán một biểu thức ngay khi chương trình đi tới vị trí cần giá trị của nó. **Đánh giá trì hoãn (lazy evaluation)** là hoãn phép tính cho đến khi có yêu cầu thực sự tiêu thụ kết quả. Đây là một khác biệt về **thời điểm thực thi**, không đơn thuần là cách viết ngắn hơn.

Trong lập trình hàm với Java, hai khái niệm này đặc biệt quan trọng khi xử lý `Stream`, `Supplier`, các toán tử logic có tính đoản mạch và phương thức chọn giá trị dự phòng của `Optional`.

Sau bài này, bạn có thể:
- Phân biệt biểu thức được tính ngay với công việc chỉ mới được mô tả.
- Dự đoán thời điểm chạy của `map`, `filter`, `limit`, `findFirst` và các thao tác kết thúc Stream.
- Chọn đúng `orElse` hay `orElseGet`, sử dụng `Supplier` để trì hoãn công việc.
- Nhận diện các rủi ro về side effect, ngoại lệ, tài nguyên, bộ nhớ và khả năng chạy lại.

## 1. Nền tảng: giá trị đã tính hay công việc sẽ tính?

Xét lời gọi phương thức thông thường:

```java
String result = normalize(loadText());
```

Java đánh giá đối số `loadText()` **trước** khi gọi `normalize(...)`. Nếu `loadText()` truy cập ổ đĩa hoặc ném ngoại lệ, việc đó xảy ra ngay tại dòng trên; `normalize` không thể quyết định bỏ qua việc tính đối số đã được truyền vào.

Muốn truyền **cách tạo ra kết quả** thay vì kết quả đã tạo, dùng hàm không đối số, chẳng hạn `Supplier<T>`:

```java
Supplier<String> pending = () -> loadText(); // chưa gọi loadText()
String result = normalize(pending.get());     // loadText() chạy tại get()
```

Hai đoạn trên là ví dụ minh họa cần có `loadText`, `normalize` và `import java.util.function.Supplier;` trong chương trình thực tế. Lambda chỉ giữ hành vi để thực hiện sau; chính `get()` mới kích hoạt.

Java **không** mặc định đánh giá trì hoãn mọi biểu thức. Ngay cả với lambda, các giá trị dùng để tạo đối tượng hoặc đối số truyền vào lambda vẫn có thể đã được tính trước. Chẳng hạn `() -> expensive()` trì hoãn lời gọi `expensive()`, còn `String s = expensive(); Supplier<String> f = () -> s;` thì không.

### Đoản mạch là một hình thức tránh đánh giá không cần thiết

```java
String name = null;
boolean valid = name != null && !name.isBlank();
```

Vế phải của `&&` không chạy nếu vế trái là `false`; tương tự, vế phải `||` không chạy nếu vế trái là `true`. Toán tử điều kiện `condition ? a : b` chỉ đánh giá một trong hai nhánh `a` hoặc `b` sau khi đánh giá `condition`. Đây là quy tắc ngôn ngữ Java, không phải tính chất riêng của Stream. Với `&` và `|` trên hai toán hạng `boolean`, cả hai vế đều được đánh giá: không được thay thế tùy tiện nếu vế phải có thể ném ngoại lệ hoặc có side effect.

## 2. Stream: khai báo pipeline trước, duyệt phần tử khi có terminal operation

Một pipeline Stream thường gồm:
1. **Nguồn**: `collection.stream()`, `Stream.of(...)`, `Files.lines(...)`...
2. **Thao tác trung gian (intermediate)**: `map`, `filter`, `distinct`, `sorted`, `peek`, `limit`... Chúng tạo một Stream mới mô tả thêm bước xử lý, thường chưa duyệt nguồn.
3. **Thao tác kết thúc (terminal)**: `toList`, `collect`, `forEach`, `reduce`, `count`, `findFirst`, `anyMatch`... Chúng kích hoạt việc xử lý cần thiết để tạo kết quả hoặc side effect được quy định.

Ví dụ đầy đủ chạy được trên Java 17+:

**Tệp: `EvaluationDemo.java`**

```java
import java.util.List;
import java.util.stream.Stream;

public class EvaluationDemo {
    private static int doubleValue(int value) {
        System.out.println("map " + value);
        return value * 2;
    }

    public static void main(String[] args) {
        System.out.println("A: tạo pipeline");
        Stream<Integer> pipeline = List.of(1, 2, 3, 4).stream()
                .map(EvaluationDemo::doubleValue)
                .filter(value -> {
                    System.out.println("filter " + value);
                    return value > 4;
                });

        System.out.println("B: chưa duyệt nguồn");
        int first = pipeline.findFirst().orElse(-1);
        System.out.println("C: kết quả = " + first);
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac -encoding UTF-8 EvaluationDemo.java
java EvaluationDemo
```

**Stdout chính xác:**

```text
A: tạo pipeline
B: chưa duyệt nguồn
map 1
filter 2
map 2
filter 4
map 3
filter 6
C: kết quả = 6
```

Giải thích theo thứ tự:
- Hai lời gọi `map(...)` và `filter(...)` chỉ dựng pipeline; chưa in `map`/`filter`.
- `findFirst()` cần tìm phần tử đầu tiên vượt qua `filter`, nên bắt đầu yêu cầu dữ liệu từ nguồn.
- Với **Stream tuần tự** này, phần tử 1 đi qua `map` rồi `filter`, tiếp đến phần tử 2, rồi phần tử 3. Đây thường là cách xử lý từng phần tử qua nhiều chặng, không phải luôn chạy hết `map` cho cả danh sách rồi mới `filter`.
- Sau khi thấy `3 * 2 = 6` đạt điều kiện, `findFirst` dừng. Phần tử 4 không bị xử lý, giúp tránh công việc thừa.
- `orElse(-1)` tại đây nhận hằng số đơn giản; `findFirst()` đã tạo `Optional<Integer>` và chỉ dùng `-1` nếu không tìm thấy giá trị.

**Quan trọng:** `Stream` không lưu sẵn kết quả trung gian như một danh sách mới sau mỗi bước. Tuy nhiên không phải thao tác nào cũng có thể phát ra kết quả ngay: các thao tác có trạng thái như `sorted`, một số trường hợp `distinct` hoặc `skip`, có thể cần tích lũy/traversal đáng kể. Cách tối ưu và số lần gọi lambda cũng có thể phụ thuộc nguồn, terminal operation và triển khai được phép theo đặc tả Stream.

## 3. Terminal operation quyết định cần thực hiện bao nhiêu công việc

Cùng một pipeline trung gian, terminal khác nhau có thể yêu cầu lượng xử lý khác nhau:

| Terminal | Nhu cầu xử lý |
| --- | --- |
| `findFirst()` | Có thể dừng ngay khi gặp phần tử đầu tiên phù hợp trong thứ tự encounter. |
| `anyMatch(predicate)` | Có thể dừng khi tìm thấy phần tử thỏa điều kiện. |
| `allMatch(predicate)` | Có thể dừng khi gặp phần tử không thỏa. |
| `limit(n).toList()` | Với pipeline phù hợp, có thể dừng sau khi tạo đủ `n` phần tử. |
| `toList()`, `collect(...)` | Thường cần duyệt toàn bộ phần tử đầu ra của nguồn hữu hạn. |
| `count()` | Có thể dùng thông tin kích thước của nguồn và bỏ qua một số bước trung gian không ảnh hưởng số lượng, tùy pipeline. |

Ví dụ ngắn:

```java
List<Integer> firstThree = java.util.stream.Stream.iterate(1, n -> n + 1)
        .filter(n -> n % 10 == 0)
        .limit(3)
        .toList();
// firstThree = [10, 20, 30]
```

Nguồn `iterate` này về nguyên tắc vô hạn; `limit(3)` cho phép `toList()` hoàn tất khi đủ ba phần tử chia hết cho 10. Nếu gọi `toList()` trên chính nguồn vô hạn mà không có điều kiện dừng thì phép tính không kết thúc bình thường. Đặt `sorted()` trước `limit` trên một luồng vô hạn cũng có thể khiến quá trình không bao giờ tạo được kết quả, vì `sorted` cần biết toàn bộ đầu vào trước khi xác định thứ tự hoàn chỉnh.

**Không suy luận số lần gọi lambda chỉ từ việc có terminal.** Ví dụ, đối với nguồn `SIZED`, `stream.map(f).count()` có thể không gọi `f`, vì `map` không thay đổi số phần tử. Vì vậy tuyệt đối không dùng side effect nằm trong `map` hoặc `peek` như công việc bắt buộc phải chạy. Khi cần side effect chủ đích, dùng terminal phù hợp như `forEach`, đồng thời hiểu quy tắc thứ tự và song song.

## 4. Supplier: trì hoãn giá trị, không tự động lưu kết quả

`Supplier<T>` là functional interface có phương thức `T get()`. Nó hữu ích khi công việc có thể bị bỏ qua, đắt đỏ, hoặc chỉ cần thực hiện tại thời điểm quyết định.

Ví dụ đầy đủ:

**Tệp: `FallbackDemo.java`**

```java
import java.util.Optional;
import java.util.function.Supplier;

public class FallbackDemo {
    private static String backup() {
        System.out.println("Tạo dữ liệu dự phòng");
        return "fallback";
    }

    public static void main(String[] args) {
        Optional<String> available = Optional.of("ready");

        System.out.println("orElse: " + available.orElse(backup()));
        System.out.println("orElseGet: " + available.orElseGet(FallbackDemo::backup));

        Supplier<String> pending = () -> {
            System.out.println("Chạy công việc");
            return "done";
        };

        System.out.println("Đã tạo Supplier");
        System.out.println("get: " + pending.get());

        Optional<String> missing = Optional.empty();
        System.out.println("empty: " + missing.orElseGet(FallbackDemo::backup));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FallbackDemo.java
java FallbackDemo
```

**Stdout chính xác:**

```text
Tạo dữ liệu dự phòng
orElse: ready
orElseGet: ready
Đã tạo Supplier
Chạy công việc
get: done
Tạo dữ liệu dự phòng
empty: fallback
```

Tại sao `backup()` được gọi ở dòng `orElse` dù `available` đã có giá trị? Vì Java phải đánh giá đối số của `orElse(T other)` **trước** khi gọi phương thức. Nó vẫn trả về `"ready"`, nhưng công việc tạo fallback đã xảy ra. Ngược lại, `orElseGet(Supplier<? extends T>)` chỉ gọi `get()` của Supplier nếu `Optional` rỗng. Với `Optional.empty()`, fallback mới thật sự cần.

Phân biệt các API:
- `optional.orElse(value)`: `value` đã được tính trước lời gọi.
- `optional.orElseGet(() -> create())`: trì hoãn tạo fallback đến khi rỗng.
- `optional.orElseThrow(() -> new IllegalStateException("missing"))`: trì hoãn tạo ngoại lệ đến khi rỗng.
- `optional.map(fn)`: `fn` chỉ được gọi khi `Optional` có phần tử; đây không phải Stream pipeline, mà là phép biến đổi ngay trên trạng thái Optional hiện tại.

**Lazy không đồng nghĩa memoization (ghi nhớ kết quả).** Mỗi lần gọi `pending.get()`, lambda ở ví dụ trên chạy lại. Nếu muốn chỉ thực hiện một lần rồi dùng lại, phải thiết kế bộ nhớ đệm riêng hoặc dùng API có hợp đồng caching phù hợp. Khi chia sẻ giữa nhiều thread, cơ chế khởi tạo một lần cần xử lý an toàn luồng; bản thân `Supplier` không bảo đảm điều đó.

## 5. Tác động thực tế: thời gian, ngoại lệ, side effect và tài nguyên

### Hiệu năng và bộ nhớ

Đánh giá trì hoãn có thể tránh tính toán không dùng tới, cho phép chạy pipeline trên nguồn lớn mà không cần dựng nhiều collection trung gian. Ví dụ, `filter(...).findFirst()` thường phù hợp hơn với nhu cầu tìm một phần tử so với việc tạo danh sách tất cả phần tử thỏa điều kiện rồi lấy phần tử đầu tiên.

Tuy nhiên lazy **không luôn nhanh hơn**: khởi tạo pipeline/lambda, boxing với `Stream<Integer>`, xử lý trạng thái như `sorted` và các bước kết thúc vẫn có chi phí. Hãy đo bằng benchmark hợp lý khi tối ưu, giữ ưu tiên cao cho tính đúng đắn. Với tính toán số nguyên lớn, có thể cân nhắc `IntStream` để tránh boxing.

### Thời điểm ném ngoại lệ

```java
Supplier<Integer> pending = () -> 10 / 0; // tạo lambda không ném lỗi
int result = pending.get();               // ArithmeticException tại đây
```

Tương tự, ngoại lệ xuất phát từ lambda `map` thường xảy ra lúc terminal operation thực sự xử lý phần tử đó. Nếu short-circuit bỏ qua phần tử gây lỗi, ngoại lệ có thể không xuất hiện. Điều này thay đổi điểm quan sát lỗi và thời điểm ghi log.

### Side effect và thứ tự

Một pipeline nên ưu tiên các hàm không sửa trạng thái bên ngoài. Đừng dựa vào việc `peek` luôn được gọi hoặc `map` luôn xử lý mọi phần tử. Nếu dùng `parallelStream()`, thứ tự và thread thực thi có thể khác pipeline tuần tự; `forEach` không bảo đảm encounter order, trong khi `forEachOrdered` tôn trọng thứ tự encounter nếu có. Side effect chia sẻ cần đồng bộ đúng cách; tốt hơn là ưu tiên phép biến đổi thuần và collector phù hợp.

### Nguồn có tài nguyên cần đóng

Stream tạo bởi `Files.lines(path)` dùng tài nguyên I/O và phải được đóng, dù thao tác trung gian là lazy:

```java
try (java.util.stream.Stream<String> lines =
             java.nio.file.Files.lines(path)) {
    java.util.Optional<String> match = lines
            .filter(line -> line.contains("ERROR"))
            .findFirst();
    // dùng match bên trong phạm vi tài nguyên còn mở
}
```

Đây là đoạn minh họa giả định biến `path` kiểu `java.nio.file.Path` đã được định nghĩa và ngoại lệ `IOException` đã được xử lý hoặc khai báo. Không trả về một Stream dựa trên tài nguyên đã đóng để thực thi sau.

## 6. Thiết kế pipeline đúng theo mục tiêu

Giả sử phải tìm bản ghi đầu tiên hợp lệ và chuyển đổi nó:

```java
java.util.Optional<String> result = names.stream()
        .filter(name -> name != null && !name.isBlank())
        .map(String::trim)
        .findFirst();
```

Đây là đoạn minh họa với `names` là `List<String>` đã tồn tại. Tính trì hoãn cho phép pipeline dừng khi tìm thấy kết quả. Thứ tự thao tác **có ý nghĩa**: đưa `map` xử lý rất đắt đỏ lên trước `filter` có thể tính thừa cho nhiều phần tử; nhưng chỉ đổi thứ tự khi việc đó giữ nguyên ngữ nghĩa. Chẳng hạn kiểm tra `isBlank()` trước/sau `trim()` cần được xem xét theo đặc tả nghiệp vụ và giá trị null.

Có thể tạo lại luồng sau khi tiêu thụ bằng cách lưu cách tạo nguồn:

```java
Supplier<java.util.stream.Stream<String>> source = names::stream;
long count = source.get().count();
java.util.List<String> copy = source.get().toList();
```

Mỗi `get()` tạo **Stream mới**, thay vì dùng lại một Stream đã có terminal operation. Với dữ liệu mutable, hai lần gọi có thể quan sát nội dung khác nhau nếu collection thay đổi giữa hai lần. Trường hợp chỉ có một Stream, gọi terminal lần thứ hai sẽ không hợp lệ (thường ném `IllegalStateException`).

### Bảng chọn nhanh

| Nhu cầu | Cách phù hợp | Lý do |
| --- | --- | --- |
| Cần tính đối số ngay để gọi hàm | Lời gọi Java thông thường | Giá trị được tạo trước khi gọi phương thức. |
| Fallback tính toán đắt, có thể không dùng | `Optional.orElseGet(...)` | Chỉ tạo fallback khi thiếu giá trị. |
| Truyền công việc để gọi về sau | `Supplier<T>` | Chưa tính trước `get()`; không tự cache. |
| Tìm một phần tử trên danh sách lớn | `stream().filter(...).findFirst()` | Có thể dừng sớm. |
| Biến đổi tất cả phần tử thành danh sách | `stream().map(...).toList()` | Terminal yêu cầu thu thập các phần tử đầu ra. |
| Kiểm tra điều kiện an toàn null | `x != null && predicate(x)` | Vế sau được bỏ qua nếu `x == null`. |
| Bắt buộc ghi side effect cho mọi phần tử | Dùng thiết kế duyệt rõ ràng, terminal phù hợp | Không dựa vào side effect trung gian có thể bị lược bỏ. |

## 7. Lỗi thường gặp và cách tự kiểm tra

1. **Nhầm việc dựng Stream với việc chạy Stream:** `map`/`filter` không thực thi ngay khi khai báo pipeline; đặt breakpoint/log ở cả trước và sau terminal để quan sát.
2. **Nhầm `orElse` là lazy:** truyền `expensive()` vào `orElse` vẫn gọi `expensive()`; dùng `orElseGet` khi cần trì hoãn.
3. **Trông chờ `peek` hoặc `map` luôn có side effect:** terminal có thể short-circuit hoặc tối ưu bỏ qua một số bước; tách side effect ra khỏi các phép biến đổi khi có thể.
4. **Dùng lại Stream đã tiêu thụ:** mỗi Stream chỉ phục vụ một chuỗi vận hành kết thúc; muốn duyệt lại hãy tạo một Stream mới.
5. **Cho rằng lazy tự cache kết quả:** gọi lại `Supplier.get()` có thể thực hiện lại công việc và phát sinh tác dụng phụ lần nữa.
6. **Bỏ quên terminal hoặc đóng tài nguyên:** pipeline không có terminal thì không có việc duyệt; Stream gắn với file phải được đóng bằng `try-with-resources`.
7. **Cho rằng `limit` luôn chặn được mọi công việc:** các thao tác như `sorted` ở phía trước `limit` có thể phải tiêu thụ toàn bộ nguồn.
8. **Suy luận thứ tự chạy từ Stream song song:** muốn kết quả có thứ tự cần hiểu encounter order và terminal tương ứng; không phụ thuộc thứ tự log nội bộ.

**Tự kiểm tra:**
- Với `Optional.of("A").orElse(expensive())`, `expensive()` có chạy không? **Có**: đối số được đánh giá ngay.
- Với `Optional.of("A").orElseGet(() -> expensive())`, có chạy không? **Không**: Optional đã có giá trị.
- Với pipeline tuần tự `Stream.of(1, 2, 3).filter(n -> n > 1).findFirst()`, kết quả là gì? **`Optional[2]`**; xử lý có thể dừng ở 2.
- `Supplier<T>` có bảo đảm chỉ tính một lần không? **Không**; cần cơ chế ghi nhớ kết quả riêng.
- Vì sao `map(...).count()` không thích hợp để bắt buộc ghi log từng phần tử? **Vì** `count` có thể dựa trên kích thước nguồn và bỏ qua việc gọi `map` nếu kết quả đếm không đổi.

Khi đọc code Java theo phong cách hàm, hãy đặt hai câu hỏi: **“Dòng này tạo ra giá trị hay chỉ mô tả cách tạo giá trị?”** và **“Thao tác nào buộc giá trị đó phải được tạo?”**. Trả lời đúng hai câu này giúp dự đoán hiệu năng, thời điểm ném lỗi và side effect của chương trình.
