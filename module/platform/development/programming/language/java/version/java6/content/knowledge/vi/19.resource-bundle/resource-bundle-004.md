# Thời gian lưu, needsReload và quản lý bộ nhớ đệm của ResourceBundle trong Java

`java.util.ResourceBundle` cung cấp cơ chế tải nội dung đa ngôn ngữ (*internationalization/i18n*), chẳng hạn văn bản giao diện, thông báo lỗi và nhãn theo `Locale`. Khi gọi `ResourceBundle.getBundle(...)`, Java **không nhất thiết đọc lại tệp `.properties` mỗi lần**: các bundle đã tìm được thường được lưu trong **cache** để giảm chi phí tìm kiếm, tải và xây dựng chuỗi fallback locale.

Nếu một ứng dụng thay đổi tệp dịch lúc đang chạy, bản dịch cũ có thể vẫn xuất hiện. Hai điểm kiểm soát quan trọng là:

- `ResourceBundle.Control.getTimeToLive(...)`: một bundle có thể ở cache trong bao lâu **trước khi cần kiểm tra lại**;
- `ResourceBundle.Control.needsReload(...)`: khi bundle **đã hết TTL**, có thực sự cần tải bundle mới hay không.

Bên cạnh đó, `ResourceBundle.clearCache()` và `clearCache(ClassLoader)` giúp chủ động xóa entry trong phạm vi phù hợp.

**Điều cốt lõi:** TTL **không phải bộ hẹn giờ tự tải lại**; hết TTL **không đồng nghĩa dữ liệu lập tức thay đổi**; `needsReload() == false` có thể giữ instance cũ và thiết lập lại hạn xác minh; `clearCache` cũng không tự sửa những biến đang giữ tham chiếu đến bundle cũ.

Những API này đã có từ Java 6 và **vẫn tồn tại trên Java 17+ cùng JDK hiện hành**. Tuy nhiên, có giới hạn rất quan trọng đối với **JPMS named modules**: cách gọi `getBundle(..., ResourceBundle.Control)` không được hỗ trợ khi caller nằm trong named module. Bài tập tùy biến `Control` trong bài được chạy trên **classpath/unnamed module**, không trình bày nó như một giải pháp áp dụng trực tiếp cho mọi module hiện đại.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Mô tả vòng đời một `ResourceBundle`: tìm kiếm, tạo bundle, cache, TTL, kiểm tra thay đổi và nạp lại.
2. Giải thích chính xác `TTL_DONT_CACHE`, `TTL_NO_EXPIRATION_CONTROL`, TTL bằng `0` và TTL dương.
3. Biết khi nào JVM gọi `needsReload(...)`, các tham số của hàm và kết quả `true`/`false`.
4. Phân biệt `getTimeToLive` với `newBundle`, đặc biệt tham số `reload`.
5. Sử dụng `clearCache()` và `clearCache(ClassLoader)` có ý thức về phạm vi, tham chiếu cũ và hiệu năng.
6. Thử nghiệm một `Control` thực tế **không cần chờ đồng hồ hay sửa timestamp tệp**, có kết quả ổn định trên Java 17+.
7. Lựa chọn chính sách cache phù hợp cho resource bất biến trong JAR, bản dịch file có thể thay đổi và dịch vụ đa luồng.
8. Tránh sử dụng sai `Control` trong named module, rò classloader hoặc gây quá tải I/O bằng chính sách reload quá gắt.

## 2. ResourceBundle: từ locale tới dữ liệu và cache

Giả sử dự án classpath có các tài nguyên:

```text
src/main/resources/messages/Labels.properties
src/main/resources/messages/Labels_vi.properties
src/main/resources/messages/Labels_en.properties
```

Nội dung minh họa:

```properties
# messages/Labels.properties
greeting=Hello
cancel=Cancel
```

```properties
# messages/Labels_vi.properties
greeting=Xin chào
cancel=Hủy
```

Đoạn Java đọc bản dịch:

```java
import java.util.Locale;
import java.util.ResourceBundle;

// Mảnh code đặt trong main/method của ứng dụng:
ResourceBundle labels = ResourceBundle.getBundle(
        "messages.Labels", Locale.forLanguageTag("vi"));
String greeting = labels.getString("greeting");
System.out.println(greeting); // Xin chào, nếu resource được đặt đúng classpath
```

Trong `getBundle("messages.Labels", locale)`, Java tìm bản dịch phù hợp với locale được yêu cầu, cùng những candidate và fallback cần thiết. Nó có thể thiết lập **parent chain** để một key không có trong bản dịch chuyên biệt rơi về bản gốc.

### Điều gì được cache?

Các bundle do `getBundle` tạo được **cache mặc định**, vì tìm tệp nguồn, khởi tạo bundle và xây dựng parent chain có chi phí. Cache cho phép những lần yêu cầu tiếp theo tái sử dụng dữ liệu thay vì tải lại không cần thiết.

Trong classpath/unnamed-module workflow của bài, identity để tra cứu cache liên quan đến **base name, locale và classloader**. Đừng cho rằng hai classloaders hoặc hai named modules đương nhiên dùng chung một cache entry. Nếu thay đổi cách tạo bundle bằng hai `Control` khác nhau cho cùng base/locale/loader, **cache đã có vẫn có thể ảnh hưởng kết quả**; không nên trộn chính sách formats/fallback một cách ngẫu nhiên.

Một số đặc điểm:

- Bundle tìm được có thể giữ một `ResourceBundle` instance và parent chain của nó.
- Những ứng viên bundle **không tồn tại** cũng có thể được ghi nhận bằng một *negative cache entry* để tránh tra cứu lại vô ích, chịu các quy tắc hết hạn tương ứng.
- Cache **không giữ mạnh vô điều kiện mọi bundle mãi mãi**: runtime có thể thu hồi cache entry dưới áp lực bộ nhớ.
- `ResourceBundle.getBundle` là nơi áp dụng TTL và refresh. Gọi `bundle.getString(...)` trên **instance bạn đã giữ** không khởi động quá trình `getBundle` mới.
- Đổi file trên ổ đĩa hoặc đổi giá trị `Locale.getDefault()` không có nghĩa mọi biến `ResourceBundle` đang tồn tại tự cập nhật.

## 3. Bốn chế độ TTL và ý nghĩa chính xác

`ResourceBundle.Control.getTimeToLive(String baseName, Locale locale)` trả về một `long`. Giá trị hợp lệ là:

| Giá trị | Ý nghĩa | Khi thích hợp |
| --- | --- | --- |
| `TTL_NO_EXPIRATION_CONTROL` | **Không kiểm soát hết hạn**: entry được cache và không bị xác minh thời gian theo TTL. | Bundle tương đối bất biến, ví dụ bản dịch đóng gói trong bản phát hành. |
| `TTL_DONT_CACHE` | **Không cache** bundle được tải. | Một số thử nghiệm hoặc nguồn dữ liệu cần tránh cache; chi phí tải tăng cao. |
| `0L` | Cache nhưng **kiểm tra hết hạn mỗi lần lấy lại qua `getBundle`**. | Test, hoặc hệ thống rất cần phát hiện phiên bản mới và chấp nhận chi phí kiểm tra. |
| Số nguyên dương, ví dụ `30_000L` | Cache và không kiểm tra lại nguồn trong khoảng TTL đó, tính bằng **milliseconds**. | Bản dịch có thể cập nhật nhưng chấp nhận độ trễ kiểm tra khoảng 30 giây. |

