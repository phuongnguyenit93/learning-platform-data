# Dùng mapMulti trên Stream nguyên thủy

## 1. Khi một số đầu vào tạo ra không, một hoặc nhiều số đầu ra

Trong chương **Stream kiểu nguyên thủy** của **JAVA_STREAM_API**, ta dùng `IntStream`, `LongStream` và `DoubleStream` để xử lý dữ liệu số trực tiếp, tránh phải đóng hộp mọi phần tử thành `Integer`, `Long` hoặc `Double`. Những Stream này vẫn hỗ trợ pipeline lazy với `filter`, `map`, `reduce` và các terminal operation như `sum`, `average`, `summaryStatistics`.

Nhưng `map` chỉ tạo **một** phần tử đầu ra cho **mỗi** phần tử đầu vào. Nếu dữ liệu cần sinh ra 0, 1 hoặc nhiều giá trị thì sao?

Ví dụ:

- Số lượng `0` tương ứng **0** đơn vị cần xử lý.
- Số lượng `1` tương ứng **1** đơn vị.
- Số lượng `3` tương ứng **3** đơn vị.
- Một số đo không hợp lệ được **bỏ qua**; một số đo hợp lệ có thể phát ra nhiều đặc trưng số học.
- Mỗi mã khoảng thời gian có thể tạo ra một dãy vị trí, thay vì chỉ một vị trí.

Từ **Java 16**, các primitive stream cung cấp `mapMulti` để giải quyết trực tiếp những tình huống trên. Lambda nhận giá trị hiện tại và một **consumer của đúng kiểu nguyên thủy**; gọi `accept` bao nhiêu lần thì phát ra bấy nhiêu phần tử.

~~~text
                   IntStream / LongStream / DoubleStream
                                   │
                                   ▼
                        mapMulti((n, out) -> ...)
                                   │
                  ┌────────────────┼────────────────┐
                  ▼                ▼                ▼
              không gọi        gọi accept       gọi accept
               accept            1 lần             N lần
                  │                │                │
                  ▼                ▼                ▼
                0 số              1 số              N số
                  └────────────────┴────────────────┘
                                   │
                                   ▼
                     Cùng loại primitive stream
~~~

Bài này tập trung vào `mapMulti` của **Stream nguyên thủy** và cách phân biệt với `mapMultiToInt`, `mapMultiToLong`, `mapMultiToDouble` của `Stream<T>`. Các ví dụ có thể chạy với **Java 17+**; `Stream.toList()` ở một số đoạn mã cũng yêu cầu Java 16+.

## 2. Ba API `mapMulti` và consumer tương ứng

Các chữ ký khái niệm:

~~~java
// Các method trên ba primitive stream:
IntStream mapMulti(IntStream.IntMapMultiConsumer mapper);
LongStream mapMulti(LongStream.LongMapMultiConsumer mapper);
DoubleStream mapMulti(DoubleStream.DoubleMapMultiConsumer mapper);
~~~

Mỗi functional interface chuyên biệt nhận một giá trị và consumer cùng loại:

~~~java
// Dạng mô tả hợp đồng của các callback:
void accept(int value, IntConsumer downstream);
void accept(long value, LongConsumer downstream);
void accept(double value, DoubleConsumer downstream);
~~~

| Stream đầu vào | Callback | Consumer phát kết quả | Stream trả về |
| --- | --- | --- | --- |
| `IntStream` | `IntStream.IntMapMultiConsumer` | `IntConsumer.accept(int)` | `IntStream` |
| `LongStream` | `LongStream.LongMapMultiConsumer` | `LongConsumer.accept(long)` | `LongStream` |
| `DoubleStream` | `DoubleStream.DoubleMapMultiConsumer` | `DoubleConsumer.accept(double)` | `DoubleStream` |

Tên method đều là `mapMulti`, nhưng kiểu đối số `n` và kiểu `out.accept(...)` được xác định từ loại primitive stream đang gọi.

~~~java
import java.util.stream.IntStream;

int[] result = IntStream.of(2, 0, 3)
    .mapMulti((value, out) -> {
        for (int i = 0; i < value; i++) {
            out.accept(value);
        }
    })
    .toArray();

// result = [2, 2, 3, 3, 3]
~~~

Hàm callback **không trả một Stream con**. Nó trả `void` và gửi các giá trị cho `out`:

