# `ParameterizedType` và `getActualTypeArguments()` trong Java Reflection

Java Reflection không chỉ đọc được tên của một class. Khi **chữ ký generic** được lưu trong class file, Reflection còn có thể mô tả những kiểu được khai báo như `List<String>`, `Map<String, List<? extends Number>>`, hoặc `Box<Integer>` qua API `java.lang.reflect.Type`. Một dạng đặc biệt quan trọng là **`ParameterizedType`**: đại diện cho việc sử dụng một *generic type* với các *type arguments* cụ thể trong một chữ ký.

Ví dụ:

~~~java
Map<String, List<Integer>> values;
~~~

`Map` là **generic type được khai báo**, còn `String` và `List<Integer>` là **actual type arguments** trong lần sử dụng đó. Lời gọi:

~~~java
Type signature = field.getGenericType();
ParameterizedType map = (ParameterizedType) signature;
Type[] arguments = map.getActualTypeArguments();
~~~

cho phép đọc cấu trúc trên. `arguments[0]` là `String.class`; `arguments[1]` là **một `ParameterizedType` khác**, biểu diễn `List<Integer>`. **Không thể luôn ép phần tử của mảng `Type[]` thành `Class<?>`.**

Bài học tập trung vào **cách lấy `ParameterizedType`, ba phương thức chính (`getRawType`, `getActualTypeArguments`, `getOwnerType`), cách xử lý các dạng `Type` lồng nhau, owner của nested class, generic superclass/interface và giới hạn do type erasure**.

## 1. Phân biệt khai báo generic và một lần sử dụng kiểu có đối số

Xét khai báo:

~~~java
class Box<T> {
    T value;
}
~~~

`Box<T>` khai báo **type variable** tên `T`. Một nơi sử dụng có thể viết:

~~~java
Box<String> names;
Box<Integer> counts;
~~~

Tại đây, `String` và `Integer` là **actual type arguments** trong chữ ký đã khai báo. Khi kiểm tra metadata của hai field bằng `Field.getGenericType()`, ta có thể thu được lần lượt một `ParameterizedType` biểu diễn `Box<String>` và một `ParameterizedType` biểu diễn `Box<Integer>`.

Nhưng hai object được khởi tạo từ `new Box<String>()` và `new Box<Integer>()` đều có **runtime class** là `Box.class`. Vì **type erasure**, thông tin đối số kiểu của *lần khởi tạo object* nói chung không nằm trên object để có thể truy vấn trực tiếp bằng `object.getClass()`.

Phân biệt hai câu hỏi:

- **“Field/method/superclass này đã được *khai báo* với type arguments nào?”** → Reflection generic metadata, thường có `ParameterizedType`.
- **“Object `new ArrayList<String>()` đang chứa những phần tử kiểu nào, hay trước đây được tạo với `String`?”** → Không thể khẳng định chỉ bằng `object.getClass()` và `ParameterizedType`; phải có hợp đồng kiểu khác hoặc kiểm tra dữ liệu.

## 2. Nhận diện đối số bên trong `ParameterizedType`

Một `ParameterizedType` chứa `Type[]`, không phải `Class<?>[]`. Ví dụ `Map<String, List<? extends Number>>` có argument thứ nhất là `Class` (`String`), argument thứ hai là `ParameterizedType` (`List<? extends Number>`); bên trong `List` lại là `WildcardType`. Nếu argument là `T` hoặc `T[]`, nó có thể là `TypeVariable` hoặc `GenericArrayType`. Vì vậy việc đọc đối số của `ParameterizedType` phải giữ nguyên cấu trúc `Type` và kiểm tra `instanceof` ở từng cấp. Sơ đồ ở bài mở đầu giới thiệu đầy đủ năm dạng `Type`; ở đây trọng tâm là đường đi qua `getActualTypeArguments()`.

## 3. Tìm `ParameterizedType` từ Field, Method và quan hệ kế thừa

Các API cần nhớ:

| Vị trí chữ ký | API lấy generic metadata | Ví dụ |
| --- | --- | --- |
| Field | `Field.getGenericType()` | `Map<String, Long> mapping` |
| Tham số method | `Method.getGenericParameterTypes()` | `void save(List<String> rows)` |
| Kiểu trả về method | `Method.getGenericReturnType()` | `List<Integer> read()` |
| Superclass trực tiếp | `Class.getGenericSuperclass()` | `class StringBox extends Box<String>` |
| Interface trực tiếp | `Class.getGenericInterfaces()` | `class Repo implements Repository<User>` |
| Tham số constructor | `Constructor.getGenericParameterTypes()` | `new Holder(List<String> values)` |

