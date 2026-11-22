# Khi nào vẫn cần cast tường minh trong Java?

> **Module:** Java Core Pattern Matching — `instanceof` cơ bản. Các ví dụ dùng **Java 17+**, khi *pattern matching for `instanceof`* đã là tính năng chính thức (từ Java 16). Trọng tâm là **ép kiểu tham chiếu** như `(String) value`, không phải ép kiểu số nguyên/thực.

## Bạn sẽ hiểu được gì?

Sau bài này, bạn có thể:

- Phân biệt phép **kiểm tra kiểu** (`instanceof`), phép **ép kiểu tường minh** (`(T) expression`) và **type pattern** (`instanceof T variable`).
- Nhận ra khi nào code theo cú pháp `instanceof` truyền thống vẫn cần cast, khi nào có thể thay toàn bộ bằng pattern variable.
- Giải thích vì sao compiler không tự suy ra kiểu chỉ từ một biến `boolean`, một lời gọi helper hoặc một hợp đồng runtime.
- Xử lý những trường hợp pattern matching chưa thay thế được cast: API trả về `Object`, giới hạn của generics, kiểu chỉ biết qua `Class<T>`, và lời gọi phương thức overload với `null`.
- Phân biệt cast có kiểm tra runtime, cast không được kiểm tra đầy đủ (*unchecked cast*) và `ClassCastException`.

## 1. Ba cú pháp trông giống nhau nhưng có vai trò khác nhau

Giả sử:

~~~java
Object value = "Java";
~~~

### 1.1. `instanceof` truyền thống: chỉ nhận kết quả boolean

~~~java
if (value instanceof String) {
    // Java biết điều kiện true, nhưng không sinh biến String mới.
}
~~~

Biểu thức `value instanceof String` trả về `true` hoặc `false`. **Bản thân cú pháp này không khai báo một biến có kiểu `String`**. Nếu muốn dùng các API riêng của `String` qua biến `value` có kiểu tĩnh `Object`, thường phải cast:

~~~java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

Dòng `(String) value` là **cast tường minh**; compiler cho phép dùng biến `text` như `String`. Cast kiểm tra kiểu tham chiếu ở runtime khi cần, và có thể ném `ClassCastException` nếu giá trị không tương thích.

### 1.2. Pattern matching for `instanceof`: nhận luôn biến đúng kiểu

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Pattern `String text` vừa kiểm tra, vừa tạo biến `text` (kiểu tĩnh `String`) trên đường đi mà match chắc chắn thành công. **Trong trường hợp này không cần cast thêm**:

~~~java
// Thừa và dễ gây nhầm:
if (value instanceof String text) {
    String again = (String) value;
}
~~~

Đây là mục đích quan trọng của pattern matching: loại bỏ mẫu code `instanceof` rồi cast thủ công lặp lại.

### 1.3. Cast không thay thế phép kiểm tra có điều kiện

~~~java
Object value = Integer.valueOf(42);
String text = (String) value; // Biên dịch được, ném ClassCastException khi chạy.
~~~

Compiler cho phép cast từ `Object` sang `String` vì giá trị `Object` *có thể* là chuỗi; tuy nhiên đối tượng thực tế ở đây là `Integer`. Cast không biến `Integer` thành chuỗi. `instanceof String` sẽ trả về `false` thay vì ném lỗi, còn `String.valueOf(value)` là **chuyển thành biểu diễn chuỗi**, không phải downcast. Ba thao tác phục vụ các mục đích khác nhau.

## 2. Khi dùng cú pháp `instanceof` cũ, cast vẫn cần để gọi API kiểu con

Một API có thể cố ý công bố kiểu tổng quát:

~~~java
static void printLength(Object input) {
    if (input instanceof String) {
        String text = (String) input; // Cần khi giữ cách viết instanceof cũ.
        System.out.println(text.length());
    }
}
~~~

Tại dòng `text.length()`, compiler biết `text` là `String`. Nếu viết `input.length()` thì không biên dịch, bởi kiểu khai báo của `input` vẫn là `Object`. Kiểm tra `instanceof` **không đổi kiểu tĩnh của biến ban đầu**.

