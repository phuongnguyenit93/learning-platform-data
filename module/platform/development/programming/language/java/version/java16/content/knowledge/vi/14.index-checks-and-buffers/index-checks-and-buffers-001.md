# Objects.checkIndex với long cho chỉ số vượt miền int

## 1. Vì sao cần kiểm tra chỉ số kiểu long?

Java có hai nhóm overload của các phương thức kiểm tra chỉ số trong `java.util.Objects`: nhóm nhận `int` và nhóm nhận `long`. Các overload nhận `long` được bổ sung từ Java 16, giúp xác thực chỉ số và phạm vi trong những cấu trúc dữ liệu có không gian địa chỉ logic lớn hơn miền của `int`.

Ví dụ, một tệp có thể có kích thước và vị trí đọc được biểu diễn bằng `long`. Một kho dữ liệu phân đoạn cũng có thể dùng một chỉ số logic `long`, dù mỗi mảng thành phần vẫn được truy cập bằng `int`.

~~~java
import java.util.Objects;

long fileSize = 5_000_000_000L;
long position = 4_000_000_000L;

long checked = Objects.checkIndex(position, fileSize);
~~~

`Objects.checkIndex(long, long)` xác thực rằng chỉ số không âm và nhỏ hơn độ dài. Nếu hợp lệ, phương thức trả về chính chỉ số đó; nếu không hợp lệ, nó ném `IndexOutOfBoundsException`.

Điểm cần phân biệt: overload `long` cho phép kiểm tra một không gian chỉ số lớn, nhưng không biến mảng Java hoặc `ByteBuffer` thành cấu trúc có thể truy cập bằng chỉ số `long`. Mảng Java vẫn có giới hạn độ dài và chỉ số kiểu `int`; các cấu trúc lớn cần API hoặc cách lưu trữ hỗ trợ offset `long`, chẳng hạn tệp, dữ liệu phân đoạn hoặc một abstraction riêng.

Mục tiêu bài học:

- Hiểu overload `Objects.checkIndex(long, long)` từ Java 16.
- Phân biệt kiểm tra một chỉ số với kiểm tra một phạm vi.
- Dùng `checkFromToIndex` và `checkFromIndexSize` cho range.
- Tránh ép `long` về `int` trước khi xác thực.
- Áp dụng kiểm tra long index cho offset của tệp và cấu trúc dữ liệu lớn.
- Hiểu giới hạn của kiểm tra chỉ số và các tình huống cần xử lý overflow.

## 2. Các overload nhận long trong Objects

Java 16 cung cấp ba phương thức kiểm tra chính với tham số `long`:

~~~java
Objects.checkIndex(long index, long length)

Objects.checkFromToIndex(
    long fromIndex,
    long toIndex,
    long length
)

Objects.checkFromIndexSize(
    long fromIndex,
    long size,
    long length
)
~~~

Cả ba phương thức đều trả về `long` nếu điều kiện hợp lệ. Chúng ném `IndexOutOfBoundsException` nếu chỉ số hoặc phạm vi nằm ngoài giới hạn.

| Phương thức | Điều kiện hợp lệ | Giá trị trả về |
| --- | --- | --- |
| `checkIndex(index, length)` | `0 <= index < length` | `index` |
| `checkFromToIndex(from, to, length)` | `0 <= from <= to <= length` | `from` |
| `checkFromIndexSize(from, size, length)` | `0 <= from`, `0 <= size` và phạm vi có kích thước `size` nằm trong `length` | `from` |

Hai overload range phù hợp với hai cách mô tả phạm vi thường gặp:

- Dùng `from` và `to` khi đã có điểm bắt đầu và điểm kết thúc, với `to` là cận trên không bao gồm.
- Dùng `from` và `size` khi biết điểm bắt đầu cùng số phần tử cần xử lý.

Các overload `int` tương ứng đã có từ những phiên bản Java trước. Bài này tập trung vào overload `long` được bổ sung trong Java 16.

## 3. Kiểm tra một chỉ số bằng checkIndex

Một chỉ số hợp lệ phải thỏa mãn:

\[
0 \le index < length
\]

Ví dụ:

~~~java
import java.util.Objects;

class IndexDemo {
    static long checkedPosition(long index, long length) {
        return Objects.checkIndex(index, length);
    }

    public static void main(String[] args) {
        long length = 6_000_000_000L;

        long position = checkedPosition(4_500_000_000L, length);
        System.out.println(position); // 4500000000
    }
}
~~~

Phương thức trả lại chỉ số đã kiểm tra, nên có thể dùng trực tiếp trong biểu thức:

~~~java
long position = Objects.checkIndex(requestedPosition, dataLength);
~~~

Nếu `requestedPosition` âm hoặc bằng/vượt `dataLength`, Java ném `IndexOutOfBoundsException`.

### Cận trên không được bao gồm

Với `length = 10`, các chỉ số hợp lệ là từ `0` đến `9`:

| Index | Kết quả |
| ---: | --- |
| `-1` | Không hợp lệ |
| `0` | Hợp lệ |
| `9` | Hợp lệ |
| `10` | Không hợp lệ |

`length` biểu diễn số lượng phần tử, không phải chỉ số cuối cùng. Vì vậy, không dùng điều kiện `index <= length` cho truy cập một phần tử.

Nếu `length` bằng `0`, không tồn tại chỉ số phần tử hợp lệ. Lệnh `Objects.checkIndex(0L, 0L)` sẽ ném `IndexOutOfBoundsException`.

## 4. Kiểm tra phạm vi bằng checkFromToIndex

Khi một thao tác cần xử lý từ vị trí `fromIndex` đến trước `toIndex`, dùng:

~~~java
long start = Objects.checkFromToIndex(fromIndex, toIndex, length);
~~~

Điều kiện là:

\[
0 \le fromIndex \le toIndex \le length
\]

Phạm vi có dạng nửa mở `[fromIndex, toIndex)`: bao gồm vị trí bắt đầu, không bao gồm vị trí kết thúc.

~~~java
import java.util.Objects;

class RangeDemo {
    static long checkedStart(long from, long to, long length) {
        return Objects.checkFromToIndex(from, to, length);
    }

    public static void main(String[] args) {
        long length = 8_000_000_000L;

        long start = checkedStart(
            2_000_000_000L,
            2_000_000_128L,
            length
        );

        System.out.println(start); // 2000000000
    }
}
~~~

Một phạm vi rỗng được phép nếu hai đầu bằng nhau và nằm trong giới hạn:

~~~java
long start = Objects.checkFromToIndex(length, length, length);
~~~

Trường hợp này trả về `length`, biểu diễn một phạm vi rỗng ở cuối dữ liệu. Tuy nhiên, `length` vẫn không phải chỉ số hợp lệ để đọc một phần tử bằng `checkIndex`.

## 5. Kiểm tra phạm vi bằng checkFromIndexSize

Nếu biết vị trí bắt đầu và số lượng phần tử, dùng:

~~~java
long start = Objects.checkFromIndexSize(fromIndex, size, length);
~~~

Điều kiện tương ứng là:

- `fromIndex` không âm.
- `size` không âm.
- Phạm vi bắt đầu tại `fromIndex` và có `size` phần tử phải nằm hoàn toàn trong dữ liệu có độ dài `length`.

Ví dụ:

~~~java
import java.util.Objects;

class SliceDemo {
    static long checkedStart(long from, long size, long length) {
        return Objects.checkFromIndexSize(from, size, length);
    }

    public static void main(String[] args) {
        long fileSize = 9_000_000_000L;

        long start = checkedStart(
            7_000_000_000L,
            512L,
            fileSize
        );

        System.out.println(start); // 7000000000
    }
}
~~~

Phạm vi có `size = 0` được phép nếu `fromIndex` nằm trong khoảng từ `0` đến `length`, kể cả vị trí ngay sau phần tử cuối:

~~~java
long end = Objects.checkFromIndexSize(length, 0L, length);
~~~

Không dùng `checkIndex` để kiểm tra một phạm vi. `checkIndex` yêu cầu một phần tử tồn tại; hai phương thức range còn cho phép phạm vi rỗng tại cuối dữ liệu.

