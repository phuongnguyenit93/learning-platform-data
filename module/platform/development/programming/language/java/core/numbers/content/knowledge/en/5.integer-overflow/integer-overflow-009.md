# Kiểm tra giới hạn trước khi cấp phát hoặc tính kích thước trong Java

Một kích thước trông có vẻ hợp lệ khi được lưu trong `int` vẫn có thể trở thành **số âm, số quá nhỏ, hoặc vượt xa ngân sách bộ nhớ** sau phép nhân/cộng. Vì Java quyết định kiểu tính toán từ kiểu toán hạng, sự cố thường xảy ra **trước** lệnh cấp phát:

```java
int elements = 1_000_000_000;
int bytesPerElement = 8;

int wrongBytes = elements * bytesPerElement;  // -589934592 (int overflow)
long exactBytes = (long) elements * bytesPerElement; // 8000000000
```

Tích toán học là 8.000.000.000 byte, vượt `Integer.MAX_VALUE`. Phép `int * int` chỉ giữ kết quả trong miền 32 bit nên `wrongBytes` thành `-589934592`. Nếu kiểm tra ngân sách bằng giá trị đã tràn, ứng dụng có thể **chấp nhận sai, cấp phát sai kích thước hoặc ném ngoại lệ muộn**.

Bài này tập trung vào cách xác định kích thước cần thiết một cách chính xác, kiểm tra giới hạn và chỉ sau đó mới chuyển kiểu/cấp phát, nhất là với **mảng, buffer, dữ liệu nhị phân, chuỗi và thông tin độ dài lấy từ bên ngoài**.

## 1. Vì sao phép tính kích thước dễ tràn?

Các biểu thức sau trông đơn giản nhưng đều có rủi ro:

- `count * bytesPerItem`: tính dung lượng payload từ số phần tử và kích thước mỗi phần tử.
- `headerBytes + payloadBytes`: tính tổng kích thước gói dữ liệu.
- `offset + length`: xác định vị trí kết thúc của một lát mảng hoặc buffer.
- `capacity * growthFactor`: tăng dung lượng cấu trúc dữ liệu.
- `rows * columns` hoặc `width * height * channels`: tính số phần tử của ma trận/ảnh.
- `(count + pageSize - 1) / pageSize`: làm tròn số trang lên; biểu thức cộng có thể tràn trước phép chia.

Các toán hạng `int` có thể đều hợp lệ và không âm nhưng **kết quả trung gian không còn nằm trong miền `int`**. Tương tự, hai giá trị `long` hợp lệ vẫn có thể cho tích vượt `Long.MAX_VALUE`.

| Biểu thức | Vấn đề | Cách tiếp cận |
| --- | --- | --- |
| `int bytes = count * 8` | `int` overflow trước khi kiểm tra | `long bytes = (long) count * 8` hoặc `Math.multiplyExact` |
| `long bytes = count * 8`, `count` là `int` | Phép nhân vẫn là `int` | Nâng toán hạng **trước** dấu nhân |
| `int total = header + payload` | Tổng có thể tràn | Tính bằng `long` hoặc dùng `Math.addExact` |
| `int end = offset + length` | Vị trí kết thúc có thể tràn | Kiểm tra bằng phép trừ an toàn sau xác minh số không âm |
| `int newCapacity = capacity * 2` | Gấp đôi có thể quấn vòng thành số âm | Kiểm tra trước khi nhân, đặt giới hạn tăng trưởng |
| `(int) largeCount` | Thu hẹp `long` có thể mất bit cao | Kiểm tra miền hoặc dùng `Math.toIntExact` |

**Đừng chỉ kiểm tra kết quả cuối** nếu trước đó đã có toán tử nguyên tràn. Khi bit đã mất, một điều kiện như `if (size <= maxBytes)` không thể khôi phục kích thước đúng.

## 2. Kiểm tra đầu vào và quy tắc “tính rộng, kiểm tra, mới thu hẹp”

