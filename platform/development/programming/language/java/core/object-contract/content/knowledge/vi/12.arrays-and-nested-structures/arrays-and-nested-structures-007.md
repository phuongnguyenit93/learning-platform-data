# Trường mảng trong lớp tự viết: đồng bộ `equals()` với `hashCode()`

Khi một lớp Java tự viết có trường là **mảng** (`int[]`, `String[]`, `Object[]`, `int[][]`…), quyết định “hai đối tượng có bằng nhau không” cần đi kèm **cách tính mã băm tương ứng**. Mảng là đối tượng đặc biệt trong Java: nó không ghi đè `Object.equals()` và `Object.hashCode()` theo nội dung phần tử. Vì thế, dù hai mảng chứa chính xác các giá trị giống nhau, `array1.equals(array2)` hoặc `Objects.equals(array1, array2)` vẫn có thể trả `false` nếu đó là hai instance khác nhau.

Nếu lớp muốn định nghĩa bằng nhau **theo nội dung mảng**, hãy dùng đúng cặp API:

- Mảng một chiều: **`Arrays.equals(...)` đi cùng `Arrays.hashCode(...)`**.
- Mảng lồng nhau cần so sánh sâu: **`Arrays.deepEquals(...)` đi cùng `Arrays.deepHashCode(...)`**.
- Các trường khác tham gia `equals` cũng phải được phản ánh nhất quán trong `hashCode`.

Việc dùng khác quy tắc giữa hai phương thức có thể làm `HashMap` và `HashSet` xử lý đối tượng trái với dự kiến.

## 1. Bắt đầu từ hợp đồng `equals`/`hashCode`

Với một lớp tự viết, hợp đồng quan trọng nhất là:

> Nếu `a.equals(b)` trả `true`, **bắt buộc** `a.hashCode() == b.hashCode()`.

Chiều ngược lại **không bắt buộc**: các đối tượng không bằng nhau vẫn có thể có mã băm trùng nhau.

Ngoài ra, `equals` cần bảo đảm phản xạ, đối xứng, bắc cầu, tính nhất quán khi dữ liệu dùng để so sánh không thay đổi và `x.equals(null)` trả `false`. Khi ghi đè `equals`, hãy ghi đè `hashCode` để các cấu trúc băm có thể tìm đúng các đối tượng bằng nhau.

Một ví dụ dễ sai (chỉ là các đoạn minh họa trong lớp, **không phải chương trình độc lập**):

```java
// Sai nếu muốn so sánh nội dung mảng:
return Objects.equals(scores, other.scores);

// Sai nếu equals đã dùng Arrays.equals(scores, other.scores):
@Override
public int hashCode() {
    return scores.hashCode();
}
```

`Objects.equals` chỉ hỗ trợ xử lý `null` và gọi `equals` của đối số; đối với mảng, `equals` kế thừa từ `Object` kiểm tra **cùng tham chiếu**. Tương tự, `scores.hashCode()` không băm từng phần tử. Nếu hai đối tượng chứa **hai mảng khác nhau nhưng cùng nội dung** được coi là bằng nhau, chúng có thể nhận hash khác nhau, vi phạm hợp đồng.

Lưu ý: nếu một lớp **cố ý** xem mảng là thành phần có ngữ nghĩa danh tính tham chiếu, việc dùng `==`/`Objects.equals` và hash tương ứng có thể hợp lệ. Nhưng đây là **quyết định về ngữ nghĩa**, phải được chọn nhất quán, không phải mặc định đúng cho mọi value object.

## 2. Mảng một chiều: `Arrays.equals` và `Arrays.hashCode`

Dùng `import java.util.Arrays;`.

Các overload phổ biến của `Arrays.equals` gồm mảng các kiểu nguyên thủy như `int[]`, `long[]`, `byte[]`, `char[]`, `boolean[]`, và mảng tham chiếu như `String[]`, `Object[]`.

