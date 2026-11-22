# MethodHandles.Lookup và ngữ cảnh kiểm tra truy cập khi định nghĩa lớp ẩn (Java 15+)

## 1. Vấn đề cốt lõi

Từ **Java 15**, Java hỗ trợ chính thức **hidden class** (lớp ẩn) thông qua `MethodHandles.Lookup.defineHiddenClass(...)`. Cơ chế này phục vụ các framework sinh mã, trình triển khai ngôn ngữ, bộ tạo proxy nội bộ hoặc hệ thống cần tạo lớp dùng trong một phạm vi hẹp, **không phải lớp thông thường có thể tìm bằng tên nhị phân**.

Phương thức có chữ ký:

~~~java
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException;
~~~

Nội dung `bytes` phải là **class file hợp lệ**; phương thức định nghĩa một hidden class rồi trả về **`Lookup` mới với chính hidden class làm `lookupClass()`**. Điểm quan trọng của bài này là **quyền tạo lớp và quyền truy cập thành viên không phụ thuộc vào nơi giữ mảng byte**, mà phụ thuộc vào **ngữ cảnh và năng lực truy cập của đối tượng `Lookup`**.

Đây là API hiện hành, được dùng tiếp trên các JDK mới; không cần API nội bộ hay cơ chế preview.

## 2. Lookup là một năng lực truy cập, không chỉ là công cụ tìm phương thức

`java.lang.invoke.MethodHandles.Lookup` lưu trữ **định danh lớp dùng làm ngữ cảnh kiểm tra truy cập** (*lookup class*) và các **access mode** đã được cấp cho đối tượng đó. Khi gọi các phương thức như `findStatic`, `findVirtual`, `findGetter` hoặc `findConstructor`, Java kiểm tra **lớp đích, thành viên đích, mô-đun và quyền của Lookup** trước khi tạo `MethodHandle` tương ứng.

Ví dụ:

~~~java
MethodHandles.Lookup here = MethodHandles.lookup();
Class<?> callerClass = here.lookupClass();
boolean full = here.hasFullPrivilegeAccess();
~~~

`MethodHandles.lookup()` là một phương thức **caller-sensitive**: ngữ cảnh gốc được xác lập theo **lớp trực tiếp gọi** nó. Gọi từ một helper khác rồi chuyển `Lookup` sang nơi khác không tự động làm quyền thay đổi thành quyền của người nhận.

**Phân biệt hai thời điểm kiểm tra:**

1. **Tạo MethodHandle:** `Lookup.findStatic(...)` và các factory liên quan thực hiện kiểm tra quyền khi tạo handle; thành viên không tồn tại dẫn đến ngoại lệ như `NoSuchMethodException`, còn không đủ quyền dẫn đến `IllegalAccessException`.
2. **Gọi MethodHandle đã có:** handle thường không lặp lại kiểm tra truy cập của `Lookup` trong mỗi lần gọi. Vì vậy, chia sẻ một handle đặc quyền hoặc `Lookup` đặc quyền đồng nghĩa **ủy quyền một năng lực thực sự**, không phải chỉ đưa thông tin tra cứu.

Bởi vậy, **không cung cấp `Lookup` có quyền riêng tư cho mã không tin cậy**.

### Các kiểu Lookup hay gặp

| Cách tạo | Ngữ cảnh và ý nghĩa |
| --- | --- |
| `MethodHandles.lookup()` | `Lookup` của lớp đang gọi, thường có **full privilege** theo lớp gốc; có khả năng truy cập private của lớp/nest tương ứng và mô-đun. |
| `MethodHandles.publicLookup()` | Năng lực công khai rất hạn chế, chỉ dùng được thành viên public thuộc các kiểu/package được xuất công khai theo quy tắc tương ứng. Không thể dùng để tự ý định nghĩa hidden class. |
| `lookup.in(Target.class)` | Chuyển lookup class sang kiểu khác nhưng **không nâng quyền**; trong quá trình chuyển có thể mất các mode. |
| `lookup.dropLookupMode(mode)` | Giảm đặc quyền một cách chủ động; không có thao tác đối xứng để tự phục hồi quyền đã mất. |
| `MethodHandles.privateLookupIn(Target.class, callerLookup)` | Xin một `Lookup` với quyền private trên `Target` **khi các điều kiện truy cập và module cho phép**. Không phải công cụ vượt qua giới hạn mô-đun tùy tiện. |

