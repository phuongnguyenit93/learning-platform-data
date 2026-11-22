# Vai trò của `Class` và `java.lang.reflect` trong Java

## 1. Reflection là gì, và hai thành phần này làm việc cùng nhau như thế nào?

Trong Java, mã thông thường đã biết kiểu và phương thức lúc biên dịch: `user.greet("Chào")`. **Reflection** cung cấp cách **khám phá cấu trúc của kiểu tại runtime**, sau đó (nếu được phép) tạo đối tượng, đọc/ghi field hoặc gọi method thông qua metadata. Tình huống điển hình là một framework chỉ biết tên lớp hoặc annotation từ cấu hình nhưng phải tìm constructor, khởi tạo đối tượng và gọi method khi chương trình chạy.

Hai lớp khái niệm có trách nhiệm riêng:

- **`java.lang.Class<T>`**: đối tượng mô tả **kiểu runtime**; là điểm vào để tìm thông tin tên, kế thừa, interface, annotation, field, method và constructor.
- **`java.lang.reflect`**: gói API cung cấp các đối tượng mô tả **thành viên và chữ ký kiểu** (`Field`, `Method`, `Constructor`, `Type`...) và thao tác phản chiếu lên chúng.

`Class` **thuộc `java.lang`**, không thuộc `java.lang.reflect`. Luồng chung là: **lấy `Class<?>` → tìm `Method`/`Field`/`Constructor` → kiểm tra quyền truy cập và kiểu → thao tác → xử lý ngoại lệ**. Tìm thấy một thành viên qua metadata không có nghĩa chương trình tự động có quyền sử dụng thành viên ấy.

## 2. `Class<T>`: định danh và thông tin của kiểu runtime

Đối tượng `Class` không phải là instance của kiểu được mô tả. `String.class` là đối tượng metadata kiểu `Class<String>`; còn `"abc"` mới là instance `String`. Mỗi kiểu mà JVM biết đến đều có biểu diễn `Class`, kể cả class, interface, enum, record, array, kiểu primitive và `void`.

Các cách lấy `Class`:

```java
Class<String> byLiteral = String.class;

String text = "Java";
Class<? extends String> byObject = text.getClass();

Class<?> byName = Class.forName("java.lang.String");

Class<?> primitiveType = int.class;
Class<?> arrayType = String[].class;
```

Đoạn trên chỉ là **minh họa trong phạm vi method**; lệnh `Class.forName(...)` phải xử lý `ClassNotFoundException`. `obj.getClass()` phản ánh kiểu runtime thực và gây `NullPointerException` nếu `obj` là `null`. `Class.forName(String)` mặc định có thể kích hoạt việc khởi tạo lớp; overload `Class.forName(name, false, loader)` yêu cầu nạp mà chưa khởi tạo ngay.

| Phương thức của `Class` | Câu hỏi trả lời |
| --- | --- |
| `getName()`, `getSimpleName()`, `getCanonicalName()` | Kiểu tên tương ứng; lớp lồng có dấu `$` trong tên nhị phân |
| `getSuperclass()`, `getInterfaces()` | Superclass và các interface trực tiếp |
| `isInterface()`, `isEnum()`, `isRecord()`, `isArray()`, `isPrimitive()` | Đây là loại kiểu nào? |
| `getComponentType()` | Kiểu phần tử của array hay `null` nếu không phải array |
| `getModifiers()` | Modifier của lớp, giải mã với `Modifier` |
| `getAnnotations()`, `getDeclaredAnnotations()` | Annotation có thể quan sát được tại runtime |
| `isInstance(obj)`, `cast(obj)`, `asSubclass(Base.class)` | Kiểm tra/biểu diễn quan hệ kiểu an toàn |
| `getClassLoader()`, `getModule()` | Bối cảnh nạp lớp và module |

Generic của `Class<T>` cung cấp kiểm tra kiểu ở compile time: khi biết chính xác lớp, ưu tiên `Class<User>`; khi nhận kiểu động, dùng `Class<?>` thay vì raw type `Class`. Lưu ý **danh tính JVM của class phụ thuộc cả class loader**: hai loader có thể định nghĩa cùng một tên lớp nhưng tạo hai kiểu không tương thích. Vì vậy so sánh mỗi chuỗi `getName()` chưa đủ để khẳng định hai class có cùng danh tính.

