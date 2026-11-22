# Pattern dominance và các nhánh không thể tới

Trong pattern matching for `switch` của Java 21, thứ tự các nhãn `case` ảnh hưởng trực tiếp đến nhánh được chọn. Nếu một nhãn đứng trước đã bao phủ toàn bộ giá trị mà nhãn phía sau có thể khớp, nhãn phía sau bị **dominated** (bị chi phối). Đây là lỗi biên dịch, giúp phát hiện những nhánh không thể được chọn theo quy tắc kiểu của Java.

Hiểu pattern dominance giúp sắp xếp các nhánh từ trường hợp cụ thể đến trường hợp tổng quát, kết hợp guard `when` đúng cách, và tránh những lỗi thường gặp khi dùng type patterns, record patterns hoặc sealed hierarchy. Nội dung dưới đây sử dụng cú pháp pattern switch đã trở thành chính thức trong Java 21.

## 1. Pattern dominance là gì?

Một nhãn `case` bị dominated khi mọi giá trị có thể khớp với nhãn đó đều đã được một nhãn đứng trước xử lý. Vì switch xét các nhãn theo thứ tự, nhãn phía sau sẽ không có cơ hội được chọn.

Ví dụ:

```java
static void describe(Object value) {
    switch (value) {
        case Object object -> System.out.println("An object");
        case String text -> System.out.println("A string"); // Lỗi biên dịch
    }
}
```

`String` là kiểu con của `Object`. Mọi giá trị khớp với `String text` cũng khớp với `Object object`, nên nhánh `String` bị nhãn đầu tiên chi phối. Trình biên dịch báo lỗi thay vì cho phép giữ một nhánh không thể được chọn.

Có thể hình dung quan hệ này như sau:

```text
Object
  └── String
```

Khi `Object` được kiểm tra trước, nhánh dành riêng cho `String` không còn giá trị phân loại. Nếu muốn xử lý riêng chuỗi, hãy đặt kiểu hẹp hơn trước:

```java
static void describe(Object value) {
    switch (value) {
        case String text -> System.out.println("A string: " + text);
        case Object object -> System.out.println("An object: " + object);
    }
}
```

`String` không chi phối `Object`, vì còn nhiều đối tượng khác không phải chuỗi. Hai nhánh trên có thể cùng tồn tại.

## 2. Quy tắc giữa các type patterns

Với type patterns, pattern có kiểu tổng quát hơn có thể chi phối pattern có kiểu cụ thể hơn. Ví dụ:

```java
static void inspect(CharSequence value) {
    switch (value) {
        case CharSequence sequence -> System.out.println(sequence.length());
        case String text -> System.out.println(text.toUpperCase()); // Dominated
    }
}
```

`String` triển khai `CharSequence`, vì vậy mọi chuỗi đều khớp với nhánh `CharSequence`. Nhánh `String` phải đứng trước:

```java
static void inspect(CharSequence value) {
    switch (value) {
        case String text -> System.out.println(text.toUpperCase());
        case CharSequence sequence -> System.out.println(sequence.length());
    }
}
```

Một quy tắc hữu ích là đặt kiểu con trước kiểu cha khi cả hai cần cách xử lý riêng. Nhánh tổng quát hơn được đặt sau để nhận các giá trị còn lại.

Không phải hai kiểu có quan hệ kế thừa ở đâu đó cũng luôn gây dominance. Điều cần xét là pattern đứng trước có bao phủ mọi giá trị mà pattern phía sau có thể khớp hay không, dựa trên kiểu selector và quy tắc chuyển đổi kiểu của Java.

## 3. Record patterns cũng có thể chi phối nhau

Record Pattern không chỉ kiểm tra kiểu record bên ngoài mà còn kiểm tra từng thành phần. Vì vậy, dominance có thể xảy ra ở cấp thành phần và được áp dụng đệ quy với record lồng nhau.

Ví dụ:

```java
record Box(Object value) {
}

static String describe(Box box) {
    return switch (box) {
        case Box(Object value) -> "Any payload";
        case Box(String text) -> "Text: " + text; // Dominated
    };
}
```

