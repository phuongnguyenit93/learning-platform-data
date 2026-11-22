# Phân biệt mảng null và phần tử null trong varargs

## 1. Hai tầng tham chiếu cần phân biệt

Với khai báo `void inspect(String... values)`, tham số `values` có kiểu mảng `String[]` trong thân phương thức. Vì vậy, có hai câu hỏi độc lập:

1. Biến `values` có tham chiếu tới một đối tượng mảng không?
2. Nếu có mảng, mỗi vị trí trong mảng đang chứa tham chiếu tới chuỗi hay chứa `null`?

**Mảng null** nghĩa là không có đối tượng mảng tại tham chiếu đang xét: `values == null`. **Phần tử null** nghĩa là mảng tồn tại nhưng một vị trí chứa `null`: chẳng hạn `values != null && values[0] == null`, với điều kiện mảng có ít nhất một phần tử.

Mảng rỗng là trạng thái thứ ba: đối tượng mảng tồn tại, có `length == 0`, không có phần tử nào để truy cập. Không truyền đối số varargs tạo ra trường hợp này; nó không có nghĩa là truyền mảng null.

```text
Mảng null:
values ──> null

Mảng rỗng:
values ──> []                  length = 0

Mảng có một phần tử null:
values ──> [null]              length = 1
```

Phân biệt đúng ba trạng thái giúp đọc lời gọi phương thức, đặt quy ước cho API và xác định vị trí thực sự có thể phát sinh `NullPointerException`. Các quy tắc này vẫn áp dụng trên Java hiện hành; bài sử dụng mã Java 17+.

## 2. Vì sao một lời gọi varargs có thể tạo ba trạng thái?

Đối với một phương thức đơn lẻ nhận `String...`, hãy tách hai cách gọi:

- Truyền một biểu thức có kiểu tương thích với `String[]`: biểu thức có thể được dùng trực tiếp làm đối số mảng, kể cả khi giá trị của nó là `null`.
- Truyền các đối số phần tử: trình biên dịch tạo một mảng để chứa các đối số đó. Không truyền phần tử nào thì mảng được tạo có độ dài 0.

Khai báo tham số varargs và cơ chế tạo mảng khi lời gọi cần số lượng đối số biến đổi được mô tả trong [JLS §8.4.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.1) và [JLS §15.12.4.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.4.2).

Bảng sau giả định chỉ có phương thức `inspect(String... values)`, không có overload khác:

| Lời gọi | Giá trị tham số `values` nhận được | Độ dài |
|---|---|---:|
| `inspect()` | Mảng rỗng, khác `null` | 0 |
| `inspect((String[]) null)` | Tham chiếu mảng `null` | Không thể đọc |
| `inspect((String) null)` | Mảng chứa một phần tử `null` | 1 |
| `inspect(new String[] {null})` | Chính mảng được truyền vào | 1 |
| `inspect("A", null)` | Mảng chứa `"A"` và `null` | 2 |
| `inspect(new String[2])` | Mảng gồm hai phần tử `null` | 2 |

Điểm quyết định là **kiểu của biểu thức đối số tại lúc biên dịch**, không chỉ là giá trị `null` tại lúc chạy. Ép kiểu `(String[]) null` nói rằng đối số là một mảng. Ép kiểu `(String) null` nói rằng đối số là một phần tử chuỗi, từ đó cần một mảng chứa phần tử ấy. Không trường hợp nào trong hai phép ép kiểu này tạo đối tượng chuỗi.

### Lời gọi chỉ viết null có nghĩa gì?

Với phương thức duy nhất `inspect(String... values)`, lời gọi:

```java
inspect(null);
```

truyền `null` như đối số mảng; nó **không tự tạo mảng một phần tử null**. `javac` thường cảnh báo tại lời gọi này và gợi ý ép kiểu để làm rõ ý định. Đây không phải lỗi biên dịch chỉ vì có `null`; cũng không tự động phát sinh ngoại lệ trước khi vào thân phương thức.

Để mã thể hiện rõ yêu cầu, nên viết một trong hai cách:

```java
inspect((String[]) null); // Không có mảng.
inspect((String) null);   // Có mảng chứa một phần tử null.
```

Nếu có các overload khác, cần xét lại việc chọn phương thức; lời gọi `null` có thể chọn overload khác hoặc trở nên mơ hồ. Không dùng kết luận của ví dụ một phương thức để suy diễn cho mọi tập overload.

### Biến mảng null vẫn là đối số mảng

```java
String[] values = null;
inspect(values);
```

Trong đoạn minh họa trên, `values` có kiểu tĩnh `String[]`; phương thức nhận tham chiếu null. Java không đóng gói biến đó thành một phần tử `String`, vì bản thân mảng không phải một chuỗi.

Ngược lại:

```java
String value = null;
inspect(value);
```

Biến `value` có kiểu `String`; lời gọi tạo mảng một phần tử để truyền cho phương thức. Hai biến cùng chứa giá trị `null` nhưng thể hiện hai ý nghĩa khác nhau qua kiểu của chúng.

## 3. Chương trình kiểm chứng đầy đủ

Lưu tệp dưới tên `NullVarargsDemo.java`:

```java
public class NullVarargsDemo {
    static void inspect(String label, String... values) {
        if (values == null) {
            System.out.println(label + ": null-array");
            return;
        }
        int nullCount = 0;
        for (String value : values) {
            if (value == null) {
                nullCount++;
            }
        }
        System.out.println(label + ": length=" + values.length
                + ", nulls=" + nullCount);
    }

    static void inspectObjects(Object... values) {
        System.out.println("Object...: length=" + values.length
                + ", firstIsArray=" + (values[0] instanceof String[]));
    }

    static int sum(int... values) {
        int result = 0;
        for (int value : values) {
            result += value;
        }
        return result;
    }

    static int sumBoxed(Integer... values) {
        int result = 0;
        for (Integer value : values) {
            result += value;
        }
        return result;
    }

    public static void main(String[] args) {
        inspect("no arguments");
        inspect("null array", (String[]) null);
        inspect("one null", (String) null);
        inspect("explicit element", new String[] {null});
        inspect("two elements", "A", null);
        String[] absent = null;
        String[] present = {null};
        inspect("array variable null", absent);
        inspect("array variable present", present);
        inspect("array of size 2", new String[2]);
        inspectObjects((Object) new String[] {null});
        System.out.println("empty primitive sum=" + sum());
        System.out.println("primitive sum=" + sum(2, 3));
        try {
            sumBoxed((Integer) null);
        } catch (NullPointerException ex) {
            System.out.println("boxed sum: NullPointerException");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -Xlint:all NullVarargsDemo.java
java NullVarargsDemo
```

Kết quả chuẩn:

```text
no arguments: length=0, nulls=0
null array: null-array
one null: length=1, nulls=1
explicit element: length=1, nulls=1
two elements: length=2, nulls=1
array variable null: null-array
array variable present: length=1, nulls=1
array of size 2: length=2, nulls=2
Object...: length=1, firstIsArray=true
empty primitive sum=0
primitive sum=5
boxed sum: NullPointerException
```

Đọc kết quả theo từng nhóm:

- `no arguments` nhận một mảng tồn tại nhưng rỗng. Kiểm tra mảng null không được dùng thay cho kiểm tra mảng rỗng.
- `null array` và `array variable null` đều không có đối tượng mảng để duyệt.
- `one null` và `explicit element` đều có mảng độ dài 1. Với mảng được truyền trực tiếp, phương thức nhận chính tham chiếu mảng đó.
- `new String[2]` tạo một mảng hợp lệ; các phần tử kiểu tham chiếu được khởi tạo mặc định bằng `null`.
- `inspectObjects((Object) new String[] {null})` nhận mảng `Object[]` một phần tử, trong đó phần tử ấy là đối tượng `String[]`. Phép ép kiểu thành `Object` khiến toàn bộ mảng nguồn được xem là một phần tử.
- `sumBoxed((Integer) null)` có mảng tồn tại, nhưng phép cộng yêu cầu mở hộp phần tử `Integer` null thành `int`, nên phát sinh `NullPointerException`.

