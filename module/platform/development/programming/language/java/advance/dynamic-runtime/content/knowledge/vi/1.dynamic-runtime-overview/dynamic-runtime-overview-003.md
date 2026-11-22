# 1.3 Quan hệ giữa khám phá siêu dữ liệu, tìm thành phần, liên kết và thực thi

**Module:** Java Advance - dynamic-runtime  
**Nhóm kiến thức:** 1. Tổng quan

Một hệ thống Java có khả năng mở rộng lúc chạy thường không gọi trực tiếp mọi lớp triển khai từ mã nguồn. Thay vào đó, hệ thống nhận một mô tả, tìm lớp hoặc nhà cung cấp phù hợp, kiểm tra cách kết nối với hợp đồng chung, rồi mới kích hoạt hành vi. Bốn khái niệm **khám phá siêu dữ liệu → tìm thành phần → liên kết → thực thi** mô tả các trách nhiệm trong quá trình đó.

Điểm quan trọng: đây là **bốn trách nhiệm logic**, không phải cam kết rằng JVM luôn chạy bốn bước độc lập, theo đúng một thứ tự thời gian. Ví dụ, muốn đọc annotation runtime của một lớp bằng Reflection thì trước hết cần có đối tượng `Class<?>` đại diện cho lớp đó; còn `ServiceLoader` có thể trì hoãn việc tìm và khởi tạo provider đến lúc duyệt.

## 1. Mỗi giai đoạn trả lời câu hỏi gì?

| Giai đoạn | Câu hỏi chính | Đầu vào tiêu biểu | Kết quả cần có |
| --- | --- | --- | --- |
| **Khám phá siêu dữ liệu (metadata discovery)** | Thành phần nào *được khai báo* và cần điều kiện gì? | Annotation, cấu hình, service descriptor, module descriptor, registry | Danh sách mô tả/ứng viên cùng ID, hợp đồng, phiên bản, quyền hoặc thuộc tính |
| **Tìm thành phần (component discovery)** | Mã triển khai thực sự nằm ở đâu và có truy cập được không? | Tên lớp, classpath/module path, `ClassLoader`, `ServiceLoader` | `Class<?>`, provider, đối tượng hoặc factory tương ứng với mô tả |
| **Liên kết (linking/binding)** | Ứng viên có phù hợp hợp đồng và có thể nối với điểm gọi không? | Kiểu, chữ ký phương thức, quyền truy cập, dependency | Tham chiếu phương thức, `MethodHandle`, factory/adapter hoặc điểm gọi hợp lệ |
| **Thực thi (execution)** | Khi truyền đầu vào, thành phần thực hiện công việc và trả kết quả gì? | Đối tượng/call site đã sẵn sàng, tham số, ngữ cảnh | Kết quả, thay đổi trạng thái, sự kiện hoặc ngoại lệ khi chạy |

Ví dụ một ứng dụng cần thao tác `upper`:

1. Registry khai báo `id=upper` và tên lớp thực hiện: **đọc thông tin khai báo**.
2. Hệ thống tải/tìm đúng lớp ở đúng class loader: **xác định thành phần**.
3. Xác nhận lớp triển khai giao diện `Action`, tìm phương thức `run(String)` và quyền gọi: **liên kết với hợp đồng**.
4. Khởi tạo đối tượng nếu cần, truyền `"java 17"` và nhận `"JAVA 17"`: **thực thi**.

**Metadata không tự bảo đảm mã tồn tại.** Có tên lớp trong cấu hình nhưng JAR vắng mặt thì chưa thể tìm thành phần. Tìm được lớp cũng chưa bảo đảm tương thích API. Liên kết thành công cũng không bảo đảm logic nghiệp vụ sẽ chạy thành công.

## 2. Phân biệt hai nghĩa của “liên kết” trong Java

### 2.1. JVM linkage: liên kết lớp và ký hiệu bytecode

Khi biên dịch, Java ghi các tham chiếu ký hiệu (tên lớp, field, phương thức, chữ ký) vào class file. Theo JVM Specification, một lớp thường trải qua:

- **Loading:** tìm biểu diễn nhị phân của lớp và tạo kiểu ở runtime qua class loader.
- **Linking:** gồm **verification** (kiểm tra tính hợp lệ), **preparation** (chuẩn bị static fields với giá trị mặc định), và **resolution** (giải các tham chiếu ký hiệu thành thực thể runtime).
- **Initialization:** chạy mã khởi tạo lớp, bao gồm static initializer và gán giá trị static theo chương trình.

