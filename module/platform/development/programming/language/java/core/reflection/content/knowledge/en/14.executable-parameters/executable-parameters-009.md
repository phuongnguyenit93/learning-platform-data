# getAnnotatedParameterTypes và getAnnotatedReceiverType trong Java Reflection

## 1. Hai phương thức trên `Executable` đọc những gì?

`Method` và `Constructor` đều kế thừa `java.lang.reflect.Executable`. Ngoài các API trả kiểu thô hoặc kiểu generic, `Executable` có hai API đọc **annotation tại vị trí sử dụng kiểu** (*type-use annotations*):

~~~java
AnnotatedType[] types = executable.getAnnotatedParameterTypes();
AnnotatedType receiver = executable.getAnnotatedReceiverType();
~~~

Đây là mã minh họa khi đã có biến `executable` kiểu `Executable`; cần import các lớp từ `java.lang.reflect`.

- **`getAnnotatedParameterTypes()`** trả mảng `AnnotatedType` theo thứ tự các kiểu tham số hình thức của executable. Nó phản ánh annotation đặt trực tiếp lên kiểu hoặc nằm sâu trong cấu trúc generic/mảng.
- **`getAnnotatedReceiverType()`** trả `AnnotatedType` của kiểu receiver (`this` đối với instance method, enclosing instance với constructor của non-static inner member class), hoặc `null` khi executable không thể có receiver parameter.
- Đây là **metadata**, không phải thao tác gọi phương thức, tạo instance, cấp quyền truy cập hay kiểm tra dữ liệu tự động.

Để đọc được annotation lúc chạy, annotation phải có `@Retention(RetentionPolicy.RUNTIME)`. Annotation với retention `SOURCE` hoặc `CLASS` không xuất hiện trong truy vấn runtime tương ứng.

## 2. Declaration annotation và type-use annotation khác nhau

Java cho phép annotation trên **khai báo tham số** (`ElementType.PARAMETER`) và trên **chính vị trí sử dụng một kiểu** (`ElementType.TYPE_USE`).

