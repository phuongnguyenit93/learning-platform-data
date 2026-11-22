# Điều kiện truy cập của lớp cần khởi tạo trong Java

Khi Java chạy một ứng dụng có nhiều class hoặc một framework **sinh mã trong thời gian chạy**, đôi khi chương trình cần chủ động bảo đảm một class đã được khởi tạo **trước** khi sử dụng nó. Java 15 bổ sung phương thức **`MethodHandles.Lookup.ensureInitialized(Class<T>)`** cho mục đích này. Đây là API vẫn còn áp dụng trong Java hiện đại.

Điều kiện trọng tâm là: **class cần khởi tạo phải *accessible* đối với đối tượng `MethodHandles.Lookup` thực hiện lời gọi.** Có một tham chiếu `Class<?>` không đồng nghĩa với việc mọi lookup được phép khởi tạo class đó. Một lookup chỉ có quyền public không thể tùy ý khởi tạo class `private`, package-private hoặc class ở một module không export cho nó.

Bài học thuộc nhóm **Khởi tạo và sinh mã**, tập trung vào việc kiểm tra quyền class, phương thức `ensureInitialized`, điều kiện JVM/JPMS, các ngoại lệ và thực hành an toàn khi framework cần chủ động khởi tạo class được tạo hoặc nạp động.

## 1. Phân biệt load, link và initialize

Trước khi xét quyền truy cập, cần phân biệt ba giai đoạn của JVM:

1. **Loading (nạp):** tìm định nghĩa class và tạo cấu trúc biểu diễn `Class<?>` trong JVM.
2. **Linking (liên kết):** kiểm tra, chuẩn bị các cấu trúc cần thiết và giải quyết các symbolic reference theo quy định JVM.
3. **Initialization (khởi tạo):** thực thi phương thức khởi tạo của class/interface, ký hiệu **`<clinit>`** ở cấp bytecode; bước này bao gồm các static initializer và những phép khởi tạo static field cần được thực thi.

Ví dụ:

```java
class Configuration {
    static final String VERSION = "1"; // Hằng compile-time: lưu ý về inlining.
    static int loadedCount;

    static {
        loadedCount++;
        System.out.println("Configuration initialized");
    }
}
```

Việc lấy `Configuration.class` có thể tạo hoặc trả về một `Class<?>` mà **không chạy** static initializer. Trái lại, truy cập `Configuration.loadedCount` thường kích hoạt initialization nếu class chưa được khởi tạo.

**Đừng xem class loading và class initialization là một việc.** Một framework có thể có class token hoặc bytecode đã được load/link, nhưng phần khởi tạo static chưa chạy. Phương thức `ensureInitialized` cung cấp một cách tường minh để yêu cầu class đã khởi tạo theo quy tắc JVM, thay vì phải đọc một static field chỉ để tạo tác dụng phụ.

## 2. API trọng tâm của Java 15: Lookup.ensureInitialized

Chữ ký khái quát:

```java
public <T> Class<T> ensureInitialized(Class<T> targetClass)
        throws IllegalAccessException;
```

Đây là **chữ ký phương thức từ API**, không phải đoạn code tự chạy. Cách gọi:

```java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> initializedClass = lookup.ensureInitialized(SomeClass.class);
```

Ví dụ gọi chỉ hợp lệ nếu có `SomeClass` trong phạm vi của mã và lookup có quyền truy cập. Hành vi chính:

- **Nếu class chưa khởi tạo:** JVM thực hiện quá trình initialization theo **JVMS §5.5**.
- **Nếu class đã khởi tạo:** phương thức không chạy lại `<clinit>`.
- **Giá trị trả về:** chính đối tượng `Class<T>` tương ứng với class đích, **không** phải một instance mới của class.
- **Quyền truy cập:** `targetClass` phải accessible đối với lookup, tương đương việc kiểm tra class access do `lookup.accessClass(targetClass)` thực hiện.
- **Đồng bộ khởi tạo:** JVM điều phối initialization giữa các thread; một thread bình thường gọi khi thread khác đang khởi tạo sẽ tuân theo quy tắc chờ của JVMS. Nếu **chính thread hiện tại** đang khởi tạo class đó, phương thức có thể trả về trước khi tiến trình khởi tạo ấy kết thúc vì đó là một lời gọi đệ quy trong cùng thread.

`ensureInitialized` được bổ sung trong **Java 15** và không cần sử dụng API nội bộ của JDK. Với các chương trình Java 17+ hiện nay, có thể gọi trực tiếp.

