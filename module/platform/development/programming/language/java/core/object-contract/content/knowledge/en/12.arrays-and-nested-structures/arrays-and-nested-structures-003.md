# `Arrays.deepEquals()` và `Arrays.deepHashCode()` cho mảng lồng trong Java

## Mục tiêu bài học

Trong Java, **mảng là đối tượng**. Hai mảng khác nhau có thể chứa cùng giá trị nhưng `==` vẫn là `false`; ngay cả `Arrays.equals()` cũng có giới hạn khi các phần tử của mảng ngoài lại là **những mảng khác**. `Arrays.deepEquals()` và `Arrays.deepHashCode()` giúp so sánh và tính mã băm **theo cấu trúc lồng nhau** trong trường hợp phù hợp.

Sau bài này, bạn có thể:

- Phân biệt `==`, `Arrays.equals()`, `Arrays.deepEquals()`, `Arrays.hashCode()` và `Arrays.deepHashCode()`.
- Giải thích vì sao `int[][]`, `String[][]` và `Object[]` chứa mảng có kết quả so sánh khác nhau giữa cách nông và sâu.
- Biết kiểu tham số mà hai API `deep*` chấp nhận và dùng `Arrays.equals()/hashCode()` cho mảng nguyên thủy một chiều.
- Hiểu cách xử lý mảng con, `null`, phần tử thường, mảng nguyên thủy, thứ tự và cấu trúc lồng.
- Giữ hợp đồng giữa bằng nhau và mã băm khi xây dựng lớp chứa mảng; nhận biết tác động của dữ liệu mutable và mảng tự tham chiếu.

## 1. Bốn phép so sánh thường gặp

Giả sử mỗi mảng con được tạo bởi một lệnh `new` riêng:

```java
int[][] a = {{1, 2}, {3, 4}};
int[][] b = {{1, 2}, {3, 4}};

System.out.println(a == b);                  // false
System.out.println(Arrays.equals(a, b));     // false
System.out.println(Arrays.deepEquals(a, b)); // true
```

Đây là đoạn mã minh họa đặt bên trong một phương thức, cần `import java.util.Arrays;`.

- **`a == b`** so sánh danh tính mảng ngoài. Hai mảng ngoài riêng biệt nên kết quả `false`.
- **`Arrays.equals(a, b)`** kiểm tra chiều dài và các phần tử cùng vị trí của mảng ngoài. Các phần tử này là các mảng `int[]` riêng biệt, và chúng không ghi đè `Object.equals()` để so theo phần tử. Do đó kết quả `false`.
- **`Arrays.deepEquals(a, b)`** đi xuống từng mảng con và so sánh phần tử tương ứng bằng quy tắc phù hợp: ở đây, các phần tử `int` bên trong tương ứng bằng nhau, nên kết quả `true`.

Mảng hai chiều `int[][]` thực chất là một mảng có các phần tử kiểu `int[]`. Các mảng con có thể dài khác nhau, và một phần tử mảng con có thể là `null`. Nó không phải một ma trận bộ nhớ phẳng bắt buộc có cùng số cột.

### Shallow vs. deep

```text
a: int[][]                    b: int[][]

  a[0] ──► [1, 2]              b[0] ──► [1, 2]
  a[1] ──► [3, 4]              b[1] ──► [3, 4]

Arrays.equals(a, b):
  So a[0] với b[0] như hai phần tử tham chiếu → khác đối tượng → false.

Arrays.deepEquals(a, b):
  So a[0] với b[0] bằng nội dung int[] → true;
  so a[1] với b[1] bằng nội dung int[] → true;
  kết quả toàn bộ → true.
```

Điểm cốt lõi: `deepEquals` so sánh **giá trị các phần tử trong cấu trúc mảng lồng**; nó không yêu cầu các mảng con nằm ở cùng địa chỉ hay là cùng đối tượng.

## 2. Kiểu tham số của `Arrays.deepEquals()` và `Arrays.deepHashCode()`

Hai phương thức có chữ ký cơ bản:

```java
public static boolean deepEquals(Object[] a1, Object[] a2);
public static int deepHashCode(Object[] a);
```

