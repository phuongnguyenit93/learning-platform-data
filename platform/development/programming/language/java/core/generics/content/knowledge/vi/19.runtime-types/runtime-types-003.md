# Vì sao `List<String>` không có đủ thông tin kiểu lúc chạy?

## 1. Câu hỏi thực chất là “thông tin kiểu nằm ở đâu?”

Trong Java, khai báo `List<String>` cho trình biên dịch biết danh sách được **dự định chứa các phần tử `String`**. Nhờ vậy, compiler kiểm tra các thao tác thêm phần tử, các phép gán và kiểu trả về của `get()`:

```java
List<String> names = new ArrayList<>();
names.add("An");             // Hợp lệ.
String first = names.get(0); // Hợp lệ; kiểu tĩnh của get(0) là String.
names.add(42);               // Lỗi biên dịch: Integer không phải String.
```

Đây là đoạn minh họa, phải đặt trong một phương thức và import `java.util.List`, `java.util.ArrayList` nếu muốn tự biên dịch. Dòng `names.add(42)` được cố ý đưa vào để minh họa lỗi, không phải mã chạy được.

Câu hỏi xuất hiện khi ứng dụng nhận một object bất kỳ và muốn biết: **“Object này là `List<String>` hay `List<Integer>`?”** Trong trường hợp danh sách generic thông thường, câu trả lời không nằm đầy đủ trong chính object khi chương trình chạy.

Điểm cần ghi nhớ ngay:

> Java Generics thông thường dùng **type erasure** (xóa kiểu): `List<String>` và `List<Integer>` là các kiểu nguồn khác nhau để compiler kiểm tra, nhưng cả hai đều dùng cùng một kiểu `List` sau xóa đối số kiểu. `ArrayList<String>` và `ArrayList<Integer>` do cùng class `ArrayList` tạo ra không có một “nhãn” kiểu phần tử riêng gắn với từng instance.

Điều đó **không** có nghĩa Java không còn bất kỳ thông tin generic nào trong mọi class file. Thông tin khai báo generic có thể được lưu trong metadata `Signature`. Sự khác nhau giữa **thông tin khai báo của field/class/method** và **kiểu tham số của từng object ở runtime** là chìa khóa của bài học này.

## 2. Phân biệt kiểu tĩnh của biến với class runtime của object

Xét:

```java
List<String> a = new ArrayList<>();
List<Integer> b = new ArrayList<>();
```

Hai biến có các **kiểu tĩnh** khác nhau:

- `a`: `List<String>`.
- `b`: `List<Integer>`.

Trình biên dịch sẽ chấp nhận `a.add("hello")` và `b.add(100)`, nhưng từ chối `a.add(100)` và `b.add("hello")`.

Tuy nhiên, object được tạo ở vế phải của cả hai khai báo đều do **cùng class runtime `ArrayList`** tạo ra. `a.getClass()` và `b.getClass()` vì thế có thể trả về cùng một đối tượng `Class` đại diện cho `java.util.ArrayList`.

Ví dụ độc lập trong tệp **`RuntimeClassDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class RuntimeClassDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        List<Integer> scores = new ArrayList<>();

        names.add("Mai");
        scores.add(10);

        System.out.println(names.getClass() == scores.getClass());
        System.out.println(names.getClass().getName());
        System.out.println(scores.getClass().getName());
        System.out.println(names instanceof List<?>);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac RuntimeClassDemo.java
java RuntimeClassDemo
```

Stdout:

```text
true
java.util.ArrayList
java.util.ArrayList
true
```

Giải thích:

1. `getClass()` trả về class runtime thực của object, ở đây là `java.util.ArrayList`.
2. Hai biến có cùng runtime class vì cùng dùng `new ArrayList<>()`.
3. `List<?>` là kiểu kiểm tra được bằng `instanceof`: nó chỉ nói object là một `List` có đối số kiểu **chưa biết**.
4. `instanceof List<?>` **không** kiểm tra xem từng phần tử có phải `String` hay `Integer`.

Dấu `<>` ở `new ArrayList<>()` là **diamond operator**: compiler suy luận đối số kiểu từ ngữ cảnh mã nguồn. Nó không tạo ra một class runtime chuyên biệt cho `String`.

Lưu ý: hai danh sách có *implementation* khác nhau, ví dụ `ArrayList<String>` và `LinkedList<String>`, sẽ có runtime class khác nhau; đó là khác biệt **class triển khai**, không phải bằng chứng runtime về `String`.

## 3. Type erasure làm gì với `List<String>`?

Generic `List<E>` là một interface khai báo tham số kiểu `E`. Khi dùng `List<String>`, compiler thay `E` bằng `String` để kiểm tra mã nguồn. Khi sinh bytecode, Java áp dụng **xóa kiểu** theo những quy tắc xác định.

Đối với kiểu tham số hóa, erasure bỏ đối số kiểu:

| Kiểu Java ở mã nguồn | Kiểu tương ứng sau erasure |
|---|---|
| `List<String>` | `List` |
| `List<Integer>` | `List` |
| `List<?>` | `List` |
| `List<? extends Number>` | `List` |
| `ArrayList<String>` | `ArrayList` |
| `Map<String, Integer>` | `Map` |
| `List<List<String>>` | `List` |

