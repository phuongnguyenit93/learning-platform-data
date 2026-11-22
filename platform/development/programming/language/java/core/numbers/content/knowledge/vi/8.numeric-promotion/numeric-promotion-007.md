# Toán tử điều kiện `?:` và các quy tắc đặc biệt cho số trong Java

## 1. `?:` làm gì, và vì sao kiểu số đôi khi gây bất ngờ?

Toán tử điều kiện ba ngôi (*conditional operator*) của Java có cú pháp:

~~~java
condition ? valueIfTrue : valueIfFalse
~~~

Đây là **cú pháp minh họa**, không phải một chương trình Java độc lập. `condition` phải có kiểu `boolean` hoặc `Boolean` (được unbox thành `boolean`). Khi điều kiện là `true`, Java đánh giá toán hạng thứ hai; khi là `false`, Java đánh giá toán hạng thứ ba. **Chỉ nhánh được chọn mới được đánh giá khi chạy**.

Ví dụ:

~~~java
int stock = 12;
int remaining = stock > 0 ? stock : 0;
~~~

Kết quả `remaining` bằng `12`. Với dữ liệu số học, người học thường dự đoán “Java lấy kiểu của nhánh chạy thực tế”. Điều đó **không đúng**: **kiểu của toàn bộ biểu thức `?:` được xác định lúc biên dịch từ kiểu của *cả hai nhánh***, kể cả nhánh không được chọn lúc chạy.

Đặc biệt, `?:` có các **ngoại lệ so với nâng kiểu số thông thường (*binary numeric promotion*)**. Biểu thức `byte b = 10; byte x = flag ? b : 20;` có thể hợp lệ dù một nhánh là literal `int`, bởi `20` là biểu thức hằng `int` nằm trong miền `byte`. Nhưng thay `20` bằng một biến `int` bình thường có thể khiến kiểu kết quả trở thành `int`, không thể gán trực tiếp cho `byte`.

Để dùng đúng `?:` trong phần số học Java, cần phân biệt:

1. **Nhánh nào chạy?** Chọn đúng một nhánh theo `boolean`.
2. **Kiểu toàn biểu thức là gì?** Trình biên dịch quyết định theo quy tắc của `?:`.
3. **Giá trị nhánh được chọn có cần chuyển kiểu?** Có thể có nâng kiểu số, unboxing hoặc chuyển đổi khác theo loại biểu thức.
4. **Kết quả có an toàn không?** Chuyển sang `float`/`double` có thể mất chính xác; unboxing `null` có thể ném `NullPointerException`.

## 2. Phân loại ba dạng biểu thức điều kiện

Đặc tả ngôn ngữ Java, mục `15.25`, phân biệt ba dạng:

| Dạng | Ví dụ | Quy tắc kiểu đáng chú ý |
|---|---|---|
| **Boolean conditional expression** | `flag ? true : false` | Kiểu `boolean` hoặc `Boolean` tùy kiểu hai nhánh |
| **Numeric conditional expression** | `flag ? 1 : 2L` | Tuân theo các quy tắc riêng cho kiểu số; ví dụ cho `long` |
| **Reference conditional expression** | `flag ? "yes" : "no"` | Có thể là *poly expression* chịu ảnh hưởng ngữ cảnh kiểu đích |

Bài học này tập trung vào **numeric conditional expressions**, tức khi nhánh thứ hai và thứ ba thuộc kiểu số nguyên thủy hoặc lớp bao tương ứng và được phân loại là biểu thức số theo đặc tả. Các nhánh như `String` và `null` có thể dẫn đến **reference conditional expression** với quy tắc riêng, nên không áp dụng máy móc bảng quy tắc số ở đây.

Với biểu thức điều kiện kiểu số, Java xác định kiểu dựa vào **cả hai toán hạng của nhánh**. Đây là *standalone expression*: kiểu của nó **không được thay đổi chỉ vì biến bên trái có kiểu mong muốn**. Ví dụ, nếu hai nhánh khiến kiểu kết quả là `int`, viết `byte result = ...` không tự buộc kết quả trở thành `byte`.

### Sơ đồ đánh giá khi chạy

~~~text
                 condition
                     |
                 boolean?
                  /     \
              true      false
               |          |
        đánh giá nhánh 2  đánh giá nhánh 3
               \          /
               chuyển đổi giá trị đã chọn
                       |
                giá trị biểu thức ?:
~~~

Sơ đồ này mô tả **thứ tự chạy**; kiểu kết quả đã được trình biên dịch xác định **trước** giai đoạn chạy. Nếu điều kiện là đối tượng `Boolean` mang `null`, việc unboxing điều kiện ném `NullPointerException` trước khi chọn nhánh nào.

## 3. Các quy tắc kiểu đặc biệt cho biểu thức số

Theo đặc tả, khi hai nhánh là biểu thức số, kiểm tra lần lượt:

1. **Hai nhánh có cùng kiểu:** kiểu kết quả là chính kiểu đó. Ví dụ `flag ? 1 : 2` là `int`; `flag ? 1L : 2L` là `long`; `flag ? someByte : otherByte` là `byte`.
2. **Một nhánh có kiểu primitive `T` và nhánh kia đúng lớp bao `T`:** kiểu kết quả là primitive `T`; chẳng hạn `byte` với `Byte` cho `byte`. Nhánh lớp bao có thể phải unbox.
3. **Một nhánh là `byte` hoặc `Byte`, nhánh kia là `short` hoặc `Short`:** kiểu kết quả **`short`** (dù dùng lớp bao ở một hoặc cả hai nhánh).
4. **Một nhánh `byte`, `short` hoặc `char`, nhánh còn lại là *constant expression* kiểu `int` nằm trong miền kiểu nhỏ đó:** kết quả có **kiểu nhỏ tương ứng**. Ví dụ `byte` với hằng `int` `100` cho `byte`.
5. **Tương tự với lớp bao `Byte`, `Short`, `Character` và hằng `int` phù hợp miền primitive bên trong:** kết quả là **primitive đã unbox**, ví dụ `Byte` với hằng `int` `100` cho `byte`.
6. **Nếu không thuộc các trường hợp trên:** thực hiện **nâng kiểu số tổng quát** (*numeric promotion*) lên kiểu chung; ví dụ `char` với `short` thành `int`, `int` với `long` thành `long`, `long` với `float` thành `float`, `float` với `double` thành `double`.

Điều thứ tư và thứ năm là hai ngoại lệ dễ bỏ sót. Không phải cứ có một nhánh kiểu `int` thì kết quả luôn là `int`; tuy nhiên **hằng số phải có kiểu `int`, là constant expression và nằm trong miền của kiểu hẹp**.

Bảng ví dụ (giả sử `flag` là `boolean` và các biến đúng kiểu đã ghi):

| Hai nhánh `?:` | Kiểu của cả biểu thức | Vì sao |
|---|---|---|
| `byte / byte` | `byte` | Cùng kiểu |
| `short / short` | `short` | Cùng kiểu |
| `byte / short` | `short` | Ngoại lệ `byte`–`short` |
| `byte / 100` | `byte` | `100` là hằng `int` nằm trong miền `byte` |
| `byte / 200` | `int` | `200` không nằm trong miền `byte` |
| `char / 65` | `char` | Hằng `int` `65` nằm trong miền `char` |
| `char / -1` | `int` | `-1` không nằm trong miền `char` |
| `char / short` | `int` | Numeric promotion |
| `short / intVariable` | `int` | Biến `int` bình thường, không phải constant expression |
| `int / long` | `long` | Numeric promotion |
| `long / float` | `float` | Numeric promotion; có thể mất chính xác |
| `float / double` | `double` | Numeric promotion |

Ở cột đầu, dấu `/` **chỉ phân cách kiểu của hai nhánh**, không biểu thị phép chia. Kiểu chung là quy tắc **biên dịch**, không phụ thuộc vào việc `flag` cuối cùng đúng hay sai.

## 4. Ngoại lệ `byte`–`short`: kết quả có kiểu `short`

Các biểu thức số học hai ngôi như `byteValue + shortValue` thường được nâng lên `int`. Nhưng `flag ? byteValue : shortValue` là trường hợp **đặc biệt**, kiểu kết quả là `short`:

~~~java
boolean flag = true;
byte small = 10;
short medium = 20;

short chosen = flag ? small : medium; // hợp lệ
// byte invalid = flag ? small : medium; // lỗi biên dịch: kết quả short
~~~

Đoạn minh họa có thể đặt vào `main`. Nếu `flag` là `true`, giá trị `10` của `byte` được mở rộng thành `short`; nếu `false`, chọn giá trị `20` kiểu `short`. **Kiểu tổng thể vẫn là `short` trong cả hai trường hợp**.

