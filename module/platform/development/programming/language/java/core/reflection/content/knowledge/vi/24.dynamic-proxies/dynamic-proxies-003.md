# Chọn class loader nhìn thấy đúng các interface khi tạo Java dynamic proxy

## 1. Vấn đề thực tế

Trong Java Reflection, `java.lang.reflect.Proxy` tạo đối tượng triển khai một hoặc nhiều **interface tại runtime**, rồi chuyển lời gọi phương thức tới `InvocationHandler`. API chính là:

~~~java
Object proxy = Proxy.newProxyInstance(
        loader,
        new Class<?>[] {Service.class, Auditable.class},
        handler);
~~~

*Đây là đoạn mã minh họa, giả định các kiểu và biến đã được khai báo.*

Tham số `loader` rất quan trọng: JVM dùng nó để định nghĩa lớp proxy được sinh ra, và **loader đó phải nhìn thấy đúng từng interface** mà proxy triển khai. Một interface có thể tồn tại trong chương trình nhưng không nhìn thấy từ loader được chọn; hai lớp/interface có tên giống hệt nhau vẫn có thể là **hai kiểu khác nhau** nếu được định nghĩa bởi hai class loader khác nhau.

**Mục tiêu bài học:** biết chọn loader phù hợp trong chương trình thông thường và môi trường plugin/module; hiểu phép kiểm tra danh tính `Class` của `Proxy`; kiểm chứng trước khi tạo proxy; nhận biết lỗi do loader, do quy tắc interface, và do ép kiểu.

## 2. “Nhìn thấy interface” nghĩa chính xác là gì?

Với từng interface `i` và class loader `cl`, một điều kiện bắt buộc của `Proxy.newProxyInstance` là:

~~~java
Class.forName(i.getName(), false, cl) == i
~~~

Ý nghĩa của từng phần:

- `i` là **chính đối tượng `Class<?>`** của interface được truyền trong mảng `interfaces`.
- `i.getName()` là tên nhị phân (*binary name*) của interface.
- `Class.forName(name, false, cl)` thử phân giải kiểu có tên đó bằng loader `cl`, với `initialize=false` để không chủ động khởi tạo lớp.
- `== i` yêu cầu trả về **đúng cùng một đối tượng `Class`**, chứ không đơn thuần là hai kiểu có cùng tên.

Nếu `Class.forName` không tìm được kiểu, nó ném `ClassNotFoundException`. Nếu tìm được **một interface khác có cùng tên**, phép so sánh `==` vẫn sai. `Proxy.newProxyInstance` sẽ từ chối trường hợp vi phạm quy tắc nhìn thấy kiểu, thường bằng `IllegalArgumentException`. Lưu ý: lớp có thể được phân giải qua cơ chế **ủy quyền** (*delegation*) của loader; không đòi hỏi `i.getClassLoader() == cl`.

Đây là phân biệt then chốt:

| Câu hỏi | Phép kiểm tra | Ý nghĩa |
| --- | --- | --- |
| Hai interface có tên giống nhau? | `a.getName().equals(b.getName())` | Chỉ so sánh tên |
| Hai interface là cùng một kiểu runtime? | `a == b` | So sánh định danh `Class` |
| Loader `cl` thấy đúng interface `i`? | `Class.forName(i.getName(), false, cl) == i` | Điều kiện bắt buộc của dynamic proxy |
| Một đối tượng có triển khai `i`? | `i.isInstance(object)` | Kiểm tra tương thích kiểu lúc chạy |

Java xác định kiểu tham chiếu theo **tên nhị phân cùng class loader định nghĩa kiểu**, không chỉ dựa vào tên. Loader được chọn cho proxy vì thế phải thấy **đúng `Class`** của mọi interface đầu vào.

## 3. Hình dung class loader trong môi trường ứng dụng và plugin

Ví dụ có một class loader ứng dụng `AppLoader` và loader plugin `PluginLoader` ủy quyền về `AppLoader`:

~~~text
                  Bootstrap / Platform
                           ↑
                        AppLoader
                       (SharedApi)
                           ↑ ủy quyền về cha
                       PluginLoader
                       (PluginOnlyApi)

AppLoader:   thường thấy SharedApi; không tự động thấy PluginOnlyApi
PluginLoader: có thể thấy cả SharedApi (qua cha) và PluginOnlyApi (do mình nạp)
~~~