- Không gọi `accept`: phát **0 phần tử**.
- Gọi một lần: phát **1 phần tử**.
- Gọi nhiều lần: phát **nhiều phần tử**, theo thứ tự các lời gọi trong callback đối với cùng đầu vào.

Không được giữ lại `out` để sử dụng sau khi callback hoàn thành hoặc gọi nó từ một tác vụ bất đồng bộ. Consumer được truyền vào là cơ chế phát kết quả của **lần xử lý hiện tại**, không phải kênh gửi dữ liệu kéo dài vô hạn.

## 3. `IntStream.mapMulti`: phát số nguyên theo quy tắc

Xét bài toán mô phỏng các lượt kiểm tra. Với mỗi số nguyên dương `n`, ta muốn phát dãy số từ `1` đến `n`. Giá trị bằng `0` không tạo kết quả; giá trị âm là đầu vào không hợp lệ và trong ví dụ minh họa được bỏ qua.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

public class IntMapMultiDemo {
    public static void main(String[] args) {
        int[] slots = IntStream.of(1, 0, 3, -2, 2)
            .mapMulti((n, out) -> {
                if (n <= 0) {
                    return; // Không phát phần tử.
                }

                for (int index = 1; index <= n; index++) {
                    out.accept(index);
                }
            })
            .toArray();

        System.out.println(Arrays.toString(slots));
        // [1, 1, 2, 3, 1, 2]
    }
}
~~~

Từng đầu vào lần lượt tạo ra:

| `n` | Các giá trị được phát |
| --- | --- |
| `1` | `1` |
| `0` | Không có |
| `3` | `1, 2, 3` |
| `-2` | Không có |
| `2` | `1, 2` |

Ở đây `mapMulti` thay thế trực tiếp cho việc tạo một `IntStream.rangeClosed(1, n)` cho mỗi số. Tuy nhiên, nếu mục tiêu thực sự là **phát một khoảng số duy nhất**, `IntStream.range` hoặc `rangeClosed` thường là API đơn giản hơn.

### Ví dụ 0 hoặc 2 kết quả: tạo cặp số

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

public class EvenPairs {
    public static void main(String[] args) {
        int[] values = IntStream.rangeClosed(1, 5)
            .mapMulti((n, out) -> {
                if ((n & 1) == 0) {
                    out.accept(n);
                    out.accept(n * 10);
                }
            })
            .toArray();

        System.out.println(Arrays.toString(values));
        // [2, 20, 4, 40]
    }
}
~~~

Ta có thể nối tiếp một terminal operation của `IntStream` mà **không phải boxing**:

~~~java
int sum = IntStream.rangeClosed(1, 5)
    .mapMulti((n, out) -> {
        if (n % 2 == 0) {
            out.accept(n);
            out.accept(n * 10);
        }
    })
    .sum();

// sum = 66 (2 + 20 + 4 + 40)
~~~

Nếu luôn phát đúng **một** số cho mỗi đầu vào, `map` ngắn gọn và thể hiện chủ đích rõ hơn. Nếu chỉ giữ hoặc bỏ **chính số hiện tại**, `filter` thường phù hợp hơn.

## 4. `LongStream.mapMulti`: xử lý số lượng và giá trị dài

`LongStream` phục vụ miền giá trị `long`, ví dụ mã số lớn, độ dài, số đếm hoặc các khoản tiền lưu dưới dạng đơn vị nhỏ nhất. `LongStream.mapMulti` dùng `LongConsumer` để phát các giá trị `long` mà không đóng hộp qua `Long`.

Ví dụ: mỗi con số cho biết số lượt sử dụng dịch vụ có đơn giá 10.000 đơn vị. Ta phát giá của từng lượt rồi tính tổng:

~~~java
import java.util.Arrays;
import java.util.stream.LongStream;

public class LongMapMultiDemo {
    public static void main(String[] args) {
        long[] unitPrices = LongStream.of(2L, 0L, 3L)
            .mapMulti((quantity, out) -> {
                if (quantity < 0 || quantity > 1000) {
                    throw new IllegalArgumentException(
                        "Số lượng không hợp lệ: " + quantity
                    );
                }

                for (long i = 0; i < quantity; i++) {
                    out.accept(10_000L);
                }
            })
            .toArray();

        System.out.println(Arrays.toString(unitPrices));
        // [10000, 10000, 10000, 10000, 10000]

        long total = LongStream.of(unitPrices).sum();
        System.out.println(total); // 50000
    }
}
~~~

