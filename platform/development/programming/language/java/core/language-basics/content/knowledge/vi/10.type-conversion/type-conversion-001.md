# Chuyển đổi ngầm định và ép kiểu tường minh trong Java 17+

**Chuyển đổi kiểu (*type conversion*)** là cách Java đưa giá trị của một biểu thức từ kiểu này sang kiểu khác. Hai trường hợp cần phân biệt khi viết mã:

- **Chuyển đổi ngầm định (*implicit conversion*)**: Java áp dụng quy tắc chuyển kiểu được phép mà không cần viết toán tử ép kiểu, ví dụ chuyển `int` sang `long` khi gán hoặc nâng các toán hạng số trước phép toán.
- **Ép kiểu tường minh (*explicit cast*)**: người lập trình viết toán tử `(TargetType) expression`, thường khi chuyển kiểu có thể mất dữ liệu hoặc khi cần thu hẹp một tham chiếu. **Cast không bảo đảm kết quả chính xác hoặc an toàn lúc chạy.**

~~~java
int count = 120;
long wide = count;         // Ngam dinh: int -> long.
byte small = (byte) count; // Tuong minh: int -> byte.
~~~

Trong ví dụ, cả `wide` và `small` đều là 120 vì giá trị 120 biểu diễn được bằng `byte`. Nhưng nếu `count = 130`, phép cast sang `byte` cho `-126`.

## 1. Chuyển đổi số nguyên thủy: widening và narrowing

| Loại | Ví dụ | Compiler xử lý | Điều cần lưu ý |
| --- | --- | --- | --- |
| **Widening primitive** (mở rộng) | `long a = 42;` | Tự động cho phép | Không phải mọi chuyển sang số thực đều giữ độ chính xác |
| **Narrowing primitive** (thu hẹp) | `byte b = (byte) 130;` | Thường cần cast | Có thể mất bit, thay đổi giá trị |
| Mở rộng `char` | `int n = 'A';` | Tự động | `char` không dấu, `'A'` thành 65 |
| Thu hẹp thành `char` | `char c = (char) 66;` | Thường cần cast | Kết quả trong miền 0–65.535 |
| Chuyển `double` sang `int` | `int n = (int) 12.9;` | Cần cast | Bỏ phần thập phân, **không làm tròn gần nhất** |
| Ngầm định tại biểu thức số học | `int sum = byteA + byteB;` | Hai `byte` thường được nâng thành `int` | Kiểu kết quả phụ thuộc toán hạng |
| Chuyển `boolean` và kiểu số | `(int) true` | **Không hợp lệ** | Java không chuyển `boolean` sang số bằng cast |

Một chuỗi chuyển đổi mở rộng quen thuộc:

~~~text
byte -> short -> int -> long -> float -> double
                  ^
                 char  (char -> int -> long -> float -> double)
~~~

Đây là sơ đồ ghi nhớ **một số đường hợp lệ**, không phải danh sách mọi phép chuyển riêng lẻ. Chú ý `char -> short` và `byte -> char` **không** phải widening hợp lệ. `boolean` đứng ngoài các phép chuyển kiểu số này.

Widening **không nhất thiết bảo toàn toàn bộ chữ số**: ví dụ `long` lớn chuyển sang `double` có thể bị làm tròn vì `double` chỉ có 53 bit độ chính xác phần định trị. Ngược lại, `int -> long` bảo toàn đúng giá trị của mọi `int`.

## 2. Chương trình Java 17+ runnable

Tạo tệp UTF-8 tên **`TypeConversionDemo.java`**:

~~~java
public class TypeConversionDemo {
    public static void main(String[] args) {
        int original = 120;
        long asLong = original;
        double asDouble = original;

        System.out.println("widenIntToLong=" + asLong);
        System.out.println("widenIntToDouble=" + asDouble);

        long huge = 9_007_199_254_740_993L;
        double approximate = huge;
        System.out.println("largeLongPreserved="
                + ((long) approximate == huge));

        int outsideByte = 130;
        byte wrappedByte = (byte) outsideByte;
        System.out.println("byteFrom130=" + wrappedByte);

        System.out.println("positiveToInt=" + (int) 12.9);
        System.out.println("negativeToInt=" + (int) -12.9);
        System.out.println("hugeDoubleToInt=" + (int) 1.0e20);
        System.out.println("nanToInt=" + (int) Double.NaN);

        char letter = 'A';
        int letterCode = letter;
        System.out.println("charToInt=" + letterCode);
        System.out.println("intToChar=" + (char) 66);

        byte literalByte = 100;
        byte left = 10;
        byte right = 20;
        int sum = left + right;
        System.out.println("literalByte=" + literalByte);
        System.out.println("sumTypeInt=" + sum);

        int five = 5;
        int two = 2;
        double integerDivision = five / two;
        double floatingDivision = (double) five / two;
        System.out.println("integerDivision=" + integerDivision);
        System.out.println("floatingDivision=" + floatingDivision);

        Object general = "Java";
        System.out.println("upcastIsString=" + (general instanceof String));

        String specific = (String) general;
        System.out.println("downcast=" + specific);

        try {
            Integer wrong = (Integer) general;
            System.out.println("unexpected=" + wrong);
        } catch (ClassCastException ex) {
            System.out.println("badDowncast=ClassCastException");
        }
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) trong thư mục chứa file; dùng **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 TypeConversionDemo.java
java TypeConversionDemo
~~~

**Expected output chính xác** của lệnh `java TypeConversionDemo` (không gồm thông tin phiên bản JDK):

~~~text
widenIntToLong=120
widenIntToDouble=120.0
largeLongPreserved=false
byteFrom130=-126
positiveToInt=12
negativeToInt=-12
hugeDoubleToInt=2147483647
nanToInt=0
charToInt=65
intToChar=B
literalByte=100
sumTypeInt=30
integerDivision=2.0
floatingDivision=2.5
upcastIsString=true
downcast=Java
badDowncast=ClassCastException
~~~

### Giải thích các kết quả quan trọng

1. `int -> long` và `int -> double` là chuyển đổi mở rộng tự động. Giá trị 120 được giữ chính xác; vì biến `asDouble` là `double`, khi in hiển thị `120.0`.
2. `long huge = 2^53 + 1` không còn biểu diễn chính xác khi chuyển sang `double`. Giá trị bị làm tròn, nên so sánh sau khi chuyển lại thành `long` là `false`. **Không đồng nhất widening với “luôn chính xác”.**
3. `(byte) 130` thu hẹp xuống 8 bit có dấu: 130 vượt 127, kết quả `-126`. Cast vẫn được Java cho phép, không báo tràn.
4. `(int) 12.9` trả 12 và `(int) -12.9` trả -12: phần lẻ bị cắt **về phía 0**. Với `double` hữu hạn vượt miền `int`, kết quả khi cast được giới hạn vào biên gần nhất (`(int) 1.0e20` thành `Integer.MAX_VALUE`). `(int) Double.NaN` thành 0.
5. `char 'A'` mở rộng sang `int` thành mã số 65; cast `(char) 66` thành ký tự `B`.
6. Hai biến `byte` trong `left + right` được nâng thành `int`. Gán kết quả vào `int sum` là hợp lệ; gán trực tiếp vào một biến `byte` không được compiler cho phép nếu kết quả không phải biểu thức hằng phù hợp.
7. `five / two` diễn ra giữa hai `int`, cho 2 **trước khi** gán sang `double` thành `2.0`. Ép `five` sang `double` **trước phép chia** tạo `2.5`.
8. `Object general = "Java"` là phép mở rộng tham chiếu (*upcast*) được phép. Cast xuống `String` hợp lệ khi đối tượng thật là String. Cast xuống `Integer` vẫn có thể biên dịch từ `Object` nhưng thất bại **lúc chạy**, ném `ClassCastException`.

## 3. Hằng int trong ngữ cảnh gán

Java cho phép gán biểu thức hằng kiểu `int` nằm trong miền `byte`, `short` hoặc `char` mà không viết cast. Ngoại lệ này chỉ áp dụng ở những ngữ cảnh được đặc tả; không suy rộng thành chuyển đổi ngầm định cho biến `int` thông thường.

~~~java
byte threshold = 100;  // Hằng int vừa miền byte.
int runtime = 100;
// byte wrong = runtime; // Không biên dịch.
byte checked = (byte) runtime;
~~~

Việc biểu thức có phải hằng tại compile time khác với việc biến tình cờ chứa giá trị nhỏ lúc chạy. Bài chuyên sâu về gán hằng sẽ phân biệt thêm `final` constant variable và phạm vi áp dụng.
## 4. Cast đúng thời điểm trong biểu thức

Kiểu toán hạng quyết định kiểu phép toán **trước** khi kết quả được gán. Vì vậy `long wrong = (long) (50_000 * 50_000);` vẫn nhận tích `int` đã tràn, còn `long right = (long) 50_000 * 50_000;` thực hiện nhân ở `long`, nhận `2500000000`. Cast sau phép tính không khôi phục được bit đã mất. Với phép chia, `(double) 5 / 2` cho `2.5`, nhưng `(double) (5 / 2)` chỉ cho `2.0`.

## 5. Cast tham chiếu: kiểm tra đối tượng thực

`Object o = "Java";` có thể được downcast về `String` vì đối tượng thực là chuỗi. Nếu cùng tham chiếu ấy được cast sang `Integer`, chương trình ném `ClassCastException`. Cast **không tạo đối tượng mới** và không phải chuyển đổi nội dung thành chuỗi.

~~~java
Object o = "Java";
if (o instanceof String text) {
    System.out.println(text.length()); // 4
}
~~~

Pattern matching `instanceof` có trong Java 17; biểu thức `null instanceof String` là `false`, còn cast một tham chiếu `null` hợp lệ thì vẫn ra `null`.

## 6. Những cơ chế khác với numeric cast

`Integer boxed = 42; int raw = boxed;` lần lượt dùng boxing và unboxing; nếu wrapper là `null`, unboxing ném `NullPointerException`. `Integer.parseInt("42")` phân tích chuỗi, không phải cast tham chiếu. Java cũng không hỗ trợ `(int) true`; nếu cần mã số từ boolean phải viết chính sách riêng như `flag ? 1 : 0`.
## 7. Bài tập tự kiểm tra

1. **Ngầm định hay tường minh?** `long x = 17;` và `byte y = (byte) 130;` thuộc loại nào?  
   *Đáp án:* Câu đầu widening implicit, câu sau narrowing explicit và `y = -126`.
2. **Khi nào mất chính xác?** `double d = 9_007_199_254_740_993L;` có giữ đúng mọi đơn vị không?  
   *Đáp án:* Không; `double` không thể biểu diễn chính xác số nguyên `2^53 + 1`.
3. **Kiểu trung gian:** Với `int a = 50_000, b = 50_000;`, cách nào đúng cho tích `long`: `(long)(a*b)` hay `(long)a*b`?  
   *Đáp án:* `(long) a * b`, vì cast xảy ra trước phép nhân.
4. **Phép chia:** `double z = 7 / 2;` và `double w = (double) 7 / 2;` lần lượt bằng gì?  
   *Đáp án:* `3.0` và `3.5`.
5. **Reference cast:** `Object o = "Hi"; String a = (String) o;` có hợp lệ không? Còn `Integer b = (Integer) o;`?  
   *Đáp án:* Cast về String thành công; cast về Integer ném `ClassCastException` khi chạy.

## Checklist trước khi chuyển kiểu

- [ ] Phân biệt **implicit widening** và **explicit narrowing**.
- [ ] Kiểm tra **miền giá trị và độ chính xác**, không chỉ kích thước kiểu.
- [ ] Xác định kiểu **từng biểu thức trung gian** trước khi cast/gán kết quả.
- [ ] Biết `byte`/`short`/`char` thường được nâng lên `int` trong phép số học.
- [ ] Biết cast số thực sang số nguyên cắt về 0 và xử lý các giá trị ngoài miền theo quy tắc Java.
- [ ] Phân biệt reference cast với tạo đối tượng, parsing và boxing.
- [ ] Không mặc định downcast luôn an toàn; cân nhắc `instanceof`.

**Kết luận:** Java thực hiện nhiều chuyển kiểu **ngầm định** khi ngữ cảnh cho phép, nhưng ép kiểu `(TargetType)` là **yêu cầu chuyển đổi**, không phải lời cam kết giữ nguyên giá trị hoặc thành công ở runtime. Hãy xem xét miền giá trị, loại biểu thức và kiểu động của đối tượng trước khi chọn cách chuyển.
