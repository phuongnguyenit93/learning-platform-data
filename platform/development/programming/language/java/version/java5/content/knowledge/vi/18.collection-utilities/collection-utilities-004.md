# Arrays.equals và Arrays.deepEquals

Hai mảng khác nhau có thể chứa cùng dữ liệu. Tuy nhiên, gọi `a.equals(b)` trên mảng không tự so sánh nội dung: mảng dùng phép bằng nhau theo đối tượng mà nó kế thừa từ `Object`.

Để so sánh dữ liệu, cần chọn mức độ phù hợp:

- `Arrays.equals`: so sánh từng phần tử ở một tầng.
- `Arrays.deepEquals`: đi sâu khi các phần tử tương ứng cũng là mảng.
- `Objects.deepEquals`: một điểm vào nhận `Object`, có hỗ trợ trường hợp đối số thực tế là mảng.

Cả hai cách so sánh nội dung đều có xét thứ tự và độ dài. Chúng không coi mảng như một tập hợp không thứ tự.

## 1. Tham chiếu bằng nhau khác nội dung bằng nhau

```java
int[] a = {1, 2};
int[] b = {1, 2};
```

Hai biểu thức khởi tạo tạo hai đối tượng mảng khác nhau:

| Biểu thức | Kết quả |
| --- | --- |
| `a == b` | `false` |
| `a.equals(b)` | `false` |
| `Arrays.equals(a, b)` | `true` |

Đoạn này minh họa trong một phương thức có import `java.util.Arrays`.

`==` trả lời hai tham chiếu có trỏ đến cùng đối tượng không. Mảng không override `Object.equals` để chuyển sang so sánh nội dung, nên `a.equals(b)` cũng không giải quyết yêu cầu đó.

Nếu viết `int[] alias = a;`, `a == alias` là `true` vì chúng trỏ đến cùng một mảng. Điều này khác với hai mảng có các ô chứa cùng giá trị.

## 2. Arrays.equals so sánh một tầng

Với hai mảng nguyên thủy cùng loại, ví dụ `int[]`, phương thức kiểm tra độ dài và giá trị ở từng chỉ số tương ứng:

```java
Arrays.equals(new int[] {1, 2}, new int[] {1, 2}); // true
Arrays.equals(new int[] {1, 2}, new int[] {2, 1}); // false
Arrays.equals(new int[] {1, 2}, new int[] {1});    // false
```

Các dòng là biểu thức minh họa, không phải một chương trình chạy độc lập.

Với overload hai mảng `Object[]`, các phần tử được so bằng quy tắc `equals` tương ứng và xử lý null:

```java
String[] left = {"java", null};
String[] right = {"java", null};
boolean same = Arrays.equals(left, right); // true
```

Hai phần tử null tại cùng vị trí được coi là bằng nhau. Một bên null và bên kia khác null thì không bằng nhau.

Nhưng nếu phần tử của mảng ngoài lại là một mảng, `equals` của chính mảng con vẫn là so sánh tham chiếu. Vì vậy, so sánh một tầng thường chưa đủ cho mảng nhiều chiều.

## 3. Mảng nhiều chiều cần xét mảng con

Xét:

```java
int[][] first = {{1, 2}, {3}};
int[][] second = {{1, 2}, {3}};
```

Mảng `int[][]` là một mảng có các phần tử mang kiểu `int[]`. Hai lần khởi tạo trên có các mảng con riêng.

`Arrays.equals(first, second)` so sánh một tầng: hai phần tử đầu đều là `int[]`, nhưng chúng là hai đối tượng khác nhau. Kết quả là `false`.

`Arrays.deepEquals(first, second)` nhận hai mảng ngoài như `Object[]`, rồi đi sâu:

1. Độ dài mảng ngoài phải bằng nhau.
2. Nếu hai phần tử tương ứng đều là mảng đối tượng, tiếp tục so sánh sâu.
3. Nếu chúng là các mảng nguyên thủy cùng loại, dùng phép so sánh nội dung phù hợp với loại đó.
4. Nếu là các đối tượng thông thường, dùng `equals`.
5. Xử lý null tương ứng.

Trong ví dụ, các mảng `int[]` cùng chứa dữ liệu bằng nhau, nên kết quả sâu là `true`.

