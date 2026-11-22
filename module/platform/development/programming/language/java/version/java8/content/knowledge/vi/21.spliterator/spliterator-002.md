# tryAdvance và forEachRemaining trong Java Spliterator

## 1. Mục tiêu và ý tưởng chính

`Spliterator<T>` là giao diện trong `java.util` dùng để **duyệt và có thể phân chia** tập phần tử của một nguồn dữ liệu. Nó xuất hiện từ Java 8, vẫn là thành phần hiện hành của Java Collections/Stream API. Tên *Spliterator* ghép từ ý tưởng **split** (phân chia) và **iterator** (duyệt).

Hai phương thức quan trọng nhất khi trực tiếp duyệt một Spliterator:

- **`tryAdvance(action)`**: thử lấy **tối đa một phần tử kế tiếp** và đưa phần tử đó vào `action`. Trả `true` nếu có phần tử được xử lý; trả `false` nếu đã hết.
- **`forEachRemaining(action)`**: xử lý **toàn bộ các phần tử còn lại** của spliterator, từ vị trí hiện tại, rồi kết thúc. Trả `void`, không trả trạng thái từng bước.

Ví dụ có nguồn `["An", "Binh", "Chi", "Dung"]`:

```text
Ban đầu: An | Binh | Chi | Dung

tryAdvance(action)    -> xử lý "An";   trả true
tryAdvance(action)    -> xử lý "Binh"; trả true
forEachRemaining(...) -> xử lý "Chi", "Dung"; trả void

tryAdvance(action)    -> không xử lý gì; trả false
```

**Điểm mấu chốt:** Hai phương thức thao tác trên **cùng vị trí duyệt** của đối tượng `Spliterator`. Khi một phần tử đã được xử lý, nó không tự xuất hiện lại trong lần duyệt tiếp theo. Muốn duyệt lại từ đầu, thông thường hãy lấy một spliterator mới từ nguồn (nếu nguồn còn có thể duyệt và vẫn phù hợp), không cố “reset” spliterator cũ.

Trong bài này, ví dụ Java đầy đủ được viết theo Java 17+, đồng thời sử dụng các API cốt lõi vẫn áp dụng trong Java hiện đại. Các kiến thức về `tryAdvance`, `forEachRemaining` và `Spliterator` không phải kỹ thuật đã bị thay thế hay bị loại bỏ.

## 2. Spliterator khác gì Iterator và Stream?

Cả ba khái niệm có liên quan nhưng không đồng nghĩa:

| Khái niệm | Vai trò | Giao diện thường thấy |
| --- | --- | --- |
| `Iterator<T>` | Duyệt các phần tử bằng `hasNext()` và `next()`, chủ yếu theo một luồng duyệt. | `Iterator<T>` |
| `Spliterator<T>` | Duyệt qua `tryAdvance`/`forEachRemaining` và **có thể** tách nguồn bằng `trySplit` để tạo các phần xử lý độc lập. | `Spliterator<T>` |
| `Stream<T>` | Mô tả một pipeline `filter`, `map`, `collect`, `reduce`...; có thể dùng spliterator phía dưới để duyệt và phân chia nguồn. | `Stream<T>` |

Ví dụ lấy Spliterator từ `List`:

```java
// Đoạn minh họa trong ngữ cảnh có import java.util.*.
List<String> names = Arrays.asList("An", "Binh", "Chi");
Spliterator<String> cursor = names.spliterator();
```

`cursor` ở đây **chưa duyệt** toàn bộ phần tử; nó mới đại diện cho công việc duyệt có thể thực hiện. Khi gọi `tryAdvance` hoặc `forEachRemaining`, trạng thái duyệt tiến về phía trước.

`Spliterator` khác `Iterator` ở việc nó có `trySplit()` và các đặc tính mô tả nguồn như `ORDERED`, `SIZED`, `DISTINCT`, `SORTED`. Tuy nhiên **không phải Spliterator nào cũng phân chia được**: `trySplit()` có thể trả `null`.

**Đừng nhầm với `Stream.forEach(...)`:** `spliterator.forEachRemaining(...)` là phương thức duyệt **phần tử còn lại của chính spliterator**. `stream.forEach(...)` là terminal operation của stream và có những quy tắc riêng khi chạy parallel. Chúng không phải một API duy nhất.

## 3. Hợp đồng chính xác của tryAdvance

Chữ ký khái niệm:

```java
boolean tryAdvance(Consumer<? super T> action);
```

Đây là **chữ ký phương thức của API**; không phải chương trình Java độc lập.

Trong một lần gọi, nếu còn phần tử:

1. Spliterator chọn phần tử kế tiếp theo cách duyệt của nó.
2. Thực hiện `action.accept(element)` **đúng một lần** cho phần tử đó.
3. Trả `true`.

Nếu **không còn phần tử**:

1. Không gọi `action.accept(...)`.
2. Trả `false`.

Ví dụ:

```java
// Đoạn minh họa: cursor được tạo từ List<String>.
boolean advanced = cursor.tryAdvance(
    name -> System.out.println("name=" + name)
);
```

Giá trị `advanced` cho biết **có phần tử được duyệt hay không**, không phải kết quả tính toán trong lambda. Bản thân `action` có kiểu `Consumer` và không trả giá trị.

### 3.1. Với nguồn có thứ tự