Ví dụ đặt một **giới hạn trên** để tránh việc một lượng đầu vào bất thường khiến chương trình phát hàng triệu phần tử hoặc chạy quá lâu. Dữ liệu thực tế cần kiểm tra cả tính hợp lệ lẫn giới hạn nghiệp vụ trước khi mở rộng.

Nếu chỉ cần tổng, **không cần tạo Stream nhiều giá trị**:

~~~java
long total = LongStream.of(2L, 0L, 3L)
    .map(quantity -> Math.multiplyExact(quantity, 10_000L))
    .sum();

// 50000
~~~

`Math.multiplyExact` phát hiện tràn số khi nhân, nhưng phép `sum()` của `LongStream` vẫn có thể tràn nếu tổng vượt miền `long`; khi độ chính xác tài chính là bắt buộc, cần thiết kế kiểm tra tràn và chính sách số học phù hợp. `mapMulti` là công cụ **mở rộng dữ liệu**, không phải phép tối ưu mặc định cho mọi công thức tổng.

### Khi nào `LongStream.mapMulti` thực sự có ích?

Nó hữu ích nếu bước sau **cần từng giá trị riêng biệt**: phát mã sự kiện, tạo các mốc thời gian hoặc áp một phép biến đổi khác nhau cho mỗi đơn vị. Nếu chỉ tính tổng, trung bình hoặc số lượng thì thường nên tính trực tiếp.

## 5. `DoubleStream.mapMulti`: lọc số đo và phát nhiều đặc trưng

`DoubleStream.mapMulti` hoạt động tương tự, nhưng mapper nhận `double` và một `DoubleConsumer`. Đây là lựa chọn thích hợp khi dữ liệu kết quả là các số thực nguyên thủy.

Ví dụ, với mỗi số đo dương, hữu hạn, phát cả giá trị gốc và một nửa giá trị; bỏ qua `NaN`, giá trị vô hạn và số không dương:

~~~java
import java.util.Arrays;
import java.util.stream.DoubleStream;

public class DoubleMapMultiDemo {
    public static void main(String[] args) {
        double[] values = DoubleStream.of(
                1.5,
                Double.NaN,
                4.0,
                Double.POSITIVE_INFINITY,
                -2.0
            )
            .mapMulti((value, out) -> {
                if (Double.isFinite(value) && value > 0.0) {
                    out.accept(value);
                    out.accept(value / 2.0);
                }
            })
            .toArray();

        System.out.println(Arrays.toString(values));
        // [1.5, 0.75, 4.0, 2.0]
    }
}
~~~

Khi chỉ cần một số trung bình, có thể nối terminal `average()`:

~~~java
double average = DoubleStream.of(1.5, 4.0)
    .mapMulti((value, out) -> {
        out.accept(value);
        out.accept(value / 2.0);
    })
    .average()
    .orElseThrow();

// (1.5 + 0.75 + 4.0 + 2.0) / 4 = 2.0625
~~~

**Lưu ý số học:** `double` dùng dấu chấm động nhị phân IEEE 754; không phải số thập phân nào cũng được biểu diễn chính xác. Tính tổng, trung bình và thứ tự gộp khi xử lý song song có thể dẫn tới chênh lệch làm tròn. Đừng dùng `DoubleStream` với giả định rằng mọi phép tính tiền đều chính xác tuyệt đối; với nghiệp vụ tiền tệ, cân nhắc số nguyên đơn vị nhỏ nhất hoặc `BigDecimal` tùy yêu cầu.

## 6. Phân biệt `IntStream.mapMulti` và `Stream<T>.mapMultiToInt`

Hai tên API dễ gây nhầm vì cùng hỗ trợ phát nhiều giá trị primitive:

| API | Nguồn đầu vào | Đầu ra | Trường hợp dùng |
| --- | --- | --- | --- |
| `IntStream.mapMulti` | `IntStream` | `IntStream` | Đã có từng số `int` và muốn phát 0–n số `int`. |
| `LongStream.mapMulti` | `LongStream` | `LongStream` | Đã có từng số `long` và muốn phát 0–n số `long`. |
| `DoubleStream.mapMulti` | `DoubleStream` | `DoubleStream` | Đã có từng số `double` và muốn phát 0–n số `double`. |
| `Stream<T>.mapMultiToInt` | `Stream<T>` | `IntStream` | Đầu vào là object, cần phát 0–n số `int`. |
| `Stream<T>.mapMultiToLong` | `Stream<T>` | `LongStream` | Đầu vào là object, cần phát 0–n số `long`. |
| `Stream<T>.mapMultiToDouble` | `Stream<T>` | `DoubleStream` | Đầu vào là object, cần phát 0–n số `double`. |