Một quy trình an toàn gồm các bước:

1. **Xác định đơn vị và ngữ nghĩa**: `count` là số phần tử, `bytesPerElement` là số byte một phần tử, `maxBytes` là ngân sách payload; không so sánh byte với số phần tử.
2. **Kiểm tra điều kiện đầu vào**: số phần tử và offset không âm; kích thước một đơn vị dương; giới hạn nghiệp vụ hợp lệ. Dữ liệu từ file/network/user cần được xem là chưa tin cậy.
3. **Tính bằng kiểu phù hợp và phát hiện tràn**: mở rộng lên `long` **trước phép toán `int` có nguy cơ tràn**, hoặc dùng `Math.multiplyExact` / `Math.addExact`. Nếu `long` vẫn chưa đủ, cần giới hạn miền từ trước hoặc tính bằng `BigInteger`.
4. **Đối chiếu các ngưỡng độc lập**: giới hạn số phần tử, dung lượng payload, kích thước một allocation, dung lượng tổng đang sử dụng và giới hạn cấu hình ứng dụng.
5. **Chuyển sang kiểu API đích sau khi kiểm tra**: phần lớn độ dài mảng/`ByteBuffer` nhận `int`; dùng `Math.toIntExact` khi nhận kích thước `long` cần chắc chắn không vượt miền `int`.
6. **Cấp phát và xử lý lỗi tài nguyên**: kích thước hợp lệ không bảo đảm JVM còn đủ heap hoặc có thể cấp phát một khối liên tục lớn.

Chẳng hạn, nguyên tắc đúng để tính payload của `long[]` có `n` phần tử là kiểm tra tích `n * Long.BYTES` ở miền `long` và ngân sách **trước** khi gọi `new long[length]`. `Long.BYTES` bằng 8; ngân sách payload ở đây chưa tính overhead mảng, căn chỉnh hay chi phí các object khác.

### Nâng kiểu trước phép nhân, không cast kết quả đã tràn

```java
int elements = 1_000_000_000;

long wrong = (long) (elements * 8);  // -589934592
long right = (long) elements * 8;    // 8000000000
```

Trong `wrong`, phép `int * int` đã tràn trước khi cast. Trong `right`, toán hạng `elements` được mở rộng trước nên phép `long * int` tính theo `long`. Nhưng `long` vẫn có thể tràn với đầu vào rất lớn; vì vậy **nâng kiểu và kiểm tra giới hạn là hai yêu cầu bổ sung cho nhau**.

## 3. Kiểm tra overflow bằng API `Math`

### `Math.multiplyExact` và `Math.addExact`

`Math.multiplyExact` có các overload `int` và `long`; chúng ném `ArithmeticException` nếu kết quả vượt miền của kiểu tương ứng:

```java
int count = 1_000_000_000;

// Math.multiplyExact(count, 8); // ném ArithmeticException: vượt int
long payload = Math.multiplyExact((long) count, 8L); // 8000000000

long header = 128L;
long packetSize = Math.addExact(header, payload);    // 8000000128
```

Nếu cả hai đối số `Math.multiplyExact` là `int`, phép kiểm tra diễn ra **trong miền `int`**. Muốn tích `long`, hãy chuyển một toán hạng sang `long` trước lời gọi.

Đặc biệt, **không viết**:

```java
long wrong = Math.addExact((long) (count * 8), 128L);
```

Vì `count * 8` đã tràn trong ngoặc. `Math.addExact` chỉ kiểm tra phép **cộng** nhận đầu vào của nó; nó không biết phép nhân trước đó đã sai.

### `Math.toIntExact`

Các API như `new byte[length]`, `ByteBuffer.allocate(capacity)` và các chỉ số mảng yêu cầu `int`. Khi đang có `long length`, `Math.toIntExact(length)` sẽ ném `ArithmeticException` nếu giá trị không biểu diễn được trong `int`:

```java
long elementCount = (long) Integer.MAX_VALUE + 1L;
// int unsafe = (int) elementCount;   // Có thể quấn vòng
// int safe = Math.toIntExact(elementCount); // Ném ArithmeticException
```

**Giới hạn `int` chỉ là một điều kiện cần.** Một mảng có độ dài gần `Integer.MAX_VALUE` có thể vượt giới hạn kích thước mảng thực tế của JVM hoặc không đủ bộ nhớ. Không coi `Math.toIntExact` là bằng chứng rằng allocation sẽ thành công.

### `BigInteger` khi phép tính lớn hơn `long`

Nếu phép nhân `long * long` có thể vượt 64 bit nhưng vẫn phải tính chính xác để **so sánh với quota**, `BigInteger` tránh overflow:

```java
import java.math.BigInteger;

// Mảnh mã minh họa bên trong một phương thức:
long rows = 5_000_000_000L;
long cols = 5_000_000_000L;
BigInteger cells = BigInteger.valueOf(rows)
        .multiply(BigInteger.valueOf(cols));
boolean tooLarge = cells.compareTo(BigInteger.valueOf(1_000_000L)) > 0;
// tooLarge = true
```

Nên kiểm tra trực tiếp điều kiện số lượng theo giới hạn cấu hình nếu có thể, nhằm tránh thực hiện phép toán không cần thiết với dữ liệu không đáng tin cậy.

## 4. Giới hạn của mảng và buffer trong Java

Java yêu cầu **độ dài một chiều của mảng là `int` không âm**:

```java
int n = 8;
long[] values = new long[n];  // Mảng primitive có 8 phần tử
```

Lưu ý:

- `new int[-1]` với độ dài âm lúc chạy gây `NegativeArraySizeException`.
- Một kích thước không âm nhưng quá lớn có thể gây `OutOfMemoryError`; JVM còn có giới hạn chiều dài mảng thực tế, không nên giả định có thể cấp phát đúng `Integer.MAX_VALUE` phần tử.
- Ngay cả khi payload lý thuyết nằm trong ngân sách, **object header, căn chỉnh, bộ nhớ đang dùng, tham chiếu object, bộ sưu tập và heap hiện tại** đều ảnh hưởng khả năng cấp phát.
- `ByteBuffer.allocate(int capacity)` tạo buffer trong heap, còn `ByteBuffer.allocateDirect(int capacity)` yêu cầu vùng bộ nhớ trực tiếp; chúng có điều kiện tài nguyên khác nhau. Capacity âm là không hợp lệ và phải được kiểm tra trước. Cả hai vẫn dùng `int` làm capacity.
- Một `byte[]` có `n` phần tử nghĩa là `n` byte dữ liệu; đối với `long[]`, payload sơ bộ `n * 8` byte. Với `Object[]` hoặc object graph, không thể giả định chi phí cố định chỉ từ số phần tử vì bộ nhớ cho tham chiếu và các object được tham chiếu phụ thuộc JVM và cấu trúc dữ liệu.
- Với chuỗi, **số ký tự không đồng nghĩa số byte sau mã hóa**: `String.length()` đếm đơn vị mã UTF-16; UTF-8 có độ dài biến thiên. Nếu giới hạn được tính bằng byte để gửi/ghi dữ liệu, phải tính theo kết quả mã hóa hoặc API cung cấp kích thước thực tế.
- `int[][]` là **mảng các tham chiếu đến từng mảng hàng**; hãy kiểm tra cả số hàng, số cột, tổng phần tử và chi phí nhiều mảng, không chỉ tích `rows * columns`.

`OutOfMemoryError` phản ánh thất bại tài nguyên, **không nên dùng nó như cơ chế kiểm tra kích thước bình thường**. Ứng dụng cần đặt ngưỡng chủ động trước allocation, đồng thời vẫn thừa nhận allocation có thể thất bại vì áp lực bộ nhớ.