Các access mode được phản ánh qua `lookupModes()`, gồm các mode như `PUBLIC`, `PRIVATE`, `PACKAGE`, `PROTECTED`, `MODULE` và `ORIGINAL`. **Full privilege** ở đây đòi năng lực `PRIVATE` **và** `MODULE`. Không nên đồng nhất “truy cập public” hoặc “có private nhưng không có module” với khả năng định nghĩa hidden class.

`ORIGINAL` là quyền riêng của lookup bắt nguồn từ ngữ cảnh gốc (hoặc lookup đặc biệt được trả khi tạo hidden class), có các tác dụng khác như hỗ trợ một số caller-sensitive method. **Không cần phải suy diễn `ORIGINAL` từ tên lớp hay từ mức truy cập public**.

## 3. Quy tắc kiểm tra truy cập của defineHiddenClass

`Lookup.defineHiddenClass(bytes, initialize, options)` không nhận một `ClassLoader` tùy ý để bỏ qua kiểm soát. Những ràng buộc thiết yếu là:

1. **`Lookup` phải có full privilege:** thiếu quyền `PRIVATE` hoặc `MODULE` dẫn đến `IllegalAccessException`.
2. **Mảng byte phải chứa class file hợp lệ:** JVM kiểm tra cấu trúc, phiên bản class file, liên kết và xác minh bytecode. Dữ liệu lỗi có thể gây `ClassFormatError`, `UnsupportedClassVersionError`, `VerifyError` hoặc các `LinkageError` thích hợp.
3. **Tên lớp bên trong class file phải thuộc cùng package với `lookupClass()`.** Không thể dùng `Lookup` của package này để định nghĩa hidden class từ class file khai báo package khác; tình huống đó bị từ chối bằng `IllegalArgumentException`.
4. **Lớp ẩn được định nghĩa trong cùng runtime package, module và protection domain với lookup class**, dùng class loader gắn với lookup class. Đây là điều kiện quan trọng đối với quyền truy cập package/module.
5. **`initialize` điều khiển khởi tạo lớp:** giá trị `true` khiến JVM thực hiện khởi tạo lớp mới; `false` không chủ động chạy class initializer tại thời điểm `defineHiddenClass` (việc khởi tạo có thể xảy ra sau đó theo quy tắc Java).
6. **`options`** có các lựa chọn `NESTMATE` và `STRONG`, tương ứng điều khiển quan hệ nest và vòng đời liên kết với class loader.

Dữ liệu class file có thể được biên dịch từ một lớp mẫu. Trong ví dụ độc lập ở mục 6, chương trình đọc `HiddenLookupDemo$Template.class` rồi định nghĩa **một lớp ẩn mới**, không tái sử dụng trực tiếp `Class<?>` có tên thông thường của `Template`.

### Tại sao chỉ cho class file cùng package?

`Lookup` là chứng cứ về khả năng truy cập của mã đã được tin cậy trong một phạm vi package/module. Nếu có thể định nghĩa một hidden class trong package bất kỳ chỉ bằng cung cấp bytes, mã gọi sẽ có cơ hội đặt lớp mới bên cạnh các thành viên package-private mà nó vốn không có quyền. Ràng buộc **same package** và **full privilege** ngăn cách sử dụng đó.

Phải nhớ hai điều kiện này **độc lập**: một `Lookup` đủ quyền nhưng bytecode thuộc package khác vẫn thất bại; bytecode thuộc đúng package nhưng `Lookup` thiếu quyền vẫn thất bại.

## 4. Lớp ẩn không phải lớp có tên nhị phân thông thường

Lớp tạo ra bởi `defineHiddenClass` có các đặc điểm:

- `hiddenLookup.lookupClass().isHidden()` trả `true`.
- `Class.getName()` của hidden class có dạng gồm tên nền và **dấu `/` cùng hậu tố do JVM tạo**, **không phải binary name hợp lệ**. Không nên so sánh hậu tố cụ thể vì nó không ổn định.
- Không tìm lại hidden class qua `Class.forName(String)`, `ClassLoader.loadClass(String)` hay `Lookup.findClass(String)` bằng tên đó.
- Thay vì tìm bằng tên, framework giữ **`Class<?>`**, **`Lookup`** hoặc **`MethodHandle`** trả về khi định nghĩa lớp.
- Hidden class không trở thành một kiểu có thể dùng như tên lớp thông thường trong constant pool của lớp khác. Nó đặc biệt phù hợp với lớp triển khai có vòng đời gắn với framework.

