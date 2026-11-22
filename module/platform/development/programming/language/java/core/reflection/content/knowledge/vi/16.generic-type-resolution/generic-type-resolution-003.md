# Ánh xạ `TypeVariable` sang kiểu cụ thể qua nhiều tầng kế thừa

## 1. Vấn đề: một field được khai báo kiểu `T`, nhưng lớp con đã chọn `String`

Trong Java, generic inheritance có thể truyền tham số kiểu qua nhiều cấp. Xét chuỗi:

~~~java
class Base<T> {
    T item;
}
class Middle<U> extends Base<List<U>> {
}
class Leaf extends Middle<String> {
}
~~~

Khi nhìn `Base.class`, field `item` có kiểu generic là **`T`**; không có `String` nào trong khai báo của `Base`. Tuy nhiên khi nhìn từ `Leaf`, ta lần theo:

~~~text
Leaf extends Middle<String>
     U = String

Middle<U> extends Base<List<U>>
     T = List<U>

Thay U = String vào T = List<U>:
     T = List<String>

Base<T>.item, xét từ Leaf:
     List<String>
~~~

**Đây là phép phân giải kiểu trong ngữ cảnh của lớp con**, không phải thay đổi metadata gốc của `Base`. `Base.class.getDeclaredField("item").getGenericType()` vẫn trả một `TypeVariable` đại diện `T`; Reflection không có API một bước tự biến mọi `T` thành `List<String>` theo lớp con tùy ý. Bạn phải đọc generic superclass/interface, xây dựng ánh xạ biến kiểu và áp dụng lần lượt các phép thế.

Các framework như serializer, ORM, dependency injection container hoặc type-aware API generator thường phải giải bài toán này: cùng một generic base class có thể được chuyên biệt hóa thành nhiều kiểu cụ thể tùy lớp con thực tế.

## 2. Những biểu diễn `Type` phải hiểu

`java.lang.reflect.Type` là giao diện đại diện thông tin kiểu phản chiếu. Các biểu diễn quan trọng:

| Loại `Type` | Ví dụ | Reflection cung cấp |
| --- | --- | --- |
| `Class<?>` | `String.class`, `List.class`, `int.class` | Kiểu cụ thể hoặc raw type |
| `TypeVariable<?>` | `T` trong `Base<T>`, `U` trong `Middle<U>` | Tham số kiểu do class/method/constructor khai báo |
| `ParameterizedType` | `Base<List<U>>`, `List<String>` | Raw type cùng danh sách actual type arguments |
| `WildcardType` | `? extends T`, `? super Number` | Upper/lower bounds của wildcard |
| `GenericArrayType` | `T[]` hoặc `List<T>[]` | Generic component type khi thành phần chưa phải kiểu class thông thường |

Một `TypeVariable` có **declaration identity**, không chỉ có tên. Hai class có thể cùng khai báo tham số kiểu tên `T` nhưng chúng là **hai biến kiểu khác nhau**. Khi xây dựng bảng ánh xạ, khóa nên là `TypeVariable<?>`, chẳng hạn `Map<TypeVariable<?>, Type>`, thay vì `Map<String, Type>`; ánh xạ theo mỗi chuỗi `"T"` có thể đè nhầm biến đến từ declaration khác.

Một `TypeVariable` có thể có bound:

~~~java
class Store<T extends Number> {
    T amount;
}
~~~

`T` vẫn là một biến kiểu. `T.getBounds()` phản ánh bound `Number`, **không** có nghĩa mọi instance của `Store` dùng đúng `Number`. Ví dụ `Store<Integer>` khiến `T` được ràng buộc với `Integer` trong ngữ cảnh lớp con tương ứng. Không dùng bound làm kết quả concrete khi chưa có ánh xạ.

## 3. Các API Reflection nối các mắt xích kế thừa

Một lớp `Leaf extends Middle<String>` chứa dữ liệu quan trọng trong `Leaf.class.getGenericSuperclass()`:

- Nếu superclass có type arguments, kết quả thường là `ParameterizedType`. `getRawType()` trỏ tới `Middle.class`, `getActualTypeArguments()` chứa `String.class`.
- `Middle.class.getTypeParameters()` trả danh sách biến kiểu của `Middle`, ở đây là `U`. Ghép từng formal type variable với actual type argument theo **vị trí**: `U → String`.
- Tiếp theo, `Middle.class.getGenericSuperclass()` biểu diễn `Base<List<U>>`. `Base.class.getTypeParameters()` trả `T` và actual argument là `List<U>`: ghi `T → List<U>`.
- Áp dụng ánh xạ đệ quy: `T → List<U> → List<String>`.

| Bước trên đường từ lớp cụ thể | Formal parameter thuộc declaration cha | Actual argument ở cạnh kế thừa |
| --- | --- | --- |
| `Leaf → Middle<String>` | `Middle.U` | `String` |
| `Middle<U> → Base<List<U>>` | `Base.T` | `List<U>` |
| Phân giải `Base.T` trong ngữ cảnh `Leaf` | `Base.T` | `List<String>` |

Cần lấy cạnh kế thừa từ **`getGenericSuperclass()`**, không phải `getSuperclass()` đơn thuần. API `getSuperclass()` chỉ trả raw `Class` và làm mất thông tin argument `String` hoặc `List<U>` trên cạnh đó.

Tương tự, với generic interface, phải dùng `getGenericInterfaces()` cùng `ParameterizedType` để lấy argument. Nhưng interface có thể tạo thành đồ thị nhiều nhánh, không phải chỉ một chuỗi superclass; cần thuật toán duyệt các cạnh interface và xác định declaration đang cần phân giải.

## 4. Ví dụ Java 17+ chạy được: ánh xạ và phân giải nested generic

Tạo file `GenericTypeResolverDemo.java`:

~~~java
import java.lang.reflect.*;
import java.util.*;

public class GenericTypeResolverDemo {
    static class Base<T> {
        T item;
        List<T> history;
        List<? extends T> readable;
    }

    static class Middle<U> extends Base<List<U>> {
    }

    static class Leaf extends Middle<String> {
    }

    static Map<TypeVariable<?>, Type> bindings(
            Class<?> concrete, Class<?> declaringClass) {
        Map<TypeVariable<?>, Type> result = new LinkedHashMap<>();

        if (!declaringClass.isAssignableFrom(concrete)) {
            throw new IllegalArgumentException("Not an ancestor");
        }

        Class<?> current = concrete;
        while (current != declaringClass) {
            Type parent = current.getGenericSuperclass();
            if (parent == null) {
                throw new IllegalArgumentException("No superclass path");
            }

            if (parent instanceof ParameterizedType p) {
                Class<?> raw = (Class<?>) p.getRawType();
                TypeVariable<?>[] formals = raw.getTypeParameters();
                Type[] actuals = p.getActualTypeArguments();

                for (int i = 0; i < formals.length; i++) {
                    result.put(formals[i], actuals[i]);
                }
                current = raw;
            } else {
                // Một cạnh extends không mang generic arguments.
                current = (Class<?>) parent;
            }
        }
        return result;
    }

    // Hiển thị kiểu sau thế biến. Đây là ví dụ cho đường superclass.
    static String render(
            Type type, Map<TypeVariable<?>, Type> bindings) {
        if (type instanceof TypeVariable<?> variable) {
            Type replacement = bindings.get(variable);
            if (replacement == null || replacement.equals(variable)) {
                return variable.getName();
            }
            return render(replacement, bindings);
        }

        if (type instanceof ParameterizedType p) {
            List<String> parts = new ArrayList<>();
            for (Type argument : p.getActualTypeArguments()) {
                parts.add(render(argument, bindings));
            }
            return render(p.getRawType(), bindings)
                    + "<" + String.join(", ", parts) + ">";
        }

        if (type instanceof WildcardType w) {
            if (w.getLowerBounds().length > 0) {
                return "? super "
                        + render(w.getLowerBounds()[0], bindings);
            }
            Type upper = w.getUpperBounds()[0];
            return upper == Object.class
                    ? "?"
                    : "? extends " + render(upper, bindings);
        }

        if (type instanceof GenericArrayType a) {
            return render(a.getGenericComponentType(), bindings) + "[]";
        }

        if (type instanceof Class<?> c) {
            return c.isArray()
                    ? render(c.getComponentType(), bindings) + "[]"
                    : c.getSimpleName();
        }

        return type.getTypeName();
    }

