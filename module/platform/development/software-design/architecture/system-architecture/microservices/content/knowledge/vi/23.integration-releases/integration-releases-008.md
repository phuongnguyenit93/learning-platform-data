# Tách thời điểm triển khai khỏi thời điểm bật tính năng trong Microservices

Trong một hệ thống microservices, việc đưa mã nguồn mới lên production và việc cho người dùng sử dụng hành vi mới là **hai quyết định khác nhau**. Một bản triển khai có thể thành công về mặt kỹ thuật nhưng tính năng mới vẫn gây lỗi nghiệp vụ, tăng độ trễ hoặc làm quá tải dịch vụ phụ thuộc khi được sử dụng rộng rãi. Nếu gắn chặt hai thời điểm này, nhóm phát triển thường phải chọn giữa trì hoãn deploy và chấp nhận mở tính năng cho toàn bộ người dùng cùng lúc.

**Tách deployment khỏi release** cho phép triển khai mã mới an toàn trước, sau đó chủ động bật, tăng phạm vi sử dụng, quan sát, tạm dừng hoặc tắt hành vi mới bằng cấu hình có kiểm soát. Đây là một nền tảng của **progressive delivery**: phân phối thay đổi theo từng bước và dựa trên kết quả thực tế thay vì coi deploy thành công là kết thúc công việc.

Ví dụ: Checkout Service có thuật toán tính phí vận chuyển mới. Nhóm phát triển triển khai phiên bản chứa cả thuật toán cũ và mới vào production khi cờ tính năng vẫn tắt. Sau khi xác nhận môi trường ổn định, họ bật cho nhân viên, rồi một nhóm khách hàng nhỏ, đo tỷ lệ lỗi và sai lệch phí, mới tăng dần phạm vi. Nếu phát hiện bất thường, họ tắt cờ để quay về hành vi cũ trong giới hạn mà thiết kế đã cho phép, trong khi phiên bản ứng dụng vẫn chạy.

Bài này giải thích khái niệm, công cụ và quy trình thiết kế để tách hai thời điểm đó, đặc biệt khi một tính năng đi qua nhiều service, database, message broker và các phiên bản triển khai khác nhau.

## 1. Phân biệt deployment, release, rollout và rollback

Những từ này thường xuất hiện cùng nhau nhưng mô tả các hoạt động khác nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Deployment** | Đưa artifact/configuration mới vào môi trường chạy | Triển khai Order Service phiên bản 2.8 lên Kubernetes |
| **Release / feature activation** | Cho một nhóm người dùng hoặc workload sử dụng hành vi mới | Bật tính phí mới cho 5% khách hàng đủ điều kiện |
| **Rollout** | Mở rộng phạm vi triển khai hoặc kích hoạt theo kế hoạch | Tăng từ 5% lên 25%, 50%, 100% |
| **Rollback deployment** | Quay ứng dụng về artifact/configuration trước đó | Chuyển lại image 2.7 khi bản mới lỗi lúc khởi động |
| **Disable/rollback feature** | Tắt hành vi mới qua cấu hình, thường không thay binary | Đưa cờ new-shipping-fee về OFF |
| **Roll forward** | Phát hành bản sửa mới thay vì quay lại artifact cũ | Triển khai 2.8.1 vá lỗi tương thích schema |
| **Experiment** | Chia nhóm người dùng để đánh giá tác động có phương pháp | So sánh tỷ lệ hoàn tất checkout giữa hai biến thể |

Có thể có **hai trục độc lập**:

~~~text
Trục 1: Mã nguồn đã triển khai?
    Version cũ  ----------------------->  Version mới có cả hai đường xử lý
                                                  |
Trục 2: Ai được sử dụng tính năng mới?            |
    OFF -> INTERNAL -> 1% -> 5% -> 25% -> 50% -> 100%
                                                  |
    Nếu có lỗi: 25% -> OFF, phiên bản mới vẫn đang chạy
~~~

Triển khai thành công chỉ chứng minh artifact có thể chạy qua các phép kiểm tra đã thiết lập. Nó **không** tự chứng minh hành vi mới an toàn khi hàng triệu request hoặc nhiều tenant cùng sử dụng.

Ngược lại, feature flag không biến một thay đổi mã nguồn không tương thích thành an toàn. Nếu một binary mới không thể đọc dữ liệu cũ, không thể chạy với service phiên bản cũ hoặc phá hủy schema ngay khi start, việc để cờ OFF có thể cũng không cứu được. Tính tương thích là điều kiện riêng phải được thiết kế.

## 2. Vấn đề của cách phát hành gắn liền với deploy

Giả sử ba microservice phối hợp xử lý đơn hàng:

~~~text
Client
  |
  v
API Gateway
  |
  v
Order Service ---> Pricing Service
  |                  |
  |                  +-- Chính sách giảm giá mới
  |
  +---------------> Payment Service
  |
  +---------------> Inventory Service
~~~

Pricing Service được thay thuật toán giảm giá trong một lần deploy duy nhất. Ngay sau khi bản mới nhận traffic, tất cả Order Service bắt đầu lấy giá tính theo quy tắc mới. Nếu có lỗi làm tròn, thay đổi cache key hoặc thêm truy vấn đắt tiền, người dùng bị ảnh hưởng đồng loạt. Quy trình rollback binary có thể mất thời gian và gặp rủi ro nếu database đã thay đổi.

Tách hai thời điểm giúp giải quyết các nhu cầu:

1. **Giảm blast radius:** chỉ một phần nhỏ người dùng chịu tác động ban đầu.
2. **Phát hiện lỗi bằng số liệu thật:** quan sát latency, error rate và kết quả nghiệp vụ của nhóm bật cờ.
3. **Tắt nhanh khi có sự cố:** một điều khiển vận hành có thể đưa hành vi về phương án đã biết.
4. **Độc lập giữa nhịp triển khai và nhịp kinh doanh:** mã được triển khai trong ngày làm việc, tính năng mở vào thời điểm chiến dịch đã định.
5. **Phối hợp nhiều service:** tất cả thành phần có thể hỗ trợ giao thức mới trước khi bật sử dụng.
6. **Kiểm thử production an toàn hơn:** cho phép nhóm nội bộ hoặc tenant thử nghiệm kiểm chứng trên hạ tầng thật.
7. **Thực hiện thử nghiệm có đối chứng:** đo tác động của hành vi mới với nhóm được phân bổ ổn định.

Tuy nhiên, lưu hai đường xử lý cũ và mới tăng độ phức tạp. Nếu giữ cờ vô hạn, code có nhiều nhánh khó kiểm thử, các nhóm không biết hành vi nào là mặc định và nguy cơ phân nhánh không đồng nhất tăng theo thời gian. Mỗi cờ cần mục đích và **kế hoạch kết thúc**.

## 3. Feature flag là gì và không phải là gì?

**Feature flag** hay **feature toggle** là một quyết định cấu hình tại runtime (hoặc tại một điểm đánh giá được kiểm soát) để chọn đường xử lý.

~~~text
Request
  |
  v
Xác thực / phân quyền bắt buộc
  |
  v
Đánh giá flag + bối cảnh
  |
  +-- OFF ------------------> Đường xử lý cũ
  |
  +-- ON, đủ điều kiện ------> Đường xử lý mới
  |
  v
Kết quả + telemetry theo biến thể
~~~

Một flag có thể có dạng boolean đơn giản, lựa chọn nhiều biến thể, quy tắc theo tenant, khu vực, phiên bản client, user segment hoặc tỷ lệ phần trăm được gán ổn định.

### Các nhóm cờ theo mục đích

