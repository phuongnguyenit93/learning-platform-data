# `isEmpty()` của `OptionalInt`, `OptionalLong` và `OptionalDouble` trong Java 11

## 1. Mục tiêu bài học

Khi tính toán, tra cứu hoặc xử lý dữ liệu số, một kết quả có thể **không tồn tại**: tìm giá trị lớn nhất trong danh sách rỗng, tìm bản ghi theo ID nhưng không thấy, hoặc tính trung bình của tập không có phần tử. Trả về `0`, `-1` hoặc `NaN` để biểu diễn “không có kết quả” thường không an toàn, vì những giá trị đó có thể là dữ liệu thật hoặc có ý nghĩa riêng.

Java cung cấp ba kiểu chứa giá trị nguyên thủy có thể vắng mặt:

- `java.util.OptionalInt`: chứa **một `int`** hoặc không chứa giá trị.
- `java.util.OptionalLong`: chứa **một `long`** hoặc không chứa giá trị.
- `java.util.OptionalDouble`: chứa **một `double`** hoặc không chứa giá trị.

Từ **Java 11**, cả ba có thêm phương thức **`boolean isEmpty()`** để hỏi trực tiếp **“có phải không có giá trị không?”**. Phương thức này vẫn được hỗ trợ trên các bản JDK hiện đại, nên là kiến thức hữu ích cho dự án Java hiện nay. Các đoạn mã trong bài dùng API tương thích Java 11.

Sau khi học, bạn có thể: phân biệt “vắng mặt” và “giá trị bằng 0”; dùng `isEmpty()` đúng trên ba lớp; chọn `orElse`, `orElseGet`, `orElseThrow` hoặc `ifPresentOrElse` khi cần; đọc kết quả từ primitive streams; và tránh lỗi phổ biến khi xử lý `Optional`.

## 2. Hiểu chính xác `isEmpty()`

Cả ba lớp đều có hai trạng thái:

1. **Present**: đối tượng đang chứa một giá trị nguyên thủy thuộc kiểu tương ứng, kể cả `0`, số âm hoặc `Double.NaN`.
2. **Empty**: đối tượng không chứa giá trị nào.

`isEmpty()` trả về `true` **chỉ khi trạng thái là empty**; nếu có giá trị, nó trả về `false`. Nó **không** đánh giá số đang chứa là “hợp lệ”, “dương”, “khác 0” hay “không phải NaN”.

| Biểu thức Java | `isEmpty()` | Lý do |
| --- | --- | --- |
| `OptionalInt.empty()` | `true` | Không chứa `int` |
| `OptionalInt.of(0)` | `false` | Số `0` vẫn là một giá trị |
| `OptionalInt.of(-1)` | `false` | Số âm vẫn hiện diện |
| `OptionalLong.empty()` | `true` | Không chứa `long` |
| `OptionalLong.of(0L)` | `false` | Giá trị `0L` vẫn hiện diện |
| `OptionalLong.of(Long.MIN_VALUE)` | `false` | Không có chuyện “giá trị cực tiểu” tự thành empty |
| `OptionalDouble.empty()` | `true` | Không chứa `double` |
| `OptionalDouble.of(0.0)` | `false` | `0.0` vẫn có mặt |
| `OptionalDouble.of(Double.NaN)` | `false` | NaN là giá trị `double`, không phải trạng thái empty |
| `OptionalDouble.of(Double.POSITIVE_INFINITY)` | `false` | Vô cực vẫn là giá trị `double` |

Tạo giá trị rỗng bằng `OptionalInt.empty()`, `OptionalLong.empty()` hoặc `OptionalDouble.empty()`. Tạo giá trị hiện diện bằng `OptionalInt.of(int)`, `OptionalLong.of(long)` hoặc `OptionalDouble.of(double)`.

Ví dụ:

```java
OptionalInt missingCount = OptionalInt.empty();
OptionalInt actualZero = OptionalInt.of(0);

System.out.println(missingCount.isEmpty()); // true
System.out.println(actualZero.isEmpty());    // false
```

Đây là **trích đoạn đặt trong một phương thức** và cần `import java.util.OptionalInt;`. Việc phân biệt empty với `0` rất quan trọng: “chưa có số lượng” và “số lượng chính xác bằng 0” không phải một dữ liệu.

### Quan hệ với `isPresent()`

Ba lớp đều có:

- `isPresent()`: `true` nếu **có** giá trị.
- `isEmpty()`: `true` nếu **không có** giá trị.

Vì thế, với một đối tượng `x` không null:

```java
x.isEmpty() == !x.isPresent()
```

Dòng trên là **biểu thức mô tả quan hệ logic**, trong đó `x` phải có kiểu `OptionalInt`, `OptionalLong` hoặc `OptionalDouble`. Trong điều kiện kiểm tra trường hợp thiếu dữ liệu, `if (value.isEmpty())` thể hiện ý định trực tiếp, đọc tự nhiên hơn việc phủ định `isPresent()`.

`isEmpty()` **được bổ sung trong Java 11** cho các kiểu trên. Nếu mã nguồn bắt buộc được biên dịch cho JDK cũ hơn, lời gọi này không tồn tại; bài này tập trung vào Java 11 và các API hiện vẫn dùng được trên những bản JDK mới.

## 3. Ba kiểu `Optional` nguyên thủy: giống nhau ở điểm nào?

| Thành phần | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| --- | --- | --- | --- |
| Kiểu giá trị | `int` | `long` | `double` |
| Tạo rỗng | `OptionalInt.empty()` | `OptionalLong.empty()` | `OptionalDouble.empty()` |
| Tạo có giá trị | `OptionalInt.of(12)` | `OptionalLong.of(12L)` | `OptionalDouble.of(12.5)` |
| Kiểm tra thiếu | `isEmpty()` | `isEmpty()` | `isEmpty()` |
| Kiểm tra có | `isPresent()` | `isPresent()` | `isPresent()` |
| Lấy giá trị trực tiếp | `getAsInt()` | `getAsLong()` | `getAsDouble()` |
| Có mặc định | `orElse(int)` | `orElse(long)` | `orElse(double)` |
| Tính mặc định khi cần | `orElseGet(IntSupplier)` | `orElseGet(LongSupplier)` | `orElseGet(DoubleSupplier)` |
| Thiếu thì báo lỗi | `orElseThrow(...)` | `orElseThrow(...)` | `orElseThrow(...)` |
| Đưa vào primitive stream | `IntStream stream()` | `LongStream stream()` | `DoubleStream stream()` |

Đây là các **lớp riêng biệt**, không phải lớp con của `Optional<T>`. Ví dụ, `OptionalInt` không phải là `Optional<Integer>`; bạn không thể gán hai kiểu này cho nhau mà không chuyển đổi. Các lớp primitive optional tránh phải bọc mỗi giá trị `int`, `long` hoặc `double` trong `Integer`, `Long`, `Double` khi API chỉ cần kết quả số đơn giản, đặc biệt khi làm việc với `IntStream`, `LongStream`, `DoubleStream`.

Tuy nhiên, **không mặc định primitive optional luôn nhanh hơn trong mọi hệ thống**. Hãy chọn theo kiểu dữ liệu và giao diện công khai, rồi benchmark nếu hiệu năng thực sự là yêu cầu quan trọng.

Cả ba là **value-based classes**. Không dùng `==` để so sánh trạng thái của hai instance, không khóa đồng bộ `synchronized` trên chúng, và không giả định `empty()` trả về đúng một instance toàn cục. Sử dụng `isEmpty()`/`isPresent()` để hỏi trạng thái và `equals()` nếu cần so sánh nội dung theo ngữ nghĩa của lớp.

## 4. Chương trình Java 11 hoàn chỉnh minh họa cả ba kiểu

