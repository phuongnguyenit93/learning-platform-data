# Tạo dãy bằng `Stream.iterate` với hàm chuyển trạng thái

## 1. Mục tiêu bài học

Trong module **`JAVA_STREAM_API`**, Stream API được dùng để xử lý dữ liệu theo cách khai báo: tạo nguồn, ghép các phép biến đổi như `filter`, `map`, `reduce`, rồi thu kết quả bằng `collect`. Không phải mọi nguồn dữ liệu đều là `List` hoặc mảng có sẵn. Có những bài toán cần **tự sinh một dãy** theo quy luật:

- Dãy số tự nhiên: 0, 1, 2, 3, ...
- Dãy lũy thừa của 2: 1, 2, 4, 8, 16, ...
- Các ngày kế tiếp nhau: hôm nay, ngày mai, ngày kia, ...
- Dãy Fibonacci: 0, 1, 1, 2, 3, 5, ...

`Stream.iterate` là cách tạo nguồn cho những dãy mà **phần tử tiếp theo được tính từ trạng thái hiện tại**. Phương pháp này thể hiện rõ quy tắc chuyển trạng thái và có thể tạo stream vô hạn mà không lưu sẵn toàn bộ phần tử trong bộ nhớ.

Sau bài học, bạn có thể:

1. Viết `Stream.iterate(seed, next)` để sinh dãy bằng một hàm chuyển trạng thái.
2. Dùng `limit` hoặc dạng `iterate(seed, hasNext, next)` để kiểm soát điểm dừng.
3. Giải thích tính lazy, thứ tự thực thi và sự khác nhau giữa trạng thái của dãy với kết quả do `map` tạo ra.
4. Sinh các dãy có trạng thái phức hợp bằng đối tượng bất biến.
5. Nhận diện những trường hợp dễ chạy mãi, tràn số hoặc kém hiệu quả.

Bài này nằm trong chương **Dãy số và Stream vô hạn**. Mẫu `iterate` còn giúp hiểu cách lập luận về trạng thái, tính thuần của hàm và giới hạn tài nguyên trước khi học các nội dung nâng cao như Spliterator, stream song song và Stream Gatherers.

## 2. Từ quy tắc truy hồi đến `Stream.iterate`

Một dãy được tạo từ hai yếu tố:

- **Giá trị ban đầu** (`seed`): phần tử đầu tiên.
- **Hàm chuyển trạng thái** (`next`): nhận trạng thái hiện tại và tính trạng thái kế tiếp.

Có thể mô tả:

```text
state[0] = seed
state[1] = next(state[0])
state[2] = next(state[1])
state[3] = next(state[2])
...
```

Ví dụ, với `seed = 1` và `next(n) = n * 2`, ta có:

```text
1 --×2--> 2 --×2--> 4 --×2--> 8 --×2--> 16 --×2--> 32 ...
```

Java cung cấp dạng `Stream.iterate` hai tham số từ **Java 8**:

```java
public static <T> Stream<T> iterate(T seed, UnaryOperator<T> f)
```

`UnaryOperator<T>` là functional interface biểu diễn phép biến đổi từ **`T` sang chính `T`**. Hàm `next` vì vậy giữ nguyên kiểu của trạng thái, dù giá trị thay đổi.

### Ví dụ hoàn chỉnh: sáu lũy thừa đầu tiên của 2

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class DayLuyThuaHai {
    public static void main(String[] args) {
        List<Integer> ketQua = Stream.iterate(1, n -> n * 2)
            .limit(6)
            .collect(Collectors.toList());

        System.out.println(ketQua);
    }
}
```

Kết quả:

```text
[1, 2, 4, 8, 16, 32]
```

Đọc từng phần:

| Biểu thức | Ý nghĩa | Kiểu kết quả |
| --- | --- | --- |
| `Stream.iterate(1, n -> n * 2)` | Bắt đầu từ 1; nhân đôi để sinh số tiếp theo | `Stream<Integer>` |
| `.limit(6)` | Chỉ lấy tối đa sáu phần tử đầu | `Stream<Integer>` |
| `.collect(Collectors.toList())` | Kích hoạt pipeline, đưa phần tử vào danh sách | `List<Integer>` |

Dạng hai tham số tự nó sinh **dãy không có điểm dừng xác định**. Chính `limit(6)` giúp chương trình chỉ cần sáu phần tử; không có danh sách vô hạn nào được cấp phát trước.

## 3. Phân biệt hàm chuyển trạng thái với `map`

Hai phép toán dễ bị nhầm vì đều nhận một hàm:

- Trong `iterate(seed, next)`, `next` quyết định **trạng thái dùng để sinh phần tử kế tiếp**.
- Trong `map(mapper)`, `mapper` **chuyển đổi giá trị đầu ra** của từng phần tử; thông thường nó không quyết định phần tử nguồn tiếp theo là gì.

Xét pipeline:

```java
List<Integer> ketQua = Stream.iterate(1, n -> n + 1)
    .map(n -> n * n)
    .limit(5)
    .collect(Collectors.toList());

