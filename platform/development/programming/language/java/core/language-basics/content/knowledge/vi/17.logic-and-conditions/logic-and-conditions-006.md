# Định luật De Morgan và đơn giản hóa điều kiện trong Java

> **Java core — language-basics / Logic và điều kiện**  
> **Môi trường:** JDK 17+, một file Java độc lập, không cần thư viện ngoài.  
> **Mục tiêu:** Đổi đúng phủ định của AND/OR, đọc bảng chân trị, viết điều kiện rõ ràng hơn mà không làm sai logic hoặc thứ tự đánh giá ngắn mạch.

## 1. Hai định luật De Morgan

Cho hai biểu thức `boolean` là `P` và `Q`:

~~~text
!(P && Q)  tương đương  !P || !Q
!(P || Q)  tương đương  !P && !Q
~~~

**Quy tắc:** Khi đưa dấu phủ định `!` vào trong ngoặc, hãy **đảo AND thành OR hoặc ngược lại**, đồng thời **phủ định từng vế**.

~~~java
boolean p = true;
boolean q = false;

boolean a = !(p && q); // true.
boolean b = !p || !q;  // true: tương đương a.

boolean c = !(p || q); // false.
boolean d = !p && !q;  // false: tương đương c.
~~~

Không được chỉ đảo từng toán hạng mà giữ nguyên toán tử:

~~~java
// SAI về logic:
// !(p && q)  KHÔNG tương đương  !p && !q.
// !(p || q)  KHÔNG tương đương  !p || !q.
~~~

Ví dụ `!(p && q)` có nghĩa **“không phải cả hai cùng đúng”**; tương đương **“ít nhất một vế sai”**, chứ không phải “cả hai đều sai”.

## 2. Bảng chân trị chứng minh

| `P` | `Q` | `!(P AND Q)` | `!P OR !Q` | `!(P OR Q)` | `!P AND !Q` |
| --- | --- | --- | --- | --- | --- |
| false | false | true | true | true | true |
| false | true | true | true | false | false |
| true | false | true | true | false | false |
| true | true | false | false | false | false |

Hai cột của mỗi cặp luôn bằng nhau với mọi tổ hợp `P`/`Q`. Đó là cơ sở để thay biểu thức mà **không đổi kết quả boolean**.

Có thể mở rộng cho nhiều điều kiện:

~~~java
// Phủ định việc cả ba điều kiện đều đúng:
boolean denied = !(p && q && r);
// Tương đương:
boolean denied2 = !p || !q || !r;

// Phủ định việc ít nhất một điều kiện đúng:
boolean none = !(p || q || r);
// Tương đương:
boolean none2 = !p && !q && !r;
~~~

Trong đoạn mở rộng, `p`, `q`, `r` là các biến boolean đã được khai báo. Đừng quên **ngoặc** khi kết hợp với điều kiện khác; `!` có độ ưu tiên cao hơn `&&` và `||`.

## 3. Áp dụng vào điều kiện nghiệp vụ và kiểm tra phạm vi

Ví dụ một người bị **từ chối** khi không đồng thời đủ tuổi và có vé:

~~~java
int age = 20;
boolean hasTicket = false;

boolean denied = !(age >= 18 && hasTicket);
boolean deniedSimplified = age < 18 || !hasTicket;
// Cả hai cùng true ở ví dụ này.
~~~

Đọc câu thứ hai dễ hơn: **chưa đủ tuổi HOẶC không có vé**.

Với `int x`, điều kiện nằm trong khoảng đóng từ 0 đến 100:

~~~java
boolean inRange = x >= 0 && x <= 100;
boolean outOfRange = !(x >= 0 && x <= 100);
boolean simpler = x < 0 || x > 100;
~~~

Khi `x` là kiểu nguyên, `outOfRange` và `simpler` tương đương. Ngược lại, muốn phủ định điều kiện “nằm ngoài khoảng”, áp dụng De Morgan:

~~~java
boolean inRangeAgain = !(x < 0 || x > 100);
// Với int, tương đương x >= 0 && x <= 100.
~~~

**Lưu ý:** Phép biến đổi `!(x >= 0)` thành `x < 0` chỉ luôn tương đương với **kiểu nguyên** hoặc khi bạn đã loại bỏ `NaN` ở kiểu số thực. Xem mục 6.

## 4. Guard với `null` và điều kiện dễ đọc

De Morgan giúp diễn đạt trường hợp dữ liệu không hợp lệ:

~~~java
String name = null;
boolean valid = name != null && !name.isBlank();
boolean invalid = !(name != null && !name.isBlank());

// Đổi theo De Morgan:
boolean invalidSimplified = name == null || name.isBlank();
~~~

Nếu `name == null`, vế phải `name.isBlank()` ở biểu thức cuối **không được chạy** nhờ `||` ngắn mạch. `invalid` và `invalidSimplified` đều true; `valid` false.