Nếu Spliterator có đặc tính `ORDERED`, phần tử được đưa vào action theo **encounter order** của nguồn. Với một `List` thông thường, đó là thứ tự các vị trí trong danh sách. Nếu nguồn **không có encounter order được bảo đảm** (ví dụ một số tập hợp), đừng áp đặt giả định rằng lần duyệt luôn có cùng thứ tự như khi in hoặc quan sát ở một lần chạy.

### 3.2. Giá trị null không phải tín hiệu kết thúc

`tryAdvance` trả `true/false` để thông báo có phần tử, **không dựa vào phần tử có bằng null hay không**. Nếu nguồn được phép chứa `null` thì một lần gọi action với `null` vẫn là đã xử lý **một phần tử**, và `tryAdvance` trả `true`. Hãy dùng boolean trả về, không dùng kiểm tra `element == null` làm tín hiệu kết thúc duyệt chung.

### 3.3. Ngoại lệ và action null

- `tryAdvance(null)` ném `NullPointerException` theo hợp đồng API.
- Ngoại lệ do action ném ra sẽ được truyền lại cho code gọi.
- Nếu action ném ngoại lệ, hành vi tiếp theo của Spliterator **không được API bảo đảm**; không nên coi đây là cách an toàn để tạm dừng rồi tiếp tục duyệt chính xác vị trí cũ.

## 4. Hợp đồng chính xác của forEachRemaining

Chữ ký khái niệm:

```java
default void forEachRemaining(Consumer<? super T> action);
```

Phương thức này gọi action cho **từng phần tử còn lại**, theo một chuỗi duyệt trong thread hiện tại, cho đến khi:

- Không còn phần tử; hoặc
- Action ném ngoại lệ và việc duyệt bị gián đoạn.

Nếu Spliterator có `ORDERED`, các action được thực hiện theo encounter order.

Đặc biệt, `forEachRemaining` **không bắt đầu lại từ đầu**. Nếu bạn đã gọi `tryAdvance` hai lần, nó chỉ duyệt những phần tử **chưa được lấy ra**.

### 4.1. Default implementation tương đương điều gì?

Theo hợp đồng `Spliterator`, cách triển khai mặc định tương đương việc lặp `tryAdvance(action)` cho đến khi nó trả `false`:

```java
// Pseudocode minh họa (không phải chương trình Java độc lập).
while (spliterator.tryAdvance(action)) {
    // Không cần thêm logic.
}
```

Điều này giải thích tại sao `forEachRemaining` có thể xử lý hết phần còn lại, mà không cần code tự viết vòng `while`. Implementation cụ thể **có thể override** `forEachRemaining` để tối ưu duyệt hàng loạt, nhưng phải giữ đúng ý nghĩa API.

### 4.2. Có thể dừng sớm không?

`forEachRemaining` trả `void` và không có cơ chế trả `false` để yêu cầu dừng sau một phần tử cụ thể. Nếu cần **giới hạn số phần tử** hoặc **kiểm tra sau từng bước**, dùng `tryAdvance` kết hợp vòng lặp và điều kiện dừng.

Đừng dùng thủ thuật ném ngoại lệ trong action để giả lập `break`; hành vi Spliterator sau ngoại lệ không được bảo đảm. Nếu đang giải quyết bài toán tìm kiếm hoặc giới hạn trên pipeline Stream, các operation như `findFirst`, `limit` hoặc `takeWhile` (Java 9+) thường diễn đạt mục tiêu tốt hơn.

### 4.3. Sau khi đã duyệt hết

Khi `forEachRemaining` hoàn tất bình thường:

- `tryAdvance` sẽ trả `false` trong lần gọi tiếp theo.
- Gọi `forEachRemaining` lần nữa không còn phần tử để đưa vào action.
- Spliterator thông thường không có `reset()` hoặc `rewind()` để bắt đầu lại.

## 5. Ví dụ 1 — kết hợp hai phương thức trên cùng cursor

Tạo file **BasicTraversalDemo.java**:

```java
import java.util.Arrays;
import java.util.Spliterator;

public class BasicTraversalDemo {
    public static void main(String[] args) {
        Spliterator<String> cursor =
            Arrays.asList("An", "Binh", "Chi", "Dung")
                  .spliterator();

        boolean first = cursor.tryAdvance(
            name -> System.out.println("first=" + name)
        );

        boolean second = cursor.tryAdvance(
            name -> System.out.println("second=" + name)
        );

        System.out.println("advanced=" + first + "," + second);

        cursor.forEachRemaining(
            name -> System.out.println("remaining=" + name)
        );

        boolean exhausted = cursor.tryAdvance(
            name -> System.out.println("unexpected=" + name)
        );

        System.out.println("hasMore=" + exhausted);

        cursor.forEachRemaining(
            name -> System.out.println("unexpectedRest=" + name)
        );
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac BasicTraversalDemo.java
java BasicTraversalDemo
```

Đầu ra chính xác:

```text
first=An
second=Binh
advanced=true,true
remaining=Chi
remaining=Dung
hasMore=false
```

Tại sao không xuất hiện các dòng `unexpected=...` hay `unexpectedRest=...`?

1. Lần `tryAdvance` thứ nhất đã xử lý `An` và trả `true`.
2. Lần `tryAdvance` thứ hai đã xử lý `Binh` và trả `true`.
3. `forEachRemaining` chỉ còn `Chi` và `Dung` để xử lý.
4. Khi hết dữ liệu, `tryAdvance` trả `false` mà không chạy lambda.
5. Lần `forEachRemaining` cuối cùng cũng không còn việc gì, nên không có dòng in mới.

