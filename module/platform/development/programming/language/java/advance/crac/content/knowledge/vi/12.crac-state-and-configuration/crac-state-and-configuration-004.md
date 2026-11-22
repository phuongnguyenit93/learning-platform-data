# Biến môi trường, system property và cấu hình đã được ứng dụng lưu lại

Ứng dụng Java thường nhận cấu hình từ nhiều nguồn: biến môi trường của tiến trình, system property của JVM, file cấu hình, database, secret store hoặc dịch vụ cấu hình từ xa. Một phần cấu hình được đọc lúc khởi động rồi giữ trong heap; phần khác được truy vấn mỗi khi cần. Khi dùng CRaC, checkpoint lưu trạng thái tiến trình tại một thời điểm, vì vậy những giá trị đã được đọc và lưu trong bộ nhớ có thể tiếp tục tồn tại sau restore.

Điều này tạo ra một điểm cần chú ý: cấu hình trong tiến trình có thể phản ánh thời điểm checkpoint, trong khi cấu hình bên ngoài đã thay đổi. Restore không tự động chạy lại toàn bộ quy trình khởi động để nạp mọi biến môi trường, system property hoặc file cấu hình từ đầu. Ứng dụng cần xác định nguồn nào là cấu hình khởi động, nguồn nào cần làm mới sau restore và nguồn nào phải được kiểm tra lại trước khi tiếp tục phục vụ.

## 1. Phân biệt các nguồn cấu hình

Các nguồn cấu hình thường gặp có vòng đời khác nhau:

| Nguồn | Cách Java truy cập | Vòng đời điển hình | Điều cần chú ý sau restore |
|---|---|---|---|
| Biến môi trường | System.getenv(...) | Được cung cấp cho tiến trình khi khởi chạy | Tiến trình được restore thường tiếp tục với môi trường đã nhận lúc khởi chạy; thay đổi cấu hình của orchestrator không tự cập nhật vào tiến trình đang chạy |
| System property | System.getProperty(...) | Được truyền lúc khởi chạy bằng -D hoặc thay đổi trong JVM bằng System.setProperty | Giá trị JVM tại checkpoint có thể được khôi phục; cần làm mới nếu ứng dụng dùng property cho cấu hình động |
| File cấu hình | Files, Properties, YAML/JSON parser hoặc framework | File nằm ngoài heap; object cấu hình đã parse có thể được giữ trong heap | File có thể thay đổi trong thời gian checkpoint, còn object đã parse có thể vẫn giữ giá trị cũ |
| Database/config service | JDBC, HTTP client hoặc SDK | Trạng thái do dịch vụ bên ngoài quản lý | Kết nối, cache và phiên bản cấu hình có thể cần xác minh hoặc truy vấn lại |
| Secret store | SDK hoặc API của nền tảng | Secret có thể được xoay vòng độc lập với tiến trình | Token, credential hoặc secret trong heap có thể hết hạn hay bị thu hồi |
| Cấu hình ứng dụng đã lưu trong heap | Field, static field, singleton, cache | Tồn tại cùng trạng thái tiến trình | Có thể được khôi phục đúng giá trị tại checkpoint nhưng đã cũ so với nguồn chuẩn |

Điểm cần phân biệt là nguồn cấu hình và bản sao cấu hình trong ứng dụng. Một file hoặc config service có thể là nguồn chuẩn; object Java được parse từ nguồn đó chỉ là bản sao trong bộ nhớ.

## 2. Biến môi trường của tiến trình

Biến môi trường thường được đặt bởi shell, container runtime, orchestrator hoặc hệ thống triển khai trước khi tiến trình Java khởi động. Java đọc các giá trị này bằng System.getenv:

~~~java
String databaseUrl = System.getenv("APP_DATABASE_URL");
String region = System.getenv("APP_REGION");
~~~

Có thể lấy toàn bộ map môi trường:

~~~java
Map<String, String> environment = System.getenv();
~~~

Map do System.getenv() trả về là không thể sửa đổi qua API Java. Ứng dụng không thể dùng map này để cập nhật biến môi trường của tiến trình bằng cách gọi put().

### Biến môi trường thường là cấu hình khởi động

Trong môi trường container, biến môi trường thường được gắn vào container hoặc process khi tạo tiến trình. Nếu cấu hình deployment thay đổi, tiến trình đang chạy không tự nhận giá trị mới chỉ vì manifest hoặc secret của orchestrator đã được cập nhật. Thông thường cần tạo tiến trình/container mới để nhận bộ biến môi trường mới.

