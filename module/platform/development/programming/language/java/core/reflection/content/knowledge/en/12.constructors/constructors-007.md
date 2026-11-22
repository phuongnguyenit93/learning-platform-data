# Constructor của non-static inner class và tham số đối tượng bao ngoài

## 1. Bản chất vấn đề

Trong Java, một **non-static member class** (lớp thành viên không có `static`), còn gọi là *non-static inner class*, gắn mỗi đối tượng của nó với một **immediately enclosing instance**: một đối tượng của lớp bao ngoài trực tiếp. Đối tượng bao ngoài cho phép inner class dùng `Outer.this` và truy cập các thành viên instance của outer class, kể cả `private` theo các quy tắc ngôn ngữ.

Ví dụ nguồn:

```java
class Outer {
    private final String prefix;

    Outer(String prefix) {
        this.prefix = prefix;
    }

    class Inner {
        private final int id;

        Inner(int id) {
            this.id = id;
        }

        String description() {
            return Outer.this.prefix + "-" + id;
        }
    }
}
```

Cách tạo thông thường:

```java
Outer outer = new Outer("A");
Outer.Inner inner = outer.new Inner(5);
```

Constructor trong mã nguồn viết `Inner(int id)` và lời gọi Java dùng `outer.new Inner(5)`. Nhưng khi Reflection tìm constructor tương ứng, danh sách kiểu tham số còn có **tham số đứng đầu đại diện cho `Outer`**:

```java
Constructor<Outer.Inner> constructor =
        Outer.Inner.class.getDeclaredConstructor(Outer.class, int.class);
Outer.Inner reflected = constructor.newInstance(outer, 5);
```

Những đoạn code trên là **mã minh họa**: cần `import java.lang.reflect.Constructor;` và khai báo checked exceptions cho lời gọi Reflection. Ví dụ hoàn chỉnh có lệnh biên dịch ở mục 4.

Ý chính: **mã nguồn chỉ viết một tham số `int`, nhưng Reflection nhận diện constructor của inner class này có hai tham số runtime: `Outer` trước, rồi `int`**. `outer` phải là một instance phù hợp, không phải `Outer.class` hay tên class dưới dạng chuỗi.

## 2. Hai cách viết tương ứng

| Góc nhìn | Ví dụ | Enclosing instance đi đâu? |
| --- | --- | --- |
| Java source | `outer.new Inner(5)` | Gắn với biểu thức `outer` đứng trước `.new` |
| Reflection — tra cứu | `getDeclaredConstructor(Outer.class, int.class)` | Kiểu `Outer` trở thành kiểu tham số thứ nhất |
| Reflection — tạo đối tượng | `constructor.newInstance(outer, 5)` | Giá trị `outer` trở thành đối số thứ nhất |
| Reflection — lấy danh sách kiểu | `constructor.getParameterTypes()` | Trả kiểu `Outer` rồi `int` |
| Reflection — đếm tham số | `constructor.getParameterCount()` | Trả `2` trong ví dụ |

**Đừng nhầm hai tham số của hai API:**

- `getDeclaredConstructor(Outer.class, int.class)` nhận **kiểu của các tham số** (đối tượng `Class<?>`) để tìm đúng constructor.
- `newInstance(outer, 5)` nhận **giá trị của các đối số** (object reference `outer` và giá trị `int` được boxing khi truyền vào `Object...`).

`getDeclaredConstructor(int.class)` sẽ **không tìm được** constructor này, dù nguồn ghi `Inner(int)`. Reflection không tự thêm đối tượng bao ngoài khi tìm constructor hoặc gọi `newInstance`.

### Vì sao compiler cần tham số bổ sung?

Cú pháp `outer.new Inner(5)` đã chỉ rõ đối tượng bao ngoài. Ở biểu diễn runtime, cần cách để chuyển tham chiếu này vào lúc khởi tạo. Constructor của non-static inner class nhận tham chiếu outer như đối số bổ sung ở đầu danh sách, rồi mới tới những tham số được khai báo trong nguồn. Cơ chế này được định nghĩa bởi hợp đồng Reflection và ngữ nghĩa inner-class của Java.

Một Java compiler thường dùng field ẩn, chẳng hạn `this$0`, để giữ tham chiếu outer. Tuy nhiên, **`this$0` là chi tiết biên dịch không được bảo đảm là tên field ổn định**. Compiler/version/việc inner class có thực sự dùng outer state hay không có thể ảnh hưởng bytecode. Khi tra cứu và gọi constructor bằng Reflection, dựa trên **constructor signature và hành vi chuẩn**, không tự phụ thuộc tên field mà compiler sinh ra.

