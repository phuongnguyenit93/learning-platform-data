# `Objects.deepEquals()` khác `Objects.equals()` ở đối số mảng

## 1. Mục tiêu: phân biệt tham chiếu mảng với nội dung mảng

`java.util.Objects` cung cấp hai phương thức tĩnh đều nhận hai đối số kiểu `Object` và đều xử lý `null` an toàn:

```java
Objects.equals(a, b);
Objects.deepEquals(a, b);
```

**Điểm khác biệt cốt lõi:** khi hai đối số là **hai mảng khác tham chiếu**, `Objects.equals(a, b)` dựa trên `equals` thông thường của đối tượng; mảng Java không override `Object.equals`, nên phép so sánh là **theo danh tính**. Ngược lại, `Objects.deepEquals(a, b)` có cơ chế so sánh **nội dung mảng**, đệ quy qua các cấp mảng lồng nhau và xử lý cả mảng kiểu nguyên thủy.

```java
int[] first = {1, 2, 3};
int[] second = {1, 2, 3};

System.out.println(first == second);                  // false
System.out.println(Objects.equals(first, second));    // false
System.out.println(Objects.deepEquals(first, second)); // true
```

Đây là đoạn minh họa đặt trong phương thức có `import java.util.Objects;`, chưa phải chương trình độc lập. Hai lần tạo mảng sinh hai đối tượng mảng riêng biệt. Chúng chứa cùng dữ liệu nhưng không trỏ tới cùng một vùng đối tượng, vì vậy hai cách so sánh cho kết quả khác nhau.

Nên đọc chữ *deep* ở đây là **so sánh sâu cấu trúc mảng**. Nó không có nghĩa rằng mọi `List`, `record`, bean hoặc đối tượng nghiệp vụ lồng bên trong đều được thư viện soi từng trường một cách tự động.

## 2. Hành vi theo loại đối số

| Trường hợp `a`, `b` | `Objects.equals(a,b)` | `Objects.deepEquals(a,b)` |
| --- | --- | --- |
| Cả hai là `null` | `true` | `true` |
| Chỉ một bên là `null` | `false` | `false` |
| Cùng một tham chiếu không `null` | `true` | `true` |
| Hai đối tượng thông thường, không phải mảng | Sử dụng `a.equals(b)` | Cũng sử dụng `a.equals(b)` |
| Hai mảng `int[]` riêng biệt có cùng phần tử | `false` | `true` |
| Hai mảng `String[]` riêng biệt có cùng chuỗi | `false` | `true` |
| Hai mảng `int[][]` riêng biệt cùng cấu trúc/số | `false` | `true` |
| Hai `List<int[]>` riêng biệt nhưng chứa các mảng cùng số | Thông thường `false` | Vẫn `false`, vì `List.equals` không so sâu nội dung phần tử mảng |
| Hai kiểu record có component là hai mảng riêng biệt | Thông thường `false` | Vẫn `false`, vì record tự sinh `equals` so component mảng theo tham chiếu |

Bảng giả định những trường hợp mang chữ "riêng biệt" không chia sẻ tham chiếu mảng tương ứng, và các đối tượng/lớp dùng quy tắc `equals` thông thường. Một lớp tùy biến hoàn toàn có thể override `equals` với ngữ nghĩa riêng.

`Objects.deepEquals` không yêu cầu các đối số phải khai báo là kiểu mảng ở compile time: chữ ký nhận `Object`. Vì vậy, nó là cách thuận tiện để so sánh hai đối tượng mà tại runtime hóa ra lại là `byte[]`, `int[]`, `Object[]` hoặc một dạng mảng lồng nhau.

## 3. Cách `Objects.equals()` hoạt động

Ở mức ngữ nghĩa, `Objects.equals(a, b)` gần tương đương:

```java
return a == b || (a != null && a.equals(b));
```

Đoạn trên minh họa logic trong một phương thức có hai tham số `a`, `b`; không phải chương trình độc lập.

