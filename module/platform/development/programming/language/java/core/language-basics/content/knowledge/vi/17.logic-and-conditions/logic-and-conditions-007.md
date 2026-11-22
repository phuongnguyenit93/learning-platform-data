# Toán tử ba ngôi `?:` và chỉ đánh giá nhánh được chọn — Java 17+

**Toán tử điều kiện `?:`** (*conditional operator*, thường gọi là *toán tử ba ngôi*) chọn **một trong hai biểu thức kết quả** dựa trên giá trị của một điều kiện `boolean`.

~~~java
int score = 85;
String level = score >= 80 ? "Tốt" : "Cần cải thiện";
// level = "Tốt".
~~~

Cú pháp:

~~~text
condition ? expressionIfTrue : expressionIfFalse
    (1)            (2)                 (3)
~~~

- **(1) Điều kiện** được đánh giá trước, phải có kiểu `boolean` hoặc `Boolean` có thể unbox.
- **(2) Nhánh true** chỉ được đánh giá khi điều kiện trả true.
- **(3) Nhánh false** chỉ được đánh giá khi điều kiện trả false.
- **Nhánh không được chọn KHÔNG chạy**: không gọi phương thức, không phát sinh tác dụng phụ và không ném ngoại lệ từ nhánh đó.

Ví dụ `boolean premium = true; int fee = premium ? 0 : 30_000;` làm `fee` nhận 0 mà không cần một khối `if/else` dài.

## 1. Quy tắc đánh giá và bảng kết quả

| Điều kiện | Nhánh được đánh giá | Nhánh bị bỏ qua | Giá trị toàn biểu thức |
| --- | --- | --- | --- |
| `true` | Sau dấu `?` | Sau dấu `:` | Giá trị của nhánh true |
| `false` | Sau dấu `:` | Sau dấu `?` | Giá trị của nhánh false |
| `Boolean null` | Không có | Cả hai | Ném `NullPointerException` khi unbox điều kiện |
| Điều kiện tự ném ngoại lệ | Không có | Cả hai | Biểu thức kết thúc đột ngột theo ngoại lệ |

Giản đồ luồng:

~~~mermaid
flowchart TD
    A["Đánh giá condition"] --> B{"Điều kiện true?"}
    B -- "Có" --> C["Chỉ đánh giá nhánh sau ?"]
    B -- "Không" --> D["Chỉ đánh giá nhánh sau :"]
    C --> E["Giá trị biểu thức ?:"]
    D --> E
~~~

**Khác biệt quan trọng với lời gọi phương thức:** `choose(condition, positive(), negative())` sẽ đánh giá **cả hai đối số** `positive()` và `negative()` trước khi gọi phương thức `choose`. Trong khi đó, `condition ? positive() : negative()` chỉ đánh giá **một** trong hai biểu thức nhánh.

## 2. Demo Java 17+ độc lập và có expected stdout

Tạo file UTF-8 tên **`TernaryBranchDemo.java`**:

~~~java
public class TernaryBranchDemo {
    static boolean test(String label, boolean result) {
        System.out.println("test=" + label);
        return result;
    }

    static int mark(String label, int value) {
        System.out.println("eval=" + label);
        return value;
    }

    static int fail() {
        System.out.println("eval=failing");
        throw new IllegalStateException("boom");
    }

