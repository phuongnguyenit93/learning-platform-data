# Java 10 — `orElseThrow()` trên `OptionalInt`, `OptionalLong` và `OptionalDouble`

## 1. Mục tiêu và phạm vi

Trong Java, một phép tính có thể **không tạo ra kết quả**: tìm số lớn nhất trên một luồng số nguyên rỗng, tìm ID trong một dãy trống, hoặc tính trung bình khi không có mẫu. Java cung cấp ba kiểu chuyên biệt để biểu diễn điều đó mà không phải dùng giá trị giả hoặc `null`:

- `OptionalInt`: có hoặc không có một giá trị `int`.
- `OptionalLong`: có hoặc không có một giá trị `long`.
- `OptionalDouble`: có hoặc không có một giá trị `double`.

**Java 10 bổ sung overload không tham số `orElseThrow()` cho cả ba kiểu này.** Khi có giá trị, phương thức trả về đúng primitive; khi không có, nó ném `NoSuchElementException`. Hành vi đó vẫn áp dụng trên các JDK hiện đại.

Bài học tập trung vào:

1. Chữ ký, kiểu trả về và ngoại lệ của ba `orElseThrow()` không tham số.
2. Phân biệt `present` với `empty`, kể cả khi giá trị thực là `0`, `0L`, `0.0` hoặc `Double.NaN`.
3. Dùng kết quả từ `IntStream`, `LongStream` và `DoubleStream` một cách an toàn.
4. So sánh với `getAsInt/getAsLong/getAsDouble`, `orElse`, `orElseGet` và overload `orElseThrow(exceptionSupplier)`.
5. Chọn chiến lược phù hợp khi thiếu kết quả: **đó là lỗi**, **có fallback hợp lệ**, hay **cần xử lý cả hai nhánh**.
6. Viết chương trình Java chạy được, kiểm thử cả nhánh thành công và nhánh ném ngoại lệ.

**Special Note:** toàn bộ nội dung được giới hạn vào những quy tắc và API vẫn phù hợp với Java hiện đại. Các API có từ phiên bản khác sẽ được ghi rõ mốc để không nhầm với tính năng gốc Java 10.

## 2. Bối cảnh phiên bản: điều gì thực sự đến từ Java 10?

| Thành phần | Xuất hiện | Vai trò |
|---|---|---|
| `OptionalInt`, `OptionalLong`, `OptionalDouble` | Java 8 | Biểu diễn giá trị primitive có thể vắng mặt |
| `getAsInt()`, `getAsLong()`, `getAsDouble()` | Java 8 | Lấy primitive khi có giá trị, nếu không có thì ném `NoSuchElementException` |
| `orElse(value)`, `orElseGet(supplier)` | Java 8 | Cung cấp fallback khi rỗng |
| `orElseThrow(exceptionSupplier)` | Java 8 | Khi rỗng, ném loại ngoại lệ do người gọi cung cấp |
| **`orElseThrow()` không tham số** | **Java 10** | Khi rỗng, ném `NoSuchElementException` mà không cần supplier |
| `isEmpty()` | Java 11 | Cách hỏi trực tiếp Optional có rỗng không |
| `OptionalInt.stream()` / tương ứng `Long`, `Double` | Java 9 | Biến 0 hoặc 1 giá trị thành primitive stream |

Như vậy, Java 10 **không** tạo ra các lớp `OptionalInt/Long/Double`. Thay đổi của Java 10 là **một phương thức đọc giá trị có tên thể hiện chính sách ném ngoại lệ**: `orElseThrow()`, đồng bộ về ý tưởng với `Optional<T>.orElseThrow()` không tham số.

Javadoc của các phương thức `getAsInt`, `getAsLong` và `getAsDouble` trên các JDK hiện đại vẫn mô tả chúng là API hợp lệ, nhưng ghi chú rằng **`orElseThrow()` là lựa chọn được ưu tiên** khi muốn thể hiện trực tiếp ý định “phải có giá trị, nếu không thì lỗi”. Không cần tuyên bố các phương thức `getAsX` đã bị xóa hoặc bị deprecated.

## 3. Chữ ký chính xác và hợp đồng

Ba phương thức Java 10:

```java
// Trong java.util.OptionalInt
public int orElseThrow()

// Trong java.util.OptionalLong
public long orElseThrow()

// Trong java.util.OptionalDouble
public double orElseThrow()
```

Đây là **chữ ký mô tả API**, không phải đoạn cần chép vào một class mới. Mỗi phương thức không nhận tham số và có hai nhánh rõ ràng:

| Đối tượng Optional | Có giá trị | Rỗng |
|---|---|---|
| `OptionalInt` | Trả primitive `int` | Ném `NoSuchElementException` |
| `OptionalLong` | Trả primitive `long` | Ném `NoSuchElementException` |
| `OptionalDouble` | Trả primitive `double` | Ném `NoSuchElementException` |

Đây là `NoSuchElementException` thuộc `java.util` và là **unchecked exception** (kế thừa `RuntimeException`). Không cần khai báo `throws NoSuchElementException` trong chữ ký phương thức gọi, nhưng cần coi rỗng là một tình huống có thể xảy ra nếu không có bất biến dữ liệu bảo đảm kết quả tồn tại.

Các lời gọi đơn giản:

```java
int count = OptionalInt.of(5).orElseThrow();           // 5
long bytes = OptionalLong.of(1_000L).orElseThrow();    // 1000L
double mean = OptionalDouble.of(2.5).orElseThrow();    // 2.5
```

