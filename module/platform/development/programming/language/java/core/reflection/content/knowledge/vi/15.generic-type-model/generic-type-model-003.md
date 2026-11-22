# Raw type, owner type và kiểu lồng có generic trong Java Reflection

## 1. Ba khái niệm phải phân biệt

Trong Java, một kiểu generic có thể được sử dụng với tham số kiểu cụ thể, chẳng hạn `List<String>` hoặc `Outer<String>.Inner<Integer>`. Khi đọc cấu trúc kiểu qua Reflection, ba khái niệm quan trọng là **raw type**, **owner type** và **tham số kiểu của bản thân kiểu lồng**.

- **Raw type trong ngôn ngữ Java** là cách dùng một kiểu generic mà bỏ danh sách đối số kiểu, chẳng hạn `List` thay cho `List<String>`, hoặc `Outer.Inner` khi `Outer<T>` bị dùng ở dạng raw. Raw type được Java giữ lại chủ yếu vì tương thích mã nguồn trước khi có generics.
- **Raw type theo `ParameterizedType.getRawType()`** là cấu trúc khai báo nền của một parameterized type, thường là `Class<?>`. Ví dụ, trong `List<String>`, `getRawType()` trả `List.class`. **Điều này không có nghĩa khai báo `List<String>` trong source là raw usage**: ta chỉ đang xem class/interface gốc của kiểu đã được tham số hóa.
- **Owner type** của một kiểu thành viên là kiểu mà nó là thành viên. Với `Outer<String>.Inner<Integer>`, owner của `Inner<Integer>` là `Outer<String>`. Owner giữ thông tin kiểu của phần bao bên ngoài, và bản thân `Inner` giữ tham số kiểu riêng của nó.

Ví dụ khởi đầu:

~~~java
class Outer<T> {
    class Inner<U> {}
    class Plain {}
    static class Nested<V> {}
}
~~~

Các kiểu khác nhau:

| Cách dùng | Ý nghĩa |
| --- | --- |
| `Outer<String>` | `Outer<T>` với `T = String`. |
| `Outer` | Dạng raw của `Outer<T>`. |
| `Outer<String>.Inner<Integer>` | Inner **không static**, vừa có owner `Outer<String>`, vừa có đối số kiểu riêng `Integer` cho `U`. |
| `Outer<String>.Plain` | Inner không generic riêng; owner vẫn chứa `String`. |
| `Outer.Inner` | Inner thuộc raw `Outer`, nên cũng được dùng dưới dạng raw. |
| `Outer.Nested<Long>` | Nested class **static** có tham số kiểu riêng `Long`, không phụ thuộc `T` của `Outer`. |

Lưu ý: “owner type” ở Reflection diễn tả **cấu trúc kiểu thành viên**, không đồng nghĩa một đối tượng outer instance. Static nested class cũng có thể có owner type theo quan hệ khai báo, mặc dù không cần outer instance để khởi tạo.

## 2. Các giao diện Reflection và API cần dùng

Java cung cấp hệ thống `java.lang.reflect.Type`, bao gồm những dạng chủ yếu sau:

| Kiểu Reflection | Khi nào thường xuất hiện? |
| --- | --- |
| `Class<?>` | Class/interface thông thường, kiểu primitive, mảng class, hoặc một khai báo dùng raw type; không chứa tập đối số generic cụ thể. |
| `ParameterizedType` | Kiểu được tham số hóa như `List<String>`, `Outer<String>.Inner<Integer>`, hoặc kiểu lồng không generic nhưng có owner parameterized. |
| `TypeVariable<?>` | Tham số kiểu khai báo như `T`, `U` ở mức class hoặc method, chưa thay bằng đối số cụ thể. |
| `WildcardType` | Ký hiệu wildcard như `? extends Number` hoặc `? super Integer`. |
| `GenericArrayType` | Một số kiểu mảng có thành phần generic như `T[]`, khác với `String[].class`. |

Khi đối tượng thực sự là `ParameterizedType p`, ba phương thức mấu chốt:

- `p.getRawType()`: trả `Type` đại diện cho class/interface khai báo kiểu đang dùng. Với `Outer<String>.Inner<Integer>`, đó là `Outer.Inner.class`, **không phải** `Outer.class`.
- `p.getOwnerType()`: trả `Type` của kiểu chứa nó, chẳng hạn `Outer<String>`. Nếu là top-level type như `List<String>`, kết quả là `null`.
- `p.getActualTypeArguments()`: trả `Type[]` cho các đối số kiểu của **phần đang xét**. Với `Outer<String>.Inner<Integer>`, mảng chỉ có `Integer`; `String` thuộc owner, không nằm trong mảng này.

Trên một `Type` bất kỳ, **không được ép thẳng sang `ParameterizedType`**: `Field.getGenericType()` có thể trả `Class`, `TypeVariable` hoặc kiểu khác tùy khai báo. Dùng `instanceof ParameterizedType p` rồi mới đọc `getRawType()`, `getOwnerType()`, `getActualTypeArguments()`.

## 3. Ví dụ Java 17+ chạy được: quan sát raw/owner/arguments

Để tránh dựa vào tên binary có ký tự `$`, ví dụ in tên ngắn bằng hàm tiện ích `shortName`. Đặt toàn bộ mã trong **`GenericOwnerDemo.java`**:

~~~java
import java.lang.reflect.*;
import java.util.*;
import java.util.stream.Collectors;

class Outer<T> {
    class Inner<U> {}
    class Plain {}
    static class Nested<V> {}
}

public class GenericOwnerDemo {
    static class Holder {
        Outer<String>.Inner<Integer> full;
        Outer<String>.Plain plain;
        Outer.Inner rawInner;
        Outer<String> parameterizedOuter;
        Outer rawOuter;
        Outer.Nested<Long> nested;
        List<String> list;
    }

    static String shortName(Type type) {
        if (type == null) return "-";
        if (type instanceof Class<?> c) return c.getSimpleName();
        if (type instanceof ParameterizedType p) {
            String args = Arrays.stream(p.getActualTypeArguments())
                    .map(GenericOwnerDemo::shortName)
                    .collect(Collectors.joining(", "));
            return shortName(p.getRawType()) + "<" + args + ">";
        }
        return type.getTypeName();
    }

    static void inspect(String fieldName) throws NoSuchFieldException {
        Field field = Holder.class.getDeclaredField(fieldName);
        Type type = field.getGenericType();

        if (type instanceof ParameterizedType p) {
            String args = Arrays.stream(p.getActualTypeArguments())
                    .map(GenericOwnerDemo::shortName)
                    .collect(Collectors.joining(", ", "[", "]"));
            System.out.printf("%s: raw=%s; owner=%s; args=%s%n",
                    fieldName, shortName(p.getRawType()),
                    shortName(p.getOwnerType()), args);
        } else {
            System.out.printf("%s: Class=%s%n",
                    fieldName, shortName(type));
        }
    }

