# Mảng hỗ trợ clone() và mảng nhiều chiều vẫn chia sẻ mảng con

## 1. Khái niệm cốt lõi

Mảng trong Java là **đối tượng**. Dù mảng không khai báo lớp bằng cú pháp thông thường, mọi kiểu mảng đều hỗ trợ `clone()`; mảng cũng triển khai giao diện đánh dấu `Cloneable`. Khi gọi `array.clone()`, Java tạo **một đối tượng mảng mới có cùng kiểu runtime, cùng độ dài**, rồi sao chép từng phần tử của mảng ban đầu sang mảng mới.

Điểm mấu chốt là **`clone()` của mảng là sao chép nông (shallow copy), chỉ sao chép một cấp**:

- Với `int[]`, `double[]`, `boolean[]`..., các phần tử là giá trị nguyên thủy nên mỗi mảng giữ một bản giá trị riêng.
- Với `String[]`, `Person[]`, `int[][]`..., các phần tử là **tham chiếu**; `clone()` sao chép giá trị tham chiếu, **không nhân bản đối tượng được tham chiếu**.
- Với mảng nhiều chiều như `int[][]` hoặc `String[][][]`, phần tử của mảng ngoài chính là **tham chiếu tới các mảng con**. Do đó clone mảng ngoài **không clone các mảng con**.

Ví dụ trực quan:

```text
int[][] original = { {1, 2}, {3, 4} };
int[][] copy = original.clone();

original ──► mảng ngoài A ──► [tham chiếu hàng X, tham chiếu hàng Y]
copy     ──► mảng ngoài B ──► [tham chiếu hàng X, tham chiếu hàng Y]
                                          │               │
                                          ▼               ▼
                                      [1, 2]          [3, 4]
```

`original` và `copy` là hai mảng ngoài khác nhau, **nhưng `original[0] == copy[0]` và `original[1] == copy[1]` đều đúng**.

**Ghi nhớ trước:** `clone()` tạo vỏ mảng mới; nó không tự đi sâu vào các phần tử là object hay các chiều phía trong.

## 2. Mảng là trường hợp đặc biệt so với Object.clone()

Trong `java.lang.Object`, `clone()` được khai báo `protected`, trả `Object`, và cơ chế mặc định thường liên quan đến `Cloneable`. Nhưng **kiểu mảng được Java hỗ trợ đặc biệt**:

```java
int[] a = {1, 2, 3};
int[] b = a.clone();  // Không cần ép kiểu; kết quả là int[].
```

Đây là đoạn minh họa có thể đặt trong phương thức Java. Với mảng:

1. Có thể gọi `clone()` trực tiếp như một phương thức công khai.
2. Biểu thức `a.clone()` mang **kiểu mảng tương ứng** (`int[]` trong ví dụ), không bắt buộc ép từ `Object`.
3. Mảng mới khác tham chiếu với mảng gốc, có cùng `length` và cùng loại thành phần.
4. Không phải tự khai báo `implements Cloneable` cho mảng, cũng không phải bắt `CloneNotSupportedException` khi gọi `clone()` của mảng.
5. Nội dung được sao chép **một cấp**, không phải deep copy đệ quy.

Giao diện `Cloneable` là **marker interface** (không khai báo một phương thức `clone()` công khai). Không nên suy rằng mọi đối tượng triển khai `Cloneable` đều cung cấp API clone công khai thuận tiện giống mảng. Đặc biệt, với lớp tự định nghĩa, `clone()` cần được thiết kế và công bố riêng nếu thật sự muốn hỗ trợ.

## 3. Ví dụ 1: mảng nguyên thủy và mảng tham chiếu

Tạo tệp `OneDimensionalCloneDemo.java`:

```java
import java.util.Arrays;

public class OneDimensionalCloneDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};
        int[] numberCopy = numbers.clone();
        numberCopy[0] = 99;

        System.out.println(numbers == numberCopy);
        System.out.println(Arrays.toString(numbers));
        System.out.println(Arrays.toString(numberCopy));

        Box[] boxes = {new Box(10), new Box(20)};
        Box[] boxCopy = boxes.clone();

        System.out.println(boxes == boxCopy);
        System.out.println(boxes[0] == boxCopy[0]);

        boxCopy[0].value = 77;
        System.out.println(boxes[0].value);

        boxCopy[1] = new Box(88);
        System.out.println(boxes[1].value);
        System.out.println(boxCopy[1].value);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac OneDimensionalCloneDemo.java
java OneDimensionalCloneDemo
```