Mảnh mã này đặt trong một phương thức, cần import các lớp Optional primitive. Mỗi biểu thức có kiểu primitive cụ thể; **không** nhận về đối tượng `Integer`, `Long` hoặc `Double` từ chính lời gọi `orElseThrow()`.

Ví dụ rỗng có chủ đích:

```java
OptionalInt.empty().orElseThrow();     // NoSuchElementException
OptionalLong.empty().orElseThrow();    // NoSuchElementException
OptionalDouble.empty().orElseThrow();  // NoSuchElementException
```

Nếu chạy riêng từng dòng mà không bắt ngoại lệ, phép gọi đầu tiên đã dừng đường thực thi hiện tại bằng ngoại lệ. Không nên viết ba dòng liên tiếp trong cùng ví dụ rồi kỳ vọng cả ba đều có thể thực thi khi chưa xử lý lỗi.

### 3.1. `orElseThrow()` không đi tìm một giá trị khác

Không có thao tác tìm kiếm hoặc tính toán bổ sung nào trong `orElseThrow()`. Nó chỉ xử lý **trạng thái đã có** của Optional:
- `present` → trả primitive đang chứa;
- `empty` → ném ngoại lệ.

Việc Optional có present hay empty do **cách nó được tạo** hoặc **phép toán upstream** quyết định. Chẳng hạn `IntStream.empty().max()` tạo một `OptionalInt.empty()`, còn `IntStream.of(2, 9).max()` cho giá trị 9.

### 3.2. Không có primitive mặc định tự động

`OptionalInt.empty()` **không** được chuyển ngầm thành `0`, `OptionalLong.empty()` **không** được chuyển thành `0L`, và `OptionalDouble.empty()` **không** được chuyển thành `0.0`.

Nếu số 0 có ý nghĩa nghiệp vụ là một kết quả hợp lệ, dùng `OptionalInt.of(0)` hoặc `OptionalDouble.of(0.0)`. Nếu “không có dữ liệu” khác “kết quả bằng 0”, `orElseThrow()` giúp giữ đúng khác biệt đó khi kết quả là bắt buộc.

## 4. Những nguồn Optional primitive phổ biến

Các primitive stream trong `java.util.stream` thường trả Optional khi phép tổng hợp **không có kết quả hợp lệ trên tập rỗng**:

| Phép toán | Kiểu trả về | Trên stream rỗng |
|---|---|---|
| `IntStream.max()` / `min()` / `findFirst()` | `OptionalInt` | Empty |
| `LongStream.max()` / `min()` / `findAny()` | `OptionalLong` | Empty |
| `DoubleStream.max()` / `min()` / `average()` | `OptionalDouble` | Empty |
| `IntStream.average()` | `OptionalDouble` | Empty |
| `LongStream.average()` | `OptionalDouble` | Empty |

Đặc biệt, **trung bình** của một dãy `int` hoặc `long` vẫn là `OptionalDouble`: kết quả trung bình có thể không phải số nguyên. Đây là một lỗi kiểu thường gặp.

Ví dụ trong phương thức:

```java
int maximum = IntStream.of(4, 8, 3)
        .max()
        .orElseThrow(); // 8

long largestId = LongStream.of(10L, 100L, 20L)
        .max()
        .orElseThrow(); // 100

double average = IntStream.of(10, 20, 30)
        .average()
        .orElseThrow(); // 20.0
```

Cần import `IntStream` và `LongStream`. Mỗi ví dụ có ít nhất một phần tử nên không ném ngoại lệ.

Ngược lại:

```java
var result = IntStream.empty().min(); // OptionalInt.empty()
int requiredMin = result.orElseThrow(); // NoSuchElementException
```

Đây là ví dụ **cố ý ném ngoại lệ** khi chạy. Không phải lỗi biên dịch; đường đi rỗng được biểu diễn chính thức bởi Optional và do người gọi quyết định chính sách.

## 5. Ví dụ hoàn chỉnh — cả ba kiểu với present/empty

Lưu tệp **`PrimitiveOptionalDemo.java`**. Chương trình này chỉ dùng tính năng phù hợp với **Java 10**, dù vẫn chạy bình thường trên JDK 17+.

```java
import java.util.NoSuchElementException;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveOptionalDemo {
    public static void main(String[] args) {
        OptionalInt count = OptionalInt.of(0);
        OptionalLong bytes = LongStream.of(12L, 45L, 30L).max();
        OptionalDouble mean = IntStream.of(10, 20, 30).average();

        System.out.println("count=" + count.orElseThrow());
        System.out.println("bytes=" + bytes.orElseThrow());
        System.out.println("mean=" + mean.orElseThrow());

        System.out.println("emptyInt=" + !OptionalInt.empty().isPresent());
        System.out.println("emptyLong=" + !OptionalLong.empty().isPresent());
        System.out.println("emptyDouble=" + !OptionalDouble.empty().isPresent());
        System.out.println("doubleZeroPresent="
                + OptionalDouble.of(0.0).isPresent());
        System.out.println("doubleNaNPresent="
                + OptionalDouble.of(Double.NaN).isPresent());

        try {
            OptionalInt.empty().orElseThrow();
        } catch (NoSuchElementException exception) {
            System.out.println("missingInt=NoSuchElementException");
        }

        try {
            OptionalLong.empty().orElseThrow();
        } catch (NoSuchElementException exception) {
            System.out.println("missingLong=NoSuchElementException");
        }

        try {
            OptionalDouble.empty().orElseThrow();
        } catch (NoSuchElementException exception) {
            System.out.println("missingDouble=NoSuchElementException");
        }
    }
}
```

