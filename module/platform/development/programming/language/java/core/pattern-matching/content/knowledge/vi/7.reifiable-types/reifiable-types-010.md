# Đánh đổi giữa type safety và độ tổng quát trong Java Generics và Pattern Matching

**Bối cảnh:** Java Core Pattern Matching — *Generic và reifiable types*. Các ví dụ dùng Java 17+; phần record pattern và pattern `switch` dùng cú pháp ổn định của **Java 21**. Mục tiêu là biết lúc nào nên giữ kiểu chặt tại thời điểm biên dịch, lúc nào chấp nhận dữ liệu tổng quát (`Object`, `List<?>`, generic wildcard), và phải kiểm tra gì tại ranh giới runtime để không tự đánh mất an toàn kiểu.

Một hệ thống nhận dữ liệu nhiều nguồn thường gặp mâu thuẫn thiết kế: API càng **tổng quát** thì càng nhận được nhiều loại đầu vào, nhưng càng khó chứng minh ở compile time rằng thao tác cụ thể trên dữ liệu là an toàn. Ngược lại, API yêu cầu một kiểu quá chặt thì rất dễ dùng sai với các nguồn dữ liệu hợp lệ khác. Java giải quyết bằng hệ thống kiểu tĩnh, generics, wildcard, pattern matching và kiểm tra runtime — **mỗi cơ chế cho một loại bảo đảm khác nhau**.

## 1. Hai mục tiêu cần phân biệt

**Type safety (an toàn kiểu):** trình biên dịch có thể phát hiện việc dùng giá trị như một kiểu không tương thích, hoặc một kiểm tra runtime được thực hiện trước khi chương trình dựa vào kiểu đó. Ví dụ, khi phương thức nhận `List<String>` từ mã Java được kiểm soát và không dùng chuyển đổi unchecked, lời gọi `get` có kiểu tĩnh `String`; bạn không cần ép từng phần tử thủ công.

**Độ tổng quát (generality/flexibility):** cùng một API, biểu thức hoặc thuật toán có thể làm việc với nhiều kiểu giá trị hơn. Ví dụ, `List<?>` có thể tham chiếu `List<String>`, `List<Integer>` và nhiều `List<T>` khác.

Đổi lại, khi chỉ biết `List<?>`, lời gọi `list.get(0)` được xem là một giá trị kiểu `Object` (trong ví dụ không có giới hạn kiểu khác). Trình biên dịch **không cho phép giả định** đó là `String`.

```java
import java.util.List;

class Example {
    static void show(List<?> values) {
        Object first = values.get(0); // Hợp lệ nếu danh sách không rỗng
        // String text = values.get(0); // Lỗi biên dịch: không chứng minh String
    }
}
```

Ghi chú: với danh sách rỗng, `get(0)` ném `IndexOutOfBoundsException`. An toàn kiểu **không** đồng nghĩa mọi phép truy cập đều hợp lệ về chỉ số hay giá trị null.

**Đánh đổi đúng cách** là giữ kiểu cụ thể khi đã biết, mở rộng kiểu tại nơi cần nhận đầu vào đa dạng, và khôi phục bảo đảm bằng kiểm tra có căn cứ trước khi xử lý chuyên biệt.

## 2. Nền tảng của giới hạn: type erasure và reifiable types

### 2.1. Type erasure — `List<String>` không mang đầy đủ `String` tại runtime

Java generics chủ yếu được kiểm tra ở **compile time**. Theo JLS `4.6, *type erasure* xóa phần lớn đối số kiểu khi chuyển tới dạng thực thi:

- `List<String>` và `List<Integer>` có cùng erasure là `List`.
- Một biến kiểu `T` được ánh xạ đến erasure của bound của nó (thường là `Object` nếu không có bound cụ thể).
- Vì vậy, chỉ kiểm tra một đối tượng có phải `List` ở runtime **không thể xác nhận** mọi phần tử bên trong là `String`.

```java
Object value = java.util.List.of("Java", "Generics");

