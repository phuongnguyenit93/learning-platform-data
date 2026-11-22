# Lưu kiểu lồng nhau qua lớp con và mẫu Type Token trong Java Generics

## 1. Bài toán: Làm sao mô tả `List<Map<String, Integer>>` khi chạy?

Giả sử một API cần biết **toàn bộ kiểu của dữ liệu** để đọc JSON, kiểm tra schema, ánh xạ dữ liệu hoặc tạo một adapter:

```java
List<Map<String, Integer>> records;
```

Kiểu trên có nhiều cấp:

- Cấp ngoài là `List`.
- Phần tử của `List` là `Map<String, Integer>`.
- Key của `Map` là `String`.
- Value của `Map` là `Integer`.

Nếu chỉ truyền:

```java
List.class
```

thì thông tin `Map<String, Integer>` **không có trong đối tượng `Class` ấy**. Java cũng không có class literal hợp lệ như:

```java
// Không hợp lệ:
// List<Map<String, Integer>>.class
```

**Super type token** (thường gọi ngắn là *type token*) là một kỹ thuật lưu mô tả generic type bằng cách khai báo **một lớp con có superclass được tham số hóa bằng kiểu cụ thể** rồi đọc phần *generic signature* của superclass thông qua Reflection.

Ví dụ cách sử dụng mong muốn:

```java
TypeRef<List<Map<String, Integer>>> token =
        new TypeRef<List<Map<String, Integer>>>() {};

Type type = token.type();
System.out.println(type.getTypeName());
```

Kết quả Java 17:

```text
java.util.List<java.util.Map<java.lang.String, java.lang.Integer>>
```

Chú ý cặp ngoặc nhọn `{}` cuối `new TypeRef<...>() {}`. Nó tạo một **anonymous subclass**. Chính subclass mang khai báo superclass có kiểu tham số hóa, cho phép Reflection đọc lại chuỗi cấu trúc `List<Map<String,Integer>>` đã viết trong source.

Bài này tập trung vào kỹ thuật lưu kiểu lồng nhau qua superclass, cách duyệt `Type`, những hạn chế do type erasure, cách xử lý `TypeVariable`/wildcard/generic array, cùng nguyên tắc dùng type token đúng và an toàn trong API thực tế. Toàn bộ ví dụ chính dùng Java 17.

## 2. Phân biệt kiểu tĩnh, class runtime và metadata generic

Hãy xem hai biến:

```java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
```

Tại source, compiler coi hai biến có **parameterized types khác nhau** và bảo vệ phép thêm/đọc phần tử theo kiểu đó.

Nhưng cả hai object được khởi tạo bằng `new ArrayList<>()`; tại runtime:

```java
System.out.println(
        names.getClass() == numbers.getClass()); // true
```

Không có một runtime class riêng `ArrayList<String>` và một class khác `ArrayList<Integer>`. Đó là đặc điểm của **type erasure** trong Java Generics.

Tuy vậy, nói “Java xóa hết mọi thông tin generic” cũng không chính xác. Compiler có thể ghi **thông tin chữ ký generic của khai báo** vào class file, chẳng hạn:

```java
class StringList extends ArrayList<String> {
}
```

Lớp `StringList` khai báo cụ thể superclass là `ArrayList<String>`. Reflection có thể đọc metadata ấy qua `StringList.class.getGenericSuperclass()`.

Điểm phân biệt:

| Nơi tìm thông tin | Câu hỏi được trả lời | Giới hạn |
| --- | --- | --- |
| Kiểu tĩnh `List<String>` | Compiler cho phép những thao tác nào? | Không tạo runtime specialization riêng. |
| `object.getClass()` | Object có runtime class gì? | Thường không biết type arguments của instance. |
| `SomeClass.class.getGenericSuperclass()` | Class *đã khai báo* generic superclass như thế nào? | Đọc khai báo, không xác nhận dữ liệu object. |
| `Field.getGenericType()` | Field được khai báo có generic type gì? | Không kiểm tra value hiện đang gán vào field. |
| `Method.getGenericReturnType()` | Method khai báo return type generic nào? | Không suy luận tự động type argument cụ thể của mỗi lời gọi. |
| Type token qua subclass | Source đã khai báo kiểu tham số hóa nào ở superclass? | Thường chỉ lưu mô tả `Type`, không tự validate object. |

**Bản chất:** type token tận dụng **metadata còn lưu ở declaration**, không đảo ngược phép xóa kiểu để truy ra generic arguments tùy ý từ một object đã tồn tại.

## 3. Các loại `java.lang.reflect.Type` phải biết

`java.lang.reflect.Type` là giao diện biểu diễn kiểu được Reflection sử dụng. Những dạng thường gặp:

| Dạng `Type` | Ví dụ | Dùng khi |
| --- | --- | --- |
| `Class<?>` | `String`, `int`, `String[]` | Kiểu có class object tương ứng. |
| `ParameterizedType` | `List<String>`, `Map<String,Integer>` | Kiểu có generic arguments đã được viết trong declaration. |
| `TypeVariable<?>` | `T`, `E`, `K`, `V` | Declaration còn biến kiểu chưa thay bằng kiểu cụ thể. |
| `WildcardType` | `?`, `? extends Number`, `? super Integer` | Generic argument là wildcard có bounds. |
| `GenericArrayType` | `T[]`, `List<String>[]` | Kiểu mảng có component là kiểu non-reifiable trong mô tả generic. |

Từ Java 8, mỗi `Type` có phương thức `getTypeName()` để lấy một biểu diễn tên kiểu phù hợp cho chẩn đoán và hiển thị.

### 3.1. `Class<?>` không đồng nghĩa `Type`

`Class<?>` **là một dạng của `Type`**, nhưng không phải mọi `Type` đều là một `Class<?>`.

```java
Type stringType = String.class; // Class<String> là Type.
```

Trong khi:

```java
Type listType =
        new TypeRef<List<String>>() {}.type();
```

`listType` thường là `ParameterizedType`, **không thể cast thẳng** thành `Class<?>`:

```java
// Có thể ném ClassCastException:
// Class<?> cls = (Class<?>) listType;
```

Một framework làm việc với generic metadata phải phân nhánh theo kiểu thực của đối tượng `Type`, thay vì luôn giả định đó là Class.

### 3.2. `ParameterizedType`

Một `ParameterizedType` cho các thông tin chính:

```java
Type raw = p.getRawType();
Type[] arguments = p.getActualTypeArguments();
Type owner = p.getOwnerType();
```

Với `List<Map<String,Integer>>`:

- `getRawType()` của lớp ngoài là `java.util.List`.
- Mảng arguments của lớp ngoài có **một phần tử**: `Map<String,Integer>`.
- Argument đó tiếp tục là `ParameterizedType`.
- Raw type của argument là `java.util.Map`.
- Hai arguments của Map lần lượt là `String.class`, `Integer.class`.

`getOwnerType()` dành cho quan hệ owner của những member/nested classes, **không** phải type argument của List. Với top-level types như `List` và `Map`, owner thông thường là `null`.

### 3.3. `TypeVariable<?>`

Một type variable như `T` có tên, generic declaration và bounds. Ví dụ:

```java
static <T> void work(T value) {
}
```