System.out.println(ketQua); // [1, 4, 9, 16, 25]
```

`iterate` sinh các trạng thái 1, 2, 3, 4, 5, ...; `map` chỉ biến mỗi trạng thái thành bình phương của nó. **Trạng thái kế tiếp vẫn được tính bằng phép cộng 1**. Nếu thay bằng `Stream.iterate(1, n -> n * n)`, đó là dãy khác: bắt đầu từ 1 thì luôn giữ 1.

Một điểm quan trọng khác: `Stream.iterate` yêu cầu hàm chuyển trạng thái trả về cùng kiểu `T`; muốn chuyển kết quả từ số sang chuỗi, hãy thêm `map`:

```java
List<String> nhan = Stream.iterate(1, n -> n + 1)
    .limit(3)
    .map(n -> "Bước " + n)
    .collect(Collectors.toList());

System.out.println(nhan); // [Bước 1, Bước 2, Bước 3]
```

## 4. Tính lazy và điểm dừng khi sinh dãy vô hạn

Stream API đánh giá các phép xử lý theo nhu cầu. Việc gọi `Stream.iterate(...)`, `map(...)`, `filter(...)` hay `limit(...)` chỉ tạo pipeline. Các phần tử được sinh khi một **terminal operation** như `collect`, `forEach`, `count` hoặc `findFirst` cần tiêu thụ chúng.

Ví dụ:

```java
Stream<Integer> day = Stream.iterate(0, n -> n + 3)
    .limit(4);

// Tới đây chưa yêu cầu tính toàn bộ dãy.
List<Integer> ketQua = day.collect(Collectors.toList());

System.out.println(ketQua); // [0, 3, 6, 9]
```

`limit` là một phép toán trung gian **short-circuiting**: với nguồn có thể sinh vô hạn, nó cho phép terminal operation kết thúc khi đã nhận đủ phần tử được yêu cầu.

### Các phép kết thúc có hành vi khác nhau

| Pipeline trên dãy có thể vô hạn | Kết quả có điểm dừng? | Giải thích |
| --- | --- | --- |
| `iterate(...).limit(10).collect(toList())` | Có | Chỉ lấy mười phần tử đầu. |
| `iterate(...).findFirst()` | Có | Lấy phần tử đầu tiên nếu nguồn có phần tử. |
| `iterate(...).count()` | Không bảo đảm | Đếm toàn bộ phần tử của stream vô hạn sẽ không hoàn tất. |
| `iterate(...).collect(toList())` | Không | Thu hết một dãy vô hạn là yêu cầu không thể hoàn thành. |
| `iterate(...).sorted().limit(10).collect(toList())` | Không bảo đảm | `sorted` thường phải xét toàn bộ đầu vào trước khi xuất phần tử. |
| `iterate(...).limit(10).sorted().collect(toList())` | Có | Trước khi sắp xếp, nguồn đã bị giới hạn mười phần tử. |

**Chú ý thứ tự các phép toán.** Đặt `limit` trước một phép cần nhìn toàn bộ dữ liệu có thể biến pipeline đang chờ vô hạn thành pipeline hữu hạn. Tuy nhiên, `limit` cũng không phải lời bảo đảm tuyệt đối: nếu đặt sau một bộ lọc **không bao giờ cho ra đủ phần tử**, stream vẫn có thể chạy mãi.

### `filter` đặt trước hay sau `limit`?

```java
List<Integer> namSoChan = Stream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(5)
    .collect(Collectors.toList());