    public static void main(String[] args) throws Exception {
        inspect("full");
        inspect("plain");
        inspect("rawInner");
        inspect("parameterizedOuter");
        inspect("rawOuter");
        inspect("nested");
        inspect("list");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 GenericOwnerDemo.java
java GenericOwnerDemo
~~~

Stdout đã được kiểm chứng từ chương trình trên:

~~~text
full: raw=Inner; owner=Outer<String>; args=[Integer]
plain: raw=Plain; owner=Outer<String>; args=[]
rawInner: Class=Inner
parameterizedOuter: raw=Outer; owner=-; args=[String]
rawOuter: Class=Outer
nested: raw=Nested; owner=Outer; args=[Long]
list: raw=List; owner=-; args=[String]
~~~

**Phân tích:**

1. `full` được khai báo `Outer<String>.Inner<Integer>`. `getRawType()` chỉ ra `Inner.class`; `getOwnerType()` là một `ParameterizedType` cho `Outer<String>`; `getActualTypeArguments()` ở cấp `Inner` chỉ gồm `Integer.class`.
2. `plain` được khai báo `Outer<String>.Plain`. Tuy `Plain` **không khai báo tham số kiểu riêng**, Reflection vẫn dùng `ParameterizedType` để giữ owner `Outer<String>`; `getActualTypeArguments()` rỗng. Đây là trường hợp dễ gây nhầm lẫn nhất.
3. `rawInner` được khai báo `Outer.Inner` trong ngữ cảnh `Outer` raw, nên `getGenericType()` là một `Class<?>`. Không thể cast sang `ParameterizedType` để yêu cầu `getOwnerType()` hay args của khai báo field này.
4. `parameterizedOuter` là kiểu top-level `Outer<String>`; owner `null`. `rawOuter` chỉ là `Class<Outer>` ở mức Reflection vì khai báo dùng `Outer` không có đối số kiểu.
5. `nested` là `Outer.Nested<Long>`. `getOwnerType()` là `Class` cho `Outer` (được in là `Outer`), **không phải `Outer<String>`**, bởi `Nested` là `static` và không mang tham số `T` của outer.
6. `List<String>` là parameterized interface top-level từ thư viện Java, nên `getOwnerType() == null`. Nó khác về quan hệ thành viên so với `Inner` và `Nested`.

Hàm `shortName` chỉ phục vụ trình bày. Nó cố tình hiển thị args của `ParameterizedType` riêng và hiển thị owner ở cột khác; khi kiểu chứa nhiều lớp lồng phức tạp, nên xử lý cấu trúc `Type` đầy đủ thay vì dùng tên rút gọn để tái tạo cú pháp khai báo ban đầu.

## 4. Đọc đúng `getRawType()`: class nền và raw usage là hai chuyện

Giả sử:

~~~java
List<String> typed;
List raw;
~~~

Trong Reflection trên **hai field khai báo khác nhau**:

- `typed`: `Field.getGenericType()` trả `ParameterizedType`; `getRawType() == List.class`, và `getActualTypeArguments()[0] == String.class`.
- `raw`: `Field.getGenericType()` trả thẳng `List.class`. Không có mảng `String` hay đối số generic được khai báo trên field đó.

Vì vậy, không nên nói “`List<String>` là raw” chỉ bởi `getRawType()` của nó là `List.class`. Tên API nói tới **loại khai báo nền của parameterized type**.

`Class<?>` của một generic declaration vẫn có thể cung cấp thông tin **tham số kiểu hình thức**:

~~~java
Outer.class.getTypeParameters(); // chứa TypeVariable tên T
Outer.Inner.class.getTypeParameters(); // chứa TypeVariable tên U
~~~

Nhưng `TypeVariable T` hoặc `U` là “biến kiểu trong khai báo”, không phải **đối số cụ thể** `String`/`Integer` gắn vào một field. Để xem đối số thật được ghi trên field, đọc `Field.getGenericType()` rồi đi qua `ParameterizedType` và owner của nó.

**Raw type và nguy cơ:** Java giữ raw type cho khả năng tương thích thư viện cũ. Truyền dữ liệu qua raw collections có thể dẫn tới **unchecked warning** ở compile time và `ClassCastException` khi lấy lại dữ liệu sai kiểu. Trong code mới, nên khai báo type argument rõ ràng; nếu chỉ không biết kiểu thì dùng wildcard `<?>` khi phù hợp, ví dụ `List<?>` khác `List` raw.

## 5. Owner type không phải outer instance

Trong mã nguồn Java, **inner class không static** có liên hệ với một instance của outer class. Còn static nested class thì không cần instance đó:

~~~java
Outer<String> outer = new Outer<>();
Outer<String>.Inner<Integer> inner = outer.new Inner<>();
Outer.Nested<Long> nested = new Outer.Nested<>();
~~~

Đây là một **đoạn minh họa sử dụng `Outer` ở phần 3**, không phải file riêng có `main`. Với `inner`, cú pháp tạo instance cần `outer.new Inner<>()` vì `Inner` không static. Với `nested`, có thể gọi trực tiếp `new Outer.Nested<>()`.

Các phương thức Reflection liên quan nhưng khác mục đích:

| API | Nội dung |
| --- | --- |
| `ParameterizedType.getOwnerType()` | Owner **trong biểu diễn kiểu generic cụ thể**: ví dụ `Outer<String>` đối với `Outer<String>.Inner<Integer>`. |
| `Class.getDeclaringClass()` | Class khai báo một member class/interface, ví dụ `Outer.class` đối với `Outer.Inner.class`; **không mang `<String>`**. |
| `Class.getEnclosingClass()` | Class bao quanh theo cấu trúc nguồn/binary; còn áp dụng cho một số local/anonymous class. Không cung cấp đối số kiểu của outer. |
| `Class.isMemberClass()` | Kiểm tra kiểu có phải member class không; không nói kiểu đã được tham số hóa ra sao. |
| `Modifier.isStatic(nestedClass.getModifiers())` | Cho biết class lồng có static modifier; không thể suy trực tiếp từ việc `getOwnerType()` khác `null`. |

Một `Outer.Nested<Long>` vẫn có owner type ở metadata vì `Nested` là **member của `Outer`**, dù không có enclosing instance và không kế thừa `T`. Chủ thể “chứa khai báo kiểu” và chủ thể “instance vật lý để truy cập” phải phân biệt.

## 6. Inner generic và non-generic inner: vì sao args có thể rỗng?

Với:

~~~java
class Outer<T> {
    class Inner<U> {}
    class Plain {}
}
~~~

`Outer<String>.Inner<Integer>` có **hai mức ràng buộc kiểu**:

- `T = String` của `Outer<T>`, nằm trong owner type.
- `U = Integer` của `Inner<U>`, nằm trong `getActualTypeArguments()` của inner type.

`Outer<String>.Plain` chỉ có mức owner `T = String`. `Plain` không khai báo `<U>` nên `getActualTypeArguments()` của inner **rỗng** dù toàn bộ kiểu có chứa thông tin generic ở owner.

Một ứng dụng thường sai là chỉ kiểm tra `getActualTypeArguments().length == 0` rồi kết luận toàn bộ kiểu không generic. Cần kiểm tra `getOwnerType()` và đọc đệ quy nếu owner cũng là `ParameterizedType`.

Cách duyệt an toàn về mặt ý tưởng:

~~~java
static void walk(Type type) {
    if (type instanceof ParameterizedType p) {
        Type owner = p.getOwnerType();
        if (owner != null) walk(owner);
        for (Type argument : p.getActualTypeArguments()) walk(argument);
    } else if (type instanceof Class<?> c) {
        System.out.println(c.getName());
    }
}
~~~

Đây là **method minh họa**, cần đặt vào class có import `java.lang.reflect.*`. Nó chưa xử lý chi tiết các nhánh `WildcardType`, `TypeVariable`, `GenericArrayType` nên không phải generic type printer hoàn chỉnh. Mục tiêu là cho thấy phải duyệt **owner lẫn args**, không chỉ mảng args của inner.

## 7. Các dạng raw với class lồng và lỗi “partially raw”

JLS §4.8 nêu quy tắc: nếu outer generic bị sử dụng raw, inner member class không static khai báo trong nó cũng được xem là raw. Java không cho dùng **nửa raw/nửa tham số hóa** tại một chuỗi kiểu inner.

Với `Outer<T>` có `Inner<U>` ở ví dụ, hai khai báo sau **không hợp lệ và không biên dịch**:

~~~text
Outer.Inner<Integer> bad1;      // Sai: raw Outer nhưng cố truyền <Integer> cho Inner
Outer<String>.Inner bad2;       // Sai: Outer<String> nhưng dùng raw Inner
~~~

Hai khai báo đúng tương ứng là:

~~~java
Outer.Inner rawInner;
Outer<String>.Inner<Integer> parameterizedInner;
~~~

Đây là các **field declaration minh họa**: đặt bên trong class nếu muốn biên dịch. Dùng raw inner hợp lệ vì lý do tương thích legacy nhưng mất bớt kiểm tra generic; dạng được tham số hóa đầy đủ an toàn hơn khi viết code mới.

Với class lồng `static`, các quy tắc khác:

~~~java
Outer.Nested<Long> ok;  // hợp lệ: Nested static có V riêng
~~~

Bạn **không** viết `Outer<String>.Nested<Long>`, vì static nested type không phụ thuộc tham số `T` và không được chọn static member type từ một parameterized outer qua cú pháp đó. Hãy dùng `Outer.Nested<Long>`.

Sự phân biệt này rất quan trọng khi viết trình phân tích generic type cho framework: đừng tự ghép chuỗi `Outer<...>.Nested<...>` chỉ vì `getOwnerType()` khác null. Cần biết `Nested` có static modifier hay không và semantics của source syntax.

## 8. `getType()` khác `getGenericType()`

Khi đọc một field:

~~~java
Field field = Holder.class.getDeclaredField("full");
Class<?> erased = field.getType();
Type generic = field.getGenericType();
~~~

Đoạn này dùng `Holder` trong ví dụ phần 3, chưa phải chương trình độc lập.

- `getType()` trả `Class<?>` của kiểu field sau erasure, tức `Outer.Inner.class`. Nó không thể mang hai đối số `String` và `Integer`.
- `getGenericType()` đọc signature generic nếu có và trả `Type` phù hợp, với `full` là `ParameterizedType` có raw=`Outer.Inner.class`, owner=`Outer<String>` và args=`[Integer]`.
- Với field raw `Outer.Inner rawInner`, cả hai biểu diễn có thể là đối tượng `Class`; generic signature của cách dùng field này không khai báo binding cho `T/U`.

Tương tự, `Method.getGenericReturnType()`, `Method.getGenericParameterTypes()`, `Class.getGenericSuperclass()` và `Class.getGenericInterfaces()` giúp giữ cấu trúc generic **được ghi trong declaration**. Dùng các API `getGeneric...` khi nhiệm vụ là phân tích schema/type model; dùng `getType()`/`getReturnType()` khi chỉ cần runtime `Class` để gọi hoặc kiểm tra kiểu.

## 9. Generic metadata không có nghĩa mọi instance giữ type argument runtime

Java generics phần lớn dùng **type erasure**. Hai object được tạo qua:

~~~java
Outer<String> first = new Outer<>();
Outer<Integer> second = new Outer<>();
~~~

đều có cùng runtime `Class` là `Outer.class` (giả sử đặt đoạn trong method hợp lệ). Gọi `first.getClass()` không thể tự xác định `String` và `second.getClass()` không thể tự xác định `Integer`.

Tuy nhiên, field như `Holder.full` có **khai báo generic trong class file**, nên `getGenericType()` vẫn đọc được `Outer<String>.Inner<Integer>`. Hai câu hỏi khác nhau:

- “Một object bất kỳ được khởi tạo với đối số generic nào?”: thường không thể phục hồi chỉ bằng `getClass()` do erasure.
- “Source khai báo một field / method / superclass generic như thế nào?”: có thể đọc metadata signature qua Reflection nếu nó hiện diện.

Điều này giải thích tại sao một raw `Class<?>` không đủ làm nơi lưu `ownerType` và nhiều tầng actual type arguments cho mọi field.

## 10. Phân tích `Type` đúng cách trong framework

Khi xây mapper, serializer, dependency injection hoặc trình tạo tài liệu API, chọn chiến lược theo bản chất `Type`:

1. **Bắt đầu từ đúng vị trí khai báo:** dùng `Field.getGenericType()`, `Method.getGenericReturnType()` hoặc signature cấp superclass/interface, tùy loại metadata cần đọc.
2. **Phân nhánh theo `Type` thực tế:** nếu là `ParameterizedType`, đọc `rawType`, `ownerType` và `actualTypeArguments`. Nếu là `Class<?>`, có thể là kiểu không generic hoặc một raw use; xem chính declaration khi cần phân biệt.
3. **Giữ cả owner và inner args:** `Outer<String>.Inner<Integer>` không tương đương `Outer<Integer>.Inner<Integer>`; nếu cache key chỉ chứa raw `Inner.class` và `Integer`, bạn sẽ bỏ mất thông tin `String`.
4. **Kiểm tra static nested:** owner ở cấp Reflection có thể là một `Class` chưa tham số hóa. Không suy ra tất cả nested types đều cần outer instance hoặc phải có generic binding bên ngoài.
5. **Xử lý các nhánh còn lại:** `TypeVariable` có thể cần phân giải qua môi trường kiểu của class kế thừa; `WildcardType` có upper/lower bounds; `GenericArrayType` mang component type có thể generic. Đừng cast tất cả thành `Class`.
6. **Không nhầm metadata với conversion:** việc biết `T=String` từ field signature không tự động kiểm tra mọi giá trị runtime. Validation và mapping dữ liệu là tác vụ riêng.

Ví dụ lỗi thường gặp:

~~~java
Type type = field.getGenericType();
ParameterizedType p = (ParameterizedType) type; // Có thể ClassCastException!
~~~

Đoạn trên chỉ minh họa **lỗi cast không kiểm tra** (cần biến `field` trong scope). Với field `rawInner` hoặc `rawOuter`, `getGenericType()` trả `Class<?>` nên không thể cast thành `ParameterizedType`. Hãy dùng `instanceof` như chương trình phần 3.

Khi định danh một parameterized type, cần tính đến cả generic declaration, owner type và đối số kiểu. Các implementation `ParameterizedType` được quy định phải có `equals()` dựa vào khai báo và đối số tương ứng; trong cache, dùng `Type` đúng nghĩa thường an toàn hơn ghép tên class đơn giản. Dù vậy, nhiều framework vẫn cần chuẩn hóa/resolve type variables riêng tùy ngữ cảnh.

## 11. Những hiểu lầm cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Có `getRawType()` nghĩa là khai báo field đã bỏ hết generics.” | `ParameterizedType.getRawType()` chỉ trả khai báo nền của một parameterized type; args vẫn nằm trong `getActualTypeArguments()` và owner. |
| “`getActualTypeArguments()` của inner chứa luôn T của outer.” | T của outer nằm ở `getOwnerType()`; mảng args của inner chỉ mô tả phần inner. |
| “Nếu args rỗng, kiểu không có generic liên quan.” | `Outer<String>.Plain` có args rỗng nhưng owner `Outer<String>`. |
| “Owner type luôn là `Class<?>`.” | Owner có thể là `ParameterizedType` như `Outer<String>`, hoặc `Class<?>` như `Outer`, hoặc `null` với top-level. |
| “Owner khác null nghĩa là có outer instance.” | Static nested class có owner theo khai báo nhưng không cần outer instance. |
| “`Class.getDeclaringClass()` cho biết `Outer<String>`.” | Nó trả `Outer.class`, không phải binding `String`. |
| “Raw `Outer` có thể đi với `Inner<Integer>`.” | Java cấm loại partially raw đó đối với non-static member inner. |
| “Static nested `Outer.Nested<Long>` phụ thuộc T của `Outer<T>`.” | Static nested có tham số riêng V và không dùng type argument T của outer. |
| “Mọi `Type` đều là `ParameterizedType`.” | Raw usage có thể trả `Class`; wildcard/type variable/array generic còn có các dạng khác. |
| “Có thể đọc `T=String` từ `new Outer<String>().getClass()`.” | Erasure không giữ đối số kiểu của instance theo cách đó; phân tích declaration signature là chuyện khác. |

## 12. Câu hỏi tự kiểm tra

1. Trong `Outer<String>.Inner<Integer>`, `getRawType()` đại diện class nào? `getOwnerType()` chứa kiểu gì? Mảng `getActualTypeArguments()` có bao nhiêu phần tử?
2. Tại sao `Outer<String>.Plain` vẫn xuất hiện như `ParameterizedType` dù `Plain` không có `<U>`?
3. Một field khai báo `Outer.Inner rawInner` sẽ cho `Class` hay `ParameterizedType` khi gọi `getGenericType()`? Có thể cast kết quả sang `ParameterizedType` không?
4. Owner của `Outer.Nested<Long>` có thể khác `null` không? Vì sao điều đó không chứng minh `Nested` cần outer instance?
5. Hai khai báo `Outer.Inner<Integer>` và `Outer<String>.Inner` có hợp lệ không? Quy tắc JLS nào khiến chúng là “partially raw”?
6. Nếu một mapper chỉ lưu `getRawType()` của `Outer<String>.Inner<Integer>`, nó bỏ mất thông tin nào cần thiết để phân biệt các field generic?

**Điểm nhớ chính:** Với kiểu lồng có generic, hãy xem **ba phần riêng**: `getRawType()` chỉ tới khai báo nền, `getOwnerType()` giữ cấu trúc bao ngoài và `getActualTypeArguments()` mô tả đối số của chính phần đang xét. Raw usage lại là chuyện **bỏ type argument tại nơi dùng kiểu**, không đồng nghĩa với việc gọi `getRawType()`.

## Tài liệu chuẩn

- [Java SE 17 — `ParameterizedType` (raw, owner, actual arguments)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 17 — `Field.getGenericType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#getGenericType())
- [JLS 17 §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5)
- [JLS 17 §4.8 — Raw Types và quy tắc inner class](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8)
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3)
