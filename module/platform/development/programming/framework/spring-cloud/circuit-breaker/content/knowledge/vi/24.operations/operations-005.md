# Quy trình ép OPEN, reset và trả lại chế độ tự động có kiểm soát

Trong quá trình vận hành, đôi khi đội ngũ cần chủ động ngăn một ứng dụng tiếp tục gọi đến dependency đang gây sự cố. Ví dụ, Inventory đang quá tải, một hệ thống đối tác liên tục timeout hoặc một đợt triển khai khiến Payment trả lỗi hàng loạt. Circuit Breaker có thể tự chuyển sang OPEN dựa trên failure rate và slow-call rate, nhưng trong một số tình huống sự cố, người vận hành cần ép mạch mở ngay để giảm tải.

Sau khi nguyên nhân được xử lý, đội ngũ cần đưa Circuit Breaker trở lại cơ chế tự động một cách có kiểm soát. Việc ép OPEN, chuyển lại sang OPEN có thời gian chờ, reset về CLOSED và quan sát HALF_OPEN có tác động khác nhau đến lưu lượng, state và lịch sử thống kê.

Bài học trình bày quy trình vận hành với Resilience4j trong ứng dụng Spring Cloud CircuitBreaker: phân biệt OPEN với FORCED_OPEN, thực hiện thao tác quản trị qua registry, bảo vệ endpoint điều khiển, ghi audit, phục hồi qua HALF_OPEN và xử lý khi ứng dụng có nhiều replica.

## 1. Khi nào cần can thiệp trạng thái thủ công?

Thông thường Circuit Breaker tự quản lý state machine:

~~~text
                 lỗi hoặc lời gọi chậm vượt ngưỡng
          +------------------------------------------+
          |                                          v
       CLOSED ------------------------------------> OPEN
          ^                                          |
          |                                          | hết waitDuration
          |                                          v
          +---------------- thành công ---------- HALF_OPEN
                                                     |
                                                     | lỗi vượt ngưỡng
                                                     +------> OPEN
~~~

Ở CLOSED, lời gọi được phép và kết quả được ghi vào sliding window. Khi đủ số mẫu và tỷ lệ lỗi hoặc lời gọi chậm đạt ngưỡng, mạch chuyển sang OPEN. Sau waitDurationInOpenState, mạch chuyển sang HALF_OPEN để thăm dò. Nếu các lời gọi thăm dò đáp ứng điều kiện phục hồi, mạch trở về CLOSED; nếu không, nó quay lại OPEN.

Can thiệp thủ công có thể cần thiết khi:

- Dependency đang gây lỗi dây chuyền và cần ngừng nhận request mới ngay lập tức.
- Đội vận hành muốn cô lập một dependency trong khi đang rollback hoặc khắc phục sự cố.
- Một đợt bảo trì có kế hoạch yêu cầu ngừng gọi dependency.
- Cần giữ một dependency ở trạng thái không nhận traffic cho đến khi có xác nhận từ đội phụ trách.
- Circuit Breaker tự động chưa đủ mẫu để mở mạch nhưng tín hiệu vận hành bên ngoài đã xác nhận dependency không an toàn.

Không nên ép OPEN chỉ vì một cảnh báo đơn lẻ. Trước khi can thiệp, hãy xác định dependency, phạm vi ảnh hưởng, hành động fallback, số replica và người chịu trách nhiệm khôi phục.

## 2. Phân biệt OPEN, FORCED_OPEN và reset

Resilience4j có các trạng thái vận hành khác nhau. Ba thao tác thường bị nhầm lẫn là chuyển sang OPEN, ép FORCED_OPEN và reset.

| Thao tác | Kết quả | Hành vi sau thao tác |
| --- | --- | --- |
| Chuyển sang OPEN | Mạch ở trạng thái OPEN bình thường | Thời gian chờ OPEN được áp dụng; sau đó có thể chuyển sang HALF_OPEN theo cấu hình |
| Ép FORCED_OPEN | Mạch bị giữ ở trạng thái từ chối lời gọi | Không tự chuyển sang HALF_OPEN chỉ vì waitDuration đã trôi qua; cần thao tác quản trị để rời trạng thái ép mở |
| reset() | Đưa instance về CLOSED và làm mới dữ liệu trạng thái/thống kê của instance | Lời gọi được phép lại ngay theo cơ chế CLOSED; không có giai đoạn thăm dò HALF_OPEN trước đó |

