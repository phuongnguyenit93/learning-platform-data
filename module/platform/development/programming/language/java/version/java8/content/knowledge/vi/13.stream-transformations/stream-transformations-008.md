# Stream.peek(): quan sát luồng xử lý và giới hạn sử dụng

`Stream.peek(Consumer<? super T> action)` xuất hiện từ Java 8 và vẫn là API hiện hành của `java.util.stream.Stream`. Đây là **phép toán trung gian (intermediate operation)** dùng chủ yếu để **quan sát phần tử khi chúng đi qua một vị trí trong pipeline**: in thông tin debug, ghi dấu một bước xử lý hoặc kiểm tra một giả định khi phát triển. `peek` không phải công cụ biến đổi dữ liệu, không phải một điểm móc sự kiện được bảo đảm chạy cho mọi phần tử và không phải nơi đặt logic nghiệp vụ có tác dụng phụ bắt buộc.

## 1. Bản chất và hợp đồng API

Chữ ký phương thức:

~~~java
Stream<T> peek(Consumer<? super T> action)
~~~

- `action` là một `Consumer`: nhận phần tử và thực hiện hành động, không trả về giá trị mới.
- Kết quả của `peek` là một `Stream<T>` chứa **chính các phần tử đang đi qua**; `peek` không đổi kiểu, không thêm/bớt phần tử và không tự biến đổi giá trị của chúng.
- `peek` **lazy**: khi chỉ khai báo pipeline, callback chưa cần chạy. Việc xử lý thường bắt đầu khi có terminal operation, ví dụ `toList()`, `collect(...)`, `forEach(...)`, `findFirst()` hoặc `count()`.
- Khi pipeline thực sự duyệt một phần tử qua vị trí `peek`, callback có thể được gọi để quan sát phần tử tại vị trí ấy. Tuy nhiên, **không có bảo đảm callback sẽ được gọi cho mọi phần tử nguồn**: short-circuit và tối ưu hóa có thể bỏ qua một phần hoặc toàn bộ callback.
- `action` phải **non-interfering**: không sửa nguồn Stream trong lúc pipeline đang chạy. Tránh phụ thuộc vào trạng thái biến đổi được chia sẻ, nhất là khi pipeline chạy song song.

So sánh nhanh các phép toán thường gặp:

| Phép toán | Vai trò | Điều cần nhớ |
|---|---|---|
| `map(x -> f(x))` | Biến đổi phần tử thành giá trị khác | Dùng khi thực sự cần giá trị mới |
| `filter(x -> test(x))` | Giữ lại phần tử đạt điều kiện | Dùng khi cần quyết định phần tử nào được đi tiếp |
| `peek(x -> log(x))` | Quan sát phần tử đi qua một giai đoạn | Hữu ích để debug; callback không được bảo đảm luôn chạy |
| `forEach(action)` | Terminal operation thực hiện hành động trên phần tử được duyệt | Dùng khi mục tiêu cuối là tác dụng phụ có chủ đích; lưu ý thứ tự và an toàn luồng |

**Mô hình tư duy:** `peek` giống một cửa sổ quan sát đặt giữa các bước, không phải một trạm bắt buộc mà mọi phần tử nhất định phải đi qua.

## 2. Ví dụ chạy được: quan sát trước và sau `filter`

Tạo tệp `PeekDemo.java` (JDK 17 trở lên):

~~~java
import java.util.List;

public class PeekDemo {
    public static void main(String[] args) {
        List<String> input = List.of("  java  ", "   ", " stream ");

        List<String> result = input.stream()
                .map(String::trim)
                .peek(value -> System.out.println("Sau trim: [" + value + "]"))
                .filter(value -> !value.isEmpty())
                .peek(value -> System.out.println("Qua filter: [" + value + "]"))
                .map(String::toUpperCase)
                .toList();

        System.out.println("Kết quả: " + result);
    }
}
~~~

Biên dịch và chạy:

~~~text
javac -encoding UTF-8 PeekDemo.java
java PeekDemo
~~~

Kết quả với pipeline tuần tự này:

~~~text
Sau trim: [java]
Qua filter: [java]
Sau trim: []
Sau trim: [stream]
Qua filter: [stream]
Kết quả: [JAVA, STREAM]
~~~

**Đọc kết quả từng bước:**

