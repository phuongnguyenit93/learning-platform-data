# Annotation trên superclass và interface được khai báo

## 1. Vấn đề: annotation nằm trên *kiểu được sử dụng* hay trên *khai báo kiểu*?

Trong Java, annotation có thể gắn vào **khai báo lớp/interface** hoặc vào **vị trí sử dụng một kiểu** trong mệnh đề `extends` và `implements`. Đây là hai nơi khác nhau dù cùng liên quan tới quan hệ kế thừa.

~~~java
// Mảnh minh họa cú pháp. Các annotation đã được định nghĩa phù hợp.
@Category("domain")                    // Annotation của declaration: Base
class Base {}

class Child extends @Edge("inheritance") Base {}
//                  ^ Annotation trên type use "Base" tại cạnh Child -> Base.
~~~

- `@Category` mô tả khai báo `Base`; tra cứu qua `Base.class.getAnnotation(Category.class)`.
- `@Edge` mô tả **việc dùng kiểu `Base` làm superclass của `Child`**, không tự gắn vào `Base.class` và không phải annotation declaration của `Child`.
- Nếu có `AnotherChild extends @Edge("another") Base`, hai cạnh có thể mang annotation khác nhau mà `Base` vẫn là một khai báo duy nhất.
- Với `implements Interface` hoặc `interface Sub extends Interface`, ý tưởng giống hệt: annotation tại cạnh sử dụng interface, không phải annotation trên chính interface declaration.

Chủ đề này thuộc **type-use annotations** (`@Target(ElementType.TYPE_USE)`), được hỗ trợ từ Java 8. Java Reflection sử dụng `AnnotatedType` để trả về annotation ở các vị trí sử dụng kiểu, chứ không chỉ trả `Class<?>`.

## 2. API chính: getAnnotatedSuperclass và getAnnotatedInterfaces

| API Java Reflection | Kết quả | Phạm vi |
| --- | --- | --- |
| `clazz.getSuperclass()` | `Class<?>` của superclass trực tiếp (nếu có) | Không có type-use annotations, không giữ generic args. |
| `clazz.getGenericSuperclass()` | `Type` của superclass trực tiếp | Có generic declaration, **không chứa annotation tại type-use**. |
| `clazz.getAnnotatedSuperclass()` | `AnnotatedType` mô tả *việc dùng superclass* của class | Có thể đọc TYPE_USE annotation trên `extends` và trên generic argument lồng bên trong. |
| `clazz.getInterfaces()` | `Class<?>[]` chứa các superinterfaces **trực tiếp** | Không chứa TYPE_USE annotation hoặc generic args. |
| `clazz.getGenericInterfaces()` | `Type[]` chứa các superinterfaces trực tiếp | Giữ generic args nhưng không chứa TYPE_USE annotation. |
| `clazz.getAnnotatedInterfaces()` | `AnnotatedType[]` chứa các *lần dùng interface* trực tiếp | Có TYPE_USE annotation trên `implements`/`extends` và các type arguments. |

Các API `getAnnotatedSuperclass()`, `getAnnotatedInterfaces()` được khai báo trên `java.lang.Class`. Hai API này khác hẳn `Class.getAnnotations()` và `Class.getDeclaredAnnotations()`: các phương thức sau đọc **declaration annotations của đối tượng Class**, không phải annotation trên cạnh superclass/interface. 

Theo hợp đồng Java SE 17:

- Với class thông thường, `getAnnotatedSuperclass()` mô tả superclass trực tiếp. Nếu superclass không được khai báo có annotation, nó vẫn có thể trả `AnnotatedType` với mảng annotation **rỗng**. Ví dụ một class không viết `extends` vẫn có superclass `Object` ngầm.
- `getAnnotatedSuperclass()` trả **null** với `Object.class`, interface, array class, primitive và `void.class`.
- `getAnnotatedInterfaces()` trả mảng theo **thứ tự khai báo** trong `implements` hoặc `extends` của interface. Không có direct superinterface thì mảng rỗng.
- Các API `getAnnotatedInterfaces()` không tự nối toàn bộ interface gián tiếp mà superclass đã implement. Muốn duyệt transitive hierarchy, người viết công cụ phải duyệt tiếp các nút cha.

