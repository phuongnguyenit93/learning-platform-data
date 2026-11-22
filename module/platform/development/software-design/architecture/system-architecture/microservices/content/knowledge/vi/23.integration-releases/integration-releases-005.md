# Quản lý phiên bản thư viện dùng chung và tránh cập nhật bắt buộc đồng loạt

Trong kiến trúc microservices, các nhóm phát triển thường muốn tái sử dụng mã Java cho logging, quan sát hệ thống, xác thực token, giao tiếp HTTP, cấu hình và những phép biến đổi dữ liệu nhỏ. Cách đơn giản nhất là đóng gói chúng thành các thư viện dùng chung rồi đưa vào nhiều dịch vụ. Tuy nhiên, nếu mọi thay đổi trong thư viện đều buộc tất cả dịch vụ nâng cấp, build lại và triển khai cùng ngày, hệ thống dần đánh mất một lợi ích quan trọng của microservices: **có thể phát hành từng dịch vụ một cách độc lập**.

Bài này giải thích cách thiết kế ranh giới thư viện, quản lý phiên bản, cam kết tương thích và quy trình phát hành để Order Service có thể dùng một phiên bản thư viện ổn định trong khi Payment Service thử phiên bản mới hơn. Mục tiêu là tái sử dụng hợp lý mà không tạo một “monolith phân tán” về lịch build và triển khai.

## 1. Kết quả học tập

Sau bài học, người học có thể:

- Phân biệt thư viện dùng chung ở **build time** với giao kèo giao tiếp giữa các service ở **runtime**.
- Nhận diện những thư viện phù hợp để chia sẻ và những mô hình miền nghiệp vụ dễ tạo phụ thuộc chặt.
- Thiết kế chính sách phiên bản dựa trên tương thích nguồn, tương thích nhị phân, hành vi, cấu hình và dữ liệu.
- Hiểu cách sử dụng Semantic Versioning, artifact repository, BOM/platform, version catalog và dependency locking mà không ép tất cả dịch vụ cùng cập nhật.
- Áp dụng **additive change**, adapter và deprecation window để hỗ trợ phiên bản cũ trong giai đoạn chuyển tiếp.
- Lập ma trận tương thích và kiểm thử các phiên bản tiêu thụ thư viện đã được phát hành.
- Tổ chức phát hành, rollout, rollback, xử lý lỗ hổng bảo mật và ngừng hỗ trợ phiên bản cũ theo mức độ rủi ro.

## 2. “Dùng chung” có thể tạo ra phụ thuộc gì?

Giả sử ba dịch vụ sử dụng thư viện observability-kit:

~~~text
                             Artifact Repository
                        com.example:observability-kit
                             /       |       \
                         v1.2.4    v1.4.0   v1.5.1
                           |         |        |
                           v         v        v
                     Order Service Payment  Notification
                         release A  release B  release C
~~~

Mỗi dịch vụ có thể chọn phiên bản thư viện phù hợp với chính nó. Artifact được phát hành bất biến: phiên bản 1.4.0 không thay đổi nội dung sau khi công bố. Mỗi dịch vụ build artifact riêng, đưa dependency vào classpath của ứng dụng hoặc phân phối cùng image/container của mình.

Điều kiện thiết kế này khác với tình huống:

~~~text
shared-library HEAD thay đổi
           |
           v
Bắt Order, Payment, Notification cùng sửa code
           |
           v
Chỉ được merge nếu mọi service build với HEAD mới
           |
           v
Triển khai cả ba cùng một cửa sổ
~~~

Cấu hình kiểu thứ hai biến thay đổi nội bộ của thư viện thành một đợt phối hợp toàn hệ thống. Vấn đề không nằm ở việc tạo package tái sử dụng; nó nằm ở **hợp đồng tương thích, cơ chế chọn phiên bản và chính sách phát hành**.

Một số phụ thuộc cần tách riêng:

| Quan hệ | Ví dụ | Hệ quả khi thay đổi |
|---|---|---|
| Dependency mã nguồn | Service biên dịch với một library API | Có thể gây compile failure |
| Dependency nhị phân | JAR đã biên dịch gọi class/method trong library | Có thể gây NoSuchMethodError, linkage error |
| Dependency hành vi | Service trông đợi retry 2 lần, timeout 500 ms | Có thể thay đổi hiệu ứng runtime dù vẫn biên dịch |
| Dependency cấu hình | Library đổi tên property hoặc biến môi trường | Có thể làm service khởi động lỗi hoặc đổi chính sách |
| Dependency dữ liệu | Library serialization ra event JSON | Có thể phá giao kèo với service khác |
| Dependency hạ tầng/runtime | Library yêu cầu Java/Spring/SDK mới | Có thể buộc nâng stack hoặc thay môi trường chạy |
| Dependency quy trình | Pipeline yêu cầu mọi repo cùng dùng “latest” | Tạo nghĩa vụ nâng cấp đồng loạt dù không có phụ thuộc kỹ thuật bắt buộc |

Mỗi quan hệ cần cách kiểm tra riêng. Việc CI của thư viện xanh không chứng minh tất cả ứng dụng đang dùng nó vẫn giữ đúng hành vi.

## 3. Nguyên tắc chủ đạo: service sở hữu phiên bản của mình

Một service chỉ nên nâng cấp thư viện khi đội sở hữu service đánh giá tác động, chạy test và lên lịch triển khai phù hợp. Thư viện cung cấp **phiên bản đã phát hành và hợp đồng rõ ràng**; không kéo code mới vào runtime của service khi service chưa build lại.

Ví dụ:

| Thời điểm | Order | Payment | Notification |
|---|---|---|---|
| Tuần 1 | logging-kit 1.3.0 | logging-kit 1.3.0 | logging-kit 1.2.8 |
| Tuần 2 | 1.3.0 | 1.4.0 | 1.2.8 |
| Tuần 3 | 1.3.1 | 1.4.0 | 1.4.0 |
| Tuần 4 | 1.4.0 | 1.4.1 | 1.4.0 |

Đây là một lịch nâng cấp minh họa. Các phiên bản khác nhau có thể cùng tồn tại giữa các process/service độc lập. **Không cần ép đồng bộ phiên bản giữa mọi service** chỉ vì tất cả dùng cùng một nhóm utility. Tuy nhiên, trong *một classpath của cùng một service*, các dependency có quan hệ nhị phân và transitive dependency vẫn phải được giải quyết thành tổ hợp tương thích.

Hai nguyên tắc bổ sung:

1. **Không sửa artifact đã phát hành.** Artifact phiên bản X phải có nội dung nhất quán; muốn đổi nội dung thì phát hành phiên bản mới. Ghi đè JAR cùng version phá tính tái lập của build và làm điều tra sự cố khó khăn.
2. **Không mặc định dùng latest.** Build của Order cần giải quyết ra dependency version được kiểm soát và xác minh, không tự nâng chỉ vì artifact repository vừa có bản mới.

