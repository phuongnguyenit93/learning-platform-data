# Đối chiếu trạng thái trong ảnh với trạng thái hiện tại của dịch vụ ngoài

CRaC (Coordinated Restore at Checkpoint) lưu trạng thái của một tiến trình Java tại một thời điểm và khôi phục tiến trình từ ảnh đó. Heap, object, cache trong bộ nhớ và luồng thực thi có thể được phục hồi theo trạng thái đã checkpoint. Trong khi đó, database, configuration service, secret manager, service registry, message broker, identity provider và các dịch vụ bên ngoài vẫn tiếp tục hoạt động.

Khoảng cách giữa hai thời điểm tạo checkpoint và restore tạo ra một vấn đề quan trọng: **trạng thái trong ảnh có thể đã cũ so với trạng thái có thẩm quyền ở bên ngoài**.

Ví dụ, ứng dụng checkpoint khi feature flag đang bật. Trong thời gian image được lưu, quản trị viên tắt feature flag vì phát hiện lỗi. Khi restore, object cấu hình trong heap vẫn ghi feature flag là true. Nếu ứng dụng tiếp tục sử dụng object đó mà không đối chiếu, instance có thể bật lại chức năng đã bị vô hiệu hóa.

Vì vậy, một ứng dụng CRaC cần có quy trình đối chiếu trạng thái sau restore. Quy trình này xác định dữ liệu nào được giữ từ image, dữ liệu nào phải đọc lại, dữ liệu nào phải xác minh và dữ liệu nào phải tạo mới.

## 1. Hai thế giới trạng thái ở thời điểm checkpoint và restore

Có thể mô hình hóa hai mốc thời gian:

- **T0 — Checkpoint:** ứng dụng đang chạy và tạo image.
- **T1 — Restore:** tiến trình được khôi phục từ image sau một khoảng thời gian.

Tại T0, ứng dụng có thể đang giữ một bản sao cấu hình, trạng thái service discovery, cache dữ liệu, token, connection pool hoặc trạng thái leader. Những giá trị này phản ánh những gì ứng dụng đã quan sát ở T0.

Trong khoảng T0 đến T1, dịch vụ ngoài có thể thay đổi:

- Cấu hình được cập nhật.
- Secret hoặc certificate được rotate.
- Database chuyển sang schema version mới.
- Endpoint của service được thay thế.
- Một instance khác nhận quyền leader.
- Feature flag hoặc chính sách truy cập bị thu hồi.
- Message broker thay đổi partition assignment.
- Một tài nguyên được tạo, xóa hoặc chuyển quyền sở hữu.

Checkpoint image không tự cập nhật theo những thay đổi đó. Khi restore, ứng dụng cần xác định trạng thái nào còn hợp lệ.

~~~mermaid
sequenceDiagram
    participant App as Java Application
    participant Image as Checkpoint Image
    participant External as External Services

    App->>External: Đọc config revision 17
    External-->>App: Config revision 17
    App->>App: Cache trạng thái trong heap
    App->>Image: Tạo checkpoint tại T0
    Note over Image,External: Tiến trình được giữ trong image
    External->>External: Config đổi thành revision 18
    External->>External: Secret được rotate
    External->>External: Leader lease được cấp cho instance khác
    Image->>App: Restore tại T1
    App->>External: Đọc trạng thái hiện tại
    External-->>App: Revision 18, secret mới, ownership mới
    App->>App: Đối chiếu và cập nhật trạng thái
    App->>App: Chỉ mở readiness khi đã sẵn sàng
~~~

Điểm cần nhớ là image lưu trạng thái của tiến trình tại T0, còn dịch vụ ngoài trả lời câu hỏi trạng thái hiện tại tại T1. Hai nguồn này có thể khác nhau mà không có lỗi checkpoint nào xảy ra.

## 2. Phân loại trạng thái được giữ trong image

Không phải mọi dữ liệu trong heap đều cần được tải lại. Hãy phân loại theo nguồn sở hữu và khả năng thay đổi.

| Loại trạng thái | Ví dụ | Chính sách sau restore |
|---|---|---|
| Trạng thái tính toán nội bộ | Kết quả parse, cấu trúc dữ liệu bất biến, cache có thể tái tạo | Có thể giữ nếu dữ liệu đầu vào và phiên bản vẫn tương thích |
| Snapshot cấu hình | Feature flags, endpoint, giới hạn nghiệp vụ | Kiểm tra revision hoặc tải lại theo chính sách |
| Trạng thái có thẩm quyền ở bên ngoài | Số dư, trạng thái đơn hàng, quyền truy cập | Đọc từ hệ thống sở hữu dữ liệu trước khi ra quyết định |
| Credential và security state | Token, certificate, secret, session | Xác minh hoặc lấy lại từ nguồn quản lý credential |
| Tài nguyên có vòng đời OS | Socket, file descriptor, connection pool | Đóng trước checkpoint và tạo lại sau restore |
| Quyền sở hữu tạm thời | Leader lease, lock, partition assignment | Revalidate hoặc acquire lại |
| Cursor và vị trí xử lý | Message offset, event sequence, change cursor | Đồng bộ với broker/store và replay phần bị bỏ lỡ |
| Metadata của image | Build ID, config revision, schema compatibility | Đối chiếu với môi trường đích trước khi phục vụ |

Một object Java tồn tại trong heap chỉ chứng minh rằng trạng thái của object được lưu trong image. Nó không chứng minh dữ liệu mà object đại diện vẫn là dữ liệu hiện tại hoặc ứng dụng còn quyền sử dụng tài nguyên đó.

### 2.1 Phân biệt bản sao cache với nguồn có thẩm quyền

Giả sử ứng dụng giữ:

~~~java
Map<String, FeatureConfig> featureCache;
~~~

Bản map trong heap là một bản sao mà ứng dụng đã tải từ configuration service. Nếu configuration service là nơi có thẩm quyền, map không được phép ghi đè dữ liệu ở service chỉ vì image chứa giá trị cũ.

