# Đọc chữ ký generic của lớp cha và giao diện

## 1. Reflection đọc thông tin nào?

Khi một lớp khai báo `extends Base<List<String>>` hoặc `implements Repository<Long, String>`, chữ ký generic mô tả mối quan hệ kiểu đó. Reflection có thể đọc thông tin được lưu trong tệp class để trả lời: lớp cha trực tiếp là gì, những giao diện trực tiếp nào được khai báo, và đối số kiểu được viết như thế nào.

Đây là việc đọc **khai báo kiểu**, không phải đoán kiểu từ dữ liệu đang chứa trong một đối tượng. Thông tin chữ ký generic trong tệp class là nguồn cho các API phản chiếu generic; nó khác với mô tả kiểu đã xóa dùng cho thực thi. [JVMS: thuộc tính Signature](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.9)

Hai API chính:

```java
Type parent = SomeClass.class.getGenericSuperclass();
Type[] interfaces = SomeClass.class.getGenericInterfaces();
```

Đoạn trên minh họa lời gọi, cần một khai báo `SomeClass` thực tế và import `java.lang.reflect.Type` để biên dịch.

## 2. So sánh API thường và API generic

| API | Kết quả | Thông tin chính |
| --- | --- | --- |
| `getSuperclass()` | `Class<?>` | Lớp cha trực tiếp |
| `getGenericSuperclass()` | `Type` | Kiểu lớp cha trực tiếp, có đối số generic nếu được khai báo |
| `getInterfaces()` | `Class<?>[]` | Các giao diện trực tiếp |
| `getGenericInterfaces()` | `Type[]` | Các kiểu giao diện trực tiếp, có đối số generic |
| `getTypeParameters()` | `TypeVariable<?>[]` | Các tham số kiểu mà chính lớp/interface khai báo |

Với `class Service extends Base<String>`, `getSuperclass()` trả `Base.class`; API generic có thể biểu diễn `Base<String>`. Trong khi đó, `Service.class.getTypeParameters()` rỗng vì Service không tự khai báo tham số kiểu. [API Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)

“Trực tiếp” là giới hạn quan trọng. Đọc giao diện của một lớp không tự gom giao diện của lớp cha và mọi giao diện tổ tiên. Muốn xem toàn bộ quan hệ, phải duyệt tiếp.

## 3. Vì sao Type không luôn là Class?

`Type` là giao diện chung của mô hình kiểu reflection. Một đối số kiểu có thể là kiểu cụ thể, kiểu có tham số, biến kiểu hay mảng generic; không được ép mọi kết quả thành `Class<?>`. [API Type](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Type.html)

| Dạng | Ví dụ trong thông tin generic | Cách đọc tiếp |
| --- | --- | --- |
| `Class<?>` | `String`, một lớp cha không có đối số kiểu | Dùng API của Class |
| `ParameterizedType` | `Base<String>`, `List<String>` | Raw type, đối số kiểu, owner |
| `TypeVariable<?>` | `T`, `U` | Tên, nơi khai báo, cận |
| `GenericArrayType` | `T[]` | Kiểu phần tử generic |
| `WildcardType` | `? extends Number` trong kiểu lồng | Cận trên/cận dưới |

Wildcard không được dùng như đối số trực tiếp trong khai báo `extends Base<?>`; ví dụ đó không hợp lệ. Nó vẫn có thể xuất hiện sâu hơn, chẳng hạn `extends Base<List<? extends Number>>`.

Với `ParameterizedType`:

- `getRawType()` cho kiểu khai báo gốc, chẳng hạn `Base`.
- `getActualTypeArguments()` cho các đối số của lần sử dụng, chẳng hạn `String`.
- `getOwnerType()` cho kiểu bao ngoài khi đây là kiểu thành viên có owner.

“Actual” trong tên phương thức không bảo đảm kết quả là một lớp cụ thể; nó vẫn có thể là `TypeVariable` như `U`. [API ParameterizedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html)

## 4. Ví dụ chạy được: lớp cha và giao diện trực tiếp

Lưu toàn bộ vào **GenericHierarchyDemo.java**:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

