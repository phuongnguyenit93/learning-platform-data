# Lookup như một đối tượng mang quyền tra cứu thành viên

## 1. Vì sao Lookup được xem là một capability object?

Trong Java, `java.lang.invoke.MethodHandles.Lookup` là một **đối tượng mang quyền** (*capability object*) dùng để tạo `MethodHandle` và `VarHandle` tới phương thức, constructor hoặc field. Một `Lookup` không chỉ biết **tìm thành viên nào**, mà còn biết **ngữ cảnh class/module nào được phép tìm**. Đó là trọng tâm của chủ đề **Quyền Lookup**.

Hai cách tạo điển hình:

~~~java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup caller = MethodHandles.lookup();
MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
~~~

Đây là code minh họa đặt trong một phương thức Java. Dù cùng kiểu `Lookup`, hai giá trị không có quyền giống nhau:

- `MethodHandles.lookup()` trả lookup có quyền theo **class thực sự gọi** nó; đây là phương thức *caller-sensitive*. Nó có thể truy cập private member của class gọi và những nestmate hợp lệ.
- `MethodHandles.publicLookup()` tạo lookup được giới hạn vào **public API**: public member của public types trong package được export vô điều kiện theo quy tắc JPMS. Nó không tự cho quyền private.
- `Lookup.in(Target.class)` đổi ngữ cảnh tra cứu sang class khác nhưng **không tăng quyền**; vượt ranh giới nest, package, module có thể làm quyền bị giảm.
- `Lookup.dropLookupMode(...)` tạo một lookup mất một số quyền.
- `MethodHandles.privateLookupIn(Target.class, callerLookup)` có thể cấp private lookup tới target **nếu caller có đủ quyền và điều kiện module cho phép**, không phải cách bỏ qua mọi kiểm tra `private`.

**Ghi chú phiên bản:** `MethodHandles.Lookup` là API đang được dùng trong JDK hiện đại. Bài giảng dùng Java 17+ và các quy tắc module đang áp dụng, không sử dụng phương thức preview hoặc thủ thuật truy cập nội bộ legacy.

### Mục tiêu

Sau khi học, bạn có thể giải thích vì sao trao `Lookup` là ủy quyền quyền tra cứu, đọc `lookupClass()`/`lookupModes()`, tạo/call handles, hiểu nestmates, phân biệt `exports` và `opens`, xử lý lỗi quyền truy cập, và hạn chế quyền khi thiết kế framework hoặc plugin không tin cậy.

## 2. Lookup lưu ngữ cảnh nào?

| API | Ý nghĩa |
|---|---|
| `lookupClass()` | Class đang là ngữ cảnh được dùng để kiểm tra quyền |
| `lookupModes()` | Bitmask những lớp quyền mà Lookup còn có |
| `previousLookupClass()` | Class được ghi lại khi Lookup teleport giữa hai module; thường null với lookup ban đầu |
| `hasPrivateAccess()` | Có private-access mode theo hợp đồng |
| `hasFullPrivilegeAccess()` | Có đồng thời `PRIVATE` và `MODULE` access |
| `accessClass(Class<?>)` | Kiểm tra class có thể truy cập; không nói rằng mọi member được phép |
| `findVirtual/findStatic/findConstructor` | Tra cứu và tạo method handle |
| `findGetter/findSetter/findVarHandle` | Tạo handle truy cập field |
| `in(Class<?>)` | Chuyển lookup class với quyền không tăng |
| `dropLookupMode(int)` | Loại một access mode và các quyền liên đới |

**Điểm mấu chốt:** `lookupClass()` khác với class mà bạn muốn truy cập. Nếu `Owner` gọi `MethodHandles.lookup()`, sau đó truyền Lookup cho framework `Formatter`, lookup class vẫn là `Owner`. Lookup không tự đổi thành `Formatter` chỉ vì được truyền làm tham số.

Một `Class<?>` thuần chỉ nhận diện kiểu; `Class.getDeclaredMethods()` có thể phản ánh private methods tồn tại, nhưng **không tự mang quyền truy cập chúng**. `Lookup` kết hợp ngữ cảnh class và quyền để tạo handle hợp lệ.

