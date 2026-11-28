# Stream Gatherers: biến đổi trung gian tùy chỉnh trong Java 27

Một pipeline Stream thường bao gồm nguồn dữ liệu, các phép biến đổi trung gian và một thao tác kết thúc. Những phép như `map`, `filter`, `flatMap` và `distinct` giải quyết được nhiều bài toán, nhưng không phải lúc nào cũng đủ. Chẳng hạn:

- Gom các phần tử liên tiếp thành từng **cửa sổ** để tính trung bình trượt.
- Tính **tổng lũy kế** sau mỗi phần tử thay vì chỉ lấy tổng cuối cùng.
- Gộp những bản ghi có cùng khóa **liên tiếp** mà không phải thu thập toàn bộ dữ liệu.
- Phát ra nhiều hoặc ít phần tử đầu ra hơn số phần tử đầu vào.
- Dừng đọc dữ liệu khi điều kiện nghiệp vụ xuất hiện.
- Biến đổi các phần tử bằng nhiều tác vụ đồng thời nhưng giới hạn số tác vụ đang chạy.

**Stream Gatherers** cung cấp một điểm mở rộng (*extension point*) cho các phép biến đổi trung gian như vậy. Trong Java 27, API này gồm `Stream.gather(Gatherer)`, interface `Gatherer<T,A,R>` và các triển khai sẵn có trong lớp `Gatherers`.

