# Định tuyến theo phiên bản, khu vực hoặc nhóm người dùng

## 1. Bối cảnh và mục tiêu

Trong một hệ thống microservices, tên dịch vụ không nhất thiết trỏ đến đúng một tiến trình hoặc một cụm triển khai. Cùng một API có thể đang chạy nhiều phiên bản, ở nhiều khu vực địa lý, dành cho những tập người dùng khác nhau. **Định tuyến có điều kiện** (*conditional routing*) quyết định request sẽ được gửi đến backend nào dựa trên thông tin được phép sử dụng và chính sách hệ thống.

Ba câu hỏi thường gặp:

1. **Theo phiên bản:** Client cũ có tiếp tục dùng hợp đồng v1 trong khi client mới chuyển sang v2 được không?
2. **Theo khu vực:** Người dùng ở Việt Nam nên đi tới cụm châu Á, nhưng dữ liệu nào bị ràng buộc phải lưu ở khu vực khác?
3. **Theo nhóm người dùng:** Chỉ một nhóm nội bộ hoặc 5% người dùng đủ điều kiện có thể thử triển khai mới trước khi mở rộng được không?

Ví dụ:

~~~text
                     +--------------------------+
Client request ----> | API Gateway / Edge Router |
                     | xác thực và xét chính sách|
                     +-------------+------------+
                                   |
                   +---------------+------------------+
                   |               |                  |
              /api/v1         /api/v2            Theo cohort
                   |               |                  |
             orders-v1        orders-v2        stable / canary
                   |
            Theo vùng hợp lệ
              |            |
          ap-southeast     europe
~~~

Sơ đồ chỉ biểu diễn các **chiều lựa chọn**. Trong thực tế, không nên áp lần lượt ba bộ quy tắc độc lập mà không xác định thứ tự ưu tiên và phạm vi áp dụng. Một request cần có **quyết định định tuyến cuối cùng duy nhất**, có thể giải thích và kiểm chứng được.

Mục tiêu học tập:

- Hiểu mối quan hệ giữa service discovery, load balancing và định tuyến theo quy tắc.
- Thiết kế định tuyến theo API version, khu vực, nhóm người dùng và tỷ lệ rollout.
- Phân biệt chính sách nghiệp vụ, định tuyến và feature flag.
- Bảo đảm tính ổn định của phiên/cohort, quyền truy cập và dữ liệu.
- Xây dựng phương án canary, rollback và chuyển tiếp khu vực không làm hỏng giao dịch.
- Đo đạc kết quả bằng chỉ số chất lượng, không chỉ số phần trăm traffic.

## 2. Ba lớp: khám phá dịch vụ, chọn tuyến và cân bằng tải

Định tuyến không đồng nghĩa với service discovery.

| Lớp | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| **Service discovery** | Backend nào đang tồn tại, có địa chỉ và trạng thái gì? | Tìm các endpoint hiện còn phục vụ của order-service |
| **Routing policy** | Request thuộc phiên bản/vùng/cohort nào? | Client API v2, tenant thuộc EU, cohort canary |
| **Load balancing** | Trong nhóm backend đã chọn, gửi tới instance nào? | Chọn một instance khỏe theo thuật toán balancing |

Một đường đi điển hình:

~~~text
Request
   |
   v
Xác thực / trích xuất context đáng tin
   |
   v
Áp quy tắc routing: version + residency + cohort
   |
   v
Chọn logical backend pool
   |
   v
Service discovery: danh sách instance còn phục vụ
   |
   v
Load balancing + health check
   |
   v
Backend instance
~~~

Ví dụ, chọn backend pool **orders-v2-eu-canary** không có nghĩa phải chỉ định một IP cố định. Router vẫn cần discovery và load balancing để tìm instance thích hợp, tránh instance không khỏe.

**Nguyên tắc phân quyền:** client không nên tự sửa header nội bộ để vượt qua quy tắc authorization, residency hoặc canary. Hãy phân biệt **đầu vào do client yêu cầu** và **quyết định có thẩm quyền của hệ thống**.

## 3. Mô hình dữ liệu cho một quyết định định tuyến

Để tránh các quy tắc mơ hồ, định nghĩa rõ đầu vào và kết quả.

**Đầu vào** có thể bao gồm:

- Operation: phương thức HTTP, path, service/API được gọi.
- API version được hỗ trợ hoặc đề nghị.
- Danh tính caller đã được xác thực và quyền sử dụng API.
- Tenant/account và vùng lưu trú dữ liệu do hệ thống quản lý.
- Khu vực phục vụ ưu tiên, latency và sức khỏe backend.
- Cohort/experiment assignment đã được tính bằng thuật toán ổn định.
- Feature flag, trạng thái rollout và chính sách vận hành hiện hành.
- Request ID, trace ID để ghi nhận quyết định.

**Đầu ra** nên là một quyết định tường minh, ví dụ:

~~~json
{
  "targetPool": "orders-v2-eu-canary",
  "apiVersion": "v2",
  "region": "eu-west",
  "cohort": "canary",
  "policyRevision": "routing-2026-11-11-01"
}
~~~

Đây là bản ghi minh họa dành cho logging/tracing nội bộ, không phải thông tin phải trả ra cho client. Một quyết định có thể chứa cả lý do lựa chọn và đường xử lý fallback, nhưng không nên log thông tin nhạy cảm ở dạng nguyên văn.

Dữ liệu có tính an toàn cao như **tenant home region** nên đến từ nguồn chính sách tin cậy. Vị trí IP là tín hiệu tiện lợi cho latency, **không phải bằng chứng đáng tin về vùng được phép lưu dữ liệu hoặc quốc tịch người dùng**.

## 4. Định tuyến theo phiên bản API

### 4.1. Khi nào cần nhiều phiên bản?

Định tuyến phiên bản hữu ích khi:

- Một client cũ chưa thể nâng cấp ngay.
- Thay đổi contract có khả năng phá vỡ tương thích: đổi kiểu field, bỏ trường bắt buộc, đổi ý nghĩa endpoint.
- Hai implementation cần chạy song song trong thời gian chuyển đổi.
- Cần thử v2 với một tập client đủ điều kiện trước khi ngừng v1.

Phải tách ba khái niệm:

1. **API contract version:** ý nghĩa dữ liệu, hành vi, lỗi mà client được phép sử dụng.
2. **Application release version:** phiên bản binary/container như 2.4.7.
3. **Experiment/canary revision:** một phần traffic dùng binary mới nhưng vẫn phục vụ cùng hợp đồng API.

