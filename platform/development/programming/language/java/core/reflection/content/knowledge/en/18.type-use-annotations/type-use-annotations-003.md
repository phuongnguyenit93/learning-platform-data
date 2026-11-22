# AnnotatedParameterizedType và annotation trên đối số kiểu trong Java Reflection

Trong Java Reflection, `AnnotatedParameterizedType` giúp đọc **annotation gắn với một lần sử dụng kiểu có tham số generic** (*parameterized type use*), bao gồm cả annotation đặt trên **từng đối số kiểu**. Đây là khác biệt quan trọng so với chỉ lấy `ParameterizedType`.

Ví dụ, hai khai báo sau đều có kiểu generic `List<String>`, nhưng mang thông tin type-use annotation khác nhau:

```java
List<@Tag("element") String> first;
@Tag("container") List<String> second;
```

Đây là ví dụ cú pháp rời; annotation `Tag` phải được khai báo với `@Target(ElementType.TYPE_USE)` và retention thích hợp. Trong `first`, annotation gắn với **`String` ở vị trí đối số generic**. Trong `second`, annotation gắn với **chính lần dùng kiểu `List<String>`**. Muốn đọc đúng từng vị trí, ta cần `AnnotatedType` và `AnnotatedParameterizedType`, không chỉ `Field.getType()` hoặc `Field.getGenericType()`.

## 1. Bối cảnh: type-use annotation là gì?

Java 8 giới thiệu type annotations và các API tương ứng cho Reflection. Annotation có thể được gắn không chỉ vào *declaration* như class, method hoặc field, mà còn vào **vị trí sử dụng một kiểu** (*type use*): kiểu trả về, kiểu của trường, đối số generic, phần tử mảng, wildcard bound, v.v.

Một annotation dùng trong bài:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Tag {
    String value();
}
```

Đoạn này minh họa phần khai báo annotation; chương trình chạy đầy đủ ở mục 4 khai báo `Tag` bên trong class để biên dịch độc lập.

Hai meta-annotation có vai trò khác nhau:

- `@Target(ElementType.TYPE_USE)` cho phép xuất hiện ở vị trí sử dụng kiểu, chẳng hạn `List<@Tag("x") String>`.
- `@Retention(RetentionPolicy.RUNTIME)` yêu cầu giữ annotation để Reflection có thể đọc ở runtime. Nếu thiếu `@Retention`, giá trị mặc định là `CLASS`: compiler có thể lưu thông tin trong class file nhưng các API Reflection runtime sẽ **không trả về** annotation ấy như kỳ vọng.

Không phải annotation nào xuất hiện gần một field cũng nhất thiết là annotation trên đối số kiểu. Cần xét chính xác **vị trí trong cây kiểu** mà annotation được gắn.

**Lưu ý:** Java compiler không tự kiểm tra hay thực thi ý nghĩa nghiệp vụ của `@Tag`. Nó chỉ ghi và cung cấp metadata theo hợp đồng ngôn ngữ; việc hiểu `"element"` là quy tắc xác thực, serialization hay nullness cần một framework/tool riêng.

## 2. AnnotatedType, ParameterizedType và AnnotatedParameterizedType

Ba API có nhiệm vụ khác nhau:

| API | Thuộc package | Diễn giải |
| --- | --- | --- |
| `Type` | `java.lang.reflect` | Giao diện chung đại diện cho một kiểu Java; có thể là `Class`, `ParameterizedType`, `TypeVariable`, v.v. |
| `ParameterizedType` | `java.lang.reflect` | Metadata của kiểu generic có đối số thực, chẳng hạn `List<String>`; `getActualTypeArguments()` trả `Type[]` |
| `AnnotatedType` | `java.lang.reflect` | **Một lần sử dụng kiểu** có thể mang type-use annotations; `getType()` trả kiểu nền `Type`, `getAnnotations()` đọc annotation tại **nút hiện tại** |
| `AnnotatedParameterizedType` | `java.lang.reflect` | Một `AnnotatedType` biểu diễn **lần sử dụng kiểu parameterized**; `getAnnotatedActualTypeArguments()` trả từng đối số dưới dạng `AnnotatedType[]`, nhờ đó giữ lại annotation tại mỗi đối số |

Ví dụ dữ liệu:

```java
Map<@Tag("key") String, List<@Tag("item") Integer>> values;
```

Cây kiểu có nhiều cấp:

```text
Map<String, List<Integer>>     (kiểu parameterized ngoài cùng)
├─ argument[0]: String         (@Tag("key") trên String)
└─ argument[1]: List<Integer>  (kiểu parameterized lồng bên trong)
   └─ argument[0]: Integer     (@Tag("item") trên Integer)
