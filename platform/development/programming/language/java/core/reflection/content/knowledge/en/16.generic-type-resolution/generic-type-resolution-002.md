# Thông tin kiểu từ lớp con có superclass được tham số hóa

Khi một lớp kế thừa từ superclass generic và cung cấp tham số kiểu cụ thể, Java có thể lưu **thông tin kiểu của quan hệ kế thừa** trong metadata class file. Reflection cho phép đọc thông tin này bằng `Class.getGenericSuperclass()` và phân tích đối tượng `java.lang.reflect.Type`. Nhờ đó, một framework có thể biết `StringRepository extends Repository<String>` đã khai báo `String` làm đối số kiểu cho `Repository<T>`, dù thông tin đối số kiểu thường bị xóa khỏi kiểu đối tượng ở runtime bởi **type erasure**.

Tuy nhiên, kết quả không phải lúc nào cũng là `Class<?>`: nó có thể là `ParameterizedType`, chứa tiếp `TypeVariable`, `WildcardType` hoặc `GenericArrayType`. Nếu có nhiều cấp kế thừa, Reflection **không tự thay thế** mọi biến kiểu từ các lớp trung gian; muốn suy ra kiểu cuối cùng phải lần theo chuỗi kế thừa và thực hiện ánh xạ biến kiểu.

## 1. Bài toán: đọc lại đối số kiểu trên quan hệ extends

Xét hai khai báo:

```java
class Repository<T> {
}

class StringRepository extends Repository<String> {
}
```

Ở mã nguồn, `StringRepository` đã cố định đối số `T` của superclass thành `String`. Vì vậy ta muốn biết:

- Superclass thô (raw superclass) của `StringRepository` là gì?
- Quan hệ kế thừa có chứa đối số kiểu nào?
- Đối số đó đã là class cụ thể, hay vẫn là biến kiểu?
- Có thể suy ra kiểu ở tầng `Repository<T>` nếu có một vài lớp trung gian không?

Hai API `Class` có mục đích khác nhau:

```java
Class<?> raw = StringRepository.class.getSuperclass();
java.lang.reflect.Type generic =
        StringRepository.class.getGenericSuperclass();
```

Kết quả có ý nghĩa:

- `getSuperclass()` trả `Repository.class`, là đối tượng `Class<?>` cho superclass trực tiếp; **không giữ đối số `String`**.
- `getGenericSuperclass()` trả một `Type` đại diện cho `Repository<String>`; trong trường hợp này nó là `ParameterizedType`.
- Hai cách đọc chỉ xét **superclass trực tiếp**, không tự tìm kiểu generic sâu hơn mọi cấp trong cây kế thừa.
- Nếu class là `Object.class` hoặc interface không có superclass tương ứng, `getGenericSuperclass()` trả `null`. Nếu superclass được dùng ở dạng raw, kết quả có thể là một `Class<?>` thay vì `ParameterizedType`.

Thông tin generic tồn tại trên **declaration** như quan hệ `extends Repository<String>`. Điều này khác việc hỏi một đối tượng `new Repository<String>()` ở runtime xem đối số `T` của nó là gì: với class generic thông thường, `new Repository<String>().getClass()` vẫn chỉ trả `Repository.class`, và không có đối số `String` trong đối tượng `Class` đó.

## 2. Những nhánh cần phân biệt của Type

`java.lang.reflect.Type` là giao diện chung cho metadata kiểu. Khi đọc `getGenericSuperclass()`, kết quả cần được kiểm tra bằng `instanceof` rồi mới ép kiểu.

| Dạng `Type` | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `Class<?>` | `Object`, `String`, superclass raw | Kiểu được biểu diễn trực tiếp bằng đối tượng `Class`, không kèm đối số tham số hóa ở chính vị trí này |
| `ParameterizedType` | `Repository<String>`, `List<Integer>` | Raw type cộng các đối số kiểu, và có thể cả owner type |
| `TypeVariable<?>` | `T` trong `Repository<T>` hoặc `U` từ lớp trung gian | Tham chiếu tới biến kiểu do class, interface hoặc method/constructor khai báo |
| `WildcardType` | `? extends Number`, `? super Integer` | Đối số kiểu wildcard với giới hạn trên/dưới |
| `GenericArrayType` | `U[]` trong một khai báo generic | Kiểu mảng mà component là kiểu generic không thể biểu diễn bằng `Class<?>` thông thường |

