# Ngăn token exchange chain vô hạn

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao chuỗi **token exchange** giữa nhiều dịch vụ có thể lặp vòng, dù mỗi lần đổi token riêng lẻ đều hợp lệ.
- Phân biệt **chuỗi ủy quyền (delegation chain)**, **đường đi qua dịch vụ**, **số lần đổi token** và việc gọi API nhiều lần bằng cùng một token.
- Thiết kế chính sách giới hạn số bước, phát hiện chu trình và hạn chế mở rộng quyền tại **Security Token Service (STS)**.
- Triển khai bộ kiểm tra trước khi phát hành token mới, kiểm thử các tình huống biên và giám sát vòng lặp trong hệ thống thật.

## 1. Vấn đề: một lần exchange hợp lệ không bảo đảm cả chuỗi an toàn

Trong hệ thống microservices, dịch vụ nhận một access token có thể cần một token khác với **audience** phù hợp để gọi dịch vụ kế tiếp. OAuth 2.0 Token Exchange (RFC 8693) định nghĩa cách client gửi token đầu vào tới STS và yêu cầu phát hành token thay thế. Đây là một cơ chế hữu ích cho các luồng on-behalf-of và ủy quyền giữa dịch vụ.

Xét luồng:

~~~text
Người dùng
   |
   v
Gateway --exchange--> Orders --exchange--> Billing
                         ^                      |
                         |                      |
                         +------exchange--------+
~~~

Nếu Billing lại xin token để gọi Orders, rồi Orders tiếp tục xin token gọi Billing, hệ thống có thể hình thành:

~~~text
Gateway -> Orders -> Billing -> Orders -> Billing -> ...
~~~

Mỗi lần STS thấy chữ ký, thời hạn và yêu cầu cấp token hợp lệ vẫn có thể phát hành token mới. **Không có một giới hạn số lần đổi token mặc định, áp dụng chung cho mọi STS, do RFC 8693 tự động cưỡng chế.** Một hệ thống phải định nghĩa và thi hành chính sách chuỗi của riêng mình.

Vòng lặp có thể đến từ cấu hình định tuyến sai, phụ thuộc hai chiều giữa dịch vụ, retry không kiểm soát, truyền token nhầm audience hoặc một client cố tình yêu cầu exchange lặp. Hậu quả thường gặp là số lượng token và request tăng nhanh, làm quá tải STS, kéo dài thời gian xử lý, gây khó truy vết và tăng bề mặt lạm dụng token.

> **Phân biệt quan trọng:** Gọi một API nhiều lần bằng cùng access token chưa phải là một chuỗi token exchange. Số bước exchange chỉ tăng khi STS thực sự phát hành token mới dựa trên token trước đó. Việc retry, vòng lặp gọi API và việc tái sử dụng token cần những cơ chế kiểm soát liên quan nhưng khác nhau.

## 2. Cần theo dõi những gì trong một chuỗi?

| Khái niệm | Ý nghĩa | Dùng để kiểm soát |
| --- | --- | --- |
| Subject | Chủ thể gốc được đại diện, ví dụ người dùng hoặc workload | Bảo toàn danh tính được ủy quyền và áp dụng chính sách |
| Actor | Bên đang hành động thay mặt subject | Xác minh quyền ủy quyền và lịch sử actor |
| Audience / resource | Dịch vụ đích có quyền nhận token | Ngăn token bị sử dụng sai đích |
| Exchange hop | Một lần STS phát hành token kế tiếp từ token hiện tại | Đặt giới hạn chiều sâu chuỗi |
| Visited service path | Các dịch vụ đã đi qua trong một nhánh xử lý | Phát hiện quay lại dịch vụ cũ |
| Scope / authorization details | Quyền cụ thể mà token được cấp | Tránh mở rộng quyền qua các lần exchange |
| Expiration | Thời điểm token hết hạn | Không cho token con sống lâu hơn giới hạn chuỗi |

