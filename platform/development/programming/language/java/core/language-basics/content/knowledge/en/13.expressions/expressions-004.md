# Dùng dấu ngoặc để làm rõ ý định — Java 17+

## 1. Vì sao cần dấu ngoặc trong biểu thức?

Trong Java, **dấu ngoặc tròn `(...)` dùng để phân nhóm một biểu thức con**, làm rõ thao tác nào được thực hiện chung trước khi kết hợp với các phần còn lại. Dấu ngoặc giúp người đọc nhận ra ý định của tác giả và đôi khi **thay đổi kết quả phép tính**.

~~~java
int a = 10;
int b = 3;
int c = 2;

System.out.println(a + b * c);     // 16
System.out.println(a + (b * c));   // 16
System.out.println((a + b) * c);   // 26
~~~

- `a + b * c`: phép nhân có mức ưu tiên cao hơn phép cộng.
- `a + (b * c)`: dấu ngoặc **làm rõ** đúng cách nhóm vốn có, không đổi kết quả.
- `(a + b) * c`: dấu ngoặc **thay đổi nhóm phép toán**, khiến cộng trước, nhân sau.

**Nguyên tắc:** hiểu thứ tự ưu tiên mặc định, rồi dùng dấu ngoặc để biểu đạt rõ ý định. Đừng thêm ngoặc ngẫu nhiên để chữa một kết quả sai mà chưa xác định nguyên nhân.

## 2. Dấu ngoặc nhóm biểu thức không phải “ép kiểu”

Hai cú pháp này khác nhau:

~~~java
double x = 7.9;
double grouped = (x);   // Nhóm biểu thức x: vẫn double
int converted = (int) x; // Cast: yêu cầu chuyển double sang int

System.out.println(grouped);   // 7.9
System.out.println(converted); // 7
~~~

- `(x)` là **biểu thức được đặt trong ngoặc**: kiểu và giá trị của `x` được giữ theo ngữ cảnh thông thường.
- `(int) x` là **cast expression**: `int` là tên kiểu, có tác dụng chuyển đổi và có thể làm mất phần thập phân.
- `method(a, b)`, `if (condition)`, `while (condition)` cũng dùng ngoặc theo **cú pháp lời gọi/điều khiển**, không nhất thiết là thao tác thay đổi ưu tiên.

Vì vậy cần nhìn vào **vị trí ngoặc và phần nằm trong ngoặc** trước khi giải thích.

## 3. Dùng kiến thức precedence vừa đủ để đặt ngoặc

Java ưu tiên truy cập/hậu tố và toán tử một ngôi trước nhân/chia, rồi cộng/trừ, so sánh, logic `&&`, `||`, điều kiện `?:` và phép gán. Các toán tử cùng mức còn có quy tắc kết hợp; chẳng hạn `*` và `/` nhóm từ trái sang phải:

~~~java
int x = 20, y = 5, z = 2;
System.out.println(x / y * z);   // 8: (20 / 5) * 2
System.out.println(x / (y * z)); // 2: 20 / 10
~~~

Khi công thức có nhiều nhóm điều kiện hay phép tính, đặt ngoặc theo **ý nghĩa** cần biểu đạt. Người đọc sẽ thấy rõ ý định mà không phải nhớ mọi mức ưu tiên. Dấu ngoặc thay đổi nhóm khi cần, nhưng không tự đảo thứ tự đánh giá toán hạng có tác dụng phụ.

## 4. Dùng ngoặc để tách công thức thành các ý nghĩa

Giả sử giá trị cần tính là **tổng giá và phí**, sau đó nhân số lượng:

~~~java
int unitPrice = 40;
int fee = 5;
int quantity = 3;

int total = (unitPrice + fee) * quantity;
System.out.println(total); // 135
~~~

Nếu bỏ ngoặc:

~~~java
int incorrect = unitPrice + fee * quantity;
System.out.println(incorrect); // 55
~~~

Công thức ban đầu `(40 + 5) * 3` khác `40 + (5 * 3)`. Ở đây ngoặc **thay đổi hành vi** chứ không chỉ trang trí.

