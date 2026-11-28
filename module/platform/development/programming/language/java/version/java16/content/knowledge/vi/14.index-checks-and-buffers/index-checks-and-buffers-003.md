# Objects.checkFromIndexSize với long và kiểm tra tràn phép cộng

## 1. Vì sao cần kiểm tra phạm vi theo vị trí và kích thước?

Một thao tác xử lý dữ liệu thường được mô tả bằng vị trí bắt đầu và số lượng phần tử cần đọc hoặc ghi. Ví dụ, đọc 512 byte bắt đầu tại offset 2.000.000.000 trong một tệp. Khi đó ta có:

- `fromIndex`: vị trí bắt đầu.
- `size`: số phần tử hoặc số byte cần xử lý.
- `length`: tổng độ dài hợp lệ của vùng dữ liệu.

Java cung cấp `Objects.checkFromIndexSize(long, long, long)` để kiểm tra ba giá trị này trong miền `long`. Overload nhận `long` có từ Java 16 và vẫn hữu ích với offset tệp hoặc cấu trúc dữ liệu có chỉ số logic lớn.

~~~java
import java.util.Objects;

long fileSize = 8_000_000_000L;
long position = 5_000_000_000L;
long requestedBytes = 4_096L;

long checkedPosition =
    Objects.checkFromIndexSize(position, requestedBytes, fileSize);
~~~

Nếu phạm vi hợp lệ, phương thức trả về `fromIndex`. Nếu vị trí, kích thước hoặc độ dài không hợp lệ, nó ném `IndexOutOfBoundsException`.

Điểm quan trọng là kiểm tra phạm vi mà không phải tự tính `fromIndex + size` trước khi xác thực. Phép cộng số nguyên `long` có thể overflow và tạo ra kết quả âm hoặc một giá trị nhỏ hơn thực tế. Dùng API kiểm tra phạm vi giúp tránh lỗi này.

Mục tiêu bài học:

- Hiểu điều kiện hợp lệ của `checkFromIndexSize(long, long, long)`.
- Phân biệt vị trí bắt đầu với số lượng phần tử.
- Hiểu vì sao phép cộng `fromIndex + size` có thể overflow.
- Kiểm tra range an toàn trước khi tính cận trên.
- Dùng `Math.addExact` khi thật sự cần tính end offset.
- Áp dụng cho array, `ByteBuffer`, `FileChannel` và abstraction có offset kiểu `long`.

## 2. Cú pháp và điều kiện hợp lệ

Chữ ký overload long:

~~~java
long Objects.checkFromIndexSize(
    long fromIndex,
    long size,
    long length
)
~~~

Phạm vi được mô tả là `[fromIndex, fromIndex + size)`. Điều kiện hợp lệ tương đương:

\[
0 \le fromIndex \le length
\]

\[
0 \le size \le length - fromIndex
\]

Trong đó:

- `fromIndex` là vị trí bắt đầu và được bao gồm.
- `size` là số phần tử cần xử lý, không phải chỉ số cuối.
- `length` là độ dài vùng dữ liệu.
- Cận trên là vị trí ngay sau phần tử cuối, không được bao gồm.
- Giá trị trả về là `fromIndex` nếu phạm vi hợp lệ.

Ví dụ:

~~~java
long start = Objects.checkFromIndexSize(3L, 4L, 10L);
long endExclusive = start + 4L;
~~~

Phạm vi được kiểm tra là `[3, 7)`, bao gồm các vị trí 3, 4, 5 và 6. Số phần tử là 4.

Các điều kiện không hợp lệ gồm:

- `fromIndex < 0`.
- `size < 0`.
- `length < 0`.
- `fromIndex > length`.
- `size > length - fromIndex`.

Nếu một trong các điều kiện trên xảy ra, phương thức ném `IndexOutOfBoundsException`. Không dựa vào chuỗi message cụ thể của exception để điều khiển nghiệp vụ.

## 3. Phân biệt size với chỉ số cuối

`size` biểu diễn số lượng phần tử cần xử lý. Nó không phải index cuối cùng và cũng không phải cận trên.

Giả sử:

~~~java
long fromIndex = 3;
long size = 4;
long length = 10;
~~~

Phạm vi tương ứng là `[3, 7)`:

| Vị trí | Có thuộc phạm vi? |
| ---: | --- |
| 2 | Không |
| 3 | Có |
| 4 | Có |
| 5 | Có |
| 6 | Có |
| 7 | Không |

Có thể tính cận trên sau khi xác thực:

~~~java
long checkedFrom = Objects.checkFromIndexSize(fromIndex, size, length);
long endExclusive = checkedFrom + size;
~~~

Vì phạm vi đã hợp lệ nên `checkedFrom + size` không vượt `length`. Nếu cần thể hiện rõ phép cộng phải kiểm tra overflow, dùng `Math.addExact`:

~~~java
long endExclusive = Math.addExact(checkedFrom, size);
~~~

Không nhầm ba cách biểu diễn:

| Dữ liệu đầu vào | API phù hợp |
| --- | --- |
| Một phần tử tại index | `Objects.checkIndex(index, length)` |
| Hai mốc bắt đầu và kết thúc | `Objects.checkFromToIndex(from, to, length)` |
| Vị trí bắt đầu và số lượng | `Objects.checkFromIndexSize(from, size, length)` |

Chọn API dựa trên dạng dữ liệu đang có sẽ giúp tránh tự chuyển đổi range không cần thiết.

## 4. Khoảng rỗng và các trường hợp biên

`size = 0` biểu diễn một phạm vi rỗng. Phạm vi rỗng hợp lệ nếu `fromIndex` nằm trong khoảng từ 0 đến `length`, kể cả vị trí ngay sau phần tử cuối.

~~~java
long start = Objects.checkFromIndexSize(10L, 0L, 10L);

System.out.println(start); // 10
~~~

Đây là phạm vi `[10, 10)`. Nó không chứa phần tử nào, nhưng là một vị trí bắt đầu hợp lệ cho thao tác không xử lý dữ liệu.

Bảng trường hợp biên với `length = 10`:

| fromIndex | size | Kết quả | Giải thích |
| ---: | ---: | --- | --- |
| 0 | 10 | Hợp lệ | Bao phủ toàn bộ vùng. |
| 3 | 4 | Hợp lệ | Bao phủ vị trí 3 đến 6. |
| 9 | 1 | Hợp lệ | Chỉ bao phủ phần tử cuối. |
| 10 | 0 | Hợp lệ | Khoảng rỗng ở cuối. |
| 0 | 0 | Hợp lệ | Khoảng rỗng ở đầu. |
| 10 | 1 | Không hợp lệ | Không còn phần tử tại vị trí 10. |
| 11 | 0 | Không hợp lệ | Vị trí bắt đầu đã vượt length. |
| -1 | 1 | Không hợp lệ | Vị trí bắt đầu âm. |
| 3 | -1 | Không hợp lệ | Kích thước âm. |
| 0 | 11 | Không hợp lệ | Kích thước vượt độ dài. |

Khoảng rỗng không có nghĩa mọi vị trí bất kỳ đều hợp lệ. `fromIndex` vẫn phải nằm trong `[0, length]`.

## 5. Vì sao fromIndex + size có thể overflow?

Kiểu `long` có giá trị lớn nhất là `Long.MAX_VALUE`. Phép cộng số nguyên trong Java không tự ném exception khi kết quả vượt giới hạn; nó giữ lại các bit thấp và có thể tạo ra một giá trị âm.

Ví dụ:

~~~java
long length = Long.MAX_VALUE;
long fromIndex = Long.MAX_VALUE - 4;
long size = 10;

long endExclusive = fromIndex + size;

System.out.println(endExclusive); // Giá trị bị overflow, trở thành số âm.
System.out.println(endExclusive <= length); // true, dù phạm vi vượt giới hạn.
~~~

Phạm vi bắt đầu chỉ còn cách cận trên hợp lệ 4 đơn vị, nhưng yêu cầu xử lý 10 đơn vị. Range thực tế không hợp lệ vì nó vượt quá `length`.

Điều kiện tự viết sau đây không an toàn:

~~~java
if (fromIndex + size <= length) {
    // Có thể chấp nhận nhầm một phạm vi đã overflow.
}
~~~

Trong ví dụ, phép cộng bị overflow thành số âm. Giá trị âm vẫn nhỏ hơn `length`, khiến điều kiện có thể trả về `true` dù yêu cầu vượt giới hạn.