RFC 8693 mô tả các tham số như **subject_token**, **subject_token_type**, **actor_token** (khi phù hợp), **audience/resource** và **scope**. Claim **act** có thể biểu diễn actor hiện tại và actor trước đó theo cấu trúc lồng nhau; **may_act** có thể cung cấp thông tin về bên được phép trở thành actor. Tuy nhiên, lịch sử actor không nhất thiết đồng nhất với danh sách mọi service hop hay mọi lần gọi STS.

Ví dụ token được STS phát hành cho Billing có thể mang thông tin:

~~~json
{
  "iss": "https://sts.example",
  "sub": "user-42",
  "aud": "billing-api",
  "scope": "invoice.read",
  "exp": 1790000000,
  "act": {
    "sub": "orders-service",
    "act": { "sub": "gateway-service" }
  },
  "https://sts.example/claims/token_exchange": {
    "path": ["gateway-service", "orders-service", "billing-api"],
    "hops": 2
  }
}
~~~

Trong ví dụ, phần **act** diễn tả các actor của ngữ cảnh ủy quyền. Claim có khóa **https://sts.example/claims/token_exchange** là **metadata riêng do STS định nghĩa**, không phải claim tiêu chuẩn do RFC 8693 bắt buộc. Đường đi được ghi ở đó có mục đích phát hiện chu trình qua dịch vụ. Trong thực tế, **exp** phải là thời điểm tương ứng với token thật; số ở ví dụ chỉ minh họa cấu trúc.

Với JWT, STS chỉ tin metadata chuỗi sau khi đã **xác minh chữ ký và toàn bộ điều kiện tin cậy** của token. Với opaque token, STS có thể tra metadata từ kho trạng thái tin cậy hoặc một dịch vụ introspection được phép. Client không được tự điền hoặc sửa **path**, **hops** rồi yêu cầu STS tin theo.

## 3. Chính sách phòng vệ nhiều lớp

Để ngăn chuỗi vô hạn và giảm tác động khi phát sinh chuỗi bất thường, nên phối hợp các quy tắc sau:

| Kiểm soát | Quy tắc gợi ý | Vấn đề được ngăn |
| --- | --- | --- |
| Giới hạn chiều sâu | Từ chối nếu **hops >= maxHops** trước lần exchange tiếp theo | Chuỗi quá dài kể cả khi không có chu trình |
| Phát hiện chu trình | Từ chối nếu dịch vụ đích đã có trong **visited path** của cùng nhánh | A → B → C → B |
| Cho phép chuyển tiếp rõ ràng | Chỉ chấp nhận cặp **caller → target** thuộc policy | Exchange sang dịch vụ không liên quan |
| Ràng buộc caller | Xác thực client gọi STS và kiểm tra quyền dùng subject token | Dịch vụ mạo danh bên trung gian |
| Ràng buộc audience | Xác minh token đầu vào có audience/ngữ cảnh phù hợp cho caller và token mới chỉ cấp cho target được phép | Sử dụng token sai mục đích |
| Giảm hoặc giữ nguyên quyền | Quyền token con phải nằm trong phần quyền được phép ủy quyền từ token cha và policy đích | Leo thang quyền qua nhiều hop |
| Hạn chế thời hạn | **exp của token con không vượt exp của token cha** và TTL tối đa do STS áp dụng | Nối dài sự sống token qua exchange |
| Kiểm soát lưu lượng | Rate limit, concurrency limit và tổng số request/token theo chủ thể hoặc chuỗi | Bùng nổ exchange khi lỗi hoặc bị tấn công |

Ví dụ cấu hình phục vụ giải thích:

~~~yaml
tokenExchange:
  maxHops: 2
  maxIssuedTokenTtlSeconds: 300
  rejectRepeatedService: true
  allowedTransitions:
    gateway-service: [orders-service]
    orders-service: [billing-api]
    billing-api: []
~~~

Đây là **cấu hình minh họa**, không phải schema mặc định của OAuth 2.0 hoặc một framework Java. Với chính sách trên, Gateway → Orders có **hops = 1**, Orders → Billing có **hops = 2**, còn Billing → Orders bị từ chối vì vừa quay lại Orders vừa vượt giới hạn bước. Giá trị **maxHops** cần được chọn theo kiến trúc và luồng nghiệp vụ thực tế; không có con số chuẩn chung cho mọi hệ thống.

