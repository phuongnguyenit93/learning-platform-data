# Xây dựng phép tính kích thước có kiểm tra tràn trong Java

## 1. Mục tiêu thực hành

Khi tính kích thước bộ nhớ, tập tin, ảnh, buffer hoặc số trang lưu trữ, biểu thức đơn giản như `width * height * bytesPerPixel` có thể **tràn số nguyên** (*integer overflow*) dù các đối số đầu vào đều hợp lệ riêng lẻ.

Ví dụ:

```java
int width = 70_000;
int height = 70_000;

int wrong = width * height; // 605032704, không phải 4900000000
```

Kết quả đúng là **4.900.000.000**, vượt `Integer.MAX_VALUE = 2.147.483.647`. Java không tự ném ngoại lệ cho phép nhân `int` thông thường: phần bit vượt phạm vi bị loại theo quy tắc số nguyên Java, dẫn đến kết quả sai nhưng chương trình vẫn có thể tiếp tục.

Trong các tác vụ tính kích thước, lỗi này đặc biệt nguy hiểm: phân bổ buffer thiếu byte, tính sai offset, số bản ghi hoặc giới hạn dữ liệu. Mục tiêu của bài này là xây một phép tính **rõ đơn vị, kiểm tra điều kiện, phát hiện tràn ngay tại phép toán, làm tròn an toàn và không cấp phát vượt khả năng thực tế**.

Sau bài học, bạn sẽ:
- Dùng `Math.multiplyExact`, `Math.addExact`, `Math.subtractExact` và `Math.toIntExact` đúng chỗ.
- Phân biệt mở rộng kiểu **trước** phép nhân với gán kết quả đã tràn vào `long`.
- Tính số byte một hàng, stride có alignment, tổng dung lượng, số trang cần cấp phát.
- Phân biệt **tràn số học**, **dữ liệu đầu vào không hợp lệ** và **thiếu tài nguyên vật lý**.
- Kiểm thử ca bình thường, biên `int`/`long`, số 0, số âm và bài toán vượt `long` với `BigInteger`.

## 2. Phát biểu bài toán: tính kích thước theo đơn vị

Giả sử ảnh có:
- `rows`: số hàng.
- `columns`: số điểm ảnh trên mỗi hàng.
- `bytesPerPixel`: số byte mỗi điểm ảnh.
- `alignment`: mức căn chỉnh số byte của mỗi hàng.

Không có căn chỉnh, tổng byte là:

```text
rawRowBytes = columns × bytesPerPixel
totalBytes  = rows × rawRowBytes
```

Nếu stride hàng cần là bội số của `alignment`:

```text
remainder  = rawRowBytes % alignment
padding    = (remainder == 0) ? 0 : alignment - remainder
stride     = rawRowBytes + padding
totalBytes = rows × stride
```

Phải kiểm tra `alignment > 0`, `rows >= 0`, `columns >= 0` và `bytesPerPixel >= 0` hoặc `> 0` theo quy tắc nghiệp vụ. Có thể yêu cầu kích thước ảnh dương, nhưng ví dụ chung trong bài **cho phép vùng 0 byte** để mô tả buffer rỗng.

Ví dụ: ảnh 2 hàng, 3 cột, 3 byte/pixel, alignment 4:
- Raw: `3 × 3 = 9` byte/hàng.
- Phần dư 9 % 4 = 1; cần thêm 3 byte padding.
- Stride: 12 byte/hàng.
- Tổng: `2 × 12 = 24` byte.

Điều cốt yếu: **mọi phép nhân/cộng có thể vượt giới hạn phải được kiểm tra ngay lúc thực hiện**, kể cả phép cộng padding sau khi phép nhân đầu tiên vẫn hợp lệ.

## 3. Tràn số nguyên hoạt động thế nào?

`int` có dấu 32 bit, từ `-2^31` đến `2^31 - 1`. `long` có dấu 64 bit, từ `-2^63` đến `2^63 - 1`.

Trong Java, cộng/trừ/nhân số nguyên thông thường thực hiện theo độ rộng của kiểu tính toán. Khi vượt phạm vi, kết quả quấn vòng theo 2^32 hoặc 2^64 (không tự ném ngoại lệ).

