# Nhận diện lỗi biên dịch do suy luận kiểu hoặc pattern không tương thích

Trong Java 21, compiler kiểm tra generic type và pattern dựa trên kiểu tĩnh của biểu thức tại thời điểm biên dịch. Vì vậy, một đối tượng có thể chứa dữ liệu đúng ở runtime nhưng mã nguồn vẫn không biên dịch nếu kiểu tham số không thể suy luận nhất quán, kiểu pattern không thể kiểm tra an toàn hoặc pattern không thể khớp với kiểu tĩnh của biểu thức.

Khi gặp lỗi ở khu vực Generics và Pattern Matching, hãy xác định lần lượt: kiểu tĩnh của biểu thức, kiểu mà compiler suy luận cho các tham số generic, kiểu pattern đang yêu cầu và liệu phép kiểm tra có cần unchecked conversion hay không. Các bước này giúp phân biệt lỗi suy luận kiểu với lỗi tương thích pattern.

## 1. Phân biệt lỗi biên dịch và kết quả matching lúc chạy

Compiler kiểm tra khả năng tương thích trước khi chương trình chạy. Ví dụ, nếu biến có kiểu `Integer`, compiler biết `Integer` là lớp final và không thể đồng thời là `String`; pattern sau không thể khớp với bất kỳ giá trị hợp lệ nào của biến:

```java
Integer number = 21;

if (number instanceof String text) { // Lỗi biên dịch
    System.out.println(text);
}
```

Nếu giá trị được giữ trong biến có kiểu tổng quát hơn như `Object`, phép kiểm tra có thể hợp lệ:

```java
Object value = number;

if (value instanceof String text) {
    System.out.println(text);
}
```

Ví dụ thứ hai biên dịch được vì một giá trị có kiểu tĩnh `Object` có thể tham chiếu tới `String`. Với giá trị hiện tại là `Integer`, nhánh `if` không chạy. Compiler chỉ xác nhận phép kiểm tra có thể xảy ra theo kiểu tĩnh; kết quả matching phụ thuộc đối tượng thực tế.

Đối với generic, cần nhớ rằng Java dùng type erasure. Runtime biết một đối tượng là `List`, nhưng không giữ đủ thông tin để xác nhận nó là `List<String>` hay `List<Integer>`. Vì vậy, không phải mọi kiểu generic viết được ở khai báo biến đều có thể dùng làm kiểu pattern.

## 2. Lỗi suy luận kiểu generic

### Diamond operator thiếu ngữ cảnh kiểu đích

Diamond operator (`<>`) cho phép compiler suy luận tham số kiểu khi tạo đối tượng. Nếu biểu thức có kiểu đích, compiler có thể sử dụng kiểu đó để suy luận:

```java
List<String> names = new ArrayList<>();
```

Trong ví dụ này, kiểu đích `List<String>` giúp compiler suy luận `ArrayList<String>`. Nhưng khi dùng `var`, biến được suy luận từ chính biểu thức khởi tạo; không có kiểu đích từ phía bên trái để truyền vào diamond:

```java
var names = new ArrayList<>(); // ArrayList<Object>

// Không thể gán ArrayList<Object> cho List<String>:
// List<String> textNames = names;
```

Hãy khai báo tham số kiểu tường minh khi không có kiểu đích:

```java
var names = new ArrayList<String>();
// Hoặc:
List<String> names2 = new ArrayList<>();
```

### Factory method generic không nhận được kiểu đích

Các factory method như `List.of` và `Collections.emptyList` cũng suy luận tham số kiểu theo đối số và ngữ cảnh sử dụng.

```java
var empty = List.of(); // List<Object>

// Không thể gán List<Object> cho List<String>:
// List<String> names = empty;
```

Nếu muốn nhận `List<String>`, hãy cung cấp kiểu đích hoặc type witness (kiểu tham số tường minh trong lời gọi method):

```java
List<String> names = List.of();

var anotherEmpty = List.<String>of();
var alsoEmpty = Collections.<String>emptyList();
```

