# Bộ nhớ đệm ResourceBundle và clearCache trong Java

## 1. Vì sao file dịch đã đổi mà giao diện vẫn hiện nội dung cũ?

`java.util.ResourceBundle` là cơ chế tiêu chuẩn của Java để tổ chức tài nguyên bản địa hóa như thông điệp, nhãn giao diện và văn bản cho nhiều `Locale`. Một ứng dụng thường gọi:

~~~java
ResourceBundle messages = ResourceBundle.getBundle(
        "i18n.Messages", Locale.forLanguageTag("vi-VN"));
String title = messages.getString("page.title");
~~~

**Đây là snippet đặt trong một phương thức Java**, cần import `java.util.ResourceBundle` và `java.util.Locale`, đồng thời ứng dụng thật phải có bundle mang base name `i18n.Messages` trên đường tải tài nguyên. Đoạn ví dụ Java **độc lập, chạy ngay không cần file properties** nằm ở mục 8.

Một tình huống quen thuộc: ứng dụng tải `Messages_vi.properties`, nhà phát triển thay câu dịch trong file, nhưng yêu cầu tiếp theo vẫn nhận câu cũ. Một nguyên nhân có thể là **cache của ResourceBundle**. `getBundle(...)` không bắt buộc tìm/đọc lại nguồn tài nguyên mỗi lần được gọi; Java **cache các instance ResourceBundle theo mặc định** và có thể trả lại cùng đối tượng khi lookup lặp lại.

Bộ nhớ đệm mang lại hiệu quả:

- Giảm số lần tìm và đọc các file `.properties` hoặc khởi tạo lớp `ListResourceBundle`.
- Giảm chi phí tìm candidate locale, fallback và dựng quan hệ parent bundle.
- Hữu ích với ứng dụng web có nhiều request cùng dùng một bộ từ khóa dịch.

Tuy nhiên, cache đặt ra những câu hỏi về **thời điểm nhìn thấy cập nhật**, **phạm vi vô hiệu hóa**, **vòng đời class loader/module**, **đồng thời** và **triển khai nhiều máy chủ**.

**Kết luận mở đầu:** `ResourceBundle.clearCache` **xóa mục khỏi cache nội bộ được chọn**, không chỉnh nội dung file, không thay đổi đối tượng bundle mà ứng dụng đang giữ và không bảo đảm mọi lớp cache bên ngoài cũng được làm mới.

## 2. Mô hình nạp ResourceBundle và phạm vi cache

Một họ resource bundle có **base name** chung và nhiều phiên bản theo `Locale`:

~~~text
src/main/resources/
└── i18n/
    ├── Messages.properties
    ├── Messages_en.properties
    ├── Messages_vi.properties
    └── Messages_vi_VN.properties
~~~

**Đây là sơ đồ cấu trúc dự án minh họa**, không phải những file được tạo bởi chương trình trong bài.

Ví dụ khi gọi `getBundle("i18n.Messages", new Locale("vi", "VN"))`, Java tìm các **candidate locales** thích hợp, lựa chọn bundle có sẵn rồi thiết lập parent chain khi cần. Một khóa không có trong bundle chi tiết có thể được lấy từ parent. Việc tìm candidate có thể thêm fallback đến default locale tùy API và `Control` đang dùng.

### 2.1. ResourceBundle là đối tượng chứ không chỉ là file

`ResourceBundle` có thể là:

- `PropertyResourceBundle` đọc dữ liệu `.properties`.
- `ListResourceBundle` dựa trên lớp Java.
- Một subclass tùy chỉnh; trong classpath/unnamed module, `ResourceBundle.Control` có thể triển khai format đặc biệt, ví dụ lưu bản dịch trong cơ sở dữ liệu hoặc tài nguyên bên ngoài.

Cache lưu **bundle instances** và thông tin cần thiết để tái sử dụng trong quá trình `getBundle`. Một `ResourceBundle` có thể có **parent bundle**. Do đó khi một key được lấy từ parent, kết quả nhìn thấy có thể phụ thuộc cả bundle con và bundle cha đã được nạp/cached.

### 2.2. Cùng tên không đồng nghĩa cùng instance trong mọi trường hợp

Việc tìm cache chịu ảnh hưởng của nhiều thông tin trong yêu cầu tải, như:

- Base name của họ bundle.
- Locale được dùng trong lookup và candidate/fallback thực tế.
- Module hoặc ClassLoader liên quan.
- Trạng thái cache, thời hạn sống và nguồn dữ liệu đang được nạp.

Đừng phát biểu rằng mọi lời gọi `getBundle("i18n.Messages")` trên tất cả class loader, module và JVM đều trả **một** instance toàn cục. Mỗi runtime có ngữ cảnh nạp khác nhau; tài nguyên cùng tên trong hai class loader còn có thể là **hai bộ file khác nhau**.

**Cũng không nên xem đối tượng `Control` là một namespace cache độc lập.** Theo tài liệu Java, `getFormats` và `getCandidateLocales` phải nhất quán khi tải cùng base name; thay Control không nhất thiết làm cache cũ biến mất. Tùy biến cấu hình cần thiết kế nhất quán và có chiến lược clear/reload.

## 3. Caching mặc định: lợi ích và hậu quả

Theo Java SE 17, các instance `ResourceBundle` **được cache mặc định**. Nếu bundle vẫn có hiệu lực trong cache, nhiều lần gọi `getBundle` có thể trả **cùng instance**.

~~~java
ResourceBundle first = ResourceBundle.getBundle(
        "i18n.Messages", Locale.forLanguageTag("vi-VN"));

ResourceBundle second = ResourceBundle.getBundle(
        "i18n.Messages", Locale.forLanguageTag("vi-VN"));
~~~

Đây là snippet minh họa với classpath đã có các resource tương ứng. Trong hoàn cảnh cache ổn định, `first == second` **có thể** đúng. Không dùng phép kiểm tra identity này làm contract xuyên class loader, ứng dụng hoặc thời điểm nâng JDK.

### 3.1. Cache không có nghĩa giữ một đối tượng mãi mãi

Dù mặc định `ResourceBundle.Control.getTimeToLive` trả `TTL_NO_EXPIRATION_CONTROL`, các bundle cached **có thể bị loại khỏi cache do điều kiện bộ nhớ**. Vì vậy:

- Không dùng `==` trên bundle làm định danh bất biến.
- Không trông đợi một lần getBundle nhất thiết luôn đọc đúng một file hoặc gọi constructor đúng một lần trong cả vòng đời.
- Cache tồn tại nhằm tối ưu tài nguyên, không phải kho lưu dữ liệu nghiệp vụ.
- Một reference `ResourceBundle` mà chương trình đang giữ có vòng đời **riêng** với entry trong cache.

Tài nguyên dịch thường là dữ liệu tĩnh theo bản phát hành. Caching mặc định phù hợp với mô hình **build → đóng gói JAR → triển khai lại ứng dụng**. Với bản dịch nóng (hot reload), phải có thiết kế rõ hơn.

### 3.2. Cache cả trường hợp không tìm thấy

Khi lookup một candidate bundle không tồn tại, quá trình tải theo `ResourceBundle.Control` có thể cache một **dummy bundle** dùng làm dấu hiệu không có tài nguyên, giúp tránh tìm file thất bại lặp lại. Dummy cũng chịu quy tắc TTL của Control.

Hệ quả: nếu một file locale mới được thêm sau lần lookup thất bại, Java có thể chưa tìm thấy nó ngay, dù file đã có mặt, do cache trạng thái **missing**. Có thể cần vô hiệu hóa cache liên quan hoặc chờ cơ chế TTL/needsReload; đồng thời phải kiểm tra đường nạp file/class loader có thực sự nhìn thấy tài nguyên mới.

Đừng dùng `MissingResourceException` làm tín hiệu chắc chắn “tệp vừa được thêm không tồn tại” mà chưa xét cache và cơ chế packaging.

## 4. clearCache(): xóa những gì, không xóa những gì?

Java SE 17 cung cấp hai overload:

~~~java
ResourceBundle.clearCache();
ResourceBundle.clearCache(classLoader);
~~~

Đây là **snippet minh họa**; `classLoader` phải là một `ClassLoader` hợp lệ, thường được lấy từ module hoặc lớp ứng dụng tương ứng.

| API | Phạm vi được mô tả trong Java SE 17 |
| --- | --- |
| `ResourceBundle.clearCache()` | Xóa các bundle trong cache được nạp bởi **caller’s module** |
| `ResourceBundle.clearCache(ClassLoader loader)` | Xóa các bundle trong cache được nạp bằng **class loader được truyền vào** |

