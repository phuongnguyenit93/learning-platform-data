# Dùng raw type để né generic limitation — lỗi thường gặp trong Java Pattern Matching

## 1. Vấn đề: raw type không giải quyết được giới hạn của generic

Khi viết pattern matching trong Java, có lúc compiler từ chối một phép kiểm tra như `Box<String>(...)` hoặc `List<String>` đối với một giá trị chỉ có kiểu tĩnh `Object`. Một cách “chữa nhanh” thường gặp là bỏ `<String>` để dùng **raw type** (`Box`, `List`), hoặc ép kiểu bằng một **unchecked cast**. Cách đó có thể làm một đoạn mã biên dịch ở vị trí khác, nhưng **không phục hồi thông tin type argument ở runtime** và có thể biến lỗi kiểu được phát hiện sớm thành `ClassCastException` lúc chạy.

Bài này tập trung vào sai lầm đó trong bối cảnh **Java Core Pattern Matching**:

- Phân biệt `Box<String>`, `Box<?>` và raw `Box`.
- Hiểu vì sao type erasure giới hạn điều kiện `instanceof`, type pattern và generic record pattern.
- Thấy được cảnh báo `rawtypes`/`unchecked`, khả năng *heap pollution* và lỗi phát sinh muộn.
- Dùng type pattern, record pattern, wildcard, generic API hoặc kiểm tra dữ liệu ở ranh giới thay cho raw type.
- Chọn giải pháp an toàn khi buộc phải tương tác với thư viện legacy.

**Phiên bản:** generic và raw type đã có từ Java 5; type pattern cho `instanceof` chính thức ở **Java 16** (JEP 394); **record patterns** và pattern matching for `switch` chính thức ở **Java 21** (JEP 440, JEP 441). Các chương trình hoàn chỉnh bên dưới sử dụng Java 21.

## 2. Ba cách viết giống nhau ở runtime nhưng khác nhau về an toàn kiểu

Giả sử có generic record:

```java
record Box<T>(T value) {}
```

Ta có thể khai báo:

```java
Box<String> typed = new Box<>("hello");
Box<?> unknownComponent = new Box<>("hello");
Box raw = new Box("hello"); // Raw type: không nên dùng cho mã mới.
```

| Khai báo | Compiler biết gì về component? | Nên dùng khi nào? |
| --- | --- | --- |
| `Box<String>` | `value()` có kiểu `String` theo hợp đồng tĩnh | API đã biết component là chuỗi |
| `Box<?>` | `value()` chỉ có thể được tiêu thụ như `Object` nếu không có ràng buộc khác | Đã biết là `Box` nhưng chưa biết tham số kiểu |
| `Box` (raw) | Bỏ kiểm tra type argument; `value()` sau erasure có kiểu `Object` | Chủ yếu để tương thích một ranh giới legacy bất khả kháng |

`Box<String>` và `Box<Integer>` không phải hai **runtime class** tách biệt. Java dùng *type erasure*: type argument như `String` hay `Integer` phục vụ kiểm tra kiểu tĩnh, còn runtime class của chúng vẫn là `Box`.

**Điểm khác nhau:** `Box<?>` vẫn cho compiler biết bạn đang làm việc với một generic type có **tham số không xác định**, vì thế những thao tác không an toàn bị hạn chế. Raw `Box` bỏ đi chính hàng rào đó và làm cho một số thao tác chưa kiểm chứng có thể lọt qua kèm cảnh báo.

Trong Java, raw type được giữ lại chủ yếu vì **khả năng tương thích khi nâng cấp mã từ thời trước generics**, không phải vì nó là một lối thoát an toàn khỏi generic limitations.

## 3. Type erasure: cái gì có thể và không thể kiểm tra?

Xét:

```java
Object input = new Box<>("java");
```

Tại runtime ta có thể xác nhận `input` là instance của record class `Box`; nhưng chỉ riêng lớp `Box` **không mã hóa** type argument `String`. Vì vậy, không thể kết luận “mọi `Box` nhận được đều là `Box<String>`” chỉ bằng phép thử runtime trên outer object.

