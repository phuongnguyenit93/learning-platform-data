# Tránh raw record pattern

## 1. Vì sao cần tránh raw type khi dùng generic record?

Giả sử ta khai báo một record có tham số kiểu:

```java
record Box<T>(T value) {}
```

`Box<String>` có component `value` được biểu diễn bằng `String` ở thời điểm biên dịch; `Box<Integer>` có component tương ứng được biểu diễn bằng `Integer`. Kiểu tổng quát giúp trình biên dịch phát hiện lỗi dùng nhầm kiểu trước khi chạy chương trình.

Một cách viết cũ là bỏ tham số kiểu ở biến hoặc khi khởi tạo:

```java
Box raw = new Box("hello"); // raw type: trình biên dịch có thể cảnh báo
```

Biến `raw` mang **raw type** (`Box` thay vì `Box<T>`, `Box<String>` hoặc `Box<?>`). Việc bỏ thông tin kiểu làm suy yếu kiểm tra kiểu tĩnh và có thể dẫn đến phép chuyển đổi không được kiểm tra (*unchecked conversion*). Trong chương trình mới, nên tránh khai báo biến hoặc API bằng raw type khi có thể sử dụng kiểu có tham số.

Tuy nhiên, có một điểm rất dễ hiểu nhầm trong **Java 21**: viết record pattern `Box(var value)` mà không ghi `<T>` **không nhất thiết tạo ra một phép khớp raw**. Đối với record pattern của generic record, Java có cơ chế **suy luận đối số kiểu** (*type argument inference*) từ kiểu của giá trị đang được khớp. Vì vậy, cần phân biệt rõ:

- `Box raw`: khai báo biến bằng raw type, làm mất thông tin kiểu ở phía biến.
- `Box(var value)`: cú pháp record pattern bỏ đối số kiểu tường minh để trình biên dịch **suy luận kiểu** trong ngữ cảnh có thể suy luận.
- `Box<?> box`: dùng wildcard để nói rõ rằng ta có một `Box` nhưng **chưa biết** đối số kiểu `T` là gì; đây là cách biểu diễn thông tin không xác định mà không dùng raw type.
- `Box<String>(var value)`: record pattern ghi rõ đối số kiểu `String`; chỉ hợp lệ khi phép kiểm tra kiểu phù hợp với quy tắc chuyển kiểu an toàn của Java.

Bài này tập trung vào việc giữ thông tin kiểu, chọn cách viết pattern đúng và tránh cảm giác an toàn giả khi dữ liệu đi qua `Object` hoặc raw type.

## 2. Khi đầu vào có kiểu generic rõ ràng: để Java suy luận

Với phương thức nhận `Box<String>`:

```java
static void printUpper(Box<String> box) {
    if (box instanceof Box(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Java 21 suy luận record pattern `Box(var text)` tương ứng với `Box<String>(var text)` trong ngữ cảnh này. Biến `text` có kiểu tĩnh `String`, nên gọi `text.toUpperCase()` hợp lệ mà không phải ép kiểu.

Ta cũng có thể ghi rõ tham số kiểu nếu muốn nhấn mạnh hợp đồng dữ liệu:

```java
static void printUpperExplicit(Box<String> box) {
    if (box instanceof Box<String>(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Hai cách đều biểu diễn ý định lấy một `String` từ `Box<String>`. Cú pháp không ghi `<String>` ở pattern là **suy luận kiểu có ngữ cảnh**, không phải bằng chứng rằng Java bỏ qua an toàn kiểu.

Với record có hai tham số kiểu:

```java
record Pair<K, V>(K key, V value) {}

static void printCount(Pair<String, Integer> pair) {
    if (pair instanceof Pair(var key, var count)) {
        System.out.println(key + ": " + (count + 1));
    }
}
```

Trình biên dịch suy luận `key` là `String` và `count` là `Integer`. Biểu thức `count + 1` sử dụng cơ chế unboxing từ `Integer` sang `int`. Lưu ý: nếu `count` có giá trị `null`, phép unboxing này sẽ gây `NullPointerException`; suy luận kiểu không có nghĩa là giá trị tham chiếu luôn khác `null`.

## 3. Không nhầm kiểm tra record với kiểm tra đối số kiểu ở runtime

Java sử dụng **type erasure** cho generic. Vì vậy, từ một biến `Object`, ta không thể kiểm tra an toàn rằng một đối tượng là `Box<String>` chỉ bằng cách nhìn đối số kiểu của record lúc chạy.

Ví dụ cần tránh:

```java
static void bad(Box raw) {
    // KHÔNG BIÊN DỊCH:
    // Không thể kiểm tra Box<String> theo cách này
    // khi đầu vào là raw Box và cần unchecked conversion.
    if (raw instanceof Box<String>(var text)) {
        System.out.println(text.length());
    }
}
```

Đây là **mã minh họa lỗi có chủ đích, không phải ví dụ chạy được**. Java không cho phép phép kiểm tra record pattern được tham số hóa này khi nó đòi hỏi chuyển kiểu không được kiểm tra từ raw `Box` sang `Box<String>`.

Cũng không nên viết:

```java
Object input = new Box<>("hello");

// Không thể bảo đảm đối số kiểu bằng instanceof kiểu tham số hóa:
// if (input instanceof Box<String> box) { ... } // lỗi biên dịch
```

Trong tình huống đầu vào là `Object`, cách làm an toàn là kiểm tra record, lấy component, rồi kiểm tra **kiểu thật của component** nếu cần sử dụng API đặc thù:

```java
static void inspect(Object input) {
    if (input instanceof Box(var item)) {
        if (item instanceof String text) {
            System.out.println(text.length());
        } else {
            System.out.println("Không phải chuỗi: " + item);
        }
    }
}
```

Ở đây, `Box(var item)` được suy luận từ ngữ cảnh nhưng **không chứng minh** record có đối số kiểu `String` tại runtime. Với đầu vào có kiểu tĩnh `Object`, không được mặc nhiên coi `item` là một `String`. Kiểm tra `item instanceof String text` mới giúp ta dùng các thao tác dành cho `String` trong nhánh đã khớp.

Điểm thực hành quan trọng: **giữ lại kiểu generic tại ranh giới API khi biết kiểu**, ví dụ nhận `Box<String>` thay vì `Object` hoặc raw `Box`. Nếu dữ liệu thực sự không đồng nhất, hãy biểu diễn sự không chắc chắn bằng `Box<?>` hoặc kiểm tra component trước khi dùng.

## 4. Không biết T: dùng Box<?> thay vì Box raw

Khi một hàm cần chấp nhận `Box` có đối số kiểu bất kỳ, hãy viết:

```java
static void processUnknown(Box<?> box) {
    if (box instanceof Box(var item)) {
        System.out.println("Giá trị: " + item);
    }
}
```

`Box<?>` cho phép truyền `Box<String>`, `Box<Integer>` và các kiểu `Box<X>` khác. Nó vẫn thể hiện rõ rằng thông tin `T` chưa biết, nên trình biên dịch không cho phép suy diễn rằng `item` chắc chắn là `String` hay `Integer`.

Chẳng hạn, nếu cần xử lý số nguyên:

```java
static void processInteger(Box<?> box) {
    if (box instanceof Box(var item)
            && item instanceof Integer number) {
        System.out.println(number + 1);
    }
}
```

Việc kiểm tra `Integer` của **component** làm rõ điều kiện. Đừng thay thế bằng ép kiểu mù `(Integer) item` khi không biết chắc dữ liệu đến từ đâu.

Một lưu ý khác: `Box<?>` và `Box<Object>` **không tương đương**. Một `Box<String>` có thể được tham chiếu bằng `Box<?>`, nhưng không thể tự động gán sang `Box<Object>` vì generic của Java bất biến (*invariant*). Vì thế, wildcard thường phù hợp hơn khi yêu cầu là “chấp nhận Box của một kiểu chưa biết”.

## 5. Generic record pattern lồng nhau vẫn có thể suy luận

Giả sử một `Box` chứa một `Box<String>` khác:

```java
static void nested(Box<Box<String>> outer) {
    if (outer instanceof Box(Box(var text))) {
        System.out.println(text.toUpperCase());
    }
}
```

Trong ngữ cảnh `Box<Box<String>>`, Java có thể suy luận pattern ngoài và pattern trong theo chuỗi component, để `text` có kiểu `String`. Không cần đưa raw type vào chỉ vì record được lồng nhiều tầng.

Dù vậy, nếu nhận một `Object` không có thông tin generic đáng tin cậy, không nên giả định mẫu lồng sẽ chứng minh được các đối số kiểu bị xóa ở runtime. Khi không chắc cấu trúc hoặc giá trị component, hãy dùng pattern đủ mức để kiểm tra các kiểu thực tế rồi mới gọi phương thức đặc thù.

Record pattern cũng **không làm giá trị null biến mất**. Bản thân giá trị record `null` không khớp record pattern; component chứa tham chiếu `null` vẫn cần được cân nhắc trước khi gọi phương thức hoặc thực hiện unboxing.

## 6. Chương trình Java 21 chạy hoàn chỉnh

Tạo tệp **`AvoidRawRecordPatternDemo.java`**:

```java
public class AvoidRawRecordPatternDemo {
    record Box<T>(T value) {}
    record Pair<K, V>(K key, V value) {}

    static void printKnown(Box<String> box) {
        if (box instanceof Box(var text)) {
            System.out.println("Known: " + text.toUpperCase());
        }
    }

    static void printAny(Object input) {
        if (input instanceof Box(var item)) {
            if (item instanceof String text) {
                System.out.println("String: " + text);
            } else {
                System.out.println("Other: " + item);
            }
        } else {
            System.out.println("Not a Box");
        }
    }

    static void printWildcard(Box<?> box) {
        if (box instanceof Box(var item)) {
            if (item instanceof Integer number) {
                System.out.println("Integer: " + (number + 1));
            } else {
                System.out.println("Wildcard: " + item);
            }
        }
    }

    static void printPair(Pair<String, Integer> pair) {
        if (pair instanceof Pair(var key, var count)) {
            System.out.println("Pair: " + key + "=" + (count + 1));
        }
    }

    static void printNested(Box<Box<String>> outer) {
        if (outer instanceof Box(Box(var text))) {
            System.out.println("Nested: " + text.length());
        }
    }

    public static void main(String[] args) {
        printKnown(new Box<>("java"));
        printAny(new Box<>("hello"));
        printAny(new Box<>(42));
        printAny("nothing");
        printWildcard(new Box<>(41));
        printPair(new Pair<>("items", 4));
        printNested(new Box<>(new Box<>("abcd")));
    }
}
```

Dùng **JDK 21 trở lên**, biên dịch và chạy bằng:

```bash
javac AvoidRawRecordPatternDemo.java
java AvoidRawRecordPatternDemo
```

Kết quả trên đầu ra chuẩn:

```text
Known: JAVA
String: hello
Other: 42
Not a Box
Integer: 42
Pair: items=5
Nested: 4
```

Ý nghĩa:

- `printKnown` nhận `Box<String>`, nên `Box(var text)` có thể suy luận `text` là `String`.
- `printAny` nhận `Object`. Nó xác nhận đối tượng là `Box`, rồi mới kiểm tra component có phải `String` hay không; `Box<Integer>` đi vào nhánh `Other`.
- `printWildcard` nhận `Box<?>`, kiểm tra component bằng `instanceof Integer` và tăng giá trị số nguyên một đơn vị.
- `printPair` tận dụng thông tin `Pair<String, Integer>` để suy luận hai kiểu component riêng biệt.
- `printNested` tận dụng kiểu `Box<Box<String>>` để suy luận qua hai tầng record và lấy `String` bên trong.

Các phương thức trong chương trình này không dùng raw type và không yêu cầu ép kiểu unchecked. Các nhánh đã minh họa phải được hiểu theo **kiểu tĩnh của tham số tại điểm gọi**.

## 7. Lỗi thường gặp và cách sửa

| Cách viết / suy nghĩ | Vấn đề | Cách phù hợp hơn |
| --- | --- | --- |
| `Box raw = new Box("x");` | Bỏ tham số kiểu của biến; dễ nhận cảnh báo raw/unchecked và mất bảo đảm tĩnh. | `Box<String> box = new Box<>("x");` |
| “`Box(var x)` luôn là raw” | Java 21 có suy luận type argument cho generic record pattern. | Xem kiểu tĩnh của biểu thức đang được khớp. |
| `Box<String> box = raw;` | Gán từ raw type có thể tạo unchecked conversion. | Truyền kiểu parameterized xuyên suốt API và tránh tạo raw type. |
| Từ `Object` suy ra `Box<String>` vì pattern khớp `Box(var x)` | Erasure không bảo đảm đối số generic từ đối tượng runtime. | Kiểm tra `x instanceof String s` khi cần dùng `String`. |
| Dùng `Box<Object>` để nhận mọi `Box<X>` | Generic bất biến; `Box<String>` không là subtype của `Box<Object>`. | Dùng `Box<?>` khi đối số kiểu chưa biết. |
| Gọi `text.length()` khi `text` có thể là `null` | Suy luận kiểu là kiểm tra kiểu tĩnh, không phải kiểm tra null. | Kiểm tra giá trị null theo hợp đồng dữ liệu. |
| Dùng record pattern trong Java 17 mà không có cấu hình preview phù hợp | Record patterns được chính thức hóa ở Java 21. | Biên dịch ví dụ bài này với JDK 21 trở lên. |

## 8. Tự kiểm tra

Cho:

```java
record Result<T>(T data) {}

Result<String> known = new Result<>("ok");
Result<?> unknown = new Result<>(42);
```

- Với `known instanceof Result(var data)`, trình biên dịch có đủ ngữ cảnh để suy luận `data` là `String`.
- Với `unknown instanceof Result(var data)`, đối số kiểu chưa được biết cụ thể. Không thể mặc định `data` có kiểu `Integer` chỉ vì giá trị ví dụ là `42`; hãy kiểm tra component nếu cần xử lý như số nguyên.
- Một phép thử kiểu `Result<String>` trên đầu vào `Object`/raw không thể được coi là cách kiểm tra đối số generic tại runtime; cần tôn trọng các giới hạn của erasure và phép chuyển kiểu có kiểm tra.

**Ghi nhớ:** Để tránh raw record pattern theo đúng tinh thần generic an toàn, hãy ưu tiên **giữ kiểu parameterized ở biến và API**, dùng `Box<?>` khi kiểu phần tử chưa biết, và tận dụng **suy luận đối số kiểu của record pattern trong Java 21** khi có ngữ cảnh. Cú pháp `Box(var value)` không tự chứng minh đối số generic tại runtime, nhưng cũng không mặc định là một thao tác raw thiếu an toàn.
