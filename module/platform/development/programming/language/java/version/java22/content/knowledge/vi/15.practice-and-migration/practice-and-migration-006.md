# Bài tập Gatherers: xử lý dữ liệu theo cửa sổ với bộ nhớ có giới hạn

## 1. Mục tiêu và phiên bản sử dụng

Giả sử một dịch vụ ghi liên tục thời gian phản hồi của các request. Bạn cần tính trung bình của **w mẫu gần nhất** mà không giữ toàn bộ lịch sử trong RAM. Đây là bài toán cửa sổ trượt: phần tử mới đi vào, phần tử cũ nhất rời cửa sổ, kết quả được chuyển tiếp ngay khi có đủ dữ liệu.

Trong chương **Vận dụng và nâng cấp** của module Java 22, bài này giúp bạn:

- Phân biệt cửa sổ cố định và cửa sổ trượt theo số phần tử.
- Dùng `Gatherers.windowFixed` và `Gatherers.windowSliding` đúng quy tắc dữ liệu biên.
- Phân tích bộ nhớ đang giữ đồng thời, lượng cấp phát và thời gian xử lý.
- Viết gatherer tuần tự bằng bộ đệm vòng để tính trung bình trượt.
- Xử lý tệp lớn theo dòng, xuất kết quả dần và tôn trọng việc downstream dừng nhận dữ liệu.

