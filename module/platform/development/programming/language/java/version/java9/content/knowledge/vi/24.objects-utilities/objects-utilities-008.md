# Áp dụng các overload `int` của Java 9 trong hợp đồng phương thức

Từ Java 9, `java.util.Objects` cung cấp ba phương thức kiểm tra chỉ số và phạm vi với kiểu `int`: `checkIndex`, `checkFromToIndex` và `checkFromIndexSize`. Chúng giúp phương thức xác thực đối số chỉ số ngay tại ranh giới API, diễn đạt rõ điều kiện hợp lệ và tránh tự viết các phép so sánh dễ sai.

Ba phương thức đều trả về chỉ số bắt đầu đã kiểm tra nếu hợp lệ; nếu điều kiện không thỏa, chúng ném `IndexOutOfBoundsException`. Chúng chỉ kiểm tra quan hệ giữa các số nguyên, không truy cập mảng hay collection và không thay thế việc kiểm tra tham chiếu null.

## 1. Vì sao nên kiểm tra chỉ số trong hợp đồng phương thức?

Khi một phương thức nhận `index`, `fromIndex`, `toIndex` hoặc `size`, người gọi cần biết miền giá trị được chấp nhận. Ví dụ, một phương thức đọc phần tử có hợp đồng `0 <= index < length`; một phương thức sao chép đoạn có hợp đồng `0 <= from <= to <= length`.

Nếu mỗi phương thức tự viết điều kiện, rất dễ nhầm dấu `<` với `<=`, quên trường hợp đoạn rỗng, hoặc tính `from + size` rồi gặp tràn số nguyên. Các helper trong `Objects` tập trung hóa những quy tắc phổ biến này.

```java
public int elementAt(int index) {
    Objects.checkIndex(index, values.length);
    return values[index];
}
```

Lệnh kiểm tra làm rõ điều kiện đầu vào của phương thức. Nếu `index` không hợp lệ, lỗi được báo ngay trước khi truy cập phần tử.

## 2. `Objects.checkIndex(int index, int length)`

Phương thức này kiểm tra một chỉ số đơn lẻ:

```java
int checkedIndex = Objects.checkIndex(index, length);
```

Điều kiện hợp lệ:

\[0 \leq index < length\]

- `index` phải lớn hơn hoặc bằng `0`.
- `index` phải nhỏ hơn `length`.
- Nếu hợp lệ, phương thức trả về chính `index`.
- Nếu không hợp lệ, phương thức ném `IndexOutOfBoundsException`.

Ví dụ:

```java
int[] scores = {70, 80, 90};
int index = Objects.checkIndex(1, scores.length);
System.out.println(scores[index]);
```

Kết quả:

```text
80
```

Với mảng có độ dài `3`, chỉ số hợp lệ là `0`, `1`, `2`. Chỉ số `3` đã nằm ngoài phạm vi vì chỉ số cuối cùng luôn là `length - 1`. Khi `length` bằng `0`, không có chỉ số phần tử nào hợp lệ.

Do phương thức trả lại chỉ số đã kiểm tra, có thể dùng trực tiếp trong biểu thức:

```java
return values[Objects.checkIndex(index, values.length)];
```

## 3. `Objects.checkFromToIndex(int fromIndex, int toIndex, int length)`

Phương thức này kiểm tra một đoạn được mô tả bằng vị trí bắt đầu và vị trí kết thúc:

```java
int checkedFrom = Objects.checkFromToIndex(fromIndex, toIndex, length);
```

Điều kiện hợp lệ:

\[0 \leq fromIndex \leq toIndex \leq length\]

Đoạn được biểu diễn theo quy ước **đầu bao gồm, cuối không bao gồm**: `[fromIndex, toIndex)`. Phương thức trả về `fromIndex` nếu hợp lệ; nếu không, nó ném `IndexOutOfBoundsException`.

Ví dụ với mảng có độ dài `5`:

| Đoạn | Hợp lệ? | Số phần tử |
| --- | --- | ---: |
| `[0, 3)` | Có | 3 |
| `[2, 5)` | Có | 3 |
| `[2, 2)` | Có | 0 |
| `[5, 5)` | Có | 0 |
| `[3, 2)` | Không | — |
| `[-1, 2)` | Không | — |
| `[1, 6)` | Không | — |

Cho phép `fromIndex == toIndex` rất hữu ích: đó là một đoạn rỗng hợp lệ. Khi cả hai bằng `length`, đoạn rỗng nằm ngay sau phần tử cuối cùng và vẫn hợp lệ.

