# `Class.isInstance()` khác `instanceof` với kiểu biết trước

Trong Java, cả `instanceof` và `Class.isInstance(Object)` đều có thể trả lời câu hỏi: **đối tượng tại thời điểm chạy có tương thích với một kiểu tham chiếu hay không?** Điểm khác biệt quyết định là **kiểu cần kiểm tra được biểu diễn ở đâu**:

- `value instanceof SomeType`: `SomeType` được viết trực tiếp trong mã nguồn và được trình biên dịch biết khi biên dịch.
- `someClass.isInstance(value)`: `someClass` là một đối tượng `Class<?>` (hoặc `Class<T>`), vì vậy kiểu đích có thể được chọn, truyền vào hoặc nạp **trong lúc chương trình chạy**.

Đây là một khác biệt về cách biểu diễn kiểu và cách viết chương trình; khi cùng kiểm tra một kiểu tham chiếu cụ thể, hai cách tuân theo cùng quan hệ tương thích kiểu lúc chạy.

## 1. Kiểm tra kiểu biết trước bằng `instanceof`

Khi kiểu đích đã rõ trong mã, `instanceof` thường dễ đọc nhất:

```java
Object value = "Java";

boolean textLike = value instanceof CharSequence; // true
boolean numeric = value instanceof Number;        // false
```

`instanceof` kiểm tra kiểu thực tế của đối tượng, bao gồm quan hệ kế thừa và triển khai interface. Vì `String` triển khai `CharSequence`, phép kiểm tra đầu trả về `true`.

Trong Java 17, có thể dùng **pattern matching for `instanceof`** để vừa kiểm tra vừa có một biến đã được thu hẹp kiểu:

```java
Object input = "reflection";

if (input instanceof String text) {
    System.out.println(text.toUpperCase()); // REFLECTION
}
```

Biến `text` chỉ được sử dụng tại những vị trí mà trình biên dịch biết phép kiểm tra đã thành công (phạm vi phụ thuộc luồng điều khiển). Cách này tránh ép kiểu thủ công khi kiểu đích đã có sẵn trong mã nguồn.

Không thể thay tên kiểu ở vế phải `instanceof` bằng một biến chứa `Class<?>`:

```java
Class<?> expectedType = String.class;

// KHÔNG biên dịch: expectedType là một biến, không phải tên kiểu.
// boolean matched = input instanceof expectedType;
```

## 2. Kiểm tra kiểu được chọn lúc chạy bằng `Class.isInstance()`

Chữ ký API là:

```java
public native boolean isInstance(Object obj);
```

Phương thức được gọi trên **đối tượng `Class` đại diện cho kiểu đích**, còn đối số là đối tượng cần kiểm tra:

```java
Object value = "Java";
Class<?> expectedType = CharSequence.class;

boolean matched = expectedType.isInstance(value); // true
```

`expectedType` có thể đến từ tham số phương thức, một registry hoặc `Class.forName(...)`. Nhờ đó, không phải viết một chuỗi `if`/`else` chỉ để lựa chọn giữa các kiểu đã có tên trong cấu hình.

Ví dụ kiểu đích chỉ được xác định lúc chạy:

```java
String configuredTypeName = "java.lang.CharSequence";
Class<?> expectedType = Class.forName(configuredTypeName);
Object candidate = "Java";

System.out.println(expectedType.isInstance(candidate)); // true
```

`Class.forName(String)` có thể ném `ClassNotFoundException` và mặc định có thể kích hoạt khởi tạo lớp. Đoạn trên là **mã minh họa đặt trong ngữ cảnh có xử lý hoặc khai báo ngoại lệ**; chương trình chạy đầy đủ ở phần tiếp theo khai báo `throws ClassNotFoundException`.

Không nên xem tên kiểu lấy từ đầu vào không tin cậy là một cơ chế cấp quyền. Khi cần cho phép người dùng chọn kiểu, hãy giới hạn danh sách kiểu hợp lệ và kiểm tra quyền/trường hợp sử dụng ở tầng ứng dụng.

## 3. Đối chiếu trực tiếp