Không nên kỳ vọng compiler suy luận từ một phép gán ở dòng sau. Kiểu của biến `var` được xác định ngay tại biểu thức khởi tạo và không thay đổi theo các lần sử dụng tiếp theo.

### Các đối số tạo ra ràng buộc kiểu mâu thuẫn

Một generic method có thể yêu cầu các đối số cùng chia sẻ một tham số kiểu. Nếu các đối số cung cấp ràng buộc không tương thích, compiler không tìm được kiểu thỏa mãn:

```java
static <T> void addTo(T value, List<T> destination) {
    destination.add(value);
}

static void example() {
    // Lỗi: đối số đầu yêu cầu T phù hợp với String,
    // nhưng List<Integer> yêu cầu T là Integer.
    addTo("Java", List.of(21));
}
```

`List<T>` là kiểu invariant (bất biến theo tham số kiểu). `List<Integer>` không phải `List<Number>` hoặc `List<Object>`, dù `Integer` là một kiểu con của `Number` và `Object`.

Nếu đích nhận dữ liệu cần cho phép một kiểu cha của `T`, có thể thiết kế tham số bằng wildcard có giới hạn dưới:

```java
static <T> void addTo(T value, List<? super T> destination) {
    destination.add(value);
}

static void example() {
    List<Object> values = new ArrayList<>();
    addTo("Java", values); // T được suy luận là String
}
```

Nếu API yêu cầu chính xác `List<T>`, hãy truyền collection có đúng tham số kiểu thay vì cố ép compiler chọn một kiểu chung không tồn tại.

### Lambda hoặc method reference không có kiểu đích

Lambda và method reference cần một kiểu functional interface làm ngữ cảnh để compiler xác định kiểu tham số và kiểu trả về. `var` không cung cấp kiểu đích đó:

```java
// Không hợp lệ: compiler không có functional interface để suy luận.
// var length = (String text) -> text.length();

Function<String, Integer> length = text -> text.length();
var anotherLength = (Function<String, Integer>) String::length;
```

Khi lỗi xuất hiện ở lambda, hãy khai báo kiểu functional interface ở biến, tham số method hoặc ép kiểu lambda sang functional interface phù hợp. Chỉ thêm kiểu tham số bên trong lambda không thay thế được kiểu đích của chính biểu thức lambda.

## 3. Wildcard và capture conversion

Wildcard biểu diễn một tập kiểu chưa biết cụ thể. `List<? extends Number>` cho phép đọc phần tử dưới dạng `Number`, nhưng không cho phép thêm một `Integer` tùy ý vì kiểu thực tế của list có thể là `List<Double>`:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }

    // Không hợp lệ:
    // values.add(21);

    return total;
}
```

Tương tự, sau khi matching `List<?>`, compiler chỉ biết kiểu phần tử là một kiểu chưa xác định. Có thể đọc phần tử dưới dạng `Object`, nhưng không thể thêm một giá trị tùy ý:

```java
static void inspect(Object candidate) {
    if (candidate instanceof List<?> values) {
        for (Object value : values) {
            System.out.println(value);
        }

        // Không hợp lệ: kiểu phần tử của values chưa được biết.
        // values.add("Java");
    }
}
```

Đây không phải lỗi pattern matching. Pattern đã khớp với một `List` hợp lệ; lỗi phát sinh khi thao tác với generic collection bằng một kiểu phần tử chưa được xác định. Nếu cần tạo danh sách chuỗi từ dữ liệu không tin cậy, hãy kiểm tra từng phần tử rồi đưa những giá trị đã xác nhận vào một danh sách mới:

```java
static List<String> onlyStrings(Object candidate) {
    List<String> result = new ArrayList<>();

    if (candidate instanceof List<?> values) {
        for (Object value : values) {
            if (value instanceof String text) {
                result.add(text);
            }
        }
    }

    return result;
}
```

## 4. Pattern generic không thể kiểm tra an toàn

### Kiểm tra tham số generic phải dựa trên kiểu tĩnh an toàn

`List<String>` không phải reifiable type (kiểu có thể kiểm tra đầy đủ ở runtime). Nếu selector chỉ có kiểu `Object`, compiler không thể xác nhận tham số `String` sau type erasure; phép chuyển đổi từ `Object` sang `List<String>` cần unchecked conversion nên pattern không hợp lệ:

```java
Object candidate = List.of("Java", "21");