Một ví dụ **không hợp lệ khi biên dịch**, cố ý minh họa sai lầm:

```java
record Box<T>(T value) {}

static void incorrect(Object input) {
    // Sai: cần unchecked conversion Object -> Box<String>.
    if (input instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
```

Với JDK 21, compiler từ chối phép dùng record pattern `Box<String>(...)` trong ngữ cảnh `input` là `Object`, vì `Object` không thể được *checked cast* một cách an toàn sang `Box<String>` với type argument cụ thể. Đổi tham số thành raw `Box` **không sửa được điều kiện này**:

```java
static void alsoIncorrect(Box raw) {
    // Vẫn sai: raw Box không kiểm chứng được là Box<String>.
    if (raw instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
```

Cả hai là **mã minh họa lỗi**, không phải chương trình dùng để chạy. Thông báo có thể có dạng “cannot be safely cast to Box<java.lang.String>”.

Đối chiếu trường hợp **hợp lệ**:

```java
static void valid(Box<String> input) {
    if (input instanceof Box(var text)) {
        String strong = text; // Kiểu tĩnh suy luận: String.
        System.out.println(strong);
    }
}
```

Khi `input` có kiểu tĩnh `Box<String>`, compiler đã biết type argument từ hợp đồng API nên có thể suy luận `text` là `String`. Đây là **suy luận kiểu từ static context**, không phải kiểm tra type argument bằng reflection.

**Quy tắc của generic record pattern (Java 21):** khai báo type argument tường minh trong record pattern chỉ hợp lệ khi nguồn có thể checked-cast sang record type đó mà không cần unchecked conversion; record pattern không có type arguments sẽ sử dụng cơ chế suy luận kiểu được đặc tả tại JLS §18.5.5.

## 4. Sai lầm lớn: ép raw `Box` thành `Box<String>` bằng unchecked conversion

Đoạn dưới đây minh họa điều gì xảy ra khi cố tình bỏ bảo vệ kiểu rồi **hứa sai** với compiler rằng component là `String`.

Lưu vào `RawTypeTrap.java`:

```java
public class RawTypeTrap {
    record Box<T>(T value) {}

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void showFailure() {
        // Chỉ minh họa lỗi: trong ứng dụng thật, đừng làm thế.
        Box raw = new Box(42);
        Box<String> claimedStringBox = raw;

        System.out.println("raw=" + raw.value());

        try {
            String text = claimedStringBox.value();
            System.out.println(text);
        } catch (ClassCastException ex) {
            System.out.println("read-failed="
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        showFailure();
    }
}
```

Chạy:

```bash
javac --release 21 RawTypeTrap.java
java RawTypeTrap
```

Kết quả:

```text
raw=42
read-failed=ClassCastException
```

Giải thích theo thứ tự:

1. Raw `Box` chứa `Integer` với giá trị `42`.
2. Phép gán `Box<String> claimedStringBox = raw` là **unchecked conversion**: compiler không thể xác thực type argument của giá trị nguồn.
3. Việc gán có thể hoàn tất mà **không kiểm tra** `42` là `String`, vì runtime class vẫn chỉ là `Box`.
4. Tại nơi đọc `claimedStringBox.value()` vào `String`, compiler tạo phép kiểm tra/cast cần thiết cho kiểu kỳ vọng. Giá trị thực là `Integer`, dẫn đến `ClassCastException`.

`@SuppressWarnings` chỉ được dùng **trong ví dụ có chủ đích gây lỗi** để không bị các cảnh báo làm nhiễu phần minh họa. Nó không làm dữ liệu an toàn hơn. Trong mã thật, nên loại bỏ raw conversion và **không che cảnh báo chỉ để bản build sạch**.

Lưu ý: `ClassCastException` có thể xuất hiện **sau** nơi phát sinh unchecked conversion, khiến lỗi khó truy vết. Đó chính là nguy cơ *heap pollution*: một biểu thức có kiểu tham số hóa ở compile time nhưng giá trị trong đó không tuân thủ cam kết type argument.

