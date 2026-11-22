# Thông tin chữ ký generic còn lưu trong class file

## 1. Xóa kiểu không có nghĩa mọi dấu vết generic đều biến mất

Java Generics chủ yếu cung cấp **kiểm tra kiểu tại thời điểm biên dịch**. Sau khi kiểm tra, trình biên dịch dùng cơ chế *type erasure* (xóa kiểu) để tạo mô tả kiểu mà JVM có thể sử dụng. Chẳng hạn, `List<String>` và `List<Integer>` đều dùng cùng class runtime `java.util.ArrayList`; JVM không sinh một bản riêng của `ArrayList` cho mỗi đối số kiểu.

Tuy nhiên, câu nói “sau biên dịch không còn bất kỳ thông tin generic nào” là **không chính xác**. Class file có thể lưu **chữ ký generic được khai báo** bằng thuộc tính `Signature`. Nhờ vậy, công cụ như `javap` và API reflection có thể đọc lại những phần khai báo như:

- Tên và giới hạn của tham số kiểu, ví dụ `<T extends Number & Comparable<T>>`.
- Kiểu cha/interface có đối số kiểu, ví dụ `extends Base<String>`.
- Kiểu của field khai báo `List<String>`.
- Kiểu generic ở tham số, kết quả và một số thành phần chữ ký method/constructor.
- Wildcard `? extends`, `? super`, mảng generic và type variable khi chúng xuất hiện trong chữ ký được lưu.

Điểm mấu chốt là cần phân biệt hai lớp thông tin:

1. **Descriptor đã xóa**: kiểu JVM dùng để định danh field/method, gọi phương thức và kiểm tra bytecode, ví dụ `Ljava/util/List;`.
2. **Generic signature**: metadata bổ sung mô tả khai báo generic, ví dụ `Ljava/util/List<Ljava/lang/String;>;`.

`Signature` không làm mỗi đối tượng tự nhớ lại mọi đối số kiểu được dùng tại biểu thức `new`. Nó giúp khôi phục **thông tin ở vị trí khai báo** mà compiler đã ghi vào class file.

## 2. Đọc đúng ba khái niệm: kiểu ở mã nguồn, descriptor và Signature

Xét khai báo:

```java
class Catalog {
    java.util.List<String> names;
}
```

Đây là một class Java hợp lệ, chưa có chương trình `main`.

Trong mã nguồn, `names` có kiểu `List<String>`. Sau xóa kiểu, **field descriptor** là:

```text
Ljava/util/List;
```

Nếu compiler ghi generic `Signature` cho field, chuỗi metadata tương ứng là:

```text
Ljava/util/List<Ljava/lang/String;>;
```

Hai chuỗi này cùng mô tả field từ hai góc độ khác nhau:

| Góc nhìn | Biểu diễn | Mục đích chính |
|---|---|---|
| Java source type | `List<String>` | Compiler kiểm tra kiểu khi viết và dùng `names` |
| JVM field descriptor | `Ljava/util/List;` | Định dạng bytecode đã xóa dùng cho field |
| Generic Signature attribute | `Ljava/util/List<Ljava/lang/String;>;` | Giữ lại đối số kiểu `String` trong metadata khai báo |

Các ký hiệu trong hai chuỗi **không** phải chính cú pháp Java source:

- `L...;` ký hiệu một kiểu class/interface tham chiếu trong descriptor hoặc signature.
- `/` phân tách các thành phần tên nội bộ JVM, ví dụ `java/util/List`.
- `<...>` bên trong signature mã hóa đối số kiểu khi có.
- Chữ ký này được ghi dưới dạng chuỗi theo ngữ pháp class file của JVM, chứ không lưu một đối tượng `ParameterizedType` Java được khởi tạo sẵn. Reflection có thể đọc và diễn giải chuỗi đó khi ứng dụng yêu cầu.

Một class file còn có thể chứa những thuộc tính khác như `Code`, `Exceptions`, `RuntimeVisibleAnnotations`, `LocalVariableTable` hoặc `LocalVariableTypeTable`. Chúng có vai trò riêng; **không được đồng nhất tất cả với `Signature`**.

## 3. Thuộc tính `Signature` nằm ở đâu?

Theo định dạng Java class file, `Signature` là một thuộc tính gắn với các cấu trúc có thể có khai báo generic, cụ thể là:

- **Class/interface**: lưu tham số kiểu của class/interface và biểu diễn generic của superclass/superinterfaces.
- **Field**: lưu kiểu generic của trường.
- **Method** (bao gồm constructor ở dạng method trong class file): lưu phần chữ ký generic liên quan đến type parameters, parameter types, return type và throws signatures nếu thích hợp.

Một ví dụ tổng hợp:

```java
import java.io.Serializable;
import java.util.List;

class Box<T extends Number & Comparable<T>> implements Serializable {
    private T value;
    private List<? extends T> history;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void replace(T next) {
        value = next;
    }

    List<? extends T> history() {
        return history;
    }
}
```

Đây là class để phân tích, không có `main`. Các vị trí chứa dấu vết generic:

| Thành phần | Kiểu ở Java source | Kiểu/descriptor sau erasure | Thông tin có thể còn trong Signature |
|---|---|---|---|
| Tham số kiểu `T` | `T extends Number & Comparable<T>` | Erasure của `T` là `Number` | Tên `T`, giới hạn `Number`, `Comparable<T>` |
| `value` | `T` | `Number` | Field có type variable `T` |
| `history` | `List<? extends T>` | `List` | `List` với wildcard upper bound `T` |
| `Box(T)` | Tham số `T` | `(Number)void` ở mức descriptor | Constructor nhận `T` |
| `get()` | Trả `T` | Trả `Number` | Method trả `T` |
| `replace(T)` | Nhận `T` | Nhận `Number` | Method nhận `T` |
| `history()` | Trả `List<? extends T>` | Trả `List` | Method trả kiểu generic có wildcard |

Class file chỉ cần một số `Signature` tương ứng với các khai báo thực sự yêu cầu biểu diễn generic. Một thành viên hoàn toàn không generic có thể **không có** thuộc tính này. Không nên mặc định mọi field hoặc mọi method đều được gắn `Signature`.

### `Signature` là metadata bổ sung

JVM định danh các phương thức bằng tên và descriptor; `Signature` không thay thế descriptor, không phải một thành phần bổ sung trong lời gọi phương thức và không tự áp đặt phép kiểm tra rằng `ArrayList` runtime đang chứa toàn `String`.

Khi thực thi bytecode, JVM vẫn dựa trên các kiểu đã xóa, kiểm tra kiểu runtime thông thường và các lệnh cast mà compiler sinh. Generic signature phục vụ biểu diễn khai báo và cho các công cụ có khả năng hiểu generic.

## 4. Ví dụ thực hành: `javap` thấy cả descriptor lẫn generic signature

Tạo tệp **`SignatureClassFileDemo.java`** với nội dung đầy đủ:

```java
import java.util.List;

public class SignatureClassFileDemo<T extends Number & Comparable<T>> {
    private T value;
    private List<? extends T> history;

    public SignatureClassFileDemo(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public void set(T next) {
        value = next;
    }

    public List<? extends T> history() {
        return history;
    }

    public static void main(String[] args) {
        SignatureClassFileDemo<Integer> box =
                new SignatureClassFileDemo<>(7);
        System.out.println(box.get());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SignatureClassFileDemo.java
java SignatureClassFileDemo
```

Stdout:

```text
7
```

Dùng công cụ đi cùng JDK:

```bash
javap -p -s SignatureClassFileDemo
```

Tập trung vào những đoạn có ý nghĩa dưới đây (đây là **bản trích rút gọn**, không phải toàn bộ kết quả từ lệnh):

```text
private T value;
  descriptor: Ljava/lang/Number;

private java.util.List<? extends T> history;
  descriptor: Ljava/util/List;

public T get();
  descriptor: ()Ljava/lang/Number;

public void set(T);
  descriptor: (Ljava/lang/Number;)V

public java.util.List<? extends T> history();
  descriptor: ()Ljava/util/List;
```

Ý nghĩa:

- `T` có **giới hạn đứng đầu là `Number`**, nên tại chỗ dùng `T`, descriptor dùng `Number`.
- `List<? extends T>` bị xóa thành `List`; wildcard không xuất hiện trong descriptor.
- Phương thức `get()` trả về `Number` ở descriptor, nhưng `javap` vẫn có thể hiển thị khai báo `T` nhờ đọc generic metadata.
- `V` biểu thị kiểu trả về `void` trong method descriptor.

Để xem rõ thuộc tính lưu trong class file:

```bash
javap -p -v SignatureClassFileDemo
```

Tìm các dòng có nhãn `Signature:`. Ký hiệu `#...` tham chiếu tới constant pool có thể thay đổi giữa các bản biên dịch, nhưng các chuỗi signature cần chú ý gồm:

```text
TT;
Ljava/util/List<+TT;>;
()TT;
(TT;)V
<T:Ljava/lang/Number;:Ljava/lang/Comparable<TT;>;>Ljava/lang/Object;
```

Đây là **các mẫu chuỗi signature liên quan**, không phải một đoạn output nguyên trạng theo đúng thứ tự trong `javap -v`. `TT;` nói tới type variable có tên `T`. Phần `+TT;` biểu diễn một wildcard `? extends T`. Chữ ký cuối lưu khai báo type parameter `T` cùng hai giới hạn và superclass `Object` của class.

Nếu muốn xem cả những phép ép kiểu do xóa kiểu tạo ra trong thân method, dùng:

```bash
javap -p -c SignatureClassFileDemo
```

`-c` hiển thị bytecode; `-s` hiển thị descriptor; `-v` cung cấp thông tin class file mở rộng, trong đó có các thuộc tính `Signature`. Đọc ba góc nhìn này cùng nhau giúp tránh nhầm metadata với logic runtime.

## 5. Cú pháp cơ bản của chuỗi generic Signature

Generic signature dùng một ngữ pháp riêng do JVM Specification định nghĩa. Không cần học thuộc hết ngữ pháp để lập trình ứng dụng, nhưng nhận diện một số ký hiệu giúp đọc `javap -v` và phân tích thư viện.