- Nếu `a == b`, kể cả cùng `null`, trả `true`.
- Nếu `a == null` còn `b != null`, trả `false`, không gọi phương thức trên `null`.
- Trong những trường hợp còn lại, kết quả phụ thuộc `a.equals(b)` và hợp đồng `equals` của kiểu thực tế.

Các lớp `String`, nhiều lớp số bao, `List` và kiểu `record` thường có quy tắc bằng nhau theo giá trị. Nhưng **mảng Java không override `equals`**, nên hai mảng khác tham chiếu sẽ không được xem là bằng nhau bởi `Objects.equals`, dù số phần tử và nội dung trùng khớp.

```java
String a = new String("java");
String b = new String("java");
System.out.println(Objects.equals(a, b)); // true

int[] x = {1, 2};
int[] y = {1, 2};
System.out.println(Objects.equals(x, y)); // false
```

Đoạn minh họa này cần `import java.util.Objects;`. Kết quả của hai nhóm khác nhau là vì chính **kiểu phần tử được so sánh** có hay không có quy tắc `equals` theo giá trị, chứ không phải vì `Objects.equals` tự phân biệt String với số.

## 4. Cách `Objects.deepEquals()` xét mảng và mảng lồng nhau

Sau khi xử lý trường hợp hai tham chiếu giống nhau hoặc `null`, `Objects.deepEquals` nhận diện mảng theo kiểu runtime và so sánh các phần tử tương ứng:

1. **Hai mảng kiểu nguyên thủy cùng loại**, chẳng hạn `byte[]` với `byte[]` hoặc `int[]` với `int[]`: so sánh độ dài và nội dung theo vị trí, tương đương phương thức `Arrays.equals` thích hợp.
2. **Hai mảng tham chiếu `Object[]`**, bao gồm `String[]`, `Object[][]`, `int[][]`: so sánh số phần tử rồi lần lượt so sâu từng cặp phần tử; nếu một cặp phần tử lại là mảng, phép so sánh tiếp tục tại cấp đó.
3. **Hai giá trị không phải cặp mảng tương thích:** quay về `equals` thông thường của đối tượng bên trái. Đối với các mảng có kiểu nguyên thủy khác nhau, ví dụ `int[]` và `long[]`, sẽ không được coi là bằng nhau chỉ vì cùng các số biểu diễn.
4. **Các lớp đối tượng bên trong không phải mảng:** vẫn sử dụng hợp đồng `equals` riêng của lớp đó, không tự lấy reflection để so từng trường.

Tư duy thuật toán (pseudocode, **không phải mã nguồn thực của JDK**):

```text
deepEqual(a, b):
    nếu a và b cùng tham chiếu: true
    nếu chỉ một bên null: false
    nếu hai bên là mảng primitive cùng loại:
        so sánh cùng chiều dài và từng giá trị ở từng vị trí
    nếu hai bên đều là Object[]:
        so sánh độ dài và deepEqual trên từng cặp phần tử
    còn lại:
        a.equals(b)
```

**Thứ tự và độ dài luôn quan trọng.** Hai mảng `{1, 2}` và `{2, 1}` không bằng nhau theo `deepEquals`; `{1, 2}` và `{1, 2, 2}` cũng không bằng nhau.

**Mảng tham chiếu khác component type vẫn có thể so sâu bằng nhau.** Chẳng hạn, một `String[]` và một `Object[]` đều chứa `"a", "b"` có thể cho `true`, bởi cả hai là `Object[]` ở runtime và từng phần tử tương ứng bằng nhau. Ngược lại, `int[]` và `long[]` có cùng biểu diễn số không bằng nhau bởi chúng là hai kiểu mảng nguyên thủy khác nhau.

### Mảng nhiều chiều và mảng răng cưa

```java
int[][] m1 = {{1, 2}, {3}};
int[][] m2 = {{1, 2}, {3}};
int[][] m3 = {{1}, {2, 3}};

System.out.println(Objects.deepEquals(m1, m2)); // true
System.out.println(Objects.deepEquals(m1, m3)); // false
```

