# Kiểm tra chỉ số bằng checkIndex

Từ Java 9, lớp `java.util.Objects` cung cấp các phương thức kiểm tra chỉ số và phạm vi: `checkIndex`, `checkFromToIndex` và `checkFromIndexSize`. Các phương thức này giúp xác thực tham số trước khi truy cập mảng, List, buffer hoặc một vùng dữ liệu.

Chúng trả về chỉ số đầu vào nếu hợp lệ và ném `IndexOutOfBoundsException` nếu phạm vi không hợp lệ. Nhờ vậy, code có thể vừa kiểm tra điều kiện vừa sử dụng trực tiếp giá trị đã kiểm tra.

## 1. Ba phương thức kiểm tra

Các overload với `int` có dạng:

~~~java
int checkIndex(int index, int length)
int checkFromToIndex(int fromIndex, int toIndex, int length)
int checkFromIndexSize(int fromIndex, int size, int length)
~~~

Java 9 cũng cung cấp các overload tương ứng nhận `long` và trả về `long`, phù hợp khi chỉ số hoặc độ dài được biểu diễn bằng kiểu long.

| Phương thức | Điều kiện hợp lệ | Giá trị trả về |
|---|---|---|
| `checkIndex(index, length)` | `0 <= index < length` | `index` |
| `checkFromToIndex(from, to, length)` | `0 <= from <= to <= length` | `from` |
| `checkFromIndexSize(from, size, length)` | `0 <= from`, `0 <= size`, và `from + size <= length` | `from` |

Trong hai phương thức kiểm tra phạm vi, quy ước là khoảng nửa mở `[from, to)`: phần tử ở vị trí `from` được tính, còn vị trí `to` không được tính. Vì vậy độ dài của phạm vi là `to - from`.

## 2. Objects.checkIndex

`Objects.checkIndex(index, length)` dùng khi cần xác thực một chỉ số đơn lẻ. Chỉ số hợp lệ bắt đầu từ 0 và nhỏ hơn `length`.

~~~java
int index = Objects.checkIndex(requestedIndex, values.length);
int value = values[index];
~~~

Nếu `requestedIndex` hợp lệ, phương thức trả lại chính chỉ số đó. Nếu chỉ số âm hoặc bằng/lớn hơn độ dài, phương thức ném `IndexOutOfBoundsException`.

Ví dụ:

- Với `length = 4`, các chỉ số hợp lệ là 0, 1, 2, 3.
- `index = -1` không hợp lệ.
- `index = 4` cũng không hợp lệ vì chỉ số cuối cùng là `length - 1`.
- Với `length = 0`, không có chỉ số đơn lẻ nào hợp lệ.

Cách viết thường gặp trong một phương thức truy cập mảng:

~~~java
static int get(int[] values, int index) {
    return values[Objects.checkIndex(index, values.length)];
}
~~~

Mảng được truy cập bằng chính chỉ số mà phương thức trả về sau khi kiểm tra.

## 3. Objects.checkFromToIndex

Dùng `Objects.checkFromToIndex(fromIndex, toIndex, length)` khi API nhận hai mốc đầu và cuối của một phạm vi.

Điều kiện hợp lệ:

~~~text
0 <= fromIndex <= toIndex <= length
~~~

Khoảng được kiểm tra là `[fromIndex, toIndex)`. `toIndex` có thể bằng `length` vì đây là mốc kết thúc exclusive, không phải chỉ số của một phần tử cần truy cập.

Ví dụ với mảng có 5 phần tử:

| Phạm vi | Hợp lệ? | Giải thích |
|---|---|---|
| `[0, 5)` | Có | Bao gồm tất cả 5 phần tử |
| `[1, 3)` | Có | Bao gồm chỉ số 1 và 2 |
| `[2, 2)` | Có | Phạm vi rỗng tại vị trí hợp lệ |
| `[0, 6)` | Không | Điểm kết thúc vượt quá length |
| `[-1, 2)` | Không | Điểm bắt đầu âm |
| `[4, 2)` | Không | Điểm bắt đầu lớn hơn điểm kết thúc |

Một phạm vi rỗng như `[2, 2)` hợp lệ nếu vị trí đó nằm trong giới hạn cho phép. Với `length = 5`, phạm vi `[5, 5)` cũng hợp lệ vì nó nằm ngay sau phần tử cuối cùng.

Ví dụ sử dụng:

~~~java
static int[] copyRange(int[] values, int from, int to) {
    Objects.checkFromToIndex(from, to, values.length);
    return Arrays.copyOfRange(values, from, to);
}
~~~

Kiểm tra tường minh đặc biệt hữu ích với `Arrays.copyOfRange`, vì API này có thể đệm giá trị mặc định khi điểm kết thúc vượt quá độ dài mảng nguồn. Nếu hợp đồng của phương thức yêu cầu phạm vi phải nằm hoàn toàn trong nguồn, hãy kiểm tra trước.

