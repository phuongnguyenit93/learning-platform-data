# Ghi ngữ cảnh lớp, class loader, module và chữ ký khi điều tra lỗi reflection

## 1. Vì sao thông báo ngoại lệ đơn lẻ chưa đủ?

Khi một thao tác reflection thất bại, chỉ ghi `exception.getMessage()` thường chưa giải thích được nguyên nhân. Cùng tên lớp có thể được nạp bởi hai `ClassLoader` khác nhau; cùng tên phương thức nhưng khác tham số là hai chữ ký khác nhau; một thành viên tồn tại nhưng bị giới hạn truy cập bởi Java Platform Module System (JPMS). Vì vậy, điều tra hiệu quả phải đặt ngoại lệ trong **ngữ cảnh chính xác của đối tượng `Class`, loader, module, thành viên và hành động đã thử**.

Các tình huống điển hình:

- `ClassNotFoundException` khi tải lớp bằng tên nhưng loader được chọn không nhìn thấy lớp.
- `NoSuchMethodException` vì tra sai kiểu tham số, nhầm primitive với wrapper, chỉ tìm declared method hay quên class cha.
- `IllegalAccessException` hoặc `InaccessibleObjectException` vì quyền truy cập Java/module không đáp ứng thao tác reflection.
- `IllegalArgumentException` khi gọi `Method.invoke` với receiver/đối số không phù hợp.
- `InvocationTargetException`: chính phương thức đích ném ngoại lệ; cần xem `getCause()` hoặc `getTargetException()`.
- `ClassCastException` có thể xuất hiện dù hai lớp được hiển thị **cùng tên**, nếu chúng khác danh tính do class loader.
- `NoSuchMethodError` hoặc các lỗi linkage khác xảy ra ở giai đoạn liên kết mã đã biên dịch với runtime, **khác** `NoSuchMethodException` khi tra reflection.

Mục tiêu của log điều tra là trả lời: *đang kiểm tra lớp nào, do loader nào định nghĩa, nằm trong module nào, cần chữ ký nào, thực tế tìm thấy gì, thất bại ở bước nào và nguyên nhân gốc là gì?*

## 2. Bộ thông tin nên ghi cho mỗi lần điều tra

| Nhóm | Dữ liệu nên thu thập | Công dụng |
| --- | --- | --- |
| Hoạt động | `operation`: `loadClass`, `getDeclaredMethod`, `invoke`, `trySetAccessible`… | Phân biệt lỗi tra cứu, quyền truy cập và lỗi trong phần thân |
| Định danh lớp | `Class.getName()`, `getTypeName()`, `getPackageName()` | Phát hiện nhầm package, tên binary, kiểu mảng, lớp lồng |
| Loader | `Class.getClassLoader()`; loại loader và ID tạm trong tiến trình | Phát hiện cùng tên nhưng khác defining loader |
| Module | `Class.getModule()`, `getName()`, `isNamed()`; package của thành viên | Phân tích module/class path và JPMS |
| Thành viên | `getDeclaringClass()`, tên, kiểu tham số, kiểu trả về, modifiers | Xác minh chữ ký và quyền truy cập |
| Chữ ký | `Method.toGenericString()`, `getParameterTypes()`, kiểu trả về; khi cần JVM descriptor | Phân biệt overload, erasure, bridge method |
| Chủ thể gọi | Class/module của code đang reflection; receiver class thực tế | Truy cập phụ thuộc cả caller lẫn target |
| Ngoại lệ | Loại lỗi, thông báo, cause chain, stack trace, target exception | Truy đến bước và nguyên nhân gốc |
| Môi trường | Runtime Java, cơ chế triển khai, phiên bản artifact/class path/module path | Tái hiện khác biệt giữa máy/phiên bản |

**Ghi cả *expected* và *actual*.** Ví dụ: lookup cần `format(int)` nhưng hệ thống truyền `Integer.class`; chỉ log tên `format` sẽ bỏ lỡ sự khác biệt. Trong hệ thống nhiều plugin, so sánh thêm đối tượng `Class` và class loader, không chỉ so tên.

