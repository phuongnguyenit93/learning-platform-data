# Phân biệt khám phá dịch vụ với quản lý phụ thuộc và vòng đời plugin trong Java

## 1. Ba trách nhiệm khác nhau của một hệ thống mở rộng

Trong Java, một ứng dụng (*host*) có thể cho phép cài thêm những phần triển khai (*service provider*, *extension*, *plugin*) để mở rộng chức năng. Khi **lựa chọn provider**, cần phân biệt ba câu hỏi:

1. **Khám phá dịch vụ (*service discovery*):** Những lớp nào tuyên bố triển khai một service contract và hiện có thể được tìm thấy?
2. **Quản lý phụ thuộc (*dependency management/resolution*):** Provider được chọn cần những API, thư viện, dịch vụ hoặc plugin khác nào; chúng có tồn tại và tương thích không?
3. **Quản lý vòng đời (*plugin lifecycle management*):** Khi nào provider được khởi tạo, được phép nhận yêu cầu, bị dừng và được giải phóng tài nguyên?

Chúng liên quan đến nhau nhưng **không phải cùng một cơ chế**. `java.util.ServiceLoader` chủ yếu giải quyết việc tìm và tạo provider được khai báo qua Java SPI; nó không tự tải dependency từ repository, không xác định thứ tự khởi động các plugin phụ thuộc, không gọi các phương thức nghiệp vụ `start()` hay `stop()`, và không áp đặt một cơ chế nâng cấp/dỡ plugin đang chạy.

| Khía cạnh | Khám phá dịch vụ | Quản lý phụ thuộc | Quản lý vòng đời |
| --- | --- | --- | --- |
| Câu hỏi | “Có provider nào cho contract này?” | “Provider cần gì để hoạt động đúng?” | “Provider đang ở trạng thái nào và được phép làm gì?” |
| Đầu vào điển hình | Service interface, SPI descriptor, module declaration, class loader | Metadata/version, JAR và thư viện, module graph, dịch vụ host, quan hệ plugin | Provider instance, cấu hình, tài nguyên, readiness, request đang chạy |
| Công cụ/cách làm | `ServiceLoader`, `META-INF/services`, `uses/provides` | Maven/Gradle lúc build, runtime classpath/module resolution, plugin dependency resolver, DI | Plugin manager, state machine, `start/stop/close`, dispatcher và registry |
| Kết quả | Một hoặc nhiều provider ứng viên | Tập phụ thuộc phù hợp, có thể nạp/được cung cấp | Instance ACTIVE, hoặc STOPPED/FAILED cùng cleanup |
| Lỗi điển hình | Không có provider, khai báo SPI hỏng | Thiếu lớp, sai version, xung đột dependency, vòng phụ thuộc | Start lỗi, request sau stop, thread/leak tài nguyên |
| `ServiceLoader` làm được? | Có: tìm và tạo provider theo quy tắc SPI | Không làm dependency resolver tổng quát | Không điều phối lifecycle do ứng dụng định nghĩa |

**Ví dụ:** Host tìm thấy `PdfExporter` qua SPI. Điều đó **không chứng minh** phiên bản PDF library mà provider cần đã có, cũng **không chứng minh** kết nối lưu trữ đã được cấp. Sau khi xác minh phụ thuộc, host vẫn phải quyết định có bật provider không, cấp cấu hình và dịch vụ cần thiết, khởi động, đưa vào registry, giám sát rồi dừng theo chính sách.

Trong bài này, “service discovery” là **khám phá provider Java trong tiến trình** qua SPI/Module System. Đây là khái niệm khác với việc tìm instance dịch vụ mạng bằng DNS, Kubernetes Service hay service registry.

## 2. Khám phá dịch vụ: Java SPI và `ServiceLoader`

### 2.1. Service contract và provider declaration

Giả sử host công bố một interface:

```java
package app.api;

public interface Plugin {
    String id();
    String process(String input);
}
```

Đây chỉ là **đoạn minh họa contract**; ví dụ chạy được ở mục 6 có thêm API vòng đời. Một lớp triển khai `app.ext.UppercasePlugin` có thể đăng ký với SPI trên classpath qua tệp:

```text
META-INF/services/app.api.Plugin
```

Nội dung:

```text
app.ext.UppercasePlugin
```

Tên tệp chính là *fully qualified name* của service interface; mỗi dòng hợp lệ trong tệp chỉ tới một provider class theo quy tắc SPI. Với named modules thuộc JPMS, provider có thể đăng ký bằng khai báo `provides app.api.Plugin with app.ext.UppercasePlugin;` và module tiêu thụ khai báo `uses app.api.Plugin;`.

