# Class literal: `String.class`, `List.class` và giới hạn của `List<String>.class`

## Mục tiêu học tập

Trong Java, cú pháp `SomeType.class` trả về một đối tượng `Class` đại diện cho một kiểu có thể được nhận diện bằng class literal. Khi đi từ `String.class` sang `List.class` rồi thử viết `List<String>.class`, bạn chạm tới khác biệt cốt lõi giữa **kiểu trong mã nguồn** và **thông tin kiểu có thể kiểm tra lúc chạy** của Java Generics.

Sau bài này, bạn có thể:

1. Hiểu `String.class` và `List.class` là gì, kiểu generic của mỗi biểu thức là gì và vì sao `List<String>.class` không hợp lệ.
2. Phân biệt `Class<T>`, `Class<?>`, `Type` và `ParameterizedType`, cùng giới hạn của từng API.
3. Giải thích liên hệ giữa **type erasure**, **reifiable type** và cú pháp class literal.
4. Sử dụng `Class.isInstance`, `Class.cast` và `Class<T>` để kiểm tra loại đối tượng cụ thể; nhận ra khi nào chúng không thể kiểm tra phần tử của collection.
5. Thu thập thông tin generic từ khai báo bằng reflection hoặc một type reference, và tránh coi metadata đó là bằng chứng dữ liệu runtime đã đúng kiểu.

## 1. Class literal là gì?

Class literal có cú pháp kết thúc bằng `.class`, ví dụ:

```java
String.class
Integer.class
java.util.List.class
int.class
String[].class
void.class
```

Những biểu thức này đại diện cho các kiểu mà Java có thể biểu diễn bằng đối tượng `java.lang.Class` tương ứng. Ví dụ:

```java
Class<String> stringType = String.class;
Class<?> listType = java.util.List.class;

System.out.println(stringType.getName());
System.out.println(listType.getName());
```

Đoạn mã minh họa trên đặt bên trong một phương thức, có stdout:

```text
java.lang.String
java.util.List
```

`String.class` không tạo một `String` mới, còn `List.class` không tạo một `List` mới. Chúng là **đối tượng mô tả kiểu** (*class tokens*), dùng cho reflection, xác thực runtime, tìm metadata, hoặc cung cấp thông tin loại đối tượng cho API có tham số kiểu.

Đối với kiểu tham chiếu không generic, kiểu của biểu thức `String.class` là `Class<String>`. Với một tên kiểu generic được viết **không có đối số kiểu**, như `List.class`, biểu thức tương ứng với `Class<List>` (trong đó `List` là raw type), và ta thường gán nó vào `Class<?>` khi không cần thao tác cụ thể với raw generic:

```java
Class<?> listToken = java.util.List.class;
```

Việc dùng `Class<?>` ở đây giúp code khai báo rõ: biến chứa một class token có kiểu thành phần chưa biết. Nó không biến token thành `Class<List<String>>`.

## 2. Vì sao có `String.class` và `List.class` nhưng không có `List<String>.class`?

Một hiểu nhầm phổ biến là: vì mã Java cho phép khai báo `List<String>` nên chắc phải có biểu thức `List<String>.class`. Thực tế:

```java
String.class             // Hợp lệ
java.util.List.class     // Hợp lệ

// Những biểu thức sau KHÔNG HỢP LỆ trong Java:
// java.util.List<String>.class
// java.util.List<?>.class
```

**`List<String>.class` không tồn tại trong cú pháp class literal của Java.** Sau type erasure, `List<String>` và `List<Integer>` không có hai lớp runtime riêng. Chúng đều sử dụng cùng kiểu runtime được biểu diễn bởi `java.util.List.class`.

Bảng đối chiếu:

| Biểu thức / kiểu | Có class literal? | Ý nghĩa |
| --- | --- | --- |
| `String.class` | Có | Token của lớp String. |
| `List.class` | Có | Token của kiểu `List`, không lưu đối số `String` hay `Integer`. |
| `List<String>.class` | Không | Java không cung cấp class literal cho tham số hóa cụ thể này. |
| `List<?>.class` | Không | `List<?>` có tính chất reifiable, nhưng cú pháp class literal không cho viết trực tiếp dạng tham số hóa này. |
| `String[].class` | Có | Token của kiểu mảng có thành phần String. |
| `int.class` | Có | Token của kiểu nguyên thủy `int`. |
| `T.class`, với `T` là type variable | Không | Tham số kiểu T không được hiện thực thành một class token tách biệt. |

