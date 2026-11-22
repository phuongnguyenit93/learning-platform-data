# SDK đám mây, bộ cấp thông tin xác thực và bộ đệm kết nối

Ứng dụng Java thường dùng SDK của nhà cung cấp đám mây để truy cập object storage, database, message queue, secret manager hoặc API quản trị. Một SDK client có thể giữ nhiều tài nguyên bên trong: credential provider, token cache, HTTP connection pool, socket, TLS session, DNS cache, event loop, executor và thread làm mới thông tin xác thực.

Khi ứng dụng dùng CRaC (Coordinated Restore at Checkpoint), các tài nguyên này cần được xem xét theo vòng đời của tiến trình. Một checkpoint có thể được tạo trước khi triển khai và được restore nhiều phút hoặc nhiều giờ sau đó. Trong khoảng thời gian đó, access token có thể hết hạn, role hoặc workload identity có thể thay đổi, DNS có thể trỏ đến endpoint khác, socket có thể bị peer hoặc NAT đóng, và connection pool có thể giữ những kết nối không còn dùng được.

Vì vậy, không nên coi một SDK client còn tồn tại trong heap sau restore là bằng chứng rằng nó vẫn có thể gọi dịch vụ đám mây. Cần xác định ai sở hữu client, credential provider và HTTP transport; ngừng request đang chạy trước checkpoint; sau restore làm mới identity và kết nối theo đúng tài liệu của SDK; rồi kiểm tra khả năng gọi dịch vụ trước khi mở traffic.

## 1. Các thành phần trong một cloud SDK client

Một cloud SDK client thường là facade mà mã nghiệp vụ gọi để thực hiện request. Phía sau facade có thể là nhiều thành phần:

- **Credential provider:** Lấy thông tin xác thực từ biến môi trường, file cấu hình, workload identity, metadata service, role service hoặc secret manager.
- **Credential/token cache:** Giữ access key, session token, OAuth token hoặc credential tạm thời để tránh lấy lại cho mọi request.
- **HTTP transport:** Thực hiện request HTTP/HTTPS, quản lý socket, TLS và giao thức mạng.
- **Connection pool:** Tái sử dụng kết nối, giới hạn số kết nối đồng thời và quản lý kết nối nhàn rỗi.
- **Retry và timeout policy:** Quyết định khi nào gửi lại request, thời gian chờ và cách xử lý lỗi.
- **Executor/event loop:** Chạy request bất đồng bộ, callback hoặc tác vụ nội bộ.
- **Endpoint và region resolver:** Xác định địa chỉ dịch vụ, region, proxy hoặc endpoint tùy chỉnh.
- **Metrics, tracing và signer:** Đo lường request, ký request và gắn metadata bảo mật.

~~~text
Mã nghiệp vụ
    |
    v
Cloud SDK client
    |
    +---- Credential provider
    |         |
    |         +---- Credential/token cache
    |         +---- Metadata / STS / OAuth / workload identity
    |
    +---- Request signer
    |
    +---- Retry / timeout / endpoint resolver
    |
    +---- HTTP transport
              |
              +---- Connection pool
              +---- DNS / TLS / socket
              +---- Executor / event loop
    |
    v
Dịch vụ đám mây
~~~

Không phải SDK nào cũng có đúng cấu trúc này. Một số thành phần được tích hợp trong client; một số được chia sẻ giữa nhiều client; một số được cung cấp bởi thư viện HTTP bên ngoài. Khi lập kế hoạch CRaC, hãy dùng tài liệu và dependency tree của đúng SDK version để xác định ranh giới sở hữu.

## 2. SDK client thường nên sống lâu hơn một request

Nhiều SDK client Java được thiết kế để tái sử dụng giữa các thread và request. Tạo một client mới cho mỗi lần gọi có thể làm tăng chi phí khởi tạo, DNS lookup, TLS handshake, tạo pool và lấy credential. Mô hình thường dùng là tạo client theo application lifecycle hoặc theo cấu hình endpoint/region, sau đó inject client vào service.

Ví dụ về cách tổ chức bean:

~~~java
@Configuration
public class CloudClientConfiguration {
    @Bean(destroyMethod = "close")
    public ObjectStorageClient objectStorageClient() {
        return ObjectStorageClient.builder()
                .region(Region.of("ap-southeast-1"))
                .build();
    }
}
~~~

ObjectStorageClient và Region trong ví dụ là tên minh họa, không phải API của một SDK cụ thể. Với SDK thực tế, hãy dùng builder và phương thức đóng được tài liệu của nhà cung cấp hỗ trợ.

Không nên tạo client mới cho mỗi request nếu SDK được thiết kế để chia sẻ. Cũng không nên giữ một client singleton mãi mãi mà không quản lý việc đóng, thay thế hoặc phục hồi khi môi trường thay đổi. Với CRaC, singleton vẫn có vòng đời riêng: client có thể cần được giữ lại, làm mới một phần, đóng và tạo lại, hoặc được thư viện tự xử lý bằng integration chính thức.

## 3. Credential provider là gì?

Credential provider là thành phần chịu trách nhiệm cung cấp thông tin xác thực cho request. Mã nghiệp vụ thường không nên tự đọc access key rồi ghép vào từng request. Thay vào đó, SDK hỏi provider khi cần ký request hoặc xác thực với dịch vụ.

Nguồn credential phổ biến:

| Nguồn | Cách hoạt động | Điểm cần chú ý |
|---|---|---|
| Environment variables | Đọc giá trị từ biến môi trường | Secret có thể bị cố định trong container hoặc ảnh checkpoint |
| Profile/configuration file | Đọc file cấu hình trên máy hoặc container | Đường dẫn, quyền và nội dung file có thể thay đổi |
| Instance/pod metadata | Lấy credential từ metadata endpoint của môi trường chạy | Endpoint và token truy cập metadata phụ thuộc runtime |
| Workload identity | Đổi identity của workload lấy credential tạm thời | Token exchange và trust policy cần hoạt động sau restore |
| STS/role assumption | Yêu cầu session credential có thời hạn | Credential cần refresh trước khi hết hạn |
| OAuth/OIDC provider | Lấy access token từ authorization server | Refresh token, client assertion và token cache có lifecycle riêng |
| Secret manager | Đọc secret từ dịch vụ quản lý bí mật | Secret có thể được rotate hoặc policy có thể thay đổi |

Provider có thể trả về credential tĩnh hoặc credential tạm thời. Credential tạm thời thường có thời điểm hết hạn và có thể được làm mới tự động. Một provider có thể giữ cache để tránh gọi metadata service hoặc STS quá thường xuyên.

## 4. Credential chain và thứ tự lựa chọn identity

Một số SDK cung cấp default credential chain. Chain thử nhiều nguồn theo thứ tự cho đến khi tìm thấy credential hợp lệ. Thứ tự cụ thể phụ thuộc SDK, phiên bản và môi trường. Ví dụ khái quát:

~~~text
Environment credentials
        |
        v
Profile / shared config
        |
        v
Workload identity / web identity
        |
        v
Container credentials endpoint
        |
        v
Instance metadata credentials
        |
        v
Credential provider được cấu hình riêng
~~~

Sơ đồ chỉ mô tả một kiểu chain minh họa. Không phải mọi SDK đều có các bước này hoặc cùng thứ tự. Cần đọc tài liệu của provider đang dùng.

Credential chain có thể chọn nguồn khác sau restore nếu môi trường đã thay đổi. Ví dụ, một tiến trình được tạo checkpoint trên máy build có thể nhìn thấy file profile của máy đó; sau restore trong container production, file profile có thể không tồn tại hoặc identity mong muốn đến từ workload identity. Nếu chain đã cache credential hoặc đã chọn provider ở thời điểm khởi động, thay đổi môi trường không nhất thiết làm chain tự chọn lại nguồn.

Vì vậy, hãy xác định identity mong muốn cho từng môi trường. Với workload trên cloud, ưu tiên cơ chế identity gắn với workload hoặc role được nhà cung cấp khuyến nghị, thay vì đóng gói access key dài hạn vào image. Kiểm tra provider có thể resolve lại credential sau restore hay cần được tạo mới.

## 5. Credential tạm thời và thời hạn token

Credential tạm thời thường gồm một định danh, secret hoặc access token, session token và thời điểm hết hạn. Provider có thể cache credential trong bộ nhớ và chỉ refresh khi gần hết hạn.

Ví dụ:

~~~text
Credential hiện tại
  issuedAt  = 10:00
  expiresAt = 11:00

Checkpoint được tạo lúc 10:20
Ảnh được lưu đến 12:30
Restore lúc 12:30

Credential trong heap: đã hết hạn
Credential cần dùng: lấy mới từ provider/identity service
~~~

Nếu request đầu tiên sau restore dùng credential đã hết hạn, SDK có thể trả lỗi xác thực. Một số provider tự refresh khi phát hiện credential sắp hết hạn; một số chỉ refresh khi được gọi; một số cần executor hoặc background refresh thread. Hành vi chính xác phụ thuộc provider.

Không nên giả định mọi credential provider đều tự refresh ngay sau restore. Cần kiểm tra:

- Provider có lưu thời điểm hết hạn không?
- Cache có kiểm tra expiration trước khi trả credential không?
- Có refresh trước một khoảng safety window không?
- Refresh được kích hoạt bởi request hay background task?
- Có cần một executor riêng để refresh không?
- Khi refresh timeout, provider trả credential cũ hay báo lỗi?
- Có cách buộc provider resolve lại credential hoặc tạo provider mới không?

Nếu SDK cung cấp API refresh, reload hoặc close cho provider, hãy dùng đúng API được tài liệu hỗ trợ. Nếu không, có thể cần tạo provider mới sau restore và thay provider/client theo lifecycle của ứng dụng.

## 6. Không đóng gói secret dài hạn vào checkpoint

Checkpoint có thể chứa dữ liệu trong heap và trạng thái runtime. Nếu credential, access token, refresh token hoặc private key đã được nạp vào bộ nhớ trước checkpoint, chúng có thể xuất hiện trong ảnh tùy cơ chế và phạm vi checkpoint.

Ảnh checkpoint vì vậy cần được bảo vệ như dữ liệu có thể chứa secret. Hạn chế quyền đọc, mã hóa khi lưu và truyền, kiểm soát thời gian lưu, ghi nhận truy cập và xóa artifact theo chính sách. Không ghi credential vào log để chẩn đoán lỗi restore.

Một số nguyên tắc thiết kế:

- Ưu tiên workload identity hoặc role credential tạm thời.
- Tránh đưa secret dài hạn vào biến môi trường khi có phương án cấp credential an toàn hơn.
- Không tạo checkpoint khi không cần thiết phải giữ credential trong heap.
- Làm mới credential sau restore nếu token có thể hết hạn hoặc identity phụ thuộc instance.
- Không dùng một token được snapshot làm identity chung cho nhiều replica.
- Giới hạn quyền truy cập checkpoint artifact và quy trình phân phối.
- Nếu secret đã bị lộ qua artifact, xử lý như một sự cố credential: thu hồi hoặc rotate theo chính sách của nhà cung cấp.

