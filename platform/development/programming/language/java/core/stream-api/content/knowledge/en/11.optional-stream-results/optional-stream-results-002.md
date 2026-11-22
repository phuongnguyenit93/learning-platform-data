# Sử dụng `OptionalInt`, `OptionalLong` và `OptionalDouble`

## 1. Vì sao kết quả của Stream cần Optional?

Trong **Java Stream API**, các pipeline khai báo thường kết hợp nguồn dữ liệu, những thao tác trung gian lazy như `filter` và `map`, rồi kết thúc bằng `min`, `max`, `average`, `findFirst` hoặc `reduce`. Không phải lúc nào pipeline cũng tìm được phần tử để trả về. Ví dụ: nguồn rỗng, hoặc toàn bộ phần tử bị `filter` loại bỏ.

Java dùng ba kiểu **Optional nguyên thủy** để diễn đạt trường hợp một phép toán *có thể có hoặc không có kết quả*:

- `OptionalInt`: có thể chứa một giá trị `int`.
- `OptionalLong`: có thể chứa một giá trị `long`.
- `OptionalDouble`: có thể chứa một giá trị `double`.

Chúng không phải stream và cũng không phải `null`. Mỗi đối tượng biểu diễn **trạng thái có giá trị hoặc rỗng**. Điều này giúp mã gọi chủ động quyết định cách xử lý trường hợp thiếu dữ liệu, thay vì giả định rằng luôn có kết quả.

Sau bài này, bạn có thể:

1. Nhận biết phương thức nào của `IntStream`, `LongStream` và `DoubleStream` trả về Optional nguyên thủy.
2. Kiểm tra và lấy giá trị bằng `isPresent`, `ifPresent`, `orElse`, `orElseGet`, `orElseThrow`.
3. Phân biệt **không có kết quả** với kết quả hợp lệ bằng `0`, `0L` hoặc `0.0`.
4. Xử lý các tình huống thực tế: điểm trung bình, giao dịch lớn nhất, giá trị đo và kết quả tìm kiếm.
5. Lựa chọn Optional nguyên thủy, `Optional<T>`, giá trị mặc định và ngoại lệ phù hợp với hợp đồng nghiệp vụ.

Bài thuộc chương **Optional trong kết quả Stream** của module `JAVA_STREAM_API`. Đây là nền tảng để đọc kết quả các pipeline số học, `reduce` và các phép tổng hợp trong các nội dung nâng cao như grouping, collector tùy chỉnh hoặc xử lý song song.

## 2. Bản đồ kiểu trả về của các phép toán kết thúc

Các primitive stream được giới thiệu từ Java 8:

| Loại stream | Các phép toán trả Optional nguyên thủy | Các phép toán trả giá trị trực tiếp |
| --- | --- | --- |
| `IntStream` | `min()`, `max()`, `findFirst()`, `findAny()`, `reduce(IntBinaryOperator)` → `OptionalInt`; `average()` → `OptionalDouble` | `sum()` → `int`, `count()` → `long` |
| `LongStream` | `min()`, `max()`, `findFirst()`, `findAny()`, `reduce(LongBinaryOperator)` → `OptionalLong`; `average()` → `OptionalDouble` | `sum()` → `long`, `count()` → `long` |
| `DoubleStream` | `min()`, `max()`, `findFirst()`, `findAny()`, `reduce(DoubleBinaryOperator)`, `average()` → `OptionalDouble` | `sum()` → `double`, `count()` → `long` |

Một lưu ý quan trọng: **`average()` của cả ba loại primitive stream đều trả về `OptionalDouble`**. Trung bình của các số nguyên có thể là một số thập phân; vì vậy không có `OptionalInt` hoặc `OptionalLong` cho phép tính này.

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

OptionalInt minDiem = IntStream.of(7, 8, 9).min();
OptionalLong giaoDichLonNhat = LongStream.of(100L, 300L).max();
OptionalDouble trungBinh = IntStream.of(7, 8, 9).average();
OptionalDouble doLonNhat = DoubleStream.of(1.5, 2.5).max();
```

Đọc từ kiểu nguồn sang kết quả:

```text
IntStream  ── min() / max() / findFirst() ──▶ OptionalInt
LongStream ── min() / max() / findFirst() ──▶ OptionalLong
DoubleStream ── min() / max() / average() ──▶ OptionalDouble

