# Minh họa pattern bằng ví dụ tối thiểu trong Java

Một tài liệu về Java Pattern Matching thường không cần mở đầu bằng ứng dụng lớn, framework hay nhiều lớp domain. **Ví dụ tối thiểu** là đoạn code ngắn nhất **vẫn đủ ngữ cảnh để người đọc hiểu và tự kiểm chứng một quy tắc cụ thể**: pattern kiểm tra kiểu gì, biến nào được ràng buộc, điều kiện nào làm nhánh được chọn và kết quả quan sát được là gì.

Bài thuộc **Java Core Pattern Matching → API và tài liệu**. Mục tiêu là học cách **viết, kiểm tra và trình bày các ví dụ nhỏ** cho `instanceof` type pattern, record pattern, nested deconstruction, pattern matching for `switch`, `when` guard, `null`, flow scoping và exhaustive `switch`; đồng thời phân biệt ví dụ minh họa trong tài liệu với mã nguồn độc lập có thể chạy hoặc ví dụ **cố ý không biên dịch**.

**Phiên bản cần nhớ:** Pattern matching for `instanceof` hoàn thiện ở **Java 16** (JEP 394); record patterns và pattern matching for `switch` hoàn thiện ở **Java 21** (JEP 440, JEP 441). Không cần `--enable-preview` cho những tính năng đã hoàn thiện này ở Java 21.

## 1. “Tối thiểu” nghĩa là đủ nhỏ, không phải thiếu ngữ cảnh

Một ví dụ tốt cần trả lời được bốn câu hỏi:

1. **Đầu vào là gì?** Ví dụ `Object input = "Java";` hoặc một record `Point(2, 3)`.
2. **Quy tắc nào đang được minh họa?** Kiểm tra kiểu, phân rã component, scope biến, guard, xử lý `null` hay tính exhaustive.
3. **Chạy trong môi trường nào?** Java 16+, Java 21+; là trích đoạn hay tệp `.java` hoàn chỉnh?
4. **Kết quả/diagnostic mong đợi là gì?** In gì ra stdout, trả về giá trị nào, hoặc compiler phải từ chối vì lý do nào?

“Tối thiểu” không đồng nghĩa chỉ viết:

~~~java
if (obj instanceof String s) {
    // ...
}
~~~

Đoạn trên cho thấy cú pháp nhưng **không nói `obj` được khai báo ở đâu, kiểu tĩnh là gì, `s` được dùng ra sao và điều gì sẽ xảy ra**. Nó có thể là minh họa cú pháp một dòng, nhưng **chưa phải ví dụ độc lập để sao chép và chạy**.

Một mẫu tối thiểu có thể chạy với chỉ một lớp, một phương thức, một đầu vào và một kết quả rõ ràng. Ngược lại, khi minh họa sự khác biệt giữa guard đúng và sai, cần ít nhất hai đầu vào. **Giữ lại những trường hợp làm sáng tỏ quy tắc, bỏ phần không liên quan.**

### Hai định dạng ví dụ phải được phân biệt

| Định dạng | Khi nào dùng | Điều phải nêu |
| --- | --- | --- |
| **Trích đoạn** | Giải thích một biểu thức/câu lệnh trong ngữ cảnh đã rõ | Kiểu và tên biến đầu vào, phiên bản Java, đây không phải tệp độc lập |
| **Chương trình độc lập** | Người đọc cần copy, compile và tự kiểm tra | Tên tệp = tên `public class`; source đầy đủ; lệnh `javac`/`java`; stdout |
| **Ví dụ cố ý sai** | Dạy compiler error, dominance hoặc flow scoping | Ghi rõ `CỐ Ý SAI`, lỗi mong đợi và bản sửa |
| **Test case tối thiểu** | Chứng minh một hành vi có thể bị regression | Input, expected, actual, assertion và phiên bản môi trường |

Trong tài liệu học tập, có thể bắt đầu bằng một trích đoạn ba dòng; khi tuyên bố “chạy được”, nên kèm **một tệp hoàn chỉnh** hoặc chỉ dẫn rõ để lắp vào tệp nào.

## 2. Mẫu cơ bản nhất: `instanceof` type pattern

Đặt cạnh cách viết cũ để người đọc thấy điều gì đã thay đổi:

~~~java
// Java kiểu cũ: trích đoạn trong phương thức có Object input.
if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.length());
}
~~~

Từ Java 16, có thể viết:

~~~java
// Java 16+: trích đoạn trong phương thức có Object input.
if (input instanceof String text) {
    System.out.println(text.length());
}
~~~

