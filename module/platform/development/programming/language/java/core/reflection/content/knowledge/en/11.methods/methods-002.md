# Reflection Method: kiểu tham số, kiểu `throws` và các biến thể generic

Khi dùng Java Reflection để đọc chữ ký một phương thức, có **hai góc nhìn phải phân biệt**:

1. **Kiểu thực thi sau type erasure** (*erased/raw runtime type*) — được biểu diễn bằng `Class<?>`. Đây là kiểu JVM dùng để xác định descriptor của method và kiểm tra đối số khi gọi qua reflection.
2. **Kiểu generic được khai báo trong mã nguồn** (*generic signature*) — được biểu diễn bằng `java.lang.reflect.Type` và các subtype của nó. Đây là metadata cho công cụ tài liệu hóa, thư viện mapping, injection và kiểm tra hợp đồng kiểu.

Ví dụ, một tham số `List<? super T>` có **runtime type** là `java.util.List` nhưng **generic type** là `ParameterizedType` biểu thị `List<? super T>`. Tham số `T...` có thể là mảng `Number[]` ở runtime nếu `T extends Number`, trong khi chữ ký generic vẫn biểu thị `T[]`.

Trên đối tượng `java.lang.reflect.Method`, bốn API trọng tâm là:

| Metadata cần đọc | Sau erasure | Giữ chữ ký generic |
| --- | --- | --- |
| Tham số phương thức | `getParameterTypes(): Class<?>[]` | `getGenericParameterTypes(): Type[]` |
| Kiểu `throws` được khai báo | `getExceptionTypes(): Class<?>[]` | `getGenericExceptionTypes(): Type[]` |
| Kiểu trả về (để đối chiếu) | `getReturnType(): Class<?>` | `getGenericReturnType(): Type` |
| Type parameter do chính method khai báo | — | `getTypeParameters(): TypeVariable<Method>[]` |

**Điểm học tập chính:** Các API có chữ `Generic` dùng để *mô tả* kiểu được khai báo. Chúng không khôi phục kiểu đối số generic của mọi đối tượng tại runtime, không tự kiểm tra nội dung một collection và không sửa quy tắc type erasure của Java.

## 1. Lấy đúng đối tượng `Method` trước khi phân tích chữ ký

Ví dụ một phương thức khai báo như sau:

~~~java
public <T extends Number & Comparable<T>, E extends Exception>
java.util.List<? extends T> query(
        java.util.List<? super T> destination, T... values)
        throws java.io.IOException, E {
    // Phần thân phương thức
    return java.util.Collections.emptyList();
}
~~~

Đây là **đoạn minh họa chữ ký**, chưa phải class Java độc lập. Nó gồm:

- **Hai tham số phương thức:** `List<? super T> destination` và `T... values`.
- **Hai type parameters do method khai báo:** `T`, `E`; `T` có hai bound (`Number`, `Comparable<T>`); `E` có bound `Exception`.
- **Kiểu trả về generic:** `List<? extends T>`.
- **Hai kiểu trong mệnh đề `throws`:** `IOException` và `E`.

Để tra cứu method bằng reflection, `getDeclaredMethod` yêu cầu **tên + các kiểu tham số sau erasure**; không truyền `List<? super T>` hay `T[]` dưới dạng biểu thức generic. Với một class `Service` chứa method này:

~~~java
Method method = Service.class.getDeclaredMethod(
        "query",
        java.util.List.class,
        Number[].class
);
~~~

`T` có bound đầu tiên là `Number`, nên `T...` có kiểu mảng runtime là `Number[]`. Nếu tra bằng `Object[].class` hoặc `Integer[].class` thì không khớp descriptor và sẽ nhận `NoSuchMethodException`.

Phân biệt cách tìm:

- `getDeclaredMethod(name, parameterTypes...)`: tìm method khai báo **trực tiếp** trên class/interface đang xét, gồm cả method không public; không tự tìm method kế thừa.
- `getMethod(name, parameterTypes...)`: tìm **public method** theo cơ chế tra cứu tương ứng, có tính đến các public method kế thừa.
- Hai method có tên và danh sách tham số khác nhau là overload; Reflection tra theo **erased parameter types**, không dùng kiểu trả về để người gọi lựa chọn overload.
- `Class.getDeclaredMethods()` không bảo đảm thứ tự theo mã nguồn; nếu hiển thị danh sách method cho người dùng, hãy sắp xếp theo tên và chữ ký đã chuẩn hóa.

## 2. `getParameterTypes()`: kiểu tham số runtime

Khai báo của API:

~~~java
Class<?>[] parameters = method.getParameterTypes();
~~~

Mỗi phần tử là một đối tượng `Class` biểu diễn **kiểu tham số formal sau erasure**. Ví dụ với `query`:

~~~text
java.util.List
java.lang.Number[]
~~~

Ở đây:

- `List<? super T>` được xóa về `List`.
- `T...` có dạng mảng khi biên dịch; `T extends Number & Comparable<T>` xóa về bound đầu tiên là `Number`, nên kết quả là `Number[]`.
- `getParameterTypes()` không cho biết `? super T`, tên `T` hoặc các bound bổ sung.
- Kiểu primitive vẫn là token primitive, ví dụ `int.class`; tham số mảng như `String[]` vẫn là class mảng `String[].class`.

`Class<?>[]` này phù hợp để so sánh descriptor, xác định method overload hoặc chuẩn bị đối số Reflection. Nó **không chứng minh** đối tượng `List` thực tế có phần tử đúng kiểu generic.

### Tham số cuối dạng varargs

`T... values` được JVM biểu diễn là **tham số mảng**. Thông tin “đây là lời khai báo varargs” lấy riêng qua `Method.isVarArgs()`:

~~~java
boolean declaredVarargs = method.isVarArgs();
~~~

Ví dụ `void a(String[] names)` và `void b(String... names)` đều có parameter type `String[].class`, nhưng chỉ `b` có `isVarArgs() == true`. Với `Method.invoke`, cần tôn trọng số lượng formal parameters và kiểu mảng đã xóa; không mặc định rằng Reflection sẽ tự đóng gói danh sách đối số theo cú pháp varargs ở lời gọi Java thông thường.

## 3. `getGenericParameterTypes()`: kiểu tham số có generic metadata

Khai báo:

~~~java
Type[] genericParameters = method.getGenericParameterTypes();
~~~

Với `query`, `Type.getTypeName()` lần lượt biểu thị:

~~~text
java.util.List<? super T>
T[]
~~~

Đây không phải hai đối tượng `Class` thông thường:

- `List<? super T>` là **`ParameterizedType`** có raw type `List.class` và một type argument là **`WildcardType`** chứa lower bound `T`.
- `T[]` là **`GenericArrayType`** vì thành phần mảng là type variable `T`. `getGenericComponentType()` cho ra `TypeVariable` tương ứng.
- Nếu kiểu tham số được khai báo trực tiếp là `T` (không có mảng), phần tử `Type[]` có thể chính là `TypeVariable`.
- Nếu tham số là `String`, `int` hoặc `String[]` không chứa generic component, kết quả thường là đối tượng `Class`.

Vì thế **không ép mọi `Type` về `Class<?>`**:

~~~java
Type generic = method.getGenericParameterTypes()[0];

if (generic instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();
}
~~~

Đây là đoạn phân tích metadata có thể đặt trong phương thức; biến `method` phải được khởi tạo trước. Khi kiểm tra `arguments[0]` của `List<? super T>`, ta gặp `WildcardType`:

~~~java
Type argument = ((ParameterizedType) generic)
        .getActualTypeArguments()[0];

if (argument instanceof WildcardType wildcard) {
    Type[] lower = wildcard.getLowerBounds(); // Chứa T ở ví dụ này.
    Type[] upper = wildcard.getUpperBounds(); // Object khi không có extends bound cụ thể.
}
~~~

