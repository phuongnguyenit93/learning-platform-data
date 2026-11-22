# So sánh diff trước và sau refactor legacy cast sang pattern matching (Java 21)

## Mục tiêu

Trong chủ đề **Refactor legacy cast**, mục tiêu của việc chuyển từ kiểm tra kiểu rồi ép kiểu thủ công sang **pattern matching** không chỉ là giảm số dòng code. Một bản refactor đạt yêu cầu khi **diff thể hiện rõ thay đổi cấu trúc, đồng thời hành vi quan sát được trước và sau vẫn tương đương** trong phạm vi đã cam kết.

Bài này hướng dẫn đọc unified diff, đối chiếu từng nhánh trước/sau, phát hiện thay đổi về `null`, thứ tự điều kiện, scope và fallback, rồi kiểm chứng bằng chương trình Java 21 chạy được.

Sau bài học, bạn có thể:

- Đọc dấu `-`/`+` trong unified diff và nhận ra phần “thay đổi cú pháp” so với phần có khả năng **đổi logic**.
- So sánh mẫu cổ điển `instanceof` + cast với type pattern và nested record pattern.
- Lập bảng **đường đi điều khiển** để xác nhận nhánh hợp lệ, nhánh thiếu dữ liệu và nhánh mặc định.
- Kiểm chứng behavior parity bằng test có **expected result** độc lập thay vì chỉ tin diff ngắn hơn.
- Review an toàn trước khi đưa refactor vào một codebase nhiều caller.

**Phiên bản:** Type patterns cho `instanceof` chính thức từ Java 16 (JEP 394); **record patterns lồng nhau** chính thức từ Java 21 (JEP 440). Chương trình của bài dùng `javac --release 21`, không cần bật preview.

## 1. Diff của refactor cần trả lời hai câu hỏi khác nhau

**Câu hỏi 1 — code thay đổi gì?** Diff cho biết dòng nào bị xóa và dòng nào được thêm. Nó giúp reviewer thấy cast thủ công biến mất, các biến pattern được bind trực tiếp và các nhánh có thể được sắp lại.

**Câu hỏi 2 — chương trình có đổi hành vi không?** Diff không tự chứng minh được điều này. Một refactor có thể nhìn ngắn hơn nhưng vô tình đổi kết quả khi input `null`, nested record thiếu, điều kiện biên sai, hoặc một nhánh fallback bị bỏ.

Vì vậy, so sánh diff theo hai trục:

| Trục review | Phải xác định |
|---|---|
| **Cấu trúc code** | Kiểm tra kiểu, cast, accessor, biến trung gian và guard được chuyển đổi như thế nào? |
| **Hợp đồng hành vi** | Với cùng input, đầu ra/exception/tác dụng phụ có giữ nguyên không? |
| **Đường đi điều khiển** | Input đi vào nhánh nào trước và sau? Có nhánh nào mới bị bỏ qua? |
| **Các biên** | `null`, kiểu sai, điều kiện đúng tại ngưỡng, dữ liệu thiếu có còn cách xử lý cũ? |
| **Khả năng bảo trì** | Bản mới có rõ ý nghĩa, ít lặp cast, giữ scope dễ hiểu và không che giấu logic không? |

Một thay đổi mang tính cú pháp vẫn cần kiểm chứng, nhất là khi “tiện tay” kết hợp refactor với đổi điều kiện nghiệp vụ.

## 2. Diff tối thiểu: type pattern thay cast

Mẫu legacy:

```java
if (input instanceof String) {
    String text = (String) input;
    return text.trim();
}
return "";
```

Trong Java 16+, có thể viết:

```java
if (input instanceof String text) {
    return text.trim();
}
return "";
```

**Unified diff minh họa:**

```diff
-if (input instanceof String) {
-    String text = (String) input;
+if (input instanceof String text) {
     return text.trim();
 }
 return "";
```

Đây là trường hợp đơn giản: `instanceof String` vẫn phân loại cùng một kiểu và biến `text` chỉ tồn tại khi pattern khớp. Không cần cast tường minh nữa.

Đừng hiểu dấu `-` là code “lỗi” và dấu `+` là “đúng” theo mặc định. Nó chỉ cho biết nội dung trước/sau. Bài toán của reviewer là xác định **tập input có thể đi vào nhánh có thay đổi hay không**.

