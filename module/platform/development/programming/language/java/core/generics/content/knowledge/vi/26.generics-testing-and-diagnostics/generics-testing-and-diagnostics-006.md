# Đối chiếu chữ ký generic, chữ ký đã xóa và bridge trong Java class file

## 1. Mục tiêu: hiểu cùng một phương thức ở ba lớp biểu diễn

Khi đọc Java Generics, bạn thường thấy các chữ ký giàu thông tin kiểu ở **source code**:

```java
class Holder<T> {
    T get() { return null; }
    void set(T value) {}
}
```

Nhưng sau `javac`, JVM làm việc với **method descriptors** mà type variables đã bị *erasure*. Trong class file có thể còn một thuộc tính `Signature` lưu cách khai báo generic cho các công cụ như Reflection. Khi có overriding sau khi thay type argument hoặc khi có covariant return type, compiler còn có thể tạo thêm **bridge method**.

Bài này hướng dẫn đối chiếu một cách có hệ thống:

1. **Chữ ký generic tại source**: type variables `<T>`, bounds, `List<String>`, overriding và inference.
2. **Chữ ký đã xóa ở JVM descriptor**: những kiểu JVM dùng để định danh field/method và thực hiện linkage.
3. **Generic `Signature` attribute**: metadata mô tả type parameters và generic arguments mà Java Reflection có thể đọc.
4. **Bridge/synthetic methods**: những method compiler sinh để giữ overriding/dispatch đúng sau erasure hoặc khi return type covariant.
5. **Kết quả thực nghiệm**: `javac --release 17`, `javap -p -s -v -c` và Reflection `Method.isBridge()`, `Method.isSynthetic()`, `getGenericReturnType()`.

Sau bài học, bạn có thể nhìn vào một class file và trả lời: vì sao source chỉ có `String get()` mà bytecode xuất hiện cả `Object get()`; vì sao `get()` trên superclass trả `Object` sau erasure nhưng `StringHolder` vẫn override đúng; vì sao Reflection thấy những phương thức không viết trong source; và khi nào xung đột sau erasure là lỗi compile time thay vì được compiler sửa bằng bridge.

## 2. Ba thứ dễ nhầm: Java method signature, JVM descriptor và generic Signature

Chữ “signature” có nhiều cách dùng; phải tách đúng ngữ cảnh.

| Khái niệm | Dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| **Java source method declaration** | Biểu diễn API và quy tắc type checking | `public T get()` |
| **Java method signature theo JLS** | Phục vụ nhận diện phương thức/overloading ở mức ngôn ngữ; tập trung vào tên và parameter types/type parameters | `get()` |
| **JVM method descriptor** | Mã hóa parameter types **và return type** ở JVM | `()Ljava/lang/Object;` |
| **Class-file `Signature` attribute** | Ghi metadata generic khi cần | `()TT;` |
| **Bridge method** | Method compiler phát sinh để giữ quan hệ overriding/dispatch | `Object get()` gọi `String get()` |
| **Cờ method `ACC_BRIDGE`** | Đánh dấu method bridge | `0x0040` |
| **Cờ method `ACC_SYNTHETIC`** | Đánh dấu member compiler sinh/không viết trực tiếp trong source | `0x1000` |

**Điểm quan trọng:** trong Java source, chỉ đổi kiểu trả về thường **không tạo một overload hợp lệ**. Nhưng ở class file, một class có thể chứa bridge `Object get()` và implementation `String get()` cùng tên, cùng danh sách tham số, **khác descriptor ở return type**. Đây là mã compiler tạo theo quy tắc JVM, không phải lời mời để bạn tự khai báo hai method Java chỉ khác return type.

### 2.1. Descriptor dùng cú pháp JVM, không dùng tên generic ở source

Ví dụ:

```java
T get();
void set(T value);
```

nếu `T` không có bound cụ thể, được erase thành `Object`. Descriptors tương ứng:

```text
()Ljava/lang/Object;
(Ljava/lang/Object;)V
```

Cú pháp rút gọn:

- `(` ... `)` là danh sách parameter descriptors.
- `V` là `void` return.
- `I` là `int`; `J` là `long`; `Z` là `boolean`.
- `Lpkg/ClassName;` là kiểu tham chiếu; dùng dấu `/` trong internal name.
- `[` đứng trước descriptor của thành phần mảng.
- Descriptor **không chứa** `<String>`, `? extends` hoặc type variable `T`.

Ví dụ khác:

```java
String get();
void set(String value);
int count();
String[] names();
```

descriptors:

```text
()Ljava/lang/String;
(Ljava/lang/String;)V
()I
()[Ljava/lang/String;
```

Dòng `()[Ljava/lang/String;` nghĩa là method không đối số, trả mảng `String[]`.

### 2.2. `Signature` attribute dùng grammar riêng

Ví dụ:

```text
()TT;
```

Trong generic signature grammar, `TT;` mô tả type variable tên `T`. Chú ý ký tự `T` đầu tiên là marker kiểu biến và `T` thứ hai là tên biến.

Với:

```java
List<String> tags();
```

class file có thể có:

```text
descriptor: ()Ljava/util/List;
Signature: ()Ljava/util/List<Ljava/lang/String;>;
```

JVM cần `List` ở descriptor; `Signature` giữ type argument `String` cho công cụ generic-aware.

Không diễn giải `Signature` là JVM descriptor dùng để dispatch. Chúng có mục đích khác nhau.

### 2.3. JVM erasure và Reflection không mâu thuẫn

Một câu thường nghe là “Java Generics bị xóa khi chạy”. Câu đúng hơn:

- **Type arguments của object instances không được reify thành các runtime classes riêng** như `ArrayList<String>` và `ArrayList<Integer>`.
- **Method descriptors** dùng kiểu đã erase.
- Compiler có thể giữ **generic declaration metadata** trong `Signature` attribute, nên Reflection trả được `TypeVariable`, `ParameterizedType`, v.v.

Không thể lấy `list.getClass()` rồi mặc định biết chính xác generic argument của biến đã tạo list. Nhưng có thể đọc generic declaration trên class/field/method có metadata tương ứng.

## 3. Type erasure chuyển kiểu như thế nào?

Giả sử:

```java
class Holder<T> {
    private T value;

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
```

`T` không có bound viết tường minh, nên upper bound mặc định là `Object`. Erasure của `T` là `Object`.

| Khai báo source | Kiểu sau erasure |
| --- | --- |
| Field `T value` | Field `Object value` |
| Return `T get()` | Return `Object get()` |
| Parameter `void set(T)` | Parameter `void set(Object)` |
| `List<String>` | `List` |
| `Map<String,Integer>` | `Map` |
| `T[]` khi T không bound | `Object[]` |
| `T extends Number` | `Number` |

### 3.1. Bound đầu tiên ảnh hưởng erasure

Với một generic method:

```java
public <N extends Number> N echo(N number) {
    return number;
}
```

Erasure của `N` là `Number`, **không phải Object**. Descriptor:

```text
(Ljava/lang/Number;)Ljava/lang/Number;
```

Generic `Signature` tương ứng:

```text
<N:Ljava/lang/Number;>(TN;)TN;
```

Nó cho biết có method type variable `N` với bound Number, tham số N và return N. Nếu chỉ xem descriptor, bạn mất quan hệ “đầu vào và đầu ra dùng cùng N” nhưng vẫn biết cả hai có raw type Number.

Với multiple bounds, erasure phụ thuộc bound đầu theo quy tắc Java. Vì thế cần kiểm tra declaration thật, không suy đoán mọi type variable đều erase thành Object.

### 3.2. Kiểu tham số hóa bị erase về raw type

