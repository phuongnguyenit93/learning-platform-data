# Mảng tạo bằng `new` và dạng khởi tạo mảng không có kiểu khi dùng `var`

*Chủ đề Java 10 — “var và biểu thức”. Các quy tắc dưới đây thuộc cú pháp Java hiện hành, tiếp tục áp dụng trong Java 17+ và các JDK mới hơn.*

## 1. Quy tắc cốt lõi

Khi khai báo một biến cục bộ bằng `var`, trình biên dịch Java phải suy luận được một **kiểu tĩnh** từ biểu thức bên phải dấu `=`. Mảng Java là một kiểu thực sự, chẳng hạn `int[]`, `String[]` hoặc `int[][]`. Vì thế, **biểu thức tạo mảng với `new` và kiểu phần tử rõ ràng** có thể dùng cùng `var`:

~~~java
var values = new int[]{1, 2, 3};      // Hợp lệ: values có kiểu int[]
var buffer = new byte[16];             // Hợp lệ: buffer có kiểu byte[]
var names = new String[]{"An", "Bình"}; // Hợp lệ: names có kiểu String[]
~~~

Trái lại, **dạng khởi tạo mảng rút gọn chỉ có dấu ngoặc nhọn** không tự mang một kiểu độc lập để `var` suy luận:

~~~java
// Sai: array initializer thuần túy không được dùng làm initializer của var.
var values = {1, 2, 3};
~~~

Sửa theo một trong hai cách:

~~~java
int[] values = {1, 2, 3};           // Kiểu đích int[] được khai báo tường minh
var values2 = new int[]{1, 2, 3};   // Biểu thức new int[] có kiểu int[]
~~~

**Điểm cần nhớ:** `var` không có nghĩa là “Java tự đoán kiểu mảng chỉ từ các phần tử trong ngoặc nhọn”. Đó là suy luận kiểu biến cục bộ dựa trên **biểu thức có kiểu**. Hai cách viết mảng nhìn giống nhau nhưng đứng ở các ngữ cảnh cú pháp khác nhau.

## 2. Phân biệt ba hình thức tạo và khởi tạo mảng

### 2.1. Biểu thức tạo mảng có kích thước: `new T[n]`

~~~java
var counts = new int[3];         // int[] gồm 3 phần tử, mặc định đều là 0
var names = new String[2];      // String[] gồm 2 phần tử, mặc định đều là null
var matrix = new int[2][4];     // int[][] gồm 2 hàng, mỗi hàng 4 phần tử int
~~~

Biểu thức sau `=` đã cho biết kiểu phần tử `T` và số chiều; trình biên dịch suy luận được kiểu mảng của biến cục bộ. Với `new int[3]`, các giá trị ban đầu là `0`; với `new String[2]`, các tham chiếu ban đầu là `null`. Số chiều và kích thước mảng là chuyện riêng với suy luận kiểu của `var`.

### 2.2. Biểu thức tạo mảng có phần tử: `new T[]{...}`

~~~java
var numbers = new int[]{3, 5, 8};              // int[]
var tags = new String[]{"core", "java"};        // String[]
var points = new double[]{1.5, 2.0};           // double[]
var empty = new long[]{};                      // long[] hợp lệ, độ dài 0
var rows = new int[][]{{1, 2}, {3}};           // int[][], các hàng dài khác nhau
~~~

`new T[]{...}` **là một biểu thức tạo mảng** (array creation expression). Kiểu `T` xuất hiện rõ sau `new`; cặp `[]` biểu thị một chiều và phần `{...}` cung cấp các giá trị. Vì biểu thức có kiểu mảng xác định, `var` suy luận được mà không cần ghi kiểu bên trái.

Không được vừa ghi kích thước cho chính chiều đó vừa cung cấp danh sách phần tử theo dạng này:

~~~java
// Sai cú pháp: không thể ghép kích thước và initializer như sau.
var numbers = new int[3]{1, 2, 3};
~~~

