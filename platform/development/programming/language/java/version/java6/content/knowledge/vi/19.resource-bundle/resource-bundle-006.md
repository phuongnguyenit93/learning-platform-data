# ResourceBundle: Vòng đời ClassLoader và phạm vi cache trong Java

## 1. Bài toán và nguyên tắc cốt lõi

`java.util.ResourceBundle` là API Java hiện hành để truy cập tài nguyên theo `Locale`, phổ biến nhất là các chuỗi giao diện đa ngôn ngữ trong tệp `.properties` hoặc các class `ListResourceBundle`. Một ứng dụng bình thường gọi `ResourceBundle.getBundle(...)` nhiều lần và nhận lợi ích từ **bộ nhớ đệm mặc định**.

Trong một ứng dụng có plugin/tenant/hot reload hoặc nhiều ClassLoader, câu hỏi trở nên phức tạp:

- Cùng base name `demo.Messages` nhưng có hai bản dịch ở hai JAR khác nhau: bản nào được trả về?
- Sửa tệp `.properties` rồi gọi `getBundle` lại: tại sao giá trị cũ có thể vẫn được trả về?
- `ResourceBundle.clearCache()` khác gì `ResourceBundle.clearCache(pluginLoader)`?
- Chuyển plugin v1 sang v2 có cần tạo ClassLoader mới không, có cần xóa cache không?
- `URLClassLoader.close()` có buộc resource bundle cũ biến mất hoặc unload class không?
- Một ứng dụng chạy **JPMS named module** có dùng `ResourceBundle.Control` để cấu hình TTL giống ứng dụng classpath được không?

**Kết luận nền tảng:** ResourceBundle **tìm bundle theo tên, locale và ngữ cảnh loader/module**, cache kết quả để tăng hiệu năng. Cache, vòng đời của ClassLoader và vòng đời nghiệp vụ của phiên bản là **ba việc khác nhau**. Xóa cache không tự đóng ClassLoader; đóng ClassLoader không sửa một bundle object cũ; GC không được bảo đảm xảy ra ngay.

Bài này tập trung vào Java **17+** và các hành vi còn đúng trong tài liệu API Java SE 25. Bài không dùng thiết kế đã legacy cho named modules.

## 2. Base name, Locale, ClassLoader: phạm vi tìm resource

Một lookup tường minh khi chạy trên **classpath/unnamed module**:

~~~java
Locale language = Locale.forLanguageTag("vi-VN");
ClassLoader loader = pluginLoader;
ResourceBundle messages =
        ResourceBundle.getBundle("demo.Messages", language, loader);
String greeting = messages.getString("greeting");
~~~

Đây là **đoạn minh họa** trong method có biến `pluginLoader` hợp lệ, cần import `java.util.Locale` và `java.util.ResourceBundle`. `demo.Messages` là **base name**, không phải đường dẫn tuyệt đối. Những tệp thông dụng trong resource path là:

~~~text
demo/Messages.properties
demo/Messages_vi.properties
demo/Messages_vi_VN.properties
~~~

JVM chọn **candidate locales** theo quy tắc ResourceBundle, tìm bundle cụ thể rồi thiết lập **parent bundle chain** cho các key bị thiếu. Nếu một resource `Messages_vi_VN` không tồn tại nhưng `Messages_vi` tồn tại, lời gọi có thể chọn bundle `vi`; nếu key không có trong bundle cụ thể, có thể lấy từ parent. `ResourceBundle#getLocale()` cho biết locale thực tế của bundle ngoài cùng được chọn, **không nhất thiết** bằng locale yêu cầu và **không tự chỉ ra** file parent nào cung cấp từng key.

Locale mặc định của JVM có thể tham gia fallback khi candidate bundles không được tìm thấy. Muốn một test không phụ thuộc `Locale.getDefault()`, dùng bộ tài nguyên kiểm soát và `Locale.ROOT` nếu mục tiêu là chỉ lấy **base bundle**.

### ClassLoader quyết định namespace tài nguyên

Đối với overload `getBundle(baseName, locale, loader)`, ClassLoader quyết định nơi tìm các tên resource và phạm vi cache liên quan. Cùng một tên, cùng Locale nhưng **hai loader độc lập thực sự** có thể lấy nội dung khác nhau:

~~~text
loader-v1  --> plugin-v1/demo/Messages.properties  --> text=old
loader-v2  --> plugin-v2/demo/Messages.properties  --> text=other

baseName = demo.Messages
locale   = Locale.ROOT
resource namespace và cache context: khác nhau theo loader
~~~

**Chú ý parent delegation:** Hai đối tượng `URLClassLoader` mới không tự động bảo đảm cách ly nếu parent loader đã có bundle cùng tên hoặc custom loader thay đổi quy tắc tìm resource. Vì vậy phải biết parent, classpath và module graph; test bằng hai resource có **giá trị khác nhau** để xác nhận không nạp nhầm cùng file.

Ngoài cách truyền loader tường minh, overload `getBundle(baseName)` và `getBundle(baseName, locale)` ở Java hiện đại hoạt động theo **caller module**. Không mặc định chúng luôn tìm qua `Thread.currentThread().getContextClassLoader()`. Nếu framework tự dựa vào TCCL, đó là hợp đồng riêng của framework; ứng dụng plugin nên truyền loading context rõ ràng.

## 3. Cache mặc định: cùng key, có thể được tái sử dụng

ResourceBundle cache theo mặc định. Đối với cách tìm bundle qua ClassLoader, Javadoc mô tả tra cache theo `baseName`, `targetLocale`, `loader` và trạng thái hiệu lực của bundle lẫn parent chain. Hệ quả:

| Thành phần ngữ cảnh | Vì sao cần xét? |
| --- | --- |
| `baseName` | `demo.Messages` và `demo.Errors` là các họ tài nguyên khác nhau |
| `Locale` | `vi`, `en`, `vi-VN` có candidate/fallback và bundle chain khác nhau |
| `ClassLoader` | Loader plugin v1/v2 có resource path và cache entry khác nhau |
| Caller `Module` / module target | Named modules có encapsulation và lookup riêng |
| Chính sách TTL/reload | Khi nào cache cần kiểm tra hoặc nạp lại |
| Trạng thái runtime | Cache entry có thể bị loại bỏ khi runtime thiếu bộ nhớ |

Một lookup lặp lại khi cache còn hiệu lực **có thể trả đúng cùng instance `ResourceBundle`**. Tuy nhiên **không được phụ thuộc instance identity tồn tại mãi**. API cho phép cache entry bị giải phóng khi có áp lực bộ nhớ, do timeout, clearCache hoặc thay đổi loading context.

### Cache âm (negative cache)

Không chỉ bundle tìm thấy mới được ghi nhớ: quá trình load có thể đặt một **dummy/negative entry** cho một candidate bundle **không tìm thấy**, để giảm lượt kiểm tra file/JAR lặp lại. Entry loại này cũng chịu chính sách expiration.

~~~text
T0: Lookup demo.NewMessages, file chưa tồn tại
T1: Tạo demo/NewMessages.properties tại nơi loader có thể nhìn thấy
T2: Lookup lại nhưng cache miss trước đó có thể còn hiệu lực
T3: Clear đúng cache / chờ validation theo policy / tạo scope mới
T4: Lookup có thể nhìn thấy bundle mới nếu loader path đúng
~~~

Đây là **diễn giải cơ chế**, không phải stdout cố định: kết quả còn phụ thuộc candidate locales, fallback, loader và TTL. Với hot deployment, đừng coi “copy tệp mới vào JAR/thư mục” là tín hiệu đủ để tất cả lookup phát hiện thay đổi tức thì.

### Đừng nhầm cache của JVM với cache tự tạo

Ví dụ một singleton host còn giữ `Map<Locale, ResourceBundle>` thì `ResourceBundle.clearCache(loader)` **không xóa map đó**. Các request đọc map vẫn thấy object cũ. Cache ứng dụng cần key phù hợp và lifecycle riêng, chẳng hạn `(tenant, version, baseName, locale)` hoặc một map nằm **bên trong version handle**.

## 4. `clearCache()` và `clearCache(ClassLoader)` khác nhau thế nào?

Tài liệu Java SE 25 định nghĩa:

~~~java
// Xóa cache bundle được nạp bởi module của caller.
ResourceBundle.clearCache();

// Xóa cache bundle được nạp bởi loader đã chỉ định.
ResourceBundle.clearCache(pluginLoader);
~~~

Đây là **mã minh họa** trong method có `pluginLoader` hợp lệ.

