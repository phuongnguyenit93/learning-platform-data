# Chuyển vòng lặp lọc, ánh xạ và tính tổng thành pipeline

> **Chương:** Bài tập nền tảng và trung cấp  
> **Module:** `JAVA_STREAM_API` — học xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; phát triển tới grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời nhận diện các giới hạn về trạng thái, tài nguyên và hiệu năng.

Trong nhiều chương trình Java, vòng lặp `for` được dùng để duyệt một danh sách, **chọn phần tử phù hợp**, **tính giá trị cần dùng** rồi **cộng dồn**. Đây là một cơ hội tốt để luyện Java Stream API: cùng một công việc có thể được mô tả bằng pipeline `filter → mapToInt/mapToLong → sum`. Mục tiêu của việc chuyển đổi không phải là bỏ mọi vòng lặp, mà là **giữ nguyên quy tắc nghiệp vụ và kết quả** trong khi làm rõ từng bước xử lý.

Bài học gồm phần giải thích, chương trình Java 17+ đầy đủ, những biến thể thường gặp và bài tập có đáp án. Người học sẽ tự đối chiếu bản `for` và bản Stream trên cùng một tập dữ liệu để phát hiện thay đổi về giá trị, thứ tự hoặc cách xử lý dữ liệu rỗng.

## 1. Bài toán mẫu và tiêu chí đúng

Một hệ thống bán hàng lưu các dòng hàng có mã sản phẩm, trạng thái đã thanh toán, số lượng và đơn giá theo **đồng Việt Nam (VND)**. Cần tính **doanh thu của những dòng đã thanh toán có số lượng từ 3 trở lên**.

| Mã sản phẩm | Đã thanh toán | Số lượng | Đơn giá (VND) | Có tính? | Thành tiền được tính |
| --- | --- | ---: | ---: | --- | ---: |
| `PEN` | Có | 3 | 12.000 | Có | 36.000 |
| `NOTE` | Không | 5 | 50.000 | Không | — |
| `RULER` | Có | 2 | 8.000 | Không | — |
| `ERASER` | Có | 4 | 7.000 | Có | 28.000 |
| `PEN` | Có | 1 | 12.000 | Không | — |

**Đầu ra mong đợi:** `64_000L` VND, vì `3 × 12_000 + 4 × 7_000 = 64_000`. Mã `PEN` có thể xuất hiện nhiều lần; bài toán tính theo **dòng**, không tự gộp các dòng trước khi áp dụng điều kiện số lượng.

Quy tắc cần giữ khi chuyển sang Stream:

1. Duyệt đúng tập đầu vào.
2. Chỉ chọn dòng **`paid == true` và `quantity >= 3`**.
3. Mỗi dòng đạt điều kiện đóng góp **`quantity × unitPriceVnd`**.
4. Cộng tất cả số tiền của những dòng đã chọn.
5. Nếu không có dòng nào đạt điều kiện, tổng là **0**.
6. Với phép cộng `long` thông thường, cả vòng lặp và `LongStream.sum()` đều có thể **tràn số**; phần sau giải thích khi cần kiểm tra overflow.

## 2. Giải bằng vòng lặp `for` trước

Đây là lời giải theo lối mệnh lệnh (*imperative*):

```java
long total = 0L;

for (SaleLine line : lines) {
    if (line.paid() && line.quantity() >= 3) {
        long amount = (long) line.quantity() * line.unitPriceVnd();
        total += amount;
    }
}

System.out.println(total); // 64000
```

`SaleLine` và `lines` sẽ được định nghĩa đầy đủ ở mục 5. Ở đây hãy chú ý cấu trúc:

- `for`: duyệt từng dòng.
- `if`: giữ những dòng thỏa điều kiện.
- `amount = ...`: ánh xạ từ dòng bán hàng sang số tiền của dòng.
- `total += amount`: cộng dồn các số tiền.

Vòng lặp này hoàn toàn hợp lệ và dễ hiểu. Đổi sang Stream có lợi khi muốn **tách rõ các thao tác dữ liệu**, thuận tiện bổ sung `filter`, thay đổi phép biến đổi hoặc kết hợp với các collector.