**Đây là hai hằng số riêng**, không phải một “TTL = 0” chung. Dùng tên hằng `ResourceBundle.Control.TTL_DONT_CACHE` và `TTL_NO_EXPIRATION_CONTROL`; không viết cứng các số âm vào code ứng dụng. Giá trị âm khác hai hằng số là không hợp lệ theo hợp đồng API.

**Mặc định**, `ResourceBundle.Control.getTimeToLive` trả về `TTL_NO_EXPIRATION_CONTROL`.

### TTL không phải “thời gian sống tối đa của một object”

Với TTL 30 giây:

1. Một lần `getBundle` tải bundle lúc 10:00:00.
2. Các lần `getBundle` trước khi TTL hết thường tái sử dụng cache **mà không gọi `needsReload`**.
3. Sau khi TTL hết, **lần `getBundle` tiếp theo** mới có cơ hội gọi `needsReload`.
4. Nếu nguồn **không đổi** và `needsReload` trả `false`, entry cũ có thể tiếp tục được dùng với TTL được làm mới.
5. Nếu trả `true`, cache loại entry cũ và hệ thống thử gọi `newBundle` để tạo bản mới.

Không có một background timer nào được `ResourceBundle.Control` hứa hẹn sẽ chạy đúng mốc hết hạn. Nếu không có request mới, việc kiểm tra có thể không diễn ra.

Một TTL rất dài **không khóa object ở RAM**; JVM vẫn có thể bỏ entry khỏi cache do hạn chế bộ nhớ. Ngược lại, một object mà ứng dụng vẫn giữ qua biến/field **không bị tự hủy** chỉ vì cache của `ResourceBundle` đã xóa entry đó.

## 4. Khi nào `needsReload` được gọi?

Chữ ký hiện hành:

```java
public boolean needsReload(
        String baseName,
        Locale locale,
        String format,
        ClassLoader loader,
        ResourceBundle bundle,
        long loadTime)
```

Giải nghĩa:

| Tham số | Mô tả |
| --- | --- |
| `baseName` | Tên gốc của nhóm bundle, như `"messages.Labels"`. |
| `locale` | Locale của bundle đang được kiểm tra, có thể là `Locale.ROOT`. |
| `format` | Dạng nguồn đã dùng, ví dụ `"java.class"` hoặc `"java.properties"`. |
| `loader` | `ClassLoader` được dùng để tìm/tải bundle trong classpath. |
| `bundle` | **Instance đã cache và đã hết TTL** mà cần xác minh có còn hợp lệ không. |
| `loadTime` | Thời điểm bundle được tạo/đưa vào cache, tính bằng **milliseconds kể từ epoch**. |

`needsReload` trả:

- `true`: bundle cũ không còn hợp lệ; `getBundle` bỏ cache entry và tiến hành tải lại.
- `false`: bundle còn hợp lệ; `getBundle` có thể tiếp tục dùng bundle đã cache, đồng thời làm mới thời hạn kiểm tra tiếp theo theo TTL.
- API có thể ném lỗi nếu tham số không hợp lệ; khi tự override cần xử lý dữ liệu nguồn/exception nhất quán với yêu cầu build/runtime.

**Điểm dễ bị bỏ sót:** `getBundle` gọi `needsReload` trên **đối tượng `Control` được truyền trong lần gọi hiện tại**, không nhất thiết là cùng object Control đã dùng khi bundle lần đầu được tải. Vì vậy `Control` nên được thiết kế với chính sách ổn định, thread-safe; không trộn Control có formats/fallback không tương thích trên một vùng cache.

### 4.1. Hành vi mặc định của `needsReload`

Implementation mặc định đối với các nguồn tiêu chuẩn so sánh `loadTime` với **last-modified timestamp** của source bundle. Nếu xác định source đã được sửa sau khi bundle được tải, trả `true`; ngược lại `false`.

Điều đó có nghĩa:

- TTL hết nhưng file chưa đổi → `needsReload` có thể trả `false`.
- File mới đổi sau khi bundle được tải → nếu metadata/thời gian sửa thay đổi và implementation nhìn thấy đúng nguồn, có thể trả `true`.
- File có timestamp granularity thấp, bên trong JAR, resource từ remote/filesystem ảo, hoặc URLConnection caching có thể khiến việc phát hiện thay đổi không như bạn kỳ vọng.
- Last-modified không phải một cơ chế *distributed invalidation* hay đảm bảo tuyệt đối source không đổi; nó chỉ là một cách xác minh.

**`needsReload` không sửa file, không tự thay nội dung trong instance cũ và không quyết định thời điểm gọi lại `getBundle`.**

### 4.2. Đừng nhầm TTL 0 với `TTL_DONT_CACHE`

Với `TTL=0`, một bundle **vẫn có thể được cache**, chỉ phải xác minh mỗi lần truy cập qua `getBundle`. Nếu `needsReload(...) == false`, lần kế tiếp có thể trả lại **chính instance cũ**.

Với `TTL_DONT_CACHE`, runtime **không đặt bản đã tải vào cache**, nên các lần `getBundle` tiếp theo có thể phải gọi `newBundle` để tạo đối tượng mới. `needsReload` không phải cơ chế chính của mode này, vì không có entry expired cần xác minh.

Đây là khác biệt quan trọng nhất khi tối ưu hóa performance: `TTL=0` có thể tốn công kiểm tra thay đổi **nhưng tránh xây bundle lại**, còn no-cache có thể tốn toàn bộ công đọc/parse/khởi tạo nhiều lần.

## 5. `newBundle`, `reload=true` và việc nạp file thật

Chữ ký của callback tạo bundle:

```java
public ResourceBundle newBundle(
        String baseName,
        Locale locale,
        String format,
        ClassLoader loader,
        boolean reload)
        throws IllegalAccessException, InstantiationException, IOException
```

- `newBundle` được gọi khi `ResourceBundle.getBundle` cần một bundle chưa có trong cache, hoặc khi bundle cũ không còn hợp lệ.
- `reload == true` cho biết đang nạp lại sau khi entry đã hết hạn; không nên bỏ qua flag này nếu nguồn bên dưới còn một tầng cache riêng.
- Khi `format == "java.properties"`, implementation mặc định sử dụng `URL`/`URLConnection` và **vô hiệu hóa cache của kết nối bên dưới** khi `reload==true`. Điều này giúp không tái đọc dữ liệu đã cache ở tầng URL.
- Khi `format == "java.class"`, implementation mặc định **không dùng flag `reload` để nạp lại định nghĩa class**. Classloader thường không thể “biến đổi” một class đã nạp thành class mới chỉ vì TTL.
- Với format tùy biến hoặc bundle từ DB/API, người viết `newBundle` chịu trách nhiệm đọc phiên bản dữ liệu chính xác và xử lý lỗi I/O.