## 3. Phân biệt non-static inner với static nested class

`static nested class` cũng được khai báo bên trong một class nhưng **không cần enclosing instance**. Nó không có tham số constructor ẩn chỉ để mang object của outer.

```java
class Outer {
    class Inner {
        Inner(int number) {}
    }

    static class Nested {
        Nested(int number) {}
    }
}
```

Cách gọi thông thường:

```java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner(10);
Outer.Nested nested = new Outer.Nested(10);
```

Cách tra cứu bằng Reflection:

```java
Constructor<?> innerCtor =
        Outer.Inner.class.getDeclaredConstructor(Outer.class, int.class);
Constructor<?> nestedCtor =
        Outer.Nested.class.getDeclaredConstructor(int.class);
```

| Khía cạnh | `Outer.Inner` | `Outer.Nested` |
| --- | --- | --- |
| Có modifier `static`? | Không | Có |
| Liên kết với `Outer` instance? | Có | Không |
| Cách tạo bằng Java | `outer.new Inner(10)` | `new Outer.Nested(10)` |
| Tham số khai báo nguồn | `int` | `int` |
| Tham số constructor qua Reflection | `Outer, int` | `int` |
| Có cần truyền object `Outer` vào `newInstance`? | Có | Không |

**Cả hai đều là nested member classes.** `Class.getEnclosingClass()` và `Class.getDeclaringClass()` có thể trả `Outer.class` cho cả `Inner` lẫn `Nested`; chỉ dựa vào hai API đó **không đủ** để suy luận constructor cần tham số outer. Với member class, kết hợp `Class.isMemberClass()` và `Modifier.isStatic(clazz.getModifiers())`. Sau đó luôn kiểm tra signature constructor thực tế.

Một lớp top-level không có enclosing class/member relationship; một local/anonymous class có quy tắc compiler-generated parameter riêng. Không đồng nhất tất cả dạng nested class thành một kiểu constructor.

## 4. Chương trình Java 17+ chạy được

Tạo tệp **`InnerConstructorDemo.java`** với nội dung:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;

public class InnerConstructorDemo {

    public static class Outer {
        private final String prefix;

        public Outer(String prefix) {
            this.prefix = prefix;
        }

        public class Inner {
            private final int number;

            public Inner(int number) {
                this.number = number;
            }

            public String label() {
                return prefix + "-" + number;
            }
        }

        public static class Nested {
            private final int number;

            public Nested(int number) {
                this.number = number;
            }

