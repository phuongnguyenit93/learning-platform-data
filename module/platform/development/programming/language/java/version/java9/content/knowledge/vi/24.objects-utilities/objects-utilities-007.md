# Biên đoạn rỗng, số âm và nguy cơ tràn khi tính chỉ số

Khi xử lý mảng, List, buffer hoặc một vùng dữ liệu, việc kiểm tra chỉ số cần xử lý đúng ba nhóm tình huống: **đoạn rỗng**, **giá trị âm** và **tràn số khi tính điểm kết thúc**. Từ Java 9, `java.util.Objects` cung cấp `checkIndex`, `checkFromToIndex` và `checkFromIndexSize` để kiểm tra các điều kiện này theo hợp đồng thống nhất.

Các phương thức trả về chỉ số bắt đầu nếu hợp lệ và ném `IndexOutOfBoundsException` nếu chỉ số hoặc phạm vi không hợp lệ. Chúng đặc biệt hữu ích khi API nhận vị trí bắt đầu cùng số phần tử cần xử lý.

## 1. Quy ước đoạn nửa mở

Các API Java thường biểu diễn một đoạn bằng khoảng nửa mở:

~~~text
[from, to)
~~~

Nghĩa là:

- Bao gồm phần tử tại `from`.
- Không bao gồm phần tử tại `to`.
- Số phần tử trong đoạn là `to - from`.
- `to` có thể bằng độ dài dữ liệu vì nó là điểm kết thúc exclusive, không phải chỉ số phần tử cần truy cập.

Ví dụ, với mảng có độ dài 5:

| Đoạn | Phần tử được chọn | Số phần tử |
|---|---|---:|
| `[0, 5)` | Chỉ số 0, 1, 2, 3, 4 | 5 |
| `[1, 3)` | Chỉ số 1, 2 | 2 |
| `[2, 2)` | Không có phần tử | 0 |
| `[5, 5)` | Không có phần tử, ngay sau phần tử cuối | 0 |

Đoạn rỗng vẫn có thể hợp lệ. Ví dụ `[2, 2)` là một đoạn rỗng nằm bên trong dữ liệu; `[length, length)` là đoạn rỗng ở cuối dữ liệu. Hai mốc phải nằm trong giới hạn và `from` không được lớn hơn `to`.

## 2. Ba phương thức kiểm tra của Objects

Java 9 cung cấp các overload nhận `int` và `long`:

~~~java
Objects.checkIndex(index, length);
Objects.checkFromToIndex(fromIndex, toIndex, length);
Objects.checkFromIndexSize(fromIndex, size, length);
~~~

| Phương thức | Điều kiện hợp lệ | Trả về |
|---|---|---|
| `checkIndex(index, length)` | `0 <= index < length` | `index` |
| `checkFromToIndex(from, to, length)` | `0 <= from <= to <= length` | `from` |
| `checkFromIndexSize(from, size, length)` | `0 <= from`, `0 <= size`, đoạn bắt đầu tại from có size phần tử nằm trong length | `from` |

`checkIndex` dùng cho một vị trí đơn lẻ. Hai phương thức còn lại kiểm tra phạm vi. Chọn phương thức theo cách API biểu diễn dữ liệu: nếu đã có from/to thì dùng `checkFromToIndex`; nếu có from/size thì dùng `checkFromIndexSize`.

## 3. Đoạn rỗng và độ dài bằng 0

Một đoạn rỗng không có nghĩa là chỉ số bắt đầu sai. Với độ dài `length`, đoạn rỗng hợp lệ khi hai mốc bằng nhau và nằm trong khoảng từ 0 đến length.

~~~java
Objects.checkFromToIndex(2, 2, 5); // hợp lệ
Objects.checkFromToIndex(5, 5, 5); // hợp lệ
Objects.checkFromIndexSize(5, 0, 5); // hợp lệ
~~~

