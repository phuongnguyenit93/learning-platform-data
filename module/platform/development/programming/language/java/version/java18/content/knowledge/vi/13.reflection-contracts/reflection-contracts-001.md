# Class, Method, Constructor và Field: metadata cần thiết cho lời gọi động

> **Bối cảnh học tập:** Bài thuộc chương **Hợp đồng reflection** của module `JAVA_VERSION_JAVA18`. Trong nhóm kiến thức Java 18 còn hữu ích trên JDK hiện đại, JEP 416 thay đổi cách JDK triển khai *core reflection* dựa trên method handles, nhưng hợp đồng công khai của `Class`, `Method`, `Constructor` và `Field` vẫn là nền tảng để kiểm tra kiểu, tìm thành viên và gọi mã được chọn lúc chạy. Bài này tập trung vào API được hỗ trợ chính thức, cách kiểm chứng metadata, các ngoại lệ và ranh giới truy cập; không dựa vào API nội bộ hay hành vi legacy.

## 1. Reflection cần những metadata nào?

Trong lời gọi thông thường, trình biên dịch thường biết lớp, constructor và phương thức:

~~~java
GreetingService service = new GreetingService("Xin chào");
String result = service.greet("Java");
~~~

Với **lời gọi động**, tên lớp hoặc tên phương thức có thể đến từ cấu hình, framework, cơ chế plugin hoặc hệ thống ánh xạ dữ liệu lúc chạy. Khi đó ứng dụng cần trả lời từng câu hỏi trước khi thực thi:

1. **Đây là kiểu nào?** — `Class<?>`.
2. **Tạo đối tượng bằng constructor nào?** — `Constructor<?>`.
3. **Gọi phương thức nào, với chữ ký tham số nào?** — `Method`.
4. **Đọc hoặc ghi trường dữ liệu nào, thuộc kiểu gì?** — `Field`.
5. **Thành viên có thể truy cập từ vị trí gọi hiện tại không?** — modifier, quy tắc truy cập Java và ranh giới module.

Bốn đối tượng trên đại diện cho metadata runtime; bản thân việc lấy `Method` hay `Field` **không thực thi** phương thức hoặc đọc giá trị trường. Hành vi bắt đầu khi gọi `newInstance`, `invoke`, `get` hoặc `set`.

| Thành phần | Metadata thường dùng | Hành động phản chiếu |
|---|---|---|
| `Class<?>` | Tên kiểu, kiểu cha, interface, modifier, phương thức/constructor/field | Tìm và kiểm chứng thành viên |
| `Constructor<?>` | Danh sách kiểu tham số, modifier, annotation, varargs | `newInstance(args...)` |
| `Method` | Tên, kiểu trả về, danh sách kiểu tham số, modifier, annotation | `invoke(target, args...)` |
| `Field` | Tên trường, kiểu trường, modifier, annotation | `get(target)`, `set(target, value)` |

**Giới hạn hợp đồng:** Reflection cho phép tìm và sử dụng các thành viên mà chương trình được quyền truy cập. Việc tìm thấy một thành viên trong metadata không tự động cấp quyền sử dụng nó.

## 2. `Class<?>`: điểm bắt đầu để chọn đúng kiểu runtime

Mỗi đối tượng Java có thể cung cấp `Class<?>` qua `getClass()`. Với kiểu đã biết lúc biên dịch, dùng `SomeType.class`. Nếu chỉ có tên kiểu ở thời điểm chạy, dùng `Class.forName(...)`.

~~~java
Class<String> known = String.class;
Class<?> actual = "hello".getClass();

// Trì hoãn khởi tạo lớp khi chỉ cần xem metadata:
Class<?> loaded = Class.forName(
        "java.util.ArrayList",
        false,
        ClassLoader.getSystemClassLoader()
);
~~~

Tham số `false` trong overload ba đối số yêu cầu không khởi tạo lớp do chính lời gọi `Class.forName` này. Nếu tiếp tục tạo instance, đọc/ghi static field hoặc gọi static method, quy tắc khởi tạo lớp của Java vẫn được áp dụng. Overload `Class.forName(String)` thông thường yêu cầu khởi tạo lớp.

Các nhóm metadata hữu ích:

| API | Mục đích | Lưu ý |
|---|---|---|
| `getName()` | Tên binary của lớp | Lớp lồng nhau thường có ký tự `$`, ví dụ `Outer$Inner` |
| `getSimpleName()` / `getPackageName()` | Tên đơn giản / package | Tên đơn giản có thể rỗng ở một số kiểu vô danh |
| `isInterface()`, `isEnum()`, `isRecord()` | Phân loại kiểu | `isRecord()` là API hiện đại, có thể dùng khi xử lý record |
| `getSuperclass()`, `getInterfaces()` | Quan hệ kiểu | Kết quả phụ thuộc loại `Class` đang xét |
| `isAssignableFrom(other)` | Kiểm tra có thể gán kiểu `other` vào kiểu nhận hay không | Hữu ích khi nạp plugin hoặc implementation |
| `getModifiers()` | Bit mask modifier của kiểu | Giải mã với `java.lang.reflect.Modifier` |

Ví dụ kiểm tra hợp đồng kiểu trước khi cho phép tạo một đối tượng:

~~~java
Class<?> candidate = Class.forName(className);
if (!TaskHandler.class.isAssignableFrom(candidate)) {
    throw new IllegalArgumentException(
            "Implementation must implement TaskHandler: " + className);
}
~~~

`TaskHandler` trong ví dụ trên là interface ứng dụng tự định nghĩa. Việc kiểm tra bằng `isAssignableFrom` giúp ngăn lỗi ép kiểu sau khi nạp, nhưng **không thay thế** chính sách tin cậy hoặc allowlist đối với class name đến từ nguồn không tin cậy.

### Kiểu `Class` và generic

`Class<?>` biểu thị một kiểu runtime, **không** mang thông tin của mọi type argument tại nơi sử dụng. Chẳng hạn, `List<String>` và `List<Integer>` cùng có runtime class của `ArrayList` khi đối tượng là `ArrayList`. Nếu cần xem khai báo generic, sử dụng các API trả về `Type` như `getGenericSuperclass()`, `Method.getGenericParameterTypes()`; không suy luận rằng có thể khôi phục type argument của mọi object.

`int.class`, `String[].class` và `void.class` cũng là các đối tượng `Class`, nhưng không phải tất cả đều biểu diễn kiểu có thể khởi tạo bằng constructor.

## 3. Tìm thành viên: phân biệt `get...` và `getDeclared...`

Chọn đúng hàm tìm kiếm là phần quan trọng của hợp đồng reflection.

| Thành viên | API tìm public, kể cả kế thừa khi phù hợp | API tìm khai báo trực tiếp trên lớp |
|---|---|---|
| Phương thức | `getMethod(name, parameterTypes...)`, `getMethods()` | `getDeclaredMethod(name, parameterTypes...)`, `getDeclaredMethods()` |
| Constructor | `getConstructor(parameterTypes...)`, `getConstructors()` | `getDeclaredConstructor(parameterTypes...)`, `getDeclaredConstructors()` |
| Field | `getField(name)`, `getFields()` | `getDeclaredField(name)`, `getDeclaredFields()` |

**Phân biệt quan trọng:**

- `getMethod` tìm phương thức `public` theo tên và **kiểu tham số**, có xét phương thức được kế thừa. `getDeclaredMethod` chỉ xét phương thức được khai báo bởi lớp đang kiểm tra, kể cả non-public; không tự tra lớp cha.
- Constructor không được kế thừa. Sự khác nhau giữa `getConstructor` và `getDeclaredConstructor` nằm ở phạm vi constructor public hoặc mọi mức truy cập được khai báo.
- `getField` có thể tìm public field được kế thừa; `getDeclaredField` tìm field được khai báo trực tiếp.
- `getDeclared...` trả về metadata kể cả thành viên private, **không có nghĩa** ứng dụng được phép gọi/đọc/ghi thành viên đó.
- Thứ tự phần tử do các phương thức dạng `getMethods()`, `getDeclaredFields()`... trả về không được bảo đảm theo thứ tự khai báo trong mã nguồn. Nếu cần thứ tự ổn định để sinh schema hoặc tài liệu, hãy tự sắp xếp theo khóa xác định.

Ví dụ tìm đúng overload:

~~~java
Method index1 = String.class.getMethod("indexOf", String.class);
Method index2 = String.class.getMethod("indexOf", String.class, int.class);

// Đây là hai Method khác nhau vì danh sách tham số khác nhau.
System.out.println(index1.getParameterCount()); // 1
System.out.println(index2.getParameterCount()); // 2
~~~