**Loading, linking và initialization khác nhau.** JVM có quyền lựa chọn thời điểm thực hiện một số công việc resolution, nên không được khẳng định mọi tham chiếu đều giải xong ngay sau lúc tải lớp. Chương trình có thể gặp `LinkageError` khi một hành động đòi hỏi giải tham chiếu không hợp lệ.

Lời gọi `Class.forName(name, false, loader)` trong ví dụ bên dưới yêu cầu tìm lớp mà không chủ động khởi tạo lớp đó. Ngược lại, dạng `Class.forName(name)` thông thường yêu cầu khởi tạo lớp. Việc tạo instance hoặc dùng một số thành viên static có thể kích hoạt initialization theo quy tắc JVM.

### 2.2. Application binding: ghép thành phần với hợp đồng động

Ở mức ứng dụng, “liên kết” còn là việc lựa chọn một implementation cho một extension point, chẳng hạn:

- kiểm tra `Action.class.isAssignableFrom(candidate)`;
- lấy constructor, method hoặc method handle đúng tên/chữ ký;
- kiểm tra khả năng truy cập trong package/module;
- tạo adapter hoặc đăng ký handler để các lời gọi sau định tuyến vào đúng implementation.

Đây là **quy trình do framework/ứng dụng thiết kế**; nó liên quan đến quy tắc JVM nhưng không phải một pha JVM linkage độc lập có tên “plugin binding”. Nếu gọi qua interface, JVM vẫn thực hiện dispatch đến implementation của đối tượng tại điểm gọi.

`MethodHandles.Lookup.findVirtual` tạo handle sau khi kiểm tra khả năng truy cập và kiểu phương thức. `MethodHandle.invokeExact` yêu cầu chữ ký phía lời gọi khớp chính xác với kiểu của handle; sai kiểu có thể gây `WrongMethodTypeException`.

### 2.3. `invokedynamic` nằm ở đâu?

`invokedynamic` là một dạng điểm gọi trong bytecode: khi cần liên kết điểm gọi, JVM dùng **bootstrap method** để tạo `CallSite` có target phù hợp. Các lần gọi sử dụng target của call site theo ngữ nghĩa của loại call site đó. Cơ chế này hỗ trợ các kiểu liên kết động ở mức bytecode (ví dụ hạ tầng lambda), nhưng **không đồng nghĩa** với việc quét JAR, đọc registry hoặc tìm plugin bằng `ServiceLoader`. Những việc đó là chính sách khám phá ở tầng cao hơn.

## 3. Siêu dữ liệu dẫn đường, bộ tải và hợp đồng quyết định khả năng thực thi

| Nguồn metadata | Mô tả được gì? | Điều cần xác minh thêm |
| --- | --- | --- |
| Annotation với `@Retention(RUNTIME)` | Vai trò, ID hoặc cấu hình gắn trên lớp/phương thức | Phải có cách tìm lớp cần kiểm tra; annotation không tự liệt kê toàn bộ classpath |
| `META-INF/services/<tên-giao-diện>` | Tên binary của các provider trên classpath | Provider có mặt, hợp lệ và có thể khởi tạo theo quy ước `ServiceLoader` |
| `module-info.java` với `uses`/`provides` | Dịch vụ được tiêu thụ/cung cấp trong hệ module | Module được resolve trong layer thích hợp; quyền đọc/xuất/mở package đủ dùng |
| Cấu hình/registry/manifest | ID, tên lớp, version, điều kiện bật/tắt | Artifact đang chạy thực sự chứa implementation và dependency cần thiết |
| Reflection trên `Class<?>` | Annotation, method, constructor, interface ở runtime | Quyền truy cập, kiểu, chữ ký và trạng thái khởi tạo vẫn phải kiểm tra |

Không có API chuẩn nào mặc định “quét toàn bộ ứng dụng rồi tìm mọi class có annotation” cho mọi kiểu deployment Java. Framework thường xây chỉ mục, đọc cấu hình, quét một phạm vi do nó sở hữu hoặc dùng discovery protocol riêng.

**Class loader là một phần của danh tính kiểu:** hai lớp có cùng binary name nhưng được *defining class loader* khác nhau định nghĩa là hai kiểu runtime khác nhau. Vì thế, plugin có thể “tìm thấy class” nhưng ép sang giao diện của host vẫn thất bại nếu nó mang một bản sao `Action` được load bởi loader khác. Trong hệ module (JPMS), `exports`/`opens` và quyền đọc module cũng chi phối việc truy cập, đặc biệt với deep reflection.