```java
public List<String> tags() {
    return List.of("java", "generics");
}
```

Descriptor:

```text
()Ljava/util/List;
```

`Signature`:

```text
()Ljava/util/List<Ljava/lang/String;>;
```

Method nào chỉ nhìn descriptor sẽ không biết element type String. Công cụ đọc `Signature` mới thấy generic argument từ declaration.

### 3.3. Type erasure không làm `List<Integer>` biến thành `List<String>`

Ở compile time:

```java
List<String> names = new ArrayList<>();

// Không biên dịch:
// List<Integer> numbers = names;
```

Invariance/type checking vẫn có hiệu lực ở source. Erasure xảy ra như một phần biên dịch/JVM representation; không có nghĩa những phép gán sai kiểu trở nên hợp lệ.

Ngược lại, raw types và unchecked conversions có thể tạo dữ liệu sai, dẫn đến lỗi muộn như `ClassCastException`. Bridge method không chữa heap pollution do raw types gây ra.

## 4. Vì sao compiler cần bridge khi override generic superclass?

Một ví dụ:

```java
class Holder<T> {
    public T get() {
        return null;
    }
}

class StringHolder extends Holder<String> {
    @Override
    public String get() {
        return "Java";
    }
}
```

Trong Java source, `StringHolder.get()` **override** `Holder<String>.get()` vì T được thay bằng String trong quan hệ kế thừa.

Nhưng ở JVM:

- Erased `Holder.get()` có descriptor `()Ljava/lang/Object;`.
- `StringHolder.get()` do bạn viết có descriptor `()Ljava/lang/String;`.

Nếu JVM chỉ có `String get()` và lời gọi từ biến `Holder<String>` tham chiếu tới descriptor `Object get()`, cơ chế dispatch sẽ thiếu implementation tương ứng ở subclass theo erased descriptor.

Vì vậy compiler có thể sinh bridge:

```java
// Pseudocode giải thích bytecode, KHÔNG phải source tự viết:
public Object get() {
    return this.get(); // Gọi String get() của class con.
}
```

Ở JVM, hai `get` phân biệt bằng descriptor return type. Method bridge có kiểu trả về Object đúng với erased superclass API và ủy quyền cho implementation String.

### 4.1. Với parameter `set(T)`, bridge cần cast

Source:

```java
class Holder<T> {
    public void set(T value) {
    }
}

class StringHolder extends Holder<String> {
    @Override
    public void set(String value) {
    }
}
```

Erased superclass method nhận Object, còn StringHolder source method nhận String. Compiler có thể tạo thêm:

```java
// Pseudocode bridge, không khai báo thủ công:
public void set(Object value) {
    set((String) value);
}
```

Method này nhận Object tại erased JVM boundary, thực hiện `checkcast String`, rồi gọi typed implementation `set(String)`.

**Hệ quả:** đi qua một raw/reflection boundary và truyền Integer vào bridge `set(Object)` có thể ném `ClassCastException`. Bridge giữ dispatch và type safety trong những ràng buộc mà JVM có thể kiểm tra, không khiến Integer biến thành String.

### 4.2. Bridge là implementation detail của class file

Người viết source **không** khai báo bridge bằng tay và không nên gọi nó qua một API Java bình thường như một overload độc lập. Compiler quyết định nơi cần method để bảo toàn quan hệ override.

Không phải **mọi** method generic đều có bridge. Bridge thường chỉ xuất hiện khi có nhu cầu tương thích descriptor từ quan hệ kế thừa/interface hoặc covariant return.

## 5. Ví dụ đầy đủ: superclass, subclass, interface và bridge

Tạo file **`GenericBytecodeDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class GenericBytecodeDemo {
    static class Holder<T> {
        private T value;

        Holder(T value) {
            this.value = value;
        }

        public T get() {
            return value;
        }

        public void set(T value) {
            this.value = value;
        }

        public <N extends Number> N echo(N number) {
            return number;
        }

        public List<String> tags() {
            return List.of("java", "generics");
        }
    }

    static final class StringHolder extends Holder<String> {
        StringHolder(String value) {
            super(value);
        }

        @Override
        public String get() {
            return super.get().toUpperCase();
        }

        @Override
        public void set(String value) {
            super.set(value.trim());
        }
    }

    interface Mapper<T> {
        T apply(T value);
    }

    static final class Uppercase implements Mapper<String> {
        @Override
        public String apply(String value) {
            return value.toUpperCase();
        }
    }

    public static void main(String[] args) throws Exception {
        Holder<String> holder = new StringHolder(" java ");
        holder.set(" bridge ");
        System.out.println("dispatch=" + holder.get());
        System.out.println("generic-method=" + holder.echo(7));

        System.out.println("generic-field="
                + Holder.class.getDeclaredField("value")
                      .getGenericType().getTypeName());

        System.out.println("generic-super="
                + StringHolder.class.getGenericSuperclass()
                      .getTypeName());

        Method[] methods = StringHolder.class.getDeclaredMethods();
        Arrays.sort(methods, Comparator.comparing(Method::toString));

        for (Method method : methods) {
            System.out.println("method=" + method.getName()
                    + ",parameter="
                    + Arrays.toString(method.getParameterTypes())
                    + ",returns="
                    + method.getReturnType().getSimpleName()
                    + ",bridge=" + method.isBridge()
                    + ",synthetic=" + method.isSynthetic());
        }

        Method getTyped =
                StringHolder.class.getDeclaredMethod("get");
        Method setBridge =
                StringHolder.class.getDeclaredMethod(
                        "set", Object.class);

        System.out.println("get-by-object-method="
                + (getTyped.getReturnType() == String.class));
        System.out.println("set-object-bridge="
                + setBridge.isBridge());

        try {
            setBridge.invoke(holder, 42);
        } catch (InvocationTargetException ex) {
            System.out.println("invalid-bridge-arg="
                    + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("mapper="
                + new Uppercase().apply("hi"));
        System.out.println("mapper-bridge="
                + Uppercase.class
                  .getDeclaredMethod("apply", Object.class)
                  .isBridge());
    }
}
```

Biên dịch và chạy với Java 17:

```bash
javac --release 17 -Xlint:all GenericBytecodeDemo.java
java GenericBytecodeDemo
```

Chương trình đã được biên dịch sạch với `-Xlint:all`. Stdout trên JDK kiểm thử:

```text
dispatch=BRIDGE
generic-method=7
generic-field=T
generic-super=GenericBytecodeDemo$Holder<java.lang.String>
method=get,parameter=[],returns=Object,bridge=true,synthetic=true
method=get,parameter=[],returns=String,bridge=false,synthetic=false
method=set,parameter=[class java.lang.Object],returns=void,bridge=true,synthetic=true
method=set,parameter=[class java.lang.String],returns=void,bridge=false,synthetic=false
get-by-object-method=true
set-object-bridge=true
invalid-bridge-arg=ClassCastException
mapper=HI
mapper-bridge=true
```

Kết quả `get-by-object-method=true` phản ánh lựa chọn return type cụ thể hơn của Reflection khi tra `getDeclaredMethod("get")` trong ví dụ; khi phân tích class file nhiều methods cùng tên/parameters mà khác return type, hãy **duyệt `getDeclaredMethods()` và kiểm tra return type/cờ bridge**, đừng tự đồng nhất mọi `get` thành một method.

### 5.1. Vì sao `dispatch=BRIDGE`?

Biến `holder` có kiểu tĩnh `Holder<String>`, nhưng object thật là StringHolder. Lời gọi set/get có typed contract String; sau erasure, JVM call site có thể dùng descriptors của Holder với Object. Bridge methods giúp dispatch tới implementation `StringHolder`, và StringHolder biến chuỗi `" bridge "` thành `"bridge"`, rồi uppercase thành `"BRIDGE"`.