### Giới hạn bước khác phát hiện chu trình ở đâu?

Giới hạn bước chặn cả chuỗi tuyến tính dài như A → B → C → D → E. Phát hiện chu trình chặn nhánh quay lại dịch vụ từng xuất hiện như A → B → C → B, ngay cả khi giới hạn bước chưa bị chạm tới. Hai quy tắc bổ sung cho nhau.

**Một lưu ý về nghiệp vụ:** Có hệ thống hợp lệ cần quay lại cùng một dịch vụ nhiều lần. Khi đó, không nên áp chính sách cấm quay lại một cách mù quáng. Có thể thiết kế luồng trao đổi mới được cấp quyền rõ ràng, sử dụng một tác vụ riêng hoặc một điểm khởi tạo ủy quyền mới. Mọi ngoại lệ vẫn phải có giới hạn chiều sâu, TTL và quyền cụ thể; tuyệt đối không đặt lại bộ đếm do client tự yêu cầu.

## 4. Thuật toán kiểm tra tại STS

Khi nhận yêu cầu token exchange, STS nên thực hiện theo thứ tự:

1. **Xác thực caller** qua client authentication phù hợp (chẳng hạn mTLS hoặc cơ chế được hệ thống cho phép).
2. **Kiểm tra subject token**: issuer tin cậy, chữ ký/thuật toán, audience/ngữ cảnh dự kiến, thời hạn, trạng thái thu hồi khi có, và các claims liên quan. Nếu là opaque token, dùng introspection/trạng thái đáng tin cậy.
3. **Đọc trạng thái chuỗi đã xác thực** từ token do STS kiểm soát hoặc kho dữ liệu phía máy chủ; chuẩn hóa định danh dịch vụ, không lấy path/hops từ tham số yêu cầu chưa được tin cậy.
4. **Kiểm tra quyền của caller** đối với subject và yêu cầu exchange, bao gồm quyền ủy quyền khi có actor hoặc actor token.
5. **Áp chính sách** maxHops, visited path, allowed transition, audience và quyền được phép cấp cho target.
6. **Tính token con** với audience cụ thể, quyền phù hợp, TTL không dài hơn token cha; tăng hops đúng một lần và thêm target vào path.
7. **Phát hành có bảo vệ**: ký JWT bằng khóa được quản lý hoặc cấp opaque token với trạng thái máy chủ; chỉ trả token nếu toàn bộ kiểm tra PASS.
8. **Ghi telemetry có kiểm soát** và trả lỗi OAuth thích hợp khi từ chối, không đưa raw token hoặc bí mật vào log.

Với trạng thái ban đầu:

~~~text
caller = gateway-service
path = [gateway-service]
hops = 0
maxHops = 2
~~~