Hãy dùng `new int[3]` rồi gán phần tử, hoặc dùng `new int[]{1, 2, 3}`.

### 2.3. Dạng khởi tạo rút gọn: `{...}`

~~~java
int[] numbers = {3, 5, 8};                      // Hợp lệ
String[] tags = {"core", "java"};               // Hợp lệ
int[][] rows = {{1, 2}, {3}};                   // Hợp lệ
~~~

Phần `{...}` ở đây là **array initializer**, được dùng trong ngữ cảnh khai báo mảng đã có **kiểu đích tường minh**. Tự nó **không phải một biểu thức độc lập có thể đặt tùy ý sau `=`**.

Do đó:

~~~java
// Ba dòng sau là ví dụ CỐ Ý KHÔNG BIÊN DỊCH.
var numbers = {3, 5, 8};            // Thiếu kiểu đích
var tags = {"core", "java"};        // Thiếu kiểu đích
var rows = {{1, 2}, {3}};           // Thiếu kiểu đích ở cả mảng ngoài
~~~

Trình biên dịch không biến dạng `{...}` thành `int[]`, `String[]` hay `Object[]` chỉ dựa vào hình thức phần tử. Cần dùng `new T[]{...}` hoặc khai báo kiểu mảng phía bên trái.

## 3. Bảng đối chiếu cú pháp hợp lệ và không hợp lệ

| Dòng khai báo | Hợp lệ? | Kiểu hoặc nguyên nhân |
| --- | --- | --- |
| `int[] a = {1, 2};` | Có | `a` được khai báo rõ là `int[]` |
| `var a = new int[]{1, 2};` | Có | Biểu thức bên phải có kiểu `int[]` |
| `var a = new int[2];` | Có | Biểu thức bên phải có kiểu `int[]` |
| `var a = {1, 2};` | **Không** | `{...}` không có kiểu độc lập cho `var` |
| `var a = new int[]{};` | Có | Mảng `int[]` độ dài 0 |
| `var a = {};` | **Không** | Dạng `{...}` không có kiểu đích |
| `int[] a = {};` | Có | `int[]` rỗng, vì đã có kiểu đích |
| `var a = new int[0];` | Có | Mảng `int[]` độ dài 0 |
| `var a = new int[2]{1, 2};` | **Không** | Sai cú pháp tạo mảng: kích thước đi cùng initializer |
| `var a = new int[];` | **Không** | Thiếu cả kích thước lẫn initializer |
| `var grid = new int[][]{{1, 2}, {3}};` | Có | `grid` có kiểu `int[][]` |
| `var grid = {{1, 2}, {3}};` | **Không** | Nested array initializer vẫn cần kiểu đích |
| `int[][] grid = {{1, 2}, {3}};` | Có | Có kiểu đích `int[][]` |
| `var a = new String[]{null};` | Có | Biểu thức có kiểu `String[]`; phần tử có thể là `null` |
| `var a = null;` | **Không** | `null` đơn lẻ không cung cấp kiểu để suy luận |

Các ví dụ không hợp lệ nhằm giải thích lỗi cú pháp/kiểu, **không** được chép chung vào một tệp chạy. Các biến trùng tên trong bảng cũng là các phương án độc lập.

## 4. Chương trình minh họa chạy được trên Java 17+

Ví dụ dưới đây cho thấy mảng dùng với `var` vẫn là mảng Java thông thường, và dạng `{...}` chỉ được phép khi có kiểu khai báo rõ. Chương trình biên dịch và chạy được bằng `javac`/`java`.

~~~java
// File: VarArrayDemo.java
import java.util.Arrays;

