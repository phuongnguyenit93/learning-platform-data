# Tách cấu hình lúc dựng ảnh khỏi cấu hình lúc triển khai

Trong ứng dụng Java dùng CRaC (Coordinated Restore at Checkpoint), việc phân chia cấu hình thành hai giai đoạn có ảnh hưởng trực tiếp đến khả năng tái sử dụng checkpoint. Một phần cấu hình mô tả ứng dụng và có thể cố định khi build; phần còn lại chỉ biết khi triển khai vào một môi trường cụ thể, chẳng hạn địa chỉ database, credential, endpoint dịch vụ, port và feature flag.

Điểm cần chú ý là checkpoint lưu trạng thái của tiến trình, bao gồm cả các object Java đã được tạo, giá trị static, system property và dữ liệu cấu hình mà ứng dụng đã đọc vào bộ nhớ. Nếu ứng dụng đọc cấu hình của môi trường A trước khi checkpoint, restore checkpoint đó ở môi trường B không tự động thay các giá trị trong bộ nhớ thành cấu hình B.

Vì vậy, cần xác định rõ cấu hình nào được phép tồn tại trong checkpoint, cấu hình nào phải được nạp sau restore và resource nào cần được tạo lại từ cấu hình triển khai. Cách phân chia này giúp một checkpoint dùng chung cho nhiều môi trường mà vẫn kết nối đúng database, dịch vụ và secret của từng môi trường.

## 1. Hai giai đoạn cấu hình

### 1.1. Cấu hình lúc dựng ảnh (build-time configuration)

Build-time configuration là các giá trị được xác định khi biên dịch ứng dụng, đóng gói artifact hoặc chuẩn bị checkpoint dùng chung. Chúng mô tả bản thân ứng dụng và thường không thay đổi giữa dev, staging và production.

Ví dụ:

- Phiên bản ứng dụng và build identifier.
- Java release target, dependency và plugin version.
- Tập tính năng được biên dịch hoặc đóng gói.
- Đường dẫn mặc định ổn định trong image.
- Tên module, schema version mà ứng dụng hỗ trợ.
- Các giá trị mặc định không chứa thông tin riêng của môi trường.
- JVM/JDK build và các tùy chọn cần thiết để tạo checkpoint.

Những giá trị này có thể được đóng gói cùng artifact hoặc ghi trong metadata của checkpoint. Chúng nên ổn định, có thể truy xuất nguồn gốc và không chứa secret.

### 1.2. Cấu hình lúc triển khai (deployment/runtime configuration)

Runtime configuration mô tả môi trường mà instance sẽ phục vụ sau khi chạy hoặc restore. Các giá trị này có thể khác giữa từng deployment và có thể thay đổi trong vòng đời ứng dụng.

Ví dụ:

- JDBC URL, hostname, port và tên database.
- Username, password, API key, certificate và token.
- Endpoint của service bên ngoài.
- Port lắng nghe, domain và network route.
- Kích thước pool, timeout theo tải của môi trường.
- Feature flag, tenant, region và policy triển khai.
- Log level, tracing endpoint và thông tin monitoring.
- Thư mục mount chứa file cấu hình hoặc secret.

Runtime configuration cần được cung cấp từ môi trường triển khai, config service, secret manager hoặc file được mount. Nếu checkpoint dùng chung cho nhiều môi trường, ứng dụng nên đọc các giá trị này sau restore và khởi tạo resource phụ thuộc từ cấu hình mới.

### 1.3. So sánh

| Tiêu chí | Build-time | Deployment/runtime |
|---|---|---|
| Thời điểm xác định | Build artifact hoặc chuẩn bị checkpoint | Khi triển khai hoặc sau restore |
| Mức độ thay đổi | Thường cố định theo bản build | Có thể khác giữa môi trường và thay đổi theo thời gian |
| Ví dụ | Version, dependency, Java target | DB URL, credentials, endpoint, port |
| Nơi lưu | Artifact, image metadata, manifest build | Environment provider, mounted config, secret manager |
| Có nên nằm trong checkpoint dùng chung? | Có, nếu không chứa dữ liệu nhạy cảm và phụ thuộc môi trường | Chỉ giữ các giá trị không nhạy cảm, ổn định; dữ liệu riêng môi trường nên nạp sau restore |
| Khi thay đổi | Thường cần build artifact/checkpoint mới | Có thể reload hoặc tạo lại resource theo policy |

Một giá trị không tự động là build-time chỉ vì nó được đặt trong file cấu hình. Hãy phân loại theo ý nghĩa: nếu giá trị thay đổi theo môi trường triển khai, đó là runtime configuration dù file chứa nó được đóng gói trong image.

## 2. Vì sao CRaC làm ranh giới cấu hình trở nên quan trọng?

Một checkpoint không chỉ chứa JAR hoặc file cấu hình. Nó lưu trạng thái tiến trình đã chạy, có thể bao gồm:

- Object cấu hình được tạo từ file properties hoặc YAML.
- Spring bean và singleton đã nhận giá trị cấu hình.
- Static field và cache giữ endpoint, port hoặc feature flag.
- System properties đã đọc lúc startup.
- Connection pool, HTTP client và thread pool được tạo từ cấu hình.
- Credential, token hoặc dữ liệu nhạy cảm đã được đưa vào heap.
- DNS result, connection state và dữ liệu runtime khác.

Giả sử ứng dụng được khởi động trong staging:

~~~text
Staging environment
    DB_URL = jdbc:postgresql://staging-db/orders
    API_URL = https://staging-api.example
            │
            ▼
Ứng dụng đọc cấu hình và tạo object
            │
            ▼
Checkpoint tiến trình
            │
            ▼
Restore cùng checkpoint trong production
~~~

Nếu các object đã giữ URL staging trong field, chúng vẫn có thể giữ giá trị đó sau restore. Việc container production có environment variable mới không tự sửa các object đã được khôi phục.

### 2.1. Environment variable không phải cơ chế reload tự động

Environment variable được cung cấp cho process khi process được tạo. Ứng dụng đọc chúng qua System.getenv(). Sau đó, nếu code sao chép giá trị vào object hoặc static field, giá trị đã đọc tiếp tục tồn tại trong trạng thái process.

Ví dụ:

~~~java
public final class DatabaseSettings {

    public static final String JDBC_URL =
            System.getenv("DB_JDBC_URL");
}
~~~

Nếu class được khởi tạo trước checkpoint, JDBC_URL đã được gán. Restore checkpoint đó ở môi trường khác không khiến static field tự đọc lại environment variable.

Tương tự, System.setProperty() hoặc truyền -D... lúc khởi động chỉ đặt giá trị trong process hiện tại. Restore không phải một lần khởi động JVM mới để đọc lại toàn bộ biến môi trường và system property từ deployment mới.

### 2.2. File cấu hình đã đọc cũng trở thành trạng thái trong bộ nhớ

Ví dụ, ứng dụng đọc runtime.properties lúc startup rồi giữ một object:

~~~java
Properties properties = new Properties();

try (var reader = Files.newBufferedReader(configPath)) {
    properties.load(reader);
}

String databaseUrl = properties.getProperty("database.url");
~~~

Sau checkpoint, nếu file bên ngoài được thay đổi, object Properties đã nằm trong heap không tự cập nhật. Muốn dùng cấu hình mới, ứng dụng phải đọc lại file hoặc gọi config service sau restore và cập nhật các thành phần phụ thuộc.

### 2.3. Resource đã tạo từ cấu hình cũ

Ngay cả khi cập nhật object cấu hình, resource đã tạo từ cấu hình cũ vẫn cần được thay thế. Ví dụ:

- HikariDataSource đã tạo connection tới staging database.
- HTTP client giữ connection pool tới staging API.
- Listener đã bind port cũ.
- Consumer đã subscribe vào queue cũ.
- Scheduler đang chạy lịch của tenant cũ.

Reload một field không thay đổi endpoint bên trong các resource này. Cần đóng hoặc dừng resource cũ theo thứ tự phù hợp rồi tạo resource mới bằng cấu hình runtime đã xác thực.

## 3. Thiết kế cấu hình dùng chung cho nhiều môi trường

Một checkpoint có thể được dùng theo hai mô hình khác nhau.

### 3.1. Checkpoint riêng cho từng môi trường

Ứng dụng được khởi động với cấu hình của một môi trường, warm-up và tạo checkpoint ngay trong môi trường đó.

~~~text
Build artifact
     │
     ├── Deploy staging config ──> Start/warm-up ──> Checkpoint staging
     │
     └── Deploy production config -> Start/warm-up -> Checkpoint production
~~~

Ưu điểm là ứng dụng đã có đầy đủ resource và trạng thái cấu hình tương ứng môi trường. Restore có thể nhanh vì không cần khởi tạo lại toàn bộ thành phần.

Đổi lại, checkpoint gắn với môi trường đã tạo nó. Không nên lấy checkpoint staging rồi dùng như checkpoint production. Cấu hình và secret có thể nằm trong heap; connection, file descriptor và namespace cũng có thể phụ thuộc môi trường gốc. Khi credential hoặc endpoint thay đổi, checkpoint cũ có thể chứa giá trị đã lỗi thời.

### 3.2. Checkpoint dùng chung, nạp runtime config sau restore

Với nhiều môi trường, có thể tạo checkpoint chung mà chưa nạp cấu hình riêng của deployment:

~~~text
Build artifact
     │
     ▼
Chuẩn bị checkpoint chung
  - Nạp class và thư viện
  - Warm-up code an toàn
  - Không nạp secret/runtime endpoint
  - Chưa tạo resource gắn với môi trường
     │
     ▼
