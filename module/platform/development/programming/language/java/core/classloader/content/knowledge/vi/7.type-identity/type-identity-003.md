# So sánh `Class`, `instanceof`, `isInstance` và `isAssignableFrom`

> **Ngữ cảnh:** Java Core → ClassLoader → Định danh kiểu. Mục tiêu của bài là biết chính xác đang hỏi về **hai runtime type**, **một object và một runtime type**, hay **một tên class**; từ đó chọn phép so sánh phù hợp, hiểu ảnh hưởng của **defining class loader**, và tránh nhầm lẫn với generic types, primitive conversions, array covariance. Ví dụ dùng Java 17 trở lên, trừ chỗ ghi rõ khác.

## 1. Bốn công cụ đang trả lời những câu hỏi khác nhau

Giả sử `Dog extends Animal`, và một biến `value` đang giữ object `new Dog()`.

| Cú pháp/API | Câu hỏi nó trả lời | Kết quả với `Dog` và `Animal` |
| --- | --- | --- |
| `value.getClass() == Dog.class` | **Runtime class chính xác** của object có đúng là `Dog` không? | `true` |
| `value instanceof Animal` | Object không-null có thuộc kiểu `Animal` (kể cả subtype) không? | `true` |
| `Animal.class.isInstance(value)` | Tương đương phép thử object-vs-type nhưng type được cung cấp **động** bằng `Class<?>`? | `true` |
| `Animal.class.isAssignableFrom(Dog.class)` | Giá trị có runtime type `Dog` có thể **gán bằng widening reference** cho biến kiểu `Animal` không? | `true` |
| `Dog.class.isAssignableFrom(Animal.class)` | Một đối tượng *bất kỳ* có static type `Animal` có bảo đảm gán cho `Dog` không? | `false` |
| `Dog.class == Animal.class` | Hai runtime type có phải đúng cùng một `Class` không? | `false` |

**Câu ghi nhớ:** Với `T.class.isAssignableFrom(S.class)`, hãy đọc **“S gán vào T được không?”**, tức target `T` nằm **bên trái**. Với `T.class.isInstance(object)`, hãy đọc **“object là một instance của T không?”**. Với `==` giữa các `Class`, ta hỏi **“có phải đúng cùng runtime type không?”**, không tính polymorphism.

Minh họa quan hệ:

~~~text
Animal                  object = new Dog()
  ^
  | extends                   |
 Dog                          v
  |                 getClass() == Dog.class  --> true
  +----------------> object instanceof Animal --> true

Animal.class.isAssignableFrom(Dog.class)  --> true
Dog.class.isAssignableFrom(Animal.class)  --> false
~~~

Các thao tác nói trên thuộc **kiểm tra kiểu ở runtime**. Chúng không phải cơ chế so sánh dữ liệu nghiệp vụ (`equals` của object), và không thay thế việc compiler kiểm tra Java source code trước khi chương trình chạy.

## 2. `Class<?>` biểu diễn **kiểu runtime**, không chỉ là chuỗi tên

Mỗi class/interface đã được JVM định nghĩa có một đối tượng `java.lang.Class` biểu diễn nó trong VM. Các dạng khác cũng có `Class` tương ứng, như array, primitive và `void`:

~~~java
Class<String> textType = String.class;
Class<Integer> boxedType = Integer.class;
Class<?> primitiveType = int.class;
Class<?> arrayType = String[].class;
Class<?> voidType = void.class;
~~~

Những cách lấy `Class`:

- `MyType.class`: class literal, type được viết trong mã Java, không đòi hỏi tạo instance.
- `someObject.getClass()`: runtime class **chính xác** của object đang có; `someObject` là `null` thì `NullPointerException`.
- `Class.forName("pkg.MyType")`: tìm class bằng tên qua loader của caller, **có thể kích hoạt initialization** theo overload mặc định.
- `Class.forName(name, false, loader)`: tìm theo loader đã chọn mà **không yêu cầu** initialization lúc đó.
- `loader.loadClass(name)`: nhận `Class<?>` từ loader; kết quả có thể do một parent **định nghĩa**.

### 2.1. Tên class không đủ xác định runtime type

Với class/interface thông thường, JVMS xác định identity theo:

`(binary name, defining class loader)`

Một tên như `com.example.Plugin` có thể được định nghĩa bởi hai loader khác nhau; hai đối tượng `Class` tương ứng **không bằng nhau**, dù chúng đọc bytecode giống hệt nhau. Nếu hai loader chỉ **ủy quyền về cùng parent**, chúng có thể trả về **chính cùng `Class`**.

Vì thế:

~~~java
left.getName().equals(right.getName())
~~~

không suy ra:

~~~java
left == right
~~~

và cũng không suy ra:

~~~java
left.isAssignableFrom(right)
~~~

Đây là trung tâm của mọi lỗi “`X cannot be cast to X`” ở plugin/container. Thêm thông tin `getClassLoader()`, `getModule()`, runtime package và dependency provenance khi debug; đừng chỉ in `getName()`.

### 2.2. Khi nào dùng `==`, `equals` và `getName`?

Với hai biến `Class<?> left, right`:

- `left == right` kiểm tra **chính xác cùng đối tượng `Class`**. Dùng khi cần strict runtime identity.
- `left.equals(right)` có cùng ý nghĩa identity trong `Class` (không so sánh chỉ tên); `Class` không định nghĩa value equality dựa trên `getName()`.
- `left.getName().equals(right.getName())` so sánh **text binary name** (hoặc dạng tên đặc thù của array/hidden class), không chứng minh compatibility.
- `left.getSimpleName()` và `getCanonicalName()` có thể trùng hoặc vắng ở local/anonymous/hidden classes; chúng cũng không phải khóa định danh đáng tin cho plugin.

**Không dùng:** `clazz.toString().contains("...")` để quyết định assignability. Mã nghiệp vụ phải biểu diễn hợp đồng bằng type hierarchy hoặc explicit plugin metadata, không parse tên class.

## 3. `instanceof`: phép thử đối tượng với kiểu tham chiếu

Cú pháp Java 17:

~~~java
Object value = "hello";

boolean isText = value instanceof String;      // true
boolean isNumber = value instanceof Number;    // false
boolean isObject = value instanceof Object;    // true
boolean nullMatches = (null instanceof Object); // false
~~~

Điều cần nhớ:

1. Operand bên trái được tính như **một biểu thức**; nếu giá trị là `null` thì phép thử kiểu tham chiếu luôn trả `false`, không ném `NullPointerException`.
2. Nếu non-null, runtime kiểm tra object có compatible với reference type bên phải theo ngữ nghĩa Java (class, interface hoặc array) hay không.
3. Các subtype được chấp nhận. `instanceof Animal` đúng cho `Dog` nếu `Dog extends Animal`; nó **không** đòi runtime class chính xác bằng `Animal.class`.
4. Kiểu vế phải phải hợp lệ ở thời điểm **biên dịch**. Java 17 không cho bạn truyền động một biến `Class<?>` vào cú pháp `instanceof`.
5. Compiler cũng kiểm tra khả năng cast hợp lệ. Ví dụ `String s = "x"; boolean b = s instanceof Integer;` là lỗi biên dịch với Java 17 vì hai kiểu final không liên hệ kiểu phù hợp; đổi `s` thành `Object` thì phép kiểm tra runtime hợp lệ và trả `false`.

### 3.1. Pattern matching cho `instanceof` từ Java 16

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return "text length=" + text.length();
    }
    if (value instanceof Number number) {
        return "number=" + number;
    }
    return "other";
}
~~~

Đây là **method minh họa** được đặt bên trong một class, không phải tệp độc lập. Biến pattern `text` chỉ có thể dùng ở các phạm vi mà compiler xác định phép thử đã thành công. Đặc tính null và runtime assignability vẫn như `instanceof` truyền thống: `null` không match pattern.

**Chọn `instanceof` khi:** kiểu mục tiêu đã biết tại compile time và bạn đang phân nhánh theo kiểu object. Nếu chỉ cần gọi hành vi đa hình, một interface/virtual method thường rõ hơn chuỗi dài `if (obj instanceof ...)`.

### 3.2. `instanceof` khác ép kiểu

~~~java
Object candidate = "hello";
System.out.println(candidate instanceof Integer); // false

// ((Integer) candidate) biên dịch được nhưng sẽ ném ClassCastException
// khi chương trình cố chạy ép kiểu này.
~~~

`instanceof` trả `false` cho object không phù hợp, trong khi cast không hợp lệ ném `ClassCastException`. Từng là kiểu `Object` không làm object thực sự đổi thành `Integer`. Tính hợp lệ của code ở compile time cũng không bảo đảm cast sẽ thành công ở runtime.

## 4. `Class.isInstance(Object)`: `instanceof` với kiểu mục tiêu được chọn động

Chữ ký API:

~~~java
public boolean isInstance(Object obj)
~~~

Giả sử người dùng hoặc plugin chọn được `Class<?> selectedType` từ registry. Khi đó:

~~~java
boolean accepted = selectedType.isInstance(value);
~~~

là tương đương kiểm tra `value instanceof SelectedType` **nếu ta có thể viết `SelectedType` trong mã nguồn** (đối với phép thử kiểu tham chiếu). API phản ánh hierarchy runtime của classes, interfaces và arrays.

Tính chất:

- `String.class.isInstance("hi")` → `true`.
- `CharSequence.class.isInstance("hi")` → `true`.
- `Number.class.isInstance("hi")` → `false`.
- `String.class.isInstance(null)` → `false`; null là giá trị cho phép, không ném exception.
- `int.class.isInstance(Integer.valueOf(1))` → `false`. Primitive class không có object instance mang kiểu primitive; wrapper object có runtime class là `Integer`.
- `String[].class.isInstance(new String[2])` → `true`.
- `Object[].class.isInstance(new int[2])` → `false` (primitive array không phải `Object[]`).

**Trường hợp dùng:** framework cần kiểm tra object theo type cấu hình runtime, annotation metadata, SPI, serializer hoặc plugin contract. Nếu đã có `Class<T>`, có thể dùng `type.cast(value)` để thực hiện cast runtime với kiểm tra tương ứng; `cast` **ném `ClassCastException`** khi object khác null và không compatible, còn `isInstance` chỉ trả boolean.

