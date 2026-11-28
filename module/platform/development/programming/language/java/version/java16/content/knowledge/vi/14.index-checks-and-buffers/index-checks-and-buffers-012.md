# Bulk put trên LongBuffer, FloatBuffer và DoubleBuffer

## 1. Bulk put dùng để làm gì?

Các lớp `LongBuffer`, `FloatBuffer` và `DoubleBuffer` thuộc Java NIO, dùng để lưu và thao tác lần lượt với các giá trị primitive `long`, `float` và `double`. Ngoài thao tác ghi từng phần tử bằng `put(value)`, mỗi lớp còn cung cấp các phương thức bulk `put` để chuyển nhiều phần tử trong một lần gọi.

Bulk put hữu ích khi:

- Chép một đoạn từ mảng primitive vào buffer.
- Chuyển phần dữ liệu còn lại từ một typed buffer sang buffer khác cùng kiểu.
- Ghi dữ liệu theo lô để giảm số lần gọi method trong code.
- Chuẩn bị dữ liệu cho các bước xử lý NIO tiếp theo.

Các API bulk put của ba lớp có cùng mô hình sử dụng:

| Buffer | Mảng nguồn | Buffer nguồn |
| --- | --- | --- |
| `LongBuffer` | `long[]` | `LongBuffer` |
| `FloatBuffer` | `float[]` | `FloatBuffer` |
| `DoubleBuffer` | `double[]` | `DoubleBuffer` |

Đây là các API NIO ổn định, có từ các phiên bản Java trước và vẫn dùng được trong Java hiện đại. Bài học đặt chúng trong môi trường JDK 16; không nên hiểu bulk put là một tính năng mới được giới thiệu riêng ở Java 16.

Mục tiêu bài học:

- Dùng `put(array)` và `put(array, offset, length)`.
- Dùng `put(sourceBuffer)` để chuyển nhiều phần tử giữa các typed buffer.
- Hiểu ảnh hưởng đến `position`, `limit` và `remaining`.
- Phân biệt bulk put tương đối với thao tác ghi từng phần tử.
- Xử lý `BufferOverflowException`, `ReadOnlyBufferException` và lỗi phạm vi mảng.
- Chọn cách copy phù hợp mà không làm thay đổi trạng thái nguồn ngoài ý muốn.

## 2. Các overload bulk put phổ biến

Với `LongBuffer`, các overload thường dùng gồm:

~~~java
LongBuffer put(long[] src)
LongBuffer put(long[] src, int offset, int length)
LongBuffer put(LongBuffer src)
~~~

`FloatBuffer` và `DoubleBuffer` có các overload tương ứng với kiểu primitive của chúng:

~~~java
FloatBuffer put(float[] src)
FloatBuffer put(float[] src, int offset, int length)
FloatBuffer put(FloatBuffer src)

DoubleBuffer put(double[] src)
DoubleBuffer put(double[] src, int offset, int length)
DoubleBuffer put(DoubleBuffer src)
~~~

Ý nghĩa:

- `put(src)`: chép toàn bộ phần tử của mảng vào buffer đích.
- `put(src, offset, length)`: chép `length` phần tử từ mảng nguồn, bắt đầu tại `offset`.
- `put(srcBuffer)`: chép các phần tử còn lại của buffer nguồn, tức vùng từ `srcBuffer.position()` đến trước `srcBuffer.limit()`.

Các phương thức này là thao tác tương đối: khi thành công, `position` của buffer đích tăng theo số phần tử được ghi. Với overload nhận một buffer nguồn, `position` của buffer nguồn cũng được cập nhật sau khi chuyển dữ liệu.

## 3. Bulk put từ mảng bằng put(array)

Ví dụ với `LongBuffer`:

~~~java
import java.nio.LongBuffer;