**Cách nên dùng từ Java 16+:**

~~~java
static void printLength(Object input) {
    if (input instanceof String text) {
        System.out.println(text.length());
    }
}
~~~

Sự khác nhau nằm ở tên biến được tạo, không nằm ở kiểu thực tế của đối tượng. Đây là trường hợp **“cần cast với lối viết cũ”**, nhưng không phải một giới hạn của pattern matching hiện đại.

### Khi bắt buộc giữ API/cú pháp cũ

Bạn có thể gặp code thư viện hoặc source phải biên dịch trên Java 8–15, nơi type pattern chưa sẵn sàng chính thức. Khi đó lối viết `if (o instanceof T) { T x = (T) o; }` vẫn là cách thông dụng. Nếu dự án được phép dùng Java 17+, nên cân nhắc refactor thành `instanceof T x`.

## 3. Compiler không nhớ một kiểm tra đã bị “đóng gói” thành boolean

Xem ví dụ:

~~~java
Object input = "  Java  ";
boolean isString = input instanceof String;

if (isString) {
    String text = (String) input;
    System.out.println(text.trim());
}
~~~

Mặc dù con người nhìn thấy `isString` được tính từ `input instanceof String`, Java **không dùng biến boolean tùy ý làm bằng chứng kiểu** để đổi kiểu của `input` hay tạo pattern variable. Vì thế, trong lối viết này, việc khai báo `String text` từ `input` vẫn cần cast.

Tương tự với helper:

~~~java
static boolean isText(Object value) {
    return value instanceof String;
}

// Ở nơi gọi:
if (isText(input)) {
    String text = (String) input;
    System.out.println(text.length());
}
~~~

Lời gọi `isText(input)` trả về `boolean`; compiler không giả định kết quả này thiết lập quan hệ kiểu cho `input`.

**Refactor để bỏ cast và giữ điều kiện gần chỗ dùng:**

~~~java
if (input instanceof String text) {
    System.out.println(text.trim());
}
~~~

Hoặc dùng guard clause; Java hỗ trợ *flow scoping*:

~~~java
static int lengthIfText(Object input) {
    if (!(input instanceof String text)) {
        return 0;
    }
    return text.length(); // text vẫn ở phạm vi an toàn tại đây.
}
~~~

Vì nhánh `return` kết thúc phương thức khi match thất bại, compiler biết mọi đường đi đến `text.length()` đều đã match thành công. **Đừng cast chỉ vì tưởng pattern variable không thể dùng sau dấu `}`**; phạm vi phụ thuộc luồng điều khiển chứ không đơn thuần vào ngoặc nhọn.

**Lưu ý về dữ liệu có thể thay đổi:** Nếu kiểm tra một field rồi cast lại field đó ở thời điểm khác, một thread khác có thể đổi giá trị giữa hai thao tác. Ví dụ `if (holder.value instanceof String) { String s = (String) holder.value; }` không đảm bảo lần đọc thứ hai là cùng đối tượng. Hãy chụp giá trị vào biến cục bộ rồi match một lần: `Object snapshot = holder.value; if (snapshot instanceof String s) { ... }`. Đây là lý do bổ sung để ưu tiên pattern variable, không phải lý do để cast mù.

## 4. Khi API chỉ trả về `Object` mà bạn cần kiểu cụ thể

Ở một ranh giới API cũ, dữ liệu đôi khi được công bố bằng `Object`:

~~~java
Object raw = legacyApiResult(); // Ví dụ minh họa; phương thức do dự án cung cấp.
String name = (String) raw;
~~~

Nếu **hợp đồng API** bảo đảm `raw` luôn là `String`, cast này có thể là cách ngắn nhất để đưa dữ liệu về kiểu mong muốn. Tuy nhiên, nó đặt niềm tin vào hợp đồng: nếu API trả kiểu khác, chương trình có thể ném `ClassCastException`.

Nếu dữ liệu chưa được tin cậy, ưu tiên kiểm tra và xử lý trường hợp không hợp lệ:

~~~java
Object raw = legacyApiResult(); // Ví dụ minh họa; không phải chương trình độc lập.
if (!(raw instanceof String name)) {
    throw new IllegalArgumentException("Expected a String");
}
System.out.println(name.toUpperCase());
~~~

