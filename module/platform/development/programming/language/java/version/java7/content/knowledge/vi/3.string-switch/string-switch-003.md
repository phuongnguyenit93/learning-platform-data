# `switch` với `String`: so sánh nội dung và phân biệt chữ hoa, chữ thường

## 1. Điều quan trọng nhất cần hiểu

Từ Java 7, `switch` có thể nhận biểu thức kiểu `String`. Khi một giá trị `String` đi vào `switch`, Java tìm nhãn `case` có **nội dung chuỗi bằng với giá trị đầu vào**, theo quy tắc của `String.equals(Object)`. Phép so sánh này **phân biệt chữ hoa và chữ thường** (case-sensitive), đồng thời xét cả khoảng trắng và ký tự Unicode thực tế.

```java
String command = "START";

switch (command) {
    case "START":
        System.out.println("Bắt đầu");
        break;
    case "STOP":
        System.out.println("Dừng");
        break;
    default:
        System.out.println("Không biết lệnh");
}
```

Ở đoạn trên, chương trình chọn `case "START"`. Nếu `command` là `"start"` hoặc `"Start"`, chương trình đi vào `default` vì các chuỗi này **khác** `"START"` theo `String.equals`.

Đây là hành vi được đặc tả trong Java và vẫn áp dụng ở Java hiện đại. Cú pháp `case:`/`break` truyền thống của Java 7 cũng vẫn được hỗ trợ; ngoài ra, Java mới còn có biểu thức `switch` với dấu `->`, nhưng **quy tắc so sánh String chính xác vẫn như vậy**.

## 2. So sánh nội dung khác so sánh tham chiếu

Java có hai kiểu so sánh dễ bị nhầm:

| Cách viết | Đang so sánh điều gì? | Khi dùng với `String` |
| --- | --- | --- |
| `a == b` | Hai tham chiếu có trỏ tới **cùng đối tượng** hay không | Không phù hợp để kiểm tra hai chuỗi có cùng nội dung |
| `a.equals(b)` | Nội dung chuỗi có bằng nhau theo `String.equals` hay không | Phân biệt chữ hoa và chữ thường |
| `a.equalsIgnoreCase(b)` | Nội dung chuỗi có tương ứng khi bỏ qua khác biệt hoa/thường theo quy tắc API hay không | Không phải quy tắc mặc định của `switch` |

Ví dụ:

```java
String literal = "START";
String anotherObject = new String("START");

System.out.println(literal == anotherObject);             // false
System.out.println(literal.equals(anotherObject));        // true
System.out.println(literal.equals("start"));               // false
System.out.println(literal.equalsIgnoreCase("start"));     // true
```

`new String("START")` tạo một đối tượng khác, nên `==` với literal thường cho `false`; `equals` vẫn cho `true` vì ký tự của hai chuỗi giống nhau. Ngược lại, literal có thể được *intern* nên đôi khi `"START" == "START"` cũng cho `true`. Kết quả đó **không biến `==` thành cách so sánh nội dung đáng tin cậy**.

`switch` với `String` tuân theo **ngữ nghĩa của `equals`**, không tuân theo `==`. Vì vậy, `switch (new String("START"))` vẫn khớp `case "START"`.

## 3. `switch` phân biệt chữ hoa/chữ thường như thế nào?

`String.equals` so sánh nội dung chính xác (chuỗi các đơn vị mã UTF-16), không tự đổi chữ thường sang chữ hoa, không bỏ dấu và không tự loại khoảng trắng.

Với bộ nhãn:

```java
switch (status) {
    case "READY":
        System.out.println("Ready uppercase");
        break;
    case "ready":
        System.out.println("Ready lowercase");
        break;
    default:
        System.out.println("Other");
}
```

| `status` | Nhánh được chọn | Vì sao? |
| --- | --- | --- |
| `"READY"` | `case "READY"` | Nội dung trùng chính xác |
| `"ready"` | `case "ready"` | Đây là chuỗi khác `"READY"` |
| `"Ready"` | `default` | Không trùng chuỗi nào |
| `"READY "` | `default` | Có thêm dấu cách cuối |
| `" READY"` | `default` | Có thêm dấu cách đầu |
| `""` | `default` | Chuỗi rỗng không có nhãn tương ứng |

**Hai nhãn `"READY"` và `"ready"` hoàn toàn có thể cùng tồn tại** vì giá trị của chúng khác nhau. Nhưng hai `case "READY"` giống hệt nhau trong cùng `switch` sẽ gây **lỗi biên dịch do nhãn trùng**.

