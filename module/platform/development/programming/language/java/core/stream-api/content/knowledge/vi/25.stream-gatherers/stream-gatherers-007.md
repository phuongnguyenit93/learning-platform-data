# Ánh xạ đồng thời có giới hạn bằng `Gatherers.mapConcurrent`

## 1. Mục tiêu bài học và tình huống thực tế

Trong module **`JAVA_STREAM_API`**, một pipeline Java Stream thường biểu diễn luồng xử lý dữ liệu bằng các thao tác khai báo: tạo nguồn, `filter`, `map`, `flatMap`, `reduce` và `collect`. Với các tác vụ độc lập nhưng có thời gian **chờ I/O**, ví dụ gọi nhiều API, kiểm tra trạng thái nhiều bản ghi hoặc đọc dữ liệu từ một dịch vụ có giới hạn kết nối, `map` tuần tự có thể dành nhiều thời gian chỉ để chờ từng kết quả.

Chạy mọi thứ song song không giới hạn cũng không phù hợp: hệ thống đích có thể chỉ cho phép một số yêu cầu đang xử lý, database connection pool bị giới hạn và bộ nhớ của ứng dụng không vô hạn.

**`Gatherers.mapConcurrent(maxConcurrency, mapper)`** là một gatherer dựng sẵn cho phép:

- Chuyển đổi từng phần tử bằng `mapper` theo quan hệ **một đầu vào → một đầu ra**.
- Chạy **nhiều lời gọi mapper đồng thời**, tối đa theo giới hạn `maxConcurrency`.
- Dùng **virtual threads** do API cung cấp để thực thi các lời gọi.
- **Bảo toàn thứ tự đầu ra** theo encounter order của stream nguồn, dù tác vụ có thể hoàn thành không theo thứ tự.
- Kết hợp với `Stream.gather(...)` để tiếp tục các thao tác `filter`, `map`, `collect` hoặc terminal operation khác.

Đây là bài trong chương **Stream Gatherer**. Mục đích không chỉ là học cú pháp Java 24 mà còn biết cách thiết kế giới hạn đồng thời, hiểu lỗi, short-circuit, tài nguyên, mức tải và kiểm thử trước khi đưa xử lý đồng thời vào hệ thống.

Sau bài, bạn sẽ có thể:

1. Sử dụng `Stream.gather(Gatherers.mapConcurrent(...))` đúng phiên bản Java.
2. Giải thích khác nhau giữa **concurrency**, **parallelism** và **rate limiting**.
3. Xác nhận giới hạn các lời gọi mapper đồng thời bằng bộ đếm an toàn thread.
4. Giữ kết quả theo thứ tự nguồn ngay khi tác vụ hoàn thành đảo thứ tự.
5. Phân biệt `mapConcurrent` với `map`, `parallelStream().map` và một executor tự quản lý.
6. Thiết kế quy tắc về ngoại lệ, hủy tác vụ, timeout và trạng thái dùng chung.
7. Đánh giá khi nào virtual threads có ích, khi nào công việc CPU-bound không được lợi.
8. Viết chương trình kiểm chứng Java 24+ và nhận diện giới hạn của thí nghiệm.

## 2. Phiên bản JDK và điều kiện biên dịch

Các mốc quan trọng:

| Phiên bản | Stream Gatherers | `Gatherers.mapConcurrent` |
| --- | --- | --- |
| Java 8–21 | Chưa có API Gatherers chuẩn | Không có phương thức này |
| Java 22 | Preview lần đầu (JEP 461) | Preview, cần bật preview tương ứng |
| Java 23 | Preview lần hai (JEP 473) | Preview, tiếp tục cần bật preview |
| **Java 24 trở lên** | **Chính thức (JEP 485)** | Dùng được như API chuẩn, không cần `--enable-preview` |

Các ví dụ trong bài dùng **Java 24+**, trừ khi ghi rõ cách thay thế trên JDK cũ. `Stream.toList()` có từ Java 16, nhưng `Stream.gather` và `Gatherers.mapConcurrent` chỉ được chuẩn hóa ở Java 24.

Kiểm tra môi trường:

```text
java -version
javac -version
```

Với file `MapConcurrentIntro.java` bên dưới:

```text
javac MapConcurrentIntro.java
java MapConcurrentIntro
```

Nếu dự án dùng Maven/Gradle toolchain hoặc `javac --release 21`, không thể dùng Gatherers Java 24 dù terminal được cài JDK 24. Cần cấu hình **mức API biên dịch** và **JDK runtime thực tế** tương thích. Đừng chỉ đổi cấu hình phiên bản mà bỏ qua máy chủ chạy ứng dụng.

## 3. Chữ ký và hợp đồng quan trọng nhất

Trên Java 24, API dựng sẵn có chữ ký:

```java
public static <T, R> Gatherer<T, ?, R> mapConcurrent(
    int maxConcurrency,
    Function<? super T, ? extends R> mapper
)
```

Ý nghĩa:

| Thành phần | Vai trò |
| --- | --- |
| `T` | Kiểu phần tử nguồn đi vào gatherer |
| `R` | Kiểu phần tử mapper tạo ra |
| `maxConcurrency` | **Mức đồng thời tối đa** mong muốn cho mapper, phải ≥ 1 |
| `mapper` | Hàm chuyển một `T` thành một `R` |
| `Gatherer<T, ?, R>` | Đối tượng mô tả phép biến đổi trung gian |
| `Stream.gather(...)` | Áp dụng gatherer lên stream nguồn, tạo `Stream<R>` |

Ví dụ về hình dạng pipeline:

```java
Stream<Integer> input = Stream.of(1, 2, 3);

Stream<String> output = input.gather(
    Gatherers.mapConcurrent(
        2,
        n -> "ID-" + n
    )
);

List<String> result = output.toList();
```

Kết quả logic là `[ID-1, ID-2, ID-3]`. `gather` vẫn là **intermediate operation**; việc thực hiện mapper được kích hoạt khi pipeline được tiêu thụ bởi một terminal operation như `toList`.

### 3.1. Một đầu vào tạo một đầu ra

`mapConcurrent` có quan hệ **một-một** về mặt phần tử khi mapper hoàn thành bình thường. Không gọi `mapConcurrent` để:

- Tự phát 0 hoặc nhiều phần tử từ một input.
- Phân nhóm thành `Map` theo khóa.
- Tạo cửa sổ trượt, cửa sổ cố định hoặc prefix scan.

Những nhu cầu đó liên quan các API khác như `filter`, `flatMap`, `mapMulti`, `collect(groupingBy(...))`, `Gatherers.windowSliding` hoặc `Gatherers.scan`.

Ví dụ chỉ nhận số chẵn:

```java
List<String> result = Stream.of(1, 2, 3, 4)
    .filter(n -> n % 2 == 0)
    .gather(Gatherers.mapConcurrent(
        2, n -> "N=" + n))
    .toList();

System.out.println(result); // [N=2, N=4]
```

Ở đây **`filter`**, không phải `mapConcurrent`, loại bớt phần tử.

### 3.2. Kiểm tra tham số

Theo API Java 24:

- `maxConcurrency < 1` → `IllegalArgumentException`.
- `mapper == null` → `NullPointerException`.

```java
// Bị từ chối:
Gatherers.mapConcurrent(0, (Integer n) -> n * 2);
Gatherers.mapConcurrent(-1, (Integer n) -> n * 2);
Gatherers.<Integer, Integer>mapConcurrent(2, null);
```

Không nên chấp nhận `0` và tự hiểu là "chạy tuần tự". Nếu cần một mapper tuần tự, dùng `stream.map(mapper)`, hoặc `mapConcurrent(1, mapper)` khi muốn giữ cùng hình thức gatherer nhưng không kỳ vọng cải thiện tốc độ.

**Giới hạn trên** cũng nên có chính sách từ ứng dụng. JDK chỉ yêu cầu giá trị dương; cấu hình `1_000_000` không có nghĩa hệ thống đích đủ sức nhận một triệu yêu cầu đồng thời.

## 4. Ví dụ đầu tiên có thể chạy (Java 24+)