Điểm cần nhớ:

- OPEN là một phần của state machine tự động. Nó có thời gian chờ và có thể chuyển sang HALF_OPEN.
- FORCED_OPEN là trạng thái ép mở để giữ dependency bị cô lập. Đây là lựa chọn phù hợp khi cần ngăn lời gọi cho đến khi có quyết định vận hành tiếp theo.
- reset() không chỉ là “xóa lỗi”. Nó đưa Circuit Breaker về trạng thái khởi đầu và làm mới metrics của instance. Thao tác này có thể xóa lịch sử mà đội vận hành đang dùng để đánh giá sự cố.
- Đưa mạch về CLOSED ngay lập tức có thể gửi lại traffic lớn đến dependency chưa phục hồi. Với quy trình khôi phục thận trọng, nên rời FORCED_OPEN bằng cách chuyển về OPEN bình thường để chờ HALF_OPEN thăm dò.

Các API chuyển trạng thái là API đặc thù của Resilience4j. Nếu ứng dụng chỉ sử dụng abstraction Spring Cloud CircuitBreaker, abstraction này không nhất thiết cung cấp các thao tác quản trị trạng thái. Khi cần điều khiển thủ công, phải dùng registry Resilience4j đang quản lý đúng instance mà lời gọi nghiệp vụ sử dụng.

## 3. Chuẩn bị registry và tên instance

Mỗi Circuit Breaker được quản lý trong registry theo tên. Tên trong thao tác vận hành phải trùng với tên được dùng ở cấu hình và lời gọi nghiệp vụ.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2

      payment:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 1
~~~

Service có thể dùng Circuit Breaker thông qua Spring Cloud factory:

~~~java
return circuitBreakerFactory.create("inventory").run(
    () -> inventoryClient.getInventory(sku),
    error -> InventoryResponse.unavailable(sku)
);
~~~

Tên inventory là định danh được sử dụng trong cấu hình. Nếu thao tác quản trị nhắm đến inventoryService trong khi lời gọi nghiệp vụ dùng inventory, người vận hành có thể thay đổi nhầm instance hoặc không tìm thấy instance.

Với Resilience4j Spring Boot integration, có thể inject CircuitBreakerRegistry để tra cứu instance:

~~~java
CircuitBreaker circuitBreaker =
    circuitBreakerRegistry.circuitBreaker("inventory");
~~~

Không nên tự tạo một registry thứ hai chỉ dành cho endpoint quản trị. Registry đó có thể chứa instance khác với instance đang bảo vệ request. Hãy bảo đảm factory, cấu hình Spring và lớp quản trị cùng sử dụng registry do ứng dụng quản lý.

Nếu dự án chỉ dùng Spring Cloud CircuitBreaker starter, hãy kiểm tra auto-configuration và bean registry trong đúng phiên bản. Không nên cast implementation nội bộ của factory hoặc phụ thuộc vào lớp provider private để điều khiển trạng thái.

## 4. Các API chuyển trạng thái cần biết

Resilience4j CircuitBreaker cung cấp các thao tác quản lý trạng thái trên instance:

~~~java
CircuitBreaker circuitBreaker =
    circuitBreakerRegistry.circuitBreaker("inventory");

// Chuyển sang OPEN bình thường, có thời gian chờ phục hồi.
circuitBreaker.transitionToOpenState();

// Ép mở và giữ trạng thái từ chối lời gọi.
circuitBreaker.transitionToForcedOpenState();

// Đưa instance về CLOSED và làm mới trạng thái/thống kê.
circuitBreaker.reset();
~~~

Ý nghĩa vận hành:

- transitionToOpenState() dùng khi muốn đặt mạch vào OPEN bình thường. Sau thời gian chờ được cấu hình, cơ chế tự động có thể cho phép HALF_OPEN.
- transitionToForcedOpenState() dùng khi muốn giữ mạch ở trạng thái ép mở, ví dụ trong lúc bảo trì hoặc điều tra sự cố.
- reset() dùng khi chủ đích đưa instance về trạng thái CLOSED và bắt đầu lại thống kê. Nó không tương đương với việc chờ HALF_OPEN thăm dò.

