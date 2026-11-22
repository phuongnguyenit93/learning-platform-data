# Phân biệt `java.lang.reflect.Type` với `Class<?>` trong Java Generics

Khi làm việc với **reflection** và **Java Generics**, hai kiểu `java.lang.reflect.Type` và `Class<?>` rất dễ bị nhầm vì cả hai đều có thể biểu diễn “kiểu”. Nhưng chúng phục vụ các nhu cầu khác nhau:

- **`Class<?>`** là đối tượng `Class` đại diện cho một **class, interface, enum, record, annotation, array hoặc primitive type cụ thể được JVM nhận biết** (cùng trường hợp `void.class` đặc biệt). Nó phù hợp khi cần kiểm tra runtime class, lấy constructor/method/field, tạo instance theo cơ chế cho phép, hoặc gọi `isInstance`/`cast`.
- **`Type`** là một **interface tổng quát dùng để mô tả cấu trúc kiểu Java** trong reflection. Nó bao trùm `Class` và những kiểu không thể biểu diễn bằng một runtime class đơn lẻ, chẳng hạn `List<String>`, `Map<String, List<Integer>>`, type variable `T`, wildcard `? extends Number` và generic array `T[]`.

Quan hệ quan trọng nhất:

```java
import java.lang.reflect.Type;

Type a = String.class; // Hợp lệ: Class<?> triển khai Type
Class<?> b = String.class;

// Type c = ...;
// Class<?> d = c; // Không luôn hợp lệ: Type có nhiều dạng khác Class
```

**Mọi đối tượng `Class<?>` là một `Type`, nhưng không phải mọi `Type` là `Class<?>`.** Với generic type arguments cụ thể, đối tượng reflection thường là `ParameterizedType`, không phải `Class`.

## 1. Bức tranh tổng thể: `Type` là abstraction, `Class` là một nhánh

Gói `java.lang.reflect` cung cấp interface `Type` và các interface con để mô tả kiểu:

```text
java.lang.reflect.Type
    |
    +-- java.lang.Class<?>                 (Class triển khai Type)
    |
    +-- java.lang.reflect.ParameterizedType
    |
    +-- java.lang.reflect.TypeVariable<D>
    |
    +-- java.lang.reflect.WildcardType
    |
    +-- java.lang.reflect.GenericArrayType
```

Đây là sơ đồ **phân loại các đối tượng reflection phổ biến** chứ không có ý nói `Class` là interface. `Class<T>` là một class của Java, triển khai interface `Type`; các kiểu `ParameterizedType`, `WildcardType` và những mục khác là interface có thể có implementation riêng của JVM/thư viện.

Ví dụ:

```java
Type primitive = int.class;        // Đối tượng Class
Type simple = String.class;        // Đối tượng Class
Type rawList = java.util.List.class; // Đối tượng Class

// List<String> không có class literal dạng:
// Type generic = List<String>.class; // KHÔNG BIÊN DỊCH
```

`List.class` mô tả runtime interface `List`, **không** chứa `String` của `List<String>`. Nếu bạn cần mô tả một kiểu tham số hóa đầy đủ, hãy lấy `Type` từ một khai báo generic bằng reflection hoặc từ cấu trúc type token phù hợp.

## 2. Bảng so sánh nhanh

| Khía cạnh | `Class<?>` | `Type` |
| --- | --- | --- |
| Bản chất | Đối tượng `Class` do JVM cung cấp; `Class<T>` là generic class | Interface chung biểu diễn kiểu |
| Quan hệ | `Class` triển khai `Type` | Có thể giữ `Class` hoặc các dạng type khác |
| `String.class` | Có | Có, vì đó cũng là một `Type` |
| `List.class` | Có: runtime interface `List` | Có |
| `List<String>` | Không có `List<String>.class` | Biểu diễn qua `ParameterizedType` trong ngữ cảnh có metadata |
| Type variable `T` | Không có `T.class` thông thường | Có thể biểu diễn qua `TypeVariable` |
| Wildcard `? extends Number` | Không có `?.class` | Có thể biểu diễn qua `WildcardType` |
| `T[]` trong khai báo generic | Không có `T[].class` để giữ type variable | Có thể biểu diễn qua `GenericArrayType` |
| Kiểm tra đối tượng runtime | Có `isInstance`, `cast`, `isAssignableFrom` | `Type` không khai báo trực tiếp các phương thức ấy |
| Truy cập cấu trúc generic | Không chứa đầy đủ generic type arguments của instance | Có thể thông qua các interface con và metadata khai báo |
| Công dụng thường gặp | Runtime type token, reflection trên class, cast/kiểm tra class | Đọc chữ ký generic, schema, serializer, binder, framework |