Host tìm provider bằng:

```java
ServiceLoader<Plugin> loader = ServiceLoader.load(Plugin.class);
for (Plugin plugin : loader) {
    System.out.println(plugin.id());
}
```

Đoạn trên là minh họa cần `import java.util.ServiceLoader;` và interface tương ứng. `ServiceLoader.load(Plugin.class)` dùng context class loader của thread; có overload `ServiceLoader.load(Plugin.class, specificLoader)` khi host quản lý plugin qua class loader được chỉ định. `ServiceLoader.load(layer, Plugin.class)` hỗ trợ tìm từ module layer.

### 2.2. “Đã khám phá” có thể hàm ý những mức khác nhau

Không nên gom mọi thao tác vào một từ “load”:

- **Tìm artifact:** thấy một JAR/manifest trong thư mục plugin; vẫn có thể chưa chạm vào class của plugin.
- **Tìm khai báo service:** nhận diện tên provider qua `META-INF/services` hoặc module metadata.
- **Nạp class:** JVM tìm, định nghĩa và liên kết các lớp cần thiết qua class loader; việc nạp không đồng nghĩa gọi constructor hay method `start` của ứng dụng.
- **Tạo instance provider:** `ServiceLoader` có thể tạo provider khi duyệt `iterator()` hoặc khi gọi `Provider.get()`; lúc này constructor/static initializer liên quan có thể chạy.
- **Kích hoạt nghiệp vụ:** host tự gọi method khởi động do contract quy định; đây không thuộc nhiệm vụ tự động của `ServiceLoader`.

`ServiceLoader` có tính *lazy*: tạo đối tượng loader không buộc tất cả provider được tạo ngay. `findFirst()` trả `Optional<Plugin>`, phù hợp khi ứng dụng chỉ cần một provider có sẵn:

```java
Optional<Plugin> first =
    ServiceLoader.load(Plugin.class).findFirst();
```

Tuy nhiên **provider đầu tiên không mặc định là provider tốt nhất**. Thứ tự duyệt có thể chịu ảnh hưởng classpath, module configuration và nguồn đăng ký. Khi lựa chọn provider theo ID, capability, version hay priority, host phải xây quy tắc lựa chọn riêng. `Optional.empty()` chỉ biểu thị không tìm thấy provider nào sau một lần duyệt bình thường; nó không thay cho xác thực dependency hoặc readiness.

### 2.3. `findFirst()` và `stream()` phục vụ nhu cầu khác nhau

| API | Kiểu kết quả | Mục đích |
| --- | --- | --- |
| `loader.findFirst()` | `Optional<Plugin>` | Lấy instance provider đầu tiên |
| `loader.stream().findFirst()` | `Optional<ServiceLoader.Provider<Plugin>>` | Lấy provider handle đầu tiên |
| `Provider.type()` | `Class<? extends Plugin>` | Xem kiểu provider mà không chủ động gọi `Provider.get()` |
| `Provider.get()` | `Plugin` | Yêu cầu tạo/lấy instance provider |

Chẳng hạn:

```java
Optional<Plugin> selected = loader.stream()
    .filter(p -> p.type().getName().equals("app.ext.UppercasePlugin"))
    .findFirst()
    .map(ServiceLoader.Provider::get);
```

Đây là đoạn minh họa lựa chọn theo tên class để chỉ ra sự khác biệt giữa *handle* và *instance*. Việc xem kiểu qua `type()` vẫn có thể cần nạp class/metadata; **không nên coi discovery là hành động an toàn với mã không đáng tin cậy**. Nếu muốn chọn theo ID/capability trước khi khởi tạo instance, nên có metadata/manifest do host kiểm soát thay vì phải gọi constructor chỉ để đọc thuộc tính.

### 2.4. Khám phá không tự giải quyết lỗi cấu hình

Một tệp SPI có thể khai báo provider không tồn tại, không thuộc service interface, không thể tạo instance hoặc thiếu dependency. Trong trường hợp đó, quá trình duyệt `ServiceLoader` có thể ném `ServiceConfigurationError`. Cần phân biệt:

- Không có provider nào: `findFirst()` trả `Optional.empty()`.
- Có khai báo provider nhưng không dùng được: thường là lỗi cấu hình/nạp/tạo provider; phải chẩn đoán và khắc phục, không biến hết thành “trống”.
- Có provider nhưng không đáp ứng chính sách lựa chọn: host có thể trả kết quả “không có provider phù hợp”, dù SPI vẫn phát hiện được các provider khác.