Điều này minh họa **override hoạt động đúng** qua erased JVM descriptors. Không phải runtime biết `Holder<String>` như một specialization class mới.

### 5.2. Vì sao `generic-field=T`?

`Field.getGenericType()` đọc generic metadata của declaration `private T value`. Nó trả một `TypeVariable` tên T. Nếu dùng `Field.getType()` thay vì `getGenericType()`, erased field type là `Object.class`.

### 5.3. Vì sao `generic-super=Holder<String>`?

`StringHolder` được khai báo `extends Holder<String>`, và generic superclass metadata còn trong class file. `getGenericSuperclass()` trả `ParameterizedType` mô tả đúng declaration đó.

Reflection không tự biến generic field `T` trong Holder thành String khi bạn gọi thẳng `Holder.class.getDeclaredField("value").getGenericType()`. Để suy ra T=String trong ngữ cảnh StringHolder, resolver phải xem cả quan hệ `StringHolder extends Holder<String>`.

### 5.4. Vì sao có bốn dòng `method=`?

Trong StringHolder:

- Typed `String get()` là method do bạn viết; `bridge=false`, `synthetic=false`.
- Bridge `Object get()` là method compiler sinh; `bridge=true`, `synthetic=true`.
- Typed `void set(String)` là method do bạn viết.
- Bridge `void set(Object)` là method compiler sinh.

Output được sắp theo `Method.toString()` trong chương trình để kiểm thử dễ đối chiếu; Reflection không hứa `getDeclaredMethods()` có thứ tự ổn định nếu không tự sắp xếp.

### 5.5. Vì sao `invalid-bridge-arg=ClassCastException`?

Reflection gọi `set(Object)` của StringHolder với Integer `42`. Bridge tồn tại và nhận một Object theo erased descriptor, nhưng bên trong nó phải cast Object thành String trước khi gọi `set(String)`. Cast thất bại, Reflection đóng gói exception trong `InvocationTargetException`; chương trình lấy nguyên nhân bằng `getCause()` để in ClassCastException.

Đây là minh chứng cho cơ chế runtime của bridge, **không phải lời khuyên gọi bridge bằng Reflection trong application code**.

### 5.6. Vì sao `mapper-bridge=true`?

`Mapper<T>` khai báo `T apply(T value)`, khi erase có descriptor `(Ljava/lang/Object;)Ljava/lang/Object;`.

`Uppercase implements Mapper<String>` cài đặt `String apply(String value)`, với descriptor `(Ljava/lang/String;)Ljava/lang/String;`.

Compiler sinh `Object apply(Object)` làm bridge để các lời gọi qua `Mapper` interface vẫn dispatch tới implementation String đúng cách. Cơ chế này giống generic superclass, nhưng xuất hiện ở **generic interface implementation**.

## 6. Quan sát class file bằng `javap`

Sau khi biên dịch `GenericBytecodeDemo.java`, chạy từ đúng thư mục chứa các `.class`:

```bash
javap -p -s 'GenericBytecodeDemo$Holder'
javap -p -s 'GenericBytecodeDemo$StringHolder'
javap -p -s 'GenericBytecodeDemo$Uppercase'
```

Trong một số shell Windows, dùng:

```powershell
javap -p -s 'GenericBytecodeDemo$Holder'
javap -p -s 'GenericBytecodeDemo$StringHolder'
javap -p -s 'GenericBytecodeDemo$Uppercase'
```

Dùng dấu nháy quanh tên chứa `$` để tránh shell xử lý sai tên nested class; trong Bash dùng nháy đơn hoặc escape `$`. Nếu chạy từ thư mục khác, thêm `-classpath path/to/classes`.

Các flags:

- `-p` hiển thị cả private members.
- `-s` in descriptors.
- `-v` in verbose class-file details, bao gồm attributes và flags.
- `-c` disassemble Code attribute thành các JVM instructions.

### 6.1. `Holder<T>` dưới `javap -p -s`

Trích đoạn đã được kiểm chứng:

```text
class GenericBytecodeDemo$Holder<T> {
  private T value;
    descriptor: Ljava/lang/Object;

  GenericBytecodeDemo$Holder(T);
    descriptor: (Ljava/lang/Object;)V

  public T get();
    descriptor: ()Ljava/lang/Object;

  public void set(T);
    descriptor: (Ljava/lang/Object;)V

  public <N extends java.lang.Number> N echo(N);
    descriptor: (Ljava/lang/Number;)Ljava/lang/Number;

  public java.util.List<java.lang.String> tags();
    descriptor: ()Ljava/util/List;
}
```

`javap` hiển thị cú pháp generic dễ đọc nhờ metadata, **nhưng các dòng `descriptor:` vẫn là kiểu đã erase**.

Điều cần quan sát:

- Field `T` → descriptor `Object`.
- Constructor nhận `T` → descriptor nhận `Object`.
- `T get()` → descriptor return `Object`.
- `void set(T)` → descriptor nhận `Object`.
- Bounded `N extends Number` → descriptor parameter và return Number.
- `List<String>` → descriptor chỉ là List.

### 6.2. `StringHolder` dưới `javap -p -s`

Trích đoạn:

```text
final class GenericBytecodeDemo$StringHolder
    extends GenericBytecodeDemo$Holder<java.lang.String> {

  GenericBytecodeDemo$StringHolder(java.lang.String);
    descriptor: (Ljava/lang/String;)V

  public java.lang.String get();
    descriptor: ()Ljava/lang/String;

  public void set(java.lang.String);
    descriptor: (Ljava/lang/String;)V

  public void set(java.lang.Object);
    descriptor: (Ljava/lang/Object;)V

  public java.lang.Object get();
    descriptor: ()Ljava/lang/Object;
}
```

Hai dòng `set` và hai dòng `get` **không cùng nguồn source**. `javap` cho thấy methods compiler tạo thêm trong class file. Với `-s` bạn xác nhận descriptors chính xác; với `-v` bạn kiểm tra cờ bridge/synthetic.

### 6.3. `Uppercase` dưới `javap -p -s`

Trích đoạn:

```text
final class GenericBytecodeDemo$Uppercase
    implements GenericBytecodeDemo$Mapper<java.lang.String> {

  public java.lang.String apply(java.lang.String);
    descriptor: (Ljava/lang/String;)Ljava/lang/String;

  public java.lang.Object apply(java.lang.Object);
    descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
}
```

Đây là dạng điển hình khi implements một generic interface bằng một type argument cụ thể. Typed method trả String; bridge giữ erased interface descriptor Object→Object.

### 6.4. `-s` không phải là `Signature` attribute

Dễ bị nhầm vì option `-s` in **descriptors** còn attribute có tên **`Signature`**. Muốn thấy trường riêng `Signature:` trong verbose output:

```bash
javap -p -v 'GenericBytecodeDemo$Holder'
```

Kết quả dài, vì có constant pool, attributes, bytecode và nhiều metadata khác. Hãy tìm những từ khóa:

```text
descriptor:
Signature:
ACC_BRIDGE
ACC_SYNTHETIC
```

Dùng một đoạn trích có context thay vì chỉ tìm một dòng rồi gán nhầm Signature cho method bên cạnh.

## 7. Đọc class file verbose: descriptor khác Signature ở đâu?

Với `Holder<T>`, `javap -p -v` có các mục dạng:

```text
private T value;
  descriptor: Ljava/lang/Object;
  Signature: #...    // TT;
```

Với `get()`:

```text
public T get();
  descriptor: ()Ljava/lang/Object;
  Signature: #...    // ()TT;
```

Với `set(T)`:

```text
public void set(T);
  descriptor: (Ljava/lang/Object;)V
  Signature: #...    // (TT;)V
```

Với method bound:

```text
public <N extends java.lang.Number> N echo(N);
  descriptor: (Ljava/lang/Number;)Ljava/lang/Number;
  Signature: #...    // <N:Ljava/lang/Number;>(TN;)TN;
```

Với `tags()`:

```text
public java.util.List<java.lang.String> tags();
  descriptor: ()Ljava/util/List;
  Signature: #...    // ()Ljava/util/List<Ljava/lang/String;>;
```

Các chỉ số `#...` là constant-pool references và **thay đổi theo biên dịch/JDK**. Phần có ý nghĩa là nội dung `// ...` của generic signature và sự khác biệt với descriptor.

### 7.1. `TT;` nghĩa là gì?

Trong `Signature` grammar:

```text
T<name>;
```

biểu diễn một type variable mang tên đó. Ví dụ tên biến `T` tạo:

```text
TT;
```

và tên biến `N` tạo:

```text
TN;
```

Đừng xem đây là descriptor tham chiếu tới class tên `T` hay `N`; type variables là metadata generic, còn JVM method descriptor đã dùng erasure.

### 7.2. Generic method `<N extends Number>` có hai tầng thông tin

Ở source, compiler bảo đảm method `echo` nhận và trả **cùng một N** cho từng generic invocation:

```java
Integer integer = holder.echo(7);
Double decimal = holder.echo(1.5);
```

Nhưng JVM descriptor chỉ có `Number -> Number`. Metadata `Signature` giữ quan hệ `(TN;)TN;` cho compiler/tools khi cần đọc declaration.

Một call site có thể có casts được compiler chèn sau khi đọc kết quả từ descriptor đã erase. Việc có cast cụ thể phụ thuộc bytecode do compiler sinh và kiểu được sử dụng tại call site.

### 7.3. Khi nào không có Signature?

Không phải **mọi** method hoặc field trong class file đều cần `Signature`. Ví dụ method chỉ dùng kiểu concrete không generic như `void ping()` có thể chỉ có descriptor.

Không nên coi `Signature` là bắt buộc trên từng method hay là thứ JVM phải kiểm tra để dispatch. Descriptor và JVM verification/linkage vận hành dựa trên những thông tin phù hợp với JVM, còn `Signature` phục vụ generic reflection/metadata.

## 8. Kiểm tra cờ ACC_BRIDGE và ACC_SYNTHETIC

Lệnh:

```bash
javap -p -v 'GenericBytecodeDemo$StringHolder'
```

Trong class file kiểm thử có hai bridge methods:

```text
public void set(java.lang.Object);
  descriptor: (Ljava/lang/Object;)V
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

```text
public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

Ý nghĩa:

- `ACC_PUBLIC`: access flag của method.
- `ACC_BRIDGE`: bridge method do compiler sinh để giữ tính đúng đắn của quan hệ method.
- `ACC_SYNTHETIC`: method không được khai báo trực tiếp theo cách source-level ordinary member.

Cả hai bridge trong ví dụ đều được đánh dấu `ACC_BRIDGE` và `ACC_SYNTHETIC`. Tuy nhiên **synthetic không đồng nghĩa luôn là bridge**. Compiler có thể sinh các synthetic members khác vì những yêu cầu biên dịch khác; cần dùng chính cờ `ACC_BRIDGE` hoặc `Method.isBridge()` để nhận diện bridge.

### 8.1. Đọc bytecode của bridge `set(Object)`

Chạy:

```bash
javap -p -c 'GenericBytecodeDemo$StringHolder'
```

Phần bridge set(Object) có dạng gần như:

```text
public void set(java.lang.Object);
  Code:
     0: aload_0
     1: aload_1
     2: checkcast     #... // class java/lang/String
     5: invokevirtual #... // Method set:(Ljava/lang/String;)V
     8: return
```

Các constant pool indices và offsets có thể thay đổi. Cốt lõi là:

1. Nạp `this`.
2. Nạp argument Object.
3. `checkcast` thành String.
4. Gọi method typed `set(String)`.
5. Trả về.

Nếu Object thật không phải String, `checkcast` ném `ClassCastException`.

### 8.2. Đọc bytecode của bridge `get()`

Bridge Object get() thường có cấu trúc gần:

```text
public java.lang.Object get();
  Code:
     0: aload_0
     1: invokevirtual #... // Method get:()Ljava/lang/String;
     4: areturn
```

Không cần cast xuống String ở phần return của bridge: kết quả String vốn có thể dùng như Object. JVM nhận một reference phù hợp Object.

Không nhầm phần bridge này với các `checkcast` khác có thể xuất hiện trong **typed `StringHolder.get()`** khi nó gọi `super.get()` trả Object và cần dùng kết quả như String.

### 8.3. Không phụ thuộc bytecode offset cụ thể

Compiler/JDK có thể thay đổi instruction layout, số constant-pool entries hoặc cách in javap. Khi kiểm thử, xác minh **descriptor, method flags và quan hệ ủy quyền/cast**, thay vì assert nguyên xi mọi bytecode offset hoặc constant pool index.

## 9. Dùng Reflection để đối chiếu source, erasure và generic metadata

Java Reflection cung cấp nhiều cặp API có ý nghĩa khác nhau.

### 9.1. Erased type với `getReturnType()`

```java
Method method = Holder.class.getDeclaredMethod("get");

Class<?> erased = method.getReturnType();
```

Với `Holder<T>.get()`, `erased` là `Object.class`. Đây là kiểu return phù hợp với erased JVM descriptor.

### 9.2. Generic declaration với `getGenericReturnType()`

```java
Type generic = method.getGenericReturnType();
```

Với Holder<T>, kết quả là một `TypeVariable` tên `T`. Nếu in `getTypeName()`, thường thấy `T`.

`Method.getGenericParameterTypes()` tương tự cho parameter types: method `set(T)` có generic parameter T, trong khi `getParameterTypes()` cho Object.

### 9.3. Field Reflection cũng phân biệt hai kiểu

```java
Field field = Holder.class.getDeclaredField("value");

Class<?> erased = field.getType();
Type generic = field.getGenericType();
```

Kết quả lần lượt mô tả Object và T. Đây là cách xác định generic metadata còn giữ tại declaration.

### 9.4. Generic superclass từ subclass cụ thể

```java
Type parent = StringHolder.class.getGenericSuperclass();
```

Nó mô tả `Holder<String>`, thường dưới dạng `ParameterizedType`.

Cần phân biệt:

```java
Holder.class.getTypeParameters()
```

trả declaration type variable T, còn:

```java
StringHolder.class.getGenericSuperclass()
```

mô tả việc một subclass cụ thể thay T bằng String ở immediate superclass declaration.

Muốn giải kiểu của field T **trong ngữ cảnh** subclass có nhiều tầng kế thừa, một type resolver phải ghép các mappings type variables, không chỉ lấy một Field object rồi tin T tự thành String.

### 9.5. Nhận diện bridge bằng Reflection

```java
for (Method method : StringHolder.class.getDeclaredMethods()) {
    System.out.println(method.getName()
            + ":" + method.isBridge()
            + ":" + method.isSynthetic());
}
```

`getDeclaredMethods()` có thể trả nhiều methods cùng tên và cùng parameter list nhưng khác return type, vì JVM class file có bridge. Để test ổn định, hãy lọc/sắp xếp và kiểm tra thêm return type/parameter types.

Cờ:

```java
method.isBridge()
method.isSynthetic()
```

là hai phép hỏi **riêng**.

### 9.6. Đừng thiết kế reflection framework bằng cách coi mọi method đều là API source

Nếu framework scan `getDeclaredMethods()` rồi đăng ký tất cả như những user-defined handlers, bridge methods có thể gây **đăng ký trùng**: `get()` typed và `get()` bridge cùng được thấy.

Một chiến lược phổ biến là loại các methods với `isBridge()` khi bạn chỉ muốn source-level handlers, nhưng không áp dụng mù quáng trong mọi framework: có bài toán cần bridge để phân tích đường dispatch và tương thích. Hãy định nghĩa mục tiêu scan trước khi lọc.

## 10. Bridge có thể xuất hiện do covariant return dù không có Generics

Đây là điểm thường bị bỏ sót.

Tạo file **`CovariantBridge.java`**:

```java
class CovariantBridge {
    static class Parent {
        Number value() {
            return 1;
        }
    }

    static class Child extends Parent {
        @Override
        Integer value() {
            return 2;
        }
    }

    public static void main(String[] args) {
        System.out.println(new Child().value());

        for (var method : Child.class.getDeclaredMethods()) {
            System.out.println(method.getName()
                    + ":" + method.getReturnType().getSimpleName()
                    + ":" + method.isBridge()
                    + ":" + method.isSynthetic());
        }
    }
}
```

Lệnh:

```bash
javac --release 17 -Xlint:all CovariantBridge.java
java CovariantBridge
```

Output của lần kiểm thử:

```text
2
value:Integer:false:false
value:Number:true:true
```

Ví dụ này có thứ tự Reflection đúng như lần chạy kiểm chứng, nhưng `getDeclaredMethods()` không bảo đảm thứ tự giữa các môi trường. Nếu dùng làm automated test, hãy sắp xếp trước khi so sánh.

`javap -p -s 'CovariantBridge$Child'` hiển thị:

```text
java.lang.Integer value();
  descriptor: ()Ljava/lang/Integer;

java.lang.Number value();
  descriptor: ()Ljava/lang/Number;
```

Child source trả `Integer`, Parent source trả `Number`. JVM descriptors khác nhau do return type, nên compiler sinh bridge trả Number để bảo toàn dispatch. **Không có `<T>` nào trong ví dụ này.**

Kết luận: bridge thường liên quan Java Generics, nhưng **không độc quyền của Generics**. Có thể xuất hiện do covariance của return type.

## 11. Phân biệt bridge, overload, override và synthetic

| Tình huống | Do ai khai báo/tạo? | Ý nghĩa |
| --- | --- | --- |
| `String get()` override `T get()` với T=String | Người viết Java source | Override theo quy tắc Generics của Java |
| `Object get()` có `ACC_BRIDGE` | Compiler | Cầu nối erased superclass descriptor tới typed override |
| `void set(Object)` có `ACC_BRIDGE` | Compiler | Cast Object sang String rồi gọi `set(String)` |
| Hai source methods `process(String)` và `process(Integer)` | Người viết Java source | Overloading hợp lệ, không tự là bridge |
| `Integer value()` override `Number value()` | Người viết Java source | Covariant-return overriding |
| `Number value()` synthetic bridge | Compiler | Giữ descriptor của superclass không generic |
| Một synthetic method khác | Compiler/tooling | Có thể không phải bridge |

### 11.1. Không coi mọi method trùng tên là bridge

Một class có hai overloads hợp lệ:

```java
void log(String value) {}
void log(Integer value) {}
```

chúng có parameter descriptors khác nhau và có thể đều là ordinary source methods; `isBridge()` thường false.

Bridge xuất phát từ quan hệ overriding/erasure/covariant return, không phải từ việc tên method bị trùng đơn giản.

### 11.2. Không tự gọi bridge như một overload bình thường

Trong source `StringHolder`, bạn không viết:

```java
// Không thể dùng đây để tuyên bố một source overload
// song song chỉ khác return type:
// public Object get() { ... }
```

JVM class file có thể chứa những method compiler tạo mà bạn không thể định nghĩa cùng signature ở Java source. Dùng typed API bình thường, để compiler/JVM thực hiện phần cầu nối.

## 12. Name clash sau erasure: compiler không tự tạo bridge để sửa mọi lỗi

Một lỗi phổ biến khi người học thấy bridge là nghĩ “nếu hai methods erase giống nhau, compiler luôn tự thêm bridge”. Thực tế **không**.

### 12.1. Hai overload chỉ khác generic argument

Tạo file **`ErasureClash.java`**:

```java
import java.util.List;

class ErasureClash {
    void process(List<String> names) {
    }

    void process(List<Integer> numbers) {
    }
}
```

Chạy:

```bash
javac --release 17 ErasureClash.java
```

Compiler báo:

```text
name clash: process(List<Integer>) and
process(List<String>) have the same erasure
```

Hai overload có thể trông khác nhau ở generic source, nhưng erasure của cả hai danh sách tham số đều là raw `List`.

Bạn phải sửa **API declaration**, ví dụ:

```java
void processNames(List<String> names) {}
void processNumbers(List<Integer> numbers) {}
```

hoặc một generic method chung nếu implementation thực sự giống nhau. Cast ở call site hoặc gọi `javap` không thể cứu source declaration sai.

### 12.2. Xung đột với generic superclass nhưng không phải override

Tạo file **`BadOverride.java`**:

```java
class BadOverride {
    static class Parent<T> {
        void set(T value) {
        }
    }

    static class Child extends Parent<String> {
        void set(Object value) {
        }
    }
}
```

Compiler Java 17 báo:

```text
name clash: set(Object) in Child and
set(String) in Parent have the same erasure,
yet neither overrides the other
```

Child khai báo `set(Object)` trong khi method được kế thừa sau thay T ở quan hệ generic là `set(String)`. Việc erasure cùng descriptor không biến method `set(Object)` thành một override hợp lệ theo Java source rules.

Cách đúng là:

```java
static class Child extends Parent<String> {
    @Override
    void set(String value) {
    }
}
```

Rồi để compiler sinh bridge nếu cần. Đừng tự thay parameter từ String sang Object với kỳ vọng “đúng bytecode descriptor là đủ”.

### 12.3. `@Override` giúp kiểm tra sớm

Luôn cân nhắc `@Override` trên method dự định override. Nếu vô tình sai parameter type hoặc khai báo một overload mới, compiler thường chỉ rõ rằng method không override đúng.

Bridge method được tạo từ **quan hệ override hợp lệ**, không phải là phép nới lỏng quy tắc override.

## 13. Đối chiếu từ source tới class file theo một ma trận

Xét class Holder<T>, StringHolder và Mapper<String> của chương trình chính.

| Vị trí | Java source declaration | JVM descriptor sau erasure/cụ thể hóa | Generic Signature hoặc vai trò |
| --- | --- | --- | --- |
| `Holder.value` | `T value` | `Ljava/lang/Object;` | `TT;` |
| `Holder.get` | `T get()` | `()Ljava/lang/Object;` | `()TT;` |
| `Holder.set` | `void set(T)` | `(Ljava/lang/Object;)V` | `(TT;)V` |
| `Holder.echo` | `<N extends Number> N echo(N)` | `(Ljava/lang/Number;)Ljava/lang/Number;` | `<N:Ljava/lang/Number;>(TN;)TN;` |
| `Holder.tags` | `List<String> tags()` | `()Ljava/util/List;` | `()Ljava/util/List<Ljava/lang/String;>;` |
| `StringHolder.get` | `String get()` | `()Ljava/lang/String;` | Typed implementation |
| `StringHolder` bridge get | Không viết | `()Ljava/lang/Object;` | `ACC_BRIDGE`, `ACC_SYNTHETIC` |
| `StringHolder.set` | `void set(String)` | `(Ljava/lang/String;)V` | Typed implementation |
| `StringHolder` bridge set | Không viết | `(Ljava/lang/Object;)V` | Cast rồi delegate |
| `Uppercase.apply` | `String apply(String)` | `(Ljava/lang/String;)Ljava/lang/String;` | Typed interface implementation |
| `Uppercase` bridge apply | Không viết | `(Ljava/lang/Object;)Ljava/lang/Object;` | Bridge cho Mapper<String> |