## 3. Chuyển từng bước sang `filter → mapToLong → sum`

Mỗi phần trong vòng lặp có một thao tác Stream tương ứng:

| Vòng lặp | Pipeline | Tác dụng |
| --- | --- | --- |
| `for (SaleLine line : lines)` | `lines.stream()` | Tạo nguồn phần tử. |
| `if (line.paid() && line.quantity() >= 3)` | `.filter(line -> ...)` | Giữ phần tử thỏa điều kiện. |
| `long amount = ...` | `.mapToLong(line -> ...)` | Chuyển dòng hàng thành số tiền kiểu `long`. |
| `total += amount` | `.sum()` | Cộng các số đã ánh xạ; kết thúc pipeline. |

```java
long total = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line -> (long) line.quantity() * line.unitPriceVnd())
        .sum();

System.out.println(total); // 64000
```

Hình dung cách xử lý:

```text
 List<SaleLine>                     Có 5 dòng
       |
       v
    stream()                        Stream<SaleLine>
       |
       v
 filter(paid && quantity >= 3)       PEN x3, ERASER x4
       |
       v
 mapToLong(quantity * price)         36000, 28000
       |
       v
      sum()                          64000 (long)
```

### Vì sao dùng `mapToLong`?

`mapToLong` chuyển `Stream<SaleLine>` thành `LongStream`. `LongStream` có terminal operation `sum()` trả trực tiếp `long`, không cần boxing thành `Long` cho mỗi số.

Nếu dùng `map`, kết quả là `Stream<Long>` (đối tượng), **không có** phương thức `sum()` trực tiếp trên `Stream<T>`:

```java
// Không biên dịch vì Stream<Long> không có sum():
// long wrong = lines.stream()
//         .map(line -> (long) line.quantity() * line.unitPriceVnd())
//         .sum();
```

Có thể viết `map(...).reduce(0L, Long::sum)`, nhưng khi phép biến đổi là số nguyên thủy, `mapToLong(...).sum()` diễn đạt mục tiêu ngắn gọn hơn.

**Cần chú ý kiểu phép nhân:** nếu cả hai toán hạng là `int`, phép nhân sẽ thực hiện dưới kiểu `int` **trước** khi chuyển sang `long`, nên có thể tràn. Ở ví dụ này `unitPriceVnd` là `long`; phép ép `(long) line.quantity()` nhấn mạnh ý định tính theo `long`.

## 4. Phân biệt lazy và terminal operation

`filter` và `mapToLong` là **intermediate operations**. Chúng thiết lập pipeline và thường **chưa duyệt nguồn ngay**. `sum()` là **terminal operation**, làm pipeline thực thi để có kết quả.

```java
import java.util.stream.LongStream;

LongStream pipeline = lines.stream()
        .filter(line -> line.paid())
        .mapToLong(line -> line.unitPriceVnd());

// Đến đây pipeline được tạo; chưa có terminal operation.
long sum = pipeline.sum(); // Bắt đầu duyệt và kết thúc Stream.
```

Vì Stream dùng một lần, gọi tiếp `pipeline.count()` sau `sum()` là không hợp lệ. Nếu cần tính chỉ số khác, tạo Stream mới từ một nguồn có thể duyệt lại như `List`, hoặc dùng một collector thống kê thích hợp.

Đừng đặt side effect bắt buộc trong `filter`, `map` hay `peek` với giả định rằng mọi phần tử luôn được gọi: một số terminal operation có thể ngắn mạch hoặc tối ưu để không gọi tất cả bước trung gian. Viết predicate và mapper **không can thiệp vào nguồn, không phụ thuộc trạng thái dùng chung** sẽ dễ kiểm thử hơn.

## 5. Chương trình Java 17+ đầy đủ, có đối chiếu kết quả

