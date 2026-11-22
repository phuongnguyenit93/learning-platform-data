# Java Reflection: `Class.cast`, `Class.isInstance` và `Class.asSubclass`

## Mục tiêu

Khi làm việc với dữ liệu kiểu `Object`, một tên lớp được tải động, hoặc một API dùng generics, bạn đôi khi không biết kiểu cụ thể ngay tại thời điểm biên dịch. `java.lang.Class<T>` cung cấp một **type token** đại diện cho một kiểu ở runtime. Ba phương thức quan trọng của nó — **`cast`**, **`isInstance`**, và **`asSubclass`** — giúp kiểm tra hoặc giới hạn kiểu một cách có căn cứ mà không phải rải unchecked casts.

Sau bài này, bạn có thể:

- Phân biệt câu hỏi “đối tượng này có thuộc kiểu mong đợi không?” với “lớp này có là subtype của lớp/interface yêu cầu không?”.
- Sử dụng `Class<T>.isInstance(Object)` để kiểm tra **một instance**, kể cả khi token `Class<T>` được truyền từ bên ngoài.
- Sử dụng `Class<T>.cast(Object)` để **kiểm tra runtime và lấy lại giá trị kiểu `T`**.
- Sử dụng `Class.asSubclass(Class<U>)` để kiểm tra **quan hệ kế thừa của đối tượng `Class`** và thu hẹp từ `Class<?>` thành `Class<? extends U>`.
- Dự đoán chính xác `false`, `null` và `ClassCastException` trong các trường hợp đúng/sai kiểu.
- Hiểu giới hạn của type erasure: `List.class` không kiểm tra được một `List` đang chứa toàn `String` hay không.
- Xây adapter kiểm tra danh sách từ API cũ, hoặc tải một implementation cụ thể bằng reflection có kiểm soát.
- Phân biệt ba API với `instanceof`, phép cast thường, `Class.isAssignableFrom`, `getClass` và generic metadata.

**Yêu cầu:** JDK 17 trở lên. Các ví dụ dùng `javac`, `java`, `javap`, không cần thư viện ngoài. Ba chương trình hoàn chỉnh được kiểm chứng bằng Java 17 và `-Xlint:all`; code nhỏ ghi “minh họa” cần đặt vào class/method thích hợp.

## 1. Bắt đầu từ `Class<T>` — type token tại runtime

Trong Java, các biểu thức:

```java
String.class
Integer.class
Number.class
java.util.List.class
```

trả những đối tượng `Class` biểu diễn các lớp/interface tương ứng. Về compile-time, chẳng hạn `String.class` có kiểu `Class<String>`; `Number.class` có kiểu `Class<Number>`.

Một method generic có thể yêu cầu token tường minh:

```java
static <T> T readAs(Object source, Class<T> expected) {
    return expected.cast(source);
}
```

Lời gọi minh họa:

```java
String name = readAs("Java", String.class);
Integer age = readAs(18, Integer.class);
```

Compiler suy luận `T` từ token, nhờ đó kiểu trả về của `readAs` rõ ràng ở source. Khi chạy, `Class.cast` so đối tượng thật với kiểu mà token chỉ tới. Nó không tự chuyển số nguyên sang chuỗi hoặc chuyển mọi giá trị về kiểu mong đợi.

**Phân biệt:** `Class<T>` là loại token dành cho một lớp/interface/kiểu runtime cụ thể; nó **không** có nghĩa JVM tạo class `List<String>` riêng. Với `List<String>`, token class thông thường là `List.class`, chưa có thông tin `String` của các phần tử.

## 2. Bảng đối chiếu ba phương thức

| API | Receiver | Đối số | Trả về | Khi không phù hợp |
| --- | --- | --- | --- | --- |
| `Class<T>.isInstance(Object obj)` | Token kiểu cần kiểm tra | **Instance** hoặc `null` | `boolean` | `false` |
| `Class<T>.cast(Object obj)` | Token kiểu đích | **Instance** hoặc `null` | `T` | `ClassCastException` nếu non-null và không hợp kiểu |
| `Class<T>.asSubclass(Class<U> superclass)` | Một đối tượng **`Class`** có sẵn | Class/interface cần làm supertype | `Class<? extends U>` | `ClassCastException` nếu receiver không là subtype của đối số |

Ba ví dụ cho cùng tên lớp `Dog`:

```java
Object animal = new Dog();
boolean yes = Animal.class.isInstance(animal);
Dog dog = Dog.class.cast(animal);
Class<? extends Animal> type = Dog.class.asSubclass(Animal.class);
```

Đây là đoạn mã minh họa giả định `Dog extends Animal` và đang ở trong class/method phù hợp. Hai câu đầu thao tác với một **đối tượng `Dog`**, câu thứ ba thao tác với **đối tượng `Class` đại diện cho `Dog`**.

Mẹo nhận diện:

- `isInstance`: **hỏi** về đối tượng, trả đúng/sai.
- `cast`: **lấy đối tượng với kiểu mong muốn**, lỗi nếu không tương thích.
- `asSubclass`: **hỏi về quan hệ giữa hai class tokens**, lấy token được giới hạn kiểu hơn.

## 3. `Class.isInstance` — kiểm tra một đối tượng theo token

Cách dùng:

```java
boolean accepted = String.class.isInstance(value);
```

Trong ví dụ này `value` là một `Object` đã có trong scope. `isInstance` trả `true` khi object không `null` và thuộc lớp, subclass hoặc interface tương thích với token.

Ví dụ:

```java
Object x = "hello";
System.out.println(String.class.isInstance(x));       // true
System.out.println(CharSequence.class.isInstance(x)); // true
System.out.println(Integer.class.isInstance(x));      // false
```

**`null` đặc biệt quan trọng:** `String.class.isInstance(null)` là `false`. Điều này không có nghĩa `null` “là String sai kiểu”; nó có nghĩa `isInstance` không xem `null` là một instance của bất kỳ class/interface nào.

Nếu token là **interface**, `isInstance` kiểm tra object có implement interface ấy không. Nếu token là **array class** như `String[].class`, nó kiểm tra object có thuộc array class tương ứng theo quan hệ type compatibility của Java không.