Bảng là bản đồ để bạn so output javap và Reflection. Không phải mọi non-generic method có thêm Signature attribute; đừng tự bịa một generic signature cho những method không cần metadata ấy.

## 14. Cách phân tích lỗi class file thực tế

### 14.1. Bước 1: Biên dịch sạch và xác định version

```bash
javac -version
javac --release 17 -Xlint:all GenericBytecodeDemo.java
```

`--release 17` đặt mức ngôn ngữ/API/class-file target theo Java 17 khi compiler đang chạy hỗ trợ mức này. Đây là cách tái lập ví dụ đáng tin hơn chỉ dùng `-source 17` trong những tình huống cần kiểm soát cả API target.

### 14.2. Bước 2: Xem descriptor bằng `-s`

```bash
javap -p -s 'GenericBytecodeDemo$Holder'
javap -p -s 'GenericBytecodeDemo$StringHolder'
```

Ghi ra các cặp method name + descriptor. Đừng vội phân tích chữ ký generic được javap in ở phần tiêu đề mà bỏ qua dòng descriptor.

### 14.3. Bước 3: Xem `Signature` và flags bằng `-v`

```bash
javap -p -v 'GenericBytecodeDemo$Holder'
javap -p -v 'GenericBytecodeDemo$StringHolder'
```

Tìm `Signature:`, `ACC_BRIDGE`, `ACC_SYNTHETIC`. Lưu ý một class có thể có Signature ở **class-level** cho superclass generic, trong khi từng method lại có hoặc không có Signature riêng.

### 14.4. Bước 4: Xem lệnh cast/delegation bằng `-c`

```bash
javap -p -c 'GenericBytecodeDemo$StringHolder'
```

Kiểm tra bridge `set(Object)` có `checkcast String`, rồi gọi typed set; bridge get(Object) ủy quyền typed get(String). Nếu cần hiểu tại sao xuất hiện `ClassCastException`, đây là bằng chứng trực tiếp.

### 14.5. Bước 5: Đối chiếu Reflection

Dùng:

```java
Class<?> type = StringHolder.class;

for (Method method : type.getDeclaredMethods()) {
    System.out.println(method.toGenericString()
            + " bridge=" + method.isBridge()
            + " synthetic=" + method.isSynthetic());
}
```

Reflection cho cái nhìn runtime; `javap` cho cái nhìn class file. Khi cả hai cùng xác nhận bridge flags và signatures, bạn tránh nhầm output bị compiler/tool khác tạo ra với source.

### 14.6. Bước 6: Kiểm tra dynamic dispatch từ biến superclass/interface

```java
Holder<String> ref = new StringHolder("hi");
String value = ref.get();
```

Lời gọi được biên dịch trong bối cảnh Holder<String> mà runtime dispatch vẫn phải đến StringHolder override. Kết quả đúng là tiêu chuẩn quan trọng, không phải chỉ việc có cờ bridge.

### 14.7. Bước 7: Không dựa hoàn toàn vào thứ tự Reflection

`Class.getDeclaredMethods()` không bảo đảm thứ tự. Nếu viết assertions, hãy lọc theo tên, parameter types, return type và flags, hoặc sắp xếp kết quả.

Một method bridge có thể cùng tên/danh sách parameters với typed method nếu chỉ khác return type. Do đó một test chỉ dùng `getDeclaredMethod("get")` mà không kiểm tra cờ/return có thể bỏ sót bridge. Hãy duyệt toàn bộ declared methods khi cần audit.

## 15. Reflection và framework: khi nào bridge gây duplicate?

Một dependency injection container, serializer, annotation scanner hoặc RPC framework có thể duyệt method declarations bằng Reflection. Nếu nó coi mọi `getDeclaredMethods()` là source-level APIs, class có cả:

```text
String get()
Object get()  [bridge]
```

có thể bị nhận thành hai handlers, hai bean properties hoặc hai operations ngoài ý muốn.

Một hướng xử lý thường gặp là:

```java
if (method.isBridge()) {
    continue;
}
```

khi mục tiêu của scanner là **phương thức do lập trình viên khai báo ở source**. Tuy nhiên:

- Có frameworks cần bridge để liên kết annotations/overridden method metadata.
- Một bridge có thể không mang cùng metadata/annotations như typed implementation.
- Các công cụ cần phân biệt override tree và generic declaration có thể phải **resolve method tương ứng**, không chỉ bỏ mọi bridge.

Vì thế đừng biến “luôn bỏ bridge” thành luật toàn cục. Hãy xác định scanner cần thực sự đại diện cho *source-level method*, *all JVM methods*, hay *overridden generic contract*.

### 15.1. `isSynthetic()` không phải bộ lọc tương đương `isBridge()`

Một method synthetic có thể tồn tại vì compiler-generated artifact không liên quan bridge. Nếu chỉ muốn lọc bridge, dùng `isBridge()`. Nếu muốn lọc mọi compiler-generated methods, đó là chính sách khác và cần cân nhắc các trường hợp đặc biệt.

### 15.2. Generic metadata không tự validate runtime data

Reflection thấy `List<String>` ở Signature không nghĩa mọi phần tử trong một list runtime là String. Raw/unchecked operations có thể đưa dữ liệu sai vào. Type token và generic signatures cho biết **kiểu đã khai báo**, không tự hoàn thành kiểm tra object graph.

Framework deserialize thực sự phải dùng metadata để chuyển đổi/kiểm tra dữ liệu, không chỉ cast một raw List và coi như đã xong.

## 16. `javap` và Java Reflection trả lời những câu hỏi khác nhau

| Câu hỏi | Công cụ phù hợp |
| --- | --- |
| JVM method descriptor là gì? | `javap -s`, `javap -v` |
| Class file có generic Signature nào? | `javap -v` |
| Method có ACC_BRIDGE/ACC_SYNTHETIC không? | `javap -v` |
| Bridge có cast/delegate như thế nào? | `javap -c` |
| Method ở runtime có `isBridge()` không? | Java Reflection |
| Erased parameter/return types trong Reflection? | `getParameterTypes()`, `getReturnType()` |
| Generic parameter/return metadata? | `getGenericParameterTypes()`, `getGenericReturnType()` |
| Generic superclass đã khai báo? | `Class.getGenericSuperclass()` |
| Source đã khai báo method nào? | Source code + đối chiếu reflection/javap |
| Một field value thực có đúng type arguments không? | Validation dữ liệu thật, không chỉ Reflection Signature |

Làm đúng thường cần kết hợp **source, javap, Reflection và runtime test**. Chỉ đọc một lớp biểu diễn có thể khiến bạn kết luận sai.

## 17. Vì sao có thể thấy class file methods “không thể viết” trong Java source?

JVM bytecode format và Java source rules không hoàn toàn giống nhau.

Java method overloading ở source dựa trên method signatures theo JLS, không cho chỉ khác return type để thành overload. Nhưng method descriptor của JVM có return descriptor, và `javac` có thể phát sinh bridge để giữ binary-level dispatch.