// Lỗi biên dịch: Object không thể chuyển an toàn sang List<String>.
// if (candidate instanceof List<String> names) { ... }
```

Tuy nhiên, Java 21 không cấm mọi type pattern có tham số generic cụ thể. Pattern được chấp nhận nếu kiểu tĩnh của selector cho phép checked cast conversion đến kiểu pattern mà không cần unchecked conversion. Ví dụ sau hợp lệ vì `List<Integer>` có thể được kiểm tra xem có phải `ArrayList<Integer>` hay không:

```java
List<Integer> candidate = new ArrayList<>(List.of(21));

if (candidate instanceof ArrayList<Integer> numbers) {
    System.out.println(numbers.getFirst());
}
```

Ở đây compiler không cần xác minh lại tham số `Integer` từ một `Object` tùy ý; kiểu tĩnh `List<Integer>` đã cung cấp thông tin generic và phép kiểm tra chỉ tinh chỉnh kiểu collection sang `ArrayList<Integer>`.

Khi selector chỉ là `Object` hoặc kiểu tĩnh không đủ để chứng minh tham số cụ thể, hãy dùng `List<?>` để kiểm tra kiểu collection, sau đó kiểm tra kiểu từng phần tử:

```java
if (candidate instanceof List<?> values) {
    for (Object value : values) {
        if (value instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

`List<?>` là reifiable type vì mọi tham số kiểu đều là unbounded wildcard. Pattern xác nhận đối tượng là một `List`, không khẳng định tất cả phần tử đều là `String`.

Quy tắc checked cast conversion cũng áp dụng cho type pattern trong `switch`. Với selector có kiểu `Object`, `case List<String> values` cần unchecked conversion và không hợp lệ; `case List<?> values` là lựa chọn an toàn. Nếu selector đã có kiểu generic cụ thể, hãy xét khả năng chuyển đổi từ chính kiểu tĩnh đó thay vì áp dụng máy móc quy tắc chỉ cho `Object`.

### Phân biệt type pattern với record pattern generic

Record pattern cũng tuân theo quy tắc checked cast conversion: có thể dùng kiểu tham số cụ thể nếu biểu thức được matching có thể chuyển sang kiểu record đó mà không cần unchecked conversion. Điểm hữu ích riêng của record pattern là compiler còn có thể suy luận tham số kiểu và kiểu component pattern từ kiểu tĩnh của selector.

```java
record Box<T>(T value) { }

static void printTypedBox(Box<String> box) {
    if (box instanceof Box<String>(String text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Ví dụ hợp lệ vì kiểu tĩnh của `box` đã là `Box<String>`. Compiler có đủ thông tin kiểu để kiểm tra phép chuyển đổi mà không phải giả định tham số generic tại runtime.

Ngược lại, nếu biểu thức chỉ có kiểu `Object`, compiler không thể xác nhận đối tượng đó là `Box<String>`:

```java
static void printUnknownBox(Object candidate) {
    // Không hợp lệ: Object không thể được chuyển an toàn sang Box<String>.
    // if (candidate instanceof Box<String>(var value)) { ... }

    if (candidate instanceof Box<?> (String text)) {
        System.out.println(text.toUpperCase());
    }
}
```

`Box<?>` kiểm tra kiểu record mà không khẳng định tham số generic cụ thể. Pattern component `String text` tiếp tục kiểm tra giá trị được trả về bởi accessor `value()`. Vì thế, nhánh chỉ chạy nếu đối tượng là `Box` và component thực tế khớp với `String`.

### Sử dụng type inference trong record pattern

Khi kiểu tĩnh của biểu thức đã mang thông tin generic, compiler có thể suy luận tham số kiểu của record pattern và kiểu các pattern variable:

```java
record Box<T>(T value) { }

static void printBox(Box<String> box) {
    if (box instanceof Box(var text)) {
        // text được suy luận là String
        System.out.println(text.toUpperCase());
    }
}
```

Với record lồng nhau, quá trình suy luận được áp dụng ở từng cấp:

```java
record Box<T>(T value) { }

static void printNestedBox(Box<Box<String>> box) {
    if (box instanceof Box(Box(var text))) {
        // text được suy luận là String
        System.out.println(text.toUpperCase());
    }
}
```

Nếu kiểu tĩnh không cung cấp đủ thông tin để suy luận tham số cụ thể, hãy dùng wildcard phù hợp rồi kiểm tra component bằng pattern riêng. Không ép compiler suy ra `String` chỉ vì dữ liệu mẫu hiện tại tình cờ chứa chuỗi.

## 5. Pattern không tương thích với kiểu tĩnh

### Hai kiểu không thể cùng mô tả một đối tượng

Compiler từ chối pattern nếu kiểu tĩnh và kiểu pattern không có khả năng giao nhau theo quy tắc chuyển đổi của Java. Ví dụ `Integer` và `String` là hai lớp final không liên quan:

```java
Integer id = 21;

// Lỗi biên dịch: Integer không thể là String.
// if (id instanceof String text) { ... }
```

Khi cần kiểm tra kiểu của một giá trị có nguồn gốc chưa biết, hãy giữ nó trong biến có kiểu tổng quát phù hợp như `Object` hoặc một interface chung mà các kiểu cần xét có thể triển khai.

### Pattern luôn khớp với mọi giá trị khác null

Java 21 cho phép type pattern có kiểu là supertype của kiểu tĩnh của biểu thức, dù phép kiểm tra thường luôn thành công với mọi giá trị khác null. Đây không còn là lỗi biên dịch như quy tắc trước Java 21:

```java
String name = "Java";

if (name instanceof Object value) {
    System.out.println(value);
}
```

Pattern trên luôn khớp khi `name` khác null và không khớp nếu `name` là null. Nếu mục đích chỉ là kiểm tra null, `name != null` diễn đạt ý định rõ hơn; nếu chỉ cần dùng giá trị dưới kiểu `Object`, có thể gán trực tiếp cho biến `Object`.

Điều tương tự áp dụng với generic:

```java
List<String> names = List.of("Java");

if (names instanceof List<?> values) {
    System.out.println(values.size());
}
```

Pattern này hợp lệ trong Java 21 vì mọi `List<String>` khác null đều là `List<?>`. Lưu ý rằng biến `values` có kiểu `List<?>`, vì vậy thông tin component `String` của biến `names` không còn được thể hiện qua biến pattern. Nếu không cần kiểm tra null hoặc chuyển sang kiểu khác, hãy sử dụng `names` trực tiếp.

### Pattern variable chỉ tồn tại trong vùng đã xác nhận matching

Pattern variable chỉ được dùng ở nơi compiler xác định pattern đã khớp. Toán tử `&&` cho phép sử dụng biến ở vế phải vì vế phải chỉ được đánh giá khi vế trái là `true`:

```java
static void printStrings(Object candidate) {
    if (candidate instanceof List<?> values && !values.isEmpty()) {
        System.out.println(values.getFirst());
    }
}
```

Với kiểm tra phủ định và thoát sớm, biến pattern cũng có thể được sử dụng sau câu lệnh:

```java
static void printList(Object candidate) {
    if (!(candidate instanceof List<?> values)) {
        return;
    }

    System.out.println(values.size());
}
```

Không dùng pattern variable ở nhánh mà pattern có thể chưa khớp, chẳng hạn ở vế phải của `||` khi vế trái là phép matching:

```java
// Không hợp lệ vì vế phải có thể chạy khi pattern không khớp.
// if (candidate instanceof String text || text.isEmpty()) { ... }
```

## 6. Nhận diện lỗi trong pattern matching cho `switch`

Pattern matching cho `switch` trong Java 21 là tính năng chính thức. Các quy tắc tương thích kiểu generic vẫn áp dụng cho type pattern và record pattern. Ngoài ra, compiler kiểm tra thứ tự nhánh để phát hiện pattern bị một nhánh trước đó bao phủ.

Ví dụ sau dùng `List<?>`, là kiểu có thể kiểm tra an toàn:

```java
static String describe(Object value) {
    return switch (value) {
        case List<?> values -> "List có " + values.size() + " phần tử";
        case null -> "null";
        default -> "Giá trị khác";
    };
}
```

Với selector có kiểu `Object`, đổi `List<?>` thành `List<String>` sẽ yêu cầu unchecked conversion nên compiler từ chối. Nếu đặt một pattern tổng quát trước pattern cụ thể hơn, nhánh cụ thể có thể bị dominated (bị bao phủ) và compiler báo không thể đạt tới:

```java
static String describeList(Object value) {
    return switch (value) {
        case List<?> values -> "List";
        // Không hợp lệ: ArrayList<?> đã được bao phủ bởi List<?> ở trên.
        // case ArrayList<?> values -> "ArrayList";
        default -> "Other";
    };
}
```

Hãy đặt pattern cụ thể trước pattern tổng quát. Khi dùng `switch` với selector có thể là null, thêm `case null` nếu cần xử lý null; `default` không tự động thay thế nhánh này.

## 7. Bảng chẩn đoán nhanh

Thông báo cụ thể có thể khác nhau giữa các phiên bản compiler, nhưng các nhóm lỗi thường chỉ ra những nguyên nhân sau:

| Dấu hiệu từ compiler | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `cannot infer type arguments` hoặc `incompatible bounds` | Các đối số hoặc kiểu đích đưa ra ràng buộc generic mâu thuẫn | Kiểm tra từng đối số; khai báo kiểu tường minh hoặc điều chỉnh wildcard của API |
| `incompatible types` khi gán collection | Generic invariant; ví dụ `List<Integer>` không phải `List<Number>` | Dùng đúng tham số kiểu hoặc wildcard `? extends` / `? super` theo hướng đọc và ghi |
| Lambda cần target type | Biểu thức lambda hoặc method reference không có functional interface làm kiểu đích | Khai báo `Function`, `Predicate`, interface phù hợp hoặc ép kiểu biểu thức |
| `cannot be safely cast` hoặc pattern không applicable | Kiểu pattern yêu cầu unchecked conversion hoặc không tương thích với kiểu tĩnh của selector | Kiểm tra checked cast conversion; dùng `List<?>`, `Box<?>` rồi kiểm tra component riêng khi kiểu tham số chưa biết |
| Pattern luôn khớp với mọi giá trị khác null | Kiểu pattern là supertype của kiểu tĩnh; hành vi này được Java 21 cho phép | Xác định có cần kiểm tra null hay chỉ cần dùng biến hiện có; không coi đây là lỗi biên dịch trong Java 21 |
| Hai kiểu không thể chuyển đổi hoặc không tương thích | Kiểu pattern và kiểu tĩnh không thể cùng mô tả một đối tượng | Kiểm tra khai báo kiểu và quan hệ kế thừa/interface; không ép kiểu để che lỗi mô hình |
| Pattern bị dominated hoặc unreachable | Nhánh trước đã bao phủ mọi giá trị mà pattern sau có thể nhận | Sắp xếp pattern cụ thể trước pattern tổng quát |
| Pattern variable không tìm thấy hoặc không nằm trong scope | Dùng biến ngoài nhánh/biểu thức đã xác nhận matching | Đưa thao tác vào nhánh đúng hoặc dùng cấu trúc `&&` / kiểm tra phủ định rồi thoát sớm |

## 8. Quy trình xử lý lỗi

Khi compiler báo lỗi tại một biểu thức generic hoặc pattern, có thể làm theo trình tự sau:

1. **Đọc kiểu tĩnh của biểu thức.** Xem khai báo biến, kiểu trả về của method và kiểu tham số tại điểm gọi. Đừng suy luận kiểu chỉ từ giá trị runtime.
2. **Viết rõ kiểu generic đang được suy luận.** Tạm thay `var` bằng kiểu tường minh hoặc thêm type witness như `List.<String>of()` để biết compiler cần kiểu nào.
3. **Kiểm tra invariant và wildcard.** Xác định API cần đọc dữ liệu (`? extends T`), ghi dữ liệu (`? super T`) hay yêu cầu chính xác `T`.
4. **Kiểm tra khả năng reifiable và kiểu selector.** Nếu selector chỉ có kiểu `Object`, type pattern `List<String>` cần unchecked conversion; dùng `List<?>` rồi xác nhận từng phần tử. Nếu selector đã có kiểu generic cụ thể, kiểm tra xem phép chuyển đổi đến kiểu pattern có an toàn hay không.
5. **Kiểm tra riêng record pattern.** Kiểu tham số cụ thể chỉ hợp lệ khi phép chuyển đổi từ kiểu tĩnh của selector sang kiểu record pattern không cần unchecked conversion. Khi không đủ thông tin, dùng wildcard.
6. **Kiểm tra quan hệ giữa các kiểu và flow scope.** Pattern có thể không tương thích, luôn đúng hoặc biến pattern nằm ngoài vùng matching.
7. **Biên dịch lại với chẩn đoán chi tiết.** Dùng compiler JDK 21 và đọc lỗi đầu tiên trong chuỗi lỗi; các lỗi phía sau có thể chỉ là hệ quả.

Ví dụ chạy compiler với release mục tiêu Java 21:

```bash
javac --release 21 -Xdiags:verbose Example.java
```

Khi lỗi đến từ Maven hoặc Gradle, hãy xác nhận build đang dùng JDK/compiler tương thích Java 21 và cùng cấu hình release với môi trường dự định triển khai. Thông báo lỗi của build tool có thể bao gồm thêm lớp gọi plugin, nhưng quy tắc kiểu vẫn do compiler Java áp dụng.

## 9. Những nguyên tắc nên áp dụng

- Dùng `var` khi kiểu khởi tạo đã rõ ràng; thêm kiểu tường minh khi diamond hoặc factory method không có đủ ngữ cảnh.
- Không kỳ vọng `var` lấy kiểu từ phép gán ở dòng sau.
- Dùng generic type cụ thể ở khai báo và API; dùng wildcard tại ranh giới cần xử lý dữ liệu chưa biết kiểu.
- Không dùng raw type hoặc unchecked cast để vượt qua lỗi generic. Chúng bỏ qua một phần kiểm tra kiểu và có thể đẩy lỗi sang runtime.
- Dùng `List<?>` hoặc `Box<?>` để kiểm tra an toàn kiểu runtime, sau đó kiểm tra từng component bằng pattern phù hợp.
- Tận dụng suy luận kiểu của record pattern khi selector đã có kiểu generic cụ thể; nếu selector chỉ là `Object`, hãy dùng wildcard và pattern lồng nhau để xác nhận dữ liệu.
- Đặt nhánh pattern cụ thể trước nhánh tổng quát trong `switch` và xử lý `null` rõ ràng.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java SE 21 — Pattern Matching for the `instanceof` Operator](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Oracle Java SE 21 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/21/language/local-variable-type-inference.html)
- [Java Language Specification, Java SE 21 — Reifiable Types (Section 4.7)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7)
- [Java Language Specification, Java SE 21 — Type Inference (Chapter 18)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html)
- [Java Language Specification, Java SE 21 — Properties of Patterns (Section 14.30.3)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [Java Language Specification, Java SE 21 — The `instanceof` Operator (Section 15.20.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394)
- [OpenJDK JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441)