Bài này làm rõ **cùng một cursor bị tiêu thụ dần**. Đừng lấy `forEachRemaining` làm “xử lý tất cả phần tử của collection” nếu trước đó Spliterator đã được duyệt một phần; nó chỉ xử lý các phần tử **remaining**.

## 6. Ví dụ 2 — dùng tryAdvance để chủ động điều khiển vòng lặp

`tryAdvance` đặc biệt hữu ích khi code cần biết **có phần tử vừa xử lý hay không** và quyết định có tiếp tục.

Tạo file **LoopTraversalDemo.java**:

```java
import java.util.Arrays;
import java.util.Spliterator;

public class LoopTraversalDemo {
    public static void main(String[] args) {
        Spliterator<Integer> cursor =
            Arrays.asList(3, 6, 9).spliterator();

        int[] calls = {0};

        while (cursor.tryAdvance(value -> {
            System.out.println("value=" + value);
            calls[0]++;
        })) {
            // Mỗi vòng vừa xử lý đúng một phần tử.
        }

        System.out.println("processed=" + calls[0]);

        System.out.println("end=" +
            cursor.tryAdvance(
                x -> System.out.println("never=" + x)));
    }
}
```

```bash
javac LoopTraversalDemo.java
java LoopTraversalDemo
```

Đầu ra:

```text
value=3
value=6
value=9
processed=3
end=false
```

Trong ví dụ nhỏ này, `int[] calls` được dùng làm holder vì biến local bị lambda capture phải *final/effectively final*. Không nên bê cách thay đổi holder dùng chung này sang một tác vụ `parallelStream()` rồi coi là thread-safe. Ở đây ta **đang trực tiếp duyệt một Spliterator tuần tự trong một thread**.

### 6.1. Chỉ lấy tối đa k phần tử

Giả sử cần xử lý **tối đa 2 phần tử** từ một spliterator đã có:

```java
// Đoạn minh họa trong ngữ cảnh đã có Spliterator<String> cursor.
int taken = 0;
while (taken < 2 && cursor.tryAdvance(System.out::println)) {
    taken++;
}
```

Vòng lặp sẽ không gọi `tryAdvance` quá hai lần thành công. Nó có thể kết thúc sớm hơn nếu hết dữ liệu. Những phần tử **chưa lấy** vẫn còn trên chính cursor nếu code sẽ duyệt tiếp sau đó.

Cách viết có điều kiện `taken < 2` ở **bên ngoài** `tryAdvance` quan trọng: nếu đưa điều kiện vào lambda mà vẫn liên tục gọi `tryAdvance`, bạn có thể âm thầm **tiêu thụ** phần tử dù không thực hiện xử lý mong muốn.

### 6.2. Dùng cho page/chunk hay backpressure?

`tryAdvance` cho phép code ở phía nhận dữ liệu duyệt từng bước với số lượng có thể kiểm soát. Đây là một cơ chế thấp hơn Stream pipeline, có thể hữu ích cho adapter, parser hay nguồn dữ liệu tự định nghĩa. Tuy nhiên, `Spliterator` **không tự cung cấp** giao thức backpressure bất đồng bộ như một thư viện reactive-streams; nó chỉ có các lời gọi duyệt/trả boolean. Không nên đánh đồng hai khái niệm.

## 7. forEachRemaining và việc duyệt phần còn lại

Nếu không cần quyết định sau mỗi phần tử, `forEachRemaining` thường đơn giản hơn một vòng `while(tryAdvance(...))` tự viết:

```java
// Hai đoạn sau tương đương về ý nghĩa duyệt phần tử còn lại.
// Mã minh họa: mỗi đoạn cần một spliterator riêng.

spliteratorA.forEachRemaining(System.out::println);

while (spliteratorB.tryAdvance(System.out::println)) {
    // Tiêu thụ cho đến khi hết.
}
```

Với cùng loại Spliterator và action không có tác động ngoài mong muốn, hai đoạn xử lý phần còn lại theo thứ tự tương ứng. Không chạy cả hai đoạn **trên cùng cursor** rồi kỳ vọng phần tử được in hai lần.

**Hiệu năng:** Một số implementation override `forEachRemaining` để giảm overhead khi duyệt nhiều phần tử. Nhưng không có bảo đảm phổ quát rằng nó luôn nhanh hơn `while(tryAdvance(...))`: hiệu năng tùy nguồn, implementation, action và bộ tối ưu JIT. Ưu tiên ý nghĩa và độ rõ ràng trước; chỉ đo benchmark nếu cần tối ưu.

**Action có side effect:** In ra console hoặc thêm vào danh sách là tác động bên ngoài và có thể phù hợp trong ví dụ duyệt trực tiếp tuần tự. Nhưng khi xử lý song song, hành động ghi chung vào một `ArrayList` hoặc biến đếm không đồng bộ sẽ gây nguy cơ race. Muốn xử lý dữ liệu trong Stream, thường nên để pipeline tạo **kết quả** bằng `map`/`filter`/`collect` thay vì phụ thuộc vào side effect của `forEach`.

## 8. Spliterator.trySplit và phần còn lại sau khi tách

`trySplit()` là phương thức khác với hai phương thức chính nhưng có mối liên hệ quan trọng: nó cho phép tạo một Spliterator khác quản lý **một phần** công việc còn lại. Nếu tách thành công, phần tử do spliterator mới quản lý sẽ **không còn thuộc** phần công việc của spliterator gốc.