Với dữ liệu quan trọng, hãy ghi rõ:

- Hệ thống nào sở hữu dữ liệu.
- Dữ liệu trong heap là bản cache, snapshot hay trạng thái chuẩn.
- Bản sao được xem là hợp lệ trong bao lâu.
- Cách phát hiện thay đổi.
- Hành vi khi không thể liên hệ nguồn có thẩm quyền.

Quy ước ownership này giúp tránh việc một instance restore ghi ngược trạng thái cũ lên hệ thống bên ngoài.

## 3. Chọn chính sách đối chiếu

Có nhiều chính sách phù hợp với các loại trạng thái khác nhau. Không nên dùng một chiến lược duy nhất cho mọi dependency.

### 3.1 Giữ nguyên snapshot đã pin

Một số workload cần tái lập chính xác cấu hình đã dùng để tạo image. Ví dụ, một batch job phải xử lý một bộ dữ liệu hoặc một phiên bản rule cố định.

Trong trường hợp này, image có thể gắn với một revision bất biến. Sau restore, ứng dụng yêu cầu đúng revision đó thay vì lấy bản mới nhất.

Phù hợp khi:

- Revision được lưu lâu dài và không bị sửa tại chỗ.
- Dữ liệu snapshot còn được lưu ở nơi có thể truy cập.
- Mục tiêu là tái lập kết quả hoặc đảm bảo tính nhất quán của một workflow.
- Chính sách bảo mật cho phép tiếp tục dùng revision cũ.

Không phù hợp với trạng thái phải có hiệu lực tức thời như quyền truy cập bị thu hồi, secret bị compromise hoặc kill switch bảo mật.

### 3.2 Tải trạng thái mới nhất

Với cấu hình động, endpoint discovery hoặc feature flag, ứng dụng thường cần tải phiên bản mới nhất sau restore.

Ưu điểm là instance nhanh chóng hội tụ về trạng thái hiện tại. Đổi lại, hành vi của instance sau restore có thể khác với hành vi tại thời điểm image được tạo.

Cần kiểm tra cấu hình mới có tương thích với code và schema mà image chứa hay không. Không phải mọi revision mới đều tương thích với một binary cũ.

### 3.3 Xác minh rồi mới tiếp tục

Với trạng thái có rủi ro cao, ứng dụng nên yêu cầu hệ thống ngoài xác nhận rằng trạng thái trong image còn hợp lệ.

Ví dụ:

- Kiểm tra lease còn thuộc về instance hay không.
- Xác minh session chưa bị revoke.
- Kiểm tra schema version nằm trong khoảng hỗ trợ.
- Xác nhận certificate hoặc credential còn được tin cậy.
- Kiểm tra endpoint và service generation còn hợp lệ.

Nếu xác minh thất bại, ứng dụng phải dừng chức năng phụ thuộc hoặc thực hiện quy trình acquire/re-authenticate.

### 3.4 Merge hoặc reconcile

Một số hệ thống có trạng thái cục bộ cần hợp nhất với trạng thái bên ngoài. Ví dụ, một workflow có local checkpoint marker nhưng event store đã nhận thêm event.

Khi đó, ứng dụng cần quy tắc hợp nhất rõ ràng:

- Dùng revision hoặc sequence để xác định phần nào mới hơn.
- Replay event từ cursor đã lưu.
- Deduplicate bằng event ID.
- Dùng version check khi cập nhật.
- Giải quyết conflict theo quy tắc nghiệp vụ.

Không merge bằng cách ghi đè toàn bộ trạng thái bên ngoài bằng object cũ trong heap.

### 3.5 Bảng lựa chọn

| Trạng thái | Chính sách thường phù hợp | Khi không thể đối chiếu |
|---|---|---|
| Cấu hình cố định theo phiên bản | Pin revision và xác minh tương thích | Từ chối image nếu revision không còn được hỗ trợ |
| Feature flag động | Tải revision mới nhất hoặc xác minh TTL | Giữ readiness false cho chức năng bị ảnh hưởng |
| Secret/certificate | Lấy hoặc xác minh credential hiện tại | Không sử dụng credential cũ khi không xác minh được |
| Database schema | So sánh version với compatibility range | Không mở traffic nếu không tương thích |
| Leader lease/lock | Revalidate hoặc acquire lại | Không thực hiện thao tác yêu cầu quyền sở hữu |
| Service discovery | Resolve endpoint hiện tại và dựng lại client | Chưa sẵn sàng cho tới khi dependency được tìm thấy |
| Cache dữ liệu tham chiếu | Validate revision hoặc rebuild | Chỉ dùng stale cache nếu chính sách cho phép |
| Event cursor | Replay từ cursor bền vững và deduplicate | Dừng consumer nếu không xác định được vị trí an toàn |

## 4. Lưu version và generation thay vì chỉ lưu giá trị

Một snapshot cấu hình nên chứa thông tin về phiên bản mà nó đại diện.

Ví dụ:

~~~java
import java.time.Instant;
import java.util.Map;

public record ConfigSnapshot(
        String revision,
        Instant fetchedAt,
        Map<String, String> values) {
}
~~~

Khi checkpoint, object này có thể được lưu trong heap. Sau restore, ứng dụng đọc revision hiện tại từ configuration service và so sánh.

Nếu chỉ lưu values mà không lưu revision, ứng dụng khó xác định:

- Bản cache được tải khi nào.
- Nó thuộc môi trường nào.
- Nó có bị thay đổi kể từ lần tải trước hay không.
- Có thể pin hoặc rollback về bản nào.
- Image có tương thích với revision mới hay không.

### 4.1 Revision phải có semantics rõ ràng

Một version có thể là:

- Số tăng đơn điệu, chẳng hạn 17, 18, 19.
- Hash nội dung cấu hình.
- ETag do HTTP server cung cấp.
- Generation ID của một resource.
- Commit ID hoặc release ID.
- Version do configuration service quản lý.

