# Biến kiểu của phương thức khác biến kiểu của lớp trong Java Reflection

## 1. Mục tiêu và vấn đề cần phân biệt

Java Generics cho phép khai báo **biến kiểu** (*type variable*) trên **lớp/interface** hoặc trên **phương thức/constructor**. Hai biến kiểu có thể mang **cùng tên**, ví dụ đều là `T`, nhưng vẫn là hai khai báo độc lập với phạm vi và ràng buộc khác nhau.

```java
class Box<T extends Number> {
    T value;

    // Đây là T của lớp Box.
    T get() {
        return value;
    }

    // Đây là T MỚI của riêng phương thức echo, che khuất tên T của lớp.
    <T extends CharSequence> T echo(T input) {
        return input;
    }

    // U thuộc phương thức; T trong tham số đầu thuộc lớp.
    <U> String describe(T item, U extra) {
        return item + ":" + extra;
    }
}
```

Đoạn code trên minh họa cú pháp trong một lớp; chưa phải ứng dụng độc lập (ví dụ hoàn chỉnh ở mục 4).

Trong `Box<Integer>`, biến kiểu `T` của lớp được liên kết với `Integer` tại điểm dùng kiểu có tham số. Tuy nhiên `<T extends CharSequence> T echo(T input)` **khai báo một `T` mới**, có phạm vi riêng của phương thức, vì vậy lời gọi `box.echo("hello")` vẫn hợp lệ. Không được suy ra rằng `echo` buộc phải nhận `Integer` chỉ vì `Box` sử dụng `Integer`.

Với Java Reflection, phân biệt này thể hiện trực tiếp ở `TypeVariable<?>` và nơi khai báo `GenericDeclaration`. Bài học giải thích cách quan sát, xác định nguồn gốc, phân giải và tránh nhầm lẫn giữa **biến kiểu của lớp** với **biến kiểu của phương thức**, kể cả khi hai biến đều tên `T`.

### Kết quả cần đạt

Sau bài, bạn sẽ:

- Xác định `T` thuộc lớp hay phương thức bằng **vị trí khai báo**, không chỉ bằng tên.
- Phân biệt `Class.getTypeParameters()` với `Method.getTypeParameters()` và `Constructor.getTypeParameters()`.
- Dùng `TypeVariable.getGenericDeclaration()` để biết owner thực sự.
- Đọc `getGenericReturnType()`, `getGenericParameterTypes()`, `getBounds()` và nhận biết type erasure.
- Giải thích hiện tượng **shadowing** khi biến kiểu của phương thức cùng tên với biến kiểu của lớp.
- Phân biệt việc Reflection nhìn thấy generic signature với việc biết kiểu cụ thể như `Integer` hoặc `String` ở runtime.

## 2. Biến kiểu được khai báo ở đâu?

### 2.1. Biến kiểu của lớp

```java
class Holder<T> {
    private T item;

    Holder(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }
}
```

Trong `Holder<T>`, tên `T` được khai báo ở danh sách tham số kiểu **ngay sau tên lớp**. Trong các vị trí dùng `T` của lớp (nơi không bị che khuất), một instance có kiểu nguồn `Holder<String>` cho phép trình biên dịch kiểm tra `T` là `String`.

Ví dụ, `Holder<String>` và `Holder<Integer>` là hai cách sử dụng generic class khác nhau; tại runtime, chúng thường cùng trỏ đến **một định nghĩa `Holder.class`** do type erasure. Object `Class` của `Holder` phản ánh **khai báo** `T`, không tự biết đối tượng cụ thể đã được tạo với tham số `String` hay `Integer`.

### 2.2. Biến kiểu của phương thức

```java
class Converter {
    public static <T> T identity(T input) {
        return input;
    }

    public <U extends Number> U keep(U number) {
        return number;
    }
}
```

Biến kiểu được khai báo **trước return type** trong khai báo phương thức: `<T>`, `<U extends Number>`. Nó thuộc riêng phương thức đó, cho dù lớp bên ngoài có generic hay không.