public class VarArrayDemo {
    public static void main(String[] args) {
        var scores = new int[]{10, 20, 30};     // int[]
        var flags = new boolean[3];            // boolean[], mặc định false
        var names = new String[]{"Lan", "Mai"}; // String[]
        var grid = new int[][]{{1, 2}, {3}};    // int[][]
        var empty = new long[]{};              // long[] độ dài 0

        int[] shorthand = {7, 8};              // Có kiểu đích tường minh
        var equivalent = new int[]{7, 8};      // Cùng kiểu và giá trị

        System.out.println("scores = " + Arrays.toString(scores));
        System.out.println("flags = " + Arrays.toString(flags));
        System.out.println("names = " + Arrays.toString(names));
        System.out.println("grid = " + Arrays.deepToString(grid));
        System.out.println("empty length = " + empty.length);
        System.out.println("shorthand = " + Arrays.toString(shorthand));
        System.out.println("equivalent = " + Arrays.toString(equivalent));

        var alias = scores;                    // int[], cùng tham chiếu
        alias[0] = 99;
        System.out.println("scores after alias write = "
                + Arrays.toString(scores));
    }
}
~~~

Tại thư mục chứa tệp `VarArrayDemo.java`:

~~~bash
javac VarArrayDemo.java
java VarArrayDemo
~~~

Đầu ra chính xác:

~~~text
scores = [10, 20, 30]
flags = [false, false, false]
names = [Lan, Mai]
grid = [[1, 2], [3]]
empty length = 0
shorthand = [7, 8]
equivalent = [7, 8]
scores after alias write = [99, 20, 30]
~~~

Giải thích:

1. `scores`, `flags` và `equivalent` đều có **kiểu tĩnh `int[]` hoặc `boolean[]`** tương ứng, hoàn toàn xác định khi biên dịch. Chúng không chuyển kiểu tùy theo giá trị phần tử.
2. `new boolean[3]` không được truyền các phần tử, nên các giá trị có mặc định `false`.
3. `grid` là `int[][]`. `Arrays.deepToString` in các mảng lồng nhau thành chuỗi đọc được; `Arrays.toString` được dùng với mảng một chiều.
4. `shorthand` và `equivalent` đều là `int[]`. Sự khác biệt nằm ở cú pháp khởi tạo/khai báo, không phải cấu trúc mảng được tạo.
5. `alias` dùng `var` nhưng không tạo bản sao. Nó trỏ tới cùng mảng `scores` nên sửa `alias[0]` cũng làm `scores[0]` đổi. `var` chỉ suy luận kiểu, không thay đổi ngữ nghĩa tham chiếu hay tính thay đổi được của mảng.

## 5. Vì sao `{...}` thiếu kiểu còn `new T[]{...}` có kiểu?

Để hiểu ranh giới cú pháp, cần tách hai việc:

- **Khai báo mảng với kiểu đã biết:** ở `int[] a = {1, 2}`, vế trái `int[]` đặt ra kiểu đích; Java cho phép một *array initializer* `{1, 2}` trong chính ngữ cảnh đó.
- **Suy luận kiểu từ biểu thức:** ở `var a = ...`, không có tên kiểu bên trái. Vế phải phải là một biểu thức phù hợp để trình biên dịch suy ra kiểu. `new int[]{1, 2}` đáp ứng; `{1, 2}` riêng lẻ không đáp ứng.

Phần `new int[]` **không bị lược bỏ chỉ vì trình biên dịch nhìn thấy các số nguyên**. Nó cung cấp kiểu phần tử và xác định rằng Java đang xử lý một biểu thức tạo mảng, không phải một dấu ngoặc nhọn không có ngữ cảnh kiểu.

Đặc biệt, dấu ngoặc nhọn không phải cách biểu diễn một “collection literal” tổng quát trong Java. Các cú pháp như `{1, 2}` không tự động biến thành `List<Integer>`, `int[]` hoặc một kiểu động.

### Trường hợp gán lại mảng đã khai báo

Đối với biến đã tồn tại, không thể gán một array initializer trần:

~~~java
int[] values = {1, 2};
values = new int[]{3, 4}; // Hợp lệ: biểu thức tạo mảng
// values = {3, 4};      // Sai: không thể dùng array initializer như biểu thức
~~~