### Ví dụ: từ object đơn hàng sang giá trị long

~~~java
import java.util.List;
import java.util.stream.LongStream;

public class PurchaseUnits {
    record OrderLine(String sku, long unitPrice, int quantity) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("BOOK", 20_000L, 2),
            new OrderLine("PEN", 5_000L, 1),
            new OrderLine("PAD", 9_000L, 0)
        );

        LongStream prices = lines.stream()
            .mapMultiToLong((line, out) -> {
                if (line.quantity() < 0 || line.quantity() > 10_000) {
                    throw new IllegalArgumentException("Số lượng không hợp lệ");
                }
                for (int i = 0; i < line.quantity(); i++) {
                    out.accept(line.unitPrice());
                }
            });

        long total = prices.sum();
        System.out.println(total); // 45000
    }
}
~~~

Nguồn là `Stream<OrderLine>` nên phải dùng **`mapMultiToLong`**, không gọi `LongStream.mapMulti` trực tiếp. Kết quả sau phép biến đổi là `LongStream`, do đó `sum()` tính trực tiếp trên `long`.

Nếu mục tiêu chỉ là tổng giá trị đơn hàng, không cần nở từng đơn vị:

~~~java
long total = lines.stream()
    .mapToLong(line ->
        Math.multiplyExact(line.unitPrice(), line.quantity())
    )
    .sum();
~~~

Đây là ví dụ về nguyên tắc lựa chọn operation: viết theo **yêu cầu đầu ra thực sự**, tránh tạo các phần tử không cần thiết.

### Ví dụ: parse chuỗi thành int mà không boxing ở đầu ra

~~~java
import java.util.List;

public class ParseScores {
    public static void main(String[] args) {
        List<String> raw = List.of(" 10 ", "bad", "", "25");

        int total = raw.stream()
            .mapMultiToInt((text, out) -> {
                try {
                    int score = Integer.parseInt(text.trim());
                    if (score >= 0) {
                        out.accept(score);
                    }
                } catch (NumberFormatException ignored) {
                    // Dữ liệu không parse được, chính sách minh họa là bỏ qua.
                }
            })
            .sum();

        System.out.println(total); // 35
    }
}
~~~

Trong bài toán cần **báo lỗi** đối với dữ liệu sai, đừng âm thầm bỏ qua bằng việc không gọi `accept`. Hãy dùng kiểu kết quả chứa nguyên nhân hoặc một nhánh xử lý lỗi rõ ràng.

## 7. So sánh với `map`, `filter` và `flatMap` của primitive stream

| Operation | Số phần tử đầu ra trên mỗi đầu vào | Ví dụ | Khi nào phù hợp |
| --- | --- | --- | --- |
| `map` | Luôn đúng 1 | `map(n -> n * 2)` | Chuyển đổi số 1–1. |
| `filter` | 0 hoặc 1, giữ chính số đầu vào | `filter(n -> n > 0)` | Chỉ cần chọn hoặc bỏ số. |
| `flatMap` | 0 đến nhiều | `flatMap(n -> IntStream.range(0, n))` | Mapper có thể trả Stream con tự nhiên. |
| `mapMulti` | 0 đến nhiều | `mapMulti((n, out) -> out.accept(n))` | Muốn phát trực tiếp các giá trị nguyên thủy. |

Hai pipeline sau đều tạo dãy `[2, 20, 4, 40]`:

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] viaFlatMap = IntStream.rangeClosed(1, 4)
    .flatMap(n -> n % 2 == 0
        ? IntStream.of(n, n * 10)
        : IntStream.empty())
    .toArray();

int[] viaMapMulti = IntStream.rangeClosed(1, 4)
    .mapMulti((n, out) -> {
        if (n % 2 == 0) {
            out.accept(n);
            out.accept(n * 10);
        }
    })
    .toArray();

System.out.println(Arrays.equals(viaFlatMap, viaMapMulti)); // true
~~~