Với Spliterator mang đặc tính `ORDERED`, đối tượng trả về từ `trySplit()` đại diện cho một **tiền tố** (prefix) của phần tử còn lại; đối tượng gốc sau đó quản lý phần **hậu tố** (suffix) tương ứng.

`trySplit()` có thể trả `null` nếu implementation không hỗ trợ tách hoặc không tách được tại thời điểm đó. API **không bảo đảm** độ dài mỗi phần tách hoặc chính xác số lần tách. Vì thế không viết ứng dụng dựa vào giả định một `List` sẽ luôn được chia đúng đôi.

### Ví dụ 3 — duyệt prefix và suffix đúng cách

Tạo file **SplitRemainingDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;

public class SplitRemainingDemo {
    public static void main(String[] args) {
        Spliterator<String> suffix =
            Arrays.asList("A", "B", "C", "D", "E", "F")
                  .spliterator();

        Spliterator<String> prefix = suffix.trySplit();

        List<String> reconstructed = new ArrayList<>();

        if (prefix != null) {
            prefix.forEachRemaining(reconstructed::add);
        }

        suffix.forEachRemaining(reconstructed::add);

        System.out.println("reconstructed=" + reconstructed);
        System.out.println("count=" + reconstructed.size());
    }
}
```

```bash
javac SplitRemainingDemo.java
java SplitRemainingDemo
```

Đầu ra:

```text
reconstructed=[A, B, C, D, E, F]
count=6
```

**Tại sao kết quả ổn định dù số phần tử của prefix không được bảo đảm?**

- Nguồn `Arrays.asList(...)` là danh sách có encounter order.
- Nếu tách thành công, `prefix` là phần **đầu**, `suffix` là phần **sau** của công việc chưa duyệt.
- Code duyệt **toàn bộ prefix trước** rồi **toàn bộ suffix**, nên xây lại đủ sáu phần tử theo thứ tự.
- Nếu `trySplit()` trả `null`, `suffix` vẫn quản lý toàn bộ phần tử; kết quả vẫn đủ sáu phần tử.

Ví dụ này xử lý hai spliterator **lần lượt trong một thread** để stdout xác định. Khi muốn xử lý hai phần **song song**, cần giao mỗi spliterator cho một worker phù hợp, tránh nhiều thread cùng thao tác trên **một Spliterator** không được thiết kế hỗ trợ truy cập đồng thời, và tránh ghi đồng thời vào một `ArrayList` chung không có đồng bộ.

### 8.1. Chú ý sau khi đã gọi tryAdvance

Nếu bạn đã xử lý trước một số phần tử bằng `tryAdvance` rồi mới gọi `trySplit()`, việc tách chỉ áp dụng cho **phần còn lại**. Các phần tử đã được action xử lý **không được tạo lại** trong prefix/suffix mới.

## 9. Primitive Spliterator: OfInt, OfLong, OfDouble

Ngoài `Spliterator<T>` cho kiểu tham chiếu, Java còn có các biến thể primitive:

- `Spliterator.OfInt`, dùng `IntConsumer`.
- `Spliterator.OfLong`, dùng `LongConsumer`.
- `Spliterator.OfDouble`, dùng `DoubleConsumer`.

Các biến thể này giúp xử lý trực tiếp `int`, `long`, `double` mà không cần boxing mỗi giá trị thành wrapper như `Integer`/`Long`/`Double`.

Ví dụ chữ ký chuyên biệt:

```java
// Chữ ký minh họa, không phải đoạn chương trình chạy độc lập.
boolean tryAdvance(IntConsumer action);
void forEachRemaining(IntConsumer action);

boolean tryAdvance(LongConsumer action);
void forEachRemaining(LongConsumer action);