Mảng hai chiều trong Java thực chất là **mảng chứa các mảng**. `int[][]` có thể được xử lý như một `Object[]` mà mỗi phần tử là `int[]`; từ đó quá trình so sâu đi tiếp từng hàng. Đoạn minh họa cần import `Objects`.

Nếu cấu trúc chứa mảng tham chiếu lồng thêm các mảng `boolean[]`, `double[]`, `char[]` hoặc mảng tham chiếu khác, quy tắc tương ứng vẫn áp dụng tại vị trí của từng mảng. Tuy nhiên, với các cấu trúc mảng **tự tham chiếu vòng** hoặc chứa các vòng tham chiếu gián tiếp, không nên giả định thuật toán đệ quy sẽ dừng an toàn; hợp đồng `Arrays.deepEquals` không dành cho các cấu trúc chứa chu trình kiểu đó.

## 5. Phân biệt với `Arrays.equals()` và `Arrays.deepEquals()`

`java.util.Arrays` cung cấp các phương thức cụ thể dành cho mảng. Chọn phương thức phù hợp với **mức cấu trúc cần so sánh**:

| API | Đối số nhận vào | Cơ chế |
| --- | --- | --- |
| `Objects.equals(Object,Object)` | Hai tham chiếu bất kỳ | Xử lý `null` rồi gọi `equals` bình thường. |
| `Objects.deepEquals(Object,Object)` | Hai tham chiếu bất kỳ | Xử lý `null`, so sâu nếu là cặp mảng thích hợp; ngoài mảng dùng `equals`. |
| `Arrays.equals(int[],int[])` và các overload primitive | Hai mảng primitive cùng kiểu | So **giá trị từng phần tử** theo thứ tự. |
| `Arrays.equals(Object[],Object[])` | Hai mảng tham chiếu | So từng phần tử bằng `Objects.equals` (mảng lồng trong phần tử vẫn được so theo tham chiếu). |
| `Arrays.deepEquals(Object[],Object[])` | Hai mảng tham chiếu | So đệ quy cả các phần tử là mảng. |

Ví dụ:

```java
int[][] x = {{1, 2}, {3, 4}};
int[][] y = {{1, 2}, {3, 4}};

System.out.println(Arrays.equals(x, y));      // false
System.out.println(Arrays.deepEquals(x, y));  // true
System.out.println(Objects.deepEquals(x, y)); // true
```

Đoạn minh họa cần `import java.util.Arrays;` và `import java.util.Objects;`.

Lý do: `int[][]` là mảng các phần tử `int[]`; `Arrays.equals(x,y)` chọn overload `Object[]` và so từng **tham chiếu hàng**, trong khi `Arrays.deepEquals` đi sâu vào mỗi hàng. Còn `Objects.deepEquals` thuận tiện vì nhận `Object` và tự xử lý kiểu mảng runtime.

**Một bẫy cú pháp:** `Arrays.deepEquals` nhận hai `Object[]`, do đó **không gọi trực tiếp** được với hai biến `int[]`:

```java
// Arrays.deepEquals(new int[]{1}, new int[]{1}); // Không biên dịch!
System.out.println(Arrays.equals(new int[]{1}, new int[]{1})); // true
System.out.println(Objects.deepEquals(
        new int[]{1}, new int[]{1}));                       // true
```

Với hai `int[]` một chiều, `Arrays.equals` thường là API rõ ý định nhất.

## 6. Ví dụ hoàn chỉnh Java 17: kiểm tra các trường hợp biên