`T` không tự trở thành `String.class` khi caller gọi `work("Java")`. Nếu metadata của một anonymous subclass vẫn chứa `T`, type token còn **chưa được giải quyết thành kiểu cụ thể**.

### 3.4. `WildcardType`

Một wildcard `? extends Number` có upper bound `Number`. Một `? super Integer` có lower bound `Integer`.

`WildcardType.getUpperBounds()` và `.getLowerBounds()` giúp một parser/validator xem bound đã khai báo. Chúng không có nghĩa có thể biết chính xác subtype được sử dụng ở từng runtime object.

### 3.5. `GenericArrayType`

`List<String>[]` có thể xuất hiện trong **mô tả kiểu** dù Java không cho `new List<String>[n]` trực tiếp. Reflection dùng `GenericArrayType` để mô tả mảng có component generic non-reifiable, ví dụ `List<String>[]` hoặc `T[]`.

Kỹ thuật type token có thể **lưu mô tả** của kiểu này; lưu metadata không đồng nghĩa được phép tạo object array bằng một cú pháp mà compiler cấm.

## 4. Vì sao anonymous subclass lưu được type arguments?

Giả sử bạn định nghĩa:

```java
abstract class TypeRef<T> {
}
```

Sau đó viết:

```java
TypeRef<List<String>> token =
        new TypeRef<List<String>>() {};
```

Đây **không đơn thuần** là `new TypeRef<List<String>>()`. Do `TypeRef` là abstract, không thể tạo instance trực tiếp. Cú pháp `{}` tạo một anonymous concrete subclass, có thể hình dung gần giống:

```java
final class GeneratedTypeRef extends TypeRef<List<String>> {
}
```

Compiler ghi generic superclass signature của class con như một khai báo:

```text
TypeRef<java.util.List<java.lang.String>>
```

Khi chạy:

```java
Type superType = token.getClass().getGenericSuperclass();
```

Reflection trả mô tả generic superclass của **class anonymous**. Nếu superclass được khai báo bằng type arguments, kết quả là một `ParameterizedType`.

Từ đó bạn có thể lấy argument `List<String>`.

### 4.1. Vai trò chính xác của `{}`

So sánh:

```java
new TypeRef<List<String>>() {};
```

với cách tạo object của một generic class thông thường:

```java
new ArrayList<String>();
```

`new ArrayList<String>()` tạo object `ArrayList` nhưng không định nghĩa thêm một class con có generic superclass signature chứa `String`. Trong khi `new TypeRef<List<String>>() {}` tạo anonymous subclass của TypeRef và **superclass signature** có chứa cấu trúc được chỉ rõ.

Một số cú pháp diamond anonymous class đã được Java hỗ trợ từ Java 9, nhưng để học super type token, ghi **tường minh toàn bộ type arguments** ngay trong `new TypeRef<...>() {}` giúp dễ kiểm tra kiểu mà metadata sẽ lưu.

### 4.2. Đây là kỹ thuật giữ metadata, không phải reification đầy đủ

Reflection đọc thông tin **trong class declaration của anonymous subclass**. JVM không tạo các object `List<String>` có runtime class riêng, cũng không có cơ chế tự động kiểm tra toàn bộ elements của một list vừa được nhận từ mạng hoặc file.

Nói cách khác, **Type token mô tả “kiểu mong đợi”**. Bước kiểm tra hoặc chuyển đổi dữ liệu thực vẫn do library/application thực hiện.

## 5. Xây một `TypeRef<T>` nhỏ, độc lập

Một ví dụ tối thiểu nhưng có kiểm tra rõ ràng:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.Objects;

abstract class TypeRef<T> {
    private final Type type;

    protected TypeRef() {
        Type parent = getClass().getGenericSuperclass();

        if (!(parent instanceof ParameterizedType p)
                || p.getRawType() != TypeRef.class) {
            throw new IllegalStateException(
                    "Use a direct parameterized subclass");
        }

        this.type = Objects.requireNonNull(
                p.getActualTypeArguments()[0]);
    }

    public final Type type() {
        return type;
    }
}
```

Đoạn class trên cần nằm trong một file Java có các imports đã liệt kê. Không chứa logic parse JSON; nó chỉ **đọc và giữ metadata**.

Quy trình trong constructor:

1. `getClass()` lấy runtime class của instance — anonymous subclass hoặc named subclass.
2. `getGenericSuperclass()` đọc kiểu superclass đã khai báo.
3. Pattern `instanceof ParameterizedType p` xác minh metadata superclass có type arguments.
4. `p.getRawType() == TypeRef.class` xác nhận cấu trúc **class con trực tiếp** của `TypeRef` như thiết kế.
5. `getActualTypeArguments()[0]` lấy type argument đầu tiên, có thể là Class, ParameterizedType, TypeVariable hoặc kiểu Type khác.
6. Field `type` lưu mô tả đó để caller hoặc framework sử dụng.

### 5.1. Vì sao constructor `protected`?

Người dùng thiết kế này tạo **subclass**, không tạo instance TypeRef trực tiếp. `protected` thể hiện constructor dành cho subclasses.

Nếu cần không cho class ngoài package kế thừa, API có thể chọn thiết kế khác; ví dụ ở đây ưu tiên đơn giản và dễ kiểm chứng.

### 5.2. Vì sao field `type` là `final`?

Cấu trúc kiểu được đọc một lần khi object được tạo. `final` làm rõ rằng token đại diện cho **một mô tả kiểu cố định**, không phải một holder có thể chuyển từ `List<String>` sang `List<Integer>` sau đó.

Dù `Type` là interface, những implementations do JDK trả từ reflection thể hiện metadata khai báo. Điều đó không có nghĩa mọi implementation `Type` do bên thứ ba tạo đều có tính bất biến/equals/hashCode đúng nếu bạn tự nhận Type từ nguồn khác.

### 5.3. Vì sao kiểm tra `getRawType()`?

Một `ParameterizedType` bất kỳ ở superclass **không đủ** để chứng minh argument đầu tiên chính là `T` của `TypeRef`. Đoạn code này chỉ xử lý trường hợp:

```java
class NamedRef extends TypeRef<List<String>> {
}
```

hoặc anonymous subclass trực tiếp tương đương. Với một lớp trung gian:

```java
class Intermediate<U> extends TypeRef<U> {
}

class Concrete extends Intermediate<List<String>> {
}
```

`Concrete.class.getGenericSuperclass()` là `Intermediate<List<String>>`, không phải `TypeRef<List<String>>`. Ví dụ kiểm tra `getRawType() == TypeRef.class` sẽ từ chối. Đây là **giới hạn có chủ đích của bản `TypeRef` đơn giản**, không phải giới hạn tuyệt đối của mọi type token library.

Một implementation hỗ trợ nhiều tầng kế thừa phải đi dọc superclass/interfaces và **thay thế TypeVariables bằng actual type arguments theo từng tầng**. Chỉ gọi `getGenericSuperclass()` rồi lấy argument `[0]` không giải quyết được bài toán tổng quát đó.

## 6. Ví dụ kiểu lồng nhau `List<Map<String,Integer>>`

Khai báo:

```java
TypeRef<List<Map<String, Integer>>> token =
        new TypeRef<List<Map<String, Integer>>>() {};
