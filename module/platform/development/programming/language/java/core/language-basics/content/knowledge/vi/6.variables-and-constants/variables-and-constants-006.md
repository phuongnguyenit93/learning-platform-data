# Khai báo nhiều biến và những cách viết dễ gây nhầm — Java 17+

Java cho phép **khai báo nhiều biến trong cùng một câu lệnh** nếu chúng có kiểu phù hợp. Cách viết này ngắn nhưng dễ gây hiểu nhầm: dấu `=` chỉ khởi tạo **biến được gắn với nó**, dấu `[]` có thể chỉ áp dụng cho **một tên**, và `var` không hỗ trợ danh sách nhiều biến trong một khai báo.

Mục tiêu: đọc đúng từng biến được khai báo, dự đoán kiểu và giá trị của chúng, hiểu lỗi *definite assignment*, rồi chọn cách viết dễ bảo trì.

## 1. Đọc đúng từng tên và biểu thức khởi tạo

~~~java
int width = 3, height = 5; // Hai biến int, đều đã khởi tạo.
int x, y = 10;             // x CHƯA được gán; chỉ y bằng 10.
int start = 2, end = start + 4; // end bằng 6.
~~~

Hình thức chung là:

~~~text
kiểu tên1 [= biểu_thức1], tên2 [= biểu_thức2], ... ;
~~~

Mỗi tên có thể có hoặc không có biểu thức khởi tạo riêng. **Dấu phẩy không sao chép giá trị** từ biến này sang biến khác. Các initializer được đánh giá theo thứ tự khai báo từ trái sang phải khi câu lệnh được thực thi; một tên đã được khởi tạo trước đó có thể được dùng trong initializer phía sau.

| Câu lệnh | Hiểu đúng |
| --- | --- |
| `int a = 1, b = 2;` | `a = 1`, `b = 2` |
| `int a, b = 2;` | `a` chưa gán; chỉ `b = 2` |
| `int a = 2, b;` | `a = 2`; `b` chưa gán |
| `int a = 2, b = a + 3;` | `a = 2`; `b = 5` |
| `double x = 1.5, y = 2;` | Hai biến `double`; `y` được chuyển thành `2.0` |
| `final int a = 1, b = 2;` | Cả hai đều `final`; không thể gán lại |
| `int a = 1; double b = 2.0;` | Hai kiểu khác nhau, cần khai báo riêng |

### Khai báo khác với gán giá trị

Ở biến cục bộ:

~~~java
int a, b = 5;
// System.out.println(a); // Sai: a chưa được gán chắc chắn.
a = b + 1;
System.out.println(a); // 6
~~~

Java kiểm tra **definite assignment**: biến cục bộ phải được gán chắc chắn trước khi đọc. Đừng suy luận rằng `int a, b = 5;` sẽ gán `5` cho cả hai.

Nếu muốn gán cùng một giá trị, có thể viết:

~~~java
int a, b;
a = b = 5; // Gán cho b trước, rồi gán kết quả cho a.
~~~

Tuy nhiên, khi khởi tạo biến trong mã sản phẩm, `int a = 5, b = 5;` hoặc hai khai báo riêng thường dễ hiểu hơn một phép gán nối chuỗi.

## 2. Chương trình Java 17+ chạy được

Tạo tệp **`MultipleVariablesDemo.java`**:

~~~java
public class MultipleVariablesDemo {
    public static void main(String[] args) {
        int first = 2, second = first + 3;

        int later, ready = 7;
        later = 9;

        int[] left = {4, 5}, right = {6, 7};

        // Cú pháp hợp lệ nhưng dễ nhầm:
        int legacyArray[] = {8, 9}, scalar = 10;

        int x, y;
        x = y = 3;

        var inferred = "OK"; // Một biến trong một khai báo var.

        System.out.println("first=" + first + ", second=" + second);
        System.out.println("later=" + later + ", ready=" + ready);
        System.out.println("arrays=" + left.length + "," + right.length);
        System.out.println(
                "legacyArrayLength=" + legacyArray.length
                + ", scalar=" + scalar);
        System.out.println("chain=" + x + "," + y);
        System.out.println("inferred=" + inferred);

        for (int i = 0, j = 3; i < j; i++, j--) {
            System.out.println("pair=" + i + ":" + j);
        }
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa tệp. Sử dụng JDK 17 trở lên:

~~~bash
java -version
javac -version
javac -encoding UTF-8 MultipleVariablesDemo.java
java MultipleVariablesDemo
~~~

**Expected output:**

~~~text
first=2, second=5
later=9, ready=7
arrays=2,2
legacyArrayLength=2, scalar=10
chain=3,3
inferred=OK
pair=0:3
pair=1:2
~~~

Giải thích điểm quan trọng:

1. `second` đọc `first` sau khi `first` đã khởi tạo, nên nhận `5`.
2. `later` chỉ có giá trị sau câu lệnh `later = 9;`; `ready` nhận `7` ngay lúc khai báo.
3. `left` và `right` đều là mảng `int[]`, mỗi mảng dài 2.
4. `legacyArray` là mảng, nhưng `scalar` là **một `int` duy nhất**, dù chúng cùng đứng trong một câu lệnh khai báo.
5. `x = y = 3` đặt cả `x` và `y` bằng 3. Không nên hiểu đó là phép so sánh.
6. Trong vòng `for`, `i` và `j` có cùng kiểu `int`; hai biến được cập nhật sau mỗi lượt. Khi `i == 2` và `j == 1`, điều kiện `i < j` sai nên dừng.

## 3. Bẫy đặc biệt: dấu `[]` có thể chỉ áp dụng cho một tên

Hai cách viết sau **khác nhau**:

~~~java
int[] a = {1}, b = {2}; // a và b đều là int[].
int c[] = {3}, d = 4;   // c là int[], d là int.
~~~

Trong Java, dấu `[]` có thể viết gần **kiểu** hoặc ngay **sau tên biến**. Khi đứng sau tên, chúng chỉ gắn với biến đó. Thậm chí:

~~~java
int[] one = {1}, two[] = {{2, 3}};
~~~

Ở đây `one` có kiểu `int[]`, còn `two` có kiểu `int[][]`. Cú pháp hợp lệ nhưng không dễ quan sát kiểu nếu chỉ đọc phần đầu câu lệnh.

**Khuyến nghị:** viết ngoặc vuông cạnh kiểu và khai báo từng biến mảng riêng biệt:

~~~java
int[] numbers = {1, 2};
int[] others = {3, 4};
int[][] grid = {{1, 2}, {3, 4}};
~~~

Cách này giảm nguy cơ đọc nhầm chiều mảng, đặc biệt khi người khác chỉnh sửa mã.

## 4. `var` không khai báo nhiều biến cùng lúc

Từ Java 10 (vẫn áp dụng trên Java 17), `var` cho phép compiler suy luận **kiểu của một biến cục bộ** từ initializer:

~~~java
var count = 3;     // int
var title = "Java"; // String
~~~

Nhưng các cách viết sau **không hợp lệ**:

~~~java
// var a = 1, b = 2; // Sai: không cho nhiều declarator với var.
// var value;        // Sai: thiếu initializer để suy luận kiểu.
// var unknown = null; // Sai: không suy luận kiểu từ null đơn lẻ.
~~~

Nếu muốn nhiều biến cùng kiểu trong một câu lệnh, hãy viết kiểu tường minh:

~~~java
int a = 1, b = 2;
~~~

Nếu các biến có ý nghĩa khác nhau, ưu tiên tách:

~~~java
int retryCount = 1;
int maxRetries = 3;
~~~

`var` **không làm biến có kiểu động**: kiểu được compiler xác định ngay khi biên dịch. Đổi `count` thành chuỗi sau khi khai báo `var count = 3;` vẫn gây lỗi kiểu.

## 5. Các cách viết dễ gây lỗi

| Viết như sau | Vấn đề | Sửa hoặc giải thích |
| --- | --- | --- |
| `int a, b = 5; System.out.println(a);` | Lỗi biên dịch: `a` chưa được gán | Gán `a` trước khi đọc |
| `int a = 1, b = a + 1;` | **Hợp lệ**, `b = 2` | Thứ tự initializer từ trái sang phải |
| `int a = b + 1, b = 2;` | Lỗi: dùng `b` trước phần khai báo/khởi tạo phù hợp | Khai báo và gán `b` trước |
| `int a = 1, b = 2.5;` | Lỗi kiểu: `b` là `int` | Tách kiểu: `int a = 1; double b = 2.5;` |
| `int[] a, b;` | **Cả hai là mảng** | Dùng `int[]` cạnh kiểu |
| `int a[], b;` | `a` là mảng, `b` là số nguyên | Tránh ngoặc vuông sau tên |
| `var a = 1, b = 2;` | Lỗi: `var` không cho nhiều declarator | Tách hai khai báo |
| `int a = 1; int a = 2;` trong cùng phạm vi | Lỗi khai báo trùng tên | Dùng tên khác hoặc gán lại `a = 2;` |
| `for (int i = 0, j = 5; ... )` | **Hợp lệ** nếu dùng cùng kiểu | Cả `i` và `j` là `int` |

**Lưu ý về dấu phẩy:** trong phần *khởi tạo* của vòng `for`, bạn thường gặp nhiều biến cùng kiểu (`int i = 0, j = 5`). Trong phần **cập nhật** của `for`, `i++, j--` là một danh sách biểu thức cập nhật, **không phải khai báo biến**.

### Side effect làm một dòng ngắn trở nên khó đọc

~~~java
int x = 1, y = ++x; // x = 2, y = 2.
~~~

Cú pháp hợp lệ, nhưng `++x` thay đổi giá trị x ngay trong lúc khởi tạo y. Với logic phức tạp, nên tách ra:

~~~java
int x = 1;
x++;
int y = x;
~~~

Code dài thêm một chút nhưng dễ kiểm tra, đặt breakpoint và tránh sai ý định hơn.

## 6. Bài tập tự luyện

**Bài 1 — Dự đoán:** Với `int a = 3, b = a * 2, c;`, biến nào đã có giá trị ngay sau dòng khai báo? Có thể in `c` ngay không?

*Đáp án:* `a = 3`, `b = 6`; `c` chưa được gán nên chưa thể đọc.

**Bài 2 — Kiểu mảng:** Cho `int[] first = {1}, second[] = {{2}};`. Hai biến có kiểu gì?

*Đáp án:* `first` là `int[]`, `second` là `int[][]`.

**Bài 3 — Sửa `var`:** Viết lại `var width = 2, height = 3;` thành hai câu khai báo dùng `var` và một câu khai báo dùng kiểu tường minh.

*Đáp án:* `var width = 2; var height = 3;` hoặc `int width = 2, height = 3;`.

**Bài 4 — Vòng `for`:** Với `for (int i = 1, j = 4; i < j; i++, j--)`, có bao nhiêu lượt chạy thân?

*Đáp án:* Hai lượt: lúc `(i,j) = (1,4)` và `(2,3)`, rồi dừng khi `(3,2)`.

**Bài 5 — Ưu tiên tính rõ ràng:** Trong mã nghiệp vụ, nên chọn `int[] scores = ...; int[] bonuses = ...;` hay `int scores[], bonuses[];`?

*Gợi ý đáp án:* Cách đầu dễ đọc và giảm bẫy thay đổi kiểu từng biến. Cách thứ hai có thể hợp lệ nhưng khó bảo trì hơn.

## Checklist

- [ ] Biết `int a, b = 5;` chỉ gán `5` cho `b`.
- [ ] Phân biệt khai báo biến với câu lệnh gán và lỗi đọc local chưa khởi tạo.
- [ ] Hiểu các initializer được đánh giá theo thứ tự từ trái sang phải.
- [ ] Nhận diện `int[] a, b` khác `int a[], b`.
- [ ] Biết `var` không hỗ trợ nhiều declarator trong một khai báo.
- [ ] Đọc đúng nhiều biến trong vòng `for`.
- [ ] Ưu tiên những khai báo ngắn, rõ kiểu, ít side effect.

**Ghi nhớ:** Khai báo nhiều biến hợp lệ không đồng nghĩa **mọi biến đều đã được gán**, và cùng một đầu câu lệnh không luôn đồng nghĩa mọi tên có đúng cùng kiểu mảng. Khi mỗi biến mang ý nghĩa riêng, **tách khai báo thành từng dòng** thường là cách rõ ràng và an toàn nhất.