Resilience4j còn có các thao tác chuyển sang những trạng thái đặc biệt khác, tùy phiên bản. Chỉ cung cấp các thao tác mà quy trình vận hành thực sự cần. Trước khi triển khai, kiểm tra API của phiên bản Resilience4j đang được quản lý bởi dependency management của dự án.

Không dùng reset() như một cách “thử xem dependency đã khỏe chưa”. Reset làm mạch cho phép request mới ngay lập tức và có thể làm mất dữ liệu cần để phân tích sự cố. Dùng health check, synthetic probe hoặc quy trình HALF_OPEN để đánh giá phục hồi.

## 5. Xây dựng lớp quản trị có allowlist

Endpoint quản trị không nên cho phép người gọi truyền bất kỳ tên Circuit Breaker nào. Dùng allowlist để giới hạn các instance được phép điều khiển và trả lỗi rõ ràng nếu tên không tồn tại.

Ví dụ lớp service quản trị:

~~~java
package com.example.operations;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

import java.util.Set;

@Service
public class CircuitBreakerOperations {

    private static final Set<String> MANAGED_INSTANCES =
        Set.of("inventory", "payment");

    private final CircuitBreakerRegistry registry;

    public CircuitBreakerOperations(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    private CircuitBreaker requireManaged(String name) {
        if (!MANAGED_INSTANCES.contains(name)) {
            throw new IllegalArgumentException(
                "Circuit Breaker is not managed by this operations API"
            );
        }

        return registry.find(name)
            .orElseThrow(() -> new IllegalArgumentException(
                "Circuit Breaker instance does not exist: " + name
            ));
    }

    public CircuitBreaker.State forceOpen(String name) {
        CircuitBreaker circuitBreaker = requireManaged(name);
        circuitBreaker.transitionToForcedOpenState();
        return circuitBreaker.getState();
    }

    public CircuitBreaker.State openWithRecoveryTimer(String name) {
        CircuitBreaker circuitBreaker = requireManaged(name);
        circuitBreaker.transitionToOpenState();
        return circuitBreaker.getState();
    }

    public CircuitBreaker.State resumeAutomaticProbing(String name) {
        CircuitBreaker circuitBreaker = requireManaged(name);

        // Rời FORCED_OPEN bằng OPEN bình thường.
        // Circuit Breaker sẽ chờ waitDuration rồi tự vào HALF_OPEN.
        circuitBreaker.transitionToOpenState();

        return circuitBreaker.getState();
    }

    public CircuitBreaker.State resetToClosed(String name) {
        CircuitBreaker circuitBreaker = requireManaged(name);
        circuitBreaker.reset();
        return circuitBreaker.getState();
    }
}
~~~

Phương thức resumeAutomaticProbing cố ý chuyển về OPEN bình thường thay vì reset thẳng sang CLOSED. Cách này cho phép Circuit Breaker áp dụng waitDurationInOpenState rồi thực hiện các probe HALF_OPEN theo cấu hình.

Allowlist cần được quản lý cùng danh sách dependency mà đội vận hành được phép điều khiển. Nếu danh sách này thay đổi theo cấu hình, hãy nạp từ cấu hình đã kiểm soát và kiểm tra khi ứng dụng khởi động. Không dùng tên do người dùng tùy ý nhập để tự tạo instance mới trong registry.

## 6. Thiết kế endpoint điều khiển nội bộ

Có thể cung cấp endpoint riêng cho đội vận hành, nhưng endpoint này phải được bảo vệ bằng xác thực và phân quyền. Ví dụ dưới đây minh họa cấu trúc controller; hệ thống thật cần cấu hình Spring Security, mạng quản trị và audit theo tiêu chuẩn của tổ chức.

~~~java
package com.example.operations;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/internal/operations/circuit-breakers")
public class CircuitBreakerOperationsController {

    private final CircuitBreakerOperations operations;

    public CircuitBreakerOperationsController(
            CircuitBreakerOperations operations) {
        this.operations = operations;
    }

    @PostMapping("/{name}/force-open")
    @PreAuthorize("hasAuthority('SCOPE_circuitbreaker:operate')")
    public ResponseEntity<Map<String, String>> forceOpen(
            @PathVariable String name) {
        CircuitBreaker.State state = operations.forceOpen(name);

        return ResponseEntity.accepted().body(Map.of(
            "name", name,
            "state", state.name()
        ));
    }