Tạo tệp **`PrimitiveOptionalIsEmptyDemo.java`**:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveOptionalIsEmptyDemo {

    public static void main(String[] args) {
        OptionalInt missingCount = OptionalInt.empty();
        OptionalInt zeroCount = OptionalInt.of(0);

        OptionalLong missingId = LongStream.empty().max();
        OptionalLong negativeId = OptionalLong.of(-1L);

        OptionalDouble missingAverage = DoubleStream.empty().average();
        OptionalDouble notANumber = OptionalDouble.of(Double.NaN);

        System.out.println("int empty: " + missingCount.isEmpty());
        System.out.println("int zero empty: " + zeroCount.isEmpty());
        System.out.println("long empty: " + missingId.isEmpty());
        System.out.println("long -1 empty: " + negativeId.isEmpty());
        System.out.println("double empty: " + missingAverage.isEmpty());
        System.out.println("double NaN empty: " + notANumber.isEmpty());

        OptionalInt maximum = IntStream.of(3, 7, 4).max();
        System.out.println("max: " + maximum.orElseThrow());

        System.out.println("fallback: " + missingCount.orElse(99));
        System.out.println("zero fallback: " + zeroCount.orElse(99));
        System.out.println("zero stream size: " + zeroCount.stream().count());
    }
}
```

Biên dịch và chạy bằng **JDK 11** (hoặc JDK mới hơn có hỗ trợ biên dịch `--release 11`):

```bash
javac --release 11 -encoding UTF-8 PrimitiveOptionalIsEmptyDemo.java
java PrimitiveOptionalIsEmptyDemo
```

Kết quả chính xác:

```text
int empty: true
int zero empty: false
long empty: true
long -1 empty: false
double empty: true
double NaN empty: false
max: 7
fallback: 99
zero fallback: 0
zero stream size: 1
```

Giải thích:

1. `OptionalInt.empty()`, kết quả `LongStream.empty().max()` và `DoubleStream.empty().average()` đều không có phần tử, nên `isEmpty()` là `true`.
2. `OptionalInt.of(0)`, `OptionalLong.of(-1L)` và `OptionalDouble.of(Double.NaN)` đều được tạo bằng `of(...)`, nên `isEmpty()` là `false`. Chúng có thể mang giá trị không phù hợp với một nghiệp vụ cụ thể, nhưng không bị coi là vắng mặt.
3. `IntStream.of(3, 7, 4).max()` tạo `OptionalInt` chứa số lớn nhất `7`; `orElseThrow()` lấy `7` vì giá trị có mặt.
4. `missingCount.orElse(99)` trả `99` do thiếu dữ liệu; `zeroCount.orElse(99)` vẫn trả `0` vì `0` là dữ liệu thật.
5. `zeroCount.stream().count()` là `1`: primitive optional hiện diện chuyển thành stream **một** phần tử. Nếu dùng `missingCount.stream().count()`, kết quả sẽ bằng `0`.

Chương trình dùng duy nhất `java.base` và không yêu cầu mạng, database hay thư viện bên ngoài.

## 5. Khi nào nên dùng `isEmpty()` trong xử lý nghiệp vụ?

### 5.1. Trả về “không tìm thấy số” một cách rõ ràng

Ví dụ cần tìm số dương đầu tiên trong một mảng. Vì `0` cũng có thể là phần tử trong mảng, không nên dùng `0` để mô tả trường hợp không tìm thấy số dương.

```java
static OptionalInt firstPositive(int[] values) {
    return java.util.Arrays.stream(values)
            .filter(value -> value > 0)
            .findFirst();
}
```

Đây là **phương thức minh họa đặt trong một lớp**, cần import `java.util.OptionalInt`. Lời gọi:

```java
OptionalInt found = firstPositive(new int[] {-3, 0, -1});
if (found.isEmpty()) {
    System.out.println("Khong tim thay so duong");
} else {
    System.out.println("Gia tri: " + found.orElseThrow());
}
```

Kết quả:

```text
Khong tim thay so duong
```

Sự vắng mặt được biểu diễn bằng trạng thái `empty`, không bị gán nhầm cho `0` hoặc `-1`. Khi có giá trị, nhánh `else` có thể sử dụng `orElseThrow()` để lấy giá trị, vì điều kiện ngay trước đó đã xác nhận nó có mặt.

### 5.2. Kết quả thống kê trên tập dữ liệu rỗng

Nhiều phép toán cuối của primitive stream trả về optional:

| Phép toán | Kiểu trả về | Ví dụ tập nguồn rỗng |
| --- | --- | --- |
| `IntStream.max()` | `OptionalInt` | `OptionalInt.empty()` |
| `IntStream.min()` | `OptionalInt` | `OptionalInt.empty()` |
| `IntStream.findFirst()` | `OptionalInt` | `OptionalInt.empty()` |
| `LongStream.max()` | `OptionalLong` | `OptionalLong.empty()` |
| `LongStream.findAny()` | `OptionalLong` | `OptionalLong.empty()` |
| `DoubleStream.min()` | `OptionalDouble` | `OptionalDouble.empty()` |
| `IntStream.average()` | `OptionalDouble` | `OptionalDouble.empty()` |
| `LongStream.average()` | `OptionalDouble` | `OptionalDouble.empty()` |
| `DoubleStream.average()` | `OptionalDouble` | `OptionalDouble.empty()` |

Chú ý: `IntStream.average()` trả về **`OptionalDouble`**, không phải `OptionalInt`, bởi trung bình cộng có thể là số thực.

```java
OptionalDouble average = java.util.stream.IntStream.empty().average();