## 3. Ca thực tế: legacy cast với record lồng nhau

Giả sử dữ liệu ứng dụng có các record sau:

```java
record Reporter(String name, String team) {}
record Order(String id, Reporter reporter, int total) {}
record OrderEvent(Order order) {}
record AuditEvent(String code) {}
```

Ứng dụng minh họa phân loại event như sau:

- `OrderEvent` có `Order` và `Reporter` khác `null`, nhóm `VIP` và `total >= 1000` → `PRIORITY:<id>`.
- Các `OrderEvent` còn lại (kể cả order/reporter thiếu) → `STANDARD`.
- `AuditEvent` → `AUDIT:<code>`.
- Selector khác kiểu hoặc `null` → `IGNORED`.

**Đây là chính sách giả lập**, không đại diện cho một quy tắc đơn hàng thực tế.

### Trước refactor: kiểm tra kiểu, cast và gọi accessor

```java
static String legacy(Object input) {
    if (input instanceof OrderEvent) {
        OrderEvent event = (OrderEvent) input;
        Order order = event.order();
        if (order != null && order.reporter() != null
                && "VIP".equals(order.reporter().team())
                && order.total() >= 1000) {
            return "PRIORITY:" + order.id();
        }
        return "STANDARD";
    }
    if (input instanceof AuditEvent) {
        AuditEvent event = (AuditEvent) input;
        return "AUDIT:" + event.code();
    }
    return "IGNORED";
}
```

Điểm cần ghi nhận trước khi sửa:

1. Root selector không phải `OrderEvent` có thể đi đến nhánh `AuditEvent`.
2. Một khi root là `OrderEvent`, dù component bên trong thiếu, kết quả luôn thuộc nhóm `PRIORITY` hoặc `STANDARD`.
3. Điều kiện `order != null && order.reporter() != null` đảm bảo lời gọi `reporter().team()` không bị dereference khi reporter thiếu.
4. `"VIP".equals(...)` an toàn với `team == null`.
5. Ngưỡng so sánh là `>= 1000`; đúng tại 1000 phải được xem là priority.
6. `AuditEvent` có code null vẫn cho ra chuỗi `AUDIT:null` qua phép nối chuỗi Java.
7. Selector null không thỏa hai câu lệnh `instanceof` và rơi xuống `IGNORED`.

### Sau refactor: nested record pattern và fallback tường minh

```java
static String modern(Object input) {
    if (input instanceof OrderEvent(
            Order(var id, Reporter(var name, var team), var total))
            && "VIP".equals(team) && total >= 1000) {
        return "PRIORITY:" + id;
    }
    if (input instanceof OrderEvent event) {
        return "STANDARD";
    }
    if (input instanceof AuditEvent(var code)) {
        return "AUDIT:" + code;
    }
    return "IGNORED";
}
```

**Điểm quan trọng nhất của bản mới là nhánh fallback `OrderEvent event`.** Nested record pattern chỉ khớp khi cả `Order` và `Reporter` tồn tại. Nếu chỉ giữ nhánh nested `PRIORITY` mà quên fallback `STANDARD`, `OrderEvent(null)` sẽ rơi xuống `IGNORED`, khác bản cũ.

Trong mã này, `name` và `event` được bind nhưng không sử dụng. Điều đó hợp lệ; nếu thiết kế thực tế không cần phân rã sâu, có thể chọn pattern nông hơn. Đừng xóa một tầng bắt buộc trong lúc refactor nếu nó đóng vai trò kiểm tra cấu trúc hoặc `null` của dữ liệu.

## 4. Unified diff: nhìn chính xác điểm bị thay

Phần diff sau mô tả **các đoạn thay đổi tiêu biểu** giữa hai phương thức `legacy` và `modern`. Các dòng bỏ đi có dấu `-`, dòng thêm mới có dấu `+`.