Mảng nhiều chiều không cần có dạng hình chữ nhật để so sánh sâu. Mảng con có thể có độ dài khác nhau giữa các hàng, nhưng các hàng ở cùng vị trí của hai phía phải có nội dung và cấu trúc tương ứng bằng nhau.

## 4. deepEquals nhận Object[], không nhận trực tiếp int[]

Chữ ký chính:

```java
boolean Arrays.deepEquals(Object[] a1, Object[] a2);
```

Đây là mô tả API, không phải cú pháp khai báo phương thức để chép vào lớp.

`int[][]` dùng được vì mảng ngoài chứa các tham chiếu mảng con. `int[]` thì không phải `Object[]`; nó chứa các giá trị nguyên thủy.

Vì vậy:

```java
int[] a = {1, 2};
int[] b = {1, 2};

boolean flat = Arrays.equals(a, b);
// Arrays.deepEquals(a, b); // Không biên dịch: int[] không phải Object[].
```

Với hai biến có kiểu khai báo `Object` và có thể chứa mảng, `Objects.deepEquals(a, b)` là một lựa chọn API phù hợp hơn cho điểm vào tổng quát.

Không ép `int[]` thành `Object[]` để né chữ ký. Hai kiểu đó không tương thích; phép ép qua `Object` vẫn có thể thất bại lúc chạy.

### Không tự boxing hoặc mở rộng kiểu mảng

`int[] {1, 2}` không tự biến thành `Integer[] {1, 2}` để so sánh sâu. Tương tự, `int[]` và `long[]` là hai loại mảng khác nhau dù các số được in ra có vẻ giống nhau.

`Arrays.deepEquals` trên hai mảng `Object[]` chứa lần lượt `int[]` và `long[]` sẽ không coi hai mảng con ấy là bằng nhau.

Khi phần tử là `Integer` và `Long`, `equals` của kiểu bao cũng không tự coi `Integer.valueOf(1)` bằng `Long.valueOf(1)`. Nếu nghiệp vụ cần so số khác kiểu theo một chuẩn chung, phải viết quy tắc so sánh riêng.

## 5. Chương trình hoàn chỉnh

Ví dụ chạy trên Java 17+, kiểm chứng cả so sánh một tầng, mảng lồng, null và số thực.

Lưu thành `ArrayEqualityDemo.java`:

```java
import java.util.Arrays;
import java.util.Objects;

public class ArrayEqualityDemo {
    record Box(int[] data) {
    }

    public static void main(String[] args) {
        int[] a = {1, 2};
        int[] b = {1, 2};
        System.out.println("same reference: " + (a == b));
        System.out.println("array equals method: " + a.equals(b));
        System.out.println("flat Arrays.equals: " + Arrays.equals(a, b));
        System.out.println("reordered: "
                + Arrays.equals(a, new int[] {2, 1}));

        String[] wordsA = {"java", null};
        String[] wordsB = {"java", null};
        System.out.println("words with null: "
                + Arrays.equals(wordsA, wordsB));

        int[][] matrixA = {{1, 2}, {3}};
        int[][] matrixB = {{1, 2}, {3}};
        System.out.println("matrix shallow: "
                + Arrays.equals(matrixA, matrixB));
        System.out.println("matrix deep: "
                + Arrays.deepEquals(matrixA, matrixB));

        Object[] nestedA = {new int[] {1, 2}, new String[] {"x", null}};
        Object[] nestedB = {new int[] {1, 2}, new String[] {"x", null}};
        System.out.println("mixed nested: "
                + Arrays.deepEquals(nestedA, nestedB));

        Object[] ints = {new int[] {1, 2}};
        Object[] longs = {new long[] {1, 2}};
        System.out.println("different primitive array types: "
                + Arrays.deepEquals(ints, longs));

        int[] missingA = null;
        int[] missingB = null;
        System.out.println("two null arrays: "
                + Arrays.equals(missingA, missingB));
        System.out.println("null versus empty: "
                + Arrays.equals(missingA, new int[0]));

        Object asObjectA = a;
        Object asObjectB = b;
        System.out.println("Objects.deepEquals: "
                + Objects.deepEquals(asObjectA, asObjectB));

        System.out.println("NaN arrays: "
                + Arrays.equals(new double[] {Double.NaN},
                                new double[] {Double.NaN}));
        System.out.println("signed zero arrays: "
                + Arrays.equals(new double[] {0.0},
                                new double[] {-0.0}));

        Object[] boxesA = {new Box(new int[] {1, 2})};
        Object[] boxesB = {new Box(new int[] {1, 2})};
        System.out.println("arrays inside ordinary objects: "
                + Arrays.deepEquals(boxesA, boxesB));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 ArrayEqualityDemo.java
java ArrayEqualityDemo
```