**Không đánh đồng “reifiable” với “viết được `.class` ở mọi dạng cú pháp”.** `List<?>` là một reifiable type theo phân loại của Java vì các đối số kiểu đều là wildcard không giới hạn; phép `instanceof List<?>` là hợp lệ. Nhưng biểu thức `List<?>.class` vẫn không hợp lệ về cú pháp. Khi cần class token của lớp chứa, ta viết `List.class`.

### Kiểu reifiable liên quan gì ở đây?

Một kiểu được gọi là *reifiable* nếu thông tin kiểu của nó có đủ biểu diễn để có thể quan sát/kiểm tra thích hợp tại runtime. Ví dụ:

- Kiểu nguyên thủy, như `int`.
- Kiểu class/interface không generic, như `String`.
- Raw type, như `List`.
- Một kiểu generic với **mọi** đối số là wildcard không giới hạn, như `List<?>`.
- Mảng có thành phần thuộc kiểu reifiable, như `String[]`.

`List<String>` **không** phải reifiable type: JVM không giữ và kiểm tra đầy đủ đối số `String` trong một đối tượng `List` thông thường. Vì thế không thể áp dụng cùng kiểu kiểm tra runtime của `String.class` cho toàn bộ `List<String>` thông qua một class literal.

## 3. Hiểu sâu hơn về type erasure

Giả sử có hai khai báo:

```java
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
```

Ở compile time, compiler xem `words` và `numbers` là hai tham số hóa khác nhau, từ đó từ chối `words.add(42)` hoặc `numbers.add("A")`. Nhưng kiểu `ArrayList` thực hiện việc lưu đối tượng theo cấu trúc có thể dùng chung cho nhiều đối số kiểu. Thông tin `String` hoặc `Integer` không làm nảy sinh hai lớp `ArrayList<String>` và `ArrayList<Integer>` độc lập ở JVM.

Sơ đồ khái niệm:

```text
Mã nguồn:
    List<String> words        List<Integer> numbers
           |                           |
           | kiểm tra generic          | kiểm tra generic
           v                           v
      ArrayList<String>          ArrayList<Integer>
           \                           /
            \       type erasure      /
             v                       v
             cùng lớp java.util.ArrayList tại runtime
                         |
                         v
                  ArrayList.class
```

Đối với một đối tượng `List<String>`, các phương thức thông thường như `get(int)` không trả về một `String` có thể suy luận độc lập từ đối tượng `Class` của danh sách. Descriptor của `List.get` trả về `Object` sau erasure; trình biên dịch chèn các phép cast thích hợp ở những vị trí chương trình cần `String`.

**Hệ quả:** `list.getClass()` trả về class runtime của implementation, ví dụ một lớp `ArrayList` hoặc implementation khác. Nó không biến thành một `Class<List<String>>`. Ngay cả khi `getClass()` cho bạn biết đối tượng là `ArrayList`, class token đó không tiết lộ từng phần tử hiện có có phải `String` hay không.

Điều này cũng giải thích tại sao:

```java
Object value = List.of("A", "B");
System.out.println(value instanceof List<?>);
```

là hợp lệ và in `true`. Runtime có thể kiểm tra đối tượng triển khai `List`. Nó **không kiểm tra** bên trong danh sách chỉ có String. Nếu đổi danh sách thành `List.of(1, 2)`, phép kiểm tra `instanceof List<?>` vẫn là `true`.

Không thể viết một phép kiểm tra chung `value instanceof List<String>` để xác minh mọi phần tử String. Với các trường hợp yêu cầu kiểm tra phần tử, hãy duyệt và xác thực các đối tượng thực tế.

## 4. `Class<T>` và `Class<?>` dùng vào việc gì?

`java.lang.Class<T>` là một API generic mà tham số `T` diễn đạt lớp/kiểu được mô tả. Hai ví dụ quen thuộc:

```java
Class<String> stringClass = String.class;
Class<Integer> integerClass = Integer.class;
```

Với `Class<T>`, Java cung cấp các thao tác tiện lợi:

- `boolean isInstance(Object obj)`: cho biết đối tượng có là instance hợp lệ của kiểu runtime do token đại diện hay không.
- `T cast(Object obj)`: kiểm tra/cast theo class token rồi trả về giá trị được gán kiểu T tại compile time; có thể ném `ClassCastException`.
- `boolean isAssignableFrom(Class<?> cls)`: xem class do `cls` mô tả có thể gán cho class/interface đang xét hay không, theo quan hệ kiểu runtime.
- `getName()`, `getDeclaredFields()`, `getDeclaredMethods()` và nhiều phương thức reflection khác.

