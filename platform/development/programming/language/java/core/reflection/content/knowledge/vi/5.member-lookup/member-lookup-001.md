# Tra cứu thành viên bằng Java Reflection: `Member`, `Field`, `Method`, `Constructor` và `Executable`

## 1. Mục tiêu và bức tranh tổng quan

Java Reflection cho phép chương trình **khám phá cấu trúc lớp tại thời điểm chạy**: lớp khai báo những trường nào, phương thức nào, constructor nào, kiểu tham số và kiểu trả về là gì, thành viên có `public` hay `private`, có thể gọi hoặc đọc giá trị ra sao. Chủ đề này tập trung vào **tra cứu thành viên** thông qua `java.lang.Class` và các kiểu trong `java.lang.reflect`.

Sơ đồ quan hệ API:

```text
java.lang.reflect.Member (interface)
├── Field implements Member
└── Executable (abstract class) implements Member
    ├── Method extends Executable
    └── Constructor<T> extends Executable
```

- `Member` diễn tả một **thành viên được khai báo bởi lớp/giao diện** ở mức thông tin chung: tên, lớp khai báo, modifiers, trạng thái synthetic.
- `Field` đại diện cho trường dữ liệu, bao gồm biến instance và biến `static`.
- `Method` đại diện cho phương thức, bao gồm phương thức instance, `static`, abstract, default của interface.
- `Constructor<T>` đại diện cho constructor của lớp, dùng để tạo instance.
- `Executable` gom API chung cho hai thứ **có danh sách tham số và có thể được thực thi** là `Method` và `Constructor`.

Điểm cần phân biệt: đối tượng `Method` hoặc `Field` là **metadata và cổng thao tác phản chiếu**, không phải giá trị của một trường hay lời gọi phương thức được thực thi sẵn. Bạn cần một đối tượng đích phù hợp cho thành viên instance.

## 2. Bảng đối chiếu nhanh các kiểu

| Kiểu | Cách lấy thường gặp | Thông tin đặc trưng | Thao tác chính |
|---|---|---|---|
| `Member` | Kiểu cha/interface của `Field`, `Method`, `Constructor` | `getName()`, `getDeclaringClass()`, `getModifiers()`, `isSynthetic()` | Chuẩn hóa thao tác tra cứu metadata |
| `Field` | `getField` / `getDeclaredField` | `getType()`, `getGenericType()`, `isEnumConstant()` | `get(object)`, `set(object, value)`, getter/setter kiểu nguyên thủy |
| `Method` | `getMethod` / `getDeclaredMethod` | `getReturnType()`, `getGenericReturnType()`, `isBridge()`, `isDefault()` | `invoke(target, args...)` |
| `Constructor<T>` | `getConstructor` / `getDeclaredConstructor` | `getDeclaringClass()`, danh sách tham số | `newInstance(args...)` |
| `Executable` | Ép/nhận từ `Method` hoặc `Constructor` | `getParameterTypes()`, `getParameters()`, `getExceptionTypes()`, `isVarArgs()` | Phân tích chữ ký và tham số chung |

`Method` và `Constructor` kế thừa `Executable`, vì vậy có thể xử lý cùng một luồng để liệt kê chữ ký. `Field` **không** phải `Executable` vì trường dữ liệu không có danh sách tham số. `Class<?>` là điểm khởi đầu: `SomeType.class`, `obj.getClass()` hoặc `Class.forName("package.Type")` khi cần nạp theo tên.

## 3. Chọn họ API để tìm metadata

Khi bắt đầu từ một `Class<?>`, hãy phân biệt **tra cứu một thành viên** theo tên/chữ ký với **liệt kê nhiều thành viên** để kiểm kê hoặc xây công cụ.

| Thành viên | Public lookup | Declared lookup |
|---|---|---|
| Field | `getField(name)` / `getFields()` | `getDeclaredField(name)` / `getDeclaredFields()` |
| Method | `getMethod(name, types...)` / `getMethods()` | `getDeclaredMethod(name, types...)` / `getDeclaredMethods()` |
| Constructor | `getConstructor(types...)` / `getConstructors()` | `getDeclaredConstructor(types...)` / `getDeclaredConstructors()` |