```java
int a = 70_000;
int b = 70_000;

int incorrect = a * b;       // 605032704
long stillWrong = a * b;     // 605032704L: đã tràn trước khi gán!
long correct = (long) a * b; // 4900000000L: mở rộng trước khi nhân
```

Đặt toán hạng `long` trước khi nhân quan trọng hơn kiểu biến kết quả. Ngoài ra:

```java
long checked = Math.multiplyExact((long) a, b); // 4900000000L
// Math.multiplyExact(a, b) chọn overload int và ném ArithmeticException.
```

Đây là khác biệt giữa **mở rộng phạm vi** và **kiểm tra tràn**:
- Chuyển một toán hạng từ `int` sang `long` có thể tránh tràn `int`, nhưng phép nhân `long` vẫn có thể tràn.
- `Math.multiplyExact(long, long)` phát hiện tràn `long` bằng cách ném `ArithmeticException`.
- `Math.multiplyExact(int, int)` ném nếu không thể chứa kết quả trong `int`.

Dùng overload có chủ đích theo **kiểu trả về và phạm vi kết quả mong muốn**.

## 4. Các API kiểm tra tràn trong Java 17

| API | Công dụng | Khi vượt miền |
| --- | --- | --- |
| `Math.addExact(int,int)` / `Math.addExact(long,long)` | Cộng có kiểm tra | `ArithmeticException` |
| `Math.subtractExact(...)` | Trừ có kiểm tra | `ArithmeticException` |
| `Math.multiplyExact(...)` | Nhân có kiểm tra | `ArithmeticException` |
| `Math.incrementExact(...)` / `Math.decrementExact(...)` | Tăng/giảm 1 | `ArithmeticException` |
| `Math.negateExact(...)` | Đổi dấu | `ArithmeticException` khi đổi dấu giá trị MIN |
| `Math.toIntExact(long)` | Thu hẹp từ `long` sang `int` có kiểm tra | `ArithmeticException` |

Một số ví dụ:

```java
long bytes = Math.multiplyExact(4_000L, 3_000L);
bytes = Math.multiplyExact(bytes, 4L);   // 48000000
long withHeader = Math.addExact(bytes, 128L);
long remaining = Math.subtractExact(withHeader, 128L);

int acceptableLength = Math.toIntExact(4_096L); // 4096
// Math.toIntExact(2_147_483_648L) ném ArithmeticException.
```

**Không nhầm `Math.toIntExact` với `(int) x`**: ép kiểu `(int)` chỉ giữ các bit thấp, có thể trả một số hoàn toàn khác. Cần kiểm tra **tính hợp lệ nghiệp vụ** riêng: `Math.toIntExact(-1L)` vẫn trả `-1` vì số -1 nằm trong miền `int`, trong khi độ dài mảng âm là không hợp lệ.

Nếu phép tính cần nhiều bước, mỗi bước có nguy cơ tràn đều cần được bảo vệ. Chỉ kiểm tra kết quả cuối `if (result < 0)` là **không đủ**: kết quả tràn có thể vẫn dương, như `70_000 × 70_000` đã cho.

## 5. Thiết kế API: giá trị hợp lệ và ngoại lệ

Một API tính kích thước nên tách hai loại lỗi:

1. **Đối số vi phạm quy tắc**: âm, divisor/alignment bằng 0; thường ném `IllegalArgumentException` với thông báo nêu tên tham số.
2. **Phép toán đúng về ý nghĩa nhưng vượt phạm vi kiểu**: ném `ArithmeticException` qua `Math.*Exact`.

Ví dụ phương thức tính byte dữ liệu:

```java
static long elementBytes(long count, long bytesPerElement) {
    if (count < 0 || bytesPerElement < 0) {
        throw new IllegalArgumentException("dimensions must be >= 0");
    }
    return Math.multiplyExact(count, bytesPerElement);
}
```

Đây là **đoạn phương thức minh họa**, phải đặt trong một lớp. Với `elementBytes(70_000,70_000)`, kết quả là `4_900_000_000L`. Với `elementBytes(Long.MAX_VALUE,2)`, phép nhân vượt `long` và ném `ArithmeticException`.