Không nên so sánh hai version như chuỗi tùy ý nếu định dạng không bảo đảm thứ tự. Nếu chỉ cần kiểm tra bằng nhau, hash hoặc opaque ETag có thể phù hợp. Nếu cần biết revision nào mới hơn, phải dùng một version có thứ tự được định nghĩa.

### 4.2 Gắn metadata image với trạng thái môi trường

Một hệ thống có thể quản lý metadata bên ngoài image:

~~~json
{
  "checkpointId": "crac-image-2026-11-13-001",
  "applicationBuild": "2.8.1",
  "environment": "production-eu",
  "configRevision": "cfg-1842",
  "schemaCompatibility": {
    "minimum": 42,
    "maximum": 44
  },
  "createdAt": "2026-11-13T06:00:00Z"
}
~~~

Đây là ví dụ metadata do deployment platform định nghĩa, không phải format bắt buộc của CRaC.

Controller có thể kiểm tra metadata trước khi restore hoặc trước khi mở traffic. Nếu image thuộc environment khác, config revision đã bị thu hồi hoặc schema nằm ngoài compatibility range, controller có thể từ chối image và khởi động ứng dụng theo cách thông thường.

Metadata không thay thế việc xác minh runtime. Trạng thái bên ngoài vẫn có thể thay đổi sau khi controller đọc metadata.

## 5. Đối chiếu cấu hình động bằng revision hoặc ETag

Configuration service thường cung cấp revision hoặc HTTP ETag để client biết nội dung đã thay đổi hay chưa.

Ví dụ, lần tải đầu nhận:

~~~http
HTTP/1.1 200 OK
ETag: "config-r17"
Content-Type: application/json
~~~

Sau restore, client gửi conditional request:

~~~http
GET /config/application
If-None-Match: "config-r17"
~~~

Nếu nội dung chưa đổi, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "config-r17"
~~~

Nếu nội dung đã đổi, server trả nội dung mới cùng ETag mới:

~~~http
HTTP/1.1 200 OK
ETag: "config-r18"
Content-Type: application/json
~~~

Cách này giảm lượng dữ liệu truyền và cho phép ứng dụng phát hiện cache đã cũ.

### 5.1 Ví dụ client dùng Java HttpClient

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class ConfigClient {

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    public ConfigResponse fetch(String etag) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create("https://config.example.internal/app"))
                .timeout(Duration.ofSeconds(5))
                .GET();

        if (etag != null) {
            builder.header("If-None-Match", etag);
        }

        HttpResponse<String> response = client.send(
                builder.build(),
                HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() == 304) {
            return ConfigResponse.notModified(etag);
        }

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Config service returned " + response.statusCode());
        }

        String newEtag = response.headers()
                .firstValue("ETag")
                .orElseThrow(() ->
                        new IllegalStateException("Missing ETag"));

        return ConfigResponse.updated(newEtag, response.body());
    }
}
~~~

ConfigResponse ở đây là kiểu dữ liệu do ứng dụng định nghĩa. Cần xác minh response body, schema, signature hoặc policy trước khi áp dụng cấu hình.

### 5.2 Áp dụng cấu hình theo cách nguyên tử

Không cập nhật từng field của cấu hình dùng chung trong khi các thread khác đang đọc. Hãy parse và validate bản mới trước, sau đó thay thế snapshot bằng một thao tác nguyên tử:

~~~java
AtomicReference<ConfigSnapshot> current =
        new AtomicReference<>();

void apply(ConfigSnapshot candidate) {
    validate(candidate);
    current.set(candidate);
}
~~~

Các thread đọc snapshot hiện tại sẽ thấy một phiên bản hoàn chỉnh. Không có khoảng thời gian mà một số field thuộc revision cũ và một số field thuộc revision mới.

Nếu một cấu hình mới không hợp lệ hoặc không tương thích với binary hiện tại, hãy từ chối áp dụng và báo lỗi. Không ghi đè snapshot hợp lệ bằng dữ liệu chưa được kiểm tra.

## 6. Không ghi ngược snapshot cũ lên dịch vụ ngoài

Một lỗi nguy hiểm là restore một object cũ rồi gửi toàn bộ object đó trở lại service ngoài.

Ví dụ, image chứa:

~~~json
{
  "revision": 17,
  "maintenanceMode": false,
  "maxWorkers": 20
}
~~~

Trong thời gian image được giữ, quản trị viên cập nhật revision 18:

~~~json
{
  "revision": 18,
  "maintenanceMode": true,
  "maxWorkers": 5
}
~~~

Nếu instance restore gửi PUT toàn bộ revision 17 lên service, nó có thể ghi đè maintenanceMode và maxWorkers mới. Đây là lost update.

### 6.1 Dùng conditional update

Nếu API hỗ trợ ETag hoặc version, gửi điều kiện phiên bản mà client đã đọc:

~~~http
PUT /config/application
If-Match: "config-r17"
Content-Type: application/json
~~~

Nếu server hiện đang ở revision 18, server từ chối cập nhật với **412 Precondition Failed**. Client phải tải lại trạng thái mới và giải quyết conflict.

Đây là optimistic concurrency control. Nó giúp ngăn một bản snapshot cũ ghi đè dữ liệu mới.

### 6.2 Chỉ cập nhật field mà instance sở hữu

Nếu instance chỉ quản lý trạng thái riêng như lastSeen hoặc runtime metrics, hãy dùng endpoint riêng cho những field đó. Không gửi toàn bộ cấu hình toàn cục.

Ví dụ:

- Configuration service sở hữu feature flags và giới hạn nghiệp vụ.
- Instance registry sở hữu heartbeat và trạng thái instance.
- Lease service sở hữu quyền leader.
- Database sở hữu trạng thái đơn hàng.
- Ứng dụng chỉ sở hữu cache cục bộ.

