# Ảnh hưởng của thứ tự phép `+` khi trộn số với chuỗi trong Java

> **Java core — language-basics / Ký tự và chuỗi**  
> **Yêu cầu:** JDK 17 trở lên, không cần thư viện bên ngoài.  
> **Mục tiêu:** Dự đoán chính xác kết quả khi `+` vừa dùng cộng số vừa dùng nối `String`; hiểu tính kết hợp trái, ưu tiên toán tử, thứ tự đánh giá và cách thêm ngoặc để tránh lỗi.

## 1. Cùng dấu `+` nhưng có hai ý nghĩa

Java dùng dấu `+` theo kiểu toán hạng:

- Nếu hai toán hạng thích hợp cho **phép cộng số**, `+` tính tổng số học (theo quy tắc nâng kiểu số của Java).
- Nếu **ít nhất một toán hạng là `String`**, `+` thực hiện **nối chuỗi**: toán hạng còn lại được chuyển thành biểu diễn văn bản để nối.

~~~java
int sum = 10 + 20;                  // 30
String joined = "10" + 20;          // "1020"
String output = "total=" + sum;     // "total=30"
~~~

Đây **không** phải “Java biến tất cả các số trong dòng thành String”. Mỗi phép `+` được phân tích theo các toán hạng của **chính phép đó**, có xét thứ tự nhóm biểu thức.

## 2. Tính kết hợp trái làm thay đổi kết quả

Các phép `+` cùng mức ưu tiên được nhóm **từ trái sang phải** (*left-associative*).

| Biểu thức | Cách nhóm | Kết quả |
| --- | --- | --- |
| `1 + 2 + "x"` | `(1 + 2) + "x"` | `"3x"` |
| `"x" + 1 + 2` | `("x" + 1) + 2` | `"x12"` |
| `1 + "2" + 3` | `(1 + "2") + 3` | `"123"` |
| `"sum=" + (1 + 2)` | Cộng trong ngoặc trước | `"sum=3"` |
| `"sum=" + 1 + 2` | Nối thành chuỗi ở phép `+` đầu tiên | `"sum=12"` |

Diễn giải `1 + 2 + "x"`: phép đầu tiên `1 + 2` là **cộng số** cho `3`, phép tiếp theo `3 + "x"` là **nối chuỗi** thành `"3x"`.

Diễn giải `"x" + 1 + 2`: ngay phép đầu đã có `String`, tạo `"x1"`; phép kế tiếp nối thêm `2` thành `"x12"`. Không có phép cộng số `1 + 2` ở biểu thức này.

**Quy tắc đọc nhanh:** Đi qua các phép `+` từ trái sang phải theo cách nhóm ngữ pháp; khi kết quả trung gian đã là `String`, các phép `+` nối tiếp với nó sẽ nối chuỗi, trừ khi một biểu thức con được nhóm riêng để tính số trước.

## 3. Dấu ngoặc và ưu tiên toán tử

Toán tử nhân `*` có **độ ưu tiên cao hơn** toán tử cộng/nối `+`. Dấu ngoặc `(...)` giúp chỉ định phép toán phải hoàn thành trước.

~~~java
System.out.println("v=" + 2 * 3 + 4);   // v=64
System.out.println("v=" + (2 * 3 + 4)); // v=10
System.out.println("v=" + 2 + 3 * 4);   // v=212
~~~

Giải thích:

- `"v=" + 2 * 3 + 4`: tính `2 * 3 = 6`; sau đó `"v=" + 6 = "v=6"`; tiếp tục nối `4` → `"v=64"`.
- `"v=" + (2 * 3 + 4)`: trong ngoặc tính `6 + 4 = 10` rồi nối → `"v=10"`.
- `"v=" + 2 + 3 * 4`: tính `3 * 4 = 12`; hai phép cộng/nối còn lại được nhóm từ trái sang phải → `"v=212"`.

Không đồng nhất **tính kết hợp (associativity)** với **thứ tự thực thi các toán hạng (evaluation order)**. Java đánh giá toán hạng của một phép toán từ **trái sang phải**, đồng thời vẫn tôn trọng cây biểu thức đã được xác định bởi ưu tiên và dấu ngoặc. Phần ví dụ runnable bên dưới minh họa bằng dấu vết in ra.

## 4. Chương trình Java 17+ chạy được

Tạo file **PlusOrderDemo.java**:

~~~java
public final class PlusOrderDemo {
    private static int traced(String name, int value) {
        System.out.println("evaluate=" + name);
        return value;
    }

    public static void main(String[] args) {
        int a = 2;
        int b = 3;

        System.out.println("numeric=" + (a + b));
        System.out.println("direct=" + a + b);
        System.out.println("left=" + (1 + 2 + "x"));
        System.out.println("right=" + ("x" + 1 + 2));
        System.out.println("middle=" + (1 + "2" + 3));

        System.out.println("precedence=" + ("v=" + 2 * 3 + 4));
        System.out.println("grouped=" + ("v=" + (2 * 3 + 4)));

        System.out.println("charMath=" + ('A' + 1));
        System.out.println("charText=" + ("A=" + 'A' + 1));

        String label = "sum=";
        label += a + b;
        System.out.println("compound=" + label);

        String nullable = null;
        System.out.println("nullable=" + nullable);

        String result = "S" + traced("first", 2)
                + traced("second", 3);
        System.out.println("traceResult=" + result);
    }
}
~~~

Chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 PlusOrderDemo.java
java PlusOrderDemo
~~~

**Expected output chính xác:**

~~~text
numeric=5
direct=23
left=3x
right=x12
middle=123
precedence=v=64
grouped=v=10
charMath=66
charText=A=A1
compound=sum=5
nullable=null
evaluate=first
evaluate=second
traceResult=S23
~~~