Stdout:

```text
same reference: false
array equals method: false
flat Arrays.equals: true
reordered: false
words with null: true
matrix shallow: false
matrix deep: true
mixed nested: true
different primitive array types: false
two null arrays: true
null versus empty: false
Objects.deepEquals: true
NaN arrays: true
signed zero arrays: false
arrays inside ordinary objects: false
```

## 6. Null: dùng đúng overload

Với các overload so sánh toàn bộ hai mảng được dùng trong bài:

| Đối số | Kết quả |
| --- | --- |
| Cùng một tham chiếu mảng | `true` |
| Hai tham chiếu đều null | `true` |
| Chỉ một tham chiếu null | `false` |
| Hai mảng rỗng cùng loại phù hợp | `true` |
| Null và mảng rỗng | `false` |

Trong chương trình, biến được khai báo `int[]` giúp chọn overload rõ ràng. Viết `Arrays.equals(null, null)` trực tiếp có thể gây nhập nhằng vì có nhiều overload cho các loại mảng.

`Arrays.deepEquals(null, null)` không có cùng vấn đề lựa chọn các overload mảng nguyên thủy như `Arrays.equals`, nhưng trong mã thật vẫn nên thể hiện rõ kiểu dữ liệu đầu vào.

Các overload so sánh theo đoạn chỉ số có hợp đồng kiểm tra đối số và giới hạn riêng; không chuyển nguyên mọi quy tắc null của overload hai mảng toàn phần sang các dạng theo đoạn.

## 7. “Deep” không có nghĩa là duyệt mọi trường của mọi đối tượng

Trong chương trình, hai `Box` đều chứa `int[] {1, 2}`, nhưng:

```java
Arrays.deepEquals(boxesA, boxesB)
```

trả `false`.

Khi đi đến phần tử `Box`, phương thức không mở mọi trường của record bằng reflection. Nó gọi `equals` của `Box`. `equals` được tạo mặc định cho record với thành phần mảng không tự chuyển sang so sánh nội dung mảng.

Nếu mô hình nghiệp vụ coi hai `Box` có mảng dữ liệu bằng nhau là cùng giá trị, cần triển khai `equals` và `hashCode` của kiểu đó theo cùng hợp đồng, hoặc dùng cách biểu diễn giá trị khác.

Điều tương tự áp dụng cho các lớp tự định nghĩa khác: chất lượng của `deepEquals` tại các lá đối tượng phụ thuộc vào hợp đồng `equals` của chúng.

### Không dùng như bộ so sánh đồ thị có chu trình

Mảng đối tượng có thể trực tiếp hoặc gián tiếp chứa chính nó:

```java
Object[] cycle = new Object[1];
cycle[0] = cycle;
```

Không dùng `Arrays.deepEquals` như một thuật toán so sánh tổng quát có phát hiện chu trình. Hành vi với cấu trúc tự chứa nằm ngoài bảo đảm được định nghĩa cho phép so sánh sâu này. Nếu dữ liệu có chu trình, cần thuật toán có theo dõi các nút đã thăm và một định nghĩa bằng nhau phù hợp.

So sánh sâu nội dung cũng không mặc nhiên kiểm tra rằng hai cấu trúc có cùng cách chia sẻ đối tượng con. Hai hàng dùng chung một mảng con và hai hàng dùng hai mảng con riêng nhưng cùng dữ liệu có thể cho cùng kết quả nội dung.

## 8. Số thực: NaN và số không có dấu

Với `double[]` và tương tự `float[]`, `Arrays.equals` dùng quy tắc phù hợp với phép bằng nhau của kiểu bao tương ứng:

- Các giá trị NaN được coi là bằng nhau trong phép so sánh mảng.
- `0.0` và `-0.0` được phân biệt.

Điều này khác với việc viết một vòng lặp chỉ dùng `==` cho từng `double`: `Double.NaN == Double.NaN` là `false`, còn `0.0 == -0.0` là `true`.

Nếu cần so sánh gần đúng theo sai số số học, `Arrays.equals` và `deepEquals` không tự cung cấp chính sách đó. Cần định nghĩa ngưỡng, cách xử lý NaN/vô cực và viết phép so sánh thích hợp.

## 9. Phối hợp với hashCode

Khi một kiểu định nghĩa bằng nhau theo nội dung mảng, hàm băm cần dùng quy tắc tương ứng:

| Cách so sánh | Cách tạo hash thường đi cùng |
| --- | --- |
| `Arrays.equals` một tầng | `Arrays.hashCode` của loại mảng tương ứng |
| `Arrays.deepEquals` cho mảng lồng | `Arrays.deepHashCode` |

Hai giá trị bằng nhau phải có hash bằng nhau. Chiều ngược lại không đúng: hash trùng không chứng minh hai mảng bằng nhau.

Nếu mảng tham gia `equals/hashCode` của một khóa trong `HashMap` hoặc `HashSet`, sửa nội dung sau khi đưa khóa vào cấu trúc có thể làm việc tìm lại sai kỳ vọng. Cần bảo vệ tính ổn định dữ liệu khóa, chẳng hạn bằng bản sao phòng vệ và cách truy cập phù hợp.

## 10. Chọn phép so sánh và đánh giá chi phí

| Dữ liệu | Lựa chọn ban đầu |
| --- | --- |
| `int[]`, `byte[]`... cần so nội dung | `Arrays.equals` đúng overload |
| `String[]` cần so chuỗi theo vị trí | `Arrays.equals` |
| `int[][]`, `Object[]` chứa mảng lồng | `Arrays.deepEquals` |
| Hai biến `Object` có thể chứa mảng | `Objects.deepEquals`, theo hợp đồng của nó |
| Các đối tượng tự định nghĩa chứa trường mảng | Xem lại `equals/hashCode` của chính kiểu đó |
| Dữ liệu số cần gần đúng | Phép so sánh riêng theo sai số |
| Không quan tâm thứ tự | Định nghĩa chính sách khác; không dùng trực tiếp equals mảng |

So sánh một tầng thường cần `O(n)` trong trường hợp phải đọc hết mảng; có thể dừng sớm khi phát hiện khác biệt. So sánh sâu còn phụ thuộc tổng dữ liệu mảng được thăm và chi phí `equals` của các đối tượng lá. Không coi nó là thao tác hằng chỉ vì được gói trong một lời gọi thư viện.

## 11. Tự kiểm tra

1. Hai `int[]` riêng nhưng cùng dữ liệu có được `a.equals(b)` coi là bằng nhau không?
2. Vì sao `Arrays.equals` có thể trả false với hai `int[][]` cùng số?
3. Gọi trực tiếp `Arrays.deepEquals` với hai `int[]` có hợp lệ không?
4. Deep equals có tự so trường mảng bên trong mọi record không?
5. Hai mảng `double[]` chứa NaN cùng vị trí có thể bằng nhau không?
6. Hash bằng nhau có đủ để khẳng định deep equals không?

Đáp án:

1. Không, nếu đó là hai đối tượng khác nhau.
2. Nó chỉ so một tầng, nên mảng con được so bằng tham chiếu.
3. Không; dùng `Arrays.equals` hoặc điểm vào phù hợp như `Objects.deepEquals`.
4. Không; đến đối tượng thông thường nó dựa vào `equals`.
5. Có, theo quy tắc so sánh của overload số thực.
6. Không; có thể có va chạm hash.

## Tài liệu đối chiếu

Xem các overload [Arrays.equals và Arrays.deepEquals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html), điểm vào [Objects.deepEquals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#deepEquals(java.lang.Object,java.lang.Object)) và [JLS 21 §10.7 — Array Members](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html#jls-10.7).
