# Toán tử, thuộc tính và quy ước của ngôn ngữ Java

**Chủ đề:** OOP → Cơ chế ngôn ngữ.  
**Mục tiêu:** dùng đúng các nhóm toán tử, hiểu thứ tự và kiểu kết quả của biểu thức; phân biệt trường dữ liệu (*field*) với thuộc tính theo quy ước JavaBeans, getter/setter và thành phần của `record`; áp dụng quy ước Java để viết mã rõ ràng, an toàn, dễ bảo trì.

Java có bộ quy tắc cú pháp và hệ thống kiểu tương đối chặt chẽ. Một biểu thức “hợp lệ khi biên dịch” vẫn có thể cho kết quả sai vì chia số nguyên, tràn số, so sánh nhầm tham chiếu, tác dụng phụ trong biểu thức hoặc thứ tự đánh giá không được hiểu đúng. Tương tự, việc một trường có thể truy cập từ nơi khác không có nghĩa nên biến toàn bộ trạng thái của đối tượng thành `public`.

## 1. Tổng quan các nhóm toán tử

| Nhóm | Ký hiệu thường gặp | Công dụng | Lưu ý |
| --- | --- | --- | --- |
| Số học | `+`, `-`, `*`, `/`, `%` | Tính toán; `+` còn nối chuỗi | `int/int` vẫn chia số nguyên; `%` là phép lấy phần dư |
| Tăng/giảm | `++`, `--` | Cập nhật biến tăng/giảm một đơn vị | Tiền tố và hậu tố khác thời điểm lấy giá trị |
| Dấu và phủ định | `+x`, `-x`, `!flag`, `~bits` | Đổi dấu, phủ định boolean hoặc từng bit | `!` chỉ dùng với boolean; `~` áp dụng cho kiểu số nguyên |
| So sánh | `<`, `<=`, `>`, `>=` | So sánh số hoặc kiểu có quy tắc toán tử tương ứng | Không so sánh trực tiếp hai `String` bằng `<` |
| Bằng nhau | `==`, `!=` | So sánh primitive theo giá trị, reference theo danh tính | Nội dung object thường so bằng `equals()` |
| Logic | `&&`, `\|\|`, `!` | Kết hợp điều kiện boolean | `&&` / `\|\|` có cơ chế short-circuit |
| Bit | `&`, `\|`, `^`, `~` | Thao tác từng bit trên integral types; `&`/`\|`/`^` cũng dùng cho boolean | `&` và `\|` với boolean luôn đánh giá hai vế |
| Dịch bit | `<<`, `>>`, `>>>` | Dịch trái, phải có dấu và phải điền 0 | Khoảng dịch được giới hạn theo kích thước kiểu |
| Gán | `=`, `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, … | Cập nhật biến | Gán kết hợp có thể ép kiểu ngầm về kiểu vế trái |
| Ba ngôi | `condition ? x : y` | Chọn một trong hai biểu thức | Chỉ đánh giá nhánh được chọn |
| Kiểm tra kiểu | `instanceof` | Xác định khả năng đối tượng thuộc một kiểu tại runtime | Với `null`, kết quả là `false` |
| Truy cập/gọi | `.`, `[]`, `()`, `new` | Truy cập thành viên, phần tử, gọi hàm, tạo object | Hành vi còn phụ thuộc visibility và kiểu biểu thức |

`->` của lambda và `::` của method reference cũng là cú pháp quan trọng, nhưng không nên coi chúng như phép toán số học thông thường. Chúng biểu diễn hàm/điểm tham chiếu phương thức phù hợp với functional interface.

### Ví dụ nhỏ: kết quả của toán tử

```java
int a = 7;
int b = 3;

System.out.println(a + b); // 10
System.out.println(a / b); // 2: chia nguyên
System.out.println(a % b); // 1
System.out.println((double) a / b); // 2.3333333333333335

int count = 5;
System.out.println(count++); // 5: dùng giá trị cũ rồi tăng
System.out.println(++count); // 7: tăng trước rồi dùng

