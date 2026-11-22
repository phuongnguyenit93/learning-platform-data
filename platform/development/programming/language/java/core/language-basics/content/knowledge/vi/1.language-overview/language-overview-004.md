# Dữ liệu, biểu thức, câu lệnh và luồng thực thi

## 1. Bốn khái niệm tạo thành một chương trình Java

Một chương trình Java nhận **dữ liệu**, dùng **biểu thức** để tính toán/so sánh, dùng **câu lệnh** để thực hiện công việc, và tuân theo **luồng thực thi** để biết phần mã nào được chạy và chạy bao nhiêu lần.

Ví dụ:

~~~java
int price = 80;
int quantity = 2;
int total = price * quantity;

if (total >= 100) {
    System.out.println("Đơn hàng lớn");
}
~~~

- `80` và `2` là các **giá trị literal**; `price`, `quantity`, `total` là biến có kiểu `int`.
- `price * quantity` là **biểu thức**: khi đánh giá, nó tạo ra giá trị `160`.
- `int total = price * quantity;` là **câu lệnh khai báo biến cục bộ** có biểu thức khởi tạo.
- `total >= 100` là biểu thức kiểu `boolean`, được `if` sử dụng để quyết định có chạy khối in thông báo hay không.
- Dấu `{ }` giới hạn **block**; những câu lệnh bên trong block chỉ được chạy khi điều kiện phù hợp.

Quan hệ chính có thể hình dung:

~~~mermaid
flowchart TD
    DATA["Dữ liệu và biến"] --> EXP["Đánh giá biểu thức"]
    EXP --> STMT["Thực hiện câu lệnh"]
    STMT --> DEC{"Điều kiện / vòng lặp?"}
    DEC -->|"Đúng hoặc còn lặp"| STMT
    DEC -->|"Không / hoàn tất"| END["Câu lệnh tiếp theo<br/>hoặc kết thúc phương thức"]
~~~

Sơ đồ là mô hình khái quát; một câu lệnh có thể chứa **nhiều** biểu thức, một biểu thức có thể có tác dụng phụ, và các cấu trúc `return`, `break`, `continue` hoặc exception có thể chuyển điều khiển sang vị trí khác.

## 2. Dữ liệu: giá trị, kiểu và biến

### Kiểu dữ liệu cơ bản

Java là ngôn ngữ có **kiểu tĩnh**: mỗi biến và biểu thức có một kiểu được trình biên dịch kiểm tra. Tám kiểu nguyên thủy (*primitive*) gồm:

| Kiểu | Ý nghĩa và ví dụ | Lưu ý |
|---|---|---|
| `byte`, `short`, `int`, `long` | Số nguyên: `int age = 20;`, `long id = 123L;` | Có miền giá trị giới hạn; số nguyên không tự vô hạn |
| `float`, `double` | Số dấu phẩy động: `double rate = 0.15;` | Có sai số biểu diễn và các giá trị đặc biệt |
| `char` | Một **đơn vị mã UTF-16**: `char mark = 'A';` | Không đồng nhất với mọi ký tự Unicode hoàn chỉnh |
| `boolean` | `true` hoặc `false` | Không tự đổi thành `0`/`1` như một số ngôn ngữ khác |

`String`, mảng như `int[]`, và các object khác là **kiểu tham chiếu**. Biến tham chiếu có thể giữ tham chiếu tới object hoặc `null`, không chứa nguyên cả object theo cách biến primitive giữ giá trị của nó:

~~~java
int count = 3;
String label = "Java";
int[] points = {10, 20, 30};
String missing = null;
~~~

`label.length()` hoạt động khi `label` không null, còn `missing.length()` ném `NullPointerException` tại runtime. Kiểu tĩnh `String` không tự bảo đảm tham chiếu luôn khác null.

### Literal, kiểu suy ra và phép gán

~~~java
int units = 10;
long population = 8_000_000_000L;
double ratio = 0.25;
boolean active = true;
char grade = 'A';
String city = "Ha Noi";

units = units + 5;
final int MAX_ITEMS = 20;
~~~

Các literal nguyên như `10` thường có kiểu `int`, trừ một số trường hợp/đuôi literal phù hợp; `L` chỉ literal `long`. Dấu gạch dưới trong `8_000_000_000L` giúp dễ đọc, không đổi giá trị. `final` trên biến cấm **gán lại biến** sau khi nó đã được gán, nhưng nếu đó là tham chiếu tới object mutable, không có nghĩa mọi trạng thái của object đều bất biến.