## 5. Kiểm tra `offset + length` không gây tràn

Xử lý một lát mảng hoặc buffer thường có ba giá trị `offset`, `length`, `capacity`. Điều kiện hợp lệ:

\[
0 \leq offset,\quad 0 \leq length,\quad offset + length \leq capacity.
\]

Viết trực tiếp `offset + length <= capacity` có thể nguy hiểm nếu phép cộng `int` tràn. Chẳng hạn `offset` gần `Integer.MAX_VALUE` và `length` dương làm tổng thành số âm, khiến một điều kiện sai được chấp nhận.

Sau khi xác minh tất cả không âm, dùng phép trừ:

```java
static boolean validSlice(int offset, int length, int capacity) {
    return offset >= 0
            && length >= 0
            && capacity >= 0
            && offset <= capacity
            && length <= capacity - offset;
}
```

Đây là đoạn phương thức minh họa, không phải class độc lập. Vì Java đánh giá `&&` theo thứ tự và ngừng khi điều kiện trước sai, `capacity - offset` chỉ thực hiện sau khi đã biết `0 <= offset <= capacity`, nên không gây overflow. Nếu đang làm việc với API Java có sẵn, cũng có thể dùng `Objects.checkFromIndexSize(fromIndex, size, length)` để kiểm tra lát chỉ số; API sẽ ném `IndexOutOfBoundsException` khi không hợp lệ.

Với các phép cộng kích thước bắt buộc như `header + payload`, hãy dùng `Math.addExact` thay vì tin rằng kết quả nguyên có dấu không tràn.

## 6. Chương trình Java 17+ kiểm tra trước khi cấp phát

Ví dụ dưới đây dùng **giới hạn số phần tử của ứng dụng** và **ngân sách payload**. Hai giới hạn này phải được chọn theo thực tế, không lấy từ giá trị không tin cậy. Chương trình chỉ cấp phát một mảng nhỏ để minh họa; các trường hợp kích thước quá lớn được kiểm tra bằng phép toán, **không thử tạo mảng khổng lồ**.

Lưu vào tệp `AllocationBoundsDemo.java`:

```java
public class AllocationBoundsDemo {
    private static int checkedLength(
            long elements,
            long bytesPerElement,
            long maxElements,
            long maxPayloadBytes) {

        if (elements < 0 || bytesPerElement <= 0
                || maxElements < 0 || maxPayloadBytes < 0) {
            throw new IllegalArgumentException("invalid length or limits");
        }
        if (elements > maxElements) {
            throw new IllegalArgumentException("element limit exceeded");
        }

        long payloadBytes = Math.multiplyExact(elements, bytesPerElement);
        if (payloadBytes > maxPayloadBytes) {
            throw new IllegalArgumentException("payload budget exceeded");
        }

        return Math.toIntExact(elements);
    }

    private static boolean validSlice(int offset, int length, int capacity) {
        return offset >= 0 && length >= 0 && capacity >= 0
                && offset <= capacity && length <= capacity - offset;
    }

    public static void main(String[] args) {
        int elements = 1_000_000_000;
        System.out.println("unchecked int bytes: " + (elements * 8));
        System.out.println("exact long bytes: "
                + Math.multiplyExact((long) elements, 8));

        try {
            Math.multiplyExact(elements, 8);
        } catch (ArithmeticException e) {
            System.out.println("int product overflow detected");
        }

        int length = checkedLength(8, 8, 1_000, 1_024);
        long[] values = new long[length];
        System.out.println("allocated array length: " + values.length);

        try {
            checkedLength(200, 8, 1_000, 1_024);
        } catch (IllegalArgumentException e) {
            System.out.println("budget rejection: " + e.getMessage());
        }

        try {
            checkedLength(-1, 8, 1_000, 1_024);
        } catch (IllegalArgumentException e) {
            System.out.println("negative length rejected");
        }

        try {
            Math.multiplyExact(Long.MAX_VALUE, 2L);
        } catch (ArithmeticException e) {
            System.out.println("long product overflow detected");
        }

        try {
            Math.toIntExact((long) Integer.MAX_VALUE + 1L);
        } catch (ArithmeticException e) {
            System.out.println("array index range exceeded");
        }

        System.out.println("valid slice: " + validSlice(8, 4, 16));
        System.out.println("invalid slice: "
                + validSlice(Integer.MAX_VALUE - 1, 10, Integer.MAX_VALUE));

        try {
            int negative = -1;
            int[] unused = new int[negative];
        } catch (NegativeArraySizeException e) {
            System.out.println("negative array size exception");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac AllocationBoundsDemo.java
java AllocationBoundsDemo
```