System.out.println(-7 % 3); // -1: dấu của phần dư theo số bị chia
```

Trong Java, **phần dư `%` không đồng nhất với phép modulo luôn không âm**. Nếu cần kết quả không âm cho số chia dương, dùng `Math.floorMod(a, b)` thay vì tự giả định `a % b >= 0`. Ví dụ `Math.floorMod(-7, 3) == 2`.

## 2. Độ ưu tiên, tính kết hợp và thứ tự đánh giá

Nên đọc biểu thức theo hai khái niệm khác nhau:

- **Precedence** (độ ưu tiên) quyết định biểu thức được nhóm như thế nào khi thiếu ngoặc.
- **Associativity** (tính kết hợp) quyết định cách nhóm các toán tử **cùng mức**; phần lớn toán tử nhị phân là trái sang phải, phép gán và toán tử điều kiện nhóm từ phải sang trái.
- **Evaluation order** (thứ tự đánh giá) là lúc các toán hạng thực sự được tính và side effect xảy ra. Java nhìn chung đánh giá toán hạng từ trái sang phải theo quy tắc của từng biểu thức; điều này không đồng nghĩa với “mọi toán tử được thực hiện từ trái sang phải”.

Bảng rút gọn mức ưu tiên thường cần khi đọc Java (trên → dưới, cao → thấp):

| Mức | Nhóm | Ví dụ |
| --- | --- | --- |
| Cao nhất trong bảng | Truy cập, gọi hàm, chỉ số, hậu tố | `object.field`, `f()`, `array[i]`, `x++` |
| | Đơn ngôi, ép kiểu, tiền tố | `!ok`, `~mask`, `(long) x`, `++x` |
| | Nhân/chia/chia dư | `*`, `/`, `%` |
| | Cộng/trừ | `+`, `-` |
| | Dịch bit | `<<`, `>>`, `>>>` |
| | Quan hệ/kiểm tra kiểu | `<`, `<=`, `>`, `>=`, `instanceof` |
| | Bằng nhau | `==`, `!=` |
| | AND, XOR, OR trên bit hoặc boolean | `&` rồi `^` rồi `\|` |
| | AND logic | `&&` |
| | OR logic | `\|\|` |
| | Điều kiện | `?:` |
| Thấp | Gán và gán kết hợp | `=`, `+=`, `-=`, … |

Ví dụ:

```java
int result = 2 + 3 * 4;       // 14
int explicit = (2 + 3) * 4;   // 20

boolean allowed = true || false && false; // true
boolean clear = true || (false && false); // true

int x = 1, y = 2, z = 3;
x = y = z; // Tương đương x = (y = z)
```

**Đặt dấu ngoặc khi nó giúp người đọc hiểu ý định**, nhất là khi trộn bitwise với logic, ghép điều kiện dài hoặc chuyển đổi số. Không nên cố tạo biểu thức ngắn bằng nhiều lần `++`, gán và gọi phương thức có side effect trong cùng một dòng.

Điểm dễ nhầm:

```java
System.out.println("Tổng: " + 1 + 2);     // Tổng: 12
System.out.println("Tổng: " + (1 + 2));   // Tổng: 3
```

Các phép cộng và nối chuỗi cùng mức được nhóm từ trái qua phải; sau khi vế trái trở thành chuỗi, `+` nối chuỗi tiếp theo. Java không tự suy đoán bạn muốn cộng số trước.

## 3. Kiểu kết quả, nâng kiểu số và tràn số

### 3.1. Phép chia và numeric promotion

```java
int total = 5;
int portions = 2;

double wrong = total / portions;           // 2.0
double correct = (double) total / portions; // 2.5
```

Ở dòng đầu, biểu thức `total / portions` được tính bằng `int` **trước** khi gán vào `double`, nên phần thập phân đã mất. Ép kiểu một toán hạng trước phép chia sẽ thay đổi kiểu tính toán.

Đối với các phép toán số học thông thường trên `byte`, `short`, `char`, Java thực hiện **binary numeric promotion**; các giá trị nhỏ hơn `int` thường được nâng lên `int`:

```java
byte first = 10;
byte second = 20;

// Lỗi biên dịch: kết quả của first + second là int.
// byte sum = first + second;

int sum = first + second; // 30
```

`short`, `char` cũng chịu quy tắc tương ứng. Nếu một toán hạng là `long`, `float` hoặc `double`, kết quả thường được nâng theo kiểu lớn hơn trong thứ tự binary numeric promotion. Quy tắc cụ thể còn phụ thuộc loại toán tử.

### 3.2. Gán kết hợp có thể gây narrowing

```java
byte value = 127;
value += 1;
System.out.println(value); // -128
```

Gán kết hợp `E1 op= E2` tương đương về mặt giá trị với `E1 = (T) ((E1) op (E2))`, trong đó `T` là kiểu của `E1`, **ngoại trừ `E1` chỉ được đánh giá một lần**. Bởi vậy, `byte += int` có thể ép ngầm về `byte` và tạo kết quả tràn mà lập trình viên không nhận ra.

Trong ngữ cảnh tài chính, số đếm lớn, phiên bản dữ liệu hoặc phép tính quan trọng, hãy kiểm tra miền giá trị và cân nhắc `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact` khi làm việc với `int`/`long`:

```java
try {
    int next = Math.addExact(Integer.MAX_VALUE, 1);
    System.out.println(next);
} catch (ArithmeticException overflow) {
    System.out.println("Tràn miền giá trị int");
}
```

Các phép cộng/trừ/nhân nguyên thủy thông thường **không tự ném lỗi khi tràn số**; chúng cho kết quả tràn theo độ rộng kiểu. Chia số nguyên cho 0 thì ném `ArithmeticException`.

### 3.3. Dấu phẩy động và tiền tệ

```java
System.out.println(0.1 + 0.2 == 0.3); // false (IEEE 754)
```

`float`/`double` dùng biểu diễn dấu phẩy động nhị phân; một số số thập phân không có biểu diễn chính xác. Không dùng `==` cho kết quả phép tính dấu phẩy động nếu bài toán yêu cầu ngưỡng sai số hoặc cách làm tròn rõ ràng.

Với tiền, có thể dùng **đơn vị nguyên nhỏ nhất** (`long` VND nếu miền giá trị phù hợp) hoặc `BigDecimal` với quy tắc làm tròn được xác định:

```java
java.math.BigDecimal price =
        new java.math.BigDecimal("0.10");