Hàm `inspect` kiểm tra mảng trước, rồi chỉ kiểm đếm phần tử null. Nhờ vậy, chương trình quan sát được dữ liệu mà không vô tình gọi phương thức trên một phần tử null.

## 4. Xác định đúng chỗ có thể phát sinh ngoại lệ

Các đoạn dưới đây minh họa riêng từng tình huống, không phải một tệp chương trình độc lập.

### Mảng null: không thể đọc length hay duyệt

```java
String[] values = null;
// System.out.println(values.length); // Gây NullPointerException.
// for (String value : values) { } // Duyệt mảng cũng sẽ gây NullPointerException.
```

`values.length` cần truy cập đối tượng mảng. Vòng `for` nâng cao trên mảng cũng cần mảng để thực hiện quá trình duyệt. Varargs không tự chặn đối số mảng null; thân phương thức phải xử lý theo quy ước của API.

### Mảng tồn tại nhưng phần tử null: length vẫn hợp lệ

```java
String[] values = {null};
System.out.println(values.length);  // 1
System.out.println(values[0] == null); // true
// values[0].length();              // Gây NullPointerException.
```

Truy cập `values[0]` hợp lệ và trả về `null`. Ngoại lệ chỉ phát sinh khi tiếp tục sử dụng tham chiếu null theo cách cần một đối tượng, ví dụ gọi `length()` trên phần tử chuỗi đó.

### Mảng rỗng: truy cập phần tử là lỗi chỉ số

```java
String[] values = {};
System.out.println(values.length); // 0
// System.out.println(values[0]); // Gây ArrayIndexOutOfBoundsException.
```

Với mảng rỗng khác null, vấn đề là không có chỉ số 0 hợp lệ. Vì vậy:

- `values != null` chưa đủ để truy cập `values[0]`.
- `values.length > 0` chỉ được đánh giá sau khi chắc chắn `values != null`.
- Có phần tử tại chỉ số 0 chưa bảo đảm phần tử ấy khác null.

Khi thật sự cần đọc độ dài chuỗi đầu tiên, thứ tự kiểm tra có thể là:

```java
if (values != null && values.length > 0 && values[0] != null) {
    System.out.println(values[0].length());
}
```

Các toán hạng của `&&` được xét từ trái sang phải và dừng khi gặp `false`, nên mỗi điều kiện bảo vệ thao tác tiếp theo.

## 5. Thiết kế quy ước null cho phương thức varargs

Không có một quy ước null duy nhất cho mọi phương thức. Hãy xác định riêng cả **mảng đầu vào** lẫn **từng phần tử**, rồi ghi rõ trong tài liệu API.

Ví dụ một phương thức đếm nhãn có thể quy định:

- Mảng null là dữ liệu đầu vào không hợp lệ.
- Mảng rỗng hợp lệ và trả về 0.
- Phần tử null không hợp lệ.
- Chuỗi rỗng vẫn là một chuỗi; có cấm chuỗi rỗng hay không là quy tắc nghiệp vụ riêng.

Đoạn sau là phần khai báo phương thức đặt trong một lớp; cần thêm `import java.util.Objects;` ở đầu tệp:

```java
static int countLabels(String... labels) {
    Objects.requireNonNull(labels, "labels must not be null");
    for (int i = 0; i < labels.length; i++) {
        Objects.requireNonNull(labels[i], "labels[" + i + "] must not be null");
    }
    return labels.length;
}
```

Với quy ước này:

| Lời gọi | Kết quả |
|---|---|
| `countLabels()` | Trả về 0 |
| `countLabels("A", "B")` | Trả về 2 |
| `countLabels((String[]) null)` | Ném `NullPointerException` với thông báo về mảng |
| `countLabels((String) null)` | Ném `NullPointerException` với thông báo về phần tử 0 |