Ví dụ `class Child implements A, B` thì `getAnnotatedInterfaces()[0]` phản ánh cách dùng `A`, phần tử `[1]` là `B`. Không nên phụ thuộc index một cách mù quáng khi mã nguồn có thể đổi thứ tự; hãy so `AnnotatedType.getType()` với kiểu đang tìm hoặc xác định đường đi rõ ràng.

## 3. Khai báo annotation đúng cho TYPE_USE

Annotation trên superclass/interface use phải cho phép target `TYPE_USE`. Nếu muốn đọc bằng Reflection lúc chạy, cần `@Retention(RetentionPolicy.RUNTIME)`. Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Edge {
    String value();
}
~~~

Đây là mảnh mã khai báo riêng để minh họa. Nếu ghép với ví dụ độc lập ở phần 6, **không** khai báo trùng annotation `Edge`.

Cần tách bạch:

| Vị trí | Ví dụ | Target thích hợp | API đọc |
| --- | --- | --- | --- |
| Khai báo lớp | `@Role class Base {}` | `TYPE` | `Base.class.getAnnotation(Role.class)` |
| Type use tại superclass | `class Child extends @Edge Base {}` | `TYPE_USE` | `Child.class.getAnnotatedSuperclass().getAnnotation(Edge.class)` |
| Type use tại implemented interface | `class Child implements @Edge Contract {}` | `TYPE_USE` | Duyệt `Child.class.getAnnotatedInterfaces()` rồi `getAnnotation(Edge.class)` |
| Type use tại superinterface | `interface Sub extends @Edge Contract {}` | `TYPE_USE` | `Sub.class.getAnnotatedInterfaces()` |
| Type argument lồng trong superclass | `extends Base<@Edge String>` | `TYPE_USE` | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` |
| Khai báo type parameter | `class Base<@Marker T> {}` | `TYPE_PARAMETER` | `TypeVariable.getAnnotations()` (ngữ nghĩa declaration khác type-use). |

Không coi `@Target(TYPE)` và `@Target(TYPE_USE)` là tương đương. Có thể khai báo một annotation cho nhiều target nếu thật sự cần, nhưng phải hiểu API nào được yêu cầu và vị trí annotation được sử dụng. Một annotation có `RetentionPolicy.CLASS` có thể có trong class file mà API Reflection runtime không cung cấp nó. `RetentionPolicy.SOURCE` không được giữ tới class file.

## 4. AnnotatedType biểu diễn gì?

`java.lang.reflect.AnnotatedType` là một `AnnotatedElement` mô tả *cách dùng kiểu*, vì vậy có:

- `getType()`: `java.lang.reflect.Type` phía dưới, có thể là `Class<?>` hoặc `ParameterizedType`.
- `getAnnotation(Edge.class)`, `isAnnotationPresent(...)`, `getAnnotations()`, `getDeclaredAnnotations()`: đọc annotation gắn trên **lần sử dụng kiểu đang được đại diện**.
- `getAnnotatedOwnerType()`: khi là kiểu thành viên và có enclosing owner type được biểu diễn, cho phép khảo sát phần owner (có thể null).

Khi superclass/interface có generic arguments, kiểu trả về thường là `AnnotatedParameterizedType`, với `getAnnotatedActualTypeArguments()` giữ annotation của từng tham số kiểu. Chẳng hạn:

~~~java
// Đã có Base<T>, Contract<T> và @Edge cho phép TYPE_USE.
class Child extends @Edge("super") Base<@Edge("arg") String>
        implements @Edge("contract") Contract<@Edge("generic-arg") Integer> {}
~~~

Phải đọc **hai tầng**:

1. `Child.class.getAnnotatedSuperclass().getAnnotation(Edge.class)` đọc `@Edge("super")`.
2. Ép superclass annotated type sang `AnnotatedParameterizedType` rồi lấy argument `[0].getAnnotation(Edge.class)` để đọc `@Edge("arg")`.

Tương tự, `getAnnotatedInterfaces()[0].getAnnotation(Edge.class)` đọc annotation tại interface use, còn annotation của `Integer` là ở annotated generic argument. **Annotation ngoài và annotation trong không tự hợp nhất**: `getAnnotations()` trên outer type use không tự trả annotation của mọi nested type argument.

Ngoài `AnnotatedParameterizedType`, các subtype liên quan gồm `AnnotatedArrayType`, `AnnotatedWildcardType`, `AnnotatedTypeVariable`. Nếu muốn hỗ trợ tất cả cách viết generic phức tạp, parser phải duyệt đệ quy. Đừng cast trực tiếp sang `Class<?>` hoặc `AnnotatedParameterizedType` khi không kiểm tra bằng `instanceof`; kiểu raw hoặc non-generic thường không phải annotated parameterized type.

## 5. @Inherited KHÔNG phải cơ chế kế thừa annotation trên cạnh extends/implements

`java.lang.annotation.Inherited` thường gây nhầm lẫn ở phần này.

Annotation khai báo:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@java.lang.annotation.Inherited
@interface Role {
    String value();
}
~~~

`@Inherited` chỉ định **declaration annotation** có thể được tìm theo **superclass chain** khi truy vấn trên khai báo class. Nếu `Base` có `@Role`, class con không tự khai báo `@Role` nhưng `Child.class.getAnnotation(Role.class)` có thể trả annotation từ `Base`. Điều này không có nghĩa annotation được chép vào class file của `Child`: `Child.class.getDeclaredAnnotation(Role.class)` vẫn null khi Child không khai báo trực tiếp.

Ba giới hạn cần nhớ:

- **Không kế thừa từ interface** qua `@Inherited`: `class Impl implements @SomeUse Interface` không nhận declaration annotation `@Role` của interface chỉ bởi implements nó.
- **Không tự lan truyền type-use annotation trên cạnh**: nếu `Child extends @Edge Base` thì `Grandchild extends Child` không tự có `@Edge` tại cạnh `Grandchild -> Child`. Muốn biết annotation của cạnh `Child -> Base`, phải chủ động duyệt đến `Child.class.getAnnotatedSuperclass()`.
- **Không áp dụng để tìm annotation trên mọi vị trí cú pháp**: `@Inherited` được định nghĩa cho việc truy vấn declaration annotation của class; không dùng nó như một bộ duyệt `AnnotatedType` hoặc thuật toán tìm annotation trên interface.

Đây chính là lý do một công cụ thiết kế policy đặt trên cạnh inheritance cần lưu ngữ cảnh **lớp khai báo cạnh**; còn công cụ xử lý class-level marker cần xét `getAnnotation`/`getDeclaredAnnotation` và quy tắc `@Inherited`. Hai nhiệm vụ khác nhau không nên dùng cùng một quy tắc “thừa kế annotation”.

## 6. Ví dụ Java 17+ hoàn chỉnh: superclass, interface và generic argument

Lưu file `AnnotatedHierarchyDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;