Một lớp không generic vẫn có thể chứa method generic, và một lớp generic vẫn có thể chứa method không generic hoặc method generic với biến kiểu riêng.

**Phương thức static** không được tham chiếu trực tiếp tới biến kiểu thuộc instance của lớp generic, nhưng hoàn toàn có thể **tự khai báo** biến kiểu riêng:

```java
class Factory<T> {
    // Không dùng trực tiếp class T trong bối cảnh static.
    static <S> S identity(S value) {
        return value;
    }
}
```

Ở đây `S` thuộc method `identity`, không phải biến kiểu `T` của `Factory`. Không thể viết method static chỉ dùng `T` lớp trong chữ ký mà không có khai báo `<T>` riêng phù hợp.

### 2.3. Biến kiểu của constructor

Constructor cũng có thể khai báo biến kiểu riêng:

```java
class Sample<T> {
    <U> Sample(U input) {
        System.out.println(input);
    }
}
```

`T` thuộc lớp, còn `U` thuộc constructor. Reflection cung cấp `Constructor.getTypeParameters()` để lấy `U`. Tương tự, `U.getGenericDeclaration()` trả về đối tượng `Constructor<?>`, không phải `Class<?>`.

Các ví dụ mục 2 là các đoạn minh họa cấu trúc Java riêng lẻ; ví dụ mục 4 gồm chương trình có `main` chạy được.

## 3. API Reflection cần dùng

| Câu hỏi | API | Trả về / ý nghĩa |
| --- | --- | --- |
| Lớp khai báo biến kiểu nào? | `Class.getTypeParameters()` | Mảng `TypeVariable<Class<T>>[]` (qua wildcard ở code dùng chung) của chính lớp/interface |
| Phương thức khai báo biến kiểu nào? | `Method.getTypeParameters()` | `TypeVariable<Method>[]` của chính phương thức |
| Constructor khai báo biến kiểu nào? | `Constructor.getTypeParameters()` | `TypeVariable<Constructor<T>>[]` của constructor |
| Biến kiểu thuộc khai báo nào? | `TypeVariable.getGenericDeclaration()` | `GenericDeclaration`: thường là `Class`, `Method` hoặc `Constructor` |
| Tên và cận trên của biến kiểu? | `TypeVariable.getName()`, `getBounds()` | Tên như `T`; các `Type` ràng buộc trên |
| Kiểu trả về generic của method? | `Method.getGenericReturnType()` | `Type`; có thể là `TypeVariable`, `ParameterizedType`, `Class`... |
| Các kiểu tham số generic? | `Method.getGenericParameterTypes()` | Mảng `Type[]` của khai báo generic |
| Kiểu trả về sau erasure? | `Method.getReturnType()` | `Class<?>` đại diện kiểu runtime đã erasure |
| Các kiểu tham số runtime sau erasure? | `Method.getParameterTypes()` | `Class<?>[]`, dùng để tra cứu chữ ký bằng `getDeclaredMethod` |
| Generic superclass của một lớp? | `Class.getGenericSuperclass()` | `Type`, có thể là `ParameterizedType` như `Box<Integer>` |

**Phân biệt hai chữ “parameters”:**

- `getTypeParameters()`: các biến kiểu được **khai báo mới** ở lớp hoặc phương thức (ví dụ `<T, U>`).
- `getGenericParameterTypes()`: các **kiểu của tham số truyền vào** một phương thức (ví dụ `List<T> input, U extra`). Một phương thức không tự khai báo `<T>` vẫn có thể sử dụng biến kiểu `T` của lớp trong danh sách tham số và vì vậy trả mảng `getTypeParameters()` rỗng nhưng `getGenericParameterTypes()` không rỗng.

Các `Type` đặc biệt trong `java.lang.reflect` gồm `TypeVariable<?>`, `ParameterizedType`, `WildcardType` và `GenericArrayType`. Không phải mọi `Type` đều là `Class<?>`; dùng `instanceof` trước khi ép kiểu sang một nhánh cụ thể.

