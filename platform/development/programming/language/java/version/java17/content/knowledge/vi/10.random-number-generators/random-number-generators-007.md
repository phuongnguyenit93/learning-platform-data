# Luồng `ints`, `longs`, `doubles` và giới hạn số phần tử trong Java 17

## 1. Mục tiêu của bài học

Java cung cấp các API để sinh một dãy giá trị giả ngẫu nhiên dưới dạng **Stream**. Với `Random` và các bộ sinh số thuộc API `RandomGenerator`, ta có thể tạo:

- `IntStream` từ các giá trị `int` bằng `ints(...)`.
- `LongStream` từ các giá trị `long` bằng `longs(...)`.
- `DoubleStream` từ các giá trị `double` bằng `doubles(...)`.

Mỗi nhóm API có overload tạo luồng **không giới hạn số phần tử được yêu cầu** và overload tạo luồng có **kích thước xác định**. Ngoài ra, có overload giới hạn khoảng giá trị để sinh số trong một miền cụ thể.

Ví dụ:

```java
Random random = new Random();

int[] fiveNumbers = random.ints(5, 1, 7).toArray();
```

Đoạn mã tạo một luồng gồm đúng 5 giá trị `int`, mỗi giá trị nằm trong khoảng từ 1 đến 6. Cận dưới `1` được tính, cận trên `7` không được tính.

Sau bài học, người học cần biết:

1. Phân biệt `ints()`, `longs()`, `doubles()` với các overload có `streamSize`.
2. Chọn đúng overload có giới hạn miền giá trị `origin` và `bound`.
3. Hiểu luồng không giới hạn, luồng hữu hạn và cách dùng `limit()`.
4. Biết vị trí của `limit()` trong pipeline ảnh hưởng đến số phần tử đầu ra như thế nào.
5. Dùng terminal operation để tiêu thụ stream, tránh thao tác không kết thúc trên luồng vô hạn.
6. Chọn bộ sinh số phù hợp trong Java 17 và hiểu giới hạn của số giả ngẫu nhiên.

## 2. API sinh các luồng số trong Java 17

### 2.1. `RandomGenerator` và `Random`

Java 17 có API chung `java.util.random.RandomGenerator`, định nghĩa hợp đồng cho các bộ sinh số giả ngẫu nhiên. `java.util.Random`, `SplittableRandom` và `ThreadLocalRandom` là những lớp có thể sử dụng qua API này.

Ví dụ khai báo:

```java
import java.util.Random;
import java.util.random.RandomGenerator;

RandomGenerator generator = new Random(12345L);
```

Biến `generator` có kiểu interface `RandomGenerator`, nên có thể gọi các phương thức sinh số và stream mà interface công bố. `new Random(12345L)` chọn một seed cố định để có thể lặp lại chuỗi kết quả khi chạy lại cùng cách sử dụng generator.

Nếu chỉ học API stream, có thể dùng trực tiếp:

```java
Random random = new Random();
IntStream integers = random.ints();
LongStream longValues = random.longs();
DoubleStream decimals = random.doubles();
```

Các kiểu stream chuyên biệt có lợi thế:

| API | Kiểu trả về | Kiểu phần tử |
|---|---|---|
| `ints(...)` | `IntStream` | `int` |
| `longs(...)` | `LongStream` | `long` |
| `doubles(...)` | `DoubleStream` | `double` |

Chúng tránh boxing từng phần tử thành `Integer`, `Long`, `Double` trong các thao tác số thông thường, đồng thời cung cấp các phép toán chuyên biệt như `sum()`, `average()`, `min()`, `max()` và `summaryStatistics()`.

### 2.2. Không có stream `floats()` trong nhóm API này

API stream của `RandomGenerator` cung cấp `ints`, `longs`, `doubles`; không có phương thức `floats()` tương ứng. Nếu một API yêu cầu `float`, cần chuyển đổi có chủ đích, đồng thời cân nhắc việc giảm độ chính xác:

```java
float sample = (float) random.nextDouble();
```

Không nên đổi sang `float` chỉ vì kiểu này dùng ít bộ nhớ hơn nếu bài toán cần độ chính xác của `double`.

## 3. Các overload tạo luồng

