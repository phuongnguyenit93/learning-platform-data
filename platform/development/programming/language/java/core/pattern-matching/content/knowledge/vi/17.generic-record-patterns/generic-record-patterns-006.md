# Giới hạn do type erasure trong generic record patterns (Java 21+)

## 1. Vấn đề cần hiểu

Java cho phép record mang tham số kiểu (*generic record*) và cho phép tách component của record bằng *record pattern*:

~~~java
record Box<T>(T value) {}

Box<String> box = new Box<>("Java");
if (box instanceof Box(var text)) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

Trong ví dụ này, trình biên dịch biết `box` có kiểu `Box<String>` nên suy luận biến `text` là `String`. Nhưng không được kết luận rằng phép so khớp đã kiểm tra được tham số `String` ở runtime.

**Ranh giới cốt lõi:** *Type erasure* xóa phần lớn thông tin về tham số kiểu generic khi biên dịch. Record pattern có thể dùng thông tin kiểu tĩnh để suy luận biến và kiểm tra tính hợp lệ của pattern, nhưng tại runtime nó **không thể tự xác thực** rằng một đối tượng `Box<?>` thật sự được tạo dưới kiểu `Box<String>` hay `Box<Integer>`.

Nội dung dưới đây áp dụng cho **Java 21 trở lên** (record patterns được chuẩn hóa trong JEP 440). Các ví dụ chương trình chạy dùng JDK 21+, không cần `--enable-preview`.

## 2. Type erasure tác động thế nào đến generic record?

Xét khai báo:

~~~java
record Box<T>(T value) {}
~~~

Ở mã nguồn, hai biến có kiểu tĩnh khác nhau:

~~~java
Box<String> names = new Box<>("hello");
Box<Integer> numbers = new Box<>(42);
~~~

Tham số kiểu `T` giúp trình biên dịch kiểm soát phép gán và kiểu kết quả của accessor. Tuy nhiên, theo quy tắc *type erasure* của Java:

- Cả `Box<String>` và `Box<Integer>` đều có cùng kiểu class ở runtime: `Box`. Chúng không trở thành hai lớp runtime khác nhau.
- `T` không có bound tường minh trong `Box<T>` nên khi xóa kiểu, vị trí sử dụng `T` được biểu diễn bằng `Object` trong chữ ký bytecode thích hợp. Nếu `T extends Number` thì erasure của `T` dựa trên bound trái nhất, ở đây là `Number`.
- Trình biên dịch có thể chèn phép ép kiểu khi cần sử dụng kết quả accessor trong ngữ cảnh cụ thể. Điều đó không thay thế việc kiểm chứng generic argument ở runtime.
- `names.getClass() == numbers.getClass()` là `true`. Phương thức `getClass()` của một instance không cho biết nó là `Box<String>` hay `Box<Integer>`.

Record pattern `Box(var item)` vẫn kiểm tra được đối tượng mang lớp `Box` và tách component `value`. Nhưng nó không có phép kiểm tra runtime tương đương với “`T` của record này phải là `String`”.

**Hai loại kiểm tra cần phân biệt:**

1. **Kiểm tra lớp record**: đối tượng có là instance của lớp `Box` không? Phép so khớp record pattern thực hiện được.
2. **Kiểm tra tham số generic**: instance này có thật sự là `Box<String>` thay vì `Box<Integer>` không? Vì erasure, không thể xác minh toàn bộ điều đó chỉ từ object tại runtime.

Có thể kiểm tra **giá trị component thực tế** bằng `instanceof String`, nhưng kết quả chỉ chứng minh giá trị đó là `String`, không chứng minh mọi khía cạnh của tham số generic đã được giữ lại.

## 3. Khi kiểu tĩnh đã biết: pattern được phép và biến được suy luận

Giả sử tham số phương thức là `Box<String>`:

~~~java
static void printTyped(Box<String> box) {
    if (box instanceof Box<String>(String value)) {
        System.out.println(value.toUpperCase());
    }

    if (box instanceof Box(var value)) {
        System.out.println(value.length());
    }
}
~~~

Cả hai pattern đều hợp lệ:

- `Box<String>(String value)` khai báo rõ tham số kiểu của record pattern và kiểu pattern của component.
- `Box(var value)` cho phép suy luận cả tham số generic của record pattern và kiểu biến `value` từ ngữ cảnh đầu vào `Box<String>`.
- Ở cả hai cách, `value` được xem là `String` trong thân `if`; gọi `toUpperCase()` hoặc `length()` được kiểm tra tại compile time.