### 4.1. Thí nghiệm: dynamic `Class<?>` và `isInstance`

Tệp **`DynamicTypeCheck.java`**:

~~~java
public class DynamicTypeCheck {
    public static void main(String[] args) throws Exception {
        Class<?> requested = Class.forName("java.lang.Number");
        Object first = Integer.valueOf(7);
        Object second = "seven";

        System.out.println("first: " + requested.isInstance(first));
        System.out.println("second: " + requested.isInstance(second));
        System.out.println("null: " + requested.isInstance(null));
        System.out.println("Integer type: "
                + requested.isAssignableFrom(Integer.class));
        System.out.println("String type: "
                + requested.isAssignableFrom(String.class));
    }
}
~~~

~~~bash
javac --release 17 DynamicTypeCheck.java
java DynamicTypeCheck
~~~

Stdout:

~~~text
first: true
second: false
null: false
Integer type: true
String type: false
~~~

Lời giải: `requested` là class token cho `Number`. `Integer` kế thừa `Number`, `String` không kế thừa; kiểm tra object trả true/false tương ứng. Dòng thử `null` luôn `false`. Hai dòng cuối so sánh **hai kiểu**, khác với ba dòng trước so sánh một **kiểu và một object**.

## 5. `Class.isAssignableFrom(Class<?>)`: quan hệ gán giữa **hai kiểu**

Chữ ký:

~~~java
public boolean isAssignableFrom(Class<?> cls)
~~~

Hãy đọc:

~~~java
Target.class.isAssignableFrom(Source.class)
~~~

là câu hỏi: **“Một giá trị có kiểu Source có thể gán cho biến kiểu Target bằng identity/widening reference conversion không?”**

~~~java
Number n = Integer.valueOf(1); // hợp lệ
// Integer i = (Number) ...;    // không được gán ngầm theo chiều ngược
~~~

Tương ứng:

~~~java
Number.class.isAssignableFrom(Integer.class); // true
Integer.class.isAssignableFrom(Number.class); // false
Object.class.isAssignableFrom(String.class);  // true
CharSequence.class.isAssignableFrom(String.class); // true
Runnable.class.isAssignableFrom(String.class); // false
String.class.isAssignableFrom(String.class);  // true
~~~

Mọi type đều assignable từ **chính nó**, kể cả interface, array, primitive. Một interface ở đích có thể nhận class implements nó; một class ở đích có thể nhận subtype. Hai interface có quan hệ `extends` được kiểm tra đúng chiều; hai interface không có quan hệ rõ ràng **không** tự tương thích chỉ vì có một class tình cờ implements cả hai.

**Chiều dễ nhầm:**

~~~java
Animal.class.isAssignableFrom(Dog.class) // true: Dog → Animal
Dog.class.isAssignableFrom(Animal.class) // false: Animal → Dog không tự động
~~~

Tên `isAssignableFrom` mô tả **receiver**: class ở vế trái phải “nhận được gán từ” đối số. Đây là phép thử **type-level**, hoàn toàn không cần tạo object.

### 5.1. `isAssignableFrom` và `isInstance` liên hệ thế nào?

Với object `obj != null`, khi biết `source = obj.getClass()`:

~~~java
target.isInstance(obj)
target.isAssignableFrom(obj.getClass())
~~~

có cùng kết quả về khả năng chuyển đổi reference trong các trường hợp class/interface/array thông thường. Nhưng **không thể thay thế một cách máy móc**:

- `obj == null`: `target.isInstance(null)` trả `false`, còn `obj.getClass()` ném `NullPointerException`.
- `isAssignableFrom` cần đầu vào là `Class<?>`, không phải object.
- `isInstance` cần object, không nhận một primitive value trực tiếp mà không boxing.
- Cả hai đều kiểm tra runtime class identity; tên binary giống nhau ở hai defining loaders **không** biến kết quả thành true.

Nếu `cls == null`, lời gọi `target.isAssignableFrom(null)` ném `NullPointerException` theo API, không trả false. Tính chất này khác với `target.isInstance(null)`.

### 5.2. Bảng chân trị điển hình

| Target ở bên trái | Source ở bên phải | `target.isAssignableFrom(source)` | Lý do |
| --- | --- | --- | --- |
| `Object.class` | `String.class` | `true` | `String` là subtype của `Object` |
| `Number.class` | `Integer.class` | `true` | Inheritance |
| `Integer.class` | `Number.class` | `false` | Không widening reference theo chiều này |
| `CharSequence.class` | `String.class` | `true` | `String implements CharSequence` |
| `Runnable.class` | `String.class` | `false` | `String` không implements `Runnable` |
| `Object.class` | `Object.class` | `true` | Cùng một type |
| `Object.class` | `int.class` | `false` | Không tự thực hiện boxing |
| `long.class` | `int.class` | `false` | Không thực hiện primitive widening |
| `int.class` | `int.class` | `true` | Chính cùng primitive type |
| `Object.class` | `int[].class` | `true` | Array là reference object |
| `Object[].class` | `int[].class` | `false` | Primitive array không phải object array |

