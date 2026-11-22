# Mảng nhiều chiều là mảng chứa tham chiếu tới mảng con trong Java

> **Java core — language-basics / Mảng nhiều chiều**  
> **Yêu cầu:** JDK 17+; ví dụ Java độc lập, không cần thư viện ngoài.  
> **Mục tiêu:** Hiểu đúng cấu trúc `int[][]` là **một mảng ngoài chứa các tham chiếu tới những mảng `int[]`**, biết phân biệt mảng con chưa tạo (`null`) với mảng con đã tạo, lý giải hàng có độ dài khác nhau, chia sẻ tham chiếu và thao tác với hai tầng chỉ số.

## 1. Mô hình “mảng chứa các mảng” thay vì một bảng nguyên khối

Trong Java, `int[][]` được đọc là “mảng có phần tử kiểu `int[]`”. Mỗi phần tử của **mảng ngoài** là **một tham chiếu** tới một mảng `int[]` hoặc giá trị `null`. Chỉ các phần tử **bên trong mảng `int[]`** mới chứa giá trị nguyên thủy `int`.

~~~text
int[][] grid = new int[2][3];

grid (tham chiếu tới mảng ngoài int[][])
       │
       ▼
  +----------+       +-------------+
  | [0]  ----|------>| int[3]      |  [0, 0, 0]
  | [1]  ----|---+   +-------------+
  +----------+   |   +-------------+
                 +-->| int[3]      |  [0, 0, 0]
                     +-------------+
~~~

Ở mức ngữ nghĩa Java, `new int[2][3]` tạo **một mảng ngoài có hai phần tử tham chiếu**, và mỗi phần tử đó được trỏ tới **một mảng con `int[3]` riêng**. Vì thế:

~~~java
int[][] grid = new int[2][3];
System.out.println(grid.length);       // 2: số phần tử của mảng ngoài.
System.out.println(grid[0].length);    // 3: số phần tử hàng 0.
System.out.println(grid[1].length);    // 3: số phần tử hàng 1.
System.out.println(grid[0] == grid[1]); // false: hai mảng con khác nhau.
~~~

Cách diễn đạt “2 hàng × 3 cột” hữu ích để hình dung, nhưng **không nên suy ra rằng Java bắt buộc lưu cả ma trận thành một vùng `int` liên tục**. Hai hàng là hai đối tượng mảng độc lập, được tham chiếu từ mảng ngoài.

## 2. Khởi tạo cả hai tầng hoặc chỉ mảng ngoài

Sự khác biệt quan trọng nằm ở **các tầng đã được `new` tạo**:

| Cú pháp | Mảng ngoài | Các mảng con ban đầu |
| --- | --- | --- |
| `new int[2][3]` | Có, độ dài 2 | Hai `int[3]` khác nhau, chứa `0` |
| `new int[2][]` | Có, độ dài 2 | Cả hai tham chiếu đều `null` |
| `new int[2][0]` | Có, độ dài 2 | Hai `int[0]` hợp lệ và khác `null` |
| `new int[0][3]` | Có, độ dài 0 | Không có phần tử mảng ngoài, nên không có hàng để truy cập |
| `new String[2][3]` | Có, độ dài 2 | Hai `String[3]`, từng phần tử chuỗi là `null` |

Trong `new int[2][]`, các phần tử của mảng ngoài có **kiểu tham chiếu `int[]`**, nên nhận mặc định `null`, dù loại phần tử ở tầng sâu hơn là `int`.

~~~java
int[][] partial = new int[2][];
System.out.println(partial.length);       // 2
System.out.println(partial[0] == null);   // true
System.out.println(partial[1] == null);   // true

partial[0] = new int[3]; // Tạo hàng số 0, gồm [0, 0, 0].
partial[1] = new int[0]; // Tạo hàng số 1, độ dài 0.
System.out.println(partial[0].length); // 3
System.out.println(partial[1].length); // 0
~~~

Từ `partial[1] == null` trước khi gán đến `partial[1].length == 0` sau khi gán là **hai trạng thái hoàn toàn khác nhau**: hàng chưa có đối tượng và hàng có đối tượng mảng rỗng.

Với cú pháp `new` có nhiều chiều, không được chỉ định chiều sâu hơn khi chiều trước còn để trống, chẳng hạn `new int[][3]` không hợp lệ. Có thể bỏ các chiều ở cuối, ví dụ `new int[2][]` hoặc `new int[2][3][]`.

## 3. Hai tầng chỉ số và kiểm tra hàng `null`