Trong Java 10+, biến cục bộ có thể dùng `var` khi có initializer phù hợp:

~~~java
var score = 10;     // Suy ra int ở thời điểm biên dịch
var message = "Hi"; // Suy ra String
~~~

`var` không biến Java thành ngôn ngữ kiểu động: kiểu suy ra vẫn cố định. Không thể viết biến cục bộ `var unknown = null;` vì compiler không suy ra kiểu phù hợp từ literal `null` đơn lẻ.

### Gán không giống so sánh

- `=` **gán** giá trị ở vế phải cho biến/vị trí lưu hợp lệ ở vế trái.
- `==` **so sánh** hai toán hạng; với primitive, thường so sánh giá trị; với hai tham chiếu object, so sánh **cùng tham chiếu** hay không.
- `"abc".equals(other)` kiểm tra nội dung theo hợp đồng của `String`; không nên dùng `==` để kiểm tra hai chuỗi có cùng ký tự.

~~~java
String a = new String("Java");
String b = new String("Java");
System.out.println(a == b);      // false: hai object khác nhau
System.out.println(a.equals(b)); // true: nội dung giống nhau
~~~

## 3. Biểu thức là gì?

**Biểu thức (expression)** được đánh giá để tạo **một giá trị hoặc kết quả** và có một kiểu. Biểu thức có thể là literal, tên biến, phép tính, lời gọi method có kiểu trả về, phép so sánh, phép gán, hoặc một biểu thức điều kiện.

| Biểu thức | Kiểu/kết quả (giả sử biến hợp lệ) | Công dụng |
|---|---|---|
| `42` | `int` / 42 | Literal |
| `price * quantity` | Số được tính từ hai toán hạng | Số học |
| `score >= 60` | `boolean` | Điều kiện |
| `ready && hasTicket` | `boolean` | Kết hợp điều kiện |
| `isMember ? 90 : 100` | Số được chọn theo điều kiện | Conditional expression |
| `"Hi".length()` | `int` / 2 | Gọi method |
| `x += 2` | Phép gán có giá trị kết quả | Cập nhật biến |

Không phải biểu thức nào cũng được phép đứng riêng thành **expression statement** trong Java. Hợp lệ, chẳng hạn:

~~~java
int x = 3;
x++;                     // increment statement
x = x + 2;               // assignment statement
System.out.println(x);   // method invocation statement
new StringBuilder();     // class instance creation statement
~~~

Nhưng một phép tính trần `x + 2;` **không phải câu lệnh hợp lệ**: giá trị vừa tính không được sử dụng, và Java không cho phép mọi expression đứng độc lập như statement.

Một lời gọi method trả `void`, chẳng hạn `System.out.println("Hi")`, được dùng trong câu lệnh gọi method nhưng không tạo ra một giá trị `void` có thể gán cho biến.

## 4. Toán tử, ưu tiên và thứ tự đánh giá

Các nhóm toán tử quan trọng:

| Nhóm (từ ưu tiên cao đến thấp, lược giản) | Ví dụ |
|---|---|
| Hậu tố, lời gọi và truy cập | `x++`, `arr[i]`, `obj.method()` |
| Một ngôi | `++x`, `-x`, `!valid` |
| Nhân/chia/chia dư | `*`, `/`, `%` |
| Cộng/trừ | `+`, `-` |
| So sánh thứ tự | `<`, `<=`, `>`, `>=` |
| So sánh bằng/khác | `==`, `!=` |
| AND logic ngắn mạch | `&&` |
| OR logic ngắn mạch | `||` |
| Điều kiện ba ngôi | `condition ? a : b` |
| Gán | `=`, `+=`, `-=`, ... |

Bảng cố ý bỏ bớt toán tử dịch bit, bitwise và một số nhóm trung gian. **Dùng ngoặc** khi muốn diễn đạt rõ ý, thay vì cố thuộc toàn bộ bảng ưu tiên.

~~~java
int a = 2 + 3 * 4;      // 14
int b = (2 + 3) * 4;    // 20
boolean ok = a > 10 && b == 20; // true
~~~

**Ba quy tắc không được nhầm lẫn:**