## 5. Raw type kết hợp `var` trong record pattern vẫn mất thông tin kiểu

Có người nghĩ rằng bỏ type argument rồi viết `Box(var value)` sẽ làm compiler “nhìn vào dữ liệu thực tế” để biết `value` là `String`. Điều này **không đúng**.

```java
record Box<T>(T value) {}

static void inspectRaw(Box raw) {
    if (raw instanceof Box(var item)) {
        Object value = item; // Hợp lệ.
        System.out.println(value);
    }
}
```

Do biến `raw` không giữ type argument cụ thể, compiler **không thể suy luận `item` là `String`** chỉ vì một lần chạy nào đó chứa chuỗi. Với `Box<T>` không có bound bổ sung, kiểu suy luận hữu ích tại đây là `Object`.

Đoạn sau **không hợp lệ** nếu dùng ngay sau matching ấy:

```java
if (raw instanceof Box(var item)) {
    String text = item; // Lỗi: Object không tự gán được cho String.
}
```

Nếu chữa tiếp bằng `(String) item`, ta chỉ đưa rủi ro `ClassCastException` quay trở lại. `var` là công cụ **suy luận kiểu tĩnh**, không phải công cụ “phục hồi generics sau erasure”.

Đối với nested generic records, cùng nguyên tắc tiếp tục áp dụng: thông tin type argument bị bỏ ở tầng ngoài **không tự quay lại** khi matching lồng tầng. Hãy giữ generic type chính xác qua các lời gọi và component của record nếu muốn compiler suy luận được kiểu sâu bên trong.

## 6. Giải pháp 1: giữ nguyên kiểu generic ở API

Khi hàm chỉ xử lý một `Box<String>`, hãy diễn đạt đúng điều đó:

```java
record Box<T>(T value) {}

static void print(Box<String> input) {
    if (input instanceof Box(var text)) {
        String validatedByCompiler = text;
        System.out.println(validatedByCompiler.toUpperCase());
    }
}
```

Đây là **đoạn minh họa trong một lớp/phạm vi đã khai báo `Box`**, không phải tệp độc lập. Kiểu của `text` được suy luận là `String` từ `Box<String>`.

Nếu cần xử lý tổng quát hơn, viết phương thức generic:

```java
static <T> T unpack(Box<T> input) {
    return input.value();
}
```

Không có lý do dùng raw `Box` ở đây. Phương thức `unpack` duy trì tương quan giữa kiểu đầu vào và đầu ra mà không cần unchecked cast.

Với record lồng nhau, vẫn có thể suy luận qua nhiều tầng:

```java
Box<Box<String>> nested =
        new Box<>(new Box<>("java"));

if (nested instanceof Box(Box(var word))) {
    String s = word; // Kiểu String nhờ generic đã được giữ.
    System.out.println(s);
}
```

Đoạn lồng trên là **mã trong ngữ cảnh đã khai báo `Box`**, dùng cú pháp record patterns của Java 21. Compiler suy luận từ `Box<Box<String>>` đến `Box<String>` rồi đến `String`; không cần sửa thành raw type để pattern chạy.

## 7. Giải pháp 2: kiểm tra component bằng type pattern, không giả vờ kiểm tra type argument

Khi đầu vào **thật sự chỉ có kiểu `Object`**, đôi khi không có hợp đồng `Box<String>` để bảo toàn. Nếu mục tiêu là xử lý một `Box` có **component thực tế là `String`**, dùng record pattern có **type pattern ở component**:

```java
if (input instanceof Box(String text)) {
    System.out.println(text.toUpperCase());
}
```

Đây là kiểm tra hai bước theo cấu trúc record: `input` có dạng record `Box`, và **component bên trong** là một `String`. Nó **không xác minh trực tiếp type argument `T` của `Box<T>` đã bị xóa**. Với `record Box<T>(T value)`, đây là một giải pháp runtime hợp lệ cho dữ liệu đơn giản cần đọc.

Lưu vào `ComponentPatternDemo.java`:

```java
import java.util.Locale;

public class ComponentPatternDemo {
    record Box<T>(T value) {}

    static void inspect(Object input) {
        if (input instanceof Box(String text)) {
            System.out.println("text="
                    + text.toUpperCase(Locale.ROOT));
        } else if (input instanceof Box(var component)) {
            System.out.println("other="
                    + (component == null
                            ? "null"
                            : component.getClass().getSimpleName()));
        } else {
            System.out.println("not-box");
        }
    }

    public static void main(String[] args) {
        inspect(new Box<>("java"));
        inspect(new Box<>(42));
        inspect(new Box<>(null));
        inspect("plain");
    }
}
```

```bash
javac --release 21 ComponentPatternDemo.java
java ComponentPatternDemo
```

Kết quả:

```text
text=JAVA
other=Integer
other=null
not-box
```

**Vì sao `null` khác nhau?**

- `Box(String text)` không khớp khi component là `null`, vì type pattern `String text` ở đây cần giá trị thực sự thuộc `String`.
- `Box(var component)` trong ngữ cảnh này có thể ràng buộc component `null`; `var` không tự biến `null` thành `String`.
- Nếu chính `input` là `null`, record pattern `Box(...)` ở tầng ngoài không khớp.

Đây là cách **kiểm tra cấu trúc và giá trị thực tế** ở ranh giới nhận dữ liệu chưa biết, khác với việc gán raw `Box` cho `Box<String>`.

## 8. Giải pháp 3: `Box<?>` và wildcard khi chưa biết type argument

Đối với một `Box` mà bạn chưa biết `T`, khai báo **`Box<?>`** thường hợp lý hơn raw `Box`:

```java
static void inspect(Box<?> input) {
    Object item = input.value();

    if (item instanceof String text) {
        System.out.println(text.length());
    } else {
        System.out.println("not a String");
    }
}
```

Compiler không hứa `item` là `String`; ta chỉ sử dụng `String` **sau một type pattern hợp lệ**. Điều này giữ nguyên tính chất “tham số kiểu chưa biết” mà không phá vỡ generic contract.

`Box<?>` không tương đương `Box<Object>` trong mọi thao tác ghi. Wildcard mang một **kiểu được capture nhưng chưa biết**; nhờ vậy Java ngăn nhiều phép gán component không an toàn nếu `Box` là generic class mutable.

Nếu cần đọc một component có quan hệ kiểu cụ thể, có thể dùng upper bound:

```java
static void printNumber(Box<? extends Number> input) {
    Number value = input.value();
    System.out.println(value.doubleValue());
}
```

Nếu cần đưa một giá trị `Integer` vào một consumer generic, có thể cân nhắc lower bound (`? super Integer`) theo quy tắc PECS (**Producer Extends, Consumer Super**). Nhưng đừng thêm wildcard chỉ như một mẹo qua compiler: hãy đặt bound theo quan hệ đọc/ghi thực sự của API.

## 9. `instanceof List<?>` an toàn hơn `instanceof List<String>`

Sai lầm tương tự thường xảy ra với Collections:

```java
// Không biên dịch khi input là Object:
if (input instanceof java.util.List<String> names) {
    System.out.println(names.size());
}
```

Java runtime không thể chứng minh mọi phần tử của một `List` đều là `String` chỉ từ type argument đã bị xóa.

Cách đúng khi cần nhận một list bất kỳ là dùng **reifiable type** `List<?>`:

```java
if (input instanceof java.util.List<?> values) {
    System.out.println(values.size());
}
```

Nếu nghiệp vụ yêu cầu nội dung là chuỗi, kiểm tra **từng phần tử**, thay vì ép toàn bộ collection sang `List<String>`.

Lưu vào `ListPatternDemo.java`:

```java
import java.util.List;

public class ListPatternDemo {
    static void inspect(Object input) {
        if (input instanceof List<?> values) {
            for (Object value : values) {
                if (value instanceof String text) {
                    System.out.println("string=" + text);
                } else {
                    System.out.println("skip");
                }
            }
        } else {
            System.out.println("not-list");
        }
    }

    public static void main(String[] args) {
        inspect(List.of("a", 3, "b"));
        inspect("plain");
    }
}
```