**Ý chính chỉ có một:** `instanceof String text` vừa kiểm tra kiểu, vừa ràng buộc `text` là `String` nếu match thành công; **không cần cast thủ công**. Tại nhánh đó, compiler biết `text` đã được ràng buộc và có kiểu `String`.

### Ví dụ độc lập 1 — type pattern và guard clause

Tạo tệp **`MinimalInstanceofDemo.java`**:

~~~java
public class MinimalInstanceofDemo {
    static String greet(Object input) {
        if (!(input instanceof String name)) {
            return "Not text";
        }
        if (name.isBlank()) {
            return "Empty";
        }
        return "Hi, " + name.trim();
    }

    public static void main(String[] args) {
        System.out.println(greet("  Lan  "));
        System.out.println(greet("   "));
        System.out.println(greet(42));
        System.out.println(greet(null));
    }
}
~~~

Biên dịch và chạy bằng **JDK 16 trở lên**:

~~~bash
javac --release 16 -encoding UTF-8 MinimalInstanceofDemo.java
java MinimalInstanceofDemo
~~~

Kết quả:

~~~text
Hi, Lan
Empty
Not text
Not text
~~~

### Đọc từng đường đi

- `"  Lan  "` là `String`. Pattern match, `name` tồn tại sau nhánh `if` phủ định vì nhánh không match đã `return`. `isBlank()` sai; `trim()` tạo chuỗi hiển thị `"Lan"`.
- `"   "` là `String` nhưng trắng; phương thức trả `"Empty"`.
- `42` không phải `String`. Nhánh phủ định trả ngay `"Not text"`.
- `null` không match type pattern `String name`, cũng trả `"Not text"`.

**Lưu ý:** `String.isBlank()` có từ Java 11, nên không gây xung đột với target Java 16 ở đây. Đoạn code cố ý không cần `record`, `sealed` hoặc pattern `switch`: mỗi ví dụ nên tập trung đúng tính năng đang dạy.

### Minh họa nhỏ về flow scoping

~~~java
// Java 16+, trích đoạn hợp lệ trong phương thức trả về int.
if (!(input instanceof String text)) {
    return -1;
}
return text.length();
~~~

Nếu không match, phương thức kết thúc; nên ở `return text.length()` cuối, compiler biết `text` tồn tại. Ngược lại:

~~~java
// CỐ Ý SAI: nhánh không match vẫn có thể đi tiếp.
if (!(input instanceof String text)) {
    System.out.println("Not a String");
}
return text.length(); // text chưa chắc đã được ràng buộc.
~~~

Đoạn thứ hai **không biên dịch** khi dùng `text` ở đường chạy không match. Ví dụ tối thiểu về lỗi phải nói đúng lý do: **flow scoping/definitely matched**, không phải một lỗi cast.

## 3. Record pattern: một record, hai component

Giả sử một điểm có hai tọa độ:

~~~java
// Java 21+, trích đoạn khai báo record.
record Point(int x, int y) {}
~~~

Chỉ cần một kiểm tra để minh họa deconstruction:

~~~java
// Java 21+, trích đoạn; input có kiểu Object.
if (input instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
~~~

Đọc là: “nếu `input` là một `Point` khác `null` thì lấy component thứ nhất vào `x` và component thứ hai vào `y`”. Compiler suy luận `x`, `y` là `int`, **không phải `Object`**. Đó là **record pattern**, khác type pattern `input instanceof Point point` vốn chỉ ràng buộc nguyên record.

Cần nêu **thứ tự component** trong tài liệu: với `record Point(int x, int y)`, vị trí đầu là `x`, vị trí sau là `y`. Tên local variable ở pattern không làm đổi thứ tự. Ví dụ `Point(var y, var x)` vẫn hợp lệ về cú pháp nhưng dễ làm người đọc hiểu sai giá trị, vì tên `y` sẽ nhận component `x` ban đầu.

### Từ một tầng sang hai tầng

~~~java
// Java 21+, trích đoạn khai báo record.
record Order(String id, Point destination) {}
~~~

Nested record pattern:

~~~java
// Java 21+, input có kiểu Object; đoạn nằm trong phương thức thích hợp.
if (input instanceof Order(var id, Point(var x, var y))) {
    System.out.println(id + " -> " + x + "," + y);
}
~~~

Chỉ cần hai record là đủ để minh họa **nested deconstruction**. Không cần dựng toàn bộ hệ thống đặt hàng, database hay DTO framework.

**Trường hợp null quan trọng:** `new Order("A-2", null)` vẫn có thể được tạo nếu constructor không áp đặt ràng buộc. Pattern `Order(var id, Point(var x, var y))` **không match** khi `destination == null`. Trong khi đó, `Order(var id, var destination)` có thể match và ràng buộc `destination == null`. Ví dụ nên thể hiện cả hai tình huống để người đọc không nghĩ `var` luôn loại bỏ null.

## 4. `switch` patterns: mỗi case diễn đạt một trường hợp

Một ví dụ Java 21+ không cần sealed hierarchy để giới thiệu `switch`:

~~~java
// Java 21+, trích đoạn; input có kiểu Object.
String label = switch (input) {
    case String text -> "Text: " + text;
    case Integer number -> "Number: " + number;
    case null -> "Missing";
    default -> "Other";
};
~~~

Các khái niệm cần minh họa riêng:

- `case String text` là **type pattern**: kiểm tra kiểu và ràng buộc biến.
- `case Integer number` xử lý một kiểu khác.
- `case null` xử lý **selector `null`**. Đừng giả định `default` bao phủ `null` theo cách mà code mong đợi.
- `default` cần thiết ở đây vì `Object` có thể chứa nhiều kiểu khác.
- Đây là **`switch expression`**, nên các nhánh tạo ra giá trị và toàn biểu thức phải có khả năng trả kết quả.

**Không nên** đưa cùng lúc nested record pattern, guard phức tạp, generics, sealed interfaces và truy cập cơ sở dữ liệu vào ví dụ `switch` đầu tiên: người đọc khó biết quy tắc nào quyết định kết quả.

## 5. Thêm guard `when` bằng một điều kiện dễ kiểm tra

Từ `switch` đơn giản, mở rộng chỉ một ý:

~~~java
// Java 21+, trích đoạn; input có kiểu Object.
String label = switch (input) {
    case String text when !text.isBlank() -> "Text";
    case String text -> "Blank";
    case null -> "Missing";
    default -> "Other";
};
~~~

Guard chạy **sau khi type pattern đã match**. Nếu `input = "Java"`, nhánh đầu được chọn; nếu `input = "   "`, guard sai và case `String` tiếp theo được chọn.

Đây là cách trình bày rõ hơn một ví dụ `when` gọi hàng loạt service hoặc dùng điều kiện khó hiểu. Một **guard thuần túy, không side effect** đủ để giải thích cơ chế.

### Thứ tự case phải đúng

~~~java
// CỐ Ý SAI, Java 21+, input là Object.
String label = switch (input) {
    case String text -> "Any string";
    case String text when text.isBlank() -> "Blank";
    case null -> "Missing";
    default -> "Other";
};
~~~

Nhánh `String` tổng quát đặt trước đã bao phủ tất cả `String`; nhánh có guard phía sau bị **dominated** nên compiler từ chối. Bản sửa là đặt nhánh **cụ thể có `when` trước**, nhánh `String` không guard sau.

Khi tạo tài liệu về dominance, nên dùng đúng **một lỗi** để compiler không bị phân tán bởi lỗi khác. Nêu rằng thông báo chẩn đoán có thể thay đổi theo JDK; quan trọng là nguyên nhân **dominated case label**.

## 6. Ví dụ độc lập 2 — kết hợp vừa đủ record, guard và `switch`

Tập hợp một số quy tắc vào **một chương trình nhỏ** để người đọc tự kiểm chứng, nhưng chỉ có hai record và một phương thức phân loại. Ví dụ này không thực hiện I/O ngoài in kết quả.

Tạo tệp **`MinimalPatternExamples.java`**:

~~~java
public class MinimalPatternExamples {
    record Point(int x, int y) {}
    record Order(String id, Point destination) {}

    static String describe(Object input) {
        return switch (input) {
            case Order(var id, Point(var x, var y))
                    when x >= 0 && y >= 0 ->
                    "Order " + id + " -> " + x + "," + y;

            case Order(var id, var destination) ->
                    "Incomplete " + id;

            case String text when !text.isBlank() ->
                    "Text: " + text.trim();

            case String text -> "Blank text";
            case null -> "Missing";
            default -> "Unsupported";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Order("A-1", new Point(2, 3))));
        System.out.println(describe(new Order("A-2", null)));
        System.out.println(describe(new Order("A-3", new Point(-1, 1))));
        System.out.println(describe("  Java  "));
        System.out.println(describe("  "));
        System.out.println(describe(null));
        System.out.println(describe(7));
    }
}
~~~

Biên dịch và chạy bằng **JDK 21 trở lên**:

~~~bash
javac --release 21 -encoding UTF-8 MinimalPatternExamples.java
java MinimalPatternExamples
~~~

Stdout:

~~~text
Order A-1 -> 2,3
Incomplete A-2
Incomplete A-3
Text: Java
Blank text
Missing
Unsupported
~~~

### Vì sao cần đúng bảy đầu vào này?

| Đầu vào | Quy tắc được chứng minh | Kết quả |
| --- | --- | --- |
| `Order("A-1", Point(2,3))` | Nested record match và guard đúng | `Order A-1 -> 2,3` |
| `Order("A-2", null)` | Nested `Point(...)` không match khi component null | `Incomplete A-2` |
| `Order("A-3", Point(-1,1))` | Nested record match nhưng guard sai; chọn fallback | `Incomplete A-3` |
| `"  Java  "` | Type pattern `String`, guard đúng, `trim()` | `Text: Java` |
| `"  "` | String match, guard sai, chọn case String sau | `Blank text` |
| `null` | `case null` | `Missing` |
| `7` | Kiểu khác, rơi vào `default` | `Unsupported` |

**Chú ý về tên fallback:** `"Incomplete"` trong ví dụ gộp hai nguyên nhân khác nhau: thiếu điểm đích và tọa độ không đạt điều kiện guard. Điều này nhằm tập trung vào **hành vi matching**, không phải một chính sách validation nghiệp vụ hoàn chỉnh. Nếu API thực tế cần lý do lỗi riêng, hãy tách bước validation hoặc dùng một kiểu kết quả có mã lỗi.

**Chú ý về kiểu tĩnh:** `describe(Object input)` được chọn có chủ đích để người đọc thấy các kiểu `Order`, `String`, `null` và kiểu lạ đều có thể được truyền vào. Với một API chuyên dụng, nên khai báo kiểu tham số hẹp hơn khi hợp đồng miền nghiệp vụ cho phép.

## 7. Ví dụ độc lập 3 — sealed hierarchy và exhaustive `switch`

Muốn minh họa **compiler yêu cầu xử lý đủ kiểu**, cần một mô hình có tập biến thể được kiểm soát. Ví dụ tối thiểu có thể chỉ cần hai event:

Tạo tệp **`MinimalSealedSwitchDemo.java`**:

~~~java
public class MinimalSealedSwitchDemo {
    sealed interface Event permits Joined, Left {}

    record Joined(String user) implements Event {}
    record Left(String user) implements Event {}

    static String describe(Event event) {
        return switch (event) {
            case Joined(var user) -> "Joined: " + user;
            case Left(var user) -> "Left: " + user;
            case null -> "No event";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Joined("Mai")));
        System.out.println(describe(new Left("Lan")));
        System.out.println(describe(null));
    }
}
~~~

Biên dịch/chạy với **Java 21+**:

~~~bash
javac --release 21 -encoding UTF-8 MinimalSealedSwitchDemo.java
java MinimalSealedSwitchDemo
~~~

Đầu ra:

~~~text
Joined: Mai
Left: Lan
No event
~~~

**Điểm đáng học:** `Event` là sealed interface chỉ cho phép `Joined` và `Left` triển khai trực tiếp trong mô hình này. Hai case record đã bao phủ tập kiểu không null, và `case null` xử lý selector null. Vì vậy `switch expression` **không cần `default`**.

Nếu bổ sung một permitted subtype thứ ba `Renamed` rồi biên dịch lại mà chưa thêm case tương ứng, `switch expression` không còn exhaustive. Compiler sẽ chỉ ra vấn đề. Đó là lý do **không thêm `default` vô điều kiện** vào ví dụ dạy exhaustiveness: default có thể che mất tín hiệu khi mở rộng hierarchy.

Một ví dụ nhỏ không cần tạo cả hệ thống event bus để chứng minh tính chất này. Chỉ cần **sealed type + hai record + một switch**.

## 8. Thế nào là ví dụ “tối thiểu nhưng không gây hiểu sai”?

Giữ những yếu tố có thể ảnh hưởng tới kết luận:

**8.1. Kiểu tĩnh của selector.** `Object input`, `Event event` hay `String text` có thể dẫn đến các quy tắc exhaustiveness/dominance khác nhau. Nếu chỉ đưa mỗi biểu thức `switch` mà không ghi selector type, người đọc có thể suy luận sai.

**8.2. Chính sách null.** Với `record Box(String value)`, `Box(var value)` có thể ràng buộc component tham chiếu `null`; với `Box(String text)`, nested type pattern `String text` không match component `null`. Đó là khác biệt đáng giữ trong ví dụ.

