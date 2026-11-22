# Sinh dãy phục vụ mô phỏng và kiểm thử có thể tái lập

Trong **Java Stream API**, nguồn dữ liệu không nhất thiết là một `List`, mảng hoặc tệp có sẵn. Ta có thể **sinh dãy theo quy tắc** bằng `IntStream.range`, `Stream.iterate`, `Stream.generate` hay các phương thức sinh số của `Random`. Khả năng này hữu ích khi cần tạo dữ liệu mô phỏng, thử nhiều kịch bản, kiểm tra thuật toán hoặc tái hiện một lỗi.

Điều kiện quan trọng là **có thể tái lập** (*reproducible*): với cùng cấu hình đầu vào, ta chủ động tạo lại cùng chuỗi dữ liệu và cùng kết quả cần kiểm chứng. Việc dùng stream vô hạn, số giả ngẫu nhiên, phép toán lazy hoặc xử lý song song đều ảnh hưởng đến khả năng này.

## 1. “Có thể tái lập” nghĩa là gì?

Cần phân biệt ba tình huống:

| Loại dãy | Ví dụ | Điều kiện để tái lập |
| --- | --- | --- |
| **Xác định hoàn toàn** | `0, 2, 4, 6, ...`; mô hình cập nhật trạng thái bằng một công thức | Giữ nguyên giá trị bắt đầu, quy tắc biến đổi, số bước và thứ tự xử lý. |
| **Giả ngẫu nhiên có seed** | Nhiệt độ, tỷ lệ lỗi, tọa độ mẫu trong một mô phỏng | Giữ nguyên seed, thuật toán sinh số, số lượng và thứ tự các lần lấy số. |
| **Phụ thuộc trạng thái bên ngoài** | `Math.random()`, thời gian hiện tại, I/O, bộ đếm dùng chung | Phải kiểm soát hoặc thay thế các phụ thuộc; nếu không, kết quả thường khó tái lập. |

**Seed** là trạng thái khởi đầu của bộ sinh số giả ngẫu nhiên. Nó giúp tái tạo một chuỗi, **không** làm chuỗi trở thành ngẫu nhiên thật và **không** bảo đảm những phép toán phụ thuộc lịch chạy của nhiều luồng sẽ cho kết quả như nhau.

Trong bài này, “tái lập” được xét theo từng mức: cùng dữ liệu sinh ra, cùng kết quả thống kê và cùng hành vi kiểm thử. Một vài phép tính dấu phẩy động có thể chênh lệch nhỏ khi thay đổi thứ tự gộp kết quả hoặc môi trường thực thi.

## 2. Chọn nguồn sinh dãy thích hợp

Các API sau tạo stream từ một quy tắc sinh phần tử, không cần cấp phát trước một collection chứa toàn bộ dữ liệu:

| API | Kiểu kết quả | Hữu hạn / không giới hạn | Trường hợp dùng |
| --- | --- | --- | --- |
| `IntStream.range(start, end)` | `IntStream` | Hữu hạn, không gồm `end` | Chỉ số lượt chạy, vòng lặp mô phỏng có số bước xác định. |
| `IntStream.rangeClosed(start, end)` | `IntStream` | Hữu hạn, gồm `end` | Các mốc nguyên trong đoạn đóng. |
| `Stream.iterate(seed, next)` | `Stream<T>` | Có khả năng vô hạn | Trạng thái sau phụ thuộc trạng thái trước. |
| `IntStream.iterate(seed, next)` | `IntStream` | Có khả năng vô hạn | Dãy số nguyên theo công thức truy hồi. |
| `Stream.iterate(seed, hasNext, next)` | `Stream<T>` | Dừng theo điều kiện, Java 9+ | Mô hình có điều kiện kết thúc rõ ràng. |
| `Stream.generate(supplier)` | `Stream<T>` | Có khả năng vô hạn, unordered | Lấy mẫu được sinh theo nhu cầu. |
| `new Random(seed).ints(n, min, max)` | `IntStream` | Hữu hạn, đúng `n` phần tử | Dữ liệu nguyên giả ngẫu nhiên theo seed. |
| `new Random(seed).doubles(n, min, max)` | `DoubleStream` | Hữu hạn, đúng `n` phần tử | Mô phỏng đại lượng liên tục trong một khoảng. |