```

Đọc:

```java
Type type = token.type();
System.out.println(type.getTypeName());
```

Output:

```text
java.util.List<java.util.Map<java.lang.String, java.lang.Integer>>
```

Phân rã từng cấp:

```java
ParameterizedType outer = (ParameterizedType) type;

Type rawList = outer.getRawType();
Type mapArgument = outer.getActualTypeArguments()[0];

ParameterizedType inner = (ParameterizedType) mapArgument;

Type rawMap = inner.getRawType();
Type key = inner.getActualTypeArguments()[0];
Type value = inner.getActualTypeArguments()[1];
```

Tương ứng:

| Thành phần | Kiểu `Type` được trả | Giá trị mô tả |
| --- | --- | --- |
| `type` | `ParameterizedType` | `List<Map<String,Integer>>` |
| `rawList` | Thường là `Class<?>` | `java.util.List` |
| `mapArgument` | `ParameterizedType` | `Map<String,Integer>` |
| `rawMap` | Thường là `Class<?>` | `java.util.Map` |
| `key` | `Class<?>` | `java.lang.String` |
| `value` | `Class<?>` | `java.lang.Integer` |

Không cần split chuỗi `getTypeName()` theo ký tự `<`, `,`, `>` rồi parse lại. **Hãy dùng cây `Type` thật** với `getRawType()` và `getActualTypeArguments()`; cách này xử lý tốt hơn khi xuất hiện wildcard, owner type hoặc nested arrays.

### 6.1. Vì sao cast sang `ParameterizedType` ở đây hợp lệ?

Vì token được viết với type `List<Map<String,Integer>>`, và bạn kiểm tra/ngầm biết class của `Type` từ mẫu ví dụ. Trong một API nhận **Type bất kỳ**, không được cast vô điều kiện:

```java
Type t = String.class;

// Không an toàn:
// ParameterizedType p = (ParameterizedType) t;
```

`String.class` là `Class`, không phải ParameterizedType. Một helper tổng quát phải dùng `instanceof` để phân nhánh.

### 6.2. `Type.getTypeName()` không phải schema validator

Nó rất hữu ích để log, debug và hiển thị. Tuy nhiên khi framework cần biến JSON thành object, không nên chỉ dựa vào chuỗi này để xác thực toàn bộ cấu trúc. API reflection đã cung cấp các đối tượng loại Type có ý nghĩa rõ hơn chuỗi hiển thị.

## 7. Tạo type token qua named subclass

Không bắt buộc phải dùng anonymous class.

```java
final class StringListRef extends TypeRef<List<String>> {
}
```

Sau đó:

```java
Type type = new StringListRef().type();
```

Kết quả:

```text
java.util.List<java.lang.String>
```

Ưu điểm: đặt tên cho kiểu dùng nhiều lần, dễ tái sử dụng và đặt ở một vị trí chung. Anonymous subclass tiện hơn khi chỉ cần một type token ngay tại call site:

```java
TypeRef<Map<String, List<Integer>>> token =
        new TypeRef<Map<String, List<Integer>>>() {};
```

### 7.1. Không nhầm named subclass với class instance chứa dữ liệu

`StringListRef` **không phải** một `List<String>`. Nó là một đối tượng mô tả kiểu `List<String>`. Viết:

```java
StringListRef token = new StringListRef();
```

không hề tạo một list mới và không chứa các String elements.

Một API parse có thể nhận `token.type()` rồi **dựa trên metadata** để tạo List; đó là công việc của parser, không phải của token.

### 7.2. Dùng constant type token như thế nào?

Nếu một type description không thay đổi, có thể giữ lại token hoặc `Type` theo phạm vi thích hợp, tránh tạo anonymous subclasses không cần thiết ở nhiều call sites.

Tuy vậy không nên tự xây một static cache toàn cục không có giới hạn nếu ứng dụng có nhiều class loaders, plugin classes hoặc dynamic types; quản lý vòng đời cache là trách nhiệm riêng.

## 8. Một type token có thể chứa nhiều dạng Type lồng nhau

### 8.1. Wildcard có bound

```java
TypeRef<List<? extends Number>> token =
        new TypeRef<List<? extends Number>>() {};
```

Cấp ngoài là `ParameterizedType` của List. Argument `? extends Number` là `WildcardType`.

```java
ParameterizedType list =
        (ParameterizedType) token.type();

WildcardType wildcard =
        (WildcardType) list.getActualTypeArguments()[0];

Type upper = wildcard.getUpperBounds()[0];
```

`upper.getTypeName()` cho:

```text
java.lang.Number
```

Điều này chỉ cho biết source đã khai báo upper bound Number. Token không biết liệu object list thực tế chứa Integer, Double hoặc subtype cụ thể nào.

### 8.2. Generic array

```java
TypeRef<List<String>[]> token =
        new TypeRef<List<String>[]>() {};
```

Mô tả `List<String>[]` có thể xuất hiện dưới dạng `GenericArrayType`:

```java
GenericArrayType array =
        (GenericArrayType) token.type();

Type component = array.getGenericComponentType();
```

`component.getTypeName()`:

```text
java.util.List<java.lang.String>
```

Cần phân biệt **mô tả kiểu array** với **khởi tạo array object**:

```java
// Không hợp lệ trong Java:
// new List<String>[3];
```

Đọc/lưu type token không biến biểu thức cấp phát bị cấm thành hợp lệ.

### 8.3. `Class<?>` của kiểu bình thường

```java
TypeRef<String> token =
        new TypeRef<String>() {};
```

Ở ví dụ này `type()` là `Class` cho String:

```java
token.type() == String.class // true trong trường hợp này
```

Không phải mọi token đều chứa ParameterizedType. Một API tổng quát phải chấp nhận cấu trúc `Type` khác nhau.

### 8.4. Kiểu lồng nhau nhiều tầng

Một token có thể mô tả các cấu trúc sâu hơn:

```java
TypeRef<Map<String, List<Map<Integer, String>>>> token =
        new TypeRef<Map<String, List<Map<Integer, String>>>>() {};