~~~java
// Java 21+, trích đoạn; input có kiểu Object và Box đã khai báo.
record Box(String value) {}

String result = switch (input) {
    case Box(String text) -> "Text " + text;
    case Box(var value) -> "Box without text";
    case null -> "Missing box";
    default -> "Other";
};
~~~

Nếu `input` là `new Box(null)`, nhánh đầu không match nhưng nhánh `Box(var value)` match. Không cần thêm framework validation để minh họa quy tắc này.

**8.3. Phạm vi biến.** Với `instanceof`, pattern variable được dùng khi compiler có thể chứng minh match. Không di chuyển `text` ra ngoài đường đi được chứng minh chỉ để rút gọn source.

**8.4. Thứ tự case.** Nhánh hẹp/guard phải đứng trước nhánh rộng khi có quan hệ dominance; thứ tự thay đổi có thể vừa làm compiler từ chối vừa làm sai ý nghĩa phân loại.

**8.5. Kết quả quan sát được.** `System.out.println` hoặc assertion nên phản ánh chính xác rule; không xuất kết quả phụ thuộc ngày giờ, randomness, locale hay I/O khi chúng không thuộc bài đang học.

**8.6. Phiên bản.** Không đặt record pattern dưới nhãn “Java 17 stable”. Type pattern cho `instanceof` ổn định từ Java 16; record patterns/switch patterns ổn định trong Java 21.

## 9. Một quy trình tạo minimal example để viết tài liệu API

Khi cần giải thích một bug, một API hoặc hành vi ngôn ngữ, có thể dùng quy trình sau:

1. **Viết câu hỏi duy nhất.** Ví dụ: “Nested `Point(...)` có match component null không?” Đừng bắt đầu bằng một ứng dụng hoàn chỉnh.
2. **Chọn phiên bản JDK mục tiêu.** Nêu rõ Java 16 hay Java 21 ngay đầu ví dụ, tránh vô tình dùng feature preview hoặc API không thuộc target.
3. **Giữ tối thiểu kiểu dữ liệu.** Dùng `record Box(Point point)` thay vì mô hình 20 class; chỉ thêm subtype khi bài cần chứng minh exhaustiveness.
4. **Chọn phương thức ngắn.** Một phương thức `describe` hoặc `classify` là đủ; hạn chế side effect, builder, service hay dependency injection.
5. **Chọn đầu vào phân biệt được các nhánh.** Ít nhất một case match, một case không match; thêm null/guard false nếu chính đó là trọng tâm.
6. **Biên dịch và chạy.** Dùng `javac --release ...` và `java ...`; không dựa vào trí nhớ để viết stdout.
7. **Đối chiếu kỳ vọng.** Nếu output không như mong đợi, xác định đã hiểu sai quy tắc hay ví dụ vô tình còn điều kiện khác.
8. **Cắt bỏ phần không ảnh hưởng.** Bỏ logging, DB, concurrency, Spring, dữ liệu lớn, lớp trợ giúp thừa; mỗi lần cắt nên chạy lại để bảo đảm hiện tượng vẫn còn.
9. **Giữ thông tin tái lập.** Tên file/class, JDK target, source hoàn chỉnh hoặc ngữ cảnh cho snippet, input và output.
10. **Giải thích một nguyên nhân chính.** Kết thúc bằng “vì sao” và điều kiện áp dụng, không chỉ chép lại cú pháp.

**Kiểm tra cuối:** Người đọc có thể tạo một file đúng tên và chạy bằng hai lệnh không? Có hiểu chính xác Java nào được yêu cầu không? Có ít nhất một đầu vào làm nổi bật quy tắc không? Có quy tắc nào khác vô tình gây ra cùng kết quả không?

### Ví dụ “giảm thiểu sự cố” (minimal reproduction)

Giả sử một dự án báo: “Một đơn hàng thiếu địa chỉ nhưng `switch` lại vào nhánh tổng quát.” Đừng vội gửi cả project. Hãy thu nhỏ thành hai record và hai case, giống `Order`/`Point` ở phần 6, có một input `new Order("A-2", null)` và stdout `Incomplete A-2`. Như vậy người đọc thấy được **nested record pattern không match null**, không bị nhiễu bởi repository, JSON mapper hay business service.

Khi gửi bug report, thêm thông tin **expected vs actual** và JDK thật đã dùng. Nếu vấn đề chỉ xảy ra sau khi upgrade Java, cần ghi rõ bản compiler/runtime liên quan; source vẫn nên được giữ tối thiểu.