**Không đánh đồng hai overload.** Trong môi trường dùng named modules, nhiều class loader, application server hoặc plugin class loader, câu “`clearCache()` luôn xóa toàn bộ bundle của mọi plugin” là sai.

### 4.1. Thực tế khi xóa cache

~~~text
Lần 1: getBundle(...) -> tạo bundle A, đưa vào cache
Lần 2: getBundle(...) -> có thể dùng lại A
             |
             v
       clearCache(loader)
             |
             v
Lần 3: getBundle(...) -> lookup lại -> có thể tạo bundle B

Các biến đang tham chiếu bundle A vẫn giữ A.
~~~

`clearCache(loader)` **không sửa dữ liệu trong bundle A**. Nếu một service giữ:

~~~java
private static final ResourceBundle MESSAGES = /* bundle đã nạp */;
~~~

thì việc clear cache không tự thay giá trị của `MESSAGES`; service phải **gọi getBundle lại và thay reference** theo chính sách của nó. Đoạn trên là khai báo minh họa, không phải file Java độc lập.

`clearCache` cũng không:

- Xóa resource files, sửa `.properties`, ghi file mới hoặc kiểm tra nội dung cập nhật.
- Loại bản sao mà ứng dụng giữ trong `Map`, `LoadingCache`, `ThreadLocal` hoặc singleton riêng.
- Làm mới các `MessageFormat`, template HTML hoặc UI strings đã format và lưu riêng.
- Buộc các JVM/node khác trong cluster vô hiệu hóa bộ nhớ đệm.
- Đóng mọi class loader, giải phóng mọi object ngay lập tức.
- Bảo đảm classpath/JAR đang chạy có thể nhìn thấy phiên bản file mới vừa thay đổi.

### 4.2. Clear cache không phải API xóa theo một key đơn lẻ

Java `ResourceBundle` không có overload `clearCache(baseName, locale)` trong API tiêu chuẩn. `clearCache(ClassLoader)` tác động đến **các bundles được nạp bởi loader đó**, không chỉ một base name, nên có thể làm phát sinh chi phí reload ở nhiều module/tính năng.

Trong hệ thống lớn, không gọi `clearCache` mỗi request chỉ để lấy một label vừa đổi. Nếu dữ liệu phải hot reload theo từng tenant/locale, cân nhắc cache ứng dụng có namespace/version và cơ chế invalidation được thiết kế cho phạm vi đó.

### 4.3. Vì sao tham số class loader quan trọng?

Ở hệ thống application server, plugin, OSGi hoặc hệ thống dùng nhiều loader, cùng tên bundle có thể tồn tại ở các ngữ cảnh khác nhau. Xóa cache bằng loader của lớp A không đảm bảo entry nạp bằng loader B sẽ bị xóa.

Ví dụ minh họa:

~~~java
ClassLoader loader = MyApplication.class.getClassLoader();
ResourceBundle.clearCache(loader);
~~~

Đây là snippet yêu cầu lớp `MyApplication` thực sự tồn tại trong dự án. Trong chương trình độc lập mục 8, ta dùng chính `BundleCacheDemo.class.getClassLoader()` nên không cần lớp bên ngoài.

**Không truyền null**: `clearCache((ClassLoader) null)` gây `NullPointerException` theo tài liệu JDK.

## 5. TTL: chủ động điều khiển thời gian cache

`ResourceBundle.Control` cho phép cấu hình `getTimeToLive(baseName, locale)` và `needsReload(...)` với các `getBundle` overload có tham số `Control`.

Các giá trị đáng nhớ:

| Giá trị từ `getTimeToLive` | Ý nghĩa |
| --- | --- |
| `TTL_NO_EXPIRATION_CONTROL` | Cache không kiểm soát hết hạn theo TTL (mặc định) |
| `TTL_DONT_CACHE` | Không đưa instance được nạp vào cache |
| `0L` | Khi lấy lại từ cache, cần **xác minh** có cần reload |
| Một số dương, ví dụ `5_000L` | Thời hạn tính theo **mili giây** trước khi kiểm tra lại |

**TTL hết hạn KHÔNG đồng nghĩa chắc chắn reload.** Theo hợp đồng `getBundle`, sau khi TTL hết hạn, `Control.needsReload` được hỏi xem nguồn tài nguyên đã thay đổi hay không:

- Trả `true`: bundle cached bị loại và được nạp lại.
- Trả `false`: bundle có thể được giữ lại, cập nhật mốc TTL và tiếp tục tái sử dụng.

Vì thế, nếu `getTimeToLive` trả `0L` mà `needsReload` luôn trả `false`, bạn **không** đạt được “mỗi lần gọi đều tạo instance mới”. Nếu mục tiêu thực sự là bỏ cache, dùng `TTL_DONT_CACHE` cho bundle tương ứng; nhưng phải cân nhắc chi phí I/O và độ ổn định.

### 5.1. Một Control có TTL theo base name

~~~java
ResourceBundle.Control policy = new ResourceBundle.Control() {
    @Override
    public long getTimeToLive(String baseName, Locale locale) {
        return baseName.equals("i18n.HotMessages")
                ? 2_000L
                : TTL_NO_EXPIRATION_CONTROL;
    }
};
~~~

Đoạn này có thể đặt trong phương thức Java; cần import `Locale` và `ResourceBundle`. Nó **chỉ thiết lập thời điểm kiểm tra**, chưa bảo đảm nạp lại nếu tài nguyên nguồn vẫn được `needsReload` đánh giá là không thay đổi.

### 5.2. needsReload dựa trên dữ liệu nào?

Chữ ký:

~~~java
boolean needsReload(String baseName, Locale locale,
        String format, ClassLoader loader, ResourceBundle bundle,
        long loadTime)
~~~

Đây là chữ ký minh họa, không phải method hoàn chỉnh. `loadTime` là mốc thời gian nạp dạng mili giây kể từ Unix epoch; mặc định JDK so sánh thời gian sửa tài nguyên khi có thể. Với format custom (database, REST, JSON, XML…), bạn thường cần **định nghĩa** cách xác định thay đổi (version, ETag hoặc modified time) và cách tải bundle mới trong `newBundle`.

Đừng gọi mạng hoặc database quá tốn kém mỗi lần TTL hết hạn nếu lượng request lớn. Có thể dùng cache metadata/version nhẹ hơn và hạn chế số lần refresh; cần thiết kế concurrency, lỗi tải và fallback khi nguồn tạm thời không khả dụng.

### 5.3. newBundle(..., reload) và các tầng cache khác

Khi quyết định reload, `ResourceBundle.Control.newBundle` nhận flag `reload`. Với tài nguyên nằm sau URL/URLConnection, cache bên dưới có thể giữ bản cũ dù ResourceBundle cache đã bị clear. Cách triển khai custom phải **đọc lại nguồn thực sự**; trong một số tình huống cần tắt URLConnection caching khi mở connection để reload.

Cũng cần nhớ bundle class-based được nạp bởi class loader đã tồn tại **không nhất thiết có thể “nạp lại class phiên bản mới”** chỉ bằng `ResourceBundle.clearCache`. Đổi class bytecode thường đòi hỏi class loader hoặc cơ chế deployment phù hợp.

## 6. Thiết kế cập nhật bản dịch nóng: chọn giải pháp theo yêu cầu

### 6.1. Ứng dụng chỉ cập nhật bản dịch khi deploy

Phổ biến nhất:

1. Đặt file `Messages*.properties` trong resources.
2. Build JAR và deploy theo phiên bản.
3. Để ResourceBundle cache mặc định giúp lookup nhanh.
4. Khi có bản dịch mới, build/deploy lại, không cần yêu cầu hệ thống đọc file classpath bị thay nóng.

Ưu điểm: đơn giản, nhất quán giữa code và key dịch, ít rủi ro runtime vừa đọc bản dịch cũ vừa đọc bản dịch mới.

### 6.2. Ứng dụng có file bản dịch ngoài JAR

Nếu file dịch có thể cập nhật trong khi server đang chạy:

1. Quy định thư mục nguồn và cách loader/Control tìm tài nguyên.
2. Chọn TTL phù hợp hoặc cơ chế sự kiện version change.
3. Khi refresh, kiểm tra encoding, toàn vẹn dữ liệu và thiếu key.
4. Thay reference bundle tại biên của request/transaction; không cập nhật tùy tiện giữa lúc render một trang.
5. Nếu cache ứng dụng bổ sung giữ dữ liệu format, invalidation phải bao phủ cả những tầng đó.
6. Có test xác nhận **bản dịch mới có thể được tìm thấy bằng loader hiện tại**; không giả định việc sửa file trên ổ đĩa đủ.

