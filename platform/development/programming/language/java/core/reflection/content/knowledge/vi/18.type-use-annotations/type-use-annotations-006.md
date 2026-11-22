# AnnotatedTypeVariable và các bound có annotation trong Java Reflection

## 1. Bài toán: annotation nằm ở vị trí nào của một type variable?

Java hỗ trợ annotation trên **kiểu được sử dụng** (*type-use annotation*) và trên **khai báo tham số kiểu** (*type-parameter declaration*). Khi dùng Reflection để đọc generic, cần phân biệt ba vị trí:

1. Annotation trên **khai báo biến kiểu**: `<@ParameterMark T ...>`.
2. Annotation trên **bound của biến kiểu**: `T extends @BoundMark Number`.
3. Annotation trên **lần sử dụng biến kiểu**: `@UseMark T value` hoặc `Comparable<@UseMark T>`.

Chúng không tự động là cùng một annotation, cũng không nhất thiết nằm trên cùng đối tượng Reflection.

Ví dụ:

```java
class Sample<@ParameterMark T extends @BoundMark Number
        & Comparable<@UseMark T>> {
    @UseMark T value;
}
```

Ở đây:

- `@ParameterMark` gắn với chính **khai báo** `T`.
- `@BoundMark` gắn với **kiểu Number được dùng làm upper bound** của `T`.
- `@UseMark` bên trong `Comparable<@UseMark T>` gắn với **lần dùng `T` làm type argument**.
- `@UseMark` trong `@UseMark T value` gắn với **kiểu của field**, không tự biến thành annotation khai báo của `T`.

Để đọc đúng các vị trí ấy, Java cung cấp `TypeVariable`, `AnnotatedType`, `AnnotatedTypeVariable` và `AnnotatedParameterizedType`.

**Trọng tâm:** `AnnotatedTypeVariable` đại diện cho *một lần sử dụng kiểu là type variable* (chẳng hạn `@UseMark T`), đồng thời cho phép đọc các **annotated upper bounds** của biến kiểu đó bằng `getAnnotatedBounds()`. Đây không phải một `Class<?>` của `T`: generic type variable và class runtime là hai khái niệm khác nhau.

## 2. Các API liên quan và quan hệ giữa chúng

| API | Kiểu trả về | Công dụng |
| --- | --- | --- |
| `Class.getTypeParameters()` | `TypeVariable<?>[]` | Các biến kiểu được khai báo bởi class/interface |
| `Method.getTypeParameters()` | `TypeVariable<Method>[]` | Các biến kiểu được khai báo bởi generic method |
| `Constructor.getTypeParameters()` | `TypeVariable<Constructor<?>>[]` | Các biến kiểu được khai báo bởi generic constructor |
| `TypeVariable.getName()` | `String` | Tên như `T`, `U` |
| `TypeVariable.getBounds()` | `Type[]` | Các upper bounds, **không kèm annotation use-site** |
| `TypeVariable.getAnnotatedBounds()` | `AnnotatedType[]` | Các upper bounds **có thể mang type-use annotation** |
| `TypeVariable.getAnnotation(...)` | annotation hoặc `null` | Annotation trên **khai báo biến kiểu** |
| `Field.getGenericType()` | `Type` | Kiểu generic của field (có thể là `TypeVariable`), chưa diễn tả vị trí type-use annotation |
| `Field.getAnnotatedType()` | `AnnotatedType` | Kiểu của field cùng annotation tại vị trí sử dụng |
| `Method.getAnnotatedReturnType()` | `AnnotatedType` | Kiểu trả về, kể cả annotation tại vị trí sử dụng |
| `Executable.getAnnotatedParameterTypes()` | `AnnotatedType[]` | Các kiểu tham số cùng annotation |
| `AnnotatedTypeVariable.getAnnotatedBounds()` | `AnnotatedType[]` | Các bound có annotation gắn với type variable được tham chiếu |
| `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` | `AnnotatedType[]` | Các type arguments có annotation nằm **bên trong** kiểu tham số hóa |
| `AnnotatedType.getType()` | `Type` | Kiểu nền mà một `AnnotatedType` đại diện |
| `AnnotatedType.getAnnotation(...)` | annotation hoặc `null` | Annotation tại **chính vị trí kiểu** mà đối tượng này đại diện |