`Stream.iterate` là nguồn có thứ tự gặp phần tử (*encounter order*); `Stream.generate` tạo stream không có thứ tự được bảo đảm. Các phép toán trung gian như `map` và `filter` là **lazy**; quá trình sinh phần tử thường bắt đầu khi có phép toán kết thúc như `toArray`, `count`, `collect` hoặc `findFirst`.

### Dãy số xác định bằng chỉ số

```java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] values = IntStream.range(0, 6)
    .map(i -> 3 + 4 * i)
    .toArray();

System.out.println(Arrays.toString(values));
// [3, 7, 11, 15, 19, 23]
```

Phần tử tại vị trí `i` được tính trực tiếp từ `i`, không cần nhớ phần tử trước. Đây là dạng thuận lợi khi cần kiểm thử độc lập từng lượt mô phỏng, kể cả khi phân chia công việc song song.

### Dãy xác định bằng quy tắc truy hồi

```java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] values = IntStream.iterate(3, value -> value + 4)
    .limit(6)
    .toArray();

System.out.println(Arrays.toString(values));
// [3, 7, 11, 15, 19, 23]
```

Kết quả giống ví dụ `range`, nhưng ý nghĩa khác: `iterate` tính giá trị sau từ giá trị trước. Khi quy luật thực sự có trạng thái tuần tự, đây là biểu diễn tự nhiên hơn.

Với Java 9 trở lên, có thể gắn điều kiện dừng ngay vào nguồn:

```java
import java.util.stream.IntStream;

IntStream.iterate(3, value -> value < 25, value -> value + 4)
    .forEachOrdered(System.out::println);
// In lần lượt: 3, 7, 11, 15, 19, 23
```

Điều kiện `hasNext` được xét trên phần tử ứng viên **trước khi** đưa phần tử đó vào stream; giá trị đầu tiên không thỏa điều kiện sẽ không xuất hiện. Với quy luật có thể tràn `int` hoặc `long`, cần thiết kế giới hạn phù hợp, vì phép cộng nguyên của Java có thể tràn mà không ném ngoại lệ.

## 3. Mô phỏng quá trình theo thời gian bằng `iterate`

Xét một vật thể có nhiệt độ ban đầu là 100°C, ở môi trường 20°C. Sau mỗi bước thời gian, nhiệt độ tiến thêm 25% khoảng cách tới nhiệt độ môi trường:

\[
T_{k+1} = T_k + 0.25(20-T_k)
\]

Ta có thể lưu quy tắc này trong dãy `DoubleStream`:

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;

double[] temperatures = DoubleStream.iterate(
        100.0,
        current -> current + 0.25 * (20.0 - current)
    )
    .limit(5)
    .toArray();

System.out.println(Arrays.toString(temperatures));
// [100.0, 80.0, 65.0, 53.75, 45.3125]
```

Mỗi phần tử biểu diễn **trạng thái ở một mốc**, tính cả trạng thái ban đầu. Việc gọi lại cùng pipeline với cùng số bước sẽ cho cùng dãy, khi công thức và môi trường tính toán không thay đổi. Dãy là lazy cho đến khi gọi `toArray()`, và `limit(5)` xác định rõ có bao nhiêu trạng thái được lấy.

Một số lưu ý khi áp dụng thực tế:

- Quy tắc cập nhật nên chỉ phụ thuộc vào trạng thái hiện tại và các tham số mô hình; tránh đọc đồng hồ hệ thống hoặc thay đổi biến toàn cục trong lambda.
- `iterate` có phụ thuộc dữ liệu giữa các bước. Thêm `parallel()` không loại bỏ phụ thuộc này và thường không mang lại lợi ích như phân chia các lượt chạy độc lập.
- Với nhiều biến trạng thái như vị trí, vận tốc và năng lượng, có thể dùng một kiểu dữ liệu bất biến làm phần tử của `Stream.iterate`, để mỗi bước trả về **trạng thái mới**.
- `DoubleStream` giúp tránh boxing của `Double` khi chỉ cần thao tác trên số thực.

## 4. Tạo dữ liệu giả ngẫu nhiên có seed cố định

Trong mô phỏng, ta thường cần dữ liệu có vẻ ngẫu nhiên nhưng có thể tạo lại để so sánh thuật toán hoặc tái hiện lỗi. `java.util.Random` cho phép cung cấp seed rõ ràng:

```java
import java.util.Arrays;
import java.util.Random;

long seed = 20261118L;

int[] run1 = new Random(seed)
    .ints(8, 0, 100)
    .toArray();

