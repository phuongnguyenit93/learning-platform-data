# `&`, `|` và `^` khi áp dụng lên `boolean` — Java 17+

Trong Java, các toán tử `&`, `|` và `^` có thể kết hợp **hai giá trị `boolean`**. Kết quả của chúng cũng có kiểu `boolean`:

- `a & b`: **AND** — true chỉ khi **cả hai** cùng true.
- `a | b`: **OR** — true khi **ít nhất một** toán hạng true.
- `a ^ b`: **XOR** (*exclusive OR*) — true khi **chính xác một** trong hai toán hạng true.

**Điểm cần nhớ nhất:** với các toán hạng boolean, **cả hai vế** của `&`, `|` và `^` đều được đánh giá nếu việc đánh giá vế trái hoàn tất bình thường, **không ngắn mạch** như `&&` và `||`.

~~~java
boolean a = true;
boolean b = false;

System.out.println(a & b); // false.
System.out.println(a | b); // true.
System.out.println(a ^ b); // true.
~~~

Không nhầm dạng một ký tự `&`/`|` với dạng hai ký tự `&&`/`||`. Chúng có thể cho **cùng kết quả logic** nhưng **khác việc thực thi các biểu thức con**, điều rất quan trọng khi có lời gọi phương thức, `null` hoặc ngoại lệ.

## 1. Bảng chân trị đầy đủ

| `a` | `b` | `a & b` (AND) | `a \| b` (OR) | `a ^ b` (XOR) |
| --- | --- | --- | --- | --- |
| false | false | false | false | false |
| false | true | false | true | true |
| true | false | false | true | true |
| true | true | true | true | false |

**Ý nghĩa của XOR:** chỉ **một** điều kiện được phép đúng, không phải “một hoặc cả hai”.

~~~java
boolean hasPassword = true;
boolean hasOneTimeCode = false;
boolean exactlyOneMethod = hasPassword ^ hasOneTimeCode; // true.

boolean bothMethods = true ^ true; // false.
~~~

Với hai toán hạng kiểu boolean, `a ^ b` cho cùng **giá trị** như `a != b`, nhưng `^` giúp thể hiện ý định XOR rõ hơn trong một số tình huống. Nó **không** có nghĩa phép lũy thừa. Java không dùng `^` để tính `2^3 = 8`; phép lũy thừa số thực có thể dùng `Math.pow(2, 3)`.

## 2. Chương trình Java 17+ chạy trực tiếp bằng CLI

Tạo file UTF-8 tên **`EagerBooleanOperatorsDemo.java`**:

~~~java
public class EagerBooleanOperatorsDemo {
    static boolean mark(String label, boolean value) {
        System.out.println("eval=" + label);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("== truth table ==");
        System.out.println("FF=" + (false & false)
                + "," + (false | false) + "," + (false ^ false));
        System.out.println("FT=" + (false & true)
                + "," + (false | true) + "," + (false ^ true));
        System.out.println("TF=" + (true & false)
                + "," + (true | false) + "," + (true ^ false));
        System.out.println("TT=" + (true & true)
                + "," + (true | true) + "," + (true ^ true));

        System.out.println("== eager evaluation ==");
        boolean eagerAnd = mark("and-left", false)
                & mark("and-right", true);
        System.out.println("eagerAnd=" + eagerAnd);

        boolean eagerOr = mark("or-left", true)
                | mark("or-right", false);
        System.out.println("eagerOr=" + eagerOr);

        boolean xor = mark("xor-left", true)
                ^ mark("xor-right", false);
        System.out.println("xor=" + xor);

        System.out.println("== short circuit ==");
        boolean shortAnd = mark("short-and-left", false)
                && mark("short-and-skipped", true);
        System.out.println("shortAnd=" + shortAnd);

        boolean shortOr = mark("short-or-left", true)
                || mark("short-or-skipped", false);
        System.out.println("shortOr=" + shortOr);

        System.out.println("== precedence ==");
        boolean p = true;
        boolean q = false;
        boolean r = false;
        System.out.println("ungrouped=" + (p | q & r));
        System.out.println("grouped=" + ((p | q) & r));
        System.out.println("notBeforeAnd=" + (!q & p));

        System.out.println("== guard conditions ==");
        String text = null;
        boolean safeText = text != null && !text.isBlank();
        System.out.println("safeText=" + safeText);
        try {
            boolean unsafeText = text != null & !text.isBlank();
            System.out.println("unexpectedText=" + unsafeText);
        } catch (NullPointerException ex) {
            System.out.println("eagerNull=NullPointerException");
        }

        int divisor = 0;
        boolean safeDivide = divisor == 0 || 12 / divisor > 3;
        System.out.println("safeDivide=" + safeDivide);
        try {
            boolean unsafeDivide = divisor == 0 | 12 / divisor > 3;
            System.out.println("unexpectedDivide=" + unsafeDivide);
        } catch (ArithmeticException ex) {
            System.out.println("eagerDivide=ArithmeticException");
        }

        System.out.println("== wrappers and toggle ==");
        Boolean missing = null;
        try {
            boolean unused = true ^ missing;
            System.out.println("unexpectedWrapper=" + unused);
        } catch (NullPointerException ex) {
            System.out.println("xorNull=NullPointerException");
        }

        boolean enabled = false;
        enabled ^= true;
        System.out.println("toggleOne=" + enabled);
        enabled ^= true;
        System.out.println("toggleTwo=" + enabled);
        System.out.println("xorVsNotEqual="
                + ((true ^ false) == (true != false)));

        System.out.println("integerBitwiseXor="
                + (0b1010 ^ 0b1100));
    }
}
~~~