Nếu mục tiêu là hot reload tài nguyên văn bản, **properties-based bundles** thường phù hợp hơn class-based bundles. Nếu tệp dịch được đóng gói cứng trong JAR của ứng dụng, chiến lược vận hành đáng tin thường là **phát hành phiên bản mới/restart hoặc thay classloader**, không phải giả định có thể ghi đè JAR rồi JVM tự nhận.

## 6. Ví dụ Java 17+ đầy đủ: TTL 0, needsReload, clearCache và hai hằng TTL

Ví dụ sau dùng một bundle **giả lập nằm trong bộ nhớ**, dữ liệu được đánh phiên bản bằng `AtomicInteger`. Nó cố ý **không dùng `Thread.sleep`, file mtime hay wall-clock timer** để kết quả ổn định trong IDE/CI/JDK khác nhau. Dữ liệu vẫn đi qua API thật `ResourceBundle.getBundle` và `ResourceBundle.Control`.

Một `VersionControl` có các thành phần:

- `revision`: phiên bản nguồn giả lập (1 → 2).
- `loads`: đếm số lần `newBundle` tạo bundle.
- `checks`: đếm số lần `needsReload` được gọi.
- `ttl`: chế độ cache đang thử nghiệm.

`SnapshotBundle` giữ giá trị phiên bản khi được tạo. Nếu nguồn giả lập đổi revision, object cũ **không tự đổi**.

### 6.1. Tạo file `ResourceBundleCacheDemo.java`

```java
import java.io.IOException;
import java.util.List;
import java.util.ListResourceBundle;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.concurrent.atomic.AtomicInteger;

public final class ResourceBundleCacheDemo {
    private static final String BASE = "demo.Messages";

    private static final class SnapshotBundle extends ListResourceBundle {
        private final int revision;

        SnapshotBundle(int revision) {
            this.revision = revision;
        }

        @Override
        protected Object[][] getContents() {
            return new Object[][] {{"label", "version-" + revision}};
        }
    }

    private static final class VersionControl extends ResourceBundle.Control {
        final AtomicInteger revision = new AtomicInteger(1);
        final AtomicInteger loads = new AtomicInteger();
        final AtomicInteger checks = new AtomicInteger();
        final long ttl;

        VersionControl(long ttl) {
            this.ttl = ttl;
        }

        @Override
        public List<String> getFormats(String baseName) {
            return FORMAT_CLASS;
        }

        @Override
        public List<Locale> getCandidateLocales(String baseName, Locale locale) {
            return List.of(Locale.ROOT);
        }

        @Override
        public Locale getFallbackLocale(String baseName, Locale locale) {
            return null;
        }

        @Override
        public long getTimeToLive(String baseName, Locale locale) {
            return ttl;
        }

        @Override
        public boolean needsReload(String baseName, Locale locale, String format,
                ClassLoader loader, ResourceBundle bundle, long loadTime) {
            checks.incrementAndGet();
            return ((SnapshotBundle) bundle).revision != revision.get();
        }

        @Override
        public ResourceBundle newBundle(String baseName, Locale locale,
                String format, ClassLoader loader, boolean reload)
                throws IllegalAccessException, InstantiationException, IOException {
            loads.incrementAndGet();
            return new SnapshotBundle(revision.get());
        }
    }

    private static ResourceBundle get(VersionControl control, ClassLoader loader) {
        return ResourceBundle.getBundle(BASE, Locale.ROOT, loader, control);
    }

    public static void main(String[] args) {
        ClassLoader loader = ResourceBundleCacheDemo.class.getClassLoader();
        ResourceBundle.clearCache(loader);

        VersionControl ttlZero = new VersionControl(0);
        ResourceBundle first = get(ttlZero, loader);
        ResourceBundle same = get(ttlZero, loader);
        System.out.println("first=" + first.getString("label"));
        System.out.println("sameInstance=" + (first == same));
        System.out.println("initialChecks=" + ttlZero.checks.get());

        ttlZero.revision.set(2);
        ResourceBundle updated = get(ttlZero, loader);
        System.out.println("afterChange=" + updated.getString("label"));
        System.out.println("reloaded=" + (first != updated));
        System.out.println("checksAfterChange=" + ttlZero.checks.get());
        System.out.println("loadsAfterChange=" + ttlZero.loads.get());

        ResourceBundle.clearCache(loader);
        ResourceBundle afterClear = get(ttlZero, loader);
        System.out.println("afterClearNew=" + (updated != afterClear));
        System.out.println("loadsAfterClear=" + ttlZero.loads.get());

        ResourceBundle.clearCache(loader);
        VersionControl neverExpire =
                new VersionControl(ResourceBundle.Control.TTL_NO_EXPIRATION_CONTROL);
        ResourceBundle stable = get(neverExpire, loader);
        neverExpire.revision.set(2);
        ResourceBundle stableAgain = get(neverExpire, loader);
        System.out.println("noExpirationSame=" + (stable == stableAgain));
        System.out.println("noExpirationValue=" + stableAgain.getString("label"));
        System.out.println("noExpirationChecks=" + neverExpire.checks.get());

        ResourceBundle.clearCache(loader);
        VersionControl dontCache =
                new VersionControl(ResourceBundle.Control.TTL_DONT_CACHE);
        ResourceBundle uncachedOne = get(dontCache, loader);
        ResourceBundle uncachedTwo = get(dontCache, loader);
        System.out.println("dontCacheDifferent=" + (uncachedOne != uncachedTwo));
        System.out.println("dontCacheLoads=" + dontCache.loads.get());
        System.out.println("dontCacheChecks=" + dontCache.checks.get());

        ResourceBundle.clearCache(loader);
    }
}
```

### 6.2. Biên dịch và chạy

Trong một thư mục chỉ chứa tệp này:

```bash
javac --release 17 -encoding UTF-8 ResourceBundleCacheDemo.java
java ResourceBundleCacheDemo
```

**Stdout đầy đủ — đã kiểm chứng thực tế bằng `javac/java` trên JDK 24:**

```text
first=version-1
sameInstance=true
initialChecks=1
afterChange=version-2
reloaded=true
checksAfterChange=2
loadsAfterChange=2
afterClearNew=true
loadsAfterClear=3
noExpirationSame=true
noExpirationValue=version-1
noExpirationChecks=0
dontCacheDifferent=true
dontCacheLoads=2
dontCacheChecks=0
```

Ví dụ **không cần `Messages.properties` trên đĩa**. `VersionControl.newBundle` trả `SnapshotBundle` trực tiếp, trong khi tham số `BASE` được dùng làm danh tính để thử nghiệm bộ nhớ đệm. Chạy trên **classpath/unnamed module** vì `getBundle(..., Control)` không hỗ trợ khi caller là named module.

### 6.3. Phân tích 15 dòng output

**TTL = 0, nhưng chưa thay source:**

- `first=version-1`: lần đầu `newBundle` tạo snapshot.
- `sameInstance=true`: `getBundle` lần hai gọi `needsReload`, thấy revision vẫn là 1 nên tiếp tục dùng **cùng instance**.
- `initialChecks=1`: một lần xác minh đã diễn ra; TTL bằng 0 không bắt buộc reload.

**TTL = 0, source đổi version:**

