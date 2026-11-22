# `var` với kết quả `switch` và giới hạn thông tin kiểu (Java 14+)

## 1. Hiểu đúng vai trò của `var` và `switch` biểu thức

Từ Java 14, `switch` biểu thức (*switch expression*) là tính năng chính thức: mỗi nhánh cung cấp một giá trị (hoặc ném ngoại lệ), và toàn bộ `switch` có thể đứng bên phải phép gán. Cú pháp `var` dành cho **suy luận kiểu biến cục bộ** đã có từ Java 10 và vẫn được sử dụng trong Java hiện đại. Hai tính năng này có thể kết hợp:

```java
int code = 1;
var status = switch (code) {
    case 0 -> "Chờ";
    case 1 -> "Đang xử lý";
    default -> "Không xác định";
};
```

Đây là **đoạn mã đặt trong một phương thức**, không phải chương trình độc lập. Vì tất cả các nhánh đều tạo ra `String`, trình biên dịch suy luận rằng biến cục bộ `status` có **kiểu tĩnh `String`**. Có thể gọi `status.length()`, `status.toUpperCase()`, ... như mọi biến `String` khác.

**`var` không có nghĩa là "kiểu bất kỳ", "kiểu động" hay "giữ nguyên mọi kiểu có thể xảy ra".** Khi biên dịch, Java xác định **một kiểu tĩnh cụ thể** cho biến dựa trên biểu thức khởi tạo; sau đó kiểu này bị cố định. Ví dụ:

```java
var status = switch (1) {
    case 0 -> "Chờ";
    default -> "Sẵn sàng";
};
status = "Đã xong";  // Đúng: vẫn là String
// status = 123;      // Sai: không thể gán int cho String
```

`var` chỉ thay thế việc viết tên kiểu **khi khai báo biến cục bộ có giá trị khởi tạo**. Nó không phải cú pháp khai báo kiểu trả về của phương thức hay trường thành viên.

## 2. Vì sao `var` với `switch` có thể suy luận kiểu khác điều ta tưởng?

Có hai tình huống quan trọng theo quy tắc kiểu của Java:

**Trường hợp A — có kiểu đích rõ ràng (*target type*)**

```java
Number value = switch (code) {
    case 0 -> Integer.valueOf(7);
    default -> Double.valueOf(3.5);
};
```

Trong ngữ cảnh gán cho biến `Number`, `switch` có thể được kiểm tra theo **kiểu đích `Number`**. Mỗi nhánh cung cấp một giá trị tương thích với `Number`; biến `value` có kiểu tĩnh `Number` và có thể chứa đối tượng `Integer` hoặc `Double` tùy nhánh. `value.doubleValue()` hợp lệ vì đó là phương thức của `Number`.

**Trường hợp B — khởi tạo bằng `var`**

```java
var value = switch (code) {
    case 0 -> Integer.valueOf(7);
    default -> Double.valueOf(3.5);
};
```

Ở đây, không có tên kiểu đích do người lập trình khai báo. `switch` được xét như **biểu thức độc lập (*standalone expression*)** để suy luận kiểu. Vì cả hai biểu thức kết quả có thể chuyển thành kiểu số, Java thực hiện **numeric promotion**: `Integer` và `Double` được chuyển sang giá trị số phù hợp, kết quả có kiểu **`double`**. Vì vậy `var value` tương đương về kiểu tĩnh với `double value`, chứ **không** suy ra `Number`.

Ví dụ, khi `code = 0`, trường hợp A có thể giữ một đối tượng `Integer(7)`, còn trường hợp B cho ra `double` có giá trị `7.0`. Khác biệt này do **ngữ cảnh xác định kiểu ở thời điểm biên dịch**, không do `var` tự đổi kiểu khi chạy.

> Ghi nhớ: biến khai báo tường minh như `Number value = switch (...) { ... };` cung cấp kiểu đích. Còn `var value = switch (...) { ... };` cần suy ra kiểu từ tất cả **biểu thức kết quả** của các nhánh, kể cả nhánh không được chọn ở một lần chạy cụ thể.

## 3. Quy tắc suy luận kiểu khi `switch` là biểu thức độc lập

Khi dùng `var` trực tiếp với `switch`, có thể vận dụng các trường hợp sau:

| Kết quả của các nhánh | Kiểu suy luận điển hình | Ví dụ |
| --- | --- | --- |
| Tất cả cùng kiểu `String` | `String` | `"A"` và `"B"` |
| Tất cả cùng kiểu `int` | `int` | `1` và `2` |
| Kết quả `boolean` / `Boolean` | `boolean` khi trộn hai kiểu này | `true` và `Boolean.FALSE` |
| Kết quả số khác kiểu | Kiểu số sau **numeric promotion** | `10` và `2.5` ⇒ `double` |
| Kết quả kiểu tham chiếu khác nhau và không thuộc nhóm số | Kiểu chung do quy tắc **least upper bound** xác định, có thể gồm nhiều interface | `String` và `StringBuilder` |
| Một nhánh `throw`, các nhánh khác cho giá trị | Kiểu được xác định từ **các nhánh cho giá trị** | `String` hoặc ném ngoại lệ |

Đối với kiểu tham chiếu, quy tắc thực tế có thêm *boxing*, *least upper bound* và *capture conversion*. Không nên kết luận rằng `var` luôn chọn `Object` hoặc luôn chọn "kiểu của nhánh đầu tiên". Trình biên dịch xét **toàn bộ các biểu thức kết quả có thể dùng**, không dựa trên nhánh thực thi.

Ví dụ khác của numeric promotion:

```java
int level = 0;
var score = switch (level) {
    case 0 -> 10;    // int
    default -> 2.5;  // double
};
System.out.println(score); // 10.0
```

Mặc dù nhánh được chọn trả literal `10` (kiểu `int`), `score` có kiểu `double` vì nhánh khác cho `2.5`. Khi chạy, Java chuyển `10` thành `10.0` phù hợp với kiểu kết quả đã xác định.

## 4. Ví dụ hoàn chỉnh trên JDK 17+

Lưu toàn bộ chương trình vào **`Main.java`**:

```java
import java.util.List;

public class Main {
    public static void main(String[] args) {
        int mode = 0;

        // Tất cả nhánh trả String -> var suy luận String.
        var label = switch (mode) {
            case 0 -> "Chờ";
            case 1 -> "Đang làm";
            default -> "Khác";
        };

        // Tất cả nhánh trả int -> var suy luận int.
        var count = switch (mode) {
            case 0 -> 10;
            default -> 20;
        };

        // int + double -> numeric promotion -> double.
        var rate = switch (mode) {
            case 0 -> 10;
            default -> 2.5;
        };

        // Có kiểu đích Number: giữ đối tượng Integer hoặc Double.
        Number boxedNumber = switch (mode) {
            case 0 -> Integer.valueOf(7);
            default -> Double.valueOf(3.5);
        };

        // Không có kiểu đích: Integer + Double -> double.
        var promotedNumber = switch (mode) {
            case 0 -> Integer.valueOf(7);
            default -> Double.valueOf(3.5);
        };

        // Kiểu đích tường minh giúp thể hiện ý định của API.
        List<String> names = switch (mode) {
            case 0 -> List.of("Java", "Switch");
            default -> List.of("Khác");
        };

        // yield cũng là một biểu thức kết quả của switch.
        var note = switch (mode) {
            case 0 -> {
                String prefix = "Mức";
                yield prefix + " cơ bản";
            }
            default -> "Mức khác";
        };

        System.out.println(label);
        System.out.println(count + 5);
        System.out.println(rate);
        System.out.println(boxedNumber.getClass().getSimpleName());
        System.out.println(promotedNumber);
        System.out.println(names.get(0));
        System.out.println(note);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Kết quả chính xác:**

```text
Chờ
15
10.0
Integer
7.0
Java
Mức cơ bản
```

**Diễn giải:** `label` là `String`; `count` là `int`; `rate` là `double` nên in `10.0`. Cùng một nhánh `mode = 0`, `boxedNumber` vẫn chứa đối tượng `Integer` vì khai báo có kiểu đích `Number`, trong khi `promotedNumber` có kiểu nguyên thủy `double` và in `7.0`. `names` được khai báo rõ là `List<String>`. Khối có `yield` tạo giá trị `String` cho `note` như nhánh mũi tên trả chuỗi trực tiếp.

Đoạn trên chỉ dùng cú pháp đã ổn định; không cần cờ `--enable-preview`.

## 5. Giới hạn thông tin kiểu: kiểu chung không đồng nghĩa với kiểu cụ thể từng nhánh

Giả sử một nhánh trả `String`, nhánh khác trả `StringBuilder`:

```java
int mode = 1;
var text = switch (mode) {
    case 0 -> "Ready";                     // String
    default -> new StringBuilder("Wait"); // StringBuilder
};