Với biểu thức dài, bạn cũng có thể đặt tên cho kết quả trung gian:

~~~java
int priceWithFee = unitPrice + fee;
int explicitTotal = priceWithFee * quantity;
~~~

Cách tách biến thường phù hợp khi mỗi phép tính mang một ý nghĩa nghiệp vụ riêng; dấu ngoặc hữu ích khi biểu thức vẫn đủ ngắn.

## 5. Ngoặc không biến phép chia nguyên thành phép chia thực

Một bẫy thường gặp là phép chia nguyên:

~~~java
int a = 7;
int b = 2;

double wrong = (a / b);
double right = ((double) a) / b;

System.out.println(wrong); // 3.0
System.out.println(right); // 3.5
~~~

Ngoặc `(a / b)` **không thay đổi kiểu toán hạng**. Vì `a` và `b` đều là `int`, biểu thức chia có kiểu `int`, nhận giá trị 3; khi gán sang `double` mới thành 3.0.

Ở `((double) a) / b`, `a` được cast thành double **trước khi chia**, nên phép chia sử dụng kiểu `double` và cho 3.5.

Bảng so sánh:

| Biểu thức | Kiểu của phép chia | Giá trị cuối |
|---|---|---|
| `7 / 2` | `int` | `3` |
| `(7 / 2)` | `int` | `3` |
| `(double) (7 / 2)` | `int`, sau đó cast `double` | `3.0` |
| `((double) 7) / 2` | `double` | `3.5` |
| `7 / 2.0` | `double` | `3.5` |

**Bài học:** dùng ngoặc cho **thứ tự nhóm**, dùng cast/literal đúng kiểu cho **chọn phép toán số học**.

## 6. Nối chuỗi: dấu ngoặc phân biệt cộng số và ghép văn bản

Trong Java, `+` còn nối chuỗi khi có `String`. Phép `+` kết hợp trái:

~~~java
int a = 10;
int b = 3;

System.out.println("sum=" + a + b);    // sum=103
System.out.println("sum=" + (a + b));  // sum=13
System.out.println((a + b) + " items"); // 13 items
~~~

Ở dòng đầu, Java nhóm như `("sum=" + a) + b`: sau khi nối String với 10, phần tiếp theo lại tiếp tục nối với 3.

Ở dòng hai, `(a + b)` thực hiện phép cộng số trước. Trong log, thông báo lỗi hoặc báo cáo, dấu ngoặc này giúp tránh các giá trị **trông hợp lệ nhưng thực tế bị ghép sai**.

**Một quy ước dễ đọc:**

~~~java
String summary = "total=" + (a + b);
~~~

Nếu chuỗi đầu ra chứa nhiều phép tính, nên đặt các phép tính trong ngoặc hoặc tính chúng vào biến có tên trước khi ghép.

## 7. Điều kiện phức hợp: ngoặc biểu thị quy tắc truy cập

Giả sử một thao tác được phép khi **tài khoản đang hoạt động** và người dùng **là quản trị viên hoặc có token hợp lệ**:

~~~java
boolean isAdmin = true;
boolean hasToken = false;
boolean active = false;

boolean correct = (isAdmin || hasToken) && active;
System.out.println(correct); // false
~~~

Nếu viết:

~~~java
boolean misleading = isAdmin || hasToken && active;
System.out.println(misleading); // true
~~~

Do `&&` ưu tiên cao hơn `||`, cách viết không có ngoặc được nhóm thành `isAdmin || (hasToken && active)`: quản trị viên sẽ vượt qua điều kiện `active`.

Dấu ngoặc ở `(isAdmin || hasToken) && active` **định nghĩa chính xác ý định**: điều kiện hoạt động bắt buộc đối với cả hai cách được cấp quyền.

| isAdmin | hasToken | active | `isAdmin || (hasToken && active)` | `(isAdmin || hasToken) && active` |
|---|---|---|---|---|
| true | false | false | true | false |
| false | true | true | true | true |
| false | true | false | false | false |
| true | false | true | true | true |