Cần phân biệt ba ý: **cùng nội dung**, **cùng chữ hoa/thường**, và **cùng tham chiếu đối tượng**. `switch` xét hai ý đầu thông qua `String.equals`; tham chiếu là đối tượng nào không làm thay đổi nhánh được chọn.

## 4. Cơ chế khớp chuỗi và va chạm `hashCode`

Một trình biên dịch Java có thể biến `switch (String)` thành mã dựa trên `String.hashCode()` kết hợp với phép so sánh nội dung. Đó là **chi tiết triển khai có thể khác giữa các trình biên dịch**, không phải quy tắc nghiệp vụ của `switch`.

Hai chuỗi khác nhau vẫn có thể có cùng mã băm:

```java
System.out.println("FB".hashCode() == "Ea".hashCode()); // true
System.out.println("FB".equals("Ea"));                  // false
```

Dù cùng `hashCode`, chương trình dưới đây vẫn phân biệt đúng hai `case`:

```java
String key = "Ea";
switch (key) {
    case "FB":
        System.out.println("Nhánh FB");
        break;
    case "Ea":
        System.out.println("Nhánh Ea");
        break;
    default:
        System.out.println("Khác");
}
```

Kết quả là `Nhánh Ea`. Vì vậy, **không nên suy luận rằng `switch` chỉ kiểm tra hash**, và càng không nên tự xây logic tương đương bằng cách so sánh riêng `hashCode()`.

## 5. Chương trình Java 17+ đầy đủ, chạy được

Ví dụ sau dùng cú pháp `switch` với `String` truyền thống để minh họa chính xác cơ chế so sánh vốn đã có từ Java 7. Chương trình xử lý cả đầu vào nguyên bản và cách nhận lệnh không phân biệt chữ hoa/thường.

Tạo tệp **`StringSwitchComparisonDemo.java`**:

```java
import java.util.Locale;

public final class StringSwitchComparisonDemo {

    static String exact(String command) {
        if (command == null) {
            return "missing";
        }

        switch (command) {
            case "START":
                return "start";
            case "STOP":
                return "stop";
            case "FB":
                return "fb";
            case "Ea":
                return "ea";
            default:
                return "unknown";
        }
    }

    static String insensitive(String command) {
        if (command == null) {
            return "missing";
        }

        switch (command.toUpperCase(Locale.ROOT)) {
            case "START":
                return "start";
            case "STOP":
                return "stop";
            default:
                return "unknown";
        }
    }

    public static void main(String[] args) {
        String input = new String("START");

        System.out.println("START=" + exact("START"));
        System.out.println("start=" + exact("start"));
        System.out.println("new=" + exact(input));

        System.out.println("identity=" + (input == "START"));
        System.out.println("content=" + input.equals("START"));
        System.out.println("ignoreCase="
                + "start".equalsIgnoreCase("START"));

        System.out.println("normalized=" + insensitive("sTaRt"));
        System.out.println("trailing=" + exact("START "));
        System.out.println("null=" + exact(null));

        System.out.println("collision="
                + ("FB".hashCode() == "Ea".hashCode()));
        System.out.println("FB=" + exact("FB"));
        System.out.println("Ea=" + exact("Ea"));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac StringSwitchComparisonDemo.java
java StringSwitchComparisonDemo
```

**Stdout chính xác:**

```text
START=start
start=unknown
new=start
identity=false
content=true
ignoreCase=true
normalized=start
trailing=unknown
null=missing
collision=true
FB=fb
Ea=ea
```

Giải thích các điểm dễ nhầm:

1. `exact("START")` tìm đúng nhãn `"START"`; `exact("start")` không tìm được do khác chữ hoa/thường.
2. Chuỗi được tạo bằng `new String("START")` vẫn khớp `case "START"`, dù `input == "START"` là `false`.
3. `equalsIgnoreCase` có thể cho `true` với `"start"` và `"START"`, nhưng `switch` **không tự sử dụng** phương thức này.
4. `insensitive("sTaRt")` đổi chữ về hoa theo `Locale.ROOT` trước khi đưa vào `switch`, nên nhận lệnh thành công.
5. `exact("START ")` không trùng vì có thêm khoảng trắng.
6. `exact(null)` trả `"missing"` nhờ kiểm tra `null` **trước khi** thực hiện `switch`.
7. Hai chuỗi `"FB"` và `"Ea"` va chạm hash nhưng vẫn vào hai nhánh riêng.