Với mỗi kiểu số, có bốn dạng chính:

| Kiểu | Không giới hạn, toàn miền | Hữu hạn, toàn miền | Không giới hạn, có khoảng | Hữu hạn, có khoảng |
|---|---|---|---|---|
| `int` | `ints()` | `ints(long streamSize)` | `ints(int origin, int bound)` | `ints(long streamSize, int origin, int bound)` |
| `long` | `longs()` | `longs(long streamSize)` | `longs(long origin, long bound)` | `longs(long streamSize, long origin, long bound)` |
| `double` | `doubles()` | `doubles(long streamSize)` | `doubles(double origin, double bound)` | `doubles(long streamSize, double origin, double bound)` |

Các phương thức này trả về stream; chúng **không trả về một số đơn lẻ** và cũng không tự tạo mảng. Việc sinh và xử lý phần tử diễn ra khi pipeline được tiêu thụ bởi terminal operation.

### 3.1. Luồng không giới hạn số phần tử

```java
IntStream allInts = random.ints();
LongStream allLongs = random.longs();
DoubleStream allDoubles = random.doubles();
```

Các stream này có độ dài **effectively unlimited**: API không yêu cầu dừng sau một số lượng phần tử xác định. Không thể tiêu thụ toàn bộ chúng bằng một terminal operation cần đọc hết luồng như `toArray()`, `sum()` hoặc `count()` mà mong chương trình kết thúc bình thường.

Nếu chỉ cần một số phần tử đầu, dùng `limit(n)`:

```java
int[] firstTen = random.ints()
        .limit(10)
        .toArray();
```

Pipeline trên chỉ cần tiêu thụ 10 giá trị rồi dừng. `limit` là một **short-circuiting stateful intermediate operation**: nó giới hạn số phần tử được truyền xuống các bước phía sau.

### 3.2. Luồng hữu hạn với `streamSize`

```java
int[] values = random.ints(5).toArray();
long[] ids = random.longs(3).toArray();
double[] samples = random.doubles(4).toArray();
```

Các overload này tạo stream với số phần tử được chỉ định. Giá trị `streamSize` có kiểu `long` và phải **không âm**:

- `streamSize == 0`: stream rỗng, không có phần tử.
- `streamSize > 0`: stream có đúng số lượng phần tử được yêu cầu.
- `streamSize < 0`: ném `IllegalArgumentException`.

Ví dụ:

```java
System.out.println(random.ints(0).count()); // 0
System.out.println(random.ints(5).count()); // 5
// random.ints(-1); // IllegalArgumentException
```

Kích thước hữu hạn giúp biết giới hạn số phần tử từ đầu. Tuy nhiên, không có nghĩa nên tạo một mảng cực lớn; `toArray()` cần cấp phát bộ nhớ cho toàn bộ kết quả và có thể gây `OutOfMemoryError` hoặc vượt giới hạn kích thước mảng.

## 4. Khoảng giá trị: cận dưới bao gồm, cận trên loại trừ

Các overload có `origin` và `bound` đều sử dụng quy ước khoảng **nửa mở**:

\[
[\text{origin}, \text{bound})
\]

Tức là:

- `origin` được tính vào miền giá trị hợp lệ.
- `bound` không được tính vào miền giá trị hợp lệ.
- Điều kiện hợp lệ: `origin < bound`.

### 4.1. Với `ints(origin, bound)`

```java
int[] dice = random.ints(10, 1, 7).toArray();
```

Mỗi giá trị thuộc `1, 2, 3, 4, 5, 6`. Không thể nhận `0` hoặc `7`. Đây là cách tạo kết quả cho một xúc xắc sáu mặt nếu chỉ cần mô phỏng số mặt xuất hiện.

### 4.2. Với `longs(origin, bound)`

```java
long[] ids = random.longs(8, 1_000_000L, 9_000_000L).toArray();
```

Mỗi ID ngẫu nhiên nằm trong `[1_000_000, 9_000_000)`. Cận trên 9.000.000 không xuất hiện.

### 4.3. Với `doubles(origin, bound)`

```java
double[] ratios = random.doubles(5, 0.0, 1.0).toArray();
```