if (average.isEmpty()) {
    System.out.println("Khong the tinh trung binh: khong co phan tu");
}
```

Kết quả:

```text
Khong the tinh trung binh: khong co phan tu
```

**Phân biệt với `sum()` và `count()`:** `IntStream.empty().sum()` trả số `0`, `IntStream.empty().count()` trả số `0L`, nhưng chúng **không** trả `Optional`. Lựa chọn API tùy mục đích: tổng của tập rỗng có phần tử trung hòa là `0`; giá trị cực đại hoặc trung bình của tập rỗng không có giá trị xác định theo cùng cách.

### 5.3. Không dùng `isEmpty()` để xác minh tính hợp lệ của số

Ví dụ `OptionalDouble.of(Double.NaN).isEmpty()` là `false`. Nếu yêu cầu nghiệp vụ cấm NaN hoặc vô cực, bạn phải **xác thực thêm giá trị sau khi biết nó hiện diện**:

```java
OptionalDouble rate = OptionalDouble.of(Double.NaN);

if (rate.isEmpty()) {
    System.out.println("Rate missing");
} else {
    double value = rate.orElseThrow();
    if (!Double.isFinite(value)) {
        System.out.println("Rate invalid");
    } else {
        System.out.println("Rate valid");
    }
}
```

Kết quả:

```text
Rate invalid
```

`Double.isFinite` trả `false` cho NaN và vô cực; API này vẫn có trên Java 11. Nếu chỉ cấm NaN nhưng cho phép vô cực, sử dụng chính sách khác; không tự mặc định mọi dữ liệu `double` phải finite.

## 6. Sau khi `isEmpty()`, xử lý thế nào?

### 6.1. `orElse(...)`: trả giá trị dự phòng

`orElse` nhận một giá trị primitive cùng kiểu:

```java
int count = OptionalInt.empty().orElse(0);
long timeoutMillis = OptionalLong.empty().orElse(5000L);
double ratio = OptionalDouble.empty().orElse(1.0);
```

Đoạn trên là **trích đoạn** cần import ba lớp. Dùng giá trị mặc định **chỉ khi nghiệp vụ quy định rõ**; nếu `0` có thể làm mất thông tin “chưa có số liệu”, nên hiển thị trạng thái “chưa có dữ liệu” hoặc truyền tiếp `Optional` thay vì tự gán mặc định.

### 6.2. `orElseGet(...)`: chỉ tính dự phòng khi thiếu

`orElseGet` nhận supplier primitive: `IntSupplier`, `LongSupplier` hoặc `DoubleSupplier`. Supplier được gọi khi optional rỗng; nếu đã có giá trị, phần tính dự phòng không chạy.

```java
OptionalInt existing = OptionalInt.of(12);
int result = existing.orElseGet(() -> {
    System.out.println("Tinh gia tri du phong");
    return 99;
});
System.out.println(result);
```

Kết quả:

```text
12
```

Không có dòng “Tinh gia tri du phong” vì `existing` có giá trị. Với `OptionalInt.empty().orElseGet(...)`, supplier mới được thực thi. Cơ chế lazy này hữu ích khi giá trị dự phòng phải truy vấn, tính toán hoặc lấy từ nguồn khác, nhưng nên giữ supplier đơn giản và có kiểm soát tác dụng phụ.

### 6.3. `orElseThrow(...)`: vắng mặt là lỗi

Có hai biến thể hữu ích:

- `orElseThrow()`: trả giá trị nếu có, nếu rỗng thì ném `NoSuchElementException`.
- `orElseThrow(() -> new IllegalStateException(...))`: trả giá trị nếu có, nếu rỗng ném lỗi do bạn xác định.

```java
OptionalLong orderId = OptionalLong.empty();