Lưu ý: `AnnotatedTypeVariable` là **interface con của `AnnotatedType`**, không phải một đối tượng có thể tạo tùy ý bằng `new AnnotatedTypeVariable(...)`. Ta nhận nó qua các API Reflection, rồi kiểm tra bằng `instanceof`.

### Phân biệt hai lối vào thường gặp

**Lối vào từ khai báo:**

```java
TypeVariable<?> t = Sample.class.getTypeParameters()[0];
AnnotatedType[] annotatedBounds = t.getAnnotatedBounds();
```

**Lối vào từ vị trí dùng:**

```java
Field field = Sample.class.getDeclaredField("value");
AnnotatedType fieldType = field.getAnnotatedType();
if (fieldType instanceof AnnotatedTypeVariable variableUse) {
    AnnotatedType[] bounds = variableUse.getAnnotatedBounds();
}
```

Cả hai đều có thể giúp quan sát những bound thuộc khai báo `T`, nhưng **vị trí dùng** còn mang annotation riêng trên `@UseMark T`. Đừng đọc mỗi `getAnnotatedBounds()` rồi kết luận mọi annotation của field đã được lấy đủ.

Các mảnh code trong mục này minh họa API, cần được đặt trong phương thức có xử lý `NoSuchFieldException` và cùng khai báo class/annotation thích hợp. Chương trình đầy đủ ở mục 4.

## 3. Điều kiện để annotation có mặt khi Reflection chạy

Cần khai báo annotation phù hợp:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParameterMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface BoundMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface UseMark {}
```

Đây là **đoạn minh họa**, yêu cầu import `java.lang.annotation.*`. Trong chương trình hoàn chỉnh bên dưới, các khai báo này nằm trong cùng file.

- `ElementType.TYPE_PARAMETER` nhắm vào **khai báo** biến kiểu như `<@ParameterMark T>`.
- `ElementType.TYPE_USE` nhắm vào **vị trí sử dụng kiểu**, gồm bound `extends @BoundMark Number`, type argument `Comparable<@UseMark T>` hoặc field `@UseMark T value`.
- `RetentionPolicy.RUNTIME` cho phép Reflection nhìn thấy annotation ở runtime. Nếu annotation chỉ có `CLASS` retention hoặc `SOURCE` retention, các API runtime không cung cấp nó như trong ví dụ.
- `@Inherited` không tự làm type-use annotation lan truyền qua giới hạn generic; không nên dùng nó để suy luận về annotated bounds.
- Nếu dùng repeatable annotation, cân nhắc `getAnnotationsByType(...)` thay vì chỉ `getAnnotation(...)`.

**Nhớ phân biệt:** một annotation trên **khai báo T** không tự được copy vào từng lần dùng T; annotation trên **bound của T** cũng không có nghĩa là mọi field kiểu T có annotation ấy tại vị trí của field.

## 4. Ví dụ Java 17+ hoàn chỉnh và kiểm chứng được

Tạo file **`AnnotatedTypeVariableDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParameterMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface BoundMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface UseMark {}

public class AnnotatedTypeVariableDemo {
    static class Sample<@ParameterMark T extends @BoundMark Number
            & Comparable<@UseMark T>> {
        @UseMark T value;
    }

    static class Unbounded<V> {}

    static <@ParameterMark U extends @BoundMark CharSequence>
            @UseMark U echo(@UseMark U value) {
        return value;
    }

