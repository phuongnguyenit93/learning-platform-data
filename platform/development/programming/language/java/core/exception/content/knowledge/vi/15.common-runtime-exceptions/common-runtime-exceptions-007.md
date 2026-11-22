# `ClassCastException` và `ArrayStoreException` trong Java: ép kiểu đối tượng và an toàn kiểu của mảng

`ClassCastException` và `ArrayStoreException` đều là **unchecked exceptions** trong Java. Cả hai thường xuất hiện khi một chương trình cố sử dụng một **đối tượng tham chiếu** theo một kiểu không phù hợp với **kiểu runtime thực tế** của đối tượng đó. Tuy nhiên, **thao tác làm phát sinh lỗi hoàn toàn khác nhau**:

- **`ClassCastException`**: thất bại khi một phép **ép kiểu tham chiếu (*reference cast*)** hoặc phép chuyển kiểu tương đương tại runtime cố xem đối tượng như một kiểu mà nó không có.
- **`ArrayStoreException`**: thất bại khi chương trình **ghi một phần tử vào mảng tham chiếu** mà đối tượng phần tử không tương thích với **kiểu phần tử runtime** của mảng.

Một chương trình có thể biên dịch thành công nhưng vẫn gặp một trong hai lỗi này, bởi trình biên dịch chỉ có một phần thông tin kiểu ở thời điểm compile, trong khi JVM kiểm tra kiểu thực tế khi phép ép kiểu hoặc phép ghi mảng chạy.

Hai ví dụ ngắn minh họa sự khác biệt:

```java
Object value = "Java";
Integer number = (Integer) value; // ClassCastException
```

```java
Object[] values = new String[1];
values[0] = Integer.valueOf(10); // ArrayStoreException
```

Hai đoạn trên là **các ví dụ cố ý ném lỗi runtime**, không phải chương trình đầy đủ. Ở ví dụ thứ nhất, `value` thật ra là một `String`, không phải `Integer`. Ở ví dụ thứ hai, biến `values` có **kiểu tĩnh** `Object[]`, nhưng chính mảng được tạo ra là **`String[]`**, nên nó chỉ được chứa `String` hoặc `null`.

## 1. Vị trí trong hệ phân cấp ngoại lệ

Cả hai lớp đều thuộc `java.lang`:

```text
java.lang.Object
└── java.lang.Throwable
    └── java.lang.Exception
        └── java.lang.RuntimeException
            ├── java.lang.ClassCastException
            └── java.lang.ArrayStoreException
```

Đây là **trích đoạn cây kế thừa**, không liệt kê mọi subtype của `RuntimeException`.

| Thuộc tính | `ClassCastException` | `ArrayStoreException` |
| --- | --- | --- |
| Nhóm | Unchecked, extends `RuntimeException` | Unchecked, extends `RuntimeException` |
| Thao tác điển hình | Ép kiểu reference không hợp lệ | Ghi phần tử sai kiểu vào reference array |
| Ví dụ | `(Integer) (Object) "abc"` | Ghi `42` vào mảng thực `String[]` qua `Object[]` |
| Kiểu được kiểm tra | Kiểu runtime của **đối tượng bị ép** so với kiểu đích | Kiểu runtime của **phần tử** so với component type thực của mảng |
| Có thể xảy ra dù biên dịch thành công? | Có | Có |
| Có nhất thiết phải có ép kiểu tường minh trong source? | Không; có thể do cast do compiler chèn, ví dụ khi đọc generic | Không; assignment vào array là đủ |
| Có nhất thiết phải có mảng? | Không | Có, hoặc API liên quan thao tác sao chép/lưu trữ vào mảng |
| Cách phòng tránh trọng tâm | Mô hình kiểu đúng, kiểm tra `instanceof` / `Class.isInstance` khi cần | Không dựa vào tính covariance để ghi phần tử không phù hợp; dùng container generic đúng thiết kế |

**Đừng dùng một `catch (RuntimeException)` rộng để “sửa” hai lỗi này một cách mặc định.** Chúng thường là dấu hiệu của lỗi thiết kế hoặc sai giả định về kiểu, không phải điều kiện nghiệp vụ bình thường có thể bỏ qua.

## 2. Kiểu tĩnh và kiểu runtime: nguyên nhân chung

Java kiểm tra nhiều điều kiện bằng **kiểu tĩnh** mà trình biên dịch nhìn thấy ở biểu thức. Nhưng đối tượng được tạo ra trong bộ nhớ có **kiểu runtime** cụ thể.

```java
Object text = "hello";
```

- Kiểu tĩnh của biến `text` là `Object`.
- Kiểu runtime của đối tượng được tham chiếu là `String`.
- `text instanceof String` là `true`.
- `text instanceof Integer` là `false`.
- Phép ép `(String) text` thành công.
- Phép ép `(Integer) text` biên dịch được nhưng ném `ClassCastException` khi chạy.

Tương tự với mảng:

```java
Object[] elements = new String[2];
```

- Kiểu tĩnh của `elements` là `Object[]`.
- Kiểu runtime của đối tượng mảng là `String[]`.
- Thành phần thực được mảng cho phép lưu là `String` (hoặc `null`).
- `elements[0] = "ok";` thành công.
- `elements[1] = new Object();` ném `ArrayStoreException`.

**Cùng một khác biệt tĩnh/runtime, nhưng hai điểm kiểm tra runtime khác nhau:** kiểm tra *cast* so với kiểm tra *store*.

### Không nhầm “kiểu của biến” với “kiểu của object”

Một biến kiểu `Object` có thể tham chiếu tới rất nhiều loại đối tượng. Java không tự biến mọi object thành một kiểu mới khi gán tham chiếu sang biến cha. Việc `Object value = "hello";` không làm đối tượng `String` trở thành một `Integer` hay `Object` “thuần” mất kiểu gốc.

Với mảng, việc gán `String[]` cho biến `Object[]` cũng không đổi **component type thực** của mảng từ `String` thành `Object`. Kiểm tra lúc ghi vẫn dựa trên mảng thực.

## 3. `ClassCastException` xuất hiện khi nào?

Một reference cast có thể thành công hoặc thất bại dựa trên khả năng đối tượng runtime là instance của kiểu đích.

### Ép kiểu hợp lệ

```java
Object object = "Java";
String language = (String) object;
System.out.println(language);
```

Kết quả:

```text
Java
```

Vì object thực sự là `String`, phép ép kiểu thành công.

### Ép kiểu sai: runtime phát hiện

```java
Object object = "Java";
Integer number = (Integer) object;
```