java.math.BigDecimal tax =
        new java.math.BigDecimal("0.20");

System.out.println(price.add(tax).toPlainString()); // 0.30
```

Tránh `new BigDecimal(0.1)` nếu muốn biểu diễn chính xác số thập phân `0.1`; ưu tiên constructor từ chuỗi hoặc `BigDecimal.valueOf(double)` khi đầu vào đã là `double` và bạn hiểu ngữ nghĩa chuyển đổi.

## 4. So sánh: `==`, `equals()` và các kiểu giá trị

Với **primitive**, `==` so sánh giá trị sau các quy tắc chuyển đổi số cần thiết:

```java
int a = 42, b = 42;
System.out.println(a == b); // true
```

Với **reference type**, `==` so sánh **hai tham chiếu có trỏ tới cùng một object** hay không:

```java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
```

`new String` tạo các object khác nhau trong ví dụ. Việc so sánh hai literal `"Java" == "Java"` có thể trả `true` nhờ string intern, nhưng **không dùng `==` để kiểm tra nội dung String**.

Để so sánh nội dung có khả năng `null`, dùng:

```java
java.util.Objects.equals(first, second);
```

`Objects.equals(null, null)` là `true`; `Objects.equals(null, "x")` là `false`. Nếu object tự định nghĩa `equals()`, phải tuân thủ các quy tắc phản xạ, đối xứng, bắc cầu, nhất quán và so với `null` là false. Khi override `equals()`, đồng thời override `hashCode()` sao cho hai object bằng nhau có cùng hash code.

Với mảng:

```java
int[] left = {1, 2};
int[] right = {1, 2};

System.out.println(left == right); // false
System.out.println(java.util.Arrays.equals(left, right)); // true
```

`Arrays.equals` so sánh các phần tử tương ứng của mảng một chiều; mảng lồng nhau có thể cần `Arrays.deepEquals`. `record` tự sinh `equals/hashCode/toString` theo thành phần, nhưng **thành phần là mảng vẫn dùng ngữ nghĩa equals của mảng**; không tự động so sánh sâu nội dung mảng.

Với `BigDecimal`, `equals()` còn xét **scale** còn `compareTo()` so sánh giá trị số:

```java
var x = new java.math.BigDecimal("1.0");
var y = new java.math.BigDecimal("1.00");

System.out.println(x.equals(y));        // false
System.out.println(x.compareTo(y) == 0); // true
```

Lựa chọn cách so sánh phải phù hợp với bài toán: giá trị tiền, định dạng nhập liệu hay tính duy nhất trong collection.

## 5. Logic ngắn mạch, bitwise và toán tử điều kiện

### 5.1. `&&` và `||` có short-circuit

```java
String input = null;

boolean valid = input != null && !input.isBlank();
System.out.println(valid); // false; vế phải không chạy
```

Nếu vế trái của `&&` là false, Java không đánh giá vế phải. Nếu vế trái của `||` là true, Java không đánh giá vế phải. Tính chất này giúp viết guard điều kiện an toàn và tránh công việc không cần thiết.

Ngược lại, `&` và `|` dùng được với boolean nhưng **đánh giá cả hai vế**:

```java
boolean firstCheck = false;
boolean secondCheck = true;

System.out.println(firstCheck && secondCheck); // false
System.out.println(firstCheck & secondCheck);  // false
```

Kết quả có thể giống nhau, nhưng điều kiện bên phải của `&` vẫn được tính. Ví dụ `input != null & !input.isBlank()` sẽ ném `NullPointerException` khi input null. Dùng `&&`/`||` cho điều kiện điều khiển thông thường, và `&`/`|` khi muốn xử lý bit hoặc thực sự muốn đánh giá cả hai vế.

### 5.2. Bitwise và dịch bit

```java
int mask = 0b1010;
mask |= 0b0100;                  // 0b1110
boolean enabled = (mask & 0b0100) != 0; // true