| Nhóm | Ví dụ | Đặc điểm vận hành |
| --- | --- | --- |
| **Release flag** | new-checkout-flow | Thường tồn tại ngắn hạn đến khi rollout xong và dọn code cũ |
| **Operational / kill switch** | enable-recommendations | Cho phép tắt nhanh chức năng tùy chọn khi lỗi hoặc quá tải |
| **Experiment flag** | pricing-layout-variant | Phải phân nhóm ổn định và ghi nhận exposure để đo tác động |
| **Migration flag** | read-from-new-index | Điều khiển chuyển đọc/ghi khi di chuyển storage hoặc API |
| **Entitlement / kế hoạch sản phẩm** | premium-export-available | Có thể tồn tại lâu dài nhưng phải gắn với chính sách quyền rõ ràng |
| **Internal / preview** | dashboard-v2-for-staff | Cho phép nhân viên hoặc tenant thử nghiệm dùng trước |

Không phải mọi cờ đều nên được sử dụng như nhau. Release flag thường có thời gian sống hữu hạn; operational switch có thể giữ lâu hơn vì là khả năng vận hành; entitlement liên quan quyền kinh doanh và bảo mật phải có hệ thống kiểm tra đáng tin cậy.

**Feature flag không phải cơ chế authorization.** Người dùng không được phép truy cập dữ liệu nhạy cảm vẫn phải bị từ chối dù UI hoặc API được bật cờ. Không coi việc giấu một nút bấm bằng cờ ở trình duyệt là đủ để bảo vệ endpoint phía server.

## 4. Những cách lưu và đánh giá cờ tính năng

Một cờ có thể được cung cấp từ:

- **Configuration đóng gói cùng ứng dụng:** dễ quản lý nhưng thay đổi thường cần deploy/restart; ít phù hợp với kill switch cần hiệu lực nhanh.
- **Environment variable hoặc ConfigMap:** phù hợp bật/tắt cho toàn service nếu pipeline cập nhật/reload rõ ràng; nhiều runtime chỉ đọc lúc khởi động.
- **Feature management service:** quản lý quy tắc nhắm mục tiêu, percentage rollout, lịch sử thay đổi, audit, RBAC và SDK runtime.
- **Cấu hình nội bộ trong database/cache:** linh hoạt, nhưng nhóm tự chịu trách nhiệm về đồng bộ, caching, tính nhất quán và lỗi cấu hình.
- **Service mesh/traffic router:** điều khiển chuyển traffic giữa các deployment, thường phù hợp canary deployment hơn là phân nhánh nghiệp vụ trong cùng binary.

### Đánh giá tại server hay client?

**Server-side evaluation** thích hợp khi quyết định ảnh hưởng nghiệp vụ, bảo mật, tiền, truy cập dữ liệu hoặc side effect. Server nhận bối cảnh đã xác thực, quyết định đường xử lý và không để client tự khai báo “tôi thuộc nhóm ON”.

**Client-side evaluation** thích hợp cho một số hành vi giao diện như hiển thị layout, hoạt ảnh hoặc chuỗi nội dung công khai. Quy tắc nhắm mục tiêu và dữ liệu nhạy cảm không được gửi xuống client nếu có thể làm lộ chính sách nội bộ. Dù client ẩn chức năng, API vẫn phải kiểm tra đầy đủ quyền.

**Hybrid:** server tính quyết định an toàn, trả một tập capability có thể công bố; client dùng capability đó để điều chỉnh UI. Ví dụ response chỉ cho biết variant và khả năng sử dụng, không cung cấp toàn bộ tập quy tắc phân nhóm.

## 5. Thiết kế một feature flag có hợp đồng rõ ràng

Một định nghĩa cờ nên bao gồm nhiều hơn tên và giá trị ON/OFF.

| Thuộc tính | Ví dụ minh họa | Lý do |
| --- | --- | --- |
| Key | checkout.new-pricing.v2 | Tên ổn định để code và vận hành cùng tham chiếu |
| Owner | Team Checkout | Có người chịu trách nhiệm rollout và dọn cờ |
| Purpose | Bật quy tắc tính phí mới | Tránh cờ tồn tại mà không rõ ý nghĩa |
| Type | Release flag | Quy định vòng đời và cách đo |
| Default khi chưa cấu hình | OFF | Hành vi dự phòng được xác định rõ |
| Scope | Production; tenant đủ điều kiện | Tránh bật nhầm ở nơi không tương thích |
| Targeting | Internal, allowlist, 1–100% | Điều khiển ai nhận variant |
| Dependencies | Pricing v2 API + dữ liệu tương thích | Chỉ bật khi tất cả điều kiện đã sẵn sàng |
| Owner approval | Người phụ trách rollout | Kiểm soát thay đổi |
| Observability | Flag key, variant, rate, business outcomes | Phát hiện suy giảm |
| Kill switch | OFF trong giới hạn SLA phù hợp | Phương án xử lý sự cố |
| Expiry/cleanup | Sau ổn định và xác nhận rollout | Tránh nợ kỹ thuật lâu dài |

Các giá trị ở đây là ví dụ để thiết kế hợp đồng; nhóm thực tế cần dùng tên, tiêu chí và khoảng thời gian phù hợp với hệ thống của mình.

Một mẫu cấu hình logic:

~~~yaml
flag:
  key: checkout.new-pricing.v2
  enabled: true
  default: false
  targeting:
    environments: [production]
    allowedTenants: [internal-demo]
    percentage: 5
  prerequisites:
    pricingApiVersion: v2
  owner: checkout-team
  purpose: progressive-release
~~~

Cấu trúc trên là **mẫu dữ liệu khái niệm**, không phải schema cấu hình của một sản phẩm feature flag cụ thể. Tên trường và cách đánh giá phụ thuộc công cụ hoặc thư viện được chọn.

## 6. Quy trình deploy rồi release theo từng bước

Một quy trình phổ biến:

~~~text
Code + tests + migration tương thích
        |
        v
Build artifact bất biến
        |
        v
Deploy production với flag OFF
        |
        v
Smoke test + kiểm tra kết nối + telemetry
        |
        v
Bật cho internal users / test tenants
        |
        v
1% -> đo -> 5% -> đo -> 25% -> đo -> 50% -> đo -> 100%
        |             |               |
        +------- bất kỳ bước lỗi ------+
                      |
                      v
                  Tạm dừng / OFF
                      |
                      v
            Chẩn đoán, sửa và đánh giá lại
        |
        v
Ổn định ở 100% -> dọn nhánh cũ và cờ theo kế hoạch
~~~

Các tỷ lệ chỉ minh họa. Với hệ thống ít khách hàng nhưng mỗi tenant có lưu lượng lớn, có thể bật theo tenant cụ thể thay vì tỷ lệ người dùng. Với chức năng có rủi ro cao như thanh toán, nên bắt đầu bằng tài khoản nội bộ có dữ liệu kiểm thử phù hợp và có điều kiện dừng rõ ràng.

Một lần tăng tỷ lệ là **một thay đổi vận hành**, phải ghi nhận ai bật, thời điểm, cấu hình trước/sau và số liệu đi kèm. Không mở rộng chỉ vì vài phút không thấy HTTP 500; có thể cần thời gian để giao dịch bất đồng bộ hoàn thành, cache hết hạn hoặc quy trình nghiệp vụ dài bộc lộ sự cố.

### Chốt điều kiện ở mỗi bước

Trước khi tăng phạm vi, kiểm tra:

- Tỷ lệ lỗi, timeout, p95/p99 latency của các endpoint liên quan.
- Kết quả nghiệp vụ: tỷ lệ checkout hoàn tất, thanh toán chưa rõ kết quả, hoàn tiền, gửi đơn thành công.
- Database connection, CPU, queue lag, mức sử dụng quota của dependency.
- Không có xu hướng tăng dữ liệu sai, backfill backlog hoặc event xử lý trùng.
- Bộ phận hỗ trợ và nhóm vận hành có đủ thông tin phản hồi.
- Đã định nghĩa người được phép tắt cờ và kênh xử lý sự cố.