1. `map(String::trim)` tạo chuỗi đã bỏ khoảng trắng đầu/cuối, nên `peek` thứ nhất thấy `java`, chuỗi rỗng rồi `stream`.
2. `filter(value -> !value.isEmpty())` chặn chuỗi rỗng, nên `peek` thứ hai chỉ thấy `java` và `stream`.
3. `map(String::toUpperCase)` mới là bước chuyển đổi dữ liệu thành chữ hoa. `peek` chỉ in nội dung; xóa cả hai `peek` thì danh sách kết quả vẫn là `[JAVA, STREAM]`.
4. Trong pipeline tuần tự gồm các bước stateless ở đây, các bước được thực hiện theo luồng từng phần tử, nên log của hai `peek` xen kẽ. **Không được mở rộng quan sát này thành bảo đảm về thứ tự callback trong mọi pipeline**, đặc biệt khi có `parallel()` hoặc các bước như `sorted()`.

`List.of(...)` được bổ sung từ Java 9 và `Stream.toList()` từ Java 16; chúng đang được dùng vì ví dụ chạy trên JDK 17+. Riêng `peek`, `map`, `filter` và nguyên lý được giải thích ở đây đều có từ Java 8. Nếu dự án cần biên dịch bằng Java 8, thay `List.of(...)` bằng `Arrays.asList(...)` và `toList()` bằng `collect(Collectors.toList())`; không cần thay `peek`.

## 3. Lazy: khai báo `peek` không đồng nghĩa với thực thi

Xét đoạn mã sau đặt trong `main`:

~~~java
var pipeline = java.util.stream.Stream.of("A", "B")
        .peek(value -> System.out.println("peek: " + value));

System.out.println("Đã tạo pipeline");
pipeline.forEach(value -> System.out.println("forEach: " + value));
~~~

Với Stream tuần tự, đầu ra là:

~~~text
Đã tạo pipeline
peek: A
forEach: A
peek: B
forEach: B
~~~

Dòng đầu xuất hiện trước các dòng `peek` vì lúc tạo pipeline chưa có terminal operation. `forEach` kích hoạt việc duyệt; từng phần tử đi qua `peek` trước khi vào hành động ở `forEach`. Không thể dùng lại biến `pipeline` cho một terminal operation khác sau khi đã tiêu thụ Stream; cần tạo Stream mới từ nguồn nếu muốn chạy lại.

Điều này còn giải thích vì sao đặt breakpoint hoặc `println` trong `peek` mà không thấy gì **chưa chắc là lỗi**: có thể chưa gọi terminal operation, hoặc phần tử đó không được pipeline yêu cầu tính đến.

## 4. Các giới hạn quan trọng khi quan sát

### 4.1. `count()` có thể tối ưu bỏ qua toàn bộ `peek`

Đoạn mã sau đặt trong `main`:

~~~java
long total = java.util.List.of("A", "B", "C").stream()
        .peek(value -> System.out.println("Đang quan sát: " + value))
        .count();

System.out.println("Tổng = " + total);
~~~

`total` bằng `3`. Tuy nhiên, **không có cam kết** sẽ xuất hiện các dòng `Đang quan sát: ...`. Nguồn `List` đã biết kích thước và `peek` không thay đổi số phần tử; một Stream implementation có thể tính trực tiếp `count()` mà không duyệt phần tử, nên không gọi `peek`. Đây là ví dụ được nêu ngay trong tài liệu API `Stream.count()` hiện hành.

Hệ quả: **không dùng `peek` để cập nhật bộ đếm chính xác, ghi audit bắt buộc, thanh toán, đồng bộ dữ liệu hay gửi thông điệp quan trọng**. Nếu kết quả cần là số phần tử, dùng trực tiếp `count()`. Nếu cần một hành động bảo đảm trên các phần tử được terminal operation xử lý, thiết kế nó ở bước xử lý thích hợp thay vì phụ thuộc vào tác dụng phụ của intermediate operation.

### 4.2. Short-circuit chỉ xử lý phần tử cần thiết

Các terminal operation như `findFirst()`, `findAny()`, `anyMatch()`, `allMatch()`, `noneMatch()` có thể kết thúc sớm. `limit(n)` cũng giới hạn số phần tử cần chuyển đến phần sau của pipeline.