Phân định ownership giúp các instance restore độc lập không tranh quyền cập nhật cùng một tài liệu trạng thái.

## 7. Đối chiếu secret, certificate và identity

Secret và certificate có thể thay đổi trong khi image được lưu. Đây là nhóm trạng thái cần xử lý nghiêm ngặt vì dữ liệu cũ có thể vẫn hoạt động về mặt kỹ thuật nhưng không còn được phép sử dụng.

### 7.1 Secret rotation

Giả sử image chứa database password cũ. Trong thời gian checkpoint, secret manager rotate password và thu hồi credential cũ.

Sau restore, connection pool được tạo lại bằng password trong heap. Kết nối sẽ thất bại.

Quy trình phù hợp:

1. Xác định secret manager là nguồn có thẩm quyền.
2. Lấy secret version hiện tại sau restore.
3. Xác thực định dạng và quyền truy cập.
4. Tạo connection hoặc client mới bằng secret hiện tại.
5. Chỉ thay thế credential đang dùng sau khi client mới hoạt động.
6. Không log secret hoặc đưa giá trị bí mật vào metadata image.

Nếu secret manager chưa sẵn sàng, giữ readiness false cho chức năng phụ thuộc. Không dùng credential cũ chỉ để ứng dụng khởi động nhanh hơn nếu credential đó có thể đã bị revoke.

### 7.2 Certificate và trust store

Certificate có thể hết hạn, bị thu hồi hoặc được thay thế. Trust store cũng có thể được cập nhật để loại bỏ CA không còn tin cậy.

Sau restore, cần xác minh:

- Certificate client còn trong thời hạn.
- Private key tương ứng còn khả dụng và được phép dùng.
- Certificate chain vẫn được trust.
- Server certificate mới có được trust store chấp nhận.
- TLS client context hoặc connection pool cũ có cần tạo lại hay không.

Một SSLContext được giữ trong heap có thể chứa trust material cũ. Nếu chính sách yêu cầu cập nhật ngay, hãy xây dựng SSLContext mới từ trust store hiện tại và thay thế client theo cách an toàn.

### 7.3 Workload identity

Nếu ứng dụng chạy trên Kubernetes hoặc cloud, credential có thể được cấp qua service account token, metadata service hoặc workload identity provider.

Token trong image có thể hết hạn hoặc gắn với pod/instance cũ. Sau restore thành nhiều replica, không nên giả định mọi replica có thể dùng cùng một token.

Lấy credential mới theo identity của từng instance sau restore. Nếu môi trường yêu cầu token file được rotate, hãy đọc lại file hoặc dùng SDK có hỗ trợ refresh credential.

## 8. Service discovery và endpoint có thể thay đổi

Một object client trong heap có thể giữ endpoint, IP hoặc connection pool được tạo trước checkpoint.

Trong lúc image được giữ:

- Service có thể scale up hoặc scale down.
- Pod có thể bị thay thế.
- IP có thể thay đổi.
- DNS record có thể được cập nhật.
- Service có thể chuyển vùng hoặc chuyển cluster.
- Certificate hoặc route có thể được rotate.

Sau restore, không nên sử dụng endpoint hoặc connection cũ chỉ vì object client còn tồn tại.

### 8.1 Resolve endpoint mới

Client nên phân giải service name hoặc truy vấn service registry sau restore. Sau đó tạo lại connection pool và health check endpoint.

~~~java
public final class ApiClientResource implements Resource {

    private final ServiceDiscovery discovery;
    private final ApiClientFactory factory;
    private ApiClient client;

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (client != null) {
            client.close();
            client = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        ServiceEndpoint endpoint = discovery.resolve("orders");
        ApiClient replacement = factory.create(endpoint);
        replacement.healthCheck();
        client = replacement;
    }
}
~~~

ServiceDiscovery, ServiceEndpoint, ApiClientFactory và ApiClient là abstraction minh họa. Client thực tế cần có timeout, TLS configuration, retry policy và cách đóng connection rõ ràng.

### 8.2 DNS cache

JVM có thể cache DNS resolution theo security properties và cấu hình runtime. Nếu ứng dụng cần dùng endpoint mới sau restore, hãy kiểm tra chính sách DNS cache của JDK và thư viện network.

Ngay cả khi DNS được resolve lại, connection pool cũ có thể vẫn giữ TCP connection tới địa chỉ cũ. Vì vậy, cần quản lý cả DNS resolution lẫn vòng đời socket.

Không nên chỉ thay một chuỗi hostname trong config rồi cho rằng mọi connection đã được chuyển sang endpoint mới.

### 8.3 Health check không phải là kiểm tra trạng thái nghiệp vụ

Một endpoint trả HTTP 200 chỉ chứng minh một mức độ sẵn sàng nhất định. Nếu client cần quyền truy cập cụ thể, cần kiểm tra chức năng hoặc quyền tương ứng.

Ví dụ, service có thể phản hồi health endpoint nhưng database của service đang read-only hoặc queue consumer chưa được assign partition. Hãy chọn validation phù hợp với chức năng mà ứng dụng cần dùng.

## 9. Database schema và trạng thái dữ liệu bên ngoài

Database không được đóng băng cùng image. Schema, dữ liệu và quyền có thể thay đổi trong thời gian checkpoint.

Một image được tạo khi ứng dụng dùng schema revision 42 có thể được restore sau khi database chuyển sang revision 45.

Trước khi phục vụ, ứng dụng nên xác minh:

- Schema version hiện tại nằm trong khoảng code hỗ trợ.
- Các bảng và cột cần thiết còn tồn tại.
- Database user vẫn có quyền phù hợp.
- Connection pool đã được tạo mới.
- Các transaction cũ không được xem là còn mở.
- Cache phụ thuộc dữ liệu database đã được validate hoặc rebuild.