### GenericDeclaration và danh tính của biến kiểu

`TypeVariable.getGenericDeclaration()` là điểm then chốt. Trong Reflection, hai biến cùng tên chỉ biểu diễn cùng một biến kiểu khi chúng **tương ứng với cùng khai báo generic**; tên đơn thuần không đủ xác nhận.

Ví dụ, ở `Box<T>` và `<T> T echo(T)`:

- `classT.getName()` và `methodT.getName()` đều là `"T"`.
- `classT.getGenericDeclaration()` là `Box.class`.
- `methodT.getGenericDeclaration()` là `Method` biểu diễn `echo`.
- Vì khai báo khác nhau, `classT.equals(methodT)` là `false`.

Dùng `getGenericDeclaration()` cùng vị trí/đối tượng khai báo khi lập trình resolver; **không** dùng một map chỉ khóa theo tên `"T"`, vì tên đó có thể được dùng lặp ở nhiều scope.

## 4. Chương trình Java 17+ hoàn chỉnh: hai chữ T nhưng hai biến kiểu

Lưu toàn bộ mã sau vào **`TypeVariableScopeDemo.java`**:

```java
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.TypeVariable;

public class TypeVariableScopeDemo {
    static class Box<T extends Number> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        public T get() {
            return value;
        }

        // T riêng của method, che tên T của class Box.
        public <T extends CharSequence> T echo(T input) {
            return input;
        }

        // U riêng của method; T trong tham số đầu thuộc Box.
        public <U> String describe(T item, U extra) {
            return item + ":" + extra;
        }

        // Method static được tự khai báo type variable S.
        public static <S extends CharSequence> S identity(S value) {
            return value;
        }
    }

    static class IntegerBox extends Box<Integer> {
        IntegerBox(Integer value) {
            super(value);
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> cls = Box.class;
        TypeVariable<?> classT = cls.getTypeParameters()[0];
        Method echo = cls.getDeclaredMethod(
                "echo", CharSequence.class);
        TypeVariable<?> methodT = echo.getTypeParameters()[0];
        Method get = cls.getDeclaredMethod("get");
        Method describe = cls.getDeclaredMethod(
                "describe", Number.class, Object.class);
        Method identity = cls.getDeclaredMethod(
                "identity", CharSequence.class);
        TypeVariable<?> methodU = describe.getTypeParameters()[0];

        System.out.println("class name: " + classT.getName());
        System.out.println("method name: " + methodT.getName());
        System.out.println("same name: "
                + classT.getName().equals(methodT.getName()));
        System.out.println("same variable: " + classT.equals(methodT));

        System.out.println("class owner Class: "
                + (classT.getGenericDeclaration() == cls));
        System.out.println("method owner Method: "
                + methodT.getGenericDeclaration().equals(echo));

        System.out.println("class bound: "
                + classT.getBounds()[0].getTypeName());
        System.out.println("method bound: "
                + methodT.getBounds()[0].getTypeName());

        System.out.println("get return is class T: "
                + get.getGenericReturnType().equals(classT));
        System.out.println("echo return is method T: "
                + echo.getGenericReturnType().equals(methodT));

        System.out.println("echo erased param: "
                + echo.getParameterTypes()[0].getSimpleName());
        System.out.println("echo erased return: "
                + echo.getReturnType().getSimpleName());

        System.out.println("describe owns U: " + methodU.getName());
        System.out.println("describe first param is class T: "
                + describe.getGenericParameterTypes()[0].equals(classT));
        System.out.println("describe second param is method U: "
                + describe.getGenericParameterTypes()[1].equals(methodU));

        System.out.println("static method variable: "
                + identity.getTypeParameters()[0].getName());

        ParameterizedType parent = (ParameterizedType)
                IntegerBox.class.getGenericSuperclass();
        System.out.println("subclass argument: "
                + parent.getActualTypeArguments()[0].getTypeName());

        Box<Integer> box = new Box<>(10);
        System.out.println("box get: " + box.get());
        System.out.println("echo: " + box.echo("hello"));
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac TypeVariableScopeDemo.java
java TypeVariableScopeDemo
```

