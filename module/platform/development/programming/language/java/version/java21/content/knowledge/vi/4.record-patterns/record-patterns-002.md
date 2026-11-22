# Kiểm tra kiểu và tách các component trong một lần matching

Record pattern (mẫu record) cho phép kiểm tra một giá trị có thuộc một kiểu record hay không, đồng thời lấy các component của record thành biến để sử dụng ngay. Thay vì kiểm tra kiểu, ép kiểu rồi gọi từng accessor, ta mô tả cấu trúc cần khớp ngay trong một pattern.

Trong Java 21, Record Patterns là tính năng chính thức theo JEP 440. Có thể sử dụng trong biểu thức `instanceof` và kết hợp với pattern matching cho `switch` mà không cần bật preview feature. Bài học này tập trung vào cú pháp Java 21 đã được chuẩn hóa.

## Từ kiểm tra kiểu đến tách component

Giả sử có record biểu diễn tọa độ:

```java
record Point(int x, int y) { }
```

Nếu chỉ cần kiểm tra kiểu và giữ toàn bộ đối tượng, type pattern là đủ:

```java
static void describe(Object value) {
    if (value instanceof Point point) {
        System.out.println(point.x() + ", " + point.y());
    }
}
```

Nếu cần cả hai component, record pattern thực hiện kiểm tra kiểu và tách component trong cùng một biểu thức:

```java
static void describe(Object value) {
    if (value instanceof Point(int x, int y)) {
        System.out.println("x = " + x + ", y = " + y);
    }
}
```

Với `Point(int x, int y)`, Java thực hiện các bước sau:

1. Kiểm tra `value` có phải là một đối tượng `Point` hay không.
2. Gọi accessor tương ứng với component thứ nhất và khớp kết quả với pattern `int x`.
3. Gọi accessor của component thứ hai và khớp kết quả với pattern `int y`.
4. Chỉ khi toàn bộ pattern khớp, các biến `x` và `y` mới được khởi tạo và có thể sử dụng trong nhánh `if`.

Danh sách component phải theo đúng thứ tự khai báo trong record. Với `record Point(int x, int y)`, `Point(int x, int y)` là đúng thứ tự; record pattern không chọn component theo tên và không cho phép đảo vị trí hai component.

| Cách viết | Kết quả |
|---|---|
| `value instanceof Point p` | Kiểm tra kiểu và giữ đối tượng trong biến `p` |
| `value instanceof Point(int x, int y)` | Kiểm tra kiểu, gọi accessor và lấy hai component vào `x`, `y` |
| `value instanceof Point(var x, var y)` | Tương tự, nhưng để compiler suy luận kiểu của từng biến |

Record pattern chỉ áp dụng cho record class. Với một class thông thường không khai báo dưới dạng record, không thể dùng cú pháp `SomeClass(...)` để tách các field hoặc thuộc tính của nó.

## Kiểu component và `var`

Kiểu trong từng vị trí pattern phải tương thích với kiểu component tương ứng. Có thể ghi kiểu tường minh để thể hiện rõ dữ liệu:

```java
record Employee(String name, int level, boolean active) { }

static void printEmployee(Object value) {
    if (value instanceof Employee(String name, int level, boolean active)) {
        System.out.println(name + " - level " + level);
        System.out.println("Active: " + active);
    }
}
```

Hoặc dùng `var` để compiler suy luận kiểu từ khai báo record:

```java
static void printEmployee(Object value) {
    if (value instanceof Employee(var name, var level, var active)) {
        // name có kiểu String, level có kiểu int, active có kiểu boolean
        System.out.println(name + " - level " + level);
    }
}
```

`var` trong component pattern không làm mất thông tin kiểu. Nó lấy kiểu component đã khai báo trong record, vì vậy compiler vẫn kiểm tra kiểu khi sử dụng biến.

Record pattern cần có một pattern cho mỗi component theo đúng thứ tự. Nếu không cần dùng giá trị của một component, có thể đặt tên biến như `var ignored` rồi không sử dụng biến đó. Cú pháp này vẫn thực hiện việc lấy và khớp component; Java 21 không có wildcard `_` ổn định để bỏ qua component trong record pattern.

## Tách dữ liệu từ record lồng nhau

Một component của record có thể là một record khác. Ta có thể đặt record pattern bên trong record pattern để đi sâu vào cấu trúc dữ liệu mà không cần viết nhiều lần kiểm tra kiểu và gọi accessor.

```java
record Address(String city, String district) { }
record Customer(String name, Address address) { }

static void printCustomer(Object value) {
    if (value instanceof Customer(
            String name,
            Address(var city, var district))) {
        System.out.println("Customer: " + name);
        System.out.println("Address: " + district + ", " + city);
    }
}
```

Pattern `Customer(...)` kiểm tra đối tượng ngoài. Component `address` tiếp tục được kiểm tra và tách bằng `Address(...)`. Nếu tất cả các cấp đều khớp, các biến `name`, `city` và `district` được sử dụng trực tiếp trong nhánh `if`.