Lưu ý **`getGenericType()` khác `getType()`**:

~~~java
Field field = Holder.class.getDeclaredField("records");

Class<?> erased = field.getType(); // Map.class
Type declared = field.getGenericType(); // Map<String, List<? extends Number>>
~~~

Đây là đoạn minh họa (cần class `Holder` có field `records`, import `java.lang.reflect.*` và xử lý `NoSuchFieldException`). `getType()` trả một `Class<?>` đại diện cho kiểu sau erasure; `getGenericType()` có thể trả `ParameterizedType`.

Với method, `getParameterTypes()` và `getReturnType()` cũng cho thông tin đã erasure; còn `getGenericParameterTypes()` và `getGenericReturnType()` giữ phần chữ ký generic nếu metadata hiện diện.

**Không phải kết quả nào của các API `getGeneric...` cũng là `ParameterizedType`**. Với field khai báo `List raw;`, `getGenericType()` trả `Class`. Với field `T data;` trong generic class, kết quả có thể là `TypeVariable`. Luôn kiểm tra biến thể.

## 4. Ba API chính của `ParameterizedType`

`ParameterizedType` có ba phương thức trọng tâm:

~~~java
Type rawType = parameterized.getRawType();
Type[] args = parameterized.getActualTypeArguments();
Type ownerType = parameterized.getOwnerType();
~~~

### 4.1. `getRawType()`

Trả về `Type` đại diện cho **generic type** mà ta đang truyền actual type arguments. Với `List<String>`, raw type thường là `List.class`; với `Map<String, Integer>` là `Map.class`.

Ví dụ:

~~~java
Type raw = map.getRawType();
if (raw instanceof Class<?> rawClass) {
    System.out.println(rawClass.getName()); // java.util.Map
}
~~~

Trong các trường hợp Java Reflection thông thường, raw type là `Class<?>`. API vẫn khai báo trả `Type`, nên code thư viện tổng quát nên kiểm tra biến thể trước khi ép kiểu. `getRawType()` **không trả type argument đầu tiên** và không đưa generic type argument thành một runtime class mới.

### 4.2. `getActualTypeArguments()`

Trả về một mảng **`Type[]`** biểu diễn các type arguments của **phần khai báo parameterized type hiện tại** theo thứ tự nguồn:

~~~java
Type[] arguments = map.getActualTypeArguments();
Type key = arguments[0];
Type value = arguments[1];
~~~

Với `Map<String, List<? extends Number>>`:

- `arguments[0]` biểu diễn `String`, tức `Class<String>`.
- `arguments[1]` biểu diễn `List<? extends Number>`, tức `ParameterizedType`.
- Từ `arguments[1]`, lấy tiếp `getActualTypeArguments()[0]` sẽ gặp `WildcardType`.

**Số type arguments không phải số field, method hay số lần tạo object.** Thông thường nó tương ứng với type parameters ở chính thành viên generic đang được parameterize. Có trường hợp nested type *không tự khai báo type parameters*, nhưng owner của nó là parameterized: `getActualTypeArguments()` của nested type có thể là **mảng rỗng**, trong khi `getOwnerType()` vẫn chứa thông tin kiểu của owner.

Mảng `Type[]` này mô tả metadata; **nó không cam kết `arguments[i] instanceof Class`**. Để xử lý kiểu phức tạp, cần phân loại `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType` và `GenericArrayType`.

### 4.3. `getOwnerType()`

Cho biết **type sở hữu** (*owner*) nếu parameterized type là kiểu lồng nhau. Ví dụ:

~~~java
class Outer<X> {
    class Inner<Y> { }
}

Outer<String>.Inner<Integer> pair;
~~~

Với `pair`:

- `getRawType()` mô tả lớp `Inner`.
- `getActualTypeArguments()` của `Inner` chứa `Integer`.
- `getOwnerType()` mô tả `Outer<String>` — đây cũng là một `ParameterizedType`, có raw type `Outer` và actual argument `String`.

`getOwnerType()` **có thể trả `null`** đối với kiểu không có owner, chẳng hạn `List<String>`, `Map<K,V>` top-level. Ngược lại, không nên giả định owner luôn là `Class<?>`: owner cũng có thể chứa type arguments và lại là `ParameterizedType`. Với member class static, quan hệ owner có ngữ nghĩa khác với inner class không static; không suy từ owner rằng luôn tồn tại enclosing instance.