Tạo file `MapConcurrentIntro.java`:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class MapConcurrentIntro {
    static String lookupLabel(int id) {
        return "item-" + id;
    }

    public static void main(String[] args) {
        List<String> labels = IntStream.rangeClosed(1, 6)
            .boxed()
            .gather(Gatherers.mapConcurrent(
                3, MapConcurrentIntro::lookupLabel))
            .toList();

        System.out.println(labels);
        // [item-1, item-2, item-3, item-4, item-5, item-6]
    }
}
```

Đọc từ trái sang phải:

1. `IntStream.rangeClosed(1, 6).boxed()` tạo `Stream<Integer>` có encounter order.
2. `Gatherers.mapConcurrent(3, ...)` cấu hình tối đa ba lời gọi mapper đang thực thi đồng thời.
3. `gather` tạo pipeline với khả năng ánh xạ đồng thời thông qua virtual threads.
4. `toList` đợi các kết quả cần thiết và thu thành danh sách.
5. Danh sách có thứ tự theo **nguồn**, không phụ thuộc callback nào hoàn tất trước.

Đây là **ví dụ đúng về ngữ nghĩa** nhưng `lookupLabel` chỉ ghép chuỗi rất nhanh. Không nên kỳ vọng nó sẽ nhanh hơn `map(MapConcurrentIntro::lookupLabel)`: chi phí điều phối có thể lớn hơn phép ghép chuỗi.

## 5. Virtual threads giúp việc chờ như thế nào?

Một **virtual thread** là cơ chế thread nhẹ do Java runtime quản lý; nhiều virtual threads có thể được lập lịch trên số lượng nhỏ hơn các platform threads. Điều này đặc biệt hữu ích khi công việc thường xuyên **chờ I/O** thay vì liên tục tiêu thụ CPU.

Một mô hình khái niệm:

```text
Stream nguồn:    A       B       C       D       E
                  \      |      /
                   mapConcurrent(3)
                  /      |      \
             virtual   virtual   virtual
             thread    thread    thread
                 |        |        |
             chờ API   chờ API   chờ API
                  \       |       /
             nhận kết quả theo thứ tự nguồn
                        |
                     Stream<R>
```

Trong lúc một tác vụ chờ phản hồi, runtime có thể thực thi tác vụ khác. **Virtual threads không làm một phép tính CPU trở nên nhanh hơn một cách thần kỳ**: khả năng chạy tính toán đồng thời vẫn bị giới hạn bởi số lõi, tranh chấp bộ nhớ và cách lập lịch.

### 5.1. Vì sao không cứ dùng `parallel()`?

`parallelStream` thường phân chia nguồn cho các phần việc của cơ chế fork/join. Điều đó phù hợp với nhiều phép tính **CPU-bound độc lập, nguồn dễ chia**. Trong khi đó, `mapConcurrent` có một lợi ích khác: **đưa một bước mapping có thể chờ vào cơ chế thực thi đồng thời có giới hạn, không cần biến toàn bộ stream thành parallel stream**.

Đừng coi hai API là đồng nghĩa. Phần so sánh chi tiết ở mục sau sẽ làm rõ khi nào chọn cách nào.

### 5.2. `maxConcurrency` không phải số lõi CPU

Chọn `maxConcurrency = 20` không yêu cầu máy có 20 lõi. Nó cho phép tối đa 20 lời gọi mapper có thể **đang thực hiện** đồng thời, có thể phần lớn thời gian nằm ở trạng thái chờ. Với tác vụ chỉ tính CPU, vượt quá mức khả dụng của CPU có thể chỉ tăng overhead.

Khi mapper gọi dịch vụ từ xa, ngoài số lõi còn cần cân nhắc:

- Số kết nối đồng thời mà dịch vụ cho phép.
- Pool kết nối HTTP/JDBC của client.
- Timeout, retry và circuit breaker.
- Bộ nhớ giữ dữ liệu đầu vào/đầu ra đang chờ.
- Số yêu cầu đồng thời từ **những pipeline khác** trong cùng ứng dụng.

## 6. Concurrency khác parallelism và rate limiting

Ba khái niệm không thể đánh đồng:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Concurrency** | Có bao nhiêu công việc được quản lý/đang tiến hành cùng lúc? | Tối đa 5 mapper đang chờ API |
| **Parallelism** | Có bao nhiêu phần tính toán thực sự chạy đồng thời trên tài nguyên CPU? | Nhiều lõi xử lý các vùng mảng |
| **Rate limit** | Có bao nhiêu yêu cầu được khởi tạo hoặc hoàn thành trong một khoảng thời gian? | Tối đa 100 request/giây |

`mapConcurrent(5, mapper)` giới hạn **số lời gọi mapper đồng thời**. Nó **không bảo đảm** tốc độ tối đa 5 request/giây.

Ví dụ một dịch vụ phản hồi trong khoảng 10 ms: năm slot có thể được tái sử dụng rất nhiều lần mỗi giây. Nếu dịch vụ phản hồi chậm tới vài giây, throughput sẽ thấp hơn đáng kể với cùng mức concurrency.

### 6.1. Không dùng concurrency như quota QPS

Nếu API có hạn mức **100 request/giây**, chỉ dùng:

```java
.gather(Gatherers.mapConcurrent(10, this::callApi))
```

chưa kiểm soát được số lần bắt đầu yêu cầu mỗi giây. Muốn tuân thủ hạn mức, có thể cần một **rate limiter theo token bucket/time window** kết hợp giới hạn concurrency; hai lớp giới hạn bảo vệ **hai tài nguyên khác nhau**.

### 6.2. Một pipeline không quản lý quota toàn ứng dụng

Hai yêu cầu web độc lập, mỗi yêu cầu tạo một pipeline `mapConcurrent(10, ...)`, không mặc nhiên chia sẻ một budget 10 yêu cầu trên toàn ứng dụng. Nếu upstream chỉ cho phép tổng 10 yêu cầu, cần quản lý **giới hạn toàn cục** ở lớp client hoặc bằng cơ chế concurrency limiter chung (ví dụ `Semaphore`/pool), ngoài giới hạn cục bộ của gatherer.

Không thể suy từ mỗi pipeline hợp lệ rằng toàn dịch vụ sẽ không bao giờ vượt tải.

## 7. Bảo toàn encounter order dù mapper hoàn thành lệch thứ tự

Giả sử nguồn `[1,2,3,4]`, nhưng mapper của 1 cần nhiều thời gian hơn mapper của 2 và 3. Với `mapConcurrent`, runtime có thể thực hiện nhiều mapper cùng lúc, song **đầu ra vẫn phản ánh encounter order** của stream nguồn có thứ tự.

Ví dụ Java 24+ với thời gian chờ mô phỏng:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class OrderedConcurrentMap {
    static String delayedLabel(int id) {
        long sleepMillis = (5L - id) * 30L;

        try {
            Thread.sleep(sleepMillis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Tac vu bi ngat", ex);
        }
        return "id-" + id;
    }

    public static void main(String[] args) {
        List<String> result = IntStream.rangeClosed(1, 4)
            .boxed()
            .gather(Gatherers.mapConcurrent(
                4, OrderedConcurrentMap::delayedLabel))
            .toList();

        System.out.println(result);
        // [id-1, id-2, id-3, id-4]
    }
}
```

Dữ liệu sau `toList` **có thứ tự ổn định** trên nguồn này. Ta cố ý làm thời gian chờ của các ID khác nhau, nhưng **không khẳng định lịch chạy hay thứ tự hoàn thành thực tế luôn giống nhau** ở mọi lần chạy. `Thread.sleep` chỉ là công cụ mô phỏng, không phải bằng chứng tốc độ ứng dụng thật.

### 7.1. Thứ tự kết quả ≠ thứ tự side effect

Không dùng `System.out.println` trong mapper để đoán thứ tự:

```java
// Chỉ để chẩn đoán, không dùng thứ tự log làm hợp đồng.
List<String> result = IntStream.rangeClosed(1, 4)
    .boxed()
    .gather(Gatherers.mapConcurrent(3, id -> {
        System.out.println("Dang xu ly " + id);
        return "item-" + id;
    }))
    .toList();
```

Dòng log có thể xuất hiện theo thứ tự khác nguồn, nhưng `result` vẫn theo encounter order. Tránh dựa vào thứ tự log để tính kết quả hoặc tạo một **mã thứ tự toàn cục** từ các mapper chạy đồng thời.

### 7.2. Nguồn không có encounter order

Nếu nguồn là `HashSet` hoặc pipeline gọi `unordered()`, `mapConcurrent` không thể tự tạo một thứ tự nghiệp vụ cố định. Muốn kết quả theo thứ tự ID tăng dần, hãy chuẩn hóa trước:

```java
List<String> result = ids.stream()
    .sorted()
    .gather(Gatherers.mapConcurrent(
        4, id -> "item-" + id))
    .toList();
```

`ids` là tập số nguyên trong chương trình thực tế. `sorted` tạo thứ tự theo giá trị, nhưng cần cân nhắc chi phí sắp xếp trên tập lớn. Nếu các phần tử là bản ghi và tiêu chí chính có thể bằng nhau, thêm **khóa phụ ổn định** để có thứ tự tổng thể.