IntStream  ── average() ──────────────────▶ OptionalDouble
LongStream ── average() ──────────────────▶ OptionalDouble
```

Khi thấy lỗi biên dịch do gán sai kiểu, hãy kiểm tra **kiểu của stream ở ngay trước terminal operation**, không chỉ kiểu dữ liệu ban đầu. Ví dụ `mapToLong` làm thay đổi kiểu stream, nên `findFirst()` sau đó trả về `OptionalLong`.

## 3. Ví dụ hoàn chỉnh: phân tích điểm thi

Chương trình dưới đây chạy trên **Java 8 trở lên**:

```java
import java.util.Arrays;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;

public class ThongKeDiem {
    public static void main(String[] args) {
        int[] diem = {7, 9, 6, 8};

        OptionalInt diemNhoNhat = Arrays.stream(diem).min();
        OptionalInt diemLonNhat = Arrays.stream(diem).max();
        OptionalDouble diemTrungBinh = Arrays.stream(diem).average();

        System.out.println("Min: " + diemNhoNhat.orElse(-1));
        System.out.println("Max: " + diemLonNhat.orElse(-1));
        System.out.println("Trung bình: " + diemTrungBinh.orElse(0.0));

        int[] khongCoDiem = {};
        OptionalDouble trungBinhRong = Arrays.stream(khongCoDiem).average();

        System.out.println("Có điểm? " + trungBinhRong.isPresent());
    }
}
```

Kết quả:

```text
Min: 6
Max: 9
Trung bình: 7.5
Có điểm? false
```

Giải thích:

- `min()`, `max()` và `average()` là các **terminal operations**, làm tiêu thụ stream.
- `Arrays.stream(diem)` tạo `IntStream`. Chương trình tạo **ba stream mới** từ cùng một mảng để thực hiện ba phép kết thúc độc lập.
- `min()` và `max()` trả về `OptionalInt`; `average()` trả về `OptionalDouble`.
- Với mảng rỗng, `average()` trả về `OptionalDouble.empty()`. Không có giá trị trung bình hợp lệ để lấy trực tiếp.

Trong ví dụ, `-1` và `0.0` là các giá trị mặc định để minh họa API. Khi áp dụng nghiệp vụ, **không được tự động coi điểm trung bình của tập dữ liệu rỗng là 0.0**, trừ khi yêu cầu thực sự định nghĩa như vậy.

## 4. Trạng thái rỗng khác giá trị bằng 0

Một Optional nguyên thủy có hai trạng thái:

```text
OptionalInt
  ├─ Có giá trị: OptionalInt.of(0) / OptionalInt.of(42) / ...
  └─ Rỗng:      OptionalInt.empty()
```

`OptionalInt.of(0)` **có giá trị** và giá trị đó bằng 0. `OptionalInt.empty()` **không có giá trị nào**. Tương tự với `OptionalLong.of(0L)` và `OptionalDouble.of(0.0)`.

```java
import java.util.OptionalInt;

OptionalInt coSoKhong = OptionalInt.of(0);
OptionalInt khongCoSo = OptionalInt.empty();

System.out.println(coSoKhong.isPresent()); // true
System.out.println(khongCoSo.isPresent()); // false

System.out.println(coSoKhong.orElse(-1)); // 0
System.out.println(khongCoSo.orElse(-1)); // -1
```

Khi stream rỗng:

```java
import java.util.stream.IntStream;

OptionalInt ketQua = IntStream.empty().max();
System.out.println(ketQua.isPresent()); // false
```

Khi một phép kết thúc có **giá trị mặc định/đơn vị (identity)**, kết quả có thể là giá trị trực tiếp dù nguồn rỗng:

```java
int tongRong = IntStream.empty().sum();
long soLuongRong = IntStream.empty().count();