Với **primitive class literal** như `int.class`, `int.class.isInstance(Integer.valueOf(7))` trả `false`; một `Integer` wrapper không phải một instance của primitive `int`. Reflection API này không thực hiện boxing/unboxing để “biến” đối tượng thành instance của primitive class.

### So với `instanceof`

```java
if (value instanceof String) { ... }
```

và:

```java
if (String.class.isInstance(value)) { ... }
```

cùng trả lời câu hỏi loại object trong trường hợp `String.class` cố định, nhưng `isInstance` có điểm mạnh: **Class token có thể là tham số runtime**.

```java
static boolean matches(Object item, Class<?> type) {
    return type.isInstance(item);
}
```

Đặt đoạn này vào một class; caller có thể truyền `String.class`, `Number.class` hoặc interface token tùy tình huống. Cách viết `instanceof` thường cần tên kiểu có thể biểu diễn trực tiếp ở source; Java 17 không thể viết một cách tổng quát `value instanceof T` với một type variable `T` không reifiable.

**Không đồng nhất `instanceof` kiểm tra kiểu với cơ chế pattern matching** như `value instanceof String text`. Pattern matching còn ràng buộc biến typed `text` theo kiểu source; `Class.isInstance` chỉ trả boolean, muốn dùng giá trị dưới kiểu `T` thì cần `Class.cast` hoặc logic có kiểm tra tương ứng.

## 4. `Class.cast` — kiểm tra và thu được giá trị kiểu `T`

Chữ ký khái niệm:

```java
public T cast(Object obj);
```

Với token `Class<T>`, method có thể trả một kết quả được compiler xem là `T`. Ở runtime, nếu `obj` khác `null` nhưng không thuộc kiểu tương thích, method ném `ClassCastException`.

```java
Object candidate = "Java";
String text = String.class.cast(candidate);
System.out.println(text.toUpperCase()); // JAVA
```

Lời gọi sai:

```java
Object candidate = Integer.valueOf(42);
// String text = String.class.cast(candidate);
// Biên dịch được, nhưng ném ClassCastException khi chạy.
```

Nên phân biệt **biên dịch được** với **thành công ở runtime**. `Class.cast` không sửa giá trị `Integer` thành `String`; nó xác minh rằng phép dùng dưới kiểu `T` có hợp lệ hay không.

### `cast(null)` trả gì?

```java
String missing = String.class.cast(null);
System.out.println(missing == null); // true
```

`Class.cast(null)` **trả `null`**, không tự ném `ClassCastException`. Khác với `isInstance(null)` trả `false`, phép cast của một tham chiếu `null` về kiểu tham chiếu vẫn được phép.

Nếu API của bạn **không chấp nhận `null`**, hãy viết chính sách riêng, ví dụ kiểm tra `Objects.requireNonNull` hoặc `isInstance` và ném một exception có ngữ cảnh. Không suy luận rằng chỉ dùng `Class.cast` đã loại `null` khỏi đầu vào.

### `Class.cast` so với phép cast thông thường

```java
String a = (String) candidate;
String b = String.class.cast(candidate);
```

Khi token cố định, hai cách đều có thể gây `ClassCastException` nếu object sai kiểu. Nhưng `Class.cast` phù hợp khi kiểu đích đến từ **biến `Class<T>` ở runtime**, trong khi một cast trực tiếp như `(T) candidate` trong generic method có thể là **unchecked cast** hoặc chỉ cast theo upper bound sau type erasure.

Ví dụ:

```java
static <T> T checked(Object input, Class<T> expected) {
    return expected.cast(input);
}
```

Cách này giúp compiler biết kết quả là `T` và thực hiện kiểm tra bằng token thật được truyền vào.

## 5. `Class.asSubclass` — thu hẹp **class token**, không phải instance

Đây là phương thức dễ bị đọc nhầm nhất.

Chữ ký:

```java
public <U> Class<? extends U> asSubclass(Class<U> clazz);
```

Giả sử bạn đang có:

```java
Class<?> discovered = Dog.class;
```

Bạn chưa biết class được phát hiện có liên quan gì tới `Animal`. Có thể kiểm tra:

```java
Class<? extends Animal> type =
        discovered.asSubclass(Animal.class);
```

Nếu `discovered` biểu diễn `Dog` và `Dog extends Animal`, lời gọi thành công. Giá trị trả về vẫn đại diện cho chính class `Dog`, nhưng **kiểu compile-time được thu hẹp** thành `Class<? extends Animal>`.

Nếu:

```java
Class<?> discovered = String.class;
// Class<? extends Animal> type = discovered.asSubclass(Animal.class);
```

thì lời gọi ném `ClassCastException`, vì `String` không là subtype của `Animal`.

### Chính xác `asSubclass` kiểm tra gì?

Nó kiểm tra **class do receiver biểu diễn có thể được xem là subclass/subtype của kiểu do đối số biểu diễn không**. Kiểu đích có thể là class hoặc interface. Ví dụ một class `Dog implements Pet` thì:

```java
Class<? extends Pet> token = Dog.class.asSubclass(Pet.class);
```

hợp lệ, kể cả khi `Pet` là interface. Về mặt kiểm tra quan hệ subtype, bản thân class đích bằng receiver cũng hợp lệ: `Animal.class.asSubclass(Animal.class)` thành công.

**Đừng suy diễn từ tên `asSubclass` rằng method tạo class con mới.** Nó không xây class, không sửa inheritance hierarchy, không tạo object và không tự gọi constructor. Nó trả về một đối tượng `Class` biểu diễn class đã có, dưới một kiểu generic bảo đảm giới hạn subtype.

### `Class<?>` và `Class<? extends Animal>`

- `Class<?>`: một class token chưa ràng buộc với loại cha cụ thể.
- `Class<? extends Animal>`: token đại diện cho class có thể dùng như `Animal` hoặc subclass của nó.

Sau bước `asSubclass`, một API có thể làm việc với những class tokens đã qua kiểm tra thay vì dùng unchecked cast:

```java
Class<? extends Animal> safeType =
        unknownClass.asSubclass(Animal.class);
```

Phần tiếp theo minh họa mẫu này với interface plugin/service.

## 6. Chương trình A — Đối chiếu cả ba API trên cùng mô hình kiểu

Tạo tệp **`ClassReflectionDemo.java`**:

```java
import java.util.List;

public class ClassReflectionDemo {
    interface Pet {
        String sound();
    }

    static class Animal {}

    static final class Dog extends Animal implements Pet {
        @Override
        public String sound() {
            return "woof";
        }
    }

    static final class Cat extends Animal {}

    public static void main(String[] args) {
        Object candidate = new Dog();

        System.out.println("animal instance: "
                + Animal.class.isInstance(candidate));
        System.out.println("dog instance: "
                + Dog.class.isInstance(candidate));
        System.out.println("cat instance: "
                + Cat.class.isInstance(candidate));
        System.out.println("null instance: "
                + Dog.class.isInstance(null));
        System.out.println("interface instance: "
                + Pet.class.isInstance(candidate));
        System.out.println("primitive instance: "
                + int.class.isInstance(Integer.valueOf(7)));
        System.out.println("array instance: "
                + String[].class.isInstance(new String[2]));

        Dog dog = Dog.class.cast(candidate);
        System.out.println("cast result: " + dog.sound());
        System.out.println("cast null: "
                + (Dog.class.cast(null) == null));

        try {
            Cat.class.cast(candidate);
        } catch (ClassCastException ex) {
            System.out.println("bad cast: "
                    + ex.getClass().getSimpleName());
        }

        Class<?> runtime = candidate.getClass();
        Class<? extends Animal> subtype =
                runtime.asSubclass(Animal.class);
        System.out.println("subclass: "
                + subtype.getSimpleName());

        Class<? extends Pet> petSubtype =
                runtime.asSubclass(Pet.class);
        System.out.println("interface subclass: "
                + petSubtype.getSimpleName());

        try {
            String.class.asSubclass(Animal.class);
        } catch (ClassCastException ex) {
            System.out.println("bad subclass: "
                    + ex.getClass().getSimpleName());
        }

        List<Integer> numbers = List.of(1, 2);
        Object collection = numbers;
        System.out.println("list instance: "
                + List.class.isInstance(collection));
        System.out.println("list cast: "
                + List.class.cast(collection).get(0));
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all ClassReflectionDemo.java
java ClassReflectionDemo
```

**Stdout đã kiểm chứng:**

```text
animal instance: true
dog instance: true
cat instance: false
null instance: false
interface instance: true
primitive instance: false
array instance: true
cast result: woof
cast null: true
bad cast: ClassCastException
subclass: Dog
interface subclass: Dog
bad subclass: ClassCastException
list instance: true
list cast: 1
```

Chương trình biên dịch thành công, không phát cảnh báo với `-Xlint:all`.

### Phân tích các kiểm tra instance

`candidate` trỏ tới đối tượng `Dog`.

- `Animal.class.isInstance(candidate)` trả `true` vì `Dog extends Animal`.
- `Dog.class.isInstance(candidate)` trả `true` vì là instance `Dog`.
- `Cat.class.isInstance(candidate)` trả `false`: cả `Dog` và `Cat` cùng là subclass của `Animal`, nhưng không phải subtype của nhau.
- `Pet.class.isInstance(candidate)` trả `true` vì `Dog implements Pet`.
- `Dog.class.isInstance(null)` trả `false`.
- `int.class.isInstance(Integer.valueOf(7))` trả `false`, không chuyển wrapper thành primitive instance.
- `String[].class.isInstance(new String[2])` trả `true` vì đối tượng thực là mảng `String[]`.

Các câu lệnh `isInstance` **không thay đổi dữ liệu**, cũng không làm compiler tự coi biến `candidate: Object` là `Dog`. Chúng chỉ trả thông tin đúng/sai.

### Phân tích các kiểm tra cast

`Dog.class.cast(candidate)` trả chính đối tượng `Dog` để dùng dưới kiểu `Dog`; sau đó `sound()` cho `woof`.

`Dog.class.cast(null)` trả `null`.

`Cat.class.cast(candidate)` thất bại bằng `ClassCastException` dù cả `Cat` và `Dog` đều là `Animal`. Cast không chuyển đổi runtime class của object.

### Phân tích `asSubclass`

`candidate.getClass()` trả runtime token cho `Dog`. Do `Dog` là subtype của `Animal` **và** implement `Pet`, hai lời gọi `asSubclass` đều thành công.

`String.class.asSubclass(Animal.class)` thất bại vì quan hệ subtype không đúng. Sự thất bại ở đây nói về **quan hệ giữa hai đối tượng `Class`**, khác với lỗi `Cat.class.cast(candidate)` nói về **instance `candidate`**.

## 7. `Class.isAssignableFrom` liên quan thế nào đến `asSubclass`?

Một phương thức phản chiếu khác của `Class` là:

```java
boolean parentAcceptsChild =
        Animal.class.isAssignableFrom(Dog.class);
```

Kết quả là `true`: biến kiểu `Animal` có thể giữ tham chiếu tới một `Dog`.

Quy tắc hướng rất quan trọng:

```java
Animal.class.isAssignableFrom(Dog.class) // true
Dog.class.isAssignableFrom(Animal.class) // false
```

Các đoạn này là biểu thức minh họa đặt trong method có khai báo `Animal`/`Dog`.

Đối chiếu với `asSubclass`:

```java
Class<?> found = Dog.class;
Class<? extends Animal> typed =
        found.asSubclass(Animal.class);
```

Ta có thể hình dung bước kiểm tra là **`Animal.class.isAssignableFrom(found)`**. Nếu thành công, `asSubclass` còn **cung cấp kết quả được giới hạn kiểu** `Class<? extends Animal>`; còn `isAssignableFrom` chỉ trả boolean.