`flatMap` yêu cầu mapper trả về `IntStream`, `LongStream` hoặc `DoubleStream` tương ứng. `mapMulti` cho phép callback phát trực tiếp từng giá trị, nên mã thường gọn khi mỗi phần tử cần phát một số lượng nhỏ giá trị có điều kiện.

Về hiệu năng, `mapMulti` **có thể** tránh việc tự tạo Stream con cho từng đầu vào và giảm một số chi phí trung gian. Tuy nhiên, **không có cam kết rằng nó không cấp phát bộ nhớ**: triển khai mặc định có thể dùng vùng đệm nội bộ và thực hiện logic tương đương `flatMap`. Hãy benchmark nếu hiệu năng là lý do lựa chọn; đừng thay `flatMap` hàng loạt chỉ theo cảm tính.

### Chuyển đổi giữa các loại primitive

`IntStream.mapMulti` chỉ phát `int`. Nếu kết quả mong muốn là `long` hoặc `double`, hãy chọn bước chuyển loại trước hoặc sau cho phù hợp:

~~~java
import java.util.stream.IntStream;

long sum = IntStream.of(1, 2, 3)
    .mapToLong(n -> (long) n)
    .mapMulti((value, out) -> {
        out.accept(value);
        out.accept(value * 1_000_000_000L);
    })
    .sum();

// Đã chuyển thành LongStream trước khi gọi LongStream.mapMulti.
~~~

Không có method `IntStream.mapMultiToLong` tương ứng với `Stream<T>.mapMultiToLong`. Trường hợp cần phát nhiều giá trị `long` trực tiếp từ một phần tử `int`, có thể cân nhắc `mapToLong(...).mapMulti(...)`, hoặc một phương thức chuyển đổi khác rõ nghĩa hơn.

## 8. Pipeline lazy, thứ tự gặp phần tử và short-circuit

`mapMulti` là **intermediate operation**. Lambda chỉ có cơ hội chạy khi một terminal operation cần dữ liệu. Với nguồn ordered như `IntStream.rangeClosed`, các giá trị đi qua một pipeline tuần tự theo encounter order của nguồn và thứ tự phát trong từng callback.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] output = IntStream.rangeClosed(1, 3)
    .mapMulti((n, out) -> {
        out.accept(n);
        out.accept(-n);
    })
    .toArray();

System.out.println(Arrays.toString(output));
// [1, -1, 2, -2, 3, -3]
~~~

Vì Stream lazy, nếu chỉ xây dựng pipeline mà chưa gọi `toArray()`, `sum()` hoặc terminal operation khác thì không cần tính toán các phần tử. Sau terminal, Stream đã tiêu thụ và không được tái sử dụng.

### `limit` sau `mapMulti` đếm **đầu ra**

~~~java
int[] firstThree = IntStream.rangeClosed(1, 5)
    .mapMulti((n, out) -> {
        out.accept(n);
        out.accept(-n);
    })
    .limit(3)
    .toArray();

// [1, -1, 2]
~~~

`limit(3)` chọn tối đa ba **phần tử đầu ra**. Nó không có nghĩa là thực hiện mapper trên đúng ba **phần tử đầu vào**.

Không viết mapper với vòng lặp **vô hạn** rồi mong `limit` chắc chắn tự dừng vòng lặp bên trong lambda. Một callback có thể tiếp tục thực hiện các lệnh riêng của nó sau khi downstream đã đủ dữ liệu. Hãy bảo đảm mỗi lời gọi mapper có thời gian chạy và số phần tử phát hữu hạn, hợp lý.

### `distinct`, `sorted` và `unordered`

Những operation này vẫn làm việc trên `IntStream`, `LongStream` hoặc `DoubleStream`:

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] distinctSorted = IntStream.of(2, 1, 2, 3)
    .mapMulti((n, out) -> {
        out.accept(n);
        out.accept(n);
    })
    .distinct()
    .sorted()
    .toArray();

System.out.println(Arrays.toString(distinctSorted));
// [1, 2, 3]
~~~

Với nguồn có encounter order, `mapMulti` giữ quan hệ thứ tự tương ứng của các kết quả được phát. Tuy nhiên, `unordered()` có thể bỏ ràng buộc thứ tự; khi chạy song song, thứ tự thực thi callback không nhất thiết là thứ tự nguồn. `sorted()` thiết lập thứ tự mới cho dữ liệu đầu ra khi có tiêu chí so sánh.

