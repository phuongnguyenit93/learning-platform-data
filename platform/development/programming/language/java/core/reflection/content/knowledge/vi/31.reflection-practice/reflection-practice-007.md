# Phân giải generic của một lớp con qua nhiều tầng kế thừa trong Java

## 1. Bài toán thực tế

Trong Java, generic phần lớn bị **type erasure** khi chạy. Tuy nhiên, thông tin về **kiểu cha được khai báo** thường còn trong class file và có thể đọc qua reflection. Nhờ đó, một framework có thể xác định tham số kiểu cụ thể mà lớp con đã cung cấp qua nhiều tầng kế thừa, chẳng hạn để xây serializer, repository, mapper hoặc bộ đăng ký handler.

Xét chuỗi:

```java
class Base<T> {}
class Middle<U> extends Base<java.util.List<U>> {}
class End extends Middle<String> {}
```

Điều muốn tìm là: khi nhìn từ `End`, `T` của `Base<T>` thực sự là `List<String>`. Không thể chỉ xem một lớp cha rồi kết luận, vì `Middle` truyền `List<U>`, còn `U` mới được `End` cố định thành `String`.

Kết quả mong muốn là **phân giải có ngữ cảnh**:

```text
Base.T = java.util.List<java.lang.String>
```

Phải giữ đúng danh tính của từng `TypeVariable` và lần theo liên kết qua các cấp. Chỉ tìm tên biến `T`/`U` hoặc dùng `getSuperclass()` là chưa đủ.

## 2. Cần đọc API nào?

| API | Giá trị nhận được | Vai trò |
| --- | --- | --- |
| `Class.getSuperclass()` | `Class<?>` của lớp cha trực tiếp | Cho biết quan hệ raw, **không chứa** đối số generic như `String` |
| `Class.getGenericSuperclass()` | `Type` mô tả kiểu cha đã khai báo | Có thể là `ParameterizedType` nếu lớp con khai báo đối số generic |
| `Class.getTypeParameters()` | `TypeVariable<?>[]` | Liệt kê biến kiểu mà chính lớp đó khai báo, đúng thứ tự |
| `ParameterizedType.getRawType()` | `Type` (thường là `Class<?>`) | Xác định lớp generic gốc như `Middle.class` |
| `ParameterizedType.getActualTypeArguments()` | `Type[]` | Các đối số như `String.class`, `List<U>`, `U[]` |
| `TypeVariable.getGenericDeclaration()` | `GenericDeclaration` | Phân biệt hai biến cùng tên nhưng từ hai khai báo khác nhau |
| `TypeVariable.getBounds()` | `Type[]` | Ràng buộc trên của biến chưa được cố định, **không phải** đối số đã truyền |

Những đối tượng có thể gặp khi duyệt `Type`:

- `Class<?>`: kiểu cụ thể, primitive hoặc array không có biến generic cần giải tiếp.
- `ParameterizedType`: kiểu có đối số, như `List<U>` hoặc `Map<String, ? extends U>`.
- `TypeVariable<?>`: biến kiểu như `T`, `U`, `Z`.
- `GenericArrayType`: kiểu mảng mà thành phần là kiểu generic, ví dụ `X[]`.
- `WildcardType`: `?`, `? extends U`, `? super U`.

**Sai lầm thường gặp:** `Base.class.getTypeParameters()[0]` sẽ vẫn là biến `T`. Nó không tự biết một lớp con nào đang được xét. Muốn nhận `List<String>`, phải xây **bảng thay thế từ lớp con cụ thể lên lớp cha**.

## 3. Cách lần theo nhiều tầng bằng bảng ánh xạ biến kiểu

Giả sử:

```java
class Three<A, B, C> {}
class Two<X, Y> extends Three<
        java.util.List<Y>,
        X[],
        java.util.Map<String, ? extends Y>> {}
class One<Z> extends Two<String, Z> {}
class Concrete extends One<Integer> {}
```

Các đối số khi đi ngược từ `Concrete` lên `Three`:

| Cạnh kế thừa | Ánh xạ theo khai báo kiểu cha |
| --- | --- |
| `Concrete extends One<Integer>` | `One.Z → Integer` |
| `One<Z> extends Two<String,Z>` | `Two.X → String`, `Two.Y → One.Z` |
| `Two<X,Y> extends Three<List<Y>,X[],Map<String,? extends Y>>` | `Three.A → List<Two.Y>`, `Three.B → Two.X[]`, `Three.C → Map<String, ? extends Two.Y>` |

Từ đó áp dụng **đệ quy**:

- `Three.A → List<Two.Y> → List<One.Z> → List<Integer>`.
- `Three.B → Two.X[] → String[]`.
- `Three.C → Map<String,? extends Two.Y> → Map<String,? extends One.Z> → Map<String,? extends Integer>`.

Từng tên biến chỉ là ký hiệu mô tả. Trong code, khóa bảng ánh xạ phải là **đối tượng `TypeVariable<?>`**, không phải chuỗi `"X"` hay `"Z"`. Vì hai lớp bất kỳ có thể đều khai báo `T`, một `Map<String,Type>` có thể vô tình ghi đè ánh xạ của lớp khác.

### Thuật toán cho chuỗi kế thừa lớp đơn

1. Bắt đầu với `Class<?> leaf` là lớp con đang khảo sát.
2. Lấy `leaf.getGenericSuperclass()`.
3. Nếu là `ParameterizedType`, lấy raw class của cha cùng mảng type arguments; ghép từng `rawClass.getTypeParameters()[i]` với `getActualTypeArguments()[i]` trong bảng ánh xạ.
4. Nếu là `Class<?>`, đó là cạnh không tham số hóa cần đi tiếp; **không tự suy ra một đối số kiểu cụ thể**.
5. Tiếp tục lên các lớp cha cho tới `Object` hoặc hết cha.
6. Khi cần biết một biến kiểu của lớp tổ tiên, **thay thế đệ quy** qua bảng vừa thu thập. Với các kiểu phức hợp, phải đi vào `ParameterizedType`, `GenericArrayType` và `WildcardType` thay vì dừng ở tầng ngoài.

Bảng ở ví dụ có thể tạm giữ `Three.A → List<Two.Y>`. Không cần “đóng băng” kết quả ngay lúc gặp `Three`; đến cuối quá trình mới giải mọi liên kết sẽ cho kết quả đúng sau khi các biến ở cấp thấp hơn đã được ghi nhận.

## 4. Ví dụ Java 17+ hoàn chỉnh: giải chữ ký qua ba cấp

Ví dụ sau cố tình **trả về chuỗi biểu diễn kiểu đã phân giải**, thay vì tạo các triển khai tự viết của `ParameterizedType`/`WildcardType`. Cách này phù hợp khi mục tiêu là chẩn đoán và học thuật toán. Nếu chương trình cần một đối tượng `Type` đã thay thế thực sự cho framework, cần thêm phần hiện thực `Type` hoặc dùng thư viện xử lý type token có hợp đồng rõ ràng.

Lưu tệp `GenericHierarchyResolverDemo.java`:

```java
import java.lang.reflect.*;
import java.util.*;
import java.util.stream.Collectors;

public class GenericHierarchyResolverDemo {
    static class Three<A, B, C> {}

    static class Two<X, Y> extends Three<
            List<Y>, X[], Map<String, ? extends Y>> {}

    static class One<Z> extends Two<String, Z> {}

    static final class Concrete extends One<Integer> {}

    // Từ lớp chưa cố định R: không được tự coi bound Number là kiểu thực tế.
    static class Open<R extends Number> extends One<R> {}

    static Map<TypeVariable<?>, Type> collectBindings(Class<?> leaf) {
        Map<TypeVariable<?>, Type> bindings = new LinkedHashMap<>();
        Class<?> current = leaf;

        while (current != null && current != Object.class) {
            Type genericParent = current.getGenericSuperclass();

            if (genericParent instanceof ParameterizedType parent) {
                Type raw = parent.getRawType();
                if (!(raw instanceof Class<?> parentClass)) {
                    throw new IllegalArgumentException(
                            "Unsupported raw type: " + raw);
                }

                TypeVariable<?>[] variables =
                        parentClass.getTypeParameters();
                Type[] arguments = parent.getActualTypeArguments();

                if (variables.length != arguments.length) {
                    throw new IllegalStateException(
                            "Mismatched generic signature");
                }

                for (int i = 0; i < variables.length; i++) {
                    bindings.put(variables[i], arguments[i]);
                }
                current = parentClass;
            } else if (genericParent instanceof Class<?> rawParent) {
                current = rawParent;
            } else {
                break;
            }
        }
        return bindings;
    }

    static String describe(Type type, Map<TypeVariable<?>, Type> bindings) {
        return describe(type, bindings, new HashSet<>());
    }

    static String describe(Type type, Map<TypeVariable<?>, Type> bindings,
            Set<TypeVariable<?>> visiting) {

        if (type instanceof TypeVariable<?> variable) {
            if (!visiting.add(variable)) {
                return variable.getName();
            }
            try {
                Type replacement = bindings.get(variable);
                if (replacement == null || replacement.equals(variable)) {
                    return variable.getName();
                }
                return describe(replacement, bindings, visiting);
            } finally {
                visiting.remove(variable);
            }
        }

        if (type instanceof ParameterizedType parameterized) {
            String arguments = Arrays.stream(
                    parameterized.getActualTypeArguments())
                    .map(argument -> describe(
                            argument, bindings, visiting))
                    .collect(Collectors.joining(", "));
            return parameterized.getRawType().getTypeName()
                    + "<" + arguments + ">";
        }

        if (type instanceof GenericArrayType genericArray) {
            return describe(
                    genericArray.getGenericComponentType(),
                    bindings, visiting) + "[]";
        }

        if (type instanceof WildcardType wildcard) {
            Type[] lower = wildcard.getLowerBounds();
            if (lower.length > 0) {
                return "? super " + Arrays.stream(lower)
                        .map(bound -> describe(
                                bound, bindings, visiting))
                        .collect(Collectors.joining(" & "));
            }

            Type[] upper = wildcard.getUpperBounds();
            if (upper.length == 1 && upper[0] == Object.class) {
                return "?";
            }
            return "? extends " + Arrays.stream(upper)
                    .map(bound -> describe(bound, bindings, visiting))
                    .collect(Collectors.joining(" & "));
        }

        return type.getTypeName();
    }

    static String resolveParameter(
            Class<?> ancestor, int index,
            Map<TypeVariable<?>, Type> bindings) {
        TypeVariable<?>[] variables = ancestor.getTypeParameters();
        if (index < 0 || index >= variables.length) {
            throw new IndexOutOfBoundsException(index);
        }
        return describe(variables[index], bindings);
    }

    static void requireEquals(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected: " + expected + "; actual: " + actual);
        }
    }

    public static void main(String[] args) {
        Map<TypeVariable<?>, Type> concrete =
                collectBindings(Concrete.class);

        String a = resolveParameter(Three.class, 0, concrete);
        String b = resolveParameter(Three.class, 1, concrete);
        String c = resolveParameter(Three.class, 2, concrete);
        String z = resolveParameter(One.class, 0, concrete);

        requireEquals("java.util.List<java.lang.Integer>", a);
        requireEquals("java.lang.String[]", b);
        requireEquals(
                "java.util.Map<java.lang.String, ? extends java.lang.Integer>",
                c);
        requireEquals("java.lang.Integer", z);

        System.out.println("Concrete.Three.A=" + a);
        System.out.println("Concrete.Three.B=" + b);
        System.out.println("Concrete.Three.C=" + c);
        System.out.println("Concrete.One.Z=" + z);

        Map<TypeVariable<?>, Type> open = collectBindings(Open.class);
        String unresolved = resolveParameter(Three.class, 0, open);
        requireEquals("java.util.List<R>", unresolved);
        System.out.println("Open.Three.A=" + unresolved);

        System.out.println("rawParent=" +
                Concrete.class.getSuperclass().getSimpleName());
        System.out.println("checks=PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 GenericHierarchyResolverDemo.java
java GenericHierarchyResolverDemo
```