Cách viết này vẫn **giữ điều kiện guard đứng trước** thao tác có thể ném `NullPointerException`. Tránh đổi thứ tự thành:

~~~java
// KHÔNG AN TOÀN khi name == null:
// boolean broken = name.isBlank() || name == null;
~~~

Khi thay đổi hoặc rút gọn điều kiện, mục tiêu không chỉ là ít ký tự hơn mà còn là **diễn đạt đúng nghiệp vụ, dễ bảo trì và bảo vệ điều kiện phụ thuộc**.

## 5. Short-circuit và tác dụng phụ khi áp dụng De Morgan

Trong Java, `&&` bỏ qua vế phải nếu vế trái false; `||` bỏ qua vế phải nếu vế trái true. Hai biến đổi De Morgan dưới đây giữ **thứ tự đánh giá P rồi Q** và cùng điều kiện bỏ qua Q:

~~~java
!(P && Q)  →  !P || !Q
!(P || Q)  →  !P && !Q
~~~

Với các biểu thức `P`/`Q` giống hệt nhau ở hai vế và không có thao tác khác chen vào, cả kết quả lẫn việc vế nào được đánh giá đều giữ nguyên theo quy tắc ngắn mạch.

~~~java
StringBuilder log = new StringBuilder();
boolean result = !(mark(log, "F", false)
        && mark(log, "X", true));
// result=true, log="F": không gọi mark(..., "X", ...).
~~~

Dạng viết lại `!mark(log, "F", false) || !mark(log, "X", true)` cũng không gọi nhánh X.

**Không tự ý đổi vị trí, nhân bản hay loại bỏ một biểu thức có tác dụng phụ**: ví dụ `readValue()`, `i++`, một lệnh ghi log hoặc lời gọi cập nhật trạng thái. Những biến đổi đại số khác ngoài De Morgan có thể cho cùng bảng chân trị nhưng khác số lần thực thi biểu thức con.

Ngoài ra, `&` và `|` trên boolean **không short-circuit**. De Morgan cũng có công thức logic cho chúng, nhưng nếu dùng một ký tự thay `&&`/`||` thì có thể khiến vế phải vốn bị bỏ qua lại được chạy.

## 6. Cẩn thận khi đổi dấu toán tử quan hệ với `double`/`float`

Thường thấy những phép biến đổi như:

~~~text
!(x < 10)   →   x >= 10
!(x >= 0)   →   x < 0
~~~

Với **`int`/`long`**, chúng tương đương. Nhưng với `double` hoặc `float`, `NaN` làm phép đổi dấu trực tiếp **không còn tương đương**:

~~~java
double x = Double.NaN;

boolean negatedLess = !(x < 10.0); // true.
boolean greaterOrEqual = x >= 10.0; // false.

boolean negatedRange = !(x >= 0.0 && x <= 100.0); // true.
boolean outsideByComparisons = x < 0.0 || x > 100.0; // false.
~~~

Các phép quan hệ `<`, `<=`, `>`, `>=` với `NaN` đều false, nên phủ định của một phép quan hệ false là true. **Định luật De Morgan vẫn đúng**; điều sai là thay `!(x >= 0)` bằng `x < 0` mà quên `NaN`.

Nếu nghiệp vụ không chấp nhận giá trị không hữu hạn, hãy quy định điều đó rõ ràng:

~~~java
double x = Double.NaN;
boolean valid = Double.isFinite(x) && x >= 0.0 && x <= 100.0;
boolean invalid = !valid;
// Có thể viết De Morgan:
// !Double.isFinite(x) || !(x >= 0.0) || !(x <= 100.0)
~~~

Với `boolean` nullable kiểu `Boolean`, phủ định `!flag` đòi hỏi unboxing, có thể ném `NullPointerException` nếu `flag == null`. Xác định rõ quy tắc xử lý null trước khi rút gọn.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **DeMorganDemo.java**:

~~~java
public final class DeMorganDemo {
    private static boolean mark(
            StringBuilder log, String label, boolean result) {
        log.append(label);
        return result;
    }