class LongArrayPut {
    public static void main(String[] args) {
        long[] values = {10L, 20L, 30L, 40L};

        LongBuffer buffer = LongBuffer.allocate(6);
        buffer.put(values);

        System.out.println(buffer.position()); // 4
        System.out.println(buffer.limit());    // 6
        System.out.println(buffer.remaining()); // 2

        buffer.flip();

        while (buffer.hasRemaining()) {
            System.out.println(buffer.get());
        }
    }
}
~~~

Sau `put(values)`:

- Bốn phần tử của mảng được ghi vào buffer.
- `position` của buffer đích tăng từ 0 lên 4.
- `limit` vẫn là 6.
- `remaining()` còn 2 vì buffer vẫn có thể nhận thêm hai phần tử.

`put(values)` không thay đổi mảng nguồn. Mảng Java không có `position` hay `limit`; chỉ trạng thái của buffer đích được cập nhật.

### FloatBuffer và DoubleBuffer

Cách dùng tương tự, chỉ thay kiểu primitive:

~~~java
import java.nio.FloatBuffer;
import java.nio.DoubleBuffer;

class FloatingPointPut {
    public static void main(String[] args) {
        float[] temperatures = {21.5f, 22.0f, 23.25f};
        FloatBuffer floatBuffer = FloatBuffer.allocate(5);
        floatBuffer.put(temperatures);

        double[] measurements = {1.25, 2.5, 5.0};
        DoubleBuffer doubleBuffer = DoubleBuffer.allocate(5);
        doubleBuffer.put(measurements);

        System.out.println(floatBuffer.position());  // 3
        System.out.println(doubleBuffer.position()); // 3
    }
}
~~~

Không có chuyển đổi kiểu tự động giữa các typed buffer trong bulk put. `FloatBuffer` nhận `float[]` hoặc `FloatBuffer`; `DoubleBuffer` nhận `double[]` hoặc `DoubleBuffer`; `LongBuffer` nhận `long[]` hoặc `LongBuffer`.

## 4. Chép một đoạn mảng bằng put(array, offset, length)

Khi chỉ muốn chuyển một phần của mảng, dùng overload có `offset` và `length`:

~~~java
import java.nio.LongBuffer;

class LongArraySlicePut {
    public static void main(String[] args) {
        long[] source = {100L, 200L, 300L, 400L, 500L};

        LongBuffer target = LongBuffer.allocate(4);
        target.put(source, 1, 3);

        System.out.println(target.position()); // 3

        target.flip();
        while (target.hasRemaining()) {
            System.out.println(target.get());
        }
    }
}
~~~

Kết quả được ghi là `200`, `300`, `400`.

Các tham số:

- `src`: mảng nguồn.
- `offset`: index đầu tiên trong mảng nguồn.
- `length`: số phần tử cần chép.

Phạm vi nguồn là khoảng nửa mở `[offset, offset + length)`. Điều kiện phạm vi mảng phải hợp lệ: `offset >= 0`, `length >= 0` và `offset + length` không vượt quá `src.length`.

Có thể dùng overload này với `FloatBuffer` và `DoubleBuffer` theo cùng cách:

~~~java
float[] floatSource = {1.0f, 2.0f, 3.0f, 4.0f};
FloatBuffer floatTarget = FloatBuffer.allocate(3);
floatTarget.put(floatSource, 1, 2); // Ghi 2.0f, 3.0f

double[] doubleSource = {10.0, 20.0, 30.0, 40.0};
DoubleBuffer doubleTarget = DoubleBuffer.allocate(3);
doubleTarget.put(doubleSource, 0, 3); // Ghi cả ba phần tử đầu
~~~

Nếu offset hoặc length không hợp lệ, phương thức ném `IndexOutOfBoundsException`. Nếu buffer đích không đủ chỗ, phương thức ném `BufferOverflowException`.

## 5. Bulk put từ một typed buffer khác

Có thể chép phần còn lại của một buffer nguồn sang buffer đích cùng kiểu:

~~~java
import java.nio.LongBuffer;

