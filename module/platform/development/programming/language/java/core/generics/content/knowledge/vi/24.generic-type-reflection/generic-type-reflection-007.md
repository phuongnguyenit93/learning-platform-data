# Đọc getGenericSuperclass, getGenericInterfaces và chữ ký thành viên trong Java Reflection

## 1. Mục tiêu: quan sát **khai báo kiểu** thay vì đoán kiểu runtime

Khi tìm hiểu Java Generics bằng Reflection, có ba nhóm câu hỏi thường gặp:

1. Một class **extends** generic superclass với type arguments nào?
2. Một class **implements** generic interfaces nào và dùng type arguments nào?
3. Một field, method, constructor hoặc type parameter **được khai báo** với kiểu generic nào?

Các API chính:

~~~java
Class<?> clazz = SomeClass.class;

Type parent = clazz.getGenericSuperclass();
Type[] directInterfaces = clazz.getGenericInterfaces();

Type fieldType = field.getGenericType();
Type returnType = method.getGenericReturnType();
Type[] parameters = method.getGenericParameterTypes();
Type[] thrown = method.getGenericExceptionTypes();
~~~

Các dòng trên là **minh họa API**: `SomeClass`, `field` và `method` phải được cung cấp từ chương trình cụ thể. Ví dụ Java 17 hoàn chỉnh, có thể chạy ngay, nằm ở phần 9.

Điều đặc biệt quan trọng: Reflection về generics chủ yếu đọc **metadata chữ ký kiểu lưu tại class file**. Nó **không** có nghĩa JVM giữ một phiên bản runtime khác nhau của `List<String>` và `List<Integer>`, và **không** tự xác minh kiểu từng phần tử trong một collection.

Chủ đề này là một phần của **phản chiếu kiểu** (*generic type reflection*), khác với việc đọc object data thông thường. Phải phân biệt:

- **`Class<?>`**: mô tả runtime class hoặc interface.
- **`java.lang.reflect.Type`**: mô tả một dạng kiểu trong hệ thống Reflection, có thể chứa type arguments, wildcard, type variable hoặc generic array.
- **`Field` / `Method` / `Constructor<?>`**: đối tượng Reflection biểu diễn khai báo thành viên, từ đó có thể đọc chữ ký kiểu tổng quát.

## 2. Khung ví dụ xuyên suốt

Giả sử một class con gắn `T = String` cho superclass generic và triển khai một interface generic:

~~~java
interface Source<K, V> {
    V get(K key);
}

class Parent<T> {
    public T item;
    public List<T> items;
    public T[] buffer;
    public List<? extends Number> upper;

    public <E extends Exception> List<? super T> transform(
            List<? extends T> input, E problem) throws E {
        throw problem;
    }
}

final class Child extends Parent<String>
        implements Source<String, List<Integer>>, Serializable {

    @Override
    public List<Integer> get(String key) {
        return List.of(key.length());
    }
}
~~~

Mảnh ví dụ giả định có import `java.io.Serializable` và `java.util.List`; trong chương trình độc lập ở phần 9, chúng sẽ là các nested types.

Các lớp chứa nhiều tầng thông tin generic:

- `Parent<T>` khai báo một **class type variable** `T`.
- `Child extends Parent<String>` cung cấp **type argument String** ở chữ ký superclass.
- `Child implements Source<String,List<Integer>>` cung cấp **hai type arguments**, trong đó type argument thứ hai chính là một parameterized type lồng nhau.
- `Serializable` là non-generic interface, nên không có type arguments.
- Trường `item` có kiểu `T`, `items` có `List<T>`, `buffer` có `T[]`, `upper` có wildcard `? extends Number`.
- `transform` có một **method type variable** `E extends Exception`, một tham số `List<? extends T>` và kết quả `List<? super T>`.

Không có một API duy nhất trả luôn “sơ đồ kiểu đã giải hết mọi biến” cho toàn bộ các khai báo này. Ta phải đọc đúng thành phần của `Type`, đồng thời hiểu ngữ cảnh khai báo gốc.

## 3. Class.getSuperclass và getGenericSuperclass khác nhau ra sao?

Hai API đều liên quan đến **superclass trực tiếp**, nhưng kiểu trả về và lượng thông tin rất khác.

~~~java
Class<?> erased = Child.class.getSuperclass();
Type generic = Child.class.getGenericSuperclass();
~~~

Với `Child extends Parent<String>`:

- `getSuperclass()` trả một **`Class<?>` biểu diễn Parent**. Nó không biểu diễn type argument String.
- `getGenericSuperclass()` trả một **`Type`**, cụ thể thường là một `ParameterizedType` mô tả `Parent<String>`.

Đọc type arguments một cách có kiểm tra:

~~~java
Type type = Child.class.getGenericSuperclass();

if (type instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();

    System.out.println(((Class<?>) raw).getSimpleName()); // Parent
    System.out.println(arguments[0].getTypeName());       // java.lang.String
}
~~~

**Không cast mù quáng** kiểu trả về sang ParameterizedType. Nếu class extends một non-generic superclass hay dùng raw parent type, kết quả có thể là `Class<?>`; nếu không có superclass theo trường hợp API quy định, nó có thể là `null`.

Một bảng hữu ích:

| Khai báo class | `getSuperclass()` | `getGenericSuperclass()` |
| --- | --- | --- |
| `class A extends Parent<String>` | Class của Parent | ParameterizedType của Parent<String> |
| `class B extends Parent` (raw) | Class của Parent | Có thể là Class của raw Parent |
| `class C extends Object` | Class của Object | Class của Object |
| `java.lang.Object` | null | null |
| Interface type | Không có class superclass theo cách class có | Thường null cho `getGenericSuperclass()` |

Các ngoại lệ như `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` có thể xuất hiện khi generic signature chứa type không tải được hoặc thông tin bất hợp lệ; cần xem API contract nếu xử lý bytecode lạ hoặc class không đầy đủ.

### 3.1. getGenericSuperclass chỉ xét **quan hệ extends trực tiếp**

Nếu `Grandchild extends Child` thì đọc trực tiếp `Grandchild.class.getGenericSuperclass()` sẽ mô tả Child, không tự đi hết cây tổ tiên đến `Parent<String>`.

Muốn lấy generic arguments của một ancestor nhiều cấp, cần duyệt các generic superclass edges và thay thế những type variables theo từng cấp. Đây là một bài toán giải kiểu khác, không phải tính năng tự động của riêng một lệnh `getGenericSuperclass()`.