if (value instanceof java.util.List<?> list) {
    System.out.println(list.size()); // 2
    // Vẫn không biết phần tử có thật sự đều là String hay không.
}
```

`instanceof List<?>` kiểm tra đối tượng là một danh sách, không kiểm tra loại phần tử. Đó là lý do một phép khớp thành công với `List<?>` chỉ mang lại **một phần bảo đảm**.

### 2.2. Reifiable types — kiểu có thể nhận diện đầy đủ ở runtime

JLS `4.7 gọi một kiểu là *reifiable* nếu thông tin kiểu cần thiết của nó sẵn có ở runtime. Những trường hợp liên quan trực tiếp đến bài:

| Kiểu | Reifiable? | Ý nghĩa cho kiểm tra |
| --- | --- | --- |
| `String`, `Number`, `Runnable` | Có | Có thể kiểm tra kiểu lớp/interface trực tiếp. |
| `List<?>` | Có | Biết đó là `List`, không biết kiểu cụ thể của phần tử. |
| `List<String>`, `List<Integer>` | Không | Tham số kiểu cụ thể bị xóa khỏi kiểm tra runtime thông thường. |
| `List` (raw type) | Có | Có thể kiểm tra là List, nhưng bỏ bảo đảm generic của mã nguồn. |
| `String[]` | Có | Mảng có kiểm tra kiểu phần tử runtime. |
| `List<String>[]` | Không | Không thể tạo mảng trực tiếp bằng `new List<String>[n]`. |

Một kiểu reifiable **không có nghĩa** rằng mọi thuộc tính nghiệp vụ bên trong đối tượng đều đã được xác nhận. `List<?>` là reifiable, nhưng phần tử có thể là nhiều kiểu khác nhau.

### 2.3. Vì sao Java chọn erasure?

Erasure hỗ trợ tương thích với mã Java và thư viện đã tồn tại trước generics. Cái giá là runtime không mang đầy đủ `T` để tự động kiểm chứng những phép gán kiểu tham số hóa tùy ý. Vì thế, Java không có phép `obj instanceof List<String>` đáng tin như một công cụ xác thực mọi phần tử của danh sách khi đầu vào có kiểu tổng quát `Object`.

## 3. Generics cho phép khái quát mà vẫn giữ an toàn kiểu tĩnh

### 3.1. `List<T>`: tổng quát theo một kiểu cụ thể do người gọi chọn

```java
static <T> T first(java.util.List<T> values) {
    return values.get(0);
}
```

Khi gọi `String name = first(List.of("An", "Bình"));`, compiler suy luận `T` là `String`. Khi gọi với `List<Integer>`, compiler suy luận kiểu tương ứng.

Lợi ích: một thuật toán áp dụng cho nhiều kiểu **nhưng mối quan hệ kiểu giữa tham số và kết quả được giữ**. Đây là kiểu tổng quát có kiểm soát, thường tốt hơn nhận và trả `Object`.

Giới hạn: `<T>` không tự tạo một token chứa thông tin runtime của `T`. Nếu phương thức nhận dữ liệu từ JSON, reflection, raw collection hoặc một `Object` chưa biết nguồn, compiler không thể bảo đảm đầu vào thực sự tuân thủ hợp đồng `T` chỉ bằng tên tham số generic.

### 3.2. `List<?>`: chấp nhận mọi `List<T>` nhưng dùng phần tử theo kiểu an toàn

```java
static int sizeOfAnyList(java.util.List<?> values) {
    return values.size();
}
```

`sizeOfAnyList(List.of("A"))` và `sizeOfAnyList(List.of(1, 2))` đều hợp lệ. Nếu thuật toán chỉ cần độ dài, `List<?>` là hợp đồng tốt: không buộc người gọi chuyển đổi kiểu hoặc sao chép dữ liệu.

Nhược điểm có chủ đích: không thể thêm một giá trị khác `null` với kiểu tùy ý vào `List<?>`, vì compiler không biết kiểu phần tử mà danh sách cho phép. Có thể đọc phần tử dưới dạng `Object`; cần kiểm tra tiếp nếu muốn gọi API riêng của `String` hay `Number`.

**Mẫu dùng:** chỉ đọc metadata, đếm, duyệt, in ra `Object.toString()` hoặc thực hiện các thao tác không đòi hỏi một kiểu phần tử cụ thể.

### 3.3. Wildcard có bound: tăng tính tái sử dụng với bảo đảm cần thiết