**Hai tùy chọn đáng phân biệt:**

| Option | Tác dụng |
| --- | --- |
| Không có `NESTMATE` | Hidden class mặc định nằm trong nest riêng của nó; cùng package/module **không có nghĩa** là được đọc thành viên `private` của lớp tạo nó. |
| `ClassOption.NESTMATE` | Đưa hidden class vào **cùng nest với lookup class**, cho phép các thành viên trong nest áp dụng quyền private theo quy tắc nestmate. |
| `ClassOption.STRONG` | Tạo quan hệ tồn tại mạnh với defining class loader như lớp thông thường; không có `STRONG`, hidden class có thể được thu hồi dù loader vẫn còn reachable nếu không có tham chiếu khác giữ nó. |

`STRONG` không cấp thêm quyền đọc thành viên private; `NESTMATE` không phải cờ “giữ lớp vĩnh viễn”. Khi một hidden class đang được dùng qua `Class` hoặc handle còn reachable, JVM vẫn phải giữ những đối tượng cần thiết. Không suy ra thời điểm GC hay unloading chính xác từ ví dụ.

## 5. Vì sao NESTMATE thay đổi quyền truy cập private?

Giả sử lớp chủ `HiddenLookupDemo` có phương thức:

~~~java
private static String secret() {
    return "ACCESS_GRANTED";
}
~~~

Nếu chỉ tạo hidden class từ `owner.defineHiddenClass(classBytes, true)`, ta thu được một `Lookup` có full privilege **đối với hidden class**. Điều đó **không mặc định** cho phép truy cập thành viên private của `HiddenLookupDemo` vì hai lớp chưa cùng nest. Lệnh dạng:

~~~java
isolated.findStatic(
        HiddenLookupDemo.class,
        "secret",
        MethodType.methodType(String.class));
~~~

sẽ bị từ chối bằng `IllegalAccessException`.

Ngược lại, tạo bằng `ClassOption.NESTMATE` rồi dùng `Lookup` trả về:

~~~java
MethodHandles.Lookup nestmate = owner.defineHiddenClass(
        classBytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);

MethodHandle readSecret = nestmate.findStatic(
        HiddenLookupDemo.class,
        "secret",
        MethodType.methodType(String.class));
~~~

sẽ cho phép tạo handle trong ví dụ vì hidden class đã là **nestmate** của lớp chủ, và lookup có các mode cần thiết. Điều này không có nghĩa “hidden class có thể tự truy cập private của mọi lớp trong module”; quyền truy cập được ràng buộc theo **nest**, quan hệ lớp và ngữ cảnh `Lookup`.

Ví dụ trên là **đoạn trích**; chương trình độc lập tiếp theo cho thấy cả trường hợp bị từ chối lẫn trường hợp được phép.

## 6. Ví dụ chạy độc lập trên Java 17+

Tạo file **`HiddenLookupDemo.java`** và lưu bằng UTF-8. File chứa cả lớp chủ và lớp mẫu tĩnh lồng bên trong; `javac` sinh `HiddenLookupDemo.class` cùng `HiddenLookupDemo$Template.class`. Chạy tại thư mục chứa các file `.class`.

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Objects;

public class HiddenLookupDemo {
    private static String secret() {
        return "ACCESS_GRANTED";
    }

    public static class Template {
        public static String greet(String person) {
            return "Hello " + person;
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] classBytes;
        try (InputStream in = Objects.requireNonNull(
                HiddenLookupDemo.class.getResourceAsStream("HiddenLookupDemo$Template.class"))) {
            classBytes = in.readAllBytes();
        }

        MethodHandles.Lookup owner = MethodHandles.lookup();
        MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
        MethodHandles.Lookup noPrivate = owner.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        System.out.println("ownerFull=" + owner.hasFullPrivilegeAccess());
        System.out.println("publicFull=" + publicOnly.hasFullPrivilegeAccess());