Ví dụ minh họa có thể đặt trong phương thức:

```java
Class<String> textType = String.class;
System.out.println(textType.isInstance("hello")); // true
System.out.println(textType.isInstance(123));     // false
String value = textType.cast("hello");            // Hợp lệ
// String invalid = textType.cast(123);           // ClassCastException
```

`Class.cast` không phải phép chuyển đổi giá trị. Nó không thể chuyển số 123 thành chuỗi `"123"`. Nó kiểm tra đối tượng thực tế có khớp kiểu runtime không. Với giá trị `null`, `Class.cast(null)` trả về `null`, trong khi `isInstance(null)` trả về `false`.

Nếu không biết trước lớp nào được dùng, `Class<?>` là lựa chọn phù hợp:

```java
Class<?> runtimeType = List.class;
System.out.println(runtimeType.isInstance(List.of(1, 2))); // true
```

Vì token đại diện cho kiểu `List`, nó chỉ xác định rằng giá trị là một List. Nó không nói những phần tử của list đó thuộc `String`, `Integer` hay một kiểu khác.

### Tại sao không dùng một `Class<List<String>>` tùy ý?

`Class<List<String>>` là một kiểu tham số hóa có thể được viết trong **khai báo kiểu Java**, nhưng bạn không thể lấy giá trị này từ `List<String>.class` vì biểu thức đó không tồn tại. Việc ép từ `List.class` qua unchecked cast để “giả” ra `Class<List<String>>` không thêm thông tin phần tử vào class token:

```java
// KHÔNG NÊN DÙNG để chứng minh phần tử là String.
// @SuppressWarnings("unchecked")
// Class<List<String>> pretend =
//         (Class<List<String>>) (Class<?>) List.class;
```

Đoạn minh họa trên được chú thích để không gây cảnh báo hay ngụ ý rằng nó bảo đảm an toàn. Ở runtime, token vẫn là `List.class` và không có cơ chế tự kiểm tra sâu `List<String>`.

## 5. Chương trình Java 17 hoàn chỉnh

Ví dụ sau trình bày các phép kiểm tra bằng `Class<?>`, đọc khai báo field bằng reflection, giữ metadata generic bằng type reference và kiểm tra **từng phần tử** trước khi trả về một `List<String>` được xác thực.

