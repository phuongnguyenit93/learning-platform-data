# Constructor<T> và constructor không được kế thừa trong Java Reflection

Trong Java Reflection, **java.lang.reflect.Constructor<T>** biểu diễn một constructor được khai báo bởi một class, cho phép kiểm tra tham số, mức truy cập, annotation và tạo instance qua **newInstance(...)**. Ký hiệu `<T>` ở `Constructor<T>` biểu thị **kiểu đối tượng mà constructor tạo ra**, thường gắn với `Class<T>` đang được tra cứu.

Điểm dễ nhầm là **constructor của superclass không được subclass kế thừa**. Khi tạo subclass, constructor superclass vẫn **được gọi** trong chuỗi khởi tạo (`super(...)`), nhưng không trở thành một constructor thuộc subclass. Reflection phản ánh quy tắc này: `Child.class.getConstructors()` không liệt kê constructor của `Parent`; `Child.class.getConstructor(...)` cũng không tìm constructor chỉ được khai báo trên `Parent`.

Bài học phân tích cả hai phần: cách hiểu `Constructor<T>` cùng generic constructor, và cách tra cứu/khởi tạo đúng theo quan hệ superclass–subclass.

## 1. Constructor<T> đại diện cho điều gì?

Các kiểu liên quan trong Java 17:

~~~java
Class<StringBuilder> type = StringBuilder.class;
Constructor<StringBuilder> constructor = type.getConstructor();
StringBuilder value = constructor.newInstance();
~~~

Đây là mảnh code minh họa đặt trong method có `throws ReflectiveOperationException` (hoặc xử lý checked exceptions); cần `import java.lang.reflect.Constructor;`.

- `StringBuilder.class` có kiểu `Class<StringBuilder>`.
- `getConstructor()` trả `Constructor<StringBuilder>` vì constructor được yêu cầu từ `Class<StringBuilder>`.
- `constructor.newInstance()` trả đối tượng kiểu `StringBuilder`.
- Đối số kiểu `T` trong `Constructor<T>` **không phải là kiểu từng tham số constructor** và **không phải kiểu tham số generic riêng của constructor**.
- `Constructor<T>` extends `Executable`; có API như `getParameterTypes()`, `getGenericParameterTypes()`, `getTypeParameters()`, `getModifiers()`, `getExceptionTypes()`, `isVarArgs()`, `getDeclaringClass()`.

Ví dụ `Constructor<Child>` biểu diễn constructor của **Child**; nó không mô tả một constructor kế thừa từ Parent và không thể dùng để tạo loại đối tượng khác tùy ý.

| Biểu thức | Ý nghĩa |
| --- | --- |
| `Class<T>` | Đối tượng mô tả một runtime class; `T` là kiểu class trong hệ thống generic Java |
| `Constructor<T>` | Constructor của class mang kiểu `T`, dùng để tạo `T` qua `newInstance` |
| `Constructor<?>` | Có constructor nhưng chưa biết chính xác class ở compile time; `newInstance` chỉ suy ra Object |
| `Constructor.getTypeParameters()` | Khai báo type variables **riêng của constructor** như `<U>`, không phải `T` của `Constructor<T>` |
| `Class.getTypeParameters()` | Type variables khai báo bởi class, ví dụ `E` trong `Box<E>` |

Trong generic class `Box<E>`, biểu thức `Box.class` đại diện runtime class raw `Box`; không tồn tại `Box<String>.class` tách biệt với `Box<Integer>.class`. Các argument `String` và `Integer` của instance thường bị **type erasure**.

## 2. Constructor không được kế thừa: phân biệt “gọi” và “sở hữu”

Theo **Java Language Specification §8.2 và §8.8**, constructor **không phải class member** theo nghĩa được kế thừa; constructor không inherited, không hidden và không overridden.

~~~java
class Parent {
    protected Parent(int code) {}
}

class Child extends Parent {
    public Child(String name) {
        super(7);
    }
}
~~~

- `Child(String)` là constructor được **Child khai báo**.
- `Parent(int)` thuộc **Parent**, không phải overload `Child(int)`.
- `super(7)` là **constructor invocation** dùng để khởi tạo phần trạng thái superclass trong cùng đối tượng Child; nó không biến `Parent(int)` thành constructor của Child.
- Việc `Parent(int)` là `protected` cho phép gọi qua `super` từ subclass phù hợp, nhưng không đồng nghĩa nó là `public Child(int)`.
- Constructor không có kiểu trả về, không tham gia overriding/polymorphic dispatch như instance method.

