# DNS, địa chỉ IP và thông tin máy chủ có thể thay đổi

Trong chu kỳ CRaC, ứng dụng có thể được checkpoint rồi nằm ngoài hoạt động trong một khoảng thời gian trước khi restore. Trong thời gian đó, môi trường mạng vẫn tiếp tục thay đổi: bản ghi DNS có thể trỏ sang địa chỉ IP mới, máy chủ có thể được thay thế, service discovery có thể chọn instance khác, cấu hình resolver hoặc route có thể được cập nhật. Tiến trình được restore vẫn mang theo trạng thái bộ nhớ đã lưu, trong đó có thể có địa chỉ đã phân giải, cache DNS của JVM, cấu hình client và các connection pool được tạo trước checkpoint.

Vì vậy, một hostname vẫn đúng nhưng IP cũ có thể không còn phục vụ ứng dụng. Nếu sau restore ứng dụng tiếp tục dùng địa chỉ đã cache hoặc tái sử dụng kết nối cũ mà không kiểm tra, request có thể timeout, bị từ chối hoặc đi tới máy chủ không còn phù hợp. Ứng dụng CRaC cần quản lý hostname và tài nguyên mạng theo vòng đời checkpoint–restore: chuẩn bị kết nối trước checkpoint, phân giải lại tên máy chủ và tạo lại các kết nối cần thiết sau restore.

## 1. Những thông tin mạng nào có thể thay đổi?

Tên máy chủ là định danh logic. DNS và hệ thống service discovery ánh xạ định danh đó sang địa chỉ hoặc endpoint có thể truy cập tại một thời điểm cụ thể. Những thông tin sau có thể thay đổi trong thời gian ứng dụng đang được checkpoint:

| Thông tin | Ví dụ thay đổi | Ảnh hưởng sau restore |
| --- | --- | --- |
| Bản ghi DNS A/AAAA | `api.example.com` chuyển từ `192.0.2.10` sang `192.0.2.25`, hoặc địa chỉ IPv6 được bổ sung | Ứng dụng có thể tiếp tục dùng IP cũ nếu kết quả phân giải còn trong cache. |
| CNAME và chuỗi phân giải | Tên alias trỏ sang một hostname đích khác | Endpoint cuối cùng có thể thay đổi dù hostname ứng dụng cấu hình vẫn giữ nguyên. |
| Danh sách nhiều địa chỉ | Load balancer hoặc DNS trả về một tập IP khác | Tập địa chỉ cũ có thể không còn đầy đủ hoặc không còn nhận traffic. |
| Service discovery | Instance của service được scale, thay thế hoặc chuyển vùng | Địa chỉ và trạng thái healthy của các instance có thể thay đổi. |
| Port và endpoint cấu hình | Service được chuyển sang port, hostname hoặc endpoint mới | Cấu hình cũ có thể kết nối nhầm hoặc không kết nối được. |
| Resolver và mạng của host/container | `/etc/resolv.conf`, DNS proxy, route, network namespace hoặc firewall được cập nhật | Cùng một hostname có thể được phân giải hoặc định tuyến khác sau restore. |
| Chứng chỉ và chính sách bảo mật | Chứng chỉ TLS được gia hạn, CA hoặc credential được xoay vòng | Kết nối mới có thể cần trust material hoặc credential mới. |

DNS không phải nguồn duy nhất của thông tin máy chủ. Ứng dụng còn có thể lấy endpoint từ environment variable, file cấu hình, service registry, Kubernetes API, cloud metadata hoặc một hệ thống discovery riêng. Những nguồn này cũng cần được kiểm tra lại nếu giá trị có thể thay đổi trong thời gian checkpoint.

## 2. Vì sao checkpoint có thể giữ lại thông tin mạng cũ?

Checkpoint lưu trạng thái bộ nhớ của tiến trình. Nếu trước checkpoint ứng dụng đã phân giải hostname, kết quả có thể đang được giữ trong cache của JVM hoặc thư viện mạng. Nếu ứng dụng lưu địa chỉ IP vào một field, object cấu hình hoặc cache riêng, giá trị đó cũng có thể được khôi phục cùng tiến trình.