## 8. Cửa sổ chờ kết quả và bài toán head-of-line blocking

Bảo toàn encounter order có đánh đổi: một mapper ở vị trí đầu **chậm** có thể khiến việc phát các kết quả **ở sau** phải chờ, dù những mapper đó đã xong.

Ví dụ khái niệm:

```text
Input:      A    B    C    D
Mapper:     ├───────────────┤
                 ├──┤ ├──┤ ├──┤
Hoàn tất:        B    C   D          ... A về sau
Output ordered:   vẫn cần A trước B, C, D
```

Hiện tượng này gọi là **head-of-line blocking**. Nó thường quan trọng khi latency mapper có đuôi dài (tail latency) hoặc khi một dịch vụ phản hồi rất không đều.

Các điểm cần phân biệt:

- `mapConcurrent` bảo đảm thứ tự **kết quả**, không bảo đảm mỗi phần tử sẵn sàng cho downstream ngay khi mapper của nó hoàn tất.
- `maxConcurrency` giới hạn số mapper chạy cùng lúc nhưng **không có nghĩa toàn bộ bộ nhớ chỉ chứa đúng `maxConcurrency` đối tượng nhỏ**; kích thước các đầu vào/đầu ra và cách downstream giữ kết quả cũng quan trọng.
- Khi `toList` thu toàn bộ kết quả, bản thân danh sách cuối cần giữ tất cả phần tử được thu.
- Nếu nghiệp vụ không cần thứ tự, các API khác có thể phù hợp hơn; đừng dựa vào `mapConcurrent` để phát "ai xong trước ra trước", vì nó có hợp đồng ngược lại.

Nếu hệ thống cần đẩy kết quả ngay khi hoàn thành theo thứ tự bất kỳ, hãy thiết kế một mô hình completion-order riêng và ghi rõ **thay đổi ngữ nghĩa** đó.


## 9. Kiểm chứng thật sự số mapper đang chạy đồng thời

Muốn kiểm tra `maxConcurrency`, không đo bằng số virtual threads tồn tại trong toàn JVM và cũng không dùng một biến `int` dùng chung không đồng bộ. Ta cần đếm **số lời gọi mapper đã bắt đầu nhưng chưa kết thúc**.

Một phép đo có thể dùng:

- `AtomicInteger active`: số mapper hiện đang thực hiện.
- `AtomicInteger peak`: mức active lớn nhất đã quan sát.
- Tăng `active` khi mapper vào.
- Giảm `active` trong `finally` để xử lý cả lỗi hoặc interruption.
- Cập nhật `peak` bằng phép atomic, không dựa vào kết quả đọc-ghi rời rạc.

### 9.1. Mẫu giám sát concurrency

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger active = new AtomicInteger();
AtomicInteger peak = new AtomicInteger();

List<String> result = ids.stream()
    .gather(Gatherers.mapConcurrent(4, id -> {
        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);

        try {
            return "item-" + id;
        } finally {
            active.decrementAndGet();
        }
    }))
    .toList();

System.out.println("Peak observed: " + peak.get());
```

Đây là một đoạn đặt bên trong method của lớp Java 24+ có `ids` là `List<Integer>` và import `java.util.List`, `java.util.stream.Gatherers`.

Cần kiểm tra:

```java
if (peak.get() > 4) {
    throw new AssertionError("Vuot gioi han dong thoi");
}
```

**Không yêu cầu `peak == 4`.** Với mapper cực nhanh hoặc nguồn ít phần tử, có thể không bao giờ có đủ bốn lời gọi đồng thời. `maxConcurrency` là **giới hạn trên**, không phải mệnh lệnh runtime luôn phải dùng hết số slot.

### 9.2. Vì sao phải có `finally`?

Nếu mapper gặp exception, bỏ `active.decrementAndGet()` sẽ làm counter hiển thị sai:

```java
int now = active.incrementAndGet();
try {
    return process(value);
} finally {
    active.decrementAndGet();
}
```

`process(value)` ở đây là hàm minh họa; cần khai báo trong chương trình ứng dụng. `finally` làm phép kiểm đếm có ý nghĩa ngay cả khi mapper bị ngắt hoặc thất bại.

Trong hệ thống observability, có thể đo gauge số yêu cầu đang chờ qua cấu trúc tương tự. Tuy nhiên, instrumentation phải **thread-safe** và không được trở thành nút cổ chai chính của pipeline.

## 10. Ví dụ tình huống I/O: nhiều lời gọi độc lập, kết quả vẫn đúng thứ tự

Một API bên ngoài có thể tra thông tin cho mỗi mã đơn hàng. Mô hình dữ liệu:

```text
orderIds = ["O-101", "O-102", "O-103", "O-104"]

Tra cứu (có thể chờ I/O):
  O-101 -> PAID
  O-102 -> PENDING
  O-103 -> PAID
  O-104 -> REFUNDED

Kết quả sau mapConcurrent:
  ["O-101:PAID", "O-102:PENDING", "O-103:PAID", "O-104:REFUNDED"]
```

Code minh họa Java 24+ dùng một nguồn giả lập để tránh phụ thuộc mạng:

```java
import java.util.List;
import java.util.stream.Gatherers;

public class OrderLookupDemo {

    static String fetchStatus(String orderId) {
        // Mô phỏng tác vụ phải chờ, không gọi mạng thật.
        try {
            Thread.sleep(40L);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Tra cuu bi ngat", ex);
        }

        return switch (orderId) {
            case "O-101", "O-103" -> "PAID";
            case "O-102" -> "PENDING";
            default -> "REFUNDED";
        };
    }

    public static void main(String[] args) {
        List<String> orderIds = List.of(
            "O-101", "O-102", "O-103", "O-104");

        List<String> results = orderIds.stream()
            .gather(Gatherers.mapConcurrent(2, id ->
                id + ":" + fetchStatus(id)))
            .toList();

        System.out.println(results);
        // [O-101:PAID, O-102:PENDING,
        //  O-103:PAID, O-104:REFUNDED]
    }
}
```

Lời gọi `Thread.sleep(40)` chỉ mô phỏng thời gian chờ: nó **không chứng minh** performance của client HTTP hoặc JDBC. Trong thực tế, mapper có thể gọi dịch vụ qua một client hỗ trợ timeout, connection pooling và giới hạn tài nguyên.

### 10.1. Khóa định danh và kết quả

Khi gọi nhiều API đồng thời, nên trả về **kết quả có gắn khóa** thay vì chỉ giữ giá trị dễ gây nhầm:

```java
record OrderStatus(String orderId, String status) {}

List<OrderStatus> statuses = orderIds.stream()
    .gather(Gatherers.mapConcurrent(
        3,
        id -> new OrderStatus(id, fetchStatus(id))))
    .toList();
```

Đây là ví dụ Java 24+ với `record` từ Java 16, đặt trong phạm vi lớp/phương thức có các import liên quan. Dù `mapConcurrent` giữ thứ tự, việc mang `orderId` trong kết quả giúp downstream làm việc an toàn khi phải đối chiếu với dữ liệu khác.

### 10.2. Chọn `maxConcurrency` dựa vào bottleneck

Một quy trình chọn mức đồng thời:

1. Xác định **tác vụ độc lập** và có thể chạy đồng thời hay không.
2. Kiểm tra giới hạn từ dịch vụ đích (pool kết nối, quota, concurrency cap, độ ổn định).
3. Chọn mức khởi đầu nhỏ để tránh tạo thác yêu cầu.
4. Đo latency, throughput, số lỗi, timeout, in-flight và áp lực bộ nhớ.
5. Thử một vài mức concurrency trong môi trường đại diện.
6. Giảm mức nếu vượt quota, gặp timeout, p95/p99 tăng hoặc pool cạn.
7. Kiểm tra tải có **nhiều pipeline đồng thời**, không chỉ một yêu cầu riêng lẻ.

Một `maxConcurrency` rất lớn có thể làm throughput **tệ hơn** do tranh chấp và lỗi retry dây chuyền. Đừng sử dụng số lớn làm mặc định chỉ vì virtual threads rẻ hơn platform threads.

## 11. Đầu ra có một phần tử cho mỗi input, nhưng có thể có lỗi

Về luồng dữ liệu, `mapConcurrent` là phép ánh xạ một-một. Nếu mọi mapper hoàn thành bình thường, các phần tử kết quả tương ứng từng đầu vào. Nhưng khi mapper ném exception, **không được giả định pipeline trả một danh sách kết quả thiếu một vài phần tử và coi như thành công**.

Theo Javadoc Java 24, nếu một kết quả **đến lượt được phát downstream** nhưng mapper tương ứng hoàn thành với exception, gatherer sẽ phát lại lỗi dưới dạng **`RuntimeException`**, sau đó cố hủy những tác vụ còn lại.

Ví dụ:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class MapperExceptionDemo {
    public static void main(String[] args) {
        try {
            List<Integer> result = Stream.of(1, 2, 3, 4)
                .gather(Gatherers.mapConcurrent(2, n -> {
                    if (n == 3) {
                        throw new IllegalArgumentException(
                            "Gia tri khong hop le: " + n);
                    }
                    return n * 10;
                }))
                .toList();

            System.out.println(result);
        } catch (RuntimeException ex) {
            System.out.println("Pipeline that bai");
        }
    }
}
```

