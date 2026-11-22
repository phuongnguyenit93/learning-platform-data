# Tạo ma trận chữ nhật và mảng có hàng dài khác nhau — Java 17+

## 1. Mảng hai chiều trong Java thực chất là gì?

Trong Java, một mảng hai chiều như `int[][] matrix` là **mảng chứa các tham chiếu tới mảng `int[]`**. Mỗi phần tử ở mảng ngoài là **một hàng**; mỗi hàng tự có trường `length`.

Vì vậy Java cho phép cả:

- **Ma trận chữ nhật (rectangular array):** các hàng đều có cùng số cột.
- **Mảng răng cưa (jagged/ragged array):** các hàng có thể dài khác nhau, có hàng rỗng, thậm chí hàng chưa được gán (giá trị `null`).

Đây không phải hai kiểu dữ liệu Java riêng biệt: **cả hai đều khai báo `int[][]`**. Khác biệt nằm ở cách tạo và độ dài thực tế của từng `int[]` con.

~~~java
int[][] rectangle = new int[2][3];
int[][] jagged = {{1}, {2, 3}, {4, 5, 6}};
~~~

- `rectangle` gồm **2 hàng × 3 cột**; mọi phần tử mặc định bằng 0.
- `jagged` gồm **3 hàng**, lần lượt dài **1, 2, 3** phần tử.

**Quy tắc bắt buộc:** duyệt theo `matrix.length` cho số hàng, và `matrix[row].length` cho số phần tử trong **chính hàng đó**.

## 2. Tạo ma trận chữ nhật với `new int[rows][cols]`

~~~java
int[][] table = new int[2][3];
table[0][0] = 7;
table[0][2] = 9;
table[1][1] = 5;

System.out.println(java.util.Arrays.deepToString(table));
~~~

**Exact expected stdout:**

~~~text
[[7, 0, 9], [0, 5, 0]]
~~~

Java cấp phát mảng ngoài dài 2 và **hai mảng con riêng biệt**, mỗi mảng con dài 3:

~~~text
table (int[][]) ───> mảng ngoài length = 2
                       [0] ──> int[] {7, 0, 9} length = 3
                       [1] ──> int[] {0, 5, 0} length = 3

Chỉ số hàng: 0, 1
Chỉ số cột trong mỗi hàng: 0, 1, 2
~~~

| Biểu thức | Kết quả |
|---|---:|
| `table.length` | 2 (số hàng) |
| `table[0].length` | 3 |
| `table[1].length` | 3 |
| `table[0][2]` | 9 |
| `table[1][1]` | 5 |

Các phần tử `int` mặc định bằng 0; với `boolean[][]` mặc định là false, còn các ô phần tử kiểu đối tượng mặc định là null.

**Quan trọng:** Mảng chữ nhật được tạo như trên có các hàng dài bằng nhau **ban đầu**, nhưng Java không khóa vĩnh viễn hình dạng đó. Vẫn có thể thay `table[1]` bằng mảng khác độ dài; khi ấy dữ liệu trở thành mảng răng cưa.

## 3. Tạo mảng có hàng dài khác nhau bằng `new int[rows][]`

~~~java
int[][] jagged = new int[3][];
jagged[0] = new int[]{4, 5};
jagged[1] = new int[0];
jagged[2] = new int[]{6, 7, 8};

System.out.println(java.util.Arrays.deepToString(jagged));
~~~

**Exact expected stdout:**

~~~text
[[4, 5], [], [6, 7, 8]]
~~~

Cách này chia thành **hai giai đoạn**:

1. `new int[3][]` tạo mảng ngoài ba phần tử, **mỗi phần tử ban đầu là null**.
2. Gán từng hàng bằng một `int[]` riêng có độ dài tùy nhu cầu.

~~~text
jagged (int[][]) ──> mảng ngoài length = 3
                      [0] ──> {4, 5}     length = 2
                      [1] ──> {}         length = 0
                      [2] ──> {6, 7, 8}  length = 3
~~~

**Không nhầm:**

~~~java
int[][] a = new int[3][];  // Hàng a[0], a[1], a[2] ban đầu null.
int[][] b = new int[3][0]; // Có ba mảng con thật, mỗi mảng dài 0.
~~~

Với `a[0].length` trước khi gán hàng, Java ném `NullPointerException`. Với `b[0].length`, kết quả là `0`.

## 4. Khởi tạo trực tiếp bằng dấu `{ }`

Nếu biết sẵn các giá trị, có thể khai báo:

~~~java
int[][] rectangular = {
    {1, 2, 3},
    {4, 5, 6}
};

int[][] ragged = {
    {10},
    {20, 30},
    {},
    {40, 50, 60}
};
~~~

Hoặc tạo và gán bằng cú pháp array creation:

~~~java
int[][] values = new int[][]{
    {1, 2},
    {3},
    {}
};
~~~

**Chú ý:** `int[][] x = {{1}, {2, 3}};` hợp lệ tại thời điểm khai báo; nhưng để gán nguyên một mảng mới cho biến đã khai báo, phải dùng `new int[][] { ... }` thay vì chỉ viết `{{...}}`.

Có thể chứa hàng null một cách tường minh:

~~~java
int[][] partial = {
    {1, 2},
    null,
    {}
};
~~~

Kiểu của cả `rectangular`, `ragged` và `partial` vẫn là `int[][]`.

## 5. `length` của mảng ngoài và từng hàng

~~~java
int[][] matrix = {{10, 20}, {30}, {}};

System.out.println("rows=" + matrix.length);
for (int row = 0; row < matrix.length; row++) {
    System.out.println("row " + row + " length=" + matrix[row].length);
}
~~~

**Exact expected stdout:**

~~~text
rows=3
row 0 length=2
row 1 length=1
row 2 length=0
~~~

| Biểu thức | Ý nghĩa |
|---|---|
| `matrix.length` | Số phần tử ở mảng ngoài, thường được gọi là **số hàng** |
| `matrix[row]` | Tham chiếu đến mảng con ở hàng `row` |
| `matrix[row].length` | Độ dài **riêng** của hàng đó (nếu khác null) |
| `matrix[row][col]` | Giá trị tại một ô có hàng và cột hợp lệ |

**Không có** một trường chung `matrix.columns` hay `matrix[0].length` được Java bảo đảm là số cột cho mọi hàng. Chỉ khi bạn **đã xác lập và duy trì** bất biến ma trận chữ nhật thì một độ dài cột chung mới có nghĩa.

## 6. Giữ đúng hình dạng khi sử dụng mảng

Việc tạo mảng chữ nhật hay răng cưa quyết định cách thuật toán đọc nó. Dùng `matrix.length` cho số hàng, `matrix[row].length` cho độ dài **hàng hiện tại**, và kiểm tra `matrix[row] != null` trước khi dùng `.length` nếu hàng được phép chưa cấp phát. Cần xử lý `new int[0][3]` (không có hàng), `new int[2][0]` (hai hàng rỗng) và `new int[2][]` (hai hàng ban đầu `null`) theo đúng hợp đồng dữ liệu.

Vòng `for` và enhanced `for` sẽ được phân tích theo mục đích sửa/đọc ở bài **Duyệt bằng chỉ số hoặc enhanced for lồng nhau**. Phần này tập trung vào **tạo dữ liệu và duy trì bất biến hình dạng**.

## 7. Thay hàng có thể biến ma trận chữ nhật thành mảng răng cưa

~~~java
int[][] matrix = new int[2][3];
matrix[1] = new int[]{7};

System.out.println(java.util.Arrays.deepToString(matrix));
System.out.println(matrix[0].length + "," + matrix[1].length);
~~~

**Exact expected stdout:**

~~~text
[[0, 0, 0], [7]]
3,1
~~~

Phần tử `matrix[1]` là một **biến chứa tham chiếu mảng con**, nên có thể được gán sang mảng mới. Trường `length` của từng mảng con vẫn cố định, nhưng **thay tham chiếu hàng** có thể làm các độ dài khác nhau.

Nếu bài toán bắt buộc là ma trận chữ nhật, chương trình phải **duy trì hợp đồng** rằng tất cả hàng tồn tại và cùng dài; khai báo `int[][]` không tự bảo đảm điều đó mãi mãi.

## 8. Kiểm tra dữ liệu có hình chữ nhật hay không

Một quy ước hữu ích: mảng ngoài rỗng được coi là chữ nhật rỗng; mảng ngoài null hoặc có hàng null không đạt điều kiện.

~~~java
static boolean isRectangular(int[][] data) {
    if (data == null) return false;
    if (data.length == 0) return true;
    if (data[0] == null) return false;

    int columns = data[0].length;
    for (int[] row : data) {
        if (row == null || row.length != columns) {
            return false;
        }
    }
    return true;
}
~~~