Đây là **suy luận kiểu tĩnh**, không phải kiểm tra đối tượng đang lưu tham số `String` ở runtime. Java chấp nhận việc destructure an toàn trên cơ sở chương trình đã giữ đúng hợp đồng `Box<String>`.

Tương tự, với nhiều tham số kiểu:

~~~java
record Pair<A, B>(A first, B second) {}

static void readPair(Pair<String, Integer> pair) {
    if (pair instanceof Pair(var name, var count)) {
        String upper = name.toUpperCase();
        int next = count + 1;
        System.out.println(upper + ": " + next);
    }
}
~~~

Trình biên dịch suy luận `name` là `String` và `count` là `Integer`, rồi thực hiện unboxing khi tính `count + 1`. Nếu `count` bằng `null` thì unboxing có thể gây `NullPointerException`; việc khớp record pattern không tự bảo đảm component tham chiếu khác `null`.

## 4. Khi chỉ có Object hoặc raw type: giới hạn checked cast

Record pattern có thể mang kiểu generic tường minh **chỉ khi** kiểu của biểu thức đầu vào có thể chuyển sang kiểu record pattern bằng **checked cast conversion** (không cần *unchecked conversion*).

Ví dụ sau **không biên dịch**:

~~~java
record Box<T>(T value) {}