Ví dụ:

```java
public final class RemoteServiceConfig {
    private final String host = "api.example.com";
    private InetAddress resolvedAddress;

    public void initialize() throws UnknownHostException {
        this.resolvedAddress = InetAddress.getByName(host);
    }
}
```

Nếu `resolvedAddress` được tạo trước checkpoint và giữ trong heap, sau restore ứng dụng có thể tiếp tục sử dụng object `InetAddress` đã được tạo trước đó. Việc DNS bên ngoài đã thay đổi không tự động sửa lại field này.

Một tình huống khác là connection pool đã mở kết nối tới IP cũ. Connection object có thể lưu socket, địa chỉ peer và trạng thái protocol. Restore không có nghĩa các thông tin này được đồng bộ lại với DNS hiện tại. Khả năng khôi phục socket còn phụ thuộc vào runtime, CRIU, kernel và loại kết nối; ứng dụng không nên mặc định rằng mọi socket cũ đều tiếp tục hợp lệ.

Phân biệt hai loại trạng thái:

- **Thông tin định danh:** hostname, port, service name và cấu hình TLS. Đây thường là dữ liệu cấu hình logic mà ứng dụng có thể giữ lại, nhưng cần làm mới nếu nguồn cấu hình đã thay đổi.
- **Thông tin kết nối tại một thời điểm:** IP đã phân giải, socket, connection pool, route và trạng thái phiên. Đây là trạng thái có thể hết hạn hoặc không còn hợp lệ sau khoảng thời gian checkpoint.

Thiết kế an toàn thường giữ hostname hoặc service identity làm cấu hình gốc, sau đó phân giải và tạo kết nối mới ở giai đoạn phù hợp sau restore.

## 3. DNS cache tồn tại ở nhiều tầng

Một truy vấn DNS có thể đi qua nhiều lớp cache. Việc DNS record có TTL ngắn không bảo đảm mọi ứng dụng sẽ lập tức thấy địa chỉ mới khi TTL đó hết hạn, vì mỗi lớp có chính sách cache riêng.

```text
Ứng dụng
   |
   +--> Cache của HTTP client / thư viện discovery
   |
   +--> Cache DNS của JVM (InetAddress)
   |
   +--> Resolver của hệ điều hành / NSS
   |
   +--> DNS proxy hoặc recursive resolver
   |
   +--> DNS authoritative
```

Các lớp thường gặp:

1. **DNS authoritative:** trả lời bản ghi và TTL do chủ sở hữu tên miền cấu hình.
2. **Recursive resolver hoặc DNS proxy:** có thể cache câu trả lời trong thời gian TTL, tùy chính sách resolver.
3. **Resolver của hệ điều hành:** có thể sử dụng DNS, `/etc/hosts`, NSS hoặc cơ chế khác tùy nền tảng.
4. **JVM:** `InetAddress` có chính sách cache kết quả phân giải thành công và thất bại.
5. **HTTP client hoặc thư viện service discovery:** có thể có cache DNS hoặc endpoint pool riêng, độc lập với cache của JVM.
6. **Cache do ứng dụng tự xây dựng:** có thể giữ `InetAddress`, IP dạng chuỗi hoặc danh sách server trong memory.

Do đó, thay đổi TTL ở DNS server không nhất thiết làm cache của client thay đổi ngay. Cần xác định tầng nào đang giữ kết quả cũ và chính sách cache của tầng đó.

## 4. Chính sách cache DNS trong Java

Java cung cấp các security property điều khiển cache kết quả phân giải tên qua `InetAddress`:

| Security property | Ý nghĩa |
| --- | --- |
| `networkaddress.cache.ttl` | Thời gian cache kết quả phân giải thành công, tính bằng giây. Giá trị `-1` có nghĩa cache vô thời hạn; `0` tắt cache; số dương đặt thời gian cache. |
| `networkaddress.cache.negative.ttl` | Thời gian cache kết quả phân giải thất bại, tính bằng giây. Giá trị `0` tắt negative cache; số dương đặt thời gian cache lỗi. |

