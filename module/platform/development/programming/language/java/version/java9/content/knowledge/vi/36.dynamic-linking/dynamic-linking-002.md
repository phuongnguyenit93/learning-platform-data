# DynamicLinkerFactory và cấu hình bộ liên kết trong Dynalink

**DynamicLinkerFactory** thuộc module **jdk.dynalink**, được đưa vào JDK từ Java 9. Factory tạo ra **DynamicLinker**, thành phần điều phối việc liên kết các call site động với những bộ liên kết (GuardingDynamicLinker) có thể xử lý từng loại đối tượng hoặc ngôn ngữ.

Factory cho phép cấu hình thứ tự ưu tiên của linker, tự phát hiện linker qua ServiceLoader, đặt fallback linker, chọn class loader và điều chỉnh cách call site được liên kết lại. Đây là hạ tầng dành cho runtime ngôn ngữ, engine biểu thức hoặc hệ thống dùng invokedynamic; nó không phải một API reflection tổng quát để thay thế mọi lời gọi Java thông thường.

## 1. Dynalink giải quyết vấn đề gì?

Một ngôn ngữ động có thể cho phép cùng một biểu thức truy cập thuộc tính hoặc gọi phương thức trên nhiều kiểu đối tượng khác nhau. Kiểu thực tế chỉ được biết khi chương trình chạy.

Ví dụ, biểu thức truy cập thuộc tính name có thể nhận một đối tượng Person, một đối tượng JavaBean khác hoặc một object thuộc mô hình dữ liệu riêng của ngôn ngữ. Runtime cần xác định cách thực hiện thao tác cho từng kiểu receiver.

Dynalink cung cấp một lớp điều phối cho việc đó:

1. Runtime mô tả thao tác bằng một CallSiteDescriptor.
2. DynamicLinker nhận call site và điều phối việc tìm linker phù hợp.
3. Mỗi GuardingDynamicLinker có cơ hội cung cấp một GuardedInvocation.
4. GuardedInvocation chứa MethodHandle thực hiện thao tác và có thể kèm guard để xác nhận receiver còn phù hợp.
5. Call site lưu invocation đã liên kết; khi guard không còn đúng, call site yêu cầu linker liên kết lại.

Cơ chế này cho phép một call site được tái sử dụng với nhiều receiver, đồng thời có thể thay target khi kiểu đối tượng thực tế thay đổi.

## 2. Những thành phần chính

| Thành phần | Vai trò |
|---|---|
| DynamicLinkerFactory | Nhận cấu hình và tạo DynamicLinker |
| DynamicLinker | Điều phối việc liên kết RelinkableCallSite với MethodHandle |
| GuardingDynamicLinker | Thử xử lý một LinkRequest và trả GuardedInvocation nếu phù hợp |
| GuardedInvocation | Gói MethodHandle thực thi cùng guard, SwitchPoint hoặc điều kiện vô hiệu hóa tùy chọn |
| LinkerServices | Hỗ trợ chuyển đổi kiểu, tìm linker tiếp theo và lọc đối tượng nội bộ |
| CallSiteDescriptor | Mô tả Lookup, Operation và MethodType của call site |
| RelinkableCallSite | Call site có thể được DynamicLinker liên kết lại |
| SimpleRelinkableCallSite | Call site có monomorphic inline cache |
| ChainedCallSite | Call site có polymorphic inline cache, giữ chuỗi các invocation còn hợp lệ |
| BeansLinker | Linker có sẵn để xử lý các đối tượng Java thông thường theo mô hình JavaBeans |

Một GuardingDynamicLinker thường không tự xử lý mọi kiểu đối tượng. Nếu không hỗ trợ request, nó trả về null để DynamicLinker tiếp tục hỏi linker tiếp theo.

## 3. Tạo DynamicLinkerFactory và DynamicLinker

Cách sử dụng cơ bản:

~~~java
DynamicLinkerFactory factory = new DynamicLinkerFactory();
DynamicLinker dynamicLinker = factory.createLinker();
~~~

Factory mới được tạo với cấu hình mặc định. Có thể gọi các phương thức setXxx() để điều chỉnh cấu hình trước khi gọi createLinker().

createLinker() tạo một DynamicLinker từ cấu hình hiện tại. Có thể gọi nhiều lần để tạo nhiều DynamicLinker; mỗi lần tạo sẽ thực hiện lại quá trình tự phát hiện linker.

Factory không thread-safe. Hãy hoàn tất việc cấu hình trước khi chia sẻ kết quả hoặc gọi createLinker() từ nhiều luồng. Tránh thay đổi cấu hình đồng thời với quá trình tạo linker.