    @PostMapping("/{name}/resume-probing")
    @PreAuthorize("hasAuthority('SCOPE_circuitbreaker:operate')")
    public ResponseEntity<Map<String, String>> resumeProbing(
            @PathVariable String name) {
        CircuitBreaker.State state =
            operations.resumeAutomaticProbing(name);

        return ResponseEntity.accepted().body(Map.of(
            "name", name,
            "state", state.name()
        ));
    }

    @PostMapping("/{name}/reset")
    @PreAuthorize("hasAuthority('SCOPE_circuitbreaker:reset')")
    public ResponseEntity<Map<String, String>> reset(
            @PathVariable String name) {
        CircuitBreaker.State state = operations.resetToClosed(name);

        return ResponseEntity.accepted().body(Map.of(
            "name", name,
            "state", state.name()
        ));
    }
}
~~~

Các endpoint trên chỉ nên truy cập từ mạng quản trị hoặc control plane nội bộ. Scope circuitbreaker:operate và circuitbreaker:reset là ví dụ về authority; cần ánh xạ chúng từ identity provider và chính sách Spring Security thực tế.

Nên tách quyền reset khỏi quyền force-open/resume vì reset có thể đưa dependency trở lại nhận traffic ngay lập tức và làm mới metrics. Với hệ thống quan trọng, reset có thể yêu cầu quyền cao hơn hoặc phê duyệt theo quy trình change management.

Không expose endpoint này dưới một route công khai không xác thực. Không dùng GET để thay đổi trạng thái vì GET có thể bị gọi bởi crawler, cache hoặc công cụ giám sát.

## 7. Ghi audit cho mọi thao tác

Mỗi lần thay đổi trạng thái thủ công cần có dấu vết để người vận hành sau này biết ai đã làm, vì sao và thao tác trên instance nào.

Thông tin audit nên gồm:

- Tên Circuit Breaker instance.
- Trạng thái trước thao tác và trạng thái sau thao tác.
- Loại hành động: force-open, resume-probing hoặc reset.
- Người thực hiện và nguồn xác thực.
- Thời điểm thao tác.
- Lý do, mã incident hoặc change ticket.
- Replica/pod nhận lệnh.
- Kết quả thao tác và lỗi nếu có.

Không ghi access token hoặc bí mật vào audit log. Có thể dùng một DTO yêu cầu có reason và incidentId, ví dụ:

~~~java
public record CircuitBreakerOperationRequest(
    String reason,
    String incidentId
) {
}
~~~

Controller cần kiểm tra reason không rỗng và ghi audit trước hoặc ngay sau khi thực hiện thao tác theo quy trình đã chọn. Nếu audit là yêu cầu bắt buộc, không nên báo thành công khi không thể ghi lại hành động. Hãy xác định rõ cách xử lý khi audit store tạm thời không khả dụng.

Các thao tác nên có tính lặp an toàn (idempotent) ở mức nghiệp vụ. Gửi lại yêu cầu force-open cho một instance đã FORCED_OPEN không được tạo ra side effect bất ngờ. Trước khi trả response, hãy đọc state hiện tại để xác nhận trạng thái sau thao tác.

## 8. Quy trình ép OPEN trong sự cố

Khi cần ngừng gọi một dependency ngay lập tức, có thể dùng quy trình sau:

1. Xác định dependency và instance Circuit Breaker chính xác.
2. Xác nhận sự cố từ metrics, log, tracing, health check hoặc thông báo từ đội sở hữu dependency.
3. Kiểm tra fallback có thể phục vụ request hay không và đánh giá ảnh hưởng nghiệp vụ.
4. Xác định phạm vi replica cần điều khiển.
5. Ghi incident ID, lý do và người chịu trách nhiệm.
6. Gọi thao tác force-open.
7. Đọc lại state và xác nhận là FORCED_OPEN.
8. Theo dõi số lời gọi bị từ chối, fallback, latency và tải của dependency.
9. Ghi thời điểm cần đánh giá lại và người chịu trách nhiệm khôi phục.

Ví dụ request quản trị (chỉ gửi từ môi trường nội bộ đã xác thực):

~~~bash
curl -X POST \
  -H "Authorization: Bearer <operations-access-token>" \
  "https://order-admin.internal/internal/operations/circuit-breakers/inventory/force-open"
~~~

Token trong ví dụ chỉ là placeholder. Không đưa token thật vào shell history, tài liệu hoặc log. Nếu endpoint yêu cầu request body chứa reason và incidentId, hãy gửi các trường đó theo hợp đồng API của ứng dụng.

Sau khi force-open, các lời gọi mới qua instance đó bị từ chối. Fallback cần được theo dõi để chắc chắn ứng dụng không chuyển sự cố sang một dependency khác hoặc trả dữ liệu sai nghiệp vụ. Những request đã được cấp quyền trước khi mạch bị ép mở có thể vẫn đang chạy; thao tác force-open không tự hủy các in-flight call.

## 9. Trả lại chế độ tự động qua OPEN và HALF_OPEN

Sau khi dependency đã được khắc phục, cách phục hồi thận trọng là đưa Circuit Breaker từ FORCED_OPEN về OPEN bình thường. Khi hết waitDurationInOpenState, state machine có thể tự chuyển sang HALF_OPEN.

Quy trình:

1. Xác nhận nguyên nhân sự cố đã được xử lý.
2. Kiểm tra health và khả năng phục vụ của dependency.
3. Gọi transitionToOpenState() để rời trạng thái FORCED_OPEN.
4. Xác nhận state là OPEN bình thường.
5. Chờ waitDurationInOpenState.
6. Theo dõi khi Circuit Breaker chuyển HALF_OPEN.
7. Quan sát số probe, kết quả thành công, lỗi và slow-call rate.
8. Nếu probe thành công theo điều kiện cấu hình, Circuit Breaker tự chuyển CLOSED.
9. Nếu probe thất bại hoặc chậm vượt ngưỡng, Circuit Breaker quay lại OPEN.
10. Chỉ đóng incident khi trạng thái và metrics ổn định.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2
        automaticTransitionFromOpenToHalfOpenEnabled: true
        failureRateThreshold: 50
        slowCallRateThreshold: 50
~~~

Trong HALF_OPEN, số probe bị giới hạn. Không nên gửi thêm traffic thử nghiệm bằng tay ngoài ngân sách probe nếu chưa đánh giá tổng tải. Hãy để Circuit Breaker quyết định dựa trên các kết quả thăm dò mà nó cho phép.

Nếu dependency có nhiều replica, mỗi Circuit Breaker cục bộ có thể có timer và thời điểm chuyển HALF_OPEN riêng. Hãy quan sát từng replica để tránh kết luận rằng toàn bộ hệ thống đã phục hồi chỉ vì một instance chuyển CLOSED.

## 10. Khi nào dùng reset()?

reset() đưa Circuit Breaker về CLOSED và làm mới trạng thái/thống kê của instance. Sau reset, lời gọi mới có thể được phép ngay lập tức và sliding window bắt đầu tích lũy dữ liệu mới.

Chỉ dùng reset khi có lý do rõ ràng, ví dụ:

- Cần xóa trạng thái và lịch sử thống kê sau một thao tác thử nghiệm trong môi trường kiểm thử.
- Có quyết định vận hành đưa dependency trở lại phục vụ ngay, đã xác nhận dependency khỏe và chấp nhận bỏ qua giai đoạn HALF_OPEN.
- Cần khôi phục một instance sau khi cấu hình hoặc điều kiện vận hành được thay đổi theo quy trình có kiểm soát.

Không nên reset chỉ để làm biến mất trạng thái OPEN trên dashboard. Việc đó không sửa nguyên nhân gốc và có thể khiến request tiếp tục đi vào dependency đang lỗi.

Ví dụ thao tác:

~~~java
CircuitBreaker inventory =
    circuitBreakerRegistry.circuitBreaker("inventory");

inventory.reset();

if (inventory.getState() != CircuitBreaker.State.CLOSED) {
    throw new IllegalStateException(
        "Inventory Circuit Breaker did not return to CLOSED"
    );
}
~~~

Sau reset, cần ghi rõ trong audit rằng metrics và cửa sổ thống kê đã được làm mới. Dashboard có thể thấy số mẫu giảm về ban đầu; đây là kết quả của reset, không phải bằng chứng dependency đã khỏe.

Nếu mục tiêu là phục hồi có thăm dò, dùng transitionToOpenState() sau FORCED_OPEN để chờ HALF_OPEN thay vì gọi reset.

## 11. Đọc trạng thái và metrics trước, sau thao tác

Lớp quản trị nên cung cấp khả năng đọc trạng thái để người vận hành kiểm chứng trước và sau khi thay đổi.

Ví dụ:

~~~java
CircuitBreaker circuitBreaker =
    circuitBreakerRegistry.find("inventory")
        .orElseThrow();

CircuitBreaker.State state = circuitBreaker.getState();
CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();

int bufferedCalls = metrics.getNumberOfBufferedCalls();
int failedCalls = metrics.getNumberOfFailedCalls();
float failureRate = metrics.getFailureRate();
float slowCallRate = metrics.getSlowCallRate();
~~~

Có thể hiển thị thông tin sau trong dashboard hoặc trang quản trị:

| Trường | Mục đích |
| --- | --- |
| Instance name | Xác định dependency được điều khiển |
| State | CLOSED, OPEN, HALF_OPEN hoặc FORCED_OPEN |
| Buffered calls | Số mẫu hiện có trong sliding window |
| Failed calls | Số lời gọi thất bại trong cửa sổ |
| Failure rate | Tỷ lệ lỗi hiện tại |
| Slow-call rate | Tỷ lệ lời gọi chậm |
| Not permitted calls | Số lời gọi bị từ chối |
| Last operation | Hành động quản trị gần nhất |
| Operator/reason | Người thực hiện và lý do |

Một số giá trị metrics có thể trả về giá trị đặc biệt khi chưa đủ mẫu để đánh giá, chẳng hạn failure rate chưa được xác định. Giao diện quản trị cần biểu diễn trường hợp chưa có dữ liệu thay vì hiển thị nó như tỷ lệ 0% đã được xác nhận.

Actuator và các endpoint metrics của Resilience4j chủ yếu phục vụ quan sát. Không nên giả định endpoint metrics có thể dùng để ép trạng thái nếu phiên bản tích hợp không cung cấp API ghi trạng thái chính thức. Dùng lớp quản trị riêng với quyền truy cập được kiểm soát.

## 12. Quản lý nhiều replica và nhiều instance

Circuit Breaker Resilience4j thường là state cục bộ trong từng tiến trình ứng dụng. Nếu Order chạy bốn replica, mỗi replica có registry và instance Circuit Breaker riêng.

~~~text
                Operations control plane
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
          Pod A        Pod B        Pod C
          inventory    inventory    inventory
          FORCED_OPEN  CLOSED       FORCED_OPEN
             |           |           |
             +-----------+-----------+
                         |
                         v
                  Inventory service
~~~

Nếu chỉ force-open một pod, LoadBalancer vẫn có thể gửi request đến các pod khác đang CLOSED. Vì vậy, thao tác trên một replica không đồng nghĩa với việc toàn bộ dependency đã bị cô lập.

Khi cần điều khiển toàn bộ replica:

- Dùng control plane hoặc automation có khả năng gửi lệnh đến từng replica.
- Thu thập xác nhận state từ từng pod.
- Xác định rõ replica mới được tạo trong lúc incident sẽ nhận chính sách nào.
- Theo dõi trạng thái sau scale-out, restart hoặc rolling deployment.
- Không giả định state được chia sẻ giữa các pod chỉ vì cùng dùng một tên instance.

Có thể lựa chọn một cách vận hành khác là thay đổi route hoặc cấu hình ở gateway/control plane để ngừng traffic đến dependency trên toàn hệ thống. Cách đó có phạm vi khác với việc thay state của Circuit Breaker cục bộ. Hãy chọn đúng lớp điều khiển theo mục tiêu và ghi rõ phạm vi tác động.

## 13. Cấu hình, state và vòng đời ứng dụng

Cấu hình Circuit Breaker và state hiện tại là hai khái niệm riêng:

- YAML hoặc Java configuration xác định ngưỡng, window, wait duration và số probe.
- Registry quản lý các instance.
- Instance giữ state và metrics tại runtime.
- Thao tác force-open hoặc reset tác động đến state của instance.
- Khởi động lại ứng dụng thường tạo lại registry và instance theo cấu hình lúc khởi động.

Do đó, không nên coi việc sửa application.yml là một thao tác reset state. Ngược lại, gọi reset không thay đổi failureRateThreshold hoặc slidingWindowSize của cấu hình hiện tại.

Khi rolling restart, instance mới có thể bắt đầu ở CLOSED trong khi replica cũ vẫn FORCED_OPEN. Nếu yêu cầu cô lập phải duy trì qua restart, cần một nguồn chính sách bền vững ở control plane hoặc cấu hình triển khai, rồi áp dụng lại cho replica mới. Không dựa vào state trong bộ nhớ của một pod để lưu quyết định vận hành dài hạn.

Nếu cần duy trì trạng thái bảo trì, hãy quản lý trạng thái đó ở một nguồn điều phối có thể kiểm tra, có thời hạn và có audit. Khi ứng dụng khởi động, nó có thể đọc chính sách vận hành đã được phê duyệt và áp dụng trạng thái tương ứng.

## 14. Kế hoạch khôi phục và rollback

Mỗi thao tác force-open nên đi kèm kế hoạch khôi phục trước khi thực hiện.

| Giai đoạn | Điều kiện cần xác nhận | Hành động |
| --- | --- | --- |
| Trước khi force-open | Dependency có sự cố, fallback sẵn sàng, đúng instance và replica | Ghi incident, người phụ trách và phạm vi |
| Sau khi force-open | State là FORCED_OPEN, request mới bị chặn | Theo dõi fallback, rejection và tải dependency |
| Trước khi resume | Nguyên nhân đã được xử lý, health và latency có dấu hiệu ổn định | Chuẩn bị đưa mạch về OPEN bình thường |
| HALF_OPEN | Probe nằm trong giới hạn và kết quả có thể quan sát | Để state machine tự quyết định |
| Sau khi CLOSED | Failure rate và latency ổn định, không có lỗi tăng trở lại | Xác nhận phục hồi và đóng incident |
| Nếu probe thất bại | Dependency vẫn không ổn định | Để mạch trở lại OPEN, điều tra tiếp và giữ fallback |

Nếu reset nhầm instance hoặc đưa mạch về CLOSED quá sớm, có thể force-open lại ngay và ghi audit bổ sung. Tuy nhiên, không nên dựa vào thao tác bù trừ để thay thế quy trình xác nhận. Hãy kiểm tra tên instance, state và phạm vi replica trước mỗi hành động.

## 15. Kiểm thử quy trình trong môi trường staging

Trước khi dùng endpoint quản trị trong production, hãy thử toàn bộ vòng đời trong staging:

1. Tạo Circuit Breaker tên inventory và gửi request thành công để xác nhận CLOSED.
2. Tạo lỗi có kiểm soát để Circuit Breaker tự chuyển OPEN.
3. Đợi mạch tự chuyển HALF_OPEN và quan sát kết quả probe.
4. Gọi endpoint force-open khi instance đang CLOSED để xác nhận state FORCED_OPEN.
5. Gửi request nghiệp vụ và xác nhận request mới bị từ chối hoặc đi qua fallback.
6. Chờ lâu hơn waitDurationInOpenState và xác nhận FORCED_OPEN vẫn được giữ.
7. Gọi resume-probing để chuyển về OPEN bình thường.
8. Chờ HALF_OPEN và gửi probe theo cấu hình.
9. Xác nhận thành công đưa mạch về CLOSED; tạo lỗi để xác nhận mạch quay lại OPEN.
10. Thử reset trong một kịch bản riêng và xác nhận state CLOSED cùng metrics được làm mới.
11. Kiểm tra quyền truy cập: người không có scope quản trị nhận 403.
12. Kiểm tra audit có tên instance, hành động, người thực hiện, lý do và thời điểm.
13. Lặp lại trên nhiều replica và xác nhận từng pod nhận lệnh.
14. Khởi động lại một pod trong lúc có chính sách bảo trì và kiểm tra quyết định được áp dụng lại nếu kiến trúc yêu cầu.

Không chạy các thao tác reset hoặc force-open tùy tiện trên production chỉ để kiểm tra endpoint. Hãy xác nhận hành vi bằng staging và có kế hoạch rollback.

## 16. Các lỗi vận hành thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Đã ép OPEN nhưng dependency vẫn nhận request | Chỉ một replica được điều khiển hoặc lời gọi đang chạy đã được cấp quyền trước đó | Kiểm tra từng replica và in-flight calls |
| Mạch tự chuyển HALF_OPEN dù muốn giữ ngắt | Dùng OPEN bình thường thay vì FORCED_OPEN | Dùng transitionToForcedOpenState() khi cần giữ trạng thái ép mở |
| Mạch vẫn FORCED_OPEN sau thời gian chờ | Đây là hành vi dự kiến của trạng thái ép mở | Gọi thao tác resume có kiểm soát |
| Reset xong traffic tăng đột ngột | Reset đưa instance về CLOSED ngay lập tức | Dùng OPEN bình thường rồi HALF_OPEN nếu cần phục hồi từ từ |
| Dashboard mất lịch sử sau reset | Reset làm mới metrics/sliding window của instance | Ghi audit và lưu dữ liệu metrics trước thao tác nếu cần điều tra |
| Endpoint không tìm thấy instance | Sai tên hoặc registry quản trị khác registry nghiệp vụ | Đồng bộ tên và dùng cùng registry |
| Restart làm mạch trở lại CLOSED | State chỉ nằm trong bộ nhớ instance | Lưu chính sách bảo trì ở control plane và áp dụng khi khởi động |
| Một số pod CLOSED, một số pod FORCED_OPEN | Lệnh mới chỉ được gửi đến một phần replica | Điều phối lệnh toàn cụm và xác nhận từng pod |
| Người dùng không có quyền vẫn điều khiển được | Endpoint thiếu xác thực hoặc phân quyền | Bật Spring Security, giới hạn scope và mạng quản trị |
| Không biết ai đã reset | Thiếu audit log hoặc incident reference | Bắt buộc ghi actor, reason, timestamp và action |

## 17. Nguyên tắc vận hành an toàn

- Dùng OPEN bình thường khi muốn state machine tự chờ và thăm dò phục hồi.
- Dùng FORCED_OPEN khi cần giữ dependency bị cô lập cho đến khi có quyết định vận hành tiếp theo.
- Dùng reset chỉ khi chấp nhận đưa instance về CLOSED ngay và làm mới lịch sử thống kê.
- Không coi reset là phép kiểm tra health hoặc cách xóa cảnh báo.
- Dùng đúng registry và tên instance mà lời gọi nghiệp vụ đang sử dụng.
- Giới hạn instance được phép điều khiển bằng allowlist.
- Bảo vệ endpoint quản trị bằng xác thực, phân quyền và mạng nội bộ.
- Ghi audit cho mọi thao tác, gồm actor, reason, incident và trạng thái trước/sau.
- Theo dõi in-flight calls, fallback và rejection sau khi force-open.
- Quản lý state trên tất cả replica; không giả định Circuit Breaker state được chia sẻ toàn cụm.
- Có kế hoạch resume, HALF_OPEN, rollback và người chịu trách nhiệm trước khi ép mở.
- Kiểm tra API và semantics đúng phiên bản Resilience4j đang chạy.

Ép OPEN, reset và trả lại chế độ tự động là các thao tác vận hành có tác động trực tiếp đến traffic. FORCED_OPEN giúp giữ dependency ở trạng thái bị cô lập; chuyển về OPEN bình thường cho phép Circuit Breaker chờ rồi tự thăm dò qua HALF_OPEN; reset đưa instance về CLOSED ngay và làm mới thống kê. Khi dùng đúng registry, bảo vệ quyền quản trị, ghi audit và kiểm soát từng replica, đội vận hành có thể chủ động xử lý sự cố mà vẫn giữ được quy trình phục hồi có thể kiểm chứng.

## Tài liệu tham khảo

- [Resilience4j CircuitBreaker — State transitions and configuration](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j CircuitBreaker API](https://javadoc.io/doc/io.github.resilience4j/resilience4j-circuitbreaker/latest/io/github/resilience4j/circuitbreaker/CircuitBreaker.html)
- [Resilience4j CircuitBreakerRegistry API](https://javadoc.io/doc/io.github.resilience4j/resilience4j-circuitbreaker/latest/io/github/resilience4j/circuitbreaker/CircuitBreakerRegistry.html)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Boot Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)