Biểu thức `matrix[row][column]` tương đương về ý nghĩa với việc **lấy tham chiếu mảng con** `matrix[row]` rồi đánh chỉ số `[column]` trên mảng con đó:

~~~java
int[][] matrix = {{10, 20}, {30, 40}};
int[] firstRow = matrix[0];

System.out.println(firstRow[1]); // 20
System.out.println(matrix[0][1]); // 20
~~~

Để đọc `matrix[r][c]` thành công, cần:

1. Biến `matrix` tham chiếu tới một mảng ngoài thực sự (không `null`).
2. `r` nằm từ `0` đến `matrix.length - 1`.
3. `matrix[r]` không phải `null`.
4. `c` nằm từ `0` đến `matrix[r].length - 1`.

Thiếu một trong các điều kiện này có thể gây `NullPointerException` hoặc `ArrayIndexOutOfBoundsException`. Một mảng ngoài đã được tạo **không** bảo đảm rằng mọi mảng con cũng đã được tạo.

Ví dụ kiểm tra an toàn khi chỉ muốn đọc nếu vị trí tồn tại:

~~~java
static boolean containsCell(int[][] matrix, int r, int c) {
    return matrix != null
            && r >= 0 && r < matrix.length
            && matrix[r] != null
            && c >= 0 && c < matrix[r].length;
}
~~~

Phương thức trên dùng toán tử `&&` có đánh giá ngắn mạch: nếu điều kiện trước sai, điều kiện sau không được đánh giá. Vì vậy không vô tình truy cập `matrix[r]` trước khi biết `r` hợp lệ.

## 4. Các hàng không cần có cùng độ dài: mảng “răng cưa”

Mỗi phần tử của mảng ngoài là một tham chiếu tới `int[]`, nên các hàng có thể có độ dài **khác nhau** (*jagged/ragged array*):

~~~java
int[][] rows = new int[3][];
rows[0] = new int[] {2, 4};
rows[1] = new int[0];
rows[2] = new int[] {9};

System.out.println(rows.length);    // 3
System.out.println(rows[0].length); // 2
System.out.println(rows[1].length); // 0
System.out.println(rows[2].length); // 1
~~~

Có thể khởi tạo ngắn gọn bằng danh sách:

~~~java
int[][] triangle = {
    {1},
    {2, 3},
    {4, 5, 6}
};
~~~

Trong vòng lặp, đừng áp đặt số cột bằng `rows[0].length` cho mọi hàng. Hãy kiểm tra độ dài **của từng hàng**:

~~~java
static int sumAll(int[][] rows) {
    int sum = 0;
    for (int[] row : rows) {
        if (row == null) {
            continue; // Bỏ qua hàng chưa được tạo theo hợp đồng ví dụ.
        }
        for (int value : row) {
            sum += value;
        }
    }
    return sum;
}
~~~

Phương thức `sumAll` xử lý cả hàng rỗng và hàng `null`, miễn chính mảng ngoài `rows` khác `null`. Với `triangle` phía trên, kết quả là 21. Với ví dụ `rows` ban đầu, tổng là 15.

## 5. Hai hàng có thể tham chiếu cùng một mảng con

Cũng giống biến tham chiếu đối tượng, **hai phần tử của mảng ngoài có thể giữ cùng một tham chiếu**:

~~~java
int[] shared = {10, 20};
int[][] aliases = {shared, shared};

System.out.println(aliases[0] == aliases[1]); // true
aliases[0][0] = 99;
System.out.println(aliases[1][0]);             // 99
~~~

Cập nhật `aliases[0][0]` thay đổi **đối tượng mảng con chung**, nên khi đọc qua `aliases[1][0]` cũng thấy 99.

**Nhưng gán lại tham chiếu hàng không sửa hàng còn lại:**

~~~java
aliases[0] = new int[] {1};
// aliases[0] trỏ tới mảng con mới [1].
// aliases[1] vẫn trỏ tới mảng con cũ [99, 20].
~~~

Đây là hai kiểu thao tác khác nhau:

| Thao tác | Điều xảy ra |
| --- | --- |
| `aliases[0][0] = 99` | Thay **phần tử của mảng con** mà hàng 0 đang tham chiếu |
| `aliases[0] = new int[] {1}` | Thay **tham chiếu ở hàng 0** bằng tham chiếu tới mảng mới |
| `aliases[1] = aliases[0]` | Để hai hàng tham chiếu chung một mảng con hiện tại |

