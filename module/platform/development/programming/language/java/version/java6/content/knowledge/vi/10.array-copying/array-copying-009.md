# Kiểm thử chỉ số sai, mảng rỗng và nguồn null

## 1. Kiểm thử biên để tránh hiểu sai hợp đồng

Một thao tác sao chép mảng không chỉ cần chạy đúng với dữ liệu thông thường. Các lỗi hay xuất hiện ở ranh giới:

- Chỉ số đầu bằng đúng độ dài nguồn.
- Khoảng sao chép có độ dài 0.
- Chỉ số cuối vượt đuôi nguồn.
- Nguồn là mảng rỗng.
- Nguồn là `null`.

Những trường hợp này không có cùng ý nghĩa. Đặc biệt, **mảng rỗng là một đối tượng mảng hợp lệ**, còn `null` nghĩa là không có đối tượng mảng để sử dụng.

Mục tiêu kiểm thử là khẳng định hành vi theo hợp đồng của phương thức: kết quả nào hợp lệ, ngoại lệ nào được mong đợi và dữ liệu nào phải giữ nguyên. Không nên chỉ chạy thử, thấy một ngoại lệ rồi kết luận mọi chỉ số khác thường đều sai.

Bài dùng `Arrays.copyOf`, `Arrays.copyOfRange` và một số ca đối chiếu với `System.arraycopy`. Các API này vẫn áp dụng trong Java hiện đại; chương trình kiểm tra đầy đủ chạy bằng Java 17+.

## 2. Viết điều kiện đúng trước khi viết test

### Arrays.copyOf

Với mảng nguồn khác `null`:

```java
int[] copied = Arrays.copyOf(source, newLength);
```

Đây là mẫu lời gọi, cần các biến tương ứng trong chương trình.

- `newLength >= 0` là độ dài kết quả hợp lệ về mặt dấu.
- `newLength == 0` tạo mảng rỗng.
- `newLength > source.length` được phép; phần dư nhận giá trị mặc định.
- `newLength < 0` gây `NegativeArraySizeException`.
- Nguồn `null` gây `NullPointerException`, kể cả khi độ dài mong muốn bằng 0.

Không áp điều kiện “độ dài mới phải nằm trong độ dài nguồn” cho `copyOf`. Nếu viết test mong ngoại lệ khi tăng độ dài, test đó đang kiểm tra một yêu cầu không thuộc hợp đồng của API.

### Arrays.copyOfRange

`Arrays.copyOfRange(source, from, to)` dùng khoảng nửa mở `[from, to)`: gồm `from`, không gồm `to`.

Với nguồn khác `null`, các ràng buộc quan trọng là:

```text
0 <= from <= source.length
from <= to
độ dài kết quả = to - from
```

`to` có thể lớn hơn `source.length`; đó là trường hợp có đệm, không mặc nhiên là lỗi vượt chỉ số. Hợp đồng của các biến thể sao chép được mô tả trong [tài liệu Arrays](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html).

Giả sử `source = new int[] {3, 6, 9}`:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| `copyOfRange(source, 0, 3)` | `[3, 6, 9]` |
| `copyOfRange(source, 3, 3)` | Mảng rỗng |
| `copyOfRange(source, 3, 5)` | `[0, 0]` |
| `copyOfRange(source, 1, 5)` | `[6, 9, 0, 0]` |
| `copyOfRange(source, -1, 1)` | `ArrayIndexOutOfBoundsException` |
| `copyOfRange(source, 4, 4)` | `ArrayIndexOutOfBoundsException` |
| `copyOfRange(source, 2, 1)` | `IllegalArgumentException` |

Ca `(4, 4)` rất hữu ích: khoảng yêu cầu có độ dài 0 nhưng vị trí bắt đầu đã nằm ngoài biên cho phép. **Khoảng rỗng không làm mọi chỉ số trở nên hợp lệ.**

## 3. Mảng rỗng khác null ngay cả khi không sao chép phần tử

Đặt:

```java
int[] empty = new int[0];
int[] missing = null;
```

Hai biến có cùng kiểu khai báo `int[]`, nhưng trạng thái khác nhau.

| Thao tác | Với `empty` | Với `missing` |
| --- | --- | --- |
| `Arrays.copyOf(source, 0)` | Mảng rỗng hợp lệ | `NullPointerException` |
| `Arrays.copyOf(source, 2)` | `[0, 0]` | `NullPointerException` |
| `Arrays.copyOfRange(source, 0, 0)` | Mảng rỗng hợp lệ | `NullPointerException` |
| `Arrays.copyOfRange(source, 0, 2)` | `[0, 0]` | `NullPointerException` |
| Đọc `source.length` | Giá trị 0 | `NullPointerException` |