## 4. Những gì nên và không nên chia sẻ?

Thư viện dùng chung có lợi khi nó mô tả năng lực kỹ thuật ổn định, ít tri thức về vòng đời nghiệp vụ của một service cụ thể.

| Loại | Thường phù hợp? | Lưu ý |
|---|---|---|
| Logging và correlation ID | Có | Không buộc toàn bộ service dùng cùng backend hoặc schema log ngoài ý muốn |
| Metrics/tracing adapter | Có | Cho phép service tự cấu hình và giữ tính tương thích |
| Retry/backoff utility | Có điều kiện | Tránh đặt retry tự động cho mọi operation có side effect |
| Authentication/token verification primitives | Có | Tách việc xác minh kỹ thuật khỏi policy phân quyền riêng từng service |
| Error/HTTP client tiện ích nhỏ | Có điều kiện | Tránh ghép cố định URL, schema và quy trình nghiệp vụ vào client |
| Common DTO của một API công khai | Có điều kiện | DTO là hợp đồng versioned; client cũ và mới phải cùng hoạt động trong cửa sổ chuyển tiếp |
| Entity/JPA model dùng chung giữa nhiều database | Thường không nên | Làm các service phụ thuộc vào schema nội bộ nhau |
| Business rules của Order và Payment nhét trong common-core | Thường không nên | Các service phải đồng bộ phát hành khi thay đổi logic miền |
| “Mega starter” tự cấu hình mọi service | Rủi ro cao | Một cập nhật nhỏ có thể thay bean graph, security và dependency của tất cả service |
| Shared secret/config chứa giá trị production | Không | Dùng secret manager và cấu hình runtime có quyền tách biệt |

Ví dụ, một hàm chuẩn hóa trace context nên nằm trong observability library. Nhưng “đơn hàng được phép hoàn tiền khi trạng thái Payment thế nào” thuộc owner của domain tương ứng; chia sẻ class Java cho rule đó không biến nó thành giao kèo phân tán an toàn.

### Khi cần chia sẻ contract

Nếu Payment phát sự kiện PaymentAuthorized, có thể công bố **schema/contract** ổn định và versioned hoặc dùng contract registry. Điều này khác với việc mọi service cùng tham chiếu entity Hibernate của Payment. Producer giữ quyền thay đổi nội bộ, consumer chỉ phụ thuộc vào giao kèo công khai.

Một lớp DTO Java dùng chung đôi khi phù hợp trong môi trường Java đồng nhất, nhưng không được trở thành bằng chứng rằng hai service đã có tương thích runtime: producer và consumer triển khai các phiên bản khác nhau, message đã nằm trong broker từ trước, và consumer ngoài Java có thể tồn tại.

## 5. Phiên bản theo Semantic Versioning: hữu ích nhưng chưa đủ

Semantic Versioning (SemVer) biểu diễn phiên bản theo mẫu MAJOR.MINOR.PATCH, chẳng hạn 2.5.3, với cam kết thông thường:

- **PATCH:** sửa lỗi không cố ý phá hợp đồng công khai đã tuyên bố.
- **MINOR:** thêm tính năng tương thích ngược với API đã công bố.
- **MAJOR:** cho phép thay đổi phá vỡ API hoặc hành vi không còn tương thích.

Các cam kết này chỉ có ý nghĩa khi library định nghĩa được **public API** và mức độ ổn định của nó. Một package public trong Java chưa chắc được tổ chức xem là “API hỗ trợ”. Nên có tài liệu về exported packages, extension points, cấu hình công khai, wire-format và thời gian hỗ trợ.

Một thay đổi tăng patch vẫn có thể làm lỗi service nếu nó đổi retry policy, serialization, bean auto-configuration hoặc version của dependency quan trọng. Version number là **tín hiệu**, không thay thế kiểm thử.

### 5.1. Ví dụ phân loại thay đổi

| Thay đổi | Tương thích cần xét | Hướng xử lý |
|---|---|---|
| Thêm helper method mới, không sửa method cũ | Nguồn/nhị phân của consumer cũ thường giữ được | Thường có thể là MINOR |
| Sửa bug mà output được chuẩn hóa lại | Hành vi của consumer cũ có thể bị ảnh hưởng | Test regression; PATCH hay MAJOR tùy hợp đồng |
| Đổi tên method public và xóa method cũ | Source và binary breaking | MAJOR hoặc giai đoạn deprecate |
| Đổi return type/signature | Có thể gây compile/linkage error | MAJOR hoặc cung cấp adapter |
| Thêm tham số bắt buộc vào constructor công khai | Consumer cũ không build/link | Giữ overload cũ hoặc MAJOR |
| Bổ sung property tùy chọn với default cũ | Có thể additive | MINOR nếu tương thích đã được test |
| Đổi default timeout từ 5s xuống 1s | Hành vi runtime có thể phá luồng cũ | Đặt opt-in/config hoặc phiên bản breaking |
| Đổi format timestamp hoặc enum khi serialize | Wire compatibility, persistence | Đổi schema cẩn thận; nhiều khi cần major/contract version |
| Nâng yêu cầu Java runtime 17 lên 21 | Runtime/platform breaking | Thông báo rõ baseline và kế hoạch chuyển |
| Ép nâng Spring Boot major qua auto-configuration | Runtime và dependency graph | Cân nhắc artifact riêng, nhánh hỗ trợ hoặc major |

Một minor release chỉ nên được quảng bá “compatible” nếu các public surface quan trọng đều có kiểm tra tương ứng.

### 5.2. Không nhầm “release major” với “mọi service phải nâng”

Library v3 có thể phá API cũ, nhưng điều đó **không buộc** Order đang dùng v2 phải nâng ngay nếu v2 vẫn nằm trong artifact repository, còn hỗ trợ theo chính sách và không có sự cố nghiêm trọng bắt buộc xử lý. Dịch vụ mới có thể dùng v3; dịch vụ cũ lên kế hoạch chuyển từ v2 sang v3 theo nhịp riêng.

Chính sách hỗ trợ có thể đặt thời hạn chấm dứt cho v2, nhưng đây phải là quyết định sản phẩm và vận hành có thông báo sớm, không phải kết quả ngẫu nhiên của việc xóa phiên bản cũ khi phát hành v3.

## 6. Tương thích gồm nhiều tầng

### 6.1. Source compatibility

Mã consumer đã viết có còn biên dịch khi thay phiên bản library hay không? Ví dụ:

~~~java
// Public API v1
public interface EventIdGenerator {
    String nextId();
}
~~~

Nếu v2 xóa nextId và chỉ giữ generate, consumer cũ dùng nextId sẽ không compile. Nếu muốn mở đường nâng cấp, có thể tạm giữ method cũ và thêm method mới, ghi deprecation với lộ trình cụ thể.

### 6.2. Binary compatibility