## 4. Class.getInterfaces và getGenericInterfaces

Tương tự với các **interfaces được khai báo trực tiếp**:

~~~java
Class<?>[] erased = Child.class.getInterfaces();
Type[] generic = Child.class.getGenericInterfaces();
~~~

Với:

~~~java
final class Child extends Parent<String>
        implements Source<String, List<Integer>>, Serializable {
    // ...
}
~~~

`getInterfaces()` trả các `Class<?>` của `Source` và `Serializable`, không chứa type arguments.

`getGenericInterfaces()` trả một mảng `Type[]` có thể bao gồm:
- `ParameterizedType` cho `Source<String,List<Integer>>`;
- `Class<?>` cho interface không generic `Serializable`.

Vì vậy:

~~~java
Type[] interfaces = Child.class.getGenericInterfaces();

for (Type type : interfaces) {
    System.out.println(type.getTypeName());
}
~~~

Có thể quan sát interface generic đi kèm các type arguments, còn marker interface Serializable được biểu diễn như một class/interface token thông thường.

**Quan trọng:** đây là các **interfaces trực tiếp được class hoặc interface khai báo**, không phải mọi interface nó kế thừa gián tiếp. Để dựng tất cả generic interfaces trên toàn bộ type hierarchy, cần duyệt superclass/interfaces thích hợp và giải type variables khi có kế thừa nhiều cấp.

### 4.1. Bóc tách interface có type argument lồng nhau

~~~java
Type[] interfaces = Child.class.getGenericInterfaces();

if (interfaces[0] instanceof ParameterizedType sourceType) {
    Type[] arguments = sourceType.getActualTypeArguments();

    Type keyType = arguments[0];    // String.
    Type valueType = arguments[1];  // List<Integer>.

    System.out.println(keyType.getTypeName());
    System.out.println(valueType.getTypeName());
}
~~~

Đầu ra theo `getTypeName()` có thể là:

~~~text
java.lang.String
java.util.List<java.lang.Integer>
~~~

Với `arguments[1]`, không nên ép thẳng thành `Class<List>`. `List<Integer>` là một **ParameterizedType**, vì nó có raw type List và actual type argument Integer.

Có thể tiếp tục bóc lớp:

~~~java
ParameterizedType listType = (ParameterizedType) valueType;

Type listRawType = listType.getRawType(); // Class của List.
Type itemType = listType.getActualTypeArguments()[0]; // Integer.
~~~

Không phải mọi generic argument đều là `Class<?>`. Type argument có thể chính là một `TypeVariable<?>`, một `WildcardType`, một `ParameterizedType` khác hoặc một `GenericArrayType`.

## 5. Hệ thống Type: phải kiểm tra dạng trước khi cast

`java.lang.reflect.Type` là abstraction chung. Một cách phân loại thực dụng:

| Kiểu Reflection | Ví dụ khai báo | Dữ liệu cần đọc |
| --- | --- | --- |
| `Class<?>` | `String`, `Integer`, raw `List` | Tên class, superclass, interfaces, thành viên |
| `ParameterizedType` | `List<String>`, `Map<String,List<Integer>>` | `getRawType`, `getActualTypeArguments`, `getOwnerType` |
| `TypeVariable<?>` | `T` trong Parent<T>, `E` của method generic | `getName`, `getBounds`, `getGenericDeclaration` |
| `WildcardType` | `?`, `? extends Number`, `? super T` | `getUpperBounds`, `getLowerBounds` |
| `GenericArrayType` | `T[]`, `List<String>[]` trong chữ ký generic | `getGenericComponentType` |

Đây là các nhánh *kiểu của mô tả Type*, không phải các loại object runtime tương ứng với mọi generic instantiation.

Một visitor đơn giản:

~~~java
static void describe(Type type) {
    if (type instanceof Class<?> clazz) {
        System.out.println("Class: " + clazz.getName());
    } else if (type instanceof ParameterizedType p) {
        System.out.println("Parameterized: " + p.getTypeName());
    } else if (type instanceof TypeVariable<?> v) {
        System.out.println("Variable: " + v.getName());
    } else if (type instanceof WildcardType w) {
        System.out.println("Wildcard: " + w.getTypeName());
    } else if (type instanceof GenericArrayType a) {
        System.out.println("Array: " + a.getTypeName());
    }
}
~~~

Đoạn trên là minh họa helper và cần `import java.lang.reflect.*;`. Nếu muốn in cây lồng nhau, visitor cần **đệ quy** vào raw/owner/arguments/bounds/component types, đồng thời tránh vòng lặp do self-bounded generics như `T extends Comparable<T>`.

### 5.1. Không dựa vào tên class cài đặt nội bộ của Type

Một `ParameterizedType` có thể được JDK thể hiện qua class nội bộ, nhưng tên class cài đặt này không phải public contract phù hợp để so sánh. Hãy dùng:

~~~java
type instanceof ParameterizedType
~~~

và các phương thức của interface chuẩn. Đừng dùng `type.getClass().getSimpleName()` rồi giả định kết quả luôn giống nhau giữa các JDK.

## 6. ParameterizedType: raw type, actual arguments, owner

Ví dụ một generic type:

~~~java
Map<String, List<Integer>>
~~~

có:
- raw type `Map`;
- argument thứ nhất `String`;
- argument thứ hai `List<Integer>`, bản thân là ParameterizedType.

Với:

~~~java
ParameterizedType p = (ParameterizedType) someType;

Type raw = p.getRawType();
Type[] args = p.getActualTypeArguments();
Type owner = p.getOwnerType();
~~~

**`getRawType()`** mô tả generic class/interface đứng làm gốc (`Map`). Nó là `Type`, thường là một `Class<?>` trong những ví dụ thông dụng.

**`getActualTypeArguments()`** trả type arguments được viết trong chữ ký generic ở mức khai báo tương ứng; với Map là hai giá trị. Đừng mặc định từng phần tử đều là Class.

**`getOwnerType()`** cho biết enclosing/owner type khi kiểu generic là member type có owner thích hợp. Chẳng hạn các cấu trúc `Outer<String>.Inner<Integer>` có thể cần thông tin về cả owner Outer<String> lẫn Inner<Integer>. Với top-level Map thông thường, owner là null.

Không được đồng nhất type owner của member type với superclass. Đây là hai quan hệ khác nhau:
- `getGenericSuperclass` đọc **extends**;
- `getOwnerType` đọc **owner/enclosing type** trong cấu trúc tên kiểu member.