## 3. `java.lang.reflect`: từ metadata tới thao tác

| API | Vai trò |
| --- | --- |
| `Constructor<T>` | Mô tả constructor; `newInstance(args...)` tạo object |
| `Method` | Mô tả method; `invoke(receiver, args...)` gọi method |
| `Field` | Mô tả field; `get(receiver)` / `set(receiver, value)` khi có quyền |
| `Modifier` | Giải mã bit modifier, ví dụ `Modifier.isPublic(...)` |
| `Executable`, `Parameter` | Metadata chung của method/constructor và tham số |
| `Type`, `ParameterizedType`, `TypeVariable`, `WildcardType` | Chữ ký kiểu generic được khai báo |
| `Array` | Tạo hoặc truy cập mảng động qua reflection |
| `Proxy`, `InvocationHandler` | Proxy động dựa trên interface |
| `RecordComponent` | Metadata từng thành phần record |

`Class` trả về những metadata này, chẳng hạn `User.class.getDeclaredFields()` trả về một mảng `Field[]`. Các đối tượng phản chiếu có thể chứa tên, kiểu, modifier và annotation; một số còn có khả năng tác động tới instance khi các kiểm tra access cho phép.

### `get...` và `getDeclared...` khác nhau ra sao?

| Tra cứu | Chỉ public hay mọi visibility? | Có tìm phần kế thừa? |
| --- | --- | --- |
| `getMethod(name, parameterTypes...)` / `getMethods()` | Public | Có, method public kế thừa |
| `getDeclaredMethod(...)` / `getDeclaredMethods()` | Mọi visibility | Không: chỉ khai báo trực tiếp |
| `getField(name)` / `getFields()` | Public | Có, field public kế thừa |
| `getDeclaredField(name)` / `getDeclaredFields()` | Mọi visibility | Không: chỉ khai báo trực tiếp |
| `getConstructor(...)` / `getConstructors()` | Public | Không: constructor không kế thừa |
| `getDeclaredConstructor(...)` / `getDeclaredConstructors()` | Mọi visibility | Không: constructor không kế thừa |

**Chữ ký tra cứu phải chính xác.** Nếu có `setAge(int)`, phải dùng `getMethod("setAge", int.class)`; `Integer.class` là kiểu khác. Việc tìm method không đoán overload từ giá trị truyền vào; method lookup dùng tên và các kiểu tham số khai báo. Thứ tự các mảng trả về bởi `getDeclaredMethods()`, `getMethods()`... **không được bảo đảm**, nên nếu cần đầu ra xác định, hãy sắp xếp chúng theo tiêu chí rõ ràng.

## 4. Ví dụ Java 17+ đầy đủ, chạy được

Chương trình minh họa chuỗi điển hình: `Class` → tìm constructor → khởi tạo → tìm method → gọi động → khảo sát field private qua metadata. Để giữ tính di động, ví dụ **không truy cập dữ liệu private**, chỉ xem tên và kiểu của field.

Tạo tệp `ReflectionDemo.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionDemo {
    public static class User {
        private final String name;

        public User(String name) {
            this.name = name;
        }

        public String greet(String prefix) {
            return prefix + ", " + name;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<User> type = User.class;

        System.out.println(type.getName());
        System.out.println(type.getSuperclass().getSimpleName());

        Constructor<User> constructor =
                type.getDeclaredConstructor(String.class);
        User user = constructor.newInstance("Lan");

        Method greet = type.getMethod("greet", String.class);
        Object result = greet.invoke(user, "Xin chào");
        System.out.println(result);

        Field field = type.getDeclaredField("name");
        System.out.println(field.getName() + ": " +
                field.getType().getSimpleName());

        System.out.println(type.isInstance(user));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac ReflectionDemo.java
java ReflectionDemo
```

Stdout:

```text
ReflectionDemo$User
Object
Xin chào, Lan
name: String
true
```

Giải thích chính xác từng phần:

1. `User.class` trả về `Class<User>`; do đây là lớp lồng static, tên nhị phân là `ReflectionDemo$User`. Superclass trực tiếp là `Object`.
2. `getDeclaredConstructor(String.class)` tìm constructor nhận đúng một `String`. `newInstance("Lan")` thực sự chạy constructor để tạo `User`.
3. `getMethod("greet", String.class)` tra cứu method public nhận `String`. `invoke(user, "Xin chào")` gọi method trên instance `user`, trả về `Object` chứa chuỗi kết quả.
4. `getDeclaredField("name")` trả về metadata của field private, dù không có getter. `getName()` và `getType()` không cần đọc giá trị field.
5. `isInstance(user)` kiểm tra tương thích kiểu thực của đối tượng.

Ở đây kiểu `User` đã biết từ compile time, nên mã trực tiếp `new User("Lan")` và `user.greet("Xin chào")` vẫn đơn giản, dễ refactor và có type checking tốt hơn. Reflection có giá trị khi kiểu hoặc method chỉ được xác định **lúc runtime**.

## 5. Ranh giới truy cập, module và ngoại lệ

Reflection vẫn chịu quy tắc access của Java:

- `getDeclaredField("name")` có thể tìm metadata của field private, nhưng `field.get(user)` thường ném `IllegalAccessException` khi caller không có quyền truy cập.
- `AccessibleObject.trySetAccessible()` hoặc `setAccessible(true)` cho phép **thử** truy cập sâu trong những trường hợp được JVM/module cho phép. `trySetAccessible()` có thể trả `false`, còn `setAccessible(true)` có thể ném `InaccessibleObjectException`; không phải cơ chế vượt mọi ranh giới module.
- Theo **JPMS**, `exports` cho phép code ngoài module truy cập public API của package theo quy tắc module; `opens` cho phép deep reflection đến các thành viên không public cho module được chỉ định. Framework có thể cần package `opens` phù hợp thay vì tăng quyền toàn ứng dụng.
- Với static method, `method.invoke(null, args...)` dùng receiver `null`; static field cũng dùng `field.get(null)`. Instance member đòi hỏi receiver đúng kiểu.
- Không nên dùng reflection để sửa các field `final` như một cơ chế cập nhật trạng thái: việc ghi có những hạn chế riêng, và không bảo đảm hành vi như setter thông thường.

Các lỗi cần nhận diện:

| Vấn đề | Exception / nguyên nhân |
| --- | --- |
| Sai tên class trong `Class.forName` | `ClassNotFoundException`; kiểm tra tên nhị phân và class loader |
| Sai tên/chữ ký method hoặc field | `NoSuchMethodException` / `NoSuchFieldException` |
| Caller không được phép sử dụng thành viên | `IllegalAccessException` |
| Yêu cầu deep reflection bị từ chối | `InaccessibleObjectException` (runtime) |
| Receiver, số lượng hoặc kiểu argument không hợp lệ | `IllegalArgumentException` |
| Constructor/method đích tự ném exception | `InvocationTargetException` bọc lỗi thật; xem `getCause()` |

`ReflectiveOperationException` là superclass chung cho nhiều lỗi checked ở reflection nhưng **không bao gồm mọi lỗi runtime** như `IllegalArgumentException` hoặc `InaccessibleObjectException`. Ở boundary reflection, log/chuyển tiếp lỗi gốc có ngữ cảnh; không được im lặng nuốt `InvocationTargetException`. `Class.newInstance()` đã deprecated: thay bằng `type.getDeclaredConstructor(...).newInstance(...)` để chọn constructor rõ ràng và xử lý lỗi tốt hơn.

## 6. Reflection, generic và annotation

