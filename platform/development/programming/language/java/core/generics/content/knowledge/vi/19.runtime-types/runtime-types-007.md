# Giới hạn của mẫu kiểu và ép kiểu sau xóa kiểu trong Java

Java cho phép kiểm tra kiểu lúc chạy bằng `instanceof`, ép kiểu bằng cast và từ Java 16 có **pattern matching for `instanceof`** để kết hợp phép kiểm tra với việc tạo biến đã được thu hẹp kiểu. Nhưng Java Generics thông thường dùng **type erasure (xóa kiểu)**: JVM thường không lưu đối số kiểu cụ thể như `String` trong runtime class của một `ArrayList<String>`.

Vì vậy, có sự khác biệt rất lớn giữa hai câu hỏi:

- “Giá trị này có phải một `List`?” — có thể kiểm tra trực tiếp bằng `instanceof List<?>`.
- “Giá trị này có phải một `List<String>` chứa toàn phần tử `String`?” — không thể kết luận chỉ từ phép `instanceof` trên một giá trị `Object`; cần hợp đồng dữ liệu an toàn hoặc kiểm tra phần tử.

Đặc biệt, **ép kiểu `(List<String>) value` không phải phép xác thực mọi phần tử**. Với nguồn dữ liệu không đáng tin, ép kiểu unchecked có thể thành công trước rồi phát sinh `ClassCastException` ở chỗ đọc phần tử.

## 1. Phép `instanceof` kiểm tra được điều gì?

Toán tử `instanceof` dựa trên thông tin kiểu còn có thể kiểm tra tại runtime. Khi giá trị là một đối tượng chứa thông tin runtime class, ta thường kiểm tra được lớp hoặc interface không cần type argument cụ thể:

```java
// Các câu lệnh minh họa; import java.util.List.
Object text = "Java";
Object items = List.of("An", 42);

boolean a = text instanceof String;  // true
boolean b = items instanceof List<?>; // true
boolean c = items instanceof List;    // true, nhưng List là raw type
```

Với `items`, hai biểu thức kiểm tra `List` trả `true` vì đối tượng thực là một danh sách. Điều này **không chứng minh phần tử thứ hai là `String`**; trong ví dụ đó phần tử thứ hai là `Integer`.

Kiểu `List<?>` là một **reifiable type** vì wildcard `?` không bị ràng buộc: kiểm tra runtime chỉ cần xác nhận đây là một `List`. Trong khi đó, `List<String>` đòi biết đối số kiểu cụ thể `String`, thứ mà đối tượng `List` thông thường không mang như một class runtime riêng.

Một kiểu reifiable không có nghĩa dữ liệu luôn an toàn. Raw `List` cũng reifiable, nhưng gọi `raw.add(42)` có thể gây heap pollution nếu cùng danh sách đang được mã khác sử dụng dưới kiểu `List<String>`.

## 2. Pattern matching for `instanceof` bổ sung điều gì?

Trước khi có pattern matching, lập trình viên thường viết:

```java
// Snippet đặt trong một phương thức có biến Object value.
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Từ Java 16 (và dùng bình thường trên Java 17+), có thể viết:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

`String text` là **type pattern**. Khi phép kiểm tra thành công, Java tạo một pattern variable `text` đã có kiểu `String`, nhờ đó tránh phải cast lặp lại.

Mẫu kiểu chỉ tạo biến khi **phép kiểm tra tương ứng hợp lệ**. Nó không thêm năng lực đọc type argument generic bị xóa. Chẳng hạn:

```java
Object value = java.util.List.of("An");

if (value instanceof java.util.List<?> items) {
    System.out.println(items.size()); // Hợp lệ
}

// Không hợp lệ với Object value:
// if (value instanceof java.util.List<String> items) { ... }
```

Trong nhánh kiểm tra `List<?> items`, compiler biết `items` là `List<?>`; mỗi `items.get(i)` chỉ được dùng như `Object` nếu chưa kiểm tra thêm. Nó **không suy ra `items` là `List<String>`**.

## 3. Vì sao mẫu `List<String>` không dùng như mẫu `List<?>`?

Với một giá trị kiểu `Object`, đoạn sau không thể dùng làm phép kiểm tra phần tử runtime:

```java
Object input = java.util.List.of("A", "B");