### 6.1. Type arguments không bảo đảm số lượng element runtime

Một `ParameterizedType` mô tả `List<String>` không tự duyệt mọi element của object `List`. Nó cũng không phải bằng chứng rằng một raw alias chưa từng thêm Integer. Generic metadata có thể rất đầy đủ ở **declaration** trong khi runtime object vẫn có dữ liệu không phù hợp với kỳ vọng compile-time nếu code sử dụng raw/unchecked operations.

## 7. TypeVariable: biến kiểu thuộc **khai báo nào**?

Trong:

~~~java
class Parent<T> {
    T item;

    <E extends Exception> void act(E problem) throws E {
        throw problem;
    }
}
~~~

có hai type variables khác nhau:

- `T` thuộc **khai báo class Parent<T>**.
- `E` thuộc **khai báo method act<E>**.

Đọc type variables ở class:

~~~java
TypeVariable<?>[] vars = Parent.class.getTypeParameters();
System.out.println(vars[0].getName()); // T
~~~

Đọc ở method:

~~~java
Method m = Parent.class.getDeclaredMethod("act", Exception.class);
TypeVariable<Method>[] methodVars = m.getTypeParameters();
System.out.println(methodVars[0].getName()); // E
~~~

`getGenericDeclaration()` cho biết **nơi khai báo type variable**. Điều này quan trọng vì hai class khác nhau đều có thể dùng tên T mà vẫn là **hai biến kiểu khác nhau**. Không nên map type variables chỉ bằng tên String `"T"` trong một type resolver phức tạp.

Đọc giới hạn:

~~~java
for (Type bound : methodVars[0].getBounds()) {
    System.out.println(bound.getTypeName());
}
~~~

Nếu E extends Exception, upper bound liên quan là `java.lang.Exception`. Với T không có bound cụ thể, giới hạn mặc định là Object.

### 7.1. Raw erasure và TypeVariable không giống nhau

Khi `T` không có bound cụ thể, erasure của T thường là Object; nhưng `field.getGenericType()` vẫn có thể trả **TypeVariable T**, bởi metadata khai báo giữ chữ ký `T`.

Vì vậy:

~~~java
Field f = Parent.class.getDeclaredField("item");

Class<?> erased = f.getType(); // Object.class.
Type generic = f.getGenericType(); // TypeVariable T.
~~~

Đừng kết luận: “Runtime erasure thành Object thì getGenericType cũng phải trả Object”. Hai API cố ý thể hiện **hai lớp thông tin khác nhau**.

## 8. WildcardType: đọc giới hạn ? extends và ? super

Xét:

~~~java
class Parent<T> {
    List<? extends Number> upper;
    List<? super T> lower;
}
~~~

Các field types là ParameterizedType, nhưng bên trong có wildcard:

~~~java
Field field = Parent.class.getDeclaredField("upper");
ParameterizedType p = (ParameterizedType) field.getGenericType();

WildcardType wildcard =
        (WildcardType) p.getActualTypeArguments()[0];

Type[] uppers = wildcard.getUpperBounds();
Type[] lowers = wildcard.getLowerBounds();
~~~

Với `? extends Number`:
- upper bound là Number;
- danh sách lower bounds rỗng.

Với `? super T`:
- lower bound là **TypeVariable T**;
- upper bound mặc định là Object.

Với `?` không có giới hạn tường minh:
- upper bound mặc định Object;
- lower bounds rỗng.

Đọc đúng wildcard bounds có ích cho serializer, schema generator và API analyzer; nhưng đừng tự chuyển chúng thành một runtime check “collection luôn chứa Number” chỉ vì Reflection nhìn thấy `? extends Number` ở field declaration.

### 8.1. Wildcard và Generic Array có thể lồng nhau

Một field có thể khai báo:

~~~java
List<? extends T[]>[] arrays;
~~~

Đây là một kiểu nhiều tầng gồm generic array, parameterized type và wildcard. Một type traversal đúng phải phân loại và đệ quy qua từng tầng thay vì ép toàn bộ thành `Class<?>`.

Đừng viết một utility chỉ xử lý `Class` và `ParameterizedType` rồi xem tất cả kiểu còn lại là “không hợp lệ”; Java Generics có nhiều dạng Type hợp pháp.

## 9. Chương trình Java 17+ hoàn chỉnh

Lưu tệp **ReflectionSignaturesDemo.java**:

~~~java
import java.io.Serializable;
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.WildcardType;
import java.util.Arrays;
import java.util.List;

public class ReflectionSignaturesDemo {
    interface Source<K, V> {
        V get(K key);
    }

    static class Parent<T> {
        public T item;
        public List<T> items;
        public T[] buffer;
        public List<? extends Number> upper;

        public <E extends Exception> List<? super T> transform(
                List<? extends T> input, E problem) throws E {
            throw problem;
        }
    }

