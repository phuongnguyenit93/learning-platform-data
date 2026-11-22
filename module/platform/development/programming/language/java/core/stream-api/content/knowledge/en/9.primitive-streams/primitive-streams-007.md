# Chuyển kiểu bằng `asLongStream` và `asDoubleStream`

## 1. Mục tiêu bài học

Trong module **`JAVA_STREAM_API`**, ta xử lý dữ liệu theo pipeline khai báo: lấy nguồn, ghép các thao tác trung gian lazy như `filter` và `map`, rồi kết thúc bằng `reduce` hoặc `collect`. Khi xử lý số, Java Stream API có ba kiểu stream chuyên biệt cho giá trị nguyên thủy:

- `IntStream` chứa các phần tử `int`.
- `LongStream` chứa các phần tử `long`.
- `DoubleStream` chứa các phần tử `double`.

Đôi khi một pipeline đang dùng `IntStream` nhưng phép tính sau đó cần miền giá trị `long`, hoặc một pipeline dùng `LongStream` cần tạo kết quả số thực `double`. Hai phương thức **`asLongStream()`** và **`asDoubleStream()`** hỗ trợ *mở rộng kiểu số nguyên thủy* (primitive widening) ngay trên stream.

Sau bài này, bạn có thể:

1. Xác định phương thức chuyển đổi nào có trên `IntStream` và `LongStream`.
2. Đọc kiểu của pipeline trước và sau `asLongStream()` hoặc `asDoubleStream()`.
3. Giải thích vì sao các phép chuyển này là thao tác trung gian lazy và không cần boxing thành wrapper.
4. Đặt phép chuyển kiểu đúng vị trí để tránh tràn số `int` trước khi tính toán.
5. Nhận diện rủi ro mất độ chính xác khi chuyển `long` sang `double`.
6. Chọn giữa `asLongStream`, `asDoubleStream`, `mapToLong`, `mapToDouble` và `boxed` theo mục tiêu xử lý.

Bài thuộc chương **Stream kiểu nguyên thủy**. Các nguyên tắc về kiểu, trạng thái, tài nguyên và hiệu năng ở đây cũng là nền tảng để xử lý stream lớn hoặc song song; chúng không thay thế cho phép đo hiệu năng trên chương trình thực tế.

## 2. Ba phương thức mở rộng kiểu cần nhớ

Các phương thức sau có từ **Java 8**:

```java
// Phương thức trên IntStream
LongStream asLongStream();
DoubleStream asDoubleStream();

// Phương thức trên LongStream
DoubleStream asDoubleStream();
```

Bảng chuyển đổi:

| Nguồn | Phương thức | Đích | Chuyển đổi từng phần tử |
| --- | --- | --- | --- |
| `IntStream` | `asLongStream()` | `LongStream` | `int` → `long` |
| `IntStream` | `asDoubleStream()` | `DoubleStream` | `int` → `double` |
| `LongStream` | `asDoubleStream()` | `DoubleStream` | `long` → `double` |

Không có `LongStream.asLongStream()` vì đã là `long`. `DoubleStream` cũng không có `asLongStream()` hoặc `asIntStream()`: chuyển `double` về số nguyên là phép **thu hẹp kiểu** (narrowing), có thể làm mất phần thập phân hoặc vượt miền giá trị. Nếu thật sự cần chuyển ngược, hãy thiết kế phép biến đổi và quy tắc làm tròn/kiểm tra riêng.

Mỗi phép trên giữ nguyên **số phần tử** và **thứ tự gặp phần tử** của nguồn có thứ tự; chỉ thay kiểu biểu diễn số. Chúng là **intermediate operations**: tạo một stream mới, chưa tự tiêu thụ nguồn.

Mô hình:

```text
IntStream
   │ asLongStream()
   ├────────────────────────────► LongStream
   │                                  │
   │                                  └── asDoubleStream()
   │                                              │
   │ asDoubleStream()                              ▼
   └───────────────────────────────────────► DoubleStream
```

## 3. Ví dụ đầu tiên: từ `int` sang `long`

Hãy tính tổng số lượng giao dịch của ba chi nhánh. Mỗi chi nhánh lưu số lượng bằng `int`, nhưng tổng có thể vượt phạm vi `int`:

```java
import java.util.stream.IntStream;

public class TongGiaoDich {
    public static void main(String[] args) {
        long tong = IntStream.of(
                1_500_000_000,
                1_500_000_000,
                100
            )
            .asLongStream()
            .sum();

        System.out.println(tong); // 3000000100
    }
}
```

Đọc theo kiểu dữ liệu:

```text
IntStream.of(...)    → IntStream
.asLongStream()      → LongStream
.sum()               → long
```

Phép chuyển `asLongStream()` nâng từng phần tử `int` thành `long` **trước khi** `LongStream.sum()` thực hiện cộng. Nhờ vậy tổng `3_000_000_100` nằm trong miền `long`.

Nếu bỏ `asLongStream()`:

```java
int tongSai = IntStream.of(
        1_500_000_000, 1_500_000_000, 100
    )
    .sum();

System.out.println(tongSai); // -1294967196 (tràn int)
```

`IntStream.sum()` trả về `int`, nên có nguy cơ tràn số. **`LongStream.sum()` cũng có thể tràn `long`** nếu tổng thực vượt miền `long`; chuyển kiểu chỉ mở rộng giới hạn, không loại bỏ mọi rủi ro. Với tổng cực lớn hoặc yêu cầu độ chính xác tuyệt đối vượt `long`, cân nhắc `BigInteger` và một thuật toán/collector phù hợp.

### Vì sao không dùng `boxed()`?

Một cách khác là chuyển `IntStream` thành `Stream<Integer>`:

```java
IntStream.of(1, 2, 3)
    .boxed(); // Stream<Integer>
```

Nhưng `boxed()` biến mỗi phần tử nguyên thủy thành đối tượng wrapper `Integer`; nó **không** tạo `LongStream`. Khi chỉ cần phép tính số nguyên thủy trên `long`, `asLongStream()` diễn đạt mục tiêu rõ ràng hơn và tránh boxing không cần thiết.

## 4. Từ `int` sang `double` với `asDoubleStream()`

Dùng `asDoubleStream()` khi muốn làm việc với các giá trị `int` theo API của `DoubleStream`:

```java
import java.util.stream.IntStream;

public class PhanTram {
    public static void main(String[] args) {
        double[] tyLe = IntStream.of(15, 20, 35)
            .asDoubleStream()
            .map(n -> n / 100.0)
            .toArray();

        System.out.println(java.util.Arrays.toString(tyLe));
        // [0.15, 0.2, 0.35]
    }
}
```

Kiểu thay đổi qua từng bước:

| Bước | Kiểu stream | Kết quả |
| --- | --- | --- |
| `IntStream.of(15, 20, 35)` | `IntStream` | `15`, `20`, `35` |
| `.asDoubleStream()` | `DoubleStream` | `15.0`, `20.0`, `35.0` |
| `.map(n -> n / 100.0)` | `DoubleStream` | `0.15`, `0.2`, `0.35` |
| `.toArray()` | — | `double[]` |

Về mặt số học, **mọi giá trị `int` đều có thể biểu diễn chính xác bằng `double`** vì `double` có đủ chữ số có nghĩa cho toàn bộ miền 32-bit của `int`. Tuy nhiên, phép chia, nhân hoặc các phép tính `double` tiếp theo có thể sinh sai số dấu phẩy động; ví dụ `0.1` không có biểu diễn nhị phân hữu hạn chính xác.

### Ví dụ: trung bình

```java
import java.util.OptionalDouble;
import java.util.stream.IntStream;

OptionalDouble trungBinh = IntStream.of(6, 7, 9)
    .asDoubleStream()
    .average();

System.out.println(trungBinh.getAsDouble());
```

Giá trị được in gần `7.333333333333333`. `average()` trả về `OptionalDouble` vì stream có thể rỗng. Trong thực tế có thể viết an toàn:

```java
double trungBinh = IntStream.of(6, 7, 9)
    .asDoubleStream()
    .average()
    .orElse(0.0);
```

**Không bắt buộc dùng `asDoubleStream()` chỉ để tính trung bình**: bản thân `IntStream.average()` đã trả `OptionalDouble`. Phép chuyển phát huy giá trị khi cần tiếp tục dùng các thao tác nhận hoặc trả `double`.

## 5. Từ `long` sang `double`: chú ý mất độ chính xác