```

Nếu chỉ gọi `ParameterizedType.getActualTypeArguments()`, ta lấy được `String` và `List<Integer>` dưới dạng các đối tượng `Type`, nhưng **không đọc trực tiếp được annotation gắn tại từng lần dùng kiểu** từ `Type` ấy. Để lấy `@Tag("key")` và `@Tag("item")`, cần duyệt **cây `AnnotatedType`**.

### Annotation của chính kiểu và annotation của đối số là hai vị trí khác nhau

Xét:

```java
@Tag("outer") List<@Tag("element") String> names;
```

- Nút ngoài `AnnotatedType` đại diện cho lần dùng `List<String>` có `@Tag("outer")`.
- Vì nút ngoài là `AnnotatedParameterizedType`, có thể gọi `getAnnotatedActualTypeArguments()`.
- Phần tử thứ nhất trong mảng trả về đại diện cho lần dùng `String` và có `@Tag("element")`.

`getAnnotations()` trên **nút ngoài** không tự gom annotation của mọi nút con. Ngược lại, annotation trên `String` không tự biến thành annotation của `List`. Phải đọc theo đúng cấp.

## 3. Lấy AnnotatedParameterizedType từ đâu?

Thông thường ta không trực tiếp tạo một đối tượng `AnnotatedParameterizedType`, mà lấy `AnnotatedType` từ Reflection, sau đó **kiểm tra loại nút** trước khi ép kiểu.

| Nơi type use xuất hiện | API bắt đầu lấy `AnnotatedType` |
| --- | --- |
| Kiểu khai báo của field | `Field.getAnnotatedType()` |
| Kiểu trả về của method | `Method.getAnnotatedReturnType()` |
| Kiểu của từng tham số method/constructor | `Method.getAnnotatedParameterTypes()` hoặc `Constructor.getAnnotatedParameterTypes()` |
| Kiểu của từng tham số qua đối tượng `Parameter` | `Parameter.getAnnotatedType()` |
| Kiểu superclass có thể mang annotation | `Class.getAnnotatedSuperclass()` |
| Các superinterface có thể mang annotation | `Class.getAnnotatedInterfaces()` |
| Kiểu của exception khai báo ở executable | `Executable.getAnnotatedExceptionTypes()` |

Ví dụ cơ bản trên một field `names`:

```java
Field field = Sample.class.getDeclaredField("names");
AnnotatedType annotated = field.getAnnotatedType();

if (annotated instanceof AnnotatedParameterizedType parameterized) {
    AnnotatedType[] args = parameterized.getAnnotatedActualTypeArguments();
    // Mỗi args[i] là một type use, có thể có annotation riêng.
}
```

Đây là mảnh mã minh họa, cần `Sample`, import các kiểu Reflection và xử lý `NoSuchFieldException`. Kể cả một generic field `List<String>` **không gắn annotation nào**, `getAnnotatedType()` vẫn có thể là `AnnotatedParameterizedType`; annotation array rỗng không có nghĩa nút không phải parameterized.

Ngược lại, field `String single` có type use thông thường `String` (không có type argument), nên không nên ép mù quáng nút đó thành `AnnotatedParameterizedType`.

**Chú ý:** Một `AnnotatedType` có thể thuộc nhiều dạng cụ thể như `AnnotatedArrayType`, `AnnotatedWildcardType` hoặc `AnnotatedTypeVariable`. Chỉ cast sang `AnnotatedParameterizedType` khi `instanceof` xác nhận loại nút.

## 4. Ví dụ Java 17+ đầy đủ và đầu ra xác định

Tạo tệp `AnnotatedTypeDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;

public class AnnotatedTypeDemo {
    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface Tag {
        String value();
    }

    public static class Sample {
        public @Tag("outer") List<@Tag("element") String> names;

        public Map<@Tag("key") String,
                   List<@Tag("nested") Integer>> scores;

        public List<String> plain;
        public String single;

        public void accept(List<@Tag("parameter") String> values) {}

        public List<@Tag("result") String> read() {
            return List.of();
        }
    }

    static String label(AnnotatedType type) {
        Tag tag = type.getAnnotation(Tag.class);
        return tag == null ? "none" : tag.value();
    }