    public static void main(String[] args) throws Exception {
        Map<TypeVariable<?>, Type> map =
                bindings(Leaf.class, Base.class);

        for (TypeVariable<?> variable : Middle.class.getTypeParameters()) {
            System.out.println(variable.getName() + " -> "
                    + render(variable, map));
        }
        for (TypeVariable<?> variable : Base.class.getTypeParameters()) {
            System.out.println(variable.getName() + " -> "
                    + render(variable, map));
        }

        for (String name : List.of("item", "history", "readable")) {
            Field field = Base.class.getDeclaredField(name);
            System.out.println(name
                    + ": raw=" + field.getType().getSimpleName()
                    + ", generic=" + field.getGenericType().getTypeName()
                    + ", resolved=" + render(field.getGenericType(), map));
        }
    }
}
~~~

Lệnh biên dịch và thực thi:

~~~bash
javac --release 17 GenericTypeResolverDemo.java
java GenericTypeResolverDemo
~~~

Đầu ra:

~~~text
U -> String
T -> List<String>
item: raw=Object, generic=T, resolved=List<String>
history: raw=List, generic=java.util.List<T>, resolved=List<List<String>>
readable: raw=List, generic=java.util.List<? extends T>, resolved=List<? extends List<String>>
~~~

Kết quả đã được kiểm tra bằng đoạn tương đương trong JShell: biên dịch/cung cấp type metadata Java 17 và chạy trên JDK 24 cho ra đúng các dòng trên.

### Phân tích từng field

- `item` của `Base<T>`: `Field.getType()` trả `Object.class` vì erasure của `T` không có bound là `Object`; `getGenericType()` vẫn là `TypeVariable T`. Trong ngữ cảnh `Leaf`, `T` được giải thành `List<String>`.
- `history`: khai báo `List<T>`. Khi `T → List<String>` thì toàn biểu thức thành `List<List<String>>`. Thay biến kiểu phải **đệ quy bên trong argument** của `ParameterizedType`.
- `readable`: khai báo `List<? extends T>`. Kết quả là `List<? extends List<String>>`. Không bỏ wildcard khi phân giải; `? extends` vẫn mang ý nghĩa variance của API.
- `U` của `Middle<U>` ánh xạ sang `String`, nên `T` của `Base<T>` có thể được giải tiếp thông qua `List<U>`.

Trong ví dụ, `render` trả chuỗi để **giải thích kết quả**, không tạo lại một đối tượng `Type` mới. Nếu framework thực sự cần đối tượng `ParameterizedType` đã được thay type argument, cần tạo biểu diễn bất biến tuân thủ hợp đồng `ParameterizedType` (hoặc dùng thư viện type-resolution đã được kiểm chứng) và xử lý `ownerType`, `WildcardType`, `GenericArrayType`, equality/hashCode.

## 5. Tại sao bảng ánh xạ phải đi từ lớp cụ thể lên lớp khai báo?

Bạn bắt đầu ở nơi **biết argument cụ thể**, ví dụ `Leaf extends Middle<String>`. Nếu chỉ đọc `Middle.class` và `Base.class` độc lập thì chưa có thông tin nào bảo đảm `U` là `String`; chúng chỉ biết quan hệ `T = List<U>`.

Quy trình tổng quát với một đường superclass:

1. Nhận `Class<?> concrete` là class thực tế và `Class<?> declaring` là class khai báo field/method đang cần phân giải.
2. Xác định tuyến `concrete → ... → declaring` qua `getGenericSuperclass()`.
3. Trên từng cạnh `Subclass extends Parent<...>`, so sánh `Parent.getTypeParameters()` với `ParameterizedType.getActualTypeArguments()` để ghi ánh xạ `TypeVariable → Type`.
4. Khi gặp biến kiểu trong field, method hoặc constructor, tìm binding dựa vào chính đối tượng `TypeVariable<?>` và thay đệ quy cho tới khi hết ánh xạ.
5. Khi gặp `ParameterizedType`, thay **từng argument**; với wildcard và generic array, duyệt các bound/component type theo cấu trúc.
6. Nếu còn biến kiểu chưa giải được, giữ nó ở trạng thái **unresolved** hoặc biểu diễn rõ ràng là chưa biết; không mặc định gán `Object` hay upper bound thành concrete type.