int[] run2 = new Random(seed)
    .ints(8, 0, 100)
    .toArray();

System.out.println(Arrays.equals(run1, run2)); // true
System.out.println(Arrays.toString(run1));      // Hai lần tạo lại đều giống nhau
```

`ints(8, 0, 100)` yêu cầu **8** số trong khoảng `[0, 100)`: gồm 0 và không gồm 100. `Random` trong Java có thuật toán xác định được đặc tả; với cùng seed và **cùng chuỗi lời gọi phương thức** trong ngữ cảnh tuần tự, nó sinh cùng chuỗi kết quả.

Điều này không có nghĩa mọi cách dùng `Random` đều tái lập. Nếu dùng chung một `Random` rồi gọi `nextInt`, `nextDouble` từ các nơi khác nhau, thứ tự gọi thay đổi sẽ khiến chuỗi quan sát được thay đổi. Để mỗi ca kiểm thử độc lập, nên tạo bộ sinh riêng từ seed được lưu kèm ca kiểm thử.

### Sinh mẫu rồi tính thống kê

```java
import java.util.Random;

long seed = 77L;
int trials = 10_000;
double failureProbability = 0.02;

long failures = new Random(seed)
    .doubles(trials, 0.0, 1.0)
    .filter(value -> value < failureProbability)
    .count();

System.out.println("Số lần lỗi: " + failures);
```

Mỗi mẫu `value` được đối chiếu với ngưỡng 2%. Khi chạy lại cùng cấu hình, số lần lỗi được tái tạo. **Không** thể suy ra rằng cứ 10.000 lượt là có đúng 200 lỗi: 2% là xác suất mô hình, không phải chỉ tiêu chính xác cho một lần lấy mẫu.

Nếu cần sinh mẫu theo `Supplier`, có thể dùng:

```java
import java.util.Random;
import java.util.stream.Stream;

Random random = new Random(77L);

double[] values = Stream.<Double>generate(random::nextDouble)
    .limit(5)
    .mapToDouble(Double::doubleValue)
    .toArray();
```

Supplier `random::nextDouble` đọc và thay đổi trạng thái của một generator. Cách dùng này chỉ dễ tái lập khi **duyệt tuần tự**, tạo generator mới cùng seed trước mỗi lần chạy và giữ nguyên chuỗi yêu cầu lấy mẫu. Đừng chia sẻ generator có trạng thái giữa các tác vụ rồi dựa vào thứ tự gọi hàm để gán kết quả cho từng lượt.

### Những API không phù hợp làm nguồn tái lập mặc định

`Math.random()` không nhận seed làm đối số, còn `ThreadLocalRandom.current()` được thiết kế cho sử dụng giữa nhiều luồng và không cung cấp cách đặt seed trực tiếp như `new Random(seed)`. Vì vậy, chúng không phải lựa chọn thuận tiện khi cần tái tạo đúng một ca kiểm thử.

`SplittableRandom` có thể hữu ích cho tính toán song song vì hỗ trợ tách generator qua `split()`, nhưng tính tái lập vẫn cần chiến lược phân chia và gắn seed ổn định; việc chia theo lịch thực thi của luồng có thể làm các lượt chạy nhận mẫu khác nhau. Ngoài ra, không nên dùng `Random` hoặc `SplittableRandom` để tạo khóa bí mật hoặc token bảo mật; bài toán mật mã cần API `SecureRandom` và yêu cầu kiểm thử riêng.

## 5. Phân biệt ba mức tái lập khi chạy song song

Một nguồn có seed cố định **chưa đủ** để bảo đảm kết quả tái lập khi áp dụng `parallel()`. Hãy tách ba yêu cầu:

1. **Dữ liệu của từng lượt mô phỏng không đổi:** lượt `i` luôn nhận cùng đầu vào, bất kể thread thực thi.
2. **Kết quả tổng hợp không đổi:** các lượt độc lập được gộp bằng phép toán phù hợp với parallel reduction.
3. **Thứ tự hiệu ứng phụ không đổi:** in log, ghi tệp hoặc cập nhật biến dùng chung theo một thứ tự cố định.

Hai yêu cầu đầu có thể đạt được nếu ánh xạ mỗi lượt sang dữ liệu xác định và gộp kết quả đúng. Yêu cầu thứ ba khó bảo đảm bằng `parallel().forEach(...)`; thời điểm chạy mỗi lambda do bộ lập lịch quyết định.

### Ví dụ: mô phỏng Monte Carlo có thể chạy tuần tự hoặc song song

Ta ước lượng số π bằng cách sinh `n` điểm trong hình vuông đơn vị, đếm số điểm nằm trong một phần tư hình tròn bán kính 1. Để **lượt chạy `i` luôn có cùng điểm**, mỗi lượt nhận seed riêng được suy ra từ `baseSeed` và chỉ số `i`:

```java
import java.util.Random;
import java.util.stream.IntStream;

