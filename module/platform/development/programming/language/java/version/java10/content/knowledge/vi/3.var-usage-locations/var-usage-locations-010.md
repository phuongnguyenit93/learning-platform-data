# Giới hạn cú pháp dấu ngoặc mảng sau tên biến khi dùng `var` (Java 10+)

## 1. Quy tắc cần nhớ

Khi khai báo biến cục bộ bằng `var`, **không được đặt cặp dấu ngoặc vuông `[]` ngay sau tên biến**, dù biểu thức khởi tạo có tạo một mảng hợp lệ. Đây là quy tắc kiểm tra **lúc biên dịch** của Java, áp dụng từ Java 10 và vẫn đúng trong các phiên bản Java hiện nay.

```java
var numbers = new int[3];              // HỢP LỆ: numbers có kiểu int[]
var scores = new int[]{10, 20, 30};    // HỢP LỆ: scores có kiểu int[]
// var numbers[] = new int[3];          // SAI: có [] sau tên numbers
// var scores[][] = new int[2][3];      // SAI: có [][] sau tên scores
```

**Điểm mấu chốt:** `var` suy luận **toàn bộ kiểu mảng** từ biểu thức ở bên phải dấu `=`. Vì vậy, tên biến bên trái chỉ là tên, không mang thêm `[]` để bổ sung chiều mảng.