## 3. Phân biệt tên lớp và danh tính lớp

`Class.getName()` trả tên nhị phân, nên lớp lồng thường có ký tự `$` (ví dụ `Outer$Inner`). Với mảng, `getName()` sử dụng dạng JVM như `[Ljava.lang.String;`; `getTypeName()` dễ đọc hơn như `java.lang.String[]`. `getCanonicalName()` có thể trả `null` với kiểu local hoặc anonymous: không nên dựa vào nó làm khóa bắt buộc.

Đối với một class Java thông thường, danh tính runtime gắn với **tên nhị phân và class loader định nghĩa**. Hai loader khác nhau có thể định nghĩa hai lớp cùng tên mà JVM vẫn xem là hai kiểu khác nhau.

```java
// Giả sử first và second đã được lấy từ hai hệ thống plugin:
boolean sameName = first.getName().equals(second.getName());
boolean sameClass = first == second;
boolean sameDefiningLoader =
        first.getClassLoader() == second.getClassLoader();
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Nếu `sameName == true` nhưng `sameClass == false`, cần kiểm tra loader, module, đường nạp class và bản build/JAR.

`Class.getClassLoader() == null` thường đại diện lớp do **bootstrap class loader** định nghĩa; đây không có nghĩa là thông tin lỗi bị thiếu. `ClassLoader.getClass().getName()` chỉ cho biết *loại loader*, chưa đủ phân biệt hai instance cùng loại. Khi cần liên hệ sự kiện **trong một JVM**, có thể ghi thêm `System.identityHashCode(loader)` cùng tên loại loader, nhưng giá trị này không phải mã định danh toàn cục, không bảo đảm duy nhất và không ổn định qua lần khởi động.

Không suy ra rằng loader mà code **yêu cầu** nạp lớp luôn là loader **định nghĩa** lớp cuối cùng: cơ chế parent delegation có thể chuyển việc nạp cho parent. Ghi `targetClass.getClassLoader()` để biết loader định nghĩa; có thể ghi riêng loader được sử dụng ở lệnh tra cứu.

## 4. Module và quyền truy cập reflection (Java 9+)

Mỗi `Class` thuộc một `Module`: `type.getModule()`. Nếu `module.isNamed() == false`, module đó là **unnamed module**, thường gặp khi chạy Java bằng class path. `module.getName()` khi đó trả `null`; nên hiển thị nhãn rõ ràng như `<unnamed>`.

Với **named module**:

- `exports p` công khai các **public** type/member trong package `p` cho module được phép đọc và truy cập.
- `opens p` cho phép **deep reflection** vào package `p` đối với module nhận quyền (bên cạnh các điều kiện truy cập khác).
- `Module.isExported(p, callerModule)` và `Module.isOpen(p, callerModule)` giúp xem một package có được export/open đến module gọi hay không.
- `setAccessible(true)` không thể tùy ý vượt qua giới hạn JPMS; có thể ném `InaccessibleObjectException`.
- `trySetAccessible()` trả `false` nếu không thể mở quyền truy cập (nhưng có thể ném `SecurityException` nếu bị từ chối bởi kiểm tra bảo mật). **Lưu ý: thao tác này có thể thay đổi accessible flag khi thành công**, nên không dùng chỉ để đọc trạng thái trên đối tượng `Method` đang được chia sẻ.

Muốn kiểm tra *khả năng truy cập theo caller* với một `Method`/`Field` mà không đổi flag, dùng `canAccess(receiver)` khi cung cấp receiver hợp lệ: instance method/field dùng instance thích hợp, static member hoặc constructor dùng `null`. Không dùng `canAccess(null)` với instance member.

Khi có `InaccessibleObjectException`, log **module đích + package + module gọi + thao tác đang thử**, sau đó xem cấu hình `module-info.java` và quan hệ `exports`/`opens`. Chỉ dùng cấu hình `--add-opens module/package=targetModule` như giải pháp có kiểm soát khi hiểu rõ ranh giới quyền; không áp dụng mở rộng bừa bãi trên môi trường sản xuất.

Xem đặc biệt sự khác nhau giữa **tìm thấy metadata** và **được phép truy cập**: `getDeclaredMethod` có thể tìm thấy phương thức private, nhưng `invoke` vẫn có thể bị từ chối nếu chưa có quyền hợp lệ.

## 5. Ghi chính xác chữ ký, kể cả overload và generics

Với `java.lang.reflect.Method`:

- `getName()`: tên phương thức.
- `getDeclaringClass()`: class/interface **khai báo** thành viên; có thể khác runtime class của receiver.
- `getParameterTypes()` và `getReturnType()`: chữ ký sau erasure ở runtime.
- `getGenericParameterTypes()`, `getGenericReturnType()` và `toGenericString()`: thông tin generic còn được lưu ở metadata.
- `getModifiers()` với `Modifier.toString(...)`; `isBridge()`, `isSynthetic()`, `isVarArgs()`: hữu ích khi compiler sinh bridge/synthetic method hoặc thao tác biến tham số.
- `getExceptionTypes()`: danh sách các exception được khai báo, khác với exception thực tế đã ném.

`Class.getDeclaredMethod(name, parameterTypes...)` tra phương thức **khai báo trực tiếp** trong class; `Class.getMethod(...)` tra phương thức **public** có thể truy cập qua quy tắc kế thừa/public members. Khi truyền tham số tra cứu, dùng **chính xác** `Class` của từng tham số: `int.class != Integer.class`. Thứ tự cũng phải trùng; return type không nằm trong danh sách tham số của `getDeclaredMethod`, mặc dù một `Method` có thể báo return type.

Một generic method khai báo `<T extends Number> T echo(T item)` có kiểu tham số runtime là `Number.class`, vì erasure. Việc tra `echo(Integer.class)` sẽ không tìm thấy nó. Nếu cần phân tích generic arguments và type variables, đọc `getGenericParameterTypes()` song song với kiểu runtime.

Với `MethodHandle`, chữ ký lời gọi có thể bao gồm receiver đứng đầu, ngay cả khi chữ ký phương thức Java không biểu diễn receiver thành một tham số rõ ràng. Khi điều tra handle, ghi `handle.type()`; với `VarHandle`, ghi `accessModeType(mode)`. Không đánh đồng `MethodHandle.type()` với kết quả chỉ lấy từ `Method.getParameterTypes()`.

Một biểu diễn JVM descriptor có thể được tạo từ kiểu trả về và tham số (sau erasure):

```java
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