```

Cách duyệt vẫn như nhau: đi từ `ParameterizedType` ngoài vào từng `getActualTypeArguments()`, cho đến khi gặp Class, TypeVariable, WildcardType hoặc GenericArrayType.

Không có giới hạn “chỉ hai cấp” trong kỹ thuật này. Giới hạn thực tế là các kiểu Java có thể khai báo hợp lệ, tài nguyên Reflection và năng lực xử lý của framework tiêu thụ Type.

## 9. Vì sao `new TypeRef<List<T>>() {}` chưa đủ để biết `T`?

Đây là **giới hạn quan trọng nhất** khi áp dụng super type token trong generic method.

```java
static <T> Type captureInside(T example) {
    return new TypeRef<List<T>>() {}.type();
}
```

Caller:

```java
Type type = captureInside("hello");
```

Bạn có thể nghĩ token đã biết `T = String`. Nhưng class của anonymous subclass được compiler tạo **từ declaration chung** của method, không tạo specialization riêng theo mỗi invocation.

Kết quả đại diện cho:

```text
java.util.List<T>
```

Argument bên trong là `TypeVariable`, **không phải `String.class`**.

### 9.1. Type erasure vẫn tồn tại

Trong source:

```java
static <T> Type makeToken() {
    return new TypeRef<List<T>>() {}.type();
}
```

type variable `T` được khai báo tại generic method. Metadata có thể giữ **tên và bounds** của T, nhưng không tự thay nó bằng class cụ thể do caller dùng tại runtime.

Thậm chí khi caller viết:

```java
makeToken();
```

ở một vị trí có target type rõ, token tạo bên trong method vẫn không được reify thành một class specialization mới.

### 9.2. Phân biệt “lưu T” với “giải T”

Một type token **có thể lưu** một TypeVariable object. Nhưng lưu tên `T` chưa đủ để biết type argument runtime của lời gọi cụ thể.

Nếu framework cần concrete type, nó phải có **context ánh xạ biến kiểu**, ví dụ một subclass chain cụ thể gắn `T = String`, hoặc caller truyền một `Type`/type token hoàn chỉnh từ nơi biết cấu trúc.

### 9.3. Truyền Type từ caller thay vì tạo token với T bên trong

Thay vì:

```java
static <T> Type wrongExpectation() {
    return new TypeRef<List<T>>() {}.type();
}
```

hãy cung cấp thông tin kiểu cụ thể tại caller:

```java
TypeRef<List<String>> token =
        new TypeRef<List<String>>() {};

// Truyền token.type() vào API nhận Type.
```

Hoặc truyền một `Class<T>`/factory rõ ràng nếu API chỉ cần **class không lồng nhau**. Không nên tin rằng chỉ thấy `<T>` trong method đã đủ phục hồi `T` sau erasure.

## 10. Kế thừa nhiều tầng cần giải type variables theo từng tầng

Xét:

```java
abstract class BaseRef<T> {
}

class Middle<U> extends BaseRef<List<U>> {
}

class Concrete extends Middle<String> {
}
```

Nếu Reflection đọc:

```java
Concrete.class.getGenericSuperclass()
```

kết quả là `Middle<String>`, không trực tiếp là `BaseRef<List<String>>`.

Nếu đọc tiếp khai báo của:

```java
Middle.class.getGenericSuperclass()
```

thì lại thấy `BaseRef<List<U>>`, với `U` là `TypeVariable` của Middle.

Một resolver tổng quát phải kết hợp:

```text
Concrete -> Middle<String>
Middle<U> -> BaseRef<List<U>>
U -> String
Suy ra: BaseRef<List<String>>
```

### 10.1. Vì sao `getGenericSuperclass()` một lần không đủ?

Nó chỉ trả **generic superclass trực tiếp** của class đang hỏi. Khi có nhiều tầng, type arguments có thể nằm ở một class, còn type variable cần thay nằm ở class khác.

Nếu một library tuyên bố hỗ trợ inheritance nhiều cấp, cần xem nó giải `TypeVariable` theo context, xử lý interfaces, owner types, bounds, generic arrays và wildcards ra sao.

### 10.2. Bản `TypeRef` ở đây cố tình chỉ hỗ trợ một tầng

Trong chương trình chạy đầy đủ:

```java
static class Intermediate<U> extends TypeRef<U> {
}

static final class TooDeep
        extends Intermediate<List<String>> {
}
```

Khi tạo `new TooDeep()`, constructor của `TypeRef` lấy direct superclass của `TooDeep`, tức `Intermediate<List<String>>`. Raw type không phải `TypeRef.class`, nên nó chủ động ném:

```text
Use a direct parameterized subclass
```

Đây là cách từ chối **thay vì lưu nhầm** một argument rồi tuyên bố đã giải quyết đúng kiểu. Nếu cần multi-level capture, hãy thay implementation bằng một generic type resolver thật sự, không gỡ bỏ check cho qua.

## 11. Type token khác `Class<T>` token

`Class<T>` rất hữu ích khi kiểu đích là một class có thể kiểm tra runtime:

```java
static <T> T checkedCast(Object value, Class<T> type) {
    return type.cast(value);
}
```

Caller:

```java
String s = checkedCast("Java", String.class);
```

Nhưng không có cú pháp class literal:

```java
// Không hợp lệ:
// List<String>.class
```

`List.class` chỉ biểu đạt runtime class/interface List, không biểu đạt type argument String.

So sánh:

| Mục đích | `Class<T>` | Super type token chứa `Type` |
| --- | --- | --- |
| Biết class `String` | Phù hợp | Cũng mô tả được |
| Mô tả `List<String>` | Không giữ type argument | Giữ được từ declaration của subclass |
| Mô tả `Map<String,List<Integer>>` | Không đủ | Giữ được toàn bộ cấu trúc khai báo |
| Runtime `isInstance` với class | Có | Type không cung cấp tương đương đầy đủ tự động |
| Tạo object bằng reflection | Có thể tra constructor nhưng có thể thất bại | Cần framework hiểu Type và cách tạo object |
| Kiểm tra mọi phần tử List | Không | Cũng **không tự kiểm tra** |
| Xử lý wildcard và type variable | Không đầy đủ | Có các dạng Type đặc thù để mô tả |

**Type token không thay thế `Class<T>` trong mọi tình huống**. Nếu chỉ cần kiểm tra một runtime class đơn giản, Class token thường đủ và dễ dùng hơn.

## 12. Type token không làm một `List<String>` tự an toàn

Giả sử ai đó xây một list bị nhiễm kiểu qua raw alias:

```java
List raw = new ArrayList();
raw.add(42);

