# Arrays.copyOf và thay đổi độ dài mảng

## 1. “Đổi độ dài” thực chất là thay mảng

Mảng Java có độ dài cố định sau khi được tạo. `Arrays.copyOf` không kéo giãn hay thu nhỏ chính đối tượng mảng đang có; nó tạo **một mảng mới**, sao chép phần dữ liệu phù hợp và trả về tham chiếu đến mảng mới.

Đây là công cụ hữu ích khi cần:

- Giữ một bản sao độc lập về các ô phần tử của mảng.
- Tạo mảng dài hơn để có thêm chỗ chứa.
- Lấy phần đầu của mảng bằng cách tạo bản sao ngắn hơn.
- Cắt bộ đệm xuống đúng số phần tử đã sử dụng trước khi trả kết quả.

Độ dài cố định là thuộc tính của đối tượng mảng, còn biến mảng chỉ giữ tham chiếu đến đối tượng đó. Phân biệt này được mô tả trong [JLS chương 10 về mảng](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html).

Các phương thức `Arrays.copyOf` có từ Java 6 và vẫn được sử dụng trong Java hiện đại. Các ví dụ dưới đây chạy bằng Java 17+.

## 2. Cú pháp và ba kết quả chính

Với mảng số nguyên:

```java
int[] copied = Arrays.copyOf(original, newLength);
```

Đây là đoạn cú pháp minh họa; trong chương trình cần `import java.util.Arrays;`, có mảng `original` và độ dài `newLength` hợp lệ.

`newLength` là **độ dài của mảng kết quả**, không phải số phần tử muốn thêm và cũng không phải chỉ số cuối.

Giả sử mảng nguồn là `[10, 20, 30]`:

| Lời gọi | Mảng kết quả | Điều xảy ra |
| --- | --- | --- |
| `Arrays.copyOf(source, 3)` | `[10, 20, 30]` | Tạo mảng mới cùng độ dài |
| `Arrays.copyOf(source, 5)` | `[10, 20, 30, 0, 0]` | Giữ phần đầu, bổ sung giá trị mặc định |
| `Arrays.copyOf(source, 2)` | `[10, 20]` | Giữ hai phần tử đầu, bỏ phần đuôi khỏi bản sao |
| `Arrays.copyOf(source, 0)` | `[]` | Tạo mảng rỗng hợp lệ |

Quy tắc có thể diễn đạt theo chỉ số:

- Mảng kết quả có đúng `newLength` phần tử.
- Các chỉ số từ `0` đến trước `min(source.length, newLength)` nhận giá trị tương ứng từ nguồn.
- Nếu kết quả dài hơn nguồn, các ô còn lại nhận giá trị mặc định.
- Mảng nguồn không bị thay đổi bởi chính thao tác sao chép.