Kết quả:

```text
false
[1, 2, 3]
[99, 2, 3]
false
true
77
20
88
```

Diễn giải:

- `numbers` và `numberCopy` là hai mảng `int[]` riêng. Gán `numberCopy[0] = 99` không sửa phần tử `numbers[0]`, vì mỗi ô lưu trực tiếp giá trị `int`.
- `boxes` và `boxCopy` cũng là **hai mảng khác nhau**, nhưng ô số 0 của chúng chứa cùng tham chiếu `Box`. Sửa `boxCopy[0].value` chính là sửa object mà `boxes[0]` cũng trỏ đến; đầu ra là `77`.
- `boxCopy[1] = new Box(88)` chỉ **thay tham chiếu trong mảng copy**. Nó không thay ô `boxes[1]`, nên giá trị trong object gốc vẫn là `20`.

Phân biệt rõ **gán lại một ô mảng** và **sửa object nằm sau tham chiếu trong ô đó**. Đây cũng là chìa khóa để hiểu mảng nhiều chiều.

## 4. Mảng nhiều chiều thực chất là mảng của các mảng

Java không cần lưu `int[][]` như một khối hình chữ nhật liên tục. Một `int[][]` là mảng chứa tham chiếu tới các `int[]`; mỗi mảng hàng có thể dài ngắn khác nhau, thậm chí một hàng có thể là `null`. Dạng có các hàng khác độ dài thường được gọi là **jagged/ragged array**.

Xét:

```java
int[][] original = {
    {1, 2},
    {3, 4}
};
int[][] outerCopy = original.clone();
```

Đây là đoạn minh họa có thể đặt trong một phương thức. Sau câu lệnh clone:

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| `original == outerCopy` | `false` | Hai mảng ngoài là hai object |
| `original.length == outerCopy.length` | `true` | Số hàng được sao chép |
| `original[0] == outerCopy[0]` | `true` | Hai ô giữ cùng tham chiếu hàng 0 |
| `original[1] == outerCopy[1]` | `true` | Hai ô giữ cùng tham chiếu hàng 1 |
| `original[0][0] == outerCopy[0][0]` | `true` | Đang đọc cùng phần tử ở cùng mảng con |

Nếu gán `outerCopy[0][0] = 90`, mảng gốc cũng thấy `original[0][0] == 90`. Ngược lại, `outerCopy[1] = new int[] {7, 8}` chỉ thay tham chiếu đến hàng 1 **ở mảng ngoài mới**; hàng 1 của `original` vẫn giữ `{3, 4}`.

Với `int[][][]`, `clone()` cũng **chỉ sao chép chiều ngoài cùng**. Các đối tượng `int[][]` bên trong vẫn được chia sẻ, cùng với các `int[]` mà chúng đang trỏ tới.

## 5. Ví dụ 2: thay phần tử mảng con và thay cả mảng con

Tạo tệp `MultidimensionalCloneDemo.java`:

```java
import java.util.Arrays;

public class MultidimensionalCloneDemo {
    public static void main(String[] args) {
        int[][] original = {
            {1, 2},
            {3, 4}
        };

        int[][] copy = original.clone();

        System.out.println(original == copy);
        System.out.println(original[0] == copy[0]);
        System.out.println(Arrays.deepEquals(original, copy));

        copy[0][0] = 90;
        System.out.println(original[0][0]);

        copy[1] = new int[] {7, 8};
        System.out.println(Arrays.toString(original[1]));
        System.out.println(Arrays.toString(copy[1]));

        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(copy));
    }
}
```

Chạy:

```bash
javac MultidimensionalCloneDemo.java
java MultidimensionalCloneDemo
```

Kết quả:

```text
false
true
true
90
[3, 4]
[7, 8]
[[90, 2], [3, 4]]
[[90, 2], [7, 8]]
```

Đặc biệt chú ý hai thao tác có ý nghĩa rất khác:

1. **`copy[0][0] = 90`** đi xuyên qua tham chiếu được chia sẻ để sửa **phần tử của chính mảng hàng 0**. Vì thế `original[0][0]` cũng là `90`.
2. **`copy[1] = new int[] {7, 8}`** chỉ gán một tham chiếu hàng mới vào **mảng ngoài `copy`**. Mảng ngoài `original` tiếp tục trỏ đến hàng cũ `[3, 4]`.