| Mẫu | Ý nghĩa minh họa |
|---|---|
| `Ljava/lang/String;` | Một kiểu class `String` |
| `Ljava/util/List<Ljava/lang/String;>;` | `List<String>` |
| `TT;` | Type variable tên `T` |
| `Ljava/util/List<TT;>;` | `List<T>` |
| `Ljava/util/List<+Ljava/lang/Number;>;` | `List<? extends Number>` |
| `Ljava/util/List<-Ljava/lang/Integer;>;` | `List<? super Integer>` |
| `Ljava/util/List<*>;` | `List<?>` |
| `[TT;` | Mảng `T[]` trong cú pháp signature |
| `(TT;)TT;` | Method nhận `T`, trả `T` |
| `<E:Ljava/lang/Object;>(TE;)TE;` | Method khai báo `<E>`, nhận `E`, trả `E` |

Các dấu quan trọng:

- `T` mở đầu biểu diễn *type variable signature*, còn tên biến kiểu nằm trước dấu `;`. Bởi vậy `TT;` là cú pháp “type variable `T`”, không phải class tên `TT`.
- `+` biểu diễn wildcard có upper bound (`? extends`).
- `-` biểu diễn wildcard có lower bound (`? super`).
- `*` biểu diễn wildcard không ràng buộc (`?`).
- `[` biểu diễn mảng.
- Cặp ngoặc `(...)` chứa các kiểu tham số method.
- Trong phần khai báo type parameter, dấu `:` mã hóa class/interface bound; với nhiều bound, có thể có nhiều dấu `:`.

Mã generic của **một class cụ thể** có thể chứa thêm nội dung như superclass, superinterfaces, return/throws signatures. Bảng chỉ nhằm giải thích các mẫu cơ bản, không thay thế toàn bộ ngữ pháp quy định trong JVMS.

### `List<?>` không cùng nghĩa với raw `List`

Mặc dù cả hai thường có cùng descriptor `Ljava/util/List;`, kiểu nguồn `List<?>` có wildcard với các kiểm tra kiểu nhất định, còn raw `List` chủ động bỏ thông tin tham số kiểu và có thể gây cảnh báo unchecked.

Nếu declaration có `List<?>`, generic signature có thể ghi lại wildcard `*`. Nếu declaration dùng raw `List`, sẽ không có đối số kiểu để mã hóa ở vị trí đó. Chúng không nên được đánh đồng chỉ vì descriptor trùng nhau.

## 6. Reflection có thể đọc generic ở khai báo

Java Reflection cung cấp hai nhóm API cần phân biệt:

- Các phương thức trả về `Class<?>` thường cho biết **kiểu đã xóa hoặc kiểu runtime** tương ứng.
- Các phương thức trả về `java.lang.reflect.Type` có tên chứa `Generic` thường cho biết **kiểu khai báo generic**, nếu metadata cần thiết hiện diện và hợp lệ.

Tạo tệp **`GenericSignatureReflectionDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;

public class GenericSignatureReflectionDemo {

    static class Box<T extends Number & Comparable<T>> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void accept(List<? extends T> input) {
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Box.class;

        TypeVariable<?> variable = type.getTypeParameters()[0];
        System.out.println("variable: " + variable.getName());

        for (Type bound : variable.getBounds()) {
            System.out.println("bound: " + bound.getTypeName());
        }

        Field field = type.getDeclaredField("value");
        System.out.println("field raw: " + field.getType().getTypeName());
        System.out.println("field generic: " + field.getGenericType().getTypeName());

        Method get = type.getDeclaredMethod("get");
        System.out.println("return raw: " + get.getReturnType().getTypeName());
        System.out.println("return generic: "
                + get.getGenericReturnType().getTypeName());

        Method accept = type.getDeclaredMethod("accept", List.class);
        Type parameter = accept.getGenericParameterTypes()[0];

        ParameterizedType listType = (ParameterizedType) parameter;
        WildcardType wildcard = (WildcardType)
                listType.getActualTypeArguments()[0];

        System.out.println("parameter raw: "
                + accept.getParameterTypes()[0].getTypeName());
        System.out.println("parameter generic raw: "
                + listType.getRawType().getTypeName());
        System.out.println("wildcard upper: "
                + wildcard.getUpperBounds()[0].getTypeName());
    }
}
```

Chạy:

```bash
javac GenericSignatureReflectionDemo.java
java GenericSignatureReflectionDemo
```

Stdout:

```text
variable: T
bound: java.lang.Number
bound: java.lang.Comparable<T>
field raw: java.lang.Number
field generic: T
return raw: java.lang.Number
return generic: T
parameter raw: java.util.List
parameter generic raw: java.util.List
wildcard upper: T
```

Giải thích kết quả:

1. `Class.getTypeParameters()` đọc tham số kiểu khai báo bởi class `Box`; tên biến là `T`.
2. `TypeVariable.getBounds()` trả về các giới hạn đã khai báo: `Number`, `Comparable<T>`. Erasure không buộc reflection chỉ thấy `Number`.
3. `Field.getType()` cho kiểu trường đã xóa là `Number`, còn `Field.getGenericType()` biết trường được khai báo bằng biến `T`.
4. `Method.getReturnType()` cho kiểu trả về erasure `Number`, còn `getGenericReturnType()` cho `T`.
5. `getDeclaredMethod("accept", List.class)` tìm method qua tham số đã xóa `List` vì overload lookup dùng `Class<?>` của các tham số runtime.
6. `getGenericParameterTypes()[0]` là `ParameterizedType` đại diện `List<? extends T>`; đối số bên trong là `WildcardType` có upper bound là `T`.