// [2, 4, 6, 8, 10]
```

Pipeline cần duyệt nhiều hơn năm trạng thái nguồn để nhận đủ năm số chẵn. Nếu đảo hai bước:

```java
List<Integer> soChanTrongNamSoDau = Stream.iterate(1, n -> n + 1)
    .limit(5)
    .filter(n -> n % 2 == 0)
    .collect(Collectors.toList());

// [2, 4]
```

Ý nghĩa nghiệp vụ đã khác: **lấy năm số chẵn đầu tiên** so với **lọc số chẵn trong năm số tự nhiên đầu tiên**.

## 5. Dạng ba tham số: sinh dãy đến khi điều kiện sai (Java 9+)

Từ **Java 9**, `Stream.iterate` có overload:

```java
public static <T> Stream<T> iterate(
    T seed,
    Predicate<? super T> hasNext,
    UnaryOperator<T> next
)
```

Các tham số:

- `seed`: trạng thái bắt đầu.
- `hasNext`: kiểm tra liệu **trạng thái đang xét** có được phát ra stream hay không.
- `next`: tạo trạng thái tiếp theo sau một trạng thái đã được chấp nhận.

Mô hình gần tương đương một vòng lặp `for`:

```java
for (int n = 1; n <= 5; n = n + 1) {
    System.out.println(n);
}
```

Viết theo Stream API:

```java
List<Integer> motDenNam = Stream.iterate(
        1,
        n -> n <= 5,
        n -> n + 1
    )
    .collect(Collectors.toList());

System.out.println(motDenNam); // [1, 2, 3, 4, 5]
```

Diễn tiến:

```text
seed = 1
hasNext(1) = true   → phát 1 → next(1) = 2
hasNext(2) = true   → phát 2 → next(2) = 3
hasNext(3) = true   → phát 3 → next(3) = 4
hasNext(4) = true   → phát 4 → next(4) = 5
hasNext(5) = true   → phát 5 → next(5) = 6
hasNext(6) = false  → dừng; không phát 6
```

**Phần tử đầu tiên cũng phải qua `hasNext`.** Nếu `hasNext(seed)` là `false`, stream rỗng:

```java
long soLuong = Stream.iterate(10, n -> n < 10, n -> n + 1)
    .count();

System.out.println(soLuong); // 0
```

Dạng ba tham số có thể tạo dãy **hữu hạn hoặc vô hạn** tùy điều kiện, ví dụ `n -> true` không tạo điểm dừng. Hai overload khác nhau ở cách thể hiện điều kiện kết thúc, không làm thay đổi quy tắc xử lý lazy của Stream.

### `limit` hay `hasNext`?

| Nhu cầu | Lựa chọn | Ví dụ |
| --- | --- | --- |
| Lấy đúng N trạng thái đầu tiên | Dạng hai tham số + `limit(N)` | Lấy 10 số đầu dãy Fibonacci |
| Dừng khi **trạng thái** đạt ngưỡng | Dạng ba tham số (Java 9+) | Sinh 1, 2, 4, 8, 16, 32 với điều kiện `n <= 32` |
| Dừng theo **giá trị đã đi qua pipeline** | Có thể dùng `takeWhile` (Java 9+) trên stream có thứ tự | Sinh số tăng dần rồi lấy khi `n < 100` |
| Sinh các chỉ số nguyên liên tiếp trong một khoảng | Cân nhắc `IntStream.range` / `rangeClosed` | Dãy chỉ số 0 đến 9 |

Ví dụ lũy thừa của 2 kết thúc theo ngưỡng:

```java
List<Integer> day = Stream.iterate(
        1,
        n -> n <= 32,
        n -> n * 2
    )
    .collect(Collectors.toList());

System.out.println(day); // [1, 2, 4, 8, 16, 32]
```

Ví dụ `takeWhile` tương đương cho dãy số tăng:

```java
List<Integer> nhoHonNam = Stream.iterate(1, n -> n + 1)
    .takeWhile(n -> n < 5)
    .collect(Collectors.toList());