Không cần dựa vào **loại exception cụ thể bên trong `RuntimeException`**, tên thread hoặc thứ tự log để xác nhận hợp đồng. API mô tả cơ chế phát lại lỗi, còn cách đóng gói/đính kèm nguyên nhân không nên bị hardcode khi không được cam kết.

### 11.1. Ngoại lệ checked từ I/O

`Function<T,R>` không khai báo checked exception. Khi mapper gọi API ném `IOException` hoặc `InterruptedException`, cần xử lý **bên trong mapper**:

```java
static String simulatedBlockingCall(String id) {
    try {
        Thread.sleep(50L);
        return "OK:" + id;
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
            "Bi ngat khi xu ly " + id, ex);
    }
}
```

Không nuốt interruption rồi tiếp tục chờ vô hạn. Bảo toàn cờ interrupt có thể giúp chính sách hủy tác vụ và dừng ứng dụng hoạt động đúng hơn.

**Tuy nhiên, interrupt không phải rollback giao dịch.** Nếu mapper đã gửi một yêu cầu thanh toán hoặc ghi database, việc ngắt Java thread không tự đảo ngược side effect xảy ra ở hệ thống ngoài.

### 11.2. Muốn giữ kết quả lỗi riêng thay vì thất bại toàn pipeline?

Hãy làm lỗi trở thành **một giá trị dữ liệu** theo hợp đồng riêng:

```java
record LookupResult(
    String id,
    String value,
    String error
) {
    boolean isSuccess() {
        return error == null;
    }
}

static LookupResult safeLookup(String id) {
    try {
        return new LookupResult(
            id, simulatedBlockingCall(id), null);
    } catch (RuntimeException ex) {
        return new LookupResult(
            id, null, "LOOKUP_FAILED");
    }
}
```

Sau đó:

```java
List<LookupResult> all = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, MyClass::safeLookup))
    .toList();
```

Đoạn này giả định `ids` và `MyClass` đã được khai báo trong ứng dụng. Đây là **một chính sách nghiệp vụ khác**: ghi nhận lỗi theo từng bản ghi thay vì ném khi gặp lỗi đầu tiên cần phát ra.

Khi xử lý lỗi, không lưu raw exception message có thể chứa token, URL chứa bí mật hay thông tin cá nhân vào kết quả hiển thị. Nên phân loại lỗi có mã, ghi log có kiểm soát và giữ correlation ID.

**Cẩn thận:** bắt mọi `RuntimeException` rồi trả về giá trị lỗi có thể che khuất bug lập trình. Chỉ nên chuyển thành lỗi dữ liệu với các loại thất bại mà nghiệp vụ đã dự kiến; những lỗi hệ thống nghiêm trọng cần được ghi nhận và xử lý riêng.

## 12. Hủy tác vụ theo best-effort và giới hạn short-circuit

Một terminal operation như `findFirst`, `anyMatch` hoặc `limit` có thể dừng khi không cần thêm kết quả.

```java
List<Integer> firstTwo = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.mapConcurrent(
        3, n -> n * 10))
    .limit(2)
    .toList();

System.out.println(firstTwo); // [10, 20]
```

Theo API, khi downstream không muốn nhận thêm phần tử, gatherer sẽ **cố hủy các tác vụ đang chạy theo best-effort**. Điều này **không phải bảo đảm** rằng:

- Chỉ đúng hai mapper đã bắt đầu chạy.
- Những mapper khác chưa gọi API ngoài.
- Mọi tác vụ đã hoàn toàn dừng ngay khi `limit(2)` hoàn tất.
- Mọi side effect đã được hủy/rollback.
- Client HTTP/JDBC của bạn chắc chắn tuân theo interruption.

Vì có thể có nhiều mapper in-flight, số tác vụ đã bắt đầu **có thể lớn hơn số kết quả được giữ**. Do đó không đưa một thao tác không thể đảo ngược vào mapper rồi dựa vào `limit` để cam kết chỉ có vài thao tác được thực hiện.

### 12.1. `findFirst` và `findAny`

`mapConcurrent` giữ encounter order của nguồn ordered, nhưng `findFirst` và `findAny` có mục đích khác nhau:

- `findFirst` cần phần tử đầu tiên trong encounter order.
- `findAny` có thể chọn bất kỳ phần tử phù hợp nào theo điều kiện của terminal operation.

Không suy ra `findAny` trên một pipeline đã dùng `mapConcurrent` sẽ tự tạo một cơ chế "ai hoàn thành trước thắng"; cách xử lý theo các tầng và thứ tự có thể ảnh hưởng việc kết quả nào sẵn sàng. Nếu sản phẩm **cần kết quả đầu tiên theo thời gian hoàn thành thực tế**, hãy thiết kế một API completion-order riêng.

### 12.2. Không dùng short-circuit để thực hiện ghi hàng loạt

Giả sử `mapper` gọi `saveToDatabase` hoặc `chargeCreditCard`. Những lệnh này có side effect quan trọng. Một terminal operation dừng sớm không làm rõ **bản ghi nào đã được ghi thành công** và những tác vụ nào đang chờ.

Với thao tác có side effect, cần:

- Định nghĩa **idempotency key** hoặc phương án chống lặp nếu retry.
- Biết khi nào thao tác đã commit ở hệ thống ngoài.
- Quản lý timeout và lỗi một phần.
- Theo dõi trạng thái từng yêu cầu và chính sách bù trừ khi cần.
- Không coi cancellation của Java task là transaction rollback.

`mapConcurrent` là công cụ ánh xạ đồng thời, **không phải trình quản lý giao dịch phân tán**.

## 13. Timeout, retry, backpressure và quota

`maxConcurrency` chỉ kiểm soát một phần áp lực tải. Một mapper chờ vô hạn có thể giữ một slot rất lâu; giữ tối đa N slot không tự tạo timeout.

### 13.1. Thiết lập timeout ngay ở client

Với HTTP, cần timeout kết nối và timeout yêu cầu ở client/request. Với JDBC, cần deadline/query timeout và pool có giới hạn. Các API này thuộc trách nhiệm **của lớp I/O**, không phải tham số của `mapConcurrent`.

Một mapper điển hình:

```java
static String fetchWithPolicy(String id) {
    // Client đã được cấu hình:
    // - timeout của yêu cầu
    // - pool kết nối
    // - retry giới hạn cho lỗi thích hợp
    // - phân loại lỗi/metrics
    return remoteClient.lookup(id);
}
```

Đây là **pseudocode**: `remoteClient` không phải lớp JDK có sẵn trong ví dụ. Cần cung cấp implementation tương ứng với API/dịch vụ thật.

### 13.2. Retry có thể làm vượt giới hạn ở dịch vụ ngoài

Nếu mapper tự khởi chạy nhiều yêu cầu **cùng lúc** khi retry/hedging hoặc gọi fan-out cho một đầu vào, `maxConcurrency` chỉ giới hạn số mapper đang chạy, không nhất thiết giới hạn tổng **yêu cầu con**.

Ví dụ `mapConcurrent(5)` mà mỗi mapper tự tạo 3 tác vụ HTTP song song có thể tạo **nhiều hơn 5** yêu cầu ngoài. Cần giới hạn ở đúng lớp mà tài nguyên được tiêu thụ.

### 13.3. Đừng dùng retry không giới hạn

Retry vô hạn hoặc backoff quá thấp có thể giữ mapper slot lâu và tạo bão yêu cầu khi dịch vụ đích yếu. Nên xác định:

- Số lần thử tối đa.
- Deadline/timeout toàn tác vụ.
- Backoff có giới hạn và jitter khi thích hợp.
- Danh sách lỗi được phép retry.
- Idempotency cho các thao tác ghi.
- Rate limiter độc lập nếu dịch vụ có hạn mức theo thời gian.

**Backpressure** không đồng nghĩa với một tham số duy nhất. `maxConcurrency` giúp hạn chế số mapper in-flight trong một gatherer, nhưng không tự quản lý mọi queue, buffer, client hoặc toàn bộ luồng công việc ở cấp hệ thống.