## 6. Nếu cần so sánh **không** phân biệt hoa/thường

Cú pháp `case "START":` **luôn là so sánh chính xác**. Không có tuỳ chọn tích hợp dạng “ignore case” cho một `switch` thông thường. Cần xác định yêu cầu của dữ liệu để chọn cách xử lý.

### 6.1. Chỉ kiểm tra một hay vài giá trị: `equalsIgnoreCase`

```java
String command = "sTaRt";

if ("START".equalsIgnoreCase(command)) {
    System.out.println("Lệnh bắt đầu");
} else if ("STOP".equalsIgnoreCase(command)) {
    System.out.println("Lệnh dừng");
} else {
    System.out.println("Lệnh khác");
}
```

Đặt hằng chuỗi ở phía gọi `equalsIgnoreCase` giúp an toàn nếu `command == null`: phương thức trả `false`. Với `equals` cũng tương tự: `"START".equals(command)` tránh gọi phương thức trên tham chiếu `null`.

`equalsIgnoreCase` so sánh không phụ thuộc `Locale`, phù hợp cho một số phép so sánh đơn giản. Nó **không phải** quy trình chuẩn hoá văn bản theo mọi ngôn ngữ, không tự bỏ dấu và không có nghĩa rằng mọi cách viết Unicode tương đương ngữ nghĩa đều được gộp lại.

### 6.2. Nhiều nhãn: chuẩn hoá đầu vào rồi `switch`

Với tập lệnh máy nhỏ, được định nghĩa bằng ký tự ASCII như `START`/`STOP`, có thể chuyển đầu vào về cùng dạng chữ:

```java
import java.util.Locale;

String command = "sTaRt";

if (command != null) {
    switch (command.toUpperCase(Locale.ROOT)) {
        case "START":
            System.out.println("Lệnh bắt đầu");
            break;
        case "STOP":
            System.out.println("Lệnh dừng");
            break;
        default:
            System.out.println("Lệnh khác");
    }
}
```

- `Locale.ROOT` biểu thị quy tắc chuyển chữ **không phụ thuộc ngôn ngữ của máy đang chạy**, phù hợp để chuẩn hoá những mã lệnh nội bộ có quy tắc cố định.
- Với input `"sTaRt"`, kết quả chuẩn hoá là `"START"` rồi khớp `case "START"`.
- **Chuẩn hoá đúng một lần trước `switch`**, tránh nhân bản nhiều biến thể của mỗi `case`.
- Đây là lựa chọn tốt cho **mã lệnh ASCII được đặc tả là không phân biệt hoa/thường**. Không mặc định rằng mọi tên riêng, từ tự nhiên, chuỗi Unicode hoặc định danh đều có cùng quy tắc tương đương.

**Tránh dùng `command.toUpperCase()` không có `Locale` cho mã lệnh dùng xuyên máy/địa phương.** Phương thức không có đối số phụ thuộc locale mặc định của tiến trình; ví dụ quy tắc chữ `i` trong tiếng Thổ Nhĩ Kỳ có thể tạo kết quả khác. Cần một chuẩn cố định, vì vậy dùng `Locale.ROOT` cho token máy; khi xử lý ngôn ngữ tự nhiên, dùng locale và quy tắc đối chiếu phù hợp với bài toán.

### 6.3. Không tự động loại khoảng trắng hoặc bỏ dấu

`"START "` khác `"START"`. Chỉ thêm `trim()` hoặc `strip()` nếu đặc tả đầu vào thực sự cho phép bỏ khoảng trắng. `strip()` có trên Java 11+, phân loại khoảng trắng theo Unicode; `trim()` dùng quy tắc cũ hẹp hơn. Chọn API theo yêu cầu, không “sửa” dữ liệu âm thầm.

Với tiếng Việt hoặc chuỗi Unicode, hai cách mã hoá nhìn gần giống nhau có thể khác về chuỗi đơn vị mã. Chẳng hạn ký tự `"é"` dạng dựng sẵn và tổ hợp `"e"` + dấu kết hợp có thể hiển thị giống nhưng `String.equals` cho `false`. Nếu hệ thống yêu cầu đối chiếu theo dạng Unicode chuẩn, hãy chuẩn hoá **theo hợp đồng** (chẳng hạn `java.text.Normalizer.Form.NFC`) trước khi so sánh; `switch` tự nó không làm việc này.