## 4. Objects.checkFromIndexSize

Dùng `Objects.checkFromIndexSize(fromIndex, size, length)` khi API nhận vị trí bắt đầu và số lượng phần tử.

Điều kiện hợp lệ tương đương:

~~~text
0 <= fromIndex
0 <= size
fromIndex + size <= length
~~~

Phương thức trả về `fromIndex` nếu hợp lệ. Cách này phù hợp với các API như `System.arraycopy`, nơi tham số được biểu diễn bằng vị trí nguồn và độ dài cần sao chép.

~~~java
static void copyInto(
        int[] source,
        int sourceFrom,
        int[] target,
        int targetFrom,
        int size) {

    Objects.checkFromIndexSize(sourceFrom, size, source.length);
    Objects.checkFromIndexSize(targetFrom, size, target.length);

    System.arraycopy(source, sourceFrom, target, targetFrom, size);
}
~~~

Cả phạm vi nguồn và phạm vi đích đều phải hợp lệ. Chỉ kiểm tra nguồn là chưa đủ vì vùng đích cũng có thể vượt giới hạn.

Một lợi ích quan trọng là kiểm tra phép cộng phạm vi an toàn trước lỗi tràn số nguyên. Không nên tự viết điều kiện `fromIndex + size <= length` mà không xử lý overflow: nếu tổng vượt `Integer.MAX_VALUE`, phép cộng int có thể quay vòng thành số âm và làm điều kiện sai lệch. `checkFromIndexSize` được thiết kế để kiểm tra trường hợp này đúng cách.

## 5. Phân biệt checkFromToIndex và checkFromIndexSize

Hai phương thức diễn đạt cùng một kiểu phạm vi nhưng nhận tham số khác nhau:

~~~java
Objects.checkFromToIndex(from, to, length);
Objects.checkFromIndexSize(from, size, length);
~~~

Nếu đã có hai mốc `from` và `to`, dùng `checkFromToIndex`. Nếu đã có vị trí bắt đầu và số lượng phần tử, dùng `checkFromIndexSize`.

Về mặt toán học, khi không xảy ra overflow:

~~~text
to = from + size
size = to - from
~~~

Không cần tự chuyển đổi tham số chỉ để gọi phương thức khác. Chọn overload khớp với cách API của bạn mô tả phạm vi sẽ làm code dễ đọc hơn và giảm nguy cơ tính toán sai.

## 6. Xử lý exception và giá trị trả về

Cả ba phương thức ném `IndexOutOfBoundsException` khi chỉ số hoặc phạm vi không hợp lệ. Đây là unchecked exception, nên không cần khai báo `throws` hoặc bắt buộc phải bắt trong chữ ký phương thức.

Thông thường, một phương thức thư viện hoặc API sẽ để exception truyền lên caller. Chỉ bắt exception khi ứng dụng có cách xử lý cụ thể, chẳng hạn chuyển thành lỗi đầu vào ở tầng giao tiếp hoặc hiển thị thông báo phù hợp.

Không nên dựa vào nội dung message của exception để điều khiển logic. Nội dung thông báo có thể khác nhau giữa implementation hoặc phiên bản runtime; hãy dựa vào loại exception và hợp đồng của API.

Giá trị trả về có thể được sử dụng trực tiếp:

~~~java
return values[Objects.checkIndex(index, values.length)];
~~~

Hoặc gọi độc lập để xác thực trước một chuỗi thao tác:

~~~java
Objects.checkFromIndexSize(offset, count, buffer.length);
process(buffer, offset, count);
~~~

Nếu không cần giá trị trả về, có thể gọi phương thức như một bước xác thực. Tuy nhiên, đừng dùng kết quả kiểm tra để giả định một đối tượng khác hoặc một vùng dữ liệu khác cũng hợp lệ.

## 7. Ví dụ chạy được với Java 17+

