# Annotation trên khai báo tham số kiểu và giới hạn kiểu trong Java Core

Trong Java generics, một tham số kiểu như `T` trong `class Box<T>` là **một khai báo tham số kiểu** (*type parameter declaration*). Nếu viết `T extends Number & Comparable<T>`, các kiểu `Number` và `Comparable<T>` là **giới hạn trên** (*upper bounds*) của tham số đó. Java cho phép đặt annotation ở **hai vị trí có ý nghĩa khác nhau**: trên chính khai báo `T` và trên những kiểu được dùng làm giới hạn của `T`.

Phân biệt hai vị trí là trọng tâm của bài:

~~~java
class Box<@ParamInfo T extends @BoundInfo Number & @BoundInfo Comparable<T>> {}
~~~

`@ParamInfo` đứng trước **tên tham số kiểu `T`**, trong khi `@BoundInfo` đứng trước **kiểu giới hạn `Number` hoặc `Comparable<T>`**. Ví dụ trên chỉ minh họa vị trí, giả định các annotation type tương ứng đã được định nghĩa. Hai dạng annotation có target, ý nghĩa và API Reflection cần dùng khác nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn cần giải thích và thực hành được:

- Phân biệt *type parameter* `T` với *type argument* `String` trong `Box<String>` và với *upper bound* trong `T extends Number`.
- Viết annotation trên khai báo type parameter của class, interface và generic method.
- Gắn annotation vào một hoặc nhiều type bounds, kể cả các thành phần sau dấu `&`.
- Hiểu sự khác nhau giữa `ElementType.TYPE_PARAMETER` và `ElementType.TYPE_USE`.
- Dùng Reflection để lấy `TypeVariable<?>`, đọc annotation tại **khai báo** với `getAnnotation(...)`, và đọc annotation trên **bound** với `getAnnotatedBounds()`.
- Đọc annotation trong type argument lồng bên trong một parameterized bound bằng `AnnotatedParameterizedType` khi cần.
- Nắm giới hạn của metadata: annotation không tự thay đổi khả năng gán kiểu, quan hệ kế thừa, erasure hay kiểm tra null.
- Tránh các lỗi cú pháp và nhầm lẫn phổ biến với `@Target`, `@Retention` và các API generic Reflection.

## 2. Ôn cú pháp generic: tham số kiểu, đối số kiểu và bound

Ví dụ:

~~~java
class Store<T> {
    private T item;

    public Store(T item) {
        this.item = item;
    }

    public T get() {
        return item;
    }
}
~~~

Ở đây `T` trong `Store<T>` là **tham số kiểu được khai báo**. Khi viết `Store<String>`, `String` là **đối số kiểu** được cung cấp tại một chỗ sử dụng kiểu. Chúng liên quan nhưng không phải cùng một vị trí trong cú pháp.

Giới hạn trên đặt sau `extends`:

~~~java
class NumericStore<T extends Number> {}
~~~

`T extends Number` nghĩa là type argument dùng cho `T` phải thỏa mãn bound `Number`. Với nhiều bounds:

~~~java
class ComparableNumber<T extends Number & Comparable<T>> {}
~~~

`T` cần thỏa cả hai: là subtype của `Number` và triển khai `Comparable<T>`. Ví dụ `Integer` đáp ứng điều kiện này vì `Integer` là `Number` và triển khai `Comparable<Integer>`.

Quy tắc thông thường của Java vẫn áp dụng khi thêm annotation:

- Nếu có **class bound** cụ thể thì class bound đứng đầu, trước các interface bounds.
- Có thể có nhiều interface bounds, phân cách bởi `&`; không được liệt kê hai class bounds.
- Nếu không viết bound, type variable có upper bound mặc định là `Object`.
- Annotation không làm kiểu không tương thích trở thành hợp lệ; compiler vẫn kiểm tra giới hạn generic như bình thường.

Ví dụ minh họa đối với `ComparableNumber`: `ComparableNumber<Integer>` hợp lệ về mặt giới hạn; `ComparableNumber<String>` không hợp lệ vì `String` không kế thừa `Number`.

## 3. `TYPE_PARAMETER`: annotation trên khai báo tham số kiểu

Để đánh dấu chính tên tham số kiểu, khai báo annotation có target `TYPE_PARAMETER`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParamInfo {
    String value();
}
~~~