Lựa chọn cho phép `count = 0` và `bytesPerElement = 0` thuộc hợp đồng bài toán. Nếu “mỗi phần tử phải chiếm byte dương”, kiểm tra `bytesPerElement > 0` thay vì để 0 hợp lệ. Điều quan trọng là không âm thầm sửa giá trị đầu vào về 0 hoặc giới hạn tối đa mà người gọi không biết.

## 6. Căn chỉnh kích thước mà không làm tràn phép cộng trung gian

Một công thức dễ gặp:

```java
// Phản ví dụ: raw + alignment - 1 có thể tràn.
long stride = ((raw + alignment - 1) / alignment) * alignment;
```

Ngay cả khi số hàng có thể chứa trong `long`, biểu thức `raw + alignment - 1` có thể tràn; phép nhân với `alignment` ở bước cuối cũng có thể tràn.

Cách an toàn cho `raw >= 0` và `alignment > 0` là tính phần dư:

```java
static long alignUp(long raw, long alignment) {
    if (raw < 0 || alignment <= 0) {
        throw new IllegalArgumentException("invalid size or alignment");
    }
    long remainder = raw % alignment;
    long padding = remainder == 0 ? 0 : alignment - remainder;
    return Math.addExact(raw, padding);
}
```

Khi `remainder != 0`, `padding` thuộc `1..alignment-1`. Phép `Math.addExact` cuối phát hiện việc **không còn đủ phạm vi `long` cho kích thước đã căn chỉnh**. Không cần giả định `alignment` luôn là lũy thừa hai; thuật toán trên dùng được cho mọi alignment dương.

Ví dụ:
- `alignUp(9,4) = 12`.
- `alignUp(12,4) = 12`.
- `alignUp(0,4) = 0`.
- `alignUp(Long.MAX_VALUE-2,8)` ném `ArithmeticException` vì kích thước căn chỉnh tiếp theo vượt `Long.MAX_VALUE`.

Chỉ dùng kỹ thuật bitwise `(value + alignment - 1) & -alignment` nếu bạn đã quy định alignment là lũy thừa hai, kiểm tra miền và xử lý tràn. Nó không phải giải pháp tổng quát tự động an toàn.

## 7. Làm tròn số trang bằng chia và phần dư

Nếu `bytes` byte cần chia thành trang `pageSize` byte, số trang là **ceil(bytes/pageSize)**. Với hai số không âm và `pageSize > 0`, có thể tính:

```java
static long pageCount(long bytes, long pageSize) {
    if (bytes < 0 || pageSize <= 0) {
        throw new IllegalArgumentException("invalid page arguments");
    }
    long whole = bytes / pageSize;
    return bytes % pageSize == 0 ? whole : Math.addExact(whole, 1);
}
```

Tránh công thức `(bytes + pageSize - 1) / pageSize` nếu phép cộng có thể tràn. Với `bytes = Long.MAX_VALUE` và `pageSize = Long.MAX_VALUE`, công thức chia-dư trả 1, trong khi công thức cộng trước có thể tràn.

Ví dụ:
- 0 byte / trang 4096 byte → 0 trang.
- 4096 byte / trang 4096 byte → 1 trang.
- 4097 byte / trang 4096 byte → 2 trang.
- 48.000.000 byte / trang 4096 byte → 11.719 trang.

Với tiền, kích thước trang, phân lô hoặc các thuật toán khác, **làm tròn lên** và **căn chỉnh bội số** là các yêu cầu có quan hệ nhưng khác nhau: số trang là **số lượng**, còn stride đã căn chỉnh là **số byte**.

## 8. Chương trình Java 17 độc lập: bộ tính kích thước có kiểm tra

Tạo tệp **`CheckedSizeDemo.java`**:

```java
import java.math.BigInteger;

public class CheckedSizeDemo {
    static long nonNegative(long value, String name) {
        if (value < 0) throw new IllegalArgumentException(name + " must be >= 0");
        return value;
    }

    static long elementBytes(long count, long bytesPerElement) {
        nonNegative(count, "count");
        nonNegative(bytesPerElement, "bytesPerElement");
        return Math.multiplyExact(count, bytesPerElement);
    }

    static long alignedRowBytes(long columns, long bytesPerPixel, long alignment) {
        nonNegative(columns, "columns");
        nonNegative(bytesPerPixel, "bytesPerPixel");
        if (alignment <= 0) throw new IllegalArgumentException("alignment must be > 0");
        long raw = Math.multiplyExact(columns, bytesPerPixel);
        long remainder = raw % alignment;
        long padding = remainder == 0 ? 0 : alignment - remainder;
        return Math.addExact(raw, padding);
    }

    static long gridBytes(long rows, long columns, long bytesPerPixel, long alignment) {
        nonNegative(rows, "rows");
        long stride = alignedRowBytes(columns, bytesPerPixel, alignment);
        return Math.multiplyExact(rows, stride);
    }

    static long pageCount(long bytes, long pageBytes) {
        nonNegative(bytes, "bytes");
        if (pageBytes <= 0) throw new IllegalArgumentException("pageBytes must be > 0");
        long wholePages = bytes / pageBytes;
        return bytes % pageBytes == 0 ? wholePages : Math.addExact(wholePages, 1);
    }

    static int arrayLength(long requestedLength) {
        nonNegative(requestedLength, "requestedLength");
        return Math.toIntExact(requestedLength);
    }

    static void expectedError(String label, Class<? extends Throwable> expected,
                              Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected " + expected.getSimpleName() + ": " + label);
        } catch (Throwable failure) {
            if (!expected.isInstance(failure)) throw failure;
            System.out.println(label + "=" + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        int incorrect = 70_000 * 70_000;
        System.out.println("uncheckedInt=" + incorrect);
        System.out.println("wideProduct=" + elementBytes(70_000, 70_000));
        System.out.println("rowStride=" + alignedRowBytes(3, 3, 4));
        System.out.println("smallGrid=" + gridBytes(2, 3, 3, 4));
        long imageBytes = gridBytes(3_000, 4_000, 4, 64);
        System.out.println("imageBytes=" + imageBytes);
        System.out.println("pages=" + pageCount(imageBytes, 4_096));
        System.out.println("zeroPages=" + pageCount(0, 4_096));
        System.out.println("maxPages=" + pageCount(Long.MAX_VALUE, Long.MAX_VALUE));
        System.out.println("arrayLength=" + arrayLength(4_096));

        expectedError("intOverflow", ArithmeticException.class,
                () -> Math.multiplyExact(70_000, 70_000));
        expectedError("longOverflow", ArithmeticException.class,
                () -> elementBytes(Long.MAX_VALUE, 2));
        expectedError("alignmentOverflow", ArithmeticException.class,
                () -> alignedRowBytes(Long.MAX_VALUE - 2, 1, 8));
        expectedError("negativeCount", IllegalArgumentException.class,
                () -> elementBytes(-1, 8));
        expectedError("zeroAlignment", IllegalArgumentException.class,
                () -> alignedRowBytes(3, 4, 0));
        expectedError("arrayLengthOverflow", ArithmeticException.class,
                () -> arrayLength(2_147_483_648L));

        BigInteger huge = BigInteger.valueOf(Long.MAX_VALUE).multiply(BigInteger.valueOf(8));
        System.out.println("hugeBytes=" + huge);
        expectedError("bigIntegerToLong", ArithmeticException.class, huge::longValueExact);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac CheckedSizeDemo.java
java CheckedSizeDemo
```

Kết quả **đã kiểm chứng thực tế** khi biên dịch với `javac --release 17`:

```text
uncheckedInt=605032704
wideProduct=4900000000
rowStride=12
smallGrid=24
imageBytes=48000000
pages=11719
zeroPages=0
maxPages=1
arrayLength=4096
intOverflow=ArithmeticException
longOverflow=ArithmeticException
alignmentOverflow=ArithmeticException
negativeCount=IllegalArgumentException
zeroAlignment=IllegalArgumentException
arrayLengthOverflow=ArithmeticException
hugeBytes=73786976294838206456
bigIntegerToLong=ArithmeticException
```

**Các phép kiểm chứng quan trọng:**