    public static void main(String[] args) throws Exception {
        TypeVariable<?> variable = Sample.class.getTypeParameters()[0];
        System.out.println("Variable: " + variable.getName());
        System.out.println("Type-parameter annotation: "
                + (variable.getAnnotation(ParameterMark.class) != null));
        System.out.println("Bounds count: " + variable.getBounds().length);

        AnnotatedType[] bounds = variable.getAnnotatedBounds();
        for (int i = 0; i < bounds.length; i++) {
            System.out.println("Bound " + i + ": "
                    + bounds[i].getType().getTypeName());
            System.out.println("  @BoundMark: "
                    + (bounds[i].getAnnotation(BoundMark.class) != null));
        }

        AnnotatedParameterizedType comparable =
                (AnnotatedParameterizedType) bounds[1];
        AnnotatedType argument =
                comparable.getAnnotatedActualTypeArguments()[0];
        System.out.println("Comparable argument @UseMark: "
                + (argument.getAnnotation(UseMark.class) != null));
        System.out.println("Comparable argument is variable: "
                + (argument instanceof AnnotatedTypeVariable));

        Field field = Sample.class.getDeclaredField("value");
        AnnotatedType fieldType = field.getAnnotatedType();
        System.out.println("Field erased type: "
                + field.getType().getSimpleName());
        System.out.println("Field generic variable: "
                + (field.getGenericType() instanceof TypeVariable));
        System.out.println("Field is variable: "
                + (fieldType instanceof AnnotatedTypeVariable));
        System.out.println("Field use @UseMark: "
                + (fieldType.getAnnotation(UseMark.class) != null));

        AnnotatedTypeVariable reference =
                (AnnotatedTypeVariable) fieldType;
        System.out.println("Field type variable: "
                + reference.getType().getTypeName());
        System.out.println("Field variable bounds: "
                + reference.getAnnotatedBounds().length);

        Method method = AnnotatedTypeVariableDemo.class.getDeclaredMethod(
                "echo", CharSequence.class);
        TypeVariable<?> methodVar = method.getTypeParameters()[0];
        System.out.println("Method variable: " + methodVar.getName());
        System.out.println("Method bound @BoundMark: "
                + (methodVar.getAnnotatedBounds()[0]
                        .getAnnotation(BoundMark.class) != null));
        System.out.println("Method parameter is variable: "
                + (method.getAnnotatedParameterTypes()[0]
                        instanceof AnnotatedTypeVariable));
        System.out.println("Method return @UseMark: "
                + (method.getAnnotatedReturnType()
                        .getAnnotation(UseMark.class) != null));

        AnnotatedType defaultBound =
                Unbounded.class.getTypeParameters()[0]
                        .getAnnotatedBounds()[0];
        System.out.println("Unbounded default: "
                + defaultBound.getType().getTypeName());
        System.out.println("Unbounded annotations: "
                + defaultBound.getAnnotations().length);
    }
}
```

Biên dịch/chạy từ thư mục chứa file bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 AnnotatedTypeVariableDemo.java
java AnnotatedTypeVariableDemo
```

**Stdout thực tế (đã biên dịch và chạy bằng JDK 21 với `--release 17`):**

```text
Variable: T
Type-parameter annotation: true
Bounds count: 2
Bound 0: java.lang.Number
  @BoundMark: true
Bound 1: java.lang.Comparable<T>
  @BoundMark: false
Comparable argument @UseMark: true
Comparable argument is variable: true
Field erased type: Number
Field generic variable: true
Field is variable: true
Field use @UseMark: true
Field type variable: T
Field variable bounds: 2
Method variable: U
Method bound @BoundMark: true
Method parameter is variable: true
Method return @UseMark: true
Unbounded default: java.lang.Object
Unbounded annotations: 0
```

### Giải thích bốn phát hiện quan trọng

**(1) Khai báo `T` và bound `Number` là hai nơi khác nhau.**

`variable.getAnnotation(ParameterMark.class)` trả annotation trên **khai báo type parameter** `T`. Trong khi đó, `bounds[0].getAnnotation(BoundMark.class)` trả annotation trên **kiểu Number đang làm bound**. Nếu dùng `variable.getAnnotation(BoundMark.class)` để hỏi “Number có annotation không?”, bạn đã hỏi sai đối tượng Reflection.

**(2) Annotated bound có thể là generic/parameterized type.**

Bound thứ hai là `Comparable<T>`. Cờ `@UseMark` không nằm trên chính đối tượng `bounds[1]` (vỏ `Comparable`); nó nằm **bên trong type argument `T`**. Vì vậy cần cast đúng kiểu:

```java
AnnotatedParameterizedType apt =
        (AnnotatedParameterizedType) bounds[1];
AnnotatedType inner = apt.getAnnotatedActualTypeArguments()[0];
boolean marked = inner.isAnnotationPresent(UseMark.class);
```

Với trường hợp này, `inner` còn là `AnnotatedTypeVariable` vì type argument được sử dụng là `T`. Nếu chỉ gọi `bounds[1].getAnnotations()` rồi dừng, bạn sẽ bỏ sót annotation lồng sâu.