Một đối tượng Child thường được khởi tạo theo chuỗi constructor của các superclass trước khi chạy phần thân constructor Child. Nhưng **kết quả của `Parent.class.getDeclaredConstructor(int.class)` luôn mô tả constructor của Parent**.

### Vì sao không tự xuất hiện no-arg constructor?

Java chỉ cung cấp một **default constructor** khi class **không khai báo constructor nào**. Nếu class đã tự khai báo `Child(String)`, compiler **không sinh thêm `Child()`**. Khi subclass không khai báo constructor, default constructor của subclass sẽ cố gọi `super()` theo quy tắc ngôn ngữ; nếu superclass không có constructor không tham số khả dụng, việc biên dịch thất bại.

Ví dụ cố ý không biên dịch được:

~~~java
class Base {
    Base(int id) {}
}
class MissingConstructor extends Base {
    // Không có constructor được khai báo.
    // Default constructor sẽ cố gọi super(), nhưng Base() không tồn tại.
}
~~~

Cách sửa là khai báo constructor của subclass và gọi super bằng tham số tương ứng:

~~~java
class Base {
    Base(int id) {}
}
class ValidChild extends Base {
    ValidChild() {
        super(10);
    }
}
~~~

Đoạn trên chỉ minh họa quan hệ constructor trong một compilation unit; không phải chương trình độc lập có main. Việc superclass có public/protected/package-private constructor không làm subclass kế thừa chúng.

## 3. API Reflection để tra cứu constructor

Các phương thức trên `Class<T>` khác nhau ở mức truy cập, **không có nhánh tìm constructor kế thừa**:

| API trên Class<T> | Kết quả | Có tìm ở superclass không? |
| --- | --- | --- |
| `getConstructor(Class<?>... parameterTypes)` | `Constructor<T>`: constructor **public** của chính class, khớp danh sách tham số | **Không** |
| `getConstructors()` | `Constructor<?>[]`: tất cả constructor public của chính class | **Không** |
| `getDeclaredConstructor(Class<?>... parameterTypes)` | `Constructor<T>`: constructor của chính class, gồm private/protected/package-private/public | **Không** |
| `getDeclaredConstructors()` | `Constructor<?>[]`: tất cả constructor được khai báo trong class, mọi mức truy cập | **Không** |

Đối với `Child` ở mục trước:

~~~java
Child.class.getConstructor(String.class);       // đúng: public Child(String)
Child.class.getDeclaredConstructor(String.class); // đúng
Child.class.getConstructor(int.class);          // NoSuchMethodException
Parent.class.getDeclaredConstructor(int.class); // đúng: Parent(int)
~~~

Trong API này `parameterTypes` được so khớp theo **thứ tự, số lượng và chính xác runtime parameter Class<?>**. Java Reflection không áp dụng cơ chế overload resolution của javac để tự tìm constructor “gần đúng”; ví dụ `int.class` khác `Integer.class`, và `List<String>` bị xóa còn `List.class`. Khi không khớp, `getConstructor/getDeclaredConstructor` ném `NoSuchMethodException`.

Khi danh sách rỗng, `getConstructor()` tìm một constructor **public không tham số**. Không thể giả định class nào cũng có constructor này. `getDeclaredConstructor()` có thể tìm constructor không tham số private nếu được khai báo/thực sự tồn tại; có thể cần quyền để gọi.

### Đọc thông tin của Constructor

~~~java
Constructor<?> c = Child.class.getDeclaredConstructor(String.class);
System.out.println(c.getDeclaringClass()); // class Child
System.out.println(c.getParameterCount()); // 1
System.out.println(c.isVarArgs());         // false
~~~

Đây là đoạn trích sử dụng `Child` từ mục 2, sau khi import `java.lang.reflect.Constructor`; các comment nêu ý nghĩa, output khi chạy trong default package có thể mang tên class khác tùy nesting. `getDeclaringClass()` là cách xác nhận constructor **thuộc class nào**; kết quả không tự đổi thành subclass khi bạn dùng constructor của Parent.

## 4. Ví dụ Java 17+ chạy độc lập

Ví dụ sau minh họa chuỗi `super(...)`, lookup thất bại vì constructor không kế thừa, và khác biệt giữa type variable của generic class với generic constructor.

Lưu nguyên văn vào **ConstructorInheritanceDemo.java**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import java.lang.reflect.Type;

public class ConstructorInheritanceDemo {
    public static class Parent {
        public Parent() { this(0); }