Một `ParameterizedType` cung cấp:

```java
ParameterizedType p = (ParameterizedType) generic;

Type rawType = p.getRawType();
Type[] arguments = p.getActualTypeArguments();
Type owner = p.getOwnerType();
```

Đây là đoạn minh họa khi biến `generic` đã được xác định là `ParameterizedType` và đã import `java.lang.reflect.*`.

- `getRawType()` thường là một `Class<?>`, chẳng hạn `Repository.class`.
- `getActualTypeArguments()` trả đối số kiểu của quan hệ tham số hóa, ví dụ `String.class` cho `Repository<String>`. Đối số có thể là các dạng `Type` lồng nhau, nên **không được ép mọi phần tử thành `Class<?>`**.
- `getOwnerType()` có thể quan trọng cho kiểu thành viên nằm bên trong kiểu bao ngoài; các ví dụ top-level/nested static thông thường không cần dựa vào owner.
- Số đối số của một `ParameterizedType` có thể bằng 0 trong một số cấu trúc owner/nested type; không nên giả định mọi `ParameterizedType` đều có đúng một đối số.

Với `TypeVariable<?> v`, `v.getName()` cho biết tên biến; `v.getBounds()` cho biết upper bounds khai báo. Nhưng **bounds không phải giá trị kiểu cụ thể được cung cấp bởi lớp con**. Ví dụ `T extends Number` chỉ nêu ràng buộc, không cho phép tự kết luận `T = Integer`.

## 3. Chương trình Java 17+ hoàn chỉnh

Tạo file `GenericSuperclassDemo.java` như sau:

```java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class GenericSuperclassDemo {
    static class Box<T> {
    }

    static class StringBox extends Box<String> {
    }

    static class Layer<U> extends Box<List<U>> {
    }

    static class IntegerLayer extends Layer<Integer> {
    }

    @SuppressWarnings("rawtypes")
    static class RawBox extends Box {
    }

    static class ArrayBox extends Box<String[]> {
    }

    static class GenericArrayBox<U> extends Box<U[]> {
    }

    static class NumberListBox extends Box<List<? extends Number>> {
    }

    static class Plain {
    }

    static String kind(Type type) {
        if (type instanceof Class<?>) {
            return "Class";
        }
        if (type instanceof ParameterizedType) {
            return "ParameterizedType";
        }
        if (type instanceof TypeVariable<?>) {
            return "TypeVariable";
        }
        if (type instanceof WildcardType) {
            return "WildcardType";
        }
        if (type instanceof GenericArrayType) {
            return "GenericArrayType";
        }
        return "Other";
    }

    static String render(Type type) {
        if (type == null) {
            return "null";
        }
        if (type instanceof Class<?> c) {
            if (c.isArray()) {
                return render(c.getComponentType()) + "[]";
            }
            return c.getSimpleName();
        }
        if (type instanceof ParameterizedType p) {
            String args = Arrays.stream(p.getActualTypeArguments())
                    .map(GenericSuperclassDemo::render)
                    .collect(Collectors.joining(", "));
            return render(p.getRawType()) + "<" + args + ">";
        }
        if (type instanceof TypeVariable<?> variable) {
            return variable.getName();
        }
        if (type instanceof GenericArrayType array) {
            return render(array.getGenericComponentType()) + "[]";
        }
        if (type instanceof WildcardType wildcard) {
            if (wildcard.getLowerBounds().length > 0) {
                return "? super " + render(wildcard.getLowerBounds()[0]);
            }
            Type[] upper = wildcard.getUpperBounds();
            if (upper.length == 1 && upper[0] == Object.class) {
                return "?";
            }
            return "? extends " + render(upper[0]);
        }
        return type.getTypeName();
    }

    static void inspect(Class<?> child) {
        Class<?> rawSuperclass = child.getSuperclass();
        Type genericSuperclass = child.getGenericSuperclass();

        String rawName = rawSuperclass == null
                ? "null" : rawSuperclass.getSimpleName();

        System.out.println(child.getSimpleName() + ": raw=" + rawName
                + ", generic=" + render(genericSuperclass));

        if (genericSuperclass instanceof ParameterizedType p) {
            Type[] args = p.getActualTypeArguments();
            for (int i = 0; i < args.length; i++) {
                System.out.println("  arg[" + i + "]="
                        + render(args[i]) + " (" + kind(args[i]) + ")");
            }
        }
    }

    public static void main(String[] args) {
        inspect(StringBox.class);
        inspect(Layer.class);
        inspect(IntegerLayer.class);
        inspect(RawBox.class);
        inspect(ArrayBox.class);
        inspect(GenericArrayBox.class);
        inspect(NumberListBox.class);
        inspect(Plain.class);
        inspect(Object.class);

        ParameterizedType first = (ParameterizedType)
                IntegerLayer.class.getGenericSuperclass();
        Type supplied = first.getActualTypeArguments()[0];

        ParameterizedType second = (ParameterizedType)
                Layer.class.getGenericSuperclass();
        ParameterizedType list = (ParameterizedType)
                second.getActualTypeArguments()[0];
        TypeVariable<?> variable = (TypeVariable<?>)
                list.getActualTypeArguments()[0];

        System.out.println("mapping: " + variable.getName()
                + " -> " + render(supplied));
        System.out.println("resolved Box argument: List<"
                + render(supplied) + ">");
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac GenericSuperclassDemo.java
java GenericSuperclassDemo
```