Lưu toàn bộ chương trình sau vào tệp `ObjectsDeepEqualsDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class ObjectsDeepEqualsDemo {
    record Box(int[] values) {}

    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        int[] b = {1, 2, 3};

        System.out.println("same reference: " + (a == b));
        System.out.println("equals int[]: " + Objects.equals(a, b));
        System.out.println("deepEquals int[]: " + Objects.deepEquals(a, b));
        System.out.println("Arrays.equals int[]: " + Arrays.equals(a, b));

        int[][] matrixA = {{1, 2}, {3, 4}};
        int[][] matrixB = {{1, 2}, {3, 4}};

        System.out.println("equals int[][]: "
                + Objects.equals(matrixA, matrixB));
        System.out.println("Arrays.equals int[][]: "
                + Arrays.equals(matrixA, matrixB));
        System.out.println("deepEquals int[][]: "
                + Objects.deepEquals(matrixA, matrixB));
        System.out.println("Arrays.deepEquals int[][]: "
                + Arrays.deepEquals(matrixA, matrixB));

        Object[] mixedA = {
                new byte[]{1, 2}, new String[]{"x", "y"}, null
        };
        Object[] mixedB = {
                new byte[]{1, 2}, new String[]{"x", "y"}, null
        };
        System.out.println("mixed nested arrays: "
                + Objects.deepEquals(mixedA, mixedB));

        System.out.println("different primitive types: "
                + Objects.deepEquals(new int[]{1}, new long[]{1}));

        List<int[]> listA = List.of(new int[]{1, 2});
        List<int[]> listB = List.of(new int[]{1, 2});
        System.out.println("list of arrays: "
                + Objects.deepEquals(listA, listB));

        Object[] outerA = {List.of(new int[]{1, 2})};
        Object[] outerB = {List.of(new int[]{1, 2})};
        System.out.println("array with nested list: "
                + Objects.deepEquals(outerA, outerB));

        Box boxA = new Box(new int[]{1, 2});
        Box boxB = new Box(new int[]{1, 2});
        System.out.println("record containing array: "
                + Objects.deepEquals(boxA, boxB));
        System.out.println("record component arrays: "
                + Objects.deepEquals(boxA.values(), boxB.values()));

        System.out.println("both null: "
                + Objects.deepEquals(null, null));
        System.out.println("one null: "
                + Objects.deepEquals(null, a));
        System.out.println("ordinary strings: "
                + Objects.deepEquals("java", new String("java")));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac ObjectsDeepEqualsDemo.java
java ObjectsDeepEqualsDemo
```

Stdout:

```text
same reference: false
equals int[]: false
deepEquals int[]: true
Arrays.equals int[]: true
equals int[][]: false
Arrays.equals int[][]: false
deepEquals int[][]: true
Arrays.deepEquals int[][]: true
mixed nested arrays: true
different primitive types: false
list of arrays: false
array with nested list: false
record containing array: false
record component arrays: true
both null: true
one null: false
ordinary strings: true
```

Cách đọc các kết quả quan trọng:

- `Objects.equals(a,b)` là `false` vì `int[]` dùng `Object.equals` theo tham chiếu. `Objects.deepEquals(a,b)` là `true` vì từng số ở vị trí tương ứng bằng nhau.
- `Arrays.equals(matrixA,matrixB)` là `false`: đây là so sánh *nông* các phần tử hàng `int[]`. Hai cách so sâu đều cho `true`.
- `mixedA` và `mixedB` là mảng `Object[]` chứa `byte[]`, `String[]` và `null`; mọi cặp phần tử tương ứng đều so sâu bằng nhau.
- `new int[]{1}` với `new long[]{1}` không phải hai mảng cùng loại, nên `deepEquals` trả `false`.
- Hai `List<int[]>` không tự trở thành phép so sâu mảng. `List.equals` gọi `equals` của phần tử `int[]`, tức so tham chiếu, dẫn đến `false`. Dù list nằm bên trong một `Object[]`, `deepEquals` cũng chỉ ủy quyền cho `List.equals` tại lớp list đó.
- Hai record `Box` khác tham chiếu có component là hai mảng mới: `record.equals` mặc định dùng quy tắc bằng nhau của component mảng, tức theo tham chiếu. Muốn so nội dung mảng, phải gọi `Objects.deepEquals` lên **chính các component mảng**, hoặc tự cài đặt quy tắc bằng nhau sâu cho kiểu bao ngoài.
- Cả hai `null` cho `true`; một `null` cho `false`, không cần tự xử lý điều kiện null trước khi gọi `Objects.deepEquals`.