boolean tryAdvance(DoubleConsumer action);
void forEachRemaining(DoubleConsumer action);
```

Một điểm dễ nhầm là các chuyên biệt primitive còn có overload nhận `Consumer<? super Integer>` hoặc tương đương do kế thừa giao diện chung; dùng đúng `IntConsumer`, `LongConsumer`, `DoubleConsumer` tránh boxing không cần thiết. Khi lambda có thể bị overload gây khó đọc, nên khai báo biến consumer với kiểu nguyên thủy một cách rõ ràng.

### Ví dụ 4 — duyệt primitive không boxing

Tạo file **PrimitiveTraversalDemo.java**:

```java
import java.util.Spliterator;
import java.util.function.DoubleConsumer;
import java.util.function.IntConsumer;
import java.util.function.LongConsumer;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveTraversalDemo {
    public static void main(String[] args) {
        Spliterator.OfInt ints =
            IntStream.rangeClosed(1, 3).spliterator();

        IntConsumer first =
            n -> System.out.println("intFirst=" + n);

        IntConsumer rest =
            n -> System.out.println("intRest=" + n);

        System.out.println("intAdvanced=" +
            ints.tryAdvance(first));

        ints.forEachRemaining(rest);

        Spliterator.OfLong longs =
            LongStream.of(10L, 20L).spliterator();

        longs.forEachRemaining((LongConsumer)
            n -> System.out.println("long=" + n));

        Spliterator.OfDouble doubles =
            DoubleStream.of(0.5, 1.5).spliterator();

        doubles.forEachRemaining((DoubleConsumer)
            n -> System.out.println("double=" + n));
    }
}
```

```bash
javac PrimitiveTraversalDemo.java
java PrimitiveTraversalDemo
```

Đầu ra:

```text
intFirst=1
intAdvanced=true
intRest=2
intRest=3
long=10
long=20
double=0.5
double=1.5
```

**Giải thích:** `ints.tryAdvance(first)` xử lý số `1`, sau đó `ints.forEachRemaining(rest)` chỉ còn `2` và `3`. Hai spliterator primitive khác xử lý tất cả phần tử tương ứng vì chưa bị tiêu thụ. Việc ghi rõ `LongConsumer`/`DoubleConsumer` cho biết cần dùng overload primitive; trong ví dụ nhỏ lợi ích hiệu năng không đáng kể, nhưng khi duyệt dữ liệu lớn việc giảm boxing có thể hữu ích.

Lưu ý: gọi `spliterator()` từ một Stream là thao tác lấy nguồn duyệt cho lần tiêu thụ đó; **không cố dùng lại cùng Stream** cho terminal operation khác. Nếu cần xử lý bằng API Stream thông thường, hãy tạo pipeline Stream mới từ dữ liệu gốc.

## 10. Viết Spliterator tùy biến: tryAdvance là nền tảng

Khi viết một Spliterator riêng, bạn cần hiểu cách các phương thức phối hợp. Một implementation có thể khai báo `tryAdvance` để lấy phần tử kế tiếp. `forEachRemaining` là **default method**, nên có thể kế thừa nếu vòng lặp qua `tryAdvance` đã đáp ứng yêu cầu; override khi cần tối ưu có cơ sở.

Ví dụ sau tạo một Spliterator sinh số đếm lùi từ `start` về `1`, **không hỗ trợ chia nhánh** (trả `null` ở `trySplit`). Nó có `estimateSize` phản ánh số phần tử còn lại.

### Ví dụ 5 — Countdown Spliterator

Tạo file **CustomTraversalDemo.java**:

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;

public class CustomTraversalDemo {
    static final class Countdown implements Spliterator<Integer> {
        private int current;

        Countdown(int value) {
            current = value;
        }

        @Override
        public boolean tryAdvance(Consumer<? super Integer> action) {
            Objects.requireNonNull(action);

            if (current <= 0) {
                return false;
            }

            action.accept(current--);
            return true;
        }

        @Override
        public Spliterator<Integer> trySplit() {
            return null; // Không hỗ trợ tách.
        }

        @Override
        public long estimateSize() {
            return Math.max(0, current);
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED | NONNULL | IMMUTABLE;
        }

        // forEachRemaining được kế thừa từ Spliterator.
    }

    public static void main(String[] args) {
        Countdown spl = new Countdown(4);

        System.out.println("initialSize=" + spl.estimateSize());

        System.out.println("firstCall=" +
            spl.tryAdvance(x -> System.out.println("step=" + x)));

        spl.forEachRemaining(
            x -> System.out.println("rest=" + x));

        System.out.println("afterSize=" + spl.estimateSize());

        System.out.println("lastCall=" +
            spl.tryAdvance(x -> System.out.println("never=" + x)));
    }
}
```

```bash
javac CustomTraversalDemo.java
java CustomTraversalDemo
```

Đầu ra:

```text
initialSize=4
step=4
firstCall=true
rest=3
rest=2
rest=1
afterSize=0
lastCall=false
```

**Các quyết định thiết kế trong ví dụ:**

1. `Countdown` giữ trạng thái `current`. Khi có phần tử, `tryAdvance` gửi giá trị hiện tại vào action rồi giảm `current`; khi `current <= 0`, nó trả `false`.
2. `forEachRemaining` không cần override: default method tiếp tục gọi `tryAdvance` cho `3,2,1` đến khi nó trả `false`.
3. `trySplit()` trả `null` vì ví dụ chọn cách duyệt tuần tự. Một Spliterator hợp lệ **không bắt buộc** phải chia được.
4. `estimateSize()` trả số lượng phần tử còn lại. `SIZED`/`SUBSIZED` là lời cam kết về độ lớn; việc báo `current` đang giảm giúp thông tin phù hợp khi duyệt.
5. `ORDERED` phù hợp vì thứ tự `4,3,2,1` là cố định. `NONNULL` phù hợp vì mọi phần tử đều là số nguyên, không null. `IMMUTABLE` mô tả nguồn sinh số không bị chỉnh sửa cấu trúc bên ngoài.
6. `action` được kiểm tra `Objects.requireNonNull` để tuân thủ hợp đồng. Nếu action ném ngoại lệ, không dựa vào trạng thái sau đó để duyệt tiếp vì API không bảo đảm hành vi trong trường hợp này.

Ví dụ tạo nguồn ở phạm vi `int` nhỏ; nếu nghiệp vụ cần số rất lớn, thêm điều kiện biên, giải pháp chia song song, hay hỗ trợ `long`, cần thiết kế riêng và kiểm thử đầy đủ.

**Không thêm `CONCURRENT` tùy tiện:** Việc một Spliterator hỗ trợ `trySplit` không có nghĩa nhiều thread được quyền gọi `tryAdvance` đồng thời trên **cùng một đối tượng**. Cơ chế parallel stream thường chia nguồn thành nhiều spliterator và giao cho các phần xử lý riêng, không mặc nhiên chia sẻ cursor duy nhất giữa threads.

## 11. Encounter order, đặc tính và ước lượng số phần tử

### 11.1. ORDERED

Khi có đặc tính `Spliterator.ORDERED`, action do `tryAdvance` hoặc `forEachRemaining` thực hiện theo encounter order của các phần tử thuộc spliterator đó. Với `List` thông thường, thứ tự là thứ tự danh sách.

