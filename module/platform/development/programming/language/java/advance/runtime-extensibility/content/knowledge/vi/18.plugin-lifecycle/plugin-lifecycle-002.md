# Xác định bước nào thuộc ServiceLoader và bước nào do ứng dụng chủ quản lý

## 1. Tách hai trách nhiệm: tìm provider và vận hành plugin

Một hệ thống mở rộng Java thường có hai thành phần cùng xuất hiện nhưng đảm nhiệm những việc rất khác nhau:

- **ServiceLoader** là cơ chế chuẩn trong JDK để *tìm các service provider đã được khai báo*, nạp và cung cấp instance theo nhu cầu, duy trì cache trong phạm vi một đối tượng ServiceLoader và cho phép xóa cache tìm kiếm.
- **Ứng dụng chủ (host/plugin manager)** là phần chịu trách nhiệm quyết định *plugin nào được phép cài, được kích hoạt, xử lý tác vụ, giám sát, dừng, cập nhật, thu hồi hoặc rollback*. Các quyết định này thuộc nghiệp vụ và chính sách vận hành, không được JDK tự xây dựng.

Ví dụ host cần một interface **Plugin** và hai nhà cung cấp triển khai. ServiceLoader giúp host biết có những provider hợp lệ nào theo metadata mà nó có thể nhìn thấy, và tạo đối tượng. **ServiceLoader không chọn provider nào phù hợp với yêu cầu khách hàng, không gọi start(), không giám sát trạng thái HEALTHY và không gọi stop() khi dừng ứng dụng.** Nếu hợp đồng Plugin định nghĩa các phương thức đó, host là bên điều phối.

Câu hỏi trung tâm của bài: **bước nào được JDK xử lý tự động theo hợp đồng ServiceLoader, và bước nào bắt buộc do host thiết kế?**

Phân biệt này tránh một lỗi kiến trúc nghiêm trọng: xem ServiceLoader như một plugin platform có quản lý vòng đời đầy đủ. Thực tế nó chỉ là **một thành phần discovery/instantiation** trong plugin platform.

## 2. Bảng phân quyền: ServiceLoader hay host?

| Bước trong vòng đời | ServiceLoader cung cấp | Host phải quản lý |
| --- | --- | --- |
| Nhận file JAR/source/plugin package | Không | Kiểm tra nguồn gốc, quyền, version, policy và lưu artifact |
| Cài đặt, gỡ cài đặt, cập nhật artifact | Không | Quản lý vị trí, class loader/module layer, dependency, metadata |
| Khai báo provider | Đọc theo SPI registration | Nhà phát triển/provider phát hành META-INF/services hoặc provides; host bảo đảm được triển khai đúng |
| Tìm các provider mà loader/layer nhìn thấy | Có | Chọn đúng class loader/layer và phạm vi plugin |
| Parse cấu hình service, đọc provider metadata | Có | Kiểm tra chính sách khai báo, tránh nguồn không được tin cậy |
| Kiểm tra điều kiện provider cơ bản | Có khi locate/load/instantiate | Kiểm tra compatibility **ngữ nghĩa**, version, quyền, năng lực |
| Nạp class và tạo provider object | Có, **lazily** khi API yêu cầu | Quyết định khi nào yêu cầu, cách sử dụng và xử lý lỗi |
| Duy trì cache provider trong một ServiceLoader | Có | Quản lý lifetime của ServiceLoader và mọi instance host giữ lại |
| Xóa cache của ServiceLoader | Có: **reload()** | Quyết định thời điểm, đồng bộ luồng và có cần nạp artifact/loader mới không |
| Liệt kê provider trước khi tạo instance | Có thể dùng **stream()** và Provider.type() | Chọn/filt theo metadata, version, priority hoặc policy riêng |
| Chọn provider cho tenant hoặc chức năng | Không | Quy tắc lựa chọn, xung đột, fallback, thứ tự ưu tiên |
| Cấu hình dependency/credentials | Không | Chỉ cung cấp dữ liệu/quyền cần thiết qua interface/config |
| Gọi init()/start()/activate() | Không | Điều phối khởi tạo tài nguyên, readiness và trạng thái |
| Gọi method nghiệp vụ | Không | Host/service consumer sử dụng provider qua SPI |
| Health check, timeout, retry, circuit breaker | Không | Chính sách đo lường, bảo vệ và cô lập lỗi |
| Dừng tác vụ, drain request và stop()/close() | Không | Host quản lý shutdown có thứ tự và thu hồi tài nguyên |
| Unload class/plugin, đóng URLClassLoader | Không | Host xử lý tham chiếu, loader, thread, cache, rollback |
| Ghi log, audit, metrics, tracing | Không có chính sách platform | Host gắn plugin ID/version và vận hành |
| Đảm bảo code plugin an toàn | Không | Trust boundary, kiểm soát quyền và cách ly tiến trình |

**Mẹo nhận diện:** một bước có dạng “**tìm class/provider từ đăng ký SPI**” thuộc khả năng ServiceLoader; một bước có dạng “**quyết định có được phép dùng hay quản lý trạng thái của plugin này**” thuộc host. Có một số điểm giao nhau: ServiceLoader có thể tạo instance, nhưng **host quyết định khi nào yêu cầu tạo và phải làm gì với instance sau đó**.

## 3. Mô hình các giai đoạn của một plugin

~~~text
Đội phát triển/provider             Host / Plugin Manager                   ServiceLoader
          |                                  |                                   |
Viết implementation + descriptor            |                                   |
          |                                  |                                   |