System.out.println(tongRong);    // 0
System.out.println(soLuongRong); // 0
```

Điều này không làm `max()` hay `average()` trở nên có nghĩa trên tập rỗng. Không có "phần tử lớn nhất" hoặc "trung bình cộng" của tập rỗng theo hợp đồng của các phương thức đó.

**Một ví dụ nghiệp vụ:** Số lượng giao dịch bằng 0 có thể là dữ liệu hợp lệ; còn "chưa có dữ liệu giao dịch" có ý nghĩa khác. Nếu hai trạng thái cần được phân biệt, trả về `OptionalInt` hoặc `OptionalLong` sẽ rõ ràng hơn việc dùng một số giả định.

## 5. Kiểm tra an toàn: `isPresent`, `ifPresent` và `getAs...`

Các phương thức lấy giá trị tương ứng:

| Kiểu | Kiểm tra | Lấy giá trị | Nếu rỗng |
| --- | --- | --- | --- |
| `OptionalInt` | `isPresent()` | `getAsInt()` | Ném `NoSuchElementException` |
| `OptionalLong` | `isPresent()` | `getAsLong()` | Ném `NoSuchElementException` |
| `OptionalDouble` | `isPresent()` | `getAsDouble()` | Ném `NoSuchElementException` |

Ví dụ hợp lệ:

```java
OptionalInt diemMax = IntStream.of(5, 8, 9).max();

if (diemMax.isPresent()) {
    System.out.println("Điểm cao nhất: " + diemMax.getAsInt());
} else {
    System.out.println("Chưa có điểm để tính");
}
```

Nếu chỉ cần thực hiện hành động **khi có kết quả**, `ifPresent` ngắn gọn hơn:

```java
OptionalLong max = java.util.stream.LongStream
    .of(1_000L, 2_000L, 1_500L)
    .max();

max.ifPresent(value -> System.out.println("Giao dịch lớn nhất: " + value));
```

`ifPresent` nhận consumer của kiểu nguyên thủy tương ứng: `IntConsumer`, `LongConsumer` hoặc `DoubleConsumer`. Khi Optional rỗng, hành động không chạy.

**Không gọi `getAsInt()`, `getAsLong()` hoặc `getAsDouble()` mà chưa biết chắc Optional có giá trị**:

```java
// BIÊN DỊCH ĐƯỢC NHƯNG SẼ NÉM NoSuchElementException.
// int x = java.util.OptionalInt.empty().getAsInt();
```

Trong bài toán mà thiếu kết quả là một khả năng bình thường, việc gọi `getAs...` trực tiếp thường làm mã dễ hỏng. Hãy chọn `orElse`, `orElseGet`, `orElseThrow` hoặc xử lý nhánh rỗng tường minh.

## 6. Giá trị dự phòng: `orElse` và `orElseGet`

### 6.1. `orElse`: có giá trị mặc định cố định

`orElse` trả về giá trị hiện có nếu Optional không rỗng; nếu rỗng, nó trả về giá trị dự phòng:

```java
int diemMacDinh = IntStream.empty()
    .max()
    .orElse(-1);

long giaoDichMacDinh = java.util.stream.LongStream.empty()
    .max()
    .orElse(0L);

double nhietDoMacDinh = java.util.stream.DoubleStream.empty()
    .average()
    .orElse(Double.NaN);

System.out.println(diemMacDinh);       // -1
System.out.println(giaoDichMacDinh);   // 0
System.out.println(Double.isNaN(nhietDoMacDinh)); // true
```

Giá trị dự phòng phải khớp kiểu nguyên thủy (`int`, `long` hoặc `double`) và **phải mang ý nghĩa nghiệp vụ**. `-1` có thể là giá trị đặc biệt hợp lệ trong một hệ thống nhưng là giá trị bị cấm trong hệ thống khác. `Double.NaN` cũng là một số `double` đặc biệt, không tương đương với trạng thái Optional rỗng.

Nếu cần phân biệt "không có dữ liệu" với một số thực, thường nên giữ `OptionalDouble` cho đến khi nơi sử dụng quyết định chính sách.

### 6.2. `orElseGet`: tính giá trị dự phòng khi cần

`orElseGet` nhận một supplier, chỉ gọi khi Optional rỗng. Đối với primitive Optional, supplier lần lượt là `IntSupplier`, `LongSupplier`, `DoubleSupplier`.

```java
OptionalInt ketQua = IntStream.of(4, 7, 2).max();