Kết quả stdout:

```text
StringBox: raw=Box, generic=Box<String>
  arg[0]=String (Class)
Layer: raw=Box, generic=Box<List<U>>
  arg[0]=List<U> (ParameterizedType)
IntegerLayer: raw=Layer, generic=Layer<Integer>
  arg[0]=Integer (Class)
RawBox: raw=Box, generic=Box
ArrayBox: raw=Box, generic=Box<String[]>
  arg[0]=String[] (Class)
GenericArrayBox: raw=Box, generic=Box<U[]>
  arg[0]=U[] (GenericArrayType)
NumberListBox: raw=Box, generic=Box<List<? extends Number>>
  arg[0]=List<? extends Number> (ParameterizedType)
Plain: raw=Object, generic=Object
Object: raw=null, generic=null
mapping: U -> Integer
resolved Box argument: List<Integer>
```

Chương trình tự định dạng `Type` để hiển thị tên ngắn, tránh phụ thuộc vào tên class nội bộ của JDK dùng để hiện thực `ParameterizedType` và tránh in thứ tự mảng Reflection không được bảo đảm. Khi xử lý ứng dụng thật, nên giữ nguyên `Type` để phân tích cấu trúc, chỉ chuyển thành chuỗi khi hiển thị.

## 4. Phân tích chi tiết output

### Trường hợp superclass được tham số hóa cụ thể

`StringBox extends Box<String>` nên:

```java
Type type = StringBox.class.getGenericSuperclass();
boolean hasTypeArguments = type instanceof ParameterizedType; // true
```

Ở đây `((ParameterizedType) type).getRawType() == Box.class` và `getActualTypeArguments()[0] == String.class`. Loại đối số là `Class<?>`.

### Trường hợp lớp trung gian vẫn generic

`Layer<U> extends Box<List<U>>` cho `getGenericSuperclass()` là `Box<List<U>>`, nhưng đối số đầu tiên không phải `Class<List>`. Nó là **`ParameterizedType` biểu diễn `List<U>`**. Trong đối số của `List<U>`, `U` là **`TypeVariable<?>`**.

Cách ép:

```java
Class<?> wrong =
        (Class<?>) ((ParameterizedType)
                Layer.class.getGenericSuperclass())
                .getActualTypeArguments()[0];
```

là **sai tại runtime**: phần tử ở vị trí đó là `ParameterizedType`, do đó có thể ném `ClassCastException`. Phải kiểm tra `instanceof` và duyệt các tầng `Type` lồng nhau.

### Trường hợp raw superclass

`RawBox extends Box` cố ý dùng raw type. `getGenericSuperclass()` trả về `Box.class` — một `Class<?>`, không có `getActualTypeArguments()` để truy ngược kiểu `T`.

Không được giả sử `T = Object` là “đối số kiểu khai báo từ lớp con”. Khi dùng raw type, thông tin đối số đã không được ghi ở quan hệ `extends`. Bounds của `T` có thể gợi ý tính hợp lệ của kiểu, nhưng không phục hồi giá trị generic đã bị bỏ.

### Mảng generic và mảng kiểu cụ thể