Với field và method, họ public lookup có thể tìm thành viên công khai được kế thừa; họ declared chỉ xem khai báo **ngay tại kiểu đang xét** nhưng bao gồm mọi mức truy cập. Constructor không kế thừa, nên cả hai họ chỉ tìm trên lớp đích. Method và constructor đòi dãy kiểu tham số khai báo chính xác; không áp dụng boxing hoặc giải overload khi **lookup**. Không dựa vào thứ tự mảng của các API liệt kê.

Các bài kế tiếp minh họa chi tiết phạm vi public/declared, chữ ký chính xác và chính sách duyệt phân cấp; phần còn lại của bài này tập trung vào các **đối tượng metadata** mà những API ấy trả về.

## 4. `Member`: thông tin chung về một thành viên

`Member` cung cấp:

- `getName()`: tên của thành viên; đối với `Constructor`, tên thường là tên đầy đủ của lớp khai báo, không phải ký hiệu `<init>`.
- `getDeclaringClass()`: **lớp hoặc interface thực sự khai báo thành viên**, có thể khác lớp dùng để tra cứu nó. Ví dụ tìm phương thức thừa kế trên `Child.class` nhưng `getDeclaringClass()` trả `Parent.class`.
- `getModifiers()`: một `int` chứa các bit biểu diễn modifiers. Dùng `java.lang.reflect.Modifier` như `Modifier.isPublic(flags)`, `isPrivate`, `isStatic`, `isFinal`, `isAbstract` thay vì so sánh trực tiếp các giá trị bit.
- `isSynthetic()`: trình biên dịch/JVM tạo thành viên phục vụ triển khai thay vì thành viên viết trực tiếp theo nghĩa thông thường trong mã nguồn.

```java
Member member = String.class.getMethod("length");
System.out.println(member.getName());                    // length
System.out.println(member.getDeclaringClass());          // class java.lang.String
System.out.println(Modifier.isPublic(member.getModifiers())); // true
```

Đoạn trên giả định import `java.lang.reflect.Member` và `java.lang.reflect.Modifier`, và chạy trong ngữ cảnh chấp nhận `NoSuchMethodException`.

Đừng nhầm `getDeclaringClass()` với `getClass()`. Ví dụ `method.getClass()` trả kiểu runtime của **đối tượng metadata**, còn `method.getDeclaringClass()` trả lớp chứa phương thức đó.

## 5. `Field`: tra cứu, đọc và ghi trường

`Field` cho biết:

- `getType()`: kiểu trường ở dạng `Class<?>`, ví dụ `int.class` hoặc `List.class`.
- `getGenericType()`: kiểu tổng quát ở dạng `Type` khi signature generic có sẵn, ví dụ `List<String>` được phản ánh qua `ParameterizedType`; cơ chế này **không** khôi phục kiểu tham số đã bị xóa của mọi đối tượng tại runtime.
- `getAnnotations()` / `getDeclaredAnnotations()`: metadata annotation có retention tại runtime.
- `isEnumConstant()`: trường đại diện một hằng của enum.
- `get(obj)`, `set(obj, value)`: đọc và ghi giá trị trường. Có các biến thể `getInt`, `setInt`, `getBoolean`... cho primitive.

Với **instance field**, truyền đối tượng chứa trường; với **static field**, truyền `null` trong `get(null)` hoặc `set(null, ...)`. Java kiểm tra quyền truy cập khi thực hiện thao tác.

```java
Field name = Student.class.getDeclaredField("name");
boolean allowed = name.trySetAccessible();
if (!allowed) {
    throw new IllegalStateException("Không được phép mở quyền truy cập");
}
Object current = name.get(student);
name.set(student, "An");
```

Đây là đoạn minh họa cần có lớp `Student` và biến `student` phù hợp. `trySetAccessible()` có thể trả `false` khi access không được phép theo cơ chế module; `setAccessible(true)` có thể ném `InaccessibleObjectException` trong tình huống tương đương. Nhiều trường hợp chỉ cần public API/getter/setter và không cần mở quyền.