@SuppressWarnings("unchecked")
List<String> claimed = (List<String>) raw;
```

Đây là đoạn **cố ý không an toàn** để minh họa; khi bật lint, raw/unchecked operations có thể bị cảnh báo.

Bạn hoàn toàn có thể tạo type token:

```java
Type token = new TypeRef<List<String>>() {}.type();
```

Nhưng token không khiến list `claimed` chứa String. Khi:

```java
String first = claimed.get(0);
```

runtime vẫn có thể ném `ClassCastException`.

Một thư viện deserialize/convert thật sự phải dùng Type token làm **mô tả kiểu đích**, sau đó thực hiện kiểm tra hoặc chuyển đổi từng phần tử theo chính sách của nó.

### 12.1. `Type` là metadata, validation là một quá trình khác

Với token `List<Map<String,Integer>>`, validator có thể cần:

1. Xác nhận value ngoài là một list hoặc có thể chuyển thành list.
2. Xác nhận từng phần tử list là map.
3. Xác nhận key của từng map là String.
4. Xác nhận value của từng map là Integer, hoặc có quy tắc chuyển từ dữ liệu đầu vào.
5. Xây cấu trúc kết quả có generic contract phù hợp.
6. Xử lý null, phần tử thiếu, số không đúng miền, dữ liệu dư, lỗi và vòng đời object.

**Reflection metadata không tự làm các bước này**. Một parser có thể có chính sách khác nhau: reject dữ liệu sai, cố chuyển số, bỏ field không nhận biết, hay trả lỗi chi tiết.

### 12.2. Không coi `ClassCastException` vắng mặt là chứng minh generic type an toàn

Cast runtime từ một Object sang raw `List` chỉ kiểm tra interface/class ngoài. Nếu bên trong có Integer thay vì String, cast generic unchecked không phát hiện cho tới khi code đọc một phần tử và cần String.

Type token là công cụ cho việc **biết phải kiểm tra gì**, không phải phép kiểm tra tổng quát tự động.

## 13. `Type` metadata từ field và method khác gì type token?

Bạn có thể lấy generic type từ khai báo field:

```java
class Model {
    List<Map<String, Integer>> records;
}
```

Reflection:

```java
Field field = Model.class.getDeclaredField("records");
Type type = field.getGenericType();
```

Nếu field declaration cụ thể, `getGenericType()` cũng trả cấu trúc `ParameterizedType` lồng nhau.

Tương tự:

```java
Method method = SomeClass.class.getDeclaredMethod("find");
Type type = method.getGenericReturnType();
```

Lệnh minh họa này giả định có method `find` không đối số. Method return type có thể là ParameterizedType, Class hoặc TypeVariable tùy declaration.

### 13.1. Khi nào nên dùng field/method reflection?

Nếu schema đã tồn tại ở class/record/method cụ thể, Reflection trực tiếp lên declaration có thể đủ. Không phải luôn cần tạo thêm anonymous subclass.

Type token hữu ích khi **call site muốn mô tả một generic type tùy chọn** mà không có một field/method riêng để làm nguồn metadata:

```java
new TypeRef<List<Map<String, Integer>>>() {}.type()
```

### 13.2. Đừng nhầm type được khai báo với type giá trị hiện tại

Nếu field `List<String> values` bị gán một list sai nội dung qua unchecked code, `Field.getGenericType()` vẫn trả đúng kiểu **đã khai báo**. Nó không biết các element hiện tại trong list. Đây là cùng giới hạn của super type token.

## 14. Equality và khả năng tái sử dụng của type descriptions

Hai anonymous subclasses khác nhau có thể khai báo cùng type:

```java
Type a = new TypeRef<List<String>>() {}.type();
Type b = new TypeRef<List<String>>() {}.type();

System.out.println(a.equals(b)); // true
```

Với Reflection types chuẩn, `ParameterizedType.equals` so sánh tính tương đương cấu trúc: raw type, owner type và các actual type arguments. Hai tokens có thể đến từ **hai anonymous classes khác nhau**, nhưng vẫn mô tả cùng `List<String>`.

Ngược lại:

```java
Type x = new TypeRef<List<String>>() {}.type();
Type y = new TypeRef<List<Integer>>() {}.type();

System.out.println(x.equals(y)); // false
```

### 14.1. Không so class của anonymous token instances

Các anonymous subclasses tại hai vị trí source có thể có **class riêng**. So:

```java
aToken.getClass() == bToken.getClass()
```

không phải phép so sánh hợp lý cho kiểu dữ liệu mà chúng mô tả. Hãy so **`Type` metadata** sau khi capture.

### 14.2. Cache theo `Type` cần chú ý scope

Nếu làm cache mapper/adapter theo `Type`, thường cần key bao gồm cấu trúc generic đầy đủ, không chỉ raw class:

```text
List<String>  != List<Integer>
Map<String,Integer> != Map<String,Long>
```

Tuy nhiên đừng tự giả định mọi Type do bên thứ ba implement đều có `equals`/`hashCode` đúng; nếu tự viết `ParameterizedType` implementation, cần tuân thủ hợp đồng của nó. Cũng lưu ý classloaders khác nhau có thể tạo Class objects không tương đương dù tên class giống nhau.

## 15. Chương trình Java 17 hoàn chỉnh

Tạo tệp **`NestedTypeTokenDemo.java`**:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class NestedTypeTokenDemo {
    static abstract class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)
                    || p.getRawType() != TypeRef.class) {
                throw new IllegalStateException(
                        "Use a direct parameterized subclass");
            }
            type = Objects.requireNonNull(
                    p.getActualTypeArguments()[0]);
        }

        public final Type type() {
            return type;
        }
    }

    static final class NamedRef extends TypeRef<List<String>> {
    }

    static class Intermediate<U> extends TypeRef<U> {
    }

    static final class TooDeep
            extends Intermediate<List<String>> {
    }

    static <T> Type unboundInMethod(T value) {
        return new TypeRef<List<T>>() {}.type();
    }

    static String category(Type type) {
        if (type instanceof ParameterizedType)
            return "ParameterizedType";
        if (type instanceof GenericArrayType)
            return "GenericArrayType";
        if (type instanceof WildcardType)
            return "WildcardType";
        if (type instanceof TypeVariable<?>)
            return "TypeVariable";
        if (type instanceof Class<?>)
            return "Class";
        return "Unknown";
    }

    public static void main(String[] args) {
        TypeRef<List<Map<String, Integer>>> nested =
                new TypeRef<List<Map<String, Integer>>>() {};

        Type type = nested.type();
        System.out.println("nested=" + type.getTypeName());

        ParameterizedType outer = (ParameterizedType) type;
        System.out.println("outer-raw="
                + outer.getRawType().getTypeName());

        Type map = outer.getActualTypeArguments()[0];
        System.out.println("inner-kind=" + category(map));

        ParameterizedType inner = (ParameterizedType) map;
        System.out.println("map-raw="
                + inner.getRawType().getTypeName());
        System.out.println("map-key="
                + inner.getActualTypeArguments()[0].getTypeName());
        System.out.println("map-value="
                + inner.getActualTypeArguments()[1].getTypeName());

        TypeRef<List<String>> a =
                new TypeRef<List<String>>() {};
        TypeRef<List<String>> b =
                new TypeRef<List<String>>() {};
        TypeRef<List<Integer>> c =
                new TypeRef<List<Integer>>() {};

        System.out.println("type-equal="
                + a.type().equals(b.type()));
        System.out.println("type-different="
                + !a.type().equals(c.type()));
        System.out.println("named="
                + new NamedRef().type().getTypeName());

        Type boundType =
                new TypeRef<List<? extends Number>>() {}.type();
        WildcardType wildcard = (WildcardType)
                ((ParameterizedType) boundType)
                .getActualTypeArguments()[0];

        System.out.println("wildcard-kind="
                + category(wildcard));
        System.out.println("wildcard-upper="
                + wildcard.getUpperBounds()[0].getTypeName());

        Type arrayType =
                new TypeRef<List<String>[]>() {}.type();
        GenericArrayType ga = (GenericArrayType) arrayType;
        System.out.println("array-kind=" + category(arrayType));
        System.out.println("array-component="
                + ga.getGenericComponentType().getTypeName());

        System.out.println("simple-kind="
                + category(new TypeRef<String>() {}.type()));

        Type generic = unboundInMethod("actual String");
        Type nestedArgument = ((ParameterizedType) generic)
                .getActualTypeArguments()[0];

        System.out.println("method-capture="
                + generic.getTypeName());
        System.out.println("type-variable="
                + category(nestedArgument));

        List<String> strings = new ArrayList<>();
        List<Integer> integers = new ArrayList<>();
        System.out.println("same-runtime-class="
                + (strings.getClass() == integers.getClass()));

        try {
            new TooDeep();
        } catch (IllegalStateException ex) {
            System.out.println("indirect-rejected="
                    + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -Xlint:all NestedTypeTokenDemo.java
java NestedTypeTokenDemo
```