Ngược lại, kiểm tra một chỉ số đơn lẻ có quy tắc khác:

~~~java
Objects.checkIndex(5, 5); // IndexOutOfBoundsException
~~~

Vị trí 5 không phải index hợp lệ trong dữ liệu có 5 phần tử; nó chỉ có thể là điểm kết thúc của một đoạn rỗng.

Khi `length = 0`:

- Không có index đơn nào hợp lệ vì không tồn tại giá trị thỏa `0 <= index < 0`.
- Đoạn `[0, 0)` hợp lệ.
- `checkFromIndexSize(0, 0, 0)` hợp lệ.
- Đoạn có from âm, to dương hoặc size dương đều không hợp lệ.

Điều này hữu ích cho API có thể nhận danh sách rỗng: không cần xem đoạn rỗng là lỗi nếu hợp đồng cho phép thao tác không làm gì.

## 4. Giá trị âm phải bị từ chối

Index, điểm bắt đầu và size không được âm. Một số trường hợp:

~~~java
Objects.checkIndex(-1, 5);          // không hợp lệ
Objects.checkFromToIndex(-1, 2, 5); // không hợp lệ
Objects.checkFromToIndex(3, 2, 5);  // không hợp lệ: from > to
Objects.checkFromIndexSize(1, -1, 5); // không hợp lệ
~~~

Cần phân biệt:

- Index âm: vị trí không tồn tại.
- From âm: đoạn bắt đầu trước dữ liệu.
- Size âm: số lượng phần tử không có ý nghĩa.
- From lớn hơn to: thứ tự hai mốc bị đảo.

Không nên tự sửa giá trị âm thành 0 nếu hợp đồng API yêu cầu caller truyền phạm vi hợp lệ. Tự clamp tham số có thể che giấu lỗi ở nơi gọi và làm thay đổi ý nghĩa nghiệp vụ. Chỉ chuẩn hóa giá trị khi đó là hành vi được mô tả rõ trong thiết kế API.

## 5. Nguy cơ tràn khi tính from + size

Một lỗi phổ biến là tự tính điểm kết thúc bằng phép cộng:

~~~java
int to = from + size;
~~~

Phép cộng kiểu `int` có thể tràn. Java không tự ném exception khi phép toán số nguyên vượt giới hạn; kết quả có thể quay vòng thành một số âm hoặc một giá trị nhỏ hơn dự kiến.

Ví dụ:

~~~java
int from = Integer.MAX_VALUE - 5;
int size = 10;
int to = from + size; // bị overflow thành số âm
~~~

Về mặt toán học, điểm kết thúc lớn hơn `Integer.MAX_VALUE`, nhưng kiểu `int` không thể biểu diễn giá trị đó. Nếu code chỉ kiểm tra `to <= length`, giá trị âm sau overflow có thể làm điều kiện sai lệch.

Khi API nhận from và size, hãy dùng:

~~~java
Objects.checkFromIndexSize(from, size, length);
~~~

Phương thức này kiểm tra phạm vi mà không yêu cầu caller tự cộng hai số để xác thực. Nó phát hiện cả trường hợp phép tính điểm kết thúc vượt giới hạn kiểu số.

Nếu cần tính `to` để sử dụng sau khi xác thực, có thể tính `from + size` sau lời gọi thành công. Khi các điều kiện đã được kiểm tra, tổng hợp lệ nằm trong `[0, length]` nên không vượt độ dài hợp lệ.

## 6. Tràn số với long

Dùng overload `long` khi miền chỉ số hoặc kích thước của API được biểu diễn bằng long:

~~~java
long from = Long.MAX_VALUE - 3;
long size = 8;

Objects.checkFromIndexSize(from, size, Long.MAX_VALUE);
// IndexOutOfBoundsException
~~~