Stdout:

```text
Concrete.Three.A=java.util.List<java.lang.Integer>
Concrete.Three.B=java.lang.String[]
Concrete.Three.C=java.util.Map<java.lang.String, ? extends java.lang.Integer>
Concrete.One.Z=java.lang.Integer
Open.Three.A=java.util.List<R>
rawParent=One
checks=PASS
```

### Đọc ví dụ theo từng bước

- `Concrete` kế thừa `One<Integer>`: `getGenericSuperclass()` là `ParameterizedType`, từ đó thu được `One.Z → Integer`.
- `One<Z>` kế thừa `Two<String,Z>`: thu được `Two.X → String` và `Two.Y → One.Z`.
- `Two<X,Y>` kế thừa `Three<List<Y>,X[],Map<String,? extends Y>>`: ghi ánh xạ cho `Three.A`, `Three.B`, `Three.C`.
- Khi in `Three.A`, hàm `describe` đi từ `TypeVariable` vào `ParameterizedType` rồi theo hai biến `Y` và `Z`; kết quả là `List<Integer>`.
- `Three.B` dùng `GenericArrayType` (mảng có thành phần là biến kiểu `X`), sau thay thế trở thành `String[]`.
- `Three.C` buộc resolver đi vào một `ParameterizedType` chứa `WildcardType`; nếu chỉ gọi `Type.getTypeName()` của cấu trúc gốc, kết quả vẫn là `? extends Y` và **chưa phân giải hoàn toàn**.
- `Open<R extends Number>` cho ra `List<R>` vì `R` **chưa được cố định** bởi lớp con cụ thể. Không được tự thay `R` bằng `Number`: bound chỉ là giới hạn kiểu, không phải đối số thực tế.
- `requireEquals` làm chương trình **tự kiểm chứng** các kết quả, không chỉ hiển thị chuỗi mô tả.

Hàm `collectBindings` được thiết kế cho **chuỗi superclass**. Nó không tự đi vào `getGenericInterfaces()`, không đưa owner type của lớp lồng non-static vào chuỗi in và không tái tạo một cây đối tượng `Type` có thể dùng thay thế trong mọi framework. Những giới hạn này phải được xử lý trước khi dùng như một thư viện generic resolution toàn diện.

## 5. Vì sao `TypeVariable` phải được phân biệt theo nơi khai báo?

Ví dụ:

```java
class Parent<T> {}
class Child<T> extends Parent<T> {}
class Fixed extends Child<String> {}
```

`Parent.T` và `Child.T` đều có tên `"T"`, nhưng là **hai biến kiểu khác nhau** vì khai báo tại hai class khác nhau. Ánh xạ đúng là:

```text
Parent.T -> Child.T
Child.T  -> java.lang.String
Kết quả Parent.T = java.lang.String
```

Nếu dùng `Map<String, Type>` với key `"T"`, bước thứ hai có thể ghi đè bước thứ nhất và làm mất cấu trúc liên kết; với nhánh phức tạp, kết quả dễ sai hoặc gặp vòng lặp giả. Dùng `Map<TypeVariable<?>,Type>` bảo toàn danh tính và bối cảnh khai báo. Có thể kiểm tra `variable.getGenericDeclaration()` để biết biến thuộc class, interface, method hay constructor nào.

Hàm `describe` còn có `Set<TypeVariable<?>> visiting` nhằm tránh lặp không kết thúc khi gặp ánh xạ tạo vòng. Đây là biện pháp phòng vệ của trình phân giải, **không** có nghĩa generic bất kỳ đều được phép tạo một lớp cha vòng lặp trong Java.

## 6. Generic array, wildcard, raw type và kiểu chưa biết

### Generic array và wildcard