**`? super T` và `? extends T` không giống nhau:** lower bound của wildcard giúp mô tả phía “được phép nhận” một kiểu, còn upper bound mô tả phía “bị giới hạn trên” về quan hệ kiểu. Reflection đọc chữ ký này, nhưng không tái tạo logic type-checking hoàn chỉnh như compiler.

## 4. Những biến thể của `Type` cần nhận diện

`java.lang.reflect.Type` là interface chung cho nhiều dạng chữ ký:

| Dạng khai báo | Kiểu `Type` thường gặp | Cần đọc gì? |
| --- | --- | --- |
| `String`, `int`, `String[]` | `Class<?>` | `getTypeName()`, `isArray()`, `getComponentType()` khi phù hợp |
| `List<String>` | `ParameterizedType` | `getRawType()`, `getActualTypeArguments()`, `getOwnerType()` khi là nested type |
| `T` | `TypeVariable<?>` | `getName()`, `getBounds()`, `getGenericDeclaration()` |
| `T[]` | `GenericArrayType` | `getGenericComponentType()` |
| `? extends Number` / `? super T` | `WildcardType` | `getUpperBounds()` / `getLowerBounds()` |

**Ví dụ phân loại:**

~~~java
static String kind(Type type) {
    if (type instanceof Class<?>) return "Class";
    if (type instanceof ParameterizedType) return "ParameterizedType";
    if (type instanceof TypeVariable<?>) return "TypeVariable";
    if (type instanceof GenericArrayType) return "GenericArrayType";
    if (type instanceof WildcardType) return "WildcardType";
    return "Other Type";
}
~~~

Đây là phương thức minh họa, cần import `java.lang.reflect.*`. Trong thực tế, một `ParameterizedType` có thể chứa tiếp `ParameterizedType`, `WildcardType`, `TypeVariable` hoặc `GenericArrayType`. Muốn dựng cây generic signature đầy đủ thì phải xử lý **đệ quy**, không chỉ in raw type.

### Type variable nằm ở method hay ở class?

Hai chữ ký có thể cùng sử dụng tên `T` nhưng nguồn khai báo khác nhau:

~~~java
class Container<T> {
    T read() { return null; }         // T của class.
    <U> U convert(U input) { return input; } // U của method.
}
~~~

Với `read`, `getGenericReturnType()` có thể là `TypeVariable` do **`Container` khai báo**; `read.getTypeParameters()` trả mảng rỗng vì method không khai báo type variable mới. Với `convert`, `getTypeParameters()` có `U`, và `U.getGenericDeclaration()` trỏ đến chính method `convert`. Đừng nhầm metadata của type parameter trên class với type parameter trên method.

**Quan trọng về giới hạn:** nếu chạy `Container<String>`, Java Reflection trên `Method` không tự suy ra “`T` lúc này là `String`” từ một instance. Muốn thay thế biến kiểu của class bằng đối số cụ thể, phải phân tích ngữ cảnh `ParameterizedType` từ generic superclass/interface hoặc type token phù hợp; nhiều thông tin bị xóa ở runtime.

## 5. `getExceptionTypes()`: kiểu trong mệnh đề `throws` sau erasure

Khai báo API:

~~~java
Class<?>[] exceptionTypes = method.getExceptionTypes();
~~~

Với:

~~~java
<T extends Number & Comparable<T>, E extends Exception>
void query(T item) throws java.io.IOException, E { }
~~~

`getExceptionTypes()` trả các class:

~~~text
java.io.IOException
java.lang.Exception
~~~

Lý do: `E` bị xóa về bound đầu tiên `Exception`. Nếu method khai báo `<X extends IOException> void fail() throws X`, dạng raw sẽ là `IOException.class`.

Lưu ý các điểm quan trọng:

- Đây là **danh sách kiểu exception được khai báo trong `throws`**, không phải danh sách mọi exception mà method *thực tế có thể ném*.
- Một method không có mệnh đề `throws` → mảng rỗng, mặc dù nó vẫn có thể ném unchecked exception như `NullPointerException` hoặc `IllegalArgumentException`.
- Java cho phép khai báo một unchecked exception trong `throws`; Reflection sẽ ghi nhận nó nếu có trong chữ ký.
- `Error` hoặc unchecked exception có thể phát sinh ngoài khai báo; không dùng `getExceptionTypes()` để chứng minh “method không bao giờ lỗi”.
- `getExceptionTypes()` không cho biết tên type variable hay mối liên hệ giữa type variable ấy và tham số của method.