Đây là **security properties**, không phải các JVM system property thông thường. Cấu hình thường được đặt trong file `java.security` của JDK, ví dụ `$JAVA_HOME/conf/security/java.security`:

```properties
networkaddress.cache.ttl=30
networkaddress.cache.negative.ttl=5
```

Giá trị trên chỉ là ví dụ. Hãy chọn TTL theo yêu cầu failover, tải DNS và chính sách hạ tầng. TTL quá dài có thể khiến client tiếp tục dùng địa chỉ cũ; TTL bằng 0 có thể làm tăng số truy vấn DNS và độ trễ. Negative cache quá dài có thể làm hostname vừa được tạo hoặc phục hồi vẫn bị coi là không phân giải được trong một khoảng thời gian.

Có thể cấu hình security property sớm trong quá trình khởi động bằng `java.security.Security.setProperty(...)`, trước khi ứng dụng thực hiện các lookup cần kiểm soát:

```java
import java.security.Security;

public final class DnsCachePolicy {
    private DnsCachePolicy() {}

    public static void configure() {
        Security.setProperty("networkaddress.cache.ttl", "30");
        Security.setProperty("networkaddress.cache.negative.ttl", "5");
    }
}
```

Việc thay đổi policy sau khi đã có lookup không phải cách đáng tin cậy để xóa mọi cache DNS ở tất cả các tầng. Nên thiết lập policy trước các lookup đầu tiên và xác nhận hành vi trên đúng JDK đang triển khai. Các HTTP client hoặc thư viện discovery có thể dùng resolver/cache riêng nên cần cấu hình riêng theo tài liệu của chúng.

Không nên mặc định JVM luôn cache theo đúng TTL của DNS authoritative. Security property và mặc định của từng JDK có thể quyết định thời gian cache thực tế. Hãy kiểm tra cấu hình runtime đang dùng thay vì suy luận chỉ từ TTL của bản ghi DNS.

## 5. Vì sao cần phân giải lại sau restore?

Giả sử ứng dụng được checkpoint khi `payments.internal` trỏ đến `10.10.1.15`. Trong thời gian checkpoint, cụm payment được triển khai lại và DNS đổi sang `10.10.2.20`.

```text
Trước checkpoint                 Trong thời gian checkpoint
-----------------                ---------------------------
payments.internal                payments.internal
        |                                |
        v                                v
    10.10.1.15                       10.10.2.20
        |                                |
        v                                v
  Kết nối cũ được giữ             Instance mới đang phục vụ
  trong memory                    traffic
```

Sau restore, nếu ứng dụng dùng lại `10.10.1.15`, kết nối có thể thất bại vì server cũ đã bị xóa, địa chỉ đã chuyển sang service khác hoặc firewall đã thay đổi. Nếu ứng dụng phân giải lại `payments.internal` qua resolver hiện tại và tạo connection mới, nó có cơ hội nhận endpoint mới.

Phân giải lại cũng giúp cập nhật danh sách nhiều địa chỉ, ví dụ khi DNS trả về một nhóm IP để phân phối tải. Tuy nhiên, phân giải thành công chỉ xác nhận resolver trả về địa chỉ; nó chưa chứng minh server đang healthy hoặc port có thể kết nối. Ứng dụng vẫn cần bước connect/health validation.

## 6. Quản lý connection pool và socket qua lifecycle CRaC

Connection pool thường tái sử dụng kết nối đã mở. DNS thường chỉ được tra cứu khi client tạo kết nối mới; một socket đang mở không tự đổi peer address chỉ vì DNS record thay đổi.

Vì vậy, nếu checkpoint kéo dài hoặc môi trường mạng có thể thay đổi, ứng dụng nên xem các kết nối mạng đang mở là tài nguyên cần quản lý rõ ràng:

- Trước checkpoint, ngừng nhận công việc mới và chờ request đang chạy hoàn tất trong thời hạn cho phép.
- Dừng hoặc tạm ngưng việc tạo connection mới trong lúc chuẩn bị checkpoint.
- Đóng hoặc đưa connection pool về trạng thái có thể khởi tạo lại theo API của pool và thư viện CRaC đang dùng.
- Không giữ một socket cũ trong field rồi giả định socket đó sẽ tự kết nối tới IP mới sau restore.
- Sau restore, phân giải lại hostname và tạo connection pool/client mới khi cần.
- Chỉ mở nhận traffic sau khi các dependency quan trọng đã kết nối và health check thành công.