1. `uncheckedInt` là ví dụ số **sai do tràn nhưng không báo lỗi**; `Math.multiplyExact` với overload `int` báo lỗi rõ ràng.
2. `wideProduct` là phép nhân theo `long`, cho kết quả 4.900.000.000.
3. `rowStride=12` là số byte hàng sau padding; `smallGrid=24` là hai hàng.
4. `imageBytes=48000000`: `4000 × 4 = 16000` byte/hàng, đã chia hết cho alignment 64; nhân 3000 hàng được 48.000.000 byte.
5. `pages=11719` chứng minh làm tròn lên bằng chia dư, không dùng cộng `pageSize-1` dễ tràn.
6. `maxPages=1` xử lý đầu vào cận trên `long` mà không tràn.
7. Những dòng mang tên `*Overflow` và lỗi đầu vào chứng minh API **ném ngoại lệ đúng loại** thay vì trả giá trị size âm/sai.
8. `hugeBytes` vượt phạm vi `long` và được tính bằng `BigInteger`; chuyển về `long` bằng `longValueExact()` báo lỗi đúng.

Hàm `expectedError` chỉ phục vụ bài kiểm thử. Ở ứng dụng thật, có thể dùng JUnit để kiểm tra `assertThrows` thay vì tự tạo helper. Vì hàm này chỉ chạy tác vụ dự kiến ném ngoại lệ, nó không dùng để nuốt những lỗi ngoài dự kiến; ngoại lệ sai loại vẫn được ném tiếp.

## 9. Phân biệt bytes, elements và số hàng

Một trong những lỗi không phải overflow nhưng cũng nguy hiểm là nhầm đơn vị:

```text
count           : số phần tử
bytesPerElement : byte/phần tử
totalBytes      : byte
rowStride       : byte/hàng
pageSize        : byte/trang
pageCount       : số trang
```

Nếu kích thước là `long bytes = 4_000_000_000L` thì **không phải** có thể tạo `new int[4_000_000_000]`. `int[]` nhận **số phần tử** kiểu `int`, không nhận số byte. Với mảng `int[]`, số byte cho dữ liệu phần tử thường là `4 × count` (chưa tính overhead đối tượng và yêu cầu bộ nhớ khác).

Để chuyển yêu cầu từ byte sang số phần tử, phải định nghĩa chính sách:
- Nếu yêu cầu phải chia hết cho kích thước mỗi phần tử, kiểm tra `bytes % bytesPerElement == 0` rồi chia.
- Nếu có thể cấp phát dư một phần tử, dùng quy tắc làm tròn lên an toàn.
- Cuối cùng kiểm tra số phần tử có nằm trong miền `int` hay không.

Ví dụ dưới đây là **đoạn phương thức minh họa**, không cần cấp phát thật:

```java
static int exactElementCount(long totalBytes, long bytesPerElement) {
    if (totalBytes < 0 || bytesPerElement <= 0) {
        throw new IllegalArgumentException("invalid byte arguments");
    }
    if (totalBytes % bytesPerElement != 0) {
        throw new IllegalArgumentException("not divisible");
    }
    return Math.toIntExact(totalBytes / bytesPerElement);
}
```

Kiểm tra `Math.toIntExact` mới chỉ xác nhận miền kiểu `int`. JVM có thể có **giới hạn mảng thực tế thấp hơn `Integer.MAX_VALUE`**, và việc cấp phát còn phụ thuộc heap còn trống. Không sử dụng `Math.toIntExact` như một bảo đảm “cấp phát sẽ luôn thành công”.

## 10. BigInteger khi yêu cầu kích thước vượt Long.MAX_VALUE

Nếu chỉ cần **ước lượng, báo cáo hoặc tính dung lượng logic** rất lớn, việc `long` không đủ không nhất thiết là dữ liệu lỗi. `BigInteger` biểu diễn số nguyên có độ lớn không bị giới hạn bởi 64 bit (vẫn chịu tài nguyên bộ nhớ):

```java
BigInteger a = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger size = a.multiply(BigInteger.valueOf(8));
System.out.println(size); // 73786976294838206456
```

`BigInteger.multiply()` không gặp overflow 64 bit. Tuy nhiên, `BigInteger` không tự khiến bạn có thể cấp phát một mảng lớn như kết quả đó. Hãy tách rõ:
- **Kích thước lý thuyết**: có thể tính chính xác bằng `BigInteger`.
- **Kích thước có thể biểu diễn bằng long**: dùng `big.longValueExact()`; nếu vượt phạm vi, ném `ArithmeticException`.
- **Kích thước hợp lệ cho API cấp phát**: có thể cần `int`, ngưỡng ứng dụng và giới hạn thực tế của JVM/tài nguyên.