Lưu thành tệp `LoopToStreamDemo.java`. Đây là ví dụ chạy độc lập: có dữ liệu, bản vòng lặp, bản Stream, một phép tạo danh sách kết quả và kiểm thử bằng cách ném `AssertionError` khi sai.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class LoopToStreamDemo {
    record SaleLine(String sku, boolean paid, int quantity, long unitPriceVnd) {
        SaleLine {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank()) {
                throw new IllegalArgumentException("SKU không được rỗng");
            }
            if (quantity <= 0 || unitPriceVnd < 0) {
                throw new IllegalArgumentException("Số lượng/giá không hợp lệ");
            }
        }
    }

    static List<SaleLine> sample() {
        return List.of(
                new SaleLine("PEN", true, 3, 12_000L),
                new SaleLine("NOTE", false, 5, 50_000L),
                new SaleLine("RULER", true, 2, 8_000L),
                new SaleLine("ERASER", true, 4, 7_000L),
                new SaleLine("PEN", true, 1, 12_000L)
        );
    }

    // Phiên bản 1: lọc, ánh xạ và tính tổng bằng vòng for.
    static long totalWithLoop(List<SaleLine> lines) {
        long total = 0L;
        for (SaleLine line : lines) {
            if (line.paid() && line.quantity() >= 3) {
                long amount = (long) line.quantity() * line.unitPriceVnd();
                total += amount;
            }
        }
        return total;
    }

    // Phiên bản 2: cùng quy tắc trên bằng Stream.
    static long totalWithStream(List<SaleLine> lines) {
        return lines.stream()
                .filter(line -> line.paid() && line.quantity() >= 3)
                .mapToLong(line ->
                        (long) line.quantity() * line.unitPriceVnd())
                .sum();
    }

    // Ví dụ 3: cùng thao tác lọc nhưng ánh xạ sang nhãn.
    static List<String> labelsWithLoop(List<SaleLine> lines) {
        List<String> labels = new ArrayList<>();
        for (SaleLine line : lines) {
            if (line.paid() && line.quantity() >= 3) {
                labels.add(line.sku() + " x" + line.quantity());
            }
        }
        return labels;
    }

    static List<String> labelsWithStream(List<SaleLine> lines) {
        return lines.stream()
                .filter(line -> line.paid() && line.quantity() >= 3)
                .map(line -> line.sku() + " x" + line.quantity())
                .toList(); // Java 16+, danh sách trả về không sửa được.
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void selfTest() {
        List<SaleLine> data = sample();

        // Cả hai lời giải phải cho cùng kết quả chính xác.
        check(totalWithLoop(data) == 64_000L, "Tổng từ for sai");
        check(totalWithStream(data) == 64_000L, "Tổng Stream sai");
        check(totalWithLoop(data) == totalWithStream(data),
                "Vòng lặp và pipeline khác nhau");

        // Lọc rồi map thành danh sách vẫn giữ encounter order của List.
        List<String> expectedLabels = List.of("PEN x3", "ERASER x4");
        check(labelsWithLoop(data).equals(expectedLabels), "Nhãn từ for sai");
        check(labelsWithStream(data).equals(expectedLabels), "Nhãn Stream sai");

        // Nguồn rỗng hoặc không có phần tử đạt điều kiện => tổng 0.
        check(totalWithStream(List.of()) == 0L, "Nguồn rỗng");
        check(totalWithStream(List.of(
                new SaleLine("A", false, 10, 100L),
                new SaleLine("B", true, 1, 100L)
        )) == 0L, "Không có dòng thỏa điều kiện");

        // Đảo nguồn: tổng không đổi, nhưng thứ tự nhãn có thể đổi.
        List<SaleLine> reversed = new ArrayList<>(data);
        Collections.reverse(reversed);
        check(totalWithStream(reversed) == 64_000L, "Tổng sau đảo nguồn");
        check(labelsWithStream(reversed).equals(
                List.of("ERASER x4", "PEN x3")), "Thứ tự nhãn sau đảo");

        // Với dữ liệu trong miền long, tổng song song cũng phải đúng.
        long parallelTotal = data.parallelStream()
                .filter(line -> line.paid() && line.quantity() >= 3)
                .mapToLong(line ->
                        (long) line.quantity() * line.unitPriceVnd())
                .sum();
        check(parallelTotal == 64_000L, "Tổng song song");

        // Kết quả Stream.toList() không sửa được.
        boolean rejected = false;
        try {
            labelsWithStream(data).add("OTHER x1");
        } catch (UnsupportedOperationException expected) {
            rejected = true;
        }
        check(rejected, "Danh sách Stream.toList() phải không sửa được");
    }

    public static void main(String[] args) {
        List<SaleLine> data = sample();
        System.out.println("for: " + totalWithLoop(data));
        System.out.println("stream: " + totalWithStream(data));
        System.out.println("labels: " + labelsWithStream(data));

        // Chạy kiểm tra dù không bật cờ -ea của Java.
        selfTest();
        System.out.println("TEST PASS");
    }
}
```

Nếu thực hành trên JDK 17+:

```text
javac LoopToStreamDemo.java
java LoopToStreamDemo
```

Kết quả kỳ vọng:

```text
for: 64000
stream: 64000
labels: [PEN x3, ERASER x4]
TEST PASS
```

Bài này cung cấp mã và phép kiểm tra để tự chạy khi học; chương trình không cần thư viện bên ngoài. `check(...)` ném `AssertionError` nếu một điều kiện sai, nên không cần bật cờ `-ea` như khi dùng câu lệnh `assert` của Java.

## 6. Chọn `map`, `mapToInt`, `mapToLong` hay `reduce`?

Câu hỏi quan trọng khi chuyển vòng lặp là: **sau khi ánh xạ, ta cần kiểu giá trị nào và cần loại kết quả gì?**

| Nhu cầu | Gợi ý pipeline | Kết quả |
| --- | --- | --- |
| Lọc các đối tượng để giữ lại danh sách | `filter(...).toList()` | `List<T>` |
| Lọc rồi tạo chuỗi hiển thị | `filter(...).map(...).toList()` | `List<String>` |
| Lọc rồi cộng số lượng `int` | `filter(...).mapToInt(...).sum()` | `int` |
| Lọc rồi cộng giá trị `long` | `filter(...).mapToLong(...).sum()` | `long` |
| Lọc rồi cộng `BigDecimal` | `filter(...).map(...).reduce(BigDecimal.ZERO, BigDecimal::add)` | `BigDecimal` |
| Chỉ đếm các dòng phù hợp | `filter(...).count()` | `long` |

### Ví dụ nền tảng với `IntStream`

Bài toán: từ các số `1` tới `6`, chọn các số chẵn, bình phương chúng rồi tính tổng.

```java
import java.util.stream.IntStream;