public class ReproducibleMonteCarlo {
    // Trộn bit theo một công thức xác định để tạo seed cho từng lượt.
    static long mix64(long z) {
        z = (z ^ (z >>> 30)) * 0xbf58476d1ce4e5b9L;
        z = (z ^ (z >>> 27)) * 0x94d049bb133111ebL;
        return z ^ (z >>> 31);
    }

    static long countInside(int trials, long baseSeed, boolean parallel) {
        IntStream indexes = IntStream.range(0, trials);
        if (parallel) {
            indexes = indexes.parallel();
        }

        return indexes.filter(index -> {
            Random sampleRandom = new Random(mix64(baseSeed + index));
            double x = sampleRandom.nextDouble();
            double y = sampleRandom.nextDouble();
            return x * x + y * y <= 1.0;
        }).count();
    }

    public static void main(String[] args) {
        int trials = 100_000;
        long seed = 20261118L;

        long sequential = countInside(trials, seed, false);
        long parallel = countInside(trials, seed, true);

        System.out.println(sequential == parallel); // true
        double pi = 4.0 * sequential / trials;
        System.out.println("Ước lượng pi = " + pi);
    }
}
```

Ở đây, mỗi predicate chỉ sử dụng `index`, `baseSeed` và generator **cục bộ**. Không có đối tượng `Random` dùng chung để các luồng cùng tiêu thụ. `count()` gộp số nguyên một cách xác định, nên số điểm nằm trong hình tròn giống nhau giữa hai chế độ trên cùng thuật toán và dữ liệu. Hàm `mix64` là phép trộn bit xác định để phân tán seed; nó **không chứng minh** tính độc lập thống kê của các mẫu và không có mục đích mật mã.

Giải pháp này cũng có chi phí: tạo một `Random` cho **mỗi** lượt mô phỏng. Với bài toán cần hiệu năng rất cao, có thể thiết kế nguồn sinh số theo chỉ số hoặc chia công việc thành các khối có seed được gán trước, nhưng phải kiểm chứng lại tính tái lập và chất lượng thống kê.

**Không nên** thay `sampleRandom` bằng một `Random` dùng chung trong đoạn mã trên. Dù bộ sinh được đồng bộ để tránh hỏng trạng thái, việc lượt `i` nhận số nào còn phụ thuộc thứ tự các thread gọi generator. Cũng không nên trông đợi `parallel().forEach(System.out::println)` in cùng thứ tự giữa các lần chạy; nếu cần giữ encounter order để hiển thị, xem xét `forEachOrdered`, chấp nhận chi phí phối hợp.

### Lưu ý về phép toán trên số thực

`count()` trong ví dụ cho kết quả nguyên chính xác. Nhưng phép cộng `double` không có tính kết hợp toán học tuyệt đối do làm tròn nhị phân. Vì thế, `parallel().mapToDouble(...).sum()` hoặc `reduce` trên số thực có thể cho sai khác rất nhỏ so với tuần tự khi thứ tự gộp thay đổi. Khi kiểm thử kết quả số thực, xác định một ngưỡng sai số phù hợp thay vì luôn yêu cầu hai bit pattern bằng nhau.

## 6. Giới hạn dãy để bảo đảm chương trình có thể kết thúc

`Stream.iterate(seed, next)` và `Stream.generate(supplier)` có thể tạo nguồn vô hạn. Những terminal operation như `count()`, `collect(...)`, `toArray()` muốn biết **toàn bộ dữ liệu** sẽ không thể kết thúc nếu không có ranh giới hữu hạn.

```java
import java.util.stream.IntStream;

// Dừng sau đúng 100 mẫu.
long count = IntStream.iterate(0, n -> n + 1)
    .limit(100)
    .count();