System.out.println(text.length()); // 4
// text.substring(0, 2);           // Không dùng được trực tiếp theo kiểu chung suy luận
```

Đoạn mã đặt trong một phương thức. `String` và `StringBuilder` đều thực hiện interface `CharSequence`, có phương thức `length()`. Tuy nhiên biến `text` không được bảo đảm mang **kiểu tĩnh `String`** hoặc **`StringBuilder`** riêng; trình biên dịch suy ra kiểu chung theo luật Java (có thể là một kiểu giao của nhiều interface). Do đó không thể mặc định dùng mọi API đặc thù của từng lớp, như `String.substring(...)`, thông qua `text`.

Nếu muốn hợp đồng kiểu rõ ràng, khai báo:

```java
CharSequence text = switch (mode) {
    case 0 -> "Ready";
    default -> new StringBuilder("Wait");
};
System.out.println(text.length()); // Được khai báo trong CharSequence
```

Nếu mọi nhánh **phải** cho một `String`, hãy chuẩn hóa kết quả tại từng nhánh:

```java
String text = switch (mode) {
    case 0 -> "Ready";
    default -> new StringBuilder("Wait").toString();
};
System.out.println(text.substring(0, 2)); // Có API String
```

Cả hai cách đều minh bạch ý định: dùng kiểu chung nếu cần các cách biểu diễn chuỗi khác nhau, hoặc dùng `String` nếu người gọi cần API `String`. Ép kiểu thủ công từ kiểu chung sang `String` khi không chắc nhánh nào được chọn có thể gây `ClassCastException`.

## 6. Generic và bộ sưu tập: `var` không tự cung cấp hợp đồng API

Khi các nhánh trả những lớp bộ sưu tập khác nhau, kiểu tự suy luận có thể rộng hơn hoặc phức tạp hơn kiểu bạn muốn công bố:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

// Đoạn mã bên trong một phương thức:
int mode = 0;
var list = switch (mode) {
    case 0 -> new ArrayList<String>(List.of("A"));
    default -> new LinkedList<String>(List.of("B"));
};
System.out.println(list.get(0)); // A
```

Cả hai nhánh đều có phần tử `String`, nhưng chúng là hai lớp cụ thể khác nhau. Suy luận kiểu tham chiếu có thể cho ra kiểu chung của các lớp, bao gồm interface hoặc kiểu giao; không nên đọc chữ `var` và mặc định đó là đúng `ArrayList<String>`, `LinkedList<String>` hay chính xác `List<String>`.

Nếu yêu cầu nghiệp vụ là "một danh sách chuỗi", nên viết kiểu đích rõ ràng:

```java
List<String> list = switch (mode) {
    case 0 -> new ArrayList<>(List.of("A"));
    default -> new LinkedList<>(List.of("B"));
};
```

Khai báo này làm hợp đồng kiểu `List<String>` hiển thị ngay cho người đọc và cho trình biên dịch biết kiểu đích khi kiểm tra các nhánh, hữu ích với generic, toán tử kim cương `<>` và lời gọi phương thức generic như `List.of(...)`.

Ví dụ cần chú ý về generic:

```java
List<? extends Number> numbers = switch (mode) {
    case 0 -> List.of(1, 2);
    default -> List.of(2.5, 3.5);
};
System.out.println(numbers.get(0).doubleValue());
```

Kiểu đích `List<? extends Number>` cho phép các nhánh trả danh sách các kiểu số cụ thể khác nhau. Nếu đổi khai báo này thành `var numbers = ...`, suy luận generic phụ thuộc vào cả hai nhánh và có thể xuất hiện wildcard/kiểu chung phức tạp; **đừng giả định** kết quả là `List<Number>`.

## 7. `var` không thay thế kiểm tra kiểu ở thời điểm biên dịch

Trong `switch` biểu thức, một kiểu kết quả phải được xác định từ toàn bộ các nhánh cho giá trị; `var` không cho phép một biến tự thay đổi kiểu theo từng nhánh.