**Quy tắc review:** với biểu thức pha trộn `&&` và `||`, thêm ngoặc xung quanh từng nhóm điều kiện theo ý nghĩa nghiệp vụ, kể cả khi bạn nhớ chính xác mức ưu tiên.

## 8. Dùng ngoặc để chỉ rõ điều kiện bảo vệ

~~~java
int divisor = 0;
boolean safe = (divisor != 0) && (10 / divisor > 1); // false, không chia 0
String name = null;
boolean hasName = (name != null) && (!name.isBlank()); // false, không NPE
~~~

Ngoặc cho biết vế phải phụ thuộc điều kiện guard ở vế trái; **toán tử `&&`** mới là cơ chế bỏ qua vế phải khi vế trái false. Nếu thay bằng boolean `&`, cả hai phía vẫn được đánh giá khi bình thường, dù thêm bao nhiêu ngoặc. Với `||`, vế phải bị bỏ qua khi vế trái true.

## 9. Khoảng giá trị: đừng viết so sánh dây chuyền kiểu toán học

Toán học thường viết \(1 \le x \le 10\), nhưng Java không cho diễn đạt tương đương bằng:

~~~java
// 1 <= x <= 10   // Lỗi biên dịch
~~~

Vì `1 <= x` tạo kết quả `boolean`, không thể tiếp tục so `boolean <= 10`.

Cách diễn đạt rõ ràng là:

~~~java
int x = 5;
boolean inRange = (x >= 1) && (x <= 10);

System.out.println(inRange); // true
~~~

Ở đây ngoặc tách **hai điều kiện có kiểu boolean** và `&&` kết hợp chúng. Đây là một kiểu phân nhóm làm code gần với ngôn ngữ tự nhiên hơn: “x từ 1 trở lên” **và** “x không vượt 10”.

## 10. Biểu thức `?:`: phân nhóm nhánh có chủ đích

Toán tử điều kiện ba ngôi `condition ? first : second` chọn **một trong hai nhánh** theo điều kiện boolean.

~~~java
int score = 82;
String grade = (score >= 90) ? "A"
        : ((score >= 70) ? "B" : "C");

System.out.println(grade); // B
~~~

Dấu ngoặc làm rõ cấu trúc “nếu đạt 90 thì A, nếu không nhưng đạt 70 thì B, nếu không thì C”.

Với nhiều cấp phân nhánh, một khối `if / else if / else` có thể dễ bảo trì hơn:

~~~java
String grade;
if (score >= 90) {
    grade = "A";
} else if (score >= 70) {
    grade = "B";
} else {
    grade = "C";
}
~~~

**Không cần ép mọi ý định vào một biểu thức `?:` lớn.** Chọn ngoặc, biến trung gian hoặc câu lệnh điều khiển tùy mức độ rõ ràng.

## 11. Ngoặc không loại bỏ tác dụng phụ

~~~java
int n = 1;
int value = (n++) + 2;
System.out.println(value); // 3: dùng giá trị cũ
System.out.println(n);     // 2: biến đã tăng
~~~

Dấu ngoặc cho thấy `n++` là biểu thức con nhưng không khiến nó trả giá trị sau tăng. Tương tự, `(x = 4)` vẫn thực hiện gán. Khi một công thức có nhiều cập nhật trạng thái hoặc lời gọi method có side effect, hãy tách thành bước rõ ràng để dễ debug và tránh đổi hành vi trong lúc refactor.

## 12. Lưu ý về thứ tự đánh giá trong Java

Java xác định thứ tự đánh giá toán hạng cho nhiều cấu trúc, ví dụ các toán hạng của toán tử nhị phân được đánh giá theo thứ tự **từ trái sang phải**. Nhưng dấu ngoặc phân nhóm quyết định **phép toán nào kết hợp với phép toán nào**, và có thể ảnh hưởng tới giá trị cuối hoặc cấu trúc đánh giá.

Ví dụ không có tác dụng phụ:

~~~java
int a = 2, b = 3, c = 4;
System.out.println(a + b * c);   // 14
System.out.println((a + b) * c); // 20
~~~

Đừng xem “thứ tự ưu tiên” như lời cho phép compiler **tự ý đổi thứ tự mọi lời gọi có tác dụng phụ** theo cách làm chương trình đổi nghĩa. Và cũng đừng dùng dấu ngoặc để che các đoạn như `x++ + ++x`; nên tách thành nhiều câu lệnh.

**Khuyến nghị:** một biểu thức nên ưu tiên **một ý định rõ ràng**, nhất là khi có gán, tăng/giảm, thay đổi trạng thái hay method tạo side effect.

## 13. Ngoặc không tự khắc phục tràn số nguyên

~~~java
long wrong = (2_000_000_000 + 2_000_000_000); // -294967296
long right = ((long) 2_000_000_000) + 2_000_000_000; // 4000000000
~~~

Dòng đầu cộng hai `int` nên tràn trước khi gán vào `long`. Dòng sau chuyển một toán hạng sang `long` **trước phép cộng**. Ngoặc chỉ nhóm, cast thay đổi kiểu; cần `Math.addExact` hoặc kiểm tra giới hạn nếu nghiệp vụ phải phát hiện overflow.

## 14. Ngoặc có thể thay đổi kết quả dấu phẩy động

Trong số học số thực nhị phân, một số phép toán không có tính kết hợp toán học tuyệt đối do **làm tròn sau từng bước**:

~~~java
double left = (1.0e16 + -1.0e16) + 1.0;
double right = 1.0e16 + (-1.0e16 + 1.0);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
~~~

Dòng đầu: `1.0e16 + -1.0e16` được 0.0, sau đó cộng 1.0. Dòng sau: `-1.0e16 + 1.0` được làm tròn thành `-1.0e16` vì 1 quá nhỏ so với độ lớn ấy; cộng với `1.0e16` được 0.0.

**Vì vậy không nên bỏ/di chuyển ngoặc tùy tiện trong biểu thức `float`/`double` với lý do “cộng có tính kết hợp”.** Việc đổi nhóm có thể đổi kết quả làm tròn ngay cả khi không có exception.

Nếu cần decimal chính xác, cần xem xét mô hình dữ liệu/thuật toán phù hợp như `BigDecimal`; thêm ngoặc **không tự biến `double` thành số thập phân chính xác**.

## 15. Các loại dấu ngoặc tròn cần phân biệt

| Cú pháp | Vai trò |
|---|---|
| `(a + b) * c` | Phân nhóm biểu thức, thay đổi thứ tự kết hợp |
| `a + (b * c)` | Phân nhóm để thể hiện thứ tự ưu tiên vốn có |
| `(double) a / b` | **Cast**, ảnh hưởng kiểu phép chia |
| `if (ready)` | Cú pháp điều kiện của câu lệnh `if` |
| `while (ready)` | Cú pháp điều kiện của câu lệnh `while` |
| `Math.max(a, b)` | Ngoặc bao danh sách đối số gọi method |
| `new Box(7)` | Ngoặc truyền đối số cho constructor |
| `(condition) ? x : y` | Phân nhóm điều kiện, tăng dễ đọc |

Các dấu ngoặc này có hình dạng tương tự nhưng **không có cùng ngữ nghĩa**. Khi đọc code, hãy xác định cấu trúc Java đang được sử dụng trước khi suy luận kết quả.

## 16. Chương trình Java 17 hoàn chỉnh

Tạo đúng tệp **`ParenthesesIntentDemo.java`**:

~~~java
public final class ParenthesesIntentDemo {
    private ParenthesesIntentDemo() {}