```java
// Biểu thức độc lập để minh họa, đặt trong main hoặc một method:
int[] x = {1, 2, 3};
int[] y = {1, 2, 3};

// x == y                 -> false (hai mảng khác instance)
// Objects.equals(x, y)   -> false (mảng không ghi đè equals theo giá trị)
// Arrays.equals(x, y)    -> true  (so sánh phần tử cùng vị trí)
// Arrays.hashCode(x) == Arrays.hashCode(y) -> true
```

Với `int[]`, các phần tử được so sánh theo giá trị nguyên thủy. Với `String[]`, mỗi cặp phần tử được so sánh theo `Objects.equals` nên hai chuỗi khác instance nhưng cùng nội dung được coi là bằng nhau. Với `Object[]`, cách so sánh nội dung từng phần tử **phụ thuộc `equals` của lớp phần tử**.

Hai mảng một chiều chỉ bằng nhau khi cùng độ dài và từng vị trí tương ứng bằng nhau. Vì thế thứ tự là quan trọng:

```text
[1, 2, 3]  và  [1, 2, 3]  -> bằng nhau
[1, 2, 3]  và  [3, 2, 1]  -> không bằng nhau
[1, 2, 3]  và  [1, 2]     -> không bằng nhau
```

`Arrays.hashCode` băm theo cùng thứ tự phần tử, bảo đảm hai mảng được `Arrays.equals` coi là bằng nhau sẽ có cùng hash. Hash trùng không chứng minh hai mảng bằng nhau vì va chạm vẫn có thể xảy ra.

Các overload này cũng xử lý `null`: hai mảng `null` được `Arrays.equals` coi là bằng nhau; một mảng `null`, một mảng không `null` thì không bằng nhau; `Arrays.hashCode` trả `0` với mảng `null`. Do đó có thể dùng trực tiếp trên trường mảng nullable khi đúng overload.

## 3. Mảng lồng nhau: khi nào cần `deepEquals` và `deepHashCode`?

Trong Java, `int[][]` là **mảng chứa các tham chiếu đến `int[]`**, không phải một vùng “ma trận” đơn khối với cơ chế bằng nhau riêng. Nếu gọi `Arrays.equals(int[][], int[][])`, phương thức dùng overload nhận `Object[]` và so sánh **mỗi phần tử hàng**. Mỗi hàng `int[]` lại dùng `Object.equals` mặc định, nên hai hàng khác instance dù cùng số vẫn không bằng nhau.

Đối với dữ liệu lồng nhau cần so sánh toàn bộ nội dung, dùng:

```java
// Hai ma trận khác instance, kể cả các mảng hàng:
int[][] first = {{1, 2}, {3, 4}};
int[][] second = {{1, 2}, {3, 4}};

// Arrays.equals(first, second)       -> false
// Arrays.deepEquals(first, second)   -> true
// Arrays.deepHashCode(first) == Arrays.deepHashCode(second) -> true
```

`Arrays.deepEquals(Object[] a1, Object[] a2)` nhận các mảng tham chiếu bên ngoài. Nó đi sâu qua các phần tử có kiểu mảng, kể cả các mảng kiểu nguyên thủy được lồng bên trong, và dùng phép so sánh phù hợp ở từng cấp. `Arrays.deepHashCode(Object[] a)` tính mã băm tương ứng. Cặp này phù hợp với các cấu trúc như `int[][]`, `String[][]` hoặc `Object[]` chứa những mảng con.

**Giới hạn cần hiểu:** `Arrays.deepEquals` không phải cơ chế tự động duyệt mọi trường của **một object bất kỳ**. Nếu phần tử là một đối tượng Java thông thường, ngữ nghĩa so sánh của nó vẫn do `equals` của lớp đó quyết định. Các cấu trúc mảng có tham chiếu vòng về chính chúng cũng không phù hợp để so sánh sâu theo cách ngây thơ: có thể dẫn tới đệ quy không kết thúc hoặc lỗi tràn stack.

`Arrays.deepHashCode` và `Arrays.deepEquals` tạo ra quy tắc phù hợp nhau; đừng dùng `deepEquals` trong `equals` nhưng lại gọi `Arrays.hashCode` ở cấp mảng ngoài trong `hashCode`.

## 4. Ví dụ Java 17+ hoàn chỉnh với lớp có ba loại trường mảng

