# Giá trị đệm khi mảng kết quả dài hơn dữ liệu nguồn

## 1. Phần đệm xuất hiện để làm gì?

Khi yêu cầu một bản sao dài hơn phần dữ liệu có thể lấy từ nguồn, các phương thức `Arrays.copyOf` và `Arrays.copyOfRange` vẫn có thể tạo mảng với độ dài được yêu cầu. Những ô không có phần tử nguồn tương ứng được điền **giá trị đệm (padding)** theo kiểu phần tử.

Ví dụ, từ hai số `[6, 9]`, tạo bản sao dài 5 cho kết quả:

```text
Chỉ số kết quả:    0   1   2   3   4
Giá trị:          6   9   0   0   0
Nguồn dữ liệu:    sao chép | phần đệm
```

Phần đệm giúp đáp ứng hình dạng của kết quả, chẳng hạn một khối dữ liệu có độ dài cố định. Tuy nhiên, nó không tạo thêm dữ liệu nghiệp vụ. Ba số 0 ở cuối không tự có nghĩa là ba lần đo có giá trị bằng 0.

Bài này tập trung vào cách nhận biết, dự đoán và xử lý phần đệm. Các API được minh họa vẫn áp dụng trong Java hiện đại; chương trình chạy bằng Java 17+.

## 2. Giá trị được điền phụ thuộc vào kiểu phần tử

Các ô mới nhận giá trị mặc định tương ứng với kiểu phần tử của mảng:

| Mảng kết quả | Giá trị đệm | Điều không nên suy diễn |
| --- | --- | --- |
| `byte[]`, `short[]`, `int[]` | Số nguyên `0` | Không mặc nhiên là mã “không có dữ liệu” |
| `long[]` | `0L` | Không phải dấu thời gian đặc biệt do API chọn |
| `float[]` | `0.0f` | Không phải `NaN` |
| `double[]` | `0.0d` | Không phải giá trị trung bình hoặc nội suy |
| `boolean[]` | `false` | Không tự biểu thị “chưa xác định” |
| `char[]` | Ký tự mã 0, `'\u0000'` | Khác `'0'` và khác dấu cách |
| Mảng tham chiếu như `String[]`, `Integer[]`, `Object[]` | `null` | Không tự tạo một đối tượng mới |
| `int[][]` | `null` ở các ô mới của mảng ngoài | Không tự tạo một hàng `int[]` |

Đây là các giá trị khởi tạo mặc định của phần tử mảng Java, theo [JLS §4.12.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.5). Quy tắc đệm cụ thể của các phương thức sao chép được mô tả trong [tài liệu Arrays](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html).

Hai cặp dễ nhầm:

- `int[]` có phần đệm là số 0, nhưng `Integer[]` có phần đệm là `null`. Việc kiểu `Integer` có thể tự động mở hộp thành `int` không làm thay đổi quy tắc khởi tạo.
- `char[]` có ký tự mã 0, trong khi `Character[]` có `null` ở các ô đệm. Ký tự mã 0 có thể khó nhìn khi in trực tiếp, nên nên kiểm tra mã số của nó.

Mảng mới không chứa dữ liệu bộ nhớ chưa khởi tạo mà chương trình được phép đọc tùy ý. Các ô đệm có giá trị được xác định bởi ngôn ngữ và hợp đồng phương thức.

## 3. Ví dụ chạy đầy đủ với nhiều kiểu dữ liệu

Lưu thành `ArrayPaddingDefaultsDemo.java`:

```java
import java.util.Arrays;

public class ArrayPaddingDefaultsDemo {
    public static void main(String[] args) {
        int[] numbers = Arrays.copyOf(new int[] {6, 9}, 5);
        double[] prices = Arrays.copyOf(new double[] {2.5}, 3);
        boolean[] checks = Arrays.copyOf(new boolean[] {true}, 3);

        String[] names = Arrays.copyOf(new String[] {"Mai"}, 3);
        Integer[] boxed = Arrays.copyOf(new Integer[] {12}, 3);

        char[] letters = Arrays.copyOf(new char[] {'X'}, 3);
        int[][] rows = Arrays.copyOf(new int[][] {{7, 8}}, 3);

        System.out.println("int: " + Arrays.toString(numbers));
        System.out.println("double: " + Arrays.toString(prices));
        System.out.println("boolean: " + Arrays.toString(checks));
        System.out.println("String: " + Arrays.toString(names));
        System.out.println("Integer: " + Arrays.toString(boxed));

        System.out.println("char padding code: " + (int) letters[1]);
        System.out.println("char padding is digit zero: "
                + (letters[1] == '0'));
        System.out.println("nested arrays: " + Arrays.deepToString(rows));

        try {
            int value = boxed[1];
            System.out.println(value);
        } catch (NullPointerException e) {
            System.out.println("cannot unbox padding null");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac ArrayPaddingDefaultsDemo.java
java ArrayPaddingDefaultsDemo
```