Chạy trên **JDK 17 trở lên** trong PowerShell (Windows) hoặc Bash (Linux/macOS), tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 EagerBooleanOperatorsDemo.java
java EagerBooleanOperatorsDemo
~~~

**Exact expected stdout** của riêng lệnh `java EagerBooleanOperatorsDemo`:

~~~text
== truth table ==
FF=false,false,false
FT=false,true,true
TF=false,true,true
TT=true,true,false
== eager evaluation ==
eval=and-left
eval=and-right
eagerAnd=false
eval=or-left
eval=or-right
eagerOr=true
eval=xor-left
eval=xor-right
xor=true
== short circuit ==
eval=short-and-left
shortAnd=false
eval=short-or-left
shortOr=true
== precedence ==
ungrouped=true
grouped=false
notBeforeAnd=true
== guard conditions ==
safeText=false
eagerNull=NullPointerException
safeDivide=true
eagerDivide=ArithmeticException
== wrappers and toggle ==
xorNull=NullPointerException
toggleOne=true
toggleTwo=false
xorVsNotEqual=true
integerBitwiseXor=6
~~~

Các lệnh `java -version` và `javac -version` hiển thị phiên bản của máy, không thuộc khối expected stdout cố định. Phương thức `mark` chỉ giúp quan sát thứ tự đánh giá; trong mã thực tế, hãy tránh giấu tác dụng phụ vào điều kiện.

## 3. `&` và `&&`: cùng AND, khác cách đánh giá

Hai biểu thức đều cho kết quả AND trên boolean:

~~~java
boolean a = false;
boolean b = true;

System.out.println(a & b);  // false.
System.out.println(a && b); // false.
~~~

Sự khác biệt là **có đánh giá toán hạng phải hay không**.

~~~java
boolean eager = mark("L", false) & mark("R", true);
// In eval=L, sau do eval=R; eager=false.

boolean shortCircuit = mark("L", false) && mark("R", true);
// Chi in eval=L; shortCircuit=false.
~~~

Với `&`, nếu biểu thức trái hoàn tất bình thường, Java vẫn đánh giá biểu thức phải ngay cả khi giá trị trái là false. Với `&&`, khi vế trái false thì vế phải không chạy.

Điều này có thể làm khác **nhật ký**, **trạng thái**, **lời gọi API** hoặc **ngoại lệ**, dù kết quả boolean cuối cùng giống nhau.

## 4. `|` và `||`: cùng OR, khác ngắn mạch

~~~java
boolean eager = mark("L", true) | mark("R", false);
// In ca eval=L va eval=R, eager=true.

boolean shortCircuit = mark("L", true) || mark("R", false);
// Chi in eval=L, shortCircuit=true.
~~~

Với `|`, toán hạng phải vẫn được đánh giá khi vế trái true. Với `||`, vế trái true đủ quyết định kết quả nên vế phải được bỏ qua.

| Điều kiện vế trái | `a & b` | `a && b` | `a \| b` | `a || b` |
| --- | --- | --- | --- | --- |
| `a == false` | Đánh giá `b` | Bỏ qua `b` | Đánh giá `b` | Đánh giá `b` |
| `a == true` | Đánh giá `b` | Đánh giá `b` | Đánh giá `b` | Bỏ qua `b` |

**Mặc định**, nên dùng `&&`/`||` cho điều kiện thường gặp, nhất là điều kiện gác cổng. Chỉ chọn `&`/`|` trên boolean khi việc đánh giá **cả hai** thật sự cần thiết và đã được cân nhắc rõ ràng.

## 5. `^`: XOR và hai vế luôn được đánh giá

Với boolean, `a ^ b` đúng khi đúng **chính xác một** trong hai điều kiện. Không có dạng toán tử Java `^^`.

~~~java
System.out.println(false ^ false); // false.
System.out.println(false ^ true);  // true.
System.out.println(true ^ false);  // true.
System.out.println(true ^ true);   // false.
~~~