Cách dùng trên khai báo của class, interface và method:

~~~java
class Holder<@ParamInfo("class-T") T> {}

interface Provider<@ParamInfo("interface-E") E> {}

class Utility {
    public <@ParamInfo("method-R") R> R identity(R value) {
        return value;
    }
}
~~~

Các đoạn trên minh họa riêng cú pháp; có thể lưu chúng cùng các annotation type đã khai báo nếu cần biên dịch.

`@ParamInfo("class-T")` mô tả **khai báo của tham số `T`**, không mô tả từng giá trị cụ thể được chứa bởi `Holder<T>` và không tự áp dụng cho tất cả những chỗ sử dụng `T` sau đó.

Annotation declaration này được đọc qua đối tượng `TypeVariable` do Reflection trả về:

~~~java
java.lang.reflect.TypeVariable<?> typeParameter =
        Holder.class.getTypeParameters()[0];

ParamInfo info = typeParameter.getAnnotation(ParamInfo.class);
System.out.println(typeParameter.getName()); // T
System.out.println(info.value());            // class-T
~~~

`Class.getTypeParameters()` trả các tham số kiểu **được khai báo bởi chính class**, theo thứ tự khai báo. Tương tự, `Method.getTypeParameters()` hoặc `Constructor.getTypeParameters()` dành cho các type parameters được khai báo trên generic method/constructor tương ứng. `TypeVariable` triển khai `AnnotatedElement` nên có thể dùng `getAnnotation(...)`, `getAnnotations()` và những API tra cứu metadata thông thường.

Điều kiện để ví dụ Reflection đọc được `@ParamInfo` là retention `RUNTIME`. Nếu đổi thành `CLASS`, metadata có thể còn trong `.class` nhưng không truy vấn được bằng Reflection runtime tiêu chuẩn; `SOURCE` sẽ không lưu annotation usage đó vào class file.

## 4. `TYPE_USE`: annotation trên kiểu được dùng làm giới hạn

Giới hạn như `Number` và `Comparable<T>` là **những chỗ sử dụng kiểu**. Annotation dùng ở đây thường khai báo `@Target(ElementType.TYPE_USE)`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface BoundInfo {
    String value();
}
~~~

Cách gắn:

~~~java
class Box<T extends @BoundInfo("number") Number
        & @BoundInfo("comparable") Comparable<T>> {}
~~~

Ở đây có hai metadata độc lập: một annotation trên việc dùng kiểu `Number` làm bound đầu, và một annotation trên việc dùng kiểu `Comparable<T>` làm bound thứ hai.

Dấu `&` là cú pháp intersection của các bounds. Mỗi annotation nằm ngay trước type tương ứng, kể cả type đứng sau `&`. Không đặt annotation của bound trước tên `T` rồi mặc định nó sẽ mô tả `Number`.

### So sánh vị trí và target