int result = IntStream.rangeClosed(1, 6)
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sum();

System.out.println(result); // 4 + 16 + 36 = 56
```

`IntStream.rangeClosed(1, 6)` bao gồm cả hai đầu; sau `filter` còn `2, 4, 6`; sau `map` là `4, 16, 36`; `sum` trả `56`.

Lưu ý `IntStream.map` khác `Stream<T>.map`: đây là phép ánh xạ **từ `int` sang `int`**, không tạo `Stream<Integer>`. Với `Stream<SaleLine>`, phải gọi `mapToInt` hoặc `mapToLong` nếu muốn có primitive stream để tính tổng.

### Ví dụ với tiền thập phân

Khi đơn giá là số thập phân cần chính xác theo nghiệp vụ, có thể dùng `BigDecimal` thay vì `double`:

```java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> prices = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"),
        new BigDecimal("0.30")
);

BigDecimal total = prices.stream()
        .filter(price -> price.signum() > 0)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 0.60
```

`BigDecimal` là đối tượng, nên không có primitive stream chuyên biệt cho nó; `reduce` dùng phép cộng của `BigDecimal`. Tránh `new BigDecimal(0.1)` nếu mong muốn đúng số thập phân `0.1`.

## 7. Bài tập tăng dần: tự chuyển từng vòng lặp

Trong mỗi bài, hãy **viết bản vòng lặp trước**, ghi lại kết quả của dữ liệu mẫu rồi mới chuyển sang Stream. Tránh dự đoán kết quả chỉ từ tên phương thức.

### Bài 1 — Lọc, biến đổi, cộng số nguyên

Cho `List<Integer> numbers = List.of(3, -2, 4, 0, 5)`. Chỉ lấy các số **dương và chẵn**, nhân mỗi số với 10 rồi tính tổng.

Mẫu vòng lặp:

```java
int total = 0;
for (int n : numbers) {
    if (n > 0 && n % 2 == 0) {
        total += n * 10;
    }
}
```

**Đáp án pipeline:**

```java
int total = numbers.stream()
        .filter(n -> n > 0 && n % 2 == 0)
        .mapToInt(n -> n * 10)
        .sum();