Khi CRaC restore một tiến trình từ checkpoint, ứng dụng tiếp tục từ trạng thái tiến trình đã được lưu. Không nên giả định việc restore tương đương với tạo một process mới từ image và nạp lại toàn bộ environment của deployment hiện tại.

Ví dụ, ứng dụng đã đọc APP_REGION thành ap-southeast-1 lúc khởi động và lưu vào field:

~~~java
public final class RegionConfig {
    private final String region;

    public RegionConfig() {
        this.region = System.getenv("APP_REGION");
    }

    public String region() {
        return region;
    }
}
~~~

Field region thuộc trạng thái trong heap. Sau restore, object RegionConfig có thể tiếp tục giữ giá trị đã đọc lúc khởi động/checkpoint. Nếu nền tảng triển khai đã thay đổi biến môi trường cho lần khởi chạy mới, điều đó không tự thay đổi field trong object đã được khôi phục.

Vì vậy, hãy dùng environment cho cấu hình có chủ đích gắn với vòng đời process, ví dụ cổng listen, profile triển khai hoặc tên vùng được cố định khi khởi động. Với cấu hình cần thay đổi mà không khởi động process mới, nên dùng một nguồn cấu hình động có API đọc lại và cơ chế versioning.

### Không dùng biến môi trường làm kho cấu hình động

Không nên thiết kế ứng dụng với giả định có thể cập nhật System.getenv() sau restore để nhận secret hoặc endpoint mới. Nếu cần xoay vòng credential hoặc cập nhật endpoint, hãy truy vấn secret/config service hoặc một nguồn có khả năng refresh rõ ràng.

Ngoài ra, không nên ghi toàn bộ map environment vào log. Biến môi trường có thể chứa password, token, connection string hoặc thông tin nhạy cảm khác.

## 3. System property của JVM

System property là cặp key/value thuộc JVM. Có thể truyền property lúc khởi chạy bằng tùy chọn -D:

~~~shell
java -Dapp.region=ap-southeast-1 -Dapp.mode=production -jar app.jar
~~~

Trong Java, đọc giá trị bằng System.getProperty:

~~~java
String region = System.getProperty("app.region");
String mode = System.getProperty("app.mode", "development");
~~~

Ứng dụng cũng có thể thay đổi property lúc chạy:

~~~java
System.setProperty("app.feature.new-checkout", "true");
~~~

Khác với environment map, System properties có thể được thay đổi thông qua System.setProperty hoặc System.clearProperty. Các property và giá trị của chúng là trạng thái JVM; nếu ứng dụng đã thay đổi chúng trước checkpoint, trạng thái đó có thể được giữ lại khi restore.

### System property không tự nạp lại từ command line

Tùy chọn -D được xử lý khi JVM khởi động. Restore không chạy lại command line và không khởi tạo một JVM mới. Vì vậy, property đã được đặt khi process khởi động hoặc được thay đổi trong runtime có thể tiếp tục giữ giá trị cũ sau restore.

Nếu một property đại diện cho cấu hình động, hãy làm mới từ nguồn chuẩn bằng một thành phần quản lý cấu hình. Đừng mong đợi thay đổi tham số khởi chạy ở deployment sẽ được áp dụng vào một tiến trình đã được restore.

### System properties toàn cục cần được quản lý cẩn thận

System properties là trạng thái toàn cục của JVM. Việc thay đổi chúng có thể ảnh hưởng đến thư viện khác và những thành phần đã đọc giá trị trước đó.

Ví dụ, thư viện có thể đọc property một lần khi class được khởi tạo:

~~~java
public final class ClientDefaults {
    public static final int TIMEOUT_MS =
            Integer.getInteger("app.client.timeout", 3000);
}
~~~

Thay đổi System.setProperty sau đó không làm static field TIMEOUT_MS tự thay đổi. Cả property lẫn giá trị cache trong static field có thể được giữ lại trong checkpoint với các giá trị khác nhau.

Với cấu hình động, nên tránh để nhiều lớp tự đọc và cache System properties theo những thời điểm khác nhau. Dùng một thành phần quản lý cấu hình có phiên bản và quy tắc refresh rõ ràng.

## 4. Cấu hình đã được ứng dụng lưu trong heap