Chương trình ép kiểu sang `ParameterizedType` và `WildcardType` vì **chúng ta biết trước chính xác khai báo của method**. Khi làm công cụ reflection tổng quát, luôn kiểm tra bằng `instanceof` trước khi cast: một đối tượng `Type` có thể thuộc nhiều dạng khác nhau.

## 7. Các dạng `Type` mà reflection có thể trả về

`java.lang.reflect.Type` là giao diện chung cho nhiều hình thức mô tả kiểu. Đây là bản đồ thực dụng:

| Dạng phản ánh | Ví dụ nguồn | Interface/class reflection |
|---|---|---|
| Kiểu class không tham số hóa | `String` | `Class<?>` |
| Kiểu tham số hóa | `List<String>` | `ParameterizedType` |
| Biến kiểu | `T` trong `class Box<T>` | `TypeVariable<?>` |
| Wildcard | `? extends Number` | `WildcardType` |
| Mảng có thành phần kiểu generic | `T[]`, `List<String>[]` | Có thể là `GenericArrayType` |
| Mảng với thành phần class cụ thể | `String[]` | `Class<?>` |

Các điểm cần nhớ:

- `ParameterizedType.getRawType()` cho biết kiểu gốc của tham số hóa, ví dụ `List.class`.
- `ParameterizedType.getActualTypeArguments()` cho các đối số khai báo, ví dụ `String.class` với `List<String>`.
- `TypeVariable.getBounds()` và `WildcardType.getUpperBounds()/getLowerBounds()` đọc các ràng buộc được biểu diễn trong generic signature.
- `GenericArrayType.getGenericComponentType()` phân tích thành phần mảng khi component là kiểu generic thích hợp.
- `Type.getTypeName()` phù hợp để trình bày tên kiểu trong nhiều công cụ học tập, nhưng đừng phân tích chữ ký bằng cách cắt chuỗi tên một cách tùy tiện nếu đã có đối tượng `Type` có cấu trúc.

Một API cần nhận nhiều hình thức `Type` nên phân nhánh theo interface thay vì cast tất cả về `ParameterizedType`.

Ngoài các API đã minh họa, còn có `Class.getGenericSuperclass()`, `Class.getGenericInterfaces()`, `Method.getGenericExceptionTypes()`, `Constructor.getGenericParameterTypes()` và những API tương tự. Chúng trả về *thông tin được khai báo* chứ không khám phá được một cách thần kỳ các đối số kiểu chỉ tồn tại trong suy luận compiler tại vị trí gọi.

## 8. Vì sao `getClass()` không khôi phục được `List<String>` của một đối tượng?

Một hiểu lầm phổ biến là:

> “Nếu class file còn Signature, gọi `list.getClass()` chắc chắn sẽ biết danh sách này là `List<String>`.”

Điều đó **sai** đối với đối tượng generic thông thường. Thử chương trình độc lập trong tệp **`GenericCaptureDemo.java`**:

```java
public class GenericCaptureDemo {

    static class Container<X> {
    }

    static class IntContainer extends Container<Integer> {
    }

    public static void main(String[] args) {
        Container<String> words = new Container<>();
        Container<Integer> numbers = new Container<>();

        System.out.println(words.getClass().equals(numbers.getClass()));
        System.out.println(Container.class.getTypeParameters()[0].getName());

        System.out.println(IntContainer.class.getSuperclass().getTypeName());
        System.out.println(
                IntContainer.class.getGenericSuperclass().getTypeName());

        Container<String> anonymous = new Container<String>() {};
        System.out.println(
                anonymous.getClass().getGenericSuperclass().getTypeName());
    }
}
```

Biên dịch và chạy:

```bash
javac GenericCaptureDemo.java
java GenericCaptureDemo
```

Stdout:

```text
true
X
GenericCaptureDemo$Container
GenericCaptureDemo$Container<java.lang.Integer>
GenericCaptureDemo$Container<java.lang.String>
```

Phân tích:

- `new Container<String>()` và `new Container<Integer>()` thông thường cùng là instance của **một class runtime** `Container`.
- `Container.class.getTypeParameters()` chỉ nói class khai báo type variable `X`; nó không cho biết mỗi instance đã được tạo với đối số kiểu gì.
- `IntContainer extends Container<Integer>` khai báo **một quan hệ kế thừa cụ thể**. Class file của `IntContainer` có thể lưu supertype generic `Container<Integer>`; `getGenericSuperclass()` đọc được quan hệ này.
- `new Container<String>() {}` tạo **một anonymous subclass riêng** tại compile time. Superclass generic được ghi trong class file của subclass đó, vì vậy reflection có thể thấy `String`.

Hai dòng cuối không có nghĩa generic được *reify* cho mọi instance; đó là thông tin của **class con đã có khai báo hoặc cấu trúc kế thừa mang đối số kiểu cụ thể**.

### Trường hợp subclass generic vẫn chưa biết kiểu cụ thể

Ví dụ:

```java
class Child<U> extends java.util.ArrayList<U> {
}
```