1. **Ưu tiên** quyết định cách nhóm toán tử: `2 + 3 * 4` là `2 + (3 * 4)`.
2. **Thứ tự đánh giá toán hạng** của Java thường là **từ trái sang phải** theo biểu thức, ngoại trừ việc có toán hạng bị bỏ qua do quy tắc ngắn mạch hoặc nhánh điều kiện. Đừng lấy bảng ưu tiên để suy đoán một lời gọi method bên phải luôn xảy ra trước bên trái.
3. **Tính ngắn mạch**: `&&` không đánh giá vế phải khi vế trái là `false`; `||` không đánh giá vế phải khi vế trái là `true`.

Ví dụ an toàn:

~~~java
String input = null;
boolean valid = input != null && !input.isBlank();
System.out.println(valid); // false; không gọi input.isBlank()
~~~

Nếu đổi `&&` thành `&` với hai biểu thức boolean, cả hai phía được đánh giá và ví dụ trên sẽ gây `NullPointerException`. Hai toán tử **có cùng giá trị logic trong nhiều trường hợp nhưng khác hành vi đánh giá**.

### Tác dụng phụ trong biểu thức

~~~java
int x = 5;
int old = x++; // old = 5, sau đó x = 6
int now = ++x; // tăng x thành 7, now = 7
~~~

`x++` trả giá trị **trước khi tăng**, còn `++x` trả giá trị **sau khi tăng**. Tránh trộn nhiều lần tăng hoặc gọi method có tác dụng phụ trong một biểu thức khó đọc; tách thành các câu lệnh đơn giản để dễ kiểm tra.

Ví dụ đánh giá theo trái sang phải:

~~~java
static int logAndReturn(String label, int value) {
    System.out.println(label);
    return value;
}

// Đặt lời gọi sau trong một method:
int sum = logAndReturn("trai", 2) + logAndReturn("phai", 3);
// In "trai", rồi "phai"; sum = 5
~~~

## 5. Số học: các edge case dễ gây lỗi

### Chia số nguyên và chia dư

~~~java
System.out.println(7 / 2);   // 3, vì cả hai là int
System.out.println(7.0 / 2); // 3.5
System.out.println(7 % 2);   // 1
System.out.println(-7 / 2);  // -3: làm tròn về 0
System.out.println(-7 % 2);  // -1
~~~

Nếu muốn phần thập phân, phải có toán hạng `double`/`float` hoặc ép kiểu thích hợp. Ép kiểu **sau** phép chia nguyên thì đã quá muộn: `(double) (7 / 2)` là `3.0`, còn `(double) 7 / 2` là `3.5`.

### Tràn số nguyên

~~~java
int max = Integer.MAX_VALUE;
System.out.println(max + 1); // -2147483648 (tràn int)
~~~

Cộng `int` thông thường có thể tràn theo quy tắc số học Java. Nếu nghiệp vụ **không cho phép tràn**, dùng `Math.addExact(a, b)` để nhận `ArithmeticException` khi kết quả vượt miền giá trị, hoặc chọn cách biểu diễn số lớn phù hợp.

### Chia cho 0 và dấu phẩy động

~~~java
// int broken = 10 / 0; // Chia số nguyên cho 0 gây ArithmeticException khi thực thi phép chia
System.out.println(1.0 / 0.0); // Infinity
System.out.println(0.0 / 0.0); // NaN
System.out.println(0.1 + 0.2); // Thường hiển thị 0.30000000000000004
~~~

Số dấu phẩy động `double` tuân theo biểu diễn nhị phân IEEE 754 với các giới hạn độ chính xác. Không dùng so sánh `==` thiếu suy xét cho kết quả tính toán thập phân; khi làm việc với tiền, cân nhắc **số nguyên theo đơn vị nhỏ nhất** hoặc `BigDecimal` với quy tắc làm tròn được định nghĩa.

## 6. Câu lệnh và block: chương trình thực sự làm gì?

**Câu lệnh (statement)** yêu cầu Java thực hiện một hành động, có thể sử dụng kết quả biểu thức để điều khiển bước tiếp theo. Những loại thường gặp:

- Khai báo biến cục bộ: `int total = 0;`.
- Câu lệnh biểu thức: `total += price;`, `printResult();`.
- Block: `{ ... }`.
- Rẽ nhánh: `if / else`, `switch`.
- Lặp: `for`, `while`, `do-while`.
- Thay đổi luồng: `break`, `continue`, `return`, `throw`.

Ví dụ block và phạm vi biến:

~~~java
int outside = 10;
if (outside > 0) {
    int inside = outside * 2;
    System.out.println(inside); // 20
}
// System.out.println(inside); // Lỗi compile: outside scope
~~~

Một biến cục bộ phải được **gán chắc chắn trước khi đọc** theo phân tích của compiler (*definite assignment*). Ví dụ:

~~~java
boolean passed = true;
String status;
if (passed) {
    status = "PASS";
} else {
    status = "FAIL";
}
System.out.println(status); // hợp lệ: hai nhánh đều gán
~~~

Nếu bỏ nhánh `else` mà biến `status` có thể chưa được gán, compiler sẽ từ chối đọc nó. Khác với **field instance** có giá trị mặc định khi object được tạo, biến cục bộ không tự được cấp một giá trị mặc định để đọc tùy ý.

## 7. Rẽ nhánh: `if`, `else` và `switch`

### `if / else if / else`

~~~java
int score = 75;
if (score >= 90) {
    System.out.println("Xuat sac");
} else if (score >= 60) {
    System.out.println("Dat");
} else {
    System.out.println("Chua dat");
}
// In "Dat"
~~~

Điều kiện `if` phải là `boolean` hoặc kiểu phù hợp được unbox; Java **không** coi `0`, `1` hoặc chuỗi rỗng tự động là `false`/`true`. Nên dùng dấu ngoặc nhọn kể cả cho một câu lệnh để tránh lỗi khi thêm nhánh hoặc chỉnh sửa mã.

### `switch` statement và `switch` expression

Java 17 hỗ trợ kiểu `switch` có nhãn arrow:

~~~java
String mode = "FAST";
int timeout = switch (mode) {
    case "FAST" -> 3;
    case "NORMAL" -> 10;
    default -> 20;
};
System.out.println(timeout); // 3
~~~

Đây là **switch expression** vì toàn bộ `switch` tạo một giá trị để gán cho `timeout`. Với `switch` statement, mục tiêu chính là lựa chọn và thực thi nhánh câu lệnh, không nhất thiết sinh ra giá trị.

So với dạng `case ...:` truyền thống, nhánh `->` không tự **fall through** xuống nhánh kế tiếp. Switch expression cần bao phủ mọi trường hợp hợp lệ; `default` trong ví dụ giúp rõ ràng khi chuỗi có giá trị ngoài hai trường hợp liệt kê.

`switch` không phải thay thế mọi `if`: dùng khi mô hình “chọn giữa nhiều trường hợp” hợp lý hơn nhiều điều kiện bất kỳ.

## 8. Vòng lặp: `for`, `while`, `do-while`

### `for` khi biết cách tiến qua chỉ số

~~~java
int total = 0;
for (int i = 1; i <= 3; i++) {
    total += i;
}
System.out.println(total); // 6
~~~

Trình tự: chạy phần khởi tạo `i = 1` một lần → kiểm tra `i <= 3` → chạy thân vòng lặp → chạy cập nhật `i++` → kiểm tra tiếp. Nếu điều kiện ban đầu sai, thân có thể **không chạy lần nào**.

### Enhanced `for` để duyệt phần tử

~~~java
int[] values = {2, 4, 6};
int sum = 0;
for (int value : values) {
    sum += value;
}
System.out.println(sum); // 12
~~~

Enhanced `for` đơn giản khi chỉ cần từng phần tử, nhưng không tự cho chỉ số. Đổi giá trị biến cục bộ `value` không phải cách để thay trực tiếp phần tử `int` trong mảng.

### `while` và `do-while`

~~~java
int n = 3;
while (n > 0) {
    System.out.print(n + " ");
    n--;
}
// In "3 2 1 "
~~~

`while` kiểm tra **trước** mỗi lượt, còn `do-while` kiểm tra **sau** thân, vì thế thân `do` luôn chạy ít nhất một lần nếu được tới câu lệnh đó:

~~~java
int attempts = 0;
do {
    attempts++;
} while (attempts < 1);
System.out.println(attempts); // 1
~~~

### `break` và `continue`

~~~java
for (int i = 1; i <= 5; i++) {
    if (i == 2) continue; // bỏ phần còn lại của lượt i=2
    if (i == 4) break;    // thoát vòng lặp
    System.out.print(i + " ");
}
// In "1 3 "
~~~