// KHÔNG biên dịch — chỉ để minh họa giới hạn.
static void invalid(Object input) {
    if (input instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
~~~

Vì `input` chỉ có kiểu tĩnh `Object`, runtime có thể xác định nó có là `Box` hay không, nhưng không thể kiểm tra đối tượng đó là `Box<String>`. Việc chuyển `Object` thành `Box<String>` yêu cầu kiểm tra generic argument đã bị xóa, nên `instanceof Box<String>(...)` bị từ chối khi biên dịch.

Tương tự, đoạn mã dùng **raw `Box`** cũng không biên dịch:

~~~java
// KHÔNG biên dịch — raw Box làm mất tham số kiểu.
static void invalidRaw(Box input) {
    if (input instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
~~~

Không nên hiểu thông báo lỗi như thể Java đã nhìn thấy một `Integer` nằm trong `Box`. Đây là lỗi **compile time** do phép cast không kiểm chứng được, chưa cần chạy chương trình hay xem dữ liệu bên trong.

**Điểm tinh tế:** Không phải mọi lần dùng `Box<String>(...)` đều bị cấm. Nó hợp lệ khi **kiểu tĩnh của đầu vào** vốn đã cung cấp đủ cơ sở để kiểm tra phép chuyển kiểu (ví dụ đầu vào `Box<String>` ở mục 3). Luật áp dụng là điều kiện *checked cast*, không phải lệnh cấm tuyệt đối đối với generic record patterns.

## 5. Cách an toàn với dữ liệu chưa biết kiểu: `Box<?>` và kiểm tra component

Khi nhận `Object` từ API hoặc một nguồn bên ngoài, có thể dùng wildcard `?` để kiểm tra record class mà không giả định tham số generic:

~~~java
static String inspect(Object input) {
    if (input instanceof Box<?>(var content)) {
        if (content instanceof String text) {
            return "String: " + text;
        }
        return "Giá trị khác";
    }
    return "Không phải Box";
}
~~~

Pattern `Box<?>(var content)` hợp lệ với `Object` vì `Box<?>` là kiểu có thể kiểm tra an toàn trong bối cảnh này; `content` không được suy luận là `String`. Với `Box<T>` không có bound, có thể xử lý `content` như `Object`. Nhánh `content instanceof String text` mới là **kiểm tra runtime thực sự** kiểu của giá trị component.

Một cách ngắn hơn:

~~~java
if (input instanceof Box(var content)) {
    // Khi input chỉ có kiểu Object, không được giả sử content là String.
    System.out.println(content);
}
~~~

Trường hợp này có thể suy luận kiểu record pattern, nhưng thông tin đầu vào không đủ để biến `content` có kiểu tĩnh `String`. Vì vậy câu lệnh `content.toUpperCase()` sẽ không biên dịch nếu không có bước kiểm tra/narrowing phù hợp.

**Với `null`:** record pattern trên chính giá trị `null` không khớp. Tuy nhiên, nếu đối tượng `Box` tồn tại còn component `value` bằng `null`, component pattern `var content` vẫn có thể ràng buộc `content == null`. Do đó nên kiểm tra `null` trước khi gọi phương thức trên giá trị component.

## 6. Generic record patterns lồng nhau: kiểu được lan truyền, không được kiểm chứng ở runtime

Suy luận kiểu vẫn hoạt động qua nhiều tầng khi kiểu tĩnh đã được khai báo chính xác:

~~~java
static void nested(Box<Box<String>> outer) {
    if (outer instanceof Box(Box(var text))) {
        System.out.println(text.toUpperCase());
    }
}
~~~

Trong ví dụ:

1. Tham số `outer` đã có kiểu tĩnh `Box<Box<String>>`.
2. Pattern ngoài `Box(...)` suy luận component `value` có kiểu `Box<String>`.
3. Pattern trong `Box(var text)` suy luận `text` có kiểu `String`.
4. Khi cả hai record pattern khớp, có thể gọi `text.toUpperCase()`.

Nếu component record bên trong bằng `null`, pattern `Box(...)` lồng trong không khớp và nhánh `if` không chạy. Nếu component `text` bằng `null`, pattern `var text` vẫn có thể khớp nhưng `toUpperCase()` sẽ lỗi nếu không kiểm tra trước.

**Giới hạn vẫn nguyên vẹn:** Việc trình biên dịch biết kiểu `Box<Box<String>>` không có nghĩa JVM đã kiểm tra hai tầng generic bằng runtime reflection. Nếu dữ liệu bị trộn kiểu do raw type hoặc unchecked cast (*heap pollution*), các giả định kiểu tĩnh có thể bị phá vỡ và gây lỗi runtime.

## 7. Phân biệt generic argument với kiểu giá trị đang nằm trong record

Hai trường hợp sau thường bị nhầm:

**Trường hợp A — biết component hiện tại là String.**

~~~java
Object unknown = new Box<>("hello");
if (unknown instanceof Box<?>(var item) && item instanceof String s) {
    System.out.println(s.toUpperCase()); // HELLO
}
~~~

Ở đây `item instanceof String s` kiểm tra trực tiếp object trong component. Nó có giá trị ngay cả khi ta không biết tham số generic của record.

**Trường hợp B — muốn kiểm tra record là Box<List<String>>.**

~~~java
record Container<T>(T value) {}
Object unknown = new Container<>(java.util.List.of("a", "b"));
~~~

Một pattern như `Container<java.util.List<String>>(var list)` áp dụng trực tiếp lên `Object` không kiểm chứng được `List<String>` ở runtime, vì kiểu tham số của cả `Container` và `List` đã bị erasure. Hướng xử lý an toàn là kiểm tra `Container<?>`, sau đó kiểm tra component có là `List<?>`, rồi kiểm tra từng phần tử nếu yêu cầu dữ liệu chỉ chứa chuỗi:

~~~java
if (unknown instanceof Container<?>(var value)
        && value instanceof java.util.List<?> list) {
    boolean allStrings = list.stream()
            .allMatch(item -> item instanceof String);
    System.out.println(allStrings); // true
}
~~~

`allStrings` kiểm tra các phần tử **hiện có** trong danh sách. Nó không biến danh sách thành `List<String>` ở mức kiểu tĩnh, không chứng minh lịch sử khởi tạo generic của nó và không ngăn dữ liệu khác được đưa vào sau này nếu cấu trúc còn có thể sửa. Với danh sách rỗng, `allMatch` trả về `true` theo logic “mọi phần tử đều thỏa”, dù không có phần tử nào để chứng minh kiểu.

## 8. Ví dụ đầy đủ chạy được với Java 21+

Lưu toàn bộ đoạn sau vào **`GenericRecordErasureDemo.java`**:

~~~java
public class GenericRecordErasureDemo {
    record Box<T>(T value) {}
    record Pair<A, B>(A first, B second) {}

    static String fromTyped(Box<String> box) {
        if (box instanceof Box<String>(var text)) {
            return text.toUpperCase();
        }
        return "Không khớp";
    }

    static String fromUnknown(Object input) {
        if (input instanceof Box<?>(var content)) {
            if (content instanceof String text) {
                return "String: " + text;
            }
            return "Khác: " +
                    (content == null ? "null" : content.getClass().getSimpleName());
        }
        return "Không phải Box";
    }

    static String fromNested(Box<Box<String>> outer) {
        if (outer instanceof Box(Box(var text))) {
            return "Nested: " + text;
        }
        return "Nested không khớp";
    }

    static String fromPair(Pair<String, Integer> pair) {
        if (pair instanceof Pair(var name, var count)) {
            return name.toUpperCase() + ": " + (count + 1);
        }
        return "Pair không khớp";
    }

    public static void main(String[] args) {
        System.out.println(fromTyped(new Box<>("java")));
        System.out.println(fromUnknown(new Box<>("hello")));
        System.out.println(fromUnknown(new Box<>(42)));
        System.out.println(fromUnknown(new Box<>(null)));
        System.out.println(fromUnknown("other"));
        System.out.println(fromNested(new Box<>(new Box<>("ok"))));
        System.out.println(fromNested(new Box<>(null)));
        System.out.println(fromPair(new Pair<>("task", 4)));
    }
}
~~~

Biên dịch và chạy bằng JDK 21+:

~~~bash
javac --release 21 GenericRecordErasureDemo.java
java GenericRecordErasureDemo
~~~

Đầu ra chính xác:

~~~text
JAVA
String: hello
Khác: Integer
Khác: null
Không phải Box
Nested: ok
Nested không khớp
TASK: 5
~~~

Giải thích:

- `fromTyped`: kiểu tĩnh `Box<String>` cho phép `Box<String>(var text)` và biến `text` có kiểu `String`.
- `fromUnknown`: dùng `Box<?>` để khớp an toàn, rồi kiểm tra riêng `content instanceof String`; các giá trị `Integer`, `null` và đầu vào không phải `Box` được xử lý riêng.
- `fromNested`: suy luận kiểu `String` qua hai record pattern lồng nhau; pattern trong không khớp khi record trong `null`.
- `fromPair`: suy luận đồng thời `String` và `Integer` từ `Pair<String, Integer>`, dùng được các phép toán phù hợp.

Cùng cú pháp record pattern có thể dùng trong `switch`. Các quy tắc về *checked cast*, type erasure và suy luận kiểu generic vẫn áp dụng; `switch` không tạo thêm khả năng nhận diện tham số kiểu bị xóa.

## 9. Heap pollution và giới hạn bảo đảm của trình biên dịch

**Heap pollution** xảy ra khi một biến mang kiểu parameterized lại tham chiếu tới dữ liệu không thực sự phù hợp kiểu đó, thường do raw type, unchecked cast hoặc API không tuân thủ generics.

Ví dụ dưới đây chỉ để phân tích rủi ro; **không chạy chung với ví dụ hoàn chỉnh**:

~~~java
record Box<T>(T value) {}

@SuppressWarnings({"rawtypes", "unchecked"})
static Box<String> unsafeBox() {
    Box raw = new Box(123);
    return raw; // Unchecked conversion: che cảnh báo không làm dữ liệu an toàn.
}
~~~

Nếu truyền kết quả của `unsafeBox()` vào hàm nhận `Box<String>` và dùng record pattern với biến suy luận `String`, chương trình có thể lỗi khi cần xử lý `Integer` như `String`. Việc record pattern khớp lớp `Box` không sửa được hợp đồng generic đã bị phá vỡ.

Trong ứng dụng thực tế:

- Tránh raw types và unchecked casts ở ranh giới dữ liệu.
- Dùng `Box<?>`/pattern trên component khi kiểu đầu vào chưa đáng tin, kết hợp kiểm tra runtime từng giá trị.
- Nếu cần xác thực một kiểu phần tử ở runtime, có thể cung cấp thêm `Class<T>` làm *type token* cho các kiểu có thể kiểm tra với `Class.isInstance`. Nhưng `Class<List<String>>` không tồn tại như một class token có thể xác minh tham số phần tử; với generic lồng, cần quy tắc xác thực từng cấp/từng phần tử.
- Với collection cần duy trì hợp đồng kiểu, ưu tiên API generic và dữ liệu đã được kiểm tra tại thời điểm đưa vào thay vì hy vọng pattern sẽ phát hiện mọi sai lệch về sau.

## 10. Bảng quyết định: pattern nào hợp lệ?

Trong các ví dụ, record được khai báo là `record Box<T>(T value) {}`.

| Kiểu tĩnh của biểu thức | Pattern | Kết quả biên dịch và giới hạn |
| --- | --- | --- |
| `Box<String>` | `Box<String>(var text)` | Hợp lệ; `text` có kiểu tĩnh `String`. |
| `Box<String>` | `Box(var text)` | Hợp lệ; `text` suy luận thành `String`. |
| `Box<?>` | `Box(var item)` | Hợp lệ; không suy luận `item` thành `String` chỉ từ wildcard. |
| `Object` | `Box<?>(var item)` | Hợp lệ; kiểm tra lớp record và ràng buộc component, không xác minh generic argument cụ thể. |
| `Object` | `Box(var item)` | Hợp lệ; không đủ ngữ cảnh để gọi trực tiếp phương thức riêng của `String` trên `item`. |
| `Object` | `Box<String>(var text)` | **Lỗi biên dịch**: cần unchecked conversion. |
| Raw `Box` | `Box<String>(var text)` | **Lỗi biên dịch**: mất căn cứ kiểm tra `String`. |
| `Box<Box<String>>` | `Box(Box(var text))` | Hợp lệ; suy luận `text` thành `String` qua record pattern lồng nhau. |

## 11. Những hiểu nhầm thường gặp

**“Tôi viết `Box<String>(...)` nên Java sẽ xác minh type argument `String` tại runtime.”** Không đúng. Mẫu này hợp lệ khi luật checked cast cho phép dựa trên kiểu tĩnh. Type erasure vẫn tồn tại.

**“Đã dùng `var` thì mọi component có kiểu `Object`.”** Không đúng. Nếu đầu vào có kiểu `Box<String>`, `Box(var s)` suy luận `s` là `String`; nếu đầu vào chỉ là `Object`, kiểu suy luận thường ít cụ thể hơn.

**“`Box<?>` khiến tôi được ép mọi giá trị sang `String`.”** Không đúng. Wildcard cho phép thao tác an toàn với kiểu chưa biết, nhưng cần `instanceof String` hoặc xác thực cụ thể trước khi dùng API của `String`.

**“Nested record patterns kiểm chứng toàn bộ cây generic ở runtime.”** Không đúng. Chúng giúp destructure và suy luận thông tin tĩnh qua nhiều lớp record. Các tham số generic bị erasure vẫn không thể được xác minh hoàn toàn từ một object bất kỳ.

**“Tắt unchecked warning là sửa được lỗi.”** Không đúng. `@SuppressWarnings("unchecked")` chỉ tác động cảnh báo; dữ liệu sai kiểu vẫn có thể gây lỗi runtime.

**“`instanceof List<?>` chứng minh đây là `List<String>`.”** Không đúng. Nó xác minh đối tượng là `List` nhưng không biết kiểu generic của phần tử. Kiểm tra từng phần tử chỉ xác nhận trạng thái dữ liệu được quan sát.

## 12. Tự kiểm tra kiến thức

1. Vì sao `Object source` không thể dùng `source instanceof Box<String>(var text)`, nhưng `source instanceof Box<?>(var text)` lại được?
2. Khi đầu vào là `Box<String>`, vì sao `Box(var text)` suy luận `text` thành `String` mà vẫn không kiểm tra được `String` là runtime type argument?
3. Với `Box<Box<String>>`, chuyện gì xảy ra nếu component `Box<String>` bên trong bằng `null`? Nếu record trong tồn tại nhưng giá trị `String` bằng `null` thì sao?
4. Vì sao kiểm tra từng phần tử của `List<?>` không đồng nghĩa với việc xác minh đầy đủ một đối tượng có kiểu `List<String>` ở runtime?
5. Nên làm gì khi nhận đối tượng chưa biết kiểu từ API ngoài nhưng muốn xử lý một component chuỗi một cách an toàn?

**Đáp án định hướng:** (1) `Box<String>` từ `Object` cần unchecked cast, còn `Box<?>` kiểm tra được; (2) kiểu tĩnh cho compiler suy luận, erasure không lưu tham số của instance; (3) pattern trong không khớp nếu record trong `null`, nhưng `var text` có thể ràng buộc `null` nếu record trong tồn tại; (4) quan sát phần tử không khôi phục được tham số generic đã bị xóa; (5) kiểm tra `Box<?>` rồi `instanceof String` trên component, xử lý `null` và loại dữ liệu khác.

## Tài liệu tham khảo

- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns và generic type inference trong Java 21.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): ví dụ `Box<String>`, lỗi unchecked conversion, `var` và nested record patterns.
- [JLS 21, `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6): quy tắc xóa kiểu generic.
- [JLS 21, `18.5.5 — Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5): suy luận tham số generic trong record pattern.