public class GenericHierarchyDemo {
    interface Source<T> {
    }

    interface Repository<K, V> extends Source<V> {
    }

    interface Named {
    }

    static class Base<T> {
    }

    static class Service
            extends Base<java.util.List<String>>
            implements Repository<Long, String>, Named {
    }

    static class Child extends Service {
    }

    public static void main(String[] args) {
        Class<?> type = Service.class;

        System.out.println("rawParent="
                + type.getSuperclass().getSimpleName());

        Type genericParent = type.getGenericSuperclass();
        System.out.println("genericParent="
                + format(genericParent));

        if (genericParent instanceof ParameterizedType parent) {
            Class<?> raw = (Class<?>) parent.getRawType();
            Type argument = parent.getActualTypeArguments()[0];

            System.out.println("parentRaw=" + raw.getSimpleName());
            System.out.println("parentArgument=" + format(argument));
            System.out.println("argumentParameterized="
                    + (argument instanceof ParameterizedType));
        }

        Type[] interfaces = type.getGenericInterfaces();
        for (int i = 0; i < interfaces.length; i++) {
            System.out.println("interface" + i + "="
                    + format(interfaces[i]));
        }

        System.out.println("serviceTypeParameters="
                + type.getTypeParameters().length);
        System.out.println("baseTypeParameter="
                + Base.class.getTypeParameters()[0].getName());

        System.out.println("repositoryParentInterface="
                + format(Repository.class
                    .getGenericInterfaces()[0]));

        System.out.println("childParent="
                + format(Child.class.getGenericSuperclass()));
        System.out.println("childDirectInterfaces="
                + Child.class.getGenericInterfaces().length);
    }