Điều này cho thấy quy tắc không phụ thuộc riêng vào `var`. Dạng rút gọn `{...}` chỉ hợp lệ tại vị trí cú pháp cho phép, chẳng hạn khai báo mảng với kiểu rõ ràng hoặc các array initializer lồng nhau có kiểu đích.

## 6. Mảng nhiều chiều và mảng không đều

Kiểu mảng hai chiều trong Java thực chất là “mảng chứa các mảng”. Ví dụ:

~~~java
var table = new int[][]{
    {1, 2, 3},
    {4},
    {}
}; // Kiểu int[][], ba hàng dài 3, 1 và 0
~~~

`var` suy luận `int[][]` từ `new int[][]`. Các `{...}` bên trong có ngữ cảnh là phần tử kiểu `int[]` do biểu thức tạo mảng ngoài cung cấp. Điều này **không** có nghĩa `var table = {{1, 2, 3}, {4}, {}};` sẽ hợp lệ; khi bỏ phần `new int[][]`, toàn bộ initializer ngoài mất kiểu đích.

Một cách tạo mảng khác cũng hợp lệ:

~~~java
var rows = new int[2][]; // Kiểu int[][]; mỗi phần tử ban đầu là null
rows[0] = new int[]{5, 6};
rows[1] = new int[]{7};
~~~

`new int[2][]` tạo mảng ngoài độ dài 2; hai mảng con chỉ được tạo khi gán ở các dòng tiếp theo. Không nên nhầm `new int[2][]` với `new int[2][0]`: hình thức đầu có các phần tử mảng con ban đầu là `null`; hình thức sau tạo sẵn hai mảng con độ dài 0.

### Không thể suy luận kiểu của mọi thứ bên trong ngoặc nhọn

~~~java
// KHÔNG HỢP LỆ: thiếu kiểu cho array initializer ngoài.
var ragged = {{1, 2}, {3}};

// HỢP LỆ: kiểu ngoài và chiều được nêu rõ.
var raggedArray = new int[][]{{1, 2}, {3}};

// HỢP LỆ: kiểu đích được khai báo tường minh.
int[][] declaredArray = {{1, 2}, {3}};
~~~

Không cần mọi hàng có cùng độ dài khi dùng `int[][]`. Tuy nhiên, mỗi phần tử không-null của `int[][]` phải là `int[]`, phù hợp với kiểu mảng đã khai báo.

## 7. Khi mảng được tạo bởi biểu thức khác

`var` không bắt buộc vế phải phải viết `new`. Điều kiện thực sự là **biểu thức khởi tạo có kiểu xác định**:

~~~java
import java.util.Arrays;

class ArrayFromExpression {
    static int[] create() {
        return new int[]{2, 4, 6};
    }

    static void demo() {
        var fromMethod = create();              // int[]
        var copied = Arrays.copyOf(fromMethod, 2); // int[]
        var first = fromMethod[0];              // int, không phải int[]
        var size = fromMethod.length;           // int
        var same = fromMethod;                  // int[], cùng mảng
    }
}
~~~

Trình biên dịch suy luận kiểu `fromMethod` từ chữ ký `create()`, `copied` từ kiểu trả về của `Arrays.copyOf`, `first` từ truy cập phần tử mảng và `size` từ thuộc tính `length`. Tức là **kiểu phụ thuộc biểu thức đang xét**, không phải chỉ vì trong mã có xuất hiện mảng.

Biểu thức điều kiện có hai nhánh tương thích cũng có thể cho kiểu mảng:

~~~java
boolean pickFirst = true;
var selected = pickFirst ? new int[]{1, 2} : new int[]{3}; // int[]
~~~

Ngược lại, hai vế `{1, 2}` và `{3}` không thể được sử dụng như các biểu thức độc lập ở vị trí tương tự.

## 8. Trường hợp `null` và mảng rỗng

`null` tự nó không cho `var` một kiểu suy luận phù hợp:

~~~java
// Sai: var unknown = null;

// Hợp lệ và rõ ràng hơn khi mục tiêu là tham chiếu mảng ban đầu null:
String[] unknown = null;

// Hợp lệ về cú pháp vì biểu thức ép kiểu có kiểu String[],
 // nhưng thường ít dễ đọc hơn nếu mục tiêu chỉ là khai báo mảng:
var casted = (String[]) null;
~~~

Trong trường hợp thông thường, nên viết `String[] unknown = null;` hoặc tạo mảng thực tế nếu phù hợp yêu cầu. Việc thêm ép kiểu chỉ để làm `var` chấp nhận `null` hiếm khi giúp mã dễ hiểu.

Mảng rỗng **không đồng nghĩa** với tham chiếu `null`:

~~~java
var emptyByInitializer = new int[]{}; // int[] độ dài 0, khác null
var emptyBySize = new int[0];         // int[] độ dài 0, khác null
~~~

Cả hai tạo một đối tượng mảng có `length == 0`. Mảng vẫn có kiểu `int[]`; chỉ có số phần tử bằng 0. Do vậy, ngay cả khi chưa có phần tử nào để “đoán”, `var` vẫn hoạt động với `new int[]{}` vì kiểu đã được viết trong biểu thức tạo mảng.

## 9. Quy tắc riêng của `var` trong khai báo local

Ngoài việc vế phải phải là biểu thức có kiểu, cú pháp khai báo local với `var` có các giới hạn liên quan:

~~~java
// Sai: var data;                        // Thiếu initializer
// Sai: var data = null;                 // Không suy luận được kiểu chỉ từ null
// Sai: var a = new int[2], b = new int[3]; // var không khai báo đồng thời nhiều biến
// Sai: var[] data = new int[2];         // Không viết [] ở phía var

var a = new int[2];  // Hợp lệ: a có kiểu int[]
var b = new int[3];  // Hợp lệ: mỗi khai báo var có một biến riêng
~~~

Nếu cần field trong lớp, tham số phương thức hoặc kiểu trả về, phải ghi tên kiểu mảng tường minh:

~~~java
class ArrayHolder {
    private int[] data = {1, 2};       // Field: dùng int[]

    int[] values() {                   // Return type: dùng int[]
        return data.clone();
    }

    void update(int[] incoming) {      // Tham số: dùng int[]
        data = incoming.clone();
    }
}
~~~

Không đổi `int[]` ở ba vị trí đó thành `var`. `var` vốn được thiết kế cho **biến cục bộ**; vị trí khai báo vẫn có ý nghĩa quyết định. Điều này áp dụng hiện nay và không phụ thuộc vào việc phần tử mảng là primitive hay reference.

## 10. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Viết `var x = {1, 2};` | `{...}` không phải biểu thức có kiểu độc lập | `var x = new int[]{1, 2};` hoặc `int[] x = {1, 2};` |
| Viết `var x = {};` | Không có kiểu đích cho mảng rỗng | `var x = new int[]{};` hoặc `int[] x = {};` |
| Viết `var grid = {{1}, {2}};` | Thiếu kiểu ngoài và chiều mảng | `var grid = new int[][]{{1}, {2}};` |
| Viết `var x = new int[2]{1, 2};` | Trộn hai dạng tạo mảng không tương thích | `new int[2]` hoặc `new int[]{1, 2}` |
| Viết `var x = new int[];` | Không có kích thước hay initializer | `new int[0]` hoặc `new int[]{}` |
| Viết `var x = null;` | Không có kiểu đủ để suy luận | Ghi `int[] x = null;` khi thực sự cần |
| Tưởng `var` làm mảng thành `Object[]` | Nhầm suy luận kiểu với dynamic typing | Xem kiểu thực tế của biểu thức, ví dụ `int[]` |
| Tưởng `var alias = array;` sao chép mảng | `var` không sao chép đối tượng | Dùng `array.clone()` hoặc `Arrays.copyOf` nếu cần bản sao |
| Tưởng khai báo `var` tự tạo mảng | `var` chỉ xác định kiểu biến; `new`/phương thức mới tạo mảng | Tách riêng khai báo, biểu thức và thao tác tạo mảng |