- `ttlZero.revision.set(2)` mô phỏng nguồn được sửa.
- Lần `getBundle` kế tiếp gọi `needsReload`; so revision của bundle cũ với nguồn mới khác nhau nên trả `true`.
- `afterChange=version-2` và `reloaded=true`: instance mới đã được tạo.
- `checksAfterChange=2`, `loadsAfterChange=2`: đã có tổng hai lượt kiểm tra, hai lượt tạo bundle.

**Chủ động `clearCache(loader)`:**

- `afterClearNew=true`: lần `getBundle` sau clear trả object mới dù source chưa đổi.
- `loadsAfterClear=3`: không cần chờ TTL; lần tải thứ ba đã diễn ra.
- **Biến `updated` vẫn trỏ object cũ** nếu code giữ nó. Cache invalidation không ép các biến đã được trao đi cập nhật.

**Không kiểm soát hết hạn:**

- Khi `TTL_NO_EXPIRATION_CONTROL`, dù nguồn giả lập đổi từ 1 sang 2, `noExpirationSame=true` và `noExpirationValue=version-1`.
- `noExpirationChecks=0`: không có validate TTL trong lần lookup thứ hai.

**Không cache:**

- `TTL_DONT_CACHE` khiến hai lượt lấy bundle không dùng chung instance: `dontCacheDifferent=true`.
- `dontCacheLoads=2`, `dontCacheChecks=0`: tải hai lần, không có expired cached entry để kiểm tra.

### 6.4. Tại sao ví dụ dùng `AtomicInteger`?

`AtomicInteger` đảm bảo bộ đếm được cập nhật an toàn ở mức thao tác nguyên tử nếu `Control` có thể bị dùng đồng thời. Đây không phải một hệ thống cache đa luồng hoàn chỉnh: nguồn giả lập và các trạng thái khác cần được quản lý nhất quán. `ResourceBundle.Control` **có thể bị các luồng khác nhau gọi đồng thời mà không có synchronization của `getBundle` quanh callback**, nên class `Control` tự viết cần thread-safe.

Demo chỉ dùng một luồng, nhưng sử dụng AtomicInteger để minh họa một cách lưu revision/counters không phụ thuộc biến static toàn cục. Cache cleanup ở cuối không thay đổi những object cũ mà code còn giữ.

## 7. Cấu hình TTL thực tế cho tệp `.properties`

Với bộ resource `messages/Labels.properties` như mục 2, nếu ứng dụng chạy **classpath** và muốn kiểm tra nguồn khoảng 30 giây/lần, có thể override `getTimeToLive` nhưng **giữ `needsReload` mặc định**:

```java
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;

public final class PropertiesTtlControl extends ResourceBundle.Control {
    @Override
    public List<String> getFormats(String baseName) {
        return FORMAT_PROPERTIES;
    }

    @Override
    public long getTimeToLive(String baseName, Locale locale) {
        return 30_000L; // 30 giây: sau đó xác minh khi có lần getBundle mới
    }
}
```

Đây là **class độc lập có thể biên dịch trên Java 17+**, nhưng chưa có `main`; dùng tại ứng dụng classpath:

```java
// Mảnh tích hợp bên trong method/class của ứng dụng:
ClassLoader loader = Thread.currentThread().getContextClassLoader();
ResourceBundle labels = ResourceBundle.getBundle(
        "messages.Labels",
        Locale.forLanguageTag("vi"),
        loader,
        new PropertiesTtlControl());
String text = labels.getString("greeting");
```

**Lưu ý quan trọng:**

1. `FORMAT_PROPERTIES` chỉ tìm tệp `.properties`, tránh xung đột với class-based bundles cùng tên.
2. Sau khoảng 30 giây **và khi code gọi lại `getBundle`**, cache mới cần xác minh dữ liệu nguồn. Không có timer tự refresh khi service không gọi.
3. Default `needsReload` so last-modified timestamp với thời gian tải. Nếu source không có timestamp đáng tin hoặc nằm trong JAR không thay đổi, reload có thể không phát hiện như ý định.
4. Nếu `needsReload` trả `true`, default `newBundle` cho properties-based format chú ý flag `reload` và tắt URLConnection cache phù hợp.
5. Nếu code vẫn giữ `labels` trong một singleton và chỉ gọi `labels.getString`, nó sẽ **không gọi lại `getBundle`**, nên TTL không được áp dụng.
6. Context classloader ở ví dụ cần **khác null và trỏ đúng nguồn**. Trong server/plugin/container, hãy dùng classloader được hệ thống thiết kế dành cho bundles; không lấy ngẫu nhiên một loader không sở hữu tài nguyên.
7. Đừng tạo một `PropertiesTtlControl` mới với policy formats/TTL khác rồi kỳ vọng cache cũ luôn độc lập. Cache đã có vẫn có thể ảnh hưởng lần getBundle tiếp theo.

Với resource đóng gói trong JAR bất biến, tùy biến TTL để hỗ trợ sửa live file thường không đem lại lợi ích thực tế. Với resource được phép chỉnh khi ứng dụng chạy, cân nhắc đặt nó trong một **filesystem location do ứng dụng kiểm soát** và thiết kế loader/versioning riêng thay vì ghi trực tiếp vào JAR đã được triển khai.

## 8. Tự override `needsReload` khi nào?

Cách xác minh last-modified mặc định không phải lúc nào cũng phù hợp với nguồn dữ liệu:

- Bundle đến từ database/API, không có file mtime.
- Nguồn có **version number**, `ETag` hoặc checksum riêng.
- Nguồn lưu trong object storage hoặc mounted filesystem có metadata timestamp không ổn định.
- Cần quy tắc phân phối phiên bản giữa nhiều máy, tránh lệ thuộc clock của từng host.

Một `needsReload` tự viết có thể so version của bundle với version nguồn, tương tự demo. Khi dùng metadata ở hệ thống thật, code thường cần:

1. Lấy metadata tương đối nhẹ (version, ETag) thay vì download toàn bộ dữ liệu.
2. So với version mà bundle hiện tại đang giữ.
3. Trả `true` khi thật sự khác.
4. `newBundle` phải thực sự tải snapshot tương ứng với version mới, không tiếp tục trả nội dung do tầng HTTP/cache riêng giữ lại.
5. Xử lý I/O failure, timeout, retry/backoff và dữ liệu không nhất quán có policy rõ ràng.
6. Giới hạn tần suất check bằng TTL phù hợp; không gọi metadata endpoint mỗi request nếu không cần.

### 8.1. Không tự coi `loadTime` là “thời gian nguồn cập nhật”

`loadTime` là thời gian bundle được tải/đưa vào cache, **không phải** timestamp nguồn dữ liệu đang giữ. Với nguồn từ DB/API, nên dùng một version/timestamp của **nguồn thực tế** nếu có. So `System.currentTimeMillis() - loadTime > X` trong `needsReload` chỉ kiểm tra tuổi snapshot, không chứng minh dữ liệu đã thay đổi. Nếu muốn reload sau mỗi đợt TTL bất kể dữ liệu nguồn, cần nêu rõ đó là chính sách *forced refresh*, có thể tăng tải đáng kể.

### 8.2. Nguyên tắc xử lý lỗi khi kiểm tra nguồn

