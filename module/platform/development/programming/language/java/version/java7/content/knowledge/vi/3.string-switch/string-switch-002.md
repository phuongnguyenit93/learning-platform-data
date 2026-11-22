# Nhãn `case` là hằng chuỗi và nhánh `default` trong `switch(String)`

## Mục tiêu

Từ Java 7, một `switch` có thể nhận biểu thức kiểu `String`. Cách viết này vẫn hợp lệ và hữu ích trên các bản Java hiện đại khi chương trình chọn nhánh theo **những chuỗi có giá trị xác định**: lệnh, trạng thái, định dạng, phương thức xử lý hoặc loại thông điệp.

Hai quy tắc quan trọng nhất:

1. Nhãn `case` cho `String` phải là **biểu thức hằng tính được lúc biên dịch** (*compile-time constant expression*). Không được viết một nhãn phụ thuộc giá trị chỉ biết khi chạy.
2. Nhánh `default` xử lý các **giá trị không khớp với nhãn `case` nào**. Nó không tự thay thế xử lý `null`, và trong cú pháp `case:` truyền thống, nó cũng có thể bị thực thi do **fall-through** từ nhánh phía trên nếu thiếu `break`.

Bài học tập trung vào hợp đồng ngôn ngữ vẫn đang áp dụng; ví dụ chạy độc lập trên **Java 17+**. Phần khác biệt của Java 21+ được ghi nhãn phiên bản riêng, tránh nhầm tính năng hiện hành với cú pháp đã có từ Java 7.

## 1. `switch` so khớp chuỗi như thế nào?

Cấu trúc quen thuộc:

~~~java
switch (command) {
    case "SAVE":
        // xử lý lệnh SAVE
        break;
    case "READ":
        // xử lý lệnh READ
        break;
    default:
        // chuỗi khác SAVE và READ
}
~~~

Đây là **đoạn minh họa**, giả sử biến `command` đã được khai báo và có kiểu `String`. Tại thời điểm chạy:

- Java đánh giá biểu thức selector `command`, tìm một nhãn `case` có giá trị chuỗi phù hợp.
- Giá trị của `String` được so khớp theo **nội dung**, tương đương `String.equals`, không theo sự trùng nhau của tham chiếu như `==`.
- Việc so khớp là **phân biệt chữ hoa/chữ thường**: `"SAVE"` khác `"save"` và `"Save"`. Dấu cách cũng là dữ liệu: `"SAVE "` không bằng `"SAVE"`.
- Nếu không khớp nhãn nào, Java đi vào `default` nếu có. Với `switch statement` truyền thống không có `default`, một giá trị không khớp khiến câu lệnh kết thúc mà không thực hiện nhánh nào.
- Với selector `null`, một `switch` không có nhãn `case null` ném `NullPointerException`; riêng `default` **không bắt được `null`**. Nhãn `case null` là khả năng ngôn ngữ từ **Java 21**, được giải thích tại mục 6.

Ví dụ: `new String("SAVE")` vẫn khớp nhãn `case "SAVE"` vì nội dung bằng nhau, dù việc tạo đối tượng mới có thể cho tham chiếu khác. Quy tắc này được nêu trực tiếp trong [JLS §14.11.1.2 — xác định nhãn phù hợp](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.11.1.2).

**Phân biệt selector và case label:** selector được phép là biến có giá trị thay đổi lúc chạy; ngược lại, mỗi **case constant** phải biết trước ở lúc biên dịch. Nhầm lẫn hai vai trò này là nguyên nhân chính của lỗi “constant string expression required”.

## 2. Một nhãn `case` chuỗi hợp lệ là gì?

Theo [JLS §15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.29), một nhãn `case` chuỗi có thể được viết bằng **chuỗi literal**, **phép nối chuỗi hằng**, hoặc **hằng biến** (*constant variable*) kiểu `String`.