Trình biên dịch chấp nhận vì `object` có kiểu tĩnh `Object`, nên về nguyên tắc có thể trỏ tới một `Integer`. Tại runtime, object thực sự là `String`, và `String` không phải `Integer`, nên JVM ném `ClassCastException`.

Nếu viết trực tiếp:

```java
// Cố ý KHÔNG BIÊN DỊCH.
String text = "Java";
Integer number = (Integer) text;
```

hai kiểu lớp `String` và `Integer` không có quan hệ chuyển đổi reference cast phù hợp ở đây; trình biên dịch có thể loại bỏ phép ép ngay. Vì vậy **không phải mọi ý định ép kiểu sai đều chờ đến runtime**. `ClassCastException` xảy ra trong những tình huống compiler cho phép kiểm tra khi chạy.

### Downcast từ lớp cha

```java
class Animal {}

class Dog extends Animal {
    void bark() {}
}

class Cat extends Animal {}
```

Đây là các khai báo minh họa. Với:

```java
Animal animal = new Cat();
Dog dog = (Dog) animal; // ClassCastException.
```

Biên dịch thành công vì `animal` là `Animal`, còn `Dog` là subtype có thể xảy ra của `Animal`. Nhưng object thực là `Cat`, không phải `Dog`.

**Bài học:** downcast không làm object đổi từ `Cat` sang `Dog`; nó chỉ kiểm tra xem object đã có đúng kiểu đích hay chưa.

## 4. Phép kiểm tra bằng `instanceof` và pattern matching trong Java 17

Khi chương trình thật sự phải làm việc với các đối tượng đa dạng, có thể kiểm tra kiểu trước khi ép:

```java
Object value = "sample";

if (value instanceof String text) {
    System.out.println("length=" + text.length());
} else {
    System.out.println("not a String");
}
```

Đây là đoạn Java hợp lệ trong một phương thức. Java 17 hỗ trợ **pattern matching for `instanceof`**: khi điều kiện đúng, biến `text` có kiểu `String`, giúp tránh một cast lặp lại.

Không cần viết:

```java
if (value instanceof String) {
    String text = (String) value;
}
```

trong những trường hợp pattern matching diễn đạt rõ hơn. Tuy nhiên, **`instanceof` không thay thế thiết kế hệ kiểu**. Nếu lúc nào cũng phải kiểm tra hàng chục kiểu bằng một chuỗi `if`, có thể interface/polymorphism hoặc kiểu dữ liệu có cấu trúc phù hợp hơn.

### `instanceof` với `null`

```java
Object value = null;

System.out.println(value instanceof String);
String text = (String) value;
System.out.println(text == null);
```

Stdout:

```text
false
true
```

- `null instanceof String` là `false`.
- Ép reference `null` sang `String` **không ném `ClassCastException`**; kết quả vẫn là `null`.
- Việc gọi phương thức trên giá trị null sau đó có thể ném **`NullPointerException`**, là loại lỗi khác.

**Đừng nhầm ép kiểu null thành công với object tồn tại và có thể sử dụng được.**

### `Class.isInstance` và `Class.cast`

Khi kiểu đích chỉ biết tại runtime qua một đối tượng `Class<T>`, có thể dùng:

```java
Class<String> type = String.class;
Object value = "hello";

System.out.println(type.isInstance(value));
String result = type.cast(value);
```

`type.isInstance(value)` trả `true`, còn `type.cast(value)` trả cùng object sau khi kiểm tra kiểu. Nếu giá trị không phù hợp, `Class.cast` ném `ClassCastException`. Với `null`, `cast(null)` trả `null`.

Các API này hữu ích cho framework/reflection/deserialization có kiểu đích động, nhưng không nên thêm reflection cho một trường hợp mà generic type hoặc polymorphism đã đủ.

## 5. `ArrayStoreException` xuất hiện khi nào?

`ArrayStoreException` có thể phát sinh khi **một đối tượng không tương thích được gán vào một mảng của kiểu tham chiếu**.

```java
String[] names = new String[2];
Object[] anyObjects = names;

anyObjects[0] = "Alice";       // Thành công.
anyObjects[1] = Integer.valueOf(5); // ArrayStoreException.
```

Điểm then chốt: **mảng vẫn là `String[]`**. Biến `anyObjects` có thể nhìn nó như một `Object[]` nhưng không làm nó trở thành mảng lưu được mọi loại object.

### Tại sao trình biên dịch lại cho phép?

Vì Java cho phép **covariance của reference array**: nếu `String` là subtype của `Object` thì `String[]` cũng có thể được dùng như `Object[]`.

```java
String[] source = new String[2];
Object[] destination = source; // Hợp lệ.
```

Khả năng gán này tiện khi đọc hoặc đi qua API cần `Object[]`, nhưng **không an toàn kiểu hoàn toàn với thao tác ghi**. JVM phải kiểm tra mỗi lần ghi để bảo vệ tính đúng đắn của mảng runtime.

Nếu loại bỏ kiểm tra runtime, mảng `String[]` có thể chứa `Integer`, khiến mã đọc `String` về sau gặp lỗi khó hiểu. Vì vậy JVM chủ động ném `ArrayStoreException` **ngay tại phép ghi không tương thích**.

### Kiểu phần tử runtime không phải kiểu tĩnh của biến mảng

```java
Number[] values = new Integer[2];

values[0] = Integer.valueOf(1); // Đúng.
values[1] = Long.valueOf(2L);   // ArrayStoreException.
```

`Integer[]` là subtype của `Number[]`, nên phép gán mảng ban đầu hợp lệ. Nhưng mảng thực là `Integer[]` nên không nhận object `Long`, dù `Long` cũng extends `Number`.

### `null` là phần tử hợp lệ cho reference array

```java
Object[] values = new String[2];
values[0] = null;      // Hợp lệ.
values[1] = "hello";   // Hợp lệ.
```

`null` không phải instance của `String` nhưng **được phép lưu trong mảng tham chiếu**. Không có `ArrayStoreException` cho phép gán null hợp lệ này.

Điều đó khác với mảng nguyên thủy như `int[]`: phần tử là `int`, không thể gán null cho một vị trí `int`.

## 6. Ví dụ Java 17+ chạy được: phân biệt hai ngoại lệ trong cùng chương trình

Lưu toàn bộ mã thành **`CastAndArrayStoreDemo.java`**:

```java
import java.util.Arrays;

public class CastAndArrayStoreDemo {

    static void wrongCast() {
        Object value = "Java";

        try {
            Integer number = (Integer) value;
            System.out.println(number);
        } catch (ClassCastException ex) {
            System.out.println(
                    "object cast=" + ex.getClass().getSimpleName());
        }

        if (value instanceof String text) {
            System.out.println("safe text=" + text);
        }
    }

    static void wrongArrayStore() {
        Object[] values = new String[2];
        values[0] = "alpha";

        try {
            values[1] = Integer.valueOf(42);
        } catch (ArrayStoreException ex) {
            System.out.println(
                    "array store=" + ex.getClass().getSimpleName());
        }

        System.out.println(
                "array content=" + Arrays.toString(values));
    }

    static void wrongArrayCast() {
        Object value = new String[] {"A", "B"};

        try {
            Integer[] numbers = (Integer[]) value;
            System.out.println(numbers.length);
        } catch (ClassCastException ex) {
            System.out.println(
                    "array cast=" + ex.getClass().getSimpleName());
        }

        if (value instanceof String[] names) {
            System.out.println("string array length=" + names.length);
        }
    }

    static void numberArrayStore() {
        Number[] values = new Integer[2];
        values[0] = Integer.valueOf(7);

        try {
            values[1] = Long.valueOf(9L);
        } catch (ArrayStoreException ex) {
            System.out.println(
                    "number store=" + ex.getClass().getSimpleName());
        }

        System.out.println(
                "numbers=" + Arrays.toString(values));
    }

    static void nullIsAllowed() {
        Object value = null;
        String text = (String) value;
        Object[] values = new String[1];
        values[0] = null;

        System.out.println("null cast=" + (text == null));
        System.out.println("null array store=" + (values[0] == null));
    }

    public static void main(String[] args) {
        wrongCast();
        wrongArrayStore();
        wrongArrayCast();
        numberArrayStore();
        nullIsAllowed();
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 CastAndArrayStoreDemo.java
java CastAndArrayStoreDemo
```

**Stdout chính xác:**

```text
object cast=ClassCastException
safe text=Java
array store=ArrayStoreException
array content=[alpha, null]
array cast=ClassCastException
string array length=2
number store=ArrayStoreException
numbers=[7, null]
null cast=true
null array store=true
```

### Giải thích từng nhánh

**`wrongCast()`:** object thực là `String`, nhưng cast sang `Integer`. JVM ném `ClassCastException`. Handler in tên lớp đơn giản; sau đó `instanceof String text` cho phép truy cập `String` an toàn.

**`wrongArrayStore()`:** mảng thực là `String[2]`. Ghi `"alpha"` đúng; ghi `Integer(42)` vào vị trí thứ hai ném `ArrayStoreException`, nên phần tử đó vẫn `null`. Lệnh `Arrays.toString` cho thấy phần tử không được ghi thành công.

**`wrongArrayCast()`:** `value` tham chiếu một mảng `String[]` nhưng bị ép sang `Integer[]`. Đó là **lỗi cast đối tượng mảng**, vì vậy ngoại lệ là `ClassCastException`, **không phải `ArrayStoreException`**. Sau đó `instanceof String[]` nhận diện chính xác kiểu runtime của mảng.

**`numberArrayStore()`:** biến `Number[]` trỏ tới mảng `Integer[]`. `Integer(7)` phù hợp; `Long(9)` không phù hợp với component type runtime `Integer`, nên ném `ArrayStoreException`.

**`nullIsAllowed()`:** cast null sang reference type và lưu null vào reference array đều hợp lệ. Kết quả của hai phép kiểm tra là `true`.

Chương trình không in message đầy đủ hoặc stack trace của exception, vì cách diễn đạt chi tiết của message có thể thay đổi theo JDK. In `getClass().getSimpleName()` và trạng thái mảng giúp giữ stdout ổn định.

## 7. Ép kiểu chính đối tượng mảng có thể là `ClassCastException`

Hai dòng này không tương đương:

```java
Object value = new String[2];
Integer[] numbers = (Integer[]) value; // ClassCastException.
```

```java
Object[] values = new String[2];
values[0] = Integer.valueOf(1);        // ArrayStoreException.
```

Ở đoạn một, object được kiểm tra là **toàn bộ mảng `String[]`**, rồi cast sang `Integer[]`. Không có phép ghi phần tử.

Ở đoạn hai, phép gán `values[0] = ...` kiểm tra **một giá trị phần tử** đối với mảng runtime `String[]`. Không hề có cast sang `Integer[]`.

Đây là cách phân biệt nhanh trong lúc đọc stack trace:

- Xem dòng gây lỗi có **`(TargetType) value`**, `Class.cast(value)`, hoặc chuyển kiểu do compiler chèn không?
- Hay có phép **`array[index] = element`** qua một biến mảng rộng kiểu, hoặc một API sao chép phần tử vào mảng?
- Xác định **kiểu runtime thật** của object và mảng tại điểm xảy ra lỗi.

Không nên dựa duy nhất vào từ khóa trong message, vì message chẩn đoán không phải định dạng hợp đồng ổn định.

## 8. Arrays covariance: tại sao Java cho phép nhưng vẫn có rủi ro?

Với các **kiểu tham chiếu** `S` và `T`, khi `S` là subtype của `T`, Java cho phép gán `S[]` cho `T[]`:

```java
String[] strings = {"a", "b"};
Object[] objects = strings;
```

Vì `String[]` là subtype của `Object[]`, phép gán hợp lệ. Nhưng phép gán này không tạo ra một mảng `Object[]` mới; **hai biến trỏ cùng object mảng `String[]`**.

Covariance hữu ích cho một số API đọc dữ liệu, nhưng nếu caller ghi một object chỉ tương thích với `T` mà không tương thích `S`, lỗi runtime sẽ xảy ra.

### Ví dụ giả định API nhận mảng rộng kiểu

```java
static void putDefault(Object[] array) {
    array[0] = new Object();
}
```

Đây là phương thức minh họa. Nếu truyền `new Object[1]` thì phép ghi hợp lệ. Nếu truyền `new String[1]` thì phép ghi ném `ArrayStoreException`.

**Cùng một chữ ký phương thức**, nhưng tính hợp lệ của phép ghi phụ thuộc **runtime component type** của mảng mà caller đưa tới.

Một API chỉ cần **đọc** các phần tử thường nên không sửa mảng đầu vào. Nếu thật sự cần thay đổi phần tử, nên thiết kế kiểu tham số đủ cụ thể, định rõ loại phần tử được phép hoặc dùng generic collection phù hợp.

### Mảng reference được kiểm tra kiểu khi ghi

Có thể xem runtime component type bằng:

```java
Object[] values = new String[2];
System.out.println(
        values.getClass().getComponentType().getSimpleName());
```

Kết quả:

```text
String
```

Từ `Object[]` ở khai báo biến không được dùng để suy luận mảng thực có thể giữ bất kỳ object nào.

## 9. Mảng nguyên thủy không có covariance như mảng tham chiếu