Mã trên đã được biên dịch sạch với Java 17 và `-Xlint:all`, không có warnings. **Stdout chính xác**:

```text
nested=java.util.List<java.util.Map<java.lang.String, java.lang.Integer>>
outer-raw=java.util.List
inner-kind=ParameterizedType
map-raw=java.util.Map
map-key=java.lang.String
map-value=java.lang.Integer
type-equal=true
type-different=true
named=java.util.List<java.lang.String>
wildcard-kind=WildcardType
wildcard-upper=java.lang.Number
array-kind=GenericArrayType
array-component=java.util.List<java.lang.String>
simple-kind=Class
method-capture=java.util.List<T>
type-variable=TypeVariable
same-runtime-class=true
indirect-rejected=Use a direct parameterized subclass
```

### 15.1. Phân tích nhóm `nested`, `outer-raw`, `map-*`

Kết quả hiển thị một `ParameterizedType` lồng nhau, chứ không chỉ raw `List`. Duyệt `getActualTypeArguments()[0]` từ List xuống Map, rồi từ Map tới String/Integer giúp phục hồi đúng cấu trúc được **khai báo trong type token**.

### 15.2. `type-equal=true`, `type-different=true`

Hai anonymous subclasses khác nhau nhưng mô tả cùng `List<String>` có `Type` metadata bằng nhau về cấu trúc. `List<Integer>` khác `List<String>` ở generic argument nên không cùng `Type`.

### 15.3. `named=...`

`NamedRef` là một class bình thường được khai báo `extends TypeRef<List<String>>`. Nó cũng cung cấp superclass signature có thể đọc được, không bắt buộc sử dụng anonymous class.

### 15.4. `wildcard-kind`, `array-kind`, `simple-kind`

Ba kết quả cho thấy không thể cast mọi Type thành ParameterizedType:

- Wildcard bên trong `List<? extends Number>` được biểu diễn bởi `WildcardType`.
- `List<String>[]` được biểu diễn bởi `GenericArrayType`.
- `String` là `Class`.

Mỗi loại cần được diễn giải phù hợp với semantics Java.

### 15.5. `method-capture` và `type-variable`

Dù caller truyền `"actual String"` vào method generic, Reflection vẫn thấy `List<T>`, với argument bên trong thuộc loại `TypeVariable`. Đây là bằng chứng rằng type token không reify `T` của mỗi generic method invocation.

### 15.6. `same-runtime-class=true`

Hai `ArrayList` khác type arguments vẫn có cùng runtime class, bởi Generics không tạo runtime specialization riêng cho từng type argument. Type token không thay đổi điều này.

### 15.7. `indirect-rejected=...`

Bản `TypeRef` đơn giản chỉ chấp nhận direct parameterized subclass. Lớp `TooDeep` có direct superclass `Intermediate<List<String>>`, nên constructor từ chối để tránh ghi nhận nhầm `Type` chưa được resolve đúng bối cảnh.

## 16. Ví dụ cố ý không biên dịch: generic class literal

Tạo file **`InvalidClassLiteral.java`**:

```java
import java.util.List;

class InvalidClassLiteral {
    Class<List<String>> token = List<String>.class;
}
```

Biên dịch:

```bash
javac --release 17 InvalidClassLiteral.java
```

Compiler báo lỗi cú pháp tại phần type arguments trước `.class`, với nội dung chính:

```text
error: <identifier> expected
```

Đoạn này **cố tình sai**. Java không cho `List<String>.class` như một class literal specialized.

Sửa tùy mục tiêu:

```java
Class<?> rawClass = List.class;
```

nếu chỉ cần runtime class `List`.

Hoặc dùng:

```java
Type nestedType =
        new TypeRef<List<String>>() {}.type();
```

nếu cần mô tả đầy đủ `List<String>` cho một API nhận `Type`. Đoạn sửa này giả định bạn đã có class `TypeRef` như chương trình hoàn chỉnh.

## 17. Các lỗi thường gặp khi tự viết TypeRef

### 17.1. Quên tạo subclass

Một class `TypeRef` concrete cho phép `new TypeRef<List<String>>()` thông thường có thể không lưu type argument ở runtime class. Constructor lúc đó chỉ thấy superclass của chính `TypeRef`, không thấy declaration `extends TypeRef<List<String>>`.

Giải pháp: tạo anonymous/named subclass có superclass tham số hóa cụ thể. Trong ví dụ này `TypeRef` abstract để caller không tạo instance trực tiếp.

### 17.2. Quên `{}` sau biểu thức tạo anonymous subclass

```java
new TypeRef<List<String>>() {};
```

Dấu `{}` là cú pháp tạo anonymous class body. Nếu sửa thành:

```java
new TypeRef<List<String>>();
```

với abstract TypeRef sẽ không biên dịch. Nếu TypeRef là concrete, nó vẫn không khai báo subclass mới mang generic superclass signature theo cách kỹ thuật này cần.

### 17.3. Ép `getGenericSuperclass()` luôn thành ParameterizedType

Không an toàn:

```java
ParameterizedType p =
        (ParameterizedType) getClass().getGenericSuperclass();
```

Nếu superclass raw, không phải generic declaration như dự kiến, hoặc class hierarchy khác, bạn có thể nhận `ClassCastException` hoặc dữ liệu không đúng.

Nên kiểm tra:

```java
if (!(parent instanceof ParameterizedType p)) {
    throw new IllegalStateException("Expected generic superclass");
}
```

Và nếu implementation chỉ hỗ trợ direct subclass, kiểm tra raw type cụ thể như ví dụ.

### 17.4. Lấy argument đầu rồi tưởng đã có Class

```java
Type t = p.getActualTypeArguments()[0];
```

`t` có thể là `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType` hoặc `Class`. Không ép thẳng thành `(Class<?>)` nếu chưa kiểm tra.

Với `List<Map<String,Integer>>`, argument ngoài là **Map parameterized**, không phải Class `Map` chứa luôn arguments.

### 17.5. Bỏ qua owner types của nested classes

Với nested/member generic classes, phần owner có thể là một `Type` có cấu trúc generic riêng. Nếu xây resolver tổng quát, phải xét `ParameterizedType.getOwnerType()` theo quy tắc của class cụ thể.

Đừng nhầm owner type với argument của List hoặc Map, và cũng đừng loại bỏ owner metadata một cách tùy tiện khi so sánh hoặc chuyển đổi type.

### 17.6. Dùng `Type.getTypeName()` làm định danh duy nhất

Tên có thể tiện cho log, nhưng hai class loaders khác nhau có thể nạp những lớp cùng tên không phải cùng `Class` identity. Một cache/reflection resolver nên có key dựa trên `Type`/class identity và hợp đồng phù hợp, không chỉ một string hiển thị.

### 17.7. Nghĩ `TypeRef<List<T>>` trong generic method là đã resolve T

Không. Nó có thể chỉ lưu `TypeVariable T`. Truyền một Type cụ thể từ caller, hoặc dùng resolver có context type mappings, thay vì tuyên bố đã capture String từ giá trị runtime.

### 17.8. Giả định type token tự validate dữ liệu

Không. Nếu một raw alias đưa Integer vào list khai báo String, token cho List<String> không tự sửa và không kiểm tra. Bảo đảm dữ liệu thuộc một generic type đòi code parse/validation thực sự.

