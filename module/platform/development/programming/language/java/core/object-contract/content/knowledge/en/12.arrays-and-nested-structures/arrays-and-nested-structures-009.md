# Kiểm tra `null`, mảng rỗng và phần tử mảng `null` trong Java

Khi thiết kế `equals()`/`hashCode()` cho đối tượng chứa mảng hoặc cấu trúc lồng nhau, ba trạng thái dễ bị nhầm lẫn là **mảng `null`**, **mảng rỗng**, và **mảng có phần tử `null`**. Chúng có ý nghĩa khác nhau và thường dẫn tới kết quả bằng nhau, mã băm hoặc ngoại lệ khác nhau. Việc chọn `Arrays.equals()`, `Arrays.deepEquals()` và hàm hash tương ứng cần bám sát cấu trúc thực tế của dữ liệu.

Ví dụ:

```java
String[] missing = null;           // Không có đối tượng mảng.
String[] empty = {};               // Có mảng, độ dài 0.
String[] oneNull = { null };       // Có mảng, độ dài 1; phần tử 0 là null.
String[] oneEmpty = { "" };        // Có mảng, độ dài 1; phần tử 0 là chuỗi rỗng.
```

Bốn trạng thái này **không đồng nghĩa**. Đặc biệt, `null` của cả biến mảng khác với `null` ở một vị trí **bên trong mảng**.

## 1. Phân biệt bằng thuộc tính và ý nghĩa nghiệp vụ

| Trạng thái | Ví dụ | `array == null` | `array.length` | Diễn giải phổ biến |
| --- | --- | --- | --- | --- |
| Mảng `null` | `String[] a = null;` | `true` | Ném `NullPointerException` nếu truy cập | Chưa có dữ liệu, không được cung cấp hoặc vắng mặt |
| Mảng rỗng | `String[] a = {};` | `false` | `0` | Dữ liệu được cung cấp, nhưng không có phần tử |
| Mảng chứa `null` | `String[] a = {null};` | `false` | `1` | Có một vị trí chưa có giá trị |
| Mảng chứa chuỗi rỗng | `String[] a = {""};` | `false` | `1` | Có một giá trị `String` thật, dài 0 |

Trong API nhận danh sách các lựa chọn, `null` có thể nghĩa là “không chỉ định”; `[]` có thể nghĩa là “đã chỉ định nhưng không chọn gì”; `[null]` có thể bị xem là dữ liệu không hợp lệ hoặc có thể là một vị trí trống hợp lệ. **Ý nghĩa chính xác do hợp đồng API quyết định**, không tự suy luận mọi trạng thái về cùng một giá trị.

Mảng nguyên thủy như `int[]` **không thể chứa phần tử `null`**. Ví dụ `int[] a = {null};` không biên dịch. Tuy nhiên, `int[] a` vẫn có thể là `null`, và mảng nhiều chiều `int[][]` có thể chứa **hàng `int[]` bằng `null`**, vì các hàng đó là tham chiếu.

## 2. Kiểm tra an toàn trước khi truy cập

Truy cập `array.length`, `array[0]` hoặc duyệt bằng vòng `for` sẽ ném `NullPointerException` nếu chính mảng là `null`. Với mảng không `null` nhưng rỗng, `array[0]` lại ném `ArrayIndexOutOfBoundsException`.

```java
static boolean hasFirstNonNull(String[] values) {
    return values != null
            && values.length > 0
            && values[0] != null;
}
```

Đây là **mảnh phương thức minh họa**, không phải chương trình độc lập. Nhờ toán tử `&&` tính ngắn mạch, điều kiện bên phải không được tính nếu điều kiện bên trái sai; vì vậy có thể kiểm tra mảng, độ dài rồi phần tử theo đúng thứ tự.

Nếu yêu cầu là không được xuất hiện phần tử `null` trong toàn bộ mảng, kiểm tra từng phần tử, sau khi xử lý mảng `null` theo chính sách đã định:

```java
static boolean hasNoNullElement(String[] values) {
    if (values == null) {
        return false;
    }
    for (String value : values) {
        if (value == null) {
            return false;
        }
    }
    return true;
}
```

Đoạn này chấp nhận mảng rỗng vì không có phần tử nào vi phạm; nếu nghiệp vụ bắt buộc **ít nhất một phần tử**, hãy kiểm tra thêm `values.length > 0`.