class LongBufferToBuffer {
    public static void main(String[] args) {
        LongBuffer source = LongBuffer.wrap(
            new long[] {11L, 22L, 33L, 44L}
        );

        source.position(1);
        LongBuffer target = LongBuffer.allocate(5);

        target.put(source);

        System.out.println(source.position()); // 4
        System.out.println(source.limit());    // 4
        System.out.println(target.position()); // 3
        System.out.println(target.limit());    // 5
    }
}
~~~

`source.position(1)` đặt vị trí đọc tiếp theo tại phần tử `22`. Vì `source.remaining()` bằng 3, bulk put chuyển các giá trị `22`, `33`, `44`.

Sau khi thành công:

- `source.position()` được đặt đến `source.limit()`.
- `target.position()` tăng thêm số phần tử đã chép.
- `limit` của hai buffer không thay đổi.

Ví dụ với các kiểu còn lại:

~~~java
FloatBuffer floatSource = FloatBuffer.wrap(
    new float[] {1.5f, 2.5f, 3.5f}
);
floatSource.position(1);

FloatBuffer floatTarget = FloatBuffer.allocate(4);
floatTarget.put(floatSource); // Chép 2.5f, 3.5f

DoubleBuffer doubleSource = DoubleBuffer.wrap(
    new double[] {10.0, 20.0, 30.0}
);
doubleSource.position(1);

DoubleBuffer doubleTarget = DoubleBuffer.allocate(4);
doubleTarget.put(doubleSource); // Chép 20.0, 30.0
~~~

Nguồn và đích phải có cùng kiểu buffer. Không thể truyền `DoubleBuffer` trực tiếp vào `FloatBuffer.put(...)` hoặc `LongBuffer.put(...)`.

## 6. Hiểu position, limit và remaining khi bulk put

Bulk put tương đối ghi dữ liệu bắt đầu tại `position` hiện tại của buffer đích. Số phần tử có thể ghi là:

\[
remaining = limit - position
\]

Trước khi ghi `n` phần tử, buffer đích cần thỏa:

\[
n \le limit - position
\]

Ví dụ:

~~~java
LongBuffer buffer = LongBuffer.allocate(8);

buffer.position(2);
buffer.limit(6);

long[] values = {10L, 20L, 30L};

buffer.put(values);
~~~

Buffer có `remaining() = 6 - 2 = 4`, nên có đủ chỗ ghi ba phần tử. Sau thao tác:

- `position` mới là 5.
- `limit` vẫn là 6.
- `remaining()` còn 1.

Nếu buffer chỉ còn hai vị trí mà cần ghi ba phần tử, thao tác thất bại bằng `BufferOverflowException`.

### Capacity không đồng nghĩa với remaining

`capacity` là dung lượng được cấp phát, `limit` là biên hiện tại, còn `position` là vị trí thao tác tiếp theo. Bulk put tương đối dùng `remaining()`, không dùng toàn bộ `capacity` để quyết định có đủ chỗ hay không.

Ví dụ buffer có capacity 10 nhưng position 7 và limit 9 thì chỉ còn 2 phần tử có thể ghi. Việc capacity vẫn bằng 10 không cho phép ghi thêm ba phần tử ở trạng thái hiện tại.

Nếu muốn ghi vào toàn bộ dung lượng đã cấp phát, có thể gọi `clear()` trước khi ghi. `clear()` đặt position về 0 và limit về capacity; nó không xóa nội dung cũ trong bộ nhớ.

## 7. Kết hợp bulk put với flip và đọc dữ liệu

Một quy trình thường gặp là ghi nhiều phần tử, sau đó chuyển buffer sang chế độ đọc bằng `flip()`:

~~~java
import java.nio.FloatBuffer;

class FloatBatch {
    public static void main(String[] args) {
        FloatBuffer buffer = FloatBuffer.allocate(6);

        buffer.put(new float[] {1.0f, 2.0f, 3.0f});
        buffer.put(new float[] {4.0f, 5.0f});

        System.out.println(buffer.position()); // 5

        buffer.flip();

        while (buffer.hasRemaining()) {
            float value = buffer.get();
            System.out.println(value);
        }
    }
}
~~~