Không dùng `big.longValue()` khi cần phép chuyển không mất dữ liệu: nó có thể làm mất các bit cao của giá trị. Dùng `longValueExact()` để phát hiện khi không biểu diễn được.

## 11. Chính sách lỗi: fail fast, giới hạn và chia nhỏ

Khi tính kích thước, có ba cách xử lý tùy mục đích:

**1. Fail fast khi tràn.** `Math.*Exact` là lựa chọn mặc định tốt nếu giá trị sai có thể làm hỏng địa chỉ, buffer, offset hoặc kiểm tra an toàn. Ném lỗi thay vì âm thầm quay vòng.

**2. Giới hạn theo ngân sách tài nguyên.** Bên cạnh kiểm tra overflow, kiểm tra giới hạn nghiệp vụ, ví dụ `requestedBytes <= maxAllowedBytes`. Giới hạn này phải là cấu hình rõ ràng và áp dụng trước khi thử cấp phát. Không tự động “kẹp” một yêu cầu 10 GB thành 100 MB nhưng vẫn hành xử như đã cấp phát đủ 10 GB.

**3. Chia nhỏ dữ liệu.** Khi tổng kích thước hợp lệ về mặt logic nhưng không thể tạo một mảng/buffer đơn lẻ, chia thành các chunk có kích thước an toàn, theo dõi tổng số byte đã xử lý bằng `long` hoặc `BigInteger` khi thích hợp. Cần kiểm tra toán học offset và lượng còn lại ở mỗi bước.

Một điều không được lẫn lộn: **kiểm tra tràn số nguyên** chỉ trả lời “số đếm này có biểu diễn đúng trong kiểu không?”. Nó **không bảo đảm** JVM còn heap, native memory, disk space hoặc quota để thực thi.

## 12. Test kế hoạch: ca biên và bất biến

### 12.1. Test table

| Đầu vào/đặc tính | Kết quả mong đợi |
| --- | --- |
| `elementBytes(0, 4)` | `0` |
| `elementBytes(1, 4)` | `4` |
| `elementBytes(70_000, 70_000)` | `4_900_000_000L` |
| `elementBytes(Long.MAX_VALUE, 1)` | `Long.MAX_VALUE` |
| `elementBytes(Long.MAX_VALUE, 2)` | `ArithmeticException` |
| `elementBytes(-1, 4)` | `IllegalArgumentException` |
| `alignedRowBytes(3, 3, 4)` | `12` |
| `alignedRowBytes(3, 3, 1)` | `9` |
| `alignedRowBytes(3, 3, 0)` | `IllegalArgumentException` |
| `alignedRowBytes(Long.MAX_VALUE-2, 1, 8)` | `ArithmeticException` |
| `pageCount(0,4096)` | `0` |
| `pageCount(4096,4096)` | `1` |
| `pageCount(4097,4096)` | `2` |
| `pageCount(Long.MAX_VALUE, Long.MAX_VALUE)` | `1` |
| `arrayLength(2_147_483_648L)` | `ArithmeticException` |

Kiểm thử overflow bằng việc **kỳ vọng ngoại lệ**, không phải chỉ kiểm tra rằng kết quả có dấu âm. Test cả trường hợp tổng vẫn dương sau khi quay vòng.

### 12.2. Những bất biến hữu ích

Với `rows, columns, bytesPerPixel >= 0`, `alignment > 0` và giả sử không tràn:

- `stride >= rawRowBytes`.
- `stride % alignment == 0`.
- `0 <= stride - rawRowBytes < alignment`.
- `totalBytes == rows × stride` theo toán học chính xác.
- `pageCount(bytes, pageSize) × pageSize >= bytes` **về mặt toán học**; nếu nhân bằng `long` để kiểm thử, bản thân tích có thể tràn. Dùng `BigInteger` hoặc kiểm tra bằng chia/dư.
- Với `bytes > 0`, `pageCount(bytes, pageSize) >= 1`.
- Nếu `bytes` tăng mà `pageSize` cố định, `pageCount` không được giảm.

Bài test tự động có thể sinh ngẫu nhiên tham số **trong vùng hợp lệ**, tính kết quả tham chiếu bằng `BigInteger`, rồi kiểm tra rằng:
1. khi giá trị tham chiếu nằm trong `0..Long.MAX_VALUE`, hàm `long` trả cùng giá trị;
2. khi vượt phạm vi `long`, hàm ném `ArithmeticException`;
3. khi đối số âm hoặc divisor/alignment không dương, hàm ném `IllegalArgumentException`.