**Không suy luận ngược:** `target.isAssignableFrom(source) == false` không có nghĩa ta *không bao giờ* cast được một object có compile-time type source sang target. Ví dụ một biến `Animal` có runtime object thực sự là `Dog` có thể cast sang `Dog` sau kiểm tra runtime; nhưng `Dog.class.isAssignableFrom(Animal.class)` vẫn là false vì không đúng cho mọi `Animal`.

## 6. Một ví dụ chạy đầy đủ để so sánh cả bốn phép kiểm tra

Tệp **`TypeCheckComparison.java`**:

~~~java
public class TypeCheckComparison {
    interface Tagged { }

    static class Animal { }

    static class Dog extends Animal implements Tagged { }

    static class Cat extends Animal { }

    public static void main(String[] args) {
        Object pet = new Dog();
        Object absent = null;

        System.out.println("exact Dog: "
                + (pet.getClass() == Dog.class));
        System.out.println("exact Animal: "
                + (pet.getClass() == Animal.class));

        System.out.println("instanceof Animal: "
                + (pet instanceof Animal));
        System.out.println("instanceof Tagged: "
                + (pet instanceof Tagged));
        System.out.println("instanceof Cat: "
                + (pet instanceof Cat));
        System.out.println("null instanceof Animal: "
                + (absent instanceof Animal));

        System.out.println("isInstance Animal: "
                + Animal.class.isInstance(pet));
        System.out.println("isInstance Cat: "
                + Cat.class.isInstance(pet));

        System.out.println("Animal <- Dog: "
                + Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Dog <- Animal: "
                + Dog.class.isAssignableFrom(Animal.class));
        System.out.println("Tagged <- Dog: "
                + Tagged.class.isAssignableFrom(Dog.class));
        System.out.println("Dog <- Dog: "
                + Dog.class.isAssignableFrom(Dog.class));
    }
}
~~~

~~~bash
javac --release 17 TypeCheckComparison.java
java TypeCheckComparison
~~~

Stdout:

~~~text
exact Dog: true
exact Animal: false
instanceof Animal: true
instanceof Tagged: true
instanceof Cat: false
null instanceof Animal: false
isInstance Animal: true
isInstance Cat: false
Animal <- Dog: true
Dog <- Animal: false
Tagged <- Dog: true
Dog <- Dog: true
~~~

Vì `pet` tham chiếu `new Dog()`, `pet.getClass()` là **chính xác `Dog.class`**. Điều đó không ngăn `Dog` trở thành instance của superclass `Animal` và interface `Tagged`. `Cat` là sibling subtype, không tương thích với `Dog`. Phép `isAssignableFrom` ở bốn dòng cuối không đọc `pet`: nó kiểm tra static relation giữa type tokens.

## 7. Null: bốn cách nhìn phải tách bạch

| Thao tác | Với `null` | Kết quả |
| --- | --- | --- |
| `null instanceof String` | Biểu thức `null` là null reference | `false` |
| `String.class.isInstance(null)` | Đối số object null | `false` |
| `String.class.cast(null)` | Cast null tới reference type | Trả về `null` |
| `((Object) null).getClass()` | Gọi instance method trên null | `NullPointerException` |
| `String.class.isAssignableFrom(null)` | Đối số `Class<?>` là null | `NullPointerException` |
| `String.class == null` | Class literal không null | `false` |

Lưu ý `Class<?> target = null; target.isInstance(value)` cũng ném `NullPointerException` vì **receiver** null, không phải vì `value`.

Trong validator động, kiểm tra kiểu thường cần phân biệt “`null` được chấp nhận theo business rule” với “đối tượng có đúng type không”:

~~~java
static boolean matches(Class<?> target, Object value, boolean nullable) {
    if (target == null) {
        throw new IllegalArgumentException("target required");
    }
    return value == null ? nullable : target.isInstance(value);
}
~~~

Đây là **method minh họa**, không phải tệp Java độc lập. `isInstance(null)` mặc định là false là quy tắc Java; việc chấp nhận null là **chính sách ứng dụng**, cần xử lý riêng.

## 8. Interface, abstract class và polymorphism

Các phương thức kiểm tra class/interface không yêu cầu target phải là concrete class:

~~~java
interface Service { }
abstract class BaseService implements Service { }
final class LiveService extends BaseService { }
~~~

Trong ngữ cảnh các khai báo ở trên:

~~~java
Service.class.isAssignableFrom(LiveService.class);     // true
BaseService.class.isAssignableFrom(LiveService.class); // true
LiveService.class.isAssignableFrom(BaseService.class); // false
~~~

`Service.class.isInstance(new LiveService())` → `true`, dù không thể tạo đối tượng trực tiếp của interface `Service`. Một class có thể implements nhiều interface; quan hệ assignability theo **kiểu**, không theo việc target tự tạo instance được hay không.

Với interface `A` và `B` không có `extends` giữa chúng, dù có `class C implements A, B`, `A.class.isAssignableFrom(B.class)` vẫn là `false`. Nhưng `A.class.isInstance(new C())` và `B.class.isInstance(new C())` đều `true`.