`continue` chuyển tới lượt tiếp theo của vòng lặp chứa nó; `break` rời khỏi vòng lặp/switch statement phù hợp. Với vòng lặp lồng nhau, dạng không nhãn tác động lên cấu trúc bao gần nhất theo quy tắc ngôn ngữ. Khi duyệt nhiều tầng, giữ code dễ đọc thay vì lạm dụng `break` có nhãn.

## 9. `return`, exception và luồng kết thúc sớm

`return` kết thúc **lời gọi method hiện tại**, đồng thời trả về một giá trị nếu method có kiểu trả về khác `void`:

~~~java
static int safePercent(int value, int max) {
    if (max <= 0) {
        throw new IllegalArgumentException("max phai duong");
    }
    return value * 100 / max;
}
~~~

Ở đây `throw` tạo luồng thực thi ngoại lệ. Khi `max <= 0`, phép chia không diễn ra; exception chuyển điều khiển tới nơi xử lý phù hợp hoặc làm lời gọi thất bại.

**Giới hạn kỹ thuật cần nhớ:** `value * 100` vẫn có thể tràn `int`, dù `max` dương. Với dữ liệu lớn, có thể chuyển phép tính sang `long` trước rồi kiểm tra miền kết quả. Một nhánh phòng lỗi không tự làm toàn bộ phép tính an toàn.

Cơ chế `try/catch/finally` cho phép xử lý và dọn tài nguyên, nhưng không nên dùng exception thay cho toàn bộ kiểm tra điều kiện thông thường. Về trình tự, khi có `return` hoặc exception, những câu lệnh sau nó trên đường đi hiện tại không được thực hiện như bình thường. Nếu có `finally`, Java thường thực thi nó khi rời `try`/`catch` trước khi chuyển điều khiển ra ngoài.

~~~java
static int example() {
    try {
        System.out.println("try");
        return 10;
    } finally {
        System.out.println("finally");
    }
}
// Khi gọi example(): in "try", rồi "finally", sau đó method trả 10.
~~~

Tránh đặt `return` trong `finally`, vì có thể che mất kết quả/exception đang xảy ra; với tài nguyên `AutoCloseable`, `try-with-resources` thường rõ trách nhiệm hơn.

## 10. Ví dụ tổng hợp chạy được: từ dữ liệu đến luồng thực thi

Tạo tệp tên chính xác **`FlowWalkthrough.java`** và lưu bằng UTF-8:

~~~java
public final class FlowWalkthrough {
    private FlowWalkthrough() {}

    static int payable(int total, boolean member) {
        if (total < 0) {
            throw new IllegalArgumentException("Tong phai khong am");
        }
        int discount = member && total >= 100 ? 15 : 0;
        return total - discount;
    }