Biên dịch bằng JDK có hỗ trợ target Java 10:

```bash
javac --release 10 PrimitiveOptionalDemo.java
java PrimitiveOptionalDemo
```

Hoặc trên dự án target Java 17:

```bash
javac --release 17 PrimitiveOptionalDemo.java
java PrimitiveOptionalDemo
```

**Stdout chính xác:**

```text
count=0
bytes=45
mean=20.0
emptyInt=true
emptyLong=true
emptyDouble=true
doubleZeroPresent=true
doubleNaNPresent=true
missingInt=NoSuchElementException
missingLong=NoSuchElementException
missingDouble=NoSuchElementException
```

### 5.1. Diễn giải đầu ra

- `OptionalInt.of(0)` chứa một **giá trị present là 0**; `count.orElseThrow()` trả về 0, không ném ngoại lệ.
- `LongStream.of(12L,45L,30L).max()` trả `OptionalLong` chứa 45; `orElseThrow()` trả `long`.
- `IntStream.of(10,20,30).average()` trả `OptionalDouble` chứa 20.0; `orElseThrow()` trả `double`.
- `emptyInt/Long/Double=true` vì biểu thức `!isPresent()` chỉ hỏi trạng thái, không cố trích xuất dữ liệu. Cách viết này tương thích Java 10.
- `OptionalDouble.of(0.0)` và `OptionalDouble.of(Double.NaN)` đều **present**. Dấu hiệu “rỗng” nằm trong trạng thái Optional, không được quyết định bằng giá trị số bên trong.
- Ba lời gọi trên Optional rỗng được bắt riêng nên chương trình chạy hết và cho thấy cùng loại ngoại lệ chuẩn.

**Không phụ thuộc thông điệp ngoại lệ:** mã chỉ bắt loại `NoSuchElementException` chứ không in `exception.getMessage()`. Chuỗi thông báo không phải hợp đồng cần giữ giữa mọi JDK.

### 5.2. Vì sao dùng `!isPresent()` thay vì `isEmpty()`?

`isPresent()` có từ Java 8. `isEmpty()` trên các Optional xuất hiện từ **Java 11**. Trên JDK hiện đại, `optional.isEmpty()` dễ đọc và hợp lệ; nhưng nếu muốn chính ví dụ biên dịch với `--release 10` thì `!optional.isPresent()` là lựa chọn phù hợp.

Sự tồn tại của `isEmpty()` ở Java 11 không thay đổi ngữ nghĩa `orElseThrow()` được bổ sung từ Java 10.

## 6. Chọn đúng chính sách khi Optional không có dữ liệu

Một Optional rỗng **không tự động đồng nghĩa có lỗi**. Đó là lý do có nhiều API cùng tồn tại. Chọn cách xử lý theo ý nghĩa nghiệp vụ:

| Nhu cầu | Ví dụ `OptionalInt` | Kết quả khi rỗng |
|---|---|---|
| Bắt buộc phải có giá trị | `opt.orElseThrow()` | Ném `NoSuchElementException` |
| Thiếu giá trị là lỗi domain | `opt.orElseThrow(() -> new IllegalArgumentException("missing"))` | Ném ngoại lệ tùy chỉnh |
| Có fallback cụ thể, được phép | `opt.orElse(-1)` | Trả `-1` |
| Fallback chỉ nên tính khi cần | `opt.orElseGet(() -> loadDefault())` | Gọi `IntSupplier` rồi trả kết quả |
| Chỉ thực hiện hành động nếu có | `opt.ifPresent(value -> use(value))` | Không gọi consumer |
| Cần xử lý cả hai nhánh | `opt.ifPresentOrElse(value -> use(value), () -> onMissing())` | Chạy nhánh empty |
| Muốn tiếp tục xử lý dạng primitive stream | `opt.stream()` | Trả stream rỗng |

Các ký hiệu `opt`, `loadDefault()`, `use(...)`, `onMissing()` là **mảnh mô tả cần có định nghĩa thích hợp**. `ifPresentOrElse` và `stream` trên Optional primitive có từ **Java 9**; các phương thức đó không phải phần mới của Java 10.

### 6.1. Khi nào dùng `orElseThrow()` không tham số?

Dùng khi:
- Contract hoặc bất biến của hàm yêu cầu phải có kết quả;
- Không có dữ liệu là trường hợp bất thường;
- Caller có thể xử lý ngoại lệ hoặc để nó được báo rõ;
- `NoSuchElementException` là tín hiệu đủ rõ về việc thiếu phần tử.

Ví dụ, khi một thuật toán đã xác minh collection không rỗng thì lấy giá trị cực đại bắt buộc là hợp lý:

```java
static int requiredMaximum(int[] numbers) {
    if (numbers.length == 0) {
        throw new IllegalArgumentException("numbers must not be empty");
    }
    return java.util.Arrays.stream(numbers).max().orElseThrow();
}
```

Đây là **method minh họa trong một class**. Kiểm tra đầu vào làm rõ lỗi của caller; `orElseThrow()` thể hiện bất biến là sau bước xác minh phải có max.

### 6.2. Khi nào nên dùng fallback?