Không thể coi hàng của `int[][]` là “bản sao giá trị” mỗi lần gán. Đây là **tham chiếu**, không phải phép sao chép sâu (*deep copy*).

## 6. Sao chép mảng ngoài vẫn chia sẻ các hàng

Phép `matrix.clone()` tạo một mảng ngoài mới, nhưng các phần tử của nó vẫn là **tham chiếu đến những hàng cũ**. Vì thế thay `copy[0][1]` có thể làm `matrix[0][1]` đổi theo; còn gán `copy[0] = new int[]{8}` chỉ đổi tham chiếu hàng của bản sao. Hai thao tác này nối trực tiếp với mô hình ở mục 5.

Nếu cần dữ liệu `int` độc lập, hãy sao chép từng mảng con không `null` vào mảng ngoài mới. Bài **Sao chép nông và chia sẻ các mảng con** phân tích đầy đủ `clone()`, `Arrays.copyOf()`, mảng có nhiều alias và phần tử đối tượng mutable.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **ArrayOfArraysDemo.java**:

~~~java
import java.util.Arrays;

public final class ArrayOfArraysDemo {
    private static void printRows(String label, int[][] rows) {
        System.out.println(label + "Length=" + rows.length);
        for (int r = 0; r < rows.length; r++) {
            int[] subarray = rows[r];
            String value = subarray == null
                    ? "null"
                    : Arrays.toString(subarray);
            System.out.println(label + "[" + r + "]=" + value);
        }
    }