Do đó trong bytecode:

```text
get:()Ljava/lang/String;
get:()Ljava/lang/Object;
```

có thể cùng xuất hiện. Java source không cho bạn khai báo hai methods `String get()` và `Object get()` cạnh nhau như hai overload thông thường.

**Bài học lớn:** không nên suy luận ngược rằng mọi class-file method là một Java source method viết tay. Metadata `ACC_BRIDGE`, `ACC_SYNTHETIC` và việc đọc source giúp phân biệt.

### 17.1. Bridge cũng ảnh hưởng quan sát của static analyzers

Nếu một công cụ chỉ đếm public methods trong class file, nó có thể đếm cả bridge và typed implementation, cho số lượng lớn hơn source. Khi xây rule về API surface, cần quyết định có tính bridge hay không.

### 17.2. Không phải cứ có `Signature` là có bridge

Một `List<String> tags()` có `Signature` giữ type argument nhưng thường không cần bridge nếu không tham gia một quan hệ override đòi descriptor cầu nối.

Một class generic `Holder<T>` có nhiều Signature entries, nhưng **Holder tự nó** không nhất thiết chứa bất kỳ bridge nào. Bridge ở subclass hoặc interface implementor được sinh khi thực sự cần.

## 18. Class-file metadata và binary compatibility

Type erasure giúp Java Generics duy trì tương thích với các thư viện trước thời Generics trong nhiều trường hợp, nhưng đừng suy ra **mọi thay đổi generic signature đều binary-compatible**.

Ví dụ thay raw parameter type `List` thành `Collection` đổi JVM descriptor; client bytecode cũ có thể không liên kết tới method mới. Ngược lại, chỉ thay generic type argument trong `Signature` mà không đổi descriptor có thể không thay JVM-level method identity, nhưng source type checking vẫn có thể thay đổi và tạo lỗi khi biên dịch lại.

Bridge là một phần cơ chế giữ overriding/binary method lookup khi subclass specialized method có descriptor khác do erasure hoặc return covariance.

### 18.1. Khi sửa generic superclass hoặc interface

Một thay đổi từ:

```java
interface Mapper<T> {
    T apply(T input);
}
```

sang một contract có bound/return/parameter khác có thể đổi descriptor sau erasure, khiến các classes đã biên dịch trước đó gặp vấn đề tương thích. Hãy đánh giá:

- Source compatibility khi client biên dịch lại.
- Binary compatibility với compiled clients.
- Override/bridge method được compiler tạo lại.
- Reflection-based frameworks có đang phụ thuộc Signature/bridge metadata không.

Đừng xóa synthetic bridge methods bằng bytecode post-processing chỉ vì “source không khai báo”; điều đó có thể làm mất đường dispatch cần thiết.

### 18.2. Bytecode tools nên bảo toàn thuộc tính thích hợp

Nếu một build step tối ưu/biến đổi class file, việc bỏ Signature không nhất thiết phá JVM linkage ngay, nhưng có thể làm mất thông tin generic cần cho Reflection, serializer hoặc framework. Việc bỏ bridges có thể nguy hiểm hơn vì chúng có thể được dùng làm method dispatch entry points.

Khi debug sự khác nhau giữa build thường và build đã qua obfuscation/shading/instrumentation, kiểm tra cả descriptors, Signature, flags và code của bridge.

## 19. Bẫy thường gặp khi học từ `javap`

### Bẫy 1 — Nhìn `javap` in `T` rồi nói JVM thật sự gọi method nhận T

Không chính xác. `javap` có thể dựng chữ ký generic dễ đọc từ metadata, nhưng descriptor cho method có bound mặc định vẫn là Object. JVM không có parameter type `T` trong descriptor.

### Bẫy 2 — Cho rằng `Signature` và descriptor là cùng một dữ liệu

Sai. Descriptor dùng cho JVM-level type/linkage; Signature lưu metadata generic theo grammar khác.

### Bẫy 3 — Nghĩ Signature giữ mọi type argument của object instance

Sai. Nó mô tả **declarations**, không phải type argument của mỗi instance lúc chạy.

### Bẫy 4 — Nghĩ chỉ generic methods mới cần bridge

Sai. Một subclass override generic superclass/interface bằng concrete typed method có thể cần bridge; covariant returns không generic cũng có thể tạo bridge.

### Bẫy 5 — Nghĩ mọi method generic sinh bridge

Sai. Bridge được sinh khi có nhu cầu giữ overriding/dispatch. Một generic method độc lập như `Holder.echo` có thể có Signature nhưng không cần bridge.

### Bẫy 6 — Tưởng `synthetic=true` luôn bằng `bridge=true`

Sai. Bridge thường synthetic trong output javac kiểm chứng, nhưng synthetic members còn có thể phục vụ mục đích khác.

### Bẫy 7 — Tự tạo `void set(Object)` để override `void set(T)` đã specialized

Có thể gây name clash “same erasure, yet neither overrides”. Định nghĩa override đúng typed parameter theo source rules, compiler sẽ tự sinh bridge.

### Bẫy 8 — Overload `process(List<String>)` và `process(List<Integer>)`

Không hợp lệ do cùng erasure. Bridge không phải cơ chế sửa overload declarations có name clash.

### Bẫy 9 — Duyệt Reflection không sắp xếp và assert thứ tự

`getDeclaredMethods()` không có ordering guarantee. Sắp xếp/lọc theo đầy đủ dấu hiệu cần thiết.

### Bẫy 10 — Framework đăng ký bridge như một handler thứ hai

Có thể xảy ra khi quét mọi declared methods mà không phân biệt source API và synthetic compiler artifacts.

### Bẫy 11 — Xem cast trong bridge là lỗi compiler

`checkcast` trong `set(Object)` là cách giữ type safety/ủy quyền cho method nhận String. Nếu Reflection/raw code gọi sai kiểu, `ClassCastException` là kết quả có thể đúng.

### Bẫy 12 — Cố so constant-pool indices giữa các compiler

Các số `#...`, offsets và chi tiết formatting không ổn định. Hãy so semantics của descriptor, Signature, flags và đường delegate.

### Bẫy 13 — Dùng Reflection generic type để khẳng định runtime collection an toàn

Generic metadata không kiểm tra elements. Nếu code dùng raw/unchecked casts, heap pollution vẫn có thể xảy ra.

### Bẫy 14 — Nhầm method descriptor với Java overloading rule

Trong descriptor JVM, return type được mã hóa. Nhưng Java source không cho overload chỉ dựa trên return type. Bridge được compiler tạo dưới luật riêng.

### Bẫy 15 — Chỉ chạy `javap` trên subclass

Bạn cần xem **cả superclass/interface erased descriptor** và **subclass implementation/bridge** để giải thích vì sao cầu nối tồn tại.

## 20. Checklist khi gặp bridge hoặc lỗi generic erasure