JAR consumer đã được compile trước đó có còn chạy với JAR library mới không? Đổi tên method, đổi constructor descriptor, đổi class thành interface hoặc đổi static/instance có thể khiến JVM ném NoSuchMethodError, NoClassDefFoundError hay IncompatibleClassChangeError dù build của library riêng lẻ vẫn xanh.

Cần có kiểm tra API nhị phân hoặc chạy consumer mẫu đã compile với artifact phiên bản trước. Chỉ test việc compile source với library mới không đủ để chứng minh tương thích nhị phân.

### 6.3. Behavioral compatibility

Một SDK HTTP vẫn có method sendRequest như cũ nhưng bắt đầu retry POST tự động từ ba lần thay vì một lần. Consumer có thể phát sinh thanh toán trùng hoặc áp lực tải mới. Về API nguồn/nhị phân, đây có thể là thay đổi tương thích; về nghiệp vụ thì không.

Với behavioral contract, nên ghi rõ timeout mặc định, retry, exception type, HTTP status mapping, cache TTL, thứ tự callback và các trường hợp side effect. Khi cần thay hành vi mặc định, ưu tiên cơ chế opt-in trước và deprecate cài đặt cũ theo lộ trình.

### 6.4. Configuration compatibility

Ví dụ config library v1:

~~~yaml
resilience:
  client:
    connect-timeout-ms: 500
    max-attempts: 2
~~~

Nếu v2 đổi tên max-attempts thành retry-count nhưng silently bỏ qua cấu hình cũ, số lần gọi có thể thay đổi. Một đường di trú an toàn hơn là hỗ trợ alias trong cửa sổ chuyển tiếp, log cảnh báo ở mức metadata, và định nghĩa thứ tự ưu tiên nếu cả hai key xuất hiện.

### 6.5. Serialization và wire compatibility

Schema JSON, Protobuf, Avro hoặc XML có hợp đồng riêng. Thêm field tùy chọn có default thường dễ tương thích hơn đổi nghĩa một field hoặc tái sử dụng field number cũ. Enum value mới có thể khiến consumer với switch exhaustive ném lỗi; thay đổi nullability có thể phá parser.

Đặc biệt, **version thư viện không đồng nhất với version API/message**. Một service sử dụng event-schema library v2 vẫn có thể phát ra payload tương thích với consumer đang chạy schema v1. Điều này cần được chứng minh qua test đọc/ghi ở cả hai chiều phù hợp.

### 6.6. Runtime/platform compatibility

Một library có thể yêu cầu JDK mới, Spring Boot major mới, Jakarta namespace hoặc thay đổi Micrometer/OTel API. Dù source API của library giữ nguyên, service cũ vẫn không nâng được nếu runtime chưa đáp ứng. Khi đó nên công bố compatibility matrix hoặc tách adapter theo platform version, tránh ép mọi service nâng toàn bộ stack chỉ để nhận một helper nhỏ.

## 7. Thiết kế API để phát hành độc lập

Một số mẫu cụ thể giúp giảm khả năng breaking:

**Giữ interface nhỏ và ổn định.** Public API chỉ chứa thao tác được hỗ trợ; ẩn implementation và internal classes. Tránh expose class từ framework/SDK nếu không cần, vì sẽ kéo version dependency bên ngoài vào public signature.

**Thêm trước, bỏ sau.** Khi cần đổi tên API, công bố method mới, giữ overload/method cũ trong giai đoạn chuyển tiếp; chỉ loại bỏ ở major release có thông báo.

**Cho phép cấu hình opt-in.** Hành vi retry/decode mới có thể được bật trong Payment trước khi trở thành mặc định của thư viện. Đặt hành vi rõ qua API để tránh hidden global configuration.

**Giữ semantic contract.** Một method có tên verifySignature cần giữ nghĩa xác minh chữ ký. Đừng lồng thêm kiểm tra policy nghiệp vụ của Order và Payment vào cùng method khiến hai service phải đổi phiên bản cùng lúc.

**Tách core khỏi adapter.** Phần lõi độc lập framework có thể phát hành theo nhịp riêng, còn adapter cho Spring Boot/Kafka/HTTP client có tọa độ artifact và compatibility riêng.

Ví dụ cấu trúc:

~~~text
company-observability-api
company-observability-core
company-observability-spring-boot-3-starter
company-observability-otel-adapter
~~~

Đây là ví dụ tổ chức module, không phải yêu cầu tách mọi thư viện thành bốn JAR. Chỉ nên tách khi giúp giảm dependency và cam kết tương thích thực sự rõ ràng.

## 8. Ví dụ tránh thay đổi bắt buộc với API có phiên bản

Một nhóm xây thư viện validation cho Order và Payment. Phiên bản 1 có method:

~~~java
public final class RequestValidator {
    public ValidationResult validate(String requestId) {
        // implementation
        return ValidationResult.valid();
    }
}
~~~

Nhóm muốn thêm correlation context, nhưng xóa method cũ và đổi chữ ký sẽ buộc tất cả service sửa source khi nâng:

~~~java
// Thay thế hoàn toàn: thay đổi phá tương thích nguồn.
public ValidationResult validate(String requestId, TraceContext trace) {
    // implementation
    return ValidationResult.valid();
}
~~~

Một đường tương thích hơn khi hợp đồng cho phép:

~~~java
public final class RequestValidator {
    // Giữ API cũ để các consumer hiện hữu tiếp tục sử dụng.
    public ValidationResult validate(String requestId) {
        return validate(requestId, TraceContext.empty());
    }

    // API mới, consumer có thể chuyển từng service.
    public ValidationResult validate(String requestId, TraceContext trace) {
        // Validation thực tế được thực hiện ở đây.
        return ValidationResult.valid();
    }
}
~~~

ValidationResult và TraceContext trong ví dụ là kiểu minh họa. Method mới không được âm thầm thay nghĩa validation của method cũ. Nếu việc thiếu trace context làm thay đổi yêu cầu bảo mật, phải thiết kế quá trình chuyển rõ ràng, không dùng default giả tạo làm vô hiệu kiểm tra an toàn.

Lộ trình:

1. Phát hành minor version thêm overload mới, giữ overload cũ và test hành vi cũ.
2. Order nâng library mà chưa thay code.
3. Payment tự chọn dùng API mới và phát hành độc lập.
4. Khi các consumer đã có kế hoạch chuyển, cảnh báo deprecation với hướng dẫn và thời hạn hỗ trợ.
5. Major version tiếp theo có thể xóa overload cũ; các service chưa sẵn sàng tiếp tục dùng nhánh library cũ trong cửa sổ hỗ trợ.

## 9. Quản lý dependency trong Gradle mà không ép đồng bộ

Với Gradle Groovy DSL, mỗi service có thể khai báo tọa độ và phiên bản artifact cụ thể:

~~~groovy
// order-service/build.gradle
dependencies {
    implementation 'com.example.platform:observability-core:1.4.2'
}
~~~

~~~groovy
// payment-service/build.gradle
dependencies {
    implementation 'com.example.platform:observability-core:1.6.0'
}
~~~

