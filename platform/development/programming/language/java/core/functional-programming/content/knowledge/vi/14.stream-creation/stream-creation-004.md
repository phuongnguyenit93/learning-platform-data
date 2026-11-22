# Stream.generate() với Supplier trong Java

## 1. Khái niệm: tạo nguồn phần tử theo yêu cầu

`Stream.generate(Supplier<? extends T> s)` là một phương thức `static` của `java.util.stream.Stream` dùng để tạo **một stream tuần tự, không có thứ tự encounter order được bảo đảm, về mặt khái niệm vô hạn**. Mỗi lần nguồn stream cần sinh một phần tử, nó yêu cầu `Supplier` cung cấp giá trị bằng phương thức `get()`.

Chữ ký của API:

~~~java
public static <T> Stream<T> generate(Supplier<? extends T> s)
~~~

`Supplier<T>` là một functional interface trong package `java.util.function`, có phương thức trừu tượng duy nhất (SAM):

~~~java
T get();
~~~

Vì không có đối số, supplier biểu diễn hành vi **“khi được yêu cầu, hãy cung cấp một phần tử”**. Có thể viết nó bằng lambda `() -> value`, method reference như `UUID::randomUUID` hoặc bằng một object triển khai `Supplier<T>`.

~~~java
Stream<String> messages = Stream.generate(() -> "hello");
~~~

**Lưu ý:** Đoạn trên chỉ minh họa một câu lệnh bên trong phương thức đã import `java.util.stream.Stream`; nó **chưa chạy supplier** ngay lúc tạo pipeline. Muốn nhận phần tử, ta phải dùng terminal operation như `toList()`, `forEach()`, `findFirst()` hoặc `count()` cùng một cách giới hạn phù hợp.

Một cách dùng cơ bản và an toàn hơn là giới hạn số lượng cần tiêu thụ:

~~~java
List<String> three = Stream.generate(() -> "hello")
        .limit(3)
        .toList();
~~~

Kết quả là `[hello, hello, hello]`. Ở đây `limit(3)` là thao tác trung gian (*intermediate operation*), còn `toList()` mới kích hoạt việc tiêu thụ pipeline.

**Ghi nhớ ngay:** `generate()` giúp khai báo **quy tắc sinh phần tử**, còn **terminal operation** mới yêu cầu stream thực sự chạy. Tuy nhiên, tính “lazy” không đồng nghĩa supplier tự được cache, tự an toàn luồng hay không bao giờ gây tác dụng phụ.

## 2. Cơ chế làm việc: `Supplier`, pipeline và terminal operation

Đọc pipeline theo từng giai đoạn:

~~~text
Supplier<T>             Stream<T>                  Kết quả
  () -> T      ──► Stream.generate(s) ──► limit(n) ──► toList()
                 nguồn lazy (vô hạn)     giới hạn    tiêu thụ
~~~

Các vai trò:

1. **`Supplier`** mô tả cách cung cấp một giá trị kiểu `T` mỗi lần `get()` được gọi.
2. **`Stream.generate(s)`** tạo nguồn stream. Bản thân lời gọi này không bắt buộc tạo sẵn phần tử nào.
3. **`limit(n)`** quy định tối đa `n` phần tử đi tiếp đến downstream; nó không tự tiêu thụ pipeline ngay tại thời điểm gọi.
4. **`map`, `filter`** là các bước biến đổi/trích lọc trung gian, cũng mang tính lazy.
5. **`toList`, `forEach`, `reduce`, `collect`, `findFirst`, `count`** là các terminal operation. Chúng kích hoạt traversal và có thể yêu cầu supplier sinh phần tử.

Một khác biệt quan trọng với collection: `List.of("a","b")` lưu sẵn hai phần tử. Với `Stream.generate(() -> expensive())`, các giá trị **không được tạo sẵn thành một danh sách** khi khai báo nguồn; `expensive()` sẽ được thực thi khi traversal yêu cầu phần tử.

### 2.1. Khi nào `get()` chạy?