`Arrays.deepEquals(original, copy)` ban đầu là `true` vì cấu trúc giá trị ở các hàng giống nhau. Nhưng `deepEquals` **không chứng minh rằng mảng được deep-clone**: ngay cả hai mảng còn chia sẻ tham chiếu hàng cũng có thể bằng nhau về nội dung.

## 6. Muốn copy sâu int[][] thì clone từng hàng

Đối với `int[][]` mà từng hàng chỉ chứa các giá trị nguyên thủy, có thể tạo mảng ngoài mới và clone **mỗi mảng con không phải null**. Khi đó mỗi hàng `int[]` là một object mới, dữ liệu `int` độc lập.

Tạo tệp `DeepCopyRowsDemo.java`:

```java
import java.util.Arrays;

public class DeepCopyRowsDemo {
    static int[][] copyAllRows(int[][] source) {
        if (source == null) {
            return null;
        }
        int[][] copy = source.clone();
        for (int row = 0; row < source.length; row++) {
            if (source[row] != null) {
                copy[row] = source[row].clone();
            }
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] original = {
            {1, 2},
            null,
            {3}
        };
        int[][] deepCopy = copyAllRows(original);

        System.out.println(original == deepCopy);
        System.out.println(original[0] == deepCopy[0]);
        System.out.println(deepCopy[1] == null);
        System.out.println(Arrays.deepEquals(original, deepCopy));

        deepCopy[0][0] = 42;
        System.out.println(original[0][0]);
        System.out.println(deepCopy[0][0]);
        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(deepCopy));
    }
}
```

Chạy:

```bash
javac DeepCopyRowsDemo.java
java DeepCopyRowsDemo
```

Kết quả:

```text
false
false
true
true
1
42
[[1, 2], null, [3]]
[[42, 2], null, [3]]
```

Hàm `copyAllRows` thực hiện:

1. Trả `null` nếu đầu vào `null`; đây là chính sách do ví dụ lựa chọn.
2. Sao chép mảng ngoài bằng `source.clone()`.
3. Duyệt các hàng, sao chép từng `int[]` bằng `clone()`, giữ nguyên hàng `null`.
4. Trả một mảng mới không dùng chung **bất kỳ mảng hàng không null nào** với đầu vào, đối với trường hợp này.

Do dữ liệu bên trong cùng chỉ là `int`, việc clone từng hàng đủ để **cô lập các phần tử số** của mảng hai chiều. Với `int[][][]`, cần tiếp tục sao chép sâu thêm cấp nữa. Với `Person[][]`, clone hai cấp mảng vẫn có thể **chia sẻ các object `Person`**; nếu object có thể sửa thì cần chiến lược sao chép riêng cho object đó.

### Giới hạn quan trọng: alias nội bộ

Nếu `source[0]` và `source[1]` vốn cùng trỏ tới một mảng hàng, cách clone từng hàng ở trên sẽ tạo **hai hàng mới khác nhau**. Như vậy dữ liệu số vẫn được sao chép, nhưng quan hệ **hai ô cùng trỏ đến một object** có thể không được giữ nguyên. Khi yêu cầu là sao chép **đồ thị đối tượng** và bảo toàn các quan hệ chia sẻ/tham chiếu vòng, cần thiết kế thuật toán copy chuyên biệt (thường ghi nhớ các object đã sao chép). Không nên tuyên bố rằng mọi “deep copy” đều có cùng nghĩa trong tất cả ứng dụng.

## 7. clone(), Arrays.copyOf() và System.arraycopy() khác gì?

Một số lựa chọn khác cũng chỉ sao chép **một cấp** khi phần tử là tham chiếu.

| Cách làm | Tác dụng chính | Với `int[][]` |
| --- | --- | --- |
| `source.clone()` | Mảng mới cùng độ dài, giữ cùng loại mảng | Mảng ngoài mới, **chia sẻ các hàng** |
| `Arrays.copyOf(source, source.length)` | Tạo mảng mới và chép các phần tử, có thể chỉ định độ dài mới | Mảng ngoài mới, **chia sẻ các hàng** |
| `System.arraycopy(source, 0, dest, 0, n)` | Chép phần tử vào một mảng đích đã có | Chép **tham chiếu hàng**, không clone hàng |
| `source.clone()` rồi clone từng `source[row]` | Tạo mảng ngoài và từng hàng mới | Các hàng `int[]` độc lập |