Trong cấu hình này, khi cần proxy cho `SharedApi` **và** `PluginOnlyApi`, loader plugin có thể là lựa chọn hợp lý **nếu** kiểm tra `Class.forName(..., false, PluginLoader) == i` đúng với *cả hai* interface. Loader ứng dụng thường không thể nhìn thấy interface chỉ có trong plugin. Ngược lại, trong hệ thống dùng loader riêng không ủy quyền chuẩn, một loader có thể nạp lại `SharedApi` thành **bản sao cùng tên nhưng khác kiểu**; khi đó không dùng nó để triển khai interface `SharedApi` của ứng dụng.

Không có quy tắc “cứ loader con là đúng”. Cấu trúc ủy quyền, chính sách child-first, JPMS và danh tính thực của mỗi `Class<?>` mới quyết định khả năng tương thích.

## 4. Quy trình chọn loader

1. **Thu thập chính các `Class<?>` của interface cần triển khai.** Ví dụ `Service.class` của API dùng chung hoặc `pluginApiClass` nhận từ loader plugin. Tránh tải lại interface chỉ bằng tên nếu đã có `Class<?>` đáng tin cậy.
2. **Chọn ứng viên dựa trên nơi các interface được định nghĩa và cơ chế ủy quyền.** Nếu chỉ có một interface thông thường, `Service.class.getClassLoader()` là điểm xuất phát đơn giản. Với nhiều interface của plugin, xem loader plugin có nhìn thấy toàn bộ interface, kể cả API dùng chung, hay không.
3. **Kiểm tra danh tính của tất cả interface**, bằng phép so sánh ở mục 2. Nếu một interface không đạt, đổi kiến trúc nạp lớp hoặc chọn loader khác có thể thấy đồng thời các kiểu thực sự cần dùng.
4. **Kiểm tra giới hạn khác của dynamic proxy.** Các interface phải hợp lệ, khả năng truy cập qua module/package phải cho phép, các kiểu xuất hiện trong chữ ký phương thức `public` cũng phải nhìn thấy; proxy có thể bị từ chối dù bước 3 đã đạt.
5. **Tạo proxy bằng đúng loader và mảng interface đã kiểm tra**, sau đó dùng proxy thông qua interface được chia sẻ giữa phía gọi và proxy.

Có thể viết phép kiểm tra sơ bộ như sau:

~~~java
static boolean seesAllInterfaces(ClassLoader loader, Class<?>... interfaces) {
    for (Class<?> iface : interfaces) {
        if (iface == null || !iface.isInterface()) {
            return false;
        }
        try {
            if (Class.forName(iface.getName(), false, loader) != iface) {
                return false;
            }
        } catch (ClassNotFoundException ex) {
            return false;
        }
    }
    return true;
}
~~~

*Đây là phương thức minh họa, cần đặt trong một lớp Java; ví dụ hoàn chỉnh ở mục 5.*

Hàm trên xác nhận **từng interface đầu vào nhìn thấy được và có cùng định danh**, nhưng **chưa chứng minh proxy chắc chắn tạo được**: quy tắc về kiểu của tham số/giá trị trả về, method trùng chữ ký, interface không công khai, module, interface `sealed` hoặc `hidden` vẫn cần được `Proxy` xác thực. Các lỗi nạp/liên kết lớp khác `ClassNotFoundException` cũng có thể phát sinh và không nên che giấu như một kết quả `false` thông thường.

## 5. Ví dụ Java 17+ chạy độc lập: một loader thấy đủ, một loader chỉ thấy một interface

Trong chương trình dưới đây, `Greeter` và `Tag` đều do loader ứng dụng nhìn thấy. `MaskingLoader` được tạo ra để **cố ý từ chối nạp `Tag`**, mô phỏng tình huống chọn loader không nhìn thấy đầy đủ interface. Đây là loader phục vụ bài thực nghiệm; trong ứng dụng thật, lỗi thường đến từ ranh giới giữa các module/plugin hoặc classpath khác nhau.

Tạo tệp `ProxyLoaderChoiceDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyLoaderChoiceDemo {
    public interface Greeter {
        String greet(String name);
    }

    public interface Tag {
    }

    static final class MaskingLoader extends ClassLoader {
        MaskingLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (name.equals(Tag.class.getName())) {
                throw new ClassNotFoundException(name);
            }
            return super.loadClass(name, resolve);
        }
    }

    static boolean seesAllInterfaces(ClassLoader loader, Class<?>... types) {
        for (Class<?> type : types) {
            if (type == null || !type.isInterface()) {
                return false;
            }
            try {
                if (Class.forName(type.getName(), false, loader) != type) {
                    return false;
                }
            } catch (ClassNotFoundException ex) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        ClassLoader good = Greeter.class.getClassLoader();
        ClassLoader masked = new MaskingLoader(good);
        Class<?>[] interfaces = {Greeter.class, Tag.class};

        System.out.println("good sees all: "
                + seesAllInterfaces(good, interfaces));
        System.out.println("masked sees Greeter: "
                + seesAllInterfaces(masked, Greeter.class));
        System.out.println("masked sees Tag: "
                + seesAllInterfaces(masked, Tag.class));

        InvocationHandler handler = (proxy, method, values) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreeterProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == values[0];
                    default -> throw new UnsupportedOperationException();
                };
            }
            if (method.getName().equals("greet")) {
                return "Xin chào, " + values[0];
            }
            throw new UnsupportedOperationException(method.toString());
        };

        Object created = Proxy.newProxyInstance(
                good, interfaces, handler);
        Greeter greeter = (Greeter) created;

        System.out.println(greeter.greet("Linh"));
        System.out.println("implements Tag: " + (created instanceof Tag));
        System.out.println("proxy loader == good: "
                + (created.getClass().getClassLoader() == good));

        try {
            Proxy.newProxyInstance(masked, interfaces, handler);
            System.out.println("unexpected success");
        } catch (IllegalArgumentException ex) {
            System.out.println("masked rejected: IllegalArgumentException");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac ProxyLoaderChoiceDemo.java
java ProxyLoaderChoiceDemo
~~~

Kết quả:

~~~text
good sees all: true
masked sees Greeter: true
masked sees Tag: false
Xin chào, Linh
implements Tag: true
proxy loader == good: true
masked rejected: IllegalArgumentException
~~~

Giải thích:

- `good` nhìn thấy cả hai interface nên có thể tạo lớp proxy triển khai `Greeter` và `Tag`.
- `masked` vẫn nhìn thấy `Greeter` nhờ ủy quyền cho `good` nhưng từ chối `Tag`. **Chỉ cần một interface không nhìn thấy** là mảng interface không hợp lệ với loader đó.
- Proxy được tạo bằng `good` có thể ép về `Greeter` và kiểm tra bằng `instanceof Tag`.
- `InvocationHandler` nhận các lời gọi qua proxy; ví dụ cũng xử lý `equals`, `hashCode` và `toString` thừa hưởng từ `Object` để tránh trả sai kiểu dữ liệu. Logic nghiệp vụ của `greet` độc lập với quy tắc chọn loader.

Trong ứng dụng thực, đừng sửa loader để “giấu” interface như `MaskingLoader`. Hãy chọn một loader **thật sự thấy đúng tất cả kiểu** hoặc thiết kế một API dùng chung qua ranh giới plugin.

## 6. Chọn `getClassLoader()`, context class loader hay system loader?

| Ứng viên | Khi nào cân nhắc | Giới hạn |
| --- | --- | --- |
| `MyApi.class.getClassLoader()` | Một hoặc nhiều interface thuộc API dùng chung, loader này thấy đủ tất cả | Không tự động thấy interface chỉ có trong plugin |
| `pluginInterface.getClassLoader()` | Interface do plugin nạp; loader plugin có thể ủy quyền thấy các API chung | Phải xác minh từng interface, kể cả API từ phía ứng dụng |
| `Thread.currentThread().getContextClassLoader()` (TCCL) | Framework/container đặt loader ngữ cảnh để khám phá kiểu theo yêu cầu hiện tại | Có thể là `null`, bị thay đổi, hoặc thấy bản sao không đúng của interface |
| `ClassLoader.getSystemClassLoader()` | Ứng dụng classpath đơn giản và tất cả interface đều có thể tìm bởi system loader | Không phải loader chung cho mọi môi trường plugin/container |
| `null` (bootstrap loader) | Interface có thể phân giải thông qua bootstrap loader và các quy tắc khác cho phép | Không phù hợp với interface ứng dụng thông thường |

**TCCL là một gợi ý về ngữ cảnh nạp lớp, không phải đảm bảo tính đúng.** Ví dụ một plugin có thể cần TCCL để nạp lớp triển khai hoặc tài nguyên, nhưng loader dùng cho `Proxy` vẫn phải vượt qua bài kiểm tra danh tính interface. Nếu framework tạm đổi TCCL, hãy bảo đảm khôi phục đúng loader cũ sau khi hoàn tất công việc.

Đoạn kiểm tra khi cần xem xét TCCL:

~~~java
ClassLoader context = Thread.currentThread().getContextClassLoader();
if (!seesAllInterfaces(context, interfaces)) {
    throw new IllegalArgumentException(
            "Context class loader cannot see the requested interfaces");
}
Object proxy = Proxy.newProxyInstance(context, interfaces, handler);
~~~

*Fragment này giả định hàm `seesAllInterfaces`, biến `interfaces` và `handler` đã được định nghĩa; vẫn cần xử lý các giới hạn proxy khác.*

Khi có sẵn interface `Class<?>`, ưu tiên truyền chúng trực tiếp thay vì ghép tên để tải qua TCCL rồi hy vọng nhận đúng kiểu.

## 7. Cùng tên nhưng khác `ClassLoader`: lỗi khó tìm trong hệ plugin

Giả sử ứng dụng và plugin **đều nạp riêng** bytecode của `com.example.api.Service`:

~~~text
AppLoader    → Class A: com.example.api.Service
PluginLoader → Class B: com.example.api.Service

A.getName().equals(B.getName()) == true
A == B                             == false
~~~

Đây là **minh họa hai kiểu runtime khác nhau**, không phải tên lớp của một chương trình ví dụ độc lập. Nếu `PluginLoader` tìm thấy `B` khi yêu cầu `Service`, nhưng bạn truyền `A` vào `Proxy.newProxyInstance`, điều kiện `Class.forName(A.getName(), false, PluginLoader) == A` thất bại. Ngay cả khi tạo được proxy triển khai `B`, mã ứng dụng đang mong `A` vẫn không thể ép proxy thành `A`: việc trùng tên không tạo quan hệ kiểu.

Cách tổ chức thường dùng:

- Đặt interface hợp đồng chung vào một thư viện/API được nạp **một lần** bởi loader dùng chung; loader plugin ủy quyền tới bản chung thay vì chứa một bản riêng.
- Nếu plugin có interface riêng, truyền `Class<?>` thực tế mà plugin đang dùng, rồi chọn một loader phân giải chính xác cả interface riêng và hợp đồng chung.
- Nếu các interface bắt buộc nằm trong hai vùng loader không thể nhìn thấy lẫn nhau, **không có một tham số `loader` thần kỳ** để tạo proxy cho cả hai. Cần điều chỉnh cấu trúc loader, tách proxy hoặc dùng một lớp chuyển tiếp qua API chung.

Một `ClassLoader` được đưa vào `Proxy.newProxyInstance` **có thể khác** loader trực tiếp định nghĩa một số interface trong danh sách: ủy quyền có thể trả về đúng `Class` của loader cha. Điều kiện là **danh tính được phân giải trùng khớp**, không phải mọi `getClassLoader()` đều bằng nhau.

## 8. Những ràng buộc khác thường bị nhầm thành lỗi class loader

Theo API `Proxy.newProxyInstance` của Java 17+:

- Mỗi phần tử của mảng `interfaces` phải là **interface hợp lệ**, không phải class, primitive, interface `sealed` hoặc `hidden`; không được truyền trùng cùng đối tượng `Class<?>`.
- **Mọi kiểu tham chiếu được dùng trong chữ ký của các phương thức `public`** của các interface (kể cả phương thức kế thừa) cũng phải nhìn thấy theo tên qua loader đã chọn. Không đủ nếu chỉ kiểm tra tên của chính interface.
- Với nhiều interface **không `public`**, tất cả phải thuộc **cùng package và module**, được định nghĩa bởi loader được cung cấp và thỏa các điều kiện truy cập. Một loader nhìn thấy chúng chưa đủ để vượt qua hạn chế này.
- Các phương thức của nhiều interface có cùng tên và danh sách tham số phải có **kiểu trả về tương thích** theo quy tắc proxy. Thứ tự các interface còn có ý nghĩa khi có những chữ ký phương thức trùng nhau.
- Trong ứng dụng dùng **Java Platform Module System (JPMS)**, Java có quy tắc xác định package/module chứa lớp proxy, đôi khi sinh proxy trong *dynamic module*. Tránh mặc định rằng có thể truy cập `public` constructor của lớp proxy bằng Reflection từ module bất kỳ; sử dụng `Proxy.newProxyInstance` như API được thiết kế.

Lỗi phổ biến:

| Biểu hiện | Hướng chẩn đoán |
| --- | --- |
| `IllegalArgumentException` từ `newProxyInstance` | Kiểm tra interface có hợp lệ, có trùng, có thấy đúng danh tính qua loader, kiểu trong chữ ký và giới hạn package/module |
| `ClassNotFoundException` khi thử `Class.forName` | Loader không tìm được kiểu bằng tên đó |
| `ClassCastException` sau khi tạo proxy | Phía gọi có thể đang dùng một `Class` khác, hoặc proxy không triển khai interface mong đợi |
| `IllegalAccessException` khi tìm cách tự khởi tạo lớp proxy | Có thể do quy tắc truy cập proxy trong module; dùng `newProxyInstance` |
| `NoClassDefFoundError` hoặc lỗi liên kết khác | Kiểm tra dependency và khả năng nạp/liên kết các kiểu tham chiếu; đây không nhất thiết là lỗi so sánh interface |

Đừng khắc phục một cách máy móc bằng `setAccessible(true)`, thay đổi thứ tự interface hoặc ép kiểu không kiểm tra. Những thao tác đó không làm hai đối tượng `Class` khác nhau trở thành một.

## 9. Cách chẩn đoán khi proxy không tạo được

Khi gặp lỗi ở ranh giới framework/plugin, ghi nhận các giá trị sau cho **từng interface**:

~~~java
for (Class<?> i : interfaces) {
    System.out.println("interface: " + i.getName());
    System.out.println("defined by: " + i.getClassLoader());
    System.out.println("module: " + i.getModule());
    try {
        Class<?> resolved = Class.forName(i.getName(), false, loader);
        System.out.println("same Class: " + (resolved == i));
        System.out.println("resolved by: " + resolved.getClassLoader());
    } catch (ClassNotFoundException ex) {
        System.out.println("not visible by name");
    }
}
~~~

*Fragment dùng biến `loader` và `interfaces` đã có. Tên do `getName()` trả về không đủ để kết luận kiểu giống nhau; kết quả `same Class` mới trả lời câu hỏi quan trọng.*

Đồng thời kiểm tra loader của các kiểu xuất hiện trong tham số/kiểu trả về của phương thức `public`, mối quan hệ giữa các module, tính `public` của interface và xem trong classpath/plugin có nhiều bản thư viện hợp đồng hay không. Chỉ bật log/diagnostics phù hợp; đừng phụ thuộc vào tên tự sinh của lớp proxy như một API ổn định.

## 10. Tự kiểm tra kiến thức

1. `Proxy.newProxyInstance` yêu cầu điều gì ở mỗi interface `i` với loader `cl`? **`Class.forName(i.getName(), false, cl) == i`.**
2. Nếu `AppLoader` định nghĩa API chung, `PluginLoader` ủy quyền về cha và tự nạp interface plugin, loader nào có khả năng tạo proxy cho cả hai? **`PluginLoader`, khi kiểm tra danh tính và các ràng buộc khác đều đạt.**
3. `interfaceA.getName().equals(interfaceB.getName())` là `true` nhưng `interfaceA == interfaceB` là `false`. Có thể coi chúng là cùng kiểu không? **Không.** Tên giống nhau không bảo đảm định danh cùng loader.
4. TCCL có phải luôn là lựa chọn đúng? **Không.** Phải xác minh nó thấy đúng mọi interface.
5. Một loader thấy đúng tất cả interface, có chắc tạo được proxy? **Chưa chắc.** Còn kiểu trong public method signatures, ràng buộc `non-public` interface/module, method trùng chữ ký, `sealed`/`hidden`, v.v.
6. Vì sao có thể gặp `ClassCastException` sau khi tạo proxy thành công? **Mã ép kiểu có thể tham chiếu interface khác danh tính hoặc interface không được proxy triển khai.**

## 11. Kết luận

Khi tạo dynamic proxy, hãy chọn **một class loader phân giải được đúng mọi interface với cùng định danh `Class`**, rồi xác minh thêm các ràng buộc kiểu, package và module. Trong chương trình đơn giản, loader của API interface thường đủ. Trong framework/plugin, quyết định phải dựa trên cấu trúc nạp lớp thực tế và cơ chế ủy quyền. Điều kiện `Class.forName(i.getName(), false, loader) == i` là phép kiểm tra xuất phát đáng tin cậy để tránh nhầm “cùng tên” với “cùng kiểu”.

Tài liệu tham khảo:
- [Java SE 21 — `Proxy.newProxyInstance` và các hạn chế đối với interface](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 21 — `Class.forName` và danh tính lớp](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [Java SE 21 — `ClassLoader` và cơ chế nạp lớp](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