    public static void main(String[] args) {
        boolean premium = true;
        int fee = premium ? 0 : 30_000;
        System.out.println("fee=" + fee);

        boolean accepted = false;
        String status = accepted ? "accepted" : "rejected";
        System.out.println("status=" + status);

        System.out.println("== selected branch ==");
        int first = test("condition-true", true)
                ? mark("true-branch", 10)
                : mark("skipped-false-branch", 20);
        System.out.println("first=" + first);

        int second = test("condition-false", false)
                ? mark("skipped-true-branch", 30)
                : mark("false-branch", 40);
        System.out.println("second=" + second);

        System.out.println("== exception behavior ==");
        int safeTrue = true ? mark("safe-true", 5) : fail();
        System.out.println("safeTrue=" + safeTrue);

        int safeFalse = false ? fail() : mark("safe-false", 6);
        System.out.println("safeFalse=" + safeFalse);

        try {
            int unused = true ? fail() : mark("never", 99);
            System.out.println("unexpected=" + unused);
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        System.out.println("== types and null ==");
        var mixedNumeric = true ? 1 : 2.5;
        System.out.println("mixedNumeric=" + mixedNumeric);

        String optionalText = false ? "text" : null;
        System.out.println("nullResult=" + (optionalText == null));

        Integer missingNumber = null;
        int safeNumber = true ? 7 : missingNumber;
        System.out.println("safeNumber=" + safeNumber);

        Boolean missingCondition = null;
        try {
            String unexpected = missingCondition ? "yes" : "no";
            System.out.println("unexpected=" + unexpected);
        } catch (NullPointerException ex) {
            System.out.println("nullCondition=NullPointerException");
        }

        System.out.println("== nesting and state ==");
        boolean mainRoute = false;
        boolean backupRoute = true;
        String route = mainRoute
                ? "main"
                : backupRoute ? "backup" : "off";
        System.out.println("route=" + route);

        int counter = 0;
        int choice = (++counter == 1) ? 8 : 9;
        System.out.println("choice=" + choice + ",counter=" + counter);

        int visits = 0;
        int onlyOne = false
                ? (visits += 10)
                : (visits += 1);
        System.out.println("onlyOne=" + onlyOne + ",visits=" + visits);

        double nan = Double.NaN;
        String nanResult = nan > 0.0 ? "positive" : "not-positive";
        System.out.println("nanResult=" + nanResult);

        System.out.println("== grouping ==");
        int grouped = (true ? 2 : 3) + 4;
        System.out.println("grouped=" + grouped);
        boolean allowed = true || false;
        String access = allowed ? "allow" : "deny";
        System.out.println("access=" + access);
    }
}
~~~

Yêu cầu **JDK 17 trở lên**; mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 TernaryBranchDemo.java
java TernaryBranchDemo
~~~

**Exact expected stdout** từ riêng lệnh `java TernaryBranchDemo`:

~~~text
fee=0
status=rejected
== selected branch ==
test=condition-true
eval=true-branch
first=10
test=condition-false
eval=false-branch
second=40
== exception behavior ==
eval=safe-true
safeTrue=5
eval=safe-false
safeFalse=6
eval=failing
caught=boom
== types and null ==
mixedNumeric=1.0
nullResult=true
safeNumber=7
nullCondition=NullPointerException
== nesting and state ==
route=backup
choice=8,counter=1
onlyOne=1,visits=1
nanResult=not-positive
== grouping ==
grouped=6
access=allow
~~~

Hai lệnh `java -version` và `javac -version` cho đầu ra phụ thuộc máy, không thuộc khối stdout cố định. Ví dụ này được rà soát theo ngữ nghĩa Java 17; có thể dùng các lệnh trên để tự biên dịch và đối chiếu.

## 3. Vì sao chỉ một nhánh được đánh giá?

~~~java
int value = true ? mark("YES", 1) : mark("NO", 2);
~~~

Khi điều kiện true, chương trình chỉ gọi `mark("YES", 1)`, lấy giá trị 1 rồi hoàn tất. Không có lời gọi `mark("NO", 2)`.

Điều này đặc biệt quan trọng với **tác dụng phụ**:

~~~java
int count = 0;
int value = false ? (count += 10) : (count += 1);
// value = 1, count = 1; nhánh +10 hoàn toàn không chạy.
~~~

Và với **ngoại lệ**:

~~~java
int result = true ? 5 : (10 / 0);
// Phép chia ở nhánh không được chọn không được đánh giá.
~~~

Để thể hiện an toàn tại thời điểm chạy, biểu thức chia ở ví dụ trên có thể được thay bằng phép chia với biến mẫu số bằng 0; Java vẫn bỏ qua nhánh đó. Nếu **nhánh được chọn** ném ngoại lệ, toàn biểu thức `?:` kết thúc đột ngột và không sinh giá trị bình thường. Nếu **chính điều kiện** ném ngoại lệ, cả hai nhánh đều chưa được đánh giá.

Đừng dựa vào nhánh bị bỏ qua để thực hiện công việc bắt buộc. Nếu một thao tác phải chạy bất kể điều kiện, hãy đặt nó thành câu lệnh riêng **trước hoặc sau** biểu thức.

## 4. Cả hai nhánh ảnh hưởng đến kiểu kết quả

Dù chỉ một nhánh chạy, **compiler vẫn kiểm tra cả hai nhánh để xác định kiểu** của `?:`. Khi trộn giá trị số, nhánh được chọn có thể được chuyển sang kiểu chung:

~~~java
var mixed = true ? 1 : 2.5;       // double, giá trị 1.0
String note = false ? "text" : null; // tham chiếu null
Integer missing = null;
int safe = true ? 7 : missing;    // 7; không unbox nhánh bỏ qua
~~~

Nếu chọn nhánh `Integer` đang null trong cặp biểu thức số `int`/`Integer`, việc unbox có thể gây `NullPointerException`; điều kiện `Boolean` null cũng lỗi ngay khi chọn nhánh. Với các nhánh tham chiếu, kiểu đích của phép gán đôi khi còn ảnh hưởng đến kiểm tra kiểu. Những quy tắc nâng kiểu, hằng `byte`/`short`, boxing và target typing được phân tích có ví dụ riêng trong bài **Kiểu kết quả của biểu thức điều kiện và chuyển kiểu có thể xảy ra**.

## 5. Độ ưu tiên, tính kết hợp và ternary lồng nhau

`?:` có độ ưu tiên **thấp hơn** nhiều toán tử số học, so sánh và logic `&&`/`||`, nhưng **cao hơn** phép gán `=`.

~~~java
int score = 80;
String rank = score >= 75 && score < 90 ? "good" : "other";
// Dieu kien: (score >= 75 && score < 90).
~~~

Dấu ngoặc thường làm mã rõ ý hơn:

~~~java
String rank = (score >= 75 && score < 90)
        ? "good" : "other";
~~~

**Toán tử điều kiện kết hợp từ phải sang trái** (*right-associative*) trong biểu thức lồng:

~~~java
String route = mainRoute ? "main"
        : backupRoute ? "backup" : "off";
~~~

Nó được nhóm tương đương:

~~~java
String route = mainRoute
        ? "main"
        : (backupRoute ? "backup" : "off");
~~~

Khi `mainRoute` false mới đánh giá điều kiện `backupRoute`. Nếu `mainRoute` true thì toàn bộ phần ternary bên phải bị bỏ qua. Với điều kiện lồng từ ba mức trở lên, **`if/else if/else` thường dễ đọc hơn**.

## 6. Khi nào dùng `?:`, khi nào dùng `if/else`?

Nên dùng `?:` cho **một lựa chọn giá trị ngắn, rõ nghĩa**:

~~~java
int max = a > b ? a : b;
String label = enabled ? "ON" : "OFF";
~~~

Nếu mục đích là nhiều câu lệnh, ghi log, cập nhật trạng thái hoặc bắt exception, dùng `if/else`:

~~~java
String label;
if (enabled) {
    label = "ON";
} else {
    label = "OFF";
}
~~~

Một số khác biệt cần nhớ:

| Đặc điểm | `?:` | `if/else` |
| --- | --- | --- |
| Cấu trúc | **Biểu thức** tạo một giá trị | **Câu lệnh** điều khiển luồng |
| Thích hợp nhất | Chọn một kết quả ngắn | Nhiều thao tác, nhiều nhánh hoặc xử lý lỗi |
| Đánh giá | Chỉ một nhánh được chọn | Chỉ thực hiện khối phù hợp |
| Hai nhánh giá trị | Phải tuân thủ quy tắc kiểu của biểu thức điều kiện | Mỗi nhánh có thể chứa những câu lệnh khác nhau |
| Gọi phương thức `void` ở hai nhánh | Không hợp lệ làm hai biểu thức kết quả của `?:` | Hoàn toàn hợp lệ trong hai khối |

**Sai lầm cú pháp phổ biến:** `?:` không phải là *statement expression* có thể tự đứng thành câu lệnh `condition ? f() : g();`. Nếu chỉ muốn gọi một trong hai phương thức, hãy dùng `if/else`; nếu muốn chọn **giá trị** để gán hoặc truyền cho hàm thì `?:` phù hợp.

## 7. Ngắn mạch của `?:` và `&&`/`||` có gì giống, khác?

Cả ba cơ chế đều có thể **bỏ qua việc đánh giá một phần biểu thức**, nhưng chúng thực hiện nhiệm vụ khác nhau:

| Cấu trúc | Phần được bỏ qua | Kiểu kết quả |
| --- | --- | --- |
| `a && b` | Bỏ `b` khi `a` false | `boolean` |
| `a \|\| b` | Bỏ `b` khi `a` true | `boolean` |
| `cond ? x : y` | Bỏ **một trong hai** nhánh `x`, `y` | Tùy kiểu hai nhánh và ngữ cảnh |

Ví dụ lựa chọn một trong hai phương thức có **giá trị trả về**:

~~~java
int result = valid ? calculateFast() : calculateFallback();
~~~

Khi `valid` true chỉ gọi `calculateFast()`; khi false chỉ gọi `calculateFallback()`. Hai phương thức ở ví dụ mang tính minh họa nên cần được khai báo trong chương trình thực tế; chương trình runnable ở mục 2 dùng các phương thức `mark` và `fail` được định nghĩa đầy đủ.

Không thay bằng `choose(valid, calculateFast(), calculateFallback())` nếu muốn giữ hành vi bỏ qua nhánh: Java đánh giá đối số lời gọi từ trái sang phải, tức **cả hai phương thức tính** có thể chạy trước khi `choose` nhận các giá trị.

## 8. Những lỗi thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “`?:` luôn chạy cả hai nhánh rồi chọn kết quả.” | Chỉ đánh giá nhánh được chọn |
| “Nếu nhánh bị bỏ qua ném exception thì ternary cũng lỗi.” | Nhánh không được chọn không được thực thi |
| “`Boolean null` được hiểu là false.” | Unboxing null ở điều kiện gây `NullPointerException` |
| “Kiểu của ternary luôn là kiểu của nhánh chạy.” | Kiểu quyết định tại compile time, xét hai nhánh và ngữ cảnh |
| “`true ? 1 : 2.5` có kiểu int vì chọn 1.” | Kết quả có kiểu `double`, giá trị `1.0` |
| “`a ? b : c ? d : e` luôn nhóm từ trái.” | `?:` kết hợp từ phải sang trái |
| “Ternary rất dài dễ đọc hơn `if/else`.” | Nhiều mức lồng nhau thường khó kiểm tra |
| “`?:` dùng được cho hai lời gọi `void` như một câu lệnh.” | Không; dùng `if/else` |
| “Tạo hàm `choose(flag, first(), second())` có cùng lazy evaluation.” | Sai; cả hai đối số có thể được đánh giá |

## 9. Bài tập tự kiểm tra

1. `int x = true ? 10 : 20;` cho `x` bằng bao nhiêu?  
   *Đáp án:* 10.
2. `boolean ok = false; String s = ok ? "Y" : "N";` cho chuỗi gì?  
   *Đáp án:* `"N"`.
3. `int n = true ? 5 : (10 / 0);` có thực hiện phép chia không?  
   *Đáp án:* Không; nhánh thứ ba bị bỏ qua.
4. `var x = true ? 1 : 2.5;`, kiểu và giá trị của `x`?  
   *Đáp án:* `double`, `1.0`.
5. `Boolean flag = null; int n = flag ? 1 : 2;` cho kết quả gì?  
   *Đáp án:* Ném `NullPointerException` khi đánh giá điều kiện.
6. `boolean a = false, b = true; String s = a ? "A" : b ? "B" : "C";` cho chuỗi gì?  
   *Đáp án:* `"B"`.
7. Nếu nhánh không được chọn tăng biến đếm, biến đó có thay đổi không?  
   *Đáp án:* Không.
8. Khi phải gọi một trong hai phương thức `void` với logic dài, nên dùng gì?  
   *Đáp án:* `if/else`.

## Checklist

- [ ] Biết cú pháp `condition ? trueExpr : falseExpr` và kiểu điều kiện là boolean.
- [ ] Nhớ **chỉ một nhánh kết quả được đánh giá** sau điều kiện.
- [ ] Biết điều kiện hoặc nhánh được chọn có thể ném ngoại lệ; nhánh không chọn không chạy.
- [ ] Hiểu kiểu toàn biểu thức quyết định khi biên dịch, không phụ thuộc nhánh thực tế lúc chạy.
- [ ] Cẩn thận `Boolean` null và unboxing của nhánh số wrapper.
- [ ] Hiểu `?:` kết hợp từ phải sang trái và nên thêm dấu ngoặc khi lồng.
- [ ] Dùng `?:` cho chọn giá trị ngắn, `if/else` cho luồng xử lý phức tạp.
- [ ] Không nhầm `?:` với một lời gọi hàm nhận cả hai kết quả đã tính.

**Kết luận:** `?:` giúp biểu diễn ngắn gọn lựa chọn giữa hai giá trị, nhưng đặc điểm quan trọng nhất là **chỉ đánh giá nhánh được chọn**. Khi hiểu thêm **kiểu biểu thức**, **null**, **ngoại lệ** và **cách nhóm biểu thức lồng**, bạn có thể dùng ternary đúng và dễ đọc trong Java 17+.