Chuyển sang `long` giúp mở rộng miền biểu diễn, nhưng không loại bỏ nguy cơ overflow. Tổng của hai giá trị long vẫn có thể vượt `Long.MAX_VALUE`. Vì vậy không nên nghĩ rằng chỉ cần ép int sang long rồi tự cộng là luôn an toàn.

Chọn overload có kiểu phù hợp với dữ liệu. Nếu API nhận `long`, dùng kiểm tra long; nếu API thao tác trên mảng Java thông thường, độ dài mảng là int nên overload int thường phù hợp.

## 7. checkFromToIndex hay checkFromIndexSize?

Hai phương thức diễn đạt phạm vi theo hai cách:

~~~java
Objects.checkFromToIndex(from, to, length);
Objects.checkFromIndexSize(from, size, length);
~~~

Dùng `checkFromToIndex` khi caller đã có hai mốc. Phương thức kiểm tra trực tiếp `0 <= from <= to <= length`; nó không cần tự cộng from và size.

Dùng `checkFromIndexSize` khi caller cung cấp vị trí bắt đầu và số lượng phần tử. Phương thức này phù hợp khi cần tránh lỗi do tự tính `from + size`.

Không nên chuyển đổi qua lại chỉ để gọi một phương thức khác. Hãy giữ cách biểu diễn tham số của API và dùng đúng hàm kiểm tra tương ứng.

## 8. Áp dụng khi sao chép dữ liệu

Một thao tác sao chép cần kiểm tra cả đoạn nguồn lẫn đoạn đích. Ví dụ với `System.arraycopy`:

~~~java
static void copy(
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

Nếu nguồn hợp lệ nhưng đích không đủ chỗ, thao tác vẫn thất bại. Kiểm tra cả hai phía giúp xác thực hợp đồng của hàm trước khi sao chép.

Với API nhận from/to, có thể xác thực rồi chuyển đoạn sang hàm khác:

~~~java
static int[] copyRange(int[] values, int from, int to) {
    Objects.checkFromToIndex(from, to, values.length);
    return Arrays.copyOfRange(values, from, to);
}
~~~

Lưu ý `Arrays.copyOfRange` có hành vi đệm giá trị mặc định nếu điểm cuối vượt độ dài mảng nguồn. Nếu hợp đồng của ứng dụng yêu cầu đoạn phải nằm hoàn toàn trong mảng gốc, kiểm tra bằng `checkFromToIndex` trước khi gọi.

## 9. Ví dụ chạy được với Java 17+

Tạo file **IndexRangeSafetyDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class IndexRangeSafetyDemo {
    static int[] copyRange(int[] values, int from, int to) {
        Objects.checkFromToIndex(from, to, values.length);
        return Arrays.copyOfRange(values, from, to);
    }

    static void copySize(
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

        System.out.println("empty range: "
                + Arrays.toString(copyRange(values, 4, 4)));
        System.out.println("middle range: "
                + Arrays.toString(copyRange(values, 1, 3)));

        int[] target = new int[4];
        copySize(values, 0, target, 1, 2);
        System.out.println("copied: " + Arrays.toString(target));

        try {
            Objects.checkIndex(-1, values.length);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("negative index rejected");
        }

        try {
            Objects.checkFromToIndex(3, 2, values.length);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("reversed range rejected");
        }

        try {
            Objects.checkFromIndexSize(1, -1, values.length);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("negative size rejected");
        }

        try {
            Objects.checkFromIndexSize(
                    Integer.MAX_VALUE - 5,
                    10,
                    Integer.MAX_VALUE
            );
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("int overflow range rejected");
        }

        try {
            Objects.checkFromIndexSize(
                    Long.MAX_VALUE - 3,
                    8L,
                    Long.MAX_VALUE
            );
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("long overflow range rejected");
        }

        Objects.checkFromIndexSize(4, 0, 4);
        System.out.println("empty range at end accepted");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IndexRangeSafetyDemo.java
java IndexRangeSafetyDemo
~~~

Kết quả stdout:

~~~text
empty range: []
middle range: [20, 30]
copied: [0, 10, 20, 0]
negative index rejected
reversed range rejected
negative size rejected
int overflow range rejected
long overflow range rejected
empty range at end accepted
~~~

Ví dụ thể hiện đoạn rỗng hợp lệ ở cuối mảng, đoạn giữa, sao chép có kiểm tra cả nguồn và đích, các giá trị âm và trường hợp overflow của cả int lẫn long.

## 10. Exception và các giới hạn cần nhớ

Ba phương thức kiểm tra ném `IndexOutOfBoundsException` nếu giá trị không hợp lệ. Đây là unchecked exception; API thường để exception truyền lên caller hoặc bắt ở tầng có thể đưa ra phản hồi phù hợp.

Không dựa vào nội dung message của exception để xác định lỗi. Nội dung message không phải dữ liệu nghiệp vụ ổn định. Dựa vào loại exception và hợp đồng của phương thức.

Các phương thức này chỉ kiểm tra giá trị chỉ số và độ dài được truyền vào tại thời điểm gọi. Chúng không:

- Kiểm tra đối tượng dữ liệu có null hay không.
- Khóa mảng hoặc List.
- Ngăn thread khác thay đổi dữ liệu sau bước kiểm tra.
- Đảm bảo một đối tượng khác có cùng kích thước.
- Thay thế các quy tắc nghiệp vụ về quyền truy cập hoặc giới hạn dung lượng.

Nếu cấu trúc dữ liệu có thể thay đổi đồng thời, việc kiểm tra rồi truy cập sau đó có thể gặp race condition. Cần đồng bộ hóa hoặc dùng cấu trúc dữ liệu phù hợp với yêu cầu thread-safety.

## 11. Lỗi thường gặp

**Coi length là index cuối hợp lệ:** index cuối cùng là `length - 1`; `length` chỉ có thể làm điểm kết thúc exclusive.

**Từ chối mọi đoạn rỗng:** `[from, from)` hợp lệ nếu mốc nằm trong `[0, length]`. Đừng nhầm đoạn rỗng với index đơn lẻ.

**Chấp nhận số âm:** index, from và size đều phải không âm. `from` cũng không được lớn hơn `to`.

**Tự cộng from + size trước khi kiểm tra:** phép cộng int/long có thể overflow. Dùng `checkFromIndexSize` nếu API nhận from và size.

**Chỉ kiểm tra một phía khi copy:** cần xác thực cả vùng nguồn và vùng đích.

**Dùng long nhưng vẫn tự cộng:** long cũng có giới hạn. Dùng overload long của Objects để xác thực phạm vi.

**Dùng checkFromToIndex cho tham số from/size mà không đổi đúng nghĩa:** tham số thứ hai của phương thức này là toIndex, không phải số lượng phần tử.

## 12. Checklist lựa chọn

- Một vị trí đơn: `checkIndex(index, length)`.
- Hai mốc đầu/cuối: `checkFromToIndex(from, to, length)`.
- Vị trí bắt đầu và số lượng: `checkFromIndexSize(from, size, length)`.
- Cho phép đoạn rỗng nếu nghiệp vụ cho phép; `from == to` hoặc `size == 0` có thể hợp lệ.
- Từ chối index/from/size âm và phạm vi đảo ngược.
- Không tự cộng from và size bằng phép toán có thể overflow.
- Dùng overload int hoặc long khớp với kiểu dữ liệu.
- Kiểm tra cả nguồn và đích khi sao chép.
- Xử lý null và cập nhật đồng thời theo hợp đồng riêng.

Các phương thức kiểm tra chỉ số của `Objects` là API hiện hành từ Java 9. Dùng đúng hàm cho từng kiểu phạm vi giúp xử lý đoạn rỗng chính xác, từ chối giá trị âm và tránh lỗi tràn số khi xác thực vùng dữ liệu.