`LongStream.asDoubleStream()` mở rộng kiểu nguyên thủy `long` thành `double`:

```java
import java.util.Arrays;
import java.util.stream.LongStream;

public class LongSangDouble {
    public static void main(String[] args) {
        double[] giaTri = LongStream.of(2L, 4L, 8L)
            .asDoubleStream()
            .toArray();

        System.out.println(Arrays.toString(giaTri));
        // [2.0, 4.0, 8.0]
    }
}
```

Với các giá trị nhỏ, kết quả dễ quan sát. Nhưng **không phải mọi `long` đều biểu diễn chính xác được bằng `double`**.

`long` là số nguyên có dấu 64-bit. `double` là số thực nhị phân 64-bit với **53 bit độ chính xác có nghĩa** (bao gồm bit ẩn). Vì vậy, mọi số nguyên từ `-(2^53)` đến `2^53` đều có thể biểu diễn chính xác; ngoài khoảng này, một số số nguyên vẫn biểu diễn được nhưng không phải tất cả.

Ví dụ:

```java
import java.util.Arrays;
import java.util.stream.LongStream;

public class MatDoChinhXac {
    public static void main(String[] args) {
        long a = 9_007_199_254_740_992L; // 2^53
        long b = 9_007_199_254_740_993L; // 2^53 + 1

        double[] ketQua = LongStream.of(a, b)
            .asDoubleStream()
            .toArray();

        System.out.println(Arrays.toString(ketQua));
        // [9.007199254740992E15, 9.007199254740992E15]

        System.out.println(ketQua[0] == ketQua[1]); // true
    }
}
```

Hai giá trị `long` **khác nhau** nhưng trở thành cùng một giá trị `double` do làm tròn khi chuyển kiểu. Nếu dùng kết quả để so sánh mã định danh, đếm chính xác, phân biệt giao dịch hoặc tính tiền, lỗi logic có thể xảy ra mà trình biên dịch không báo.

**Quy tắc lựa chọn:** giữ `LongStream` và phép tính `long` khi cần chính xác số nguyên trong miền `long`. Với nghiệp vụ tiền tệ hoặc số nguyên cực lớn cần độ chính xác, cân nhắc `BigDecimal`/`BigInteger` phù hợp. Dùng `DoubleStream` khi mô hình toán học chấp nhận sai số số thực, chẳng hạn phép đo cảm biến, thống kê xấp xỉ hoặc tính tỷ lệ.

### Có gây tràn thành vô cực không?

Khi chuyển một giá trị `long` hữu hạn thành `double`, giá trị tuyệt đối lớn nhất của `long` vẫn nhỏ hơn nhiều so với giới hạn độ lớn của `double`. Do đó bản thân phép chuyển `long` → `double` **không tạo `Infinity` chỉ vì số quá lớn**; rủi ro trực tiếp là **mất độ chính xác nguyên**. Các phép toán `double` sau đó vẫn có thể tràn, sinh `Infinity` hoặc `NaN` tùy dữ liệu.

## 6. `asLongStream` và `asDoubleStream` đều lazy

Hai phép chuyển là **thao tác trung gian**. Việc viết chúng chưa duyệt nguồn; pipeline chỉ được thực thi khi terminal operation cần kết quả.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

IntStream nguon = IntStream.rangeClosed(1, 5);

LongStream chuyenKieu = nguon.asLongStream(); // Chưa thu dữ liệu.

List<Long> ketQua = chuyenKieu
    .map(n -> n * n)
    .boxed()
    .collect(Collectors.toList());

System.out.println(ketQua); // [1, 4, 9, 16, 25]
```

> Đoạn mã trên cần `import java.util.stream.LongStream;` nếu được đặt trong một lớp Java độc lập có khai báo biến `LongStream`.

Giải thích:

- `IntStream.rangeClosed(1, 5)` sinh các số nguyên từ 1 đến 5.
- `asLongStream()` chuyển từng số sang `long` khi cần xử lý.
- `map(n -> n * n)` thực hiện phép nhân trên `long`.
- `boxed()` chuyển `LongStream` thành `Stream<Long>`, cần thiết ở đây để thu `List<Long>` bằng `Collectors.toList()`.
- `collect` là thao tác kết thúc, yêu cầu tạo kết quả.

Các thao tác chuyển kiểu không làm thay đổi số phần tử nên vẫn kết hợp được với `filter`, `limit`, `skip`, `sum`, `average` và `reduce`. Cần nhớ: **stream chỉ được tiêu thụ một lần**, không lấy lại `nguon` để chạy một terminal operation khác sau khi `chuyenKieu` đã được tiêu thụ.

### Nguồn vô hạn vẫn cần điểm dừng

```java
long tong = IntStream.iterate(1, n -> n + 1)
    .limit(5)
    .asLongStream()
    .sum();