**`Class<?>` không phải raw `Class`.** Nó là một kiểu tham số hóa với wildcard chưa biết class được đại diện. Ví dụ `Class<String>` có thông tin kiểu tĩnh cụ thể hơn `Class<?>`, còn `Class<?> unknown = String.class` vẫn là khai báo generic có kiểm tra kiểu.

## 3. Vì sao `Class<?>` không biểu diễn được `List<String>`?

Java Generics thông thường dùng **type erasure**. Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

List<String> words = new ArrayList<>();
List<Integer> counts = new ArrayList<>();

boolean same = words.getClass() == counts.getClass(); // true
```

Đây là hai **instance của cùng runtime class `ArrayList`**. `getClass()` trả `Class` của object thực, nên không tạo hai `Class` riêng mang tên `ArrayList<String>` và `ArrayList<Integer>`.

Không có cú pháp:

```java
// KHÔNG BIÊN DỊCH:
Class<List<String>> token = List<String>.class;
```

Cũng không thể dùng:

```java
// KHÔNG phải đường giải quyết:
// Class.forName("java.util.List<java.lang.String>");
```

`Class.forName` dùng tên class/interface có thể được JVM tải theo hợp đồng của API, không phân tích một chuỗi tên type generic để tạo runtime class chuyên biệt `List<String>`.

Với một giá trị không biết trước:

```java
Object value = List.of("Java");

// Hợp lệ:
boolean list = value instanceof List<?>;

// Không hợp lệ khi value có kiểu tĩnh Object:
// boolean stringList = value instanceof List<String>;
```

`List<?>` chỉ xác minh đối tượng bên ngoài là `List`. Nó **không** kiểm tra mọi phần tử là `String`.

**Kết luận:** một `Class<?> listClass` có thể mô tả `List.class`; muốn mô tả khai báo `List<String>`, phải dùng một `Type` thuộc dạng phù hợp, nhưng dữ liệu `Type` ấy **vẫn không tự bảo đảm** nội dung list runtime đúng kiểu.

## 4. `Field.getType()` so với `Field.getGenericType()`

Một trường khai báo kiểu generic có thể có thông tin khai báo lưu trong metadata của class file. Reflection cung cấp hai lối đọc:

```java
import java.util.List;

class Example {
    List<String> names;
}
```

Với trường `names`:

```java
java.lang.reflect.Field field =
        Example.class.getDeclaredField("names");

Class<?> erased = field.getType();
java.lang.reflect.Type declared = field.getGenericType();

System.out.println(erased.getTypeName());
System.out.println(declared.getTypeName());
```

Đầu ra:

```text
java.util.List
java.util.List<java.lang.String>
```

`getType()` trả `Class<?>` của **kiểu trường ở dạng runtime/erasure**: `List`. `getGenericType()` trả `Type` diễn đạt **kiểu trường được khai báo**: `List<String>`, thường có dạng `ParameterizedType`.

Không nên hiểu `getGenericType()` là “đọc nội dung object đang nằm trong field và xác định mọi phần tử”. Đây là **metadata của khai báo**, không phải phép kiểm tra collection tại runtime.

### Cùng trường, hai góc nhìn

Nếu class generic có:

```java
class NumericHolder<T extends Number> {
    T number;
}
```

thì:

- `numberField.getType()` trả `Class` tương ứng erasure của `T`, tức `Number.class`.
- `numberField.getGenericType()` có thể trả `TypeVariable` đại diện cho `T`, với bound `Number`.

Vì vậy ngay cả khi không thấy dấu `<String>` trong một chữ ký, `getGenericType()` vẫn có thể khác `getType()`: type variable, wildcard và generic array đều là những trường hợp hữu ích.

## 5. `ParameterizedType`: đọc các đối số kiểu cụ thể

Khi reflection nhìn thấy một khai báo như `List<String>` hoặc `Map<String, List<Integer>>`, `Type` tương ứng thường là `ParameterizedType`.

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

Type t = Example.class.getDeclaredField("names").getGenericType();

if (t instanceof ParameterizedType p) {
    Type raw = p.getRawType();
    Type[] args = p.getActualTypeArguments();

    System.out.println(raw.getTypeName());
    System.out.println(args[0].getTypeName());
}
```

Ví dụ `List<String>` cho:

```text
java.util.List
java.lang.String
```

Ba phương thức chính:

- **`getRawType()`**: trả kiểu gốc, ví dụ `java.util.List`. Chữ ký của nó trả `Type`; trên một generic class/interface bình thường, object thực thường là `Class`.
- **`getActualTypeArguments()`**: trả mảng `Type[]` cho type arguments tại khai báo; mỗi phần tử **có thể là `Class`, `ParameterizedType`, `WildcardType` hoặc `TypeVariable`**, không được cast hết về `Class`.
- **`getOwnerType()`**: mô tả owner type của kiểu nested khi có quan hệ owner phù hợp; hữu ích cho các khai báo lớp lồng nhau.

Ví dụ với `Map<String, List<Integer>>`:

```text
Map<String, List<Integer>>
    ParameterizedType(Map)
    ├── Class(String)
    └── ParameterizedType(List)
        └── Class(Integer)
```

Cần **duyệt đệ quy cấu trúc `Type`** nếu framework muốn xây schema đầy đủ. Viết `(Class<?>) args[1]` cho đối số `List<Integer>` sẽ gây `ClassCastException`, bởi đối số đó là `ParameterizedType`, không phải `Class`.

## 6. `TypeVariable`: biểu diễn `T` được khai báo ở class hoặc method

Xét:

```java
class NumberBox<T extends Number> {
    T value;
}
```

Metadata của field `value` có thể chứa `TypeVariable` tương ứng tên `T`:

```java
java.lang.reflect.Type declared =
        NumberBox.class.getDeclaredField("value").getGenericType();

if (declared instanceof java.lang.reflect.TypeVariable<?> variable) {
    System.out.println(variable.getName()); // T
    System.out.println(variable.getBounds()[0].getTypeName());
}
```

Đầu ra dòng bound:

```text
java.lang.Number
```

Các thông tin đáng chú ý:

- `getName()`: tên type variable, ví dụ `T`.
- `getBounds()`: upper bounds của type variable; nếu không ghi bound thì thường có bound ngầm `Object`.
- `getGenericDeclaration()`: class, constructor hoặc method nơi type variable được khai báo.

**Không nên tự thay `T` thành `String` chỉ vì đang giữ một `NumberBox<String>` giả định.** Thực ra `String` không thỏa bound `Number` trong ví dụ, và quan trọng hơn: `TypeVariable` nói về **khai báo `T`**, không chứa một type argument riêng cho mọi instance khi chạy. Khi có một subclass cung cấp type argument cụ thể, reflection trên `getGenericSuperclass()` có thể cung cấp thêm ngữ cảnh cần để giải quyết `T`.

Với `class Box<T>`, `new Box<String>().getClass()` bình thường vẫn trả `Class` của `Box` mà không chứa `String` như một type argument chuyên biệt.

## 7. `WildcardType`: `?`, `? extends` và `? super`

Một type argument dạng wildcard được phản chiếu qua `WildcardType`.

```java
class Bounds {
    java.util.List<? extends Number> producer;
    java.util.List<? super Integer> consumer;
}
```

Khi đọc `producer`, `Field.getGenericType()` trả một `ParameterizedType` cho `List<? extends Number>`; phần tử của `getActualTypeArguments()[0]` là **`WildcardType`**.

```java
java.lang.reflect.Type t =
        Bounds.class.getDeclaredField("producer").getGenericType();

java.lang.reflect.ParameterizedType p =
        (java.lang.reflect.ParameterizedType) t;

java.lang.reflect.WildcardType w =
        (java.lang.reflect.WildcardType) p.getActualTypeArguments()[0];

System.out.println(w.getUpperBounds()[0].getTypeName()); // java.lang.Number
```

Phương thức cần nhớ:

- `getUpperBounds()`: các upper bounds của wildcard, ví dụ `Number` trong `? extends Number`; với `? super Integer` upper bound thường là `Object`.
- `getLowerBounds()`: lower bounds, ví dụ `Integer` trong `? super Integer`; nếu không có lower bound sẽ trả mảng rỗng.

Đừng cast wildcard về `Class` chỉ vì upper bound có thể là `Number.class`. **Wildcard không phải chính upper bound**, và một framework cần giữ đúng thông tin `? extends`/`? super` trong mô hình type của nó.

## 8. `GenericArrayType` và mảng `Class`: khác nhau ở kiểu phần tử

Mảng có runtime component type reifiable như `String[]` thường được mô tả trực tiếp bằng đối tượng `Class`:

```java
Class<?> arrayClass = String[].class;
System.out.println(arrayClass.getTypeName()); // java.lang.String[]
System.out.println(arrayClass.getComponentType()); // class java.lang.String
```

Nhưng với một khai báo generic array có component type non-reifiable:

```java
class ArraysHolder<T> {
    T[] variables;
    java.util.List<String>[] lists;
    String[] strings;
}
```

Các khai báo field như `T[]` và `List<String>[]` **hợp lệ**, dù biểu thức **tạo trực tiếp** `new T[n]` hoặc `new List<String>[n]` bị Java cấm.

