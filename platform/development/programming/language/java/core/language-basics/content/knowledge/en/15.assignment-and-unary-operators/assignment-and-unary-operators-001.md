# Phép gán `=` và giá trị của biểu thức gán — Java 17+

## 1. Mục tiêu và khái niệm

Trong Java, toán tử `=` dùng để **gán một giá trị cho một biến** (*assignment*). Quan trọng hơn: **bản thân phép gán cũng là một biểu thức có kiểu và có giá trị** nếu được đánh giá thành công.

~~~java
int count = 1;
int result = (count = 5) + 2;

System.out.println(count);  // 5
System.out.println(result); // 7
~~~

Diễn biến:

1. `count = 5` thay giá trị của biến `count` thành `5`.
2. Biểu thức gán `(count = 5)` có **kiểu `int`** và **giá trị `5`**.
3. `5 + 2` bằng `7`, gán vào `result`.

Từ đây, cần tách rõ **hai hiệu ứng** của phép gán:

- **Cập nhật nơi lưu giá trị** (*side effect*): thay giá trị của biến bên trái.
- **Tạo giá trị biểu thức**: biểu thức `a = b` tự nó cho một giá trị có thể dùng trong biểu thức bao ngoài.

Đây là ngữ nghĩa **kiểu tĩnh** của Java 17+, không phải biến động kiểu hay cú pháp đặc biệt chỉ dành cho ví dụ.

## 2. `=` khác `==` như thế nào?

| Toán tử | Mục đích | Ví dụ | Kết quả |
|---|---|---|---|
| `=` | **Gán** giá trị vào biến | `x = 10` | Cập nhật `x`; biểu thức gán có giá trị 10 |
| `==` | **So sánh bằng** | `x == 10` | Biểu thức có kiểu `boolean` |
| `!=` | **So sánh khác** | `x != 10` | Biểu thức có kiểu `boolean` |

Ví dụ:

~~~java
int x = 10;

System.out.println(x == 10); // true
System.out.println(x != 10); // false

x = 20;
System.out.println(x);       // 20
~~~

**Bẫy thường gặp:**

~~~java
boolean allowed = false;

if (allowed = true) { // Hợp lệ nhưng là PHÉP GÁN, không phải so sánh
    System.out.println("entered");
}
~~~

Dòng `if` trên đặt `allowed = true`; biểu thức gán trả `true`, nên nhánh được thực hiện. Đây là **lỗi logic dễ lọt qua compiler** vì cả kiểu và cú pháp đều hợp lệ.

Nếu mục đích là kiểm tra, viết `if (allowed)` hoặc `if (allowed == true)` (cách đầu thường gọn hơn). Nếu muốn kiểm tra `false`, dùng `if (!allowed)`.

## 3. Các thành phần của phép gán đơn giản

Cú pháp cơ bản:

~~~java
variable = expression
~~~

- **Vế trái** (*left-hand side*) phải biểu thị một **biến có thể gán**, chẳng hạn biến cục bộ, field hoặc phần tử mảng.
- **Vế phải** (*right-hand side*) được đánh giá để lấy giá trị phù hợp với kiểu biến bên trái.
- Khi hoàn tất bình thường, biến bên trái nhận giá trị được gán.

Ví dụ:

~~~java
int local = 0;
local = 12; // Biến cục bộ

int[] data = {1, 2};
data[1] = 9; // Phần tử mảng

Box box = new Box();
box.value = 4; // Field của object (class Box định nghĩa ở ví dụ độc lập bên dưới)
~~~

Không phải mọi biểu thức có giá trị đều có thể đứng bên trái `=`:

~~~java
// 5 = local;                // SAI: literal không phải biến
// (local + 1) = 10;         // SAI: kết quả phép cộng không phải biến
// Math.abs(local) = 10;     // SAI: kết quả gọi method không phải biến
~~~

**`=` không giống dấu bằng toán học đối xứng.** `x = y` và `y = x` là **hai thao tác khác nhau**: nơi được cập nhật là biến ở vế trái.

## 4. Giá trị và kiểu của biểu thức gán