Stdout:

```text
int: [6, 9, 0, 0, 0]
double: [2.5, 0.0, 0.0]
boolean: [true, false, false]
String: [Mai, null, null]
Integer: [12, null, null]
char padding code: 0
char padding is digit zero: false
nested arrays: [[7, 8], null, null]
cannot unbox padding null
```

Dòng `int value = boxed[1];` minh họa lỗi mở hộp tự động từ `null`. Trong mã ứng dụng, nên biết phạm vi dữ liệu hợp lệ hoặc kiểm tra `null` trước, thay vì dùng ngoại lệ như một vòng lặp xử lý thông thường.

Với `rows`, chỉ mảng ngoài dài thêm. Gọi `rows[1][0]` ngay lúc này sẽ gây `NullPointerException`, vì `rows[1]` chưa phải một mảng hàng.

## 4. Tính đúng phần đệm của copyOf

Với:

```java
int[] result = Arrays.copyOf(source, newLength);
```

Đây là đoạn minh họa, giả sử nguồn khác `null` và `newLength >= 0`.

Có thể tính:

```text
Số phần tử được sao chép = min(source.length, newLength)
Số ô đệm                = newLength - số phần tử được sao chép
Chỉ số bắt đầu phần đệm  = số phần tử được sao chép
```

Ví dụ, nguồn dài 2 và kết quả dài 5:

```text
Sao chép:  min(2, 5) = 2 phần tử
Phần đệm:  5 - 2 = 3 ô
Vị trí đệm trong kết quả: [2, 5)
```

Ký hiệu `[2, 5)` nghĩa là gồm chỉ số 2, 3, 4; không gồm chỉ số 5.

Nếu kết quả bằng hoặc ngắn hơn nguồn, không có phần đệm. Khi đó, phương thức chỉ giữ đủ số phần tử đầu cần thiết. Với một mảng nguồn rỗng hợp lệ và độ dài kết quả dương, toàn bộ kết quả là phần đệm.

Nguồn `null` khác với nguồn rỗng. Không thể dùng `copyOf` với nguồn `null` rồi mong phương thức tạo một mảng chỉ gồm giá trị mặc định; nguồn `null` là lỗi.

## 5. Tính đúng phần đệm của copyOfRange

`Arrays.copyOfRange(source, from, to)` yêu cầu một khoảng `[from, to)`:

- `from` được tính vào khoảng.
- `to` không được tính vào khoảng.
- Độ dài kết quả là `to - from`.
- `to` được phép lớn hơn độ dài nguồn, khi đó phần vượt đuôi được đệm.