    private static String format(Type type) {
        if (type == null) {
            return "<none>";
        }

        if (type instanceof Class<?> concrete) {
            return concrete.getSimpleName();
        }

        if (type instanceof ParameterizedType parameterized) {
            StringBuilder text = new StringBuilder(
                    format(parameterized.getRawType()));
            text.append("<");

            Type[] arguments =
                    parameterized.getActualTypeArguments();
            for (int i = 0; i < arguments.length; i++) {
                if (i > 0) {
                    text.append(", ");
                }
                text.append(format(arguments[i]));
            }

            return text.append(">").toString();
        }

        return type.getTypeName();
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 GenericHierarchyDemo.java
java GenericHierarchyDemo
```

Kết quả:

```text
rawParent=Base
genericParent=Base<List<String>>
parentRaw=Base
parentArgument=List<String>
argumentParameterized=true
interface0=Repository<Long, String>
interface1=Named
serviceTypeParameters=0
baseTypeParameter=T
repositoryParentInterface=Source<V>
childParent=Service
childDirectInterfaces=0
```

### Đọc đúng các kết quả

`Base<List<String>>` là một `ParameterizedType`. Đối số duy nhất của nó là `List<String>`, cũng là `ParameterizedType`; ép đối số này thành `Class` sẽ sai.

`Repository<Long, String>` mang đối số kiểu; `Named` là giao diện không có tham số nên được biểu diễn bằng `Class`. Khi đọc `Repository.class`, chữ ký giao diện cha vẫn là `Source<V>`, không tự trở thành `Source<String>` chỉ vì một lớp khác dùng Repository với V là String.

Child kế thừa Service, nên lớp cha trực tiếp là Service. Child không trực tiếp khai báo `implements`, vì vậy mảng giao diện trực tiếp rỗng. Điều đó không có nghĩa Child không phải một Repository theo quan hệ kiểu.

Thứ tự giao diện trực tiếp theo thứ tự khai báo trong mã nguồn. Hàm `format` ở ví dụ chủ động rút tên lớp cho dễ đọc; đây không phải bộ định danh kiểu tổng quát. Với các kiểu lồng phức tạp, muốn biểu diễn đầy đủ cần xử lý owner và tên đủ điều kiện. [API Class: các quan hệ generic](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)

## 5. Nhiều tầng kế thừa cần ngữ cảnh thay thế biến kiểu

Xem chuỗi:

```java
class Parent<T> {
}

class Middle<U> extends Parent<U> {
}

class Leaf extends Middle<String> {
}
```

Đây là ba khai báo minh họa; chương trình đầy đủ theo sau dùng các lớp lồng cùng quan hệ.

Đọc chữ ký của Middle cho `Parent<U>`. Muốn kết luận kiểu T của Parent trong ngữ cảnh Leaf là String, cần ghép:

```text
Leaf → Middle<String>     suy ra U của Middle = String
Middle<U> → Parent<U>     suy ra T của Parent = U
Thay thế theo ngữ cảnh   T = String
```

Không thể chỉ nhìn `Parent.class.getTypeParameters()[0]` rồi nhận ngay String: kết quả ấy là biến kiểu T của khai báo Parent.

### Chương trình minh họa việc ghép hai quan hệ

Lưu thành **GenericContextDemo.java**:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.HashMap;
import java.util.Map;

public class GenericContextDemo {
    static class Parent<T> {
    }

    static class Middle<U> extends Parent<U> {
    }

    static class Leaf extends Middle<String> {
    }

    public static void main(String[] args) {
        ParameterizedType leafParent =
                requireParameterized(
                    Leaf.class.getGenericSuperclass());

        TypeVariable<?> middleVariable =
                Middle.class.getTypeParameters()[0];
        Type leafArgument =
                leafParent.getActualTypeArguments()[0];

        Map<TypeVariable<?>, Type> bindings = new HashMap<>();
        bindings.put(middleVariable, leafArgument);

        ParameterizedType middleParent =
                requireParameterized(
                    Middle.class.getGenericSuperclass());
        Type parentArgument =
                middleParent.getActualTypeArguments()[0];

        System.out.println("leafToMiddle="
                + leafArgument.getTypeName());
        System.out.println("middleToParent="
                + parentArgument.getTypeName());
        System.out.println("argumentIsVariable="
                + (parentArgument instanceof TypeVariable<?>));

        Type resolved = parentArgument;
        if (parentArgument instanceof TypeVariable<?> variable) {
            resolved = bindings.getOrDefault(variable, variable);
        }

        System.out.println("resolvedParentArgument="
                + resolved.getTypeName());
        System.out.println("parentStillDeclares="
                + Parent.class.getTypeParameters()[0].getName());
    }

    private static ParameterizedType requireParameterized(
            Type type) {
        if (type instanceof ParameterizedType parameterized) {
            return parameterized;
        }
        throw new IllegalArgumentException(
                "Expected a parameterized relation");
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 GenericContextDemo.java
java GenericContextDemo
```

Kết quả:

```text
leafToMiddle=java.lang.String
middleToParent=U
argumentIsVariable=true
resolvedParentArgument=java.lang.String
parentStillDeclares=T
```

Chương trình chỉ ghép đúng chuỗi hai quan hệ trong ví dụ, không phải bộ phân giải generic tổng quát. Nó không sửa khai báo Parent: dòng cuối vẫn là T. Kết quả String thuộc **ngữ cảnh Leaf**.

Khóa ánh xạ là `TypeVariable<?>`, không chỉ chuỗi tên `"T"`: hai lớp khác nhau có thể đều khai báo T nhưng đó là hai biến kiểu khác nhau. Hãy dùng so sánh theo hợp đồng `equals`, không dựa vào việc các đối tượng reflection nhất định có cùng tham chiếu. [API TypeVariable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/TypeVariable.html)

## 6. Nếu xây bộ duyệt tổng quát

Để tìm một giao diện tổ tiên trong ngữ cảnh lớp cụ thể, có thể duyệt cả quan hệ lớp cha và giao diện:

1. Bắt đầu ở lớp cần phân tích và một ánh xạ biến kiểu.
2. Đọc từng quan hệ trực tiếp.
3. Nếu quan hệ là `ParameterizedType`, ghép tham số kiểu của raw type với đối số tương ứng đã thay thế theo ngữ cảnh hiện tại.
4. Đi tiếp vào lớp/interface cha với ánh xạ phù hợp.
5. Khi gặp kiểu đích, trả các đối số sau thay thế; giữ nguyên phần chưa biết thay vì tự đoán một lớp.

Đây là định hướng thuật toán. Bộ triển khai thật cần thay thế đệ quy bên trong `ParameterizedType`, `GenericArrayType` và các cận wildcard; còn phải xử lý owner, đường đi giao diện và phần thông tin chưa được cố định.

Ví dụ `Middle<U> extends Parent<List<U>>` không được giải bằng cách chỉ tra nguyên đối số `List<U>` trong map biến kiểu. Cần đi vào đối số của List để thay U. Với `Parent<U[]>`, phần mảng có thể được biểu diễn bằng `GenericArrayType`, nên cần đọc kiểu thành phần qua `getGenericComponentType()`. [API GenericArrayType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/GenericArrayType.html)

Không dùng `TypeVariable.getBounds()` như kết quả thay thế. Cận `T extends Number` nói rằng T bị giới hạn bởi Number; nó không chứng minh T thực tế là Number trong mọi lớp con.

## 7. Giới hạn do thông tin khai báo và xóa kiểu

Một đối tượng được tạo bằng `new ArrayList<String>()` không có một `Class` riêng cho String. Đọc `object.getClass()` thường chỉ cho lớp ArrayList và các quan hệ generic khai báo của ArrayList, không khôi phục đối số String từ cú pháp tạo đối tượng ở bên gọi.

Ngược lại, lớp được khai báo `class StringList extends ArrayList<String>` lưu quan hệ kiểu có đối số trong chữ ký của lớp con. Đó là lý do có thể đọc String từ quan hệ lớp cha của StringList. Kết quả này đến từ khai báo lớp con, không từ nội dung hiện tại của một instance.

Nếu một quan hệ dùng kiểu thô hoặc metadata generic đã bị công cụ biến đổi loại bỏ, API không có đủ chữ ký để tái dựng các đối số đã mất. Không giả định rằng thấy `Class<Base>` thì đối số của Base là Object; có thể thông tin đối số không được giữ ở quan hệ đó.

Một số trường hợp biên:

- `Object.class.getGenericSuperclass()` trả `null`.
- Đọc lớp cha generic của một interface trả `null`; giao diện cha phải đọc bằng `getGenericInterfaces()`.
- Một lớp có thể trả `Class` làm quan hệ lớp cha, ví dụ Child → Service trong chương trình đầu.
- Metadata sai hoặc thiếu kiểu được tham chiếu có thể gây `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException`; không coi mọi lỗi thành mảng rỗng. [Hợp đồng API Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html)

## 8. Cách đọc đáng tin cậy

Dùng `instanceof` kiểm tra dạng Type trước khi đi tiếp. Dùng các thành phần mô hình kiểu thay vì phân tích chuỗi từ `toString()`; chuỗi thích hợp để hiển thị chẩn đoán, không phải cấu trúc dữ liệu cho thuật toán.

Giữ rõ hai đầu của một kết luận: “đối số khai báo trực tiếp” và “đối số đã giải trong ngữ cảnh lớp cụ thể”. Nếu công cụ chưa giải được U, hãy báo U cùng nơi khai báo thay vì gán một kiểu cụ thể không có bằng chứng.

### Tự thực hành

1. Đổi Service thành `extends Base<String>`: vì sao đối số đầu tiên đổi từ ParameterizedType thành Class?
2. Thêm `interface Audited` vào cuối danh sách `implements`: xác nhận mảng giao diện trực tiếp đổi thế nào.
3. Đọc `Source.class.getGenericSuperclass()`: vì sao kết quả không phải lớp Object?
4. Đổi Leaf thành `extends Middle<Integer>`: dòng `resolvedParentArgument` đổi ra sao?
5. Đổi Middle thành `extends Parent<List<U>>`: vì sao chương trình ghép map đơn giản chưa đủ để giải đệ quy?
6. Tạo hai lớp đều khai báo biến T: chỉ ra vì sao map khóa bằng tên `"T"` có thể gộp sai hai ngữ cảnh.