Kiểu của `x = expression` liên quan tới **kiểu của biến bên trái** theo quy tắc ngôn ngữ (có các chi tiết *capture conversion* trong trường hợp generic). Giá trị biểu thức là **giá trị của biến sau khi gán**, không phải một kiểu mới được suy ra tùy tiện.

~~~java
int n = 0;
long wider = (n = 7); // n=7; giá trị int 7 được widening thành long

System.out.println(n);     // 7
System.out.println(wider); // 7
~~~

Ở đây `(n = 7)` có kiểu `int`. Phép gán ngoài `long wider = ...` tiếp tục chuyển rộng từ `int` sang `long`.

Với số nhỏ:

~~~java
byte small = 0;
int combined = (small = 42) + 1;

System.out.println(small);    // 42
System.out.println(combined); // 43
~~~

`small = 42` có kiểu `byte` và giá trị 42; khi cộng 1, Java áp dụng *binary numeric promotion*, nên `(small = 42) + 1` có kiểu `int` và giá trị 43.

**Đừng suy rằng mọi phép gán đều trả về một biến tham chiếu mới hoặc một bản sao object.** Biểu thức cho **giá trị** (đối với tham chiếu là giá trị tham chiếu) và có cập nhật ở nơi được gán; đó là hai khía cạnh khác nhau.

## 5. Chuyển đổi kiểu khi gán: hợp lệ và không hợp lệ

Java kiểm tra kiểu tĩnh của vế phải theo **assignment conversion**. Một vài trường hợp thường gặp:

| Mẫu code | Kết quả | Giải thích |
|---|---|---|
| `long a = 7;` | Hợp lệ | `int` sang `long` (widening) |
| `double d = 7;` | Hợp lệ | `int` sang `double` |
| `byte b = 42;` | Hợp lệ | Literal hằng `int` trong miền byte được phép thu hẹp khi gán |
| `byte b = 128;` | Lỗi compile | Hằng 128 ngoài miền byte |
| `int n = 3.5;` | Lỗi compile | `double` không tự thu hẹp thành `int` |
| `int n = (int) 3.5;` | Hợp lệ | Cast tường minh, giá trị 3 |
| `Integer boxed = 7;` | Hợp lệ | Autoboxing `int` thành `Integer` |
| `Long boxed = 7;` | Lỗi compile | Không tự kết hợp `int → long → Long` trong phép gán này |
| `Long boxed = 7L;` | Hợp lệ | Boxing `long` thành `Long` |

Một đặc điểm quan trọng: **constant expression narrowing** trong phép gán:

~~~java
byte small = 100;  // Hằng int 100 nằm trong miền byte
int variable = 100;
// byte other = variable; // Lỗi compile: biến int không phải hằng được phép thu hẹp
byte other = (byte) variable; // Hợp lệ về cú pháp; cần tự kiểm tra miền
~~~

Nếu dùng cast sai miền, giá trị có thể bị mất hoặc tràn. Phép gán biên dịch được **không bảo đảm** dữ liệu thỏa yêu cầu nghiệp vụ.

## 6. Phép gán liên tiếp: hệ quả của giá trị biểu thức gán

Vì `(b = 9)` vừa cập nhật `b` vừa cho giá trị `9`, Java cho phép dùng nó làm vế phải của một phép gán khác:

~~~java
int a, b, c;
a = b = c = 9; // a, b, c đều bằng 9
~~~

Dấu `=` **kết hợp từ phải sang trái**: `a = (b = (c = 9))`. Điều này nói về cách **nhóm biểu thức**, không nói rằng mọi toán hạng trong Java đều chạy từ phải sang trái. Mỗi phép gán vẫn phải qua kiểm tra kiểu riêng; chẳng hạn `long wide; int narrow; wide = narrow = 8;` hợp lệ, còn phép gán kết quả `long` về `int` không tự hợp lệ.

Để hiểu đầy đủ khi nào nên tránh gán liên tiếp, đặc biệt với chỉ số mảng, lời gọi hàm và nhiều biến tham chiếu, xem bài **“Gán liên tiếp và lý do nên hạn chế”**. Ở bài này, điều cần giữ lại là **giá trị của một phép gán có thể tiếp tục làm đầu vào cho phép gán khác**.