Đây là lỗi logic nghiêm trọng vì phép kiểm tra có vẻ hợp lệ nhưng đã mất thông tin về giá trị toán học ban đầu.

## 6. Dùng checkFromIndexSize thay cho phép cộng trước kiểm tra

Hãy truyền trực tiếp vị trí, kích thước và độ dài vào API:

~~~java
import java.util.Objects;

class RangeValidator {
    static long validate(
            long fromIndex,
            long size,
            long length
    ) {
        return Objects.checkFromIndexSize(fromIndex, size, length);
    }
}
~~~

Kiểm tra trường hợp gây overflow ở phần trước:

~~~java
long length = Long.MAX_VALUE;
long fromIndex = Long.MAX_VALUE - 4;
long size = 10;

long checked = Objects.checkFromIndexSize(fromIndex, size, length);
~~~

Lệnh trên ném `IndexOutOfBoundsException` vì không thể chứa đủ 10 phần tử từ vị trí bắt đầu đã cho trong vùng có độ dài `Long.MAX_VALUE`.

Về mặt logic, sau khi xác nhận `length` và `fromIndex` không âm, có thể kiểm tra bằng phép trừ:

~~~java
static boolean isRangeValid(
        long fromIndex,
        long size,
        long length
) {
    return fromIndex >= 0
        && size >= 0
        && length >= 0
        && fromIndex <= length
        && size <= length - fromIndex;
}
~~~

Phép trừ `length - fromIndex` chỉ được thực hiện sau khi các giá trị không âm và `fromIndex <= length` đã được xác nhận. Khi đó phép trừ không overflow.

Trong code ứng dụng, nên ưu tiên `Objects.checkFromIndexSize` để dùng chung quy tắc chuẩn của JDK và nhận exception nhất quán. Hàm boolean trên chỉ minh họa cách viết điều kiện an toàn khi thật sự cần kết quả đúng/sai.

## 7. Khi nào dùng Math.addExact?

Sau khi range đã được xác thực, đôi khi ứng dụng cần biết cận trên độc quyền để truyền cho một API khác hoặc lưu metadata.

Có thể dùng:

~~~java
long checkedFrom =
    Objects.checkFromIndexSize(fromIndex, size, length);

long endExclusive = Math.addExact(checkedFrom, size);
~~~

`Math.addExact` trả về tổng nếu phép cộng không overflow; nếu overflow, nó ném `ArithmeticException`.

Trong trường hợp này, range đã hợp lệ nên tổng không thể vượt `length` và không thể lớn hơn `Long.MAX_VALUE`. Dùng `addExact` làm rõ ý định tính toán an toàn, đồng thời bảo vệ nếu logic xung quanh thay đổi về sau.

Không dùng `Math.addExact(fromIndex, size)` như một phép thay thế hoàn toàn cho range validation. Phép cộng không overflow vẫn có thể tạo ra một cận trên lớn hơn `length`:

~~~java
long length = 100;
long fromIndex = 90;
long size = 20;

long endExclusive = Math.addExact(fromIndex, size); // 110, không overflow.
~~~

Tổng 110 vẫn nằm ngoài vùng có độ dài 100. Vì vậy, cần kiểm tra cả tính hợp lệ của range, không chỉ kiểm tra overflow.

Quy trình phù hợp:

1. Kiểm tra `fromIndex`, `size` và `length` bằng `checkFromIndexSize`.
2. Chỉ sau khi hợp lệ mới tính cận trên nếu cần.
3. Dùng `Math.addExact` khi muốn biểu đạt rõ phép cộng có kiểm soát overflow.

## 8. Kiểm tra range trước khi ép long về int

Một số API nhận index và size kiểu `int`, trong khi dữ liệu đầu vào của ứng dụng có thể là `long`. Hãy kiểm tra trong miền long trước, sau đó mới chuyển kiểu.

Ví dụ với mảng byte:

~~~java
import java.util.Arrays;
import java.util.Objects;