**(3) Một field kiểu `T` vừa có generic type vừa có annotated type.**

`field.getType()` trả `Number.class` do **type erasure**: trong `T extends Number & Comparable<T>`, erasure của `T` là first bound `Number`. `field.getGenericType()` vẫn biểu diễn `T` dưới dạng `TypeVariable`. `field.getAnnotatedType()` trả một `AnnotatedTypeVariable` có annotation trên lần dùng `@UseMark T`.

Ba API nói về **ba tầng thông tin khác nhau**, không mâu thuẫn:

| Lệnh trên field `@UseMark T value` | Thông tin nhận được |
| --- | --- |
| `field.getType()` | Runtime erased type: `Number.class` |
| `field.getGenericType()` | Generic type: `TypeVariable` tên `T` |
| `field.getAnnotatedType()` | `AnnotatedTypeVariable` biểu diễn `@UseMark T` |
| `((AnnotatedTypeVariable) field.getAnnotatedType()).getAnnotatedBounds()` | Hai bound: `@BoundMark Number` và `Comparable<@UseMark T>` |

**(4) Generic method cũng có type variable riêng.**

`echo` khai báo `<@ParameterMark U extends @BoundMark CharSequence>`. Do erasure của `U` là `CharSequence`, muốn tìm method bằng `getDeclaredMethod` phải truyền `CharSequence.class`, không phải `Object.class` hoặc một lớp bất kỳ của giá trị được gọi.

`method.getTypeParameters()[0]` đại diện cho **khai báo U**; `getAnnotatedParameterTypes()[0]` và `getAnnotatedReturnType()` đại diện cho **vị trí dùng U ở parameter/return**. Chương trình quan sát cả ba vị trí này.

## 5. Cách dùng `AnnotatedTypeVariable.getAnnotatedBounds()`

Giả sử từ field, parameter hoặc return type có `AnnotatedType annotated`:

```java
if (annotated instanceof AnnotatedTypeVariable variableUse) {
    for (AnnotatedType bound : variableUse.getAnnotatedBounds()) {
        System.out.println(bound.getType().getTypeName());
        for (Annotation mark : bound.getAnnotations()) {
            System.out.println(mark.annotationType().getName());
        }
    }
}
```

Đây là **đoạn minh họa** cần import `java.lang.annotation.Annotation` và `java.lang.reflect.*`; biến `annotated` do caller cung cấp.

Quy trình đúng:

1. Kiểm tra bằng `instanceof AnnotatedTypeVariable` trước khi cast. Field có thể là `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType` hoặc kiểu không generic chứ không phải type variable.
2. Lấy `getType()`; với `AnnotatedTypeVariable`, đối tượng `Type` nền tương ứng là một `TypeVariable<?>`.
3. Gọi `getAnnotatedBounds()` để lấy **từng upper bound**, theo đúng thứ tự khai báo.
4. Trên mỗi bound, đọc annotation gắn **trực tiếp tại bound** bằng `getAnnotations()`, `getAnnotation(...)` hoặc `getAnnotationsByType(...)`.
5. Nếu bound có generic type arguments, cast có kiểm tra sang `AnnotatedParameterizedType` rồi duyệt `getAnnotatedActualTypeArguments()` để tìm annotation lồng bên trong.
6. Nếu cần biết annotation tại **lần dùng type variable**, đọc `variableUse.getAnnotations()`; chúng không được thay thế bằng annotation trên bound.

### Bound nhiều thành phần

Java hỗ trợ upper bound dạng intersection:

```java
class Sample<T extends Number & Comparable<T>> {}
```

`T` có hai upper bounds theo thứ tự `Number` và `Comparable<T>`. `TypeVariable.getBounds()` và `getAnnotatedBounds()` đều biểu diễn **hai vị trí**; khác nhau ở chỗ API annotated bảo tồn metadata annotation trên cách dùng từng kiểu bound.

Không được giả định chỉ có một bound. Đối với intersection, class bound (nếu có) phải đứng đầu, còn các interface bounds xuất hiện tiếp theo theo quy tắc Java. Các annotation tương ứng được gắn với đúng thành phần mà chúng đứng trước.

Nếu **không khai báo bound**:

```java
class Plain<T> {}
```

bound mặc định của `T` là `Object` và không có annotation. `getAnnotatedBounds()` trả mảng chứa một `AnnotatedType` cho `Object` không được annotate; nó **không** trả mảng rỗng. Điều này được chứng minh bởi `Unbounded<V>` trong ví dụ chạy ở mục 4.

## 6. Đọc annotation khai báo khác đọc annotation trên kiểu

| Cú pháp trong source | Nơi lấy annotation | Thực thể metadata |
| --- | --- | --- |
| `<@ParameterMark T>` | `typeVariable.getAnnotation(ParameterMark.class)` | Khai báo biến kiểu |
| `T extends @BoundMark Number` | `typeVariable.getAnnotatedBounds()[0].getAnnotation(BoundMark.class)` | Upper bound |
| `Comparable<@UseMark T>` | Cast bound `AnnotatedParameterizedType` rồi lấy annotated argument | Type argument trong bound |
| `@UseMark T value` | `field.getAnnotatedType().getAnnotation(UseMark.class)` | Lần dùng T trong field |
| `@UseMark U echo(...)` | `method.getAnnotatedReturnType().getAnnotation(UseMark.class)` | Lần dùng U ở return type |
| `echo(@UseMark U value)` | `method.getAnnotatedParameterTypes()[0].getAnnotation(UseMark.class)` | Lần dùng U ở parameter |

**Tránh nhầm:** `TypeVariable` là `AnnotatedElement` và có thể trả annotation từ khai báo type parameter; nhưng `AnnotatedTypeVariable` triển khai `AnnotatedType` và biểu diễn annotation gắn vào **type use cụ thể**. Cùng tên `getAnnotation(...)` nhưng câu hỏi đặt cho hai đối tượng là khác nhau.

Một số annotation có `@Target` cho nhiều nơi, ví dụ vừa `TYPE_PARAMETER` vừa `TYPE_USE`. Khi ấy việc kiểm tra vị trí vẫn quan trọng; tên annotation giống nhau không có nghĩa runtime luôn lưu chúng tại cùng một loại target.

## 7. Generic erasure: Annotation trên bound không làm thay đổi runtime class

Có hai vấn đề độc lập:

- **Generic signature** mô tả `T extends Number & Comparable<T>`. Reflection truy cập qua `TypeVariable` và các `Type` con.
- **Runtime erased type** của field `T value` là `Number` khi `Number` là bound đầu. Kiểu bị xóa không lưu “đối tượng này là một subtype cụ thể của T” ở runtime.
- **TYPE_USE annotation** mô tả chú giải về những vị trí kiểu trong chữ ký, không tự thực thi ràng buộc kiểm tra dữ liệu khi runtime chạy.

Ví dụ nếu `@BoundMark` mang nghĩa nghiệp vụ “đã được xác thực”, Reflection chỉ đọc được marker đó. Việc kiểm tra dữ liệu thật sự vẫn cần validator/framework riêng; JVM không thay thế code kiểm tra dựa chỉ vào type-use marker tùy chỉnh.

Một generic field chứa type variable không thể được dùng để suy ra tự động `T` là `Integer` hay `Long` trên một object cụ thể do type erasure. Nếu cần actual type arguments của một superclass/interface đã được parameterize, phải phân tích `ParameterizedType` từ vị trí khai báo sử dụng phù hợp và cân nhắc kế thừa; đó là bài toán khác với đọc annotation trên upper bound.

## 8. Khi bound là parameterized, array hoặc wildcard type

`AnnotatedType` có các subtype chuyên biệt và mỗi subtype mở thêm tầng cấu trúc:

| Hình dạng kiểu | Subtype nên kiểm tra | Cách đi sâu |
| --- | --- | --- |
| `T` | `AnnotatedTypeVariable` | `getAnnotatedBounds()` |
| `List<@A String>` | `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` |
| `@A String[]` hoặc `String @A []` | `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |
| `? extends @A Number` | `AnnotatedWildcardType` | `getAnnotatedUpperBounds()` |
| `? super @A Integer` | `AnnotatedWildcardType` | `getAnnotatedLowerBounds()` |

Mỗi cấp có thể mang annotation riêng. Không nên chỉ gọi `getAnnotations()` ở nút ngoài cùng rồi kết luận đã lấy đủ mọi annotation lồng bên trong.

**Đặc biệt với recursive bounds:**

```java
interface Node<T extends Comparable<T>> {}
```

Một type variable có thể xuất hiện lại bên trong bound của chính nó (*F-bounded polymorphism*). Nếu viết trình duyệt metadata đệ quy từ `T` → `Comparable<T>` → `T` → bound..., sẽ lặp vô hạn nếu không đánh dấu đã thăm.

Khi viết trình duyệt tổng quát, cần lưu dấu các khai báo `TypeVariable<?>` đã đi qua theo ngữ cảnh (chẳng hạn tập các variable đã thăm); phân biệt **annotation trên lần dùng hiện tại** và **việc mở rộng bound khai báo**. Có thể vẫn ghi lại annotation của nút dùng trước khi quyết định không duyệt lại các bound của nó.

`AnnotatedTypeVariable.getAnnotatedOwnerType()` trả `null` theo hợp đồng API; owner type dành cho những dạng nested member type khác, không phải cơ chế tìm khai báo của `T`. Nếu cần biết biến kiểu `T` được khai báo ở class/method/constructor nào, dùng `((TypeVariable<?>) annotated.getType()).getGenericDeclaration()`.

## 9. Áp dụng trong công cụ phân tích generic/annotation

Một schema generator, validation framework hoặc API documentation tool có thể dùng annotated bounds để hiểu ràng buộc về dạng kiểu và metadata ở đúng vị trí. Quy trình thực tế:

1. Xác định nguồn: type variable khai báo của **class**, **method** hoặc **constructor**, hay type variable được dùng tại **field/parameter/return**.
2. Lấy metadata khai báo qua `getTypeParameters()` khi cần type parameter annotations.
3. Lấy annotated type của vị trí dùng qua `getAnnotatedType()`, `getAnnotatedReturnType()` hoặc `getAnnotatedParameterTypes()`.
4. Phân nhánh theo subtype `AnnotatedType` bằng `instanceof`; với variable, đọc `getAnnotatedBounds()`; với parameterized bound, duyệt annotated type arguments.
5. Phân biệt annotation trên khai báo type variable, trên bound và trên type use. Không chuyển annotation từ vị trí này sang vị trí khác khi chưa có quy tắc nghiệp vụ rõ ràng.
6. Đối với classfile từ compiler khác hoặc thư viện không có RUNTIME retention, chấp nhận metadata annotation vắng mặt mà không tự suy diễn rằng annotation chưa từng tồn tại ở source.
7. Chống vòng lặp khi F-bounded/recursive generics; xử lý `TypeNotPresentException` và `MalformedParameterizedTypeException` khi metadata generic hỏng hoặc tham chiếu kiểu không khả dụng.
8. Viết test trên classfile thực tế để xác nhận cách khai báo annotation, thứ tự bound và vị trí nested annotation.

### Một helper nhỏ để báo cáo annotated bounds

Đặt method sau trong class tiện ích có import `java.lang.reflect.*` và `java.lang.annotation.*`:

```java
static void printDirectBoundAnnotations(TypeVariable<?> variable) {
    for (AnnotatedType bound : variable.getAnnotatedBounds()) {
        System.out.println("Bound: " + bound.getType().getTypeName());
        for (Annotation annotation : bound.getDeclaredAnnotations()) {
            System.out.println("  @" + annotation.annotationType().getSimpleName());
        }
    }
}
```

Đây là **mảnh code minh họa**, chỉ đọc annotation gắn trực tiếp vào từng **bound ở lớp ngoài**, không duyệt sâu type arguments. Với `Comparable<@UseMark T>`, nếu muốn nhận `@UseMark`, phải bổ sung bước duyệt `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` như mục 4.

## 10. Những nhầm lẫn phổ biến

| Nhầm lẫn | Kết luận đúng |
| --- | --- |
| “`TypeVariable.getBounds()` trả cả annotation.” | `getBounds()` trả `Type[]`; dùng `getAnnotatedBounds()` để lấy annotation |
| “`AnnotatedTypeVariable` là class runtime tương đương T.” | Đây là metadata của type-variable use; `getType()` là `TypeVariable`, không phải `Class<?>` cụ thể |
| “Annotation của `<@P T>` là annotation của mọi bound T.” | Annotation trên khai báo và annotation trên bound nằm ở hai vị trí khác nhau |
| “`T extends @A Number` làm mọi `@T` field có `@A`.” | Annotation trên bound không tự chuyển sang vị trí field |
| “Đọc `bounds[1].getAnnotations()` là đủ lấy cả `Comparable<@A T>`.” | Annotation type argument lồng trong `AnnotatedParameterizedType` |
| “Không khai báo `extends` thì annotated bounds rỗng.” | Có bound `Object` mặc định, không annotate |
| “Một biến kiểu chỉ có một bound.” | Có thể có nhiều upper bounds nối bằng `&` |
| “`field.getType()` trả TypeVariable.” | `getType()` trả erased `Class<?>`; dùng `getGenericType()` |
| “Annotation TYPE_USE mặc định đọc được ở runtime.” | Muốn Reflection đọc được thì cần `RetentionPolicy.RUNTIME` |
| “F-bound có thể mở rộng đệ quy không giới hạn.” | Dễ tạo vòng lặp; cần đánh dấu type variable đã duyệt |
| “Metadata type-use tự validate dữ liệu.” | Marker được lưu để công cụ khác diễn giải, không tự chạy validator |

## 11. Câu hỏi tự kiểm tra

1. Với `class Box<@ParameterMark T extends @BoundMark Number> {}`, muốn đọc `@ParameterMark` và `@BoundMark` dùng hai API nào?
2. Vì sao `Field.getGenericType()` và `Field.getAnnotatedType()` cung cấp thông tin khác nhau?
3. Với `Comparable<@UseMark T>` là upper bound, `@UseMark` nằm trên đối tượng `AnnotatedType` của `Comparable` hay trên type argument bên trong?
4. Nếu một type variable không khai báo `extends`, `getAnnotatedBounds()` có bao nhiêu phần tử và đó là kiểu gì?
5. `AnnotatedTypeVariable.getAnnotatedBounds()` có ý nghĩa gì khi `AnnotatedTypeVariable` được lấy từ field `@UseMark T value`?
6. Vì sao cần `@Target(TYPE_USE)` và `@Retention(RUNTIME)` đối với annotation muốn đọc trên bound qua Reflection?
7. Một field kiểu `T extends Number & Comparable<T>` có `getType()` là `T` hay `Number.class`? Làm thế nào đọc lại `T` ở mức generic?
8. Điều gì có thể xảy ra nếu trình duyệt bound tự mở rộng `T extends Comparable<T>` mà không phát hiện chu trình?

**Đáp án:** (1) `TypeVariable.getAnnotation(...)` và `TypeVariable.getAnnotatedBounds()[0].getAnnotation(...)`; (2) một bên là loại generic nền, bên kia có type-use annotations; (3) type argument bên trong; (4) một `Object` không annotate; (5) trả annotated upper bounds của T, còn annotation trực tiếp tại field đọc trên chính `AnnotatedTypeVariable`; (6) đúng target và runtime visibility; (7) `Number.class`, dùng `getGenericType()`/`getAnnotatedType()`; (8) lặp vô hạn/stack overflow.

## 12. Kết luận

**AnnotatedTypeVariable giúp phân tích một lần sử dụng type variable có annotation và tìm các upper bounds có thể được annotate.** Để đọc chính xác, hãy tách ba tầng: *type-parameter declaration*, *bound type use* và *variable type use*. Sử dụng `TypeVariable.getAnnotatedBounds()` hoặc `AnnotatedTypeVariable.getAnnotatedBounds()` cho bound, và dùng các subtype `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType` để tìm annotation bên trong cấu trúc kiểu phức tạp. Chỉ dữ liệu generic/annotation còn hiện diện ở classfile runtime mới đọc được; Reflection không tự loại bỏ type erasure hoặc thay thế kiểm tra nghiệp vụ.

Tài liệu chính thức:

- [Java SE 21 — AnnotatedTypeVariable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedTypeVariable.html).
- [Java SE 21 — TypeVariable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html).
- [Java SE 21 — AnnotatedType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html).
- [Java SE 21 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
- [JLS 17 `4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4) và [JLS 17 `9.7.4 — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4).