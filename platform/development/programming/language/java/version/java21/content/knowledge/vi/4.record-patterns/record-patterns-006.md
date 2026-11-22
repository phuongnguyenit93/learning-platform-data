# Khai báo component pattern bằng kiểu tường minh hoặc `var`

## 1. Record pattern và component pattern

Trong Java 21, **record pattern** cho phép kiểm tra một giá trị có thuộc một record class hay không, đồng thời tách các component của record thành những pattern variable để sử dụng trực tiếp. Tính năng này đã trở thành tính năng chính thức trong Java 21 theo JEP 440; khi biên dịch mã Java 21, không cần bật preview feature.

Ví dụ, khai báo một record biểu diễn tọa độ:

```java
record Point(double x, double y) {}
```

Ta có thể kiểm tra và lấy hai component bằng record pattern:

```java
static void printPoint(Object value) {
    if (value instanceof Point(double x, double y)) {
        System.out.println("x = " + x + ", y = " + y);
    }
}
```

`Point(double x, double y)` là record pattern. Hai pattern nằm trong dấu ngoặc là **component pattern**. Java kiểm tra giá trị bên ngoài có phải `Point` hay không, sau đó lấy từng component thông qua accessor tương ứng và kiểm tra component theo pattern đã khai báo.

Component pattern có thể là:

- **Type pattern với kiểu tường minh**: ghi kiểu dữ liệu và tên biến, ví dụ `String name`, `double x`.
- **Type pattern dùng `var`**: chỉ ghi `var` và tên biến, ví dụ `var name`, để compiler suy luận kiểu từ component tương ứng.
- **Record pattern lồng nhau**: dùng một record pattern làm component pattern để tiếp tục tách một record con.

Danh sách component pattern phải có đúng số lượng và đúng thứ tự như các record component trong khai báo record. Mỗi component được xử lý theo vị trí tương ứng.

## 2. Khai báo component pattern bằng kiểu tường minh

Với kiểu tường minh, ta ghi kiểu của biến ngay trong component pattern. Kiểu này có thể là kiểu nguyên thủy hoặc kiểu tham chiếu, miễn là pattern phù hợp với kiểu component tương ứng.

```java
record Point(double x, double y) {}
record Person(String name, int age) {}

static void printDetails(Object value) {
    if (value instanceof Point(double x, double y)) {
        // x và y có kiểu double
        System.out.println(Math.hypot(x, y));
    }

    if (value instanceof Person(String name, int age)) {
        // name có kiểu String, age có kiểu int
        System.out.println(name + " - " + age);
    }
}
```

Ở đây, `double x`, `double y`, `String name` và `int age` đều là khai báo pattern variable trong vị trí component. Java 21 cho phép type pattern với kiểu nguyên thủy trong component pattern khi kiểu đó khớp với kiểu component, ví dụ `double` với component `double`. Quy tắc này thuộc ngữ cảnh record pattern; không nên suy ra rằng có thể dùng `value instanceof int number` như một type pattern độc lập.

Kiểu tường minh đặc biệt hữu ích khi component được khai báo bằng một kiểu tổng quát hơn nhưng chương trình chỉ muốn xử lý một kiểu con cụ thể:

```java
record Message(Object payload, String source) {}

static void handle(Object value) {
    if (value instanceof Message(String text, String source)) {
        // Chỉ vào nhánh này khi payload là String.
        System.out.println(source + ": " + text.toUpperCase());
    }
}
```

Component `payload` được khai báo là `Object`, nhưng pattern `String text` yêu cầu giá trị thực tế có thể được ép kiểu sang `String`. Nếu `payload` là một `Integer` hoặc một kiểu không tương thích, toàn bộ record pattern không khớp và thân `if` không chạy.

Kiểu tường minh giúp thể hiện rõ ý định và thu hẹp kiểu của biến ngay tại nơi sử dụng. Khi cần kiểm tra kiểu con, đây thường là lựa chọn dễ đọc hơn việc nhận một biến `Object` rồi ép kiểu thủ công.