Các phương thức trên không tự clone mọi object nằm sau tham chiếu. Dùng `Arrays.copyOf` thay `clone` không phải cách “sửa” chia sẻ mảng con.

Ví dụ minh họa độc lập về ý nghĩa (đặt trong phương thức):

```java
int[][] source = {{1}, {2}};
int[][] viaCopyOf = Arrays.copyOf(source, source.length);
int[][] viaArrayCopy = new int[source.length][];
System.arraycopy(source, 0, viaArrayCopy, 0, source.length);

System.out.println(source[0] == viaCopyOf[0]);    // true
System.out.println(source[0] == viaArrayCopy[0]); // true
```

Đoạn trên cần `import java.util.Arrays;`; kết quả hai lệnh `println` đều là `true`.

Cũng nên phân biệt với các phương thức hỗ trợ xem hoặc so nội dung:

- `Arrays.toString(int[])` hiển thị một chiều, ví dụ `[1, 2]`.
- `Arrays.deepToString(Object[])` hữu ích để hiển thị mảng nhiều chiều, ví dụ `[[1, 2], [3, 4]]`.
- `Arrays.deepEquals(Object[], Object[])` so sánh đệ quy **nội dung các mảng lồng nhau**; **không cho biết** hai mảng có dùng chung các mảng con hay không.
- `Arrays.equals(Object[], Object[])` trên `int[][]` so các phần tử hàng theo `equals`; vì mảng `int[]` thông thường không định nghĩa equality theo nội dung, hai hàng khác tham chiếu sẽ không bằng nhau theo phép so này dù chứa cùng các số. Dùng `Arrays.deepEquals` khi cần so cấu trúc mảng nhiều chiều theo giá trị phần tử.

## 8. Kiểm tra alias đúng cách

Khi cần xác minh bản sao có thật sự độc lập hay không, hãy kiểm tra **tham chiếu** và thực hiện một phép sửa có kiểm soát, thay vì chỉ kiểm tra nội dung in ra:

```java
int[][] a = {{1, 2}};
int[][] b = a.clone();

System.out.println(a == b);       // false: khác mảng ngoài
System.out.println(a[0] == b[0]); // true: cùng mảng con
```

Đây là đoạn minh họa chạy trong một phương thức Java.

Nếu sau này chỉ thay `b[0]` bằng một `int[]` khác, `a[0]` không tự thay theo. Nhưng khi thay `b[0][0]`, bạn sửa object hàng vốn đang được dùng chung.

**Cẩn trọng khi nhiều luồng cùng truy cập:** vì clone nông có thể chia sẻ các phần tử mutable, hai mảng khác tham chiếu không có nghĩa là hai luồng đã được cách ly. Việc tạo một bản clone cũng không cung cấp đồng bộ hóa hoặc snapshot nguyên tử khi luồng khác đang sửa dữ liệu đồng thời.

## 9. Khi nào shallow copy đủ và khi nào cần deep copy?

**Shallow copy đủ** trong các trường hợp như:

- Mảng một chiều chứa giá trị nguyên thủy.
- Mảng chứa các object bất biến như `String`, khi ứng dụng chỉ cần tách các **ô tham chiếu** và không cần nhân bản object bất biến.
- Ứng dụng chủ ý chia sẻ các phần tử để tránh sao chép bộ nhớ, với hợp đồng rõ ràng về quyền sửa.

**Cần copy thêm các cấp** khi:

- Muốn sửa một ô trong mảng con mà **không làm thay đổi mảng gốc**.
- Muốn truyền dữ liệu cho thành phần khác mà không cho phép thành phần đó sửa các hàng gốc.
- Muốn tạo snapshot độc lập của một cấu trúc lồng nhau có thể thay đổi, với định nghĩa rõ về tính độc lập và các quan hệ tham chiếu cần bảo toàn.

Với mảng các object có thể thay đổi, clone mảng chỉ là **bước đầu**. Cần biết cách copy bản thân các object; không phải object nào cũng có `clone()`, và gọi clone đệ quy không tự động xử lý vòng tham chiếu hoặc quan hệ chia sẻ.

Nếu được thiết kế API mới, các factory, copy constructor hoặc phương thức `copy()` mô tả rõ shallow/deep semantics thường dễ hiểu hơn việc mặc định rằng `clone()` sẽ “copy hết”.