**Output** (đã đối chiếu hoạt động Java Reflection trên JVM):

```text
class name: T
method name: T
same name: true
same variable: false
class owner Class: true
method owner Method: true
class bound: java.lang.Number
method bound: java.lang.CharSequence
get return is class T: true
echo return is method T: true
echo erased param: CharSequence
echo erased return: CharSequence
describe owns U: U
describe first param is class T: true
describe second param is method U: true
static method variable: S
subclass argument: java.lang.Integer
box get: 10
echo: hello
```

### Giải thích kết quả cốt lõi

**1. Cùng tên nhưng khác identity.** Cả `Box<T>` và `echo<T>` đều có `getName() == "T"`, nhưng `classT.equals(methodT)` là `false`. Vì vậy resolver phải xác định **declaration owner**, thay vì map tất cả biến tên `T` sang một kiểu thực duy nhất.

**2. Bounds khác nhau.** `T` của lớp có bound `Number`; `T` của `echo` có bound `CharSequence`. Tức là `Box<Integer>` chấp nhận đối tượng Number làm class parameter, trong khi một lời gọi `echo("hello")` chấp nhận String do String triển khai CharSequence. Hai ràng buộc áp dụng cho hai biến kiểu độc lập.

**3. Return type generic khác return type sau erasure.** `get.getGenericReturnType()` là chính biến kiểu class `T`. `echo.getGenericReturnType()` là biến kiểu method `T`. Nhưng `echo.getReturnType()` là `CharSequence.class` do erasure sử dụng cận trên của biến kiểu method.

**4. Tra cứu phương thức dùng chữ ký erased.** `Box.class.getDeclaredMethod("echo", CharSequence.class)` thành công. Dùng `Object.class` hay `Number.class` thay cho `CharSequence.class` sẽ không tìm đúng method vì kiểu tham số erased của method này là `CharSequence`.

**5. Phương thức dùng cả biến kiểu class và method.** `describe` tự khai báo `U`; tham số đầu `T item` vẫn liên kết với class `Box<T>`. Vì thế `getTypeParameters()` của `describe` chỉ chứa `U`, còn `getGenericParameterTypes()` cho thấy cả `T` của lớp lẫn `U` của method.

**6. Static method có biến kiểu riêng.** `identity` là static generic method với `S` do chính nó khai báo; đó không phải `T` của lớp.

**7. Generic superclass cho biết binding trong một nhánh cụ thể.** `IntegerBox extends Box<Integer>` khai báo rõ `Integer` trong generic superclass, vì vậy `IntegerBox.class.getGenericSuperclass()` trả một `ParameterizedType` chứa type argument `Integer`. Nhưng `Box.class.getTypeParameters()[0]` vẫn biểu diễn **khai báo `T`**, không tự đổi thành `Integer`.

## 5. Shadowing: method có thể khai báo T trùng tên T của class

Giả sử:

```java
class Repository<T> {
    T current;

    T load() {
        return current; // T của Repository
    }

    <T> T transform(T input) {
        return input;   // T mới của transform
    }

    <U> T update(U source) {
        return current; // U của update; T của Repository
    }
}
```

Đây là đoạn minh họa về phạm vi tên; không cần chạy riêng. **Shadowing** xảy ra khi declaration `<T>` ở method che tên `T` của lớp trong phạm vi method đó. Nhờ phân biệt owner, Reflection có thể quan sát hai biến có tên giống nhau mà không nhập nhằng.

| Thành phần | Biến kiểu khai báo trực tiếp ở thành phần đó | Ý nghĩa của T xuất hiện trong chữ ký |
| --- | --- | --- |
| `Repository<T>` | `T` của class | Class-level type variable |
| `load()` | Không có | `T` return thuộc class |
| `<T> T transform(T)` | `T` của method | `T` trong return và tham số thuộc method |
| `<U> T update(U)` | `U` của method | `T` return thuộc class, `U` tham số thuộc method |