Vì `int[][]` là một mảng các `int[]` (mỗi `int[]` là một `Object`), `int[][]` có thể được truyền như một `Object[]`. `String[][]`, `long[][][]` và `Object[]` cũng có thể truyền vào các API này.

Ngược lại, **`int[]` nguyên thủy một chiều không phải `Object[]`**:

```java
int[] a = {1, 2};
int[] b = {1, 2};

boolean same = java.util.Arrays.equals(a, b); // true
int hash = java.util.Arrays.hashCode(a);

// Các dòng sau KHÔNG BIÊN DỊCH:
// java.util.Arrays.deepEquals(a, b);
// java.util.Arrays.deepHashCode(a);
```

Đây là đoạn minh họa trong một phương thức; hai dòng sai được comment cố ý.

Chọn API theo kiểu mảng tại vị trí so sánh:

| Dữ liệu | So sánh nội dung | Tính hash theo nội dung |
| --- | --- | --- |
| `int[]`, `byte[]`, `char[]`, `boolean[]`,… | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` |
| `String[]`, không có mảng con | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` |
| `int[][]` hoặc mảng nguyên thủy nhiều chiều | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(a)` |
| `Object[]` chứa các mảng, hoặc `Object[][]` | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(a)` |

Với mảng một chiều chứa đối tượng thường không phải mảng, `Arrays.deepEquals` cũng có thể dùng nhưng không mang lại lợi ích so sánh sâu đặc biệt. Cả hai đường thường đi đến `equals()` của phần tử. **Deep** ở đây chỉ nghĩa là đi sâu vào **các mảng lồng nhau**; nó không tự duyệt các trường của mọi đối tượng Java tùy ý.

## 3. Java 17+ hoàn chỉnh: so sánh nông, sâu, `null` và mảng nguyên thủy

Tạo tệp `DeepArraysDemo.java`:

```java
import java.util.Arrays;

public class DeepArraysDemo {
    public static void main(String[] args) {
        int[][] left = {{1, 2}, {3, 4}};
        int[][] right = {{1, 2}, {3, 4}};
        int[][] changed = {{1, 2}, {3, 5}};

        System.out.println("same outer reference: " + (left == right));
        System.out.println("shallow equals: "
                + Arrays.equals(left, right));
        System.out.println("deep equals: "
                + Arrays.deepEquals(left, right));
        System.out.println("deep hash equal: "
                + (Arrays.deepHashCode(left)
                   == Arrays.deepHashCode(right)));
        System.out.println("changed equals: "
                + Arrays.deepEquals(left, changed));

        Object[] mixedLeft = {
                new int[] {7, 8},
                new Object[] {new String[] {"A", "B"}, null}
        };
        Object[] mixedRight = {
                new int[] {7, 8},
                new Object[] {new String[] {"A", "B"}, null}
        };
        System.out.println("mixed shallow: "
                + Arrays.equals(mixedLeft, mixedRight));
        System.out.println("mixed deep: "
                + Arrays.deepEquals(mixedLeft, mixedRight));
        System.out.println("mixed hashes match: "
                + (Arrays.deepHashCode(mixedLeft)
                   == Arrays.deepHashCode(mixedRight)));

        int[] singleLeft = {10, 20};
        int[] singleRight = {10, 20};
        System.out.println("single primitive equals: "
                + Arrays.equals(singleLeft, singleRight));
        System.out.println("single primitive hash equal: "
                + (Arrays.hashCode(singleLeft)
                   == Arrays.hashCode(singleRight)));

        int[][] nullableLeft = {null, {9}};
        int[][] nullableRight = {null, {9}};
        System.out.println("nested null equals: "
                + Arrays.deepEquals(nullableLeft, nullableRight));

        left[1][1] = 99;
        System.out.println("after mutation equals: "
                + Arrays.deepEquals(left, right));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac DeepArraysDemo.java
java DeepArraysDemo
```

Kết quả chuẩn:

```text
same outer reference: false
shallow equals: false
deep equals: true
deep hash equal: true
changed equals: false
mixed shallow: false
mixed deep: true
mixed hashes match: true
single primitive equals: true
single primitive hash equal: true
nested null equals: true
after mutation equals: false
```