Ứng dụng thường đọc nhiều nguồn cấu hình khi khởi động rồi chuyển thành object bất biến để sử dụng nhanh:

~~~java
public record AppConfig(
        String databaseUrl,
        String region,
        int requestTimeoutMillis,
        boolean newCheckoutEnabled) {}
~~~

Một singleton hoặc Spring bean có thể giữ object AppConfig này. Nếu object nằm trong heap tại thời điểm checkpoint, nó là một phần trạng thái ứng dụng được khôi phục.

Ví dụ:

~~~java
public final class ConfigHolder {
    private volatile AppConfig current;

    public ConfigHolder(AppConfig initialConfig) {
        this.current = initialConfig;
    }

    public AppConfig current() {
        return current;
    }

    public void replace(AppConfig next) {
        this.current = next;
    }
}
~~~

Nếu current đã được thay bằng cấu hình mới trước checkpoint, giá trị mới có thể được giữ trong heap. Nếu nguồn cấu hình bên ngoài thay đổi sau checkpoint, object current được restore vẫn có thể chứa phiên bản cũ.

Đây là khác biệt giữa:

- **Trạng thái đã lưu trong tiến trình:** object cấu hình, static field, cache, singleton.
- **Nguồn cấu hình chuẩn:** file, database, config server, secret manager hoặc nền tảng triển khai.

Nếu cấu hình cần phản ánh trạng thái hiện tại của nguồn chuẩn, ứng dụng phải đọc lại hoặc xác minh phiên bản sau restore. Không nên giả định checkpoint tự làm mới object đã parse.

## 5. File cấu hình và dữ liệu bên ngoài

File cấu hình nằm trên filesystem, còn object được parse từ file nằm trong heap. Hai phần này có thể không cùng phiên bản sau restore.

Ví dụ:

1. Ứng dụng đọc app.yml phiên bản 10.
2. Cấu hình được parse thành AppConfig và lưu trong singleton.
3. Tiến trình tạo checkpoint.
4. Trong lúc tiến trình không hoạt động, app.yml được cập nhật lên phiên bản 11.
5. Tiến trình được restore và object AppConfig phiên bản 10 vẫn tồn tại.

Nếu ứng dụng cần dùng phiên bản 11, nó phải đọc lại file hoặc nhận sự kiện refresh từ nguồn cấu hình. Việc file đã đổi không làm object Java tự cập nhật.

Đối với config service hoặc database, tình huống tương tự xảy ra: server có thể trả về cấu hình mới, nhưng cache trong heap vẫn giữ phiên bản cũ. Sau restore, ứng dụng cần kiểm tra cache TTL, version hoặc ETag và tải lại khi cần.

Không phải cấu hình nào cũng cần reload. Một số giá trị như schema mapping hoặc profile cố định có thể được xem là cấu hình khởi động. Một số giá trị như endpoint, feature flag, quota hoặc credential có thể cần refresh. Quyết định này phải xuất phát từ yêu cầu vận hành của ứng dụng.

## 6. Phân loại cấu hình theo chính sách vòng đời

Một cách hữu ích là phân loại cấu hình theo mức độ thay đổi:

| Nhóm | Ví dụ | Chính sách phù hợp |
|---|---|---|
| Cấu hình cố định theo process | Port, profile, vùng triển khai, tên instance | Giữ giá trị khởi động; nếu muốn đổi cần tạo process mới hoặc có quy trình restart |
| Cấu hình JVM | System property, timezone, locale, flag thư viện | Giữ giá trị JVM tại checkpoint; chỉ thay đổi qua cơ chế được hỗ trợ và có kiểm soát |
| Cấu hình động | Feature flag, timeout, endpoint, giới hạn request | Refresh hoặc kiểm tra version sau restore nếu nguồn có thể thay đổi |
| Credential/secret | Password database, API token, certificate | Xác minh thời hạn và quyền truy cập; làm mới qua secret provider khi cần |
| Cấu hình nghiệp vụ đã cache | Bảng giá, danh sách quyền, quy tắc định tuyến | Kiểm tra version/TTL và tải lại từ nguồn chuẩn nếu đã cũ |
| Trạng thái runtime | Số request, bộ đếm, cache tạm, trạng thái scheduler | Giữ nếu vẫn hợp lệ; tái tạo hoặc đối soát nếu phụ thuộc thời gian và dịch vụ bên ngoài |