// Đoạn minh họa; giả sử đã có Method method:
String descriptor = MethodType.methodType(
        method.getReturnType(), method.getParameterTypes())
        .toMethodDescriptorString();
```

Ví dụ `String format(int)` cho descriptor `(I)Ljava/lang/String;`. Descriptor thuận tiện để đối chiếu bytecode, nhưng **không thay thế** tên phương thức, declaring class và loader/module.

## 6. Ví dụ Java 17+ chạy độc lập: chụp ngữ cảnh và khoanh vùng lỗi

Lưu file `ReflectionInvestigationDemo.java`:

```java
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class ReflectionInvestigationDemo {
    static final class Sample {
        private final String code;

        Sample(String code) {
            this.code = code;
        }

        public String format(int revision) {
            return code + "-" + revision;
        }

        public <T extends Number> T echo(T value) {
            return value;
        }
    }

    static void describe(String tag, Class<?> type) {
        ClassLoader loader = type.getClassLoader();
        Module module = type.getModule();
        String moduleName = module.isNamed()
                ? module.getName() : "<unnamed>";
        String packageName = type.getPackageName().isEmpty()
                ? "<default>" : type.getPackageName();

        System.out.println(tag + ".class=" + type.getName());
        System.out.println(tag + ".loader=" +
                (loader == null ? "bootstrap" : "non-bootstrap"));
        System.out.println(tag + ".module=" + moduleName);
        System.out.println(tag + ".package=" + packageName);
    }

    public static void main(String[] args) throws Exception {
        describe("target", Sample.class);
        describe("jdk", String.class);

        Method m = Sample.class.getDeclaredMethod("format", int.class);
        System.out.println("method=" + m.getName());
        System.out.println("declaring=" +
                m.getDeclaringClass().getName());
        System.out.println("parameters=" +
                Arrays.toString(m.getParameterTypes()));
        System.out.println("return=" + m.getReturnType().getTypeName());
        System.out.println("descriptor=" +
                MethodType.methodType(
                        m.getReturnType(), m.getParameterTypes())
                        .toMethodDescriptorString());
        System.out.println("public=" +
                Modifier.isPublic(m.getModifiers()));
        System.out.println("bridge=" + m.isBridge());

        Method generic = Sample.class.getDeclaredMethod(
                "echo", Number.class);
        System.out.println("erased=" +
                Arrays.toString(generic.getParameterTypes()));
        System.out.println("generic=" +
                Arrays.toString(generic.getGenericParameterTypes()));

        try {
            Sample.class.getDeclaredMethod("format", Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup.failure=" +
                    e.getClass().getSimpleName());
            System.out.println("requested.parameter=Integer");
        }

        Sample instance = new Sample("A");
        try {
            m.invoke(instance, "2");
        } catch (IllegalArgumentException e) {
            System.out.println("invoke.failure=" +
                    e.getClass().getSimpleName());
        }

        System.out.println("result=" + m.invoke(instance, 2));
    }
}
```

Biên dịch và chạy trên class path từ thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 ReflectionInvestigationDemo.java
java ReflectionInvestigationDemo
```