Đừng tạo nguồn rỗng bằng cách viết `null` trong test. Hai đầu vào này phải được kiểm thử riêng vì chúng thể hiện hai hợp đồng khác nhau.

Khi gọi một phương thức có nhiều biến thể cho nhiều kiểu mảng, một literal `null` không chỉ rõ kiểu có thể khiến trình biên dịch không chọn được biến thể. Dùng biến đã khai báo kiểu như `int[] missing = null;` hoặc ép rõ `(int[]) null` khi test. Lỗi chọn biến thể ở lúc biên dịch khác với ngoại lệ khi chạy.

## 4. Mỗi ca lỗi nên vi phạm một điều kiện chính

Một test tốt giúp người đọc biết nguyên nhân thất bại.

Ví dụ, để kiểm tra vị trí bắt đầu vượt nguồn dài 3, dùng `from = 4, to = 4`. Điều kiện thứ tự `from <= to` vẫn đúng, nên lỗi cần quan sát là vị trí bắt đầu.

Để kiểm tra khoảng đảo chiều, dùng `from = 2, to = 1`. Cả hai giá trị không vượt độ dài nguồn; điều sai là thứ tự khoảng.

Không dùng một lời gọi như sau để học riêng quy tắc nguồn `null`:

```java
Arrays.copyOfRange((int[]) null, -5, -10);
```

Đoạn này cố ý có nhiều đối số sai. Nếu hợp đồng không cam kết thứ tự ưu tiên kiểm tra, test không nên khóa chặt vào một loại ngoại lệ chỉ vì một phiên bản JVM hiện tại kiểm tra điều kiện đó trước.

Với nguồn `null`, hãy giữ các chỉ số thông thường như `0, 0`. Với độ dài âm, hãy dùng một nguồn không `null`. Cách tách này giúp test rõ nghĩa và ít phụ thuộc vào chi tiết triển khai.

## 5. Chương trình kiểm thử độc lập, không cần thư viện ngoài

Chương trình sau kiểm tra cả kết quả và loại ngoại lệ. Nếu một ca sai, nó ném `AssertionError` và không in dòng PASS.

Lưu thành `ArrayCopyBoundaryChecks.java`:

```java
import java.util.Arrays;

public class ArrayCopyBoundaryChecks {
    private static int checks;

    private static void checkArray(
            String label, int[] expected, int[] actual) {
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError(label
                    + ": expected " + Arrays.toString(expected)
                    + ", actual " + Arrays.toString(actual));
        }
        checks++;
    }

    private static void expectThrows(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {

        try {
            action.run();
        } catch (RuntimeException actual) {
            if (!expected.isInstance(actual)) {
                throw new AssertionError(label
                        + ": expected " + expected.getSimpleName()
                        + ", actual " + actual.getClass().getSimpleName(),
                        actual);
            }
            checks++;
            return;
        }

        throw new AssertionError(label + ": expected an exception");
    }

    public static void main(String[] args) {
        int[] source = {3, 6, 9};
        int[] empty = new int[0];
        int[] missing = null;

        checkArray("copy empty to empty",
                new int[0], Arrays.copyOf(empty, 0));
        checkArray("expand empty",
                new int[] {0, 0}, Arrays.copyOf(empty, 2));
        checkArray("copy to zero",
                new int[0], Arrays.copyOf(source, 0));

        expectThrows("negative length", NegativeArraySizeException.class,
                () -> Arrays.copyOf(source, -1));
        expectThrows("null source with zero length", NullPointerException.class,
                () -> Arrays.copyOf(missing, 0));

        checkArray("full range",
                new int[] {3, 6, 9}, Arrays.copyOfRange(source, 0, 3));
        checkArray("empty range at end",
                new int[0], Arrays.copyOfRange(source, 3, 3));
        checkArray("padding from end",
                new int[] {0, 0}, Arrays.copyOfRange(source, 3, 5));
        checkArray("empty range on empty",
                new int[0], Arrays.copyOfRange(empty, 0, 0));
        checkArray("padding from empty",
                new int[] {0, 0}, Arrays.copyOfRange(empty, 0, 2));
        checkArray("end beyond source",
                new int[] {6, 9, 0, 0},
                Arrays.copyOfRange(source, 1, 5));

        expectThrows("negative start", ArrayIndexOutOfBoundsException.class,
                () -> Arrays.copyOfRange(source, -1, 1));
        expectThrows("start after end of source",
                ArrayIndexOutOfBoundsException.class,
                () -> Arrays.copyOfRange(source, 4, 4));
        expectThrows("reversed range", IllegalArgumentException.class,
                () -> Arrays.copyOfRange(source, 2, 1));
        expectThrows("null with empty range", NullPointerException.class,
                () -> Arrays.copyOfRange(missing, 0, 0));
        expectThrows("invalid start on empty",
                ArrayIndexOutOfBoundsException.class,
                () -> Arrays.copyOfRange(empty, 1, 1));

        checkArray("source unchanged",
                new int[] {3, 6, 9}, source);

        System.arraycopy(empty, 0, empty, 0, 0);
        checks++;

        expectThrows("arraycopy invalid start with zero length",
                IndexOutOfBoundsException.class,
                () -> System.arraycopy(source, 4, empty, 0, 0));
        expectThrows("arraycopy null with zero length",
                NullPointerException.class,
                () -> System.arraycopy(missing, 0, empty, 0, 0));

        System.out.println("PASS: " + checks + " checks");
    }
}
```