// [1, 2, 3, 4] — Java 9+
```

Với stream **có thứ tự** như stream sinh bởi `iterate`, `takeWhile` lấy đoạn đầu liên tiếp còn thỏa điều kiện rồi dừng; nó không tương đương với `filter` khi các giá trị sau đó có thể lại thỏa điều kiện.

## 6. Ví dụ thực tế: sinh chuỗi ngày bằng `LocalDate`

Ngày tháng là một dạng trạng thái tự nhiên: biết hôm nay, ta tính ngày tiếp theo bằng `plusDays(1)`. Điều này thuận tiện cho lịch học, lịch công việc hoặc sinh mốc thời gian.

```java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class LichTuan {
    public static void main(String[] args) {
        LocalDate batDau = LocalDate.of(2026, 11, 16);

        List<LocalDate> bayNgay = Stream.iterate(
                batDau,
                ngay -> ngay.plusDays(1)
            )
            .limit(7)
            .collect(Collectors.toList());

        System.out.println(bayNgay);
    }
}
```

Kết quả:

```text
[2026-11-16, 2026-11-17, 2026-11-18, 2026-11-19,
 2026-11-20, 2026-11-21, 2026-11-22]
```

Từ Java 9, nếu ngày kết thúc được xác định theo dữ liệu nghiệp vụ, có thể dùng dạng ba tham số:

```java
LocalDate batDau = LocalDate.of(2026, 11, 16);
LocalDate ketThuc = LocalDate.of(2026, 11, 20);

List<LocalDate> cacNgay = Stream.iterate(
        batDau,
        ngay -> !ngay.isAfter(ketThuc),
        ngay -> ngay.plusDays(1)
    )
    .collect(Collectors.toList());

// [2026-11-16, 2026-11-17, 2026-11-18, 2026-11-19, 2026-11-20]
```

Điều kiện `!ngay.isAfter(ketThuc)` cho phép giữ **cả ngày kết thúc**. Nếu dùng `ngay.isBefore(ketThuc)`, ngày kết thúc sẽ bị loại.

### Sinh ba ngày làm việc đầu tiên từ một ngày thứ Sáu

```java
import java.time.DayOfWeek;

LocalDate batDau = LocalDate.of(2026, 11, 20); // Thứ Sáu

List<LocalDate> ngayLamViec = Stream.iterate(
        batDau, ngay -> ngay.plusDays(1))
    .filter(ngay -> ngay.getDayOfWeek() != DayOfWeek.SATURDAY)
    .filter(ngay -> ngay.getDayOfWeek() != DayOfWeek.SUNDAY)
    .limit(3)
    .collect(Collectors.toList());

System.out.println(ngayLamViec);
// [2026-11-20, 2026-11-23, 2026-11-24]
```

Ở đây, `filter` bỏ thứ Bảy và Chủ nhật; `limit(3)` chỉ tính **ba ngày đã vượt qua bộ lọc**. Ví dụ đơn giản chưa xét ngày nghỉ lễ của từng quốc gia hay doanh nghiệp.

## 7. Trạng thái phức hợp: dãy Fibonacci bằng đối tượng bất biến

Một số dãy không thể tính phần tử tiếp theo chỉ từ **một giá trị hiện tại**. Fibonacci cần nhớ **hai giá trị gần nhất**:

```text
F(0) = 0
F(1) = 1
F(n + 2) = F(n + 1) + F(n)
```

Cách giải phù hợp là xem trạng thái tại mỗi bước là một cặp `(a, b)`:

```text
(a, b) = (0, 1)
    ↓ (a, b) → (b, a+b)
(1, 1)
    ↓
(1, 2)
    ↓
(2, 3)
    ↓
