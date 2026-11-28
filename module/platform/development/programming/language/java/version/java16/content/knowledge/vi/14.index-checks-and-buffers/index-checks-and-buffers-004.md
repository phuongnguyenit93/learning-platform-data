# Đầu vào âm, độ dài bằng không và biên cuối hợp lệ

## 1. Vì sao cần hiểu rõ các trường hợp biên?

Khi truy cập mảng, buffer, tệp hoặc một vùng dữ liệu logic, lỗi thường xuất hiện ở các giá trị sát biên: chỉ số âm, độ dài bằng không, vị trí đúng bằng độ dài hoặc phần tử cuối cùng. Những trường hợp này cần được phân biệt rõ để tránh lỗi off-by-one và truy cập ngoài phạm vi.

Java cung cấp các phương thức kiểm tra trong `java.util.Objects` như `checkIndex`, `checkFromToIndex` và `checkFromIndexSize`. Từ Java 16, các phương thức này có overload nhận `long`, hữu ích cho offset tệp và cấu trúc dữ liệu có miền chỉ số logic lớn.

~~~java
import java.util.Objects;

long length = 5;
long lastIndex = Objects.checkIndex(4, length); // Hợp lệ
~~~

Với `length = 5`, các chỉ số phần tử hợp lệ là `0` đến `4`. Chỉ số `5` đã nằm ngoài vùng, dù nó chính là giá trị độ dài.

Mục tiêu bài học:

- Nhận diện đầu vào âm và hiểu vì sao chúng không hợp lệ.
- Phân biệt độ dài bằng không với một vùng có phần tử.
- Xác định phần tử cuối cùng hợp lệ khi độ dài dương.
- Phân biệt index của phần tử với cận trên độc quyền của một range.
- Kiểm tra đầu vào trước khi truy cập hoặc thu hẹp kiểu.
- Viết kiểm tra biên rõ ràng cho API nhận dữ liệu từ bên ngoài.

## 2. Quy tắc cơ bản của một chỉ số

Một chỉ số phần tử hợp lệ phải thỏa mãn:

\[
0 \le index < length
\]

Hai điều kiện quan trọng:

- Chỉ số không được âm.
- Chỉ số phải nhỏ hơn độ dài.

`Objects.checkIndex(index, length)` thực hiện kiểm tra này và trả lại chính `index` nếu hợp lệ. Nếu không hợp lệ, nó ném `IndexOutOfBoundsException`.

~~~java
import java.util.Objects;

class IndexExample {
    static long checkedIndex(long index, long length) {
        return Objects.checkIndex(index, length);
    }

    public static void main(String[] args) {
        long length = 5;

        System.out.println(checkedIndex(0, length)); // 0
        System.out.println(checkedIndex(4, length)); // 4
    }
}
~~~

Với `length = 5`:

| Index | Kết quả | Lý do |
| ---: | --- | --- |
| -1 | Không hợp lệ | Chỉ số âm. |
| 0 | Hợp lệ | Phần tử đầu tiên. |
| 1 | Hợp lệ | Nằm trong phạm vi. |
| 4 | Hợp lệ | Phần tử cuối cùng. |
| 5 | Không hợp lệ | Bằng length, nằm ngoài phạm vi. |

Đừng dùng điều kiện `index <= length` để kiểm tra một phần tử. Điều kiện đúng là `index < length`.

## 3. Đầu vào âm: index, fromIndex và size

Các phương thức kiểm tra range có các tham số với ý nghĩa khác nhau. Mỗi giá trị đều phải phù hợp với miền hợp lệ của nó.

### Index âm

~~~java
Objects.checkIndex(-1, 5);
~~~

Lệnh này ném `IndexOutOfBoundsException` vì không tồn tại phần tử có index âm trong một vùng bắt đầu từ 0.

### fromIndex âm

~~~java
Objects.checkFromToIndex(-1, 3, 5);
Objects.checkFromIndexSize(-1, 4, 5);
~~~

Cả hai đều không hợp lệ vì vị trí bắt đầu âm.

### Size âm

~~~java
Objects.checkFromIndexSize(2, -1, 5);
~~~