~~~java
boolean found = java.util.stream.Stream.of(8, 3, 5)
        .peek(value -> System.out.println("Đã nhìn thấy: " + value))
        .anyMatch(value -> value % 2 == 0);

System.out.println("found = " + found);
~~~

Ở pipeline **tuần tự** trên, `8` là số chẵn đầu tiên, nên `anyMatch` có thể kết thúc ngay với `found = true` và không cần quan sát `3`, `5`. Đừng suy số phần tử nguồn từ số dòng log. Với pipeline song song, các phần tử được yêu cầu tính và thời điểm callback chạy còn có thể khác.

Vị trí `peek` cũng quan trọng:

~~~java
stream.filter(predicate).peek(logger);  // Quan sát các phần tử vượt qua filter.
stream.peek(logger).filter(predicate);  // Quan sát ở vị trí trước filter.
~~~

Hai dòng là **mẫu minh họa**, không phải chương trình chạy độc lập: `stream`, `predicate`, `logger` cần được định nghĩa trong ứng dụng. Ngay cả `peek` đặt trước một bước short-circuit cũng không trở thành lời hứa quan sát hết nguồn.

### 4.3. Parallel Stream không bảo đảm thứ tự hoặc luồng chạy của callback

~~~java
java.util.stream.IntStream.rangeClosed(1, 6)
        .parallel()
        .peek(value -> System.out.printf(
                "%s -> %d%n", Thread.currentThread().getName(), value))
        .sum();
~~~

Đây là đoạn mã đặt trong `main` để **khám phá**, không có stdout cố định: khi chạy song song, callback có thể chạy vào những lúc khác nhau và trên những thread khác nhau. Thứ tự dòng log không nhất thiết là `1, 2, 3, 4, 5, 6`. Ngay cả khi terminal operation tạo kết quả có thứ tự encounter order, **thứ tự tác dụng phụ trong `peek` vẫn không được bảo đảm**.

Nếu cần terminal action theo encounter order của nguồn có thứ tự, `forEachOrdered` là công cụ phù hợp hơn `forEach`; điều đó **không biến log trong `peek` thành log có thứ tự**. Với trạng thái dùng chung, phải xem xét an toàn luồng và chi phí đồng bộ; lựa chọn tốt hơn thường là tránh side effect trong pipeline.

### 4.4. Tối ưu hóa và thao tác stateful làm log khó suy diễn

`sorted()` có thể cần giữ các phần tử trước khi phát ra kết quả; `distinct()` thay đổi phần tử được truyền tiếp. Vì vậy log `peek` đặt **trước** và **sau** các bước ấy có thể phản ánh hai tập/thứ tự khác nhau. Ở pipeline song song, kể cả khi kết quả cuối đúng, không được suy ra thứ tự tính toán từ thứ tự dòng in.

Tài liệu Stream hiện hành cho phép bỏ qua cả bước trung gian khi việc bỏ qua không làm đổi **kết quả tính toán**. Side effect của `peek` không được xem là kết quả cần bảo toàn. Không nên viết logic dựa trên giả định “mỗi phần tử nguồn sẽ gọi `peek` đúng một lần”.

## 5. Không dùng `peek` để sửa dữ liệu nguồn hoặc biến đổi đối tượng

**Sai về mục đích thiết kế:**

~~~java
// Mẫu phản ví dụ; không đưa vào logic ứng dụng.
List<String> names = new ArrayList<>(List.of("Ana", "Binh"));
names.stream()
        .peek(names::remove) // Sửa chính nguồn đang duyệt: vi phạm non-interference.
        .forEach(System.out::println);
~~~

Đoạn trên chỉ minh họa lỗi, **không phải ví dụ nên chạy**. Thay đổi nguồn không đồng thời trong lúc duyệt có thể khiến kết quả sai, gặp `ConcurrentModificationException` hoặc hành vi không phù hợp hợp đồng Stream.

Ngay cả khi không sửa danh sách, việc gọi `peek(person -> person.setActive(true))` để thay đổi trạng thái đối tượng đi qua Stream cũng dễ làm tác dụng phụ bị bỏ qua, khó kiểm thử và khó an toàn luồng. Nếu mục tiêu là tạo dữ liệu mới, dùng `map` với đối tượng kết quả mới:

~~~java
List<String> normalized = names.stream()
        .map(String::trim)
        .map(String::toUpperCase)
        .toList();
~~~

Ở đây `names` là một `List<String>` đã khai báo; `map` diễn đạt rõ phép biến đổi, còn `toList()` thu kết quả. Trường hợp cần chỉnh sửa đối tượng mutable thật sự, nên xử lý một cách tường minh và có kiểm soát ngoài pipeline hoặc ở một bước nghiệp vụ được thiết kế cho việc đó.

**Lưu ý thêm:** `peek` không tự sao chép phần tử. Với phần tử là object mutable, `peek` vẫn nhận tham chiếu tới object đó. Việc sửa object trong callback có thể làm các bước sau nhìn thấy trạng thái đã đổi, nhưng không vì thế mà callback được bảo đảm chạy hay hành vi đó trở thành cách biến đổi được khuyến nghị.

## 6. Ghi log và đo lường: dùng đúng mức

`peek` phù hợp cho **quan sát tạm thời khi phát triển hoặc điều tra lỗi**: xem dữ liệu đi vào/ra `map` hay `filter`, phát hiện giá trị bất thường, xác định giai đoạn làm phần tử bị loại. Với log trong ứng dụng thực tế:

- Ưu tiên log ở mức `DEBUG`/`TRACE` và kiểm soát phạm vi, tần suất; gọi logger hoặc format chuỗi cho từng phần tử có thể tăng CPU, I/O và làm thay đổi thời gian thực thi.
- Không ghi token, mật khẩu, thông tin cá nhân hoặc dữ liệu nhạy cảm chỉ vì phần tử đi qua pipeline; chỉ log trường thật sự cần thiết và đã được che phù hợp.
- Khi dùng `parallelStream()`, log có thể xen kẽ; ghi thêm định danh tương quan nếu thật sự cần điều tra một tác vụ.
- Không dùng số dòng `peek` làm metric chính xác. Để biết tổng số phần tử kết quả, lấy từ `count()` hoặc kích thước collection đã thu; để đo một công việc nghiệp vụ, đặt bộ đo ở nơi công việc đó được thực thi và có ngữ nghĩa bảo đảm rõ ràng.
- Không dùng `System.out.println` làm cơ chế logging production: ví dụ dùng `println` để dễ học; trong ứng dụng dùng logging framework và cấu hình mức log phù hợp.

Ví dụ **quan sát hai mốc** (đoạn đặt trong `main`):

~~~java
List<Integer> output = java.util.List.of(2, 5, 8, 11).stream()
        .peek(n -> System.out.println("Đầu vào: " + n))
        .filter(n -> n % 2 == 0)
        .peek(n -> System.out.println("Sau filter: " + n))
        .map(n -> n * n)
        .toList();

System.out.println("output = " + output);
~~~

Với pipeline tuần tự này, kết quả danh sách là `[4, 64]`; `peek` trước `filter` giúp theo dõi vị trí đang xét, còn `peek` sau `filter` chỉ quan sát số chẵn. Xóa các `peek` không làm thay đổi kết quả tính toán.

## 7. Chọn thao tác theo yêu cầu thực tế

| Yêu cầu | Lựa chọn | Vì sao |
|---|---|---|
| Xem giá trị sau một bước khi debug | `peek(...)` | Quan sát nhanh theo vị trí trong pipeline; không dựa vào việc callback luôn chạy |
| Chuyển chuỗi, tính toán giá trị, tạo object mới | `map(...)` hoặc `flatMap(...)` | Kết quả mới là một phần ý nghĩa của pipeline |
| Loại dữ liệu không hợp lệ | `filter(...)` | Điều kiện chọn phần tử hiện rõ, kiểm thử được |
| Tính số phần tử đầu ra | `count()` hoặc kích thước kết quả | Không dựa vào side effect để đếm |
| Thu dữ liệu thành danh sách/tập | `toList()`, `collect(...)` | Terminal operation tạo dữ liệu mong muốn |
| Thực hiện tác vụ có side effect trên phần tử đã chọn | `forEach(...)` / `forEachOrdered(...)` với thiết kế an toàn | Tác dụng phụ là mục đích rõ ràng của terminal operation; cần cân nhắc thứ tự và thread |
| Kiểm tra pipeline bằng test | Assert kết quả `toList()`, `count()`, `findFirst()`... | Hợp đồng test dựa trên kết quả được API bảo đảm |