System.out.println(1 << 3);         // 8
System.out.println(-8 >> 1);        // -4: mở rộng bit dấu
System.out.println(-8 >>> 1);       // 2147483644: dịch phải điền 0
System.out.println(1L << 32);       // 4294967296
```

`>>` dịch phải bảo toàn bit dấu; `>>>` dịch phải điền 0. Với `int`, Java chỉ sử dụng **5 bit thấp** của số lượng dịch; với `long`, sử dụng **6 bit thấp**. Vì vậy `1 << 32` cho kết quả `1`, không phải `4294967296`; muốn phép dịch 32 bit trên long cần `1L << 32`.

Không dùng toán tử bitwise như một “cách tối ưu” số học nếu nó làm mất ý nghĩa; JVM/JIT đã có nhiều tối ưu và biểu thức rõ ràng dễ được kiểm chứng hơn.

### 5.3. Toán tử ba ngôi

```java
long goodsTotalVnd = 600_000L;
long deliveryFeeVnd = goodsTotalVnd >= 500_000L
        ? 0L
        : 30_000L;
```

Biểu thức `?:` chọn một trong hai nhánh; nhánh không được chọn sẽ không chạy. Nó phù hợp cho lựa chọn gọn có cùng ý nghĩa kiểu dữ liệu; khi nhiều điều kiện, có side effect hoặc cần xử lý lỗi chi tiết, `if/else` thường dễ đọc hơn.

**Lưu ý kiểu của toán tử ba ngôi:** Java có các quy tắc riêng để quyết định kiểu kết quả theo hai nhánh và ngữ cảnh; đặc biệt việc trộn primitive với wrapper có thể gây **unboxing** và `NullPointerException` trong tình huống khó đoán. Đừng giả định luôn lấy kiểu “chung chung nhất”; khi nhánh có null hoặc kiểu khác nhau, cân nhắc `if/else` rõ ràng.

## 6. `instanceof`, ép kiểu và pattern matching

Với Java 17, có thể dùng **pattern matching cho `instanceof`**:

```java
static int normalizedTextLength(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return text.trim().length();
    }
    return 0;
}
```

Nếu điều kiện `instanceof String text` thành công, biến `text` có kiểu `String` và có hiệu lực trong phạm vi Java chứng minh pattern đã match. Nếu `value == null`, `instanceof` cho `false`, không ném lỗi.

Cách truyền thống:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Cần phân biệt **ép kiểu tham chiếu** (runtime có thể ném `ClassCastException`) với **chuyển đổi số primitive** (có thể mất phần thập phân hoặc tràn miền):

```java
double original = 12.9;
int truncated = (int) original; // 12: bỏ phần thập phân
```

Ép kiểu không phải công cụ “sửa” thiết kế generic: nếu phải cast liên tục giữa các lớp, hãy xem có thể biểu diễn hợp đồng bằng kiểu chính xác hơn hay không.

## 7. Thuộc tính trong Java: field, accessor và property

Trong lập trình hướng đối tượng, “thuộc tính của đối tượng” thường là dữ liệu tạo nên trạng thái của object, nhưng Java cần phân biệt vài khái niệm:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Field (trường)** | `private String email;` | Biến được khai báo trong class, thuộc instance hoặc class |
| **Instance field** | `private boolean active;` | Mỗi object có bản trạng thái riêng |
| **Static field** | `private static int count;` | Giá trị thuộc class, dùng chung cho các instance |
| **Accessor/getter** | `getEmail()`, `isActive()` | Phương thức cho phép đọc trạng thái qua API |
| **Mutator/setter** | `setActive(boolean)` | Phương thức cập nhật trạng thái có thể kèm validation |
| **JavaBeans property** | Property `email` suy từ `getEmail()`/`setEmail(...)` | Quy ước getter/setter được framework và công cụ sử dụng |
| **Record component** | `record User(String email)` | Thành phần record sinh field private final và accessor `email()` |
| **Local variable** | `int total = 0;` trong method | Biến trong phạm vi cục bộ, không phải field của object |

**Java không có cú pháp property khai báo sẵn kiểu C#** như `public string Name { get; set; }`. Từ “property” trong nhiều thư viện Java thường là quy ước được nhận diện qua method, hoặc metadata của framework. Truy cập `user.email` là truy cập field nếu visibility cho phép; nó **không tự gọi** `getEmail()`.

Ví dụ class giữ dữ liệu được đóng gói:

```java
public final class UserProfile {
    private final String email;
    private boolean active;