`ArrayBox extends Box<String[]>` có đối số `String[].class`, chính là một `Class<?>` của array type.

`GenericArrayBox<U> extends Box<U[]>` lại có đối số kiểu `GenericArrayType`, với component type là biến kiểu `U`. Sự khác biệt này quan trọng khi viết serializer hoặc type resolver cho generic arrays. Không thể ép `U[]` thành `Class<?>` khi `U` còn chưa được ràng buộc.

### Wildcard lồng nhau

`NumberListBox extends Box<List<? extends Number>>` có đối số cấp ngoài là `ParameterizedType` mô tả `List<? extends Number>`. Phần tử bên trong `List` là `WildcardType`. Sử dụng `getUpperBounds()` và `getLowerBounds()` để biết giới hạn; không coi wildcard là một `Class<?>` hoặc kiểu thực tế duy nhất.

## 5. Qua nhiều cấp kế thừa: tự ánh xạ TypeVariable

Đây là phần dễ gây nhầm nhất:

```java
class Box<T> {
}

class Layer<U> extends Box<List<U>> {
}

class IntegerLayer extends Layer<Integer> {
}
```

Gọi:

```java
Type type = IntegerLayer.class.getGenericSuperclass();
```

chỉ nhận được **`Layer<Integer>`**, do superclass trực tiếp của `IntegerLayer` là `Layer`. Gọi tiếp:

```java
Type type2 = Layer.class.getGenericSuperclass();
```

nhận **`Box<List<U>>`**, với `U` vẫn là biến kiểu, chứ không tự thành `Box<List<Integer>>`. Đó là hai declaration riêng, Reflection không thay biến của declaration thứ hai theo mapping phát hiện được ở declaration thứ nhất.

Để suy ra đối số cuối cùng của `Box<T>`, thực hiện:

1. Đọc `IntegerLayer extends Layer<Integer>`: đối số của `Layer<U>` là `Integer`, do đó lập mapping **`U → Integer`**.
2. Đọc `Layer<U> extends Box<List<U>>`: đối số của `Box<T>` là biểu thức kiểu **`List<U>`**.
3. Thay `U` bằng `Integer` trong biểu thức trên: **`List<Integer>`**.
4. Kết luận đối số `T` của `Box<T>` ở quan hệ kế thừa được suy ra là **`List<Integer>`**.

Trong chương trình chạy được ở mục 3, ví dụ chỉ giải một cấp mapping đơn giản. Với công cụ tổng quát, cần xử lý nhiều biến và nhiều cấp, chẳng hạn:

```java
class Pair<A, B> {
}

class Intermediate<X, Y> extends Pair<Y, List<X>> {
}

class FinalPair extends Intermediate<String, Integer> {
}
```

Đây là đoạn minh họa. Mapping ban đầu là `X → String` và `Y → Integer`, nên `FinalPair` nhìn từ `Pair<A,B>` tương ứng `Pair<Integer, List<String>>`.

Để xây resolver đúng cho lớp bất kỳ, nên giữ một `Map<TypeVariable<?>, Type>` thay vì chỉ dựa vào tên biến như `"T"`. Hai class khác nhau có thể cùng khai báo biến `T` nhưng đó là **hai `TypeVariable` thuộc hai `GenericDeclaration` khác nhau**. Nếu chỉ map chuỗi tên, dễ thay sai biến.

Một thuật toán tổng quát:

- Bắt đầu từ `Class<?>` lớp con.
- Ở mỗi bước, lấy `getGenericSuperclass()`. Nếu là `ParameterizedType`, lấy raw superclass và ghép danh sách `rawClass.getTypeParameters()` với `getActualTypeArguments()` theo vị trí.
- Trước khi lưu mapping mới, **thay thế đệ quy** những `TypeVariable` đã có mapping từ các cấp con trong từng đối số.
- Tiếp tục tới superclass tiếp theo cho tới lớp generic đích hoặc `Object`.
- Khi gặp `ParameterizedType`, `GenericArrayType` hoặc `WildcardType` lồng nhau, phải thay thế trong cấu trúc con; không chỉ thay nếu đối số trực tiếp là `TypeVariable`.
- Nếu gặp raw edge, biến không có mapping hoặc chuỗi kế thừa không đi tới target, **giữ trạng thái chưa phân giải** thay vì đoán một `Class<?>` cụ thể.