Credential provider và credential value là hai thứ khác nhau. Có thể giữ một đối tượng provider nếu nó có thể resolve lại credential an toàn; điều đó không có nghĩa nên giữ nguyên credential đã cache bên trong provider.

## 7. Workload identity và metadata service

Trên nền tảng đám mây, ứng dụng thường lấy credential từ metadata service hoặc identity endpoint gắn với máy ảo, container hay workload. Provider gửi request đến endpoint nội bộ để nhận credential tạm thời.

Khi restore, endpoint metadata hoặc token bảo vệ metadata có thể phụ thuộc network namespace, địa chỉ link-local, container identity hoặc node hiện tại. Một request đã được chuẩn bị trước checkpoint có thể không còn phù hợp sau restore.

Cần kiểm tra:

- SDK/provider có hỗ trợ loại workload identity đang triển khai không.
- Metadata endpoint có được truy cập từ container sau restore không.
- Token cần để gọi metadata endpoint có được làm mới không.
- Có proxy hoặc network policy ảnh hưởng đến endpoint nội bộ không.
- Identity sau restore có đúng service account/role mong muốn không.
- Provider có cache endpoint hoặc credential theo instance cũ không.

Không hardcode metadata endpoint của một cloud provider nếu SDK đã cung cấp provider phù hợp. Endpoint và yêu cầu bảo mật có thể khác theo nền tảng, region và cấu hình. Dùng integration chính thức và xác minh bằng một thao tác lấy credential không gây side effect.

## 8. Token refresh và background refresh thread

Một số credential provider làm mới token nền trước khi hết hạn. Cách này giúp request không phải chờ token exchange. Tuy nhiên, thread refresh có thể đang chạy, đang chờ hoặc giữ socket khi checkpoint xảy ra.

Trước checkpoint, cần biết:

- Provider có background refresh scheduler hay không.
- Có refresh operation đang chạy không.
- Có request metadata/STS/OAuth đang chờ không.
- Có thể pause refresh thread theo API chính thức không.
- Có cần đóng provider hoặc executor không.
- Provider có thể khởi động lại sau restore hay phải tạo mới?

Sau restore, không nên dựa vào một timer đã được lưu từ trước để quyết định thời điểm refresh. Tiến trình có thể đã dừng lâu hơn token lifetime. Hãy để provider kiểm tra expiration theo thời gian hiện tại và buộc resolve mới nếu API hỗ trợ.

Nếu provider không có CRaC integration, một adapter do ứng dụng sở hữu có thể ngừng việc refresh mới, chờ refresh đang chạy kết thúc, sau đó đóng hoặc đánh dấu provider cần tạo lại. Không gọi các phương thức private bằng reflection để điều khiển scheduler nội bộ.

## 9. HTTP connection pool là gì?

HTTP connection pool quản lý các kết nối mạng có thể tái sử dụng giữa nhiều request. Thay vì mở TCP connection và TLS handshake cho mỗi request, client mượn một kết nối có sẵn, gửi request, rồi trả kết nối về pool.

Một pool thường quản lý:

- Số lượng kết nối tối đa.
- Số kết nối nhàn rỗi và thời gian giữ idle.
- Thời gian chờ lấy connection.
- Thời gian connect và socket read/write timeout.
- Keep-alive và connection reuse.
- Health/validation của kết nối.
- HTTP/1.1 connection hoặc HTTP/2 connection/stream.
- Thread, event loop và callback cho I/O bất đồng bộ.

Pool giúp tăng hiệu năng nhưng giữ trạng thái gắn với mạng. Một socket có thể bị server, load balancer, NAT hoặc firewall đóng khi tiến trình đang checkpoint. Khi restore, object connection vẫn có thể còn trong heap nhưng kết nối vật lý đã chết hoặc không còn phù hợp.

## 10. Vì sao connection pool có thể stale sau restore?

Giả sử một SDK client đang có 20 kết nối nhàn rỗi. Ứng dụng tạo checkpoint và tiến trình dừng trong 45 phút. Trong thời gian đó:

- Server có thể đóng keep-alive connection.
- NAT hoặc firewall có thể xóa mapping.
- Load balancer có thể thay backend.
- DNS có thể thay đổi địa chỉ.
- TLS session hoặc certificate có thể hết hạn hoặc bị rotate.
- Proxy có thể thay đổi hoặc yêu cầu xác thực lại.
- Cloud endpoint có thể chuyển vùng hoặc thay đổi route.

Sau restore, pool có thể trả ra một connection mà client nghĩ là còn mở. Request đầu tiên có thể gặp connection reset, broken pipe, EOF, timeout hoặc lỗi TLS.

Một số HTTP client có kiểm tra connection stale, idle eviction hoặc tự loại kết nối lỗi. Nhưng không nên giả định mọi pool đều phát hiện được mọi tình huống. Cần đọc tài liệu HTTP transport và kiểm thử bằng đúng phiên bản SDK.

## 11. Ai sở hữu HTTP transport và connection pool?

Một SDK client có thể tự tạo HTTP transport mặc định, hoặc nhận một HTTP client/transport được ứng dụng chia sẻ. Ranh giới ownership ảnh hưởng trực tiếp đến việc đóng và tạo lại.

| Mô hình | Owner thường gặp | Điều cần lưu ý |
|---|---|---|
| SDK tự tạo transport | SDK client | Đóng client có thể đóng luôn transport và pool |
| Ứng dụng truyền shared transport | Ứng dụng hoặc bean cấu hình | Đóng một SDK client có thể không được phép đóng transport dùng chung |
| Nhiều SDK client dùng chung transport | Component cấu hình transport | Phải đóng các client trước, rồi mới đóng transport theo thứ tự |
| Async SDK dùng event loop riêng | SDK hoặc executor owner | Cần drain request và xử lý thread/event loop |
| HTTP transport do framework quản lý | Spring/container hoặc integration | Tuân theo lifecycle của framework, tránh close trùng |