Đối với trường `final`, đặc biệt `static final`, đừng xem Reflection là cơ chế cập nhật cấu hình runtime: việc sửa có hạn chế và liên quan tối ưu hóa/JVM, không bảo đảm hành vi mong muốn.

## 6. `Method` và `Executable`: phân tích chữ ký và thực thi

### 6.1. Thông tin của `Method`

`Method` kế thừa metadata chung rồi bổ sung:

- `getReturnType()`: kiểu trả về đã erasure ở dạng `Class<?>`; `void` được biểu diễn bởi `void.class`.
- `getGenericReturnType()`: biểu diễn tổng quát của kiểu trả về; nên kiểm tra `instanceof ParameterizedType` trước khi ép kiểu.
- `isBridge()`: có phải bridge method do compiler tạo để duy trì đa hình sau generic erasure hoặc covariant return không.
- `isDefault()`: có phải phương thức `default` của interface không.
- `getDefaultValue()`: giá trị mặc định của phần tử annotation, nếu có; không phải “giá trị trả về mặc định” của mọi method.
- `invoke(receiver, args...)`: gọi phản chiếu; với phương thức `static` truyền `null` làm receiver, với instance truyền đúng đối tượng.

`Method.invoke` trả `Object`: primitive return được boxing; phương thức trả `void` cho `null`. Nếu code bên trong phương thức bị lỗi, ngoại lệ gốc được **bọc** trong `InvocationTargetException`; xem `getCause()` để biết nguyên nhân thực.

### 6.2. API chung của `Executable`

Áp dụng cho cả `Method` và `Constructor`:

| API | Ý nghĩa |
|---|---|
| `getParameterCount()` | Số lượng tham số theo chữ ký phản chiếu |
| `getParameterTypes()` | Mảng `Class<?>[]` của kiểu tham số (sau erasure) |
| `getGenericParameterTypes()` | Mảng `Type[]` của kiểu tham số generic |
| `getParameters()` | Mảng `Parameter[]` để đọc tên, annotation, modifiers và metadata tham số |
| `getExceptionTypes()` | Mảng `Class<?>[]` các exception khai báo trong `throws` |
| `getGenericExceptionTypes()` | Kiểu generic của exception khai báo |
| `isVarArgs()` | Có khai báo tham số cuối ở dạng varargs (`...`) hay không |
| `getAnnotatedParameterTypes()` | Thông tin type-use annotations của các kiểu tham số |
| `getAnnotatedExceptionTypes()` | Type-use annotations của các kiểu exception khai báo |

`Parameter.getName()` **không mặc định bảo toàn tên viết trong source**. Khi biên dịch thông thường không có `-parameters`, tên có thể là `arg0`, `arg1`; dùng `javac -parameters` khi thật sự cần tên tham số runtime và nhớ kiểm tra `Parameter.isNamePresent()`. Tên tham số không phải thành phần để `getMethod` phân biệt overload.

Ví dụ tiện ích tái sử dụng:

```java
static void printSignature(Executable executable) {
    System.out.println("Tên: " + executable.getName());
    for (Class<?> type : executable.getParameterTypes()) {
        System.out.println("  Tham số: " + type.getTypeName());
    }
}
```

Hàm minh họa này cần import `java.lang.reflect.Executable`; truyền vào một `Method` hoặc `Constructor<?>` đều hợp lệ.

### 6.3. Varargs và mảng tham số

`String... args` được biểu diễn thành kiểu mảng `String[]` trong metadata; `isVarArgs()` là chỉ dấu cho cú pháp varargs ban đầu. Không giả định rằng `Method.invoke` luôn tự áp dụng cùng quy tắc varargs như lời gọi Java được compiler kiểm tra. Hãy cung cấp số đối số và kiểu theo API phản chiếu; với varargs, khi cần hãy đóng gói tham số cuối thành mảng đúng kiểu và tránh nhầm giữa mảng là *một argument* và mảng chứa *toàn bộ arguments*.

```java
Method join = Example.class.getMethod("join", String[].class);
Object result = join.invoke(example, (Object) new String[] {"A", "B"});
```