**Điểm cần nhớ:** `(String) raw` có thể cần khi API yêu cầu bạn tự chuyển từ kiểu công bố `Object` sang kiểu cụ thể. Nếu có thể biểu đạt được điều kiện bằng type pattern, bạn thường loại được cast thủ công. Khi thiết kế API mới, ưu tiên kiểu trả về chính xác hoặc generic an toàn để người gọi không phải cast.

### Kiểu đã cụ thể thì không cần cast

~~~java
String name = "Java";
String copy = name; // Không cần (String) name.
~~~

Một cast thừa không tăng độ an toàn. Với Java 17, cố viết `name instanceof String text` khi `name` đã có kiểu tĩnh `String` còn là lỗi biên dịch do kiểu pattern bao phủ toàn bộ kiểu tĩnh của biểu thức. Hãy dùng `name` trực tiếp.

## 5. Generics và type erasure: trường hợp cast còn xuất hiện nhưng cần cảnh giác

Java sử dụng **type erasure**: ở runtime, một đối tượng `List<String>` và một đối tượng `List<Integer>` đều có kiểu lớp danh sách, không mang theo đầy đủ đối số kiểu phần tử để JVM xác nhận bằng một `instanceof` thông thường.

Ví dụ sau **cố ý không biên dịch** khi target là `Object`:

~~~java
Object raw = java.util.List.of("a", "b");
if (raw instanceof java.util.List<String> names) { // ERROR: List<String> không reifiable.
    System.out.println(names.size());
}
~~~

Type pattern có thể kiểm tra một kiểu reifiable:

~~~java
Object raw = java.util.List.of("a", "b");
if (raw instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}
~~~

Nhưng `items` có kiểu `List<?>`: compiler chưa có chứng cứ rằng **mọi phần tử** đều là `String`.

### 5.1. Cast generic không bảo đảm kiểu phần tử

~~~java
Object raw = java.util.List.of(1, 2);
@SuppressWarnings("unchecked")
java.util.List<String> names = (java.util.List<String>) raw;

String first = names.get(0); // Có thể ném ClassCastException ở lúc lấy phần tử.
~~~

Cast sang `List<String>` **không kiểm tra từng phần tử là String**. Compiler thường báo cảnh báo *unchecked cast*; annotation chỉ **ẩn cảnh báo**, không tạo bảo đảm runtime. Trong ví dụ trên, phép đọc phần tử như `String` sẽ lỗi vì phần tử thực tế là `Integer`. Vị trí ném lỗi có thể ở điểm dùng phần tử, chứ không nhất thiết ngay tại dòng cast.

Nếu một API cũ trả về raw type hoặc `Object` nhưng hợp đồng bên ngoài bảo đảm danh sách chỉ có chuỗi, nhóm code tích hợp đôi khi phải viết cast unchecked. Hãy giới hạn chỗ dùng và phạm vi `@SuppressWarnings("unchecked")`, nêu rõ hợp đồng đã được kiểm tra ở đâu, và tránh truyền danh sách đó ra ngoài như dữ liệu đã được kiểm chứng nếu chưa thể bảo đảm.

### 5.2. Phương án an toàn hơn: kiểm tra và sao chép phần tử

~~~java
static java.util.List<String> copyStrings(Object raw) {
    if (!(raw instanceof java.util.List<?> values)) {
        throw new IllegalArgumentException("Expected a list");
    }

    java.util.List<String> result = new java.util.ArrayList<>();
    for (Object item : values) {
        if (!(item instanceof String text)) {
            throw new IllegalArgumentException("Non-string element");
        }
        result.add(text);
    }
    return java.util.List.copyOf(result);
}
~~~

Ở đây **không cần unchecked cast**: `List<?>` chỉ đảm bảo “đây là danh sách”, sau đó từng phần tử được xác nhận là `String` bằng pattern. Kết quả là một danh sách mới có kiểu được bảo đảm bằng những phép kiểm tra đã thực hiện. Cách này cũng ngăn sửa danh sách nguồn làm thay đổi nội dung của bản sao bất biến.