Stdout mong đợi:

```text
target.class=ReflectionInvestigationDemo$Sample
target.loader=non-bootstrap
target.module=<unnamed>
target.package=<default>
jdk.class=java.lang.String
jdk.loader=bootstrap
jdk.module=java.base
jdk.package=java.lang
method=format
declaring=ReflectionInvestigationDemo$Sample
parameters=[int]
return=java.lang.String
descriptor=(I)Ljava/lang/String;
public=true
bridge=false
erased=[class java.lang.Number]
generic=[T]
lookup.failure=NoSuchMethodException
requested.parameter=Integer
invoke.failure=IllegalArgumentException
result=A-2
```

Điểm học được:

1. `Sample.class` là class do application (hoặc loader khác không phải bootstrap) nạp và ở unnamed module khi chạy bằng class path; `String.class` ở `java.base` và do bootstrap loader định nghĩa.
2. Tên nhị phân của nested class chứa `$`; việc chỉ dùng tên hiển thị đơn giản `Sample` sẽ đánh mất ngữ cảnh.
3. Tra `format(int.class)` thành công, tra `format(Integer.class)` thất bại vì primitive `int` khác wrapper `Integer`.
4. Generic `echo(T)` có tham số runtime `Number` trong khi `getGenericParameterTypes()` còn trả type variable `T`.
5. `Method.invoke(instance, "2")` thất bại vì tham số `String` không thể chuyển thành `int` theo quy tắc cho phép của invocation; sử dụng đối số kiểu `int` mới thành công.
6. Chữ ký và descriptor xác nhận chính xác phương thức đang gọi. Ví dụ chỉ ghi loại lỗi tại các nhánh đã biết nên không đưa thông tin nhạy cảm vào stdout.

Trong môi trường module path hoặc loader tùy biến, vài dòng module/loader có thể khác; ví dụ dùng class path để có đầu ra xác định.

## 7. Khi ngoại lệ phát sinh: chụp cả cause chain và điểm thất bại

Với `Method.invoke`, lỗi *bên trong thân phương thức đích* thường bị gói vào `InvocationTargetException`. Lỗi **trước khi thực thi thân** như receiver/arguments sai hoặc thiếu quyền truy cập lại thuộc nhóm khác. Tách hai nhánh khi điều tra:

```java
// Đoạn minh họa đặt trong phương thức có Method method,
// Object receiver và Object[] arguments hợp lệ:
try {
    method.invoke(receiver, arguments);
} catch (java.lang.reflect.InvocationTargetException e) {
    Throwable root = e.getTargetException();
    // Ghi loại lỗi + stack/cause chain theo chính sách ứng dụng.
    // Không vô tình bỏ qua ngoại lệ gốc.
    System.err.println("target threw: " +
            root.getClass().getName());
} catch (IllegalAccessException e) {
    System.err.println("reflection access denied: " +
            e.getClass().getName());
} catch (IllegalArgumentException e) {
    System.err.println("bad receiver/arguments: " +
            e.getClass().getName());
}
```

Đây **không phải chương trình độc lập**. Khi viết helper phục vụ production, nên log structured fields (`operation`, `targetClass`, `loader`, `module`, `methodSignature`, `exceptionType`, `causeType`) và giữ stack trace gốc thông qua logger. Tránh chỉ gọi `getCause().getCause()` không kiểm tra null vì cause chain có thể ngắn hơn dự kiến. Cũng cần tránh vòng lặp khi tự duyệt chain với Throwable bất thường; ưu tiên logging framework đã quản lý stack trace.

### Nhận diện nhanh theo ngoại lệ

| Ngoại lệ/lỗi | Câu hỏi ưu tiên |
| --- | --- |
| `ClassNotFoundException` | Tên binary đúng chưa? Loader yêu cầu nạp là gì? Class path/module path có dependency đó không? |
| `NoSuchMethodException` | Đúng overload, kiểu tham số, thứ tự, primitive/wrapper, erasure và `getDeclaredMethod`/`getMethod` chưa? |
| `IllegalAccessException` | Caller, visibility, module readability/exports hoặc điều kiện access checks có phù hợp không? |
| `InaccessibleObjectException` | Có đang cố bật deep reflection mà package/module không mở quyền không? |
| `IllegalArgumentException` khi `Method.invoke` | Receiver có đúng declaring class? Đối số có đúng số lượng/kiểu và varargs chưa? |
| `InvocationTargetException` | Exception gốc của thân phương thức là gì? Dòng stack phía ứng dụng nào gây ra? |
| `ClassCastException` | Hai class thật sự bằng nhau qua `==` không? Defining loader và module khác nhau không? |
| `NoSuchMethodError` / `LinkageError` | Có sự khác biệt bytecode/binary giữa bản compile và runtime, xung đột dependency hoặc loader constraint không? |

**Phân biệt:** `NoSuchMethodException` là checked exception của API tra cứu reflection; `NoSuchMethodError` thuộc `LinkageError`, thường phản ánh mismatch liên kết binary. Cách điều tra không thể chỉ dựa vào cùng cụm chữ "NoSuchMethod".

## 8. Ghi log đủ dùng nhưng không làm phát sinh lỗi mới

Để có log chẩn đoán đáng tin:

- **Không gọi `toString()` tùy ý trên receiver/argument của người dùng**: phương thức có thể tốn thời gian, truy cập dữ liệu riêng tư, ném ngoại lệ hoặc có tác dụng phụ. Ghi loại của giá trị khi cần (`obj == null ? "<null>" : obj.getClass().getName()`).
- Không log token, mật khẩu, payload request, object graph, stack của dữ liệu nhạy cảm hoặc đường dẫn nội bộ quá chi tiết ở kênh công khai. Phân mức log và giới hạn quyền truy cập.
- Lấy **định danh loader tương đối trong một tiến trình**, cùng module và package để so sánh; không coi identity hash là ID ổn định qua restart.
- Ghi rõ **chữ ký đã yêu cầu** và **chữ ký thực tế** nếu tìm được. Đối với overload, thiếu một tham số hoặc sai thứ tự đều có ý nghĩa.
- Xác định vị trí lỗi: tra lớp → tra thành viên → kiểm tra quyền → chuyển đổi đối số → thực thi phương thức → chuyển kiểu kết quả. Bước khác nhau cho cùng tên ngoại lệ sẽ cần cách xử lý khác nhau.
- Nếu dùng `Thread.currentThread().getContextClassLoader()` để tìm plugin/resource, ghi cả context loader và loader định nghĩa class được trả về. Hai loader không bắt buộc giống nhau.
- Với lỗi xảy ra trong luồng đa tiến trình, đính kèm trace/correlation ID từ ứng dụng để kết nối các sự kiện; log một lần tại ranh giới được quản lý, tránh đổ trùng stack trace nhiều tầng.
- Không mặc định thêm `--add-opens` hoặc bật `setAccessible(true)` chỉ để làm biến mất lỗi; trước tiên xác định module/package và vì sao thao tác cần quyền truy cập đó.

