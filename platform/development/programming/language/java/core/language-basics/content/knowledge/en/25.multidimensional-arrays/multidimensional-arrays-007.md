# `Arrays.deepToString()` và `Arrays.deepEquals()` trong Java

> **Java core — language-basics / Mảng nhiều chiều**  
> **Môi trường:** JDK 17+, chương trình một file, không cần thư viện ngoài.  
> **Mục tiêu:** Hiển thị và so sánh **nội dung lồng nhau** của mảng nhiều chiều; phân biệt `toString`/`equals` thông thường với hai hàm `deep...`, hiểu hàng `null`, mảng không đều và giới hạn của phép so sánh sâu.

## 1. Vì sao mảng nhiều chiều cần các hàm `deep...`?

Trong Java, mảng hai chiều thực chất là **mảng chứa tham chiếu đến các mảng con**:

~~~java
int[][] grid = {{1, 2}, {3}};
System.out.println(java.util.Arrays.deepToString(grid));
// [[1, 2], [3]]
~~~

Nếu gọi `Arrays.toString(grid)`, Java xử lý từng **phần tử của mảng ngoài** là một đối tượng `int[]`. Phần tử mảng con thường được biểu diễn bằng chuỗi kiểu `[I@...` chứa mã danh tính, **không phải** danh sách các số. Chuỗi danh tính đó phụ thuộc runtime và không nên dùng làm expected output.

`Arrays.deepToString(grid)` đi qua các cấp mảng và in nội dung bên trong. Tương tự, `Arrays.deepEquals(a, b)` so sánh nội dung mảng con thay vì chỉ so sánh tham chiếu của từng hàng.

| Nhu cầu | Mảng một chiều | Mảng nhiều chiều / lồng nhau |
| --- | --- | --- |
| In các phần tử | `Arrays.toString(array)` | `Arrays.deepToString(outer)` |
| So sánh phần tử | `Arrays.equals(a, b)` | `Arrays.deepEquals(a, b)` |
| So cùng đối tượng mảng? | `a == b` | `a == b` chỉ so tham chiếu outer |
| Tạo bản sao? | `Arrays.copyOf` / `clone` | Cần sao chép thêm từng hàng để độc lập |

**Quan trọng về kiểu:** `deepToString` và `deepEquals` nhận tham số kiểu `Object[]`. `int[][]` dùng được vì các phần tử của nó là `int[]` (tham chiếu); **`int[]` không phải `Object[]`**. Muốn in/so sánh `int[]` trực tiếp thì dùng `Arrays.toString(int[])` và `Arrays.equals(int[], int[])`.

## 2. `Arrays.deepToString()`: xem nội dung qua nhiều tầng

~~~java
import java.util.Arrays;

int[][] matrix = {{1, 2}, {3, 4}};
System.out.println(Arrays.deepToString(matrix));
// [[1, 2], [3, 4]]
~~~

`deepToString` tự nhận biết phần tử là một mảng và tiếp tục định dạng các phần tử con. Nó cũng xử lý **mảng răng cưa** (*ragged array*) — các hàng không bắt buộc dài bằng nhau:

~~~java
int[][] jagged = {{1, 2}, null, {}, {7}};
System.out.println(Arrays.deepToString(jagged));
// [[1, 2], null, [], [7]]
~~~

Ở đây `null` biểu thị **một hàng chưa có đối tượng mảng**, còn `[]` biểu thị **một hàng đã được tạo với độ dài 0**. Hai trạng thái này khác nhau và được hiển thị khác nhau.

Với mảng lồng nhiều tầng hơn, `deepToString` tiếp tục xuống các tầng đó. Nếu phần tử cuối là đối tượng thông thường (không phải mảng), cách biểu diễn phụ thuộc `String.valueOf(element)`/`toString()` của đối tượng; không phải mọi lớp đều có `toString()` biểu diễn giá trị nghiệp vụ.

## 3. `Arrays.deepEquals()`: so sánh từng hàng theo nội dung

Hai mảng có giá trị giống nhau nhưng các hàng được tạo **độc lập**:

~~~java
int[][] first = {{1, 2}, {3}};
int[][] second = {{1, 2}, {3}};

System.out.println(first == second);                   // false
System.out.println(Arrays.equals(first, second));      // false
System.out.println(Arrays.deepEquals(first, second));  // true
~~~