Khi làm resolver, nên giữ mô hình dữ liệu theo cả **scope của khai báo** lẫn biến kiểu:

```text
Repository<T>              : key = (Repository.class, "T")
Repository.transform<T>(T)  : key = (Method transform, "T")
Repository.update<U>(U)     : key = (Method update, "U")
```

Đây là **mô hình minh họa**, không phải Java code runnable. Chính API `getGenericDeclaration()` và tính tương đương của `TypeVariable` giúp phân biệt những trường hợp trên.

Một lỗi phổ biến là lưu mapping dưới dạng `Map<String, Type>` với key chỉ là `"T"`. Khi resolver đi qua phương thức `transform`, mapping mới có thể **ghi đè** binding `T` của lớp. Kết quả giải thích generic trở nên sai dù code vẫn compile.

## 6. TypeVariable.getBounds() và erasure

Khi khai báo:

```java
class Container<T extends Number> {
    <U extends CharSequence> U use(U text) {
        return text;
    }
}
```

`T.getBounds()` của lớp trả bound `Number`; `U.getBounds()` của phương thức trả bound `CharSequence`. Với một biến kiểu không có bound tường minh như `<T>`, bound ngầm định là `Object`.

### Nhiều bound

```java
class MultiBound<T extends Number & Comparable<T>> {
    T value;
}
```

`getBounds()` có thể trả một mảng `Type[]` gồm nhiều bound theo thứ tự khai báo. Khi thực hiện erasure của một biến kiểu, **bound bên trái** quyết định kiểu erasure; trong ví dụ là `Number`.

Đừng lấy duy nhất `getBounds()[0]` nếu nhiệm vụ cần bảo toàn **mọi constraint**. Ví dụ runnable mục 4 chỉ dùng một bound để output dễ hiểu; resolver thực tế phải xử lý cả intersection bounds, tham chiếu generic trong bounds và trường hợp type variable sử dụng chính nó (chẳng hạn `Comparable<T>`).

### Generic metadata và class runtime

Hai API khác nhau có thể đưa kết quả khác nhau:

```java
Method method = Box.class.getDeclaredMethod(
        "echo", CharSequence.class);

System.out.println(method.getReturnType());        // interface java.lang.CharSequence
System.out.println(method.getGenericReturnType()); // T
```

Đoạn trên cần đặt trong một phương thức xử lý `NoSuchMethodException`, đã import `Method` và dùng lớp `Box` như ví dụ. `getReturnType()` xem return type **sau erasure** dưới dạng `Class<?>`; `getGenericReturnType()` giữ `TypeVariable` `T` của method. Cùng một phương thức, hai góc nhìn đều đúng.

Với generic type dùng kiểu tham số hóa, như `List<T>`, `getGenericReturnType()` có thể là `ParameterizedType`. Khi xử lý, dùng `instanceof ParameterizedType` để lấy `getRawType()` và `getActualTypeArguments()`; một type argument có thể là `TypeVariable` của lớp, của method, một wildcard hoặc cấu trúc phức tạp khác. Không cast `Type` sang `Class<?>` một cách mặc định.

## 7. Vì sao Class.getTypeParameters() không trả biến kiểu của method?

`Class.getTypeParameters()` chỉ liệt kê biến kiểu **được class/interface tự khai báo**. Nó không tập hợp `T` hoặc `U` từ tất cả method thành viên.

Ví dụ:

```java
class Plain {
    <X> X echo(X input) { return input; }
}
```

`Plain.class.getTypeParameters()` là mảng **rỗng**, vì `Plain` không phải generic class. Ngược lại:

```java
Method m = Plain.class.getDeclaredMethod("echo", Object.class);
TypeVariable<?>[] vars = m.getTypeParameters();
```