Điểm quan trọng là độ dài kết quả được tính từ khoảng yêu cầu, không phải luôn bằng số phần tử thật có thể đọc. Xem [hợp đồng copyOfRange cho int[]](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#copyOfRange(int%5B%5D,int,int)).

Khi `0 <= from <= source.length`, `to >= from` và kích thước kết quả có thể cấp phát được:

```text
resultLength = to - from
available    = source.length - from
copiedCount  = min(available, resultLength)
paddingCount = resultLength - copiedCount
```

Ví dụ:

```text
source       = [10, 0, 30, 40, 50]
from         = 1
to           = 7

Khoảng muốn lấy:     [1, 7) -> dài 6
Dữ liệu thật còn có: [0, 30, 40, 50] -> 4 phần tử
Kết quả:            [0, 30, 40, 50, 0, 0]
Chỉ số đệm trong kết quả: 4 và 5
```

Số 0 ở đầu kết quả được sao chép từ nguồn. Hai số 0 cuối mới là phần đệm. Chỉ nhìn giá trị 0 không đủ phân biệt chúng.

### Các biên cần nhớ

| Điều kiện | Kết quả hoặc giới hạn |
| --- | --- |
| `from == source.length`, `to > from` | Không còn phần tử thật để lấy; toàn bộ kết quả là phần đệm |
| `from == to`, `from` nằm trong biên hợp lệ | Mảng kết quả rỗng |
| `from > source.length` | Không được phép bắt đầu hoàn toàn bên ngoài nguồn; ném `ArrayIndexOutOfBoundsException` |
| `from < 0` | Ném `ArrayIndexOutOfBoundsException`; không có đệm tự động ở phía trước |
| `from > to` | Khoảng không hợp lệ; ném `IllegalArgumentException` |
| Nguồn là `null` | Ném `NullPointerException` |

Các hàng lỗi ở trên minh họa từng điều kiện riêng. Không nên dựa vào thứ tự một triển khai chọn kiểm tra khi truyền đồng thời nhiều đối số sai.

## 6. Ví dụ chạy đầy đủ: giữ dữ liệu thật và đổi phần đệm

Nếu nghiệp vụ cần giá trị đệm khác mặc định, có thể sao chép trước rồi dùng `Arrays.fill` để thay **đúng các ô đệm**.

Lưu thành `ArrayRangePaddingDemo.java`:

```java
import java.util.Arrays;

public class ArrayRangePaddingDemo {
    public static void main(String[] args) {
        int[] source = {10, 0, 30, 40, 50};
        int from = 1;
        int to = 7;

        int[] result = Arrays.copyOfRange(source, from, to);
        int copiedCount = Math.min(source.length - from, result.length);

        System.out.println("copied count: " + copiedCount);
        System.out.println("default padding: " + Arrays.toString(result));

        // Chi thay phan dem, khong thay cac so 0 that trong du lieu.
        Arrays.fill(result, copiedCount, result.length, -1);
        System.out.println("custom padding: " + Arrays.toString(result));
        System.out.println("source unchanged: " + Arrays.toString(source));

        int[] allPadding =
                Arrays.copyOfRange(source, source.length, 8);
        System.out.println("all padding: " + Arrays.toString(allPadding));

        int[] empty =
                Arrays.copyOfRange(source, source.length, source.length);
        System.out.println("empty length: " + empty.length);

        try {
            Arrays.copyOfRange(source, source.length + 1, 8);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("start outside source rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac ArrayRangePaddingDemo.java
java ArrayRangePaddingDemo
```

Stdout:

```text
copied count: 4
default padding: [0, 30, 40, 50, 0, 0]
custom padding: [0, 30, 40, 50, -1, -1]
source unchanged: [10, 0, 30, 40, 50]
all padding: [0, 0, 0]
empty length: 0
start outside source rejected
```

`copiedCount` là chỉ số bắt đầu phần đệm **trong mảng kết quả**. Nó không phải luôn là `source.length`.

Trong ví dụ, nguồn dài 5 nhưng phần đệm của kết quả bắt đầu ở chỉ số 4. Nếu điền từ chỉ số 5, bạn sẽ bỏ sót một ô đệm.

Với `copyOf`, có thể dùng cùng nguyên tắc:

```java
int[] result = Arrays.copyOf(source, desiredLength);
int copiedCount = Math.min(source.length, result.length);
Arrays.fill(result, copiedCount, result.length, -1);
```

Đoạn này là mẫu thao tác, cần biến `source` và `desiredLength` hợp lệ trong chương trình.

Không dùng một vòng lặp thay **mọi** số 0 thành `-1`; việc đó phá dữ liệu thật nếu nguồn có số 0. Cũng không mặc nhiên coi `-1` là dấu hiệu thiếu dữ liệu trong mọi bài toán: giá trị này có thể là dữ liệu hợp lệ. Nếu cần phân biệt chắc chắn, hãy giữ riêng số phần tử thật hoặc thông tin đánh dấu hợp lệ.

## 7. Đệm mặc định không thay thế kiểm tra nghiệp vụ

### Kết quả dài hơn không có nghĩa dữ liệu nguồn đầy đủ

Giả sử một bản ghi cần đúng 16 byte nhưng nguồn chỉ có 10 byte. `Arrays.copyOf(source, 16)` tạo được mảng dài 16 với sáu byte 0 ở cuối. Nếu ứng dụng yêu cầu đủ 16 byte dữ liệu thật, việc kiểm tra chỉ `result.length == 16` sẽ bỏ sót lỗi thiếu đầu vào.

Có hai lựa chọn khác nhau:

- Nếu đầu vào bắt buộc đủ, kiểm tra độ dài trước và từ chối nguồn thiếu.
- Nếu định dạng cho phép đệm, thực hiện đệm theo quy tắc của định dạng và giữ thông tin về độ dài dữ liệu thật khi cần.

Không để tính tiện dụng của API quyết định thay yêu cầu nghiệp vụ.

### Phép tính trên toàn mảng có thể tính cả phần đệm

Ví dụ, hai phép đo `[4, 8]` được đệm thành `[4, 8, 0, 0, 0]`. Trung bình của hai phép đo thật là 6. Nếu chia tổng cho độ dài mảng mới, kết quả thành 2,4.

Cả năm ô đều là phần tử hợp lệ của mảng ở góc nhìn Java. Ngôn ngữ không tự biết ba ô cuối chỉ là phần đệm. Bên tính toán phải dùng phạm vi dữ liệu thật hoặc chính sách xử lý dữ liệu thiếu.

### null có thể là dữ liệu thật hoặc phần đệm

Nếu nguồn vốn có `null`, bản sao vẫn giữ `null` đó ở vị trí tương ứng. API không gắn thêm nhãn để phân biệt `null` được sao chép với `null` được đệm.

Ví dụ `["A", null]` sao chép lên độ dài 4 cho `["A", null, null, null]`. Có một `null` từ nguồn và hai `null` do đệm; giá trị đơn lẻ không mang thông tin nguồn gốc này.

## 8. Không áp dụng quy tắc đệm cho mọi thao tác sao chép

`System.arraycopy` nhận một mảng đích đã tồn tại và sao chép đúng số phần tử được yêu cầu. Nó không tự tạo một đoạn đệm để bù cho việc yêu cầu đọc vượt nguồn. Nếu phạm vi nguồn hoặc đích không hợp lệ, thao tác có thể bị từ chối theo hợp đồng kiểm tra biên.

Nếu bạn tạo `new int[10]` rồi chỉ chép ba phần tử vào đầu, những ô còn lại có thể vẫn là 0 vì chúng đã được khởi tạo khi tạo mảng. Điều đó khác với việc yêu cầu `arraycopy` sao chép mười phần tử từ nguồn chỉ có ba phần tử.

Hơn nữa, nếu mảng đích đã tồn tại và các ô ngoài đoạn được chép đã có giá trị khác 0, `arraycopy` không tự xóa chúng về mặc định. Xem [System.arraycopy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)).