Cần tách test đầu vào không hợp lệ khỏi test overflow để tránh khẳng định nhầm loại lỗi.

## 13. Những lỗi phổ biến và cách sửa

### Lỗi 1: nhân int rồi mới gán long

```java
int width = 70_000, height = 70_000;

long wrong = width * height;        // sai vì overflow int
long correct = (long) width * height; // đúng trong phạm vi long
long checked = Math.multiplyExact((long) width, height);
```

### Lỗi 2: chỉ kiểm tra kết quả âm

```java
int size = width * height;
if (size < 0) {
    // Không bắt hết trường hợp overflow!
}
```

Ví dụ `70_000 × 70_000` tràn thành số dương 605.032.704. Phải kiểm tra phép toán thay vì suy từ dấu kết quả.

### Lỗi 3: dùng phép cộng trước khi chia để ceil

```java
// Có nguy cơ tràn:
long pages = (bytes + pageSize - 1) / pageSize;
```

Sửa bằng chia và phần dư, với các ràng buộc byte không âm và pageSize dương.

### Lỗi 4: căn chỉnh mà không kiểm tra cộng padding

```java
long stride = raw + padding; // có thể tràn long
```

Sửa thành `Math.addExact(raw, padding)`, sau khi đã đảm bảo padding hợp lệ.

### Lỗi 5: dùng toIntExact và nghĩ có thể cấp phát mọi mảng

`Math.toIntExact(long)` chỉ đảm bảo phép chuyển kiểu không mất thông tin. JVM và heap có giới hạn riêng. Cần ngưỡng cấp phát/chunk phù hợp, và xử lý tình huống thiếu bộ nhớ theo kiến trúc hệ thống.

### Lỗi 6: trộn đơn vị KB, KiB, MB, MiB

- `1 KB = 1000 byte`.
- `1 KiB = 1024 byte`.
- `1 MB = 1_000_000 byte`.
- `1 MiB = 1_048_576 byte`.

Đừng so sánh một giá trị byte với “MB” không xác định hệ thập phân/hệ nhị phân. Tốt hơn đặt tên biến chứa đơn vị như `fileBytes`, `pageBytes`, `maxBytes` và xác định quy ước trong tài liệu.

### Lỗi 7: cho rằng nhân chính xác đồng nghĩa kích thước hợp lệ

`Math.multiplyExact(-2, 4)` trả -8 mà **không tràn**, nhưng kích thước âm không hợp lệ. Phải xác minh tính hợp lệ **trước hoặc cùng lúc** với phép tính.

### Lỗi 8: chuyển BigInteger sang long mà không kiểm tra

`BigInteger.longValue()` có thể cắt mất dữ liệu; `longValueExact()` ném lỗi khi không chứa vừa `long`.

### Lỗi 9: tính đúng tổng nhưng sai phép nhân trung gian

Nếu phép tính gồm nhiều bước, một giá trị trung gian có thể vượt phạm vi dù kết quả sau đó được chia nhỏ trở lại. Nếu cần thực hiện phép toán chính xác trên giá trị trung gian lớn, dùng `BigInteger` cho giai đoạn đó hoặc biến đổi đại số một cách có chứng minh để tránh overflow.

### Lỗi 10: âm thầm nuốt ArithmeticException

Nếu `Math.*Exact` ném lỗi, việc trả `0` thay thế có thể dẫn đến **cấp phát ít hơn yêu cầu** và lỗi dữ liệu. Chỉ dùng fallback nếu hợp đồng nghiệp vụ đã định nghĩa rõ và người gọi có thể phân biệt lỗi với trường hợp kích thước thực sự bằng 0.

## 14. Bài luyện tập

**Bài 1.** Tính kích thước pixel cho 70.000 × 70.000, mỗi pixel 4 byte. Vì sao `(long)(70_000 * 70_000 * 4)` sai?  
**Đáp án:** biểu thức bên trong cast được tính bằng `int` và đã tràn. Dùng `Math.multiplyExact(Math.multiplyExact(70_000L, 70_000L), 4L)` → 19.600.000.000 byte, hoặc cách tương đương có kiểm tra.