Không dùng một ngưỡng chung cho mọi chỉ số; quy định điều kiện giữ, tăng, dừng và quay lại theo SLO và mức rủi ro của tính năng cụ thể.

## 7. Percentage rollout cần phân nhóm ổn định

Một lỗi triển khai thường gặp là mỗi request gọi random để quyết định có bật cờ không:

~~~text
request 1: user A -> ON
request 2: user A -> OFF
request 3: user A -> ON
~~~

Điều này làm trải nghiệm không nhất quán. Với thanh toán, đặt hàng hoặc dữ liệu thay đổi theo variant, việc đảo đường xử lý giữa các request có thể gây sai nghiệp vụ.

**Deterministic bucketing** dùng một định danh ổn định và khóa cờ để tính nhóm cố định cho người dùng/tenant trong một khoảng rollout:

~~~text
bucket = stableHash(flagKey, allocationId, salt) % 10000

Nếu bucket thuộc [0, 500) và percentage = 5% -> ON
Ngược lại -> OFF
~~~

Đây là mô tả thuật toán, không phải mã hash được chọn cho production. Cần xác định cụ thể quy tắc chuẩn hóa ID, salt, version hash, cách dùng nhiều variant và sự ổn định giữa SDK/ngôn ngữ.

**Chọn đơn vị phân nhóm phù hợp:**

- Theo **user ID** khi mục tiêu là trải nghiệm độc lập cho từng người dùng.
- Theo **tenant/account ID** khi nhiều người trong cùng tổ chức phải thấy cùng chức năng.
- Theo **order/workflow ID** nếu một giao dịch cần dùng nhất quán cùng variant từ đầu đến cuối.
- Theo **instance** khi đang kiểm tra khả năng vận hành của một nhóm pod, nhưng khó suy ra trực tiếp tác động người dùng.

Nếu người dùng chưa đăng nhập, việc phân nhóm bằng session hoặc anonymous ID cần quy tắc chuyển tiếp khi đăng nhập để tránh thay đổi đột ngột. Không dùng email hay dữ liệu cá nhân thô trong log hoặc báo cáo phân nhóm khi không cần thiết.

### Nguyên tắc sticky decision

Khi một phiên làm việc hoặc workflow đã bắt đầu với variant A, các bước tiếp theo có thể cần giữ nguyên variant A dù tỷ lệ rollout đã thay đổi. Lưu **phiên bản chính sách hoặc quyết định variant** trong ngữ cảnh giao dịch nếu điều này ảnh hưởng kết quả.

Ví dụ Order Service tính giá theo thuật toán v2 khi tạo bản nháp đơn. Khi xác nhận đơn sau vài phút, không tự ý dùng v1 vì cờ vừa bị tắt nếu việc thay đổi thuật toán giữa chừng gây sai giá. Thay vào đó, thiết kế trạng thái nghiệp vụ, hạn hiệu lực báo giá và chính sách xử lý đơn đang xử lý rõ ràng.

## 8. Ví dụ Java/Spring Boot: điều hướng hai đường xử lý

Giả sử Checkout Service đang có luồng cũ và chuẩn bị luồng mới. Hãy đặt quyết định cờ ở một vị trí rõ ràng, sử dụng bối cảnh đã xác thực và ghi nhận variant được chọn.

~~~java
package example.checkout;

import org.springframework.stereotype.Service;

record CheckoutCommand(
    String cartId,
    String deliveryAddressId
) {}

record CallerContext(
    String tenantId,
    String userId
) {}

record CheckoutResult(
    String orderId,
    String status
) {}

interface FeatureDecision {
    boolean isEnabled(String flagKey, CallerContext caller);
}

interface CheckoutFlow {
    CheckoutResult execute(
        CheckoutCommand command,
        CallerContext caller
    );
}

@Service
final class CheckoutRouter {
    private static final String FLAG_KEY = "checkout.new-flow.v2";

    private final FeatureDecision decisions;
    private final CheckoutFlow legacy;
    private final CheckoutFlow next;

    CheckoutRouter(
        FeatureDecision decisions,
        LegacyCheckoutFlow legacy,
        NewCheckoutFlow next
    ) {
        this.decisions = decisions;
        this.legacy = legacy;
        this.next = next;
    }

    CheckoutResult execute(
        CheckoutCommand command,
        CallerContext caller
    ) {
        // Xác thực và phân quyền phải được kiểm tra ở lớp phù hợp
        // trước khi gọi router; flag không thay authorization.
        boolean newEnabled = decisions.isEnabled(FLAG_KEY, caller);

        if (newEnabled) {
            return next.execute(command, caller);
        }
        return legacy.execute(command, caller);
    }
}
~~~

LegacyCheckoutFlow và NewCheckoutFlow là các thành phần triển khai CheckoutFlow do ứng dụng cung cấp. Interface FeatureDecision được thực hiện bằng cấu hình hoặc SDK feature flag có chính sách fail-safe. Ví dụ minh họa **điểm điều hướng**, không phải toàn bộ use case checkout.

Thiết kế này giúp:

- Gói quyết định chọn nhánh vào một service rõ ràng.
- Tránh rải các lệnh if(flag) tùy tiện ở nhiều controller/repository.
- Giữ một contract CheckoutResult mà cả hai đường xử lý cùng đáp ứng.
- Có thể test riêng chế độ OFF, ON và khi flag provider lỗi.
- Tách lỗi do tính năng mới khỏi lỗi do authorization, cấu hình database hoặc hạ tầng chung.

Nhưng cần cẩn trọng: **không phải mọi thao tác đều có thể chạy lại bằng nhánh khác sau khi lỗi**. Một lệnh thanh toán đã được gửi đi mà timeout có thể đã trừ tiền. Không được tự động thử lại qua legacy checkout khi new checkout lỗi nếu không có idempotency và trạng thái giao dịch rõ ràng. Đường chuyển nhánh phải quyết định **trước khi tạo side effect** hoặc có cơ chế phục hồi nghiệp vụ được thiết kế.

### 8.1. Tách lớp quyết định khỏi logic nghiệp vụ

Nên để FeatureDecision trả quyết định dựa trên người gọi và bối cảnh, trong khi các luồng xử lý giữ phần tính toán hoặc điều phối riêng. Nếu mọi lớp đều tự gọi flag provider, cùng một request có thể nhận quyết định khác nhau vì cấu hình đổi giữa chừng hoặc cache của các instance chưa đồng bộ.

Một cách là tạo feature decision snapshot ở đầu request rồi truyền nó xuống tầng ứng dụng có liên quan. Với quy trình async nhiều ngày, nên lưu variant hoặc schema version cần thiết trong trạng thái nghiệp vụ hoặc payload event nếu hành vi downstream phụ thuộc vào phiên bản.

### 8.2. Kết quả không thành công của flag provider

Nếu dịch vụ quản lý cờ không khả dụng, hệ thống cần một chính sách đã định:

- Release flag của chức năng mới thường có thể **fallback về OFF** khi chưa có trạng thái đáng tin cậy.
- Một cờ tắt chức năng nguy hiểm trong sự cố có thể yêu cầu **ưu tiên quyết định OFF từ nguồn local đã được xác nhận** để không bật nhầm.
- Dữ liệu cached có thể dùng trong giới hạn tuổi, nhưng phải biết đang dùng quyết định stale.
- Với tác vụ đang xử lý, không đổi variant giữa chừng nếu điều đó làm sai trạng thái.
- Cờ phân quyền hoặc tuân thủ không được mặc định “cho phép” chỉ vì config provider lỗi; dùng cơ chế authorization độc lập và fail closed khi cần.