try {
    long id = orderId.orElseThrow(
            () -> new IllegalStateException("Missing order id"));
    System.out.println(id);
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage());
}
```

Kết quả:

```text
Missing order id
```

Đây là trích đoạn cần import `java.util.OptionalLong`. Trong code thực tế, chọn loại exception hoặc kiểu trả về phù hợp hợp đồng API; đừng biến “không tìm thấy” vốn là tình huống bình thường thành lỗi hệ thống một cách tùy tiện.

### 6.4. `ifPresentOrElse(...)`: thực thi một trong hai nhánh

Khi mục tiêu là **hành động** thay vì cần một giá trị trả về, `ifPresentOrElse` thường rõ ràng:

```java
OptionalDouble temperature = OptionalDouble.empty();

temperature.ifPresentOrElse(
        value -> System.out.println("Temperature: " + value),
        () -> System.out.println("No reading"));
```

Kết quả:

```text
No reading
```

`ifPresentOrElse` có từ Java 9 và sử dụng được trên Java 11. `ifPresent` chỉ chạy hành động khi có giá trị, không có nhánh empty. Không cần thêm điều kiện `isEmpty()` trước `ifPresentOrElse` nếu chính hành động này đã diễn đạt đầy đủ hai trường hợp.

### 6.5. `stream()`: tích hợp vào luồng xử lý nguyên thủy

`stream()` của `OptionalInt`, `OptionalLong` và `OptionalDouble` lần lượt trả về `IntStream`, `LongStream`, `DoubleStream`; mỗi stream có **0 hoặc 1 phần tử**. API này có từ Java 9 và vẫn hữu ích trên JDK hiện đại.

```java
long count = java.util.stream.Stream.of(
        OptionalInt.of(5),
        OptionalInt.empty(),
        OptionalInt.of(0))
        .flatMapToInt(OptionalInt::stream)
        .count();