## 6. Vì sao overload long quan trọng với dữ liệu lớn?

Kiểu `int` là số nguyên có dấu 32 bit, nên giá trị lớn nhất là `2_147_483_647`. Kiểu `long` là số nguyên có dấu 64 bit, nên có thể biểu diễn giá trị lớn hơn nhiều.

Một số API và abstraction làm việc với kích thước hoặc vị trí kiểu `long`, ví dụ:

- Kích thước và vị trí trong tệp.
- Offset trong dữ liệu lưu trữ phân đoạn.
- Chỉ số logic trong kho dữ liệu lớn.
- Vị trí trong một luồng dữ liệu được truy cập ngẫu nhiên.
- Một abstraction biểu diễn không gian địa chỉ lớn hơn giới hạn của `int`.

Trước khi dùng overload `long`, cần hiểu giới hạn của cấu trúc dữ liệu thực tế. `long` chỉ mở rộng miền số mà phép kiểm tra có thể xác thực; nó không tự cấp phát một mảng lớn hơn giới hạn của JVM, không làm `ByteBuffer` nhận index `long`, và không làm một API chỉ nhận `int` trở thành API hỗ trợ long index.

## 7. Ví dụ thực tế: kiểm tra offset khi đọc FileChannel

`FileChannel` cung cấp thao tác đọc tại một vị trí tệp được biểu diễn bằng `long`. Có thể kết hợp `channel.size()` với `Objects.checkFromIndexSize` để kiểm tra phạm vi yêu cầu trước khi đọc:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.util.Objects;

class FileReaderSupport {
    static int readOnceAt(
            FileChannel channel,
            long position,
            ByteBuffer target
    ) throws IOException {

        long fileSize = channel.size();

        long checkedPosition = Objects.checkFromIndexSize(
            position,
            (long) target.remaining(),
            fileSize
        );

        return channel.read(target, checkedPosition);
    }
}
~~~

Phân tích:

1. `channel.size()` trả về kích thước tệp dưới dạng `long`.
2. `target.remaining()` trả về số byte còn trống trong `ByteBuffer` dưới dạng `int`; chuyển sang `long` để thể hiện rõ phép kiểm tra trong miền long.
3. `checkFromIndexSize` xác thực toàn bộ vùng đích dự kiến đọc nằm trong kích thước tệp hiện tại.
4. Giá trị trả về là vị trí bắt đầu đã kiểm tra.
5. `channel.read(target, checkedPosition)` dùng vị trí tệp kiểu `long`.

Tên `readOnceAt` nhấn mạnh đây là một lần đọc. `FileChannel.read` có thể đọc ít byte hơn số byte yêu cầu; nếu cần đọc đủ, ứng dụng phải có vòng lặp xử lý partial read và EOF. Việc kiểm tra phạm vi cũng không khóa tệp: nếu một tiến trình khác thay đổi kích thước tệp đồng thời, thao tác I/O vẫn có thể đọc ít hơn dự kiến hoặc gặp tình huống khác với kích thước vừa kiểm tra.

`ByteBuffer` trong ví dụ vẫn có dung lượng và vị trí được quản lý bằng `int`. `long` ở đây dùng cho vị trí trong tệp; nó không làm buffer có khả năng chứa hơn giới hạn của chính buffer.

## 8. Không ép long về int trước khi kiểm tra

Một lỗi nguy hiểm là ép chỉ số `long` sang `int` trước khi xác thực:

~~~java
long requestedIndex = 4_294_967_296L;

// Không an toàn: ép kiểu có thể làm mất các bit cao.
int index = (int) requestedIndex;
Objects.checkIndex(index, array.length);
~~~

`4_294_967_296L` có thể bị thu hẹp thành `0` khi ép sang `int`. Nếu mảng có phần tử tại index `0`, phép kiểm tra sau khi ép kiểu có thể thành công dù chỉ số ban đầu nằm ngoài phạm vi.