public class AnnotatedHierarchyDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Edge {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Role {
        String value();
    }

    @Role("base-declaration")
    static class Base<T> {
    }

    @Role("interface-declaration")
    interface Contract<T> {
    }

    static class Child
            extends @Edge("superclass-edge") Base<@Edge("superclass-arg") String>
            implements @Edge("interface-edge") Contract<@Edge("interface-arg") Integer> {
    }

    static class Grandchild extends Child {
    }

    static class OnlyInterface implements Contract<String> {
    }

    interface SubContract extends @Edge("superinterface-edge") Contract<Long> {
    }

    static String edge(AnnotatedType annotated) {
        Edge value = annotated.getAnnotation(Edge.class);
        return value == null ? "-" : value.value();
    }

    static String role(Class<?> type) {
        Role value = type.getAnnotation(Role.class);
        return value == null ? "-" : value.value();
    }

    public static void main(String[] args) {
        AnnotatedType superclass = Child.class.getAnnotatedSuperclass();
        AnnotatedType interfaceUse = Child.class.getAnnotatedInterfaces()[0];

        System.out.println("Child superclass edge=" + edge(superclass));
        System.out.println("Child superclass argument="
                + edge(((AnnotatedParameterizedType) superclass)
                        .getAnnotatedActualTypeArguments()[0]));
        System.out.println("Child interface edge=" + edge(interfaceUse));
        System.out.println("Child interface argument="
                + edge(((AnnotatedParameterizedType) interfaceUse)
                        .getAnnotatedActualTypeArguments()[0]));

        System.out.println("SubContract superinterface edge="
                + edge(SubContract.class.getAnnotatedInterfaces()[0]));
        System.out.println("Base declaration role=" + role(Base.class));
        System.out.println("Child inherited role=" + role(Child.class));
        System.out.println("Child declared role="
                + (Child.class.getDeclaredAnnotation(Role.class) != null));
        System.out.println("OnlyInterface inherited role=" + role(OnlyInterface.class));
        System.out.println("Grandchild role=" + role(Grandchild.class));
        System.out.println("Grandchild direct edge="
                + edge(Grandchild.class.getAnnotatedSuperclass()));
        System.out.println("Grandchild direct interfaces="
                + Grandchild.class.getAnnotatedInterfaces().length);
        System.out.println("Interface has superclass="
                + (Contract.class.getAnnotatedSuperclass() != null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 AnnotatedHierarchyDemo.java
java AnnotatedHierarchyDemo
~~~

Đầu ra kỳ vọng trên Java 17+:

~~~text
Child superclass edge=superclass-edge
Child superclass argument=superclass-arg
Child interface edge=interface-edge
Child interface argument=interface-arg
SubContract superinterface edge=superinterface-edge
Base declaration role=base-declaration
Child inherited role=base-declaration
Child declared role=false
OnlyInterface inherited role=-
Grandchild role=base-declaration
Grandchild direct edge=-
Grandchild direct interfaces=0
Interface has superclass=false
~~~

Giải thích từng nhóm kết quả:

- `Child` có **một superclass trực tiếp** và một **direct implemented interface**, mỗi cạnh gắn `@Edge` riêng. Reflection trả về annotation chính xác tại vị trí tương ứng.
- `Base<@Edge String>` / `Contract<@Edge Integer>` giữ `@Edge` ở type argument; do đó phải đi qua `AnnotatedParameterizedType` để đọc chúng.
- `SubContract` là một **interface** mở rộng interface khác. Nó không có class superclass (`getAnnotatedSuperclass()==null`) nhưng `getAnnotatedInterfaces()` vẫn phản ánh cạnh `extends Contract<Long>`.
- `Role` là declaration annotation của `Base` và `Contract`. `Child` kế thừa `Role("base-declaration")` từ superclass nhờ `@Inherited`, nhưng `getDeclaredAnnotation` trên `Child` không trả nó.
- `OnlyInterface` không có superclass được đánh dấu `Role`; `@Role` trên `Contract` **không chuyển sang class implement** theo `@Inherited`.
- `Grandchild` tiếp tục được truy vấn declaration annotation `Role` dọc class superclass chain, nhưng direct superclass edge (`Grandchild -> Child`) **không** có `@Edge`, nên `edge(...)` trả `-`.
- `Grandchild.getAnnotatedInterfaces().length == 0` vì Grandchild **không trực tiếp khai báo implements**. Điều đó không có nghĩa một `Grandchild` không phải `Contract`: nó vẫn kế thừa implementation interface qua `Child` trong type hierarchy.

Nếu thay `@Retention(RUNTIME)` của `Edge` thành `CLASS`, runtime Reflection sẽ không thấy các marker đó nữa. Thứ tự type arguments trong mảng trả về tương ứng với thứ tự trong khai báo `Base<T>`/`Contract<T>`.

## 7. Duyệt nhiều cấp đúng cách

`getAnnotatedSuperclass()` và `getAnnotatedInterfaces()` cung cấp **các cạnh trực tiếp của node hiện tại**, không duyệt closure của toàn bộ đồ thị inheritance. Một framework tìm type-use annotations qua phân cấp có thể làm như sau:

1. Chọn class/interface gốc `root` cần phân tích.
2. Tại mỗi node `current`, đọc `current.getAnnotatedSuperclass()` (nếu khác null), xử lý annotation của **cạnh đi tới superclass**.
3. Duyệt `current.getAnnotatedInterfaces()` theo thứ tự trả về, xử lý annotation của **từng cạnh interface trực tiếp**.
4. Từ mỗi annotated edge, lấy `getType()` để xác định type đích. Nếu là `ParameterizedType`, dùng `getRawType()` để xác định class/interface cần duyệt tiếp; nếu là `Class<?>`, dùng trực tiếp.
5. Khi cần generic argument annotation, phân nhánh `instanceof AnnotatedParameterizedType` rồi duyệt `getAnnotatedActualTypeArguments()`, và sâu hơn với array/wildcard/nested owner type khi thích hợp.
6. Duyệt tiếp các class/interface đích theo chính sách ứng dụng (class chain riêng, interface graph riêng hoặc cả hai). Có thể gặp cùng một interface theo **nhiều đường đi**, vì vậy lưu visited để tránh lặp nếu chỉ cần node duy nhất; nếu nghiệp vụ đánh giá **từng cạnh có annotation riêng**, phải giữ thông tin đường đi/cạnh thay vì vô tình gộp tất cả.
7. Đừng tự động đẩy annotation từ cạnh cha xuống mọi cạnh con: semantics của `@Edge` do ứng dụng định nghĩa; Java chỉ lưu và cung cấp metadata, **không thực thi policy runtime thay người viết framework**.

Một hàm chỉ cần xác định kiểu raw từ `AnnotatedType` có thể dùng:

~~~java
// Đoạn mã để đặt trong class có import java.lang.reflect.*.
// Nó chỉ giải raw class cho Class và ParameterizedType, không phải resolver
// tổng quát cho mọi TypeVariable, GenericArrayType hay WildcardType.
static Class<?> rawClass(AnnotatedType annotated) {
    java.lang.reflect.Type type = annotated.getType();
    if (type instanceof Class<?> cls) {
        return cls;
    }
    if (type instanceof java.lang.reflect.ParameterizedType pt
            && pt.getRawType() instanceof Class<?> cls) {
        return cls;
    }
    throw new IllegalArgumentException("Unsupported raw type: " + type);
}
~~~

Code trên là đoạn tiện ích minh họa, không phải chương trình độc lập. Chưa xử lý mọi `Type` và không thể thay thế bộ phân tích generic đầy đủ; cách phân nhánh này là chủ ý để các trường hợp chưa hỗ trợ được báo lỗi rõ ràng thay vì ép kiểu sai.

### Khi gặp nhiều declaration annotation khác nhau

Nếu mục tiêu là “class này có `@Role` không?”, dùng `Class.getAnnotation(Role.class)` theo ngữ nghĩa `@Inherited`. Nếu mục tiêu là “cạnh extends/implements này có `@Edge` không?”, **đọc annotated hierarchy edges**. Framework nên ghi rõ chính sách khi:

- interface A được kế thừa gián tiếp qua nhiều nhánh;
- superclass và interface có annotation cùng tên nhưng ý nghĩa khác;
- một type-use annotation nằm ở outer type, type argument hoặc inner component;
- một class không khai báo `extends` tường minh nhưng có superclass `Object`;
- các annotation không được giữ đến runtime.

## 8. Những lỗi phổ biến cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`Base.class.getAnnotation(Edge.class)` đọc `extends @Edge Base`.” | Annotation trên **cạnh của Child** phải đọc từ `Child.class.getAnnotatedSuperclass()`. |
| “`getGenericSuperclass()` là đủ để lấy TYPE_USE annotation.” | API trả `Type`, không mang lớp annotation; dùng `getAnnotatedSuperclass()`. |
| “Annotation trên `implements` sẽ tự xuất hiện trên interface declaration.” | Đó là metadata của lần dùng interface trong class đang khai báo. |
| “`@Inherited` làm annotation từ interface truyền sang class implement.” | Sai: `@Inherited` chỉ xét superclass chain của class declaration. |
| “`@Inherited` sao chép annotation TYPE_USE xuống mọi class con.” | Sai: type-use annotation tại mỗi cạnh là metadata độc lập. |
| “`getAnnotatedInterfaces()` liệt kê mọi interface được kế thừa gián tiếp.” | Sai: chỉ direct superinterfaces được class/interface khai báo. |
| “Nếu `getAnnotatedSuperclass()` trả không null thì nhất định có annotation.” | Sai: có thể đại diện superclass không có annotation, ví dụ `Object` ngầm định. |
| “`@Target(TYPE)` đủ cho type-use trong `extends/implements`.” | Cần `TYPE_USE` cho vị trí type-use. |
| “`AnnotatedParameterizedType.getAnnotations()` gồm annotation của mọi generic argument.” | Sai: phải đọc từng `getAnnotatedActualTypeArguments()`. |
| “Có annotation trong source là Reflection thấy.” | Cần retention thích hợp (`RUNTIME`) và metadata hợp lệ. |

**Tình huống thực tế:** một dependency injection framework muốn xác định cách xử lý adapter theo đường implement `Contract<T>` có thể dùng edge annotation như metadata định tuyến. Ngược lại một validator muốn tìm class-level `@Entity` có thể chỉ cần `Class.getAnnotation(...)` (và quy tắc `@Inherited` của annotation đó). Chọn đúng vị trí metadata sẽ ngăn nhầm annotation giữa hai đối tượng và hai lớp trách nhiệm.

## 9. Bài tập thực hành

1. Thêm interface `Loggable` rồi viết `implements @Edge("api") Contract<String>, @Edge("log") Loggable`; in từng phần tử `getAnnotatedInterfaces()` để thấy thứ tự.
2. Thử `class Plain {}` và kiểm tra `Plain.class.getAnnotatedSuperclass()` khác null nhưng không có `@Edge`.
3. Thử `Object.class.getAnnotatedSuperclass()`, `Contract.class.getAnnotatedSuperclass()`, `int.class.getAnnotatedSuperclass()` và so sánh với class thường.
4. Bỏ `@Inherited` khỏi `Role` trong demo, chạy lại và giải thích vì sao `Child.class.getAnnotation(Role.class)` không nhận marker từ `Base`.
5. Giữ `@Inherited` trên `Role` nhưng xóa `@Role` của `Base`; chỉ giữ marker trên `Contract` và chứng minh `OnlyInterface`/`Child` không tự thừa hưởng annotation từ interface.
6. Thay type argument `String` bằng `List<@Edge("nested") String>` ở superclass, triển khai traversal hai tầng `AnnotatedParameterizedType`.
7. Tạo `Grandchild extends @Edge("direct-grandchild") Child`, kiểm chứng annotation của `Grandchild -> Child` độc lập với annotation của `Child -> Base`.
8. Xây hàm liệt kê các cạnh trực tiếp: tên class nguồn, kiểu đích, annotation trên cạnh và annotation trên generic arguments; phân biệt direct và transitive.
9. Với `@Retention(CLASS)` hoặc `SOURCE`, quan sát việc annotation không xuất hiện qua runtime Reflection mặc dù cú pháp source hợp lệ.

## 10. Tài liệu chính thức

- [Java SE 17 — Class.getAnnotatedSuperclass / getAnnotatedInterfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): hợp đồng superclass/interface trực tiếp, null và thứ tự.
- [Java SE 17 — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): type-use annotation và kiểu nền tảng.
- [Java SE 17 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html): generic arguments có annotation riêng.
- [Java SE 17 — @Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): kế thừa declaration annotation theo superclass chain, không qua interface.
- [JLS Java 17 — Type Annotations `9.7.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): annotation trên type use.
- [JLS Java 17 — Inheriting Annotations `9.6.4.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3): phạm vi của `@Inherited`.

**Điểm cốt lõi:** `Class.getAnnotation` đọc **annotation khai báo trên class** (có quy tắc `@Inherited` riêng), còn `getAnnotatedSuperclass` và `getAnnotatedInterfaces` đọc **annotation tại từng lần sử dụng superclass/interface trực tiếp**. Phải phân biệt hai lớp metadata này, và đi vào `AnnotatedParameterizedType` nếu annotation nằm trên generic argument.