System.out.println(total); // 40
```

Chỉ số `4` thỏa điều kiện, nên kết quả `4 × 10 = 40`. Không nhầm số `-2` là số chẵn **dương**.

### Bài 2 — Giữ danh sách thay vì tổng

Cho `List<String> names = List.of(" An ", " ", "Bình", " Chi ")`. Bỏ tên chỉ gồm khoảng trắng, loại khoảng trắng hai đầu và viết hoa theo `Locale.ROOT`. Yêu cầu **giữ thứ tự**.

```java
import java.util.Locale;

List<String> cleaned = names.stream()
        .map(String::trim)
        .filter(name -> !name.isBlank())
        .map(name -> name.toUpperCase(Locale.ROOT))
        .toList();

System.out.println(cleaned); // [AN, BÌNH, CHI]
```

Ở đây terminal operation là `toList()`, không phải `sum()`, vì mục tiêu là **một danh sách chuỗi**. `Stream.toList()` trên Java 16+ trả danh sách không sửa được; nó không cam kết một kiểu triển khai cụ thể như `ArrayList`.

### Bài 3 — Chuyển một vòng lặp cộng tồn kho

Nguồn gồm các sản phẩm `Product(String code, boolean active, int stock)`. Chỉ tính tổng tồn kho của sản phẩm đang hoạt động. Chọn kiểu trả về phù hợp:

```java
record Product(String code, boolean active, int stock) {}

List<Product> products = List.of(
        new Product("A", true, 12),
        new Product("B", false, 100),
        new Product("C", true, 7)
);

long activeStock = products.stream()
        .filter(Product::active)
        .mapToLong(Product::stock)
        .sum();

System.out.println(activeStock); // 19
```

`mapToLong(Product::stock)` cho phép xử lý tổng lớn hơn `int`; khi dữ liệu đầu vào nhỏ, `mapToInt(Product::stock)` cũng cho kết quả đúng. Nhưng cả `long` lẫn `int` đều có giới hạn; nếu tổng có thể vượt `long`, cần giải pháp số lớn hoặc phát hiện overflow.

### Bài 4 — Hai phép tính từ cùng danh sách

Cần cả **tổng tiền** và **số dòng** thỏa điều kiện. Có dùng lại một `Stream` sau `sum()` được không?

```java
long revenue = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line ->
                (long) line.quantity() * line.unitPriceVnd())
        .sum();

long matchingLines = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .count();
```

**Đáp án:** Không được tái sử dụng cùng đối tượng Stream; hai lệnh `lines.stream()` tạo hai Stream mới từ một `List` có thể duyệt lại. Nếu nguồn chỉ đọc được một lần hoặc việc duyệt rất tốn kém, có thể tạo collector tính nhiều chỉ số trong một lần duyệt. Đây là bước phát triển ở các bài collector nâng cao.

### Bài 5 — Lọc trước hay ánh xạ trước?

Cần lấy danh sách SKU của những dòng `paid && quantity >= 3`. Hai phương án sau có tương đương không?

```java
// ĐÚNG: vẫn có toàn bộ SaleLine ở bước kiểm tra.
List<String> result = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .map(SaleLine::sku)
        .toList();