## 14. So sánh `map`, `mapConcurrent` và `parallelStream`

Cùng một chức năng biến đổi:

```java
// Tuần tự: mapper của từng phần tử chạy theo pipeline tuần tự.
List<String> a = ids.stream()
    .map(this::fetch)
    .toList();

// Đồng thời có giới hạn: virtual threads, vẫn giữ thứ tự nguồn.
List<String> b = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, this::fetch))
    .toList();

// Stream song song: runtime chia pipeline theo Spliterator.
List<String> c = ids.parallelStream()
    .map(this::fetch)
    .toList();
```

Đoạn trên là hình thức minh họa trong **một instance method** có `ids` là `List<String>` và `fetch(String)` trả `String`. Cả ba có thể cho cùng kết quả nếu mapper thuần, thread-safe và không có lỗi.

| Tiêu chí | `stream().map(...)` | `gather(mapConcurrent(...))` | `parallelStream().map(...)` |
| --- | --- | --- | --- |
| Mốc Java | Java 8 | Java 24 chính thức | Java 8 |
| Sự đồng thời của mapper | Không, trong stream tuần tự | Có, tối đa `maxConcurrency` | Theo cách chia/lập lịch parallel stream |
| Cơ chế cơ bản | Pipeline tuần tự | Virtual threads | Fork/join trong các triển khai JDK thông dụng |
| Giới hạn trực tiếp cho mapper | Không cần | Có: `maxConcurrency` | Không có tham số trực tiếp tương đương |
| Dữ liệu có encounter order | Giữ thứ tự | **Giữ thứ tự** | Terminal thích hợp giữ thứ tự |
| Hợp tác với I/O blocking | Từng mapper chờ lần lượt | Phù hợp để khảo sát khi nhiều tác vụ chờ độc lập | Có thể làm worker pool chờ |
| CPU-bound thuần | Baseline tốt | Không tự bảo đảm lợi ích | Có thể tăng tốc với nguồn dễ chia, đủ nặng |
| Cần quản lý timeout/quota | Có | Có | Có |
| Đảm bảo tốc độ cao hơn | Không | Không | Không |

Không có bảng xếp hạng tốc độ chung cho mọi ứng dụng. Một mapper làm phép cộng đơn giản thường không hưởng lợi từ việc khởi chạy virtual threads. Một mapper có thời gian chờ mạng đáng kể có thể được lợi từ concurrency, nhưng **dịch vụ đích và pool kết nối** vẫn quyết định mức song song hiệu quả.

### 14.1. `maxConcurrency = 1` so với `map`

`mapConcurrent(1, mapper)` giới hạn một mapper thực thi cùng lúc. Nhưng nó **không phải lời hứa** sẽ có cùng overhead, cách quản lý exception hoặc cách lập lịch như `map(mapper)` tuần tự.

Nếu không cần cơ chế virtual-thread mapping, `map` thường đơn giản hơn. Khi bắt đầu đo, coi `mapConcurrent(1)` là một **cấu hình đối chứng riêng**, không đồng nhất hoàn toàn với `map`.

### 14.2. Không cộng dồn `parallel()` theo cảm tính

`parallelStream().gather(Gatherers.mapConcurrent(...))` có thể kết hợp các cơ chế đồng thời, nhưng không nên xem đó là "song song nhân đôi" hay tự động tốt hơn.

Hãy chọn một mô hình đo rõ ràng:

- Mapper có tính **CPU-bound**: so loop/Stream tuần tự với parallel stream.
- Mapper có tính **I/O-bound** và độc lập: so Stream tuần tự với `mapConcurrent` nhiều giới hạn.
- Hỗn hợp CPU + I/O: xác định bottleneck, băng thông, pool và side effect trước khi thêm concurrency.

Khi có nhiều nguồn dữ liệu khác nhau, cũng cần xem `Spliterator` có chia hiệu quả không và mỗi nguồn có encounter order hay không.


## 15. Bảo đảm mapper thread-safe và không can thiệp nguồn

Thực thi đồng thời nghĩa là nhiều lời gọi `mapper` có thể chạy cùng lúc. Do đó, quy tắc về **stateless, non-interfering và thread safety** của Stream API cần được áp dụng nghiêm túc.

### 15.1. Sai: ghi vào `ArrayList` dùng chung

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherers;

List<String> shared = new ArrayList<>();

List<String> result = ids.stream()
    .gather(Gatherers.mapConcurrent(4, id -> {
        shared.add(id);  // KHONG AN TOAN.
        return "OK:" + id;
    }))
    .toList();
```

`ArrayList` không an toàn khi nhiều thread cùng ghi. `mapConcurrent` có thể chạy nhiều mapper đồng thời, làm mất dữ liệu, sai thứ tự hoặc ném lỗi. Thêm `Collections.synchronizedList` có thể giải quyết một phần đồng bộ nhưng **không làm cho thứ tự ghi** trùng encounter order.

Cách đúng: để mapper **trả kết quả**, rồi dùng terminal operation:

```java
List<String> result = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, id -> "OK:" + id))
    .toList();
```

Đây là mẫu một-một dễ kiểm thử, không cần một danh sách bên ngoài.

### 15.2. Không sửa nguồn trong mapper

Sai về nguyên tắc:

```java
// KHONG NEN:
// ids.stream()
//     .gather(Gatherers.mapConcurrent(4, id -> {
//         ids.remove(id); // Can thiep nguon dang duyet.
//         return id;
//     }))
//     .toList();
```

Ngay cả trên một `List` không có thread khác, việc sửa cấu trúc nguồn trong khi duyệt có thể làm kết quả không xác định hoặc gây `ConcurrentModificationException`. Nếu cần thay đổi dữ liệu, tạo kết quả mới rồi thực hiện bước cập nhật tường minh **sau khi pipeline kết thúc**, với chính sách transaction phù hợp.

### 15.3. Bộ đếm để quan sát khác trạng thái nghiệp vụ

`AtomicInteger` có thể phù hợp để đo `active/peak` trong một test. Nhưng không nên dùng counter chia sẻ để **quyết định giá trị đầu ra theo thứ tự**:

```java
AtomicInteger sequence = new AtomicInteger();

List<String> result = ids.stream()
    .gather(Gatherers.mapConcurrent(4, id ->
        sequence.incrementAndGet() + ":" + id))
    .toList();
```

Counter tăng theo **thứ tự mapper chạy**, không phải encounter order. Dù `result` được đặt đúng thứ tự nguồn, số thứ tự gắn với ID có thể không tăng liên tiếp theo vị trí.

Nếu cần số thứ tự chuẩn, hãy đánh chỉ số **trước** khi chạy mapper, hoặc dựa vào khóa sẵn có. Không dùng lịch thread làm nguồn sinh khóa nghiệp vụ.

## 16. Bộ nhớ, throughput và tail latency

`maxConcurrency` có thể giúp kiểm soát số tác vụ in-flight, nhưng không tự bảo đảm một ngưỡng RAM hay thời gian phản hồi.

### 16.1. Các thành phần chiếm tài nguyên

- Các input chưa được xử lý hoặc đang chờ phát.
- Virtual threads và trạng thái thực thi của mỗi mapper.
- Kết nối HTTP/JDBC, buffer yêu cầu/phản hồi và tài nguyên native.
- Kết quả mapper đã hoàn thành nhưng phải chờ phần tử sớm hơn để giữ encounter order.
- Các collection mà terminal operation như `toList` giữ lại.
- Cấu trúc bên trong những bước khác: `sorted`, `distinct`, `groupingBy`.

Do đó "chỉ có bốn mapper đồng thời" **không đồng nghĩa** "chỉ cần bộ nhớ tương đương bốn chuỗi nhỏ". Một mapper có thể nhận hoặc tạo object rất lớn; một downstream `toList` vẫn giữ toàn bộ dữ liệu đầu ra.

### 16.2. Concurrency và throughput theo mô hình gần đúng

Trong điều kiện ổn định, nếu một mapper cần trung bình `W` giây và có `C` slot mapper liên tục bận, một ước lượng thô là:

\[
\text{Throughput lý tưởng} \approx \frac{C}{W}
\]

Ví dụ toán học: `C = 5`, `W = 0,1` giây, trần gần đúng là 50 tác vụ/giây. Đây **không phải số đo thực tế** và không phải rate limit được áp đặt. Throughput có thể thấp hơn do head-of-line blocking, giới hạn dịch vụ ngoài, timeout, GC hoặc nguồn không cung cấp dữ liệu kịp.

Tăng `C` không đảm bảo tăng throughput tuyến tính. Khi dịch vụ ngoài quá tải, thời gian `W` có thể tăng; lúc đó thêm concurrency làm hàng chờ lớn hơn và tail latency xấu đi.

### 16.3. Khi nào công việc CPU-bound không hưởng lợi?

Ví dụ:

```java
List<Long> squares = values.stream()
    .gather(Gatherers.mapConcurrent(
        100, x -> x * x))
    .toList();