```bash
javac --release 21 ListPatternDemo.java
java ListPatternDemo
```

Kết quả:

```text
string=a
skip
string=b
not-list
```

`List<?>` chỉ xác định input là một `List`; **nó không xác minh phần tử**. Chính `value instanceof String text` thực hiện việc phân biệt từng giá trị. Nếu list chứa `null`, type pattern `String text` sẽ trả `false` cho phần tử đó.

## 10. Pattern matching với `switch`: phân loại giá trị thay vì dùng raw cast

Với Java 21, `switch` có thể dùng record patterns để phân nhánh theo loại component. Điều này giúp viết các consumer xử lý dữ liệu không đồng nhất mà không cần unchecked cast.

Lưu vào `SwitchBoxDemo.java`:

```java
public class SwitchBoxDemo {
    record Box<T>(T value) {}

    static String classify(Object input) {
        return switch (input) {
            case Box(String text) ->
                    "text:" + text;
            case Box(var item) ->
                    "box:" + (item == null
                            ? "null"
                            : item.getClass().getSimpleName());
            case null ->
                    "null-input";
            default ->
                    "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Box<>("hello")));
        System.out.println(classify(new Box<>(24)));
        System.out.println(classify(new Box<>(null)));
        System.out.println(classify(null));
    }
}
```

```bash
javac --release 21 SwitchBoxDemo.java
java SwitchBoxDemo
```

Kết quả:

```text
text:hello
box:Integer
box:null
null-input
```

Ở đây, `case Box(String text)` xử lý trường hợp cụ thể trước, còn `case Box(var item)` bao phủ các `Box` còn lại. **Thứ tự quan trọng:** đặt case rộng `Box(var item)` trước case chuỗi sẽ làm case cụ thể phía sau bị che khuất (*dominated case*) và compiler có thể từ chối.

`case null` xử lý selector `null` riêng. Không được hiểu pattern `Box(var item)` là lời hứa rằng `item` mang một generic type cụ thể ở runtime.

Khi mỗi variant có một record type riêng trong sealed hierarchy, nên ưu tiên mô hình domain rõ kiểu cùng các `case` exhaustive thay vì trộn các payload khác loại vào raw `Box`.

## 11. Kiểm tra record pattern lồng nhau từ dữ liệu chưa biết

Generic record patterns có thể **lồng nhau**. Nếu đầu vào là `Object`, không thể dựa vào type argument đã bị xóa ở tầng ngoài; nhưng có thể dùng các pattern kiểm tra component từng tầng.

Giả sử:

```java
record Box<T>(T value) {}
record Envelope<T>(T payload) {}
```

Cách tiếp cận:

```java
Object input = new Envelope<>(new Box<>("deep"));

if (input instanceof Envelope(Box(String text))) {
    System.out.println("nested=" + text);
}
```

Kết quả trong trường hợp trên:

```text
nested=deep
```

Đây là **đoạn minh họa trong phạm vi đã khai báo hai record**. Record pattern `Envelope(...)` trước hết kiểm tra bản thân wrapper; pattern `Box(...)` kiểm tra component bên trong; `String text` kiểm tra tiếp component cuối.

Dữ liệu giả có `Envelope<Box<Integer>>` không vượt qua pattern `String text`, cho dù container ở tầng ngoài có cùng runtime class `Envelope`. Không có unchecked cast nào được dùng.

**Giới hạn còn lại:** kiểm tra từng component đang quan sát **không đồng nghĩa xác thực toàn bộ một cấu trúc dữ liệu generic phức tạp**. Ví dụ `Box<List<String>>` chứa một collection cần kiểm tra từng phần tử nếu nguồn đến từ vùng dữ liệu chưa được tin cậy.

## 12. Biến dữ liệu ở ranh giới thành một collection đúng kiểu