## 5. Đọc nested `ParameterizedType` và wildcard

Giả sử field:

~~~java
Map<String, List<? extends Number>> records;
~~~

Truy cập lớp ngoài rồi lớp trong:

~~~java
Type type = Holder.class.getDeclaredField("records").getGenericType();

if (!(type instanceof ParameterizedType map)) {
    throw new IllegalStateException("records is not parameterized");
}

Type[] args = map.getActualTypeArguments();
Type keyType = args[0]; // String.class
Type listType = args[1]; // List<? extends Number>

if (listType instanceof ParameterizedType list) {
    Type itemType = list.getActualTypeArguments()[0];
    if (itemType instanceof WildcardType wildcard) {
        Type[] upper = wildcard.getUpperBounds();
        Type[] lower = wildcard.getLowerBounds();
        // Ở đây upper chứa Number, lower rỗng.
    }
}
~~~

Đây là đoạn minh họa (cần `Holder.records` tương ứng, `import java.lang.reflect.*`, xử lý exception tra field). Sơ đồ:

~~~text
Map
├─ String
└─ List
   └─ ? extends Number
~~~

### Hai dạng wildcard quan trọng

| Chữ ký | Metadata cần đọc | Ý nghĩa |
| --- | --- | --- |
| `List<? extends Number>` | `WildcardType.getUpperBounds()` → `Number`; lower bounds rỗng | Phần tử có một upper bound là `Number` |
| `List<? super Integer>` | `getLowerBounds()` → `Integer`; upper bounds chứa `Object` | Wildcard có lower bound `Integer` |

Java Reflection phản ánh **giới hạn khai báo**, không chứng minh nội dung runtime của mọi phần tử của `List`. Với wildcard không có upper bound tường minh (hoặc dạng `? super ...`), `getUpperBounds()` thường trả `Object`.

Một wildcard có thể nằm sâu trong một parameterized argument, trong array hoặc trong superclass generic. Nếu viết một trình formatter/validator tổng quát, xử lý `Type` như một **cây đệ quy** thay vì chỉ một tầng `getActualTypeArguments()`.

## 6. `TypeVariable` và `GenericArrayType` không phải `ParameterizedType`

### Type variable

Ví dụ:

~~~java
class Bucket<T extends Number> {
    T number;
}
~~~

Với `Bucket.class.getDeclaredField("number").getGenericType()`, ta nhận một `TypeVariable<?>` đại diện cho `T`. Nó khai báo:

- `getName()`: tên `T`.
- `getBounds()`: các upper bounds; ở đây là `Number`.
- `getGenericDeclaration()`: class, method hoặc constructor khai báo biến kiểu đó.

`TypeVariable` **khác** actual type argument `Integer` trong field `Bucket<Integer> bucket;`. Nếu đang đọc một method kế thừa dùng type variable từ generic superclass, cần phân giải mapping từ superclass/interface cụ thể nếu muốn biết `T` tương ứng kiểu nào trong ngữ cảnh class con.

### Generic array

Java cho phép **khai báo tham chiếu** tới array có generic component, ví dụ:

~~~java
List<String>[] buckets;
~~~

Khi đọc `Field.getGenericType()` của field đó, kết quả có thể là `GenericArrayType`, với:

~~~java
Type component = ((GenericArrayType) type).getGenericComponentType();
// component mô tả List<String> và có thể là ParameterizedType
~~~

Điều này **không đồng nghĩa** Java cho phép tạo trực tiếp `new List<String>[10]`. Generic array creation với type component không reifiable bị compiler từ chối. Trong thực tế, nên ưu tiên `List<List<String>>` hoặc một cấu trúc phù hợp, tránh unchecked array cast khi không thật sự cần.

Ngược lại, `String[]` là một array class reifiable; `String[].class` là `Class<?>`. Vì thế parser không được xem **mọi array** là `GenericArrayType`.

## 7. Ví dụ hoàn chỉnh Java 17+: inspect generic type arguments

Tạo file **`ParameterizedTypeDemo.java`** trong một thư mục riêng và nhập toàn bộ chương trình sau. Nó kiểm chứng field lồng nhau, wildcard upper/lower bounds, generic array, owner type của inner class, generic superclass, raw declaration và chữ ký method.