| Method | Receiver | Tham số | Trả về |
| --- | --- | --- | --- |
| `Animal.class.isAssignableFrom(Dog.class)` | Class cha dự kiến | Class con có thể gán | `true` |
| `Dog.class.asSubclass(Animal.class)` | Class con thực tế | Class cha/interface bắt buộc | Token `Class<? extends Animal>` |
| `Animal.class.isInstance(new Dog())` | Class cha dự kiến | **Đối tượng** | `true` |

Đảo sai hướng là lỗi reflection phổ biến. Hãy tự hỏi: “Biến kiểu nào cần nhận một object của class nào?” Nếu biến `Animal` giữ được `Dog`, thì `Animal.class.isAssignableFrom(Dog.class)` đúng.

## 8. Generic erasure: những phép kiểm tra này **không** xác thực type arguments lồng nhau

Ví dụ:

```java
List<Integer> integers = List.of(1, 2);
Object object = integers;

System.out.println(List.class.isInstance(object)); // true
List rawView = List.class.cast(object);
```

`List.class` chỉ nói về **interface `List` ở runtime**. Nó không lưu riêng đối số `Integer` hay `String` của instance.

Vì vậy, một lỗi thiết kế là nghĩ rằng:

```java
// KHÔNG HỢP LỆ trong Java:
// Class<List<String>> token = List<String>.class;
```

Không tồn tại class literal `List<String>.class` tương ứng với một runtime class riêng. Một đối tượng `List<Integer>` và một đối tượng `List<String>` đều có thể thỏa `List.class.isInstance(...)`.

Đặc biệt **không** thực hiện unchecked cast từ `List.class.cast(rawObject)` sang `List<String>` rồi coi đó là kiểm chứng. `Class.cast` tại đây chỉ kiểm tra object có implement `List`; nó không duyệt từng phần tử.

Nếu cần kết quả `List<String>` an toàn từ một nguồn chưa xác định, hãy:

1. Xác minh nguồn là một `List` ở runtime.
2. Duyệt các phần tử.
3. Kiểm tra mỗi phần tử thuộc `String.class` hoặc một chính sách chuyển đổi rõ ràng.
4. Tạo danh sách typed mới, tránh để tham chiếu raw mutable tiếp tục can thiệp vào dữ liệu.

Mẫu đầy đủ ở phần tiếp theo sử dụng `Class<T>` token để tổng quát hóa bước kiểm tra.

## 9. Chương trình B — Xác minh dữ liệu từ API legacy bằng `Class<T>`

Tạo tệp **`TypedBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class TypedBoundaryDemo {
    static <T> T requireNonNullType(Object value, Class<T> expected) {
        Objects.requireNonNull(expected, "expected");
        if (!expected.isInstance(value)) {
            throw new IllegalArgumentException(
                    "Expected " + expected.getSimpleName());
        }
        return expected.cast(value);
    }

    static <T> List<T> checkedCopy(List<?> source,
                                   Class<T> expected) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(expected, "expected");

        List<T> result = new ArrayList<>();
        for (int i = 0; i < source.size(); i++) {
            Object value = source.get(i);
            if (!expected.isInstance(value)) {
                throw new IllegalArgumentException(
                        "Invalid element at " + i);
            }
            result.add(expected.cast(value));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        Object input = "Java";
        System.out.println("scalar: "
                + requireNonNullType(input, String.class));

        List<?> oldData = List.of("Lan", "Minh");
        System.out.println("checked: "
                + checkedCopy(oldData, String.class));

        try {
            checkedCopy(List.of("Lan", 42), String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        System.out.println("class cast null: "
                + (String.class.cast(null) == null));
        try {
            requireNonNullType(null, String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("null rejected: "
                    + ex.getMessage());
        }

        List<Integer> integers = List.of(10);
        System.out.println("list token permits integers: "
                + List.class.isInstance(integers));
        System.out.println("list class cast first: "
                + List.class.cast(integers).get(0));
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all TypedBoundaryDemo.java
java TypedBoundaryDemo
```

**Stdout đã kiểm chứng:**

```text
scalar: Java
checked: [Lan, Minh]
rejected: Invalid element at 1
class cast null: true
null rejected: Expected String
list token permits integers: true
list class cast first: 10
```

Không có cảnh báo `rawtypes` hoặc `unchecked` trong chương trình này với `-Xlint:all`.

### `requireNonNullType` dùng phối hợp hai method để làm gì?

```java
if (!expected.isInstance(value)) {
    throw new IllegalArgumentException(...);
}
return expected.cast(value);
```

`isInstance` giúp áp dụng **chính sách dữ liệu nghiệp vụ**, ở đây là không chấp nhận `null` hoặc giá trị sai kiểu, và ném `IllegalArgumentException` có thông điệp do API kiểm soát.

Sau đó `cast` trả `T` dưới một kiểm tra runtime đúng với token. Không cần viết unchecked cast `(T)value`.

Nếu API muốn cho phép `null`, có thể dùng `expected.cast(value)` trực tiếp với token không `null`, và giải thích rõ trong contract rằng kết quả có thể `null`. Sự lựa chọn về `null` là **chính sách API**, không phải một giới hạn ngầm của `Class.cast`.

### `checkedCopy` giải quyết giới hạn của `List.class`

`checkedCopy(List<?> source, Class<T> expected)` nhận **danh sách chưa biết kiểu phần tử**. Nó lấy từng phần tử như `Object`, kiểm tra `expected.isInstance`, rồi thêm `expected.cast(value)` vào `ArrayList<T>`.

Với `List.of("Lan","Minh")`, tất cả phần tử là `String`, trả `List<String>` hợp lệ.

Với `List.of("Lan",42)`, phần tử ở index 1 là `Integer`, nên adapter **từ chối ngay tại ranh giới**, thay vì để `ClassCastException` xảy ra muộn khi code nghiệp vụ đọc giá trị.

`List.copyOf(result)` trả một list không sửa được bằng các thao tác list thông thường và không giữ cấu trúc mutable ban đầu. Tuy vậy, với những phần tử `T` có state mutable, copy list **không** tự biến chúng thành immutable sâu.

### `List.class` không biết bên trong chứa gì

Hai dòng cuối cố ý minh họa:

```text
list token permits integers: true
list class cast first: 10
```

`List<Integer>` vẫn là một `List` runtime. `List.class.cast(integers)` hợp lệ, nhưng chỉ trả một góc nhìn `List` về object ấy, không xác thực nó phù hợp `List<String>`. Vì vậy, adapter cần kiểm tra **từng phần tử** khi phải cung cấp typed collection.

## 10. `Class.asSubclass` trong nạp implementation và cơ chế plugin

Một trường hợp điển hình của `asSubclass` là **nạp class theo tên**, rồi kiểm tra xem nó có implement interface được yêu cầu hay không.

Một chuỗi xử lý điển hình:

```text
Tên class do cấu hình cung cấp
                |
                v
        Class.forName(name)
                |
                v
             Class<?>
                |
                v
   asSubclass(Service.class)
                |
          kiểm tra subtype
          /             \
      hợp lệ           sai kiểu
        |                  |
        v                  v
 Class<? extends      ClassCastException
     Service>
        |
        v
getDeclaredConstructor()
    .newInstance()
        |
        v
   Service instance
```

Chú ý có **hai vấn đề độc lập**:

1. Class được tìm thấy có implement `Service` không? — `asSubclass` giải quyết.
2. Class có thể tạo instance hợp lệ không? — còn phụ thuộc constructor, access, abstract/interface status, ngoại lệ từ constructor, quyền truy cập và những ràng buộc riêng của runtime.

`asSubclass` **không kiểm tra** constructor tồn tại, có public hay không, và cũng không tạo object. Nó chỉ kiểm tra quan hệ subtype để kết quả có một kiểu `Class<? extends Service>` thích hợp.

## 11. Chương trình C — Tải một service class an toàn về kiểu

Tạo tệp **`PluginServiceDemo.java`**:

```java
public class PluginServiceDemo {
    public interface Service {
        String id();
    }

    public static class FastService implements Service {
        public FastService() {}

        @Override
        public String id() {
            return "fast";
        }
    }

    public static class NotAService {
        public NotAService() {}
    }

    static Service load(String className)
            throws ReflectiveOperationException {
        Class<?> unknown = Class.forName(className);
        Class<? extends Service> implementation =
                unknown.asSubclass(Service.class);

        return implementation
                .getDeclaredConstructor()
                .newInstance();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Service service = load(FastService.class.getName());
        System.out.println("loaded: " + service.id());

        try {
            load(NotAService.class.getName());
        } catch (ClassCastException ex) {
            System.out.println("wrong plugin type: "
                    + ex.getClass().getSimpleName());
        }

        try {
            load("not.existing.Plugin");
        } catch (ClassNotFoundException ex) {
            System.out.println("missing plugin: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all PluginServiceDemo.java
java PluginServiceDemo
```

**Stdout đã kiểm chứng:**

```text
loaded: fast
wrong plugin type: ClassCastException
missing plugin: ClassNotFoundException
```

Chương trình chạy thành công và không có cảnh báo compiler với `-Xlint:all`.

### Phân tích từng tình huống

**Tải `FastService`:** `Class.forName` trả `Class<?>`, tức biết class thực nhưng chưa có ràng buộc generic về interface. `asSubclass(Service.class)` xác minh nó implement `Service`. `getDeclaredConstructor().newInstance()` tạo instance thông qua public no-arg constructor trong mẫu.

**Tải `NotAService`:** tên class có thật, `Class.forName` thành công. Nhưng class không implement `Service`, nên `asSubclass` ném `ClassCastException`. Vấn đề là **sai quan hệ kiểu**, không phải thiếu class.

**Tải tên không tồn tại:** `Class.forName` ném `ClassNotFoundException` trước khi gọi `asSubclass`. Đây là lỗi nạp class, khác lỗi kiểm tra subtype.

### Những lưu ý khi áp dụng thật

- Nếu class là abstract/interface, thiếu constructor phù hợp hoặc constructor ném lỗi, bước tạo instance vẫn có thể thất bại.
- `newInstance()` trên `Constructor` có thể ném những ngoại lệ reflection như `InstantiationException`, `IllegalAccessException`, `InvocationTargetException` hoặc `NoSuchMethodException`; cần xử lý theo hợp đồng thực tế.
- Java module access có thể hạn chế phản chiếu những thành viên không được mở quyền.
- Không nạp/thực thi **tên class tùy ý từ nguồn không đáng tin** chỉ vì `asSubclass` thành công. Việc implement `Service` không đồng nghĩa mã đó an toàn để chạy. Trong sản phẩm nên dùng registry/allowlist và quy trình tin cậy riêng.

Mẫu minh họa chỉ dùng hai nested classes trong chương trình của chính bạn; không thực hiện cơ chế cài đặt plugin bên ngoài.

## 12. Tổng hợp ba dạng “kiểm tra kiểu” qua một luồng dữ liệu

Một hệ thống có thể có cả class name, object và collection chưa rõ kiểu:

```text
CONFIG: "com.example.FastService"
        |
        +--> Class.forName(...) -> Class<?>
                |
                +--> asSubclass(Service.class)
                |        |
                |        +--> Class<? extends Service>
                |
                +--> Constructor.newInstance()
                         |
                         +--> Object thực

DATA: Object input
        |
        +--> Service.class.isInstance(input) -> boolean
        |
        +--> Service.class.cast(input)       -> Service

COLLECTION: List<?> data
        |
        +--> duyệt từng Object
                |
                +--> type.isInstance(element)
                +--> type.cast(element)
                |
                +--> List<T> mới đã được xác minh
```

Tùy điểm dữ liệu, chọn đúng công cụ:

- Nếu **đã có object**, cần hỏi nó thuộc kiểu đích không: `isInstance`.
- Nếu **đã có object**, muốn đưa giá trị sang kiểu generic `T`: `cast`.
- Nếu **chỉ có một Class<?>**, muốn bảo đảm class ấy là subtype của interface/class yêu cầu: `asSubclass`.
- Nếu **có collection từ nguồn bất định**, ba API không thể một mình khôi phục `List<String>` qua erasure; hãy kiểm tra từng phần tử bằng class token.