## 9. Xử lý song song: lambda độc lập và không can thiệp nguồn

Các quy tắc cho **behavioral parameters** của Stream API vẫn áp dụng:

- **Không trạng thái (stateless):** mapper xử lý một phần tử không phụ thuộc vào trạng thái mutable do việc xử lý phần tử khác thay đổi.
- **Không can thiệp (non-interfering):** mapper không sửa nguồn dữ liệu mà Stream đang duyệt.
- **Không dựa vào side effect:** không dùng việc tăng biến đếm, ghi vào danh sách ngoài hay gọi I/O trong mapper như một phần bắt buộc của kết quả terminal.

Ví dụ **không an toàn** trên parallel stream:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

int[] values = IntStream.range(0, 100_000)
    .parallel()
    .mapMulti((n, out) -> {
        shared.add(n); // Race condition trên ArrayList.
        out.accept(n * 2);
    })
    .toArray();
~~~

`shared` được thay đổi từ nhiều tác vụ; `ArrayList` không an toàn khi nhiều thread cùng ghi. `mapMulti` không biến mutation bên ngoài thành thao tác đồng bộ. Cách xử lý đúng nếu chỉ cần mảng kết quả:

~~~java
int[] values = IntStream.range(0, 100_000)
    .parallel()
    .mapMulti((n, out) -> out.accept(n * 2))
    .toArray();
~~~

Stream tự quản lý việc thu kết quả. Cần lưu ý phép tính có thể tràn `int` nếu đầu vào lớn, mặc dù ví dụ này vẫn nằm trong miền an toàn.

Trong pipeline song song, `forEach` không bảo đảm thứ tự thực thi action ngay cả khi nguồn có encounter order. Nếu kết quả bắt buộc theo thứ tự nguồn, ưu tiên thu thập qua `toArray()` hoặc dùng `forEachOrdered` khi phải thực hiện action theo thứ tự. Việc giữ thứ tự có thể hạn chế hiệu năng, nên cần cân nhắc yêu cầu nghiệp vụ.

### Kết hợp, hiệu năng và tổng hợp

Với phép tổng, `IntStream.sum()` trả về `int` và có thể tràn. Nếu tổng cần vượt miền `int`, chuyển sang `long`:

~~~java
import java.util.stream.IntStream;

long safeRangeSum = IntStream.rangeClosed(1, 100_000)
    .mapMulti((n, out) -> out.accept(n))
    .asLongStream()
    .sum();

System.out.println(safeRangeSum); // 5_000_050_000
~~~

Với `DoubleStream.sum()`, các sai khác làm tròn do số thực và cách kết hợp trong parallel stream cần được chấp nhận hoặc xử lý theo mục tiêu độ chính xác. Không có guarantee rằng song song sẽ nhanh hơn: overhead chia việc, trộn kết quả, lượng fan-out hoặc dữ liệu nhỏ có thể làm hiệu năng kém hơn.

## 10. Ví dụ hoàn chỉnh: kiểm tra số lượng đơn vị qua `IntStream.mapMulti`

Đây là một bài toán mô phỏng: hệ thống nhận số lượt thử cho mỗi thiết bị trong ngày; số âm và số vượt hạn mức được xem là lỗi đầu vào. Mỗi thiết bị hợp lệ tạo một dãy số thứ tự lượt thử. Kết quả được phân tích bằng `summaryStatistics()`.

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

public class PrimitiveFanOut {
    private static final int MAX_ATTEMPTS = 100;

    static IntStream expandAttempts(IntStream counts) {
        return counts.mapMulti((count, out) -> {
            if (count < 0 || count > MAX_ATTEMPTS) {
                throw new IllegalArgumentException(
                    "Lượt thử không hợp lệ: " + count
                );
            }
            for (int attempt = 1; attempt <= count; attempt++) {
                out.accept(attempt);
            }
        });
    }

    public static void main(String[] args) {
        int[] attempts = expandAttempts(
            IntStream.of(0, 3, 2)
        ).toArray();

        System.out.println(Arrays.toString(attempts));
        // [1, 2, 3, 1, 2]

        IntSummaryStatistics stats = expandAttempts(
            IntStream.of(0, 3, 2)
        ).summaryStatistics();

        System.out.println(stats.getCount()); // 5
        System.out.println(stats.getSum());   // 9
        System.out.println(stats.getMin());   // 1
        System.out.println(stats.getMax());   // 3
        System.out.println(stats.getAverage()); // 1.8
    }
}
~~~