Không tự động chạy migration phá vỡ tương thích trong afterRestore chỉ để làm cho image cũ tiếp tục hoạt động. Nếu schema mới không tương thích, từ chối image hoặc triển khai theo chiến lược expand/contract.

### 9.1 Trạng thái dữ liệu không thể suy ra từ cache

Ví dụ, image giữ cache:

~~~java
Map<Long, OrderStatus> orderStatusCache;
~~~

Trong khi tiến trình không chạy, một đơn hàng có thể được thanh toán, hủy hoặc hoàn tiền. Cache trong image không phản ánh các thay đổi đó.

Đối với dữ liệu nghiệp vụ có tính nhất quán cao, hãy truy vấn database hoặc invalidate cache. Stale cache chỉ được sử dụng nếu nghiệp vụ cho phép độ trễ và có giới hạn rõ ràng.

### 9.2 Cache revision và invalidation

Có thể gắn revision của nguồn dữ liệu vào cache:

~~~java
public record CacheSnapshot(
        long sourceRevision,
        Instant loadedAt,
        Map<Long, OrderStatus> values) {
}
~~~

Sau restore, so sánh sourceRevision với revision hiện tại. Nếu khác, tải lại hoặc invalidate.

Nếu database không cung cấp revision tổng thể, có thể dùng bảng metadata, CDC sequence, event offset hoặc version của từng entity. Chọn một cơ chế có semantics được xác định, không dựa vào timestamp local đơn thuần.

## 10. Message broker, event cursor và subscription

Một consumer có thể giữ trong heap:

- Partition assignment.
- Offset đã đọc hoặc đã xử lý.
- Subscription state.
- Connection tới broker.
- Batch message đang xử lý.

Broker vẫn tiếp tục hoạt động khi tiến trình được checkpoint. Trong thời gian đó, partition assignment có thể thay đổi và message mới có thể được ghi vào log.

### 10.1 Không giữ assignment cũ

Sau restore, consumer cần reconnect và tham gia lại cơ chế group coordination. Broker có thể cấp partition khác với partition mà image ghi nhận.

Không tự khẳng định instance vẫn sở hữu partition cũ. Hãy để broker hoặc consumer group coordinator quyết định assignment mới.

### 10.2 Xác định offset an toàn

Phân biệt:

- Offset đã fetch.
- Offset đã xử lý.
- Offset đã commit.
- Offset được xác nhận bởi broker.

Nếu checkpoint lưu offset đã fetch nhưng chưa xử lý xong, sau restore có thể bỏ sót hoặc xử lý lặp tùy cách commit.

Một chính sách phổ biến là commit sau khi side effect đã được lưu bền vững. Sau restore, bắt đầu từ committed offset và dùng idempotent processing để xử lý lại an toàn khi cần.

### 10.3 Replay event bị bỏ lỡ

Nếu ứng dụng dùng event stream để cập nhật cache, image có thể chứa cursor ở sequence 100. Trong thời gian checkpoint, stream đã tới sequence 130.

Sau restore:

1. Reconnect tới broker.
2. Lấy cursor bền vững hoặc sequence hiện tại.
3. Replay event từ vị trí an toàn.
4. Deduplicate theo event ID.
5. Áp dụng event theo thứ tự cần thiết.
6. Chỉ đánh dấu state synchronized khi đã bắt kịp tới một watermark phù hợp.

Không chỉ mở lại subscription rồi giả định cache trong heap đã mới nhất.

## 11. Lease, leader election và quyền sở hữu tài nguyên

Một image có thể chứa boolean isLeader=true hoặc object lock đã được acquire trước checkpoint. Sau một khoảng thời gian, lease có thể hết hạn và một instance khác đã nhận quyền leader.

Nếu nhiều replica restore cùng image, tất cả có thể cùng mang trạng thái isLeader=true trong heap. Đây là lỗi nghiêm trọng nếu mỗi instance tiếp tục ghi dữ liệu hoặc điều phối job.

### 11.1 Không checkpoint quyền sở hữu tạm thời như một sự thật

Trạng thái leader hoặc lock trong heap chỉ là quan sát tại T0. Sau restore, phải xác minh lại với lease service hoặc database lock.

Nếu lease đã hết hạn:

- Không tiếp tục side effect.
- Acquire lease mới bằng thao tác nguyên tử.
- Nhận generation hoặc fencing token mới.
- Chỉ hoạt động sau khi hệ thống đích xác nhận quyền sở hữu.

### 11.2 Fencing token bảo vệ khỏi owner cũ

Giả sử instance A có fencing token 105. A checkpoint và lease hết hạn. Instance B nhận token 106. Sau đó A restore.

Nếu A vẫn gửi lệnh với token 105, hệ thống đích phải từ chối vì token 106 đã mới hơn. Như vậy, kể cả A không biết lease đã mất, fencing vẫn ngăn nó ghi dữ liệu.

Một boolean local hoặc lock object không thể thay thế cơ chế này.

## 12. Quy trình reconcile sau restore

Một ứng dụng có thể xây dựng một giai đoạn RECONCILING riêng sau khi các resource cơ bản đã được tạo lại.

Trình tự tham khảo:

1. Giữ readiness phục vụ traffic ở false.
2. Tạo lại các connection tới dịch vụ ngoài.
3. Đọc revision/generation hiện tại từ nguồn có thẩm quyền.
4. Xác minh application build tương thích với trạng thái hiện tại.
5. Làm mới secret, certificate và identity.
6. Revalidate lease, lock và service ownership.
7. Đồng bộ event cursor hoặc cache cần thiết.
8. Áp dụng snapshot mới theo cách nguyên tử.
9. Chạy health check chức năng.
10. Chuyển trạng thái sang READY.