Đây là đoạn trong một phương thức có xử lý ngoại lệ. `vars.length` là `1`, và biến ở `vars[0]` tên `X`. Chữ ký erased của method dùng `Object` do `X` không có bound tường minh.

Cũng vậy, `Method.getTypeParameters()` trả về **mảng rỗng** cho một method bình thường dùng type variable thuộc lớp nhưng không khai báo type variable mới:

```java
class GenericService<T> {
    T fetch() { return null; }
}
```

Khi inspect `fetch()`, `getTypeParameters()` rỗng dù `getGenericReturnType()` là `T` của class. Để biết owner của `T` này, kiểm tra `TypeVariable.getGenericDeclaration()`.

## 8. Phân giải generic ở lớp con và giới hạn cần biết

Giả sử:

```java
class Parent<T> {
    T get() { return null; }
}

class Child extends Parent<String> {
}
```

Ở lớp `Child`, generic superclass chứa binding `Parent<String>`. Nhưng đối tượng `Method` được khai báo ở `Parent` với return type `T` vẫn giữ metadata `T` của **Parent**. Reflection **không tự thay biến kiểu đó bằng String** chỉ vì caller nhận method thông qua `Child.class`.

Resolver muốn giải đúng return type theo ngữ cảnh `Child` phải:

1. Xác định method được khai báo ở lớp/interface nào bằng `getDeclaringClass()`.
2. Duyệt quan hệ `getGenericSuperclass()` và `getGenericInterfaces()` theo đúng phân cấp.
3. Thu thập mapping từ biến kiểu **của từng declaration** sang type argument cụ thể, chẳng hạn `Parent<T> → String`.
4. Thay thế biến kiểu bằng mapping đúng owner, có xử lý `ParameterizedType`, `WildcardType`, `GenericArrayType` và các biến kiểu trung gian nếu cần.

**Điểm quan trọng:** mapping `Parent.T → String` **không được** tự áp lên `T` khác do một method `<T>` trong Parent khai báo. Hai `T` đó không phải cùng biến kiểu, dù chúng cùng tên.

### Method type argument suy diễn tại compile time

Ví dụ:

```java
class Tools {
    static <T> T identity(T value) {
        return value;
    }
}

String text = Tools.identity("hello");
Integer count = Tools.identity(123);
```

Hai câu lệnh sử dụng method generic với hai cách suy diễn khác nhau ở compile time. Nhưng Reflection trên `Tools.identity` chỉ nhìn thấy **một khai báo `<T> T identity(T)`**. Nó không lưu một binding method-T cố định là String hay Integer trên đối tượng `Method`.

Khi gọi `Method.invoke(...)`, caller phải dùng các kiểu runtime thích hợp; thông tin về type argument suy diễn ở compile time không trở thành metadata “lời gọi method này dùng T = String” trong `Method`.

Nếu API của ứng dụng cần theo dõi binding từ một phương thức generic trong ngữ cảnh cụ thể, nó phải nhận đủ thông tin bổ sung (kiểu của tham số/return expected type/quy tắc resolver) và không suy diễn quá mức từ `Method.getTypeParameters()`.

## 9. Constructor type variable khác class type variable

`Constructor<?>` cũng triển khai `GenericDeclaration`. Điều đó cho phép phân biệt biến kiểu ở constructor với biến kiểu ở class:

```java
class Factory<T> {
    <U extends CharSequence> Factory(U name) {
    }
}
```

Đoạn minh họa:

```java
Class<?> type = Factory.class;
TypeVariable<?> classT = type.getTypeParameters()[0];

Constructor<?> ctor =
        type.getDeclaredConstructor(CharSequence.class);
TypeVariable<?> ctorU = ctor.getTypeParameters()[0];
```

Đây là code đặt trong một phương thức có xử lý/khai báo `NoSuchMethodException` và import `java.lang.reflect.Constructor`, `java.lang.reflect.TypeVariable`.