Gatherers xuất hiện ở Java 22 dưới dạng preview; xem [API Gatherer của Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/stream/Gatherer.html). Tính năng đã trở thành chính thức từ Java 24 và vẫn có trong Java 25; xem [công bố Java 24 của Oracle](https://blogs.oracle.com/java/the-arrival-of-java-24) và [API Gatherers hiện dùng trong bài](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Gatherers.html).

**Môi trường thực hành:** JDK 25, source và runtime cùng dùng Java 25, không bật preview. Bài dùng API ổn định hiện nay để học kiến thức bắt đầu từ Java 22; không tái sử dụng cấu hình preview cũ. Các chương trình mẫu chỉ dùng thư viện chuẩn.

## 2. Chốt ngữ nghĩa cửa sổ trước khi viết pipeline

### 2.1. Hai kiểu cửa sổ

Cho dữ liệu có thứ tự:

```text
10, 20, 30, 40, 50, 60, 70
```

Với kích thước `w = 3`:

| Cách chia | Các cửa sổ |
| --- | --- |
| Cố định, không chồng lấn | `[10,20,30]`, `[40,50,60]`, `[70]` |
| Trượt một phần tử mỗi bước | `[10,20,30]`, `[20,30,40]`, `[30,40,50]`, `[40,50,60]`, `[50,60,70]` |

`windowFixed` phù hợp xử lý từng lô. `windowSliding` phù hợp khi kết quả mới cần phản ánh các mẫu gần nhất. Chúng chia theo **số phần tử và encounter order**, không tự diễn giải timestamp, đơn vị thời gian hoặc mã cảm biến. Xem [hợp đồng của hai gatherer dựng sẵn](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html).

### 2.2. Đầu vào ngắn và phần đuôi

Với `w = 3`, kết quả dựng sẵn là:

| Đầu vào | `windowFixed(3)` | `windowSliding(3)` |
| --- | --- | --- |
| Rỗng | Không có cửa sổ | Không có cửa sổ |
| `[10]` | `[10]` | `[10]` |
| `[10,20]` | `[10,20]` | `[10,20]` |
| `[10,20,30]` | `[10,20,30]` | `[10,20,30]` |
| `[10,20,30,40]` | `[10,20,30]`, `[40]` | `[10,20,30]`, `[20,30,40]` |

Cửa sổ cố định có thể phát lô cuối chưa đủ `w` phần tử. Cửa sổ trượt phát một cửa sổ ngắn nếu **toàn bộ đầu vào hữu hạn không rỗng nhưng ngắn hơn w**; nó không phát tiếp các hậu tố ngắn dần sau khi đã có cửa sổ đầy. Hai phương thức yêu cầu kích thước dương; các danh sách đầu ra không cho sửa cấu trúc. Xem [chi tiết API Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Gatherers.html).

Bài tập trung bình trượt dưới đây chọn một chính sách rõ ràng: **chỉ phát kết quả cho cửa sổ đủ w mẫu**. Vì vậy, với đầu vào ngắn hơn `w`, kết quả phải rỗng. Khi dùng `windowSliding`, cần lọc cửa sổ ngắn để thực hiện chính sách này.

Gọi `n` là số mẫu hợp lệ được xử lý và `w >= 1`. Số kết quả theo chính sách của bài là:

```text
m = max(0, n - w + 1)
```

## 3. Bộ nhớ có giới hạn cần được hiểu cho cả pipeline

### 3.1. Những gì phải tính vào ngân sách

Một gatherer chỉ giữ `w` phần tử chưa đủ chứng minh toàn chương trình dùng bộ nhớ độc lập với `n`. Cần nhìn cả nguồn dữ liệu, các bước trung gian và nơi nhận kết quả:

```text
Nguồn đọc dần → xử lý một cửa sổ → kết quả nhỏ → nơi nhận tiêu thụ dần
    M_source        M_window       M_result         M_sink
```

Ví dụ sau giữ tất cả cửa sổ đầu ra:

```java
var allWindows = samples.gather(Gatherers.windowSliding(w)).toList();
```

Với `m` cửa sổ đầy, danh sách kết quả biểu diễn khoảng `m * w` vị trí phần tử. Không có cam kết API về cách chia sẻ lưu trữ nội bộ để dựa vào cho một giới hạn nhỏ hơn; cũng không có nghĩa mỗi đối tượng mẫu được nhân bản sâu. Riêng việc giữ mọi đầu ra đã phá mục tiêu xử lý không phụ thuộc độ dài lịch sử.

Nếu chuyển mỗi cửa sổ thành một `double` rồi vẫn gom toàn bộ bằng `toList()`, bạn giữ `O(m)` kết quả. Bộ nhớ có giảm so với giữ mọi cửa sổ, nhưng vẫn tăng theo chiều dài dữ liệu.

Một thiết kế phù hợp hơn là xử lý rồi chuyển tiếp ngay:

```java
samples.gather(Gatherers.windowSliding(w))
       .filter(window -> window.size() == w)
       .mapToDouble(window -> window.stream()
                                    .mapToLong(Long::longValue)
                                    .average()
                                    .orElseThrow())
       .forEach(value -> System.out.println(value));
```

Đoạn này minh họa đầu ra được tiêu thụ dần. Nó chưa tối ưu CPU cho cửa sổ trượt và cần các import, biến nguồn thích hợp trong chương trình thực hành.

### 3.2. Ba đại lượng khác nhau

| Đại lượng | Câu hỏi cần trả lời |
| --- | --- |
| Bộ nhớ còn được giữ đồng thời | Có bao nhiêu dữ liệu vẫn còn tham chiếu và chưa thể thu hồi? |
| Tổng lượng cấp phát | Qua cả lần chạy đã tạo bao nhiêu mảng, danh sách hoặc record? |
| Thời gian xử lý | Mỗi mẫu đi qua có cần duyệt lại toàn bộ cửa sổ không? |

Một pipeline có thể chỉ giữ `O(w)` dữ liệu cửa sổ tại một thời điểm nhưng liên tục tạo đối tượng mới. Áp lực GC và chi phí CPU vẫn có thể cao. Với cách tính lại trung bình bằng cách duyệt từng cửa sổ đầy, riêng phép cộng cần `O(m * w)` thời gian.

`O(w)` cũng chưa phải một giới hạn số byte nếu `w` không được chặn, hoặc mỗi phần tử có thể chứa một payload rất lớn. Bài này sẽ đặt giới hạn cả kích thước cửa sổ lẫn miền giá trị mẫu, rồi dùng mảng số nguyên thủy để phân tích được ngân sách.

## 4. Bài tập A: xử lý từng lô bằng windowFixed

Yêu cầu: đọc bảy mẫu, chia lô tối đa ba phần tử, in số mẫu và trung bình của từng lô; giữ cả lô cuối chưa đầy.

Tạo `FixedWindowExercise.java` trong thư mục thực hành riêng:

```java
import java.util.Locale;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FixedWindowExercise {
    public static void main(String[] args) {
        Stream.of(10L, 20L, 30L, 40L, 50L, 60L, 70L)
                .gather(Gatherers.windowFixed(3))
                .forEach(batch -> {
                    double mean = batch.stream()
                            .mapToLong(Long::longValue)
                            .average()
                            .orElseThrow();
                    System.out.printf(Locale.ROOT,
                            "count=%d, mean=%.1f%n", batch.size(), mean);
                });
    }
}
```

Đầu ra mong đợi:

```text
count=3, mean=20.0
count=3, mean=50.0
count=1, mean=70.0
```

Mỗi mẫu chỉ thuộc một lô nên việc tính tổng trên tất cả các lô cần `O(n)` phép xử lý phần tử. Nếu thay `forEach` bằng việc gửi lô tới một hệ thống khác, hệ thống nhận cũng phải tiêu thụ hoặc giới hạn số lô đang chờ; một hàng đợi tăng vô hạn vẫn làm mất giới hạn bộ nhớ.

Danh sách không cho sửa không làm các đối tượng bên trong tự trở thành bất biến. Trong bài, `Long` là giá trị bất biến; khi đổi sang một lớp mutable, cần tự xác định quyền sở hữu và thời điểm đọc dữ liệu.

## 5. Bài tập B: trung bình trượt bằng windowSliding

Yêu cầu: cùng dữ liệu, `w = 3`, chỉ tính cửa sổ đầy. Tạo `SlidingWindowExercise.java`:

```java
import java.util.Locale;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class SlidingWindowExercise {
    public static void main(String[] args) {
        int windowSize = 3;

        Stream.of(10L, 20L, 30L, 40L, 50L, 60L, 70L)
                .gather(Gatherers.windowSliding(windowSize))
                .filter(window -> window.size() == windowSize)
                .mapToDouble(window -> window.stream()
                        .mapToLong(Long::longValue)
                        .average()
                        .orElseThrow())
                .forEach(mean -> System.out.printf(Locale.ROOT, "%.1f%n", mean));
    }
}
```

Đầu ra mong đợi:

```text
20.0
30.0
40.0
50.0
60.0
```

Thay nguồn bằng hai mẫu, bạn phải nhận được không có kết quả sau bước `filter`. Nếu bỏ bước lọc, API dựng sẵn phát cửa sổ ngắn khi nguồn kết thúc, và chương trình sẽ tính trung bình của hai mẫu đó.

Đây là lời giải dễ đọc khi cửa sổ nhỏ hoặc hàm tổng hợp cần nhìn toàn bộ cửa sổ. Với luồng dài và cửa sổ lớn, phép tính tổng lặp lại công việc: chẳng hạn hai cửa sổ `[10,20,30]` và `[20,30,40]` có hai phần tử chung. Bài tiếp theo giữ tổng hiện tại để tránh tính lại.

## 6. Bài tập C: thiết kế gatherer với bộ đệm vòng

### 6.1. Hợp đồng của lời giải

Viết phương thức `rollingStats(int windowSize)` với yêu cầu:

| Thuộc tính | Quy định trong bài |
| --- | --- |
| Loại cửa sổ | Theo số mẫu, trượt một mẫu mỗi bước |
| Thứ tự | Theo thứ tự xuất hiện trong nguồn có thứ tự |
| Kích thước | Từ 1 đến 100.000 mẫu |
| Giá trị đầu vào | Số nguyên mili giây từ 0 đến 60.000; không nhận `null` |
| Khi chưa đủ mẫu | Chưa phát kết quả |
| Khi đủ mẫu | Phát tổng, số mẫu và vị trí kết thúc; trung bình tính từ tổng |
| Khi hết nguồn | Không phát cửa sổ ngắn, không phát lặp cửa sổ cuối |
| Bộ nhớ trạng thái | Một mảng `long[w]` và số lượng cố định các biến |
| Chế độ | Tuần tự |
| Khi downstream ngừng nhận | Trả tín hiệu dừng, không cố giữ đầu ra để gửi lại |

Các mức 100.000 và 60.000 là **giới hạn của bài tập**, không phải giới hạn do API Gatherers quy định.

### 6.2. Trạng thái và bất biến

Bộ đệm vòng có các thành phần:

- `values`: chứa các mẫu còn thuộc cửa sổ.
- `next`: vị trí sẽ ghi mẫu tiếp theo; khi cửa sổ đã đầy, đó cũng là vị trí của mẫu cũ nhất.
- `used`: số ô đã có mẫu, luôn từ 0 đến `w`.
- `sum`: tổng các mẫu đang giữ.
- `seen`: tổng số mẫu đã xử lý, dùng làm chỉ số kết thúc không bao gồm cận cuối.

Mỗi mẫu mới đi qua các bước:

```text
Kiểm tra mẫu
    ↓
Cửa sổ đã đầy? Có → trừ mẫu cũ tại next
               Chưa → tăng used
    ↓
Ghi mẫu mới tại next, cộng vào sum
    ↓
Dịch next theo vòng, tăng seen
    ↓
used < w → chờ thêm mẫu
used = w → phát một kết quả nhỏ
```

Sau mỗi lần cập nhật, `sum` bằng tổng của `used` mẫu còn thuộc cửa sổ; `next` luôn thuộc `[0, w)`. Khi cửa sổ đầy, kết quả đại diện cho đoạn chỉ số `[seen - w, seen)`.

Ví dụ tại `w = 3`:

| Mẫu vừa đọc | Các mẫu theo thứ tự thời gian trong cửa sổ | Tổng | Kết quả |
| --- | --- | --- | --- |
| 10 | `[10]` | 10 | Chưa phát |
| 20 | `[10,20]` | 30 | Chưa phát |
| 30 | `[10,20,30]` | 60 | Trung bình 20 |
| 40 | `[20,30,40]` | 90 | Trung bình 30 |
| 50 | `[30,40,50]` | 120 | Trung bình 40 |

Thứ tự vật lý trong mảng có thể đã quay vòng; không cần xếp lại mảng để tính tổng.

## 7. Lời giải tham khảo hoàn chỉnh

Tạo `RollingLatencyLab.java` trong thư mục thực hành riêng. Chương trình đọc một mẫu trên mỗi dòng và ghi CSV dần:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;
import java.util.Objects;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class RollingLatencyLab {
    private static final int MAX_WINDOW = 100_000;
    private static final long MAX_LATENCY_MS = 60_000L;

    public record WindowStat(long endExclusive, int count, long sumMs) {
        public double averageMs() {
            return (double) sumMs / count;
        }
    }

    private static final class Ring {
        final long[] values;
        int next;
        int used;
        long sum;
        long seen;

        Ring(int windowSize) {
            values = new long[windowSize];
        }
    }

    public static Gatherer<Long, ?, WindowStat> rollingStats(int windowSize) {
        if (windowSize < 1 || windowSize > MAX_WINDOW) {
            throw new IllegalArgumentException(
                    "windowSize must be between 1 and " + MAX_WINDOW);
        }

        return Gatherer.<Long, Ring, WindowStat>ofSequential(
                () -> new Ring(windowSize),
                (state, boxedValue, downstream) -> {
                    long value = Objects.requireNonNull(boxedValue, "latencyMs");
                    if (value < 0 || value > MAX_LATENCY_MS) {
                        throw new IllegalArgumentException(
                                "latencyMs must be between 0 and " + MAX_LATENCY_MS);
                    }

                    if (state.used == windowSize) {
                        state.sum -= state.values[state.next];
                    } else {
                        state.used++;
                    }

                    state.values[state.next] = value;
                    state.sum += value;

                    state.next++;
                    if (state.next == windowSize) {
                        state.next = 0;
                    }
                    state.seen = Math.incrementExact(state.seen);

                    if (state.used < windowSize) {
                        return true;
                    }

                    return downstream.push(new WindowStat(
                            state.seen, windowSize, state.sum));
                });
    }

    private static void writeCsv(BufferedWriter writer, WindowStat stat) {
        try {
            writer.write(String.format(Locale.ROOT, "%d,%d,%.3f%n",
                    stat.endExclusive() - stat.count(),
                    stat.endExclusive(),
                    stat.averageMs()));
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    public static void runCsv(Path input, Path output, int windowSize)
            throws IOException {
        Gatherer<Long, ?, WindowStat> gatherer = rollingStats(windowSize);

        try (Stream<String> lines = Files.lines(input, StandardCharsets.UTF_8);
             BufferedWriter writer = Files.newBufferedWriter(
                     output,
                     StandardCharsets.UTF_8,
                     StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE)) {
            writer.write("startInclusive,endExclusive,averageMs");
            writer.newLine();

            lines.sequential()
                    .map(Long::valueOf)
                    .gather(gatherer)
                    .forEach(stat -> writeCsv(writer, stat));
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: RollingLatencyLab <input> <output> <windowSize>");
        }

        runCsv(Path.of(args[0]), Path.of(args[1]), Integer.parseInt(args[2]));
    }
}
```

`Gatherer.ofSequential(initializer, integrator)` tạo một gatherer có trạng thái riêng cho mỗi lần đánh giá pipeline. Trong mẫu, mỗi lần gọi initializer tạo một `Ring` mới; đối tượng gatherer chỉ giữ cấu hình kích thước cửa sổ. Kết quả là record chứa các giá trị số, không chứa tham chiếu tới mảng đang bị thay đổi. Xem [factory và hợp đồng trạng thái của Gatherer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Gatherer.html).

### 7.1. Vì sao không có finisher riêng?

Chính sách của bài chỉ phát cửa sổ đầy. Mỗi cửa sổ đầy đã được phát ngay khi mẫu tương ứng tới nơi, nên khi hết nguồn không còn đầu ra cần phát thêm. Không có finisher giúp tránh hai lỗi phổ biến: phát cửa sổ ngắn ngoài hợp đồng hoặc phát lại cửa sổ cuối đã gửi.

Nếu đổi bài toán sang phát lô cuối chưa đủ kích thước, phải thiết kế lại hành vi kết thúc. Không thêm thao tác flush chỉ vì thấy gatherer có khái niệm finisher.

### 7.2. Vì sao phải trả giá trị của push?

`downstream.push(result)` trả về khả năng tiếp tục nhận phần tử của downstream. Khi nó trả `false`, downstream không nhận thêm; giá trị này không phải lời yêu cầu giữ kết quả để thử gửi lại. Xem [Gatherer.Downstream.push](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Gatherer.Downstream.html).

Integrator trả `true` khi cần tiếp tục đọc đầu vào, `false` khi cần dừng. Mẫu trả lại tín hiệu từ `push` để phối hợp với các bước như `limit` hoặc `findFirst`; xem [Gatherer.Integrator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Gatherer.Integrator.html).

Đây là cơ chế dừng hợp tác trong pipeline Stream. Nó không tự tạo giao thức mạng, giới hạn tốc độ nguồn hay quản lý hàng đợi bất đồng bộ bên ngoài.

## 8. Chạy chương trình với tệp và đọc kết quả

Chuẩn bị `latency.txt`, mỗi dòng một số nguyên mili giây; không có header hay dòng trống:

```text
10
20
30
40
50
60
70
```

Biên dịch và chạy từ thư mục chứa source bằng JDK 25:

```powershell
java --version
javac --version
javac --release 25 -encoding UTF-8 -d out RollingLatencyLab.java
if ($LASTEXITCODE -ne 0) { throw 'Biên dịch thất bại' }
java -cp out RollingLatencyLab latency.txt rolling.csv 3
if ($LASTEXITCODE -ne 0) { throw 'Xử lý dữ liệu thất bại' }
```

Không cần `--enable-preview`. `rolling.csv` phải có nội dung:

```text
startInclusive,endExclusive,averageMs
0,3,20.000
1,4,30.000
2,5,40.000
3,6,50.000
4,7,60.000
```

Chỉ số bắt đầu tính từ 0, cận cuối không thuộc đoạn. Ví dụ `[1,4)` tương ứng ba mẫu `20,30,40`.

Mẫu dùng `CREATE_NEW`, vì vậy tệp đầu ra phải chưa tồn tại; khi chạy lại có thể chọn tên mới. Nếu dữ liệu sai hoặc có lỗi I/O giữa chừng, chương trình thất bại và tệp đầu ra có thể mới chỉ được ghi một phần. Chỉ dùng tệp đó làm kết quả hoàn chỉnh khi lần chạy kết thúc thành công.

`Files.lines` cung cấp các dòng theo nhu cầu thay vì đọc toàn bộ tệp vào danh sách. Stream giữ tài nguyên tệp nên được đóng bằng try-with-resources, kể cả khi xử lý thất bại hoặc dừng sớm. Xem [Files.lines](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset)).

Trong lời giải, `Long::valueOf` báo lỗi nếu một dòng không parse được; gatherer báo lỗi với số ngoài miền cho phép. Không có bước bỏ qua mẫu lỗi. Nếu chọn bỏ qua mẫu lỗi trong một ứng dụng khác, cửa sổ sẽ tính theo chuỗi mẫu còn lại và vị trí đầu ra cần được định nghĩa lại.

## 9. Phân tích giới hạn bộ nhớ và độ phức tạp

### 9.1. Phần trạng thái gatherer

Với `w <= 100.000`, payload của mảng `long[w]` là:

```text
8 * w byte <= 800.000 byte
```

Đây là số byte cho phần tử mảng, chưa cộng header mảng, các field, header đối tượng và chi phí JVM. Nó không phải một phép đo tổng heap của chương trình. Vì gatherer chỉ giữ mảng và số lượng cố định các biến, bộ nhớ trạng thái là `O(w)` và không tăng theo `n`.

Mảng được cấp phát theo `w` ngay khi initializer tạo trạng thái, kể cả nguồn sau đó có ít mẫu. Đặt giới hạn `w` là một phần của hợp đồng bộ nhớ, không chỉ kiểm tra `w > 0`.

### 9.2. Vì sao dùng long cho tổng?

Miền giá trị của bài đảm bảo:

```text
0 <= sum <= 100.000 * 60.000 = 6.000.000.000
```

Giá trị này vượt khả năng chứa của `int`, nhưng nằm trong `long`. Khi trượt, chương trình trừ mẫu cũ trước rồi mới cộng mẫu mới nên tổng vẫn nằm trong giới hạn đã chứng minh. Trung bình chỉ chuyển sang `double` ở phép chia; không cộng/trừ liên tục bằng số thực.

Đếm `seen` dùng `Math.incrementExact` để báo lỗi nếu vượt miền `long`, thay vì âm thầm quay vòng chỉ số. Không có kiểu số nguyên cố định nào biểu diễn được số mẫu tăng vô hạn theo nghĩa toán học.

### 9.3. Chi phí của toàn quá trình

| Cách tính cửa sổ đầy | Thời gian tính tổng | Dữ liệu cửa sổ cần giữ | Nếu gom mọi đầu ra |
| --- | --- | --- | --- |
| `windowSliding` rồi duyệt lại từng cửa sổ | `O(m * w)` | Phụ thuộc bộ đệm và biểu diễn cửa sổ của thư viện | Giữ trung bình: `O(m)`; giữ mọi cửa sổ có thể lớn hơn nhiều |
| Bộ đệm vòng của bài | `O(n)` | `O(w)` với mảng kích thước xác định | Vẫn tăng `O(m)` nếu gom các record |

Khởi tạo mảng còn có chi phí `O(w)`; nếu tính cả khởi tạo, lời giải bộ đệm vòng là `O(n + w)`. Mỗi lần cập nhật sau khởi tạo cần `O(1)` thao tác số học. Chi phí parse, định dạng CSV và I/O cũng cần tính khi đo chương trình thật.

Mỗi kết quả vẫn tạo một record nhỏ, và nguồn `Stream<Long>` có thể phát sinh boxing. Lời giải không cam kết không cấp phát; nó tránh giữ lịch sử đầu vào và tránh tạo danh sách chứa toàn bộ mẫu của từng cửa sổ.

### 9.4. Phạm vi của cam kết bộ nhớ

Với nguồn và nơi nhận đều xử lý dần, bộ nhớ còn giữ có dạng:

```text
O(w + L + B_in + B_out)
```

Trong đó `L` là kích thước dòng hiện tại, `B_in` và `B_out` là bộ đệm I/O cùng chi phí triển khai liên quan. Mô hình giả định dữ liệu đầu vào có độ dài dòng được giới hạn hợp lý và không có nơi nhận tích lũy lịch sử.

`Files.lines` không phải bộ đọc tự áp hạn mức độ dài dòng. Với dữ liệu có dòng rất dài, dòng đó có thể đã được cấp phát trước khi `Long::valueOf` từ chối. Nếu cần hạn mức RAM cứng ngay cả với đầu vào sai định dạng, phải bổ sung nguồn đọc giới hạn số ký tự/byte trước khi tạo cả dòng. Kiểm tra `line.length()` sau khi dòng đã được tạo không loại bỏ đỉnh cấp phát trước đó.

Dung lượng tệp CSV vẫn tăng `O(m)`. Bộ nhớ heap có giới hạn không đồng nghĩa đầu ra trên đĩa có kích thước cố định.

## 10. Dừng sớm và nguồn không có điểm kết thúc

Gatherer bộ đệm vòng không cần đợi hết nguồn để phát cửa sổ đầy. Có thể ghép với nguồn vô hạn và giới hạn số kết quả:

```java
var firstTwo = Stream.iterate(10L, value -> value)
        .gather(RollingLatencyLab.rollingStats(3))
        .limit(2)
        .toList();
```

Kết quả gồm hai record với `endExclusive` lần lượt bằng 3 và 4, mỗi record có `count = 3`, `sumMs = 30`. Việc gom hai kết quả ở đây có giới hạn tường minh; nó khác với gom mọi kết quả từ một nguồn không bị chặn.

Để tạo hai cửa sổ đầy trong pipeline tuần tự trực tiếp này, cần bốn mẫu. Không suy ra từ đó rằng tầng I/O bên dưới cũng chỉ đọc đúng bốn mẫu ở cấp byte; nguồn có thể có bộ đệm đọc trước.

Vị trí của `limit` thay đổi yêu cầu:

```java
// Chỉ cho tối đa 100 mẫu đầu vào đi qua: w = 1.000 thì chưa có cửa sổ đầy.
source.limit(100)
      .gather(RollingLatencyLab.rollingStats(1_000));

// Yêu cầu tối đa 100 kết quả: để có đủ cần 1.099 mẫu hợp lệ.
anotherSource.gather(RollingLatencyLab.rollingStats(1_000))
             .limit(100);
```

Hai đoạn trên chỉ là pipeline trung gian minh họa; cần terminal operation để thực thi. `source` và `anotherSource` là hai nguồn mới vì một Stream không được tái sử dụng sau khi đã tham gia pipeline tiêu thụ. Xem [hợp đồng Stream và Stream.gather](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html).

Nếu thêm bộ lọc cảnh báo trước `limit`, số mẫu phải đọc phụ thuộc dữ liệu:

```java
Stream.iterate(10L, value -> value)
        .gather(RollingLatencyLab.rollingStats(3))
        .filter(stat -> stat.averageMs() > 1_000)
        .limit(2)
        .forEach(System.out::println);
```

Nguồn này không bao giờ tạo trung bình vượt 1.000 nên pipeline không kết thúc. Bộ nhớ cửa sổ có giới hạn và khả năng kết thúc là hai thuộc tính phải phân tích riêng. Khi có giới hạn nghiệp vụ về số mẫu cần khảo sát, đặt giới hạn đó ở nguồn hoặc thiết kế điều kiện dừng tương ứng.

## 11. Bộ kiểm tra nhỏ để người học tự chạy

Các kiểm tra dưới đây bảo vệ hợp đồng cửa sổ, miền dữ liệu, khả năng dùng lại gatherer và dừng sớm. Chúng dùng dữ liệu nhỏ nên có thể gom kết quả bằng `toList()` để so sánh. Tạo `RollingLatencyChecks.java` cạnh `RollingLatencyLab.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public class RollingLatencyChecks {
    private static List<RollingLatencyLab.WindowStat> collect(
            int windowSize, Long... values) {
        return Arrays.stream(values)
                .gather(RollingLatencyLab.rollingStats(windowSize))
                .toList();
    }

    private static void checkEquals(Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError("Expected " + expected + ", got " + actual);
        }
    }

    private static void expectFailure(
            Class<? extends RuntimeException> expected, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException exception) {
            if (expected.isInstance(exception)) {
                return;
            }
            throw new AssertionError("Unexpected exception", exception);
        }
        throw new AssertionError("Expected exception: " + expected.getSimpleName());
    }

    public static void main(String[] args) {
        checkEquals(List.of(), collect(3));
        checkEquals(List.of(), collect(3, 10L, 20L));
        checkEquals(
                List.of(new RollingLatencyLab.WindowStat(3, 3, 60)),
                collect(3, 10L, 20L, 30L));

        var all = collect(3, 10L, 20L, 30L, 40L, 50L, 60L, 70L);
        checkEquals(5, all.size());
        checkEquals(List.of(60L, 90L, 120L, 150L, 180L),
                all.stream().map(RollingLatencyLab.WindowStat::sumMs).toList());
        checkEquals(20.0, all.getFirst().averageMs());
        checkEquals(new RollingLatencyLab.WindowStat(7, 3, 180), all.getLast());

        checkEquals(List.of(0L, 60_000L, 7L),
                collect(1, 0L, 60_000L, 7L).stream()
                        .map(RollingLatencyLab.WindowStat::sumMs)
                        .toList());

        expectFailure(IllegalArgumentException.class,
                () -> RollingLatencyLab.rollingStats(0));
        expectFailure(IllegalArgumentException.class,
                () -> RollingLatencyLab.rollingStats(-1));
        expectFailure(IllegalArgumentException.class,
                () -> RollingLatencyLab.rollingStats(100_001));
        expectFailure(IllegalArgumentException.class, () -> collect(1, -1L));
        expectFailure(IllegalArgumentException.class, () -> collect(1, 60_001L));
        expectFailure(NullPointerException.class, () -> collect(1, (Long) null));

        var reusable = RollingLatencyLab.rollingStats(3);
        var firstRun = Stream.of(10L, 20L, 30L).gather(reusable).toList();
        var secondRun = Stream.of(100L, 200L, 300L).gather(reusable).toList();
        checkEquals(List.of(new RollingLatencyLab.WindowStat(3, 3, 60)), firstRun);
        checkEquals(List.of(new RollingLatencyLab.WindowStat(3, 3, 600)), secondRun);

        var limited = Stream.iterate(10L, value -> value)
                .gather(RollingLatencyLab.rollingStats(3))
                .limit(2)
                .toList();
        checkEquals(List.of(
                new RollingLatencyLab.WindowStat(3, 3, 30),
                new RollingLatencyLab.WindowStat(4, 3, 30)), limited);

        System.out.println("All rolling-window checks passed");
    }
}
```

Chạy bằng:

```powershell
javac --release 25 -encoding UTF-8 -d out RollingLatencyLab.java RollingLatencyChecks.java
if ($LASTEXITCODE -ne 0) { throw 'Biên dịch bộ kiểm tra thất bại' }
java -cp out RollingLatencyChecks
if ($LASTEXITCODE -ne 0) { throw 'Kiểm tra thất bại' }
```

Các hàm kiểm tra tự ném `AssertionError`, không phụ thuộc vào việc bật `-ea`. Dòng `All rolling-window checks passed` là đầu ra mong đợi khi người học chạy thành công, không phải số liệu benchmark.

Để kiểm tra rộng hơn, sinh các danh sách nhỏ với nhiều kích thước rồi so sánh tổng từ gatherer tự viết với `windowSliding(w)`, sau khi lọc cửa sổ đầy và tính tổng trực tiếp. Hai lời giải dùng cách tính khác nhau nên phép đối chiếu có thể phát hiện sai vị trí ghi đè, thiếu cửa sổ hoặc phát thừa ở cuối.

## 12. Bài thử dữ liệu lớn mà không tạo danh sách đầu vào

Tạo `RollingLatencyLoad.java`:

```java
import java.util.stream.LongStream;

public class RollingLatencyLoad {
    public static void main(String[] args) {
        long sampleCount = args.length > 0 ? Long.parseLong(args[0]) : 1_000_000L;
        int windowSize = args.length > 1 ? Integer.parseInt(args[1]) : 1_024;
        if (sampleCount < 0) {
            throw new IllegalArgumentException("sampleCount must be nonnegative");
        }

        long actual = LongStream.range(0, sampleCount)
                .map(index -> index % 60_001L)
                .boxed()
                .gather(RollingLatencyLab.rollingStats(windowSize))
                .count();

        long expected = Math.max(0L, sampleCount - windowSize + 1L);
        if (actual != expected) {
            throw new AssertionError("Expected " + expected + ", got " + actual);
        }

        System.out.println("windows=" + actual);
    }
}
```

Chương trình sinh từng mẫu khi pipeline cần, chỉ giữ bộ đếm kết quả ở terminal operation. Nó không in mọi cửa sổ nên tránh để tốc độ console chi phối bài thử.

```powershell
javac --release 25 -encoding UTF-8 -d out RollingLatencyLab.java RollingLatencyLoad.java
if ($LASTEXITCODE -ne 0) { throw 'Biên dịch bài thử tải thất bại' }
java -Xmx64m -cp out RollingLatencyLoad 1000000 1024
java -Xmx64m -cp out RollingLatencyLoad 10000000 1024
```

Số kết quả mong đợi tương ứng là `998977` và `9998977`. Khi giữ `w` cố định và tăng `n`, thời gian cùng tổng lượng cấp phát có thể tăng, nhưng mảng trạng thái vẫn có cùng kích thước. Khi giữ `n` đủ lớn và tăng `w`, phần payload mảng tăng tuyến tính theo `w`.

Một lần chạy không bị hết bộ nhớ chỉ là bằng chứng thực nghiệm trong môi trường đó. Muốn đánh giá đầy đủ, kết hợp phân tích cấu trúc dữ liệu với quan sát heap còn sống sau GC, tốc độ cấp phát và thời gian chạy. Không coi đỉnh heap trước GC là kích thước duy nhất của tập dữ liệu đang được giữ.

`-Xmx64m` giới hạn heap tối đa; nó không giới hạn toàn bộ bộ nhớ process, vốn còn có các phần khác do JVM và hệ điều hành quản lý. Bài không ấn định thời gian hoàn thành hoặc con số RAM đo được trên mọi máy.

## 13. Các thay đổi dễ phá vỡ hợp đồng

| Thay đổi | Hệ quả cần xem xét |
| --- | --- |
| Đọc đầu vào bằng `readAllLines` hoặc gom bằng `toList` trước khi gather | Toàn bộ nguồn đã nằm trong RAM |
| Gom tất cả `WindowStat` sau gather | Bộ nhớ đầu ra tăng theo số cửa sổ |
| Chèn `sorted()` trên nguồn rất lớn hoặc vô hạn | Cần giữ dữ liệu để sắp thứ tự; nguồn vô hạn không có điểm hoàn tất sắp xếp toàn cục |
| Dùng `distinct()` trên lịch sử có nhiều giá trị khác nhau | Tập các giá trị đã gặp có thể tăng theo dữ liệu |
| Chọn cửa sổ cực lớn vì đầu vào thường nhỏ | Cấp phát vẫn có thể lớn; cần giới hạn cấu hình |
| Giữ một mảng hoặc danh sách dùng chung trong các kết quả đã phát | Các kết quả trước có thể bị thay đổi hoặc giữ tham chiếu ngoài dự kiến |
| Tạo `Ring` một lần ngoài initializer rồi dùng lại cho mọi stream | Trạng thái các lần chạy lẫn nhau, khó kiểm soát vòng đời và an toàn luồng |
| Đẩy kết quả vào hàng đợi không giới hạn | Downstream chậm làm bộ nhớ hàng đợi tăng |
| Thêm finisher phát toàn bộ phần còn lại | Có thể phát sai chính sách hoặc phát trùng cửa sổ cuối |
| Giả định mọi lỗi dữ liệu đều được phát hiện khi đã dùng `limit` | Dữ liệu nằm sau điểm dừng có thể chưa được đọc hoặc kiểm tra |

Các gatherer cửa sổ dựng sẵn có thể cấp phát vùng chứa theo kích thước cửa sổ từ sớm; kích thước lớn vẫn có thể tốn bộ nhớ ngay cả với nguồn ngắn. Chọn `w` theo ngân sách thực tế, không theo một giá trị tối đa tùy ý của kiểu `int`.

### 13.1. Không thêm parallel như một bước tối ưu mặc định

Lời giải chọn `ofSequential` để giữ thuật toán theo một chuỗi đầu vào. Nó không cung cấp combiner có khả năng ghép các phân vùng, nên không được giả định thêm `.parallel()` sẽ chia trạng thái thành nhiều bộ đệm vòng và giữ nguyên chứng minh bộ nhớ.

Nếu thiết kế một gatherer cửa sổ hỗ trợ xử lý phân vùng song song, phải xử lý cả các cửa sổ đi qua ranh giới phân vùng, thứ tự phát, trạng thái biên và số phân vùng đang giữ dữ liệu. Chỉ cộng hai tổng cửa sổ độc lập không giải được vấn đề đó. Trong bài này, giữ pipeline tuần tự để hợp đồng và giới hạn trạng thái dễ kiểm chứng.

### 13.2. Cửa sổ thời gian và nhiều khóa là bài toán khác

“1.000 mẫu gần nhất” không tương đương “một giây gần nhất”. Với cửa sổ thời gian, số mẫu trong khoảng thời gian có thể tăng mạnh theo tốc độ đầu vào; chỉ giới hạn thời gian không tự giới hạn số phần tử cần giữ.

Nếu tính riêng theo `sensorId`, một buffer giới hạn cho mỗi cảm biến vẫn có thể cho tổng bộ nhớ tăng theo số cảm biến hoạt động:

```text
Trạng thái tổng xấp xỉ O(K * w), với K là số khóa đang được giữ.
```

Muốn có ngân sách tổng, phải giới hạn cả `K`, kích thước mỗi trạng thái và quy tắc hết hạn hoặc loại bỏ khóa. Quy tắc loại bỏ còn ảnh hưởng đến ý nghĩa kết quả khi cảm biến xuất hiện trở lại. Bài hiện tại chỉ xử lý một chuỗi mẫu có thứ tự và một cửa sổ.

## 14. Bài nộp và tiêu chí hoàn thành

Hoàn thành lần lượt:

1. Chạy bài cửa sổ cố định và giải thích vì sao có lô cuối chỉ chứa một mẫu.
2. Chạy bài cửa sổ trượt với nguồn rỗng, nguồn ngắn hơn `w` và nguồn dài hơn `w`; xác nhận chính sách cửa sổ đầy.
3. Viết `rollingStats` trước khi đối chiếu lời giải tham khảo, trình bày các bất biến của mảng vòng và tổng.
4. Chạy bộ kiểm tra nhỏ, kiểm tra cả dùng lại gatherer với một nguồn mới và dừng sớm trên nguồn vô hạn.
5. Đọc `latency.txt` và ghi CSV dần; đối chiếu cận chỉ số và trung bình của năm cửa sổ mẫu.
6. Chạy bài thử sinh dữ liệu lớn, tăng `n` khi giữ `w` cố định rồi tăng `w` khi giữ `n` cố định.
7. Viết giải thích ngắn về bộ nhớ trạng thái, bộ nhớ toàn pipeline và tổng lượng cấp phát; nêu các giả định đối với nguồn và nơi nhận.

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Đúng phiên bản | Dùng API chính thức trên JDK 25, không cần preview |
| Đúng ngữ nghĩa | `m = max(0, n - w + 1)`, không có cửa sổ ngắn hoặc cửa sổ cuối bị lặp |
| Đúng phép tính | Tổng không dùng `int`; kết quả mẫu và các ca biên khớp kỳ vọng |
| Trạng thái có giới hạn | Một `long[w]`, giới hạn `w` rõ ràng, không giữ lịch sử |
| Đầu ra được tiêu thụ dần | Không gom mọi cửa sổ hoặc mọi record khi chạy dữ liệu lớn |
| Dừng đúng | Tín hiệu downstream được chuyển thành giá trị trả về của integrator |
| Không lẫn trạng thái | Dùng cùng gatherer cho hai stream mới cho kết quả độc lập |
| Phân tích đầy đủ | Phân biệt `O(w)`, chi phí cấp phát, heap toàn process và dung lượng đầu ra |

Bạn hoàn thành bài khi có thể chỉ ra chính xác dữ liệu nào vẫn được giữ sau mỗi mẫu, vì sao mẫu cũ đã được loại khỏi trạng thái, và điều kiện nào đảm bảo bộ nhớ không tăng theo toàn bộ lịch sử đầu vào.