## 7. Assignment expression được dùng ở những đâu?

Một phép gán có thể làm **câu lệnh biểu thức** (*statement expression*) hoặc là một phần của biểu thức lớn hơn:

~~~java
int x = 1;

x = 5;                 // Câu lệnh gán
int y = (x = 6) + 2;   // Gán dùng như biểu thức con
boolean changed = (x = 7) > 5; // Kết quả x=7 được đem so

System.out.println(x);       // 7
System.out.println(y);       // 8
System.out.println(changed); // true
~~~

Ngoài ra, với biến boolean:

~~~java
boolean ready = false;
boolean copied = (ready = true);

System.out.println(ready);  // true
System.out.println(copied); // true
~~~

Tuy nhiên, **được phép dùng không đồng nghĩa nên lạm dụng**. Code business thường sáng sủa hơn khi tách:

~~~java
x = 7;
boolean changed = x > 5;
~~~

Điều này đặc biệt quan trọng nếu vế phải chứa method có tác dụng phụ hoặc phép tính có thể ném ngoại lệ.

## 8. Biểu thức gán và biểu thức điều kiện

Ví dụ biểu thức điều kiện:

~~~java
int count = 0;
boolean valid = true;

int selected = valid ? (count = 10) : (count = -1);

System.out.println(selected); // 10
System.out.println(count);    // 10
~~~

Khi `valid` là true, chỉ nhánh `count = 10` được đánh giá; nhánh còn lại không chạy. Giá trị của phép gán được chọn trở thành kết quả biểu thức điều kiện.

**Điểm quan trọng:** việc gán trạng thái bên trong `?:` có thể khó kiểm tra; cách thông thường dễ đọc hơn:

~~~java
if (valid) {
    count = 10;
} else {
    count = -1;
}
int selected = count;
~~~

Cách nào đúng phụ thuộc quy mô logic, nhưng không nên đặt các side effect quan trọng vào biểu thức lồng nhiều tầng.

## 9. Thứ tự đánh giá khi dùng giá trị gán trong phép tính

~~~java
int n = 1;
int result = (n = 4) + n;
System.out.println(result); // 8
System.out.println(n);      // 4
~~~

Toán hạng trái `(n = 4)` được đánh giá trước toán hạng phải `n`. Nó cập nhật `n` và cung cấp `4`; lần đọc sau cũng thấy `4`. Hai việc “cung cấp giá trị” và “đổi trạng thái” xảy ra trong một biểu thức, nên hãy thận trọng khi đặt phép gán vào phép tính hoặc điều kiện.

Các tình huống nhiều lần `++`/`--` trên cùng biến cần một cách truy vết khác và được phân tích ở bài cuối chương. Ở đây, mẫu an toàn khi không cần side effect trong biểu thức là tách rõ:

~~~java
n = 4;
int simplerResult = n + n; // 8
~~~

## 10. Field và phần tử mảng cũng dùng phép gán có giá trị

Ví dụ field:

~~~java
static final class Box {
    int value;
}

Box box = new Box();
int assignedField = (box.value = 12);

System.out.println(box.value);     // 12
System.out.println(assignedField); // 12
~~~

Ví dụ mảng:

~~~java
int[] scores = {3, 7};
int assignedElement = (scores[1] = 20);

System.out.println(scores[1]);      // 20
System.out.println(assignedElement); // 20
~~~

Trong cả hai trường hợp, biểu thức gán cập nhật **một biến thực sự**: một field hoặc một thành phần mảng. Giá trị biểu thức phản ánh giá trị sau gán.

### Chỉ số mảng có thể có tác dụng phụ riêng

~~~java
int[] values = {10, 20};
int index = 0;
int result = (values[index++] = 99) + index;

System.out.println(values[0]); // 99
System.out.println(index);     // 1
System.out.println(result);    // 100
~~~