Hai pattern cùng mô tả record `Box`. Trong pattern đầu tiên, thành phần `Object value` bao phủ mọi giá trị có thể khớp với thành phần kiểu `String` ở pattern thứ hai. Do đó, pattern thứ hai bị chi phối.

Đổi thứ tự sẽ giữ được cả hai trường hợp:

```java
static String describe(Box box) {
    return switch (box) {
        case Box(String text) -> "Text: " + text;
        case Box(Object value) -> "Any payload";
    };
}
```

Quy tắc này áp dụng cả với record lồng nhau. Ví dụ, nếu một record `Response` chứa `Box`, pattern rộng ở thành phần `Box` có thể chi phối pattern hẹp hơn ở cùng vị trí lồng đó. Khi đọc một pattern dài, hãy so sánh cấu trúc record từ ngoài vào trong và kiểm tra từng cặp component pattern tương ứng.

Lưu ý: một record pattern không được xem là unconditional cho toàn bộ kiểu record, vì giá trị `null` không khớp với record pattern. Tuy nhiên, hai record patterns có cùng record class vẫn có thể được so sánh dominance dựa trên các component patterns tương ứng.

## 4. Guard `when` thay đổi cách xác định dominance

Guard `when` bổ sung điều kiện sau khi giá trị đã khớp với pattern. Guard được đánh giá tại runtime, nên trình biên dịch thường không thể chứng minh điều kiện đó đúng hay sai cho mọi giá trị.

Ví dụ sau hợp lệ:

```java
static String classify(String text) {
    return switch (text) {
        case String value when value.length() == 2 -> "Two characters";
        case String value -> "Other string";
    };
}
```

Pattern đầu tiên chỉ xử lý chuỗi có độ dài bằng hai. Nếu pattern khớp nhưng guard trả về `false`, switch tiếp tục xét nhãn sau. Vì vậy, guarded pattern thông thường không chi phối một unguarded pattern giống nó.

Chiều ngược lại gây lỗi:

```java
static String classify(String text) {
    return switch (text) {
        case String value -> "Any string";
        case String value when value.length() == 2 -> "Two characters"; // Dominated
    };
}
```

Pattern `String value` không có guard đã nhận mọi chuỗi trước đó. Nhánh có guard phía sau không thể được chọn.

Có một ngoại lệ quan trọng: guard là constant expression có giá trị `true` được xem như pattern không guard khi xét dominance:

```java
static String classify(String text) {
    return switch (text) {
        case String value when true -> "Any string";
        case String value -> "Other string"; // Dominated
    };
}
```

Nhánh đầu tiên tương đương một pattern không guard về mặt bao phủ, nên nhánh sau bị chi phối. Trong Java 21, guard là constant expression có giá trị `false` cũng là lỗi biên dịch; không dùng `when false` để tạo một nhánh bị vô hiệu hóa.

## 5. Compiler không chứng minh toàn bộ logic của guard

Dominance là phép kiểm tra tĩnh theo quy tắc của ngôn ngữ, không phải công cụ chứng minh mọi biểu thức điều kiện trong chương trình. Với guard không phải constant expression `true`, compiler không phân tích đầy đủ nội dung logic để kết luận guard luôn đúng hoặc luôn sai.

Ví dụ:

```java
static String classify(Integer number) {
    return switch (number) {
        case Integer value when value > 0 -> "Positive";
        case 1 -> "One";
        case Integer value -> "Other integer";
    };
}
```

Đây là thứ tự nhãn được Java chấp nhận theo quy tắc dominance: guarded pattern không chi phối nhãn hằng `1`. Tuy nhiên, trong thực tế, khi `number` bằng `1`, guard `value > 0` đã đúng và nhánh `case 1` không được chọn. Compiler không suy luận điều đó từ biểu thức guard.

Vì thế, để mã dễ đọc và tránh nhánh bị che khuất về mặt logic, nên sắp xếp theo thứ tự:

1. Các hằng số cụ thể.
2. Các pattern có guard, từ điều kiện cụ thể đến tổng quát.
3. Các pattern không guard, từ kiểu cụ thể đến kiểu tổng quát.
4. `default` nếu thực sự cần.

Thứ tự này là quy ước tổ chức mã dễ hiểu; quy tắc biên dịch chính xác vẫn được xác định bởi JLS.

## 6. Pattern có thể chi phối nhãn hằng số