Không có một default an toàn cho **tất cả** cờ. An toàn hay không phụ thuộc hậu quả nghiệp vụ của ON/OFF. Cần diễn tả fail-safe theo từng cờ thay vì đặt toàn hệ thống mặc định true hoặc false một cách mù quáng.

## 9. Feature flag, canary deployment và blue-green khác nhau thế nào?

Các kỹ thuật thường kết hợp nhưng không đồng nghĩa.

### 9.1. Feature flag

- **Đơn vị điều khiển:** hành vi logic trong ứng dụng.
- **Quyết định:** tính năng A hay B được sử dụng.
- **Có thể:** cùng một phiên bản binary phục vụ cả hai hành vi.
- **Rủi ro:** các nhánh cũ/mới cùng tồn tại; consistency phụ thuộc thiết kế.
- **Ví dụ:** bật thuật toán đề xuất mới cho nhóm nội bộ.

### 9.2. Canary deployment

- **Đơn vị điều khiển:** lưu lượng tới các phiên bản deployment.
- **Quyết định:** bao nhiêu traffic tới version mới so với version cũ.
- **Có thể:** đo startup, resource, memory leak và tính tương thích của binary.
- **Rủi ro:** cả request sử dụng version mới có thể nhận hành vi mới nếu không có flag.
- **Ví dụ:** đưa 2% request qua pod v2 để kiểm tra Java runtime hoặc thư viện mới.

### 9.3. Blue-green deployment

- **Đơn vị điều khiển:** hai môi trường/nhóm instance tương đương đang sẵn sàng.
- **Quyết định:** định tuyến phần lớn traffic từ nhóm blue sang green.
- **Có thể:** giảm thời gian chuyển phiên bản nếu lưu lượng có thể đổi lại.
- **Rủi ro:** dữ liệu, schema và side effect đã được thay đổi có thể làm reverse switch không an toàn.
- **Ví dụ:** đổi router từ release đang chạy sang release mới sau kiểm tra readiness.

### So sánh ngắn

| Kỹ thuật | Điều chỉnh bằng gì? | Có nhất thiết cần cả hai phiên bản code? | Thuộc tính kiểm tra mạnh |
| --- | --- | --- | --- |
| Feature flag | Quy tắc cấu hình runtime | Không; thường cùng binary chứa hai nhánh | Hành vi tính năng theo nhóm người dùng |
| Canary deployment | Tỷ lệ traffic giữa instance/version | Có hai tập instance hoặc version đang phục vụ | Rủi ro vận hành của binary mới |
| Blue-green | Chuyển traffic giữa hai môi trường | Có hai nhóm deployment | Chuyển cutover và khả năng trở lại môi trường cũ |

Một release quan trọng có thể dùng **canary để triển khai binary**, sau đó dùng **feature flag để bật hành vi** trong các instance đã sẵn sàng. Cả hai trục cần được theo dõi để biết lỗi do bản triển khai hay do nhánh tính năng.

## 10. Triển khai nhiều microservice: bài toán version và tương thích

Trong microservices, các service thường deploy độc lập. Khi Order Service gọi Pricing Service, không thể giả định tất cả instance cùng được nâng cấp ngay một thời điểm.

~~~text
Thời điểm T0:
  Order v1 ---> Pricing v1

Thời điểm T1:
  Order v1 ---> Pricing v1 / Pricing v2 (cùng hoạt động)

Thời điểm T2:
  Order v1/v2 ---> Pricing v2

Thời điểm T3:
  Tất cả phiên bản hỗ trợ hợp đồng mới
  -> mới bật tính năng phụ thuộc hợp đồng mới
~~~

Nếu tính năng chỉ hoạt động khi **mọi service nhận dạng trường mới**, việc bật nó sớm có thể khiến message lỗi hoặc consumer không xử lý được.

### Các nguyên tắc khi nhiều phiên bản cùng tồn tại

1. **Backward-compatible API:** thêm trường tùy chọn, giữ hợp đồng cũ trong thời gian chuyển tiếp, không đổi ý nghĩa trường âm thầm.
2. **Consumer tolerant theo schema đã thỏa thuận:** consumer cũ hiểu hoặc bỏ qua trường mới phù hợp; dữ liệu bắt buộc phải được version hóa rõ.
3. **Không thay đổi enum vô điều kiện:** consumer cũ có thể lỗi khi gặp giá trị enum mới.
4. **Có compatibility test:** kiểm tra producer mới với consumer cũ và ngược lại trong phạm vi được hỗ trợ.
5. **Đường cũ luôn hợp lệ khi cờ OFF:** tránh để nhánh legacy phụ thuộc vào schema hoặc API đã bị xóa.
6. **Chặn activation bằng prerequisite:** chỉ bật khi tất cả service cần thiết có khả năng phục vụ hợp đồng mới.

Đây là nơi tách deploy và release phát huy tác dụng: nhóm có thể đưa code **hiểu giao thức mới** ra toàn hệ thống trước, rồi mới bắt đầu tạo dữ liệu mới theo giao thức đó.

## 11. Expand–contract cho thay đổi cơ sở dữ liệu

Feature flag không thể cứu một bản deploy đã xóa cột mà service cũ còn cần. Thay đổi schema phải được thực hiện theo các bước tương thích.

Ví dụ cần đổi cột customer_name sang first_name và last_name:

~~~text
Giai đoạn 1 — Expand:
  ALTER TABLE thêm first_name, last_name (nullable lúc đầu)
  Ứng dụng cũ vẫn đọc customer_name
  Ứng dụng mới có thể hiểu cả cũ lẫn mới

Giai đoạn 2 — Migrate:
  Backfill dữ liệu cũ theo lô
  Áp dụng dual-write hoặc chiến lược ghi tương thích nếu cần
  Theo dõi độ đầy đủ và sai lệch dữ liệu

Giai đoạn 3 — Release:
  Bật read-from-new-fields cho một nhóm nhỏ
  Đối chiếu kết quả và tăng phạm vi
  Chỉ chuyển hoàn toàn khi dữ liệu đã sẵn sàng

Giai đoạn 4 — Contract:
  Ngừng đường đọc/ghi cũ theo kế hoạch
  Xác nhận không còn phiên bản cũ sử dụng schema cũ
  Sau đó mới xóa customer_name
~~~

Không nhất thiết mọi migration đều cần dual-write. Dual-write cũng có nguy cơ cập nhật lệch giữa hai biểu diễn; phải có nguồn dữ liệu chuẩn, quy tắc chuyển đổi, kiểm thử và đo đạc phù hợp.

Nếu đã chuyển sang ghi dữ liệu chỉ đọc được bởi version mới, **tắt feature flag có thể không đủ để rollback**. Hành vi rollback phải dựa trên compatibility và migration contract, không chỉ một nút OFF.

### 11.1. Thay đổi có tính phá hủy cần kế hoạch riêng

Các thao tác như xóa cột, đổi khóa chính, tách bảng, thay cơ chế tính tiền hoặc ghi event format mới có thể khiến dữ liệu cũ/ mới không còn tương thích. Trước khi bật cờ, xác nhận đường cũ vẫn đọc được dữ liệu do đường mới tạo và ngược lại trong thời gian hỗ trợ, hoặc tuyên bố rõ giới hạn rollback với biện pháp xử lý dữ liệu.

Không dùng feature flag để bỏ qua migration rollback plan khi thay đổi dữ liệu không thể đảo ngược.

## 12. Tách release trong kiến trúc event-driven

Luồng bất đồng bộ khiến “bật cờ cho 5% người dùng” không còn là một quyết định thuần HTTP:

~~~text
User
  |
  v