| Method | Phạm vi |
| --- | --- |
| `clearCache()` | Xóa những bundle trong cache được tải bởi **module của caller** |
| `clearCache(ClassLoader loader)` | Xóa những bundle trong cache được tải bởi **ClassLoader được cung cấp** |

**Không** diễn giải `clearCache()` là xóa tất cả cache toàn JVM, mọi plugin và mọi loader. Với plugin có loader riêng, hãy xét `clearCache(pluginLoader)`. Đồng thời, overload theo ClassLoader **không chỉ xóa một baseName hay một Locale**: nó có thể invalidate nhiều bundle cùng chia sẻ loader, ảnh hưởng những luồng khác đang lookup.

Việc clear có **ba giới hạn quan trọng**:

1. **Object cũ không bị sửa:** nếu `ResourceBundle old = getBundle(...)` đang được một request giữ, `old.getString("text")` vẫn có thể trả nội dung cũ ngay sau khi cache bị xóa. Cache eviction chỉ tác động lần lookup sau.
2. **ClassLoader vẫn còn:** `clearCache(loader)` không gọi `URLClassLoader.close()`, không đóng JAR handle, không đóng file/socket/thread của plugin và không làm một loader đang được host giữ trở nên unreachable.
3. **Không ép class unloading:** Java không cung cấp deadline GC/class unloading. Đóng loader, xóa cache và cho GC đủ điều kiện là các bước khác nhau.

Trong dịch vụ đa luồng, việc invalidate giữa lúc xử lý request có thể khiến request cũ dùng bundle v1 còn request mới nhìn bundle v2. Nếu nội dung cần nhất quán trong một request, hãy cấp **bundle/version handle snapshot** lúc bắt đầu request rồi chuyển version có kiểm soát.

## 5. Ví dụ Java 17+ hoàn chỉnh: hai loader, cache riêng, refresh một bên

Chương trình sau tạo tất cả dữ liệu trong **thư mục tạm**, vì vậy không cần tự chuẩn bị tệp `.properties`. Nó dùng hai `URLClassLoader`, mỗi loader trỏ tới một thư mục có `demo/Messages.properties` cùng tên nhưng khác nội dung.

Quy trình:

1. Nạp v1 và v2 với `Locale.ROOT` và loader riêng.
2. Gọi hai lần trên v1 để thấy một cache hit trong điều kiện test.
3. Sửa file v1 thành `updated`, rồi lookup trước khi clear vẫn thấy `old`.
4. Gọi `ResourceBundle.clearCache(loader1)` và lookup lại: v1 thấy `updated`.
5. Biến `first` vẫn trỏ tới bundle cũ và trả `old`.
6. V2 không bị ảnh hưởng; kết thúc bằng clear cache, đóng loader, xóa tệp tạm.

Tạo **`BundleLoaderLifecycleDemo.java`** chứa mã đầy đủ:

~~~java
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.stream.Stream;

public final class BundleLoaderLifecycleDemo {
    private static final String BASE_NAME = "demo.Messages";

    private static void write(Path versionDir, String message) throws IOException {
        Path file = versionDir.resolve("demo/Messages.properties");
        Files.createDirectories(file.getParent());
        Files.writeString(file, "text=" + message + "\n", StandardCharsets.UTF_8);
    }