`Child.class.getGenericSuperclass()` có thể cho biết quan hệ `ArrayList<U>`, nhưng không thể tự biết một instance `Child<String>` đã được tạo với `U = String`. Ở đây `U` vẫn là type variable của `Child`.

Muốn nắm một kiểu cụ thể tại runtime, API thường yêu cầu người gọi truyền một **type token** (`Class<T>` cho class không tham số hóa, hoặc `Type`/mẫu type reference phù hợp để mô tả kiểu tham số hóa), hoặc dùng một lớp con có metadata được khai báo cụ thể như trên. Type token không phải bằng chứng dữ liệu bên trong một collection đã thực sự thỏa mọi điều kiện generic.

## 9. Phương thức generic cũng có Signature độc lập

`Signature` không chỉ dùng cho class hoặc field. Một method tự khai báo tham số kiểu cũng có thể được phản ánh đầy đủ.

Tạo tệp **`GenericMethodSignatureDemo.java`**:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;

public class GenericMethodSignatureDemo {

    static <T extends Runnable & AutoCloseable> T pass(T input) {
        return input;
    }

    public static void main(String[] args) throws Exception {
        Method method = GenericMethodSignatureDemo.class
                .getDeclaredMethod("pass", Runnable.class);

        System.out.println("parameter raw: "
                + method.getParameterTypes()[0].getTypeName());
        System.out.println("parameter generic: "
                + method.getGenericParameterTypes()[0].getTypeName());
        System.out.println("return generic: "
                + method.getGenericReturnType().getTypeName());

        TypeVariable<Method> variable = method.getTypeParameters()[0];
        for (Type bound : variable.getBounds()) {
            System.out.println("bound: " + bound.getTypeName());
        }
    }
}
```

Chạy:

```bash
javac GenericMethodSignatureDemo.java
java GenericMethodSignatureDemo
```

Stdout:

```text
parameter raw: java.lang.Runnable
parameter generic: T
return generic: T
bound: java.lang.Runnable
bound: java.lang.AutoCloseable
```

`T` có giới hạn đầu là `Runnable`, nên method descriptor dùng `Runnable` ở vị trí tham số và kết quả. Nhưng method-level generic `Signature` giữ lại tên `T` cùng hai giới hạn, cho phép reflection phân biệt chúng.

Đây cũng là lý do cần nhìn đúng **nơi khai báo**: type variable của method không nhất thiết là type variable của class chứa method. `Method.getTypeParameters()` đọc tham số kiểu **của method**, còn `Class.getTypeParameters()` đọc tham số kiểu **của class**.

Với generic constructor, phương thức reflection tương ứng là `Constructor.getTypeParameters()` và `Constructor.getGenericParameterTypes()`. Constructor không có kiểu trả về như method thông thường.

## 10. Signature và descriptor tác động khác nhau đến runtime

Hãy xét:

```java
import java.util.List;