Xuất bản plugin.jar  ----------------------> |                                   |
                                             | Verify artifact / dependency       |
                                             | Chọn loader hoặc ModuleLayer       |
                                             | Tạo ServiceLoader ---------------->|
                                             |                                   | Locate metadata (lazy)
                                             | Iterator / stream --------------->|
                                             |                                   | Load type
                                             |                                   | Create instance khi được yêu cầu
                                             | <---------------- Provider -------|
                                             | Validate ID / version / policy    |
                                             | Select / configure / start        |
                                             | Serve requests, monitor, retry    |
                                             | Drain / stop / release resources  |
                                             | Lập kế hoạch update/rollback      |
                                             | Tạo loader/layer mới nếu cần       |
                                             | reload cache tùy kịch bản ------->| Clear own cache
                                             | Đóng loader cũ khi an toàn         |
~~~

Đây là **sơ đồ trách nhiệm**, không phải trình tự cứng áp dụng cho mọi framework. Một host có thể load provider để kiểm tra metadata trước rồi mới chọn; hệ thống khác có thể kiểm tra thông tin JAR trước khi tạo class loader. Điều không đổi là **ServiceLoader không có các API install, activate, health, deactivate hoặc uninstall**.

Một mô hình trạng thái host thường tự định nghĩa:

~~~text
DISCOVERED
    |
    v
VERIFIED ----> REJECTED (artifact/contract không hợp lệ)
    |
    v
SELECTED
    |
    v
STARTING ----> FAILED (nếu init/start lỗi)
    |
    v
ACTIVE -----> DEGRADED (health kém)
    |
    v
DRAINING
    |
    v
STOPPING
    |
    v
STOPPED
    |
    v
RETIRED (tham chiếu, loader và resource đã được quản lý)
~~~

ServiceLoader **không lưu các trạng thái này**. Nó không biết một provider đang ACTIVE hay đã STOPPED. Có instance trong cache cũng **không có nghĩa plugin đó đã được host kích hoạt**.

## 4. Chính xác ServiceLoader làm được gì?

### 4.1. Tìm nhà cung cấp đã đăng ký

Một provider được công bố theo hai mô hình chính:

- **Classpath/unnamed module:** file văn bản **META-INF/services/<tên nhị phân của SPI>** trong JAR hoặc thư mục classpath. Nội dung là tên lớp provider, mỗi dòng một tên. Ví dụ **META-INF/services/demo.api.Plugin** chứa **demo.provider.UpperPlugin**.
- **Explicit named module của JPMS:** file **module-info.java** của module provider có **provides demo.api.Plugin with demo.provider.UpperPlugin;**. Module tiêu thụ có **uses demo.api.Plugin;** ở nơi gọi ServiceLoader, cùng các requires/exports cần thiết cho API.

ServiceLoader tra cứu các provider **mà class loader hoặc module layer được cấu hình có thể nhìn thấy**. Việc một JAR có mặt trên đĩa **không tự khiến ServiceLoader phát hiện JAR đó** nếu nó không nằm trong đường nạp của loader/layer phù hợp.

Class provider trên classpath thường phải là một class public, gán được cho service type và có public constructor không tham số. Với explicit named module, còn có cơ chế **public static provider()** hợp lệ cho kiểu factory. Đây là điều kiện **đăng ký/khởi tạo provider**, không phải toàn bộ tiêu chuẩn chất lượng plugin.

### 4.2. Tạo provider theo nhu cầu

Một lời gọi:

~~~java
// Mảnh minh họa trong host: Plugin là SPI được công bố.
ServiceLoader<Plugin> loader = ServiceLoader.load(Plugin.class);
~~~

**Không có nghĩa tất cả constructor provider lập tức chạy.** ServiceLoader tìm và tạo provider lazily khi iteration hoặc một API yêu cầu provider cụ thể được thực hiện. Trong luồng dùng **iterator()**, **hasNext()** và **next()** có thể thực hiện công việc tìm/nạp nên cũng có thể ném **ServiceConfigurationError**. Các lỗi này không nhất thiết xuất hiện ở dòng tạo đối tượng ServiceLoader.

Duyệt các provider:

~~~java
// Mảnh minh họa trong host có Plugin và loader hợp lệ.
for (Plugin candidate : loader) {
    System.out.println(candidate.id());
}
~~~

Khi cần **chỉ xem kiểu provider trước khi tạo object**, có thể dùng:

~~~java
// Mảnh minh họa trong host có Plugin và loader hợp lệ.
loader.stream()
      .map(ServiceLoader.Provider::type)
      .forEach(System.out::println);
~~~

**Provider.type()** có thể giúp lọc provider theo metadata/type mà chưa gọi constructor provider. Nhưng với named-module provider factory, type có thể là **kiểu trả về của provider()**, không nhất thiết là tên class factory trong provides. Khi gọi **Provider.get()**, provider mới được cung cấp theo quy tắc engine/provider; không xem việc gọi type() là một phép kiểm tra sức khỏe hoặc một cam kết về các side effect khi sau này tạo instance.

### 4.3. Cache provider đã duyệt

Một đối tượng **ServiceLoader** ghi nhớ các provider được nạp/khởi tạo theo quy tắc API. Với iterator, các lần duyệt sau trước hết trả những **instance đã được cache**, rồi mới lazily tìm và khởi tạo thêm provider chưa có.

Điều này hữu ích để tránh tạo lại provider ở mỗi vòng lặp, nhưng cũng gây nhầm lẫn:

- Cache không đại diện cho trạng thái RUNNING/STOPPED do host quản lý.
- Host có thể giữ reference tới một instance đã ngừng hoạt động, dù ServiceLoader vẫn cache nó.
- Không được giả định duyệt lại sẽ tự thấy JAR mới đặt vào một thư mục chưa được loader quan sát.
- Không dùng một ServiceLoader toàn JVM cho nhiều tenant/layer mà không xét class loader và phạm vi dữ liệu.