~~~java
import java.lang.annotation.*;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface InputTag {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeTag {
    String value();
}

class Sample {
    void accept(@InputTag @TypeTag("list")
                List<@TypeTag("element") String> names) {}
}
~~~

Ví dụ trên là các khai báo có thể đặt cùng một file Java; chúng chưa có hàm `main` độc lập.

- `@InputTag` gắn vào **khai báo tham số `names`**. Đọc bằng `Parameter.getAnnotation(InputTag.class)` hoặc `Executable.getParameterAnnotations()`.
- `@TypeTag("list")` gắn lên **kiểu `List` ở vị trí tham số**; đọc qua `getAnnotatedParameterTypes()[0].getAnnotation(TypeTag.class)`.
- `@TypeTag("element")` gắn lên **kiểu đối số `String` trong `List<String>`**; phải đi xuống cây `AnnotatedParameterizedType`.
- `getParameterTypes()[0]` trả raw class `List.class`, còn `getGenericParameterTypes()[0]` cho kiểu generic `List<String>`. Không API nào trong hai API đó thay thế `getAnnotatedParameterTypes()` khi muốn xem type-use annotations.

Annotation đặt tên `@NonNull`, `@Readonly` hoặc tên tương tự **không tự biến Reflection thành trình kiểm tra runtime**. Compiler plugin, static analyzer hoặc framework riêng phải hiểu và thực thi quy tắc đó.

## 3. Cấu trúc dữ liệu `AnnotatedType`

`getAnnotatedParameterTypes()` trả một phần tử cho mỗi tham số của executable. Mỗi phần tử là `AnnotatedType` và cung cấp `getType()`, `getAnnotations()`, `getAnnotation(...)`.

| API/kiểu | Thông tin phản ánh |
| --- | --- |
| `Class<?>[] getParameterTypes()` | Kiểu runtime/raw class của tham số |
| `Type[] getGenericParameterTypes()` | Kiểu generic, ví dụ `List<String>`, `T`, wildcard |
| `AnnotatedType[] getAnnotatedParameterTypes()` | Type-use annotations trên kiểu tham số và cấu trúc lồng |
| `Parameter[] getParameters()` | Metadata từng tham số, gồm declaration annotations và tên nếu có |
| `Annotation[][] getParameterAnnotations()` | Declaration annotations trên các tham số |
| `AnnotatedType getAnnotatedReceiverType()` | Receiver type và annotation của receiver |
| `AnnotatedType getAnnotatedReturnType()` | Type-use annotations ở kiểu trả về |
| `AnnotatedType[] getAnnotatedExceptionTypes()` | Type-use annotations trên kiểu trong `throws` |

Các subtype dùng khi đi sâu:

- `AnnotatedParameterizedType` cho `List<@Tag String>`: `getAnnotatedActualTypeArguments()`.
- `AnnotatedArrayType` cho kiểu mảng: `getAnnotatedGenericComponentType()`.
- `AnnotatedWildcardType` cho wildcard: `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()`.
- `AnnotatedTypeVariable` cho `T`: `getAnnotatedBounds()`.

Luôn dùng `instanceof` trước khi ép kiểu. Ví dụ, `int` có thể có type-use annotation nhưng không phải `AnnotatedParameterizedType`. `AnnotatedType.getType()` trả `Type`, có thể là `ParameterizedType` hoặc `TypeVariable`, không phải lúc nào cũng ép được thành `Class<?>`.

### Annotation bên trong generic không tự trồi lên ngoài

~~~java
AnnotatedType outer = method.getAnnotatedParameterTypes()[0];

if (outer instanceof AnnotatedParameterizedType p) {
    AnnotatedType inner = p.getAnnotatedActualTypeArguments()[0];
    TypeTag tag = inner.getAnnotation(TypeTag.class);
    if (tag != null) {
        System.out.println(tag.value());
    }
}
~~~

Đây là đoạn trích dùng `method` và `TypeTag` trong ngữ cảnh ví dụ đầy đủ bên dưới. Annotation trên `String` bên trong `List<String>` nằm ở **nút con của cây kiểu**, không xuất hiện chung trong `outer.getAnnotations()`.

Với mảng, `String @TypeTag("array") [] values` đặt annotation trên **mức mảng**. Vị trí annotation trước kiểu thành phần và trước ngoặc `[]` có ý nghĩa khác nhau; khi cần phân tích chuẩn xác phải duyệt `AnnotatedArrayType`.

## 4. Receiver parameter là gì?

Instance method chạy trên một đối tượng `this`. Java cho phép khai báo tường minh **receiver parameter** để chú thích kiểu của `this`:

~~~java
class Service {
    void process(@TypeTag("receiver") Service this,
                 @TypeTag("value") String value) {
        System.out.println(value);
    }
}
~~~

Đây là đoạn minh họa khi annotation `TypeTag` đã được định nghĩa với `@Target(TYPE_USE)`.

`Service this`:

- Phải xuất hiện trước các tham số hình thức còn lại.
- **Không phải tham số gọi method bổ sung**: phương thức `process` chỉ có **một** formal parameter là `String value`.
- Không thay đổi `getParameterCount()`, `getParameterTypes()` hay chữ ký tra cứu `getDeclaredMethod("process", String.class)`.
- Không tạo cơ chế gán lại `this`, truyền receiver mới qua danh sách `args`, hoặc thay đổi overload/dispatch.
- Cung cấp vị trí viết type-use annotation để `getAnnotatedReceiverType()` có thể đọc.

### Instance method không viết receiver tường minh

**Điểm rất quan trọng:** một instance method thông thường, dù **không có `Service this` trong source**, vẫn có receiver type theo API `Executable`. `getAnnotatedReceiverType()` của nó trả **một `AnnotatedType` khác `null`**, thường không mang annotation nào.

Do đó, phải phân biệt:

- `receiver == null`: executable **không thể có** receiver parameter, như static method.
- `receiver != null` và `receiver.getAnnotations().length == 0`: có receiver type nhưng **không có type-use annotation** được lưu trên receiver.
- `receiver.getAnnotation(TypeTag.class) != null`: receiver có annotation runtime được truy vấn.

Không thể suy “không viết receiver tường minh” chỉ từ việc kết quả không có annotation.

## 5. Receiver của method và constructor khác nhau

| Loại executable | Kết quả `getAnnotatedReceiverType()` |
| --- | --- |
| Instance method với receiver annotation | `AnnotatedType` mang annotation trên kiểu `this` |
| Instance method không có receiver annotation | `AnnotatedType` không `null`, thường rỗng annotation |
| Static method | `null` |
| Constructor top-level class | `null` |
| Constructor static nested/member class | `null` |
| Constructor local class hoặc anonymous class | `null` theo hợp đồng Javadoc |
| Constructor **non-static inner member class** | `AnnotatedType` đại diện enclosing instance receiver |

Với inner class, có cú pháp `Outer Outer.this` trong danh sách constructor để đặt annotation lên **kiểu của enclosing instance receiver**:

~~~java
class Outer {
    class Inner {
        Inner(@TypeTag("owner") Outer Outer.this,
              @TypeTag("text") String text) {}
    }
}
~~~

Đây là mã minh họa có `TypeTag` ở phạm vi truy cập phù hợp. Inner class non-static cần một **enclosing instance** để khởi tạo. Compiler thường đưa một tham số ẩn kiểu `Outer` vào **chữ ký constructor ở bytecode**. Vì vậy khi Reflection tra constructor, có thể cần `Outer.class` trước tham số `String.class`.

**Không đồng nhất hai việc:** receiver parameter tường minh `Outer Outer.this` là nơi để **chú thích kiểu**, không tự tạo một tham số gọi mới; sự hiện diện của outer-instance argument ở constructor là kết quả của mô hình inner class.

## 6. Ví dụ Java 17+ hoàn chỉnh

Tạo file **`AnnotatedExecutableDemo.java`**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

public class AnnotatedExecutableDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface TypeTag {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface InputTag {}

    public static class Service {
        public Service() {}

        public void process(@TypeTag("receiver") Service this,
                            @InputTag @TypeTag("list")
                            List<@TypeTag("element") String> values,
                            @TypeTag("count") int count) {}

        public void plain(String value) {}

        public static void staticAction(
                @TypeTag("static") String value) {}
    }

    public static class Outer {
        public class Inner {
            public Inner(@TypeTag("owner") Outer Outer.this,
                         @TypeTag("label") String label) {}
        }
    }

    public static void main(String[] args) throws Exception {
        Method method = Service.class.getDeclaredMethod(
                "process", List.class, int.class);

        AnnotatedType[] parameters =
                method.getAnnotatedParameterTypes();

        System.out.println("parameters=" + parameters.length);
        System.out.println("raw0="
                + method.getParameterTypes()[0].getTypeName());
        System.out.println("declaration0="
                + method.getParameters()[0].isAnnotationPresent(
                        InputTag.class));
        System.out.println("type0="
                + parameters[0].getAnnotation(TypeTag.class).value());

        AnnotatedParameterizedType list =
                (AnnotatedParameterizedType) parameters[0];
        System.out.println("element="
                + list.getAnnotatedActualTypeArguments()[0]
                      .getAnnotation(TypeTag.class).value());

        System.out.println("type1="
                + parameters[1].getAnnotation(TypeTag.class).value());
        System.out.println("receiver="
                + method.getAnnotatedReceiverType()
                        .getAnnotation(TypeTag.class).value());

        Method plain = Service.class.getDeclaredMethod(
                "plain", String.class);
        System.out.println("plainReceiverPresent="
                + (plain.getAnnotatedReceiverType() != null));
        System.out.println("plainReceiverTags="
                + plain.getAnnotatedReceiverType().getAnnotations().length);

        Method staticMethod = Service.class.getDeclaredMethod(
                "staticAction", String.class);
        System.out.println("staticReceiverNull="
                + (staticMethod.getAnnotatedReceiverType() == null));

        Constructor<Service> ctor = Service.class.getConstructor();
        System.out.println("staticNestedCtorReceiverNull="
                + (ctor.getAnnotatedReceiverType() == null));

        Constructor<?> inner = Outer.Inner.class.getConstructor(
                Outer.class, String.class);
        System.out.println("innerReceiver="
                + inner.getAnnotatedReceiverType()
                       .getAnnotation(TypeTag.class).value());
        System.out.println("innerParameters="
                + inner.getParameterCount());
        System.out.println("innerParam0="
                + inner.getParameterTypes()[0].getSimpleName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 AnnotatedExecutableDemo.java
java AnnotatedExecutableDemo
~~~

Stdout:

~~~text
parameters=2
raw0=java.util.List
declaration0=true
type0=list
element=element
type1=count
receiver=receiver
plainReceiverPresent=true
plainReceiverTags=0
staticReceiverNull=true
staticNestedCtorReceiverNull=true
innerReceiver=owner
innerParameters=2
innerParam0=Outer
~~~

**Giải thích từng nhóm kết quả:**

1. `parameters=2` khẳng định receiver `Service this` không được tính là formal parameter của `process`. Hai kiểu dùng để tra method là `List.class` và `int.class`.
2. `raw0=java.util.List` đến từ `getParameterTypes()`; `declaration0=true` là kết quả `@InputTag` trên khai báo tham số.
3. `type0=list` là annotation trên `List` ở vị trí dùng kiểu. `element=element` là annotation trên kiểu `String` lồng sâu trong generic; đọc qua `AnnotatedParameterizedType`.
4. `type1=count` cho thấy ngay cả primitive `int` cũng có thể mang type-use annotation.
5. `receiver=receiver` là annotation trên receiver parameter khai báo tường minh.
6. `plainReceiverPresent=true` cùng `plainReceiverTags=0`: instance method không viết receiver tường minh vẫn có `AnnotatedType`, nhưng không có annotation.
7. `staticReceiverNull=true` và `staticNestedCtorReceiverNull=true`: static method và constructor của static nested class không có receiver type theo API.
8. `innerReceiver=owner` cho thấy annotation trên enclosing-instance receiver của inner constructor.
9. `innerParameters=2`, `innerParam0=Outer` cho thấy tham số `Outer` do compiler đưa vào constructor bytecode, rồi tới tham số `String` khai báo trong source.

Ví dụ dùng API có mặt ở Java 17. Mã đã được kiểm tra thực tế bằng `javac --release 17` và chạy trên JDK 24 với đúng stdout phía trên.

## 7. Không nhầm receiver metadata với đối tượng truyền cho `Method.invoke`

Khi dùng Reflection để gọi instance method, chữ ký:

~~~java
Object result = method.invoke(receiver, args...);
~~~

nhận **đối tượng đích thực tế** ở `receiver`, còn `args` là danh sách các đối số ứng với formal parameters của method.

Nếu `process(@TypeTag Service this, List<String> values, int count)` thì một lời gọi có thể là:

~~~java
Method method = Service.class.getDeclaredMethod(
        "process", List.class, int.class);

Service service = new Service();
List<String> values = List.of("a", "b");
method.invoke(service, values, 5);
~~~

Các đoạn này minh họa trong ngữ cảnh có định nghĩa `Service` và xử lý checked exceptions; chúng không cần truyền thêm đối số nào cho receiver parameter `Service this`. `service` là giá trị đích runtime của `invoke`, còn `getAnnotatedReceiverType()` chỉ nói về **kiểu receiver được annotate**, không trả về đối tượng `service`.

Receiver annotation cũng **không thay đổi** quyền truy cập, không khiến `Method.invoke` tự xác thực dữ liệu theo annotation và không thay đổi lựa chọn overload.

## 8. Cách dùng trong framework đọc schema/annotation

Một thư viện tự phân tích executable có thể theo quy trình:

1. Lấy đúng `Method` hoặc `Constructor` cần phân tích.
2. Duyệt `getAnnotatedParameterTypes()` theo thứ tự, đọc annotation trên từng kiểu và đi xuống generic/mảng/wildcard nếu cần.
3. Nếu muốn annotation khai báo trên tham số, dùng `getParameters()` hoặc `getParameterAnnotations()` **riêng**.
4. Gọi `getAnnotatedReceiverType()` rồi **kiểm tra `null` trước khi lấy annotation**.
5. Với constructor của non-static inner member class, kiểm tra `getParameterTypes()` vì có thể xuất hiện outer-instance argument do compiler thêm.
6. Nếu cần annotation trên kiểu trả về hoặc `throws`, dùng `getAnnotatedReturnType()` / `getAnnotatedExceptionTypes()`.
7. Áp dụng các quy tắc ứng dụng (validation, schema, DI) ở tầng xử lý tiếp theo. Reflection chỉ trả metadata.

### Những lỗi thường gặp

- **Coi `null` và `AnnotatedType` rỗng annotation là một:** static method thường trả `null`, instance method thông thường trả `AnnotatedType` không `null`.
- **Đếm `this` như một formal parameter:** receiver parameter tường minh không làm tăng `getParameterCount()` của instance method.
- **Dùng `getParameterAnnotations()` để đọc `List<@Tag String>`:** phải dùng `getAnnotatedParameterTypes()` rồi duyệt `AnnotatedParameterizedType`.
- **Không kiểm tra subtype:** ép mọi `AnnotatedType` thành `AnnotatedParameterizedType` sẽ sai với primitive, mảng hay kiểu thường.
- **Đọc kiểu lồng bằng mỗi `getAnnotations()` ở ngoài:** annotation trên type argument nằm ở node con.
- **Quên retention:** runtime Reflection không đọc được annotation đã bị bỏ ở giai đoạn biên dịch.
- **Nhầm `getAnnotatedReceiverType()` với API quyền truy cập:** nó không liên quan đến `canAccess` hay `trySetAccessible`.
- **Nghĩ annotation tự ràng buộc dữ liệu:** framework hoặc trình phân tích phải định nghĩa ý nghĩa và thực thi kiểm tra.
- **Đoán constructor inner class từ source:** outer-instance argument có thể nằm trong chữ ký runtime; luôn kiểm tra parameter metadata.

## 9. Tự kiểm tra

**Câu 1.** Một instance method khai báo `void f(@Tag X this, String value)` có bao nhiêu formal parameters?  
**Một** (`String value`). Receiver parameter không nằm trong `getAnnotatedParameterTypes()`.

**Câu 2.** Instance method không khai báo receiver tường minh có `getAnnotatedReceiverType() == null` không?  
**Thông thường không.** Nó trả `AnnotatedType` đại diện receiver, với annotation rỗng nếu không có type-use annotation.

**Câu 3.** Static method có receiver type không?  
**Không**, `getAnnotatedReceiverType()` trả `null`.

**Câu 4.** Muốn lấy annotation trên `String` bên trong `List<@Tag String>`, đọc ở đâu?  
**`getAnnotatedParameterTypes()` → `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`** rồi tra annotation của phần tử.

**Câu 5.** `getParameterAnnotations()` trả cùng thông tin với `getAnnotatedParameterTypes()`?  
**Không.** Cái đầu đọc declaration annotations, cái sau đọc type-use annotations.

**Câu 6.** Constructor non-static inner class có thể trả receiver type?  
**Có**; receiver đại diện enclosing instance của lớp bao, dù constructor source có thể không ghi tường minh receiver annotation.

**Ghi nhớ:** `getAnnotatedParameterTypes()` trả annotation trên **kiểu của các tham số**, còn `getAnnotatedReceiverType()` trả annotation trên **kiểu receiver**. Receiver không phải một tham số gọi method bổ sung, và kết quả `null` phải được phân biệt với receiver type không có annotation.

### Tài liệu chính thức

- [JDK 17 — `java.lang.reflect.Executable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html)
- [JDK 17 — `java.lang.reflect.AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [JDK 17 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [JDK 17 — `Parameter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html)
- [JLS 17 §8.4.1 — Formal Parameters, Receiver Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1)