`size` là số lượng phần tử, nên không thể âm. Kích thước bằng 0 có nghĩa là không xử lý phần tử nào; kích thước âm không biểu diễn một vùng dữ liệu hợp lệ.

### ToIndex nhỏ hơn fromIndex

~~~java
Objects.checkFromToIndex(4, 3, 5);
~~~

Cận trên không thể nằm trước cận dưới. Range dùng quy ước nửa mở `[fromIndex, toIndex)`, nên điều kiện phải là `fromIndex <= toIndex`.

Không nên tự chuyển giá trị âm thành 0 hoặc bỏ qua chúng nếu nghiệp vụ yêu cầu từ chối đầu vào sai. Hãy quyết định rõ tại biên API: từ chối bằng exception, trả về kết quả lỗi hoặc chuẩn hóa theo một quy tắc nghiệp vụ được công bố.

## 4. Độ dài âm phải được từ chối ở biên dữ liệu

`length` biểu diễn số lượng phần tử hoặc kích thước logic của vùng. Một độ dài âm không mô tả được vùng dữ liệu hợp lệ.

Khi `length` lấy trực tiếp từ `array.length`, `ByteBuffer.capacity()` hoặc `FileChannel.size()`, API nguồn đã cung cấp giá trị độ dài theo hợp đồng của nó. Nhưng nếu `length` là tham số do caller gửi vào, hãy xác thực nó như một invariant riêng.

Ví dụ:

~~~java
import java.util.Objects;

class RangeChecks {
    static long checkedStart(long from, long size, long length) {
        if (length < 0) {
            throw new IllegalArgumentException("length must be non-negative");
        }

        return Objects.checkFromIndexSize(from, size, length);
    }
}
~~~

Ở đây:

- `length < 0` là dữ liệu miền không hợp lệ, nên helper từ chối bằng `IllegalArgumentException`.
- Các lỗi về `from` hoặc `size` được API range check báo bằng `IndexOutOfBoundsException`.
- Việc kiểm tra `length` trước cũng làm rõ invariant và tránh dựa vào phép tính range với một độ dài không có ý nghĩa.

Không nên xem `length` âm như một vùng rỗng. Vùng rỗng có độ dài đúng bằng 0; độ dài âm là đầu vào sai.

## 5. Độ dài bằng không: không có index phần tử hợp lệ

Nếu `length = 0`, điều kiện `0 <= index < 0` không thể đúng với bất kỳ index nào.

Vì vậy, cả index 0 cũng không hợp lệ:

~~~java
Objects.checkIndex(0, 0); // Ném IndexOutOfBoundsException
~~~

Điều này thường gặp với:

- Mảng rỗng.
- Buffer có giới hạn hiện tại bằng 0.
- Tệp rỗng.
- Kết quả truy vấn không có phần tử.
- Một đoạn dữ liệu không chứa byte nào.

Ví dụ với mảng rỗng:

~~~java
byte[] data = new byte[0];

System.out.println(data.length); // 0
Objects.checkIndex(0, data.length); // Không hợp lệ
~~~

Không có phần tử đầu tiên khi độ dài bằng 0. Đừng cố truy cập `data[0]` hoặc tính một index cuối cùng cho vùng rỗng.

### Độ dài bằng không vẫn có thể có range rỗng hợp lệ

Kiểm tra một phần tử và kiểm tra một range là hai thao tác khác nhau. Range rỗng `[0, 0)` hợp lệ:

~~~java
long start1 = Objects.checkFromToIndex(0, 0, 0);
long start2 = Objects.checkFromIndexSize(0, 0, 0);

System.out.println(start1); // 0
System.out.println(start2); // 0
~~~

Không có phần tử nào được chọn, nhưng vị trí bắt đầu và kết thúc đều nằm đúng tại biên của vùng rỗng.

Ngược lại, range yêu cầu một phần tử không hợp lệ:

~~~java
Objects.checkFromIndexSize(0, 1, 0); // Ném IndexOutOfBoundsException
~~~

Quy tắc dễ nhớ:

- `length = 0`: không có index phần tử hợp lệ.
- `[0, 0)`: range rỗng hợp lệ.
- `[0, 1)`: không hợp lệ vì yêu cầu một phần tử trong vùng không có phần tử.