~~~mermaid
stateDiagram-v2
    [*] --> RESTORING
    RESTORING --> RECONNECTING: JVM và resource bắt đầu phục hồi
    RECONNECTING --> RECONCILING: Kết nối dependency thành công
    RECONNECTING --> FAILED: Dependency không thể kết nối
    RECONCILING --> VALIDATING: Đã đọc trạng thái hiện tại
    RECONCILING --> FAILED: Conflict hoặc state không tương thích
    VALIDATING --> READY: Tất cả điều kiện thiết yếu hợp lệ
    VALIDATING --> FAILED: Validation thất bại
    READY --> SERVING: Mở readiness
    FAILED --> RECONCILING: Retry có giới hạn
~~~

Trạng thái RECONCILING giúp phân biệt một JVM đã restore với một ứng dụng đã thực sự đồng bộ với môi trường hiện tại.

### 12.1 Phân biệt dependency bắt buộc và tùy chọn

Không phải dịch vụ nào cũng cần hoạt động trước khi ứng dụng nhận traffic.

Ví dụ:

- Database chính có thể là dependency bắt buộc.
- Feature flag service có thể bắt buộc nếu nó điều khiển quyền truy cập.
- Metrics exporter có thể là tùy chọn.
- Một cache có thể được rebuild bất đồng bộ nếu database vẫn đủ khả năng phục vụ.
- Search index có thể không cần thiết với một số endpoint.

Hãy xác định rõ từng dependency có thể:

- Chặn toàn bộ readiness.
- Chặn một nhóm chức năng.
- Dùng snapshot cũ trong thời gian giới hạn.
- Bỏ qua tạm thời.
- Khiến instance phải dừng.

Không để trạng thái lỗi của dependency tùy chọn vô tình làm toàn bộ ứng dụng mất sẵn sàng. Ngược lại, không đánh dấu ready nếu dependency bắt buộc chưa được xác minh.

## 13. Ví dụ Java: đối chiếu ConfigSnapshot trong afterRestore

Ví dụ dưới đây minh họa một Resource giữ snapshot cấu hình trong heap và tải revision hiện tại từ service sau restore.

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ConfigResource implements Resource {

    private final ConfigClient client;
    private final ConfigValidator validator;
    private final AtomicReference<ConfigSnapshot> current;

    public ConfigResource(
            ConfigClient client,
            ConfigValidator validator,
            ConfigSnapshot initial) {
        this.client = client;
        this.validator = validator;
        this.current = new AtomicReference<>(initial);

        Core.getGlobalContext().register(this);
    }

    public ConfigSnapshot current() {
        return current.get();
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Có thể pause watcher hoặc config polling tại đây.
        // Không ghi snapshot cũ trở lại configuration service.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        ConfigSnapshot restored = current.get();
        ConfigSnapshot latest = client.fetchCurrent();

        validator.validate(latest);

        if (!latest.revision().equals(restored.revision())) {
            current.set(latest);
        }
    }
}

record ConfigSnapshot(
        String revision,
        Instant fetchedAt,
        Map<String, String> values) {
}
~~~

ConfigClient và ConfigValidator là abstraction của ứng dụng. Trong production, cần bổ sung timeout, xác thực response, kiểm tra môi trường và chính sách khi revision mới không tương thích.

Một số điểm quan trọng:

- Snapshot trong heap được xem là bản cache.
- Configuration service là nguồn có thẩm quyền.
- Sau restore, client tải trạng thái mới.
- Validator kiểm tra trước khi thay snapshot.
- AtomicReference thay toàn bộ snapshot trong một thao tác.
- Không gửi dữ liệu cũ về service ngoài.

Nếu latest không thể tải vì network lỗi, hành vi phụ thuộc chính sách. Với cấu hình bảo mật hoặc cấu hình bắt buộc, callback nên thất bại để restore không được xem là hoàn tất. Với một số cấu hình không quan trọng, ứng dụng có thể giữ bản cũ trong thời gian ngắn nhưng phải ghi nhận trạng thái STALE và giới hạn chức năng.

### 13.1 Không phải mọi đối chiếu đều nên nằm trong callback

Callback afterRestore có thể thực hiện các thao tác đồng bộ cần thiết để tiến trình trở lại trạng thái nhất quán. Tuy nhiên, không nên đưa mọi tác vụ tải dữ liệu lớn hoặc retry vô hạn vào callback.

Có thể chia hai giai đoạn:

- **Bắt buộc trước readiness:** tạo connection, xác minh identity, đọc revision và kiểm tra các dependency cốt lõi.
- **Có thể chạy nền:** rebuild cache lớn, tải dữ liệu tham chiếu tùy chọn, prefetch hoặc warm-up bổ sung.

Nếu chọn phục hồi bất đồng bộ, readiness phải phản ánh rõ những chức năng nào đã sẵn sàng. Không được chuyển toàn bộ ứng dụng sang READY trước khi các điều kiện bắt buộc hoàn tất.

## 14. Xử lý lỗi và conflict khi reconcile

Đối chiếu có thể thất bại vì network, quyền truy cập, version incompatibility hoặc conflict dữ liệu.

| Lỗi | Cách xử lý |
|---|---|
| Timeout khi đọc config | Retry có giới hạn; giữ readiness false nếu config bắt buộc |
| Revision mới không tương thích với build | Từ chối image hoặc yêu cầu rollout build mới |
| Secret đã rotate | Lấy credential hiện tại và tạo lại client |
| ETag thay đổi trước conditional update | Tải lại và giải quyết conflict |
| Lease đã mất | Không thực hiện side effect; acquire lại nếu được phép |
| Schema vượt compatibility range | Không mở traffic; triển khai migration/rollout phù hợp |
| Broker assignment thay đổi | Chấp nhận assignment mới và đồng bộ cursor |
| Cache revision không khớp | Invalidate hoặc rebuild |
| Dependency tùy chọn không sẵn sàng | Chuyển chức năng phụ thuộc sang degraded nếu policy cho phép |

### 14.1 Retry phải có giới hạn

Một callback có thể gặp dịch vụ tạm thời không sẵn sàng. Dùng timeout, backoff và số lần thử tối đa.