```diff
-    if (input instanceof OrderEvent) {
-        OrderEvent event = (OrderEvent) input;
-        Order order = event.order();
-        if (order != null && order.reporter() != null
-                && "VIP".equals(order.reporter().team())
-                && order.total() >= 1000) {
-            return "PRIORITY:" + order.id();
-        }
+    if (input instanceof OrderEvent(
+            Order(var id, Reporter(var name, var team), var total))
+            && "VIP".equals(team) && total >= 1000) {
+        return "PRIORITY:" + id;
+    }
+    if (input instanceof OrderEvent event) {
         return "STANDARD";
     }
-    if (input instanceof AuditEvent) {
-        AuditEvent event = (AuditEvent) input;
-        return "AUDIT:" + event.code();
+    if (input instanceof AuditEvent(var code)) {
+        return "AUDIT:" + code;
     }
     return "IGNORED";
```

**Không xem đây là patch hoàn chỉnh để áp dụng bằng lệnh `git apply`**: đó là phần thân phương thức được rút ra nhằm giải thích ý nghĩa. Diff chính xác trong repository được tạo từ Git (mục 8).

### Đọc diff theo từng thay đổi

| Vị trí | Trước | Sau | Điều reviewer phải xác nhận |
|---|---|---|---|
| Kiểm tra root | `instanceof OrderEvent` + cast | `instanceof OrderEvent(...)` | Nhánh hẹp hơn có bỏ sót OrderEvent thiếu component không? |
| Truy cập dữ liệu | `event.order()`, `order.reporter()` | `Order(..., Reporter(...), ...)` | Nested record null có còn được xử lý đúng? |
| Điều kiện group | `"VIP".equals(order.reporter().team())` | `"VIP".equals(team)` | Giữ null-safe và cùng phép so sánh? |
| Điều kiện số | `order.total() >= 1000` | `total >= 1000` | Giữ ngưỡng và cả dấu `=`? |
| Tạo kết quả | `order.id()` | `id` | Component được bind cùng nguồn và cùng hành vi với ID null? |
| Fallback OrderEvent | `return "STANDARD"` bên trong block | Nhánh `instanceof OrderEvent` tiếp theo | Có thể đi vào trước nhánh Audit và mặc định không? |
| AuditEvent | Cast thủ công | `AuditEvent(var code)` | Component code null vẫn được bind? |
| Mặc định | `IGNORED` | `IGNORED` | Null root và kiểu khác còn đi tới đây? |

Bảng này giúp tách **cú pháp giảm bớt** khỏi **logic có nguy cơ thay đổi**.

## 5. Ví dụ Java 21 hoàn chỉnh để đối chiếu trước/sau

Lưu toàn bộ chương trình dưới tên **`PatternCastDiffDemo.java`**:

```java
import java.util.Objects;

public class PatternCastDiffDemo {
    record Reporter(String name, String team) {}
    record Order(String id, Reporter reporter, int total) {}
    record OrderEvent(Order order) {}
    record AuditEvent(String code) {}

    static String legacy(Object input) {
        if (input instanceof OrderEvent) {
            OrderEvent event = (OrderEvent) input;
            Order order = event.order();
            if (order != null && order.reporter() != null
                    && "VIP".equals(order.reporter().team())
                    && order.total() >= 1000) {
                return "PRIORITY:" + order.id();
            }
            return "STANDARD";
        }
        if (input instanceof AuditEvent) {
            AuditEvent event = (AuditEvent) input;
            return "AUDIT:" + event.code();
        }
        return "IGNORED";
    }

    static String modern(Object input) {
        if (input instanceof OrderEvent(
                Order(var id, Reporter(var name, var team), var total))
                && "VIP".equals(team) && total >= 1000) {
            return "PRIORITY:" + id;
        }
        if (input instanceof OrderEvent event) {
            return "STANDARD";
        }
        if (input instanceof AuditEvent(var code)) {
            return "AUDIT:" + code;
        }
        return "IGNORED";
    }

    static void check(String label, Object input, String expected) {
        String before = legacy(input);
        String after = modern(input);
        if (!Objects.equals(before, after) || !Objects.equals(expected, after)) {
            throw new AssertionError(label + ": legacy=" + before
                    + ", modern=" + after + ", expected=" + expected);
        }
        System.out.println(label + " => " + after);
    }

    public static void main(String[] args) {
        check("vip boundary", new OrderEvent(new Order(
                "O1", new Reporter("An", "VIP"), 1000)), "PRIORITY:O1");
        check("vip high", new OrderEvent(new Order(
                "O2", new Reporter("Binh", "VIP"), 1500)), "PRIORITY:O2");
        check("not vip", new OrderEvent(new Order(
                "O3", new Reporter("Chi", "REGULAR"), 1500)), "STANDARD");
        check("below threshold", new OrderEvent(new Order(
                "O4", new Reporter("Dung", "VIP"), 999)), "STANDARD");
        check("null reporter", new OrderEvent(new Order(
                "O5", null, 1500)), "STANDARD");
        check("null order", new OrderEvent(null), "STANDARD");
        check("null team", new OrderEvent(new Order(
                "O6", new Reporter("Em", null), 1500)), "STANDARD");
        check("null id", new OrderEvent(new Order(
                null, new Reporter(null, "VIP"), 1500)), "PRIORITY:null");
        check("audit", new AuditEvent("A1"), "AUDIT:A1");
        check("audit null code", new AuditEvent(null), "AUDIT:null");
        check("wrong type", "text", "IGNORED");
        check("root null", null, "IGNORED");
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 PatternCastDiffDemo.java
java PatternCastDiffDemo
```