## 3. Khai báo component pattern bằng `var`

Nếu kiểu của component đã rõ từ khai báo record hoặc từ kiểu tham số hóa của record pattern, có thể dùng `var` để compiler tự suy luận kiểu pattern variable.

```java
record Point(double x, double y) {}

static void printPoint(Object value) {
    if (value instanceof Point(var x, var y)) {
        // Compiler suy luận x và y đều có kiểu double.
        System.out.println(Math.hypot(x, y));
    }
}
```

`Point(var x, var y)` có cùng mục đích tách dữ liệu như `Point(double x, double y)`. Khác biệt là kiểu của biến được suy luận từ kiểu component thay vì được lặp lại trong mã nguồn.

Với record có component kiểu tham chiếu, `var` cũng lấy kiểu khai báo của component:

```java
record Person(String name, int age) {}

static void printPerson(Object value) {
    if (value instanceof Person(var name, var age)) {
        // name có kiểu String; age có kiểu int.
        System.out.println(name + " - " + age);
    }
}
```

Kiểu được suy luận từ kiểu component sau khi áp dụng kiểu của record pattern. `var` không đợi đến runtime để suy ra kiểu cụ thể của object đang chứa. Ví dụ, nếu component khai báo là `Object`, biến được khai báo bằng `var` vẫn có kiểu tĩnh `Object`, kể cả khi object thực tế là một `String`.

Trong Java 21, `var` ở đây được dùng trực tiếp trong danh sách component của record pattern. Nó không phải cách viết type pattern độc lập như `value instanceof var result`.

## 4. So sánh kiểu tường minh và `var`

| Tiêu chí | Kiểu tường minh | `var` |
|---|---|---|
| Cách viết | `String text`, `double x` | `var text`, `var x` |
| Nguồn xác định kiểu | Kiểu ghi trực tiếp trong pattern | Kiểu component tương ứng sau khi suy luận kiểu record pattern |
| Thu hẹp kiểu component tổng quát | Có thể, ví dụ `String` từ component `Object` | Không; giữ kiểu được suy luận từ component |
| Mức độ thể hiện kiểu trong mã nguồn | Rõ ràng ngay tại vị trí khai báo | Gọn hơn khi kiểu đã hiển nhiên từ record |
| Tình huống phù hợp | Cần kiểm tra kiểu con hoặc muốn nhấn mạnh kiểu sử dụng | Component có kiểu đã rõ, nhất là record có nhiều component |

Chọn `var` để giảm lặp lại khi kiểu component đã đủ rõ. Chọn kiểu tường minh khi cần kiểm tra một kiểu con, khi muốn người đọc nhận ra kiểu đích ngay tại chỗ, hoặc khi kiểu component là `Object`/interface nhưng logic chỉ chấp nhận một kiểu cụ thể.

Không nên dùng `var` với suy nghĩ rằng nó tự động biến một component `Object` thành kiểu runtime thực tế. Nếu cần một `String` từ component `Object`, hãy dùng `String text` để pattern thực hiện kiểm tra kiểu.

## 5. Khác biệt khi component có thể là `null`

Đây là một quy tắc quan trọng khi chọn kiểu pattern. Cần phân biệt giá trị của record bên ngoài với giá trị của từng component:

- **Record bên ngoài bằng `null`**: không khớp với bất kỳ record pattern nào.
- **Component có kiểu tham chiếu**: một type pattern trực tiếp trong danh sách component có thể khớp `null` nếu pattern đó là *unconditional* đối với kiểu component.
- **Pattern kiểu con**: nếu kiểu pattern hẹp hơn kiểu component và không unconditional, `null` không khớp pattern đó.

Ví dụ:

```java
record Person(String name, Object note) {}

static void inspect(Object value) {
    if (value instanceof Person(String name, var note)) {
        // String name là pattern unconditional cho component String.
        // var note có kiểu Object.
        System.out.println(name);
        System.out.println(note);
    }

    if (value instanceof Person(String name, String note)) {
        // Component note có kiểu Object.
        // Pattern String note chỉ khớp khi note là String khác null.
        System.out.println(name + ": " + note);
    }
}
```