class ByteArraySlices {
    static byte[] copyRange(
            byte[] data,
            long fromIndex,
            long size
    ) {
        long checkedFrom = Objects.checkFromIndexSize(
            fromIndex,
            size,
            (long) data.length
        );

        int start = Math.toIntExact(checkedFrom);
        int end = Math.toIntExact(Math.addExact(checkedFrom, size));

        return Arrays.copyOfRange(data, start, end);
    }
}
~~~

Phân tích:

- `data.length` được chuyển sang `long` để gọi overload tương ứng.
- `checkFromIndexSize` xác nhận toàn bộ vùng nằm trong mảng.
- Chỉ sau khi xác thực mới chuyển cận dưới và cận trên về `int`.
- `Math.toIntExact` ném `ArithmeticException` nếu giá trị không thể biểu diễn bằng `int`.
- Vì range nằm trong mảng nên các vị trí hợp lệ có thể chuyển về miền index của mảng.

Không ép `fromIndex` hoặc `size` về `int` trước khi kiểm tra. Việc thu hẹp sớm có thể làm mất bit cao và biến một đầu vào lớn thành một giá trị nhỏ có vẻ hợp lệ.

Ví dụ này không mở rộng giới hạn mảng Java. Nó chỉ xử lý đầu vào kiểu `long` một cách an toàn trước khi gọi API array dùng `int`.

## 9. Ứng dụng với offset tệp và FileChannel

`FileChannel` dùng vị trí tệp kiểu `long`. Khi đọc một vùng có vị trí bắt đầu và số byte yêu cầu, có thể kiểm tra bằng `checkFromIndexSize`:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.util.Objects;