**Kết quả chạy đã được kiểm chứng:**

```text
vip boundary => PRIORITY:O1
vip high => PRIORITY:O2
not vip => STANDARD
below threshold => STANDARD
null reporter => STANDARD
null order => STANDARD
null team => STANDARD
null id => PRIORITY:null
audit => AUDIT:A1
audit null code => AUDIT:null
wrong type => IGNORED
root null => IGNORED
```

Trong `check(...)`, chương trình **không chỉ** so sánh `legacy(input)` và `modern(input)` mà còn so cả hai với chuỗi kết quả `expected`. Điều này giảm rủi ro “hai phiên bản cùng sai”. Nếu khác nhau, một `AssertionError` được ném và chương trình không thể in đầy đủ kết quả như trên.

Các hàm `legacy` và `modern` ở cùng một lớp chỉ phục vụ **minh họa và regression check**. Trong codebase thật, thường lưu bản cũ ở Git và chỉ giữ một implementation production sau khi refactor được duyệt.

## 6. Bảng đường đi: chứng minh fallback không bị mất

Có thể đọc lại kết quả dưới góc nhìn *control-flow diff*:

| Trường hợp | Đường đi trước | Đường đi sau | Kết quả |
|---|---|---|---|
| VIP và total = 1000 | OrderEvent → guard đúng | Nested OrderEvent → guard đúng | `PRIORITY:O1` |
| VIP và total = 999 | OrderEvent → guard sai → STANDARD | Nested match nhưng `total >= 1000` sai → fallback OrderEvent | `STANDARD` |
| Reporter null | OrderEvent → `reporter != null` sai | Nested `Reporter(...)` không khớp → fallback OrderEvent | `STANDARD` |
| Order null | OrderEvent → `order != null` sai | Nested `Order(...)` không khớp → fallback OrderEvent | `STANDARD` |
| Team null | `"VIP".equals(null)` là false | `team` bind null; so sánh an toàn như cũ | `STANDARD` |
| ID null, đủ điều kiện | `"PRIORITY:" + order.id()` | `"PRIORITY:" + id` | `PRIORITY:null` |
| Audit code null | Cast AuditEvent; ghép code null | `AuditEvent(var code)` bind null | `AUDIT:null` |
| Sai kiểu hoặc root null | Không nhánh nào khớp | Không nhánh nào khớp | `IGNORED` |

Đây là phần **có giá trị nhất** của review: không chỉ đọc patch theo từng dòng mà còn nhìn thấy **phân hoạch input** có được giữ lại hay không.

### Vì sao `AuditEvent(var code)` vẫn nhận code null?

Trong Java 21, record pattern `AuditEvent(...)` cần một **đối tượng AuditEvent khác null**. Nhưng pattern `var code` trực tiếp trên component có thể bind giá trị `null`. Do đó nó giữ được hành vi nối chuỗi với null như phiên bản gọi `event.code()`.

Ngược lại, `OrderEvent(Order(...))` và `Reporter(...)` là **nested record patterns**, không khớp khi chính record ở tầng đó bằng null. Vì vậy một nhánh `OrderEvent` rộng hơn là cần thiết để tái tạo `STANDARD`.