Reflection có thể cho:

| Field | `getType()` — kiểu erasure | `getGenericType()` — dạng type |
| --- | --- | --- |
| `T[] variables` khi `T` không bound | `Object[]` | `GenericArrayType` có component `T` |
| `List<String>[] lists` | `List[]` | `GenericArrayType` có component `List<String>` |
| `String[] strings` | `String[]` | `Class` cho `String[]` |

Nếu `T extends Number`, erasure của `T[]` là `Number[]`, không phải `Object[]`. Điều đó vẫn **không biến `T[]` thành array có thể tự tạo bằng `new T[n]`**.

Khi gặp `GenericArrayType`, dùng:

```java
if (type instanceof java.lang.reflect.GenericArrayType arrayType) {
    java.lang.reflect.Type component =
            arrayType.getGenericComponentType();
    System.out.println(component.getTypeName());
}
```

Đừng giả định mọi `Type` có tên kết thúc `[]` đều là `GenericArrayType`: `String[]` và các mảng có component type reifiable có thể là `Class`. Cần kiểm tra **dạng của object `Type`**, không đoán từ chuỗi tên.

## 9. Chương trình Java 17+ hoàn chỉnh: xem từng dạng `Type`

Lưu thành **`TypeVsClassDemo.java`**:

```java
import java.lang.reflect.*;
import java.util.*;

public class TypeVsClassDemo {
    static class Fields<T extends Number> {
        List<String> names;
        Map<String, List<Integer>> index;
        List<? extends Number> upper;
        List<? super Integer> lower;
        T[] variableArray;
        List<String>[] genericArray;
        String[] fixedArray;
        T number;

        List<T> wrap(T value) {
            return List.of(value);
        }
    }

    static abstract class TypeRef<T> {
        final Type captured;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)) {
                throw new IllegalStateException("Missing type argument");
            }
            captured = p.getActualTypeArguments()[0];
        }

        Type getType() {
            return captured;
        }
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

    static void show(String field) throws NoSuchFieldException {
        Field f = Fields.class.getDeclaredField(field);
        Type generic = f.getGenericType();

        System.out.println(field + ": "
                + f.getType().getTypeName()
                + " | " + generic.getTypeName()
                + " | " + kind(generic));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Type basic = String.class;
        System.out.println("Class is Type: "
                + (basic instanceof Class<?>));

        show("names");
        show("index");
        show("upper");
        show("lower");
        show("number");
        show("variableArray");
        show("genericArray");
        show("fixedArray");

        ParameterizedType nameType = (ParameterizedType)
                Fields.class.getDeclaredField("names")
                        .getGenericType();

        System.out.println("List raw type: "
                + nameType.getRawType().getTypeName());
        System.out.println("List argument: "
                + nameType.getActualTypeArguments()[0].getTypeName());

        TypeVariable<?> variable = (TypeVariable<?>)
                Fields.class.getDeclaredField("number")
                        .getGenericType();
        System.out.println("T bound: "
                + variable.getBounds()[0].getTypeName());

        ParameterizedType upper = (ParameterizedType)
                Fields.class.getDeclaredField("upper")
                        .getGenericType();
        WildcardType wildcard = (WildcardType)
                upper.getActualTypeArguments()[0];

        System.out.println("Wildcard upper bound: "
                + wildcard.getUpperBounds()[0].getTypeName());

        Method m = Fields.class.getDeclaredMethod(
                "wrap", Number.class);
        System.out.println("Method return: "
                + m.getReturnType().getTypeName()
                + " | " + m.getGenericReturnType().getTypeName());

        List<String> list = new ArrayList<>();
        System.out.println("Runtime list class: "
                + list.getClass().getTypeName());

        Type captured =
                new TypeRef<List<String>>() {}.getType();
        System.out.println("Captured Type: "
                + captured.getTypeName());
        System.out.println("Captured is Class: "
                + (captured instanceof Class<?>));

        System.out.println("String token check: "
                + String.class.isInstance("Java"));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 TypeVsClassDemo.java
java TypeVsClassDemo
```

Standard output:

```text
Class is Type: true
names: java.util.List | java.util.List<java.lang.String> | ParameterizedType
index: java.util.Map | java.util.Map<java.lang.String, java.util.List<java.lang.Integer>> | ParameterizedType
upper: java.util.List | java.util.List<? extends java.lang.Number> | ParameterizedType
lower: java.util.List | java.util.List<? super java.lang.Integer> | ParameterizedType
number: java.lang.Number | T | TypeVariable
variableArray: java.lang.Number[] | T[] | GenericArrayType
genericArray: java.util.List[] | java.util.List<java.lang.String>[] | GenericArrayType
fixedArray: java.lang.String[] | java.lang.String[] | Class
List raw type: java.util.List
List argument: java.lang.String
T bound: java.lang.Number
Wildcard upper bound: java.lang.Number
Method return: java.util.List | java.util.List<T>
Runtime list class: java.util.ArrayList
Captured Type: java.util.List<java.lang.String>
Captured is Class: false
String token check: true
```