Dominance không chỉ áp dụng giữa hai pattern. Một unguarded pattern có thể chi phối nhãn `case` chứa hằng số nếu pattern đó là unconditional cho kiểu của hằng số.

Ví dụ với `Integer`:

```java
static void inspect(Integer number) {
    switch (number) {
        case Integer value -> System.out.println("An integer");
        case 42 -> System.out.println("The answer"); // Dominated
    }
}
```

`Integer value` bao phủ mọi giá trị `Integer` không null, bao gồm cả `42`. Do đó, `case 42` bị chi phối.

Tương tự với `String`:

```java
static void inspect(String text) {
    switch (text) {
        case String value -> System.out.println("A string");
        case "JAVA" -> System.out.println("Java"); // Dominated
    }
}
```

Và với enum:

```java
enum Status { NEW, RUNNING, DONE }

static void inspect(Status status) {
    switch (status) {
        case Status value -> System.out.println(value);
        case NEW -> System.out.println("New status"); // Dominated
    }
}
```

Nếu cần xử lý riêng một hằng số, hãy đặt nhãn hằng trước pattern tổng quát:

```java
static void inspect(Integer number) {
    switch (number) {
        case 42 -> System.out.println("The answer");
        case Integer value -> System.out.println("Other integer: " + value);
    }
}
```

Một guarded pattern không chi phối nhãn hằng số theo quy tắc dominance. Dù vậy, guard có thể khiến nhãn hằng không được chọn trong một số trường hợp thực tế, như ví dụ ở phần trước.

## 7. Quan hệ giữa pattern dominance và `default`

`default` là nhánh dự phòng cho các giá trị không khớp với nhãn `case` trước đó. Nếu một unguarded pattern đứng trước là unconditional cho kiểu selector, nó đã bao phủ mọi giá trị không null của kiểu đó và có thể chi phối `default`.

Ví dụ:

```java
static void inspect(Object value) {
    switch (value) {
        case Object object -> System.out.println(object);
        default -> System.out.println("Other value"); // Dominated
    }
}
```

`Object object` bao phủ mọi đối tượng khác null có kiểu selector là `Object`, nên `default` không còn giá trị xử lý bổ sung. Lưu ý type pattern này không khớp `null`; nếu selector là null, switch vẫn ném `NullPointerException` khi không có nhãn xử lý null.

Một `default` đặt trước nhãn pattern hoặc `case null` cũng là lỗi biên dịch. Vì vậy, nếu dùng `default`, hãy đặt nó cuối switch. Java cho phép một số dạng `default` đứng trước các nhãn hằng số thuần túy vì lý do tương thích, nhưng không nên dựa vào cách sắp xếp đó trong mã mới.

Nếu muốn một nhãn xử lý cả null lẫn mọi giá trị khác, Java 21 hỗ trợ `case null, default`:

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Text: " + text;
        case null, default -> "Not a string or null";
    };
}
```

Nhãn kết hợp `case null, default` phải đứng cuối switch. Nó bị chi phối nếu trước đó đã có một unguarded pattern unconditional cho kiểu selector.

## 8. Phân biệt dominance với exhaustiveness

Hai khái niệm này liên quan nhưng giải quyết hai câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Hệ quả |
|---|---|---|
| Dominance | Nhãn hiện tại có bị nhãn trước bao phủ hoàn toàn không? | Nếu có, lỗi biên dịch |
| Exhaustiveness | Tập nhãn có bao phủ mọi trường hợp cần xử lý của selector không? | Nếu không exhaustive ở switch expression hoặc enhanced switch statement, lỗi biên dịch |

Một switch có thể có đầy đủ các nhánh nhưng vẫn lỗi vì một nhánh bị dominated. Ngược lại, các nhánh không chi phối nhau nhưng vẫn có thể chưa exhaustive.

Ví dụ với sealed hierarchy:

```java
sealed interface Shape permits Circle, Rectangle {
}

record Circle(double radius) implements Shape {
}

record Rectangle(double width, double height) implements Shape {
}