int giaTri = ketQua.orElseGet(() -> {
    System.out.println("Đang tính dự phòng");
    return -1;
});

System.out.println(giaTri); // 7
```

Vì `ketQua` có giá trị, chuỗi `Đang tính dự phòng` không được in. Ngược lại, `orElse(-1)` phù hợp khi chỉ cần một hằng số đơn giản.

Ví dụ dự phòng có ý nghĩa như tính cấu hình:

```java
int gioiHan = IntStream.empty()
    .max()
    .orElseGet(() -> {
        // Tính cấu hình mặc định khi không có dữ liệu.
        return 100;
    });
```

Không nên dùng `orElseGet` chỉ để gây tác dụng phụ; mục đích chính của nó là **cung cấp giá trị**.

## 7. Bắt buộc phải có kết quả: `orElseThrow`

Trong một số hệ thống, không tìm được dữ liệu là lỗi nghiệp vụ: ví dụ đã yêu cầu điểm cao nhất của một lớp được xác nhận là có bài thi, nhưng hệ thống không chứa điểm nào. Khi đó, có thể ném ngoại lệ có thông báo rõ:

```java
import java.util.stream.IntStream;

int diemCaoNhat = IntStream.of(6, 9, 8)
    .max()
    .orElseThrow(() -> new IllegalStateException(
        "Không có điểm thi để tính điểm cao nhất"
    ));

System.out.println(diemCaoNhat); // 9
```

Nếu stream rỗng, supplier tạo `IllegalStateException`. Đây là overload **`orElseThrow(Supplier<? extends X>)`** có trong Java 8.

```java
// Ví dụ cố ý phát sinh ngoại lệ lúc chạy:
// int max = IntStream.empty()
//     .max()
//     .orElseThrow(() -> new IllegalStateException("Thiếu điểm"));
```

Không cần viết `isPresent` rồi tự ném ngoại lệ khi `orElseThrow` diễn đạt cùng hợp đồng rõ hơn.

**Lựa chọn nhanh:**

| Tình huống | Lựa chọn |
| --- | --- |
| Không có dữ liệu là bình thường và bên gọi cần phân biệt | Giữ `OptionalInt` / `OptionalLong` / `OptionalDouble` |
| Không có dữ liệu thì dùng một hằng số đã thống nhất | `orElse(defaultValue)` |
| Cần tính giá trị dự phòng khi thiếu dữ liệu | `orElseGet(supplier)` |
| Thiếu dữ liệu vi phạm hợp đồng nghiệp vụ | `orElseThrow(exceptionSupplier)` |
| Chỉ chạy hành động nếu có kết quả | `ifPresent(consumer)` |

## 8. Ví dụ riêng cho `OptionalLong` và `OptionalDouble`

### 8.1. `OptionalLong`: tìm giao dịch lớn nhất

Giá trị giao dịch có thể vượt giới hạn `int`, do đó dùng `LongStream`:

```java
import java.util.OptionalLong;
import java.util.stream.LongStream;

public class GiaoDichLonNhat {
    public static void main(String[] args) {
        long[] giaoDich = {
            3_000_000_000L,
            5_000_000_000L,
            2_000_000_000L
        };

        OptionalLong lonNhat = LongStream.of(giaoDich).max();

        lonNhat.ifPresent(value ->
            System.out.println("Lớn nhất: " + value)
        );

        long ketQua = lonNhat.orElseThrow(
            () -> new IllegalStateException("Chưa có giao dịch")
        );
        System.out.println(ketQua); // 5000000000
    }
}
```

Nếu thực tế `giaoDich` rỗng, phép `max()` trả về `OptionalLong.empty()`. Không tự hiểu điều này thành số tiền `0L`, bởi một giao dịch có giá trị 0 vẫn có thể là một bản ghi thật.

### 8.2. `OptionalDouble`: trung bình cảm biến

`DoubleStream.average()` trả về `OptionalDouble`. Kết quả có thể không tồn tại nếu không có mẫu đo:

```java
import java.util.OptionalDouble;
import java.util.stream.DoubleStream;

