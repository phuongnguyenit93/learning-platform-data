# Kiểm tra tính đúng của kết quả số khi chuyển sang song song

> **Chương:** Độ chính xác khi tổng hợp số  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Kiểm chứng rằng pipeline tổng hợp số bằng Java Stream API vẫn đáp ứng yêu cầu nghiệp vụ khi chuyển từ `stream()` sang `parallelStream()` hoặc gọi `parallel()`. Các yếu tố quyết định gồm tính kết hợp của phép gộp, giá trị đơn vị, tràn số nguyên, sai số dấu phẩy động, làm tròn, trạng thái chia sẻ và hợp đồng của `Collector`.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **đúng về mặt số học**, **đúng theo kiểu dữ liệu Java** và **ổn định giữa các lần chạy**.
2. Kiểm tra ba điều kiện quan trọng của phép tổng hợp có thể chạy song song: *identity*, *associativity* và (khi dùng dạng `reduce` ba tham số) *compatibility*.
3. Giải thích vì sao `int`/`long` có thể tràn và vì sao cộng `double`/`float` có thể đổi kết quả khi thứ tự gộp thay đổi.
4. Chọn `mapToLong`, `BigInteger`, `BigDecimal`, phép tổng hợp primitive hoặc collector phù hợp với yêu cầu chính xác.
5. Viết phép kiểm chứng dựa trên **oracle độc lập**, bất biến (*invariants*), trường hợp biên và đầu vào phân vùng/đảo thứ tự.
6. Phát hiện side effect và data race khi chuyển một vòng lặp hoặc pipeline tuần tự sang Stream song song.
7. Đưa ra quyết định có nên bật xử lý song song hay giữ tuần tự dựa trên **độ đúng** trước khi đo hiệu năng.

Các ví dụ dùng Java 17+ (phù hợp với `record` và `List.of`). Các nguyên tắc về `reduce`, `collect`, kiểu primitive và `parallelStream` đã có từ Java 8. Khi cần Stream Gatherers hoặc collector tùy chỉnh ở các phần nâng cao của module, nguyên tắc kiểm tra độ đúng vẫn là kiểm tra phép chia/gộp trạng thái và kết quả cuối.

## 1. Vì sao đổi sang parallel có thể làm thay đổi kết quả?

Trong pipeline tuần tự, các phần tử thường được đưa vào phép tích lũy theo trình tự duyệt nguồn. Với parallel stream, công việc có thể được chia thành nhiều phần, mỗi phần tổng hợp riêng, rồi các kết quả trung gian được **gộp lại**. Cây gộp có thể khác với phép tính tuần tự từ trái sang phải.

~~~text
Nguồn có thứ tự: [a, b, c, d]

Tuần tự (một cách tính điển hình):
    (((identity ⊕ a) ⊕ b) ⊕ c) ⊕ d

Song song (một cách phân nhóm có thể xảy ra):
    (a ⊕ b)       (c ⊕ d)
         \         /
          \       /
       (a ⊕ b) ⊕ (c ⊕ d)

⊕ = phép tích lũy/gộp do chương trình cung cấp
~~~

Nếu phép `⊕` có tính **kết hợp** (*associative*) và giá trị đơn vị đúng, cách đặt dấu ngoặc sẽ không đổi kết quả theo đại số tương ứng. Nếu không, cùng tập dữ liệu có thể trả về các giá trị khác nhau.

Lưu ý: **Stream có encounter order không có nghĩa phép cộng sẽ luôn được nhóm theo một thứ tự cố định khi chạy song song.** Việc `toList()` bảo toàn thứ tự phần tử đầu ra (khi nguồn có thứ tự) cũng không bảo đảm một phép `reduce` số thực sẽ gộp theo cùng thứ tự như pipeline tuần tự.

Các nguyên nhân sai phổ biến:

| Nguyên nhân | Biểu hiện | Mức độ rủi ro |
|---|---|---|
| Phép tích lũy không kết hợp | Trừ, chia, làm tròn giữa chừng cho kết quả khác khi đổi cách nhóm | Sai logic |
| `float`/`double` có làm tròn nhị phân | Tổng/average có thể lệch vài đơn vị ở chữ số cuối, hoặc lệch lớn khi triệt tiêu | Sai số số học |
| Tràn `int`/`long` | Giá trị âm, nhỏ bất thường hoặc kết quả bị cuộn modulo | Sai miền giá trị |
| Thay đổi container ngoài lambda | Mất lượt cộng, ghi đè dữ liệu, lỗi đồng thời | Data race |
| Collector có combiner sai | Kết quả thiếu, nhân đôi hoặc lệ thuộc phân vùng | Sai hợp đồng |
| Dùng kết quả tuần tự làm chuẩn duy nhất | Hai cách đều có thể sai cùng một kiểu | Kiểm thử chưa đủ |
| So sánh `double` bằng `==` | Báo sai dù chênh lệch được chấp nhận, hoặc che khuất yêu cầu chính xác | Sai tiêu chí kiểm thử |

Ví dụ đơn giản để bắt đầu:

~~~java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4);

int sequential = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();

int parallel = numbers.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sequential); // 10
System.out.println(parallel);   // 10
~~~

Trường hợp này chưa phát hiện vấn đề vì đầu vào nhỏ và không tràn. Độ đúng phải được kiểm tra với **miền dữ liệu thực**, phép toán thật và các trường hợp biên.

## 2. Ba tầng của khái niệm “kết quả đúng”

Trước khi viết phép so sánh, xác định điều cần bảo đảm:

1. **Đúng theo nghiệp vụ:** tổng tiền phải chính xác đến đồng/xu, trung bình phải làm tròn theo quy tắc đã thỏa thuận, phép đếm không được mất bản ghi.
2. **Đúng theo phép toán và kiểu dữ liệu:** `int`, `long`, `double` và `BigDecimal` có hợp đồng số học khác nhau. Phép cộng có thể hợp lệ ở Java nhưng không thể hiện số nguyên toán học mong muốn khi tràn.
3. **Đúng theo tính chất thực thi:** pipeline không được đọc trạng thái đang thay đổi, không được có race condition hoặc phụ thuộc vào thứ tự thực thi của các lambda.

Hai phép tính có thể **đồng nhất từng bit nhưng vẫn sai nghiệp vụ**. Chẳng hạn cả tuần tự và song song cùng tính tổng `int` bị tràn. Ngược lại, hai phép tính `double` có thể khác vài bit nhưng đều đạt giới hạn sai số cho một bài toán thống kê.

Bảng thiết kế phép kiểm chứng:

| Loại kết quả | Chuẩn so sánh thường dùng |
|---|---|
| Số lượng bản ghi, tổng số nguyên trong miền an toàn | Bằng nhau **chính xác** với oracle |
| Tổng nguyên có nguy cơ vượt `long` | Oracle `BigInteger` hoặc phép toán miền rộng phù hợp |
| Tiền tệ, số thập phân cần chính xác | Oracle `BigDecimal` được tạo từ dữ liệu thập phân chuẩn; làm tròn theo quy tắc nghiệp vụ |
| Tổng/average `double` chấp nhận sai số | Sai số tuyệt đối/tương đối theo ngưỡng đã quy định; kiểm tra riêng NaN/vô cực |
| Kết quả theo nhóm | So sánh cùng tập khóa và giá trị của từng khóa; không dựa vào thứ tự duyệt `Map` |
| Đầu ra dạng danh sách | Xác định trước có yêu cầu thứ tự hay chỉ yêu cầu cùng nội dung/phần tử |

Đối với một bài toán nhạy cảm về tài chính, không nên “nới epsilon” để hợp thức hóa một phép cộng sai; hãy chọn cách biểu diễn số và quy tắc làm tròn thích hợp.

## 3. Hợp đồng giảm gộp: identity và associativity

### 3.1. Giá trị đơn vị (identity)

Với phép gộp `f` và phần tử đơn vị `e`, cần có:

~~~text
f(e, x) = x
f(x, e) = x
~~~

Ví dụ:

- Phép cộng: `e = 0`.
- Phép nhân: `e = 1`.
- Lấy giá trị lớn nhất: cần chọn identity phù hợp với miền dữ liệu, hoặc dùng dạng `reduce(BinaryOperator)` trả `Optional` nếu không có identity chung hợp lệ.

**Sai identity** có thể làm kết quả song song sai nặng vì identity được dùng cho các phần tính độc lập.

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

// Sai: 10 không phải identity của phép cộng.
int bad = values.parallelStream()
        .reduce(10, Integer::sum);

// Đúng theo modulo int (khi không quan tâm overflow):
int good = values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(good); // 6
~~~

Giá trị `bad` **không nên** được sử dụng để suy ra một kết quả ổn định: phép gộp song song có thể cộng giá trị 10 nhiều lần ở các phân vùng khác nhau. Ngay cả khi một lần chạy vô tình cho kết quả mong muốn, phép tổng hợp vẫn sai hợp đồng.

### 3.2. Tính kết hợp (associativity)

Phép `f` cần thỏa:

~~~text
f(f(a, b), c) = f(a, f(b, c))
~~~

Về số học chính xác, cộng và nhân số nguyên có tính kết hợp; trừ và chia **không có**.

~~~java
int left = (20 - 5) - 3;
int right = 20 - (5 - 3);

System.out.println(left);  // 12
System.out.println(right); // 18
~~~

Không dùng phép trừ làm accumulator/combiner cho một phép `reduce` mong đợi kết quả không phụ thuộc phân vùng:

~~~java
import java.util.List;

List<Integer> numbers = List.of(20, 5, 3);

// Không phù hợp với yêu cầu giảm gộp song song:
int result = numbers.parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

Với dữ liệu cố định, kết quả tùy cách nhóm và ghép trung gian, nên không bảo đảm đúng nghiệp vụ. Nếu muốn tính `20 - 5 - 3` theo thứ tự, hãy biểu đạt yêu cầu phụ thuộc thứ tự bằng vòng lặp hoặc thuật toán tuần tự phù hợp.

### 3.3. Phép cộng int có tính kết hợp theo modulo, nhưng vẫn có thể sai nghiệp vụ

Ở Java, cộng `int` tràn theo số học 32-bit dạng cuộn (wraparound). Đây là phép cộng có tính kết hợp **modulo** \(2^{32}\), nhưng không còn đại diện cho phép cộng số nguyên toán học khi kết quả thật vượt miền `int`.

~~~java
import java.util.stream.IntStream;

int wrapped = IntStream.of(Integer.MAX_VALUE, 1)
        .parallel()
        .sum();

System.out.println(wrapped); // -2147483648
~~~

Lỗi ở đây là **chọn miền số không đủ lớn**, không phải bằng chứng `parallel()` gây ra sai số. Một phép cộng tuần tự trên `int` cũng có thể trả về kết quả cuộn tương tự. Chuyển sang `long` hoặc `BigInteger` tùy miền giá trị.

## 4. Hợp đồng reduce ba tham số và tính tương thích

Dạng:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner
);
~~~

`accumulator` biến trạng thái `U` và phần tử `T` thành trạng thái mới; `combiner` gộp hai trạng thái `U`. Khi song song, thư viện có thể chạy accumulator ở nhiều phần rồi dùng combiner hợp nhất kết quả.

Bên cạnh identity và associativity, cần có **tính tương thích**:

~~~text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
~~~

Và `combiner(identity, u) == u`. Viết hai thao tác có ý nghĩa khác nhau sẽ làm kết quả phụ thuộc cách phân chia.

Ví dụ đúng khi muốn đếm tổng số ký tự:

~~~java
import java.util.List;

List<String> words = List.of("java", "stream", "api");

int sequential = words.stream()
        .reduce(
                0,
                (length, word) -> length + word.length(),
                Integer::sum
        );

int parallel = words.parallelStream()
        .reduce(
                0,
                (length, word) -> length + word.length(),
                Integer::sum
        );

System.out.println(sequential); // 13
System.out.println(parallel);   // 13
~~~

Với số ký tự có thể vượt `Integer.MAX_VALUE`, hãy dùng `long` hoặc `BigInteger`.

Ví dụ sai hợp đồng:

~~~java
// Sai: accumulator cộng độ dài, combiner lại lấy hiệu.
// Không dùng kết quả để ra quyết định nghiệp vụ.
int invalid = words.parallelStream()
        .reduce(
                0,
                (length, word) -> length + word.length(),
                (left, right) -> left - right
        );
~~~

Dạng `reduce` ba tham số còn đòi hỏi accumulator/combiner **không sửa trực tiếp một container mutable được chia sẻ**. Nếu muốn gom vào collection hoặc bản đồ, thường nên dùng `collect` với collector đúng hợp đồng.

## 5. Sai số dấu phẩy động: double không có tính kết hợp tổng quát

`double` tuân theo số học dấu phẩy động nhị phân hữu hạn. Phép cộng có làm tròn tại mỗi bước. Vì thế:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
~~~

Khi tính `b + c`, phần `1.0` nhỏ hơn rất nhiều so với độ lớn của `b` nên có thể bị mất trong làm tròn. Còn cách tính `(a + b) + c` triệt tiêu hai số rất lớn trước, sau đó giữ được `1.0`.

Sơ đồ:

~~~text
Nhóm trái:
  10^16 + (-10^16) = 0
  0 + 1 = 1

Nhóm phải:
  -10^16 + 1 ≈ -10^16  (mất phần nhỏ do làm tròn)
  10^16 + (-10^16) = 0

Cùng 3 đầu vào, khác cách nhóm => khác kết quả
~~~

Dạng `reduce(0.0, Double::sum)` dùng phép cộng `double` không đáp ứng tính kết hợp theo số học thực trong mọi trường hợp. Chuyển sang song song có thể đổi cấu trúc gộp và kết quả.