## 3. Quản lý phụ thuộc: “nhìn thấy provider” chưa đủ để chạy được

### 3.1. Bốn loại phụ thuộc thường gặp

**1. Phụ thuộc thư viện/mã:** provider cần thư viện bên ngoài hoặc một phiên bản Java/JAR cụ thể. Ví dụ `PdfExporter` cần một thư viện tạo PDF, nhưng `ServiceLoader` không tải thư viện đó giúp bạn. Maven/Gradle giải quyết phụ thuộc trong quá trình build/packaging; môi trường runtime vẫn cần có đúng class/module cần thiết. Thiếu dependency có thể dẫn tới `ClassNotFoundException`, `NoClassDefFoundError` hoặc `LinkageError`.

**2. Phụ thuộc API dùng chung:** host và plugin phải hiểu cùng service contract/DTO. Trong JVM, danh tính của một class gồm **tên đầy đủ + defining class loader**. Nếu một JAR plugin tự mang bản sao `app.api.Plugin` được nạp bởi class loader khác, host có thể gặp lỗi ép kiểu hoặc liên kết dù tên class giống nhau. Thông thường host/parent loader sở hữu contract ổn định; plugin loader chỉ nạp implementation và dependency riêng.

**3. Phụ thuộc dịch vụ host:** provider cần logger, clock, repository, cấu hình hoặc khách hàng HTTP. Host phải tạo, chọn, cấu hình và cấp những dịch vụ đó qua interface/context hay DI. `ServiceLoader` không biết provider cần một `AuditLog` hay một kết nối database như thế nào, trừ khi ứng dụng tự thiết kế contract và quy trình cấp dependency.

**4. Phụ thuộc plugin khác:** ví dụ plugin `Report` cần plugin `Storage` đã `ACTIVE`; plugin `Export` lại cần `Report`. Host phải biết các cạnh phụ thuộc, kiểm tra version/capability và khởi động theo thứ tự hợp lệ.

### 3.2. Đồ thị phụ thuộc và thứ tự khởi động

Giả sử:

```text
Export ──requires──► Report ──requires──► Storage
```

Nếu ký hiệu `A → B` là “A cần B”, thứ tự khởi động nên là:

```text
Storage → Report → Export
```

Khi dừng, đảo ngược:

```text
Export → Report → Storage
```

Một plugin manager có thể áp dụng **topological sort** cho dependency graph, rồi:

1. Đọc danh sách dependency/capability và yêu cầu version.
2. Xác minh mỗi dependency bắt buộc có mặt và tương thích; dependency tùy chọn có chính sách rõ ràng.
3. Phát hiện vòng phụ thuộc, ví dụ A cần B và B cần A, để báo lỗi có thể chẩn đoán.
4. Chuẩn bị class loader/module layer và các dịch vụ cần thiết.
5. Khởi động các phần phụ thuộc trước, chỉ kích hoạt plugin đang chờ khi những phần bắt buộc đã sẵn sàng.
6. Dừng theo thứ tự ngược, tránh đóng một dependency trong khi plugin khác vẫn dùng nó.

Đây là chính sách của host/framework, **không phải chức năng có sẵn của `ServiceLoader`**. Đặc biệt, một vòng lặp `for (Plugin p : ServiceLoader.load(Plugin.class))` không bảo đảm đưa các plugin vào đúng thứ tự phụ thuộc.

### 3.3. Maven/Gradle, JPMS và dependency injection khác nhau ra sao?

| Cơ chế | Giải quyết được | Không giải quyết tự động |
| --- | --- | --- |
| Maven/Gradle | Khai báo, lấy và đóng gói dependency trong build | Quyết định plugin nào `ACTIVE`, chạy `start/stop` của runtime plugin |
| Classpath và class loader | Nạp/tìm class từ nguồn được cung cấp | Tải dependency thiếu từ repository, xác minh version theo chính sách nghiệp vụ |
| JPMS `requires` và module resolution | Ràng buộc tính đọc được và giải quyết dependency module khi cấu hình layer | Đưa plugin vào trạng thái nghiệp vụ READY, đợi inflight request, close resource |
| DI container/factory | Tạo object graph và tiêm dependency theo cấu hình | Tự nhận diện mọi provider bên ngoài hay điều phối hot swap nếu không được cấu hình |
| Plugin manager tự thiết kế | Có thể kết hợp metadata, graph resolution, DI, trạng thái, health check và cleanup | Chỉ làm được những chính sách mà ứng dụng thực sự triển khai |