Trước `flip()`, buffer đang ở chế độ ghi:

- `position` bằng số phần tử đã ghi.
- `limit` bằng capacity ban đầu (nếu chưa thay đổi).

Sau `flip()`:

- `limit` được đặt bằng position cũ.
- `position` được đặt về 0.
- Các thao tác đọc sẽ đi qua đúng vùng vừa được ghi.

`flip()` không sao chép dữ liệu và không thay đổi các phần tử trong buffer; nó chỉ cập nhật trạng thái.

## 8. Kiểm tra đủ chỗ trước khi bulk put

Có thể chủ động kiểm tra `remaining()` để đưa ra thông báo dễ hiểu trước khi ghi:

~~~java
import java.nio.BufferOverflowException;
import java.nio.LongBuffer;

class CheckedLongPut {
    static void putAll(LongBuffer target, long[] source) {
        if (source.length > target.remaining()) {
            throw new BufferOverflowException();
        }

        target.put(source);
    }
}
~~~

Trong hầu hết trường hợp, không cần tự kiểm tra trước vì `put` đã thực hiện kiểm tra và ném `BufferOverflowException` theo hợp đồng. Kiểm tra tường minh hữu ích khi muốn báo lỗi ở một lớp API riêng hoặc kết hợp nhiều điều kiện nghiệp vụ.

Nếu tự kiểm tra, hãy dùng `remaining()` thay vì `capacity() - position` để giữ đúng trạng thái hiện tại của buffer, kể cả khi `limit` nhỏ hơn capacity.

Với nguồn là buffer khác, số phần tử cần chuyển là `source.remaining()`:

~~~java
if (source.remaining() > target.remaining()) {
    throw new IllegalArgumentException("Target has insufficient remaining space");
}

target.put(source);
~~~

Ví dụ này chủ động chuyển tình huống thiếu chỗ thành `IllegalArgumentException` theo hợp đồng helper. Nếu không có yêu cầu như vậy, có thể để `target.put(source)` tự ném `BufferOverflowException`.

## 9. Buffer chỉ đọc và ReadOnlyBufferException

Một buffer được tạo bằng `asReadOnlyBuffer()` không cho phép ghi. Mọi phương thức `put`, bao gồm bulk put, sẽ ném `ReadOnlyBufferException`.

~~~java
import java.nio.LongBuffer;

class ReadOnlyExample {
    public static void main(String[] args) {
        LongBuffer writable = LongBuffer.allocate(4);
        LongBuffer readOnly = writable.asReadOnlyBuffer();

        // Ném ReadOnlyBufferException.
        readOnly.put(new long[] {1L, 2L});
    }
}
~~~

Kiểm tra `isReadOnly()` khi API cần cung cấp thông báo hoặc quyết định hành vi trước khi ghi:

~~~java
if (target.isReadOnly()) {
    throw new IllegalArgumentException("Target buffer is read-only");
}

target.put(values);
~~~

Ở ví dụ này helper chọn exception riêng cho hợp đồng của nó. Nếu gọi trực tiếp API NIO, exception chuẩn là `ReadOnlyBufferException`.

Không nhầm buffer chỉ đọc với buffer có `remaining() == 0`:

- Read-only: không được phép ghi dù còn chỗ.
- Không còn remaining: được phép ghi theo quyền truy cập nhưng không còn chỗ; bulk put sẽ ném `BufferOverflowException`.

## 10. Các exception cần biết

| Exception | Nguyên nhân thường gặp |
| --- | --- |
| `BufferOverflowException` | Số phần tử cần ghi lớn hơn `target.remaining()`. |
| `ReadOnlyBufferException` | Buffer đích không cho phép ghi. |
| `IndexOutOfBoundsException` | `offset` hoặc `length` của vùng mảng nguồn không hợp lệ. |
| `NullPointerException` | Mảng nguồn hoặc buffer nguồn là null. |
| `IllegalArgumentException` | Với `put(sourceBuffer)`, nguồn và đích là cùng một buffer object. |