Không gọi close() ở nhiều nơi trên cùng một transport nếu ownership chưa rõ. Một client có thể chỉ mượn transport do ứng dụng sở hữu; một client khác có thể tự sở hữu transport. Xác định hợp đồng close/dispose trong tài liệu SDK và HTTP library.

## 12. Lựa chọn giữ, làm mới hay tạo lại client

Không có một hành động duy nhất phù hợp với mọi SDK. Có thể chia thành ba nhóm:

| Chiến lược | Khi phù hợp | Việc cần xác minh |
|---|---|---|
| Giữ client và để SDK tự phục hồi | SDK/transport có CRaC support hoặc tài liệu xác nhận xử lý socket/token sau restore | Tính tương thích, callback tích hợp và kiểm thử lỗi kết nối |
| Giữ client, làm mới credential và loại connection stale | Client/provider có API refresh hoặc pool có API phục hồi được hỗ trợ | Thread safety, trạng thái request đang chạy và thứ tự refresh |
| Đóng client/transport và tạo client mới | SDK hoặc transport không hỗ trợ tiếp tục với tài nguyên cũ, hoặc tài liệu khuyến nghị tạo lại | Owner, client replacement atomically, request gate và cleanup |

Không nên đóng client một cách tùy tiện trong callback nếu SDK integration đã tự quản lý nó. Ngược lại, cũng không nên giữ nguyên client chỉ vì object vẫn còn tồn tại. Chọn chiến lược theo tài liệu của đúng SDK version và HTTP transport.

## 13. Trước checkpoint: dừng request và drain SDK call

Một request cloud có thể đang upload object, ghi message, tạo resource hoặc chờ response. Nếu checkpoint xảy ra giữa thao tác, kết quả phía dịch vụ có thể không rõ ràng.

Một quy trình quiesce có thể gồm:

1. Ngừng nhận request mới hoặc ngừng giao job mới cho worker.
2. Chờ các SDK call đang chạy hoàn tất trong giới hạn thời gian.
3. Hủy hoặc đưa các thao tác dài về trạng thái có thể retry nếu không thể chờ.
4. Xử lý upload multipart, stream body và response body đang mở.
5. Chờ credential refresh đang chạy kết thúc hoặc dừng theo API provider.
6. Đóng client/transport nếu chiến lược yêu cầu.
7. Xác nhận không còn thao tác đang sử dụng pool hoặc credential provider.
8. Chỉ cho phép checkpoint khi các owner báo sẵn sàng.

Không nên chỉ chờ thread HTTP kết thúc mà bỏ qua callback bất đồng bộ, stream hoặc future chưa hoàn tất. Một SDK call có thể trả về CompletableFuture trong khi request vẫn đang chạy. Cần theo dõi các operation đang active ở tầng ứng dụng.

## 14. Sau restore: refresh identity trước khi mở traffic

Sau restore, thứ tự phục hồi thường là:

1. Đọc lại identity và cấu hình phụ thuộc instance.
2. Resolve credential mới hoặc buộc provider refresh.
3. Tạo lại HTTP transport/connection pool nếu cần.
4. Tạo lại SDK client nếu client cũ đã đóng hoặc không được hỗ trợ.
5. Thực hiện health check nhẹ, không tạo side effect.
6. Mở worker và ingress sau khi dependency sẵn sàng.

Nếu SDK client phụ thuộc credential provider, provider cần sẵn sàng trước khi client phát request. Nếu client được xây dựng với provider reference có thể refresh, có thể giữ client theo thiết kế; nếu client giữ credential snapshot bất biến, có thể phải tạo lại client.

Không phải mọi SDK đều lấy credential ở mỗi request. Một số ký request bằng provider động; một số lưu credential trong signer hoặc cấu hình client; một số dùng token cache nội bộ. Hãy kiểm tra cách SDK cụ thể lấy credential để quyết định có cần rebuild client.

## 15. Ví dụ: quản lý SDK client bằng factory có thể thay thế

Một thiết kế tổng quát là đặt client trong một holder do ứng dụng sở hữu. Holder chịu trách nhiệm tạo, thay thế và đóng client. Mã nghiệp vụ lấy client hiện tại thông qua holder.

~~~java
public interface CloudClient extends AutoCloseable {
    void healthCheck() throws Exception;

    @Override
    void close() throws Exception;
}

public interface CloudClientFactory {
    CloudClient createWithCurrentIdentity() throws Exception;
}

public final class CloudClientHolder {
    private final CloudClientFactory factory;
    private volatile CloudClient current;

    public CloudClientHolder(CloudClientFactory factory) {
        this.factory = factory;
    }

    public synchronized void initialize() throws Exception {
        if (current == null) {
            current = factory.createWithCurrentIdentity();
        }
    }

    public CloudClient current() {
        CloudClient client = current;
        if (client == null) {
            throw new IllegalStateException("Cloud client is not ready");
        }
        return client;
    }

    public synchronized void replace() throws Exception {
        CloudClient replacement = factory.createWithCurrentIdentity();
        try {
            replacement.healthCheck();
        } catch (Exception ex) {
            replacement.close();
            throw ex;
        }

        CloudClient previous = current;
        current = replacement;

        if (previous != null) {
            previous.close();
        }
    }

    public synchronized void closeCurrent() throws Exception {
        CloudClient previous = current;
        current = null;
        if (previous != null) {
            previous.close();
        }
    }
}
~~~