    public static void main(String[] args) {
        int a = 10;
        int b = 3;
        int c = 2;

        System.out.println("default arithmetic=" + (a + b * c));
        System.out.println("explicit precedence=" + (a + (b * c)));
        System.out.println("grouped arithmetic=" + ((a + b) * c));
        System.out.println("grouped division=" + ((a + b) / c));

        int numerator = 7;
        int denominator = 2;
        System.out.println("integer division=" + (numerator / denominator));
        System.out.println("late cast=" + ((double) (numerator / denominator)));
        System.out.println("early cast=" + (((double) numerator) / denominator));

        System.out.println("concat plain=" + ("x=" + a + b));
        System.out.println("concat grouped=" + ("x=" + (a + b)));
        System.out.println("numbers first=" + ((a + b) + " units"));

        boolean isAdmin = true;
        boolean hasToken = false;
        boolean active = false;
        boolean defaultAccess = isAdmin || hasToken && active;
        boolean groupedAccess = (isAdmin || hasToken) && active;
        System.out.println("boolean default=" + defaultAccess);
        System.out.println("boolean grouped=" + groupedAccess);

        int divisor = 0;
        boolean safeDivision = (divisor != 0) && (10 / divisor > 1);
        System.out.println("safe division=" + safeDivision);

        String name = null;
        boolean validName = (name != null) && (!name.isBlank());
        System.out.println("safe text=" + validName);

        int number = 5;
        boolean inRange = (number >= 1) && (number <= 10);
        System.out.println("range=" + inRange);

        int score = 82;
        String grade = (score >= 90) ? "A"
                : ((score >= 70) ? "B" : "C");
        System.out.println("grade=" + grade);

        int n = 1;
        int postfixValue = (n++) + 2;
        System.out.println("postfix result=" + postfixValue);
        System.out.println("postfix after=" + n);

        int updated = 0;
        int assignmentValue = (updated = 4) + 2;
        System.out.println("assignment target=" + updated);
        System.out.println("assignment result=" + assignmentValue);

        long overflowFirst = (2_000_000_000 + 2_000_000_000);
        long safeLong = ((long) 2_000_000_000) + 2_000_000_000;
        System.out.println("overflow before long=" + overflowFirst);
        System.out.println("long arithmetic=" + safeLong);

        double left = (1.0e16 + -1.0e16) + 1.0;
        double right = 1.0e16 + (-1.0e16 + 1.0);
        System.out.println("floating left=" + left);
        System.out.println("floating right=" + right);
    }
}
~~~

**Yêu cầu:** JDK 17 hoặc mới hơn. Mở terminal ở thư mục chứa `ParenthesesIntentDemo.java`; không cần Maven, Gradle hoặc thư viện bên ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ParenthesesIntentDemo.java
java -cp . ParenthesesIntentDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ParenthesesIntentDemo.java
java -cp . ParenthesesIntentDemo
~~~

**Exact expected output:**

~~~text
default arithmetic=16
explicit precedence=16
grouped arithmetic=26
grouped division=6
integer division=3
late cast=3.0
early cast=3.5
concat plain=x=103
concat grouped=x=13
numbers first=13 units
boolean default=true
boolean grouped=false
safe division=false
safe text=false
range=true
grade=B
postfix result=3
postfix after=2
assignment target=4
assignment result=6
overflow before long=-294967296
long arithmetic=4000000000
floating left=1.0
floating right=0.0
~~~

**Giải thích các dòng quan trọng:**

- `default arithmetic` và `explicit precedence` đều 16 vì phép nhân vốn ưu tiên cao hơn cộng.
- `grouped arithmetic` ra 26 vì nhóm phép cộng trước; `grouped division` ra 6 vì `(10+3)/2` là chia nguyên.
- `late cast` vẫn 3.0 vì phép chia int đã xảy ra; `early cast` ra 3.5 khi chuyển toán hạng trước.
- `concat plain` ra `x=103`, nhưng `concat grouped` ra `x=13` vì phép cộng số được nhóm.
- `boolean default=true` có thể là logic sai nếu mọi truy cập đều cần `active`; `boolean grouped=false` thể hiện đúng điều kiện bắt buộc đó.
- `safe division` và `safe text` không ném exception nhờ short-circuit.
- `postfix result` là 3 vì `n++` đóng góp giá trị cũ 1; `assignment target` và `assignment result` minh họa phép gán có giá trị.
- `overflow before long` chứng minh ngoặc không chữa overflow; `long arithmetic` dùng cast trước phép cộng.
- Hai dòng `floating` cho thấy đổi cách nhóm trong floating-point có thể đổi kết quả làm tròn.