Ví dụ sử dụng trong phương thức lấy bản sao một đoạn:

```java
static int[] copyRange(int[] values, int fromIndex, int toIndex) {
    Objects.requireNonNull(values, "values");
    Objects.checkFromToIndex(fromIndex, toIndex, values.length);
    return Arrays.copyOfRange(values, fromIndex, toIndex);
}
```

Phương thức kiểm tra cả thứ tự hai đầu mút lẫn giới hạn trên của mảng. Nó không tự sao chép dữ liệu; thao tác sao chép vẫn do `Arrays.copyOfRange` thực hiện.

## 4. `Objects.checkFromIndexSize(int fromIndex, int size, int length)`

Phương thức này kiểm tra một đoạn bằng vị trí bắt đầu và số lượng phần tử:

```java
int checkedFrom = Objects.checkFromIndexSize(fromIndex, size, length);
```

Điều kiện hợp lệ tương đương:

\[0 \leq fromIndex \leq length\]

\[0 \leq size \leq length - fromIndex\]

Đoạn được kiểm tra tương ứng với `[fromIndex, fromIndex + size)`. Nếu hợp lệ, phương thức trả về `fromIndex`; nếu không, nó ném `IndexOutOfBoundsException`.

Ví dụ với `length = 5`:

| `fromIndex` | `size` | Đoạn tương ứng | Hợp lệ? |
| ---: | ---: | --- | --- |
| 0 | 3 | `[0, 3)` | Có |
| 2 | 3 | `[2, 5)` | Có |
| 5 | 0 | `[5, 5)` | Có |
| 4 | 2 | `[4, 6)` | Không |
| -1 | 1 | `[-1, 0)` | Không |
| 2 | -1 | `[2, 1)` | Không |

### Vì sao biến thể `fromIndex + size` hữu ích?

Nhiều API nhận vị trí bắt đầu và độ dài thay vì hai đầu mút. Nếu tự kiểm tra bằng:

```java
if (fromIndex < 0 || size < 0 || fromIndex + size > length) {
    throw new IndexOutOfBoundsException();
}
```

phép cộng `fromIndex + size` có thể tràn `int`. Khi tràn, kết quả có thể thành số âm hoặc một số nhỏ hơn giá trị toán học thực tế, khiến phép so sánh bỏ lọt đầu vào sai.

`checkFromIndexSize` kiểm tra theo quan hệ `size <= length - fromIndex` sau khi xác thực các biên. Cách kiểm tra này tránh phải dựa vào phép cộng có thể tràn.

Ví dụ:

```java
Objects.checkFromIndexSize(
    1_500_000_000,
    1_000_000_000,
    Integer.MAX_VALUE
);
```

Phạm vi trên không hợp lệ và phương thức ném `IndexOutOfBoundsException`, dù phép cộng hai đối số đầu nếu thực hiện bằng `int` sẽ bị tràn.

## 5. So sánh ba overload `int`

| Phương thức | Dữ liệu đầu vào | Điều kiện chính | Giá trị trả về |
| --- | --- | --- | --- |
| `checkIndex(index, length)` | Một chỉ số | `0 <= index < length` | `index` |
| `checkFromToIndex(from, to, length)` | Hai đầu mút | `0 <= from <= to <= length` | `from` |
| `checkFromIndexSize(from, size, length)` | Điểm bắt đầu và số lượng | `0 <= from <= length` và `0 <= size <= length - from` | `from` |

Cách chọn:

- Chỉ truy cập một phần tử: `checkIndex`.
- API nhận điểm bắt đầu và điểm kết thúc loại trừ: `checkFromToIndex`.
- API nhận điểm bắt đầu và số phần tử: `checkFromIndexSize`.

Không chuyển đổi tham số tùy tiện chỉ để dùng một helper khác. Hãy chọn overload khớp trực tiếp với cách hợp đồng phương thức mô tả phạm vi.

## 6. Dùng trong hợp đồng của API

### Kiểm tra chỉ số trước khi đọc hoặc ghi

```java
public int get(int index) {
    return elements[Objects.checkIndex(index, elements.length)];
}

public void set(int index, int value) {
    elements[Objects.checkIndex(index, elements.length)] = value;
}
```

Việc kiểm tra ở đầu phương thức giúp hợp đồng của `get` và `set` rõ ràng: chỉ số phải trỏ đến một phần tử hiện có.

### Kiểm tra đoạn theo hai đầu mút