Không thể chọn một overload chỉ dựa vào tên phương thức. `getMethod("indexOf")` chỉ tìm phiên bản không tham số, và sẽ ném `NoSuchMethodException` nếu không tồn tại.

## 4. `Method`: từ metadata đến lời gọi động

`Method` mô tả một phương thức. Các phép kiểm tra đáng dùng trước `invoke` gồm:

| Metadata | API | Vì sao cần |
|---|---|---|
| Tên và lớp khai báo | `getName()`, `getDeclaringClass()` | Xác định chính xác thành viên |
| Kiểu tham số | `getParameterTypes()` | Chọn overload, kiểm tra cách truyền đối số |
| Kiểu trả về | `getReturnType()` | Diễn giải kết quả, tránh ép kiểu sai |
| Khai báo generic | `getGenericParameterTypes()`, `getGenericReturnType()` | Đọc thông tin kiểu tổng quát tại vị trí khai báo |
| Modifier | `getModifiers()` và `Modifier.isStatic(...)` | Biết có cần instance làm receiver hay không |
| Kiểu tham số biến đổi | `isVarArgs()` | Biết đối số cuối được khai báo là varargs |
| Phương thức do compiler sinh | `isBridge()`, `isSynthetic()` | Tránh nhầm phương thức hỗ trợ compiler với API nghiệp vụ |
| Annotation | `getAnnotations()`, `getDeclaredAnnotations()` | Đọc cấu hình giữ lại ở runtime |

Để gọi một phương thức public trên instance:

~~~java
Method method = target.getClass().getMethod("greet", String.class);
Object returned = method.invoke(target, "Java");
~~~

Đối với **static method**, truyền `null` ở vị trí receiver:

~~~java
Method parse = Integer.class.getMethod("parseInt", String.class);
Object number = parse.invoke(null, "42"); // Integer chứa giá trị 42
~~~

`Method.invoke` trả về `Object`: giá trị primitive được boxing; phương thức trả `void` cho kết quả `null`. Một phép ép kiểu tùy tiện sau khi gọi vẫn có thể ném `ClassCastException`. Với instance method, receiver phải có kiểu phù hợp; truyền `null` làm receiver sẽ thất bại.

### Hợp đồng ngoại lệ khi gọi phương thức

Mã bên trong phương thức được gọi có thể ném exception. `Method.invoke` bọc exception từ lời gọi đích trong `InvocationTargetException`:

~~~java
try {
    Object result = method.invoke(target, "Java");
    System.out.println(result);
} catch (InvocationTargetException e) {
    Throwable rootCause = e.getCause();
    throw new IllegalStateException("Business method failed", rootCause);
}
~~~

Đoạn minh họa giả định `method` và `target` đã được khai báo, và vị trí gọi xử lý hoặc khai báo các checked exceptions khác của reflection. Đừng coi `InvocationTargetException` là lỗi tìm metadata; hãy kiểm tra `getCause()` để thấy nguyên nhân thực sự từ phương thức đích.

Các ngoại lệ khác gồm `IllegalAccessException` khi không có quyền gọi và `IllegalArgumentException` khi receiver/đối số không phù hợp.

### Generic, varargs và tên tham số

- `getParameterTypes()` phản ánh kiểu tham số sau khi **type erasure**. Ví dụ, phương thức `List.add(E)` được tìm bằng `List.class.getMethod("add", Object.class)`, không phải `String.class`.
- `getGenericParameterTypes()` trả về `Type[]`, có thể biểu diễn `TypeVariable` hoặc `ParameterizedType` từ **khai báo**; không phải lúc nào cũng cho biết type argument của một đối tượng cụ thể.
- `isVarArgs()` cho biết cách phương thức được khai báo. Khi dùng reflection, phải truyền đúng kiểu mảng cho tham số varargs cuối; không giả định `Method.invoke` tự đóng gói đối số như cú pháp gọi Java thông thường. Ví dụ nếu tham số phương thức đích là `String...`, có thể truyền đối số cuối dưới dạng `(Object) new String[] {"a", "b"}` để tránh nhập nhằng với chính varargs của `invoke`.
- `getParameters()` cung cấp metadata `Parameter`. Tên nguồn như `name` chỉ đáng tin khi bytecode chứa thông tin tên tham số (ví dụ biên dịch với `javac -parameters`); luôn kiểm tra `Parameter.isNamePresent()` nếu framework phụ thuộc vào tên đó.