Trong ví dụ, map cố ý lưu `T → List<U>` chứ không đòi biến ngay thành `List<String>` tại thời điểm chèn. Khi `render(T, map)` được gọi, nó lần theo `T → List<U>` và nhìn vào `U → String` để cho kết quả cuối.

Với generic field khai báo trong superclass, đừng dùng `leaf.getDeclaredField("item")`: `getDeclaredField` chỉ tìm field khai báo trực tiếp ở `Leaf`. Hãy tìm `Base.class.getDeclaredField("item")` hoặc đi từ field tìm được qua `field.getDeclaringClass()`; sau đó dùng lớp concrete làm ngữ cảnh phân giải.

## 6. Generic method và biến kiểu riêng của method

`Method.getGenericReturnType()` và `Method.getGenericParameterTypes()` cũng có thể chứa `TypeVariable`. Cần phân biệt hai nguồn:

~~~java
class Container<T> {
    T find() {
        return null;
    }

    <R> R convert(R value) {
        return value;
    }
}
~~~

- `T` thuộc khai báo **class** `Container<T>`. Nếu có `StringContainer extends Container<String>` thì mapping của generic superclass cho phép suy ra return type của `find()` là `String` trong ngữ cảnh đó.
- `R` thuộc khai báo **method** `convert`, không phải biến kiểu của `Container`. Chỉ biết subclass của `Container<String>` **không** đủ để suy ra `R` là kiểu gì; muốn xác định `R` phải có thêm ngữ cảnh áp dụng phương thức hoặc type inference tương ứng.

Bạn có thể gọi `TypeVariable.getGenericDeclaration()` để xác định biến kiểu được khai báo bởi `Class`, `Method` hay `Constructor`. Điều này giúp tránh ánh xạ nhầm một `T` ở method với `T` ở class, dù tên giống nhau.

**Type erasure:** generic metadata cho phép phân tích ràng buộc kiểu, nhưng JVM không biến đối tượng `new ArrayList<String>()` thành class runtime riêng biệt với `new ArrayList<Integer>()`. `obj.getClass()` chỉ cho `ArrayList.class`. Nếu mã cần biết `String`, nguồn thông tin đáng tin phải nằm trong superclass/interface generic được khai báo, `Type` được capture, annotation hoặc một type token tương ứng; nó không thể luôn khôi phục từ object runtime.

## 7. Mở rộng sang generic interface

Ví dụ:

~~~java
interface Handler<T> {
    void handle(T value);
}

interface NamedHandler<U> extends Handler<List<U>> {
}

class StringHandler implements NamedHandler<String> {
    @Override
    public void handle(List<String> value) {
    }
}
~~~

Quan hệ cần giải là:

~~~text
StringHandler -> NamedHandler<String>
NamedHandler<U> -> Handler<List<U>>

U = String
Handler.T = List<U> = List<String>
~~~

Mỗi đường nối **interface** lấy qua `Class.getGenericInterfaces()`; raw interface `Handler.class` có type parameter `T`, còn cạnh generic cần đọc các actual type arguments. Từ `StringHandler.class` đi lên có thể gặp nhiều interface, superclass chứa interface, generic interface lồng nhau: vì thế thuật toán phải duyệt **đồ thị interface + superclass**, tìm đúng declaration mục tiêu rồi tích lũy mapping theo từng đường hợp lệ.

Đoạn khai báo trên là ví dụ lý thuyết; mã `bindings` ở mục 4 **chỉ hỗ trợ một chuỗi superclass** nên không được đem áp dụng trực tiếp cho `StringHandler → Handler` mà kết luận sai rằng không có đường. Một triển khai đủ dùng trong framework nên thêm duyệt `getGenericInterfaces()` và kiểm tra những interface lặp trong đồ thị.