        try {
            publicOnly.defineHiddenClass(classBytes, false);
            System.out.println("publicDefine=UNEXPECTED");
        } catch (IllegalAccessException expected) {
            System.out.println("publicDefine=DENIED");
        }

        try {
            noPrivate.defineHiddenClass(classBytes, false);
            System.out.println("reducedDefine=UNEXPECTED");
        } catch (IllegalAccessException expected) {
            System.out.println("reducedDefine=DENIED");
        }

        MethodHandles.Lookup isolated = owner.defineHiddenClass(classBytes, true);
        Class<?> isolatedType = isolated.lookupClass();
        System.out.println("hidden=" + isolatedType.isHidden());
        System.out.println("sameModule=" + (isolatedType.getModule() == HiddenLookupDemo.class.getModule()));
        System.out.println("samePackage=" + (isolatedType.getPackageName().equals(HiddenLookupDemo.class.getPackageName())));
        System.out.println("isolatedFull=" + isolated.hasFullPrivilegeAccess());
        System.out.println("selfNest=" + (isolatedType.getNestHost() == isolatedType));
        MethodHandle greet = isolated.findStatic(
                isolatedType, "greet", MethodType.methodType(String.class, String.class));
        System.out.println("greet=" + (String) greet.invokeExact("An"));

        try {
            isolated.findStatic(HiddenLookupDemo.class, "secret",
                    MethodType.methodType(String.class));
            System.out.println("isolatedSecret=UNEXPECTED");
        } catch (IllegalAccessException expected) {
            System.out.println("isolatedSecret=DENIED");
        }

        try {
            Class.forName(isolatedType.getName());
            System.out.println("classForName=UNEXPECTED");
        } catch (ClassNotFoundException expected) {
            System.out.println("classForName=NOT_FOUND");
        }