Nếu công cụ cần xuất ra một đối tượng `Type` hoàn chỉnh sau thay thế, hãy dùng biểu diễn Type phù hợp hoặc thư viện resolver đã được kiểm chứng, đồng thời kiểm tra compatibility với JDK/module path. Việc tạo string `"List<Integer>"` chỉ để in demo **không tương đương** đã xây xong một `ParameterizedType` đúng ngữ nghĩa.

## 6. Phân biệt TypeVariable, bounds và đối số thực tế

Xét:

```java
class NumericBox<T extends Number> {
}

class LongBox extends NumericBox<Long> {
}

class StillGeneric<N extends Number> extends NumericBox<N> {
}
```

Các trường hợp:

- `LongBox.class.getGenericSuperclass()` là `NumericBox<Long>`; argument là `Long.class`, đã cụ thể.
- `StillGeneric.class.getGenericSuperclass()` là `NumericBox<N>`; argument là `TypeVariable<N>`, chưa chọn `Integer`, `Long` hay loại số nào.
- `N.getBounds()` chỉ cho biết upper bound `Number`. Nó **không nói** lớp con đã chọn `Number` làm actual type argument.
- Với `NumericBox<T>`, `NumericBox.class.getTypeParameters()` trả về danh sách biến kiểu do `NumericBox` khai báo, ví dụ `T`. Đây là **type parameter declaration**, khác `getActualTypeArguments()` của quan hệ `extends NumericBox<Long>`.

Trong code generic có nhiều cấp, có thể một biến kiểu vẫn chưa được giải xong. Trường hợp đó, kết quả hợp lệ của resolver có thể là một `TypeVariable<?>`, không nhất thiết là `Class<?>`. Chỉ ép về class khi chắc chắn đã đạt một concrete type là `Class<?>`.

## 7. Anonymous subclass và kỹ thuật type token

Cách tạo object trực tiếp:

```java
Box<String> value = new Box<String>();
Type generic = value.getClass().getGenericSuperclass();
```

không khôi phục được đối số `String`: lớp runtime của `value` vẫn là `Box.class`, và superclass của `Box` là `Object`.

Nhưng nếu tạo **anonymous subclass** có superclass generic cụ thể:

```java
Box<String> value = new Box<String>() {};

Type generic = value.getClass().getGenericSuperclass();
boolean captured = generic instanceof ParameterizedType; // true
```

đây là đoạn minh họa có lớp `Box<T>` từ ví dụ trước. Anonymous class thực sự **extends `Box<String>`**, nên generic superclass signature của chính anonymous class có thể chứa `String`. Kỹ thuật này là nền tảng cho các **type token**:

```java
abstract class TypeToken<T> {
    protected final Type capturedType;

    protected TypeToken() {
        Type parent = getClass().getGenericSuperclass();
        if (!(parent instanceof ParameterizedType p)) {
            throw new IllegalStateException(
                    "Subclass must provide a concrete type argument");
        }
        this.capturedType = p.getActualTypeArguments()[0];
    }

    public Type type() {
        return capturedType;
    }
}
```

Đây là lớp **minh họa** cần import `java.lang.reflect.Type` và `ParameterizedType`. Ví dụ sử dụng:

```java
TypeToken<List<String>> token = new TypeToken<List<String>>() {};
Type captured = token.type(); // Metadata của List<String>
```

**Giới hạn cần hiểu:** type token này đọc **superclass trực tiếp của anonymous subclass**, đúng với mẫu khởi tạo đã nêu. Nếu thêm một lớp trung gian giữa anonymous class và `TypeToken<T>`, cần resolver qua nhiều cấp. Một type token kiểu này cũng không thể tự biến biến kiểu chưa ràng buộc ở nơi gọi thành kiểu cụ thể; ví dụ nếu mã bao ngoài vẫn generic `<U>` thì token có thể chứa `TypeVariable<U>`.

Type erasure vẫn tồn tại. Type token chỉ tận dụng metadata của **generic superclass declaration cụ thể**, không làm mọi instance generic tự mang runtime type arguments.

## 8. Superclass khác interface generic

`getGenericSuperclass()` đi theo **nhánh class extends**, không thay thế việc đọc quan hệ implements hoặc extends interface.

```java
interface Handler<T> {
}

class TextHandler implements Handler<String> {
}
```