Với pipeline tuần tự đơn giản `Stream.generate(supplier).limit(3).toList()`, supplier được gọi ba lần để tạo ba phần tử. Nếu chỉ xây pipeline mà không gọi terminal operation, không có traversal. Nếu dùng `limit(0)`, kết quả trống và không cần yêu cầu phần tử từ nguồn.

Trong những pipeline phức tạp, **đừng đồng nhất số phần tử kết quả với số lần `get()`**:

~~~java
List<Integer> values = Stream.generate(() -> 1)
        .filter(x -> x > 10)
        .limit(3)
        .toList();
~~~

**Đây là ví dụ cố ý nguy hiểm, không chạy:** nguồn chỉ tạo `1`, điều kiện `x > 10` luôn sai, nên `limit(3)` không bao giờ nhận đủ ba phần tử và terminal operation có thể chạy mãi. `limit` chặn **số phần tử đi qua**, chứ không luôn chặn **số lần sinh thử** ở phía trước một bộ lọc.

Một pipeline khác:

~~~java
List<Integer> values = Stream.generate(() -> 1)
        .limit(3)
        .filter(x -> x > 10)
        .toList();
~~~

Pipeline thứ hai hoàn tất và trả danh sách trống, vì `limit(3)` giới hạn số phần tử **trước** khi lọc. **Thứ tự `limit` và `filter` có ý nghĩa rất lớn** khi nguồn có thể vô hạn.

## 3. Ví dụ hoàn chỉnh: kiểm chứng tính lazy và số lần gọi