## 7. Các diff “trông sạch” nhưng đổi hành vi

### 7.1. Xóa luôn nhánh fallback

**Sai về ngữ nghĩa đối với yêu cầu ví dụ:**

```java
if (input instanceof OrderEvent(
        Order(var id, Reporter(var name, var team), var total))
        && "VIP".equals(team) && total >= 1000) {
    return "PRIORITY:" + id;
}
return "IGNORED"; // OrderEvent thiếu reporter nay bị IGNORED!
```

Bản cũ trả `STANDARD` cho mọi OrderEvent không đủ điều kiện. Thêm fallback `if (input instanceof OrderEvent ...) return "STANDARD";` là cần thiết. Một patch ngắn hơn nhưng làm mất nhánh không phải refactor bảo toàn hành vi.

### 7.2. Thay so sánh null-safe bằng lời gọi có thể ném lỗi

```java
// Giữ semantics khi team có thể null:
"VIP".equals(team)

// Không tương đương nếu team == null:
team.equals("VIP")
```

Bản thứ hai ném `NullPointerException` với team null. Diff phải được review cả ở những dòng chỉ đổi thứ tự hai toán hạng của `equals`.

### 7.3. Đổi thứ tự đánh giá của boolean expression

```java
// Guard an toàn nếu text có thể null:
text != null && text.startsWith("A")

// Có thể ném lỗi khi text null:
text.startsWith("A") && text != null
```

`&&` và `||` trong Java short-circuit theo thứ tự. Chuyển điều kiện hoặc gọi helper ở vị trí khác có thể làm thay đổi việc một phương thức có được thực thi hay không.

### 7.4. Thay ngưỡng trong lúc refactor

```java
// Trước: bao gồm total = 1000.
total >= 1000

// Sau: bỏ loại total = 1000.
total > 1000
```

Nếu cố tình thay chính sách, hãy tách commit thay đổi hành vi và test của nó, đừng trộn vào commit chuyển cú pháp pattern.

### 7.5. Đổi phạm vi biến và bỏ sót đường đi

Pattern variable chỉ có scope tại vị trí compiler xác định pattern đã khớp:

```java
if (input instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
// Không được tùy ý dùng 'text' ở đây: pattern có thể không khớp.
```

Một bản refactor có thể cần đổi lại cấu trúc control flow, chẳng hạn dùng *guard clause*, nhưng phải đảm bảo nhánh kết thúc sớm và đường đi còn lại giữ đúng kết quả.

### 7.6. Thêm hoặc xóa lượt gọi accessor có side effect

Trong record thông thường, accessor do compiler sinh chỉ trả component. Tuy nhiên người viết có thể **khai báo tường minh accessor** với logic riêng. Nếu code cũ gọi `order.reporter()` hai lần và pattern mới deconstruct một lần, hiệu ứng quan sát được có thể khác nếu accessor được tùy biến gây side effect hoặc dữ liệu tham chiếu bên trong thay đổi ngoài dự kiến.

**Khuyến nghị:** chỉ coi refactor là giữ nguyên hành vi sau khi hiểu các accessor, exception và side effects liên quan. Không chỉ dựa vào việc cả hai bản cùng trả một chuỗi trong bộ test mẫu.

## 8. Cách xem diff thật trong Git

Khi thực hiện refactor trong repository, Git giúp theo dõi chính xác vùng code thay đổi. Các lệnh sau là **hướng dẫn thao tác**, không phải đầu ra của lần chạy ví dụ trong mục 5.

Xem diff của file đang sửa (thay đường dẫn ví dụ bằng file thực tế):

```bash
git diff --unified=12 -- src/main/java/example/EventRouter.java
```

Tùy chọn `--unified=12` giữ thêm ngữ cảnh hai bên để xem nhánh fallback và thứ tự `if`. Với diff dài, có thể dùng word diff để biết chính xác phần đổi cú pháp:

```bash
git diff --word-diff=plain -- src/main/java/example/EventRouter.java
```

Kiểm tra whitespace có vấn đề:

```bash
git diff --check
```

Nếu đã stage các thay đổi:

```bash
git diff --staged -- src/main/java/example/EventRouter.java
```

So sánh hai file được lưu riêng, ngay cả khi không thuộc cùng commit:

```bash
git diff --no-index before.java after.java
```

Lưu ý: `git diff --no-index` có thể trả **exit code 1** khi phát hiện khác biệt; điều này không có nghĩa là lệnh bị lỗi. Khi review thay đổi thực tế, không nên chỉ xem diff đã ẩn whitespace hoặc diff của một file nếu refactor còn ảnh hưởng caller/test khác.

**Không đưa đường dẫn/filename ví dụ trên vào production một cách máy móc**; đặt theo cấu trúc dự án thực tế. Người review cần nhìn cả code mới, những nơi gọi code và regression tests.

## 9. Checklist review diff trong pull request

1. **Scope:** Chỉ chuyển cast cũ thành pattern, hay còn đổi policy, default value, API, exception hoặc thứ tự xử lý?
2. **Root type:** Input có vẫn được nhận diện bằng cùng loại `instanceof` không? Giá trị `null` và sai kiểu đi đâu?
3. **Nested types:** Nếu pattern mới phân rã sâu hơn, trường hợp component lồng nhau bằng null còn nhận cùng kết quả không?
4. **Fallback:** Mỗi đường đi `else`, `return`, `continue` hoặc nhánh mặc định trước đây có tương ứng sau refactor không?
5. **Guard:** Kiểm tra `==`/`equals`, null-safe, ngưỡng biên, thứ tự `&&`/`||` và short-circuit.
6. **Scope:** Biến được bind trong pattern có chỉ được dùng tại vị trí hợp lệ không? Có xảy ra shadowing hoặc đổi tên sai nghĩa không?
7. **Side effects:** Cast, accessor, method call, logging, exception có thay đổi số lần hoặc thứ tự thực hiện?
8. **API:** Java version phù hợp chưa? Type pattern của `instanceof` có từ Java 16, còn nested record pattern yêu cầu Java 21.
9. **Tests:** Có test input đủ điều kiện, không đủ điều kiện, hai phía ngưỡng, nested null, root null và sai kiểu không?
10. **Git diff:** Có thay đổi ngoài phạm vi không? Có dòng bị xóa vô tình, import mới không cần thiết hay formatting làm loãng patch không?

Một review tốt nên phát biểu được **invariant** ngắn gọn, ví dụ: “Mọi OrderEvent đều cho PRIORITY hoặc STANDARD; AuditEvent cho AUDIT; input khác cho IGNORED; ID null vẫn được nối thành chuỗi ‘null’.” Sau đó kiểm tra từng đường đi theo invariant này.

## 10. So sánh hành vi: thêm test nhưng không biến test thành bản sao logic

Chỉ so sánh:

```java
assert legacy(input).equals(modern(input));
```

là hữu ích, nhưng chưa đủ: hai hàm có thể cùng chứa cùng một lỗi. Nên bổ sung **expected output** được xác định từ yêu cầu hoặc behavior contract trước khi refactor, ví dụ trong chương trình:

```java
check("vip boundary",
        new OrderEvent(new Order(
                "O1", new Reporter("An", "VIP"), 1000)),
        "PRIORITY:O1");
```

Dòng này yêu cầu cả bản cũ và bản mới trả đúng `PRIORITY:O1` tại ngưỡng 1000. Với một codebase dùng JUnit, nên chuyển thành parameterized tests, trong đó input và expected tách khỏi implementation của cả hai phiên bản.

Ngoài các case đã chạy ở mục 5, cần kiểm tra tùy hợp đồng ứng dụng:

- Các exception có thể xảy ra do accessor được tùy biến, không chỉ output string.
- Dữ liệu mutable nằm trong component tham chiếu của record, nhất là khi đầu vào có thể bị sửa từ nơi khác.
- Side effects, log có ý nghĩa nghiệp vụ, tương tác repository/service, hoặc thứ tự xử lý event.
- Kiểm thử tích hợp ở các caller quan trọng, vì thay đổi từ `instanceof` sang record pattern có thể tác động nhiều chỗ.
- Kiểm tra compilation theo đúng phiên bản Java mà dự án chạy, ví dụ `javac --release 21` nếu sử dụng nested record patterns.