`^` luôn đánh giá cả hai toán hạng nếu vế trái hoàn thành bình thường:

~~~java
boolean different = mark("first", true) ^ mark("second", false);
// In eval=first, eval=second; different=true.
~~~

Ứng dụng điển hình là kiểm tra **đúng một lựa chọn**:

~~~java
boolean choseEmail = true;
boolean chosePhone = false;
boolean exactlyOne = choseEmail ^ chosePhone; // true.
~~~

Nếu muốn cho phép **ít nhất một** lựa chọn, dùng `||` thay vì `^`. Nếu muốn **cả hai** cùng có, dùng `&&`.

Với hai giá trị boolean, `a ^ b` và `a != b` có cùng kết quả. Khi các toán hạng có tác dụng phụ, cả `^` lẫn `!=` đều đánh giá hai toán hạng theo các quy tắc của Java. Tuy nhiên, cách biểu đạt `^` có thể giúp người đọc nhận ra rõ hơn khái niệm “đúng một”.

## 6. Không dùng `&` hoặc `|` làm null guard

Vì đánh giá vế phải luôn được thực hiện, dùng `&` có thể tạo `NullPointerException`:

~~~java
String name = null;

// An toan: vế phải bị bỏ qua nếu name null.
boolean safe = name != null && !name.isBlank();

// Nguy hiem:
// boolean wrong = name != null & !name.isBlank();
// Ném NullPointerException.
~~~

Tương tự với chia số nguyên cho 0:

~~~java
int divisor = 0;

// An toan: vế trái true làm || bỏ qua phép chia.
boolean safe = divisor == 0 || 12 / divisor > 3;

// Nguy hiem:
// boolean wrong = divisor == 0 | 12 / divisor > 3;
// Ném ArithmeticException.
~~~

Đây là khác biệt về **luồng đánh giá**, không phải về “độ chính xác của bảng chân trị”. Với toán hạng thứ hai có thể ném ngoại lệ, `&`/`|` có thể không trả kết quả boolean bình thường.

**Chú ý concurrency:** một guard đọc giá trị và một biểu thức truy cập cùng dữ liệu dùng chung có thể chịu ảnh hưởng từ luồng khác. Bản thân `&&` không thay thế cơ chế đồng bộ hoặc snapshot nếu chương trình có dữ liệu thay đổi đồng thời.

## 7. `Boolean` wrapper và unboxing

Ba toán tử nhận biểu thức `boolean` nguyên thủy hoặc `Boolean` có thể **unbox** về `boolean`.

~~~java
Boolean enabled = Boolean.TRUE;
boolean result = enabled ^ false; // true.
~~~

Nhưng nếu wrapper chứa `null`, unboxing gây `NullPointerException`:

~~~java
Boolean missing = null;
// boolean result = true ^ missing; // Ném NullPointerException.
~~~

Đừng ngầm coi `Boolean null` là false. Cần xác định chính sách nghiệp vụ; khi muốn coi chỉ `Boolean.TRUE` là đúng:

~~~java
Boolean flag = null;
boolean isEnabled = Boolean.TRUE.equals(flag); // false.
~~~

Với `&&`/`||`, vế phải chứa wrapper null **có thể được bỏ qua nhờ ngắn mạch**, nhưng nếu đến lượt đánh giá và unbox null thì vẫn ném ngoại lệ.

## 8. Độ ưu tiên và dấu ngoặc

Với các toán tử logic liên quan, thứ tự ưu tiên từ cao xuống thấp gồm:

| Độ ưu tiên tương đối | Toán tử |
| --- | --- |
| Cao | `!` |
| Sau đó | `&` |
| Sau đó | `^` |
| Sau đó | `\|` |
| Sau đó | `&&` |
| Thấp hơn | `||` |

Do `&` ưu tiên hơn `|`:

~~~java
boolean p = true;
boolean q = false;
boolean r = false;

boolean ungrouped = p | q & r;   // true: p | (q & r).
boolean grouped = (p | q) & r;   // false.
~~~

**Độ ưu tiên quyết định cách nhóm**, không đảo thứ tự đánh giá toán hạng. Những biểu thức có nhiều toán tử nên dùng ngoặc để thể hiện rõ ý thay vì buộc người đọc ghi nhớ mọi mức ưu tiên.

Ví dụ `!a & b` được nhóm `(!a) & b`, còn `!(a & b)` phủ định toàn bộ kết quả AND — đây là hai điều kiện khác nhau.

## 9. Phân biệt phép logic boolean với bitwise trên số nguyên

`&`, `|`, `^` còn được Java hỗ trợ trên **các kiểu số nguyên** để thao tác từng bit. Compiler quyết định phép toán nào dựa vào **kiểu toán hạng**.

~~~java
boolean logical = true ^ false; // true, XOR boolean.
int bitwise = 0b1010 ^ 0b1100;  // 0b0110 = 6.
~~~