// SAI: sau map(SaleLine::sku), mỗi phần tử chỉ còn String.
// Không thể gọi paid() hoặc quantity() trên String.
// lines.stream().map(SaleLine::sku).filter(sku -> sku.paid()) ...
```

**Bài học:** thứ tự `filter` và `map` không tùy ý đổi được nếu phép ánh xạ **làm mất dữ liệu cần cho điều kiện lọc**. Nếu muốn lọc theo chuỗi SKU, hãy viết predicate tương ứng với kiểu `String`.

## 8. Các trường hợp cần kiểm tra khi chuyển đổi

| Trường hợp | Vòng `for` | Pipeline Stream | Điều cần khẳng định |
| --- | --- | --- | --- |
| Nguồn rỗng | Không vào thân vòng lặp | `sum()` không có số cần cộng | Cả hai trả 0 với biến tích lũy ban đầu là 0. |
| Không có phần tử đạt điều kiện | Bỏ qua mọi lần cộng | `filter` tạo Stream rỗng | Tổng vẫn là 0. |
| Có phần tử trùng SKU | Xử lý từng dòng | `filter`/`mapToLong` xử lý từng dòng | Không tự gọi `distinct()` nếu nghiệp vụ không yêu cầu. |
| Đảo thứ tự nguồn | Tổng cộng không đổi khi không overflow | `sum` trên số nguyên cũng vậy | Danh sách nhãn theo encounter order có thể đổi. |
| `unitPriceVnd` rất lớn | Có thể tràn `long` | `sum()` cũng có thể tràn `long` | Không đồng nhất Stream với cơ chế chống overflow. |
| Phần tử nguồn `null` | Gọi getter trên null có thể lỗi | Lambda gọi getter trên null cũng có thể lỗi | Quy định chính sách xử lý null trước khi biến đổi. |
| Stream song song | Không áp dụng tự động | Lambda có thể chạy trên nhiều thread | Tránh trạng thái mutable dùng chung và giữ phép gộp phù hợp. |

### Xử lý `null` có chủ đích

Nếu nguồn cho phép chứa phần tử `null`, hãy quyết định xem cần **loại bỏ** hay **báo lỗi**. Ví dụ lọc null trước:

```java
import java.util.Objects;

long total = lines.stream()
        .filter(Objects::nonNull)
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line ->
                (long) line.quantity() * line.unitPriceVnd())
        .sum();
```

Nếu null là lỗi nhập liệu, bỏ qua nó một cách âm thầm có thể che giấu vấn đề; khi đó nên validate hoặc dùng `Objects.requireNonNull` để báo lỗi rõ ràng. `List.of(...)` không cho phép phần tử null, nhưng các loại nguồn khác có thể có.

## 9. Tràn số nguyên và yêu cầu tính tổng an toàn

Việc chuyển vòng lặp sang `sum()` không mặc nhiên thay đổi quy tắc số học. Ví dụ:

```java
int wrong = java.util.stream.IntStream
        .of(2_000_000_000, 2_000_000_000)
        .sum();
System.out.println(wrong); // -294967296, tràn int

long correct = java.util.stream.IntStream
        .of(2_000_000_000, 2_000_000_000)
        .asLongStream()
        .sum();
System.out.println(correct); // 4000000000
```

`LongStream.sum()` cũng có thể tràn nếu kết quả vượt miền `long`. Nếu bài toán yêu cầu **phát hiện** thay vì âm thầm để tràn, có thể dùng `Math.addExact` trong `reduce`, và `Math.multiplyExact` khi tính thành tiền:

```java
long totalExact = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line -> Math.multiplyExact(
                (long) line.quantity(), line.unitPriceVnd()))
        .reduce(0L, Math::addExact);
```

Với dữ liệu mẫu, `totalExact == 64_000L`. Khi phép nhân hoặc phép cộng vượt phạm vi `long`, `Math.multiplyExact`/`Math.addExact` ném `ArithmeticException`. Nếu đầu vào có thể vượt cả `long`, hãy cân nhắc `BigInteger` hoặc mô hình tiền tệ thích hợp, chứ không tự chuyển sang `double` để tránh overflow.

### Chú ý phép ép kiểu ở vị trí nào

```java
int quantity = 100_000;
int price = 100_000;