Không phải mọi connection pool đều có cùng lifecycle API. Một số pool có thể đóng nhưng không thể start lại cùng object; một số HTTP client có thể không hỗ trợ đóng hoàn toàn ở phiên bản đang dùng. Khi đó, nên giữ một factory hoặc provider trong owner lâu dài và thay thế client/pool bằng instance mới sau restore.

## 7. Ví dụ Resource làm mới endpoint sau restore

Ví dụ dưới đây minh họa một `Resource` giữ hostname làm cấu hình gốc. Trước checkpoint, nó dừng sử dụng client hiện tại và đóng các kết nối theo API của abstraction. Sau restore, nó phân giải hostname để quan sát endpoint hiện tại rồi tạo lại client.

```java
import org.crac.Context;
import org.crac.Resource;

import java.net.InetAddress;
import java.util.Arrays;

public final class NetworkResource implements Resource {
    private final String host;
    private final int port;
    private final NetworkClientFactory clientFactory;
    private NetworkClient client;

    public NetworkResource(
            String host,
            int port,
            NetworkClientFactory clientFactory) {
        this.host = host;
        this.port = port;
        this.clientFactory = clientFactory;
        this.client = clientFactory.create(host, port);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        stopAcceptingRequests();
        if (!awaitRequestsToDrain()) {
            throw new IllegalStateException("Requests did not drain before checkpoint");
        }

        if (client != null) {
            client.closeConnections();
            client = null;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        InetAddress[] addresses = InetAddress.getAllByName(host);
        System.out.println("Resolved " + host + ": " + Arrays.toString(addresses));

        // Factory dùng hostname để tạo client mới và áp dụng chính sách
        // DNS, TLS, timeout, load balancing của thư viện đang sử dụng.
        client = clientFactory.create(host, port);
        client.validateConnectivity();
        resumeAcceptingRequests();
    }

    private void stopAcceptingRequests() { /* application-specific */ }
    private boolean awaitRequestsToDrain() { return true; /* bounded wait */ }
    private void resumeAcceptingRequests() { /* application-specific */ }
}
```

`NetworkClient` và `NetworkClientFactory` là abstraction do ứng dụng định nghĩa; các method trong ví dụ cần được ánh xạ tới API thực tế của HTTP client, database pool hoặc thư viện mạng đang sử dụng. Việc gọi `InetAddress.getAllByName(host)` có thể vẫn trả về kết quả từ JVM cache nếu entry còn hiệu lực. Muốn lấy kết quả mới, phải thiết kế cache policy phù hợp và xử lý cache riêng của thư viện client.

Ví dụ cũng giữ `host` thay vì chỉ giữ `InetAddress` hoặc IP. Khi factory tạo client mới bằng hostname, thư viện có thể thực hiện phân giải theo resolver và chính sách riêng. Không nên truyền IP đã lưu từ trước checkpoint vào factory nếu mục tiêu là nhận endpoint mới.

Các method `stopAcceptingRequests` và `awaitRequestsToDrain` minh họa việc chặn traffic mới trước khi đóng client. Phần drain cần có timeout hữu hạn. Khi ứng dụng đã quiesce và chưa mở traffic sau restore, callback có thể thay client mà không phải giữ application lock trong lúc DNS hoặc network I/O. Nếu thiết kế cần lock để bảo vệ state, chỉ giữ lock trong đoạn swap client ngắn và thực hiện phân giải/kết nối bên ngoài critical section.

## 8. Hostname, IP và TLS

Khi có nhiều địa chỉ IP, nên ưu tiên dùng hostname/service name trong cấu hình ứng dụng và để client phân giải tên theo chính sách phù hợp. Kết nối trực tiếp bằng IP có thể bỏ qua cơ chế DNS failover hoặc service discovery.

Hostname cũng quan trọng với TLS:

- TLS SNI thường cần hostname để server chọn đúng certificate.
- Certificate hostname verification kiểm tra tên máy chủ mà client dự định kết nối.
- Nếu ứng dụng thay hostname bằng IP trong URL hoặc cấu hình TLS, việc xác thực certificate có thể thất bại hoặc cần cấu hình SAN IP riêng.
- Không tắt hostname verification chỉ để vượt qua lỗi kết nối sau restore.

Nếu buộc phải dùng IP tĩnh, cần có quy trình cập nhật cấu hình, kiểm tra route và certificate tương ứng. Không nên coi IP là định danh lâu dài nếu hạ tầng có khả năng thay đổi địa chỉ.

## 9. Cập nhật thông tin server từ cấu hình và service discovery

Không phải ứng dụng nào cũng dùng DNS trực tiếp. Một số ứng dụng đọc danh sách endpoint từ cấu hình, registry hoặc API discovery. Khi checkpoint, các danh sách này có thể đã cũ sau restore.

Thiết kế nên tách:

- **Nguồn cấu hình:** hostname, service id, port, TLS policy và thông tin xác thực. Đây là đầu vào logic để tạo client.
- **Endpoint snapshot:** IP hoặc danh sách instance được phân giải tại một thời điểm. Đây là dữ liệu tạm thời, cần refresh theo chính sách.
- **Connection state:** socket, pool, session và trạng thái health. Đây là tài nguyên cần kiểm tra hoặc tạo lại sau restore.

Ở `afterRestore`, ứng dụng có thể đọc lại cấu hình động hoặc refresh service registry trước khi tạo client. Nếu cấu hình đến từ environment variable chỉ được nạp lúc process start, việc restore cùng process có thể giữ giá trị cũ; cần có cơ chế refresh rõ ràng nếu môi trường có thể đổi giá trị trong thời gian checkpoint.

Khi cập nhật endpoint, nên xử lý trường hợp DNS trả về nhiều địa chỉ, một số địa chỉ không reachable hoặc thứ tự ưu tiên IPv4/IPv6 thay đổi. Client nên có retry có giới hạn, backoff và giới hạn tổng thời gian reconnect để một địa chỉ lỗi không làm callback chờ vô hạn.

## 10. Các lỗi thường gặp sau restore

| Hiện tượng | Nguyên nhân có thể gặp | Hướng điều tra |
| --- | --- | --- |
| Kết nối tới IP cũ bị timeout | `InetAddress`, cache riêng hoặc cấu hình ứng dụng vẫn giữ IP cũ | Kiểm tra hostname, kết quả DNS hiện tại, JVM cache và cache của client. |
| Hostname mới phân giải thất bại dù DNS đã được cập nhật | Negative DNS cache hoặc resolver/proxy vẫn giữ kết quả cũ | Kiểm tra `networkaddress.cache.negative.ttl`, resolver và thời điểm bản ghi được cập nhật. |
| Một số instance kết nối được, một số không | DNS trả nhiều địa chỉ hoặc một số backend chưa healthy | Kiểm tra từng IP, port, health, routing và load balancing. |
| DNS phân giải đúng nhưng request vẫn lỗi | Connection pool tái sử dụng socket cũ hoặc TLS/session không còn hợp lệ | Tạo client/pool mới, kiểm tra peer address, handshake và certificate. |
| Restore trên container mới không phân giải được tên | DNS config, search domain, resolver hoặc network namespace khác | Kiểm tra `/etc/resolv.conf`, `/etc/hosts`, NSS, DNS proxy và cấu hình network của container. |
| Reconnect kéo dài hoặc callback bị treo | Không có connect/read timeout hoặc retry vô hạn | Đặt deadline tổng, timeout cho từng tầng và giới hạn retry/backoff. |
| Kết nối TLS lỗi sau khi endpoint đổi | Certificate, SNI, trust store hoặc hostname verification không phù hợp | Kiểm tra hostname, SAN, CA, thời hạn certificate và cấu hình TLS. |

## 11. Quan sát và kiểm thử thay đổi DNS

Để chẩn đoán, nên ghi lại hostname/service id, danh sách IP nhận được, thời điểm phân giải, thời gian reconnect và kết quả health check. Log không nên chứa credential, token hoặc dữ liệu nhạy cảm.

