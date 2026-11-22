# Khởi tạo SPI trong JPMS: constructor hay public static provider()?

`ServiceLoader` là cơ chế chuẩn để ứng dụng Java khám phá và tạo đối tượng cung cấp một **service contract** (SPI), trong khi module tiêu thụ chỉ phụ thuộc vào interface/abstract class công khai của service. Với **Java Platform Module System (JPMS)**, module cung cấp dịch vụ đăng ký provider qua `provides ... with ...` và có **hai cơ chế tạo service instance**:

1. **Provider constructor:** `ServiceLoader` gọi constructor `public` không tham số của class provider, class đó phải triển khai/mở rộng service.
2. **Provider method:** `ServiceLoader` gọi phương thức `public static provider()` không tham số trên class được khai báo là provider; phương thức trả về một instance của service. Bản thân class chứa factory **không cần** triển khai service.

Chọn cơ chế phù hợp sẽ quyết định cách bạn che giấu implementation, xây dựng đối tượng, phát hiện lỗi cấu hình, đọc metadata provider và quản lý vòng đời instance. Bài này tập trung vào cách **khởi tạo provider bằng hai cơ chế trong explicit named modules**, đồng thời phân biệt các quy tắc khi dùng classpath hoặc automatic module.

## 1. Các vai trò trong một hợp đồng SPI có module

Giả sử một ứng dụng muốn dùng `MessageService` mà không cần biết nhà cung cấp cụ thể:

~~~text
lesson.app                 lesson.spi                  lesson.providers
(host/consumer)              (API)                     (implementations)
requires lesson.spi  ----> exports lesson.spi <---- requires lesson.spi
uses MessageService                                         |
       |                                                    |
       +--- ServiceLoader<MessageService> <--- provides MessageService
                                               with DirectMessage, FactoryMessage
~~~

- **Service type:** interface hoặc class được người dùng API nhận biết, chẳng hạn `lesson.spi.MessageService`.
- **Consumer module:** module thực hiện khám phá, có `uses lesson.spi.MessageService;` và thông thường `requires lesson.spi;`.
- **Provider module:** module khai báo `provides lesson.spi.MessageService with ...;` để đăng ký một hoặc nhiều provider.
- **Provider class:** class được đặt **sau từ khóa `with`**. Đối với constructor path, class này là implementation. Đối với factory path, class này có thể chỉ là nơi cung cấp phương thức `provider()`.
- **Service instance:** đối tượng thực sự được trả về cho host khi provider được khởi tạo; luôn phải tương thích với service type.

`uses` và `provides` là metadata mô-đun; `ServiceLoader` dùng chúng để tìm nhà cung cấp được resolve. `requires` diễn tả phụ thuộc vào API giữa các module. Module consumer thường **không** cần `requires lesson.providers`: điều này giữ cấu trúc mở rộng không phụ thuộc vào implementation cụ thể.

## 2. Khởi tạo bằng provider constructor

### 2.1. Điều kiện cần

Đối với một provider được khai báo bằng `provides` trong module và **không khai báo provider method**, lớp provider cần:

- Là class công khai được khai báo trong chính module đang có `provides`; module provider có thể giữ package implementation không export.
- Là subtype hợp lệ của service type: `implements ServiceInterface` hoặc `extends AbstractService` phù hợp.
- Có **constructor `public` không tham số**. Constructor do Java tự sinh có thể đáp ứng nếu class công khai và không khai báo constructor nào khác.
- Có thể khởi tạo bình thường; nếu constructor ném lỗi, việc tạo service thất bại.

Ví dụ:

~~~java
package lesson.providers;

import lesson.spi.MessageService;

public final class DirectMessage implements MessageService {
    public DirectMessage() {
        System.out.println("constructor: DirectMessage");
    }

    @Override
    public String message(String name) {
        return "Hello, " + name;
    }
}
~~~

Khi provider này được yêu cầu qua `ServiceLoader`, JDK tạo `DirectMessage` bằng constructor công khai không tham số. Đối tượng kết quả chính là instance của class đó; `Provider.type()` sẽ trả `DirectMessage.class`.