System.out.println(tong); // 15
```

`asLongStream()` không tự tạo điểm dừng. Nếu dùng nguồn vô hạn rồi gọi `sum()` hoặc `toArray()` mà không giới hạn hợp lý, phép toán kết thúc có thể không bao giờ hoàn thành.

## 7. Vị trí chuyển kiểu quyết định có bị tràn số hay không

Một lỗi rất phổ biến là **chuyển kiểu sau khi phép toán `int` đã bị tràn**. Khi đó, chuyển sang `long` không thể khôi phục kết quả đúng ban đầu.

Ví dụ tính bình phương của 50.000:

```java
import java.util.stream.IntStream;

// SAI về kết quả: n * n tính bằng int, đã tràn trước khi mở rộng.
long sai = IntStream.of(50_000)
    .map(n -> n * n)
    .asLongStream()
    .sum();

System.out.println(sai); // -1794967296
```

`50_000 × 50_000 = 2_500_000_000`, vượt `Integer.MAX_VALUE = 2_147_483_647`. Cần chuyển sang `long` **trước khi nhân**:

```java
long dung = IntStream.of(50_000)
    .asLongStream()
    .map(n -> n * n)
    .sum();

System.out.println(dung); // 2500000000
```

Hai pipeline có vẻ chỉ khác vị trí `asLongStream()`, nhưng **ngữ nghĩa phép nhân đã khác**:

```text
SAI:  int * int (có thể tràn) → kết quả int → chuyển sang long
ĐÚNG: int → long → long * long → kết quả long
```

Nếu chỉ có một phép tính cụ thể, có thể mở rộng toán hạng ngay trong lambda:

```java
long cungDung = IntStream.of(50_000)
    .mapToLong(n -> (long) n * n)
    .sum();

System.out.println(cungDung); // 2500000000
```

Ở đây phép ép kiểu `(long) n` xảy ra **trước phép nhân**, nên phép nhân được thực hiện với `long`.

Một lưu ý nữa: `asLongStream()` không sửa mọi lỗi toán học. Nếu một phép tính vẫn có thể vượt `Long.MAX_VALUE`, cần thiết kế miền giá trị, dùng `Math.multiplyExact` để phát hiện tràn, hoặc sử dụng `BigInteger` nếu yêu cầu.

## 8. Phân biệt `asLongStream` / `asDoubleStream` và `mapToLong` / `mapToDouble`

Tất cả đều giúp tạo primitive stream với kiểu đích mong muốn, nhưng mục đích khác nhau:

- **`asLongStream()`, `asDoubleStream()`**: chuyển kiểu từng phần tử **mà không thực hiện công thức biến đổi giá trị ngoài quy tắc chuyển kiểu nguyên thủy của Java**.
- **`mapToLong(mapper)`, `mapToDouble(mapper)`**: thực hiện **một hàm biến đổi** để tạo giá trị kiểu `long` hoặc `double`.

Ví dụ:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

long[] a = IntStream.of(2, 4, 6)
    .asLongStream()
    .toArray();               // [2L, 4L, 6L]

long[] b = IntStream.of(2, 4, 6)
    .mapToLong(n -> n * 100L)
    .toArray();               // [200L, 400L, 600L]

double[] c = IntStream.of(2, 4, 6)
    .asDoubleStream()
    .toArray();               // [2.0, 4.0, 6.0]

double[] d = IntStream.of(2, 4, 6)
    .mapToDouble(n -> n / 10.0)
    .toArray();               // [0.2, 0.4, 0.6]

System.out.println(Arrays.toString(a));
System.out.println(Arrays.toString(b));
System.out.println(Arrays.toString(c));
System.out.println(Arrays.toString(d));
```