| Ví dụ đặt sau `case` | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `"START"` | Có | Literal có giá trị ngay khi biên dịch |
| `"ST" + "ART"` | Có | Hai toán hạng hằng, được tính thành `"START"` lúc biên dịch |
| `START` với `static final String START = "START";` | Có | Hằng biến `String`, khởi tạo bằng biểu thức hằng |
| `PREFIX + "ART"` với `static final String PREFIX = "ST";` | Có | Hai phần đều là hằng biểu thức |
| `LOCAL` với `final String LOCAL = "START";` | Có | Biến cục bộ `final` với khởi tạo hằng cũng đủ điều kiện |
| `input` với `String input = readInput();` | Không | Giá trị chỉ được biết khi chạy |
| `dynamic` với `final String dynamic = System.getenv("ACTION");` | Không | `final` chỉ ngăn gán lại; lời gọi hàm không biến thành hằng biên dịch |
| `new String("START")` | Không | Khởi tạo object bằng `new` không phải hằng biểu thức |
| `"START".toLowerCase()` | Không | Lời gọi phương thức không phải hằng biểu thức |
| `null` | Khác quy tắc | `case null` là nhãn đặc biệt được hỗ trợ từ Java 21, không phải hằng `String` |

`static` **không bắt buộc** để là hằng biến: điều cốt yếu là kiểu `String` hoặc kiểu nguyên thủy, có `final`, và được khởi tạo bằng **constant expression**. Với trường của class, `static final String` khởi tạo bằng literal thường là lựa chọn rõ ràng.

Ví dụ về mã **không biên dịch được**, chỉ để nhận diện lỗi:

~~~java
String input = "START";
final String runtimeValue = System.getenv("ACTION");

switch (input) {
    case input:          // LỖI: input không phải hằng biên dịch
        break;
    case runtimeValue:   // LỖI: final nhưng initializer là lời gọi method
        break;
    case new String("START"): // LỖI: new không phải constant expression
        break;
}
~~~

Các dòng trên không phải chương trình chạy; đây là những lỗi **compile-time**. Để so với một giá trị thay đổi theo runtime, dùng `if/else`, `equals` hoặc cấu trúc dữ liệu phù hợp. Không thể “sửa” nhãn không hằng bằng cách thêm `final` vào biến khởi tạo động.

### 2.1. Hằng khác tên nhưng cùng giá trị vẫn bị trùng nhãn

Giả sử có:

~~~java
static final String START = "START";
static final String PREFIX = "ST";

// Không hợp lệ nếu cùng xuất hiện trong một switch block:
case START:            // giá trị "START"
case PREFIX + "ART":   // cũng là "START" => duplicate case label
~~~

Đây là **minh họa các nhãn gây lỗi**, không phải chương trình độc lập. Hai biểu thức đều hợp lệ khi đứng riêng, nhưng **cùng một `switch` không được có hai case constant có giá trị giống nhau**. Trình biên dịch kiểm tra giá trị hằng sau khi nối chuỗi, chứ không chỉ kiểm tra tên biến khác nhau.

**Điểm kiểm tra khi review:** tìm cả các nhãn tạo bằng hằng biến hoặc nối literal, vì `case "A"` và `case "A" + ""` cũng trùng nhau.

## 3. Chương trình Java 17+: literal, hằng biến, nhóm case và default

Tạo file `StringCaseLabelsDemo.java`:

~~~java
public class StringCaseLabelsDemo {
    private static final String SAVE = "SAVE";
    private static final String PREFIX = "RE";
    private static final String READ = PREFIX + "AD";

    static String route(String command) {
        if (command == null) {
            return "missing";
        }

        switch (command) {
            case SAVE:
                return "write";
            case READ:
            case "SHOW":
                return "read";
            case "":
                return "empty";
            default:
                return "unknown:" + command;
        }
    }