(3, 5)
...
```

Để tránh tràn `int` hoặc `long` khi tạo nhiều số Fibonacci, ví dụ dùng `BigInteger`. Lớp trạng thái chỉ có trường `final`, và phép chuyển tạo một đối tượng mới:

```java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FibonacciBangIterate {
    private static final class TrangThai {
        final BigInteger a;
        final BigInteger b;

        TrangThai(BigInteger a, BigInteger b) {
            this.a = a;
            this.b = b;
        }

        TrangThai tiepTheo() {
            return new TrangThai(b, a.add(b));
        }
    }

    public static void main(String[] args) {
        TrangThai batDau = new TrangThai(
            BigInteger.ZERO, BigInteger.ONE);

        List<BigInteger> fibonacci = Stream
            .iterate(batDau, TrangThai::tiepTheo)
            .map(trangThai -> trangThai.a)
            .limit(10)
            .collect(Collectors.toList());

        System.out.println(fibonacci);
        // [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
    }
}
```

Ở đây:

- Kiểu nguồn là `Stream<TrangThai>`.
- Hàm `tiepTheo()` nhận trạng thái hiện tại và tạo **trạng thái mới** cùng kiểu.
- `map(trangThai -> trangThai.a)` chỉ chọn giá trị cần công bố, tạo `Stream<BigInteger>`.
- `limit(10)` buộc quá trình sinh kết thúc sau mười giá trị đầu.

Cách dùng **trạng thái bất biến** giúp phép chuyển trạng thái minh bạch, dễ thử nghiệm và tránh phụ thuộc vào biến ngoài pipeline. Không nên dùng mảng được sửa tại chỗ hoặc biến đếm bên ngoài lambda để "nhớ" hai số trước khi có thể biểu diễn trạng thái bằng giá trị mới.

Nếu dùng Java 16+ để xây dựng ứng dụng, có thể thay lớp chứa hai trường bằng `record`; tuy nhiên, cách viết ở trên vẫn chạy với Java 8.

## 8. Chọn `Stream<Integer>` hay `IntStream`?

Với dãy số nguyên, Java có biến thể primitive `IntStream.iterate`. Nó tránh boxing từ `int` sang `Integer` ở từng phần tử, hữu ích cho các phép tính số học.

Ví dụ Java 8:

```java
import java.util.stream.IntStream;

int tong = IntStream.iterate(2, n -> n + 2)
    .limit(5)
    .sum();

System.out.println(tong); // 2 + 4 + 6 + 8 + 10 = 30
```

Trong Java 9+, `IntStream` cũng có dạng ba tham số:

```java
int[] day = IntStream.iterate(
        1,
        n -> n <= 16,
        n -> n * 2)
    .toArray();

// [1, 2, 4, 8, 16]
```

So sánh nhanh:

| Kiểu stream | Dạng giá trị | Đặc điểm |
| --- | --- | --- |
| `Stream<Integer>` | Đối tượng `Integer` | Phù hợp khi cần generic, `collect(Collectors.toList())` hoặc xử lý cùng các kiểu đối tượng. |
| `IntStream` | Nguyên thủy `int` | Có `sum()`, `average()`, `max()` và `toArray()`. |
| `LongStream` | Nguyên thủy `long` | Hữu ích khi miền giá trị `int` không đủ nhưng vẫn phải xét nguy cơ tràn số. |
| `DoubleStream` | Nguyên thủy `double` | Dùng cho dữ liệu số thực; cần chú ý sai số dấu phẩy động. |

Nếu cần đổi `IntStream` sang `Stream<Integer>`, dùng `boxed()`. Nếu chỉ cần dãy số nguyên liên tiếp từ A đến B, `IntStream.range(A, B)` hoặc `rangeClosed(A, B)` thường trực tiếp hơn so với viết hàm `n -> n + 1`.

## 9. Những bẫy thực tế khi tạo dãy

### 9.1. Quên điểm dừng

Đoạn sau **có thể chạy mãi và tăng sử dụng bộ nhớ** vì cố thu toàn bộ dãy không có điểm cuối:

```java
// KHÔNG CHẠY: không có limit hoặc điều kiện kết thúc.
List<Integer> voHan = Stream.iterate(0, n -> n + 1)
    .collect(Collectors.toList());
```

Giới hạn dữ liệu trước khi gom vào bộ nhớ:

```java
List<Integer> motTramSo = Stream.iterate(0, n -> n + 1)
    .limit(100)
    .collect(Collectors.toList());
```

Trong ứng dụng thực tế, chọn giới hạn hợp lý theo yêu cầu và tài nguyên; không tạo danh sách cực lớn chỉ vì có thể sinh từng phần tử lazily.

### 9.2. Bộ lọc không bao giờ cho đủ kết quả

`limit(k)` đếm các phần tử **đi qua những bước phía trước**, không đếm số trạng thái đã được nguồn sinh. Ví dụ sau không thể nhận được phần tử nào:

```java
// KHÔNG CHẠY: filter luôn false, limit(1) không đạt đủ phần tử.
Stream.iterate(0, n -> n + 1)
    .filter(n -> false)
    .limit(1)
    .count();