## 6. Phần tử cuối cùng hợp lệ

Khi `length > 0`, index cuối cùng hợp lệ là:

\[
lastIndex = length - 1
\]

Ví dụ với `length = 5`:

~~~java
long length = 5;
long lastIndex = length - 1;

long checked = Objects.checkIndex(lastIndex, length);
System.out.println(checked); // 4
~~~

Bảng đối chiếu:

| length | Index hợp lệ | Index cuối cùng |
| ---: | --- | ---: |
| 1 | 0 | 0 |
| 2 | 0, 1 | 1 |
| 5 | 0, 1, 2, 3, 4 | 4 |
| 10 | 0 đến 9 | 9 |

Điều kiện để tính `length - 1` là `length > 0`. Nếu length bằng 0, kết quả -1 không phải một index hợp lệ; không có phần tử cuối cùng.

### Kiểm tra phần tử cuối cùng bằng checkIndex

~~~java
static long lastValidIndex(long length) {
    if (length <= 0) {
        throw new IllegalArgumentException(
            "length must be positive to have a last element"
        );
    }

    return Objects.checkIndex(length - 1, length);
}
~~~

Helper này thể hiện rõ hai bước:

1. Đảm bảo vùng có ít nhất một phần tử.
2. Kiểm tra index cuối cùng theo quy tắc chuẩn của JDK.

Nếu length đến từ một array hoặc buffer, có thể dùng trực tiếp độ dài của cấu trúc đó. Với một abstraction có độ dài logic kiểu long, vẫn cần bảo đảm cách truy cập thực tế hỗ trợ miền chỉ số tương ứng.

## 7. Phân biệt index cuối với cận trên của range

Một nguồn gây lỗi off-by-one là nhầm index cuối cùng với cận trên độc quyền.

Với `length = 5`:

- Index cuối cùng là `4`.
- Cận trên của toàn bộ range là `5`.
- Range toàn bộ dữ liệu là `[0, 5)`.

~~~java
long length = 5;

long lastIndex = Objects.checkIndex(length - 1, length);
long rangeStart = Objects.checkFromToIndex(0, length, length);
long rangeEndExclusive = length;

System.out.println(lastIndex);        // 4
System.out.println(rangeStart);       // 0
System.out.println(rangeEndExclusive); // 5
~~~

`checkFromToIndex` trả về `fromIndex`, không trả về `toIndex`. Trong ví dụ, `rangeEndExclusive` được giữ riêng bằng `length`.

Range `[0, 5)` bao gồm các index 0, 1, 2, 3 và 4. Cận trên 5 được phép bằng length vì nó không được dùng làm index phần tử.

### Range một phần tử cuối cùng

Có thể biểu diễn riêng phần tử cuối bằng range `[length - 1, length)` khi length dương:

~~~java
long length = 5;
long from = Objects.checkFromToIndex(length - 1, length, length);
long count = length - from;

System.out.println(from);  // 4
System.out.println(count); // 1
~~~

Với `length = 0`, không thể dùng `length - 1` để mô tả một phần tử cuối. Hãy xử lý trường hợp rỗng trước khi tính.

## 8. Biên cuối với giá trị long lớn

Các overload nhận `long` hữu ích khi độ dài logic lớn hơn miền `int`. Quy tắc biên vẫn giữ nguyên:

\[
0 \le index < length
\]

Ví dụ:

~~~java
long length = Long.MAX_VALUE;
long lastIndex = length - 1;

long checked = Objects.checkIndex(lastIndex, length);
System.out.println(checked == Long.MAX_VALUE - 1); // true
~~~

`Long.MAX_VALUE` không phải index hợp lệ khi `length` cũng bằng `Long.MAX_VALUE`, vì điều kiện yêu cầu index nhỏ hơn length. Index cuối cùng là `Long.MAX_VALUE - 1`.

Với độ dài lớn, đừng ép index về `int` trước khi kiểm tra. Nếu cấu trúc đích chỉ hỗ trợ index int, hãy xác thực theo độ dài thật của cấu trúc đó rồi mới chuyển kiểu:

~~~java
static byte get(byte[] data, long requestedIndex) {
    long checked = Objects.checkIndex(
        requestedIndex,
        (long) data.length
    );

    return data[Math.toIntExact(checked)];
}
~~~