Có thể kết hợp record pattern với type pattern ở từng cấp. Ví dụ, record `SearchResult` có component `Object value`; chỉ xử lý khi component đó là `Customer`:

```java
record SearchResult(String source, Object value) { }

static void inspect(Object input) {
    if (input instanceof SearchResult(
            var source,
            Customer(String name, var address))) {
        System.out.println("Source: " + source);
        System.out.println("Customer: " + name);
        System.out.println("Address value: " + address);
    }
}
```

Ở ví dụ này, pattern `Customer(...)` vừa kiểm tra component `value` có phải `Customer` hay không, vừa tách tiếp các component của `Customer`.

## Record pattern với record generic

Record pattern hỗ trợ record có tham số kiểu. Có thể ghi rõ kiểu tham số hoặc để compiler suy luận từ kiểu tĩnh của biểu thức được kiểm tra.

```java
record Box<T>(T value) { }

static void printTextBox(Box<String> box) {
    if (box instanceof Box<String>(String text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Vì `box` có kiểu `Box<String>`, compiler cũng có thể suy luận tham số kiểu và kiểu component:

```java
static void printTextBox(Box<String> box) {
    if (box instanceof Box(var text)) {
        // text được suy luận là String
        System.out.println(text.toUpperCase());
    }
}
```

Việc suy luận kiểu cũng áp dụng cho record pattern lồng nhau. Tuy nhiên, pattern vẫn phải thỏa quy tắc tương thích kiểu của Java. Không thể dùng một kiểu tham số cụ thể nếu việc kiểm tra đòi hỏi unchecked conversion. Chẳng hạn, từ một biến raw type `Box`, không thể an toàn khẳng định component của nó là `String` chỉ bằng cách viết `Box<String>(String text)`.

## Dùng record pattern trong `switch`

Java 21 hoàn thiện pattern matching cho `switch` theo JEP 441. Nhờ đó, mỗi nhánh có thể kiểm tra một kiểu record và tách component tương ứng.

```java
record Point(int x, int y) { }

static String classify(Object value) {
    return switch (value) {
        case Point(int x, int y) when x == 0 && y == 0 -> "origin";
        case Point(int x, int y) when x == y -> "diagonal";
        case Point(int x, int y) -> "point";
        case null -> "null";
        default -> "other value";
    };
}
```

Mỗi nhánh `case Point(...)` vừa xác nhận kiểu record vừa lấy component. Mệnh đề `when` là guard (điều kiện bổ sung) của pattern trong `switch`; nó chỉ chạy sau khi record pattern khớp. Trong `if`, có thể kết hợp pattern với toán tử `&&` để kiểm tra điều kiện tương tự:

```java
if (value instanceof Point(int x, int y) && x == y) {
    System.out.println("Point nằm trên đường chéo y = x");
}
```

Đặt các nhánh cụ thể trước nhánh tổng quát. Ví dụ `case Point(var x, var y)` khớp mọi `Point` không null, vì vậy nếu đặt trước một nhánh `Point(...)` hẹp hơn thì nhánh phía sau sẽ bị compiler xác định là unreachable (không thể đạt tới). Một pattern có guard như `when x == y` chỉ khớp khi điều kiện đúng, nên có thể đặt nhánh `Point(...)` tổng quát phía sau để xử lý các trường hợp còn lại.

## Phạm vi của pattern variable

Các biến được khai báo trong record pattern chỉ có thể được sử dụng tại nơi compiler xác định pattern đã khớp. Trong `if`, chúng có hiệu lực bên trong nhánh thành công và ở phần biểu thức bên phải của `&&` khi phần bên trái đã xác nhận pattern.

```java
static int sumIfPoint(Object value) {
    if (!(value instanceof Point(int x, int y))) {
        return 0;
    }

    // Nhánh không khớp đã return, vì vậy x và y đã được khởi tạo ở đây.
    return x + y;
}
```

Trong `switch`, các biến của record pattern chỉ có hiệu lực trong guard và phần thân của nhánh tương ứng. Không thể sử dụng `x`, `y` hoặc component variable của một nhánh ở nhánh `case` khác.

## Xử lý `null`

Một record pattern ở cấp ngoài không khớp với `null`:

```java
Object value = null;

if (value instanceof Point(int x, int y)) {
    // Không chạy khi value là null.
}
```

Với `switch`, nếu selector là `null`, cần có nhánh `case null` để xử lý. Nhánh `default` không tự động khớp với `null`; nếu không khai báo `case null`, việc switch trên giá trị null sẽ ném `NullPointerException`.

Đối với component kiểu tham chiếu, cần chú ý null ở từng cấp. `var` có thể nhận giá trị null, còn một record pattern lồng nhau không khớp với component null. Ví dụ:

```java
record Customer(String name, Address address) { }