`Objects.requireNonNull(values, "values")` phù hợp khi API cấm mảng `null`; nó ném ngoại lệ ngay tại ranh giới nhận dữ liệu, giúp phát hiện sai sót sớm. Nếu cả mảng và phần tử đều bắt buộc không null, phải kiểm tra **cả hai cấp**: `requireNonNull` trên biến mảng không tự kiểm tra phần tử.

## 3. `Arrays.equals()` phân biệt ba trạng thái thế nào?

Dùng `java.util.Arrays.equals(...)` để so sánh **nội dung của mảng một chiều** thay vì toán tử `==` hay `array.equals(other)`.

Các quy tắc chính:

1. Hai biến mảng đều `null` được `Arrays.equals()` xem là bằng nhau.
2. Một mảng `null` và một mảng rỗng là **khác nhau**.
3. Hai mảng rỗng cùng kiểu tương ứng bằng nhau về nội dung dù khác tham chiếu.
4. Hai mảng cùng độ dài được so sánh theo **từng vị trí**.
5. Với mảng tham chiếu như `String[]`, hai phần tử cùng `null` ở cùng vị trí là bằng nhau; một `null` và một `String` không null là khác nhau; hai phần tử không null được so sánh bằng `equals()` tương ứng.
6. Với mảng nguyên thủy như `int[]`, mỗi giá trị nguyên thủy được so sánh theo quy tắc của overload tương ứng, không có phần tử null.

### 3.1. Ví dụ Java 17+ chạy được

Lưu thành **`NullArrayDemo.java`**:

```java
import java.util.Arrays;

public class NullArrayDemo {
    public static void main(String[] args) {
        String[] missing = null;
        String[] empty = {};
        String[] oneNull = {null};
        String[] anotherNull = {null};
        String[] oneEmpty = {""};

        System.out.println("missing is null: "
                + (missing == null));
        System.out.println("empty length: " + empty.length);
        System.out.println("oneNull length: " + oneNull.length);

        System.out.println("null vs null: "
                + Arrays.equals(missing, (String[]) null));
        System.out.println("null vs empty: "
                + Arrays.equals(missing, empty));
        System.out.println("empty vs empty: "
                + Arrays.equals(empty, new String[0]));
        System.out.println("null-element vs null-element: "
                + Arrays.equals(oneNull, anotherNull));
        System.out.println("null-element vs empty: "
                + Arrays.equals(oneNull, empty));
        System.out.println("null-element vs empty-string: "
                + Arrays.equals(oneNull, oneEmpty));

        System.out.println("hash null array: "
                + Arrays.hashCode(missing));
        System.out.println("hash empty array: "
                + Arrays.hashCode(empty));
        System.out.println("hash [null]: "
                + Arrays.hashCode(oneNull));
    }
}
```

Biên dịch/chạy:

```bash
javac NullArrayDemo.java
java NullArrayDemo
```

Stdout:

```text
missing is null: true
empty length: 0
oneNull length: 1
null vs null: true
null vs empty: false
empty vs empty: true
null-element vs null-element: true
null-element vs empty: false
null-element vs empty-string: false
hash null array: 0
hash empty array: 1
hash [null]: 31
```

`Arrays.hashCode((Object[]) null)` trả `0`; mảng rỗng có mã băm `1`; mảng đối tượng một phần tử `null` có mã băm `31` vì quy tắc tích lũy bắt đầu từ `1`, sau đó lấy `31 * 1 + 0`. Các giá trị trên xác định bởi `Arrays.hashCode()` với mảng tham chiếu đang minh họa; chúng **không phải mã định danh duy nhất**.

Khi muốn gọi trực tiếp với hằng `null`, phải tránh gọi `Arrays.equals(null, null)` hoặc `Arrays.hashCode(null)` không có kiểu đích: lớp `Arrays` có nhiều overload cho các loại mảng, nên lời gọi có thể **mơ hồ khi biên dịch**. Sử dụng biến có kiểu rõ ràng hoặc ép kiểu phù hợp như `(String[]) null`.

## 4. `==`, `Objects.equals()` và `Arrays.equals()` không thay thế nhau

Với hai mảng riêng biệt có cùng phần tử:

```java
String[] a = {"Java", null};
String[] b = {"Java", null};
```

- `a == b` là `false` vì chúng là **hai tham chiếu khác nhau**.
- `a.equals(b)` là `false` vì các lớp mảng không ghi đè `Object.equals()` để so nội dung.
- `Objects.equals(a, b)` cũng là `false`: hàm này xử lý null nhưng với mảng không null, nó vẫn gọi `a.equals(b)`.
- `Arrays.equals(a, b)` là `true`: so sánh độ dài và từng phần tử ở cùng vị trí.
- `Objects.deepEquals(a, b)` cũng là `true` vì cả hai là mảng; nhưng với mảng một chiều, `Arrays.equals()` thường làm rõ ý định hơn.

