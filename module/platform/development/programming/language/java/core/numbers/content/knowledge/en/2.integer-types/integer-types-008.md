# Vì sao `boolean` không phải kiểu số trong Java?

Trong Java, `boolean` là **kiểu dữ liệu nguyên thủy (primitive type) dành riêng cho giá trị logic**: chỉ có hai giá trị `true` và `false`. Nó không thuộc nhóm **kiểu số (numeric types)**, kể cả nhóm **kiểu số nguyên (integral types)**. Vì vậy, Java không hiểu `true` là số `1`, `false` là số `0`, cũng không tự coi một số khác `0` là điều kiện đúng.

## 1. Phân loại kiểu nguyên thủy: vị trí của `boolean`

Java có tám kiểu nguyên thủy, chia theo ý nghĩa và quy tắc ngôn ngữ:

| Nhóm | Kiểu | Giá trị/ý nghĩa |
| --- | --- | --- |
| Số nguyên (*integral*) | `byte`, `short`, `int`, `long` | Các số nguyên có dấu, với các độ rộng lần lượt 8, 16, 32 và 64 bit. |
| Số nguyên (*integral*) | `char` | Giá trị không dấu 16 bit, thường biểu diễn một đơn vị mã UTF-16; có thể tham gia một số phép toán số. |
| Số thực (*floating-point*) | `float`, `double` | Các giá trị dấu phẩy động theo quy tắc IEEE 754 của Java. |
| Logic | `boolean` | Chỉ `true` hoặc `false`; **không phải số**. |

Điểm dễ nhầm: tên nhóm “số nguyên” trong ngữ cảnh *Java Language Specification* có cả `char`, dù ta thường dùng `char` cho ký tự. Ngược lại, `boolean` **không** thuộc nhóm này. Khả năng chứa hai trạng thái không đồng nghĩa với khả năng chứa hai số nguyên.

Ví dụ, `int count = 0;` nói về **số lượng**, còn `boolean empty = true;` nói về **một mệnh đề đúng/sai**. Hai biến có thể liên hệ qua biểu thức `count == 0`, nhưng vẫn có kiểu và phép toán khác nhau.

## 2. Vì sao Java tách `boolean` khỏi số?

**Khác miền giá trị.** Một giá trị số mô tả lượng có thể tính toán, so sánh lớn/nhỏ, cộng, trừ, nhân, chia. Một giá trị `boolean` mô tả kết quả của điều kiện hoặc trạng thái logic. Không có ý nghĩa ngôn ngữ cho `true + 1` hay `false < true`.

**Kiểm tra kiểu ngay khi biên dịch.** Java yêu cầu biểu thức trong `if`, `while` và các điều kiện tương tự có kiểu `boolean` (có thể tự mở hộp từ `Boolean`). Java không có quy tắc “*truthy/falsy*” cho số như một số ngôn ngữ khác. Quy tắc này ngăn những lỗi như vô tình viết `if (count)` khi thật ra cần `if (count > 0)`.

**Tường minh tại ranh giới dữ liệu.** Khi một API hoặc hệ thống cũ quy ước `0`/`1` biểu thị tắt/bật, mã Java cần ánh xạ rõ ràng giữa số và logic. Cách đó khiến ý nghĩa các trường hợp ngoài `0` và `1` phải được quyết định, tránh giả định âm thầm.

Đây là **quy tắc của hệ thống kiểu Java**, không phải kết luận rằng máy tính không thể lưu trạng thái đúng/sai bằng các bit.

## 3. Những gán, ép kiểu và điều kiện nào hợp lệ?

Các câu lệnh sau **không biên dịch được** trong Java (mỗi dòng là ví dụ riêng về lỗi kiểu):

```java
boolean active = 1;        // Lỗi: int không chuyển thành boolean.
int value = true;          // Lỗi: boolean không chuyển thành int.
boolean flag = (boolean) 1; // Lỗi: không tồn tại phép cast int -> boolean.
int n = (int) false;       // Lỗi: không tồn tại phép cast boolean -> int.
if (1) {                   // Lỗi: điều kiện if phải là boolean.
    System.out.println("run");
}
boolean result = true + false; // Lỗi: phép cộng không áp dụng cho boolean.
```

Không có chuyển đổi số `byte`/`short`/`int`/`long`/`float`/`double` ↔ `boolean`, dù dùng gán ngầm, cast tường minh hay *numeric promotion*. **Autoboxing** cũng không biến `boolean` thành `Integer` hoặc `Number`.

Muốn suy ra một trạng thái từ số, hãy viết **một phép so sánh tạo `boolean`**:

```java
int count = 3;
boolean hasItems = count > 0; // true
boolean isZero = count == 0;  // false

if (count > 0) {
    System.out.println("Có phần tử");
}
```

Ở đây, hai toán hạng của `>` và `==` là số, nhưng **kết quả so sánh** là `boolean`. Với cờ có hai trạng thái, dùng `if (hasItems)` thay vì so sánh thừa `if (hasItems == true)`.

Nếu phải biểu diễn logic bằng `0`/`1` để giao tiếp với hệ thống bên ngoài, hãy **mã hóa/giải mã** tường minh:

```java
int encoded = hasItems ? 1 : 0; // boolean -> int theo quy ước của ứng dụng
boolean decoded = encoded == 1; // int -> boolean bằng phép so sánh
```

Hai dòng này dùng toán tử điều kiện và so sánh; **không** phải chuyển kiểu `boolean` ↔ `int`. Quy ước `0`/`1` là do ứng dụng hoặc giao thức đặt ra, không phải giá trị số tự có của `false`/`true`.

## 4. Toán tử được phép: phân biệt logic với số

| Phép toán | Với `boolean` | Với kiểu số |
| --- | --- | --- |
| `!` | Phủ định logic, ví dụ `!true` là `false`. | Không dùng cho số. |
| `&&`, `||` | AND/OR có **đoản mạch** (*short-circuit*). | Không dùng trực tiếp cho hai số. |
| `&`, `\|`, `^` | AND/OR/XOR logic, **luôn đánh giá cả hai vế**. | Là các toán tử theo bit cho các kiểu số nguyên phù hợp. |
| `==`, `!=` | So sánh hai giá trị logic. | So sánh các toán hạng số phù hợp. |
| `+`, `-`, `*`, `/`, `%` | Không áp dụng cho `boolean`. | Các phép toán số. |
| `<`, `<=`, `>`, `>=` | Không áp dụng cho `boolean`. | So sánh thứ tự số, trả về `boolean`. |
| `~`, `<<`, `>>`, `>>>` | Không áp dụng cho `boolean`. | Các toán tử theo bit/dịch bit cho kiểu số nguyên. |

*Chú ý:* Phép `+` trong `"active=" + true` là **nối chuỗi**, không phải phép cộng số trên `boolean`.

Ví dụ về đoản mạch:

```java
int denominator = 0;
boolean canDivide = denominator != 0 && 10 / denominator > 1;
System.out.println(canDivide); // false; vế chia không được đánh giá
```

Nếu thay `&&` bằng `&` trong ví dụ trên, vế phải vẫn được đánh giá và gây `ArithmeticException` do chia cho `0`. Sự khác nhau này xuất phát từ **cách đánh giá toán tử logic**, không liên quan đến chuyển `boolean` thành số.

## 5. JVM có thể dùng 0/1, nhưng ngôn ngữ vẫn xem `boolean` là logic

Ở tầng triển khai, máy ảo Java có thể biểu diễn giá trị logic bằng bit hoặc byte trong bộ nhớ; các lệnh bytecode xử lý biểu thức `boolean` trên *operand stack* thường sử dụng biểu diễn dựa trên `int`. Trình biên dịch có thể phát sinh hằng `0` cho `false` và `1` cho `true` ở tầng bytecode.

Nhưng cần tách ba tầng:

1. **Mã nguồn Java:** quy tắc kiểu chỉ cho phép `true`/`false`, không có cast giữa `boolean` và `int`.
2. **Bytecode/JVM:** biểu diễn và tập lệnh vận hành theo đặc tả JVM; một số hoạt động trên boolean dựa vào lệnh số nguyên.
3. **Bộ nhớ/hệ điều hành/hệ thống bên ngoài:** cách đóng gói bit, byte hay `0`/`1` có thể tùy triển khai hoặc giao thức.

Không suy ra từ bytecode rằng `boolean` “thực chất là `int`” trong Java. Cũng **không được giả định** mọi biến `boolean` chiếm đúng 1 bit hay 1 byte trong bộ nhớ: Java không định nghĩa kích thước lưu trữ cố định của `boolean` như đối với độ rộng giá trị của các kiểu số nguyên.

Giá trị mặc định của **trường** kiểu `boolean` và phần tử của `boolean[]` là `false`. Biến cục bộ không tự được gán giá trị mặc định để có thể đọc tùy ý; trước khi đọc, nó phải được gán chắc chắn (*definite assignment*).

## 6. `Boolean` và `Number` cũng là hai nhánh khác nhau