Với Stream API, ServiceLoader cũng có quy tắc cache riêng; không nên đồng nhất một lời gọi **Provider.get()** với “cùng một singleton do host đã start”. Hãy quản lý instance được chọn theo hợp đồng của host.

### 4.4. reload() chỉ xóa cache của ServiceLoader

~~~java
// Mảnh minh họa: loader là ServiceLoader<Plugin>.
loader.reload();
~~~

**reload()** xóa cache provider của **đối tượng ServiceLoader đó**, khiến lần tra cứu/duyệt tiếp theo tìm provider từ đầu theo đường nạp mà nó đang sử dụng. Nó **không**:

- Tải một file JAR mới từ Internet hoặc tự sửa application classpath.
- Cập nhật trực tiếp class definition đã được JVM load.
- Khởi tạo hoặc gọi start() cho tất cả provider mới.
- Gọi stop(), close(), dispose() trên các object cũ.
- Ngắt các thread do plugin tạo hay xóa cache của application.
- Đóng URLClassLoader, gỡ ModuleLayer hoặc bảo đảm class unloading.
- Chuyển request đang chạy sang phiên bản mới hoặc tự rollback nếu bản mới lỗi.

Nếu host vẫn giữ **Plugin old** thì old vẫn là một object bình thường sau **reload()**. Nếu cùng class loader đã nạp class provider, một instance mới thường vẫn là **cùng phiên bản class definition**, chứ không tự biến thành bytecode mới trên đĩa.

**Chú ý với iterator/stream cũ:** khi gọi reload(), các iterator/stream đã được lấy trước đó phải được bỏ. Theo Java 17, việc sử dụng chúng sau khi cache bị clear có thể dẫn đến **ConcurrentModificationException**. Đó là lý do host cần điều phối reload và lookup nhất quán.

### 4.5. Báo lỗi cấu hình SPI, không thay host xử lý sự cố

Các lỗi cấu hình/tạo provider có thể xuất hiện dưới dạng **ServiceConfigurationError** (đây là subclass của **Error**, không phải checked exception):

- File META-INF/services sai format hoặc đọc lỗi.
- Tên class provider không tồn tại hay không nhìn thấy qua loader.
- Provider class không phù hợp với SPI hoặc thiếu điều kiện constructor/provider method.
- Constructor hoặc provider method ném lỗi.
- Lỗi liên kết dependency khiến provider không được nạp hoặc khởi tạo.

ServiceLoader **báo lỗi**, không biết liệu host nên dừng hệ thống, cô lập plugin lỗi, dùng provider thay thế, đưa vào quarantine hay cần rollback. Các quyết định này phải được host thiết kế.

## 5. Những việc host bắt buộc quản lý

### 5.1. Cài đặt, xác thực và lựa chọn plugin

Host quản lý nguồn artifact, version, checksum, chữ ký nếu có, quyền của publisher, mức tương thích API, dependency cần thiết và chính sách cấp quyền. **ServiceLoader chỉ thấy provider đã được đăng ký theo đường nạp của nó**, không xác minh chữ ký hay đánh giá độ tin cậy kinh doanh.

Khi có nhiều provider, host cần chính sách chọn:
- Lựa chọn tường minh theo **plugin ID**, version và capability.
- Loại provider không tương thích contract, schema hoặc quyền.
- Độ ưu tiên đã được định nghĩa riêng trong metadata/registry, không phụ thuộc tình cờ vào thứ tự JAR.
- Fallback rõ ràng khi không có provider đạt yêu cầu.
- Tách lựa chọn toàn hệ thống và lựa chọn theo tenant nếu có nhiều tenant.

**findFirst() không đồng nghĩa “provider tốt nhất”.** Thứ tự provider có thể phụ thuộc discovery/classloader/module graph; nó không phải ranking nghiệp vụ.

### 5.2. Kích hoạt/khởi động và thực hiện công việc

Nếu interface SPI có các phương thức:

~~~java
// Mảnh minh họa hợp đồng, trích ý tưởng từ ví dụ đầy đủ bên dưới.
void start();
String handle(String input);
void stop();
~~~

Thì **host** phải gọi chúng. ServiceLoader không biết chữ ký hoặc ý nghĩa của các method do ứng dụng tự đặt. Nó chỉ cần đối tượng là provider hợp lệ của interface/service tương ứng.

Một plugin có thể:
- Tạo connection pool, thread, scheduler hoặc cache khi start().
- Đăng ký callback với host.
- Đọc config được host cấp và kiểm tra readiness.
- Xử lý nhiều request khi ACTIVE.
- Xả công việc dang dở, đóng connection, hủy callback trong stop().

Host cần biết **lúc nào**, **bao nhiêu lần**, **ở luồng nào** và **thứ tự nào** để gọi từng bước. Nên định nghĩa semantics rõ: start() được gọi tối đa một lần trên mỗi activation hay idempotent? Stop() có được gọi sau start() lỗi một phần? Có thể restart cùng instance không? Đây đều là câu hỏi của **hợp đồng host**, không phải JDK ServiceLoader.

### 5.3. Giám sát, phục hồi và ngừng hoạt động

Host quyết định health checks, readiness, metrics, logging, tracing, timeout, retry, backpressure và circuit breaker. Nếu plugin ném exception khi handle(), ServiceLoader không tự đưa provider ra khỏi registry hay gọi stop().

Với ứng dụng phục vụ request đồng thời:
1. Host theo dõi số request đang dùng plugin.
2. Khi thay bản mới, ngăn phát sinh request mới với bản cũ.
3. Chờ hoặc hủy theo chính sách những request đang chạy.
4. Gọi stop()/close() thích hợp và kiểm tra tài nguyên được trả lại.
5. Chỉ sau đó mới cân nhắc đóng loader và bỏ toàn bộ reference.