Hàm `Objects.equals()` hữu ích khi thuộc tính là một đối tượng giá trị có `equals()` đúng; nó **không tự biến một trường mảng thành phép so sánh phần tử**. Trong `equals()` của lớp chứa mảng, sử dụng đúng overload `Arrays.equals()` hoặc `Arrays.deepEquals()` theo cấu trúc.

Nguyên tắc song hành: nếu trường mảng tham gia `equals()` bằng `Arrays.equals()`, phần tương ứng của `hashCode()` nên dùng `Arrays.hashCode()`; nếu dùng `Arrays.deepEquals()`, dùng `Arrays.deepHashCode()` cho phần cấu trúc lồng tương ứng. Tránh dùng `Objects.hashCode(array)` hoặc bản thân `array.hashCode()` rồi kỳ vọng cùng kết quả theo nội dung: chúng dùng mã băm của **đối tượng mảng**, không thay thế `Arrays.hashCode()`.

## 5. Mảng lồng nhau: vì sao cần `deepEquals()` và `deepHashCode()`?

Mảng hai chiều trong Java là **mảng chứa các mảng**. Với `String[][]`, mỗi phần tử hàng có thể là một `String[]` hoặc `null`. Hàng không null lại có thể rỗng, hoặc chứa phần tử `String` bằng `null`. Các cấp này cần được phân biệt.

`Arrays.equals(String[][], String[][])` thực chất chọn overload `equals(Object[], Object[])`: nó so sánh **các phần tử hàng** bằng `equals()`. Vì mỗi hàng là một đối tượng mảng, hai hàng riêng biệt có nội dung giống nhau **không bằng nhau** theo `Object.equals()`. Đó là so sánh *nông* tại lớp lồng.

`Arrays.deepEquals(Object[], Object[])` so sánh đệ quy phần tử là mảng; xử lý cả mảng nguyên thủy bên trong bằng overload so sánh nội dung tương ứng. `Arrays.deepHashCode(Object[])` tính hash tương thích với quan hệ `deepEquals()`.

### 5.1. Ví dụ phân biệt hàng `null`, hàng rỗng, phần tử `null`

Tạo file **`NestedArrayDemo.java`**:

```java
import java.util.Arrays;

public class NestedArrayDemo {
    public static void main(String[] args) {
        String[][] left = {
            null,
            {},
            {null, "ok"}
        };
        String[][] same = {
            null,
            {},
            {null, "ok"}
        };
        String[][] changed = {
            null,
            {},
            {"", "ok"}
        };
        String[][] nullRow = {null};
        String[][] emptyRow = {new String[0]};

        System.out.println("shallow equals: "
                + Arrays.equals(left, same));
        System.out.println("deep equals: "
                + Arrays.deepEquals(left, same));
        System.out.println("null vs empty row: "
                + Arrays.deepEquals(nullRow, emptyRow));
        System.out.println("null vs empty element: "
                + Arrays.deepEquals(left, changed));
        System.out.println("same deep hash: "
                + (Arrays.deepHashCode(left)
                        == Arrays.deepHashCode(same)));
        System.out.println("nested data: "
                + Arrays.deepToString(left));

        int[][] numbers = {{1, 2}, null, {}};
        int[][] copy = {{1, 2}, null, {}};
        System.out.println("primitive nested equal: "
                + Arrays.deepEquals(numbers, copy));
    }
}
```

Chạy:

```bash
javac NestedArrayDemo.java
java NestedArrayDemo
```

Stdout:

```text
shallow equals: false
deep equals: true
null vs empty row: false
null vs empty element: false
same deep hash: true
nested data: [null, [], [null, ok]]
primitive nested equal: true
```

**Phân tích từng cấp:**