`Stream.toList()` có từ Java 16 và trả danh sách không thể thay đổi bằng các thao tác như `add`/`remove`. Nếu cần một danh sách có thể chỉnh sửa, lựa chọn phải phù hợp yêu cầu về mutability, chẳng hạn thu về `ArrayList` bằng collector. Đó là quyết định về kết quả dữ liệu, không liên quan đến `peek`.

## 8. Các lỗi dễ gặp và cách tự kiểm tra

**Lỗi 1 — Không thấy log nên tưởng `peek` không hoạt động.** Hãy kiểm tra pipeline đã có terminal operation chưa, giai đoạn `filter` có loại phần tử không, terminal có short-circuit không, và terminal có thể tính kết quả bằng tối ưu hóa không (đặc biệt `count()` trên nguồn biết kích thước).

**Lỗi 2 — Coi `peek` như `map`.** Callback nhận giá trị nhưng không trả giá trị thay thế; muốn biến đổi, dùng `map` hoặc `flatMap`. Thay đổi trường bên trong object qua `peek` là side effect, không phải phép biến đổi hàm thuần.

**Lỗi 3 — Dùng `peek` để tăng bộ đếm hoặc ghi audit quan trọng.** Callback có thể không được gọi, hoặc bị short-circuit; tránh phụ thuộc vào side effect này. Chọn phương án đếm, lưu vết hoặc xử lý có hợp đồng rõ ràng.

**Lỗi 4 — Dựa vào thứ tự log để suy ra kết quả parallel.** Kết quả và thứ tự thực thi callback là hai khái niệm khác nhau; `parallel()` làm thứ tự và thread chạy khó đoán. Kiểm tra dữ liệu cuối và đặc tính ordering của từng operation.

**Lỗi 5 — Mutate nguồn hoặc trạng thái dùng chung trong callback.** Có thể vi phạm non-interference hoặc gặp race condition. Tránh biến đổi nguồn khi duyệt; với kết quả mới, dùng operation biểu đạt phép biến đổi.

**Lỗi 6 — Test đếm số lần gọi `peek` như một hợp đồng của Stream.** Test đáng tin cậy nên kiểm tra giá trị đầu ra. Chỉ sử dụng `peek` như hỗ trợ chẩn đoán, không ép implementation phải giữ các callback mà API cho phép tối ưu bỏ đi.

## 9. Tự luyện và kiểm tra hiểu bài

1. Trong pipeline `Stream.of("a", "bb", "ccc").filter(s -> s.length() >= 2).peek(System.out::println).findFirst()`, kết quả của `findFirst()` là gì? Có cần in cả `bb` và `ccc` không?
2. Vì sao `List.of(1, 2, 3).stream().peek(System.out::println).count()` không phải cách đáng tin để chứng minh cả ba số đều đã được duyệt?
3. Muốn biến `" java "` thành `"JAVA"`, dùng `map` hay `peek`? Nếu muốn nhìn giá trị trước và sau biến đổi để debug thì chèn `peek` ở đâu?

**Đáp án gợi ý:** (1) `Optional[bb]`; với pipeline tuần tự, không cần xét `ccc` sau khi gặp phần tử đầu thỏa điều kiện. (2) `count()` có thể suy từ kích thước nguồn mà không duyệt phần tử. (3) dùng `map(String::trim)` và `map(String::toUpperCase)` để tạo giá trị mới; đặt `peek` ở mốc cần quan sát, chẳng hạn trước và sau chuỗi `map`.

## Ghi nhớ

`peek` là công cụ quan sát thuận tiện trong Stream pipeline **khi callback thực sự được thực thi**. Nó là intermediate operation lazy, giữ nguyên phần tử, phụ thuộc nhu cầu duyệt của terminal operation và có thể bị tối ưu bỏ qua. **Kết quả nghiệp vụ phải được biểu đạt bằng các operation của Stream có hợp đồng phù hợp**, không dựa trên log hoặc side effect của `peek`.

### Tài liệu API hiện hành

- [Oracle Java SE 25 — `Stream.peek` và `Stream.count`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle Java SE 25 — `java.util.stream`: laziness, non-interference, statelessness và side effects](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