## 13. Sự khác nhau giữa lỗi `ClassCastException` và kết quả `false`

Cùng một object `Dog` không phải `Cat`:

```java
Object obj = new Dog();
boolean check = Cat.class.isInstance(obj); // false
// Cat cat = Cat.class.cast(obj);           // ClassCastException
```

`isInstance` thích hợp với **nhánh điều kiện**, kiểm tra đầu vào và validation mềm. `cast` thích hợp khi kiểu đích là **điều kiện bắt buộc** và sai kiểu phải là lỗi của luồng thực thi.

Tương tự với class token:

```java
Class<?> found = String.class;
// Class<? extends Animal> t = found.asSubclass(Animal.class);
// ClassCastException vì String không extends Animal.
```

Nếu chỉ cần hỏi mà không muốn exception, bạn có thể dùng:

```java
boolean ok = Animal.class.isAssignableFrom(found); // false
```

Vậy nên quyết định giữa boolean hay exception là **quyết định về API và luồng lỗi**, không phải method nào “mạnh hơn” theo nghĩa tự sửa dữ liệu.

### Các tình huống `null` cần quy định

- `Animal.class.isInstance(null)` → `false`.
- `Animal.class.cast(null)` → `null`.
- Gọi một instance method trên biến `Class<?> token = null` (ví dụ `token.cast(obj)`) → `NullPointerException` do receiver null.
- Đối số `Class<U>` của `asSubclass` phải là token hợp lệ; trong API nên bắt buộc non-null thay vì coi null như một supertype.
- `Class.forName(null)` cũng không phải một yêu cầu tìm class hợp lệ; cần validation cấu hình trước khi nạp.

Nếu contract đòi **giá trị có mặt và đúng kiểu**, hãy kết hợp `Objects.requireNonNull` và `Class.cast`, hoặc áp dụng `isInstance` rồi báo lỗi có ngữ cảnh như `TypedBoundaryDemo`.

## 14. Các kiểu đặc biệt: interface, array, primitive

Không chỉ class thường mới có thể dùng làm token.

### Interface token

```java
CharSequence.class.isInstance(new StringBuilder("A"))
```

trả `true` vì `StringBuilder implements CharSequence`.

Với `asSubclass`, class thực hiện interface cũng thỏa:

```java
StringBuilder.class.asSubclass(CharSequence.class)
```

kết quả là `Class<? extends CharSequence>` biểu diễn `StringBuilder`.

### Array token

```java
String[].class.isInstance(new String[]{"A", "B"})
```

trả `true`; các array class có runtime identity và component type. Nhưng đừng dùng `List.class` như một token thay thế cho kiểu tham số hóa lồng nhau `List<String>`.

### Primitive token

```java
int.class.isInstance(Integer.valueOf(7))
```

trả `false`: `Integer` không phải runtime instance của primitive `int`. Khi muốn kiểm tra một object chứa giá trị nguyên được boxing, hãy dùng `Integer.class` thay vì `int.class`. Boxing/unboxing của Java không biến `Class.isInstance` thành một phép chuyển đổi tùy ý.

## 15. `Class.cast` không phải phép chuyển đổi dữ liệu

Một hiểu lầm quen thuộc:

```java
Object number = Integer.valueOf(17);
// String text = String.class.cast(number); // Lỗi runtime.
```

`Class.cast` **kiểm tra tương thích kiểu**, không chuyển `17` thành `"17"`. Nếu thật sự muốn chuyển số sang văn bản, dùng API conversion đúng nghĩa:

```java
String text = String.valueOf(number); // "17"
```

Tương tự, `Class.cast` không phân tích một chuỗi `"17"` thành `Integer`; đó là việc của `Integer.parseInt` hoặc parser phù hợp.

Phân biệt hai câu hỏi:

- “Đối tượng này **đã là** kiểu `T` chưa?” → `Class.isInstance`/`Class.cast`.
- “Tôi muốn **biến đổi** giá trị từ miền dữ liệu A sang B” → conversion/parser/mapper.

Đánh đồng sẽ khiến API reflection phát `ClassCastException` không mong muốn và khó debug.

## 16. Phản chiếu kiểu và erasure trong bytecode

Xét method trong chương trình `TypedBoundaryDemo`:

```java
static <T> T requireNonNullType(Object value, Class<T> expected) {
    Objects.requireNonNull(expected, "expected");
    if (!expected.isInstance(value)) {
        throw new IllegalArgumentException(
                "Expected " + expected.getSimpleName());
    }
    return expected.cast(value);
}
```

Chạy sau khi biên dịch:

```bash
javap -p -s TypedBoundaryDemo
```

Một phần output đã được xác minh:

```text
static <T> T requireNonNullType(java.lang.Object, java.lang.Class<T>);
  descriptor: (Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;

static <T> java.util.List<T> checkedCopy(
    java.util.List<?>, java.lang.Class<T>);
  descriptor: (Ljava/util/List;Ljava/lang/Class;)Ljava/util/List;
```

Generic signature metadata mà `javap` hiển thị có `T`, `List<T>` và `Class<T>`, nhưng **JVM descriptors** dùng `Object`, `List`, `Class` sau erasure.

Nhờ token `Class<T>` được truyền tường minh, thân method **vẫn kiểm tra được runtime class** của object, kể cả khi generic method `<T>` bị xóa ở descriptor. Đây là cách **đưa thông tin loại dữ liệu runtime vào API một cách chủ động**, khác với việc trông chờ `T` tự được “phục hồi” từ erasure.

Khi code typed gán kết quả `requireNonNullType(..., String.class)` vào biến `String`, compiler còn có thể sinh cast ở điểm gọi để thực hiện hợp đồng source. Sự tồn tại của token và những cast compiler chèn hỗ trợ type safety; chúng không tạo specialized class riêng cho `T=String`.

## 17. Không dùng `getClass()` để đoán đối số generic tùy ý

Ví dụ:

```java
List<String> names = new java.util.ArrayList<>();
List<Integer> counts = new java.util.ArrayList<>();
boolean same = names.getClass() == counts.getClass(); // true
```