- `classT.getGenericDeclaration() == Factory.class` là `true`.
- `ctorU.getGenericDeclaration().equals(ctor)` là `true`.
- `ctorU.getName()` là `"U"`, và `getBounds()[0]` là `CharSequence`.
- `getDeclaredConstructor(CharSequence.class)` tra cứu theo **erasure của bound**, không dùng một type argument suy diễn nào như `String.class`.

Với non-static inner class, constructor runtime còn có thể xuất hiện tham số outer-instance do compiler sinh. Đó là vấn đề về chữ ký constructor, **khác** việc constructor có khai báo `<U>` hay không.

## 10. Lỗi thường gặp khi xây dựng generic resolver

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| So sánh hai `TypeVariable` chỉ qua `getName()` | Class-T và method-T có thể cùng tên | So sánh identity/declaration owner |
| Giả định class generic thì mọi method trả class-T | Method có thể khai báo T mới và shadow class-T | Đọc `Method.getTypeParameters()` và `getGenericReturnType()` |
| Cho rằng `Class.getTypeParameters()` gồm cả generic methods | API chỉ trả biến kiểu khai báo ở class | Truy vấn trên từng `Method` |
| Cho rằng `Method.getTypeParameters()` là kiểu các tham số runtime | Nó trả biến kiểu method khai báo, không phải argument types | Dùng `getGenericParameterTypes()` hoặc `getParameterTypes()` |
| Dùng `getReturnType()` để hiểu đầy đủ generic | Erasure làm mất biểu thức generic | Dùng `getGenericReturnType()` |
| Tra cứu `echo(T)` bằng `Object.class` khi `T extends CharSequence` | Erased parameter là CharSequence | Tra cứu bằng `CharSequence.class` |
| Đổi mọi T thành Integer vì có `Box<Integer>` | Chỉ class-T được binding; method-T độc lập | Mapping theo `GenericDeclaration` |
| Tin rằng mỗi call `identity("x")` giữ riêng method-T = String trong `Method` | Type inference compile-time không được lưu như vậy | Dùng context/hợp đồng kiểu riêng |
| Ép mọi `Type` sang `Class<?>` | `TypeVariable` và `ParameterizedType` không phải `Class` | Phân nhánh `instanceof` |
| Bỏ qua multi-bound và nested parameterized type | Resolver có thể chọn erasure hoặc constraint sai | Xử lý các loại `Type` và tất cả bounds |
| Dựa vào tên biến để suy ra kiểu runtime object | Erasure và tính đa hình làm suy luận không đủ | Kiểm tra object thực nếu cần |

### Thiết kế map thay thế an toàn

Một resolver nên sử dụng khóa có danh tính khai báo rõ ràng, ví dụ trực tiếp `TypeVariable<?>`:

```java
Map<TypeVariable<?>, java.lang.reflect.Type> bindings =
        new java.util.HashMap<>();
```

Đây là đoạn trong class/phương thức có import `java.util.Map`, `java.lang.reflect.TypeVariable`; ví dụ không cung cấp thuật toán resolver hoàn chỉnh. `TypeVariable.equals` được xác định theo generic declaration tương ứng, giúp tránh tình huống hai biến tên giống nhau ghi đè nhau.

Dù vậy, việc giải binding đầy đủ vẫn phức tạp khi có generic superclass nhiều tầng, wildcard, capture, interface, owner type và biến kiểu tự tham chiếu. Đừng dùng `getName()` rồi thay text trong `Type.getTypeName()`; hãy làm việc với cấu trúc `Type`.

## 11. Các bài thực hành nhỏ

**Bài 1.** Với:

```java
class Service<T> {
    T read() { return null; }
    <T> T convert(T value) { return value; }
    <U> T combine(U input) { return null; }
}
```

Hãy trả lời:

1. `Service.class.getTypeParameters()` có bao nhiêu phần tử?
2. `read.getTypeParameters()` có bao nhiêu phần tử?
3. `convert.getTypeParameters()` có bao nhiêu phần tử?
4. `combine.getGenericReturnType()` thuộc class hay method?
5. Hai chữ `T` của `Service<T>` và `convert<T>` có là một biến kiểu không?