Một provider mới được phát hiện không được tự trở thành ACTIVE trước khi vượt qua các bước validation/readiness do host yêu cầu.

## 6. Ví dụ Java 17 hoàn chỉnh: thấy rõ ranh giới trách nhiệm

Ví dụ dùng **một SPI và một provider trong JAR riêng**, không phụ thuộc thư viện ngoài. Provider có constructor ghi ra màn hình **chỉ nhằm minh họa khi nào ServiceLoader tạo object**; trong sản phẩm thực tế, constructor nên nhẹ và tránh side effect nặng.

Bài kiểm tra được bốn hành vi:
1. Chỉ tạo ServiceLoader chưa làm constructor chạy.
2. Khi host duyệt provider, ServiceLoader tạo instance.
3. Host tự chọn, start(), handle() và stop().
4. Cache khiến lần duyệt sau trả cùng instance; reload() xóa cache nhưng **không khởi động provider**.

### 6.1. Cấu trúc thư mục

~~~text
demo/
├── src/
│   └── demo/
│       ├── api/Plugin.java
│       ├── provider/UpperPlugin.java
│       └── app/Main.java
├── resources/
│   └── META-INF/services/demo.api.Plugin
├── out/
│   ├── host/                  # Sinh bởi javac
│   └── provider/              # Sinh bởi javac, kèm descriptor
└── plugin.jar                 # Sinh bởi jar
~~~

Host được compile **không cần class UpperPlugin trên compile classpath**. SPI và Main được đưa vào out/host; provider được compile riêng theo API rồi đóng gói vào plugin.jar. Khi chạy, descriptor trong JAR giúp ServiceLoader tìm thấy provider.

### 6.2. API chung của host

**src/demo/api/Plugin.java**

~~~java
package demo.api;

public interface Plugin {
    String id();
    void start();
    String handle(String input);
    void stop();
}
~~~

Đây là **hợp đồng ứng dụng**. Các phương thức **id/start/handle/stop** do host và nhà phát triển plugin thống nhất; Java ServiceLoader không đặt ra những phương thức này. Ở hệ thống lớn, có thể mở rộng hợp đồng bằng metadata, semantic version và health check, nhưng không gắn những ý nghĩa đó vào API ServiceLoader.

### 6.3. Provider: class hợp lệ và hành vi cụ thể

**src/demo/provider/UpperPlugin.java**

~~~java
package demo.provider;

import demo.api.Plugin;
import java.util.Locale;

public final class UpperPlugin implements Plugin {
    public UpperPlugin() {
        System.out.println("Provider: constructor");
    }

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public void start() {
        System.out.println("Provider: start");
    }

    @Override
    public String handle(String input) {
        return input.toUpperCase(Locale.ROOT);
    }

    @Override
    public void stop() {
        System.out.println("Provider: stop");
    }
}
~~~

Provider implements đúng interface **demo.api.Plugin**, là public class và có public no-arg constructor. Constructor ghi **Provider: constructor** để xác định lúc object được tạo. **start()** và **stop()** ghi log riêng để phân biệt **khởi tạo Java object** với **kích hoạt tài nguyên plugin**; hành vi handle() chuyển input thành chữ hoa.

Descriptor **resources/META-INF/services/demo.api.Plugin** chỉ có một dòng:

~~~text
demo.provider.UpperPlugin
~~~

Đây là một **tên nhị phân class**, không phải lệnh start plugin. ServiceLoader sẽ dùng đăng ký đó để locate và khởi tạo provider khi được yêu cầu.

### 6.4. Host dùng ServiceLoader nhưng nắm vòng đời

**src/demo/app/Main.java**

~~~java
package demo.app;

import demo.api.Plugin;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Plugin> loader =
                ServiceLoader.load(Plugin.class, Plugin.class.getClassLoader());
        System.out.println("Host: ServiceLoader created");

        Plugin selected = null;
        for (Plugin candidate : loader) {
            if ("upper".equals(candidate.id())) {
                selected = candidate;
                break;
            }
        }
        if (selected == null) {
            throw new IllegalStateException("Required provider not found");
        }
        System.out.println("Host: selected " + selected.id());
        System.out.println("Host: cached same instance: " +
                (loader.iterator().next() == selected));

        boolean started = false;
        try {
            System.out.println("Host: starting");
            selected.start();
            started = true;
            System.out.println("Host: result " + selected.handle("hello"));
        } finally {
            if (started) {
                System.out.println("Host: stopping");
                selected.stop();
            }
        }

        System.out.println("Host: clearing ServiceLoader cache");
        loader.reload();
        Plugin fresh = loader.iterator().next();
        System.out.println("Host: new instance after reload: " +
                (fresh != selected));
    }
}
~~~

Các điểm đáng quan sát:

- **ServiceLoader.load(Plugin.class, Plugin.class.getClassLoader())** dùng loader hiện nhìn thấy SPI để khám phá provider. Lựa chọn class loader này được host đưa ra rõ ràng; ứng dụng plugin phức tạp có thể cần một loader khác.
- Sau dòng **Host: ServiceLoader created** chưa xuất hiện **Provider: constructor**. Vì ServiceLoader lazy nên chưa có vòng đời ACTIVE.
- **for (Plugin candidate : loader)** yêu cầu provider. ServiceLoader mới tạo instance và bổ sung cache; **host** so sánh **candidate.id()** để chọn.
- **loader.iterator().next() == selected** minh họa provider instance đã được cache, không bị tạo lại trong lượt duyệt đó.
- **Host: starting** rồi **selected.start()** là **lệnh do host gọi**, hoàn toàn ngoài ServiceLoader.
- **Host: result HELLO** đến từ **selected.handle("hello")**, tương tự.
- **Host: stopping** rồi **selected.stop()** do host gọi trong finally sau khi start thành công.
- **loader.reload()** khiến vòng duyệt sau tạo instance mới, nhưng **không có lời gọi start() nào** cho instance mới đó.