Một constructor có tham số như `DirectMessage(Settings settings)` **không** thay thế được provider constructor. `ServiceLoader` không tự đưa đối tượng cấu hình hay đối tượng DI vào các tham số. Nếu cần khởi tạo với cấu hình phức tạp, có thể chọn factory path, hoặc tạo instance đơn giản rồi cấu hình qua hợp đồng lifecycle được định nghĩa riêng.

### 2.2. Khi nào cơ chế này phù hợp?

Constructor path thường dễ kiểm tra và ít tầng gián tiếp khi:

- Class provider chính là implementation public của service.
- Khởi tạo đủ đơn giản và không cần lựa chọn implementation theo điều kiện runtime.
- Không muốn công bố factory riêng hoặc quy tắc khởi tạo đặc biệt.
- Cần cách đóng gói hỗ trợ cả explicit named module, **automatic module** và kiểu provider dựa trên `META-INF/services` ở classpath.

Dù class provider `public`, module có thể không `exports` package implementation. Tính công khai trong khai báo Java và việc export package của JPMS là hai tầng kiểm soát khác nhau.

## 3. Khởi tạo bằng public static provider()

### 3.1. Hợp đồng của provider method

Trong **explicit named module**, nếu class provider khai báo một phương thức:

~~~java
public static MessageService provider()
~~~

thì `ServiceLoader` dùng phương thức đó để lấy service instance. Phương thức hợp lệ phải:

1. Có tên chính xác `provider`, là `public static` và **không có tham số**.
2. Có **kiểu trả về khai báo** gán được cho service type (cùng service type hoặc subtype hợp lệ).
3. Có mặt trên provider class được đăng ký qua `provides` trong chính module đó.
4. Trả về **một đối tượng không `null`**, tương thích với service type; ngoại lệ ném ra từ factory sẽ làm thao tác khởi tạo thất bại.

Ví dụ:

~~~java
package lesson.providers;

import lesson.spi.MessageService;

public final class FactoryMessage {
    private FactoryMessage() {}

    public static MessageService provider() {
        return new PrivateMessage();
    }
}

final class PrivateMessage implements MessageService {
    @Override
    public String message(String name) {
        return "Hi, " + name;
    }
}
~~~

`FactoryMessage` được ghi trong `provides`, nhưng **không implements `MessageService`** và có **constructor private**. Đối tượng được tạo là `PrivateMessage`, một class package-private. Mã ở module tiêu thụ nhận instance dưới dạng `MessageService` mà không cần truy cập implementation trực tiếp.

Với provider factory, **`Provider.type()` trả về `Class` của kiểu trả về *được khai báo* ở `provider()`**. Với ví dụ này là `MessageService.class`, không phải `FactoryMessage.class` hay `PrivateMessage.class`.

### 3.2. Factory được gọi như thế nào?

~~~text
Provider module declares:
provides MessageService with FactoryMessage
                            |
                            +--> public static MessageService provider()
                                      |
                                      +--> new PrivateMessage()
                                              |
                                              +--> instance of MessageService
~~~

Không có constructor injection tự động: chữ ký factory không có tham số. Factory vẫn có thể dùng logic bên trong để chọn một implementation, tạo proxy/decorator hoặc điều phối cache đã được thiết kế trước, nhưng cần bảo đảm cấu hình hợp lệ, xử lý lỗi và tránh side effect bất ngờ.

Đặc biệt, **factory class không bị yêu cầu có public no-arg constructor**; nó có thể dùng constructor private, hoặc thậm chí provider type có thể là một interface/abstract class khai báo static factory phù hợp theo quy tắc Java. Đối với code mẫu, một class `final` với constructor private giúp thể hiện rõ ý định “chỉ dùng factory”.

### 3.3. Nếu có cả constructor và provider() thì sao?