Những lớp bao tương ứng cũng chịu quy tắc này: `Byte` với `short` hoặc `Short` với `byte` có thể tạo biểu thức kiểu `short` và cần unbox ở nhánh được chọn.

Lưu ý khác biệt khi **cộng**:

~~~java
byte small = 10;
short medium = 20;
int sum = small + medium;  // int, vì phép cộng nâng kiểu
short selection = true ? small : medium; // short
~~~

Cùng hai kiểu toán hạng nhưng **hai toán tử khác nhau có hệ quy tắc kiểu khác nhau**.

## 5. Hằng `int` vừa miền kiểu nhỏ: `byte`, `short`, `char`

Giả sử có `byte small = 10;`:

~~~java
boolean flag = true;
byte small = 10;

byte a = flag ? small : 20;      // byte: 20 nằm trong [-128, 127]
int b = flag ? small : 200;      // int: 200 ngoài miền byte
// byte invalid = flag ? small : 200; // lỗi: toàn biểu thức kiểu int
~~~

Dù nhánh được chọn có thể là `small` và mang giá trị `10`, trình biên dịch vẫn xét **cả hai nhánh**. Đổi `flag` thành `true` cố định không biến biểu thức có kiểu `int` thành `byte` theo quy tắc `?:`; kết quả kiểu phải được suy ra trước khi xét gán vào biến đích.

Với `short` và `char` cũng tương tự:

~~~java
short count = 123;
char letter = 'A';

short s = true ? count : 30_000;   // short: 30000 vừa miền
char c = true ? letter : 65;       // char: 65 vừa miền
int x = true ? letter : -1;        // int: -1 không vừa char
int y = true ? count : 40_000;     // int: 40000 ngoài miền short
~~~

Đoạn mã là minh họa, không phải một class chạy độc lập.

### Biểu thức hằng khác với biến `int`

Một **biến `int` không phải `final`** không được xem là hằng thời điểm biên dịch, ngay cả khi tại runtime luôn bằng 20:

~~~java
byte small = 10;
int normal = 20;
final int constant = 20;

byte first = true ? small : constant; // byte
int second = true ? small : normal;   // int
// byte invalid = true ? small : normal; // lỗi nếu gán vào byte
~~~

Trong ví dụ, `constant` là **constant variable** vì kiểu primitive `int`, `final` và được khởi tạo bằng biểu thức hằng. Một biến `final int` được gán từ kết quả runtime, chẳng hạn lời gọi phương thức, **không tự trở thành constant variable**.

Có thể viết các biểu thức hằng như `10 + 10` hoặc `(1 << 5)` khi chúng đáp ứng quy tắc *constant expression*. Nhưng nếu biểu thức có kiểu `long`, ví dụ `20L`, thì ngoại lệ “hằng kiểu `int`” **không áp dụng**; `byte` với `20L` cho `long` theo numeric promotion.

## 6. Cách kiểm chứng **kiểu biên dịch**, không chỉ nhìn giá trị in ra

Nếu in `System.out.println(flag ? small : 20)`, bạn chỉ thấy số `10` hoặc `20`, không biết biểu thức mang kiểu `byte` hay `int`. Có thể dùng **overload** để quan sát lựa chọn của trình biên dịch.

Tạo tệp `ConditionalNumericTypeDemo.java`:

~~~java
public class ConditionalNumericTypeDemo {
    static String kind(byte value) { return "byte"; }
    static String kind(short value) { return "short"; }
    static String kind(int value) { return "int"; }
    static String kind(long value) { return "long"; }
    static String kind(float value) { return "float"; }
    static String kind(double value) { return "double"; }