**Trạng thái phiên bản:** Stream Gatherers được chuẩn hóa chính thức theo **JEP 485 trong JDK 24** và tiếp tục có mặt trong Java SE 27. Từ JDK 24 trở đi, các ví dụ sử dụng API này **không cần** `--enable-preview`. Tài liệu tham khảo chính thức: [Gatherer (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.html), [Gatherers (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherers.html), [Stream.gather (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html#gather(java.util.stream.Gatherer)).

## 1. Gatherer nằm ở đâu trong Stream pipeline?

Ví dụ một pipeline thông thường:

~~~~java
import java.util.List;

List<Integer> result = List.of(1, 2, 3, 4, 5).stream()
        .filter(n -> n % 2 == 1)
        .map(n -> n * 10)
        .toList();

System.out.println(result); // [10, 30, 50]
~~~~

`filter` giữ hoặc bỏ từng phần tử, `map` biến một phần tử thành một phần tử, còn `toList` **kết thúc** pipeline và trả một danh sách. Khi cần một phép biến đổi có **bộ nhớ về phần tử trước đó**, nhiều đầu ra hoặc hành động ở **cuối luồng**, việc chỉ phối hợp `map` với `filter` có thể khiến code trở nên vòng vèo.

Với Gatherer, ta đưa phép biến đổi riêng vào **vị trí trung gian**:

~~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<List<Integer>> batches = List.of(1, 2, 3, 4, 5, 6, 7).stream()
        .gather(Gatherers.windowFixed(3))
        .toList();

System.out.println(batches);
// [[1, 2, 3], [4, 5, 6], [7]]
~~~~

Sơ đồ:

~~~~text
Nguồn Stream<T>
      |
      v
  filter / map
      |
      v
  gather(Gatherer<T, A, R>)
      |   - initializer: tạo state A
      |   - integrator: nhận T, đẩy 0..n giá trị R
      |   - combiner: ghép state khi hỗ trợ parallel
      |   - finisher: có thể phát ra kết quả cuối
      v
     Stream<R>
      |
      v
   map / limit / toList / collect / ...
~~~~

`gather` **không phải** một terminal operation: nó trả về một `Stream<R>` mới, có thể nối tiếp các bước xử lý thông thường. Nó cũng tuân theo tính **lazy** của Stream: thao tác chỉ thực sự chạy khi có một terminal operation và pipeline chỉ yêu cầu những phần tử cần thiết.

### 1.1. Khi nào dùng Gatherer thay vì các API sẵn có?

| Yêu cầu | Lựa chọn thông thường | Khi Gatherer có ích |
| --- | --- | --- |
| Một đầu vào thành một đầu ra | `map` | Chỉ cần Gatherer khi đang xây dựng một tổ hợp tùy chỉnh lớn hơn |
| Giữ hoặc bỏ một phần tử | `filter` | Không cần Gatherer nếu không dùng state hoặc logic đặc biệt |
| Mở rộng mỗi phần tử thành nhiều phần tử | `flatMap` | Khi kết quả phụ thuộc phần tử **trước/sau** hoặc state chung |
| Loại phần tử trùng trong toàn bộ luồng | `distinct` | Khi chỉ muốn gộp các **phần tử trùng liên tiếp** |
| Lấy N phần tử đầu | `limit` | Khi điểm dừng phụ thuộc phép tích hợp tùy chỉnh |
| Tính tổng hoặc gom collection ở cuối | `reduce`, `collect` | Khi cần phát ra kết quả như **phần tử của Stream** để xử lý tiếp |
| Chia đoạn cố định/trượt, scan lũy kế | Không có một intermediate operation tương đương trực tiếp | Sử dụng `Gatherers.windowFixed`, `windowSliding`, `scan` |
| Xử lý mapper đồng thời theo giới hạn | Tự điều phối tác vụ hoặc executor | Sử dụng `Gatherers.mapConcurrent` với virtual threads |

**Nguyên tắc:** dùng `map`/`filter`/`collect` khi chúng đã biểu đạt được nghiệp vụ rõ ràng. Gatherer là công cụ cho những phép trung gian chưa được Stream cung cấp trực tiếp, không phải cách thay thế mọi thao tác cũ.

## 2. Năm Gatherer có sẵn trong Java 27

Lớp `java.util.stream.Gatherers` hiện có năm phương thức factory chính:

| Phương thức | Nhận | Phát ra | Mục đích |
| --- | --- | --- | --- |
| `windowFixed(int size)` | Các phần tử đơn lẻ | Các `List<T>` theo lô, không chồng lấp | Batch theo kích thước |
| `windowSliding(int size)` | Các phần tử đơn lẻ | Các `List<T>` trượt, có chồng lấp | Phân tích chuỗi thời gian, trung bình trượt |
| `fold(initial, folder)` | Nhiều phần tử | Một kết quả gộp duy nhất | Tích lũy có thứ tự, sau đó vẫn xử lý Stream |
| `scan(initial, scanner)` | Các phần tử tuần tự | Một kết quả tích lũy cho mỗi phần tử | Tổng lũy kế, lịch sử trạng thái |
| `mapConcurrent(maxConcurrency, mapper)` | Các phần tử đơn lẻ | Kết quả mapper với mức đồng thời giới hạn | Tác vụ độc lập thường có chờ I/O |

Các phương thức là API chính thức, thuộc `java.base`; không cần thư viện ngoài. Những tham số kích thước cửa sổ và mức đồng thời phải **từ 1 trở lên**.

### 2.1. `windowFixed`: chia dữ liệu thành lô cố định

~~~~java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FixedWindowDemo {
    public static void main(String[] args) {
        List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
                .gather(Gatherers.windowFixed(3))
                .toList();

        System.out.println(windows);
        // [[1, 2, 3], [4, 5, 6], [7, 8]]
    }
}
~~~~

- Các cửa sổ **không chồng lấp** và giữ encounter order của nguồn.
- Nếu còn phần tử nhưng chưa đủ một cửa sổ ở cuối, phần còn lại vẫn được phát ra.
- Nếu nguồn **rỗng**, kết quả không có cửa sổ nào.
- Cửa sổ được phát ra là **unmodifiable List**; không cho gọi `add` hoặc `set` lên cửa sổ.
- Chọn `windowSize < 1` sẽ gây `IllegalArgumentException`.

Ví dụ một đơn hàng có 8 mã hàng, mỗi yêu cầu gửi tối đa 3 mã:

~~~~java
List<String> ids = List.of(
        "P01", "P02", "P03", "P04", "P05", "P06", "P07", "P08");

List<List<String>> requests = ids.stream()
        .gather(Gatherers.windowFixed(3))
        .toList();

// [[P01, P02, P03], [P04, P05, P06], [P07, P08]]
~~~~

**Lưu ý hiệu năng:** Javadoc cho biết cửa sổ có thể được cấp phát liền mạch và sớm vì mục tiêu hiệu năng. Chọn kích thước cửa sổ rất lớn với một nguồn nhỏ vẫn có thể làm tốn bộ nhớ; không để đầu vào không tin cậy tùy ý quyết định `windowSize` mà không giới hạn.

### 2.2. `windowSliding`: cửa sổ trượt có chồng lấp

~~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<List<Integer>> windows = List.of(10, 20, 30, 40, 50).stream()
        .gather(Gatherers.windowSliding(3))
        .toList();

System.out.println(windows);
// [[10, 20, 30], [20, 30, 40], [30, 40, 50]]
~~~~

Mỗi cửa sổ có kích thước 3 chứa hai phần tử cuối của cửa sổ trước và thêm một phần tử mới. Một trường hợp điển hình là trung bình trượt:

~~~~java
List<Double> averages = List.of(10, 20, 30, 40, 50).stream()
        .gather(Gatherers.windowSliding(3))
        .map(window -> window.stream()
                .mapToInt(Integer::intValue)
                .average()
                .orElseThrow())
        .toList();

System.out.println(averages); // [20.0, 30.0, 40.0]
~~~~

Khác `windowFixed`, `windowSliding` không phát từng cửa sổ thiếu phần tử **trong khi** chưa đạt kích thước yêu cầu. Nhưng có ngoại lệ quan trọng: **nếu toàn bộ Stream có ít phần tử hơn `windowSize`**, Gatherer phát ra **một cửa sổ chứa tất cả phần tử** (nếu không rỗng).

~~~~java
System.out.println(
        List.of(1, 2).stream()
                .gather(Gatherers.windowSliding(5))
                .toList());
// [[1, 2]]

System.out.println(
        Stream.<Integer>empty()
                .gather(Gatherers.windowSliding(5))
                .toList());
// []
~~~~

Cửa sổ trượt cũng là List unmodifiable; số phần tử của nguồn và kích thước cửa sổ ảnh hưởng lớn đến số lượng output. Với N phần tử và cửa sổ W, khi N ≥ W sẽ có **N - W + 1** cửa sổ. Nếu xử lý toàn bộ Stream và mỗi cửa sổ có thể chứa nhiều object, hãy cân nhắc chi phí bộ nhớ và CPU của các bước downstream.

### 2.3. `scan`: kết quả tích lũy sau mỗi phần tử

`scan` nhận một `Supplier<R>` tạo trạng thái ban đầu và hàm `BiFunction<R,T,R>` áp dụng dữ liệu mới. Nó phát ra **giá trị mới sau mỗi lần nhận phần tử**:

~~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<Integer> runningTotals = List.of(3, 4, 5).stream()
        .gather(Gatherers.scan(
                () -> 0,
                Integer::sum))
        .toList();

System.out.println(runningTotals); // [3, 7, 12]
~~~~

**Giá trị khởi tạo 0 không được phát ra riêng**: chỉ có ba output ứng với ba input. Với nguồn rỗng, `scan` không phát phần tử nào.

Trong nghiệp vụ, có thể tính mức sử dụng hạn mức sau từng giao dịch:

~~~~java
record Balance(long amount) {
}

List<Balance> balances = List.of(100L, -20L, 40L).stream()
        .gather(Gatherers.scan(
                () -> new Balance(0L),
                (current, delta) ->
                        new Balance(Math.addExact(current.amount(), delta))))
        .toList();

System.out.println(balances);
// [Balance[amount=100], Balance[amount=80], Balance[amount=120]]
~~~~

`scan` là phép tích lũy **phụ thuộc thứ tự**. Nếu áp dụng cho giao dịch tài chính, cần lựa chọn đơn vị số và xử lý tràn một cách phù hợp; ví dụ dùng `Math.addExact` để không im lặng tràn số nguyên.

### 2.4. `fold`: tích lũy một kết quả ở cuối nhưng vẫn là intermediate operation

`fold` cũng lấy trạng thái khởi tạo và hàm tích lũy, nhưng **không phát một giá trị cho mỗi input**. Nó tạo **một output tổng hợp** khi kết thúc upstream nếu không có exception.

~~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<String> grouped = List.of("a", "b", "c").stream()
        .gather(Gatherers.fold(
                () -> new StringBuilder(),
                (builder, text) -> builder.append(text.toUpperCase())))
        .map(StringBuilder::toString)
        .toList();

System.out.println(grouped); // [ABC]
~~~~

Trong ví dụ, `fold` tích lũy vào một `StringBuilder` của lần đánh giá pipeline, sau đó `map` chuyển kết quả thành String. Vì Gatherer trả về Stream, ta còn có thể nối thêm các intermediate operation sau `fold`.

Khác nhau:

| Tiêu chí | `scan` | `fold` |
| --- | --- | --- |
| Số output với N input | N output | Một output tổng hợp khi hoàn tất thành công |
| Thời điểm tạo output | Sau từng input | Khi kết thúc upstream |
| Mục đích chính | Quan sát quá trình biến đổi trạng thái | Lấy kết quả gộp để xử lý tiếp như phần tử Stream |
| So với `reduce`/`collect` | Không phải terminal | `fold` vẫn là intermediate, còn `reduce`/`collect` là terminal |

Không nên mặc định `fold` là cách nhanh hơn `reduce`. Nếu chỉ cần một giá trị kết thúc, `reduce` hoặc `collect` thường đơn giản hơn. `fold` hữu ích khi cần phép tích lũy **phụ thuộc thứ tự** như một thành phần bên trong pipeline lớn hơn.

### 2.5. `mapConcurrent`: mapper đồng thời với giới hạn

`Gatherers.mapConcurrent(int maxConcurrency, Function mapper)` thực hiện mapper bằng **virtual threads** và hạn chế số tác vụ đồng thời theo tham số. Kết quả được đưa tới downstream theo **encounter order của nguồn**, dù thời điểm hoàn thành các mapper có thể khác nhau.

Một chương trình hoàn chỉnh:

~~~~java
import java.util.List;
import java.util.stream.Gatherers;

public class ConcurrentLookupDemo {
    static String lookup(String itemCode) {
        try {
            // Mô phỏng chờ phản hồi I/O; ví dụ độc lập, không gọi mạng thật.
            Thread.sleep(20);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Lookup was interrupted", exception);
        }
        return "stock:" + itemCode;
    }

    public static void main(String[] args) {
        List<String> result = List.of("P01", "P02", "P03", "P04")
                .stream()
                .gather(Gatherers.mapConcurrent(3, ConcurrentLookupDemo::lookup))
                .toList();

        System.out.println(result);
        // [stock:P01, stock:P02, stock:P03, stock:P04]
    }
}
~~~~

Các điểm quan trọng:

- `maxConcurrency` phải **≥ 1**, nếu không ném `IllegalArgumentException`.
- Mapper được thực thi đồng thời, nên phải **an toàn luồng** nếu chia sẻ tài nguyên hoặc trạng thái.
- `mapConcurrent` giữ thứ tự **kết quả đầu ra** nhưng không bảo đảm thứ tự **bắt đầu, hoàn thành hay tác dụng phụ** của mapper.
- Khi downstream không còn muốn phần tử, các tác vụ đang chạy có thể được **yêu cầu hủy theo best effort**; không giả định chúng dừng tức thì.
- Nếu một mapper hoàn thành với exception đúng lúc kết quả của nó cần được phát ra, exception được truyền lên theo quy tắc API, dưới dạng `RuntimeException`; các tác vụ còn lại được hủy.
- Virtual threads thường hữu ích khi công việc có **thời gian chờ I/O**. Không tự suy ra rằng song song hóa mã tính toán CPU-heavy sẽ nhanh hơn.

Không dùng `mapConcurrent` để gửi các thao tác nghiệp vụ có tác dụng phụ **bắt buộc đúng một lần** nếu chỉ dựa vào việc xử lý và hủy tác vụ của Gatherer. Các giao dịch bên ngoài cần cơ chế idempotency, timeout và kiểm soát lỗi riêng.

## 3. Cấu trúc một Gatherer tùy chỉnh

Interface `Gatherer<T,A,R>` có ba tham số kiểu:

| Tham số | Ý nghĩa |
| --- | --- |
| `T` | Kiểu phần tử **đầu vào** của bước gather |
| `A` | Kiểu **trạng thái trung gian**; có thể mutable, nội bộ của Gatherer |
| `R` | Kiểu phần tử **đầu ra** được đẩy xuống pipeline |

Một Gatherer được mô tả bằng tối đa bốn thành phần:

| Thành phần | Kiểu ý nghĩa | Nhiệm vụ |
| --- | --- | --- |
| `initializer` | `Supplier<A>` | Tạo state mới cho mỗi lần thực thi/nhánh xử lý |
| `integrator` | `Gatherer.Integrator<A,T,R>` | Nhận một `T`, cập nhật state và có thể phát 0, 1 hoặc nhiều `R` |
| `combiner` | `BinaryOperator<A>` | Kết hợp state của các phân đoạn nếu Gatherer hỗ trợ xử lý song song |
| `finisher` | `BiConsumer<A, Downstream<? super R>>` | Xử lý state còn lại hoặc phát kết quả khi kết thúc upstream |

Một Gatherer không nhất thiết phải tự định nghĩa đầy đủ cả bốn. `Gatherer.ofSequential(...)` cung cấp nhiều overload cho Gatherer **tuần tự**; `Gatherer.of(...)` hỗ trợ Gatherer **có khả năng song song** khi cung cấp combiner tương ứng. Với trường hợp không cần state hoặc không cần finisher, có thể dùng overload ngắn.

### 3.1. Vòng đời từ góc nhìn logic

Một mô hình tư duy đơn giản:

~~~~text
                    initializer()
                         |
                         v
                    state mới A
                         |
       phần tử T ------> integrator(state, T, downstream)
                               |                  |
                               | cập nhật A       +--> push(R) 0..n lần
                               |
                         lặp theo nhu cầu
                               |
                    hết upstream hoặc dừng
                               |
                               v
                     finisher(state, downstream)
                               |
                               v
                        downstream / terminal
~~~~

Đây là **mô hình ngữ nghĩa**, không cam kết chính xác số lần gọi từng phương thức. Trong một pipeline song song, engine có thể tạo nhiều state độc lập, xử lý các phân đoạn rồi kết hợp chúng. Các thành phần có giá trị mặc định phù hợp có thể được engine tối ưu hóa và không nhất thiết được gọi vật lý theo đúng sơ đồ.

**Cảnh báo quan trọng:** không giữ hoặc chia sẻ tham chiếu đến `state` hay đối tượng `Gatherer.Downstream` ra bên ngoài thời gian callback đang được gọi. Cả hai là thành phần do runtime điều phối cho một phép đánh giá, không phải dịch vụ dùng chung hay thứ để lưu vào biến toàn cục.

### 3.2. Integrator điều khiển việc đẩy kết quả và dừng sớm

Integrator nhận ba đối số: `state`, `element` và `downstream`.

~~~~java
(state, element, downstream) -> {
    // Có thể cập nhật state và quyết định có gửi element hay không.
    return downstream.push(element);
}
~~~~

- `downstream.push(result)` gửi một phần tử tới bước tiếp theo.
- Giá trị trả về `boolean` của `push` biểu thị downstream có muốn nhận thêm phần tử hay không.
- Giá trị `boolean` mà `integrator` trả về báo cho bộ xử lý có tiếp tục lấy các phần tử từ upstream hay không.
- Nếu `integrator` trả `false`, phép xử lý có thể **short-circuit** như thể không còn upstream; các phần tử tiếp theo không cần được xử lý.
- Khi không muốn phát kết quả từ một input nhưng vẫn tiếp tục, integrator có thể trả `true` mà không gọi `push`.

Đừng trả `true` sau khi `downstream.push` đã báo `false` nếu Gatherer của bạn cần tôn trọng việc downstream dừng. Với Gatherer có thể dừng sớm, thường chuyển trực tiếp kết quả của `push` vào giá trị trả về của integrator.

### 3.3. Greedy integrator là gì?

`Gatherer.Integrator.ofGreedy(...)` tạo một integrator được khai báo là **không short-circuit upstream**. Runtime có thể tận dụng đặc điểm này để tối ưu pipeline, nhưng do đó một Greedy integrator **không phù hợp** khi bạn muốn dừng ở điều kiện bất kỳ hoặc dừng do downstream không cần thêm dữ liệu.

Chỉ dùng Greedy nếu hợp đồng của phép biến đổi thật sự không tự cắt ngắn upstream. Không biến một integrator có khả năng trả false thành Greedy chỉ để “tăng tốc”.

## 4. Custom Gatherer không có state: dừng ở dấu mốc

Giả sử dãy dữ liệu cảm biến bắt đầu bằng những giá trị không âm; một số âm có nghĩa là nguồn đã gửi **dấu kết thúc**, và các phần tử sau dấu đó không còn hợp lệ cho lần đọc này.

~~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class StopAtMarkerDemo {
    static Gatherer<Integer, ?, Integer> untilNegative() {
        return Gatherer.<Integer, Integer>ofSequential(
                (ignored, number, downstream) ->
                        number >= 0 && downstream.push(number));
    }

    public static void main(String[] args) {
        List<Integer> values = Stream.of(4, 7, 2, -1, 99, 100)
                .gather(untilNegative())
                .toList();

        System.out.println(values); // [4, 7, 2]
    }
}
~~~~

Trong ví dụ:

1. `Gatherer.ofSequential` nhận một integrator không có state, sử dụng loại state `Void` nội bộ.
2. Nếu số không âm, nó được đưa xuống downstream.
3. Nếu gặp số âm, biểu thức trả `false` và dừng phép gather.
4. Nếu downstream không nhận thêm phần tử, kết quả `downstream.push` cũng có thể trả `false`.

Với bài toán chỉ cần lấy tiền tố theo điều kiện thông thường, `Stream.takeWhile` cũng là lựa chọn tốt. Ví dụ này nhằm cho thấy **cơ chế short-circuit mà custom Gatherer có thể sử dụng khi kết hợp nhiều quy tắc hơn**.

**Hợp đồng input:** đoạn mã giả định phần tử `Integer` không null. Nếu nguồn có thể chứa null, cần định nghĩa chính sách và kiểm tra trước khi so sánh `number >= 0` để tránh unboxing gây `NullPointerException`.

## 5. Custom Gatherer có state: bỏ trùng chỉ ở các phần tử kề nhau

`Stream.distinct()` loại bỏ các phần tử trùng trong **toàn bộ** Stream; đôi khi nghiệp vụ lại muốn chỉ gộp các kết quả **liên tiếp giống nhau**. Ví dụ danh sách tín hiệu:

~~~~text
Input:   [A, A, B, B, A, A, C]
Output:  [A, B, A, C]
~~~~

Ta giữ state gồm giá trị gần nhất và cờ nhận biết đã có giá trị hay chưa:

~~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

public class AdjacentDistinctDemo {
    static <T> Gatherer<T, ?, T> distinctAdjacent() {
        class State {
            T previous;
            boolean seen;
        }

        return Gatherer.<T, State, T>ofSequential(
                State::new,
                (state, current, downstream) -> {
                    if (state.seen && Objects.equals(state.previous, current)) {
                        return true; // Bỏ giá trị lặp kề nhau, tiếp tục đọc.
                    }

                    state.seen = true;
                    state.previous = current;
                    return downstream.push(current);
                });
    }

    public static void main(String[] args) {
        List<String> events = List.of("A", "A", "B", "B", "A", "A", "C");

        List<String> result = events.stream()
                .gather(distinctAdjacent())
                .toList();

        System.out.println(result); // [A, B, A, C]
    }
}
~~~~

**Vì sao không lưu state bên ngoài?** Mỗi lần thực thi Gatherer cần một state độc lập. Dùng `State::new` để runtime tạo state cho từng phép đánh giá, thay vì khai báo biến `static` chứa `previous` dễ gây sai khi nhiều request hoặc nhiều pipeline cùng chạy.

Cờ `seen` là cần thiết nếu muốn phân biệt “chưa có phần tử trước đó” với “đã thấy phần tử null”. Nhờ `Objects.equals`, thuật toán cũng có ngữ nghĩa được xác định khi nguồn có null, miễn là downstream và các bước sau chấp nhận null. Ví dụ chính sử dụng `List.of` nên bản thân nguồn không chứa null.

**So sánh với `distinct()`:**

~~~~java
List<String> input = List.of("A", "A", "B", "A");

System.out.println(input.stream().distinct().toList());
// [A, B]

System.out.println(input.stream().gather(distinctAdjacent()).toList());
// [A, B, A]
~~~~

`distinctAdjacent()` có thể xử lý một Stream dài mà chỉ giữ **giá trị trước đó**. `distinct()` có thể cần lưu tập các giá trị đã gặp. Hai phép không tương đương; chọn theo yêu cầu loại trùng của nghiệp vụ.

### 5.1. Vì sao dùng `ofSequential` thay vì tự viết combiner?

Kết quả phụ thuộc quan hệ giữa phần tử cuối của phân đoạn trước và phần tử đầu của phân đoạn sau. Nếu xử lý các phân đoạn song song, một combiner đúng phải biết cách giải quyết ranh giới ấy. Việc chỉ gộp các state “giá trị gần nhất” **không đủ** để bảo toàn kết quả.

`Gatherer.ofSequential` cố ý khai báo một Gatherer không có combiner có khả năng song song. Nó vẫn giữ kết quả đúng theo thứ tự cho ví dụ trên, kể cả nếu nguồn của pipeline được đánh dấu `parallel()`: công đoạn Gatherer này phải được đánh giá tuần tự theo hợp đồng.

## 6. Custom Gatherer có finisher: nhóm các bản ghi liên tiếp theo khóa

Để hiểu `finisher`, xét chuỗi đọc cảm biến theo thứ tự thời gian:

~~~~text
(A, 3), (A, 4), (B, 9), (B, 11), (A, 5)
      |
      v
Run(A, [3,4]), Run(B, [9,11]), Run(A, [5])
~~~~

Yêu cầu là **gộp các bản ghi có cùng sensor ID liền nhau**, không gom tất cả bản ghi của A ở mọi vị trí. Mỗi khi ID thay đổi, Gatherer phát nhóm cũ. Khi upstream kết thúc, phải phát **nhóm còn lại** bằng finisher.

Chương trình sau có thể lưu thành `ConsecutiveGroupDemo.java`:

~~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Gatherer;

record Reading(String sensorId, int value) {
    Reading {
        Objects.requireNonNull(sensorId, "sensorId");
    }
}

record SensorRun(String sensorId, List<Integer> values) {
}

public class ConsecutiveGroupDemo {
    static Gatherer<Reading, ?, SensorRun> groupConsecutive() {
        class State {
            String sensorId;
            final List<Integer> values = new ArrayList<>();
        }

        return Gatherer.<Reading, State, SensorRun>ofSequential(
                State::new,
                (state, reading, downstream) -> {
                    Objects.requireNonNull(reading, "reading");

                    if (!state.values.isEmpty()
                            && !state.sensorId.equals(reading.sensorId())) {

                        SensorRun completed = new SensorRun(
                                state.sensorId,
                                List.copyOf(state.values));

                        state.values.clear();
                        if (!downstream.push(completed)) {
                            return false;
                        }
                    }

                    state.sensorId = reading.sensorId();
                    state.values.add(reading.value());
                    return true;
                },
                (state, downstream) -> {
                    if (!state.values.isEmpty()) {
                        downstream.push(new SensorRun(
                                state.sensorId,
                                List.copyOf(state.values)));
                    }
                });
    }

    public static void main(String[] args) {
        List<Reading> input = List.of(
                new Reading("A", 3),
                new Reading("A", 4),
                new Reading("B", 9),
                new Reading("B", 11),
                new Reading("A", 5));

        List<SensorRun> runs = input.stream()
                .gather(groupConsecutive())
                .toList();

        runs.forEach(System.out::println);
        // SensorRun[sensorId=A, values=[3, 4]]
        // SensorRun[sensorId=B, values=[9, 11]]
        // SensorRun[sensorId=A, values=[5]]
    }
}
~~~~

Đọc kỹ ba phần:

1. **Initializer:** `State::new` tạo buffer mới.
2. **Integrator:** nếu khóa thay đổi, copy buffer thành `SensorRun` rồi `downstream.push`, sau đó bắt đầu nhóm tiếp theo.
3. **Finisher:** nếu còn buffer khi upstream kết thúc, phát nhóm cuối cùng.

`List.copyOf` bảo đảm mỗi nhóm output không chia sẻ **cấu trúc mutable** của `state.values`. Nếu push trực tiếp `state.values` rồi gọi `clear()` để dùng lại, dữ liệu mà downstream nhận có thể bị thay đổi hoặc rỗng ngoài ý muốn.

**Chi tiết short-circuit:** integrator làm rỗng buffer **trước khi** gọi `push`. Nếu `push` trả `false` và finisher vẫn được gọi, buffer không còn nhóm đã gửi để phát trùng. Thiết kế state và finisher phải tính đến đường kết thúc sớm, không chỉ trường hợp tiêu thụ toàn bộ nguồn.

Trong ví dụ, mỗi nhóm chỉ bắt đầu nếu có một bản ghi mới; stream rỗng cho kết quả rỗng. Nếu một nhóm có hàng triệu bản ghi liên tiếp, buffer có thể tăng tương ứng. Ứng dụng thực tế có thể cần giới hạn kích thước nhóm, phát ra từng khối, hoặc phân vùng dữ liệu theo thời gian tùy mục tiêu.

## 7. Combiner và khả năng xử lý song song

Khi xử lý một Stream song song, runtime có thể chia dữ liệu thành các phân đoạn. Với Gatherer có state, mỗi phân đoạn cần trạng thái riêng; **combiner** quyết định cách gộp hai state đã xử lý để thu được kết quả tương đương với xử lý tuần tự.

Không thể chỉ thêm một combiner bất kỳ rồi xem thuật toán là song song đúng. Combiner phải bảo toàn ngữ nghĩa **theo encounter order** nếu kết quả phụ thuộc thứ tự, tương thích với initializer và integrator, đồng thời không giữ tham chiếu state để sửa sau khi runtime bàn giao cho giai đoạn tiếp theo.

### 7.1. Ví dụ có combiner: tổng số nguyên thành một phần tử Stream

Với phép cộng các số nguyên nhỏ không gây tràn, state của từng phân đoạn có thể lưu **tổng cục bộ** rồi cộng các tổng ấy. Ví dụ minh họa đầy đủ bốn thành phần:

~~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class ParallelGathererDemo {
    static Gatherer<Integer, ?, Long> sumAsElement() {
        class State {
            long total;
        }

        return Gatherer.<Integer, State, Long>of(
                State::new,
                Gatherer.Integrator.ofGreedy(
                        (state, value, downstream) -> {
                            state.total = Math.addExact(state.total, value);
                            return true;
                        }),
                (left, right) -> {
                    left.total = Math.addExact(left.total, right.total);
                    return left;
                },
                (state, downstream) ->
                        downstream.push(state.total));
    }

    public static void main(String[] args) {
        List<Long> totals = Stream.of(1, 2, 3, 4, 5)
                .parallel()
                .gather(sumAsElement())
                .toList();

        System.out.println(totals); // [15]
    }
}
~~~~

Các thành phần:

- `State::new` tạo tổng ban đầu bằng 0 cho mỗi phân đoạn.
- Integrator là **Greedy** vì nó không chủ động dừng upstream và không phát kết quả trong lúc tích lũy.
- Combiner cộng hai tổng cục bộ để trả một state chứa tổng đã gộp.
- Finisher phát đúng **một** `Long` tổng hợp khi hoàn tất.

Với số rất lớn có thể tràn, `Math.addExact` phát hiện lỗi. Khi dữ liệu có số âm/dương lớn, thứ tự cộng ở các phân đoạn có thể dẫn đến thời điểm phát hiện tràn khác nhau; đừng coi kết quả là tương đương trong mọi trường hợp có tràn. Nếu cần tổng chính xác ngoài phạm vi `long`, dùng kiểu số có miền biểu diễn phù hợp như `BigInteger`.

**Lưu ý mục đích:** ví dụ này minh họa cấu trúc combiner. Để tính tổng thông thường, `mapToLong(...).sum()`, `reduce` hoặc `collect` vẫn đơn giản hơn. Đồng thời, cung cấp combiner chỉ khiến Gatherer **có khả năng** xử lý song song; runtime không cam kết mọi lần đánh giá đều thực sự chạy song song hoặc nhanh hơn.

### 7.2. Vì sao Gatherer phụ thuộc thứ tự khó song song?

Xét phép nhóm các bản ghi liên tiếp:

~~~~text
Phân đoạn 1: A, A, B
Phân đoạn 2: B, B, C
~~~~

Nếu mỗi phân đoạn phát ra kết quả quá sớm, hai nhóm B ở hai phía ranh giới có thể bị chia thành hai nhóm dù trong toàn bộ nguồn chúng liên tiếp nhau. Một combiner đúng phải có khả năng giữ đủ thông tin ranh giới và kết hợp chúng **trước khi** xuất ra kết quả cuối cùng.

Vì vậy, `ofSequential` thường là lựa chọn an toàn và minh bạch cho phép biến đổi phụ thuộc thứ tự, nhất là khi thuật toán cần đẩy kết quả ngay hoặc dừng sớm. Chỉ thiết kế combiner khi chứng minh được ngữ nghĩa chính xác và có nhu cầu hiệu năng thực tế.

## 8. Ghép nhiều Gatherer bằng `andThen`

Interface `Gatherer` có phương thức `andThen`, dùng để hợp nhất logic của hai Gatherer thành một Gatherer:

~~~~java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererCompositionDemo {
    public static void main(String[] args) {
        Gatherer<Integer, ?, List<Integer>> pairs =
                Gatherers.windowFixed(2);

        Gatherer<List<Integer>, ?, Integer> sumEachWindow =
                Gatherer.<List<Integer>, Integer>of(
                        (ignored, batch, downstream) ->
                                downstream.push(
                                        batch.stream()
                                                .mapToInt(Integer::intValue)
                                                .sum()));

        List<Integer> sums = Stream.of(1, 2, 3, 4, 5)
                .gather(pairs.andThen(sumEachWindow))
                .toList();

        System.out.println(sums); // [3, 7, 5]
    }
}
~~~~

`pairs` biến `Integer` thành `List<Integer>`, còn `sumEachWindow` biến mỗi list thành `Integer`. `andThen` nối hai biến đổi, tương ứng `Gatherer<Integer, ?, Integer>`.

Nếu không cần tái sử dụng như một Gatherer tổng hợp, nhiều khi cách rõ hơn là:

~~~~java
List<Integer> sums = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.windowFixed(2))
        .map(batch -> batch.stream().mapToInt(Integer::intValue).sum())
        .toList();
~~~~

Cả hai cách có cùng mục tiêu với dữ liệu ví dụ. `andThen` hữu ích để tạo một **thành phần biến đổi tái sử dụng**, có thể đưa vào nhiều pipeline, hoặc để kết hợp hai gatherer tùy chỉnh có logic bổ sung cho nhau.

API cho phép implementation tối ưu liên tiếp nhiều gatherer, nhưng không bảo đảm mọi trường hợp đều được hợp nhất thành một quá trình hiệu năng vượt trội. Hãy ưu tiên tính đúng và dễ đọc trước khi đo tối ưu.

## 9. Stream Gatherer so với Collector và Spliterator

| Đặc điểm | `Gatherer` | `Collector` | `Spliterator` |
| --- | --- | --- | --- |
| Vị trí điển hình | **Intermediate operation** qua `gather` | **Terminal operation** qua `collect` | Abstraction duyệt/chia phần tử của nguồn |
| Số output quan sát được | 0, 1 hoặc nhiều phần tử theo từng input / khi kết thúc | Một giá trị kết quả terminal | Định nghĩa cách cung cấp phần tử cho Stream |
| Có state nội bộ? | Có thể có | Có thể có | Có thể có |
| Có thể kết nối `map`/`filter` ở phía sau? | Có | Không, vì pipeline đã kết thúc | Cần tạo Stream từ Spliterator |
| Có short-circuit? | Có, nếu integrator được thiết kế thích hợp | Phụ thuộc terminal và cơ chế xử lý | Trách nhiệm của quá trình duyệt |
| Xử lý song song | Có thể, khi có combiner hợp lệ | Tùy collector và nguồn | Có thể phân chia công việc qua `trySplit` |
| Mục đích chính | Biến đổi luồng theo logic trung gian chưa có sẵn | Thu thập/kết xuất một kết quả cuối | Điều khiển duyệt dữ liệu ở mức thấp |

Ví dụ, nếu chỉ muốn nhóm toàn bộ bản ghi theo mã khách hàng:

~~~~java
Map<String, List<Order>> ordersByCustomer = orders.stream()
        .collect(Collectors.groupingBy(Order::customerId));
~~~~

Ở đây `Order` là kiểu nghiệp vụ giả định với accessor `customerId()`; ví dụ cho thấy ý định của `groupingBy`. Không cần tự viết Gatherer để thay thế một collector sẵn có.

Ngược lại, nếu muốn **phát một nhóm ngay khi mã khách hàng chuyển sang mã khác** để tiếp tục xử lý bằng `map`/`filter`, Gatherer có state và finisher giống ví dụ `groupConsecutive` phù hợp hơn.

`Spliterator` hữu ích khi chính **nguồn dữ liệu** có cách duyệt/chia việc đặc biệt. Gatherer hữu ích khi nguồn Stream đã có rồi nhưng muốn thêm một **bước biến đổi trung gian**.

## 10. Thứ tự, trạng thái và các quy tắc của Stream

### 10.1. Encounter order là một phần của hợp đồng

Nhiều Gatherer tích lũy hoặc tạo cửa sổ dựa trên encounter order. Với nguồn `List`, encounter order thường là thứ tự phần tử của list. Với một `HashSet` thông thường, thứ tự duyệt không được cam kết; dùng `windowFixed` trên nguồn đó không bảo đảm luôn có cùng nhóm ở các lần chạy.

~~~~java
List<Integer> ordered = List.of(1, 2, 3, 4, 5);

System.out.println(ordered.stream()
        .gather(Gatherers.windowFixed(2))
        .toList());
// [[1, 2], [3, 4], [5]]
~~~~

Nếu yêu cầu là nhóm theo **thời gian**, phải xác định thứ tự ngay từ nguồn hoặc áp dụng `sorted(...)` theo khóa phù hợp trước `gather`. Không dựa vào thứ tự ngẫu nhiên của tập giá trị.

### 10.2. State phải thuộc lần đánh giá

Ví dụ **không nên làm**:

~~~~java
// Sai về thiết kế: state được chia sẻ giữa các pipeline.
static int runningTotal;

static int accumulate(int value) {
    return runningTotal += value;
}
~~~~

Nếu dùng biến static này với `map`, các pipeline độc lập và những thread khác nhau có thể tác động lẫn nhau, làm kết quả phụ thuộc thứ tự gọi. Thay vào đó, khai báo state trong Gatherer thông qua `initializer` như `Gatherers.scan` hoặc `Gatherer.ofSequential`.

State nội bộ của một Gatherer tuần tự có thể là mutable; không cần tự động đưa vào `AtomicReference` hay dùng `synchronized` cho mỗi phần tử nếu runtime bảo đảm nó không bị truy cập đồng thời theo cùng state. Với Gatherer song song, runtime quản lý các state phân đoạn; **combiner** phải xử lý đúng, còn việc tham chiếu tài nguyên ngoài vẫn cần chính sách thread safety riêng.

### 10.3. Không sửa nguồn Stream trong callbacks

Một yêu cầu chung của Stream là các lambda/callback thường phải **không can thiệp vào nguồn dữ liệu** đang được duyệt. Ví dụ, không thêm/xóa phần tử trong `ArrayList` nguồn từ bên trong integrator. Hậu quả có thể là `ConcurrentModificationException`, kết quả không xác định hoặc lỗi logic.

~~~~java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3));

// Không làm:
// values.stream().gather(Gatherer.ofSequential(
//     (ignored, value, downstream) -> {
//         values.add(99); // Can thiệp trực tiếp vào source
//         return downstream.push(value);
//     }
// )).toList();
~~~~

Nếu cần xây dựng kết quả mới, đẩy phần tử mới bằng `downstream.push` hoặc giữ state nội bộ của Gatherer thay vì sửa chính nguồn.

### 10.4. Short-circuit và kết quả của thao tác downstream

Các terminal/intermediate operation như `findFirst`, `limit` hoặc một Gatherer khác có thể làm upstream không cần được tiêu thụ hết. Vì vậy:

- Không dựa vào một callback được gọi **đúng một lần cho mỗi phần tử nguồn** khi pipeline có thể dừng sớm.
- Không dựa vào `finisher` để thực hiện giao dịch nghiệp vụ bên ngoài thay cho cơ chế quản lý tài nguyên/vòng đời rõ ràng.
- Không giữ dữ liệu hoặc tài nguyên cần cleanup bên ngoài hợp đồng đánh giá của Stream mà không có cơ chế đóng riêng.
- Khi tạo Gatherer, tôn trọng kết quả của `downstream.push` nếu integrator có khả năng dừng sớm.

Một ví dụ:

~~~~java
List<List<Integer>> firstTwoWindows = Stream.iterate(1, n -> n + 1)
        .gather(Gatherers.windowFixed(3))
        .limit(2)
        .toList();

System.out.println(firstTwoWindows);
// [[1, 2, 3], [4, 5, 6]]
~~~~

Một nguồn vô hạn có thể trở thành kết quả hữu hạn nhờ giới hạn downstream, miễn là pipeline/gatherer có khả năng ngừng cung cấp dữ liệu khi downstream không cần thêm. Không nên kết hợp nguồn vô hạn với `fold` chỉ phát kết quả ở cuối rồi mong `findFirst` trả ngay: nếu không có điểm kết thúc hay cơ chế dừng, kết quả cuối có thể không bao giờ được phát.

## 11. Hiệu năng, bộ nhớ và xử lý lỗi

### 11.1. Không mặc định “gather” nhanh hơn

Gatherer bổ sung khả năng diễn đạt, không phải một lời hứa tăng tốc mọi pipeline. Hãy xem:

| Trường hợp | Chi phí/giới hạn cần xem xét |
| --- | --- |
| `windowFixed` với cửa sổ rất lớn | Có thể cấp phát buffer lớn ngay cả khi nguồn nhỏ |
| `windowSliding` với nhiều cửa sổ | Có thể tạo nhiều danh sách/cửa sổ và xử lý các phần tử chồng lấp |
| `fold`/custom gatherer tích lũy | State có thể tăng theo kích thước dữ liệu nếu không giới hạn |
| `scan` lưu lịch sử mutable | Nếu mỗi output dùng cùng object state, có thể bị aliasing và thay đổi sau khi phát |
| `mapConcurrent` | Tạo và điều phối tác vụ; có chi phí scheduling và nguy cơ quá tải dịch vụ downstream |
| `parallel()` cùng Gatherer stateful | Cần combiner đúng; không chắc chạy song song hoặc tăng tốc |
| `andThen` | Có thể được tối ưu kết hợp nhưng không có bảo đảm về chi phí cụ thể |

Với dữ liệu lớn, cân nhắc **không thu mọi kết quả vào `toList()`** nếu mục tiêu là xử lý từng khối; có thể dùng terminal operation khác hoặc truyền vào hệ thống xử lý theo lô phù hợp. Tuy nhiên, nếu cần ghi I/O có tác dụng phụ, phải xác định lỗi, retry và tính idempotent, không dựa vào tối ưu hóa Stream.

### 11.2. Tránh phát object mutable rồi tiếp tục sửa

Phản ví dụ:

~~~~java
// SAI nếu muốn mỗi kết quả là một snapshot độc lập.
// State là một ArrayList, và đẩy thẳng state ra downstream.
// Sau này state.clear()/state.add(...) sẽ làm các kết quả cũ bị thay đổi.
downstream.push(state);
state.clear();
~~~~

Hướng phù hợp hơn:

~~~~java
downstream.push(List.copyOf(state));
state.clear();
~~~~

Khi phần tử trong state là object mutable, `List.copyOf` mới chỉ sao chép **cấu trúc** danh sách, không tự deep copy các object. Phải xem xét mô hình sở hữu và bất biến của phần tử.

### 11.3. Lỗi trong initializer, integrator, combiner, finisher

Nếu một callback ném exception, quá trình đánh giá Stream có thể dừng. Đặc biệt với `mapConcurrent`, các tác vụ còn lại được yêu cầu hủy, nhưng hủy là best effort.

Một số nguyên tắc:

1. Validation tham số của Gatherer trước khi bắt đầu: ví dụ `windowFixed(0)` hay `mapConcurrent(0, mapper)` không hợp lệ.
2. Chọn chính sách lỗi rõ ràng: chuyển exception lên, hay phát ra kiểu kết quả biểu đạt thất bại.
3. Không bắt rồi bỏ qua exception nếu người gọi cần biết bản ghi bị lỗi.
4. Nếu mapper đồng thời gọi dịch vụ ngoài, giới hạn `maxConcurrency` theo tải chịu được của dịch vụ, không chỉ theo số lượng CPU.
5. Tài nguyên nguồn như `Files.lines(path)` cần được đóng bằng `try-with-resources`, vì `Stream` là `AutoCloseable` nhưng không phải mọi pipeline tự đóng nguồn chỉ vì terminal operation kết thúc.

Ví dụ một nguồn file (chỉ minh họa cú pháp; cần xử lý `IOException` theo ứng dụng):

~~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

static List<List<String>> readBatches(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.gather(Gatherers.windowFixed(100)).toList();
    }
}
~~~~