Không nên dùng một giá trị **v2** cho cả ba mà không nêu rõ. Một canary release của API v1 vẫn phải giữ hợp đồng v1, bất kể code mới mang version triển khai là gì.

### 4.2. Các cách biểu diễn phiên bản

**Version trong đường dẫn:**

~~~http
GET /api/v1/orders/123
GET /api/v2/orders/123
~~~

Ưu điểm: dễ quan sát và định tuyến; có thể cache/bảo vệ theo path. Nhược điểm: version trở thành phần của URL, cần quản lý nhiều đường dẫn.

**Version qua header:**

~~~http
GET /api/orders/123
Accept: application/vnd.example.orders.v2+json
~~~

Hoặc một header nội bộ được công bố:

~~~http
X-Api-Version: 2
~~~

Version trong header có thể giữ URL ổn định, nhưng phải quy định content negotiation, cache key và hành vi khi header thiếu/không hỗ trợ. **X-Api-Version** là ví dụ tên header theo hợp đồng, không phải chuẩn HTTP bắt buộc của mọi gateway.

**Version qua host:**

~~~text
v1.api.example.com
v2.api.example.com
~~~

Dễ tách hạ tầng nhưng làm tăng cấu hình DNS/TLS/cert và có thể gây phân mảnh endpoint.

Không có cách nào luôn tốt nhất. Với API public, cần có thông báo deprecation, kế hoạch migration và client compatibility. Với RPC nội bộ, có thể dựa trên schema evolution mà không cần URL versioning cho mọi bản triển khai.

### 4.3. Chọn version trước, chọn release sau

Một quy tắc đúng về nguyên tắc:

~~~text
Client gọi hợp đồng /api/v1
     |
Chỉ lựa chọn backend tương thích API v1
     |
Trong nhóm tương thích v1:
    95% -> release ổn định
     5% -> release canary
~~~

Không gửi ngẫu nhiên 5% request v1 sang implementation **chỉ hiểu v2** nếu contract đã breaking. Canary chỉ an toàn khi các backend trong pool phục vụ **cùng hợp đồng được client yêu cầu** hoặc có adapter chuyển đổi được xác minh.

### 4.4. Ví dụ định tuyến version

~~~text
if request.path starts with "/api/v1/":
    pool = "orders-api-v1-compatible"
else if request.path starts with "/api/v2/":
    pool = "orders-api-v2-compatible"
else:
    return 404 or contract-defined version error
~~~

Cần trả lỗi rõ khi version không được hỗ trợ. Không nên âm thầm chuyển client v1 sang v2 nếu ngữ nghĩa không tương thích.

## 5. Định tuyến theo khu vực

### 5.1. Mục đích

Có nhiều lý do để gửi request tới vùng khác nhau:

- Giảm latency bằng cách phục vụ từ hạ tầng gần người dùng.
- Phân chia tải giữa các region.
- Đáp ứng chính sách **data residency** hoặc chủ quyền dữ liệu.
- Hạn chế ảnh hưởng sự cố khu vực.
- Đáp ứng kiến trúc active-active, active-passive hoặc disaster recovery.

Tuy nhiên, **nơi nhận request không nhất thiết là nơi dữ liệu được lưu hoặc xử lý cuối cùng**. Nếu gateway ở Singapore chuyển yêu cầu tới database tại châu Âu, latency, quyền dữ liệu và failover phải được xem xét theo đường đi thật.

### 5.2. Ba loại khu vực không được đánh đồng

| Thuộc tính | Ý nghĩa | Có thể dùng làm quyết định nào? |
|---|---|---|
| **Client location** | Vị trí mạng được suy đoán từ IP/GPS do client cung cấp | Gợi ý endpoint gần, tối ưu latency |
| **Home region của tenant/data** | Vùng được hệ thống quản lý và phê duyệt cho dữ liệu | Xác định nơi có quyền đọc/ghi nguồn dữ liệu |
| **Runtime healthy region** | Vùng đang hoạt động đủ khỏe và có năng lực | Chọn region đáp ứng policy, với fallback hợp lệ |

Một tenant có home region **EU** có thể đăng nhập từ Việt Nam. Routing chỉ theo GeoIP sang châu Á có thể vi phạm chính sách dữ liệu nếu truy cập hoặc sao lưu dữ liệu trái phép. Ngược lại, một hệ thống chỉ phục vụ nội dung công khai từ CDN có thể chọn vùng gần người dùng mà không liên quan tới residency cá nhân.

### 5.3. Ví dụ chính sách vùng

~~~text
1. Xác thực request -> tenantId
2. Đọc tenant.homeRegion từ hệ thống đáng tin
3. Xác định danh sách vùng được phép xử lý dữ liệu
4. Xem health, capacity, latency của các vùng hợp lệ
5. Chọn vùng phục vụ được phép và có khả năng đáp ứng
6. Nếu không có vùng hợp lệ:
      fail closed / trả lỗi có kiểm soát
      không chuyển bừa sang vùng không được phép
~~~

Bước 2 cần tránh tải nặng hoặc gây phụ thuộc vòng lặp trên mỗi request: có thể cache mapping tenant-region với TTL, version và cơ chế invalidation rõ. Cache quá cũ có thể định tuyến sai khi tenant được di chuyển; vì vậy điều kiện cập nhật và dữ liệu có thẩm quyền phải được thiết kế.

### 5.4. GeoDNS, global load balancing và application routing

- **GeoDNS** có thể trả về endpoint khu vực theo vị trí DNS resolver/EDNS client subnet hoặc chính sách khác. Đây thường chỉ là một gợi ý vị trí mạng, không phải kiểm soát residency đầy đủ.
- **Global load balancer** chọn điểm nhận request dựa trên vùng, health và capacity.
- **Application gateway/service layer** quyết định dựa trên tenant, identity, operation và luật dữ liệu.
- **Service discovery trong region** tìm những instance đang phục vụ của backend.

Một hệ thống có thể dùng cả bốn lớp. Cần đo toàn bộ đường đi và tránh tình trạng Gateway A chọn EU nhưng backend B lại gọi trực tiếp service ở vùng bị cấm.

### 5.5. Data consistency trong multi-region

Trước khi định tuyến write sang region khác, làm rõ:

- Mỗi tenant có **một write leader** hay multi-primary?
- Dữ liệu được replicate đồng bộ hay bất đồng bộ?
- Read-after-write có được bảo đảm khi chuyển vùng?
- Khi mất kết nối liên vùng, có chấp nhận ghi ở vùng phụ không?
- Xung đột cập nhật được phát hiện và giải quyết thế nào?
- Có điểm chuyển đổi quyền ghi (*fencing*) để tránh split-brain không?
- RPO/RTO và failover drill có phù hợp yêu cầu?

Nếu data layer chỉ có một primary ở EU, chuyển API write sang vùng Asia không tự tạo khả năng ghi gần người dùng; request có thể vẫn đi xuyên vùng hoặc lỗi vì backend không có dữ liệu có thẩm quyền.

**Tuyến đúng phải đi cùng topology dữ liệu đúng.**

## 6. Định tuyến theo nhóm người dùng (cohort)

### 6.1. Khi nào cần cohort routing?

Cohort routing hữu ích khi:

- Cho nhân viên nội bộ thử một phiên bản mới.
- Canary rollout tới 1%, 5%, 20% người dùng.
- Thử một kiến trúc backend với nhóm khách hàng nhất định.
- Bật tính năng theo tenant hoặc gói dịch vụ.
- Cung cấp ring rollout: internal → beta → limited → general.
- A/B test khi có mục tiêu đo lường rõ và các nhóm so sánh hợp lệ.

Không nên hiểu “5% người dùng” là “5% request” nếu người dùng cần trải nghiệm ổn định. Một người gửi nhiều request có thể bị luân phiên giữa hai backend nếu router chia tỷ lệ ngẫu nhiên theo từng request.

### 6.2. Random weighted traffic so với stable cohort

**Chia trọng số theo request:**

~~~text
Mỗi request ngẫu nhiên:
95% -> stable
 5% -> canary
~~~

Phù hợp với một số thử nghiệm hạ tầng/stateless và backend cùng contract, nhưng **không bảo đảm một user giữ nguyên nhóm**. Cùng một người có thể gọi stable ở request thứ nhất và canary ở request thứ hai.

**Chia nhóm ổn định theo định danh:**

~~~text
cohort = hash(experimentId + stableUserId) mod 10.000

Nếu cohort < 500:
    canary (5%)
Ngược lại:
    stable
~~~

Cách này giữ user trong một nhóm nếu:

- Dùng cùng thuật toán, encoding, namespace/salt và đầu vào.
- ID ổn định sau xác thực.
- Không đổi policy gán nhóm giữa chừng mà không chủ đích.
- Mapping và logic routing nhất quán trên tất cả gateway.
- Các trường hợp anonymous được quy định riêng.

Nhóm 5% **trên tập user đủ điều kiện** không có nghĩa chính xác 5% lưu lượng, vì cường độ sử dụng của mỗi user không giống nhau.

### 6.3. Định danh nào là thích hợp?

| Loại request | Khóa cohort gợi ý | Lưu ý |
|---|---|---|
| Người dùng đã đăng nhập | Stable internal user ID | Không dùng email/PII trực tiếp trong metric |
| SaaS nhiều tenant | Tenant ID | Cả tenant nên cùng backend nếu có trạng thái chung |
| Request trước đăng nhập | Cookie ẩn danh ký/được gateway quản lý | Cần xử lý việc xóa cookie, consent và thay đổi thiết bị |
| B2B integration | Client/application ID | Phải từ xác thực, không dùng header tùy ý |
| Job nền | Job/workflow ID hoặc tenant ID | Không nên đổi backend giữa các bước nếu workflow state riêng |

Chọn đơn vị phù hợp với **tác động của thay đổi**. Nếu canary ảnh hưởng schema dữ liệu của tenant, chia user trong cùng tenant sang hai backend có thể gây bất nhất. Khi đó chia theo **tenant** có thể an toàn hơn.

### 6.4. Feature flag không hoàn toàn là routing

Một feature flag điều khiển hành vi bên trong service (ví dụ cho phép dùng thuật toán giá mới), trong khi routing chọn backend hoặc cluster xử lý request. Hai thứ có thể phối hợp:

~~~text
Routing decision:
    tenant A -> orders-v2-canary pool

Feature decision bên trong:
    tenant A -> bật new-pricing-algorithm
~~~

Nếu dùng cả hai, tránh “hai nguồn sự thật” làm bất nhất. Có thể phát hành release mới mà feature flag vẫn tắt. Ngược lại, bật flag mới trên backend không hỗ trợ khiến request lỗi. Tài liệu cần mô tả ma trận tương thích giữa release, version API, flag và data schema.

## 7. Thuật toán chọn cohort ổn định – ví dụ Java

Đoạn code minh họa cách lấy một bucket 0–9.999 từ identity đáng tin cậy và tên rollout. Để tránh các nhóm thử nghiệm luôn trùng nhau, mỗi experiment có namespace khác.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class CohortBuckets {
    private CohortBuckets() {}

    public static int bucket(String experimentId, String stableId) {
        if (experimentId == null || stableId == null
                || experimentId.isBlank() || stableId.isBlank()) {
            throw new IllegalArgumentException("Missing experiment or identity");
        }

        byte[] input = (experimentId + ":" + stableId)
            .getBytes(StandardCharsets.UTF_8);

        byte[] hash;
        try {
            hash = MessageDigest.getInstance("SHA-256").digest(input);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }

        long first32 = ((long) (hash[0] & 0xff) << 24)
                     | ((long) (hash[1] & 0xff) << 16)
                     | ((long) (hash[2] & 0xff) << 8)
                     |  (long) (hash[3] & 0xff);

        return (int) (first32 % 10_000L);
    }

    public static boolean isCanary(
            String experimentId, String stableId, int basisPoints) {
        if (basisPoints < 0 || basisPoints > 10_000) {
            throw new IllegalArgumentException("Expected 0..10000");
        }
        return bucket(experimentId, stableId) < basisPoints;
    }
}
~~~

Dùng:

~~~java
String experiment = "orders-release-2026-11";
String tenantId = authenticatedPrincipal.tenantId();

boolean canary = CohortBuckets.isCanary(experiment, tenantId, 500);
// 500 / 10000 ~= 5% tenant IDs trong tập đủ điều kiện.
~~~

**Giới hạn ví dụ:**