        protected Parent(int id) {
            System.out.println("Parent(" + id + ")");
        }
    }

    public static class Child extends Parent {
        public Child(String name) {
            super(7);
            System.out.println("Child(" + name + ")");
        }
    }

    public static class Box<E> {
        private final E value;

        public <U> Box(E value, U marker) {
            this.value = value;
        }

        public E value() { return value; }
    }

    public static void main(String[] args) throws Exception {
        Constructor<Child> childCtor = Child.class.getConstructor(String.class);
        Child child = childCtor.newInstance("Ada");
        System.out.println("child type=" + child.getClass().getSimpleName());
        System.out.println("child public constructors=" + Child.class.getConstructors().length);

        try {
            Child.class.getConstructor(int.class);
        } catch (NoSuchMethodException e) {
            System.out.println("Child(int)=not found");
        }

        Constructor<Parent> parentCtor = Parent.class.getDeclaredConstructor(int.class);
        System.out.println("parent int protected="
                + Modifier.isProtected(parentCtor.getModifiers()));
        System.out.println("parent declaring=" + parentCtor.getDeclaringClass().getSimpleName());

        Constructor<Box> boxCtor = Box.class.getConstructor(Object.class, Object.class);
        Box<?> box = boxCtor.newInstance("payload", 123);
        System.out.println("box value=" + box.value());
        Type[] generic = boxCtor.getGenericParameterTypes();
        System.out.println("box erased=" + boxCtor.getParameterTypes()[0].getSimpleName()
                + "," + boxCtor.getParameterTypes()[1].getSimpleName());
        System.out.println("box generic=" + generic[0].getTypeName()
                + "," + generic[1].getTypeName());
        System.out.println("constructor type parameter="
                + boxCtor.getTypeParameters()[0].getName());
        System.out.println("class type parameter=" + Box.class.getTypeParameters()[0].getName());
        System.out.println("box declaring=" + boxCtor.getDeclaringClass().getSimpleName());
    }
}
~~~

Từ thư mục có file, biên dịch bằng Java 17 và chạy:

~~~bash
javac --release 17 -encoding UTF-8 ConstructorInheritanceDemo.java
java ConstructorInheritanceDemo
~~~

Stdout (đã thực thi với `javac --release 17` trên JDK 21):

~~~text
Parent(7)
Child(Ada)
child type=Child
child public constructors=1
Child(int)=not found
parent int protected=true
parent declaring=Parent
box value=payload
box erased=Object,Object
box generic=E,U
constructor type parameter=U
class type parameter=E
box declaring=Box
~~~

Cách diễn giải:

1. `childCtor.newInstance("Ada")` tạo **Child**, chạy `Parent(int)` do `super(7)`, sau đó chạy phần thân constructor Child. Điều đó **không phải thừa kế constructor**.
2. `Child.class.getConstructors().length` là 1 vì Child chỉ khai báo một constructor public `Child(String)`; public `Parent()` không được liệt kê cho Child.
3. `Child.class.getConstructor(int.class)` thất bại vì Child không sở hữu `Child(int)`, dù Parent có `Parent(int)`.
4. `Parent.class.getDeclaredConstructor(int.class)` tìm được constructor protected do Parent khai báo. `getDeclaringClass()` trả Parent.
5. `Box<E>` có constructor generic `<U> Box(E value, U marker)`. Sau erasure, hai kiểu tham số runtime đều là `Object`, nên lookup nhận `Object.class, Object.class`.
6. `getGenericParameterTypes()` phản ánh chữ ký khai báo `E,U`; `getTypeParameters()` **trên Constructor** chỉ trả `U`, trong khi `Box.class.getTypeParameters()` trả `E`. `Constructor<Box>` biểu diễn kiểu class được tạo (raw Box trong ví dụ), **không biểu diễn U**.

Ví dụ dùng `Constructor<Box>` raw để truy vấn trực tiếp `Box.class`; trong code thư viện generic nghiêm ngặt, hãy quản lý type safety riêng và tránh giả định Reflection biết `Box<String>` từ runtime `Box.class`. Việc `newInstance("payload", 123)` chấp nhận String/Integer không làm thay đổi erased parameter types.

## 5. Generic class và generic constructor: ba kiểu khác nhau

Xét:

~~~java
class Packet<E> {
    public <U extends Number> Packet(E payload, U version) {}
}
~~~

Có ba khái niệm:

- `E` thuộc về **Packet<E>**, được truy vấn bởi `Packet.class.getTypeParameters()`.
- `U` thuộc về **chính constructor**, được truy vấn bởi `Constructor.getTypeParameters()`; bound của U là Number.
- `T` trong API `Constructor<T>` là **class được tạo** (chẳng hạn Packet), không liên quan đến tên biến kiểu E/U ở mã khai báo.

Với `Packet.class.getConstructor(Object.class, Number.class)`, lookup dùng **erasure**: E thành Object vì E không có bound, U thành Number do có bound. Truy vấn `getGenericParameterTypes()` đọc được ký hiệu E, U nếu metadata được bảo toàn trong class file. Lưu ý `Class<Packet>` và `Constructor<Packet>` dùng **raw Packet** vì Java không có literal `Packet<String>.class`.

Nếu cần mô tả một type parameterized của class tại runtime, ta phải nắm giữ `Type`/`ParameterizedType` từ trường, phương thức, superclass, hoặc token kiểu thích hợp. Chỉ `Constructor<T>` không thể tái tạo type argument của mọi instance mà constructor tạo.

### Từ chữ ký generic sang lookup thực tế

| Khai báo constructor | `getDeclaredConstructor(...)` nhận |
| --- | --- |
| `Box(E value, U tag)` với E, U không bound | `Object.class, Object.class` |
| `Packet(E value, U num)`, U extends Number | `Object.class, Number.class` |
| `Child(String name)` | `String.class` |
| `Sample(int count, List<String> values)` | `int.class, List.class` |
| `Logger(String... messages)` | `String[].class` |

Đây là ví dụ về quy tắc tìm constructor; các class `Packet`, `Sample`, `Logger` là tên mô tả tình huống tương ứng chứ không phải một chương trình đã định nghĩa đầy đủ.

Không dùng wildcard hoặc `ParameterizedType` làm tham số cho `getDeclaredConstructor`: API này nhận `Class<?>...`, phù hợp kiểu sau erasure.

## 6. Gọi constructor và phân biệt các nhóm lỗi

Sau khi tìm được `Constructor<T>`, `newInstance(Object... initargs)` tạo object của declaring class; Reflection không truyền receiver như `Method.invoke`. Việc tìm thấy metadata chưa đủ để bảo đảm quyền truy cập hoặc đối số hợp lệ.

| Bước | Lỗi điển hình | Ý nghĩa |
| --- | --- | --- |
| Lookup | `NoSuchMethodException` | Sai danh sách kiểu runtime hoặc không có constructor phù hợp |
| Truy cập | `IllegalAccessException`, `InaccessibleObjectException` | Caller không có quyền gọi hoặc JPMS không cho phép mở quyền |
| Khởi tạo | `InstantiationException`, `IllegalArgumentException` | Kiểu không thể tạo trực tiếp hoặc đối số không hợp lệ |
| Thực thi constructor | `InvocationTargetException` | Mã trong quá trình khởi tạo instance ném lỗi; xem `getCause()` |
| Khởi tạo class | `ExceptionInInitializerError` | Static initialization thất bại trước khi chạy constructor |

Với constructor `private`, `getDeclaredConstructor` chỉ lấy metadata. `trySetAccessible()` có thể thất bại nếu module không mở package cho deep reflection; `exports` không thay thế `opens`. `Class.newInstance()` là API đã deprecated, nên ưu tiên chọn chữ ký qua `getDeclaredConstructor(...).newInstance(...)` và xử lý lỗi theo giai đoạn.

## 7. Các trường hợp đặc biệt cần nhận biết

- **Abstract class** có constructor để subclass gọi, nhưng không thể tạo trực tiếp instance của abstract class; interface không có constructor tạo object.
- **Enum** có constructor nội bộ nhưng `Constructor.newInstance` từ chối tạo thêm enum constant; record có canonical constructor tương ứng với các component, không kế thừa từ `Record`.
- **Non-static inner class** nhận enclosing instance dưới dạng tham số constructor đầu tiên ở runtime. Ví dụ `Outer.Inner(Outer, int)` có thể tương ứng với khai báo source `Inner(int)`.
- **Varargs** được biểu diễn bằng tham số mảng (như `String[].class`); khi gọi `newInstance`, truyền nguyên mảng thành một argument bằng cast `(Object)` khi cần.
- **Compiler-generated parameters** có thể xuất hiện với enum, local/anonymous class hoặc inner class. Đọc `getParameterTypes()` và metadata `Parameter`, không suy luận từ thứ tự liệt kê constructor hay tên tham số compiler sinh.