Order Service --- lưu order + event ----> Broker
                                          |
                               +----------+----------+
                               |                     |
                         Inventory Consumer   Billing Consumer
                               |                     |
                          cập nhật hàng        tạo phí/biên lai
~~~

Một request được bật variant mới có thể phát message được xử lý nhiều phút sau. Nếu consumer chỉ truy vấn giá trị feature flag **ở thời điểm nhận message**, kết quả có thể khác thời điểm tạo event.

Những câu hỏi cần giải quyết:

- Variant được chọn ở producer hay mỗi consumer đánh giá riêng?
- Nếu feature flag đã OFF sau khi event được phát, consumer xử lý event cũ thế nào?
- Dữ liệu trong event có schema version, business context hoặc feature decision cần thiết không?
- Nếu consumer không hỗ trợ event version mới, có được publish không?
- Message bị retry từ DLQ sau nhiều ngày có còn hợp đồng hợp lệ không?

Thường nên lưu **business facts và schema version** trong event, không phụ thuộc vào cấu hình thay đổi liên tục để diễn giải một dữ kiện đã xảy ra. Khi variant ảnh hưởng ý nghĩa nghiệp vụ, cần ghi rõ phiên bản hoặc quyết định đủ để consumer xử lý nhất quán. Không đưa toàn bộ nội bộ flag rules hoặc dữ liệu nhạy cảm vào broker payload.

Với event replay, hãy phân biệt **đánh giá cờ cho thao tác mới** và **xử lý lại sự kiện đã được quyết định trong quá khứ**. Replay không nên tự thay đổi tiền hoặc quyền sở hữu chỉ vì cờ hiện tại đã khác.

## 13. Dark launch, shadow traffic và chuẩn bị dữ liệu

**Dark launch** triển khai đường xử lý mới nhưng chưa công bố kết quả cho người dùng. Mục đích là kiểm tra khả năng chạy trong production hoặc thu thập tín hiệu trước khi release chính thức.

**Shadow traffic** sao chép request để đường mới xử lý ở chế độ quan sát, sau đó so sánh kết quả mà không dùng kết quả đó để quyết định phản hồi chính.

~~~text
Client request
       |
       v
Legacy path ----------> Response chính cho người dùng
       |
       +--- bản sao đã kiểm soát ----> New calculation
                                       |
                                       v
                                 Compare / metrics
                                 (không side effect thật)
~~~

Điều kiện thiết yếu:

- Đường shadow **không tạo side effect nghiệp vụ** như trừ tiền, gửi SMS, giữ hàng hoặc gửi đơn tới đối tác.
- Tuân thủ quyền, bảo mật và giới hạn dùng dữ liệu production; không tự sao chép PII sang môi trường thiếu bảo vệ.
- Tránh gấp đôi tải lên database hoặc service downstream mà không có quota/bulkhead.
- Phân biệt chênh lệch hợp lệ do thời gian/cache với sai lệch thực trong thuật toán.
- Không phát shadow event vào topic production mà consumer thật sẽ xử lý.
- Khi không thể bảo đảm tính an toàn của shadow side effect, chỉ kiểm thử trên fixture hoặc môi trường staging phù hợp.

Dark launch hữu ích để kiểm tra khả năng vận hành và phát hiện sai lệch tính toán, nhưng **không tự thay thế** rollout thực vì đường shadow có thể khác đường chính về áp lực tải, caching hoặc tương tác người dùng.

## 14. Feature flag và dữ liệu nghiệp vụ có trạng thái

Tính năng UI thuần đọc thường dễ tắt. Những tính năng **ghi dữ liệu, gửi message hoặc gọi API có side effect** đòi hỏi chính sách mạnh hơn.

### 14.1. Đơn hàng và thanh toán

Nếu luồng checkout mới dùng logic thanh toán khác, phải phân biệt:

- Request chưa bắt đầu: có thể chọn nhánh theo cờ.
- Request đã tạo payment intent: phải tiếp tục bằng state machine/idempotency phù hợp, không “thử lại” bằng nhánh cũ như một request mới.
- Đơn hàng đã lưu ở schema mới: đường cũ có đọc và hoàn tất được không?
- Payment timeout: không suy ra chưa trừ tiền; phải đối soát trước khi quyết định retry.
- Khi tắt cờ: xử lý thế nào với các giao dịch đã bắt đầu trên nhánh mới?

Feature flag nên điều khiển **điểm bắt đầu một workflow mới**, còn workflow đã bắt đầu nên đi tiếp theo quy tắc lưu trạng thái. Với những chuyển đổi không thể đảo ngược, cần runbook xử lý in-flight transactions và giới hạn rollback rõ ràng.

### 14.2. Tìm kiếm hoặc recommendation

Đây thường là ứng viên dễ rollout hơn:

- Kết quả mới có thể thử ở một nhóm người dùng.
- Khi lỗi, chuyển về thuật toán cũ hoặc cache đủ điều kiện.
- Có thể so sánh độ trễ, click-through và tỷ lệ chuyển đổi theo nhóm.
- Cần bảo đảm cache key có variant để không lẫn dữ liệu hoặc kết quả của hai thuật toán.

### 14.3. Thay đổi dữ liệu có tính toàn vẹn

Nếu nhánh mới ghi một loại bản ghi mà nhánh cũ không hiểu, việc bật cờ dù chỉ 1% có thể làm hỏng quy trình nghiệp vụ của nhóm đó. Cần kiểm thử tương thích, migration, phục hồi và cách xử lý dữ liệu tồn tại trước khi mở cờ cho bất kỳ khách hàng nào.

## 15. Vận hành feature flag trong môi trường phân tán

Trong microservices, cùng một flag có thể được đánh giá tại nhiều pod, nhiều region và nhiều service. Cần làm rõ **tính nhất quán mong muốn**.

### 15.1. Cached configuration và độ trễ đồng bộ

Nếu mỗi instance cache cấu hình 30 giây, lúc tắt cờ có thể tồn tại khoảng thời gian một số instance vẫn sử dụng giá trị cũ. Do đó “tắt trong vài mili giây” chỉ đúng nếu toàn bộ pipeline từ control plane đến ứng dụng thực sự bảo đảm mức trễ đó.

Quy trình nên xác định:

- Refresh bằng streaming, polling hay TTL?
- Giá trị local được phép stale bao lâu?
- Khi mất kết nối control plane, instance tiếp tục dùng last-known-good hay default?
- Làm sao kiểm tra **effective flag state** đang được các instance sử dụng?
- Khi cần dừng khẩn cấp, SLA tắt cờ thực tế là bao lâu?
- Trong multi-region, có độ trễ đồng bộ hoặc khác biệt chính sách theo region không?

Một nút OFF trên dashboard quản lý cờ chưa phải bằng chứng toàn bộ traffic đã về đường cũ. Cần có telemetry đo thực tế tỷ lệ request đi qua các variant.

### 15.2. Phân quyền thay đổi cấu hình

Flag là **control plane ảnh hưởng hành vi production**. Nên áp dụng:

- Role-based access control cho người được tạo, sửa, bật/tắt và xóa flag.
- Audit trail: actor, thời điểm, môi trường, quy tắc cũ/mới, lý do.
- Phê duyệt phù hợp với thay đổi có rủi ro cao; kill switch khẩn cấp cần cơ chế thao tác nhanh đã được cấp quyền.
- Phân tách staging/production; không để thay đổi môi trường test tự động ảnh hưởng production.
- Cảnh báo khi flag bị bật/tắt ngoài lịch hoặc tăng tỷ lệ quá nhanh.
- Quản lý API token của flag service như secret; không nhúng token quản trị vào frontend.

**Không dựa vào tên flag để bảo mật.** Một key khó đoán vẫn có thể bị lộ; quyền ở backend và chính sách quản lý cấu hình mới là hàng rào bảo vệ.