Vì sao?

1. `first == second` là false: hai **mảng ngoài** khác đối tượng.
2. `Arrays.equals(first, second)` so sánh các phần tử mảng ngoài. Mỗi phần tử là một `int[]`, và mảng con không override `equals` để so theo giá trị: các tham chiếu hàng khác nhau nên false.
3. `Arrays.deepEquals(first, second)` đi xuống từng hàng và so sánh từng giá trị số; cùng kích thước, thứ tự và nội dung nên true.

Nếu một hàng chứa phần tử khác, số hàng khác hoặc độ dài một hàng khác thì `deepEquals` trả false. Phép so sánh **có xét thứ tự**: `{{1,2},{3}}` không bằng `{{2,1},{3}}` theo `deepEquals`.

Hai mảng ngoài cùng tham chiếu sẽ so bằng nhau, nhưng đây không phải mục tiêu chính của deep comparison: nó hữu ích khi hai cấu trúc là **những đối tượng riêng biệt**.

## 4. Mảng lồng không đều, hàng `null` và mảng rỗng

~~~java
int[][] a = {{1, 2}, null, {}, {7}};
int[][] b = {{1, 2}, null, {}, {7}};
int[][] c = {{1, 2}, {}, null, {7}};

System.out.println(Arrays.deepEquals(a, b)); // true
System.out.println(Arrays.deepEquals(a, c)); // false
~~~

`a` và `b` cùng cấu trúc, cùng các hàng `null`/rỗng và cùng các phần tử. `c` đã đổi chỗ hai trạng thái nên không bằng `a`.

| Cấu trúc | `Arrays.deepToString(...)` |
| --- | --- |
| `new int[][] {{1}, {2, 3}}` | `"[[1], [2, 3]]"` |
| `new int[2][]` | `"[null, null]"` |
| `new int[][] {{}, {}}` | `"[[], []]"` |
| `new int[0][]` | `"[]"` |

`deepToString((Object[]) null)` trả chuỗi `"null"`. `deepEquals((Object[]) null, (Object[]) null)` trả true, còn so một outer null với một outer rỗng trả false. Cần phân biệt **outer null**, **outer có hàng null**, và **outer rỗng**.

Các kiểu primitive như `int[]`, `long[]` bên trong `Object[]` vẫn được xử lý theo nội dung; không cần boxing từng số thành `Integer`.

## 5. Mảng hỗn hợp và `equals` của phần tử là đối tượng

Có thể đặt nhiều loại mảng con cùng các đối tượng thông thường trong một `Object[]`:

~~~java
Object[] values = {
    "Java",
    new int[] {4, 5},
    new String[] {"A", "B"},
    null
};
System.out.println(Arrays.deepToString(values));
// [Java, [4, 5], [A, B], null]
~~~

`deepEquals` so sánh đệ quy nếu cả hai phần tử tương ứng là mảng. Nếu chúng là **đối tượng không phải mảng**, nó dựa vào quy tắc `equals` của đối tượng đó:

~~~java
Object[] textA = {new String("OK")};
Object[] textB = {"OK"};
System.out.println(Arrays.deepEquals(textA, textB)); // true

Object[] builderA = {new StringBuilder("OK")};
Object[] builderB = {new StringBuilder("OK")};
System.out.println(Arrays.deepEquals(builderA, builderB)); // false
~~~

`String` override `equals` theo nội dung; `StringBuilder` không override `equals` theo nội dung, nên hai builder riêng biệt có cùng chữ vẫn không bằng nhau. **Deep** trong `deepEquals` có nghĩa là **đi sâu vào phần tử nào thực sự là mảng**, không phải tự so sánh mọi thuộc tính bên trong bất kỳ đối tượng nào.

Hai mảng con khác loại (`int[]` và `long[]`) không trở thành bằng nhau chỉ vì cùng các giá trị số; quy tắc so sánh vẫn xét loại mảng phù hợp.

## 6. So sánh sâu KHÔNG phải sao chép sâu

`Arrays.deepEquals` trả kết quả `boolean` và **không sao chép bất kỳ đối tượng nào**. `Arrays.deepToString` tạo chuỗi hiển thị, cũng **không sao chép dữ liệu**.

Trong khi đó, sao chép mảng ngoài bằng `clone()`/`Arrays.copyOf` vẫn là **shallow copy**: các hàng con tiếp tục được chia sẻ.