    public UserProfile(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }
        this.email = email.trim();
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

`email` chỉ được gán lúc tạo; `active` có thể thay đổi. Không phải field nào cũng cần setter. Với nghiệp vụ thật, việc cập nhật trạng thái có thể cần tên hành vi rõ hơn:

```java
public void activate() {
    if (active) {
        return;
    }
    active = true;
}
```

Phương thức có ý nghĩa domain thường dễ bảo vệ bất biến hơn API setter tổng quát. Nếu trạng thái kích hoạt phụ thuộc phê duyệt hoặc quyền truy cập, các kiểm tra đó phải được tổ chức ở ranh giới có trách nhiệm tương ứng.

### 7.1. Quyền truy cập và đóng gói

| Modifier | Có thể truy cập từ đâu? | Hướng áp dụng |
| --- | --- | --- |
| `private` | Bên trong lớp/nhóm nested tương ứng theo quy tắc ngôn ngữ | Field nội bộ, invariant, helper |
| Không ghi modifier (*package-private*) | Cùng package | Thành phần triển khai chỉ dùng trong package |
| `protected` | Cùng package; và trong subclass ở package khác theo quy tắc truy cập `protected` | API mở rộng có chủ đích cho kế thừa |
| `public` | Nơi có thể nhìn thấy kiểu chứa thành viên | API công khai cần ổn định |

Ưu tiên **visibility hẹp nhất vẫn đáp ứng nhu cầu thực**. Việc một getter công khai không có nghĩa getter được phép lộ mật khẩu, token, giá trị nhạy cảm hoặc trạng thái mutable nội bộ.

Nếu field chứa collection mutable, trả trực tiếp field qua getter có thể cho client sửa trái phép dữ liệu:

```java
private final java.util.List<String> tags =
        new java.util.ArrayList<>();

public java.util.List<String> getTags() {
    return java.util.List.copyOf(tags); // snapshot không sửa qua getter
}
```

`List.copyOf` tạo danh sách không sửa được và tách cấu trúc danh sách khỏi nguồn, **không sao chép sâu các phần tử mutable**. Với phần tử là `String` như ví dụ, điều này không gây vấn đề. Nếu phần tử là object có setter, cần cân nhắc immutable value object hoặc defensive copy các phần tử.

### 7.2. `static`, `final`, `var`, `record`

- `static` đánh dấu thành viên ở cấp lớp; `static final` thường dùng cho hằng số. **Không phải mọi `static final` là hằng số compile-time**.
- `final` trên biến/field ngăn **gán lại reference hoặc giá trị sau khi được gán hợp lệ**, nhưng không bảo đảm object tham chiếu tới là bất biến.
- `var` (Java 10+) hỗ trợ suy luận kiểu cho **biến cục bộ có initializer**, một số biến vòng lặp và tham số lambda trong những trường hợp được phép; không dùng để khai báo field hay kiểu trả về phương thức. `var x = null;` không hợp lệ.
- `record` (ổn định từ Java 16) phù hợp cho dữ liệu mang cấu trúc giá trị. Record **không tự tạo bất biến sâu** nếu component chứa mảng/list/object mutable.

```java
final java.util.List<String> names =
        new java.util.ArrayList<>();
names.add("Java"); // Hợp lệ: sửa object mà names trỏ tới

// names = new java.util.ArrayList<>(); // Lỗi: gán lại biến final
```

`volatile` là công cụ về **visibility và thứ tự bộ nhớ giữa các thread**, không khiến những thao tác như `count++` trở thành nguyên tử. Không dùng `volatile` để thay locking hoặc `AtomicInteger` khi cần atomic read-modify-write.

## 8. JavaBeans và record: lựa chọn hợp đồng dữ liệu

### 8.1. Getter/setter theo quy ước

Quy ước JavaBeans thường dùng:

```java
String getName()
void setName(String value)
boolean isEnabled()
```

Các công cụ JavaBeans và nhiều framework có thể suy ra tên property từ tên method. Tuy nhiên, **không phải mọi class có getter/setter đều là một JavaBean đầy đủ theo đặc tả**, vì JavaBeans còn các quy ước khác liên quan đến cơ chế khởi tạo, sự kiện, introspection và khả năng serializable tùy trường hợp.

Setter tùy ý trên entity có thể làm sai bất biến; đừng sinh getter/setter cho mọi field như một quy tắc bắt buộc. Một API `changeEmail(...)` có kiểm tra dữ liệu, trạng thái và quyền có thể tốt hơn setter trống logic.

### 8.2. Record không dùng accessor `getX()` mặc định

```java
record Product(String sku, long unitPriceVnd) {
    Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException("Đơn giá âm");
        }
        sku = sku.trim();
    }
}

Product product = new Product(" P-01 ", 125_000L);
System.out.println(product.sku());          // P-01
System.out.println(product.unitPriceVnd()); // 125000
```

Record sinh accessor `sku()`, `unitPriceVnd()`, chứ không phải `getSku()`, `getUnitPriceVnd()` theo mặc định. Nó cũng tự sinh `equals`, `hashCode`, `toString` theo các component. Quy ước của framework serialization/binding cần được kiểm tra riêng khi dùng record thay cho JavaBean.

### 8.3. Khi nào nên có property mutable?

Một object UI form có thể cần cập nhật dần nhiều trường. Một domain value object thể hiện địa chỉ giao hàng đã hợp lệ thường phù hợp bất biến. Entity của ORM có thể có ràng buộc tạo, hydrate hoặc proxy riêng.

Hãy xác định **ai được phép sửa, sửa lúc nào và điều kiện hợp lệ là gì** trước khi quyết định setter public, builder, constructor, record hoặc phương thức domain chuyên biệt.

## 9. Quy ước đặt tên và tổ chức mã Java

Các quy ước phổ biến trong cộng đồng Java giúp code được hiểu nhất quán; chúng không phải toàn bộ đều là luật compiler.

| Thành phần | Quy ước | Ví dụ |
| --- | --- | --- |
| Package | Chữ thường; thường theo reverse-domain | `com.example.order` |
| Class/record/interface/enum | `UpperCamelCase` | `OrderService`, `Money`, `PaymentStatus` |
| Method và field | `lowerCamelCase` | `calculateTotal()`, `totalPrice` |
| Biến cục bộ | `lowerCamelCase`, tên có nghĩa | `deliveryFeeVnd`, `isExpired` |
| Hằng số `static final` có nghĩa hằng số | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Type parameter generic | Tên ngắn theo vai trò khi dễ hiểu | `T` = Type, `E` = Element, `K` = Key, `V` = Value |
| Tên test | Nêu hành vi hoặc điều kiện | `rejectsNegativePrice` |
| File Java public top-level type | Tên file tương ứng với kiểu public | `OrderService.java` |

Các nguyên tắc đọc mã hữu ích:

1. Một method nên có **tên mô tả hành động**, không chỉ `process()` nếu thiếu ngữ cảnh; với predicate boolean, thường chọn `isActive()`, `hasAccess()`, `canRetry()`.
2. Dùng `@Override` khi override phương thức để compiler giúp phát hiện sai chữ ký.
3. Dùng `final` có chủ đích cho những tham chiếu không nên được gán lại; không giả định chỉ thêm `final` là dữ liệu đã immutable.
4. Khi thể hiện đơn vị đo, ghi vào tên hoặc dùng value object: `timeoutMillis`, `priceVnd` giúp tránh nhầm milliseconds với seconds hoặc tiền tệ khác.
5. Không che giấu lỗi bằng `catch (Exception ignored)`; chỉ xử lý loại lỗi mà tầng hiện tại có trách nhiệm.
6. Giữ class, package, API public đủ nhỏ theo trách nhiệm; không tạo getter/setter chỉ để đạt “đủ tính OOP”.

**Cú pháp có thể được IDE formatter chuẩn hóa**, còn lựa chọn tên phụ thuộc ngôn ngữ nghiệp vụ. Đặt tên rõ ràng có ích hơn việc cực đoan chọn một số lượng ký tự hoặc dòng cố định.

## 10. Chương trình Java 17 kết hợp toán tử và thuộc tính

Lưu toàn bộ ví dụ sau vào file **LanguageMechanicsDemo.java**. Mã chạy với JDK 17+ và không dùng thư viện ngoài.

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Objects;

public class LanguageMechanicsDemo {