Quá trình:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu exchange"] --> B["Xác thực caller và token đầu vào"]
    B --> C{"Tin cậy và được ủy quyền?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D{"hops >= maxHops?"}
    D -- "Có" --> X
    D -- "Không" --> E{"Target đã ở trong path?"}
    E -- "Có" --> X
    E -- "Không" --> F{"Transition, scope, audience, TTL hợp lệ?"}
    F -- "Không" --> X
    F -- "Có" --> G["Thêm target, tăng hops và phát hành token con"]
~~~

### Mã Java minh họa phần quyết định chính sách

Ví dụ sử dụng kiểu dữ liệu đơn giản để tập trung vào thuật toán. **ParentState** phải được xây dựng sau khi xác thực token thành công; đoạn mã không thay thế bước kiểm tra JWT, OAuth client authentication hoặc bước ký token.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.function.BiPredicate;

record ParentState(
        String subject,
        String currentService,
        List<String> visitedServices,
        int hops,
        Instant expiresAt,
        Set<String> scopes) {}

record ExchangeInput(
        String authenticatedService,
        String targetService,
        Set<String> requestedScopes,
        Instant now) {}

class ExchangePolicy {
    static ParentState authorizeNextHop(
            ParentState parent,
            ExchangeInput request,
            int maxHops,
            Duration maxChildTtl,
            BiPredicate<String, String> allowedTransition) {

        // Caller và target phải là định danh chuẩn hóa đã xác thực.
        if (!parent.currentService().equals(request.authenticatedService())) {
            throw new SecurityException("caller_mismatch");
        }
        if (!parent.visitedServices().contains(parent.currentService())) {
            throw new SecurityException("invalid_chain_state");
        }
        if (parent.hops() != parent.visitedServices().size() - 1) {
            throw new SecurityException("invalid_hop_count");
        }
        if (parent.hops() >= maxHops) {
            throw new SecurityException("max_hops_exceeded");
        }
        if (parent.visitedServices().contains(request.targetService())) {
            throw new SecurityException("exchange_cycle_detected");
        }
        if (!allowedTransition.test(
                parent.currentService(), request.targetService())) {
            throw new SecurityException("transition_not_allowed");
        }
        if (!parent.scopes().containsAll(request.requestedScopes())) {
            throw new SecurityException("scope_escalation");
        }

        Instant ttlLimit = request.now().plus(maxChildTtl);
        Instant childExpiry = parent.expiresAt().isBefore(ttlLimit)
                ? parent.expiresAt() : ttlLimit;
        if (!childExpiry.isAfter(request.now())) {
            throw new SecurityException("expired_parent");
        }

        var path = new ArrayList<>(parent.visitedServices());
        path.add(request.targetService());

        // Trả về dữ liệu cho bước issue token có audience = targetService.
        return new ParentState(
                parent.subject(),
                request.targetService(),
                List.copyOf(path),
                parent.hops() + 1,
                childExpiry,
                Set.copyOf(request.requestedScopes()));
    }
}
~~~

Các giả định của ví dụ: mỗi bước đổi token chuyển từ một dịch vụ sang **một target service**; path ban đầu có đúng dịch vụ khởi nguồn, hops ban đầu bằng 0; danh tính caller đã được ràng buộc với dịch vụ đang nắm token; policy quyền thực tế còn cần kiểm tra quyền ủy quyền, resource, tenant và constraint cụ thể. Trong hệ thống có nhiều client dùng chung một API, **client ID** và **audience** không thể mặc định coi là cùng một chuỗi; phải ánh xạ sang định danh dịch vụ chuẩn trước khi dùng thuật toán. Mã trên chỉ là lõi quyết định, chưa phải một STS hoàn chỉnh.

### Khi nên trả lỗi gì?

Đối với yêu cầu OAuth token exchange bị từ chối vì chính sách ủy quyền, STS có thể trả lỗi thích hợp như **invalid_grant** hoặc **access_denied** theo tình huống và hợp đồng API. Có thể dùng mã nội bộ chi tiết như **max_hops_exceeded** hoặc **exchange_cycle_detected** trong telemetry an toàn. Không nên làm rò rỉ danh sách dịch vụ nội bộ, token hoặc nội dung nhạy cảm qua thông báo lỗi cho client.

## 5. Thiết kế lưu trạng thái chuỗi: JWT hay opaque token?

| Phương án | Cách theo dõi chuỗi | Điểm cần cân nhắc |
| --- | --- | --- |
| JWT mang metadata riêng có chữ ký | STS cập nhật hops/path trong token con và xác minh ở lần sau | Không cần tra kho cho mỗi lần, nhưng token lớn dần và việc thu hồi tức thời khó hơn |
| Opaque token với trạng thái phía STS | STS lưu hops/path theo mã tham chiếu, lấy ra qua kho tin cậy | Dễ cập nhật/thu hồi, cần quản lý lưu trữ, TTL và khả năng sẵn sàng |
| Mã định danh chuỗi kèm kho ngắn hạn | Token hoặc record chứa chain ID; STS tra trạng thái được bảo vệ | Hữu ích khi cần theo dõi nhánh, hạn mức tổng và phát hiện hoạt động bất thường |

**Không lấy chain ID làm căn cứ duy nhất để cho phép exchange.** Một chain ID được client tự khai báo, hoặc metadata chưa xác thực, không cung cấp bảo đảm an ninh. Một request mới cũng không được tùy ý khai lại hops = 0 để vượt chính sách.

Trong xử lý song song (fan-out), hai nhánh xuất phát từ cùng token cha có thể đi đến hai dịch vụ khác nhau. Mỗi nhánh cần trạng thái đường đi riêng; nếu có hạn mức tổng cho cả chuỗi, STS phải cộng dồn bằng thao tác nguyên tử để không bị vượt hạn mức khi nhiều exchange đồng thời.

Đối với hệ thống có nhiều STS hoặc nhiều issuer, cần thống nhất ranh giới tin cậy và policy: STS nhận token từ issuer khác chỉ được kế thừa metadata chuỗi nếu đã xác thực issuer, định dạng, quyền và hợp đồng truyền trạng thái được chấp nhận. Không nên xóa lịch sử khi chuyển STS rồi coi đó là một chuỗi mới không giới hạn.

## 6. Các cơ chế hỗ trợ quan trọng

**Ngăn token bị dùng sai đích.** Kiểm tra **iss**, **aud**, **exp**, **nbf**, chữ ký và thuật toán được phép của JWT; với opaque token, kiểm tra kết quả introspection đáng tin cậy. Chỉ phát hành token có audience phù hợp đích. Ở mỗi hop, giới hạn quyền dựa trên cả token cha, quyền của actor, chính sách target và yêu cầu hiện tại.

**Ngăn đánh cắp và phát lại.** Nếu phù hợp mô hình triển khai, dùng sender-constrained access tokens với mTLS (RFC 8705) hoặc DPoP (RFC 9449), xác minh bằng chứng sở hữu ở điểm bắt buộc. Claim **jti** có thể hỗ trợ định danh token và một số chiến lược phát hiện phát lại, nhưng **jti không tự động khiến mọi lần tái sử dụng token trở thành replay trái phép**. Token exchange có thể cho phép sử dụng một access token hợp lệ nhiều lần theo policy. Cần phân biệt replay độc hại với yêu cầu hợp lệ và kiểm soát nonce, bằng chứng, giới hạn lưu lượng khi cơ chế áp dụng yêu cầu.

**Giới hạn khuếch đại do lỗi hệ thống.** Rate limit theo caller, subject và target; giới hạn exchange đồng thời, timeout và retry có backoff cho các lỗi tạm thời. Không retry vô hạn khi STS đã trả lỗi chính sách (như vượt hop, phát hiện chu trình). Một distributed trace ID có thể giúp liên kết sự kiện, nhưng trace ID đơn lẻ không đủ để chứng minh tính hợp lệ của delegation chain.

**Giám sát an toàn.** Theo dõi số lượt exchange theo chuỗi, tỉ lệ bị từ chối theo lý do, độ sâu lớn nhất, các cạnh chuyển tiếp bất thường và STS latency. Log định danh đã được phép và mã tương quan với mức tiết lộ tối thiểu; không log raw bearer token, refresh token, client secret hoặc đầy đủ claims nhạy cảm.

## 7. Kịch bản kiểm thử

Giả sử maxHops = 2, đường đi bắt đầu tại Gateway, chỉ cho phép Gateway → Orders → Billing:

| Trường hợp | Hành động | Kỳ vọng |
| --- | --- | --- |
| Lần exchange đầu | Gateway → Orders, hops 0 → 1 | Cho phép khi claims, quyền và audience hợp lệ |
| Lần exchange thứ hai | Orders → Billing, hops 1 → 2 | Cho phép khi policy hợp lệ |
| Vòng lặp | Billing → Orders | Từ chối vì target đã thuộc path |
| Vượt số bước | Billing → Reporting, dù thêm cạnh allowlist | Từ chối vì đã đạt maxHops |
| Target không được phép | Gateway → Payroll | Từ chối vì transition không nằm trong policy |
| Nâng quyền | Token cha chỉ có invoice.read, token con xin invoice.write | Từ chối nếu không được cho phép bởi toàn bộ policy |
| Nối dài TTL | Token cha còn 60 giây, yêu cầu token con 300 giây | Token con không được hết hạn sau token cha |
| Giả mạo metadata | Client gửi path rỗng/hops = 0 để vượt giới hạn | Bỏ qua giá trị không đáng tin cậy; dùng trạng thái đã xác thực |
| Caller không khớp | Service X trình token chỉ dành cho service Y | Từ chối theo chính sách binding/audience |
| Fan-out đồng thời | Orders xin token tới hai target được phép từ cùng cha | Tính giới hạn mỗi nhánh và hạn mức tổng một cách nhất quán |

Ngoài kiểm thử từng trường hợp, nên có **integration test** cho hai dịch vụ cấu hình phụ thuộc vòng tròn và kiểm tra STS ngừng phát hành token sau số bước tối đa, client không retry lỗi chính sách vô hạn, đồng thời telemetry cung cấp nguyên nhân từ chối.

## 8. Sai lầm thường gặp

1. **Chỉ kiểm tra chữ ký JWT:** token hợp lệ về mật mã vẫn có thể tạo chuỗi ủy quyền trái policy.
2. **Chỉ đếm actor lồng nhau trong act:** không chắc bằng số lần exchange hoặc đường đi dịch vụ; thiếu actor claim cũng không có nghĩa là chuỗi mới.
3. **Tin giá trị hops từ request:** client có thể sửa bộ đếm hoặc xóa lịch sử để xin token vô hạn.
4. **Chỉ giới hạn TTL:** chuỗi token ngắn hạn vẫn có thể được tạo rất nhanh nếu không có maxHops/rate limit.
5. **Mặc định mỗi exchange cho thêm quyền:** chuyển audience không có nghĩa được thêm scope hay bỏ kiểm soát ủy quyền.
6. **Cấm mọi lần đi qua lại mà không xét nghiệp vụ:** có thể làm hỏng luồng hợp lệ; cần thiết kế ranh giới chuỗi và ngoại lệ được kiểm soát.
7. **Nhầm chống vòng lặp với chống replay:** hai bài toán liên quan nhưng có điều kiện nhận diện và biện pháp xử lý riêng.

## 9. Checklist áp dụng trong production

- [ ] Xác định rõ **đơn vị đếm hop**, điểm bắt đầu và ranh giới kết thúc chuỗi exchange.
- [ ] Chuẩn hóa định danh caller/target, thiết lập maxHops và allowlist chuyển tiếp.
- [ ] Bảo đảm STS lấy path/hops từ token đã xác thực hoặc lưu trữ tin cậy.
- [ ] Kiểm tra audience, issuer, expiration, quyền ủy quyền và scope ở từng hop.
- [ ] Không phát hành token con có thời hạn vượt giới hạn token cha.
- [ ] Chặn chu trình hoặc cấu hình ngoại lệ nghiệp vụ có giới hạn rõ ràng.
- [ ] Bảo vệ token trước đánh cắp/phát lại theo mô hình token được chọn.
- [ ] Giới hạn rate, concurrency, retry và ghi metrics mà không lộ token.
- [ ] Kiểm thử chain dài, cycle, giả mạo metadata, chuyển issuer và fan-out.

## Ghi nhớ

**Đừng coi mỗi token exchange hợp lệ là bằng chứng cả chuỗi hợp lệ.** Với OAuth 2.0/OIDC và microservices, STS phải kiểm soát quyền của từng lần đổi token **và** trạng thái ủy quyền xuyên suốt chuỗi: giới hạn độ sâu, nhận biết dịch vụ đã đi qua, áp chính sách chuyển tiếp, giữ quyền ở mức tối thiểu và không cho token con kéo dài tuổi thọ trái phép. RFC 8693 cung cấp giao thức đổi token; giới hạn chuỗi cụ thể là trách nhiệm thiết kế và thực thi của hệ thống.

### Tài liệu tham khảo

- IETF RFC 8693 — *OAuth 2.0 Token Exchange* (subject/actor token, act, may_act): https://www.rfc-editor.org/rfc/rfc8693
- IETF RFC 8705 — *OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens*: https://www.rfc-editor.org/rfc/rfc8705
- IETF RFC 9449 — *OAuth 2.0 Demonstrating Proof of Possession (DPoP)*: https://www.rfc-editor.org/rfc/rfc9449
