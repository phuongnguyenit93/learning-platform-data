# Selector là reference type và các giới hạn kiểu trong Java 21

Java 21 cho phép `switch` nhận selector thuộc bất kỳ kiểu tham chiếu nào, chẳng hạn `Object`, một interface, class, record, enum, array hoặc kiểu generic. Nhờ đó, một `switch` có thể phân nhánh theo kiểu thực tế của đối tượng bằng pattern như `case String s` hoặc `case int[] values`.

Khả năng này không có nghĩa mọi pattern đều hợp lệ với mọi selector. Compiler xét **kiểu tĩnh của biểu thức selector** để xác định pattern có thể khớp hay không. Các pattern không tương thích, các nhánh bị nhánh trước bao phủ, hoặc switch không đầy đủ đều có thể gây lỗi ngay khi biên dịch.

Các ví dụ trong bài dùng cú pháp Pattern Matching for `switch` đã trở thành tính năng chính thức trong Java 21, không cần bật preview feature.

## 1. Những kiểu nào có thể làm selector?

Theo Java Language Specification 21, kiểu của biểu thức selector trong `switch` có thể là `char`, `byte`, `short`, `int` hoặc một kiểu tham chiếu. Bài này tập trung vào nhóm kiểu tham chiếu.

Một số kiểu tham chiếu thường gặp:

| Kiểu selector | Ví dụ pattern có thể xét |
|---|---|
| `Object` | `String`, `Integer`, `Point`, `int[]` |
| Interface như `CharSequence` | `String`, `StringBuilder` |
| Class như `Number` | `Integer`, `Double` |
| Record | Chính record đó hoặc pattern phân rã record |
| Enum | Enum type pattern hoặc các enum constant phù hợp |
| Array | `String[]`, `int[]`, `Object[]` nếu tương thích |
| Generic type như `List<String>` | Các kiểu con tương thích như `ArrayList<String>` |

Ví dụ, selector có kiểu tĩnh `Object` có thể được phân nhánh theo class, record, enum hoặc array:

```java
record Point(int x, int y) {}

enum Color {
    RED, GREEN, BLUE
}

static String describe(Object value) {
    return switch (value) {
        case null -> "Giá trị null";
        case String text -> "Chuỗi: " + text;
        case Color color -> "Màu: " + color;
        case Point point -> "Điểm: " + point.x() + ", " + point.y();
        case int[] numbers -> "Mảng int có " + numbers.length + " phần tử";
        default -> "Kiểu khác";
    };
}
```

`Object` là kiểu tham chiếu rộng nên các pattern trên đều có thể được kiểm tra. Khi chạy, chỉ nhánh phù hợp với giá trị thực tế mới được chọn.

Java 21 chưa hỗ trợ `long`, `float`, `double` hoặc `boolean` làm kiểu selector nguyên thủy của `switch`, và cũng chưa có primitive type pattern ở cấp cao nhất như `case int n`. Nếu dữ liệu mang các giá trị đó nhưng được lưu trong wrapper như `Long`, `Float`, `Double` hoặc `Boolean`, wrapper là kiểu tham chiếu nên có thể dùng type pattern tương ứng. Các pattern nguyên thủy trong component list của record là một ngữ cảnh khác; chúng không biến primitive thành kiểu selector mới.

## 2. Kiểu tĩnh của selector quyết định pattern có hợp lệ

Compiler không đợi đến runtime để thử mọi kiểu có thể tưởng tượng. Nó dùng kiểu tĩnh của selector để kiểm tra liệu kiểu pattern có thể giao nhau với kiểu selector hay không.

Ví dụ, `CharSequence` có thể tham chiếu đến `String` hoặc `StringBuilder`, vì cả hai đều triển khai interface này:

```java
static String describeText(CharSequence value) {
    return switch (value) {
        case String text -> "String: " + text;
        case StringBuilder builder -> "StringBuilder: " + builder;
        default -> "Một CharSequence khác";
    };
}
```

Nhưng `Integer` là class `final` và không triển khai `CharSequence`. Không có đối tượng nào vừa là `Integer` vừa là `CharSequence`, nên pattern sau không tương thích với selector:

```java
static String invalid(CharSequence value) {
    return switch (value) {
        case Integer number -> "Số: " + number; // Lỗi biên dịch
        default -> "Khác";
    };
}
```