`int[]`, `long[]`, `double[]` là các object mảng trong Java, nhưng **không có quan hệ subtype `int[] extends Object[]`**.

Ví dụ:

```java
int[] numbers = {1, 2, 3};
Object container = numbers; // Được: mọi mảng là Object.
```

Nhưng:

```java
// Cố ý KHÔNG BIÊN DỊCH.
Object[] objects = new int[3];
```

`int[]` không thể gán sang `Object[]` vì thành phần `int` là primitive, không phải reference subtype của `Object`.

### Ép kiểu primitive và `ClassCastException` là hai vấn đề khác nhau

Ép `long` sang `int` là **primitive numeric conversion**:

```java
long large = 1_000_000_000_000L;
int narrowed = (int) large;
```

Đoạn này có thể làm mất thông tin số do narrowing conversion, nhưng **không ném `ClassCastException`** chỉ vì giá trị nằm ngoài phạm vi `int`.

`ClassCastException` liên quan reference casts/chuyển kiểu reference tại runtime; `ArrayStoreException` liên quan lưu reference vào mảng runtime không tương thích. Không nên dùng hai lỗi này để mô tả tràn số khi chuyển primitive.

## 10. Generics khác arrays: invariance và type erasure

Một nguồn gây nhầm lẫn là so sánh:

```java
String[] strings = new String[2];
Object[] objects = strings; // Hợp lệ: array covariance.
```

với:

```java
java.util.List<String> strings = new java.util.ArrayList<>();
// java.util.List<Object> objects = strings; // Không biên dịch.
```

`List<String>` **không phải subtype của `List<Object>`**. Generic type parameter của `List<T>` mặc định **invariant**, khác với covariance của reference array.

Sự bất biến này chặn tại compile time việc biến một `List<String>` thành `List<Object>` để thêm `Integer` tùy ý.

### Type erasure tạo một kiểu bẫy khác cho `ClassCastException`

Với generics, Java dùng **type erasure**: tham số `T` thường không còn như một “tag” của từng `List<T>` ở runtime. Vì thế một cast có cảnh báo chưa chắc thất bại ngay tại thời điểm cast; lỗi có thể xảy ra lúc lấy phần tử ra khỏi collection.

```java
java.util.List<Integer> numbers =
        new java.util.ArrayList<>();
numbers.add(10);

Object asObject = numbers;

@SuppressWarnings("unchecked")
java.util.List<String> texts =
        (java.util.List<String>) asObject;

// String text = texts.get(0); // Có thể ClassCastException tại đây.
```

Đây là đoạn minh họa. Cast sang `List<String>` có thể qua được vì runtime kiểm tra object có phải `List` phù hợp không, **không thể kiểm tra toàn bộ tham số generic `String` bị xóa**. Khi gọi `texts.get(0)` và nhận kết quả theo kiểu `String`, compiler có thể chèn checkcast; giá trị thực `Integer` không phù hợp, dẫn đến `ClassCastException`.

**Không hiểu sai:** việc suppress compiler warning không “làm cast an toàn”. `@SuppressWarnings("unchecked")` chỉ tắt cảnh báo ở phạm vi đó; nó không thay đổi dữ liệu trong collection và không thêm kiểm tra kiểu runtime cần thiết.

## 11. Ví dụ Java 17+ chạy được: heap pollution và `ClassCastException` xuất hiện muộn

Lưu tệp **`GenericCastDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericCastDemo {

    static void unsafeGenericCast() {
        List<Integer> numbers = new ArrayList<>();
        numbers.add(17);

        Object stored = numbers;

        @SuppressWarnings("unchecked")
        List<String> texts = (List<String>) stored;

        System.out.println("list cast reached");

        try {
            String text = texts.get(0);
            System.out.println(text);
        } catch (ClassCastException ex) {
            System.out.println(
                    "element read=" + ex.getClass().getSimpleName());
        }
    }

    static void safeReadUsingWildcard() {
        List<Integer> numbers = List.of(17);

        List<?> unknown = numbers;
        Object element = unknown.get(0);

        System.out.println(
                "element type=" + element.getClass().getSimpleName());

        if (element instanceof Integer number) {
            System.out.println("safe integer=" + number);
        }
    }

    static void checkArrayType() {
        Object data = new String[] {"one", "two"};

        if (data instanceof String[] texts) {
            System.out.println("array first=" + texts[0]);
        }

        System.out.println(
                "is Integer[]=" + (data instanceof Integer[]));
    }

    public static void main(String[] args) {
        unsafeGenericCast();
        safeReadUsingWildcard();
        checkArrayType();
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GenericCastDemo.java
java GenericCastDemo
```

**Stdout chính xác:**

```text
list cast reached
element read=ClassCastException
element type=Integer
safe integer=17
array first=one
is Integer[]=false
```

### Tại sao dòng `list cast reached` được in?

Cast sang `List<String>` vượt qua kiểm tra runtime ở mức `List`. Kiểu tham số `String` không được kiểm tra hoàn chỉnh do type erasure. Khi lệnh `String text = texts.get(0);` yêu cầu giá trị là `String`, object thực từ list là `Integer` và JVM ném `ClassCastException`.

Ví dụ `safeReadUsingWildcard` dùng `List<?>` vì chưa biết kiểu phần tử. Đọc ra `Object` rồi kiểm tra `instanceof Integer` trước khi dùng là hợp lý hơn **ép cả danh sách thành `List<String>` không có cơ sở**.

### Vì sao đây không phải `ArrayStoreException`?

`ArrayList` lưu phần tử bằng một cấu trúc nội bộ, nhưng người dùng đang thao tác thông qua **API `List` và generic cast**, không làm một phép ghi `Integer` trực tiếp vào object mảng thực `String[]`. Lỗi quan sát được là cast của phần tử khi đọc, không phải vi phạm runtime component type của một `String[]`.

Không suy đoán kiểu lỗi chỉ từ việc một collection có thể dùng mảng nội bộ; phải xác định **thao tác Java/API gây lỗi ở mức chương trình**.

## 12. Vì sao không thể tạo trực tiếp `new List<String>[10]`?

Java không cho tạo mảng với loại thành phần là một kiểu generic parameterized không reifiable như `List<String>`:

```java
// Cố ý KHÔNG BIÊN DỊCH: generic array creation.
java.util.List<String>[] lists =
        new java.util.List<String>[10];
```

Một lý do thiết kế là mảng thực hiện runtime component-type checks, trong khi thông tin tham số generic như `String` của `List<String>` thường bị erasure. Nếu tạo mảng parameterized như vậy, hệ thống kiểm tra kiểu có thể tạo ảo giác an toàn khó giữ được.