### Mẫu dữ liệu log có cấu trúc (minh họa)

```text
event=reflection_lookup_failed
operation=getDeclaredMethod
targetClass=com.example.plugins.PaymentAdapter
targetModule=<unnamed>
targetLoaderKind=PluginClassLoader
requestedMethod=calculate(java.math.BigDecimal,int):java.math.BigDecimal
exceptionType=java.lang.NoSuchMethodException
correlationId=<id-cua-ung-dung>
```

Đây là **mẫu minh họa cấu trúc**, không phải output của chương trình Java phía trên; `PluginClassLoader`/`PaymentAdapter`/`correlationId` chỉ là giá trị ví dụ. Không tự giả định chi tiết loader, module hay chữ ký như các sự kiện đã đo được.

## 9. Quy trình kiểm tra nhanh trong thực tế

1. Ghi `operation`, loại exception và cause/stack trace gốc.
2. Xác định tên binary và `Class<?>` **thực tế** của target/receiver/argument.
3. Ghi defining loader (xử lý giá trị `null` của bootstrap) và module/package cho cả target lẫn caller khi cần.
4. Đối chiếu chữ ký yêu cầu và metadata trả về: overload, runtime erasure, primitive/wrapper, receiver, bridge/synthetic.
5. Phân biệt *không tìm thấy*, *không được phép*, *đối số sai* và *thân phương thức ném ngoại lệ*.
6. So artifact/JAR, dependency, class path/module path và cấu hình opens/exports khi lỗi chỉ xuất hiện ở một môi trường.
7. Sửa đúng nguyên nhân, tái hiện bằng test hoặc đoạn Java nhỏ cùng phiên bản JDK và loader/module setup tương ứng.

## 10. Tự kiểm tra

**Câu 1.** Hai `Class` có cùng `getName()` luôn là cùng một kiểu không?

**Đáp án:** Không. Nếu chúng do hai defining class loader khác nhau định nghĩa, có thể là hai kiểu khác nhau; so trực tiếp `first == second` và kiểm tra loader.

**Câu 2.** Vì sao `getDeclaredMethod("run", Integer.class)` có thể thất bại khi source khai báo `run(int)`?

**Đáp án:** Reflection so kiểu tham số chính xác ở runtime; `Integer.class` khác `int.class`.

**Câu 3.** `getDeclaredMethod` trả về `Method` nhưng `invoke` vẫn ném `IllegalAccessException`. Mâu thuẫn không?

**Đáp án:** Không. Tra được metadata chưa đồng nghĩa với được phép gọi; cần kiểm tra visibility, caller và quy tắc module.

**Câu 4.** Trong `InvocationTargetException` cần xem ngoại lệ nào để biết code đích hỏng?

**Đáp án:** Xem `getTargetException()` (hoặc `getCause()`) cùng stack trace của ngoại lệ gốc.

**Câu 5.** Khi class ở unnamed module, `getModule().getName()` có giá trị gì?

**Đáp án:** `null`. Ghi nhãn `<unnamed>` hoặc `isNamed() == false` để tránh hiểu sai.

**Ghi nhớ:** Lỗi reflection cần được điều tra theo bộ **class + defining loader + module/package + declaring member + chữ ký runtime + caller/receiver + exception/cause**. Thiếu một trong các yếu tố đó có thể khiến hai trường hợp khác nguyên nhân trông giống nhau trong log.

Tham khảo API Java 17: [`Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), [`AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html), [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).