### 17.9. Viết API chỉ nhận `Class<T>` rồi cố ép dữ liệu nested vào

`Class<List>` không chứa `String`, và `Class<Map>` không chứa key/value arguments. Nếu mục tiêu là API deserialize generic structures, định nghĩa đầu vào nhận `Type`/type token hoặc loại abstraction tương đương.

### 17.10. Dùng type token làm factory tạo object

`TypeRef<List<String>>` chỉ lưu Type, không có phương thức tạo `ArrayList<String>` hoặc giải constructor cho mọi generic type. Nếu muốn tạo object, cần quy tắc chọn implementation, constructor, dependencies và chính sách dữ liệu riêng.

### 17.11. Xem reflection Signature là nguồn dữ liệu luôn hoàn chỉnh

Generic metadata mô tả những declaration đã biên dịch. Class file tạo từ nguồn không tiêu chuẩn, bytecode bị sửa hoặc generic hierarchy quá phức tạp có thể tạo trường hợp Reflection không đúng kỳ vọng hoặc báo các ngoại lệ liên quan malformed/unresolvable types.

Một framework robust cần có xử lý lỗi, không cast cứng mọi Type thành một dạng duy nhất.

### 17.12. Dùng type token cho mục đích compile-time type safety rồi bỏ qua unchecked warnings

Type token hữu ích để mang metadata qua API; nhưng phép cast unchecked từ Object thành `List<String>` vẫn cần chứng minh invariant. Không coi `@SuppressWarnings("unchecked")` là hành vi validate.

## 18. Type token trong thiết kế JSON/deserialization

Một API giả định có thể trông như:

```java
<T> T fromJson(String json, TypeRef<T> targetType);
```

Với cú pháp:

```java
List<Map<String, Integer>> result =
        fromJson(json,
            new TypeRef<List<Map<String, Integer>>>() {});
```

Đây là **chữ ký và lời gọi minh họa**, không phải API có sẵn của JDK. Nó cần một library/parser implement thực sự.

Một implementation có thể dùng `targetType.type()` để duyệt cấu trúc kiểu rồi quyết định:

- Dùng loại collection implementation nào.
- Dùng adapter nào cho key/value.
- Có chấp nhận null không.
- Làm gì nếu JSON chứa số không phù hợp Integer.
- Có xử lý wildcard/TypeVariable chưa resolve không.
- Trả lỗi cụ thể khi schema không phù hợp ra sao.

Các thư viện khác nhau có API tên khác nhau, ví dụ họ `TypeToken`, `TypeReference`, `ParameterizedTypeReference`; cần tra chính xác phiên bản/documentation của thư viện đang dùng. Kỹ thuật cốt lõi giống nhau: **đưa một mô tả generic Type từ declaration sang runtime logic**.

### 18.1. Kiểm tra thư viện có hỗ trợ `Type` lồng nhau

Không phải mọi parser hỗ trợ tất cả các dạng:

- `Class<?>`.
- `ParameterizedType` nhiều tầng.
- `WildcardType`.
- `TypeVariable<?>` chưa được resolve.
- `GenericArrayType`.
- Owner type của nested class.

Một API nhận `Type` chưa bảo đảm implementation xử lý được mọi dạng Type. Hãy đọc contract và test cấu trúc thực tế cần dùng.

### 18.2. Tránh “JSON đã parse thành Object rồi unchecked cast”

Nếu parser chỉ tạo `Object` hoặc raw `Map`, cast tới `Map<String, List<Integer>>` không xác minh generic arguments. Nên truyền type token ngay lúc parse để converter có metadata cần thiết, hoặc validate và copy rõ từng cấp sau parse.

## 19. Thiết kế helper duyệt cây Type đúng mức

Một helper chẩn đoán có thể phân nhánh:

```java
static String kind(Type type) {
    if (type instanceof ParameterizedType)
        return "ParameterizedType";
    if (type instanceof GenericArrayType)
        return "GenericArrayType";
    if (type instanceof WildcardType)
        return "WildcardType";
    if (type instanceof TypeVariable<?>)
        return "TypeVariable";
    if (type instanceof Class<?>)
        return "Class";
    return "Unknown";
}
```

Đoạn này cần imports của Reflection và được đặt trong class. Nó chỉ phân loại type; chưa phải serializer hoặc validator.

Khi viết một **resolver tổng quát**, các nhánh có thể tiếp tục:

- Với `ParameterizedType`: duyệt owner, raw type và actual arguments.
- Với `GenericArrayType`: duyệt component type.
- Với `WildcardType`: duyệt upper/lower bounds.
- Với `TypeVariable`: duyệt bounds và tra cứu mapping theo generic declaration/context.
- Với `Class`: xét array component qua `getComponentType()` nếu class là mảng.

### 19.1. Cẩn thận với type graphs và vòng lặp

Một type variable có thể có recursive bound:

```java
class Node<T extends Comparable<T>> {
}
```

Nếu walker đệ quy không theo dõi loại Type đã thăm hoặc không có quy tắc dừng, nó có thể lặp lại khi đi từ TypeVariable tới bounds rồi trở về TypeVariable.

Một implementation hoàn chỉnh cần chính sách cycle detection và mapping kiểu, thay vì chỉ gọi đệ quy vô hạn qua mọi bound.

### 19.2. Không tự xây generic type parser nếu chỉ cần dùng library

Khi code ứng dụng chỉ muốn chuyển JSON thành một cấu trúc lồng nhau, dùng type token mà library hỗ trợ thường đủ. Tự implement mọi nhánh Type, owner, wildcard, variable substitution dễ tạo lỗi tinh tế.

Bạn nên hiểu metadata để debug và thiết kế API, nhưng không nhất thiết phải viết một generic framework mới cho từng dự án.

## 20. Những hiểu lầm quan trọng

| Khẳng định | Đúng hay sai? | Vì sao |
| --- | --- | --- |
| `new TypeRef<List<String>>() {}` giữ được metadata List<String>. | Đúng, với TypeRef đọc đúng superclass signature. | Anonymous subclass khai báo generic superclass. |
| `List<String>.class` hợp lệ. | Sai. | Java không có specialized class literal kiểu đó. |
| `List.class` đủ mô tả List<Map<String,Integer>>. | Sai. | Nó chỉ mô tả raw runtime class/interface. |
| `new TypeRef<List<T>>() {}` trong generic method luôn biết T=String ở caller. | Sai. | Metadata có thể vẫn chứa TypeVariable T. |
| Type token tự chứng minh mọi phần tử list là String. | Sai. | Metadata và validation dữ liệu là hai việc khác nhau. |
| `Type` luôn cast được thành `Class`. | Sai. | Có ParameterizedType/WildcardType/TypeVariable/GenericArrayType. |
| `TypeRef<List<String>[]>` lưu được mô tả generic array. | Đúng. | Reflection có GenericArrayType. |
| Có thể `new List<String>[3]` nhờ dùng TypeRef. | Sai. | Java generic array creation vẫn bị giới hạn. |
| Hai anonymous subclasses khác nhau có thể biểu diễn `Type` bằng nhau. | Đúng. | Cùng cấu trúc generic declaration. |
| Lớp con nhiều tầng chỉ cần `getGenericSuperclass()` một lần. | Sai. | Thường cần thay thế type variables qua hierarchy. |