Cũng cần phân biệt **bỏ qua hoa/thường** với **bỏ dấu tiếng Việt**: hai việc này không giống nhau. Không nên dùng cách chuyển chữ hoặc xoá dấu tùy tiện cho định danh, dữ liệu bảo mật hay mã cần khớp chính xác.

## 7. `null`, `default` và phạm vi phiên bản Java

Trong **`switch (String)` kiểu Java 7**, selector bằng `null` gây `NullPointerException`, **không đi vào `default`**. Vì vậy:

```java
String command = null;

// switch (command) { // Nếu chạy theo dạng Java 7 không có case null:
//     default: System.out.println("Không xác định");
// } // sẽ ném NullPointerException

if (command == null) {
    System.out.println("Thiếu lệnh");
} else {
    switch (command) {
        case "START":
            System.out.println("Lệnh bắt đầu");
            break;
        default:
            System.out.println("Lệnh khác");
    }
}
```

Từ **Java 21**, cú pháp `switch` có hỗ trợ `case null` để chủ động xử lý `null`; đây là khả năng mới của Java, **không sử dụng được khi biên dịch với Java 7 hay `--release 17`**. Ví dụ riêng cho **Java 21+**:

```java
static String classify(String value) {
    return switch (value) {
        case null -> "missing";
        case "START" -> "start";
        default -> "unknown";
    };
}
```

Dù dùng kiểu `switch` nào, nhãn `default` có nghĩa “không khớp nhãn khác” và **không mang ý nghĩa “bỏ qua chữ hoa/thường”**. Nó cũng không tự sửa các lỗi đầu vào.

## 8. Quy tắc `case` và những nhầm lẫn khi triển khai

### 8.1. Nhãn `case` là hằng chuỗi tại thời điểm biên dịch

`case` nhận **biểu thức hằng** có giá trị `String`, không được dùng chuỗi chỉ xác định khi chạy chương trình:

```java
static final String START = "START"; // hằng compile-time

// Hợp lệ bên trong một phương thức:
switch (command) {
    case START:
        System.out.println("Bắt đầu");
        break;
    default:
        System.out.println("Khác");
}
```

Ở đây `START` là hằng `static final` được khởi tạo bằng literal. Ngược lại:

```java
String dynamic = System.getenv("COMMAND");

// switch (command) {
//     case dynamic:        // sai: dynamic không phải hằng compile-time
//         break;
// }
```

Không thể viết `case command.equalsIgnoreCase("START"):` để thay đổi cách so sánh của `switch`: nhãn `case` cần hằng phù hợp với kiểu selector, còn `equalsIgnoreCase` trả `boolean` và phụ thuộc dữ liệu lúc chạy.

### 8.2. Cú pháp cũ cần xử lý `break` hoặc `return` đúng

```java
switch (command) {
    case "START":
        System.out.println("Start");
        break;
    case "STOP":
        System.out.println("Stop");
        break;
    default:
        System.out.println("Unknown");
}
```

Trong `switch` kiểu dấu hai chấm, **thiếu `break` hoặc `return` có thể làm lệnh chạy tiếp sang nhánh sau** (*fall-through*), kể cả khi giá trị đầu vào không khớp nhãn tiếp theo. Hành vi này không phải do so sánh chuỗi bị lỗi.

Có thể cố ý gom hai giá trị để thực hiện chung một thao tác:

```java
switch (command) {
    case "START":
    case "RUN":
        System.out.println("Start action");
        break;
    default:
        System.out.println("Other");
}
```

Chỉ gom các giá trị được đặc tả là đồng nghĩa; đừng đưa `"start"` vào chỉ để “đoán” đầu vào không phân biệt chữ hoa/thường, vì sẽ khó quản lý khi có nhiều nhãn.

### 8.3. Phân biệt giới hạn phiên bản với tính đúng đắn

- **Java 7+:** `switch` nhận `String` và phân nhánh theo nội dung `equals`, case-sensitive. Cú pháp truyền thống vẫn hợp lệ ngày nay.
- **Java 14+:** biểu thức `switch` và dạng mũi tên `->` là cú pháp chuẩn; khi so sánh với hằng `String`, vẫn dùng quy tắc khớp nội dung chính xác.
- **Java 21+:** có thể viết `case null` theo ngữ pháp `switch` mới. Luôn kiểm tra phiên bản mục tiêu của ứng dụng trước khi dùng.

Bài này tập trung vào **hành vi so sánh của `switch` với `String`**, áp dụng cả khi dùng ngữ pháp truyền thống hoặc dạng mới.

## 9. Lỗi phổ biến và cách sửa