| Đầu vào | `isRectangular` |
|---|---|
| `new int[2][3]` | true |
| `new int[2][0]` | true |
| `new int[0][3]` | true theo quy ước trong hàm |
| `{{1, 2}, {3}}` | false |
| `new int[2][]` chưa gán hàng | false |
| `null` | false |

Phép kiểm tra có chi phí `O(rows)` vì chỉ đọc độ dài mỗi hàng; không cần duyệt toàn bộ giá trị. Tuy nhiên nó chỉ kiểm tra **trạng thái hiện tại** — nếu sau đó thay một hàng, kết quả có thể khác.



## 9. Chương trình Java 17+ hoàn chỉnh, chạy bằng CLI

Tạo file đúng tên **`RectangularJaggedArrayDemo.java`**:

~~~java
import java.util.Arrays;

public final class RectangularJaggedArrayDemo {
    private RectangularJaggedArrayDemo() {}

    static void describe(String name, int[][] matrix) {
        System.out.println(name + " rows=" + matrix.length);
        for (int row = 0; row < matrix.length; row++) {
            if (matrix[row] == null) {
                System.out.println(name + " row " + row + "=null");
            } else {
                System.out.println(name + " row " + row
                        + " length=" + matrix[row].length
                        + " values=" + Arrays.toString(matrix[row]));
            }
        }
    }

    static int sum(int[][] matrix) {
        int total = 0;
        for (int[] row : matrix) {
            if (row == null) continue;
            for (int value : row) {
                total += value;
            }
        }
        return total;
    }

    static boolean validCell(int[][] matrix, int row, int col) {
        return matrix != null
                && row >= 0 && row < matrix.length
                && matrix[row] != null
                && col >= 0 && col < matrix[row].length;
    }

    static boolean isRectangular(int[][] matrix) {
        if (matrix == null) return false;
        if (matrix.length == 0) return true;
        if (matrix[0] == null) return false;
        int columns = matrix[0].length;
        for (int[] row : matrix) {
            if (row == null || row.length != columns) {
                return false;
            }
        }
        return true;
    }