1. Xác định compiler/JDK version và compile target; với bài này dùng `--release 17`.
2. Mở source declaration của superclass/interface và subclass; tìm type parameters/bounds.
3. Ghi chữ ký source sau khi **substitute type arguments**, ví dụ `T = String`.
4. Tính erasure của từng method theo bounds, không mặc định Object nếu có bound.
5. Dùng `javap -p -s` xác nhận descriptors của superclass/interface và subclass.
6. Dùng `javap -p -v` tìm `Signature:` ở class/fields/methods cần đọc.
7. Với methods bổ sung không thấy ở source, kiểm tra `ACC_BRIDGE`, `ACC_SYNTHETIC`.
8. Dùng `javap -p -c` xem bridge delegate method nào và cast gì.
9. Dùng Reflection `getDeclaredMethods()`, `isBridge()`, `isSynthetic()` và return/parameter types để xác nhận từ runtime.
10. Không dựa vào ordering của Reflection; sắp xếp hoặc lọc trước khi assert.
11. Kiểm tra dynamic dispatch qua biến có kiểu superclass/interface.
12. Với lỗi `name clash`, phân biệt declaration conflict với trường hợp override hợp lệ có bridge.
13. Với generic field/return, tách `getType()`/`getReturnType()` khỏi `getGenericType()`/`getGenericReturnType()`.
14. Khi thay đổi API hoặc xử lý class file, đánh giá source/binary compatibility và framework Reflection.
15. Đừng dùng raw/unchecked code như cách chứng minh bridge hoạt động; nếu cần test runtime error, khoanh nó trong ví dụ kiểm thử.
16. Ghi nhận rõ output phụ thuộc compiler/class-file tool ở những chi tiết như constant-pool indices.

## 21. Bài tập thực hành và đáp án

### Bài 1 — Erasure của type variable không bound

Cho:

```java
class Box<T> {
    T value();
}
```

**Câu hỏi:** Return descriptor của `value()` là gì nếu T không có bound tường minh?

<details>
<summary>Đáp án</summary>

Erasure của T là Object, nên method descriptor là `()Ljava/lang/Object;`. Nếu class file giữ generic method Signature thì phần return dùng `TT;`, ví dụ `()TT;`.

</details>

### Bài 2 — Bound thay đổi descriptor

Cho:

```java
<N extends Number> N twice(N n);
```

**Câu hỏi:** Erased parameter/return types là gì?

<details>
<summary>Đáp án</summary>

Cả hai erase về Number, nên descriptor là `(Ljava/lang/Number;)Ljava/lang/Number;`. Generic Signature giữ quan hệ kiểu N ở cả input/output.

</details>

### Bài 3 — `List<String>` ở return

```java
List<String> names();
```

**Câu hỏi:** Vì sao descriptor không chứa String?

<details>
<summary>Đáp án</summary>

Parameterized type `List<String>` erase thành List, nên descriptor là `()Ljava/util/List;`. Generic `Signature` có thể ghi `()Ljava/util/List<Ljava/lang/String;>;`.

</details>

### Bài 4 — Vì sao StringHolder cần Object get()?

Cho:

```java
class Base<T> {
    T get() { return null; }
}
class Derived extends Base<String> {
    @Override String get() { return "x"; }
}
```

<details>
<summary>Đáp án</summary>

Erased Base.get descriptor trả Object, còn typed Derived.get trả String. Compiler có thể tạo bridge Object get() trong Derived để các lời gọi qua erased Base method descriptor dispatch tới typed override.

</details>

### Bài 5 — Vì sao bridge `set(Object)` có cast?

<details>
<summary>Đáp án</summary>

Method typed implementation nhận String, trong khi erased superclass method nhận Object. Bridge phải cast argument Object thành String trước khi delegate. Nếu caller qua raw/reflection boundary truyền Integer, cast có thể ném ClassCastException.

</details>

### Bài 6 — Cờ Bridge và Synthetic có giống nhau không?

<details>
<summary>Đáp án</summary>

Không. `ACC_BRIDGE` nhận diện bridge; `ACC_SYNTHETIC` đánh dấu compiler-generated member rộng hơn. Trong ví dụ javac Java 17, bridge có cả hai cờ, nhưng không phải mọi synthetic method đều là bridge.

</details>

### Bài 7 — Covariant return không generic

Nếu Parent trả Number và Child override trả Integer, bridge có thể xuất hiện không?

<details>
<summary>Đáp án</summary>

Có. Trong ví dụ `CovariantBridge`, compiler sinh Integer value() typed implementation và Number value() bridge. Đây là cầu nối do covariant return, ngay cả khi không khai báo generic type parameters.

</details>

### Bài 8 — Lỗi overload sau erasure

```java
void save(List<String> names) {}
void save(List<Integer> counts) {}
```

**Câu hỏi:** Compiler có tự sinh bridge để phân biệt hai method không?

<details>
<summary>Đáp án</summary>

Không. Cả hai có cùng erasure của tham số là List, dẫn tới name clash. Phải đổi chữ ký/tên hoặc tái thiết kế API.

</details>

### Bài 9 — Reflection thấy hai get methods

Nếu Reflection trên subclass liệt kê một typed get và một bridge get, làm thế nào scanner chỉ đăng ký method người dùng khai báo?

<details>
<summary>Đáp án</summary>

Một hướng là lọc `method.isBridge()` rồi xem xét `isSynthetic()` và context của framework. Cần kiểm tra return types vì JVM có thể chứa cùng tên/parameters với return descriptors khác nhau. Nếu scanner cần liên kết generic override metadata, có thể cần resolve bridge thay vì đơn giản bỏ qua.

</details>

### Bài 10 — Generic superclass và generic field

`StringHolder extends Holder<String>` nhưng `Holder.value` có generic type T. Tại sao `Holder.class.getDeclaredField("value").getGenericType()` không tự trả String.class?

<details>
<summary>Đáp án</summary>

Field declaration của Holder vẫn dùng type variable T. StringHolder's generic superclass metadata lưu mapping T→String, nhưng phép Reflection trên chính Holder field không mang sẵn context của subclass. Cần resolver kết hợp hai nguồn metadata.

</details>

### Bài 11 — `javap -s` hay `javap -v`?

<details>
<summary>Đáp án</summary>

`-s` in descriptors. `-v` hiển thị verbose attributes/flags, trong đó có `Signature` và `ACC_BRIDGE`. Dùng `-c` để xem JVM instructions và `-p` để xem private members.

</details>

### Bài 12 — Bridge có bảo đảm List<String> thật sự chỉ chứa String không?

<details>
<summary>Đáp án</summary>

Không. Bridge giữ dispatch khi generic overriding/covariant return cần descriptor phù hợp. Nó không tự kiểm tra từng phần tử bên trong generic collections hoặc khắc phục heap pollution do raw/unchecked operations.

</details>

## 22. Tổng kết

Để đọc đúng Generics trong class file, hãy nhìn **cả ba tầng**:

1. **Source generic declaration** cho compiler hiểu quan hệ kiểu: `T get()`, `void set(T)`, `<N extends Number> N echo(N)`, `List<String> tags()`.
2. **Erased JVM descriptor** để runtime định danh/call method: Object thay T không bound, Number thay N bound, List thay List<String>.
3. **Generic `Signature` metadata** giúp công cụ phục hồi khai báo kiểu: `()TT;`, `(TT;)V`, `<N:Ljava/lang/Number;>(TN;)TN;`, các nested generic type arguments.

Khi một subclass specialized generic override hoặc dùng covariant return có descriptor khác, compiler có thể sinh **bridge method**. Trên Java 17, `javap -v` cho thấy cờ `ACC_BRIDGE, ACC_SYNTHETIC`; Reflection xác nhận bằng `Method.isBridge()` và `isSynthetic()`. Bridge chỉ nối các descriptors/đường dispatch theo quan hệ hợp lệ, **không** sửa name clash declarations và **không** reify toàn bộ generic types của object instances.

Quy trình đáng tin là: **đọc source → tính erasure → xem `javap -s` → kiểm tra `Signature`/flags với `javap -v` → xem bridge code bằng `javap -c` → đối chiếu Reflection và runtime dispatch**. Khi nắm quy trình này, bạn sẽ phân biệt được API người dùng khai báo, metadata Generics, và những bytecode methods compiler bắt buộc phải phát sinh để Java overriding hoạt động đúng.