Bản thân `ServiceLoader` kết hợp nhiều trách nhiệm: đọc khai báo service, tìm provider, rồi cung cấp/khởi tạo chúng một cách có thể trì hoãn. Khi chia pipeline thành bốn giai đoạn để thiết kế và quan sát, cần nhận ra một API có thể đảm nhiệm nhiều giai đoạn.

## 4. Ví dụ Java 17+: đi từ metadata đến lời gọi thực tế

Ví dụ dùng một tên lớp đã đăng ký sẵn để mô phỏng registry; annotation quyết định ứng viên có đúng ID hay không; `Class` và interface kiểm tra component; `MethodHandle` liên kết lời gọi; cuối cùng chương trình tạo đối tượng và chạy. Tất cả nằm trong **một file chạy độc lập**, không cần thư viện ngoài.

**Tệp: `DynamicPipelineDemo.java`**

~~~java
import java.lang.annotation.*;
import java.lang.invoke.*;
import java.util.Locale;

public class DynamicPipelineDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Plugin { String id(); }

    public interface Action {
        String run(String input);
    }

    @Plugin(id = "upper")
    public static class UpperAction implements Action {
        @Override
        public String run(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws Throwable {
        // 1. Registry/config cung cấp một ứng viên (không quét classpath).
        String declaredName = "DynamicPipelineDemo$UpperAction";
        ClassLoader loader = DynamicPipelineDemo.class.getClassLoader();
        Class<?> candidate = Class.forName(declaredName, false, loader);

        // 2. Đọc metadata và kiểm tra đúng ID được yêu cầu.
        Plugin metadata = candidate.getAnnotation(Plugin.class);
        if (metadata == null || !"upper".equals(metadata.id())) {
            throw new IllegalStateException("Plugin metadata mismatch");
        }
        System.out.println("metadata=" + metadata.id());

        // 3. Xác nhận component tuân theo hợp đồng của host.
        if (!Action.class.isAssignableFrom(candidate)) {
            throw new IllegalStateException("Not an Action");
        }
        Class<? extends Action> type = candidate.asSubclass(Action.class);
        System.out.println("component=" + type.getSimpleName());

        // 4. Liên kết phương thức cần gọi, theo chữ ký của interface.
        MethodHandle call = MethodHandles.lookup().findVirtual(
                Action.class, "run",
                MethodType.methodType(String.class, String.class));
        System.out.println("binding=" + call.type());

        // 5. Khởi tạo và thực thi sau khi đã kiểm tra/ghép hợp đồng.
        Action action = type.getDeclaredConstructor().newInstance();
        String output = (String) call.invokeExact(action, "java 17");
        System.out.println("output=" + output);
    }
}
~~~

Biên dịch và chạy (JDK 17 trở lên):

~~~bash
javac --release 17 DynamicPipelineDemo.java
java DynamicPipelineDemo
~~~

Kết quả chuẩn:

~~~text
metadata=upper
component=UpperAction
binding=(Action,String)String
output=JAVA 17
~~~

**Vì sao ví dụ thể hiện đúng quan hệ?**

- `declaredName` là **đầu mối discovery**, được giả định đến từ registry. Không có chức năng tự quét annotation để tìm ứng viên.
- `Class.forName(..., false, loader)` cung cấp kiểu runtime để đọc annotation; vì vậy phần đọc metadata **xảy ra sau khi đã tìm được `Class`** trong ví dụ này. “Khám phá metadata” là trách nhiệm, không nhất thiết là sự kiện đầu tiên của JVM.
- `getAnnotation` xác minh ý nghĩa metadata; `isAssignableFrom` kiểm tra hợp đồng, còn `asSubclass` cung cấp kiểu an toàn hơn cho bước tạo instance.
- `findVirtual` tạo handle mang kiểu `(Action, String) -> String`; `invokeExact` thực thi trên đối tượng `UpperAction`. Trong thực tế có thể dùng lời gọi interface trực tiếp hoặc Reflection thay cho method handle.
- `getDeclaredConstructor().newInstance()` tạo đối tượng; ở thiết kế thật, thời điểm tạo và phạm vi dùng lại đối tượng cần được xác định riêng. Ví dụ này dùng constructor có thể truy cập trong cùng lớp/nhóm lớp, nên không cần bật truy cập Reflection trái phép.

Thử thay `"upper"` trong annotation bằng `"lower"`: chương trình dừng ở bước kiểm tra metadata, trước khi tạo đối tượng hoặc gọi `run`. Thử để `UpperAction` không triển khai `Action` (và bỏ `@Override`): chương trình dừng ở bước kiểm tra hợp đồng. Hai lỗi minh họa việc **được tìm thấy không có nghĩa là có thể liên kết và thực thi**.

## 5. Khi thay registry bằng `ServiceLoader`

Nếu ứng dụng cung cấp một giao diện SPI, mỗi provider có thể được khai báo qua file `META-INF/services/<binary-name-của-SPI>` (khi dùng classpath), hoặc `uses`/`provides` trong module descriptor (khi dùng JPMS). Ví dụ, SPI tên `com.example.spi.Action` thì đường dẫn khai báo classpath là:

~~~text
META-INF/services/com.example.spi.Action
~~~

Nội dung file là tên lớp provider đầy đủ, mỗi tên trên một dòng, ví dụ:

~~~text
com.example.impl.UpperAction
~~~

Sau khi đóng gói SPI, implementation và metadata đúng cách, mã **minh họa trong ứng dụng có SPI `Action`** có thể dùng:

~~~java
ServiceLoader<Action> providers = ServiceLoader.load(Action.class);
for (Action provider : providers) {
    System.out.println(provider.run("java 17"));
}
~~~

Đoạn này **không phải chương trình độc lập** và không dùng nguyên tên lớp lồng trong ví dụ một file ở mục 4. Nó đòi hỏi dự án có SPI/provider tương ứng và service descriptor hợp lệ.

`ServiceLoader.load` tạo service loader; quá trình tìm và khởi tạo provider thường diễn ra khi duyệt nó, nên lỗi cấu hình có thể lộ ra muộn hơn lúc gọi `load`. Nếu cần quan sát metadata của provider trước khi tạo instance, có thể xem API `ServiceLoader.stream()` và `Provider.type()`, nhưng vẫn phải tuân theo quy tắc tìm/đọc provider của API.

Trong cả hai cách làm, **hợp đồng chung** quan trọng hơn tên implementation: host nên biết `Action`, registry hoặc discovery mới biết `UpperAction`. Điều này cho phép thêm implementation mà không sửa mọi chỗ gọi.

## 6. Lỗi xảy ra ở đâu và chẩn đoán thế nào?

| Triệu chứng | Giai đoạn nghi vấn | Hướng kiểm tra |
| --- | --- | --- |
| Không có entry hoặc ID không khớp | Metadata discovery | Tên service, annotation retention, cấu hình, filter hoặc version |
| `ClassNotFoundException`, `ServiceConfigurationError` | Component discovery/provider setup | Tên binary, artifact trên classpath/module path, loader/layer, khai báo provider |
| `NoClassDefFoundError`, `NoSuchMethodError`, `IncompatibleClassChangeError` | Load/link runtime, tương thích nhị phân | Dependency bị thiếu, API/ABI không khớp giữa lúc compile và lúc chạy |
| `IllegalAccessException`, `InaccessibleObjectException` hoặc `IllegalAccessError` | Truy cập/liên kết | Modifier, module readability, `exports`/`opens`, đúng `Lookup` |
| `NoSuchMethodException` hoặc `WrongMethodTypeException` | Tìm phương thức/binding | Tên, tham số, return type; chữ ký chính xác của `invokeExact` |
| `ExceptionInInitializerError` hoặc exception từ logic provider | Khởi tạo/thực thi | Static initializer, constructor, dữ liệu đầu vào và stack trace gốc |

Một lỗi có thể xuất hiện *khi thực hiện hành động đầu tiên đòi hỏi pha đó*, không nhất thiết ngay tại thời điểm lập registry. Với Reflection, `Method.invoke` có thể bọc ngoại lệ từ phương thức đích trong `InvocationTargetException`; với method handle, ngoại lệ của target được truyền theo cơ chế của lời gọi handle.

Để debug có hệ thống, ghi dấu các mốc **metadata read → candidate resolved → contract checked → method bound → instance created → invoked**, kèm ID provider, tên lớp, class loader, module/layer và nguyên nhân ngoại lệ. Không ghi dữ liệu nhạy cảm từ input hoặc classpath ngoài nhu cầu chẩn đoán.

## 7. Nguyên tắc thiết kế một pipeline dynamic runtime đáng tin

1. **Định nghĩa contract trước:** giao diện/SPI, đầu vào-đầu ra, vòng đời, điều kiện phiên bản và chính sách lỗi phải rõ. Một provider có metadata đẹp nhưng không thỏa contract vẫn phải bị từ chối.
2. **Tách phát hiện khỏi kích hoạt nếu có thể:** chỉ tạo instance khi cần; không khởi chạy mọi plugin chỉ để liệt kê. Nhận thức rằng một số API thực hiện nhiều việc trong một lời gọi.
3. **Chọn đúng phạm vi tìm kiếm:** classpath, module layer, class loader, registry; tránh giả định mọi provider trên máy sẽ được JVM tìm tự động.
4. **Ràng buộc kiểu và quyền truy cập:** xác minh `isAssignableFrom`, chữ ký method, module access; tránh ép kiểu mù quáng hoặc bật `setAccessible(true)` cho mọi thứ.
5. **Quản lý vòng đời và cache:** metadata, `Class`, handle, instance có chi phí và ngữ nghĩa khác nhau. Cache phải gắn với đúng loader/layer và phải có chính sách làm mới khi thay artifact; đừng cache một instance không thread-safe như singleton nếu contract không cho phép.
6. **Giữ ranh giới tin cậy:** tải mã từ nguồn ngoài có thể thực thi code ở initialization, constructor hoặc method. `ClassLoader` **không tự tạo sandbox bảo mật**. Chỉ nạp provider được kiểm soát/kiểm chứng trong cùng tiến trình, hoặc cô lập bằng tiến trình/quyền hệ điều hành khi cần.
7. **Đo từng pha trước khi tối ưu:** hạn chế quét lặp, dùng discovery cache hợp lý, tạo/bind handle một lần nếu thích hợp. Không kết luận Reflection, interface dispatch hay `MethodHandle` luôn nhanh hơn chỉ từ tên cơ chế; cần đo workload thực tế.

## 8. Các nhầm lẫn thường gặp

- **“Có annotation thì plugin tự được tìm thấy.”** Không đúng; cần một cơ chế duyệt tên lớp, registry hoặc chỉ mục trước khi kiểm tra annotation.
- **“Load class là đã chạy plugin.”** Không đúng; loading khác initialization, tạo object và gọi method. Tuy vậy code initialization vẫn có thể gây side effect khi được kích hoạt.
- **“Liên kết ở framework chính là JVM linking.”** Hai lớp trách nhiệm liên quan nhau nhưng khác phạm vi.
- **“`Class.forName(name)` chỉ đọc metadata.”** Dạng overload này yêu cầu khởi tạo lớp; dùng overload có tham số `initialize=false` khi muốn tránh chủ động khởi tạo.
- **“Trùng tên lớp là trùng kiểu.”** Sai khi defining class loader khác nhau.
- **“Tìm provider thành công thì chạy chắc chắn thành công.”** Provider có thể thiếu dependency, vi phạm chữ ký, không truy cập được, lỗi constructor hoặc lỗi nghiệp vụ.

## 9. Tự kiểm tra tư duy

**Tình huống A:** File `META-INF/services` có đúng tên provider nhưng ứng dụng báo `ServiceConfigurationError` lúc duyệt. Hãy kiểm tra metadata định danh, loader/module, khả năng tải provider, contract và quy tắc khởi tạo thay vì chỉ kiểm tra tên file.

**Tình huống B:** Registry tìm được `com.example.UpperAction` nhưng `Action.class.isAssignableFrom(candidate)` trả `false` dù mã nguồn ghi `implements Action`. Hãy kiểm tra liệu host và plugin có định nghĩa hai bản sao `Action` bằng các defining class loader khác nhau hay không.

**Tình huống C:** Lấy được `MethodHandle` nhưng `invokeExact` ném `WrongMethodTypeException`. Hãy đối chiếu `handle.type()` với **kiểu tĩnh của từng đối số và kiểu trả về ở call site**; `invokeExact` không thực hiện chuyển đổi kiểu linh hoạt như `invoke`.

Một cách nhớ đúng: **metadata mô tả khả năng; discovery tìm hiện thân runtime; binding xác lập hợp đồng/điểm gọi; execution tạo ra hành vi quan sát được.** Các bước phụ thuộc lẫn nhau, có thể xen kẽ hoặc diễn ra muộn, và lỗi ở bước nào phải được chẩn đoán theo trách nhiệm bước đó.

## Tài liệu đối chiếu

- [JVM Specification, Java SE 17 — Chapter 5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java SE 17 API — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 API — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 17 API — MethodHandle và MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