Mảng Java vẫn dùng index kiểu int. Overload long chỉ giúp xác thực đầu vào long trước khi chuyển sang miền index mà array hỗ trợ.

## 9. Ví dụ kiểm tra các trường hợp âm, rỗng và biên cuối

Có thể gom các trường hợp quan trọng thành một chương trình nhỏ:

~~~java
import java.util.Objects;

public class BoundaryChecks {
    static void expectOutOfBounds(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " should fail");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println(label + ": rejected");
        }
    }

    public static void main(String[] args) {
        long length = 5;

        // Biên đầu và phần tử cuối hợp lệ.
        System.out.println(Objects.checkIndex(0, length)); // 0
        System.out.println(Objects.checkIndex(4, length)); // 4

        // Index âm và index bằng length không hợp lệ.
        expectOutOfBounds("negative index",
            () -> Objects.checkIndex(-1, length));
        expectOutOfBounds("index at length",
            () -> Objects.checkIndex(length, length));

        // Không có phần tử khi length bằng 0.
        expectOutOfBounds("empty data index",
            () -> Objects.checkIndex(0, 0));

        // Nhưng range rỗng ở vị trí 0 hợp lệ.
        System.out.println(
            Objects.checkFromIndexSize(0, 0, 0)
        );

        // Một phần tử cuối cùng được mô tả bằng [4, 5).
        System.out.println(
            Objects.checkFromToIndex(4, 5, 5)
        );
    }
}
~~~

Helper `expectOutOfBounds` chỉ minh họa cách xác nhận exception trong ví dụ. Trong ứng dụng, hãy xử lý exception ở ranh giới phù hợp với hợp đồng API thay vì bắt rồi bỏ qua mọi lỗi.

## 10. Kiểm tra trước khi truy cập array hoặc buffer

Với array, có thể nhận một index kiểu long từ input, xác thực theo độ dài thật của array, rồi chuyển sang int:

~~~java
import java.util.Objects;

class SafeArrayAccess {
    static int get(int[] values, long index) {
        Objects.requireNonNull(values, "values");

        long checkedIndex =
            Objects.checkIndex(index, (long) values.length);

        return values[Math.toIntExact(checkedIndex)];
    }
}
~~~

Với `ByteBuffer`, position, limit và capacity đều được quản lý bằng int. Với thao tác truy cập tuyệt đối như `get(index)` hoặc `put(index, value)`, index phải nằm trước limit. Với thao tác tương đối, vị trí hiện tại phải còn nhỏ hơn limit; số phần tử còn lại được biểu diễn bởi `remaining()`. Capacity là giới hạn dung lượng được cấp phát và limit không thể vượt capacity. Không dùng overload long để giả định buffer có thể truy cập vượt giới hạn int.

Cũng cần phân biệt:

- `capacity` là dung lượng được cấp phát.
- `limit` là biên hiện tại của vùng có thể đọc hoặc ghi theo thao tác tương ứng.
- `position` là vị trí hiện tại của buffer.

Chọn đúng giới hạn phụ thuộc thao tác. Một index nhỏ hơn capacity nhưng lớn hơn limit vẫn không hợp lệ cho thao tác truy cập tuyệt đối; thao tác tương đối lại dựa trên position và remaining, không nhận index từ caller.

## 11. Bảng tổng hợp các trường hợp biên

| Trường hợp | Kiểm tra | Kết quả |
| --- | --- | --- |
| Index âm | `checkIndex(-1, 5)` | Không hợp lệ. |
| Index 0 với length dương | `checkIndex(0, 5)` | Hợp lệ. |
| Index cuối | `checkIndex(4, 5)` | Hợp lệ. |
| Index bằng length | `checkIndex(5, 5)` | Không hợp lệ. |
| Index bất kỳ với length 0 | `checkIndex(0, 0)` | Không hợp lệ. |
| Range rỗng tại đầu | `checkFromToIndex(0, 0, 0)` | Hợp lệ. |
| Range rỗng tại cuối | `checkFromToIndex(5, 5, 5)` | Hợp lệ. |
| Một phần tử cuối | `checkFromToIndex(4, 5, 5)` | Hợp lệ. |
| Size âm | `checkFromIndexSize(0, -1, 5)` | Không hợp lệ. |
| From âm | `checkFromIndexSize(-1, 1, 5)` | Không hợp lệ. |
| Length âm từ caller | Guard length trước khi kiểm tra | Từ chối đầu vào miền. |