Một type pattern khai báo biến kiểu tham chiếu `U` được xem là applicable tại kiểu selector `T` khi `T` *checked cast convertible* sang `U` theo JLS. Quan hệ này cho phép cả trường hợp `T` đã là subtype của `U` lẫn trường hợp có thể thu hẹp kiểu bằng một phép kiểm tra runtime an toàn. Nó loại trừ những cặp kiểu chắc chắn không thể giao nhau và những phép chuyển đổi cần unchecked cast, nên pattern không tương thích bị từ chối ngay lúc biên dịch.

Nhãn constant có quy tắc tương thích riêng. Constant expression như `case "ready"` chỉ dùng được với selector thuộc nhóm kiểu mà switch hỗ trợ constant expression, trong đó có `String` và các kiểu số nguyên được hỗ trợ. Vì vậy, nếu selector có kiểu tĩnh `Object`, hãy dùng type pattern kết hợp guard thay vì viết `case "ready"`:

```java
static String state(Object value) {
    return switch (value) {
        case String text when text.equals("ready") -> "Sẵn sàng";
        case String text -> "Chuỗi khác";
        default -> "Kiểu khác";
    };
}
```

Điều này cũng giải thích vì sao selector interface có thể được kiểm tra với nhiều class khác nhau: một class không `final` có thể có subclass triển khai interface đó. Ngược lại, class `final` không triển khai interface sẽ không thể bất ngờ trở thành một instance của interface ấy.

### Dùng kiểu rộng khi cần phân nhánh nhiều loại

Nếu một phương thức thực sự nhận nhiều loại đối tượng không liên quan, khai báo tham số bằng `Object` có thể phù hợp:

```java
static String category(Object value) {
    return switch (value) {
        case String text -> "text";
        case Integer number -> "integer";
        case Point point -> "point";
        default -> "other";
    };
}
```

Nếu tham số đã có kiểu hẹp như `CharSequence`, chỉ liệt kê những kiểu có thể là `CharSequence`. Không nên thêm một pattern bất khả thi chỉ vì kiểu runtime của một biến khác trong chương trình có thể là kiểu đó.

## 3. Giới hạn của generic type pattern

Type pattern với kiểu generic cũng phải đáp ứng quy tắc checked cast. Java dùng type erasure nên runtime không lưu đầy đủ mọi type argument. Vì thế, compiler không cho phép một pattern đòi hỏi unchecked conversion mà JVM không thể kiểm chứng an toàn.

Với selector có kiểu tĩnh `Object`, có thể kiểm tra một `List` bằng wildcard:

```java
import java.util.List;

static String inspectList(Object value) {
    return switch (value) {
        case List<?> items -> "List có " + items.size() + " phần tử";
        default -> "Không phải List";
    };
}
```

`List<?>` chấp nhận mọi kiểu phần tử. Ngược lại, pattern `List<String>` không hợp lệ khi selector là `Object`, vì compiler không thể xác minh rằng một object bất kỳ là `List<String>` mà không dựa vào unchecked conversion:

```java
static String invalidListPattern(Object value) {
    return switch (value) {
        case List<String> items -> "List<String>"; // Lỗi biên dịch
        default -> "Khác";
    };
}
```

Không nên ghi nhớ một quy tắc quá rộng rằng mọi parameterized type đều bị cấm. Một pattern generic vẫn có thể hợp lệ nếu kiểu selector cho phép một checked cast. Chẳng hạn, khi selector đã có kiểu `List<String>`, kiểm tra xem đối tượng có phải `ArrayList<String>` hay không là hợp lệ:

```java
import java.util.ArrayList;
import java.util.List;

static String inspectStrings(List<String> values) {
    return switch (values) {
        case ArrayList<String> arrayList -> "ArrayList, size=" + arrayList.size();
        default -> "Một kiểu List<String> khác";
    };
}
```

Trong trường hợp này, compiler biết type argument của selector là `String` và có thể kiểm tra an toàn phép thu hẹp sang `ArrayList<String>`. Nếu thay pattern thành `ArrayList<Integer>`, compiler sẽ báo lỗi vì `List<String>` và `ArrayList<Integer>` có các type argument không tương thích.

| Selector | Pattern | Kết quả |
|---|---|---|
| `Object` | `List<?>` | Hợp lệ; wildcard cho phép kiểm tra an toàn. |
| `Object` | `List<String>` | Không hợp lệ; cần unchecked conversion. |
| `List<String>` | `ArrayList<String>` | Hợp lệ; có thể checked-cast. |
| `List<String>` | `ArrayList<Integer>` | Không hợp lệ; type argument không tương thích. |