Kết quả `List<List<String>>` sống độc lập với việc đóng Stream file; các cửa sổ chứa các String đã đọc. Tuy nhiên, việc thu toàn bộ các batch vào list vẫn có chi phí bộ nhớ tỷ lệ với toàn bộ file; nếu file rất lớn, cân nhắc xử lý từng batch ngay khi được phát.

### 11.4. Không dùng Gatherer như hệ thống xử lý bất đồng bộ đa chức năng

`Stream.gather` là API biến đổi **trung gian** của Stream. `mapConcurrent` có khả năng xử lý mapper bằng virtual threads, nhưng không thay thế kiến trúc hàng đợi, hệ thống retry bền vững, giao dịch phân tán hoặc reactive streams với những hợp đồng backpressure khác nhau.

Khi công việc cần đảm bảo giao hàng, xử lý đúng-một-lần, ghi log kiểm toán hoặc điều phối tài nguyên dài hạn, phải thiết kế ở tầng nghiệp vụ hoặc tầng hệ thống. Gatherer chỉ nên nhận nhiệm vụ biến đổi dữ liệu trong phạm vi một pipeline Stream.

## 12. Ma trận kiểm tra hành vi và trường hợp biên

Trước khi đưa Gatherer tùy chỉnh vào thư viện, cần xác nhận cả **số lượng kết quả**, **thứ tự kết quả** và **điều kiện kết thúc**. Một số đầu vào hữu ích:

| Phép biến đổi | Input | Kết quả mong đợi |
| --- | --- | --- |
| `windowFixed(2)` | `[1, 2, 3, 4, 5]` | `[[1, 2], [3, 4], [5]]` |
| `windowFixed(5)` | `[1, 2]` | `[[1, 2]]` |
| `windowFixed(3)` | `[]` | `[]` |
| `windowSliding(3)` | `[1, 2, 3, 4]` | `[[1, 2, 3], [2, 3, 4]]` |
| `windowSliding(5)` | `[1, 2]` | `[[1, 2]]` |
| `windowSliding(5)` | `[]` | `[]` |
| `scan(() -> 0, Integer::sum)` | `[2, 3, 4]` | `[2, 5, 9]` |
| `fold(() -> "", String::concat)` | `["A", "B"]` | Một output `"AB"` |
| `distinctAdjacent()` | `["A", "A", "B", "A"]` | `["A", "B", "A"]` |
| `untilNegative()` | `[2, 3, -1, 9]` | `[2, 3]` |
| `groupConsecutive()` | `[(A,1), (B,2), (B,3)]` | Hai nhóm A và B |
| `mapConcurrent(3, mapper)` | `[A, B, C]` | Ba kết quả giữ encounter order |

Test đặc biệt cho Gatherer tự viết:

- **Nguồn rỗng:** initializer và finisher có tạo kết quả ngoài ý muốn hay không?
- **Một phần tử:** có bị bỏ sót vì chưa đủ dữ liệu để phát kết quả không?
- **Ranh giới nhóm:** hai phần tử cuối/đầu nhóm có được xử lý chính xác?
- **Dừng sớm:** sau khi integrator trả false, state còn chứa những gì và finisher phát gì?
- **Nhiều lần chạy độc lập:** có state bị rò rỉ giữa các lần sử dụng cùng một instance Gatherer?
- **Lỗi mapper/integrator:** exception có được truyền lên và tài nguyên có được giải phóng đúng?
- **Song song:** kết quả có tương đương xử lý tuần tự khi Gatherer có combiner?
- **Nguồn vô hạn:** pipeline có cách ngừng thực sự hay đang đợi kết thúc upstream?

Với `windowFixed` và `windowSliding`, nên test thêm `windowSize=0`, giá trị âm và trường hợp kích thước rất lớn so với nguồn. Các phương thức factory sẽ từ chối kích thước dưới 1; kích thước quá lớn có thể tạo chi phí bộ nhớ không cần thiết ngay cả khi input rất nhỏ.

## 13. Những lỗi thường gặp

| Lỗi | Vì sao gây vấn đề | Hướng xử lý |
| --- | --- | --- |
| Cho rằng Gatherer là terminal operation | Không thể hiểu đúng vì `gather` vẫn trả `Stream<R>` | Nối `map`/`filter`/`toList` hoặc terminal khác sau `gather` |
| Dùng `fold` để xử lý nguồn vô hạn mà không có điểm kết thúc | `fold` cần kết thúc upstream để phát kết quả cuối | Dùng `scan` hoặc thiết kế điều kiện ngừng |
| Mong `scan` phát riêng giá trị khởi tạo | `scan` chỉ phát sau mỗi input | Bổ sung trạng thái khởi tạo ở pipeline riêng nếu cần |
| Giả định `windowSliding` luôn đợi đủ W phần tử mới trả gì đó | Nếu nguồn ngắn hơn W, nó phát một cửa sổ chứa toàn bộ nguồn | Kiểm tra trường hợp N < W |
| Thay `distinct()` bằng gộp trùng liên tiếp mà không xem yêu cầu | Hai phép có ngữ nghĩa khác nhau | Chọn giữa loại trùng toàn cục và kề nhau |
| Lưu state trong biến static | Dễ rò rỉ state và tạo data race giữa các pipeline | Đặt state trong `initializer` |
| Đẩy buffer mutable rồi `clear` | Downstream nhận dữ liệu đã bị thay đổi | Tạo snapshot trước khi `push` |
| Không phát nhóm cuối | Integrator chỉ flush khi gặp khóa mới | Dùng `finisher` |
| Không xử lý giá trị false của `downstream.push` | Có thể tiêu thụ upstream không cần thiết | Trả false nếu downstream không nhận thêm |
| Gắn Greedy cho integrator có thể dừng sớm | Runtime có thể giả định không short-circuit | Chỉ dùng `ofGreedy` khi đúng ngữ nghĩa |
| Tạo combiner không xét ranh giới phân đoạn | Parallel có thể gộp sai thứ tự/nhóm | Chứng minh quy tắc gộp hoặc chọn `ofSequential` |
| Nghĩ `mapConcurrent` đồng nghĩa `parallel()` | Một bên điều phối mapper bằng virtual threads; bên kia xử lý parallel stream | Chọn theo loại công việc và hợp đồng ordering |
| Dựa vào thứ tự hoàn thành mapper | `mapConcurrent` chỉ bảo đảm encounter order của kết quả | Không phụ thuộc thứ tự side effect |
| Tự động tăng maxConcurrency rất lớn | Có thể làm quá tải dịch vụ hoặc tăng tiêu thụ tài nguyên | Đo và đặt giới hạn theo hệ thống bên ngoài |
| Giữ `Gatherer.Downstream` ngoài callback | Vi phạm hợp đồng vòng đời | Chỉ sử dụng downstream trong callback do engine gọi |
| Sửa collection nguồn khi đang gather | Can thiệp vào nguồn và có thể làm traversal sai | Giữ state riêng và phát output mới |
| Dùng Gatherer cho logic đã có `map`/`collect` đơn giản | Tăng độ phức tạp không cần thiết | Ưu tiên API đơn giản hiện có |