**Sai: chỉ nhìn nhánh được chọn tại runtime để giả định biến có kiểu đó.**

```java
int code = 0;
var item = switch (code) {
    case 0 -> "READY";
    default -> 500;
};
// item.toUpperCase(); // Không hợp lệ: kiểu suy luận không được bảo đảm là String
```

`String` và `int` không cùng kiểu. Java sẽ xét các nhánh theo quy tắc boxing và kiểu chung; tại thời điểm biên dịch không được coi `item` là `String` chỉ vì `code = 0`. Chẳng hạn `item.toString()` vẫn có ý nghĩa thông qua kiểu tham chiếu chung, nhưng `item.toUpperCase()` không được đảm bảo tồn tại.

**Đúng: chọn kiểu đích rõ ràng khi kết quả thực sự dị loại.**

```java
Object item = switch (code) {
    case 0 -> "READY";
    default -> 500;
};
System.out.println(item); // READY
```

Dùng `Object` chỉ khi hợp đồng thực sự cho phép nhiều loại giá trị. Trong thiết kế API thông thường, nên chọn một kiểu chung có ý nghĩa hơn (`Number`, `CharSequence`, interface nghiệp vụ, kiểu kết quả riêng), hoặc chuẩn hóa các nhánh sang cùng một kiểu.

**Sai: khai báo lại `var` mà không có khởi tạo hoặc gán kiểu không phù hợp.**

```java
// var result; // Lỗi: var phải có biểu thức khởi tạo

var result = switch (code) {
    case 0 -> "OK";
    default -> "FAIL";
};
// result = 42; // Lỗi: result đã có kiểu String
```

`var` không làm giảm việc kiểm tra kiểu. Nó chỉ giảm phần tên kiểu viết ở khai báo.

## 8. Trường hợp `null`, `throw` và `yield`

**Chỉ có `null`:** Kiểu của literal `null` không đủ để suy luận kiểu biến `var`.

```java
// Cố ý sai: toàn bộ kết quả đều là null
// var missing = switch (code) {
//     case 0 -> null;
//     default -> null;
// };
```

Nếu về mặt nghiệp vụ thật sự cần một kết quả nullable, có thể khai báo rõ kiểu:

```java
String missing = switch (code) {
    case 0 -> null;
    default -> null;
};
```

Đoạn trên là Java hợp lệ, nhưng một biến luôn `null` thường không mang giá trị nghiệp vụ; ví dụ dùng để phân biệt cơ chế xác định kiểu, không phải khuyến nghị thiết kế. Khi có các nhánh khác trả `String`, bạn vẫn nên xem xét cách kiểm soát `null` phù hợp trước khi gọi phương thức trên kết quả.

**Nhánh `throw`:** Một nhánh chỉ ném ngoại lệ không có biểu thức kết quả để xác định kiểu.

```java
static String commandName(int code) {
    return switch (code) {
        case 1 -> "START";
        case 2 -> "STOP";
        default -> throw new IllegalArgumentException("Mã không hợp lệ");
    };
}
```

Ở đây hai nhánh sinh `String`; nhánh `default` kết thúc bằng ngoại lệ. Nếu **mọi** nhánh đều chỉ `throw` thì `switch` biểu thức không có biểu thức kết quả nào; đó là lỗi biên dịch, kể cả khi khai báo biến với kiểu tường minh.

**Nhánh khối `yield`:** Kiểu kết quả được xét từ biểu thức **sau `yield`**, không phải từ các biến trung gian trong khối.

```java
var description = switch (code) {
    case 0 -> {
        int id = 100;
        yield "ID-" + id;
    }
    default -> "Không có";
};
// description có kiểu String.
```

`id` là `int` nhưng giá trị `yield` là chuỗi `"ID-100"`, nên `description` là `String`. Không dùng `break` hoặc `return` thay cho `yield` để tạo kết quả của khối `switch` biểu thức.

**Giá trị selector và giá trị trả về là hai vấn đề khác nhau:** `var` xác định kiểu **kết quả** của `switch`, không thay đổi kiểu selector bên trong `switch (selector)`. Khi selector là `String` hoặc `enum`, cần xử lý `null` theo cú pháp và phiên bản Java được sử dụng; `var` không bổ sung cơ chế xử lý `null`.

