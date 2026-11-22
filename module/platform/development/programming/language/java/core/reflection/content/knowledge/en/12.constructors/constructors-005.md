# Constructor private và điều kiện truy cập trong Java Reflection

## 1. Private constructor giải quyết vấn đề gì?

Constructor là thành viên đặc biệt dùng để khởi tạo một instance. Khai báo một constructor `private` giúp **hạn chế nơi có thể gọi constructor theo ngôn ngữ Java**, thường được dùng để kiểm soát quá trình tạo đối tượng, buộc đi qua factory method hoặc ngăn tạo đối tượng của lớp tiện ích.

~~~java
final class SecretBox {
    private final String value;

    private SecretBox(String value) {
        this.value = value;
    }

    public static SecretBox of(String value) {
        return new SecretBox(value);
    }
}
~~~

Đây là đoạn minh họa ngắn: code thông thường ở ngoài phạm vi được phép không thể viết `new SecretBox("abc")` vì constructor là private; thay vào đó gọi `SecretBox.of("abc")`. Tuy nhiên Java Reflection **có thể tra cứu metadata của private constructor**, và trong một số điều kiện có thể yêu cầu bỏ qua kiểm tra truy cập khi gọi. Khả năng đó phụ thuộc caller, phạm vi package/module và quyền deep reflection.

Vì vậy cần phân biệt rõ ba câu hỏi:

1. **Constructor có được khai báo trong lớp không?** Kiểm tra bằng `getDeclaredConstructor(...)` hoặc `getDeclaredConstructors()`.
2. **Caller có quyền gọi constructor đang tìm được không?** Kiểm tra quyền khi dùng `Constructor.newInstance(...)`; `Constructor.canAccess(null)` giúp thăm dò quyền hiện tại.
3. **Có được phép bật access-check override không?** `trySetAccessible()` hoặc `setAccessible(true)` chỉ hoạt động khi những ranh giới truy cập cho phép.

**Tìm thấy constructor không đồng nghĩa gọi được constructor.** Đây là trọng tâm khi làm việc với private constructor bằng Reflection.

## 2. `getConstructor` khác `getDeclaredConstructor`

| API của `Class<T>` | Phạm vi tra cứu | Có lấy private constructor không? |
| --- | --- | --- |
| `getConstructor(Class<?>... parameterTypes)` | Chỉ public constructor được khai báo trên chính lớp | Không |
| `getConstructors()` | Mảng các public constructor của chính lớp | Không |
| `getDeclaredConstructor(Class<?>... parameterTypes)` | Constructor được khai báo trên chính lớp, bất kể modifier | Có |
| `getDeclaredConstructors()` | Mọi constructor khai báo trên chính lớp: public, protected, package-private và private | Có |

Khác với nhiều public method/field, **constructor không được kế thừa**. Ví dụ `Child extends Parent` không làm constructor `Parent(int)` trở thành constructor `Child(int)`. Cả hai nhóm API trên đều tra cứu constructor của **lớp đang xét**, không tìm constructor kế thừa.

Hai API tra cứu một constructor yêu cầu **danh sách kiểu tham số chính xác**, theo đúng thứ tự, bằng đối tượng `Class`:

~~~java
Constructor<SecretBox> ctor =
        SecretBox.class.getDeclaredConstructor(String.class);
~~~

Nếu constructor thực tế nhận `String` thì truyền `String.class`; nếu nhận primitive `int` thì truyền `int.class`, không thay bằng `Integer.class`. Tra cứu không thực hiện overload resolution giống cú pháp `new` và không tự chuyển đổi kiểu cho bạn. Sai chữ ký sẽ ném `NoSuchMethodException`, còn `getDeclaredConstructor` không cần constructor phải public.

**Modifier và vị trí khai báo:** Có thể kiểm tra `Modifier.isPrivate(ctor.getModifiers())`, `ctor.getDeclaringClass()`, `ctor.getParameterTypes()` và `ctor.isVarArgs()` để biết metadata. Những phép đọc metadata này tự thân không cấp quyền chạy constructor.