Trong pattern đầu tiên, `String name` là unconditional đối với component khai báo `String`, nên pattern variable `name` có thể được khởi tạo bằng `null`. `var note` được suy luận thành `Object`, cũng có thể nhận `null`.

Trong pattern thứ hai, component `note` được khai báo là `Object`, còn pattern yêu cầu `String`. Đây là kiểm tra kiểu có điều kiện: `null` không khớp `String note`, và một giá trị không phải `String` cũng không khớp. Do đó, toàn bộ record pattern thất bại nếu `note` là `null` hoặc không phải `String`.

Quy tắc này được đặc tả tại JLS 21, mục 14.30.1 đến 14.30.3. Khi thiết kế dữ liệu, hãy xác định rõ component nào cho phép `null` và chọn pattern phù hợp; đừng giả định mọi type pattern trong component đều xử lý `null` giống nhau.

## 6. Suy luận kiểu với generic record

Với generic record, kiểu component có thể phụ thuộc vào type argument của record. Java 21 có thể suy luận type argument của record pattern và kiểu biến được khai báo bằng `var`.

```java
record Box<T>(T value) {}

static void printBox(Box<String> box) {
    if (box instanceof Box<String>(String text)) {
        System.out.println(text.toUpperCase());
    }

    if (box instanceof Box(var text)) {
        // Compiler suy luận pattern thành Box<String>(String text).
        System.out.println(text.toUpperCase());
    }
}
```

Trong ví dụ thứ hai, kiểu `Box<String>` của biểu thức `box` cung cấp thông tin để compiler suy luận type argument `String`. Vì vậy, `text` có kiểu tĩnh `String`, không phải `Object`.

Kiểm tra generic vẫn phải an toàn. Java không cho phép dùng một record pattern tham số hóa nếu việc kiểm tra đòi hỏi unchecked conversion. Chẳng hạn, từ một biến raw `Box`, không thể tùy tiện khẳng định giá trị đó là `Box<String>` bằng record pattern `Box<String>(var text)`. Hãy giữ kiểu generic chính xác ở API và biến trung gian để compiler có đủ thông tin kiểm tra.

## 7. Kết hợp component pattern lồng nhau

Khi một record chứa record khác, có thể đặt record pattern trực tiếp ở component tương ứng. Cách này giúp truy cập dữ liệu nhiều tầng mà không cần gọi chuỗi accessor thủ công.

```java
record Point(double x, double y) {}
record Address(String city, String postalCode) {}
record Customer(String name, Address address, Point location) {}

static void printCustomerLocation(Object value) {
    if (value instanceof Customer(
            String name,
            Address(var city, String postalCode),
            Point(var x, var y))) {
        System.out.println(name + " lives in " + city);
        System.out.println("Postal code: " + postalCode);
        System.out.println("Location: " + x + ", " + y);
    }
}
```

Pattern trên kiểm tra `Customer`, sau đó lần lượt kiểm tra component `name`, record `Address` và record `Point`. Các biến `city`, `postalCode`, `x` và `y` chỉ được khởi tạo khi tất cả component pattern đều khớp.

Nếu `address` hoặc `location` bằng `null`, record pattern lồng nhau tương ứng không khớp và toàn bộ pattern bên ngoài thất bại. Nếu `city` là `null`, `var city` có thể nhận `null`; còn `String postalCode` là unconditional đối với component `String`, nên cũng có thể nhận `null`. Nếu nghiệp vụ yêu cầu các giá trị này bắt buộc khác `null`, cần validation ở nơi tạo record hoặc thêm điều kiện kiểm tra rõ ràng.

## 8. Dùng record pattern trong `instanceof` và `switch`

Record pattern có thể được sử dụng trong biểu thức `instanceof`, `switch` statement và `switch` expression. Pattern variable chỉ có thể được sử dụng trong phạm vi mà compiler xác định pattern đã khớp.