Đối với biến kiểu (*type variable*), erasure thường là erasure của giới hạn đứng đầu:

- `<T>`: `T` bị xóa về `Object`.
- `<T extends Number>`: `T` bị xóa về `Number`.
- `<T extends Number & Comparable<T>>`: `T` bị xóa về `Number`.

Với interface `List<E>`, tham số `E` không có giới hạn tường minh, vì vậy erasure của `E` là `Object`. Khai báo phương thức như `E get(int index)` ở interface khi nhìn theo bytecode thường có kiểu trả về đã xóa là `Object`. Khi mã nguồn dùng `List<String>`, compiler biết lời gọi `get()` được kỳ vọng là `String` và có thể thêm cast tương ứng tại nơi sử dụng.

Ví dụ mô hình tinh giản:

```java
// Mô hình giải thích, KHÔNG phải mã nguồn thật của java.util.List.
interface ListModel {
    Object get(int index);
    boolean add(Object item);
}
```

Mô hình này chỉ cho thấy các vị trí chứa `E` có thể xuất hiện dưới dạng `Object` sau erasure; `List` thật còn có nhiều phương thức và các quy tắc bytecode khác. Không nên dùng nó như định nghĩa đầy đủ của Collections Framework.

### Vì sao Java chọn cách này?

Erasure giúp các thư viện generic làm việc với hệ thống class, JVM và mã Java cũ theo mô hình tương thích đã được thiết kế khi Generics được bổ sung vào ngôn ngữ. Đổi lại, generic Java thông thường **không được chuyên biệt hóa thành một class riêng cho mỗi đối số kiểu**.

Đó là lý do một instance `new ArrayList<String>()` không tự mang đủ thông tin để hỏi “Đối số generic nào đã được suy luận tại lệnh `new`?”

## 4. “Không có thông tin” không đồng nghĩa với “không kiểm tra kiểu”

Câu nói “Generics bị xóa” đôi khi bị hiểu sai thành “`List<String>` không có tác dụng”. Thực tế, phần lớn lợi ích nằm **trước và trong quá trình biên dịch**:

- Compiler từ chối truyền `Integer` vào API nhận `List<String>` nếu đường đi kiểu được kiểm tra bình thường.
- `String value = list.get(0)` được kiểm tra như lời gọi trả `String`.
- Trong một phương thức `<T>`, compiler giữ quan hệ cùng biến kiểu `T` giữa nhiều tham số và kiểu trả về.
- Wildcard như `List<?>`, `List<? extends Number>` và `List<? super Integer>` đặt thêm các giới hạn an toàn khi đọc/ghi.
- Các cast cần thiết có thể được tạo trong bytecode để duy trì ngữ nghĩa của mã đã được type-check.

Tuy nhiên, kiểm tra compile time không thể bảo vệ tuyệt đối khi chương trình đi qua **raw type**, **unchecked cast**, reflection hoặc dữ liệu bên ngoài được giải mã không an toàn. Đó là cách một object `List<String>` ở mức mã nguồn vẫn có thể chứa một phần tử không phải `String`.

## 5. Ví dụ heap pollution: danh sách sai kiểu nhưng chỉ lỗi khi đọc