Nếu “không có dữ liệu” là kết quả bình thường, việc ném ngoại lệ có thể gây phức tạp không cần thiết. Ví dụ đếm số lượng khớp bộ lọc mà không có dữ liệu có thể có giá trị mặc định 0 **nếu nghiệp vụ quy định như vậy**.

```java
int min = IntStream.empty().min().orElse(-1);
```

Đây là một mảnh Java hợp lệ. Tuy nhiên `-1` có thể là **giá trị dữ liệu hợp lệ** nếu tập có số âm; khi đó fallback dạng sentinel có thể làm mất thông tin về việc không tìm thấy. Giữ nguyên `OptionalInt` hoặc chọn loại kết quả domain rõ nghĩa nếu cần phân biệt.

Một ví dụ nhạy cảm hơn: điểm trung bình từ một tập dữ liệu rỗng **không nhất thiết bằng 0**. Dùng `average().orElse(0.0)` chỉ khi nghiệp vụ **chủ động** định nghĩa giá trị thay thế đó, không phải để tránh exception một cách máy móc.

### 6.3. Khi nào dùng supplier ngoại lệ?

Nếu muốn thông báo có ngữ cảnh hay loại lỗi cụ thể:

```java
int result = optionalCount.orElseThrow(
        () -> new IllegalStateException("Expected at least one count"));
```

Đây là mảnh code, giả định `optionalCount` kiểu `OptionalInt`. Overload nhận `Supplier<? extends X>` đã có từ **Java 8** và vẫn được hỗ trợ. Supplier chỉ được sử dụng để tạo ngoại lệ khi Optional rỗng; không cần tạo ngoại lệ mới ở nhánh present.

Đừng nhầm `orElseThrow()` **không tham số** với `orElseThrow(Supplier)`. Cả hai cùng mô tả tình huống thiếu dữ liệu là lỗi nhưng **khác loại ngoại lệ** mà người gọi lựa chọn.

## 7. So sánh với getAsInt/getAsLong/getAsDouble

Các cặp phương thức có **hành vi tương đương đối với present/empty**:

| Kiểu | Phương thức có từ Java 8 | Phương thức ưu tiên đọc rõ ý định từ Java 10 |
|---|---|---|
| `OptionalInt` | `getAsInt()` | `orElseThrow()` |
| `OptionalLong` | `getAsLong()` | `orElseThrow()` |
| `OptionalDouble` | `getAsDouble()` | `orElseThrow()` |

Ví dụ:

```java
var count = OptionalInt.of(8);
int a = count.getAsInt();
int b = count.orElseThrow(); // a == b == 8
```

Đây là mảnh code trong method, cần import `OptionalInt`.

Điểm khác không phải hiệu năng hay loại ngoại lệ:
- `getAsInt()` nói “lấy giá trị int”.
- `orElseThrow()` thể hiện trực tiếp ý nghĩa “trả về giá trị nếu có, **nếu không thì ném lỗi**”.

Cả hai đều ném `NoSuchElementException` khi rỗng. `getAsX` vẫn là phương thức hợp lệ trong JDK hiện đại; không cần áp dụng một cuộc chuyển đổi máy móc nếu đoạn code đã rõ. Tuy nhiên, khi viết mã mới có ý định “missing is an error”, `orElseThrow()` thường dễ diễn đạt hợp đồng hơn.

**Không nên viết kiểu:**

```java
if (optional.isPresent()) {
    return optional.getAsInt();
}
throw new NoSuchElementException();
```

Đây là **mảnh giả định `optional` là `OptionalInt` trong phương thức trả `int`**, và có thể được thay gọn bằng `return optional.orElseThrow();` nếu đúng yêu cầu. Việc kiểm tra `isPresent()` rồi gọi `getAsInt()` không có lợi khi nhánh empty vốn phải ném cùng ngoại lệ.

Ngược lại, nếu hai nhánh cần làm điều khác nhau, `ifPresentOrElse` hay kiểm tra trạng thái rõ ràng vẫn có chỗ dùng.

## 8. Ví dụ đầy đủ Java 10: fallback, supplier và ngoại lệ theo domain

Lưu tệp **`PrimitivePoliciesDemo.java`**:

```java
import java.util.Arrays;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class PrimitivePoliciesDemo {
    static int requireMax(int[] numbers) {
        return Arrays.stream(numbers)
                .max()
                .orElseThrow(() -> new IllegalArgumentException("no-numbers"));
    }

    public static void main(String[] args) {
        int[] calls = {0};
        int defaultInt = IntStream.empty().min().orElse(-1);

        double present = OptionalDouble.of(2.5).orElseGet(() -> {
            calls[0]++;
            return -1.0;
        });
        double missing = OptionalDouble.empty().orElseGet(() -> {
            calls[0]++;
            return -1.0;
        });

        System.out.println("max=" + requireMax(new int[]{2, 5, 3}));
        System.out.println("defaultInt=" + defaultInt);
        System.out.println("present=" + present);
        System.out.println("missing=" + missing);
        System.out.println("fallbackCalls=" + calls[0]);
        System.out.println("flattenedSum="
                + Stream.of(OptionalInt.of(7), OptionalInt.empty(),
                             OptionalInt.of(9))
                        .flatMapToInt(OptionalInt::stream)
                        .sum());

        try {
            requireMax(new int[]{});
        } catch (IllegalArgumentException exception) {
            System.out.println("customException=" + exception.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac --release 10 PrimitivePoliciesDemo.java
java PrimitivePoliciesDemo
```