```java
static double sum(java.util.List<? extends Number> values) {
    double result = 0.0;
    for (Number number : values) {
        result += number.doubleValue();
    }
    return result;
}
```

`sum(List.of(1, 2))` và `sum(List.of(2.5, 3.5))` đều biên dịch. Việc dùng `? extends Number` cho phép **đọc** mọi phần tử dưới dạng `Number`.

```java
static void addOne(java.util.List<? super Integer> values) {
    values.add(1);
    Object first = values.get(0);
}
```

`? super Integer` cho phép **ghi** `Integer` vào danh sách thích hợp; khi đọc theo kiểu tổng quát, chỉ chắc chắn có `Object`. Đây là nguyên tắc *PECS* (*Producer Extends, Consumer Super*), nhưng áp dụng dựa trên hành vi API thực tế, không áp dụng máy móc.

**Generic invariance:** `List<Integer>` không phải subtype của `List<Number>`, dù `Integer` là subtype của `Number`. Nếu muốn nhận danh sách mọi loại `Number` để chỉ đọc, dùng `List<? extends Number>`; không ép `List<Integer>` thành `List<Number>`.

## 4. Pattern matching giúp xử lý đầu vào tổng quát đến mức nào?

### 4.1. Từ `Object` sang `List<?>`: kiểm tra “hình dạng bên ngoài”

```java
static String describe(Object input) {
    if (input instanceof java.util.List<?> list) {
        return "List size=" + list.size();
    }
    return "not-list";
}
```

Khi pattern khớp, compiler biết biến `list` có kiểu `List<?>`. Bạn có thể gọi `size()`, `isEmpty()`, lặp qua các phần tử kiểu `Object`. Nhưng `input instanceof List<?> list` **không chứng minh** danh sách chỉ chứa `String`.

Ví dụ dưới đây **không biên dịch** với `Object` là kiểu tĩnh của nguồn:

```java
// KHÔNG BIÊN DỊCH:
static void invalid(Object input) {
    // if (input instanceof java.util.List<String> strings) {
    //     System.out.println(strings.get(0).length());
    // }
}
```

Lý do không phải “Java cấm mọi dấu ngoặc nhọn `<...>` trong pattern”. Lý do chính xác là phép kiểm tra kiểu đòi hỏi chuyển kiểu an toàn theo điều kiện áp dụng của JLS, trong khi một `Object` tùy ý không thể được xác thực thành `List<String>` chỉ qua erasure.

### 4.2. Ngoại lệ quan trọng từ Java 16: kiểu tĩnh đủ chặt có thể cho phép kiểu tham số hóa

Không nên học thuộc mệnh đề tuyệt đối “`instanceof` luôn yêu cầu reifiable type”. Từ Java 16, JLS `15.20.2 đã nới giới hạn so với các phiên bản trước: việc kiểm tra kiểu `instanceof` có thể dùng một kiểu tham số hóa **không reifiable** khi có thể thực hiện *checked cast* theo kiểu tĩnh đã biết.

```java
import java.util.ArrayList;
import java.util.List;