## 5. `Constructor<?>`: tạo đối tượng đúng chữ ký

Một lớp có thể có nhiều constructor; `getConstructor(String.class)` tìm **đúng** constructor public nhận một `String`, và sẽ ném `NoSuchMethodException` nếu không có.

~~~java
Constructor<StringBuilder> constructor =
        StringBuilder.class.getConstructor(int.class);

StringBuilder builder = constructor.newInstance(64);
System.out.println(builder.capacity()); // 64
~~~

Trước khi gọi, có thể kiểm tra `constructor.getParameterTypes()`, `getParameterCount()`, `isVarArgs()` và `getModifiers()`. `Constructor.newInstance` trả về instance của lớp khai báo constructor; nếu code khởi tạo ném exception, nó cũng có thể được bọc trong `InvocationTargetException`.

Cần phân biệt:

- **Không có constructor không tham số:** gọi `getConstructor()` thất bại; reflection không tự tạo constructor bị thiếu.
- **Constructor tồn tại nhưng không có quyền gọi:** metadata có thể tìm thấy bằng `getDeclaredConstructor`, nhưng khi sử dụng vẫn phải tuân thủ quyền truy cập Java/module.
- **Constructor abstract/interface:** không thể tạo instance trực tiếp của abstract class/interface chỉ bằng reflection; phải chọn implementation cụ thể.
- **Kiểu tham số:** khi khai báo `int`, hãy tìm bằng `int.class`, không dùng `Integer.class`. Tra cứu thành viên yêu cầu chữ ký chính xác dù khi thực thi có một số chuyển đổi boxing/unboxing/widening được hỗ trợ.

## 6. `Field`: đọc metadata, đọc giá trị, ghi giá trị

`Field` là metadata về một trường, không phải giá trị của trường. Hai phép lấy thông tin cơ bản là `getType()` và `getModifiers()`; có thể dùng thêm `getGenericType()`, `getAnnotations()` và `isSynthetic()`.

~~~java
Field field = SomePublicType.class.getField("description");
Class<?> fieldType = field.getType();

Object current = field.get(instance);
field.set(instance, "Mô tả mới");
~~~

Ví dụ minh họa trên giả định `SomePublicType` khai báo hoặc kế thừa một public, non-final field tên `description` có kiểu tương thích và `instance` là đối tượng phù hợp. Với **static field**, receiver truyền cho `Field.get`/`Field.set` có thể là `null`.

Nên kiểm tra các giới hạn:

- `Field.get`/`set` có thể thất bại vì không có quyền truy cập, receiver không phù hợp hoặc giá trị ghi không tương thích.
- `final` biểu diễn ràng buộc về khả năng thay đổi trường. Không xây framework dựa vào việc ép ghi các final field; nhiều loại final field có giới hạn đặc biệt, và thay đổi cưỡng ép có thể phá vỡ bất biến của đối tượng.
- Reflection không gọi setter, không tự chạy validation trong setter và không tự bảo vệ invariant của domain object. Với logic nghiệp vụ, thường nên gọi public method/setter thay vì ghi field trực tiếp.
- Trường có thể bị **ẩn** trong lớp con; `Field.getDeclaringClass()` cho biết field thực sự thuộc lớp nào. Trường không có dispatch đa hình như instance method.

## 7. Ví dụ hoàn chỉnh: nạp lớp, kiểm tra kiểu, tạo instance, đọc field và gọi method