public class TrungBinhCamBien {
    public static void main(String[] args) {
        double[] nhietDo = {24.5, 25.0, 25.5};

        OptionalDouble trungBinh = DoubleStream.of(nhietDo)
            .average();

        if (trungBinh.isPresent()) {
            System.out.println(trungBinh.getAsDouble()); // 25.0
        } else {
            System.out.println("Chưa có mẫu đo");
        }
    }
}
```

Nếu nguồn có dữ liệu `Double.NaN` hoặc giá trị vô cực, kết quả số học có thể là `NaN` hoặc vô cực **dù Optional vẫn có giá trị**. Trạng thái có/không có dữ liệu và tính hợp lệ của một giá trị số thực là **hai kiểm tra khác nhau**.

```java
OptionalDouble giaTri = DoubleStream.of(Double.NaN).average();

System.out.println(giaTri.isPresent());                 // true
System.out.println(Double.isNaN(giaTri.getAsDouble())); // true
```

Nếu hệ thống chỉ chấp nhận số hữu hạn, hãy kiểm tra `Double.isFinite(value)` (Java 8+) hoặc chính sách xác thực dữ liệu phù hợp, thay vì cho rằng `isPresent()` đồng nghĩa với giá trị đo hợp lệ.

## 9. `findFirst`, `findAny` và các kết quả tìm kiếm

Khi tìm kiếm trong primitive stream, kiểu kết quả phụ thuộc vào stream **ngay trước phép kết thúc**:

```java
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

OptionalInt dauTien = IntStream.of(3, 5, 7)
    .filter(n -> n > 4)
    .findFirst();

OptionalLong batKy = LongStream.of(10L, 20L, 30L)
    .filter(n -> n >= 20L)
    .findAny();

System.out.println(dauTien.orElse(-1)); // 5
System.out.println(batKy.isPresent());  // true
```

`findFirst()` tôn trọng thứ tự gặp phần tử của một stream có thứ tự; trong ví dụ, kết quả là 5. `findAny()` cho phép trả về **một phần tử bất kỳ phù hợp**, đặc biệt hữu ích khi triển khai có thể tận dụng xử lý song song. Vì thế **không nên giả định** `batKy` luôn chứa 20L, dù trên một pipeline tuần tự đơn giản kết quả thường là phần tử gặp đầu tiên.

Với stream rỗng hoặc lọc không còn phần tử:

```java
OptionalInt khongTimThay = IntStream.of(1, 2, 3)
    .filter(n -> n > 10)
    .findFirst();

System.out.println(khongTimThay.isPresent()); // false
```

`findFirst` và `findAny` là terminal operations có thể **short-circuit**, nghĩa là có thể ngừng xử lý khi đã xác định kết quả. Nhưng điều đó không bảo đảm chúng sẽ đánh giá mọi lambda trong pipeline hay theo một thứ tự nhất định ở chế độ song song. Tránh đặt tác dụng phụ bắt buộc thực thi trong `filter` hoặc `map`.

## 10. `reduce` có identity và không có identity

`reduce` minh họa rõ khác biệt giữa "luôn có một giá trị tổng hợp" và "có thể không có kết quả".

### 10.1. Không có identity: trả Optional

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt tong = IntStream.of(2, 4, 6)
    .reduce((a, b) -> a + b);

OptionalInt tongRong = IntStream.empty()
    .reduce((a, b) -> a + b);

System.out.println(tong.orElse(-1));       // 12
System.out.println(tongRong.isPresent());  // false
```

Ở overload này, không có giá trị nào để bắt đầu giảm nếu stream rỗng, nên kết quả là `OptionalInt.empty()`.

### 10.2. Có identity: trả giá trị nguyên thủy

```java
int tong = IntStream.of(2, 4, 6)
    .reduce(0, (a, b) -> a + b);

int tongRong = IntStream.empty()
    .reduce(0, (a, b) -> a + b);

System.out.println(tong);     // 12
System.out.println(tongRong); // 0
```