    // Giá trị nghiệp vụ bất biến, record có compact constructor.
    public record Product(String sku, long unitPriceVnd) {
        public Product {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("SKU không hợp lệ");
            }
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException("Đơn giá âm");
            }
            sku = sku.trim();
        }
    }

    // Đối tượng có encapsulation và method thay đổi trạng thái rõ nghĩa.
    public static final class CartLine {
        private final Product product;
        private int quantity;

        public CartLine(Product product, int quantity) {
            this.product = Objects.requireNonNull(product, "product");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "Số lượng phải dương");
            }
            this.quantity = quantity;
        }

        public Product getProduct() {
            return product;
        }

        public int getQuantity() {
            return quantity;
        }

        public void increaseQuantity(int delta) {
            if (delta <= 0) {
                throw new IllegalArgumentException(
                        "Giá trị tăng phải dương");
            }
            quantity = Math.addExact(quantity, delta);
        }

        public long goodsTotalVnd() {
            return Math.multiplyExact(
                    product.unitPriceVnd(), (long) quantity);
        }
    }

    public static long checkoutTotalVnd(
            CartLine line, boolean vipCustomer) {
        Objects.requireNonNull(line, "line");
        long goodsTotalVnd = line.goodsTotalVnd();

        // VIP được miễn phí vận chuyển, khách khác miễn khi đủ ngưỡng.
        long shippingFeeVnd =
                vipCustomer || goodsTotalVnd >= 500_000L
                        ? 0L : 30_000L;

        return Math.addExact(goodsTotalVnd, shippingFeeVnd);
    }

    public static String normalizeText(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return text.trim();
        }
        return "";
    }

    public static void main(String[] args) {
        Product product = new Product(" P-01 ", 125_000L);
        CartLine line = new CartLine(product, 2);

        line.increaseQuantity(1);

        System.out.println(product.sku());               // P-01
        System.out.println(line.getQuantity());           // 3
        System.out.println(line.goodsTotalVnd());         // 375000
        System.out.println(checkoutTotalVnd(line, false)); // 405000
        System.out.println(checkoutTotalVnd(line, true));  // 375000

        System.out.println(normalizeText("  Java  "));    // Java

        Product sameValue = new Product("P-01", 125_000L);
        System.out.println(product.equals(sameValue));   // true
        System.out.println(product == sameValue);        // false

        System.out.println(Arrays.equals(
                new int[]{1, 2}, new int[]{1, 2}));      // true

        BigDecimal sum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println(sum.toPlainString());          // 0.3
    }
}
```

Chạy:

```bash
javac LanguageMechanicsDemo.java
java LanguageMechanicsDemo
```

Kết quả:

```text
P-01
3
375000
405000
375000
Java
true
false
true
0.3
```

Ở đây:

- **Toán tử số học** xuất hiện khi tính tiền hàng; `Math.multiplyExact` và `Math.addExact` làm rõ chính sách với số nguyên bị tràn.
- **`||` và `?:`** biểu diễn lựa chọn phí vận chuyển có short-circuit.
- **`instanceof String text`** lọc đầu vào trước khi xử lý chuỗi.
- **Product record** thể hiện value object; hai sản phẩm khác instance nhưng bằng nhau theo nội dung, do đó `equals()` khác `==`.
- **CartLine** đóng gói state mutable và chỉ cho thay đổi số lượng qua `increaseQuantity()` có validation.
- **Accessor** giúp client đọc trạng thái nhưng không sửa trực tiếp `quantity`; quy ước `getQuantity()` khác accessor `product.sku()` của record.

Dùng `long` cho đơn vị VND là giả định của bài. Một ứng dụng thật cần xác định tiền tệ, thuế, giảm giá, làm tròn và miền giá trị; không chuyển máy móc sang `double` khi xử lý tiền.

## 11. Kiểm thử hành vi thay vì kiểm tra mẹo toán tử

Ví dụ test bằng **JUnit Jupiter 5** (đặt vào file **LanguageMechanicsDemoTest.java**; JUnit cần được cấu hình trong dự án):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class LanguageMechanicsDemoTest {

    @Test
    void khachThuongChuaDuNguongPhaiTraPhiGiao() {
        var product =
                new LanguageMechanicsDemo.Product("P01", 125_000L);
        var line =
                new LanguageMechanicsDemo.CartLine(product, 2);

        assertEquals(280_000L,
                LanguageMechanicsDemo.checkoutTotalVnd(line, false));
    }

    @Test
    void khachVipDuocMienPhiGiao() {
        var product =
                new LanguageMechanicsDemo.Product("P01", 125_000L);
        var line =
                new LanguageMechanicsDemo.CartLine(product, 2);

        assertEquals(250_000L,
                LanguageMechanicsDemo.checkoutTotalVnd(line, true));
    }

    @Test
    void khongChoGiamSoLuongBangSoAm() {
        var product =
                new LanguageMechanicsDemo.Product("P01", 125_000L);
        var line =
                new LanguageMechanicsDemo.CartLine(product, 1);

        assertThrows(IllegalArgumentException.class,
                () -> line.increaseQuantity(-1));
        assertEquals(1, line.getQuantity());
    }

    @Test
    void phatHienTranSo() {
        var product =
                new LanguageMechanicsDemo.Product("P01", Long.MAX_VALUE);
        var line =
                new LanguageMechanicsDemo.CartLine(product, 2);

        assertThrows(ArithmeticException.class, line::goodsTotalVnd);
    }

    @Test
    void recordSoSanhTheoGiaTri() {
        var a =
                new LanguageMechanicsDemo.Product(" P01 ", 100L);
        var b =
                new LanguageMechanicsDemo.Product("P01", 100L);

        assertEquals(a, b);
        assertNotSame(a, b);
    }

    @Test
    void patternMatchingXuLyNull() {
        assertEquals("",
                LanguageMechanicsDemo.normalizeText(null));
        assertEquals("Java",
                LanguageMechanicsDemo.normalizeText(" Java "));
    }
}
```