- SHA-256 với đầu vào có thể đoán được **không phải cơ chế ẩn danh hoặc xác thực**. Không truyền ID nhạy cảm ra client dưới dạng có thể suy ngược.
- Production có thể sử dụng feature-flag service hoặc HMAC với key được quản lý để giảm khả năng đoán cohort nếu đó là yêu cầu bảo mật.
- Hash modulo tạo phân phối gần đều, nhưng không bảo đảm chính xác tỷ lệ trong từng nhóm người dùng nhỏ.
- Nếu muốn so sánh A/B có tính thống kê, cần thiết kế thí nghiệm để tránh sai lệch selection và khác biệt lưu lượng.
- Khi tăng rollout 5% lên 10%, dùng cùng namespace/bucket cho phép 5% ban đầu thường tiếp tục ở canary. Đổi namespace sẽ phân nhóm lại.
- Nếu cần rollback user đã dùng schema hoặc workflow mới, routing về stable chỉ an toàn khi **dữ liệu và contract tương thích**; không suy ra an toàn từ hash.

## 8. Một chính sách tổng hợp: version × region × cohort

Hệ thống có thể cần đồng thời cả ba điều kiện. Thứ tự cần rõ ràng và có kiểm chứng:

1. **Xác thực và ủy quyền:** lấy caller, tenant và quyền từ nguồn đáng tin cậy.
2. **Quyết định loại API:** xác định contract version được yêu cầu và có được hỗ trợ không.
3. **Ràng buộc dữ liệu:** tìm danh sách region hợp lệ cho tenant/operation.
4. **Xác định nhóm đủ điều kiện:** tenant đã đồng ý beta? Thiết bị/client có tương thích không?
5. **Gán cohort ổn định:** internal/beta/canary/stable theo policy đã công bố.
6. **Chọn backend pool:** chỉ trong các pool **phù hợp cả API version, region và cohort**.
7. **Kiểm tra health/capacity:** chọn instance khỏe trong pool; áp fallback được cho phép.
8. **Ghi nhận quyết định:** policy revision, pool, lý do và metric/tracing.
9. **Thực thi:** chuyển request cùng context bảo mật, deadline, trace và idempotency nếu áp dụng.

Ví dụ bảng định tuyến minh họa:

| API version | Tenant home region | Cohort | Backend pool |
|---|---|---|---|
| v1 | EU | Stable | orders-v1-eu |
| v1 | Asia | Stable | orders-v1-ap |
| v2 | EU | Stable | orders-v2-eu |
| v2 | EU | Canary | orders-v2-eu-canary |
| v2 | Asia | Stable | orders-v2-ap |
| v2 | Asia | Canary | orders-v2-ap-canary |

Một user v1 ở EU **không được** chuyển sang v2 Asia chỉ vì v2 Asia đang khỏe. Cũng không được chuyển tenant bị ràng buộc residency sang vùng khác chỉ để đạt mục tiêu availability. Khi pool hợp lệ hết capacity, **fail closed hoặc degrade theo policy**; không tự bỏ qua bất biến.

### 8.1. Bảng quyết định đơn giản

~~~text
request
  |
  v
authenticate()
  |
  +-- denied -> 401/403
  |
  v
version = negotiateVersion(request)
  |
  +-- unsupported -> documented version error
  |
  v
allowedRegions = policy.allowedRegions(tenant, operation)
  |
  +-- none -> deny / unavailable
  |
  v
cohort = assignment(tenantId, experimentId, eligibility)
  |
  v
candidatePools = match(version, allowedRegions, cohort)
  |
  +-- no healthy allowed pool -> configured safe fallback or error
  |
  v
select endpoint via service discovery + load balancing
~~~

Không được dùng header nội bộ do client tự gửi để bỏ qua bước authenticate hoặc eligibility.

## 9. Ví dụ HTTPRoute (Kubernetes Gateway API)

Ví dụ sau minh họa **định tuyến theo header phiên bản** và **cân bằng trọng số giữa hai release cùng contract v2**. Đây là một phác thảo cho môi trường Kubernetes có Gateway API controller phù hợp; việc hỗ trợ feature và cách triển khai thực tế phụ thuộc controller/phiên bản.

~~~yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: orders-v2
  namespace: commerce
spec:
  parentRefs:
    - name: api-gateway
  hostnames:
    - api.example.internal
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /orders
          headers:
            - name: X-Api-Version
              type: Exact
              value: "2"
      backendRefs:
        - name: orders-v2-stable
          port: 8080
          weight: 95
        - name: orders-v2-canary
          port: 8080
          weight: 5
~~~

Giải thích:

- Chỉ request có header **X-Api-Version: 2** và path phù hợp mới dùng rule này.
- **95/5** là trọng số request tới hai backend phù hợp; không phải stable user cohort 5%.
- Hai backend phải đáp ứng **cùng contract v2**. Nếu canary đổi contract breaking, không được dùng weighted routing như vậy.
- Một HTTPRoute như trên **không tự thực hiện** data residency, tenant authorization hoặc stable cohort hashing.
- Rule cần được đặt trong thiết kế gateway/namespace/route đầy đủ, bao gồm route khác dành cho v1 và hành vi mặc định khi header không hợp lệ.
- Các chính sách timeout, retry, TLS, authentication, telemetry và health phải được cấu hình ở các lớp tương ứng, không tự xuất hiện từ YAML.
- Khi nhiều route cùng match, cần xác minh quy tắc ưu tiên của controller/spec; không mặc định thứ tự các dòng YAML là chính sách bảo mật.

Nếu yêu cầu **canary nhất quán theo tenant**, cần một bộ quyết định cohort đáng tin (ứng dụng edge, policy service hoặc cơ chế router hỗ trợ nhất quán) để gắn request tới backend pool đã quyết định; weighted request ở ví dụ trên chưa đủ.

## 10. Service discovery và tình trạng sức khỏe backend

Routing chỉ hoạt động khi các pool được quảng bá đúng và có instance sẵn sàng.

**Các nguồn discovery** phổ biến:

- Kubernetes Services/Endpoints và DNS nội bộ.
- Service registry hoặc control plane của service mesh.
- DNS/global load balancer cho vùng.
- Cấu hình endpoint động do platform quản lý.

Các thuộc tính endpoint có thể dùng trong chính sách:

~~~yaml
service: orders
contract: v2
region: eu-west
release: canary
capacityClass: standard
readiness: ready
~~~