Ép mảng thành `Object` trong ví dụ minh họa là để truyền nó dưới dạng **một tham số** cho `invoke`; `Example` và `example` là đối tượng trong ngữ cảnh giả định.

## 7. `Constructor<T>`: khám phá và tạo instance

Constructor không có kiểu trả về và không được kế thừa. `Class<T>.getDeclaredConstructor(Class<?>... parameterTypes)` tìm đúng constructor do lớp đó khai báo, bất kể mức truy cập; `getConstructor(...)` chỉ tìm constructor `public`.

```java
Constructor<Student> ctor = Student.class.getDeclaredConstructor(String.class);
Student student = ctor.newInstance("Lan");
```

`newInstance` thực thi constructor thật và có thể bọc exception do constructor ném trong `InvocationTargetException`. Nếu constructor `private` nằm ngoài phạm vi được phép truy cập, cần xử lý quyền truy cập giống `Field`/`Method`; một module khác có thể từ chối mở quyền ngay cả khi gọi `setAccessible(true)`. Không thể dùng constructor của lớp trừu tượng để tạo instance; enum cũng không được tạo tùy tiện qua `Constructor.newInstance`.

Đối với chương trình mới, thường ưu tiên lời gọi constructor trực tiếp, factory method hoặc dependency injection; Reflection phù hợp khi lựa chọn kiểu/constructor chỉ được biết tại runtime, chẳng hạn serializer hoặc framework test.

## 8. Ví dụ Java 17+ đầy đủ: tra cứu, kế thừa, gọi method và đọc field