- Metadata endpoint timeout không có nghĩa phiên bản đã đổi; nếu chọn dùng lại bundle cũ (*stale-if-error*), ứng dụng phải chấp nhận rủi ro hiển thị bản dịch cũ và log có giám sát.
- Với dữ liệu liên quan đến an ninh/quyền truy cập, đừng áp dụng stale-if-error như chính sách mặc định; ResourceBundle thường dùng cho text hiển thị, không phải nơi chứa access policy.
- `needsReload` không có khai báo checked `throws IOException`, nên nếu thao tác kiểm tra có lỗi, bạn phải quyết định exception unchecked/giữ bundle cũ với log thay vì lén bỏ qua mọi sự cố.
- `newBundle` có thể ném `IOException` và những checked exception được khai báo. Hãy để caller nhận biết việc refresh thất bại hoặc có fallback đã định nghĩa; không biến lỗi dữ liệu thành chuỗi trống.
- Nếu dữ liệu mới bị lỗi format, cần lựa chọn giữa fail fast, giữ bản đã xác minh gần nhất, hoặc rollback từ nguồn; ResourceBundle TTL thuần không phải một hệ thống versioned-config deployment hoàn chỉnh.

## 9. `clearCache`: chủ động loại bỏ entry mà không chờ TTL

Hai phương thức:

```java
ResourceBundle.clearCache();
ResourceBundle.clearCache(loader);
```

- `clearCache()`: xóa các bundles khỏi cache trong **phạm vi module của caller** theo hợp đồng API hiện hành. Không nên mô tả nó như một phép xóa tất cả cache của mọi ứng dụng/JVM.
- `clearCache(ClassLoader loader)`: loại bỏ bundles gắn với **classloader được chỉ định**. Tham số null là không hợp lệ.
- Hai method là static, trả `void`; chúng không làm thay đổi nội dung file, không buộc mọi consumer bỏ tham chiếu `ResourceBundle` đã giữ và không bảo đảm hệ thống liên quan được làm mới đồng thời.
- Khi gọi lại `getBundle` sau clear, runtime cần tải/tìm lại những entries cần thiết, nên có thể tạo một spike I/O/CPU.
- `clearCache` cũng quan trọng trong **tests** khi từng test muốn bắt đầu ở trạng thái cache sạch, nhưng phải cẩn thận nếu các tests chạy song song và dùng chung classloader.

### Khi nào nên clear?

| Tình huống | Có nên gọi `clearCache`? |
| --- | --- |
| Người vận hành yêu cầu reload sau khi cập nhật bản dịch | Có thể, nếu classloader/bundle scope được kiểm soát; thay thế reference cũ bằng kết quả `getBundle` mới. |
| Thay file trong JAR bất biến mà không thay classloader | Clear cache không bảo đảm nạp được nội dung mới; cần kế hoạch deployment chuẩn. |
| Batch import nhiều phiên bản tài nguyên | Có thể sau khi publish snapshot mới, song phải cân nhắc đồng bộ threads và source consistency. |
| Mỗi HTTP request | Thường **không nên**; gây tải lại tốn chi phí và phá lợi ích cache. |
| Test isolation | Có thể dùng `clearCache(loader)` với loader dành riêng cho test; tránh ảnh hưởng suite khác. |
| Hot-reload cùng named module | Không dùng `Control` trực tiếp từ named module; cần thiết kế provider/cache theo JPMS. |

### Tham chiếu cũ và memory leak

`ResourceBundle.clearCache(loader)` chỉ xóa **cache entries**. Nếu ứng dụng vẫn giữ một biến:

```java
ResourceBundle oldLabels = ResourceBundle.getBundle("messages.Labels", locale);
// ... clearCache(loader) ...
String stillOld = oldLabels.getString("greeting");
```

thì `oldLabels` là **object cũ** và có thể tiếp tục đọc giá trị cũ. Mảnh code này minh họa ý nghĩa, không phải một chương trình độc lập: `locale` và `loader` cần được cấp từ ứng dụng.

Nếu một server giữ `ResourceBundle`, `ClassLoader`, metadata hoặc tham chiếu trong singleton static lâu hơn vòng đời plugin/webapp, classloader cũ có thể không được giải phóng. Đừng suy ra cache của ResourceBundle là nơi gây leak duy nhất. Kiểm tra **toàn bộ ứng dụng và thư viện**, classloader context, thread-local và các caches khác. Việc chỉ gọi `clearCache` chưa đủ nếu vẫn có references bên ngoài.

## 10. Locale fallback, parent chain và negative caching

Một lời gọi:

```java
ResourceBundle rb = ResourceBundle.getBundle(
        "messages.Labels", Locale.forLanguageTag("vi-VN"));
```

có thể liên quan tới nhiều candidate bundles:

```text
messages.Labels_vi_VN
       |
       v
messages.Labels_vi
       |
       v
messages.Labels
```

Đây là **minh họa chuỗi candidate/parent khi các bundle tương ứng tồn tại**. Thực tế `ResourceBundle.Control.getCandidateLocales` và `getFallbackLocale` quyết định ứng viên/fallback; có thể có thêm chiến lược mặc định theo locale của JVM. Không nên coi mọi lần lookup luôn tải đủ đúng ba file trên.

Hệ quả với cache:

- Parent bundle có thể có entry/TTL riêng. Ngay cả khi child đang hợp lệ, chuỗi parent cần được tính đến trong quá trình xác định bundle trả về.
- Một key không có trong child có thể được đọc từ parent; cập nhật parent không có nghĩa child instance đã giữ tự phản ánh thay đổi nếu parent chain của nó vẫn gắn object cũ.
- Khi một candidate trước đó **không có file**, JVM có thể ghi nhận entry đánh dấu “không tìm được” để giảm số lần thử tải; nó cũng liên quan tới cơ chế hết hạn.
- Thêm tệp dịch mới trong lúc chạy không nhất thiết được nhận ra ngay nếu trước đó còn negative cache hoặc chưa có lần `getBundle` kích hoạt kiểm tra.
- Thay đổi `Locale.getDefault()` có thể ảnh hưởng chiến lược fallback của những lần tìm kiếm sau; không tự sửa những `ResourceBundle` đã được ứng dụng giữ.

Khi chẩn đoán “vừa thêm `Labels_vi_VN.properties` mà app chưa dùng”, đừng chỉ nhìn TTL của bản `vi_VN`: hãy kiểm tra classloader, resource path, negative cache, parent/fallback, và việc app có gọi lại `getBundle` hay không.

## 11. Named modules: giới hạn quan trọng của `ResourceBundle.Control`

**ResourceBundle.Control không bị xóa khỏi Java**, nhưng **không được hỗ trợ cho lời gọi `ResourceBundle.getBundle` nhận `Control` khi caller là một named module**. Java sẽ báo `UnsupportedOperationException` trong trường hợp này theo API hiện hành.

Điều này quan trọng vì:

- Demo ở mục 6 và `PropertiesTtlControl` ở mục 7 chạy trong **unnamed module** thông qua classpath.
- Nếu chuyển ví dụ sang một ứng dụng `module-info.java` rồi gọi `getBundle(..., control)` từ named module, không thể giả định code tiếp tục chạy.
- Trong hệ thống JPMS, nên xem `ResourceBundleProvider` và `ResourceBundle.getBundle(baseName, locale, module)` cùng quy tắc package/resource encapsulation theo module.
- `ResourceBundleControlProvider` tùy biến xử lý mặc định cũng bị bỏ qua trong named modules.
- `ResourceBundleProvider` là hướng hỗ trợ nguồn bundle trong module, nhưng **không phải bản sao một-một của tất cả callbacks/TTL hooks trên `Control`**. Nếu cần hot reload với provider, ứng dụng thường phải thiết kế vòng đời dữ liệu/cache/provider riêng.
- Module package mở/đóng ảnh hưởng cách tìm resource; một bản dịch “có trong JAR” không có nghĩa API của mọi module đều được phép đọc.

Cách tiếp cận thực tế: **biết rõ deployment model**. Trong classpath-based Java application hoặc công cụ cũ hiện đại hóa nhưng chưa modular hóa, Control vẫn dùng đúng mục đích. Với JPMS named modules, không cố lách `UnsupportedOperationException` bằng cách cast hay bọc method; thiết kế theo provider/module resources từ đầu.

## 12. Hiệu năng: chọn TTL thế nào?

| Đặc tính nguồn | TTL/policy thường phù hợp | Đánh đổi |
| --- | --- | --- |
| Bản dịch đóng gói bất biến vào ứng dụng | `TTL_NO_EXPIRATION_CONTROL`/mặc định | Nhanh, nhưng triển khai bản mới mới làm mới nội dung. |
| Resource file triển khai ngoài app, cập nhật đôi khi | TTL dương như `30_000L` hoặc `60_000L` | Giảm check I/O; có độ trễ tới lần request sau expiry. |
| Test cần kiểm tra bản dịch đổi ngay | `0L` + `needsReload` theo version/metadata | Check mỗi lookup; phù hợp test hơn hot path tải lớn. |
| Cần bỏ cache hoàn toàn | `TTL_DONT_CACHE` | Có thể giảm stale object nhưng tăng lượng load/parse và I/O. |
| Dữ liệu dịch lấy từ API | TTL dương + version/ETag check + newBundle có cache policy rõ | Cần timeout/backoff/giám sát; không chỉ override một method. |

Không có một TTL mặc định tốt cho mọi hệ thống. Hãy ước lượng:

- Tần suất truy cập bản dịch trong request path;
- Chi phí tra metadata so với tải full bundle;
- Độ trễ cập nhật chấp nhận được;
- Tỷ lệ ngôn ngữ và số lượng bundles/parents;
- Classloader và phạm vi cache của service;
- Số replicas của ứng dụng (TTL mỗi tiến trình **không đồng bộ** nhau);
- Lỗi I/O và mức độ chấp nhận nội dung cũ.

**TTL không tạo consistency giữa nhiều JVM**. Với hệ thống nhiều replicas, có thể dùng publish version, invalidation event hoặc deployment rolling và cho từng instance tải lại theo contract chung, thay vì xem giá trị milliseconds như SLA tuyệt đối.

## 13. Thread safety và tính nhất quán

`ResourceBundle.Control` có thể được gọi bởi nhiều threads. API không hứa đồng bộ hóa bao quanh mọi callback do Control tự viết. Do đó:

1. Giữ configuration như TTL hoặc formats **immutable** nếu có thể.
2. Với mutable version state, dùng synchronization/atomic values hoặc snapshot quản lý chặt.
3. Không ghi vào non-thread-safe `HashMap` từ callbacks nếu cùng object Control dùng đồng thời mà không có bảo vệ.
4. Khi cần tải bundle từ nhiều nguồn, đảm bảo snapshot được tạo nhất quán giữa version metadata và resource content; tránh trường hợp `needsReload` thấy version B nhưng `newBundle` lại lấy data của version C giữa hai lần cập nhật.
5. Không lưu mutable data structure vào `ListResourceBundle.getContents()` rồi chỉnh trực tiếp trong khi nhiều threads đọc.
6. Có policy khi reload fail: lỗi phải được báo đúng chỗ, hoặc giữ bản known-good theo chiến lược công khai. Tránh xoay vòng refresh không kiểm soát.
7. Hạn chế race giữa cập nhật nguồn và cache invalidation trong môi trường nhiều threads. `clearCache` không tương đương một transaction toàn hệ thống.
8. Với UI/localization, nếu một request cần nhất quán toàn bộ text trong suốt request, lấy **một bundle snapshot** cho request đó thay vì lấy lại bundle sau mỗi key và có thể pha hai phiên bản dịch.

Một pattern có thể sử dụng là truyền `ResourceBundle` đã chọn vào lớp render thông điệp cho **một request**. Ở request sau, controller có thể gọi lại `getBundle` để xem TTL; nếu lấy object cũ thì cùng snapshot, nếu reload thì dùng phiên bản mới. Đừng lưu toàn bộ bundle instance vĩnh viễn trong một static field nếu hệ thống thật sự cần hot reload.

## 14. Kiểm thử đúng cách

### 14.1. Phân tách test hành vi và test thời gian thực

**Unit test không phụ thuộc thời gian** giống mục 6 nên kiểm tra:

- Lần đầu `getBundle` gọi `newBundle` để nạp.
- Với TTL = 0 và version không đổi, `needsReload` chạy nhưng instance vẫn được tái sử dụng.
- Khi revision đổi, `needsReload` trả true và instance mới được tạo.
- `clearCache(loader)` khiến lần tải tiếp theo tạo object khác.
- `TTL_NO_EXPIRATION_CONTROL` không gọi `needsReload` chỉ vì nguồn thay đổi.
- `TTL_DONT_CACHE` cho hai lần tải tách biệt.

**Integration test với file `.properties`** nên kiểm tra:

- Tệp được đặt đúng classpath và bundle tên/locale khớp.
- Last-modified timestamp thay đổi đủ rõ theo filesystem đang dùng.
- `getBundle` sau khi TTL hết xác minh source, không phải trước expiry.
- Dữ liệu mới được đọc khi reload thực sự xảy ra.
- Không giữ stale reference trong component cần thấy bản mới.
- Nếu source nằm trong JAR, kỳ vọng thay đổi được quản lý qua deployment/classloader thay vì “ghi file trong JAR”.

Đừng viết một test chạy nhanh rồi phụ thuộc `Thread.sleep(30)` để khẳng định TTL 30 ms đã hết trên mọi OS/CI. Scheduler, filesystem mtime granularity, GC và độ trễ máy ảo có thể gây flaky tests. Chọn chính sách test deterministic hoặc kiểm tra thời gian bằng clock/file fixtures có kiểm soát.

### 14.2. Kịch bản QA cần có