class Report {
    List<String> labels;
}
```

Class `Report` có field `labels`, nhưng đối tượng `List` ở runtime không tự kiểm tra từng giá trị chèn vào để bảo đảm chỉ chứa `String`. Nếu một nơi dùng raw type hoặc unchecked cast sai, lỗi có thể xuất hiện sau đó khi đọc phần tử dưới dạng `String`.

Generic signature của field có thể giúp một framework biết **field này được khai báo là `List<String>`**. Chẳng hạn, thư viện ánh xạ JSON có thể dùng thông tin đó để chọn cách chuyển đổi phần tử. Nhưng metadata không tự xác minh rằng dữ liệu thực tế đã an toàn.

### Điều JVM dùng khi liên kết và thực thi

- **Field/method descriptor** biểu diễn kiểu đã xóa mà bytecode sử dụng.
- **Lệnh runtime** như `checkcast` và kiểm tra kiểu mảng thực thi các quy tắc runtime cần thiết.
- **Synthetic bridge methods** có thể được compiler tạo khi override generic cần tương thích với chữ ký đã xóa.
- **Signature** hỗ trợ công cụ và reflection hiểu khai báo generic; nó không tạo thêm overload ở runtime theo từng đối số kiểu.

Ví dụ một interface `Processor<T>` khai báo `T process(T input)`, còn class triển khai dùng `String` có thể khiến compiler sinh bridge method để lời gọi qua `Processor` tiếp tục dispatch đúng sau xóa kiểu. Các công cụ reflection có thể thấy bridge method; method đó có thể được đánh dấu `isBridge()` và `isSynthetic()`.

Bridge method là **mã thực thi** do compiler sinh để giữ hành vi override, còn Signature là **metadata khai báo**. Chúng liên quan tới cùng vấn đề xóa kiểu nhưng không phải một thứ.

### Chữ ký generic không thay thế binary descriptor

Nếu một thư viện công khai đổi giới hạn đầu của type parameter, kiểu đã xóa ở field/method descriptor có thể thay đổi. Thay đổi đó có thể tác động tới tương thích nhị phân, dù kiểu Java nhìn tương tự ở mức ý tưởng.

Ngược lại, hai khai báo có cùng descriptor vẫn có thể mang generic signature khác nhau. JVM không dùng generic signature để phân biệt hai overload xung đột erasure; compiler Java có quy tắc ngăn một số khai báo gây name clash.

## 11. Signature có phải lúc nào cũng còn không?

Không thể giả định một class file bất kỳ luôn mang đầy đủ generic metadata.

**Trường hợp biên dịch Java hiện đại thông thường:** `javac` ghi Signature khi cần biểu diễn generic ở class/field/method. Đây là trường hợp của các ví dụ đang học.

**Trường hợp nguồn hoặc bytecode không có khai báo generic:** Có thể không có Signature tương ứng; reflection khi ấy cho thông tin kiểu không generic hoặc thông tin đã xóa.

**Trường hợp công cụ biến đổi bytecode:** Một số pipeline obfuscation, bytecode weaving, tối ưu hóa hoặc xây dựng class file thủ công có thể loại bỏ hoặc thay đổi Signature. Vì thuộc tính là metadata cho generic, nên công cụ phụ thuộc reflection cần cấu hình để giữ thuộc tính cần thiết.

**Trường hợp metadata không hợp lệ hoặc thiếu kiểu được tham chiếu:** API reflection phân tích generic có thể báo lỗi như `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` tùy tình huống. Không nên xem Signature như dữ liệu đáng tin tuyệt đối khi nạp class file từ nguồn không kiểm soát.

### `javac -g:none` và `LocalVariableTypeTable` là chuyện khác

`javac -g:none` vô hiệu hóa việc sinh các loại thông tin **debug** được điều khiển bởi tùy chọn `-g`. Nó không có nghĩa phải xóa Signature generic của class, field và method. Chữ ký generic không chỉ là một bảng debug.

Ngược lại, `LocalVariableTypeTable` là thuộc tính **tùy chọn**, thường gắn với thông tin debug của các biến cục bộ có kiểu generic, và có thể không hiện diện. Reflection chuẩn qua `Field` và `Method` không lấy generic của mọi biến cục bộ trong thân method.

Thử so sánh:

```bash
javac -g:none SignatureClassFileDemo.java
javap -p -v SignatureClassFileDemo
```

Bạn vẫn có thể tìm thấy `Signature` cho các khai báo generic của ví dụ, trong khi thông tin biến cục bộ/debug đã được lược bớt. Đây là một phép thử tốt để tránh nhầm giữa **generic declaration metadata** và **debug metadata**.

### Bảng phân biệt metadata

| Thuộc tính/cấu trúc | Chứa gì? | Có thay thế Signature không? |
|---|---|---|
| Descriptor | Kiểu JVM đã xóa cho field/method | Không; descriptor là phần cần thiết cho mô tả bytecode |
| `Signature` | Khai báo generic của class/field/method khi áp dụng | Đây là nơi giữ generic signature |
| `LocalVariableTable` | Thông tin tên, scope và descriptor của biến cục bộ trong debug | Không |
| `LocalVariableTypeTable` | Thông tin generic cho biến cục bộ nếu compiler/công cụ ghi | Không; phục vụ local variables |
| `RuntimeVisibleAnnotations` | Annotation có runtime retention ở những vị trí thích hợp | Không |
| `RuntimeVisibleTypeAnnotations` | Type-use annotations có runtime retention ở những vị trí thích hợp | Không |
| `Code` | Bytecode thân method cùng cấu trúc liên quan | Không |

Một số class file còn lưu tham số method, exceptions hoặc thuộc tính bổ sung; mục đích từng phần cần được xem độc lập.

## 12. Type-use annotation và Signature là hai cơ chế

Java cho phép annotation xuất hiện tại vị trí kiểu khi annotation đó có target phù hợp, ví dụ `List<@Nonnull String>` trong một hệ sinh thái có định nghĩa annotation type-use thích hợp.

Generic Signature mô tả cấu trúc generic như `List<String>`. Thông tin về annotation gắn lên một vị trí kiểu được lưu theo cơ chế **type annotations**, chứ không đơn giản mã hóa thành tên annotation trong chuỗi Signature.

Do đó:

- `Field.getGenericType()` trả về cấu trúc kiểu generic.
- `Field.getAnnotatedType()` dùng để xem các annotation trên kiểu tại vị trí khai báo field khi annotation và metadata phù hợp.
- Có hay không annotation runtime phụ thuộc `@Retention`, `@Target` và cách class file được tạo.

Khi viết framework cần cả generic structure lẫn type-use annotations, có thể phải dùng **cả hai** nhóm API. Không nên suy luận rằng chỉ cần phân tích Signature là đã thấy mọi annotation hoặc toàn bộ ràng buộc nghiệp vụ.

## 13. Phân biệt metadata khai báo với kiểu thực của dữ liệu

Xét ba tình huống:

**Tình huống A — field có generic cố định**

```java
class Registry {
    java.util.List<String> names;
}
```

Reflection trên `Registry.names` có thể thấy `List<String>`, vì đối số `String` được viết **ngay trong khai báo field**.

**Tình huống B — local variable do suy luận kiểu**

```java
var names = new java.util.ArrayList<String>();
```

Đây là một câu lệnh Java nằm trong method hợp lệ, không phải chương trình chạy độc lập. `var` để compiler suy ra kiểu tĩnh của biến cục bộ; việc một local variable được suy luận là `ArrayList<String>` không khiến mọi instance của `ArrayList` ở runtime mang đối số `String`, cũng không có nghĩa reflection chuẩn có API đọc trực tiếp mọi thông tin local-variable generic từ object.

**Tình huống C — subclass khai báo kiểu cha cụ thể**

```java
class StringQueue extends java.util.ArrayDeque<String> {
}
```

Class file của `StringQueue` có thể ghi quan hệ generic với `ArrayDeque<String>`. Reflection trên **class `StringQueue`** có thể truy xuất supertype parameterized. Điều đó khác với tạo `new ArrayDeque<String>()` trực tiếp: một instance `ArrayDeque` thường không giữ `String` như thuộc tính runtime của chính đối tượng.

Những khác biệt này giải thích vì sao các thư viện JSON, ORM, dependency injection hay phân tích schema có thể đọc một số thông tin generic rất hữu ích, nhưng đôi khi vẫn yêu cầu type token hoặc cấu hình rõ hơn. Metadata phản ánh **chữ ký khai báo đang có**, không phải lịch sử suy luận kiểu của mọi lời gọi.

## 14. Ứng dụng thực tế và lưu ý khi thiết kế API

### Viết thư viện dựa trên reflection

Khi đọc kiểu field, tham số method hoặc kiểu cha generic, ưu tiên API có chữ `Generic` và xử lý đúng các dạng `Type`. Nếu chỉ dùng `getType()`/`getReturnType()`, bạn thường nhìn thấy erasure và có thể đánh mất cấu trúc như `List<Invoice>`.

Ví dụ đoạn mã kiểm tra kiểu field (cần đặt trong class và có `Field field` phù hợp):

```java
Type type = field.getGenericType();