| Tiêu chí | `instanceof` | `Class.isInstance()` |
| --- | --- | --- |
| Ví dụ | `obj instanceof Number` | `Number.class.isInstance(obj)` |
| Cách chỉ ra kiểu đích | Tên kiểu hoặc mẫu kiểu được viết trong mã | Giá trị `Class<?>`/`Class<T>` |
| Chọn kiểu đích khi chạy | Không thể dùng biến `Class<?>` thay tên kiểu | Có thể, qua tham số, registry, `Class.forName`… |
| Kiểm tra quan hệ kế thừa/interface | Có | Có |
| Đối tượng `null` | `false` | `false` |
| Thu hẹp kiểu trong Java 17 | Có thể khai báo biến pattern (`instanceof T t`) | Không tự sinh biến pattern hoặc tự thu hẹp kiểu |
| Tình huống nên dùng | Kiểu đã biết, nhánh xử lý nghiệp vụ thông thường | Framework, reflection, bộ kiểm tra nhận `Class` từ cấu hình hoặc API |

Với một kiểu tham chiếu cụ thể `T` có thể dùng trực tiếp, ta có tính tương đương thực tế:

```java
boolean a = value instanceof Number;
boolean b = Number.class.isInstance(value);
// a và b cho cùng kết quả đối với cùng value.
```

Điều này **không** có nghĩa mọi biểu thức liên quan đến generic, kiểu nguyên thủy hoặc kiểu được chọn động đều có thể đổi cú pháp một cách máy móc.

## 4. Chương trình Java 17+ chạy được

Lưu toàn bộ mã sau trong tệp `TypeChecksDemo.java`:

```java
import java.util.List;

public class TypeChecksDemo {
    public static void main(String[] args) throws ClassNotFoundException {
        Object text = "Java";

        System.out.println(text instanceof CharSequence);
        System.out.println(CharSequence.class.isInstance(text));

        Class<?> selectedType = Class.forName("java.lang.CharSequence");
        System.out.println(selectedType.isInstance(text));
        System.out.println(Integer.class.isInstance(text));

        Object number = Integer.valueOf(42);

        if (number instanceof Number n) {
            System.out.println(n.intValue());
        }

        Class<? extends Number> numberType = Number.class;
        if (numberType.isInstance(number)) {
            Number n = numberType.cast(number);
            System.out.println(n.intValue());
        }

        System.out.println(String.class.isInstance(null));
        System.out.println(int.class.isInstance(number));
        System.out.println(Integer.class.isInstance(number));

        Object words = List.of("a", "b");
        System.out.println(List.class.isInstance(words));
        System.out.println(Object[].class.isInstance(new String[] {"x"}));
        System.out.println(Object[].class.isInstance(new int[] {1}));

        String checked = requireType(String.class, text);
        System.out.println(checked.length());
    }

    private static <T> T requireType(Class<T> expectedType, Object value) {
        if (!expectedType.isInstance(value)) {
            throw new IllegalArgumentException(
                    "Expected " + expectedType.getTypeName());
        }
        return expectedType.cast(value);
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac --release 17 TypeChecksDemo.java
java TypeChecksDemo
```

Kết quả chuẩn (`stdout`):

```text
true
true
true
false
42
42
false
false
true
true
true
false
4
```

Giải thích các nhóm kết quả:

1. Chuỗi `"Java"` vừa là `CharSequence` qua `instanceof`, vừa thỏa `CharSequence.class.isInstance(...)` và kiểu được nạp bằng `Class.forName`. Nó không phải `Integer`.
2. Hai nhánh xử lý đối tượng `Integer(42)` đều lấy được giá trị `42`: nhánh thứ nhất dùng biến pattern `Number n`, nhánh thứ hai dùng token `Class<? extends Number>` và `cast`.
3. `null` không là instance của `String`. `int.class` đại diện cho kiểu nguyên thủy `int`, còn `number` là đối tượng `Integer`, nên kiểm tra với `int.class` là `false` và với `Integer.class` là `true`.
4. `List.class` nhận diện đối tượng danh sách; mảng `String[]` là `Object[]`, còn mảng nguyên thủy `int[]` không phải `Object[]`.
5. `requireType(String.class, text)` xác nhận kiểu, ép kiểu có kiểm tra và trả về `String`. `"Java".length()` bằng `4`.

## 5. `Class.cast()` và giới hạn của thu hẹp kiểu

`isInstance()` trả về `boolean` và **không làm trình biên dịch suy ra kiểu cụ thể của biến**:

```java
Object candidate = "hello";
Class<String> expected = String.class;

if (expected.isInstance(candidate)) {
    // candidate vẫn có kiểu khai báo là Object.
    String result = expected.cast(candidate);
    System.out.println(result.toUpperCase()); // HELLO
}
```