```

Nếu `values` là một list nhỏ và mapper chỉ nhân một phép `long`, chi phí chuẩn bị/lập lịch nhiều virtual threads có thể vượt lợi ích. So với `values.stream().map(x -> x * x)`, `mapConcurrent` không có lợi thế mặc định.

Với CPU-heavy work trên nguồn lớn, hãy benchmark `parallelStream` hoặc một mô hình executor phù hợp, đồng thời kiểm tra số lõi và cách chia việc. Virtual threads chủ yếu cải thiện **khả năng quản lý nhiều tác vụ chờ**, không tạo thêm năng lực CPU.

## 17. Kết hợp với các stage khác của Java Stream API

`mapConcurrent` là một bước trung gian trong pipeline, không thay thế các phép lọc, thu thập hoặc tổng hợp.

### 17.1. Lọc trước khi tra cứu để giảm số lời gọi I/O

```java
List<String> result = orders.stream()
    .filter(order -> order.isActive())
    .gather(Gatherers.mapConcurrent(
        4, order -> lookup(order.getId())))
    .toList();
```

Đây là **pseudocode có kiểu miền**: cần định nghĩa `orders`, lớp Order và `lookup` khi dùng trong ứng dụng. Ý nghĩa: bỏ qua những bản ghi không cần gọi API **trước khi** khởi chạy các mapper có thể tốn I/O.

Nếu đổi vị trí filter để lọc trên dữ liệu đã tra cứu, hệ thống sẽ làm nhiều lời gọi hơn. Đó có thể là yêu cầu thật, nhưng phải được mô tả rõ.

### 17.2. Lọc sau khi tra cứu nếu điều kiện chỉ biết từ kết quả

```java
List<String> paid = orderIds.stream()
    .gather(Gatherers.mapConcurrent(
        4, id -> fetchStatus(id)))
    .filter(status -> status.equals("PAID"))
    .toList();
```

Bước này phải tra cứu trước vì điều kiện nằm ở kết quả. **Không đánh đồng** `filter` sau mapper với việc bỏ bớt lời gọi ngoài; những đơn bị loại đã được tra cứu.

### 17.3. Thu báo cáo kết quả sau mapping

```java
Map<String, Long> countByStatus = orderIds.stream()
    .gather(Gatherers.mapConcurrent(
        4, id -> fetchStatus(id)))
    .collect(java.util.stream.Collectors.groupingBy(
        status -> status,
        java.util.stream.Collectors.counting()));
```

Ở đây `groupingBy` là terminal collector, còn `mapConcurrent` là intermediate gatherer. Mặc dù mapper có thể chạy đồng thời, collector **không tự trở thành concurrent collector**; điều đó không cần thiết để có kết quả đúng.

Nếu cần thứ tự hiển thị rõ, sau khi nhóm có thể sắp xếp `entrySet()` theo giá trị và khóa; không dựa vào thứ tự của `HashMap`.

### 17.4. Kết quả rỗng

Với nguồn rỗng, mapper không có đầu vào để xử lý:

```java
List<String> empty = Stream.<Integer>empty()
    .gather(Gatherers.mapConcurrent(
        3, n -> "ID-" + n))
    .toList();

System.out.println(empty); // []
```

Dữ liệu rỗng là một ca hợp lệ và không nên tự tạo kết quả placeholder. Nếu cần thông tin "không tìm thấy", hãy định nghĩa kiểu kết quả hoặc `Optional` theo nghiệp vụ.

## 18. Chương trình kiểm thử tổng hợp Java 24+

Ví dụ này kiểm tra **mức concurrency thực tế quan sát được**, kết quả giữ thứ tự, tính một-một, nguồn rỗng, tham số sai, exception và việc chạy mapper trên virtual threads.

Tạo file `MapConcurrentCheck.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class MapConcurrentCheck {

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static String fakeLookup(
            int id,
            AtomicInteger active,
            AtomicInteger peak) {

        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);

        try {
            // Mô phỏng những request có độ trễ khác nhau.
            Thread.sleep(8L + (id % 3) * 4L);
            return "ID-" + id;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Lookup bi ngat", ex);
        } finally {
            active.decrementAndGet();
        }
    }

    public static void main(String[] args) {
        List<String> expected = IntStream.range(0, 20)
            .mapToObj(id -> "ID-" + id)
            .toList();

        for (int limit : new int[] {1, 2, 4}) {
            AtomicInteger active = new AtomicInteger();
            AtomicInteger peak = new AtomicInteger();

            List<String> actual = IntStream.range(0, 20)
                .boxed()
                .gather(Gatherers.mapConcurrent(
                    limit,
                    id -> fakeLookup(id, active, peak)))
                .toList();

            check(actual.equals(expected),
                "Sai cardinality/thu tu o limit=" + limit);

            check(peak.get() >= 1,
                "Nguon khong rong phai co mapper");

            check(peak.get() <= limit,
                "Vuot maxConcurrency=" + limit);

            check(active.get() == 0,
                "Con mapper dang hoat dong");
        }

        AtomicInteger called = new AtomicInteger();

        List<Integer> empty = Stream.<Integer>empty()
            .gather(Gatherers.mapConcurrent(
                2, n -> {
                    called.incrementAndGet();
                    return n + 1;
                }))
            .toList();

        check(empty.isEmpty() && called.get() == 0,
            "Nguon rong khong duoc goi mapper");

        List<Boolean> virtualThreads = Stream.of(1, 2, 3)
            .gather(Gatherers.mapConcurrent(
                2, n -> Thread.currentThread().isVirtual()))
            .toList();

        check(virtualThreads.equals(
                Arrays.asList(true, true, true)),
            "Mapper phai dung virtual thread");

        boolean rejectedZero = false;
        try {
            Gatherers.mapConcurrent(
                0, (Integer n) -> n * 2);
        } catch (IllegalArgumentException expectedError) {
            rejectedZero = true;
        }
        check(rejectedZero,
            "Phai tu choi maxConcurrency = 0");

        boolean rejectedNullMapper = false;
        try {
            Gatherers.<Integer, Integer>mapConcurrent(
                2, null);
        } catch (NullPointerException expectedError) {
            rejectedNullMapper = true;
        }
        check(rejectedNullMapper,
            "Phai tu choi null mapper");

        boolean mapperFailed = false;
        try {
            Stream.of(1, 2, 3)
                .gather(Gatherers.mapConcurrent(
                    2,
                    n -> {
                        if (n == 2) {
                            throw new IllegalStateException(
                                "Simulated failure");
                        }
                        return n * 10;
                    }))
                .toList();
        } catch (RuntimeException expectedError) {
            mapperFailed = true;
        }
        check(mapperFailed,
            "Mapper loi phai khien pipeline bao loi");

        List<Integer> shortResult = Stream.of(
                1, 2, 3, 4, 5)
            .gather(Gatherers.mapConcurrent(
                3, n -> n * 10))
            .limit(2)
            .toList();

        check(shortResult.equals(Arrays.asList(10, 20)),
            "limit khong dung encounter order");

        System.out.println("PASS: Gatherers.mapConcurrent");
    }
}
```

Khi chạy thành công trên Java 24+:

```text
PASS: Gatherers.mapConcurrent
```

Chương trình **không yêu cầu `peak` phải bằng `limit`**, vì mức đồng thời thực tế còn tùy scheduling và tốc độ callback. Nó cũng **không đo throughput**: `Thread.sleep` giả lập chờ, không mô phỏng hoàn toàn client I/O hoặc độ tải dịch vụ.

### 18.1. Vì sao không khẳng định số mapper chạy sau `limit`?

Test chỉ xác nhận hai kết quả đầu có đúng thứ tự. Nó **cố ý không assert** mapper được gọi đúng hai lần, vì gatherer có thể khởi chạy thêm tác vụ in-flight trước khi downstream dừng. Đây là một điểm quan trọng trong hợp đồng hủy theo best-effort.

### 18.2. Kiểm tra tương đương với mapper tuần tự

Với mapper thuần, kết quả cũng có thể đối chiếu trực tiếp:

```java
List<String> reference = ids.stream()
    .map(id -> "ID-" + id)
    .toList();

List<String> concurrent = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, id -> "ID-" + id))
    .toList();