Một cách mạnh hơn “cast rồi tin” là **validate rồi copy** sang cấu trúc generic đúng kiểu. Khi đầu vào có thể đến từ API cũ hoặc deserializer không giữ generic contract, hãy thực hiện bước này ở một **adapter** duy nhất.

Lưu vào `SafeListAdapterDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeListAdapterDemo {
    static List<String> readStrings(Object input) {
        if (!(input instanceof List<?> values)) {
            throw new IllegalArgumentException("not a list");
        }

        List<String> result = new ArrayList<>();

        for (Object item : values) {
            if (!(item instanceof String text)) {
                throw new IllegalArgumentException(
                        "non-string element");
            }

            result.add(text);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println("items="
                + readStrings(List.of("a", "b")));

        try {
            readStrings(List.of("a", 2));
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
```

```bash
javac --release 21 SafeListAdapterDemo.java
java SafeListAdapterDemo
```

Kết quả:

```text
items=[a, b]
error=non-string element
```

Ở đây adapter có hợp đồng cụ thể:

1. Chỉ nhận đối tượng là `List<?>`.
2. Từng phần tử phải matching `String text`.
3. Dữ liệu hợp lệ được **copy** vào `List<String>` mới, tránh phụ thuộc vào collection mutable gốc.
4. Dữ liệu không hợp lệ bị từ chối ở ranh giới với lỗi rõ ràng.

Nếu `null` là một giá trị cho phép trong nghiệp vụ, phải định nghĩa chính sách riêng. Adapter trên **từ chối `null`** vì `null` không khớp `String text`, và `List.copyOf` cũng không chấp nhận phần tử `null`.

Cách này không phải là “khôi phục type argument từ runtime”; nó là **chứng minh và tái tạo một container mới có dữ liệu thực sự đáp ứng type argument mong muốn**.

## 13. Khi nào `Class<T>` giúp kiểm tra runtime?

Đối với **một component đơn lẻ**, một type token `Class<T>` cho phép caller chỉ ra kiểu runtime cần kiểm tra bằng `isInstance` và `cast`. Ví dụ:

```java
record Box<T>(T value) {}

static <T> java.util.Optional<T> findBoxComponent(
        Object input,
        Class<T> expected) {

    if (input instanceof Box(var item)
            && expected.isInstance(item)) {
        return java.util.Optional.of(expected.cast(item));
    }

    return java.util.Optional.empty();
}
```

Đây là **đoạn minh họa trong một lớp/phạm vi chứa `Box`**. Với `expected = String.class`, Java xác minh component là `String` trước khi chuyển đổi; nếu không đúng thì trả `Optional.empty()` theo logic trên. Kiểm tra này không cần raw `Box`.

Điểm giới hạn: `String.class` kiểm tra được một class cụ thể; **không có `List<String>.class` để xác minh đầy đủ mọi type argument của một parameterized collection**. `Class<List>` hoặc `List.class` chỉ xác minh lớp/interface `List`, không xác minh mỗi element có kiểu `String`.

Nếu cần kiểm tra dữ liệu nhiều cấp, phải đi qua các tầng container, kiểm tra phần tử và/hoặc áp dụng schema/validation thích hợp.

## 14. Raw type có thể gây rủi ro gì cho type hierarchy và domain?

Trong domain model dùng sealed interface, record và pattern matching, raw generic thường dẫn đến các vấn đề dây chuyền:

- **Mất type-safety của API:** caller có thể truyền một `Box<Integer>` vào biến raw `Box` rồi chuyển không kiểm chứng sang `Box<String>`.
- **Mất độ chính xác của suy luận pattern variable:** `Box(var component)` không còn biết component là `String` nếu kiểu tĩnh đã bị thô hóa.
- **Giảm ích lợi của compiler:** lỗi được phát hiện ở vị trí tiêu thụ thay vì ở vị trí khai báo/tạo dữ liệu.
- **Tăng unchecked warning hoặc buộc cast thủ công:** nhiều chỗ phải tự bảo đảm một điều mà compiler không thể xác minh.
- **Che contract của domain:** ví dụ `Command<Result>` thành raw `Command` khiến các loại request/result dễ bị trộn.
- **Gây lỗi muộn ở consumer:** `ClassCastException` có thể xảy ra trong `switch`, service method hoặc mapper sau nhiều lớp truyền dữ liệu.