**Nhấn mạnh:** `ensureInitialized` không tạo đối tượng bằng constructor, không tự tìm class theo chuỗi tên và không cho lookup quyền mới. Nó chỉ chủ động bảo đảm tiến trình khởi tạo của một **class đã được xác định** sau khi kiểm tra điều kiện truy cập.

## 3. Accessible nghĩa là gì trong trường hợp này?

`MethodHandles.Lookup` mang **lookup class** cùng các **lookup modes**. Đối tượng tạo bằng `MethodHandles.lookup()` có quyền theo lớp **thực sự gọi** phương thức ấy; khi bị chuyển cho code khác, nó vẫn mang ngữ cảnh quyền đã được ghi trong lookup.

Khi kiểm tra khả năng truy cập một target class, JVM xem xét:

- **Lookup class** và quan hệ giữa lookup class với target class.
- **Lookup modes**, ví dụ `PUBLIC`, `PACKAGE`, `PRIVATE`, `MODULE` hoặc `UNCONDITIONAL`.
- **Phạm vi package/runtime package, nest, module và class loader**, nơi chúng tác động đến quy tắc truy cập.
- **Java Platform Module System (JPMS):** quan hệ `reads` và `exports` giữa các module đối với class public ở module khác.
- **Previous lookup class**, nếu lookup là kết quả của một số phép chuyển đổi lookup qua ranh giới module; nó có thể khiến quyền bị giới hạn thêm.

Các trường hợp thực tế:

| Class đích | Lookup cần có gì? | Lưu ý |
| --- | --- | --- |
| Chính lookup class hoặc một lớp cùng nest | Lookup có quyền `PRIVATE` phù hợp, hoặc một con đường access khác hợp lệ | Các nested private class thường được truy cập qua quan hệ nest |
| Class package-private cùng runtime package | Quyền `PACKAGE` phù hợp | Có class token không có nghĩa public lookup được phép |
| Class public cùng module | Quyền hợp lệ, chẳng hạn `MODULE`, hoặc điều kiện public/export phù hợp | Quy tắc cụ thể còn tùy lookup modes |
| Class public trong module khác | Lookup cần quyền public phù hợp, quan hệ module-read và package được export cho phía truy cập | Chỉ public của class là chưa đủ nếu package không được export |
| Class thuộc package được export vô điều kiện | `MethodHandles.publicLookup()` có thể truy cập nếu target là public type phù hợp | Public lookup có mode `UNCONDITIONAL`, không phải full-privilege lookup |
| Class private nested mà code ngoài nest chỉ dùng public lookup | Thường **bị từ chối** | `IllegalAccessException`, kể cả khi phía gọi đã có `Class<?>` từ nơi khác |

Danh sách này là cách đọc **những trường hợp điển hình**; điều kiện chính xác được mô tả bởi `Lookup.accessClass(...)` trong Javadoc. Đặc biệt, đừng cố khái quát rằng `privateLookupIn(...)` luôn bắt buộc. Để **chủ động khởi tạo một class public accessible**, lookup chỉ cần quyền class access thích hợp; nó **không cần** quyền đọc private field hay gọi private method của class ấy.

## 4. accessClass kiểm tra quyền nhưng không chạy initializer

`MethodHandles.Lookup.accessClass(Class<?>)` xác định một class có accessible hay không đối với lookup và trả về class token nếu hợp lệ:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> checked = lookup.accessClass(Target.class);
```

Đây là đoạn **minh họa**, giả định có `Target` và import thích hợp. Khác biệt với `ensureInitialized`:

| API/thao tác | Kiểm tra class access | Tự yêu cầu chạy `<clinit>` nếu chưa chạy |
| --- | --- | --- |
| `Target.class` | Compile/link theo ngữ cảnh biểu thức | **Không** |
| `lookup.accessClass(Target.class)` | **Có** | **Không** |
| `lookup.ensureInitialized(Target.class)` | **Có** | **Có** |
| `new Target()` | Theo quy tắc ngôn ngữ/JVM | **Có**, trước khi instance constructor hoàn tất |
| Dùng một static method/field phù hợp | Theo quy tắc ngôn ngữ/JVM | Thường là tác nhân khởi tạo class |

Không nên dùng `Class.forName(...)` hoặc đọc static field như một cách “kiểm tra class access” thay cho `lookup.accessClass(...)`: chúng có mục đích và quy tắc riêng. Nếu muốn kiểm tra quyền mà không gây tác dụng phụ của khởi tạo, **`accessClass` là API đúng ngữ nghĩa**.

Ngay cả khi lookup không thể truy cập class, nếu một hệ thống khác đã khởi tạo class ấy thì điều đó **không cấp quyền cho lookup**. Quyền access và trạng thái initialized là hai điều kiện độc lập.

## 5. Ví dụ Java 17+ hoàn chỉnh: đủ quyền, thiếu quyền và class khởi tạo lỗi

Lưu toàn bộ mã thành **`ClassInitializationAccessDemo.java`**:

```java
import java.lang.invoke.MethodHandles;