**Bài 2.** Với raw row 13 byte và alignment 8, padding/stride là bao nhiêu?  
**Đáp án:** 13 % 8 = 5, padding = 3, stride = 16.

**Bài 3.** Vì sao `(Long.MAX_VALUE + 4) / 4` không phải cách tính số trang an toàn?  
**Đáp án:** phép cộng `long` tràn trước khi chia. Dùng thương và phần dư.

**Bài 4.** Nếu cần phân bổ 3.000.000.000 phần tử trong một `int[]`, `Math.toIntExact(3_000_000_000L)` xử lý thế nào?  
**Đáp án:** ném `ArithmeticException` vì số phần tử không vừa miền `int`. Ngay cả số phần tử vừa `int` cũng có thể không cấp phát được.

**Bài 5.** Khi cần biểu diễn kích thước 8 × `Long.MAX_VALUE`, kiểu số nào phù hợp để tính giá trị lý thuyết?  
**Đáp án:** `BigInteger`. Nó tính chính xác giá trị 73.786.976.294.838.206.456; không thể chuyển về `long` bằng `longValueExact()`.

**Bài 6.** Viết phương thức tính `totalBytes = rows × alignedRowBytes(columns,bpp,alignment)`, làm gì để không có overflow âm thầm?  
**Đáp án:** kiểm tra rows/columns/bpp không âm và alignment dương; dùng `Math.multiplyExact(columns,bpp)`, chia dư để tính padding, `Math.addExact(raw,padding)` rồi `Math.multiplyExact(rows,stride)`.

## 15. Checklist trước khi đưa vào sản phẩm

1. Tất cả tham số có **đơn vị** và phạm vi hợp lệ rõ ràng chưa?
2. Các phép toán `+`, `-`, `*` trên kích thước/offset có dùng exact arithmetic hoặc cách chứng minh an toàn chưa?
3. Nếu có phép nhân `int`, đã chuyển đúng toán hạng sang `long` **trước** phép nhân chưa?
4. Có chia/làm tròn lên không? Đã tránh `bytes + pageSize - 1` chưa?
5. Căn chỉnh có kiểm tra overflow ở bước cộng padding không?
6. Phân biệt kích thước logic `long/BigInteger` với độ dài mảng `int` và tài nguyên vật lý chưa?
7. Mọi phép chuyển thu hẹp kiểu có dùng `Math.toIntExact` hoặc phương án được kiểm tra tương đương chưa?
8. Khi yêu cầu vượt ngân sách, có báo lỗi minh bạch hoặc chia chunk thay vì cấp phát thiếu không?
9. Test đã có ca 0, âm, boundary, overflow cho số dương và case alignment overflow chưa?
10. Có kiểm tra rằng tính đúng số byte vẫn **không có nghĩa** sẽ luôn cấp phát thành công không?

## 16. Kết luận

- Dùng **`Math.multiplyExact`, `Math.addExact` và `Math.toIntExact`** để phát hiện tràn và mất dữ liệu khi tính kích thước.
- Với số nguyên thông thường, **gán kết quả tràn `int` sang `long` không sửa được phép tính**; phải mở rộng kiểu trước.
- Với kích thước được căn chỉnh, tính padding từ phần dư và cộng bằng `Math.addExact`; với số trang, dùng thương và phần dư thay công thức cộng `pageSize-1`.
- Kiểm tra **đối số âm, đơn vị, ngưỡng tài nguyên** bên cạnh kiểm tra số học.
- Khi kết quả lý thuyết vượt `long`, dùng `BigInteger`; nếu một API yêu cầu `long` hoặc `int`, chuyển bằng phương thức `*ValueExact` hoặc `Math.toIntExact` để phát hiện không biểu diễn được.
- Số đếm **đúng** không đảm bảo bộ nhớ/đĩa **đủ**; cả hai lớp kiểm tra đều cần trong hệ thống an toàn.

Tài liệu tham khảo chính thức Java SE 17:
- [`Math` — multiplyExact, addExact, subtractExact, toIntExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)
- [`BigInteger` — multiply, longValueExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)
- [`ArithmeticException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ArithmeticException.html)
- [`IllegalArgumentException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html)