Nếu toán hạng là hai số nguyên, `^` thực hiện XOR bit; nếu là hai boolean, `^` thực hiện XOR logic. Với toán hạng boolean, `&` và `|` không đổi thành phép số nguyên và trả `boolean`.

- `&&` và `||` **chỉ áp dụng cho boolean**.
- `&`, `|`, `^` áp dụng cho **boolean hoặc kiểu số nguyên phù hợp**.
- Java không tự đổi số 0 thành false, số khác 0 thành true; vì vậy `1 && 2` và `!0` đều không hợp lệ.
- `^` không phải phép lũy thừa; `Math.pow(...)` là API khác với số thực.

### Gán kết hợp trên boolean

Java còn có các dạng `&=`, `|=`, `^=`. Ví dụ:

~~~java
boolean enabled = false;
enabled ^= true;  // true: toggle.
enabled ^= true;  // false: toggle them lan nua.
~~~

`x ^= true` là một cách đảo `boolean`, nhưng `x = !x` thường rõ ràng hơn khi mục đích chỉ là phủ định trạng thái. Với biểu thức vế trái phức tạp, gán kết hợp có quy tắc đánh giá vế trái một lần; không tự thay mã bằng phép gán hai lần đọc vế trái có tác dụng phụ.

## 10. Bẫy thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`&` và `&&` giống hệt nhau trên boolean.” | Bảng chân trị giống, nhưng `&` **không ngắn mạch** |
| “`|` và `||` đều bỏ qua vế phải khi vế trái true.” | Chỉ `||` bỏ qua |
| “`^` đúng nếu ít nhất một điều kiện true.” | `^` đúng khi **chính xác một** điều kiện true |
| “`^` là lũy thừa số nguyên.” | `^` là XOR boolean/bit |
| “`false & risky()` an toàn vì kết quả đã false.” | `risky()` vẫn được đánh giá |
| “`true | risky()` không cần chạy risky.” | Vế phải vẫn chạy |
| “`Boolean null` tự coi là false.” | Unboxing null gây `NullPointerException` |
| “`a | b & c` luôn nhóm như `(a | b) & c`.” | Thực ra `a | (b & c)` |
| “Dùng `&` thay `&&` giúp null guard.” | Có thể gây lỗi do đánh giá vế phải |

## 11. Bài tập tự kiểm tra

1. `true & false`, `true | false`, `true ^ false` cho gì?  
   *Đáp án:* false, true, true.
2. `true ^ true` và `false ^ false` cho gì?  
   *Đáp án:* Cả hai false.
3. `false & check()` có đánh giá `check()` không?  
   *Đáp án:* Có nếu vế trái hoàn thành bình thường; kết quả AND vẫn false nếu `check()` trả bình thường.
4. `false && check()` có đánh giá `check()` không?  
   *Đáp án:* Không.
5. `true | check()` khác `true || check()` thế nào?  
   *Đáp án:* `|` đánh giá `check()`, `||` bỏ qua.
6. Với `String s = null`, tại sao `s != null & !s.isBlank()` không an toàn?  
   *Đáp án:* `&` vẫn đánh giá lời gọi `isBlank()` trên null.
7. `true | false & false` cho giá trị nào?  
   *Đáp án:* true, vì `&` ưu tiên hơn `|`.
8. `Boolean b = null; boolean x = true ^ b;` có kết quả gì?  
   *Đáp án:* Ném `NullPointerException` khi unbox.
9. `boolean x = false; x ^= true; x ^= true;` cuối cùng `x` bằng gì?  
   *Đáp án:* false.

## Checklist

- [ ] Biết `&` là AND, `|` là OR, `^` là XOR với boolean.
- [ ] Nhớ `^` chỉ true khi **chính xác một** toán hạng true.
- [ ] Hiểu `&`, `|` và `^` **đánh giá cả hai vế**, không ngắn mạch.
- [ ] Phân biệt với `&&` và `||`, đặc biệt trong null guard và exception.
- [ ] Chú ý `Boolean` null có thể ném `NullPointerException` do unboxing.
- [ ] Biết độ ưu tiên `!` rồi `&`, `^`, `|`, `&&`, `||`.
- [ ] Phân biệt toán tử boolean với bitwise trên số nguyên.
- [ ] Không dùng XOR như phép lũy thừa hoặc OR thông thường.

**Kết luận:** Trong biểu thức `boolean` Java, `&`, `|` và `^` lần lượt thực hiện AND, OR, XOR. Điểm cốt lõi là **không ngắn mạch**, khác `&&`/`||`. Chọn đúng toán tử theo **ý nghĩa điều kiện** và **nhu cầu đánh giá vế phải** để tránh những lỗi khó nhận ra với tác dụng phụ, null và ngoại lệ.