Lưu ý trong ví dụ `b`, `n * 100L` thực hiện phép nhân bằng `long` vì toán hạng `100L` là `long`; viết `n * 100` có thể tràn `int` trước khi được trả về dưới dạng `long`.

Cùng một yêu cầu có thể có hai cách viết:

```java
long tong1 = IntStream.of(50_000, 60_000)
    .asLongStream()
    .map(n -> n * n)
    .sum();

long tong2 = IntStream.of(50_000, 60_000)
    .mapToLong(n -> (long) n * n)
    .sum();

System.out.println(tong1); // 6100000000
System.out.println(tong2); // 6100000000
```

Cả hai hợp lệ vì phép nhân được đánh giá bằng `long`. Chọn cách truyền tải ý định dễ đọc hơn: chuyển cả pipeline sang `long` thì dùng `asLongStream`; tính ngay một giá trị `long` từ mỗi `int` thì `mapToLong` cũng phù hợp.

### Khi nguồn là `Stream<T>`

`asLongStream` và `asDoubleStream` **không tồn tại trên `Stream<T>`**. Nếu nguồn là danh sách đối tượng:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> so = Arrays.asList(2, 4, 6);

long tong = so.stream()         // Stream<Integer>
    .mapToInt(Integer::intValue) // IntStream
    .asLongStream()              // LongStream
    .sum();

System.out.println(tong); // 12
```

Có thể ngắn gọn hơn bằng `mapToLong` trực tiếp:

```java
long tong = so.stream()
    .mapToLong(Integer::longValue)
    .sum();
```

Nếu không cần thay đổi kiểu đầu ra, `mapToInt(Integer::intValue)` cũng là lựa chọn tốt cho các phép tính vừa miền `int`; việc mở rộng sang `long` chỉ nên xuất phát từ yêu cầu dữ liệu hoặc tính toán.

### API có sẵn sau khi chuyển

| Sau bước chuyển | Một số terminal operations thường dùng |
| --- | --- |
| `LongStream` | `sum()` → `long`, `average()` → `OptionalDouble`, `toArray()` → `long[]`, `max()` → `OptionalLong` |
| `DoubleStream` | `sum()` → `double`, `average()` → `OptionalDouble`, `toArray()` → `double[]`, `max()` → `OptionalDouble` |

`OptionalLong`, `OptionalDouble` biểu diễn kết quả có thể thiếu (ví dụ stream rỗng). Tránh gọi `getAsLong()` hoặc `getAsDouble()` nếu chưa bảo đảm có giá trị; có thể dùng `orElse` hoặc `orElseThrow` tùy bài toán.

## 9. So sánh chi phí chuyển kiểu và boxing

Các thao tác `asLongStream` và `asDoubleStream` chuyển primitive sang primitive. Về mặt API, chúng **không cần tạo một đối tượng wrapper cho mỗi phần tử** như khi gọi `boxed()`. Điều này có thể giảm overhead khi xử lý số lượng dữ liệu lớn.

Tuy nhiên, không nên suy ra rằng một pipeline dùng `asDoubleStream()` luôn nhanh hơn mọi cách khác: tốc độ còn phụ thuộc nguồn, JIT, số lần cấp phát, truy cập bộ nhớ, phép toán trung gian và cách sử dụng stream. Chỉ nên kết luận về hiệu năng sau khi đo với dữ liệu và môi trường phù hợp.

| Phép chuyển | Kiểu đầu ra | Boxing từng phần tử? | Dùng khi |
| --- | --- | --- | --- |
| `IntStream.asLongStream()` | `LongStream` | Không | Muốn miền `long` mà vẫn xử lý primitive |
| `IntStream.asDoubleStream()` | `DoubleStream` | Không | Muốn xử lý `double` từ số nguyên |
| `LongStream.asDoubleStream()` | `DoubleStream` | Không | Muốn phép tính số thực từ `long`, chấp nhận rủi ro làm tròn |
| `IntStream.boxed()` | `Stream<Integer>` | Có | Cần stream đối tượng hoặc collector generic |
| `LongStream.boxed()` | `Stream<Long>` | Có | Cần `Long` hoặc API thao tác đối tượng |
| `DoubleStream.boxed()` | `Stream<Double>` | Có | Cần `Double` hoặc API thao tác đối tượng |

Nếu chỉ cần một giá trị tổng hợp, thường không cần `boxed()`:

```java
long tong = IntStream.rangeClosed(1, 100)
    .asLongStream()
    .sum();