System.out.println(count); // 100
```

Đối với nguồn xác định độ dài, `IntStream.range(0, 100)` thường rõ nghĩa hơn `iterate(...).limit(100)`. Khi giới hạn theo nội dung dãy, Java 9+ cung cấp `takeWhile` hoặc overload ba tham số của `iterate`. Cần hiểu rõ sự khác nhau giữa `filter` và `takeWhile`:

```java
import java.util.stream.IntStream;

int[] prefix = IntStream.of(2, 4, 7, 8, 10)
    .takeWhile(n -> n % 2 == 0)
    .toArray();
// [2, 4] — dừng lấy tiền tố ở 7.

int[] allEven = IntStream.of(2, 4, 7, 8, 10)
    .filter(n -> n % 2 == 0)
    .toArray();
// [2, 4, 8, 10] — xét cả các phần tử sau 7.
```

**Một phép toán có khả năng ngắn mạch không bảo đảm lúc nào cũng kết thúc.** Ví dụ, `Stream.generate(() -> 0).filter(n -> n == 1).findFirst()` sẽ tiếp tục tìm mà không bao giờ gặp phần tử cần thiết. `sorted()` trước `limit()` có thể buộc đọc toàn bộ nguồn để sắp xếp; vì vậy `infiniteStream.sorted().limit(10)` không phải cách sinh 10 giá trị an toàn.

Với mô phỏng dài, chỉ lưu các thống kê cần thiết thay vì `toArray()` toàn bộ mẫu. Một stream hữu hạn nhưng chứa hàng trăm triệu phần tử vẫn có thể gây hết bộ nhớ khi thu gom hết vào collection.

## 7. Thiết kế kiểm thử tái lập, không bị ngẫu nhiên làm “flaky”

Một ca kiểm thử dữ liệu mô phỏng nên lưu được **seed, số bước, tham số mô hình và kỳ vọng**. Có hai kiểu kỳ vọng phổ biến:

- **Kết quả chính xác:** chạy cùng seed và pipeline để xác nhận kết quả được sinh ra giống nhau; phù hợp để tái hiện một lỗi cụ thể.
- **Bất biến của mô hình:** mọi giá trị nằm trong khoảng hợp lệ, số lượt không âm, số lượt thành công không vượt quá tổng số lượt; hữu ích để kiểm tra nhiều seed mà không gắn kỳ vọng vào một chuỗi ngẫu nhiên cụ thể.

Ví dụ kiểm thử độc lập với thư viện test:

```java
import java.util.Arrays;
import java.util.Random;

public class ReproducibleDataTest {
    static int[] samples(long seed) {
        return new Random(seed).ints(100, 0, 50).toArray();
    }