Tạo tệp **`HeapPollutionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionDemo {

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void insertThroughRawType(List<String> values) {
        List raw = values;
        raw.add(99);
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("safe");

        insertThroughRawType(words);

        System.out.println(words.size());
        System.out.println(words.get(0));

        try {
            String second = words.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Chạy:

```bash
javac HeapPollutionDemo.java
java HeapPollutionDemo
```

Stdout:

```text
2
safe
ClassCastException
```

Diễn biến:

1. `words` có kiểu tĩnh `List<String>`.
2. Phương thức `insertThroughRawType` cố ý dùng raw `List` để bỏ mất đối số kiểu.
3. `raw.add(99)` thêm `Integer`; ở runtime, collection bình thường không tự kiểm tra rằng object từng được dùng qua biến `List<String>`.
4. Kích thước danh sách trở thành `2`; đọc phần tử đầu (`String`) vẫn hoạt động.
5. `words.get(1)` có kiểu tĩnh `String`; khi nhận kết quả thực `Integer`, phép chuyển kiểu cần thiết thất bại và sinh `ClassCastException`.

Đây là **heap pollution**: một biến có kiểu tham số hóa trỏ tới dữ liệu không còn phù hợp với hợp đồng kiểu của biến.

Annotation `@SuppressWarnings` chỉ được đặt trên phương thức cố ý minh họa hành vi nguy hiểm để tránh nhiễu output cảnh báo trong ví dụ. Trong ứng dụng thật, **không nên dùng raw type hoặc suppress unchecked warning tùy tiện**. Bảo vệ ranh giới dữ liệu đúng cách quan trọng hơn việc làm mất cảnh báo.

Bài học quan trọng: Java không bắt buộc lỗi xuất hiện ngay tại `raw.add(99)`. Việc dùng `String` ở nơi đọc mới có thể làm cast thất bại.

## 6. Vì sao không viết được `instanceof List<String>`?

Giả sử một API nhận:

```java
Object input = new ArrayList<String>();
```

Mục tiêu là kiểm tra chính xác liệu `input` có phải danh sách các chuỗi hay không. Thử viết:

```java
// Cố ý không hợp lệ trong Java:
boolean isStringList = input instanceof List<String>;
```

Compiler từ chối dạng kiểm tra này vì `List<String>` **không phải kiểu reifiable**: JVM không thể xác minh đầy đủ đối số generic `String` chỉ từ runtime type của object.

Các biểu thức hợp lệ có ý nghĩa khác:

```java
boolean a = input instanceof List;
boolean b = input instanceof List<?>;
```

Chúng có thể xác minh object thuộc `List`, nhưng không xác minh loại phần tử.

Từ Java 16 trở đi, pattern matching `instanceof` có thể dùng với `List<?>`:

```java
if (input instanceof List<?> values) {
    System.out.println(values.size());
}
```

Ở đây biến pattern `values` có kiểu `List<?>`. Khi đọc `values.get(0)`, compiler chỉ có thể dựa vào những điều đã biết về một đối số kiểu chưa xác định; với `List<?>`, kết quả an toàn để nhận là `Object`.

### Kiểu reifiable là gì?

Một kiểu là **reifiable** khi biểu diễn kiểu của nó đủ hiện diện tại runtime theo các quy tắc của ngôn ngữ. Ví dụ thường gặp:

- `String`, `Integer` và các class/interface không tham số hóa.
- `int`, `boolean` và các primitive types.
- Raw `List`.
- `List<?>`, `Map<?, ?>`: tham số hóa chỉ dùng wildcard không giới hạn ở các vị trí đối số kiểu thích hợp.
- Mảng có kiểu phần tử reifiable, chẳng hạn `String[]` hoặc `List<?>[]`.

Ngược lại, `List<String>`, `List<Integer>`, `List<? extends Number>` không phải kiểu reifiable theo nghĩa có thể kiểm tra đầy đủ cấu trúc generic tại runtime.

Hãy phân biệt **kiểm tra loại container** với **kiểm tra từng phần tử**. `input instanceof List<?>` chỉ thực hiện việc đầu tiên.

## 7. Kiểm tra dữ liệu runtime đúng cách với `List<?>`

Nếu chương trình nhận một object từ plugin, thư viện cũ hoặc một API kém kiểu hóa, và nghiệp vụ yêu cầu **mọi phần tử đều là `String`**, ta có thể kiểm tra **nội dung thực tế**.

Tạo tệp **`CheckListElementsDemo.java`**:

```java
import java.util.List;

public class CheckListElementsDemo {