## 21. Câu hỏi thực hành có đáp án

### Bài 1. Vì sao không dùng `List<Map<String,Integer>>.class`?

<details>
<summary>Đáp án</summary>

Java không tạo một runtime Class object chuyên biệt theo mọi type arguments của Generics. Class literal chỉ có thể viết ở những dạng ngôn ngữ cho phép, không có dạng parameterized specialized như `List<String>.class`. Dùng `List.class` nếu chỉ cần raw class, hoặc TypeRef/Type token nếu muốn mô tả generic structure lồng nhau.

</details>

### Bài 2. Dấu `{}` trong `new TypeRef<List<String>>() {}` có tác dụng gì?

<details>
<summary>Đáp án</summary>

Nó tạo anonymous subclass của TypeRef, superclass được khai báo là `TypeRef<List<String>>`. Generic superclass signature của class con là nguồn metadata mà Reflection có thể đọc.

</details>

### Bài 3. `getClass()` của `new ArrayList<String>()` có cho biết String không?

<details>
<summary>Đáp án</summary>

Không. Runtime class của object thông thường là `ArrayList`, không có specialization riêng cho type argument String. Type token hoạt động nhờ superclass metadata **trên class con được tạo**, không nhờ runtime contents của ArrayList.

</details>

### Bài 4. Type bên ngoài của `List<Map<String,Integer>>` thuộc nhóm nào?

<details>
<summary>Đáp án</summary>

`ParameterizedType` của List. Argument duy nhất là một `ParameterizedType` khác của Map; raw type của Map là Map, với arguments String và Integer.

</details>

### Bài 5. Vì sao `getActualTypeArguments()[0]` không luôn là Class?

<details>
<summary>Đáp án</summary>

Vì một generic argument có thể là kiểu tham số hóa, wildcard, type variable hoặc generic array. Chẳng hạn argument của `List<Map<String,Integer>>` là `ParameterizedType`, không phải `Map.class` chứa tự động key/value arguments.

</details>

### Bài 6. `new TypeRef<List<T>>() {}` trong method `<T>` có đảm bảo biết subtype cụ thể caller chọn không?

<details>
<summary>Đáp án</summary>

Không. Nó có thể lưu `List<T>` với TypeVariable T chưa resolve. Muốn kiểu cụ thể như List<String>, caller cần cung cấp Type token cụ thể hoặc framework phải có context ánh xạ T.

</details>

### Bài 7. Vì sao TypeRef của chương trình trên từ chối `TooDeep`?

<details>
<summary>Đáp án</summary>

Constructor kiểm tra direct superclass có raw type chính là TypeRef. `TooDeep` trực tiếp extends `Intermediate<List<String>>`, không phải TypeRef. Hỗ trợ nhiều tầng cần resolver thay thế generic variables theo chain kế thừa.

</details>

### Bài 8. Type token cho `List<? extends Number>` có biết list thực chứa Integer hay Double không?

<details>
<summary>Đáp án</summary>

Không. Wildcard mô tả upper bound Number, không ghi specialization runtime của từng list object. Có thể dùng `WildcardType` để đọc bound, còn dữ liệu thực phải được kiểm tra riêng nếu cần.

</details>

### Bài 9. Có thể giữ generic array type dù không tạo được `new List<String>[n]` không?

<details>
<summary>Đáp án</summary>

Có. `TypeRef<List<String>[]>` có thể giữ metadata `GenericArrayType`, nhưng điều đó không làm generic array creation với non-reifiable component trở nên hợp lệ.

</details>

### Bài 10. Muốn biết JSON có đúng kiểu `Map<String,List<Integer>>` cần làm gì?

<details>
<summary>Đáp án</summary>

Cung cấp một `Type` mô tả cấu trúc mong đợi cho parser/validator hỗ trợ kiểu lồng nhau, rồi đảm bảo parser/validator thực sự kiểm tra/chuyển đổi cả key, value, collection và từng phần tử. Type token chỉ chuyển metadata, không tự validate JSON hay Object graph.

</details>

## 22. Checklist áp dụng vào dự án

1. **Xác định yêu cầu thực sự:** chỉ cần `Class<T>`, hay cần giữ `List<Map<String,Integer>>`?
2. Nếu cần kiểu lồng nhau, tạo token từ **nơi biết concrete type arguments**, ví dụ `new TypeRef<List<Map<String,Integer>>>() {}`.
3. Xem `getGenericSuperclass()` trả Class hay ParameterizedType; không cast mù.
4. Duyệt cây Type theo từng cấp, thay vì cắt chuỗi `getTypeName()` bằng tay.
5. Nhận diện `TypeVariable` chưa resolve; đừng quảng cáo nó là concrete `String.class`.
6. Nếu cần lớp con nhiều tầng, dùng resolver có substitution mapping thay vì một phép Reflection đơn giản.
7. Nếu làm JSON/deserialization, kiểm tra thư viện hỗ trợ Type lồng nhau, wildcard và null policy ra sao.
8. Tách **metadata** khỏi **validation**, tránh unchecked cast dữ liệu ngoài mà không kiểm tra.
9. Khi cache type-based adapters, phân biệt đầy đủ type arguments, owner type và class loader context nếu có.
10. Dùng Java 17 để biên dịch ví dụ/kiểm thử cả nested type, named subclass, wildcard, generic array và unresolved type variables.
11. Nếu API chỉ yêu cầu một runtime class cụ thể, `Class<T>` vẫn là công cụ đơn giản và thích hợp.
12. Không đọc generic metadata của một instance rồi mặc định rằng tất cả dữ liệu hiện tại phù hợp với declaration.

## 23. Tổng kết

**Super type token lưu thông tin generic lồng nhau bằng cách khai báo một subclass có superclass được tham số hóa cụ thể.** Với:

```java
new TypeRef<List<Map<String, Integer>>>() {}
```

anonymous subclass có metadata cho `TypeRef<List<Map<String,Integer>>>`, nên Reflection có thể lấy lại Type của `List<Map<String,Integer>>` và duyệt các nested `ParameterizedType` tới `String`/`Integer`.

Kỹ thuật này đặc biệt hữu ích khi API cần một **mô tả kiểu đầy đủ** chứ không chỉ `List.class`. Nhưng cần nhớ ba giới hạn:

- **Type erasure vẫn còn**: type token không làm mỗi `List<String>` trở thành một runtime class riêng.
- **TypeVariable có thể chưa resolve**: `List<T>` trong generic method không tự biến thành `List<String>` ở mỗi lời gọi.
- **Metadata không phải validation**: parser/validator phải thật sự đọc và kiểm tra dữ liệu theo schema đã mô tả.

Dùng TypeRef trực tiếp và đơn giản cho call sites có concrete generic structure; dùng một resolver/framework đủ năng lực nếu phải xử lý inheritance nhiều tầng, owner type, wildcard hoặc type variables. Khi hiểu đúng nguồn metadata và giới hạn của nó, bạn có thể truyền thông tin kiểu lồng nhau vào Reflection, serialization và data mapping mà không nhầm lẫn với runtime type checks.