Với đầu vào `long` và một mảng, hãy kiểm tra bằng overload `long` trước rồi mới chuyển kiểu:

~~~java
import java.util.Objects;

class ArrayAccess {
    static byte get(byte[] data, long requestedIndex) {
        long checkedIndex =
            Objects.checkIndex(requestedIndex, (long) data.length);

        // Sau kiểm tra, index chắc chắn nằm trong miền index của mảng.
        return data[(int) checkedIndex];
    }
}
~~~

Ở đây, `data.length` không vượt quá miền index của mảng Java. Sau khi `checkIndex` xác nhận `0 <= requestedIndex < data.length`, phép ép về `int` là an toàn.

Ví dụ này chỉ minh họa cách xác thực một đầu vào `long` trước khi truy cập mảng. Nó không cho phép mảng có độ dài vượt giới hạn của Java array.

## 9. Tránh lỗi overflow khi tự kiểm tra range

Không nên tự kiểm tra phạm vi bằng cách cộng trực tiếp:

~~~java
// Không nên dùng cách này cho dữ liệu long:
if (offset + size <= length) {
    // Xử lý range
}
~~~

Nếu `offset + size` vượt `Long.MAX_VALUE`, phép cộng số nguyên có thể overflow và tạo ra giá trị âm hoặc một giá trị nhỏ hơn thực tế. Điều kiện kiểm tra khi đó có thể cho kết quả sai.

Dùng overload được thiết kế cho range:

~~~java
long checkedOffset =
    Objects.checkFromIndexSize(offset, size, length);
~~~

Phương thức này kiểm tra quan hệ giữa vị trí bắt đầu, kích thước và độ dài theo quy tắc của API, tránh việc phải tự viết phép cộng dễ overflow.

Nếu ứng dụng vẫn cần tính vị trí kết thúc sau khi xác thực, có thể dùng phép toán exact:

~~~java
long checkedOffset =
    Objects.checkFromIndexSize(offset, size, length);

long endExclusive = Math.addExact(checkedOffset, size);
~~~

`Math.addExact` ném `ArithmeticException` nếu phép cộng bị overflow. Chỉ dùng khi thật sự cần giá trị kết thúc; nếu chỉ cần xác thực range, kết quả từ `checkFromIndexSize` thường đã đủ.

Cũng cần nhớ rằng `Objects.checkIndex` không thể phát hiện một phép tính đã overflow trước khi truyền vào. Nếu chỉ số được tạo từ phép cộng hoặc nhân, hãy xác thực các toán hạng hoặc dùng các phương thức như `Math.addExact` và `Math.multiplyExact` ở bước tính toán.

## 10. Chọn đúng phương thức cho từng nhu cầu

| Nhu cầu | Phương thức |
| --- | --- |
| Đọc hoặc ghi một phần tử tại index `long` | `Objects.checkIndex(index, length)` |
| Kiểm tra vùng từ `from` đến trước `to` | `Objects.checkFromToIndex(from, to, length)` |
| Kiểm tra vùng bắt đầu tại `from` với `size` phần tử | `Objects.checkFromIndexSize(from, size, length)` |
| Truy cập một mảng bằng đầu vào `long` | Kiểm tra với độ dài mảng trước, sau đó mới thu hẹp về `int` |
| Đọc tại offset của tệp | Kiểm tra range bằng kích thước tệp `long`, sau đó gọi API I/O nhận offset `long` |
| Truy cập `ByteBuffer` | Tôn trọng index/capacity kiểu `int` của buffer; không coi overload long là mở rộng giới hạn buffer |

Một quy tắc dễ nhớ:

- Một phần tử: `checkIndex`.
- Hai đầu mút: `checkFromToIndex`.
- Điểm bắt đầu cộng số lượng: `checkFromIndexSize`.

## 11. Những lỗi thường gặp