## 10. Trình bày ví dụ trong README, API docs và code review

### 10.1. Dùng một cấu trúc nhất quán

Một mục tài liệu gọn có thể theo định dạng:

~~~text
Tính năng: record pattern
Phiên bản: Java 21+
Đầu vào: new Point(2, 3)
Quy tắc: Point(var x, var y) ràng buộc hai component int
Mã nguồn: snippet hoặc link tới file chạy được
Lệnh chạy: javac --release 21 ...; java ...
Kết quả: một dòng có giá trị xác định
Lưu ý: nested pattern không match component null
~~~

Đây là **khung thông tin** chứ không phải một đoạn Java để chạy. Không nhất thiết mục nào cũng cần nhiều trường; giữ các phần có ảnh hưởng đến việc tự kiểm chứng.

### 10.2. Không trộn “sơ đồ cú pháp” với “chương trình hoàn chỉnh”

~~~java
// MẪU CÚ PHÁP, KHÔNG PHẢI TỆP ĐỘC LẬP.
case Point(var x, var y) when x > 0 -> ...
~~~

Một dấu `...` hoặc tên biến chưa khai báo có thể hợp lệ trong ví dụ **minh họa cấu trúc** nhưng không thể tự biên dịch. Hãy ghi rõ đó là mẫu cú pháp/trích đoạn. Nếu muốn gọi là **runnable**, dùng source đầy đủ như phần 6 hoặc 7 và không để placeholder.

### 10.3. Gắn ví dụ với phiên bản và test

Tài liệu nguồn nên được cập nhật cùng codebase. Nếu ví dụ được copy từ source test đã chạy thành công, rủi ro **documentation drift** thấp hơn việc viết lại thủ công. Với project có hỗ trợ Javadoc, có thể cân nhắc tính năng **code snippets trong Javadoc** (JEP 413, từ Java 18) để trình bày code trong API docs và đối chiếu với source được kiểm thử. Không nên giả định mọi dự án cũ đều có Javadoc tool hỗ trợ snippet tag.

Dù dùng Markdown code fence hay Javadoc snippets, **cú pháp hiển thị không tự chứng minh ví dụ chạy đúng**. Vẫn cần một bước kiểm thử compile/run source trong CI nếu ví dụ là tài liệu quan trọng hoặc được dùng làm hợp đồng API.

### 10.4. Những điều nên bỏ khỏi ví dụ API đầu tiên

- Dependency framework không liên quan đến cơ chế pattern.
- Gọi database/network hoặc điều kiện phụ thuộc môi trường.
- Nested patterns quá sâu khi chỉ muốn giải thích `instanceof`.
- Những tên biến `a`, `b`, `c` khó đọc nếu component mang ý nghĩa nghiệp vụ.
- Nhiều kiểu Java mới cùng xuất hiện mà không cần thiết.
- Output quá dài hoặc thay đổi ngẫu nhiên; khó so với kỳ vọng.
- “Tối ưu hóa” performance không được đo, làm lệch bài cú pháp.
- Ngoại lệ bị catch rồi bỏ qua, khiến ví dụ trông như thành công dù code lỗi.

Ví dụ tối thiểu **không nhất thiết là code production lý tưởng**. Một đoạn demo có thể bỏ error handling không liên quan, nhưng phải nêu rõ giới hạn ấy, đặc biệt khi minh họa `null` hoặc trường hợp dữ liệu không hợp lệ.

## 11. Kiểm tra tự động ví dụ mà không cần framework

Với một bài dạy cơ bản, chỉ cần `javac` và `java`:

~~~bash
javac --release 16 -encoding UTF-8 MinimalInstanceofDemo.java
java MinimalInstanceofDemo

javac --release 21 -encoding UTF-8 MinimalPatternExamples.java
java MinimalPatternExamples

javac --release 21 -encoding UTF-8 MinimalSealedSwitchDemo.java
java MinimalSealedSwitchDemo
~~~

Các lệnh **biên dịch source độc lập**; mỗi tên file phải trùng `public class`. Trên JDK 21+ hỗ trợ `--release 16`, chương trình đầu tiên có thể compile cho Java 16. Nếu chạy trên JDK 16 trực tiếp, cũng có thể biên dịch bằng `javac MinimalInstanceofDemo.java`.

Một cách kiểm tra sâu hơn là dùng **Java Compiler API** để so sánh target: với một chương trình nhỏ có `instanceof String text`, compilation theo `--release 16` nên thành công; với đoạn có record pattern và pattern `switch`, `--release 21` thành công còn `--release 17` bị từ chối. Kết quả thực nghiệm trên JDK 24 với một cặp source rút gọn:

~~~text
type pattern, release 16: true
record switch, release 21: true
record switch, release 17: false
~~~

Đây là kiểm tra **khả năng biên dịch theo release**, không phải bài test hiệu năng hay bảo đảm mọi dependency/runtime được hỗ trợ. Khi target source và runtime khác nhau, vẫn cần kiểm tra `java -version` của môi trường chạy.

### Tại sao không chỉ chạy một lần bằng IDE?

IDE có thể cấu hình language level/JDK khác với CI. Một ví dụ Java 21 “đúng” trên IDE vẫn có thể thất bại nếu build project dùng `--release 17`. Đưa câu lệnh build vào tài liệu là cách giúp người khác **tái lập** và tránh đánh giá sai vì toolchain.

### Negative example phải có mục đích

Nếu tài liệu muốn chứng minh lỗi dominance, tạo một snippet có **một** nhánh bị che, gắn nhãn `CỐ Ý SAI` và nói rõ compiler sẽ từ chối. Không đặt source cố ý sai trong `src/main/java` nếu nó làm build chính luôn thất bại. Thay vào đó, có thể để ở tài liệu hoặc kiểm thử compiler riêng.

## 12. Những lỗi thường gặp khi viết ví dụ tối thiểu

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Trích đoạn không có kiểu selector | Không biết compiler áp dụng rule nào | Nêu `Object input` hoặc kiểu event cụ thể |
| Không nêu Java version | Người đọc Java 17 không compile được record pattern | Ghi Java 16+/21+ và lệnh `--release` |
| Dùng `var` như thể luôn có kiểu `Object` | Hiểu sai type inference của record component | Nêu kiểu suy luận từ record declaration |
| Quên selector/component `null` | Kết quả chạy khác dự đoán | Thêm tối thiểu một test null nếu null là trọng tâm |
| Đặt case rộng trước case hẹp | Compiler báo dominated case | Đưa case hẹp/guard lên trước |
| Dùng `default` trong ví dụ exhaustive sealed | Che lỗi thiếu subtype khi mở rộng | Dùng các case cụ thể, không default nếu đã bao phủ |
| Sao chép source mà tên file khác `public class` | Ví dụ không compile | Đồng bộ tên tệp, lớp và lệnh chạy |
| Ghi stdout theo phỏng đoán | Người học mất thời gian tìm lỗi không có thật | Chạy source thật và lấy output chính xác |
| Vừa demo cú pháp vừa làm I/O/transaction | Người đọc không biết kết quả do đâu | Tách mẫu cú pháp khỏi ví dụ nghiệp vụ |
| Đoạn sai chỉ báo “compile fails” | Không rõ failure có đúng nguyên nhân không | Ghi loại chẩn đoán mong đợi và đối chứng dương |
| Giữ mọi chi tiết sau khi rút gọn bug | MRE vẫn khó hiểu | Loại phần không ảnh hưởng, chạy lại sau mỗi lần cắt |
| Ngắn đến mức mất trường hợp đặc biệt | Người đọc suy luận sai hành vi | Giữ input phản ví dụ cần thiết như guard false/null |

## 13. Bài tập tự luyện

### Bài 1 — Hoàn thiện một snippet `instanceof`

Cho `Object input = "Java";`. Viết một biểu thức Java 16+ sử dụng type pattern để in độ dài của chuỗi mà không cast. Nếu input không phải String, in `"Other"`.

**Đáp án:**

~~~java
// Java 16+, trích đoạn.
Object input = "Java";
if (input instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("Other");
}
~~~

Output là `4`. Ví dụ này chỉ cần một source value và hai nhánh. Muốn test trường hợp không match, đổi `input` thành `42` và chạy lại; output sẽ là `"Other"`.

### Bài 2 — Nested pattern và null

Cho:

~~~java
record Point(int x, int y) {}
record Box(Point point) {}
~~~

Với `Object input = new Box(null);`, `case Box(Point(var x, var y))` có được chọn không? `case Box(var point)` có match không?

**Đáp án:** Nhánh nested `Point(...)` không match vì component `point` là null; nhánh `Box(var point)` có thể match và biến local `point` nhận null. Đây là lý do một ví dụ về nested deconstruction nên có đúng một input null để phân biệt hai loại pattern.

### Bài 3 — Sửa ví dụ `when`

~~~java
// CỐ Ý SAI, input là Object.
String label = switch (input) {
    case String s -> "text";
    case String s when s.isBlank() -> "blank";
    case null -> "null";
    default -> "other";
};
~~~