## 10. Lỗi phổ biến và cách tránh

| Nhầm lẫn | Hệ quả | Cách xử lý |
| --- | --- | --- |
| “Gọi `clone()` sẽ nhân bản mọi mảng con.” | Sửa `copy[0][0]` làm dữ liệu gốc thay đổi | Với `int[][]`, clone mảng ngoài rồi clone từng hàng |
| “Hai mảng ngoài khác nhau thì không chia sẻ dữ liệu.” | Hai mảng vẫn có thể dùng chung cùng hàng hoặc object phần tử | Kiểm tra `original[i] == copy[i]` |
| “`Arrays.copyOf` là deep copy.” | Vẫn chia sẻ các tham chiếu hàng | Xác định độ sâu cần sao chép, copy từng cấp |
| “`Arrays.deepEquals` chứng minh deep copy.” | Hai cấu trúc có thể bằng nội dung dù đang alias cùng mảng con | Kiểm tra identity và thử sửa độc lập |
| “`int[][]` luôn là hình chữ nhật.” | Dễ gặp `NullPointerException` hoặc sai chỉ số | Hỗ trợ hàng `null`/khác độ dài theo dữ liệu thật |
| “Clone `Person[][]` tới hai cấp thì Person cũng được clone.” | Các object `Person` vẫn được tham chiếu chung | Copy object phần tử bằng chính sách riêng |
| “Có `Cloneable` là gọi `clone()` công khai được.” | Với lớp thông thường, `Object.clone()` là `protected` | Dùng API sao chép do lớp công bố; mảng là trường hợp đặc biệt |
| “Cứ clone từng hàng là bảo toàn mọi quan hệ object.” | Các hàng vốn alias nhau có thể không còn alias | Khi cần bảo toàn alias/cycle, dùng thuật toán sao chép đồ thị thích hợp |

## 11. Checklist thực hành

1. **Xác định cấp sao chép cần thiết:** chỉ mảng ngoài, mọi mảng con hay cả object phần tử?
2. **Nhìn vào kiểu phần tử của từng cấp:** `int` là giá trị nguyên thủy; `int[]` và `Person` đều là đối tượng được trỏ tới bằng tham chiếu.
3. **Đối với mảng nhiều chiều, nhớ rằng `clone()` chỉ sao chép mảng đầu tiên.**
4. **Kiểm tra `null` và mảng ragged:** không giả định mọi hàng đều có cùng độ dài hoặc khác `null`.
5. **Kiểm thử cả sửa nội dung và gán lại tham chiếu:** `copy[i][j] = value` khác `copy[i] = newRow`.
6. **Phân biệt `==` và `Arrays.deepEquals`:** phép đầu kiểm tra cùng object; phép sau kiểm tra giá trị lồng nhau.
7. **Giữ hợp đồng ownership rõ ràng:** bên nhận có được sửa object/mảng con được chia sẻ không?
8. **Nếu cần bản sao đồ thị**, thiết kế cách xử lý chia sẻ tham chiếu, chu trình và trạng thái mutable trước khi code.

**Tự kiểm tra:**

- `int[] a = {1}; int[] b = a.clone(); b[0] = 2;` thì `a[0]` là bao nhiêu? **1**, vì hai mảng nguyên thủy riêng biệt.
- `int[][] a = {{1}}; int[][] b = a.clone(); b[0][0] = 2;` thì `a[0][0]` là bao nhiêu? **2**, vì hai mảng ngoài cùng giữ tham chiếu tới mảng con.
- `b[0] = new int[] {9};` sau khi clone mảng ngoài có làm `a[0]` trỏ đến mảng mới không? **Không**, vì chỉ thay ô của mảng ngoài `b`.
- `Arrays.deepEquals(a, b)` trả `true` thì có chắc `a` và `b` độc lập không? **Không**, phép so chỉ xét nội dung.
- Với `int[][]`, muốn sửa hàng của bản sao mà không sửa hàng gốc cần gì? **Sao chép mảng ngoài và từng hàng `int[]` không null**.

**Ghi nhớ:** Mảng Java có `clone()` tiện lợi, nhưng **clone mảng chỉ sao chép một cấp**. Một `int[][]` là một mảng chứa tham chiếu tới các mảng `int[]`, vì vậy clone mảng ngoài vẫn dùng chung các hàng. Muốn bản sao độc lập ở cấp nào, hãy sao chép rõ ràng ở cấp đó.