Có thể tham khảo mức bao phủ nhánh, nhưng phần trăm coverage cao không tự chứng minh tương đương ngữ nghĩa. Những **trường hợp biên mang ý nghĩa nghiệp vụ** vẫn phải được nêu rõ.

## 11. Khi nào không nên dùng nested record pattern để thay cast?

Pattern matching không phải mục tiêu tự thân. Giữ cách viết nông hoặc đưa logic vào domain khi:

- Chỉ cần biết `input instanceof OrderEvent` và không cần mọi component bên trong.
- Nested pattern khiến caller phải biết quá sâu cấu trúc dữ liệu, khó bảo trì khi record thay đổi.
- Logic được quyết định bởi chính sách nghiệp vụ có tên riêng, thích hợp với phương thức domain (ví dụ `order.isPriority()`).
- Accessor có side effect, data flow phức tạp hoặc các nhánh cần xử lý lỗi rất cụ thể, khiến một pattern dài làm mờ hành vi.
- Codebase vẫn phải chạy Java thấp hơn 21; nested record pattern không khả dụng theo release mục tiêu.

Có thể dùng type pattern đơn giản:

```java
if (input instanceof OrderEvent event) {
    Order order = event.order();
    // Giữ phần xử lý Order tại đây khi nó dễ hiểu hơn.
}
```

Đoạn này cũng xóa cast thủ công mà không ép chuyển sang phân rã nhiều tầng. Chọn cấp độ refactor vừa đủ cho ý định, không phải cú pháp có ít dòng nhất.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Nếu refactor thay một khối `if (input instanceof OrderEvent) { ... return "STANDARD"; }` bằng duy nhất một nested pattern kiểm tra reporter khác null, diff có thể đổi hành vi nào?

**Đáp án:** `OrderEvent` có `order == null` hoặc `reporter == null` không còn được trả `STANDARD` nếu không có nhánh fallback OrderEvent.

**Câu 2.** Vì sao output `PRIORITY:null` ở ví dụ không thể tùy ý đổi thành lỗi trong cùng commit refactor?

**Đáp án:** Đó là hành vi quan sát được của logic cũ khi ID null. Siết invariant hoặc validate ID là thay đổi nghiệp vụ riêng, cần phân tích và test.

**Câu 3.** Khi xem diff, vì sao `"VIP".equals(team)` và `team.equals("VIP")` không tương đương?

**Đáp án:** Biến `team` có thể null. Bản đầu trả false, bản sau có thể ném `NullPointerException`.

**Câu 4.** Khi record `OrderEvent` tồn tại nhưng component `order` bằng null, `input instanceof OrderEvent(Order(...))` trả gì?

**Đáp án:** `false`, bởi nested record pattern `Order(...)` không khớp null. Nhưng `input instanceof OrderEvent event` vẫn true.

**Câu 5.** Vì sao test nên kiểm tra both parity và expected result?

**Đáp án:** So sánh trước/sau tìm lệch hành vi; expected độc lập giúp phát hiện cả hai bản cùng trả sai kết quả so với yêu cầu.

**Câu 6.** Nếu `git diff --no-index before.java after.java` trả exit code 1 nhưng in được diff, có phải refactor thất bại?

**Đáp án:** Không. Exit code 1 thường chỉ báo hai file khác nhau. Cần đọc nội dung khác biệt và chạy test mới đánh giá chất lượng.

## Tóm tắt

So sánh diff trước/sau refactor là quá trình **đối chiếu cú pháp với hành vi**. Việc chuyển `instanceof` + cast sang pattern matching có thể giảm mã thừa, nhưng một nested record pattern có điều kiện khớp chặt hơn kiểu outer record. Vì thế cần giữ fallback, null contract, ngưỡng, thứ tự nhánh và output. Đọc diff bằng bảng đường đi, chạy test trước/sau với expected result độc lập và review những thay đổi ngoài scope. **Diff ngắn hơn không phải bằng chứng cho refactor đúng; hành vi tương đương mới là tiêu chí chính.**

## Tài liệu tham khảo chính thức

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Java SE 21 JLS — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Git documentation — git diff](https://git-scm.com/docs/git-diff)