Thay vì dùng mảng generic trực tiếp, đa số trường hợp nên dùng:

```java
java.util.List<java.util.List<String>> groups =
        new java.util.ArrayList<>();
```

Một `List<List<String>>` dùng generic type checking ở compile time cho các phép thêm đọc theo API `List`, tránh dựa vào array covariance.

**Lưu ý:** Java vẫn cho phép một số dạng mảng có kiểu thành phần *reifiable*, ví dụ `List<?>[]`; điều đó không làm cho `new List<String>[10]` trở thành hợp lệ.

## 13. `System.arraycopy` cũng có thể ném `ArrayStoreException`

Không chỉ phép gán dạng `array[index] = value`. Nếu bạn sao chép phần tử từ một mảng sang mảng đích có component type không tương thích, `System.arraycopy` có thể ném `ArrayStoreException`.

```java
Object[] source = {"ok", Integer.valueOf(7), "later"};
String[] destination = {"old-0", "old-1", "old-2"};

System.arraycopy(source, 0, destination, 0, source.length);
```

Đây là đoạn minh họa cố ý ném lỗi runtime. Mảng nguồn có phần tử đầu là `String` nhưng phần tử thứ hai là `Integer`. Mảng đích là `String[]`, không thể nhận `Integer`.

Một khác biệt quan trọng so với một phép gán đơn: **`arraycopy` có thể đã sao chép một phần tử hợp lệ trước khi gặp phần tử không tương thích**, nên trạng thái mảng đích có thể đã bị thay đổi một phần khi ngoại lệ được ném.

Với dạng `Object[]` → `String[]` và dữ liệu cụ thể ở trên, `System.arraycopy` chuyển phần tử `"ok"` đầu tiên trước khi gặp `Integer(7)`. Nó ném `ArrayStoreException` và không hoàn tất toàn bộ phép sao chép.

### Đừng suy ra phép sao chép là “all-or-nothing”

Nếu cần thao tác nguyên tử về ngữ nghĩa, hãy validate dữ liệu trước và cân nhắc tạo mảng mới hoặc một cấu trúc kết quả chỉ được công bố sau khi kiểm tra thành công. `System.arraycopy` không phải transaction.

## 14. Ví dụ Java 17+ chạy được: sao chép mảng có lỗi kiểu và trạng thái một phần

Lưu **`ArrayCopyFailureDemo.java`**:

```java
import java.util.Arrays;

public class ArrayCopyFailureDemo {

    public static void main(String[] args) {
        Object[] source = {
                "ok", Integer.valueOf(7), "later"
        };

        String[] destination = {
                "old-0", "old-1", "old-2"
        };

        try {
            System.arraycopy(
                    source, 0, destination, 0, source.length);
        } catch (ArrayStoreException ex) {
            System.out.println(
                    "copy error=" + ex.getClass().getSimpleName());
        }

        System.out.println(
                "destination=" + Arrays.toString(destination));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ArrayCopyFailureDemo.java
java ArrayCopyFailureDemo
```

**Stdout chính xác:**

```text
copy error=ArrayStoreException
destination=[ok, old-1, old-2]
```

### Phân tích

- Phần tử nguồn `source[0]` là `String("ok")`, tương thích với `String[]`, nên được sao chép vào `destination[0]`.
- Phần tử `source[1]` là `Integer(7)`, không thể lưu trong mảng `String[]`, nên thao tác báo `ArrayStoreException`.
- `destination[1]` và `destination[2]` vẫn giữ các giá trị cũ trong trường hợp này.
- Handler chỉ bắt lỗi, **không rollback** thay đổi `destination[0]`.

Đây là lý do cần cân nhắc trạng thái dữ liệu sau khi bắt `ArrayStoreException` từ một API sao chép. Không nên bắt lỗi rồi mặc định xem mảng đích chưa bị động tới.

## 15. Phân biệt với các lỗi mảng hoặc reference khác

Các tình huống có vẻ giống nhau nhưng thực tế khác loại:

| Mã/sự kiện | Lỗi tương ứng | Nguyên nhân |
| --- | --- | --- |
| `(Integer) (Object) "s"` | `ClassCastException` | Reference cast sai kiểu runtime |
| `Object[] a = new String[1]; a[0] = 1;` | `ArrayStoreException` | Lưu object không tương thích với component type |
| `Object[] a = null; a[0] = "x";` | `NullPointerException` | Biến mảng tham chiếu null |
| `String[] a = new String[1]; a[5] = "x";` | `ArrayIndexOutOfBoundsException` | Vị trí truy cập ngoài phạm vi |
| `String value = (String) null;` | Không lỗi tại cast | Reference null có thể cast sang reference type |
| `Object[] a = new String[1]; a[0] = null;` | Không lỗi | Null hợp lệ cho reference array |
| `int n = (int) 1_000_000_000_000L;` | Không phải `ClassCastException` | Numeric narrowing conversion primitive |
| `Object a = new int[2];` | Không lỗi | Mảng primitive vẫn là object |
| `Object[] a = new int[2];` | Lỗi biên dịch | `int[]` không phải `Object[]` |

Đừng dùng `catch (ClassCastException | ArrayStoreException ex)` như một cơ chế kiểm soát kiểu bình thường khi có thể thiết kế code để không tạo tình huống sai ngay từ đầu.

### `NumberFormatException` không phải `ClassCastException`

`Integer.parseInt("abc")` thất bại vì nội dung chuỗi không phải biểu diễn số nguyên hợp lệ. Đây là `NumberFormatException`, không phải lỗi ép một object `String` thành object `Integer`. Parse một giá trị và reference cast giữa các object là hai thao tác khác nhau.

### Không cố đoán lỗi từ thứ tự đánh giá nhiều vấn đề cùng lúc

Nếu một câu lệnh vừa dùng mảng null, vừa chỉ số sai, vừa giá trị không tương thích, loại lỗi đầu tiên phụ thuộc quy tắc đánh giá và kiểm tra của biểu thức. Khi học hai loại lỗi, hãy dùng ví dụ chỉ có **một điều kiện sai chính**; khi debug thực tế, xem stack trace và dòng mã, không suy luận từ nhiều giả định không kiểm chứng.

## 16. Cách phòng tránh `ClassCastException` trong thiết kế API

### Ưu tiên polymorphism thay vì downcast

Nếu tất cả đối tượng có một hành vi chung, đưa hành vi ấy lên interface:

```java
interface Renderer {
    String render();
}

final class TextRenderer implements Renderer {
    @Override
    public String render() {
        return "text";
    }
}

final class HtmlRenderer implements Renderer {
    @Override
    public String render() {
        return "html";
    }
}
```