            public String label() {
                return "N-" + number;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Outer outerA = new Outer("A");
        Outer.Inner direct = outerA.new Inner(5);
        System.out.println("direct: " + direct.label());

        Class<Outer.Inner> innerType = Outer.Inner.class;
        System.out.println("inner is member: " + innerType.isMemberClass());
        System.out.println("inner static: "
                + Modifier.isStatic(innerType.getModifiers()));
        System.out.println("inner declaring class: "
                + (innerType.getDeclaringClass() == Outer.class));

        Constructor<Outer.Inner> innerCtor =
                innerType.getDeclaredConstructor(Outer.class, int.class);

        System.out.println("inner parameter count: "
                + innerCtor.getParameterCount());
        System.out.println("first is Outer: "
                + (innerCtor.getParameterTypes()[0] == Outer.class));
        System.out.println("second is int: "
                + (innerCtor.getParameterTypes()[1] == int.class));

        try {
            innerType.getDeclaredConstructor(int.class);
        } catch (NoSuchMethodException e) {
            System.out.println("missing Outer lookup: NoSuchMethodException");
        }

        Outer outerB = new Outer("B");
        Outer.Inner reflected = innerCtor.newInstance(outerB, 9);
        System.out.println("reflected: " + reflected.label());

        Constructor<Outer.Nested> nestedCtor =
                Outer.Nested.class.getDeclaredConstructor(int.class);
        System.out.println("nested static: "
                + Modifier.isStatic(Outer.Nested.class.getModifiers()));
        System.out.println("nested parameter count: "
                + nestedCtor.getParameterCount());
        Outer.Nested nested = nestedCtor.newInstance(4);
        System.out.println("nested: " + nested.label());
    }
}
```

Biên dịch, chạy từ thư mục chứa file bằng JDK 17 trở lên:

```bash
javac InnerConstructorDemo.java
java InnerConstructorDemo
```

**Stdout:**

```text
direct: A-5
inner is member: true
inner static: false
inner declaring class: true
inner parameter count: 2
first is Outer: true
second is int: true
missing Outer lookup: NoSuchMethodException
reflected: B-9
nested static: true
nested parameter count: 1
nested: N-4
```

**Đọc kết quả:**

1. `outerA.new Inner(5)` sử dụng implicit enclosing instance `outerA`, do đó trả `A-5`.
2. `Outer.Inner.class` là member class, không có modifier `static`; lớp khai báo bao ngoài là `Outer`.
3. Constructor mà Reflection thấy là `(Outer, int)`, nên `getParameterCount()` bằng `2`. `getDeclaredConstructor(int.class)` ném `NoSuchMethodException`; đây là lỗi **tra cứu chữ ký**, chưa phải lỗi gọi constructor.
4. `innerCtor.newInstance(outerB, 9)` tạo inner object mới gắn với `outerB`. Method `label()` sử dụng `prefix` của `outerB` và in `B-9`, chứng minh tham số đầu là **giá trị enclosing instance**, không phải chỉ một marker trong signature.
5. `Outer.Nested` có `static`, không cần enclosing instance. Reflection tìm constructor với duy nhất `int.class` và gọi `newInstance(4)`.

Không cần `setAccessible(true)` trong ví dụ vì các nested types và constructors được khai báo `public` trong ngữ cảnh truy cập này. Cũng không cần dựng một `Outer` object chỉ để tạo `Outer.Nested`.

## 5. Constructor không có tham số tường minh vẫn cần outer

Một hiểu nhầm phổ biến là inner class có constructor không đối số trong nguồn thì Reflection dùng `getDeclaredConstructor()` trống.

```java
class Book {
    class Page {
        Page() {}
    }
}
```

Để tra cứu constructor của `Page`:

```java
Constructor<Book.Page> constructor =
        Book.Page.class.getDeclaredConstructor(Book.class);
Book book = new Book();
Book.Page page = constructor.newInstance(book);
```

Đây là **đoạn minh họa** phải đặt trong scope có quyền truy cập package-private constructor và có xử lý checked exceptions. Dù mã nguồn viết `Page()`, Reflective constructor vẫn có tham số đầu `Book`.

Nếu gọi `Book.Page.class.getDeclaredConstructor()`, bạn sẽ gặp `NoSuchMethodException` đối với chương trình này. Nếu tìm đúng constructor nhưng gọi `constructor.newInstance()` thiếu đối số outer, kết quả là `IllegalArgumentException` vì không đủ argument. Hai lỗi xảy ra ở **hai bước khác nhau**.

### Ví dụ inner class với nhiều tham số

```java
class Server {
    class Connection {
        Connection(String host, int port) {}
    }
}
```

Chữ ký constructor qua Reflection có dạng:

```java
Server.Connection.class.getDeclaredConstructor(
        Server.class, String.class, int.class);
```

Đầu tiên là **lớp bao ngoài trực tiếp**, tiếp đó là `String` và `int` được khai báo trong nguồn, giữ đúng thứ tự. Bên gọi phải truyền `Server` instance, `String` và `int`.

## 6. Enclosing instance khác gì `Class` metadata?

Ba cặp thông tin rất dễ bị lẫn:

- `Inner.class.getEnclosingClass()` cho biết **kiểu lớp bao quanh về mặt cấu trúc**. Nó trả đối tượng `Class<Outer>`, không phải một instance cụ thể của `Outer`.
- `Inner.class.getDeclaringClass()` cho biết **lớp khai báo member class** (đối với member class); cũng là metadata `Class`.
- Đối tượng outer thật mà inner object gắn vào là **giá trị tại runtime**, ví dụ `outerB`; có thể có vô số `Outer` instances và mỗi inner object gắn với một instance phù hợp.

`getEnclosingClass() == Outer.class` **không có nghĩa** Reflection có thể tự chọn instance outer. Bạn phải cung cấp đúng object để `Constructor.newInstance` tạo inner object. Hai `Outer` instance có thể cùng kiểu `Outer.class` nhưng mang trạng thái khác nhau, vì vậy không thể lấy `Outer.class` để thay cho reference thật.

**Không truyền `null` để giả lập outer object hợp lệ.** Hợp đồng constructor của non-static inner class yêu cầu một enclosing instance. Một số cách biên dịch/cơ chế thực thi có thể báo lỗi ở các bước khác nhau khi đưa `null`; đó không phải cách tạo một inner object liên kết hợp lệ và không nên dựa vào phản ứng ngoại lệ cụ thể của mọi compiler.

## 7. API Reflection nên dùng và các bước chính xác

### 7.1. `getDeclaredConstructor` hay `getConstructor`?

- `Class.getDeclaredConstructor(parameterTypes...)` tìm constructor được **khai báo trực tiếp**, bất kể modifier của constructor, theo đúng danh sách kiểu tham số.
- `Class.getConstructor(parameterTypes...)` tìm **public constructor** theo chữ ký. Với inner member class không static, danh sách kiểu vẫn phải có outer class ở vị trí đầu.
- `Class.getDeclaredConstructors()` trả toàn bộ constructor khai báo trực tiếp, hữu ích khi bạn chưa chắc signature. Đừng dựa vào thứ tự mảng constructors; hãy kiểm tra `getParameterTypes()` cho từng phần tử.
- `Constructor.getParameterTypes()` trả `Class<?>[]` theo thứ tự runtime; `getParameterCount()` cho số lượng tham số; `getGenericParameterTypes()` có thể giúp phân tích thông tin generic nếu metadata tương ứng được lưu và phản ánh phù hợp.

Mẫu tra cứu đáng tin:

```java
Class<?> inner = Outer.Inner.class;
for (Constructor<?> ctor : inner.getDeclaredConstructors()) {
    System.out.println(ctor.getParameterCount());
    // Xem ctor.getParameterTypes() để nhận diện đúng chữ ký.
}
```

Đây là đoạn minh họa, cần `import java.lang.reflect.Constructor;` và một lớp `Outer.Inner` hợp lệ. Nếu các constructor có overload, khớp **đầy đủ kiểu và thứ tự**, không chỉ đếm.

### 7.2. `Constructor.newInstance` thực sự làm gì?

`Constructor<T>.newInstance(Object... initargs)` tạo và khởi tạo một instance mới bằng constructor phản ánh. Với non-static inner member class, **đối số đầu tiên là enclosing instance**; các đối số kế tiếp tương ứng tham số được khai báo.

```java
Outer outer = new Outer("P");
Constructor<Outer.Inner> ctor =
        Outer.Inner.class.getDeclaredConstructor(Outer.class, int.class);
Outer.Inner child = ctor.newInstance(outer, 3);
```

Khác với `Class.newInstance()` cũ (đã deprecated), API `Constructor.newInstance` cho phép lựa chọn constructor theo tham số, cung cấp đúng đối số và bọc exception của constructor đích trong `InvocationTargetException`. Nó cũng giúp biểu diễn rõ ràng các lựa chọn truy cập.

### 7.3. Không tự động vượt qua quyền truy cập

Nếu inner class hoặc constructor không public, gọi `getDeclaredConstructor` để lấy metadata **không bảo đảm** `newInstance` có quyền sử dụng. Khi cần:

```java
Constructor<?> ctor = innerClass.getDeclaredConstructor(
        enclosingClass, int.class);

if (ctor.trySetAccessible()) {
    Object instance = ctor.newInstance(actualOuter, 3);
}
```

Đây là mẫu minh họa; `innerClass`, `enclosingClass` và `actualOuter` là các biến đã có sẵn. `trySetAccessible()` chỉ được cấp phép nếu Java access rules và JPMS cho phép. Với named module và deep reflection từ module khác, package có thể phải được `opens` đúng module của caller. Không xem việc truyền outer hợp lệ là quyền bỏ qua Java access checks.

## 8. `getParameters()`, tham số ẩn và metadata compiler

Một số chương trình mong có thể xác định tham số outer bằng:

```java
Parameter[] parameters = ctor.getParameters();
for (Parameter parameter : parameters) {
    System.out.println(parameter.getType());
    System.out.println(parameter.isImplicit());
    System.out.println(parameter.isSynthetic());
}
```

Đoạn minh họa này cần `java.lang.reflect.Parameter` và biến `ctor`. Các cờ như `isImplicit()`/`isSynthetic()` và tên tham số phụ thuộc metadata trong class file, đặc biệt `MethodParameters`, cũng như cấu trúc lớp và cách compiler tạo bytecode. **Không thể suy ra bảo đảm mọi compiler/phiên bản gắn cùng cờ hoặc cùng tên cho tham số outer chỉ từ việc thấy non-static inner class.**

Với `javac -parameters`, compiler thường ghi thêm tên/thuộc tính tham số để Reflection đọc được. Không có metadata tên, `Parameter.getName()` có thể trả tên tổng hợp như `arg0`; `isNamePresent()` cho biết có tên thật được lưu theo hợp đồng API hay không. Tên tham số outer có thể xuất hiện khác nhau, nên không làm công cụ dựa vào một tên như `this$0` hoặc `arg0`.

**Cách ổn định khi cần gọi constructor:** lấy danh sách `getParameterTypes()`, đối chiếu phần đầu với enclosing class và đưa đúng instance vào `newInstance`. Chỉ dùng metadata tham số để trình bày bổ sung, không thay cho signature.

### Kiểm tra bằng `javap`

Biên dịch `InnerConstructorDemo.java` rồi, trong thư mục có class file, có thể xem cấu trúc bằng lệnh:

```bash
javap -p 'InnerConstructorDemo$Outer$Inner'
javap -p 'InnerConstructorDemo$Outer$Nested'
```

Đây là ví dụ tham khảo cú pháp terminal hỗ trợ trích dẫn bằng dấu nháy đơn để ký tự `$` không bị diễn giải thành biến môi trường. **Trên Windows PowerShell**, cũng có thể dùng cách đặt tên lớp trong dấu nháy đơn. Với cấu trúc này, bạn sẽ thấy constructor của inner có tham số outer ở đầu, còn constructor của nested static không có tham số đó. Có thể chạy `javap -v -p` để xem metadata chi tiết hơn, nhưng không phụ thuộc tên field compiler tự sinh hoặc thứ tự hiển thị.

Công cụ đọc class file và Reflection phục vụ việc quan sát bytecode đã biên dịch; chúng không dựng lại nguyên vẹn cách viết mã nguồn.

## 9. Nested nhiều cấp và các lớp local/anonymous

### 9.1. Nested nhiều cấp

Giả sử:

```java
class Building {
    class Floor {
        class Room {
            Room(int number) {}
        }
    }
}
```

`Room` là inner member class trực tiếp nằm trong `Floor`. Khi dùng Reflection tìm constructor, tham số enclosing instance đầu tiên có kiểu **`Building.Floor`**:

```java
Constructor<Building.Floor.Room> ctor =
        Building.Floor.Room.class.getDeclaredConstructor(
                Building.Floor.class, int.class);
```

Muốn tạo `Room`, cần một `Floor` instance phù hợp; còn bản thân `Floor` instance gắn với một `Building` instance. Reflection không tự thêm lần lượt `Building` và `Floor` thành hai tham số riêng trong constructor của `Room` chỉ vì có hai tầng lexical nesting.

### 9.2. Local class và anonymous class không theo một khuôn

Local class nằm trong block và anonymous class có thể liên quan đến:

- Enclosing instance của non-static context;
- Các giá trị local hoặc tham số được capture (theo quy tắc effectively-final);
- Tham số bổ sung do compiler dùng để gọi superclass constructor hoặc thực hiện khởi tạo.

Chữ ký constructor thực tế của chúng có thể phức tạp và **phụ thuộc việc class được khai báo trong static hay non-static context, những giá trị được capture và compiler**. Không áp dụng máy móc công thức `Outer.class + các tham số nguồn` cho mọi local/anonymous class.

Trong bài này, công thức trọng tâm nhắm tới **non-static member inner class** như `Outer.Inner`. Đối với loại khác, kiểm tra `getEnclosingClass()`, `getEnclosingMethod()`, `getEnclosingConstructor()`, `isLocalClass()`, `isAnonymousClass()` và danh sách constructor thực tế; không giả định một chữ ký khi chưa quan sát.

### 9.3. Generic outer class

Ví dụ `Outer<String>.Inner` khi runtime vẫn có outer instance là object của `Outer`; kiểu tham số constructor phản ánh là `Outer.class` do type erasure, không thể tra cứu bằng cú pháp `Outer<String>.class` (Java không có class literal cho kiểu parameterized đó). Nếu cần kiểm tra generic metadata, hãy tìm `Signature`/Reflection generic APIs nếu được compiler lưu.

## 10. Lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `NoSuchMethodException` khi tìm `Inner(int)` | Quên tham số outer đứng đầu signature | Tìm `Inner(Outer, int)` |
| `IllegalArgumentException` từ `newInstance(5)` | Thiếu enclosing instance khi gọi | `newInstance(outer, 5)` |
| `IllegalArgumentException` do sai kiểu đầu tiên | Đưa object khác `Outer` vào tham số outer | Truyền instance `Outer` đúng kiểu |
| `IllegalAccessException` | Caller thiếu quyền gọi constructor | Kiểm tra modifier, package, module; dùng cơ chế access hợp lệ |
| `InaccessibleObjectException` khi bật access | JPMS không cho deep reflection | Kiểm tra package `opens` tới module caller |
| `InvocationTargetException` | Constructor đích ném exception | Xem `getCause()` để tìm lỗi trong constructor |
| `InstantiationException` | Lớp khai báo constructor không thể khởi tạo trong điều kiện API | Kiểm tra kiểu/constructor đích; không dùng với abstract class |
| Nhận nhầm `Nested` là `Inner` | Chỉ kiểm tra `getEnclosingClass()`, bỏ qua `static` | Kiểm tra `isMemberClass()` và `Modifier.isStatic` |
| Đọc field `this$0` rồi gắn chặt logic vào tên này | Phụ thuộc compiler-generated implementation detail | Dựa vào constructor signature và `newInstance` |
| Cho rằng mọi anonymous/local class có tham số đầu giống member inner class | Khái quát hóa quá mức | Quan sát constructors thực tế và bối cảnh khai báo |

**Phân biệt thời điểm lỗi:** `getDeclaredConstructor(...)` có thể thất bại trong bước **tìm chữ ký**; `newInstance(...)` có thể thất bại trong bước **kiểm tra đối số/quyền hoặc chạy constructor**. Gặp lỗi nào hãy kiểm tra đúng bước đó trước.

## 11. Bài tự kiểm tra

Cho lớp sau:

```java
class Company {
    class Employee {
        Employee(String name, int level) {}
    }