`Class<T>.cast(Object)` dùng kiểu được đại diện bởi `Class<T>` để ép kiểu lúc chạy; nếu đối tượng không tương thích, nó ném `ClassCastException` (riêng `cast(null)` trả về `null`). Kết hợp `isInstance()` trước `cast()` giúp quyết định rõ cách xử lý trường hợp không khớp, chẳng hạn trả về kết quả lỗi riêng thay vì để ngoại lệ xuất hiện.

Với `Class<?>`, kiểu `T` cụ thể chưa được biết:

```java
Class<?> expected = String.class;
Object candidate = "hello";

if (expected.isInstance(candidate)) {
    Object accepted = expected.cast(candidate);
    System.out.println(accepted); // hello
}
```

Biến `accepted` vẫn được dùng như `Object` trong ví dụ; không thể coi `Class<?>` tự động biến thành `Class<String>` chỉ vì đối tượng thực tế là chuỗi. Nếu API biết kiểu cần trả về, hãy nhận tham số `Class<T>` và dùng `T` như hàm `requireType` trong chương trình đầy đủ.

## 6. Các trường hợp biên dễ nhầm

### `null`

Cả `obj instanceof T` lẫn `T.class.isInstance(obj)` đều trả về `false` khi `obj == null`. Vì vậy `isInstance()` không phải phép kiểm tra một giá trị có thể gán vào biến kiểu tham chiếu hay không theo mọi nghĩa: Java cho phép gán `null` cho nhiều biến tham chiếu, nhưng phép thử instance vẫn trả về `false`.

### Primitive, boxing và mảng

`int.class` là một đối tượng `Class` hợp lệ, nhưng **một giá trị primitive không phải đối tượng instance** để `isInstance()` chấp nhận:

```java
Integer boxed = 7;

System.out.println(int.class.isInstance(boxed));     // false
System.out.println(Integer.class.isInstance(boxed)); // true
```

Lệnh `Integer.class.isInstance(7)` cũng trả về `true` vì đối số primitive `7` được **autobox** thành `Integer` khi truyền vào tham số `Object`. Điều này không có nghĩa `int.class` và `Integer.class` là cùng một lớp.

Với mảng, Java kiểm tra loại thành phần và quy tắc tương thích mảng. `String[]` là một loại `Object[]`; `int[]` là một đối tượng và là `Object`, nhưng **không** là `Object[]`:

```java
System.out.println(Object.class.isInstance(new int[] {1}));    // true
System.out.println(Object[].class.isInstance(new int[] {1}));  // false
System.out.println(Object[].class.isInstance(new String[] {"a"})); // true
```

### Generic và type erasure

Thông tin tham số kiểu như `String` trong `List<String>` nhìn chung **không được lưu để kiểm tra phần tử bằng `instanceof` hoặc `Class.isInstance()`** ở thời điểm chạy:

```java
Object data = List.of("a", "b");

System.out.println(data instanceof List<?>);    // true
System.out.println(List.class.isInstance(data)); // true

// KHÔNG biên dịch với data là Object: kiểu tham số hóa không reifiable.
// boolean x = data instanceof List<String>;

// KHÔNG có class literal cho List<String>.
// Class<?> c = List<String>.class;
```

Hai phép kiểm tra hợp lệ chỉ xác nhận đối tượng là một `List`, không xác nhận mỗi phần tử có kiểu `String`. Khi cần xác minh phần tử, cần duyệt và kiểm tra dữ liệu theo yêu cầu thực tế, hoặc dùng cơ chế mô tả kiểu tổng quát riêng phù hợp với framework.

### Class loader và định danh kiểu

Hai lớp có **cùng tên đầy đủ** nhưng được định nghĩa bởi hai class loader khác nhau có thể là hai kiểu runtime khác nhau. `Class.isInstance()` kiểm tra tính tương thích với đúng đối tượng `Class` đang giữ, không chỉ so sánh chuỗi tên lớp. Điều này đặc biệt quan trọng trong hệ thống plugin hoặc môi trường nạp lớp động.

## 7. Phân biệt với `Class.isAssignableFrom()`

Reflection còn có phép kiểm tra rất gần nhưng nhận **kiểu**, không nhận đối tượng:

```java
System.out.println(Number.class.isInstance(Integer.valueOf(5))); // true
System.out.println(Number.class.isAssignableFrom(Integer.class)); // true
```