Giải thích:

1. `left` và `right` được tạo thành hai đối tượng mảng riêng nên `==` là `false`. `Arrays.equals` cũng là `false` do các mảng con là những đối tượng riêng.
2. `Arrays.deepEquals(left, right)` là `true` vì tất cả các hàng `int[]` tương ứng cùng số phần tử và cùng giá trị; bởi vậy hai mã `deepHashCode` bắt buộc bằng nhau.
3. `changed` khác một phần tử `5` thay vì `4` nên `deepEquals` là `false`.
4. Với `mixedLeft`/`mixedRight`, cấu trúc gồm `int[]`, một `Object[]` lồng trong, `String[]` và `null`. Phép so sâu xử lý được cả những cấp lồng này.
5. Mảng nguyên thủy một chiều dùng `Arrays.equals` và `Arrays.hashCode`.
6. Hai cấu trúc có phần tử mảng con `null` tại cùng vị trí có thể bằng nhau theo phép so sâu.
7. Sau khi thay `left[1][1]` thành `99`, nội dung đã khác `right`, nên `deepEquals` chuyển từ `true` sang `false`. Các API không “đóng băng” kết quả hay lưu snapshot dữ liệu.

## 4. `deepEquals` xử lý các phần tử như thế nào?

Ở mức khái niệm, `Arrays.deepEquals(a, b)` với hai `Object[]` có quy tắc:

1. Nếu hai tham chiếu mảng ngoài là cùng tham chiếu (kể cả cùng `null`), kết quả là `true`.
2. Nếu một mảng ngoài là `null` còn mảng kia không phải, kết quả là `false`.
3. Nếu độ dài khác nhau, kết quả là `false`.
4. Với từng vị trí tương ứng, kiểm tra hai phần tử. Nếu là các `Object[]` tương ứng, so đệ quy. Nếu là hai mảng nguyên thủy cùng loại, dùng phép so sánh phần tử nguyên thủy thích hợp. Nếu không phải cặp mảng cần so sâu, áp dụng quan hệ bằng nhau phù hợp với các đối tượng bình thường. Chỉ cần một vị trí không bằng nhau là trả về `false`.

Do đó, **kiểu mảng, mức lồng, thứ tự, độ dài và phần tử** đều quan trọng.

### Thứ tự không bị bỏ qua

```java
int[][] a = {{1}, {2}};
int[][] b = {{2}, {1}};

System.out.println(Arrays.deepEquals(a, b)); // false
```

Các dòng này minh họa bên trong phương thức và cần import `java.util.Arrays`. Hai mảng chứa cùng tập giá trị nếu không xét thứ tự, nhưng `deepEquals` là phép so sánh **theo vị trí**, không phải phép so sánh tập hợp hay hoán vị.

### Khác kiểu mảng nguyên thủy không được chuyển đổi

```java
Object[] a = {new int[] {1, 2}};
Object[] b = {new long[] {1L, 2L}};

System.out.println(Arrays.deepEquals(a, b)); // false
```

Mặc dù những số hiển thị có cùng độ lớn, `int[]` và `long[]` là hai kiểu mảng khác nhau. Không có quy tắc tự nâng kiểu nguyên thủy để biến các mảng thành “bằng nhau” về cấu trúc.

### Mảng răng cưa và mảng có phần tử `null`

```java
int[][] a = {{1}, null, {2, 3}};
int[][] b = {{1}, null, {2, 3}};
int[][] c = {{1}, {}, {2, 3}};

System.out.println(Arrays.deepEquals(a, b)); // true
System.out.println(Arrays.deepEquals(a, c)); // false
```

Một hàng `null` khác với một mảng rỗng `new int[0]`. Phương thức không tự coi dữ liệu vắng mặt là mảng rỗng.

### Phần tử không phải mảng

```java
Object[] a = {"hello", Integer.valueOf(7)};
Object[] b = {new String("hello"), Integer.valueOf(7)};

System.out.println(Arrays.deepEquals(a, b)); // true
```