Không retry một lỗi không thể tự phục hồi như:

- Credential bị revoke.
- Schema không tương thích.
- Resource đã bị xóa vĩnh viễn.
- Permission bị thu hồi.
- Image thuộc sai environment.

Các lỗi này cần một quyết định deployment hoặc vận hành, không phải retry liên tục.

### 14.2 Không bỏ qua conflict bằng cách ghi đè

Nếu conditional update trả 412 Precondition Failed, client biết trạng thái đã thay đổi. Hãy tải lại và xử lý theo ownership/version. Không tự động gửi lại cùng payload cũ mà bỏ header If-Match.

### 14.3 Phân biệt STALE với INVALID

Một snapshot cũ chưa chắc đã sai. Có thể nó vẫn hợp lệ trong một TTL hoặc theo một revision pin.

- **FRESH:** đã đối chiếu với nguồn hiện tại.
- **STALE:** chưa được làm mới, nhưng policy cho phép sử dụng tạm thời.
- **INVALID:** không còn tương thích hoặc đã bị thu hồi.
- **UNKNOWN:** không thể xác minh do lỗi kết nối.

UNKNOWN không nên tự động chuyển thành FRESH. Ứng dụng cần chính sách rõ ràng cho từng trạng thái.

## 15. Restore một image thành nhiều instance

Một image có thể được dùng để tạo nhiều instance nhằm scale nhanh. Tất cả instance có thể bắt đầu từ cùng snapshot trong heap.

Điều này tạo ra các rủi ro:

- Cùng giữ một instance ID.
- Cùng dùng một token hoặc credential.
- Cùng nghĩ mình là leader.
- Cùng giữ một message offset.
- Cùng ghi một sequence number.
- Cùng đăng ký một scheduled job.
- Cùng gửi lại một side effect đã thực hiện bởi instance khác.

### 15.1 Tạo identity riêng cho mỗi instance

Nếu hệ thống cần instance identity duy nhất, hãy lấy hoặc tạo identity mới sau restore từ nền tảng hoặc registry. Không dùng UUID đã được tạo trước checkpoint làm định danh của tất cả replica.

Identity có thể gồm:

- Pod UID hoặc VM instance ID.
- Process generation.
- Deployment revision.
- Region/zone.
- Checkpoint image ID.

Không nhầm application build ID dùng chung với instance ID cần duy nhất.

### 15.2 Trạng thái dùng chung phải có coordination

Một biến static trong image không thể làm distributed lock. Nhiều replica restore đều có cùng giá trị static.

Các tài nguyên dùng chung cần coordination ở bên ngoài:

- Database unique constraint.
- Distributed lock hoặc lease service.
- Compare-and-set.
- Idempotency key.
- Fencing token.
- Consumer group coordination.

### 15.3 Không lặp side effect

Nếu checkpoint image được tạo sau khi một thao tác đã gửi tới hệ thống bên ngoài nhưng trước khi ứng dụng ghi nhận kết quả vào heap, restore có thể gửi lại thao tác.

Ví dụ, một request tạo payment đã được payment service xử lý, nhưng response chưa được lưu vào trạng thái local. Sau restore, code có thể gửi lại payment.

Dùng idempotency key ổn định cho cùng một nghiệp vụ, truy vấn trạng thái trước khi retry và lưu trạng thái nghiệp vụ bền vững ở nguồn có thẩm quyền.

## 16. Quan sát trạng thái đối chiếu

Để biết ứng dụng đã đồng bộ sau restore hay chưa, nên ghi nhận các mốc và version liên quan.

Metric hoặc log hữu ích:

- checkpoint ID và image build ID.
- instance ID mới sau restore.
- thời điểm bắt đầu restore và reconcile.
- revision trong image.
- revision hiện tại từ external service.
- số dependency đã reconnect.
- số snapshot được refresh hoặc invalidate.
- thời gian reconcile.
- số conflict conditional update.
- số lần retry và timeout.
- trạng thái cuối cùng FRESH, STALE, INVALID hoặc UNKNOWN.
- thời điểm readiness chuyển true.

Không log secret, access token hoặc session ID nguyên bản. Dùng reference không nhạy cảm hoặc hash có kiểm soát để liên kết log.

Ví dụ log có thể trông như sau:

~~~json
{
  "event": "external_state_reconciled",
  "checkpointId": "crac-image-2026-11-13-001",
  "instanceId": "pod-7f8b9",
  "configRevisionInImage": "cfg-17",
  "configRevisionCurrent": "cfg-18",
  "result": "UPDATED",
  "durationMs": 142
}
~~~

Log này giúp xác định vì sao instance sau restore dùng cấu hình khác với thời điểm tạo image.

## 17. Kiểm thử trạng thái thay đổi giữa checkpoint và restore

Một bài kiểm thử chỉ restore ngay sau checkpoint thường không phát hiện được state drift. Cần mô phỏng thay đổi thực sự ở dịch vụ ngoài.

| Tình huống | Thay đổi trong lúc image được giữ | Điều cần xác nhận |
|---|---|---|
| Config update | Revision 17 thành 18 | Instance tải hoặc pin đúng revision theo policy |
| Feature flag off | Kill switch bị tắt | Không bật lại flag cũ từ heap |
| Secret rotation | Password/token cũ bị revoke | Client dùng secret mới hoặc giữ readiness false |
| Certificate renewal | Certificate hoặc trust store thay đổi | TLS client được tạo lại với trust material hiện tại |
| Database migration | Schema tiến lên version mới | Image được xác minh tương thích |
| Service replacement | Endpoint/IP thay đổi | Connection pool được tạo lại với endpoint mới |
| Lease expiry | Instance khác nhận lease | Instance restore không tiếp tục quyền sở hữu cũ |
| Broker rebalance | Partition assignment thay đổi | Consumer tham gia lại group và xử lý offset đúng |
| Session revoke | Người dùng logout | Session cũ không được chấp nhận |
| Restore nhiều replica | Cùng image tạo nhiều instance | Identity, lock, token và side effect không bị dùng chung sai cách |
| External service unavailable | Không thể đọc trạng thái mới | Policy fail-closed hoặc degraded được áp dụng đúng |