Mỗi giá trị thuộc `[0.0, 1.0)`. Giá trị có thể là 0.0 nhưng không bằng 1.0 theo cận trên loại trừ. `doubles()` không tham số cũng sinh trong khoảng `[0.0, 1.0)`.

Với `doubles(origin, bound)`, cả `origin` và `bound` phải là số hữu hạn và `origin < bound`; không dùng NaN hoặc infinity làm cận. Các giá trị sinh ra được phân bố trong miền được chỉ định theo quy tắc của API.

### 4.4. Ví dụ ranh giới

| Lời gọi | Miền giá trị | Ghi chú |
|---|---|---|
| `ints(1, 6)` | `1, 2, 3, 4, 5` | 6 bị loại |
| `longs(0L, 1L)` | Chỉ có `0L` | Khoảng chỉ chứa một số nguyên |
| `doubles(0.0, 1.0)` | `0.0 <= x < 1.0` | Không sinh đúng 1.0 |
| `ints(5, 10, 10)` | Không hợp lệ | Hai cận bằng nhau |
| `ints(5, 11, 10)` | Không hợp lệ | Cận dưới lớn hơn cận trên |

Nếu muốn tạo một số nguyên trong đoạn **bao gồm cả hai đầu** `min` và `max`, cần tính cận trên loại trừ một cách an toàn. Ví dụ với các giá trị nhỏ:

```java
int min = 1;
int maxInclusive = 6;
int value = random.nextInt(min, maxInclusive + 1);
```

Với miền sát `Integer.MAX_VALUE`, phép cộng `maxInclusive + 1` có thể tràn số. Hãy xử lý riêng hoặc dùng một cách tạo miền phù hợp; không cộng cận trên một cách mù quáng.

## 5. Giới hạn số phần tử bằng `limit()`

`limit(long maxSize)` là intermediate operation của Stream API. Nó tạo một stream chỉ chứa tối đa `maxSize` phần tử đầu của stream trước đó.

```java
int[] firstFive = random.ints()
        .limit(5)
        .toArray();
```

Trong ví dụ này:

1. `ints()` tạo nguồn có thể tiếp tục sinh số.
2. `limit(5)` chỉ cho tối đa năm phần tử đi tiếp.
3. `toArray()` tiêu thụ pipeline và thu năm giá trị thành mảng.

Giá trị `maxSize` phải không âm. `limit(0)` cho stream rỗng; giá trị âm gây `IllegalArgumentException`.

### 5.1. So sánh overload có kích thước và `limit`

Hai cách sau có thể tạo ra cùng số lượng giá trị:

```java
int[] a = random.ints(5).toArray();
int[] b = random.ints().limit(5).toArray();
```

Tuy nhiên, chúng diễn đạt ý định khác nhau:

- `ints(5)`: ngay tại nguồn đã yêu cầu stream hữu hạn gồm năm phần tử.
- `ints().limit(5)`: nguồn không giới hạn được cắt còn tối đa năm phần tử.

Nếu đã biết số phần tử cần tạo, overload có `streamSize` thường thể hiện ý định rõ hơn. `limit` hữu ích khi nguồn vốn không giới hạn hoặc khi số lượng đầu ra được quyết định bởi pipeline.

### 5.2. Vị trí `limit` trước hay sau `filter` rất quan trọng

Xét hai pipeline:

```java
long atMostFiveMatches = random.ints()
        .limit(5)
        .filter(n -> n % 2 == 0)
        .count();

long fiveMatches = random.ints()
        .filter(n -> n % 2 == 0)
        .limit(5)
        .count();
```

Pipeline thứ nhất:

- Chỉ lấy tối đa 5 số từ nguồn.
- Sau đó lọc số chẵn.
- Kết quả có thể là 0, 1, 2, 3, 4 hoặc 5 phần tử.

Pipeline thứ hai:

- Lọc các số chẵn từ nguồn không giới hạn.
- Lấy tối đa 5 số chẵn đầu tiên.
- Với nguồn giả ngẫu nhiên thông thường và điều kiện có xác suất khớp dương, pipeline thường thu được 5 kết quả; về nguyên tắc một predicate không bao giờ khớp hoặc một luồng không tạo được thêm phần tử phù hợp có thể khiến quá trình không kết thúc.