Khi thư mục nguồn không nằm trong đường tìm kiếm của `ClassLoader` hoặc jar không được thay, `clearCache` không tự bổ sung nó vào đường nạp.

### 6.3. Ứng dụng nhiều JVM hoặc nhiều node

`ResourceBundle.clearCache` chỉ tác động **trong JVM đang gọi**. Nếu dịch vụ triển khai trên nhiều node:

- Ghi version/đợt triển khai tài nguyên.
- Phân phối sự kiện invalidation đến các node cần làm mới.
- Kiểm tra tất cả node có thể đọc cùng phiên bản source.
- Giữ giao diện của một request nhất quán trên cùng snapshot resource.
- Có kế hoạch rollback khi bản dịch lỗi, thiếu key hoặc không đạt QA.

Không coi một lần gọi Java trên node A đã xóa cache của node B.

## 7. ResourceBundle.Control và named modules

Một giới hạn kiến trúc quan trọng trong **Java Platform Module System (JPMS)**:

- `ResourceBundle.Control` được thiết kế cho ứng dụng ở **unnamed module/classpath**.
- Gọi `ResourceBundle.getBundle(..., Control)` **từ named module** có thể ném `UnsupportedOperationException` theo hợp đồng Java SE 17.
- Với kiến trúc named modules, Java hỗ trợ `ResourceBundleProvider`/service provider và các `getBundle` overload theo module; không giả định có thể mang nguyên mọi tùy biến `Control` từ classpath sang modulepath.

Chương trình demo ở mục 8 được biên dịch/chạy **trên classpath** theo lệnh `javac` và `java` thông thường, nên áp dụng `Control` như một ví dụ Java 17 hợp lệ.

### 7.1. Phạm vi clearCache trong module

`ResourceBundle.clearCache()` trên Java 17 xóa các cached bundles **được nạp bởi caller’s module**. `ResourceBundle.clearCache(loader)` xóa theo class loader cụ thể. Hai overload có phạm vi riêng, và named module có thêm quy tắc encapsulation/resources.

Nếu ứng dụng dựa trên JPMS, xác định rõ **caller module**, loader, cách resource được khai báo/mở và cách lookup được thực hiện. Khi không chắc, viết integration test đúng packaging runtime, không chỉ chạy trong IDE classpath.

## 8. Chương trình Java 17 hoàn chỉnh: cache, DONT_CACHE và clearCache

Ví dụ tạo các bundle **trong bộ nhớ**, không cần file `.properties` hay mạng. Mỗi bundle mới nhận giá trị tăng dần `v1`, `v2`,… nên dễ quan sát **khi nào Java đã thực sự tạo instance mới**.

**File `BundleCacheDemo.java`:**

~~~java
import java.io.IOException;
import java.util.List;
import java.util.ListResourceBundle;
import java.util.Locale;
import java.util.ResourceBundle;
import java.util.concurrent.atomic.AtomicInteger;

public class BundleCacheDemo {
    private static final AtomicInteger CREATED = new AtomicInteger();

    private static final ResourceBundle.Control CONTROL =
            new ResourceBundle.Control() {
        @Override
        public List<String> getFormats(String baseName) {
            return List.of("demo.memory");
        }

        @Override
        public Locale getFallbackLocale(
                String baseName, Locale locale) {
            return null;
        }

        @Override
        public long getTimeToLive(String baseName, Locale locale) {
            return baseName.equals("demo.Fresh")
                    ? TTL_DONT_CACHE : TTL_NO_EXPIRATION_CONTROL;
        }

        @Override
        public ResourceBundle newBundle(String baseName, Locale locale,
                String format, ClassLoader loader, boolean reload)
                throws IOException {
            if (!"demo.memory".equals(format)) {
                return null;
            }
            String content = "v" + CREATED.incrementAndGet();
            return new ListResourceBundle() {
                @Override
                protected Object[][] getContents() {
                    return new Object[][] {{"message", content}};
                }
            };
        }
    };

    private static ResourceBundle load(String name, ClassLoader loader) {
        return ResourceBundle.getBundle(
                name, Locale.ROOT, loader, CONTROL);
    }