| Kịch bản | Kết quả phải xác minh |
| --- | --- |
| TTL dương còn hiệu lực | Không gọi `needsReload` quá sớm. |
| TTL dương hết hạn, source không đổi | `needsReload=false` → tiếp tục cached instance và reset thời hạn. |
| TTL dương hết hạn, source đổi | `needsReload=true` → `newBundle` cung cấp snapshot mới. |
| TTL 0, source không đổi | Có validation, **không cần** instance mới. |
| TTL 0, source đổi | Sau lookup mới, nhận instance/value mới. |
| `TTL_DONT_CACHE` | Không reuse các loaded bundle instances theo cache. |
| `TTL_NO_EXPIRATION_CONTROL` | Không tự refresh vì elapsed time; test `clearCache` riêng. |
| `clearCache(ClassLoader)` | Đúng loader được invalidated, references cũ vẫn tồn tại. |
| Bundle chưa từng tồn tại, sau đó được thêm | Negative cache không ngăn nhận resource mãi mãi khi đã có policy refresh phù hợp. |
| Fallback child/parent | Sau thay đổi parent, các key fallback được cập nhật khi chain mới hình thành. |
| Hai threads cùng `getBundle` | Control state không race/làm mất counters hoặc tạo dữ liệu lỗi. |
| Named module caller | `getBundle(..., Control)` không dùng được; dùng cơ chế phù hợp JPMS. |
| Source lỗi/không đọc được | Có error signal/monitoring rõ, không trả chuỗi rỗng giả tạo. |

## 15. Các lỗi phổ biến

| Hiểu sai / lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| “TTL 30s thì Java tự nạp lúc giây thứ 30.” | TTL chỉ được kiểm tra khi `getBundle` được gọi lại. | Thiết kế on-demand refresh hoặc scheduler riêng ngoài ResourceBundle nếu cần proactive. |
| “TTL=0 đồng nghĩa không cache.” | TTL=0 vẫn giữ instance nếu `needsReload=false`. | Dùng đúng `TTL_DONT_CACHE` nếu chủ đích bỏ cache. |
| “Hết hạn TTL đồng nghĩa bundle cần reload.” | `needsReload` là bước xác minh riêng. | Phân biệt expiry/validation với reload. |
| “`needsReload` trả true sẽ sửa object đang dùng.” | Bản đã trao cho caller là object riêng, không cập nhật tự động. | Lấy lại `getBundle` và thay reference trong tầng sở hữu. |
| “Gọi `clearCache` để update tất cả clients.” | Chỉ xóa cache entry trong scope, không sửa references cũ. | Phối hợp lifecycle/refresh của client. |
| Dùng `TTL_NO_EXPIRATION_CONTROL` nhưng muốn hot reload | Default không revalidate theo TTL. | Chọn TTL dương + needsReload phù hợp hoặc invalidate chủ động. |
| Override `needsReload` nhưng `getTimeToLive` vẫn default | Mặc định không hết hạn → callback có thể không bao giờ chạy. | Override TTL cùng chính sách validation. |
| Dùng `needsReload = true` không điều kiện | Mọi lần hết TTL đều tải lại, gây tải I/O cao. | So source revision/ETag/timestamp thực tế. |
| Đổi `Control`/formats mà không tính cache cũ | Cache không coi mọi Control instance là namespace độc lập. | Dùng policy nhất quán; clear trong scope nếu thay policy có chủ đích. |
| Đòi class-based bundle “nạp lại class” bằng TTL | Classloader không thay class definition đã nạp chỉ vì getBundle. | Triển khai resource data riêng hoặc reload classloader/deploy lại. |
| Sửa tệp `.properties` trong JAR rồi kỳ vọng JVM đọc mới | JAR và URL caching/metadata có thể che thay đổi. | Thay artifact bằng deployment strategy đúng. |
| Bỏ qua negative cache | Bundle chưa có cũng có thể bị cache dưới dạng marker. | Test thêm/xóa locale resources cùng TTL/cache refresh. |
| Chỉ nhìn TTL của requested locale | Parent/fallback cũng có cache/expiry. | Xác minh cả candidate bundles và parent chain. |
| Clear cache trên loader sai | Bundle thuộc loader khác vẫn có entry. | Xác định đúng classloader và module boundary. |
| Gọi `clearCache` cho mọi request | Phá cache, tăng allocation/I/O. | Chỉ invalidate khi có publish/update có chủ đích. |
| Dùng `getBundle(..., Control)` trong named module | API không hỗ trợ, có thể ném `UnsupportedOperationException`. | Dùng provider/module-aware loading + cache strategy thích hợp. |
| Tự viết Control với mutable state không đồng bộ | `ResourceBundle` không khóa các callbacks cho bạn. | Immutable config, atomic/synchronization, integration tests. |
| Log nguyên văn dữ liệu dịch chứa bí mật | Bundle không phải secret store. | Không dùng ResourceBundle chứa tokens/passwords; kiểm soát logging và access. |

## 16. Chiến lược kiến trúc: ứng dụng nên chọn gì?

### 16.1. Ứng dụng web/desktop có bản dịch phát hành cùng code

Nếu file `.properties` được build vào JAR và chỉ thay đổi theo release, **để caching mặc định** thường hợp lý. Thay vì xây hot reload phức tạp, cập nhật nội dung bằng deploy phiên bản mới có thể đơn giản và đáng tin cậy hơn.

### 16.2. Công cụ chỉnh bản dịch tại runtime

Nếu operator thực sự sửa tệp `.properties` bên ngoài artifact đang chạy, cần:

- Một source location đáng tin cậy và classloader/file manager có thể thấy dữ liệu;
- TTL phù hợp với độ trễ cập nhật yêu cầu;
- Một phép `needsReload` đáng tin, có thể là default timestamp hoặc version check riêng;
- Cơ chế `newBundle` đọc được bản mới;
- Consumer gọi lại `getBundle` và thay references khi muốn thấy dữ liệu mới;
- Tài liệu hóa hành vi khi file mất hoặc sửa sai format.

### 16.3. Dịch vụ i18n từ database hoặc API

Trong mô hình này, `Control` có thể là **một adapter classpath** nhưng không nên bị ép thành cache phân tán. Nhiều hệ thống phù hợp hơn với một cache/provider riêng có version, async refresh, metric, timeout và fallback. Nếu chạy JPMS named modules, dùng hướng `ResourceBundleProvider` và module-aware resource access thay cho `Control` trực tiếp.

### 16.4. Không sử dụng ResourceBundle để giữ cấu hình bí mật hoặc chính sách an ninh

Các bản dịch nhiều ngôn ngữ thường là dữ liệu hiển thị. TTL của ResourceBundle không bảo đảm **thu hồi quyền truy cập**, **rotation secret** hay cập nhật security policy kịp thời. Không dùng những cơ chế như stale-if-error của bản dịch cho credential/authorization.

## 17. Checklist triển khai