    public static void main(String[] args) {
        System.out.println(route(new String("SAVE")));
        System.out.println(route("READ"));
        System.out.println(route("SHOW"));
        System.out.println(route("save"));
        System.out.println(route(""));
        System.out.println(route(null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 StringCaseLabelsDemo.java
java StringCaseLabelsDemo
~~~

Kết quả:

~~~text
write
read
read
unknown:save
empty
missing
~~~

Giải thích từng dòng:

1. `new String("SAVE")` khớp hằng `SAVE` theo **nội dung** → `write`.
2. `READ = PREFIX + "AD"` là hằng biên dịch, có giá trị `"READ"` → `read`.
3. Hai nhãn `case READ:` và `case "SHOW":` được đặt liên tiếp, dùng chung một nhóm câu lệnh → `read`.
4. `"save"` không bằng `"SAVE"` do phân biệt hoa/thường → `default` trả `unknown:save`.
5. Chuỗi rỗng `""` là một giá trị **khác null**, có thể viết `case ""` → `empty`.
6. Guard `if (command == null)` xử lý `null` **trước** khi vào `switch` → `missing`.

Mỗi nhánh có `return` nên phương thức kết thúc ngay, **không cần `break`**. Đây là cách tránh fall-through phù hợp khi nhiệm vụ của `switch` là chọn **một** giá trị trả về. Một `switch statement` dùng `case:` và các câu lệnh không `return`/`throw`/`break` lại phải kiểm tra fall-through riêng.

## 4. Hiểu chính xác nhánh `default`

`default` là **nhãn mặc định cho trường hợp không có nhãn `case` nào khớp**. Nó có thể được dùng để trả một trạng thái rõ ràng, xử lý dữ liệu không hợp lệ hoặc ném exception có chủ đích.

Ví dụ cách xử lý lệnh không hỗ trợ:

~~~java
default:
    throw new IllegalArgumentException("Unsupported command: " + command);
~~~

Đây là **đoạn bên trong switch**; exception là quyết định của ứng dụng, **không phải** ngoại lệ mà `default` tự động ném.

Những điều cần phân biệt:

- **Không bắt buộc với `switch statement` cổ điển:** thiếu `default` và không có case khớp thì không có nhánh xử lý. Tuy nhiên, với đầu vào ngoài phạm vi kiểm soát, `default` giúp tránh “im lặng bỏ qua” không mong muốn.
- **Chỉ có tối đa một `default`** trong một switch block. Trùng nhãn `default` là lỗi biên dịch.
- **Nên đặt cuối:** với switch chỉ có nhãn hằng chuỗi, Java vẫn có thể cho phép vị trí khác, nhưng đặt cuối dễ đọc và giảm lỗi do luồng chạy rơi xuống nhánh tiếp theo. Khi dùng nhãn pattern/null trong các bản mới, còn có ràng buộc về thứ tự nhãn.
- **Không phải nhánh `else if` kiểm tra theo thứ tự:** Java chọn nhãn tương ứng với selector. Việc đặt `default` trước hay sau các hằng không thay đổi nguyên tắc so khớp; **thứ tự code vẫn quan trọng** nếu dùng cú pháp `:` có fall-through.
- **Không tự xử lý `null`:** nếu selector là `null` và switch không có `case null`, Java ném `NullPointerException` trước khi đi vào `default`.
- **Không thay thế kiểm tra đầu vào:** chuỗi rỗng, dấu cách dư, khác chữ hoa/thường, dữ liệu ngoài miền giá trị vẫn cần một chính sách rõ ràng của ứng dụng.

### 4.1. Fall-through: vì sao `default` có thể chạy dù đã khớp `case`?

Trong cú pháp các nhóm `case:`, nếu thực thi nhánh đầu tiên mà không gặp `break`, `return` hoặc `throw`, luồng xử lý **có thể chạy tiếp câu lệnh của nhóm kế tiếp**, kể cả nhóm `default`. Đây là *fall-through*.

Tạo `DefaultFallthroughDemo.java`:

~~~java
public class DefaultFallthroughDemo {
    static void withoutBreak(String value) {
        switch (value) {
            case "OPEN":
                System.out.println("open");
            default:
                System.out.println("fallback");
        }
    }

    static void withBreak(String value) {
        switch (value) {
            case "OPEN":
                System.out.println("open");
                break;
            default:
                System.out.println("fallback");
        }
    }

    public static void main(String[] args) {
        System.out.println("withoutBreak:");
        withoutBreak("OPEN");

        System.out.println("withBreak:");
        withBreak("OPEN");
        withBreak("OTHER");
    }
}
~~~

~~~bash
javac --release 17 DefaultFallthroughDemo.java
java DefaultFallthroughDemo
~~~

~~~text
withoutBreak:
open
fallback
withBreak:
open
fallback
~~~

Trong lượt `withoutBreak("OPEN")`, `"OPEN"` đã **khớp `case`**, nhưng vẫn in tiếp `fallback` vì thiếu `break`. Đây **không** có nghĩa `default` đã so khớp với `"OPEN"`. Nó chỉ bị **chạy xuyên xuống**. Lượt `withBreak("OPEN")` chỉ in `open`; dòng `fallback` cuối cùng đến từ lời gọi `withBreak("OTHER")`, khi không có nhãn hằng nào khớp.

**Quy tắc thực hành:** Với cú pháp dấu hai chấm, mỗi nhánh xử lý độc lập thường nên kết thúc bằng `break`, `return` hoặc `throw`. Có thể chủ động đặt nhiều nhãn liên tiếp để chung logic như `case "READ": case "SHOW":`. Hãy phân biệt **nhiều nhãn chung nhóm** với **vô tình rơi sang nhóm thực thi khác**.

## 5. Cú pháp `switch expression` hiện hành: nhãn hằng và default rõ ràng hơn

Trên Java 17+, có thể sử dụng cú pháp `switch expression` với các nhánh `->`. Tính năng expression và cú pháp rule này được chuẩn hóa từ **Java 14**, không nên gán ngược toàn bộ cú pháp ấy cho Java 7.

Tạo file `StringSwitchExpressionDemo.java`:

~~~java
public class StringSwitchExpressionDemo {
    static String route(String command) {
        if (command == null) {
            return "missing";
        }

        return switch (command) {
            case "CREATE", "SAVE" -> "write";
            case "READ", "SHOW" -> "read";
            default -> "unknown";
        };
    }

    public static void main(String[] args) {
        System.out.println(route("SAVE"));
        System.out.println(route("SHOW"));
        System.out.println(route("DELETE"));
        System.out.println(route(null));
    }
}
~~~

~~~bash
javac --release 17 StringSwitchExpressionDemo.java
java StringSwitchExpressionDemo
~~~

~~~text
write
read
unknown
missing
~~~

So sánh:

| Cú pháp | Cách xử lý nhiều nhãn | Có fall-through giữa các nhánh? | `default` |
| --- | --- | --- | --- |
| `switch statement` dùng `case "A":` | Đặt liên tiếp `case "A": case "B":` | **Có thể**, nếu thiếu điểm thoát | Thường nên có cho đầu vào không xác định |
| `switch expression` dùng `case "A", "B" ->` | Danh sách hằng cách nhau bằng dấu phẩy | **Không**; mỗi rule độc lập | Cần bảo đảm **exhaustiveness**; với `String` và chỉ liệt kê vài hằng thì cần `default` |
| `switch statement` dùng `case ... ->` | Có thể gom nhiều hằng | **Không** | Tùy nhu cầu với switch statement thông thường |

Đối với `switch expression` trên một miền giá trị `String` bất kỳ, chỉ liệt kê `"CREATE"` và `"READ"` không thể bao phủ hết các chuỗi. `default` cung cấp kết quả cho phần còn lại, để biểu thức luôn có nhánh xử lý với đầu vào phù hợp. Lưu ý `default` trong ví dụ vẫn **không bắt `null`** ở Java 17; guard đầu phương thức đã xử lý trường hợp đó.

Cú pháp `->` hữu ích khi mỗi case thực hiện một hành động hoặc trả một kết quả. Nó tránh lỗi fall-through của cú pháp dấu hai chấm. Với các case cần nhiều lệnh trong một `switch expression`, dùng block và `yield` để trả giá trị của nhánh (theo cú pháp hiện hành), không nhầm `yield` với `break`.

## 6. `null` và `default` theo từng mức Java

Đây là thay đổi thực tế cần phân biệt khi đọc JavaDoc hoặc review mã nguồn đa phiên bản.

**Java 17 / kiểu truyền thống:**

~~~java
if (command == null) {
    return "missing";
}
return switch (command) {
    case "START" -> "start";
    default -> "other";
};
~~~

Đoạn trên nằm **trong một phương thức trả `String`**. Guard xử lý null trước switch; áp dụng được cho Java 17 và các bản mới.

**Java 21+** cho phép nhãn đặc biệt `case null` trong switch đối với kiểu tham chiếu. Đoạn sau là **phương thức hoàn chỉnh để đặt trong một class**, yêu cầu Java 21+ khi biên dịch:

~~~java
static String classify(String command) {
    return switch (command) {
        case null -> "missing";
        case "START" -> "start";
        default -> "other";
    };
}
~~~

- `case null` nhận tham chiếu `null` thực sự; khác hoàn toàn `case "null"`, vốn chỉ nhận **chuỗi chứa bốn ký tự n-u-l-l**.
- Nếu chỉ có `default` mà **không có `case null`**, một selector `null` vẫn dẫn tới `NullPointerException` (với trường hợp switch tham chiếu thông thường).
- Java 21+ còn hỗ trợ nhãn kết hợp `case null, default` cho tình huống muốn gom chung, nhưng quy tắc kết hợp null với các nhãn khác bị giới hạn. Không suy diễn rằng có thể thêm `null` vào bất kỳ danh sách `case` hằng chuỗi nào.
- Chọn cú pháp theo **minimum Java version** của ứng dụng. Nếu phải hỗ trợ Java 17, guard `null` riêng như các ví dụ trước là cách rõ ràng, tương thích và không phụ thuộc vào cú pháp 21+.

Nguồn: [Pattern Matching for switch — Null case Labels (Java 25)](https://docs.oracle.com/en/java/javase/25/language/pattern-matching-switch.html) và [JLS §14.11](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html).

## 7. Tình huống vận dụng

### 7.1. Router lệnh có tập chuỗi hữu hạn

Một dịch vụ nhận `"CREATE"`, `"READ"` và `"DELETE"` có thể dùng `switch(String)` khi input đã được kiểm soát. Đặt nhãn bằng literal/hằng biên dịch, bảo đảm `default` có hành vi có chủ đích cho lệnh không hỗ trợ. Nếu đầu vào có thể null, chọn rõ chính sách null.

Với interface công khai, một lệnh lạ thường nên dẫn đến **lỗi đầu vào rõ nghĩa** hoặc kết quả “unsupported”, thay vì âm thầm đi qua. Nếu nghiệp vụ muốn không phân biệt hoa/thường hoặc bỏ khoảng trắng, xử lý chuẩn hóa đầu vào trước `switch` theo hợp đồng cụ thể; Java **không tự thực hiện** việc đó. Khi chuẩn hóa case theo quy tắc độc lập ngôn ngữ, ví dụ ứng dụng có thể cân nhắc `toUpperCase(Locale.ROOT)`, nhưng chỉ khi việc gộp chữ hoa/thường thực sự được phép. Không áp dụng chuẩn hóa ngầm cho mã định danh phân biệt hoa/thường hoặc dữ liệu cần so sánh nguyên bản.

### 7.2. Chọn cấu trúc theo bản chất dữ liệu

- **Ít nhãn chuỗi cố định, nhánh rõ ràng:** `switch(String)` là lựa chọn hợp lệ, dễ đọc.
- **Nhiều alias cùng xử lý:** gom các nhãn vào một nhóm `case:` hoặc một rule `case "A", "B" ->`, theo mức JDK.
- **Nhãn chỉ được biết khi chạy** (từ config/database): không thể khai báo thành `case`. Cân nhắc `Map<String, Handler>` hoặc chiến lược tra cứu runtime.
- **Tập trạng thái domain hữu hạn, ổn định:** có thể cân nhắc `enum` để tăng an toàn kiểu. Tuy nhiên API nhận đầu vào text vẫn cần ánh xạ/kiểm tra dữ liệu trước.
- **Đầu vào không hợp lệ là lỗi:** `default` có thể ném `IllegalArgumentException` hoặc trả kết quả có cấu trúc theo hợp đồng ứng dụng. Không giả định mọi lệnh lạ đều nên bị bỏ qua.

## 8. Các lỗi cần tránh khi viết và review

| Hiểu nhầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `case variable:` dùng được miễn variable có kiểu `String` | Nhãn cần **compile-time constant expression** | Dùng literal hoặc `final String` khởi tạo bằng biểu thức hằng |
| `final String x = read(); case x:` hợp lệ | `final` không biến lời gọi phương thức thành hằng | Dùng `if/else` hoặc tra cứu bằng `Map` khi giá trị là runtime |
| Hai case khác tên biến thì không trùng | Compiler xét **giá trị** hằng đã được tính | Kiểm tra trùng sau khi nối literal/hằng |
| `switch` dùng `==` nên `new String("X")` không khớp | Chuỗi được so theo nội dung qua `String.equals` | Không dựa vào intern/đồng nhất đối tượng |
| `default` sẽ xử lý cả `null` | Không có `case null` thì `null` gây NPE | Guard null hoặc Java 21+ `case null` |
| Thiếu `break` chỉ khiến bỏ qua code phía sau | Cú pháp `case:` có thể **fall-through** | `break`/`return`/`throw` hoặc chuyển sang `->` |
| `default` chạy nghĩa là không khớp case nào | Với fall-through, `default` có thể chạy sau một case đã khớp | Theo dõi luồng điều khiển từ nhãn đã được chọn |
| Nhãn `case "save"` khớp `"SAVE"` | So khớp chuỗi phân biệt hoa/thường | Chuẩn hóa có chủ đích hoặc viết nhãn khác |
| Có `default` nên switch expression Java 17 nhận null an toàn | `default` không bắt null | Guard null trước khi vào switch |
| Cú pháp `case null` có từ Java 7 | Bắt đầu hỗ trợ từ Java 21 | Ghi rõ `--release` và minimum JDK |

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Hai nhãn `case "A" + "B":` và `case "AB":` trong cùng switch có hợp lệ?  
**Đáp án:** Không. Cả hai đều là hằng chuỗi `"AB"`, tạo duplicate case label lúc biên dịch.

**Câu 2.** `final String MODE = System.getProperty("mode");` có dùng làm `case MODE:` được không?  
**Đáp án:** Không. Biến final nhưng initializer là lời gọi phương thức, giá trị được biết lúc chạy.

**Câu 3.** `switch (new String("OK"))` có khớp `case "OK":` không?  
**Đáp án:** Có. `String` được so khớp theo nội dung chứ không theo tham chiếu.

**Câu 4.** Trong `case "OPEN": print("open"); default: print("fallback");`, selector `"OPEN"` có thể in cả hai?  
**Đáp án:** Có, nếu không có `break`/`return`/`throw` sau nhánh `"OPEN"`. Đó là fall-through, không phải `default` khớp `"OPEN"`.

**Câu 5.** `default` có xử lý `null` trong Java 17?  
**Đáp án:** Không. Dùng guard null; còn `case null` là cú pháp từ Java 21+.

**Câu 6.** Một `switch expression` chỉ có `case "YES" -> true;` mà không có `default` có hợp lệ cho selector `String` tùy ý?  
**Đáp án:** Không. Switch expression phải exhaustive; một hằng không bao phủ mọi chuỗi. Thêm `default` hoặc thiết kế lại toàn bộ tập nhánh phù hợp.

## Tài liệu chính thức

- [Oracle — Strings in switch Statements, Java SE 7](https://docs.oracle.com/javase/7/docs/technotes/guides/language/strings-switch.html): bằng chứng **nguồn gốc** của khả năng dùng `String` làm selector.
- [Java SE 25 JLS §14.11 — switch Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.11): hợp đồng hiện hành về nhãn `case`, `default`, trùng nhãn và chọn nhánh.
- [JLS §15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.29): những biểu thức nào đủ điều kiện làm hằng chuỗi ở nhãn `case`.
- [JLS §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.28): tính exhaustive và cách biểu thức trả kết quả.
- [Java SE 25 — Pattern Matching for switch, Null case Labels](https://docs.oracle.com/en/java/javase/25/language/pattern-matching-switch.html): quy tắc hiện hành của `case null` và ranh giới hỗ trợ từ Java 21.

**Ghi nhớ khi viết code hôm nay:** nhãn `case` chuỗi phải là **hằng biên dịch**; `default` xử lý **giá trị không khớp**, không tự bắt `null` và không ngăn fall-through trong cú pháp dấu hai chấm. Hãy chọn kiểu `switch` và cách xử lý null phù hợp **phiên bản Java thấp nhất mà dự án hỗ trợ**.