1. **Dùng `index <= length`:** chỉ số phần tử phải nhỏ hơn `length`; dùng `checkIndex`.
2. **Dùng `checkIndex` cho range:** nó chỉ kiểm tra một phần tử; dùng `checkFromToIndex` hoặc `checkFromIndexSize`.
3. **Nhầm `toIndex` là phần tử cuối được lấy:** range dùng cận trên không bao gồm, dạng `[from, to)`.
4. **Ép `long` về `int` trước khi kiểm tra:** có thể làm mất bit cao và khiến một chỉ số sai trở thành chỉ số có vẻ hợp lệ.
5. **Cho rằng long overload làm mảng lớn hơn:** mảng Java vẫn có giới hạn index kiểu `int`.
6. **Cho rằng `ByteBuffer` hỗ trợ index long:** buffer vẫn dùng các vị trí và kích thước kiểu `int`.
7. **Tự kiểm tra `offset + size <= length`:** phép cộng có thể overflow; dùng `checkFromIndexSize`.
8. **Cho rằng checkIndex bảo đảm thao tác I/O thành công:** nó chỉ xác thực phạm vi tại thời điểm kiểm tra; thao tác đọc vẫn có thể partial read, EOF hoặc lỗi I/O.
9. **Phụ thuộc vào nội dung thông báo exception:** dựa vào loại exception và điều kiện API, không dựa vào chuỗi message cụ thể.
10. **Quên kiểm tra độ dài âm hoặc dữ liệu đầu vào sai:** các phương thức sẽ từ chối phạm vi không hợp lệ; với invariant nghiệp vụ riêng, vẫn cần xác thực ở lớp phù hợp.

## 12. Bài tập thực hành

1. Viết method nhận `long index` và `long length`, trả về kết quả của `Objects.checkIndex`.
2. Với `length = 10`, liệt kê các giá trị `from` và `to` hợp lệ cho `checkFromToIndex`.
3. So sánh `checkFromToIndex(3, 7, 10)` với `checkFromIndexSize(3, 4, 10)`. Giải thích vì sao hai cách biểu diễn cùng một vùng.
4. Viết method kiểm tra một vùng dữ liệu tệp bằng `checkFromIndexSize(long, long, long)`.
5. Viết method nhận `byte[]` và `long index`; kiểm tra bằng overload long trước khi ép về `int`.
6. Thử truyền `4_294_967_296L` vào method truy cập mảng. So sánh kết quả khi ép về `int` trước với kiểm tra long trước.
7. Giải thích vì sao `offset + size <= length` có thể sai khi số học overflow và thay bằng `checkFromIndexSize`.
8. Giải thích giới hạn còn lại khi dùng `long` cho offset tệp nhưng dùng `ByteBuffer` để lưu dữ liệu đọc.

## Ghi nhớ

Java 16 bổ sung overload nhận `long` cho `Objects.checkIndex`, `checkFromToIndex` và `checkFromIndexSize`. Chúng cho phép kiểm tra chỉ số hoặc phạm vi trong không gian dữ liệu có độ dài kiểu `long`, trả lại vị trí bắt đầu/chỉ số nếu hợp lệ và ném `IndexOutOfBoundsException` nếu không hợp lệ. Dùng `checkIndex` cho một phần tử, `checkFromToIndex` cho hai đầu mút và `checkFromIndexSize` cho vị trí cộng kích thước. Hãy xác thực trước khi thu hẹp `long` về `int`; chỉ ép kiểu sau khi đã chứng minh giá trị nằm trong miền của mảng hoặc API nhận `int`. Overload long hữu ích với offset tệp và cấu trúc dữ liệu lớn, nhưng không mở rộng giới hạn của array hay `ByteBuffer`. Khi kiểm tra vùng, ưu tiên API có sẵn để tránh phép cộng có thể overflow và vẫn xử lý riêng các lỗi I/O hoặc thay đổi dữ liệu đồng thời.

**Tài liệu tham khảo chính thức:**

- [Java 16 API – Objects.checkIndex(long, long)](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkIndex(long,long))
- [Java 16 API – Objects.checkFromToIndex(long, long, long)](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkFromToIndex(long,long,long))
- [Java 16 API – Objects.checkFromIndexSize(long, long, long)](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkFromIndexSize(long,long,long))
- [Java API – FileChannel](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/FileChannel.html)
- [Java API – ByteBuffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html)
