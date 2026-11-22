# Phân biệt metadata generic trong khai báo với thông tin bị xóa lúc chạy

## 1. Câu hỏi trọng tâm

Khi khai báo một field kiểu `List<String>`, tại sao Reflection có thể in ra `java.util.List<java.lang.String>` bằng `Field.getGenericType()` nhưng một đối tượng `new ArrayList<String>()` ở runtime lại không cho biết phần tử của nó chắc chắn là `String`?

Câu trả lời nằm ở việc Java generic có **hai tầng thông tin khác nhau**:

1. **Metadata generic của khai báo** (*generic declaration metadata*): trình biên dịch có thể ghi lại mô tả kiểu trong class file, để các API Reflection như `getGenericType()`, `getGenericReturnType()`, `getGenericSuperclass()` đọc lại.
2. **Kiểu runtime sau type erasure**: JVM thực thi phần lớn generic thông qua **raw class, erased type và các cast do compiler chèn**. Một đối tượng `ArrayList<String>` thông thường không mang tham số `String` như một danh tính class runtime riêng biệt.

Do vậy, **thấy `List<String>` trong một `Type` qua Reflection không đồng nghĩa có thể kiểm tra toàn bộ kiểu phần tử của bất kỳ đối tượng `List` nào tại runtime**.

Sau bài học, bạn có thể phân biệt `Class<?>` và `Type`, đọc đúng các dạng `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`, kiểm tra erased signatures, truy vết generic arguments trong quan hệ kế thừa, và chẩn đoán những lỗi khi giả định runtime còn giữ toàn bộ kiểu generic.

## 2. Ví dụ nhanh: cùng khai báo nhưng hai góc nhìn

Xét một lớp Java:

```java
import java.util.List;

class Store<T> {
    T value;
    List<String> labels;
}
```

Đây là **mã minh họa**, chưa có `main`. Với Reflection:

| Thành viên | Kiểu khai báo trong mã Java | API cho kiểu đã erasure | API cho metadata generic |
| --- | --- | --- | --- |
| `Store.value` | `T` | `getType()` trả `Object.class` nếu `T` không có bound cụ thể | `getGenericType()` trả một `TypeVariable` tên `T` |
| `Store.labels` | `List<String>` | `getType()` trả `List.class` | `getGenericType()` trả `ParameterizedType` biểu diễn `List<String>` |

Điểm cần phân biệt:

- Thông tin `List<String>` được gắn với **khai báo field `labels`**; đây là một đặc tả kiểu do compiler lưu để công cụ đọc.
- Nếu `labels` chứa một đối tượng `ArrayList<Integer>` do raw type hoặc lời gọi Reflection không an toàn truyền vào, Java runtime **không tự đối chiếu từng phần tử** theo chuỗi `String` lấy từ metadata.
- Nếu `new Store<String>()` và `new Store<Integer>()` là hai object bình thường, `getClass()` của cả hai đều trả về **`Store.class`**, không phải hai runtime class khác nhau.
- Field `value` không tự trở thành một field runtime có kiểu `String` trong mọi instance `Store<String>`. Erasure của `T` không bound là `Object`.

## 3. Type erasure thực sự xóa những gì?