Một bộ kiểm thử tốt chú trọng **ràng buộc đầu vào, miền giá trị, kết quả nghiệp vụ, tình huống biên và exception**. Đừng cố tạo biểu thức cực kỳ rối chỉ để kiểm thử compiler. Khi logic tiền tệ dùng `BigDecimal`, cần kiểm tra rõ phép chia, scale, rounding mode và so sánh giá trị.

## 12. Các lỗi Java thường gặp khi áp dụng quy ước

| Tình huống | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `if (name == "admin")` | So sánh identity, không bảo đảm nội dung | `"admin".equals(name)` hoặc `Objects.equals` |
| `double rate = 5 / 2;` | Chia nguyên rồi mới chuyển thành double | `5.0 / 2` hoặc `(double) 5 / 2` |
| `int result = a * b;` trên giá trị lớn | Có thể overflow âm thầm | `Math.multiplyExact` hoặc kiểu/thuật toán phù hợp |
| `x != null & x.isReady()` | Vế phải chạy dù `x == null` | Dùng `&&` khi cần short-circuit |
| `List` được trả trực tiếp qua getter | Client có thể sửa nội bộ | Snapshot/immutable view và invariant phù hợp |
| Tất cả field đều `public` | Không kiểm soát thay đổi trạng thái | `private`, constructor và method nghiệp vụ |
| Mặc định sinh setter cho mọi trạng thái | Client có thể vượt quy tắc vòng đời | Chỉ expose hành vi được phép |
| Hiểu `final List` là không thể sửa danh sách | `final` chỉ ngăn gán lại reference | Dùng immutable collection/defensive copy |
| `record` có component là `int[]` và tin `equals()` so theo nội dung mảng | Mảng dùng equality theo reference | Thiết kế value object hoặc xử lý equals/hashCode phù hợp |
| `volatile int count; count++` | `++` không atomic | `AtomicInteger`, lock hoặc mô hình đồng bộ phù hợp |
| Đặt tên `timeout` mà không nói đơn vị | Dễ nhầm seconds/millis | `timeoutMillis`, `Duration` |
| Dùng một biểu thức nhiều side effect | Khó theo dõi thứ tự và debug | Tách các bước, đặt biến trung gian có tên rõ |