    public static void main(String[] args) {
        boolean p = true;
        boolean q = false;
        System.out.println("andNot=" + (!(p && q)));
        System.out.println("andDeMorgan=" + (!p || !q));
        System.out.println("orNot=" + (!(p || q)));
        System.out.println("orDeMorgan=" + (!p && !q));

        boolean allEquivalent = true;
        for (boolean a : new boolean[] {false, true}) {
            for (boolean b : new boolean[] {false, true}) {
                allEquivalent &= (!(a && b) == (!a || !b));
                allEquivalent &= (!(a || b) == (!a && !b));
            }
        }
        System.out.println("truthTableEquivalent=" + allEquivalent);

        int age = 20;
        boolean hasTicket = false;
        System.out.println("denied=" + (!(age >= 18 && hasTicket)));
        System.out.println("deniedSimplified=" + (age < 18 || !hasTicket));

        String name = null;
        System.out.println("nameValid="
                + (name != null && !name.isBlank()));
        System.out.println("nameInvalid="
                + (name == null || name.isBlank()));

        StringBuilder andOriginalLog = new StringBuilder();
        boolean originalAnd = !(mark(andOriginalLog, "F", false)
                && mark(andOriginalLog, "X", true));
        System.out.println("andOriginal=" + originalAnd
                + ",trace=" + andOriginalLog);

        StringBuilder andRewriteLog = new StringBuilder();
        boolean rewrittenAnd = !mark(andRewriteLog, "F", false)
                || !mark(andRewriteLog, "X", true);
        System.out.println("andRewrite=" + rewrittenAnd
                + ",trace=" + andRewriteLog);

        StringBuilder orOriginalLog = new StringBuilder();
        boolean originalOr = !(mark(orOriginalLog, "T", true)
                || mark(orOriginalLog, "Y", false));
        System.out.println("orOriginal=" + originalOr
                + ",trace=" + orOriginalLog);

        StringBuilder orRewriteLog = new StringBuilder();
        boolean rewrittenOr = !mark(orRewriteLog, "T", true)
                && !mark(orRewriteLog, "Y", false);
        System.out.println("orRewrite=" + rewrittenOr
                + ",trace=" + orRewriteLog);

        double nan = Double.NaN;
        System.out.println("nanNotLess=" + (!(nan < 10.0)));
        System.out.println("nanGreaterEqual=" + (nan >= 10.0));
        System.out.println("nanNegatedRange="
                + (!(nan >= 0.0 && nan <= 100.0)));
        System.out.println("nanOutsideComparisons="
                + (nan < 0.0 || nan > 100.0));
    }
}
~~~

Biên dịch và chạy ở thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 DeMorganDemo.java
java DeMorganDemo
~~~

**Expected stdout chính xác:**

~~~text
andNot=true
andDeMorgan=true
orNot=false
orDeMorgan=false
truthTableEquivalent=true
denied=true
deniedSimplified=true
nameValid=false
nameInvalid=true
andOriginal=true,trace=F
andRewrite=true,trace=F
orOriginal=false,trace=T
orRewrite=false,trace=T
nanNotLess=true
nanGreaterEqual=false
nanNegatedRange=true
nanOutsideComparisons=false
~~~

`truthTableEquivalent=true` kiểm tra đủ bốn tổ hợp của hai giá trị boolean. Hai cặp trace chứng minh phép đổi De Morgan **không buộc nhánh bị bỏ qua chạy thêm**. Bốn dòng `nan...` chứng minh cảnh báo về đổi dấu bất đẳng thức với `NaN`.

## 8. Quy trình rút gọn và bài tập

Khi gặp một điều kiện nhiều phủ định, hãy làm theo thứ tự:

1. **Nhận diện nhóm trong ngoặc**: `!(P && Q)` hay `!(P || Q)`?
2. **Đảo phép nối** (`&&` ↔ `||`) và **phủ định mỗi toán hạng**.
3. **Đọc lại bằng lời**: “không đồng thời” → “ít nhất một điều kiện không đúng”.
4. **Giữ guard đúng vị trí** và không thay đổi thứ tự/ số lần gọi biểu thức có side effect.
5. **Kiểm tra kiểu và dữ liệu đặc biệt**, nhất là `double NaN`, `Boolean null`, và các ranh giới 0, min, max.

| Dạng ban đầu | Dạng theo De Morgan |
| --- | --- |
| `!(a && b)` | `!a \|\| !b` |
| `!(a \|\| b)` | `!a && !b` |
| `!(x >= 0 && x <= 10)` | `!(x >= 0) \|\| !(x <= 10)` |
| `!(obj != null && obj.ready())` | `obj == null \|\| !obj.ready()` |

**Bài 1.** Viết lại `!(hasAccount && isActive)` bằng OR và hai phủ định; đọc nghĩa bằng tiếng Việt.

**Bài 2.** Viết lại `!(isWeekend || isHoliday)` bằng AND; lập bảng chân trị nhỏ để kiểm chứng.

**Bài 3.** Cho `int x = -1`, so sánh `!(x >= 0 && x <= 10)` với `x < 0 || x > 10`. Hai biểu thức có tương đương khi `x` thuộc kiểu `int` không?

**Bài 4.** Cho `String name = null`. Vì sao `name == null || name.isBlank()` không ném ngoại lệ? Viết lại theo dạng phủ định của một AND.

**Bài 5.** Vì sao với `double x = Double.NaN`, `!(x < 10)` khác `x >= 10`? Sự khác biệt đó có phủ định định luật De Morgan không?

### Ghi nhớ

**De Morgan:** `!(P && Q) == (!P || !Q)` và `!(P || Q) == (!P && !Q)`. Muốn đẩy `!` vào trong ngoặc, phải **đổi AND ↔ OR** và **phủ định từng điều kiện**. Với Java, ưu tiên dễ đọc, giữ short-circuit an toàn và chú ý `NaN` trước khi đổi dấu quan hệ.