**JPMS làm rõ dependency ở cấp module**, nhưng việc cấu hình module layer và runtime lifecycle vẫn cần host chủ động quản lý. **DI giải quyết quan hệ giữa các object**, còn service discovery giúp tìm tập provider ứng viên. Nhiều ứng dụng kết hợp cả hai.

### 3.4. Dependency conflict trong plugin động

Nếu hai plugin đòi hai phiên bản không tương thích của cùng thư viện, đưa cả hai lên một classpath có thể gây lỗi. Một chiến lược là class loader riêng cho plugin, đặt API dùng chung ở parent và quản lý policy cho dependency riêng. Điều đó cần xét:

- Ranh giới parent-first/child-first thực tế và sự xuất hiện của trùng package.
- Không đóng gói lặp contract của host vào plugin.
- Dependency được chia sẻ hay cô lập; JNI/native library có giới hạn riêng.
- Thread, callback, `ThreadLocal` hoặc cache nào có thể giữ class loader cũ sau reload.
- Quyền truy cập tài nguyên: **class loader isolation không phải security sandbox**. Plugin chạy trong cùng tiến trình thường có các quyền của tiến trình.

## 4. Quản lý vòng đời: provider phải được kích hoạt và dừng rõ ràng

### 4.1. Một state machine hợp lý

```text
DISCOVERED
    │
    ▼
VALIDATED / DEPENDENCIES_RESOLVED
    │
    ▼
INSTANTIATED
    │
    ▼
STARTING ──lỗi──► FAILED ──cleanup──► STOPPED
    │
  thành công
    ▼
ACTIVE ──ngừng nhận mới──► QUIESCING
                              │
                           đợi inflight
                              ▼
                           STOPPING
                              │
                              ▼
                            STOPPED
```

Các tên trạng thái là **thiết kế ở cấp ứng dụng**; JVM không có sẵn state machine này cho SPI. Host quyết định ai được gọi khi nào:

- Chỉ công bố plugin vào registry phục vụ request sau khi `start` và readiness check thành công.
- Chặn các lời gọi mới ngay khi chuyển sang `QUIESCING`.
- Cho những lời gọi đang chạy hoàn thành trong deadline, sau đó áp dụng chính sách hủy/rollback.
- Gọi `stop()`/`close()`, hủy đăng ký listener, đóng executor/thread, stream, socket và các tài nguyên mà plugin sở hữu.
- Gỡ plugin khỏi registry, callback và cache; đóng class loader do host tạo khi thích hợp.

Một hợp đồng vòng đời phổ biến:

```java
public interface ManagedPlugin {
    String id();
    void start(HostServices services);
    Object execute(Object request);
    void stop();
}
```

Đây là **minh họa thiết kế API**, chưa phải chương trình chạy đầy đủ. Contract nên quy định thread safety, idempotence của `stop`, cách xử lý lỗi một phần khi `start` thất bại và deadline khi chờ request kết thúc.

### 4.2. Tạo instance khác với khởi động nghiệp vụ

Khi `ServiceLoader` tạo provider, constructor và logic khởi tạo class có thể chạy. Nhưng `ServiceLoader` **không tự gọi** một phương thức `start` mà bạn tự khai báo.

Ví dụ một plugin `StoragePlugin` có constructor không tham số. Dù `ServiceLoader.findFirst()` tìm được instance, host vẫn phải cung cấp cấu hình/kết nối trước khi đưa plugin vào bộ định tuyến. Nếu constructor gây side effect lớn, host rất khó kiểm soát và rollback; nên giữ constructor gọn và đưa phần khởi động chủ động vào `start`.

Khi `start` thất bại sau khi đã tạo một số tài nguyên, plugin nên tự giải phóng phần đã cấp phát; host không đánh dấu `ACTIVE` và tránh điều phối request vào instance đó. Khi plugin khác phụ thuộc instance này, manager phải ngăn khởi động hoặc đánh dấu trạng thái phụ thuộc lỗi theo chính sách.

### 4.3. Dừng plugin không có nghĩa unload class

`URLClassLoader.close()` đóng các file/JAR mà loader đã mở; nó **không giết thread**, không làm các object plugin đang tồn tại ngừng hoạt động và không bảo đảm class unloading. Class loader/class chỉ có thể được GC dọn khi không còn tham chiếu giữ chúng. Các nguồn giữ lại thường là thread, TCCL (`Thread.currentThread().getContextClassLoader()`), `ThreadLocal`, static cache, listener, callback, executor và registry.