- `expectedType.isInstance(value)` hỏi **đối tượng `value`** có là instance của `expectedType` không.
- `expectedType.isAssignableFrom(actualType)` hỏi **kiểu `actualType`** có thể gán cho biến kiểu `expectedType` theo quan hệ kiểu tham chiếu hay không.

Nếu đã có đối tượng không `null`, `expectedType.isInstance(value)` thường là cách diễn đạt trực tiếp hơn việc tự lấy `value.getClass()`. Gọi `value.getClass()` trên `null` sẽ ném `NullPointerException`; còn `isInstance(null)` trả về `false`. `isAssignableFrom` cũng có thể kiểm tra quan hệ giữa các `Class` của kiểu primitive, nhưng không thay thế tự động các quy tắc boxing/unboxing của biểu thức Java.

## 8. Chọn API trong thực tế

Dùng **`instanceof`** khi logic xử lý biết trước kiểu cần kiểm tra, nhất là khi pattern variable giúp đọc và xử lý giá trị ngay. Ví dụ: một nhánh nghiệp vụ nhận `Object` và xử lý riêng `String` hoặc `Number`.

Dùng **`Class.isInstance()`** khi kiểu đích là một giá trị đi qua API, cấu hình hoặc registry; chẳng hạn bộ lọc nhận `Class<T> expectedType`, bộ điều phối plugin được đăng ký bằng đối tượng `Class`, hoặc tiện ích reflection muốn kiểm tra đối tượng trước khi gọi `expectedType.cast(...)`.

Một mẫu API hữu ích là:

```java
static <T> boolean accepts(Class<T> expectedType, Object candidate) {
    return expectedType.isInstance(candidate);
}
```

Ví dụ `accepts(CharSequence.class, "Java")` trả về `true`. Tham số `Class<T>` làm ý nghĩa của kiểu đích rõ ràng, còn `isInstance` thực hiện kiểm tra khi chạy.

Không cần thay mọi `instanceof` bằng reflection: nếu kiểu cố định trong mã, `instanceof` ngắn gọn và hỗ trợ pattern matching. Nếu kiểu có thể thay đổi trong lúc chạy, `Class.isInstance()` cho phép truyền kiểu như dữ liệu mà vẫn dùng quan hệ kế thừa/interface của Java.

## 9. Lỗi thường gặp và tự kiểm tra

- Viết `value instanceof expectedClass` khi `expectedClass` là biến `Class<?>`: sai cú pháp/kiểu; hãy gọi `expectedClass.isInstance(value)`.
- Tưởng `isInstance` tự ép kiểu biến: nó chỉ trả về `boolean`; cân nhắc `Class<T>.cast()` sau khi kiểm tra.
- Dùng `int.class` để kiểm tra một `Integer`: hai kiểu khác nhau, kết quả `false`.
- Dùng `List.class.isInstance(value)` để kết luận đó là `List<String>`: tham số kiểu đã bị erasure, kết luận này không được bảo đảm.
- Dùng `obj.getClass()` mà chưa xử lý `null`, hoặc so sánh tên lớp thay cho quan hệ tương thích kiểu và class loader.

**Câu hỏi tự kiểm tra:**

1. Nếu kiểu kiểm tra được lưu trong `Class<?> selected`, vì sao `instanceof selected` không hợp lệ, và lời gọi nào thay thế được?
2. Vì sao `Number.class.isInstance(Integer.valueOf(10))` là `true` nhưng `int.class.isInstance(Integer.valueOf(10))` là `false`?
3. Khi cần trả về `T` từ một hàm nhận `Class<T>`, vì sao kết hợp `isInstance` và `cast` rõ ràng hơn ép kiểu `T` không kiểm tra?
4. Một thư viện nhận tên lớp cấu hình ở thời điểm chạy nên dùng cơ chế nào để kiểm tra đối tượng? Nó cần kiểm soát thêm điều gì đối với tên lớp được phép tải?

**Ghi nhớ:** `instanceof` biểu diễn **kiểu đích ngay trong mã Java**; `Class.isInstance()` biểu diễn **kiểu đích bằng một đối tượng `Class` có thể chọn khi chạy**. Cả hai kiểm tra tương thích kiểu runtime, nhưng khác nhau ở khả năng truyền kiểu như dữ liệu và hỗ trợ thu hẹp kiểu của trình biên dịch.