Một sealed hierarchy không tự sửa được lỗi do raw generic: sealed giúp giới hạn **tập subtype trực tiếp**, còn generic giúp bảo toàn **quan hệ kiểu giữa dữ liệu trong các class/record**. Cần dùng đúng cả hai cơ chế ở đúng vai trò.

## 15. Cảnh báo compiler: dùng để tìm lỗi, không phải để che

Khi nghi ngờ mã legacy dùng raw type, có thể bật cảnh báo:

```bash
javac --release 21 -Xlint:rawtypes -Xlint:unchecked MyClass.java
```

Đây là **lệnh minh họa** cho file nguồn tương ứng. `-Xlint:rawtypes` giúp nhận diện chỗ dùng raw generic type; `-Xlint:unchecked` giúp nhận diện những phép chuyển đổi hoặc thao tác không được compiler kiểm chứng. Không phải **mỗi** lần xuất hiện raw type đều phát sinh cả hai loại cảnh báo: hành vi chính xác tùy ngữ cảnh.

`@SuppressWarnings("unchecked")` **không chuyển một phép ép kiểu thành an toàn**. Nếu buộc phải hỗ trợ một API legacy, hãy:

1. Khoanh vùng tương tác raw trong một adapter nhỏ.
2. Kiểm tra rõ kiểu đối tượng và phần tử có thể kiểm tra được.
3. Tạo/copy sang kiểu dữ liệu an toàn trước khi xuất ra API hiện đại.
4. Chỉ suppress cảnh báo hẹp nhất tại đoạn đã được kiểm toán, kèm lý do cụ thể.
5. Có test với đúng kiểu, sai kiểu, `null` và dữ liệu trộn kiểu.

Việc xóa hết cảnh báo bằng suppression trên toàn package chỉ làm cho các biến thể lỗi mới khó bị phát hiện.

## 16. Bảng chọn giải pháp thay thế

| Tình huống | Không nên | Nên dùng |
| --- | --- | --- |
| Hàm đã biết đầu vào là `Box<String>` | Đổi tham số thành raw `Box` để pattern dễ viết | Giữ `Box<String>`; dùng `Box(var text)` |
| Hàm nhận `Object`, cần chuỗi trong `Box` | Thử `Box<String>(...)` hoặc unchecked cast | `instanceof Box(String text)` |
| Hàm nhận `List` với phần tử chưa biết | Ép raw `List` sang `List<String>` | `List<?>` và kiểm tra từng phần tử |
| Nested generic record đã có kiểu tĩnh đầy đủ | Làm raw tầng ngoài để né suy luận | Giữ kiểu generic và nested record patterns |
| Dữ liệu JSON/API chưa tin cậy | Tin vào cast `List<String>` | Validate schema và copy vào cấu trúc đúng kiểu |
| Cần xử lý nhiều dạng `Box` | Gộp vào raw và cast từng nơi | `switch` với type/record patterns có kiểm tra component |
| Tích hợp thư viện quá cũ | Rải raw type khắp domain | Adapter cô lập raw, validate trước khi trả generic API |
| Cần kiểm tra component đơn lẻ theo `Class<T>` | Giả sử `T` được lưu trong `Box` runtime | `expected.isInstance` / `expected.cast` |
| Muốn tắt `unchecked` warning | Suppress toàn dự án | Cải thiện generic contract hoặc suppress có lý do hẹp |

## 17. Những hiểu nhầm thường gặp