Khi phần tử không phải mảng, `deepEquals` dựa vào `equals()` của các đối tượng. Không có “deep reflection” để tự truy cập những trường `private` trong lớp tùy ý. Nếu một lớp tự định nghĩa `equals` theo danh tính, các đối tượng khác nhau của lớp đó sẽ không tự bằng nhau chỉ vì đặt trong `Object[]`.

Các ví dụ ở phần này là các đoạn thân phương thức, không phải tệp Java chạy độc lập.

## 5. `Arrays.deepHashCode()` tính hash của cấu trúc lồng

`Arrays.deepHashCode(Object[] a)` tính mã băm theo các phần tử của mảng ngoài. Nếu một phần tử là mảng con:

- Mảng con kiểu tham chiếu (`Object[]`) được xử lý sâu bằng cách áp dụng `deepHashCode` cho mảng con đó.
- Mảng con kiểu nguyên thủy, ví dụ `int[]` hoặc `double[]`, dùng phép `Arrays.hashCode` thích hợp cho kiểu mảng đó.
- Phần tử đối tượng bình thường được hash dựa trên `hashCode()` của đối tượng; phần tử `null` được xử lý theo quy tắc của thuật toán.

Phép tổng hợp mã băm tuân theo cách kết hợp tuần tự của các phần tử. Với mảng không lồng, nó phù hợp ý tưởng tích lũy `31 * result + elementHash`; với mảng lồng, `elementHash` có thể là hash tính sâu của mảng con.

Ví dụ:

```java
int[][] a = {{1, 2}, {3}};
int[][] b = {{1, 2}, {3}};

System.out.println(Arrays.deepEquals(a, b)); // true
System.out.println(Arrays.deepHashCode(a)
        == Arrays.deepHashCode(b));           // true
```

Không cần nhớ một mã số hash cụ thể để dùng API đúng. Điều quan trọng là **quan hệ** giữa hai phép toán:

```text
Arrays.deepEquals(a, b) == true
                  ↓ bắt buộc
Arrays.deepHashCode(a) == Arrays.deepHashCode(b)
```

**Không được đảo chiều:** hai mảng khác nhau về phép so sánh sâu vẫn có thể có cùng deep hash. Mã băm là `int` nên collision là điều có thể xảy ra với bất kỳ hàm băm chất lượng tốt nào.

### Vì sao phải dùng cặp phương thức nhất quán?

Nếu định nghĩa “bằng nhau” cho một đối tượng chứa mảng bằng `Arrays.deepEquals`, hàm `hashCode` của đối tượng đó phải có quan hệ tương thích; `Arrays.deepHashCode` là cách tự nhiên để thực hiện. Ngược lại, nếu dùng `Arrays.hashCode` trên **mảng ngoài** chứa mảng con, nó nhìn các mảng con như những phần tử tham chiếu. Những mảng con riêng biệt nhưng cùng nội dung không bắt buộc có cùng hash theo cách tính nông.

Vì vậy, không nên ghép tùy tiện một phép so sánh sâu với một hàm hash nông khi các mảng con quyết định bằng nhau theo nội dung.

## 6. Cạm bẫy: `Arrays.hashCode`/`Arrays.equals` trên mảng ngoài

Với `int[][]`, mỗi phần tử của mảng ngoài là `int[]`. `int[]` không ghi đè `equals()` và `hashCode()` theo giá trị phần tử, nên các phép toán **nông** xử lý mảng con theo quy tắc mặc định của đối tượng.

So sánh:

```java
int[][] a = {{1, 2}};
int[][] b = {{1, 2}};

boolean shallow = Arrays.equals(a, b);       // false
boolean deep = Arrays.deepEquals(a, b);      // true
boolean deepHashesEqual =
        Arrays.deepHashCode(a)
        == Arrays.deepHashCode(b);           // true
```

Không nên in hay khẳng định trước một kết quả cố định cho `Arrays.hashCode(a) == Arrays.hashCode(b)` ở đây: mã băm danh tính của các mảng con có thể vô tình trùng nhau, dù điều đó không làm `Arrays.equals(a, b)` thành `true`. Về mặt thiết kế, hash nông **không tương thích được bảo đảm** với tiêu chí bằng nhau sâu.

Một cách nhìn khác là thay các mảng con bằng cách dùng chung tham chiếu:

```java
int[] row = {1, 2};
int[][] a = {row};
int[][] b = {row};

System.out.println(Arrays.equals(a, b)); // true
```

Hai mảng ngoài khác nhau nhưng đều chứa **chính đối tượng** `row`, nên phép so nông của phần tử cũng cho `true`. Đây không phải bằng chứng rằng `Arrays.equals` so dữ liệu sâu. Phép so sâu sẽ đúng cả khi mỗi bên có một mảng con mới cùng nội dung.

## 7. Khi cấu trúc mảng có alias (chia sẻ mảng con)

`deepEquals` so sánh **nội dung theo vị trí**; nó không yêu cầu biểu đồ tham chiếu bên trong phải có cùng kiểu chia sẻ đối tượng.

```java
int[] shared = {4, 5};
Object[] left = {shared, shared};
Object[] right = {new int[] {4, 5}, new int[] {4, 5}};

System.out.println(Arrays.deepEquals(left, right)); // true
```

Trong `left`, hai vị trí cùng tham chiếu đến `shared`. Trong `right`, chúng trỏ đến hai mảng `int[]` khác nhau. Tuy nhiên, ở mỗi vị trí, dữ liệu bên trong tương ứng bằng nhau nên phép so sâu cho `true`. Nếu yêu cầu nghiệp vụ của bạn cần biết hai vị trí có chia sẻ cùng một instance hay không, `deepEquals` **không phải** phép kiểm tra đó; hãy kiểm tra danh tính tham chiếu bằng `==` theo từng vị trí.

Một vấn đề khác là **mutable aliasing**: sửa `shared[0]` sẽ thay đổi nội dung có thể quan sát ở cả hai vị trí của `left`, còn `right` không đổi. Kết quả `deepEquals`/`deepHashCode` của cùng một cấu trúc có thể thay đổi theo thời gian nếu mảng con bị sửa.

## 8. Các mảng tự tham chiếu hoặc chứa chu trình

Mảng `Object[]` có thể trực tiếp hoặc gián tiếp chứa tham chiếu đến chính nó:

```java
Object[] cycle = new Object[1];
cycle[0] = cycle;
```

Với cấu trúc như trên, **không được dựa vào `Arrays.deepEquals` hoặc `Arrays.deepHashCode`**. Tài liệu API Java nêu rằng hành vi của các phép toán sâu là **không xác định** khi mảng chứa chính nó như phần tử, trực tiếp hoặc gián tiếp. Trên một số môi trường, việc đệ quy có thể dẫn đến `StackOverflowError`; đây không phải kết quả chuẩn mà ứng dụng có thể dựa vào.

Nếu mô hình dữ liệu thực sự có đồ thị đối tượng chứa chu trình (ví dụ nút cha/con tham chiếu qua lại), cần thiết kế thuật toán so sánh/hash chuyên biệt có theo dõi các đối tượng đã thăm và quy tắc rõ ràng cho chu trình. Không thể thay thế hoàn toàn bằng một lời gọi `deep*`.

**Phạm vi dùng tốt nhất:** mảng lồng có cấu trúc hữu hạn, không có chu trình tham chiếu tự chứa.

## 9. Áp dụng cho `equals()` và `hashCode()` của lớp chứa mảng

Mặc định, một trường kiểu mảng dùng phương thức `equals()` thừa kế từ `Object`, tức là so sánh **danh tính của đối tượng mảng**. Nếu mô hình nghiệp vụ muốn coi hai đối tượng là bằng nhau khi dữ liệu mảng lồng giống nhau, phải cài đặt rõ.

Ví dụ Java 17+ dùng một lớp value object đơn giản. Đoạn sau là **một chương trình độc lập** để thấy cách dùng cặp API sâu:

Tạo tệp `DeepValueEqualityDemo.java`:

```java
import java.util.Arrays;

public class DeepValueEqualityDemo {
    static final class MatrixValue {
        private final int[][] values;

        MatrixValue(int[][] source) {
            this.values = copy(source);
        }

        private static int[][] copy(int[][] source) {
            if (source == null) {
                return null;
            }
            int[][] result = new int[source.length][];
            for (int i = 0; i < source.length; i++) {
                result[i] = source[i] == null
                        ? null : source[i].clone();
            }
            return result;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof MatrixValue other)) {
                return false;
            }
            return Arrays.deepEquals(values, other.values);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(values);
        }
    }

    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3}};
        MatrixValue a = new MatrixValue(input);
        MatrixValue b = new MatrixValue(new int[][] {{1, 2}, {3}});
        MatrixValue c = new MatrixValue(new int[][] {{1, 2}, {4}});

        System.out.println("equal values: " + a.equals(b));
        System.out.println("equal hashes: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("different values: " + a.equals(c));

        input[0][0] = 99;
        System.out.println("safe from source mutation: "
                + a.equals(b));
    }
}
```

Biên dịch và chạy:

```bash
javac DeepValueEqualityDemo.java
java DeepValueEqualityDemo
```

Đầu ra:

```text
equal values: true
equal hashes: true
different values: false
safe from source mutation: true
```

Ở đây `MatrixValue` là lớp `final` nên pattern matching với `instanceof` không đặt ra lựa chọn phức tạp về kế thừa. `Arrays.deepEquals` so dữ liệu mảng lồng, còn `Arrays.deepHashCode` tính hash từ cùng dữ liệu, bảo đảm chiều bắt buộc của hợp đồng.

Constructor sao chép **mảng ngoài và từng hàng `int[]`**, cho nên việc sửa `input` sau khi tạo `MatrixValue` không ảnh hưởng đến đối tượng. Các trường không có phương thức setter hay getter trả trực tiếp mảng nội bộ; trong ví dụ này, đối tượng giữ dữ liệu ổn định trong suốt vòng đời của nó. Nếu cấu trúc thay bằng các mảng tham chiếu lồng nhau chứa đối tượng mutable, `clone()` từng lớp như ví dụ này **chưa đủ** để bảo đảm bất biến hoàn toàn; phải xem xét chiến lược sao chép sâu hoặc đóng gói tương ứng.

### Vì sao không dùng mảng trực tiếp làm khóa nếu muốn bằng nhau theo nội dung?

`HashMap<int[][], String>` vẫn chấp nhận mảng làm khóa, nhưng khóa mảng không tự dùng `Arrays.deepEquals`:

```java
Map<int[][], String> map = new HashMap<>();
map.put(new int[][] {{1, 2}}, "found");

String result = map.get(new int[][] {{1, 2}});
// result là null vì khóa truy vấn là một đối tượng mảng mới
```

Đây là đoạn minh họa cần `import java.util.Map;` và `import java.util.HashMap;` trong một phương thức.

Nếu muốn so khóa theo nội dung mảng lồng, dùng lớp wrapper bất biến có cài đặt `equals/hashCode` theo nội dung như `MatrixValue`. Đừng kỳ vọng `HashMap` tự gọi `Arrays.deepEquals` cho từng khóa mảng.

**Lưu ý với `record` chứa mảng:** record tự sinh `equals/hashCode` cho các thành phần theo hợp đồng của từng kiểu. Thành phần là mảng vẫn có ngữ nghĩa equality/hash của chính đối tượng mảng (không tự so sâu). Vì vậy, `record Payload(int[][] values) {}` không tự thay thế một wrapper có `Arrays.deepEquals/deepHashCode` nếu nghiệp vụ cần so nội dung mảng lồng.

## 10. Lỗi thường gặp