## 7. Vì sao `deepEquals` không tự so sâu mọi đối tượng chứa mảng?

Xét hai kiểu dữ liệu:

```java
record Snapshot(int[] bytes) {}
record CollectionBox(List<int[]> items) {}
```

Đây là hai khai báo record Java 17 có thể đặt ở cấp top-level, không phải chương trình độc lập.

Trong `Snapshot`, phương thức `equals` tự sinh chỉ so component `bytes` theo quy tắc của chính component. Vì `bytes` là mảng, quy tắc đó là **so tham chiếu**; `Objects.deepEquals(new Snapshot(...), new Snapshot(...))` không dùng reflection để khám phá component và không sửa hành vi này.

Trong `CollectionBox`, `equals` tự sinh gọi `List.equals` đối với `items`. `List.equals` so các phần tử theo vị trí, nhưng phần tử ở đây là `int[]`, nên các mảng khác tham chiếu vẫn không bằng nhau. Việc dùng `Objects.deepEquals` đối với hai `CollectionBox` cũng không thay đổi cơ chế đó.

Một lớp tự viết có thể cài đặt `equals` bằng `Arrays.equals`, `Arrays.deepEquals` hoặc `Objects.deepEquals` cho từng trường tùy ngữ nghĩa. **Ranh giới quan trọng:** `deepEquals` tự đi sâu qua **mảng**, rồi dừng việc đi sâu tự động khi chạm đến một đối tượng không phải mảng và gọi `equals` của chính đối tượng đó.

Nếu nghiệp vụ đòi hỏi so giá trị của từng mảng nằm trong `List<int[]>`, phải thiết kế hàm duyệt từng cặp phần tử và gọi `Arrays.equals` cho từng `int[]`, hoặc chuyển cấu trúc phần tử sang một kiểu giá trị bất biến có hợp đồng `equals` phù hợp. `Objects.deepEquals(listA,listB)` không cung cấp sẵn thuật toán đó.

## 8. Gắn so sánh sâu với `hashCode()`

Quy tắc chung của Java: nếu `a.equals(b) == true` thì `a.hashCode() == b.hashCode()`. Khi tự override `equals` để so **nội dung mảng** của một lớp, `hashCode` cũng phải được tính tương thích với nội dung đó.

| Cách so sánh dữ liệu | Cách tính mã băm tương ứng |
| --- | --- |
| `Arrays.equals(int[],int[])` | `Arrays.hashCode(int[])` |
| `Arrays.equals(Object[],Object[])` | `Arrays.hashCode(Object[])` |
| `Arrays.deepEquals(Object[],Object[])` | `Arrays.deepHashCode(Object[])` |
| `Objects.deepEquals(int[][],int[][])` | `Arrays.deepHashCode(int[][])` |

Không có một phương thức `Objects.deepHashCode(Object)` dùng chung tương ứng trong `java.util.Objects`. Cần chọn hàm `Arrays.hashCode`/`Arrays.deepHashCode` đúng với **kiểu mảng và ngữ nghĩa bằng nhau**. `Objects.hashCode(array)` chỉ gọi hash của đối tượng mảng theo quy tắc đối tượng; nó **không phải** mã băm sâu theo nội dung mảng. `Objects.hash(array)` cũng không phải giải pháp tổng quát để thay thế `Arrays.deepHashCode` và còn có đặc điểm varargs dễ gây nhầm với mảng `Object[]`.

Nếu một lớp dùng `Arrays.deepEquals` cho trường `int[][]` nhưng lại tính hash bằng `System.identityHashCode` hoặc `Object.hashCode` của chính mảng, hai đối tượng có nội dung bằng nhau có thể mang hai hash khác nhau, vi phạm hợp đồng.