### Trước và sau khi tạo MethodHandle

~~~text
MethodHandles.lookup() trong class C
              |
              v
    Lookup { class=C, modes=... }
              |
              v
       findVirtual/findStatic
       findVarHandle/findGetter
              |
      +-------+-------+
      |               |
    Hợp lệ         Không hợp lệ
      |               |
      v               v
 MethodHandle       IllegalAccessException
 / VarHandle        hoặc lỗi member/signature
      |
      v
 invokeExact/invoke
 get/set/compareAndSet
~~~

`Lookup` thường áp dụng **access checks khi tạo direct handle**, khác Core Reflection có cơ chế kiểm tra ở lúc thao tác. Sau khi tạo, handle là **capability** có thể được gọi bởi code được nhận handle phù hợp với kiểu; code nhận handle không phải tự gọi private lookup thêm lần nữa. Vì thế **không chỉ Lookup mà cả handle private được tạo cũng cần được bảo vệ**.

## 3. Các access modes còn được hỗ trợ

`lookup.lookupModes()` trả bit mask gồm các mode:

| Mode | Quyền khái quát |
|---|---|
| `PUBLIC` | Thành viên public theo điều kiện module readability/exports |
| `PRIVATE` | Private member của lookup class và nestmates hợp lệ |
| `PROTECTED` | Protected member theo điều kiện kế thừa và receiver |
| `PACKAGE` | Package-private members thuộc runtime package phù hợp |
| `MODULE` | Quyền trong phạm vi module của lookup class |
| `UNCONDITIONAL` | Public access tới public types trong package được export vô điều kiện, không yêu cầu readability |
| `ORIGINAL` | Lookup do ngữ cảnh gốc tạo, liên quan các khả năng như caller-sensitive methods |

Có mode không nghĩa “được truy cập mọi nơi”. Một lookup có `PRIVATE` **không** tự truy cập private field của bất kỳ class trong JVM. Quy tắc nest/module/package tiếp tục áp dụng.

**Điểm tinh tế:** `publicLookup()` mang `UNCONDITIONAL`, khác mode `PUBLIC` trong các lookup gắn với module cụ thể. Tránh code kiểm tra sai rằng `publicLookup().lookupModes()` phải có bit `PUBLIC` mới được xem là public access.