Đây là abstraction minh họa. Client thực tế có thể không khai báo AutoCloseable, có thể dùng close() không ném checked exception hoặc có transport được chia sẻ. Hãy điều chỉnh theo API thật. Ví dụ cũng cần request gate hoặc reference management nếu có request đang sử dụng client cũ trong lúc replace; không đóng client cũ trước khi các operation đã drain.

Một holder thay thế client giúp ứng dụng không cần khởi tạo lại toàn bộ Spring ApplicationContext. Tuy nhiên, mọi service phải dùng holder hoặc một proxy ổn định; nếu service giữ trực tiếp reference đến client cũ, việc thay holder không cập nhật reference đó.

## 16. Ví dụ CRaC Resource cho cloud client

Resource có thể phối hợp lifecycle của holder. Ví dụ dưới đây giả định ứng dụng đã có request gate để ngăn thao tác mới và chờ operation đang chạy kết thúc.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public final class CloudClientCracResource implements Resource {
    private final CloudRequestGate requestGate;
    private final CloudClientHolder clientHolder;
    private final CredentialLifecycle credentials;

    public CloudClientCracResource(
            CloudRequestGate requestGate,
            CloudClientHolder clientHolder,
            CredentialLifecycle credentials) {
        this.requestGate = requestGate;
        this.clientHolder = clientHolder;
        this.credentials = credentials;
    }

    @PostConstruct
    public void register() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        requestGate.stopNewCalls();
        requestGate.awaitInFlightCalls();
        credentials.stopRefreshAndWait();
        clientHolder.closeCurrent();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        credentials.resolveFreshIdentity();
        clientHolder.initialize();
        clientHolder.current().healthCheck();
    }

    public interface CloudRequestGate {
        void stopNewCalls() throws Exception;
        void awaitInFlightCalls() throws Exception;
    }

    public interface CredentialLifecycle {
        void stopRefreshAndWait() throws Exception;
        void resolveFreshIdentity() throws Exception;
    }
}
~~~

Các interface CloudRequestGate và CredentialLifecycle là abstraction do ứng dụng định nghĩa, không phải API chuẩn của Spring hoặc CRaC. Ví dụ thể hiện thứ tự logic: drain request, dừng refresh, đóng client trước checkpoint; sau restore resolve identity, tạo client và kiểm tra kết nối.

Trong ứng dụng thật, cần xác định ai sở hữu credential provider và transport. Nếu client tự sở hữu provider hoặc transport, đóng client có thể đóng chúng. Nếu provider hoặc transport được chia sẻ, phải quản lý theo đúng owner và thứ tự. Nếu SDK có CRaC integration chính thức, dùng integration đó và tránh đăng ký callback trùng.

Cũng cần có đường xử lý khi checkpoint bị hủy sau khi beforeCheckpoint() đã đóng client. Ứng dụng cần biết cách mở lại client nếu tiến trình tiếp tục chạy mà không restore. Lifecycle cụ thể phụ thuộc cách runtime và framework phát tín hiệu checkpoint failure/cancel; không giả định rằng callback đóng client sẽ luôn được theo sau bởi restore.

## 17. Quản lý credential provider riêng với client

Credential provider có thể sống lâu hơn một client và được chia sẻ giữa nhiều client. Ví dụ, một provider cấp credential cho object storage, queue và secret manager. Nếu mỗi client tự tạo provider riêng, refresh và cache có thể bị nhân đôi; nếu dùng provider chung, việc đóng provider phải được quản lý ở đúng owner.

Một abstraction ứng dụng có thể biểu diễn:

~~~java
public interface CredentialLifecycle {
    void stopRefreshAndWait() throws Exception;
    void resolveFreshIdentity() throws Exception;
    void verifyIdentity() throws Exception;
}
~~~

resolveFreshIdentity() có thể thực hiện một trong các cách sau, tùy SDK:

- Yêu cầu provider làm mới credential theo API được hỗ trợ.
- Tạo provider mới từ cấu hình hiện tại.
- Xóa cache token theo API công khai.
- Gọi identity service hoặc metadata provider để xác nhận role hiện tại.
- Tạo lại client nếu client không thể nhận provider mới.

Không nên tự xóa field private trong provider hoặc signer. Các cache nội bộ có thể có đồng bộ và invariants riêng; sửa bằng reflection có thể làm provider rơi vào trạng thái lỗi.

Nếu provider có thread refresh, hãy dừng nó theo API được hỗ trợ và chờ operation đang chạy. Nếu provider không có API lifecycle, có thể để provider được giữ lại chỉ khi tài liệu xác nhận nó tự kiểm tra expiration và refresh đúng sau restore. Cần kiểm thử thay vì giả định.

## 18. Connection pool và cấu hình HTTP cần xem xét

Một HTTP transport có thể cho phép cấu hình các giới hạn sau:

| Cấu hình | Ý nghĩa | Ảnh hưởng đến restore |
|---|---|---|
| Max connections | Giới hạn kết nối đồng thời | Tránh quá tải endpoint khi nhiều instance restore |
| Max idle connections | Số kết nối nhàn rỗi được giữ | Kết nối cũ có thể stale trong ảnh |
| Idle timeout | Thời gian giữ kết nối nhàn rỗi | Cần phù hợp với keep-alive của server/proxy |
| Connection TTL | Tuổi tối đa của connection | Giúp loại connection lâu năm |
| Connect timeout | Thời gian thiết lập TCP/TLS | Tránh restore chờ vô hạn |
| Read/write timeout | Thời gian chờ I/O | Kiểm soát request treo |
| Retry policy | Cách thử lại request | Có thể gây side effect lặp nếu request không idempotent |
| DNS cache TTL | Thời gian cache kết quả DNS | Endpoint có thể thay đổi trong thời gian checkpoint |
| TLS/session cache | Trạng thái bắt tay và xác thực TLS | Có thể cần handshake lại hoặc refresh trust material |