**Giới hạn có chủ đích:** ví dụ chỉ có một provider và không triển khai audit, isolation, hot swap thật, health checks hoặc lựa chọn giữa nhiều phiên bản. Phần xử lý failure khi start() chỉ là mô hình đơn giản; production cần quy định cleanup cả khi start() đã cấp phát một phần tài nguyên rồi ném lỗi.

### 6.5. Biên dịch, đóng gói và chạy

Đứng trong thư mục **demo/** và đã tạo các file theo cấu trúc ở trên.

**Linux/macOS (bash):**

~~~bash
mkdir -p out/host out/provider out/provider/META-INF/services

javac --release 17 -d out/host \
  src/demo/api/Plugin.java src/demo/app/Main.java

javac --release 17 -cp out/host -d out/provider \
  src/demo/provider/UpperPlugin.java

cp resources/META-INF/services/demo.api.Plugin \
  out/provider/META-INF/services/demo.api.Plugin

jar --create --file plugin.jar -C out/provider .

java -cp "out/host:plugin.jar" demo.app.Main
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out/host,out/provider,out/provider/META-INF/services | Out-Null

javac --release 17 -d out/host src/demo/api/Plugin.java src/demo/app/Main.java

javac --release 17 -cp out/host -d out/provider src/demo/provider/UpperPlugin.java

Copy-Item resources/META-INF/services/demo.api.Plugin out/provider/META-INF/services/demo.api.Plugin

jar --create --file plugin.jar -C out/provider .

java -cp "out/host;plugin.jar" demo.app.Main
~~~

Đối với lệnh **java -cp**, Linux/macOS dùng dấu **:** giữa các classpath entry; Windows dùng dấu **;**. Provider **không cần nằm trong classpath khi biên dịch host**, chỉ cần có mặt khi khởi chạy ví dụ. Nếu triển khai cài đặt động sau khi host đã chạy, phải dùng cơ chế plugin loader phù hợp; ví dụ này kiểm chứng **discovery và vòng đời**, không tự chứng minh khả năng nạp JAR mới vào một classpath đã cố định.

**Standard output chính xác:**

~~~text
Host: ServiceLoader created
Provider: constructor
Host: selected upper
Host: cached same instance: true
Host: starting
Provider: start
Host: result HELLO
Host: stopping
Provider: stop
Host: clearing ServiceLoader cache
Provider: constructor
Host: new instance after reload: true
~~~

### 6.6. Đọc output theo quyền sở hữu

| Dòng output | Ai gây ra? | Ý nghĩa |
| --- | --- | --- |
| Host: ServiceLoader created | Host | Đã tạo đối tượng tra cứu, chưa tạo provider |
| Provider: constructor | ServiceLoader yêu cầu tạo provider; constructor chạy | Provider object được tạo lazily |
| Host: selected upper | Host | Host quyết định chọn provider ID upper |
| Host: cached same instance: true | ServiceLoader cache; host quan sát | Duyệt lại trả provider đã cache |
| Host: starting | Host | Host bắt đầu activation |
| Provider: start | Host gọi; provider thi hành | Không phải method ServiceLoader tự gọi |
| Host: result HELLO | Host gọi handle; provider thi hành | Nghiệp vụ được xử lý |
| Host: stopping | Host | Host quyết định shutdown |
| Provider: stop | Host gọi; provider thi hành | Cleanup thuộc hợp đồng plugin |
| Host: clearing ServiceLoader cache | Host | Host quyết định làm mới lookup |
| Provider: constructor (lần hai) | ServiceLoader tạo instance trong lượt duyệt mới | Cache cũ đã được clear |
| Host: new instance after reload: true | Host | Đối tượng mới, không có nghĩa đã dùng bytecode/plugin version mới |

Không có dòng **Provider: start** sau lần constructor thứ hai. Đây là bằng chứng dễ thấy rằng **reload() không phải activate()**. Cũng không có dòng **Provider: stop** do ServiceLoader tự sinh; stop xuất hiện bởi host gọi phương thức riêng của plugin.

## 7. ServiceLoader.reload() khác hoàn toàn hot reload plugin

Một lỗi phổ biến là thấy **reload()** và kết luận “đã cập nhật JAR/plugin”. Trong Java, cần tách ít nhất ba đối tượng:

1. **ServiceLoader**: giữ trạng thái tra cứu và cache provider của chính nó.
2. **ClassLoader hoặc ModuleLayer**: quyết định class/module definition nào có thể nạp và với identity nào.
3. **Plugin instance và tài nguyên**: object đã được tạo, thread, connection, callback, file handle và request đang chạy.

**ServiceLoader.reload() chỉ tác động tầng 1.** Nó không sửa trực tiếp tầng 2 hoặc đóng/giải phóng tầng 3.

Một quy trình nâng cấp thực tế có thể là:

~~~text
Plugin v1 ACTIVE trên loader L1
       |
       | Host nhận, verify plugin v2 artifact
       v
Host tạo loader L2 / module layer mới (khi cần)
       |
       v
Host tạo ServiceLoader mới gắn với L2/layer v2
       |
       v
ServiceLoader phát hiện và tạo provider v2
       |
       v
Host validate version/contract và start v2
       |
       +---- v2 thất bại --> stop/cleanup v2; tiếp tục v1; báo lỗi
       |
       v
Host chuyển request mới sang v2
       |
       v
Host drain các request v1, stop v1
       |
       v
Host đóng L1 khi an toàn, gỡ reference/callback/thread
       |
       v
v2 ACTIVE; v1 có thể được GC/unload khi đủ điều kiện
~~~

**Class đã được loader L1 định nghĩa không tự thay thế bằng bytecode cùng tên chỉ nhờ reload().** Đối với ứng dụng dùng URLClassLoader, cách phổ biến để thay định nghĩa là tạo loader mới và bảo đảm kiểu API/SPI chung vẫn do loader cha xác định.

**Đóng URLClassLoader** giải phóng các tài nguyên loader quản lý, nhưng không bảo đảm class được unload ngay. Nếu thread context class loader, static registry, callback, thread pool, task hoặc object do plugin tạo còn tham chiếu tới loader cũ, class có thể vẫn reachable. Host phải quản lý và kiểm chứng quá trình thu hồi.

**Độ an toàn của rollout:** không ngừng bản v1 trước khi chứng minh v2 đã vượt các kiểm tra cần thiết, trừ khi kiến trúc chấp nhận downtime. Với plugin stateful, phải có chính sách migrate state, compatibility của dữ liệu và cơ chế rollback; ServiceLoader không đảm nhiệm bất kỳ bước nào.

## 8. ClassLoader, TCCL và ModuleLayer là cấu hình của host

Trên classpath, cách chọn loader ảnh hưởng trực tiếp đến provider có được nhìn thấy:

~~~java
// Hai mảnh minh họa, trong host đã có Plugin và pluginClassLoader.
ServiceLoader<Plugin> explicit =
        ServiceLoader.load(Plugin.class, pluginClassLoader);

ServiceLoader<Plugin> byContext =
        ServiceLoader.load(Plugin.class);
~~~

Lời gọi thứ hai dùng **thread context class loader (TCCL)** ở thời điểm tạo ServiceLoader. Nếu host điều khiển nhiều plugin loader, lựa chọn explicit thường dễ lý giải và kiểm thử hơn. Khi tạm đặt TCCL, host phải khôi phục trong **finally** và tránh để thread pool giữ tham chiếu tới loader đã ngừng dùng.

Hai class có cùng tên nhị phân nhưng do defining class loader khác nhau định nghĩa **không tự có cùng type identity**. Nếu host và plugin vô tình nạp hai bản interface Plugin, việc tạo instance có thể thành công ở một loader nhưng **không assignable** cho SPI của host. Host thiết kế **parent loader chứa API chung**, rồi mới tạo loader con cho implementation và dependency riêng.

Đối với **JPMS explicit named modules**:
- **Module API** cần export package chứa SPI cho consumer/provider.
- **Module consumer** chứa lời gọi ServiceLoader phải khai báo **uses** cho service; có **requires** module API khi tham chiếu type.
- **Module provider** khai báo **provides service with provider** và các requires cần thiết.
- **Host** quyết định module graph/layer nào được resolve, được chọn và được sử dụng; **ServiceLoader.load(layer, service)** khám phá provider trong layer đó và các parent layer theo quy tắc API.

ServiceLoader **không tạo một ModuleLayer mới từ JAR plugin** cho host. Nếu runtime extension yêu cầu nạp thêm named module, host/framework phải giải quyết module configuration, class loader và lifecycle cho layer tương ứng.

**Không lạm dụng service discovery làm ranh giới bảo mật.** Việc provider được tìm thấy qua ServiceLoader không bảo đảm nó đáng tin hoặc không có quyền truy cập filesystem/network; kiểm soát đó thuộc deployment/policy/isolation của host.

## 9. Phân biệt Provider.type() và Provider.get() trong kiến trúc lựa chọn

Với **ServiceLoader.stream()**, host có thể khảo sát **Provider<S>** trước khi gọi get():

~~~java
// Mảnh minh họa; Plugin và loader đã tồn tại.
java.util.List<ServiceLoader.Provider<Plugin>> types =
        loader.stream().toList();

for (ServiceLoader.Provider<Plugin> provider : types) {
    System.out.println(provider.type().getName());
}
~~~

**provider.type()** trả Class liên quan đến kiểu provider theo hợp đồng API; có thể dùng annotation hoặc metadata kiểu để hỗ trợ lựa chọn trước khi tạo instance. **provider.get()** yêu cầu lấy một instance; tùy cơ chế provider constructor/factory, việc này có thể có side effect.

Do đó một plugin manager muốn loại provider không được phép **trước constructor** có thể dùng metadata an toàn bên ngoài JAR hoặc type-level inspection khi phù hợp. Nhưng cần lưu ý:

- **type() không chứng minh code an toàn**, không kiểm tra toàn bộ dependency hoặc contract nghiệp vụ.
- Với explicit module provider factory, type() có thể là **return type của provider()**, không phải factory class.
- Một số kiểm tra có thể làm JVM load/verify class; không coi việc liệt kê type là thao tác không có tác động vận hành trong mọi môi trường.
- Duyệt stream cũng có thể ném **ServiceConfigurationError**; host phải xử lý trước khi kích hoạt plugin.
- Dùng Stream và Iterator đan xen khi có reload/concurrency cần theo quy tắc ServiceLoader; tránh giữ lâu các view cũ.

Nếu cần một quy trình xác minh không được nạp code chưa tin cậy vào host, kiểm tra artifact/signature và metadata trong một môi trường tách biệt **trước khi** tạo ClassLoader/ServiceLoader.

## 10. Xử lý lỗi: JDK báo lỗi, host quyết định chính sách

| Sự cố | ServiceLoader có thể làm gì? | Host cần làm gì? |
| --- | --- | --- |
| Không có provider | Duyệt rỗng hoặc findFirst() trả Optional.empty | Quyết định bắt buộc hay optional; fail-fast hoặc fallback |
| Descriptor sai format | Ném **ServiceConfigurationError** khi duyệt | Ghi nhận plugin/version; reject artifact hoặc quarantine |
| Provider thiếu constructor/method hợp lệ | Ném **ServiceConfigurationError** | Kiểm tra package, constructor, factory, metadata và release |
| Provider constructor ném exception | Có thể bọc trong **ServiceConfigurationError** | Báo init failure, tránh start và quyết định rollback |
| Provider được tạo nhưng ID/version không khớp | Không biết policy của host | Host reject hoặc chuyển sang candidate khác |
| start() ném exception | Không gọi start(), không tự xử lý | Host cleanup theo contract khi partial init; báo FAILED |
| handle() thất bại | Không tham gia | Host timeout/retry/response mapping/circuit breaker |
| stop() bị lỗi | Không gọi stop() | Host log, tiếp tục cleanup có kiểm soát, theo dõi leak |
| Plugin v2 không healthy | Không biết health | Host giữ v1 hoặc rollback |
| Class loader cũ còn referenced | Không unload và không quan sát | Host loại TCCL/thread/callback/cache, đo resource leak |

**ServiceConfigurationError là Error:** bắt cụ thể tại ranh giới **provider discovery/instantiation** là hợp lý khi host cần quản lý lỗi cấu hình của plugin. Không dùng **catch(Throwable)** bao hết hệ thống rồi nuốt mọi lỗi JVM nghiêm trọng; và không coi mọi ServiceConfigurationError là một tình huống có thể tiếp tục bằng retry vô hạn.

Ví dụ xử lý ở ranh giới khám phá:

~~~java
// Mảnh minh họa trong host: Plugin và pluginClassLoader đã có.
try {
    ServiceLoader<Plugin> loader =
            ServiceLoader.load(Plugin.class, pluginClassLoader);

    for (Plugin candidate : loader) {
        // Host xác minh ID, version, quyền, health và chọn candidate.
    }
} catch (java.util.ServiceConfigurationError configurationFailure) {
    // Host ghi nhận lỗi của plugin và áp dụng policy reject/rollback.
}
~~~

Trên Java 17, javadoc giải thích rằng sau một ServiceConfigurationError, iterator chỉ **cố gắng tốt nhất** để đi tới provider khác; khả năng phục hồi không được bảo đảm. Vì vậy, một host không nên duyệt vô hạn để “bỏ qua lỗi rồi tìm provider tốt” mà không có giới hạn và thiết kế riêng.

**Sự cố start/stop khác với ServiceConfigurationError:** nếu provider đã được tạo và method do host gọi ném RuntimeException, lỗi đó thuộc **vòng đời do host điều phối** chứ không tự thành lỗi từ ServiceLoader.

## 11. Concurrency, cache và các quy tắc không được suy diễn

**ServiceLoader không được thiết kế thread-safe.** Không chia sẻ một instance ServiceLoader giữa nhiều thread rồi đồng thời duyệt, gọi stream, reload mà không có cơ chế đồng bộ riêng. Host nên điều phối discovery trong một giai đoạn kiểm soát được rồi lưu các provider đã chọn trong registry của chính host.

Ví dụ một cách thiết kế:

- **Discovery phase:** một luồng duyệt ServiceLoader và tạo danh sách candidate bất biến cho phiên bản plugin.
- **Validation phase:** host xác nhận ID, compatibility, policy và resource contract.
- **Activation phase:** host start() theo thứ tự, ghi lại trạng thái ACTIVE rõ ràng.
- **Serving phase:** nhiều luồng gọi provider theo mức concurrency mà contract cho phép.
- **Shutdown/replace phase:** host dừng nhận request mới, drain, stop và giải phóng loader.

Việc ServiceLoader cache instance **không có nghĩa instance đó thread-safe**. Constructor, method **handle()** và state của provider cần có contract riêng cho concurrency; host có thể phải serialize calls, cung cấp pool, hoặc tạo instance theo request nếu thiết kế cho phép.

**Thứ tự discovery không phải thứ tự ưu tiên nghiệp vụ.** Khi nhiều provider cùng phục vụ SPI, host nên dùng plugin ID và metadata/priority có kiểm soát để quyết định. Sử dụng **findFirst()** chỉ phù hợp khi bản thân quy tắc nghiệp vụ nói “chọn provider đầu tiên theo cấu hình tra cứu đã được kiểm soát”, hoặc khi chỉ một provider được triển khai và điều kiện đó được kiểm thử.

**Cache cũng không phải version registry.** ServiceLoader caching là cơ chế thuận tiện cho lookup trong một loader instance; host vẫn cần một registry quản lý artifact version, activation state, lease/reference count, health và thời điểm được phép retire.

## 12. Ba tình huống ra quyết định

### Tình huống A: một SPI ổn định, một provider duy nhất

Ứng dụng cung cấp **Formatter** và chỉ một JAR đăng ký provider. ServiceLoader tìm và tạo Formatter; host dùng nó để xử lý request. Nếu provider không quản lý resource, host có thể không cần start/stop phức tạp. **Nhưng việc không có start/stop là quyết định của contract**, không phải vì ServiceLoader tự dọn dẹp.

**Thuộc ServiceLoader:** locate descriptor, load class, instantiate.
**Thuộc host:** chọn class loader, gọi format(), xử lý exception và đóng mọi tài nguyên đã tạo.

### Tình huống B: nhiều provider cho nhiều tenant

Cả ProviderA và ProviderB đều hợp lệ cho một SPI. Tenant A chỉ được dùng ProviderA vì chính sách dữ liệu; tenant B cần ProviderB vì tính năng khác.

**ServiceLoader không biết tenant identity**. Nó có thể liệt kê cả hai. Host phải định nghĩa metadata, authorization, routing, quota và cách tránh rò rỉ state giữa tenants. Không nên chỉ lấy provider đầu tiên và xem đó là quyết định hợp lệ.

**Thuộc ServiceLoader:** khám phá các provider nhìn thấy.
**Thuộc host:** kiểm tra quyền, chọn theo tenant, cô lập dữ liệu, quan sát lỗi và chuyển traffic.

### Tình huống C: cập nhật plugin mà không dừng host

Đội vận hành cài plugin v2. Gọi ServiceLoader.reload() trên loader cũ chỉ làm mới lookup cache. Để nạp code v2 nếu loader cũ đã định nghĩa code v1, host cần kiến trúc loader/layer phù hợp, chuẩn bị v2, validate/start v2, chuyển request, stop v1 và bỏ tham chiếu cũ. **ServiceLoader không có quyền quyết định khi nào version v2 đủ healthy**.

**Thuộc ServiceLoader:** khám phá provider trong loader/layer v2 và tạo instance khi host yêu cầu.
**Thuộc host:** artifact update, loader/layer, validation, rollout, cutover, rollback, cleanup và observability.

## 13. Checklist triển khai plugin manager

### Trước discovery
- [ ] Có API/SPI được công bố ổn định, đúng class identity trong loader hoặc module API dùng chung.
- [ ] Artifact được xác minh theo nguồn gốc, version, checksum/signature và dependency policy phù hợp.
- [ ] Class loader hoặc ModuleLayer được chọn đúng cho plugin cần tìm.
- [ ] Provider đăng ký đúng **META-INF/services** hoặc **module-info provides**, consumer named module có **uses**.
- [ ] Có quyết định rõ plugin nào được phép load theo tenant/process và trust boundary.

### Discovery và lựa chọn
- [ ] Host xử lý **không có provider** và **ServiceConfigurationError** ở đúng ranh giới.
- [ ] Không coi **findFirst()** là ranking nghiệp vụ khi có nhiều provider.
- [ ] Chỉ instantiate khi cần; cân nhắc **stream().type()** nếu việc đọc type trước có ích.
- [ ] Có chính sách xác minh ID, version, contract, capability và quyền truy cập.
- [ ] Có một registry của host ghi rõ instance nào **SELECTED** và **ACTIVE**, độc lập cache ServiceLoader.

### Vận hành
- [ ] Host gọi start()/stop()/close() nếu SPI định nghĩa; có phương án cleanup khi start thất bại một phần.
- [ ] Có health, timeout, retry và cơ chế giảm tác động khi plugin lỗi.
- [ ] Có quy tắc đồng thời cho instance; không suy diễn thread safety từ việc được cache.
- [ ] Có log/metrics/tracing kèm provider ID, version, loader/layer để điều tra class identity và resource leak.

### Cập nhật và ngừng sử dụng
- [ ] Không đồng nhất **ServiceLoader.reload()** với nâng version/hot swap/unload.
- [ ] Không dùng iterator/stream cũ sau khi reload().
- [ ] Có kế hoạch loader/layer mới, start mới, chuyển traffic, drain, stop cũ, cleanup và rollback.
- [ ] Gỡ tham chiếu/TCCL/thread/callback/registry đến plugin cũ trước khi kỳ vọng class unloading.
- [ ] Có kiểm thử lifecycle và thất bại ở từng bước, không chỉ kiểm tra provider có được phát hiện.

## 14. Câu hỏi tự kiểm tra

**1. Nếu ServiceLoader tìm thấy provider nhưng host chưa gọi start(), plugin đã ACTIVE chưa?**  
Chưa. Một instance được tạo không chứng minh plugin đã vượt validation/readiness hoặc được host kích hoạt.

**2. Nếu gọi reload(), JVM có thay ngay bytecode từ plugin-v1.jar bằng plugin-v2.jar không?**  
Không. reload() xóa cache riêng của ServiceLoader; class definition và plugin lifecycle do loader/layer và host quản lý.

**3. Nếu provider constructor bị lỗi thì ai thông báo? Ai quyết định fallback?**  
ServiceLoader có thể ném ServiceConfigurationError khi instantiation; host chịu trách nhiệm log/policy/fallback/reject.

**4. Nếu start() hoặc stop() ném lỗi thì ServiceLoader có tự thử lại không?**  
Không. Đây là các method do SPI/host đặt ra; host quyết định thử lại, cleanup và chuyển trạng thái.

**5. Khi có hai provider, ai quyết định dùng provider nào?**  
ServiceLoader cho phép phát hiện provider; host chọn theo ID, version, capability, priority, authorization và yêu cầu nghiệp vụ.

**6. Tại sao không nên giữ ServiceLoader dùng TCCL làm singleton toàn JVM?**  
Mỗi ứng dụng/tenant có thể có TCCL khác nhau, dẫn tới tập provider khác nhau; giữ loader/provider quá lâu cũng có thể giữ class loader cũ và gây leak.

**7. Trong ví dụ chạy, ai gọi constructor, ai gọi start, ai gọi stop?**  
Constructor chạy trong quá trình ServiceLoader khởi tạo provider theo yêu cầu iterator; start và stop do host gọi trực tiếp.

## 15. Kết luận

**ServiceLoader cung cấp cơ chế để host tìm và nhận provider của một SPI đã đăng ký; nó không phải plugin lifecycle manager.** Việc tìm/nạp/tạo instance/cache thuộc phạm vi ServiceLoader. Việc xác minh nguồn gốc, phân quyền, chọn provider, cấu hình, kích hoạt, health, xử lý request, shutdown, nâng phiên bản, rollback và giải phóng tài nguyên thuộc trách nhiệm **ứng dụng chủ**.

Nếu ghi nhớ một quy tắc duy nhất: **“ServiceLoader trả lời có thể lấy provider nào; host trả lời provider nào được phép chạy, chạy khi nào, chạy ra sao và dừng khi nào.”**

### Tài liệu Java 17 chính thức

- ServiceLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- ServiceLoader.Provider: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- ServiceConfigurationError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceConfigurationError.html
- URLClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