## 4. Thứ tự ưu tiên của các linker

Một DynamicLinker thông thường phối hợp ba nhóm linker theo thứ tự:

1. **Prioritized linkers:** những linker được runtime đăng ký tường minh bằng setPrioritizedLinker() hoặc setPrioritizedLinkers(). Chúng được hỏi trước.
2. **Automatically discovered linkers:** các linker được tìm qua ServiceLoader bằng GuardingDynamicLinkerExporter.
3. **Fallback linkers:** những linker được đăng ký bằng setFallbackLinkers(). Chúng được hỏi sau cùng.

Factory bỏ qua linker tự phát hiện nếu class của linker đó đã được đăng ký tường minh trong nhóm prioritized hoặc fallback. Như vậy, runtime có thể thay thế một implementation được tự phát hiện bằng instance do chính nó quản lý.

Có thể đặt một linker ưu tiên:

~~~java
factory.setPrioritizedLinker(languageLinker);
~~~

Hoặc đăng ký nhiều linker:

~~~java
factory.setPrioritizedLinkers(
        firstLanguageLinker,
        secondLanguageLinker
);
~~~

Thứ tự trong danh sách là thứ tự được sử dụng khi thử các linker ưu tiên. Các linker nên trả null nhanh khi không nhận diện được operation hoặc receiver mà chúng hỗ trợ.

## 5. Cấu hình fallback và BeansLinker

**BeansLinker** là linker có sẵn để xử lý các đối tượng Java thông thường. Nó hỗ trợ các thao tác theo namespace property, method và element dựa trên quy tắc của Dynalink.

Có thể chỉ định BeansLinker làm fallback tường minh:

~~~java
factory.setFallbackLinkers(new BeansLinker());
~~~

Ý nghĩa của các trường hợp cấu hình:

| Cấu hình fallback | Hành vi |
|---|---|
| Không gọi setFallbackLinkers() | Factory tạo BeansLinker làm fallback mặc định |
| Truyền null | Dùng fallback mặc định BeansLinker |
| Truyền một hoặc nhiều linker | Dùng các linker được cung cấp theo thứ tự |
| Truyền danh sách rỗng hoặc mảng rỗng | Không đăng ký fallback linker nào |

Khi runtime có linker riêng cho object model của ngôn ngữ, thường đặt linker đó ở nhóm prioritized và giữ BeansLinker ở cuối để xử lý Java object khi cần.

Không nên vô tình truyền danh sách rỗng nếu vẫn cần khả năng truy cập property hoặc method của JavaBean thông thường.

## 6. Tự phát hiện linker bằng ServiceLoader

Dynalink hỗ trợ nạp linker được cung cấp bởi runtime khác thông qua **GuardingDynamicLinkerExporter** và cơ chế **ServiceLoader**.

Có thể chọn class loader dùng để tìm provider:

~~~java
factory.setClassLoader(
        Thread.currentThread().getContextClassLoader());
~~~

Các quy tắc:

- Nếu không gọi setClassLoader(), factory dùng thread context class loader của thread gọi createLinker().
- Nếu truyền một class loader cụ thể, ServiceLoader dùng class loader đó để tìm exporter.
- Nếu gọi setClassLoader(null), factory dùng ServiceLoader.loadInstalled() để tìm provider được cài đặt cho môi trường runtime.

Một exporter cung cấp danh sách GuardingDynamicLinker. Các linker này được thêm vào nhóm tự phát hiện, sau nhóm prioritized và trước nhóm fallback.

Sau khi createLinker(), có thể kiểm tra lỗi nạp provider:

~~~java
List<ServiceConfigurationError> errors =
        factory.getAutoLoadingErrors();
~~~

Các lỗi tự phát hiện không được ném trực tiếp từ createLinker(). Factory cố gắng tiếp tục bằng cách bỏ qua provider bị lỗi và lưu các ServiceConfigurationError để ứng dụng kiểm tra.

Nếu ứng dụng đóng gói runtime bằng jlink, cần bảo đảm module và các provider cần thiết được đưa vào runtime image.

## 7. Các tùy chọn cấu hình quan trọng