System.out.println(tong); // 5050
```

Nếu cần `List<Long>` để lưu kết quả, boxing ở ranh giới cuối pipeline là hợp lý:

```java
import java.util.List;
import java.util.stream.Collectors;

List<Long> ds = IntStream.rangeClosed(1, 3)
    .asLongStream()
    .boxed()
    .collect(Collectors.toList());

// [1L, 2L, 3L] — các phần tử có kiểu Long
```

Từ Java 16, `Stream.toList()` có thể thay `collect(Collectors.toList())` trong các tình huống phù hợp, nhưng `Stream.toList()` trả về danh sách không cho phép sửa. Việc chọn collector vẫn phụ thuộc cách sử dụng kết quả.

## 10. Lỗi thường gặp và cách khắc phục

| Lỗi / hiểu nhầm | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Gọi `asLongStream()` trên `LongStream` | `LongStream` đã là luồng `long`, không có phương thức đó | Giữ nguyên stream, hoặc dùng `map` nếu cần biến đổi |
| Gọi `asDoubleStream()` trên `Stream<Integer>` | Phương thức chỉ có ở primitive stream thích hợp | Dùng `mapToDouble(Integer::doubleValue)` hoặc `mapToInt(...).asDoubleStream()` |
| Gọi `asLongStream()` trên `DoubleStream` | Không có API thu hẹp kiểu như vậy | Dùng `mapToLong` với quy tắc chuyển đổi/kiểm tra rõ ràng |
| `IntStream.map(n -> n*n).asLongStream()` vẫn cho số sai | Phép nhân `int` tràn trước khi chuyển | Chuyển trước với `asLongStream().map(...)` hoặc `mapToLong(n -> (long)n*n)` |
| Chuyển mọi `long` sang `double` rồi so sánh bằng nhau | `double` không biểu diễn chính xác mọi số nguyên 64-bit | Giữ `long` nếu cần phân biệt chính xác |
| Cho rằng `asDoubleStream()` tự chia hoặc chuẩn hóa giá trị | Phép chuyển chỉ đổi kiểu | Thêm `map(n -> ...)` nếu cần công thức nghiệp vụ |
| Dùng `boxed()` để đổi `int` sang `long` | `boxed()` tạo `Integer`, không tạo `LongStream` | Dùng `asLongStream()` |
| Cố dùng lại stream nguồn sau khi tiêu thụ stream đích | Pipeline đã tiêu thụ nguồn | Tạo stream mới |
| `sum()` trên nguồn vô hạn không trả kết quả | Không có điểm dừng | Thêm `limit` hoặc giới hạn nguồn |
| Dùng số thực để cộng/trừ tiền chính xác | `double` có sai số nhị phân | Chọn biểu diễn số nguyên hoặc `BigDecimal` theo yêu cầu |

Ví dụ lỗi biên dịch do sai loại stream:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> so = Arrays.asList(1, 2, 3);

// KHÔNG BIÊN DỊCH: Stream<Integer> không có asLongStream().
// long tongSai = so.stream().asLongStream().sum();

// ĐÚNG:
long tongDung = so.stream()
    .mapToLong(Integer::longValue)
    .sum();
```

Đừng bỏ qua phần kiểu ở giữa pipeline: `Stream<Integer>` và `IntStream` có nhiều phương thức khác nhau dù cùng diễn đạt dãy các số nguyên.

## 11. Bài tập thực hành

### Bài 1 — Chọn đúng phép chuyển

Cho dữ liệu:

```java
int[] soLuong = {1_000_000_000, 1_000_000_000, 1_000_000_000};
```

Hãy tính tổng chính xác bằng `long` với `IntStream` và `asLongStream()`. Giải thích vì sao `IntStream.sum()` không phù hợp.

### Bài 2 — Dự đoán kiểu và kết quả

```java
double[] kq = IntStream.of(10, 20, 30)
    .asDoubleStream()
    .map(n -> n / 2)
    .toArray();
```

Mỗi bước có kiểu gì? Mảng `kq` chứa giá trị nào?

### Bài 3 — Phát hiện tràn trước khi chuyển kiểu