**Đáp án:** Đặt `case String s when s.isBlank()` lên trước `case String s` để tránh dominance. Để kiểm chứng runtime, dùng `" "` và `"A"`; hai input này cần cho kết quả khác nhau.

### Bài 4 — Ví dụ nào tối thiểu hơn?

Muốn giải thích `instanceof String name`, phương án A dùng Spring Controller, JSON, repository và 8 lớp; phương án B có một phương thức nhận `Object`, một `if` và hai input đại diện. Nên chọn phương án nào cho tài liệu cú pháp?

**Đáp án:** B. Những thành phần Spring/repository không giúp chứng minh `instanceof` và còn có thể gây lỗi môi trường ngoài phạm vi. Tuy nhiên, B vẫn phải nêu Java version, selector type và cách kiểm tra kết quả. Nếu tài liệu đang hướng dẫn **tích hợp Spring thật**, một ví dụ lớn hơn mới là phù hợp.

### Bài 5 — Viết ví dụ exhaustive đúng trọng tâm

Tạo sealed interface `Action` với hai record `Start` và `Stop`. Hãy viết `switch expression` trả `"start"`/`"stop"` và xử lý `null`, không dùng `default`.

**Đáp án:**

~~~java
// Java 21+, trích đoạn khai báo và phương thức trong cùng phạm vi hợp lệ.
sealed interface Action permits Start, Stop {}
record Start() implements Action {}
record Stop() implements Action {}

static String name(Action action) {
    return switch (action) {
        case Start() -> "start";
        case Stop() -> "stop";
        case null -> "none";
    };
}
~~~

Nếu thêm một permitted subtype mới, `switch expression` cần được xem xét lại để bảo đảm exhaustive. Đây là ví dụ nhỏ vừa đủ: không cần tạo hệ thống event processing.

## 14. Checklist trước khi xuất bản ví dụ

Trước khi đưa một pattern example vào tài liệu API, README hoặc câu trả lời kỹ thuật, kiểm tra:

- [ ] Có đúng **một thông điệp chính** mà người đọc cần rút ra.
- [ ] Biến đầu vào và **kiểu tĩnh** được khai báo hoặc giải thích.
- [ ] Phiên bản Java và trạng thái preview/final được nêu chính xác.
- [ ] Trích đoạn được gắn nhãn **trích đoạn**, ví dụ chạy được có **file/class đầy đủ**.
- [ ] `javac`/`java` được ghi kèm đúng tên tệp.
- [ ] Stdout hoặc loại lỗi compiler được **đối chiếu bằng thực nghiệm**.
- [ ] Có ít nhất một trường hợp match; thêm non-match, guard false, null nếu phục vụ bài.
- [ ] Không đưa I/O, dependency hoặc nghiệp vụ thừa làm nhiễu cơ chế pattern.
- [ ] Thứ tự `case`, phạm vi biến và semantics null không bị hiểu sai.
- [ ] Với sealed hierarchy, không dùng `default` chỉ để che thiếu nhánh.
- [ ] Có thể tái lập bằng môi trường được mô tả; không yêu cầu thiết lập ẩn.
- [ ] Nếu ví dụ dùng trong CI/docs lâu dài, source được lưu ở nơi có thể compile/test lại.

## 15. Tổng kết

**Ví dụ pattern tốt nhất không phải ví dụ có ít ký tự nhất**, mà là ví dụ **ít thành phần nhất vẫn chứng minh một quy tắc có thể kiểm chứng**.

- Dạy type pattern bằng `instanceof` + một biến có kiểu tĩnh `Object`.
- Dạy record pattern bằng một `record` đơn giản; nested record pattern chỉ cần hai tầng và một input null.
- Dạy `switch` patterns bằng hai kiểu và một fallback; dạy `when` bằng một guard Boolean rõ ràng.
- Dạy exhaustiveness bằng **sealed hierarchy nhỏ** và `switch` không `default`.
- Dạy lỗi compiler bằng **một ví dụ cố ý sai** kèm nguyên nhân chẩn đoán, không trộn nhiều lỗi.
- Ghi rõ **Java version, source hoàn chỉnh hay trích đoạn, lệnh chạy và output thực tế**.
- Khi ví dụ trở thành tài liệu API hoặc regression test, duy trì khả năng **compile/test lại tự động** để hạn chế lỗi thời.

**Nguồn chính thức:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394); [JEP 440 — Record Patterns](https://openjdk.org/jeps/440); [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441); [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409); [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413); [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html); [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