## 9. Tính đầy đủ của `switch` vẫn bắt buộc khi dùng `var`

Một `switch` biểu thức phải bảo đảm có kết quả ở mọi trường hợp hợp lệ (hoặc ném ngoại lệ). Với selector `int` hoặc `String` và chỉ một số hằng, thường cần `default`.

```java
int month = 4;
var quarter = switch (month) {
    case 1, 2, 3 -> "Q1";
    case 4, 5, 6 -> "Q2";
    case 7, 8, 9 -> "Q3";
    case 10, 11, 12 -> "Q4";
    default -> throw new IllegalArgumentException("Tháng không hợp lệ");
};
```

`quarter` có kiểu `String`; nếu `month` là `4`, giá trị là `"Q2"`. Dùng `var` **không làm** một `switch` thiếu nhánh trở thành đầy đủ. Với selector kiểu `enum`, có thể bỏ `default` khi các nhãn đã bao phủ mọi hằng enum ở thời điểm biên dịch.

## 10. Khi nào chọn `var`, khi nào ghi kiểu tường minh?

| Hoàn cảnh | Cách viết nên cân nhắc | Lý do |
| --- | --- | --- |
| Mọi nhánh trả cùng một kiểu rõ ràng | `var label = switch (...) { ... };` | Ngắn, ít lặp tên kiểu, dễ suy luận. |
| Các nhánh trả các kiểu số khác nhau | `double total = switch (...) { ... };` nếu cần `double` | Cho thấy rõ quy tắc numeric promotion và kiểu mong đợi. |
| Các nhánh trả nhiều lớp con của cùng API | `Number number = ...` hoặc `List<String> values = ...` | Hợp đồng kiểu dễ hiểu, ít bất ngờ khi sửa nhánh. |
| Generic/phương thức generic phụ thuộc kiểu đích | Khai báo kiểu đích tường minh | Hỗ trợ kiểm tra nhánh và suy luận generic theo ý định. |
| Một nhánh có thể trả kiểu khác trong tương lai | Kiểu tường minh của hợp đồng API | Thay đổi kiểu nhánh sẽ được phát hiện rõ tại nơi gán. |
| Muốn dùng phương thức chỉ có ở một lớp cụ thể | Chuẩn hóa mọi nhánh sang lớp đó hoặc dùng interface thích hợp | `var` không tự phục hồi API chỉ có ở một nhánh. |

Nguyên tắc thực tế: **Dùng `var` khi kiểu kết quả suy luận ngay được và đáp ứng đúng cách sử dụng của biến. Dùng kiểu tường minh khi muốn người đọc và trình biên dịch thấy rõ hợp đồng kết quả, đặc biệt với số hỗn hợp, generic hoặc nhiều lớp triển khai.**

## 11. Tự kiểm tra

Xét đoạn mã trong một phương thức:

```java
int choice = 1;
var response = switch (choice) {
    case 0 -> 10;
    case 1 -> 20L;
    default -> 30;
};
System.out.println(response);
```

1. `response` có kiểu gì? **`long`**, vì `int` và `long` áp dụng numeric promotion.
2. Giá trị in ra? **`20`**, vì `choice = 1` chọn nhánh `20L`.
3. Nếu `case 1 -> "20";` thì `response` có còn là `long`? **Không**. Có nhánh chuỗi khiến Java áp dụng quy tắc kiểu tham chiếu/boxing cho biểu thức độc lập; kết quả không còn một kiểu số `long` duy nhất.
4. Muốn biến luôn là `Number`? **Khai báo `Number response = switch (...)`** và bảo đảm mọi nhánh trả kết quả tương thích `Number`, không trả chuỗi.

**Kiến thức cần nhớ:** `var` suy luận một **kiểu tĩnh duy nhất** từ toàn bộ `switch` biểu thức ở thời điểm biên dịch. Kết quả của `switch` có thể được suy ra khác khi có kiểu đích tường minh. Hãy chú ý numeric promotion, kiểu chung của các nhánh tham chiếu, generic, `null` và `yield`; chọn kiểu tường minh khi nó diễn đạt rõ hơn ý định thiết kế.

### Tham khảo chính thức

- [Java Language Specification — `15.28: switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [Java Language Specification — `14.4.1: Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.4.1).
