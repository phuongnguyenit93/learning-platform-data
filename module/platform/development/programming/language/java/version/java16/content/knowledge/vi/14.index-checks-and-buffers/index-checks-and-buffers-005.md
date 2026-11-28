# Giá trị trả về của phép kiểm tra và IndexOutOfBoundsException

## 1. Phép kiểm tra trả về điều gì?

Các phương thức kiểm tra chỉ số trong `java.util.Objects` vừa xác thực phạm vi, vừa trả lại một giá trị đã được kiểm tra để caller có thể dùng tiếp. Điểm này giúp code ngắn gọn và tránh lặp lại cùng một biểu thức kiểm tra.

Ba phương thức thường dùng có ý nghĩa trả về như sau:

| Phương thức | Giá trị trả về khi hợp lệ | Exception khi không hợp lệ |
| --- | --- | --- |
| `Objects.checkIndex(index, length)` | Chính `index` | `IndexOutOfBoundsException` |
| `Objects.checkFromToIndex(from, to, length)` | Chính `from` | `IndexOutOfBoundsException` |
| `Objects.checkFromIndexSize(from, size, length)` | Chính `from` | `IndexOutOfBoundsException` |

Các overload nhận `long` được bổ sung trong Java 16; các overload nhận `int` cũng có cùng ý nghĩa trả về và cùng loại exception.

Điều quan trọng là phương thức không trả về `length`, `toIndex`, `size` hoặc cận trên của range. Nó trả lại chỉ số đơn hoặc cận dưới đã xác thực. Caller vẫn giữ các giá trị khác nếu cần dùng tiếp.

Ví dụ:

~~~java
import java.util.Objects;

long checkedIndex = Objects.checkIndex(requestedIndex, dataLength);
long checkedFrom = Objects.checkFromToIndex(from, to, dataLength);
long checkedStart = Objects.checkFromIndexSize(from, size, dataLength);
~~~

Nếu một lời gọi hoàn tất bình thường, giá trị trả về đã thỏa mãn điều kiện biên tương ứng. Nếu không, phương thức ném exception và không trả về giá trị để tiếp tục.

Mục tiêu bài học:

- Hiểu chính xác giá trị trả về của ba phương thức kiểm tra.
- Phân biệt index, điểm bắt đầu, kích thước và cận trên.
- Dùng giá trị trả về trực tiếp khi truy cập hoặc xử lý dữ liệu.
- Hiểu `IndexOutOfBoundsException` và thời điểm nó được ném.
- Phân biệt lỗi phạm vi với lỗi null hoặc dữ liệu nghiệp vụ không hợp lệ.
- Xử lý exception ở ranh giới API phù hợp và tránh phụ thuộc exception message.

## 2. Giá trị trả về của checkIndex

`Objects.checkIndex(index, length)` kiểm tra một phần tử. Điều kiện hợp lệ là:

\[
0 \le index < length
\]

Khi hợp lệ, phương thức trả lại đúng giá trị `index` đã truyền vào:

~~~java
int index = Objects.checkIndex(requestedIndex, values.length);
String value = values[index];
~~~

Ví dụ với kiểu `long`:

~~~java
long index = Objects.checkIndex(requestedIndex, logicalLength);
~~~

Không có phép chuyển đổi hoặc chuẩn hóa index. Nếu đầu vào là 4 và hợp lệ, kết quả cũng là 4.

### Dùng trực tiếp trong biểu thức

Vì phương thức trả về index, có thể đặt nó ngay tại nơi cần chỉ số:

~~~java
String value = values[Objects.checkIndex(index, values.length)];
~~~

Cách viết này phù hợp khi biểu thức ngắn và dễ đọc. Nếu cần dùng chỉ số ở nhiều nơi, nên lưu kết quả vào biến `checkedIndex` để thể hiện rõ rằng bước xác thực đã hoàn tất.

Với mảng, overload `int` trả về `int`, phù hợp trực tiếp với cú pháp truy cập mảng. Overload `long` trả về `long`; nếu sau đó truy cập mảng, phải bảo đảm giá trị nằm trong miền index của mảng rồi mới thu hẹp về `int`.

~~~java
long checked = Objects.checkIndex(requestedIndex, (long) values.length);
String value = values[Math.toIntExact(checked)];
~~~