| Phương thức | Ý nghĩa | Khi nên dùng |
|---|---|---|
| setClassLoader() | Chọn class loader cho ServiceLoader | Khi runtime có nhiều class loader hoặc cần kiểm soát plugin discovery |
| setPrioritizedLinker(s) | Đặt linker được hỏi trước | Khi có object model hoặc ngôn ngữ riêng |
| setFallbackLinkers() | Đặt linker được hỏi cuối | Khi muốn thay đổi hoặc giới hạn fallback mặc định |
| setSyncOnRelink(boolean) | Gọi MutableCallSite.syncAll() sau khi relink | Nên bật khi runtime chạy code liên kết động trên nhiều thread |
| setUnstableRelinkThreshold(int) | Số lần relink trước khi call site được đánh dấu unstable | Khi muốn điều chỉnh cách linker xử lý call site đổi receiver thường xuyên |
| setPrelinkTransformer() | Chỉnh GuardedInvocation cuối cùng trước khi cài vào call site | Khi cần tùy biến nâng cao việc chuyển đổi hoặc deoptimization |
| setAutoConversionStrategy() | Tùy biến conversion sau custom language conversion | Khi ngôn ngữ có quy tắc chuyển đổi khác Java method invocation conversion |
| setInternalObjectsFilter() | Lọc MethodHandle để object nội bộ không thoát khỏi runtime | Khi runtime quản lý object nội bộ cần được bảo vệ |

### Đồng bộ khi relink

~~~java
factory.setSyncOnRelink(true);
~~~

Mặc định giá trị là false. Khi bật, DynamicLinker gọi MutableCallSite.syncAll() sau khi call site được relink. Tài liệu API khuyến nghị cân nhắc bật tùy chọn này nếu runtime hỗ trợ thực thi code liên kết động đa luồng.

### Ngưỡng call site không ổn định

~~~java
factory.setUnstableRelinkThreshold(8);
~~~

Mặc định là 8. Giá trị phải không âm; giá trị 0 có nghĩa call site không bao giờ bị đánh dấu unstable. Sau khi vượt ngưỡng, LinkRequest.isCallSiteUnstable() có thể cho linker biết call site đang thay đổi target thường xuyên.

Một linker có thể dùng thông tin này để chọn chiến lược liên kết phù hợp hơn với call site có nhiều kiểu receiver.

### Các hook nâng cao

setPrelinkTransformer() cho phép biến đổi GuardedInvocation sau khi linker thành phần tạo ra nó và trước khi DynamicLinker gắn invocation vào call site. Khi không cấu hình, factory dùng transformer mặc định để chuyển invocation sang MethodType của call site qua LinkerServices.

setAutoConversionStrategy() cho phép runtime thay đổi cách áp dụng method invocation conversions sau khi custom conversion của ngôn ngữ đã được áp dụng.

setInternalObjectsFilter() cho phép lọc MethodHandle để object nội bộ của runtime không bị trả ra ngoài phạm vi cho phép. Đây là điểm mở rộng chuyên biệt; ứng dụng thông thường thường không cần cấu hình các hook này.

## 8. CallSiteDescriptor, Operation và MethodType

CallSiteDescriptor chứa ba thông tin cốt lõi:

- MethodHandles.Lookup của nơi tạo call site.
- Operation mô tả thao tác động.
- MethodType mô tả kiểu tham số và kiểu trả về của call site.

Ví dụ một call site đọc property name từ receiver:

~~~java
Operation getName = new NamedOperation(
        new NamespaceOperation(
                StandardOperation.GET,
                StandardNamespace.PROPERTY),
        "name");

CallSiteDescriptor descriptor = new CallSiteDescriptor(
        MethodHandles.lookup(),
        getName,
        MethodType.methodType(Object.class, Object.class));
~~~

GET và SET phải được dùng bên trong NamespaceOperation. NamedOperation gắn tên property vào operation; vì tên đã được gắn vào descriptor nên nó không còn là tham số riêng trong MethodType.

Với ví dụ trên, call site có kiểu tương đương:

~~~text
(Object)Object
~~~

Nghĩa là call site nhận một receiver kiểu Object và trả về Object. Khi cần truy cập method, element hoặc namespace khác, dùng StandardOperation và StandardNamespace tương ứng theo hợp đồng Dynalink.

## 9. Liên kết call site và cơ chế relink

Sau khi tạo descriptor, tạo một RelinkableCallSite và đưa nó cho DynamicLinker:

~~~java
SimpleRelinkableCallSite callSite =
        new SimpleRelinkableCallSite(descriptor);

dynamicLinker.link(callSite);

MethodHandle invoker = callSite.dynamicInvoker();
~~~

dynamicLinker.link() khởi tạo call site với một relink-and-invoke handle. Việc liên kết cụ thể có thể được trì hoãn đến lần gọi đầu tiên, khi receiver thật đã có mặt. Điều đó giúp linker chọn implementation dựa trên kiểu và giá trị đối số thực tế.

Khi invocation đã được cài đặt:

1. Call site gọi MethodHandle đã liên kết.
2. Guard kiểm tra receiver có còn phù hợp không.
3. Nếu guard hợp lệ, invocation được dùng tiếp.
4. Nếu guard thất bại hoặc SwitchPoint bị vô hiệu hóa, call site yêu cầu DynamicLinker liên kết lại.

**SimpleRelinkableCallSite** dùng monomorphic inline cache: giữ một GuardedInvocation tại một thời điểm. Khi receiver đổi kiểu, nó có thể bỏ invocation cũ và relink.

**ChainedCallSite** dùng polymorphic inline cache: có thể giữ chuỗi các invocation còn hợp lệ cho nhiều kiểu receiver. Lựa chọn phụ thuộc số kiểu receiver và hành vi của call site trong runtime.

## 10. Ví dụ hoàn chỉnh: linker ưu tiên và BeansLinker fallback

Chương trình dưới đây tạo một linker ưu tiên cho kiểu Greeting. Linker này xử lý property name và thêm tiền tố priority:. Với kiểu Person thông thường, linker tùy chỉnh trả null để BeansLinker fallback xử lý JavaBean property getName().

Lưu chương trình dưới tên **DynamicLinkerFactoryDemo.java**.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.NamedOperation;
import jdk.dynalink.NamespaceOperation;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.beans.BeansLinker;
import jdk.dynalink.linker.GuardedInvocation;
import jdk.dynalink.linker.GuardingDynamicLinker;
import jdk.dynalink.linker.LinkRequest;
import jdk.dynalink.linker.LinkerServices;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynamicLinkerFactoryDemo {
    public static final class Greeting {
        private final String name;

        public Greeting(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public static final class Person {
        private final String name;

        public Person(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    private static final MethodHandle GREETING_NAME;
    private static final MethodHandle IS_GREETING;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            GREETING_NAME = lookup.findStatic(
                    DynamicLinkerFactoryDemo.class,
                    "greetingName",
                    MethodType.methodType(Object.class, Object.class));
            IS_GREETING = lookup.findStatic(
                    DynamicLinkerFactoryDemo.class,
                    "isGreeting",
                    MethodType.methodType(boolean.class, Object.class));
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static Object greetingName(Object receiver) {
        return "priority:" + ((Greeting) receiver).getName();
    }

    private static boolean isGreeting(Object receiver) {
        return receiver instanceof Greeting;
    }

    private static final class GreetingLinker
            implements GuardingDynamicLinker {
        @Override
        public GuardedInvocation getGuardedInvocation(
                LinkRequest request, LinkerServices services) {
            Operation operation =
                    request.getCallSiteDescriptor().getOperation();

            if (!"name".equals(NamedOperation.getName(operation))) {
                return null;
            }

            Operation baseOperation =
                    NamedOperation.getBaseOperation(operation);
            if (!(baseOperation instanceof NamespaceOperation)) {
                return null;
            }

            NamespaceOperation namespaceOperation =
                    (NamespaceOperation) baseOperation;
            if (!StandardOperation.GET.equals(
                    namespaceOperation.getBaseOperation())
                    || !namespaceOperation.contains(StandardNamespace.PROPERTY)) {
                return null;
            }

            if (!(request.getReceiver() instanceof Greeting)) {
                return null;
            }

            return new GuardedInvocation(GREETING_NAME, IS_GREETING);
        }
    }

    public static void main(String[] args) throws Throwable {
        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setPrioritizedLinker(new GreetingLinker());
        factory.setFallbackLinkers(new BeansLinker());
        factory.setSyncOnRelink(true);

        DynamicLinker linker = factory.createLinker();

        Operation getName = new NamedOperation(
                new NamespaceOperation(
                        StandardOperation.GET,
                        StandardNamespace.PROPERTY),
                "name");

        CallSiteDescriptor descriptor = new CallSiteDescriptor(
                MethodHandles.lookup(),
                getName,
                MethodType.methodType(Object.class, Object.class));

        SimpleRelinkableCallSite callSite =
                linker.link(new SimpleRelinkableCallSite(descriptor));
        MethodHandle invoker = callSite.dynamicInvoker();

        Object custom = invoker.invokeExact((Object) new Greeting("Ada"));
        Object bean = invoker.invokeExact((Object) new Person("Lin"));

        System.out.println("prioritized linker result: " + custom);
        System.out.println("BeansLinker fallback result: " + bean);
        System.out.println("call site type: " + callSite.type());
        System.out.println("auto-loading errors: " +
                factory.getAutoLoadingErrors().size());
    }
}
~~~

Biên dịch và chạy trên JDK 9 trở lên:

~~~bash
javac --release 9 --add-modules jdk.dynalink DynamicLinkerFactoryDemo.java
java --add-modules jdk.dynalink DynamicLinkerFactoryDemo
~~~

Kết quả stdout:

~~~text
prioritized linker result: priority:Ada
BeansLinker fallback result: Lin
call site type: (Object)Object
auto-loading errors: 0
~~~

Giải thích:

- GreetingLinker được đăng ký bằng setPrioritizedLinker(), nên được hỏi trước.
- GreetingLinker chỉ nhận operation GET PROPERTY name và receiver kiểu Greeting.
- GuardedInvocation chứa MethodHandle thực thi greetingName() và guard isGreeting().
- Với Person, linker tùy chỉnh trả null; BeansLinker xử lý JavaBean property name thông qua getName().
- Call site có kiểu Object → Object và được relink khi receiver chuyển từ Greeting sang Person.
- getAutoLoadingErrors() cho biết có lỗi nào trong lần tự phát hiện linker gần nhất hay không.

## 11. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đặt linker tổng quát ở nhóm prioritized | Nó có thể chiếm request trước linker chuyên biệt | Đặt linker đặc thù trước, linker tổng quát ở fallback |
| Quên BeansLinker khi đã thay fallback | JavaBean property/method có thể không còn được xử lý | Đăng ký BeansLinker nếu runtime vẫn cần tương tác Java object |
| Trả GuardedInvocation không có guard phù hợp | Invocation có thể bị dùng với receiver không tương thích | Tạo guard kiểm tra đúng receiver và điều kiện liên kết |
| Ném lỗi khi linker không hỗ trợ operation | Ngăn các linker tiếp theo được thử | Trả null khi không xử lý được request |
| Dùng GET hoặc SET mà không có NamespaceOperation | Operation không đúng cấu trúc chuẩn của Dynalink | Kết hợp GET/SET với PROPERTY, METHOD hoặc ELEMENT phù hợp |
| Đặt MethodType sai với invocation | Lỗi khi chuyển đổi hoặc gọi MethodHandle | Khớp descriptor với kiểu handle và dùng LinkerServices khi cần conversion |
| Không kiểm tra lỗi ServiceLoader | Linker provider bị lỗi có thể bị bỏ qua mà ứng dụng không biết | Kiểm tra getAutoLoadingErrors() sau createLinker() |
| Chỉnh factory đồng thời từ nhiều thread | Cấu hình và quá trình tạo linker có thể cạnh tranh | Cấu hình factory trước khi gọi createLinker() |
| Dùng SimpleRelinkableCallSite cho nhiều kiểu receiver mà không hiểu cache | Call site có thể relink thường xuyên khi receiver đổi kiểu | Cân nhắc ChainedCallSite cho polymorphic inline cache |

## 12. Ghi nhớ

- DynamicLinkerFactory thuộc module jdk.dynalink và có từ Java 9.
- Factory tạo DynamicLinker từ các linker được cấu hình tường minh, tự phát hiện và fallback.
- Thứ tự mặc định là prioritized, auto-discovered, rồi fallback.
- BeansLinker là fallback mặc định nếu không cấu hình fallback khác hoặc truyền null.
- ServiceLoader tìm GuardingDynamicLinkerExporter bằng class loader được cấu hình.
- setSyncOnRelink(true) hữu ích khi runtime thực thi code liên kết động đa luồng.
- setUnstableRelinkThreshold() điều chỉnh số lần relink trước khi call site được xem là unstable.
- CallSiteDescriptor kết hợp Lookup, Operation và MethodType; GET/SET phải đi cùng NamespaceOperation.
- DynamicLinker liên kết RelinkableCallSite với GuardedInvocation và relink khi guard không còn hợp lệ.
- Dùng linker ưu tiên cho object model của runtime; giữ fallback để xử lý kiểu dữ liệu tổng quát.
- Factory không thread-safe; cấu hình xong rồi mới tạo DynamicLinker.
- Đây là API JDK hiện hành; không cần dựa vào package nội bộ hoặc thư viện Dynalink cũ bên ngoài cho ví dụ này.

## Tài liệu tham khảo

- [DynamicLinkerFactory — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/jdk/dynalink/DynamicLinkerFactory.html)
- [DynamicLinkerFactory — Java SE API hiện hành](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html)
- [Dynalink package — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/jdk/dynalink/package-summary.html)
- [StandardOperation — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/jdk/dynalink/StandardOperation.html)
- [SimpleRelinkableCallSite — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/jdk/dynalink/support/SimpleRelinkableCallSite.html)