    static boolean containsOnlyStrings(Object input) {
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

    public static void main(String[] args) {
        System.out.println(containsOnlyStrings(List.of("An", "Binh")));
        System.out.println(containsOnlyStrings(List.of("An", 10)));
        System.out.println(containsOnlyStrings(List.of()));
        System.out.println(containsOnlyStrings("not a list"));
    }
}
```

Biên dịch và chạy:

```bash
javac CheckListElementsDemo.java
java CheckListElementsDemo
```

Stdout:

```text
true
false
true
false
```

Ý nghĩa của ví dụ:

- Nếu không phải `List<?>`, trả `false`.
- Nếu là `List<?>`, duyệt từng phần tử và kiểm tra bằng `instanceof String`.
- Danh sách rỗng trả `true` vì không có phần tử nào vi phạm quy tắc “mọi phần tử đều là String”.

**Cảnh báo về ý nghĩa:** Hàm trên kiểm tra *nội dung đang có*, không chứng minh danh sách được **khai báo** là `List<String>`. Một `List<Object>` chứa toàn chuỗi cũng đạt kiểm tra. Danh sách rỗng không có phần tử để suy ra bất kỳ type argument nào.

Ví dụ này xem `null` là không hợp lệ, bởi `null instanceof String` là `false`. Nếu bài toán cho phép phần tử `null`, phải thay điều kiện thành `value != null && !(value instanceof String)` để chỉ bác bỏ những phần tử khác `String`, đồng thời giữ chính sách nhất quán ở các lớp xử lý khác.

Thêm nữa, kiểm tra trên một collection **đang bị thread khác chỉnh sửa** không bảo đảm nội dung không thay đổi ngay sau đó. Nếu cần dữ liệu ổn định, có thể tạo một bản sao đã được xác minh, đồng bộ hoặc áp dụng hợp đồng bất biến phù hợp.

## 8. Tạo bản sao được kiểm tra bằng `Class<T>`

Đối với các trường hợp biết phần tử mong đợi là một **class runtime cụ thể**, có thể truyền `Class<T>` vào API và tạo một bản sao đã kiểm tra.

Tệp **`CheckedCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CheckedCopyDemo {

    static <T> List<T> checkedCopy(List<?> source, Class<T> type) {
        List<T> result = new ArrayList<>();

        for (Object element : source) {
            result.add(type.cast(element));
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> words = checkedCopy(
                List.of("red", "blue"), String.class);
        System.out.println(words);

        try {
            checkedCopy(List.of("red", 3), String.class);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CheckedCopyDemo.java
java CheckedCopyDemo
```

Stdout:

```text
[red, blue]
ClassCastException
```

Ở đây:

1. `source` là `List<?>`, nên không giả định trước loại phần tử.
2. `type.cast(element)` kiểm tra runtime rằng từng phần tử phù hợp `Class<T>`.
3. Các phần tử qua kiểm tra được đưa vào `List<T>` mới.
4. `List.copyOf` tạo danh sách không thể chỉnh sửa qua API chuẩn và từ chối `null`; trong ví dụ đầu vào không chứa `null`.

Đây là cách chuyển một ranh giới nhận dữ liệu chưa biết kiểu thành một kết quả có hợp đồng rõ ràng, **dựa trên việc xác minh thực tế**.

Nhưng `Class<T>` chỉ mô tả một class hoặc array class có thể có `Class` token. Bạn không thể cung cấp `List<String>.class` như một `Class<List<String>>` cụ thể: parameterized type này không có class literal riêng. Khi cần mô tả các kiểu lồng nhau như `List<List<String>>` hay `Map<String, List<Integer>>`, ta cần biểu diễn kiểu ở mức `java.lang.reflect.Type` hoặc một schema phù hợp, và vẫn phải kiểm tra dữ liệu theo cấu trúc tương ứng.

## 9. Vì sao `List<String>.class` không tồn tại?

Java cho phép các class literal như:

```java
String.class
Integer.class
java.util.List.class
String[].class
```

Nhưng không cho:

```java
// Cố ý không hợp lệ:
List<String>.class
List<Integer>.class
```

Nguyên nhân trực tiếp là `List<String>` và `List<Integer>` **không có hai đối tượng `Class` runtime tách biệt**. `List.class` đại diện cho raw `java.util.List`, chứ không phải một phần tử kiểu `String`.

Đó cũng là lý do đoạn sau là sai về mặt mô hình:

```java
// Cố ý không hợp lệ:
Class<List<String>> listClass = List<String>.class;
```

Một `Class<?>` biểu thị runtime class, còn `java.lang.reflect.Type` có thể biểu thị cả cấu trúc generic **được khai báo**. Hai khái niệm này liên quan nhưng khác phạm vi thông tin.

Không nên cố sửa bằng cast unchecked một `Class<?>` để giả vờ có `Class<List<String>>`: kiểu biến có vẻ “đẹp” hơn không tạo kiểm tra runtime cho những đối số generic đã bị xóa.

## 10. Generic `Signature`: tại sao reflection đôi khi vẫn thấy `List<String>`?

Java class file có thể lưu metadata generic trong thuộc tính **`Signature`**. Metadata này ghi cấu trúc **khai báo generic** trên class, field hoặc method khi thích hợp.

Ví dụ:

```java
import java.util.List;

class Catalog {
    List<String> names;
    List<Integer> counts;
}
```

Compiler có thể ghi:

- `names`: field descriptor `Ljava/util/List;`, generic signature `Ljava/util/List<Ljava/lang/String;>;`.
- `counts`: field descriptor `Ljava/util/List;`, generic signature `Ljava/util/List<Ljava/lang/Integer;>;`.

**Descriptor** biểu diễn kiểu JVM dùng cho field. **Signature** giữ thông tin `String` hoặc `Integer` từ khai báo của field. Reflection có thể đọc Signature bằng `Field.getGenericType()`.

Đây không phải “đối tượng List tự nhớ nó chứa gì”. Nếu bạn gán cùng một object `ArrayList` cho một field khai báo `List<String>` (qua lời gán an toàn hoặc mã unchecked), reflection trên field sẽ thấy **khai báo của field**, không đọc danh sách để suy ra kiểu từ từng phần tử.

### Ví dụ reflection trên hai field

Tạo tệp **`FieldMetadataDemo.java`**:

```java
import java.lang.reflect.Field;
import java.util.List;

public class FieldMetadataDemo {

    static class Registry {
        List<String> names;
        List<Integer> numbers;
    }

    public static void main(String[] args) throws Exception {
        Field names = Registry.class.getDeclaredField("names");
        Field numbers = Registry.class.getDeclaredField("numbers");

        System.out.println(names.getType().getTypeName());
        System.out.println(names.getGenericType().getTypeName());
        System.out.println(numbers.getType().getTypeName());
        System.out.println(numbers.getGenericType().getTypeName());
    }
}
```

Chạy:

```bash
javac FieldMetadataDemo.java
java FieldMetadataDemo
```

Stdout:

```text
java.util.List
java.util.List<java.lang.String>
java.util.List
java.util.List<java.lang.Integer>
```

`getType()` cho `Class<?>` tương ứng với kiểu đã xóa. `getGenericType()` cho `Type`, có khả năng diễn đạt cấu trúc generic trong khai báo. Cả hai cùng trả lời những câu hỏi đúng trong **bối cảnh khác nhau**.

Ví dụ này có thể chạy khi chưa hề tạo instance `Registry` hay instance `List`, chứng minh metadata nằm trên **khai báo field của class**, không phụ thuộc vào giá trị danh sách tại runtime.

## 11. Metadata superclass là thông tin khai báo, không phải nhãn của từng instance

Một subclass có thể ghi rõ đối số generic trong quan hệ kế thừa:

```java
class StringList extends java.util.ArrayList<String> {}
class GenericList<E> extends java.util.ArrayList<E> {}
```

`StringList.class.getGenericSuperclass().getTypeName()` có thể trả `java.util.ArrayList<java.lang.String>`, trong khi cùng phép đọc metadata ở `GenericList.class` trả `java.util.ArrayList<E>`. Class đầu **khai báo** String; class sau vẫn có type variable E và không tự chuyển thành Integer theo từng `new GenericList<Integer>()`.

Đó là thông tin `Signature` trong class file của **lớp con**, không phải bằng chứng những phần tử thực đã được kiểm tra. Bài chuyên về `getClass()` sẽ phân tích sâu sự khác nhau giữa class instance, subclass cố định type argument và anonymous subclass được tạo trong một generic factory.


## 12. Anonymous subclass và kỹ thuật type capture

Một số thư viện dùng **type reference/type token** bằng lớp con vô danh để giữ cấu trúc generic trong khai báo superclass. Đó là một cách chủ động tạo **class mới có khai báo** mang kiểu mong muốn.

Tạo tệp **`TypeCaptureDemo.java`**:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.List;
import java.util.Map;

public class TypeCaptureDemo {

    static abstract class TypeRef<T> {
        private final Type captured;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();

            if (!(parent instanceof ParameterizedType parameterized)) {
                throw new IllegalStateException(
                        "Subclass must declare a concrete type argument");
            }

            captured = parameterized.getActualTypeArguments()[0];
        }

        final Type type() {
            return captured;
        }
    }

    public static void main(String[] args) {
        TypeRef<List<String>> words = new TypeRef<List<String>>() {};
        TypeRef<Map<String, List<Integer>>> nested =
                new TypeRef<Map<String, List<Integer>>>() {};

        System.out.println(words.type().getTypeName());
        System.out.println(nested.type().getTypeName());
    }
}
```

Biên dịch và chạy:

```bash
javac TypeCaptureDemo.java
java TypeCaptureDemo
```

Stdout:

```text
java.util.List<java.lang.String>
java.util.Map<java.lang.String, java.util.List<java.lang.Integer>>
```

Cơ chế:

1. `TypeRef<T>` là một class generic.
2. `new TypeRef<List<String>>() {}` khai báo một **anonymous subclass** có generic superclass là `TypeRef<List<String>>`.
3. `getClass()` trong constructor cho class runtime của anonymous subclass.
4. `getGenericSuperclass()` đọc **khai báo** superclass của class vô danh.
5. `ParameterizedType.getActualTypeArguments()[0]` lấy đối số kiểu `List<String>` dưới dạng `Type`.
6. `Type.getTypeName()` trình bày cấu trúc generic có thể lồng nhiều tầng.

Đây là kỹ thuật nền tảng trong một số thư viện serialization/deserialization; một số thư viện đặt tên lớp hỗ trợ là `TypeReference` hoặc `TypeToken`.

**Giới hạn quan trọng:** Kỹ thuật này chỉ giữ thông tin **thực sự được ghi trong quan hệ khai báo superclass**. Nếu một type argument vẫn là `T` của một phương thức generic, type capture không tự biến `T` thành `String` ở runtime. Ngoài ra, type reference không tự xác thực dữ liệu JSON hoặc collection; nó chỉ cung cấp **mô tả kiểu mong đợi** cho mã khác thực hiện công việc.

Mẫu `TypeRef` trên cố tình đơn giản: nó giả định anonymous subclass trực tiếp mở rộng `TypeRef<...>`. Một framework thực tế có thể cần xử lý nhiều tầng kế thừa và ánh xạ type variables kỹ hơn.

## 13. `ParameterizedType`, `TypeVariable` và `WildcardType` không phải `Class`

Khi đọc metadata generic qua reflection, dữ liệu trả về thường có kiểu interface `java.lang.reflect.Type`. Một `Type` không nhất thiết là `Class<?>`.

Các dạng thường gặp:

| Kiểu ở khai báo | Reflection thường biểu diễn |
|---|---|
| `String` | `Class<?>` |
| `List<String>` | `ParameterizedType` |
| `T` trong `class Box<T>` | `TypeVariable<?>` |
| `? extends Number` | `WildcardType` |
| `T[]` với `T` là type variable | `GenericArrayType` |
| `String[]` | `Class<?>` |

Ví dụ đoạn mã phân tích generic field:

```java
Type type = field.getGenericType();

if (type instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();
    // Phân tích raw và từng argument theo yêu cầu ứng dụng.
}
```

Đây là **mảnh code minh họa**, cần đặt trong class/method có biến `field` kiểu `java.lang.reflect.Field` và import các kiểu reflection tương ứng.

Việc một `Type` mô tả `List<String>` **không có nghĩa** phép `type instanceof Class<?>` phải đúng. `ParameterizedType` lưu cấu trúc tham số hóa chứ không phải tạo `Class<List<String>>` mới.

Cũng không nên phân tích `type.getTypeName()` bằng cách cắt chuỗi tùy tiện: generic type có thể gồm wildcard, giới hạn, mảng, kiểu lồng và type variables. Khi viết framework, ưu tiên mô hình có cấu trúc của API Reflection.

## 14. Thông tin `List<String>` của biến cục bộ thì sao?

Câu lệnh:

```java
List<String> names = new ArrayList<>();
```

nếu nằm trong một method, giúp compiler kiểm tra kiểu **biến cục bộ** `names`. Nhưng từ một object `ArrayList`, API Reflection thông thường **không thể hỏi ngược** rằng nó từng được gán vào biến cục bộ `names` khai báo `List<String>`.

Một số class file có thể chứa metadata debug dành cho local variables, như `LocalVariableTable` hoặc `LocalVariableTypeTable` khi compiler/cấu hình ghi chúng. Dữ liệu này có thể hỗ trợ công cụ debug, nhưng:

- Không nhất thiết hiện diện trong mọi bản build.
- Gắn với vị trí/thời gian sống của biến cục bộ trong **method bytecode**, không tự gắn vào object.
- Không phải API tiêu chuẩn để đọc type argument của một object `List` khi ứng dụng chạy.
- Không nên dùng làm hợp đồng của thư viện nghiệp vụ.

Thông tin `Signature` ở **field/method/class declaration** có vai trò khác với metadata local-variable phục vụ debug. Đừng gộp chúng thành một khái niệm duy nhất “JVM luôn nhớ kiểu generic”.

## 15. Generic arrays: sự khác biệt có ích để đối chiếu

Java arrays có cơ chế runtime khác generic collections:

```java
String[] names = new String[2];
Object[] objects = names;
```

Mảng `String[]` có component type runtime là `String`, nên JVM có thể kiểm tra phép gán phần tử. Với generic `List<String>`, không có runtime component class riêng cho `String` trong `ArrayList` thông thường.

Tạo tệp **`ArrayVsGenericDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ArrayVsGenericDemo {
    public static void main(String[] args) {
        String[] names = new String[2];
        Object[] objects = names;

        try {
            objects[0] = 123;
        } catch (ArrayStoreException ex) {
            System.out.println("ArrayStoreException");
        }

        List<String> words = new ArrayList<>();
        words.add("ok");

        System.out.println(names.getClass().getComponentType().getName());
        System.out.println(words.getClass().getName());
    }
}
```

Biên dịch và chạy:

```bash
javac ArrayVsGenericDemo.java
java ArrayVsGenericDemo
```

Stdout:

```text
ArrayStoreException
java.lang.String
java.util.ArrayList
```

Giải thích:

- `String[]` là mảng có component type reifiable. Nếu một tham chiếu `Object[]` thực sự trỏ tới `String[]`, nạp `Integer` vào mảng sẽ bị `ArrayStoreException`.
- `ArrayList<String>` vẫn chỉ có runtime class là `ArrayList`. Danh sách không dùng kiểu phần tử generic của biến để kiểm tra `add(...)` bằng một runtime component type tương tự mảng.

Đó cũng là một phần lý do Java **cấm trực tiếp tạo mảng của kiểu generic không reifiable** như:

```java
// Cố ý không hợp lệ:
List<String>[] array = new List<String>[10];
```

Sự kết hợp giữa tính hiệp biến (*covariance*) của mảng và cơ chế erasure của generic có thể tạo vấn đề an toàn kiểu. Nên ưu tiên dùng `List<List<String>>` hoặc một cấu trúc phù hợp thay vì tìm cách lách giới hạn mảng generic bằng các unchecked casts.

## 16. `Collections.checkedList` có giải quyết hết bài toán không?

Java cung cấp các checked collection wrappers như `Collections.checkedList(List<E>, Class<E>)`. Wrapper này thực hiện một phần kiểm tra kiểu **ở runtime khi thao tác thêm/sửa phần tử đi qua wrapper**.

Ví dụ **`CheckedListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CheckedListDemo {
    public static void main(String[] args) {
        List<String> checked =
                Collections.checkedList(new ArrayList<>(), String.class);

        checked.add("safe");
        System.out.println(checked);

        try {
            @SuppressWarnings({"rawtypes", "unchecked"})
            List raw = checked;
            raw.add(42);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }

        System.out.println(checked);
    }
}
```

Chạy:

```bash
javac CheckedListDemo.java
java CheckedListDemo
```

Stdout:

```text
[safe]
ClassCastException
[safe]
```

Điểm đúng cần rút ra:

- `checkedList` giữ một `Class<E>` token để kiểm tra các thao tác phù hợp **đi qua chính wrapper**.
- Dù caller dùng raw reference trỏ tới wrapper, thao tác chèn giá trị sai lớp vẫn có thể bị từ chối ở runtime.
- Wrapper **không biến kiểu tham số hóa `List<String>` thành reified** trong ngôn ngữ Java.
- Nếu bên ngoài còn giữ tham chiếu trực tiếp tới **backing list** và chỉnh sửa nó mà bỏ qua wrapper, các kiểm tra của wrapper không bảo vệ được những thay đổi ấy.
- Các phần tử đã nằm trong backing list trước khi tạo wrapper không nhất thiết được wrapper quét và xác thực toàn bộ ngay lúc khởi tạo.

Vì vậy, checked wrapper là một công cụ bảo vệ ranh giới cụ thể, không phải cơ chế phục hồi generic type argument từ mọi `List` runtime.

## 17. Những sai lầm thường gặp khi suy luận kiểu của `List`

**Sai lầm 1 — “`getClass()` trả về `ArrayList<String>`.”** Không. Trong ví dụ thông thường, `getClass()` trả `Class` của `ArrayList`. Thông tin `<String>` không tạo class runtime mới.

**Sai lầm 2 — “`instanceof List<String>` sẽ kiểm tra được phần tử.”** Không. Kiểu này không reifiable, nên phép kiểm tra trực tiếp không hợp lệ. `instanceof List<?>` chỉ xác minh container.

**Sai lầm 3 — “Mọi thông tin generic bị mất khỏi mọi class file.”** Không. `Signature` có thể lưu generic declaration của field/method/class, và reflection có thể đọc chúng.

**Sai lầm 4 — “Nếu reflection thấy `List<String>` ở field, object chắc chắn chỉ chứa `String`.”** Không. Reflection mô tả **kiểu được khai báo**; raw/unchecked access hoặc dữ liệu không được kiểm tra có thể làm collection chứa giá trị sai.

**Sai lầm 5 — “Kiểm tra phần tử đầu tiên là đủ.”** Không. Danh sách có thể rỗng, có nhiều kiểu phần tử, hoặc được chỉnh sửa sau khi kiểm tra. Kiểm tra toàn bộ chỉ chứng minh điều kiện trên dữ liệu được quan sát tại thời điểm kiểm tra.

**Sai lầm 6 — “Danh sách rỗng tự chứng minh `List<String>`.”** Không. Một danh sách rỗng đồng thời thỏa vị từ “mọi phần tử là String” và “mọi phần tử là Integer”; không thể suy ra generic argument nguồn từ việc không có phần tử.

**Sai lầm 7 — “Type token tự động xác thực mọi kiểu lồng nhau.”** Không. `String.class` kiểm tra được `String`, nhưng `List<String>.class` không tồn tại. Kiểu generic lồng nhau cần biểu diễn bằng `Type` hoặc schema, và cần mã kiểm tra/giải mã thực tế.

**Sai lầm 8 — “Anonymous subclass chứng minh các phần tử đã an toàn.”** Không. Nó có thể giữ lại khai báo `List<String>` trong generic superclass metadata; nội dung collection vẫn cần hợp đồng và xác minh riêng.

**Sai lầm 9 — “Thấy `@SuppressWarnings("unchecked")` là chắc chắn an toàn.”** Không. Annotation chỉ tắt cảnh báo biên dịch được chỉ định; nó không thêm kiểm tra runtime nào.

**Sai lầm 10 — “Type erasure khiến generics không hữu dụng.”** Không. Generics giúp bắt lỗi sớm trong mã được kiểm tra bình thường và duy trì quan hệ kiểu nhất quán giữa tham số, kết quả và thao tác trên collection.

## 18. Tình huống áp dụng: chọn công cụ đúng câu hỏi

| Câu hỏi bạn cần trả lời | Cách phù hợp |
|---|---|
| “Object này có phải một `List` không?” | `instanceof List<?>` |
| “Mọi phần tử hiện tại có phải `String` không?” | Duyệt `List<?>`, kiểm tra từng phần tử và chính sách `null` |
| “Tôi muốn có một `List<String>` mới được xác minh.” | Tạo bản sao kiểm tra bằng `String.class` trước khi dùng |
| “Field này được khai báo là `List<String>` hay `List<Integer>`?” | Reflection: `Field.getGenericType()` |
| “Subclass này khai báo kiểu generic gì cho superclass?” | `Class.getGenericSuperclass()` |
| “Tôi cần mô tả `Map<String, List<Integer>>` cho thư viện giải mã.” | `Type`/type reference hoặc schema phù hợp |
| “Tôi có thể lấy `Class<List<String>>` từ `List<String>.class` không?” | Không; không tồn tại class literal đó |
| “Muốn cấm thêm phần tử sai qua wrapper runtime.” | `Collections.checkedList` với class token |
| “Muốn an toàn kiểu khi code mới làm việc với danh sách.” | Giữ `List<T>` hoặc `List<?>`, tránh raw types |
| “Có dữ liệu từ JSON/API chưa tin cậy.” | Giải mã theo schema/type và xác minh dữ liệu thực tế |

Một quy tắc thiết kế thực dụng: **để compiler kiểm tra kiểu khi có thể; truyền metadata/type token khi thư viện thật sự cần biết kiểu; kiểm tra nội dung tại biên giới dữ liệu chưa tin cậy**. Ba hoạt động này có vai trò riêng và thường bổ sung cho nhau.

## 19. Tự kiểm tra hiểu biết

**Câu 1.** Với:

```java
List<String> a = new ArrayList<>();
List<Integer> b = new ArrayList<>();
```

`a.getClass() == b.getClass()` trả gì?

**Đáp án:** `true`, vì hai object cùng được tạo từ `ArrayList`.

**Câu 2.** Vì sao compiler cho `String s = a.get(0)` dù method `List.get` ở bytecode liên quan tới `Object`?

**Đáp án:** Compiler dùng kiểu tĩnh `List<String>` để biết kết quả mong đợi là `String` và có thể tạo cast tương ứng trong bytecode.

**Câu 3.** Có thể viết `obj instanceof List<String>` trong Java 17 để xác minh loại phần tử không?

**Đáp án:** Không. `List<String>` không phải kiểu reifiable dùng được trong kiểm tra runtime kiểu này.

**Câu 4.** `obj instanceof List<?>` chứng minh điều gì?

**Đáp án:** `obj` là một `List` (không null) có đối số kiểu chưa biết; không chứng minh phần tử đều là `String`.

**Câu 5.** `Field.getGenericType()` trả `List<String>`. Điều này nói về object trong field hay khai báo của field?

**Đáp án:** Nói về **kiểu generic được khai báo của field**, không chứng nhận nội dung thực tế của object.

**Câu 6.** Tại sao `getGenericSuperclass()` của một subclass có thể báo `ArrayList<String>`?

**Đáp án:** Vì quan hệ `extends ArrayList<String>` là một phần của **khai báo class con**, có thể được giữ trong generic metadata.

**Câu 7.** Một hàm kiểm tra từng phần tử cho kết quả `true` với danh sách rỗng. Nó chứng minh danh sách là `List<String>` không?

**Đáp án:** Không. Không có phần tử sai không có nghĩa metadata kiểu của đối tượng đã được phục hồi.

**Câu 8.** `Class<String>` khác `Type` chứa `List<String>` thế nào?

**Đáp án:** `Class<String>` đại diện cho class runtime `String`; `Type` có thể diễn tả cấu trúc generic của một khai báo, trong đó `List<String>` là một `ParameterizedType`.

**Câu 9.** Một `Collections.checkedList` có bảo vệ các thay đổi đi trực tiếp vào backing list mà không qua wrapper không?

**Đáp án:** Không; kiểm tra của wrapper chỉ áp dụng khi các thao tác phù hợp được thực hiện thông qua wrapper.

**Câu 10.** Vì sao raw `List` có thể làm một `List<String>` chứa `Integer`?

**Đáp án:** Raw type làm mất kiểm tra kiểu phần tử ở compile time tại điểm sử dụng; object `ArrayList` thường không có runtime generic argument `String` để chặn thao tác thêm sai kiểu.

## 20. Bài thực hành theo từng bước

1. **Quan sát class runtime:** Chạy `RuntimeClassDemo`, thay `List<String>` bằng `List<Double>` và giải thích vì sao `getClass()` vẫn không hiển thị type argument.
2. **Chứng minh erasure:** Biên dịch `FieldMetadataDemo`, chạy `javap -p -s FieldMetadataDemo` hoặc xem class nested `FieldMetadataDemo$Registry`; xác định field descriptor chứa `List` chứ không chứa `<String>`.
3. **Đọc Signature:** Chạy `javap -p -v 'FieldMetadataDemo$Registry'` và tìm chuỗi generic Signature của hai field.
4. **Thử `instanceof`:** Viết một phiên bản dùng `instanceof List<String>` và quan sát lỗi compiler; thay bằng `instanceof List<?>` và kiểm tra từng phần tử.
5. **Kiểm tra heap pollution:** Chạy `HeapPollutionDemo`, bỏ phần catch trong một bản sao thử nghiệm để xem vị trí runtime phát sinh lỗi.
6. **Chủ động giữ type metadata:** Chạy `TypeCaptureDemo`, thử đổi kiểu thứ hai thành `Map<Long, List<String>>` và quan sát `getTypeName()`.
7. **Thực hành biên giới dữ liệu:** Mở rộng `checkedCopy` để từ chối `null` bằng chính sách rõ ràng; đối chiếu với `List.copyOf`, vốn cũng từ chối phần tử `null`.
8. **Kiểm tra giới hạn wrapper:** Tạo một backing `ArrayList<String>`, bọc bằng `Collections.checkedList`, sau đó xác minh rằng mọi thao tác thêm qua wrapper được kiểm tra; giải thích rủi ro nếu vẫn còn đường truy cập không an toàn vào backing list.

Trong tất cả bài tập, hãy phân biệt **điều compiler chứng minh**, **kiểu JVM biết lúc chạy**, và **điều chương trình tự kiểm tra trong dữ liệu**.

## 21. Tổng kết

`List<String>` có ý nghĩa rất lớn **ở mã nguồn Java**: nó cho compiler biết loại phần tử dự kiến và cho phép phát hiện sai kiểu sớm. Nhưng Java Generics thông thường bị xóa kiểu khi biên dịch; một instance `ArrayList` không tự mang đối số `<String>` như một phần đầy đủ của runtime class identity. Vì thế `getClass()`, `instanceof` hay class literal thông thường không thể khôi phục chắc chắn `String` từ một danh sách bất kỳ.

Một số generic information **vẫn còn trong class file** dưới dạng `Signature` của khai báo class, field hoặc method. Reflection và type-reference pattern có thể đọc phần metadata **đã được khai báo** ấy, nhưng không biến mọi generic object thành reified object.

Khi cần xác minh loại phần tử thực tế, hãy kiểm tra dữ liệu bằng `List<?>` và cơ chế như `Class<T>.cast`, tạo bản sao an toàn hoặc dùng wrapper có kiểm tra runtime ở ranh giới thích hợp. Đừng nhầm metadata khai báo với việc xác minh từng phần tử.

### Tài liệu chuẩn để đối chiếu

- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): nguyên tắc xóa parameterized types và type variables.
- [Java Language Specification §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): các kiểu có đủ thông tin runtime theo đặc tả.
- [Java Language Specification §4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8): tương thích mã cũ và nguy cơ unchecked.
- [Java Language Specification §15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): điều kiện dùng `instanceof`.
- [JVM Specification §4.7.9 — `Signature` Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.9): metadata generic trong class file.
- [Java SE 17 `java.lang.reflect.Type`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html): biểu diễn kiểu generic qua Reflection.
- [Java SE 17 `java.util.Collections.checkedList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#checkedList(java.util.List,java.lang.Class)): wrapper kiểm tra phần tử khi chạy.