`0` là phần tử đơn vị của phép cộng: `0 + x = x`. Vì đã có identity, overload này trả trực tiếp `int` cả khi nguồn rỗng.

| Phép toán | Stream có phần tử | Stream rỗng |
| --- | --- | --- |
| `reduce((a, b) -> a + b)` | `OptionalInt.of(tổng)` | `OptionalInt.empty()` |
| `reduce(0, (a, b) -> a + b)` | `int` bằng tổng | `int` bằng 0 |
| `sum()` | `int` bằng tổng | `int` bằng 0 |

**Không tùy tiện đặt identity.** Nó phải thực sự là phần tử đơn vị của phép toán. Ví dụ `reduce(1, (a, b) -> a * b)` hợp lý cho phép nhân; dùng `0` làm identity cho phép nhân sẽ khiến kết quả sai.

Để dùng `reduce` an toàn trên stream song song, hàm kết hợp cũng cần tuân thủ các yêu cầu như tính kết hợp (associativity). Nếu cần tính tổng thông thường, các phép `sum()` sẵn có thường dễ đọc hơn.

## 11. Phân biệt Optional nguyên thủy với `Optional<T>`

Ba kiểu Optional nguyên thủy **không có quan hệ kế thừa** với `Optional<Integer>`, `Optional<Long>` hoặc `Optional<Double>`. Vì vậy, không thể gán trực tiếp:

```java
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;

// KHÔNG BIÊN DỊCH: OptionalInt khác Optional<Integer>.
// Optional<Integer> sai = IntStream.of(1, 2).max();

OptionalInt dung = IntStream.of(1, 2).max();
```

`Optional<T>` là kiểu generic bọc giá trị đối tượng; ví dụ `Stream<Integer>.max(Comparator)` có thể trả về `Optional<Integer>`, còn `IntStream.max()` trả về `OptionalInt`:

```java
import java.util.Comparator;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

Optional<Integer> maxDoiTuong = Stream.of(1, 3, 2)
    .max(Comparator.naturalOrder());

OptionalInt maxNguyenThuy = IntStream.of(1, 3, 2)
    .max();
```

Sự khác biệt quan trọng:

| Đặc điểm | `OptionalInt` / `OptionalLong` / `OptionalDouble` | `Optional<T>` |
| --- | --- | --- |
| Giá trị bên trong | Primitive `int`/`long`/`double` | Giá trị tham chiếu kiểu `T` |
| Lấy giá trị | `getAsInt`/`getAsLong`/`getAsDouble` | `get()` |
| Không cần wrapper từng giá trị nguyên thủy | Có | Không |
| `map`, `filter`, `flatMap` kiểu generic | Không có các phương thức này trong API primitive Optional | Có |
| Có thể rỗng | Có | Có |

Để **biến đổi một Optional nguyên thủy** trong Java 8, thường xử lý bằng `isPresent` rồi gọi giá trị, hoặc thực hiện `map` trên stream *trước khi* có Optional.

Ví dụ, thay vì tìm số rồi mới nhân đôi:

```java
OptionalInt ketQua = IntStream.of(4, 7, 9)
    .filter(n -> n > 5)
    .map(n -> n * 2)
    .findFirst();

System.out.println(ketQua.orElse(-1)); // 14
```

Khi cần tích hợp với API đòi hỏi `Optional<Integer>`, có thể chuyển đổi tường minh:

```java
OptionalInt primitive = IntStream.of(4, 7).max();

Optional<Integer> boxed = primitive.isPresent()
    ? Optional.of(primitive.getAsInt())
    : Optional.empty();
```

Sự chuyển đổi này có boxing, nên chỉ làm khi có lý do rõ ràng.

## 12. Bổ sung API theo phiên bản Java

Các ví dụ cốt lõi ở trên dùng API từ **Java 8**. Một số phương thức tiện ích xuất hiện sau đó:

| Phương thức | Phiên bản | Công dụng |
| --- | --- | --- |
| `OptionalInt.stream()`, `OptionalLong.stream()`, `OptionalDouble.stream()` | Java 9+ | Chuyển Optional thành primitive stream có 0 hoặc 1 phần tử. |
| `ifPresentOrElse(consumer, emptyAction)` | Java 9+ | Xử lý cả nhánh có giá trị lẫn nhánh rỗng. |
| `isEmpty()` | Java 11+ | Kiểm tra Optional rỗng trực tiếp, tương đương `!isPresent()`. |