if (!reference.equals(concurrent)) {
    throw new AssertionError("Khac ket qua mapping");
}
```

Trong đoạn này `ids` là một `List<Integer>` được tạo bên ngoài. So sánh `List.equals` kiểm tra **số phần tử, giá trị và vị trí**; không dùng `Set.equals` vì nó bỏ số lần xuất hiện của những giá trị trùng.

## 19. Đo hiệu năng và quan sát hệ thống

Một phép benchmark nên so cùng công việc, không chỉ so cú pháp:

| Phép thử | Cần đo | Lưu ý |
| --- | --- | --- |
| Mapper CPU nhẹ | Latency/throughput của `map` so với `mapConcurrent` | Virtual threads có thể tăng overhead. |
| Mapper chờ giả lập | Thời gian hoàn thành với nhiều mức concurrency | Không suy ra hiệu năng HTTP thật. |
| Mapper gọi API đọc dữ liệu thật | Latency p50/p95/p99, QPS, timeout, lỗi | Chú ý rate limit và pool kết nối. |
| Nhiều pipeline đồng thời | Throughput toàn dịch vụ, cạnh tranh tài nguyên | Mỗi pipeline có budget riêng. |
| Mapper có kết quả lớn | Heap, allocation, GC, head-of-line buffering | Thứ tự đầu ra có thể tăng thời gian chờ. |

### 19.1. Không suy từ `Thread.sleep` ra tốc độ thực tế

Một ví dụ `Thread.sleep(100)` chỉ thể hiện rằng **các tác vụ chờ có thể chồng lấn**. Không có nghĩa dịch vụ ngoài sẽ cho phép cùng mức concurrency, hay thời gian trả kết quả của mỗi yêu cầu luôn bằng 100 ms.

Khi đo ứng dụng thật, ghi:

- JDK, JVM flags, phần cứng, giới hạn container, môi trường mạng.
- `maxConcurrency` và số pipeline đồng thời.
- Pool kết nối, timeout, số retry, rate limit.
- Số phần tử nguồn, phân phối thời gian mapper, kích thước kết quả.
- Throughput, latency trung bình/p95/p99, timeout/error rate và GC.
- Các trường hợp lỗi, dữ liệu rỗng và nguồn bị cập nhật.

### 19.2. Kích thước dữ liệu lớn, không thu hết mọi thứ nếu không cần

`toList` thu toàn bộ dữ liệu đầu ra vào bộ nhớ. Nếu chỉ cần thống kê, thay bằng một terminal aggregation:

```java
long successCount = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, this::lookup))
    .filter(Result::isSuccess)
    .count();
```

Đây là đoạn code minh họa trong một instance method có `ids` và kiểu `Result` của ứng dụng. Dù không giữ mọi kết quả trong list, mapper và các kết quả in-flight vẫn tiêu thụ tài nguyên. Một thao tác `count` phía sau `filter` cần biết phần tử nào thỏa điều kiện; nhưng đừng đặt side effect bắt buộc trong mapper rồi coi số lần callback là hợp đồng chung cho mọi terminal operation.

## 20. Lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `mapConcurrent` trên JDK 21 | Không có API chuẩn | Dùng Java 24+ hoặc mô hình thay thế. |
| Quên bật preview với Java 22/23 | Lỗi biên dịch/chạy | Bật preview tương ứng hoặc nâng JDK 24+. |
| `maxConcurrency = 0` | `IllegalArgumentException` | Yêu cầu giới hạn ≥ 1. |
| Truyền null mapper | `NullPointerException` | Cung cấp mapper hợp lệ. |
| Hiểu `maxConcurrency` là yêu cầu/giây | Dễ vượt quota dịch vụ | Tách rate limiter khỏi concurrency cap. |
| Hiểu giới hạn ở từng gatherer thành budget toàn hệ thống | Nhiều pipeline cùng vượt tải | Có limiter chung ở lớp dịch vụ/client. |
| Nghĩ virtual threads tạo thêm lõi CPU | Tác vụ CPU-bound không nhanh như kỳ vọng | Xác định bottleneck và benchmark. |
| Nghĩ kết quả ra theo thứ tự hoàn tất mapper | Logic phụ thuộc completion order bị sai | `mapConcurrent` bảo toàn encounter order. |
| Ghi mã thứ tự bằng counter trong mapper | ID/số thứ tự không khớp thứ tự nguồn | Đánh chỉ số trước hoặc dùng khóa nguồn. |
| Ghi `ArrayList` dùng chung trong mapper | Race condition, mất/sai dữ liệu | Trả kết quả rồi dùng terminal collector. |
| Sửa nguồn trong mapper | Vi phạm non-interference | Xử lý trên nguồn ổn định, ghi sau. |
| Dùng `limit(2)` để cam kết chỉ hai yêu cầu ngoài | Tác vụ in-flight có thể đã bắt đầu | Cancellation chỉ best-effort. |
| Dựa vào interrupt như rollback | Side effect từ xa có thể đã commit | Idempotency, transaction/compensation riêng. |
| Không có timeout | Slot mapper có thể kẹt lâu | Deadline/timeout ở client. |
| Retry vô hạn | Bão yêu cầu, giữ slot | Retry giới hạn, backoff, circuit breaker. |
| Giới hạn mapper nhưng mỗi mapper gọi nhiều request con | Vượt concurrency ở hệ thống ngoài | Limit ở lớp tài nguyên thực tế. |
| Nguồn `HashSet` mà kỳ vọng thứ tự ID | Không có encounter order xác định | `sorted` theo khóa ổn định. |
| Thấy `mapConcurrent` chậm hơn `map` khi nhân số | Overhead cao hơn công việc | Dùng `map` cho CPU nhẹ. |
| Giữ toàn bộ kết quả lớn bằng `toList` | Áp lực heap và GC | Thu kết quả cần thiết, phân lô/streaming có kiểm soát. |
| Chỉ đo một pipeline lúc máy rảnh | Không phản ánh tải đồng thời | Đo throughput và latency thực tế. |

## 21. Bài tập thực hành

### Bài 1 — Dự đoán thứ tự

Nguồn `[1,2,3,4]` có mapper của số 1 chậm hơn số 2, 3, 4. Kết quả của `gather(mapConcurrent(4, n -> "N-" + n)).toList()` có bắt buộc ra theo thứ tự mapper hoàn thành không?

### Bài 2 — Giới hạn tối đa

`mapConcurrent(3, mapper)` có luôn chạy đủ ba mapper đồng thời không? Nêu hai lý do mức `peak` thực tế có thể thấp hơn ba.

### Bài 3 — Phân biệt QPS

Dịch vụ chỉ cho phép 20 request/giây. Giải thích vì sao `mapConcurrent(5, callApi)` không đủ để tuân thủ quota. Cần thành phần gì khác?

### Bài 4 — Chọn giải pháp cho CPU-bound

Bài toán cần bình phương một triệu số nguyên trong RAM. Nêu lý do không nên mặc định chọn `mapConcurrent(100, mapper)` và hai phương án nên benchmark.

### Bài 5 — Hủy tác vụ

Có `limit(2)` ngay sau `mapConcurrent(6, remoteCall)`. Có được đảm bảo chỉ hai remote call thực hiện không? Nếu các lời gọi có side effect ghi tiền, cần chính sách nào?

### Bài 6 — Viết bộ kiểm đếm concurrency

Dùng `AtomicInteger active` và `AtomicInteger peak` để kiểm tra `maxConcurrency = 4`. Vì sao decrement nên đặt trong `finally`?

### Bài 7 — Nguồn không có thứ tự

Một `HashSet<Integer>` chứa các ID 5, 1, 4, 2, 3. Hãy lấy kết quả mapping theo thứ tự ID tăng dần mà vẫn dùng `mapConcurrent`.

### Bài 8 — Exception

Một mapper ném `IllegalStateException`. Hãy nêu hợp đồng truyền lỗi của `mapConcurrent` và giải thích vì sao không nên assert chính xác kiểu wrapper/cause chưa được cam kết.

### Bài 9 — Thực thi đồng thời nhiều pipeline

Một server xử lý 20 yêu cầu web đồng thời, mỗi yêu cầu có `mapConcurrent(10, ...)`. Có thể có hơn 10 yêu cầu tới backend trong toàn hệ thống không? Cần đặt limiter ở đâu?

### Bài 10 — Lọc trước và sau map

Nếu một phần tử có cờ `active` sẵn ở dữ liệu gốc, tại sao `filter(active)` trước `mapConcurrent(fetch)` thường tiết kiệm I/O hơn? Khi nào phải lọc sau?

### Bài 11 — So sánh API

Nêu điểm khác biệt giữa `Stream.map`, `mapConcurrent`, `parallelStream` và `CompletableFuture`/executor riêng về quyền quản lý concurrency, thứ tự và lifecycle.

### Bài 12 — Thiết kế bài đo

Thiết kế thử nghiệm chọn `maxConcurrency` trong tập `{1,2,4,8,16}` khi tra cứu một API có giới hạn kết nối. Nêu ít nhất sáu chỉ số/cấu hình phải ghi và tiêu chí dừng tăng mức.

## 22. Đáp án và hướng dẫn

**Bài 1.** Không. Với ordered stream, `mapConcurrent` bảo toàn **encounter order** của kết quả, nên đầu ra là `[N-1,N-2,N-3,N-4]` khi mọi mapper hoàn thành thành công. Lịch thực thi và thứ tự hoàn thành mapper có thể khác.

**Bài 2.** Không. `3` là **giới hạn trên**; nguồn có thể chỉ một phần tử, hoặc mapper quá nhanh/chậm cung cấp dữ liệu khiến mức đồng thời không luôn đạt ba. Scheduling và các bước downstream cũng có thể ảnh hưởng.

**Bài 3.** Concurrency là số yêu cầu **đang tiến hành**, còn quota 20 request/giây là **tần suất**. Nếu các request phản hồi nhanh, năm slot có thể gửi hơn 20 request/giây. Dùng rate limiter theo thời gian, cùng giới hạn concurrency và timeout.

**Bài 4.** Virtual threads không tạo thêm lõi CPU và việc dispatch nhiều mapper có overhead. So vòng lặp hoặc `Stream.map` tuần tự với `parallelStream`/primitive stream phù hợp; kiểm chứng tính đúng và benchmark trên nguồn/máy thực.

**Bài 5.** Không. Một số lời gọi có thể đã in-flight và cancellation là best-effort. Cần idempotency, xác định trạng thái commit, retry có giới hạn và xử lý lỗi một phần/compensation khi phù hợp.

**Bài 6.**

```java
int now = active.incrementAndGet();
peak.accumulateAndGet(now, Math::max);
try {
    return process(id);
} finally {
    active.decrementAndGet();
}
```

`finally` giữ số liệu chính xác khi thành công, exception hoặc interruption; `peak <= 4` là điều cần kiểm tra, không nhất thiết `peak == 4`.

**Bài 7.**

```java
List<String> labels = ids.stream()
    .sorted()
    .gather(Gatherers.mapConcurrent(
        3, id -> "ID-" + id))
    .toList();