**Nguyên tắc:** `limit(n)` đếm số phần tử đi qua đúng vị trí nó xuất hiện trong pipeline, không phải lúc nào cũng là số phần tử nguồn được tạo hoặc số phần tử cuối cùng.

### 5.3. Giới hạn sau `map`

```java
int[] squares = random.ints()
        .map(n -> n * n)
        .limit(10)
        .toArray();
```

Pipeline lấy tối đa mười kết quả sau bước `map`; do mỗi đầu vào tạo đúng một đầu ra, nó cần tối đa mười số nguồn. Lưu ý phép `n * n` trên `int` có thể tràn số; nếu miền đầu vào lớn, cần chọn kiểu `long` hoặc quy tắc xử lý overflow phù hợp.

### 5.4. `limit` không phải giới hạn bộ nhớ tổng thể

`limit(10)` giới hạn số phần tử đầu ra của pipeline tại vị trí đó, nhưng không đảm bảo mọi bước trước nó dùng bộ nhớ hằng số. Một thao tác như `sorted()` phải nhìn toàn bộ đầu vào trước khi trả kết quả; nếu đặt trước `limit` trên stream không giới hạn, pipeline không thể hoàn tất:

```java
// Không kết thúc: sorted cần tiêu thụ toàn bộ nguồn không giới hạn.
// random.ints().sorted().limit(10).toArray();

// Có thể kết thúc: chỉ sắp xếp 100 số đầu tiên.
int[] smallestOfFirstHundred = random.ints()
        .limit(100)
        .sorted()
        .limit(10)
        .toArray();
```

Vị trí cắt nguồn phải đứng trước thao tác cần toàn bộ dữ liệu khi nguồn là không giới hạn.

## 6. Luồng hữu hạn sau khi lọc

Khi dùng overload có `streamSize`, số lượng phần tử **sau filter** có thể nhỏ hơn số lượng nguồn:

```java
long evenCount = random.ints(100)
        .filter(n -> n % 2 == 0)
        .count();
```

Nguồn có đúng 100 số, nhưng kết quả chỉ đếm số chẵn trong 100 số đó; không có bảo đảm kết quả là 50. Với phân bố phù hợp, 50 là kỳ vọng gần đúng chứ không phải số lượng được bảo đảm.

Nếu yêu cầu chính xác 20 số chẵn, có thể dùng:

```java
int[] twentyEvens = random.ints()
        .filter(n -> n % 2 == 0)
        .limit(20)
        .toArray();
```

Nguồn không giới hạn để có thể tiếp tục sinh đến khi đủ 20 kết quả phù hợp. Dù xác suất thiếu phần tử trong thực tế rất nhỏ với predicate này, đây vẫn là thuật toán có điều kiện dừng dựa trên khả năng sinh được đủ kết quả. Với predicate hiếm, việc chờ đủ số lượng có thể tốn thời gian lớn hoặc không kết thúc.

Nếu cần kiểm soát tài nguyên chặt chẽ, hãy giới hạn nguồn trước rồi chấp nhận kết quả có thể ít hơn, hoặc viết vòng lặp có giới hạn số lần thử và xử lý trường hợp không đủ mẫu.

## 7. Giới hạn với `ints`, `longs`, `doubles` trong thực tế

### 7.1. Kích thước stream dùng kiểu `long`

Các overload hữu hạn nhận `long streamSize`, không phải `int`. Điều này cho phép mô tả số lượng lớn hơn miền của `int`, nhưng không có nghĩa có thể thu mọi stream thành một mảng Java có kích thước tùy ý.

```java
long requested = 1_000_000L;
long count = random.ints(requested).count();
System.out.println(count); // 1000000
```

Nếu xử lý kết quả rất lớn, hãy dùng pipeline streaming để tính toán hoặc ghi từng phần thay vì luôn gọi `toArray()` hoặc `toList()`.

### 7.2. `count()` và terminal operation

`count()` tiêu thụ stream và trả về số phần tử dưới dạng `long`. Với stream có kích thước đã biết và pipeline chỉ gồm các thao tác không làm thay đổi số phần tử, implementation có thể tối ưu và không cần gọi generator cho từng phần tử. Không dựa vào side effect trong `peek` hoặc lambda để đếm số lần sinh.