Ta thiết kế lớp `CourseReport` gồm:

- `title`: chuỗi có thể `null`, so sánh bằng `Objects.equals`.
- `scores`: `int[]`, so sánh và băm theo nội dung một chiều.
- `tags`: `String[]`, so sánh và băm từng phần tử theo giá trị chuỗi.
- `matrix`: `int[][]`, so sánh và băm sâu theo nội dung các hàng.

Mọi trường này đều tham gia tiêu chí bằng nhau của `CourseReport`. Lớp `final`, giữ các trường `private final` và **sao chép đầu vào** để tránh bên ngoài sửa mảng sau khi tạo đối tượng.

Lưu thành tệp **`ArrayFieldContractDemo.java`**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class CourseReport {
    private final String title;
    private final int[] scores;
    private final String[] tags;
    private final int[][] matrix;

    CourseReport(String title, int[] scores, String[] tags, int[][] matrix) {
        this.title = title;
        this.scores = Objects.requireNonNull(scores, "scores").clone();
        this.tags = Objects.requireNonNull(tags, "tags").clone();
        this.matrix = copyMatrix(matrix);
    }

    private static int[][] copyMatrix(int[][] source) {
        Objects.requireNonNull(source, "matrix");
        int[][] copy = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copy[i] = Objects.requireNonNull(source[i], "matrix row").clone();
        }
        return copy;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof CourseReport other)) {
            return false;
        }
        return Objects.equals(title, other.title)
                && Arrays.equals(scores, other.scores)
                && Arrays.equals(tags, other.tags)
                && Arrays.deepEquals(matrix, other.matrix);
    }

    @Override
    public int hashCode() {
        int result = Objects.hashCode(title);
        result = 31 * result + Arrays.hashCode(scores);
        result = 31 * result + Arrays.hashCode(tags);
        result = 31 * result + Arrays.deepHashCode(matrix);
        return result;
    }
}