    public static void main(String[] args) {
        ClassLoader loader = BundleCacheDemo.class.getClassLoader();

        ResourceBundle first = load("demo.Cached", loader);
        ResourceBundle second = load("demo.Cached", loader);
        System.out.println("first=" + first.getString("message"));
        System.out.println("cachedSameObject=" + (first == second));
        System.out.println("createdAfterCache=" + CREATED.get());

        ResourceBundle fresh1 = load("demo.Fresh", loader);
        ResourceBundle fresh2 = load("demo.Fresh", loader);
        System.out.println("noCacheValues="
                + fresh1.getString("message") + ","
                + fresh2.getString("message"));
        System.out.println("noCacheSameObject=" + (fresh1 == fresh2));

        ResourceBundle.clearCache(loader);
        ResourceBundle afterClear = load("demo.Cached", loader);
        System.out.println("afterClear="
                + afterClear.getString("message"));
        System.out.println("oldReference="
                + first.getString("message"));
        System.out.println("sameAfterClear=" + (first == afterClear));
        System.out.println("createdTotal=" + CREATED.get());
    }
}
~~~

**Biên dịch và chạy Java 17+:**

~~~bash
javac -encoding UTF-8 BundleCacheDemo.java
java BundleCacheDemo
~~~

**Stdout đã được kiểm thử** trên JDK có hành vi Java SE 17 tương ứng:

~~~text
first=v1
cachedSameObject=true
createdAfterCache=1
noCacheValues=v2,v3
noCacheSameObject=false
afterClear=v4
oldReference=v1
sameAfterClear=false
createdTotal=4
~~~

Giải thích:

1. Lần tải `demo.Cached` đầu tạo `v1`; lần tiếp theo nhận **cùng instance** vì Control cho `TTL_NO_EXPIRATION_CONTROL`.
2. Sau hai lần tải cached, bộ đếm tạo bundle là `1`.
3. `demo.Fresh` được gán `TTL_DONT_CACHE`, nên hai lần tải lần lượt sinh `v2` và `v3`. Hai tham chiếu này không trỏ cùng một object.
4. `ResourceBundle.clearCache(loader)` vô hiệu hóa các cache entries gắn với loader; tải lại `demo.Cached` tạo `v4`.
5. `first` vẫn trỏ tới `v1` dù entry của nó đã bị clear. `clearCache` **không sửa bundle đang được tham chiếu**.
6. Tổng cộng bốn instance đã được tạo.

`ListResourceBundle` trong chương trình **không tạo file và không truy cập mạng**; `Control.newBundle` khởi tạo resource trực tiếp để minh họa cache. Đây là **một trình diễn có kiểm soát**, không phải ví dụ đọc file dịch nóng trong môi trường production. `AtomicInteger` dùng để tăng bộ đếm an toàn nếu demo được mở rộng cho nhiều thread; điều đó không khiến mọi tùy biến `Control` bất kỳ tự động thread-safe.

### 8.1. Vì sao không cần Thread.sleep để kiểm thử?

Ví dụ không thử TTL tính bằng mili giây. Nó dùng hai chính sách rõ nghĩa:

- `TTL_NO_EXPIRATION_CONTROL`: theo hành vi cache mặc định.
- `TTL_DONT_CACHE`: luôn tạo bundle mới khi yêu cầu nạp.

Kết quả không phụ thuộc thời gian ngủ/tốc độ máy. Khi test TTL dương và `needsReload`, nên dùng fake clock/metadata test hoặc một nguồn có version thay đổi kiểm soát được, tránh kiểm thử mong manh dựa trên mtime và `Thread.sleep`.

### 8.2. Vì sao custom format hợp lệ?

`getFormats` trả `List.of("demo.memory")`, và `newBundle` hiểu đúng format đó. Đây là một định dạng **tự định nghĩa** trong Control, không phải file extension được JDK tìm tự động. Vì locale là `Locale.ROOT` và fallback được vô hiệu hóa, kết quả demo không phụ thuộc default locale của máy.

Trong ứng dụng thật nếu Control đọc từ file/DB, hãy đảm bảo `getFormats`, `newBundle`, `getTimeToLive` và `needsReload` thống nhất cùng một mô hình nguồn dữ liệu.

## 9. Những lỗi thường gặp