Với nguồn không ordered, **không có thứ tự encounter được cam kết**. Một lần chạy có thể tình cờ trông ổn định, nhưng không được biến quan sát đó thành giả định nghiệp vụ.

### 11.2. SIZED và estimateSize

`estimateSize()` cho một ước lượng về số phần tử **còn lại**. Khi Spliterator có `SIZED` và nguồn không bị sửa theo cách làm thay đổi contract, kích thước là chính xác theo quy tắc của đặc tính. Nếu không có `SIZED`, đây có thể chỉ là ước lượng.

- `getExactSizeIfKnown()` trả kích thước chính xác khi `SIZED` phù hợp; nếu không biết, thường trả `-1`.
- Không dựa vào `estimateSize()` như một điều kiện thay thế `tryAdvance` cho mọi Spliterator: estimate có thể không chính xác hoặc có thể là `Long.MAX_VALUE` khi không biết.
- Khi một số phần tử đã duyệt, giá trị ước lượng/kích thước có thể thay đổi.

Đối với câu hỏi “còn phần tử thực sự không?”, câu trả lời đáng tin trực tiếp là **boolean của `tryAdvance`**, không phải đoán bằng estimate.

### 11.3. Đừng nhầm trySplit với tryAdvance

| API | Tác động | Trả về |
| --- | --- | --- |
| `tryAdvance(action)` | Tiêu thụ tối đa **một phần tử** và chạy action | `boolean` |
| `forEachRemaining(action)` | Tiêu thụ **mọi phần tử còn lại** | `void` |
| `trySplit()` | Thử tách **một phần công việc còn lại** sang spliterator khác | `Spliterator<T>` hoặc `null` |
| `estimateSize()` | Cung cấp ước lượng số phần tử còn lại | `long` |

**Không gọi `trySplit` để “chuyển tới phần tử tiếp theo”**. Nó không phải một bước duyệt thay thế `tryAdvance` mà là thao tác phân chia nguồn.

## 12. An toàn khi duyệt và thay đổi nguồn

Spliterator có các chính sách phụ thuộc từng nguồn: có nguồn **late-binding**, có nguồn **early-binding**, có nguồn **fail-fast**, và có nguồn được thiết kế **concurrent**. Không có một quy tắc duy nhất áp dụng cho mọi collection.

Một nguyên tắc thực hành an toàn:

> Trong khi đang duyệt một nguồn không hỗ trợ sửa đồng thời, **không thêm/xóa phần tử khỏi cấu trúc nguồn ngay trong action** của `tryAdvance` hoặc `forEachRemaining`.

Ví dụ dưới đây **cố ý minh họa thiết kế sai**:

```java
// KHÔNG CHẠY: mẫu nguy hiểm khi sửa List đang được duyệt.
List<String> names = new ArrayList<>(List.of("A", "B", "C"));
Spliterator<String> spl = names.spliterator();
spl.forEachRemaining(name -> names.add(name + "!"));
```

Với spliterator của `ArrayList`, thay đổi cấu trúc trong khi duyệt có thể gây `ConcurrentModificationException`. Nhưng fail-fast chỉ là cơ chế phát hiện theo khả năng thực thi, **không phải bảo đảm** ứng dụng luôn nhận exception một cách chắc chắn khi có sửa sai. Hành vi cụ thể phụ thuộc implementation và timing.

Thay vào đó, thu thập kết quả **riêng**, rồi mới quyết định có cập nhật nguồn hay không:

```java
// Mã minh họa đầy đủ trong ngữ cảnh có import java.util.*.
List<String> names = new ArrayList<>(List.of("A", "B", "C"));
List<String> transformed = new ArrayList<>();

names.spliterator().forEachRemaining(
    name -> transformed.add(name + "!")
);
// names giữ nguyên; transformed chứa [A!, B!, C!].
```

Ở ví dụ này, action thêm vào **một danh sách khác** trong cùng thread. Nếu muốn xử lý qua parallel stream, thường nên dùng pipeline `map` và `toList`/`collect` thay vì nhiều thread cùng sửa `transformed`.

### 12.1. Thread safety không tự có

Đừng giao **cùng một Spliterator** cho hai thread rồi cùng gọi `tryAdvance` mà không có bảo đảm rõ ràng từ implementation. Phần lớn spliterator không được thiết kế để cùng nhiều thread thao tác trên một cursor.

Nếu cần xử lý đồng thời, `trySplit` cho phép tạo các vùng công việc khác nhau (khi hỗ trợ), nhưng vẫn phải quản lý việc gộp kết quả và tránh race ở action. Trong phần lớn ứng dụng thông thường, `parallelStream()` hoặc `StreamSupport.stream(...)` quản lý chia công việc sẽ ít lỗi hơn tự điều phối threads.

### 12.2. Action ném exception

Cả `tryAdvance` lẫn `forEachRemaining` đều truyền exception do action ném ra về phía caller. Sau đó, trạng thái duyệt **không có bảo đảm để tiếp tục chính xác** theo hợp đồng API. Nếu cần nghiệp vụ khôi phục/đọc lại, hãy xây dựng cơ chế checkpoint trên **nguồn dữ liệu** hoặc tạo lượt duyệt mới, thay vì phụ thuộc vào vị trí của spliterator đã lỗi.

## 13. Khi nào dùng hai phương thức này thay vì Stream?

`Spliterator` là API mức thấp hơn pipeline `Stream`. Nó rất hữu ích khi:

- Bạn đang xây dựng một **nguồn Stream tùy biến** và cần triển khai logic “phần tử tiếp theo”.
- Bạn cần tự đọc **một số lượng phần tử có kiểm soát** và giữ cursor để dùng tiếp.
- Bạn xây dựng adapter sang một API có mô hình callback/tiêu thụ riêng.
- Bạn muốn hiểu hoặc kiểm tra cách một nguồn hỗ trợ duyệt và tách cho xử lý song song.

Với các tác vụ đơn giản như “lọc danh sách”, “map rồi collect”, “tìm phần tử đầu tiên thỏa điều kiện” hoặc “đếm/tính tổng”, Stream API thường rõ ràng và ít lỗi hơn:

```java
// Đoạn minh họa: không cần trực tiếp quản lý spliterator.
List<String> result = names.stream()
    .filter(name -> name.length() >= 2)
    .map(String::toUpperCase)
    .toList();  // Java 16+
```

`names` ở đây là một `List<String>` đã được khai báo. `Stream.toList()` trả danh sách không chỉnh sửa được theo hợp đồng hiện hành.

Nếu cần tạo Stream từ Spliterator tùy biến:

```java
// Đoạn minh họa; spliterator đã được tạo từ một nguồn phù hợp.
Stream<T> stream = StreamSupport.stream(spliterator, false);
```

`false` chỉ định pipeline tuần tự; `true` yêu cầu pipeline parallel. **Chọn parallel không bảo đảm nhanh hơn** và không làm một `trySplit` vốn luôn trả `null` tự nhiên chia được. Cần cân nhắc đặc tính `SIZED`, `ORDERED`, chi phí xử lý và khả năng phân chia thực tế của nguồn.

## 14. Những lỗi thường gặp

### Lỗi 1. Nhầm `tryAdvance` trả phần tử thay vì boolean

`tryAdvance` **không trả phần tử**; nó đưa phần tử vào `Consumer` rồi trả `boolean`. Nếu cần lưu giá trị, có thể dùng holder trong duyệt tuần tự hoặc xem xét API `Iterator`/`Stream.findFirst` phù hợp.

### Lỗi 2. Nghĩ mỗi lần `tryAdvance` lấy cả tập còn lại

Mỗi lần thành công chỉ xử lý **một** phần tử. Muốn duyệt tất cả, dùng vòng `while(tryAdvance(...))` hoặc `forEachRemaining`.

### Lỗi 3. Gọi `forEachRemaining` sau hai lần tryAdvance nhưng kỳ vọng vẫn xử lý từ đầu

Nó bắt đầu từ **vị trí hiện tại**, không reset. Kết quả phụ thuộc các phần tử đã duyệt trước đó.

### Lỗi 4. Gọi `forEachRemaining` nhưng cố `break` bằng return trong lambda

`return` trong một lambda `Consumer` chỉ kết thúc lần xử lý **phần tử hiện tại**; nó không dừng vòng duyệt do `forEachRemaining` điều khiển. Nếu cần dừng sớm, chuyển sang `tryAdvance` kèm điều kiện vòng lặp, hoặc dùng Stream operation hỗ trợ giới hạn/tìm kiếm.

### Lỗi 5. Dùng exception để giả lập break

Sau khi action ném exception, hành vi spliterator tiếp theo không được bảo đảm. Không dùng cơ chế này để duyệt theo trang rồi tiếp tục.

### Lỗi 6. Quên xử lý `trySplit() == null`

Tách có thể thất bại hợp lệ; không được gọi `prefix.forEachRemaining` khi `prefix` là `null`. Kiểm tra trước khi dùng.

### Lỗi 7. Duyệt prefix/suffix rồi làm mất thứ tự nguồn

Với nguồn `ORDERED`, prefix đứng trước suffix. Nếu nghiệp vụ yêu cầu kết quả theo đúng thứ tự, phải thiết kế cách gộp kết quả phù hợp; không tùy ý nối hậu tố trước tiền tố.

### Lỗi 8. Coi forEachRemaining tự chạy parallel

Phương thức này duyệt các phần tử còn lại của **một spliterator** theo hợp đồng, không tự tạo nhiều task. Muốn xử lý phân chia song song, cần `trySplit` và cơ chế thực thi tương ứng hoặc dùng parallel Stream.

### Lỗi 9. Dùng Consumer boxed cho primitive spliterator khi không cần

`OfInt`, `OfLong`, `OfDouble` có các phương thức nhận consumer nguyên thủy, giúp tránh boxing không cần thiết. Ưu tiên `IntConsumer`, `LongConsumer`, `DoubleConsumer` khi làm việc với nguồn primitive lớn.

### Lỗi 10. Sửa collection nguồn trong action

Có thể gây `ConcurrentModificationException` hoặc hành vi không dự đoán được. Tách nguồn và kết quả; không phụ thuộc vào fail-fast như một cơ chế đồng bộ hóa.

### Lỗi 11. Chia sẻ cùng cursor cho nhiều threads

Spliterator thông thường không có cam kết truy cập đồng thời trên một đối tượng. Nên phân chia công việc đúng cách hoặc để Stream API quản lý parallel.

### Lỗi 12. Tự triển khai tryAdvance không tiến cursor

Nếu `tryAdvance` trả `true` mà không làm tiến trạng thái, default `forEachRemaining` có thể chạy vô hạn trên cùng phần tử. Mỗi lần xử lý thành công phải đưa spliterator tiến tới vị trí tiếp theo, hoặc có quy tắc kết thúc đúng đắn.

### Lỗi 13. Báo sai `SIZED` hoặc estimateSize