Nên đọc kỹ **vị trí báo lỗi** từ `javac` và ghi lại đúng đoạn khai báo. Thông báo lỗi chữ nghĩa có thể khác nhau giữa các phiên bản trình biên dịch; hãy dựa vào các quy tắc ngữ pháp và kiểu ở trên để sửa.

## 11. Bài tập tự kiểm tra

**Bài 1.** Dòng nào hợp lệ?

~~~java
// Đánh giá từng dòng độc lập:
var a = {10, 20};
var b = new int[]{10, 20};
var c = new int[2];
int[] d = {10, 20};
~~~

**Đáp án:** `b`, `c`, `d` hợp lệ, đều là mảng `int[]`. `a` sai vì initializer rút gọn không cung cấp kiểu cho `var`.

**Bài 2.** `var names = new String[2];` tạo giá trị gì?

**Đáp án:** `names` có kiểu `String[]`, độ dài 2, cả hai phần tử khởi tạo mặc định thành `null`. Không có chuỗi rỗng `""` được tạo tự động.

**Bài 3.** `var grid = new int[][]{{1, 2}, {3}};` có hợp lệ không, và kiểu của `grid[1]` là gì?

**Đáp án:** Hợp lệ. `grid` có kiểu `int[][]`; `grid[1]` có kiểu `int[]` và chứa một phần tử có giá trị 3.

**Bài 4.** Thay `int[] values = {};` bằng `var values = {};` có hợp lệ không?

**Đáp án:** Không. Dù cả hai viết `{}`, câu thứ hai không có kiểu đích. Phải viết `var values = new int[]{};` hoặc giữ `int[] values = {};`.

**Bài 5.** Đoạn sau in ra gì?

~~~java
int[] original = {1, 2};
var alias = original;
alias[0] = 9;
System.out.println(original[0]);
~~~

**Đáp án:** In ra `9`, vì `alias` và `original` cùng tham chiếu tới một mảng. `var` không khiến Java sao chép các phần tử.

**Bài 6.** Vì sao `var empty = new String[]{};` hợp lệ dù không có phần tử để suy luận?

**Đáp án:** Bởi vì kiểu của **biểu thức tạo mảng** đã được ghi rõ là `String[]`. `var` suy luận từ kiểu của biểu thức, không suy luận số lượng hoặc lớp của các phần tử trong ngoặc nhọn.

## 12. Nguồn tài liệu chuẩn

- [JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): phạm vi `var` từ Java 10; loại trừ array initializer thuần `{...}` làm biểu thức khởi tạo để suy luận kiểu.
- [Java Language Specification — Arrays, `10.6 Array Initializers](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html#jls-10.6): cú pháp và ngữ cảnh kiểu của `{...}`.
- [Java Language Specification — Array Creation Expressions, `15.10](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.10): biểu thức `new T[n]`, `new T[]{...}`.
- [Java Language Specification — Local Variable Declarations, `14.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): quy tắc khai báo local với `var`.
- [dev.java — Local Variable Type Inference](https://dev.java/learn/language-basics/using-var/): hướng dẫn Java hiện hành về giới hạn và cách dùng `var`.
- [Java SE API — `java.util.Arrays`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html): tài liệu chuẩn cho `toString`, `deepToString` và `copyOf` được minh họa.

**Ghi nhớ:** Khi `var` đứng trước một biến cục bộ mảng, hãy dùng một **biểu thức có kiểu mảng** như `new int[]{...}`, `new int[n]` hoặc lời gọi phương thức trả về `int[]`. Dạng `{...}` trần chỉ dùng khi **ngữ cảnh khai báo đã nêu kiểu mảng**; nó không đủ làm initializer trực tiếp của `var`.