```java
long x = IntStream.of(50_000)
    .map(n -> n * n)
    .asLongStream()
    .sum();
```

Đoạn mã có kết quả `2_500_000_000L` không? Sửa ít nhất hai cách.

### Bài 4 — Mất độ chính xác khi dùng `double`

```java
long a = 9_007_199_254_740_992L;
long b = 9_007_199_254_740_993L;

double[] values = LongStream.of(a, b)
    .asDoubleStream()
    .toArray();
```

Dự đoán `values[0] == values[1]` và giải thích. Có nên dùng `DoubleStream` để xác định hai mã định danh `long` có bằng nhau không?

### Bài 5 — Chọn API theo mục tiêu

Nguồn là `List<Integer>` chứa số lượt xem của nhiều bài viết. Bạn muốn tính tổng bằng `long`, rồi xuất một danh sách `List<Long>` gồm từng số lượt xem đã chuyển kiểu. Viết hai pipeline **độc lập** từ cùng một danh sách nguồn; giải thích vì sao không được dùng lại một stream đã gọi `sum()`.

<details>
<summary>Đáp án tham khảo</summary>

**Bài 1**

```java
long tong = java.util.Arrays.stream(soLuong)
    .asLongStream()
    .sum();

System.out.println(tong); // 3000000000
```

`IntStream.sum()` trả `int`, nhỏ hơn tổng thực; `asLongStream()` đưa từng phần tử thành `long` trước khi cộng.

**Bài 2**

`IntStream` → `DoubleStream` → `DoubleStream` → `double[]`. Kết quả là `[5.0, 10.0, 15.0]`. Biến `n` trong `map` có kiểu `double` vì đã gọi `asDoubleStream()`.

**Bài 3**

Không. Phép nhân bằng `int` đã tràn. Hai cách sửa:

```java
long cach1 = IntStream.of(50_000)
    .asLongStream()
    .map(n -> n * n)
    .sum();

long cach2 = IntStream.of(50_000)
    .mapToLong(n -> (long) n * n)
    .sum();

// Cả hai đều bằng 2500000000
```

**Bài 4**

Biểu thức so sánh trả về `true` vì `2^53 + 1` không biểu diễn chính xác được bằng `double` và được làm tròn về cùng giá trị với `2^53`. Không dùng chuyển đổi sang `double` để kiểm tra tính bằng nhau của mã định danh `long`.

**Bài 5**

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> luotXem = Arrays.asList(10, 20, 30);

long tong = luotXem.stream()
    .mapToLong(Integer::longValue)
    .sum();

List<Long> duLieuLong = luotXem.stream()
    .mapToInt(Integer::intValue)
    .asLongStream()
    .boxed()
    .collect(Collectors.toList());

System.out.println(tong);         // 60
System.out.println(duLieuLong);   // [10, 20, 30]
```

Mỗi lời gọi `luotXem.stream()` tạo một stream mới. Một stream đã bị tiêu thụ bởi terminal operation `sum()` không được sử dụng tiếp để tạo danh sách.

</details>

## 12. Ghi nhớ

Ba phép mở rộng kiểu số nguyên thủy cốt lõi là:

```java
IntStream  --asLongStream()-->   LongStream
IntStream  --asDoubleStream()--> DoubleStream
LongStream --asDoubleStream()--> DoubleStream
```

- Các phép chuyển là **intermediate operations lazy**, giữ nguyên số lượng phần tử và không cần boxing.
- Chuyển `int` → `long` và `int` → `double` bảo toàn giá trị số nguyên chính xác; chuyển `long` → `double` có thể làm tròn.
- Nếu phép tính trung gian có thể tràn `int`, hãy **mở rộng kiểu trước khi tính**.
- Dùng `mapToLong` / `mapToDouble` khi cần *công thức biến đổi*, dùng `asLongStream` / `asDoubleStream` khi chỉ cần *chuyển kiểu*.
- Chọn kiểu dữ liệu theo miền giá trị và yêu cầu độ chính xác; không dùng `double` cho dữ liệu số nguyên hoặc tiền tệ cần chính xác tuyệt đối.

Nắm được vị trí và giới hạn của các phép chuyển giúp viết pipeline `filter`, `map`, `reduce` và các phép tổng hợp dữ liệu rõ ràng, đáng tin cậy hơn khi xử lý Stream API.
