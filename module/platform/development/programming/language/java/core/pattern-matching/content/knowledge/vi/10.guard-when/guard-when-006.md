# Sắp xếp guard cụ thể trước guard tổng quát trong Java

## 1. Vấn đề: nhiều `case ... when` có thể cùng đúng

**Pattern matching for `switch`**, chính thức từ **Java 21** (JEP 441), cho phép một nhãn `case` gồm **pattern** và điều kiện bảo vệ (*guard*):

```java
case String s when s.isBlank() -> System.out.println("Blank");
```

Java trước tiên thử xem giá trị selector có khớp `String s` không; nếu khớp thì khởi tạo biến pattern `s` và đánh giá `s.isBlank()`. Rule chỉ được chọn khi **cả pattern và guard đều khớp**.

Điểm quan trọng: **Các nhãn `case` được xem xét theo thứ tự xuất hiện trong switch block.** Khi nhiều nhãn có thể nhận cùng một giá trị, nhãn phù hợp đầu tiên là nhãn được chọn. Không có cơ chế tự động đoán nhãn nào “cụ thể hơn” về nghiệp vụ.

Ví dụ:

```java
static String label(Object input) {
    return switch (input) {
        case String s when s.isBlank() -> "blank";
        case String s when s.length() <= 4 -> "short";
        case String s -> "other text";
        case null -> "null";
        default -> "other";
    };
}
```

Với giá trị `"  "` (hai dấu cách), **cả hai guard đầu đều đúng**: chuỗi trắng và có độ dài 2. Java chọn rule `isBlank()` vì nó **đứng trước**. Nếu đảo vị trí hai rule, chương trình vẫn có thể biên dịch nhưng `"  "` sẽ được gán nhãn `"short"` thay vì `"blank"`.

Đó là lý do của quy tắc thiết kế:

> **Đặt các trường hợp đặc biệt, ưu tiên cao, dễ bị bao phủ ở phía trước; đặt các trường hợp rộng hơn phía sau; kết thúc bằng nhánh không guard hoặc `default` khi cần.**

“Cụ thể” ở đây là **mức độ ưu tiên nghiệp vụ và tập giá trị được phép nhận**, không chỉ quan hệ kế thừa lớp.

## 2. Cách Java chọn rule có guard

Với `switch` sử dụng type pattern trong Java 21, luồng xét nhãn theo thứ tự mã nguồn có thể mô tả như sau:

1. Tính giá trị selector `switch (input)` một lần.
2. Xem nhãn `case` đầu tiên có áp dụng cho giá trị đó không.
3. Nếu nhãn chứa pattern, kiểm tra pattern. **Chỉ khi pattern khớp** mới có pattern variables để đánh giá `when`.
4. Nếu guard không đúng, tiếp tục tìm nhãn phù hợp kế tiếp. Nếu guard đúng, chọn rule và thực thi phần bên phải `->`.
5. Với arrow rule, không tự chạy tiếp xuống rule dưới (*không fall-through*).
6. Nếu không nhãn nào phù hợp, việc xử lý phụ thuộc tính bao phủ của switch; với enhanced switch, trình biên dịch yêu cầu đủ các nhãn để bao phủ các giá trị được phép.

Quy tắc chọn nhãn không phải là gọi tất cả các guard rồi lấy kết quả “đặc biệt nhất”. Ngay khi một rule được chọn, các guard đứng **sau rule đó không còn được đánh giá cho lần switch này**.

### Guard sai khác guard ném ngoại lệ

```java
case String s when s.length() > 10 -> System.out.println("long");
```

Nếu `s.length() > 10` là `false`, Java thử nhãn sau. Nhưng nếu **biểu thức guard ném ngoại lệ**, switch bị kết thúc đột ngột theo ngoại lệ, chứ không xem ngoại lệ như giá trị `false`. Vì vậy nên dùng guard ngắn, an toàn và hạn chế tác dụng phụ.

### Chỉ đánh giá guard sau khi khớp pattern

```java
case String s when s.startsWith("ERR:") -> System.out.println(s);
```

`String s` không khớp `Integer`, `null` hay kiểu khác. Khi không khớp, Java không thể dùng `s` để chạy guard. Việc truy cập `s.startsWith(...)` hợp lệ vì guard chỉ được xét sau khi `s` đã được ràng buộc với một đối tượng `String` không null.

## 3. Ví dụ rõ nhất: guard cho chuỗi trắng và chuỗi ngắn

Giả sử chương trình cần phân loại chuỗi thành ba nhóm:

- **Trắng**: `s.isBlank()`.
- **Ngắn nhưng không được ưu tiên là trắng**: `s.length() <= 4`.
- **Các chuỗi còn lại**: nhánh `case String s` không guard.

Thứ tự **đúng theo yêu cầu nghiệp vụ**:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.isBlank() -> "blank";
        case String s when s.length() <= 4 -> "short";
        case String s -> "text";
        default -> "other";
    };
}
```

Thứ tự **không phù hợp** khi muốn nhận diện chuỗi trắng trước:

```java
static String classifyPoorly(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.length() <= 4 -> "short";
        case String s when s.isBlank() -> "blank";
        case String s -> "text";
        default -> "other";
    };
}
```

Hai hàm đều có thể **biên dịch hợp lệ trên Java 21**, bởi Java không chứng minh tổng quát rằng `isBlank()` có tập giá trị nằm hoàn toàn trong điều kiện `length() <= 4`. Nhưng kết quả khác nhau:

| Đầu vào | Guard `isBlank()` trước | Guard `length() <= 4` trước |
| --- | --- | --- |
| `"  "` | `"blank"` | `"short"` |
| `""` | `"blank"` | `"short"` |
| `"Hi"` | `"short"` | `"short"` |
| `"Java"` | `"short"` | `"short"` |
| `"Pattern"` | `"text"` | `"text"` |

Với đầu vào `""`, cả hai guard đúng: `isBlank()` đúng và `length()` bằng 0. Nếu muốn chuỗi rỗng/trắng được xử lý đặc biệt, nó phải đứng trước nhánh ngắn.

**Cách làm chặt chẽ hơn:** nếu hai quy tắc dễ bị chồng lấn, vừa sắp xếp ưu tiên, vừa có thể làm rõ sự loại trừ:

```java
case String s when s.isBlank() -> "blank";
case String s when !s.isBlank() && s.length() <= 4 -> "short";
case String s -> "text";
```

Guard thứ hai loại trừ chuỗi trắng một cách tường minh. Điều đó giúp giải thích thiết kế dễ hơn; vẫn nên đặt các nhánh theo thứ tự ưu tiên mong muốn.

## 4. Ưu tiên mã lỗi trước phân loại độ dài

Một ví dụ thực tế khác là chuỗi có prefix `"ERR:"`:

```java
static String route(Object input) {
    return switch (input) {
        case String s when s.startsWith("ERR:") -> "error";
        case String s when s.length() <= 4 -> "short";
        case String s -> "other text";
        case null -> "null";
        default -> "other";
    };
}
```

Giá trị `"ERR:"` đồng thời thỏa điều kiện prefix và điều kiện độ dài 4. Nếu quy tắc nghiệp vụ yêu cầu **nhận diện thông báo lỗi trước**, nhãn `startsWith("ERR:")` phải đứng trên nhãn `length() <= 4`.

Đặt nhánh ngắn trước có thể khiến mã lỗi được phân loại sai mà compiler **không nhất thiết báo lỗi dominance**. Đây là **xung đột logic tại runtime**, khác với trường hợp một pattern bị che toàn bộ mà JLS có thể phát hiện ngay khi biên dịch.

Nên thiết kế thứ tự theo câu hỏi:

1. Trường hợp nào quan trọng hơn khi **nhiều điều kiện cùng đúng**?
2. Có điều kiện nào là **tập con** của điều kiện khác theo nghiệp vụ?
3. Có một rule cuối **không guard** để bao phủ các giá trị còn lại của cùng kiểu không?
4. Có `case null` và `default` nếu selector có thể nhận giá trị ngoài các kiểu được liệt kê không?

## 5. Guard cụ thể, guard tổng quát và type pattern tổng quát

“Guard tổng quát” không đồng nghĩa với “pattern tổng quát”. Cần phân biệt ba tầng:

| Dạng `case` | Ví dụ | Mức độ khớp |
| --- | --- | --- |
| Pattern + guard cụ thể | `case String s when s.isBlank()` | Chỉ chuỗi trắng |
| Pattern + guard rộng | `case String s when s.length() <= 4` | Mọi chuỗi dài tối đa 4, gồm chuỗi trắng ngắn |
| Pattern không guard | `case String s` | Mọi chuỗi không null |
| Pattern kiểu cha | `case CharSequence cs` | `String` cùng các lớp khác triển khai `CharSequence` |
| `default` | `default` | Các giá trị không null chưa được chọn |

Một pattern không guard `case String s` được đặt **trước** `case String s when s.isBlank()` sẽ che nhánh guarded phía sau: nó khớp tất cả `String`, không để lại chuỗi nào cho nhánh kia. Đây là tình huống **dominance** mà trình biên dịch Java 21 phát hiện.

Ví dụ **không biên dịch** (mảnh mã minh họa trong cùng một switch):

```java
// KHÔNG HỢP LỆ:
case String s -> System.out.println("any String");
case String s when s.isBlank() -> System.out.println("blank"); // Bị che.
```

Sửa bằng cách đổi thứ tự:

```java
// HỢP LỆ khi đặt trong một switch có selector tương thích:
case String s when s.isBlank() -> System.out.println("blank");
case String s -> System.out.println("any other String");
```

Tương tự, khi trộn lớp cha và lớp con, nhãn không guard của lớp cha có thể che nhãn lớp con:

```java
// KHÔNG HỢP LỆ nếu ở cùng switch:
case CharSequence cs -> System.out.println("char sequence");
case String s -> System.out.println("string"); // String đã bị che.
```

**Khắc phục:** đặt `case String s` hoặc các nhãn String có guard trước, rồi mới đến `case CharSequence cs` nếu muốn phân biệt riêng String.

### Lỗi dominance khác lỗi ưu tiên nghiệp vụ

- **Compile-time dominance**: một nhãn trước theo quy tắc JLS đã bao phủ nhãn sau, ví dụ `case String s` trước một `case String s when ...`. Java 21 từ chối biên dịch.
- **Runtime overlap**: hai guard tùy ý có miền khớp giao nhau, ví dụ `s.isBlank()` và `s.length() <= 4`. Java không suy luận tổng quát mọi quan hệ logic giữa các biểu thức guard; chương trình có thể biên dịch, nhưng **thứ tự khiến kết quả thay đổi**.

Một guard luôn đúng về mặt toán học cũng không nên dùng để “thay” pattern không guard: thiết kế rõ ràng và dễ hiểu hơn là dùng `case String s` làm nhánh cuối của nhóm String.

## 6. Pattern variable và scope của `when`

Trong một rule:

```java
case String s when s.length() > 4 -> System.out.println(s.toUpperCase());
```

Biến `s` được tạo khi pattern `String s` khớp. Nó dùng được:

1. Trong guard **`when s.length() > 4`** của chính nhãn ấy;
2. Trong biểu thức, lệnh hoặc block bên phải `->` thuộc chính rule ấy.

Không thể lấy biến pattern của rule trước để dùng trong `when` hoặc RHS của rule sau. Hai rule khác nhau có thể dùng **cùng tên** `s` vì mỗi nhãn là một khai báo pattern variable độc lập:

```java
switch (input) {
    case String s when s.isBlank() -> System.out.println("blank " + s.length());
    case String s when s.length() <= 4 -> System.out.println("short " + s);
    case String s -> System.out.println("text " + s);
    default -> System.out.println("other");
}
```

Đoạn này là một switch statement minh họa với biến `input` được khai báo phù hợp và **giả định không truyền `null`**; nếu cần hỗ trợ null, thêm `case null`. Biến `s` ở nhánh thứ nhất và biến `s` ở nhánh thứ hai **không phải cùng một biến**.

Guard thường dùng các phương thức của kiểu vừa khớp, ví dụ `String.isBlank`, `String.length`, `Integer.signum`, hoặc các điều kiện kết hợp `&&`, `||`. Mọi điều kiện phụ nên không có tác dụng phụ không cần thiết vì việc đổi thứ tự rule sẽ đổi cả thứ tự gọi các guard.

## 7. Chương trình Java 21+ hoàn chỉnh

Lưu vào file **`GuardOrderingDemo.java`**:

```java
public class GuardOrderingDemo {
    static String route(Object value) {
        return switch (value) {
            case null -> "null";

            case String s when s.isBlank() -> "blank";

            case String s when s.startsWith("ERR:") ->
                    "error-code=" + s.substring(4);

            case String s when s.length() <= 4 -> "short: " + s;

            case String s -> "text: " + s;

            case Integer n when n == 0 -> "zero";

            case Integer n when n < 0 -> "negative: " + n;

            case Integer n when n <= 10 -> "small positive: " + n;

            case Integer n -> "large positive: " + n;

            default -> "other";
        };
    }