    private static ResourceBundle load(ClassLoader loader) {
        return ResourceBundle.getBundle(BASE_NAME, Locale.ROOT, loader);
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("bundle-loader-");
        try {
            Path v1 = root.resolve("v1");
            Path v2 = root.resolve("v2");
            write(v1, "old");
            write(v2, "other");
            try (URLClassLoader loader1 = new URLClassLoader(
                         new URL[] {v1.toUri().toURL()},
                         ClassLoader.getPlatformClassLoader());
                 URLClassLoader loader2 = new URLClassLoader(
                         new URL[] {v2.toUri().toURL()},
                         ClassLoader.getPlatformClassLoader())) {

                ResourceBundle first = load(loader1);
                ResourceBundle again = load(loader1);
                ResourceBundle second = load(loader2);

                System.out.println("v1: " + first.getString("text"));
                System.out.println("v2: " + second.getString("text"));
                System.out.println("same-loader cache hit: " + (first == again));
                System.out.println("different-loader bundles: " + (first != second));

                write(v1, "updated");
                System.out.println("v1 before clear: " + load(loader1).getString("text"));

                ResourceBundle.clearCache(loader1);
                ResourceBundle refreshed = load(loader1);
                System.out.println("v1 after clear: " + refreshed.getString("text"));
                System.out.println("old reference still old: " + first.getString("text"));
                System.out.println("v2 untouched: " + load(loader2).getString("text"));

                ResourceBundle.clearCache(loader1);
                ResourceBundle.clearCache(loader2);
            }
            System.out.println("loaders closed: true");
        } finally {
            try (Stream<Path> stream = Files.walk(root)) {
                for (Path file : stream.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(file);
                }
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ trong thư mục chứa file:

~~~bash
javac --release 17 BundleLoaderLifecycleDemo.java
java BundleLoaderLifecycleDemo
~~~

Stdout **chính xác**, đã kiểm thử trên OpenJDK 24.0.2 với `--release 17`:

~~~text
v1: old
v2: other
same-loader cache hit: true
different-loader bundles: true
v1 before clear: old
v1 after clear: updated
old reference still old: old
v2 untouched: other
loaders closed: true
~~~

### Vì sao từng dòng xuất hiện?

- `v1: old` và `v2: other`: hai thư mục resource khác nhau, parent không có resource `demo.Messages`, nên hai loader nhìn thấy đúng tài nguyên riêng.
- `same-loader cache hit: true`: trong điều kiện test, bản v1 còn trong cache và hai lời gọi trả cùng object. **Không** suy diễn mọi lần lookup sẽ có identity giống nhau trong toàn bộ đời JVM.
- `different-loader bundles: true`: v1 và v2 không dùng chung `ResourceBundle` instance trong ví dụ.
- `v1 before clear: old`: file đã được ghi `updated` nhưng bundle đang cache vẫn là `old`.
- `v1 after clear: updated`: lookup mới sau `clearCache(loader1)` đã đọc file mới.
- `old reference still old: old`: một `ResourceBundle` object đã trao cho caller không được cache eviction mutate.
- `v2 untouched: other`: cache refresh v1 không làm nguồn tài nguyên của loader v2 đổi trong phép thử.
- `loaders closed: true`: try-with-resources đã đóng các `URLClassLoader` trước khi in; không có assertion nào về GC hay class unloading.

**Lý do dùng `Locale.ROOT`:** chỉ kiểm tra base bundle, không phụ thuộc locale mặc định của máy. File content toàn ASCII để stdout ổn định trên terminal khác nhau. Với ứng dụng thật cần test resource tiếng Việt/UTF-8 và các locale fallback. Program dùng `ClassLoader.getPlatformClassLoader()` làm parent để tránh host application loader chứa bundle trùng tên trong demo; đó không phải cấu hình bắt buộc cho mọi plugin system.

## 6. TTL và `ResourceBundle.Control` trên classpath

`ResourceBundle.Control` vẫn là API hợp lệ với ứng dụng chạy trên **classpath/unnamed module**. Nó có thể điều chỉnh danh sách candidate locales, formats, fallback, TTL và quyết định reload.

`ResourceBundle.Control.getTimeToLive(baseName, locale)` có những giá trị quan trọng:

| Giá trị | Ý nghĩa |
| --- | --- |
| `TTL_NO_EXPIRATION_CONTROL` | Bundle được cache **không có kiểm soát hết hạn**; đây là giá trị mặc định |
| `TTL_DONT_CACHE` | Bundle mới tải không được đặt vào cache |
| `0` | Entry trong cache cần được **kiểm tra lại** mỗi lần truy vấn, không đồng nghĩa luôn bắt buộc reload |
| Số mili-giây dương | Sau TTL, entry cần được kiểm tra có nên reload hay không |

Nếu TTL hết hạn, `ResourceBundle.getBundle` gọi `Control.needsReload(...)` theo hợp đồng để quyết định có cần nạp lại. Nếu method trả `false`, object cached có thể vẫn được tái sử dụng với TTL được cập nhật. **TTL hết hạn không đồng nghĩa auto reload chắc chắn.** Cache cũng có thể bị giải phóng do áp lực bộ nhớ; TTL dài không phải hợp đồng giữ object sống vĩnh viễn.

Ví dụ control không cache trên classpath:

~~~java
ResourceBundle.Control noCache = new ResourceBundle.Control() {
    @Override
    public long getTimeToLive(String baseName, Locale locale) {
        return TTL_DONT_CACHE;
    }
};

ResourceBundle bundle = ResourceBundle.getBundle(
        "demo.Messages", Locale.ROOT, pluginLoader, noCache);
~~~

Đây là **mã minh họa trong method**, cần biến `pluginLoader` và import `Locale`/`ResourceBundle`. Không trộn nhiều `Control` có chính sách khác nhau cho cùng cache context rồi giả định mỗi lời gọi hoàn toàn độc lập với entries trước đó. Xác định một chính sách nhất quán cho từng bundle family/loading scope.

### Named modules: không dùng Control overload

Trong **JPMS named module**, các overload `ResourceBundle.getBundle(..., ResourceBundle.Control)` **không được hỗ trợ** và ném `UnsupportedOperationException` theo tài liệu hiện hành. Không copy cấu hình TTL/custom formats qua `module-info.java` rồi trông đợi nguyên trạng.

Với named modules, xem `ResourceBundleProvider`, các service providers và cách tìm theo module. API như `ResourceBundle.getBundle(baseName, locale, module)` và caller-module overload có thể phù hợp hơn; cần bảo đảm module resource visibility/encapsulation và module descriptor tương ứng. Không nhầm hai overload:

~~~java
// Classpath / unnamed module:
ResourceBundle a = ResourceBundle.getBundle(
        baseName, locale, explicitLoader);

// Module-aware lookup:
ResourceBundle b = ResourceBundle.getBundle(
        baseName, locale, module);
~~~

Đây là **đoạn minh họa** với các biến do caller cung cấp. Trong named module, overload theo `ClassLoader` cũng có một số quy tắc tương đương caller-module khi loader là loader của chính caller module; đừng tự áp dụng máy móc hành vi classpath cho module graph.

## 7. Vòng đời plugin: invalidate, close và unload là ba việc khác nhau

Một quy trình thay phiên bản theo hướng an toàn:

~~~text
v1 đang hoạt động với loader-v1 / bundles-v1
      │
      ▼
1. Deploy resource/package v2 thành một artifact/version riêng
2. Tạo loader hoặc module-layer scope mới cho v2
3. Load/validate bundles v2, kiểm tra missing keys và locale fallback
4. Atomic swap active version handle: request mới dùng v2
5. Request cũ đang giữ v1 được drain/hoàn tất
6. Dừng callback/scheduler/thread, hủy listener và đăng ký dịch vụ v1
7. Xóa host caches, evict ResourceBundle cache ở scope phù hợp
8. Đóng URLClassLoader v1 nếu áp dụng và không còn load đang chạy
9. Bỏ strong refs tới bundle, plugin object, Class và loader v1
10. JVM có thể reclaim loader/class metadata về sau, không deadline
~~~

**Tại sao không chỉ `activeLoader = newLoader`?** Một host registry, cache, request đang chạy hoặc thread vẫn có thể giữ loader v1; thậm chí một `Map<Locale, ResourceBundle>` nằm trong singleton host vẫn giữ **bundle object cũ**. Khi đó:
- Giá trị cũ vẫn được request đọc sau clearCache.
- Với **class-based bundle** hoặc plugin instance thuộc loader cũ, strong-reference graph có thể tiếp tục giữ defining loader sống.
- Memory có thể tăng qua mỗi lần deploy nếu host không gỡ những reference đã hết cần.

Không phải mọi bundle object luôn giữ loader trực tiếp; đặc biệt `PropertyResourceBundle` là class thư viện chuẩn có thể chỉ giữ dữ liệu, không có đường strong-reference tới loader riêng theo mọi implementation. Vì vậy **không chẩn đoán memory leak chỉ bằng việc có cache**: hãy xem heap dump, GC roots, thread TCCL, `Class<?>`/instance và scope mà host còn giữ.

### Đóng `URLClassLoader` là gì?

`URLClassLoader.close()` giúp đóng tài nguyên JAR/URL đã mở, ngăn loader tìm thêm class/resources từ các URL của nó. Nó **không**:
- cập nhật giá trị của `ResourceBundle` đã nạp;
- xóa static map/host cache riêng;
- ngắt thread/socket hoặc đóng resource nghiệp vụ của plugin;
- ép các class đã nạp unload;
- bảo đảm loader có thể được tái sử dụng để tìm một phiên bản JAR mới.

Một bundle v1 có thể vẫn được dùng nếu caller còn reference. Đừng close loader trong lúc thread khác còn đang load resource/class qua nó. Đối với class-based `ListResourceBundle`, muốn dùng cùng class binary name với implementation bytecode mới thường phải dùng **loader mới**, vì không thể định nghĩa lại cùng class name trong loader đang có theo kiểu refresh thông thường.

### TCCL và `ThreadLocal`

Thread pool có thể sống lâu hơn version plugin. Nếu framework đặt `Thread.currentThread().setContextClassLoader(loaderV1)` mà không khôi phục, thread có thể giữ loader cũ qua TCCL. Nếu plugin có `ThreadLocal` giữ provider/bundle/implementation v1, cần `remove()` trên chính thread liên quan. Cả hai là **vấn đề lifecycle riêng**, không được giải quyết tự động bằng `ResourceBundle.clearCache`.

Mã minh họa có thể dùng:

~~~java
ClassLoader before = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    performPluginAction();
} finally {
    Thread.currentThread().setContextClassLoader(before);
}
~~~

Đoạn này đặt trong method với `pluginLoader`, `performPluginAction()` do ứng dụng cung cấp. Nhớ rằng chỉ đặt TCCL không có nghĩa `ResourceBundle.getBundle(baseName, locale)` sẽ mặc định chọn TCCL: các overload không truyền loader hoạt động theo caller module.

## 8. Fallback locale và scope cache thường bị hiểu sai

Một bundle được chọn theo locale **có thể dùng parent** cho key bị thiếu. Ví dụ:

~~~text
demo/Messages.properties          title=Default
demo/Messages_vi.properties       title=Tieu-de
demo/Messages_vi_VN.properties    country=Viet-Nam
~~~

Yêu cầu `Locale.forLanguageTag("vi-VN")` có thể cho một bundle ngoài cùng thuộc `vi_VN`; `getString("title")` lấy giá trị từ parent `vi`. Đây là hành vi fallback hợp lệ, **không phải cache trộn locale**.

- Nếu không có bundle cho target locale, quy tắc mặc định có thể xét default locale của máy rồi mới base locale.
- Nhiều bundle có thể chia sẻ parent; cache và TTL cũng liên quan đến parent chain.
- `getLocale()` cho biết locale bundle được chọn, nhưng không truy vết chính xác nguồn của từng key khi parent fallback.
- Test phải kiểm soát input files, locale yêu cầu, locale mặc định, loader/module; tránh assert kết quả theo locale của laptop developer.
- Với tài nguyên có nhiều tenant, cache host chỉ keyed bằng `Locale` sẽ dễ nhầm vì thiếu tenant, version, base name và loader/module scope.
- Nếu cần content nhất quán trong một request, tránh liên tục gọi `getBundle` giữa các bước khi có concurrent refresh; cấp bundle/version snapshot tại ranh giới request.

## 9. Vận hành: khi nào refresh và khi nào không?

### Tài nguyên bất biến theo phiên bản

Nếu translations được phát hành như **JAR/version bất biến**, cách ít rủi ro nhất thường là **loader hoặc module layer mới cho mỗi version**, kiểm tra trước, chuyển active handle và retire bản cũ có điều phối. Không phải poll file trong một JAR đang được sử dụng để cố thay resource tại chỗ.

### File tài nguyên có thể thay đổi khi ứng dụng đang chạy

Nếu dùng thư mục tài nguyên mutable và loader còn hoạt động, có thể:
- cập nhật file atomically theo khả năng nền tảng;
- invalidate `ResourceBundle.clearCache(loader)` **sau** khi bản mới đã hoàn chỉnh;
- đảm bảo host caches riêng cũng được cập nhật/evict;
- cân nhắc `Control.getTimeToLive` và `needsReload` trên classpath nếu yêu cầu;
- thử concurrency, negative cache và consistency giữa các request.

Không clear toàn bộ cache trên **mỗi request**: tăng lookup/I/O và có thể làm các thành phần khác chia sẻ loader tái tải tài nguyên ngoài dự kiến.

### Named modules và service provider

`ResourceBundleProvider` là hướng modular cho resource bundle services. Resource trong named module chịu **encapsulation**, vì vậy có thể không được tìm thấy từ module khác dù tồn tại. Cần thiết kế `uses`/`provides` và module path đúng theo service interface mà resource bundle family sử dụng. Đừng định nghĩa một loader tùy tiện rồi cho rằng nó có thể vượt qua module encapsulation.

### Đừng nhận nguồn bundle không tin cậy như code dữ liệu thông thường

Classpath ResourceBundle có thể nạp **class-based bundle** như `ListResourceBundle` (Java code), không chỉ tệp `.properties`. Nếu cho phép một JAR plugin không tin cậy chỉ để “đọc chuỗi ngôn ngữ”, class-based bundle trong JAR có thể có code thực thi khi load/khởi tạo. Cần xét duyệt artifact, dependency, resource namespace và policy thực thi. ClassLoader riêng **không phải sandbox OS**.

## 10. Kiểm thử lifecycle/cache nên có những case nào?

| Case | Kỳ vọng / mục đích |
| --- | --- |
| Cùng base name, locale, loader | Cache có thể tái sử dụng; kiểm tra giá trị và tránh assert identity vĩnh viễn |
| Cùng tên nhưng loader A/B | Test hai dữ liệu khác nhau để xác nhận scope, parent path |
| Cache sau khi sửa file | Giá trị cũ có thể tồn tại tới khi policy reload/clear |
| `clearCache(loaderA)` | Lookup A được làm mới, B không bị invalidated trong ví dụ |
| Bundle object cũ còn tham chiếu | `oldBundle.getString` có thể vẫn là giá trị cũ |
| Cache âm: file chưa có rồi được tạo | Kiểm tra behavior theo TTL/clear/loader; không mặc định phát hiện tức thời |
| Target locale và fallback | Kiểm tra `getLocale`, key từ parent, default locale |
| `Control` không cache và TTL | Test đúng classpath; hết TTL có thể chỉ validation |
| Named module resource | Test module encapsulation và provider lookup, không dùng overload Control |
| Nhiều thread cùng refresh | Không crash, biết rõ thời điểm chuyển phiên bản/snapshot |
| Đóng `URLClassLoader` | Đóng sau drain, không ép class unloading |
| Cache host / registry | Gỡ v1 và đảm bảo không còn strong-reference từ GC roots |
| Repeated deploy | Theo dõi số active version, heap/metaspace và old loaders qua nhiều vòng |
| Unicode properties | Tiếng Việt, UTF-8 và locale files đúng encoding |
| Exception/missing key | Xử lý `MissingResourceException` có ranh giới rõ, không bỏ qua silently |

### WeakReference và bằng chứng GC

Một `WeakReference<ClassLoader>` có thể dùng để **quan sát** loader sau khi retire và xóa strong references:

~~~java
WeakReference<ClassLoader> weak = new WeakReference<>(pluginLoader);
ClassLoader observed = weak.get(); // Có thể còn sống hoặc đã được GC.
boolean cleared = observed == null;
observed = null;                   // Tránh giữ strong reference mới.
~~~

Đây là đoạn minh họa trong method có `pluginLoader`, cần import `java.lang.ref.WeakReference`. Không viết test `System.gc()` rồi đòi `weak.get() == null` trong 100 ms: GC không có deadline. Một loader còn sống **không nhất thiết leak** (có thể request cũ chưa drain). Phải tìm **đường giữ reference từ GC roots** sau khi version đã được retire.

## 11. Những hiểu lầm dẫn đến lỗi

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “ResourceBundle chỉ cache theo base name.” | Cần xét locale, loader/module và cache policy |
| “Đổi file là `getBundle` tự thấy nội dung mới.” | Cache mặc định có thể trả dữ liệu cũ |
| “`clearCache()` sẽ xóa mọi plugin trong JVM.” | Phạm vi theo caller module, không toàn JVM |
| “`clearCache(loader)` chỉ xóa một key.” | Nó áp dụng cache bundles theo loader, không chọn riêng baseName |
| “Xóa cache sẽ mutate mọi object đã được phát ra.” | Bundle reference cũ vẫn trả giá trị cũ |
| “Đóng URLClassLoader là unload class.” | Close resource khác với GC/class unloading |
| “Nếu v1 chưa được GC tức là leak.” | JVM có thể chưa GC hoặc vẫn còn in-flight work |
| “TTL 0 nghĩa là reload chắc chắn.” | Chỉ yêu cầu kiểm tra; `needsReload` quyết định |
| “`TTL_DONT_CACHE` giống `TTL_NO_EXPIRATION_CONTROL`.” | Một bên không cache, một bên cache không đặt expiration |
| “`ResourceBundle.Control` dùng y hệt trong named modules.” | Overload có Control không được hỗ trợ |
| “Thay TCCL sẽ khiến mọi getBundle luôn tìm ở TCCL.” | Không đúng cho các overload dựa vào caller module |
| “Host cache cũng được ResourceBundle.clearCache xóa.” | Cache riêng phải tự invalidate |
| “Hai loader luôn tách bundle.” | Parent có thể cung cấp cùng resource |
| “Chỉ dùng bundle để đọc text nên JAR untrusted an toàn.” | Bundle có thể là class-based code, cần trust boundary |

## 12. Câu hỏi tự kiểm tra

1. **Hai plugin có cùng `demo.Messages` và `Locale.ROOT` có thể trả bundle khác nhau khi nào?** Khi chúng thật sự tìm qua các loader/module scope khác nhau và parent không chiếm bundle trùng tên.
2. **`ResourceBundle.clearCache()` áp dụng scope nào?** Caller module theo Java SE 25.
3. **`clearCache(loaderA)` có làm `oldBundleA` đổi `text` không?** Không. Object cũ vẫn có thể được giữ.
4. **Sửa file trong loader A có luôn hiện ngay không?** Không; phải xét cache/TTL/invalidation.
5. **`Locale.ROOT` trong demo giúp gì?** Làm lookup chỉ dùng base bundle, tránh phụ thuộc locale mặc định của máy.
6. **TTL 0 có đồng nghĩa luôn tạo ResourceBundle instance mới?** Không; `needsReload` có thể cho giữ entry cũ.
7. **Hai hằng TTL đặc biệt khác nhau thế nào?** Không cache so với cache không có expiration control.
8. **`URLClassLoader.close()` có làm class cũ unload ngay?** Không.
9. **Trong JPMS named module, nên tùy biến resource bundle bằng API nào?** Thiết kế `ResourceBundleProvider` và module-aware lookup; tránh Control overload.
10. **Vì sao `Map<Locale, ResourceBundle>` ở singleton có thể nguy hiểm?** Thiếu tenant/version/loader scope và có thể giữ bundle cũ sau clearCache.
11. **Có thể dùng `System.gc()` để xác nhận lifecycle đã dọn đúng không?** Không, cần theo dõi references, cache host, active jobs và heap/GC roots.
12. **Nếu bản dịch tiếng Việt thiếu một key, có nhất thiết throw ngay không?** Không; có thể fallback qua parent bundle.

## 13. Tài liệu chính thức còn áp dụng

- [Java SE 25 — ResourceBundle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ResourceBundle.html): `getBundle`, scope của `clearCache`, cache, fallback và module system.
- [Java SE 25 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ResourceBundle.Control.html): `TTL_NO_EXPIRATION_CONTROL`, `TTL_DONT_CACHE`, `getTimeToLive` và `needsReload`.
- [Java SE 25 — ResourceBundleProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/ResourceBundleProvider.html): service-provider hướng modular.
- [Java SE 25 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/PropertyResourceBundle.html): properties-backed bundle và encoding.
- [Java SE 25 — URLClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): đóng URL/JAR resources và giới hạn của `close()`.
- [Java SE 25 — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, class/resource namespace.
- [Java SE 25 — Locale](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): `Locale.ROOT`, fallback và locale tags.
- [Java SE 25 — WeakReference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/WeakReference.html): quan sát mà không giữ referent sống.

**Tổng kết:** `ResourceBundle` cache theo loading context; ClassLoader/module quyết định nguồn tài nguyên nhìn thấy; ứng dụng quyết định lúc một phiên bản được dùng và lúc dọn nó. `clearCache(loader)` **không** sửa bundle cũ, không đóng loader và không ép GC. Với hot reload, ưu tiên scope/version mới, kiểm thử, chuyển active handle, drain phiên bản cũ, dọn host cache và resource, sau đó để JVM quyết định khi nào có thể thu hồi loader.