**Phân biệt:** Cast sang `List<?>` thường được kiểm tra về kiểu danh sách; cast sang `List<String>` từ một `Object` không được JVM kiểm tra đầy đủ đối số `String`. Đừng coi hai loại cast là tương đương.

## 6. Kiểu cần kiểm tra chỉ biết ở runtime: dùng `Class<T>.cast()`

Giả sử một hàm generic nhận kiểu mong đợi qua `Class<T>`:

~~~java
static <T> T requireType(Object value, Class<T> type) {
    if (!type.isInstance(value)) {
        throw new IllegalArgumentException("Unexpected type");
    }
    return type.cast(value);
}
~~~

Ví dụ:

~~~java
String text = requireType("Java", String.class); // "Java"
Integer number = requireType(7, Integer.class); // 7
~~~

Không thể thay trực tiếp bằng `value instanceof T item`, bởi **`T` là type variable** và kiểu runtime cần kiểm tra chưa được biểu diễn như một type pattern reifiable trong mã nguồn. `type.isInstance(value)` là phép thử kiểu động, còn `type.cast(value)` là phép cast kiểm tra runtime, trả về `T` theo `Class<T>`.

`Class.cast` là **phép cast qua API**, khác cú pháp `(T) value`. Nó đặc biệt hữu ích khi kiểu đích được chuyển vào từ bên ngoài dưới dạng đối tượng `Class`, đồng thời tránh một cast unchecked trực tiếp sang `T`.

**Ranh giới:** `String.class` hoặc `Integer.class` mang thông tin lớp runtime; bạn không thể có một literal `List<String>.class` để kiểm chứng đối số generic. `Class.cast` không phá bỏ giới hạn type erasure.

**Null:** `type.isInstance(null)` trả `false`; còn `type.cast(null)` trả `null`. Nếu muốn từ chối `null`, cần quy định rõ ở API, ví dụ kiểm tra `isInstance` như trên.

## 7. Cast để chọn overload khi đối số là `null`

Đây là trường hợp cast còn có chức năng khác: **định hướng compiler chọn phương thức**, hoàn toàn độc lập với pattern matching.

~~~java
static void receive(String text) {
    System.out.println("String overload");
}

static void receive(Integer value) {
    System.out.println("Integer overload");
}
~~~

Lời gọi sau **cố ý không biên dịch**:

~~~java
receive(null); // ERROR: ambiguous — String và Integer không liên quan phân cấp.
~~~

Cách chọn overload mong muốn:

~~~java
receive((String) null);  // In: String overload
receive((Integer) null); // In: Integer overload
~~~

Ép kiểu `null` sang một kiểu tham chiếu là hợp lệ và không biến `null` thành đối tượng. Không thể dùng `null instanceof String` để chọn nhánh vì biểu thức đó luôn `false`. Cast ở đây giúp **chọn chữ ký tại compile time**, không phải kiểm tra kiểu đối tượng.

## 8. Ví dụ đầy đủ có thể biên dịch/chạy (Java 17)