Lưu file **`StreamGenerateDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class StreamGenerateDemo {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();

        Supplier<String> source = () -> {
            int current = counter.incrementAndGet();
            System.out.println("get#" + current);
            return "ticket-" + current;
        };

        Stream<String> stream = Stream.generate(source);
        System.out.println("before=" + counter.get());

        List<String> tickets = stream.limit(3).toList();
        System.out.println("tickets=" + tickets);
        System.out.println("after=" + counter.get());

        List<String> fixed = Stream.generate(() -> "ping")
                .limit(2)
                .toList();
        System.out.println("fixed=" + fixed);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac StreamGenerateDemo.java
java StreamGenerateDemo
~~~

Stdout:

~~~text
before=0
get#1
get#2
get#3
tickets=[ticket-1, ticket-2, ticket-3]
after=3
fixed=[ping, ping]
~~~

**Đọc kết quả:**

- `Stream.generate(source)` chỉ tạo một stream mô tả nguồn sinh; ở thời điểm in `before`, `counter` vẫn bằng `0`.
- Khi `toList()` yêu cầu ba phần tử từ `limit(3)`, supplier chạy lần lượt và tăng bộ đếm lên `1`, `2`, `3`.
- `List<String> tickets` chứa các chuỗi được tạo ra, còn biến `stream` đã được sử dụng cho một terminal operation. **Không được tái sử dụng cùng một stream** để chạy terminal operation khác.
- Pipeline cuối tạo một **stream mới** từ supplier hằng `() -> "ping"`, trả hai phần tử giống nhau.

`AtomicInteger` ở ví dụ chỉ để đo số lần gọi một cách rõ ràng. Việc tăng bộ đếm vẫn là một **tác dụng phụ** của supplier và không phải mẫu thiết kế lý tưởng cho mọi pipeline. Ví dụ này cố ý chạy tuần tự để stdout có thứ tự ổn định.

## 4. Khi nào nên dùng `Stream.generate()`?

### 4.1. Sinh các phần tử độc lập theo cùng một quy tắc

Ví dụ tạo mã định danh ngẫu nhiên:

~~~java
List<UUID> ids = Stream.generate(UUID::randomUUID)
        .limit(5)
        .toList();
~~~

`UUID::randomUUID` là method reference tới phương thức `static` không có tham số, trả `UUID`; nó tương thích với `Supplier<UUID>`. Đây là đoạn minh họa cần import `java.util.List`, `java.util.UUID` và `java.util.stream.Stream`.

Đặc điểm: mỗi phần tử được tạo khi nguồn cần cung cấp dữ liệu. Tuy nhiên, không nên dùng các UUID như bằng chứng rằng stream có thứ tự encounter order hay rằng luôn tạo đúng một số lượng lời gọi trong mọi pipeline song song. Nếu cần dự đoán đầu ra để kiểm thử, dùng supplier xác định thay vì UUID ngẫu nhiên.

### 4.2. Sinh dữ liệu giả phục vụ test hoặc demo

~~~java
List<String> placeholders = Stream.generate(() -> "UNKNOWN")
        .limit(4)
        .toList();
~~~

Dữ liệu cố định như `"UNKNOWN"` không cần cơ chế stateful. Cách này phù hợp khi muốn tạo danh sách có số lượng `n` nhưng cùng một giá trị, chẳng hạn dữ liệu giả để kiểm tra giao diện.

Nếu chỉ cần *một* giá trị hoặc vài literal đã biết, dùng `List.of(...)` có thể đơn giản và dễ đọc hơn. Không nên ép `generate` vào mọi trường hợp tạo collection.

### 4.3. Tạo đối tượng mới theo nhu cầu

~~~java
List<StringBuilder> buffers = Stream.generate(StringBuilder::new)
        .limit(3)
        .toList();
~~~

Ở đây constructor reference `StringBuilder::new` tương thích với `Supplier<StringBuilder>`. Ba lần cấp phần tử trong pipeline tuần tự đơn giản sẽ tạo ba đối tượng `StringBuilder` độc lập.

**Phân biệt:** `Stream.generate(() -> sharedBuffer)` chỉ trả lại cùng một reference đến `sharedBuffer` nhiều lần. `Stream.generate(StringBuilder::new)` gọi constructor mỗi lần để tạo object mới. Chữ ký `Supplier<T>` **không quyết định** object được tạo mới hay dùng lại: điều đó phụ thuộc thân supplier.

## 5. Ví dụ hoàn chỉnh: tạo DTO và kết hợp với pipeline

Lưu file **`GeneratedRecordsDemo.java`**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class GeneratedRecordsDemo {
    record Ticket(int id, String state) {}

    public static void main(String[] args) {
        AtomicInteger sequence = new AtomicInteger(100);

        Supplier<Ticket> ticketFactory = () ->
                new Ticket(sequence.incrementAndGet(), "NEW");

        List<String> descriptions = Stream.generate(ticketFactory)
                .limit(3)
                .map(t -> t.id() + ":" + t.state())
                .toList();

        System.out.println("tickets=" + descriptions);
        System.out.println("lastId=" + sequence.get());

        List<Integer> ordered = Stream.iterate(1, n -> n + 1)
                .limit(4)
                .toList();

        System.out.println("iterate=" + ordered);
    }
}
~~~

Lệnh chạy:

~~~bash
javac GeneratedRecordsDemo.java
java GeneratedRecordsDemo
~~~

Kết quả:

~~~text
tickets=[101:NEW, 102:NEW, 103:NEW]
lastId=103
iterate=[1, 2, 3, 4]
~~~

**Tại sao hai cách sinh khác nhau cùng xuất hiện?**

- `generate(ticketFactory)` lấy từng `Ticket` theo hành vi do supplier cung cấp. Nguồn `generate` không đưa số thứ tự cho callback. Ta tự sử dụng `AtomicInteger` bên ngoài để tạo ID minh họa.
- `map(t -> t.id() + ":" + t.state())` biến object được sinh ra thành mô tả chuỗi, và `toList()` trả danh sách kết quả.
- `Stream.iterate(1, n -> n + 1)` là một **dãy có quan hệ với phần tử trước**, có thứ tự encounter order rõ theo quy tắc của `iterate`. Vì thế khi muốn `1,2,3,4`, `iterate` biểu đạt ý định tốt hơn một `Supplier` tăng counter.
- Record `Ticket` là tính năng chuẩn từ Java 16; toàn bộ ví dụ phù hợp Java 17+.

**Lưu ý về mã tạo ID:** bộ đếm dùng chung là mutable state. Ví dụ được chạy tuần tự và dùng giới hạn nhỏ để dễ minh họa, **không phải** bằng chứng `Stream.generate` phù hợp tự nhiên với việc sinh dãy có thứ tự khi chạy song song.

## 6. Tính “vô hạn” và lý do phải quan tâm đến điểm dừng

`Stream.generate` trả **một stream vô hạn về mặt ngữ nghĩa**, tức nguồn không tự thông báo đã hết phần tử. Nó không cấp phát vô hạn phần tử ở thời điểm khai báo; rủi ro xảy ra khi terminal operation cố tiêu thụ hết nguồn mà không có điều kiện dừng.

### 6.1. Cách an toàn với giới hạn rõ ràng

~~~java
List<Integer> ten = Stream.generate(() -> 7)
        .limit(10)
        .toList();
~~~

Mười phần tử `7` được thu thập rồi kết thúc. Với `limit(n)`, `n` phải không âm; `limit(-1)` ném `IllegalArgumentException`.

### 6.2. Cách gây treo hoặc tốn tài nguyên

~~~java
// KHÔNG CHẠY: cố thu thập một nguồn vô hạn.
List<String> neverEnds = Stream.generate(() -> "x").toList();
~~~

Không có điểm kết thúc, `toList()` cố thu thập mãi, có thể dẫn tới tiêu thụ tài nguyên rất lớn hoặc không hoàn tất. Tương tự, `count()` hoặc `forEach()` trên nguồn vô hạn không giới hạn có thể không bao giờ trả về.

Không nhầm `findFirst()` hoặc `findAny()` với việc tạo danh sách đầy đủ. Chúng là terminal operation có thể dừng sớm khi đã nhận được một phần tử; tuy nhiên, hiệu ứng phụ của một supplier và số lần gọi với pipeline song song/phức tạp vẫn không nên được dự đoán như một vòng lặp tuần tự đơn giản.

### 6.3. `filter` có thể khiến `limit` không đạt đủ phần tử

~~~java
// KHÔNG CHẠY: không có giá trị nào đạt điều kiện.
Stream.generate(() -> 0)
      .filter(n -> n > 0)
      .limit(5)
      .toList();
~~~

`limit(5)` yêu cầu năm phần tử **sau khi lọc**, nhưng nguồn chỉ sinh `0` và mọi phần tử bị loại bỏ. Vì không bao giờ có đủ năm kết quả, pipeline không kết thúc bình thường.

Muốn giới hạn số **lần sinh thử**, đưa `limit` trước `filter`:

~~~java
List<Integer> none = Stream.generate(() -> 0)
        .limit(5)
        .filter(n -> n > 0)
        .toList();
// none là [].
~~~

Trong ví dụ thứ hai, chỉ tối đa năm phần tử từ nguồn được phép đi qua `limit(5)` trong pipeline tuần tự. Vì tất cả bị loại, kết quả là danh sách rỗng.

**Bài học thiết kế:** cần xác định muốn giới hạn **số phần tử đầu vào** hay **số phần tử đầu ra đạt điều kiện**. Chọn vị trí của `limit` theo yêu cầu, đặc biệt với nguồn không có điểm dừng.

## 7. `generate()` và `iterate()` không thay thế hoàn toàn cho nhau

| Tiêu chí | `Stream.generate(supplier)` | `Stream.iterate(seed, next)` |
|---|---|---|
| Nguồn sinh | Một `Supplier<T>` không có tham số | Phần tử đầu tiên + phép lấy phần tử kế tiếp |
| Quan hệ giữa các phần tử | Không được biểu diễn qua tham số callback | `next` nhận phần tử trước đó |
| Encounter order | Nguồn **unordered** | Nguồn **ordered** |
| Chiều dài mặc định | Vô hạn | Vô hạn với overload 2 tham số |
| Bản có điều kiện kết thúc | Không có overload truyền predicate trực tiếp | Overload `iterate(seed, hasNext, next)` từ Java 9 |
| Trường hợp phù hợp | Giá trị độc lập, đối tượng mới, dữ liệu sinh theo supplier | Dãy truy hồi, chỉ số, ngày liên tiếp, tiến trình tuần tự |

Ví dụ dãy số tuần tự có thứ tự:

~~~java
List<Integer> sequence = Stream.iterate(1, n -> n + 1)
        .limit(4)
        .toList();
// [1, 2, 3, 4]
~~~

Với Java 9+ có thể dùng overload ba đối số:

~~~java
List<Integer> bounded = Stream.iterate(
        1,
        n -> n <= 4,
        n -> n + 1
).toList();
// [1, 2, 3, 4]
~~~

Dạng ba đối số biểu diễn điều kiện tiếp tục ngay trong nguồn. Nếu cần chỉ một dãy `int` nguyên thủy từ 1 đến 4, `IntStream.rangeClosed(1, 4)` thường là cách ngắn gọn, rõ ràng và không cần boxing thành `Integer`.

**Hãy chọn theo semantics:** Một supplier có thể chứa bộ đếm nội bộ để sinh `1,2,3,...`, nhưng điều đó ẩn quan hệ thứ tự trong mutable state. `iterate` hoặc `IntStream.range` mô tả quan hệ đó ngay bằng API.

## 8. Một supplier có thể cung cấp object mới hoặc object chia sẻ

Hai cách viết sau có cùng kiểu `Supplier<List<String>>` nhưng **khác hẳn hành vi**:

~~~java
List<String> shared = new ArrayList<>();

Supplier<List<String>> same = () -> shared;
Supplier<List<String>> fresh = ArrayList::new;
~~~

Đây là các đoạn minh họa cần import `java.util.List`, `java.util.ArrayList` và `java.util.function.Supplier`. Nếu dùng:

~~~java
List<List<String>> a = Stream.generate(same).limit(3).toList();
List<List<String>> b = Stream.generate(fresh).limit(3).toList();
~~~

Danh sách `a` chứa **ba reference trỏ tới cùng một `shared`**. Thay đổi `shared` sau đó có thể xuất hiện qua cả ba vị trí. Danh sách `b` chứa ba danh sách mới riêng biệt.

Điều này có ý nghĩa với `StringBuilder`, entity mutable, buffer hoặc các object giữ trạng thái. `Stream.toList()` trả **danh sách kết quả không hỗ trợ các thao tác sửa cấu trúc**, nhưng không làm các object phần tử trở nên immutable. Tính bất biến của collection **khác** với tính bất biến của từng phần tử.

Một lỗi điển hình là supplier trả mãi một object rồi downstream cố dùng object ấy như phần tử độc lập. Kết quả có thể có dữ liệu bị ghi đè hoặc trạng thái dùng chung không mong muốn. Khi cần instance riêng, hãy bảo đảm supplier thực sự tạo object mới.

## 9. Supplier có trạng thái, side effect và chạy song song

### 9.1. Supplier có mutable state có thể hoạt động tuần tự nhưng khó bảo trì

Một supplier kiểu:

~~~java
Supplier<Integer> next = new Supplier<>() {
    int value = 0;

    @Override
    public Integer get() {
        return ++value;
    }
};
~~~

sinh ra các số tăng dần nếu được gọi lần lượt trong cùng một thread. Đây là đoạn minh họa của một `Supplier<Integer>`, không có `main`.

Nhưng việc dùng nó như nguồn `generate(next)` có một số vấn đề:

- Thứ tự giá trị được giấu trong state của supplier, trong khi nguồn `generate` được đặc tả là **unordered**.
- Nếu cùng supplier được dùng cho nhiều stream hoặc nhiều thread, state có thể bị chia sẻ và gây race condition.
- Nếu một pipeline có `filter`, `limit`, short-circuit hay thay đổi execution mode, số lần gọi `get()` có thể không phản ánh số phần tử cuối cùng.
- Khi muốn “phần tử sau phụ thuộc phần tử trước”, `Stream.iterate` hoặc `IntStream.range` thường truyền đạt ý định rõ hơn.

Đối với stream song song, không nên xây logic dựa vào việc nhận `1,2,3,...` theo một thứ tự nhất định từ supplier stateful.

### 9.2. `parallel()` không làm mọi supplier tự động thread-safe

~~~java
// Ví dụ chỉ về cú pháp, không khuyến nghị supplier stateful.
List<String> values = Stream.generate(() -> "stable")
        .parallel()
        .limit(5)
        .toList();
~~~

Supplier hằng `() -> "stable"` không có mutable state; với pipeline này, danh sách kết quả gồm năm chuỗi `"stable"`. Nhưng `generate` là nguồn unordered và khi chạy song song, **không có cam kết về thứ tự gọi callback hoặc thread thực hiện callback**.

Nếu một supplier ghi vào `ArrayList` dùng chung, tăng biến `int` không đồng bộ hoặc sử dụng object không thread-safe, chuyển sang `parallel()` có thể tạo lỗi dữ liệu. `AtomicInteger` giúp việc tăng một counter là nguyên tử nhưng **không** biến toàn bộ pipeline và mọi side effect trở nên đúng theo thứ tự mong muốn.

Theo tài liệu Stream, các behavioral parameter của pipeline nên **non-interfering**; phần lớn trường hợp cũng nên stateless. Nếu cần random số trong các stream phức tạp hoặc song song, cân nhắc `ThreadLocalRandom.current()` ở phạm vi phù hợp và xác định yêu cầu về thứ tự/tái lập kết quả thay vì chia sẻ một instance generator mutable không an toàn.

### 9.3. Không dùng supplier để làm side effect bắt buộc

Stream được thiết kế để xử lý phần tử, không phải để đảm bảo một callback tạo nguồn phải chạy đúng một số lần như giao thức giao dịch. Ví dụ supplier vừa sinh phần tử vừa ghi vào database, `limit`/`filter`/short-circuit có thể làm số lần tác động khác dự kiến. Hãy tách hành vi nghiệp vụ quan trọng khỏi mục đích chỉ sinh dữ liệu stream, hoặc thiết kế một API vòng đời/tác vụ riêng có kiểm soát.

**Quy tắc:** supplier nên chủ yếu **cung cấp giá trị**, tránh dùng nó để điều khiển nghiệp vụ bằng những side effect phụ thuộc chính xác vào thời gian hoặc số lần gọi.

## 10. Khi nào `Stream.generate()` **không** phù hợp?

### 10.1. Dữ liệu đã có sẵn trong collection

~~~java
List<String> names = List.of("An", "Binh", "Chi");
List<String> upper = names.stream().map(String::toUpperCase).toList();
~~~

Với collection đã tồn tại, `names.stream()` là nguồn tự nhiên. Không cần dùng `Stream.generate` để đọc lại danh sách từng phần tử, rồi tự quản lý chỉ số và điểm dừng.

### 10.2. Muốn sinh một dãy số có thứ tự và hữu hạn

~~~java
List<Integer> ids = java.util.stream.IntStream.rangeClosed(1, 3)
        .boxed()
        .toList();
~~~

`IntStream.rangeClosed` diễn đạt chính xác `1,2,3` và có điểm kết thúc. `generate` chỉ thích hợp nếu thực sự cần **một quy tắc cung cấp phần tử độc lập**.

### 10.3. Đọc tài nguyên có trạng thái kết thúc

Nếu đọc dữ liệu từ file, network hoặc database, nguồn thường có một điểm **EOF/end-of-stream** và vòng đời tài nguyên. `Stream.generate` không có thông tin kết thúc tích hợp trong `Supplier<T>`; một supplier trả `null` để báo hết có thể đưa `null` thành một phần tử thực sự và gây lỗi downstream.

Với file văn bản, hãy xem `Files.lines(Path)` và đóng stream theo tài liệu, ví dụ dùng `try-with-resources`. Với các nguồn có kết thúc tùy chỉnh, cân nhắc `Stream.iterate(seed, hasNext, next)`, `Spliterator` hoặc một abstraction chuyên dụng, tùy yêu cầu. Không dùng `generate` rồi `filter(Objects::nonNull)` để xử lý EOF: việc lọc bỏ null **không** làm nguồn vô hạn tự dừng.

### 10.4. Muốn xử lý lỗi I/O đã kiểm tra

`Supplier.get()` không khai báo checked exception. Lambda đọc file có thể ném `IOException` không được phép để exception ấy thoát ra khỏi một `Supplier<T>` chuẩn mà không xử lý. Nếu cần I/O, hãy cân nhắc API có vòng đời tài nguyên và hợp đồng lỗi rõ ràng, không ép mọi thao tác vào `generate`.

### 10.5. Muốn số lần gọi chính xác trong giao dịch

Một stream pipeline có thể thay đổi theo `limit`, `filter`, short-circuit và chế độ thực thi. Đừng sử dụng một supplier có side effect để thay thế vòng lặp cần tính chính xác số lần ghi/đọc bên ngoài. Với công việc có ý nghĩa giao dịch, một vòng lặp hoặc API chuyên biệt có thể rõ ràng và kiểm soát được hơn.

## 11. Các lỗi phổ biến khi dùng `Stream.generate()`

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| `Stream.generate(...).toList()` không giới hạn | Có thể cố tiêu thụ nguồn vô hạn | Thêm điểm dừng phù hợp hoặc chọn nguồn hữu hạn |
| `filter` không bao giờ cho phần tử qua, rồi `limit(n)` | Pipeline không đạt đủ `n` kết quả nên không kết thúc | Nếu muốn giới hạn lượt thử, đưa `limit` trước `filter` |
| Mong supplier chạy ngay khi gọi `generate` | Hiểu sai thời điểm tạo dữ liệu | Nhớ terminal operation mới kích hoạt traversal |
| Nghĩ supplier chỉ chạy một lần | Giá trị sinh ra thiếu hoặc lặp logic sai | Kiểm tra contract; `get()` có thể được gọi nhiều lần |
| Giữ mutable state không đồng bộ trong supplier khi `parallel()` | Race condition, không ổn định kết quả | Dùng nguồn stateless/thread-safe; tránh phụ thuộc thứ tự |
| Cho rằng `generate` có encounter order | Dự đoán sai thứ tự khi chạy song song | Dùng `iterate`/`range` nếu cần ordered sequence |
| Dùng `null` làm tín hiệu hết nguồn | Null trở thành phần tử, nguồn không tự dừng | Dùng API có điều kiện kết thúc/spliterator phù hợp |
| Dùng cùng stream sau terminal operation | `IllegalStateException` hoặc không thể tái sử dụng | Tạo stream mới cho lần xử lý tiếp theo |
| Supplier trả cùng mutable object nhiều lần | Phần tử chia sẻ state ngoài ý muốn | Tạo object mới hoặc chấp nhận chia sẻ có chủ đích |
| Quên đóng tài nguyên bên trong supplier | Rò rỉ tài nguyên hoặc tài nguyên đã đóng | Thiết kế vòng đời, try-with-resources và API chuyên biệt |

**Lưu ý về `null`:** `Stream.generate(() -> null)` có thể tạo các phần tử `null` ở một `Stream<T>` tham chiếu; nhưng nhiều phép toán downstream, như method reference vào một instance method, có thể ném `NullPointerException`. `null` không được diễn giải tự động là điểm dừng. Khi nghiệp vụ có trạng thái “hết dữ liệu”, hãy mô hình hóa nó tường minh.

## 12. Checklist thiết kế cho nguồn sinh phần tử

Trước khi chọn `Stream.generate`, hãy tự hỏi:

1. Nguồn dữ liệu có thể được mô tả bằng một **Supplier không tham số** không?
2. Các phần tử có **độc lập về logic** hay thực sự phụ thuộc thứ tự phần tử trước?
3. Có một **điểm dừng hữu hạn** chắc chắn không: `limit`, terminal short-circuit, hay API khác?
4. Nếu có `filter`, `limit` đang giới hạn lượt sinh thử hay số kết quả sau lọc?
5. Supplier trả **object mới** hay **reference dùng chung**? Điều đó có đúng mong muốn không?
6. Supplier có mutable state hoặc side effect nào gây rủi ro với parallel execution không?
7. Nguồn có tài nguyên cần **đóng**, lỗi I/O hoặc tín hiệu EOF không?
8. Một pipeline khác có dễ đọc hơn với `Stream.iterate`, `IntStream.range` hoặc `Collection.stream` không?
9. Các test có được giới hạn bằng nguồn xác định và có kết quả lặp lại không?
10. Có đang nhầm “lazy generation” với cache hoặc bất đồng bộ không?

Nếu vẫn muốn dùng `generate`, hãy giữ supplier **ngắn, độc lập, dễ kiểm tra**, đặt giới hạn hoặc điều kiện kết thúc ở nơi dễ thấy và dùng nguồn tuần tự khi bài toán cần dự đoán thứ tự thực hiện.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `Stream.generate(() -> "x")` có tạo vô hạn chuỗi trong bộ nhớ ngay khi gọi không?

**Câu 2.** Khi nào `Supplier.get()` bắt đầu được gọi trong pipeline `generate(s).limit(3).toList()`?

**Câu 3.** Vì sao `Stream.generate(() -> 0).filter(x -> x > 0).limit(3).toList()` không kết thúc?

**Câu 4.** Đổi `filter` và `limit` có thay đổi điều kiện dừng không?

**Câu 5.** `Stream.generate(StringBuilder::new).limit(3).toList()` trả ba đối tượng mới hay ba reference trỏ tới cùng một object?

**Câu 6.** Vì sao không nên tin rằng `generate` sinh một dãy có thứ tự cố định trong parallel stream?

**Câu 7.** Với dãy số 1..100 có thứ tự, chọn `generate`, `iterate` hay `IntStream.rangeClosed`?

**Câu 8.** Có thể dùng `null` do supplier trả về để báo EOF tự động không?

**Câu 9.** `Supplier` có tự cache giá trị hoặc chạy bất đồng bộ không?

**Đáp án ngắn:**

1. Không; nguồn được tạo lazy và không cấp phát toàn bộ phần tử ngay.
2. Khi terminal operation tiêu thụ pipeline; trong ví dụ tuần tự đơn giản, ba phần tử được yêu cầu.
3. `filter` loại mọi số `0`, `limit` phía sau không bao giờ đủ ba phần tử.
4. Có; `limit` trước `filter` giới hạn số đầu vào phải thử, còn `limit` sau `filter` giới hạn số phần tử qua lọc.
5. Supplier constructor reference được thực hiện mỗi lần cần phần tử, tạo các object mới.
6. Vì nguồn `generate` được đặc tả là unordered và parallel traversal không hứa thứ tự gọi supplier.
7. `IntStream.rangeClosed(1,100)` rõ nhất nếu chỉ cần dãy `int` hữu hạn.
8. Không; `null` có thể là phần tử, không phải tín hiệu kết thúc của `generate`.
9. Không; muốn cache hay async cần công cụ/cơ chế riêng.

## 14. Nguồn tham khảo chính thức

- [Java SE 17 API — Stream.generate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#generate(java.util.function.Supplier)): mô tả stream vô hạn, tuần tự, unordered và yêu cầu `Supplier`.
- [Java SE 17 API — Supplier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html): SAM `T get()`.
- [Java SE 17 API — Stream.limit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#limit(long)): giới hạn số phần tử và lưu ý với nguồn có encounter order/parallel.
- [Java SE 17 API — Stream.iterate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#iterate(T,java.util.function.UnaryOperator)): nguồn có thứ tự, trong đó phần tử sau phụ thuộc phần tử trước.
- [Java SE 17 API — IntStream.rangeClosed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html#rangeClosed(int,int)): tạo dãy primitive `int` hữu hạn với giới hạn rõ ràng.

**Tóm lại:** `Stream.generate(Supplier)` là cách diễn đạt một **nguồn phần tử được tạo theo nhu cầu**: mỗi lần cần phần tử, stream có thể gọi `get()`. Nó phù hợp với việc tạo giá trị độc lập, dữ liệu giả hoặc object mới, nhưng nguồn **vô hạn và unordered**, nên cần quan tâm điểm dừng, `filter`/`limit`, tác dụng phụ và sự an toàn khi chạy song song. Khi cần dãy hữu hạn hoặc phụ thuộc thứ tự, ưu tiên các nguồn như `Stream.iterate` hay `IntStream.rangeClosed`.