Không nên reload toàn bộ cấu hình một cách mù quáng. Một số giá trị chỉ được phép đặt lúc khởi động; thay đổi chúng khi ứng dụng đang chạy có thể làm các thành phần sử dụng những giá trị không đồng nhất. Chính sách cần chỉ rõ trường nào có thể refresh nóng và trường nào yêu cầu restart.

## 7. Tổ chức ConfigProvider có khả năng refresh

Một ConfigProvider có thể gom logic đọc nguồn chuẩn, parse, validate và công bố phiên bản cấu hình mới.

~~~java
public interface ConfigSource {
    LoadedConfig load() throws Exception;
}

public record LoadedConfig(long version, AppConfig config) {}

public final class ConfigProvider {
    private final ConfigSource source;
    private volatile LoadedConfig current;

    public ConfigProvider(ConfigSource source, LoadedConfig initial) {
        this.source = source;
        this.current = initial;
    }

    public AppConfig current() {
        return current.config();
    }

    public long version() {
        return current.version();
    }

    public synchronized void refresh() throws Exception {
        LoadedConfig candidate = source.load();
        validate(candidate.config());
        current = candidate;
    }

    private void validate(AppConfig config) {
        if (config.requestTimeoutMillis() <= 0) {
            throw new IllegalArgumentException(
                    "Request timeout must be positive");
        }
        if (config.databaseUrl() == null
                || config.databaseUrl().isBlank()) {
            throw new IllegalArgumentException(
                    "Database URL is required");
        }
    }
}
~~~

Ví dụ này minh họa cách chỉ công bố cấu hình sau khi đọc và validate thành công. current là volatile để các thread nhìn thấy object cấu hình mới. AppConfig là record bất biến, giúp tránh một thread nhìn thấy object ở trạng thái cập nhật dở.

Trong ứng dụng thực tế, ConfigSource có thể đọc file, database hoặc config service. LoadedConfig.version có thể là revision, generation hoặc ETag do nguồn chuẩn cung cấp. Nếu nguồn không hỗ trợ version, ứng dụng cần dùng một cơ chế xác định độ mới phù hợp.

Refresh không nên cập nhật từng field rời rạc trong nhiều object dùng chung mà không có cơ chế đồng bộ. Nếu nhiều thành phần cần cùng một bộ cấu hình nhất quán, hãy công bố một snapshot bất biến mới để tất cả cùng đọc.

## 8. Kết hợp refresh cấu hình với CRaC Resource

Nếu cấu hình động cần được kiểm tra lại sau restore, có thể tạo một Resource để gọi ConfigProvider.refresh trong afterRestore:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ConfigRefreshResource implements Resource {
    private final ConfigProvider configProvider;

    public ConfigRefreshResource(ConfigProvider configProvider) {
        this.configProvider = configProvider;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Không cần đóng ConfigProvider nếu nó chỉ giữ snapshot trong heap.
        // Nếu nguồn cấu hình có connection riêng, chủ sở hữu nguồn đó
        // cần quản lý vòng đời connection theo integration của nó.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        configProvider.refresh();
    }
}
~~~

Đây là ví dụ cho nguồn cấu hình có thể truy vấn lại sau restore. Nếu refresh thất bại, callback ném lỗi để quá trình phục hồi được nhận biết. Ứng dụng không nên đánh dấu ready khi cấu hình bắt buộc chưa được tải hoặc validate.

Không phải ConfigProvider nào cũng cần Resource. Nếu cấu hình chỉ cố định theo process, không có nhu cầu refresh sau restore, object trong heap có thể được giữ nguyên. Nếu nguồn cấu hình dùng HTTP client, database connection hoặc file handle có vòng đời riêng, Resource quản lý connection đó nên thuộc về thành phần sở hữu nguồn, tránh đóng/mở cùng tài nguyên từ nhiều callback.

### Chọn thứ tự phục hồi hợp lý

Nếu ConfigProvider cần một HTTP client để đọc cấu hình, client phải sẵn sàng trước khi gọi refresh. Nếu client dùng credential lấy từ secret store, secret cần được xác minh hoặc làm mới trước khi tạo client.

Một thứ tự logic có thể là:

~~~text
Restore tiến trình
      |
      v
Làm mới credential cần thiết
      |
      v
Mở lại config client
      |
      v