Tránh dùng `getClass() == BaseService.class` để kiểm tra “có phải một dịch vụ loại BaseService không?”, vì mọi subclass bị loại. Nếu muốn chấp nhận subclass, dùng `instanceof` hoặc `isInstance`.

## 9. Arrays: covariance, marker interfaces và primitive arrays

Array trong Java là **reference type**, nhưng phải xét **component type**.

### 9.1. Object array có covariance theo component reference type

~~~java
Object[].class.isAssignableFrom(String[].class); // true
Number[].class.isAssignableFrom(Integer[].class); // true
String[].class.isAssignableFrom(Object[].class); // false
~~~

Bởi vì `String` là subtype của `Object` và `Integer` là subtype của `Number`, quan hệ reference component cho phép covariance ở array. Quy tắc này không kéo theo việc ghi bất kỳ object nào vào mảng:

~~~java
Object[] data = new String[1];
// Dòng sau biên dịch nhưng ném ArrayStoreException tại runtime:
// data[0] = Integer.valueOf(10);
~~~

Array vẫn ghi nhớ runtime component type `String`. Compile-time type `Object[]` không cho phép ghi đè giới hạn runtime đó.

### 9.2. Primitive arrays không phải `Object[]`

~~~java
Object.class.isAssignableFrom(int[].class);       // true
Cloneable.class.isAssignableFrom(int[].class);    // true
java.io.Serializable.class.isAssignableFrom(int[].class); // true
Object[].class.isAssignableFrom(int[].class);     // false
int[].class.isAssignableFrom(long[].class);       // false
~~~

Mọi array class kế thừa `Object` và implements marker interfaces `Cloneable`, `Serializable`. Nhưng `int[]` là một mảng chứa **primitive int**, không phải `Object[]`, và primitive array có component type khác nhau không covariance như reference arrays.

### 9.3. Ví dụ runnable

Tệp **`ArrayTypeChecks.java`**:

~~~java
import java.io.Serializable;

public class ArrayTypeChecks {
    public static void main(String[] args) {
        Object textArray = new String[2];
        Object numbers = new int[2];

        System.out.println(textArray instanceof Object[]);
        System.out.println(textArray instanceof Cloneable);
        System.out.println(Object[].class.isInstance(numbers));
        System.out.println(Object.class.isAssignableFrom(int[].class));
        System.out.println(Cloneable.class.isAssignableFrom(int[].class));
        System.out.println(Serializable.class.isAssignableFrom(int[].class));
        System.out.println(Number[].class.isAssignableFrom(Integer[].class));
        System.out.println(Object[].class.isAssignableFrom(int[].class));
        System.out.println(int[].class.isAssignableFrom(long[].class));
    }
}
~~~

~~~bash
javac --release 17 ArrayTypeChecks.java
java ArrayTypeChecks
~~~

Stdout theo thứ tự:

~~~text
true
true
false
true
true
true
true
false
false
~~~

Điểm quan trọng: `int[]` vừa là `Object`, `Cloneable`, `Serializable`, nhưng không phải `Object[]`. Không dùng suy luận “mảng nào cũng Object[]” khi viết APIs nhận dữ liệu động.

## 10. Primitive, wrapper, boxing và widening: vì sao kết quả khác phép gán trong Java source?

Đây là nơi tên `isAssignableFrom` dễ gây ngộ nhận nhất. Phương thức này kiểm tra **identity/widening reference conversion**, hoặc **chính cùng primitive type**; nó **không** tự chạy boxing, unboxing, primitive widening hoặc chuỗi chuyển đổi compile-time để biến primitive `int` thành `long`/`Object`.

Ví dụ Java source **hợp lệ**:

~~~java
long wide = 12;     // primitive widening: int -> long
Object boxed = 12;  // boxing int -> Integer, sau đó widening reference
Number n = 12;      // boxing int -> Integer -> Number
~~~

Nhưng các kiểm tra type token:

~~~java
long.class.isAssignableFrom(int.class);       // false
Object.class.isAssignableFrom(int.class);     // false
Number.class.isAssignableFrom(int.class);     // false
Integer.class.isAssignableFrom(int.class);    // false
int.class.isAssignableFrom(int.class);        // true
Object.class.isAssignableFrom(Integer.class); // true
Number.class.isAssignableFrom(Integer.class); // true
~~~

`int.class.isInstance(Integer.valueOf(12))` → `false`, vì `Integer` là một **reference object**, không phải primitive value object của `int.class`. Trái lại `Integer.class.isInstance(Integer.valueOf(12))` → `true`.

**Không mở rộng cách hiểu `isAssignableFrom` thành “mọi phép gán viết được bằng Java code”.** Compiler có các quy tắc conversion riêng (boxing/unboxing, widening primitive, constant narrowing trong một số trường hợp); `Class.isAssignableFrom` không mô phỏng tất cả.

## 11. Generics và type erasure: `Class` không mang `List<String>` runtime token

Phần lớn generic type arguments không được reified như một runtime class riêng:

~~~java
java.util.List<String> names =
        new java.util.ArrayList<>();