Kết quả stdout:

```text
unchecked int bytes: -589934592
exact long bytes: 8000000000
int product overflow detected
allocated array length: 8
budget rejection: payload budget exceeded
negative length rejected
long product overflow detected
array index range exceeded
valid slice: true
invalid slice: false
negative array size exception
```

**Giải thích các kiểm tra:**

- Tích `int` bị tràn âm dù dữ liệu đầu vào hợp lệ; `long` tính được giá trị 8 tỷ.
- `Math.multiplyExact(int, int)` báo overflow. `Math.multiplyExact(long, long)` cũng báo lỗi khi tích vượt `long`.
- Hàm `checkedLength` từ chối số lượng âm, số phần tử vượt quota và payload vượt ngân sách; `Math.toIntExact` bảo đảm kết quả có thể biểu diễn dưới dạng `int`.
- Với giới hạn minh họa 1.000 phần tử và 1.024 byte payload, 8 phần tử kiểu `long` dùng 64 byte payload nên cho phép cấp phát mảng nhỏ. 200 phần tử cần 1.600 byte payload nên bị từ chối.
- `validSlice` nhận lát `[8, 12)` trong capacity 16, đồng thời từ chối lát gần `Integer.MAX_VALUE` dù phép cộng trực tiếp có thể overflow.
- Giá trị độ dài âm khiến `new int[negative]` ném `NegativeArraySizeException`; ứng dụng thực tế nên chặn điều kiện này **trước** khi gọi `new`.

Hàm này là mô hình đơn giản cho **một mảng `long[]`**. Khi triển khai, thêm ngưỡng chính sách phù hợp với ứng dụng, có thể kiểm tra ngân sách tổng thể nhiều allocation, và cân nhắc byte overhead thực tế. Không coi `maxPayloadBytes` là số byte heap chắc chắn còn trống.

## 7. Mô hình kiểm tra giới hạn cho một số tình huống

### Trường hợp A: đọc chiều dài một thông điệp nhị phân

Giả sử một gói tin có `headerBytes` và `itemCount` mục dữ liệu, mỗi mục có độ dài cố định `itemBytes`. Quy trình nên là:

1. Giới hạn `itemCount` từ đầu vào về miền được phép, kiểm tra không âm.
2. Tính `payload = Math.multiplyExact((long) itemCount, itemBytes)` sau khi xác nhận kích thước mỗi mục hợp lệ.
3. Tính `packetBytes = Math.addExact(headerBytes, payload)`.
4. So sánh `packetBytes` với giới hạn gói tin cấu hình và lượng dữ liệu thực tế được cung cấp.
5. Chỉ sau khi hợp lệ mới chuyển kiểu cho API cần `int` và cấp phát buffer.

Không tin vào trường độ dài chỉ vì nó được lưu vừa trong `int`. Một trường length có thể **tự nó hợp lệ**, nhưng gây overflow khi nhân với đơn vị hoặc cộng header.

### Trường hợp B: bảng dữ liệu/ảnh nhiều chiều