// [ID-1, ID-2, ID-3, ID-4, ID-5]
```

`ids` là `HashSet<Integer>` trong bài toán. `sorted` xác định encounter order trước mapper.

**Bài 8.** Khi một kết quả của mapper cần phát downstream nhưng mapper đã hoàn thành với exception, gatherer phát lại exception dưới dạng `RuntimeException`, sau đó cố hủy các tác vụ còn lại. Kiểm tra loại lỗi ở mức hợp đồng, không phụ thuộc tên wrapper/cause hoặc thứ tự side effect nếu API không bảo đảm.

**Bài 9.** Có. Mỗi gatherer có giới hạn cục bộ, nên 20 pipeline có thể cùng làm nhiều mapper. Nếu quota toàn ứng dụng là 10, cần một limiter chung tại client/backend adapter hay nơi gửi yêu cầu, không chỉ đặt `mapConcurrent(10)` ở từng pipeline.

**Bài 10.** Lọc trước tránh gọi `fetch` cho phần tử không active. Nếu điều kiện chỉ biết sau khi gọi API, phải map trước rồi filter theo kết quả; chấp nhận chi phí đã thực hiện.

**Bài 11.** `map` tuần tự thực hiện lần lượt; `mapConcurrent` ánh xạ bằng virtual threads với giới hạn và bảo toàn encounter order; `parallelStream` chia pipeline và không có tham số cap mapper tương đương; `CompletableFuture`/executor riêng cho nhiều quyền điều khiển nhưng phải tự quản lý ordering, lỗi, cancellation và shutdown.

**Bài 12.** Giữ cùng tập ID, tải nền, client và timeout; thử `C={1,2,4,8,16}`, ghi throughput, latency p50/p95/p99, timeout/error rate, pool utilization, in-flight, retry, CPU, allocation/GC và response size. Dừng tăng khi lỗi/thời gian chờ tăng, backend sắp vượt quota, hoặc throughput không còn cải thiện đáng kể. Đo cả một pipeline và nhiều pipeline đồng thời.

## 23. Checklist đưa `mapConcurrent` vào ứng dụng

- [ ] JDK biên dịch và runtime hỗ trợ **Java 24+** hoặc preview đúng phiên bản cũ.
- [ ] Có hiểu rõ quan hệ **một input → một output** khi mapper thành công.
- [ ] `maxConcurrency >= 1` và có giới hạn trên theo thực tế.
- [ ] Phân biệt concurrency cap với **QPS/rate limit**.
- [ ] Có shared limiter nếu nhiều pipeline dùng chung một dịch vụ có quota tổng.
- [ ] Mapper độc lập, thread-safe, non-interfering; không sửa nguồn hoặc collection chia sẻ.
- [ ] Chọn `mapConcurrent` vì nhiều tác vụ **chờ độc lập**, không chỉ vì muốn "chạy nhanh".
- [ ] Không dựa vào thứ tự log hoặc completion để định nghĩa encounter order.
- [ ] Nếu nguồn không ordered, đã xác định/sắp xếp thứ tự nghiệp vụ khi cần.
- [ ] Đã tính tới head-of-line blocking do bảo toàn thứ tự.
- [ ] Mapper I/O có timeout/deadline và client pool phù hợp.
- [ ] Retry, idempotency và rate limit được thiết kế riêng.
- [ ] Không coi interruption/cancellation là rollback side effect đã commit.
- [ ] Không giả định `limit(n)` khiến đúng n mapper đã được gọi.
- [ ] Đã xét kích thước kết quả và chi phí `toList`/buffering.
- [ ] Đã kiểm thử nguồn rỗng, giới hạn 1/2/N, mapper throw, null mapper và đầu vào trùng.
- [ ] Đã đo `peak <= maxConcurrency`, không đòi dùng hết tất cả slot.
- [ ] Đã so kết quả với `map` tuần tự trên mapper thuần.
- [ ] Đã đo latency, throughput, lỗi và tài nguyên dưới tải đại diện.
- [ ] Không ghép `parallel()` với `mapConcurrent` chỉ dựa vào cảm tính.
- [ ] Đã xác định ai sở hữu việc đóng tài nguyên nếu nguồn là `Files.lines`/cursor.
- [ ] Không đưa dữ liệu nhạy cảm, khóa API hoặc payload bí mật vào log mapper.

## 24. Tổng kết và nguồn tham khảo

`Gatherers.mapConcurrent(maxConcurrency, mapper)` đưa một kiểu concurrency có giới hạn vào pipeline Java Stream API:

```java
List<String> result = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, id -> fetchStatus(id)))
    .toList();
```

Đoạn mẫu trên giả định `ids` và `fetchStatus` thuộc chương trình ứng dụng.

Tư duy cần giữ:

1. **Một-một:** một mapper bình thường tạo một kết quả cho mỗi đầu vào.
2. **Giới hạn:** `maxConcurrency` là **trần số lời gọi mapper đồng thời**, không phải QPS.
3. **Virtual threads:** hữu ích với nhiều tác vụ chờ độc lập; không thêm lõi CPU.
4. **Thứ tự:** đầu ra giữ encounter order của nguồn nếu nguồn ordered, không theo completion order.
5. **Hủy:** khi downstream ngừng yêu cầu thêm, cancellation là **best-effort**, không rollback tác vụ ngoài.
6. **Lỗi:** mapper thất bại được phản ánh qua `RuntimeException` khi kết quả tương ứng cần được phát.
7. **Tài nguyên:** có timeout, rate limiter, connection pool, giới hạn bộ nhớ và quản lý vòng đời.
8. **Kiểm chứng:** đo peak concurrency, so kết quả tuần tự và benchmark trên workload thực tế.

Tham khảo chính thức:

- [Javadoc Java 24 — Gatherers.mapConcurrent](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html#mapConcurrent(int,java.util.function.Function))
- [Oracle Java 24 — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html)
- [OpenJDK JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485)

Khi hiểu đúng các hợp đồng trên, bạn có thể dùng Java Stream Gatherers để xử lý nhiều tra cứu độc lập với mức concurrency có kiểm soát, giữ dữ liệu đầu ra ổn định và tránh nhầm lẫn giữa song song hóa, rate limiting, cancellation và an toàn tài nguyên.