**Stdout:**

```text
max=5
defaultInt=-1
present=2.5
missing=-1.0
fallbackCalls=1
flattenedSum=16
customException=no-numbers
```

### 8.1. Điểm cần đọc ở ví dụ

1. `requireMax(...)` chọn chính sách **ném `IllegalArgumentException` có thông báo rõ** khi mảng rỗng. Đây là overload `orElseThrow(Supplier)`. Nếu thay bằng `orElseThrow()` không tham số, trường hợp rỗng sẽ ném `NoSuchElementException`.
2. `IntStream.empty().min().orElse(-1)` dùng fallback cụ thể do ví dụ quy định. Nó **không** làm cho Optional empty biến thành present, chỉ trích xuất một giá trị thay thế.
3. `OptionalDouble.of(2.5).orElseGet(...)` không gọi supplier; với `OptionalDouble.empty().orElseGet(...)` supplier được gọi **một lần**. Biến đếm vì vậy là 1.
4. `Stream.of(...).flatMapToInt(OptionalInt::stream)` ghép các OptionalInt thành một `IntStream` chỉ chứa `7` và `9`, rồi `sum()` cho 16. `OptionalInt.stream()` xuất hiện từ Java 9, vẫn dùng được ở Java 10.
5. `customException=no-numbers` cho thấy khi thiếu dữ liệu, ứng dụng có thể chọn một **exception phù hợp hợp đồng phương thức** thay vì ngoại lệ mặc định.

Đây là ví dụ minh họa khác nhau về chính sách. Trong một service thực tế, hãy thống nhất cách báo lỗi với các phương thức lân cận, không tùy tiện thay giữa `NoSuchElementException`, `IllegalArgumentException` hoặc fallback.

## 9. Những điều cần đặc biệt lưu ý với ba kiểu primitive

### 9.1. `0` không phải empty

`OptionalInt.of(0).orElseThrow()` trả 0.
`OptionalLong.of(0L).orElseThrow()` trả 0L.
`OptionalDouble.of(0.0).orElseThrow()` trả 0.0.

Ngược lại, `OptionalInt.empty().orElseThrow()` ném `NoSuchElementException`, dù lập trình viên “muốn” coi thiếu là 0.

**Sai về mặt nghiệp vụ** nếu dùng số 0 làm chỉ báo không có dữ liệu trong một domain mà 0 cũng là giá trị hợp lệ. Đây chính là lý do dùng Optional để phân biệt hai trạng thái.

### 9.2. `Double.NaN` không phải empty

`OptionalDouble.of(Double.NaN)` là **present**. Gọi `orElseThrow()` trả `Double.NaN` và **không ném**. Nếu domain không chấp nhận NaN, hãy kiểm tra riêng, ví dụ:

```java
double value = optionalDouble.orElseThrow();
if (Double.isNaN(value)) {
    throw new IllegalArgumentException("NaN is not allowed");
}
```

Mảnh code cần `optionalDouble` kiểu `OptionalDouble`. `orElseThrow()` kiểm tra **sự có mặt**, không kiểm tra số đó có hữu hạn, có nằm trong miền cho phép hay có ý nghĩa thống kê.

Tương tự, `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` cũng là những giá trị `double` có thể present. Tính hợp lệ của dữ liệu phải được xác định riêng.

### 9.3. `OptionalInt` và `OptionalLong` không tự ép kiểu cho nhau

`OptionalInt` không phải subtype của `OptionalLong`. Những method trích xuất trả primitive tương ứng; nếu code cần `long` có thể widening từ `int` sau khi lấy giá trị:

```java
OptionalInt amount = OptionalInt.of(10);
long widened = amount.orElseThrow(); // Widening int -> long
```

Nhưng không thể gán một `OptionalInt` trực tiếp vào biến `OptionalLong`. Nếu API đích cần biểu diễn optional long, cần tạo OptionalLong theo một quy tắc chuyển đổi phù hợp với trạng thái present/empty, chứ không chỉ cast.

### 9.4. Optional primitive không dùng null để biểu thị thiếu

Không được viết:

```java
OptionalInt count = null; // Biên dịch được nhưng sai hợp đồng sử dụng
count.orElseThrow();      // NullPointerException, không phải NoSuchElementException
```

Đây là **mảnh cảnh báo**, cố tình cho thấy việc gọi method trên biến null. `OptionalInt.empty()` mới là giá trị biểu diễn vắng mặt. Javadoc khuyến nghị Optional primitive chủ yếu dùng như **kiểu trả về khi phép tính có thể không có kết quả**, và biến kiểu Optional không nên tự là null.

Đừng nhầm hai lỗi:
- **Optional rỗng:** `NoSuchElementException` từ `orElseThrow()`.
- **Tham chiếu Optional là null:** `NullPointerException` khi cố gọi phương thức.

### 9.5. Không dựa vào identity của các Optional

Ba lớp Optional primitive là **value-based classes**. Tránh dùng `==` để khẳng định hai Optional empty là cùng một object, tránh khóa đồng bộ trên instance Optional. So sánh trạng thái hoặc giá trị theo phương thức có hợp đồng như `isPresent` và `equals` khi cần. Không có bảo đảm rằng `OptionalInt.empty()` trả cùng một object singleton trong mọi lần gọi.

### 9.6. Primitive Optional và generic Optional