```

Tương tự, `distinct().limit(3)` không kết thúc nếu nguồn chỉ có hai giá trị khác nhau lặp vô hạn. Khi không bảo đảm có đủ kết quả phù hợp, nên **giới hạn nguồn trước bước lọc** hoặc thiết kế nguồn có điều kiện dừng thực sự.

### 9.3. Tràn số nguyên

Kiểu `int` và `long` có giới hạn. Ví dụ `Stream.iterate(1, n -> n * 2)` có thể tràn `int` nếu lấy đủ nhiều phần tử; Java không tự đổi sang `BigInteger`.

Các lựa chọn:

- Giảm số phần tử bằng `limit` khi biết miền giá trị an toàn.
- Chọn `long` nếu vừa đủ cho miền giá trị.
- Dùng `BigInteger` cho dãy số lớn, ví dụ `Stream.iterate(BigInteger.ONE, n -> n.multiply(BigInteger.TWO))` khi chạy Java 9+ (`BigInteger.TWO` xuất hiện từ Java 9); với Java 8 có thể dùng `BigInteger.valueOf(2)`.

Giới hạn số phần tử và giới hạn **giá trị số** là hai vấn đề khác nhau. Với bài toán cần phát hiện tràn, cân nhắc `Math.addExact` hoặc `Math.multiplyExact` để gây ngoại lệ khi phép tính vượt giới hạn kiểu nguyên thủy.

### 9.4. Tác dụng phụ trong hàm `next`

Hàm chuyển trạng thái nên dựa trên đầu vào và không phụ thuộc biến bên ngoài:

```java
// NÊN: cùng một n luôn cho cùng n + 1.
Stream<Integer> nen = Stream.iterate(0, n -> n + 1);
```

Tránh dùng biến đếm hay danh sách dùng chung để tính phần tử tiếp theo. Phần lớn các phép toán trung gian có yêu cầu về hành vi **non-interfering** và **stateless**; việc thay đổi dữ liệu nguồn hoặc trạng thái ngoài trong các lambda có thể gây lỗi logic, đặc biệt khi chuyển sang parallel stream.

Cũng cần nhớ rằng một `Stream` **chỉ được tiêu thụ một lần**. Sau `collect` hoặc `count`, hãy tạo stream mới nếu muốn tính lại dãy.

### 9.5. Song song không mặc nhiên nhanh hơn

`Stream.iterate` tạo nguồn có thứ tự, mỗi trạng thái dựa trên trạng thái trước. Đây thường là bài toán **có phụ thuộc tuần tự**. Gọi `parallel()` không xóa được sự phụ thuộc đó; việc chia việc, phối hợp và giữ thứ tự có thể khiến nó chậm hơn.

Với phép xử lý trên dãy ngắn hoặc quy tắc chuyển trạng thái rẻ, giữ pipeline tuần tự là lựa chọn dễ hiểu. Chỉ cân nhắc xử lý song song khi đo được lợi ích thực tế và các hàm trong pipeline an toàn với xử lý đồng thời.

## 10. So sánh `iterate` với những cách tạo stream khác

| Phương thức | Ý tưởng | Khi nào nên dùng |
| --- | --- | --- |
| `Stream.iterate(seed, next)` | Mỗi trạng thái tạo ra trạng thái kế tiếp; mặc định không có điểm dừng | Dãy truy hồi, lấy N giá trị đầu bằng `limit` |
| `Stream.iterate(seed, hasNext, next)` (Java 9+) | Dãy truy hồi có điều kiện kiểm tra trạng thái | Sinh đến ngưỡng hoặc ngày kết thúc |
| `Stream.generate(supplier)` | Mỗi phần tử lấy từ một `Supplier`; không cần nhận trạng thái trước đó | Sinh dữ liệu độc lập qua nhà cung cấp |
| `IntStream.range(start, end)` | Các số nguyên liên tiếp, loại trừ `end` | Lặp trên miền chỉ số |
| `IntStream.rangeClosed(start, end)` | Các số nguyên liên tiếp, gồm cả `end` | Lấy đoạn số nguyên đóng |
| `collection.stream()` | Duyệt phần tử đã có trong tập hợp | Xử lý dữ liệu đã được lưu |

Ví dụ:

```java
import java.util.stream.IntStream;

// Các số nguyên liên tiếp 0, 1, 2, 3, 4.
int[] chiSo = IntStream.range(0, 5).toArray();