Lưu tệp **`CastLessonDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CastLessonDemo {
    static void legacy(Object target) {
        if (target instanceof String) {
            String text = (String) target;
            System.out.println("Legacy=" + text.trim().toUpperCase());
        }
    }

    static void modern(Object target) {
        if (target instanceof String text) {
            System.out.println("Pattern=" + text.trim().toUpperCase());
        }
    }

    static String viaFlag(Object target) {
        boolean matches = target instanceof String;
        if (!matches) {
            return "invalid";
        }
        return ((String) target).trim();
    }

    static String viaGuard(Object target) {
        if (!(target instanceof String text)) {
            return "invalid";
        }
        return text.trim();
    }

    static <T> T requireType(Object value, Class<T> type) {
        if (!type.isInstance(value)) {
            throw new IllegalArgumentException("Wrong type");
        }
        return type.cast(value);
    }

    static List<String> copyStrings(Object input) {
        if (!(input instanceof List<?> entries)) {
            throw new IllegalArgumentException("Not a list");
        }
        List<String> result = new ArrayList<>();
        for (Object element : entries) {
            if (!(element instanceof String text)) {
                throw new IllegalArgumentException("Non-string element");
            }
            result.add(text);
        }
        return List.copyOf(result);
    }

    static void receive(String value) {
        System.out.println("String overload=" + value);
    }

    static void receive(Integer value) {
        System.out.println("Integer overload=" + value);
    }

    public static void main(String[] args) {
        Object input = "  java  ";

        legacy(input);
        modern(input);
        System.out.println("Flag=" + viaFlag(input));
        System.out.println("Guard=" + viaGuard(input));

        System.out.println("Token=" + requireType("ok", String.class));
        System.out.println("Copied=" + copyStrings(List.of("a", "b")));

        receive((String) null);

        try {
            Integer wrong = Integer.class.cast("oops");
            System.out.println(wrong);
        } catch (ClassCastException ex) {
            System.out.println("Wrong cast=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 CastLessonDemo.java
java CastLessonDemo
~~~

**Stdout chính xác:**

~~~text
Legacy=JAVA
Pattern=JAVA
Flag=java
Guard=java
Token=ok
Copied=[a, b]
String overload=null
Wrong cast=ClassCastException
~~~

**Giải thích từng kết quả:**

1. `legacy` dùng `instanceof String` kiểu cũ nên phải dùng `(String) target` để có biến `String`; `modern` dùng `instanceof String text` nên không cast.
2. `viaFlag` lưu kết quả phép thử vào boolean, rồi cast; `viaGuard` để compiler theo dõi trực tiếp pattern variable qua nhánh trả về.
3. `requireType` dùng `Class<T>.cast()` để chuyển giá trị theo một `Class<T>` truyền vào runtime.
4. `copyStrings` kiểm tra từng phần tử và tạo danh sách `List<String>` đúng kiểu; không có unchecked cast.
5. `receive((String) null)` chỉ rõ overload cần gọi, trong khi `Integer.class.cast("oops")` chứng minh một cast động không tương thích sẽ ném `ClassCastException`.

## 9. Những điều dễ nhầm

| Tình huống | Có cần cast tường minh không? | Hành động nên làm |
| --- | --- | --- |
| `if (obj instanceof String)` rồi gọi `String` API qua `obj` kiểu `Object` | **Có**, nếu giữ cú pháp cũ | `String s = (String) obj`; tốt hơn: `instanceof String s` |
| `if (obj instanceof String s)` và dùng `s` trong nhánh đúng | **Không** | Dùng `s` trực tiếp |
| `if (!(obj instanceof String s)) return;`, rồi dùng `s` | **Không** | Tận dụng flow scoping |
| Lưu `obj instanceof String` vào `boolean ok`, sau đó dùng `obj` như `String` | **Có**, với cấu trúc đó | Cast sau kiểm tra ổn định, hoặc viết lại bằng type pattern |
| API `Object` có hợp đồng trả về `String` | Có thể cần để lấy kiểu mong muốn | Cast ở boundary, kiểm chứng hợp đồng và xử lý lỗi |
| Từ `Object` muốn có `List<String>` | Cast có thể viết nhưng **unchecked** | Ưu tiên `List<?>` + kiểm tra từng phần tử |
| Kiểu được truyền vào bằng `Class<T>` | Dùng **`Class<T>.cast()`** | Kết hợp `isInstance` nếu cần trả lỗi có kiểm soát |
| Gọi overload `receive(null)` với `String` và `Integer` | **Có thể cần** cast để chọn overload | `receive((String) null)` |
| Đã có biến `String s`, dùng ngay API `String` | **Không** | Không ép kiểu lặp lại |
| Muốn chuyển `Integer 42` thành chữ `"42"` | **Không dùng downcast** | `String.valueOf(42)` |

### Lỗi phổ biến cần tránh

- **“Chỉ cần kiểm tra `instanceof` là biến cũ đổi kiểu tĩnh.”** Không: `obj` vẫn được khai báo `Object`; type pattern tạo **biến mới** đúng kiểu.
- **“Mọi cast đều an toàn vì compiler cho biên dịch.”** Không: cast tham chiếu có thể ném `ClassCastException`; cast generic còn có thể unchecked.
- **“`instanceof List<?>` chứng minh danh sách chứa String.”** Không: chỉ chứng minh đối tượng là một `List`.
- **“`@SuppressWarnings("unchecked")` sửa được kiểu dữ liệu.”** Không: annotation chỉ ẩn cảnh báo.
- **“Pattern variable chỉ sống trong cặp ngoặc nhọn ngay sau `if`.”** Không: luồng điều khiển có thể cho phép dùng sau guard clause.
- **“`null instanceof String` là true sau khi cast null thành String.”** Không: `null` không là instance của `String`; `(String) null` vẫn có giá trị `null`.
- **“Cast Object sang String là chuyển nội dung thành String.”** Không: downcast chỉ xác nhận tham chiếu có kiểu tương thích, khác `String.valueOf(...)`.
- **“Kiểm tra và cast lại một field nhiều lần luôn an toàn.”** Không: đối tượng có thể thay đổi giữa các lần đọc; ưu tiên một giá trị local rồi dùng pattern.

## 10. Tự kiểm tra

**Câu 1.** `Object o = "abc";`. Hai đoạn dưới đều biên dịch trên Java 17? Đoạn nào cần cast?

~~~java
if (o instanceof String) {
    System.out.println(((String) o).length());
}
if (o instanceof String s) {
    System.out.println(s.length());
}
~~~

**Câu 2.** Vì sao `boolean ok = o instanceof String; if (ok) { String s = o; }` không biên dịch? Sửa ít nhất bằng hai cách.

**Câu 3.** `Object raw = List.of(1, 2);`. Vì sao `(List<String>) raw` có thể biên dịch với cảnh báo nhưng `String first = ((List<String>) raw).get(0)` có thể ném lỗi khi chạy?

**Câu 4.** Trong `static <T> T require(Object o, Class<T> type)`, vì sao `o instanceof T s` không phải cách kiểm tra hợp lệ? Thay bằng API nào?

**Câu 5.** Tại sao với hai overload `f(String)` và `f(Integer)`, lời gọi `f(null)` mơ hồ và `f((String) null)` lại giải quyết được?

**Câu 6.** Phân tích các cách sau: `String s = (String) obj`, `if (obj instanceof String s)`, `String.valueOf(obj)`. Cách nào kiểm tra và tạo biến kiểu String nếu match? Cách nào có thể ném `ClassCastException`? Cách nào tạo biểu diễn văn bản dù `obj` không là String?

**Đáp án gợi ý:**

1. Cả hai đều biên dịch nếu `o` có kiểu tĩnh `Object`; đoạn đầu cast vì `instanceof` chỉ kiểm tra, đoạn hai dùng biến `s` của pattern.
2. `o` vẫn có kiểu tĩnh `Object`. Cách 1: `String s = (String) o` sau kiểm tra; cách 2: viết lại `if (o instanceof String s) { ... }`.
3. Runtime chỉ xác nhận đối tượng là một `List`; đối số phần tử `String` bị erasure. Khi lấy `Integer` như `String` sẽ lỗi.
4. `T` là type variable không reifiable cho type pattern thông thường. Sử dụng `type.isInstance(o)` và `type.cast(o)`.
5. `null` tương thích với cả hai kiểu tham chiếu không có quan hệ subtype phù hợp; cast làm rõ kiểu đối số mà compiler dùng chọn overload.
6. Cast `(String) obj` có thể ném `ClassCastException`; `instanceof String s` kiểm tra có điều kiện và cung cấp biến khi thành công; `String.valueOf(obj)` tạo văn bản thông qua logic chuyển đổi chuỗi.

## Tài liệu tham khảo

- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): cú pháp truyền thống, type pattern, phạm vi biến theo luồng điều khiển.
- [Java Language Specification 17 — `15.20.2, The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): tính hợp lệ và cách đánh giá phép thử.
- [Java Language Specification 17 — `5.5, Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): chuyển đổi tường minh, checked/unchecked cast và ngoại lệ runtime.
- [Java SE 17 API — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isInstance(Object)`, `cast(Object)` và hợp đồng xử lý `null`.