| Vị trí mã nguồn | Ví dụ | Target phù hợp | Reflection cần dùng |
| --- | --- | --- | --- |
| Khai báo type parameter | `class C<@ParamInfo T>` | `TYPE_PARAMETER` | `C.class.getTypeParameters()[0].getAnnotation(...)` |
| Bound thứ nhất | `T extends @BoundInfo Number` | `TYPE_USE` | `TypeVariable.getAnnotatedBounds()[0]` rồi `getAnnotation(...)` |
| Bound tiếp theo | `T extends Number & @BoundInfo Comparable<T>` | `TYPE_USE` | `getAnnotatedBounds()[1]` |
| Type argument trong bound | `Comparable<@BoundInfo T>` | `TYPE_USE` | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` |

**Lưu ý về `TYPE_USE`:** Theo định nghĩa Java, target `TYPE_USE` cũng cho phép annotation xuất hiện trên **khai báo tham số kiểu** như một tiện ích của ngôn ngữ. Vì vậy, đừng nói rằng annotation trước `T` *bắt buộc* có target `TYPE_PARAMETER`. Điều đúng là: `TYPE_PARAMETER` chuyên biệt cho vị trí khai báo type parameter; `TYPE_USE` dùng cho các vị trí sử dụng kiểu, bao gồm bound, và cũng có thể dùng tại khai báo type parameter theo quy định Java. Ngược lại, một annotation **chỉ** có target `TYPE_PARAMETER` không hợp lệ khi đặt trực tiếp trước kiểu bound `Number`.

Mẫu tổng hợp rõ ràng:

~~~java
class Box<
    @ParamInfo("T") T extends
        @BoundInfo("number") Number
        & @BoundInfo("comparable") Comparable<T>
> {}
~~~

Nếu bạn dùng hai annotation type riêng, mã và Reflection thể hiện tường minh ý nghĩa: `ParamInfo` mô tả khai báo `T`; `BoundInfo` mô tả các type uses trong danh sách bounds.

## 5. Ví dụ Java 17+ đầy đủ: đọc declaration và bounds bằng Reflection

Tạo file **`TypeParameterAnnotationsDemo.java`** với toàn bộ mã sau. Các annotation type cùng class phụ không `public`; class `TypeParameterAnnotationsDemo` là class `public` duy nhất nên tên file phải khớp.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface ParamInfo {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface BoundInfo {
    String value();
}

class Box<
    @ParamInfo("T") T extends
        @BoundInfo("number") Number
        & @BoundInfo("comparable") Comparable<@BoundInfo("argument") T>
> {
    public <@ParamInfo("U") U extends @BoundInfo("sequence") CharSequence>
    U echo(U input) {
        return input;
    }
}

class Free<@ParamInfo("V") V> {}

public class TypeParameterAnnotationsDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        TypeVariable<?> t = Box.class.getTypeParameters()[0];

        System.out.println("name=" + t.getName());
        System.out.println("declaration="
                + t.getAnnotation(ParamInfo.class).value());
        System.out.println("bounds=" + Arrays.toString(t.getBounds()));

        for (AnnotatedType bound : t.getAnnotatedBounds()) {
            BoundInfo tag = bound.getAnnotation(BoundInfo.class);
            System.out.println("bound=" + bound.getType().getTypeName()
                    + ", tag=" + tag.value());
        }

        AnnotatedParameterizedType comparableBound =
                (AnnotatedParameterizedType) t.getAnnotatedBounds()[1];
        AnnotatedType argument =
                comparableBound.getAnnotatedActualTypeArguments()[0];
        System.out.println("argument="
                + argument.getAnnotation(BoundInfo.class).value());

        Method method = Box.class.getDeclaredMethod(
                "echo", CharSequence.class);
        TypeVariable<?> u = method.getTypeParameters()[0];
        System.out.println("method=" + u.getName() + ":"
                + u.getAnnotation(ParamInfo.class).value());
        System.out.println("methodBound=" + u.getAnnotatedBounds()[0]
                .getAnnotation(BoundInfo.class).value());

        TypeVariable<?> v = Free.class.getTypeParameters()[0];
        System.out.println("freeBound="
                + v.getAnnotatedBounds()[0].getType().getTypeName());
        System.out.println("freeAnnotations="
                + v.getAnnotatedBounds()[0].getAnnotations().length);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 TypeParameterAnnotationsDemo.java
java TypeParameterAnnotationsDemo
~~~

**Stdout dự kiến:**

~~~text
name=T
declaration=T
bounds=[class java.lang.Number, java.lang.Comparable<T>]
bound=java.lang.Number, tag=number
bound=java.lang.Comparable<T>, tag=comparable
argument=argument
method=U:U
methodBound=sequence
freeBound=java.lang.Object
freeAnnotations=0
~~~

### Giải thích từng phần

1. `Box.class.getTypeParameters()[0]` lấy `TypeVariable` đại diện cho `T`; `t.getName()` trả `"T"`.
2. `t.getAnnotation(ParamInfo.class)` đọc annotation trên **khai báo `T`**, trả `"T"` từ element `value()`.
3. `t.getBounds()` trả `Type[]` của các bounds; nội dung cho biết `Number` và `Comparable<T>` nhưng không phải API để đọc các annotation được đặt trên các type-use bounds.
4. `t.getAnnotatedBounds()` trả `AnnotatedType[]` theo đúng thứ tự bounds đã khai báo. Đọc `@BoundInfo` trên từng `AnnotatedType` nhận `"number"` và `"comparable"`.
5. Bound `Comparable<@BoundInfo("argument") T>` là một parameterized type. `AnnotatedParameterizedType` giữ cấu trúc annotated type argument. `getAnnotatedActualTypeArguments()[0]` đưa tới chỗ dùng `T` bên trong `Comparable<T>`, nơi có annotation `"argument"`.
6. Generic method `echo` khai báo **tham số kiểu riêng `U`**, không phải sử dụng lại `T` của class. `Method.getTypeParameters()[0]` lấy `U`, còn `u.getAnnotatedBounds()[0]` đọc annotation `"sequence"` trên bound `CharSequence`.
7. `Free<V>` không khai báo upper bound. Reflection vẫn trả **một bound ngầm định `Object` không có annotation** qua `getAnnotatedBounds()`, do đó hai dòng cuối là `java.lang.Object` và `0`.
8. Lệnh `getDeclaredMethod("echo", CharSequence.class)` dùng tham số `CharSequence.class` vì method `echo(U)` có bound đầu `CharSequence` và **erasure** của `U` là `CharSequence`. Không dùng `Object.class` cho chữ ký method này.

Mã ví dụ chỉ **đọc** metadata. Nó không cần tạo instance `Box` hay gọi `echo`. Việc gắn `@ParamInfo` và `@BoundInfo` không tự chèn runtime validation hoặc kiểm tra null.

## 6. Điều gì được lưu trong class file?

Trong chương trình này, cả `ParamInfo` và `BoundInfo` đều có retention `RUNTIME`, nên `javac` ghi metadata cần thiết vào file `.class`:

- Annotation trên **type parameter declaration** có thông tin mục tiêu liên quan đến tham số kiểu của class hoặc method.
- Annotation trên **upper bound** có thông tin mục tiêu liên quan đến bound nào của tham số kiểu nào.
- Annotation trên **type argument** `T` bên trong `Comparable<T>` còn mang đường dẫn đến vị trí type argument trong cấu trúc kiểu.

Các annotation dạng này thuộc cơ chế **type annotations** được Java bổ sung từ Java 8; chúng thường được biểu diễn trong thuộc tính class file `RuntimeVisibleTypeAnnotations` khi retention là `RUNTIME`. Cấu trúc lưu metadata cho phép phân biệt việc annotation gắn ở `T`, bound `Number`, bound `Comparable<T>` hay type argument bên trong bound. Chúng không chỉ là chuỗi văn bản `@...` ghép vào tên kiểu.

Để kiểm tra, sau khi biên dịch có thể chạy:

~~~bash
javap -v Box
~~~

Trong phần dữ liệu chi tiết, tìm `RuntimeVisibleTypeAnnotations` và các mục liên quan tới **CLASS_TYPE_PARAMETER**, **CLASS_TYPE_PARAMETER_BOUND**, **METHOD_TYPE_PARAMETER** hoặc **METHOD_TYPE_PARAMETER_BOUND** (tên hiển thị có thể phụ thuộc phiên bản `javap`). Nếu kiểm tra riêng `ParamInfo.class` và `BoundInfo.class`, bạn còn thấy các meta-annotations mô tả target/retention của chúng. Không nên dự đoán các chỉ số constant pool hoặc bytecode offset; chúng là chi tiết compiler.

Truy vấn Reflection bằng `getAnnotation(...)` cần annotation có retention `RUNTIME`. Nếu khai báo `SOURCE` hoặc `CLASS`, khả năng lưu trong binary/khả năng đọc runtime thay đổi theo retention. Đó là quy tắc của annotation, độc lập với kiểu `T` được giới hạn ra sao.

## 7. Phân biệt `TypeVariable` và `AnnotatedType`

Khi debug annotations của generics, hãy đặt câu hỏi “mình muốn đọc annotation **trên khai báo** hay **trên một lần sử dụng kiểu**?”

### 7.1. `TypeVariable<?>` đại diện cho tham số kiểu đã khai báo

Ví dụ `Box.class.getTypeParameters()[0]` là một `TypeVariable` cho `T`. Nó có:

- `getName()` để lấy tên `T`.
- `getGenericDeclaration()` để biết khai báo generic nào tạo ra `T` (class, method hoặc constructor).
- `getBounds()` trả các `Type` đại diện cho các giới hạn, không giữ lớp API annotations.
- `getAnnotatedBounds()` trả các `AnnotatedType` đại diện cho **cách các kiểu bound được viết và annotated**.
- Các API `AnnotatedElement` như `getAnnotation(ParamInfo.class)` để lấy metadata gắn trên **khai báo tham số kiểu**.

Ví dụ:

~~~java
TypeVariable<?> t = Box.class.getTypeParameters()[0];
ParamInfo declaration = t.getAnnotation(ParamInfo.class);
AnnotatedType firstBound = t.getAnnotatedBounds()[0];
BoundInfo bound = firstBound.getAnnotation(BoundInfo.class);
~~~

Đây là đoạn minh họa sử dụng type trong chương trình đầy đủ. `declaration` và `bound` đang đọc **hai nơi khác nhau**, dù cả hai có liên quan đến cùng `T`.

### 7.2. `AnnotatedType` đại diện cho kiểu được sử dụng và annotation trên nó

`AnnotatedType` có `getType()` để lấy type bên dưới và các API annotation như `getAnnotation(...)`. Khi kiểu có cấu trúc phức tạp, những subtype của `AnnotatedType` biểu diễn các phần cấu trúc:

- `AnnotatedParameterizedType` cho parameterized type, có `getAnnotatedActualTypeArguments()`.
- `AnnotatedArrayType` cho array type, có `getAnnotatedGenericComponentType()`.
- `AnnotatedWildcardType` cho wildcard có upper/lower bounds, có các API lấy annotated bounds.
- `AnnotatedTypeVariable` cho **một lần sử dụng type variable** ở vị trí kiểu, có thể cung cấp thông tin annotated bounds của variable.

Đừng nhầm `AnnotatedTypeVariable` (một dạng annotated *use* của type variable) với `TypeVariable` (đại diện cho type variable trong khai báo generics). Muốn đọc annotation trên `<@ParamInfo T>`, bắt đầu từ `getTypeParameters()` của declaration. Muốn đọc annotation trên `extends @BoundInfo Number`, bắt đầu từ `t.getAnnotatedBounds()`.

### 7.3. Type parameter declaration khác type argument

~~~java
class Bucket<@ParamInfo("decl") T> {}

class Example {
    Bucket<@BoundInfo("use") String> names;
}
~~~

`@ParamInfo("decl")` đánh dấu **`T` tại nơi khai báo `Bucket`**. `@BoundInfo("use")` đánh dấu **việc dùng `String` làm type argument** cho field `names`. Annotation ở field type argument thường cần truy vấn bắt đầu từ `Field.getAnnotatedType()`, rồi xét `AnnotatedParameterizedType`.

Một object `Bucket<String>` không mang ý nghĩa “annotation trên `T` tự được chuyển thành annotation trên `String`”. Java không tự lan truyền annotation của declaration sang mọi argument hoặc reference.

## 8. Annotation không thay thế quy tắc generic bounds

Giới hạn generic `T extends Number & Comparable<T>` do **hệ thống kiểu Java** kiểm tra. Thêm `@BoundInfo("number")` chỉ bổ sung metadata; nó không biến một class thiếu `Comparable<T>` thành hợp lệ và không làm việc kiểm tra bounds xảy ra lúc runtime.

Ví dụ sai về type argument:

~~~java
// Sai về giới hạn generics: String không extends Number.
// Box<String> invalid;
~~~

Ở chiều ngược lại, `Box<Integer>` phù hợp về mặt generic bound, dù annotation trên bound tên `"number"` hay `"comparable"`. Những chuỗi này không phải điều kiện logic được compiler Java hiểu mặc định.

Đối với annotation chỉ đóng vai trò marker, bản thân Java compiler không mặc định biết nó biểu diễn “nonnull”, “thread safe” hoặc “validated”. Một annotation processor, static analyzer, compiler plugin hoặc runtime framework có thể **tự định nghĩa và áp dụng quy tắc**, nhưng đó là logic của công cụ đó.

**Erasure:** Generic type variable `T` và các upper bounds ảnh hưởng cách compiler kiểm tra kiểu và dạng erased type khi tạo bytecode. Annotation type-use **không tự thay đổi erasure**; trong ví dụ method `echo(U)` bị erasure thành tham số `CharSequence` bởi upper bound `CharSequence`, không phải bởi chuỗi `"sequence"` trong annotation.

## 9. Nhiều bounds và vị trí annotation

Có thể kết hợp nhiều giới hạn:

~~~java
interface Readable {
    void read();
}

interface Writable {
    void write();
}

class Resource<
    @ParamInfo("resource") T extends
        @BoundInfo("read") Readable
        & @BoundInfo("write") Writable
> {}
~~~

Ở ví dụ này `Readable` và `Writable` đều là interface, nên danh sách bounds chỉ chứa interface types và hợp lệ. Dấu `&` nối các upper bounds, không phải phép AND điều kiện runtime.

Nếu thêm class bound, class phải đứng đầu:

~~~java
class Good<
    @ParamInfo("item") T extends
        @BoundInfo("number") Number
        & @BoundInfo("order") Comparable<T>
> {}
~~~

Ví dụ sai thứ tự (chỉ để nhận biết lỗi):

~~~java
// Sai: class Number không thể đứng sau interface trong danh sách bounds.
// class Wrong<T extends Comparable<T> & Number> {}
~~~

Nếu annotation cần đặt trên từng giới hạn, phải viết riêng cho từng kiểu sau `extends`/`&`. Nếu chỉ đặt annotation trước `T`, vị trí đó là type parameter declaration và không được hiểu thành annotation của toàn bộ tập bounds.

### Bound là parameterized type

Trong ví dụ chính, `Comparable<@BoundInfo("argument") T>` có hai lớp metadata:

- Annotation `"comparable"` trên bản thân kiểu bound `Comparable<T>`.
- Annotation `"argument"` trên lần dùng `T` làm **type argument** bên trong `Comparable<T>`.

Vì thế `t.getAnnotatedBounds()[1].getAnnotation(BoundInfo.class)` cho `"comparable"`; muốn lấy `"argument"` phải đi thêm một bước xuống `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`. Đây là lý do Reflection có một họ `AnnotatedType`, thay vì chỉ một danh sách annotation phẳng.

## 10. Sai lầm thường gặp

**1. Dùng `@Target(TYPE_PARAMETER)` để annotate upper bound.** Annotation có target đó dùng cho khai báo `T`. Muốn đặt trên kiểu `Number` sau `extends` hoặc kiểu sau `&`, khai báo target `TYPE_USE`.

**2. Nhầm `TYPE_PARAMETER` với `TYPE`.** `TYPE` chủ yếu là khai báo class/interface/enum/annotation type; nó không phải tên target chuyên biệt cho tham số kiểu generics. `TYPE_USE` rộng hơn và bao gồm các lần dùng kiểu.

**3. Nghĩ annotation bound quyết định generic constraint.** Chỉ `extends Number & Comparable<T>` quyết định ràng buộc Java; annotation không bổ sung kiểm tra kiểu mới trừ khi có công cụ hiểu nó.

**4. Dùng `getBounds()` rồi chờ đọc annotation.** `getBounds()` trả `Type[]` đại diện cho bounds; hãy dùng `getAnnotatedBounds()` để truy xuất metadata gắn trên từng type use.

**5. Chỉ gọi `Class.getAnnotation(...)` rồi không thấy annotation trên `T`.** Đó là hai phần tử Reflection khác nhau. Annotation khai báo trên type parameter thuộc `TypeVariable` từ `Class.getTypeParameters()`, không tự trở thành annotation trên class.

**6. Quên retention.** Mặc định annotation type có retention `CLASS`; để truy vấn declaration và bounds lúc runtime, annotation cần `@Retention(RUNTIME)`.

**7. Lấy sai index.** `getAnnotatedBounds()` trả bounds theo thứ tự khai báo; với `T extends Number & Comparable<T>`, index 0 là `Number`, index 1 là `Comparable<T>`. Với type variable không có bound tường minh, array thường gồm `Object` không được annotate.

**8. Nhầm annotated bound với annotated type argument bên trong bound.** Một `Comparable<@BoundInfo T>` được đọc qua `AnnotatedParameterizedType`. Annotation trên `Comparable` và trên `T` ở bên trong là các vị trí khác nhau.

**9. Nhầm type parameter class với type parameter method.** `Box<T>` và `<U> U echo(U input)` có khai báo type variables khác nhau. Muốn lấy `U` hãy dùng `Method.getTypeParameters()`.

**10. Sai thứ tự class/interface bounds.** Class bound cụ thể nếu có phải đứng trước các interface bounds. Thêm annotation không sửa lỗi cú pháp hoặc lỗi constraints ở generics.

**11. Nghĩ `TYPE_USE` chỉ hợp lệ với bound.** Nó còn hợp lệ tại nhiều nơi dùng kiểu như type argument, cast, kiểu trả về và trong một số declaration contexts, gồm type parameter declarations theo quy tắc ngôn ngữ.

**12. Tưởng annotation đã tồn tại trên mỗi instance.** Metadata trên khai báo `T` hoặc các bounds được gắn với cấu trúc class/method trong class file. Khi tạo nhiều instance của cùng generic class, nó không sinh metadata riêng cho từng instance.

## 11. Bài tập tự luyện

1. Tạo `class Pair<@ParamInfo("K") K, @ParamInfo("V") V> {}`. Dùng `Pair.class.getTypeParameters()` in tên và giá trị `@ParamInfo` của cả hai khai báo.
2. Thêm `@BoundInfo("numeric")` vào `Number` trong `T extends Number`. Dự đoán vì sao `getAnnotation(BoundInfo.class)` trên `TypeVariable<T>` và trên `getAnnotatedBounds()[0]` trả kết quả khác nhau.
3. Tạo generic method `<@ParamInfo("X") X extends @BoundInfo("text") CharSequence> X choose(X value)`. Dùng `Method.getTypeParameters()` đọc declaration và bounds annotations. Giải thích vì sao erased parameter type là `CharSequence`.
4. Mở rộng ví dụ `Box` thành `Comparable<@BoundInfo("arg") T>`; dùng `AnnotatedParameterizedType` đọc annotation ở type argument. Đối chiếu với annotation trên bound `Comparable`.
5. Bỏ upper bound khỏi `class Free<V>` và dùng `getAnnotatedBounds()`. Giải thích vì sao Java báo về `Object` dù source không ghi `extends Object`.
6. Thử gắn `@ParamInfo` trực tiếp lên `Number` sau `extends` khi `@ParamInfo` chỉ có target `TYPE_PARAMETER`. Ghi lại lỗi compiler và giải thích lựa chọn `@Target`.
7. Tạo annotation `@Check` có `@Target(TYPE_USE)`. Thử gắn nó cả trước tên `T` lẫn trước bound `Number`. Quan sát khả năng compile và API Reflection đọc được từng vị trí.
8. Dùng `javap -v Box` để phân biệt metadata type parameter declaration, type parameter bound và annotation trên type argument trong bound. Chỉ ra đường đi của từng giá trị `T`, `number`, `comparable` và `argument`.

## 12. Checklist ghi nhớ

- `<@ParamInfo T>`: annotation tại **khai báo type parameter** `T`.
- `T extends @BoundInfo Number`: annotation trên **lần dùng kiểu `Number` làm bound**.
- `T extends Number & @BoundInfo Comparable<T>`: annotation trên bound thứ hai.
- `Comparable<@BoundInfo T>`: annotation trên type argument là một lần dùng `T`.
- `TYPE_PARAMETER` chuyên biệt cho declaration; `TYPE_USE` hợp lệ cho bounds và nhiều vị trí type use khác, đồng thời có thể dùng ở type parameter declaration.
- `TypeVariable.getAnnotation(...)` đọc annotation trên khai báo tham số kiểu; `TypeVariable.getAnnotatedBounds()` trả các annotated upper bounds.
- `AnnotatedParameterizedType` giúp đi sâu vào type arguments bên trong một parameterized bound.
- `@Retention(RUNTIME)` cần thiết để đọc các annotation tương ứng qua Reflection runtime; mặc định retention là `CLASS`.
- Annotation metadata không tự thay đổi generic type checking, erasure hoặc hành vi JVM.

Hiểu được các điểm này sẽ giúp bạn đọc chính xác annotation trên generics trong Java Core, đồng thời chuẩn bị cho những công cụ xử lý type-use annotations nâng cao.

### Tài liệu tham khảo

- [Java Language Specification 17 — `4.4: Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4).
- [Java Language Specification 17 — `9.6.4.1: @Target](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1).
- [Java SE 17 — ElementType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html).
- [Java SE 17 — TypeVariable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html).
- [Java SE 17 — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html).
- [Java SE 17 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html).