Với `put(sourceBuffer)`, không truyền chính buffer đích làm nguồn. Nếu cần đọc từ cùng vùng dữ liệu mà vẫn muốn có trạng thái position độc lập, có thể cân nhắc `duplicate()` hoặc `slice()` theo đúng ý nghĩa vùng dữ liệu; tuy nhiên phải hiểu chúng chia sẻ nội dung với buffer gốc.

Các phương thức bulk put kiểm tra điều kiện trước khi hoàn tất thao tác. Khi gặp lỗi dung lượng hoặc quyền ghi, không nên dựa vào một phần dữ liệu đã được chép; hãy xử lý exception và trạng thái buffer theo hợp đồng API.

## 11. Bảo toàn position của buffer nguồn

`put(sourceBuffer)` cập nhật position của nguồn đến limit sau khi copy. Nếu cần giữ nguyên position của nguồn, dùng một view có trạng thái độc lập:

~~~java
LongBuffer source = LongBuffer.wrap(new long[] {10L, 20L, 30L});
source.position(1);

LongBuffer sourceView = source.duplicate();
LongBuffer target = LongBuffer.allocate(4);

target.put(sourceView);

System.out.println(source.position());     // 1
System.out.println(sourceView.position()); // 3
System.out.println(target.position());     // 2
~~~

`duplicate()` chia sẻ nội dung với buffer ban đầu nhưng có position, limit và mark riêng. Việc copy làm thay đổi position của `sourceView`, không thay đổi position của `source`.

Cần lưu ý rằng `duplicate()` không tạo bản sao dữ liệu. Nếu một bên ghi vào vùng nhớ được chia sẻ, bên kia cũng quan sát được thay đổi nội dung theo vùng tương ứng.

Nếu cần snapshot độc lập, hãy copy dữ liệu vào buffer hoặc mảng khác; không coi `duplicate()` là deep copy.

## 12. Ví dụ tổng hợp cho ba loại typed buffer

Ví dụ dưới đây minh họa bulk put từ mảng, từ buffer nguồn và cách đọc lại:

~~~java
import java.nio.DoubleBuffer;
import java.nio.FloatBuffer;
import java.nio.LongBuffer;

public class TypedBufferBulkPut {
    public static void main(String[] args) {
        LongBuffer longs = LongBuffer.allocate(5);
        longs.put(new long[] {10L, 20L});
        longs.put(new long[] {30L, 40L, 50L}, 1, 2);
        longs.flip();

        FloatBuffer floats = FloatBuffer.allocate(4);
        FloatBuffer floatSource = FloatBuffer.wrap(
            new float[] {1.5f, 2.5f, 3.5f}
        );
        floatSource.position(1);
        floats.put(floatSource);
        floats.flip();

        DoubleBuffer doubles = DoubleBuffer.allocate(4);
        doubles.put(new double[] {0.25, 0.5, 0.75});
        doubles.flip();

        while (longs.hasRemaining()) {
            System.out.println("long: " + longs.get());
        }

        while (floats.hasRemaining()) {
            System.out.println("float: " + floats.get());
        }

        while (doubles.hasRemaining()) {
            System.out.println("double: " + doubles.get());
        }
    }
}
~~~

Phân tích:

- `LongBuffer` ghi hai phần tử đầu, sau đó ghi hai phần tử từ mảng bắt đầu tại offset 1.
- `FloatBuffer` nhận phần còn lại của `floatSource`, vì nguồn đã đặt position tại 1.
- `DoubleBuffer` nhận toàn bộ mảng `double`.
- Mỗi buffer gọi `flip()` trước khi đọc lại.
- Kiểu primitive của nguồn và đích luôn tương ứng.

## 13. Lỗi thường gặp và cách khắc phục