Đây là đoạn minh họa. `TextHandler.class.getGenericSuperclass()` trả `Object.class` vì superclass trực tiếp của class là `Object`. Muốn xem `Handler<String>`, hãy dùng:

```java
Type[] interfaces = TextHandler.class.getGenericInterfaces();
```

Kết quả có một `ParameterizedType` tương ứng `Handler<String>`. Với interface kế thừa nhiều interface khác, cần duyệt riêng cây superinterfaces và ánh xạ type variables dọc các cạnh đó.

Nếu mục tiêu là tìm một supertype generic bất kể nó nằm trong đường `extends class` hay `implements interface`, resolver phải xem **cả `getGenericSuperclass()` và `getGenericInterfaces()`**, và tránh lặp khi một interface xuất hiện qua nhiều nhánh.

## 9. Kiểm tra trước khi lấy actual type arguments

Một lỗi phổ biến:

```java
ParameterizedType p = (ParameterizedType)
        child.getGenericSuperclass();
Class<?> argument = (Class<?>)
        p.getActualTypeArguments()[0];
```

Đây là đoạn minh họa; nó chỉ chạy an toàn nếu:

1. `getGenericSuperclass()` thực sự trả `ParameterizedType`, không phải `Class<?>` hoặc `null`.
2. Mảng actual type arguments đủ dài để truy cập chỉ số 0.
3. Đối số đầu là `Class<?>`, không phải nested `ParameterizedType`, `TypeVariable<?>` hay `GenericArrayType`.

Viết code có kiểm tra:

```java
Type parent = child.getGenericSuperclass();

if (parent instanceof ParameterizedType p) {
    Type[] args = p.getActualTypeArguments();
    if (args.length == 1) {
        Type argument = args[0];
        if (argument instanceof Class<?> concreteClass) {
            System.out.println("Concrete: " + concreteClass.getName());
        } else {
            System.out.println("Needs resolution: " + argument.getTypeName());
        }
    }
}
```

Đây là **đoạn minh họa**, biến `child` cần là `Class<?>` hợp lệ và đã import `java.lang.reflect.Type`, `ParameterizedType`. Khi thư viện yêu cầu một kiểu cụ thể, không nên âm thầm fallback về `Object.class` đối với `TypeVariable` chưa giải được; cần trả lỗi rõ ràng hoặc giữ `Type` để tầng gọi quyết định.

Khi đọc generic signature từ bytecode, Reflection có thể gặp `GenericSignatureFormatError` nếu chữ ký không hợp lệ, `TypeNotPresentException` nếu metadata nhắc tới kiểu không có sẵn, hoặc `MalformedParameterizedTypeException` với cấu trúc tham số không tạo được. Vì vậy công cụ xử lý class bên ngoài hoặc plugin phải có đường báo lỗi metadata, thay vì giả định mọi class file luôn có chữ ký hợp lệ và đầy đủ.

## 10. Phân biệt type erasure và metadata đã lưu

Type erasure không có nghĩa *mọi* thông tin generic đều bị xóa sạch. JVM thường thực thi trên raw classes, nhưng compiler có thể lưu **generic signature** trong class file để Reflection đọc lại:

| Tình huống | Reflection có thể biết gì? |
| --- | --- |
| `new Box<String>()` | Runtime class là `Box.class`; không biết riêng đối số `String` từ chính instance |
| `class StringBox extends Box<String>` | Có thể đọc `Box<String>` từ `StringBox.class.getGenericSuperclass()` |
| `class Layer<U> extends Box<List<U>>` | Đọc `Box<List<U>>` nhưng `U` vẫn là biến kiểu |
| `class IntegerLayer extends Layer<Integer>` | Đọc `Layer<Integer>`; muốn đi sâu phải thay thế `U` trên cạnh tiếp theo |
| `class RawBox extends Box` | Không có actual type argument được khai báo trên raw edge |
| `class StringHandler implements Handler<String>` | Phải đọc qua `getGenericInterfaces()` |