Đối với **hot reload**, thường dùng loader mới + instance mới, kiểm tra compatibility, khởi động và health check, chuyển traffic, đợi request cũ, dừng instance cũ, bỏ các tham chiếu cũ rồi đóng loader cũ. `ServiceLoader.reload()` chỉ xóa cache provider của đối tượng `ServiceLoader`; nó không thay định nghĩa class đã được JVM nạp bằng loader cũ và không tự gọi `stop`.

## 5. Khi lựa chọn provider, ba cơ chế kết hợp với nhau thế nào?

Một quy trình vận hành điển hình:

```text
[1] Nhận artifact / metadata
          │
          ▼
[2] Xác thực nguồn, version, capability, dependency bắt buộc
          │
          ▼
[3] Resolve dependency graph, cấu hình class loader/module layer
          │
          ▼
[4] SPI discovery: ServiceLoader → các provider ứng viên
          │
          ▼
[5] Selection policy: bật/tắt, ID, capability, priority, compatibility
          │
          ▼
[6] Tạo instance, cấp HostServices, gọi start và readiness check
          │
          ▼
[7] Chỉ đưa provider ACTIVE vào registry nhận request
          │
          ▼
[8] Quiesce → stop → cleanup theo dependency order
```

Thứ tự thực thi cụ thể phụ thuộc kiến trúc: provider trên classpath có thể được đóng gói với dependency từ trước, nên bước resolve ở runtime gần như không nhìn thấy; hệ thống nạp JAR động cần xác minh metadata và thư viện **trước khi** cho code provider chạy. Điểm cốt lõi là host phải phân biệt **“được tìm thấy”**, **“hợp lệ để lựa chọn”** và **“sẵn sàng để phục vụ”**.

### Selection policy cần rõ ràng

Nếu có hai provider cùng một interface, đừng đơn thuần dùng `findFirst()` khi nghiệp vụ yêu cầu lựa chọn xác định. Host có thể:

- Lọc theo `id` và kiểm tra ID không trùng.
- Lọc theo capability (ví dụ `supports("pdf")`).
- Kiểm tra version contract, flags bật/tắt và chính sách nguồn đã được tin cậy.
- Ưu tiên dựa trên cấu hình/priority được định nghĩa, có tie-break ổn định.
- Chỉ chọn provider có dependency đã thỏa mãn; chỉ dispatch sau readiness.

Đối với provider **không có**, nên phân biệt “tính năng tùy chọn → bỏ qua/fallback”, “tính năng bắt buộc → báo lỗi rõ” và “có provider nhưng hỏng dependency/config → không im lặng fallback”. Nếu nhiều provider có cùng ID, manager nên từ chối cấu hình mơ hồ hoặc áp dụng quy tắc xung đột tường minh.

## 6. Ví dụ Java 17+ chạy được: khám phá bằng SPI, host tự cấp phụ thuộc và quản lý lifecycle

Ví dụ dưới đây cố tình tách ba trách nhiệm bằng ba thao tác nhìn thấy được:

1. **Khám phá và chọn:** `ServiceLoader` tìm lớp thực thi `Plugin` từ một JAR và host chọn theo `id`.
2. **Cấp dependency:** host tạo `AuditLog` rồi truyền vào `start(AuditLog)`. `ServiceLoader` không cấp dependency này.
3. **Vòng đời:** host chủ động gọi `start`, `process` và `stop` trong `finally`.

Ví dụ chỉ có một plugin để giữ mã dễ theo dõi. Một plugin manager production cần bổ sung resolver cho quan hệ plugin-to-plugin, version check, đồng bộ trạng thái, giới hạn thời gian và xử lý lỗi khởi động một phần như đã giải thích.

### 6.1. Cấu trúc

```text
demo/
├── src/
│   └── app/
│       ├── api/
│       │   ├── AuditLog.java
│       │   └── Plugin.java
│       ├── host/
│       │   └── App.java
│       └── ext/
│           └── UppercasePlugin.java
└── resources/
    └── META-INF/
        └── services/
            └── app.api.Plugin
```

### 6.2. Contract cấp cho cả host và plugin

**`src/app/api/AuditLog.java`**

```java
package app.api;

@FunctionalInterface
public interface AuditLog {
    void record(String event);
}
```

**`src/app/api/Plugin.java`**

```java
package app.api;

public interface Plugin {
    String id();
    void start(AuditLog audit);
    String process(String input);
    void stop();
}
```

`AuditLog` là một **phụ thuộc của plugin do host cấp**, không phải service mà `ServiceLoader` tự động biết cách khởi tạo và tiêm.

### 6.3. Implementation được đóng trong JAR riêng

**`src/app/ext/UppercasePlugin.java`**