Ví dụ đơn giản:

```java
long count = random.ints(1_000)
        .count();
```

Kết quả là `1000`; không cần tạo mảng 1000 phần tử chỉ để biết kích thước.

### 7.3. Không tái sử dụng một stream

Stream chỉ được tiêu thụ một lần. Ví dụ:

```java
IntStream numbers = random.ints(5);
long count = numbers.count();

// numbers.sum(); // IllegalStateException: stream đã được dùng.
```

Nếu cần hai kết quả độc lập, tạo hai stream mới từ generator hoặc thu dữ liệu vào một cấu trúc phù hợp rồi xử lý cấu trúc đó.

### 7.4. Tránh side effect trong pipeline

Các thao tác intermediate thường được thực hiện lazy. Một đoạn:

```java
random.ints(10)
        .peek(System.out::println);
```

chưa tiêu thụ stream, nên không có nghĩa mười số đã được in. Cần terminal operation:

```java
random.ints(10)
        .forEach(System.out::println);
```

Ngay cả khi có terminal operation, không nên dùng `peek` để thực hiện công việc nghiệp vụ bắt buộc. Hãy dùng `map`, `forEach` hoặc một cấu trúc xử lý rõ ràng theo mục đích.

## 8. Chọn bộ sinh số trong Java 17

### 8.1. `Random`

`java.util.Random` là lựa chọn đơn giản, quen thuộc và có các overload stream đang học. Có thể tạo seed cố định:

```java
Random random = new Random(2026L);
int[] sample = random.ints(5, 1, 100).toArray();
```

Với cùng seed và cùng cách gọi theo thứ tự, `Random` có hợp đồng tạo chuỗi giả ngẫu nhiên có thể tái lập; hữu ích cho ví dụ, kiểm thử và mô phỏng cần lặp lại. Seed cố định không biến kết quả thành ngẫu nhiên bảo mật.

`Random` an toàn khi được nhiều thread dùng chung, nhưng có thể gây tranh chấp khi nhiều luồng truy cập cùng một instance.

### 8.2. `ThreadLocalRandom`

`ThreadLocalRandom.current()` trả về generator gắn với thread hiện tại:

```java
import java.util.concurrent.ThreadLocalRandom;

int[] values = ThreadLocalRandom.current()
        .ints(10, 1, 7)
        .toArray();
```

Đây là lựa chọn thuận tiện cho mã nhiều thread cần số giả ngẫu nhiên độc lập theo thread mà không chia sẻ một `Random` instance duy nhất. Không thể đặt seed tùy ý cho instance nhận từ `current()` như cách tạo `new Random(seed)`.

### 8.3. `SplittableRandom`

`SplittableRandom` được thiết kế để hỗ trợ tách generator thành các generator con, phù hợp với những tác vụ tính toán có thể chia thành phần độc lập:

```java
import java.util.SplittableRandom;

SplittableRandom random = new SplittableRandom(2026L);
int[] values = random.ints(10, 1, 7).toArray();
```

Có thể dùng `split()` để tạo generator con cho tác vụ riêng. Đây là hướng hữu ích trong tính toán song song khi mỗi nhánh cần nguồn số riêng. Không chia sẻ một trạng thái generator tùy tiện giữa các tác vụ nếu tính tái lập và thứ tự kết quả là quan trọng.

### 8.4. `RandomGenerator` và thuật toán được chọn

Java 17 đưa vào `java.util.random.RandomGenerator` và các factory để làm việc với nhiều thuật toán. Có thể lập trình dựa trên interface:

```java
import java.util.random.RandomGenerator;

RandomGenerator generator = RandomGenerator.getDefault();
int[] values = generator.ints(10, 1, 7).toArray();
```

`getDefault()` cung cấp generator mặc định của runtime. Nếu cần thuật toán cụ thể, hãy tìm factory và chọn tên thuật toán được môi trường Java hỗ trợ, thay vì giả định mọi JDK hoặc cấu hình đều dùng cùng một implementation mặc định.