Ví dụ dùng `stream()` từ Java 9:

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt lonNhat = IntStream.of(2, 8, 4).max();

int[] mang = lonNhat.stream()
    .map(n -> n * 2)
    .toArray();

System.out.println(java.util.Arrays.toString(mang)); // [16]
```

Nếu `lonNhat` rỗng, `lonNhat.stream()` tạo `IntStream` rỗng, nên `toArray()` trả mảng rỗng. Đây là cách tiện lợi để ghép tiếp vào các pipeline khi phiên bản Java hỗ trợ.

Ví dụ Java 9+ cho hai nhánh:

```java
IntStream.empty().max().ifPresentOrElse(
    value -> System.out.println("Max: " + value),
    () -> System.out.println("Không có dữ liệu")
);

// Không có dữ liệu
```

Đừng dùng những phương thức này trong dự án giới hạn ở Java 8. Ở Java 8, có thể dùng `isPresent()` và nhánh `if/else` như phần trước.

## 13. Những lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi `getAsInt()` trên Optional rỗng | Không có giá trị; ném `NoSuchElementException` | Dùng `orElse`, `orElseThrow` hoặc kiểm tra `isPresent` |
| Tưởng `OptionalInt.empty()` bằng `OptionalInt.of(0)` | Lẫn lộn trạng thái thiếu dữ liệu và giá trị 0 hợp lệ | Dựa vào `isPresent` để biết có dữ liệu |
| Gán `IntStream.average()` cho `OptionalInt` | `average()` trả về `OptionalDouble` | Khai báo đúng `OptionalDouble` |
| Gán `IntStream.max()` cho `Optional<Integer>` | Optional nguyên thủy khác Optional generic | Sử dụng `OptionalInt` hoặc chuyển kiểu tường minh |
| Mặc định dùng `orElse(0)` cho mọi trường hợp thiếu | 0 có thể làm sai báo cáo nghiệp vụ | Giữ Optional hoặc chọn chính sách thiếu dữ liệu rõ ràng |
| Dùng `getAsDouble()` rồi chỉ kiểm tra `isPresent` | Số thực có thể là `NaN` hoặc vô cực | Kiểm tra tính hữu hạn nếu bài toán yêu cầu |
| Truyền `null` thay cho một Optional rỗng | Mất ý nghĩa của kiểu Optional và gây nguy cơ `NullPointerException` | Dùng `OptionalInt.empty()`, `OptionalLong.empty()` hoặc `OptionalDouble.empty()` |
| Dùng lại stream sau `max` / `average` / `findFirst` | Terminal operation đã tiêu thụ stream | Tạo stream mới từ nguồn |
| Cho rằng `findAny()` luôn trả phần tử đầu | `findAny` không bảo đảm phần tử cụ thể | Dùng `findFirst` khi cần theo thứ tự |
| Dùng phương thức `isEmpty()` trong Java 8 | Phương thức chỉ có từ Java 11 | Dùng `!isPresent()` trong Java 8 |

**Điểm cần nhớ khi chẩn đoán:** Optional là **kết quả của phép toán**, không phải bằng chứng rằng pipeline đã duyệt toàn bộ nguồn. Các phép tìm kiếm như `findFirst` có thể dừng sớm; đừng đặt tác dụng phụ bắt buộc bên trong lambda và giả định chúng luôn chạy.

## 14. Bài tập thực hành

### Bài 1 — Kết quả rỗng hay bằng 0?

Dự đoán trạng thái và giá trị sau:

```java
OptionalInt a = IntStream.of(0).max();
OptionalInt b = IntStream.empty().max();