    public static void main(String[] args) {
        long seed = 123456L;
        int[] first = samples(seed);
        int[] second = samples(seed);

        if (!Arrays.equals(first, second)) {
            throw new AssertionError("Cùng seed nhưng dữ liệu khác");
        }
        if (first.length != 100) {
            throw new AssertionError("Sai số lượng mẫu");
        }
        if (Arrays.stream(first).anyMatch(x -> x < 0 || x >= 50)) {
            throw new AssertionError("Có giá trị ngoài [0, 50)");
        }
    }
}
```

Không nên yêu cầu một mẫu ngẫu nhiên nhỏ phải có tỷ lệ lỗi, trung bình hay tần suất **đúng bằng** kỳ vọng xác suất: một kiểm thử như vậy có thể thất bại dù thuật toán hợp lệ. Khi kiểm định tính chất thống kê, cần chọn cỡ mẫu, khoảng chấp nhận và mức tin cậy phù hợp; khi kiểm thử hồi quy, có thể dùng một tập seed cố định.

Nếu phát hiện lỗi ở seed cụ thể, hãy ghi lại:

```text
baseSeed=20261118
trials=100000
generator=java.util.Random
mode=sequential
modelVersion=1
```

Đây là **ví dụ cấu hình**, không phải đầu ra của chương trình. Với những mô hình phức tạp hơn, cần ghi cả dữ liệu đầu vào, thứ tự xử lý, tham số và phiên bản runtime hoặc thư viện có liên quan.

## 8. Các lỗi thường gặp và cách phòng tránh

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Chạy lại một test nhưng dữ liệu khác | Dùng `new Random()` không truyền seed, `Math.random()`, đồng hồ hoặc trạng thái ngoài | Cố định seed và đầu vào; tạo generator mới cho mỗi ca. |
| Cùng seed nhưng kết quả theo từng chỉ số khác khi chuyển sang `parallel()` | Nhiều lượt lấy mẫu từ một generator dùng chung theo thứ tự không cố định | Sinh dữ liệu độc lập theo chỉ số hoặc gán seed trước cho từng khối. |
| Stream chạy mãi không ra kết quả | Dãy vô hạn đi với `count`, `collect` hoặc điều kiện ngắn mạch không bao giờ đúng | Dùng nguồn hữu hạn, `limit` hoặc điều kiện dừng thật sự đạt được. |
| Test kiểm tra tỷ lệ ngẫu nhiên lúc đúng lúc sai | Kiểm tra xác suất bằng đẳng thức chính xác hoặc ngưỡng quá chặt | Kiểm tra bất biến; dùng thống kê và khoảng sai số hợp lý. |
| Dữ liệu hoặc tổng thay đổi do thứ tự xử lý | Hiệu ứng phụ trong `map`, `peek`, `forEach`; phép gộp không kết hợp | Dùng lambda thuần hàm và reduction đúng hợp đồng. |
| `limit` trả tập mẫu khác mong đợi | Thứ tự gặp phần tử không được bảo đảm hoặc dùng `unordered()` | Gắn chỉ số mẫu rõ ràng, giữ encounter order khi nghiệp vụ cần. |
| Vòng lặp `iterate` bị lặp giá trị bất ngờ | Tràn số nguyên, bước tiến bằng 0 hoặc quy tắc không đạt điểm dừng | Giới hạn số bước và kiểm tra điều kiện kết thúc, khoảng giá trị. |
| Hết bộ nhớ khi lấy mẫu | Thu toàn bộ stream thành mảng hoặc danh sách rất lớn | Xử lý theo luồng và tính thống kê bằng terminal operation thích hợp. |

### Bộ câu hỏi tự rà soát trước khi chạy mô phỏng

1. Mỗi lượt chạy được xác định bằng chỉ số hay bằng trạng thái trước đó?
2. Seed và thuật toán sinh số có được truyền rõ ràng, có thể lưu lại không?
3. Stream có giới hạn số phần tử hoặc điều kiện dừng thật sự đạt được không?
4. Các lambda có phụ thuộc đồng hồ, I/O, biến chia sẻ hoặc thứ tự lập lịch thread không?
5. Có cần giữ thứ tự kết quả, và phép tổng hợp có an toàn khi song song không?
6. Phần nào cần so sánh bằng giá trị chính xác, phần nào phải chấp nhận sai số số thực hoặc độ dao động thống kê?
7. Có thể tái tạo một ca lỗi chỉ từ seed, tham số, số bước và phiên bản mô hình không?

## 9. Bài thực hành nhỏ

**Bài 1 — Dãy xác định.** Sinh 20 số nguyên dạng `5 + 3 * i` bằng `IntStream.range`, sau đó tạo lại bằng `IntStream.iterate` kết hợp `limit`. So sánh hai mảng bằng `Arrays.equals`. Giải thích vì sao công thức theo chỉ số thuận tiện hơn nếu mỗi phần tử được tính độc lập.

**Bài 2 — Tái hiện lỗi.** Viết `samples(seed)` sinh 1.000 số nguyên trong khoảng `[0, 100)`. Chạy với seed `42L` hai lần và xác nhận hai mảng bằng nhau; thay seed rồi quan sát kết quả. Đừng viết test với giả định rằng hai seed bất kỳ **bắt buộc** tạo hai mảng khác nhau, vì API không cung cấp bảo đảm đó.

**Bài 3 — Mô phỏng độc lập.** Từ ví dụ `ReproducibleMonteCarlo`, thử `10_000` và `100_000` lượt. Kiểm tra `countInside(n, seed, false) == countInside(n, seed, true)` cho cùng `n` và seed, đồng thời xác nhận số điểm đếm được luôn nằm trong `[0, n]`. Quan sát rằng ước lượng π có thể khác khi đổi `n` hay seed.

**Điểm cần nhớ:** Java Stream API giúp mô tả dãy mô phỏng bằng các pipeline lazy, từ nguồn hữu hạn đến nguồn vô hạn. Để kiểm thử có thể tái lập, hãy làm rõ nguồn sinh, seed, số bước, tính độc lập của từng mẫu, điều kiện dừng và hợp đồng của phép gộp. Những điều đó quyết định khả năng tái hiện kết quả, hơn là việc chỉ sử dụng một lời gọi `parallel()` hay một seed cố định.