Nên kiểm thử cả các trường hợp thay đổi giữa hai lần kiểm tra: trạng thái có thể thay đổi ngay sau khi reconcile. Với thao tác ghi quan trọng, dùng conditional update hoặc lease/fencing để bảo vệ tại thời điểm thực hiện, không chỉ kiểm tra một lần ở startup.

## 18. Những sai lầm thường gặp

### Tin mọi object trong heap vẫn phản ánh trạng thái hiện tại

Object chỉ phản ánh snapshot ở thời điểm checkpoint. Dữ liệu ngoài tiến trình có thể đã thay đổi.

### Ghi ngược cấu hình cũ lên configuration service

Instance restore có thể ghi đè thay đổi mới. Dùng ownership rõ ràng và conditional update theo revision.

### Chỉ kiểm tra endpoint có phản hồi

HTTP 200 không chứng minh service có đúng version, quyền, schema hoặc trạng thái nghiệp vụ mà ứng dụng cần.

### Giữ connection pool và endpoint cũ

Object client còn tồn tại không chứng minh socket hoặc endpoint vẫn hợp lệ. Reconnect và resolve lại dependency.

### Dùng boolean isLeader đã checkpoint

Quyền leader hoặc lease có thể đã hết hạn. Revalidate với lease service và dùng fencing token.

### Giữ token hoặc secret cũ

Credential có thể bị rotate hoặc revoke. Lấy trạng thái hiện tại từ secret manager hoặc identity provider.

### Chỉ so sánh timestamp local

Clock skew và revocation có thể làm local timestamp sai. Ưu tiên revision, generation hoặc trạng thái có thẩm quyền từ service.

### Cho phép UNKNOWN được xem là VALID

Nếu không liên hệ được dependency, ứng dụng không biết trạng thái hiện tại. Hãy áp dụng fail-closed với chức năng bảo mật và chức năng có tính nhất quán cao.

### Restore nhiều replica với cùng identity

Nhiều instance có thể ghi đè state hoặc cùng thực hiện một side effect. Tạo identity mới và dùng coordination bên ngoài.

### Chuyển readiness sang true quá sớm

JVM đã restore không đồng nghĩa các dependency đã được đối chiếu. Chỉ mở traffic sau khi trạng thái bắt buộc đã hợp lệ.

## 19. Quy trình triển khai

Khi đưa ứng dụng Java vào CRaC, có thể áp dụng quy trình sau để đối chiếu trạng thái trong image với trạng thái hiện tại của dịch vụ ngoài:

**Bước 1 — Kiểm kê state được cache.** Tìm config snapshot, feature flag, secret, token, endpoint, schema version, lease, session, cache và event cursor.

**Bước 2 — Xác định nguồn có thẩm quyền.** Ghi rõ hệ thống sở hữu từng dữ liệu và instance có quyền đọc hay ghi field nào.

**Bước 3 — Chọn policy cho từng loại state.** Pin revision, refresh latest, validate, merge hoặc recreate tùy semantics.

**Bước 4 — Lưu metadata.** Gắn revision, generation, application build và checkpoint ID để nhận diện trạng thái trong image.

**Bước 5 — Reconnect và reconcile.** Sau restore, tạo lại connection, đọc trạng thái hiện tại, kiểm tra compatibility và áp dụng snapshot mới nguyên tử.

**Bước 6 — Bảo vệ thao tác ghi.** Dùng ETag/If-Match, version check, compare-and-set, idempotency key hoặc fencing token để tránh ghi đè state mới.

**Bước 7 — Xử lý multi-instance.** Tạo identity riêng, lấy credential riêng và không kế thừa quyền sở hữu tạm thời từ image.

**Bước 8 — Quản lý readiness.** Giữ ứng dụng ở RECONCILING cho tới khi dependency bắt buộc đã được xác minh. Cho phép degraded mode chỉ khi policy đã định nghĩa.

**Bước 9 — Kiểm thử state drift.** Thay đổi config, secret, schema, endpoint, lease và session trong thời gian image được giữ; sau đó restore và xác nhận hành vi.

**Bước 10 — Quan sát.** Ghi revision trước/sau, thời gian reconcile, conflict, retry và readiness transition để có thể truy vết.

Một ứng dụng CRaC đáng tin cậy phải xem checkpoint image là snapshot của tiến trình tại T0 và chủ động đối chiếu với các nguồn trạng thái có thẩm quyền tại T1. Cách làm này giúp image được tái sử dụng mà không vô tình khôi phục cấu hình đã bị thu hồi, quyền sở hữu đã hết hạn hoặc dữ liệu đã lỗi thời.

## Tài liệu tham khảo

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và sự phối hợp giữa ứng dụng với tài nguyên bên ngoài.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): đăng ký Resource và lifecycle callback beforeCheckpoint/afterRestore.
- [Java API — AtomicReference](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): thay thế snapshot cấu hình theo cách nguyên tử.
- [Java API — HttpClient](https://docs.oracle.com/en/java/javase/24/docs/api/java.net.http/java/net/http/HttpClient.html): tạo HTTP client và gửi request có timeout.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ETag, If-Match, If-None-Match và conditional requests.
- [RFC 7232 — HTTP Conditional Requests](https://www.rfc-editor.org/rfc/rfc7232): cơ chế validator và điều kiện cập nhật HTTP (được hợp nhất vào RFC 9110).
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/): quản lý cấu hình và cập nhật cấu hình cho workload.
- [Kubernetes — Service](https://kubernetes.io/docs/concepts/services-networking/service/): discovery và truy cập endpoint của service.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): quản lý credential, refresh token và thu hồi.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): xác thực và bảo vệ kết nối TLS.