## 6. `getGenericExceptionTypes()`: bảo toàn `throws E`

API:

~~~java
Type[] genericExceptions = method.getGenericExceptionTypes();
~~~

Với `query(...) throws IOException, E`, hai phần tử có chữ ký:

~~~text
java.io.IOException
E
~~~

Trong đó phần tử thứ nhất thường là `Class<IOException>`, phần tử thứ hai là `TypeVariable` tên `E`. Ta có thể truy cập bound:

~~~java
for (Type type : method.getGenericExceptionTypes()) {
    if (type instanceof TypeVariable<?> variable) {
        System.out.println(variable.getName());
        System.out.println(java.util.Arrays.toString(variable.getBounds()));
    }
}
~~~

Nếu `E extends Exception`, bound là `Exception.class`; nếu `X extends IOException`, bound là `IOException.class`.

### Vì sao generic `throws` có ích?

Khai báo:

~~~java
static <X extends Exception> void propagate(X problem) throws X {
    throw problem;
}
~~~

Đây là một **phương thức độc lập dùng để minh họa**, đặt bên trong class để biên dịch. Nó mô tả cho compiler rằng kiểu exception truyền vào và kiểu exception có thể ném ra được liên kết bởi **cùng type variable `X`**. Sau erasure, Reflection `getExceptionTypes()` chỉ còn `Exception.class`; `getGenericExceptionTypes()` vẫn biểu diễn `X`. Thư viện phân tích API có thể dùng metadata này để hiển thị hợp đồng chính xác hơn.

**Không nhầm generic `throws` với `List<IOException>` trong throws:** Java không cho phép tham số hóa một exception class kiểu `SomeException<T> extends Exception`, vì generic class không được trực tiếp/gián tiếp kế thừa `Throwable`. Biến kiểu có bound exception (`<E extends Exception> ... throws E`) là cơ chế hợp lệ để khai báo generic throws.

### Reflection gọi method thì exception ra sao?

`Method.invoke(receiver, args...)` không trực tiếp chuyển cho caller checked exception của method được gọi như một lời gọi Java thông thường. Nếu phần thân method ném exception, `invoke` bọc nó bằng **`InvocationTargetException`**; có thể kiểm tra `getCause()`. Ngoài ra bản thân Reflection có thể ném `IllegalAccessException`, `IllegalArgumentException` hoặc lỗi khác do lời gọi. Danh sách `getGenericExceptionTypes()` chỉ mô tả **chữ ký của method đích**, không tự thay thế hợp đồng exception của `Method.invoke`.

## 7. `getTypeParameters()` và erasure khi có nhiều bound

API:

~~~java
TypeVariable<Method>[] variables = method.getTypeParameters();
~~~

Với:

~~~java
<T extends Number & Comparable<T>, E extends Exception>
~~~

ta có:

- `T.getName()` → `"T"`.
- `T.getBounds()` → `Number` và `Comparable<T>`; bound đầu là class `Number`, bound thứ hai là parameterized interface.
- `E.getName()` → `"E"`.
- `E.getBounds()` → `Exception.class`.

Quy tắc **erasure của type variable** dùng bound bên trái đầu tiên. Nếu chỉ khai báo `<T>`, implicit upper bound là `Object`, nên erasure của `T` là `Object`. Nếu có nhiều bound, không đồng nghĩa JVM có “kiểu giao” cụ thể làm tham số; descriptor dùng erasure theo quy tắc JLS.

`getTypeParameters()` chỉ trả type variables được **method** khai báo. Nó không đại diện cho mọi type variable xuất hiện trong tham số: chúng cũng có thể được khai báo bởi class bao ngoài.

## 8. Ví dụ Java 17+ chạy đầy đủ, so sánh cả bốn API