- `left` và `same` là hai mảng ngoài riêng biệt; các hàng rỗng và hàng chứa `null` cũng được tạo thành đối tượng mảng riêng. Vì vậy so sánh nông `Arrays.equals(left, same)` là `false`.
- `Arrays.deepEquals(left, same)` cho `true`: hàng thứ nhất đều `null`; hàng thứ hai đều rỗng; hàng thứ ba cùng chuỗi `"ok"` và cùng phần tử `null` ở vị trí đầu.
- `nullRow` khác `emptyRow`, vì **hàng không tồn tại** khác **hàng tồn tại với 0 phần tử**.
- `changed` chứa `""` thay cho `null` ở vị trí đầu của hàng thứ ba, nên so sánh sâu khác nhau.
- `Arrays.deepHashCode(left)` bằng `Arrays.deepHashCode(same)` vì dữ liệu so sánh sâu bằng nhau.
- `int[][]` cũng là `Object[]` ở **cấp ngoài** (mỗi phần tử là một `int[]`), nên gọi `Arrays.deepEquals(numbers, copy)` hợp lệ. Bên trong, các phần tử của `int[]` là số nguyên thủy, không thể là `null`; nhưng cả hàng `int[]` có thể bằng `null`.

Cần nhớ: `Arrays.deepEquals()` và `Arrays.deepHashCode()` nhận `Object[]`, nên dùng cho mảng tham chiếu và các cấu trúc lồng. Với **mảng nguyên thủy một chiều** (`int[]`, `byte[]`, `long[]`, ...), dùng đúng overload `Arrays.equals(int[], int[])` / `Arrays.hashCode(int[])`. Không thể đưa trực tiếp một `int[]` vào tham số `Object[]` của `Arrays.deepEquals()`.

Đối với mảng có cấu trúc **tự tham chiếu/vòng lặp** (mảng chứa chính nó trực tiếp hoặc gián tiếp), không nên áp dụng máy móc các phép deep recursion: hợp đồng của các phương thức deep comparison/hash không bảo đảm kết quả xác định cho mảng vòng. Hãy tránh chu trình hoặc thiết kế thuật toán xử lý identity/chu trình riêng.

## 6. Lồng trong một lớp: `equals()` và `hashCode()` phải đối xứng về độ sâu

Giả sử một giá trị biểu diễn ma trận `int[][]`. Nếu `equals()` dùng `Arrays.deepEquals(rows, other.rows)` nhưng `hashCode()` lại dùng `Arrays.hashCode(rows)`, hai ma trận có các hàng **khác tham chiếu nhưng cùng nội dung** có thể được đánh giá bằng nhau, trong khi mã băm dựa trên identity của các hàng và khác nhau. Đó là **nguy cơ vi phạm hợp đồng**.

Cặp đúng là:

```java
boolean same = Arrays.deepEquals(rows, other.rows);
int hash = Arrays.deepHashCode(rows);
```

Đây là **mảnh code minh họa**, giả định `rows` và `other.rows` đều thuộc loại `int[][]`. Với mảng phẳng `byte[]`, cặp tương ứng là `Arrays.equals(bytes, other.bytes)` và `Arrays.hashCode(bytes)`.

Không được suy luận rằng `Objects.hash(rows)` là lựa chọn tương đương với `Arrays.deepHashCode(rows)`. `Objects.hash(...)` dùng varargs, dễ gây nhầm lẫn về cách mảng được trải thành các phần tử; với mảng lồng, nó không tự có ngữ nghĩa deep hash đúng như yêu cầu.

## 7. Ví dụ lớp giá trị bất biến, chấp nhận hàng `null`

Một đối tượng dùng làm khóa `HashMap` hoặc phần tử `HashSet` nên giữ các trường tham gia equality/hash **ổn định**. Với mảng, `final int[][] rows` chỉ làm **tham chiếu bên ngoài** không đổi; mã gọi vẫn có thể sửa `rows[0][0]` qua alias nếu không sao chép. Đối với ma trận `int[][]`, cần sao chép cả **mảng ngoài lẫn từng hàng không null** khi nhận đầu vào, và không trả trực tiếp mảng bên trong ra ngoài.