| Nhầm lẫn | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Sửa file properties rồi chờ `getBundle` đọc lại ngay | Cache có thể trả resource cũ | TTL hoặc clear/reload có kiểm chứng |
| Gọi `clearCache` rồi giữ biến `static final ResourceBundle` | UI vẫn hiện chuỗi cũ | Gọi lại `getBundle` và thay reference ở nơi cần |
| Tưởng `clearCache()` xóa mọi bundle của mọi loader | Còn cache ở scope khác | Chọn overload theo module/loader phù hợp |
| Tưởng `clearCache(loader)` chỉ xóa một locale | Có thể ảnh hưởng nhiều bundle cùng loader | Cân nhắc phạm vi và chi phí reload |
| Tưởng TTL hết hạn chắc chắn tạo object mới | `needsReload` có thể trả false | Phân biệt validate với reload |
| Đặt TTL 0 nhưng `needsReload` không phát hiện thay đổi | Vẫn nhận dữ liệu cũ | Triển khai version/mtime phù hợp |
| Dùng `TTL_DONT_CACHE` cho mọi request bận rộn | Tốn I/O, CPU, tăng tải dịch vụ | Thiết kế TTL/snapshot hoặc cache versioned |
| Thay đổi Control formats cho cùng base name tùy request | Cache có thể tái dùng bundle khác format | Giữ quy tắc Control nhất quán |
| Thêm bundle mới mà loader không thấy | `clearCache` không giúp tìm file | Kiểm tra classpath/JAR/classloader |
| Bỏ qua negative-cache/dummy | Locale mới vẫn chưa được phát hiện | Xử lý invalidation/TTL cho missing |
| Tưởng xóa cache làm GC ngay | Object còn tham chiếu vẫn tồn tại | Loại app references khi an toàn |
| Dùng Control overload trong named module | Có thể `UnsupportedOperationException` | Dùng kiến trúc module/provider phù hợp |
| Refresh mỗi key trong lúc render một trang | Chuỗi cùng trang lệch phiên bản bản dịch | Dùng một snapshot per request |
| Một node clear cache và tưởng toàn cluster đã xong | Các node khác vẫn hiển thị bản cũ | Phối hợp invalidation/deployment |
| Chỉ test trên IDE classpath rồi deploy qua modulepath | Scope/loading behavior khác | Integration test đúng packaging |

## 10. Kiểm thử cần có

Một module sử dụng ResourceBundle nên có các nhóm kiểm thử:

1. **Cache hit:** hai lần tải cùng base name/locale/loader/control khi chưa hết hạn cho cùng nội dung, không bắt buộc refetch.
2. **clearCache(loader):** sau clear, lần tải kế tiếp theo loader đó nhận bundle được nạp từ nguồn mới; reference cũ vẫn giữ dữ liệu trước đó.
3. **clearCache() module scope:** nếu dùng JPMS, kiểm tra đúng phạm vi caller module, không suy rộng ra toàn JVM.
4. **TTL_DONT_CACHE:** hai lần getBundle tạo các instance độc lập khi cơ chế Control không cache.
5. **TTL dương và TTL 0:** xác nhận expired dẫn đến kiểm tra `needsReload`, nhưng chỉ tạo bundle mới khi return true hoặc do các điều kiện cache khác.
6. **Fallback:** thiếu key trong locale cụ thể và key có trong parent; kiểm tra kết quả sau refresh parent.
7. **Negative lookup:** thiếu bundle, sau đó thêm; xác nhận chính sách phát hiện mới, kể cả cache dấu “không tồn tại”.
8. **ClassLoader:** hai loader có bundle cùng tên nhưng nguồn khác nhau; clear đúng loader không làm lẫn dữ liệu.
9. **Multi-thread:** nhiều request đồng thời đọc bundle, clear/reload trong khi có reference cũ; không có dữ liệu nửa chừng hoặc crash.
10. **Multi-node:** phiên bản bản dịch đúng trên từng node và có invalidation orchestration khi cần.
11. **Packaging:** so classpath/unnamed module và modulepath/named module; tránh Control unsupported ở named module.
12. **Lỗi tài nguyên:** không có base name, thiếu key, lỗi parsing properties, encoding không hợp lệ, I/O không thành công; thông báo lỗi và fallback có chính sách.
13. **Hành vi khi sửa file thực:** ghi mới hợp lệ, kiểm tra loader có thấy file và `needsReload` đánh giá mtime/version đúng, không chỉ “clear cache trả về không ném lỗi”.
14. **Hiệu năng:** đo cache hit rate, độ trễ reload, kích thước heap và số lượt đọc nguồn, đặc biệt với TTL ngắn.