class RefinementExample {
    static void check(List<Integer> numbers) {
        if (numbers instanceof ArrayList<Integer> array) {
            System.out.println(array.size());
        }
    }
}
```

Đoạn Java 17+ này **hợp lệ**. Thông tin `Integer` đã có trong **kiểu tĩnh** của `numbers`; `instanceof` ở đây phân biệt `ArrayList` với những hiện thực `List` khác, không xác minh lại từng phần tử là `Integer` tại runtime.

Không suy diễn rằng `Object input` có thể được kiểm tra bằng `input instanceof ArrayList<Integer>` theo cách tương tự. Nếu nguồn mất thông tin generic, một phép kiểm tra lớp container không thể khôi phục bằng chứng về kiểu phần tử.

### 4.3. `switch` có type pattern: phân loại kiểu runtime, không kiểm tra kiểu phần tử bị xóa

```java
static String category(Object input) {
    return switch (input) {
        case null -> "null";
        case java.util.List<?> list -> "list of size " + list.size();
        case String text -> "string " + text;
        default -> "other";
    };
}
```

Đây là `switch` expression Java 21, lựa chọn một nhánh dựa trên cấu trúc runtime mà Java kiểm tra được. Nhánh `List<?>` có thể xử lý mọi danh sách; nó không thể phân biệt `List<String>` với `List<Integer>` chỉ bằng pattern.

Nếu cần xử lý theo **kiểu phần tử**, thực hiện bước xác thực **bên trong** nhánh `List<?>` hoặc thiết kế mô hình dữ liệu thành các kiểu mang ý nghĩa riêng thay vì chỉ dựa vào generic parameter.

## 5. Lựa chọn thực tế: giữ kiểu rộng rồi kiểm tra tại ranh giới

Giả sử một API nhận `Object` từ plug-in bên ngoài. Mục tiêu là tạo một `List<String>` dùng nội bộ an toàn. Không thể xác nhận bằng `input instanceof List<String>`; cũng không nên thực hiện unchecked cast rồi tự tin gọi `String.length()`.

**Cách đúng:** kiểm tra container bằng `List<?>`, kiểm tra **từng phần tử**, rồi tạo danh sách mới được gán kiểu mạnh:

```java
static java.util.List<String> validateStrings(Object input) {
    if (!(input instanceof java.util.List<?> source)) {
        throw new IllegalArgumentException("Expected a list");
    }

    java.util.List<String> result = new java.util.ArrayList<>();
    for (Object element : source) {
        if (!(element instanceof String text)) {
            throw new IllegalArgumentException("Expected strings only");
        }
        result.add(text);
    }
    return java.util.List.copyOf(result);
}
```

**Điều thực sự được bảo đảm:**

- Nếu phương thức trả về bình thường, mọi phần tử đã qua kiểm tra `String`.
- Khi gặp phần tử `null`, `instanceof String` trả về `false` nên phương thức từ chối. Đây là chính sách chủ ý; nếu null hợp lệ thì phải đưa ra quy tắc và biểu diễn đầu ra khác.
- Kết quả là một danh sách **không sửa đổi được qua API `List`** nhờ `List.copyOf`. Danh sách đầu vào có thể bị thay đổi về sau mà không làm thay đổi cấu trúc danh sách kết quả.
- Chỉ kiểm tra đúng một lớp phần tử; nếu phần tử là đối tượng mutable, `List.copyOf` **không làm deep copy**.

Chi phí: phải duyệt **O(n)** phần tử và có thể phân bổ thêm bộ nhớ **O(n)**. Đổi lại, đường biên dữ liệu được xác minh một lần để phần còn lại của ứng dụng dùng `List<String>` đúng nghĩa.

Đây là mẫu rất hữu ích khi nhận đầu vào từ dữ liệu parse, reflection, raw collection, Java interop hoặc API không kiểm soát được.

## 6. Tránh raw type và unchecked cast nếu chưa có chứng cứ

### 6.1. Raw type: tổng quát bề ngoài nhưng mất hợp đồng compile time

```java
// Ví dụ minh họa code legacy; không nên áp dụng trong API mới:
java.util.List raw = new java.util.ArrayList();
raw.add("Java");
raw.add(42);
```

`List` (raw) cho phép thao tác cũ nhưng bỏ kiểm tra tham số generic. Nó vẫn là một kiểu reifiable theo JLS `4.7; điều này **không biến nó thành type-safe**.

So với `List<?>`:

- `List<?>` thừa nhận chưa biết kiểu phần tử và ngăn bổ sung tùy tiện.
- `List` raw cho phép thêm phần tử không theo một hợp đồng generic rõ ràng, dễ tạo warning và *heap pollution*.

Nếu chỉ cần quan sát dữ liệu tổng quát, ưu tiên **`List<?>`**. Chỉ dùng raw type ở ranh giới legacy thật sự cần thiết và khoanh vùng chỗ chuyển đổi.

### 6.2. Unchecked cast: warning mang ý nghĩa cụ thể

```java
// Ví dụ MẤT AN TOÀN KIỂU; không chạy như một giải pháp xác thực:
Object input = java.util.List.of(1, 2, 3);
@SuppressWarnings("unchecked")
java.util.List<String> strings = (java.util.List<String>) input;

// Cast của container có thể vượt qua runtime check...
String first = strings.get(0); // ClassCastException khi đọc Integer như String
```