## 12. Lỗi thường gặp và cách khắc phục

1. **Dùng `index <= length`:** phần tử cuối là `length - 1`; dùng điều kiện `index < length`.
2. **Coi index 0 hợp lệ khi length bằng 0:** không có phần tử nào trong vùng rỗng.
3. **Tính `length - 1` mà không kiểm tra length:** chỉ tính index cuối khi `length > 0`.
4. **Nhầm cận trên range với index cuối:** range `[0, length)` có cận trên bằng length, nhưng phần tử cuối là `length - 1`.
5. **Coi range rỗng là lỗi:** `[0, 0)` và `[length, length)` hợp lệ nếu các mốc nằm trong biên.
6. **Bỏ qua index hoặc size âm:** từ chối dữ liệu sai tại biên API; không tự ép về 0 nếu nghiệp vụ không yêu cầu.
7. **Không kiểm tra length do caller truyền:** xác thực length không âm trước khi dùng nó làm kích thước logic.
8. **Ép long về int trước khi kiểm tra:** có thể làm thay đổi giá trị; kiểm tra long trước rồi dùng `Math.toIntExact`.
9. **Dùng capacity thay cho limit trong mọi thao tác ByteBuffer:** xác định biên phù hợp với thao tác đọc hoặc ghi hiện tại.
10. **Dựa vào exception message:** dựa vào loại exception và điều kiện API, không phân tích chuỗi message.

## 13. Bài tập thực hành

1. Với `length = 5`, liệt kê tất cả index hợp lệ và index đầu tiên không hợp lệ ở phía trên.
2. Giải thích vì sao `checkIndex(0, 0)` ném exception nhưng `checkFromIndexSize(0, 0, 0)` hợp lệ.
3. Viết method `lastIndex(long length)` chỉ trả index cuối khi length dương; từ chối length bằng 0 hoặc âm.
4. Viết helper nhận `long length` từ caller và từ chối độ dài âm bằng `IllegalArgumentException`.
5. Kiểm tra các trường hợp `fromIndex = -1`, `size = -1`, `fromIndex = length`, `size = 0` bằng `checkFromIndexSize`.
6. Biểu diễn phần tử cuối của một vùng bằng `checkFromToIndex(length - 1, length, length)`. Xử lý riêng khi length bằng 0.
7. Dùng `Long.MAX_VALUE` làm length và xác định index cuối hợp lệ.
8. Viết method nhận `byte[]` cùng index long; kiểm tra trước khi chuyển sang int và truy cập phần tử.
9. Giải thích sự khác nhau giữa capacity, limit và position khi kiểm tra vùng truy cập của `ByteBuffer`.

## Ghi nhớ

Một index phần tử hợp lệ phải thỏa `0 <= index < length`. Vì vậy, index âm và index bằng length đều không hợp lệ. Khi length bằng 0, không có phần tử nào có thể truy cập, nhưng range rỗng `[0, 0)` vẫn hợp lệ vì nó không yêu cầu phần tử. Khi length dương, index cuối cùng là `length - 1`; chỉ tính giá trị này sau khi đã xác nhận length lớn hơn 0. Đừng nhầm index cuối với cận trên độc quyền: toàn bộ vùng có range `[0, length)`. Với dữ liệu do caller cung cấp, hãy từ chối length âm như một đầu vào miền không hợp lệ, kiểm tra range bằng Objects và chỉ thu hẹp long về int sau khi xác thực. Các quy tắc biên này áp dụng cho cả overload int và long trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [Java API – Objects.checkIndex](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkIndex(long,long))
- [Java API – Objects.checkFromToIndex](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkFromToIndex(long,long,long))
- [Java API – Objects.checkFromIndexSize](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkFromIndexSize(long,long,long))
- [Java API – ByteBuffer](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java API – Math.toIntExact](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/lang/Math.html#toIntExact(long))