Hai biến có đối số generic khác nhau nhưng cùng runtime class `ArrayList`. Gọi `getClass()` lên một object collection không đủ để biết `String` hay `Integer` là đối số kiểu được khai báo ở source.

Tương tự, `Class<List>` dựa trên `List.class` chỉ kiểm tra object có là `List`, **không kiểm tra `List<String>`**. Nếu code cần kiểm tra một giá trị complex như `Map<String,Integer>`, phải dùng schema/metadata phù hợp và kiểm tra key/value cụ thể; một `Class<Map>` token không đủ.

Reflection có thể đọc generic metadata ở **khai báo field, method, superclass** nhờ `Type`/`ParameterizedType`, nhưng đó là thông tin của **vị trí khai báo**, không phải phép giải mã tùy ý type arguments của mọi object runtime.

Vì vậy, ngay cả khi dùng cả `Class.cast`, `isInstance` và `asSubclass`, hãy giữ rõ ranh giới: chúng làm việc với class/interface runtime, không phải bộ kiểm tra tự động cho mọi generic type argument sau erasure.

## 18. Nên chọn API nào trong một tình huống thực tế?

| Nhu cầu | API ưu tiên | Giải thích |
| --- | --- | --- |
| Hỏi object có là subtype/implementation không | `Class.isInstance` | Trả boolean, dùng được với token runtime |
| Bắt buộc object phải thuộc kiểu đích `T` | `Class.cast` | Trả typed value hoặc ném `ClassCastException` |
| Kiểm tra hai class tokens có quan hệ subtype không | `Class.isAssignableFrom` | Trả boolean, cần chú ý hướng receiver |
| Muốn biến `Class<?>` thành `Class<? extends U>` đã kiểm tra | `Class.asSubclass` | Runtime subtype check và thu hẹp generic token |
| Tìm class từ tên | `Class.forName` | Nạp/tra class; chưa bảo đảm implement interface |
| Tạo instance bằng reflection | `getDeclaredConstructor().newInstance()` | Cần class hợp lệ, constructor và quyền truy cập |
| Cần xác thực `List<String>` từ dữ liệu động | Duyệt phần tử với `String.class.isInstance/cast` | Token `List.class` không đủ do erasure |
| Cần chuyển `Integer` thành `String` | Conversion API như `String.valueOf` | `Class.cast` không chuyển dữ liệu |
| Kiểm tra đúng kiểu tại compile time | Generic type `List<T>`, `Function<T,R>` | Hạn chế unchecked casts trước khi chạy |

Từng công cụ giải quyết một tầng khác nhau. Một thiết kế rõ ràng thường phối hợp chúng ở ranh giới hệ thống thay vì cố dùng một method để kiểm tra mọi cấu trúc dữ liệu.

## 19. Những lỗi phổ biến cần tránh

**Lỗi 1 — Nghĩ `asSubclass` ép object thành subclass.** Nó nhận và trả **đối tượng `Class`**, không nhận một `Object` nghiệp vụ như `Dog`. Nếu đã có object, dùng `isInstance` hoặc `cast`.

**Lỗi 2 — Nghĩ `isInstance` trả một object typed.** Nó chỉ trả `boolean`. Nếu cần `T`, dùng `cast` sau khi kiểm tra hoặc để `cast` tự báo lỗi khi sai kiểu.

**Lỗi 3 — Nghĩ `cast(null)` tự từ chối null.** `Class.cast(null)` trả `null`. Nếu null không hợp đồng, phải kiểm tra riêng.

**Lỗi 4 — Đảo hướng `isAssignableFrom`.** `Animal.class.isAssignableFrom(Dog.class)` là đúng, không phải ngược lại. Trong `asSubclass`, receiver thường là class phát hiện, đối số là kiểu cha bắt buộc.

**Lỗi 5 — Nghĩ `List.class.cast(list)` đã chứng minh list có phần tử `String`.** Runtime chỉ kiểm tra đây là một `List`. Việc xác thực generic elements cần kiểm tra từng phần tử/schema.

**Lỗi 6 — Viết unchecked cast `(Class<? extends Service>) unknown` mà chưa xác minh.** Có thể tạo cảm giác type safety không đúng. `unknown.asSubclass(Service.class)` diễn đạt một runtime subtype check thực tế.

**Lỗi 7 — Coi `Class.cast` là parser hoặc converter.** Cast không biến `Integer` thành `String`, không sửa giá trị không tương thích.

**Lỗi 8 — Giả định class implement interface luôn khởi tạo được.** `asSubclass` không kiểm tra constructor, access, abstract status hoặc logic constructor; bước instantiate cần handling riêng.

**Lỗi 9 — Nạp class tùy ý không kiểm soát từ cấu hình không đáng tin.** Kiểm tra subtype không làm mã bên trong class an toàn; cần allowlist hoặc cơ chế tin cậy.

**Lỗi 10 — Lầm tưởng `getClass()` mang type argument `String` của `List<String>`.** Generic erasure khiến `getClass()` không thể tự suy ra đối số kiểu tùy ý từ object collection.

**Lỗi 11 — Nghĩ `isInstance` cho primitive như wrapper do boxing.** `int.class.isInstance(Integer.valueOf(1))` vẫn `false`; dùng wrapper token khi kiểm tra object.

**Lỗi 12 — Bỏ qua chính sách null và lỗi đầu vào.** Một API trả `false`, một API trả `null`, một API ném `ClassCastException`; cần chọn cách xử lý phù hợp thay vì chỉ đổi cú pháp.

## 20. Bài tập kiểm tra hiểu biết

### Bài 1 — Dự đoán kết quả `isInstance`

Cho:

```java
Object value = new StringBuilder("x");
boolean a = CharSequence.class.isInstance(value);
boolean b = String.class.isInstance(value);
boolean c = Object.class.isInstance(null);
```

**Đáp án:** `a=true`, `b=false`, `c=false`. `StringBuilder` implement `CharSequence` nhưng không phải `String`; `null` không là instance của class nào.

### Bài 2 — Dự đoán `Class.cast`