Đối với một provider hợp lệ trong explicit named module, nếu có provider method, `ServiceLoader` **chọn phương thức `provider()`** để tạo instance. Điều này cũng đúng khi provider class tự implements service và đồng thời có public no-arg constructor. Không nên thiết kế hai đường tạo với side effect khác nhau mà phụ thuộc vào việc người dùng đoán đường nào được gọi.

Ngược lại, nếu provider class **không có** provider method hợp lệ, nó phải đáp ứng yêu cầu constructor và subtype. Không thể coi một method `create()`, một method `provider(String name)` hay một static field `INSTANCE` là provider method thay thế.

## 4. So sánh trực tiếp hai cơ chế

| Khía cạnh | Provider constructor | Public static provider() |
| --- | --- | --- |
| Dạng khai báo trong JPMS | `provides S with DirectImpl;` | `provides S with FactoryClass;` |
| Provider class cần là subtype của `S`? | **Có** | **Không bắt buộc** |
| Constructor `public` không tham số? | **Bắt buộc** | **Không bắt buộc** |
| Factory `public static provider()` không tham số? | Không có | **Bắt buộc** |
| Kiểu trả về được kiểm tra | Instance là class provider, là subtype `S` | Kiểu trả về khai báo của method là subtype `S` |
| `Provider.type()` | Class provider trực tiếp | Kiểu trả về khai báo của method |
| `Provider.get()` | Kích hoạt constructor | Kích hoạt method |
| Có thể che implementation cụ thể? | Class triển khai phải là provider công khai | Có thể trả class package-private hoặc một implementation được chọn |
| Hỗ trợ ở classpath/automatic module | Có, theo quy tắc provider constructor | **Không** |
| Chi phí/side effect khởi tạo | Trong constructor | Trong factory và quá trình tạo object nó lựa chọn |

Cả hai đều là cách **khởi tạo một service provider cho `ServiceLoader`**. Không cơ chế nào mặc định bảo đảm singleton, thread safety, retry, lifecycle cleanup hay isolation giữa các tenant.

## 5. Ví dụ Java 17 có thể biên dịch và chạy

Bộ ví dụ dùng **ba explicit named modules**: một module SPI, một module đăng ký hai provider theo hai cách, một module consumer. Mục đích là quan sát khi nào constructor/factory được gọi, instance trả về có kiểu gì, và vì sao đọc danh sách `Provider` chưa đồng nghĩa đã tạo instance.

Cấu trúc tệp:

~~~text
src/
├── lesson.spi/
│   ├── module-info.java
│   └── lesson/spi/MessageService.java
├── lesson.providers/
│   ├── module-info.java
│   └── lesson/providers/
│       ├── DirectMessage.java
│       └── FactoryMessage.java
└── lesson.app/
    ├── module-info.java
    └── lesson/app/Main.java
~~~

### 5.1. Khai báo module SPI

Tệp `src/lesson.spi/module-info.java`:

~~~java
module lesson.spi {
    exports lesson.spi;
}
~~~

Tệp `src/lesson.spi/lesson/spi/MessageService.java`:

~~~java
package lesson.spi;

public interface MessageService {
    String message(String name);
}
~~~

Dùng interface làm service type giúp host chỉ phụ thuộc vào lời gọi `message`, không ép kiểu về implementation class của provider.

### 5.2. Khai báo module chứa providers

Tệp `src/lesson.providers/module-info.java`:

~~~java
module lesson.providers {
    requires lesson.spi;
    provides lesson.spi.MessageService
            with lesson.providers.DirectMessage, lesson.providers.FactoryMessage;
}
~~~

`provides ... with ...` chỉ rõ thứ tự đăng ký hai provider **trong cùng một descriptor module**. Package `lesson.providers` được giữ kín vì không có `exports lesson.providers;`. Host vẫn có thể khám phá provider qua `ServiceLoader` theo hợp đồng JPMS.

Tệp `src/lesson.providers/lesson/providers/DirectMessage.java`:

~~~java
package lesson.providers;

import lesson.spi.MessageService;

public final class DirectMessage implements MessageService {
    public DirectMessage() {
        System.out.println("constructor: DirectMessage");
    }