// KHÔNG BIÊN DỊCH trong ngữ cảnh này:
// if (input instanceof java.util.List<String> strings) {
//     System.out.println(strings.get(0));
// }
```

Lý do: `List<String>` là **non-reifiable parameterized type**. JVM không có đủ thông tin từ riêng runtime class `List` để xác định mọi phần tử tuân thủ `String`. Java sẽ không chấp nhận một kiểm tra `instanceof` như thể có thể kiểm tra điều đó.

Cách viết hợp lệ:

```java
if (input instanceof java.util.List<?> values) {
    for (Object element : values) {
        if (element instanceof String text) {
            System.out.println(text.toUpperCase(java.util.Locale.ROOT));
        } else {
            System.out.println("Phần tử không phải String");
        }
    }
}
```

Lúc này có **hai tầng kiểm tra**: tầng ngoài chứng minh là `List`; tầng trong dùng `instanceof String` cho từng giá trị. Đối số `String` của kiểu generic ban đầu không được JVM tự khôi phục.

### Một sắc thái quan trọng của `instanceof` từ Java 16

Với một biểu thức có **kiểu tĩnh đã biết rất cụ thể**, các quy tắc tương thích kiểu khi biên dịch có thể cho phép một số cách dùng `instanceof` liên quan kiểu tham số hóa non-reifiable. Điều đó không tạo phép kiểm tra type argument mới ở runtime.

Do đó, không nên ghi nhớ quá mức rằng “mọi cú pháp `instanceof List<String>` đều sai trong mọi ngữ cảnh”. Quy tắc thực hành chính xác cho việc kiểm tra một giá trị `Object` chưa biết là: **dùng kiểu reifiable như `List<?>` rồi xác minh nội dung nếu cần**. Với type pattern, compiler còn áp dụng quy tắc riêng về tính tương thích và pattern variable.

## 4. Pattern variable có phạm vi sử dụng theo luồng điều khiển

Biến được khai báo trong type pattern không có phạm vi giống biến local bình thường. Nó **chỉ được dùng khi compiler chứng minh phép kiểm tra pattern đã thành công**.

### 4.1. Nhánh `if`

```java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text.length()); // text đã được xác nhận là String
    }
    // System.out.println(text); // Không hợp lệ: text không có phạm vi tại đây
}
```

### 4.2. Kết hợp với `&&`

```java
static boolean nonEmptyList(Object input) {
    return input instanceof java.util.List<?> values
            && !values.isEmpty();
}
```

Vế phải `&&` chỉ chạy khi vế trái `true`, nên biến pattern `values` chắc chắn đã được gán và có thể dùng ở vế phải.

Không được tự thay `&&` bằng `||` rồi dùng biến ở vế phải:

```java
// KHÔNG BIÊN DỊCH:
// return input instanceof java.util.List<?> values
//         || values.isEmpty();
```

Khi toán tử `||` đánh giá vế phải, vế trái đã `false`; biến pattern chưa có bảo đảm được tạo.

### 4.3. Guard clause với `!` và `return`

```java
static int listSizeOrZero(Object input) {
    if (!(input instanceof java.util.List<?> values)) {
        return 0;
    }
    return values.size(); // Hợp lệ vì đường đến đây bảo đảm pattern khớp
}
```

Kiểu kiểm tra này hữu ích khi cần kiểm tra dữ liệu ở đầu hàm rồi sử dụng biến đã thu hẹp ở phần còn lại.

### 4.4. `null` không khớp type pattern

```java
Object input = null;
boolean matched = input instanceof String; // false
```

Pattern matching không tự xử lý `null` theo kiểu một `String` hợp lệ. Nếu `null` là giá trị được phép về nghiệp vụ, cần một nhánh hoặc chính sách riêng.

### 4.5. Pattern hiển nhiên đúng cũng có thể bị từ chối

Nếu biểu thức đã có kiểu tĩnh là subtype của pattern type, một type pattern như `String s; if (s instanceof String text)` không được phép vì phép thu hẹp kiểu đã hiển nhiên ở nguồn. Điều này là quy tắc **tính tương thích của pattern tại compile time**, không liên quan đến việc JVM quên mất `String`.

## 5. Ép kiểu sau erasure: phần kiểm tra được và phần không kiểm tra được

Một cast Java có thể là **checked cast** hoặc **unchecked cast**, tùy việc JVM có đủ thông tin để kiểm tra toàn bộ kiểu đích hay không.

Ví dụ checked cast của một class reifiable:

```java
Object input = "Java";
String text = (String) input; // Runtime kiểm tra được String
```

Nếu `input` thực tế là `Integer`, cast sang `String` sẽ ném `ClassCastException`.

Nhưng với một kiểu generic cụ thể:

```java
Object input = java.util.List.of("Java", 42);