Đây là mẫu metadata khái niệm, không phải schema chung áp dụng cho mọi registry.

### Readiness khác liveness

- **Liveness:** tiến trình còn chạy hay có dấu hiệu bế tắc?
- **Readiness:** instance có nên nhận request mới không?
- **Business dependency health:** instance có phụ thuộc dữ liệu, message broker và giới hạn tải phù hợp để phục vụ operation không?

Một instance có thể “alive” nhưng chưa sẵn sàng do schema migration, cache chưa warm hoặc connection pool cạn. Router cần tránh instance chưa ready; đồng thời tránh thăm dò quá mạnh gây quá tải.

Với multi-region, health check phải xem cả khả năng truy cập **nguồn dữ liệu có thẩm quyền**. API server vẫn khỏe nhưng không còn quyền ghi trong vùng có thể không đủ điều kiện nhận write request.

## 11. Sticky session và tính nhất quán theo workflow

### 11.1. Sticky theo người dùng

Sticky session lưu trạng thái định tuyến của user vào cookie, session ID, consistent hash hoặc assignment store. Nó giúp nhiều request của user tiếp tục dùng một nhóm backend, nhưng cần xác định:

- Giá trị nào tạo stickiness? User ID, session hay tenant?
- Trong bao lâu nhóm giữ nguyên? Sau đăng nhập/đăng xuất thì sao?
- Nếu backend bị lỗi, fallback có tương thích với dữ liệu/session không?
- Tất cả gateway có cùng thuật toán và policy revision không?
- Cookie được ký/bảo vệ ra sao để người dùng không tự chọn nhóm?

Đừng gắn sticky session vào một pod cụ thể nếu hệ thống không cần. Sticky theo **pool/cohort** thường linh hoạt hơn và vẫn cho phép load balancing giữa nhiều instance khỏe.

### 11.2. Sticky theo giao dịch/workflow

Một yêu cầu tạo đơn có thể bắt đầu tại phiên bản canary, sau đó đợi event hoặc callback. Khi bước tiếp theo đến, hệ thống phải quyết định **giữ workflow ở cùng behavior** hay dùng phiên bản mới.

Nếu trạng thái workflow phụ thuộc vào phiên bản xử lý, cần lưu **workflow version** hoặc **policy revision** cùng business operation, không chỉ suy ra từ cookie người dùng hiện tại. Nếu thay đổi rollout giữa chừng, một callback không có session của user vẫn phải tiếp tục đúng ngữ nghĩa.

Ví dụ:

~~~text
Order #A:
  checkoutWorkflowVersion = "v2"
  assignedRegion = "eu-west"
  operationId = "ord-A"

Later payment callback:
  lookup Order #A
  use workflow version and data ownership from state
  NOT hash anonymous caller anew
~~~

Không có nghĩa mọi sự kiện đều bắt buộc quay về cùng instance. Mục tiêu là **giữ hợp đồng và trạng thái nghiệp vụ nhất quán**, có thể trên nhiều instance tương đương.

## 12. Weighted canary so với blue-green và ring rollout

| Chiến lược | Cách triển khai | Điểm cần quản lý |
|---|---|---|
| **Weighted canary** | Gửi tỷ lệ nhỏ request tới release mới | Đo sai khác, sticky khi cần, rollback |
| **Stable cohort** | Một tập user/tenant ổn định dùng release mới | Assignment nhất quán; số request không bằng số user |
| **Blue-green** | Chuyển phần lớn/toàn bộ traffic giữa hai môi trường | Data/schema tương thích, rollback rõ |
| **Ring rollout** | Internal → beta → limited → general | Quy tắc eligibility, gate quyết định |
| **Shadow traffic** | Sao chép request tới backend mới nhưng không dùng response | Ngăn side effects và rò rỉ dữ liệu |
| **Regional rollout** | Triển khai theo từng region có kiểm soát | Khác biệt hạ tầng, dữ liệu và policy |

Canary cần có **thước đo thành công và điều kiện dừng**. Chỉ thấy pod healthy và không crash là chưa đủ.

Các gate minh họa:

- Error rate của canary không vượt ngưỡng tăng đã thống nhất so với stable.
- p95/p99 latency không vi phạm SLO.
- Không tăng lỗi bất biến dữ liệu, timeout giao dịch hay tranh chấp transaction.
- Không có sự cố quyền dữ liệu, ủy quyền hoặc lộ thông tin.
- Có đủ lượng traffic/dữ liệu để so sánh phù hợp trước khi tăng tỷ lệ.

Ngưỡng cụ thể phải dựa trên baseline và mục tiêu sản phẩm. Với cohort gồm khách hàng giá trị cao hoặc khối lượng thấp, rất ít lỗi cũng có thể quan trọng; không có tỷ lệ 1% hoặc 5% “an toàn cho mọi trường hợp”.

## 13. Shadow traffic không được tạo tác dụng phụ

Một kỹ thuật thử nghiệm là sao chép request đang phục vụ sang backend mới và so sánh response:

~~~text
Client
  |
Primary backend --------------> response được dùng
  |
  +---- shadow copy ---------> shadow backend
                               |
                           chỉ đo/so sánh
                           không commit side effect
~~~

**Rủi ro:** shadow request tới endpoint POST có thể tạo đơn, trừ tồn kho, gửi email hoặc gọi payment lần thứ hai. Vì vậy không nên sao chép write traffic tùy ý rồi hy vọng backend mới “chỉ xem thử”.

Những phương án có kiểm soát:

1. Shadow chỉ các operation read-only có quyền truy cập hợp lệ.
2. Tách môi trường dữ liệu để shadow không thể sửa production.
3. Dùng mock/stub cho bên thứ ba và chặn outbound side effects.
4. Với dữ liệu nhạy cảm, bảo đảm privacy và residency cho nơi nhận shadow.
5. Đánh giá kết quả theo semantic equivalence, không chỉ so JSON byte-for-byte khi timestamp hoặc ID có thể khác.

Shadow traffic không thay thế canary thật về hành vi ghi dữ liệu, nhưng có thể giảm rủi ro trước khi bật rollout.

## 14. Rollback và tương thích dữ liệu

Định tuyến traffic về stable chỉ đảo lại **đường đi request**. Nó không đảo lại một schema migration, message/event format đã phát hoặc dữ liệu được bản mới ghi.