Khi selector là kiểu generic, hãy giữ type argument phù hợp với dữ liệu đã biết và dùng wildcard khi chỉ cần kiểm tra loại container mà không cần khẳng định kiểu phần tử.

## 4. Pattern top-level phải khai báo kiểu tham chiếu

Trong Java 21, pattern ở cấp cao nhất của một `case` phải khai báo một biến có kiểu tham chiếu tường minh. Vì vậy, cách viết `case String text` là hợp lệ, còn `case var value` không phải cú pháp hợp lệ cho top-level type pattern.

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> text;
        case Object object -> object.toString();
    };
}
```

Ở đây `case Object object` là pattern rộng cho selector `Object`: nó khớp mọi giá trị khác null thuộc kiểu selector. Nếu muốn xử lý null, vẫn cần thêm `case null`; type pattern top-level không tự bắt null.

`var` vẫn hữu ích trong component list của record pattern, nơi kiểu của component được suy ra từ khai báo record:

```java
record Person(String name, int age) {}

static String describePerson(Object value) {
    return switch (value) {
        case Person(var name, var age) -> name + ", " + age;
        default -> "Không phải Person";
    };
}
```

Đây là `var` nằm bên trong record pattern, không phải pattern top-level. Record pattern ở cấp cao nhất vẫn có kiểu record tường minh là `Person`.

## 5. Null là trường hợp riêng của reference selector

Một selector kiểu tham chiếu có thể nhận `null`. Tuy nhiên, `case null` là nhãn riêng; `case String s`, `case Object o` và `default` không thay thế nhãn này.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case String text -> "Chuỗi: " + text;
        default -> "Giá trị khác";
    };
}
```

Nếu selector là `null` mà switch không có nhãn `case null`, Java ném `NullPointerException` trước khi chọn nhánh, kể cả khi switch có `default` hoặc một pattern rộng như `case Object o`. Có thể gộp hai trường hợp null và các giá trị còn lại bằng `case null, default -> ...`; nhãn kết hợp này phải đặt cuối switch block.

`case null` chỉ dùng được khi selector có kiểu tham chiếu. Nó không phải pattern để đặt vào component list của record. Với component có thể null, hãy bắt component bằng `var` hoặc một type pattern unconditional phù hợp rồi kiểm tra giá trị trong guard hay phần thân.

## 6. Thứ tự pattern và lỗi dominance

Một giá trị có thể khớp nhiều pattern. Java xét các nhãn theo thứ tự từ trên xuống, nhưng compiler sẽ báo lỗi nếu một nhãn không thể được chọn vì một nhãn không guard ở trước đã bao phủ toàn bộ giá trị mà nó có thể khớp. Quy tắc này gọi là *pattern label dominance*.

Với selector `Object`, có thể đặt pattern hẹp trước, pattern rộng sau:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String";
        case CharSequence chars -> "CharSequence khác String";
        case Object object -> "Một object khác";
    };
}
```

Nếu đảo hai nhãn `CharSequence` và `String`, compiler báo lỗi vì mọi `String` đều là `CharSequence`; nhánh `CharSequence` đứng trước đã bao phủ toàn bộ giá trị của nhánh `String`:

```java
static String invalidOrder(Object value) {
    return switch (value) {
        case CharSequence chars -> "Chuỗi ký tự";
        case String text -> "String"; // Lỗi: bị pattern phía trên dominate
        default -> "Khác";
    };
}
```

Pattern `Object object` trên selector `Object` là pattern rộng không guard và đóng vai trò như nhánh mặc định cho các giá trị khác null. Không đặt thêm pattern hoặc `default` phía sau nó. Nếu cần xử lý null riêng, đặt `case null` trước pattern rộng.

Guard `when` cho phép chia nhỏ một kiểu thành nhiều trường hợp. Guard không hằng đúng không được xem là bao phủ toàn bộ kiểu, vì vậy có thể đặt một nhánh có guard trước nhánh cùng pattern không guard:

```java
static String describeText(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "Chuỗi rỗng hoặc chỉ có khoảng trắng";
        case String text -> "Chuỗi: " + text;
        default -> "Không phải chuỗi";
    };
}
```

Ngược lại, pattern không guard đứng trước sẽ dominate pattern cùng kiểu có guard. Vì thế, luôn đặt nhánh cụ thể trước nhánh tổng quát. Nếu một guard là constant expression có giá trị `true`, compiler xem nhãn đó như unguarded khi xét dominance.

## 7. Switch phải bao phủ các giá trị hợp lệ

`switch` expression luôn phải exhaustive. `switch` statement cũng phải exhaustive nếu là enhanced switch: ví dụ switch có pattern label, có `case null`, hoặc selector thuộc kiểu ngoài nhóm switch truyền thống (`char`, `byte`, `short`, `int`, wrapper tương ứng, `String` và enum). Với selector `Object`, chỉ liệt kê một vài kiểu không thể bao phủ mọi object:

```java
static int length(Object value) {
    return switch (value) { // Lỗi: chưa exhaustive
        case String text -> text.length();
        case Integer number -> number;
    };
}
```

Thêm `default` để xử lý các kiểu còn lại:

```java
static int length(Object value) {
    return switch (value) {
        case null -> 0;
        case String text -> text.length();
        case Integer number -> number;
        default -> -1;
    };
}
```

Với sealed class hoặc sealed interface, compiler có thể xác định các kiểu con được phép và chấp nhận switch không cần `default` khi tất cả nhánh đã được bao phủ:

```java
sealed interface Command permits Start, Stop {}