    @Override
    public String message(String name) {
        return "Hello, " + name;
    }
}
~~~

Tệp `src/lesson.providers/lesson/providers/FactoryMessage.java`:

~~~java
package lesson.providers;

import lesson.spi.MessageService;

public final class FactoryMessage {
    private FactoryMessage() {}

    public static MessageService provider() {
        System.out.println("factory: provider()");
        return new PrivateMessage();
    }
}

final class PrivateMessage implements MessageService {
    @Override
    public String message(String name) {
        return "Hi, " + name;
    }
}
~~~

Lưu ý `PrivateMessage` nằm cùng source file nhưng là class top-level **không public**. Java cho phép điều này khi file chỉ có một class top-level public có tên khớp tên file. Provider thực tế được che trong module và giao tiếp qua `MessageService`.

### 5.3. Khai báo module tiêu thụ

Tệp `src/lesson.app/module-info.java`:

~~~java
module lesson.app {
    requires lesson.spi;
    uses lesson.spi.MessageService;
}
~~~

Tệp `src/lesson.app/lesson/app/Main.java`:

~~~java
package lesson.app;

import java.util.List;
import java.util.ServiceLoader;
import lesson.spi.MessageService;

public final class Main {
    public static void main(String[] args) {
        List<ServiceLoader.Provider<MessageService>> providers =
                ServiceLoader.load(MessageService.class).stream().toList();
        System.out.println("found=" + providers.size());
        for (ServiceLoader.Provider<MessageService> provider : providers) {
            System.out.println("type=" + provider.type().getName());
        }
        System.out.println("create:");
        for (ServiceLoader.Provider<MessageService> provider : providers) {
            MessageService instance = provider.get();
            System.out.println(instance.message("Java"));
        }
    }
}
~~~

Vòng đầu xử lý `Provider.type()` và chưa gọi `Provider.get()`. Vòng thứ hai mới kích hoạt tạo instance bằng constructor hoặc factory. `List` chỉ giữ provider handles để trình bày hai giai đoạn rõ ràng.

### 5.4. Lệnh biên dịch và chạy

Ở thư mục chứa `src/`, với JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 --module-source-path src -d out -m lesson.app,lesson.providers
java --module-path out --add-modules lesson.providers -m lesson.app/lesson.app.Main
~~~

`javac` biên dịch các module đích và module `lesson.spi` cần thiết. Khi chạy, `--module-path out` cho JVM thấy các compiled modules. `--add-modules lesson.providers` bảo đảm module provider được **resolve** để service binding có thể tìm thấy provider trong ví dụ đơn giản này. Trong ứng dụng thật, module graph và cấu hình runtime có thể cung cấp cách resolve provider khác.

**Stdout chính xác của ví dụ:**

~~~text
found=2
type=lesson.providers.DirectMessage
type=lesson.spi.MessageService
create:
constructor: DirectMessage
Hello, Java
factory: provider()
Hi, Java
~~~

Các dòng in ra có ý nghĩa:

1. `found=2`: `ServiceLoader.stream()` khám phá hai provider. Con số này đúng với **bộ module của ví dụ**; một ứng dụng có thể có thêm provider khác.
2. `type=lesson.providers.DirectMessage`: provider constructor khai báo subtype triển khai service, nên `type()` là class provider.
3. `type=lesson.spi.MessageService`: factory khai báo trả `MessageService`, nên `type()` là return type của method, **không phải** `FactoryMessage` hoặc `PrivateMessage`.
4. `create:` xuất hiện trước hai lời gọi khởi tạo, chứng minh vòng duyệt metadata ở ví dụ **chưa gọi constructor hay factory**.
5. `constructor: DirectMessage` xuất hiện ngay khi provider đầu được yêu cầu qua `get()`.
6. `factory: provider()` xuất hiện khi provider thứ hai được yêu cầu qua `get()`; factory trả instance của class package-private `PrivateMessage`.
7. Cả hai trả lời thành công qua cùng interface: `Hello, Java` và `Hi, Java`.