Biên dịch và chạy:

```shell
javac ArrayCopyBoundaryChecks.java
java ArrayCopyBoundaryChecks
```

Stdout:

```text
PASS: 20 checks
```

Không cần bật `-ea`: ví dụ không dùng từ khóa Java `assert`, mà chủ động ném `AssertionError` khi không đúng mong đợi.

Hàm `expectThrows` kiểm tra bằng `expected.isInstance(actual)`, nên chấp nhận cả một lớp con của loại ngoại lệ mong đợi. Nếu không có ngoại lệ hoặc có loại ngoại lệ khác, ca kiểm tra thất bại.

Các phép so sánh dùng `Arrays.equals`, không dùng `==`. Hai mảng khác đối tượng vẫn có thể chứa cùng các giá trị mong đợi.

## 6. Vì sao đối chiếu với System.arraycopy?

Ba ca cuối nhắc rằng không phải mọi API sao chép đều có cùng quy tắc biên.

`System.arraycopy` sao chép vào mảng đích đã tồn tại và yêu cầu đoạn nguồn, đoạn đích hợp lệ. Với độ dài sao chép bằng 0:

- Sao chép từ mảng rỗng tại vị trí 0 sang mảng rỗng tại vị trí 0 là hợp lệ.
- Vị trí đầu vượt độ dài mảng vẫn không hợp lệ.
- Nguồn `null` vẫn gây `NullPointerException`.

Hợp đồng của phương thức quy định lỗi chỉ số bằng `IndexOutOfBoundsException`; không nên bắt test phải nhận một lớp con cụ thể chỉ dựa trên thông báo của một lần chạy. Xem [System.arraycopy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)).

Đừng bê nguyên test của `copyOfRange` sang `arraycopy` rồi mong việc đọc vượt đuôi cũng được đệm. Mỗi lời gọi phải được kiểm tra theo đúng hợp đồng của nó.

## 7. Chuyển sang JUnit Jupiter

Khi dự án đã cấu hình JUnit Jupiter, có thể diễn đạt cùng các ca bằng `assertArrayEquals`, `assertThrows` và `assertDoesNotThrow`.