    static String badOrder(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.length() <= 4 -> "short";
            case String s when s.isBlank() -> "blank";
            case String s when s.startsWith("ERR:") -> "error";
            case String s -> "text";
            default -> "other";
        };
    }

    static void announce(Object value) {
        switch (value) {
            case null -> System.out.println("ANNOUNCE null");
            case String s when s.isBlank() ->
                    System.out.println("ANNOUNCE blank");
            case String s when s.length() <= 4 ->
                    System.out.println("ANNOUNCE short");
            case String s -> System.out.println("ANNOUNCE text");
            default -> System.out.println("ANNOUNCE other");
        }
    }

    public static void main(String[] args) {
        System.out.println(route("  "));
        System.out.println(route("ERR:42"));
        System.out.println(route("ok"));
        System.out.println(route("Java 21"));
        System.out.println(route(0));
        System.out.println(route(-4));
        System.out.println(route(7));
        System.out.println(route(21));
        System.out.println(route(null));
        System.out.println(route(2.5));

        System.out.println("wrong blank: " + badOrder("  "));
        System.out.println("right blank: " + route("  "));
        System.out.println("wrong error: " + badOrder("ERR:"));
        System.out.println("right error: " + route("ERR:"));

        announce(" ");
        announce("Hi");
    }
}
```

Biên dịch và chạy với **JDK 21 trở lên**, không cần `--enable-preview`:

```bash
javac GuardOrderingDemo.java
java GuardOrderingDemo
```

**Standard output chính xác:**

```text
blank
error-code=42
short: ok
text: Java 21
zero
negative: -4
small positive: 7
large positive: 21
null
other
wrong blank: short
right blank: blank
wrong error: short
right error: error-code=
ANNOUNCE blank
ANNOUNCE short
```

**Lý giải theo thứ tự:**

1. `"  "` là chuỗi trắng và ngắn. Hàm `route` ưu tiên `isBlank()`, nên trả `blank`.
2. `"ERR:42"` có prefix `"ERR:"`, không trắng, nên trả `error-code=42` trước khi kiểm tra độ dài.
3. `"ok"` ngắn (2 ký tự) nên trả `short: ok`; `"Java 21"` dài hơn 4 nên đến rule `case String s` không guard.
4. `Integer` 0, -4, 7, 21 lần lượt khớp guard số 0, số âm, số dương nhỏ, rồi nhánh Integer tổng quát.
5. `null` được `case null` xử lý riêng; `2.5` được boxing thành `Double`, không thuộc nhóm `String`/`Integer`, nên vào `default`.
6. Trong `badOrder`, guard độ dài đứng trước. Vì thế `"  "` thành `"short"` thay vì `"blank"`, và `"ERR:"` thành `"short"` thay vì `"error"`.
7. `route("ERR:")` khớp prefix trước, `substring(4)` là chuỗi rỗng, nên in `right error: error-code=` (không có ký tự nào sau dấu `=`).
8. `announce` là **switch statement** với arrow rules. Các guard vẫn được xét theo thứ tự; nhánh được chọn in thông tin rồi dừng, không fall through.

Chương trình chứng minh sự khác biệt giữa **thứ tự quy tắc đúng ý đồ** và **thứ tự vẫn biên dịch nhưng phân loại sai**, đồng thời cho thấy quy tắc áp dụng như nhau cho `switch expression` và `switch statement`.

## 8. Cách sắp xếp guard theo nhiều tầng ưu tiên

Với các rule nhiều điều kiện, một cách ổn định là đặt ưu tiên theo tầng:

1. **Giá trị đặc biệt** cần chính sách riêng: ví dụ `case null`, chuỗi trắng, mã lỗi nghiêm trọng, số 0.
2. **Guard chuyên biệt**: ví dụ `startsWith("ERR:")`, `n < 0`, hoặc `n > 1000`.
3. **Guard bao trùm rộng hơn**: ví dụ `s.length() <= 4`, `n <= 10`.
4. **Pattern cùng kiểu không guard**: ví dụ `case String s`, `case Integer n`.
5. **Pattern kiểu cha hoặc `default`**: dành cho các kiểu còn lại.

Thứ tự chỉ là khung gợi ý; **ý đồ nghiệp vụ mới quyết định cụ thể là gì**. Ví dụ trong hệ thống log, một chuỗi rỗng có thể được coi là lỗi định dạng và phải kiểm tra trước mọi prefix. Trong một chương trình khác, một prefix đặc biệt có thể có ưu tiên cao hơn phân loại độ dài.

### Guard loại trừ lẫn nhau thì sao?

Nếu các guard **không thể cùng đúng**, đổi thứ tự chúng thường không đổi kết quả. Ví dụ, với `Integer n`:

```java
case Integer n when n < 0 -> "negative";
case Integer n when n == 0 -> "zero";
case Integer n when n > 0 -> "positive";
```

Ba điều kiện trên loại trừ lẫn nhau về mặt giá trị số, nên mỗi `Integer` chỉ khớp tối đa một guard. Tuy vậy vẫn cần bảo đảm các trường hợp còn lại của selector được bao phủ. Có thể dùng `case Integer n -> ...` làm nhánh dự phòng rõ ràng; nếu thiếu nhánh cuối, trong một switch chỉ có selector `Integer`, compiler không nhất thiết suy ra rằng ba guard tùy ý đã bao phủ mọi số nguyên.

**Không nên trông cậy vào trình biên dịch chứng minh các bất đẳng thức trong guard để xác nhận exhaustiveness.** Trình biên dịch áp dụng các quy tắc pattern/label ở mức ngôn ngữ, không chạy một bộ giải tổng quát cho mọi predicate nghiệp vụ.

### Dùng guard tinh gọn, không có side effect

Tránh các guard ghi log, thay đổi biến đếm hoặc gọi API gây side effect chỉ để xác định một nhánh:

```java
// Không khuyến nghị:
// case String s when externalService.recordAndCheck(s) -> ...
```

Việc đổi thứ tự nhãn, thêm một nhánh mới hoặc thất bại của guard có thể khiến side effect chạy ở thời điểm khác. Nên tính các dữ kiện cần thiết trước switch, hoặc tách kiểm tra thuần (*pure predicate*) khỏi hành động cần thực hiện sau khi chọn rule.

## 9. Dominance, `when` và các lỗi biên dịch cần phân biệt

### 9.1. Pattern không guard đứng trước guard

**Sai vì dominance**:

```java
// Minh họa trong cùng một switch(Object value):
// case String s -> "all strings";
// case String s when s.isBlank() -> "blank"; // Compiler từ chối.
```

**Đúng**:

```java
// Trong switch expression có selector và các nhánh bao phủ khác:
case String s when s.isBlank() -> "blank";
case String s -> "other strings";
```

Nhánh String không guard phải đặt **sau cùng** trong các nhánh String nếu muốn các trường hợp được guard xử lý trước.

### 9.2. Kiểu cha không guard đứng trước kiểu con

**Sai vì dominance**:

```java
// Trong cùng switch(Object value):
// case CharSequence cs -> "any char sequence";
// case String s -> "string"; // String bị che.
```

**Đúng**:

```java
// Trong switch expression tương thích:
case String s -> "string";
case CharSequence cs -> "another char sequence";
```

Dù `String` và `CharSequence` đều có thể khớp giá trị `"abc"`, nhánh chuyên biệt được đặt trước; `CharSequence` xử lý các đối tượng khác triển khai interface này.

### 9.3. Hai guard tùy ý chồng lấn nhưng vẫn biên dịch

```java
// Hợp lệ nhưng thứ tự có thể làm sai ý đồ:
case String s when s.length() <= 4 -> "short";
case String s when s.isBlank() -> "blank";
case String s -> "other";
```

Với `" "`, rule đầu đã khớp và rule thứ hai không chạy. Đây là **lỗi phân loại logic**, không phải một lỗi dominance mà compiler nhất thiết phải phát hiện.

### 9.4. `when` chỉ áp dụng cho nhãn có pattern

```java
// Không phải cách viết hợp lệ của Java 21:
// case "ERR:" when flag -> "error";
```

Nếu selector là `String`, có thể dùng `case "ERR:" -> ...` làm nhãn hằng số riêng, rồi bổ sung các rule khác. Nếu cần guard dựa trên dữ liệu của chuỗi, dùng `case String s when s.equals("ERR:") && flag -> ...` trong ngữ cảnh thích hợp.

### 9.5. `default` và `null`

Trong switch Java 21, **`case String s` không khớp `null`**, và `default` thông thường không tự xử lý selector `null`. Nếu selector có thể null, thêm `case null -> ...` (hoặc dùng nhãn đặc biệt `case null, default` khi phù hợp). Thiếu nhãn null có thể khiến `switch(null)` ném `NullPointerException`.

### 9.6. Enhanced switch và exhaustiveness

`switch expression` phải bao phủ đủ các giá trị có thể gặp; `switch statement` dùng pattern cũng thuộc nhóm enhanced switch statement và phải **exhaustive**. Với selector kiểu `Object`, hãy có `default` nếu các pattern chưa bao phủ toàn bộ các giá trị không null.

Một nhánh `case Object o` là pattern rất rộng. Khi selector đã là `Object`, không nên đặt nó cạnh `default` như hai nhánh tổng quát đối địch; chọn chiến lược bao phủ phù hợp và xử lý null một cách rõ ràng.

### 9.7. Switch rule và statement group khác nhau

Trong switch rule `case ... -> ...`, không có fall-through. Trong switch statement dùng nhóm lệnh `case ...:`, Java có cơ chế fall-through hạn chế bởi quy tắc bảo đảm pattern variable được khởi tạo. **Đổi thứ tự nhãn không chỉ ảnh hưởng việc chọn rule mà còn có thể ảnh hưởng luồng lệnh** nếu dùng cú pháp `:`. Với phân loại nhiều guard, `->` thường dễ kiểm soát hơn.

## 10. Bài tập thực hành

1. **Chuỗi trắng và chuỗi ngắn.** Tạo switch expression với `case String s when s.isBlank()`, `case String s when s.length() <= 5` và `case String s`. Thử đầu vào `""`, `" "`, `"Hi"`, `"Java 21"`. Đảo thứ tự hai guard đầu và ghi lại kết quả khác nhau.
2. **Thông điệp lỗi.** Viết rule `case String s when s.startsWith("ERR:")` rồi rule `case String s when s.length() <= 4`. Thử `"ERR:"`, `"ERR:404"`, `"OK"`. Giải thích vì sao cần ưu tiên prefix trước độ dài.
3. **Khoảng số chồng lấn.** Với `Integer n`, viết guard `n == 0`, `n < 0`, `n <= 10`, rồi `case Integer n`. Thử `0`, `-4`, `5`, `20`. Đảo thứ tự `n <= 10` lên trước `n == 0` và giải thích vì sao nhánh số 0 bị bắt mất.
4. **Lỗi dominance.** Đặt `case String s` trước `case String s when s.isBlank()` và quan sát lỗi compiler. Sửa thứ tự. So sánh với việc đặt `when s.length() <= 5` trước `when s.isBlank()`, là trường hợp có thể biên dịch nhưng sai logic.
5. **Guard loại trừ.** Viết các nhánh `n < 0`, `n == 0`, `n > 0` và thử đổi thứ tự. Giải thích vì sao kết quả không đổi với `Integer` khi điều kiện thực sự loại trừ nhau; thêm nhánh dự phòng để bảo đảm tính bao phủ.
6. **Phạm vi pattern variable.** Viết hai rule `case String s when ...` khác nhau dùng cùng tên `s`; giải thích lý do hợp lệ. Thử sử dụng `s` bên ngoài switch để thấy lỗi.
7. **Null và kiểu khác.** Dùng selector `Object`, thêm `case null` và `default`. Kiểm tra `null`, `Double`, `String` và `Integer` để bảo đảm mọi đường đi có chủ đích.
8. **Bài toán nghiệp vụ.** Thiết kế bộ phân loại yêu cầu có ưu tiên: tài khoản bị khóa, giao dịch quá hạn, giao dịch số tiền lớn, rồi yêu cầu thông thường. Xác định các guard nào có thể cùng đúng; viết thứ tự, sau đó viết bảng test cho các điểm giao nhau.
9. **Record pattern (Java 21+).** Tạo `record Request(String path, int priority) {}`. Dùng hai nhánh: `case Request(String path, int priority) when path.startsWith("/admin") && priority >= 10`, rồi `case Request(String path, int priority) when priority >= 10`, và nhánh Request tổng quát. Giải thích vì sao “quyền admin khẩn cấp” phải đứng trước “mọi yêu cầu khẩn cấp”.

**Ghi nhớ:** Java chọn **nhãn `case` phù hợp đầu tiên**, không tự chọn guard “cụ thể nhất”. Với guard chồng lấn, thứ tự là một phần của logic nghiệp vụ. Đặt guard chuyên biệt trước guard rộng, pattern không guard sau cùng trong nhóm cùng kiểu, và kiểm tra cả **dominance lúc biên dịch** lẫn **overlap lúc chạy**.

## Tài liệu tham khảo

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [JLS 21, §14.11 — Switch Statements, switch labels và dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11).
- [JLS 21, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
- [JLS 21, §6.3.3 — Scope for Pattern Variables in case Labels](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3.3).
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