Checkpoint dùng chung
     │
     ├── Restore staging ──> Load staging config ──> Create staging resources
     │
     └── Restore production -> Load production config -> Create production resources
~~~

Ở mô hình này, phần trạng thái có thể tái sử dụng được chuẩn bị trước; cấu hình riêng và resource phụ thuộc môi trường được khởi tạo sau restore.

Đây là mô hình phù hợp khi muốn dùng cùng checkpoint artifact cho nhiều deployment. Nó yêu cầu ứng dụng có một bootstrap/lifecycle coordinator để nạp cấu hình và khởi tạo dependency sau restore, trước khi nhận traffic.

### 3.3. Chọn mô hình theo mục tiêu triển khai

| Mục tiêu | Mô hình phù hợp |
|---|---|
| Tối ưu restore cho một môi trường cố định | Checkpoint riêng cho môi trường |
| Dùng một checkpoint cho dev, staging và production | Checkpoint chung, nạp runtime config sau restore |
| Secret thay đổi thường xuyên | Nạp secret sau restore từ secret manager hoặc mounted secret |
| Endpoint database thay đổi giữa các môi trường | Nạp URL sau restore rồi tạo connection pool tương ứng |
| JVM option khác nhau giữa các môi trường | Tạo checkpoint phù hợp từng cấu hình JVM hoặc dùng cách khởi chạy riêng; không giả định restore thay đổi được JVM đã checkpoint |
| Warm-up code nhưng không muốn lưu dữ liệu môi trường | Warm-up bằng dữ liệu giả lập/an toàn trước checkpoint, tạo resource thật sau restore |

## 4. Phân loại cấu hình trước khi đóng gói

Có thể chia cấu hình thành ba nhóm để quyết định thời điểm nạp.

### 4.1. Cấu hình bất biến theo bản build

Nhóm này mô tả artifact:

- Version và build ID.
- Java bytecode level.
- Danh sách thư viện và driver.
- Tập tính năng đã biên dịch.
- Schema compatibility mà ứng dụng hỗ trợ.
- Các giá trị mặc định không gắn với môi trường.

Có thể đóng gói chúng vào JAR hoặc image. Nếu thay đổi nhóm này, thường cần build artifact mới và tạo checkpoint tương ứng.

### 4.2. Cấu hình deployment

Nhóm này mô tả nơi ứng dụng chạy:

- Database endpoint và tên schema/database.
- URL của service bên ngoài.
- HTTP port và network binding.
- Pool size và timeout.
- Tenant, region, feature flag.
- Log level và monitoring endpoint.

Với checkpoint dùng chung, không nên nạp các giá trị này trước khi tạo checkpoint. Nạp từ file được mount hoặc config service sau restore.

### 4.3. Secret và credential

Secret cần được quản lý riêng:

- Database password.
- API key và access token.
- Private key, client certificate và TLS material.
- Refresh token và credential của message broker.

Không đưa secret vào source code, build argument, image layer hoặc checkpoint dùng chung. Một secret đã được đọc vào heap trước checkpoint có thể vẫn tồn tại trong snapshot ngay cả khi ứng dụng đặt field về null trước khi checkpoint.

Hãy lấy secret từ secret manager hoặc file secret được mount sau restore. Nếu cần credential mới sau một khoảng checkpoint dài, thực hiện refresh/rotation trước khi resource được đưa vào sử dụng.

## 5. Tổ chức file cấu hình

Một cách tổ chức dễ hiểu là tách metadata build khỏi cấu hình deployment:

~~~text
application/
├── app.jar
├── build-info.properties
└── config/
    └── defaults.properties        # Giá trị mặc định không gắn môi trường

Deployment mount:
├── /run/app-config/runtime.properties
└── /run/secrets/
    ├── database-password
    └── partner-api-token
~~~

Ví dụ build metadata:

~~~properties
application.name=orders-service
application.version=2.4.0
application.build=git-8f31c2a
java.release=21
~~~

Ví dụ runtime configuration:

~~~properties
server.port=8080
database.url=jdbc:postgresql://db.internal:5432/orders
database.username=orders_app
database.passwordFile=/run/secrets/database-password
partner.apiUrl=https://partner.internal/api
partner.tokenFile=/run/secrets/partner-api-token
request.timeout=PT3S
feature.newCheckout=true
logging.level=INFO
~~~

File runtime ở trên chỉ minh họa cấu trúc; trong production, nó được mount hoặc cung cấp từ hệ thống cấu hình của deployment. Không commit file chứa endpoint và thông tin nội bộ production vào repository công khai. Các giá trị password/token chỉ là đường dẫn đến secret, không phải secret value.

### 5.1. Đường dẫn mount nên ổn định

Nếu checkpoint dùng chung cần đọc file sau restore, hãy chọn một đường dẫn ổn định trong container, ví dụ:

- /run/app-config/runtime.properties
- /run/secrets/database-password

Mỗi deployment mount nội dung khác nhau vào cùng đường dẫn. Như vậy, application code và checkpoint chỉ cần biết vị trí đọc; dữ liệu cụ thể do môi trường triển khai cung cấp.

Nếu đường dẫn cấu hình cũng khác nhau giữa các môi trường, đường dẫn đó phải được cung cấp bởi một bootstrap mechanism có thể thay đổi sau restore. Đừng đặt một đường dẫn staging vào static field trước checkpoint rồi mong deployment production tự thay thế.

## 6. Nạp runtime configuration sau restore

Một config loader nên thực hiện các việc sau:

1. Đọc file hoặc gọi config service từ môi trường triển khai.
2. Parse các giá trị thành kiểu dữ liệu rõ ràng.
3. Validate các trường bắt buộc và giới hạn giá trị.
4. Lấy secret từ nguồn riêng.
5. Tạo resource phụ thuộc như connection pool, HTTP client và listener.
6. Chỉ đánh dấu ứng dụng READY khi các dependency bắt buộc hoạt động.

Ví dụ kiểu cấu hình:

~~~java
package com.example.app;

import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;

public record RuntimeConfig(
        int httpPort,
        URI databaseUrl,
        String databaseUsername,
        Path databasePasswordFile,
        URI partnerApiUrl,
        Path partnerTokenFile,
        Duration requestTimeout,
        boolean newCheckoutEnabled) {
}
~~~

Loader đọc file runtime:

~~~java
package com.example.app;

import java.io.Reader;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Properties;

public final class RuntimeConfigLoader {

    private RuntimeConfigLoader() {
    }

    public static RuntimeConfig load(Path configFile)
            throws Exception {

        Properties properties = new Properties();

        try (Reader reader = Files.newBufferedReader(
                configFile, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        int port = Integer.parseInt(
                required(properties, "server.port"));

        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException(
                    "server.port must be between 1 and 65535");
        }

        Path passwordFile = Path.of(
                required(properties, "database.passwordFile"));

        Path tokenFile = Path.of(
                required(properties, "partner.tokenFile"));

        Duration timeout = Duration.parse(
                required(properties, "request.timeout"));

        if (timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException(
                    "request.timeout must be positive");
        }

        return new RuntimeConfig(
                port,
                URI.create(required(properties, "database.url")),
                required(properties, "database.username"),
                passwordFile,
                URI.create(required(properties, "partner.apiUrl")),
                tokenFile,
                timeout,
                Boolean.parseBoolean(
                        properties.getProperty(
                                "feature.newCheckout", "false")));
    }

    private static String required(
            Properties properties,
            String key) {

        String value = properties.getProperty(key);

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required configuration: " + key);
        }

        return value.trim();
    }
}
~~~

Loader chỉ đọc đường dẫn secret; nó chưa đọc password hoặc token vào object RuntimeConfig. Thành phần sở hữu connection hoặc API client sẽ đọc secret sau khi bootstrap đã xác định đúng môi trường.

Trong production, cần bổ sung validation theo giao thức cụ thể, kiểm tra URI scheme, kiểm tra quyền đọc file secret và báo lỗi rõ ràng khi file cấu hình thiếu hoặc sai định dạng.

## 7. Coordinator quản lý cấu hình và resource sau restore

Để bảo đảm service không khởi động trước khi cấu hình có sẵn, có thể dùng một coordinator CRaC. Coordinator được đăng ký trước khi checkpoint và chịu trách nhiệm nạp config, khởi tạo dependency theo thứ tự, cũng như dừng chúng trước checkpoint.

Ví dụ contract cho các thành phần:

~~~java
package com.example.app;

public interface RuntimeComponent {

    // Khởi tạo từ cấu hình của deployment hiện tại.
    void start(RuntimeConfig config) throws Exception;

    // Phải an toàn nếu start mới hoàn tất một phần.
    void stop() throws Exception;
}
~~~

Coordinator:

~~~java
package com.example.app;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class RuntimeBootstrap implements Resource {

    public interface Readiness {
        void markReady();
        void markNotReady();
    }

    private enum State {
        INACTIVE,
        ACTIVE,
        FAILED
    }

    private final Path configFile;
    private final List<RuntimeComponent> components;
    private final Readiness readiness;
    private final List<RuntimeComponent> attempted =
            new ArrayList<>();

    private State state = State.INACTIVE;

    public RuntimeBootstrap(
            Path configFile,
            List<RuntimeComponent> components,
            Readiness readiness) {

        this.configFile = configFile;
        this.components = List.copyOf(components);
        this.readiness = readiness;

        // Đăng ký coordinator trước khi khởi tạo resource phụ thuộc.
        Core.getGlobalContext().register(this);
    }

    public synchronized void activate() throws Exception {
        if (state == State.ACTIVE) {
            return;
        }

        if (state == State.FAILED) {
            throw new IllegalStateException(
                    "Runtime bootstrap is in FAILED state");
        }

        readiness.markNotReady();

        RuntimeConfig config =
                RuntimeConfigLoader.load(configFile);

        try {
            for (RuntimeComponent component : components) {
                // Ghi nhận trước để cleanup được partial start.
                attempted.add(component);
                component.start(config);
            }

            state = State.ACTIVE;
            readiness.markReady();

        } catch (Exception startupFailure) {
            Exception cleanupFailure = stopInReverseOrder();

            state = State.FAILED;

            if (cleanupFailure != null) {
                startupFailure.addSuppressed(cleanupFailure);
            }

            throw startupFailure;
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        readiness.markNotReady();

        if (state != State.ACTIVE) {
            return;
        }

        Exception failure = stopInReverseOrder();
        state = failure == null ? State.INACTIVE : State.FAILED;

        if (failure != null) {
            throw failure;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        // Đọc lại cấu hình deployment và tạo resource mới.
        activate();
    }

    private Exception stopInReverseOrder() {
        Exception firstFailure = null;

        for (int index = attempted.size() - 1; index >= 0; index--) {
            try {
                attempted.get(index).stop();
            } catch (Exception failure) {
                if (firstFailure == null) {
                    firstFailure = failure;
                } else {
                    firstFailure.addSuppressed(failure);
                }
            }
        }

        attempted.clear();
        return firstFailure;
    }
}
~~~

Ví dụ tạo bootstrap:

~~~java
Path runtimeConfig = Path.of(
        "/run/app-config/runtime.properties");

List<RuntimeComponent> components = List.of(
        databaseComponent,
        partnerClientComponent,
        applicationServiceComponent,
        httpServerComponent
);

RuntimeBootstrap bootstrap =
        new RuntimeBootstrap(
                runtimeConfig,
                components,
                readiness);

// Chạy khi khởi động bình thường:
if (!checkpointPreparationMode) {
    bootstrap.activate();
}
~~~

Trong checkpoint preparation mode, ứng dụng không gọi activate() trước checkpoint. Coordinator đã đăng ký nhưng vẫn ở trạng thái INACTIVE. Khi checkpoint được restore ở deployment đích, afterRestore() đọc file runtime của deployment đó, validate cấu hình và khởi tạo các thành phần theo thứ tự.

Trong khởi động bình thường, activate() được gọi để ứng dụng hoạt động mà không cần restore. Với checkpoint dùng chung, cờ checkpointPreparationMode là lựa chọn của quy trình build/prepare; nó phải được xác định trước khi bắt đầu warm-up. Cách truyền cờ cụ thể tùy pipeline, nhưng không nên dùng một giá trị deployment riêng được bake vào checkpoint chung.

Đây là skeleton minh họa luồng điều phối. Ứng dụng thực tế cần bổ sung shutdown chủ động, timeout, xử lý trạng thái FAILED, readiness integration và cơ chế đồng bộ với framework. Các RuntimeComponent phải đóng an toàn cả khi start thất bại một phần.

## 8. Thứ tự khởi tạo và callback

Khi coordinator quản lý các component theo thứ tự dependency:

~~~text
RuntimeConfig
     │
     ▼
Database pool
     │
     ▼
Partner API client
     │
     ▼
Application service
     │
     ▼
HTTP server
~~~

Sau restore, config được nạp trước, rồi các component được khởi tạo theo thứ tự danh sách. HTTP server mở sau cùng để request không đi vào khi database hoặc service chưa sẵn sàng.

Nếu từng component cũng tự đăng ký CRaC Resource, cần xác định thứ tự đăng ký một cách tường minh. Trong cùng context, callback beforeCheckpoint chạy theo thứ tự ngược với đăng ký; afterRestore chạy theo thứ tự đăng ký. Không để coordinator và component cùng đóng/mở một resource hai lần.

Với kiến trúc coordinator ở trên, các component con không tự đăng ký callback cho cùng một pool hoặc client. Coordinator là owner của lifecycle và gọi start/stop theo thứ tự dependency.

## 9. Cấu hình trong Spring và dependency injection

Trong Spring Boot hoặc framework DI, cấu hình thường được bind thành bean và được inject vào service. Khi application context được tạo trước checkpoint, nhiều bean có thể giữ giá trị runtime đã đọc ở thời điểm đó.

Ví dụ, một bean giữ JDBC URL:

~~~java
@ConfigurationProperties(prefix = "database")
public record DatabaseProperties(URI url) {
}

@Component
public class DatabaseClient {

    private final URI jdbcUrl;

    public DatabaseClient(DatabaseProperties properties) {
        this.jdbcUrl = properties.url();
    }
}
~~~

Nếu bean này được tạo trước checkpoint trong staging, restore checkpoint đó ở production không làm constructor chạy lại với property production.

Các hướng tổ chức:

- Giữ build metadata và cấu hình bất biến trong bean thông thường.
- Dùng một RuntimeConfigProvider có thể thay đổi cấu hình sau restore.
- Tạo các bean/resource phụ thuộc sau khi RuntimeConfigProvider đã nạp và validate cấu hình.
- Đóng và tạo lại connection pool, HTTP client hoặc consumer có endpoint thay đổi.
- Chỉ công bố readiness sau khi application context hoặc các phần runtime cần thiết đã sẵn sàng.

Nếu toàn bộ Spring context đã được tạo trước checkpoint, cần xác định bean nào có thể giữ lại và bean nào phải refresh/recreate. Chỉ thay đổi Environment hoặc một Properties object không tự thay đổi các field đã được inject vào singleton.

Một số ứng dụng có thể tạo lại một phần context sau restore; ứng dụng khác dùng facade hoặc provider động. Lựa chọn phụ thuộc framework integration và thời gian khởi tạo. Dù chọn cách nào, cần có một lifecycle owner duy nhất cho từng resource.

## 10. Những cấu hình JVM không thể coi là runtime reload thông thường

Một số cấu hình được áp dụng khi JVM khởi động và ảnh hưởng đến runtime process:

- Heap sizing như Xms và Xmx.
- Garbage collector và các JVM flag.
- Classpath/module path.
- Native library path.
- Một số system property được thư viện đọc một lần.
- Agent, instrumentation và runtime option.

Nếu checkpoint được tạo với một cấu hình JVM nhất định, không nên giả định lệnh restore có thể thay đổi tùy ý những thiết lập đã định hình trạng thái tiến trình. Muốn thay đổi heap, GC hoặc cấu hình JVM nền tảng, thường cần tạo checkpoint mới phù hợp hoặc dùng quy trình khởi chạy khác.

Phân biệt JVM option với application runtime configuration. Database URL có thể được nạp lại bởi ứng dụng nếu thiết kế hỗ trợ; kích thước heap của JVM không thể được thay đổi bằng cách reload file properties trong callback.

Cũng cần ghi nhận vendor, version, build number, kiến trúc và các JVM option khi tạo checkpoint. Restore cần chạy trong môi trường tương thích với checkpoint và các giới hạn của CRaC/CRIU.

## 11. Secret và dữ liệu nhạy cảm trong checkpoint

Checkpoint có thể chứa dữ liệu trong heap và trạng thái process. Nếu ứng dụng đã đọc password, API token hoặc private key trước khi tạo checkpoint, giá trị đó có thể còn trong snapshot.

Đặt một field về null trước checkpoint không bảo đảm byte của secret biến mất khỏi mọi page memory. Garbage collection, copy nội bộ, buffer và thư viện native có thể đã tạo thêm bản sao.

Với checkpoint dùng chung:

1. Không nạp secret trước khi tạo checkpoint.
2. Chỉ lưu đường dẫn hoặc tên secret provider ổn định nếu cần.
3. Sau restore, xác thực với secret manager hoặc đọc mounted secret.
4. Không ghi secret vào log, build metadata hoặc image layer.
5. Bảo vệ checkpoint artifact như một dữ liệu nhạy cảm nếu nó có thể chứa state runtime khác.
6. Thiết kế refresh/rotation nếu secret có thể đổi trong thời gian checkpoint.

Docker build argument hoặc biến ENV trong Dockerfile không phải secret store. Build argument có thể xuất hiện trong metadata/layer tùy cách sử dụng; ENV được đóng vào image config. Dùng cơ chế secret của build system cho bước build cần credential, và dùng secret manager hoặc secret mount khi triển khai.

## 12. Thay đổi cấu hình trong thời gian ứng dụng đang chạy

Runtime configuration có thể thay đổi sau restore. Cần xác định chính sách reload:

- **Reload tức thời:** cập nhật provider và resource hỗ trợ đổi cấu hình an toàn.
- **Reload theo phiên bản:** nạp một snapshot config mới, validate, tạo resource mới, chuyển traffic rồi đóng resource cũ.
- **Restart/restore lại:** dùng khi thay đổi không thể áp dụng an toàn trong process hiện tại.

Không nên cập nhật từng field rời rạc trong khi request đang đọc cấu hình. Một cách an toàn là tạo immutable RuntimeConfig mới rồi publish bằng một reference volatile hoặc AtomicReference:

~~~java
private final AtomicReference<RuntimeConfig> current =
        new AtomicReference<>();

public RuntimeConfig current() {
    RuntimeConfig config = current.get();

    if (config == null) {
        throw new IllegalStateException(
                "Runtime configuration is not active");
    }

    return config;
}

public void publish(RuntimeConfig updated) {
    current.set(updated);
}
~~~

Các request đang chạy có thể giữ snapshot config mà chúng đã bắt đầu sử dụng; request mới nhận snapshot mới. Với resource như connection pool, cần quy trình chuyển đổi riêng để không đóng pool cũ trong khi request còn dùng nó.

Sau restore, luôn validate config mới trước khi publish. Nếu cấu hình sai hoặc secret không truy cập được, giữ readiness ở NOT_READY và báo lỗi cụ thể. Không dùng fallback sang endpoint staging hoặc credential cũ một cách âm thầm.

## 13. Warm-up khi chuẩn bị checkpoint dùng chung

Warm-up giúp nạp class và làm nóng code trước khi tạo checkpoint. Tuy nhiên, cần phân biệt warm-up code với khởi tạo dữ liệu riêng của deployment.

Có thể warm-up an toàn bằng:

- Gọi các luồng xử lý đại diện với dữ liệu tổng hợp.
- Nạp class và khởi tạo thư viện không phụ thuộc endpoint môi trường.
- Thực hiện tính toán CPU-bound không cần credential.
- Chuẩn bị cache chỉ chứa metadata bất biến hoặc dữ liệu public.
- Làm nóng code path trước khi resource runtime được tạo.

Cần tránh:

- Kết nối database production/staging và giữ pool trong checkpoint chung.
- Nạp API token, password hoặc private key.
- Cache dữ liệu tenant, user hoặc dữ liệu nhạy cảm.
- Resolve và cache endpoint của môi trường cụ thể.
- Ghi lại kết quả request thử nghiệm có dữ liệu thật.
- Khởi tạo consumer hoặc scheduler gắn với queue/tenant riêng.

Nếu warm-up cần database, hãy dùng database thử nghiệm với dữ liệu giả lập và đóng hoàn toàn resource trước checkpoint; tốt hơn nữa là tách warm-up phần code khỏi warm-up phần tích hợp bên ngoài.

Sau restore, các resource deployment-specific được tạo lại từ runtime config. Nếu cần warm-up connection pool hoặc cache cho môi trường đích, thực hiện sau khi đã nạp đúng config và trước khi đánh dấu READY.

## 14. Quy trình build và deploy có thể tái lập

Một pipeline cho checkpoint dùng chung có thể chia thành các giai đoạn:

~~~text
BUILD
  - Compile source
  - Resolve dependency versions
  - Package application
  - Record build metadata
        │
        ▼
PREPARE CHECKPOINT
  - Start CRaC-enabled JDK
  - Load application classes
  - Warm-up code with synthetic data
  - Keep deployment config/secrets unloaded
  - Register runtime bootstrap coordinator
  - Create checkpoint
        │
        ▼
PACKAGE
  - Store JAR and checkpoint
  - Store JDK/build/architecture metadata
  - Record checksums
        │
        ▼
DEPLOY
  - Mount runtime config at stable path
  - Mount secrets or connect secret provider
  - Provide compatible Linux/CRIU environment
        │
        ▼
RESTORE
  - Restore checkpoint
  - Load and validate deployment config
  - Fetch secrets
  - Create database/client/server resources
  - Run health checks
  - Mark READY
~~~

Nên lưu cùng checkpoint:

- Git commit và build ID.
- Checksum JAR và checkpoint artifact.
- JDK vendor/version/build.
- JVM options quan trọng.
- OS/kernel, kiến trúc CPU và CRIU version.
- Cấu hình build-time không nhạy cảm.
- Version/schema của runtime config mà ứng dụng hỗ trợ.

Không lưu secret value trong manifest build. Deployment cần có cấu hình và secret riêng, có version hoặc revision để việc điều tra restore có thể xác định chính xác cấu hình nào đã được dùng.

### 14.1. Kiểm tra tương thích trước restore

Trước khi restore, xác nhận:

- JDK/CRaC build phù hợp với checkpoint.
- OS, kernel, architecture và CRIU đáp ứng điều kiện.
- Đường dẫn mount cần thiết tồn tại.
- Runtime config có mặt và đúng schema.
- Secret provider có thể truy cập.
- Database và các endpoint cần thiết có network route.
- Port và resource limit phù hợp với deployment.

Nếu thiếu runtime config hoặc secret, bootstrap phải fail trước khi mở traffic. Không dùng cấu hình build-time làm fallback cho endpoint hoặc credential môi trường.

## 15. Kiểm chứng việc tách cấu hình

Có thể kiểm chứng bằng hai deployment giả lập sử dụng cùng checkpoint artifact nhưng cấu hình khác nhau.

### 15.1. Hai bộ runtime config

Staging:

~~~properties
server.port=8080
database.url=jdbc:postgresql://staging-db:5432/orders
database.username=orders_staging
database.passwordFile=/run/secrets/database-password
partner.apiUrl=https://staging-partner.example/api
partner.tokenFile=/run/secrets/partner-api-token
request.timeout=PT3S
feature.newCheckout=false
~~~

Production:

~~~properties
server.port=8080
database.url=jdbc:postgresql://production-db:5432/orders
database.username=orders_app
database.passwordFile=/run/secrets/database-password
partner.apiUrl=https://partner.example/api
partner.tokenFile=/run/secrets/partner-api-token
request.timeout=PT2S
feature.newCheckout=true
~~~

Cả hai deployment mount file của mình vào cùng đường dẫn trong container. Checkpoint chung không chứa các giá trị endpoint hoặc secret của riêng staging/production.

### 15.2. Bằng chứng cần quan sát

Sau restore ở staging:

- RuntimeConfig cho biết database URL staging.
- Connection pool kết nối staging database.
- Partner client sử dụng staging endpoint.
- Feature flag được đọc theo cấu hình staging.
- Readiness chỉ chuyển READY sau health check thành công.

Sau restore ở production:

- RuntimeConfig cho biết database URL production.
- Connection pool kết nối production database.
- Partner client sử dụng production endpoint.
- Feature flag được đọc theo cấu hình production.
- Không có connection hoặc client cũ trỏ về staging.

Log chỉ nên ghi tên môi trường, config revision, endpoint đã được phép công khai và kết quả validation. Không ghi password, token hoặc nội dung secret.

### 15.3. Thử thay đổi cấu hình

Để chứng minh ứng dụng thật sự đọc lại cấu hình sau restore:

1. Tạo checkpoint chung khi runtime config chưa được nạp.
2. Restore với file staging và xác nhận resource dùng endpoint staging.
3. Dừng instance staging theo quy trình.
4. Restore cùng checkpoint artifact với file production.
5. Xác nhận resource dùng endpoint production.
6. Thay đổi config revision hoặc secret trong môi trường thử nghiệm.
7. Restore lại và xác nhận bootstrap nhận revision mới.
8. Kiểm tra log và health endpoint để xác nhận không có resource cũ còn hoạt động.

Không chỉ kiểm tra nội dung file sau restore. Cần xác nhận resource đã được tạo từ cấu hình đó bằng một health check hoặc truy vấn thực tế.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đọc DB URL trước checkpoint chung | Restore production vẫn giữ endpoint staging | Chỉ nạp deployment config sau restore |
| Tin rằng environment variable mới sẽ ghi đè static field | Object đã khôi phục vẫn dùng giá trị cũ | Dùng config loader/provider có thể đọc lại |
| Chỉ sửa Properties nhưng giữ connection pool cũ | Pool tiếp tục kết nối endpoint trước đó | Đóng và tạo lại resource phụ thuộc |
| Đóng gói password vào image | Secret tồn tại trong image layer hoặc checkpoint | Dùng secret manager/mount và nạp sau restore |
| Nạp config file một lần rồi không reload | File thay đổi nhưng bean vẫn giữ giá trị cũ | Reload và publish config snapshot mới |
| Để HTTP server mở trước khi config/dependency sẵn sàng | Request đến trong trạng thái không hoàn chỉnh | Khởi tạo dependency trước, mở listener sau |
| Dùng một checkpoint có JVM option khác yêu cầu | Restore không đáp ứng cấu hình runtime mong muốn | Tạo checkpoint tương thích với JVM option cần thiết |
| Warm-up bằng dữ liệu production | Checkpoint có thể chứa dữ liệu hoặc cache riêng môi trường | Dùng dữ liệu tổng hợp, loại bỏ state không dùng |
| Có hai lifecycle owner cho cùng resource | Đóng/mở lặp hoặc callback sai thứ tự | Chỉ định một coordinator/owner cho từng resource |
| Không ghi config revision | Khó xác định instance đã dùng cấu hình nào | Ghi revision và build metadata không nhạy cảm |

## 17. Nguyên tắc thiết kế cần ghi nhớ

Hãy xem checkpoint là ảnh chụp của một process đã có trạng thái. Mọi cấu hình đã được đọc vào object, static field, singleton hoặc resource trước thời điểm đó đều có thể được khôi phục cùng process. Deployment mới không tự động thay các giá trị này.

Với checkpoint dùng chung, chỉ đưa vào snapshot những trạng thái bất biến và an toàn để tái sử dụng. Giữ runtime configuration và secret ở nguồn bên ngoài, đọc chúng sau restore, validate rồi tạo lại resource phụ thuộc. Với checkpoint riêng cho từng môi trường, ghi nhận rõ môi trường và version cấu hình mà checkpoint gắn với nó.

Một ứng dụng chỉ nên nhận traffic sau khi cấu hình deployment đã được nạp, secret đã được lấy từ nguồn phù hợp, database/client/listener đã được tạo lại và health check cần thiết đã thành công. Khi ranh giới build-time và runtime được xác định rõ, cùng một artifact có thể được triển khai có kiểm soát mà không mang theo endpoint hoặc trạng thái nhạy cảm của môi trường tạo checkpoint.