static double area(Shape shape) {
    return switch (shape) {
        case Circle circle -> Math.PI * circle.radius() * circle.radius();
        case Rectangle rectangle -> rectangle.width() * rectangle.height();
    };
}
```

Hai pattern xử lý hai kiểu con được phép nên switch expression exhaustive. Không cần `default`.

Nếu thêm `case Shape value` lên đầu, các nhánh `Circle` và `Rectangle` phía sau sẽ bị dominated, dù switch có vẻ đã bao phủ mọi trường hợp. Nếu chỉ viết `case Circle circle` mà bỏ `Rectangle`, switch không exhaustive. Như vậy, dominance kiểm tra thứ tự và phần giao nhau giữa các nhãn; exhaustiveness kiểm tra độ bao phủ của toàn bộ switch.

## 9. Các lỗi liên quan nhưng không phải dominance

Không phải mọi lỗi nhãn `case` đều là dominance:

- **Trùng hằng số:** cùng một giá trị constant xuất hiện nhiều lần trong một switch block là lỗi biên dịch.
- **Nhiều nhãn null:** một switch block không được có nhiều hơn một nhãn `null`.
- **Nhiều nhãn default:** một switch block không được có nhiều hơn một nhãn `default`.
- **Guard không hợp lệ:** guard phải có kiểu `boolean` hoặc `Boolean`; biến bên ngoài được dùng trong guard phải là `final` hoặc effectively final.
- **Guard constant false:** Java 21 không chấp nhận guard là constant expression có giá trị `false`.

Khi đọc thông báo lỗi, hãy xác định lỗi xuất phát từ quan hệ bao phủ giữa các pattern, từ nhãn bị trùng, hay từ điều kiện guard. Sửa đúng nguyên nhân sẽ tránh thay đổi thứ tự case một cách tùy tiện.

## 10. Quy trình rà soát một pattern switch

Khi thêm hoặc sửa nhánh `case`, có thể rà soát theo trình tự sau:

1. Xác định kiểu selector và các kiểu con có thể xuất hiện.
2. Liệt kê các nhánh hằng số cần ưu tiên xử lý riêng.
3. Đặt các type patterns cụ thể trước pattern tổng quát hơn.
4. Với record patterns, so sánh cả kiểu record và từng component pattern tương ứng, kể cả các thành phần lồng nhau.
5. Đặt guarded patterns trước unguarded pattern cùng cấu trúc; nhớ rằng guard không constant `true` không được compiler dùng để chứng minh dominance.
6. Kiểm tra `case null` nếu hợp đồng đầu vào cho phép null.
7. Xác nhận switch exhaustive; chỉ thêm `default` khi cần chính sách dự phòng hoặc khi tập kiểu mở không thể liệt kê đầy đủ.
8. Biên dịch lại sau khi thay đổi sealed hierarchy hoặc thêm biến thể mới để phát hiện nhánh thiếu hoặc bị chi phối.

## 11. Tổng kết

Pattern dominance là quy tắc kiểm tra tĩnh của Java: nếu một nhãn `case` phía trước đã bao phủ mọi giá trị mà nhãn sau có thể khớp, nhãn sau bị dominated và chương trình không biên dịch. Quy tắc áp dụng cho type patterns, record patterns, nhãn hằng số và `default` theo các điều kiện cụ thể của JLS.

Guard `when` thông thường không được dùng để chứng minh dominance vì điều kiện được đánh giá tại runtime; guard constant `true` được xem như unguarded. Khi viết switch, nên đặt trường hợp cụ thể trước trường hợp tổng quát, kiểm tra cấu trúc record pattern lồng nhau và phân biệt rõ dominance với exhaustiveness. Những nguyên tắc này giúp switch trong Java 21 rõ ràng, dễ bảo trì và được compiler kiểm tra chặt chẽ.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 21 — Switch Blocks, §14.11.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1) — quy tắc dominance của nhãn `case`, guard và `default`.
- [Java Language Specification, Java SE 21 — Properties of Patterns, §14.30.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3) — pattern applicability, unconditional patterns và quan hệ dominance giữa các pattern.
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch-expressions-and-statements.html) — giải thích thứ tự pattern labels và các ví dụ pattern label dominance.
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441) — pattern matching for switch được hoàn thiện trong Java 21.
- [JEP 440: Record Patterns](https://openjdk.org/jeps/440) — Record Patterns được hoàn thiện trong Java 21.