Các giá trị phù hợp phụ thuộc tải, dịch vụ và HTTP implementation. Đừng đặt max connections quá cao chỉ để giảm queue time; khi nhiều replica restore đồng thời, tổng số kết nối có thể vượt quota dịch vụ.

Nếu nhiều SDK client dùng chung một HTTP transport, hãy tính tổng request concurrency. Một pool có thể là bottleneck chung hoặc một điểm lỗi chung. Với CRaC, cần biết pool có thể được giữ, evict stale connections hoặc phải tạo lại.

## 19. DNS, TLS, proxy và endpoint sau restore

Kết nối không chỉ phụ thuộc socket. SDK còn có thể cache endpoint, DNS result, TLS session, certificate chain và proxy configuration.

Sau một khoảng checkpoint dài:

- DNS record có thể đã đổi.
- Endpoint regional có thể được cấu hình lại.
- Proxy có thể yêu cầu credential mới.
- CA bundle hoặc certificate có thể được rotate.
- TLS session cache có thể không còn phù hợp.
- Service discovery có thể trả địa chỉ mới.
- Network policy hoặc route có thể thay đổi.

Không nên hardcode giả định rằng địa chỉ endpoint đã resolve trước checkpoint vẫn còn hợp lệ. Dùng endpoint resolver và DNS behavior được hỗ trợ. Nếu cấu hình endpoint có thể thay đổi, cần đọc lại hoặc tạo client mới sau restore.

Khi kiểm thử, hãy quan sát cả trường hợp connection pool rỗng và trường hợp có nhiều idle connection trong checkpoint. Một request thành công nhờ retry tự động không nhất thiết chứng minh connection cũ được phục hồi; cần quan sát metric và log của transport để biết pool đã loại bỏ stale connection hay chưa.

## 20. Retry, timeout và idempotency cho request cloud

Checkpoint có thể xảy ra khi request đang gửi hoặc chờ response. Phía dịch vụ có thể đã thực hiện thao tác nhưng response chưa về đến client. Nếu restore rồi retry, thao tác có thể bị lặp.

Ví dụ, request tạo resource đã đến cloud API và server đã tạo thành công, nhưng client bị checkpoint trước khi nhận response. Sau restore, ứng dụng không biết kết quả và gửi lại request. Nếu API không có idempotency key hoặc cơ chế tra cứu trạng thái, resource có thể được tạo hai lần.

Nguyên tắc:

- Không checkpoint khi còn request có side effect chưa xác định kết quả nếu có thể drain.
- Dùng idempotency token/request ID nếu API hỗ trợ.
- Lưu operation ID và trạng thái tiến độ ở nơi bền vững.
- Với upload multipart, lưu upload ID và part state theo hợp đồng dịch vụ; không chỉ giữ trong heap.
- Phân biệt lỗi kết nối trước khi gửi với timeout sau khi gửi.
- Giới hạn retry và dùng backoff/jitter.
- Không retry tự động thao tác không idempotent nếu không biết kết quả lần trước.

Retry policy trong SDK có thể che giấu một số lỗi connection stale, nhưng không thay thế idempotency nghiệp vụ. Hãy kiểm tra cách SDK phân loại retryable exception và cách nó xử lý request body có thể replay hay không.

## 21. Restore nhiều replica từ cùng checkpoint

Nếu một checkpoint được dùng làm mẫu cho nhiều instance, mỗi replica có thể bắt đầu với cùng credential cache, endpoint cache và trạng thái connection pool trong heap. Đây là lý do cần tách trạng thái nền dùng chung khỏi trạng thái theo instance.

Sau restore, mỗi replica cần:

- Có identity riêng từ workload environment.
- Resolve credential đúng role/service account của replica.
- Không dùng một token ngắn hạn được snapshot làm credential chung.
- Tạo connection pool riêng hoặc dùng transport được thiết kế chia sẻ theo cách an toàn.
- Không chia sẻ socket hoặc file descriptor theo giả định không được nền tảng bảo đảm.
- Có client ID riêng nếu SDK/service yêu cầu.
- Giới hạn đồng thời quá trình refresh token và khởi tạo connection để tránh thundering herd.
- Chỉ báo ready sau khi identity và client được xác minh.

Nếu 50 replica cùng restore và cùng gọi STS hoặc metadata endpoint ngay lập tức, hệ thống identity có thể bị tải đột biến. Có thể thêm jitter, giới hạn concurrency, cache được thiết kế phù hợp hoặc khởi tạo theo đợt. Không dùng cùng một credential cache trong heap làm cơ chế phối hợp giữa replica.

## 22. Bảo mật khi xử lý checkpoint và cloud credential

Checkpoint có thể chứa token, credential, request header, payload hoặc dữ liệu nhạy cảm đang nằm trong heap. Cần áp dụng kiểm soát tương ứng:

- Hạn chế quyền đọc/ghi checkpoint artifact.
- Mã hóa artifact khi lưu và truyền nếu nền tảng yêu cầu.
- Dùng secret manager hoặc workload identity để cấp credential sau restore.
- Tránh log access key, bearer token, session token, private key hoặc header Authorization.
- Xác định thời hạn lưu checkpoint và xóa artifact cũ theo chính sách.
- Rotate/revoke credential nếu nghi ngờ artifact đã bị truy cập trái phép.
- Phân quyền riêng cho thao tác tạo, restore, tải xuống và xóa checkpoint.
- Không đưa dữ liệu người dùng hoặc payload nghiệp vụ thật vào warm-up chỉ để làm nóng SDK.