### 15.3. Tránh phụ thuộc đồng bộ nguy hiểm

Nếu mỗi request phải gọi mạng đến feature service để quyết định ON/OFF, feature service lỗi có thể làm toàn hệ thống chậm hoặc mất khả dụng. SDK thường sử dụng cache/streaming hoặc đánh giá local phù hợp. Cần thiết kế timeout, tải khởi động, rate limit và fail-safe rõ ràng.

Không cho phép việc quản lý cờ trở thành một dependency single point of failure của mọi request cốt lõi.

## 16. Telemetry: đo theo variant và theo kết quả nghiệp vụ

Bật cờ 5% không có ý nghĩa nếu không biết nhóm đó có trải nghiệm tốt hơn, kém hơn hay không nhận đủ điều kiện thực tế. Cần kết hợp **technical metrics** và **business metrics**.

| Nhóm chỉ số | Cần theo dõi |
| --- | --- |
| Lưu lượng | Request rate theo route, service, variant, region khi hợp lý |
| Độ tin cậy | Error rate, timeout, circuit breaker, fallback rate |
| Độ trễ | p50/p95/p99 latency, downstream latency, DB connection wait |
| Kết quả nghiệp vụ | Checkout completed, abandoned, rejected, refunded, payment pending |
| Data correctness | Sai lệch kết quả, mismatch đối soát, dữ liệu migrate còn thiếu |
| Hạ tầng | CPU/memory, cache hit, connection pool, queue lag, quota |
| Flag runtime | Số evaluation ON/OFF, flag config age, evaluation failures |
| Rollout | Tỷ lệ traffic thực qua biến thể, thay đổi target cohort |

Khi thiết kế metrics, dùng nhãn có **cardinality thấp và tập giá trị được giới hạn** như service, route template, variant, region, outcome. Không gắn user_id, order_id, email hay trace_id vào metric label. Khi cần điều tra một giao dịch, sử dụng log/trace có kiểm soát truy cập.

### 16.1. Đánh giá guardrails

Một rollout có thể dùng bộ điều kiện ví dụ:

~~~text
Nếu:
- Error rate của variant mới vượt ngưỡng rủi ro đã định
- p95 latency tăng vượt mức được chấp nhận
- Tỷ lệ checkout hoàn tất giảm theo tiêu chí nghiệp vụ
- Số giao dịch payment pending bất thường
Thì:
- Dừng tăng phạm vi
- Tắt cờ nếu quyết định an toàn
- Ghi nhận mốc và nguyên nhân
- Điều tra trước khi thử rollout lại
~~~

Cần xem kích thước mẫu và độ biến động; với tỷ lệ 1% traffic, một vài lỗi có thể khiến tỷ lệ dao động mạnh. Không lấy mỗi biến động nhỏ làm bằng chứng chắc chắn. Với lỗi có tác động lớn như tính sai tiền hoặc lộ dữ liệu, **một bằng chứng đáng tin cậy có thể đủ để dừng ngay**, không chờ thống kê đủ lớn.

### 16.2. Exposure và phân tích experiment

Một **experiment flag** không chỉ quyết định ai thuộc nhóm A/B. Để phân tích tác động có cơ sở, cần ghi nhận người dùng thực sự **được tiếp xúc với biến thể**, cách chọn nhóm, thời gian và tiêu chí đo lường.

Lưu ý:

- Phân bổ ngẫu nhiên nhưng ổn định theo đơn vị phù hợp; hạn chế việc một người chuyển nhóm.
- Kiểm tra sample-ratio mismatch: số người ở mỗi nhóm có phù hợp kỳ vọng không?
- Chống contamination: người trong cùng tenant có tương tác chéo hoặc dùng nhiều thiết bị không?
- Phân biệt “được phân vào nhóm” và “đã thấy/đã sử dụng tính năng”.
- Có thước đo guardrail về lỗi, latency và an toàn nghiệp vụ trước khi tối ưu conversion.
- Định nghĩa khoảng đo đủ thời gian; hiệu ứng dài hạn có thể khác phản ứng ban đầu.

Feature rollout để giảm rủi ro và A/B experiment để suy luận tác động có mục đích khác nhau. Có thể dùng cùng nền tảng flag nhưng tiêu chí quyết định và phân tích không nên bị trộn lẫn.

## 17. Kiểm thử các trạng thái cờ

Việc giữ hai đường xử lý trong production đòi hỏi test cả hai. Không nên để test chỉ chạy cấu hình mặc định và bỏ quên đường ON.

### 17.1. Unit test

- OFF → gọi đường xử lý cũ.
- ON + đủ điều kiện → gọi đường mới.
- ON nhưng tenant không đủ điều kiện → theo policy trả về OFF.
- Flag provider lỗi/không trả dữ liệu → đi theo fail-safe đã định.
- Cả hai đường giữ cùng API contract và phân quyền.
- Bối cảnh tenant/user lấy từ dữ liệu đã xác thực, không lấy tùy ý từ body.

### 17.2. Integration test

- Flag ON/OFF trên cùng database schema và các phiên bản service đang được hỗ trợ.
- Migrate schema trước khi ON; đường cũ đọc được dữ liệu trong thời gian tương thích.
- Event schema mới không làm consumer cũ crash.
- Cache không lẫn dữ liệu/variant nếu kết quả khác nhau.
- Quyết định variant được truyền hoặc lưu đúng trong workflow async.
- Một flag OFF không khiến in-flight payment chạy lại hoặc tạo duplicate.
- Khi config service mất kết nối, ứng dụng tuân thủ policy cached/default và vẫn có observability.

### 17.3. Rollout test

- Nhóm allowlist/internal được ON đúng; nhóm ngoài không bị bật.
- Tỷ lệ 0% và 100% có ý nghĩa chính xác theo policy.
- Một subject ID được gán ổn định qua nhiều request và nhiều instance.
- Khi tăng percentage, nhóm cũ có giữ assignment nếu đó là yêu cầu?
- Đổi salt hoặc hash algorithm có tác động gì lên cohort?
- Thay đổi target rule có làm chuyển nhóm giữa workflow không?
- Kill switch có thực sự đưa traffic về đường cũ trong giới hạn thời gian cam kết?

Kiểm thử cờ không đồng nghĩa chạy tất cả **2^N** tổ hợp nếu có nhiều cờ. Nên hạn chế phụ thuộc giữa các cờ, mô hình hóa những trạng thái thực sự được hỗ trợ và kiểm tra các tương tác có rủi ro cao.

## 18. Ví dụ kiểm thử router với fake FlagDecision

Test minh họa tập trung vào điểm quyết định, chưa cần khởi động toàn bộ Spring application context:

~~~java
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class CheckoutRouterTest {

    @Test
    void flagOffUsesLegacyFlow() {
        FeatureDecision decisions = (flag, caller) -> false;
        LegacyCheckoutFlow legacy = mock(LegacyCheckoutFlow.class);
        NewCheckoutFlow next = mock(NewCheckoutFlow.class);

        CheckoutCommand command = new CheckoutCommand(
            "cart-1", "address-1"
        );
        CallerContext caller = new CallerContext(
            "tenant-1", "user-1"
        );
        CheckoutResult expected = new CheckoutResult(
            "order-1", "CREATED"
        );

        when(legacy.execute(any(), any())).thenReturn(expected);

        CheckoutRouter router =
            new CheckoutRouter(decisions, legacy, next);

        CheckoutResult result = router.execute(command, caller);

        assertThat(result).isEqualTo(expected);
        verify(legacy).execute(command, caller);
        verifyNoInteractions(next);
    }

    @Test
    void flagOnUsesNewFlow() {
        FeatureDecision decisions = (flag, caller) -> true;
        LegacyCheckoutFlow legacy = mock(LegacyCheckoutFlow.class);
        NewCheckoutFlow next = mock(NewCheckoutFlow.class);

        CheckoutCommand command = new CheckoutCommand(
            "cart-2", "address-2"
        );
        CallerContext caller = new CallerContext(
            "tenant-1", "user-2"
        );

        CheckoutResult expected = new CheckoutResult(
            "order-2", "CREATED"
        );

        when(next.execute(any(), any())).thenReturn(expected);

        CheckoutRouter router =
            new CheckoutRouter(decisions, legacy, next);

        CheckoutResult result = router.execute(command, caller);

        assertThat(result).isEqualTo(expected);
        verify(next).execute(command, caller);
        verifyNoInteractions(legacy);
    }
}
~~~