### Ví dụ đầy đủ: khóa ma trận có bằng nhau sâu

Lưu thành tệp `DeepMatrixKeyDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class DeepMatrixKeyDemo {
    static final class MatrixKey {
        private final int[][] rows;

        MatrixKey(int[][] input) {
            Objects.requireNonNull(input, "input");
            rows = new int[input.length][];
            for (int i = 0; i < input.length; i++) {
                rows[i] = Objects.requireNonNull(
                        input[i], "row " + i).clone();
            }
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof MatrixKey other)) return false;
            return Arrays.deepEquals(rows, other.rows);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(rows);
        }

        @Override
        public String toString() {
            return Arrays.deepToString(rows);
        }
    }

    public static void main(String[] args) {
        int[][] external = {{1, 2}, {3, 4}};
        MatrixKey original = new MatrixKey(external);
        MatrixKey same = new MatrixKey(
                new int[][]{{1, 2}, {3, 4}});

        System.out.println("equals: " + original.equals(same));
        System.out.println("same hash: "
                + (original.hashCode() == same.hashCode()));

        Map<MatrixKey, String> map = new HashMap<>();
        map.put(original, "saved");
        System.out.println("lookup: " + map.get(same));

        external[0][0] = 99;
        System.out.println("lookup after input changed: "
                + map.get(same));

        MatrixKey changed = new MatrixKey(external);
        System.out.println("changed differs: "
                + original.equals(changed));
        System.out.println("original data: " + original);
    }
}
```

Biên dịch/chạy:

```bash
javac DeepMatrixKeyDemo.java
java DeepMatrixKeyDemo
```

Stdout:

```text
equals: true
same hash: true
lookup: saved
lookup after input changed: saved
changed differs: false
original data: [[1, 2], [3, 4]]
```

Lớp `MatrixKey` so nội dung từng hàng của ma trận bằng `Arrays.deepEquals` và tính hash tương ứng bằng `Arrays.deepHashCode`. Constructor chủ động **clone từng hàng** nên việc thay đổi ma trận được đưa vào sau thời điểm tạo khóa không làm đổi trạng thái bên trong khóa. Ví dụ này giới hạn ở ma trận `int[][]` không có hàng `null`; nếu nghiệp vụ cho phép hàng `null`, constructor phải có chính sách riêng phù hợp.

**Bất biến và sao chép phòng vệ quan trọng khi làm khóa băm:** Nếu mảng hoặc phần tử con được sửa sau khi đưa khóa vào `HashMap`/`HashSet`, cả `equals` và mã băm có thể thay đổi, khiến collection không tìm lại được entry theo giá trị mong đợi. Trong ví dụ này, hai cấp mảng đều được sao chép và không có getter làm lộ `rows`, nên dữ liệu bên trong khóa giữ ổn định sau khi tạo.

## 9. Các lỗi phổ biến khi chọn phương thức so sánh