Khi cần tái lập kết quả qua nhiều lần chạy hoặc nhiều môi trường, hãy ghi rõ thuật toán, seed và trình tự sử dụng. Không dựa vào generator mặc định nếu hợp đồng ứng dụng yêu cầu chuỗi kết quả ổn định qua các phiên bản.

### 8.5. Số giả ngẫu nhiên không phải số ngẫu nhiên mật mã

`Random`, `SplittableRandom` và `ThreadLocalRandom` phù hợp với mô phỏng, lấy mẫu, trò chơi hoặc phân phối tải tùy yêu cầu. Không dùng chúng để tạo mật khẩu, token phiên, khóa hoặc giá trị cần chống đoán.

Với mục đích bảo mật, dùng `SecureRandom` và API bảo mật phù hợp. Đừng nhầm việc có seed dài hoặc kết quả khó đoán bằng mắt với bảo đảm mật mã.

## 9. Tính tái lập và thứ tự trong stream

### 9.1. Seed cố định cho bài kiểm thử

Một ví dụ kiểm thử có thể dùng seed cố định:

```java
Random first = new Random(123L);
Random second = new Random(123L);

int[] a = first.ints(5, 0, 100).toArray();
int[] b = second.ints(5, 0, 100).toArray();

System.out.println(java.util.Arrays.equals(a, b)); // true
```

Hai generator có cùng seed và cùng trình tự gọi sẽ tái lập kết quả theo hợp đồng của `Random`. Điều này hữu ích khi cần tái hiện lỗi hoặc tạo dữ liệu mẫu xác định.

### 9.2. Parallel stream và thứ tự xử lý

Có thể yêu cầu xử lý song song:

```java
random.ints(1_000, 0, 100)
        .parallel()
        .forEach(System.out::println);
```

Các hành động in có thể xuất hiện theo thứ tự khác nhau do các thread xử lý đồng thời. Nếu cần tôn trọng encounter order của stream:

```java
random.ints(10, 0, 100)
        .parallel()
        .forEachOrdered(System.out::println);
```

Tuy nhiên, `forEachOrdered` có thể giảm khả năng song song. Với xử lý số lượng lớn, hãy đo hiệu năng và chỉ dùng parallel khi tác vụ đủ lớn, độc lập và phù hợp.

Không giả định rằng chạy cùng seed trong một pipeline parallel tùy ý sẽ cho cùng thứ tự kết quả hiển thị hoặc cùng lịch thực thi giữa các môi trường. Nếu cần tính tái lập nghiêm ngặt, hãy xác định rõ generator, cách phân chia dữ liệu, thứ tự kết hợp và tránh phụ thuộc vào scheduling.

## 10. Ví dụ tích hợp: lấy mẫu, lọc và giới hạn

Chương trình sau tạo một số lượng hữu hạn các mẫu, lọc các số đạt điều kiện, thống kê và minh họa trường hợp stream không giới hạn được cắt bằng `limit`.

Tạo tệp `Main.java`:

```java
import java.util.Arrays;
import java.util.Random;
import java.util.stream.IntStream;

public class Main {
    public static void main(String[] args) {
        Random random = new Random(2026L);

        // Tạo đúng 12 số nguyên trong [10, 100).
        int[] samples = random.ints(12, 10, 100).toArray();
        System.out.println("Samples: " + Arrays.toString(samples));

        // Chỉ lấy tối đa 5 số chẵn từ nguồn 12 phần tử.
        int[] evenFromSamples = Arrays.stream(samples)
                .filter(value -> value % 2 == 0)
                .limit(5)
                .toArray();
        System.out.println("Even: " + Arrays.toString(evenFromSamples));

        // Lấy 5 số chẵn từ một nguồn effectively unlimited.
        int[] fiveEvens = random.ints()
                .filter(value -> value % 2 == 0)
                .limit(5)
                .toArray();
        System.out.println("Five evens: " + Arrays.toString(fiveEvens));

        // Lấy 4 số double trong [0.0, 1.0).
        double[] ratios = random.doubles(4).toArray();
        System.out.println("Ratios: " + Arrays.toString(ratios));

        // Luồng rỗng vì streamSize bằng 0.
        System.out.println(random.longs(0).count()); // 0
    }
}
```