~~~java
int[][] source = {{1, 2}, {3}};
int[][] shallow = source.clone();

shallow[0][0] = 9;
// source[0][0] == 9 vì hai outer vẫn trỏ cùng hàng 0.
~~~

Muốn sao chép độc lập tất cả các giá trị `int`, phải tạo hàng mới cho từng hàng tồn tại:

~~~java
static int[][] copyRows(int[][] source) {
    if (source == null) return null;
    int[][] copy = new int[source.length][];
    for (int i = 0; i < source.length; i++) {
        copy[i] = source[i] == null ? null : source[i].clone();
    }
    return copy;
}
~~~

Cách này giữ nguyên hàng null nhưng tạo **đối tượng hàng mới** cho mỗi hàng không null. Với mảng chứa các đối tượng mutable, ngay cả khi clone từng hàng, các đối tượng phần tử vẫn có thể được chia sẻ và cần chiến lược sao chép theo hợp đồng nghiệp vụ.

## 7. Lưu ý hiệu năng, mảng tự tham chiếu và phiên bản

- Cả hai hàm đều duyệt qua các phần tử cần hiển thị/so sánh; chi phí tăng theo tổng số phần tử lồng nhau. `deepEquals` có thể dừng sớm ở vị trí khác biệt đầu tiên, nhưng trường hợp cần so hết vẫn tốn thời gian theo số phần tử.
- Với mảng lồng nhau có **chu trình tham chiếu** như một `Object[]` chứa chính nó, `deepToString` có cơ chế đánh dấu vòng tham chiếu trong chuỗi hiển thị. Đừng thiết kế thuật toán nghiệp vụ phụ thuộc vào định dạng tham chiếu vòng; nên tránh cấu trúc vòng nếu không cần.
- `Arrays.deepEquals` **không nên dùng để so sánh các cấu trúc mảng tự tham chiếu theo chu trình**: quy tắc API không định nghĩa kết quả đáng tin cậy cho mảng chứa chính nó trực tiếp hoặc gián tiếp. Hãy xác định cách xử lý chu trình riêng nếu bài toán yêu cầu.
- Nếu mảng chứa phần tử là `double[]` hoặc `float[]`, `deepEquals` dùng quy tắc so sánh mảng primitive tương ứng của `Arrays.equals`, không đơn giản là phép `==` cho từng số. Nếu cần so số thực theo ngưỡng sai số, phải xây dựng kiểm tra riêng theo yêu cầu.

Cú pháp và các API trong bài hoạt động trên Java 17+ không cần cờ `--enable-preview`.

## 8. Chương trình Java 17+ chạy độc lập

Tạo file **DeepArraysDemo.java**:

~~~java
import java.util.Arrays;

public final class DeepArraysDemo {
    private static int[][] copyRows(int[][] source) {
        if (source == null) {
            return null;
        }
        int[][] copy = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copy[i] = source[i] == null ? null : source[i].clone();
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] first = {{1, 2}, {3}};
        int[][] second = {{1, 2}, {3}};

        System.out.println("outerSame=" + (first == second));
        System.out.println("shallowEqual=" + Arrays.equals(first, second));
        System.out.println("deepEqual=" + Arrays.deepEquals(first, second));
        System.out.println("deepText=" + Arrays.deepToString(first));
        System.out.println("flatText=" + Arrays.toString(first[0]));
        System.out.println("flatEqual=" + Arrays.equals(first[0], second[0]));

        int[][] jagged = {{1, 2}, null, {}, {7}};
        int[][] jaggedTwin = {{1, 2}, null, {}, {7}};
        System.out.println("jaggedText=" + Arrays.deepToString(jagged));
        System.out.println("jaggedEqual=" + Arrays.deepEquals(jagged, jaggedTwin));

        Object[] mixed = {
            "Java", new int[] {4, 5}, new String[] {"A", "B"}, null
        };
        Object[] mixedTwin = {
            "Java", new int[] {4, 5}, new String[] {"A", "B"}, null
        };
        System.out.println("mixedText=" + Arrays.deepToString(mixed));
        System.out.println("mixedEqual=" + Arrays.deepEquals(mixed, mixedTwin));