| Lỗi hoặc nhận định sai | Cách hiểu/sửa đúng |
| --- | --- |
| `switch` dùng `==` để so sánh `String` | Java đặc tả so khớp bằng nội dung, theo `String.equals`. |
| `case "OK"` cũng nhận `"ok"` | Sai; tự chuẩn hoá theo quy tắc đầu vào hoặc dùng `equalsIgnoreCase` ở nhánh `if`. |
| Hai đối tượng `String` khác nhau không thể vào cùng `case` | Sai; tham chiếu khác nhau vẫn có thể mang cùng nội dung. |
| Hai chuỗi có cùng `hashCode()` sẽ vào cùng `case` | Sai; va chạm hash không làm hai chuỗi `equals`. |
| `default` bắt cả selector bằng `null` trong Java 7 | Sai; sẽ có `NullPointerException` nếu chưa kiểm tra `null`. |
| `"GO"` và `"GO "` luôn trùng nhau | Sai; khoảng trắng cũng là ký tự của chuỗi. |
| Dùng `toUpperCase()` ở mọi máy là giống nhau | Không bảo đảm; kết quả có thể phụ thuộc locale mặc định. Với token ASCII, dùng `Locale.ROOT`. |
| `equalsIgnoreCase` xoá dấu và chuẩn hoá Unicode | Sai; nó giải quyết một kiểu so sánh hoa/thường, không thay mọi quy tắc Unicode/ngôn ngữ. |
| Đặt `case` bằng biến `String` thông thường | Chỉ hằng biểu thức chuỗi tại lúc biên dịch mới được làm nhãn `case`. |
| Quên `break` nhưng tưởng `switch` so sánh sai | Sai; nhánh sau có thể chạy do fall-through của cú pháp truyền thống. |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `switch (new String("YES"))` có khớp `case "YES"` không?  
**Đáp án:** Có. `switch` so sánh **nội dung**, không yêu cầu hai tham chiếu là một đối tượng.

**Câu 2.** `case "ACTIVE"` có khớp `"active"` không?  
**Đáp án:** Không. Hai chuỗi khác nhau về chữ hoa/thường.

**Câu 3.** Vì sao `"FB"` và `"Ea"` vẫn có thể là hai `case` riêng khi chúng cùng `hashCode`?  
**Đáp án:** Vì ngữ nghĩa khớp chuỗi là `equals`; hai chuỗi này có nội dung khác nhau.

**Câu 4.** Với bộ lệnh ASCII `START`/`STOP`, làm sao cho `"Start"`, `"start"`, `"START"` cùng vào một nhánh mà không viết ba `case`?  
**Đáp án:** Kiểm tra `null` rồi chuẩn hoá bằng `command.toUpperCase(Locale.ROOT)` trước `switch`.

**Câu 5.** `default` có tự xử lý được `null` trong `switch` kiểu Java 7 không?  
**Đáp án:** Không. Cần guard `null` trước; với Java 21+ có thể dùng `case null` khi mục tiêu biên dịch cho phép.

**Câu 6.** Có nên tự chuyển tên người dùng, mật khẩu hoặc mã định danh sang chữ thường trước `switch` không?  
**Đáp án:** Chỉ khi hợp đồng dữ liệu **nói rõ** rằng giá trị đó không phân biệt hoa/thường. Các chuỗi yêu cầu khớp chính xác phải giữ nguyên.

## 11. Ghi nhớ và tài liệu chuẩn

**Ghi nhớ:** `switch (String)` **khớp nội dung như `String.equals`**, nên **phân biệt chữ hoa/thường**; nó không dùng `==`, không bỏ khoảng trắng, không chuẩn hoá ngôn ngữ. Nếu bài toán yêu cầu đối chiếu không phân biệt chữ hoa/thường, hãy thực hiện chính sách đó **tường minh** và phù hợp với dữ liệu đầu vào. Bảo vệ `null` theo phiên bản Java, và nhớ `break`/`return` trong cú pháp `switch` truyền thống.

Tài liệu chính thức còn hiệu lực:

- [Java Language Specification, `14.11 — The `switch` Statement](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.11): quy tắc so khớp nhãn `case`, bao gồm `String`.
- [Java SE 17 API — `String.equals` và `String.equalsIgnoreCase`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): ngữ nghĩa của các phương thức so sánh.
- [Java SE API — `Locale.ROOT`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale không phụ thuộc ngôn ngữ khi chuẩn hoá mã lệnh.