Hai service có classpath và image riêng; không tồn tại yêu cầu mọi service dùng cùng bản chỉ vì tọa độ artifact giống nhau.

Một tổ chức có thể dùng **version catalog** để đặt tên dependency nhất quán trong một repository:

~~~toml
# gradle/libs.versions.toml, ví dụ dành cho một repository.
[versions]
observability = "1.4.2"

[libraries]
observability-core = { module = "com.example.platform:observability-core", version.ref = "observability" }
~~~

~~~groovy
dependencies {
    implementation libs.observability.core
}
~~~

Catalog giúp quản lý phiên bản tập trung **trong phạm vi build đó**; nó không tự yêu cầu các repo khác dùng đúng một version. Nếu tổ chức cung cấp một catalog cho nhiều repo, nên version và phát hành catalog như một artifact/quy ước có lựa chọn nâng cấp, tránh biến thay đổi catalog thành bắt buộc merge đồng thời.

### 9.1. BOM hoặc Gradle platform giải quyết bài toán gì?

Khi một service dùng nhiều artifact thuộc cùng một SDK, BOM/platform giúp **đồng bộ phiên bản có quan hệ nhị phân trong build của service**:

~~~groovy
dependencies {
    implementation platform('com.example.platform:platform-bom:3.2.0')
    implementation 'com.example.platform:observability-core'
    implementation 'com.example.platform:observability-http'
}
~~~

BOM không phải nghĩa vụ để mọi service trong công ty nâng cùng ngày. Order có thể chọn BOM 3.2.0, Payment chọn BOM 3.3.0, miễn mỗi build giải quyết ra dependency graph hợp lệ và runtime tương thích.

Chú ý: BOM có các dạng ràng buộc phiên bản; cách giải quyết xung đột của Gradle còn phụ thuộc constraints, dependency declarations và plugins. Muốn khống chế chính xác tập phiên bản đã kiểm chứng, cần phân tích resolved dependency graph và dùng constraints/locking theo yêu cầu, không giả định BOM luôn “ghim cứng” mọi version.

### 9.2. Không dùng dynamic version bừa bãi

Ví dụ cần cân nhắc tránh trong pipeline phát hành:

~~~groovy
dependencies {
    implementation 'com.example.platform:observability-core:1.+'
}
~~~

Một build lại cùng commit ở ngày khác có thể lấy bản 1.x khác nếu không có locking hoặc cơ chế pin. Mục tiêu phát hành độc lập là **consumer chủ động chọn thời điểm nâng**, nên ưu tiên version cụ thể và dependency resolution có thể tái lập.

Cũng tránh dùng snapshot không ổn định làm baseline production nếu cần rollback và truy vết chính xác. Artifacts phát hành nên là bất biến, có checksum/provenance và được lưu trong repository có quyền truy cập phù hợp.

### 9.3. Dependency locking và verification

Lockfile giúp ghi lại version transitive dependency đã resolve trong từng build. Dependency verification kiểm tra tính toàn vẹn artifact theo metadata/chữ ký/checksum khi triển khai đúng. Hai cơ chế giúp build có thể kiểm tra và tái lập, nhưng không thay thế việc test compatibility hay cập nhật bản vá bảo mật.

Thư viện cũng cần công bố dependency constraints hoặc metadata phù hợp, tránh truyền transitive dependencies không cần thiết vào consumer. Trong Gradle, sự khác biệt giữa API và implementation dependency có ý nghĩa quan trọng với Java Library plugin: API lộ ra compile classpath của consumer, trong khi implementation nên được giữ nội bộ khi có thể.

## 10. Sự khác biệt giữa đồng bộ trong một service và đồng bộ toàn hệ thống

Hãy phân biệt hai yêu cầu:

**Trong một service:** `observability-core` và `observability-http` có thể đòi các API tương thích trong cùng classpath. Nếu adapter mới gọi method chưa có trong core cũ, build của service cần giải quyết ra tổ hợp hợp lệ. BOM và integration tests giúp ngăn lỗi này.

**Giữa hai service:** Order và Payment là các process khác nhau. Chúng không liên kết trực tiếp classpath với nhau. Một bên dùng core 1.4 và bên kia dùng core 1.6 thường hoàn toàn hợp lệ nếu giao tiếp qua API/event contract vẫn tương thích.

Một ngoại lệ cần lưu ý là các thành phần chia sẻ **một runtime chung**, plugin loaded vào cùng JVM hoặc shared container classloader. Khi cùng classloader, các JAR version khác nhau có thể xung đột. Điều đó cho thấy cần thiết kế ranh giới tải lớp thích hợp; không phải lý do để áp một version toàn công ty cho mọi microservice độc lập.

## 11. Client SDK: tiện cho consumer nhưng dễ tạo coupling

Một thư viện client cho Payment API có thể giúp caller xử lý authentication, serialization và retry. Tuy nhiên nếu SDK chứa cả model nội bộ, quy tắc nghiệp vụ riêng của Payment và các phiên bản framework lớn, mọi thay đổi phía Payment có thể ép caller nâng.

Thiết kế client SDK nên ưu tiên:

- Hợp đồng endpoint và schema công khai, versioned.
- Retry policy có thể điều chỉnh và không tự retry thao tác có side effect khi chưa bảo vệ idempotency.
- Các cấu hình timeout, authentication, tracing rõ ràng.
- Khả năng nói chuyện với **nhiều phiên bản server đang hỗ trợ** trong cửa sổ chuyển tiếp.
- Test tương thích với server thật/sandbox hoặc stub sinh từ contract chính thức.
- Không phụ thuộc trực tiếp entity/database model của service cung cấp API.

Ví dụ ma trận:

| Client SDK | Payment API 1.x | Payment API 2.x |
|---|---|---|
| SDK 1.4 | Được hỗ trợ | Chỉ khi API 2 có đường tương thích đã kiểm thử |
| SDK 1.5 | Được hỗ trợ | Có thể hỗ trợ cả hai khi test chứng minh |
| SDK 2.0 | Có thể không hỗ trợ | Được hỗ trợ theo hợp đồng |

Bảng trên chỉ minh họa các khả năng; danh sách hỗ trợ thật phải được công bố dựa trên test. **Không suy ra** SDK 2 chỉ nói chuyện được với API 2 hoặc ngược lại chỉ dựa vào số major giống nhau. Version của JAR và version của giao kèo mạng là hai quyết định tách biệt.

## 12. Triển khai độc lập: dùng expand-and-contract

Khi thay đổi API hoặc schema dữ liệu mà nhiều service sử dụng, một cách chuyển đổi an toàn là **expand-and-contract**:

~~~text
Giai đoạn A — Expand:
Producer hỗ trợ định dạng/hành vi cũ và mới.
Consumer cũ vẫn hoạt động.

Giai đoạn B — Migrate:
Consumer chuyển dần sang hợp đồng mới.
Có thể rollback từng consumer nếu tương thích còn giữ.