## 3. Ví dụ Java 17+: tra cứu, bị chặn, mở quyền, khởi tạo

Tạo tệp **`PrivateCtorDemo.java`**, trong đó có **hai top-level class tách biệt**. Đặt `PrivateCtorDemo` và `SecretBox` trong cùng tệp/package giúp ví dụ đơn giản, nhưng chúng **không phải nested class/nestmate** nên private constructor của `SecretBox` không tự nhiên truy cập được từ `PrivateCtorDemo`.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Modifier;

public class PrivateCtorDemo {
    public static void main(String[] args) throws Exception {
        Class<SecretBox> type = SecretBox.class;

        try {
            type.getConstructor(String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("public lookup: " + e.getClass().getSimpleName());
        }

        Constructor<SecretBox> ctor =
                type.getDeclaredConstructor(String.class);

        System.out.println("private: "
                + Modifier.isPrivate(ctor.getModifiers()));
        System.out.println("canAccess before: " + ctor.canAccess(null));

        try {
            ctor.newInstance("alpha");
        } catch (IllegalAccessException e) {
            System.out.println("invoke before: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("opened: " + ctor.trySetAccessible());
        System.out.println("canAccess after: " + ctor.canAccess(null));
        System.out.println("created: " + ctor.newInstance("alpha").code());

        try {
            ctor.newInstance("");
        } catch (InvocationTargetException e) {
            System.out.println("target error: "
                    + e.getCause().getClass().getSimpleName());
        }

        ctor.setAccessible(false);
        System.out.println("canAccess reset: " + ctor.canAccess(null));
    }
}

class SecretBox {
    private final String code;

    private SecretBox(String code) {
        if (code.isBlank()) {
            throw new IllegalArgumentException("empty code");
        }
        this.code = code;
    }

    public String code() {
        return code;
    }
}
~~~

Biên dịch bằng trình biên dịch tương thích Java 17, rồi chạy trên classpath:

~~~bash
javac --release 17 PrivateCtorDemo.java
java PrivateCtorDemo
~~~

Output dự kiến của ví dụ khi chạy trong unnamed module/classpath thông thường:

~~~text
public lookup: NoSuchMethodException
private: true
canAccess before: false
invoke before: IllegalAccessException
opened: true
canAccess after: true
created: alpha
target error: IllegalArgumentException
canAccess reset: false
~~~

### Giải thích từng giai đoạn

**Giai đoạn 1 — Chỉ tìm constructor công khai.** `type.getConstructor(String.class)` ném `NoSuchMethodException` vì constructor `SecretBox(String)` là private. Điều này **không nói** constructor không tồn tại, mà nói nó không nằm trong tập public constructor theo cách tra cứu đó.

**Giai đoạn 2 — Tìm đúng khai báo.** `type.getDeclaredConstructor(String.class)` trả về `Constructor<SecretBox>`. `Modifier.isPrivate(...)` là `true`. `canAccess(null)` lúc này là `false` do caller ở một top-level class khác và constructor private chưa được mở quyền.

**Giai đoạn 3 — Gọi khi chưa có quyền.** `ctor.newInstance("alpha")` thực hiện access check và ném `IllegalAccessException`. Constructor body chưa chạy, nên không có object nào được tạo từ lời gọi bị chặn này.

**Giai đoạn 4 — Bật override hợp lệ.** `ctor.trySetAccessible()` trả `true` trong môi trường classpath của ví dụ. Khi đó access check ngôn ngữ Java được bỏ qua **cho reflection object `ctor`**, `canAccess(null)` trở thành `true` và `ctor.newInstance("alpha")` tạo đối tượng, truy cập `code()` nhận `alpha`.

**Giai đoạn 5 — Lỗi từ logic constructor.** `ctor.newInstance("")` đã qua bước kiểm tra quyền, nhưng constructor body tự ném `IllegalArgumentException` khi chuỗi trống. Reflection bọc lỗi của target trong `InvocationTargetException`; `getCause()` cho thấy nguyên nhân gốc là `IllegalArgumentException`. Trường hợp này **khác** lỗi `IllegalAccessException` ở giai đoạn 3.

**Giai đoạn 6 — Trả về kiểm tra truy cập bình thường.** `ctor.setAccessible(false)` tắt override trên object `Constructor`; `canAccess(null)` trở lại `false` với caller này.

Đây là bài tập phân tích hành vi, **không phải lời khuyên luôn bật private access trong mã sản xuất**. Kết quả `opened: true` chỉ là kết quả trong điều kiện chạy của ví dụ, không phải bảo đảm cho tất cả named module hoặc thư viện.

## 4. Khi nào `Constructor.newInstance` được gọi mà không cần override?

Điều kiện của `Constructor.newInstance` tùy **ngữ cảnh caller thực sự**, không chỉ tùy modifier:

- `public` constructor của kiểu truy cập được từ caller có thể được gọi trực tiếp hoặc qua Reflection mà không mở override.
- Constructor `private` thường chỉ truy cập được từ code bên trong chính lớp khai báo hoặc những **nestmates** được ngôn ngữ Java cho phép; caller bên ngoài như `PrivateCtorDemo` trong ví dụ trên bị chặn.
- Constructor package-private có thể được code cùng package gọi khi các điều kiện khác thỏa; `protected` có quy tắc về package/subclass và ngữ cảnh truy cập.
- Class bản thân không truy cập được (ví dụ top-level class package-private thuộc package khác, hoặc public class ở package không được export cho named module gọi) có thể ngăn truy cập dù constructor có modifier public.

Vì thế, `getDeclaredConstructor` chỉ chứng minh tìm được metadata. **Không suy từ `getModifiers()` rằng việc gọi luôn thành công.** Access check còn xét lớp khai báo, quan hệ caller, module và trạng thái override.

Một chi tiết dễ gây nhầm trong bài thực hành: nếu đặt private constructor trong **nested class** và gọi Reflection từ outer class cùng nest, Java có thể coi các lớp đó là **nestmates** với quyền truy cập private theo ngôn ngữ. Khi đó `canAccess(null)` có thể đã `true`, và lời gọi không bị `IllegalAccessException`. Muốn minh họa lời gọi bị chặn rõ ràng, dùng caller ở một **top-level class tách biệt** như chương trình trên.

## 5. `canAccess(null)`, `trySetAccessible` và `setAccessible`

`Constructor<T>` kế thừa `AccessibleObject` nên cung cấp các API:

| API | Ý nghĩa | Hành vi chính |
| --- | --- | --- |
| `ctor.canAccess(null)` | Kiểm tra quyền dùng constructor từ caller hiện tại | Trả `boolean`, không tự bật quyền |
| `ctor.trySetAccessible()` | Thử bật override access check ngôn ngữ | Trả `true` nếu bật được, `false` nếu ranh giới truy cập không cho phép |
| `ctor.setAccessible(true)` | Yêu cầu bật override | Có thể ném `InaccessibleObjectException` khi không mở được |
| `ctor.setAccessible(false)` | Tắt override | Lần gọi tiếp theo phải tuân thủ kiểm tra quyền thông thường |

Constructor **không có receiver đã tồn tại**; vì vậy với `canAccess` dùng đúng `null`. Không nhầm với `Method.canAccess(receiver)` hoặc `Field.canAccess(receiver)` của instance member. `Constructor.newInstance(...)` nhận **đối số truyền vào constructor**, không nhận receiver; số lượng/kiểu đối số phải tương thích với signature.

Quy tắc kiểm tra trước khi gọi:

~~~java
Constructor<SecretBox> constructor =
        SecretBox.class.getDeclaredConstructor(String.class);
if (!constructor.canAccess(null) && !constructor.trySetAccessible()) {
    throw new IllegalStateException(
            "Không được phép gọi constructor của SecretBox");
}
SecretBox instance = constructor.newInstance("alpha");
~~~

Đây là **mảnh code minh họa** dùng lại định nghĩa `SecretBox` ở ví dụ; không phải một file độc lập. Nó thể hiện thao tác kiểm tra và xử lý nhánh mở quyền bị từ chối. Đoạn code không giải quyết mọi lỗi: `newInstance` vẫn có thể lỗi nếu constructor tự ném exception, tham số sai kiểu hoặc khởi tạo lớp gặp vấn đề.

`setAccessible(true)`/`trySetAccessible()` **không sửa modifier `private` trong class file**, không biến constructor thành public cho mọi code và không bỏ qua kiểm tra kiểu đối số hoặc logic validation bên trong constructor. Override thuộc reflection object đang được sử dụng.

## 6. JPMS: vì sao cùng một code hoạt động trên classpath nhưng thất bại ở named module?

Khi Java Platform Module System (Java 9+) được dùng với **named module**, public API và deep reflection có ranh giới riêng. Một private constructor nằm trong package của named module không nhất thiết được mở cho một module khác chỉ vì có thể tìm metadata.

Xét hai module `com.example.domain` (chứa class đích) và `com.example.framework` (cần Reflection). Descriptor của module domain có thể công bố:

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.internal to com.example.framework;
}
~~~

Ý nghĩa:

- `exports com.example.domain.api;` cho phép các module phù hợp truy cập public type/member trong package API theo quy tắc Java. **`exports` không tự cho phép deep reflection vào private constructor**.
- `opens com.example.domain.internal to com.example.framework;` cho phép module framework dùng deep reflection trong package internal, nếu các điều kiện khác phù hợp. Package được `opens` không vì vậy trở thành public API có thể import tùy ý ở compile time.
- Nếu package không được mở cho module gọi và caller không thuộc trường hợp JPMS cho phép, `ctor.trySetAccessible()` có thể trả `false`; `ctor.setAccessible(true)` có thể ném `java.lang.reflect.InaccessibleObjectException` (unchecked).
- Caller ở **cùng module** với declaring class có những khả năng khác caller xuyên module. Với các class trên classpath thuộc unnamed module, package thường mở cho deep reflection nên ví dụ đơn giản có thể bật override.

Nếu chương trình thật sự cần framework được gọi private constructor ở module khác, người thiết kế module có thể chủ động mở đúng package, ví dụ `opens ... to ...`, hoặc cung cấp một public factory API để tránh phụ thuộc vào private implementation. Trong quá trình triển khai, JVM option `--add-opens module/package=caller-module` cũng có thể cấp quyền mở tương ứng, nhưng cấu hình đó phải được quản lý rõ ràng và không nên dùng như cách “sửa nhanh” cho một API thiếu thiết kế.

**Đừng chuyển logic từ ví dụ trên thành “private constructor luôn gọi được bằng setAccessible(true)”.** Đó không phải cam kết của JPMS.

## 7. Các ngoại lệ thường gặp theo từng bước

| Bước | Lỗi/kết quả | Cách hiểu |
| --- | --- | --- |
| `getConstructor(String.class)` | `NoSuchMethodException` | Không có **public** constructor với signature yêu cầu; private constructor có thể vẫn tồn tại |
| `getDeclaredConstructor(...)` | `NoSuchMethodException` | Không có constructor khai báo trực tiếp với danh sách kiểu tham số chính xác |
| `ctor.newInstance(...)` khi access check từ chối | `IllegalAccessException` | Caller không được phép gọi constructor trong trạng thái hiện tại |
| `ctor.trySetAccessible()` | `false` | Không thể bật access-check override cho caller, thường do ranh giới JPMS |
| `ctor.setAccessible(true)` | `InaccessibleObjectException` | Yêu cầu mở quyền vượt khả năng được JPMS cho phép |
| `ctor.newInstance(...)` sai số lượng/kiểu tham số | `IllegalArgumentException` | Không tương thích signature hoặc receiver/đối số theo contract |
| `ctor.newInstance(...)` khi constructor body ném | `InvocationTargetException` | Xem `getCause()` để lấy lỗi gốc do constructor đích ném |
| `ctor.newInstance(...)` với abstract class | `InstantiationException` | Kiểu không thể trực tiếp khởi tạo thành instance |
| Khởi tạo class thất bại trong quá trình thực thi | Có thể có `ExceptionInInitializerError` | Lỗi xảy ra khi JVM chạy phần khởi tạo static, tách khỏi quyền constructor |

`IllegalAccessException` và `InvocationTargetException` là hai tình huống khác nhau: tình huống đầu tiên thường có nghĩa chưa được phép chạy constructor; tình huống thứ hai cho biết constructor đích đã được gọi và logic bên trong ném lỗi. Một chương trình xử lý Reflection tốt không nên bắt hết `Exception` rồi báo “không có quyền”.

Các constructor của **enum** còn có ràng buộc riêng: Reflection không được dùng `Constructor.newInstance` để tạo enum constant mới, ngay cả khi đã tìm được metadata của constructor. Constructor thuộc **non-static inner class** cũng có thể chứa tham số ẩn đại diện instance của outer class; signature tra cứu phải phù hợp với thực tế do compiler tạo. Đây là lý do xem `getParameterTypes()` thay vì đoán signature.

## 8. Private constructor trong singleton, utility class và framework

### Utility class

Một lớp chỉ có các static method thường dùng private constructor để ngăn khởi tạo thông thường:

~~~java
public final class TextUtils {
    private TextUtils() {
        throw new AssertionError("Utility class");
    }

    public static String trim(String value) {
        return value == null ? null : value.trim();
    }
}
~~~

Mẫu này không biến lớp thành “bất khả khởi tạo dưới mọi hình thức”. Nếu code có quyền Reflection hợp lệ để vào constructor private, lời gọi `newInstance()` sẽ chạy thân constructor và ném `AssertionError`, được bọc qua `InvocationTargetException`. Vì vậy private constructor không nên được xem như một ranh giới bảo mật độc lập.

### Singleton/factory

Một lớp singleton hoặc factory có thể dựa vào private constructor để kiểm soát số instance và validation. Deep reflection có thể vượt qua **rào cản truy cập ngôn ngữ** khi package được mở, nhưng không tự bỏ qua validation bên trong constructor. Nếu dự án cần bảo đảm invariant hoặc identity tuyệt đối, phải thiết kế bất biến, lifecycle và cơ chế quản lý phù hợp; không đặt toàn bộ tính đúng đắn vào modifier `private`.

### Framework và dependency injection

Một số framework cần tạo object từ constructor non-public. Chúng thường:

1. Tìm constructor phù hợp qua `getDeclaredConstructors()` hoặc `getDeclaredConstructor(...)`.
2. Chọn constructor theo annotation/signature hoặc quy tắc thiết kế cụ thể.
3. Kiểm tra khả năng truy cập; nếu cần deep reflection thì yêu cầu `opens` cho framework module.
4. Gọi `Constructor.newInstance(...)` với đối số đúng và báo lỗi có phân biệt quyền truy cập, chữ ký sai, hoặc exception từ body.

Không nên mặc định framework nào cũng có thể mở private constructor của mọi library/JDK class; trong named module, cấu hình mở package là một phần của hợp đồng vận hành.

## 9. So sánh `Constructor.newInstance` với `Class.newInstance`

`Class.newInstance()` là API cũ và đã **deprecated**. Nó yêu cầu constructor không đối số phù hợp và cách xử lý exception từ constructor không rõ ràng như API `Constructor.newInstance`.

Cách hiện đại nên dùng khi có yêu cầu Reflection:

~~~java
Constructor<MyType> ctor = MyType.class.getDeclaredConstructor();
MyType item = ctor.newInstance();
~~~

Đây là mảnh mã minh họa, giả định `MyType` tồn tại và có constructor không đối số; không phải chương trình độc lập. Nếu constructor đó private và caller không có quyền, vẫn cần xét `canAccess(null)` và khả năng mở quyền. `Constructor.newInstance` bọc exception từ constructor body trong `InvocationTargetException`, giúp phân biệt lỗi logic đích với lỗi truy cập.

Trong mã ứng dụng bình thường, nếu public factory hoặc cú pháp `new` đáp ứng được mục tiêu, cách gọi trực tiếp vẫn dễ đọc và dễ kiểm soát hơn. Chỉ dùng Reflection khi có lý do kỹ thuật rõ ràng như DI, serialization, testing hoặc tooling.

## 10. Checklist thực hành và tự kiểm tra

1. **Biết chính xác class đích:** constructor không kế thừa; dùng đúng `Class<?>` của lớp muốn tạo.
2. **Biết signature:** dùng `getDeclaredConstructor(int.class, String.class)` nếu constructor thực tế nhận `int, String`; `Integer.class` không tương đương `int.class` trong bước tìm.
3. **Phân biệt public lookup và declared lookup:** `getConstructor` không thấy private; `getDeclaredConstructor` có thể thấy nhưng không mở quyền.
4. **Kiểm tra quyền từ caller thực tế:** `ctor.canAccess(null)` và khả năng `trySetAccessible()`; không đoán kết quả chỉ từ modifier.
5. **Tôn trọng package và JPMS:** nếu cần truy cập non-public xuyên module, kiểm tra `opens` có đích và dùng API được phép.
6. **Xử lý lỗi tách biệt:** `NoSuchMethodException` là tra cứu; `IllegalAccessException` là truy cập; `InvocationTargetException.getCause()` là lỗi từ constructor body; `IllegalArgumentException` thường liên quan signature/arguments.
7. **Tránh coi private là bảo mật tuyệt đối:** Reflection hợp lệ có thể vượt rào cản truy cập ngôn ngữ; invariants của object cần được bảo vệ ngay trong thiết kế.

**Câu hỏi 1.** `getDeclaredConstructor(String.class)` trả về `Constructor` của private constructor. Có được gọi `newInstance("x")` ngay không? **Chưa chắc**: phải xét quyền của caller và trạng thái access-check override.

**Câu hỏi 2.** Vì sao `getConstructor(String.class)` ném `NoSuchMethodException` còn `getDeclaredConstructor(String.class)` thành công? **Vì thứ nhất chỉ tìm public constructor, thứ hai tìm constructor khai báo trực tiếp ở mọi mức truy cập.**

**Câu hỏi 3.** `trySetAccessible()` trả `false` khi framework khác module truy cập private constructor. Cách xử lý? **Dùng API hợp lệ hoặc mở chính xác package qua `opens` theo thiết kế module; không tiếp tục gọi như thể override đã bật.**

**Câu hỏi 4.** Constructor tự ném `IllegalArgumentException`. Lúc `Constructor.newInstance` chạy, caller quan sát loại exception nào? **`InvocationTargetException`**, và exception gốc được lấy qua `getCause()`.

**Câu hỏi 5.** Có cần `canAccess(someObject)` trước khi gọi constructor không? **Không.** Constructor chưa có receiver; gọi `canAccess(null)`.

Khi thao tác private constructor bằng Java Reflection, hãy theo đúng trình tự **tìm constructor → xác định quyền và ranh giới module → cân nhắc mở quyền → gọi với tham số hợp lệ → xử lý exception từ constructor**. Sự phân tách này giúp code Reflection đúng về ngữ nghĩa, minh bạch về quyền và dễ bảo trì.