java.util.List<Integer> ages =
        new java.util.ArrayList<>();

System.out.println(names.getClass() == ages.getClass()); // true
System.out.println(java.util.List.class.isInstance(names)); // true
System.out.println(java.util.List.class.isInstance(ages));  // true
~~~

Ba câu in trên thuộc **một đoạn minh họa** có thể đặt trong `main`, không phải tệp độc lập.

- `List.class` đại diện **raw class/interface** tại runtime, không có `List<String>.class`.
- Không thể dùng `value instanceof List<String>` trong Java 17 vì kiểu tham số hóa cụ thể không reifiable; `value instanceof List<?>` thì hợp lệ.
- `List.class.isAssignableFrom(ArrayList.class)` trả `true` cho hierarchy raw types, không kiểm tra phần tử là `String` hay `Integer`.
- `Class<?>` không phân biệt `List<String>` và `List<Integer>` từ object thực; generic signature có thể lưu trong **metadata của khai báo** (ví dụ `Field.getGenericType()` trả `Type`), không biến thành runtime element-type validation.

Nếu một serializer/validator cần phân biệt `List<String>` và `List<Integer>`, hãy truyền token của **kiểu đầy đủ** bằng cơ chế như `ParameterizedType`/type reference, rồi **kiểm tra từng phần tử** khi chính sách đòi hỏi. Đừng suy ra generic argument runtime chỉ từ `getClass()` của `ArrayList`.

**Điểm phân biệt:** Array có runtime component type thật (ví dụ `String[]`), nên store check tạo `ArrayStoreException`. Generic `List<String>` không kiểm tra runtime type argument theo cùng kiểu array covariance.

## 12. Tác động ClassLoader: hai lớp **cùng tên** vẫn không tương thích

Khi một plugin loader và một host loader định nghĩa class có cùng binary name, mỗi lớp là runtime type khác. Khi đó:

~~~java
hostType.getName().equals(pluginType.getName()); // có thể true
hostType == pluginType;                          // false
hostType.isAssignableFrom(pluginType);           // thường false
hostType.isInstance(pluginObject);               // thường false
~~~

Các kết quả assignability/instance còn tùy hierarchy thực của plugin class; trường hợp minh họa dưới đây chủ ý chỉ dùng hai bản riêng biệt của cùng một class **không có inheritance nối hai bản**.

### 12.1. Ví dụ hai defining loaders, thực thi với Java 17+

Tạo hai file cạnh nhau.

**`Widget.java`**:

~~~java
public class Widget {
    public Widget() { }
}
~~~