System.out.println(count);
```

Kết quả:

```text
2
```

Cả `5` và `0` đều là phần tử hợp lệ; chỉ optional empty bị bỏ qua. Cách này hữu ích khi gộp nhiều kết quả optional thành một stream primitive; với một giá trị đơn lẻ, gọi `ifPresent`, `orElse` hoặc `isEmpty` thường dễ đọc hơn.

## 7. Thiết kế API: khi nào nên trả về primitive optional?

**Phù hợp:** phương thức trả về đúng **một kết quả số có thể không tồn tại**; ví dụ tìm ID số trong nguồn dữ liệu, tìm lần đo cuối cùng, tìm cực đại/cực tiểu, lấy thống kê từ tập có thể rỗng.

```java
static OptionalLong lastEventId(long[] ids) {
    return java.util.Arrays.stream(ids).max();
}
```

Đây là phương thức minh họa đặt trong một lớp, cần import `java.util.OptionalLong`. Nếu `ids` là mảng rỗng, kết quả là `OptionalLong.empty()`; nếu chứa ID, kết quả là `OptionalLong` có giá trị cực đại. Tên `lastEventId` chỉ đúng nếu hợp đồng quy định ID lớn nhất đồng nghĩa sự kiện gần nhất; nếu không, nên đặt tên `maxEventId`. Với nghiệp vụ cần “sự kiện cuối trong thứ tự”, phải tìm theo thứ tự thay vì dùng `max()`.

**Không phù hợp nếu:** cần phân biệt nhiều lý do thất bại (timeout, bị từ chối, dữ liệu sai, không tìm thấy), cần thông tin lỗi đầy đủ hoặc cần biểu diễn một tập kết quả. Một `OptionalInt.empty()` chỉ nói **không có giá trị**, không mang mã lỗi hay thông điệp. Trường hợp ấy cần exception phù hợp hoặc kiểu kết quả nghiệp vụ riêng.

**Không tự ý sử dụng làm tham số hoặc trường trong mô hình lưu trữ:** các Optional được thiết kế chủ yếu cho kiểu trả về. Nếu muốn dùng `OptionalInt` làm field trên entity, DTO hoặc đối tượng được serialize, hãy kiểm tra hỗ trợ của ORM/JSON mapper và hợp đồng dữ liệu; nhiều hệ thống xử lý dữ liệu thiếu giá trị bằng thiết kế nullable hoặc mô hình riêng tại biên. Đối với phương thức nhận tham số, thường đơn giản hơn nếu đối số cần thiết là `int` và sự vắng mặt được mô tả bằng một overload hoặc kiểu có ý nghĩa rõ ràng.

**Không truyền `null` thay cho một Optional:** một biến kiểu `OptionalInt`, `OptionalLong` hoặc `OptionalDouble` nên luôn trỏ tới một instance thực sự; dùng `empty()` để biểu diễn không có số. Gọi `isEmpty()` trên tham chiếu `null` sẽ ném `NullPointerException`.

## 8. `OptionalInt` so với `Optional<Integer>`

Cả hai đều có `isEmpty()` trên Java 11, nhưng không tương đương về kiểu:

| Chủ đề | Primitive optional | Generic optional |
| --- | --- | --- |
| Ví dụ | `OptionalInt` | `Optional<Integer>` |
| Dữ liệu | `int` nguyên thủy | `Integer` được bọc |
| Giá trị rỗng | `OptionalInt.empty()` | `Optional.empty()` |
| Lấy giá trị | `orElseThrow()` cho `int` | `orElseThrow()` cho `Integer` |
| Supplier dự phòng | `IntSupplier` | `Supplier<Integer>` |
| Stream | `IntStream` | `Stream<Integer>` |
| Các phép biến đổi kiểu `map/filter/flatMap` | **Không có** trực tiếp như `Optional<T>` | Có theo API `Optional<T>` |

Nếu mục tiêu là chỉ nhận hoặc không nhận một giá trị `int`, `OptionalInt` thường diễn đạt rõ ràng và tránh boxing của giá trị. Nếu cần chuỗi phép biến đổi đối tượng hoặc tích hợp API dùng generic `Optional<T>`, chọn kiểu tương ứng và cân nhắc chuyển đổi rõ ràng.

Chẳng hạn, biến `OptionalInt value` không có phương thức `value.map(...)` tương ứng với `Optional<Integer>.map(...)`. Bạn có thể sử dụng `value.stream().map(...).findFirst()` khi phù hợp với loại phép biến đổi, hoặc viết điều kiện thông thường. Không suy ra rằng mọi phương thức của `Optional<T>` đều xuất hiện trên ba loại primitive optional.

## 9. Lỗi phổ biến cần tránh

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Coi `OptionalInt.of(0)` là empty | Phân biệt sai “0 thật” và “chưa có dữ liệu” | `isEmpty()` kiểm tra trạng thái container |
| Coi `Double.NaN` là empty | Lọc sai dữ liệu số chưa hợp lệ | Kiểm tra `Double.isNaN` hoặc `Double.isFinite` độc lập |
| Gọi `getAsInt()` khi optional rỗng | `NoSuchElementException` | Dùng `orElse`/`orElseThrow` hoặc kiểm tra trạng thái trước |
| Gán mặc định `0` cho mọi trường hợp thiếu | Có thể làm méo thống kê và quyết định nghiệp vụ | Xác định rõ chính sách cho giá trị thiếu |
| So sánh `OptionalLong.empty() == another` | Phụ thuộc identity không được đảm bảo | Dùng `isEmpty()` hoặc `equals` |
| Dùng `null` làm Optional | Gọi `isEmpty()` gây `NullPointerException` | Trả về `empty()` |
| Tưởng `OptionalInt` hỗ trợ `map` như generic `Optional<T>` | Code không biên dịch | Dùng stream thích hợp hoặc thao tác rõ ràng |
| Tưởng `IntStream.average()` trả `OptionalInt` | Sai kiểu dữ liệu | `average()` trả `OptionalDouble` |
| Dùng primitive optional để chứa thông tin lỗi chi tiết | Không biết vì sao thiếu dữ liệu | Dùng result type hoặc exception phù hợp |
| Dùng `isEmpty()` nhưng yêu cầu biên dịch Java 8 | Method không tồn tại ở source/API mục tiêu | Dùng Java 11+ hoặc giải pháp theo yêu cầu runtime |
| Gọi `orElseThrow()` không có phương án xử lý empty | Exception ngoài dự kiến | Thiết kế nhánh empty hoặc hợp đồng ném lỗi rõ |
| Tối ưu chỉ dựa vào chữ “primitive” | Lựa chọn API thiếu căn cứ | Đo benchmark thực tế nếu cần tối ưu hiệu năng |

### Không lạm dụng việc lấy giá trị trực tiếp

Các phương thức `getAsInt()`, `getAsLong()` và `getAsDouble()` trả về dữ liệu khi có, nhưng ném `NoSuchElementException` khi optional rỗng. Với code cần báo lỗi khi thiếu, `orElseThrow()` biểu thị ý định rõ hơn; với code đã kiểm tra bằng `isEmpty()`, cả hai đều lấy được giá trị theo hợp đồng nhưng không cần tạo thói quen gọi `getAs...()` mà không biết trạng thái.

### Không nhầm `isEmpty()` với các API khác

`String.isEmpty()` hỏi chuỗi có độ dài bằng 0; `Collection.isEmpty()` hỏi tập hợp có 0 phần tử; `OptionalInt.isEmpty()` hỏi **container có vắng giá trị số hay không**. Các phương thức trùng tên nhưng áp dụng cho **loại dữ liệu khác nhau**. Một chuỗi `"0"` có ký tự nên không rỗng; một `OptionalInt.of(0)` có giá trị nên cũng không rỗng, nhưng lý do là khác nhau.

## 10. Checklist xử lý giá trị số có thể vắng mặt

Khi thiết kế một phương thức trả về số tùy chọn, hãy trả lời:

1. Có thật sự xảy ra trạng thái “không có số”, hay `0` là giá trị mặc định có ý nghĩa nghiệp vụ?
2. Nếu không có số, người gọi nên biết là thiếu (`isEmpty()`), được nhận số dự phòng (`orElse`), hay phải xử lý lỗi (`orElseThrow`)?
3. Đúng kiểu là `int`, `long` hay `double`? Kết quả trung bình thường cần `double`.
4. Nếu số có mặt, có cần kiểm tra thêm như `value >= 0`, `Double.isFinite(value)` hoặc ràng buộc phạm vi không?
5. Có đang giữ sự khác biệt giữa **giá trị không có** với **giá trị không hợp lệ** và **lỗi truy vấn** không?
6. Có test cả trường hợp nguồn rỗng, giá trị `0`, giá trị âm, `NaN` và giá trị hợp lệ bình thường chưa?
7. Có tránh trả `null` cho chính Optional và tránh so sánh identity của Optional không?

## 11. Bài tập tự kiểm tra

Hãy dự đoán kết quả của các biểu thức sau khi chạy trên Java 11:

1. `OptionalInt.of(0).isEmpty()`
2. `OptionalLong.empty().isEmpty()`
3. `OptionalDouble.of(Double.NaN).isEmpty()`
4. `java.util.stream.IntStream.empty().average().isEmpty()`
5. `java.util.stream.IntStream.of(0).max().orElse(-1)`
6. `OptionalInt.empty().stream().count()`
7. `OptionalInt.of(-1).stream().count()`
8. `OptionalDouble.empty().orElse(0.0)`

**Đáp án:** (1) `false` — số 0 hiện diện; (2) `true` — rỗng; (3) `false` — NaN vẫn hiện diện; (4) `true` — không tính được trung bình từ tập rỗng; (5) `0` — max có giá trị 0; (6) `0` — stream không phần tử; (7) `1` — số -1 là phần tử hiện diện; (8) `0.0` — lấy giá trị dự phòng.

## 12. Ghi nhớ và tài liệu tham khảo còn áp dụng

- **`isEmpty()`** của `OptionalInt`, `OptionalLong` và `OptionalDouble` trả về `true` khi không có giá trị; phương thức được thêm từ **Java 11**.
- **`0`, số âm, `NaN` và vô cực vẫn là giá trị có mặt** khi tạo bằng `of(...)`.
- Chọn `orElse` khi giá trị dự phòng đã rõ, `orElseGet` khi cần tính dự phòng theo yêu cầu, `orElseThrow` khi thiếu dữ liệu là lỗi, `ifPresentOrElse` khi cần thực thi một trong hai hành động.
- Primitive streams có thể tạo `OptionalInt`, `OptionalLong` hoặc `OptionalDouble` theo phép toán; **`average()` trả `OptionalDouble`**.
- `Optional` không thay thế validation, không mang chi tiết lỗi, không nên là `null` và không nên so sánh bằng identity.
- Ba kiểu primitive optional và `isEmpty()` tiếp tục được sử dụng trên JDK hiện đại; hãy kiểm tra mục tiêu JDK thực tế của dự án khi biên dịch.

Tài liệu API chính thức:

- [`OptionalInt`, Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/OptionalInt.html).
- [`OptionalLong`, Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/OptionalLong.html).
- [`OptionalDouble`, Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/OptionalDouble.html).
- [`Optional<T>`, Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Optional.html).
- [`OptionalInt`, Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalInt.html) để đối chiếu API trên JDK mới hơn.