## 17. Khi nào nên thêm ngoặc?

Nên thêm ngoặc khi:

- Pha trộn **`&&` và `||`** để minh họa quy tắc nghiệp vụ.
- Ghép **String với một phép tính** cần cộng/trừ/nhân/chia trước.
- Một công thức có **nhiều nhóm có ý nghĩa riêng**, ví dụ `(unitPrice + fee) * quantity`.
- Sử dụng **`?:` lồng nhau** và vẫn muốn giữ biểu thức ngắn, dễ kiểm tra.
- Muốn giữ rõ cách nhóm của các phép toán floating-point nhạy với làm tròn.
- Code review cho thấy người đọc dễ nhầm mức ưu tiên hoặc tính kết hợp.

Không nên thêm ngoặc tới mức che mất cấu trúc logic. Nếu biểu thức vẫn quá dài, **tách biến trung gian có tên tốt** hoặc dùng `if/else` để trình bày rõ ràng.

### Checklist review nhanh

1. Đọc từng biểu thức con và xác định kiểu dữ liệu.
2. Xác định ưu tiên và tính kết hợp mặc định.
3. Đặt ngoặc quanh các nhóm mang **ý nghĩa nghiệp vụ**.
4. Kiểm tra ngoặc có **thay đổi hành vi** hay chỉ giúp dễ đọc.
5. Kiểm tra `int` division/overflow, String concatenation, `&&`/`||`, tác dụng phụ và nullable.
6. Chạy chương trình với giá trị ranh giới và so expected output.

## 18. Các lỗi và ngộ nhận phổ biến

| Cách viết hoặc giả định | Vấn đề | Hướng xử lý |
|---|---|---|
| `a + b * c` khi muốn cộng trước | Nhân có ưu tiên cao hơn | `(a + b) * c` |
| `double x = (7 / 2);` khi muốn 3.5 | Ngoặc không đổi kiểu int của phép chia | `((double) 7) / 2` |
| `"sum=" + a + b` khi muốn cộng số | String concatenation kết hợp trái | `"sum=" + (a + b)` |
| `admin || token && active` khi muốn active bắt buộc | `&&` được nhóm trước `||` | `(admin || token) && active` |
| `(x >= 1) & (x <= 10)` để short-circuit | `&` trên boolean đánh giá cả hai bên | Dùng `&&` khi cần short-circuit |
| `1 <= x <= 10` | So sánh đầu tạo boolean, không so được với int | `(x >= 1) && (x <= 10)` |
| `(int)(7.9)` được nghĩ là chỉ nhóm | `(int)` là cast | Phân biệt cast và grouping |
| `long x = (intA + intB)` để tránh tràn | Cộng int có thể tràn trước | Chuyển một toán hạng sang long trước |
| Đổi nhóm `double` vì nghĩ cộng luôn kết hợp | Làm tròn sau từng bước có thể khác | Giữ grouping có chủ đích, kiểm thử |
| `(x++)` được nghĩ trả giá trị sau tăng | Postfix cho giá trị cũ | Dùng biến trung gian hoặc `++x` đúng ý |
| Ngoặc giúp tránh `NullPointerException` | Chỉ ngoặc không làm phép truy cập an toàn | Dùng guard và short-circuit |
| Lồng nhiều `?:` mà không làm rõ nhánh | Khó đọc, dễ hiểu nhầm | Ngoặc rõ hoặc chuyển sang `if/else` |

**Đừng nhầm compile success với đúng nghiệp vụ.** Một biểu thức có thể đúng cú pháp và đúng kiểu nhưng tính sai do cách nhóm.

## 19. Bài tập có đáp án

### Bài A — thay đổi kết quả phép toán