`Objects.requireNonNull(labels)` chỉ kiểm tra tham chiếu mảng; nó không duyệt và kiểm tra từng phần tử. Nếu nghiệp vụ cho phép phần tử null, thay vì ném ngoại lệ có thể quy định rõ rằng phần tử đó bị bỏ qua hoặc được giữ làm dấu hiệu “thiếu dữ liệu”.

Cũng có API coi mảng null giống mảng rỗng. Chỉ chuẩn hóa như vậy khi hợp đồng thực sự cho phép, vì thao tác này xóa sự khác biệt giữa “không cung cấp mảng” và “cung cấp danh sách không có phần tử”. Không tự thay null bằng mảng rỗng chỉ để che lỗi gọi phương thức.

## 6. Varargs kiểu nguyên thủy và kiểu bao

Với `int... values`, tham số có kiểu `int[]`:

- `sum()` nhận mảng rỗng.
- `sum((int[]) null)` có thể truyền mảng null.
- `new int[2]` chứa hai giá trị 0, không chứa null.
- `new int[] {null}` không biên dịch vì null không phải giá trị của `int`.

Với `Integer... values`, tham số có kiểu `Integer[]`, nên cả mảng null lẫn phần tử null đều có thể xuất hiện. Nếu phép tính cần chuyển phần tử `Integer` thành `int`, phần tử null gây lỗi mở hộp như chương trình kiểm chứng đã cho thấy.

Một tình huống khác là truyền biến `Integer` null vào `int...`:

```java
Integer number = null;
// sum(number); // Phải mở hộp number; NullPointerException xảy ra trước khi vào sum.
```

Đừng chỉ kiểm tra null trong thân `sum` rồi cho rằng đã xử lý được mọi trường hợp: ở lời gọi này, việc tạo giá trị phần tử nguyên thủy đã thất bại trước khi phương thức bắt đầu chạy.

## 7. Lỗi suy luận thường gặp

| Suy luận sai | Cách hiểu đúng |
|---|---|
| Không truyền đối số nghĩa là tham số null | Lời gọi varargs không có phần tử nhận mảng rỗng |
| `inspect(null)` luôn là một phần tử null | Với phương thức `String...` duy nhất, null được dùng làm mảng; ép kiểu để thể hiện rõ ý định |
| Mảng có null nghĩa là bản thân mảng null | Mảng có thể tồn tại và chứa một hoặc nhiều phần tử null |
| Kiểm tra `values != null` đã đủ an toàn | Còn phải xét chỉ số hợp lệ và phần tử có null hay không |
| Khai báo varargs cấm null | Varargs hỗ trợ cách truyền đối số; tính hợp lệ của null do hợp đồng phương thức quyết định |
| `int...` và `Integer...` xử lý null giống nhau | Mảng `int[]` không chứa null; `Integer[]` có thể chứa null và gây lỗi khi mở hộp |

## 8. Thực hành đọc lời gọi

Giả sử chỉ có phương thức `inspect(String... values)`. Trước khi chạy, hãy dự đoán mảng null hay mảng tồn tại, số phần tử và số phần tử null:

```java
inspect(new String[0]);
inspect((String[]) null);
inspect((String) null);
inspect(null, null);
inspect(new String[] {"", null});
```

Đáp án:

1. Mảng tồn tại, độ dài 0, không có phần tử null.
2. Mảng null; không thể đọc độ dài.
3. Mảng tồn tại, độ dài 1, có một phần tử null.
4. Mảng tồn tại, độ dài 2, cả hai phần tử đều null.
5. Mảng tồn tại, độ dài 2, có một phần tử null. Chuỗi rỗng `""` vẫn là một đối tượng chuỗi hợp lệ.

Khi phân tích một lời gọi, hãy đi theo thứ tự: **kiểu đối số → dùng trực tiếp mảng hay tạo mảng phần tử → mảng có tồn tại không → phần tử có tồn tại không → hợp đồng của phương thức cho phép những gì**. Trình tự này giúp phân biệt lỗi truyền mảng, lỗi xử lý phần tử và lỗi mở hộp.