Đầu tiên runtime chỉ kiểm tra giá trị là một `List`. Generic parameter `String` không được kiểm chứng, nên việc truy xuất với kiểu tĩnh `String` có thể kích hoạt cast do compiler thêm vào và gây `ClassCastException` **muộn**.

`@SuppressWarnings("unchecked")` chỉ tắt thông báo từ compiler; nó **không** thêm kiểm tra runtime và không khiến phép cast an toàn hơn. Nếu bắt buộc dùng unchecked cast do thiết kế thư viện, hãy đặt trong phương thức nhỏ có hợp đồng, kiểm tra bất biến tại đầu vào hoặc dùng cơ chế tạo dữ liệu bảo đảm kiểu; lý giải tính an toàn ở đúng vị trí đó.

### 6.3. Kiểm tra “có vẻ đúng” nhưng không đủ

```java
// Không chứng minh được toàn bộ danh sách chứa String:
if (input instanceof java.util.List<?> list
        && !list.isEmpty()
        && list.get(0) instanceof String) {
    // Các phần tử còn lại vẫn có thể là Integer, null, v.v.
}
```

Chỉ kiểm tra phần tử đầu không xác minh toàn bộ collection. Nếu yêu cầu “mọi phần tử là String”, phải duyệt tất cả phần tử hoặc nhận dữ liệu từ một API đã có hợp đồng đáng tin cậy về điều đó.

## 7. Class token: tăng tính tổng quát của bước xác thực runtime

Khi cùng một bộ kiểm tra cần trả về nhiều kiểu phần tử, có thể đưa vào **`Class<T>` token**:

```java
static <T> java.util.List<T> checkedList(
        Object input, Class<T> elementType) {
    java.util.Objects.requireNonNull(elementType);

    if (!(input instanceof java.util.List<?> source)) {
        throw new IllegalArgumentException("not-a-list");
    }

    java.util.List<T> result = new java.util.ArrayList<>();
    for (Object element : source) {
        if (!elementType.isInstance(element)) {
            throw new IllegalArgumentException("invalid-element");
        }
        result.add(elementType.cast(element));
    }
    return java.util.List.copyOf(result);
}
```

Ví dụ:

```java
java.util.List<String> names =
        checkedList(java.util.List.of("A", "B"), String.class);
java.util.List<Integer> counts =
        checkedList(java.util.List.of(1, 2), Integer.class);
```

`Class.isInstance` kiểm tra kiểu runtime của từng phần tử; `Class.cast` tạo giá trị kiểu `T` tương ứng. Với ví dụ này, `null` bị loại vì `isInstance(null)` là `false`. Phương thức tổng quát mà vẫn giữ được kết quả `List<T>` **vì caller đã cung cấp bằng chứng runtime cho chính loại phần tử**.

Giới hạn của token: Java có `String.class` và `Integer.class`, nhưng **không có** `List<String>.class`. Một `Class<List>` chỉ nhận diện loại container ở runtime, không mô tả đầy đủ cấu trúc generic lồng nhau. Nếu dữ liệu có cấu trúc `Map<String, List<User>>`, cần kiểm tra đệ quy, schema rõ ràng, hoặc một thư viện parser có cơ chế biểu diễn generic type phù hợp; không thể xác thực tất cả chỉ bằng `Class<T>` đơn giản.

## 8. Generic record pattern: thêm khả năng mô tả cấu trúc, vẫn không loại bỏ erasure

Trong Java 21, record patterns giúp kiểm tra kiểu record và phân rã các component. Với record generic:

```java
record Box<T>(T value) {}
```

Có thể kiểm tra component theo kiểu runtime:

```java
static String describeBox(Object input) {
    return switch (input) {
        case null -> "null";
        case Box(String value) -> "Box item: " + value;
        case Box(var value) -> "Box other: " + value;
        default -> "other";
    };
}
```

Lưu ý rất kỹ:

- `Box(String value)` kiểm tra đối tượng là một `Box` phù hợp **và component thực tế có thể khớp `String value`**. Nó không kiểm tra tổng quát rằng mọi `Box<T>` đều có tham số kiểu khai báo là `String`.
- `Box(var value)` là record pattern suy luận kiểu của component theo ngữ cảnh; khi selector có kiểu tĩnh `Object`, không được tự giả định `value` là `String`. Trên ví dụ này, nó có thể nhận `Integer` hoặc `null`.
- Nếu input đã được khai báo `Box<String>` từ mã type-safe, compiler có thể tận dụng thông tin kiểu tĩnh để suy luận chi tiết hơn; đó là bảo đảm từ **nguồn tĩnh**, không phải generic parameter bỗng được reify ở runtime.
- Record pattern với tham số kiểu và suy luận chịu các quy tắc applicability/inference (`14.30, `18.5.5). Đừng kết luận mọi pattern như `Box<String>(...)` đều hợp lệ chỉ vì tên record là generic. Nếu đầu vào là raw hoặc `Object`, cần xét khả năng checked cast và từng component.

Đánh đổi ở đây là thêm cấu trúc diễn đạt để trích xuất dữ liệu, trong khi vẫn tôn trọng giới hạn mà erasure áp đặt lên kiểm tra kiểu tham số hóa.

## 9. Chương trình Java 21 hoàn chỉnh: kiểm tra container, phần tử và record