    static final class Child extends Parent<String>
            implements Source<String, List<Integer>>, Serializable {

        @Override
        public List<Integer> get(String key) {
            return List.of(key.length());
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<Child> clazz = Child.class;

        Type superclass = clazz.getGenericSuperclass();
        ParameterizedType parentType =
                (ParameterizedType) superclass;

        System.out.println(
                "erasedSuperclass=" +
                clazz.getSuperclass().getSimpleName()
        );
        System.out.println(
                "genericSuperclass=" +
                (superclass instanceof ParameterizedType)
        );
        System.out.println(
                "superRaw=" +
                ((Class<?>) parentType.getRawType()).getSimpleName()
        );
        System.out.println(
                "superArg=" +
                parentType.getActualTypeArguments()[0].getTypeName()
        );

        Type[] interfaces = clazz.getGenericInterfaces();
        System.out.println(
                "interfaces=" + interfaces.length
        );

        ParameterizedType source =
                (ParameterizedType) interfaces[0];

        System.out.println(
                "sourceRaw=" +
                ((Class<?>) source.getRawType()).getSimpleName()
        );
        System.out.println(
                "sourceKey=" +
                source.getActualTypeArguments()[0].getTypeName()
        );
        System.out.println(
                "sourceValueNested=" +
                (source.getActualTypeArguments()[1]
                        instanceof ParameterizedType)
        );
        System.out.println(
                "markerClass=" +
                (interfaces[1] instanceof Class<?>)
        );

        System.out.println(
                "declaredT=" +
                Parent.class.getTypeParameters()[0].getName()
        );

        Field item = Parent.class.getDeclaredField("item");
        Field items = Parent.class.getDeclaredField("items");
        Field buffer = Parent.class.getDeclaredField("buffer");
        Field upper = Parent.class.getDeclaredField("upper");

        System.out.println(
                "itemType=" + item.getGenericType().getTypeName()
        );
        System.out.println(
                "itemsType=" + items.getGenericType().getTypeName()
        );
        System.out.println(
                "arrayType=" +
                (buffer.getGenericType()
                        instanceof GenericArrayType)
        );
        System.out.println(
                "wildcard=" +
                (((ParameterizedType) upper.getGenericType())
                        .getActualTypeArguments()[0]
                        instanceof WildcardType)
        );

        Method method = Parent.class.getDeclaredMethod(
                "transform", List.class, Exception.class
        );

        System.out.println(
                "methodReturn=" +
                method.getGenericReturnType().getTypeName()
        );
        System.out.println(
                "parameter0=" +
                method.getGenericParameterTypes()[0].getTypeName()
        );
        System.out.println(
                "parameter1=" +
                method.getGenericParameterTypes()[1].getTypeName()
        );
        System.out.println(
                "exceptionType=" +
                method.getGenericExceptionTypes()[0].getTypeName()
        );
        System.out.println(
                "methodVariable=" +
                method.getTypeParameters()[0].getName()
        );

        System.out.println(
                "inheritedItemType=" +
                clazz.getField("item").getGenericType().getTypeName()
        );
        System.out.println(
                "concreteReturn=" +
                clazz.getMethod("get", String.class)
                        .getGenericReturnType().getTypeName()
        );

        long bridges = Arrays.stream(clazz.getDeclaredMethods())
                .filter(Method::isBridge)
                .count();

        System.out.println("bridges=" + bridges);
    }
}
~~~

Biên dịch ở mức ngôn ngữ Java 17:

~~~bash
javac --release 17 -Xlint:all ReflectionSignaturesDemo.java
java ReflectionSignaturesDemo
~~~

**Stdout chính xác:**

~~~text
erasedSuperclass=Parent
genericSuperclass=true
superRaw=Parent
superArg=java.lang.String
interfaces=2
sourceRaw=Source
sourceKey=java.lang.String
sourceValueNested=true
markerClass=true
declaredT=T
itemType=T
itemsType=java.util.List<T>
arrayType=true
wildcard=true
methodReturn=java.util.List<? super T>
parameter0=java.util.List<? extends T>
parameter1=E
exceptionType=E
methodVariable=E
inheritedItemType=T
concreteReturn=java.util.List<java.lang.Integer>
bridges=1
~~~

Chương trình được thiết kế để đầu ra không phụ thuộc vào tên implementation nội bộ của ParameterizedType hoặc vào thứ tự duyệt tùy ý của `getDeclaredMethods()`; chỉ **đếm** các bridge methods. Trong ví dụ, compiler tạo một bridge cho phương thức triển khai generic interface `Source<K,V>`.

### 9.1. Những điểm cần quan sát trong output

**`erasedSuperclass=Parent`**: API thông thường trả class gốc không có type argument.

**`genericSuperclass=true` và `superArg=java.lang.String`**: chữ ký superclass ở Child cho biết Parent đã được tham số hóa bằng String.

**`interfaces=2`**: Child trực tiếp triển khai Source và Serializable. Source có generic signature; Serializable là non-generic interface.

**`sourceValueNested=true`**: argument thứ hai của Source là `List<Integer>`, bản thân là ParameterizedType, không phải Class<List<Integer>> runtime.

**`itemType=T`, `itemsType=java.util.List<T>`**: field metadata giữ **cách khai báo trong Parent**, không được tự đổi thành String chỉ vì ta đi qua Child.

**`arrayType=true`**: `T[]` được Reflection mô tả bằng GenericArrayType; khác với `String[]` được biểu diễn qua Class có component type String.

**`wildcard=true`**: `List<? extends Number>` chứa WildcardType ở vị trí type argument.

**`methodReturn` và `parameter0`**: method declaration dùng wildcard theo hai chiều `? super T` và `? extends T`.

**`parameter1=E`, `exceptionType=E`, `methodVariable=E`**: generic method có một type variable E dùng trong tham số và mệnh đề throws.

**`inheritedItemType=T`**: ngay cả khi tìm inherited public field qua Child, `Field.getGenericType()` vẫn nói về khai báo Parent<T>.

**`concreteReturn=java.util.List<java.lang.Integer>`**: method `get(String)` được Child khai báo trực tiếp với kiểu trả về List<Integer>, nên Reflection đọc chính chữ ký cụ thể của method này.

**`bridges=1`**: compiler có thể sinh bridge method do type erasure để duy trì overriding/interface dispatch ở JVM. Các phương thức synthetic/bridge có thể xuất hiện trong danh sách Reflection, nhưng không nên xem bridge là một generic declaration do developer tự viết.

## 10. Field.getType và Field.getGenericType

Đây là cặp API cần phân biệt nhất khi xem chữ ký thành viên:

~~~java
Field field = Parent.class.getDeclaredField("item");

Class<?> erasedType = field.getType();
Type genericType = field.getGenericType();
~~~

Với `T item` không có bound tường minh:
- `getType()` thường trả `Object.class` do erasure.
- `getGenericType()` trả **TypeVariable T**.

Với `List<T> items`:
- `getType()` trả `List.class`.
- `getGenericType()` trả **ParameterizedType List<T>**.

Với `T[] buffer`:
- `getType()` trả array class tương ứng erasure (`Object[]` khi T không có bound).
- `getGenericType()` trả **GenericArrayType T[]**.

Bảng:

| Field declaration | `getType()` | `getGenericType()` |
| --- | --- | --- |
| `String name` | String.class | Class của String |
| `T item` | Object.class nếu T unbounded | TypeVariable T |
| `List<T> items` | List.class | ParameterizedType List<T> |
| `T[] buffer` | Object[].class nếu T unbounded | GenericArrayType T[] |
| `List<? extends Number> upper` | List.class | ParameterizedType có WildcardType |

Không nên bỏ qua `getGenericType()` nếu xây schema mapper, serializer hoặc trình đọc metadata generic. Nhưng cũng không nên dùng nó để thay thế `getType()` khi cần runtime class dùng cho `isInstance` hoặc `Class.cast`.

## 11. Method.getReturnType và getGenericReturnType

Với:

~~~java
public <E extends Exception> List<? super T> transform(
        List<? extends T> input, E problem) throws E
~~~

`Method.getReturnType()` cho biết class của return type sau erasure: `List.class`.

`Method.getGenericReturnType()` cho biết kiểu khai báo đầy đủ:

~~~text
java.util.List<? super T>
~~~

Đọc phương thức:

~~~java
Method method = Parent.class.getDeclaredMethod(
        "transform", List.class, Exception.class
);

Type genericReturn = method.getGenericReturnType();
Class<?> erasedReturn = method.getReturnType();
~~~

Chú ý cách tìm `getDeclaredMethod`: tham số truyền vào là các **`Class<?>` theo erased parameter types**, không phải các `Type` đại diện cho `List<? extends T>` hoặc E.

Ở đây:
- `List<? extends T>` bị xóa về List;
- `E extends Exception` bị xóa về Exception;
- vì thế Java Reflection lookup dùng `List.class, Exception.class`.

Nếu nhầm truyền `Object.class` cho E hoặc `ArrayList.class` thay vì List, `getDeclaredMethod` có thể ném NoSuchMethodException do lookup đòi đúng **erased formal parameter types**.

### 11.1. Void và primitive return types

`Method.getGenericReturnType()` không có nghĩa mọi method trả ParameterizedType. Nếu method trả `void`, `int` hoặc `String`, Type tương ứng có thể được biểu diễn qua một `Class<?>` thích hợp. Luôn kiểm tra dạng Type trước khi cast.

## 12. getGenericParameterTypes và getGenericExceptionTypes

Phương thức:

~~~java
Method method = Parent.class.getDeclaredMethod(
        "transform", List.class, Exception.class
);
~~~

có:
- `getParameterTypes()`: các Class<?> đã xóa generic (`List.class`, `Exception.class`).
- `getGenericParameterTypes()`: `List<? extends T>` và `E`.
- `getExceptionTypes()`: các Class<?> trong mệnh đề throws sau erasure.
- `getGenericExceptionTypes()`: `E` dưới dạng TypeVariable.

Ví dụ:

~~~java
Type[] parameters = method.getGenericParameterTypes();
Type[] exceptions = method.getGenericExceptionTypes();

for (Type parameter : parameters) {
    System.out.println(parameter.getTypeName());
}
for (Type exceptionType : exceptions) {
    System.out.println(exceptionType.getTypeName());
}
~~~

Chữ ký generic giúp đọc **mối liên hệ giữa E trong tham số và E trong throws**. Chỉ xem `getExceptionTypes()` thường thấy bound Exception, không biết cả hai vị trí gắn cùng type variable E.

### 12.1. Type parameter của method khác type parameter của class

Đừng lấy `Parent.class.getTypeParameters()` rồi kết luận đã tìm được E. E được khai báo ở method `transform`, nên phải đọc:

~~~java
TypeVariable<Method>[] variables = method.getTypeParameters();
~~~

Trong khi T thuộc class Parent nên lấy qua `Parent.class.getTypeParameters()`. Hai variable có phạm vi khai báo khác nhau và có thể trùng tên nếu người viết source cố tình đặt như vậy ở những declarations khác nhau.

## 13. Declared members và inherited members

Đây là một nguồn lỗi lớn khi duyệt Reflection.

**Các API declared**:
- `getDeclaredFields()`, `getDeclaredField(name)`;
- `getDeclaredMethods()`, `getDeclaredMethod(name, parameterTypes...)`;
- `getDeclaredConstructors()`.

Chúng xét thành viên **được khai báo trực tiếp bởi class/interface được phản chiếu**, gồm cả những visibility khác nhau trong phạm vi API. Chúng không mặc định đi lên superclass để trả các thành viên được kế thừa.

**Các API public/inherited**:
- `getFields()`, `getField(name)`;
- `getMethods()`, `getMethod(name, parameterTypes...)`.

Chúng có thể thấy public members kế thừa và công khai, theo hợp đồng từng API.

Với `Child extends Parent<String>`:
- `Child.class.getDeclaredField("item")` thất bại nếu Child không tự khai báo field item;
- `Child.class.getField("item")` có thể tìm được public field item trong Parent;
- Field trả về có `getDeclaringClass() == Parent.class`;
- `getGenericType()` của Field ấy vẫn mô tả **T** như được viết ở Parent.

Bởi vậy, cách duyệt inherited fields rồi đếm các type variables xuất hiện trong metadata không tự trả một schema đầy đủ đã được specialize theo Child.

### 13.1. Duyệt class hierarchy khác duyệt declared fields

Để ghi một report đầy đủ, có thể duyệt các lớp cha theo `getSuperclass()` hoặc `getGenericSuperclass()`, rồi đọc `getDeclaredFields()` ở từng lớp. Nếu cần giữ kiểu thực tế của Child, phải lưu một **mapping các type variables → actual type arguments** khi đi qua generic superclass edges.

Cần xử lý cả shadowing, override, static fields, visibility, bridge methods và interfaces nếu thực sự xây type resolver production. Bài này tập trung vào cách đọc đúng metadata và phát hiện lúc nào cần bước resolution bổ sung.

## 14. Bẫy quan trọng: getGenericType trên field kế thừa vẫn là T

Với:

~~~java
class Parent<T> {
    public T item;
}

class Child extends Parent<String> {}
~~~

Không nên kỳ vọng:

~~~java
Type type = Child.class.getField("item").getGenericType();
// Không phải lúc nào cũng trả String; ở đây trả T.
~~~

Vì sao?

1. Field `item` được **khai báo** trong Parent<T>.
2. Reflection object `Field` đại diện cho **chính declaration đó**, không phải một bản field mới được compiler sinh cho mỗi subclass.
3. `Child extends Parent<String>` chứa quan hệ T→String trên **generic superclass edge**.
4. `Field.getGenericType()` đọc **chữ ký field gốc** trong Parent, nên biểu diễn T.
5. Muốn suy ra kiểu field trong **ngữ cảnh Child**, phải áp dụng mapping T→String vào Type của field.

Sơ đồ:

~~~text
Child
  extends Parent<String>
              │
              └── Parent<T> khai báo field T item
                             │
                             ▼
                       getGenericType() = T
                             │
               thay T bằng String trong ngữ cảnh Child
                             │
                             ▼
                 resolved contextual type = String
~~~

**Không nhầm type declaration với contextual resolved type.** Chính sự khác biệt đó giải thích vì sao những thư viện như type token utilities hoặc JSON binders cần logic giải generic supertypes thay vì chỉ gọi một API Reflection đơn lẻ.

## 15. Phác thảo thuật toán giải type variable theo ngữ cảnh

Muốn tìm “trong Child, field Parent.item có kiểu gì?”, có thể làm như sau:

1. Bắt đầu từ `Child.class` cùng một môi trường mapping rỗng.
2. Đọc `Child.getGenericSuperclass()`: `Parent<String>`.
3. Lấy raw type Parent, khai báo type parameters của nó: `Parent.class.getTypeParameters()` cho `T`.
4. Ghép từng type parameter với actual argument tương ứng từ ParameterizedType, tạo mapping `T → String`.
5. Đọc `Parent.class.getDeclaredField("item").getGenericType()` cho T.
6. Thay T bằng giá trị mapped là String.
7. Nếu type là `List<T>`, thay **bên trong** ParameterizedType để thành `List<String>` về mặt mô tả ngữ cảnh.
8. Nếu type là `T[]`, wildcard hoặc nested generic, đi sâu vào các thành phần để thay biến kiểu thích hợp.
9. Nếu superclass nhiều cấp có type variables khác, cần lặp và **compose mappings**, không chỉ giải ở một cạnh.
10. Nếu gặp `TypeVariable` không có mapping (hoặc có wildcard, owner types...), giữ thông tin chưa biết đúng ngữ nghĩa thay vì ép về Object một cách tùy tiện.

Ví dụ nhiều tầng:

~~~java
class Base<T> {
    T value;
}

class Middle<U> extends Base<List<U>> {}

class FinalChild extends Middle<String> {}
~~~

Suy luận trong ngữ cảnh FinalChild:

~~~text
Middle<U> nhận U = String
Base<T> nhận T = List<U>
Thay U = String
=> T = List<String>
=> Base.value là List<String> theo ngữ cảnh FinalChild
~~~

`Base.class.getDeclaredField("value").getGenericType()` vẫn trả **T**, trong khi kết quả contextual resolution dự kiến là `List<String>`.

**Đây là mô hình thuật toán**, không phải lời hứa rằng JDK cung cấp sẵn một nút `resolveEverything()` cho mọi cấu trúc kiểu. Viết một Type resolver tổng quát cần xử lý `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`, owner types, interfaces, bounds và các trường hợp đặc biệt.

## 16. Bridge methods do compiler sinh ra

Khi class triển khai generic interface:

~~~java
interface Source<K, V> {
    V get(K key);
}

final class Child implements Source<String, List<Integer>> {
    @Override
    public List<Integer> get(String key) {
        return List.of(key.length());
    }
}
~~~

Sau erasure, interface method có dạng tương thích `Object get(Object)` trong bytecode, trong khi implementation source có `List<Integer> get(String)`. Compiler có thể tạo **bridge method** để bảo toàn cơ chế override/dispatch sau erasure.

Reflection có các API:
- `method.isBridge()`: có phải bridge method?
- `method.isSynthetic()`: có phải method compiler-generated synthetic?
- `method.getGenericReturnType()`: chữ ký kiểu của chính method được Reflection object đó đại diện.

Nếu in tất cả `Child.class.getDeclaredMethods()` mà không lọc, có thể thấy:
- method thực `get(String)` với generic return `List<Integer>`;
- bridge method với signature đã erasure như `get(Object)`.

Đừng tính bridge như một API nghiệp vụ mới do developer tự khai báo, và đừng để nó làm trùng entry khi xây tài liệu method signatures. Trong ví dụ hoàn chỉnh, `isBridge()` phát hiện **một** bridge method.

### 16.1. Kiểm tra bytecode

Dùng:

~~~bash
javap -p -c ReflectionSignaturesDemo
javap -p -v 'ReflectionSignaturesDemo$Child'
~~~

Trên shell cần quote `$` phù hợp; ví dụ lệnh thứ hai dùng cú pháp single quote phổ biến của Bash. Trong Windows PowerShell, cũng có thể dùng single quote để ngăn nội suy biến. Chú ý không dùng tên class chung chung `Child` khi nó là nested type; binary name chứa `$`.

Trong output bytecode, các attributes liên quan có thể gồm:
- `Signature`: metadata chữ ký generic;
- `ACC_BRIDGE` và `ACC_SYNTHETIC` cho bridge method;
- các descriptors đã erasure.

`javap -v` hữu ích để đối chiếu **bytecode descriptor** với **generic signature**; số offset cụ thể và thứ tự methods không phải thứ để phụ thuộc.

## 17. Constructor và ParameterizedType của thành viên khác

Chủ đề chữ ký thành viên không chỉ gồm field/method.

`Constructor<?>` có thể cung cấp:
- `getGenericParameterTypes()`;
- `getGenericExceptionTypes()`;
- `getTypeParameters()`;
- `getAnnotatedParameterTypes()` khi quan tâm type-use annotations.

Ví dụ constructor generic:

~~~java
class Factory {
    <X extends Number> Factory(X value) {
        System.out.println(value);
    }
}
~~~

Khi introspect, `getTypeParameters()` của constructor có thể cho X. Một constructor generic **không** khiến cả class Factory trở thành generic class.

Cần phân biệt:
- Type parameters **của class** từ `Class.getTypeParameters()`.
- Type parameters **của method** từ `Method.getTypeParameters()`.
- Type parameters **của constructor** từ `Constructor.getTypeParameters()`.

Với **non-static inner class constructors**, JVM có thể thêm tham số enclosing instance vào bytecode và cách Reflection báo parameters có các điểm tinh tế; khi viết một analyzer production cần hiểu synthetic/mandated parameters thay vì chỉ nhìn source count.

Đối với type-use annotations (ví dụ annotation trên type arguments), `getAnnotatedType` và họ `getAnnotatedReturnType` / `getAnnotatedParameterTypes` bổ sung góc nhìn về annotation metadata. Nhưng các API `getGeneric*` chủ yếu cung cấp **cấu trúc Type**, không phải toàn bộ annotation metadata.

## 18. Type erasure: generic metadata không thay thế kiểm tra runtime

Khi viết:

~~~java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
~~~

hai đối tượng `ArrayList` không trở thành hai runtime classes khác nhau theo type argument:

~~~java
boolean sameClass = names.getClass() == numbers.getClass();
~~~

Kết quả là true với hai đối tượng ArrayList được tạo như trên. Reflection gọi `names.getClass()` chỉ thấy runtime class ArrayList, không thể tự suy ra `String` từ biến source đã giữ đối tượng này.

Trong khi đó:

~~~java
Field f = SomeHolder.class.getDeclaredField("names");
Type declared = f.getGenericType();
~~~

nếu `SomeHolder` khai báo trường `List<String> names;` thì Reflection có thể đọc metadata `List<String>` từ **khai báo field**. Đó là sự khác biệt:
- **Object reflection**: object runtime có class, không mang mọi generic arguments.
- **Declaration reflection**: class file có thể ghi generic signature của field/method/supertype đã viết trong source.

Bản thân việc đọc `List<String>` từ metadata không phải validation:
- Không xác minh mọi phần tử trong list.
- Không chữa lỗi heap pollution do raw/unchecked aliases.
- Không tự xây schema đầy đủ nếu chữ ký chứa TypeVariable chưa giải.

Nếu muốn xử lý JSON, payload API hoặc dữ liệu không tin cậy theo `List<String>`, vẫn cần kiểm tra/copy dữ liệu hoặc dùng library binding có quy tắc runtime validation rõ ràng.

## 19. Chỗ nào Type.getTypeName() hữu ích, chỗ nào không đủ?

`Type.getTypeName()` cho ra tên dễ đọc, rất thích hợp cho logging và chẩn đoán:

~~~java
Type type = Parent.class.getDeclaredField("items").getGenericType();
System.out.println(type.getTypeName()); // java.util.List<T>
~~~

Nhưng một ứng dụng cần **phân tích cấu trúc** không nên dựa vào chuỗi này làm cách duy nhất để:
- đếm type arguments;
- so khớp type variables qua ngữ cảnh;
- đọc owner type;
- xác định wildcard upper/lower bounds;
- phát hiện generic array component;
- gắn type-use annotations.

Những thao tác đó nên dùng các interfaces Reflection và truy cập thành phần qua methods chính thức. String representation thích hợp để **hiển thị**, không phải parser thay thế AST Type trong các hệ thống cần độ chính xác.

### 19.1. Tránh suy ra quá nhiều từ tên Type implementation

Một lời gọi `type.getClass().getName()` có thể cho tên lớp nội bộ của JDK. Những tên này không phải hợp đồng Java Reflection cấp cao. Viết:

~~~java
if (type instanceof ParameterizedType p) {
    // Sử dụng p.getActualTypeArguments(), p.getRawType(), ...
}
~~~

thường bền vững hơn việc so sánh tên `sun.reflect...` hoặc một tên class nội bộ khác.

## 20. Những lỗi thường gặp

### Lỗi A — dùng getSuperclass để lấy type arguments

~~~java
Class<?> parent = Child.class.getSuperclass();
// parent không chứa String như một actual type argument.
~~~

**Sửa:** dùng `getGenericSuperclass()` và phân loại Type; khi nhận ParameterizedType thì đọc `getActualTypeArguments()`.

### Lỗi B — cast mọi getGenericSuperclass thành ParameterizedType

~~~java
// ParameterizedType p =
//     (ParameterizedType) SomeClass.class.getGenericSuperclass();
~~~

**Sai khi** superclass không generic, dùng raw superclass hoặc không có superclass tương ứng. Kiểm tra `instanceof ParameterizedType` và null trước.

### Lỗi C — nghĩ getGenericInterfaces tự trả interfaces được kế thừa gián tiếp

`getGenericInterfaces()` phản ánh **direct interfaces**. Nếu class kế thừa implementation từ parent, phải duyệt hierarchy đúng cách để lấy toàn bộ giao diện liên quan.

### Lỗi D — nghĩ mọi actual type argument là Class

Với `Source<String,List<Integer>>`, argument thứ hai là ParameterizedType, không phải một Class<List<Integer>>. Với `List<? extends Number>`, argument là WildcardType; với `List<T>`, argument là TypeVariable.

### Lỗi E — nghĩ Child.getField("item").getGenericType trả String

Trong ví dụ Parent<T>/Child extends Parent<String>, Field đại diện declaration ở Parent, nên vẫn trả T. Cần contextual substitution T→String từ generic superclass edge.

### Lỗi F — tìm method bằng generic parameterized Type

`getDeclaredMethod` nhận các Class<?> theo **erased parameter types**, không nhận ParameterizedType. Với `transform(List<? extends T>,E)` và E extends Exception, dùng `List.class, Exception.class`.

### Lỗi G — gộp getMethods và getDeclaredMethods như thể cùng semantics

Một cái có thể bao gồm public inherited methods, cái kia chỉ gồm members declared trực tiếp. Khi build analyzer, phải chọn đúng phạm vi, xử lý override và bridge/synthetic members.

### Lỗi H — dùng TypeVariable.getName làm định danh duy nhất

Nhiều khai báo khác nhau cùng dùng `T`. Cần xét `getGenericDeclaration()` và binding context, không chỉ chuỗi ký tự T.

### Lỗi I — đọc T[] như một Class array có component T runtime

`T[]` có thể được phản chiếu bằng GenericArrayType; erasure có thể thành Object[]. Không có runtime class riêng T[] cho mỗi generic instantiation.

### Lỗi J — xem generic metadata như dữ liệu runtime đáng tin

Một field được khai báo `List<String>` không ngăn code raw/unchecked làm hỏng nội dung tại runtime. Reflection không thực hiện validation toàn bộ phần tử.

### Lỗi K — quên các synthetic/bridge methods

Compiler có thể sinh bridge methods để duy trì overriding generic sau erasure. Không nên xuất báo cáo API có phương thức trùng mà không xét `isBridge()`, `isSynthetic()` và declaring class.

### Lỗi L — không nghĩ đến giới hạn generic signature thực tế

Một số class được sinh bytecode bằng công cụ khác hoặc bị loại generic signature có thể khiến thông tin Reflection không đầy đủ hoặc không thể giải như mong muốn. Nếu đang phân tích class ngoài dự án, cần chiến lược fallback và xử lý exceptions phù hợp.

## 21. Checklist khi đọc chữ ký generic trong dự án

1. Xác nhận `Class<?>` cần phân tích là class/interface nào và có đúng classloader không.
2. Dùng `getGenericSuperclass()` để đọc edge **extends trực tiếp**; kiểm tra null, Class hoặc ParameterizedType.
3. Dùng `getGenericInterfaces()` để đọc edges **implements/extends interface trực tiếp**; không bỏ các interface non-generic.
4. Nếu Type là ParameterizedType, đọc `getRawType()`, `getActualTypeArguments()` và `getOwnerType()` khi phù hợp.
5. Nếu Type là TypeVariable, xem `getName()`, `getBounds()`, `getGenericDeclaration()`.
6. Nếu Type là WildcardType, xem `getUpperBounds()` và `getLowerBounds()`.
7. Nếu Type là GenericArrayType, đi vào `getGenericComponentType()`.
8. Dùng `Field.getGenericType()` để đọc khai báo field; đối chiếu `Field.getType()` khi cần erasure.
9. Dùng `Method.getGenericReturnType()`, `getGenericParameterTypes()` và `getGenericExceptionTypes()` cho chữ ký method.
10. Nếu cần type parameters của riêng method/constructor, dùng `getTypeParameters()` đúng đối tượng khai báo.
11. Khi phân tích members inherited, xét `getDeclaringClass()` rồi giải context mapping từ subclass đến declaring class.
12. Lọc hoặc phân loại bridge/synthetic methods nếu mục tiêu là tài liệu API do developer viết.
13. Kiểm tra generic signature là **declaration metadata**, không phải runtime validation của mọi object.
14. Không dựng parser dựa trên `getTypeName()` nếu đã có Type interfaces để điều hướng cấu trúc.
15. Khi xử lý bytecode phức tạp, cân nhắc missing types, classloader boundaries và malformed signatures thay vì assume mọi Type đều tải được.
16. Viết bài kiểm thử cho `List<T>`, nested `Map<String,List<Integer>>`, `T[]`, `? extends`, `? super`, inherited T substitution và generic method throws E.

## 22. Câu hỏi tự kiểm tra

**1.** `Child extends Parent<String>`. API nào cho biết type argument String của superclass?

**Đáp án:** `Child.class.getGenericSuperclass()`; nếu kết quả là ParameterizedType thì đọc `getActualTypeArguments()[0]`.

**2.** Vì sao `getSuperclass()` không trả ParameterizedType?

**Đáp án:** `getSuperclass()` có kiểu trả về Class<?> và chỉ cung cấp runtime class của superclass; generic arguments không được mã hóa vào giá trị Class đó.

**3.** `getGenericInterfaces()` trả tất cả inherited interfaces hay trực tiếp?

**Đáp án:** Các direct interfaces được class/interface khai báo. Muốn toàn bộ hierarchy, phải duyệt tiếp superclass và interfaces.

**4.** Với `Source<String,List<Integer>>`, type argument thứ hai là dạng gì?

**Đáp án:** ParameterizedType của List<Integer>, không phải Class<List<Integer>>.

**5.** Với `Parent<T>` có field `T item`, `getGenericType()` cho biết gì?

**Đáp án:** TypeVariable T của declaration Parent, trong khi `getType()` có thể trả Object.class sau erasure nếu T unbounded.

**6.** Vì sao `Child.class.getField("item").getGenericType()` vẫn là T?

**Đáp án:** Field object mô tả declaration ở Parent<T>. Quan hệ T→String được lưu trên generic superclass edge của Child và phải được áp dụng riêng khi giải contextual type.

**7.** Với `T[] buffer`, Reflection có thể biểu diễn generic type bằng interface nào?

**Đáp án:** GenericArrayType; có thể đọc `getGenericComponentType()` để lấy TypeVariable T.

**8.** Với `List<? extends Number>`, làm sao đọc Number?

**Đáp án:** Lấy Field.getGenericType() dưới dạng ParameterizedType; type argument là WildcardType; đọc `getUpperBounds()`.

**9.** `getDeclaredMethod("transform", List.class, Exception.class)` dùng hai Class vì sao?

**Đáp án:** Lookup bằng erased formal parameter types, không phải generic Type objects của `List<? extends T>` và `E`.

**10.** `method.getGenericExceptionTypes()` trả E hay Exception trong ví dụ transform?

**Đáp án:** E dưới dạng TypeVariable, còn `getExceptionTypes()` phản ánh class sau erasure tương ứng Exception.

**11.** TypeVariable T và TypeVariable E khác nhau ở đâu?

**Đáp án:** T thuộc generic class Parent, E thuộc generic method transform. `getGenericDeclaration()` cho biết declaration chứa mỗi biến.

**12.** Một bridge method có thể xuất hiện dù không có trong source code không?

**Đáp án:** Có. Compiler có thể tạo bridge sau erasure để duy trì overriding và polymorphism, phát hiện bằng `isBridge()`.

**13.** Chỉ có Type object của `List<String>` thì đã xác minh được mọi phần tử của List runtime là String chưa?

**Đáp án:** Chưa. Type là metadata mô tả khai báo; vẫn cần kiểm tra dữ liệu hoặc đảm bảo bất biến qua API được tin cậy.

**14.** `getTypeName()` có nên được parse bằng regex để giải mọi generic type không?

**Đáp án:** Không. Nó thích hợp để hiển thị; dùng Type interfaces và methods chính thức để phân tích cấu trúc, đặc biệt nested types, wildcards và type variables.

**15.** Để suy ra Base.value thành List<String> trong `FinalChild extends Middle<String>` và `Middle<U> extends Base<List<U>>` cần bước gì?

**Đáp án:** Compose mappings qua các superclass edges: U→String, T→List<U>, rồi thay U để có T→List<String>. `Field.getGenericType()` đơn lẻ chỉ cho declaration T.

## 23. Ghi nhớ

**Java Reflection có thể đọc được generic signatures của superclass, interfaces và members nhưng không tự khôi phục toàn bộ type arguments của mọi runtime instance.**

Ba bước quan trọng nhất:

~~~text
Class<?> cần phân tích
    │
    ├── getGenericSuperclass() → Type của superclass trực tiếp
    │
    ├── getGenericInterfaces() → Type[] của direct interfaces
    │
    └── declared/inherited member
            ├── Field.getGenericType()
            ├── Method.getGenericReturnType()
            ├── Method.getGenericParameterTypes()
            └── Method.getGenericExceptionTypes()
~~~

Sau đó **phân loại Type** thành `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType` hoặc `GenericArrayType` để điều hướng tiếp.

Nếu cần xem kiểu thành viên trong **ngữ cảnh subclass**, hãy nhớ rằng Reflection trả **chữ ký tại nơi member được khai báo**: `Parent<T>.item` vẫn là T, dù `Child extends Parent<String>`. Muốn có String theo ngữ cảnh Child, phải thực hiện type-variable substitution theo hierarchy.

Cuối cùng, đừng nhầm **metadata generic trong class file** với **kiểm tra runtime của object**. Hiểu đúng sự khác biệt đó là nền tảng để sử dụng Reflection trong serializers, object mappers, dependency injection containers, API analyzers và các công cụ Java Generics.