long wrong = quantity * price;        // Tràn int TRƯỚC khi gán long.
long right = (long) quantity * price; // Tính bằng long: 10000000000.
```

Một lỗi tương tự có thể xảy ra trong `mapToLong(line -> line.quantity() * line.price())` khi cả hai getter trả `int`. Hãy kiểm tra kiểu của **các toán hạng** chứ không chỉ kiểu biến đích hoặc phương thức `mapToLong`.

## 10. Thứ tự kết quả và hiệu năng của pipeline

Với `List` là nguồn có encounter order, pipeline `filter(...).map(...).toList()` giữ thứ tự các phần tử còn lại. Nhưng **tính tổng** không cung cấp một danh sách có thứ tự; chỉ cần biết tổng số học trong miền số hợp lệ.

```java
List<String> labels = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .map(line -> line.sku() + " x" + line.quantity())
        .toList();
// [PEN x3, ERASER x4]
```

Nếu thêm `sorted()`, danh sách sẽ được sắp theo thứ tự từ điển của nhãn, **không còn phản ánh thứ tự xuất hiện ban đầu**. Chỉ sắp xếp khi đây là yêu cầu; `distinct()` chỉ nên dùng khi nghiệp vụ cho phép bỏ các phần tử được xem là trùng.

### Có nên dùng `parallelStream()` để nhanh hơn?

```java
long totalParallel = lines.parallelStream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line ->
                (long) line.quantity() * line.unitPriceVnd())
        .sum();
```

Đây là phép tổng hợp có tính kết hợp trên `long` theo ngữ nghĩa Java, nên với dữ liệu mẫu kết quả là `64_000L`. Tuy nhiên, song song tạo chi phí chia nguồn, lập lịch và gộp; với danh sách nhỏ, nó thường không có lợi. Các phép biến đổi nên độc lập, không sửa danh sách nguồn hay một biến tổng dùng chung. Không thay thế `sum()` bằng `parallelStream().forEach(line -> sharedTotal += ...)` khi `sharedTotal` là biến chung: đó là race condition.

Độ phức tạp duyệt thông thường của cả vòng `for` và `filter → mapToLong → sum` trên một danh sách hữu hạn là **O(n)** thời gian, ngoài các chi phí của predicate và mapper. `sum` chỉ giữ trạng thái cộng dồn nhỏ; còn `filter(...).map(...).toList()` phải tạo danh sách kết quả với bộ nhớ tăng theo số phần tử được giữ.

Đừng chỉ nhìn số dòng mã để kết luận cách nào nhanh hơn. **Hãy chọn cách dễ kiểm tra tính đúng**, sau đó đo hiệu năng bằng dữ liệu thực tế nếu đây là một điểm nghẽn.

## 11. Lỗi thường gặp khi chuyển vòng lặp sang Stream

| Lỗi | Vì sao sai | Hướng khắc phục |
| --- | --- | --- |
| Viết `map(...).sum()` trên `Stream<Long>` | `Stream<T>` không có `sum()`. | Dùng `mapToLong(...).sum()` hoặc `reduce` phù hợp. |
| `map` thành SKU trước khi lọc theo `paid` | Mất các trường cần để lọc. | `filter` khi còn `SaleLine`, rồi `map` ra SKU. |
| Dùng `distinct()` trước `sum()` chỉ vì SKU trùng | Làm mất dòng bán hàng hợp lệ. | Không loại trùng nếu bài toán tính theo từng dòng. |
| Nhân hai `int` rồi gán vào `long` | Có thể tràn trước khi ép kiểu. | Ép `long` trước phép nhân hoặc dùng `Math.multiplyExact`. |
| Gọi `sum()` rồi cố dùng lại cùng Stream | Terminal operation tiêu thụ Stream. | Gọi `lines.stream()` mới hoặc chọn collector phù hợp. |
| Dùng `findFirst()` để lấy tổng | Chỉ lấy tối đa một phần tử. | Dùng `sum()`/`reduce` cho phép cộng toàn bộ. |
| Dùng `peek` để tăng biến tổng | Side effect khó kiểm soát, có thể bị tối ưu hoặc race. | Diễn đạt cộng dồn bằng terminal operation. |
| Cho rằng Stream luôn nhanh hơn vòng `for` | Pipeline có chi phí tạo và vận hành; parallel còn thêm chi phí chia/gộp. | Đo trên dữ liệu đại diện nếu hiệu năng quan trọng. |
| Không xét nguồn rỗng | Dự đoán sai giá trị mặc định. | `sum()` trả 0; với `average()`/`min()` cần xử lý `Optional`. |
| Tự sửa collection nguồn trong `filter` | Vi phạm non-interference, có thể gây hành vi lỗi. | Duyệt nguồn ổn định, biến đổi đầu ra thay vì sửa đầu vào. |

## 12. Bài tập kiểm tra cuối bài

**Câu 1.** Từ `IntStream.rangeClosed(1, 10)`, lấy số chia hết cho 3, nhân đôi rồi tính tổng. Kết quả?

```java
int total = java.util.stream.IntStream.rangeClosed(1, 10)
        .filter(n -> n % 3 == 0)
        .map(n -> n * 2)
        .sum();