Tạo tệp **`GenericSafetyDemo.java`** với nội dung:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class GenericSafetyDemo {
    record Box<T>(T value) {}

    static <T> List<T> checkedList(Object input, Class<T> elementType) {
        Objects.requireNonNull(elementType);
        if (!(input instanceof List<?> source)) {
            throw new IllegalArgumentException("not-a-list");
        }

        List<T> result = new ArrayList<>();
        for (Object element : source) {
            if (!elementType.isInstance(element)) {
                throw new IllegalArgumentException("invalid-element");
            }
            result.add(elementType.cast(element));
        }
        return List.copyOf(result);
    }

    static String inspect(Object input) {
        if (input instanceof List<?> list) {
            return "List size=" + list.size();
        }
        return "not-list";
    }

    static String boxValue(Object input) {
        return switch (input) {
            case null -> "null";
            case Box(String value) -> "Box item: " + value;
            case Box(var value) -> "Box other: " + value;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object one = List.of("A", "B");
        Object two = List.of("A", 3);
        Object three = List.of(1, 2);

        System.out.println(inspect(one));
        System.out.println(checkedList(one, String.class));

        try {
            System.out.println(checkedList(two, String.class));
        } catch (IllegalArgumentException e) {
            System.out.println(e.getMessage());
        }

        System.out.println(checkedList(three, Integer.class));
        System.out.println(boxValue(new Box<>("Hi")));
        System.out.println(boxValue(new Box<>(10)));
        System.out.println(boxValue(new Box<>(null)));
        System.out.println(boxValue(null));
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 GenericSafetyDemo.java
java GenericSafetyDemo
```

Kết quả:

```text
List size=2
[A, B]
invalid-element
[1, 2]
Box item: Hi
Box other: 10
Box other: null
null
```

Diễn giải:

1. `inspect(one)` chỉ chứng minh `one` là một `List<?>`, nên chỉ in số phần tử 2.
2. `checkedList(one, String.class)` kiểm tra từng phần tử là `String`, tạo `List<String>` kết quả và in `[A, B]`.
3. `checkedList(two, String.class)` gặp phần tử `3` là `Integer`, thất bại đúng tại điểm kiểm tra và ném `IllegalArgumentException("invalid-element")`; không cần chờ lỗi cast xảy ra muộn.
4. `checkedList(three, Integer.class)` chấp nhận toàn bộ danh sách số nguyên và trả `[1, 2]`.
5. `Box<>("Hi")` khớp record pattern với component `String`; `Box<>(10)` đi vào nhánh record tổng quát; `Box<>(null)` vẫn là đối tượng record khác null, nhánh `var value` nhận null.
6. Cuối cùng, **selector null** được xử lý bằng `case null`. Nó khác với trường hợp record không null nhưng component null ở dòng trước.

Mẫu này đạt hai mục tiêu: **đầu vào đủ rộng** để nhận dữ liệu từ nhiều nguồn, còn **đầu ra có bảo đảm kiểu rõ ràng** sau khi vượt qua ranh giới kiểm tra.

## 10. So sánh các lựa chọn kiến trúc

| Lựa chọn | Linh hoạt ở đầu vào | Bảo đảm kiểu | Chi phí/rủi ro | Khi nên dùng |
| --- | --- | --- | --- | --- |
| `List<String>` | Chỉ danh sách String theo hợp đồng generic | Rất tốt ở compile time nếu nguồn đáng tin và không có unchecked conversion | Không chấp nhận `List<Integer>` | API đã biết rõ dữ liệu |
| `List<T>` | Dùng lại thuật toán cho nhiều `T` | Giữ quan hệ kiểu giữa input/output tại compile time | Runtime không tự biết `T` | Generic algorithms |
| `List<?>` | Nhận mọi `List<T>` | Chắc container là List, phần tử đọc dưới dạng Object | Không thao tác chuyên biệt lên phần tử chưa kiểm tra | Đọc, duyệt, kiểm tra kích thước |
| `List<? extends Number>` | Nhận nhiều dạng danh sách Number | Phần tử đọc an toàn dưới dạng Number | Giới hạn thao tác ghi | Tính tổng, thống kê |
| `Object` + `instanceof List<?>` | Nhận mọi đối tượng | Phải kiểm tra đúng loại container trước | Runtime branch, chưa biết phần tử | Boundary của dữ liệu không đồng nhất |
| `Object` + kiểm tra từng phần tử + typed copy | Rất rộng nhưng đầu ra chặt | Có thể chứng minh phần tử đúng loại đã kiểm tra | Duyệt O(n), sao chép, từ chối dữ liệu sai | Parse, import, plug-in |
| Raw `List` / unchecked cast | Dễ vượt hàng rào compiler | Không có chứng cứ đầy đủ cho kiểu phần tử | Heap pollution, lỗi trễ, warning | Tương thích legacy có kiểm soát |

**Không có lựa chọn luôn tốt nhất.** Với nội bộ ứng dụng đã có mô hình dữ liệu chặt, bắt đầu bằng `List<T>` hoặc kiểu nghiệp vụ riêng thường dễ bảo trì hơn. Khi nhận dữ liệu thiếu schema, bắt đầu bằng `Object`/`List<?>` rồi xác thực và trả về kiểu chặt. Bảo vệ được ranh giới quan trọng hơn việc thêm thật nhiều phép cast.

## 11. Các lỗi thiết kế và lỗi Java cần tránh

1. **Tin rằng `List<?>` bảo đảm mọi phần tử có cùng một kiểu.** Nó chỉ diễn đạt chưa biết kiểu phần tử; kiểm tra một phần tử không xác thực toàn bộ danh sách.
2. **Nhầm reifiable với type-safe.** Raw `List` là reifiable nhưng thao tác với raw type có thể tạo heap pollution.
3. **Nói `instanceof` cấm mọi parameterized type.** Java 16+ cho phép một số phép kiểm tra checked-cast compatible với kiểu tĩnh đủ hẹp; hãy đọc `15.20.2`.
4. **Nói pattern matching tự khôi phục tham số generic bị xóa.** `List<?>` pattern không phục hồi được `T`; record pattern mô tả thêm component nhưng không tái tạo mọi generic argument runtime.
5. **Ép `List<Object>` hoặc `List<Number>` từ `List<Integer>`.** Generics invariant; hãy dùng bounded wildcard hoặc copy/convert phù hợp.
6. **Ẩn warning bằng `@SuppressWarnings("unchecked")` mà không kiểm soát nguồn.** Điều này che cảnh báo, không bổ sung runtime check.
7. **Dùng `Class<T>` với kiểu nested phức tạp như `List<String>`.** `List<String>.class` không tồn tại; cần kiểm tra cấu trúc sâu hơn bằng schema, validator hoặc Type token phù hợp của thư viện.
8. **Không định nghĩa chính sách null.** `isInstance(null)` trả false; `List.copyOf` cũng không chấp nhận phần tử null. Nêu rõ sẽ từ chối hay biểu diễn null.
9. **Cho rằng tạo bản sao là deep copy.** `List.copyOf` ngăn sửa danh sách qua API trả về nhưng không tự clone các phần tử mutable.
10. **Tạo bộ phân loại dài bằng `instanceof` cho một tập subtype cố định.** Nếu mô hình do mình kiểm soát và hữu hạn, xem xét một `sealed interface` cùng các type/record pattern phù hợp, hoặc đa hình qua method của chính kiểu đó. Giữ các nhánh runtime ở biên hệ thống khi hợp đồng ban đầu thật sự tổng quát.

## 12. Bài tập kiểm tra hiểu đúng đánh đổi

**Bài tập 1 — kiểm tra mức bảo đảm.** Với `Object x = List.of(1, "A");`, biểu thức `x instanceof List<?> list` có khớp không? Có thể nhận `list` như `List<String>` ngay không?

**Đáp án:** Có khớp vì đó là danh sách. Không thể coi toàn bộ danh sách là `List<String>` an toàn: phần tử đầu là `Integer` và runtime check chưa xác minh tham số generic.

**Bài tập 2 — chọn chữ ký.** Viết một phương thức chỉ tính tổng của mọi danh sách `Integer` hoặc `Double`. Nên nhận `List<Number>`, `List<?>` hay `List<? extends Number>`?

**Đáp án:** `List<? extends Number>` diễn đạt đúng ý định chỉ đọc phần tử Number và cho phép hai kiểu danh sách đó, trong khi `List<Number>` không chấp nhận trực tiếp `List<Integer>` vì bất biến generics.

**Bài tập 3 — type erasure.** Vì sao `Object x = new ArrayList<String>(); if (x instanceof ArrayList<String> a) ...` không được dùng để xác thực kiểu phần tử? Trong trường hợp nào cú pháp tương tự có thể hợp lệ?

**Đáp án:** Kiểu tĩnh `Object` không mang thông tin tham số `String` để kiểm tra checked cast. Nếu đầu vào có kiểu tĩnh `List<String>`, phép tinh chỉnh `instanceof ArrayList<String>` là hợp lệ từ Java 16 trong ngữ cảnh tương thích; nó kiểm tra lớp hiện thực, không kiểm tra lại mọi phần tử.

**Bài tập 4 — biên dữ liệu.** Một plug-in trả `Object` nhưng API nội bộ phải trả `List<Long>` và từ chối `null`. Viết `checkedList(input, Long.class)` theo mẫu ở trên; kiểm tra ba đầu vào `List.of(1L, 2L)`, `List.of(1L, "2")` và `List.of("2")`.

**Đáp án:** Đầu vào thứ nhất thành công. Hai đầu vào còn lại thất bại ở phần tử String (không tự chuyển `"2"` thành `Long`). Nếu muốn parse chuỗi thành số, đó là **quy tắc chuyển đổi dữ liệu bổ sung**, không phải type check.

**Bài tập 5 — record pattern.** Cho `record Box<T>(T value) {}` và `Object x = new Box<>(5);`. Nhánh `case Box(String s)` có được chọn không? Nhánh `case Box(var item)` thì sao?

**Đáp án:** Nhánh String không khớp component `Integer`. Nhánh `var item` có thể khớp và `item` nhận giá trị `5`; đừng suy luận tham số generic `T` đã được kiểm tra đầy đủ tại runtime.

## Tài liệu đối chiếu chính thức

- [JLS Java SE 21 `4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.5): generic types, tham số kiểu và wildcard.
- [JLS Java SE 21 `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6): ánh xạ erasure và giới hạn thông tin ở runtime.
- [JLS Java SE 21 `4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7): định nghĩa chính xác các kiểu reifiable.
- [JLS Java SE 21 `4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.8): tương thích mã legacy và nguy cơ mất kiểm tra generic.
- [JLS Java SE 21 `5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.5): checked/unchecked cast.
- [JLS Java SE 21 `15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): type comparison và pattern matching, bao gồm ngoại lệ với non-reifiable parameterized types từ Java 16.
- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type pattern, record pattern và điều kiện khả dụng.
- [JLS Java SE 21 `18.5.5 — Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5): suy luận tham số kiểu của record pattern.
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): ví dụ chính thức về pattern trên record generic.