Tạo file **`MatrixKeyDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

final class MatrixKey {
    private final int[][] rows;

    MatrixKey(int[][] source) {
        Objects.requireNonNull(source, "source");
        this.rows = deepCopy(source);
    }

    private static int[][] deepCopy(int[][] source) {
        int[][] copy = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copy[i] = source[i] == null
                    ? null
                    : source[i].clone();
        }
        return copy;
    }

    public int[][] rowsCopy() {
        return deepCopy(rows);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof MatrixKey other
                && Arrays.deepEquals(rows, other.rows);
    }

    @Override
    public int hashCode() {
        return Arrays.deepHashCode(rows);
    }
}

public class MatrixKeyDemo {
    public static void main(String[] args) {
        int[][] input = {{1, 2}, null, {}};
        MatrixKey first = new MatrixKey(input);
        MatrixKey second =
                new MatrixKey(new int[][] {{1, 2}, null, {}});
        MatrixKey different =
                new MatrixKey(new int[][] {{1, 2}, {}, {}});

        System.out.println("equal contents: "
                + first.equals(second));
        System.out.println("same hash: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("null row vs empty row: "
                + first.equals(different));

        Set<MatrixKey> keys =
                new HashSet<>(List.of(first, second));
        System.out.println("set size: " + keys.size());

        input[0][0] = 99;
        System.out.println("after source mutation: "
                + first.equals(second));

        int[][] externalCopy = first.rowsCopy();
        externalCopy[0][0] = 77;
        System.out.println("after copy mutation: "
                + first.equals(second));
    }
}
```

Chạy:

```bash
javac MatrixKeyDemo.java
java MatrixKeyDemo
```

Stdout:

```text
equal contents: true
same hash: true
null row vs empty row: false
set size: 1
after source mutation: true
after copy mutation: true
```

**Vì sao ví dụ này quan trọng?**

1. Ma trận có hàng `null`, hàng rỗng và hàng có dữ liệu; sự khác nhau ấy được giữ nguyên bằng `deepCopy`.
2. `Arrays.deepEquals()` và `Arrays.deepHashCode()` xét các hàng theo nội dung một cách tương ứng.
3. Lớp `final` giữ `rows` là `private final`, sao chép từng hàng khi nhận và trả dữ liệu, nên thay đổi bên ngoài không phá trạng thái khóa.
4. Hai khóa có cùng nội dung logic được `HashSet` coi là một; khóa có hàng `null` khác khóa có hàng rỗng.
5. Ví dụ dành riêng cho `int[][]`; nếu phần tử lồng là **đối tượng mutable** (ví dụ `List<MutableItem>[]`) thì `clone()` từng hàng chỉ sao chép tham chiếu phần tử, **chưa đủ để tạo bất biến sâu**. Cần sao chép/đóng băng phù hợp với mô hình dữ liệu.

Tùy API, bạn có thể lựa chọn **cấm hoàn toàn hàng `null`**, thay vì giữ nó. Nhưng phải kiểm tra trong constructor và thể hiện rõ với người gọi, không lén chuẩn hóa nếu `null` mang ý nghĩa nghiệp vụ.

## 8. Khi nào nên chuẩn hóa `null` thành mảng rỗng?

Có hai lựa chọn đều hợp lệ, miễn là thống nhất giữa đọc dữ liệu, `equals()` và `hashCode()`:

### Lựa chọn A: bảo toàn khác biệt

Nếu `null` nghĩa là “chưa biết”, còn rỗng nghĩa là “biết chắc không có”, hãy giữ nguyên. Dùng `Arrays.equals()` và `Arrays.hashCode()` cho mảng phẳng; `Arrays.deepEquals()` và `Arrays.deepHashCode()` cho mảng lồng. Hai trạng thái sẽ khác nhau theo phép so sánh nội dung chuẩn.

### Lựa chọn B: coi `null` như rỗng ngay ở ranh giới

Nếu nghiệp vụ coi **không cung cấp** và **danh sách rỗng** là cùng một giá trị, có thể chuẩn hóa trong constructor:

```java
this.tags = tags == null ? new String[0] : tags.clone();
```

Đây là **mảnh code minh họa** cho trường `String[] tags`. Sau chuẩn hóa, không còn sự phân biệt giữa đầu vào `null` và đầu vào rỗng. Dùng `Arrays.equals(this.tags, other.tags)` và `Arrays.hashCode(this.tags)` sẽ nhất quán, với điều kiện không để sửa mảng nội bộ qua getter. Nếu còn cần phân biệt “không được cung cấp”, phải lưu riêng thông tin hiện diện, hoặc giữ `null`.

**Không chuẩn hóa chỉ trong một phương thức.** Nếu `equals()` coi `null` và `[]` bằng nhau nhưng `hashCode()` vẫn trả 0 cho `null` và 1 cho `[]`, bạn đã vi phạm hợp đồng. Tốt nhất chuẩn hóa dữ liệu **một lần tại ranh giới**, rồi dùng cùng trạng thái chuẩn hóa để so sánh và tính hash.

Cũng không nên tự động bỏ các phần tử `null` hoặc đổi `null` thành `""`: `[null]`, `[]` và `[""]` mang những thông tin khác nhau, và hành vi làm sạch dữ liệu phải là **quyết định nghiệp vụ tường minh**.