Điểm cần chú ý:

1. Hàm `expandAttempts` nhận **`IntStream`** nên sử dụng `IntStream.mapMulti`.
2. `count = 0` phát 0 số; `count = 3` phát `1, 2, 3`; `count = 2` phát `1, 2`.
3. Hai lần gọi `expandAttempts` nhận **hai Stream mới**; không tái sử dụng Stream đã chạy terminal.
4. Mapper độc lập theo từng `count` và không sửa dữ liệu bên ngoài.
5. `summaryStatistics()` tạo một kết quả tổng hợp không cần boxing từng `int`.
6. Giới hạn `MAX_ATTEMPTS` giúp kiểm soát số phần tử tối đa phát trên mỗi đầu vào.

Trong một hệ thống thật, nếu chỉ cần **tổng số lượt thử**, hãy dùng `IntStream.sum()` hoặc `mapToLong(...).sum()` sau khi kiểm tra đầu vào; không cần nở dãy lượt thử. Fan-out chỉ phù hợp khi logic phía sau thật sự phải xử lý từng lượt.

## 11. Những lỗi thường gặp

### Lỗi 1: quên `out.accept`

~~~java
int[] result = IntStream.of(1, 2, 3)
    .mapMulti((n, out) -> {
        int doubled = n * 2; // Có tính toán nhưng không phát giá trị.
    })
    .toArray();

// result là mảng rỗng.
~~~

Đoạn trên vẫn biên dịch nhưng kết quả rỗng vì mapper không gọi `accept`. Cách viết **đáp ứng mục tiêu**:

~~~java
int[] result = IntStream.of(1, 2, 3)
    .mapMulti((n, out) -> out.accept(n * 2))
    .toArray(); // [2, 4, 6]
~~~

Lambda `mapMulti` phải gọi `accept` để phát phần tử. Nếu mapper không gọi `accept` thì đầu ra của phần tử hiện tại rỗng.

### Lỗi 2: nhầm `mapMulti` với `flatMap`

~~~java
// Sai mục đích: mapMulti không nhận lambda trả IntStream.
// .mapMulti(n -> IntStream.of(n, -n))

// Đúng với mapMulti:
int[] values = IntStream.of(1, 2)
    .mapMulti((n, out) -> {
        out.accept(n);
        out.accept(-n);
    })
    .toArray(); // [1, -1, 2, -2]

// Đúng với flatMap:
int[] sameValues = IntStream.of(1, 2)
    .flatMap(n -> IntStream.of(n, -n))
    .toArray();
~~~

### Lỗi 3: mở rộng dữ liệu không giới hạn

~~~java
// Cần kiểm tra count trước khi phát số phần tử tương ứng:
int count = 3;

int[] values = IntStream.of(count)
    .mapMulti((n, out) -> {
        if (n < 0 || n > 10_000) {
            throw new IllegalArgumentException("Vượt hạn mức");
        }
        for (int i = 0; i < n; i++) {
            out.accept(i);
        }
    })
    .toArray();
~~~

Một lượng đầu ra lớn có thể tốn thời gian và bộ nhớ dù phép biến đổi chỉ dùng primitive. Đừng dùng một vòng lặp vô hạn trong mapper rồi trông chờ terminal short-circuit bảo đảm dừng nó.

### Lỗi 4: coi `mapMulti` là phép chuyển đổi từ object sang primitive

~~~java
// Với Stream<String>, phải gọi mapMultiToInt:
int[] parsed = List.of("1", "2").stream()
    .mapMultiToInt((text, out) ->
        out.accept(Integer.parseInt(text))
    )
    .toArray(); // [1, 2]
~~~

`IntStream.mapMulti` chỉ có trên `IntStream`; `Stream<String>` không có phương thức mang cùng chữ ký này. Với nguồn là object, dùng đúng biến thể `mapMultiToInt/Long/Double`.

### Lỗi 5: tưởng `mapMulti` tự động cải thiện hiệu năng