**Tệp `ClassLiteralDemo.java`:**

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class ClassLiteralDemo {
    static final class PersonData {
        List<String> names = List.of("An", "Binh");
    }

    static final class GenericBox<T> {
        List<T> items;
    }

    abstract static class TypeRef<T> {
        private final Type captured;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType parameterized)) {
                throw new IllegalStateException("Missing type argument");
            }
            this.captured = parameterized.getActualTypeArguments()[0];
        }

        Type type() {
            return captured;
        }
    }

    static <T> T castKnown(Class<T> type, Object value) {
        return type.cast(value);
    }

    static <E> List<E> checkedCopy(List<?> values, Class<E> elementType) {
        List<E> result = new ArrayList<>();
        for (Object value : values) {
            result.add(elementType.cast(value));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<String> textClass = String.class;
        Class<?> listClass = List.class;
        System.out.println("textClass=" + textClass.getName());
        System.out.println("listClass=" + listClass.getName());
        System.out.println("isList=" + listClass.isInstance(List.of("A")));
        System.out.println("isString=" + textClass.isInstance(42));

        Field field = PersonData.class.getDeclaredField("names");
        System.out.println("rawField=" + field.getType().getTypeName());
        System.out.println("genericField=" + field.getGenericType().getTypeName());

        Field variableField = GenericBox.class.getDeclaredField("items");
        System.out.println("genericVariable=" + variableField.getGenericType().getTypeName());

        Type captured = new TypeRef<List<String>>() {}.type();
        System.out.println("captured=" + captured.getTypeName());

        List<?> mixed = List.of("A", 42);
        System.out.println("listTest=" + List.class.isInstance(mixed));
        try {
            checkedCopy(mixed, String.class);
        } catch (ClassCastException exception) {
            System.out.println("badElement=" + exception.getClass().getSimpleName());
        }

        System.out.println("validated="
                + checkedCopy(List.of("A", "B"), String.class));
        System.out.println("castKnown="
                + castKnown(String.class, "hello").toUpperCase(Locale.ROOT));
        System.out.println("arrayToken=" + String[].class.getTypeName());
    }
}
```

**Biên dịch và chạy** với JDK 17 trở lên:

```bash
javac --release 17 ClassLiteralDemo.java
java ClassLiteralDemo
```

**Stdout đã được kiểm chứng:**

```text
textClass=java.lang.String
listClass=java.util.List
isList=true
isString=false
rawField=java.util.List
genericField=java.util.List<java.lang.String>
genericVariable=java.util.List<T>
captured=java.util.List<java.lang.String>
listTest=true
badElement=ClassCastException
validated=[A, B]
castKnown=HELLO
arrayToken=java.lang.String[]
```

Phân tích các phần chính:

1. `textClass` là `Class<String>`, còn `listClass` là `Class<?>` trỏ tới `List.class`. Mỗi token cho biết một kiểu runtime, không tạo đối tượng dữ liệu.
2. `List.class.isInstance(List.of("A"))` cho `true`, còn `String.class.isInstance(42)` cho `false`.
3. `field.getType()` của `PersonData.names` chỉ trả về class/interface raw `List`. `field.getGenericType()` đọc **khai báo field** và cho `List<String>` dưới dạng `Type`.
4. `GenericBox<T>.items` được khai báo với `T` chưa được thay bằng loại cụ thể trong metadata của lớp generic gốc; bởi vậy `getGenericType()` phản ánh `List<T>`.
5. `TypeRef<List<String>>` giữ lại một khai báo generic cụ thể thông qua lớp con ẩn danh. Kết quả `Type` in ra `List<String>`.
6. `List.class.isInstance(mixed)` chỉ nhìn cấu trúc ngoài, nên vẫn là `true` khi danh sách chứa một `Integer`.
7. `checkedCopy` kiểm tra từng đối tượng bằng `elementType.cast(value)`. Đến `Integer`, nó ném `ClassCastException`. Với danh sách chỉ chứa String, nó tạo bản sao không sửa được.
8. `String[].class` là token của mảng String, và `getTypeName()` cho tên kiểu mảng thân thiện `java.lang.String[]`.

### Phân biệt hai loại thông tin đang được hiển thị

Hai dòng:

```text
rawField=java.util.List
genericField=java.util.List<java.lang.String>
```

**không mâu thuẫn**. `getType()` truy vấn kiểu class/interface runtime của field, còn `getGenericType()` trả về mô tả kiểu **đã được khai báo ở nguồn và lưu trong class-file metadata**. Metadata có ích cho framework và công cụ phân tích, nhưng không phải phép chứng minh rằng **mọi giá trị hiện nằm trong field** đã được kiểm tra là `String`.

## 6. Những dòng cố ý không biên dịch

Ví dụ sau là **mã lỗi có chủ đích**, không thêm vào chương trình chạy ở phần 5.

**Tệp `InvalidClassLiterals.java`:**

```java
import java.util.List;

class InvalidClassLiterals {
    Class<List<String>> token = List<String>.class;
}
```

Biên dịch:

```bash
javac --release 17 InvalidClassLiterals.java
```

`javac` từ chối ở `List<String>.class`; trong bản kiểm chứng Java 17 compiler mode, lỗi cú pháp có phần chính:

```text
error: <identifier> expected
```

Thông điệp và dấu mũ đánh dấu ký tự có thể khác theo compiler; nguyên nhân không đổi là class literal không nhận dạng `List<String>` theo cách viết này.

**Tệp `InvalidGenericToken.java`:**

```java
class InvalidGenericToken {
    <T> Class<T> token() {
        return T.class;
    }
}
```

Biên dịch:

```bash
javac --release 17 InvalidGenericToken.java
```

Lỗi trọng tâm đã kiểm chứng:

```text
error: cannot select from a type variable
```

`T` là biến kiểu ở compile time, không phải một lớp runtime có class literal riêng. Cách sửa là nhận token từ caller:

```java
static <T> Class<T> token(Class<T> type) {
    return type;
}
```

Đây là khai báo phương thức minh họa, đặt trong một lớp. Caller có thể gọi `token(String.class)` và nhận lại `Class<String>`. Giá trị này xác định lớp String, nhưng `Class<T>` vẫn không biểu diễn đầy đủ `List<String>`.

**Tệp `InvalidWildcardLiteral.java`:**

```java
import java.util.List;