`Optional<Integer>` có thể biểu diễn một `Integer` hoặc vắng mặt, trong khi `OptionalInt` chứa trực tiếp một `int` khi present. Tương tự `Optional<Long>`/`OptionalLong` và `Optional<Double>`/`OptionalDouble`.

Chọn kiểu theo API thực tế và mục tiêu dữ liệu. Primitive Optional có lợi thế tránh một số boxing/unboxing trong các phép tính, nhưng **không nên tuyên bố nó luôn nhanh hơn** ở mọi hoàn cảnh. Ba kiểu Optional primitive có tập phương thức chuyên biệt; không mặc nhiên hỗ trợ toàn bộ phép biến đổi generic của `Optional<T>`. Khi cần API generic hoặc kết hợp phức tạp, hãy chọn kiểu biểu diễn hợp đồng rõ nhất.

## 10. Lỗi thường gặp và cách sửa

| Lỗi hoặc hiểu nhầm | Điều đúng / cách sửa |
|---|---|
| “`OptionalInt.empty().orElseThrow()` trả 0.” | Không. Nó ném `NoSuchElementException`; dùng `orElse(0)` chỉ khi 0 là fallback hợp lệ. |
| “`OptionalDouble.of(0.0)` là empty.” | Sai. Đây là Optional có giá trị present là 0.0. |
| “`Double.NaN` đồng nghĩa không tìm thấy.” | Không. `OptionalDouble.of(Double.NaN)` vẫn present; NaN cần xác thực riêng. |
| “`orElseThrow()` luôn ném exception.” | Chỉ ném khi **empty**. Khi present, nó trả primitive đang có. |
| “`OptionalInt.orElseThrow()` trả `Integer`.” | Không. Kiểu trả về là `int`. |
| “`LongStream.average()` trả `OptionalLong`.” | Không. Nó trả `OptionalDouble`. |
| “`getAsInt()` đã bị xóa khỏi Java hiện đại.” | Không. `getAsInt()` vẫn hợp lệ; `orElseThrow()` được API Note khuyên dùng để biểu đạt ý định. |
| “No-arg `orElseThrow()` có từ Java 8.” | Không. Overload **không tham số** là Java 10; overload nhận exception supplier có từ trước. |
| “`isEmpty()` trên OptionalInt có sẵn trong Java 10.” | Không. `isEmpty()` có từ Java 11; Java 10 dùng `!isPresent()` để hỏi empty. |
| “Có thể dùng `OptionalInt` trực tiếp thay `OptionalLong`.” | Không. Đây là hai kiểu container khác nhau; phải chuyển đổi có kiểm soát. |
| “`OptionalInt.empty() == OptionalInt.empty()` luôn đúng.” | Không được dựa vào identity của value-based class. |
| “Nếu Optional biến là `null`, `orElseThrow()` ném `NoSuchElementException`.” | Không. Gọi method trên null gây `NullPointerException`. |
| “Có dữ liệu thì gọi `orElseThrow(() -> ...)` vẫn tạo exception.” | Exception supplier chỉ được gọi ở nhánh empty. |
| “`orElse(-1)` là cách giải quyết mọi Optional rỗng.” | Fallback phải được nghiệp vụ cho phép; sentinel có thể trùng giá trị thật. |

## 11. Kiểm thử đúng: phải có cả nhánh present và empty

Một test chỉ gọi `OptionalInt.of(5).orElseThrow()` chưa kiểm tra được quy tắc quan trọng nhất của phương thức. Nên có:

1. **Present**: assert đúng primitive được trả, kể cả 0.
2. **Empty**: assert ném đúng `NoSuchElementException`.
3. **Custom exception supplier**: assert supplier chỉ được sử dụng khi empty.
4. **Tình huống upstream**: stream có dữ liệu và stream rỗng.
5. **Double đặc biệt**: xác nhận OptionalDouble.of(0.0) và OptionalDouble.of(Double.NaN) là present nếu domain cần.

### 11.1. Test bằng Java thuần

Tệp độc lập **`PrimitiveOptionalContractTest.java`**:

```java
import java.util.NoSuchElementException;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;

public class PrimitiveOptionalContractTest {
    static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Optional contract failed");
        }
    }

    static void expectMissing(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException expected) {
            // The empty branch is verified.
        }
    }

    public static void main(String[] args) {
        require(OptionalInt.of(0).orElseThrow() == 0);
        require(OptionalLong.of(0L).orElseThrow() == 0L);
        require(OptionalDouble.of(0.0).orElseThrow() == 0.0);

        expectMissing(() -> OptionalInt.empty().orElseThrow());
        expectMissing(() -> OptionalLong.empty().orElseThrow());
        expectMissing(() -> OptionalDouble.empty().orElseThrow());

        require(Double.isNaN(OptionalDouble.of(Double.NaN).orElseThrow()));
        System.out.println("contract=PASS");
    }
}
```

Lệnh:

```bash
javac --release 10 PrimitiveOptionalContractTest.java
java PrimitiveOptionalContractTest
```

Khi tất cả assertion đúng, stdout:

```text
contract=PASS
```

Phần `expectMissing` dùng `Runnable` chứa lời gọi `orElseThrow()` và bắt riêng `NoSuchElementException`. Nếu không có exception, chương trình sẽ phát sinh `AssertionError`. Đây là cách kiểm tra hành vi mà không phụ thuộc chuỗi thông báo ngoại lệ.