Giai đoạn C — Contract:
Sau khi chứng minh không còn consumer cũ trong phạm vi hỗ trợ,
producer mới loại bỏ hợp đồng cũ.
~~~

Ví dụ Notification muốn thêm trường `locale` vào event `UserRegistered`:

**Trước thay đổi:**

~~~json
{
  "eventId": "evt-42",
  "userId": "usr-1",
  "email": "example@example.test"
}
~~~

**Sau thay đổi additive:**

~~~json
{
  "eventId": "evt-42",
  "userId": "usr-1",
  "email": "example@example.test",
  "locale": "vi-VN"
}
~~~

Producer/consumer cần có quy tắc rõ về trường không biết, field optional và default. Nếu consumer cũ được thiết kế chấp nhận unknown fields, nó có thể tiếp tục hoạt động. Nhưng một deserializer cấu hình fail-on-unknown-properties có thể gãy; do đó phải test chứ không suy diễn “JSON thêm field chắc chắn tương thích”.

Quy trình cho phép Notification deploy trước hoặc sau các service khác trong phạm vi tương thích đã chứng minh, thay vì buộc toàn bộ hệ thống cắt phiên bản cùng lúc.

### Khi cần thay tên hoặc kiểu field

Thay `userId` bằng `accountId` và xóa ngay field cũ là breaking. Một hướng chuyển tiếp:

1. Trong một giai đoạn, producer phát cả hai field theo hợp đồng rõ ràng, tránh hai field có giá trị mâu thuẫn.
2. Consumer được cập nhật từng cái để đọc field mới, chấp nhận field cũ nếu còn nằm trong cửa sổ hỗ trợ.
3. Đo việc sử dụng contract cũ và kiểm tra dữ liệu nằm trong broker/DB vẫn cần được giải mã.
4. Chỉ bỏ field cũ khi không còn consumer/dữ liệu lịch sử cần thiết hoặc đã có migration thích hợp.

Các quy tắc phiên bản của Protobuf/Avro khác JSON; ví dụ field number và schema registry compatibility mode phải được tôn trọng theo công nghệ đang dùng.

## 13. Chiến lược hỗ trợ nhiều phiên bản trong thời gian chuyển tiếp

Một tổ chức có thể chọn chính sách phát hành như:

| Nhánh | Mục đích | Chính sách |
|---|---|---|
| 1.x | Service chưa nâng stack | Sửa lỗi/bảo mật trong thời hạn hỗ trợ được công bố |
| 2.x | API hiện hành | Feature mới, patch, compatibility test |
| 3.x prerelease | Thử major change | Canary/consumer thử nghiệm, chưa coi là stable |
| Nhánh legacy đã hết hỗ trợ | Chỉ còn để tái tạo build lịch sử | Không hứa có security patch; có lộ trình thay thế |

Đây là ví dụ, không phải quy định cố định phải giữ đúng ba nhánh. Quan trọng là mỗi nhánh có **owner, support window, điều kiện chấm dứt, yêu cầu kiểm thử và hướng dẫn nâng cấp**.

Nếu cần sửa lỗ hổng nghiêm trọng ở 1.x trong khi 2.x vẫn đang dùng, có thể backport patch phù hợp sang nhánh 1.x. Tránh lấy một thay đổi major trên 2.x rồi ép consumer 1.x nâng toàn stack ngay chỉ để nhận một fix nhỏ, nếu bản vá tương thích ngược có thể thực hiện an toàn. Với lỗ hổng không thể backport, có thể phải nâng cấp khẩn; trường hợp đó cần được nêu là ngoại lệ có đánh giá rủi ro chứ không coi bắt buộc đồng loạt là thiết kế thường ngày.

### Deprecation không đồng nghĩa xóa ngay

Một API được đánh dấu deprecated vẫn cần thời hạn hỗ trợ theo chính sách. Cần công bố:

- API nào bị deprecate và từ phiên bản nào.
- Thay thế bằng API nào; có ví dụ migrate hay adapter không.
- Thời điểm sớm nhất có thể loại bỏ.
- Cách consumer biết mình còn dùng API cũ.
- Ngưỡng áp dụng khẩn khi xuất hiện nguy cơ bảo mật.

Việc đánh dấu `@Deprecated` trong Java giúp compiler/IDE cảnh báo, nhưng không thay thế tài liệu migration hoặc khả năng thấy các consumer chạy ngoài repository của thư viện.

## 14. Kiểm thử tương thích phải chạy trước khi phát hành

Một library release đáng tin cần có cả test của chính thư viện lẫn các dạng kiểm tra về consumer.

| Kiểm thử | Bằng chứng muốn có | Có thể phát hiện |
|---|---|---|
| Unit test library | Hàm/hợp đồng của version mới hoạt động | Regression logic |
| Public API/source compatibility check | Consumer sample cũ vẫn compile khi thay library | Thay signature, xóa class/method |
| Binary compatibility check | Consumer đã compile trước đó vẫn link/chạy | JVM linkage break |
| Behavioral contract tests | Default, lỗi, timeout, retry, serialization giữ hợp đồng | Thay đổi hành vi âm thầm |
| Consumer integration tests | Service tiêu thụ dùng version mới qua đường nghiệp vụ | Break trong cấu hình, bean, dependency |
| Provider/consumer contract tests | API/event giữa các service còn tương thích | Wire-format/semantic break |
| Dependency/runtime matrix | Các tổ hợp JDK, Spring, transitive SDK được hỗ trợ | Runtime platform conflict |
| Security/license checks | Artifact và dependency đủ điều kiện phát hành | Thư viện lỗ hổng, chính sách license |
| Rollback smoke test | Service trở lại artifact cũ trong cửa sổ cho phép | Migration không tương thích hoặc config one-way |

**Đọc API diff** giúp xác định breaking changes sớm. Với Java, có thể dùng công cụ so sánh public/binary API hoặc compile/run test consumer mẫu với nhiều phiên bản artifact. Một library dùng Spring auto-configuration còn cần thử khởi động context và xác nhận điều kiện tạo bean.

### Consumer-driven compatibility

Đội sở hữu thư viện không cần copy mọi service vào mono-repo rồi bắt build tất cả trên mỗi commit. Có thể sử dụng contract tests, bộ consumer fixture đại diện, test matrix, hoặc pipeline thử upgrade theo lịch ở từng service. Quan trọng là kết quả kiểm thử được ghi theo cặp **library version + consumer baseline**.

Nếu không có đủ bằng chứng về một consumer chưa được thử, báo phạm vi kiểm chứng cụ thể. Không ghi “compatible với mọi service” dựa trên việc unit test library chạy xanh.

### Ma trận minh họa

| Consumer | Phiên bản hiện tại | Phiên bản muốn nâng | Kết quả kiểm tra cần có |
|---|---|---|---|
| Order | 1.4.2 | 1.5.0 | Build, smoke test, observability contract |
| Payment | 1.3.7 | 1.5.0 | Retry/idempotency test, payment sandbox |
| Notification | 1.2.9 | 1.4.2 | Email flow test, provider adapter |
| Billing Batch | 1.3.7 | 1.5.0 | Job startup, cron window, transaction test |