```java
public int[] slice(int fromIndex, int toIndex) {
    Objects.checkFromToIndex(fromIndex, toIndex, elements.length);
    return Arrays.copyOfRange(elements, fromIndex, toIndex);
}
```

Hợp đồng chấp nhận đoạn rỗng và không cho phép `toIndex` vượt quá độ dài nguồn.

### Kiểm tra đoạn theo kích thước

```java
public void readInto(
        int[] destination,
        int sourceOffset,
        int destinationOffset,
        int size) {
    Objects.requireNonNull(destination, "destination");
    Objects.checkFromIndexSize(sourceOffset, size, elements.length);
    Objects.checkFromIndexSize(destinationOffset, size, destination.length);
    System.arraycopy(elements, sourceOffset, destination, destinationOffset, size);
}
```

Phương thức kiểm tra độc lập đoạn nguồn và đoạn đích trước khi sao chép. Cả hai đoạn đều phải đủ chỗ cho cùng `size` phần tử.

### Kiểm tra và trả lại chỉ số đã xác thực

Do các helper trả lại `index` hoặc `fromIndex`, có thể đưa chúng vào biểu thức trả về hoặc lời gọi tiếp theo. Tuy nhiên, trong phương thức phức tạp, gọi kiểm tra thành câu lệnh riêng thường giúp người đọc dễ nhận ra điều kiện hợp đồng hơn.

## 7. Xử lý null và loại ngoại lệ

Các phương thức `check...` chỉ nhận các giá trị số nguyên. Chúng không kiểm tra tham chiếu mảng hoặc collection mà bạn định truy cập.

Ví dụ:

```java
Objects.checkIndex(index, values.length);
```

Nếu `values` là `null`, biểu thức `values.length` gây `NullPointerException` trước khi `checkIndex` được gọi. Khi hợp đồng cần thông báo null rõ ràng, kiểm tra riêng:

```java
Objects.requireNonNull(values, "values");
Objects.checkIndex(index, values.length);
```

Phân biệt hai loại lỗi:

- `NullPointerException`: tham chiếu đầu vào bắt buộc khác null nhưng lại là null.
- `IndexOutOfBoundsException`: chỉ số hoặc đoạn số nguyên nằm ngoài miền hợp lệ.

Không nên bắt `IndexOutOfBoundsException` rồi tiếp tục truy cập bằng chỉ số ban đầu. Nếu đầu vào vi phạm hợp đồng, hãy để lỗi truyền ra hoặc chuyển đổi sang ngoại lệ miền nghiệp vụ ở ranh giới API khi hợp đồng công khai yêu cầu điều đó.

## 8. Ví dụ hoàn chỉnh chạy với Java 9 trở lên

Chương trình sau minh họa cả ba helper, đoạn rỗng, việc kiểm tra vùng nguồn/đích và trường hợp phép cộng có thể tràn `int`.

```java
import java.util.Arrays;
import java.util.Objects;

public class Main {
    static int getAt(int[] values, int index) {
        Objects.requireNonNull(values, "values");
        Objects.checkIndex(index, values.length);
        return values[index];
    }

    static int[] copyRange(int[] values, int fromIndex, int toIndex) {
        Objects.requireNonNull(values, "values");
        Objects.checkFromToIndex(fromIndex, toIndex, values.length);
        return Arrays.copyOfRange(values, fromIndex, toIndex);
    }

    static void copyInto(
            int[] source,
            int fromIndex,
            int size,
            int[] destination,
            int destinationIndex) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");
        Objects.checkFromIndexSize(fromIndex, size, source.length);
        Objects.checkFromIndexSize(destinationIndex, size, destination.length);
        System.arraycopy(source, fromIndex, destination, destinationIndex, size);
    }

    public static void main(String[] args) {
        int[] values = {10, 20, 30, 40};
        int[] destination = new int[4];

        System.out.println(getAt(values, 2));
        System.out.println(Arrays.toString(copyRange(values, 1, 3)));

        copyInto(values, 1, 2, destination, 1);
        System.out.println(Arrays.toString(destination));

        try {
            getAt(values, 4);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("index rejected");
        }

        try {
            copyRange(values, 3, 2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("range rejected");
        }

        try {
            copyInto(values, 3, 2, destination, 0);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("size rejected");
        }

        try {
            Objects.checkFromIndexSize(1_500_000_000, 1_000_000_000, Integer.MAX_VALUE);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("overflow-safe rejection");
        }
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 Main.java
java Main
```

Stdout chính xác:

```text
30
[20, 30]
[0, 20, 30, 0]
index rejected
range rejected
size rejected
overflow-safe rejection
```

Giải thích:

1. `getAt(values, 2)` đọc phần tử thứ ba, có giá trị `30`.
2. `copyRange(values, 1, 3)` lấy đoạn `[1, 3)`, tức hai phần tử `20` và `30`.
3. `copyInto` kiểm tra cả đoạn nguồn và đích trước khi sao chép; mảng đích trở thành `[0, 20, 30, 0]`.
4. Chỉ số `4` không hợp lệ với mảng có độ dài `4`.
5. Đoạn có `fromIndex = 3`, `toIndex = 2` sai thứ tự.
6. Đoạn bắt đầu ở `3` với kích thước `2` vượt quá mảng có độ dài `4`.
7. Trường hợp số nguyên lớn bị từ chối an toàn mà không cần cấp phát một mảng rất lớn.

## 9. Những giới hạn cần hiểu đúng

- Các helper xác thực giới hạn số nguyên; chúng không thực hiện thao tác đọc, ghi, cắt hoặc sao chép dữ liệu.
- Chúng không thay thế `Objects.requireNonNull` cho tham chiếu đầu vào.
- Việc kiểm tra chỉ số không bảo đảm đối tượng có thể truy cập vẫn giữ nguyên kích thước sau đó. Với cấu trúc dữ liệu mutable được chia sẻ giữa nhiều luồng, cần cơ chế đồng bộ hoặc thiết kế an toàn luồng riêng.
- Đối với API dùng `int` để biểu diễn chỉ số và độ dài, hãy dùng các overload `int` tương ứng để hợp đồng khớp với kiểu tham số.
- Không phụ thuộc vào nội dung thông báo lỗi cụ thể của `IndexOutOfBoundsException`; hãy kiểm tra loại ngoại lệ và điều kiện hợp lệ trong hợp đồng.
- Đừng tự tính `fromIndex + size` trước khi xác thực. Dùng `checkFromIndexSize` để tránh lỗi tràn số trong bước kiểm tra.

## 10. Lỗi thường gặp

1. **Dùng `index <= length`.** Chỉ số phần tử cuối cùng là `length - 1`; dùng `checkIndex` để kiểm tra đúng biên.
2. **Cho rằng `toIndex` là vị trí cuối được lấy.** `checkFromToIndex` dùng đoạn cuối loại trừ, vì vậy độ dài đoạn là `toIndex - fromIndex`.
3. **Từ chối đoạn rỗng.** `fromIndex == toIndex` hợp lệ nếu nằm trong giới hạn; đây là cách biểu diễn một đoạn không có phần tử.
4. **Dùng `fromIndex + size` để kiểm tra.** Phép cộng có thể tràn `int`; chọn `checkFromIndexSize`.
5. **Chỉ kiểm tra đoạn nguồn khi sao chép.** Đoạn đích cũng cần đủ chỗ; kiểm tra cả hai chiều trước khi thao tác.
6. **Quên kiểm tra null.** `values.length` trên tham chiếu null gây `NullPointerException` trước khi helper chạy; dùng `requireNonNull` khi cần hợp đồng rõ ràng.
7. **Nhầm loại ngoại lệ.** Vi phạm biên chỉ số gây `IndexOutOfBoundsException`; đầu vào null gây `NullPointerException`.
8. **Nghĩ helper bảo đảm an toàn khi có luồng khác thay đổi dữ liệu.** Helper chỉ kiểm tra giá trị tại thời điểm gọi; nó không khóa collection hoặc tạo giao dịch nguyên tử.

## 11. Ghi nhớ

1. Java 9 bổ sung ba helper kiểm tra chỉ số/phạm vi kiểu `int` trong `java.util.Objects`.
2. `checkIndex(index, length)` xác thực một phần tử với điều kiện `0 <= index < length`.
3. `checkFromToIndex(from, to, length)` xác thực đoạn nửa mở `[from, to)` với điều kiện `0 <= from <= to <= length`.
4. `checkFromIndexSize(from, size, length)` xác thực đoạn theo kích thước và tránh phép cộng có thể tràn.
5. Cả ba trả lại `index` hoặc `fromIndex` khi hợp lệ và ném `IndexOutOfBoundsException` khi sai.
6. Kiểm tra null riêng bằng `Objects.requireNonNull`.
7. Đặt kiểm tra tại ranh giới phương thức để hợp đồng đầu vào rõ ràng và dễ bảo trì.