1. **Dùng `Arrays.equals` cho `int[][]` rồi ngạc nhiên vì `false`.** Phần tử của mảng ngoài là các mảng con; dùng `Arrays.deepEquals` khi muốn so nội dung các hàng.
2. **Dùng `Arrays.deepEquals` cho `int[]` một chiều.** Không biên dịch vì chữ ký đòi `Object[]`; dùng `Arrays.equals`.
3. **Gọi `Arrays.deepHashCode` rồi suy ra hai mảng có hash giống nhau chắc chắn bằng nhau.** Sai: collision vẫn có thể xảy ra; dùng `deepEquals` để kết luận.
4. **So sâu trong `equals` nhưng hash nông trong `hashCode` của wrapper.** Có thể vi phạm hợp đồng giữa hai đối tượng bằng nhau theo nội dung; dùng cặp hàm nhất quán.
5. **Cho rằng `deepEquals` tự so sâu mọi đối tượng người dùng tự định nghĩa.** Với phần tử không phải mảng, kết quả theo `equals` của lớp phần tử.
6. **Bỏ qua thứ tự, độ dài, kiểu mảng hoặc `null`.** Các khác biệt này thường làm `deepEquals` cho `false`; phép so sâu không phải phép chuyển đổi kiểu hay so tập hợp.
7. **Đưa cấu trúc có chu trình vào `deepEquals/deepHashCode`.** Hành vi không xác định; cần thuật toán dành cho đồ thị có chu trình.
8. **Dùng đối tượng chứa mảng mutable làm khóa trong `HashMap`.** Nếu các phần tử dùng tính hash thay đổi khi đối tượng đang ở trong bảng, việc tra cứu có thể thất bại. Cần đóng gói/sao chép và bảo đảm dữ liệu dùng cho equality/hash ổn định.
9. **Nhầm cùng cấu trúc dữ liệu với cùng sơ đồ alias.** Hai vị trí trỏ chung một mảng con vẫn có thể so sâu bằng một cấu trúc chứa hai bản sao mảng con độc lập.

## 11. Tự kiểm tra

Xét các biến sau:

```java
int[][] a = {{1, 2}, null};
int[][] b = {{1, 2}, null};
int[][] c = {{2, 1}, null};
int[][] d = {{1, 2}, {}};

boolean q1 = a == b;
boolean q2 = Arrays.equals(a, b);
boolean q3 = Arrays.deepEquals(a, b);
boolean q4 = Arrays.deepHashCode(a)
          == Arrays.deepHashCode(b);
boolean q5 = Arrays.deepEquals(a, c);
boolean q6 = Arrays.deepEquals(a, d);
```

Đoạn mã minh họa đặt trong phương thức đã import `java.util.Arrays`.

**Đáp án và lý do:**

- `q1 = false`: hai mảng ngoài là hai đối tượng khác nhau.
- `q2 = false`: ở vị trí đầu, `a[0]` và `b[0]` là hai mảng `int[]` khác nhau về danh tính; so nông dừng ở đây.
- `q3 = true`: hai mảng con đầu cùng `[1, 2]` và hai phần tử tiếp theo đều `null`.
- `q4 = true`: khi phép so sâu cho `true`, mã băm sâu bắt buộc bằng nhau.
- `q5 = false`: `[1, 2]` khác `[2, 1]` do thứ tự phần tử.
- `q6 = false`: hàng `null` không tương đương với hàng rỗng.

Một bài tập mở rộng: tạo hai `Object[]` mỗi bên chứa `new int[] {1,2}` và `"abc"`, rồi so `Arrays.equals`, `Arrays.deepEquals`, `Arrays.hashCode`, `Arrays.deepHashCode`. Giải thích vì sao phép so sâu có thể là `true` ngay cả khi phép so nông là `false`, và vì sao không nên dùng một kết quả hash bằng nhau làm bằng chứng hai giá trị bằng nhau.

## Ghi nhớ

- **`Arrays.equals`/`Arrays.hashCode`** phù hợp cho so sánh nội dung mảng nguyên thủy một chiều, hoặc mảng đối tượng không cần đi xuống những mảng con.
- **`Arrays.deepEquals`/`Arrays.deepHashCode`** phù hợp cho `Object[]` chứa cấu trúc mảng lồng, bao gồm `int[][]` và `String[][]`; chúng đi sâu qua các mảng con để so sánh và tính hash theo nội dung.
- **`deepEquals(a, b) == true` ⇒ deep hash của `a` và `b` bằng nhau**, nhưng cùng deep hash không bảo đảm hai mảng bằng nhau.
- Các phương thức `deep*` không tự xử lý mọi đồ thị đối tượng tùy ý có chu trình, không tự so trường bên trong mọi object và không tự làm dữ liệu trở nên bất biến. Khi dùng mảng lồng trong `equals/hashCode` hoặc làm khóa của cấu trúc băm, phải thiết kế hợp đồng và bảo vệ trạng thái dữ liệu phù hợp.