record Start(String id) implements Command {}
record Stop(String id) implements Command {}

static String handle(Command command) {
    return switch (command) {
        case null -> "Không có command";
        case Start start -> "Start " + start.id();
        case Stop stop -> "Stop " + stop.id();
    };
}
```

Compiler xác định `Start` và `Stop` là toàn bộ các kiểu con được phép của `Command`, nên hai pattern đã bao phủ miền kiểu. Nhãn `case null` xử lý thêm trường hợp selector null. Nếu bỏ nhãn này, switch vẫn có thể exhaustive theo miền kiểu nhưng sẽ ném `NullPointerException` khi selector là null.

Lưu ý rằng exhaustive ở compile time không bảo đảm một hierarchy đã thay đổi binary vẫn khớp với những nhánh đã biên dịch. Nếu sealed hierarchy thay đổi và có giá trị runtime không còn nhánh tương ứng, một switch được xem là exhaustive khi biên dịch có thể ném `MatchException`; hãy biên dịch lại module phụ thuộc khi cập nhật hierarchy.

## 8. Checklist kiểm tra selector và pattern

- [ ] Đã xác định kiểu tĩnh của biểu thức selector, không chỉ nhìn kiểu runtime dự kiến.
- [ ] Selector thuộc kiểu Java 21 cho phép: `char`, `byte`, `short`, `int` hoặc reference type.
- [ ] Mỗi type pattern có kiểu tham chiếu và có thể checked-cast từ kiểu selector.
- [ ] Record pattern tương thích với selector và từng component pattern tương thích với kiểu component tương ứng.
- [ ] Với generic type, pattern không đòi hỏi unchecked conversion; dùng wildcard khi chỉ cần kiểm tra loại container.
- [ ] Không dùng `var` làm top-level type pattern trong Java 21.
- [ ] Đã xử lý `null` bằng `case null` nếu selector có thể null và nghiệp vụ cần nhánh riêng.
- [ ] Pattern hẹp đứng trước pattern rộng; không có nhánh bị dominate.
- [ ] Switch expression và enhanced switch statement đã exhaustive.
- [ ] Nếu switch dựa trên sealed hierarchy, đã xem xét việc biên dịch lại khi hierarchy thay đổi.

## Tài liệu tham khảo

- [Pattern Matching for switch Expressions and Statements — Java SE 21](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): kiểu selector, type pattern, guard `when`, dominance, type coverage và `case null`.
- [Java Language Specification, Java SE 21 — §14.11 Switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): kiểu selector hợp lệ, tính tương thích của switch block, dominance và exhaustive switch.
- [Java Language Specification, Java SE 21 — §14.30.1–§14.30.3 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): loại pattern, điều kiện applicable tại kiểu selector và quy tắc dominance.
- [Java Language Specification, Java SE 21 — §5.5 Casting Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.5): checked và unchecked narrowing reference conversions dùng để xác định khả năng tương thích kiểu.
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441): mục tiêu và các quy tắc thiết kế của tính năng đã được hoàn thiện trong Java 21.