## 14. Hướng dẫn ra quyết định

Nếu phải lựa chọn công cụ, có thể đi từ **đặc điểm dữ liệu đầu ra**:

1. **Một phần tử đầu vào thành một phần tử đầu ra**, không state: ưu tiên `map`.
2. **Giữ hoặc bỏ** dựa trên điều kiện độc lập từng phần tử: ưu tiên `filter`.
3. **Một phần tử thành nhiều phần tử** nhưng không cần state qua nhiều input: ưu tiên `flatMap` hoặc `mapMulti` nếu phù hợp.
4. **Tổng hợp dữ liệu ở cuối** và không còn bước trung gian khác: ưu tiên `collect`/`reduce`.
5. **Chia cửa sổ cố định hoặc trượt:** dùng `Gatherers.windowFixed`/`windowSliding`.
6. **Tích lũy từng bước:** dùng `Gatherers.scan`.
7. **Tích lũy thành một output nhưng vẫn muốn xử lý bằng Stream:** cân nhắc `Gatherers.fold`.
8. **Mapper độc lập có thời gian chờ I/O**, muốn giới hạn concurrency: cân nhắc `Gatherers.mapConcurrent`.
9. **Biến đổi trung gian không có sẵn**, cần state/buffer/finisher/dừng sớm: tạo `Gatherer` qua `ofSequential`; chỉ bổ sung combiner khi đúng và có ích.