1. **“Bỏ `<String>` làm compiler nhận ra giá trị thực tế là `String`.”** Sai: raw type bỏ type argument, không thêm thông tin runtime.
2. **“Raw type và `<?>` giống hệt nhau.”** Sai: wildcard giữ ràng buộc generic để compiler ngăn nhiều thao tác không an toàn; raw nới lỏng kiểm tra cho legacy.
3. **“`instanceof Box<String>` kiểm tra mọi component bằng `String.class`.”** Sai: type erasure ngăn kiểm tra type argument trực tiếp trong ngữ cảnh cần unchecked conversion.
4. **“`Box(var s)` luôn suy luận `s` thành kiểu thật của đối tượng ở runtime.”** Sai: compiler suy luận dựa trên kiểu tĩnh của ngữ cảnh pattern.
5. **“Gán raw `Box` cho `Box<String>` xong không lỗi nghĩa là an toàn.”** Sai: lỗi có thể chỉ xuất hiện khi truy xuất component.
6. **“`@SuppressWarnings` đã giải quyết rủi ro.”** Sai: chỉ ẩn cảnh báo, không thêm runtime validation.
7. **“`List<?>` đảm bảo phần tử cùng kiểu.”** Sai: mọi phần tử vẫn phải được coi là kiểu chưa biết cho đến khi kiểm tra hoặc có hợp đồng khác.
8. **“`Box(String s)` chứng minh type argument `T` của mọi reference tới Box là String.”** Sai: nó kiểm tra component được matching, không dựng lại toàn bộ thông tin generic đã bị xóa.
9. **“Pattern matching loại bỏ mọi `ClassCastException`.”** Sai: unchecked conversion/heap pollution từ chỗ khác vẫn có thể gây lỗi sau đó.
10. **“Một type token `Class<T>` kiểm tra được `List<String>`.”** Sai: `Class` không chứa đầy đủ parameterized type arguments của container.
11. **“Raw type là cách tốt nhất khi code generic phức tạp.”** Sai: thường nên cải thiện khai báo `T`, wildcard bound, adapter hoặc API design.
12. **“Có thể dùng record pattern để ép mọi class thường thành record.”** Sai: record pattern chỉ áp dụng cho record class tương ứng; không phải cơ chế deconstruction tùy ý cho class bất kỳ.

## 18. Checklist khi review một refactor liên quan raw type

- Có còn khai báo `List`, `Map`, `Box` mà thiếu type arguments không?
- Chúng có thật sự bắt buộc để tương thích legacy, hay có thể đổi thành `List<?>`, `Map<?, ?>`, `Box<T>`?
- Có unchecked conversion nào đang biến dữ liệu sai thành một kiểu generic hứa hẹn quá mạnh không?
- Nếu `instanceof` với record pattern không biên dịch, đã xác định **checked cast limitation** thay vì sửa bằng raw chưa?
- Với `Object` hoặc payload chưa tin cậy, có kiểm tra **giá trị component** bằng type pattern trước khi dùng không?
- Với collection, đã kiểm tra từng phần tử trước khi trả `List<String>` chưa?
- Có chỗ nào dùng `(String)` chỉ để “bù” cho việc mất generic type information không?
- Đã bật `-Xlint:rawtypes -Xlint:unchecked` và xem xét cảnh báo chưa?
- Đã test `null`, sai kiểu, nested record, dữ liệu sai bên trong collection và tình huống `ClassCastException` chưa?
- Nếu sửa API từ raw sang generic, những caller còn phụ thuộc hợp đồng cũ đã được cập nhật hoặc cô lập trong adapter chưa?

**Kết luận:** Raw type chỉ là cơ chế tương thích lịch sử. Trong Java Pattern Matching, nó **không vượt qua type erasure một cách an toàn**, không chứng minh được `Box<T>` mang type argument nào và có thể đẩy lỗi từ compile time sang runtime. Hãy **giữ generic type ở API**, dùng **wildcard khi chưa biết type argument**, dùng **type/record patterns để kiểm tra component**, hoặc **validate và copy dữ liệu** ở ranh giới hệ thống thay vì che cảnh báo bằng raw type.

## Tài liệu chính thức

- [Oracle Java SE 21 — Record Patterns: Generic Records và Type Inference](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394)
- [JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — §4.8 Raw Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.8)
- [Java Language Specification 21 — §5.1.9 Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.9)
- [Java Language Specification 21 — §14.30 Record Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java Language Specification 21 — §18.5.5 Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5)