Với `instanceof`, có thể kết hợp pattern với điều kiện bằng `&&`:

```java
record Point(double x, double y) {}

static boolean isInFirstQuadrant(Object value) {
    return value instanceof Point(var x, var y)
            && x > 0
            && y > 0;
}
```

`x` và `y` chỉ được sử dụng ở vế phải của `&&` sau khi record pattern khớp. Nếu pattern không khớp, các điều kiện phía sau không được đánh giá.

Trong `switch`, mỗi nhánh có thể khai báo component pattern riêng:

```java
record Point(double x, double y) {}

static String describe(Object value) {
    return switch (value) {
        case Point(double x, double y) ->
                "Point(" + x + ", " + y + ")";
        case null -> "No value";
        default -> "Not a point";
    };
}
```

Record pattern không khớp selector `null`. Nếu `switch` cần xử lý `null`, hãy khai báo `case null` riêng. `default` không tự động thay thế nhánh `case null`.

## 9. Cơ chế khớp pattern và các giới hạn cần nhớ

Khi runtime kiểm tra một record pattern, Java thực hiện các bước chính:

1. Giá trị bên ngoài phải khác `null` và có thể được ép kiểu an toàn sang record type trong pattern.
2. Java gọi accessor tương ứng của từng record component để lấy giá trị.
3. Mỗi giá trị component được kiểm tra với component pattern cùng vị trí.
4. Chỉ khi tất cả component pattern khớp, các pattern variable trong danh sách mới được khởi tạo và sử dụng.

Việc tách component dựa trên accessor method. Nếu accessor hoàn tất bất thường do ném exception, quá trình pattern matching kết thúc bằng `MatchException`, với nguyên nhân được giữ trong cause. Vì vậy, accessor của record nên tuân thủ hợp đồng component và tránh side effect khó dự đoán.

Một số giới hạn thực tế:

- Số lượng component pattern phải bằng số record component; không thể tự ý bỏ qua vị trí giữa danh sách.
- Không khai báo trùng tên pattern variable trong cùng một record pattern.
- `var` trong pattern chỉ dùng trực tiếp tại vị trí component của record pattern.
- Với generic record, type argument phải được suy luận hoặc kiểm tra mà không cần unchecked conversion.
- Record pattern bên ngoài và record pattern lồng nhau đều không khớp giá trị `null` của chính record tương ứng.

## 10. Chọn cách khai báo phù hợp

Hãy ưu tiên kiểu tường minh khi cần kiểm tra component có kiểu tổng quát, ví dụ `Object`, có thực sự chứa một kiểu con cụ thể hay không. Cách này vừa thực hiện kiểm tra kiểu vừa cung cấp biến có kiểu đích để sử dụng an toàn.

Hãy ưu tiên `var` khi kiểu component đã được định nghĩa rõ trong record hoặc được suy luận từ generic type argument. Cách viết này giảm lặp lại kiểu và giúp pattern tập trung vào cấu trúc dữ liệu.

Với record lồng nhau, có thể kết hợp cả hai: dùng record pattern để đi sâu vào cấu trúc, dùng kiểu tường minh ở nơi cần thu hẹp kiểu, và dùng `var` ở nơi kiểu component đã rõ. Dù chọn cách nào, hãy xác định chính sách `null` và generic trước khi dựa vào kết quả pattern.

## 11. Tài liệu tham khảo chính thức

- [Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): cú pháp, `var`, generic record và record pattern lồng nhau.
- [Java Language Specification, Java SE 21 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): quy tắc component pattern, suy luận kiểu, null matching và quá trình pattern matching.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): thiết kế và trạng thái chính thức của record patterns trong Java 21.

Khi đọc ví dụ record pattern, hãy luôn xác định kiểu khai báo của từng component, kiểu pattern variable sau suy luận và điều kiện để component khớp. Ba yếu tố này giúp chọn đúng giữa kiểu tường minh và `var`, đồng thời tránh lỗi khi dữ liệu có thể chứa `null` hoặc generic type.