**Đáp án:** lần lượt là **1, 0, 1, class, không**. `combine` tự khai báo `U`, nhưng return type `T` là biến kiểu của class.

**Bài 2.** Với:

```java
class Numeric<T extends Number> {
    <T extends CharSequence> T text(T input) {
        return input;
    }
}
```

**Câu hỏi:** Dùng API nào để lấy biến kiểu của method và Reflection phải dùng parameter class nào để tra cứu `text`?

**Đáp án:** `Numeric.class.getDeclaredMethod("text", CharSequence.class)` rồi gọi `method.getTypeParameters()`. Dùng `CharSequence.class` vì bound của method-T là CharSequence; bound class-T là Number không liên quan đến chữ ký method này.

**Bài 3.** Cho `class Child extends Parent<String>`, trong đó `Parent<T>` có `T read()` và `<T> T echo(T input)`. Có thể thay cả hai T bằng String trong generic resolver không?

**Đáp án:** Không. Binding trong quan hệ kế thừa chỉ áp dụng **Parent.class-T**. `echo` có method-T độc lập nên không được suy ra rằng nó bằng String.

**Bài 4.** Nếu `Method.getTypeParameters()` trả mảng rỗng, có kết luận method không sử dụng generic trong return/parameter được không?

**Đáp án:** Không. Method có thể dùng biến kiểu khai báo ở class, như `T read()`, hoặc tham số `List<T>`. Kiểm tra `getGenericReturnType()` và `getGenericParameterTypes()`.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Hai biến kiểu đều tên `T` có nhất thiết cùng identity không?

**Đáp án:** Không. Phải xét nơi khai báo `GenericDeclaration`. Class-T và method-T là hai biến độc lập.

**Câu 2.** API nào trả các biến kiểu do method tự khai báo, như `<U>`?

**Đáp án:** `Method.getTypeParameters()`. `getGenericParameterTypes()` lại trả kiểu của các tham số nhận vào.

**Câu 3.** Phương thức `<T extends CharSequence> T echo(T x)` có `Method.getReturnType()` và `getGenericReturnType()` khác nhau ra sao?

**Đáp án:** `getReturnType()` trả `CharSequence.class` sau erasure; `getGenericReturnType()` trả `TypeVariable` thuộc method (tên T).

**Câu 4.** Vì sao biến kiểu của `<T>` ở phương thức static không phụ thuộc type argument của generic class?

**Đáp án:** Nó được method khai báo riêng; static context không sử dụng biến kiểu instance của generic class.

**Câu 5.** `Box<Integer>` có tự khiến `<T extends CharSequence> T echo(T)` trả Integer không?

**Đáp án:** Không. Method-T shadow class-T, bound của method-T là CharSequence nên có thể trả String.

**Câu 6.** `TypeVariable.getGenericDeclaration()` trả về những đối tượng nào?

**Đáp án:** Một declaration như `Class`, `Method` hoặc `Constructor` tương ứng với nơi biến kiểu được khai báo.

**Câu 7.** Khi phân giải `Parent<T>` trong `Child extends Parent<String>`, vì sao nên dùng khóa `TypeVariable<?>` thay vì chuỗi `"T"`?

**Đáp án:** Để binding String chỉ áp dụng Parent-T và không ghi đè các biến kiểu tên T ở method hay các class khác.

**Ghi nhớ:** Biến kiểu của **lớp** và biến kiểu của **phương thức** là các khai báo độc lập. Cùng tên `T` không tạo cùng identity; Reflection cho biết owner bằng `TypeVariable.getGenericDeclaration()`. Dùng `Class.getTypeParameters()` để xem biến kiểu lớp, `Method.getTypeParameters()` để xem biến kiểu method, và các API `getGeneric...` để giữ thông tin trước erasure. Khi giải generic, luôn gắn binding với **đúng declaration**, đặc biệt khi method khai báo một biến `T` mới che khuất `T` của lớp.