class InvalidWildcardLiteral {
    Class<?> token = List<?>.class;
}
```

Đoạn này cũng **không biên dịch** với `javac --release 17`. Mặc dù `List<?>` là một *reifiable type*, cú pháp `List<?>.class` không được phép. Nếu cần token, dùng `List.class`; nếu cần kiểm tra một đối tượng là List mà không yêu cầu phần tử cụ thể, có thể dùng `obj instanceof List<?>`.

## 7. Vì sao `instanceof List<?>` hợp lệ mà `List<String>.class` không?

`instanceof` hỏi liệu **đối tượng** có thuộc một kiểu mà runtime có thể kiểm tra được hay không.

```java
Object candidate = List.of("A");
boolean listLike = candidate instanceof List<?>;
System.out.println(listLike);
```

Kết quả:

```text
true
```

`List<?>` không yêu cầu runtime phân biệt loại phần tử. Vì vậy phép kiểm tra dạng wildcard không giới hạn có thể thực hiện bằng thông tin kiểu `List`.

Ngược lại:

```java
// Không phải một phép kiểm tra generic runtime hợp lệ:
// boolean stringsOnly = candidate instanceof List<String>;
```

Nhìn chung, kiểu `List<String>` không reifiable và runtime không thể chứng minh mọi phần tử có kiểu String chỉ bằng `instanceof`. Quy tắc compiler cho `instanceof` còn có một số trường hợp đặc biệt liên quan đến kiểu tĩnh của toán hạng và phép chuyển đổi cast; **không nên** dựa vào những trường hợp đặc biệt ấy để suy rằng JVM kiểm tra được đối số generic.

Để xác thực một danh sách String nhận từ nguồn chưa rõ kiểu, hãy kiểm tra hai tầng:

1. Kiểm tra hoặc yêu cầu đối tượng ngoài là `List<?>`.
2. Duyệt phần tử và kiểm tra mỗi giá trị với `String.class.isInstance` hoặc `String.class.cast` theo hợp đồng, rồi đưa vào cấu trúc typed được kiểm soát.

Mẫu này là chức năng của `checkedCopy` trong chương trình phần 5. Nó tạo ra bảo đảm dựa trên **dữ liệu đã duyệt**, không phụ thuộc vào việc cố tạo một `Class<List<String>>` giả.

## 8. `Class`, `Type` và `ParameterizedType` khác nhau thế nào?

Reflection của Java dùng nhiều abstraction vì một `Class<?>` không đủ biểu diễn tất cả kiểu ở mã nguồn.

| Khái niệm | Biểu diễn | Biết được gì? | Giới hạn |
| --- | --- | --- | --- |
| `Class<?>` | Class token, ví dụ `List.class` | Danh tính kiểu runtime, superclass, interface, phương thức, field... | Không lưu đối số `String` cho từng List object. |
| `Type` | Interface chung trong `java.lang.reflect` | Mô tả nhiều loại kiểu reflective | Không phải API kiểm tra phần tử runtime. |
| `ParameterizedType` | Ví dụ type mô tả `List<String>` | Raw type, các đối số kiểu trong một khai báo generic | Metadata khai báo không bảo đảm dữ liệu thực đúng kiểu. |
| `TypeVariable<?>` | Ví dụ `T` trong `GenericBox<T>` | Tên biến kiểu và các bound khai báo | Không tự trở thành Class<String> khi có đối tượng GenericBox<String>. |
| `WildcardType` | Ví dụ `? extends Number` | Giới hạn trên/dưới của wildcard khai báo | Không thay thế kiểm tra dữ liệu. |
| `GenericArrayType` | Ví dụ mảng có thành phần là biến kiểu | Kiểu thành phần generic trong khai báo | Không nhất thiết là `Class<?>` của mảng reifiable. |

Ví dụ đọc kiểu từ field:

```java
Field field = PersonData.class.getDeclaredField("names");
Type declared = field.getGenericType();