Đối với framework serializer/ORM/DI, vấn đề thiết kế thường là **giữ được `Type` đúng biểu thức** trước khi cố lấy `Class<?>`. Các kiểu như `List<String>` và `List<Integer>` có cùng raw type `List.class` nhưng khác type argument, có thể ảnh hưởng quy tắc deserialize và validation.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật |
| --- | --- |
| `getSuperclass()` trả đối số generic của superclass | Nó trả `Class<?>` raw; muốn giữ signature dùng `getGenericSuperclass()` |
| `getGenericSuperclass()` luôn là `ParameterizedType` | Có thể là `Class<?>` hoặc `null` |
| Mọi `getActualTypeArguments()[i]` đều là `Class<?>` | Có thể là `ParameterizedType`, `TypeVariable`, `GenericArrayType`, `WildcardType` |
| `Layer<U> extends Box<List<U>>` có đối số `List.class` | Đối số thực là biểu thức `List<U>`, tức `ParameterizedType` |
| `IntegerLayer extends Layer<Integer>` khiến `Layer.class.getGenericSuperclass()` tự đổi thành `Box<List<Integer>>` | Metadata của `Layer.class` vẫn là `Box<List<U>>`; phải ánh xạ `U → Integer` |
| Bound `T extends Number` có nghĩa actual type là `Number` | Bounds là ràng buộc của biến kiểu, không phải giá trị type argument lớp con đã chọn |
| Lớp raw `extends Box` có thể suy ra argument chính xác từ `Box.class` | Raw edge không ghi actual type argument |
| `new Box<String>().getClass()` nhớ được `String` | Runtime class vẫn là `Box.class`; khác với anonymous subclass type token |
| `getGenericSuperclass()` tự xử lý `implements Handler<String>` | Muốn đọc interface dùng `getGenericInterfaces()` |
| Dùng tên biến `"T"` làm khóa resolver | Biến `T` ở hai generic declarations khác nhau có thể là hai biến khác nhau |
| Một `Type.getTypeName()` đủ để dùng làm runtime class | Type có thể chứa cấu trúc generic chưa giải; đừng coi chuỗi hiển thị là `Class<?>` |
| Class file luôn chứa metadata generic hợp lệ | Metadata có thể thiếu/hỏng hoặc nhắc tới type không tìm thấy; cần xử lý lỗi |

## 12. Câu hỏi tự kiểm tra

Dựa trên các lớp ở mục 3:

1. **`StringBox.class.getSuperclass()` trả gì?** `Box.class`, không có đối số kiểu.
2. **`StringBox.class.getGenericSuperclass()` thuộc dạng nào?** `ParameterizedType` biểu diễn `Box<String>`.
3. **Đối số đầu của `Layer.class.getGenericSuperclass()` là gì?** `ParameterizedType` biểu diễn `List<U>`; bên trong có `TypeVariable<U>`.
4. **`IntegerLayer.class.getGenericSuperclass()` có phải `Box<List<Integer>>` không?** Không; nó chỉ là superclass trực tiếp `Layer<Integer>`.
5. **Muốn suy ra argument của `Box<T>` nhìn từ `IntegerLayer`, cần làm gì?** Lần theo `IntegerLayer → Layer → Box` và thay `U → Integer` để nhận biểu thức `List<Integer>`.
6. **`RawBox.class.getGenericSuperclass()` có `getActualTypeArguments()` không?** Không, kết quả là `Class<?>` biểu diễn `Box`.
7. **Đối số của `Box<U[]>` có bắt buộc là `Class<?>` không?** Không; `U[]` được mô tả bằng `GenericArrayType` khi `U` chưa được ràng buộc.
8. **`new Box<String>()` và `new Box<String>() {}` khác nhau ở đâu?** Vế thứ hai tạo anonymous subclass khai báo `extends Box<String>`; generic superclass metadata của anonymous class có thể lưu `String`.
9. **Một class `implements Handler<String>` nhưng không extends class generic, đọc thông tin kiểu ở đâu?** `getGenericInterfaces()`.

**Ghi nhớ:** `getGenericSuperclass()` cho bạn **biểu thức generic của superclass trực tiếp**. Khi biểu thức đó được tham số hóa, `ParameterizedType.getActualTypeArguments()` cho các `Type` thành phần. Với nhiều tầng kế thừa, giữ cấu trúc `Type` và ánh xạ `TypeVariable` qua từng cạnh; chỉ kết luận một `Class<?>` cụ thể khi metadata thật sự đủ căn cứ.

### Tài liệu tham khảo

- [Java SE 17 — Class.getGenericSuperclass()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getGenericSuperclass())
- [Java SE 17 — ParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 17 — TypeVariable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Java SE 17 — GenericArrayType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/GenericArrayType.html)