    public static void main(String[] args) throws Exception {
        Field names = Sample.class.getDeclaredField("names");
        System.out.println("erased=" + names.getType().getTypeName());
        System.out.println("generic=" + names.getGenericType().getTypeName());

        AnnotatedType annotated = names.getAnnotatedType();
        System.out.println("root=" + label(annotated));
        System.out.println(
                "parameterized="
                + (annotated instanceof AnnotatedParameterizedType)
        );

        AnnotatedType first =
                ((AnnotatedParameterizedType) annotated)
                .getAnnotatedActualTypeArguments()[0];
        System.out.println(
                "argument=" + first.getType().getTypeName()
                + ",tag=" + label(first)
        );

        AnnotatedParameterizedType scores =
                (AnnotatedParameterizedType) Sample.class
                .getDeclaredField("scores").getAnnotatedType();

        AnnotatedType[] pair =
                scores.getAnnotatedActualTypeArguments();
        System.out.println("key=" + label(pair[0]));

        AnnotatedType nested =
                ((AnnotatedParameterizedType) pair[1])
                .getAnnotatedActualTypeArguments()[0];
        System.out.println("nested=" + label(nested));

        AnnotatedType plain =
                Sample.class.getDeclaredField("plain").getAnnotatedType();
        System.out.println(
                "plain parameterized="
                + (plain instanceof AnnotatedParameterizedType)
        );
        System.out.println(
                "plain argument="
                + label(((AnnotatedParameterizedType) plain)
                        .getAnnotatedActualTypeArguments()[0])
        );
        System.out.println(
                "single parameterized="
                + (Sample.class.getDeclaredField("single")
                        .getAnnotatedType()
                        instanceof AnnotatedParameterizedType)
        );

        Method accept =
                Sample.class.getDeclaredMethod("accept", List.class);
        System.out.println(
                "method parameter="
                + label(((AnnotatedParameterizedType)
                        accept.getAnnotatedParameterTypes()[0])
                        .getAnnotatedActualTypeArguments()[0])
        );

        Method read = Sample.class.getDeclaredMethod("read");
        System.out.println(
                "method result="
                + label(((AnnotatedParameterizedType)
                        read.getAnnotatedReturnType())
                        .getAnnotatedActualTypeArguments()[0])
        );
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac AnnotatedTypeDemo.java
java AnnotatedTypeDemo
```

Đầu ra:

```text
erased=java.util.List
generic=java.util.List<java.lang.String>
root=outer
parameterized=true
argument=java.lang.String,tag=element
key=key
nested=nested
plain parameterized=true
plain argument=none
single parameterized=false
method parameter=parameter
method result=result
```

Giải thích:

1. `Field.getType()` chỉ cho class đã erasure: `java.util.List`.
2. `Field.getGenericType()` cho `java.util.List<java.lang.String>`, nhưng chưa phải một cây nút chứa type-use annotations.
3. `Field.getAnnotatedType()` trả nút ngoài; `label(annotated)` đọc `@Tag("outer")`.
4. `getAnnotatedActualTypeArguments()[0]` trả nút của `String` trong `List<...>`; nút ấy có `@Tag("element")`.
5. Field `scores` chứa `Map` với **hai đối số kiểu**. Nút thứ nhất gắn `key`, nút thứ hai là `List<Integer>`; phải đi tiếp vào nút thứ hai mới lấy được `nested` trên `Integer`.
6. Field `plain` chứng minh việc **không có annotation** trên generic argument không làm mất tính chất parameterized. Field `single` chứng minh không phải mọi `AnnotatedType` đều ép được thành `AnnotatedParameterizedType`.
7. `getAnnotatedParameterTypes()[0]` và `getAnnotatedReturnType()` cũng có thể dẫn đến type argument được annotation như field.

Chương trình đọc metadata bằng Reflection, **không cần instance của `Sample`** và không gọi `accept()`/`read()`. Nó cũng không dựa vào thứ tự của `getDeclaredFields()` hay `getDeclaredMethods()`, vì luôn tra cứu từng field/method bằng tên và kiểu tham số tương ứng.

## 5. Cách đọc annotation ở từng đối số kiểu

`AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` trả về `AnnotatedType[]`. Vị trí mảng tương ứng với **vị trí đối số generic được khai báo trong type use**, ví dụ:

```java
Map<@Tag("key") String, @Tag("value") Integer> data;
```

- `args[0]` biểu diễn `String`; `args[0].getAnnotation(Tag.class)` có `value() == "key"`.
- `args[1]` biểu diễn `Integer`; `args[1].getAnnotation(Tag.class)` có `value() == "value"`.

Khi không có annotation `Tag` tại nút đang xét, `getAnnotation(Tag.class)` trả `null`. Dùng `getAnnotations()` để đọc các type-use annotations hiện diện ở **chính nút ấy**, hoặc `getDeclaredAnnotations()` khi cần các annotation được khai báo trực tiếp tại nút. Cần kiểm tra `@Retention(RUNTIME)` của các annotation muốn đọc.

Một hình thức xử lý có kiểm tra an toàn:

```java
AnnotatedType typeUse = field.getAnnotatedType();

if (typeUse instanceof AnnotatedParameterizedType pt) {
    AnnotatedType[] typeArgs = pt.getAnnotatedActualTypeArguments();

    for (int i = 0; i < typeArgs.length; i++) {
        AnnotatedType argument = typeArgs[i];
        Tag tag = argument.getAnnotation(Tag.class);
        // tag có thể null nếu đối số thứ i không được gắn @Tag.
    }
}
```

Đây là đoạn minh họa trong ngữ cảnh đã có `Field field` và annotation `Tag` trong scope. Nếu cần lấy annotation trên **container type** `List` hoặc `Map`, truy vấn `typeUse.getAnnotation(Tag.class)` trước khi duyệt các phần tử; không nên dùng `field.getAnnotation(Tag.class)` để thay thế.

### Field annotation khác type-use annotation

Một annotation có `@Target(ElementType.FIELD)` nhắm vào **khai báo field** và được tra qua `Field.getAnnotation`. Một annotation chỉ có `@Target(ElementType.TYPE_USE)` nhắm vào **lần dùng kiểu** và được tra qua `Field.getAnnotatedType().getAnnotation` hoặc các nút con.

Nếu annotation có nhiều target như `FIELD` và `TYPE_USE`, cần đọc tài liệu về **ngữ cảnh cú pháp và vị trí annotation** để xác định nó được lưu ở đâu. Không nên suy rằng `field.getAnnotations()` luôn chứa mọi annotation trên generic arguments.

Điều tương tự xảy ra với method: `method.getAnnotations()` nói về **annotation trên khai báo method**, còn `method.getAnnotatedReturnType()` nói về **annotation trên kiểu trả về**. Với tham số, `Parameter.getAnnotation` liên quan annotation trên khai báo parameter, khác với `Parameter.getAnnotatedType()` của kiểu tham số ấy.

## 6. Kiểu generic lồng nhau: phải duyệt đệ quy

Một `Map<String, List<Integer>>` là cây nhiều cấp. `getAnnotatedActualTypeArguments()` của `Map` **chỉ trả về hai nút con trực tiếp**: `String` và `List<Integer>`; nó không tự flatten đến `Integer`.

Một thuật toán duyệt kiểu tổng quát có thể phân nhánh theo các subinterface:

| Kiểu nút | API để tiếp tục duyệt |
| --- | --- |
| `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()`; khi cần nested owner: `getAnnotatedOwnerType()` |
| `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | `getAnnotatedBounds()` |
| `AnnotatedType` thông thường | Đọc annotation ngay tại nút; có thể không có nút con cần duyệt |

Ví dụ (mảnh mã minh họa không độc lập):

```java
static void visit(AnnotatedType type) {
    // Xử lý annotation trên chính type tại đây.

    if (type instanceof AnnotatedParameterizedType pt) {
        for (AnnotatedType arg : pt.getAnnotatedActualTypeArguments()) {
            visit(arg);
        }
    } else if (type instanceof AnnotatedArrayType at) {
        visit(at.getAnnotatedGenericComponentType());
    } else if (type instanceof AnnotatedWildcardType wt) {
        for (AnnotatedType upper : wt.getAnnotatedUpperBounds()) {
            visit(upper);
        }
        for (AnnotatedType lower : wt.getAnnotatedLowerBounds()) {
            visit(lower);
        }
    } else if (type instanceof AnnotatedTypeVariable tv) {
        for (AnnotatedType bound : tv.getAnnotatedBounds()) {
            visit(bound);
        }
    }
}
```

Đoạn này cần import các interface `AnnotatedType`, `AnnotatedParameterizedType`, `AnnotatedArrayType`, `AnnotatedWildcardType`, `AnnotatedTypeVariable`; giả định đã đặt trong class Java. **Lưu ý quan trọng:** Type-variable bounds có thể tự tham chiếu hoặc tạo đồ thị kiểu lặp (ví dụ `T extends Comparable<T>`), vì vậy một thuật toán duyệt metadata production cần **phát hiện chu trình / giới hạn tập nút đã thăm** thay vì đệ quy vô hạn. `visit` ở trên chỉ trình bày các nhánh API, chưa phải thư viện duyệt hoàn chỉnh.

Nếu generic argument là `List<@Tag String>`, nút argument là **`AnnotatedParameterizedType`**, không phải nút leaf. Nếu là `? extends @Tag Number`, cần đi vào `AnnotatedWildcardType.getAnnotatedUpperBounds()`. Nếu là `String @Tag []`, cần chú ý annotation gắn vào vị trí mảng hay thành phần mảng theo cú pháp Java; đường đi nằm ở `AnnotatedArrayType`.

## 7. getAnnotatedOwnerType() và nested generic types

Với một lần dùng kiểu nested/member type, annotation có thể nằm trên **owner**. `AnnotatedParameterizedType.getAnnotatedOwnerType()` trả về biểu diễn annotated type của kiểu bao ngoài nếu có, thay vì gộp annotation của owner vào các type arguments của nested type.

Ví dụ ý tưởng:

```java
class Outer<T> {
    class Inner<U> {}
}
```

Nếu code dùng một kiểu như `Outer<String>.Inner<Integer>` và có annotation gắn vào lần sử dụng `Outer<String>`, một công cụ phân tích metadata phải quan sát thêm `getAnnotatedOwnerType()` của nút Inner. Nó không nên giả định annotation owner xuất hiện trong `Inner`'s `getAnnotatedActualTypeArguments()`.

Đối với kiểu top-level không có owner, `getAnnotatedOwnerType()` trả `null`. Tài liệu Oracle cũng lưu ý rằng `getAnnotatedActualTypeArguments()` **có thể là mảng rỗng** trong một số trường hợp hiếm, chẳng hạn nút biểu diễn non-parameterized member type lồng bên trong parameterized type. Vì vậy đừng tự suy ra số phần tử chỉ dựa vào việc cast thành `AnnotatedParameterizedType`; luôn dùng độ dài mảng thực tế.

Hợp đồng `getAnnotatedOwnerType()` có từ Java 9; ví dụ và kiến thức trong bài áp dụng tốt với Java 17+.

## 8. Giới hạn và những điều API không làm

**Không thay đổi runtime generic erasure:** `List<@Tag String>` và `List<String>` vẫn có cùng raw class `List.class`. Annotation không làm JVM tạo một class mới tên `ListOfTagString`, cũng không thay đổi nội dung các phần tử `List`.

**Không tự xác thực giá trị:** Chỉ có `@Tag` không khiến Java tự kiểm tra từng String trong list. Nếu cần enforce rule, framework cần code để đọc annotation đúng vị trí và kiểm tra dữ liệu.

**Không giải generic type variable cho từng subclass:** `Box<T>` được thừa kế dưới dạng `Box<String>` không tự biến mọi `TypeVariable` trên khai báo của `Box` thành `String` khi gọi Reflection trên declaration gốc. Muốn hiểu giá trị type argument theo một subclass, cần xét mapping `TypeVariable` và generic superclass/interface riêng.

**Không đảm bảo annotations luôn có thể được đọc:** Nếu retention không phải `RUNTIME`, Reflection sẽ không thấy annotation như mong muốn; class-file biến đổi, giới hạn metadata hoặc các hình thức type use khác cũng cần được xử lý đúng contract.

**Không phải lúc nào cũng là `AnnotatedParameterizedType`:** `int`, `String`, `String[]`, wildcard/type variable đều có thể yêu cầu những dạng `AnnotatedType` khác. Kiểm tra bằng `instanceof`.

**Không trộn vị trí và tên annotation:** Annotation cùng loại `Tag` có thể xuất hiện đồng thời ở container, type argument, wildcard bound và array dimension với giá trị khác nhau. Đọc annotation ở sai nút dễ dẫn đến báo cáo metadata sai dù code không ném exception.

## 9. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| Dùng `Field.getType()` để tìm annotation trên `List<@Tag String>` | `getType()` chỉ trả kiểu raw sau erasure; dùng `getAnnotatedType()` |
| Dùng `Field.getGenericType()` rồi nghĩ `ParameterizedType` mang đầy đủ type-use annotations | `ParameterizedType` mang cấu trúc generic; muốn annotation ở từng vị trí dùng `AnnotatedParameterizedType` |
| Đọc `annotated.getAnnotations()` và cho rằng có toàn bộ annotation của các type argument | Chỉ đọc annotation ở nút đang xét; cần duyệt `getAnnotatedActualTypeArguments()` |
| Thấy `getAnnotations()` rỗng thì khẳng định không phải generic | Generic type use vẫn có thể là `AnnotatedParameterizedType` nhưng không mang annotation |
| Cast mọi `AnnotatedType` sang `AnnotatedParameterizedType` | Kiểm tra `instanceof`, vì có array, wildcard, type variable và kiểu thông thường |
| Tưởng `List<@Tag String>` luôn bắt buộc các phần tử mang điều kiện `Tag` | Type-use annotation là metadata; runtime enforcement do ứng dụng/framework quyết định |
| Chỉ duyệt type arguments của `Map` rồi bỏ qua `List<Integer>` ở cấp trong | Duyệt đệ quy cây annotated types; chú ý chu trình của type variables |
| Tưởng `getAnnotatedOwnerType()` luôn trả một kiểu | Với top-level type, thường là `null` |
| Quên `@Retention(RUNTIME)` | Annotation không xuất hiện qua Reflection runtime nếu retention không phù hợp |
| Dùng `Method.getAnnotations()` thay cho type-use annotation ở kiểu trả về | Dùng `Method.getAnnotatedReturnType()` rồi duyệt đúng cấp |

## 10. Tự kiểm tra kiến thức

1. Với `List<@Tag String>`, lấy annotation gắn lên `String` bằng API nào? **`Field.getAnnotatedType()` → kiểm tra/cast `AnnotatedParameterizedType` → `getAnnotatedActualTypeArguments()[0].getAnnotation(Tag.class)`.**
2. `AnnotatedParameterizedType` là subinterface của gì? **`AnnotatedType`** (và gián tiếp kế thừa `AnnotatedElement`).
3. `ParameterizedType.getActualTypeArguments()` trả về kiểu dữ liệu gì? **`Type[]`**, khác với **`AnnotatedType[]`** của `getAnnotatedActualTypeArguments()`.
4. Với `@Tag("outer") List<@Tag("inner") String>`, `getAnnotation(Tag.class)` trên nút ngoài cho gì? **`outer`**, không phải `inner`.
5. Vì sao annotation dùng để đọc bằng Reflection cần `@Retention(RUNTIME)`? **Để runtime Reflection truy vấn được annotation.**
6. Không có annotation ở generic argument thì `getAnnotatedType()` có còn là `AnnotatedParameterizedType` không? **Có thể có**, vì hình dạng parameterized độc lập với việc annotation có hiện diện.
7. Trong `Map<String, List<@Tag Integer>>`, làm sao đến `Integer`? **Đi vào đối số thứ hai của Map, rồi vào đối số thứ nhất của List**.
8. Annotation trên `? extends @Tag Number` nằm ở nút nào? **Nút upper bound** của `AnnotatedWildcardType`.
9. Có được cast `String` plain type use thẳng sang `AnnotatedParameterizedType` không? **Không**, nên dùng `instanceof`.
10. Type-use annotation có tự xác nhận dữ liệu trong một `List` thỏa rule không? **Không**, nó là metadata mà công cụ khác có thể diễn giải.

## 11. Tài liệu chính thức

- [Oracle Java SE 21 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html): `getAnnotatedActualTypeArguments()`, `getAnnotatedOwnerType()` và lưu ý mảng rỗng trong nested type.
- [Oracle Java SE 21 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html): `getType()`, `getAnnotations()`, `getAnnotation()` và các subinterface.
- [Oracle Java SE 21 — `Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html): `getType()`, `getGenericType()`, `getAnnotatedType()`.
- [Oracle Java SE 21 — `ParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html): đối số kiểu generic chưa gắn thông tin annotation theo từng type use.
- [Java Language Specification SE 21 — §9.7 Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7): vị trí annotation và type-use annotation.

**Ghi nhớ:** `ParameterizedType` cho biết **các kiểu generic nào** được sử dụng, còn `AnnotatedParameterizedType` cho phép biết **annotation nằm trên chính generic type use hoặc từng đối số kiểu ở vị trí nào**. Muốn đọc đúng `List<@Tag String>` hay generic lồng nhau, phải duyệt cây `AnnotatedType` thay vì chỉ xem raw type hoặc một annotation array ở nút ngoài.