Các bài tiếp theo phân tích từng trường hợp với ví dụ chạy được. Trong bài này, điểm chính vẫn là `Constructor<T>` gắn với class khai báo và constructor của superclass không trở thành constructor của subclass.

## 8. Quy trình áp dụng thực tế

Khi một DI container, serializer, CLI parser hoặc factory dựa Reflection cần tạo instance:

1. **Chọn class thực sự định tạo.** Nếu cần Child, tra trên `Child.class`, không lấy `Constructor<Parent>` rồi mong tạo Child.
2. **Chọn phạm vi quyền.** `getConstructor` khi cần public API; `getDeclaredConstructor` khi code có lý do hợp lệ để dùng constructor non-public.
3. **Xác định tham số runtime chính xác.** Phân biệt primitive/boxed, varargs array, kiểu đã erasure và enclosing instance của inner class.
4. **Xem danh sách constructor nếu chưa biết signature.** Dùng `getDeclaredConstructors()`, `getParameterTypes()`, `getModifiers()`, `getGenericParameterTypes()` và lọc theo tiêu chí đã xác định; không đoán ngẫu nhiên qua thứ tự.
5. **Đối chiếu module access.** Nếu private/package-private nằm trong named module khác, cân nhắc factory API hoặc `opens` đúng package/caller thay vì mở rộng toàn bộ module.
6. **Gọi `newInstance` và bắt lỗi chính xác.** `InvocationTargetException.getCause()` giúp tìm lỗi do constructor; `NoSuchMethodException` thường là lỗi chọn signature.
7. **Không nhầm chuỗi constructor với inheritance.** Java sẽ chạy superclass constructor trong quá trình tạo subclass, nhưng Reflection vẫn giữ mỗi constructor thuộc đúng declaring class.

## 9. Câu hỏi tự kiểm tra

**1.** Parent có `public Parent(int id)`, Child extends Parent và chỉ có `public Child()` gọi `super(5)`. `Child.class.getConstructor(int.class)` tìm được không?

**Đáp án:** Không. Parent(int) không được kế thừa; Child chỉ khai báo Child().

**2.** `Constructor<Child> ctor = Child.class.getConstructor()`; `ctor.newInstance()` có thể trả Parent thay vì Child không?

**Đáp án:** Không. Generic type T và declaring class của Constructor là Child. Nếu tạo được, đối tượng là Child; constructor Parent có thể chạy như một phần khởi tạo đối tượng Child.

**3.** `class Box<E> { public <U extends Number> Box(E value, U version) {} }`. Có thể tìm bằng `Box.class.getConstructor(String.class, Integer.class)` không?

**Đáp án:** Không theo chữ ký được khai báo. Erasure là `Object.class, Number.class`. `String` và `Integer` là kiểu argument của một lần gọi cụ thể, không phải parameter types trong constructor descriptor.

**4.** `Constructor.getTypeParameters()` trên constructor ở câu 3 có trả E không?

**Đáp án:** Không. Nó trả U của constructor; E là type variable thuộc Box, xem `Box.class.getTypeParameters()`.

**5.** `getDeclaredConstructor()` tìm private no-arg constructor rồi: có luôn gọi được `newInstance()` không?

**Đáp án:** Không. Tra cứu metadata và quyền gọi khác nhau; cần Java access/JMPS opens phù hợp, hoặc dùng factory công khai.

**6.** Vì sao `Outer.Inner.class.getDeclaredConstructor(int.class)` có thể thất bại dù source có `Inner(int)`?

**Đáp án:** Non-static inner class có tham số enclosing instance được thêm vào constructor runtime; cần `Outer.class, int.class`.

**Ghi nhớ:** `Constructor<T>` mang kiểu class được khởi tạo; một generic constructor còn có type variables riêng, tra cứu theo erased parameter types. Constructor của superclass **được gọi khi khởi tạo subclass nhưng không bao giờ được kế thừa**. Luôn tra cứu constructor trên class bạn thực sự muốn tạo.

### Tài liệu tham khảo

- Java Language Specification 17, §8.2 (Class Members) và §8.8 (Constructor Declarations): https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html
- Java SE 17, `Class.getConstructor/getDeclaredConstructor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17, `Constructor<T>` và `newInstance`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html
- Java SE 17, `Executable` (type parameters, generic parameter types): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html
- dev.java — Invoking Constructors: https://dev.java/learn/api/reflection-method-handles/reflection/constructors/