Nếu cần kiểm tra credential sau restore, log identity name/role đã được phép công khai, expiration hoặc trạng thái hợp lệ; không log giá trị secret. Có thể gọi API identity introspection hoặc một thao tác đọc an toàn với quyền tối thiểu.

## 23. Quy trình tích hợp cloud SDK với CRaC

Một quy trình triển khai có thể chia thành các bước:

### Bước 1: Lập inventory

Liệt kê mọi SDK client, credential provider, token cache, HTTP transport, connection pool, executor và background refresh thread. Với mỗi thành phần, ghi creator, owner, consumer và API close/refresh/rebuild.

### Bước 2: Xác nhận CRaC support

Kiểm tra JDK distribution, SDK version, HTTP client version và tài liệu nhà cung cấp. Xác định thành phần nào có CRaC integration chính thức và thành phần nào cần adapter.

### Bước 3: Chọn identity strategy

Xác định nguồn credential ở build, test, staging và production. Ưu tiên workload identity hoặc credential tạm thời. Xác định cách resolve lại identity sau restore và cách tránh dùng token cũ.

### Bước 4: Thiết kế request gate

Ngừng nhận request mới, theo dõi SDK call đang chạy, drain future/stream/upload và xử lý operation có kết quả không xác định. Không chỉ đếm thread đồng bộ.

### Bước 5: Quản lý credential và transport

Theo owner, dừng refresh task, làm mới hoặc tạo lại provider, đóng/rebuild client và connection pool nếu cần. Không đóng shared transport từ nhiều owner.

### Bước 6: Tạo checkpoint

Chỉ cho phép checkpoint sau khi request gate và mọi resource owner xác nhận trạng thái an toàn. Bảo vệ artifact như dữ liệu có thể chứa credential.

### Bước 7: Restore và xác minh

Resolve identity mới, tạo hoặc phục hồi transport, health check với thao tác không gây side effect, kiểm tra readiness rồi mới mở traffic.

### Bước 8: Kiểm thử lỗi và tải

Thử token hết hạn, metadata endpoint không sẵn sàng, DNS đổi, socket stale, request timeout, callback lỗi và nhiều replica restore đồng thời.

## 24. Ví dụ cấu hình theo môi trường

Một cấu hình có thể tách thông tin không bí mật khỏi credential:

~~~yaml
cloud:
  region: ap-southeast-1
  endpoint: https://storage.example.internal
  identity:
    mode: workload
  http:
    max-connections: 100
    connection-timeout: 3s
    read-timeout: 10s
    idle-timeout: 30s
~~~

Đây là cấu trúc cấu hình minh họa; tên property và cách bind phụ thuộc ứng dụng. Không đặt access key hoặc refresh token trực tiếp trong file YAML được đóng gói vào image. Credential nên được cấp từ identity provider hoặc secret manager theo chính sách môi trường.

Với Spring Boot, có thể bind cấu hình không bí mật vào ConfigurationProperties, còn credential provider và client được tạo bởi bean factory. Nếu endpoint hoặc identity thay đổi sau restore, cần có lifecycle để cập nhật cấu hình/client hoặc tạo bean holder mới. Không nên giả định Spring tự bind lại toàn bộ Environment khi tiến trình restore.

## 25. Quan sát và chẩn đoán sau restore

Để biết SDK đã phục hồi đúng, cần theo dõi các lớp riêng:

| Chỉ số/log | Điều cần quan sát |
|---|---|
| Credential resolve duration | Thời gian lấy identity/credential sau restore |
| Credential refresh success/failure | Provider có refresh thành công không |
| Credential expiration margin | Còn bao lâu trước khi token hết hạn |
| HTTP pool active/idle/pending | Pool có kết nối và hàng đợi bất thường không |
| Connection creation/reuse | Có tạo kết nối mới hay dùng lại connection cũ |
| DNS resolution | Endpoint được resolve thành địa chỉ nào |
| TLS handshake failures | Certificate hoặc session có vấn đề không |
| SDK request latency/error | Request đầu tiên và request sau restore |
| Retry count | Có nhiều retry do stale socket hoặc timeout không |
| In-flight request count | Có request chưa drain khi chuẩn bị checkpoint không |
| Client rebuild count | Client/transport được tạo lại bao nhiêu lần |

Gắn restore ID và instance ID vào log/metric để phân biệt các replica. Không ghi secret hoặc payload nhạy cảm. Khi request đầu tiên lỗi, phân loại lỗi xác thực, DNS, TLS, connection reset, timeout và service-side error trước khi thay đổi retry policy.

## 26. Kiểm thử cloud SDK sau checkpoint/restore

Một bộ kiểm thử nên dùng đúng JDK CRaC, SDK version, HTTP transport và môi trường identity dự kiến triển khai.

### Kiểm thử credential hết hạn

1. Dùng credential tạm thời có TTL ngắn trong môi trường test.
2. Khởi chạy ứng dụng và xác nhận provider lấy được credential.
3. Tạo checkpoint.
4. Chờ đến khi credential cũ hết hạn.
5. Restore.
6. Gọi một API đọc an toàn.
7. Xác nhận provider lấy credential mới và request thành công.

### Kiểm thử connection pool stale

1. Tạo một số kết nối nhàn rỗi bằng workload test.
2. Tạo checkpoint khi pool có connection idle.
3. Trong lúc tiến trình dừng, đóng kết nối phía server hoặc để proxy/NAT hết thời gian idle.
4. Restore và gửi request.
5. Xác nhận transport phát hiện connection lỗi, loại bỏ và tạo kết nối mới theo policy.
6. Kiểm tra retry không tạo side effect trùng.

### Kiểm thử request đang chạy