### Checklist cho một Gatherer tự viết

- [ ] Đã xác định rõ loại đầu vào `T`, state `A` và output `R`.
- [ ] Mỗi lần đánh giá có state riêng, không giữ state hoặc downstream ra bên ngoài callback.
- [ ] Integrator xác định rõ lúc nào phát 0, 1 hoặc nhiều phần tử.
- [ ] Nếu có short-circuit, giá trị boolean trả về là đúng và tôn trọng downstream.
- [ ] Nếu có buffer chưa phát, finisher xử lý cả đường kết thúc thông thường và kết thúc sớm.
- [ ] Output không chia sẻ object mutable có thể bị thay đổi sau khi push, trừ khi hợp đồng cho phép.
- [ ] Có kiểm thử với nguồn rỗng, một phần tử, nguồn dài và ranh giới nhóm/cửa sổ.
- [ ] Nếu hỗ trợ parallel, combiner bảo toàn kết quả tương đương tuần tự.
- [ ] Các callback không sửa nguồn Stream, không dựa vào tác dụng phụ chạy đúng số lần.
- [ ] Đã giới hạn tài nguyên khi window/buffer hoặc mapper đồng thời có thể tăng tải.
- [ ] Đã so sánh với các phép Stream đơn giản để tránh tự xây dựng thứ đã có.