## 8. Các trường hợp mà một mapping đơn giản chưa đủ

### A. Raw type làm mất argument

~~~java
class RawMiddle extends Base { }
class RawLeaf extends RawMiddle { }
~~~

Khi chọn `extends Base` không có type argument, cạnh generic không cung cấp `T → SomeType`. Một thuật toán nghiêm ngặt cần nhận diện việc mất metadata do dùng raw type. Nó **không thể suy ra** một `String` cụ thể chỉ từ thông tin đã bị xóa; `T` có thể còn unresolved, mặc dù erasure runtime tương ứng bound của `T`.

### B. Bounded variable và wildcard

~~~java
class NumberBase<T extends Number> {
    List<? super T> consumer;
}
class IntegerBase extends NumberBase<Integer> {
}
~~~

Từ `IntegerBase`, ánh xạ là `T → Integer`; kiểu của field trở thành `List<? super Integer>`. **Không biến** nó thành `List<Integer>` vì wildcard `? super` không đồng nhất với concrete argument `Integer`. Upper/lower bound của wildcard là metadata cần giữ, cũng như bound của type variable khi còn unresolved.

### C. Generic array

~~~java
class ArrayBase<T> {
    T[] values;
}
class ArrayChild extends ArrayBase<String> {
}
~~~

`ArrayBase.values` có `GenericArrayType` tương ứng `T[]`; từ `ArrayChild` có thể diễn giải về mặt kiểu là `String[]`. Nhưng lời giải trình bày dưới dạng chuỗi chỉ dành cho đọc hiểu. Nếu cần tạo `Type` có thể dùng trong framework, phân biệt `Class<?>` của mảng reifiable, `GenericArrayType` và khả năng runtime khởi tạo mảng một cách an toàn.

### D. Nested/owner types

Ví dụ `Outer<String>.Inner<Integer>` có `ownerType` và các actual type arguments. Chỉ lấy `getRawType()` + `getActualTypeArguments()` rồi tự ghép thành chuỗi chưa đủ để biểu diễn tất cả ý nghĩa kiểu lồng. Resolver thực tế phải xét `ParameterizedType.getOwnerType()`, đặc biệt với non-static inner class.

### E. Chu kỳ bounds và biến chưa ràng buộc

`class Node<T extends Comparable<T>>` chứa quan hệ tự tham chiếu trong **bound**. Một resolver đầy đủ không được đệ quy vô hạn khi phân tích bound hoặc alias. Nó nên có tập `visited`/đánh dấu ngữ cảnh đang phân giải và trả trạng thái unresolved/cyclic khi cần. Hàm `render` trong ví dụ chỉ giải ánh xạ tuyến tính, không phải parser/renderer tổng quát cho mọi Java type.

### F. Class loader và tên biến giống nhau

Một `TypeVariable` gắn với đúng declaration của nó. Nếu nhiều thư viện hoặc class loader cung cấp các lớp có tên đơn giản giống nhau, ánh xạ dựa vào chuỗi như `"T"`, `"U"` rất dễ sai. Dùng đối tượng `TypeVariable<?>` và khai báo nguồn; để log/debug nên in đầy đủ `getGenericDeclaration()` khi cần phân biệt.

## 9. Phân biệt `getType()`, `getGenericType()` và kiểu sau phân giải

| Câu hỏi | API/thao tác | Trên field `Base.item` trong ví dụ |
| --- | --- | --- |
| JVM biết kiểu field sau erasure là gì? | `Field.getType()` | `Object.class` |
| Khai báo generic ban đầu ở Base viết gì? | `Field.getGenericType()` | `TypeVariable T` |
| Trong ngữ cảnh Leaf, T đã được ràng buộc thế nào? | Duyệt `getGenericSuperclass()` và thay type variables | `List<String>` |
| `obj.getClass()` có tiết lộ type argument `String` không? | Class runtime của object | Không đủ để khôi phục generic argument tùy ý |

`getType()` không sai khi trả `Object.class`: JVM dùng type erasure cho descriptor. `getGenericType()` giữ thông tin khai báo để Reflection có thể tái dựng *một phần* quan hệ generic. Việc phân giải đầy đủ cần bối cảnh cụ thể của subclass và các cạnh type arguments.