Một ảnh có `height` hàng, `width` cột và `channels` kênh. Nếu lưu mỗi mẫu bằng một byte, số mẫu là `height * width * channels`. Nên kiểm tra:

- `height`, `width`, `channels` dương và nằm trong giới hạn định dạng.
- Tích trung gian không overflow; dùng `Math.multiplyExact` từ đầu với kiểu `long`.
- Tổng số byte nằm trong quota.
- Loại array/buffer định cấp phát đáp ứng số phần tử và giới hạn JVM; một mảng đơn lớn có thể không phù hợp, cần chia thành các khối nhỏ nếu ứng dụng cho phép.

Nếu dữ liệu là ảnh có stride, padding hoặc cấu trúc lồng nhau, `height * width * channels` mới là ước lượng payload thô; phép tính cấp phát phải phù hợp layout thật.

### Trường hợp C: tăng capacity

Một cấu trúc lưu trữ có thể thử `newCapacity = oldCapacity * 2`. Khi `oldCapacity` lớn, phép nhân `int` dễ tràn. Hãy giới hạn mục tiêu tối đa và kiểm tra trước phép nhân:

```java
int oldCapacity = 800;
int maximum = 1_000;
int newCapacity = oldCapacity > maximum / 2
        ? maximum
        : oldCapacity * 2; // 1000, không vượt maximum
```

Đây là ví dụ **khi `oldCapacity >= 0` và `maximum > 0` đã được xác minh**. Một chiến lược tăng trưởng thực tế phải bảo đảm `newCapacity >= minRequiredCapacity`; nếu không đáp ứng được, từ chối yêu cầu. Không tự động xem việc “kẹp” về maximum là thành công nếu dữ liệu vẫn cần nhiều hơn maximum.

### Trường hợp D: phân trang và chia nhóm

Với `count >= 0`, `pageSize > 0`, công thức thường gặp `(count + pageSize - 1) / pageSize` có thể overflow khi `count` gần `Integer.MAX_VALUE`. Thay bằng:

```java
int count = Integer.MAX_VALUE;
int pageSize = 1000;
int pages = count / pageSize + (count % pageSize == 0 ? 0 : 1);
```

Cách này không cộng trước phép chia và giữ số trang trong miền `int` khi `count` không âm, `pageSize` dương. Với số lượng tính bằng `long` hoặc yêu cầu phân trang rất lớn, vẫn phải xét riêng giới hạn của miền đó.

## 8. Các lớp lỗi cần phân biệt

| Vấn đề | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Overflow số học** | `int count * 8` trả số âm | Nâng kiểu trước phép toán, `Math.multiplyExact` |
| **Narrowing mất dữ liệu** | `(int) longLength` với độ dài quá lớn | Kiểm tra miền, `Math.toIntExact` |
| **Length âm** | `new byte[-1]` | Kiểm tra đầu vào, `NegativeArraySizeException` là triệu chứng |
| **Vượt giới hạn JVM / thiếu bộ nhớ** | `new long[veryLarge]` | Quota thực tế, thiết kế streaming/chunking, không dựa vào `OutOfMemoryError` để validate |
| **Sai đơn vị** | So `elementCount` với quota tính bằng byte | Nêu rõ byte/element/character và đổi đơn vị đúng |
| **Sai phép kiểm tra slice** | `offset + length <= capacity` sau khi tổng tràn | Kiểm tra số không âm rồi dùng `length <= capacity - offset` |
| **Vượt quota tích lũy** | Nhiều mảng nhỏ cùng tồn tại | Theo dõi tổng sử dụng, giới hạn đồng thời và áp lực bộ nhớ |
| **Tin trường length do client đưa** | File/network báo độ dài quá lớn | Kiểm tra quota trước đọc toàn bộ và trước allocation |

## 9. Những nhầm lẫn thường gặp