Tạo file **ObjectsCheckIndexDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class ObjectsCheckIndexDemo {
    static int get(int[] values, int index) {
        return values[Objects.checkIndex(index, values.length)];
    }

    static int[] copyRange(int[] values, int from, int to) {
        Objects.checkFromToIndex(from, to, values.length);
        return Arrays.copyOfRange(values, from, to);
    }

    static void copyInto(
            int[] source,
            int sourceFrom,
            int[] target,
            int targetFrom,
            int size) {

        Objects.checkFromIndexSize(sourceFrom, size, source.length);
        Objects.checkFromIndexSize(targetFrom, size, target.length);
        System.arraycopy(source, sourceFrom, target, targetFrom, size);
    }

    public static void main(String[] args) {
        int[] values = {10, 20, 30, 40};

        System.out.println("get: " + get(values, 2));
        System.out.println("range: " + Arrays.toString(copyRange(values, 1, 3)));

        int[] target = new int[4];
        copyInto(values, 0, target, 1, 2);
        System.out.println("copied: " + Arrays.toString(target));

        try {
            get(values, -1);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("index rejected");
        }

        try {
            copyRange(values, 1, 5);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("range rejected");
        }

        try {
            copyInto(values, Integer.MAX_VALUE, target, 0, 2);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("size range rejected");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ObjectsCheckIndexDemo.java
java ObjectsCheckIndexDemo
~~~

Kết quả stdout:

~~~text
get: 30
range: [20, 30]
copied: [0, 10, 20, 0]
index rejected
range rejected
size range rejected
~~~

Trong ví dụ, `get` kiểm tra chỉ số đơn, `copyRange` xác thực hai mốc nửa mở, còn `copyInto` kiểm tra cả vùng nguồn lẫn vùng đích. Trường hợp `Integer.MAX_VALUE` cùng size 2 được từ chối an toàn, dù phép cộng int thông thường có thể bị overflow.

## 8. Áp dụng cho API và cấu trúc dữ liệu

Các phương thức này hữu ích khi viết:

- Hàm truy cập mảng hoặc vùng nhớ theo index.
- Hàm xử lý một đoạn dữ liệu theo cặp from/to.
- Hàm sao chép dữ liệu nhận offset và size.
- API thao tác trên buffer, slice hoặc một vùng con của collection.
- Constructor hoặc method nhận chỉ số từ caller và cần xác thực hợp đồng đầu vào.

Nếu kiểm tra chỉ số cho List, truyền `list.size()` làm length:

~~~java
static <T> T elementAt(java.util.List<T> list, int index) {
    return list.get(Objects.checkIndex(index, list.size()));
}
~~~

Lưu ý kiểm tra và sử dụng phải áp dụng trên cùng đối tượng và cùng giới hạn. Nếu cấu trúc dữ liệu có thể bị thread khác thay đổi giữa lúc kiểm tra và lúc truy cập, việc kiểm tra trước không tự tạo ra tính nguyên tử hay thread-safety. Cần cơ chế đồng bộ hoặc cấu trúc dữ liệu phù hợp nếu có cập nhật đồng thời.

Các phương thức cũng không thay thế kiểm tra `null`: nếu đối tượng là null, việc đọc `length` hoặc gọi `size()` vẫn có thể ném `NullPointerException`. Hãy xác thực null theo hợp đồng riêng khi cần.

## 9. Lỗi thường gặp

**Dùng length như chỉ số cuối hợp lệ**

Chỉ số cuối cùng là `length - 1`. Với một phần tử, index hợp lệ là 0; index bằng length luôn nằm ngoài phạm vi.

**Nhầm điểm cuối của range là inclusive**

`checkFromToIndex(from, to, length)` dùng khoảng `[from, to)`. Phần tử tại `to` không thuộc phạm vi.

**Nhầm size với toIndex**

`checkFromIndexSize(from, size, length)` nhận số lượng phần tử, không nhận mốc kết thúc. Nếu truyền `to` vào vị trí size, phạm vi có thể sai.

**Chỉ kiểm tra vùng nguồn khi sao chép**

Một thao tác copy cần kiểm tra cả nguồn và đích. Vùng đích vượt giới hạn vẫn gây lỗi dù vùng nguồn hợp lệ.

**Tự cộng from + size bằng int**

Phép cộng có thể overflow. Dùng `checkFromIndexSize` để kiểm tra phạm vi theo hợp đồng và tránh lỗi tính toán.

**Dùng kiểm tra như cơ chế đồng bộ**

Các phương thức chỉ xác thực giới hạn tại thời điểm gọi. Chúng không khóa mảng hoặc List và không ngăn thread khác thay đổi cấu trúc dữ liệu.

**Bắt quá rộng hoặc phụ thuộc exception message**

Bắt `IndexOutOfBoundsException` khi cần xử lý đúng loại lỗi; không phân tích chuỗi message để suy luận chỉ số sai.

## 10. Checklist lựa chọn

- Một chỉ số đơn: `Objects.checkIndex(index, length)`.
- Hai mốc đầu/cuối: `Objects.checkFromToIndex(from, to, length)`.
- Vị trí bắt đầu và số lượng: `Objects.checkFromIndexSize(from, size, length)`.
- Dùng overload `int` hoặc `long` phù hợp với kiểu chỉ số.
- Kiểm tra cả vùng nguồn và vùng đích trước thao tác copy.
- Không tự cộng chỉ số và size bằng phép toán có thể overflow.
- Nhớ rằng range là nửa mở và có thể rỗng nếu các mốc hợp lệ.
- Xử lý null và truy cập đồng thời theo hợp đồng riêng.

Các phương thức kiểm tra chỉ số của `Objects` là API hiện hành từ Java 9. Chúng giúp chuẩn hóa việc xác thực index và range, làm rõ hợp đồng đầu vào, đồng thời giảm lỗi biên và lỗi overflow trong code thao tác dữ liệu.