Lịch nâng cấp khác nhau là bình thường; từng consumer có thể ở phiên bản riêng khi đáp ứng chính sách và vẫn hoạt động tốt.

## 15. Quy trình phát hành artifact độc lập

Một pipeline minh họa:

~~~text
Pull request thay đổi library
    |
    v
Unit + API/behavior compatibility checks
    |
    v
Build artifact + kiểm tra dependency
    |
    v
Publish immutable version vào artifact repository
    |
    v
Release notes + migration guide + compatibility matrix
    |
    v
Consumer chọn lúc nâng (PR riêng, CI riêng)
    |
    v
Canary / deploy từng service / quan sát
~~~

Quy trình này không đòi cùng một commit chứa thay đổi cho tất cả service. Ngay cả khi nhiều service nằm trong cùng một monorepo, pipeline vẫn có thể phát hành từng module với version/điều kiện thích hợp.

### 15.1. Release notes nên nêu gì?

Ví dụ cho library `observability-core 1.5.0`:

- Thêm API tạo span context mới; method cũ vẫn hỗ trợ.
- Không đổi định dạng trace ID đang phát ra.
- Giữ defaults về timeout và exporter.
- Yêu cầu tối thiểu Java version đã công bố.
- Các tổ hợp Spring Boot/OTel adapter đã được test.
- Khuyến nghị nâng cấp, thay đổi cấu hình cần xem xét và hướng rollback.
- Các issue đã sửa, dependency đã cập nhật, nguy cơ còn biết.

Release notes chỉ nêu “refactor internal classes” có thể không đủ nếu internal refactor vô tình thay exception hoặc metric name mà consumer dựa vào.

### 15.2. Pin version và lưu artifact

Trong production, pipeline cần record:

- Library version chính xác và dependency lock/resolved dependency graph.
- Artifact checksum/provenance/SBOM theo cơ chế tổ chức sử dụng.
- Commit nguồn, toolchain và build metadata liên quan.
- Service/image version đã nhúng library đó.
- Cấu hình feature flags/defaults ảnh hưởng hành vi.

Khi lỗi xảy ra, nhóm vận hành có thể truy ngược service image đang chạy tới thư viện thật sự được đóng gói, không phải chỉ phiên bản hiện đang “mới nhất” trong repository.

## 16. Cập nhật bảo mật: độc lập nhưng có thời hạn

Phát hành độc lập không có nghĩa service có thể giữ phiên bản có lỗ hổng vô hạn. Cần cân bằng autonomy với security policy.

Ví dụ một bản vá cho authentication helper:

1. Owner library đánh giá mức độ ảnh hưởng và xác định các nhánh đang được hỗ trợ.
2. Phát hành patch tương thích ngược nếu khả thi, hoặc công bố major migration bắt buộc nếu không còn hướng an toàn.
3. Tạo inventory các service thật sự phụ thuộc vào artifact/phiên bản bị ảnh hưởng.
4. Gán mức ưu tiên và deadline cập nhật theo rủi ro, môi trường và mức lộ diện.
5. Mỗi service chạy test riêng và deploy có quan sát; với sự cố khẩn có thể áp quy trình triển khai nhanh.
6. Kiểm tra môi trường đang chạy, không chỉ repository đã cập nhật phiên bản trên file build.

**Phối hợp deadline** để xử lý rủi ro bảo mật khác với **khóa chu kỳ release** của mọi dịch vụ trong hoạt động bình thường. Các nhóm có thể cùng chịu yêu cầu khắc phục nhưng vẫn xây dựng và triển khai từng dịch vụ độc lập.

Đặc biệt, nếu thư viện có khóa xác thực, crypto, deserialization hoặc dependency dễ bị khai thác, cần cân nhắc giới hạn support window và khả năng backport thực tế. Không giữ nhánh legacy với rủi ro nghiêm trọng chỉ để bảo đảm “không ai phải nâng”.

## 17. Các mô hình kiến trúc gây cập nhật bắt buộc

### 17.1. Shared domain model “mọi thứ”

~~~text
common-domain
  OrderEntity
  PaymentEntity
  InventoryEntity
  DatabaseMigration
  RepositoryBase
  BusinessStatus
  AuthorizationRule
~~~

Nếu Order thêm trạng thái mới vào enum chung, Payment và Inventory có thể bị yêu cầu đổi source/build dù không sử dụng nó. Nếu cả ba dùng entity chung, các service vô tình phụ thuộc schema nội bộ của nhau và thường phải phối hợp migration.

Hướng xử lý: mỗi bounded context sở hữu domain model và storage. Chỉ chia sẻ contract thực sự được công khai, ideally schema có version và backward compatibility; utility kỹ thuật được giữ độc lập với domain behavior.

### 17.2. Một starter khởi động quá nhiều chức năng

Thư viện `company-spring-starter` có thể tự bật security filter, HTTP retry, database config và tracing khi thêm một dependency. Một update về tracing vô tình đổi authentication hoặc transaction behavior của Payment.

Hướng xử lý: module nhỏ hơn, auto-configuration theo điều kiện rõ ràng, opt-in cho hành vi nguy hiểm, starter có compatibility matrix và test startup của consumer.

### 17.3. Cập nhật version bằng một file dùng chung ép tất cả build

Trong mono-repo, phiên bản thư viện được đặt tại root và mọi service bắt buộc dùng `project(":common")` HEAD cùng lần build. Điều này thích hợp với một số trường hợp một release unit duy nhất, nhưng không phù hợp nếu mục tiêu là deploy microservices độc lập.

Nếu cùng repo vẫn cần độc lập, có thể xuất bản common artifact versioned rồi để từng service tham chiếu version của mình; hoặc tối thiểu tách quy tắc build/release và duy trì compatibility window. Cách cụ thể phụ thuộc build structure.

### 17.4. Shared database migration trong library

Thư viện tự chạy migration trên DB chung khi bất cứ service nào khởi động sẽ làm các service liên quan vào một lịch triển khai ngầm. Nên để owner của database/schema kiểm soát migration; dùng expand-contract cho thay đổi dữ liệu. Thư viện chỉ hỗ trợ client logic trong phạm vi hợp đồng được công bố.

### 17.5. Tự cập nhật dependency ngay khi khởi động

Nếu application runtime tải code/plugin “latest” từ nơi tập trung, một thay đổi thư viện có thể tác động đồng thời lên nhiều service mà không đi qua build/deploy riêng. Trừ kiến trúc plugin runtime có quản trị tương thích riêng, nên tránh kiểu này với core service library.

## 18. Chiến lược nâng cấp theo từng dịch vụ

Giả sử Payment muốn chuyển từ library v1 sang v2, còn Order và Notification chưa sẵn sàng.

**Bước 1: Chốt phạm vi.** Xác định class/method công khai Payment đang dùng, transitive dependencies, defaults, runtime compatibility và external contracts liên quan.