**Type erasure** khiến thông tin tham số generic không tạo ra class runtime riêng cho mỗi kiểu tham số: chẳng hạn `ArrayList<String>` và `ArrayList<Integer>` có cùng runtime class `ArrayList`; `obj instanceof List<String>` không hợp lệ khi `obj` có kiểu tĩnh `Object`, vì cần chuyển đổi unchecked. Từ Java 16, phép kiểm tra với kiểu tham số hóa có thể hợp lệ nếu kiểu tĩnh của biểu thức đã đủ thông tin, chẳng hạn `List<String> values` được kiểm tra bằng `values instanceof ArrayList<String>`; điều này vẫn không kiểm tra kiểu từng phần tử tại runtime. Nhưng metadata **chữ ký khai báo** vẫn có thể truy xuất qua `Type`: `Field.getType()` thường trả kiểu thô `List.class`, còn `Field.getGenericType()` có thể trả `ParameterizedType` diễn tả `List<String>` nếu field được khai báo đúng như vậy. Điều đó không xác nhận từng phần tử runtime thực sự là `String`.

**Annotation** là một lý do reflection phổ biến trong framework. `getAnnotation(MyAnnotation.class)` và `isAnnotationPresent(MyAnnotation.class)` tra cứu metadata annotation khi annotation có `@Retention(RetentionPolicy.RUNTIME)`. Với retention `SOURCE` hoặc `CLASS`, không thể giả định reflection thấy annotation đó ở runtime. `@Inherited` chỉ ảnh hưởng cách kế thừa annotation trên lớp theo quy tắc riêng; không làm annotation trên method/field tự động kế thừa tương tự.

**Dynamic proxy:** `java.lang.reflect.Proxy` và `InvocationHandler` có thể tạo implementation cho một hoặc nhiều interface ở runtime, để chặn hoặc định tuyến lời gọi (ví dụ RPC, mock, interceptor). JDK dynamic proxy không phải cơ chế tự động subclass mọi concrete class.

## 7. Ứng dụng thực tế và lựa chọn thay thế

Reflection thường hiện diện trong:

- **Dependency injection:** đọc constructor, annotation, kiểu parameter để tạo và nối dependency.
- **ORM, serializer/deserializer:** ánh xạ field hoặc property dựa vào metadata, dưới những quyền truy cập cho phép.
- **Test framework:** phát hiện method có annotation runtime và gọi chúng theo quy ước.
- **Plugin, trình khám phá metadata và công cụ chẩn đoán:** nạp, kiểm tra hoặc tương tác với những kiểu chưa biết ở thời điểm biên dịch.

Cần đánh đổi: reflection làm yếu khả năng phát hiện lỗi lúc compile time, nhạy với rename/chữ ký và ranh giới module, có thêm exception runtime và có thể tốn chi phí tra cứu/gọi động. Không có một hệ số hiệu năng cố định cho mọi JVM; tránh tra cứu metadata lặp lại trên đường nóng, cache có kiểm soát và đo hiệu năng khi cần. Nếu mục tiêu chính là gọi động với hiệu năng hoặc kiểm soát access rõ hơn, nghiên cứu `MethodHandle` và `MethodHandles.Lookup` của gói **`java.lang.invoke`** (gói này khác `java.lang.reflect`).

**Quy tắc thực hành:** nếu biết kiểu và method từ compile time, ưu tiên lời gọi Java trực tiếp; nếu chỉ có metadata tại runtime, bắt đầu với `Class<?>`, tìm đúng thành viên phản chiếu, kiểm tra accessibility, gọi có chủ đích và xử lý nguyên nhân lỗi.

## 8. Câu hỏi tự kiểm tra

1. `Class` mô tả điều gì; tại sao nó không thuộc gói `java.lang.reflect`?
2. Vì sao `getDeclaredField("secret")` tìm được field private nhưng `Field.get(obj)` vẫn có thể thất bại?
3. `getMethod` và `getDeclaredMethod` khác nhau như thế nào khi method khai báo ở superclass?
4. Tra cứu `f(int)` với `getMethod` phải truyền `int.class` hay `Integer.class`?
5. Vì sao `exports` trong JPMS chưa đủ cho framework truy cập private field của một package?
6. `getGenericType()` có bảo đảm dữ liệu thực trong một `List<String>` đều là `String` không?

Nếu trả lời được, bạn đã nắm vai trò hai tầng: **`Class` định danh/khám phá kiểu; `java.lang.reflect` diễn tả và thao tác lên thành viên; JVM vẫn quản lý kiểu và quyền truy cập.**