Ví dụ dùng Mockito và AssertJ thường có trong Spring Boot Test, đồng thời giả định hai lớp LegacyCheckoutFlow và NewCheckoutFlow là implementation cụ thể của CheckoutFlow. Để test policy thực tế, còn cần test riêng phần đánh giá target, fallback, consistency và integration với flag SDK/provider.

**Không coi unit test router là đủ cho release.** Các lỗi lớn thường nằm ở schema, event format, kết quả nghiệp vụ, thread/transaction boundary và side effect bên ngoài.

## 19. Tắt cờ nhanh và rollback thật sự khác nhau

Một cờ OFF chỉ giúp nếu đường cũ vẫn còn đúng và hệ thống đã thiết kế cách quay lại.

### Khi OFF có thể đủ

- Tính năng mới chỉ thay kết quả đề xuất, có fallback an toàn.
- UI hiển thị/ẩn một thành phần độc lập không ảnh hưởng dữ liệu đã lưu.
- Thuật toán tính toán mới chưa ghi dữ liệu không tương thích hoặc chưa tạo side effect.
- Điều khiển tải một tính năng tùy chọn có thể tắt nhanh.

### Khi cần xử lý thêm

- Database migration đã xóa cột hoặc thay đổi dữ liệu không thể đảo ngược.
- Event mới đã được gửi và consumer cũ không đọc được.
- Người dùng đã bắt đầu luồng thanh toán và có trạng thái pending.
- Đơn hàng hoặc bản ghi đã được tạo bằng format chỉ đường mới hiểu.
- Cache đã lưu kết quả theo schema mới; đường cũ đọc sai.
- Một số instance chưa nhận cấu hình OFF do mất kết nối control plane.

Runbook nên xác định: điều kiện tắt cờ, thẩm quyền thực hiện, hiệu lực, telemetry xác nhận, cách xử lý giao dịch đang chạy, cách sửa dữ liệu đã ghi, quy trình rollback binary nếu cần và bước thông báo cho các bên liên quan.

**Kill switch không phải phép hoàn tác dữ liệu.** Mục tiêu là dừng phát sinh lỗi mới và giảm ảnh hưởng; sửa dữ liệu hoặc phục hồi state cần quy trình riêng.

## 20. Feature flag và khả năng phục hồi khi control plane lỗi

Một dịch vụ cấu hình flag có thể trở thành phụ thuộc nguy hiểm nếu mọi request phải chờ mạng để đánh giá cờ. Khi nó mất kết nối, hệ thống cần phản hồi xác định.

Một thiết kế thường có:

~~~text
Control Plane (quản lý flags)
         |
     stream/poll
         v
SDK cache / local evaluator
         |
  evaluate(context)
         |
      ON / OFF
         |
    business service
~~~

Các chính sách cần lựa chọn có cơ sở:

- Last-known-good decision tối đa được giữ bao lâu?
- Nếu SDK chưa tải config lúc startup, service có khởi động được không?
- Với release flag, OFF có an toàn không?
- Với operational kill switch, nếu cache đang ON khi có yêu cầu OFF thì hệ thống nhận cập nhật bằng cách nào?
- Với workflow dài, dùng snapshot decision đã lưu hay đánh giá lại?
- Có metric cảnh báo flag evaluation failure và config staleness không?

Không tự áp đặt một phương án lên mọi service. Một quyết định stale có thể chấp nhận cho layout mới, nhưng có thể không chấp nhận cho chính sách liên quan đến quyền hoặc giá cuối.

## 21. Dọn feature flag sau rollout

Sau khi tính năng mới đã phục vụ 100% traffic và ổn định, một **release flag** thường cần được loại bỏ theo kế hoạch.

Nếu để nhiều cờ tồn tại lâu, sẽ có các vấn đề:

- Code có nhánh không còn được sử dụng nhưng vẫn phải duy trì.
- Unit test và integration test phải xử lý thêm nhiều tổ hợp.
- Logic mới có thể phụ thuộc nhầm vào nhánh cũ.
- Không rõ trạng thái production thật khi đọc source.
- Nhân viên vận hành có thể vô tình bật lại tính năng đã lỗi thời.
- Migrated schema hoặc API cũ khó được loại bỏ vì vẫn còn đường code tham chiếu.

Một quy trình cleanup:

1. Xác nhận 100% đối tượng mục tiêu dùng nhánh mới trong khoảng thời gian đủ tin cậy.
2. Đo không còn lưu lượng hợp lệ qua nhánh cũ, kể cả batch và consumer chậm.
3. Đảm bảo không còn transaction/event/data version cần đường cũ.
4. Thay router bằng đường xử lý mới mặc định.
5. Xóa code legacy, flag key, quy tắc targeting và test nhánh cũ trong cùng phạm vi phù hợp.
6. Sau khi phiên bản mới đã ổn định, thực hiện bước contract schema/API nếu đã đủ điều kiện.
7. Cập nhật tài liệu, dashboard, runbook và đóng vòng đời flag.

Không xóa flag/nhánh cũ trước khi xác nhận rollout đã xong và đường quay lại không còn cần thiết. Với operational kill switch, có thể giữ lâu dài theo thiết kế, nhưng cần owner và kiểm thử định kỳ.

## 22. Lỗi thiết kế thường gặp

**“Đã deploy nghĩa là đã release.”** Làm cho mọi người dùng tiếp xúc với thay đổi cùng lúc và khó cô lập tác động.

**“Bật feature flag là thay được mọi kiểu rollback.”** Không đúng với migration phá hủy, side effect thanh toán hoặc message không tương thích.

**“Flag chỉ cần boolean và không cần owner.”** Thiếu owner, mục đích, default, telemetry và ngày kết thúc làm cờ tồn tại mãi.

**“Đánh giá ngẫu nhiên ở mỗi request là rollout 5%.”** Người dùng có thể liên tục đổi nhánh; cần phân nhóm ổn định theo subject phù hợp.

**“Kiểm tra cờ ở frontend là đủ.”** UI flag không phải authorization; server vẫn phải xác thực và kiểm soát quyền.

**“Mọi instance nhận OFF tức thì.”** Cache và kết nối control plane có độ trễ; cần đo effective state thực tế.

**“Tăng phần trăm càng nhanh càng tốt.”** Số liệu bất đồng bộ và chu kỳ sử dụng có thể cần thời gian trước khi bộc lộ lỗi.

**“Tắt flag sau khi new checkout lỗi rồi thử lại trên legacy.”** Nếu giao dịch đã tạo side effect, retry không có idempotency có thể tạo đơn hoặc charge trùng.

**“Bật 1% là chỉ ảnh hưởng 1% hệ thống.”** Một số lỗi có tác động toàn cục như migration, shared cache, shared DB hoặc công việc background; phải đánh giá blast radius theo phụ thuộc, không chỉ tỷ lệ request.