| Sai lầm | Vì sao sai hoặc thiếu | Cách làm phù hợp |
| --- | --- | --- |
| `Objects.equals(new int[]{1}, new int[]{1})` rồi kỳ vọng `true`. | Mảng không override `equals`. | `Arrays.equals` hoặc `Objects.deepEquals`. |
| `Arrays.equals(matrix1, matrix2)` với `int[][]` rồi kỳ vọng so từng số. | `int[][]` được so nông theo tham chiếu các hàng. | `Arrays.deepEquals(matrix1,matrix2)`. |
| Gọi `Arrays.deepEquals` trực tiếp với hai `int[]`. | Overload này đòi `Object[]`, còn `int[]` không phải `Object[]`. | `Arrays.equals(int[],int[])`. |
| Cho rằng `Objects.deepEquals` luôn soi mọi trường của record/class. | Với hai object không phải mảng, nó dùng `equals` của object. | Override `equals` ở lớp bao hoặc so trực tiếp trường mảng. |
| Cho rằng `Objects.deepEquals(List<int[]>, List<int[]>)` luôn so số bên trong mảng. | `List.equals` dùng `equals` của phần tử `int[]`, tức theo tham chiếu. | Duyệt list, dùng `Arrays.equals` cho các mảng tương ứng. |
| Dùng `Objects.hashCode(array)` với `equals` sâu. | Hash không dựa theo nội dung mảng. | `Arrays.hashCode`/`Arrays.deepHashCode` phù hợp. |
| Sử dụng một mảng mutable làm khóa hash nhưng vẫn sửa nội dung. | Hash có thể đổi, collection không tự lập chỉ mục lại. | Sao chép phòng vệ, cố định dữ liệu hoặc dùng khóa bất biến. |
| Chọn `deepEquals` mà không xét yêu cầu thứ tự. | Mảng được so theo vị trí, không phải theo tập phần tử. | Nếu nghiệp vụ cần so không thứ tự, thiết kế thuật toán riêng. |
| So hai mảng khác kiểu primitive chỉ vì giá trị số nhìn giống nhau. | `int[]` và `long[]` là hai kiểu mảng khác nhau. | Chuyển đổi giá trị có chủ đích khi nghiệp vụ cho phép. |

Một bẫy tinh tế nữa là mảng có tham chiếu vòng. Các API đệ quy như `Arrays.deepEquals`, `Arrays.deepHashCode` và `Arrays.deepToString` không nên được xem là bộ xử lý đồ thị tổng quát. Với `Arrays.deepEquals` và `deepHashCode`, hành vi với cấu trúc mảng chứa vòng có thể không được xác định theo hợp đồng. Nếu dữ liệu là đồ thị có chu trình, cần thuật toán so sánh theo đồ thị có cơ chế ghi nhớ những nút đã thăm thay vì dựa hoàn toàn vào phép so sâu mảng.

## 10. Bài tập tự kiểm tra

1. Hai mảng `int[]` tạo bởi hai lệnh `new` có cùng nội dung: `Objects.equals` và `Objects.deepEquals` trả gì?
2. Vì sao `Arrays.equals(int[][],int[][])` có thể `false` trong khi `Arrays.deepEquals(int[][],int[][])` là `true`?
3. `Objects.deepEquals(null,null)` trả gì? Nếu một bên là mảng, một bên là `null` thì sao?
4. `Objects.deepEquals(new int[]{1},new long[]{1})` có bằng nhau không? Vì sao?
5. Hai `List<int[]>` cùng cấu trúc số nhưng chứa những mảng riêng biệt có tự bằng nhau qua `Objects.deepEquals` không?
6. Tại sao `Objects.deepEquals` không tự làm hai record chứa mảng khác tham chiếu trở thành bằng nhau?
7. Trong một lớp tự override `equals` để so trường `Object[][]` bằng `Arrays.deepEquals`, nên tính mã băm trường đó bằng API nào?
8. Một `MatrixKey` được dùng trong `HashMap` sẽ có rủi ro gì nếu code bên ngoài còn giữ tham chiếu tới mảng bên trong và sửa nội dung?
9. Khi nào nên chọn `Arrays.equals(int[],int[])` thay vì `Objects.deepEquals`?
10. Tại sao so sánh sâu mảng không nhất thiết đồng nghĩa với so sánh "sâu toàn bộ mọi object" trong một cấu trúc dữ liệu?

**Ghi nhớ:** `Objects.equals` gọi phép bằng nhau thông thường của đối tượng; với mảng, điều đó thường là **cùng tham chiếu**. `Objects.deepEquals` bổ sung phép **so nội dung cho các cặp mảng**, kể cả mảng nguyên thủy và mảng lồng nhiều chiều, nhưng không tự đào sâu các lớp/`List` chứa mảng. Khi xây dựng lớp giá trị có so sánh sâu, luôn chọn `hashCode` tương ứng và giữ dữ liệu tham gia bình đẳng ổn định.