1. Gửi request cloud có thời gian xử lý đủ dài.
2. Bắt đầu quy trình quiesce.
3. Xác nhận request hoàn tất hoặc bị hủy theo chính sách.
4. Tạo checkpoint.
5. Restore và kiểm tra không có operation bị thực hiện lặp ngoài dự kiến.

### Kiểm thử workload identity

1. Chạy ứng dụng với identity được cấp bởi môi trường test.
2. Tạo checkpoint.
3. Thay đổi hoặc rotate credential/role theo kịch bản kiểm thử.
4. Restore.
5. Xác nhận ứng dụng resolve identity theo cấu hình hiện tại.
6. Kiểm tra quyền truy cập tối thiểu vẫn đúng.

### Kiểm thử nhiều replica

1. Tạo một checkpoint nền không chứa side effect và identity riêng của instance.
2. Restore nhiều replica.
3. Xác nhận mỗi replica có identity phù hợp.
4. Đo tải lên metadata/STS/secret service.
5. Kiểm tra pool và số kết nối không vượt quota.
6. Xác nhận không có token hoặc client identity bị chia sẻ ngoài thiết kế.

## 27. Những lỗi thường gặp

**Giữ nguyên credential đã cache trong checkpoint.** Token có thể hết hạn hoặc identity không còn đúng. Resolve lại credential sau restore theo provider được hỗ trợ.

**Đưa access key dài hạn vào ảnh checkpoint.** Artifact có thể chứa secret. Ưu tiên workload identity và bảo vệ checkpoint như dữ liệu nhạy cảm.

**Cho rằng SDK client còn trong heap là còn dùng được.** Socket hoặc TLS session có thể stale. Kiểm tra integration và phục hồi transport.

**Tạo client mới cho mọi request.** Điều này lãng phí pool và handshake. Dùng client theo application lifecycle, có cơ chế replace khi cần.

**Đóng shared transport từ nhiều client.** Một client có thể làm hỏng client khác đang dùng chung pool. Gán owner duy nhất và đóng theo thứ tự.

**Để refresh thread chạy qua checkpoint mà không kiểm tra.** Task refresh có thể đang dở hoặc timer cũ. Dùng API lifecycle của provider hoặc tạo lại provider.

**Chỉ health check bằng cách kiểm tra object khác null.** Object tồn tại không chứng minh identity, network hoặc endpoint hoạt động. Thực hiện một thao tác xác minh an toàn.

**Retry mọi lỗi request.** Timeout có thể xảy ra sau khi dịch vụ đã thực hiện side effect. Dùng idempotency key và tra cứu operation state.

**Mở traffic trước khi client sẵn sàng.** Request đầu tiên có thể thất bại hàng loạt. Readiness phải chờ credential và transport được xác minh.

**Restore nhiều replica cùng refresh ngay lập tức.** Có thể tạo thundering herd lên metadata/STS. Dùng jitter, giới hạn concurrency và rollout theo đợt.

**Giả định mọi SDK hỗ trợ CRaC giống nhau.** Client, credential provider và HTTP transport có version/lifecycle riêng. Kiểm tra tài liệu đúng dependency version.

## 28. Checklist tích hợp SDK đám mây với CRaC

- [ ] Đã liệt kê SDK client, credential provider, token cache, HTTP transport và connection pool chưa?
- [ ] Đã xác định creator, owner và consumer của từng thành phần chưa?
- [ ] SDK version và HTTP implementation có tài liệu CRaC support không?
- [ ] Credential provider có refresh tự động, background thread hoặc cache riêng không?
- [ ] Đã xác định identity mong muốn ở môi trường sau restore chưa?
- [ ] Token và credential tạm thời có được resolve lại khi cần không?
- [ ] Checkpoint artifact có thể chứa secret và đã được bảo vệ phù hợp chưa?
- [ ] Request đồng bộ, future, stream và upload đang chạy có được drain không?
- [ ] Refresh task có được chờ/dừng theo API công khai không?
- [ ] Shared transport có owner duy nhất và không bị close trùng không?
- [ ] Connection pool có cách xử lý stale socket sau restore không?
- [ ] DNS, TLS, proxy và endpoint có được kiểm tra lại khi môi trường thay đổi không?
- [ ] Client được giữ, refresh hay tạo lại dựa trên tài liệu SDK chưa?
- [ ] Request có side effect có idempotency hoặc operation ID không?
- [ ] Readiness có chờ identity và một thao tác cloud an toàn thành công không?
- [ ] Đã thử credential hết hạn, connection stale và nhiều replica restore chưa?
- [ ] Log/metric có thể chẩn đoán mà không lộ secret không?

## Kết luận

SDK đám mây thường bao gồm nhiều thành phần có vòng đời khác nhau: credential provider, token cache, HTTP transport, connection pool, DNS/TLS state và executor. Khi checkpoint, những thành phần này có thể giữ thông tin xác thực đã hết hạn hoặc kết nối mạng không còn hợp lệ. Việc tiến trình restore thành công không chứng minh request cloud tiếp theo sẽ thành công.

Hãy xác định rõ owner của từng client/provider/transport, ưu tiên workload identity và credential tạm thời, drain mọi SDK operation trước checkpoint, rồi làm mới identity và kết nối theo API được hỗ trợ sau restore. Nếu cần tạo lại client, dùng holder hoặc lifecycle manager để thay thế có kiểm soát và chỉ mở traffic sau health check. Với nhiều replica, cấp identity riêng, tránh chia sẻ token cũ và giới hạn tải refresh/connection khởi tạo. Kiểm thử trên đúng SDK version, JDK CRaC và môi trường cloud mục tiêu sẽ xác nhận được cả khả năng phục hồi lẫn tính an toàn của request.