Giả sử canary bắt đầu ghi \`orderStatus="PENDING_REVIEW"\` nhưng stable chỉ hiểu \`CREATED/PAID/CANCELLED\`. Sau rollback router, stable có thể không đọc được dữ liệu do canary tạo.

Trước rollout cần xác định:

- Schema database có tương thích cả hai release không?
- API và event có backward/forward compatibility trong thời gian cùng chạy không?
- Có dùng **expand → migrate → contract** để tránh thay đổi phá vỡ ngay không?
- Stable xử lý được trạng thái hoặc enum mới không?
- Cache/search projection có dùng schema khác biệt không?
- Có event đã được phát ra và consumer cũ có hiểu không?
- Một workflow đang chạy sẽ tiếp tục ở đâu sau rollback?
- Có cần dừng tăng traffic nếu schema đã vượt **điểm không thể rollback**?

**Rollback an toàn** có thể yêu cầu tắt feature flag, chặn tạo dữ liệu mới, chạy migration sửa chữa hoặc giữ một compatibility adapter. Không nên chỉ gọi “đổi weight 5 về 0 là rollback thành công”.

### 14.1. Rollout thay đổi dữ liệu qua nhiều bước

Ví dụ một field mới:

~~~text
Giai đoạn 1:
  Stable và Canary đều hiểu field cũ và field mới nếu xuất hiện.

Giai đoạn 2:
  Canary bắt đầu ghi field mới theo cách không phá stable.

Giai đoạn 3:
  Theo dõi dữ liệu và các consumer; tăng dần cohort.

Giai đoạn 4:
  Chỉ loại bỏ field cũ sau khi mọi consumer liên quan
  đã chuyển và cửa sổ rollback không còn cần.
~~~

Nếu field mới chứa thông tin chỉ có bản mới hiểu, cần adapter hoặc phương án state compatibility rõ trước khi mở rộng.

## 15. Fallback an toàn: khác biệt giữa phiên bản, khu vực và cohort

Không phải mọi tuyến đều có cùng chính sách fallback.

| Nguyên nhân | Fallback có thể phù hợp | Fallback nguy hiểm |
|---|---|---|
| Canary có tỷ lệ lỗi cao | Trả cohort về stable **nếu tương thích state/contract** | Trả về stable khi nó không hiểu dữ liệu mới |
| Instance bị lỗi | Chọn instance khỏe khác cùng pool | Chuyển sang API version breaking |
| Cả pool khu vực lỗi | Chuyển region chỉ khi residency, dữ liệu và failover policy cho phép | Đưa tenant EU tới vùng chưa được phê duyệt |
| Client v2 gọi phiên bản không hỗ trợ | Trả lỗi có hợp đồng; yêu cầu client điều chỉnh | Âm thầm downgrade sang v1 với semantics khác |
| Router không xác định được tenant | Từ chối hoặc phục vụ operation công khai theo policy | Dùng IP để suy ra tenant và cho đọc dữ liệu |
| Không xác định được cohort | Dùng stable theo policy đã thống nhất | Gán canary ngẫu nhiên cho thao tác nhạy cảm |

**Fail closed** phù hợp với điều kiện có thể gây vi phạm bảo mật, phân quyền hoặc residency. Với availability, cần một chiến lược degrade được phê duyệt hơn là thay đổi tuyến tùy tiện.

## 16. Bảo mật của context định tuyến

Thông tin routing có thể ảnh hưởng backend nhận dữ liệu. Vì vậy cần thiết kế ranh giới tin cậy:

- **Identity:** lấy từ token đã xác thực hoặc service identity, không chỉ header \`X-User-Id\` do client gửi.
- **Tenant:** xác định từ principal và map quyền, tránh truy cập nhầm tenant.
- **Region:** dùng chính sách data residency thuộc hệ thống, không tin GeoIP cho quyết định tuân thủ.
- **Version:** client có thể yêu cầu một API version, nhưng phải kiểm tra version đó được hỗ trợ và cho phép.
- **Cohort:** assignment được quyết định ở bộ điều khiển tin cậy, không cho client tự chọn \`X-Canary: true\`.
- **Header nội bộ:** gateway xóa header giả mạo từ phía ngoài trước khi tạo header đã xác minh, hoặc truyền context qua kênh đáng tin cậy có authentication/mTLS.
- **Authorization trong service:** backend vẫn cần thực thi quyền truy cập dữ liệu; không coi việc được router chọn là bằng chứng đủ để cho phép mọi hành động.
- **Audit:** ghi dấu chính sách nào đã chọn tuyến và thay đổi policy do ai phê duyệt.

Nếu canary triển khai ở một vùng mà dữ liệu nhạy cảm không được phép xử lý, việc chỉ gửi “một tỷ lệ nhỏ” **không làm rủi ro tuân thủ nhỏ đi thành hợp lệ**.

## 17. Cookie, cache và các lớp trung gian

Định tuyến theo cohort/version có thể tương tác với cache:

1. **Cache key:** hai API version có response khác nhau phải không vô tình dùng cùng cached response.
2. **Header-based variation:** nếu response thay đổi theo request header, cần cấu hình cache/CDN phù hợp (chẳng hạn \`Vary\` khi có ý nghĩa theo HTTP).
3. **Authorization và tenant:** không cache nhầm response riêng tư cho user/tenant khác.
4. **Sticky cookie:** nếu dùng cookie quyết định cohort, phải có scope, expiration, signing và SameSite/Secure/HttpOnly phù hợp.
5. **Cache invalidation:** rollout thay đổi thuật toán giá hoặc định dạng response có thể cần chính sách invalidation tương thích.
6. **Service worker / mobile clients:** client cũ có thể giữ response hoặc offline state, nên version policy phải xử lý trường hợp này.

Một gateway trả đúng pool nhưng CDN phía trước lấy từ cache sai version vẫn gây lỗi contract. Kiểm thử nên bao phủ **đường đi đầu cuối**, không chỉ router unit test.

## 18. Quan sát và xác minh routing

Mọi request nên có quyết định routing đủ để truy vết. Các thuộc tính minh họa:

~~~text
routing.policy_revision = 2026-11-11-01
routing.contract_version = v2
routing.region = eu-west
routing.cohort = canary
routing.backend_pool = orders-v2-eu-canary
routing.fallback_reason = none
trace_id = ...
~~~

Tên là ví dụ thuộc tính nội bộ, không phải mặc định bắt buộc của OpenTelemetry.

**Chú ý cardinality và quyền riêng tư:** tránh dùng user ID, email, tenant ID chi tiết hoặc session ID làm metric label số lượng lớn. Có thể dùng các nhãn thấp cardinality như version, region, cohort, backend pool và policy revision phù hợp; business ID nằm trong log/traces được bảo vệ khi cần.

Các metric đáng theo dõi:

| Metric | Câu hỏi |
|---|---|
| Request volume theo version/region/cohort | Traffic thực tế phân bố ra sao? |
| Distinct users/tenants theo cohort | 5% được đo theo user hay theo request? |
| HTTP/gRPC error rate | Backend nào có vấn đề? |
| p50/p95/p99 latency theo tuyến | Tuyến nào chậm bất thường? |
| SLO burn rate | Rollout có gây mất ngân sách lỗi không? |
| 4xx vs 5xx | Lỗi hợp đồng hay lỗi hệ thống? |
| Fallback count/reason | Quy tắc nào thường xuyên phải chuyển tuyến? |
| Cross-region traffic | Có đường đi dữ liệu ngoài kế hoạch không? |
| Routing decision mismatch | Gateway khác nhau có tính ra cohort khác nhau không? |
| Version compatibility failures | Client nào đang dùng contract không hỗ trợ? |
| Workflow state mismatch | Rollback/canary có khiến workflow lỗi không? |
| Pool health/capacity | Backend có đủ tài nguyên khi tăng traffic không? |

Khi so sánh canary và stable, cần xem **khác biệt về tập người dùng**, workload và thời gian. Cohort chứa nhiều tenant lớn có thể khiến lỗi tăng không phải do release; ngược lại, canary chỉ chứa nhân viên nội bộ có thể không phản ánh traffic production.

## 19. Chính sách triển khai từng bước

Một rollout theo cohort có thể gồm:

### Bước 1: Mô tả thay đổi

Xác định dịch vụ, API contract, bản release, loại dữ liệu, vùng triển khai, đối tượng đủ điều kiện và mục tiêu quan sát. Nêu các bất biến phải giữ: không mất đơn, không tăng lỗi thanh toán, không rò rỉ dữ liệu tenant.

### Bước 2: Kiểm tra khả năng tương thích

Chạy contract tests cho API/event, kiểm tra schema migration, shared cache, session, workflow version và khả năng rollback. Nếu backend mới là API version breaking, yêu cầu client version negotiation tách khỏi canary deployment.

### Bước 3: Định nghĩa cohort và quyền

Chọn stable user/tenant ID do hệ thống xác thực, namespace và thuật toán phân nhóm. Ghi rõ tỷ lệ **người dùng** hay **request**, chính sách sticky, nhóm loại trừ và điều kiện chuyển đổi.

### Bước 4: Kiểm tra region và hạ tầng

Bảo đảm mọi pool có data residency hợp lệ, data access đúng, health/readiness, capacity, TLS, tracing và khả năng failover. Kiểm tra routing qua các gateway, CDN, service mesh và cả callback bất đồng bộ.

### Bước 5: Test trên môi trường hạn chế

Bắt đầu nhóm nội bộ hoặc staging có dữ liệu phù hợp. Dùng shadow read-only khi có ích; chặn side effects ngoài ý muốn. Không dùng dữ liệu production vượt phạm vi được cho phép.

### Bước 6: Rollout từng ring

Ví dụ giả định:

~~~text
Internal -> Beta tenants -> 1% -> 5% -> 20% -> 50% -> 100%
~~~

Các mức chỉ để minh họa. Chuyển ring sau khi đủ dữ liệu theo gate định nghĩa, không tự động theo thời gian nếu error rate đang xấu đi.

### Bước 7: Giám sát và hành động

Theo dõi latency, error, saturation, business conversion, invalid state, cross-region access và số người/tenant thực tế trong cohort. So sánh với baseline tương ứng, theo dõi regression và điều kiện dừng.

### Bước 8: Mở rộng hoặc rollback

Nếu đạt gate, tăng tỷ lệ theo policy. Nếu vi phạm guardrail, khóa tăng rollout, rollback tuyến trong phạm vi an toàn hoặc kích hoạt phương án dữ liệu đã chuẩn bị. Ghi mốc quyết định, người phụ trách và kết quả.

### Bước 9: Dọn dẹp policy cũ

Khi hoàn tất, xóa rule không còn dùng, xác định thời hạn hỗ trợ API cũ, gỡ feature flag không cần thiết và rà soát quyền truy cập. Policy quá cũ dễ gây tuyến “ma” khiến lỗi chỉ xuất hiện ở một phần traffic.

## 20. Kịch bản thực hành: API Orders v2 tại hai khu vực

Giả sử ứng dụng có:

- Orders v1 và Orders v2, cả hai vẫn hỗ trợ client theo hợp đồng tương ứng.
- Hai vùng **EU** và **Asia**, mỗi tenant có home region được cấu hình.
- 10% tenant đủ điều kiện dùng Orders v2 canary tại region của tenant; không phải tất cả client đều đã hỗ trợ API v2.
- Các client cũ tiếp tục gọi \`/api/v1/orders\`.
- Một số tác vụ đặt hàng có workflow kéo dài qua callback từ Payment.

### 20.1. Các câu hỏi thiết kế

1. Bạn chọn region trước hay cohort trước? Vì sao residency phải được xem như ràng buộc cứng?
2. Nếu tenant được phân canary nhưng đang gọi API v1, router phải chọn backend nào?
3. Nếu một request của cùng tenant được gửi qua hai Gateway khác nhau, làm thế nào để kết quả chọn cohort vẫn thống nhất?
4. Nếu region EU bị mất hẳn, điều kiện nào cho phép chuyển write traffic của tenant EU sang vùng Asia?
5. Nếu Orders v2 ghi thêm trạng thái mà v1 không đọc được, làm sao rollback an toàn?
6. Khi Payment callback đến sau vài phút, nó nên dựa vào thông tin routing nào?
7. Nếu 10% tenant tạo ra 40% traffic, có phải tỷ lệ rollout sai không?
8. Đặt ba SLI kỹ thuật, hai chỉ số nghiệp vụ và ba điều kiện tự động dừng rollout.

### 20.2. Một phương án tham khảo

- Xác thực tenant và xác định home region trước; mọi candidate pool phải thuộc vùng được phép.
- Version API là contract: v1 chỉ tới pool tương thích v1; rollout binary canary nằm trong các pool cùng contract.
- Dùng hash ổn định theo tenant + experiment ID, không random theo request nếu cần trạng thái liên tục.
- Lưu workflow version hoặc operation routing context trong trạng thái nghiệp vụ để callback hoạt động đúng, không dựa vào cookie.
- Rollback canary chỉ khi stable đọc/ghi được state đã tạo; nếu không, cần compatibility step hoặc lộ trình rollback dữ liệu.
- Nếu EU mất, chỉ failover sang region được phê duyệt và có dữ liệu đủ điều kiện; nếu không, trả lỗi có kiểm soát.
- Thống kê cả **distinct tenants** và **request volume**; tỷ lệ số tenant không đồng nghĩa tỷ lệ request.

## 21. Tình huống sai cần nhận diện

**Sai lầm: “Cho 5% request đi v2 là canary user 5%.”** Một người có thể luân phiên stable/canary, đặc biệt nguy hiểm với phiên và workflow. Cần chọn đúng đơn vị gán nhóm.

**Sai lầm: “Định tuyến EU theo IP là đủ tuân thủ residency.”** IP có thể không phản ánh tenant home region hoặc nơi database đặt. Cần metadata tin cậy và topology dữ liệu.

**Sai lầm: “Mỗi HTTPRoute đã xử lý authorization.”** Một tuyến khớp path/header không tự kiểm soát quyền truy cập. Backend vẫn cần AuthN/AuthZ.

**Sai lầm: “Rollback là đổi weight về 0.”** Dữ liệu mới, event đã phát và workflow đang chạy có thể không tương thích với bản cũ.

**Sai lầm: “Version API là version image.”** Canary release vẫn phải giữ contract; breaking API v2 cần cơ chế client negotiation.

**Sai lầm: “Nhóm nội bộ chạy tốt nên production an toàn.”** Workload, dữ liệu và hành vi nhóm nội bộ có thể khác người dùng thật; rollout cần đo đại diện.

**Sai lầm: “Rớt region thì chuyển sang bất kỳ region khỏe.”** Không được phá vỡ dữ liệu, compliance, quyền ghi hoặc invariant chỉ để đạt availability.

**Sai lầm: “Router chọn một pod cố định để giữ sticky.”** Có thể tăng nguy cơ lỗi khi instance mất. Nên giữ cohort/pool ổn định và cân bằng tải trong pool khỏe.

**Sai lầm: “Client tự gửi X-Canary: true là được.”** Header không tin cậy có thể vượt qua eligibility, truy cập bản beta hoặc vùng sai. Gateway phải xác định và ký/xác thực context hoặc dùng kênh tin cậy.

## 22. Mẫu tài liệu chính sách routing

~~~markdown
# Routing Policy: <tên dịch vụ>

## Mục tiêu
- Năng lực nghiệp vụ / API contract:
- Đối tượng chịu ảnh hưởng:
- Mục tiêu rollout / residency / latency:

## Đầu vào và mức tin cậy
- API version được client yêu cầu:
- Authenticated tenant/user ID:
- Tenant home region và nguồn dữ liệu có thẩm quyền:
- Cohort/experiment ID và eligibility:
- Health/capacity của backend:
- Thứ tự ưu tiên và policy revision:

## Decision rules
- Version được hỗ trợ:
- Allowed regions:
- Cohort assignment:
- Candidate backend pools:
- Default route:
- Fallback và fail-closed conditions:

## State và consistency
- Session/workflow stickiness:
- Database ownership và write leader:
- API/event/schema compatibility:
- Cross-region data movement:
- Khả năng rollback dữ liệu:

## Rollout
- Internal/beta/canary rings:
- Tỷ lệ tenant/user/request:
- SLI, SLO và business KPIs:
- Guardrails và người phê duyệt:
- Rollback runbook:

## Vận hành
- Metrics, tracing, logs và dashboards:
- Health/readiness và discovery:
- Incident response và failover:
- Ngày xem xét lại/loại bỏ rule:
~~~

Mẫu này nên được version-control cùng thay đổi policy. Routing configuration cũng là **thành phần phần mềm quan trọng**: cần review, test và khả năng truy nguyên thay đổi.

## 23. Checklist trước khi đưa vào production

- [ ] Phân biệt contract version, release version và experiment cohort.
- [ ] Có quy tắc ưu tiên duy nhất khi version × region × cohort cùng áp dụng.
- [ ] Chỉ sử dụng user/tenant identity từ nguồn đã xác thực.
- [ ] Định tuyến region phù hợp quyền dữ liệu, ownership và replication.
- [ ] Có hành vi fail-closed khi không có vùng được phép.
- [ ] Backend pool được khám phá động và chỉ chứa instance có readiness.
- [ ] Sticky assignment phù hợp user/tenant/workflow và nhất quán giữa gateway.
- [ ] Weighted request routing không bị nhầm với stable user cohort.
- [ ] Mọi canary backend phục vụ cùng API contract khi chia traffic theo weight.
- [ ] Cache và CDN không trả response sai version, cohort hoặc tenant.
- [ ] Có plan compatibility cho schema, event và các workflow đang chạy.
- [ ] Rollback route không được coi là rollback dữ liệu.
- [ ] Không shadow write traffic có side effect vào production.
- [ ] Có metric theo region/version/cohort, không tạo high-cardinality metric labels.
- [ ] Có gate rollout, guardrail và phương án xử lý sự cố được xác nhận.
- [ ] Các rule cũ được gỡ sau khi hoàn tất migration/deprecation.

## 24. Ghi nhớ

**Định tuyến theo phiên bản, khu vực hoặc nhóm người dùng là quyết định về nơi một yêu cầu hợp lệ được phục vụ, trong những ràng buộc mà hệ thống phải bảo vệ.** Version routing giữ hợp đồng với client; region routing gắn với latency, residency và quyền sở hữu dữ liệu; cohort routing cho phép thử nghiệm và rollout có kiểm soát. Khi kết hợp chúng, hãy xác thực context, chọn pool theo thứ tự rõ ràng, cân bằng tải trên instance khỏe và giữ ổn định trạng thái theo phiên/workflow. Một đợt canary thành công không chỉ là chuyển được 5% request: nó phải giữ nguyên bất biến, bảo mật, khả năng khôi phục và trải nghiệm người dùng.