System.out.println(a.isPresent());
System.out.println(b.isPresent());
System.out.println(a.orElse(-1));
System.out.println(b.orElse(-1));
```

Vì sao không thể chỉ so sánh `orElse(0)` để phân biệt hai trường hợp?

### Bài 2 — Kiểu kết quả của `average`

Cho:

```java
long[] luotXem = {3L, 4L, 5L, 6L};
```

Viết pipeline tạo một Optional chứa trung bình cộng số lượt xem. Optional có kiểu gì? Kết quả là bao nhiêu?

### Bài 3 — Xử lý kết quả không bắt buộc

Cho:

```java
int[] diem = {4, 6, 8, 10};
```

Tìm điểm đầu tiên lớn hơn 7, in ra nếu có. Nếu không có, dùng giá trị dự phòng `-1`. Thực hiện bằng API Java 8.

### Bài 4 — `reduce` có và không có identity

Dự đoán kết quả:

```java
OptionalLong a = java.util.stream.LongStream.empty()
    .reduce((x, y) -> x + y);

long b = java.util.stream.LongStream.empty()
    .reduce(0L, (x, y) -> x + y);
```

Vì sao `a` rỗng nhưng `b` bằng 0?

### Bài 5 — Trung bình cảm biến có `NaN`

```java
OptionalDouble m = java.util.stream.DoubleStream.of(
    5.0, Double.NaN
).average();
```

`m.isPresent()` là `true` hay `false`? Tại sao vẫn cần kiểm tra dữ liệu trước khi dùng giá trị này?

### Đáp án tham khảo

**Bài 1:** `a.isPresent() == true`, `b.isPresent() == false`, `a.orElse(-1) == 0`, `b.orElse(-1) == -1`. Nếu dùng `orElse(0)`, cả hai đều ra 0 dù trạng thái khác nhau.

**Bài 2:**

```java
OptionalDouble trungBinh = java.util.Arrays.stream(luotXem)
    .average();

System.out.println(trungBinh.orElse(-1.0)); // 4.5
```

`Arrays.stream(long[])` tạo `LongStream`, nhưng `average()` vẫn trả `OptionalDouble`.

**Bài 3:**

```java
OptionalInt timDuoc = java.util.Arrays.stream(diem)
    .filter(d -> d > 7)
    .findFirst();

timDuoc.ifPresent(d -> System.out.println("Điểm: " + d)); // 8

int giaTri = timDuoc.orElse(-1);
System.out.println(giaTri); // 8
```

Nếu tất cả điểm nhỏ hơn hoặc bằng 7, `findFirst()` trả Optional rỗng, `ifPresent` không in và `orElse(-1)` trả -1.

**Bài 4:** `a.isPresent() == false` vì không có phần tử để bắt đầu phép giảm không identity. `b == 0L` vì identity `0L` là phần tử đơn vị của phép cộng.

**Bài 5:** `m.isPresent() == true` vì stream không rỗng. Tuy nhiên, kết quả `m.getAsDouble()` là `NaN` do một mẫu đầu vào là `NaN`. `OptionalDouble` chỉ diễn đạt *có kết quả hay không*, không bảo đảm kết quả là số hữu hạn.

## 15. Ghi nhớ

- `OptionalInt`, `OptionalLong` và `OptionalDouble` chứa **0 hoặc 1 giá trị nguyên thủy**, và được các phép toán như `min`, `max`, `findFirst`, `findAny` hoặc `reduce` không có identity trả về.
- `average()` của `IntStream`, `LongStream` và `DoubleStream` đều trả **`OptionalDouble`**.
- Trường hợp **không có dữ liệu** khác với giá trị hợp lệ `0`, `0L` hoặc `0.0`.
- Dùng `isPresent`/`ifPresent` để kiểm tra, `orElse`/`orElseGet` khi có giá trị dự phòng, `orElseThrow` khi thiếu dữ liệu là lỗi.
- Không gọi `getAs...` trên Optional rỗng; không nhầm Optional nguyên thủy với `Optional<T>`.
- Khi làm việc với dữ liệu số thực, phải xét thêm `NaN`, vô cực và yêu cầu độ chính xác của bài toán.

Xử lý Optional đúng giúp pipeline Stream API diễn đạt rõ hợp đồng dữ liệu, giữ được ý nghĩa của trường hợp rỗng và tránh các lỗi lúc chạy trong ứng dụng thống kê, tìm kiếm và tổng hợp dữ liệu.