Kiểm tra quyền:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
boolean hasPrivate =
        (lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
boolean full = lookup.hasFullPrivilegeAccess();
Class<?> source = lookup.lookupClass();
~~~

Đoạn này có thể đặt trong một method, import `MethodHandles` phù hợp. `hasFullPrivilegeAccess()` cho biết lookup có private/module access của **ngữ cảnh được phép**; không phải “root toàn JVM”.

## 4. Chọn API tra cứu theo loại thành viên

| Method | Thành viên | Chữ ký tra cứu |
|---|---|---|
| `findStatic(owner,name,type)` | Static method | MethodType gồm return + tham số khai báo |
| `findVirtual(owner,name,type)` | Instance method | MethodType không chứa receiver; handle kết quả có receiver |
| `findConstructor(owner,type)` | Constructor | MethodType dùng `void.class` làm return |
| `findGetter/Setter(owner,name,fieldType)` | Instance field | Receiver và kiểu field |
| `findStaticGetter/Setter` | Static field | Không có receiver instance |
| `findVarHandle` | Instance field | Đọc/ghi/atomic theo access modes của VarHandle |
| `findStaticVarHandle` | Static field | Field static |
| `findSpecial` | Invokespecial-like | Quy tắc riêng, không phải tự do vượt virtual dispatch |
| `unreflect(Method)` | Từ reflection Method | Vẫn kiểm tra quyền |
| `accessClass(Class)` | Truy cập class | Không tạo handle |

Ví dụ public virtual method:

~~~java
MethodHandles.Lookup pub = MethodHandles.publicLookup();
MethodHandle upper = pub.findVirtual(
        String.class, "toUpperCase",
        MethodType.methodType(String.class));
String result = (String) upper.invokeExact("java");
~~~

Đoạn minh họa nằm trong phương thức `throws Throwable` với imports `MethodHandle`, `MethodHandles`, `MethodType`. `result` là `"JAVA"`.

**Không đặt receiver vào MethodType của `findVirtual`.** Khi tìm phương thức instance `String greet(String name)`, MethodType tra cứu là `methodType(String.class, String.class)`. Handle kết quả mới có receiver ở vị trí đầu khi gọi:

~~~java
String hello = (String) mh.invokeExact(service, "Java");
~~~

Ở đây `mh` là handle tới `Service.greet` và `service` có đúng kiểu `Service`. `invokeExact` yêu cầu kiểu tham số/return ở call site khớp chính xác handle type. `invoke` và `asType` cho phép một số chuyển đổi theo quy tắc riêng; đừng dùng chúng để che lỗi quyền.

Ví dụ static:

~~~java
MethodHandle max = MethodHandles.publicLookup().findStatic(
        Math.class, "max",
        MethodType.methodType(int.class, int.class, int.class));
int value = (int) max.invokeExact(4, 9);  // 9
~~~

Ví dụ constructor:

~~~java
MethodHandle ctor = MethodHandles.publicLookup().findConstructor(
        StringBuilder.class, MethodType.methodType(void.class));
StringBuilder sb = (StringBuilder) ctor.invokeExact();
~~~

Cả hai đoạn nằm trong method `throws Throwable`. `findConstructor` mô tả constructor với return `void.class`, trong khi handle được tạo trả về instance mới.

## 5. Chương trình Java 17+ hoàn chỉnh

Ví dụ dưới đây đã được biên dịch với `javac --release 17` và chạy thử thực tế. Nó so sánh lookup gốc, public lookup, `dropLookupMode`, `Lookup.in` và `privateLookupIn`, đồng thời thử private method và private field qua handles.

Lưu file **`LookupCapabilityDemo.java`**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;

public class LookupCapabilityDemo {
    public static final class Service {
        public String greet(String name) { return "Hello, " + name; }
    }

    private static final class NestVault {
        private int pin = 7;
        private String secret() { return "nest-secret"; }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup caller = MethodHandles.lookup();
        MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();

        System.out.println("callerClass=" + caller.lookupClass().getSimpleName());
        System.out.println("fullAccess=" + caller.hasFullPrivilegeAccess());
        System.out.println("publicFullAccess=" + publicOnly.hasFullPrivilegeAccess());

        MethodHandle greeting = publicOnly.findVirtual(
                Service.class, "greet",
                MethodType.methodType(String.class, String.class));
        String hello = (String) greeting.invokeExact(new Service(), "Java");
        System.out.println("public=" + hello);

        NestVault vault = new NestVault();
        MethodHandle secret = caller.findVirtual(
                NestVault.class, "secret", MethodType.methodType(String.class));
        System.out.println("nestPrivate=" + (String) secret.invokeExact(vault));

        VarHandle pinHandle = caller.findVarHandle(NestVault.class, "pin", int.class);
        pinHandle.set(vault, 42);
        System.out.println("privateField=" + (int) pinHandle.get(vault));

        MethodHandles.Lookup weaker =
                caller.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        try {
            weaker.findVirtual(NestVault.class, "secret",
                    MethodType.methodType(String.class));
            System.out.println("reduced=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("reduced=denied");
        }

        try {
            caller.in(ExternalVault.class).findVirtual(
                    ExternalVault.class, "privateEcho",
                    MethodType.methodType(String.class));
            System.out.println("in=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("in=denied");
        }

        MethodHandles.Lookup granted =
                MethodHandles.privateLookupIn(ExternalVault.class, caller);
        MethodHandle hidden = granted.findVirtual(
                ExternalVault.class, "privateEcho",
                MethodType.methodType(String.class));
        System.out.println("privateLookupIn=" +
                (String) hidden.invokeExact(new ExternalVault()));

        try {
            MethodHandles.privateLookupIn(ExternalVault.class, publicOnly);
            System.out.println("publicUpgrade=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("publicUpgrade=denied");
        }

        MethodHandle max = publicOnly.findStatic(
                Math.class, "max",
                MethodType.methodType(int.class, int.class, int.class));
        System.out.println("publicStatic=" + (int) max.invokeExact(4, 9));
    }
}

class ExternalVault {
    private String privateEcho() {
        return "another-class-secret";
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac --release 17 LookupCapabilityDemo.java
java LookupCapabilityDemo
~~~

**Standard output chính xác đã kiểm tra:**

~~~text
callerClass=LookupCapabilityDemo
fullAccess=true
publicFullAccess=false
public=Hello, Java
nestPrivate=nest-secret
privateField=42
reduced=denied
in=denied
privateLookupIn=another-class-secret
publicUpgrade=denied
publicStatic=9
~~~

### Phân tích code và output

1. `lookup()` trong `main` trả lookup class `LookupCapabilityDemo`. Nó không trở thành `Service` hoặc `ExternalVault`.
2. `fullAccess=true` chỉ quyền private/module tương ứng caller, không cho phép truy cập mọi class trong hệ thống.
3. `publicFullAccess=false` cho thấy public lookup không có full privilege.
4. `public=Hello, Java` cho thấy public instance method có thể được gọi qua `publicLookup`.
5. `NestVault` là **nested class cùng nest** với outer class, nên caller lookup có thể tìm private `secret()` của nó.
6. `findVarHandle` lấy handle đến private field `pin` hợp lệ; `set` đổi giá trị từ 7 thành 42.
7. `dropLookupMode(PRIVATE)` tạo lookup không còn quyền cần thiết: `reduced=denied`.
8. `ExternalVault` là **top-level class khác nest**, dù cùng package/unnamed module. `caller.in(ExternalVault.class)` không tự cấp private access: `in=denied`.
9. `MethodHandles.privateLookupIn(ExternalVault.class, caller)` được phép trong cùng module khi caller có quyền, nên `privateLookupIn=another-class-secret`.
10. `privateLookupIn(..., publicOnly)` thất bại vì nguồn không có `PRIVATE` và `MODULE`: `publicUpgrade=denied`.
11. `Math.max(int,int)` public static, do đó `publicStatic=9`.

Ví dụ dùng string `"nest-secret"` chỉ để kiểm chứng quyền; không đưa mật khẩu hoặc dữ liệu nhạy cảm thật vào cách minh họa này.

## 6. Nestmates và giới hạn của Lookup.in

Các class trong cùng **nest** có thể truy cập private members của nhau theo quy tắc JVM. Hai class top-level bất kỳ nằm cùng package **không tự là nestmates**. Vì vậy một Lookup có `PACKAGE` access không tự được quyền `PRIVATE` của class khác nest.

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandles.Lookup moved = lookup.in(ExternalVault.class);
boolean privateMode =
        (moved.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
~~~

Đoạn minh họa đặt trong `LookupCapabilityDemo` của chương trình trên sẽ có `privateMode == false`. **Không kết luận mọi `in(...)` đều xóa PRIVATE**: cùng nest và các điều kiện phù hợp có thể giữ private access.

Các phép biến đổi:

| Thao tác | Quy tắc chính |
|---|---|
| `lookup.in(sameNestClass)` | Có thể giữ private access |
| `lookup.in(otherNestSamePackage)` | Mất private access |
| `lookup.in(otherPackageSameModule)` | Mất package/private access |
| `lookup.in(classInOtherModule)` | Mất module/package/private, còn public access tùy điều kiện |
| `lookup.dropLookupMode(PRIVATE)` | Bỏ private cùng những modes liên đới theo hợp đồng |
| `lookup.dropLookupMode(MODULE)` | Bỏ MODULE, PACKAGE và PRIVATE |

**Quyền đã mất không tự khôi phục** bằng `in(...)`. Một lookup đã hạ quyền cũng không nhất thiết bằng `publicLookup()` vì có thể còn mode `MODULE`/`PACKAGE` khác với `UNCONDITIONAL`.

## 7. privateLookupIn và điều kiện JPMS

Chữ ký:

~~~java
public static MethodHandles.Lookup privateLookupIn(
        Class<?> targetClass,
        MethodHandles.Lookup callerLookup
) throws IllegalAccessException
~~~

Đây là chữ ký API tham khảo, **không phải method cần tự cài đặt**.

Để gọi hợp lệ:

1. `callerLookup` phải có cả **`PRIVATE` và `MODULE` access**.
2. Nếu class target cùng module với caller lookup class, có thể tạo private lookup vào target theo các quy tắc áp dụng.
3. Nếu target ở **module khác**, module caller phải **đọc** module đích và package của target phải được module đích **`opens` cho caller module** (hoặc mở vô điều kiện). **`exports` không đồng nghĩa `opens`**.
4. Khi `privateLookupIn` teleport sang module khác, lookup kết quả mất `MODULE` và có previous lookup class. Không thể dùng lookup đã mất MODULE rồi tiếp tục có được private lookup vào một module thứ ba.
5. Không dùng `privateLookupIn` từ `publicLookup()` để tự nâng quyền, như ví dụ cho thấy.

### exports và opens

Giả sử một named module sở hữu dữ liệu:

~~~java
module owner.module {
    exports org.example.api;
    opens org.example.internal to framework.module;
}
~~~

Và framework tin cậy:

~~~java
module framework.module {
    requires owner.module;
}
~~~

Đây là **hai module-info.java minh họa**, không phải chương trình độc lập (cần package/class thực và module path để chạy). `exports` cho phép public API được truy cập theo điều kiện đọc module, còn `opens ... to framework.module` cho phép deep reflection/private lookup đối với package được chọn. Mở package có chủ đích là quyết định bảo mật của chủ sở hữu module.

**Không thêm `--add-opens ...=ALL-UNNAMED` tràn lan** chỉ để tránh lỗi trong development. Tùy chọn này có thể hỗ trợ triển khai kiểm soát được, nhưng nó mở rộng khả năng truy cập; nên ưu tiên public API hoặc module descriptor rõ ràng.

### previousLookupClass khi teleport

`previousLookupClass()` (có từ Java 14) cho biết class/module mà lookup được chuyển đi từ đó khi teleport qua module. Khi current lookup class và previous lookup class ở các module khác nhau, việc truy cập public có thể cần thỏa **cả hai phía** về readability/exports. Đi qua module thứ ba không liên quan có thể mất toàn bộ access modes. Vì vậy không dùng `Lookup.in` như một mẹo “đi vòng các module” để tăng quyền.

## 8. Vì sao không nên phát full Lookup cho plugin?

Đoạn sau thể hiện điều cần tránh khi bên nhận không đáng tin:

~~~java
public static MethodHandles.Lookup expose() {
    return MethodHandles.lookup();
}
~~~

Trong class có private members, API công khai như vậy có thể cấp cho bên ngoài khả năng tạo private handles theo quyền của class. Việc dùng Lookup thay vì reflection **không tự làm hành vi đó an toàn hơn**.

Khuyến nghị theo nguyên tắc **ít quyền nhất**:

- Nếu plugin chỉ cần gọi public methods, dùng `publicLookup()` hoặc public interface.
- Nếu chỉ cần một thao tác cụ thể, cung cấp một method public có kiểm tra input/quyền nghiệp vụ.
- Nếu buộc phải trao một MethodHandle private, **coi handle là capability**; không đặt ở registry public và không truyền tiếp sang code không được tin cậy.
- Nếu phải trao Lookup, cân nhắc `dropLookupMode(...)` hoặc API hẹp hơn và kiểm thử access modes thực tế.
- Nếu framework/serializer được tin cậy cần private access, module sở hữu dữ liệu có thể `opens` đúng package cho framework; framework dùng `privateLookupIn` để tạo handles có phạm vi mục tiêu.

Ví dụ public interface giới hạn:

~~~java
interface TaskAction {
    void execute();
}
~~~

thường dễ kiểm soát hơn một interface nhận trực tiếp đặc quyền:

~~~java
interface Plugin {
    void initialize(MethodHandles.Lookup privilegedLookup);
}
~~~

Hai interface trên là **minh họa**, không phải kiến trúc bắt buộc của mọi ứng dụng. Một `Lookup` là access-control capability **trong JVM**, không phải sandbox đủ để cô lập arbitrary untrusted code; nếu thật sự cần chạy mã không tin cậy, dùng ranh giới OS/tiến trình thích hợp.

## 9. Phân biệt lỗi tra cứu và lỗi gọi handle

| Tình huống | Ngoại lệ/hậu quả | Cách kiểm tra |
|---|---|---|
| Không có method với tên/signature | `NoSuchMethodException` | Xác nhận tên, return type, tham số |
| Field không tồn tại/khác type | `NoSuchFieldException` | Xác nhận field và static/instance |
| Lookup không đủ quyền | `IllegalAccessException` | Kiểm tra lookupClass, modes, nest, exports/opens |
| `findVirtual` cho method static | Tra cứu sai | Dùng `findStatic` |
| `invokeExact` khác kiểu handle | `WrongMethodTypeException` | So khớp receiver/arguments/return ở call site |
| Ép kiểu không phù hợp | `ClassCastException` | Kiểm tra kiểu runtime/`asType` |
| `VarHandle.set` vào final field | Không hỗ trợ thao tác ghi | Không xem VarHandle là cách vượt `final` |
| Private handle bị lộ | Bên nhận có thể thực hiện thao tác đã cấp | Bảo vệ handle và nơi lưu |
| Module chưa mở package | `IllegalAccessException` | Xác minh `opens`, readability và quyền nguồn |

**Không tự động bắt mọi `Throwable` rồi gọi `privateLookupIn` như “fallback”.** `NoSuchMethodException` có thể chỉ ra sai signature, trong khi `IllegalAccessException` có thể phản ánh một ranh giới bảo mật có chủ đích.

### unreflect và setAccessible

`Lookup.unreflect(Method)` có thể tạo MethodHandle từ một reflection Method, nhưng vẫn có kiểm tra quyền liên quan. `setAccessible(true)` của Core Reflection **không bảo đảm** vượt được strong encapsulation của named modules. Không dùng chúng như thủ thuật phá bảo vệ module.

## 10. Checklist thực tế

- [ ] Đã thực sự cần dynamic MethodHandle/VarHandle thay vì gọi Java thông thường?
- [ ] `lookup()` được gọi ở đúng class chủ sở hữu quyền?
- [ ] Không nhầm lookup class với target class hoặc class nhận Lookup?
- [ ] Đã biết `lookupModes()` và phân biệt `PUBLIC` với `UNCONDITIONAL`?
- [ ] Đã áp dụng `findVirtual`/`findStatic` đúng loại method và MethodType?
- [ ] Không đưa receiver vào MethodType khi `findVirtual`?
- [ ] Đã kiểm tra call site của `invokeExact` đúng kiểu?
- [ ] Đã xét nestmates khi tìm private member?
- [ ] Có hiểu `Lookup.in` không tăng quyền và `dropLookupMode` có thể xóa nhiều modes?
- [ ] Nếu dùng `privateLookupIn`, nguồn có `PRIVATE` + `MODULE`?
- [ ] Với module khác, có đúng `requires`/readability và `opens` cho caller?
- [ ] Không nhầm `exports` public API với `opens` deep access?
- [ ] Không trao private Lookup/handle cho plugin không tin cậy?
- [ ] Đã phân biệt `NoSuchMethodException`, `IllegalAccessException` và `WrongMethodTypeException`?
- [ ] Đã chạy test bằng named modules thật nếu hệ thống triển khai JPMS?
- [ ] Không thêm `--add-opens` đại trà để bỏ qua một lỗi thiết kế?
- [ ] Có kiểm thử lại access rights khi thay đổi package/module hoặc JDK?

## 11. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `Lookup` là capability object?

**Đáp án:** Nó mang lookup class và access modes để tạo handles. Trao nó cho code khác có thể ủy quyền khả năng tạo handles tới các member nằm trong phạm vi của lookup.

**Câu 2.** `MethodHandles.lookup()` gọi trong class A rồi gửi cho class B có tự đổi lookup class thành B không?

**Đáp án:** Không. Nó vẫn gắn với A, trừ khi Lookup được biến đổi bằng API.

**Câu 3.** `publicLookup()` có truy cập private của mọi public class không?

**Đáp án:** Không. Nó chỉ tiếp cận public member của public types được export vô điều kiện theo quy tắc JPMS.

**Câu 4.** `lookup.in(Other.class)` có tự trao private quyền của Other không?

**Đáp án:** Không. Nó chỉ chuyển ngữ cảnh và có thể làm giảm quyền, nhất là khi sang khác nest.

**Câu 5.** Vì sao `privateLookupIn(Target.class, publicLookup())` thất bại?

**Đáp án:** `publicLookup()` không có đồng thời `PRIVATE` và `MODULE` access theo yêu cầu.

**Câu 6.** Với target trong named module khác, chỉ `exports` là đủ cho private lookup không?

**Đáp án:** Không. Cần module readability và `opens` package đích cho caller, ngoài quyền của caller lookup.

**Câu 7.** Nếu đã tạo private MethodHandle rồi trao cho mã khác, mã nhận có cần private lookup mới ở mỗi lần invoke không?

**Đáp án:** Không. Access check khi tạo direct handle đã hoàn tất; đó là lý do phải bảo vệ handle.

**Câu 8.** `dropLookupMode(MODULE)` có mất thêm các mode khác không?

**Đáp án:** Có. Theo Javadoc, nó còn loại `PACKAGE` và `PRIVATE`.

**Câu 9.** Khi dùng `findVirtual`, MethodType truyền vào có receiver không?

**Đáp án:** Không. Receiver được thêm vào method handle kết quả và truyền làm đối số đầu khi gọi.

**Câu 10.** `WrongMethodTypeException` có luôn nghĩa là không đủ quyền private?

**Đáp án:** Không. Nó phản ánh kiểu call site không khớp handle; quyền tra cứu thường được kiểm tra khi `find...`.

**Câu 11.** `hasFullPrivilegeAccess()==true` nghĩa là có thể đọc mọi private member trong Java không?

**Đáp án:** Không. Nó chỉ phản ánh quyền private/module trong lookup context. Các quy tắc module/nest/target vẫn quyết định.

**Câu 12.** Khi plugin chỉ cần một hành động, nên cấp full Lookup hay API giới hạn?

**Đáp án:** Ưu tiên public interface hoặc capability giới hạn theo hành động được phép; không phát full Lookup vì tiện.

## 12. Tài liệu tham khảo chính thức

- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): access modes, quyền private/public, `in`, `dropLookupMode` và cross-module lookup.
- [Java SE 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup` caller-sensitive, `publicLookup` và `privateLookupIn`.
- [Java SE 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `invoke`, `asType`.
- [Java SE 17 — VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): field access và atomic operations.
- [JLS Java SE 17 `6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): public/protected/package/private.
- [JVMS Java SE 17 `5.4.4 — Access Control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): kiểm tra access của JVM.
- [Java SE 25 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): đối chiếu API vẫn được duy trì trong JDK mới.

**Kết luận:** `Lookup` là **đối tượng mang quyền tra cứu**. `lookup()` mang quyền của caller, `publicLookup()` chỉ cho public API được export, `in(...)`/`dropLookupMode(...)` không làm tăng quyền và `privateLookupIn(...)` cần authorization rõ ràng. Cần bảo vệ cả `Lookup` và handles được tạo, dùng đúng module openness và nguyên tắc **ít quyền nhất cần thiết**.