Trong ví dụ, việc kiểm tra theo độ dài thật của mảng chứng minh index không âm và nhỏ hơn `values.length`; `Math.toIntExact` thực hiện phép thu hẹp có kiểm tra.

## 3. Giá trị trả về của checkFromToIndex

`Objects.checkFromToIndex(fromIndex, toIndex, length)` xác thực một khoảng nửa mở:

\[
0 \le fromIndex \le toIndex \le length
\]

Khi hợp lệ, phương thức trả lại `fromIndex`, tức cận dưới đã kiểm tra.

~~~java
long checkedFrom =
    Objects.checkFromToIndex(from, to, dataLength);

long count = to - checkedFrom;
~~~

Giá trị trả về không phải `to` và cũng không phải `to - from`. Nếu cần cận trên, giữ biến `to`; nếu cần số phần tử, tính `to - checkedFrom` sau khi range đã được xác thực.

Ví dụ xử lý một đoạn:

~~~java
import java.util.Objects;

class RangeReader {
    static void process(byte[] data, int from, int to) {
        int start = Objects.checkFromToIndex(from, to, data.length);

        for (int i = start; i < to; i++) {
            System.out.println(data[i]);
        }
    }
}
~~~

Vòng lặp bắt đầu tại giá trị đã kiểm tra và dừng trước `to`, giữ đúng semantics `[from, to)`.

### Khoảng rỗng vẫn trả về fromIndex

Nếu `fromIndex == toIndex` và hai mốc nằm trong giới hạn, range rỗng hợp lệ:

~~~java
long start = Objects.checkFromToIndex(8L, 8L, 10L);
System.out.println(start); // 8
~~~

Phương thức vẫn trả về cận dưới `8`. Nó không trả về `0` để biểu diễn số phần tử, vì số phần tử của range rỗng là `0`.

Một trường hợp quan trọng là range rỗng ở cuối:

~~~java
long end = Objects.checkFromToIndex(length, length, length);
~~~

Kết quả là `length`. Giá trị này hợp lệ với vai trò cận dưới của một range rỗng, nhưng không phải index hợp lệ để truy cập phần tử.

## 4. Giá trị trả về của checkFromIndexSize

`Objects.checkFromIndexSize(fromIndex, size, length)` kiểm tra một vùng được mô tả bằng vị trí bắt đầu và số lượng phần tử.

Điều kiện hợp lệ:

\[
0 \le fromIndex \le length
\]

\[
0 \le size \le length - fromIndex
\]

Khi hợp lệ, phương thức trả lại `fromIndex`, không trả về `size` hoặc `fromIndex + size`.

~~~java
long checkedStart =
    Objects.checkFromIndexSize(from, size, dataLength);

long endExclusive = checkedStart + size;
~~~

Sau khi kiểm tra thành công, `checkedStart + size` nằm trong giới hạn `length`. Nếu cần biểu đạt phép cộng có kiểm tra overflow một cách tường minh, có thể dùng `Math.addExact` sau khi range đã hợp lệ:

~~~java
long endExclusive = Math.addExact(checkedStart, size);
~~~

### Ví dụ dùng giá trị trả về để cắt một đoạn mảng

~~~java
import java.util.Arrays;
import java.util.Objects;

class ByteSlices {
    static byte[] copy(byte[] source, int from, int size) {
        int checkedFrom =
            Objects.checkFromIndexSize(from, size, source.length);

        int endExclusive = checkedFrom + size;
        return Arrays.copyOfRange(source, checkedFrom, endExclusive);
    }
}
~~~

`checkedFrom` là vị trí bắt đầu đã xác thực. `size` vẫn là số phần tử caller yêu cầu. Cận trên được tính sau khi kiểm tra thành công.

Không nhầm kết quả trả về với số phần tử đã kiểm tra. Nếu cần số phần tử, dùng `size`; nếu cần cận trên, tính từ vị trí bắt đầu và size sau khi xác thực.

## 5. Vì sao các phương thức ném IndexOutOfBoundsException?

Nếu index hoặc range không thỏa điều kiện của phương thức, `Objects` ném `IndexOutOfBoundsException`.

Ví dụ:

~~~java
Objects.checkIndex(-1, 5);              // Index âm.
Objects.checkIndex(5, 5);               // Index bằng length.
Objects.checkFromToIndex(4, 3, 5);      // to nhỏ hơn from.
Objects.checkFromIndexSize(2, -1, 5);  // size âm.
Objects.checkFromIndexSize(4, 2, 5);   // Range vượt length.
~~~

Khi một lời gọi ném exception:

- Phương thức không trả về giá trị.
- Các câu lệnh sau lời gọi trong cùng luồng thực thi không tiếp tục, trừ khi exception được bắt ở nơi phù hợp.
- Caller có thể để exception truyền lên, bắt exception để chuyển thành kết quả lỗi, hoặc chuyển đổi sang exception thuộc hợp đồng API của mình.
- Không nên tiếp tục truy cập dữ liệu bằng giá trị đầu vào chưa được xác thực.

`IndexOutOfBoundsException` là unchecked exception, thuộc nhóm `RuntimeException`. Caller không bắt buộc phải khai báo `throws` hoặc bắt exception khi gọi các phương thức này.

### Exception được ném ngay tại bước kiểm tra

~~~java
int checked = Objects.checkIndex(index, values.length);
use(values[checked]);
~~~

Nếu index không hợp lệ, dòng đầu tiên ném exception và dòng `use(...)` không được thực thi. Đây là lợi ích của việc đặt kiểm tra ngay trước thao tác cần chỉ số.

## 6. Phân biệt lỗi phạm vi với lỗi đầu vào khác

Không phải mọi dữ liệu không hợp lệ đều là lỗi index. Mỗi loại vấn đề có thể cần loại exception khác nhau.

| Tình huống | Cách kiểm tra thường dùng | Loại exception thường gặp |
| --- | --- | --- |
| Index âm hoặc vượt giới hạn | `Objects.checkIndex` | `IndexOutOfBoundsException` |
| Range nằm ngoài vùng | `Objects.checkFromToIndex` hoặc `checkFromIndexSize` | `IndexOutOfBoundsException` |
| Tham chiếu object bắt buộc nhưng là null | `Objects.requireNonNull` | `NullPointerException` |
| Đối số vi phạm quy tắc nghiệp vụ | Kiểm tra theo hợp đồng method | Thường là `IllegalArgumentException` |
| Không tìm thấy tài nguyên | API tìm kiếm hoặc lớp nghiệp vụ | Có thể là `NoSuchElementException` hoặc exception riêng |

Ví dụ:

~~~java
import java.util.Objects;

static byte read(byte[] data, long index) {
    Objects.requireNonNull(data, "data");

    long checked = Objects.checkIndex(index, (long) data.length);
    return data[Math.toIntExact(checked)];
}
~~~

Nếu `data` là null, `requireNonNull` ném `NullPointerException` trước khi kiểm tra index. Nếu `data` tồn tại nhưng index không hợp lệ, `checkIndex` ném `IndexOutOfBoundsException`.

Không dùng `IndexOutOfBoundsException` để báo mọi lỗi đầu vào. Hãy chọn exception thể hiện đúng loại vi phạm để caller có thể hiểu và xử lý phù hợp.

## 7. Xử lý exception ở đúng ranh giới

Các phương thức kiểm tra được thiết kế để báo lỗi phạm vi ngay tại nơi xác thực. Có thể để exception truyền lên nếu method hiện tại không có trách nhiệm chuyển đổi lỗi.

Ví dụ method nội bộ:

~~~java
static byte getByte(byte[] data, int index) {
    int checked = Objects.checkIndex(index, data.length);
    return data[checked];
}
~~~

Method không cần bắt rồi ném lại cùng exception:

~~~java
static byte getByte(byte[] data, int index) {
    try {
        int checked = Objects.checkIndex(index, data.length);
        return data[checked];
    } catch (IndexOutOfBoundsException ex) {
        throw ex;
    }
}
~~~

Đoạn thứ hai không bổ sung hành vi có ích. Chỉ bắt exception khi có việc thực sự cần làm, chẳng hạn bổ sung ngữ cảnh ở biên API hoặc chuyển thành kiểu lỗi được hợp đồng công khai quy định.

### Chuyển exception ở biên API khi cần

~~~java
class RequestRangeException extends RuntimeException {
    RequestRangeException(String message, Throwable cause) {
        super(message, cause);
    }
}