~~~java
import java.lang.reflect.*;
import java.util.*;

public class ParameterizedTypeDemo {
    static class Box<T> { }
    static class StringBox extends Box<String> { }

    static class Outer<X> {
        class Inner<Y> { }
    }

    static class Holder {
        Map<String, List<? extends Number>> records;
        List<? super Integer> sink;
        List<String>[] buckets;
        Outer<String>.Inner<Integer> pair;
        @SuppressWarnings("rawtypes")
        List raw;
    }

    static class Service {
        public Map<String, Integer> convert(List<? extends Number> input) {
            return Collections.emptyMap();
        }
    }

    public static void main(String[] args) throws Exception {
        Field records = Holder.class.getDeclaredField("records");
        System.out.println("erased records: " + records.getType().getTypeName());
        ParameterizedType map = (ParameterizedType) records.getGenericType();
        System.out.println("map raw: " + map.getRawType().getTypeName());
        System.out.println("map arguments: " + map.getActualTypeArguments().length);
        System.out.println("key: " + map.getActualTypeArguments()[0].getTypeName());
        ParameterizedType values = (ParameterizedType) map.getActualTypeArguments()[1];
        System.out.println("value raw: " + values.getRawType().getTypeName());
        WildcardType wildcard = (WildcardType) values.getActualTypeArguments()[0];
        System.out.println("value upper: " + wildcard.getUpperBounds()[0].getTypeName());
        System.out.println("value lower count: " + wildcard.getLowerBounds().length);
        ParameterizedType sink = (ParameterizedType) Holder.class.getDeclaredField("sink").getGenericType();
        WildcardType lower = (WildcardType) sink.getActualTypeArguments()[0];
        System.out.println("sink lower: " + lower.getLowerBounds()[0].getTypeName());
        System.out.println("sink upper: " + lower.getUpperBounds()[0].getTypeName());

        Type buckets = Holder.class.getDeclaredField("buckets").getGenericType();
        System.out.println("buckets generic array: " + (buckets instanceof GenericArrayType));
        Type component = ((GenericArrayType) buckets).getGenericComponentType();
        System.out.println("buckets component: " + component.getTypeName());

        ParameterizedType pair = (ParameterizedType) Holder.class.getDeclaredField("pair").getGenericType();
        System.out.println("pair raw simple: " + ((Class<?>) pair.getRawType()).getSimpleName());
        System.out.println("pair argument: " + pair.getActualTypeArguments()[0].getTypeName());
        ParameterizedType owner = (ParameterizedType) pair.getOwnerType();
        System.out.println("owner raw simple: " + ((Class<?>) owner.getRawType()).getSimpleName());
        System.out.println("owner argument: " + owner.getActualTypeArguments()[0].getTypeName());

        ParameterizedType base = (ParameterizedType) StringBox.class.getGenericSuperclass();
        System.out.println("base raw simple: " + ((Class<?>) base.getRawType()).getSimpleName());
        System.out.println("base argument: " + base.getActualTypeArguments()[0].getTypeName());

        Type raw = Holder.class.getDeclaredField("raw").getGenericType();
        System.out.println("raw list is Class: " + (raw instanceof Class<?>));

        Method convert = Service.class.getDeclaredMethod("convert", List.class);
        System.out.println("method arg: " + convert.getGenericParameterTypes()[0].getTypeName());
        System.out.println("method return: " + convert.getGenericReturnType().getTypeName());
    }
}
~~~

Biên dịch và chạy bằng Java 17 hoặc cao hơn:

~~~bash
javac --release 17 -Xlint:all ParameterizedTypeDemo.java
java ParameterizedTypeDemo
~~~

**Stdout chính xác** từ lần biên dịch/chạy đã kiểm chứng:

~~~text
erased records: java.util.Map
map raw: java.util.Map
map arguments: 2
key: java.lang.String
value raw: java.util.List
value upper: java.lang.Number
value lower count: 0
sink lower: java.lang.Integer
sink upper: java.lang.Object
buckets generic array: true
buckets component: java.util.List<java.lang.String>
pair raw simple: Inner
pair argument: java.lang.Integer
owner raw simple: Outer
owner argument: java.lang.String
base raw simple: Box
base argument: java.lang.String
raw list is Class: true
method arg: java.util.List<? extends java.lang.Number>
method return: java.util.Map<java.lang.String, java.lang.Integer>
~~~

Giải thích phần output:

1. `records.getType()` chỉ thấy `Map.class`, còn `getGenericType()` có `Map<String, List<? extends Number>>`, gồm **hai actual arguments**.
2. Argument thứ hai của `Map` lại là `ParameterizedType List<...>`; wildcard argument bên trong có upper bound `Number`.
3. `sink` chứa wildcard `? super Integer` nên lower bound là `Integer` và upper bound là `Object`.
4. `buckets` chứa generic array, với generic component `List<String>`. Việc khai báo field này vẫn biên dịch, dù không thể `new List<String>[n]` trực tiếp.
5. `pair` là member `Inner<Integer>` được sở hữu bởi `Outer<String>`; `getOwnerType()` giữ thông tin `String` của outer class.
6. `StringBox extends Box<String>` cho thấy actual type argument trong *generic superclass*. Đây là metadata của quan hệ kế thừa, **không phải type argument đoán từ object bất kỳ**.
7. Field khai báo raw `List` trả `Class`, chứng minh không nên cast mọi `Type` thành `ParameterizedType`.
8. Method `convert` cho ví dụ `getGenericParameterTypes()` và `getGenericReturnType()` với signature generic.

Chương trình không phụ thuộc thứ tự `getDeclaredFields()` nên kết quả dễ tái hiện: từng field được tìm bằng tên tường minh.

## 8. Kế thừa, generic interface và phân giải type variable

Không phải lúc nào thông tin type argument nằm ngay trong field. Ví dụ:

~~~java
interface Repository<T> { }

class UserRepository implements Repository<String> { }
~~~

Đọc:

~~~java
Type[] interfaces = UserRepository.class.getGenericInterfaces();
ParameterizedType repository = (ParameterizedType) interfaces[0];
Type argument = repository.getActualTypeArguments()[0]; // String.class
~~~

Đây là đoạn minh họa; cần đặt trong class/phương thức với import `java.lang.reflect.*`. `getGenericInterfaces()` mô tả generic superinterfaces khai báo trực tiếp; nếu một lớp con chỉ kế thừa interface gián tiếp, cần duyệt cây class/interface phù hợp.

Một trường hợp phức tạp hơn:

~~~java
class Parent<T> {
    T value;
}

class Child extends Parent<String> { }
~~~

`Parent.class.getDeclaredField("value").getGenericType()` vẫn là **`TypeVariable T`**, bởi field được khai báo trong `Parent<T>`. Trong khi đó, `Child.class.getGenericSuperclass()` trả `ParameterizedType Parent<String>`.

Muốn suy ra field `value` có type argument `String` trong **ngữ cảnh `Child`**, bạn phải xây dựng mapping `T → String` rồi áp vào chữ ký field; API `Field.getGenericType()` không tự làm phép thay thế đó.

Điều này đặc biệt quan trọng ở framework ORM, serializer hoặc dependency injection: nếu chỉ đọc `Field.getGenericType()` rồi luôn ép kết quả thành `Class<?>`, parser sẽ sai với subclass generic, wildcard hoặc nested types.

## 9. Phạm vi thông tin có thể kết luận

`ParameterizedType` phản ánh **chữ ký generic tại vị trí khai báo**, chẳng hạn `Repository<User>` ở field hoặc `Child extends Parent<String>` ở superclass. Nó không xác định kiểu phần tử của một đối tượng `new ArrayList<String>()` thông thường: `new ArrayList<Integer>().getClass()` và `new ArrayList<String>().getClass()` đều cho `ArrayList.class`.

Muốn chuyển `T` của `Parent<T>` thành `String` trong ngữ cảnh `Child`, công cụ phải đọc cạnh `Child extends Parent<String>`, ánh xạ biến kiểu và thay vào declaration. Nếu cần truyền `List<String>` vào serializer, bên gọi có thể giữ `Type` từ field hoặc type token; kỹ thuật type token phụ thuộc vào chữ ký superclass của một subclass khai báo rõ kiểu. Trong mọi trường hợp, metadata không tự kiểm chứng dữ liệu runtime. Bài cuối chương phân tích erasure, class-file `Signature` và thử nghiệm Reflection invocation đầy đủ.

## 10. Kiểm tra cấu trúc trước khi xử lý