Kiểu `X[]` trong khai báo `Two<X,Y>` thường xuất hiện dưới dạng `GenericArrayType` vì thành phần `X` là `TypeVariable`. Một generic resolver không đọc nhánh này sẽ trả nguyên `X[]` thay vì `String[]`.

Tương tự, `Map<String, ? extends Y>` là `ParameterizedType` chứa `WildcardType`. Đối số `? extends Y` phải được giải tiếp để ra `? extends Integer`. Với `? super Y`, cần xử lý `getLowerBounds()`; với wildcard không giới hạn, `getUpperBounds()` thường là `Object.class` và biểu diễn là `?`.

**Không lẫn bound và type argument**: `class Open<R extends Number>` không có nghĩa `R` là `Number`. Một instance của `Open<Long>` là hợp lệ, vì thế `R` chỉ được thay bằng `Long` khi có một lớp con/đường kế thừa thực sự cung cấp đối số tương ứng.

### Raw type làm mất thông tin

```java
class Box<T> {}
class Raw extends Box {} // Raw type, không cung cấp T cụ thể.
```

Đây là đoạn minh họa. `Raw.class.getGenericSuperclass()` có thể là `Class<?>` dạng raw thay vì `ParameterizedType`; không có dữ liệu để kết luận `T` là `String` hay `Integer`. Với framework nghiêm ngặt, nên **báo unresolved hoặc từ chối**, không tự đoán `Object` là đối số cụ thể chỉ vì type erasure hoặc bound mặc định là `Object`.

### Runtime object không khôi phục `List<String>` tùy ý

`new ArrayList<String>().getClass()` chỉ cho lớp runtime `ArrayList`; cú pháp `new ArrayList<String>()` không tạo một subclass mang `String` trong `generic superclass` của `ArrayList`. Reflection có thể giải đối số từ **khai báo kiểu cha** trên một lớp con có chữ ký ghi trong class file; nó không thể đọc mọi type argument từ một object thông thường.

Một cách khác để mang thông tin generic là **anonymous subclass/type token**, ví dụ `new TypeReference<List<String>>() {}`, nơi superclass được tham số hóa trong class file. Type token là một kỹ thuật khác, không đồng nghĩa với việc mọi object đều giữ generic khi chạy.

## 7. Interface, owner type và những giới hạn cần mở rộng

Java cho phép một class **kế thừa một superclass** nhưng **implements nhiều interface**. Nếu mục tiêu là generic được khai báo bởi interface, cần mở rộng sang `Class.getGenericInterfaces()` và duyệt đồ thị interface/superclass.

Ví dụ:

```java
interface Handler<E> {}
interface NamedHandler<X> extends Handler<java.util.List<X>> {}
class NamedStringHandler implements NamedHandler<String> {}
```

Muốn giải `Handler.E` trong ngữ cảnh `NamedStringHandler`, phải đi qua cạnh interface:

```text
NamedStringHandler
  -> NamedHandler<String>
  -> Handler<List<X>>
  -> Handler.E = List<String>
```

**Không** thể dùng duy nhất `getGenericSuperclass()` để tìm các cạnh này. Với resolver tổng quát, mỗi nhánh traversal nên mang theo **môi trường ánh xạ riêng**; tránh dùng một map toàn cục để trộn các đường khác nhau. Cần tránh thăm lặp, kiểm tra quan hệ `target.isAssignableFrom(candidate)` thích hợp và giải quyết đường kế thừa tới đúng khai báo.

Ngoài ra, một non-static member class có thể sử dụng biến kiểu từ lớp ngoài qua **owner type** (`ParameterizedType.getOwnerType()`). Nếu mô tả kết quả phải đầy đủ, hãy giải cả owner và biểu diễn tên nested class chính xác. Ví dụ code chạy ở mục 4 **không tuyên bố hỗ trợ trường hợp này**.

Một `ParameterizedType`/`TypeVariable` được trả về từ metadata cũng có thể dẫn tới `TypeNotPresentException` hay `MalformedParameterizedTypeException` nếu chữ ký tham chiếu tới kiểu thiếu hoặc metadata lỗi. Thư viện production nên xử lý rõ ràng, kèm class/module/loader đang phân tích để chẩn đoán.