Đầu ra cho thấy một số điểm dễ bị bỏ sót:

1. `Class` triển khai `Type`, vì vậy `String.class` là cả hai theo quan hệ interface.
2. Kiểu field `List<String>` được `getType()` nhìn như `List`, trong khi `getGenericType()` giữ `String` và được phân loại là `ParameterizedType`.
3. `Map<String, List<Integer>>` là một `ParameterizedType` lồng nhau; type argument thứ hai không thể cast trực tiếp thành `Class`.
4. `List<? extends Number>` và `List<? super Integer>` có **kiểu field ngoài** là `ParameterizedType`. `WildcardType` nằm **bên trong mảng type arguments**, không phải tại gốc của field.
5. `T number` là `TypeVariable`; với bound `Number`, `getType()` có erasure `Number`.
6. `T[]` và `List<String>[]` phản chiếu qua `GenericArrayType`; `String[]` lại là `Class`.
7. `Method.getReturnType()` và `Method.getGenericReturnType()` khác nhau tương tự `Field.getType()` và `Field.getGenericType()`.
8. `list.getClass()` không khôi phục `String`; anonymous subclass của `TypeRef<List<String>>` giữ được **metadata generic của superclass được khai báo**, nên cung cấp một `ParameterizedType` để thao tác.
9. `String.class.isInstance("Java")` là một **runtime class check thực sự**; một đối tượng `Type` chung không có method `isInstance` tương ứng.

## 10. `TypeRef<T>` hoạt động thế nào? Nó có “đảo ngược” erasure không?

Trong ví dụ chạy:

```java
Type captured = new TypeRef<List<String>>() {}.getType();
```

Biểu thức `new TypeRef<List<String>>() {}` tạo **một anonymous subclass** có generic superclass được khai báo là `TypeRef<List<String>>`. Reflection trên `getClass().getGenericSuperclass()` đọc **generic signature của superclass** và lấy type argument `List<String>`.

Cách tiếp cận này thường được gọi là **type token pattern** hoặc **super type token**. Nhiều thư viện serialization/binding cũng dùng một ý tưởng tương tự: bạn cung cấp type argument trong **khai báo lớp con**, từ đó framework giữ một mô tả `Type` gồm các lớp generic lồng nhau.

Nó **không** chứng minh bất kỳ `ArrayList` runtime nào có nội dung toàn `String`:

```java
List<String> normal = new ArrayList<>();
Class<?> runtime = normal.getClass(); // ArrayList.class

Type schema = new TypeRef<List<String>>() {}.getType();
// schema mô tả kiểu mong muốn, không duyệt "normal" để kiểm tra phần tử
```

Không có sự tái tạo thần kỳ của type argument đã bị erasure trên object `normal`. Type token tạo thêm **metadata từ nguồn/khai báo có chủ đích**, rồi parser/serializer phải áp dụng cấu trúc đó khi chuyển đổi hoặc xác thực dữ liệu.

Một giới hạn quan trọng: nếu bạn viết `new TypeRef<T>() {}` ở nơi `T` vẫn là type variable chưa được giải quyết, metadata có thể chỉ giữ `T`, không tự suy ra class cụ thể của mọi lời gọi. Framework muốn resolve `T` có thể cần môi trường type bindings theo class/method chứa `T`.

## 11. Cùng câu hỏi khi reflection trên method và superclass

`Field` không phải nơi duy nhất có sự khác biệt giữa runtime class và generic declaration:

| Thành phần | Dạng xóa kiểu / `Class` | Dạng generic / `Type` |
| --- | --- | --- |
| Field | `Field.getType()` | `Field.getGenericType()` |
| Method return | `Method.getReturnType()` | `Method.getGenericReturnType()` |
| Method parameters | `Method.getParameterTypes()` | `Method.getGenericParameterTypes()` |
| Constructor parameters | `Constructor.getParameterTypes()` | `Constructor.getGenericParameterTypes()` |
| Superclass | `Class.getSuperclass()` | `Class.getGenericSuperclass()` |
| Implemented interfaces | `Class.getInterfaces()` | `Class.getGenericInterfaces()` |
| Exceptions của method | `Method.getExceptionTypes()` | `Method.getGenericExceptionTypes()` |