if (type instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();
    // Kiểm tra raw và từng argument theo hợp đồng của framework.
}
```

Đây chỉ là đoạn minh họa API reflection, không phải chương trình độc lập. Bên ngoài ví dụ, cần giải quyết `TypeVariable`, `WildcardType`, generic array, nested/owner type và các tình huống metadata không đầy đủ trước khi coi thông tin là một class cụ thể.

### Thiết kế thư viện phát hành cho người khác

- Nếu thay đổi thứ tự giới hạn generic, kiểm tra cả **descriptor sau erasure** và **Signature**.
- Nếu một framework cần generic metadata, cấu hình pipeline build/shrink/obfuscation để giữ các thuộc tính cần thiết.
- Dùng `javap -p -s` và `javap -p -v` để kiểm chứng phần class file thực tế thay vì chỉ suy luận từ Java source.
- Với API nhận `Class<T>`, nhớ rằng `Class<List<String>>` không thể được cung cấp trực tiếp bằng biểu thức class literal `List<String>.class`. `List.class` chỉ là class literal của raw `List`; cấu trúc type parameterized cần biểu diễn bằng `Type` hoặc một cơ chế type reference phù hợp.
- Không sử dụng `Signature` để chứng nhận dữ liệu collection đã sạch hoặc hoàn toàn an toàn. Kiểm tra dữ liệu và bảo đảm kiểu runtime vẫn là trách nhiệm của ứng dụng.

### Quan hệ với công cụ bytecode

Công cụ đọc/sinh bytecode có thể nhìn thấy raw descriptor đồng thời với generic Signature. Khi tạo class file mới, cần đảm bảo chúng **nhất quán theo ngữ nghĩa**: một field khai báo `List<String>` cần descriptor tương ứng `List`, còn Signature mô tả đối số `String`. Nếu metadata không khớp với bytecode, các công cụ downstream và reflection có thể hiểu sai hoặc gặp lỗi.

Đừng viết một bộ parser Signature thủ công chỉ bằng `split("<")` hoặc thay thế chuỗi: ngữ pháp hỗ trợ nested parameterized types, owner types, bounds, arrays và wildcard. Nếu thực sự thao tác bytecode, sử dụng công cụ có parser Signature phù hợp với classfile version đang làm việc.

## 15. Những lỗi hiểu sai thường gặp

**Lỗi 1: “Type erasure xóa sạch toàn bộ thông tin generic.”** Không đúng. Generic declarations có thể còn trong `Signature` dù descriptor đã dùng kiểu bị xóa.

**Lỗi 2: “JVM dùng `Signature` để biết chính xác loại phần tử của mọi `ArrayList`.”** Không đúng. Phần tử generic của mỗi instance thông thường không được reify bằng Signature; kiểm tra kiểu tại runtime vẫn theo quy tắc kiểu đã xóa.

**Lỗi 3: “`getType()` và `getGenericType()` luôn giống nhau.”** Không đúng. Với field `T value` có bound `Number`, `getType()` có thể là `Number.class`, còn `getGenericType()` là `TypeVariable` mang tên `T`.

**Lỗi 4: “`Signature` chỉ lưu đối số kiểu của field.”** Không đúng. Nó còn dùng cho class-level và method-level generic declarations khi cần.

**Lỗi 5: “Nếu reflection thấy `<T>` thì biết mỗi object có `T` là gì.”** Không đúng. `Class.getTypeParameters()` nêu các biến kiểu được khai báo bởi class, không biết đối số của mọi lần khởi tạo.

**Lỗi 6: “Đổi bound không ảnh hưởng gì vì generic đã bị xóa.”** Không đúng. Bound đứng đầu quyết định erasure của type variable; sự thay đổi có thể ảnh hưởng descriptor và tương thích nhị phân.

**Lỗi 7: “`-g:none` sẽ xóa generic Signature.”** Không đúng theo cách hoạt động bình thường của `javac`: Signature khai báo là metadata generic, tách biệt các bảng thông tin debug.

**Lỗi 8: “`List<?>` chỉ là raw `List`.”** Không đúng. Hai kiểu có thể dùng cùng raw descriptor, nhưng generic signature và kiểm tra kiểu ở mã nguồn khác nhau.

**Lỗi 9: “Một đối tượng `Type` đọc được luôn là `ParameterizedType`.”** Không đúng. Cần phân biệt `Class`, `TypeVariable`, `WildcardType`, `GenericArrayType` và `ParameterizedType`.

**Lỗi 10: “Có thể tin mọi generic signature đọc từ class file bất kỳ.”** Không nên. Class file do công cụ biến đổi, thiếu dependency hoặc chứa chữ ký lỗi có thể khiến reflection/công cụ thất bại; ứng dụng xử lý dữ liệu không tin cậy cần bảo vệ luồng phân tích.

## 16. Tự kiểm tra kiến thức

1. Với `List<String> values;`, field descriptor có còn `<String>` không? **Đáp án:** không, descriptor dùng `Ljava/util/List;`; generic Signature có thể giữ đối số `String`.
2. Với `<T extends Number & Comparable<T>>`, erasure của `T` là gì? **Đáp án:** `Number`, vì `Number` là giới hạn đầu tiên. `Comparable<T>` vẫn có thể xuất hiện trong `Signature` khai báo.
3. Vì sao `Container.class.getTypeParameters()` không suy ra một instance `Container<Integer>` đang giữ `Integer`? **Đáp án:** API này phản ánh biến kiểu được **khai báo** trên class, không phản ánh đối số của mọi instance.
4. `Class.getGenericSuperclass()` hữu ích khi nào? **Đáp án:** khi class có quan hệ superclass được khai báo bằng kiểu parameterized, ví dụ `IntContainer extends Container<Integer>`.
5. `Method.getReturnType()` và `Method.getGenericReturnType()` khác gì? **Đáp án:** cái đầu trả `Class<?>` thể hiện kiểu đã xóa, cái sau trả `Type` diễn đạt kiểu generic trong khai báo nếu có.
6. `LocalVariableTypeTable` có phải thuộc tính `Signature` của field không? **Đáp án:** không; nó là thuộc tính riêng cho thông tin generic của biến cục bộ, thường phụ thuộc debug metadata.
7. Có thể dùng `new ArrayList<String>().getClass()` để biết `String` không? **Đáp án:** không theo cách chung; class runtime của `ArrayList<String>` và `ArrayList<Integer>` là cùng `ArrayList.class`.
8. `getGenericType()` cho phép bỏ qua việc kiểm tra dữ liệu JSON đưa vào `List<String>` không? **Đáp án:** không; metadata mô tả khai báo, không kiểm tra chất lượng hoặc kiểu thực của từng giá trị input.

### Bài thực hành nhỏ

Tạo class có ba field:

```java
class WildcardFields {
    java.util.List<?> unknown;
    java.util.List<? extends Number> upper;
    java.util.List<? super Integer> lower;
}
```

Biên dịch và dùng `javap -p -s WildcardFields`, sau đó `javap -p -v WildcardFields`. Hãy dự đoán trước:

- Cả ba descriptor đều là `Ljava/util/List;`.
- Signature thứ nhất có ký hiệu `*` cho wildcard.
- Signature thứ hai có `+` trước kiểu `Number`.
- Signature thứ ba có `-` trước kiểu `Integer`.

Mục tiêu bài tập là nhìn thấy **cùng một raw descriptor** nhưng có **ba generic signatures khác nhau**. Nếu tiếp tục đọc bằng reflection, hãy phân tích các đối số của `ParameterizedType` dưới dạng `WildcardType` thay vì cố cast trực tiếp sang `Class<?>`.

## 17. Tổng kết và tài liệu tra cứu

**Generic Signature là dấu vết có cấu trúc của khai báo generic được lưu trong class file.** JVM vẫn dùng descriptor đã xóa để biểu diễn field/method, trong khi các công cụ và reflection có thể đọc metadata `Signature` để biết type parameters, bounds, parameterized types và wildcard khi chúng được ghi.

Cần ghi nhớ cùng lúc hai điều: **erasure vẫn có hiệu lực đối với mô hình thực thi**, và **một phần khai báo generic vẫn có thể truy xuất ở runtime qua class metadata**. Khả năng truy xuất này không làm generic trở thành reified cho mọi object và không thay thế việc xác minh dữ liệu.

Nguồn tham khảo chuẩn:

- [JVM Specification, §4.7.9 — The `Signature` Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.9): cấu trúc, vị trí và điều kiện của thuộc tính Signature.
- [JVM Specification, §4.7.9.1 — Signatures](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.9.1): ngữ pháp class, method và field type signatures.
- [Java Language Specification, §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): định nghĩa kiểu bị xóa.
- [Java SE 17 — `java.lang.reflect.Type`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html): hệ phân cấp API biểu diễn kiểu generic.
- [Java SE 17 — `java.lang.reflect.Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): `getType()` và `getGenericType()`.
- [Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): tham số kiểu, kiểu cha generic và generic interfaces.