Đối với method parameter, các API tương ứng là `getParameterTypes()` và `getGenericParameterTypes()`. Đối với return type của method, dùng `getReturnType()` và `getGenericReturnType()`. Việc trả về generic type ban đầu không có nghĩa đã tự áp dụng binding của subclass.

## 10. Các lỗi thường gặp và cách sửa

| Lỗi thường gặp | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Lấy `Base.class.getDeclaredField("item").getType()` rồi kết luận field là Object ở mọi ngữ cảnh | Đây chỉ là erased type | Kết hợp `getGenericType()` với binding từ concrete subclass |
| Gọi `getSuperclass()` để đi qua generic inheritance | Mất actual type arguments | Dùng `getGenericSuperclass()` |
| Lấy `getGenericSuperclass()` của `Base`, không xét `Leaf` | Base chưa biết argument cụ thể | Bắt đầu từ concrete class có liên kết generic cụ thể |
| Chỉ thay `T` ở lớp trực tiếp, không thay `U` bên trong `List<U>` | Phép thế chưa đệ quy | Đi theo chuỗi mapping cho tới `List<String>` |
| Map type variable bằng tên `"T"` | Các declaration có thể trùng tên | Dùng `Map<TypeVariable<?>, Type>` |
| Bỏ `? extends`/`? super` khi thay kiểu | Mất variance và bound | Phân giải bên trong wildcard, giữ cấu trúc wildcard |
| Coi `T extends Number` đồng nghĩa `T = Number` | Bound là giới hạn, không phải actual argument | Giữ `T` unresolved nếu không có binding |
| Dùng thuật toán một superclass cho đường generic interface | Interface là đồ thị | Duyệt thêm `getGenericInterfaces()` |
| Dùng `new ArrayList<String>().getClass()` để suy ra String | Type erasure | Cần metadata generic trên khai báo hoặc type token |
| Tự chế `ParameterizedType` chỉ bằng chuỗi | Chuỗi không đáp ứng giao diện Type, equality, owner, arrays | Tạo cấu trúc Type đầy đủ hoặc dùng thư viện đã kiểm chứng |

## 11. Tự kiểm tra

**Câu 1:** `class A<T>`, `class B<U> extends A<List<U>>`, `class C extends B<Integer>`. Trong `C`, `A.T` là gì? **`List<Integer>`**.

**Câu 2:** `Field.getGenericType()` trên `A.class` trả `T` hay `List<Integer>`? **`T`**, vì đây là metadata của khai báo `A`; việc phân giải là phép thế theo ngữ cảnh `C`.

**Câu 3:** Vì sao dùng `TypeVariable.getName()` làm khóa có thể sai? **Vì hai declaration khác nhau có thể cùng gọi biến là `T`**.

**Câu 4:** Nếu có `List<? extends T>` và `T → String` thì kiểu sau phân giải là gì? **`List<? extends String>`**, không tự biến thành `List<String>`.

**Câu 5:** Nếu `class B extends A` dùng raw type, có thể chắc chắn `A.T` là `String` không? **Không**, vì cạnh đó không cung cấp concrete type argument.

**Câu 6:** Với `interface I<T>`, lớp triển khai có thể phân giải `T` qua `getGenericSuperclass()` duy nhất không? **Không phải lúc nào cũng được**; phải xét cạnh interface từ `getGenericInterfaces()` và có thể cả nhiều nhánh.

**Câu 7:** Generic method `<R> R convert(R value)` nằm trong `A<T>`. Ràng buộc `A.T → String` có tự làm `R → String` không? **Không**; `R` thuộc declaration của method và cần ngữ cảnh suy luận riêng.

**Ghi nhớ:** Để ánh xạ `TypeVariable` qua nhiều tầng kế thừa, phải giữ **đúng declaration của biến**, đọc **generic edges** từ lớp concrete về nơi khai báo và **thay đệ quy** bên trong nested parameterized types, wildcard, array. Nếu không có đủ metadata (raw type, erasure, method variable chưa ràng buộc), hãy biểu diễn kết quả chưa xác định thay vì đoán một kiểu cụ thể.