`index++` cung cấp chỉ số 0 rồi tăng `index` lên 1. Phép gán phần tử cho giá trị 99; vế phải `+ index` dùng 1. Ví dụ hợp lệ nhưng **khó đọc và dễ sửa sai** hơn cách tách việc chọn chỉ số, cập nhật mảng và tính tổng.

## 11. Gán tham chiếu không sao chép đối tượng

~~~java
StringBuilder first = new StringBuilder("A");
StringBuilder alias = first;

alias.append("B");
System.out.println(first); // AB
~~~

`alias = first` sao chép **giá trị tham chiếu**, nên hai biến trỏ đến **cùng object**; phép gán không tạo bản sao `StringBuilder`.

Khi gán tham chiếu mới vào một biến:

~~~java
StringBuilder original = first;
first = new StringBuilder("C");

System.out.println(original); // AB
System.out.println(first);    // C
~~~

`first` trỏ sang object mới; `original` vẫn trỏ object cũ. Không nhầm **gán lại biến tham chiếu** với **sửa nội dung object**.

Nếu muốn object độc lập, phải dùng cơ chế copy thích hợp do class cung cấp, chẳng hạn `new StringBuilder(first.toString())` trong ngữ cảnh này.

## 12. Ranh giới giữa `=` và các phép gán kết hợp

Phép gán đơn giản `x = value` chuyển giá trị vế phải theo quy tắc *assignment conversion*. Phép gán kết hợp như `x += value` còn thực hiện phép toán rồi có thể **thu hẹp ngầm** kết quả về kiểu vế trái; với vế trái phức tạp, nó chỉ đánh giá vế trái **một lần**. Đây là khác biệt về ngữ nghĩa, không chỉ cách viết ngắn:

~~~java
byte b = 120;
b += 10;             // Hợp lệ; 130 thu hẹp về byte thành -126.
// b = b + 10;       // Lỗi compile: phép cộng thông thường cho int.

String label = "value=";
label += 7;          // Nối chuỗi: "value=7".
~~~

Bài này chỉ dùng những ví dụ đó để **đặt ranh giới với toán tử `=`**. Khi tính toán thật, kiểm tra miền số và tác dụng phụ; đừng tự thay `op=` bằng `x = x op y` khi vế trái là biểu thức có side effect.

## 13. Gán và ràng buộc của `final`

`final` giới hạn việc **gán lại biến**, không phải luôn làm đối tượng mà tham chiếu trỏ đến bất biến:

~~~java
final int once;
once = 10; // Hợp lệ: biến local final được gán chắc chắn đúng một lần.
// once = 11; // Lỗi compile: gán lại.

final StringBuilder builder = new StringBuilder("A");
builder.append("B"); // Hợp lệ: sửa trạng thái object.
// builder = new StringBuilder("C"); // Lỗi: gán lại tham chiếu final.
~~~

Giá trị của phép gán `=` không bỏ qua các quy tắc definite assignment và `final`. Khi chỉ cần cập nhật một biến thông thường, hãy ưu tiên câu lệnh độc lập dễ kiểm tra thay vì lồng trong biểu thức lớn.

## 14. Exception và lỗi trong vế phải

Một phép gán chỉ hoàn thành bình thường khi những bước cần thiết đều thành công. Ví dụ vế phải ném ngoại lệ:

~~~java
int value = 3;
int divisor = 0;

try {
    value = 10 / divisor;
} catch (ArithmeticException ex) {
    System.out.println("division failed");
}
System.out.println(value); // 3
~~~

Với biến cục bộ đơn giản này, phép chia `10 / divisor` thất bại **trước khi giá trị mới được gán**, nên `value` vẫn bằng 3.

Nhưng không nên suy rộng rằng mọi biểu thức gán thất bại đều **không có tác dụng phụ**: quá trình đánh giá vế trái hoặc vế phải có thể đã gọi method, tăng chỉ số, sửa object hoặc ghi I/O trước khi exception xảy ra.

**Khuyến nghị:** kiểm tra input và hạn chế nhiều side effect trong một biểu thức gán, nhất là trong logic giao dịch.

## 15. Các lỗi phổ biến và cách khắc phục