    public static void main(String[] args) {
        boolean flag = true;
        byte small = 10;
        short medium = 20;
        char letter = 'A';
        int normal = 20;
        final int constant = 20;

        System.out.println("byteShort=" + kind(flag ? small : medium));
        System.out.println("byteIntConst=" + kind(flag ? small : 20));
        System.out.println("byteFinalConst=" + kind(flag ? small : constant));
        System.out.println("byteIntVariable=" + kind(flag ? small : normal));
        System.out.println("byteIntOutside=" + kind(flag ? small : 200));
        System.out.println("charShort=" + kind(flag ? letter : medium));
        System.out.println("intLong=" + kind(flag ? 1 : 2L));
        System.out.println("intDouble=" + kind(flag ? 1 : 2.5));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ConditionalNumericTypeDemo.java
java ConditionalNumericTypeDemo
~~~

Đầu ra:

~~~text
byteShort=short
byteIntConst=byte
byteFinalConst=byte
byteIntVariable=int
byteIntOutside=int
charShort=int
intLong=long
intDouble=double
~~~

Đây là **kiểu tĩnh của kết quả `?:`** được Java chọn tại vị trí gọi `kind`. Đặc biệt, dù `flag` đang là `true` và nhánh `small` có giá trị 10, dòng `byteIntOutside` vẫn gọi overload `kind(int)` vì nhánh không được chọn là hằng `200` vượt miền `byte`.

Bằng cách tương tự, trong môi trường Java 10+ có thể dùng `var result = flag ? small : medium;`. `var` suy diễn **kiểu tĩnh của biểu thức bên phải** là `short`; `var` không tự giữ kiểu của nhánh runtime.

## 7. Wrapper `Byte`, `Short`, `Character` và unboxing

Java hỗ trợ lớp bao cho primitive: `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`. Với `?:` dạng số, **box/unbox có thể xảy ra** để đưa hai nhánh về kiểu kết quả.

### Kết hợp primitive và wrapper đúng cặp

Ví dụ:

~~~java
Byte wrapper = Byte.valueOf((byte) 10);
byte primitive = 20;
byte chosen = true ? wrapper : primitive; // byte: wrapper được unbox
~~~

Biểu thức kết quả là **`byte`**, không phải `Byte`. Nếu wrapper là `null` và nhánh wrapper được chọn, phép unbox ném `NullPointerException`.

### Kết hợp wrapper với hằng `int` nằm trong miền

~~~java
Byte boxed = Byte.valueOf((byte) 5);
int chosen = true ? boxed : 7; // biểu thức có kiểu byte, mở rộng khi gán int
~~~

Ở đây, hằng `7` là `int` nằm trong miền `byte`, nên kết quả `?:` là **primitive `byte`**; khi gán cho `int` mới có thêm bước widening từ `byte` lên `int`.

Ngược lại, `true ? boxed : 200` có kiểu `int` vì `200` không nằm trong miền `byte`, cũng có thể cần unbox nhánh `boxed`.

### Hai wrapper cùng một kiểu

`Byte first = ...; Byte second = ...;` thì `flag ? first : second` có kiểu **`Byte`** theo quy tắc hai nhánh cùng kiểu. Kết quả có thể là `null` mà chưa ném lỗi, miễn là chưa có bước unboxing. Đây là khác biệt quan trọng với một nhánh `Byte` và một nhánh primitive `byte`.

### Ví dụ Java 17+ độc lập: lỗi `null` chỉ khi nhánh cần unbox được chọn

Tạo tệp `ConditionalWrapperDemo.java`:

~~~java
public class ConditionalWrapperDemo {
    public static void main(String[] args) {
        Byte missing = null;

        System.out.println("unselected=" + (false ? missing : 7));

        try {
            int value = true ? missing : 7;
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("selectedNull=NPE");
        }

        Byte other = Byte.valueOf((byte) 9);
        Byte sameType = true ? missing : other;
        System.out.println("sameTypeKeepsNull=" + (sameType == null));

        Boolean condition = null;
        try {
            int value = condition ? 1 : 2;
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("nullCondition=NPE");
        }
    }
}
~~~

~~~bash
javac ConditionalWrapperDemo.java
java ConditionalWrapperDemo
~~~

Đầu ra:

~~~text
unselected=7
selectedNull=NPE
sameTypeKeepsNull=true
nullCondition=NPE
~~~

Giải thích:

1. `false ? missing : 7` chọn `7` và không đánh giá biến `missing` như toán hạng được chọn để unbox; do đó không gây lỗi.
2. `true ? missing : 7` chọn `missing`: kiểu biểu thức số là `byte`, cần unbox đối tượng `null`, gây `NullPointerException`.
3. Hai nhánh `Byte` cùng kiểu, kết quả biểu thức vẫn là tham chiếu `Byte`, có thể mang `null`.
4. `condition` thuộc kiểu `Boolean` và chứa `null`; lỗi phát sinh khi unbox **điều kiện**, trước bước chọn nhánh.

Nếu cần diễn đạt rõ chính sách cho giá trị tùy chọn, có thể kiểm tra `null` trước hoặc chuyển sang câu lệnh `if`. Đừng xem `?:` là cơ chế tự động cung cấp giá trị mặc định an toàn khi có wrapper `null`.

## 8. Nâng kiểu số thông thường khi không có ngoại lệ

Nếu không khớp các trường hợp đặc biệt, hai nhánh được đưa tới một kiểu số chung. Quy tắc cốt lõi:

- Nếu có `double`, kết quả thường thành `double`.
- Nếu không có `double` nhưng có `float`, kết quả thường thành `float`.
- Nếu không có hai loại trên nhưng có `long`, kết quả thường thành `long`.
- Các tổ hợp nhỏ còn lại (`byte`, `short`, `char`, `int`) thường thành `int`, **trừ những ngoại lệ ở phần trước**.

Ví dụ:

~~~java
boolean flag = true;
char letter = 'A';
short small = 12;

int result = flag ? letter : small;   // int: char/short
long count = flag ? 12 : 30L;        // long: int/long
double ratio = flag ? 1.25f : 2.0;  // double: float/double
~~~

Đây là đoạn minh họa. Hãy lưu ý rằng kiểu chung có thể dẫn đến **mất chính xác**:

~~~java
long huge = 9_007_199_254_740_993L; // 2^53 + 1
double number = true ? huge : 0.0; // long được chuyển sang double
~~~

`double` không biểu diễn chính xác mọi số nguyên 64 bit. Ở ví dụ này, giá trị `huge` lớn hơn số nguyên chính xác cuối cùng liên tiếp của `double`, và chuyển đổi sang `double` có thể làm tròn thành `9007199254740992.0`. Chỉ dùng kiểu số dấu phẩy động khi sai số phù hợp với bài toán.

### Numeric promotion không phải toán tử cộng

`flag ? a : b` **chọn một nhánh**, khác `a + b` là thực hiện phép cộng. Mặc dù cả hai có thể dùng cơ chế numeric promotion, **chúng không đánh giá cả hai nhánh để cộng lại**, và `?:` có quy tắc đặc biệt cho `byte`/`short`/`char` cùng hằng `int` mà phép cộng không có.

## 9. Chỉ nhánh được chọn chạy: side effect và ngoại lệ

Tạo tệp `ConditionalEvaluationDemo.java`:

~~~java
public class ConditionalEvaluationDemo {
    private static int calls;

    private static int selected() {
        calls++;
        return 42;
    }

    private static int notSelected() {
        calls += 100;
        throw new IllegalStateException("should not execute");
    }

    public static void main(String[] args) {
        int answer = true ? selected() : notSelected();

        System.out.println("answer=" + answer);
        System.out.println("calls=" + calls);

        int second = false ? notSelected() : 7;
        System.out.println("second=" + second);
        System.out.println("callsAfter=" + calls);
    }
}
~~~

~~~bash
javac ConditionalEvaluationDemo.java
java ConditionalEvaluationDemo
~~~

Đầu ra:

~~~text
answer=42
calls=1
second=7
callsAfter=1
~~~

Lý do: `notSelected()` **không chạy** trong cả hai lần dùng `?:` vì điều kiện không chọn nhánh đó. Nhưng trình biên dịch vẫn kiểm tra **kiểu** và cú pháp của cả hai nhánh. Đừng đặt các side effect quan trọng ở nhánh không chắc được chọn. Nếu hai nhánh chứa nhiều lệnh phức tạp, `if/else` thường dễ đọc và dễ kiểm soát hơn.

Cũng cần phân biệt với `Math.max(a, b)`: khi gọi phương thức, Java đánh giá cả hai biểu thức đối số trước khi gọi, trong khi `?:` chỉ đánh giá biểu thức nhánh được chọn.

## 10. Kết hợp nhiều `?:`, độ ưu tiên và khả năng đọc

Toán tử điều kiện liên kết **từ phải sang trái** (*right associative*):

~~~java
int level = 2;
int score = level == 1 ? 10 : level == 2 ? 20 : 30;
~~~

Đây là mã minh họa; nó được hiểu là:

~~~java
int score = level == 1 ? 10 : (level == 2 ? 20 : 30);
~~~

Kết quả bằng `20`. Nếu có nhiều điều kiện và nhánh cùng số, cần bảo đảm kiểu của các biểu thức `?:` lồng nhau, vì kiểu của biểu thức con có thể tác động lên kiểu biểu thức ngoài. Dùng ngoặc và đặt tên biến trung gian cho các trường hợp khó đọc.

### Bẫy ưu tiên khi kết hợp phép toán

Một số biểu thức dễ hiểu sai khi thiếu ngoặc:

~~~java
int a = 5;
int b = 3;
int selected = a > b ? a : b;    // 5
int result = (a > b ? a : b) + 1; // 6
~~~

Đây là minh họa. Ngoặc ở `result` làm rõ phép cộng áp dụng lên **toàn bộ kết quả đã chọn**.

Không nên viết quá nhiều toán tử `?:` nối tiếp cho một quy tắc nghiệp vụ có nhiều điều kiện lồng nhau. Dùng `if/else` hoặc phương thức có tên rõ nghĩa thường dễ đọc, dễ kiểm thử hơn.

## 11. So sánh với biểu thức số học và câu lệnh `if/else`

| Tình huống | `?:` | `if/else` hoặc phép toán khác |
|---|---|---|
| Chọn một trong hai giá trị số ngắn gọn | Phù hợp, ví dụ `flag ? a : b` | `if/else` cũng được nhưng dài hơn |
| Hai nhánh có kiểu khác nhau | Cần hiểu quy tắc kiểu của `?:` | Có thể gán riêng sau kiểm tra miền |
| Nhánh có nhiều bước hoặc side effect | Dễ khó đọc | `if/else` rõ luồng |
| Cần xử lý wrapper có thể `null` | Có thể ném lỗi lúc unbox | Kiểm tra `null` và hợp đồng dữ liệu rõ ràng |
| Cần loại bỏ kết quả mất chính xác | Phải xác định kiểu biểu thức trước | Dùng kiểu chính xác/chuyển đổi có kiểm tra |
| Cần tính giá trị lớn/nhỏ nhất | `a > b ? a : b` | `Math.max(a, b)` thuận tiện cho số, nhưng biểu thức đối số được đánh giá theo cơ chế gọi phương thức |

### Không nhầm kiểu của `?:` với kiểu phép gán

Ví dụ, cả hai nhánh đều là biểu thức `int`, nhưng kết quả lựa chọn nằm trong miền `byte`:

~~~java
int left = 10;
int right = 20;
// byte value = true ? left : right; // không biên dịch
int value = true ? left : right;    // hợp lệ
~~~

Dù tại runtime kết quả là 10, kiểu `?:` vẫn là `int`. Nếu muốn thu hẹp xuống `byte`, hãy kiểm tra miền rồi cast một cách có chủ ý, hoặc khai báo các nhánh là `byte` phù hợp khi mô hình dữ liệu thực sự là số 8 bit.

Trường hợp khác: `flag ? (byte) 10 : 20` cho kiểu `byte` vì một nhánh là `byte` và nhánh kia là hằng `int` `20` nằm trong miền. Đây là ngoại lệ ở quy tắc `15.25.2`, không phải quá trình suy kiểu từ biến gán bên trái.

## 12. Những lỗi phổ biến

| Nhận định | Cách hiểu đúng |
|---|---|
| “`?:` luôn làm binary numeric promotion như `+`.” | Có các ngoại lệ như `byte` với `short` cho `short`, hoặc `byte` với hằng `int` vừa miền cho `byte`. |
| “`flag` đúng nên compiler chỉ xét kiểu nhánh thứ hai.” | Compiler vẫn xét kiểu của cả hai nhánh, dù nhánh kia không chạy. |
| “`byte` với bất kỳ `int` đều thành `byte` nếu chọn nhánh `byte`.” | Chỉ có ngoại lệ khi nhánh `int` là **constant expression** và giá trị nằm trong miền. |
| “`final int` luôn là hằng compile-time.” | Chỉ khi biến là *constant variable* được khởi tạo bằng biểu thức hằng hợp lệ. |
| “`byte` với `short` thành `int` vì phép `+` làm vậy.” | Riêng numeric `?:` có kết quả `short`. |
| “Hai nhánh `Byte` có kết quả `byte`.” | Nếu cùng kiểu `Byte`, biểu thức có kiểu `Byte`; trường hợp kết hợp primitive khác. |
| “Nhánh không chạy vẫn được unbox.” | Nhánh không được chọn không đánh giá lúc chạy, nhưng điều kiện `Boolean` cần unbox trước và nhánh được chọn có thể cần unbox. |
| “`null` an toàn vì Java tự chọn nhánh còn lại.” | Điều kiện mới quyết định nhánh; nếu chọn wrapper `null` cần unbox, sẽ có `NullPointerException`. |
| “Kiểu kết quả được chọn theo biến ở vế trái.” | Numeric conditional là standalone expression, kiểu được xác định từ nhánh. |
| “`long` với `float` không mất dữ liệu vì cả hai đều nhiều bit.” | Chuyển `long` sang `float` có thể làm tròn/mất chính xác. |

## 13. Quy trình đọc một biểu thức `?:` số

Khi gặp `condition ? x : y`:

1. Xác minh `condition` có kiểu `boolean` hoặc `Boolean`; với `Boolean` lưu ý trường hợp `null`.
2. Xác định **kiểu tĩnh** của `x` và `y`, không chỉ giá trị đang giữ.
3. Kiểm tra có cùng kiểu hoặc cặp primitive-wrapper tương ứng không.
4. Kiểm tra ngoại lệ `byte`/`Byte` với `short`/`Short`.
5. Kiểm tra một nhánh `byte`/`short`/`char` (hoặc wrapper tương ứng) và nhánh kia là **hằng `int` nằm trong miền** hay không.
6. Nếu không, áp dụng numeric promotion để xác định kiểu chung.
7. Xác minh phép chuyển từ nhánh được chọn sang kiểu kết quả: có mất chính xác số học hoặc unboxing `null` không?
8. Cuối cùng, xem kiểu biểu thức đó có gán được cho biến đích hay không; nếu không, chọn kiểu đích đủ rộng hoặc kiểm tra/ép kiểu rõ ràng.

### Bài tập tự kiểm tra

Giả sử:

~~~java
boolean flag = true;
byte b = 5;
short s = 300;
char c = 'A';
int ordinary = 5;
final int fixed = 5;
Byte boxed = Byte.valueOf((byte) 5);
~~~

Đây là đoạn khởi tạo dùng chung cho các câu hỏi, chưa phải class hoàn chỉnh.

1. Kiểu của `flag ? b : s` là gì?
2. Kiểu của `flag ? b : 5` là gì?
3. Kiểu của `flag ? b : ordinary` là gì, dù `ordinary` hiện bằng 5?
4. Kiểu của `flag ? b : fixed` là gì?
5. Kiểu của `flag ? c : s` là gì?
6. Kiểu của `flag ? boxed : 5` là `Byte`, `byte` hay `int`?
7. Kiểu của `flag ? b : 500` là gì?
8. Nếu `Byte missing = null;` thì `true ? missing : 5` có thể ném ngoại lệ nào?
9. Viết kiểu kết quả của `flag ? 5L : 2.5f`. Có đảm bảo mọi giá trị `long` chuyển sang kiểu đó chính xác không?
10. Nếu `flag` được đặt `true`, biểu thức `flag ? b : someMethod()` có gọi `someMethod()` không? Kiểu của lời gọi `someMethod()` có được compiler xét không?

**Gợi ý đáp án:** (1) `short`. (2) `byte`. (3) `int`. (4) `byte` vì `fixed` là constant variable. (5) `int`. (6) `byte`. (7) `int`. (8) `NullPointerException` khi cần unbox wrapper được chọn. (9) `float`; chuyển `long` sang `float` có thể mất chính xác. (10) Không gọi ở runtime; compiler vẫn kiểm tra kiểu cả hai nhánh.

## 14. Nguồn đặc tả và ghi nhớ

Các quy tắc trên được mô tả trong **Java Language Specification**, mục **15.25 — Conditional Operator `? :`**, đặc biệt **15.25.2 — Numeric Conditional Expressions**:  
[Java Language Specification §15.25](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.25)

**Ghi nhớ:** `?:` **chỉ đánh giá một nhánh khi chạy**, nhưng **kiểu của cả biểu thức được suy ra từ cả hai nhánh khi biên dịch**. Đối với kiểu số, hãy nhớ ngoại lệ `byte`/`short`, hằng `int` vừa miền kiểu hẹp, wrapper và unboxing; những ngoại lệ đó giải thích vì sao kiểu của `?:` không phải lúc nào cũng là kiểu của phép cộng trên cùng toán hạng.