        Object[] stringsA = {new String("OK")};
        Object[] stringsB = {"OK"};
        System.out.println("stringEqual="
                + Arrays.deepEquals(stringsA, stringsB));

        Object[] buildersA = {new StringBuilder("OK")};
        Object[] buildersB = {new StringBuilder("OK")};
        System.out.println("builderEqual="
                + Arrays.deepEquals(buildersA, buildersB));

        Object[] absent = null;
        System.out.println("nullText=" + Arrays.deepToString(absent));
        System.out.println("nullEqualNull="
                + Arrays.deepEquals(absent, (Object[]) null));
        System.out.println("nullEqualEmpty="
                + Arrays.deepEquals(absent, new Object[0]));

        int[][] shallow = first.clone();
        shallow[0][0] = 9;
        System.out.println("outerCopySame=" + (first == shallow));
        System.out.println("sharedRow=" + (first[0] == shallow[0]));
        System.out.println("sourceAfterShallow=" + Arrays.deepToString(first));
        System.out.println("deepEqualAfterChange="
                + Arrays.deepEquals(first, second));

        int[][] independent = copyRows(first);
        independent[0][1] = 77;
        System.out.println("independentRowSame="
                + (first[0] == independent[0]));
        System.out.println("sourceAfterDeepCopy=" + Arrays.deepToString(first));
        System.out.println("newDeepCopy=" + Arrays.deepToString(independent));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (PowerShell, Command Prompt hoặc Bash):

~~~bash
javac -encoding UTF-8 DeepArraysDemo.java
java DeepArraysDemo
~~~

**Expected stdout chính xác:**

~~~text
outerSame=false
shallowEqual=false
deepEqual=true
deepText=[[1, 2], [3]]
flatText=[1, 2]
flatEqual=true
jaggedText=[[1, 2], null, [], [7]]
jaggedEqual=true
mixedText=[Java, [4, 5], [A, B], null]
mixedEqual=true
stringEqual=true
builderEqual=false
nullText=null
nullEqualNull=true
nullEqualEmpty=false
outerCopySame=false
sharedRow=true
sourceAfterShallow=[[9, 2], [3]]
deepEqualAfterChange=false
independentRowSame=false
sourceAfterDeepCopy=[[9, 2], [3]]
newDeepCopy=[[9, 77], [3]]
~~~

Dòng `shallowEqual=false` nhưng `deepEqual=true` cho thấy hai outer độc lập vẫn có thể có nội dung sâu bằng nhau. Dòng `sharedRow=true` chứng minh bản clone outer dùng lại các hàng cũ, còn `independentRowSame=false` chứng minh `copyRows` đã tạo hàng riêng.

### Bài tập và checklist

**Bài 1.** Tạo hai `int[][]` có các hàng độc lập nhưng chứa cùng giá trị; dự đoán `==`, `Arrays.equals` và `Arrays.deepEquals`.

**Bài 2.** Với `{{1, 2}, null, {}}`, dự đoán đầu ra của `Arrays.deepToString` và giải thích khác biệt giữa hàng null và hàng rỗng.

**Bài 3.** Dùng `Object[]` chứa một `int[]`, một `String[]` và một `null`; so sánh bằng `deepEquals` với cấu trúc mới có cùng nội dung.

**Bài 4.** Gọi `Arrays.deepEquals` cho hai `Object[]` mỗi bên chứa một `StringBuilder("A")` riêng biệt. Vì sao kết quả không giống hai `String("A")`?

**Bài 5.** `clone()` mảng ngoài, sửa phần tử hàng 0 và quan sát bản gốc. Sau đó dùng `copyRows` để chứng minh bản sao hàng độc lập.

**Checklist:** Dữ liệu có thật sự là mảng lồng nhau không? Có hàng null hay độ dài không đều không? Cần so sánh **nội dung sâu** hay **cùng tham chiếu**? Phần tử có override `equals` không? Có chu trình tham chiếu hoặc nhu cầu sao chép sâu không?

### Ghi nhớ

**`Arrays.deepToString` hiển thị mảng lồng nhau; `Arrays.deepEquals` so sánh nội dung các mảng con.** `Arrays.toString` và `Arrays.equals` chỉ xử lý một tầng của mảng ngoài. Deep comparison **không phải** deep copy; sao chép mảng ngoài vẫn chia sẻ mảng con nếu không tạo bản sao từng hàng.