Đây là các lớp minh họa, không cần ép từ `Renderer` xuống `TextRenderer` hoặc `HtmlRenderer` để gọi `render()`. Caller chỉ viết:

```java
String output = renderer.render();
```

nếu `renderer` là biến kiểu `Renderer` hợp lệ.

Điều này giúp mở rộng subtype mới mà không phải cập nhật một chuỗi cast liên tục.

### Dùng generics đúng kiểu

Một API nhận danh sách tên nên ưu tiên `List<String>`, không phải `List<Object>` mà caller phải downcast từng phần tử. Nếu dữ liệu thực sự có nhiều kiểu, xem xét một interface chung, `sealed hierarchy`, record có tag hoặc `List<?>` với kiểm tra kiểu rõ ràng.

### Kiểm tra kiểu ở ranh giới dữ liệu không đáng tin

Với reflection, plugin hoặc deserialization mà object đến từ bên ngoài:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        return "text:" + text;
    }
    if (value instanceof Integer number) {
        return "number:" + number;
    }
    return "unsupported";
}
```

Đây là phương thức Java độc lập có thể đặt trong lớp. Nó sử dụng pattern matching thay vì ép kiểu mù quáng. Tuy nhiên, ở API public nên chọn chính sách rõ khi gặp loại không hỗ trợ: trả lỗi validation, từ chối input, hoặc mô hình hóa kiểu kết quả thích hợp, chứ không chỉ mặc định bỏ qua.

### Dùng `Class<T>` khi kiểu được truyền vào lúc chạy

```java
static <T> T requireType(Object value, Class<T> type) {
    if (!type.isInstance(value)) {
        throw new IllegalArgumentException(
                "unexpected value type");
    }
    return type.cast(value);
}
```

Đây là phương thức minh họa, với hợp đồng **không chấp nhận null**. `isInstance(null)` là `false`, nên hàm chủ động từ chối null trước khi cast. Cách này có ích khi phương thức nhận dữ liệu động cùng một `Class<T>` làm “type token”.

**Không dùng `Class<T>` nếu cần biểu diễn đầy đủ tham số generic như `List<String>`**: `List.class` không giữ nguyên `String` là tham số type ở runtime.

## 17. Cách phòng tránh `ArrayStoreException`

### Không gán bừa vào mảng được truyền bằng kiểu quá rộng

Một hàm:

```java
static void fill(Object[] target, Object value) {
    target[0] = value;
}
```

có thể thất bại nếu mảng runtime hẹp hơn kiểu `Object[]`. Nếu caller có thể truyền `String[]`, `Integer[]` hoặc `Number[]`, hàm không được mặc định rằng mọi `Object` đều hợp lệ cho mảng.

Những chiến lược tốt hơn:

1. **Không sửa mảng của caller** nếu nhiệm vụ thực sự chỉ cần đọc.
2. **Giữ kiểu phần tử ở API** bằng generics hoặc kiểu cụ thể.
3. **Tạo mảng có component type đúng**, nếu hàm chịu trách nhiệm sở hữu dữ liệu.
4. **Xác thực dữ liệu** khi nhận từ nguồn động trước khi ghi hàng loạt.
5. **Không dựa vào `Object[]` làm vùng chứa tùy ý** nếu mảng thực có thể là một array subtype hẹp.
6. Nếu dùng `System.arraycopy`, tính đến khả năng sao chép một phần khi lỗi.
7. Nếu cần sưu tập có thể thêm đa dạng object, dùng một `ArrayList<Object>` thực sự được khai báo để chứa `Object`, hoặc mô hình kiểu chung phù hợp.

### Generic collections thường an toàn hơn cho thao tác thêm

`List<String>` cho phép compiler từ chối:

```java
java.util.List<String> values =
        new java.util.ArrayList<>();

// values.add(Integer.valueOf(7)); // Không biên dịch.
```

Với các thao tác thông thường không dùng raw/unchecked casts, `List<String>` giúp compiler chặn thêm `Integer` ngay từ đầu, trong khi `Object[]` có thể trỏ tới `String[]` và chỉ ném lỗi lúc chạy.

**Không nói rằng collection generics “không bao giờ sai kiểu”.** Raw types, unchecked casts, reflection và code không an toàn vẫn có thể gây *heap pollution*, và lúc đọc phần tử có thể gặp `ClassCastException`. Generics nâng khả năng kiểm tra ở compile time, nhưng không thay thế việc tuân thủ API.

### Về mảng bất biến

Nếu không cần thay đổi phần tử, cân nhắc trả `List.copyOf(...)` hoặc một cấu trúc immutable phù hợp. Điều này tránh một lớp rủi ro ghi sai kiểu, đồng thời làm hợp đồng dễ hiểu hơn. Tuy nhiên, `List.copyOf` từ chối phần tử null; hãy đọc hợp đồng cụ thể thay vì coi mọi collection immutable có hành vi giống mảng.

## 18. Cách đọc stack trace và chẩn đoán nhanh

Cả hai lỗi thường có stack trace mô tả vị trí hoạt động không hợp lệ. Ví dụ định dạng minh họa:

```text
java.lang.ClassCastException: <runtime class> cannot be cast to <target>
    at example.Service.convert(Service.java:<line>)
    at example.Main.main(Main.java:<line>)
```

```text
java.lang.ArrayStoreException: <incompatible type>
    at example.Service.fill(Service.java:<line>)
    at example.Main.main(Main.java:<line>)