Java generic chủ yếu sử dụng **type erasure** theo các quy tắc của Java Language Specification (JLS `4.6). Khi biên dịch, compiler chuyển thông tin generic cần thiết thành các dạng runtime phù hợp:

1. `List<String>` và `List<Integer>` đều có erasure `List`.
2. Một type variable **không có bound** như `T` có erasure là `Object`.
3. Type variable có một hoặc nhiều bound lấy erasure của **bound đầu tiên**.
4. Parameterized types và generic methods được biên dịch thành các descriptor mang erased types; compiler có thể chèn cast và phát sinh bridge method khi cần giữ tính đa hình.
5. Metadata generic của declaration có thể được ghi vào class file, chủ yếu qua thuộc tính **`Signature`** theo class-file format; JVM vẫn thực thi theo descriptor và kiểu runtime thông thường.

Ví dụ:

```java
class Bounded<T extends Number & Comparable<T>> {
    T amount;
}
```

Field `amount` có kiểu khai báo `T`. Với Reflection, `getType()` trả `Number.class` vì **`Number` là bound đầu tiên**, trong khi `getGenericType()` vẫn có thể trả `TypeVariable` đại diện cho `T` và đọc các bound từ đó.

**Erasure không có nghĩa “Reflection hoàn toàn không thấy generic”.** Nó có nghĩa thông tin kiểu được dùng để định danh object/method ở runtime **không còn đầy đủ như kiểu ở source**. Metadata mô tả declaration là một kênh khác.

### 3.1. Kiểu runtime vẫn có kiểm tra thật

Erasure không bỏ qua mọi kiểm tra kiểu:

- JVM vẫn kiểm tra object có đúng runtime class/interface không khi `checkcast`, `instanceof`, `Field.set` hoặc `Method.invoke` cần kiểm tra kiểu.
- Nếu method generic đọc một phần tử và compiler biết phải nhận `String`, nó có thể chèn `checkcast String` tại nơi sử dụng.
- Những kiểm tra này **không xác nhận đầy đủ** toàn bộ đối tượng `List` là một `List<String>`; cast thường xuất hiện khi một giá trị riêng lẻ được rút ra.

Chẳng hạn, nếu dùng raw API đưa `List<Integer>` vào nơi khai báo `List<String>` rồi trong method gán `String first = list.get(0);`, lỗi `ClassCastException` có thể xuất hiện **khi đọc phần tử**, không phải ngay khi truyền danh sách.

## 4. Chữ ký kiểu vẫn nằm trong mô hình `Type`

Các API generic trả `Type` vì một khai báo có thể chứa `Class` như `String`, `ParameterizedType` như `List<String>`, `TypeVariable` như `T`, wildcard bên trong `List<? extends Number>`, hoặc `GenericArrayType` như `T[]`. Phân biệt quan trọng cho bài erasure là: `Field.getType()` trả class runtime sau erasure; `Field.getGenericType()` trả cấu trúc generic **trên declaration** nếu metadata còn tồn tại. `Type.getTypeName()` chỉ hiển thị tên và không tạo runtime class riêng.

Không ép mọi `Type` sang `Class<?>`. Khi ví dụ bên dưới in ra `Map<String,List<Integer>>`, việc nó có hai tầng `ParameterizedType` nói lên cấu trúc **khai báo field**, chưa chứng minh collection runtime chứa đúng `Integer`.

## 5. Chương trình Java 17+ độc lập và kết quả chạy

Lưu toàn bộ mã sau thành **`GenericMetadataDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class GenericMetadataDemo {
    static class Holder<T> {
        T value;
        T[] elements;
        List<String> labels;
        Map<String, List<Integer>> index;
        List<? extends Number> numbers;

        T echo(T item) { return item; }

        void consume(List<String> input) {
            System.out.println("consume size=" + input.size());
        }

        void readFirst(List<String> input) {
            String first = input.get(0);
            System.out.println("first=" + first);
        }
    }

    static class IntegerHolder extends Holder<Integer> {}
    static class Bounded<T extends Number & Comparable<T>> {
        T amount;
    }

    private static void inspect(String fieldName) throws Exception {
        Field field = Holder.class.getDeclaredField(fieldName);
        System.out.println(fieldName + " raw=" + field.getType().getTypeName());
        System.out.println(fieldName + " generic=" + field.getGenericType().getTypeName());
    }

    public static void main(String[] args) throws Exception {
        inspect("value");
        inspect("elements");
        inspect("labels");
        inspect("index");
        inspect("numbers");

        Field labels = Holder.class.getDeclaredField("labels");
        Type declared = labels.getGenericType();
        System.out.println("labels is ParameterizedType="
                + (declared instanceof ParameterizedType));

        Method echo = Holder.class.getDeclaredMethod("echo", Object.class);
        System.out.println("echo raw return=" + echo.getReturnType().getTypeName());
        System.out.println("echo generic return="
                + echo.getGenericReturnType().getTypeName());
        System.out.println("bounded raw="
                + Bounded.class.getDeclaredField("amount").getType().getTypeName());
        System.out.println("subclass generic parent="
                + IntegerHolder.class.getGenericSuperclass().getTypeName());
        System.out.println("Holder type variable="
                + Holder.class.getTypeParameters()[0].getName());

        Class<?> a = new ArrayList<String>().getClass();
        Class<?> b = new ArrayList<Integer>().getClass();
        System.out.println("same runtime class=" + (a == b));

        Holder<String> holder = new Holder<>();
        Method consume = Holder.class.getDeclaredMethod("consume", List.class);
        consume.invoke(holder, List.of(42));
        Method readFirst = Holder.class.getDeclaredMethod("readFirst", List.class);
        try {
            readFirst.invoke(holder, List.of(42));
        } catch (InvocationTargetException e) {
            System.out.println("readFirst cause="
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 GenericMetadataDemo.java
java GenericMetadataDemo
```

**Stdout chính xác** đã kiểm tra với `javac 21 --release 17` và OpenJDK 21:

```text
value raw=java.lang.Object
value generic=T
elements raw=java.lang.Object[]
elements generic=T[]
labels raw=java.util.List
labels generic=java.util.List<java.lang.String>
index raw=java.util.Map
index generic=java.util.Map<java.lang.String, java.util.List<java.lang.Integer>>
numbers raw=java.util.List
numbers generic=java.util.List<? extends java.lang.Number>
labels is ParameterizedType=true
echo raw return=java.lang.Object
echo generic return=T
bounded raw=java.lang.Number
subclass generic parent=GenericMetadataDemo$Holder<java.lang.Integer>
Holder type variable=T
same runtime class=true
consume size=1
readFirst cause=ClassCastException
```

### 5.1. Giải thích từng nhóm dòng

**`value`:** `T` là type variable không bound, có erasure `Object`. `Field.getType()` chỉ thấy `Object`, còn `getGenericType()` đọc lại ký hiệu `T` từ metadata khai báo.

**`elements`:** khai báo `T[]` có runtime erasure `Object[]`, nhưng `getGenericType()` vẫn mô tả `T[]`, thường bằng một `GenericArrayType`.

**`labels`, `index`, `numbers`:** mọi field đều có raw type là `List` hoặc `Map`. Metadata vẫn chứa argument `String`, cấu trúc lồng nhau `List<Integer>` và wildcard `? extends Number`, tương ứng `ParameterizedType` cùng các nút `Type` con.

**`echo`:** phương thức `T echo(T)` được tìm bằng erased parameter type `Object.class`. Runtime return type là `Object`; generic return type là `T`.

**`bounded`:** `T extends Number & Comparable<T>` lấy erasure của **bound đầu tiên** là `Number`. Điều đó không phủ nhận bound thứ hai; nó vẫn thuộc metadata của `TypeVariable`.

**`IntegerHolder`:** lời khai báo `extends Holder<Integer>` ghi lại tham số kiểu cụ thể ở **quan hệ superclass**; Reflection có thể đọc `Holder<Integer>`. Nhưng field `value` thực ra vẫn được khai báo trong `Holder<T>`, nên bản thân `Field.getGenericType()` của field ấy vẫn là `T`.

**`same runtime class=true`:** generic instantiations `ArrayList<String>` và `ArrayList<Integer>` đều có cùng runtime class `ArrayList`. Chương trình không thể dùng `list.getClass()` để xác định argument `String` hay `Integer` đã sử dụng ở source.

**`consume` và `readFirst`:** Reflection chấp nhận `List.of(42)` ở tham số method khai báo `List<String>` vì erased parameter type là `List`. `consume` chỉ đọc `size()` nên hoạt động. Trong `readFirst`, khi gán phần tử lấy ra vào `String`, phép cast do compiler chèn phát sinh `ClassCastException`; Reflection bao nó vào `InvocationTargetException` và chương trình in cause.

## 6. Metadata generic thực tế được lưu ở đâu?

Trong class file, JVM dùng **field/method descriptors** để biểu diễn các kiểu cần thiết cho runtime invocation và linking. Compiler Java có thể ghi thêm **`Signature` attribute** mô tả generic type parameters, parameterized field types, generic methods hoặc generic superclass/interface theo cấu trúc ở source.

Có thể kiểm tra hai kênh bằng JDK tool:

```bash
javap -v -p 'GenericMetadataDemo$Holder'
javap -v -p 'GenericMetadataDemo$IntegerHolder'
```

Dấu nháy đơn giúp bảo vệ ký tự `$` trong tên binary của nested class ở các shell có hỗ trợ cú pháp này (chẳng hạn Bash và PowerShell).

Trong `Holder`, chú ý:

- `descriptor: Ljava/lang/Object;` cho `value`; phần `Signature` có thể biểu diễn `TT;`.
- `descriptor: Ljava/util/List;` cho `labels`; `Signature` biểu diễn `Ljava/util/List<Ljava/lang/String;>;`.
- `descriptor: [Ljava/lang/Object;` cho `elements`; generic signature vẫn ghi `[TT;`.
- Erased descriptor của `echo` dùng tham số/giá trị trả về `Object`; generic signature dùng `T`.

Trong `IntegerHolder`, generic superclass `Holder<Integer>` được mô tả bằng `Signature` dù runtime superclass vẫn là chính `Holder.class`.

**Không nên hiểu `Signature` là một danh sách type arguments gắn tự động với từng instance.** Nó mô tả khai báo class/member hoặc generic supertype relationship. Một object tạo bằng `new Holder<String>()` thông thường không giữ riêng type argument này ở `getClass()`.

### 6.1. Nếu generic signature không có thì sao?

Không phải class file do mọi ngôn ngữ hoặc tool tạo ra đều lưu đủ metadata generic như `javac`. Công cụ bytecode transformer hoặc obfuscator cũng có thể bỏ hoặc làm hỏng `Signature`:

- Khi không có thông tin generic bổ sung, generic reflection API có thể chỉ cho **raw `Class<?>`** tương ứng.
- Metadata có thể nêu type không load được, khiến truy cập generic type phát sinh `TypeNotPresentException`.
- Chữ ký generic không hợp lệ có thể dẫn tới `GenericSignatureFormatError` hoặc `MalformedParameterizedTypeException` tùy dạng lỗi.

Nếu ứng dụng phân tích bytecode từ nguồn lạ, nên xử lý các lỗi đó rõ ràng. **Không suy diễn một `List.class` trở thành `List<String>` chỉ vì quy ước đặt tên hoặc dữ liệu tình cờ chứa String.**

## 7. Dữ liệu generic phải được đọc có cấu trúc

Khi `Holder.labels` khai báo `List<String>`, `getGenericType()` trả `ParameterizedType` có `getRawType() == List.class`, argument `String.class` và owner `null`. Với field `Map<String, List<Integer>>`, argument thứ hai lại là một `ParameterizedType`; với `List<? extends Number>`, argument là `WildcardType`. Vì vậy metadata cần phân tích qua các subtype của `Type`, không ép mọi argument sang `Class<?>` hoặc parse chuỗi `getTypeName()`.

Điểm của bài cuối là **cùng cấu trúc ấy chỉ mô tả lời khai báo**. Phần tiếp theo thử truy vết type argument ở subclass rồi phân tích những runtime checks thực sự còn hiệu lực.

## 8. Truy vết type argument qua lớp con: có thể biết được gì?

`IntegerHolder extends Holder<Integer>` ghi rõ argument `Integer` trong generic superclass declaration. Vì vậy:

```java
Type parent = IntegerHolder.class.getGenericSuperclass();
if (parent instanceof ParameterizedType pt) {
    System.out.println(pt.getActualTypeArguments()[0].getTypeName());
    // java.lang.Integer
}
```

Đây là **mã minh họa**, sử dụng kiểu từ `GenericMetadataDemo` và import `Type`, `ParameterizedType` như chương trình chính.

Nhưng kết luận cần giới hạn:

- Trong subclass `IntegerHolder`, declaration ở cạnh `extends Holder<Integer>` gắn một argument cụ thể, nên metadata cho biết `T` tương ứng `Integer` ở quan hệ đó.
- `Field value` vẫn do `Holder<T>` khai báo; gọi `field.getGenericType()` một mình trả về `T`, **không tự thay thành Integer** khi đối tượng field được lấy từ `IntegerHolder.class`.
- Nếu có chuỗi `Derived<U> extends Middle<List<U>>` rồi `Concrete extends Derived<String>`, việc suy ra field gốc cần **truy vết nhiều cạnh và ánh xạ `TypeVariable`** qua từng tham số kiểu. Java Reflection cơ bản cung cấp dữ liệu, không có một API duy nhất tự giải mọi phép thay thế generic trong hệ phân cấp.
- Nếu chỉ có một đối tượng bình thường `new Holder<Integer>()` và không có subclass mang tham số cố định hay token bổ sung, thường **không có đủ metadata runtime** để truy ra `Integer`.

### 8.1. Anonymous subclass và type token

Một kỹ thuật thường gặp là tạo subclass ẩn danh với superclass generic cố định:

```java
Holder<String> typed = new Holder<String>() {};
Type genericParent = typed.getClass().getGenericSuperclass();
System.out.println(genericParent.getTypeName());
```

Đây là **mã minh họa** sử dụng `Holder` từ chương trình chính, không phải chương trình độc lập. Một compiler như `javac` giữ metadata `Holder<String>` trên declaration của anonymous subclass, nên nhiều thư viện *type token* đọc được type arguments từ `getGenericSuperclass()`.

Tuy nhiên:

- Kỹ thuật này dựa vào **metadata của lớp con ẩn danh**, không chứng minh mọi instance `Holder<String>` tự có type parameter ở runtime.
- Không phải mọi biểu thức generic đều được giữ đầy đủ nếu kiểu vẫn còn là `T` từ một scope khác.
- Metadata cũng không biến phép kiểm tra `instanceof List<String>` thành hợp lệ trong Java source.

## 9. Những thông tin generic không thể kiểm tra trực tiếp ở runtime

### 9.1. `instanceof` và `List<String>`

Trong Java:

```java
Object value = java.util.List.of("a", "b");

if (value instanceof java.util.List<?>) {
    System.out.println("some list");
}

// Sai: instanceof List<String> không phải kiểm tra reifiable hợp lệ.
// if (value instanceof java.util.List<String>) { ... }
```

Đây là đoạn minh họa; cần import hoặc fully qualified name tương ứng. `List<?>` là một dạng reifiable cho kiểm tra `instanceof`; `List<String>` không reifiable theo kiểu đó.

`value instanceof List<?>` chỉ chứng minh object là một `List` phù hợp ở runtime, **không chứng minh các phần tử là String**.

### 9.2. Không thể tạo generic array trực tiếp với type variable

Trong class generic, biểu thức:

```java
class Buffer<T> {
    // T[] array = new T[10]; // Không hợp lệ.
}
```

không hợp lệ vì runtime cần biết loại component của array để thực hiện store checks, còn `T` không được reify như class tùy ý. Có thể tạo array bằng một `Class<T>` token phù hợp qua `Array.newInstance(...)` và cân nhắc cast, nhưng cần quản lý an toàn kiểu của token/array.

### 9.3. Raw types và unchecked conversions

Nếu sử dụng raw `List`, cast unchecked hoặc Reflection, bạn có thể đưa một collection chứa `Integer` vào nơi khai báo `List<String>`. Compiler có thể cảnh báo, nhưng runtime không tự duyệt collection để xác minh generic element type.

**Hệ quả thực tế:** khi nhận dữ liệu từ JSON, DB hoặc hệ thống plugin, muốn đảm bảo `List<String>` thực sự chỉ chứa `String`, ứng dụng phải kiểm tra **giá trị từng phần tử** hoặc sử dụng framework có runtime type-token và quy tắc validation phù hợp.

## 10. Phân biệt generic declaration metadata và generic erasure khi tìm method

Giả sử một method khai báo:

```java
static void process(java.util.List<String> values) {
    System.out.println(values.size());
}
```

Đây là **mã minh họa** chưa có class chạy. Reflection tìm theo **erased parameter types**, không theo `List<String>`:

```java
Method method = SomeClass.class.getDeclaredMethod(
        "process", java.util.List.class);
```

`SomeClass` là class giả định chứa method. Nếu cần đọc chữ ký generic, gọi `method.getGenericParameterTypes()` sau khi đã tìm được method.

Cần nhớ:

- `getDeclaredMethod` nhận `Class<?>...` của **formal parameters**, không nhận `ParameterizedType`.
- Hai method trong cùng class **không thể overload chỉ bằng `List<String>` so với `List<Integer>`**, bởi cả hai có cùng erasure `List` và gây name clash.
- Compiler có thể sinh **bridge method** khi overriding generic method cần tương thích sau erasure. Reflection sẽ thấy cả method gốc và bridge; `Method.isBridge()` giúp phân biệt, còn `getGenericParameterTypes()` phải đọc trên đúng `Method` bạn đang phân tích.
- `Method.invoke` vẫn thực hiện kiểm tra loại tham số erased tương ứng; metadata generic không tự áp đặt ràng buộc `String` lên từng phần tử collection.

## 11. Đọc metadata generic qua Reflection có phải luôn đáng tin?

Đúng **đối với điều mà metadata thể hiện**: nó mô tả declaration và generic supertype relationships được ghi trong class file, thường do compiler `javac` tạo. Nhưng mục đích dùng phải đúng:

| Mục tiêu | Metadata generic hữu ích? | Giới hạn |
| --- | --- | --- |
| Hiển thị `Map<String, List<Integer>>` trong tài liệu API | Có, dùng `getGenericType()` và phân tích `Type` | Metadata có thể vắng hoặc bị công cụ bytecode sửa |
| Phân tích `Child extends Base<Foo>` | Có, dùng `getGenericSuperclass()` | Phải tự ánh xạ type variables khi quan hệ kế thừa nhiều tầng |
| Xác nhận `List<?>` là collection kiểu `List` | Có thể dùng `isInstance`/`isAssignableFrom` với raw class | Không kiểm tra được type argument |
| Chứng minh mọi phần tử trong runtime collection là `String` | Không chỉ bằng metadata | Cần kiểm tra giá trị hoặc có ràng buộc từ cơ chế khác |
| Tìm method nhận `List<String>` | Dùng `getDeclaredMethod` với `List.class`, rồi xem metadata | Không truy vấn method bằng `List<String>.class` |
| Tìm class của `T` ở một object `new Holder<Integer>()` | Thường không | Type argument của parameterized object không được reify |
| Serialization/deserialization có kiểu phần tử | Có, nếu caller cung cấp `Type`/type token hoặc field declaration | Vẫn cần thực thi conversion/validation từ dữ liệu ngoài |

### 11.1. Rủi ro khi framework suy luận quá mức

Một framework có thể đọc `Field.getGenericType()` ra `List<String>` rồi dùng nó để deserialize JSON thành `List<String>`. Đây là **sử dụng metadata để chủ động hướng dẫn conversion**, không phải JVM bất ngờ “nhớ lại” type argument của đối tượng raw `ArrayList`.

Tương tự, ORM/DI container có thể dùng type arguments để resolve dependency hoặc mapping. Độ đúng của thao tác dựa vào **mô hình và runtime checks của framework**, bao gồm xử lý wildcard, generic hierarchy, raw type và class loader, chứ không chỉ vào một lời gọi `getGenericType()`.

## 12. Lỗi phổ biến và cách khắc phục

**Lỗi 1 — “Generics bị erase nên `getGenericType()` chắc cũng chỉ trả raw class.”** Erasure áp dụng cho runtime representation/descriptor; metadata generic trong `Signature` vẫn có thể được Reflection đọc.

**Lỗi 2 — “`getGenericType()` trả `List<String>` nên object field đang chứa chắc chắn là `List<String>`.”** Metadata mô tả **khai báo field**; không tự xác nhận trạng thái runtime hay từng element.

**Lỗi 3 — Ép mọi `Type` thành `Class<?>`.** `ParameterizedType`, `TypeVariable`, `WildcardType` và `GenericArrayType` không phải `Class<?>`. Cần phân nhánh theo `instanceof`.

**Lỗi 4 — Tìm method `echo(T)` bằng argument class cụ thể.** Runtime lookup dùng erased parameter, ví dụ `Object.class` hoặc erasure của bound đầu tiên.

**Lỗi 5 — Nhầm `getGenericSuperclass()` là generic superclass của object gốc đã truyền tham số.** Nó mô tả declaration **trực tiếp của class được hỏi**; `new Holder<String>().getClass()` vẫn là `Holder.class`, không tự cung cấp `String`. Subclass `IntegerHolder` mới ghi lại `Holder<Integer>` ở cạnh `extends`.

**Lỗi 6 — Kiểm tra `List<String>` bằng `instanceof`.** Đây không phải runtime-reifiable parameterized type. Kiểm tra raw class và dữ liệu phần tử bằng giải pháp thích hợp.

**Lỗi 7 — Cho rằng `Map<String,List<Integer>>` là một `ParameterizedType` phẳng có toàn bộ arguments là `Class<?>`.** Phải duyệt cấu trúc `Type` lồng nhau.

**Lỗi 8 — Cho rằng generic signature luôn tồn tại và luôn hợp lệ.** Class-file tools hoặc code do ngôn ngữ khác biên dịch có thể làm metadata vắng mặt hay không hợp lệ. Cần xử lý trường hợp fallback/lỗi đọc generic type.

**Lỗi 9 — Đồng nhất lỗi Reflection trước invoke với lỗi cast trong method.** Truyền `List<Integer>` vào parameter erased `List` có thể thành công; cast `String` thất bại trong method và `Method.invoke` bọc bằng `InvocationTargetException`.

**Lỗi 10 — Cho rằng danh tính kiểu generic được phân biệt bởi `getClass()`.** `ArrayList<String>` và `ArrayList<Integer>` thông thường cùng runtime class; nơi giữ được generic arguments là metadata ở **declaration**, hoặc type token được tạo có chủ đích.

## 13. Bài tập tự kiểm tra

1. Thay `Holder<T>` bằng `Holder<T extends Number>`. Dự đoán `value.getType()`, `value.getGenericType()` và erased signature của `echo(T)` trước khi chạy chương trình.
2. Dùng `ParameterizedType.getActualTypeArguments()` duyệt `Map<String, List<Integer>>` trong `index`. Vẽ cây `Type` và chỉ ra nút nào là `Class<?>`, nút nào là `ParameterizedType`.
3. Thêm `List<? super Integer> lower;` vào `Holder`. Đọc `WildcardType.getLowerBounds()` và giải thích khác với `? extends Number`.
4. Tạo `new Holder<String>() {}` rồi kiểm tra `getGenericSuperclass()`; so sánh với `new Holder<String>().getClass().getGenericSuperclass()`.
5. Với `List.of(42)` truyền qua Reflection vào `consume(List<String>)`, giải thích vì sao không có lỗi; với `readFirst(List<String>)`, giải thích `ClassCastException` xuất phát từ đâu.
6. Dùng `javap -v -p` xem descriptor và `Signature` của field `value`, `labels` và superclass `IntegerHolder`. Chỉ ra thông tin nào phục vụ runtime linkage và thông tin nào dùng để mô tả generic declaration.

## 14. Checklist áp dụng thực tế

- Khi cần biết **kiểu dùng để gán/invoke ở runtime**, lấy `Field.getType()`, `Method.getParameterTypes()`, `getReturnType()` và kiểm tra assignability.
- Khi cần đọc **chữ ký generic khai báo**, lấy `getGenericType()`, `getGenericParameterTypes()`, `getGenericReturnType()`, `getGenericSuperclass()` hoặc `getGenericInterfaces()` phù hợp.
- Xác định từng dạng `Type` trước khi dùng; đừng cast `Type` thành `Class<?>` vô điều kiện.
- Khi đi qua generic inheritance, duy trì ánh xạ `TypeVariable → Type` và thay thế qua từng cạnh; không suy từ field declaration riêng lẻ.
- Không coi metadata `List<String>` là kiểm chứng runtime element types; tách schema declaration khỏi validation thực tế.
- Đối với raw Reflection, chuẩn bị cho unchecked conversions, runtime casts và `InvocationTargetException` ở nơi code sử dụng giá trị.
- Với class-file tooling, kiểm tra sự tồn tại và độ hợp lệ của `Signature`; đừng suy đoán tham số kiểu đã bị mất.
- Nếu cần giữ type arguments tại runtime, truyền `Class<T>` hoặc một cấu trúc `Type`/type token phù hợp từ caller, sau đó chủ động kiểm tra dữ liệu.

**Ghi nhớ:** **type erasure** làm những tham số generic như `String` trong `List<String>` không trở thành danh tính runtime của từng object, nhưng **metadata generic của khai báo** có thể vẫn được lưu lại để Reflection đọc. `Class<?>` và `Type` trả lời hai câu hỏi khác nhau; phân biệt chúng là nền tảng để viết code Reflection, serializer và framework generic đúng đắn.