    static int[][] copyRows(int[][] source) {
        int[][] copy = new int[source.length][];
        for (int row = 0; row < source.length; row++) {
            copy[row] = source[row] == null
                    ? null
                    : Arrays.copyOf(source[row], source[row].length);
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] rectangle = new int[2][3];
        rectangle[0][0] = 1;
        rectangle[0][2] = 3;
        rectangle[1][1] = 5;
        describe("rectangle", rectangle);
        System.out.println("rectangle deep=" + Arrays.deepToString(rectangle));
        System.out.println("rectangle sum=" + sum(rectangle));
        System.out.println("rectangle shape=" + isRectangular(rectangle));

        int[][] jagged = new int[3][];
        jagged[0] = new int[]{4, 5};
        jagged[1] = new int[0];
        jagged[2] = new int[]{6, 7, 8};
        describe("jagged", jagged);
        System.out.println("jagged deep=" + Arrays.deepToString(jagged));
        System.out.println("jagged sum=" + sum(jagged));
        System.out.println("jagged shape=" + isRectangular(jagged));

        System.out.println("jagged valid 0,1=" + validCell(jagged, 0, 1));
        System.out.println("jagged valid 1,0=" + validCell(jagged, 1, 0));
        System.out.println("jagged valid 2,2=" + validCell(jagged, 2, 2));
        System.out.println("jagged valid 3,0=" + validCell(jagged, 3, 0));

        int[][] zeroRows = new int[0][3];
        int[][] zeroColumns = new int[2][0];
        System.out.println("zero rows=" + zeroRows.length);
        System.out.println("zero cols rows=" + zeroColumns.length
                + ",row0=" + zeroColumns[0].length);
        System.out.println("zero rows rectangular=" + isRectangular(zeroRows));
        System.out.println("zero cols rectangular=" + isRectangular(zeroColumns));

        int[][] partial = new int[2][];
        partial[1] = new int[]{9};
        describe("partial", partial);
        System.out.println("partial sum=" + sum(partial));
        System.out.println("partial shape=" + isRectangular(partial));

        try {
            System.out.println(jagged[1][0]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("empty row index=OUT_OF_BOUNDS");
        }
        try {
            System.out.println(partial[0].length);
        } catch (NullPointerException ex) {
            System.out.println("null row length=NULL_POINTER");
        }

        int[][] shallow = rectangle.clone();
        shallow[0][0] = 99;
        System.out.println("shallow original=" + rectangle[0][0]);

        int[][] separate = copyRows(rectangle);
        separate[0][0] = -1;
        System.out.println("separate original=" + rectangle[0][0]
                + ",copy=" + separate[0][0]);

        jagged[0] = new int[]{1};
        System.out.println("replaced row length=" + jagged[0].length);
        System.out.println("jagged after replacement=" + Arrays.deepToString(jagged));
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; terminal ở thư mục chứa file. Không cần thư viện ngoài JDK, Maven, Gradle hay tính năng preview.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 RectangularJaggedArrayDemo.java
java -cp . RectangularJaggedArrayDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\RectangularJaggedArrayDemo.java
java -cp . RectangularJaggedArrayDemo
~~~

### Exact expected stdout

~~~text
rectangle rows=2
rectangle row 0 length=3 values=[1, 0, 3]
rectangle row 1 length=3 values=[0, 5, 0]
rectangle deep=[[1, 0, 3], [0, 5, 0]]
rectangle sum=9
rectangle shape=true
jagged rows=3
jagged row 0 length=2 values=[4, 5]
jagged row 1 length=0 values=[]
jagged row 2 length=3 values=[6, 7, 8]
jagged deep=[[4, 5], [], [6, 7, 8]]
jagged sum=30
jagged shape=false
jagged valid 0,1=true
jagged valid 1,0=false
jagged valid 2,2=true
jagged valid 3,0=false
zero rows=0
zero cols rows=2,row0=0
zero rows rectangular=true
zero cols rectangular=true
partial rows=2
partial row 0=null
partial row 1 length=1 values=[9]
partial sum=9
partial shape=false
empty row index=OUT_OF_BOUNDS
null row length=NULL_POINTER
shallow original=99
separate original=99,copy=-1
replaced row length=1
jagged after replacement=[[1], [], [6, 7, 8]]
~~~

**Đối chiếu:**

1. `rectangle`: hai hàng, mỗi hàng ba phần tử; tổng `1+3+5=9`; `isRectangular` true.
2. `jagged`: ba hàng lần lượt dài 2, 0, 3; tổng `4+5+6+7+8=30`; không chữ nhật.
3. `validCell` kiểm tra cả chỉ số hàng, hàng null, chỉ số cột và độ dài hàng.
4. `new int[0][3]` tạo **0 hàng**; `new int[2][0]` tạo **2 hàng rỗng**.
5. `partial` có một hàng null và một hàng dài 1; hàm `sum` trong ví dụ chủ động bỏ qua hàng null.
6. Truy cập `jagged[1][0]` gây vượt biên vì hàng 1 rỗng; `partial[0].length` gây null-pointer vì hàng 0 null.
7. `rectangle.clone()` sao chép mảng ngoài nhưng chia sẻ các hàng: sửa `shallow[0][0]` làm `rectangle[0][0]` thành 99.
8. `copyRows` tạo các hàng `int[]` riêng; sửa bản sao thành -1 không làm mảng gốc đổi.
9. Thay `jagged[0]` bằng mảng dài 1 vẫn hợp lệ vì đây là phép gán **tham chiếu hàng**.

## 10. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| Nghĩ Java có kiểu ma trận chữ nhật riêng | Hiểu sai cấu trúc `int[][]` | Mảng ngoài chứa các mảng con |
| `new int[3][]` rồi truy cập `a[0][0]` | `NullPointerException` vì chưa tạo hàng | Gán `a[0] = new int[...]` trước |
| Dùng `matrix[0].length` cho mọi hàng | Vượt biên hoặc bỏ sót phần tử | Dùng `matrix[row].length` |
| Nghĩ `matrix.length` là tổng số ô | Tính sai kích thước | `matrix.length` chỉ là số hàng |
| Dùng `matrix[row].length` trên hàng null | `NullPointerException` | Kiểm tra hàng null |
| Dùng `<= length` khi duyệt | `ArrayIndexOutOfBoundsException` | Dùng `< length` |
| Cho rằng `new int[0][3]` có thể truy cập `[0]` | Mảng ngoài không có hàng | Kiểm tra `matrix.length > 0` |
| Cho rằng `new int[2][0]` có các ô cột | Hàng có độ dài 0 | Không truy cập `[row][0]` |
| Nghĩ từng `length` có thể sửa | Trường mảng là final | Thay cả tham chiếu hàng bằng mảng mới |
| Nghĩ `matrix.clone()` sao chép mọi hàng | Hai cấu trúc vẫn chia sẻ mảng con | `Arrays.copyOf` từng hàng |
| Giả định không có hàng null chỉ vì kiểu là `int[][]` | Crash ở `.length` | Xác lập hợp đồng dữ liệu và kiểm tra |
| Cho rằng các hàng có cùng kích thước mãi mãi | Thay hàng làm mất hình chữ nhật | Kiểm tra/duy trì bất biến kích thước |

## 11. Bài tập có đáp án

### A — phân biệt chữ nhật và răng cưa

~~~java
int[][] a = new int[2][3];
int[][] b = {{1}, {2, 3}};
~~~

**Đáp án:** `a` ban đầu là ma trận chữ nhật 2×3; `b` là mảng răng cưa có hai hàng dài 1 và 2. Cả hai đều có kiểu `int[][]`.

### B — mảng ngoài đã tạo, nhưng hàng chưa tạo

~~~java
int[][] a = new int[2][];
// System.out.println(a[0].length);
~~~

**Đáp án:** `a.length == 2`, nhưng `a[0] == null`. Nếu bật dòng truy cập `.length`, chương trình ném `NullPointerException`. Sửa:

~~~java
a[0] = new int[3];
System.out.println(a[0].length);
~~~

**Exact stdout:**

~~~text
3
~~~

### C — tổng các hàng khác độ dài

~~~java
int[][] a = {{1, 2}, {}, {3, 4}};
int total = 0;
for (int[] row : a) {
    for (int value : row) {
        total += value;
    }
}
System.out.println(total);
~~~

**Đáp án:** in `10`. Hàng rỗng có 0 lượt duyệt.

### D — truy cập chỉ số

~~~java
int[][] a = {{5}, {6, 7}};
System.out.println(a[1][1]);
// System.out.println(a[0][1]);
~~~

**Đáp án:** in `7`; `a[0][1]` vượt biên vì hàng đầu chỉ dài 1.

### E — sao chép mảng hai chiều

~~~java
int[][] a = {{1}, {2}};
int[][] b = a.clone();
b[0][0] = 9;
System.out.println(a[0][0]);
~~~

**Đáp án:** in `9`, vì bản clone chỉ sao chép mảng ngoài, còn hàng `a[0]` và `b[0]` cùng tham chiếu mảng con.

### F — thay hàng làm đổi hình dạng

~~~java
int[][] a = new int[2][2];
a[1] = new int[4];
System.out.println(a[0].length + "," + a[1].length);
~~~

**Đáp án:** in `2,4`. Java cho phép thay một hàng bằng mảng có độ dài khác.

## 12. Checklist và kết luận

- [ ] Biết `int[][]` là mảng chứa các mảng `int[]`.
- [ ] Tạo ma trận chữ nhật bằng `new int[rows][cols]`.
- [ ] Tạo mảng răng cưa bằng `new int[rows][]` rồi tạo từng hàng.
- [ ] Phân biệt hàng `null` với hàng rỗng `new int[0]`.
- [ ] Đọc số hàng bằng `matrix.length`, số cột thực tế từng hàng bằng `matrix[row].length`.
- [ ] Duyệt đúng cả hàng dài ngắn khác nhau, không mặc định số cột chung.
- [ ] Kiểm tra đủ biên hàng/cột và trạng thái null trước khi truy cập.
- [ ] Hiểu `new int[0][3]` và `new int[2][0]` là các cấu trúc khác nhau.
- [ ] Biết thay tham chiếu hàng có thể làm dữ liệu không còn chữ nhật.
- [ ] Phân biệt sao chép một cấp `clone()` với sao chép từng hàng `Arrays.copyOf`.
- [ ] Biết cách xác minh hình chữ nhật khi bài toán yêu cầu các hàng cùng độ dài.
- [ ] Biên dịch và chạy `RectangularJaggedArrayDemo.java` trên Java 17+ và đối chiếu stdout.

**Kết luận:** Trong Java 17+, `int[][]` **không bắt buộc là một khối chữ nhật**; mỗi hàng là một mảng riêng có độ dài và tham chiếu riêng. `new int[r][c]` tạo các hàng ban đầu cùng dài, còn `new int[r][]` cho phép cấp phát từng hàng khác nhau. Muốn duyệt đúng và an toàn, hãy luôn dựa vào **`matrix.length` cho số hàng, `matrix[row].length` cho độ dài hàng hiện tại**, đồng thời xử lý hàng rỗng/null theo hợp đồng dữ liệu.