class FileRangeReader {
    static int readOnce(
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

Ở đây:

1. `channel.size()` trả về độ dài tệp kiểu `long`.
2. `target.remaining()` cho biết số byte còn có thể ghi vào buffer; giá trị này có kiểu `int`.
3. Chuyển số byte cần đọc sang `long` để kiểm tra cùng offset và kích thước tệp.
4. `checkFromIndexSize` xác thực toàn bộ range dự kiến.
5. `channel.read(target, checkedPosition)` nhận offset kiểu `long`.

Tên `readOnce` nhấn mạnh rằng một lần gọi `FileChannel.read` có thể đọc ít byte hơn số lượng yêu cầu. Nếu ứng dụng cần đọc đủ, phải lặp và xử lý partial read, EOF và lỗi I/O.

Việc kiểm tra cũng không khóa tệp. Nếu một tiến trình khác thay đổi kích thước tệp sau khi kiểm tra, thao tác đọc có thể cho kết quả khác với dự kiến. Range validation là bước kiểm tra đầu vào, không phải cơ chế đồng bộ file.

`ByteBuffer` vẫn có capacity, position và limit kiểu `int`. Overload long chỉ phù hợp với offset tệp và range logic; nó không biến buffer thành vùng nhớ có kích thước long.

## 10. So sánh ba phương thức kiểm tra

| Phương thức | Dữ liệu đầu vào | Dùng khi |
| --- | --- | --- |
| `Objects.checkIndex(index, length)` | Một index | Kiểm tra một phần tử. |
| `Objects.checkFromToIndex(from, to, length)` | Hai đầu mút | Đã biết cận dưới và cận trên độc quyền. |
| `Objects.checkFromIndexSize(from, size, length)` | Vị trí bắt đầu và số lượng | Đã biết điểm bắt đầu và số phần tử cần xử lý. |

Ví dụ hai cách biểu diễn cùng một vùng:

~~~java
long from = 4;
long to = 9;
long size = 5;
long length = 20;

Objects.checkFromToIndex(from, to, length);
Objects.checkFromIndexSize(from, size, length);
~~~

Cả hai cùng kiểm tra vùng `[4, 9)`. Khác biệt là dạng đầu vào: một bên nhận `to`, bên còn lại nhận `size`.

Nếu chỉ có `from` và `size`, đừng tự tính `to = from + size` trước khi kiểm tra. Hãy gọi `checkFromIndexSize` trực tiếp.

## 11. Lỗi thường gặp và cách khắc phục

1. **Dùng `fromIndex + size <= length` trước khi kiểm tra:** phép cộng có thể overflow. Dùng `Objects.checkFromIndexSize`.
2. **Nhầm size với index cuối:** size là số lượng phần tử; range là `[fromIndex, fromIndex + size)`.
3. **Quên kiểm tra size âm:** size phải lớn hơn hoặc bằng 0.
4. **Cho rằng fromIndex bằng length luôn không hợp lệ:** nó hợp lệ khi size bằng 0, tạo khoảng rỗng ở cuối.
5. **Cho rằng `Math.addExact` thay thế range validation:** phép cộng không overflow vẫn có thể vượt length.
6. **Ép long về int trước khi xác thực:** có thể làm mất bit cao. Kiểm tra trong miền long trước rồi mới dùng `Math.toIntExact`.
7. **Cho rằng overload long làm array hoặc `ByteBuffer` lớn hơn:** API kiểm tra chỉ xác thực range số học; cấu trúc đích vẫn có giới hạn riêng.
8. **Cho rằng range hợp lệ đảm bảo I/O đọc đủ:** vẫn cần xử lý partial read, EOF và lỗi I/O.
9. **Tự viết phép kiểm tra subtraction khi chưa xác thực đầu vào:** chỉ tính `length - fromIndex` sau khi bảo đảm các giá trị không âm và `fromIndex <= length`.
10. **Phụ thuộc vào exception message:** chỉ dựa vào loại exception và hợp đồng API.

## 12. Bài tập thực hành

1. Viết method nhận `long fromIndex`, `long size`, `long length`; dùng `Objects.checkFromIndexSize` và trả về vị trí bắt đầu đã xác thực.
2. Với `length = 100`, xác định các cặp `(fromIndex, size)` hợp lệ: `(0, 100)`, `(90, 10)`, `(100, 0)`, `(100, 1)`, `(101, 0)`, `(-1, 1)`.
3. Dùng `Long.MAX_VALUE` để tạo ví dụ mà `fromIndex + size` overflow. Giải thích vì sao điều kiện `fromIndex + size <= length` có thể chấp nhận sai.
4. Viết hàm boolean kiểm tra range bằng điều kiện `size <= length - fromIndex`, bảo đảm kiểm tra các giá trị không âm trước phép trừ.
5. Sau khi range hợp lệ, tính `endExclusive` bằng `Math.addExact`.
6. Viết method nhận `byte[]` cùng hai tham số `long`; kiểm tra trước khi chuyển sang `int` để sao chép một đoạn.
7. Viết method đọc một đoạn tệp bằng `FileChannel`, dùng `channel.size()` và `checkFromIndexSize`.
8. Giải thích vì sao `Math.addExact` phát hiện overflow nhưng không tự phát hiện range vượt `length`.

## Ghi nhớ

`Objects.checkFromIndexSize(long, long, long)` được bổ sung trong Java 16 để kiểm tra một vùng dữ liệu bằng vị trí bắt đầu, số lượng phần tử và độ dài kiểu `long`. Điều kiện hợp lệ là `fromIndex` và `size` không âm, `fromIndex` không vượt `length`, đồng thời `size` không vượt `length - fromIndex`. Phương thức trả về `fromIndex` nếu hợp lệ và ném `IndexOutOfBoundsException` nếu không hợp lệ. Tránh tự cộng `fromIndex + size` trước khi xác thực vì phép cộng `long` có thể overflow và làm điều kiện kiểm tra sai. Khi cần cận trên, hãy kiểm tra range trước rồi mới tính; `Math.addExact` hữu ích để biểu đạt phép cộng có kiểm soát nhưng không thay thế range validation. Với API chỉ nhận `int`, hãy xác thực trong miền `long` trước rồi mới thu hẹp bằng `Math.toIntExact`. Đây là API ổn định, tiếp tục hữu ích khi làm việc với offset tệp và dữ liệu lớn, trong khi array và `ByteBuffer` vẫn giữ giới hạn riêng.

**Tài liệu tham khảo chính thức:**

- [Java 16 API – Objects.checkFromIndexSize(long, long, long)](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkFromIndexSize(long,long,long))
- [Java 16 API – Objects.checkFromToIndex(long, long, long)](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkFromToIndex(long,long,long))
- [Java 16 API – Objects.checkIndex(long, long)](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkIndex(long,long))
- [Java API – Math.addExact](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/lang/Math.html#addExact(long,long))
- [Java API – FileChannel](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/FileChannel.html)