Tương tự, chỉ truy cập `source[source.length]` không sinh giá trị đệm. Đó là truy cập vượt biên. Cơ chế đệm thuộc về hợp đồng của các phương thức sao chép cụ thể.

## 9. Cách dự đoán kết quả trước khi chạy

Với mỗi lời gọi sao chép, hãy trả lời lần lượt:

1. Mảng kết quả có kiểu phần tử gì?
2. Độ dài kết quả là bao nhiêu?
3. Phần nào của nguồn được chọn?
4. Có bao nhiêu phần tử nguồn thực sự được sao chép?
5. Các ô đệm bắt đầu ở chỉ số nào của kết quả?
6. Giá trị mặc định đó có được phép tham gia xử lý nghiệp vụ không?

Bài tự kiểm tra:

| Câu hỏi | Đáp án |
| --- | --- |
| Sao chép `byte[] {2, 3}` thành độ dài 4 | `[2, 3, 0, 0]` |
| Sao chép `Boolean[] {true}` thành độ dài 3 | `[true, null, null]` |
| `copyOfRange(new int[] {5, 7, 9}, 2, 5)` | `[9, 0, 0]` |
| `copyOfRange(new int[] {5, 7, 9}, 3, 5)` | `[0, 0]` |
| `copyOfRange(new int[] {5, 7, 9}, 4, 5)` | Lỗi vì vị trí bắt đầu vượt độ dài nguồn |
| Có thể phân biệt số 0 thật và số 0 đệm chỉ bằng giá trị không? | Không; cần biết ranh giới hoặc thông tin hợp lệ |
| Tăng `String[]` có gọi hàm khởi tạo `String` cho các ô mới không? | Không; các ô đệm nhận `null` |