1. **“Tất cả toán hạng đều không âm thì kích thước cũng không âm.”** Sai: phép nhân/cộng `int` có thể overflow sang giá trị âm.
2. **“Đích là `long` nên `int * int` tự động dùng 64 bit.”** Sai: phải chuyển toán hạng sang `long` **trước khi nhân**.
3. **“`(long) (count * unitSize)` sửa overflow.”** Sai: phép nhân `int` đã diễn ra.
4. **“`Math.multiplyExact(count, 8)` tự trả `long` nếu kết quả lớn.”** Sai: overload `int, int` ném lỗi khi vượt `int`; muốn kết quả `long` thì nâng toán hạng.
5. **“Có `long` thì không thể tràn.”** Sai: `long * long` vẫn có thể vượt 64 bit.
6. **“`Math.toIntExact` thành công thì cấp phát sẽ thành công.”** Sai: giới hạn JVM, heap, pressure, layout và quota vẫn áp dụng.
7. **“`new byte[negativeSize]` sẽ tự sửa thành mảng rỗng.”** Sai: ném `NegativeArraySizeException`.
8. **“`offset + length <= capacity` an toàn với mọi số nguyên.”** Sai: phép cộng có thể overflow; kiểm tra bằng phép trừ sau xác minh số không âm.
9. **“Giới hạn payload bằng số byte là đủ để giới hạn heap.”** Sai: còn overhead, alignment, object graph, tham chiếu và allocation đồng thời.
10. **“`String.length()` là số byte UTF-8.”** Sai: `String.length()` đếm đơn vị mã UTF-16, byte mã hóa thay đổi theo nội dung.
11. **“Thấy `OutOfMemoryError` rồi bắt lỗi là đủ để validate.”** Sai: lúc đó JVM có thể đã thiếu tài nguyên nghiêm trọng; cần **kiểm tra, giới hạn và thiết kế theo luồng** từ đầu.
12. **“Chỉ cần kiểm tra một lần ở lúc cấp phát.”** Chưa đủ: còn công thức cộng/nhân khi tăng capacity và việc giữ nhiều allocation đồng thời.

## 10. Tự kiểm tra

- **`int count = 1_000_000_000; long bytes = count * 8;` đúng 8 tỷ không?** Không. Phép nhân `int` tràn trước khi gán. Viết `(long) count * 8` hoặc `Math.multiplyExact((long) count, 8L)`.
- **Có phải mọi `long` hợp lệ đều chuyển thành `int` hợp lệ?** Không; `Math.toIntExact` báo lỗi khi giá trị ngoài miền 32 bit.
- **`Math.multiplyExact(Long.MAX_VALUE, 2L)` làm gì?** Ném `ArithmeticException` vì tích vượt phạm vi `long`.
- **Vì sao kiểm tra `offset <= capacity` và `length <= capacity - offset` tốt hơn cộng trực tiếp?** Với điều kiện không âm phù hợp, không tính một tổng có thể overflow.
- **Payload lý thuyết của 200 phần tử `long` là bao nhiêu?** `200 * 8 = 1600` byte, chưa tính overhead mảng.
- **Nếu byte quota là 1024 mà cần 1600 byte payload?** Từ chối **trước khi cấp phát**; không chờ `OutOfMemoryError`.
- **Vì sao `Integer.MAX_VALUE` không phải giới hạn mảng chắc chắn cấp phát được?** Khả năng cấp phát còn tùy JVM, bộ nhớ và overhead; giới hạn của ứng dụng thường phải nhỏ hơn.

**Ghi nhớ:** Khi tính kích thước, **xác nhận đầu vào → tính bằng kiểu đủ rộng và kiểm tra overflow → so với quota → chuyển về kiểu API → mới cấp phát**. Đừng dùng kích thước đã bị tràn để đánh giá an toàn. Kiểu `long` giúp tránh nhiều overflow `int`, còn `Math.*Exact`, giới hạn ứng dụng và kiểm tra tài nguyên giúp quản lý các trường hợp `long` vẫn chưa đủ.