Khi đọc một field/method/supertype, xác nhận `type instanceof ParameterizedType p` trước khi gọi ba phương thức của nó. Duyệt từng `Type` từ `p.getActualTypeArguments()`; nếu đối số cũng là `ParameterizedType`, lặp lại theo chiều sâu, nếu là `WildcardType` thì đọc upper/lower bounds, nếu là `TypeVariable` thì xem generic declaration/bounds, nếu là `GenericArrayType` thì đọc generic component. **Duyệt cả `p.getOwnerType()` khi khác null**, vì `Outer<String>.Inner<Integer>` mang `String` ở owner, không ở argument của inner.

Để hiển thị có thể dùng `getTypeName()`; với resolver/cache, phải giữ cấu trúc `Type` chứ không tách chuỗi. Bounds tự tham chiếu như `T extends Comparable<T>` cần tập node đã thăm để tránh đệ quy vô hạn. Nếu signature trong bytecode thiếu hoặc sai, các API generic có thể báo `TypeNotPresentException`, `MalformedParameterizedTypeException` hay `GenericSignatureFormatError`: thông báo lỗi metadata thay vì tự tạo đối số kiểu.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Cast mọi `field.getGenericType()` thành `ParameterizedType` | Field có thể là raw `List`, `T`, `String` hoặc array | Kiểm tra `instanceof` trước |
| Cast mọi `getActualTypeArguments()[i]` thành `Class<?>` | Argument có thể là wildcard, type variable hoặc parameterized type lồng nhau | Xử lý toàn bộ họ `Type` |
| Nhầm raw type là kiểu argument đầu tiên | `getRawType()` trả `Map`, không trả `String` | Lấy args qua `getActualTypeArguments()` |
| Đọc một tầng `Map` rồi kết luận value là `List.class` | `List<? extends Number>` chứa metadata sâu hơn | Duyệt cây nested parameterized arguments |
| Mặc định `getOwnerType() == null` | Member class có owner, có thể là parameterized owner | Xử lý owner khi có |
| Hiểu `List<String>[]` là một `Class<List<String>[]>` | Generic component không reifiable | Nhận diện `GenericArrayType` |
| Dùng `getClass()` của `ArrayList<String>` để lấy `String` | Type erasure không giữ tham số kiểu của instance | Dùng chữ ký khai báo hoặc type token được truyền rõ |
| Đọc field `T` ở parent rồi mong thấy `String` của child | `Field` gắn với generic declaration `Parent<T>` | Giải mapping `T → String` từ `Child extends Parent<String>` |
| So sánh `Type.getTypeName()` bằng chuỗi để phân loại | Kiểu có cấu trúc và owner/bounds lồng nhau | Dùng `instanceof` và API của từng subtype |
| Tin rằng actual type arguments tự validate object collection | Generic metadata không bảo đảm trạng thái dữ liệu runtime | Kiểm tra dữ liệu/hợp đồng ở boundary riêng |

## 12. Khi nào nên dùng `ParameterizedType`?

- **Serializer và JSON mapper:** đọc `Map<String, List<Item>>` trong khai báo để định hướng xử lý cấu trúc object, phối hợp với logic kiểm tra dữ liệu riêng.
- **Dependency injection / framework registration:** nhận dạng injection point như `Repository<User>` và phân biệt các specialization dựa trên generic metadata.
- **Tài liệu hóa API và schema:** trình bày đúng tham số, return type hoặc superclass generic, thay vì chỉ dùng raw `Map` hay `List`.
- **Công cụ static/runtime inspection:** phát hiện khai báo raw type, wildcard bounds, nested generic argument và owner type trong chữ ký.
- **Generic type resolver:** theo dõi quan hệ `Child extends Parent<String>` để thay thế type variable `T` trong ngữ cảnh cụ thể.

**Quy tắc ghi nhớ:** `getRawType()` cho biết *generic type gốc*; `getActualTypeArguments()` cho biết *các đối số kiểu ở lớp đang xét*; `getOwnerType()` cho biết *kiểu sở hữu nếu là nested type*. Mỗi actual argument lại là **`Type`**, nên phải phân tích theo cấu trúc — và mọi thông tin đó vẫn bị giới hạn bởi **type erasure** khi muốn suy luận về một object runtime.

### Tài liệu chuẩn

- [Java SE 21 — `java.lang.reflect.ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html): `getRawType`, `getActualTypeArguments`, `getOwnerType`.
- [Java SE 21 — `Type`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Type.html), [`WildcardType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html), [`GenericArrayType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericArrayType.html), [`TypeVariable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html).
- [Java SE 21 — `Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html) và [`Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html) cho các API đọc generic signatures.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6) và [§4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.5).