`boolean` là kiểu nguyên thủy; `java.lang.Boolean` là lớp bọc (*wrapper*) cho nó. `Boolean` **không kế thừa `java.lang.Number`**, trong khi các lớp bọc số như `Integer`, `Long`, `Double` là những lớp con của `Number`.

```java
Boolean boxed = Boolean.TRUE; // Hợp lệ: Boolean chứa giá trị logic.
boolean unboxed = boxed;      // Hợp lệ: tự mở hộp.
Number amount = Integer.valueOf(1); // Hợp lệ.
 // Number wrong = Boolean.TRUE;    // Không biên dịch: Boolean không là Number.
```

`Boolean.parseBoolean("true")` trả về `true` (không phân biệt hoa/thường cho chữ `true`); `Boolean.parseBoolean("1")` trả về `false`. Đây là thao tác đọc **chuỗi theo quy tắc của API**, không phải phép chuyển số `1` sang `true`.

Lưu ý thêm: biến `Boolean` là tham chiếu nên có thể là `null`; tự mở hộp một giá trị `null` sẽ gây `NullPointerException`. Dùng `boolean` nguyên thủy cho cờ hai trạng thái nếu không cần biểu thị trạng thái `null`.

## 7. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`BooleanNumberDemo.java`**:

```java
public class BooleanNumberDemo {
    public static void main(String[] args) {
        int pending = 0;
        boolean hasPending = pending > 0;
        boolean enabled = true;
        boolean shouldRun = enabled && hasPending;

        int flagForLegacyApi = enabled ? 1 : 0;
        boolean fromLegacyApi = decodeZeroOne(flagForLegacyApi);

        System.out.println("hasPending=" + hasPending);
        System.out.println("shouldRun=" + shouldRun);
        System.out.println("flagForLegacyApi=" + flagForLegacyApi);
        System.out.println("fromLegacyApi=" + fromLegacyApi);
    }

    private static boolean decodeZeroOne(int value) {
        if (value != 0 && value != 1) {
            throw new IllegalArgumentException("Flag must be 0 or 1");
        }
        return value == 1;
    }
}
```

Biên dịch và chạy:

```bash
javac BooleanNumberDemo.java
java BooleanNumberDemo
```

Kết quả:

```text
hasPending=false
shouldRun=false
flagForLegacyApi=1
fromLegacyApi=true
```

Đọc lần lượt: `pending > 0` tạo một giá trị logic; `&&` kết hợp hai điều kiện; `enabled ? 1 : 0` mã hóa cờ thành số theo quy ước; `decodeZeroOne` kiểm tra đầu vào đúng miền `{0, 1}` trước khi biến nó thành điều kiện logic bằng `==`. Nếu đầu vào là `2` hoặc `-1`, hàm chủ động báo lỗi thay vì ngầm coi mọi số khác `0` là `true`.

## 8. Những nhầm lẫn cần tránh

- **“Vì boolean chỉ có hai giá trị nên nó là số nguyên 1 bit.”** Sai về loại dữ liệu: nó có hai giá trị logic; kích thước lưu trữ là vấn đề triển khai.
- **“`true` có nghĩa là `1` trong Java.”** Sai ở mã nguồn Java. Một giao thức hay đoạn bytecode có thể dùng `1` để biểu diễn `true`, nhưng điều đó không tạo ra phép chuyển kiểu Java.
- **“Có thể viết `if (n)` vì `n` là số.”** Sai. Hãy phát biểu điều kiện rõ ràng, ví dụ `if (n != 0)` hoặc `if (n > 0)`, tùy ý nghĩa.
- **“Không thể dùng `&`/`\|`/`^` với boolean.”** Sai. Các toán tử này có dạng áp dụng cho boolean, nhưng không đoản mạch như `&&`/`||`.
- **“`Boolean` là một kiểu `Number`.”** Sai. `Boolean` là wrapper của kiểu logic, đứng ngoài hệ phân cấp `Number`.
- **“Chuyển chuỗi `"1"` qua `Boolean.parseBoolean` sẽ được `true`.”** Sai. Phải tự xác định quy ước chuyển đổi hoặc kiểm tra đầu vào.

**Ghi nhớ:** `boolean` dùng để biểu diễn một mệnh đề **đúng/sai**; các kiểu số dùng để biểu diễn **lượng**. Dùng **so sánh** để tạo logic từ số, dùng **quy ước mã hóa tường minh** khi phải chuyển logic sang số cho hệ thống bên ngoài; không dựa vào biểu diễn ở JVM để vượt qua quy tắc kiểu của Java.

Nguồn đặc tả tham khảo: [Java Language Specification, §4.2 (Primitive Types and Values)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2) và [Java Virtual Machine Specification, §2.3.4 (The boolean Type)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.3.4).