Với JUnit 5 đã cài trong dự án, có thể dùng `assertThrows(NoSuchElementException.class, () -> optional.orElseThrow())`. Mã Java thuần ở trên không cần dependency nào ngoài JDK.

### 11.2. Kiểm tra giá trị trả về chính xác

Đừng chỉ assert `optional.isPresent()`. Nếu phép toán thật có yêu cầu về cực đại/trung bình, hãy so sánh số nhận được với kỳ vọng. Với `double` tính từ dữ liệu thập phân, cần xem xét độ chính xác dấu phẩy động và dung sai phù hợp, thay vì tùy tiện kiểm tra bằng `==` trên các phép tính có sai số làm tròn. `orElseThrow()` không làm thay đổi cách hoạt động của số dấu phẩy động.

### 11.3. Không test thông điệp ngoại lệ mặc định

Loại ngoại lệ `NoSuchElementException` là một phần của hợp đồng. Chi tiết `message` mặc định không nên là điều kiện của test vì có thể khác giữa implementation. Nếu ứng dụng cần thông báo ổn định cho API công khai, chọn overload có `exceptionSupplier` tạo ngoại lệ phù hợp và kiểm thử thông điệp do **bạn tự định nghĩa**.

## 12. Thiết kế API và xử lý lỗi hợp lý

### 12.1. Giữ Optional ở tầng mà thiếu dữ liệu là kết quả bình thường

Một phương thức có thể trả:

```java
static OptionalLong findLargestId(long[] ids) {
    return java.util.Arrays.stream(ids).max();
}
```

Đây là method minh họa, cần import `java.util.OptionalLong`. Caller có thể:
- Chọn `orElseThrow()` nếu bắt buộc có ID;
- Chọn `orElse(defaultId)` nếu một ID mặc định thực sự có nghĩa;
- Chọn `ifPresent(...)` để chỉ thực hiện hành động khi có dữ liệu.

Thiết kế này giữ **quyết định thiếu dữ liệu** cho nơi có đủ ngữ cảnh. Nếu bản thân method có hợp đồng bắt buộc phải tìm được ID, việc trả `long` và dùng `orElseThrow()` trong method cũng hợp lý.

### 12.2. Đừng bắt rồi nuốt NoSuchElementException một cách vô điều kiện

Ví dụ chống mẫu:

```java
try {
    return result.orElseThrow();
} catch (NoSuchElementException ignored) {
    return 0;
}
```

Đây là mảnh mã giả định method trả một `int` và `result` là `OptionalInt`. Nếu 0 là fallback đúng, viết trực tiếp `return result.orElse(0);` dễ đọc hơn. Nếu thiếu kết quả là lỗi, việc bắt rồi đổi thành 0 có thể làm mất dữ liệu và che nguyên nhân.

### 12.3. Tránh tự gán `null` vào một Optional primitive

Dạng:

```java
OptionalDouble average = null;
```

có thể biên dịch nhưng phá vỡ ý nghĩa của Optional. Dùng `OptionalDouble.empty()` để biểu thị vắng mặt. Nếu nguồn là `Double` nullable, chuyển đổi cần kiểm tra null rõ ràng:

```java
Double raw = readAverage();
OptionalDouble average =
        raw == null ? OptionalDouble.empty() : OptionalDouble.of(raw);
```

Đây là mảnh minh họa, giả định `readAverage()` trả `Double`. Việc unbox diễn ra chỉ sau kiểm tra null.

### 12.4. Kết hợp `stream()` và Optional primitive

Nếu có một danh sách các OptionalInt và cần chỉ lấy những giá trị present, thay vì gọi `orElseThrow()` lên từng phần tử rồi xử lý exception, có thể dùng:

```java
int sum = java.util.stream.Stream.of(
        OptionalInt.of(7),
        OptionalInt.empty(),
        OptionalInt.of(9)
).flatMapToInt(OptionalInt::stream).sum(); // 16
```

`OptionalInt.stream()` trả một `IntStream` có 1 phần tử nếu present, 0 phần tử nếu empty. Đây là **chính sách bỏ qua Optional rỗng**, chỉ đúng khi nghiệp vụ muốn bỏ dữ liệu thiếu. Nếu mỗi item bắt buộc present, cách bỏ qua này có thể che lỗi; khi đó `orElseThrow()` cho từng item mới diễn đạt đúng yêu cầu.

## 13. Quy tắc code review nhanh

- [ ] Optional có thể empty theo dữ liệu thực tế không?
- [ ] Nếu empty, nghiệp vụ muốn lỗi, fallback hay xử lý nhánh riêng?
- [ ] Nếu lỗi, `NoSuchElementException` có truyền tải đủ ý nghĩa không, hay cần ngoại lệ domain có ngữ cảnh?
- [ ] Kiểu trả về có đúng không: `int`, `long` hay `double`?
- [ ] Có nhầm trung bình `IntStream/LongStream` với `OptionalInt/OptionalLong` không?
- [ ] Giá trị 0 hoặc `Double.NaN` có bị coi nhầm là empty không?
- [ ] Code có đang dựa vào `isEmpty()` khi target dự án chỉ là Java 10 không?
- [ ] Có dùng `OptionalInt.empty()` thay cho `null` đúng quy ước không?
- [ ] Có sử dụng `orElse(-1)` với sentinel có thể là dữ liệu hợp lệ không?
- [ ] Có test present, empty, exception type, fallback và nhánh stream rỗng không?
- [ ] Có dùng identity-sensitive operations với các lớp Optional value-based không?
- [ ] Nếu vừa xử lý dòng dữ liệu rỗng vừa cần giá trị bắt buộc, đã phân biệt lỗi đầu vào với lỗi không có kết quả chưa?

