# Một ví dụ xuyên suốt: khám phá và sử dụng một kiểu chưa biết trước

Trong Java thông thường, ta viết `new HelloPlugin(...)` và gọi `plugin.greet(...)` khi mã nguồn đã biết lớp cùng phương thức. Reflection giải quyết tình huống khác: ứng dụng nhận **tên lớp dưới dạng dữ liệu lúc chạy**, rồi tìm hiểu kiểu đó, tạo đối tượng và gọi phương thức. Ví dụ xuyên suốt dưới đây đặt toàn bộ quá trình vào một chương trình chạy được.

## 1. Tình huống và luồng xử lý

Giả sử có một chương trình chủ (host) nhận tên một thành phần mở rộng (plugin) từ tham số dòng lệnh. Host chưa biết trước sẽ chọn `HelloPlugin` hay `LoudPlugin`; nó chỉ biết **quy ước**: lớp được chọn phải có constructor `public (String)` và phương thức `public String greet(String)`.

~~~text
Tên lớp nhận lúc chạy (String)
       │
       ▼
Class.forName(...)                 → Class<?>: mô tả kiểu
       │
       ├── getName(), getSuperclass(), getDeclaredFields()
       ├── getAnnotation(...)      → đọc metadata
       │
       ▼
getConstructor(String.class)       → Constructor<?>
       │
       ▼
newInstance("Xin chào")            → Object: đối tượng thật
       │
       ▼
getMethod("greet", String.class)   → Method
       │
       ▼
invoke(instance, "Lan")            → kết quả trả về
~~~

Reflection nằm trong các API `java.lang.Class` và `java.lang.reflect`. `Class<?>` là đối tượng mô tả **một kiểu**; còn `Object` nhận từ `newInstance` là **một instance của kiểu đó**. Hai khái niệm này khác nhau và đều cần trong ví dụ.

## 2. Chương trình Java 17+ hoàn chỉnh

Lưu tất cả nội dung sau vào **`ReflectionWalkthrough.java`**. Hai plugin được đặt trong cùng tệp dưới dạng lớp lồng tĩnh (`static nested class`) để chạy độc lập mà không cần thư viện hay JAR bên ngoài. Đây là môi trường mô phỏng plugin; trong ứng dụng thật, lớp được chọn có thể ở dependency riêng.

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Locale;

public class ReflectionWalkthrough {
    @Retention(RetentionPolicy.RUNTIME)
    public @interface ComponentInfo {
        String role();
    }

    @ComponentInfo(role = "greeting")
    public static class HelloPlugin {
        private final String prefix;

        public HelloPlugin(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return prefix + ", " + name + "!";
        }
    }

    @ComponentInfo(role = "loud")
    public static class LoudPlugin {
        private final String prefix;