    static class Department {
        Department(String name) {}
    }
}
```

Hãy dự đoán trước khi chạy:

1. `Company.Employee.class.getDeclaredConstructor(String.class, int.class)` có tìm được constructor không?
2. Danh sách kiểu tham số đúng cho `Company.Employee` là gì?
3. `Company.Department.class.getDeclaredConstructor(String.class)` có cần `Company.class` đứng đầu không?
4. Khi gọi constructor của `Employee` qua `newInstance`, tham số đầu tiên cần **kiểu** hay **giá trị**?
5. Nếu có hai `Company` instances khác nhau, Reflection tự chọn instance nào?
6. `Company.Employee.class.getDeclaringClass() == Company.class` có đủ để tạo `Employee` không?

**Đáp án:**

1. Không; thiếu `Company.class` trong lookup, nên `NoSuchMethodException`.
2. `(Company.class, String.class, int.class)`.
3. Không; `Department` là `static nested class`.
4. Đưa **giá trị `Company` instance**; `Company.class` chỉ dùng khi tra cứu signature.
5. Không tự chọn; caller truyền đối tượng bao ngoài cụ thể vào `newInstance`.
6. Không. `getDeclaringClass()` chỉ cung cấp class metadata; vẫn phải có `Company` instance phù hợp và cung cấp các tham số constructor.

## 12. Ghi nhớ

**Non-static member inner class có enclosing instance**. Khi Reflection lấy constructor của nó, hãy tính **kiểu enclosing class là tham số đứng đầu**, rồi nối tiếp các kiểu tham số mà mã nguồn khai báo; khi gọi `newInstance`, cung cấp **đối tượng outer thật** trước các đối số tường minh.

Phân biệt với `static nested class` không cần đối tượng outer. Dùng `getParameterTypes()` để xác minh signature, `Modifier.isStatic()` để hỗ trợ phân loại member class, xử lý đúng quyền truy cập và exception. Không phụ thuộc vào tên field/parameter compiler tự sinh; với local/anonymous classes, cần khảo sát bytecode cụ thể thay vì áp dụng một công thức duy nhất.

Tài liệu chuẩn để đối chiếu:

- [Java SE 17 — `Class.getDeclaredConstructor` và `Class.getConstructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — `Constructor.newInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html)
- [Java Language Specification `8.8.1 và `15.9.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html)