| Lỗi / ngộ nhận | Vì sao sai? | Cách đúng |
|---|---|---|
| `x = 5` là phép so sánh | `=` gán, không so | `x == 5` |
| `if (ready = true)` để kiểm tra `ready` | Thực tế gán true rồi điều kiện luôn true | `if (ready)` |
| `5 = x` | Literal không phải biến có thể gán | `x = 5` |
| `a + 1 = 3` | Kết quả phép cộng không gán được | Gán vào biến thích hợp |
| `int x = 3.5;` | Double không tự chuyển thành int | Cast có kiểm tra hoặc dùng double |
| `Long boxed = 7;` | Không tự int → long → Long | `Long boxed = 7L;` |
| `byte b = 128;` | Hằng không vừa miền byte | Chọn kiểu đủ lớn, không che bằng cast |
| Nghĩ `a = b = 9` nhóm từ trái | Phép gán kết hợp phải | `a = (b = 9)` |
| `i = i++` để tăng i | Phép gán ngoài ghi đè tăng hậu tố | `i++;` |
| Nghĩ assignment expression không có giá trị | Nó có giá trị sau gán | Có thể dùng `(x = 5) + 2`, nhưng cân nhắc dễ đọc |
| `byte b; b = b + 1;` | Kết quả int không tự thu hẹp | Chọn int hoặc cast có kiểm tra |
| Nghĩ `b += 1` luôn y như `b = b + 1` | Compound assignment có chuyển kiểu và đánh giá vế trái đặc thù | Hiểu quy tắc trước khi đổi code |
| Gán tham chiếu tưởng đã clone object | Sao chép tham chiếu, không copy object | Dùng copy riêng khi cần |
| Gán lại biến `final` | Vi phạm quy tắc definite assignment | Thiết kế init một lần |
| Cho rằng `catch` luôn rollback phép gán | Side effect trước lỗi có thể đã xảy ra | Tách bước/validate/transaction phù hợp |

## 16. Chương trình Java 17 đầy đủ — quan sát riêng phép gán

Lưu thành `AssignmentExpressionDemo.java`. Ví dụ gom các trường hợp **phép gán đơn giản trả giá trị** và phân biệt với phép so sánh; những chương trình về `op=`, gán chuỗi và `++` được triển khai ở bài riêng.

~~~java
public final class AssignmentExpressionDemo {
    static final class Box {
        int value;
    }

    public static void main(String[] args) {
        int count = 1;
        int result = (count = 5) + 2;
        System.out.println("assignment=" + result + ",count=" + count);

        boolean ready = false;
        boolean expression = (ready = true);
        System.out.println("boolean=" + expression + ",ready=" + ready);

        int number = 0;
        long widened = (number = 7);
        System.out.println("widened=" + widened + ",number=" + number);

        Box box = new Box();
        int assignedField = (box.value = 12);
        System.out.println("field=" + assignedField + ",stored=" + box.value);

        int[] scores = {3, 7};
        int assignedElement = (scores[1] = 20);
        System.out.println("element=" + assignedElement + ",stored=" + scores[1]);

        StringBuilder first = new StringBuilder("A");
        StringBuilder alias = first;
        alias.append("B");
        System.out.println("alias=" + first);

        int unchanged = 3;
        int zero = 0;
        try {
            unchanged = 10 / zero;
        } catch (ArithmeticException ex) {
            System.out.println("rhs failed");
        }
        System.out.println("unchanged=" + unchanged);
    }
}
~~~

Biên dịch và chạy với **JDK 17+** trong thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 AssignmentExpressionDemo.java
java AssignmentExpressionDemo
~~~

**Expected stdout:**

~~~text
assignment=7,count=5
boolean=true,ready=true
widened=7,number=7
field=12,stored=12
element=20,stored=20
alias=AB
rhs failed
unchanged=3
~~~

`(count = 5)` trả `5`; gán `boolean` trả `true`; giá trị `int` từ `(number = 7)` có thể chuyển rộng thành `long`. Phép gán field/mảng cập nhật đúng nơi chứa giá trị, còn gán tham chiếu chỉ sao chép tham chiếu. Cuối cùng, phép chia cho 0 làm vế phải thất bại trước khi `unchanged` nhận giá trị mới.