Tạo một file `ReflectionContractsDemo.java` với nội dung:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionContractsDemo {

    public static class GreetingService {
        public String prefix;

        public GreetingService(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return prefix + ", " + name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        // Binary name của nested class có dấu '$'.
        String implementationName = args.length == 0
                ? "ReflectionContractsDemo$GreetingService"
                : args[0];

        // Xem metadata trước khi khởi tạo lớp.
        Class<?> implementation = Class.forName(
                implementationName,
                false,
                ReflectionContractsDemo.class.getClassLoader()
        );

        if (!GreetingService.class.isAssignableFrom(implementation)) {
            throw new IllegalArgumentException(
                    "Unsupported implementation: " + implementationName);
        }

        // Constructor public có đúng một tham số String.
        Constructor<?> constructor =
                implementation.getConstructor(String.class);
        Object service = constructor.newInstance("Xin chào");

        // Field public, không phải final.
        Field prefix = implementation.getField("prefix");
        System.out.println("Prefix before: " + prefix.get(service));
        prefix.set(service, "Chào");

        // Method public: tên + danh sách kiểu tham số chính xác.
        Method greet = implementation.getMethod("greet", String.class);
        System.out.println("Return type: "
                + greet.getReturnType().getTypeName());

        try {
            Object result = greet.invoke(service, "Java");
            System.out.println("Result: " + result);
        } catch (InvocationTargetException e) {
            throw new IllegalStateException(
                    "GreetingService.greet failed", e.getCause());
        }
    }
}
~~~

Biên dịch và chạy với một JDK hiện đại (từ Java 18 trở lên):

~~~shell
javac -encoding UTF-8 ReflectionContractsDemo.java
java ReflectionContractsDemo
~~~

Kết quả mong đợi:

~~~text
Prefix before: Xin chào
Return type: java.lang.String
Result: Chào, Java
~~~

**Vì sao ví dụ hoạt động:**

1. `Class.forName(..., false, loader)` tìm kiểu qua binary name, chưa yêu cầu khởi tạo lớp tại bước xem metadata.
2. `isAssignableFrom` kiểm tra kiểu được nạp tương thích với giao diện thực tế mà ví dụ mong đợi.
3. `getConstructor(String.class)` trả metadata constructor public phù hợp; `newInstance("Xin chào")` tạo đối tượng.
4. `getField("prefix")` tìm field public; `get` đọc, `set` cập nhật giá trị trên instance.
5. `getMethod("greet", String.class)` xác định overload; `invoke` thực thi instance method với receiver `service`.
6. Khi mã đích ném exception, `InvocationTargetException.getCause()` cho biết nguyên nhân cần chẩn đoán.

**Lưu ý khi tùy biến:** Thay tên lớp trong đối số CLI chỉ có ý nghĩa nếu lớp mới có thể nạp bởi class loader được truyền vào, thỏa `isAssignableFrom` và công khai constructor, field, method đúng hợp đồng ví dụ. Ứng dụng thực tế nên dùng interface/annotation hoặc factory để định nghĩa hợp đồng cấu hình rõ ràng, đồng thời kiểm soát danh sách implementation được phép nạp.

## 8. Truy cập reflection trên classpath và module path

Khi chương trình chạy trên classpath thông thường, các quy tắc Java access control vẫn chi phối thành viên public/protected/package-private/private. Khi chạy trong **named modules**, ranh giới module bổ sung điều kiện quan trọng.

| Tình huống | Ý nghĩa |
|---|---|
| Public type và public member trong package được `exports` phù hợp | Thường có thể gọi bằng reflection theo quy tắc truy cập thông thường |
| Lấy được `getDeclaredMethod` cho private method | Có metadata nhưng chưa chắc được phép gọi |
| Muốn deep reflection trên package của named module | Module sở hữu cần `opens` package đến module gọi, hoặc cơ chế mở tương đương được cấu hình rõ ràng |
| Package không được mở cho caller | `trySetAccessible()` có thể trả `false`; cưỡng ép `setAccessible(true)` có thể ném `InaccessibleObjectException` |

Ví dụ một **module cung cấp API** có thể xuất package API và mở riêng package model cho framework:

~~~java
module demo.domain {
    exports example.api;
    opens example.model to demo.framework;
}
~~~

`opens ... to ...` chỉ áp dụng cho module đích được chỉ định, giúp giới hạn deep reflection. Đó là khai báo minh họa trong `module-info.java`, không phải nội dung cần thêm vào ví dụ classpath ở phần 7.

Nếu thực sự cần gọi thành viên không public trong phạm vi được phép, dùng API hiện đại:

~~~java
Method selected = type.getDeclaredMethod("internalOperation");
if (!selected.canAccess(receiver) && !selected.trySetAccessible()) {
    throw new IllegalStateException("Module does not permit access");
}
Object value = selected.invoke(receiver);
~~~

Đoạn minh họa giả định `type`, `receiver` và phương thức không tham số đã tồn tại, receiver phù hợp; cần xử lý checked exceptions của reflection. `canAccess(receiver)` đánh giá khả năng truy cập tại vị trí gọi; nếu là static method, truyền `null`. `trySetAccessible()` không vượt qua mọi ranh giới module. Với API public đã được export, ưu tiên gọi bình thường, không cần bỏ kiểm tra quyền truy cập.

Việc JDK triển khai core reflection bằng method handles từ Java 18 **không** khiến module encapsulation trở nên tùy chọn. Không dùng lớp nội bộ `jdk.internal.*` hoặc các kỹ thuật phụ thuộc vào cấu trúc triển khai để né quyền truy cập.

## 9. Phân loại lỗi theo từng giai đoạn

Khi viết framework sử dụng reflection, hãy ghi rõ thao tác nào thất bại thay vì gộp mọi tình huống thành một thông báo "reflection failed".

| Giai đoạn | Lỗi thường gặp | Cách hiểu và xử lý |
|---|---|---|
| Nạp kiểu bằng tên | `ClassNotFoundException` | Tên binary sai, thiếu JAR/module hoặc class loader không nhìn thấy kiểu |
| Tìm constructor/method | `NoSuchMethodException` | Sai tên, sai loại public/declared hoặc chữ ký tham số không khớp |
| Tìm field | `NoSuchFieldException` | Field không tồn tại trong phạm vi tìm kiếm đã chọn |
| Gọi hoặc đọc/ghi | `IllegalAccessException` | Quy tắc truy cập không cho phép thao tác |
| Chuyển đối số/receiver | `IllegalArgumentException` | Đối số sai số lượng/kiểu, receiver không phù hợp |
| Constructor hoặc method đích ném lỗi | `InvocationTargetException` | Kiểm tra `getCause()`; lỗi có nguồn gốc từ code được gọi |
| Khởi tạo lớp | `ExceptionInInitializerError` | Lỗi trong quá trình khởi tạo static; có thể xảy ra khi bắt đầu sử dụng lớp |
| Cố nới quyền truy cập | `InaccessibleObjectException` | Thường liên quan module encapsulation và deep reflection bị cấm |

`ReflectiveOperationException` là superclass checked exception cho nhiều lỗi reflection, thuận tiện ở ví dụ ngắn. Với dịch vụ thật, nên xử lý riêng các trường hợp cần phản hồi khác nhau: cấu hình sai, quyền truy cập thiếu, hay code nghiệp vụ thất bại.

**Chú ý:** `Class.forName`, `Constructor.newInstance`, `Method.invoke` và `Field.get/set` không có chung một bộ ngoại lệ. Đọc hợp đồng của từng API và giữ nguyên cause khi wrap exception để không mất thông tin chẩn đoán.

## 10. Bẫy metadata trong hệ thống động

### 10.1. Chữ ký thực sự là danh sách kiểu tham số

~~~java
// Hợp lệ: List.add(E) được xóa kiểu thành add(Object).
Method add = java.util.List.class.getMethod("add", Object.class);
System.out.println(add.getParameterTypes()[0]); // class java.lang.Object
~~~

Trong reflection, một overload `work(int)` khác `work(Integer)`. Nếu ứng dụng có dispatcher nhận đối số từ JSON hoặc CLI, cần chọn method sau khi kiểm tra chuyển đổi kiểu có chủ đích; reflection không tự giải quyết overload dựa trên giá trị như compiler Java.

### 10.2. Không dựa vào thứ tự hoặc tên tham số không được lưu

`getDeclaredMethods()` không cam kết trả theo thứ tự trong source. Metadata tên tham số cũng phụ thuộc cách biên dịch. Framework dùng annotation, parameter type hoặc metadata được khai báo rõ ràng thường ổn định hơn giả định rằng phần tử thứ nhất là hành động chính và tên tham số luôn được lưu.

### 10.3. Bridge/synthetic method có thể xuất hiện

Compiler đôi khi sinh bridge method để giữ hành vi đa hình khi dùng generics. Công cụ quét method cần cân nhắc `isBridge()` và `isSynthetic()` trước khi xem mọi `Method` là một endpoint do developer trực tiếp khai báo. Không xóa bừa những method này nếu mục tiêu là phân tích đầy đủ bytecode hoặc hành vi Java.

### 10.4. Có metadata không đồng nghĩa là được gọi

Một public method của một lớp có thể không được truy cập từ module hiện tại nếu package không được export đúng cách. `getDeclaredMethod` cũng không bỏ qua privacy. Hãy phân biệt **tìm thành viên**, **kiểm tra quyền truy cập** và **thực thi** khi thiết kế lỗi hoặc log.

### 10.5. Reflection có chi phí nhưng không có tỉ lệ chậm cố định

JEP 416 tái triển khai core reflection bằng method handles trong JDK, giúp thống nhất một phần cơ sở triển khai. Chi phí thực tế của `Method.invoke` phụ thuộc kiểu member, khả năng tối ưu hóa JIT, cách giữ metadata và tải ứng dụng. Đừng khẳng định reflection luôn chậm hơn theo một hệ số cố định. Với đường gọi nóng và hợp đồng phương thức đã biết, có thể đo đạc rồi cân nhắc lời gọi trực tiếp hoặc `java.lang.invoke.MethodHandle`; hai cơ chế có quy tắc gọi và kiểm tra kiểu khác nhau.

## 11. Checklist trước khi đưa reflection vào ứng dụng

| Câu hỏi kiểm chứng | Kết quả mong muốn |
|---|---|
| Tên kiểu có đúng **binary name** và class loader có thấy lớp không? | `Class.forName` thành công |
| Implementation có tuân thủ interface/base class đã yêu cầu? | `isAssignableFrom` trả `true` |
| Member có đúng tên và danh sách kiểu tham số? | Tra cứu thành công đúng overload |
| Có cần public/inherited member hay declared member? | Dùng đúng cặp `get...` / `getDeclared...` |
| Có kiểm tra static/instance trước khi chọn receiver? | Receiver phù hợp hoặc `null` cho static member |
| Code có chú ý return type, boxing, varargs, generic erasure? | Không ép kiểu hoặc truyền tham số sai |
| Caller có quyền truy cập thành viên trong named module không? | Không phụ thuộc deep reflection bị cấm |
| Có tách lỗi tra cứu với exception từ code đích? | Log được giai đoạn và giữ nguyên `cause` |
| Field cần ghi có thể sửa hợp lệ và không phá bất biến? | Ưu tiên public API và validation của domain |
| Có cần sắp xếp kết quả metadata để ổn định? | Sắp xếp bằng khóa thay vì dựa vào thứ tự reflection |

## 12. Bài tập tự kiểm tra

1. Một lớp có `process(String)` và `process(Object)`. Hãy viết hai lời gọi `getMethod` để tìm đúng từng overload. Vì sao chỉ cung cấp tên `"process"` là không đủ?
2. Lớp con kế thừa public `execute()` nhưng không khai báo lại. `getMethod("execute")` và `getDeclaredMethod("execute")` trên lớp con khác nhau như thế nào?
3. Điều gì khác nhau giữa tìm thấy một private method bằng `getDeclaredMethod` và gọi thành công phương thức ấy trong một named module?
4. Tại sao ứng dụng không thể dùng `Integer.class` để tìm constructor nhận tham số `int`?
5. Nếu `Method.invoke` báo `InvocationTargetException`, cách xác định lỗi thực sự do code đích ném là gì?
6. Khi `getDeclaredMethods()` trả các method có `isBridge() == true`, trình quét endpoint nên xem xét điều gì?
7. `Class.forName(name, false, loader)` có bảo đảm lớp không bao giờ được khởi tạo trong phần còn lại của chương trình không? Giải thích.
8. Nếu muốn truy cập public API ở package được export từ named module, có cần gọi `trySetAccessible()` trước hay không?
9. Tại sao xử lý `Field.set` trên private/final fields không phải phương án thay thế tốt cho validation trong public setter?
10. Một framework dựa vào tên tham số từ `getParameters()` nên kiểm tra metadata và tùy chọn biên dịch nào?

**Ghi nhớ:** `Class` xác định kiểu runtime; `Constructor` tạo instance; `Method` mô tả và gọi phương thức theo chữ ký; `Field` mô tả và truy cập trường. Luôn kiểm tra kiểu, chữ ký, modifier, receiver, ranh giới module và nguyên nhân ngoại lệ trước khi coi một thao tác reflection là hợp lệ. Những hợp đồng công khai này vẫn cần thiết trên JDK hiện đại dù phần triển khai core reflection đã thay đổi từ Java 18.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
- [Java SE 25: `Class` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html).
- [Java SE 25: `Method` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html).
- [Java SE 25: `Constructor` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Constructor.html).
- [Java SE 25: `Field` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html).
- [Java SE 25: `AccessibleObject` API và ranh giới truy cập](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html).