1. **Nhầm `put(array, offset, length)` với `put(array, from, to)`:** tham số thứ ba là số phần tử, không phải cận trên.
2. **Dùng `capacity()` để tính chỗ trống hiện tại:** bulk put tương đối dựa trên `remaining() = limit - position`.
3. **Quên position tăng sau khi ghi:** sau bulk put, position đích tiến lên số phần tử đã chép.
4. **Quên position nguồn thay đổi khi dùng `put(sourceBuffer)`:** nguồn được tiêu thụ đến limit; dùng `duplicate()` nếu cần giữ position ban đầu.
5. **Ghi quá nhiều phần tử:** kiểm tra số lượng so với remaining hoặc xử lý `BufferOverflowException`.
6. **Ghi vào read-only buffer:** kiểm tra `isReadOnly()` nếu cần hoặc xử lý `ReadOnlyBufferException`.
7. **Truyền buffer khác kiểu primitive:** dùng đúng cặp `LongBuffer`/`long[]`, `FloatBuffer`/`float[]`, `DoubleBuffer`/`double[]`.
8. **Dùng chính buffer đích làm nguồn:** `put(sourceBuffer)` không cho phép source là cùng object với destination.
9. **Cho rằng `duplicate()` tạo bản sao dữ liệu:** nó chỉ tạo view với trạng thái độc lập; nội dung vẫn được chia sẻ.
10. **Quên flip trước khi đọc dữ liệu vừa ghi:** sau khi ghi, position đang ở cuối vùng vừa ghi; gọi `flip()` để chuyển sang chế độ đọc.

## 14. Bài tập thực hành

1. Tạo `LongBuffer` có capacity 8, ghi một mảng 5 phần tử bằng `put(array)`. Ghi lại position, limit và remaining.
2. Dùng `put(array, offset, length)` để chép ba phần tử giữa của một mảng `long[]`.
3. Tạo `FloatBuffer` nguồn, thay đổi position của nguồn rồi dùng `put(sourceBuffer)`. Quan sát position của cả hai buffer sau copy.
4. Làm lại bài trên với `DoubleBuffer`.
5. Thử ghi nhiều phần tử hơn `target.remaining()` và quan sát `BufferOverflowException`.
6. Tạo read-only buffer rồi gọi bulk put. Quan sát `ReadOnlyBufferException`.
7. Dùng `duplicate()` để copy dữ liệu nhưng giữ nguyên position của buffer nguồn.
8. Giải thích vì sao `put(array, offset, length)` không làm thay đổi mảng nguồn.
9. Viết helper kiểm tra đủ chỗ bằng `remaining()` trước khi gọi bulk put.
10. Giải thích vì sao `FloatBuffer` không nhận trực tiếp một `double[]` hoặc `DoubleBuffer`.

## Ghi nhớ

`LongBuffer`, `FloatBuffer` và `DoubleBuffer` hỗ trợ bulk put từ mảng primitive cùng kiểu hoặc từ một buffer nguồn cùng kiểu. `put(array)` chép toàn bộ mảng; `put(array, offset, length)` chép một đoạn; `put(sourceBuffer)` chép phần còn lại từ position đến limit của nguồn. Với bulk put tương đối, position của đích tăng theo số phần tử ghi; khi nguồn là buffer, position nguồn cũng tiến đến limit sau khi copy thành công. Dung lượng có thể ghi được xác định bởi `remaining()`, không phải chỉ capacity. Buffer đích read-only gây `ReadOnlyBufferException`, thiếu chỗ gây `BufferOverflowException`, và vùng mảng sai gây `IndexOutOfBoundsException`. Dùng `duplicate()` khi cần position độc lập mà vẫn chia sẻ nội dung; dùng bản copy riêng nếu cần dữ liệu độc lập. Đây là API NIO ổn định và tiếp tục áp dụng trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [Java API – LongBuffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/LongBuffer.html)
- [Java API – FloatBuffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/FloatBuffer.html)
- [Java API – DoubleBuffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/DoubleBuffer.html)
- [Java API – Buffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/Buffer.html)
- [Java API – BufferOverflowException](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/BufferOverflowException.html)
- [Java API – ReadOnlyBufferException](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ReadOnlyBufferException.html)