        public LoudPlugin(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return (prefix + ", " + name + "!")
                    .toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        String className = args.length == 0
                ? "ReflectionWalkthrough$HelloPlugin"
                : args[0];

        Class<?> type = Class.forName(className);
        System.out.println("Tên lớp: " + type.getName());
        System.out.println("Lớp cha: " + type.getSuperclass().getName());
        System.out.println("Là interface: " + type.isInterface());

        for (Field field : type.getDeclaredFields()) {
            System.out.println("Field: " + Modifier.toString(field.getModifiers())
                    + " " + field.getType().getSimpleName() + " " + field.getName());
        }

        ComponentInfo info = type.getAnnotation(ComponentInfo.class);
        System.out.println("Vai trò: " + (info == null ? "(không có)" : info.role()));

        Constructor<?> constructor = type.getConstructor(String.class);
        Object instance = constructor.newInstance("Xin chào");

        Method method = type.getMethod("greet", String.class);
        System.out.println("Method: " + method.getReturnType().getSimpleName()
                + " " + method.getName() + "(String)");
        Object result = method.invoke(instance, "Lan");
        System.out.println("Kết quả: " + result);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ReflectionWalkthrough.java
java ReflectionWalkthrough
~~~

Đầu ra (stdout):

~~~text
Tên lớp: ReflectionWalkthrough$HelloPlugin
Lớp cha: java.lang.Object
Là interface: false
Field: private final String prefix
Vai trò: greeting
Method: String greet(String)
Kết quả: Xin chào, Lan!
~~~

Chạy với tên plugin còn lại:

~~~bash
java 'ReflectionWalkthrough$LoudPlugin'
~~~

Đầu ra:

~~~text
Tên lớp: ReflectionWalkthrough$LoudPlugin
Lớp cha: java.lang.Object
Là interface: false
Field: private final String prefix
Vai trò: loud
Method: String greet(String)
Kết quả: XIN CHÀO, LAN!
~~~

**Lưu ý về shell:** Dấu nháy đơn quanh tên có ký tự `$` dành cho Bash/Zsh và PowerShell, giúp chuyển nguyên tên lớp lồng vào Java (không để shell diễn giải `$LoudPlugin`). Trên Windows CMD có thể dùng `java "ReflectionWalkthrough$LoudPlugin"`. Nếu chỉ dùng lệnh `java ReflectionWalkthrough`, chương trình tự chọn plugin mặc định.

## 3. Khám phá kiểu từ tên nhận lúc chạy

~~~java
String className = args.length == 0
        ? "ReflectionWalkthrough$HelloPlugin"
        : args[0];
Class<?> type = Class.forName(className);
~~~

- `className` là **chuỗi** cấu hình/đầu vào; host không gọi `new HelloPlugin(...)` và không tham chiếu `HelloPlugin.class` để quyết định plugin.
- `Class.forName(String)` tìm lớp bằng tên nhị phân (*binary name*) qua cơ chế nạp lớp tương ứng và, nếu cần, khởi tạo lớp. Không tìm thấy sẽ ném `ClassNotFoundException`; lỗi khởi tạo tĩnh có thể là `ExceptionInInitializerError`.
- `Class<?>` nghĩa là “một đối tượng `Class` với kiểu tham số chưa biết”. Dấu `?` không biến nó thành một instance; nó biểu diễn thông tin kiểu tại runtime.
- Tên nhị phân của lớp lồng là `ReflectionWalkthrough$HelloPlugin`. Với lớp độc lập có package, chẳng hạn `com.example.plugins.HelloPlugin`, dùng tên đầy đủ theo package thay vì tên đơn giản.
- `getName()` cho tên nhị phân; `getSimpleName()` cho tên đơn giản; `getSuperclass()` cho lớp cha trực tiếp (có thể trả `null` với `Object`, interface hoặc một số trường hợp khác). `isInterface()` phân biệt interface và class.

Điểm cốt lõi: **biết tên để tải lớp không đồng nghĩa với biết API của lớp tại thời điểm biên dịch**. Ví dụ vẫn yêu cầu quy ước constructor/phương thức; Reflection không tự đoán ý nghĩa của mọi phương thức.

## 4. Đọc metadata trước khi sử dụng

Dòng lặp trong chương trình:

~~~java
for (Field field : type.getDeclaredFields()) {
    System.out.println("Field: " + Modifier.toString(field.getModifiers())
            + " " + field.getType().getSimpleName() + " " + field.getName());
}
~~~

`getDeclaredFields()` trả các field **khai báo trực tiếp** trên lớp, kể cả `private`; nó không có nghĩa host được phép truy cập giá trị các field đó. Mảng trả về không có thứ tự được bảo đảm, vì vậy nếu cần danh sách ổn định cho nhiều field, phải tự sắp xếp theo tên. Ví dụ này mỗi plugin chỉ có một field: `private final String prefix`.

Một số phép khám phá thường gặp:

| Nhu cầu | API | Điều cần nhớ |
|---|---|---|
| Kiểm tra tên/loại lớp | `getName()`, `getSimpleName()`, `isInterface()` | Metadata về kiểu |
| Xem lớp cha và interface | `getSuperclass()`, `getInterfaces()` | Quan hệ kế thừa/triển khai trực tiếp |
| Xem field khai báo trên lớp | `getDeclaredFields()` | Có cả field không public; không bao gồm field kế thừa |
| Xem method public gồm kế thừa | `getMethods()` | Chỉ các method public có thể nhìn thấy theo API này |
| Xem method khai báo trực tiếp | `getDeclaredMethods()` | Có thể gồm private; không bao gồm method kế thừa |
| Tìm method public theo chữ ký | `getMethod("greet", String.class)` | Tên + **kiểu tham số**, không tìm theo kiểu trả về |
| Tìm constructor public | `getConstructor(String.class)` | Chữ ký phải khớp chính xác |
| Đọc annotation runtime | `getAnnotation(ComponentInfo.class)` | Annotation phải tồn tại ở runtime |

Tương ứng, `getDeclaredMethod(...)` và `getDeclaredConstructor(...)` có thể tìm thành viên khai báo trực tiếp dù không public; **tìm được không đảm bảo được phép gọi**. Quyền truy cập vẫn do Java và hệ thống module kiểm soát.

Trong ví dụ, annotation `@ComponentInfo(role = "...")` được khai báo với `@Retention(RetentionPolicy.RUNTIME)` nên có thể đọc khi chạy:

~~~java
ComponentInfo info = type.getAnnotation(ComponentInfo.class);
String role = info == null ? "(không có)" : info.role();
~~~

Không có annotation thì `getAnnotation` trả `null`. Nếu retention chỉ là `SOURCE` hoặc `CLASS`, không thể mong đọc annotation đó bằng lời gọi Reflection trên. Annotation cung cấp metadata; bản thân nó không tự tạo hoặc kích hoạt plugin.

## 5. Tạo instance bằng constructor được tìm ở runtime

~~~java
Constructor<?> constructor = type.getConstructor(String.class);
Object instance = constructor.newInstance("Xin chào");
~~~

`getConstructor(String.class)` tìm constructor **public nhận đúng một `String`**. Không có constructor như vậy sẽ ném `NoSuchMethodException`. Nếu tìm constructor nhận `int` thì phải dùng `int.class` (không tự thay bằng `Integer.class` ở bước tra cứu chữ ký). `newInstance(...)` thật sự gọi constructor, có thể chạy logic và phát sinh lỗi.

Vì biến `type` là `Class<?>`, kết quả lưu trong `Object`. Java không thể bảo đảm tại compile time rằng đối tượng ấy có `greet(String)`. Chương trình phải kiểm tra và gọi phương thức tiếp bằng Reflection. Đừng dùng cách cũ `Class.newInstance()`: API này đã deprecated, yêu cầu constructor không đối số và có cách xử lý ngoại lệ kém rõ ràng; `getDeclaredConstructor().newInstance()` là lối thay thế phù hợp khi cần constructor không đối số.

## 6. Tìm và gọi phương thức trên instance

~~~java
Method method = type.getMethod("greet", String.class);
Object result = method.invoke(instance, "Lan");
~~~

Ở đây `getMethod` chọn method public tên `greet` có một tham số `String`. Kiểu trả về có thể đọc bằng `method.getReturnType()`. `invoke` cần **đối tượng đích** đối với phương thức instance; tham số tiếp theo là các đối số gửi tới phương thức được gọi. Giá trị trả về được đóng hộp nếu là primitive, hoặc là `null` khi phương thức trả `void`. Trong ví dụ, `result` thực chất là `String`; in bằng `println` không cần ép kiểu.

Với phương thức `static`, đối tượng đích truyền cho `invoke` có thể là `null`. Nếu đích sai kiểu, đối số không tương thích hoặc sai số lượng, có thể gặp `IllegalArgumentException`; nếu method tự ném ngoại lệ, `invoke` bọc nó trong `InvocationTargetException`. Để hiểu nguyên nhân nghiệp vụ, đọc `getCause()` của wrapper này.

**Ranh giới quan trọng:** `getDeclaredMethod` hoặc `getDeclaredField` có thể trả về thành viên private, nhưng việc gọi/đọc không mặc nhiên hợp lệ. Đừng thêm `setAccessible(true)` như một “bước bắt buộc” của Reflection: trong ứng dụng dùng Java Platform Module System (JPMS), việc mở quyền truy cập sâu còn phụ thuộc package có được `opens` cho module gọi hay không; ngay cả trên classpath cũng cần cân nhắc giới hạn đóng gói và quyền truy cập.

## 7. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `ClassNotFoundException` | Sai tên nhị phân, thiếu JAR/module, class loader không nhìn thấy lớp | Kiểm tra tên, classpath/module path và loader |
| `NoSuchMethodException` | Constructor/method không tồn tại với đúng tên, visibility hoặc danh sách kiểu tham số | Kiểm tra API thực tế và chữ ký |
| `InstantiationException` | Không thể tạo instance, ví dụ cố khởi tạo abstract class | Chọn lớp concrete có constructor phù hợp |
| `IllegalAccessException` | Thành viên không thể được truy cập từ nơi gọi | Thiết kế API public/module exports; tránh phá đóng gói |
| `InvocationTargetException` | Code bên trong constructor hoặc method đã ném lỗi | Xem `getCause()` và xử lý nguyên nhân thực |
| `IllegalArgumentException` | Truyền đích/đối số không tương thích lúc `invoke`/`newInstance` | So đúng số lượng và kiểu tham số |
| `ExceptionInInitializerError` | Khởi tạo tĩnh của lớp thất bại | Kiểm tra static initializer và nguyên nhân lỗi |

Chương trình demo khai báo `throws ReflectiveOperationException` để giữ luồng học tập rõ ràng; chương trình sản xuất cần bắt lỗi theo ngữ cảnh, báo plugin nào hỏng và lý do, đồng thời xử lý riêng lỗi runtime như `ExceptionInInitializerError` khi thích hợp. Không nên nuốt ngoại lệ rồi tiếp tục như thể plugin đã tải thành công.

## 8. Từ demo sang thiết kế thực tế

**Khi dùng Reflection?** Framework DI, serializer, công cụ kiểm thử, plugin loader và công cụ phân tích cấu trúc mã thường cần khám phá type/annotation/member lúc chạy. Nhưng Reflection đánh đổi một số lợi ích: mất kiểm tra kiểu tại compile time, dễ lỗi do chuỗi tên/chữ ký, chịu giới hạn truy cập module và có chi phí tra cứu/gọi động. Đừng chọn Reflection chỉ để gọi một lớp đã biết rõ trong source.

Nếu có thể định nghĩa hợp đồng Java chung, hướng ổn định hơn cho plugin là interface:

~~~java
public interface GreetingService {
    String greet(String name);
}
~~~

Đoạn trên là **mảnh thiết kế minh họa**, không phải chương trình chạy độc lập. Khi plugin triển khai `GreetingService`, host có thể dùng `GreetingService.class.isAssignableFrom(type)` để kiểm tra tương thích trước khi tạo instance, rồi ép kiểu bằng `GreetingService.class.cast(instance)` và gọi `service.greet("Lan")` như Java thông thường. Không nên ép kiểu trực tiếp từ đối tượng vừa nạp nếu chưa xác minh interface; tên method giống nhau không khiến lớp tự động triển khai interface. Khi cần khám phá provider theo hợp đồng trên classpath/module path, `ServiceLoader` thường phù hợp hơn cơ chế tự lưu tên class trong cấu hình.

**Giới hạn an toàn:** Chỉ tải plugin từ nguồn được tin cậy; `Class.forName` có thể kích hoạt khởi tạo lớp và `newInstance`/`invoke` thực thi mã thật, không phải thao tác chỉ đọc metadata. Không lấy tên class tùy ý từ người dùng bên ngoài để rồi tùy tiện khởi chạy. Khi kiểm tra hiệu năng, đo trước khi tối ưu; có thể cache `Class`, `Constructor` hoặc `Method` đã xác minh thay vì tra cứu lặp lại, nhưng cache phải tuân theo vòng đời của class loader.

## 9. Tự kiểm tra trên chính ví dụ

1. Đổi tham số dòng lệnh giữa `ReflectionWalkthrough$HelloPlugin` và `ReflectionWalkthrough$LoudPlugin`. Xác định phần nào của host giữ nguyên, phần nào thay đổi theo metadata và hành vi plugin.
2. Đổi `getConstructor(String.class)` thành `getConstructor()`. Vì sao hiện tại ném `NoSuchMethodException`? Hãy bổ sung constructor không đối số vào một plugin rồi thử lại.
3. Đổi `getDeclaredFields()` thành `getFields()`. Vì sao trường `prefix` biến mất khỏi kết quả? Hãy giải thích sự khác biệt giữa “được khai báo” và “public”.
4. Bỏ `@Retention(RetentionPolicy.RUNTIME)` khỏi `ComponentInfo` rồi quan sát `getAnnotation(...)`. Tìm hiểu retention mặc định và lý do host không đọc được role.
5. Viết thêm một plugin có cùng constructor/method public, chạy bằng tên nhị phân mới; sau đó cố tình đổi tên `greet` để xác nhận lỗi và cách chẩn đoán.

**Điểm cần nắm:** Tên lớp ở runtime → `Class<?>` để khám phá → xác minh chữ ký/metadata → `Constructor.newInstance` tạo đối tượng → `Method.invoke` gọi hành vi. Reflection đưa quyết định về kiểu sang runtime, nên trách nhiệm xác minh hợp đồng, xử lý lỗi và kiểm soát nguồn mã được tải cũng chuyển sang runtime.