public class ArrayFieldContractDemo {
    public static void main(String[] args) {
        int[] scores = {9, 10};
        String[] tags = {"java", "core"};
        int[][] matrix = {{1, 2}, {3, 4}};

        CourseReport a = new CourseReport("lesson", scores, tags, matrix);
        CourseReport b = new CourseReport(
                "lesson",
                new int[]{9, 10},
                new String[]{"java", "core"},
                new int[][]{{1, 2}, {3, 4}}
        );

        System.out.println("a equals b: " + a.equals(b));
        System.out.println("Equal hash: " + (a.hashCode() == b.hashCode()));

        scores[0] = 0;
        tags[0] = "changed";
        matrix[0][0] = 99;

        System.out.println("Equal after changing inputs: " + a.equals(b));
        System.out.println("Hash still equal: "
                + (a.hashCode() == b.hashCode()));

        CourseReport different = new CourseReport(
                "lesson",
                new int[]{9, 11},
                new String[]{"java", "core"},
                new int[][]{{1, 2}, {3, 4}}
        );
        System.out.println("Different scores: " + a.equals(different));

        Set<CourseReport> reports = new HashSet<>();
        reports.add(a);
        reports.add(b);
        reports.add(different);
        System.out.println("HashSet size: " + reports.size());

        int[][] nested1 = {{1, 2}};
        int[][] nested2 = {{1, 2}};
        System.out.println("Nested shallow equals: "
                + Arrays.equals(nested1, nested2));
        System.out.println("Nested deep equals: "
                + Arrays.deepEquals(nested1, nested2));
        System.out.println("Nested deep hashes equal: "
                + (Arrays.deepHashCode(nested1)
                        == Arrays.deepHashCode(nested2)));

        System.out.println("Array Objects.equals: "
                + Objects.equals(new int[]{1}, new int[]{1}));
        System.out.println("Array Arrays.equals: "
                + Arrays.equals(new int[]{1}, new int[]{1}));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac ArrayFieldContractDemo.java
java ArrayFieldContractDemo
```

Đầu ra xác định:

```text
a equals b: true
Equal hash: true
Equal after changing inputs: true
Hash still equal: true
Different scores: false
HashSet size: 2
Nested shallow equals: false
Nested deep equals: true
Nested deep hashes equal: true
Array Objects.equals: false
Array Arrays.equals: true
```

### Giải thích đầu ra và thiết kế

1. `a` và `b` có hai bộ mảng **khác tham chiếu** nhưng cùng nội dung. Nhờ `Arrays.equals` và `Arrays.deepEquals`, `a.equals(b)` là `true`.
2. `hashCode()` tính theo cùng các trường và cùng quy tắc so sánh, vì vậy `a.hashCode() == b.hashCode()` chắc chắn đúng.
3. Sau khi sửa `scores`, `tags` và `matrix` gốc, nội dung bên trong `a` **không thay đổi** nhờ clone ở từng cấp cần thiết. Do đó `a` và `b` vẫn bằng nhau và có cùng hash.
4. `different` có phần tử score khác nên không bằng `a`, dù các trường còn lại giống nhau. `HashSet` chứa hai phần tử logic: một tương đương với `a`/`b` và một là `different`.
5. Hai `int[][]` độc lập cho `Arrays.equals` là `false` vì các mảng hàng khác instance; `Arrays.deepEquals` là `true` và mã băm sâu bằng nhau.
6. `Objects.equals` trên hai `int[]` mới tạo là `false`, còn `Arrays.equals` là `true`, minh họa chính xác khác biệt danh tính và nội dung.

Chương trình **không in các mã hash cụ thể** vì đề bài cần xác minh hợp đồng bằng nhau, không cần dựa trên một giá trị hash số học trùng hợp. Hơn nữa, hai đối tượng khác nhau vẫn có thể trùng hash, nên không kiểm tra tính khác nhau bằng điều kiện “hash khác”.

## 5. Vì sao phải sao chép mảng đầu vào?

Một field được khai báo `private final int[] scores` chỉ ngăn **gán lại tham chiếu `scores`**; nó không ngăn `scores[0] = ...`. Nếu constructor giữ trực tiếp mảng do caller truyền, caller có thể sửa mảng sau khi đối tượng đã được dùng làm key trong `HashMap`/`HashSet`. Khi `hashCode` đổi theo phần tử, tra cứu theo khóa có thể thất bại.

Trong ví dụ:

- `int[]`: `clone()` sao chép các giá trị nguyên thủy; đủ để cô lập nội dung.
- `String[]`: `clone()` sao chép cấu trúc mảng, còn các đối tượng `String` vốn bất biến; đủ trong phạm vi ví dụ.
- `int[][]`: `matrix.clone()` **chỉ sao chép mảng ngoài**, còn những hàng `int[]` bên trong vẫn dùng chung tham chiếu. Cần clone từng hàng, như `copyMatrix`.
- Nếu mảng chứa phần tử là đối tượng **mutable**, ví dụ `Address[]`, clone mảng không clone từng `Address`; cần chính sách sao chép phòng vệ thích hợp hoặc giữ các đối tượng phần tử bất biến.

Nguyên tắc áp dụng cả cho **getter**: nếu cung cấp getter trả về trực tiếp mảng nội bộ, bên ngoài vẫn có thể sửa nó. Hãy trả về bản sao hoặc cấu trúc read-only/bất biến phù hợp. “Read-only view” không đồng nghĩa dữ liệu nền tự bất biến nếu nơi khác còn được quyền sửa.

Nếu bài toán thật sự yêu cầu đối tượng có mảng mutable, phải định nghĩa rõ thời điểm được thay đổi, cơ chế đồng bộ hóa khi có đa luồng và ảnh hưởng đến collection. Thông thường, **không dùng các trường mutable tham gia hash của key đang được lưu** là cách đơn giản hơn.

## 6. Các cách ghép hash phổ biến và bẫy `Objects.hash`

Một cách viết thủ công như ví dụ:

```java
int result = Objects.hashCode(title);
result = 31 * result + Arrays.hashCode(scores);
result = 31 * result + Arrays.hashCode(tags);
result = 31 * result + Arrays.deepHashCode(matrix);
return result;
```

Với hai `CourseReport` được `equals` coi là bằng nhau, mỗi thành phần hash tương ứng bằng nhau, nên phép kết hợp theo cùng công thức sẽ cho kết quả bằng nhau. Phép nhân cộng trên `int` có thể tràn theo số học Java; **tràn int không làm hỏng hợp đồng** nếu công thức áp dụng nhất quán.

Cũng có thể kết hợp các hash thành phần bằng:

```java
return Objects.hash(
        title,
        Arrays.hashCode(scores),
        Arrays.hashCode(tags),
        Arrays.deepHashCode(matrix)
);
```

Đây vẫn là mã băm `int` thông thường, có khả năng va chạm, nhưng nhất quán với `equals`.

**Không dùng trực tiếp:**

```java
// Sai cho lớp dùng Arrays.equals/deepEquals trong equals:
return Objects.hash(title, scores, tags, matrix);
```

Lý do: `Objects.hash` không tự chuyển mọi tham chiếu mảng thành băm nội dung/sâu phù hợp; khi mảng xuất hiện như phần tử của danh sách varargs, nó được xử lý theo `hashCode` của chính mảng. Hai lớp có các mảng khác instance nhưng nội dung bằng nhau có thể nhận hash khác, dẫn tới vi phạm hợp đồng của `CourseReport.equals`.

Cũng đừng nhầm `Objects.hash(array)` và `Arrays.hashCode(array)`: cách overload/varargs diễn giải tham số có thể gây ngạc nhiên, đặc biệt với `Object[]`; hãy **chọn rõ API của `Arrays` với đúng mức sâu**.

## 7. Bảng quyết định theo kiểu trường

| Trường trong lớp | Nếu muốn bằng nhau theo nội dung | Hash tương ứng |
| --- | --- | --- |
| `int[]`, `long[]`, `byte[]`, `boolean[]`… | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` |
| `String[]`, `Object[]` không có mảng con cần so sâu | `Arrays.equals(a, b)` | `Arrays.hashCode(a)` |
| `int[][]`, `String[][]`, `Object[]` có mảng con | `Arrays.deepEquals(a, b)` | `Arrays.deepHashCode(a)` |
| `String` hoặc object nullable thông thường | `Objects.equals(a, b)` | `Objects.hashCode(a)` hoặc thành phần tương đương |
| Kiểu nguyên thủy như `int`, `boolean` | `==` | `Integer.hashCode`, `Boolean.hashCode` hoặc phép kết hợp phù hợp |

Với mảng `float[]` hoặc `double[]`, nên dùng đồng bộ `Arrays.equals` và `Arrays.hashCode`; các quy tắc xử lý `NaN` và `-0.0` của các overload này được thiết kế nhất quán. Tránh tự kết hợp so sánh `==` từng phần tử float với hash tính theo `Float.hashCode` nếu chưa xem xét các giá trị đặc biệt.

Nếu trường là collection như `List<String>`, nó có `equals`/`hashCode` theo quy ước collection; **không tự động áp dụng `Arrays.equals`** lên collection. Chọn cách so sánh đúng cho kiểu dữ liệu thực sự.

## 8. Record chứa mảng và trường hợp cần thận trọng

Java `record` tự sinh `equals`/`hashCode` từ các component, nhưng với component kiểu mảng, phép so sánh được sinh theo **ngữ nghĩa tham chiếu của mảng**, không tự chuyển thành `Arrays.equals` hay `Arrays.deepEquals` theo nội dung. Chẳng hạn:

```java
record Sample(int[] values) {}

// Hai Sample sau không tự nhiên bằng nhau theo nội dung values:
Sample x = new Sample(new int[]{1, 2});
Sample y = new Sample(new int[]{1, 2});
// x.equals(y) -> false
```

Đoạn này chỉ minh họa, **không phải chương trình độc lập**. Nếu cần record có mảng và so sánh theo nội dung, phải tự cân nhắc cài đặt lại cả `equals` lẫn `hashCode`, kèm sao chép phòng vệ lúc tạo/trả dữ liệu nếu cần ổn định. Một lựa chọn khác dễ kiểm soát hơn là lưu dữ liệu trong kiểu value bất biến có `equals`/`hashCode` theo nội dung như `List.copyOf(...)` khi phù hợp, nhưng bản thân phần tử của list vẫn cần có ngữ nghĩa bằng nhau đúng.

## 9. Các lỗi thường gặp và cách rà soát

1. **Dùng `Objects.equals(array1, array2)` và nghĩ rằng nó so từng phần tử:** nó thường chỉ so danh tính mảng. Hãy dùng `Arrays.equals` hoặc `Arrays.deepEquals` tùy cấu trúc.
2. **Dùng `Arrays.equals` cho `int[][]` nhưng muốn so toàn bộ số:** overload `Object[]` chỉ so hàng theo `equals` của từng hàng; dùng `Arrays.deepEquals`.
3. **Cài `equals` theo mảng nội dung nhưng `hashCode` theo tham chiếu:** vi phạm yêu cầu hash bằng nhau khi đối tượng bằng nhau.
4. **Dùng `Objects.hash(title, array)` mà tưởng nó băm sâu:** hãy chuyển mảng thành `Arrays.hashCode(array)` hoặc `Arrays.deepHashCode(array)` trước khi kết hợp.
5. **Bỏ quên một trường trong `equals` nhưng đưa nó vào `hashCode`:** hai đối tượng có thể `equals` bằng nhau nhưng hash khác nhau. Ngược lại, không băm đủ trường có thể vẫn đúng hợp đồng nhưng gây nhiều va chạm; nên thống nhất quy tắc.
6. **Chỉ clone mảng ngoài của cấu trúc nhiều chiều:** dữ liệu hàng con vẫn có thể bị sửa. Clone từng cấp cần cô lập.
7. **Cho caller sửa mảng sau khi object được chèn vào `HashSet` hoặc làm key `HashMap`:** hash hoặc quan hệ bằng nhau có thể thay đổi; ưu tiên value object bất biến, key bất biến.
8. **Dựa vào mã hash trùng/khác để kết luận `equals`:** hash bằng nhau không bảo đảm đối tượng bằng nhau; cần so `equals` thật sự.
9. **Giả định một mảng chứa object được clone là bất biến sâu:** các phần tử object mutable vẫn có thể thay đổi qua tham chiếu khác.
10. **Nhầm `Arrays.deepEquals` với bộ so sánh đồ thị đối tượng tùy ý:** nó chủ yếu đi sâu qua mảng lồng, không tự hiểu toàn bộ quan hệ nghiệp vụ hay vòng tham chiếu tùy ý.

### Checklist cho lớp tự viết chứa mảng

- Đã xác định từng mảng so **tham chiếu** hay **nội dung** theo quy tắc nghiệp vụ?
- Mảng một chiều dùng cặp `Arrays.equals`/`Arrays.hashCode`; mảng lồng dùng cặp `Arrays.deepEquals`/`Arrays.deepHashCode`?
- Các trường thường khác được xử lý nhất quán trong cả `equals` và `hashCode`?
- Đã kiểm thử hai instance có **mảng khác tham chiếu nhưng cùng nội dung**, mảng khác một phần tử, mảng khác độ dài, mảng lồng, và nếu được phép thì mảng `null`?
- Constructor/getter có làm lộ mảng mutable tham gia `equals`/`hashCode` không? Mảng đa chiều đã sao chép đủ sâu cho cấu trúc cụ thể chưa?
- Có dùng object làm khóa `HashMap` hoặc phần tử `HashSet` không? Các dữ liệu tham gia hash có ổn định trong suốt thời gian lưu trữ không?

**Ghi nhớ:** khi trường mảng của lớp được xem là **giá trị**, `equals` và `hashCode` phải dùng **cùng mức so sánh/băm nội dung**: `Arrays.equals` đi với `Arrays.hashCode`, `Arrays.deepEquals` đi với `Arrays.deepHashCode`. Bảo vệ nội dung mảng khỏi thay đổi ngoài ý muốn để giữ tính nhất quán trong các collection dựa trên băm.