Nếu cần thứ tự cập nhật chặt, nên kiểm thử với **version cụ thể** thay vì chỉ so “mới hơn” bằng thời gian hệ thống. Filesystem mtime có độ phân giải khác nhau; clock skew hoặc cập nhật trong cùng tick có thể khiến logic phát hiện thay đổi không ổn định.

## 11. Bài tập thực hành

1. Chạy `BundleCacheDemo`, chỉ ra chính xác hai lời gọi nào trả cùng instance và hai lời gọi nào tạo mới.
2. Bỏ `ResourceBundle.clearCache(loader)`; dự đoán `afterClear` trở thành giá trị nào trong chương trình và bộ đếm cuối.
3. Đổi `getTimeToLive` để `demo.Cached` cũng trả `TTL_DONT_CACHE`. Kiểm tra số lần `newBundle` được gọi và giải thích trade-off.
4. Tạo hai base name có cùng loader và cho phép caching; sau `clearCache(loader)`, kiểm tra tác động lên cả hai bundle.
5. Tạo `Messages.properties`, `Messages_vi.properties` và load `Locale.forLanguageTag("vi-VN")` với fallback cụ thể; thay một khóa trong bundle cha, rồi kiểm tra hiệu quả của refresh.
6. Tạo một `Control` trả TTL 0 và `needsReload` trả false; giải thích vì sao mỗi lần getBundle **không** tất yếu tạo instance mới.
7. Tạo một `Control` dùng version number ở nguồn (không dùng `Thread.sleep`); khi version thay đổi, `needsReload` trả true. Kiểm thử bundle được nạp lại.
8. Giữ `ResourceBundle` trong một field singleton, sau clear cache gọi `getString` trên field cũ và bundle mới; giải thích kết quả.
9. Thử thêm một file locale trong thư mục **không nằm trên classpath**; giải thích vì sao clear cache không tự giúp loader tìm file.
10. Dùng hai `ClassLoader` khác nhau để nạp resource cùng base name; quan sát phạm vi `clearCache(loader)`.
11. Viết checklist hot reload khi chạy nhiều JVM: xác định nguồn sự thật, version, cơ chế thông báo, scope invalidate và kiểm thử rollback.
12. Tìm hiểu `ResourceBundleProvider` trong named module, so khác biệt với Control ở unnamed module.

## 12. Tóm tắt

`ResourceBundle` **cache các bundle đã tải theo mặc định** để giảm chi phí lookup và khởi tạo. `ResourceBundle.clearCache()` xóa theo **caller module**, còn `clearCache(ClassLoader)` xóa theo **loader được truyền**; cả hai không sửa các bundle object mà mã nguồn vẫn giữ reference.

Khi cần tải lại bản dịch, phải phân biệt **xóa cache** với **nguồn tài nguyên thực sự có thể được tải lại**. `ResourceBundle.Control.getTimeToLive` quyết định thời điểm kiểm tra, `needsReload` quyết định có cần nạp mới sau khi expired; `TTL_DONT_CACHE` vô hiệu hóa caching. Một số lookup không tồn tại cũng được cache dưới dạng dấu hiệu thiếu, và class loader/JAR/JPMS có thể hạn chế việc nhìn thấy tài nguyên mới.

Chọn chiến lược theo sản phẩm: **cache mặc định + redeploy** cho tài nguyên đóng gói cố định; **TTL/versioned reload + invalidation chính xác** khi thực sự cần hot reload; quản lý cùng một snapshot trong request và phối hợp giữa các node khi chạy phân tán. Không gọi clearCache dàn trải mỗi request nếu không có nhu cầu.

**Tài liệu tham khảo:**

- Java SE 17, `ResourceBundle` (Cache Management, clearCache, getBundle): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html
- Java SE 17, `ResourceBundle.Control` (getTimeToLive, needsReload, newBundle): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html
- Java SE 17, `ListResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListResourceBundle.html
- Java SE 17, `ResourceBundleProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/ResourceBundleProvider.html