// Đây là UNCHECKED cast, compiler sẽ cảnh báo nếu không suppress.
java.util.List<String> names = (java.util.List<String>) input;
```

Cast này không thể xác minh mọi phần tử thành `String`; nó chỉ kiểm tra được phần thích hợp của kiểu runtime, ví dụ đối tượng có là `List` hay không. Dữ liệu sai kiểu có thể nằm trong list và chưa gây lỗi ngay tại câu lệnh cast.

Sau đó:

```java
// Snippet tiếp tục:
String second = names.get(1); // ClassCastException khi Integer bị xem là String
```

Compiler xem kết quả `get` của `List<String>` là `String`. Bytecode sau erasure có thể chứa thao tác `checkcast java/lang/String` ở vị trí tiêu thụ kết quả. Vì thế **địa điểm lỗi runtime có thể khác với vị trí cast unchecked ban đầu**.

Cần phân biệt ba điều:

1. Cast tới `String` có thể xác minh kiểu đối tượng ngay tại thời điểm cast.
2. Cast tới `List<String>` không xác minh phần `String` trong type argument theo cách đó.
3. `List<?> values = (List<?>) input;` có kiểu đích reifiable: cast kiểm tra được đối tượng có phải `List`, nhưng vẫn không xác minh loại của từng phần tử.

Điểm (3) thường là cách làm tốt khi tiếp nhận một danh sách từ kiểu `Object` mà chưa biết kiểu phần tử.

## 6. Chương trình Java 17+ chạy được: pattern và unchecked cast

Lưu toàn bộ mã sau thành **`PatternErasureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PatternErasureDemo {
    static boolean allStrings(Object input) {
        if (!(input instanceof List<?> values)) {
            return false;
        }
        for (Object value : values) {
            if (!(value instanceof String)) {
                return false;
            }
        }
        return true;
    }

    static List<String> checkedCopy(Object input) {
        if (!(input instanceof List<?> values)) {
            throw new IllegalArgumentException("Not a list");
        }

        List<String> result = new ArrayList<>();
        for (int i = 0; i < values.size(); i++) {
            Object value = values.get(i);
            if (!(value instanceof String s)) {
                throw new IllegalArgumentException("Bad element at " + i);
            }
            result.add(s);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        Object mixed = new ArrayList<>(List.of("Java", 42));

        System.out.println("Outer List<?>: "
                + (mixed instanceof List<?>));
        System.out.println("All Strings: " + allStrings(mixed));
        System.out.println("Null is List<?>: " + (null instanceof List<?>));

        if (mixed instanceof List<?> values) {
            System.out.println("List size: " + values.size());
            Object first = values.get(0);
            System.out.println("First is String: "
                    + (first instanceof String));
        }

        try {
            @SuppressWarnings("unchecked")
            List<String> assumed = (List<String>) mixed;
            String second = assumed.get(1);
            System.out.println(second);
        } catch (ClassCastException exception) {
            System.out.println("Unchecked read: ClassCastException");
        }

        try {
            checkedCopy(mixed);
        } catch (IllegalArgumentException exception) {
            System.out.println("Validation: " + exception.getMessage());
        }

        System.out.println("Checked copy: "
                + checkedCopy(List.of("An", "Binh")));
        System.out.println("Empty all Strings: "
                + allStrings(List.of()));

        try {
            String.class.cast(42);
        } catch (ClassCastException exception) {
            System.out.println("Class token: ClassCastException");
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 -Xlint:unchecked PatternErasureDemo.java
java PatternErasureDemo
```

Standard output:

```text
Outer List<?>: true
All Strings: false
Null is List<?>: false
List size: 2
First is String: true
Unchecked read: ClassCastException
Validation: Bad element at 1
Checked copy: [An, Binh]
Empty all Strings: true
Class token: ClassCastException
```

Bài thử cho thấy:

- `instanceof List<?>` xác nhận lớp ngoài mà không khẳng định mọi phần tử là `String`.
- Pattern variable `values` có kiểu `List<?>`, vì vậy cần đọc phần tử thành `Object` trước khi kiểm tra `instanceof String`.
- Ép `mixed` thành `List<String>` không tự quét danh sách; khi đọc `Integer` qua kiểu `String`, `ClassCastException` mới xuất hiện.
- `checkedCopy` thực hiện kiểm tra từng phần tử, báo lỗi tại vị trí 1 nếu sai kiểu, và trả một `List<String>` mới khi toàn bộ dữ liệu thỏa.
- `allStrings(List.of())` là `true` theo logic “mọi phần tử đều là String” của tập rỗng. Nếu yêu cầu dữ liệu không rỗng, cần kiểm tra thêm.
- `String.class.cast(42)` kiểm tra được class runtime cụ thể và ném `ClassCastException` ngay lúc cast.

Tệp có một lớp `public` trùng tên file, dùng những API và cú pháp có trong Java 17. Lệnh `-Xlint:unchecked` hữu ích khi chủ động thử các cast không được suppress; trong ví dụ chạy, `@SuppressWarnings("unchecked")` chỉ được dùng ở đúng khai báo cố ý không an toàn để tập trung minh họa hành vi.

## 7. Vì sao `Class<T>` không tự giải quyết được generic lồng nhau?

Nếu cần kiểm tra một phần tử theo class runtime, `Class<T>` là cơ chế hữu ích:

```java
static <T> T castOne(Object input, Class<T> type) {
    return type.cast(input);
}

// castOne("Java", String.class) -> "Java"
// castOne(42, String.class) -> ném ClassCastException
```

`String.class` mô tả class `String` tại runtime. Nhưng không có class literal Java `List<String>.class` để kiểm tra đối số `String` trong một collection một cách tương đương.

Có thể dùng `List.class.isInstance(input)` để xác nhận lớp ngoài, và `String.class.isInstance(item)` để xác nhận từng phần tử. Với generic lồng nhau như `List<List<String>>`, phải kiểm tra lần lượt danh sách ngoài, các danh sách con và các phần tử ở lá.

Ngoài ra, `Class<T>` thường kiểm tra theo **tính tương thích của class**. `Number.class.isInstance(Integer.valueOf(42))` là `true`, dù runtime class cụ thể của giá trị là `Integer`. Nếu hợp đồng yêu cầu **đúng chính xác một class**, cần tự quy định chính sách chặt hơn, thay vì mặc định cho mọi subclass là sai.

## 8. Vấn đề với type variable `T` trong pattern và cast

Một phương thức generic không thể trực tiếp dùng type variable như class runtime để kiểm tra:

```java
// Snippet minh họa phương thức generic KHÔNG HỢP LỆ:
static <T> boolean isType(Object input) {
    // return input instanceof T; // Không thể kiểm tra type variable T
    return false;
}
```

Câu `return false` chỉ giúp snippet có thân phương thức hợp lệ; dòng quan trọng là lệnh `instanceof T` bị chú thích vì sai. Dù `T extends Number`, điều đó không cho biết `T` là `Integer`, `Double` hay một subtype khác khi chạy.

Mẫu `input instanceof T item` cũng không giúp lấy lại kiểu đã bị xóa. Nếu cần kiểm tra class của giá trị do caller yêu cầu, hãy truyền một token:

```java
static <T> boolean matches(Object input, Class<T> type) {
    return type.isInstance(input);
}
```

Token này giải quyết kiểm tra **một class cụ thể**. Đừng suy ra nó đại diện được một type argument lồng nhau như `Map<String, List<Integer>>`.

Tương tự, một cast sang `T` trong mã generic có thể chỉ được kiểm tra theo bound đã xóa hoặc trở thành unchecked trong những tình huống nhất định. Nó không phải bằng chứng độc lập rằng đối tượng thỏa mọi ràng buộc kiểu mà caller suy luận được ở cấp mã nguồn.

## 9. Raw type và heap pollution làm cast càng dễ đánh lừa

Generic bình thường ngăn nhiều lỗi lúc biên dịch:

```java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("An");
// names.add(42); // Lỗi biên dịch
```

Nhưng một raw alias có thể ghi dữ liệu không tương thích:

```java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List raw = names;
raw.add(42); // Unchecked warning
// String s = names.get(0); // Có thể ném ClassCastException
```

Khi đối tượng được dùng dưới kiểu `List<String>` nhưng chứa `Integer`, ta có **heap pollution**. Việc `names` ở nguồn trông đúng generic không bảo đảm mọi phần tử mãi mãi đúng nếu có đường truy cập không an toàn.

Cũng không nên nghĩ rằng cast `(List<String>) raw` sẽ sửa heap pollution. Cast ấy có thể không ném lỗi ngay, vì runtime không xác minh tham số `String` của list. Muốn khôi phục tính đáng tin, cần kiểm tra nội dung rồi sao chép/chuẩn hóa dữ liệu vào một collection mới.

### Cảnh báo unchecked nói gì?

`unchecked` nghĩa là **compiler không thể chứng minh đầy đủ an toàn kiểu** của phép chuyển hoặc lời gọi. Nó là cảnh báo hữu ích, không nhất thiết là lỗi cú pháp.

Các hướng xử lý thường là:

1. Thay raw `List` bằng `List<?>` nếu chỉ đọc hoặc cần kiểm tra cấu trúc.
2. Dùng kiểu tham số hóa rõ ràng tại API nhận/trả dữ liệu.
3. Duyệt, kiểm tra và chuyển từng phần tử khi đọc dữ liệu chưa đáng tin.
4. Thu hẹp phạm vi `@SuppressWarnings("unchecked")` vào đoạn được chứng minh an toàn và giải thích invariant.
5. Tránh cast unchecked dây chuyền làm các tầng API sau hiểu sai tính an toàn dữ liệu.

## 10. Khi nào có thể chuyển từ `List<?>` sang `List<String>`?

Sau khi kiểm tra:

```java
Object input = java.util.List.of("An", "Binh");
if (input instanceof java.util.List<?> values) {
    boolean allStrings = values.stream()
            .allMatch(String.class::isInstance);
    // values vẫn có kiểu tĩnh List<?> dù allStrings là true.
}
```

Compiler Java **không tự nâng kiểu** từ `List<?>` thành `List<String>` chỉ vì một boolean predicate đã trả `true`. Có hai phương án đáng cân nhắc:

- Nếu cần trả về `List<String>` có bảo đảm, hãy kiểm tra **từng phần tử** rồi thêm vào một `ArrayList<String>` mới. Kết quả có kiểu tĩnh đúng, không cần unchecked cast; có thể dùng `List.copyOf` nếu muốn collection kết quả không thể sửa cấu trúc.
- Nếu chỉ cần đọc mà không cần khẳng định toàn bộ phần tử, giữ `List<?>` và kiểm tra từng giá trị lúc sử dụng.

Ngay cả khi tất cả phần tử đang là String, một danh sách **mutable** có thể bị thay đổi qua alias khác sau lúc kiểm tra. Vì vậy, kiểm tra rồi cast tham chiếu gốc sang `List<String>` có thể không an toàn nếu người khác còn sửa danh sách. Một bản sao sau validation giúp tách cấu trúc kết quả khỏi nguồn, nhưng việc tạo snapshot nhất quán vẫn đòi hỏi kiểm soát concurrent mutation trong thời gian duyệt.

### Trường hợp `null`

`String.class.isInstance(null)` là `false`, và `null instanceof String` cũng là `false`. Vì vậy, validator trong ví dụ chạy coi `null` là không hợp lệ.

Một `List<String>` nói chung **không mặc nhiên cấm null**: Java type parameter không phải non-null type annotation. Nếu nghiệp vụ cho phép null, phải mô tả predicate riêng như `value == null || value instanceof String`; đồng thời nhớ `List.copyOf` từ chối phần tử null.

## 11. Tại sao `List<?>[]` có thể tạo nhưng `List<String>[]` không?

Mảng Java biết **runtime component type**, trong khi generic element type `List<String>` không reifiable. Vì thế:

```java
// Hợp lệ:
java.util.List<?>[] groups = new java.util.List<?>[2];
groups[0] = java.util.List.of("An");
groups[1] = java.util.List.of(42);

// Không hợp lệ:
// java.util.List<String>[] names = new java.util.List<String>[2];
```

`List<?>` là reifiable, nên array có component type phù hợp để runtime kiểm tra. Nhưng `List<String>` không reifiable, khiến tạo trực tiếp array với thành phần `List<String>` bị cấm.

Một khác biệt nổi bật:

```java
Object[] array = new String[1];
try {
    array[0] = 42;
} catch (ArrayStoreException exception) {
    System.out.println("ArrayStoreException");
}
```

Với array runtime `String[]`, JVM bắt lỗi ngay khi ghi giá trị sai loại. Với `ArrayList<String>` bị raw alias làm bẩn, lỗi có thể chỉ xuất hiện khi đọc qua cast thành `String`. Cả hai cơ chế đều liên quan kiểm tra kiểu, nhưng **loại thông tin runtime được giữ là khác nhau**.

## 12. Reflection nhìn thấy `List<String>` có mâu thuẫn với erasure không?

Không. Class file có thể chứa metadata về **khai báo generic**, ví dụ thuộc tính `Signature`. Reflection có thể đọc kiểu khai báo của trường:

```java
class FieldHolder {
    java.util.List<String> names;
}
```

Ví dụ, `FieldHolder.class.getDeclaredField("names").getGenericType()` có thể mô tả `List<String>`; trong khi `getType()` phản ánh raw interface `List`.

Thông tin về khai báo không có nghĩa rằng mọi đối tượng list gắn vào trường đều mang một runtime class riêng `List<String>`, hoặc mọi giá trị được đưa vào qua raw/unchecked code đều là `String`.

Vì vậy, nếu nhận một đối tượng chưa rõ nguồn, reflection chỉ giúp biết **hợp đồng được khai báo ở đâu đó**; việc xác minh dữ liệu thực tế vẫn cần kiểm tra tương ứng.

## 13. Những lỗi hiểu sai phổ biến

**Nhầm 1 — “Pattern matching `instanceof` đọc được type argument generic.”** Sai. Nó chỉ gắn một biến khi phép kiểm tra kiểu runtime hợp lệ; `List<?> values` không trở thành `List<String>`.

**Nhầm 2 — “Dùng `instanceof List<?>` là đủ để biết danh sách chứa toàn String.”** Sai. Nó chỉ xác nhận kiểu tổng thể của object.

**Nhầm 3 — “Ép kiểu `(List<String>)` kiểm tra từng phần tử.”** Sai. Đây có thể là unchecked cast; lỗi kiểu có thể lộ ra khi lấy phần tử thành `String`.

**Nhầm 4 — “Pattern variable sử dụng được ở mọi nơi sau `if`.”** Sai. Phạm vi phụ thuộc luồng điều khiển; `&&` và guard clause có quy tắc khác `||`.

**Nhầm 5 — “Type variable `T` là một class runtime dùng trực tiếp cho `instanceof`.”** Sai. `T` không phải reifiable type và không có `T.class` thông thường.

**Nhầm 6 — “Báo `ClassCastException` tại thời điểm cast chưa xảy ra thì dữ liệu đã đúng kiểu.”** Sai. Unchecked cast có thể không kiểm tra được type argument; dữ liệu sai chỉ bộc lộ khi dùng đến.

**Nhầm 7 — “`List<String>` không reifiable nên compiler không kiểm tra generic.”** Sai. Hệ thống kiểu generic vẫn kiểm tra tại compile time; non-reifiable nói tới khả năng kiểm tra đầy đủ tại runtime.

**Nhầm 8 — “Reflection thấy `List<String>` nên có thể ép mọi list bất kỳ sang `List<String>`.”** Sai. Metadata của khai báo khác với chứng cứ từng phần tử của object runtime.

**Nhầm 9 — “Sau khi validate toàn bộ list, mọi lần đọc tương lai đều an toàn.”** Không bảo đảm nếu list bị sửa qua alias khác. Cần kiểm soát mutation hoặc tạo snapshot/bản sao đáng tin.

## 14. Bài tập tự kiểm tra

**Câu 1.** `Object x = List.of("A", 7); x instanceof List<?>;` cho kết quả gì?

`true`. Chỉ kiểu bên ngoài được kiểm tra; `Integer` trong danh sách không làm `instanceof List<?>` thành `false`.

**Câu 2.** Với `Object x`, vì sao `x instanceof List<String> names` không phải cách kiểm tra toàn bộ phần tử?

Vì type argument `String` của `List<String>` không reifiable ở runtime theo cách kiểm tra ấy. Dùng `List<?>` và kiểm tra từng phần tử.

**Câu 3.** `Object x = List.of("A", 7); List<String> y = (List<String>) x;` có nhất thiết ném exception ngay ở cast không?

Không. Cast có thể thành công khi object là `List`; `ClassCastException` có thể chỉ xảy ra khi lấy phần tử `Integer` để dùng như `String`.

**Câu 4.** Tại sao trong `input instanceof List<?> values && !values.isEmpty()`, biến `values` được dùng trong vế phải?

Vì toán tử `&&` chỉ đánh giá vế phải khi pattern ở vế trái đã khớp, nên `values` có phạm vi hợp lệ ở đó.

**Câu 5.** `Class<String>` có cho phép kiểm tra `List<String>` toàn bộ chỉ bằng một lệnh `cast` không?

Không. `String.class` kiểm tra một đối tượng kiểu `String`; nó không mô tả đầy đủ tham số kiểu bên trong một `List` và không quét mọi phần tử.

**Câu 6.** Nếu hàm đã kiểm tra mọi phần tử `String`, tại sao `List<?> values` vẫn không tự thành `List<String>`?

Vì Java không dùng kết quả boolean của một validator bất kỳ để tự thay đổi generic type argument trong hệ thống kiểu tĩnh. Cần chuyển đổi có kiểm tra hoặc giữ kiểu wildcard.

## 15. Cách áp dụng khi viết API

Khi nhận dữ liệu, quyết định rõ **cần biết gì**:

1. Chỉ muốn biết đây là `List`: `input instanceof List<?>` là thích hợp.
2. Muốn xử lý mỗi phần tử tùy runtime class: dùng `List<?> values`, rồi pattern `element instanceof String s` hoặc pattern cho class phù hợp.
3. Muốn bảo đảm **mọi** phần tử là `String`: duyệt hết các phần tử và từ chối dữ liệu không thỏa.
4. Muốn trả `List<String>` đáng tin: kiểm tra và sao chép phần tử thành collection mới có kiểu tĩnh `List<String>`.
5. Muốn kiểm tra đối tượng kiểu `T` do caller chỉ định: dùng `Class<T>` khi `T` là class có thể được biểu diễn bằng token ấy; với generic lồng nhau, dùng schema hoặc validator cấu trúc rõ ràng.
6. Đang thấy `unchecked` warning: kiểm tra nguyên nhân và ranh giới tin cậy; không coi `@SuppressWarnings` là biện pháp làm sạch dữ liệu.

**Kết luận:** mẫu kiểu `instanceof` giúp Java viết mã kiểm tra class/interface runtime ngắn gọn và an toàn hơn, nhưng không đảo ngược **type erasure** để lấy lại đối số `T` hay `List<String>` của từng instance generic. Cast tới generic parameterized type có thể mang cảnh báo unchecked và không kiểm tra từng phần tử. Khi hợp đồng đòi một kiểu phần tử cụ thể, hãy kết hợp kiểm tra tổng thể, xác minh dữ liệu thực tế và chuyển đổi/sao chép có kiểm soát.