Tải và validate cấu hình động
      |
      v
Tạo/làm mới dependency dùng cấu hình
      |
      v
Health check và readiness
      |
      v
Nhận traffic
~~~

Thứ tự callback giữa các Resource độc lập phải dựa trên bảo đảm của CRaC runtime hoặc framework cụ thể. Nếu ứng dụng cần thứ tự phụ thuộc, hãy dùng một thành phần điều phối có chủ sở hữu rõ ràng hoặc cơ chế lifecycle của framework.

## 9. Cấu hình và secret trong checkpoint

Environment variable, system property và object cấu hình có thể chứa thông tin nhạy cảm:

- Database password.
- API key hoặc access token.
- Private key hoặc certificate material.
- Connection string có thông tin xác thực.
- Thông tin định tuyến nội bộ hoặc tên dịch vụ nhạy cảm.

Nếu các giá trị này đã được đọc vào heap, checkpoint có thể chứa bản sao của chúng. Vì vậy, checkpoint image và nơi lưu checkpoint cần được bảo vệ như một artifact có thể chứa secret.

Một số nguyên tắc:

- Giới hạn quyền đọc và ghi checkpoint image.
- Không ghi environment, system properties hoặc object config nhạy cảm vào log.
- Tránh đưa secret vào field sống lâu nếu có thể dùng credential provider có khả năng refresh.
- Xác minh token/credential sau restore nếu chúng có thể hết hạn trong khoảng thời gian tiến trình tạm dừng.
- Xoay vòng secret theo quy trình của hệ thống quản lý secret; không giả định thay đổi environment ở deployment sẽ tự thay đổi giá trị trong process đã restore.
- Khi secret được refresh, làm mới các client hoặc pool đang dùng secret cũ theo hướng dẫn của thư viện.

Không nên tự ý xóa secret khỏi object đang được thư viện sử dụng nếu chưa hiểu hợp đồng của thư viện. Cần xác định rõ thời điểm credential được tiêu thụ, cách tạo lại client và cách dừng sử dụng credential cũ.

## 10. Static initializer và cấu hình được đọc một lần

Một số class đọc cấu hình trong static initializer:

~~~java
public final class FeatureFlags {
    public static final boolean NEW_FLOW =
            Boolean.getBoolean("app.feature.new-flow");

    private FeatureFlags() {}
}
~~~

Giá trị NEW_FLOW được tính khi class được khởi tạo. Thay đổi system property sau đó không tự tính lại static field. Khi checkpoint lưu trạng thái class và static field, giá trị này có thể tiếp tục được dùng sau restore.

Tương tự, framework có thể đọc environment hoặc system property khi tạo ApplicationContext rồi giữ chúng trong bean. Reload file bên ngoài không tự động làm mới bean hoặc static field.

Nếu giá trị cần thay đổi trong thời gian chạy, tránh đọc một lần trong static initializer. Hãy dùng ConfigProvider hoặc một cơ chế refresh chính thức của framework. Nếu giá trị chỉ thay đổi khi process restart, hãy ghi rõ đó là cấu hình startup-only và tạo process mới khi muốn áp dụng thay đổi.

## 11. Các tình huống thường gặp sau restore

| Tình huống | Điều có thể xảy ra | Cách xử lý |
|---|---|---|
| Deployment thay đổi biến môi trường trong lúc tiến trình đã checkpoint | Process được restore vẫn có thể tiếp tục với environment cũ | Tạo process mới để nhận startup environment mới hoặc đọc cấu hình động từ nguồn khác |
| System.setProperty được gọi trước checkpoint | JVM khôi phục property theo trạng thái đã lưu | Kiểm tra lại nếu property đại diện cho giá trị có thể thay đổi |
| File cấu hình được sửa sau checkpoint | Object đã parse trong heap có thể vẫn giữ phiên bản cũ | Đọc lại file, validate và công bố snapshot mới |
| Feature flag đổi ở config service | Cache trong heap có thể chưa cập nhật | Kiểm tra revision/TTL và refresh |
| Secret hết hạn trong lúc checkpoint | Object credential cũ còn trong heap nhưng không còn được chấp nhận | Lấy secret/token mới và tạo lại client phụ thuộc |
| Database URL thay đổi | DataSource hoặc pool cũ có thể vẫn trỏ tới endpoint cũ | Tạo hoặc cấu hình lại pool theo quy trình an toàn |
| Cấu hình mới không hợp lệ | Refresh có thể tạo trạng thái nửa cũ nửa mới nếu cập nhật từng field | Parse và validate snapshot trước, chỉ công bố khi hoàn chỉnh |