Nếu gắn `SIZED` mà ước lượng không phản ánh đúng số lượng phần tử còn lại, các thuật toán tiêu thụ Spliterator có thể dựa vào thông tin sai. Khi tự triển khai, chỉ công bố characteristic mà mình thực sự bảo đảm.

## 15. Checklist review và luyện tập

### Checklist dành cho code review

1. `tryAdvance` có thực sự xử lý **tối đa một phần tử** và trả đúng `true/false` không?
2. Khi thành công, cursor có tiến tới phần tử kế tiếp không?
3. `forEachRemaining` chỉ duyệt phần **chưa được tiêu thụ**, không xử lý trùng?
4. Với nguồn `ORDERED`, action có được thực hiện theo encounter order?
5. Nếu `trySplit()` hoạt động, prefix/suffix có bao phủ đúng các phần tử còn lại mà không mất/trùng?
6. Nếu dùng primitive Spliterator, có chọn đúng `IntConsumer/LongConsumer/DoubleConsumer`?
7. Có tránh sửa nguồn, tránh dùng state mutable chia sẻ và tránh gọi đồng thời trên cùng cursor?
8. Nếu action ném exception, code có tránh tiếp tục dựa vào trạng thái không được bảo đảm?
9. Các đặc tính `SIZED`/`ORDERED`/`IMMUTABLE` có phản ánh đúng nguồn thực tế?
10. Với yêu cầu nghiệp vụ ở mức cao, việc dùng trực tiếp Spliterator có đơn giản hơn dùng Stream pipeline không?

### Câu hỏi tự kiểm tra

**Câu 1.** Với `["A", "B", "C"]`, gọi `tryAdvance(print)` một lần rồi `forEachRemaining(print)`. Có những phần tử nào được in?

**Đáp án:** `"A"` được in ở lần gọi đầu, sau đó `"B"` và `"C"`. Mỗi phần tử được xử lý đúng một lần nếu không có hành vi can thiệp.

**Câu 2.** Nếu `tryAdvance` trả `false`, action có được gọi không?

**Đáp án:** Không, vì không còn phần tử nào để xử lý trong lần gọi đó.

**Câu 3.** `forEachRemaining` trả kiểu gì? Nó có cho phép `break` bằng boolean không?

**Đáp án:** Trả `void`; không cung cấp boolean để dừng. Dùng `tryAdvance` nếu cần kiểm soát từng bước.

**Câu 4.** Nếu `trySplit()` trả `null`, spliterator có bị xem là sai không?

**Đáp án:** Không. Nó có thể không hỗ trợ tách hoặc không thể tách tại thời điểm hiện tại.

**Câu 5.** Duyệt `Spliterator.OfInt` nên ưu tiên consumer nào?

**Đáp án:** `IntConsumer`, vì là API chuyên biệt primitive, giúp tránh boxing khi không cần.

**Câu 6.** Khi thực thi một `Consumer` ném exception, ta có thể chắc chắn tiếp tục từ phần tử kế tiếp bằng cùng Spliterator không?

**Đáp án:** Không. Javadoc không bảo đảm hành vi tiếp theo của spliterator sau exception do action ném ra.

**Câu 7.** Có phải `forEachRemaining` tự chia việc ra nhiều thread?

**Đáp án:** Không. Nó duyệt toàn bộ phần còn lại của spliterator theo hợp đồng, không phải công cụ khởi chạy các task parallel.

**Câu 8.** Vì sao mã `while (spliterator.tryAdvance(action)) {}` có thể không bao giờ kết thúc khi viết custom Spliterator sai?

**Đáp án:** Nếu `tryAdvance` không làm tiến trạng thái nhưng cứ trả `true`, vòng lặp sẽ xử lý lại cùng dữ liệu vô hạn.

**Câu 9.** Lấy một phần tử trước, rồi gọi `trySplit`: phần tử vừa lấy có nằm trong prefix mới không?

**Đáp án:** Không. Việc tách chỉ áp dụng cho các phần tử **chưa bị tiêu thụ** của spliterator tại thời điểm gọi.

## 16. Tài liệu tham khảo API hiện hành

- [Oracle Java SE 26 — Spliterator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.html): mô tả `tryAdvance`, `forEachRemaining`, `trySplit`, `ORDERED`, `SIZED` và hợp đồng truy cập nguồn.
- [Oracle Java SE 26 — Spliterator.OfPrimitive](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.OfPrimitive.html): phương thức primitive và default `forEachRemaining`.
- [Oracle Java SE 26 — Spliterator.OfInt](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.OfInt.html): overload nhận `IntConsumer`, `Consumer` và lưu ý tránh boxing.
- [Oracle Java SE 26 — Spliterators](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterators.html): tiện ích và lớp trợ giúp cho implementation của Spliterator.
- [Oracle Java SE 26 — StreamSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/StreamSupport.html): cách tạo Stream từ Spliterator khi cần.

**Kết luận:** `tryAdvance` là công cụ tiến **một bước** và báo `boolean`; `forEachRemaining` duyệt **tất cả bước còn lại** và không trả trạng thái. Cả hai dùng chung cursor và phải tôn trọng encounter order nếu `ORDERED`. Khi cần phân chia nguồn, `trySplit` tách phần việc còn lại; khi cần duyệt số nguyên thủy, chọn phương thức chuyên biệt `OfInt/OfLong/OfDouble`. Hiểu đúng sự tiêu thụ từng bước sẽ giúp tránh xử lý trùng, bỏ sót phần tử và lỗi khi viết Spliterator tùy biến.