## 14. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `OptionalInt.empty().orElseThrow()` trả về gì?

**Đáp án:** Ném `NoSuchElementException`. Không trả 0.

**Câu 2.** `OptionalLong.of(0L).orElseThrow()` có ném ngoại lệ không?

**Đáp án:** Không. Nó trả primitive `long` bằng 0.

**Câu 3.** `IntStream.empty().average().orElseThrow()` có kiểu Optional nào trước khi trích xuất?

**Đáp án:** `OptionalDouble`. Khi rỗng, `orElseThrow()` ném `NoSuchElementException`.

**Câu 4.** `LongStream.of(1L, 4L).max().orElseThrow()` trả về kiểu gì và giá trị bao nhiêu?

**Đáp án:** Primitive `long` với giá trị 4L.

**Câu 5.** Nếu có Optional rỗng nhưng nghiệp vụ cho phép dùng -1, chọn gì?

**Đáp án:** `orElse(-1)`, miễn là -1 thực sự là fallback hợp lệ và không nhầm với giá trị thật.

**Câu 6.** Cần `IllegalArgumentException` có thông báo “no data” thay vì ngoại lệ mặc định?

**Đáp án:** Dùng `orElseThrow(() -> new IllegalArgumentException("no data"))`.

**Câu 7.** `orElseThrow()` không tham số trên `OptionalDouble` xuất hiện từ Java 8 hay 10?

**Đáp án:** Java 10; lớp `OptionalDouble` đã có từ Java 8.

**Câu 8.** `getAsDouble()` còn hợp lệ không?

**Đáp án:** Có. Nó vẫn thực hiện cùng hành vi trích xuất hoặc ném khi empty; API Note gợi ý `orElseThrow()` vì rõ ý định hơn.

**Câu 9.** `OptionalDouble.of(Double.NaN).orElseThrow()` có ném `NoSuchElementException`?

**Đáp án:** Không. Optional present; nó trả NaN. Cần kiểm tra `Double.isNaN(...)` riêng nếu NaN không hợp lệ.

**Câu 10.** Có thể viết `OptionalInt value = null; value.orElseThrow();` và chờ `NoSuchElementException` không?

**Đáp án:** Không. Đây là tham chiếu null, nên gọi method ném `NullPointerException`; biểu diễn vắng mặt bằng `OptionalInt.empty()`.

**Câu 11.** Trên Java 10, `optional.isEmpty()` có sẵn chưa?

**Đáp án:** Chưa. `isEmpty()` xuất hiện từ Java 11. Dùng `!optional.isPresent()` khi cần tương thích Java 10.

**Câu 12.** Vì sao `OptionalInt.stream()` có thể thích hợp hơn `orElseThrow()` khi gộp nhiều Optional?

**Đáp án:** Nếu thiếu dữ liệu là bình thường và cần **bỏ qua** giá trị vắng mặt, `stream()` biến empty thành stream 0 phần tử. Nếu mọi giá trị bắt buộc có, `orElseThrow()` mới phù hợp.

## 15. Tài liệu chính thức

- [Oracle JDK 10 — OptionalInt](https://docs.oracle.com/javase/10/docs/api/java/util/OptionalInt.html): `orElseThrow()` trả `int` và ghi `Since: 10`.
- [Oracle JDK 10 — OptionalLong](https://docs.oracle.com/javase/10/docs/api/java/util/OptionalLong.html): `orElseThrow()` trả `long` và ghi `Since: 10`.
- [Oracle JDK 10 — OptionalDouble](https://docs.oracle.com/javase/10/docs/api/java/util/OptionalDouble.html): `orElseThrow()` trả `double` và ghi `Since: 10`.
- [Oracle Java SE 21 — OptionalInt](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/OptionalInt.html): hợp đồng tiếp tục áp dụng và API Note về `getAsInt()`.
- [Oracle Java SE 21 — OptionalLong](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/OptionalLong.html): chi tiết tương ứng cho primitive `long`.
- [Oracle Java SE 21 — OptionalDouble](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/OptionalDouble.html): chi tiết về empty/present, `orElseThrow()`, NaN và các thao tác liên quan.
- [Oracle Java SE 21 — IntStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/IntStream.html): `max()`/`min()` trả `OptionalInt` và `average()` trả `OptionalDouble`.
- [Oracle Java SE 21 — LongStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/LongStream.html): `max()`/`min()` trả `OptionalLong` và `average()` trả `OptionalDouble`.
- [Oracle Java SE 21 — DoubleStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/DoubleStream.html): `average()`, `max()` và `min()` trả `OptionalDouble`.

**Ghi nhớ:** `OptionalInt.orElseThrow()`, `OptionalLong.orElseThrow()` và `OptionalDouble.orElseThrow()` đều là **bổ sung ở Java 10**. Khi present, chúng trả đúng primitive `int`/`long`/`double`; khi empty, chúng ném `NoSuchElementException`. Đừng nhầm “rỗng” với số 0 hoặc NaN; hãy chọn `orElse`, `orElseGet`, exception supplier hoặc `stream()` nếu nghiệp vụ cần một chính sách thiếu dữ liệu khác.