if (declared instanceof ParameterizedType parameterized) {
    System.out.println(parameterized.getRawType());
    System.out.println(parameterized.getActualTypeArguments()[0]);
}
```

Đây là đoạn đặt trong `ClassLiteralDemo.main`, nơi `PersonData` đã được định nghĩa và `Field`/`Type`/`ParameterizedType` đã được import. Kết quả trong chương trình minh họa tương ứng là raw type `interface java.util.List` và đối số `class java.lang.String` khi in `Type.toString()`.

**Khi nào xuất hiện metadata generic?** Trong class file, compiler có thể lưu `Signature` attribute mô tả tham số generic của field, method, superclass hoặc interface. Reflection đọc phần metadata đó, khác với việc xét class token runtime của một đối tượng cụ thể.

Ví dụ:

```java
class Holder<T> {
    List<T> items;
}
```

Nếu bạn tạo `new Holder<String>()`, runtime vẫn dùng cùng `Holder.class` với các instantiation tham số kiểu khác. Metadata trong khai báo `Holder.items` là `List<T>`, không tự hóa thành `List<String>` trên từng instance. Muốn biết T gắn với `String` trong một type hierarchy, cần có thông tin về lớp con generic đã chuyên biệt hóa, hoặc caller cung cấp một `Type`/token mô tả sự chuyên biệt hóa.

## 9. Type reference lưu được `List<String>` ở đâu?

Một mẫu kỹ thuật thường gặp trong thư viện JSON và reflection là **type reference** (đôi khi được gọi *super type token*): tạo một subclass ẩn danh của một lớp generic rồi đọc generic superclass đã khai báo.

Mẫu từ phần 5:

```java
Type captured = new TypeRef<List<String>>() {}.type();
System.out.println(captured.getTypeName());
```

Kết quả:

```text
java.util.List<java.lang.String>
```

Lý do cách này hoạt động:

1. `new TypeRef<List<String>>() {}` tạo một lớp con ẩn danh với superclass được khai báo có đối số `List<String>`.
2. Thông tin tham số hóa của superclass được lưu trong metadata class file của lớp ẩn danh đó.
3. `getClass().getGenericSuperclass()` đọc một `ParameterizedType` đại diện cho `TypeRef<List<String>>`.
4. `getActualTypeArguments()[0]` lấy `Type` đại diện cho `List<String>`.

Đây là **thông tin về khai báo generic của class**, không phải cơ chế JVM tạo class runtime mới cho `List<String>`. Nó không tự xác minh một danh sách đang chứa các chuỗi hay cho phép `List<String>.class`.

Trong ứng dụng dùng JSON serializer/deserializer, thư viện có thể nhận một `Type` như vậy để hướng dẫn cách đọc từng phần tử. Khi đó **thư viện** đảm nhận việc đọc và chuyển dữ liệu theo kiểu được mô tả; việc type reference tồn tại không khiến mọi danh sách bất kỳ tự đúng kiểu.

Không thể viết một implementation type reference ngây thơ rồi kỳ vọng lúc nào cũng biết tham số kiểu T. Nếu lớp con không cung cấp đối số kiểu cụ thể trong generic superclass, hoặc cấu trúc kế thừa phức tạp hơn giả định của ví dụ, việc lấy metadata cần logic bổ sung. Ở đây `TypeRef` chủ động kiểm tra `ParameterizedType` để báo lỗi nếu thiếu thông tin.

## 10. `Class<T>` hữu ích trong API generic, nhưng có giới hạn

Một API cần kiểm tra đối tượng thuộc loại đơn giản có thể yêu cầu token từ người gọi:

```java
static <T> T checkedCast(Class<T> type, Object value) {
    return type.cast(value);
}
```

Caller:

```java
String name = checkedCast(String.class, "An");
// String invalid = checkedCast(String.class, 42); // ClassCastException.
```

Tương tự, có thể nhận class token để tạo mảng đúng kiểu phần tử bằng `Array.newInstance`:

```java
@SuppressWarnings("unchecked")
static <T> T[] newArray(Class<T> componentType, int length) {
    return (T[]) java.lang.reflect.Array.newInstance(componentType, length);
}
```

Đây là phương thức minh họa độc lập. Runtime kiểm tra đúng loại phần tử mảng, nên `String[]` thực sự có thành phần String. Cast generic dùng trong implementation được giới hạn vào kết quả `Array.newInstance` với token caller cung cấp.

Tuy nhiên, đối với `List<String>`, một `Class<T>` duy nhất như `List.class` chỉ cho biết loại **container**. Không thể đưa `String.class` vào `List.class` để nó biến thành class literal của `List<String>`. Nếu cần bảo đảm sâu, chữ ký API nên nhận riêng:

```java
static <E> List<E> checkedCopy(
        List<?> input, Class<E> elementType) {
    List<E> result = new ArrayList<>();
    for (Object element : input) {
        result.add(elementType.cast(element));
    }
    return List.copyOf(result);
}
```

Đoạn này là phần rút từ chương trình hoàn chỉnh phần 5. Nó kiểm tra từng phần tử và trả về một danh sách mới. `List.copyOf` không cho phần tử `null`, vì vậy nếu hợp đồng cần hỗ trợ null phải thiết kế biến thể thích hợp.

### `Class.isInstance` có thể kiểm tra gì?

- `String.class.isInstance("A")` → `true`.
- `String.class.isInstance(1)` → `false`.
- `List.class.isInstance(List.of("A"))` → `true`.
- `List.class.isInstance(List.of(1))` → **cũng là `true`**.
- `String[].class.isInstance(new String[0])` → `true`.
- `List.class.isInstance(null)` → `false`.

Trường hợp `List.class` minh họa giới hạn quan trọng nhất của bài: class token đại diện loại container, không biểu diễn điều kiện về tất cả phần tử generic.

## 11. Mảng và generic: điểm tương phản hữu ích

Mảng Java giữ loại phần tử runtime. Ví dụ:

```java
String[] words = new String[2];
Object[] objects = words;
objects[0] = "OK";
// objects[1] = Integer.valueOf(1); // ArrayStoreException lúc chạy.
```

Nếu bỏ chú thích ở dòng cuối, JVM kiểm tra loại mảng String[] tại runtime và ném `ArrayStoreException` khi chèn Integer. Mảng là *covariant*, vì `String[]` gán được cho `Object[]`; việc kiểm tra runtime bù lại nguy cơ ghi phần tử sai kiểu.

Ngược lại, generic collections như `List<String>` và `List<Integer>` là **invariant** và phần lớn được triển khai bằng erasure, không có cơ chế tương đương để tự kiểm tra phần tử String của một raw `ArrayList` khi thêm qua alias raw.

Một số quy tắc liên quan:

```java
String[].class             // Hợp lệ.
java.util.List[].class     // Hợp lệ, dùng raw List ở thành phần mảng.