Các công cụ hệ điều hành có thể giúp kiểm tra kết quả resolver bên ngoài JVM:

```bash
getent hosts api.example.com
```

Trên môi trường có `dig`, có thể kiểm tra bản ghi và TTL từ resolver đang cấu hình:

```bash
dig api.example.com A
dig api.example.com AAAA
```

Kết quả từ `dig` hoặc `getent` không nhất thiết giống ngay kết quả của ứng dụng nếu JVM hoặc HTTP client đang giữ cache riêng. Vì vậy, hãy kiểm tra từ cùng container/namespace và quan sát chính client mà ứng dụng sử dụng.

Kịch bản kiểm thử tích hợp có thể thực hiện như sau:

1. Cấu hình hostname thử nghiệm trỏ đến server A.
2. Khởi động ứng dụng, xác nhận client kết nối tới A và tạo checkpoint.
3. Thay đổi DNS hoặc service discovery để hostname trỏ sang server B.
4. Đợi theo TTL và cache policy dự kiến, hoặc dùng resolver test có thể điều khiển để xác định thời điểm cập nhật.
5. Restore ứng dụng trong môi trường tương thích.
6. Xác nhận callback đóng kết nối cũ, phân giải endpoint mới và tạo client mới.
7. Kiểm tra request sau restore thực sự tới B và ứng dụng đạt readiness.
8. Thử thêm trường hợp DNS tạm thời không phân giải được, trả về nhiều IP, hoặc một backend không reachable để xác nhận timeout và retry có giới hạn.

Không nên chỉ kiểm tra `InetAddress.getAllByName()` rồi kết luận client đã dùng endpoint mới. Cần xác nhận kết nối thực tế của client, bởi connection pool có thể giữ socket cũ và thư viện có thể có resolver riêng.

## 12. Checklist quản lý DNS và endpoint trong CRaC

- [ ] Lưu hostname hoặc service identity làm cấu hình gốc thay vì chỉ lưu IP đã phân giải.
- [ ] Xác định tất cả tầng DNS cache: JVM, OS resolver, HTTP client, service discovery và cache ứng dụng.
- [ ] Cấu hình positive/negative DNS cache phù hợp với yêu cầu failover.
- [ ] Không nhầm security properties `networkaddress.cache.*` với JVM system properties thông thường.
- [ ] Trước checkpoint, dừng công việc mới và xử lý connection pool/socket theo lifecycle của thư viện.
- [ ] Sau restore, refresh cấu hình hoặc service discovery nếu endpoint có thể thay đổi.
- [ ] Phân giải hostname lại theo cache policy phù hợp và tạo connection mới khi cần.
- [ ] Đặt connect/read timeout, deadline tổng và retry/backoff có giới hạn.
- [ ] Kiểm tra TLS SNI, hostname verification, trust store và certificate sau khi endpoint thay đổi.
- [ ] Chỉ mở nhận traffic sau khi các dependency quan trọng đã kết nối và health check đạt.
- [ ] Kiểm thử DNS đổi IP giữa checkpoint và restore trên đúng môi trường CRaC triển khai.

## 13. Kết luận

Checkpoint giữ trạng thái bộ nhớ của tiến trình tại một thời điểm, trong khi DNS, IP, server instance và cấu hình mạng bên ngoài vẫn có thể thay đổi. Sau restore, hostname có thể vẫn đúng nhưng địa chỉ đã lưu hoặc socket cũ có thể không còn phù hợp. Cần phân biệt cache DNS ở JVM với cache của OS, resolver, HTTP client và service discovery; mỗi tầng có chính sách riêng.

Hãy giữ hostname/service identity làm nguồn định danh, quản lý connection pool qua `beforeCheckpoint`, refresh thông tin endpoint và tạo kết nối mới trong `afterRestore`, rồi kiểm tra readiness trước khi nhận traffic. Cấu hình TTL, timeout và retry có giới hạn giúp ứng dụng thích nghi với thay đổi DNS mà không biến quá trình restore thành một callback chờ vô hạn.