## 17. Bài tập có đáp án

### Bài A — giá trị biểu thức gán

~~~java
int x = 2;
int y = (x = 6) * 3;
System.out.println(x);
System.out.println(y);
~~~

**Đáp án:**

~~~text
6
18
~~~

### Bài B — chuỗi gán

~~~java
int a, b, c;
a = b = c = 4;
System.out.println(a + b + c);
~~~

**Đáp án:** `12`. Cả ba biến nhận 4 rồi cộng số nguyên.

### Bài C — lỗi logic `=` và `==`

~~~java
boolean enabled = false;
if (enabled = true) {
    System.out.println("enabled");
}
~~~

**Đáp án:** in `enabled`; đoạn code đã **gán true**, không phải so sánh. Nếu chỉ muốn kiểm tra giá trị ban đầu, viết `if (enabled)`.

### Bài D — khác nhau giữa `=` và `+=`

~~~java
byte a = 120;
a += 10;
System.out.println(a);
~~~

**Đáp án:** `-126`. Compound assignment tự chuyển về byte; `a = a + 10` không tự hợp lệ vì phép cộng thông thường trả `int`.

### Bài E — biểu thức gán trong mảng

~~~java
int[] data = {5, 8};
int result = (data[0] = 12) + data[1];
System.out.println(result);
System.out.println(data[0]);
~~~

**Đáp án:**

~~~text
20
12
~~~

### Bài F — local final

~~~java
final int value;
value = 3;
// value = 4;
~~~

**Đáp án:** gán `3` là khởi tạo hợp lệ; bật dòng `value = 4` sẽ lỗi compile do gán lại biến local final.

### Bài G — xử lý exception

~~~java
int x = 10;
int zero = 0;
try {
    x = 1 / zero;
} catch (ArithmeticException ex) {
    System.out.println(x);
}
~~~

**Đáp án:** `10`. Vế phải lỗi trước khi phép gán đơn giản cập nhật `x`.

## 18. Checklist và kết luận

- [ ] Hiểu toán tử `=` là **gán**, `==` là **so sánh bằng**.
- [ ] Biết vế trái phải là một biến gán được (local, field, array component).
- [ ] Biết phép gán là biểu thức có kiểu và giá trị sau gán.
- [ ] Hiểu `int y = (x = 5) + 2;` vừa sửa `x` vừa tạo giá trị 7.
- [ ] Hiểu phép gán kiểm tra *assignment conversion* theo kiểu đích.
- [ ] Biết chuỗi `a = b = c = 9` được nhóm từ phải sang trái.
- [ ] Không dùng nhầm `if (condition = true)` thay cho kiểm tra boolean.
- [ ] Nhận diện side effect khi lồng phép gán vào biểu thức khác.
- [ ] Biết gán field/mảng cũng tạo giá trị; chú ý chỉ số thay đổi.
- [ ] Biết gán tham chiếu không tự sao chép object.
- [ ] Phân biệt `=` đơn giản với compound assignment như `+=`.
- [ ] Hiểu `final` ngăn gán lại biến đã khởi tạo.
- [ ] Biết vế phải ném exception có thể khiến phép gán không hoàn tất.
- [ ] Chạy `AssignmentExpressionDemo.java` bằng `javac` và `java` trên JDK 17+; so khớp toàn bộ stdout.

**Kết luận:** `a = b` trong Java 17+ vừa **cập nhật biến `a`** vừa **tạo một giá trị biểu thức** theo kiểu được kiểm tra tại compile time. Khả năng dùng phép gán trong biểu thức lớn hơn giải thích được gán chuỗi, gán trong điều kiện và biểu thức số học — nhưng cũng tạo nguy cơ side effect khó đọc. Ưu tiên các câu lệnh gán riêng, có tên biến rõ ràng, và chỉ tận dụng giá trị của biểu thức gán khi thực sự giúp code đơn giản hơn.