public class ClassInitializationAccessDemo {
    private static class Target {
        static int counter;

        static {
            counter++;
            System.out.println("Target.<clinit>");
        }
    }

    private static class FailingTarget {
        static {
            System.out.println("FailingTarget.<clinit>");
            if ("boom".length() > 0) {
                throw new IllegalStateException("initializer error");
            }
        }
    }

    public static void main(String[] args) throws IllegalAccessException {
        MethodHandles.Lookup owner = MethodHandles.lookup();
        Class<?> token = Target.class;

        // Nhận Class token không làm chạy static initializer.
        System.out.println("classToken=" + token.getSimpleName());

        // Chỉ kiểm tra access: không khởi tạo Target.
        System.out.println("accessOnly=" + (owner.accessClass(token) == token));

        // Public lookup không được truy cập lớp private nested này.
        try {
            MethodHandles.publicLookup().ensureInitialized(Target.class);
            System.out.println("publicAccess=allowed");
        } catch (IllegalAccessException ex) {
            System.out.println("publicAccess=denied");
        }

        System.out.println("beforeEnsure");

        // Lookup của lớp ngoài có quyền truy cập private nestmate.
        Class<?> initialized = owner.ensureInitialized(Target.class);
        System.out.println("sameClass=" + (initialized == token));
        System.out.println("counter=" + Target.counter);

        // Khởi tạo thành công chỉ diễn ra một lần.
        owner.ensureInitialized(Target.class);
        System.out.println("counterAgain=" + Target.counter);

        // Không áp dụng API này cho primitive hoặc array class.
        try {
            owner.ensureInitialized(int.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("primitive=IllegalArgumentException");
        }

        try {
            owner.ensureInitialized(String[].class);
        } catch (IllegalArgumentException ex) {
            System.out.println("array=IllegalArgumentException");
        }

        // Lỗi trong static initializer được báo ra cho bên gọi.
        try {
            owner.ensureInitialized(FailingTarget.class);
        } catch (ExceptionInInitializerError ex) {
            System.out.println("failure=ExceptionInInitializerError");
        }
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 ClassInitializationAccessDemo.java
java ClassInitializationAccessDemo
```

Đầu ra **đã kiểm chứng bằng một JDK hiện đại**:

```text
classToken=Target
accessOnly=true
publicAccess=denied
beforeEnsure
Target.<clinit>
sameClass=true
counter=1
counterAgain=1
primitive=IllegalArgumentException
array=IllegalArgumentException
FailingTarget.<clinit>
failure=ExceptionInInitializerError
```

### Điều cần nhận ra từ output

1. `classToken=Target` và `accessOnly=true` xuất hiện **trước** `Target.<clinit>`. Class token và `accessClass` không tự kích hoạt static initializer.
2. `publicAccess=denied` chứng minh có `Target.class` **không vượt qua** được điều kiện access của một public lookup. Trong chương trình này `Target` là **private nested class**.
3. Lần đầu `owner.ensureInitialized(Target.class)` chạy static initializer, in `Target.<clinit>`, tăng bộ đếm từ 0 lên 1 và trả về chính class token.
4. Gọi lần thứ hai không chạy lại initializer: `counterAgain=1`.
5. `int.class` và `String[].class` bị từ chối bằng `IllegalArgumentException`; chúng không phải đối tượng hợp lệ để yêu cầu `ensureInitialized`.
6. `FailingTarget` chủ động ném `IllegalStateException` trong initializer. JVM báo `ExceptionInInitializerError` cho lời gọi khởi tạo thất bại.

Tất cả code chính đều nằm trong một file, không cần library ngoài và không cần cờ `--add-opens`. Chương trình chỉ tạo các class trong cùng một nest; không giả định có module hoặc database bên ngoài.

## 6. Những ngoại lệ và lỗi cần hiểu

`ensureInitialized` khai báo `throws IllegalAccessException`, nhưng còn có thể phát sinh runtime exception hoặc error do tính chất JVM:

| Tình huống | Hành vi điển hình | Cách xử lý |
| --- | --- | --- |
| `targetClass` không accessible với lookup | `IllegalAccessException` | Dùng lookup được phép truy cập, xem lại package/module thay vì cố vượt quyền |
| `targetClass` là primitive, `void` hoặc array | `IllegalArgumentException` | Chỉ truyền class/interface đích hợp lệ |
| `targetClass` bằng `null` | `NullPointerException` | Kiểm tra input/API contract |
| Static initializer ném một exception thông thường | `ExceptionInInitializerError` | Sửa logic initialization, phụ thuộc hoặc cấu hình thiếu |
| Class đã thất bại ở lần khởi tạo trước | Những lần sử dụng sau có thể gặp `NoClassDefFoundError` do trạng thái erroneous | Không tự retry lặp vô hạn; cần xử lý nguyên nhân gốc và vòng đời class loader |
| Lỗi liên kết/verification liên quan lớp được sinh hoặc phụ thuộc | Các `LinkageError` tương ứng | Kiểm tra class-file, class loader, API nhị phân và quyền truy cập |

**`IllegalAccessException` là checked exception** nên cần bắt hoặc khai báo; `ExceptionInInitializerError` và `NoClassDefFoundError` thuộc nhánh `Error`. Không nên dùng `catch (Throwable)` để che mọi lỗi JVM rồi tiếp tục như thể hệ thống đã khởi tạo thành công.

Nếu muốn logging, có thể ghi tên lớp, ngữ cảnh khởi tạo và lỗi gốc mà không làm lộ thông tin nhạy cảm; nhưng khi class initialization thực sự thất bại, cần coi đối tượng class đó là một trạng thái lỗi nghiêm trọng theo JVM, không phải một lỗi nhập liệu có thể sửa đơn giản.

## 7. Liên quan đến lookup modes, nest và Java module

### Quyền nestmate và lớp private

Một nested class có khai báo `private` không mặc nhiên “vô hình” với mọi lớp khác: lớp cùng **nest** có thể được cấp quyền truy cập private theo cơ chế JVM. Vì vậy, lời gọi `MethodHandles.lookup()` từ lớp ngoài trong ví dụ có quyền với nested `Target`.

Tuy nhiên, nếu thay lookup của chủ sở hữu bằng `MethodHandles.publicLookup()`, nested private target không còn accessible. Một lookup được tạo bằng `dropLookupMode(MethodHandles.Lookup.PRIVATE)` cũng không được mặc định là tương đương với public lookup: nó có thể còn mode `PACKAGE` hoặc `MODULE`, và quyết định access phải dựa trên **toàn bộ điều kiện class/mode**, không phải chỉ một bit.

### Module và exports

Trong chương trình modular, việc một class khai báo `public` không có nghĩa mọi module bên ngoài tự nhìn thấy nó. Với class public trong **module khác**, thông thường cần:

- Module của lookup **đọc được** module đích.
- Package chứa class được module đích **export** theo cách phù hợp với module gọi.
- Lookup có mode thích hợp để truy cập class ấy, kể cả những giới hạn từ previous lookup class nếu có.

Ví dụ mô-đun đích:

```java
module library.model {
    exports com.example.model.api;
}
```

Đoạn trên là nội dung minh họa của `module-info.java`; chỉ hợp lệ khi package/module đó tồn tại. Mục tiêu là export API public ra bên ngoài. Nếu `Product.class` là một public class trong package `com.example.model.api` và module caller có quan hệ read thích hợp, lookup từ caller có thể truy cập nó, rồi gọi `ensureInitialized(Product.class)` nếu điều kiện còn lại thỏa.

**Không nhầm `exports` với `opens`:** `opens` thường quan trọng với deep reflection, ví dụ khi dùng `MethodHandles.privateLookupIn(...)` sang module khác. Nhưng nếu mục đích chỉ là **khởi tạo một public class accessible**, không nên mở cả package cho deep reflection một cách không cần thiết. Mối quan hệ module access cho một lời gọi cụ thể cần được kiểm chứng theo Javadoc, chứ không nên xử lý mọi `IllegalAccessException` bằng `--add-opens`.

## 8. Với framework sinh mã và hidden class

Trong một framework, cần phân biệt **định nghĩa một class**, **nhận class token**, **kiểm tra access**, **khởi tạo class**, và **thực thi một phương thức của nó**.

Quy trình mức cao:

```text
Nhận / sinh bytecode hợp lệ
           |
           v
Tạo hoặc định nghĩa class bằng Lookup thích hợp
           |
           v
Nhận Class<?> của class vừa tạo
           |
           v
Kiểm tra access theo lookup định sử dụng
           |
           v
Chủ động ensureInitialized nếu cần hiệu ứng static initializer
           |
           v
Tạo instance / lấy MethodHandle / gọi API thực tế
```

Trường hợp hidden class (Java 15):

```java
MethodHandles.Lookup hiddenLookup =
        ownerLookup.defineHiddenClass(classFileBytes, false);

Class<?> hiddenType = hiddenLookup.lookupClass();
hiddenLookup.ensureInitialized(hiddenType);
```

Đây là **đoạn minh họa**, cần `ownerLookup` đủ đặc quyền và `classFileBytes` là bytecode hợp lệ thuộc đúng runtime package của lookup. Đoạn trên không tự chạy nếu thiếu bytecode và lookup. Nội dung:

- Tham số `initialize=false` yêu cầu **không khởi tạo ngay trong lúc định nghĩa hidden class**.
- `hiddenLookup.lookupClass()` nhận được token của class vừa định nghĩa.
- `hiddenLookup.ensureInitialized(hiddenType)` có thể chủ động kích hoạt initialization trong ngữ cảnh lookup có quyền truy cập lớp ẩn ấy.
- Nếu `defineHiddenClass(..., true, ...)`, lời gọi định nghĩa đã yêu cầu khởi tạo và không cần thêm một bước ensure riêng chỉ để đạt cùng mục tiêu.

Đối với class được định nghĩa bằng `Lookup.defineClass(byte[])`, phương thức này tạo và **liên kết** named class; ứng dụng có thể cần chủ động khởi tạo sau đó. Đừng mặc định việc có `Class<?>` trả về tức là static initializer đã chạy.

**Không trao full-privilege `Lookup` hoặc bytecode tùy ý cho mã không tin cậy.** Framework nên kiểm soát nguồn bytecode, quyền lookup và vòng đời class. Phép `ensureInitialized` có thể chạy code static initializer với side effects (đọc cấu hình, đăng ký service, tạo tài nguyên...); nó **không phải API kiểm tra an toàn hoặc sandbox** cho class sinh động.

### Mẫu sử dụng phù hợp

Một bộ sinh adapter nội bộ định nghĩa class rồi muốn bảo đảm việc đăng ký/cấu hình static diễn ra trước khi công bố adapter cho caller. Nếu class reachable qua lookup hợp lệ, framework có thể gọi `ensureInitialized` và xử lý lỗi một cách rõ ràng.

Ngược lại, nếu chỉ tạo một object bình thường bằng `new` hoặc gọi static method hợp lệ, JVM vốn đã biết khi nào cần khởi tạo class. Không cần gọi `ensureInitialized` ở mọi đường đi chỉ để “cho chắc”.

## 9. Phân biệt với các phương thức có tên gần giống

| API | Vai trò chính | Có tự yêu cầu initialization? |
| --- | --- | --- |
| `MethodHandles.lookup()` | Lấy lookup mang quyền của lớp gọi | Không |
| `lookup.accessClass(C.class)` | Kiểm tra class accessible đối với lookup | Không |
| `lookup.ensureInitialized(C.class)` | Bảo đảm khởi tạo class accessible | **Có** nếu class chưa khởi tạo |
| `lookup.findClass("a.b.C")` | Tìm class từ tên theo ngữ cảnh lookup và kiểm tra access | Không có nghĩa là đã chạy static initializer |
| `lookup.defineClass(bytes)` | Định nghĩa và link named class từ bytecode | Không tự bảo đảm đã khởi tạo |
| `lookup.defineHiddenClass(bytes, true, options)` | Định nghĩa hidden class và yêu cầu khởi tạo | **Có** khi `initialize=true` |
| `Class.forName(name)` | Tìm/nạp class theo tên và cách thức của overload được dùng | Overload mặc định yêu cầu khởi tạo; overload có boolean cho phép lựa chọn |

Có class token và truy cập class là hai vấn đề khác nhau: việc dùng một overload `Class.forName(name, false, loader)` có thể load class nhưng không init; còn `ensureInitialized` chuyên biệt cho việc yêu cầu init **với kiểm tra access của lookup**.

Trong Java hiện đại, nên ưu tiên các API công khai của `java.lang.invoke` và cơ chế JVM được đặc tả, tránh dùng những API JDK nội bộ để ép khởi tạo class.

## 10. Các sai lầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Có `Target.class` tức là target đã khởi tạo | `Class<?>` không tự kích hoạt `<clinit>` |
| `ensureInitialized` chỉ cần class token, không kiểm tra access | Target **phải accessible** với lookup; nếu không ném `IllegalAccessException` |
| `publicLookup()` khởi tạo được mọi class mà code giữ token | Chỉ class public accessible theo rules của public lookup |
| Lookup không được truy cập private field thì không init được class public | Kiểm tra **class accessibility** khác với truy cập private member |
| `accessClass` và `ensureInitialized` tương đương | Cái trước chỉ kiểm tra access, cái sau có thể chạy `<clinit>` |
| `int.class` và `String[].class` có static initialization như class thường | `ensureInitialized` từ chối primitive, `void` và array |
| Static initializer sẽ chạy mỗi lần gọi `ensureInitialized` | JVM chỉ khởi tạo thành công một lần trên mỗi class identity |
| Có thể retry vô hạn nếu static initializer ném lỗi | Class có thể rơi vào trạng thái erroneous, về sau gặp `NoClassDefFoundError` |
| Class public ở module khác luôn accessible | Còn phụ thuộc `reads`, `exports`, lookup modes và module context |
| Cần `--add-opens` cho mọi lần ensureInitialized | Chỉ cần **class access** hợp lệ, không nhất thiết deep reflection |
| `defineClass` và `defineHiddenClass(..., false)` tự chạy initializer | Phải xem rõ thời điểm initialization và tùy chọn `initialize` |
| Có thể khởi tạo bytecode tùy ý an toàn nhờ hidden class | Initialization thực thi code; hidden class không phải sandbox |

## 11. Bài tập và đáp án

**Bài 1.** Mã có `private static class Secret` trong lớp `Host`. Một lookup do `Host` tạo có đủ quyền; một lookup từ `MethodHandles.publicLookup()` được truyền cùng `Secret.class`. Ai có khả năng gọi `ensureInitialized(Secret.class)`?

**Bài 2.** Một framework đã nhận `Class<?>` của một public class nằm trong module khác, nhưng package không được export cho module của lookup. Dùng `lookup.ensureInitialized(token)` có tự vượt qua JPMS không?

**Bài 3.** Một class có static block in ra “READY”. Chương trình gọi `lookup.accessClass(C.class)` rồi `lookup.ensureInitialized(C.class)` hai lần. Bao nhiêu lần static block được chạy nếu class chưa từng khởi tạo và lookup có quyền?

**Bài 4.** Một framework gọi `defineHiddenClass(bytes, false)` để định nghĩa lớp ẩn. Khởi tạo class đã được yêu cầu chưa?

**Bài 5.** Nếu initializer của class lần đầu ném `IllegalStateException`, lời gọi `ensureInitialized` thường sẽ nhìn thấy gì? Có nên tiếp tục retry mãi không?

**Đáp án:**

1. Lookup do `Host` tạo có thể truy cập private nestmate theo quyền của nó; public lookup thường nhận `IllegalAccessException` với class đích private.
2. Không. Giữ token không thay đổi quy tắc **class accessibility** và quan hệ module.
3. **Một lần** khi `ensureInitialized` đầu tiên thực sự gây initialization; `accessClass` không chạy initializer và ensure tiếp theo không chạy lại.
4. Chưa; `initialize=false` không yêu cầu chạy static initializer ngay. Cần một trigger hợp lệ sau đó, ví dụ `hiddenLookup.ensureInitialized(hiddenType)`.
5. Thường là `ExceptionInInitializerError` khi exception phát sinh trong `<clinit>`. Class có thể vào trạng thái erroneous; phải sửa lỗi phụ thuộc/logic thay vì retry vô hạn.

## Tài liệu chính thức, hiện còn áp dụng

- [Oracle Java SE 25 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `ensureInitialized(...)`, `accessClass(...)`, lookup modes, module access và `defineHiddenClass(...)`.
- [Oracle Java SE 25 — MethodHandles](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()` và `privateLookupIn(...)`.
- [Java Virtual Machine Specification SE 25, §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5): các quy tắc thời điểm và đồng bộ khởi tạo.
- [Oracle Java SE 15 — Lookup.ensureInitialized (từ Java 15)](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): mốc giới thiệu API và điều kiện access ban đầu.