Các trường hợp này cho thấy restore cần một chính sách cấu hình rõ ràng. Không nên refresh mọi thứ một cách tự động nếu điều đó có thể thay đổi hành vi nghiệp vụ không an toàn.

## 12. Những hiểu nhầm thường gặp

**“Environment variable thay đổi ở container thì System.getenv() tự cập nhật.”**

Thông thường không đúng với một tiến trình đang chạy. Environment được cung cấp khi process khởi chạy; cập nhật manifest hoặc secret của orchestrator không tự thay đổi process environment. Restore cũng không tạo process mới.

**“System property được truyền bằng -D sẽ được đọc lại khi restore.”**

Không đúng. -D được xử lý lúc JVM khởi động. Restore tiếp tục JVM đã được checkpoint; không chạy lại command line.

**“File cấu hình đã thay đổi nên object cấu hình trong Spring bean cũng thay đổi.”**

Không tự động. Object đã parse và lưu trong heap vẫn giữ giá trị của nó cho tới khi framework hoặc ứng dụng thực hiện refresh.

**“Cứ reload toàn bộ cấu hình sau restore là an toàn.”**

Không nhất thiết. Một số trường chỉ được phép đặt lúc khởi động; thay đổi nóng có thể làm dependency đang chạy không nhất quán. Cần phân loại startup-only và dynamic config.

**“Secret trong heap không nằm trong checkpoint.”**

Không nên giả định như vậy. Nếu secret đã được đọc vào object hoặc system property, checkpoint có thể chứa bản sao trong trạng thái tiến trình. Bảo vệ checkpoint artifact và hạn chế secret sống lâu trong heap.

**“ConfigProvider đã refresh thì mọi client tự dùng cấu hình mới.”**

Không đúng nếu client hoặc pool đã được tạo từ cấu hình cũ. Thành phần sở hữu dependency cần có bước tạo lại hoặc cập nhật theo hợp đồng của thư viện.

## 13. Kiểm thử chính sách cấu hình

Nên kiểm thử trên đúng JDK/CRaC runtime và nền tảng triển khai:

- Khởi động với một bộ environment và system properties cụ thể, tạo checkpoint rồi restore.
- Thay đổi file hoặc config service trong thời gian checkpoint và xác nhận chính sách refresh hoạt động như dự kiến.
- Thay đổi feature flag và kiểm tra snapshot cấu hình mới được công bố nguyên tử.
- Làm hết hạn hoặc thu hồi credential trong lúc tiến trình tạm dừng, sau đó xác nhận ứng dụng làm mới client.
- Làm cho config service không sẵn sàng để kiểm tra callback báo lỗi và readiness không mở quá sớm.
- Cung cấp cấu hình không hợp lệ để xác nhận snapshot cũ vẫn được giữ hoặc ứng dụng chuyển sang trạng thái lỗi theo chính sách.
- Thực hiện nhiều chu kỳ checkpoint/restore để phát hiện refresh trùng, listener trùng hoặc client còn dùng credential cũ.
- Kiểm tra checkpoint artifact và log không làm lộ secret ngoài phạm vi được phép.

Nên ghi nhận revision cấu hình đang dùng, thời điểm refresh và trạng thái thành công/thất bại. Không ghi giá trị secret. Readiness cần phản ánh các cấu hình và dependency bắt buộc đã được xác minh.

## 14. Kết luận

Biến môi trường, system property và cấu hình ứng dụng có vòng đời khác nhau. Environment thường gắn với lần khởi chạy process; system properties thuộc trạng thái JVM; object cấu hình đã parse nằm trong heap; còn file, database, config service và secret store tiếp tục thay đổi theo vòng đời bên ngoài.

CRaC khôi phục trạng thái tiến trình tại checkpoint, vì vậy những giá trị đã lưu trong heap có thể cũ so với nguồn cấu hình chuẩn. Ứng dụng cần phân loại cấu hình startup-only và dynamic, xác định giá trị nào phải refresh hoặc xác minh sau restore, bảo vệ secret trong checkpoint artifact và chỉ mở traffic sau khi cấu hình cùng các dependency bắt buộc đã sẵn sàng.