Tạo file duy nhất **`MethodSignatureDemo.java`**. Ví dụ chủ động dùng:

- Parameterized type `List<? super T>`.
- Generic array `T...` với erasure thành `Number[]`.
- Wildcard return `List<? extends T>`.
- Generic `throws IOException, E` và method `fail` khai báo `throws X`.
- Phân tích bounds của `T` và `E`.
- `Parameter.isNamePresent()` để nhận biết việc lưu tên tham số khi biên dịch.

~~~java
import java.io.IOException;
import java.lang.reflect.*;
import java.util.*;
import java.util.stream.Collectors;

public class MethodSignatureDemo {
    static class Service {
        @SafeVarargs
        public final <T extends Number & Comparable<T>, E extends Exception>
        List<? extends T> query(List<? super T> destination, T... values)
                throws IOException, E {
            for (T value : values) {
                destination.add(value);
            }
            return Collections.emptyList();
        }

        public void text(String[] names) throws IOException { }

        public <X extends IOException> void fail(X problem) throws X {
            throw problem;
        }
    }

    private static String types(Type[] xs) {
        return Arrays.stream(xs).map(Type::getTypeName).collect(Collectors.joining(" | "));
    }

    private static String classes(Class<?>[] xs) {
        return Arrays.stream(xs).map(Class::getTypeName).collect(Collectors.joining(" | "));
    }

    public static void main(String[] args) throws Exception {
        Method m = Service.class.getDeclaredMethod("query", List.class, Number[].class);
        System.out.println("params raw: " + classes(m.getParameterTypes()));
        System.out.println("params generic: " + types(m.getGenericParameterTypes()));
        System.out.println("return raw: " + m.getReturnType().getTypeName());
        System.out.println("return generic: " + m.getGenericReturnType().getTypeName());
        System.out.println("throws raw: " + classes(m.getExceptionTypes()));
        System.out.println("throws generic: " + types(m.getGenericExceptionTypes()));
        System.out.println("vars: " + Arrays.stream(m.getTypeParameters()).map(TypeVariable::getName)
                .collect(Collectors.joining(" | ")));

        for (TypeVariable<Method> variable : m.getTypeParameters()) {
            System.out.println("bound " + variable.getName() + ": " + types(variable.getBounds()));
        }

        System.out.println("isVarArgs: " + m.isVarArgs());
        System.out.println("second is GenericArrayType: "
                + (m.getGenericParameterTypes()[1] instanceof GenericArrayType));
        System.out.println("first is ParameterizedType: "
                + (m.getGenericParameterTypes()[0] instanceof ParameterizedType));
        System.out.println("names present: "
                + Arrays.stream(m.getParameters()).allMatch(Parameter::isNamePresent));

        Method fail = Service.class.getDeclaredMethod("fail", IOException.class);
        System.out.println("fail raw throws: " + classes(fail.getExceptionTypes()));
        System.out.println("fail generic throws: " + types(fail.getGenericExceptionTypes()));
    }
}
~~~

Biên dịch trong thư mục chứa file bằng **JDK 17 trở lên**. Không thêm `-parameters` ở lệnh đầu để kiểm chứng trường hợp tên tham số **không được lưu**:

~~~bash
javac --release 17 -Xlint:all MethodSignatureDemo.java
java MethodSignatureDemo
~~~

**Stdout chính xác** (đã biên dịch/chạy với lệnh trên):

~~~text
params raw: java.util.List | java.lang.Number[]
params generic: java.util.List<? super T> | T[]
return raw: java.util.List
return generic: java.util.List<? extends T>
throws raw: java.io.IOException | java.lang.Exception
throws generic: java.io.IOException | E
vars: T | E
bound T: java.lang.Number | java.lang.Comparable<T>
bound E: java.lang.Exception
isVarArgs: true
second is GenericArrayType: true
first is ParameterizedType: true
names present: false
fail raw throws: java.io.IOException
fail generic throws: X
~~~

Quan sát những điểm dễ hiểu sai:

1. `getParameterTypes()` đã xóa `List<? super T>` thành `List` và `T[]` thành `Number[]`, còn `getGenericParameterTypes()` giữ chữ ký có wildcard/type variable.
2. `getExceptionTypes()` trả `Exception` cho `E`, trong khi `getGenericExceptionTypes()` trả type variable `E`. Method `fail` tương tự nhưng xóa `X` thành `IOException`.
3. `getTypeParameters()` và `getBounds()` giữ được giới hạn `T extends Number & Comparable<T>`.
4. `isVarArgs()` xác nhận dấu `...` ở nguồn; `getParameterTypes()` chỉ thấy kiểu mảng.
5. `names present: false` vì lệnh `javac` trên **không** sử dụng `-parameters`. Đây là thông tin tên tham số từ class file, **độc lập** với việc chữ ký generic có được giữ lại hay không.

Nếu biên dịch lại với:

~~~bash
javac --release 17 -parameters MethodSignatureDemo.java
java MethodSignatureDemo
~~~

thì dòng `names present` sẽ thành `true` đối với hai tham số của `query`, còn các dòng phân tích kiểu ở trên không thay đổi. Với các công cụ build khác, kết quả này phụ thuộc compiler options của **class file thực sự được chạy**, không phụ thuộc tên hiển thị trong IDE.

## 9. `Parameter` API, tên tham số và annotations

`Method.getParameters()` trả mảng `Parameter[]`; mỗi phần tử chứa thông tin metadata của một formal parameter:

~~~java
for (Parameter parameter : method.getParameters()) {
    String name = parameter.getName();
    boolean realName = parameter.isNamePresent();
    Class<?> erased = parameter.getType();
    Type generic = parameter.getParameterizedType();
    boolean varargsParameter = parameter.isVarArgs();
}
~~~

Đoạn trên là minh họa, cần import `java.lang.reflect.*` và cung cấp `method`. Các API liên quan:

- `Parameter.getType()` tương ứng góc nhìn `Class<?>`; `getParameterizedType()` tương ứng góc nhìn `Type`.
- `Parameter.getName()` có thể trả tên tổng hợp như `arg0` nếu không có metadata; **không nên coi tên ấy là tên khai báo trong source**. Dùng `isNamePresent()` để biết tên thật có được ghi trong class file không.
- `Parameter.isImplicit()` / `isSynthetic()` phản ánh một số tham số do compiler/qui ước ngôn ngữ tạo ra, ví dụ constructor của inner class không static hoặc enum constructor. Với các bytecode đặc biệt, cần phân biệt formal parameters ở class file và danh sách người viết thấy ở source.
- `Method.getParameterAnnotations()` và `Parameter.getAnnotations()` trả các annotation trên tham số theo quy tắc retention phù hợp. Annotation thuộc **type use** có thể cần API `getAnnotatedParameterTypes()` để thấy vị trí khai báo trên chính kiểu (`List<@SomeAnno String>`).

Metadata của **method signature generic** và **runtime-visible annotations** là hai nguồn thông tin riêng; không suy ra kiểu generic chỉ từ một annotation.

## 10. Những giới hạn và lỗi thường gặp

### 10.1. Tìm Method theo generic argument

**Sai ý tưởng:** muốn lấy `process(List<String>)` nên gọi `getDeclaredMethod` với kiểu `List<String>`. Java không có literal `List<String>.class`. Runtime method lookup dùng erased parameter types, do đó với tham số `List<String>` thường chỉ truyền `List.class`.

Không thể khai báo hai overload chỉ khác nhau ở `List<String>` và `List<Integer>` vì cả hai cùng erasure `List` (name clash). Reflection không khôi phục những overload mà ngôn ngữ không cho phép khai báo.

### 10.2. Ép `Type` thành `Class<?>`

`(Class<?>) method.getGenericParameterTypes()[0]` có thể ném `ClassCastException` nếu phần tử là `ParameterizedType`. Kiểm tra bằng `instanceof` và xử lý đúng biến thể của `Type`. Trong cấu trúc nested generic, có thể cần duyệt đệ quy các type arguments và bounds.