// Các giá trị truy hồi 1, 3, 9, 27, 81.
List<Integer> luyThuaBa = Stream.iterate(1, n -> n * 3)
    .limit(5)
    .collect(Collectors.toList());
```

Nếu phép sinh phụ thuộc vào **trạng thái trước đó**, `iterate` diễn đạt ý định rõ ràng. Nếu chỉ cần các chỉ số liên tiếp, API `range` dễ đọc hơn.

## 11. Bài tập tự thực hành

### Bài 1 — Dãy cấp số cộng

Dùng `Stream.iterate` hai tham số và `limit` để sinh **sáu** số bắt đầu từ 5, mỗi lần cộng 3. Dự đoán kết quả trước khi chạy.

### Bài 2 — Dãy hữu hạn theo điều kiện

Dùng overload ba tham số (Java 9+) để sinh các số bắt đầu từ 2, mỗi lần nhân 3, **chỉ giữ các số không vượt quá 200**. Khi nào điều kiện được kiểm tra? Có phát phần tử đầu tiên nếu `seed > 200` không?

### Bài 3 — Đổi thứ tự xử lý

Cho hai pipeline:

```java
List<Integer> a = Stream.iterate(1, n -> n + 1)
    .filter(n -> n % 3 == 0)
    .limit(4)
    .collect(Collectors.toList());

List<Integer> b = Stream.iterate(1, n -> n + 1)
    .limit(4)
    .filter(n -> n % 3 == 0)
    .collect(Collectors.toList());
```

Giải thích vì sao `a` và `b` khác nhau.

### Bài 4 — Chọn kiểu trạng thái

Muốn sinh dãy Fibonacci với 100 phần tử đầu mà không bị tràn số, bạn sẽ chọn `int`, `long` hay `BigInteger`? Vì sao cần giữ cặp giá trị gần nhất làm trạng thái thay vì chỉ dùng một số Fibonacci?

### Đáp án tham khảo

**Bài 1:**

```java
List<Integer> ketQua = Stream.iterate(5, n -> n + 3)
    .limit(6)
    .collect(Collectors.toList());

// [5, 8, 11, 14, 17, 20]
```

**Bài 2:**

```java
List<Integer> ketQua = Stream.iterate(
        2,
        n -> n <= 200,
        n -> n * 3
    )
    .collect(Collectors.toList());

// [2, 6, 18, 54, 162]
```

`hasNext` kiểm tra **trạng thái hiện tại**, gồm cả `seed`, trước khi phát phần tử đó. Sau 162, phép chuyển tạo 486; kiểm tra 486 thất bại nên không phát 486. Nếu `seed > 200`, kết quả rỗng.

**Bài 3:** `a = [3, 6, 9, 12]` vì lọc trước rồi mới giới hạn bốn phần tử thỏa điều kiện. `b = [3]` vì chỉ xét bốn số 1, 2, 3, 4 rồi mới lọc bội số của 3.

**Bài 4:** `BigInteger` phù hợp nếu cần chính xác đến phần tử thứ 100, vì cả `int` và `long` đều tràn trước đó. Hàm chuyển trạng thái cần cả hai giá trị của cặp `(a, b)` để tạo `(b, a + b)`. Có thể dùng lớp trạng thái bất biến như trong ví dụ Fibonacci ở phần 7.

## 12. Ghi nhớ

`Stream.iterate` tạo nguồn dữ liệu bằng một **hàm chuyển trạng thái**:

```java
// Java 8+: nguồn có thể sinh vô hạn; giới hạn số phần tử khi cần.
Stream.iterate(seed, current -> next(current))
    .limit(soPhanTu);

// Java 9+: kiểm tra current trước khi đưa nó vào stream.
Stream.iterate(seed,
    current -> conDuocPhep(current),
    current -> next(current));
```

Hãy xác định rõ **trạng thái ban đầu**, **quy tắc tạo trạng thái tiếp theo**, **điều kiện dừng** và **kiểu dữ liệu phù hợp**. Kết hợp `iterate` với `filter`, `map`, `reduce` và `collect` chỉ khi đã hiểu số lượng phần tử được yêu cầu và tác động của thứ tự các phép toán. Đó là nền tảng để sinh và xử lý dãy dài an toàn, dễ kiểm tra và dễ mở rộng.