Ví dụ:

```java
class Base<T> {}
class Child extends Base<String> {}

Class<?> superclass = Child.class.getSuperclass();
java.lang.reflect.Type genericSuperclass =
        Child.class.getGenericSuperclass();

System.out.println(superclass.getTypeName());
System.out.println(genericSuperclass.getTypeName());
```

Kết quả:

```text
Base
Base<java.lang.String>
```

Với một class trong package khác, tên đầy đủ có thể gồm tên package; trong ví dụ `Base` không có package. Chú ý `getGenericSuperclass()` ở `Child` mô tả **quan hệ kế thừa được khai báo** `extends Base<String>`, không tạo runtime class mới chuyên biệt `Base<String>`.

Đối với parameter có annotation trên type use, `AnnotatedType` và các API như `Field.getAnnotatedType()` còn cung cấp thông tin annotation liên quan type. `AnnotatedType` là cơ chế bổ sung, không phải một subtype thay thế của `Type`; khi cần mô hình kiểu lẫn type-use annotations, phải xét cả hai.

## 12. `Class<T>`, `Class<?>`, `Type`: dùng trong thiết kế API thế nào?

### 12.1. Cần một runtime class token cụ thể

```java
static <T> T checkedCast(Object value, Class<T> expected) {
    return expected.cast(value);
}

String name = checkedCast("Java", String.class);
// checkedCast(42, String.class) -> ClassCastException
```

`Class<T>.cast` kiểm tra được kiểu runtime tương ứng với một class/interface thực sự. `Class<T>` giúp compiler biết kết quả trả về là `T`.

Nếu API chỉ cần **giữ một class chưa biết**, dùng `Class<?>`:

```java
Class<?> token = Integer.class;
boolean matched = token.isInstance(42); // true
```

Wildcard `?` nói rằng compiler không biết chính xác class được token đại diện. `Class<?>` không đồng nghĩa với `Class<Object>`: token `String.class` có thể gán vào `Class<?>`, nhưng không thể tùy tiện gán vào `Class<Object>`.

### 12.2. Cần mô tả `List<String>`, `Map<String, Integer>`, `T[]`

Hãy chọn `Type` hoặc một abstraction mà thư viện hỗ trợ:

```java
Type declared = new TypeRef<List<String>>() {}.getType();
```

`Type` thích hợp làm tham số cho serializer/deserializer hay schema analyzer cần biết nested generic arguments. Nó không tự có method `cast`, `getDeclaredMethod` hoặc `newInstance` giống `Class`.

Ví dụ, nếu bạn viết:

```java
static void inspect(java.lang.reflect.Type type) {
    if (type instanceof java.lang.reflect.ParameterizedType p) {
        System.out.println(p.getRawType().getTypeName());
    } else if (type instanceof Class<?> c) {
        System.out.println(c.getName());
    }
}
```

thì việc **phân nhánh** theo dạng `Type` là cần thiết. Không cast tất cả `Type` sang `Class`.

### 12.3. API cần cả hai khả năng

Một số API cần **raw runtime class** để phân bổ object/kiểm tra và **`Type`** để mô tả schema generic. Chúng có thể yêu cầu cả hai hoặc tự phân tích `Type` để lấy raw class, nhưng việc lấy raw class từ `Type` **không phải luôn chỉ là một cast**.

Nếu một `Type` là:

- `Class<?>`: đã có class.
- `ParameterizedType`: `getRawType()` thường là class gốc của parameterized declaration.
- `GenericArrayType`: phải xử lý component type, có thể còn type variable.
- `TypeVariable`: cần bounds và môi trường type bindings.
- `WildcardType`: cần bounds và mục đích xử lý wildcard.

Với nhiều loại, không có **một** runtime class duy nhất phản ánh đầy đủ toàn bộ cấu trúc generic. Framework có thể dùng `Object.class` hoặc upper bound làm fallback cho những mục tiêu nhất định, nhưng đó là **quy tắc do framework lựa chọn**, không phải `Type` tự quy định.

## 13. Tại sao không nên chỉ dùng `getTypeName()` để xử lý generic?

Mọi `Type` đều có `getTypeName()` để tạo dạng tên dễ hiển thị, ví dụ:

```text
java.util.List<java.lang.String>
java.util.Map<java.lang.String, java.util.List<java.lang.Integer>>
T[]
```

Nhưng dùng string matching thủ công để hiểu generic type vừa dễ sai vừa làm mất thông tin cấu trúc:

- Chuỗi `Map<String,List<Integer>>` có generic lồng nhau, dấu phẩy, khoảng trắng và các dạng viết tên khác nhau.
- Wildcard có `extends`/`super` và bounds.
- Type variables có thể cùng tên `T` nhưng **khai báo ở hai scope khác nhau**; so chuỗi `"T"` không thể xác định chúng là cùng biến kiểu.
- Nested classes có owner type, và array có component type cần phân tích đúng tầng.

Đúng hơn là dùng `instanceof` với `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`, sau đó đọc **các phần tử của cấu trúc**.

Nếu cần làm key cho cache type, hãy tìm hiểu hợp đồng `equals`/`hashCode` của các biểu diễn `Type` và môi trường class loader; đừng lấy tên string làm danh tính kiểu một cách máy móc. Hai class có tên giống nhau được nạp bởi class loaders khác nhau có thể là hai runtime classes khác nhau.

## 14. Metadata generic có đủ để xác minh dữ liệu thật không?

**Không.** Giả sử reflection báo một field được khai báo `List<String>`; một chương trình có raw alias hoặc unchecked cast vẫn có thể đưa giá trị trái kiểu vào một list runtime:

```java
// Snippet CỐ Ý KHÔNG AN TOÀN:
List<String> names = new ArrayList<>();
List raw = names;
raw.add(42); // Unchecked warning; list bị sai hợp đồng String

// String value = names.get(0); // Có thể ClassCastException
```

`getGenericType()` không quét mọi phần tử và không sửa heap pollution. Nó chỉ phản ánh **hợp đồng kiểu khai báo**. Tương tự, `TypeRef<List<String>>` là schema do caller nêu ra, không phải một runtime test chứng minh nội dung object luôn đúng với schema.

Muốn xác minh một object bất kỳ thực sự là danh sách chỉ chứa `String`, có thể:

```java
static boolean allStrings(Object value) {
    if (!(value instanceof List<?> list)) {
        return false;
    }
    return list.stream().allMatch(String.class::isInstance);
}
```

Hàm này kiểm tra **đối tượng bên ngoài** qua `List<?>`, rồi xác minh **từng phần tử** bằng `String.class.isInstance`. Với danh sách rỗng, `allMatch` trả `true` theo quy tắc “mọi phần tử thỏa”; nếu cần danh sách không rỗng, kiểm tra thêm.

Ngay cả sau khi xác thực, một list mutable có alias khác vẫn có thể bị sửa. Nếu cần bảo đảm ổn định qua thời gian, hãy cân nhắc snapshot và chính sách ownership/đồng bộ phù hợp.

## 15. Lỗi phổ biến

**Lỗi 1 — “`Type` và `Class<?>` là hai loại không liên quan.”** Sai. `Class` triển khai `Type`.

**Lỗi 2 — “`Type` lúc nào cũng cast sang `Class` được.”** Sai. `List<String>` phản chiếu thành `ParameterizedType`; `T` là `TypeVariable`; một `T[]` là `GenericArrayType`.

**Lỗi 3 — “`Class<?>` chứa type argument của `ArrayList<String>`.”** Sai. `getClass()` trả runtime class `ArrayList`; generic type argument không nằm trong một class chuyên biệt cho mỗi instance.

**Lỗi 4 — “`Field.getType()` và `getGenericType()` luôn giống nhau.”** Sai. `List<String>`, `T`, generic arrays là phản ví dụ.

**Lỗi 5 — “`getGenericType()` trả `ParameterizedType` với mọi generic field.”** Sai. Field `T` có thể trả `TypeVariable`; `T[]` có thể trả `GenericArrayType`; field `List` raw có thể trả `Class`.

**Lỗi 6 — “Type argument lấy từ `getActualTypeArguments()` luôn là `Class`.”** Sai. Nó có thể lồng `ParameterizedType`, `WildcardType` hoặc `TypeVariable`.

**Lỗi 7 — “Mọi array type đều là `GenericArrayType`.”** Sai. `String[]` thuộc `Class`; `T[]` và `List<String>[]` là các ví dụ generic array.

**Lỗi 8 — “Có `TypeRef<List<String>>` nghĩa JVM biết mọi `ArrayList` nào là `List<String>`.”** Sai. TypeRef giữ metadata từ khai báo subclass, không gắn type argument runtime cho các list instance tùy ý.

**Lỗi 9 — “Reflection thấy `List<String>` thì dữ liệu collection chắc chắn an toàn.”** Sai. Raw alias và unchecked operations có thể gây heap pollution.

**Lỗi 10 — “Chỉ cần so chuỗi `getTypeName()` để xác định bằng nhau.”** Cần thận trọng: type identity, class loader, scope của type variables và cấu trúc nested đều quan trọng.