Lưu đoạn sau thành **`ReflectionMembersDemo.java`**. Chương trình minh họa đầy đủ: `Class`, `Member`, `Field`, `Method`, `Constructor` và `Executable`; đồng thời kiểm chứng khác biệt giữa lớp dùng để tra cứu và lớp khai báo method kế thừa.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ReflectionMembersDemo {
    interface Greeter {
        default String salutation() {
            return "Xin chào";
        }
    }

    static class Parent {
        public String inherited() {
            return "parent";
        }
    }

    static class Student extends Parent implements Greeter {
        private String name;

        public Student(String name) {
            this.name = name;
        }

        public String greet(String prefix) {
            return prefix + ", " + name;
        }

        public static int twice(int number) {
            return number * 2;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Student> type = Student.class;

        Constructor<Student> ctor = type.getDeclaredConstructor(String.class);
        Method inherited = type.getMethod("inherited");
        Method greet = type.getDeclaredMethod("greet", String.class);
        Method twice = type.getDeclaredMethod("twice", int.class);
        Field name = type.getDeclaredField("name");

        System.out.println("Constructor thuộc: "
                + ctor.getDeclaringClass().getSimpleName());
        System.out.println("Tên Field: " + name.getName());
        System.out.println("Method thuộc: "
                + inherited.getDeclaringClass().getSimpleName());

        Student student = ctor.newInstance("Lan");
        System.out.println("Gọi Method: " + greet.invoke(student, "Chào"));
        System.out.println("Method static: " + twice.invoke(null, 21));

        if (!name.trySetAccessible()) {
            throw new IllegalStateException("Không thể truy cập field name");
        }
        System.out.println("Field private: " + name.get(student));

        Executable executable = greet;
        System.out.println("Khả năng public: "
                + Modifier.isPublic(greet.getModifiers()));
        System.out.println("Số tham số: " + executable.getParameterCount());
        System.out.println("Kế thừa interface: "
                + type.getMethod("salutation").invoke(student));
    }
}
```

Biên dịch và chạy ở thư mục chứa file:

```bash
javac ReflectionMembersDemo.java
java ReflectionMembersDemo
```

Kết quả chuẩn:

```text
Constructor thuộc: Student
Tên Field: name
Method thuộc: Parent
Gọi Method: Chào, Lan
Method static: 42
Field private: Lan
Khả năng public: true
Số tham số: 1
Kế thừa interface: Xin chào
```

Giải thích các dòng đáng chú ý:

1. `getDeclaredConstructor(String.class)` tìm constructor được khai báo trong `Student`, rồi `newInstance("Lan")` tạo đối tượng.
2. `getMethod("inherited")` tìm được phương thức public từ `Parent`. Metadata trả `getDeclaringClass() == Parent.class` dù việc tra cứu bắt đầu tại `Student.class`.
3. `getDeclaredMethod("greet", String.class)` tìm phương thức ngay trong `Student`; `Method.invoke` gọi nó trên `student` với đối số `"Chào"`.
4. Phương thức `static` `twice` được gọi với receiver `null`, nên trả 42.
5. `name` là trường `private`, nên dùng `getDeclaredField`; `trySetAccessible()` kiểm tra mở quyền trước `get`. Ví dụ khai báo lớp lồng nhau trong cùng một chương trình, tránh phụ thuộc vào module ngoài.
6. Biến `Executable executable = greet` cho thấy method chia sẻ API chữ ký qua `Executable`. `Modifier.isPublic` xử lý bit modifier đúng cách.
7. Phương thức `default` của `Greeter` có thể tìm qua `getMethod` trên `Student.class`.

## 9. Quyền truy cập, module và giới hạn thực tế

Reflection **không đồng nghĩa quyền truy cập vô hạn**. Ba câu hỏi phải tách biệt:

1. **Có tìm thấy metadata không?** `getDeclaredField` có thể tìm được field `private`.
2. **Có được phép truy cập/thực thi không?** `get`, `set`, `invoke` hoặc `newInstance` vẫn kiểm tra quyền.
3. **Có được phép *mở rộng* quyền Reflection không?** `trySetAccessible()`/`setAccessible(true)` bị ràng buộc bởi Java module system (JPMS) và khả năng truy cập giữa module/package.

Từ Java 9+, module có strong encapsulation. Với module có tên, việc truy cập sâu vào thành viên non-public từ module khác thường cần package được `opens` đúng đích. Ví dụ trong `module-info.java` của module sở hữu lớp:

```java
module school.model {
    opens school.model.internal to school.tooling;
}
```

`opens` phục vụ deep reflection vào package; `exports` phục vụ truy cập thông thường vào kiểu public và **không thay thế** `opens` cho mọi tình huống Reflection private. Lựa chọn khả dụng tùy module và quyền sở hữu package. Cân nhắc API public trước khi mở rộng quyền reflection.

Các ngoại lệ và lỗi thường gặp:

| Tình huống | Ngoại lệ / kết quả |
|---|---|
| Tra cứu sai tên hoặc sai signature method | `NoSuchMethodException` |
| Tra cứu tên field không tồn tại | `NoSuchFieldException` |
| Thao tác thành viên không có quyền | `IllegalAccessException`, hoặc lỗi truy cập tương ứng |
| Cố `setAccessible(true)` khi package không thể mở | `InaccessibleObjectException` (runtime) |
| Receiver không phù hợp hoặc đối số không khớp | `IllegalArgumentException` |
| Method/constructor bên trong ném ngoại lệ | `InvocationTargetException`; truy nguyên bằng `getCause()` |
| Gọi phương thức instance với receiver `null` | `NullPointerException` |
| Tạo instance qua constructor của kiểu trừu tượng | `InstantiationException` |
| `trySetAccessible()` không mở được quyền | Trả `false`; có thể có ngoại lệ khác theo API và bối cảnh |

`ReflectiveOperationException` là lớp cha hữu ích cho nhiều checked exceptions Reflection như `NoSuchMethodException`, `NoSuchFieldException`, `IllegalAccessException`, `InstantiationException` và `InvocationTargetException`, nhưng **không** bao quát mọi lỗi runtime ở bảng trên.

Với lỗi từ method đích, bắt ngoại lệ phù hợp và xem nguyên nhân:

```java
try {
    method.invoke(target);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable original = ex.getCause();
    System.err.println("Lỗi bên trong method: " + original);
}
```

Đây là ví dụ xử lý lỗi trong ngữ cảnh đã có `method` và `target`, không phải mã độc lập. Trong sản phẩm thực tế, chọn chiến lược log/propagate phù hợp và tránh làm mất stack trace.

## 10. Những bẫy cần nhớ khi viết công cụ Reflection

- **Nhầm declared với inherited:** metadata declared chỉ phản ánh kiểu được chọn; cần quyết định có xét lớp cha, interface hay không.
- **Nhầm public với accessible:** thành viên `public` không tự động có thể gọi từ mọi module/ngữ cảnh; lớp khai báo và chính sách module cũng quan trọng.
- **Sai signature vì autoboxing/widening:** `getDeclaredMethod("f", int.class)` không thể tùy tiện đổi thành `Integer.class`; hãy xác định đúng parameter types.
- **Quên generic erasure:** `getType()` trả kiểu thô như `List.class`; `getGenericType()` trả `Type` và có thể cần xử lý `ParameterizedType`, `TypeVariable`, `WildcardType`.
- **Phụ thuộc tên tham số:** source parameter names thường không tồn tại nếu thiếu `-parameters`.
- **Coi mọi method phản chiếu là do người viết:** có thể xuất hiện method bridge/synthetic do compiler; kiểm tra `isBridge()`, `isSynthetic()` khi xây API scanner.
- **Dựa vào thứ tự liệt kê:** nếu cần hiển thị ổn định, tự sắp xếp theo quy tắc rõ ràng, ví dụ tên, số tham số và tên đầy đủ các parameter types.
- **Gọi nhầm receiver:** method/field instance cần object tương thích; static dùng receiver `null`.
- **Đọc/ghi private hoặc final tràn lan:** ưu tiên contract public; Reflection có thể phá vỡ tính đóng gói và khiến nâng cấp JDK/module khó hơn.
- **Cho phép input không tin cậy tùy ý chọn class/method:** công cụ động phải giới hạn danh sách lớp, thành viên, quyền thao tác và kiểu đối số được phép; tránh tạo API thực thi tùy ý.
- **Bỏ qua chi phí:** tra cứu metadata lặp lại trong đường chạy nóng có thể gây overhead; cache các `Method`/`Field`/`Constructor` phù hợp khi có lý do đo được, không cache bất cẩn qua nhiều class loader.

## 11. Checklist áp dụng và câu hỏi tự kiểm tra

Một quy trình thực tế để xây trình tra cứu:

1. Xác định `Class<?>` của đối tượng/lớp cần nghiên cứu.
2. Chọn `getXxx` nếu muốn thành viên public có thể thừa kế; chọn `getDeclaredXxx` nếu muốn thành viên khai báo ngay tại lớp, bất kể mức truy cập.
3. Với Method/Constructor, xác định **chính xác** các `Class<?>` tham số trước khi tra cứu; với Field, xác định tên khai báo.
4. Xem `getDeclaringClass()`, `getModifiers()`, `getType()`/`getReturnType()` và `Executable.getParameterTypes()` để kiểm tra chữ ký.
5. Chỉ thực thi `invoke`/`newInstance` hay đọc/ghi `get`/`set` sau khi biết receiver, đối số và điều kiện truy cập.
6. Xử lý riêng lỗi tra cứu, lỗi quyền truy cập, lỗi đối số và lỗi phát sinh **bên trong** method/constructor.
7. Nếu dùng scanner/framework, xử lý bridge/synthetic, generic metadata và thứ tự hiển thị một cách có chủ đích.

Tự kiểm tra:

- Vì sao `Child.class.getMethod("parentPublic")` có thể thành công nhưng `Child.class.getDeclaredMethod("parentPublic")` thất bại?
- Khi nào dùng `Field.get(null)`? Khi nào `Method.invoke(null, ...)`?
- `getReturnType()` khác `getGenericReturnType()` như thế nào với `List<String>`?
- Tại sao `getDeclaredField("secret")` thành công vẫn chưa bảo đảm `field.get(instance)` thành công?
- Ngoại lệ nào bao bọc exception do method thật ném, và tìm nguyên nhân gốc ra sao?
- `Executable` cung cấp điểm chung nào để viết một hàm in chữ ký dùng được cho cả `Method` và `Constructor`?

Tài liệu chuẩn để đối chiếu API: [`Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`Member`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Member.html), [`Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html), [`Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), [`Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html), [`Executable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html).