Biên dịch và chạy trên JDK 17:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Seed cố định giúp kết quả có thể lặp lại khi thực hiện cùng chuỗi lời gọi. Nội dung quan trọng không phải một dãy số cụ thể, mà là cách xác định giới hạn:

- `ints(12, 10, 100)` sinh 12 số trong miền `[10, 100)`.
- `filter(...).limit(5)` chỉ trả tối đa năm phần tử chẵn trong 12 mẫu.
- `ints().filter(...).limit(5)` tiếp tục lấy từ nguồn không giới hạn đến khi có năm phần tử phù hợp.
- `doubles(4)` sinh đúng bốn giá trị trong `[0.0, 1.0)`.
- `longs(0)` là stream rỗng.

## 11. Các lỗi thường gặp

### 11.1. Gọi terminal operation trên stream không giới hạn

```java
// Không kết thúc bình thường:
// long count = random.ints().count();
```

Thêm `limit` hoặc chọn overload hữu hạn:

```java
long count = random.ints(1_000).count();
// Hoặc:
long countLimited = random.ints().limit(1_000).count();
```

### 11.2. Hiểu sai cận trên

```java
int value = random.ints(1, 10).findFirst().orElseThrow();
```

Giá trị có thể là 1 đến 9, không bao gồm 10. Nếu cần khoảng khác, hãy kiểm tra kỹ hợp đồng cận `[origin, bound)`.

### 11.3. Đặt `limit` trước `filter` khi muốn đủ số phần tử thỏa điều kiện

```java
// Có thể ít hơn 10 số chẵn:
int[] maybeTen = random.ints().limit(10)
        .filter(n -> n % 2 == 0).toArray();

// Lấy tối đa 10 số chẵn từ nguồn:
int[] tenEvens = random.ints()
        .filter(n -> n % 2 == 0)
        .limit(10)
        .toArray();
```

Hai pipeline không tương đương. Chọn thứ tự dựa trên việc muốn giới hạn **mẫu đầu vào** hay **kết quả sau lọc**.

### 11.4. Gọi `toArray` cho stream rất lớn

Một stream hữu hạn không có nghĩa luôn an toàn để đưa toàn bộ vào mảng. Với số lượng lớn, dùng xử lý theo phần, ghi ra nơi lưu trữ hoặc giảm dữ liệu bằng các phép toán phù hợp.

### 11.5. Dùng lại stream

Mỗi stream chỉ được tiêu thụ một lần. Gọi terminal operation thứ hai trên cùng instance thường gây `IllegalStateException`. Tạo stream mới cho lần xử lý tiếp theo.

### 11.6. Cho rằng `limit` bảo đảm pipeline luôn kết thúc

`limit(10)` sẽ chờ đủ tối đa mười phần tử tại vị trí của nó. Nếu phía trước là một `filter` không bao giờ cho qua phần tử nào, pipeline có thể chạy mãi. Nếu predicate quá hiếm, việc đủ mẫu có thể mất thời gian rất lâu.

### 11.7. Dùng bộ sinh giả ngẫu nhiên cho bảo mật

Không dùng `Random` để tạo token đăng nhập hoặc bí mật mật mã. Dùng `SecureRandom` và thiết kế bảo mật tương ứng.

## 12. Bài tập thực hành

### Bài 1 — Tạo đúng số lượng phần tử

Viết chương trình tạo 20 số nguyên trong khoảng `[100, 200)`, chuyển thành mảng và in độ dài.

Lời giải:

```java
int[] values = new Random().ints(20, 100, 200).toArray();
System.out.println(values.length); // 20
```

Giải thích: overload đầu tiên nhận `streamSize = 20`, tiếp theo là cận dưới và cận trên.

### Bài 2 — Tạo số double trong miền

Tạo 8 số double thuộc `[-2.5, 2.5)`; viết điều kiện kiểm tra từng số.

```java
double[] values = new Random().doubles(8, -2.5, 2.5).toArray();
for (double value : values) {
    if (value < -2.5 || value >= 2.5) {
        throw new AssertionError("Out of range: " + value);
    }
}
```

### Bài 3 — Phân biệt số mẫu và số kết quả

Cho nguồn 100 số nguyên. Tính số phần tử chẵn:

```java
long evenCount = new Random().ints(100)
        .filter(n -> n % 2 == 0)
        .count();
```

Kết quả không nhất thiết bằng 50. Hãy giải thích 50 là giá trị kỳ vọng nếu phân bố chẵn/lẻ cân bằng, còn số lượng thực tế được xác định bởi mẫu ngẫu nhiên cụ thể.

### Bài 4 — Lấy đúng 10 số chia hết cho 3

Viết pipeline từ nguồn không giới hạn, lọc các số chia hết cho 3 và lấy 10 phần tử đầu.

```java
int[] divisibleByThree = new Random().ints()
        .filter(n -> n % 3 == 0)
        .limit(10)
        .toArray();
```

Giải thích vì sao đặt `limit(10)` trước `filter` có thể chỉ thu được ít hơn 10 số.

### Bài 5 — Giới hạn số lần thử

Giả sử cần tìm 5 số thỏa một predicate có thể rất hiếm, nhưng không được phép thử vô hạn. Hãy dùng stream hữu hạn:

```java
int[] matches = new Random().ints(10_000)
        .filter(value -> value == 0)
        .limit(5)
        .toArray();
```

Kết quả có thể có ít hơn 5 phần tử, kể cả bằng 0. Hãy thiết kế cách báo cáo “không tìm đủ mẫu” thay vì giả định stream luôn tạo đủ.

### Bài 6 — Tái lập kết quả

Tạo hai đối tượng `Random` với cùng seed, sinh 10 số trong cùng miền, rồi dùng `Arrays.equals` so sánh hai mảng. Giải thích vì sao seed cố định hữu ích cho kiểm thử nhưng không tạo ra nguồn ngẫu nhiên bảo mật.

## 13. Tiêu chí hoàn thành

Người học hoàn thành bài khi có thể:

1. Nêu được kiểu stream và kiểu phần tử tương ứng của `ints`, `longs`, `doubles`.
2. Chọn đúng overload không giới hạn, overload hữu hạn và overload có khoảng giá trị.
3. Giải thích `streamSize` là số phần tử nguồn, chấp nhận 0, từ chối số âm.
4. Dự đoán đúng miền `[origin, bound)`, kiểm tra điều kiện cận hợp lệ và tránh lỗi cộng cận trên bị tràn.
5. Dùng `limit(n)` để cắt nguồn không giới hạn và giải thích vị trí `limit` tương tác với `filter`, `map`, `sorted`.
6. Phân biệt số phần tử nguồn với số phần tử sau lọc; biết một pipeline có thể không tạo đủ kết quả phù hợp.
7. Giải thích stream lazy, terminal operation, giới hạn tiêu thụ một lần và nguy cơ materialize mảng quá lớn.
8. Chọn được `Random`, `ThreadLocalRandom`, `SplittableRandom` hoặc một `RandomGenerator` phù hợp với bối cảnh.
9. Biết số giả ngẫu nhiên thông thường không dùng cho token hoặc dữ liệu cần bảo mật.
10. Biên dịch ví dụ bằng JDK 17 với `javac --release 17`.

## 14. Tài liệu chính thức

- [Java SE 17 API — `RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): hợp đồng API và các overload `ints`, `longs`, `doubles`.
- [Java SE 17 API — `Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): bộ sinh số giả ngẫu nhiên truyền thống và các stream.
- [Java SE 17 API — `ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): generator gắn với thread hiện tại.
- [Java SE 17 API — `SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): generator hỗ trợ split cho tác vụ độc lập.
- [Java SE 17 API — `IntStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html), [`LongStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/LongStream.html) và [`DoubleStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html): terminal operations, intermediate operations và cách tiêu thụ primitive streams.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): API và cải tiến generator được đưa vào Java 17.

**Ghi nhớ:** overload có `streamSize` xác định số phần tử nguồn; overload không có kích thước tạo luồng effectively unlimited; `limit(n)` cắt tối đa số phần tử tại vị trí của nó trong pipeline; `origin` được bao gồm còn `bound` bị loại trừ. Hiểu bốn điểm này giúp tạo đúng số mẫu, đúng miền giá trị và tránh pipeline không kết thúc.