Đoạn dưới là một lớp test trong dự án đã có JUnit Jupiter, không phải chương trình chạy trực tiếp bằng lệnh `java`:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ArrayCopyBoundaryTest {
    @Test
    void emptySourceCanProducePadding() {
        int[] empty = new int[0];

        int[] copied = java.util.Arrays.copyOfRange(empty, 0, 2);

        assertArrayEquals(new int[] {0, 0}, copied);
    }

    @Test
    void nullSourceIsInvalidEvenForEmptyRange() {
        int[] source = null;

        assertThrows(NullPointerException.class,
                () -> java.util.Arrays.copyOfRange(source, 0, 0));
    }
}
```

`assertThrows` chấp nhận loại ngoại lệ chỉ định hoặc lớp con của nó. Nếu thật sự cần đúng một lớp cụ thể, JUnit có `assertThrowsExactly`; chỉ dùng yêu cầu chặt hơn này khi hợp đồng cần kiểm thử bảo đảm như vậy. Các phương thức được mô tả trong [JUnit Jupiter Assertions](https://docs.junit.org/6.1.3/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html).

Một ca bắt ngoại lệ nên đặt lời gọi đang kiểm tra trực tiếp trong lambda. Không để nhiều thao tác không liên quan cùng nằm bên trong, vì một thao tác khác có thể ném cùng loại ngoại lệ và khiến test qua nhầm.

Ví dụ, test nguồn `null` không nên chỉ viết `() -> source.length`: ngoại lệ đó đến từ việc đọc `length`, chưa hề chứng minh lời gọi sao chép đã được kiểm tra.

## 8. Kiểm thử nội dung, độ dài và việc giữ nguyên nguồn

Chỉ kiểm tra “không ném ngoại lệ” còn thiếu nhiều thông tin.

Với một lời gọi hợp lệ, có thể kiểm tra:

- Độ dài đúng yêu cầu.
- Các phần tử được lấy từ đúng vị trí.
- Phần dư có đúng giá trị mặc định nếu hợp đồng cho phép đệm.
- Nguồn giữ nguyên khi dùng các phương thức tạo bản sao như `copyOf` hoặc `copyOfRange`.

`assertArrayEquals` hoặc phép so sánh trong ví dụ độc lập đã kiểm tra cả độ dài và thứ tự các giá trị. Nếu viết thêm kiểm tra độ dài riêng, hãy dùng nó khi giúp báo lỗi rõ hơn, không phải để tăng số lượng test.

Với mảng tham chiếu, cần thêm ca tương ứng cho `null` trong phần đệm. Một mảng hợp lệ chứa phần tử `null` khác với chính tham chiếu nguồn bằng `null`.

Nếu chuyển sang `System.arraycopy`, không mặc định mọi lỗi đều giữ nguyên đích. Lỗi kiểu phần tử trong khi sao chép mảng tham chiếu có thể để lại phần đầu đã được chép. Đó là một nhóm hợp đồng khác với chỉ số sai trong bài này.

## 9. Các lỗi viết test thường gặp

| Lỗi | Vì sao test chưa đúng | Cách điều chỉnh |
| --- | --- | --- |
| Mong lỗi khi `to > source.length` với `copyOfRange` | API cho phép đệm khi vị trí bắt đầu hợp lệ | Kiểm tra nội dung có đệm |
| Chỉ có nguồn thông thường | Bỏ sót rỗng, biên cuối và `null` | Chọn các ca tại ranh giới |
| Dùng nguồn `null` thay cho mảng rỗng | Hai trạng thái khác hợp đồng | Tạo `new int[0]` cho ca rỗng |
| Vi phạm nhiều điều kiện rồi khóa chặt ngoại lệ đầu tiên | Có thể phụ thuộc thứ tự kiểm tra của triển khai | Tách ca theo một điều kiện chính |
| Bắt `Exception` rồi coi là test qua | Có thể che lỗi khác hoàn toàn | Kiểm tra loại ngoại lệ mong đợi |
| Dùng `==` để kiểm tra nội dung mảng | Đang so sánh tham chiếu | Dùng so sánh mảng theo phần tử |
| Kiểm tra nguyên văn thông báo lỗi của JDK | Thông báo không phải lúc nào cũng là hợp đồng ổn định | Ưu tiên loại ngoại lệ và trạng thái dữ liệu |
| Đặt thao tác gây lỗi phụ trước lời gọi cần test | Có thể test nhầm thao tác | Thu hẹp lambda vào đúng lời gọi |

Trong dự án thật, ưu tiên kiểm thử chính sách và phép tính chỉ số do bạn viết. Nếu một hàm bọc coi `null` là nguồn rỗng, đó là hợp đồng riêng của hàm bọc và cần được đặt tên, tài liệu hóa, kiểm thử riêng; đừng gán hành vi đó cho `Arrays.copyOf`.

## 10. Tự kiểm tra

1. Nguồn dài 3, `copyOfRange(source, 3, 3)` có lỗi không? **Không; đây là khoảng rỗng ở biên cuối hợp lệ.**
2. Cũng nguồn đó, `copyOfRange(source, 4, 4)` có hợp lệ vì khoảng rỗng không? **Không; vị trí bắt đầu đã vượt nguồn.**
3. Nguồn rỗng, `copyOfRange(empty, 0, 2)` với `int[]` cho gì? **`[0, 0]`.**
4. Nguồn `null`, yêu cầu kết quả dài 0 có bỏ qua lỗi được không? **Không; vẫn phải kiểm tra hành vi `NullPointerException`.**
5. Vì sao kiểm tra độ dài mới âm cần dùng nguồn không `null`? **Để chỉ kiểm tra một điều kiện sai chính, tránh phụ thuộc thứ tự phát hiện lỗi.**
6. Một ca chỉ bắt được bất kỳ ngoại lệ nào đã đủ chưa? **Chưa; cần xác minh đúng loại và đúng thao tác gây ngoại lệ.**