~~~java
int a = 8;
int b = 4;
int c = 2;
System.out.println(a - b / c);
System.out.println((a - b) / c);
~~~

**Đáp án:**

~~~text
6
2
~~~

Dòng đầu `8 - (4 / 2)` ra 6; dòng hai `(8 - 4) / 2` ra 2.

### Bài B — phép chia và kiểu số

~~~java
int a = 5;
int b = 2;
System.out.println((double) (a / b));
System.out.println(((double) a) / b);
~~~

**Đáp án:**

~~~text
2.0
2.5
~~~

Phép cast sau chia nguyên không khôi phục phần lẻ đã mất.

### Bài C — nối String

~~~java
System.out.println("n=" + 2 + 3);
System.out.println("n=" + (2 + 3));
~~~

**Đáp án:**

~~~text
n=23
n=5
~~~

### Bài D — điều kiện nghiệp vụ

Giả sử mọi người dùng phải `active` và đồng thời (`admin` hoặc có `token`). Hãy viết biểu thức đúng.

**Đáp án:**

~~~java
boolean allowed = (admin || token) && active;
~~~

Nếu dùng `admin || token && active`, quản trị viên có thể vượt qua điều kiện `active`.

### Bài E — giới hạn giá trị

Viết điều kiện `age` nằm trong khoảng 18 đến 65 (bao gồm hai biên).

**Đáp án:**

~~~java
boolean validAge = (age >= 18) && (age <= 65);
~~~

### Bài F — dấu ngoặc có chống overflow không?

~~~java
long n = (2_000_000_000 + 2_000_000_000);
System.out.println(n);
~~~

**Đáp án:** `-294967296` vì cộng int đã tràn. Muốn tính đúng 4 tỷ:

~~~java
long n = ((long) 2_000_000_000) + 2_000_000_000;
System.out.println(n); // 4000000000
~~~

### Bài G — khi nào thêm ngoặc không đổi kết quả?

~~~java
int a = 2, b = 3, c = 4;
System.out.println(a + b * c);
System.out.println(a + (b * c));
~~~

**Đáp án:** cả hai in `14`. Ngoặc ở dòng hai chỉ trình bày rõ nhóm phép nhân theo ưu tiên vốn có.

## 20. Tổng kết

- [ ] Hiểu dấu ngoặc dùng để nhóm biểu thức và diễn đạt ý định.
- [ ] Phân biệt ngoặc **làm rõ thứ tự vốn có** với ngoặc **thay đổi cách nhóm**.
- [ ] Biết thứ tự ưu tiên và tính kết hợp của các toán tử cơ bản.
- [ ] Không nhầm ngoặc nhóm với cast hoặc cú pháp method/`if`.
- [ ] Dùng ngoặc hợp lý trong công thức, phép chia và nối String.
- [ ] Phân nhóm `&&`/`||` dựa trên quy tắc nghiệp vụ, không chỉ dựa vào nhớ precedence.
- [ ] Hiểu short-circuit là thuộc tính toán tử, không do ngoặc tự tạo.
- [ ] Biết viết `(x >= min) && (x <= max)` để kiểm tra khoảng.
- [ ] Biết khi nào tách `?:` phức tạp thành `if/else`.
- [ ] Không tin rằng ngoặc tự sửa overflow, null hoặc sai kiểu dữ liệu.
- [ ] Nhận ra đổi nhóm phép toán floating-point có thể đổi kết quả.
- [ ] Hạn chế các tác dụng phụ ẩn trong biểu thức dài.
- [ ] Chạy được `ParenthesesIntentDemo.java` bằng Java 17+ và kiểm tra exact expected output.

**Kết luận:** Dấu ngoặc giúp lập trình viên nói rõ **phần nào của biểu thức thuộc cùng một ý nghĩa**. Dùng ngoặc vừa đủ để người đọc không phải đoán precedence, đặc biệt trong điều kiện logic và phép nối String; đồng thời luôn kiểm tra kiểu toán hạng, short-circuit, overflow và tác dụng phụ vì dấu ngoặc **không tự giải quyết** những vấn đề đó.