**Bước 2: Chuẩn bị phiên bản mới.** Library owner phát hành v2 với tài liệu migration; v1 tiếp tục có artifact và hỗ trợ theo policy.

**Bước 3: Thử nâng riêng Payment.** Tạo PR trong Payment, cập nhật tọa độ dependency hoặc BOM riêng. Chạy build, unit/integration, payment sandbox, binary/behavior contract nếu có và kiểm tra dependency conflicts.

**Bước 4: Giảm tác động runtime.** Nếu library v2 đưa ra hành vi mới, bật opt-in/canary trong Payment. Giữ API/event hợp đồng với Order ổn định để Order không phải nâng theo.

**Bước 5: Phát hành Payment.** Triển khai từng phần và quan sát latency, error rate, retry/charge duplicate, correlation ID, security failures. Có sẵn image và cấu hình rollback khả thi.

**Bước 6: Kiểm tra môi trường hỗn hợp.** Test Payment v2 tương tác với Order và Notification phiên bản đang chạy. Đặc biệt kiểm tra event cũ đã lưu, API retries và schema decoding.

**Bước 7: Lên lịch service còn lại.** Order/Notification tự đánh giá bản nâng trong cửa sổ hỗ trợ đã công bố. Không gộp nâng thư viện với thay đổi nghiệp vụ lớn nếu điều đó làm rollback khó phân biệt.

**Bước 8: Thu hẹp legacy.** Khi policy yêu cầu, đo consumer còn ở v1, gửi cảnh báo và mở PR riêng cho từng service; cuối cùng chấm dứt support theo kế hoạch.

Kịch bản chứng minh rằng **không bắt buộc coordinated deployment** không có nghĩa “không cần phối hợp”. Nhóm vẫn phối hợp contract, thông báo security, support window và observability. Tính độc lập thể hiện ở chỗ service có thể dùng phiên bản phù hợp và deploy vào những thời điểm khác nhau.

## 19. Phép thử quan trọng: phiên bản cũ và mới cùng tồn tại

Một chiến lược kiến trúc nên được kiểm chứng bằng môi trường có phiên bản hỗn hợp:

~~~text
                API Gateway
                     |
            +--------+---------+
            |                  |
         Order v1           Payment v2
        Lib 1.4.2          Lib 2.0.0
            |                  |
            +------events------+
                     |
               Notification v1
                 Lib 1.3.9
~~~

Trong thử nghiệm:

1. Order v1 gọi API Payment v2 qua contract đang được hỗ trợ.
2. Payment v2 phát event đọc được bởi Notification v1.
3. Notification v1 xử lý event trùng và unknown optional field theo policy.
4. Rollback Payment về v1 nếu cần mà không làm hỏng schema dữ liệu vừa được ghi.
5. Không service nào bị yêu cầu compile lại chỉ vì một service khác đã nâng thư viện.
6. Theo dõi hành vi runtime quan trọng, không chỉ kết quả deploy.

Nếu test thất bại vì thay đổi serialization hoặc config xuyên service, vấn đề thuộc **runtime contract**, không thể giải quyết chỉ bằng việc gán lại version JAR. Cần điều chỉnh hợp đồng và cơ chế chuyển đổi phù hợp.

### Ma trận chiều triển khai

Có thể viết ma trận producer/consumer:

| Producer | Consumer | Cần xác minh |
|---|---|---|
| V1 | V1 | Baseline |
| V2 | V1 | Tương thích ngược cho consumer chưa nâng |
| V1 | V2 | Consumer mới còn đọc dữ liệu cũ khi rollback hoặc tồn tại event lịch sử |
| V2 | V2 | Hành vi mới ổn định |

Không phải mọi tổ hợp đều được hỗ trợ mãi mãi. Phạm vi ma trận phụ thuộc service contract, retention của event và cửa sổ deploy/rollback; cần công bố chính xác.

## 20. Khi nào cần phát hành song song nhiều major version?

Có thể duy trì nhiều major trong một giai đoạn nếu:

- Các service có chu kỳ nâng cấp khác nhau và không thể chuyển ngay.
- Library version mới yêu cầu runtime/JDK/SDK major khác.
- Một nhóm consumer ngoài tổ chức sử dụng public SDK.
- Cần đổi lớn cách serialize nhưng vẫn phải đọc dữ liệu lịch sử.
- Security support window cho version cũ vẫn còn hiệu lực.

Mỗi nhánh hỗ trợ tăng chi phí backport, test và vận hành. Không nên giữ vô hạn mọi major chỉ để tránh quyết định kết thúc. Một chính sách tốt đặt **end-of-support** dựa trên mức sử dụng, nhu cầu và bảo mật, cho phép nhóm consumer có thời gian chuyển hợp lý.

Khi thay đổi đặc biệt lớn, đôi khi nên phát hành artifact ID mới thay vì tăng major trên cùng tọa độ nếu hai API có thể cùng tồn tại trong một classpath hoặc ranh giới chức năng đã khác. Nhưng điều đó cần có chủ đích: tạo nhiều artifact ID có thể gây trùng code và khó kiểm soát vòng đời.

## 21. Rollback không chỉ là hạ phiên bản thư viện

Giả sử Payment deploy library v2, rồi thấy lỗi trong production. Quay về image Payment trước đó thường đưa runtime code về lib v1. Nhưng các thay đổi sau có thể không tự đảo ngược:

- Database schema đã bị migrate theo chiều chỉ tiến.
- Event format mới đã được đưa vào broker.
- Config cũ bị xóa hoặc key đã đổi.
- Cache/data đã được ghi theo format mới.
- External provider đã nhận lệnh với idempotency rule khác.

Do đó mỗi kế hoạch nâng cần đánh giá:

| Bề mặt | Câu hỏi rollback |
|---|---|
| Code/JAR | Image cũ còn deploy được trên runtime hiện tại không? |
| Configuration | Config cũ còn hợp lệ hay đã bị loại bỏ? |
| Database | Schema mới cho phép code cũ đọc/ghi trong cửa sổ rollback không? |
| Message | Consumer cũ đọc được event mới hoặc dữ liệu trong topic không? |
| External side effect | Có trạng thái không thể hoàn tác như charge/payment không? |
| Observability | Biết được bản nào, dependency nào đang chạy để đánh giá rollback không? |

Một migration theo expand-contract nên giữ code cũ và mới chạy được trong giai đoạn chuyển, cho tới khi cửa sổ rollback kết thúc. Khi contract đã bị loại bỏ có chủ đích, rollback về phiên bản quá cũ có thể không còn an toàn.

## 22. Quyền sở hữu và quản trị thư viện

Một thư viện không thể tự duy trì cam kết tương thích nếu không có owner. Cần biết ai phê duyệt public API, ai review breaking changes, ai vận hành artifact repository và ai tiếp nhận sự cố bảo mật.

Có thể lập danh sách:

| Thông tin | Ví dụ |
|---|---|
| Artifact | com.example.platform:observability-core |
| Owner | Platform Observability Team |
| Supported versions | 1.x và 2.x theo support policy |
| Public API | Các package và extension point được công bố |
| Supported runtime | Java/Spring/adapter matrix đã test |
| Consumers | Order, Payment, Notification, Batch |
| Release policy | SemVer + immutable artifact |
| Breaking change policy | Major release + migration guide + thời hạn deprecation |
| Security policy | CVE assessment, backport khi phù hợp, deadline xử lý |
| Documentation | Changelog, upgrade guide, compatibility matrix |

Việc biết danh sách consumer không đồng nghĩa library owner phải quyết định thời điểm deploy của họ. Danh sách đó giúp thông báo breaking/security changes, phân tích phạm vi ảnh hưởng và bảo đảm migration có đường đi thực tế.

### Chọn mô hình dependency governance

Có thể đặt guardrails ở mức tổ chức: không dùng version có lỗ hổng nghiêm trọng, phải có SBOM, không dùng snapshot production, và tuân thủ runtime được hỗ trợ. Những guardrails này bảo vệ chất lượng và bảo mật; chúng khác với ép tất cả service dùng chung **một phiên bản mới nhất** bất kể độ tương thích hay rủi ro.

## 23. Checklist kỹ thuật trước khi xuất bản một bản thư viện

Trước khi gắn release tag hoặc publish:

1. **Public API:** Những class/method/constructor công khai nào thay đổi? Có xóa hoặc đổi signature không?
2. **Binary:** Consumer đã compile với phiên bản cũ có chạy được nếu thay JAR không?
3. **Behavior:** Retry, timeout, exception, serialization, cache, logging và metric có thay đổi?
4. **Config:** Property cũ còn hoạt động? Default có giữ nguyên hoặc được opt-in?
5. **Transitive dependencies:** Có nâng framework/SDK làm thay đổi classpath của consumer?
6. **Runtime:** Yêu cầu tối thiểu Java/OS/container/framework đã công bố rõ?
7. **Tests:** Unit, API compatibility, consumer fixtures, integration và security phù hợp đã chạy?
8. **Version:** SemVer mới phản ánh cam kết tương thích thực tế?
9. **Artifact:** Được phát hành bất biến, có checksum/provenance và có thể truy vết?
10. **Tài liệu:** Có changelog, compatibility matrix và migration guide nếu cần?
11. **Rollback:** Consumer có thể quay về phiên bản cũ khi phát hiện lỗi trong cửa sổ chuyển?
12. **Support:** Phiên bản trước còn được hỗ trợ trong bao lâu và ai chịu trách nhiệm?
13. **Security:** Nếu sửa lỗ hổng, có hướng xử lý cho nhánh đang dùng rộng rãi?
14. **Communication:** Consumer được thông báo những thay đổi họ thực sự cần biết?

Checklist này hướng tới **khả năng phát hành an toàn**, không phải yêu cầu mọi consumer phải nâng trước khi library được publish.

## 24. Bài thực hành thiết kế

### Bài tập A — Tách library bị coupling

Cho module common-core gồm logger, retry interceptor, OrderEntity, PaymentEntity và một lớp kiểm tra “đơn có được thanh toán không?”. Order và Payment phụ thuộc chung vào common-core.

Hãy đề xuất các ranh giới artifact hợp lý. Xác định thành phần nào nên ở trong service owner và thành phần nào xứng đáng là reusable library. Giải thích vì sao chia nhỏ phù hợp có thể giảm tần suất nâng bắt buộc của những service không liên quan.

### Bài tập B — Phân loại phiên bản

Một release đề xuất ba thay đổi: thêm API mới, đổi default maxAttempts từ 2 lên 5 và yêu cầu Java 21 thay cho Java 17. Hãy xác định các bề mặt compatibility, phương án opt-in hoặc major release, và test cần chạy trước publish.

### Bài tập C — Gradle và độc lập phiên bản

Order dùng observability-core 1.4.2; Payment dùng 1.6.0; Notification dùng 1.3.9. Hãy mô tả vì sao ba version này có thể cùng tồn tại trong hệ thống dù mỗi service có một classpath riêng. Trong một service, hãy xác định tình huống observability-http cần phiên bản core tương thích và vai trò của BOM/platform/locking.

### Bài tập D — Migration không cần triển khai đồng loạt

Producer Payment muốn đổi event field userId thành accountId. Có ba consumer với thời điểm nâng khác nhau. Viết kế hoạch expand-migrate-contract, test producer V2/consumer V1 và consumer V2/producer V1, cùng điều kiện được phép xóa field cũ.

### Bài tập E — Security patch cho nhánh legacy

Một authentication utility v1 được 40 service dùng; v2 chỉ có 5 service đã nâng. Lỗ hổng nằm ở logic chung và có thể sửa tương thích ngược trên v1. Hãy thiết kế phương án backport, rollout theo mức rủi ro, xác nhận các image đang chạy và support window sau vá mà không buộc 45 service đồng loạt nâng v2.

### Bài tập F — Kiểm thử rollback hỗn hợp

Payment nâng từ SDK 1.x lên 2.x, ứng dụng vẫn tương tác với Order cũ. Viết danh sách test cho HTTP API, event schema, database và external payment side effect. Xác định những thay đổi nào khiến rollback chỉ bằng việc hạ Docker image là chưa đủ.

## 25. Những kết luận cần nhớ

- **Một version thư viện không phải một version toàn hệ thống.** Microservice có thể chọn dependency version và deploy độc lập khi runtime contract giữa chúng giữ tương thích.
- **SemVer là lời hứa về public API, không tự động chứng minh tương thích.** Phải xét source, binary, behavior, config, schema và platform.
- **Library dùng chung nên nhỏ, có owner và ít tri thức domain.** Tránh chia sẻ entity/database model hoặc mega-starter làm mọi service đổi cùng nhau.
- **Immutable artifact và pin dependency** giúp mỗi service có build truy vết và rollback được.
- **Additive change, deprecation window và expand-contract** cho phép phiên bản cũ/mới cùng chạy trong giai đoạn chuyển tiếp.
- **BOM/Gradle platform căn chỉnh dependency bên trong một build**; không có lý do kỹ thuật chung để bắt mọi service trên những runtime riêng nâng cùng ngày.
- **Consumer compatibility tests và mixed-version integration tests** chứng minh độc lập triển khai tốt hơn tuyên bố “backward compatible” trong changelog.
- **Security fixes và hết hạn hỗ trợ có thể có deadline bắt buộc**, nhưng không vì thế biến mọi cập nhật thư viện bình thường thành coordinated deployment.

Thiết kế phiên bản tốt cho phép một nhóm phát hành thư viện mới thường xuyên, từng service chủ động áp dụng khi đủ bằng chứng tương thích, và toàn hệ thống vẫn giữ được tính ổn định khi nhiều phiên bản cùng tồn tại.