class PublicRangeApi {
    static byte read(byte[] data, int index) {
        try {
            int checked = Objects.checkIndex(index, data.length);
            return data[checked];
        } catch (IndexOutOfBoundsException ex) {
            throw new RequestRangeException(
                "Requested byte position is outside the data",
                ex
            );
        }
    }
}
~~~

Ví dụ này chỉ phù hợp nếu API muốn công bố một exception riêng. Nếu `IndexOutOfBoundsException` đã đúng với hợp đồng của method, để exception gốc truyền lên thường đơn giản hơn.

Không nên bắt `RuntimeException` quá rộng chỉ để biến mọi lỗi thành một thông báo chung; điều đó có thể che giấu bug hoặc lỗi không liên quan đến phạm vi.

## 8. Không phụ thuộc vào exception message

Không dùng nội dung message để xác định chính xác tham số nào sai:

~~~java
try {
    Objects.checkIndex(index, length);
} catch (IndexOutOfBoundsException ex) {
    // Không nên phân tích ex.getMessage() để quyết định nghiệp vụ.
}
~~~

Thông điệp có thể khác giữa các phiên bản JDK hoặc cách triển khai. Hợp đồng ổn định cần dựa vào:

- Loại exception.
- Điều kiện hợp lệ được mô tả trong API.
- Giá trị đầu vào mà ứng dụng đang quản lý.

Nếu giao diện cần hiển thị lỗi thân thiện, hãy tự tạo message từ dữ liệu đã có ở lớp ứng dụng:

~~~java
static int checkedUserIndex(int index, int length) {
    try {
        return Objects.checkIndex(index, length);
    } catch (IndexOutOfBoundsException ex) {
        throw new IllegalArgumentException(
            "Index " + index + " is outside a collection of size " + length,
            ex
        );
    }
}
~~~

Chỉ chuyển sang `IllegalArgumentException` nếu hợp đồng method muốn coi đây là đối số caller truyền vào không hợp lệ. Nếu method được thiết kế như một phép truy cập collection, `IndexOutOfBoundsException` có thể là lựa chọn tự nhiên hơn.

## 9. Dùng kết quả kiểm tra để viết code ít lặp hơn

Giá trị trả về cho phép xác thực và sử dụng chỉ số trong một biểu thức:

~~~java
byte value = data[Objects.checkIndex(index, data.length)];
~~~

Hoặc lưu vào biến để dùng nhiều lần:

~~~java
int checkedIndex = Objects.checkIndex(index, data.length);

byte value = data[checkedIndex];
logAccess(checkedIndex);
~~~

Với range:

~~~java
int checkedFrom = Objects.checkFromToIndex(from, to, data.length);

for (int i = checkedFrom; i < to; i++) {
    consume(data[i]);
}
~~~

Với vị trí và kích thước:

~~~java
int checkedFrom = Objects.checkFromIndexSize(from, size, data.length);
int checkedTo = checkedFrom + size;

consumeRange(data, checkedFrom, checkedTo);
~~~

Cách viết này giúp thể hiện rõ điểm bắt đầu đã qua kiểm tra. Không cần viết lại cùng điều kiện ở nhiều nơi.

Tuy nhiên, không gọi check nhiều lần trong vòng lặp nếu độ dài và chỉ số không thay đổi. Kiểm tra một lần trước khi bắt đầu thao tác thường rõ ràng và hiệu quả hơn.

## 10. Lưu ý khi dùng overload int và long

Các overload nhận `int` trả về `int`; overload nhận `long` trả về `long`. Loại giá trị trả về phù hợp với overload được chọn.

~~~java
int checkedInt = Objects.checkIndex(indexInt, lengthInt);

long checkedLong = Objects.checkIndex(indexLong, lengthLong);
~~~

Java chọn overload dựa trên kiểu đối số. Không nên dựa vào việc một hằng số số nguyên có thể được chuyển đổi trong một số ngữ cảnh để đoán overload; hãy dùng kiểu biến rõ ràng khi cần kiểm soát miền chỉ số.

Khi API đích chỉ nhận `int`, kiểm tra bằng độ dài thật của cấu trúc đích rồi mới chuyển kiểu:

~~~java
long checked = Objects.checkIndex(requestedIndex, (long) array.length);
int arrayIndex = Math.toIntExact(checked);
byte value = array[arrayIndex];
~~~

Overload `long` hữu ích để xác thực đầu vào có miền lớn. Nó không mở rộng giới hạn index của array hoặc `ByteBuffer`.

## 11. Bảng tổng hợp cách dùng và kết quả

| Phương thức | Điều kiện | Giá trị trả về | Lỗi phạm vi |
| --- | --- | --- | --- |
| `checkIndex(index, length)` | `0 <= index < length` | `index` | `IndexOutOfBoundsException` |
| `checkFromToIndex(from, to, length)` | `0 <= from <= to <= length` | `from` | `IndexOutOfBoundsException` |
| `checkFromIndexSize(from, size, length)` | `0 <= from <= length` và `0 <= size <= length - from` | `from` | `IndexOutOfBoundsException` |

Các điểm cần nhớ:

- Giá trị trả về là giá trị đầu vào đã xác thực, không phải độ dài.
- `checkFromToIndex` và `checkFromIndexSize` trả về điểm bắt đầu, không phải cận trên.
- Range rỗng có thể hợp lệ và vẫn trả về `from`.
- Nếu không hợp lệ, exception được ném thay vì trả về một giá trị sentinel.
- Các phương thức không kiểm tra null cho object dữ liệu và không xác thực quy tắc nghiệp vụ ngoài phạm vi.

## 12. Bài tập thực hành

1. Viết method dùng `Objects.checkIndex` rồi trả lại index đã xác thực. Giải thích giá trị trả về có khác index đầu vào hay không.
2. Gọi `checkFromToIndex(3, 7, 10)` và xác định giá trị trả về, số phần tử và cận trên.
3. Gọi `checkFromIndexSize(3, 4, 10)` và giải thích vì sao phương thức trả về 3 chứ không phải 4 hoặc 7.
4. Viết đoạn code dùng trực tiếp giá trị trả về của `checkIndex` để truy cập một mảng.
5. Thử một index âm và quan sát `IndexOutOfBoundsException`. Giải thích vì sao câu lệnh truy cập sau bước kiểm tra không chạy.
6. So sánh lỗi `data == null` với lỗi index vượt giới hạn. Dùng `requireNonNull` và `checkIndex` cho đúng mục đích.
7. Viết một API công khai chuyển `IndexOutOfBoundsException` thành exception nghiệp vụ riêng, giữ exception gốc làm cause.
8. Giải thích vì sao không nên phân tích `getMessage()` của exception.
9. Viết ví dụ dùng overload long, sau đó chuyển sang int an toàn cho một array.
10. Với mỗi phương thức, ghi lại kiểu dữ liệu trả về khi gọi overload int và overload long.

## Ghi nhớ

`Objects.checkIndex` trả về chính index đã kiểm tra; `checkFromToIndex` và `checkFromIndexSize` trả về chính `fromIndex`. Chúng không trả về length, size hoặc cận trên của range. Khi đầu vào không hợp lệ, các phương thức ném `IndexOutOfBoundsException` và không trả về giá trị để caller tiếp tục. Dùng giá trị trả về trực tiếp hoặc lưu vào biến `checkedIndex`/`checkedFrom` để thể hiện rằng kiểm tra đã thành công. Phân biệt lỗi phạm vi với tham chiếu null và lỗi nghiệp vụ; dùng `requireNonNull` hoặc exception miền phù hợp cho các trường hợp đó. Chỉ bắt exception khi cần chuyển đổi lỗi tại ranh giới API hoặc bổ sung ngữ cảnh; không bắt rồi ném lại cùng exception và không phụ thuộc vào message cụ thể. Đây là semantics ổn định của API `Objects` trong Java hiện đại, bao gồm các overload long được bổ sung từ Java 16.

**Tài liệu tham khảo chính thức:**

- [Java API – Objects.checkIndex](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkIndex(long,long))
- [Java API – Objects.checkFromToIndex](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkFromToIndex(long,long,long))
- [Java API – Objects.checkFromIndexSize](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkFromIndexSize(long,long,long))
- [Java API – IndexOutOfBoundsException](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/lang/IndexOutOfBoundsException.html)
- [Java API – Objects.requireNonNull](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String))