        MethodHandles.Lookup nestmate = owner.defineHiddenClass(
                classBytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
        System.out.println("nestHost=" + (nestmate.lookupClass().getNestHost() == HiddenLookupDemo.class));
        MethodHandle readSecret = nestmate.findStatic(
                HiddenLookupDemo.class, "secret", MethodType.methodType(String.class));
        System.out.println("nestSecret=" + (String) readSecret.invokeExact());

        MethodHandles.Lookup privateOnTemplate =
                MethodHandles.privateLookupIn(Template.class, owner);
        System.out.println("privateLookupFull=" + privateOnTemplate.hasFullPrivilegeAccess());
        try {
            MethodHandles.privateLookupIn(Template.class, publicOnly);
            System.out.println("publicPrivateLookup=UNEXPECTED");
        } catch (IllegalAccessException expected) {
            System.out.println("publicPrivateLookup=DENIED");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 HiddenLookupDemo.java
java HiddenLookupDemo
~~~

**Stdout chính xác** khi chạy chương trình trên JDK hiện đại (đã biên dịch bằng `--release 17` và kiểm tra thực tế):

~~~text
ownerFull=true
publicFull=false
publicDefine=DENIED
reducedDefine=DENIED
hidden=true
sameModule=true
samePackage=true
isolatedFull=true
selfNest=true
greet=Hello An
isolatedSecret=DENIED
classForName=NOT_FOUND
nestHost=true
nestSecret=ACCESS_GRANTED
privateLookupFull=true
publicPrivateLookup=DENIED
~~~

Giải thích theo nhóm:

- `ownerFull=true`: lời gọi `MethodHandles.lookup()` diễn ra ngay bên trong lớp chủ, cung cấp một lookup có đủ đặc quyền.
- `publicDefine=DENIED` và `reducedDefine=DENIED`: dùng `publicLookup()` hay drop quyền `PRIVATE` đều không đủ cho `defineHiddenClass`.
- `hidden=true`, `sameModule=true`, `samePackage=true`: chứng minh lớp được sinh ra là hidden class trong ngữ cảnh package/module của lookup.
- `isolatedFull=true` không mâu thuẫn với `isolatedSecret=DENIED`: **full privilege của hidden class không tự biến nó thành nestmate của lớp chủ**.
- `greet=Hello An`: tra cứu và gọi phương thức `public static` của chính hidden class bằng `Lookup` được trả về.
- `classForName=NOT_FOUND`: hidden class không thể được tìm lại bằng binary name thông thường.
- `nestHost=true` và `nestSecret=ACCESS_GRANTED`: `NESTMATE` thiết lập đúng quan hệ truy cập private với lớp chủ.
- `privateLookupFull=true`: `privateLookupIn(Template.class, owner)` hợp lệ vì lớp mẫu cùng module và `owner` có quyền yêu cầu.
- `publicPrivateLookup=DENIED`: `publicLookup()` không thể tự nâng quyền thành private lookup.

Không in `hiddenClass.getName()` để so sánh tuyệt đối vì JVM tạo hậu tố định danh không ổn định. Mẫu dùng **boolean và chuỗi dự kiến** để kiểm thử có tính lặp lại.

## 7. privateLookupIn và kiểm tra truy cập giữa các module

`MethodHandles.privateLookupIn(Target.class, callerLookup)` cho phép chuyển ngữ cảnh private sang lớp đích **chỉ khi đáp ứng các điều kiện**:

1. `callerLookup` có đủ hai mode `PRIVATE` và `MODULE` (full privilege).
2. `Target` là một loại class hợp lệ cho API này (không phải primitive hay array).
3. Nếu hai lớp ở **cùng module**, có thể lấy lookup private trên `Target`, với ngữ cảnh mới phù hợp.
4. Nếu hai lớp thuộc **khác module**, module của caller phải **đọc** module đích, đồng thời module đích phải **`opens` package chứa lớp đích** cho module caller. Chỉ `exports` thông thường để truy cập public là chưa đủ cho deep reflection/private lookup.

Ví dụ **minh họa**, không phải mã chạy độc lập vì cần cấu hình module thực tế:

~~~java
MethodHandles.Lookup root = MethodHandles.lookup();
MethodHandles.Lookup target =
        MethodHandles.privateLookupIn(Target.class, root);
~~~

Nếu quyền/module không hợp lệ, lời gọi có thể ném `IllegalAccessException`. Nếu thành công với **target khác module**, lookup được trả về **không còn `MODULE` access**. Nó có thể có quyền private thích hợp để tra cứu thành viên đích nhưng **không đủ full privilege để tiếp tục gọi `defineHiddenClass`**. Hãy luôn kiểm tra điều kiện đầy đủ thay vì suy đoán từ việc truy cập được một thành viên private.

**Đừng nhầm `Lookup.in(Target.class)` với `privateLookupIn(Target.class, root)`:** `in` chỉ chuyển bối cảnh và có thể giảm quyền; nó không được sử dụng để leo thang đặc quyền private. Ngay cả `privateLookupIn` cũng bị hạn chế bởi cơ chế module readability/opens.

Trong ví dụ ở mục 6, các lớp đều thuộc cùng module không đặt tên (*unnamed module*), vì vậy `privateLookupIn(Template.class, owner)` thành công. Ví dụ đó **không chứng minh** một module tên riêng bất kỳ có thể mở quyền sang module khác.

## 8. Kiểm tra truy cập ở đâu, và lỗi nào cần phân biệt?

| Tình huống | Kết quả thông thường | Cách khắc phục |
| --- | --- | --- |
| `publicLookup().defineHiddenClass(bytes, false)` | `IllegalAccessException` | Cần lookup hợp lệ với full privilege từ ngữ cảnh đáng tin cậy. |
| `lookup.dropLookupMode(PRIVATE).defineHiddenClass(...)` | `IllegalAccessException` | Không có đủ private/module access. Không thể tự nâng quyền lại bằng `in(...)`. |
| Bytes là class file ở package khác với lookup class | `IllegalArgumentException` | Sinh/biên dịch class file ở đúng package theo thiết kế. |
| Bytes không phải class file hợp lệ | `ClassFormatError` hoặc lỗi liên kết/xác minh tùy nguyên nhân | Kiểm tra nguồn sinh bytes, phiên bản class file và bytecode. |
| `isolated.findStatic(host, "secret", ...)` khi không cùng nest | `IllegalAccessException` | Dùng `NESTMATE` nếu hợp đồng bảo mật cho phép và quan hệ nest là chủ đích. |
| `Class.forName(hiddenClass.getName())` | `ClassNotFoundException` | Giữ `Class<?>` hoặc `Lookup` trả về thay vì tìm hidden class bằng tên. |
| `privateLookupIn(target, publicLookup())` | `IllegalAccessException` | Không dùng public lookup để yêu cầu private; cần quyền và module opens hợp lệ. |
| Tạo MethodHandle sai tên hoặc chữ ký thành viên | `NoSuchMethodException` (với method), hoặc ngoại lệ tương ứng | Xác định đúng tên, static/instance và `MethodType`. |
| `initialize=true` và static initializer bị lỗi | Có thể có `ExceptionInInitializerError` | Không chạy khởi tạo của bytecode không tin cậy; kiểm thử tác dụng phụ. |

**Lỗi lúc tạo hidden class**, **lỗi lúc tạo MethodHandle**, **lỗi lúc gọi MethodHandle** là ba giai đoạn khác nhau. Ví dụ, handle `invokeExact` còn phải có kiểu tham số/kiểu trả về phù hợp; lỗi `WrongMethodTypeException` không phải là một lỗi thiếu `PRIVATE` của `Lookup`.

## 9. Bảo mật và thiết kế thực tế

- **Xem `Lookup` là capability:** `MethodHandles.lookup()` trả về quyền gắn với caller gốc; không phát tán nguyên trạng vào thư viện/plugin không tin cậy.
- **Không tùy tiện cấp `NESTMATE` cho class file nhận từ bên ngoài:** hidden class cùng nest có thể truy cập private member theo quy tắc JVM. Nếu dữ liệu bytecode đến từ nguồn không tin cậy, nó có thể khai thác quyền của nest khi được khởi tạo hoặc thực thi.
- **Không kỳ vọng hidden class là sandbox:** từ “hidden” nói về khả năng tìm bằng tên/linkage và vòng đời, **không phải** cơ chế cô lập an ninh.
- **Kiểm tra package/module/nguồn bytes:** class file cùng package và `Lookup` đầy đủ quyền mới được dùng đúng mục đích; thiếu một trong hai là lỗi.
- **Chọn rõ `initialize`:** để `true` chỉ khi muốn chủ động thực hiện class initializer; cân nhắc tác dụng phụ của `<clinit>`.
- **Giữ tham chiếu khi cần sống lâu:** nếu ứng dụng cần hidden class tồn tại theo vòng đời loader, đánh giá `STRONG` và chi phí bộ nhớ; không mặc định mọi hidden class đều được giữ mãi.
- **Ưu tiên API chính thức:** dùng `Lookup.defineHiddenClass` thay vì cách định nghĩa lớp vô danh bằng API nội bộ trước đây. Không cần `Unsafe` để thực hiện công việc này trên Java hiện đại.

### Quy trình tự rà soát trước khi viết framework

1. `Lookup` đến từ **lớp nào** và còn **những mode nào**? Kiểm tra `lookupClass()`, `lookupModes()` và `hasFullPrivilegeAccess()`.
2. Bytes có mô tả class file hợp lệ **cùng package** với lookup class không?
3. Framework có thật sự cần hidden class **cùng nest** để truy cập private, hay chỉ cần tạo lớp độc lập?
4. Khi sử dụng `privateLookupIn` qua module, đã thỏa **reads/opens** chưa và lookup được trả về còn `MODULE` không?
5. Mã có giữ đối tượng `Class<?>`/`MethodHandle` cần thiết mà không dựa vào `Class.forName` hoặc tên có hậu tố không ổn định không?
6. Lớp ẩn có cần khởi tạo ngay và có được phép xem bytecode đầu vào là tin cậy không?

## 10. Tài liệu chuẩn còn áp dụng

- [Java SE 26 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, truy cập theo ngữ cảnh, `lookupModes`, `hasFullPrivilegeAccess`, `ClassOption` và yêu cầu về module/package.
- [Java SE 26 — MethodHandles](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()` và `privateLookupIn(...)`.
- [Java SE 26 — Lookup.ClassOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): định nghĩa hiện hành của `NESTMATE` và `STRONG`.
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): đặc tả thiết kế đưa hidden class thành tính năng chính thức từ Java 15.

Kết luận: **`defineHiddenClass` kiểm tra năng lực của `Lookup`, không chỉ tính hợp lệ của bytecode**. Hidden class nhận đúng module/package và một ngữ cảnh `Lookup` riêng; quyền đọc private của lớp chủ chỉ xuất hiện khi có điều kiện truy cập và quan hệ nest phù hợp. Đây là quy tắc Java 15+ vẫn còn hiệu lực.