```

Đây **không phải thông điệp nguyên văn cố định**: nội dung message, tên module, class loader và số dòng có thể khác theo JDK, bytecode và nguồn gây lỗi.

### Quy trình điều tra `ClassCastException`

1. Xác định **biểu thức cast** tại frame liên quan: tường minh, `Class.cast`, hoặc cast ngầm khi đọc generic.
2. In/quan sát **kiểu runtime thật** của object, nếu dữ liệu không nhạy cảm.
3. Xác định **kiểu đích** mà code kỳ vọng.
4. Truy nguồn đối tượng được tạo/gán ở đâu: class thực, map, deserialization, reflection, raw generic, plugin...
5. Chọn sửa thiết kế kiểu, kiểm tra `instanceof`, hoặc chuyển đổi dữ liệu thực sự thay vì ép kiểu.
6. Kiểm tra lại các đường null và dữ liệu không hợp lệ.

Ví dụ xem kiểu runtime:

```java
Object value = "Java";
System.out.println(value.getClass().getName());
```

Stdout:

```text
java.lang.String
```

Cần bảo vệ null trước khi gọi `getClass()`. Không sử dụng `getClass()` như một phần logic nghiệp vụ nếu polymorphism đã diễn đạt hợp đồng tốt hơn.

### Quy trình điều tra `ArrayStoreException`

1. Tìm điểm ghi `array[index] = value` hoặc `System.arraycopy`.
2. Xác định **kiểu runtime của mảng** bằng `array.getClass()` và `getComponentType()`.
3. Xác định kiểu runtime của **giá trị đang ghi**.
4. Kiểm tra nơi mảng được tạo; một biến `Object[]` có thể trỏ tới `String[]`.
5. Nếu là sao chép nhiều phần tử, xác định **trạng thái mảng đích sau lỗi**: có thể đã bị thay đổi một phần.
6. Sửa chữ ký và ownership để không cần phép ghi vượt component type; không chỉ thêm `catch` rồi tiếp tục trong trạng thái chưa chắc đúng.

### Không dùng message làm giao thức phân loại

Không nên viết:

```java
if (ex.getMessage().contains("String")) {
    // ...
}
```

`getMessage()` có thể null và định dạng thông điệp không ổn định. Khi phải phân loại cho chương trình, dùng **kiểu ngoại lệ**, error code riêng, hoặc dữ liệu đầu vào đã được validate. Message/stack trace phục vụ chẩn đoán.

## 19. Ví dụ một thư viện API bị lỗi do giả định sai về mảng

Giả sử API này được viết để “điền giá trị mặc định”:

```java
static void initializeAll(Object[] values) {
    for (int i = 0; i < values.length; i++) {
        values[i] = new Object();
    }
}
```

Tất cả lời gọi với `new Object[3]` đều hợp lệ. Nhưng nếu caller gọi:

```java
String[] labels = new String[3];
initializeAll(labels);
```

thì Java cho phép truyền `String[]` vào tham số `Object[]` do covariance. Trong vòng lặp, dòng `values[i] = new Object()` ném `ArrayStoreException` ngay khi cố lưu vào `String[]`.

Nếu API chỉ có mục tiêu **xóa phần tử**, nó có thể đặt mọi phần tử reference thành `null` mà không vi phạm component type (nếu hợp đồng cho phép xóa và hậu quả null phù hợp). Nếu cần **giá trị mặc định theo kiểu**, API phải biết kiểu phần tử và cách tạo giá trị đúng; tạo một `Object` chung không đủ.

Ví dụ này minh họa rằng đôi khi **lỗi là ở chữ ký và hợp đồng thiết kế API**, không phải ở caller. Một phương thức nhận `Object[]` nhưng lại tự ý ghi object bất kỳ là một thiết kế cần xem xét lại.

## 20. `ArrayStoreException` và validation cho nhập liệu động

Khi dữ liệu đến từ JSON hoặc cấu hình động, có thể có danh sách giá trị không đồng nhất. Ví dụ một API nội bộ nhận `List<Object>`, trong đó có chuỗi và số.

Nếu chỉ cần tất cả là chuỗi, **không nên** sao chép thẳng vào `String[]` rồi dựa vào `ArrayStoreException` để báo validation. Cách này khiến thông tin lỗi nghèo nàn và có thể tạo kết quả một phần.

Nên kiểm tra từng giá trị, giữ chỉ số và lỗi có cấu trúc:

```java
static String[] requireStrings(
        java.util.List<?> input) {

    String[] result = new String[input.size()];

    for (int i = 0; i < input.size(); i++) {
        Object item = input.get(i);

        if (!(item instanceof String text)) {
            throw new IllegalArgumentException(
                    "item at index " + i + " must be a String");
        }

        result[i] = text;
    }

    return result;
}
```

Đây là phương thức minh họa Java 17+, có chủ đích **không chấp nhận null** trong đầu vào. Nó kiểm tra bằng `instanceof String text` trước khi ghi, rồi trả một `String[]` chỉ khi tất cả dữ liệu đã đi qua vòng lặp thành công.

Lợi ích:

- Câu báo lỗi có vị trí phần tử rõ hơn thông điệp JVM của `ArrayStoreException`.
- Mảng kết quả được tạo mới trong phương thức; nếu validation thất bại, caller **không nhận mảng kết quả chưa hoàn tất**.
- Không cần cast mù từ `List<?>` sang `List<String>`.
- Chính sách với null là chủ động; nếu null được phép, điều kiện kiểm tra có thể được thay đổi có chủ đích.

Trong hệ thống lớn, có thể dùng record `ValidationFailure(index, code, safeMessage)` để trả nhiều lỗi thay vì ném lỗi đầu tiên; điều đó là lựa chọn hợp đồng validation, không phải chức năng tự có của `ArrayStoreException`.

## 21. Các lỗi hiểu sai phổ biến

| Nhầm lẫn | Thực tế | Cách tiếp cận tốt |
| --- | --- | --- |
| “Ép `Object` thành bất cứ lớp nào cũng biến object thành lớp đó” | Cast chỉ kiểm tra kiểu runtime; không biến đổi object | Dùng constructor/parser/chuyển đổi dữ liệu đúng chức năng |
| “Tất cả cast sai đều ném `ClassCastException` lúc chạy” | Một số cast bị compiler từ chối từ đầu | Phân biệt lỗi compile-time với lỗi runtime |
| “Mảng `String[]` gán vào `Object[]` sẽ chứa được mọi Object” | Runtime vẫn là `String[]` | Không ghi giá trị ngoài component type |
| “`ArrayStoreException` xảy ra khi ép `String[]` sang `Integer[]`” | Đó là lỗi cast chính object mảng | Nhận diện thao tác cast vs store |
| “Có `ArrayStoreException` khi lưu null vào `String[]`” | Null hợp lệ với reference array | Kiểm tra hợp đồng null riêng |
| “`int[]` là một `Object[]`” | Primitive array không subtype `Object[]` | Phân biệt `Object` với `Object[]` |
| “Generic `List<String>` có tính covariance như `String[]`” | Generic `List<T>` mặc định invariant | Dùng wildcard phù hợp khi chỉ cần đọc |
| “Cast `List<Integer>` sang `List<String>` luôn ném ngay” | Erasure có thể khiến cast qua; lỗi nổ khi đọc phần tử | Tránh unchecked casts, dùng kiểu đúng |
| “`@SuppressWarnings` sửa dữ liệu sai kiểu” | Chỉ tắt warning | Sửa design và nơi tạo dữ liệu |
| “`System.arraycopy` lỗi thì mảng đích chắc chắn nguyên trạng” | Có thể đã sao chép một phần tử trước khi ném | Kiểm tra trước hoặc dùng phương án tạo bản mới |
| “`NumberFormatException` là lỗi cast” | Parse chuỗi thành số khác cast object | Dùng parsing API và xử lý lỗi riêng |
| “Ép null sang `String` ném `ClassCastException`” | Cast null thành null hợp lệ | Chú ý NPE khi dereference |
| “Bắt `ClassCastException` là đủ để validate toàn bộ input” | Chỉ bắt lỗi sau khi cast sai, thiếu ngữ cảnh | Xác thực dữ liệu ở boundary |
| “`Class.cast` luôn trả giá trị” | Ném `ClassCastException` nếu object không phù hợp | Dùng `isInstance` hoặc xử lý theo hợp đồng |
| “`ArrayStoreException` là checked” | Nó extends `RuntimeException` | Sửa kiểu dữ liệu, không thêm `throws` máy móc |

## 22. Bài tập tự kiểm tra

**Bài A. Kiểu lỗi nào?**

```java
Object value = Integer.valueOf(10);
String text = (String) value;
```

**Đáp án:** `ClassCastException`. Object runtime là `Integer`, không thể cast thành `String`.

**Bài B. Kiểu lỗi nào?**

```java
Object[] values = new String[1];
values[0] = new Object();
```

**Đáp án:** `ArrayStoreException`. Mảng thực `String[]` không nhận object `Object` thông thường.

**Bài C. Tại sao `Object[]` vẫn lỗi?**

Vì biến `Object[]` là **kiểu tĩnh**, còn phép ghi mảng được kiểm tra theo **component type runtime**, có thể là `String`.

**Bài D. Có lỗi không?**

```java
Object value = null;
String text = (String) value;
```

**Không có `ClassCastException`.** `text` nhận `null`. Nếu sau đó gọi `text.length()`, mới có thể gặp `NullPointerException`.

**Bài E. Có lỗi không?**

```java
Object[] values = new String[1];
values[0] = null;
```

**Không có `ArrayStoreException`** vì null được phép lưu trong reference array.

**Bài F. Ép mảng hay ghi mảng?**

```java
Object value = new String[2];
Integer[] numbers = (Integer[]) value;
```

**`ClassCastException`**, vì phép đang thất bại là ép kiểu **toàn bộ object mảng**.

**Bài G. Generic cast lúc nào lỗi?**

Một `List<Integer>` bị cast unchecked sang `List<String>` qua `Object`. Cast có thể qua, nhưng `String s = list.get(0);` có thể ném `ClassCastException`, vì object phần tử thực là `Integer`.

**Bài H. Có thể gán `int[]` vào `Object[]` không?**

**Không.** Primitive array `int[]` là `Object` nhưng không là `Object[]`.

**Bài I. Mảng `Number[]` trỏ `Integer[]` có thể chứa `Long` không?**

**Không.** Ghi `Long` ném `ArrayStoreException` vì mảng runtime là `Integer[]`.

**Bài J. `System.arraycopy` ném lỗi tại phần tử thứ hai. Phần tử đầu đã sao chép có nhất thiết rollback không?**

**Không.** Trường hợp sao chép thành phần từng phần có thể để phần tử đầu đã được ghi. Không coi `arraycopy` là transaction.

**Bài K. `String[]` hay `List<String>` giúp ngăn thêm `Integer` sớm hơn?**

Với API generic sử dụng bình thường, `List<String>.add(Integer)` bị compiler từ chối. `String[]` cũng từ chối gán trực tiếp `Integer` ở compile time, nhưng vì **array covariance**, có đường `Object[]` hợp lệ để phép ghi sai bị phát hiện tại runtime. `List<String>` invariant làm giảm đường rủi ro đó.

**Bài L. Có nên phân loại bằng cách tìm `"cannot be cast"` trong `getMessage()`?**

**Không.** Message không phải hợp đồng ổn định. Dùng loại exception cùng thông tin kiểu/nguồn dữ liệu, và tránh phụ thuộc câu chữ JVM.

## 23. Checklist kiểm tra khi sửa lỗi trong ứng dụng

Khi bạn gặp `ClassCastException`:

1. Tìm biểu thức cast hoặc chỗ generic/retrieval yêu cầu một reference type cụ thể.
2. Xác định runtime class thật và kiểu đích, có kiểm tra null hợp lệ.
3. Xác minh nguồn tạo object và hợp đồng biến chứa nó.
4. Tìm raw types, unchecked cast, reflection hoặc dữ liệu từ plugin/deserialization.
5. Cân nhắc chuyển dữ liệu thực sự thay vì chỉ ép kiểu.
6. Nếu nhiều subtype cùng hành vi, cân nhắc polymorphism.
7. Chỉ dùng `instanceof` để xử lý những loại động mà API thực sự cho phép.
8. Thử lại đường dữ liệu sai kiểu và null; không chỉ thêm `catch` rồi lặng lẽ trả mặc định.

Khi gặp `ArrayStoreException`:

1. Xác định mảng thực được tạo bằng `new ComponentType[...]` ở đâu.
2. Kiểm tra runtime component type, không chỉ kiểu biến `Object[]`/`Number[]`.
3. Kiểm tra runtime type của giá trị được ghi và quy tắc null.
4. Xác minh có covariance qua tham số phương thức hoặc giá trị trả về không.
5. Kiểm tra `System.arraycopy` hay API sao chép có thể đã thay đổi mảng một phần.
6. Sửa chữ ký API, dùng mảng đúng kiểu hoặc generic collection phù hợp.
7. Nếu dữ liệu từ nguồn động, validate trước khi sao chép hoặc ghi.
8. Không mặc định dùng exception để thực hiện nhánh validation thông thường; diễn đạt lỗi ở ranh giới input bằng mã/ngữ cảnh thích hợp.

## Kết luận

**`ClassCastException` là lỗi của một phép cast reference; `ArrayStoreException` là lỗi của một phép ghi vào reference array.** Cả hai đều xuất phát từ việc kiểu runtime thực tế không phù hợp với thao tác, mặc dù kiểu tĩnh đôi khi cho phép code biên dịch.

Java 17 giúp giảm nguy cơ cast bằng **pattern matching `instanceof`**, generics và các API có kiểu rõ ràng. Với mảng, phải đặc biệt chú ý **covariance**: một biến `Object[]` hoàn toàn có thể trỏ tới `String[]`, và JVM vẫn kiểm tra phần tử theo `String` khi ghi. Khi sao chép mảng, hãy tính tới khả năng trạng thái đích thay đổi một phần nếu lỗi xảy ra.

Giải pháp bền vững là **thiết kế hệ kiểu và hợp đồng API đúng**, kiểm tra dữ liệu không đáng tin tại ranh giới, bảo toàn thông tin chẩn đoán và sửa nguyên nhân thay vì chỉ bắt hai ngoại lệ runtime rồi bỏ qua.