// java.util.List<String>[].class  // Không phải class literal hợp lệ.
// new java.util.List<String>[5]   // Không được phép tạo generic array kiểu này.
```

Khi cần danh sách có phần tử String, hãy dùng `List<String>`; khi cần mảng String, dùng `String[]`. Không cố ép `Class<List<String>>` từ `List[].class`: token mảng chỉ mô tả mảng các List ở mức erasure.

## 12. Những hiểu nhầm thường gặp

| Nhận định | Vì sao chưa đúng | Cách hiểu đúng |
| --- | --- | --- |
| “`List<String>.class` chỉ là cách viết dài của `List.class`.” | Biểu thức đầu **không hợp lệ** về cú pháp Java. | Sử dụng `List.class` cho kiểu raw runtime, và `Type` để mô tả khai báo tham số hóa. |
| “`List.class` phân biệt List String với List Integer.” | Không có đối số generic trong class token. | `List.class` nhận diện loại container. |
| “`List<?>` là raw List.” | Wildcard vẫn duy trì kiểm tra generic đối với phép ghi. | `List<?>` là typed view với phần tử chưa biết; `List` là raw type. |
| “`List<?>.class` phải hợp lệ vì List<?> reifiable.” | Reifiable không đồng nghĩa mọi cách viết đều được class-literal grammar cho phép. | Viết `List.class`; dùng `instanceof List<?>` khi muốn kiểm tra kiểu ngoài. |
| “`T.class` dùng được trong method generic.” | T không có class token tách biệt sau erasure. | Nhận `Class<T>` từ caller hoặc dùng mô hình `Type` phù hợp. |
| “Reflection thấy `List<String>` nghĩa là List đó đã được kiểm tra sâu.” | Reflection đọc metadata khai báo, không duyệt nội dung đối tượng. | Xác thực từng phần tử tại ranh giới dữ liệu. |
| “Ép `Class<?>` thành `Class<List<String>>` sẽ tăng an toàn.” | Cast không thêm thông tin runtime. | Tránh unchecked cast; dùng `Type` và validator khi cần. |
| “TypeRef biến `List<String>` thành class runtime mới.” | TypeRef lưu metadata của subclass khai báo generic. | Dùng nó để truyền mô tả kiểu cho thư viện hiểu `Type`, không phải thay `Class`. |
| “`Class.cast` có thể chuyển Integer thành String.” | Cast kiểm tra khả năng gán, không chuyển giá trị. | Nếu cần chuyển đổi, dùng quy tắc chuyển đổi rõ ràng riêng. |

## 13. Quy trình chọn công cụ đúng

**Trường hợp A — cần kiểm tra đối tượng thuộc lớp cụ thể:** dùng `String.class`, `Class<T>.isInstance` hoặc `Class<T>.cast`.

**Trường hợp B — cần kiểm tra một đối tượng có phải collection:** dùng `obj instanceof List<?>` hoặc `List.class.isInstance(obj)`.

**Trường hợp C — cần xác nhận các phần tử của một collection là String:** nhận `List<?>` rồi kiểm tra từng phần tử, copy sang `List<String>` đã được xác thực. Nếu dữ liệu không tin cậy, xác định chính sách đối với null, subtype và giá trị sai.

**Trường hợp D — cần đọc generic được viết trên field/method/superclass:** dùng `getGenericType()`, `getGenericReturnType()`, `getGenericParameterTypes()` hoặc `getGenericSuperclass()` và làm việc với `Type`/`ParameterizedType` khi phù hợp.

**Trường hợp E — thư viện cần mô tả `List<String>` để deserialize JSON:** truyền `Type`/type reference theo API của thư viện; việc xác thực/chuyển đổi phần tử thuộc về quá trình xử lý dữ liệu của thư viện.

**Trường hợp F — generic method cần tạo/check đối tượng kiểu T:** cho caller truyền `Class<T>` nếu T là class token có thể đại diện; không dùng `T.class`.

Lưu ý về thiết kế: đừng đưa quá nhiều tham số `Class<?>` vào public API chỉ vì generic của Java không reified. Hãy xác định rõ yêu cầu là **kiểm tra một lớp**, **mô tả kiểu generic** hay **xác thực dữ liệu thực** rồi chọn abstraction thích hợp.

## 14. Bài tập tự kiểm tra

**Bài 1.** `List<String>.class` và `List<Integer>.class` có trả về hai class token khác nhau không?

**Đáp án:** Không có biểu thức nào hợp lệ. Cả hai loại danh sách được mô tả ở mức container bằng `List.class`; đối số generic khác nhau được kiểm tra ở compile time và có thể tồn tại trong metadata khai báo.

**Bài 2.** Vì sao đoạn sau không thể xác nhận một danh sách chứa toàn String?

```java
Object data = List.of(1, 2);
System.out.println(List.class.isInstance(data));
```

**Đáp án:** Nó chỉ kiểm tra đối tượng triển khai `List`, nên in `true`. Không có kiểm tra phần tử bằng `String.class`.

**Bài 3.** `Field.getType()` và `Field.getGenericType()` khác nhau ra sao khi field khai báo `List<String>`?

**Đáp án:** `getType()` trả về class/interface `List`; `getGenericType()` trả về một `Type` có thể là `ParameterizedType` lưu mô tả `List<String>` từ khai báo.

**Bài 4.** Tại sao `T.class` không dùng được trong `<T> void process(T value)`?

**Đáp án:** Type variable T không được reify thành class token riêng. Có thể viết `<T> void process(T value, Class<T> type)` khi API cần token cụ thể do caller cung cấp.

**Bài 5.** `List<?>.class` và `obj instanceof List<?>` có cùng tính hợp lệ không?

**Đáp án:** Không. `List<?>.class` không hợp lệ; `instanceof List<?>` hợp lệ để kiểm tra đối tượng thuộc loại List mà không yêu cầu phần tử cụ thể.

**Bài 6.** `new TypeRef<List<String>>() {}.type()` có chứng minh mọi phần tử của một danh sách nhập từ network là String không?

**Đáp án:** Không. Nó lưu mô tả generic trong metadata của một subclass. Muốn chắc chắn dữ liệu đúng, chương trình hoặc thư viện deserializer vẫn phải kiểm tra và xử lý từng phần tử.

**Bài 7.** Tại sao `String[].class` hợp lệ trong khi `List<String>.class` không hợp lệ?

**Đáp án:** Mảng String có kiểu thành phần String được lưu tại runtime; một tham số hóa `List<String>` thông thường bị erasure và không có class token riêng cho đối số String.

## 15. Ghi nhớ

- `String.class` là `Class<String>`, biểu diễn kiểu String.
- `List.class` biểu diễn kiểu `List` ở runtime, **không** biểu diễn `List<String>`.
- `List<String>.class`, `List<?>.class` và `T.class` đều không phải class literal hợp lệ theo cách viết đó.
- `List<?>` là một kiểu dùng được trong chương trình và `instanceof List<?>` có thể kiểm tra loại container, nhưng **không kiểm tra kiểu phần tử**.
- `Type` và `ParameterizedType` giúp đọc mô tả generic từ **khai báo**, không thay thế xác thực dữ liệu thực tế.
- Khi cần một danh sách được tin cậy là `List<String>` từ nguồn chưa rõ kiểu, hãy dùng `Class<String>` để kiểm tra **từng phần tử**, sau đó giữ kết quả dưới API generic có kiểu rõ ràng.

Ranh giới quan trọng nhất là: **class literal mô tả lớp runtime; generic type argument có thể là thông tin ở compile time hoặc metadata; còn tính đúng kiểu của dữ liệu thực cần được đảm bảo bằng hợp đồng và kiểm tra phù hợp.**