```java
package app.ext;

import app.api.AuditLog;
import app.api.Plugin;
import java.util.Locale;
import java.util.Objects;

public final class UppercasePlugin implements Plugin {
    private AuditLog audit;
    private boolean active;

    // Constructor mặc định không tham số, dùng được với SPI.
    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public void start(AuditLog audit) {
        if (active) {
            throw new IllegalStateException("Plugin already active");
        }
        this.audit = Objects.requireNonNull(audit, "audit");
        active = true;
        audit.record("start uppercase");
    }

    @Override
    public String process(String input) {
        if (!active) {
            throw new IllegalStateException("Plugin not active");
        }
        return input.toUpperCase(Locale.ROOT);
    }

    @Override
    public void stop() {
        if (!active) {
            return;
        }
        active = false;
        audit.record("stop uppercase");
        audit = null;
    }
}
```

`active` trong ví dụ chỉ phục vụ kiểm tra vòng đời tuần tự; nó **không phải** giải pháp thread safety cho ứng dụng có nhiều request đồng thời. Trong production, việc chuyển trạng thái và đếm inflight cần cơ chế đồng bộ/điều phối thích hợp.

### 6.4. Host khám phá, chọn, tiêm dependency rồi dừng

**`src/app/host/App.java`**

```java
package app.host;

import app.api.AuditLog;
import app.api.Plugin;
import java.util.Optional;
import java.util.ServiceLoader;

public final class App {
    public static void main(String[] args) {
        String desiredId = args.length == 0 ? "uppercase" : args[0];

        // (1) Khám phá: SPI tạo các provider khi stream được duyệt.
        // (2) Lựa chọn: chính sách ID do host quyết định.
        Optional<Plugin> selected = ServiceLoader.load(Plugin.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .filter(plugin -> desiredId.equals(plugin.id()))
            .findFirst();

        if (selected.isEmpty()) {
            System.out.println("Không có provider: " + desiredId);
            return;
        }

        Plugin plugin = selected.orElseThrow();

        // (3) Quản lý dependency: host tự tạo và cấp AuditLog.
        AuditLog audit = event -> System.out.println("[audit] " + event);

        // (4) Quản lý lifecycle: ServiceLoader không tự gọi start/stop.
        try {
            plugin.start(audit);
            System.out.println("Kết quả: " + plugin.process("Java SPI"));
        } finally {
            // Hợp đồng plugin phải cho phép cleanup kể cả khi start lỗi.
            plugin.stop();
        }
    }
}
```

Ở đây `map(ServiceLoader.Provider::get)` tạo instance cho các ứng viên được duyệt tới trước khi lọc ID. Nếu có rất nhiều plugin và muốn chọn **trước khi khởi tạo**, cần metadata bên ngoài hoặc một chính sách dựa trên `Provider.type()`; không nên tạo tất cả chỉ để đọc ID khi việc khởi tạo tốn kém. Đoạn mã này chủ ý giữ mô hình lựa chọn đơn giản.

### 6.5. Khai báo SPI

Tạo tệp **`resources/META-INF/services/app.api.Plugin`** có nội dung:

```text
app.ext.UppercasePlugin
```

Tệp phải nằm trong JAR provider đúng vị trí; service interface `app.api.Plugin` nằm trong host/API, không đóng gói lặp vào provider JAR.

### 6.6. Biên dịch và chạy trên Windows PowerShell

Đứng tại thư mục `demo` với JDK 17+ (`javac`, `java` và `jar` có trong `PATH`):

```powershell
New-Item -ItemType Directory -Force build/host, build/provider | Out-Null

# Biên dịch contract và host, chưa đưa implementation lên classpath.
javac -encoding UTF-8 -d build/host src/app/api/AuditLog.java src/app/api/Plugin.java src/app/host/App.java

# Provider được biên dịch riêng, phụ thuộc vào API ở build/host.
javac -encoding UTF-8 -cp build/host -d build/provider src/app/ext/UppercasePlugin.java

# Đóng descriptor SPI và class provider vào JAR.
New-Item -ItemType Directory -Force build/provider/META-INF/services | Out-Null
Copy-Item resources/META-INF/services/app.api.Plugin build/provider/META-INF/services/app.api.Plugin
jar --create --file build/uppercase-plugin.jar -C build/provider .

# Thử không có provider:
java -cp build/host app.host.App

# Thử có provider:
java -cp 'build/host;build/uppercase-plugin.jar' app.host.App
```

**Chạy lần 1 (không có provider)** — stdout chính xác:

```text
Không có provider: uppercase
```

**Chạy lần 2 (có JAR provider)** — stdout chính xác:

```text
[audit] start uppercase
Kết quả: JAVA SPI
[audit] stop uppercase
```

Giải thích theo ba trách nhiệm:

- **Discovery:** lần 1 thiếu descriptor/provider trong runtime classpath nên `selected.isEmpty()` là `true`; lần 2 thấy descriptor, SPI tạo instance `UppercasePlugin`.
- **Dependency:** host tạo lambda `AuditLog` rồi **truyền tường minh** vào `plugin.start(audit)`. Không có dòng nào của `ServiceLoader` tự tiêm `AuditLog`.
- **Lifecycle:** `start` và `stop` ghi log qua dependency; `process` chỉ chạy giữa hai lời gọi đó. Nếu bỏ `start` mà gọi `process`, implementation sẽ ném `IllegalStateException("Plugin not active")`.

Để thử lựa chọn theo ID khi đã có JAR, chạy:

```powershell
java -cp 'build/host;build/uppercase-plugin.jar' app.host.App unknown
```

Stdout:

```text
Không có provider: unknown
```

Lúc này **SPI vẫn khám phá được `UppercasePlugin`**, nhưng host không chọn nó vì ID không khớp. Điều này phân biệt rõ “không có provider được đăng ký” với “có provider nhưng không phù hợp tiêu chí chọn”.

Trên Linux/macOS dùng `mkdir -p`/`cp` thay cho `New-Item`/`Copy-Item` và dấu hai chấm `:` thay dấu chấm phẩy `;` giữa các phần classpath; ví dụ `java -cp 'build/host:build/uppercase-plugin.jar' app.host.App`.

### 6.7. Giới hạn của ví dụ

Ví dụ không dùng dependency resolver bên ngoài, không thực hiện khởi động nhiều plugin theo dependency graph, không quản lý class loader riêng và không hot swap. Với **cùng JVM và một lần chạy**, `ServiceLoader` tìm các provider đã hiện diện trong classpath. Nếu muốn cài JAR mới trong khi host vẫn đang chạy, phải quản lý class loader/module layer, phiên bản API, thư viện liên quan và lifecycle của instance cũ/mới. Demo chỉ chứng minh rằng discovery, dependency injection và lifecycle là các trách nhiệm khác nhau.

Trong ví dụ, `stop` có thể gọi lặp lại mà không gây tác dụng phụ. Với plugin mở tài nguyên ngay giữa `start` rồi lỗi, contract phải yêu cầu cleanup phần đã mở (trong `start` hoặc `stop`). Khi ứng dụng phức tạp có nhiều plugin, host cũng nên bắt lỗi cleanup riêng để tiếp tục dọn các thành phần khác.

## 7. Các tình huống thực tế và cách thiết kế

### Tình huống A: ServiceLoader tìm được provider nhưng thiếu thư viện

Một provider `CsvExporter` được khai báo đúng SPI nhưng tham chiếu thư viện phiên bản khác với môi trường chạy. Khi duyệt, JVM có thể ném `NoClassDefFoundError`, `LinkageError` hoặc `ServiceConfigurationError` tùy nơi lỗi phát sinh.

**Cách xử lý:** kiểm tra artifact/dependency/bytecode và policy version; sửa runtime packaging hoặc resolver. Không kết luận rằng chỉ cần gọi `findFirst()` lần nữa hoặc `reload()` là đủ. Không biến lỗi tạo provider thành `Optional.empty()` để âm thầm dùng fallback.

### Tình huống B: Có hai provider đều triển khai cùng contract

`FastCompressor` và `SafeCompressor` cùng implement `Compressor`. `findFirst()` chỉ cho “provider đầu tiên được duyệt” và không hiểu nhu cầu hiệu năng hay an toàn.

**Cách xử lý:** host định policy chọn dựa vào ID, định dạng hỗ trợ, feature flag, độ ưu tiên, compatibility và ràng buộc cần thiết. Nếu dùng priority, phải quy định khi bằng điểm và có thể không ổn định theo thứ tự SPI.

### Tình huống C: Provider phụ thuộc plugin khác

`ReportPlugin` đòi `StoragePlugin` ở trạng thái `ACTIVE`. `ServiceLoader` có thể tìm cả hai nhưng không tự biết cần khởi động `StoragePlugin` trước.

**Cách xử lý:** quản lý dependency graph, kiểm tra presence/version, resolve thứ tự và chỉ đưa `ReportPlugin` vào registry khi dependency sẵn sàng. Khi tắt, dừng `ReportPlugin` trước `StoragePlugin`.

### Tình huống D: Provider khởi động thất bại