~~~java
import java.util.List;

List<Double> values = List.of(1.0e16, -1.0e16, 1.0);

double sequential = values.stream()
        .reduce(0.0, Double::sum);

double parallel = values.parallelStream()
        .reduce(0.0, Double::sum);

// Không khẳng định parallel luôn trả một giá trị cố định.
// So sánh với yêu cầu sai số và oracle thích hợp.
System.out.println("Sequential: " + sequential);
System.out.println("Parallel: " + parallel);
~~~

**Quan trọng:** `DoubleStream.sum()` có thể sử dụng kỹ thuật tổng có bù sai số (*compensated summation*) hoặc cách triển khai khác để cải thiện độ chính xác. API không bảo đảm một thứ tự cộng cố định; do đó không nên dự đoán từng bit của `DoubleStream.sum()` từ một ví dụ gộp thủ công hoặc dùng kết quả của nó làm định nghĩa duy nhất của “đúng”.

### 5.1. Lỗi làm tròn và lỗi triệt tiêu

Hai vấn đề thường gặp:

- **Làm tròn tích lũy:** nhiều phép cộng nhỏ có thể tạo sai số tương đối đáng kể.
- **Triệt tiêu (*cancellation*):** tổng các giá trị dương/âm gần bằng nhau làm mất chữ số có nghĩa khi xử lý các số có độ lớn rất khác nhau.

Ví dụ tổng số rất lớn và rất nhỏ trong cùng dãy có thể nhạy với cách chia phân vùng và thứ tự cộng. Khi kết quả thật rất gần 0, chỉ dùng **sai số tương đối** dễ gây hiểu lầm vì mẫu so sánh gần 0; cần kết hợp ngưỡng sai số tuyệt đối.

### 5.2. Không hứa tính tất định bit-for-bit với parallel double

Ngay cả khi một JDK và một cỡ dữ liệu thường cho kết quả lặp lại giống nhau, **hợp đồng tổng quát của phép giảm gộp double không cam kết một cây gộp cố định theo mọi môi trường**. Đổi nguồn, `Spliterator`, phiên bản JDK hoặc điều kiện chạy có thể thay đổi cách nhóm.

Nếu yêu cầu là “mỗi lần chạy phải ra đúng cùng chuỗi thập phân”, hãy xác định một thuật toán và quy tắc làm tròn cụ thể. Với dữ liệu thập phân cần chính xác, cân nhắc `BigDecimal`. Với số thực khoa học, chọn thuật toán ổn định số học và chuẩn so sánh sai số rõ ràng; có thể phải duy trì thứ tự xử lý cố định.

## 6. Tràn int/long khi tổng hợp: chọn miền số trước khi song song hóa

### 6.1. Nâng kiểu trước khi cộng

~~~java
import java.util.List;

List<Integer> amounts = List.of(
        1_500_000_000,
        1_500_000_000
);

int overflowed = amounts.stream()
        .mapToInt(Integer::intValue)
        .sum();

long exactInLong = amounts.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(overflowed);  // -1294967296
System.out.println(exactInLong); // 3000000000
~~~

Phải chuyển sang `long` **trước khi phép cộng tràn `int`**. Ép kiểu một tổng `int` sau khi đã tràn sẽ không khôi phục được giá trị thật:

~~~java
int badIntSum = amounts.stream()
        .mapToInt(Integer::intValue)
        .sum();

long stillWrong = (long) badIntSum; // Đã quá muộn
~~~

`long` rộng hơn `int` nhưng **không vô hạn**. `LongStream.sum()` cũng có thể tràn nếu tổng vượt miền `long`.

### 6.2. Dùng BigInteger khi yêu cầu tính đúng số nguyên toán học

~~~java
import java.math.BigInteger;
import java.util.List;

List<Long> hugeValues = List.of(
        Long.MAX_VALUE,
        Long.MAX_VALUE,
        5L
);

BigInteger exact = hugeValues.parallelStream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(exact); // 18446744073709551619
~~~

Phép cộng `BigInteger` không tràn như `long` theo giới hạn giá trị cố định. `BigInteger::add` là phép gộp chính xác và có tính kết hợp theo số học nguyên; `BigInteger.ZERO` là identity đúng.

### 6.3. Math.addExact giúp phát hiện tràn, nhưng cần hiểu giới hạn

~~~java
import java.util.List;

List<Long> values = List.of(5L, 10L, 20L);

long sum = values.parallelStream()
        .reduce(0L, Math::addExact);

System.out.println(sum); // 35
~~~

`Math.addExact` ném `ArithmeticException` khi **một phép cộng trung gian** vượt miền `long`. Đây là lựa chọn hữu ích khi quy định bài toán là **từ chối phép tính có tràn**.

Nhưng nếu dữ liệu có cả số rất lớn dương/âm, một cách nhóm có thể tạo tổng trung gian tràn trong khi tổng toán học cuối cùng vẫn nằm trong miền `long`. Vì vậy, `Math.addExact` không phải phép kiểm chứng “kết quả cuối luôn đúng trong long bất kể cách nhóm” nếu đầu vào có thể triệt tiêu. Khi cần tính toán chính xác trên **mọi cách nhóm**, dùng `BigInteger` rồi kiểm tra miền tại **cuối**:

~~~java
import java.math.BigInteger;

BigInteger total = values.parallelStream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

long safeLong = total.longValueExact(); // Ném nếu kết quả cuối ngoài long
~~~

Với đầu vào chỉ không âm, kiểm tra overflow bằng `addExact` có thể phù hợp hơn vì tổng trung gian không vượt quá tổng cuối; với dữ liệu hỗn hợp dương/âm, hãy kiểm tra giả định trước khi chọn kỹ thuật.

## 7. Tiền tệ và thập phân: BigDecimal, scale và thời điểm làm tròn

`double` không biểu diễn chính xác nhiều phân số thập phân thông dụng như `0.1`. Khi nghiệp vụ cần tổng tiền hoặc tỷ lệ thập phân chính xác, dùng `BigDecimal` (hoặc lưu đơn vị nhỏ nhất bằng `long` nếu chắc chắn không tràn và đơn vị cố định).

### 7.1. Tạo BigDecimal từ dữ liệu thập phân chuẩn

~~~java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> prices = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"),
        new BigDecimal("0.30")
);

BigDecimal sequential = prices.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal parallel = prices.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(sequential); // 0.60
System.out.println(parallel);   // 0.60
~~~

Ở ví dụ này, phép `add` không truyền `MathContext` nên là phép cộng thập phân **chính xác**, và identity `BigDecimal.ZERO` hợp lệ.