    public static void main(String[] args) {
        int[] prices = {40, 70, 20};
        int total = 0;
        int processed = 0;

        for (int i = 0; i < prices.length; i++) {
            int price = prices[i];
            if (price <= 0) {
                continue;
            }
            total += price;
            processed++;
        }

        boolean member = args.length > 0
                && "member".equalsIgnoreCase(args[0]);

        int amount = payable(total, member);
        String group = switch (amount) {
            case 0 -> "MIEN_PHI";
            default -> amount >= 100 ? "LON" : "NHO";
        };

        System.out.println("So mon: " + processed);
        System.out.println("Tong: " + total);
        System.out.println("Thanh vien: " + member);
        System.out.println("Can tra: " + amount);
        System.out.println("Nhom: " + group);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 FlowWalkthrough.java
java FlowWalkthrough
java FlowWalkthrough member
~~~

**Chạy không có đối số**:

~~~text
So mon: 3
Tong: 130
Thanh vien: false
Can tra: 130
Nhom: LON
~~~

**Chạy với đối số `member`**:

~~~text
So mon: 3
Tong: 130
Thanh vien: true
Can tra: 115
Nhom: LON
~~~

### Trace lần chạy có đối số `member`

| Bước | Câu lệnh/biểu thức | Trạng thái sau bước |
|---|---|---|
| 1 | `prices = {40,70,20}` | Mảng có 3 phần tử |
| 2 | `total=0; processed=0` | Tổng 0; đã xử lý 0 |
| 3 | Lượt `i=0`, giá 40 | Tổng 40; đã xử lý 1 |
| 4 | Lượt `i=1`, giá 70 | Tổng 110; đã xử lý 2 |
| 5 | Lượt `i=2`, giá 20 | Tổng 130; đã xử lý 3 |
| 6 | `args.length > 0 && ...` | `member=true` |
| 7 | `member && total >= 100 ? 15 : 0` | `discount=15` |
| 8 | `return total - discount` | `amount=115` |
| 9 | `switch(amount)` | `group="LON"` |
| 10 | Các câu lệnh `println` | In 5 dòng như trên |

**Các chi tiết đáng chú ý:**

- `prices.length` dùng để giới hạn chỉ số, tránh truy cập vượt khỏi phần tử cuối.
- `continue` bỏ qua giá không dương; ví dụ hiện có toàn giá dương. Nếu thêm `-5` vào mảng, vòng lặp vẫn an toàn và không tính dòng đó.
- `"member".equalsIgnoreCase(args[0])` gọi trên literal khác null. Khi không có đối số, `&&` ngắn mạch nên không đọc `args[0]`.
- `payable` tách phép tính và điều kiện đầu vào khỏi phần in ra; có thể thử độc lập với các giá trị tổng khác nhau.
- `switch` ở đây tạo `String` theo số tiền, trong khi vòng `for` và `if` là các câu lệnh điều khiển luồng.

## 11. Dự đoán đường chạy trước khi bấm Run

Xét:

~~~java
int x = 1;
if (x > 1) {
    x += 10;
} else {
    x += 2;
}
while (x < 5) {
    x++;
}
System.out.println(x);
~~~

Dùng bảng trace:

| Mốc | `x` | Lý do |
|---|---:|---|
| Sau khai báo | 1 | Initializer |
| Sau `if/else` | 3 | `x > 1` sai, chạy `else` |
| Sau vòng `while` lần 1 | 4 | `4 < 5` sẽ còn đúng khi kiểm tra tiếp |
| Sau vòng `while` lần 2 | 5 | `x < 5` trở thành sai |
| Khi in | 5 | Vòng lặp kết thúc |

Thói quen tốt: ghi **giá trị trước/sau** của biến, điều kiện đang xét và nhánh được chọn. Nếu không có tiến triển làm điều kiện lặp sai hoặc không có `break`, hãy kiểm tra nguy cơ vòng lặp vô hạn.

## 12. Lỗi thường gặp và cách phân loại

| Mã/sự cố | Triệu chứng | Nguyên nhân |
|---|---|---|
| `if (x = 1)` với `x` là `int` | Lỗi biên dịch | Kết quả gán kiểu `int`, không phải `boolean` |
| `int z = 7 / 2;` rồi mong `3.5` | Sai kết quả mong đợi | Chia nguyên trả `3` |
| `input.length()` khi `input == null` | `NullPointerException` | Gọi method qua tham chiếu null |
| `values[values.length]` | `ArrayIndexOutOfBoundsException` | Chỉ số cuối hợp lệ là `length - 1` khi mảng không rỗng |
| `while (n > 0)` không đổi `n` | Vòng lặp không kết thúc | Không có tiến triển hoặc nhánh thoát |
| Dùng `if (a && b)` nhưng `b` không được gọi | Hành vi đúng theo ngôn ngữ | Ngắn mạch khi `a=false` |
| Viết `total + price;` một mình | Lỗi biên dịch | Không phải expression statement hợp lệ |
| Truy cập biến khai báo trong một block ở bên ngoài | Lỗi biên dịch | Sai phạm vi biến |
| `String s = null; s.equals("x")` | `NullPointerException` | Không kiểm tra null |
| `int x = Integer.MAX_VALUE + 1;` | Số âm do tràn | Kết quả vượt phạm vi `int` |

Đọc lỗi theo **giai đoạn**: lỗi cú pháp/kiểu/phạm vi thường bị `javac` bắt; các exception liên quan dữ liệu thực hoặc chỉ số xuất hiện lúc chạy; vòng lặp vô hạn có thể không ném exception mà khiến chương trình treo lâu. Compile thành công không chứng minh mọi đường chạy đều đúng.

## 13. Bài tập kèm đáp án

### Bài 1 — xác định expression và statement

Trong đoạn `int n = 4; n += 3; System.out.println(n > 5);`, hãy chỉ ra hai biểu thức và ba câu lệnh.

**Đáp án:** biểu thức `4`, `n += 3`, `n > 5` đều hợp lệ (còn có biểu thức con); cả ba dòng kết thúc `;` là câu lệnh hoặc câu lệnh khai báo. `n > 5` có kiểu `boolean` và in ra `true`.

### Bài 2 — dự đoán kết quả

~~~java
int a = 8;
int b = 3;
System.out.println(a / b);
System.out.println((double) a / b);
~~~

**Đáp án:** `2` rồi `2.6666666666666665` (cách hiển thị thập phân thực tế theo giá trị `double`). Phép chia nguyên xảy ra khi cả hai toán hạng là `int`; cast trước phép chia đổi loại phép toán.

### Bài 3 — ngắn mạch bảo vệ dữ liệu

~~~java
String text = null;
boolean canRead = text != null && text.length() > 2;
System.out.println(canRead);
~~~

**Đáp án:** in `false`, không ném exception vì vế phải của `&&` không được đánh giá. Nếu dùng `&` boolean thay `&&`, vế phải sẽ bị đánh giá và có thể ném `NullPointerException`.

### Bài 4 — `continue` và `break`

~~~java
int sum = 0;
for (int i = 1; i <= 6; i++) {
    if (i == 2) continue;
    if (i == 5) break;
    sum += i;
}
System.out.println(sum);
~~~

**Đáp án:** `8` (`1 + 3 + 4`). Bỏ lượt 2; đến lượt 5 thì thoát vòng trước khi cộng.

### Bài 5 — sửa lỗi definite assignment

~~~java
boolean paid = false;
String result;
if (paid) {
    result = "OK";
}
// System.out.println(result);
~~~

**Yêu cầu:** cho phép in kết quả ở mọi đường chạy. **Đáp án:** thêm `else { result = "PENDING"; }` trước lệnh in; hoặc gán giá trị khởi đầu có chủ đích cho `result`.

### Bài 6 — mở rộng chương trình chính

Sửa `FlowWalkthrough` để thêm giá `0` và `-10` vào cuối mảng `prices`. Dự đoán `processed`, `total`, `amount`.

**Đáp án:** `processed=3`, `total=130`, `amount=130` nếu không có đối số; `amount=115` khi đối số là `member`. Hai phần tử không dương được `continue` bỏ qua trước khi cập nhật tổng/số món.

### Bài 7 — phân biệt lỗi biên dịch và runtime

Xét hai trường hợp: (A) `int count = "three";`; (B) `int divisor = 0; int value = 12 / divisor;`. Lỗi ở giai đoạn nào?

**Đáp án:** (A) `javac` từ chối vì kiểu không tương thích; (B) phép chia nguyên với divisor 0 ném `ArithmeticException` khi biểu thức được đánh giá lúc chạy.

## 14. Checklist tự đánh giá

- [ ] Giải thích được quan hệ **dữ liệu → biểu thức → câu lệnh → luồng thực thi** bằng một đoạn Java.
- [ ] Phân biệt `=` với `==`, kiểu primitive với kiểu tham chiếu, và `null` với một giá trị object hợp lệ.
- [ ] Xác định kiểu/kết quả của phép số học và biểu thức `boolean`; nhận diện chia nguyên, tràn số và sai số dấu phẩy động.
- [ ] Hiểu ưu tiên toán tử, đánh giá toán hạng và ngắn mạch `&&`/`||`.
- [ ] Biết một biểu thức bất kỳ không phải lúc nào cũng là một câu lệnh Java hợp lệ.
- [ ] Viết được `if`, `switch`, `for`, `while`, `break`, `continue` đúng ý.
- [ ] Dự đoán được khi nào `return` kết thúc method và `throw` thay đổi luồng chạy.
- [ ] Biên dịch và chạy `FlowWalkthrough.java`; kết quả khớp ví dụ.
- [ ] Lập bảng trace biến để giải thích được đầu ra và phát hiện vòng lặp sai.
- [ ] Phân loại được lỗi compile-time, runtime exception và lỗi logic dù chạy không báo lỗi.

**Kết luận:** dữ liệu là thứ chương trình xử lý; biểu thức tạo giá trị (đôi khi có tác dụng phụ); câu lệnh tổ chức hành động; cấu trúc điều khiển quyết định những hành động nào được thực hiện và theo thứ tự nào. Nắm được bốn lớp này giúp bạn đọc code, dự đoán đầu ra và kiểm tra lỗi Java có phương pháp, trước khi xây dựng chương trình lớn hơn.