## 9. Các lỗi rất dễ gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Truy cập `array.length` khi array là `null` | `NullPointerException` | Kiểm tra biến mảng trước |
| Truy cập `array[0]` khi mảng rỗng | `ArrayIndexOutOfBoundsException` | Kiểm tra `length > 0` |
| Chỉ kiểm tra mảng ngoài mà quên phần tử/hàng null | `NullPointerException` khi dùng phần tử/hàng | Kiểm tra từng cấp phù hợp |
| Dùng `==`, `array.equals()` hoặc `Objects.equals()` để so nội dung mảng | So tham chiếu, khác với nội dung | Dùng `Arrays.equals()` hoặc `Arrays.deepEquals()` |
| Dùng `Arrays.equals()` cho hai mảng lồng, rồi kỳ vọng so mọi cấp | Mảng con khác tham chiếu bị coi là khác | Dùng `Arrays.deepEquals()` nếu muốn so sâu |
| Dùng `Arrays.deepEquals()` nhưng `hashCode()` tính theo tham chiếu của mảng con | Nguy cơ hai đối tượng bằng nhau khác hash | Dùng `Arrays.deepHashCode()` tương ứng |
| Coi `null`, `[]` và `[null]` như nhau vô điều kiện | Mất ý nghĩa dữ liệu | Thống nhất quy tắc đầu vào |
| Dùng `Arrays.equals(null, null)` mà không chỉ kiểu | Lời gọi overload có thể mơ hồ | Dùng biến đã khai báo kiểu hoặc ép kiểu |
| Đưa mảng mutable trực tiếp vào khóa hash | Thay đổi dữ liệu làm mất tra cứu | Tạo wrapper bất biến và sao chép phòng vệ |
| Chỉ `clone()` mảng ngoài của cấu trúc lồng | Mảng/hàng con còn bị sửa từ ngoài | Sao chép đủ mức lồng của dữ liệu |

**Lưu ý về `Arrays.toString()` / `Arrays.deepToString()`:** Chúng giúp kiểm tra dữ liệu, nhưng chuỗi hiển thị không phải định nghĩa equality/hash. Ví dụ `Arrays.toString(new String[]{null})` hiển thị `[null]`, còn `Arrays.toString(new String[]{"null"})` cũng hiển thị `[null]`. Đừng so sánh kết quả `toString()` để xác định hai mảng có bằng nhau hay không. Với mảng lồng, dùng `deepToString()` để quan sát các cấp nội dung khi debug.

## 10. Checklist thực hành

- [ ] Xác định rõ `null` của **cả mảng**, mảng `length == 0`, và phần tử `null` có phải ba trạng thái khác nhau theo nghiệp vụ không.
- [ ] Nếu chỉ cho phép đầu vào không null, kiểm tra sớm bằng `Objects.requireNonNull()`; nếu cần cấm phần tử null, kiểm tra từng phần tử/hàng.
- [ ] Khi truy cập `length` hoặc `[0]`, đã kiểm tra mảng không null và đủ số phần tử.
- [ ] Mảng phẳng dùng cặp `Arrays.equals()` / `Arrays.hashCode()` đúng overload.
- [ ] Mảng lồng dùng cặp `Arrays.deepEquals()` / `Arrays.deepHashCode()` khi ý định là so nội dung các cấp.
- [ ] Không nhầm `Objects.equals()` với phép so nội dung mảng; không nhầm `String` rỗng với phần tử null.
- [ ] Không tự chuẩn hóa `null` thành rỗng hay bỏ phần tử null nếu hợp đồng không quy định.
- [ ] Nếu mảng tham gia equality/hash của khóa trong `HashMap`/`HashSet`, trạng thái của nó được bảo vệ khỏi thay đổi ngoài ý muốn.
- [ ] Kiểm thử cả hai mảng null, một null một rỗng, hai rỗng, `[null]`, `[""]`, các hàng null/rỗng trong mảng lồng, và mảng nguyên thủy.

**Nguyên tắc ghi nhớ:** `null` không có nghĩa là “mảng độ dài 0”, và phần tử `null` cũng không có nghĩa là “không có phần tử”. Hãy xác định trước ý nghĩa của dữ liệu, rồi chọn phép kiểm tra, phép so sánh và mã băm tương ứng. Khi cấu trúc lồng nhau, bảo đảm **độ sâu so sánh và độ sâu tính hash nhất quán**.