- [ ] Biết bundle đang chạy ở **classpath/unnamed module hay JPMS named module**?
- [ ] Xác định đúng base name, locale, classloader/module và parent fallback?
- [ ] Xác định file `.properties` là immutable trong artifact hay được sửa ngoài runtime?
- [ ] Hiểu rõ default `TTL_NO_EXPIRATION_CONTROL` và chọn TTL theo mục tiêu thực tế?
- [ ] Phân biệt chính xác TTL=0, TTL dương, `TTL_DONT_CACHE` và `TTL_NO_EXPIRATION_CONTROL`?
- [ ] Nếu cần revalidate, đã override `getTimeToLive` cùng `needsReload`/cơ chế mặc định thích hợp?
- [ ] Biết `needsReload` chỉ được gọi **sau expiry** trong quá trình `getBundle`?
- [ ] Nếu có custom `newBundle`, đã xử lý flag `reload` và cache tầng nguồn?
- [ ] Nếu dùng file mtime, đã kiểm tra timestamp granularity và behavior của filesystem/JAR?
- [ ] Consumer có lấy lại `getBundle` để thấy snapshot mới thay vì giữ bundle cũ mãi mãi?
- [ ] `clearCache(loader)` dùng đúng scope; không ảnh hưởng tests/clients không liên quan?
- [ ] Cần invalidation khi publish hay chỉ eventual validation theo TTL?
- [ ] Có metric/log load count, validation count, reload count, error count ở mức phù hợp?
- [ ] Custom Control có thread-safe và có chính sách fallback khi nguồn không đọc được?
- [ ] Đã test bundle candidate/parent chain, locale không tồn tại và negative cache?
- [ ] Khi thay phiên bản app/JDK, tests có bao phủ behavior cache/locale thực tế?
- [ ] Tài liệu deployment chỉ ra rằng **named module không dùng `getBundle(..., Control)`**?
- [ ] Không lưu secret/security settings dưới dạng bản dịch rồi tin TTL đảm bảo tính cập nhật?

## 18. Bài tập thực hành

**Bài tập A — Phân biệt validate và reload.** Chạy ví dụ mục 6, ghi lại `initialChecks`, `checksAfterChange` và `loadsAfterChange`. Giải thích vì sao lần getBundle thứ hai kiểm tra nhưng không tạo bundle mới.

**Bài tập B — Điều chỉnh revision.** Bỏ lệnh `ttlZero.revision.set(2)` và chạy lại. Dự đoán `reloaded`, `checksAfterChange` và `loadsAfterChange`; giải thích việc `needsReload=false` làm cache tiếp tục được sử dụng.

**Bài tập C — Chọn TTL policy.** Thử thay `0` bằng `TTL_NO_EXPIRATION_CONTROL` trong phần đầu demo. Vì sao `needsReload` không được gọi dù revision đổi? Thêm `clearCache(loader)` có làm kết quả khác không?

**Bài tập D — Không cache.** Thay `TTL_DONT_CACHE` bằng `0L` trong phần test no-cache. Dự đoán số lần `newBundle` được gọi khi revision không thay đổi, đồng thời quan sát số lần `needsReload`.

**Bài tập E — Properties thật.** Tạo `messages/Labels.properties` trên classpath, dùng `PropertiesTtlControl` TTL dương. Sửa file giữa hai lần `getBundle`, chú ý sửa timestamp và chờ TTL; log `ResourceBundle` instance và `getString`. Giải thích các giới hạn khi chạy từ JAR.

**Bài tập F — Resource không tồn tại.** Yêu cầu locale chưa có, sau đó thêm file tương ứng. Phân tích ảnh hưởng của cache marker “not found” và cách bảo đảm có lần tải lại phù hợp với policy.

**Bài tập G — Request-level consistency.** Thiết kế một service nhận `Locale` và có 10 keys để render. Làm sao mỗi request dùng đúng **một bundle snapshot**, trong khi request tiếp theo vẫn có thể thấy bản dịch mới?

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `getTimeToLive(...) = 0` có chắc hai lần `getBundle` trả hai instance khác nhau không?

**Đáp án:** Không. Nó bắt buộc kiểm tra TTL khi lấy lại. Nếu `needsReload` trả `false`, runtime có thể dùng lại cùng instance.

**Câu 2.** `TTL_DONT_CACHE` khác `TTL_NO_EXPIRATION_CONTROL` thế nào?

**Đáp án:** `TTL_DONT_CACHE` không giữ loaded bundle trong cache; `TTL_NO_EXPIRATION_CONTROL` cho cache nhưng không có validation theo TTL. Không có cách nói “cả hai đều cache vô hạn”.

**Câu 3.** File nguồn đổi lúc 10:00:10 và TTL 30 giây được tính từ lúc 10:00:00, khi nào chắc chắn app thấy file mới?

**Đáp án:** Không thể đảm bảo một thời điểm tuyệt đối. Sau khi TTL hết và có **lần getBundle mới**, `needsReload` mới được xem xét; nếu xác định nguồn đổi và `newBundle` thực sự đọc được version mới, caller mới có bundle mới.

**Câu 4.** `needsReload(...) == true` có tự cập nhật `ResourceBundle` đang được một controller giữ trong field không?

**Đáp án:** Không. `getBundle` sẽ dùng kết quả tạo bundle mới cho lần lookup thích hợp; object mà controller đã giữ vẫn tồn tại tới khi không còn reference hoặc bị GC.

**Câu 5.** Vì sao `getTimeToLive` được override mà `needsReload` của bạn không hề chạy?

**Đáp án:** Có thể do TTL là `TTL_NO_EXPIRATION_CONTROL`/chưa hết hạn, chưa có lần `getBundle` mới, gọi sai loader/cache policy, hoặc Control không được sử dụng đúng phạm vi. Kiểm tra đường thực thi và deployment trước khi kết luận API lỗi.

**Câu 6.** `clearCache(ClassLoader)` xóa tất cả bản dịch của mọi classloader và module không?

**Đáp án:** Không. Phạm vi là classloader được chỉ định theo API; còn `clearCache()` có phạm vi theo caller module trên Java hiện hành. References đã giữ vẫn không bị thay đổi.

**Câu 7.** Có thể dùng `getBundle(baseName, locale, control)` trực tiếp từ named module không?

**Đáp án:** Không. API `ResourceBundle.Control` nêu rõ lời gọi có `Control` từ named module có thể ném `UnsupportedOperationException`; cần mô hình provider/resource access phù hợp với JPMS.

**Câu 8.** Vì sao class-based `ListResourceBundle` đóng trong JAR không thích hợp để “reload bản class mới” chỉ bằng TTL?

**Đáp án:** Default `newBundle` với `java.class` không dùng flag `reload` để tái định nghĩa class đã được classloader tải. Có thể cần deploy/classloader mới hoặc đưa text resource ra nguồn được hỗ trợ refresh.

## 20. Tài liệu chính thức và kiến thức còn áp dụng

- [ResourceBundle — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html): cache management, `getBundle`, `clearCache`, parent chain và giới hạn module.
- [ResourceBundle.Control — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.Control.html): `getTimeToLive`, `needsReload`, `newBundle` và các hằng TTL.
- [ResourceBundleProvider — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ResourceBundleProvider.html): hướng tùy biến nguồn bundle trong JPMS modules.
- [PropertyResourceBundle — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html): nguồn dữ liệu property-based.
- [ListResourceBundle — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ListResourceBundle.html): cách triển khai bundle từ danh sách key/value.
- [ClassLoader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): classloader là ranh giới quan trọng của việc tìm resource và cache.

**Ghi nhớ:** `ResourceBundle` cache theo cơ chế của runtime; `getTimeToLive` xác định **khi nào cần xác minh**, `needsReload` xác định **có phải tải lại hay không**, `newBundle` thực sự tạo dữ liệu mới, còn `clearCache` chỉ **xóa entries trong scope**, không tự thay references cũ. Dùng API hiện hành đúng với classpath hoặc named modules, và chọn cache policy theo độ trễ cập nhật, độ tin cậy của nguồn và chi phí tải.