Trong thuật ngữ của Java Language Specification (JLS) `14.4, khi `LocalVariableType` là `var` thì `VariableDeclaratorId` **không được có bất kỳ cặp dấu ngoặc vuông nào**. Nếu viết `var a[] = ...`, trình biên dịch báo lỗi ngay cả khi bên phải là `new int[...]`.

Không nên hiểu rằng `var` chỉ dùng cho giá trị đơn. Biến khai báo bằng `var` **hoàn toàn có thể có kiểu mảng** như `int[]`, `String[][]`, `long[][][]`; giới hạn chỉ nằm ở **cách viết khai báo**.

## 2. Phân biệt vị trí của dấu `[]`

Có hai nơi rất khác nhau có thể xuất hiện dấu ngoặc mảng:

1. **Trong phần khai báo kiểu tường minh**, ví dụ `int[] a` hoặc `String[][] names`. Đây là phần của kiểu Java.
2. **Trong biểu thức khởi tạo**, ví dụ `new int[3]`, `new int[]{1, 2}` hoặc `new String[2][3]`. Đây là nơi tạo ra giá trị có kiểu mảng để `var` suy luận.

Với `var`, dạng chuẩn là:

```java
var tenBien = bieuThucTaoMang;
```

Ví dụ đối chiếu:

| Khai báo | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `int[] a = new int[3];` | Có | Khai báo tường minh: `int[]` là kiểu. |
| `var a = new int[3];` | Có | `var` suy luận `int[]` từ `new int[3]`. |
| `var a = new int[]{1, 2, 3};` | Có | `new int[]{...}` là biểu thức tạo mảng có kiểu `int[]`. |
| `var a[] = new int[3];` | **Không** | `[]` nằm sau tên biến `a`. |
| `var a[][] = new int[2][3];` | **Không** | `[][]` nằm sau tên biến `a`. |
| `var[] a = new int[3];` | **Không** | Không thể dùng `var[]` như một tên kiểu mảng tường minh. |
| `var a = {1, 2, 3};` | **Không** | `{...}` là array initializer rút gọn, cần một kiểu đích tường minh; đây là lỗi khác với `a[]`. |

Java vẫn chấp nhận kiểu khai báo tường minh `int a[] = new int[3];`, nhưng kiểu viết `int[] a` rõ nghĩa và được ưu tiên trong mã Java hiện đại. Quy tắc của `var` chặt hơn: dù cú pháp `int a[]` được chấp nhận, **`var a[]` không được chấp nhận**.

## 3. Cách viết mảng một chiều đúng với `var`

### Mảng tạo theo kích thước

```java
var values = new int[4];        // kiểu tĩnh: int[], gồm bốn phần tử 0
var names = new String[2];      // kiểu tĩnh: String[], hai phần tử ban đầu là null
var flags = new boolean[3];     // kiểu tĩnh: boolean[], các phần tử ban đầu là false
```

Phần `[4]`, `[2]` hay `[3]` là số lượng phần tử của biểu thức `new`, **không phải dấu ngoặc đặt sau tên biến**. Bất kể độ dài mảng là bao nhiêu, kiểu của `values` vẫn là `int[]`.

### Mảng tạo kèm phần tử

```java
var values = new int[]{4, 5, 6};               // int[]
var words = new String[]{"Java", "10"};        // String[]
var temperatures = new double[]{21.5, 22.0}; // double[]
```

Với `var`, cần giữ `new int[]` (hoặc kiểu phù hợp) trước phần `{...}`. Dạng viết rút gọn sau chỉ hợp lệ khi khai báo kiểu mảng tường minh:

```java
int[] values = {4, 5, 6};            // HỢP LỆ: kiểu đích là int[]
var inferred = new int[]{4, 5, 6};  // HỢP LỆ: biểu thức tự có kiểu int[]
// var wrong = {4, 5, 6};           // SAI: không có kiểu đích cho {...}
```

**Hai lỗi độc lập cần phân biệt:**

- `var wrong[] = new int[]{4, 5, 6};` sai vì **dấu `[]` sau tên biến**.
- `var wrong = {4, 5, 6};` sai vì **array initializer rút gọn không cung cấp kiểu độc lập** cho `var`.

Thêm `[]` vào tên biến sẽ **không** giải quyết được trường hợp khởi tạo `{...}`.

## 4. Mảng hai chiều hoặc nhiều chiều

Số chiều của mảng không làm thay đổi quy tắc. Hãy để biểu thức khởi tạo cung cấp thông tin về số chiều, còn tên biến không có dấu ngoặc.

```java
var matrix = new int[2][3]; // kiểu int[][]: hai hàng, mỗi hàng ba phần tử
var lines = new String[][]{
        {"A", "B"},
        {"C"}
};                             // kiểu String[][]
var cube = new long[2][3][4]; // kiểu long[][][]
```

Những cách dưới đây đều sai:

```java
// var matrix[][] = new int[2][3]; // SAI: [][] sau tên biến
// var lines[] = new String[][]{{"A"}}; // SAI: [] sau tên biến
// var[][] matrix = new int[2][3]; // SAI: var[][] không phải kiểu tường minh
```

Để nhìn thấy kiểu qua thao tác truy cập:

```java
var matrix = new int[][]{{1, 2}, {3, 4}}; // int[][]
var firstRow = matrix[0];                  // int[]
var firstValue = matrix[0][0];             // int
```

Dấu `[0]` trong `matrix[0]` là **phép truy cập phần tử**, hoàn toàn khác với `[]` đặt sau tên biến trong dòng khai báo. `var` không cấm truy cập mảng, dùng `length`, sửa phần tử, hay duyệt mảng bằng vòng lặp.

Với mảng nhiều chiều chưa cấp phát hết các hàng:

```java
var partial = new int[2][];     // hợp lệ, kiểu int[][]
partial[0] = new int[]{1, 2};   // hợp lệ
partial[1] = new int[]{3};      // hợp lệ
```

Mảng `partial` có hai phần tử kiểu `int[]`; ngay sau `new int[2][]`, các phần tử này ban đầu là `null`. Phải tạo từng hàng trước khi truy cập phần tử bên trong. Đây là quy tắc mảng thông thường, không phải ngoại lệ của `var`.

## 5. Trong vòng lặp, `var` vẫn không đi kèm `[]` sau tên biến

Ở vòng lặp enhanced `for`, kiểu của phần tử được suy luận từ mảng (hoặc `Iterable`) đang duyệt:

```java
var values = new int[]{1, 2, 3};
for (var value : values) {     // value có kiểu int
    System.out.println(value);
}
```

Khi duyệt mảng hai chiều, mỗi phần tử ở vòng ngoài lại là một mảng:

```java
var grid = new int[][]{{1, 2}, {3, 4}};
for (var row : grid) {         // row có kiểu int[]
    for (var value : row) {    // value có kiểu int
        System.out.println(value);
    }
}
```

Không viết `for (var row[] : grid)`: dấu ngoặc sau tên biến vẫn bị cấm. Cũng không viết `for (var[] row : grid)`, vì `var[]` không thể thay cho kiểu phần tử tường minh. Nếu muốn khai báo rõ kiểu phần tử là mảng, dùng `for (int[] row : grid)`.

Tương tự trong phần khởi tạo của vòng lặp `for` thông thường:

```java
for (var i = 0; i < 3; i++) {      // hợp lệ: i có kiểu int
    System.out.println(i);
}

// for (var a[] = new int[3]; ... ) // sai vì [] sau tên a
```

## 6. Lỗi liên quan: không khai báo nhiều biến cùng lúc với một `var`

Dù không đặt `[]` sau tên, khai báo nhiều biến bằng cùng một `var` cũng không hợp lệ:

```java
// var first = new int[2], second = new int[3]; // SAI: nhiều declarator
```

Cách viết đúng là tách thành hai khai báo, để mỗi biến suy luận từ biểu thức của chính nó:

```java
var first = new int[2];    // int[]
var second = new int[3];   // int[]
```

Nếu cần khai báo nhiều mảng bằng kiểu tường minh, `int[] first = new int[2], second = new int[3];` vẫn là cú pháp Java hợp lệ. Tuy nhiên, với `var`, **mỗi khai báo chỉ được có một biến, có biểu thức khởi tạo, và tên biến không được có dấu ngoặc mảng**.

## 7. Ví dụ hoàn chỉnh, biên dịch và chạy được (Java 17+)

Tạo tệp `VarArrayBracketDemo.java`:

```java
import java.util.Arrays;