## 8. Những lỗi phổ biến

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ dùng `getSuperclass()` | Mất type arguments của cạnh cha | Dùng `getGenericSuperclass()` |
| Chỉ xét một cấp | Lấy `List<U>` thay vì `List<String>` | Theo bảng thế biến tới lớp cuối |
| Thay biến bằng tên chuỗi | Hai class đều có thể khai báo `T` | Dùng khóa `TypeVariable<?>` |
| Cast mọi `Type` sang `ParameterizedType` | Cha raw, tham số concrete, wildcard, array không phải dạng đó | Kiểm tra `instanceof` theo từng nhánh |
| Chỉ thay `TypeVariable` ở tầng ngoài | `List<U>`/`Map<?,U>` còn giữ biến bên trong | Duyệt đệ quy `ParameterizedType`, wildcard, array |
| Dùng `getBounds()` làm kiểu thực tế của biến chưa gắn | Bound không phải actual argument | Giữ trạng thái unresolved |
| Mặc định raw type là `Object` chính xác | Không có thông tin type argument thực | Báo thiếu thông tin; quyết định fallback theo contract |
| Trộn superclass với interface mà không duyệt interface | Mất đường tới generic interface | Duyệt `getGenericInterfaces()` theo môi trường từng nhánh |
| Coi `new List<String>()`-style object giữ type arguments | Type erasure không cho suy từ object thông thường | Dựa vào signature khai báo hoặc type token |
| Không kiểm soát class loader | Tên class giống nhau từ hai loader không nhất thiết cùng kiểu | So `Class<?>`/`Type` thực, ghi bối cảnh loader khi debug |

## 9. Bài tập tự luyện

**Bài 1.** `class A<T> {}`; `class B<U> extends A<U[]> {}`; `class C extends B<Long> {}`. Giải `A.T` trong ngữ cảnh `C`.

**Đáp án:** `java.lang.Long[]`. Biến `U` của `B` được cố định thành `Long`, nên `U[]` thành `Long[]`.

**Bài 2.** `class A<T> {}`; `class B<T> extends A<List<T>> {}`; `class C extends B<String> {}`. Có được dùng `Map<String,Type>` chứa `"T"` không?

**Đáp án:** Không an toàn. `A.T` và `B.T` khác nhau dù tên giống. Dùng `TypeVariable<?>` làm khóa.

**Bài 3.** `class A<T extends Number> {}`; `class B<U extends Number> extends A<U> {}`. `A.T` có tự giải thành `Number` không?

**Đáp án:** Không. Trong `B` chưa cố định `U`; kết quả vẫn là biến `U` với bound `Number`.

**Bài 4.** Lớp triển khai `interface Handler<T>` bằng một chuỗi interface trung gian có thể giải bằng chỉ `getGenericSuperclass()` không?

**Đáp án:** Không. Cần duyệt `getGenericInterfaces()` và ánh xạ biến theo các cạnh interface.

**Bài 5.** Sau khi giải `List<? extends U>` với `U=Integer`, có thể bỏ wildcard và xem là `List<Integer>` không?

**Đáp án:** Không. `List<? extends Integer>` và `List<Integer>` không phải cùng một kiểu generic; resolver phải giữ wildcard.

**Ghi nhớ:** Muốn phân giải generic qua nhiều tầng, hãy đi theo **đường kế thừa đúng**, tạo bản đồ **TypeVariable theo khai báo → Type argument**, rồi thay thế **đệ quy cả kiểu lồng, mảng generic và wildcard**. Chỉ kết luận một kiểu cụ thể khi chuỗi khai báo thực sự cung cấp đủ thông tin.

Tham khảo API Java 17: [`Class.getGenericSuperclass()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getGenericSuperclass()), [`ParameterizedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html), [`TypeVariable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html), [`GenericArrayType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html), [`WildcardType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/WildcardType.html).