    public static void main(String[] args) {
        int[][] rectangular = new int[2][3];
        System.out.println("rectRows=" + rectangular.length);
        System.out.println("rectColumns0=" + rectangular[0].length);
        System.out.println("rectColumns1=" + rectangular[1].length);
        System.out.println("rectDistinct="
                + (rectangular[0] != rectangular[1]));
        rectangular[0][1] = 7;
        System.out.println("rectRow0=" + Arrays.toString(rectangular[0]));
        System.out.println("rectRow1=" + Arrays.toString(rectangular[1]));

        int[][] partial = new int[3][];
        printRows("partial", partial);
        partial[0] = new int[] {2, 4};
        partial[1] = new int[0];
        partial[2] = new int[] {9};
        printRows("ragged", partial);
        System.out.println("lastLength=" + partial[2].length);

        int[] shared = {10, 20};
        int[][] aliases = {shared, shared};
        System.out.println("sharedRowsSame=" + (aliases[0] == aliases[1]));
        aliases[0][0] = 99;
        System.out.println("sameRowSeen=" + aliases[1][0]);

        int[] oldRow = aliases[0];
        aliases[0] = new int[] {1};
        System.out.println("afterReplaceRowsSame="
                + (aliases[0] == aliases[1]));
        System.out.println("oldRow=" + Arrays.toString(oldRow));
        System.out.println("newRow=" + Arrays.toString(aliases[0]));
        System.out.println("remainingRow=" + Arrays.toString(aliases[1]));

        int[][] copiedOuter = partial.clone();
        System.out.println("cloneOuterSame=" + (copiedOuter == partial));
        System.out.println("cloneRowSame="
                + (copiedOuter[0] == partial[0]));
        copiedOuter[0][1] = 55;
        System.out.println("mutatedSource=" + partial[0][1]);
        copiedOuter[0] = new int[] {8};
        System.out.println("sourceRow=" + Arrays.toString(partial[0]));
        System.out.println("copiedRow=" + Arrays.toString(copiedOuter[0]));

        int[][] noRows = new int[0][3];
        int[][] zeroWidth = new int[2][0];
        System.out.println("noRows=" + noRows.length);
        System.out.println("zeroWidthRow=" + zeroWidth[0].length);
        System.out.println("zeroWidthNonNull=" + (zeroWidth[0] != null));

        System.out.println("outerType=" + partial.getClass().getTypeName());
        System.out.println("innerType=" + partial[0].getClass().getTypeName());

        try {
            int[][] missingRow = new int[1][];
            System.out.println(missingRow[0].length);
        } catch (NullPointerException ex) {
            System.out.println("nullRowError=NullPointerException");
        }
        System.out.println("deepRagged=" + Arrays.deepToString(partial));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ArrayOfArraysDemo.java
java ArrayOfArraysDemo
~~~

**Expected stdout chính xác:**

~~~text
rectRows=2
rectColumns0=3
rectColumns1=3
rectDistinct=true
rectRow0=[0, 7, 0]
rectRow1=[0, 0, 0]
partialLength=3
partial[0]=null
partial[1]=null
partial[2]=null
raggedLength=3
ragged[0]=[2, 4]
ragged[1]=[]
ragged[2]=[9]
lastLength=1
sharedRowsSame=true
sameRowSeen=99
afterReplaceRowsSame=false
oldRow=[99, 20]
newRow=[1]
remainingRow=[99, 20]
cloneOuterSame=false
cloneRowSame=true
mutatedSource=55
sourceRow=[2, 55]
copiedRow=[8]
noRows=0
zeroWidthRow=0
zeroWidthNonNull=true
outerType=int[][]
innerType=int[]
nullRowError=NullPointerException
deepRagged=[[2, 55], [], [9]]
~~~

Phần `rectDistinct=true` cho thấy mỗi hàng của `new int[2][3]` là một mảng con độc lập. `partial[r]=null` thể hiện mảng con chưa được tạo. `sharedRowsSame=true` và `sameRowSeen=99` chứng minh hai hàng có thể cùng tham chiếu một mảng con; `cloneRowSame=true` cho thấy sao chép mảng ngoài vẫn chia sẻ các hàng.

Ở dòng cuối, `Arrays.deepToString(partial)` in cấu trúc lồng nhau theo nội dung, khác với `Arrays.toString(partial)` có thể hiển thị chuỗi định danh mảng con khó đọc.

## 8. Lỗi thường gặp, checklist và bài tập

| Nhầm lẫn hoặc lỗi | Cách hiểu đúng |
| --- | --- |
| `int[][]` là một khối ô `int` liên tục duy nhất | Là mảng ngoài chứa **tham chiếu tới `int[]`** |
| `new int[2][]` đã tạo hai `int[]` | Sai: hai hàng đang là `null` |
| `new int[2][3]` dùng một đối tượng hàng chung | Sai: mỗi hàng là mảng con riêng |
| Mọi hàng đều phải có cùng độ dài | Sai: mỗi mảng con có thể có độ dài riêng |
| `matrix.length` là số cột | Sai: là số phần tử của mảng ngoài (số hàng nếu tổ chức theo hàng) |
| `matrix[r].length` luôn đọc được | Cần `r` hợp lệ và `matrix[r] != null` |
| Gán `a[1] = a[0]` sao chép giá trị hàng | Sai: gán **tham chiếu**, khiến hai hàng chia sẻ cùng mảng |
| `a.clone()` sao chép toàn bộ các mảng con | Sai: chỉ tạo mảng ngoài mới, các tham chiếu hàng được sao chép |
| `new int[2][0]` và `new int[2][]` giống nhau | Sai: hàng rỗng không phải hàng `null` |
| Dùng `Arrays.toString` trên `int[][]` để xem tất cả số | Ưu tiên `Arrays.deepToString` cho hiển thị nhiều tầng |

**Bài 1.** Tạo `int[][] data = new int[3][];`. Kiểm tra `data[0] == null`, rồi lần lượt gán `new int[2]`, `new int[0]` và `new int[] {5}` cho ba hàng. In độ dài mỗi hàng.

**Bài 2.** Khởi tạo `int[][] jagged = {{1}, {2, 3}, {4, 5, 6}};`, viết hai vòng lặp để tính tổng và giải thích tại sao vòng trong phải dựa vào `jagged[row].length`.

**Bài 3.** Tạo hai hàng cùng tham chiếu `int[] shared`, cập nhật một phần tử qua hàng đầu rồi đọc qua hàng còn lại. Sau đó gán lại hàng đầu thành một mảng con mới và dự đoán kết quả.

**Bài 4.** So sánh `new int[0][3]`, `new int[2][0]` và `new int[2][]` về số hàng, `null` và độ dài mảng con hợp lệ.

**Bài 5.** Dùng `clone()` cho mảng ngoài, chứng minh `outerCopy[0] == original[0]`. Sau đó viết hàm sao chép từng `int[]` để thay đổi bản sao mà không ảnh hưởng bản gốc.

### Ghi nhớ

**`int[][]` là mảng mà mỗi phần tử có kiểu `int[]`, tức một tham chiếu tới mảng con.** Dạng `new int[rows][columns]` tạo cả mảng ngoài và các hàng; `new int[rows][]` chỉ tạo mảng ngoài, hàng ban đầu là `null`. Các hàng có thể khác độ dài, chia sẻ tham chiếu hoặc được thay bằng mảng khác; vì vậy hãy kiểm tra từng hàng và hiểu rõ việc sao chép tham chiếu.