`PaymentPlugin.start()` mở kết nối rồi lỗi vì thiếu cấu hình. Việc discovery thành công không có nghĩa plugin đủ điều kiện nhận request.

**Cách xử lý:** state machine chuyển sang `FAILED`, không publish instance, ghi lỗi và rollback tài nguyên đã mở. Dịch vụ host cần thông báo tình trạng health thay vì tiếp tục gọi instance chưa khởi động.

### Tình huống E: Nâng cấp plugin trong JVM đang chạy

JAR plugin đã được nạp qua loader cũ. Việc thay file trên disk và gọi `ServiceLoader.reload()` không tự chuyển code đang chạy sang phiên bản mới.

**Cách xử lý:** nạp bản mới qua loader/layer phù hợp, xác minh dependency và API, khởi động/readiness, chuyển traffic, chờ request cũ, dừng bản cũ, dọn callback/thread và đóng loader cũ. Không kết luận class đã unload chỉ vì đã gọi `URLClassLoader.close()`.

## 8. Lỗi thường gặp khi gộp các trách nhiệm

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “`ServiceLoader` quản lý dependencies.” | Nó tìm/tạo provider, không tải JAR hoặc resolve graph plugin nghiệp vụ | Dùng build dependency resolver và runtime plugin resolver thích hợp |
| “Có provider nghĩa là sẵn sàng chạy.” | Constructor có thể thành công nhưng thiếu cấu hình/readiness | Kiểm tra dependency, gọi start, chỉ publish khi ACTIVE |
| “`findFirst()` bảo đảm chọn đúng provider.” | Thứ tự phát hiện không phải policy nghiệp vụ | Chọn theo ID/capability/priority, kiểm tra trùng |
| “`Optional.empty()` và `ServiceConfigurationError` là một.” | Một bên là vắng mặt bình thường; một bên là lỗi khai báo/tạo provider | Báo lỗi cấu hình riêng, không nuốt lỗi |
| “DI container đồng nghĩa plugin discovery.” | DI thường tạo object theo cấu hình; SPI phát hiện provider từ declaration | Kết nối rõ bước discovery với bước dependency injection |
| “`start` tự chạy khi ServiceLoader tạo instance.” | SPI không biết method nghiệp vụ do ứng dụng đặt tên | Host chủ động start/stop và kiểm soát state |
| “`reload()` là nâng cấp code tại chỗ.” | Nó xóa cache tìm provider, không thay class đã định nghĩa | Loader/instance mới cùng quy trình chuyển traffic |
| “Đóng loader là dừng plugin/unload class.” | Instance/thread/callback cũ vẫn có thể sống | Quiesce, stop, cleanup, gỡ reference rồi đóng loader |
| “Class loader là sandbox bảo mật.” | Plugin trong cùng JVM thường dùng quyền của tiến trình | Chạy mã không tin cậy ở process cô lập, quyền OS giới hạn |

## 9. Checklist cho người thiết kế hệ thống plugin

- [ ] Contract service rõ ràng, API/version ổn định và không bị nạp lặp bởi class loader không tương thích.
- [ ] Cơ chế discovery được khai báo đúng (SPI descriptor hoặc JPMS `uses/provides`).
- [ ] Có chính sách chọn provider xác định: ID, capability, enabled state, version, priority; không ngầm dựa vào thứ tự duyệt.
- [ ] Tách lỗi “không tìm thấy” khỏi lỗi descriptor/class loading/constructor.
- [ ] Liệt kê dependency thư viện, host service và plugin-to-plugin; xác minh version, optional dependency, conflict và cycle.
- [ ] Plugin manager xác định thứ tự start/stop theo dependency graph, cấp context tối thiểu và chỉ publish sau readiness.
- [ ] Invocation có kiểm soát concurrency, timeout, input/output contract, lỗi và metrics.
- [ ] Shutdown chặn request mới, chờ inflight, cleanup đầy đủ và không để tham chiếu giữ loader cũ.
- [ ] Hot reload (nếu cần) có chiến lược loader/instance mới, switch traffic, rollback và leak check.

**Điểm cần ghi nhớ:** `ServiceLoader` trả lời **“ai có thể cung cấp service?”**; dependency management trả lời **“provider cần gì để có thể chạy?”**; lifecycle management trả lời **“provider được phép chạy khi nào và phải dừng ra sao?”**. Một host chọn provider đúng cần cả ba, với chính sách rõ ràng ở ranh giới từng bước.

**Tài liệu tham khảo:** [`ServiceLoader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`ServiceConfigurationError` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceConfigurationError.html), [`URLClassLoader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), [`ModuleLayer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html).