public class VarArrayBracketDemo {
    public static void main(String[] args) {
        int[] conventional = {2, 4, 6};          // kiểu tường minh int[]
        var inferred = new int[]{2, 4, 6};       // var suy luận int[]
        var zeros = new int[3];                  // var suy luận int[]
        var grid = new String[][]{
                {"A", "B"},
                {"C"}
        };                                       // var suy luận String[][]
        var rows = new int[][]{{1, 2}, {3, 4}};  // var suy luận int[][]

        System.out.println("conventional=" + Arrays.toString(conventional));
        System.out.println("inferred=" + Arrays.toString(inferred));
        System.out.println("zerosLength=" + zeros.length);
        System.out.println("grid=" + Arrays.deepToString(grid));
        System.out.println("rows=" + rows.length
                + ", firstRow=" + Arrays.toString(rows[0]));

        int sum = 0;
        for (var value : inferred) {  // value là int
            sum += value;
        }
        System.out.println("sum=" + sum);

        for (var row : rows) {        // row là int[]
            System.out.println("row=" + Arrays.toString(row));
        }
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac VarArrayBracketDemo.java
java VarArrayBracketDemo
```

Kết quả:

```text
conventional=[2, 4, 6]
inferred=[2, 4, 6]
zerosLength=3
grid=[[A, B], [C]]
rows=2, firstRow=[1, 2]
sum=12
row=[1, 2]
row=[3, 4]
```

Trong chương trình này, các biến `inferred` và `zeros` có cùng kiểu `int[]` với `conventional` dù phần khai báo không viết tường minh `int[]`. Biến `rows` có kiểu `int[][]`; khi duyệt bằng `for (var row : rows)`, biến `row` có kiểu `int[]`, không cần viết `[]` sau tên.

## 8. Các lỗi thường gặp và cách sửa

| Viết sai | Cách sửa đúng | Nguyên nhân |
| --- | --- | --- |
| `var a[] = new int[3];` | `var a = new int[3];` | Xóa `[]` sau tên biến; kiểu mảng lấy từ biểu thức `new`. |
| `var a[][] = new int[2][3];` | `var a = new int[2][3];` | Không thể bổ sung số chiều sau tên biến. |
| `var[] a = new int[3];` | `var a = new int[3];` | `var[]` không phải cú pháp khai báo kiểu hợp lệ. |
| `var a = {1, 2, 3};` | `var a = new int[]{1, 2, 3};` | Array initializer rút gọn cần target type tường minh. |
| `for (var row[] : grid)` | `for (var row : grid)` | Phần khai báo phần tử không được có `[]` sau tên. |
| `var a = new int[2], b = new int[3];` | Tách thành hai lệnh `var`. | Một khai báo `var` chỉ có một declarator. |

Nếu mục tiêu là **nêu rõ kiểu mảng trong mã nguồn**, dùng khai báo tường minh `int[] values = ...` hoặc `String[][] grid = ...`. Nếu mục tiêu là **rút gọn khai báo bằng suy luận kiểu**, dùng `var values = new int[]{...}`. Đừng trộn phần khai báo kiểu tường minh với cách viết `var`.

## 9. Tự kiểm tra

Hãy xác định từng khai báo sau hợp lệ hay không và, nếu hợp lệ, kiểu của biến:

```java
var a = new byte[5];
var b = new String[][]{{"x"}, {"y", "z"}};
// var c[] = new String[2];
// var d = {"x", "y"};
var e = new int[2][];
var f = e[0];
```

**Đáp án:**

1. `a` hợp lệ, kiểu `byte[]`.
2. `b` hợp lệ, kiểu `String[][]`.
3. `c[]` không hợp lệ vì chứa dấu `[]` sau tên biến trong khai báo `var`.
4. `d` không hợp lệ vì `{"x", "y"}` là array initializer rút gọn cần kiểu đích.
5. `e` hợp lệ, kiểu `int[][]`.
6. `f` hợp lệ, kiểu `int[]`. Giá trị ban đầu của `e[0]` là `null`; việc gán `null` vào một biến tham chiếu kiểu `int[]` là hợp lệ, và việc truy cập phần tử của `f` khi chưa gán mảng thực sẽ gây `NullPointerException`.

**Ghi nhớ:** Với `var`, phần khai báo là `var tên = biểuThức;`. Mảng một chiều hay nhiều chiều đều hợp lệ nếu **kiểu mảng đến từ biểu thức khởi tạo**; dấu ngoặc sau **tên biến** thì không hợp lệ.

## Nguồn chính thức

- [Java Language Specification (Java SE 25), `14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4), quy định lỗi biên dịch khi `VariableDeclaratorId` có một hoặc nhiều cặp ngoặc với `var`.
- [Java Language Specification (Java SE 25), `10.2 — Array Variables](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html#jls-10.2), về kiểu và khai báo biến mảng.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286), tính năng suy luận kiểu cục bộ được giới thiệu ở Java 10.