static void inspectAddress(Object value) {
    if (value instanceof Customer(String name, var address)) {
        if (address == null) {
            System.out.println(name + " chưa có địa chỉ");
        } else if (address instanceof Address(var city, var district)) {
            System.out.println(district + ", " + city);
        }
    }
}
```

Trong `Customer(String name, var address)`, `var address` nhận cả trường hợp component là null. Cách viết này hữu ích khi ứng dụng cho phép component tùy chọn. Ngược lại, `Customer(String name, Address(var city, var district))` yêu cầu component `address` phải là một `Address` không null để pattern lồng nhau khớp.

Một type pattern dùng đúng kiểu hoặc kiểu cha tương thích với kiểu component được khai báo có thể là pattern vô điều kiện và vẫn khớp khi component có giá trị null. Nếu dùng một kiểu hẹp hơn kiểu khai báo của component, giá trị null không thể vượt qua phép kiểm tra kiểu đó. Vì vậy, không nên hiểu rằng toàn bộ component trong record pattern đều mặc định khác null; hãy xác định rõ component nào có thể null và kiểm tra phù hợp.

## Những điểm cần nhớ khi áp dụng

| Tình huống | Hành vi |
|---|---|
| Giá trị ngoài không phải kiểu record được nêu | Pattern không khớp |
| Giá trị ngoài là `null` | Record pattern không khớp |
| Một component không khớp pattern tương ứng | Toàn bộ record pattern không khớp |
| Component lồng nhau được kiểm tra bằng record pattern nhưng có giá trị `null` | Pattern lồng nhau không khớp |
| Tất cả pattern ở mọi cấp đều khớp | Các pattern variable được khởi tạo |
| Accessor của record ném exception khi được gọi | Quá trình matching kết thúc bằng `MatchException`, giữ exception gốc làm cause |

Record pattern lấy component thông qua accessor method tương ứng, theo thứ tự component được khai báo. Nếu record có accessor được triển khai tường minh, logic của accessor vẫn được thực thi trong quá trình matching. Vì vậy, accessor nên trả về dữ liệu component ổn định và tránh side effect; không nên dựa vào record pattern để bỏ qua logic của accessor.

Record pattern cũng không tạo bản sao record và không thay đổi đối tượng ban đầu. Các biến pattern chỉ nhận giá trị trả về từ accessor để xử lý tiếp.

Một số lưu ý về cú pháp và phiên bản:

- Record Patterns được hoàn thiện trong Java 21; khi biên dịch mã nguồn Java 21 không cần `--enable-preview`.
- Pattern matching cho `switch` cũng là tính năng chính thức từ Java 21; guard dùng từ khóa `when`.
- Java 21 yêu cầu pattern cho từng component theo đúng thứ tự. Nếu không dùng một giá trị, đặt tên như `var ignored`.
- Không dùng record pattern trong header của enhanced `for` như `for (Point(int x, int y) : points)`: cú pháp này không thuộc phiên bản Record Patterns được chuẩn hóa trong Java 21.

## Ví dụ tổng hợp

Ví dụ sau kết hợp `instanceof`, nested record pattern, generic record pattern và pattern matching trong `switch`:

```java
public class RecordPatternDemo {
    record Point(int x, int y) { }
    record Address(String city, String district) { }
    record Customer(String name, Address address) { }
    record Box<T>(T value) { }

    static void printPoint(Object value) {
        if (value instanceof Point(int x, int y)) {
            System.out.printf("Point(%d, %d)%n", x, y);
        }
    }

    static void printCustomer(Object value) {
        if (value instanceof Customer(
                String name,
                Address(var city, var district))) {
            System.out.println(name + " sống tại " + district + ", " + city);
        }
    }

    static void printBox(Box<String> box) {
        if (box instanceof Box(var text)) {
            System.out.println(text.toUpperCase());
        }
    }

    static String describe(Object value) {
        return switch (value) {
            case Point(int x, int y) when x == 0 && y == 0 -> "Origin";
            case Point(int x, int y) when x == y -> "Diagonal point";
            case Point(int x, int y) -> "Point: " + x + ", " + y;
            case Customer(String name, var address) -> "Customer: " + name;
            case null -> "No value";
            default -> "Unsupported value";
        };
    }

    public static void main(String[] args) {
        printPoint(new Point(3, 4));
        printCustomer(new Customer(
                "An", new Address("Đà Nẵng", "Hải Châu")));
        printBox(new Box<>("Java 21"));

        System.out.println(describe(new Point(0, 0)));
        System.out.println(describe(null));
    }
}
```

Có thể biên dịch bằng JDK 21 với:

```bash
javac --release 21 RecordPatternDemo.java
java RecordPatternDemo
```

Không cần bật preview feature. Khi đưa vào dự án Maven hoặc Gradle, đặt release mục tiêu là 21 và bảo đảm compiler đang dùng JDK có hỗ trợ Java 21.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java SE 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification, Java SE 21 — Patterns (Section 14.30)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