## Tài liệu tham khảo chính thức

- [Java SE 27 – Gatherer<T,A,R>](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.html): mô hình initializer, integrator, combiner, finisher, `of`, `ofSequential`, `andThen`.
- [Java SE 27 – Gatherers](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherers.html): năm triển khai có sẵn, điều kiện biên và ngữ nghĩa xử lý đồng thời.
- [Java SE 27 – Stream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html): `Stream.gather`, lazy evaluation, non-interference, encounter order và terminal operation.
- [Java SE 27 – Gatherer.Integrator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.Integrator.html): callback tích hợp, giá trị boolean và `ofGreedy`.
- [Java SE 27 – Gatherer.Downstream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.Downstream.html): đẩy output và tiếp nhận tín hiệu dừng.
- [JEP 485 – Stream Gatherers](https://openjdk.org/jeps/485): quá trình hoàn thiện tính năng trong JDK 24.

**Kết luận:** Stream Gatherers mở rộng Stream bằng các **phép biến đổi trung gian tùy chỉnh**, gồm cả biến đổi có state, phát nhiều hoặc ít phần tử, xử lý cuối nguồn và short-circuit. Bắt đầu bằng những Gatherer có sẵn của Java 27; chỉ triển khai `Gatherer` riêng khi cần ngữ nghĩa khác. Thiết kế initializer, integrator, finisher và combiner đúng hợp đồng là điều kiện để kết quả chính xác, có thể tái sử dụng và an toàn khi pipeline được đánh giá theo nhiều cách.