```java
Object value = Integer.valueOf(9);
Number n = Number.class.cast(value);
// String s = String.class.cast(value);
```

**Đáp án:** cast về `Number` thành công, còn cast về `String` biên dịch được nếu được sử dụng nhưng ném `ClassCastException` khi chạy.

### Bài 3 — `asSubclass` có thay đổi object không?

```java
Class<?> unknown = Integer.class;
Class<? extends Number> numberType =
        unknown.asSubclass(Number.class);
```

**Đáp án:** thành công vì `Integer extends Number`. Không tạo đối tượng `Integer` và không sửa class; chỉ trả token cùng runtime class dưới kiểu `Class<? extends Number>`.

### Bài 4 — Đảo chiều subtype

```java
boolean a = Number.class.isAssignableFrom(Integer.class);
boolean b = Integer.class.isAssignableFrom(Number.class);
```

**Đáp án:** `a=true`, `b=false`. Một biến `Number` giữ được `Integer`, nhưng một biến `Integer` không giữ được mọi `Number`.

### Bài 5 — `null` với hai API

```java
boolean a = String.class.isInstance(null);
String b = String.class.cast(null);
```

**Đáp án:** `a=false`, `b=null`. Muốn loại null từ input, thêm quy tắc API riêng.

### Bài 6 — Interface plugin

Bạn có `Class<?> loaded` do `Class.forName` trả, muốn biết class có implement `Runnable` và chỉ tạo instance nếu hợp lệ.

**Đáp án định hướng:** `Class<? extends Runnable> type = loaded.asSubclass(Runnable.class)`. Nếu kiểm tra qua, tiếp tục xác minh constructor và quyền truy cập rồi mới gọi `newInstance`; nếu không, `ClassCastException` thể hiện sai quan hệ kiểu. Không dùng unchecked cast trực tiếp từ `Class<?>`.

### Bài 7 — Generic collection từ API cũ

`List.class.isInstance(List.of(1,2))` cho `true`. Có thể kết luận đối tượng là `List<String>` không?

**Đáp án:** không. `List.class` không chứa type argument `String`. Muốn kết quả `List<String>` an toàn, kiểm tra từng phần tử và tạo typed copy như `checkedCopy`.

### Bài 8 — Lựa chọn giữa boolean và exception

Một form validation cần kiểm tra một object là `LocalDate` và tự tạo thông điệp “Ngày nhập không hợp lệ”. Nên dùng `Class.cast` trực tiếp hay `isInstance` rồi báo lỗi?

**Đáp án định hướng:** `LocalDate.class.isInstance(value)` phù hợp để quyết định nhánh và tạo thông báo domain; sau đó có thể dùng `LocalDate.class.cast(value)` để nhận typed value. `cast` trực tiếp hợp lý khi sai kiểu được xem là lỗi lập trình cần `ClassCastException`.

### Bài 9 — Đọc generic method sau erasure

Một method `<T> T requireNonNullType(Object, Class<T>)` có JVM descriptor trả `Object`. Vì sao source vẫn trả `T` an toàn khi dùng `expected.cast(value)`?

**Đáp án:** compiler kiểm tra quan hệ token `Class<T>` và generic return `T`, còn `Class.cast` kiểm tra runtime theo token được truyền. Descriptor erased không xóa việc kiểm tra này và không tạo class runtime chuyên biệt cho `T`.

### Bài 10 — Sửa một nhận định sai

“`asSubclass(Service.class)` thành công chứng minh plugin an toàn để thực thi và có public no-arg constructor.”

**Đáp án:** sai. Nó chỉ chứng minh class implement/extends kiểu `Service` theo runtime subtype relation. Constructor, access, khả năng tạo instance và mức độ tin cậy của code là những kiểm tra riêng.

## 21. Checklist trước khi dùng Java Reflection type token

- [ ] Mình đang kiểm tra một **instance** hay một **class token**?
- [ ] Nếu chỉ cần đúng/sai trên object, đã chọn `isInstance`?
- [ ] Nếu cần object typed `T`, đã chọn `cast` và có chính sách lỗi?
- [ ] Nếu cần class token `Class<? extends U>`, đã dùng `asSubclass(U.class)` thay unchecked cast?
- [ ] Đã xử lý `null` đúng hợp đồng?
- [ ] Đã phân biệt subtype của class/interface với type arguments generic bị xóa?
- [ ] Nếu nguồn là collection, đã kiểm tra từng phần tử theo schema chứ không chỉ `List.class`?
- [ ] Nếu nạp class động, đã tách xử lý `ClassNotFoundException`, `ClassCastException` và lỗi constructor?
- [ ] Có giới hạn danh sách các class được phép nạp khi đầu vào không đáng tin?
- [ ] Ví dụ compile-time và output runtime đã được thử với cả dữ liệu đúng và dữ liệu sai?
- [ ] Có tránh được raw types, unchecked casts không có bằng chứng và phép đổi kiểu thiếu an toàn không?

## Kết luận

Ba phương thức giải quyết ba nhu cầu reflection liên quan nhưng khác nhau:

- **`Class.isInstance(Object)`** kiểm tra một đối tượng có tương thích với token runtime không; trả `true` hoặc `false`, với `null` là `false`.
- **`Class.cast(Object)`** kiểm tra một đối tượng và trả typed value `T`; sai kiểu non-null ném `ClassCastException`, còn đầu vào `null` trả `null`.
- **`Class.asSubclass(Class<U>)`** kiểm tra quan hệ subtype của chính đối tượng `Class`, trả `Class<? extends U>` hoặc ném `ClassCastException`. Nó không khởi tạo object.

Khi kết hợp với **`Class<T>` token**, generics và reflection hỗ trợ xây những API ranh giới vừa linh hoạt vừa có kiểm tra runtime. Nhưng vì **type erasure**, ba phương thức này không tự kiểm tra `List<String>` ở mức phần tử. Hãy giữ các cam kết đúng phạm vi, dùng adapter kiểm tra dữ liệu lồng nhau và phân biệt rõ kiểm tra kiểu với conversion.