**Không** nên tạo số tiền bằng `new BigDecimal(0.1)` nếu nghiệp vụ muốn biểu diễn chính xác chuỗi thập phân `"0.1"`. Constructor từ `double` ghi nhận giá trị nhị phân chính xác của `double`, vốn có thể khác số thập phân mong muốn. Dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` sau khi hiểu rõ nguồn đầu vào.

### 7.2. Làm tròn ở mỗi bước làm hỏng tính kết hợp

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

MathContext mc = new MathContext(2, RoundingMode.HALF_UP);

BigDecimal a = new BigDecimal("9.9");
BigDecimal b = new BigDecimal("0.2");
BigDecimal c = new BigDecimal("-9.9");

BigDecimal left = a.add(b, mc).add(c, mc);
BigDecimal right = a.add(b.add(c, mc), mc);

System.out.println(left);  // 0.1
System.out.println(right); // 0.2
~~~

Khi `MathContext` làm tròn kết quả từng phép cộng, phép gộp không còn kết hợp theo toán học thập phân chính xác. Nếu đưa `add(other, mc)` vào `parallelStream().reduce(...)`, kết quả có thể phụ thuộc cách chia và gộp.

Khi quy tắc nghiệp vụ cho phép, hãy **cộng chính xác trước, làm tròn một lần cuối**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal total = prices.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal rounded = total.setScale(2, RoundingMode.HALF_UP);
~~~

Tuy nhiên, có bài toán mà **mỗi giao dịch phải được làm tròn trước khi tổng hợp** (ví dụ từng khoản thuế/phí theo một quy tắc cụ thể). Khi ấy, cần làm tròn **từng dòng dữ liệu theo nghiệp vụ** rồi mới gộp các giá trị đã được làm tròn bằng phép cộng chính xác. Quy tắc làm tròn là một phần của mô hình dữ liệu, không phải “tối ưu” tùy chọn.

### 7.3. So sánh BigDecimal đúng ý nghĩa

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));        // false
System.out.println(a.compareTo(b) == 0); // true
~~~

`equals` xét cả **giá trị và scale**, còn `compareTo` xét giá trị số. Nếu mục tiêu là kiểm tra **cùng số tiền**, `compareTo(...) == 0` thường phù hợp. Nếu giao diện hoặc định dạng lưu trữ yêu cầu scale cố định (ví dụ luôn hai chữ số thập phân), nên kiểm tra/chuẩn hóa scale theo hợp đồng riêng.

## 8. Trung bình cộng: gộp tổng và số lượng, chỉ chia ở cuối

Một sai lầm phổ biến là “tính trung bình mỗi phân vùng rồi lấy trung bình các trung bình”. Cách đó chỉ đúng khi các phân vùng có cùng số phần tử (hoặc khi gộp có trọng số phù hợp).

Ví dụ:

~~~text
Nhóm A: [10, 20]        average = 15
Nhóm B: [100]           average = 100

Sai: (15 + 100) / 2 = 57.5
Đúng: (10 + 20 + 100) / 3 = 43.333...
~~~

Nếu cần trung bình cộng từ một Stream song song và yêu cầu kết quả chính xác theo thập phân, giữ **tổng chính xác** và **số lượng**, rồi chia sau khi gộp:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.List;

record SumCount(BigInteger sum, long count) {
    SumCount add(int value) {
        return new SumCount(sum.add(BigInteger.valueOf(value)),
                            Math.addExact(count, 1));
    }

    SumCount merge(SumCount other) {
        return new SumCount(sum.add(other.sum),
                            Math.addExact(count, other.count));
    }
}

List<Integer> samples = List.of(10, 20, 100);

SumCount stats = samples.parallelStream()
        .reduce(
                new SumCount(BigInteger.ZERO, 0L),
                SumCount::add,
                SumCount::merge
        );

if (stats.count() == 0) {
    System.out.println("Không có dữ liệu để tính trung bình");
} else {
    BigDecimal mean = new BigDecimal(stats.sum())
            .divide(BigDecimal.valueOf(stats.count()),
                    4, RoundingMode.HALF_UP);

    System.out.println(mean); // 43.3333
}
~~~

Các thuộc tính quan trọng:

- `SumCount` là `record` bất biến; accumulator và combiner trả về **đối tượng mới**, không sửa một biến chia sẻ.
- `sum` dùng `BigInteger`, giữ giá trị số nguyên chính xác.
- `count` cộng bằng `Math.addExact` để nhận diện tràn nếu xảy ra.
- `merge` cộng các tổng và số lượng, là cách gộp đúng cho mọi phân vùng.
- Chỉ `divide` và làm tròn **sau** khi đã hợp nhất toàn bộ dữ liệu.

Nếu nghiệp vụ chấp nhận độ chính xác `double`, `IntStream.average()` hoặc `DoubleStream.average()` có thể ngắn hơn; vẫn cần kiểm tra kết quả và trường hợp Stream rỗng (API trả `OptionalDouble`).

## 9. Collector tự tạo: kiểm chứng supplier, accumulator, combiner, finisher

`collect` cũng có thể chạy song song bằng cách tạo các container tích lũy rồi gộp chúng. Hợp đồng tổng hợp áp dụng cho **trạng thái** được tích lũy, không chỉ cho giá trị cuối.

Một collector tốt cho tổng số nguyên chính xác có thể dùng một container riêng cho mỗi phần xử lý rồi gộp:

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collector;

record Row(long cents) {}

class Totals {
    static final class Acc {
        BigInteger sum = BigInteger.ZERO;

        void add(Row row) {
            sum = sum.add(BigInteger.valueOf(row.cents()));
        }

        Acc merge(Acc other) {
            sum = sum.add(other.sum);
            return this;
        }
    }

    static BigInteger total(List<Row> rows, boolean parallel) {
        var source = parallel ? rows.parallelStream() : rows.stream();

        return source.collect(Collector.of(
                Acc::new,
                Acc::add,
                Acc::merge,
                acc -> acc.sum
        ));
    }

    public static void main(String[] args) {
        List<Row> rows = List.of(new Row(100), new Row(250), new Row(-50));
        System.out.println(total(rows, false)); // 300
        System.out.println(total(rows, true));  // 300
    }
}
~~~

Ở đây `Acc` có trạng thái thay đổi **bên trong container của collector**, nhưng `Collector.of` không khai báo `CONCURRENT`, nên framework quản lý việc tạo container và gộp cho các luồng xử lý. Không được giữ một `Acc` toàn cục rồi cho mọi thread cập nhật không đồng bộ.

Khi tự viết collector, kiểm tra:

1. **Supplier** tạo container mới, độc lập, đúng trạng thái ban đầu.
2. **Accumulator** cập nhật đúng một container bằng dữ liệu đầu vào.
3. **Combiner** gộp hai container sao cho kết quả tương đương với xử lý toàn bộ phần tử chung.
4. **Finisher** trả kết quả theo hợp đồng; nếu làm tròn, cần xác định làm tròn **một lần ở cuối**.
5. Nếu khai báo `CONCURRENT`, container và accumulator phải thực sự đáp ứng yêu cầu an toàn khi nhiều thread cùng truy cập. Không tự gắn đặc tính này chỉ để “tăng tốc”.
6. Nếu kết quả phải bảo toàn encounter order, không đánh dấu `UNORDERED` tùy tiện.

Những kiểm tra này cũng hữu ích với `groupingBy`, collector tùy chỉnh và những hoạt động dựa trên `Spliterator` của Java Stream API.

## 10. Nhóm dữ liệu rồi cộng: tính đúng của từng khóa

Chuyển sang song song không chỉ ảnh hưởng một tổng toàn cục; với `groupingBy` hoặc `toMap`, cần kiểm tra từng nhóm.

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Entry(String category, long cents) {}

List<Entry> rows = List.of(
        new Entry("BOOK", 100),
        new Entry("PEN",  40),
        new Entry("BOOK", -20),
        new Entry("PEN",  60)
);

Map<String, BigInteger> totals = rows.parallelStream()
        .collect(Collectors.groupingBy(
                Entry::category,
                Collectors.mapping(
                        e -> BigInteger.valueOf(e.cents()),
                        Collectors.reducing(BigInteger.ZERO, BigInteger::add)
                )
        ));

System.out.println(totals.get("BOOK")); // 80
System.out.println(totals.get("PEN"));  // 100
~~~

`groupingBy` có thể thu gom và gộp các bản đồ trung gian; thứ tự duyệt `Map` đầu ra không phải điều cần dựa vào. Kiểm chứng bản đồ bằng **tập khóa** và **tổng của từng khóa**, không so sánh chuỗi được in từ `Map.toString()`.

Nếu chuyển sang `groupingByConcurrent`, cần hiểu rõ hợp đồng collector, thứ tự và tính đồng thời. Với các phép cộng số thập phân có làm tròn trung gian, chỉ đổi từ `groupingBy` sang dạng concurrent không tự làm kết quả chính xác.

### 10.1. Dữ liệu trùng khóa và merge function

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigInteger> totals = rows.parallelStream()
        .collect(Collectors.toMap(
                Entry::category,
                e -> BigInteger.valueOf(e.cents()),
                BigInteger::add
        ));
~~~

`toMap` cần merge function vì có nhiều dòng cùng khóa. `BigInteger::add` có tính kết hợp, nên phù hợp để gộp các số tiền chính xác. Ngược lại, merge function kiểu `(a, b) -> a - b` hoặc làm tròn từng bước có thể cho kết quả phụ thuộc cách nhóm.

## 11. Không dùng biến cộng dồn bên ngoài pipeline song song

Mã tuần tự sau có thể tình cờ cho kết quả mong đợi:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);
int[] shared = {0};

values.stream().forEach(n -> shared[0] += n);

System.out.println(shared[0]); // 10 trong ví dụ tuần tự này
~~~

Nhưng chuyển trực tiếp sang song song là sai:

~~~java
// Tránh:
values.parallelStream().forEach(n -> shared[0] += n);
~~~

`shared[0] += n` gồm đọc, tính và ghi; nhiều thread có thể ghi đè kết quả của nhau. `shared` effectively final **không** làm nội dung mảng bất biến hoặc thread-safe.

Thay bằng:

~~~java
long total = values.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(total); // 10
~~~

Tương tự, không ghi vào một `ArrayList`/`HashMap` chia sẻ từ `forEach` song song nếu không có thiết kế đồng bộ phù hợp.

### 11.1. AtomicInteger có phải lời giải mặc định?

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger total = new AtomicInteger();

IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(total::addAndGet);

System.out.println(total.get()); // 500500
~~~

`AtomicInteger` bảo đảm cập nhật nguyên tử trong phạm vi `int`, nhưng mọi thread cùng tranh chấp một ô số và phép cộng vẫn có thể tràn. Nó cũng làm pipeline phụ thuộc side effect và khó phân tích trong các phép dừng sớm như `findAny` hoặc `limit`.

Với tổng hợp thông thường, dùng `sum`, `reduce` hoặc collector chuẩn đúng hợp đồng. Nếu thật sự cần counter đồng thời bên ngoài Stream (ví dụ ghi metric), thiết kế đó phải được đánh giá riêng; metric không nên bị nhầm với kết quả số nghiệp vụ.

## 12. Kiểm chứng bằng oracle độc lập

**Không nên chỉ so sánh `sequential == parallel` rồi kết luận đúng.** Cả hai có thể chia sẻ cùng lỗi: overflow, sai quy tắc lọc, nhầm đơn vị tiền, hoặc làm tròn ở vị trí sai.

Một oracle là cách tính tham chiếu tin cậy, **khác đường thực thi** với pipeline cần kiểm tra. Với tổng tiền dạng cent, một vòng lặp `BigInteger` rõ ràng là oracle tốt.

Ví dụ hoàn chỉnh, dùng `BigInteger` để kiểm tra kết quả trên đơn hàng có số lượng và các bản ghi hoàn trả (cents âm):

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.List;

public class ParallelTotalVerification {
    record Sale(String id, long centsPerUnit, long quantity) {}

    static BigInteger expectedByLoop(List<Sale> sales) {
        BigInteger total = BigInteger.ZERO;
        for (Sale sale : sales) {
            BigInteger lineTotal =
                    BigInteger.valueOf(sale.centsPerUnit())
                            .multiply(BigInteger.valueOf(sale.quantity()));
            total = total.add(lineTotal);
        }
        return total;
    }

    static BigInteger totalByStream(List<Sale> sales, boolean parallel) {
        var source = parallel ? sales.parallelStream() : sales.stream();

        return source
                .map(sale -> BigInteger.valueOf(sale.centsPerUnit())
                        .multiply(BigInteger.valueOf(sale.quantity())))
                .reduce(BigInteger.ZERO, BigInteger::add);
    }

    static void verify(List<Sale> sales) {
        BigInteger oracle = expectedByLoop(sales);
        BigInteger sequential = totalByStream(sales, false);
        BigInteger parallel = totalByStream(sales, true);

        if (!oracle.equals(sequential)) {
            throw new AssertionError(
                    "Sequential != oracle: " + sequential + " / " + oracle);
        }

        if (!oracle.equals(parallel)) {
            throw new AssertionError(
                    "Parallel != oracle: " + parallel + " / " + oracle);
        }

        System.out.println("PASS: " + oracle + " cents");
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("S-01", 199, 2),  // +398 cents
                new Sale("S-02", 150, 3),  // +450 cents
                new Sale("R-03", -199, 1)  // -199 cents
        );

        verify(sales); // PASS: 649 cents

        BigInteger cents = totalByStream(sales, true);
        BigDecimal display = new BigDecimal(cents, 2);
        System.out.println(display); // 6.49
    }
}
~~~

Trong ví dụ:

- Mỗi dòng nhân giá với số lượng bằng `BigInteger`, tránh tràn `long` ngay ở bước nhân.
- Oracle dùng **vòng lặp** để tính trực tiếp; pipeline cần kiểm tra dùng `map` + `reduce`.
- Cả hai chế độ Stream được đối chiếu với oracle, không chỉ đối chiếu lẫn nhau.
- Việc chuyển cents thành số tiền có hai chữ số thập phân diễn ra **sau** tổng hợp.
- Nếu nguồn thực tế có các quy tắc giảm giá, thuế, hoàn trả và làm tròn riêng, oracle phải mô hình hóa đúng các quy tắc ấy.

Đoạn mã này minh họa chiến lược kiểm chứng; trong quy trình STEP 4, đây là tài liệu học và chưa phải kết quả chạy test của dự án.

## 13. Kiểm tra tính bất biến khi phân vùng lại dữ liệu

Một phép tổng hợp kết hợp đúng nên cho cùng kết quả khi chia dữ liệu thành các phần rồi gộp, **nếu giữ cùng tập phần tử và các điều kiện nghiệp vụ**.

Với tổng `BigInteger`:

~~~java
import java.math.BigInteger;
import java.util.List;

List<Long> amounts = List.of(7L, -3L, 20L, 5L);

BigInteger allAtOnce = amounts.parallelStream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

BigInteger firstHalf = amounts.subList(0, 2).stream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

BigInteger secondHalf = amounts.subList(2, 4).stream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

BigInteger recombined = firstHalf.add(secondHalf);

System.out.println(allAtOnce); // 29
System.out.println(recombined); // 29
~~~

Các bất biến hữu ích khác:

- **Phân vùng:** `aggregate(A ++ B) = combine(aggregate(A), aggregate(B))` nếu phép gộp đúng hợp đồng.
- **Phần tử đơn vị:** thêm phần tử có giá trị 0 không đổi tổng, nếu 0 thật sự là phần tử trung hòa.
- **Hoán vị:** với tổng chính xác của số nguyên hoặc `BigDecimal` không làm tròn trung gian, đổi thứ tự không đổi kết quả toán học.
- **Lọc:** tổng các phần tử được giữ + tổng các phần tử bị loại = tổng tất cả, khi các tổng được tính chính xác và có thể cộng lại hợp lệ.
- **Nhóm dữ liệu:** tổng của tất cả nhóm bằng tổng toàn cục, nếu mỗi dòng thuộc đúng một nhóm và không mất/nhân đôi.

**Không áp dụng bất biến hoán vị “bằng nhau bit-for-bit” một cách máy móc cho `double`**, vì phép cộng nhị phân không kết hợp. Ở đó cần kiểm tra theo tolerance/đặc tính số học đã xác định.

## 14. Ma trận ca kiểm thử khi bật parallel()

Một vài trường hợp nhỏ không thể thay thế việc kiểm tra dải dữ liệu thực tế.

| Ca | Mục đích | Điều cần xác nhận |
|---|---|---|
| Stream rỗng | Identity/giá trị mặc định | Tổng 0 hoặc kết quả trống đúng hợp đồng |
| Một phần tử | Không mất hoặc nhân đôi | Kết quả bằng chính phần tử |
| Toàn số 0 | Trạng thái trung hòa | Kết quả 0 |
| Toàn số âm | Độ đúng với dấu | Tổng/average chính xác |
| Dương và âm triệt tiêu | Lỗi cộng trung gian | Tổng cuối và hành vi overflow đúng |
| `Integer.MAX_VALUE` / `Long.MAX_VALUE` | Kiểm tra giới hạn kiểu số | Không âm thầm overflow |
| Nhiều giá trị rất lớn xen rất nhỏ | Độ ổn định dấu phẩy động | Tolerance đạt yêu cầu |
| `NaN`, ±Infinity, -0.0 | Các giá trị IEEE 754 đặc biệt | Chính sách rõ, không so sánh vô nghĩa |
| Nhóm trùng khóa | Collector và combiner | Không mất hay nhân đôi dòng |
| Dữ liệu không đều giữa các phân vùng | Kiểm tra trung bình và giảm gộp | Không lấy trung bình các trung bình |
| Dữ liệu lặp lớn | Race condition, contention | Kết quả và số lượng bất biến |
| Nguồn có thứ tự/không thứ tự | Phụ thuộc encounter order | Kết quả số đúng theo yêu cầu |
| Mỗi giá trị xuất hiện nhiều lần | Không tạo tác dụng phụ | Tổng phản ánh đúng multiplicity |
| Shuffle với seed cố định | Độ nhạy cách nhóm | Kết quả chính xác hoặc trong tolerance |

### 14.1. Không đủ nếu chỉ chạy một lần

Một data race đôi khi không bộc lộ ở đầu vào nhỏ hoặc khi máy chỉ chạy ít thread. Bài test song song nên được lặp lại với kích thước và phân bố dữ liệu khác nhau. **Nhưng kết quả lặp lại ổn định vẫn chưa chứng minh phép toán hợp đồng đúng**: cần một oracle và các trường hợp phản ví dụ đã thiết kế.

### 14.2. Hoán vị có seed để tái hiện lỗi

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

List<Long> original = List.of(
        Long.MAX_VALUE, -Long.MAX_VALUE, 5L, 7L, -3L
);

BigInteger expected = original.stream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

for (int trial = 0; trial < 30; trial++) {
    List<Long> shuffled = new ArrayList<>(original);
    Collections.shuffle(shuffled, new Random(20261118L + trial));

    BigInteger actual = shuffled.parallelStream()
            .map(BigInteger::valueOf)
            .reduce(BigInteger.ZERO, BigInteger::add);

    if (!expected.equals(actual)) {
        throw new AssertionError("Mismatch at trial " + trial);
    }
}
~~~

Seed cố định giúp tái hiện ca kiểm thử. Với kết quả số thực có thể sai khác do thứ tự cộng, kiểm thử hoán vị nên đánh giá sai số thay vì yêu cầu chính xác tuyệt đối nếu nghiệp vụ không đòi hỏi điều đó.

## 15. So sánh double bằng tolerance có kiểm soát

Với kết quả số thực, hãy xác định **ngưỡng sai số theo nghiệp vụ**:

- **Absolute tolerance:** phù hợp khi giá trị thật gần 0 hoặc đơn vị đo có sai số tối đa cố định.
- **Relative tolerance:** phù hợp khi độ lớn biến thiên rộng và sai số có thể tăng theo quy mô.
- **ULP-based:** đôi khi hữu ích để kiểm tra khác biệt biểu diễn nhị phân, nhưng không tự nói lên sai số chấp nhận được trong nghiệp vụ.

Một hàm so sánh tổng quát cho **hai giá trị hữu hạn**, đặt trong lớp tiện ích:

~~~java
final class NumericComparison {
    static boolean closeEnough(
            double actual, double expected,
            double absoluteTolerance, double relativeTolerance) {

        if (!Double.isFinite(actual) || !Double.isFinite(expected)) {
            return false; // Giá trị đặc biệt cần kiểm tra theo chính sách riêng
        }
        if (!Double.isFinite(absoluteTolerance)
                || !Double.isFinite(relativeTolerance)
                || absoluteTolerance < 0.0
                || relativeTolerance < 0.0) {
            throw new IllegalArgumentException("Tolerance không hợp lệ");
        }

        double scale = Math.max(Math.abs(actual), Math.abs(expected));
        double allowed = Math.max(
                absoluteTolerance,
                relativeTolerance * scale
        );

        return Math.abs(actual - expected) <= allowed;
    }
}
~~~

Hàm dùng công thức:

~~~text
|actual - expected| <= max(absTol, relTol * max(|actual|, |expected|))
~~~

Ví dụ:

~~~java
double expected = 100.0;
double actual = 100.0000003;

System.out.println(
        NumericComparison.closeEnough(actual, expected, 1e-6, 1e-9)
); // true
~~~

**Đây là một tiêu chí kiểm thử mẫu**, không phải giới hạn sai số được Java bảo đảm. Giá trị `1e-6` hay `1e-9` phải bắt nguồn từ yêu cầu đo lường/nghiệp vụ. Nếu dữ liệu có độ lớn rất lớn làm phép tính chênh lệch tràn thành vô cực, hoặc thuật toán có yêu cầu nghiêm ngặt về độ ổn định, cần thiết kế so sánh số học phù hợp hơn.

### 15.1. NaN, infinity và signed zero cần xử lý riêng

~~~java
System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.isNaN(Double.NaN));  // true

System.out.println(Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY);
// true

System.out.println(0.0 == -0.0); // true
System.out.println(Double.compare(0.0, -0.0) == 0); // false
~~~

Không tự đặt quy tắc “hai NaN là bằng nhau” hay “-0.0 và +0.0 là khác nhau” cho mọi bài toán. Cần quyết định:

- `NaN` trong dữ liệu có được phép hay bị loại?
- Có được phép xuất hiện ±Infinity không?
- Dấu của số 0 có ý nghĩa với phép tính tiếp theo hay định dạng đầu ra không?

Nếu các giá trị đặc biệt là không hợp lệ, hãy loại/chặn ở bước xác thực đầu vào và kiểm tra không có giá trị không hữu hạn trong kết quả cuối:

~~~java
import java.util.stream.DoubleStream;

double total = DoubleStream.of(1.25, 2.75).parallel().sum();

if (!Double.isFinite(total)) {
    throw new ArithmeticException("Kết quả không hữu hạn");
}
~~~

### 15.2. Oracle cho thập phân và oracle cho số thực nhị phân

Nếu đầu vào gốc là các **chuỗi số thập phân** như `"0.10"` và `"0.20"`, dùng `BigDecimal(String)` làm oracle cho phép cộng thập phân chính xác. Nếu đầu vào vốn là một mảng `double` đã qua tính toán vật lý, việc tự chuyển sang `BigDecimal.valueOf(double)` không tự khôi phục độ chính xác đã mất trong các bước trước đó.

Hãy ghi rõ oracle biểu diễn **đại lượng thực, thập phân nghiệp vụ hay giá trị nhị phân lưu trong double**. Không có một chuẩn so sánh duy nhất đúng cho mọi ứng dụng.

## 16. Quy trình chuyển từ sequential sang parallel có kiểm soát

Một quy trình thực tế gồm các bước sau:

1. **Xác định hợp đồng số học:** đơn vị, miền giá trị, sai số cho phép, rounding mode, chính sách overflow, NaN và kết quả rỗng.
2. **Kiểm tra nguồn:** Stream có thể phân chia không, dữ liệu có đang bị thay đổi không, nguồn có gắn I/O hay tài nguyên không?
3. **Kiểm tra pipeline:** các lambda có stateless và non-interfering không? Có ghi vào biến/container dùng chung không?
4. **Kiểm tra reduce/collect:** identity, associativity, compatibility, supplier/combiner và độ đúng khi thay phân vùng.
5. **Xây oracle độc lập:** dùng vòng lặp đơn giản và phép toán đủ độ rộng/chính xác, hoặc bộ dữ liệu được tính tay đáng tin cậy.
6. **Chạy đối chiếu:** cả tuần tự lẫn song song đều phải đạt oracle hoặc ngưỡng tolerance; không lấy một cách làm oracle duy nhất của cách kia.
7. **Thử ca biên, shuffle và nhiều kích thước:** tìm overflow, lỗi grouping/combiner, sai số số thực và race condition.
8. **Đánh giá hiệu năng sau khi đã đúng:** so sánh latency/throughput và chi phí cấp phát, cân nhắc `Spliterator`, tải hệ thống và quy mô dữ liệu.

Sơ đồ quyết định:

~~~text
Cần tổng hợp song song?
        |
        v
Phép gộp có identity + associativity đúng?
        |-- Không --> Đổi phép gộp / giữ tuần tự có thứ tự
        |
        v
Kiểu số có đủ miền và độ chính xác?
        |-- Không --> Nâng kiểu / BigInteger / BigDecimal /
        |             đổi thuật toán và chính sách rounding
        |
        v
Lambda và collector có an toàn khi phân vùng?
        |-- Không --> Bỏ trạng thái chia sẻ, sửa combiner
        |
        v
Có oracle độc lập + bộ ca biên?
        |-- Không --> Bổ sung kiểm chứng
        |
        v
Sequential và parallel đều đạt tiêu chí?
        |-- Không --> Điều tra và sửa trước khi triển khai
        |
        v
Đo tốc độ với dữ liệu thật; chỉ giữ parallel nếu có lợi
~~~

Trong dự án học Java Stream API, đây là nơi liên hệ các chủ đề **reduce**, **collect**, grouping, collector tùy chỉnh, `Spliterator` và parallel stream: tất cả đều yêu cầu người viết hiểu **dữ liệu được chia, biến đổi và gộp lại như thế nào**.

## 17. Chẩn đoán khi kết quả parallel lệch

Khi gặp một khác biệt, đừng vội kết luận “Stream song song không đáng tin cậy”. Tách các khả năng theo thứ tự:

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Sequential và parallel lệch lớn | Accumulator/combiner khác nghĩa, side effect, race condition | Giảm bộ dữ liệu, kiểm tra identity và mỗi bước gộp |
| Hai cách bằng nhau nhưng tổng âm bất thường | Tràn `int`/`long` | Tính oracle `BigInteger` |
| Chỉ lệch ở chữ số cuối của `double` | Thứ tự cộng và làm tròn nhị phân | So với oracle và tolerance |
| Tiền lệch vài xu khi chia nhiều phân vùng | Làm tròn trong mỗi bước `add`/`reduce` | Tổng hợp chính xác rồi làm tròn theo quy tắc |
| Trung bình lệch khi nhóm có kích thước khác nhau | Lấy trung bình các trung bình không có trọng số | Gộp `sum` và `count` |
| Thiếu dữ liệu ở Map theo nhóm | Combiner sai hoặc collector trạng thái chia sẻ | Kiểm tra mỗi khóa và tổng toàn cục |
| Test có lúc đúng lúc sai | Race condition hoặc trạng thái thay đổi | Dùng dữ liệu bất biến, lặp với seed/kích thước đa dạng |
| Lỗi chỉ xuất hiện với nguồn tệp | Vòng đời nguồn, concurrent I/O, ngoại lệ đọc | Quản lý tài nguyên và đường đi dữ liệu |
| Parallel chậm hơn | Overhead chia/gộp lớn hơn công việc hữu ích | Benchmark khi đã đúng; xét cỡ dữ liệu |

Nếu kết quả chỉ lệch vài ULP, không tự bỏ qua sai lệch mà chưa đọc yêu cầu của hệ thống. Với điểm số thống kê, một sai số nhỏ có thể chấp nhận được. Với kế toán hoặc tính quyền lợi người dùng, từng đơn vị tiền có thể là bắt buộc.

## 18. Bài tập củng cố (kèm đáp án)

### Bài 1. Xác định điều kiện sai

~~~java
import java.util.List;

List<Integer> nums = List.of(2, 3, 5);

int result = nums.parallelStream()
        .reduce(1, Integer::sum);
~~~

**Câu hỏi:** Vì sao không thể dùng `1` làm identity cho phép cộng?

**Đáp án:** Identity cộng phải là `0`. `1` được cộng thêm vào mỗi tổng của phân vùng và có thể làm kết quả sai phụ thuộc cách chia; thay bằng `reduce(0, Integer::sum)`.

### Bài 2. Vì sao hai cách tính double có thể khác?

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c);
System.out.println(a + (b + c));
~~~

**Đáp án:** In `1.0` và `0.0`. Cộng `double` làm tròn tại từng bước, nên không bảo đảm tính kết hợp. Trong `parallel().reduce`, cách nhóm phần tử có thể khác và phải kiểm tra sai số theo mục tiêu nghiệp vụ.

### Bài 3. Tránh overflow trước khi cộng

**Đề:** Tính tổng của `List.of(1_500_000_000, 1_500_000_000)` mà không tràn `int`.

**Đáp án tham khảo:**

~~~java
import java.util.List;

List<Integer> values = List.of(1_500_000_000, 1_500_000_000);

long result = values.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(result); // 3000000000
~~~

Nếu tổng có thể vượt `long`, cần `BigInteger`.

### Bài 4. Phân tích MathContext

**Đề:** Vì sao `reduce(BigDecimal.ZERO, (a,b) -> a.add(b, mc))` có thể cho kết quả khác nhau giữa các cách nhóm?

**Đáp án:** `add(b, mc)` làm tròn ở từng bước, nên phép gộp mất tính kết hợp. Nếu nghiệp vụ cho phép, tổng hợp bằng `BigDecimal::add` chính xác trước rồi làm tròn một lần ở cuối. Nếu phải làm tròn từng giao dịch, chuyển các giá trị đầu vào thành số tiền giao dịch đã làm tròn rồi cộng chính xác.

### Bài 5. Chọn tiêu chí so sánh

**Đề:** Một pipeline xử lý số thực có oracle `0.0`, kết quả song song `2e-10` và ngưỡng sai số tuyệt đối đã được xác định là `1e-9`. Có đạt không?

**Đáp án:** Đạt theo ngưỡng sai số tuyệt đối vì `2e-10 <= 1e-9`, nếu cả hai giá trị hữu hạn và đó là ngưỡng nghiệp vụ được chấp thuận. Không thể kết luận như vậy nếu bài toán yêu cầu **chính xác tuyệt đối**.

### Bài 6. Tìm data race

~~~java
import java.util.stream.IntStream;

int[] sum = {0};

IntStream.rangeClosed(1, 100_000)
        .parallel()
        .forEach(n -> sum[0] += n);
~~~

**Đáp án:** `sum[0] += n` không nguyên tử và nhiều thread ghi chung vào một mảng. Đồng thời, tổng đúng là `5_000_050_000`, vượt phạm vi `int`. Sửa bằng:

~~~java
long result = IntStream.rangeClosed(1, 100_000)
        .parallel()
        .asLongStream()
        .sum();

System.out.println(result); // 5000050000
~~~

### Bài 7. Không lấy trung bình các trung bình

**Đề:** Hai phân vùng có số `[10, 20]` và `[100]`. Tính trung bình chung.

**Đáp án:** Tổng là `130`, số lượng là `3`, trung bình chính xác là `130 / 3`. Không lấy `(15 + 100) / 2` vì mỗi trung bình đại diện cho lượng phần tử khác nhau. Trong pipeline song song, gộp tổng và số đếm trước rồi chia ở cuối.

### Bài 8. Oracle nào phù hợp với tiền tệ?

**Đề:** Giá trị đầu vào là chuỗi `"0.10"`, `"0.20"`, `"0.30"` và yêu cầu tổng chính xác hai chữ số thập phân. Có nên dùng `double` làm oracle không?

**Đáp án:** Không nên nếu yêu cầu là phép cộng thập phân chính xác. Dùng `BigDecimal(String)` để tạo giá trị chuẩn và `BigDecimal::add` không làm tròn trung gian, rồi kiểm tra giá trị bằng `compareTo` hoặc chuẩn hóa scale theo hợp đồng.

### Bài 9. Kết quả bằng nhau đã đủ chưa?

**Đề:** Pipeline tuần tự và song song đều trả `-1294967296` cho hai giá trị `1_500_000_000`. Test so sánh bằng nhau có thể coi là PASS không?

**Đáp án:** Không. Hai cách đã cùng gặp overflow `int`. Oracle số nguyên toán học cho biết tổng phải là `3_000_000_000`. Cần nâng kiểu trước khi cộng hoặc dùng `BigInteger`.

### Bài 10. Chọn phép thử cho groupingBy

**Đề:** Dữ liệu phân loại `BOOK: +100`, `PEN: +40`, `BOOK: -20`, `PEN: +60` được gộp song song. Cần kiểm tra gì?

**Đáp án:** Map kết quả phải có đúng hai khóa, `BOOK = 80`, `PEN = 100`; tổng qua tất cả nhóm phải là `180`. Không nên so sánh thứ tự key được in ra khi không có bảo đảm về thứ tự của Map.

---

**Ghi nhớ:** Trước khi chuyển một phép tổng hợp số sang Stream song song, phải kiểm tra **identity, associativity, compatibility, miền số, quy tắc làm tròn và trạng thái chia sẻ**. Kết quả tuần tự bằng kết quả song song **không đủ** để chứng minh tính đúng: hãy đối chiếu cả hai với oracle độc lập, thử ca tràn/triệt tiêu/phân vùng và dùng tolerance có căn cứ cho số thực. Chỉ đánh giá tăng tốc sau khi đã xác nhận hợp đồng số học và yêu cầu nghiệp vụ được giữ nguyên.