**Về thứ tự:** trong ví dụ mỗi provider thuộc **cùng một module** và được liệt kê theo thứ tự `DirectMessage, FactoryMessage`, nên `ServiceLoader` lấy chúng theo thứ tự descriptor. Không áp đặt thứ tự này lên các provider từ **nhiều module** khác nhau, vì API không cam kết thứ tự giữa các module/layer. Với hệ thống cần ưu tiên rõ ràng, hãy định nghĩa priority hoặc metadata riêng thay vì dựa vào thứ tự phát hiện.

## 6. Vòng đời khám phá, metadata và khởi tạo trễ

`ServiceLoader` có hai cách tiêu thụ tiêu biểu:

~~~java
ServiceLoader<MessageService> loader =
        ServiceLoader.load(MessageService.class);

// Duyệt instance: phần tử được lấy là MessageService.
for (MessageService service : loader) {
    // service đã được khởi tạo khi iterator trả phần tử.
}

// Duyệt provider handles: lấy metadata trước, gọi get() khi cần.
loader.stream().forEach(provider -> {
    Class<? extends MessageService> type = provider.type();
    // provider.get() mới yêu cầu tạo instance.
});
~~~

Đây là **đoạn minh họa các API**, giả định `MessageService` đã tồn tại và module có `uses`. Nó không phải chương trình Java độc lập.

| Thao tác | Mục đích | Hệ quả nên dự kiến |
| --- | --- | --- |
| `ServiceLoader.load(Service.class)` | Tạo đối tượng tìm provider theo context loader / module graph | Chưa đồng nghĩa đã instantiate tất cả providers |
| `iterator().next()` | Lấy service instance | Có thể thực thi constructor hoặc factory; kết quả được cache theo hành vi iterator của `ServiceLoader` |
| `stream().toList()` | Thu thập provider handles/metadata | Không cần gọi `provider.get()` chỉ để lấy type metadata |
| `Provider.type()` | Trả declared provider type | Với factory là return type khai báo của `provider()` |
| `Provider.get()` | Lấy instance qua đúng con đường tạo | Có thể thực thi mã tùy biến, lỗi, tạo tài nguyên và side effect |
| `ServiceLoader.reload()` | Xóa provider cache của đối tượng loader | Lần duyệt sau khám phá lại; không tự đóng instance hoặc unload module |

**Phân biệt cache:** khi duyệt qua `iterator`, `ServiceLoader` cache các provider instance mà nó đã khởi tạo để phục vụ các vòng duyệt của cùng loader, trừ khi `reload()`. Với `stream()`, loader cache các provider đã phát hiện ở mức provider handles; **không nên dựa vào giả định gọi `Provider.get()` nhiều lần luôn trả về cùng instance**. Nếu cần singleton có chủ đích, factory và host phải cùng có hợp đồng rõ ràng về ownership/lifecycle.

Việc thực hiện `get()` có thể gây I/O, mở kết nối hoặc lỗi khởi tạo theo cách provider lập trình. Vì vậy, duyệt metadata trước khi chọn provider có thể giảm khởi tạo không cần thiết, nhưng bộ chọn phải hiểu rằng `type()` của factory có thể chỉ là service interface, không tiết lộ implementation class.

## 7. Constructor và provider method với classpath, automatic module và explicit named module

Ba cách đóng gói **khác nhau về quy tắc khởi tạo**:

| Môi trường triển khai | Khai báo đăng ký | Constructor | `public static provider()` |
| --- | --- | --- | --- |
| **Explicit named module** có `module-info.java` | `provides Service with ProviderClass;` | Có | **Có** |
| **Automatic module** (JAR không có descriptor đầy đủ, ở module path) | Có thể suy từ cấu hình provider trong JAR | Có | **Không hỗ trợ** |
| **Classpath/unnamed module** | `META-INF/services/<binary service name>` | Có | **Không hỗ trợ** |

Ví dụ cấu hình classpath:

~~~text
META-INF/services/lesson.spi.MessageService
~~~

Nội dung của file đó có thể là:

~~~text
lesson.providers.DirectMessage
~~~

File này phải mã hóa UTF-8, tên là **binary name đầy đủ của service**, còn mỗi dòng dữ liệu xác định **binary name của provider class**, có thể kèm comment bắt đầu bằng `#`.

Cấu hình classpath trên hợp lệ nếu `DirectMessage` là subtype của `MessageService` và có public constructor không tham số. **Không** thể chỉ đổi thành:

~~~text
lesson.providers.FactoryMessage
~~~

rồi kỳ vọng `ServiceLoader` ở classpath tự gọi `FactoryMessage.provider()`. Khi provider được khai báo theo classpath hoặc automatic module, cơ chế provider method không hoạt động; class factory trong ví dụ không implements service và có constructor private nên không đáp ứng điều kiện constructor provider.

Do đó, khi chuyển một hệ thống từ classpath sang JPMS hoặc ngược lại, cần kiểm tra lại **kiểu provider**, **cơ chế tạo instance**, **metadata đăng ký** và **module graph**. Có method tên `provider` không đồng nghĩa `ServiceLoader` sẽ phát hiện method đó ở mọi môi trường.

## 8. Điều kiện compile-time và lỗi runtime

### 8.1. Các ràng buộc trong module-info.java

Theo Java Language Specification `7.7.4, khi dùng `provides S with P`:

- `P` là provider được khai báo trong **chính module**; không lấy provider class nằm trong module khác rồi liệt kê trực tiếp.
- Provider phải là kiểu **public top-level hoặc public static member**, không phải inner class không static.
- Nếu có provider method, **return type khai báo** phải accessible và là subtype của service; class factory có thể không phải subtype của service.
- Nếu không có provider method, provider class phải là subtype của service và có provider constructor công khai không tham số.
- Không liệt kê cùng provider hai lần trong một `with` và không khai báo trùng dịch vụ bằng nhiều `provides` trong cùng module.

Những vi phạm có thể bị compiler phát hiện khi xây dựng explicit named module. Đối với metadata/JAR đã bị sửa, bytecode ngoài quy ước Java nguồn hoặc các sai sót xuất hiện lúc runtime, `ServiceLoader` có thể phát sinh `ServiceConfigurationError`.

### 8.2. Những cấu hình lỗi thường gặp

**Sai 1: constructor có tham số, không có provider method.**

~~~java
// Minh họa sai cho constructor provider:
public DirectMessage(Config config) { /* ... */ }
~~~

Constructor này không được `ServiceLoader` gọi kèm `Config`. Cần có public constructor không tham số hợp lệ, hoặc chuyển sang factory trong explicit named module.

**Sai 2: provider method có tham số hoặc không public/static.**

~~~java
// Minh họa sai, không phải provider method hợp lệ:
private MessageService provider() { /* ... */ return null; }
public static MessageService provider(Config config) { /* ... */ return null; }
~~~

`ServiceLoader` không tự động “đoán” lời gọi factory; nếu còn thiếu constructor hợp lệ, provider không hợp lệ. Các dòng trên chỉ minh họa chữ ký sai, không phải một chương trình Java runnable.

**Sai 3: factory trả `null` hoặc ném lỗi.**

~~~java
public static MessageService provider() {
    return null; // Provider.get() sẽ thất bại.
}
~~~

Đây là phương thức minh họa hành vi lỗi, không dùng làm triển khai thật. Khi `ServiceLoader` gọi factory và nhận `null` (hoặc exception), nó báo `ServiceConfigurationError`; phần khởi tạo có thể đã mở tài nguyên trước khi lỗi xảy ra, nên provider phải tự cleanup khi thất bại.

**Sai 4: provider chưa được resolve lúc chạy.**

Có file module trên module path không nhất thiết đồng nghĩa module đó đã nằm trong graph resolved đang được dùng cho ứng dụng. Kiểm tra `--module-path`, root modules, `--add-modules` (nếu phù hợp) hoặc cơ chế service binding/ModuleLayer. Không thêm `requires providerModule` vào consumer chỉ để né vấn đề cấu hình nếu kiến trúc cần giữ phụ thuộc vào SPI.

**Sai 5: service type bị nhân đôi giữa các loader.**

Provider implements một bản interface được nạp từ loader khác với `MessageService.class` mà consumer dùng. Lúc kiểm tra subtype có thể thất bại dù binary name giống nhau. SPI interface, DTO và exception công khai nên nằm ở vùng API chung do host và plugin cùng nhìn thấy.

### 8.3. Tìm lỗi ở bước nào?

- `javac` có thể báo lỗi ngay ở `module-info.java` khi chữ ký provider không thỏa ràng buộc source-level.
- `ServiceLoader.load(...)` dựng một loader nhưng discovery có tính lazy; nhiều lỗi chỉ xuất hiện lúc xử lý `iterator` hoặc `stream`.
- Với iterator, `hasNext()`/`next()` có thể báo `ServiceConfigurationError` khi nạp hoặc instantiate provider.
- Với stream, lỗi có thể xuất hiện khi một terminal operation thực sự tìm/nạp provider; `Provider.get()` còn có thể báo lỗi riêng khi gọi constructor hoặc factory.
- `ServiceConfigurationError` là một `Error`, **không** phải exception checked. Host cần xác định chính sách bỏ provider lỗi hay fail-fast, logging nguyên nhân phù hợp và không che lỗi cấu hình bằng một catch tổng quát rồi im lặng.

Một lỗi của factory không chứng minh SPI interface sai; hãy kiểm tra stack trace và nguyên nhân gốc trong constructor, factory, classloading hoặc module resolution.

## 9. Chọn cơ chế theo nhu cầu và trách nhiệm vận hành

**Ưu tiên constructor** khi bạn cần một implementation trực tiếp, có public no-arg constructor, không cần chọn subclass runtime hay giấu chi tiết tạo instance. Đây cũng là lựa chọn cần thiết nếu phải giữ khả năng triển khai trên classpath/automatic module theo ServiceLoader mặc định.

**Ưu tiên provider()** nếu muốn module chứa provider quyết định cách tạo instance mà không công bố implementation, ví dụ:

- Chọn implementation nội bộ theo môi trường đã được xác thực.
- Trả decorator/proxy tương thích với service.
- Khởi tạo cache hoặc phụ thuộc phức tạp bên trong factory một cách có kiểm soát.
- Giữ class implementation package-private và tránh tạo public constructor chỉ phục vụ discovery.

Nhưng factory vẫn có những giới hạn rõ ràng:

- Method **không có tham số**: host không thể đưa thẳng `Config` hoặc `Executor` như tham số factory SPI. Nếu cần truyền context, nên thiết kế API khởi tạo/cấu hình riêng, dependency container riêng hoặc hợp đồng extension context đúng scope.
- Factory có thể trả kiểu rộng như `MessageService`; `Provider.type()` khi đó không cho biết implementation runtime, nên bộ lọc dựa trên class name/annotation của implementation có thể sai.
- Cần công bố **quy tắc instance scope**: mỗi lần gọi tạo instance mới hay tái sử dụng, ai đóng, có cho gọi đồng thời không, và phải làm gì khi factory thất bại.
- Mỗi provider được đăng ký là extension point có thể thất bại độc lập; host cần chính sách cách ly lỗi và fallback nhất quán.

### Bảng checklist thiết kế

| Câu hỏi cần trả lời | Constructor path | Factory path |
| --- | --- | --- |
| Instance có cần public implementation class không? | Provider class phải public | Instance class có thể không public |
| Cần tùy biến cách chọn implementation lúc tạo? | Tính linh hoạt hạn chế | Factory được quyền chọn implementation tương thích |
| Có yêu cầu deploy trên classpath hoặc automatic module? | Thích hợp | Không dùng provider method trong các chế độ đó |
| Có cần đọc metadata trước khi instantiate? | `Provider.type()` là implementation class | `Provider.type()` có thể chỉ là return interface |
| Có yêu cầu quản lý tài nguyên/singleton? | Cần hợp đồng riêng | Cũng cần hợp đồng riêng |
| Có cần DI/context đầu vào? | Không có constructor injection tự động | Không có tham số factory tự động |
| Class provider có thể ẩn sau constructor private? | Không | Có |

## 10. Kiểm thử một extension point có hai cơ chế

Một bộ kiểm thử hợp đồng hữu ích nên bao gồm các trường hợp:

1. **Discovery**: module consumer có `uses`, module provider có `provides`, module graph thực tế đã resolve; số lượng provider được tìm là số lượng mong muốn trong fixture.
2. **Constructor route**: class implements service, public no-arg constructor được gọi **khi cần instance**, `Provider.type()` chính là class provider.
3. **Factory route**: provider class không implements service, có private constructor và public static `provider()` hợp lệ; `get()` vẫn trả instance dùng được qua service API.
4. **Metadata and laziness**: thao tác `stream().map(Provider::type)` không tự gọi `get()`; số lần constructor/factory chạy được đo bằng counter/log để tránh dựa vào suy đoán.
5. **Invalid signatures**: provider không có constructor hợp lệ, factory không public/static/không tham số hoặc return type không tương thích; phân biệt compile-time validation với lỗi runtime.
6. **Factory failure**: factory ném exception hoặc trả null; host nhận và ghi lại `ServiceConfigurationError` có nguyên nhân.
7. **Lifetime**: nếu provider giữ socket, thread, listener hoặc file, có cơ chế cleanup riêng; `ServiceLoader.reload()` không thay host đóng các tài nguyên đó.
8. **Concurrency**: không dùng chung một đối tượng `ServiceLoader` từ nhiều thread tùy ý vì bản thân nó **không thread-safe**; kiểm thử độc lập thread safety của instance do constructor/factory cung cấp.
9. **Compatibility**: kiểm tra classpath/automatic module vẫn dùng provider constructor; không dựa vào factory method khi chuyển packaging.
10. **Ordering**: không dựa vào thứ tự module tùy ý để quyết định provider ưu tiên; nếu cần một provider cụ thể, lọc theo metadata được công bố.

Việc kiểm thử cả hai con đường còn có ích khi nâng cấp Java hoặc thay classloader: host phải luôn nhận một đối tượng gán được cho **đúng service `Class` chung**, không chỉ một object có tên interface giống nhau nhưng được loader khác định nghĩa.

## 11. Tổng kết quy tắc cần nhớ

~~~text
Explicit named module:
    provides S with P
          |
          +-- P có public static S_or_Subtype provider()?
          |       |
          |       +-- CÓ -> ServiceLoader gọi provider()
          |                     P không cần implements S
          |                     P không cần public no-arg constructor
          |
          +-- KHÔNG -> P phải implements/extends S
                         và có public no-arg constructor

Automatic module / classpath provider:
    dùng provider constructor
    không hỗ trợ provider method

ServiceLoader.Provider<S>.type():
    constructor path -> provider implementation class
    factory path     -> declared return type của provider()
ServiceLoader.Provider<S>.get():
    yêu cầu tạo/trả service instance theo cơ chế tương ứng
~~~

**Điểm quyết định:** lựa chọn constructor hay `public static provider()` là **một phần của hợp đồng đóng gói provider trong JPMS**, không phải hai tên gọi tương đương. Với constructor, provider class chính là subtype của service; với factory, provider class là nơi tạo ra subtype của service. Cả hai cùng giao tiếp với consumer bằng một service API chung.

### Tài liệu tham khảo chính thức

- [ServiceLoader – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): quy tắc provider constructor, provider method, module/classpath, discovery và lỗi.
- [ServiceLoader.Provider – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html): ngữ nghĩa `type()` và `get()`.
- [Java Language Specification 17, `7.7.4 Service Provision](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4): điều kiện compile-time của `provides ... with ...`.
- [JPMS module descriptor – java.lang.module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html): khai báo `uses` và `provides` trong module graph.