## 13. Bài tập thực hành

Xây dựng `InvoiceLine` với `unitPriceVnd` và `quantity`, cùng `Invoice` chứa nhiều dòng hóa đơn.

**Yêu cầu:**

1. Dùng `record` hoặc class bất biến để biểu diễn đơn giá và mã hàng; kiểm tra đơn giá không âm, số lượng dương.
2. Viết `goodsTotalVnd()` có kiểm soát overflow. Tính phí vận chuyển theo quy tắc: đơn từ **1.000.000 VND** hoặc thành viên VIP thì miễn phí; ngược lại 25.000 VND.
3. Không cho client thêm phần tử trực tiếp vào collection thuộc `Invoice`. Chọn `List.copyOf` hoặc defensive copy thích hợp.
4. Kiểm tra sự khác nhau giữa `==`, `equals()` cho hai value object bằng nhau nhưng được khởi tạo riêng.
5. Viết điều kiện `String coupon != null && !coupon.isBlank()`; thử giải thích nếu thay `&&` bằng `&` trong trường hợp null.
6. Viết test cho đúng ngưỡng miễn phí, lượng hàng tăng, giá trị 0, overflow, null và dữ liệu không hợp lệ.
7. Review tên: field, method, class, hằng số, đơn vị tiền, tính công khai và tính bất biến có diễn đạt đúng domain không?

**Tiêu chí đạt:** mã biên dịch và chạy trên Java 17+, không dựa vào trùng tham chiếu để so nội dung, không làm mất phần thập phân ngoài chủ đích, tránh overflow âm thầm ở phép tính trọng yếu, dữ liệu nội bộ được đóng gói, và API tuân thủ quy ước Java rõ ràng.

**Ghi nhớ:** toán tử quyết định **biểu thức được tính ra sao**, hệ thống kiểu quyết định **thao tác nào được phép**, còn field/property và quy ước Java quyết định **trạng thái được trình bày và kiểm soát như thế nào**. Hiểu cả ba giúp code OOP vừa đúng hành vi vừa dễ đọc và bảo trì.