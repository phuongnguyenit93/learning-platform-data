# Kiểu reifiable và thông tin kiểu còn lại lúc chạy — nền tảng cho varargs an toàn

**Chủ đề:** Java 7 — Varargs an toàn  
**Bài học:** Kiểu reifiable và thông tin kiểu còn lại lúc chạy  
**Môi trường:** Java 17+; các nguyên tắc về *reifiable types*, *type erasure*, arrays, generic varargs và `@SafeVarargs` vẫn được dùng trong Java hiện đại.

Một chương trình Java có thể khai báo `List<String>`, `List<Integer>` và `List<?>`. Compiler hiểu được các khai báo này và có thể từ chối những thao tác sai kiểu. Nhưng **JVM không giữ toàn bộ thông tin generic type argument trên từng đối tượng collection**. Khác biệt đó ảnh hưởng trực tiếp đến cách dùng `instanceof`, phép cast, generic arrays và varargs.

**Câu hỏi trung tâm:** Sau khi biên dịch, **những phần nào của kiểu có thể kiểm tra ở runtime**, và vì sao một số lời gọi varargs với kiểu generic có thể tạo **heap pollution**?

## 1. Reifiable type là gì?

Theo Java Language Specification (JLS `4.7), **reifiable type** là kiểu mà biểu diễn runtime có đủ thông tin để JVM thực hiện những kiểm tra kiểu tương ứng mà không cần biết các đối số generic đã bị xóa. Đây là thuật ngữ quy định trong ngôn ngữ Java, không phải một annotation hay interface để implements.

Những nhóm cần biết:

1. **Primitive type:** `int`, `boolean`, `double`, ... có kiểu runtime xác định.
2. **Kiểu class/interface không parameterized**, chẳng hạn `String`, `Object`, `Runnable` (và non-generic type).
3. **Raw type**, chẳng hạn `List`, có biểu diễn runtime như `List` nhưng **không bảo đảm kiểu của phần tử**. Raw type vẫn reifiable về mặt JLS; điều này **không biến raw type thành cách viết nên dùng**.
4. **Parameterized type có mọi type argument là unbounded wildcard**, như `List<?>`, `Map<?, ?>`. Nó có thể được kiểm tra ở mức raw container; `?` tuyên bố kiểu phần tử chưa biết.
5. **Array có component type reifiable**, chẳng hạn `String[]`, `int[]`, `List<?>[]`.

Các chi tiết hình thức về nested types được nêu đầy đủ trong JLS `4.7; khi gặp một kiểu lồng phức tạp, hãy đối chiếu đúng quy tắc đó. Trong code ứng dụng, hai phân biệt có giá trị nhất là **`List<?>` đối lập với `List<String>`**, và **`String[]` đối lập với những mảng của parameterized types không reifiable**.

### 1.1. Bảng phân loại nhanh

| Biểu thức kiểu | Reifiable? | Điều có thể biết lúc chạy |
| --- | --- | --- |
| `int`, `String`, `IOException` | Có | Loại primitive/class cụ thể |
| `String[]`, `int[]` | Có | Array component type |
| `List` (raw) | Có | Đối tượng có phải một `List`, **không** biết `E` |
| `List<?>` | Có | Có phải `List`, kiểu phần tử vẫn chưa biết |
| `Map<?, ?>` | Có | Có phải `Map`, không kiểm chứng key/value arguments |
| `List<String>` | **Không** | Không kiểm tra được mọi phần tử là `String` chỉ qua runtime class |
| `List<Integer>` | **Không** | Không kiểm tra được mọi phần tử là `Integer` chỉ qua runtime class |
| `List<? extends Number>` | **Không** | Bounded wildcard vẫn mang tham số kiểu không reifiable |
| `Map<String, Integer>` | **Không** | Không kiểm chứng được cặp type arguments |
| `List<String>[]` | **Không** | Component là parameterized type không reifiable |
| `List<?>[]` | Có | Component có runtime type chung là `List` |
| Type variable `T` | Thông thường **không** | Kiểu cụ thể của `T` không có như một runtime class riêng |

**Lưu ý:** Reifiable **không đồng nghĩa** “an toàn về kiểu dữ liệu phần tử”. Raw `List` được coi là reifiable nhưng có thể chứa các phần tử trộn kiểu. `List<?>` được coi là reifiable nhưng compiler **không cho phép** gán kết quả `get(0)` thẳng vào `String` nếu chưa có kiểm tra phù hợp.

## 2. Type erasure: cái gì còn và cái gì bị xóa?

Java generics chủ yếu sử dụng **type erasure**. Khi biên dịch, compiler kiểm tra type arguments, thay type variables theo quy tắc erasure, chèn cast thích hợp khi cần và có thể phát sinh bridge methods để duy trì overriding.

Điều này cho phép `ArrayList<String>` và `ArrayList<Integer>` sử dụng **cùng một class runtime**. Type argument `String` hay `Integer` không được gắn lên từng instance để JVM kiểm tra mọi phép sử dụng collection.

Tuy nhiên, erasure **không có nghĩa toàn bộ metadata generic bị xóa khỏi tệp class**:

- **Runtime object:** mỗi instance vẫn có class thực tế, ví dụ `java.util.ArrayList`; không có `ArrayList<String>.class` riêng cho instance.
- **Generic declaration / signature metadata:** tệp class có thể chứa thông tin signature của field, method, superclass hoặc interface được khai báo. Reflection có thể đọc metadata này qua `getGenericType()`, `getGenericReturnType()` hoặc `getGenericInterfaces()` khi thông tin có trong class file.
- **Actual element content:** mỗi phần tử vẫn là một đối tượng runtime có class riêng; chỉ cần duyệt và kiểm tra từng phần tử là có thể xác nhận hợp đồng cụ thể.
- **Type parameter của lời gọi / object:** reflection đọc generic signature **không cho phép tự động suy ra** nội dung type argument của một đối tượng collection bất kỳ, nhất là sau khi dữ liệu qua API raw hoặc reflection.

Vì vậy “Java generic chỉ tồn tại ở compile time” là một cách nói **quá giản lược**. Hợp đồng generic được kiểm tra chủ yếu lúc biên dịch, nhưng vẫn có metadata khai báo; điều **không có** là một runtime representation đầy đủ của từng instantiation `List<String>` để `instanceof` kiểm tra loại phần tử.

### 2.1. Chương trình kiểm tra runtime class

Tạo tệp `RuntimeTypeDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class RuntimeTypeDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();

        System.out.println(
                "sameClass="
                + (words.getClass() == numbers.getClass()));

        Object supplied = List.of("alpha", "beta");
        System.out.println(
                "isList=" + (supplied instanceof List<?>));

        if (supplied instanceof List<?> items) {
            System.out.println(
                    "elementClass="
                    + items.get(0).getClass().getSimpleName());
        }

        System.out.println(
                "component="
                + String[].class.getComponentType()
                                .getSimpleName());
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:all RuntimeTypeDemo.java
java RuntimeTypeDemo
```

**stdout chính xác:**

```text
sameClass=true
isList=true
elementClass=String
component=String
```

Cặp `words`/`numbers` có type arguments khác nhau nhưng cùng class runtime `ArrayList`. `supplied instanceof List<?>` hợp lệ vì `List<?>` reifiable; kết quả chỉ xác minh **container là List**. Khi lấy phần tử đầu, `getClass()` cho biết chính **đối tượng phần tử** là `String`; phép kiểm tra này không tự suy rộng sang toàn bộ danh sách.

**Array là trường hợp khác:** `String[].class.getComponentType()` cung cấp `String` vì mảng Java lưu component type để hỗ trợ runtime store checks.

## 3. instanceof và Class literal: kiểm tra được đến đâu?

Vì `List<String>` không reifiable, compiler không cho dùng nó để kiểm tra một biểu thức `Object` tùy ý bằng `instanceof`:

```java
Object unknown = List.of("a");

// Hợp lệ:
boolean listLike = unknown instanceof List<?>;

// Không hợp lệ nếu bỏ comment:
// boolean onlyStrings = unknown instanceof List<String>;
```

Đây là **đoạn minh họa trong một method** đã có import `List`. Dạng `instanceof List<String>` trong ví dụ này không hợp lệ vì type argument không thể được kiểm tra trên một `Object` tùy ý. Trong một số trường hợp Java mới có các điều kiện chuyển đổi kiểu tĩnh đặc thù đối với `instanceof`; **không hiểu nhầm** chúng thành khả năng runtime kiểm chứng nội dung của collection.

Tương tự:

```java
Class<?> rawClass = List.class;

// Không tồn tại class literal:
// Class<List<String>> typed = List<String>.class;
```

`List.class` biểu diễn raw runtime class của interface `List`. Không có runtime class token riêng `List<String>.class`. Với `Map<String, Integer>`, cũng không có `Map<String, Integer>.class`.

**Giới hạn quan trọng:** `List.class.isInstance(value)` hay `value instanceof List<?>` chỉ xác định được loại container. Chúng **không** bảo đảm tất cả phần tử đều là `String`, cũng không bảo đảm không có `null`, schema đúng, hoặc list immutable.

### 3.1. Dùng Class<T> khi T là kiểu reifiable cụ thể

`Class<T>` hữu ích khi bạn biết một class runtime có thể kiểm tra, như `String.class` hay `Integer.class`. Có thể dùng `isInstance` hoặc `cast` để kiểm tra một đối tượng:

Tạo `ClassTokenDemo.java`:

```java
import java.util.List;

public class ClassTokenDemo {
    public static void main(String[] args) {
        Object text = "hello";

        System.out.println(
                "string=" + String.class.isInstance(text));
        System.out.println(
                "cast=" + String.class.cast(text).toUpperCase());
        System.out.println(
                "list=" + List.class.isInstance(List.of(1)));

        try {
            Integer.class.cast(text);
        } catch (ClassCastException ex) {
            System.out.println("rejected-wrong-class");
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ClassTokenDemo.java
java ClassTokenDemo
```

```text
string=true
cast=HELLO
list=true
rejected-wrong-class
```

`Class.cast` thực hiện kiểm tra class runtime phù hợp; nó giúp tránh unchecked cast khi type parameter là một class token kiểm tra được. Tuy nhiên `List.class` chỉ xác minh đối tượng là `List`: nó **không phải** token cho toàn bộ `List<String>` hoặc `List<Integer>`.

## 4. Array Java giữ component type ở runtime

Mảng Java biết component type và có runtime store check. Một phần tử sai kiểu sẽ bị JVM từ chối ngay khi gán, kể cả khi ta giữ tham chiếu qua một supertype như `Object[]`.

Tạo `ArrayRuntimeDemo.java`:

```java
import java.util.List;

public class ArrayRuntimeDemo {
    public static void main(String[] args) {
        String[] names = new String[1];
        Object[] alias = names;
        alias[0] = "safe";

        try {
            alias[0] = 42;
        } catch (ArrayStoreException ex) {
            System.out.println("array-store-rejected");
        }

        List<?>[] groups = new List<?>[2];
        groups[0] = List.of("red");
        groups[1] = List.of(10);

        System.out.println(
                groups[0].get(0) + "|" + groups[1].get(0));
        System.out.println(
                "arrayComponent="
                + groups.getClass().getComponentType()
                        .getSimpleName());
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ArrayRuntimeDemo.java
java ArrayRuntimeDemo
```

```text
array-store-rejected
red|10
arrayComponent=List
```

Điểm khác biệt:

- `Object[] alias = names` hợp lệ vì Java arrays **covariant**. JVM vẫn biết object thực tế là `String[]`, nên việc gán `42` bị chặn bằng `ArrayStoreException`.
- `List<?>[]` là một array hợp lệ vì `List<?>` reifiable. Nhưng mỗi phần tử của mảng **có thể là List chứa những kiểu giá trị khác nhau**.
- `groups.getClass().getComponentType()` cho ra `List`. Mảng biết container component type; nó **không giữ type argument cụ thể** của từng `List` nằm bên trong.
- Mảng `String[]` và generic collection `List<String>` có cơ chế bảo vệ kiểu khác nhau: array kiểm tra *component class* khi gán; generics kiểm tra *type arguments* chủ yếu tại compile time.

### 4.1. Tại sao không được tạo mảng List<String>?

Câu lệnh sau **không biên dịch**:

```java
// Generic array creation — không hợp lệ:
// List<String>[] groups = new List<String>[2];
```

Nếu Java cho phép tạo `new List<String>[2]` mà runtime chỉ nhìn thấy `List[]`, kiểm tra kiểu của mảng **không thể phân biệt** `List<Integer>` với `List<String>`. Điều đó tạo lỗ hổng type safety.

Một mảng `List<?>[]` hợp lệ không vì Java đã xác nhận từng phần tử cùng kiểu `String`, mà vì `?` thừa nhận **không biết** type argument. Khi muốn tập hợp nhiều `List<String>`, ưu tiên:

```java
List<List<String>> batches = new java.util.ArrayList<>();
batches.add(List.of("a"));
batches.add(List.of("b"));
```

Đây là **mã minh họa trong method**. Collection lồng generic cho compiler bảo vệ kiểu ở các phép `add`, tránh nhu cầu tạo generic array không reifiable.

**Lỗi tương tự với type variable:**

```java
// Trong generic method <T>:
// T[] array = new T[10]; // Không hợp lệ.
```

Không có runtime component class của `T` nếu chỉ biết một type variable. Nếu thật sự cần mảng có component type cụ thể, API có thể nhận `IntFunction<T[]>` như `String[]::new` hoặc array prototype; đừng tạo rồi ép bừa từ `Object[]` sang `T[]`.

## 5. Vì sao varargs đặc biệt nhạy cảm với non-reifiable types?

`varargs` (cú pháp `Type... args`) cho phép lời gọi truyền số lượng phần tử linh hoạt. Về cơ bản, khi gọi theo dạng varargs, Java dùng **một mảng** để chứa các đối số. Ví dụ `String...` tương ứng với `String[]`, là kiểu reifiable.

Nhưng xét:

```java
static void process(List<String>... groups) {
    // ...
}
```

Đây là **phương thức minh họa**. Kiểu phần tử varargs là `List<String>`, **không reifiable**. Mảng ở runtime không thể bảo đảm rằng mọi phần tử là `List<String>`. Trình biên dịch có thể cảnh báo:

- `[unchecked] Possible heap pollution from parameterized vararg type ...` tại khai báo phương thức.
- `[unchecked] unchecked generic array creation for varargs parameter ...` tại một số lời gọi tạo varargs array.

**Từ khóa:** *non-reifiable varargs*, *unchecked warning*, *heap pollution*. Đừng coi cảnh báo chỉ là vấn đề hiển thị của IDE; chúng báo rằng ngôn ngữ không thể chứng minh tuyệt đối type safety nếu implementation thao tác sai với mảng varargs.

### 5.1. Heap pollution là gì?

**Heap pollution** xảy ra khi một biến có kiểu tham số hóa tham chiếu tới dữ liệu **không phù hợp với kiểu ấy**, thường qua raw types, unchecked casts hoặc một generic varargs array bị dùng không an toàn.

Trong ví dụ generic varargs, mảng runtime có kiểu như `List[]`. Vì array covariance, nó có thể bị xem là `Object[]`. Nếu code gán một `List<Integer>` vào vị trí mà biến `List<String>...` đang tin là chứa `List<String>`, compiler không còn chứng cứ an toàn. Chỉ khi đọc giá trị như `String` mới có thể ném `ClassCastException`.

**Heap pollution không nhất thiết gây exception ngay tại dòng gây hỏng.** Đây chính là lý do cảnh báo generic varargs cần được phân tích theo cả chuỗi sử dụng mảng.

## 6. Ví dụ chạy được: cố tình gây heap pollution

Tạo `UnsafeVarargsDemo.java`:

```java
import java.util.List;

public class UnsafeVarargsDemo {
    static void corrupt(List<String>... groups) {
        Object[] alias = groups;
        alias[0] = List.of(123);

        String first = groups[0].get(0);
        System.out.println(first);
    }

    public static void main(String[] args) {
        try {
            corrupt(List.of("safe"));
        } catch (ClassCastException ex) {
            System.out.println("pollution-detected");
        }
    }
}
```

Biên dịch **có chủ đích để xem warnings**:

```bash
javac -encoding UTF-8 -Xlint:unchecked UnsafeVarargsDemo.java
java UnsafeVarargsDemo
```

**stdout chính xác** (compiler warnings in ra khi chạy `javac` là phần chẩn đoán riêng, không phải stdout của lệnh `java`):

```text
pollution-detected
```

Đây là ví dụ **cố ý không an toàn**, chỉ dùng để hiểu nguyên nhân; **không dùng nó làm template production**.

Các bước thực tế:

1. Compiler nhìn tham số `groups` là mảng varargs của `List<String>`.
2. Sau erasure, runtime array chỉ có khả năng kiểm tra component là `List`, không thể kiểm tra type argument `String`.
3. `Object[] alias = groups` hợp lệ vì mảng là đối tượng tham chiếu và có khả năng gán cho `Object[]`.
4. `alias[0] = List.of(123)` đưa `List<Integer>` vào mảng, nhưng runtime array store check chỉ thấy `List` nên **không chặn**.
5. `groups[0].get(0)` được code tin rằng trả `String`. Dữ liệu thật là `Integer` nên lỗi xuất hiện khi compiler-generated cast sang `String` được thực hiện.
6. `ClassCastException` được bắt trong `main` chỉ để ghi nhận lỗi; **bắt exception không sửa được heap pollution**.

**Đối chiếu với `String[]`:** Khi gán `Integer` vào `String[]` qua `Object[]`, JVM chặn ngay bằng `ArrayStoreException`. Với `List<String>[]`/varargs, runtime không biết generic argument nên không có kiểm tra tương tự cho `String`.

### 6.1. Những thao tác có nguy cơ cao với varargs array

Cần đặc biệt kiểm tra nếu body của phương thức varargs làm những việc này:

- Ép `List<String>...` hoặc `T...` thành `Object[]` rồi gán phần tử không đáp ứng hợp đồng.
- Lưu tham chiếu varargs array vào một field/shared cache, hoặc **trả lại** array để code ngoài có thể sửa nó.
- Đưa array đó vào một API cho phép thao tác không kiểm soát trên các phần tử.
- Truyền array cho helper không rõ hợp đồng mutation/escape.
- Dùng unchecked cast/suppression mà không chứng minh array chỉ chứa đúng loại phần tử.

Không phải mọi lời gọi generic varargs đều gây hỏng. Warning báo sự **thiếu bảo đảm tự động**; implementation và cách dùng quyết định có thực sự an toàn không.

## 7. @SafeVarargs: cam kết có điều kiện, không phải phép màu

`@SafeVarargs` là annotation tiêu chuẩn từ **Java 7**, cho phép tác giả API khẳng định một method/constructor varargs không gây heap pollution hoặc thao tác không an toàn trên tham số varargs có kiểu non-reifiable. Nó giúp giảm một số warnings tại khai báo và lời gọi.

**Annotation này không thêm runtime type checking**. Compiler tin vào cam kết của người viết API; nếu code gắn annotation sai nhưng vẫn làm hỏng mảng, chương trình **vẫn có thể gây heap pollution**.

Quy tắc áp dụng trên Java hiện đại:

- `static` method đủ điều kiện.
- `final` instance method đủ điều kiện.
- `private` instance method đủ điều kiện từ **Java 9**.
- Constructor đủ điều kiện.
- Không dùng annotation trên instance method có thể bị override tùy ý: một subclass có thể phá cam kết.
- Annotation phù hợp khi varargs parameter có **non-reifiable element type**; không dùng bừa cho `String...` chỉ để “tắt warning”.

**Trước khi annotate**, phải review body, helper mà nó gọi, việc có rò rỉ mảng hay alias hay không, cùng những hành động trên các phần tử varargs.

### 7.1. Ví dụ an toàn: chỉ đọc input và tạo List mới

Tạo `SafeVarargsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsDemo {
    @SafeVarargs
    static <T> List<T> merge(List<? extends T>... sources) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> source : sources) {
            result.addAll(source);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(
                merge(List.of("a"), List.of("b", "c")));
        System.out.println(
                merge(List.of(1), List.of(2, 3)));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all SafeVarargsDemo.java
java SafeVarargsDemo
```

```text
[a, b, c]
[1, 2, 3]
```

Lý do annotation **có cơ sở**:

1. `merge` chỉ **đọc** các tham chiếu `List<? extends T>` trong varargs array; không thay thế bất kỳ vị trí nào của array.
2. Không trả array, không lưu alias array vào field và không để callback bên ngoài sửa array.
3. Mỗi list nguồn chỉ được đọc qua `addAll` để đưa phần tử vào một `ArrayList<T>` mới.
4. `List.copyOf` cung cấp danh sách không thể sửa qua các phương thức mutator thông thường; ví dụ dùng `List.of` nên dữ liệu không chứa null. Nếu input có null, `List.copyOf` sẽ từ chối — đây là hợp đồng riêng của `List.copyOf`, không phải thuộc tính của annotation.
5. Phương thức `static` là nơi hợp lệ để dùng `@SafeVarargs`; không bị một subclass override rồi làm mất cam kết.

**Không lạm dụng:** Nếu thực sự chỉ muốn nhận **một danh sách các danh sách**, kiểu `List<List<T>>` hay `Collection<? extends Collection<? extends T>>` có thể đơn giản và tránh generic varargs warning. `@SafeVarargs` hữu ích khi API cần tính tiện dụng của đối số biến thiên; nó không phải nghĩa vụ để làm cho mọi method có `...` trông “sạch”.

### 7.2. Không dùng @SuppressWarnings thay cho kiểm chứng

`@SuppressWarnings("unchecked")` chỉ yêu cầu compiler ẩn một phần diagnostics trong scope có annotation. Nó **không** chứng minh method generic varargs an toàn; đặt suppression ở class level có thể che cảnh báo quan trọng khác.

Nếu một thiết kế bắt buộc dùng unchecked operation, hãy giảm scope tối thiểu, diễn giải bất biến kiểu và viết tests bắt những đường dữ liệu sai. Trong generic varargs, ưu tiên **loại bỏ hành vi ghi đè/escape mảng** hoặc thiết kế lại API trước khi cân nhắc suppression.

**Cũng đừng tự động gắn `@SafeVarargs` vào method chỉ vì có lint warning.** Nội dung `UnsafeVarargsDemo` vẫn không an toàn dù có annotation; việc ẩn warning chỉ làm rủi ro khó nhìn thấy hơn.

## 8. Runtime metadata qua reflection: còn gì, mất gì?

Một số người nghĩ Java không còn giữ **bất kỳ** thông tin generic nào khi chạy. Điều đó sai. Reflection có thể đọc **khai báo generic signature** của field, method và supertype khi metadata tương ứng có trong class file.

Tạo `ReflectionSignatureDemo.java`:

```java
import java.lang.reflect.Field;
import java.util.List;

public class ReflectionSignatureDemo {
    static final class Model {
        List<String> names = List.of("alpha");
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Field field = Model.class.getDeclaredField("names");

        System.out.println(
                "raw=" + field.getType().getSimpleName());
        System.out.println(
                "generic=" + field.getGenericType().getTypeName());
        System.out.println(
                "listLike="
                + field.getType().isInstance(List.of(123)));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ReflectionSignatureDemo.java
java ReflectionSignatureDemo
```

```text
raw=List
generic=java.util.List<java.lang.String>
listLike=true
```

`field.getGenericType()` cho biết field **được khai báo** là `List<String>`, nên có thể đọc chuỗi generic signature. Nhưng `field.getType().isInstance(List.of(123))` vẫn trả `true` vì `getType()` là `List.class` và chỉ kiểm tra raw runtime interface.

**Sự khác biệt cốt lõi:** Reflection giúp khám phá *metadata của khai báo*; nó không làm runtime array component có `List<String>` riêng và không tự kiểm tra dữ liệu phần tử trong một đối tượng `List`. Các thư viện serialization/deserialization có thể dùng `ParameterizedType`/type reference để biết schema được mong đợi, nhưng vẫn cần **thực hiện validation/conversion phù hợp**; chỉ giữ một type descriptor không thể bảo đảm dữ liệu thật luôn đáp ứng.

## 9. Bảo vệ ở ranh giới dữ liệu: kiểm tra từng phần tử

Nếu API bên ngoài trả `Object`/`List<?>`, không chuyển thẳng sang `List<String>` bằng unchecked cast. `instanceof List<?>` chỉ kiểm tra cấp container. Muốn bảo đảm **toàn bộ** phần tử là String, duyệt và copy qua danh sách typed.

Tạo `ValidatedBoundaryDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ValidatedBoundaryDemo {
    static List<String> requireStrings(Object candidate) {
        if (!(candidate instanceof List<?> items)) {
            throw new IllegalArgumentException("not-a-list");
        }

        List<String> result = new ArrayList<>();
        for (int i = 0; i < items.size(); i++) {
            Object item = items.get(i);
            if (!(item instanceof String text)) {
                throw new IllegalArgumentException(
                        "not-string-at-" + i);
            }
            result.add(text);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(
                requireStrings(List.of("red", "blue")));

        try {
            requireStrings(List.of("red", 42));
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ValidatedBoundaryDemo.java
java ValidatedBoundaryDemo
```

```text
[red, blue]
not-string-at-1
```

Đoạn code này **không có unchecked cast**. Nó thực sự xác nhận từng phần tử trước khi tạo và trả một `List<String>` mới, đồng thời tránh alias tới collection nguồn có thể tiếp tục bị sửa.

Một số giới hạn cần biết:

- `null` không đáp ứng `instanceof String` và sẽ bị từ chối. Nếu ứng dụng cho phép null, cần chính sách khác; `List.copyOf` cũng không nhận null.
- Kiểm tra và copy có thể cần bảo đảm snapshot nhất quán nếu nguồn collection có thể bị sửa **đồng thời** bởi thread khác. `List.copyOf` không giải quyết mọi vấn đề concurrency.
- Với `List<List<String>>`/`Map<String, List<Integer>>`, phải xác thực **từng cấp**. Kiểm tra `instanceof List<?>` hay `Map<?,?>` chỉ xác minh cấu trúc ở mức ngoài cùng.
- Việc tạo bản sao không tự làm các đối tượng mutable bên trong bất biến. Trong ví dụ này, phần tử là `String`, nên việc chia sẻ chính phần tử đã kiểm tra là phù hợp.

## 10. Các ngộ nhận cần tránh

| Ngộ nhận | Thực tế |
| --- | --- |
| “`List<String>` và `List<Integer>` là hai class runtime.” | Cả hai có thể là instance cùng `ArrayList.class`, khác hợp đồng compile-time. |
| “Raw type reifiable nghĩa là raw type nên dùng.” | Reifiable nói về khả năng kiểm tra runtime representation; raw type đánh mất bảo đảm generic và thường nên tránh. |
| “`List<?>` reifiable nên chắc chắn chứa String.” | Wildcard `?` có nghĩa **không biết** type argument; chỉ kiểm tra được container. |
| “`List<? extends Number>` reifiable vì Number có class.” | Bounded wildcard vẫn không làm type argument reifiable. |
| “`List<String>.class` tồn tại.” | Chỉ có `List.class`; không có class literal riêng cho parameterized instantiation. |
| “`instanceof List<String>` kiểm tra mọi String bên trong.” | Không có runtime kiểm tra đầy đủ generic argument bằng phép đó. |
| “Array và generics cùng kiểm tra kiểu tại cùng thời điểm.” | Array có component-type checks ở runtime; generic type arguments chủ yếu được compiler kiểm tra. |
| “Tạo `new List<String>[10]` là bình thường.” | Generic array creation với non-reifiable component bị từ chối. |
| “Varargs chỉ là cú pháp đẹp; không ảnh hưởng kiểu.” | Varargs được thực hiện qua array; non-reifiable components có thể dẫn tới unchecked warnings và heap pollution. |
| “`@SafeVarargs` khiến JVM kiểm tra generic element.” | Annotation là cam kết của tác giả API, không thêm runtime checks. |
| “`@SuppressWarnings` xử lý heap pollution.” | Suppression chỉ giấu diagnostics; dữ liệu sai kiểu vẫn có thể lọt qua. |
| “Reflection đọc được `List<String>` nghĩa là object đã có String.” | Reflection có thể đọc signature khai báo, không tự xác minh tất cả phần tử runtime. |

## 11. Cách review generic varargs an toàn

Khi gặp method có chữ ký `static <T> ... method(List<T>... values)` hoặc `T... values`, hãy làm theo quy trình:

1. **Xác định component type có reifiable không.** `String...` khác `List<String>...` và `T...`.
2. **Đọc đầy đủ warnings** bằng `javac -Xlint:unchecked -Xlint:varargs`. Đừng coi tất cả warning là giả.
3. **Tìm các alias của array:** `Object[] alias = values`, field assignment, method calls có thể giữ hoặc sửa array, và lời gọi trả array ra ngoài.
4. **Kiểm tra có ghi vào varargs array không.** Nếu có, xác minh không thể đưa vào một phần tử không đúng type argument.
5. **Kiểm tra từng phần tử được dùng thế nào.** Đọc như `String` có thể gặp `ClassCastException` sau khi heap pollution xảy ra.
6. **Xem liệu API có thể nhận `List`/`Collection` thay cho varargs** để tránh phải tạo array của kiểu non-reifiable hay không.
7. **Chỉ gắn `@SafeVarargs` khi có chứng cứ** rằng body và các helper được gọi không phá an toàn kiểu và không để array thoát ra.
8. **Dùng tests cho các đường biên:** danh sách rỗng, một phần tử, nhiều danh sách, list có null (nếu được cho phép), dữ liệu không tin cậy và runtime type mismatch.
9. **Không dựa vào số lượng test như chứng minh duy nhất:** cần lập luận về bất biến của code; test chỉ kiểm chứng các trường hợp tiêu biểu.
10. **Mô tả contract cho người gọi:** quyền sở hữu/mutation của input collections, khả năng null, danh sách được copy hay alias, và ngoại lệ có thể phát sinh.

Một method như `merge` ở phần 7 có thể sử dụng varargs an toàn vì nó **chỉ đọc** và tạo result mới. Một method như `corrupt` ở phần 6 làm hỏng mảng từ phía bên trong; **không annotate để che lỗi**.

## 12. Bài tập

**Bài 1 — Phân loại kiểu.** Chỉ ra kiểu nào reifiable: `String`, `List`, `List<?>`, `List<String>`, `Map<?,?>`, `Map<String, Integer>`, `String[]`, `List<?>[]`, `List<String>[]`. Giải thích vì sao raw `List` reifiable mà vẫn nguy hiểm.

**Bài 2 — Runtime class.** Chạy `RuntimeTypeDemo`, thay `ArrayList<String>` bằng `LinkedList<String>` và quan sát `getClass()`. Giải thích sự khác biệt giữa class implementation thực tế và type argument.

**Bài 3 — Array store.** Chạy `ArrayRuntimeDemo`. Thử thay phần tử `List<?>` bằng `String` (thông qua `Object[]`) để xem runtime store check của mảng xác nhận được container class nào.

**Bài 4 — Generic varargs warning.** Biên dịch `UnsafeVarargsDemo` với `-Xlint:unchecked`. Xác định warning ở khai báo và lời gọi, rồi chỉ ra dòng làm heap pollution. Không dùng `@SafeVarargs` để che warning của code này.

**Bài 5 — @SafeVarargs.** Chạy `SafeVarargsDemo`. Thử bỏ annotation và quan sát warnings; sau đó giải thích vì sao method gốc an toàn theo bất biến “không mutate, không expose varargs array”.

**Bài 6 — Reflection.** Chạy `ReflectionSignatureDemo`. So sánh `getType()` với `getGenericType()` và trả lời tại sao `List.of(123)` vẫn thỏa `List.class.isInstance(...)`.

**Bài 7 — Validate boundary.** Chạy `ValidatedBoundaryDemo`. Thử thêm list có dữ liệu lẫn `Integer`, dữ liệu `null` và cấu trúc nested, rồi thiết kế hàm kiểm tra đầy đủ trước khi trả `List<String>`.

## 13. Ghi nhớ

- **Reifiable** là khả năng biểu diễn/kiểm tra kiểu ở runtime; `List<?>`/`Map<?,?>` reifiable nhưng **không chứng minh kiểu phần tử**.
- **Type erasure** loại bỏ type arguments khỏi runtime class của một generic instantiation, nhưng metadata khai báo generic có thể vẫn xuất hiện trong class file và reflection.
- **Arrays giữ component type ở runtime**, nên có `ArrayStoreException`; `List<String>` không có runtime class riêng để kiểm tra generic arguments.
- **Generic varargs dùng array**, nên non-reifiable components có thể tạo `unchecked` warnings và heap pollution nếu implementation làm sai.
- **`@SafeVarargs` là cam kết có điều kiện của tác giả**, không phải hệ thống sửa lỗi tự động. Chỉ dùng trên method/constructor đủ điều kiện và đã kiểm chứng không gây thao tác không an toàn.
- **Không biết kiểu dữ liệu thì dùng `<?>` và xác thực ở ranh giới**; không thay bằng unchecked cast sang `List<String>`.
- **Thực hành Java 17+** vẫn cần những nguyên tắc này khi thiết kế APIs generic, varargs, reflection, collections và xử lý dữ liệu động.

## Tài liệu chính thức để đối chiếu

- [JLS `4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7): định nghĩa và phân loại reifiable type.
- [JLS `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6): quy tắc xóa kiểu.
- [JLS `8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.1): varargs parameters và non-reifiable element types.
- [SafeVarargs JavaDoc — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/SafeVarargs.html): hợp đồng annotation và lưu ý về heap pollution.
- [Class JavaDoc — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `isInstance()`, `cast()` và runtime classes.