**“Có canary deployment thì không cần release flag.”** Canary kiểm tra phiên bản runtime, còn release flag điều khiển hành vi; chúng có mục đích khác nhau và thường bổ sung nhau.

**“Thêm flag vào mọi if để an toàn.”** Quá nhiều cờ đan xen khiến behavior khó dự đoán và tăng số trạng thái cần kiểm thử.

**“Một khách hàng thành công nghĩa là đủ dữ liệu để mở 100%.”** Cần quan sát cả lỗi hiếm, hiệu năng, thời gian dài, dữ liệu và kết quả kinh doanh.

## 23. Mẫu kế hoạch rollout cho một chức năng cụ thể

Giả sử mục tiêu là thay thuật toán tính phí giao hàng trong Checkout Service.

| Giai đoạn | Trạng thái và đối tượng | Điều kiện tiếp tục |
| --- | --- | --- |
| Chuẩn bị | API/schema tương thích; flag OFF | Contract và integration tests đạt, có rollback plan |
| Deploy | Mã mới chạy production; chưa bật khách thật | Smoke test, latency/resource không bất thường |
| Internal | Nhân viên/test tenants sử dụng | Đối soát phí, log/trace và transaction chính xác |
| 1% | Cohort ổn định, giới hạn rủi ro | Error/latency và sai lệch phí trong ngưỡng |
| 5–25% | Tăng từ từ theo quan sát | Đủ mẫu, không có sự cố dữ liệu/side effect |
| 50–100% | Mở rộng khi an toàn | KPI nghiệp vụ và guardrails được chấp nhận |
| Cleanup | Nhánh mới thành mặc định | Không còn phụ thuộc đường cũ, dọn flag và code |

Các tỷ lệ và ngưỡng phải được thay bằng giá trị phù hợp quy mô và mức rủi ro. Ở hệ thống thanh toán, việc bật cho một tập tài khoản kiểm thử được kiểm soát trước có thể quan trọng hơn một percentage arbitrary.

### Các câu hỏi cần trả lời trước khi bấm ON

1. Khi ON, khách nào thực sự nhận hành vi mới? Rule có ổn định giữa nhiều pod/region không?
2. Đường cũ và đường mới có cùng contract API, event và dữ liệu không?
3. Các giao dịch đang chạy sẽ giữ variant hay đổi theo flag hiện tại?
4. Khi KMS, flag provider, database hoặc broker lỗi, fallback nào an toàn?
5. Nếu OFF sau 10 phút, dữ liệu đã viết bởi nhánh mới có còn được xử lý đúng không?
6. Dashboard có phân biệt được lỗi ở variant mới với lỗi toàn hệ thống không?
7. Đã có người trực, runbook, điều kiện dừng và thẩm quyền kill switch chưa?
8. Bao lâu mới đủ dữ liệu để quyết định tăng tỷ lệ?
9. Cơ chế audit có lưu được người thay đổi cờ và cấu hình cũ/mới không?
10. Khi rollout hoàn tất, ai chịu trách nhiệm xóa nhánh cũ và flag?

## 24. Bài tập tình huống: triển khai trước, bật sau

Một hệ thống thương mại điện tử có các service:

~~~text
Mobile/Web
   |
   v
API Gateway -> Order Service -> Pricing Service
                    |                  |
                    v                  v
               PostgreSQL          Redis cache
                    |
                    +--> Broker --> Payment Consumer
                    |
                    +--> Broker --> Notification Consumer
~~~

Nhóm triển khai chức năng **giảm giá thành viên v2**. Pricing Service trả thêm trường discountVersion; Order Service lưu snapshot giá; Payment Consumer cần tính tiền theo giá đã chốt. Nhóm muốn release cho khách hàng premium trước rồi tăng dần. Một số mobile client cũ vẫn chưa cập nhật.

**Yêu cầu thiết kế:**

1. Xác định thứ tự deploy của Pricing, Order và Payment Consumer để mọi phiên bản còn hoạt động đều hiểu dữ liệu cần thiết.
2. Đề xuất flag key, owner, mặc định và targeting theo account/tenant.
3. Giải thích lý do cần lưu discountVersion và giá đã xác nhận trong trạng thái đơn hàng, thay vì consumer hỏi lại flag hiện tại khi nhận event.
4. Mô tả quy trình bật: internal → nhóm nhỏ → tăng dần với các guardrail và điều kiện dừng.
5. Thiết kế metric để phát hiện sai lệch số tiền, độ trễ Pricing và tỷ lệ payment pending.
6. Xử lý tình huống đã gửi lệnh thanh toán rồi flag OFF; tránh tính tiền hoặc gửi lệnh hai lần.
7. Nêu thời điểm được xóa đường tính giá cũ, cấu hình flag và hợp đồng hỗ trợ mobile client cũ.

**Gợi ý hướng giải:**

- Triển khai các consumer hỗ trợ dữ liệu/phiên bản mới trước khi producer bắt đầu phát event có format mới; dùng API/event schema tương thích.
- Pricing và Order đều có thể xử lý chế độ OFF; giá đã chốt và version cần được lưu bền vững trong order, không tính lại do config đổi.
- Quyết định rollout theo account/tenant ổn định; kiểm tra entitlements/authorization độc lập với flag.
- Chỉ bật rộng sau khi đo kết quả đúng và latency; nếu phát hiện sai tiền, dừng ngay và có quy trình đối soát dữ liệu bị ảnh hưởng.
- Những giao dịch đã tạo payment intent tiếp tục theo state machine/idempotency; không tự chuyển sang đường cũ để thu tiền lần nữa.
- Dọn đường cũ khi các client/consumer/workflow cần nó đã hết thời hạn hỗ trợ, sau đó mới contract schema và loại bỏ flag theo kế hoạch.

## 25. Checklist áp dụng trong dự án microservices

Trước khi release một tính năng mới, đội phát triển nên có đầy đủ:

- **Phân tách hai thời điểm:** pipeline triển khai artifact và quyết định mở tính năng độc lập.
- **Cờ có chủ sở hữu:** định nghĩa mục đích, default, target, quyền đổi cấu hình, audit, expiry.
- **Tương thích:** API, database và event hợp đồng hoạt động trong giai đoạn nhiều phiên bản.
- **Đánh giá ổn định:** cùng người dùng hoặc workflow không đổi nhánh ngoài ý muốn.
- **An toàn nghiệp vụ:** authorization riêng, idempotency, dữ liệu đã ghi và side effect có quy tắc xử lý rõ.
- **Giới hạn sự cố:** có kill switch, khả năng tắt được đo thực tế, rollback binary và kế hoạch khôi phục dữ liệu khi cần.
- **Observability:** metrics/trace/log theo variant, release version, technical guardrails và business outcome.
- **Kiểm thử:** OFF/ON, lỗi provider, đa phiên bản, schema migration, async workflow, rollout targeting và khả năng phục hồi.
- **Quy trình tăng phạm vi:** có người chịu trách nhiệm, thời gian quan sát, tiêu chí tạm dừng/tắt rõ.
- **Dọn nợ kỹ thuật:** kết thúc release flag và loại bỏ nhánh cũ khi đã an toàn.

---

**Điểm cần nhớ:** Trong microservices, **deploy là đưa khả năng mới vào môi trường**, còn **release là quyết định ai được sử dụng khả năng đó và khi nào**. Feature flags và progressive delivery giúp giảm rủi ro, nhưng hiệu quả phụ thuộc vào khả năng tương thích giữa các service, tính đúng đắn của dữ liệu và side effect, phân nhóm ổn định, telemetry theo biến thể, quyền vận hành và kế hoạch xử lý sự cố. Triển khai trước rồi bật dần chỉ thực sự an toàn khi hệ thống có thể quan sát, dừng và phục hồi hành vi mới một cách có kiểm soát.