Hợp đồng các biến thể cho kiểu nguyên thủy và kiểu tham chiếu được quy định trong [tài liệu Arrays.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#copyOf(int%5B%5D,int)).

### Phần tăng thêm chứa gì?

| Kiểu phần tử | Giá trị ở các ô mới |
| --- | --- |
| `byte`, `short`, `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `char` | Ký tự có mã 0, viết là `'\u0000'` |
| `boolean` | `false` |
| Kiểu tham chiếu như `String`, `Student`, `int[]` | `null` |

Đây là các giá trị mặc định của phần tử mảng Java, theo [JLS §4.12.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.12.5). Ký tự mã 0 không phải ký tự chữ số `'0'`, cũng không phải dấu cách.

Tăng độ dài `Student[]` không tự tạo thêm các đối tượng `Student`. Các ô mới chỉ có giá trị `null`; muốn sử dụng đối tượng phải khởi tạo chúng riêng.

## 3. Ví dụ chạy đầy đủ: giữ nguyên, tăng, giảm và gán lại

Lưu thành `CopyOfLengthDemo.java`:

```java
import java.util.Arrays;

public class CopyOfLengthDemo {
    public static void main(String[] args) {
        int[] source = {10, 20, 30};

        int[] sameLength = Arrays.copyOf(source, source.length);
        int[] longer = Arrays.copyOf(source, 5);
        int[] shorter = Arrays.copyOf(source, 2);
        int[] empty = Arrays.copyOf(source, 0);

        System.out.println("source: " + Arrays.toString(source));
        System.out.println("same: " + Arrays.toString(sameLength));
        System.out.println("same object: " + (source == sameLength));
        System.out.println("longer: " + Arrays.toString(longer));
        System.out.println("shorter: " + Arrays.toString(shorter));
        System.out.println("empty length: " + empty.length);

        sameLength[0] = 99;
        System.out.println("source after editing copy: "
                + Arrays.toString(source));

        int[] alias = source;
        source = Arrays.copyOf(source, 4);

        System.out.println("source length: " + source.length);
        System.out.println("alias length: " + alias.length);

        alias[1] = 77;
        System.out.println("source after editing old array: "
                + Arrays.toString(source));
        System.out.println("old array: " + Arrays.toString(alias));

        String[] names = Arrays.copyOf(new String[] {"An"}, 3);
        System.out.println("names: " + Arrays.toString(names));

        boolean[] flags = Arrays.copyOf(new boolean[] {true}, 3);
        System.out.println("flags: " + Arrays.toString(flags));
    }
}
```

Biên dịch và chạy:

```shell
javac CopyOfLengthDemo.java
java CopyOfLengthDemo
```

Stdout:

```text
source: [10, 20, 30]
same: [10, 20, 30]
same object: false
longer: [10, 20, 30, 0, 0]
shorter: [10, 20]
empty length: 0
source after editing copy: [10, 20, 30]
source length: 4
alias length: 3
source after editing old array: [10, 20, 30, 0]
old array: [10, 77, 30]
names: [An, null, null]
flags: [true, false, false]
```

Các điểm cần quan sát:

1. Sao chép cùng độ dài vẫn trả về một mảng mới. `source == sameLength` là `false`.
2. Đối với `int[]`, sửa một ô của bản sao không sửa ô tương ứng của nguồn.
3. Câu lệnh `source = Arrays.copyOf(source, 4)` đổi tham chiếu trong biến `source`.
4. Biến `alias` vẫn giữ mảng cũ dài 3; nó không tự chuyển sang mảng mới.
5. Mảng cũ còn được tham chiếu nên vẫn tồn tại và vẫn sửa được qua `alias`.

Có thể hình dung lần gán lại như sau:

```text
Trước khi gán lại:
source ----+
           +----> mảng cũ [10, 20, 30]
alias -----+

Sau source = Arrays.copyOf(source, 4):
source ---------> mảng mới [10, 20, 30, 0]
alias ----------> mảng cũ  [10, 20, 30]
```

Nếu chỉ gọi `Arrays.copyOf(source, 4);` rồi bỏ qua giá trị trả về, biến `source` vẫn trỏ tới mảng cũ. Phương thức không tự gán lại biến của bên gọi.

## 4. Giảm độ dài là cắt phần đuôi, không phải lưu rồi khôi phục

Với đoạn minh họa:

```java
int[] original = {10, 20, 30};
int[] shortened = Arrays.copyOf(original, 2);
int[] expandedAgain = Arrays.copyOf(shortened, 3);
```

Kết quả:

```text
original      = [10, 20, 30]
shortened     = [10, 20]
expandedAgain = [10, 20, 0]
```

Giá trị `30` không nằm trong `shortened`, nên mở rộng chính bản đó không thể lấy lại `30`. Phần mới được điền `0`.

Điều này không có nghĩa lời gọi đầu đã xóa `30` khỏi `original`. Mảng nguồn vẫn giữ dữ liệu. Nhưng nếu ứng dụng chỉ giữ lại bản đã cắt và không còn nguồn dữ liệu nào khác, phần bị bỏ không được `copyOf` lưu hộ.

Nếu muốn lấy một đoạn ở giữa, chẳng hạn từ chỉ số 1 đến trước chỉ số 3, `copyOf` không phải API thể hiện trực tiếp yêu cầu đó: nó luôn sao chép từ đầu. Khi ấy xem `Arrays.copyOfRange`.

## 5. Mảng tham chiếu: mảng mới, đối tượng bên trong có thể vẫn dùng chung

Với `int[]`, giá trị được sao chép là các số nguyên. Với `StringBuilder[]` hoặc `Student[]`, giá trị trong từng ô là **tham chiếu đến đối tượng**. `Arrays.copyOf` sao chép các tham chiếu này; nó không tự tạo bản sao của từng đối tượng.

Đây là **sao chép nông (shallow copy)**.

Lưu thành `CopyOfReferenceDemo.java`:

```java
import java.util.Arrays;

public class CopyOfReferenceDemo {
    public static void main(String[] args) {
        StringBuilder[] source = {new StringBuilder("A")};
        StringBuilder[] copied = Arrays.copyOf(source, 2);

        System.out.println("same array: " + (source == copied));
        System.out.println("same element: " + (source[0] == copied[0]));
        System.out.println("new slot is null: " + (copied[1] == null));

        copied[0].append("B");
        System.out.println("source element: " + source[0]);

        copied[0] = new StringBuilder("C");
        System.out.println("source after replacement: " + source[0]);
        System.out.println("copy after replacement: " + copied[0]);

        String[] names = {"An"};
        Object[] preservedType = Arrays.copyOf(names, 2);
        System.out.println("preserved String array: "
                + (preservedType.getClass() == String[].class));

        try {
            preservedType[1] = Integer.valueOf(7);
        } catch (ArrayStoreException e) {
            System.out.println("incompatible store rejected");
        }

        Object[] objectArray = Arrays.copyOf(names, 2, Object[].class);
        objectArray[1] = Integer.valueOf(7);
        System.out.println("explicit Object array: "
                + (objectArray.getClass() == Object[].class));
        System.out.println("object contents: "
                + Arrays.toString(objectArray));
    }
}
```

Biên dịch và chạy:

```shell
javac CopyOfReferenceDemo.java
java CopyOfReferenceDemo
```

Stdout:

```text
same array: false
same element: true
new slot is null: true
source element: AB
source after replacement: AB
copy after replacement: C
preserved String array: true
incompatible store rejected
explicit Object array: true
object contents: [An, 7]
```

Phân biệt hai kiểu sửa:

- `copied[0].append("B")` sửa đối tượng đang được hai mảng cùng tham chiếu, nên đọc qua `source[0]` cũng thấy `AB`.
- `copied[0] = new StringBuilder("C")` thay giá trị tham chiếu trong một ô của mảng mới. Ô `source[0]` không bị gán lại.

Với `String[]`, các chuỗi là đối tượng bất biến, nên không có thao tác sửa nội dung chuỗi tại chỗ như `StringBuilder.append`. Tuy vậy, cơ chế sao chép vẫn là sao chép tham chiếu.

### Mảng nhiều chiều cũng cần phân biệt lớp ngoài và lớp trong

Đoạn minh họa sau dùng `int[][]`:

```java
int[][] matrix = {{1, 2}, {3, 4}};
int[][] copied = Arrays.copyOf(matrix, 3);

copied[0][0] = 99;
```

Sau đoạn này:

- `copied` là một mảng ngoài mới, dài 3.
- `matrix[0]` và `copied[0]` vẫn cùng trỏ đến một mảng `int[]`, nên `matrix[0][0]` cũng là `99`.
- `copied[2]` là `null`, không phải một hàng mới chứa các số 0.

Nếu cần tách từng hàng, phải sao chép riêng các mảng hàng. Nếu hàng còn chứa các đối tượng có thể thay đổi, còn phải quyết định có sao chép những đối tượng đó hay không. `copyOf` không tự chọn một chính sách sao chép sâu cho nghiệp vụ.

## 6. Kiểu mảng lúc chạy và biến thể ba tham số

Phần cuối chương trình `CopyOfReferenceDemo` cho thấy kiểu của biến và kiểu thật của đối tượng mảng có thể khác nhau.

Với biến thể hai tham số cho mảng tham chiếu:

```java
String[] names = {"An"};
Object[] copied = Arrays.copyOf(names, 2);
```

Biến `copied` có kiểu khai báo `Object[]`, nhưng đối tượng được tạo vẫn là `String[]`. Vì vậy, gán một `Integer` vào mảng này sẽ bị kiểm tra và từ chối lúc chạy bằng `ArrayStoreException`.

Nếu chủ đích cần mảng `Object[]`, có thể chỉ rõ kiểu mảng kết quả:

```java
Object[] copied = Arrays.copyOf(names, 2, Object[].class);
```

Tham số thứ ba là **kiểu mảng**, chẳng hạn `Object[].class` hoặc `String[].class`, không phải `Object.class` hay `String.class`.

Biến thể này không chuyển đổi giá trị của từng phần tử. Ví dụ:

```java
Number[] values = {Integer.valueOf(1), Double.valueOf(2.5)};
Integer[] integers = Arrays.copyOf(values, 2, Integer[].class);
```

Đoạn minh họa này ném `ArrayStoreException`: `Double` được sao chép không tương thích với ô `Integer`. Nó không tự đổi `2.5` thành `2`. Chỉ các phần tử thực sự cần sao chép mới phải lưu được trong kiểu mảng đích.

Tương tự, `Arrays.copyOf(intArray, length)` vẫn trả về `int[]`; phương thức không phải công cụ tự chuyển `int[]` thành `long[]` hay tự đóng hộp thành `Integer[]`.

## 7. Dùng để cắt bộ đệm theo số phần tử thực tế

Trong xử lý dữ liệu, độ dài mảng có thể biểu diễn **sức chứa**, còn một biến khác biểu diễn **số phần tử đã dùng**.

Đoạn minh họa:

```java
int[] buffer = new int[8];
int size = 0;

buffer[size++] = 42;
buffer[size++] = 0;
buffer[size++] = 17;

int[] result = Arrays.copyOf(buffer, size);
```

`buffer.length` là 8, nhưng `size` là 3. Mảng `result` là `[42, 0, 17]`, dài đúng 3.

Không suy ra số phần tử đã dùng bằng cách đếm các giá trị khác 0. Trong ví dụ, số 0 là dữ liệu thật. `Arrays.copyOf` cũng không tự biết ý nghĩa của `size`; bên gọi phải truyền đúng độ dài cần giữ.

Nếu truyền `buffer.length` thay vì `size`, kết quả giữ cả phần sức chứa chưa sử dụng. Với dữ liệu tham chiếu, lỗi tương tự có thể đưa thêm nhiều `null` vào kết quả.

### Khi thêm nhiều phần tử

Có thể dùng `copyOf` để mở rộng mảng khi hết sức chứa. Nhưng nếu cứ thêm một phần tử lại tạo bản sao dài hơn đúng 1 ô, để xây dựng n phần tử sẽ phải sao chép tổng cộng:

```text
0 + 1 + 2 + ... + (n - 1)
```

Lượng sao chép tăng theo bậc hai, O(n²). Đây là hệ quả của cách sử dụng, không phải điều bắt buộc khi dùng `copyOf`.

Khi dữ liệu tăng nhiều lần, nên dùng cấu trúc quản lý sức chứa phù hợp, chẳng hạn `ArrayList` cho phần tử tham chiếu, hoặc một chiến lược mở rộng sức chứa theo từng đợt cho mảng nguyên thủy. Vẫn có thể dùng `copyOf` một lần ở cuối để cắt về kích thước thực tế.

Mỗi lần sao chép cần có mảng mới. Trong lúc chuyển từ mảng cũ sang mảng mới, cả hai có thể cùng tồn tại; chi phí bộ nhớ không chỉ là phần chênh lệch độ dài.

## 8. Ngoại lệ và lỗi sử dụng thường gặp

| Trường hợp | Điều cần hiểu |
| --- | --- |
| `newLength < 0` | Ném `NegativeArraySizeException` |
| Mảng nguồn là `null` | Ném `NullPointerException`, kể cả khi muốn độ dài 0 |
| `newLength == 0`, nguồn hợp lệ | Tạo mảng rỗng hợp lệ |
| `newLength > source.length` | Hợp lệ; không phải lỗi vượt chỉ số, phần dư được điền mặc định |
| Kiểu đích ba tham số không chứa được phần tử cần sao chép | Ném `ArrayStoreException` |
| Độ dài quá lớn hoặc không đủ bộ nhớ cấp phát | Không bảo đảm tạo được mảng; có thể gặp `OutOfMemoryError` |

Một số lỗi khác:

- **Nhầm độ dài mới với phần tăng thêm.** Muốn từ 3 lên 5 thì truyền `5`, không phải `2`.
- **Bỏ qua kết quả trả về.** Mảng nguồn không tự đổi độ dài.
- **Gán lại tham số bên trong phương thức rồi mong biến bên gọi đổi theo.** Java truyền giá trị tham chiếu; nếu phương thức tạo mảng mới thì nên trả mảng đó về và để bên gọi nhận lại.
- **Cho rằng sao chép nông đã tách mọi dữ liệu.** Phải xét các đối tượng và mảng con vẫn được dùng chung.
- **Dùng `==` để kiểm tra nội dung.** `==` kiểm tra hai tham chiếu có trỏ cùng đối tượng mảng không. Với mảng một chiều, dùng `Arrays.equals` khi muốn so sánh các giá trị phần tử.
- **In trực tiếp mảng rồi khó đọc nội dung.** Dùng `Arrays.toString` cho mảng một chiều; với mảng lồng, có thể dùng `Arrays.deepToString`.

## 9. Chọn đúng thao tác sao chép

| Nhu cầu | Công cụ thường phù hợp |
| --- | --- |
| Mảng mới từ phần đầu nguồn, có thể đổi độ dài | `Arrays.copyOf` |
| Mảng mới từ một đoạn bắt đầu ở vị trí khác 0 | `Arrays.copyOfRange` |
| Bản sao mới cùng độ dài, cùng kiểu mảng | `clone()` hoặc `Arrays.copyOf(source, source.length)` |
| Sao chép vào mảng đích đã tồn tại, có vị trí nguồn/đích cụ thể | `System.arraycopy` |
| Tạo bản sao các đối tượng có thể thay đổi bên trong | Tự định nghĩa cách sao chép đối tượng; một lần sao chép mảng ngoài chưa đủ |

Các công cụ trên có phạm vi và cách xử lý chỉ số khác nhau. Với bài toán đơn giản “giữ phần đầu và tạo mảng dài N”, `Arrays.copyOf` thể hiện ý định trực tiếp.

## 10. Tự kiểm tra

1. `Arrays.copyOf(new int[] {4, 5}, 4)` cho gì? **`[4, 5, 0, 0]`.**
2. `Arrays.copyOf(new String[] {"A", "B"}, 3)` có tạo chuỗi rỗng ở ô cuối không? **Không; ô cuối là `null`.**
3. Sao chép cùng độ dài có trả về chính mảng nguồn không? **Không; đó là một mảng mới.**
4. Cắt `[4, 5, 6]` xuống độ dài 1 rồi mở rộng bản đã cắt lên 3 cho gì? **`[4, 0, 0]`; hai giá trị đã bị bỏ không tự khôi phục.**
5. Sao chép `Student[]` có tự tạo các `Student` mới không? **Không; các ô tương ứng ban đầu giữ cùng tham chiếu đối tượng.**
6. Gán mảng sao chép từ `String[]` vào biến `Object[]` có mặc nhiên cho phép thêm mọi đối tượng không? **Không; với biến thể hai tham số, kiểu mảng lúc chạy vẫn là `String[]`.**