So với `flatMap`, `mapMulti` có thể dễ viết và có thể giảm overhead khi phát ít giá trị, nhưng vẫn phải tuân theo hợp đồng Stream, vẫn có thể có bộ đệm nội bộ và không bảo đảm tốc độ hoặc bộ nhớ tốt hơn trong mọi ứng dụng. Hãy dùng profiler/benchmark nếu đó là tiêu chí chọn lựa.

### Lỗi 6: nhầm miền giá trị và độ chính xác

- `IntStream.sum()` có thể tràn `int`; cân nhắc `asLongStream().sum()` nếu tổng lớn.
- `LongStream.sum()` cũng có thể tràn `long`; kiểm tra quy mô dữ liệu và chính sách số học.
- `DoubleStream.sum()` chịu ảnh hưởng làm tròn; có thể có `NaN` hoặc vô hạn nếu giá trị đầu vào không được lọc.
- Primitive stream không biểu diễn `null` cho từng phần tử; nếu nguồn có dữ liệu thiếu, cần quy tắc xử lý tại bước chuyển từ object/Optional sang primitive.

## 12. Bảng chọn nhanh và câu hỏi tự kiểm tra

| Yêu cầu | Operation nên cân nhắc | Lý do |
| --- | --- | --- |
| `int` thành 0–n `int` | `IntStream.mapMulti` | Giữ nguyên primitive stream. |
| `long` thành 0–n `long` | `LongStream.mapMulti` | Phát bằng `LongConsumer`. |
| `double` thành 0–n `double` | `DoubleStream.mapMulti` | Phát bằng `DoubleConsumer`. |
| `Stream<Order>` thành 0–n `long` | `mapMultiToLong` | Chuyển nguồn object sang primitive stream. |
| `Stream<String>` thành 0–n `int` | `mapMultiToInt` | Parse và phát trực tiếp `int`. |
| Một `int` thành đúng một `int` | `map` | Diễn đạt biến đổi 1–1. |
| Chỉ giữ số thỏa điều kiện | `filter` | Không cần tạo thêm giá trị. |
| Mapper vốn đã trả `IntStream` | `flatMap` | Phù hợp để làm phẳng các Stream con. |
| Chỉ cần tổng số lượng | `sum`/`mapToLong(...).sum()` | Tránh fan-out không cần thiết. |

Tự kiểm tra:

1. **`IntStream.mapMulti` trả về kiểu gì?** `IntStream`; mapper nhận số `int` và một `IntConsumer`.
2. **Một phần tử không gọi `out.accept` sẽ tạo ra bao nhiêu giá trị?** Không có giá trị nào.
3. **Một phần tử gọi `out.accept` hai lần tạo bao nhiêu phần tử đầu ra?** Hai phần tử, theo thứ tự hai lời gọi trong mapper.
4. **Khi đầu vào là `Stream<String>` và muốn kết quả `IntStream`, dùng gì?** `mapMultiToInt`.
5. **Có cần `boxed()` trước khi gọi `IntStream.mapMulti` không?** Không; một lợi ích là giữ pipeline ở dạng nguyên thủy.
6. **`limit(3)` sau `mapMulti` giới hạn ba input hay output?** Giới hạn số phần tử **đầu ra**.
7. **`parallel().mapMulti(...)` có cho phép cộng biến mutable dùng chung không?** Không; mapper vẫn cần không trạng thái và không can thiệp nguồn.
8. **Nếu chỉ cần tổng của các số lượng, có nên phát `quantity` lần mỗi giá trị không?** Thường không; tính tổng trực tiếp phù hợp hơn.
9. **`mapMulti` có luôn nhanh hơn `flatMap` không?** Không; API có thể sử dụng bộ đệm và hiệu năng phụ thuộc dữ liệu, triển khai và tải thực tế.
10. **Có nên xem `DoubleStream` là lựa chọn mặc định để tính tiền chính xác tuyệt đối không?** Không; phải chọn kiểu số phù hợp chính sách làm tròn và độ chính xác.

**Ghi nhớ:** `mapMulti` trên **`IntStream`, `LongStream` và `DoubleStream`** là phép biến đổi **một giá trị primitive thành 0–n giá trị primitive cùng loại**, phát qua `IntConsumer`, `LongConsumer` hoặc `DoubleConsumer`. Với đầu vào là object, dùng `Stream<T>.mapMultiToInt/Long/Double`. Giữ mapper độc lập, phát số lượng hữu hạn, dùng terminal operation phù hợp và đánh giá lợi ích theo đúng nhu cầu của pipeline.