**Giải thích những dòng quan trọng:**

1. `"numeric=" + (a + b)` cộng số trong ngoặc thành 5, rồi nối chuỗi; `"direct=" + a + b` nối từng số thành `"direct=23"`.
2. `char` tham gia phép cộng số có thể được **nâng lên `int`**: `'A' + 1` là `66` vì mã của `'A'` bằng 65. Nhưng `"A=" + 'A' + 1` nối lần lượt, thành `"A=A1"`.
3. Với `label += a + b`, vế phải là biểu thức số `a + b` (giá trị 5); toán tử gán kết hợp nối vào chuỗi cũ, kết quả `"sum=5"`. So với `label = label + a + b`, hai số sẽ bị nối lần lượt, không cộng trước.
4. Nối tham chiếu `String` đang bằng `null` vào chuỗi tạo phần văn bản `"null"`, không tạo ra một `String` mới có giá trị `null`.
5. Hai lời gọi `traced` thực thi theo thứ tự `first` rồi `second`; sau đó kết quả `2`, `3` được nối vào `"S"` thành `"S23"`.

## 5. Một số tình huống dễ nhầm

| Mã/nhận định | Kết quả đúng |
| --- | --- |
| `System.out.println(5 + 6);` | In `11`, vì hai toán hạng là số |
| `System.out.println("5" + 6);` | In `56`, vì có `String` |
| `System.out.println(5 + 6 + "7");` | In `117` |
| `System.out.println("5" + (6 + 7));` | In `513` |
| `System.out.println('A' + 'B');` | In `131`: hai `char` được nâng thành số |
| `System.out.println("letters=" + 'A' + 'B');` | In `letters=AB`: nối chuỗi |
| `System.out.println("ratio=" + 7 / 2);` | In `ratio=3`: phép chia nguyên thực hiện trước khi nối |
| `System.out.println("ratio=" + (7.0 / 2));` | In `ratio=3.5` |

### Tràn số vẫn xảy ra trước khi nối chuỗi

~~~java
int side = 50_000;
System.out.println("area=" + side * side);          // area=-1794967296
System.out.println("area=" + ((long) side * side)); // area=2500000000
~~~

Vế phải `side * side` dùng `int` và có thể tràn **trước** lúc chuyển thành văn bản. Nối chuỗi không tự động giúp phép tính số học rộng hơn hoặc an toàn hơn; nếu phép tính có thể vượt `int`, cần chọn kiểu toán hạng thích hợp.

## 6. Cách viết tránh lỗi khi ghép số vào thông điệp

- **Có phép tính toán học muốn người đọc nhận ra?** Đặt nó trong ngoặc: `"total=" + (price * quantity)` hoặc `"sum=" + (a + b)`.
- **Muốn liệt kê nhiều số cạnh nhau?** Dùng dấu phân cách trong chuỗi: `"a=" + a + ", b=" + b`; nếu không, `"a=" + a + b` rất dễ tạo kết quả mơ hồ.
- **Không ghép biểu thức quá dài** chứa lẫn nhiều `+` toán học và `+` chuỗi. Đặt tổng vào biến số rõ ràng trước khi format:
  
  ~~~java
  int total = a + b;
  System.out.println("total=" + total);
  ~~~
- **Dùng `String.format` khi cần định dạng** nhiều giá trị hoặc số thực, thay vì dựa vào một chuỗi phép nối dài. Việc định dạng số làm việc độc lập với việc phép cộng số có đúng hay không.
- **Nhớ kiểu của biểu thức con:** dấu ngoặc không tự “ép kiểu thành số”; `("1" + "2")` vẫn là `"12"` vì hai toán hạng là chuỗi.
- **Không dựa vào tối ưu hóa compiler** để suy đoán thứ tự in/tác dụng phụ. Java giữ ngữ nghĩa đánh giá theo thứ tự đã quy định.

## 7. Bài tập nhanh

**Bài 1 — Đoán đầu ra.** Dự đoán bốn kết quả: `1 + 2 + "3"`, `"1" + 2 + 3`, `"1" + (2 + 3)`, `2 * 3 + "4"`. Giải thích tại từng phép `+` vì sao là cộng số hay nối chuỗi.

**Bài 2 — Sửa thông báo.** Với `int a = 10, b = 20;`, vì sao `System.out.println("Tổng=" + a + b);` in `Tổng=1020`? Sửa để in `Tổng=30` mà không thay đổi giá trị `a` hay `b`.

**Bài 3 — `char` và số.** Dự đoán kết quả `'A' + 2` và `"A" + 2`, phân biệt phép cộng mã ký tự và nối chuỗi.

**Bài 4 — Dấu vết.** Thay `"S" + traced("first", 2) + traced("second", 3)` bằng `traced("first", 2) + traced("second", 3) + "S"`. Hai dòng `evaluate=...` có đổi thứ tự không? Kết quả của phép cộng có thay đổi không?

**Bài 5 — Tình huống thực.** Viết thông báo tổng tiền theo số lượng và đơn giá sao cho phép nhân được thực hiện trước khi ghép chuỗi; nêu kiểu dữ liệu phù hợp nếu giá trị trung gian có thể vượt `int`.

### Ghi nhớ

**Dấu `+` là phép cộng số khi áp dụng trên toán hạng số, và là nối chuỗi khi có `String`.** Các dấu `+` cùng mức ưu tiên được nhóm **từ trái sang phải**; dấu ngoặc và phép toán ưu tiên cao hơn quyết định phép tính diễn ra trước khi nối. Khi muốn biểu thức số được tính riêng, viết `"label=" + (a + b)`, không viết `"label=" + a + b`.