**Lỗi 11 — “`Type` có `isInstance` giống `Class`.”** Sai. `isInstance` là API của `Class`, không được `Type` khai báo.

## 16. Bài tập tự kiểm tra

**Câu 1.** `String.class` có phải một `Type` không?

Có. `Class` triển khai `java.lang.reflect.Type`.

**Câu 2.** `List<String>.class` có hợp lệ không?

Không. Java không có class literal cho cách tham số hóa cụ thể như `List<String>`; chỉ có `List.class`.

**Câu 3.** Field `Map<String, List<Integer>> index;` thường được `getGenericType()` phản chiếu thành dạng nào?

`ParameterizedType` ở ngoài cho `Map`, với một đối số là `Class(String)` và một đối số là `ParameterizedType(List<Integer>)`.

**Câu 4.** Vì sao `((Class<?>) field.getGenericType())` có thể gây `ClassCastException`?

Vì `getGenericType()` trả `Type` nói chung; nếu field có dạng `List<String>`, object thực là `ParameterizedType`, không phải `Class`.

**Câu 5.** Field `T number` trong `class Box<T extends Number>` có erasure là gì?

`Number`. Nhưng `getGenericType()` vẫn có thể biểu diễn `T` bằng `TypeVariable` với bound `Number`.

**Câu 6.** `String[]` và `List<String>[]` có cùng dạng `Type` phản chiếu không?

Không nhất thiết. `String[]` được phản chiếu bằng `Class`, trong khi `List<String>[]` thường là `GenericArrayType`.

**Câu 7.** `new TypeRef<List<String>>() {}.getType()` có kiểm tra danh sách thật chứa toàn String không?

Không. Nó thu thập mô tả generic type từ khai báo superclass của anonymous subclass.

**Câu 8.** Nếu cần `Class<T>.cast`, tham số API nên nhận `Class<T>` hay `Type`?

Thông thường là `Class<T>` nếu hợp đồng chỉ cần một runtime class cụ thể. Nếu cần nested generic metadata, `Type` mới phù hợp, nhưng cần cơ chế xác thực/chuyển đổi riêng.

**Câu 9.** Khi một kiểu khai báo `List<? super Integer>`, wildcard ở gốc của field hay bên trong `ParameterizedType`?

Field ngoài là `ParameterizedType` của `List`; wildcard là một **type argument** nằm bên trong.

## 17. Checklist đọc reflection an toàn

Khi nhận một biến `Type type`, hãy lần lượt hỏi:

1. **Đó là `Class<?>`?** Nếu có, bạn có runtime class token và những API như `isInstance`.
2. **Đó là `ParameterizedType`?** Đọc `getRawType()`, các `getActualTypeArguments()` và owner type nếu cần.
3. **Đó là `TypeVariable`?** Đọc tên, bounds, declaration; có cần resolve trong ngữ cảnh generic nào không?
4. **Đó là `WildcardType`?** Kiểm tra upper/lower bounds và mục đích sử dụng.
5. **Đó là `GenericArrayType`?** Xử lý component type đệ quy, không ép mặc định thành `Class`.
6. **Nguồn `Type` là khai báo nào?** Field, method, superclass, interface hay type token? Nó có phản ánh actual data không, hay chỉ schema?
7. **Có cần runtime check thật không?** `Class.isInstance` kiểm tra một class/interface; nested generic constraints có thể cần duyệt dữ liệu.
8. **Bạn đang phụ thuộc vào chuỗi type name không?** Tránh parser thủ công không xét type structure/scope/class loader.
9. **Có generic metadata cần phản chiếu đầy đủ không?** Đảm bảo class file và đường truy cập reflection cung cấp thông tin; framework cần dự phòng khi chữ ký thiếu/hỏng hoặc type không resolve.
10. **Bạn đang thiết kế public API nào?** Dùng `Class<T>` cho runtime class token; dùng `Type`/type token cho schema generic, và nói rõ giới hạn xác thực.

**Kết luận:** `Class<?>` là một nhánh cụ thể của `Type`, dùng để mô tả runtime class/interface/array/primitive và hỗ trợ trực tiếp kiểm tra/cast ở runtime. `java.lang.reflect.Type` là abstraction rộng hơn cho những kiểu được viết trong chương trình Java, bao gồm `ParameterizedType`, `TypeVariable`, `WildcardType` và `GenericArrayType`. `Field.getType()` thường cho bạn góc nhìn kiểu đã xóa, còn `Field.getGenericType()` có thể giữ cấu trúc generic của **khai báo**. Nắm rõ phân biệt đó giúp viết reflection, parser, serializer và API generic đúng mà không nhầm metadata kiểu với bằng chứng về dữ liệu runtime.