// (3 + 6 + 9) * 2 = 36
```

**Câu 2.** Nếu tất cả `SaleLine` đều `paid == false`, pipeline ở mục 3 trả giá trị gì?

**Đáp án:** `0L`. Sau `filter` không còn phần tử, nên `LongStream.sum()` trả phần tử trung hòa của phép cộng.

**Câu 3.** Tại sao `lines.stream().map(SaleLine::sku).filter(line -> line.paid())` không biên dịch?

**Đáp án:** Sau `map(SaleLine::sku)`, phần tử đã là `String`; `String` không có phương thức `paid()`. Muốn lọc theo trạng thái, làm trước bước `map`.

**Câu 4.** Khi đã có vòng lặp tính tổng chính xác và pipeline cho cùng kết quả với dữ liệu mẫu, đã đủ chứng minh hai cách luôn tương đương chưa?

**Đáp án:** Chưa. Cần thêm dữ liệu rỗng, không thỏa điều kiện, giá trị lớn, mã trùng và kiểm tra xem phiên bản Stream có vô tình thay đổi quy tắc lọc, kiểu số hay thứ tự khi trả danh sách không.

**Câu 5.** Khi cần giá trị trung bình của các dòng phù hợp thay vì tổng, đổi `sum()` thành gì và vì sao cần kiểm tra kết quả?

```java
var maybeAverage = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line ->
                (long) line.quantity() * line.unitPriceVnd())
        .average();
```

**Đáp án:** `average()` trả `OptionalDouble`, vì không có giá trị trung bình khi không có phần tử đạt điều kiện. Không gọi `getAsDouble()` trên Optional rỗng mà chưa kiểm tra; chỉ dùng `orElse(0.0)` khi nghiệp vụ quy định 0 là giá trị mặc định thích hợp.

**Câu 6.** Có thể giữ nguyên một Stream rồi tính vừa tổng vừa số dòng bằng hai terminal operation trên cùng biến không?

**Đáp án:** Không. Một đối tượng Stream chỉ dùng cho một terminal operation. Nếu nguồn là `List`, tạo hai Stream mới; nếu nguồn không tái duyệt được, cần cách tích lũy nhiều chỉ số trong một lượt.

## Ghi nhớ

- Chuyển `for` sang Stream bằng cách **tách đúng thao tác**: điều kiện trong `if` thành `filter`, phép tính của từng dòng thành `map`/`mapToLong`, cộng dồn thành `sum` hoặc `reduce`.
- `filter` và `map` thường lazy; `sum` là terminal operation và tiêu thụ Stream. Dùng `mapToInt`/`mapToLong` khi cần tổng số nguyên thủy.
- Đặt đúng thứ tự các bước: lọc trước khi làm mất dữ liệu cần kiểm tra; không tự `distinct()` hay `sorted()` nếu nghiệp vụ không yêu cầu.
- Trường hợp rỗng, kiểu số, nguy cơ overflow, nguồn có phần tử null và tính không can thiệp phải được xét **trong cả bản vòng lặp lẫn bản Stream**.
- Đối chiếu hai lời giải bằng kiểm thử có thể lặp lại; ưu tiên **tính đúng và sự rõ ràng** trước khi tối ưu hoặc chuyển sang song song.