**`LoaderIdentityDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;

public class LoaderIdentityDemo {
    static final class IsolatedWidgetLoader extends ClassLoader {
        IsolatedWidgetLoader() {
            super(LoaderIdentityDemo.class.getClassLoader());
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals("Widget")) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    result = findClass(name);
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("Widget")) {
                throw new ClassNotFoundException(name);
            }
            try (InputStream in = LoaderIdentityDemo.class
                    .getClassLoader().getResourceAsStream("Widget.class")) {
                if (in == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = in.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Widget hostObject = new Widget();
        Class<?> hostType = Widget.class;

        Class<?> pluginType =
                new IsolatedWidgetLoader().loadClass("Widget");
        Object pluginObject =
                pluginType.getDeclaredConstructor().newInstance();

        System.out.println("same name: "
                + hostType.getName().equals(pluginType.getName()));
        System.out.println("same Class: " + (hostType == pluginType));
        System.out.println("same defining loader: "
                + (hostType.getClassLoader()
                        == pluginType.getClassLoader()));
        System.out.println("host type accepts plugin: "
                + hostType.isInstance(pluginObject));
        System.out.println("plugin type accepts host: "
                + pluginType.isInstance(hostObject));
        System.out.println("assignable across loaders: "
                + hostType.isAssignableFrom(pluginType));
        System.out.println("plugin accepts own object: "
                + pluginType.isInstance(pluginObject));
        System.out.println("pluginObject instanceof Widget: "
                + (pluginObject instanceof Widget));
    }
}
~~~

~~~bash
javac --release 17 Widget.java LoaderIdentityDemo.java
java -cp . LoaderIdentityDemo
~~~

Stdout:

~~~text
same name: true
same Class: false
same defining loader: false
host type accepts plugin: false
plugin type accepts host: false
assignable across loaders: false
plugin accepts own object: true
pluginObject instanceof Widget: false
~~~

**Tại sao?** Loader tùy biến chọn **định nghĩa riêng** chỉ với `Widget`; với tên còn lại, nó ủy quyền cho parent như thông thường. Khi Java code dùng `Widget.class` hoặc `new Widget()` ở phía host, chúng thuộc application loader. Khi `IsolatedWidgetLoader` đọc `Widget.class` bytes và gọi `defineClass`, VM tạo một type **mới** trong namespace loader mới. Cả hai có cùng `getName()`, nhưng `==`/`isInstance`/`isAssignableFrom` theo runtime identity lại khác nhau.

**Giới hạn demo:** Class loader này chỉ để minh họa identity, không phải implementation plugin production. Plugin thực tế cần thiết kế package ownership, dependency delegation, exception/linking, concurrent loading, resource lookup, module access, lifecycle/unloading và ranh giới trust. Đừng chuyển mọi class thành child-first một cách mù quáng: một shared interface/API từ host thường phải được cả hai phía nhìn thấy dưới **cùng defining loader**.

### 12.2. Lỗi “`Widget cannot be cast to Widget`”

Giả sử plugin tạo `pluginObject`. Cast dưới đây có thể compile vì biến nguồn là `Object` nhưng runtime ném `ClassCastException`:

~~~java
// Widget hostView = (Widget) pluginObject;  // thất bại ở runtime
~~~

Thông báo lỗi đôi khi hiển thị tên lớp trùng nhau kèm thông tin loader/module. Đây không phải nghịch lý: tên giống nhau **không** có nghĩa hai runtime types giống nhau. Cách sửa thường là chia sẻ đúng interface/DTO/contract với parent, hoặc tránh ép cast object xuyên classloader boundary; kiểm tra bản dependency trùng giữa host/plugin và vị trí deploy.

## 13. `Class.cast` và `Class.asSubclass`: khi cần chuyển từ kiểm tra sang thao tác

Hai API liên quan, rất hữu ích trong registry/plugin framework:

~~~java
Class<? extends Number> accepted =
        Integer.class.asSubclass(Number.class);

Number n = accepted.cast(Integer.valueOf(5));
~~~

- `Class.cast(Object)` thực hiện checked cast từ object theo runtime class, **trả `null` nếu tham số null**, hoặc ném `ClassCastException` nếu object không compatible.
- `Class.asSubclass(Class<U>)` xác nhận **một `Class` có phải subtype của U**; nếu có, trả token typed `Class<? extends U>`; nếu không, ném `ClassCastException`.
- `isInstance`/`isAssignableFrom` trả boolean để rẽ nhánh; `cast`/`asSubclass` hữu ích khi cần tiếp tục với kiểu generic tĩnh an toàn hơn.

Ví dụ method generic để filter:

~~~java
static <T> T castOrNull(Class<T> target, Object candidate) {
    return target.isInstance(candidate)
            ? target.cast(candidate)
            : null;
}
~~~

Đây là method minh họa không độc lập. Nếu business domain cho phép candidate null có ý nghĩa khác với “type mismatch”, không nên gộp cả hai tình huống thành `null`; hãy dùng `Optional`, kết quả có trạng thái hoặc kiểm tra null tường minh.

### 13.1. Chọn đúng API trong một registry

Giả sử plugin registry nhận `Class<?> providedType` và contract `Service.class`:

~~~java
if (!Service.class.isAssignableFrom(providedType)) {
    throw new IllegalArgumentException("Expected Service subtype");
}
Class<? extends Service> serviceType =
        providedType.asSubclass(Service.class);
~~~

Đây là **snippet phụ thuộc interface `Service` do project định nghĩa**. Kiểm tra này chỉ xác nhận inheritance/interface identity. Nó **không bảo đảm** class có public constructor, class không abstract, module cho phép reflective invocation, dependency có mặt hay plugin đáng tin cậy.

Khi đã có một instance do plugin trả:

~~~java
if (Service.class.isInstance(pluginObject)) {
    Service service = Service.class.cast(pluginObject);
}
~~~

Các đoạn này phụ thuộc đúng **cùng `Service.class`** qua loader boundary. Nếu host và plugin mỗi bên định nghĩa `Service` riêng, `isAssignableFrom` có thể trả `false` dù tên `Service` trên cả hai phía bằng nhau.

## 14. Các ngộ nhận thường gặp

| Ngộ nhận | Điều đúng |
| --- | --- |
| `getClass() == Parent.class` sẽ nhận mọi subtype | Chỉ true với **đúng runtime class**; dùng `instanceof`/`isInstance` cho subtype |
| `a.getClass().getName().equals(b.getClass().getName())` nghĩa là cùng type | Sai nếu defining class loader khác |
| `Target.isAssignableFrom(Source)` đọc theo “Target có thể gán sang Source” | Sai chiều; phải đọc **“Source có thể gán vào Target”** |
| `isAssignableFrom` mô phỏng tất cả Java assignment conversions | Sai: không boxing/unboxing hay widening primitives |
| `int.class.isInstance(1)` phải true | Sai: khi truyền vào API `Object`, `1` được boxing; primitive `Class` không chứa object instances |
| `List.class.isInstance(list)` xác minh phần tử đều là String | Sai: type erasure |
| `null instanceof T` ném lỗi | Sai: trả false; lỗi xảy ra khi dereference null |
| `isAssignableFrom(null)` trả false | Sai: `NullPointerException` |
| `Object[].class.isAssignableFrom(int[].class)` true vì `int[]` là Object | Sai: primitive array là Object nhưng không phải `Object[]` |
| Hai loader khác nhau luôn tạo hai `Class` khác nhau | Sai nếu cả hai ủy quyền cùng defining loader |
| `instanceof` cũng là so sánh classloader? | Kiểm tra runtime type sử dụng identity do loader xác định; không trực tiếp so sánh object loader như giá trị |
| `Class.forName` luôn không khởi tạo class | Sai: overload một chuỗi mặc định yêu cầu initialization; overload có `initialize=false` có thể tránh yêu cầu ấy |

## 15. Quy trình chẩn đoán khi so sánh kiểu bất ngờ trả `false`

1. **Xác minh object thực:** `obj == null`? Nếu không, in `obj.getClass().getName()` và `obj.getClass().getClassLoader()`.
2. **Xác minh target:** in `target.getName()`, `target.getClassLoader()` và `target.getModule()`, so với source/runtime object.
3. **Kiểm tra chiều assignability:** `Target.class.isAssignableFrom(Source.class)`, tránh viết ngược.
4. **Kiểm tra classpath/plugin graph:** JAR trùng FQCN? Có child-first loader hay module layer mới? Có parent delegation trả về type khác dự kiến?
5. **Kiểm tra array/primitive/generics:** primitive wrapper, boxing/unboxing, `Object[]` vs `int[]` và erased generic arguments.
6. **Kiểm tra compilation vs runtime:** compiler có thể cấm `instanceof` vì cast inconvertible, trong khi API dynamic kiểm tra runtime class token có thể trả false; đây không nhất thiết là bug.
7. **Ưu tiên contract thay vì đoán tên:** xác định một interface/abstract parent chung thực sự được define bởi cùng loader; khi cần kiểm tra exact class dùng `==`, khi cần polymorphism dùng `instanceof`/`isInstance`.

Đoạn log hỗ trợ:

~~~java
static void explain(Class<?> target, Object source) {
    if (source == null) {
        System.out.println("source is null");
        return;
    }
    Class<?> actual = source.getClass();
    System.out.println("actual: " + actual.getName());
    System.out.println("actual loader: " + actual.getClassLoader());
    System.out.println("target: " + target.getName());
    System.out.println("target loader: " + target.getClassLoader());
    System.out.println("exact: " + (actual == target));
    System.out.println("instance: " + target.isInstance(source));
    System.out.println("assignable: " + target.isAssignableFrom(actual));
}
~~~

Method minh họa cần đặt trong class và truyền `target != null`. Khi log trong production, hạn chế in giá trị object/đường dẫn có thể chứa thông tin nhạy cảm; metadata loader được dùng để chẩn đoán quan hệ định danh kiểu.

## 16. Bài tập tự kiểm tra

Với:

~~~java
interface Pet { }
class Animal { }
class Dog extends Animal implements Pet { }
class Cat extends Animal { }
Object dog = new Dog();
~~~

Các khai báo trên được đặt trong cùng phạm vi Java thích hợp.

1. `dog instanceof Animal` → **true**, vì Dog extends Animal.
2. `dog.getClass() == Animal.class` → **false**, vì class chính xác là Dog.
3. `Pet.class.isInstance(dog)` → **true**, vì Dog implements Pet.
4. `Animal.class.isAssignableFrom(Dog.class)` → **true**; đảo chiều → **false**.
5. `Cat.class.isInstance(dog)` → **false**; cùng superclass không khiến hai sibling classes tương thích.
6. `Object[].class.isAssignableFrom(String[].class)` → **true**, nhưng `Object[].class.isAssignableFrom(int[].class)` → **false**.
7. `long.class.isAssignableFrom(int.class)` → **false**, dù `long x = 1` hợp lệ.
8. Nếu `Dog` được define riêng ở hai loaders, `Dog` tokens hai bên cùng `getName()` thì `==` có true không? **Không**.
9. Nếu `Class<?> runtimeType = Dog.class`, nên dùng gì để kiểm tra `dog`? **`runtimeType.isInstance(dog)`**.
10. Nếu chỉ có `Class<?> source, target`, nên kiểm tra gì trước khi nhận loại source? **`target.isAssignableFrom(source)`**.

## 17. Tài liệu chuẩn

- [`java.lang.Class` API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html) — hợp đồng chính thức cho `isInstance`, `isAssignableFrom`, `getClassLoader`, `cast`, `asSubclass`, primitive và array class tokens.
- [JLS `15.20.2` — Type Comparison Operator `instanceof` (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2) — quy tắc compile time, null và kiểm tra runtime ở Java 17.
- [JLS `5` — Conversions and Contexts (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html) — identity, widening reference, boxing/unboxing và casting.
- [JLS `4.7` — Reifiable Types (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7) — vì sao `List<String>` không thể dùng như runtime token và `List<?>` có thể kiểm tra.
- [JVMS `5.3` — Creation and Loading (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3) — type identity theo **binary name + defining loader**, array classes và initiating/defining loaders.
- [`ClassLoader` API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html) — delegation và `defineClass`, bối cảnh cho plugin isolation.

**Nhớ ba câu:** `==` giữa `Class` kiểm tra **định danh kiểu chính xác**; `instanceof`/`Class.isInstance` kiểm tra **object có thuộc kiểu (kể cả subtype)**; `Target.class.isAssignableFrom(Source.class)` kiểm tra **quan hệ gán Source → Target**. Cả ba đều dựa trên **runtime type identity**, mà với class thông thường identity bao gồm cả **defining class loader**.