### 10.3. Giả định `throws` là toàn bộ exception thực tế

`getExceptionTypes()` và `getGenericExceptionTypes()` chỉ ghi nhận **throws declaration**. Không có bảo đảm method sẽ ném mọi exception đó, cũng không bảo đảm nó không ném unchecked exception khác. Reflection `Method.invoke` còn có lớp exception bọc `InvocationTargetException`.

### 10.4. Nhầm `TypeVariable` với kiểu đã được giải quyết

`T extends Number` không có nghĩa Reflection luôn biết `T` cụ thể là `Integer`. `T` có thể tồn tại trong `Type` metadata mà chưa biết type argument trong ngữ cảnh gọi thực tế. Muốn kiểm tra dữ liệu runtime, vẫn cần ranh giới/validator riêng phù hợp.

### 10.5. Coi `T...` là một danh sách tham số bất kỳ

Ở mức method descriptor, varargs vẫn là **một tham số mảng cuối cùng**. `Method.isVarArgs()` giúp xác định cách biểu diễn trong source, nhưng `getParameterTypes()` trả array class. Reflection invocation cần đối số phù hợp với formal parameter array sau erasure.

### 10.6. Trông chờ tên tham số luôn xuất hiện

`-g` và debug information không thay thế hoàn toàn cho mục đích lấy tên qua `Parameter.isNamePresent()`; dùng `javac -parameters` khi cần public reflection parameter names. Các compiler/build tools có thể phát sinh các method bridge/synthetic; khi quét API, cân nhắc `Method.isBridge()`, `Method.isSynthetic()` và ngữ cảnh class khai báo.

### 10.7. Không xử lý metadata bất thường

Khi generic signature không hợp lệ hoặc tham chiếu kiểu trong metadata không giải quyết được, các API `getGeneric...` có thể ném những lỗi như `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` tùy trường hợp. Đây là vấn đề class file/generic metadata, khác với việc method không tồn tại (`NoSuchMethodException`). Một công cụ introspection xử lý class của bên thứ ba nên báo lỗi có ngữ cảnh, không âm thầm thay thế generic signature sai bằng kiểu đoán.

## 11. Checklist chọn API theo câu hỏi

| Bạn cần trả lời | API thích hợp |
| --- | --- |
| “Method có những formal parameter type nào ở runtime?” | `getParameterTypes()` |
| “Method có `List<? super T>` hay `T[]` trong chữ ký không?” | `getGenericParameterTypes()` |
| “Method khai báo những loại exception nào sau erasure?” | `getExceptionTypes()` |
| “`throws E` gắn với type variable nào?” | `getGenericExceptionTypes()` + `TypeVariable.getBounds()` |
| “Method khai báo `T, E` với giới hạn nào?” | `getTypeParameters()` |
| “Tên formal parameter có thật được giữ trong class file không?” | `getParameters()` + `isNamePresent()` |
| “Có phải tham số cuối được khai báo `...`?” | `isVarArgs()` |
| “Kiểu trả về có wildcard hoặc generic arguments?” | `getGenericReturnType()` |

Khi xây dựng một công cụ reflection cho method, quy trình an toàn là: **xác định `Method` bằng erased parameter types → đọc metadata thô `Class<?>[]` để hiểu descriptor → đọc các mảng `Type[]` để hiểu generic signature → phân loại từng `Type` và phân giải type variable trong đúng ngữ cảnh khai báo**. Khi hiển thị báo cáo, nói rõ giá trị nào là *erasure* và giá trị nào là *generic declaration*.

### Tài liệu chuẩn

- [Java SE 21 — `java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): `getParameterTypes`, `getGenericParameterTypes`, `getExceptionTypes`, `getGenericExceptionTypes`, `getTypeParameters`.
- [Java SE 21 — `java.lang.reflect.Type`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Type.html), [`ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html), [`TypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html), [`GenericArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericArrayType.html), [`WildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html).
- [Java SE 21 — `java.lang.reflect.Parameter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html).
- [Java Language Specification `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6) và [`8.4 — Method Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4).