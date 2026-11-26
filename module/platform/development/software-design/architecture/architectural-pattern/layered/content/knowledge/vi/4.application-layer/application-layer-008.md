# Tái sử dụng ca sử dụng từ HTTP, tác vụ nền, CLI hoặc xử lý theo lô

Trong chương **Tầng ứng dụng**, bài học này tập trung vào cách nhiều điểm khởi đầu khác nhau cùng sử dụng một ca sử dụng của ứng dụng. Với module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, mục tiêu là tổ chức phần mềm theo kiến trúc phân tầng: tầng trình bày tiếp nhận tương tác bên ngoài, tầng ứng dụng điều phối ca sử dụng, thành phần nghiệp vụ bảo vệ quy tắc và tầng truy cập dữ liệu làm việc với cơ chế lưu trữ.

Một chức năng nghiệp vụ có thể được kích hoạt bởi request HTTP, lịch chạy tự động, lệnh dòng lệnh (CLI), message hoặc một tệp dữ liệu cần xử lý theo lô. Nếu mỗi cách khởi chạy tự viết lại quy tắc và trình tự xử lý, hệ thống sẽ có nhiều phiên bản của cùng một hành vi. Khi quy tắc thay đổi, các phiên bản đó dễ lệch nhau. Tầng ứng dụng giải quyết vấn đề bằng cách cung cấp hợp đồng ca sử dụng để các adapter đầu vào khác nhau gọi chung.

Sau bài học, bạn có thể:

- Phân biệt ca sử dụng với giao thức hoặc cơ chế khởi chạy nó.
- Thiết kế một hợp đồng ứng dụng có thể được gọi từ HTTP, tác vụ nền, CLI và batch.
- Tổ chức các adapter để chuyển dữ liệu đầu vào và ngữ cảnh người gọi thành command phù hợp.
- Xử lý nhất quán giao dịch, quyền truy cập, retry, idempotency và lỗi ở từng kiểu khởi chạy.
- Kiểm thử ca sử dụng độc lập với adapter, đồng thời kiểm tra riêng việc ánh xạ của từng adapter.

## 1. Ca sử dụng độc lập với điểm khởi đầu

Ca sử dụng mô tả một mục tiêu mà ứng dụng cần thực hiện, chẳng hạn phê duyệt đơn hàng, ghi nhận thanh toán, phát hành hóa đơn hoặc cập nhật hồ sơ. Nó không đồng nghĩa với một endpoint, một lệnh CLI hay một phương thức được bộ lập lịch gọi.

Ví dụ, mục tiêu **phê duyệt một đơn hàng** có thể được khởi chạy theo nhiều cách:

- Nhân viên gửi request HTTP từ màn hình quản trị.
- Một tác vụ nền tự động xử lý những đơn đủ điều kiện sau thời hạn.
- Nhân viên vận hành chạy lệnh CLI để xử lý một đơn cụ thể.
- Một chương trình batch đọc danh sách mã đơn từ tệp và xử lý từng dòng.

Nếu cả bốn cách đều yêu cầu ứng dụng thực hiện cùng một hành vi phê duyệt, chúng nên gọi cùng hợp đồng ca sử dụng. Adapter chịu trách nhiệm hiểu cách nhận dữ liệu của nó, xác định người khởi chạy và chuyển dữ liệu thành đầu vào ứng dụng. Ca sử dụng chịu trách nhiệm điều phối quy trình và bảo đảm các quy tắc cần thiết được thực hiện.

Điều được tái sử dụng là **hành vi ứng dụng**, không phải request HTTP, controller, câu lệnh CLI hay định dạng tệp. Một tác vụ nền không cần gọi vòng lại endpoint HTTP của chính hệ thống. Nó có thể gọi trực tiếp hợp đồng ứng dụng trong cùng tiến trình. Tương tự, batch không nên sao chép logic phê duyệt vào vòng lặp đọc tệp.

Không nên ép hai yêu cầu khác ý nghĩa vào cùng một ca sử dụng chỉ vì chúng có vài bước giống nhau. Ví dụ, phê duyệt thủ công và tự động phê duyệt có thể có chính sách, thẩm quyền hoặc điều kiện khác nhau. Khi đó, chúng có thể là hai ca sử dụng riêng nhưng cùng gọi một quy tắc nghiệp vụ hoặc thành phần dùng chung. Chỉ dùng chung một hợp đồng khi mục tiêu và cam kết của thao tác thực sự giống nhau.

## 2. Hợp đồng ca sử dụng trong tầng ứng dụng

Hợp đồng ứng dụng mô tả thao tác bằng ngôn ngữ của ứng dụng. Nó không nên phụ thuộc vào `HttpServletRequest`, `ResponseEntity`, `CommandLineRunner`, định dạng CSV hay annotation của bộ lập lịch.

Ví dụ, ca sử dụng phê duyệt đơn hàng có thể được biểu diễn như sau:

~~~java
import java.util.UUID;

public record ActorId(String value) {}

public record ApproveOrderCommand(
        UUID orderId,
        ActorId actorId,
        String reason
) {}

public record ApprovalResult(
        UUID orderId,
        String status,
        boolean changed
) {}

public interface ApproveOrder {
    ApprovalResult execute(ApproveOrderCommand command);
}
~~~

`ApproveOrderCommand` chứa dữ liệu mà ca sử dụng cần: đơn hàng nào được phê duyệt, ai thực hiện và lý do. `ActorId` là định danh theo ngôn ngữ ứng dụng, không phải đối tượng principal của Spring Security. `ApprovalResult` mô tả kết quả theo ngữ nghĩa của ứng dụng, không phải HTTP response hay dòng xuất của CLI.

Không phải mọi ca sử dụng đều cần `actorId` hoặc `reason`. Chỉ đưa chúng vào command khi chúng có ý nghĩa đối với kiểm tra quyền, kiểm toán hoặc quy tắc nghiệp vụ. Các giá trị như mã tương quan, tenant hoặc thời điểm thực thi cũng chỉ nên được truyền vào khi ứng dụng thực sự cần; tránh biến command thành một túi chứa toàn bộ header và metadata của giao thức.

Một triển khai dịch vụ ứng dụng có thể điều phối các thành phần như sau:

~~~java
import java.time.Clock;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class ApproveOrderService implements ApproveOrder {
    private final OrderRepository orders;
    private final ApprovalAuthorization authorization;
    private final Clock clock;

    ApproveOrderService(
            OrderRepository orders,
            ApprovalAuthorization authorization,
            Clock clock) {
        this.orders = orders;
        this.authorization = authorization;
        this.clock = clock;
    }

    @Override
    @Transactional
    public ApprovalResult execute(ApproveOrderCommand command) {
        var order = orders.getById(command.orderId());
        authorization.checkCanApprove(command.actorId(), order);
        var result = order.approve(
                command.actorId(), command.reason(), clock.instant());
        orders.save(order);
        return new ApprovalResult(
                order.id(), result.status().name(), result.changed());
    }
}
~~~

Đây là ví dụ minh họa; `OrderRepository`, `ApprovalAuthorization`, `Order` và `Clock` là các kiểu thuộc hợp đồng hoặc mô hình mà dự án định nghĩa. Điểm chính là dịch vụ ứng dụng điều phối việc tải đơn, kiểm tra quyền, gọi hành vi nghiệp vụ và lưu kết quả trong một đơn vị công việc phù hợp. `@Transactional` là cách Spring thường được dùng để đặt ranh giới giao dịch cho thao tác lưu trữ cục bộ; dự án dùng framework khác có thể áp dụng cơ chế tương đương.

Tầng ứng dụng không cần biết ai đã gửi HTTP, lệnh CLI có tên gì hay batch đang đọc tệp nào. Nó nhận command và thực hiện ca sử dụng theo hợp đồng đã định.

## 3. Sơ đồ nhiều adapter gọi chung một ca sử dụng

Các adapter đầu vào chuyển dữ liệu riêng của chúng thành cùng một command:

~~~mermaid
flowchart TD
    H[HTTP Controller] -->|ApproveOrderCommand| U[Hợp đồng ApproveOrder]
    S[Scheduled Job] -->|ApproveOrderCommand| U
    C[CLI Command] -->|ApproveOrderCommand| U
    B[Batch Importer] -->|ApproveOrderCommand cho từng dòng| U
    U --> A[ApproveOrderService]
    A --> P[Kiểm tra quyền và quy tắc nghiệp vụ]
    A --> R[OrderRepository]
    R --> D[(Cơ sở dữ liệu)]
~~~

Trong ứng dụng phân tầng, các adapter thường thuộc vùng trình bày hoặc vùng tích hợp đầu vào; dịch vụ ca sử dụng thuộc tầng ứng dụng. Repository và adapter lưu trữ là các thành phần được tầng ứng dụng sử dụng qua hợp đồng phù hợp. Vị trí package hoặc module cụ thể có thể khác nhau, miễn là hướng phụ thuộc và quyền sở hữu hợp đồng được làm rõ.

Các tầng logic này có thể chạy trong cùng một ứng dụng Spring. Việc có nhiều adapter đầu vào không bắt buộc phải tách thành nhiều dịch vụ hoặc tiến trình. Ngược lại, nếu sau này cần triển khai CLI hoặc worker ở tiến trình riêng, hợp đồng ứng dụng và cách trao đổi thông điệp có thể được đóng gói ở ranh giới phù hợp.

## 4. Adapter HTTP: chuyển request thành command

Controller nhận dữ liệu theo hợp đồng HTTP, lấy danh tính đã xác thực và chuyển đổi thành command. Ví dụ:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import java.util.UUID;

record ApproveOrderRequest(@NotBlank String reason) {}
record ApprovalResponse(UUID orderId, String status) {}

@RestController
class OrderApprovalController {
    private final ApproveOrder approveOrder;

    OrderApprovalController(ApproveOrder approveOrder) {
        this.approveOrder = approveOrder;
    }

    @PostMapping("/orders/{orderId}/approval")
    ResponseEntity<ApprovalResponse> approve(
            @PathVariable UUID orderId,
            @Valid @RequestBody ApproveOrderRequest request,
            @AuthenticationPrincipal OperatorPrincipal principal) {

        var command = new ApproveOrderCommand(
                orderId,
                new ActorId(principal.actorId()),
                request.reason());
        var result = approveOrder.execute(command);
        var response = new ApprovalResponse(
                result.orderId(), result.status());
        return ResponseEntity.ok(response);
    }
}
~~~

`OperatorPrincipal` là kiểu principal của ứng dụng được hệ thống bảo mật cung cấp sau khi xác thực. Controller không lấy `actorId` từ body do client tự khai báo. Nó chuyển dữ liệu HTTP thành command, gọi ca sử dụng rồi ánh xạ kết quả thành response. Controller không tự tải đơn, kiểm tra điều kiện phê duyệt hoặc ghi dữ liệu.

HTTP adapter còn có thể kiểm tra cú pháp request và ánh xạ lỗi ứng dụng thành status code. Những chi tiết đó thuộc hợp đồng HTTP; chúng không nên làm thay đổi ý nghĩa của `ApproveOrderCommand`.

## 5. Adapter cho tác vụ nền và lịch chạy

Một scheduled job có thể tìm các đơn đã đến hạn và gọi cùng ca sử dụng cho từng đơn. Việc tìm danh sách có thể được thực hiện qua một query/use case riêng, để job không truy cập trực tiếp bảng hoặc repository nội bộ:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import java.time.Clock;

@Component
class AutoApprovalJob {
    private static final int PAGE_SIZE = 100;
    private static final ActorId SYSTEM_ACTOR = new ActorId("system:auto-approval");

    private final FindOrdersDueForApproval findDue;
    private final ApproveOrder approveOrder;
    private final Clock clock;

    AutoApprovalJob(
            FindOrdersDueForApproval findDue,
            ApproveOrder approveOrder,
            Clock clock) {
        this.findDue = findDue;
        this.approveOrder = approveOrder;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${jobs.order-approval.delay}")
    void run() {
        var dueOrders = findDue.execute(clock.instant(), PAGE_SIZE);
        for (var orderId : dueOrders) {
            approveOrder.execute(new ApproveOrderCommand(
                    orderId, SYSTEM_ACTOR, "AUTO_APPROVAL"));
        }
    }
}
~~~

`FindOrdersDueForApproval` là một hợp đồng đọc riêng, còn `ApproveOrder` thực hiện từng thao tác phê duyệt. Job chỉ điều phối lịch chạy và truyền danh tính hệ thống đã được cấu hình. Việc tự động phê duyệt chỉ phù hợp khi chính sách nghiệp vụ cho phép; không nên dùng actor hệ thống để bỏ qua các điều kiện hoặc quyền cần được kiểm tra.

Trong môi trường thật, job cần có giới hạn số bản ghi, phân trang hoặc checkpoint, ghi nhận kết quả và xử lý lỗi theo từng đơn. Nếu một đơn thất bại tạm thời, có thể lên lịch thử lại; lỗi do vi phạm quy tắc thường cần được ghi nhận để xử lý thay vì lặp vô hạn. Khi nhiều worker có thể chạy đồng thời, cần cơ chế nhận việc hoặc khóa phù hợp để tránh xử lý cạnh tranh.

Tác vụ nền có thể được kích hoạt bởi scheduler, message broker hoặc một sự kiện nội bộ. Adapter tương ứng vẫn chuyển thông điệp thành command của ca sử dụng. Với message có khả năng được giao lại, cần giả định rằng cùng một thông điệp có thể đến nhiều lần và thiết kế thao tác an toàn khi lặp.

## 6. Adapter CLI: chuyển đối số thành command

CLI thường nhận mã đơn và lý do từ đối số hoặc prompt tương tác. Sau khi kiểm tra cú pháp và xác định người vận hành, adapter gọi cùng hợp đồng:

~~~java
import java.util.UUID;

class ApproveOrderCli {
    private final ApproveOrder approveOrder;

    ApproveOrderCli(ApproveOrder approveOrder) {
        this.approveOrder = approveOrder;
    }

    int execute(
            UUID orderId,
            String reason,
            ActorId authenticatedOperator) {
        var command = new ApproveOrderCommand(
                orderId, authenticatedOperator, reason);
        var result = approveOrder.execute(command);
        System.out.printf("Order %s: %s%n",
                result.orderId(), result.status());
        return 0;
    }
}
~~~

Đây là phần thân của một adapter CLI; thư viện như Spring Shell, picocli hoặc bộ phân tích đối số khác có thể gọi phương thức này. Adapter chịu trách nhiệm hiển thị thông báo và chọn exit code. Nó không cần tái tạo quy tắc phê duyệt. `authenticatedOperator` phải đến từ cơ chế xác thực phù hợp với môi trường vận hành, không nên mặc định rằng mọi người có thể truyền một chuỗi actor tùy ý.

## 7. Adapter batch: gọi ca sử dụng cho từng bản ghi

Batch thường đọc dữ liệu từ CSV, spreadsheet đã xuất, tệp trao đổi hoặc nguồn dữ liệu khác. Adapter phân tích từng bản ghi, kiểm tra định dạng, ánh xạ thành command rồi gọi cùng ca sử dụng:

~~~java
import java.util.UUID;

for (var row : approvalFile.rows()) {
    UUID orderId;
    try {
        orderId = UUID.fromString(row.orderId());
    } catch (IllegalArgumentException invalidRow) {
        report.invalid(row.lineNumber(), "Mã đơn không hợp lệ");
        continue;
    }

    try {
        var command = new ApproveOrderCommand(orderId, batchActor, row.reason());
        var result = approveOrder.execute(command);
        report.success(row.lineNumber(), result.status());
    } catch (BusinessRuleViolation rejected) {
        report.rejected(row.lineNumber(), rejected.getCode());
    }
}
~~~

Ví dụ trên chỉ minh họa cách ánh xạ và phân loại lỗi; kiểu `approvalFile`, `batchActor` và `report` do adapter định nghĩa. Một batch có thể tiếp tục với bản ghi sai định dạng hoặc bị từ chối theo nghiệp vụ, đồng thời tổng hợp kết quả để người vận hành biết dòng nào thành công và dòng nào cần xử lý.

Không nên bắt mọi exception rồi bỏ qua. Lỗi cấu hình, mất kết nối cơ sở dữ liệu hoặc lỗi lập trình có thể cần dừng batch để tránh tạo báo cáo thành công giả. Hãy phân biệt lỗi dữ liệu từng dòng, lỗi nghiệp vụ có thể ghi nhận và lỗi hạ tầng cần retry hoặc dừng tiến trình.

Với tập dữ liệu lớn, xử lý từng bản ghi trong một giao dịch riêng có thể phù hợp hơn một giao dịch bao trùm toàn bộ tệp. Cũng có thể gom theo chunk để cân bằng hiệu năng và khả năng phục hồi. Lựa chọn phụ thuộc vào yêu cầu nguyên tử: toàn bộ tệp phải thành công, từng dòng độc lập hay từng nhóm dòng là một đơn vị công việc. Nếu tiến trình dừng giữa chừng, checkpoint hoặc khóa chống lặp giúp tiếp tục mà không xử lý sai dữ liệu đã hoàn tất.

## 8. Các quy tắc cần giữ khi tái sử dụng ca sử dụng

### Ngữ cảnh người gọi và phân quyền

HTTP có thể nhận danh tính từ session hoặc token; CLI có thể dùng tài khoản vận hành; scheduled job dùng service account; batch có thể chạy dưới danh tính của người tải tệp hoặc tài khoản hệ thống. Adapter chịu trách nhiệm xác thực nguồn danh tính và chuyển định danh đáng tin cậy vào command khi ứng dụng cần.

Không nên chỉ dựa vào filter bảo mật của HTTP để bảo vệ quy tắc quan trọng. Cùng ca sử dụng có thể được gọi từ CLI hoặc scheduler, nơi không có HTTP filter. Quyền thực hiện hành động và điều kiện nghiệp vụ cần được kiểm tra tại ranh giới phù hợp trong ứng dụng hoặc mô hình nghiệp vụ. Adapter vẫn có thể có thêm kiểm tra riêng, ví dụ quyền truy cập endpoint hoặc quyền sử dụng lệnh quản trị.

### Giao dịch và phạm vi nguyên tử

Với một thao tác đơn lẻ, ranh giới giao dịch thường đặt quanh ca sử dụng để các thay đổi lưu trữ cần thiết cùng thành công hoặc cùng rollback. Khi batch gọi ca sử dụng nhiều lần, mỗi lần gọi có thể là một giao dịch riêng hoặc một chunk có giao dịch riêng. Không nên mặc định giữ một giao dịch duy nhất cho hàng nghìn bản ghi vì nó có thể khóa dữ liệu lâu, tăng bộ nhớ và khiến rollback rất tốn kém.

Nếu ca sử dụng phải gọi dịch vụ bên ngoài qua mạng, cần cân nhắc không giữ transaction cơ sở dữ liệu mở trong suốt thời gian chờ mạng. Có thể tách bước trao đổi bên ngoài khỏi bước cập nhật cục bộ, dùng outbox/inbox hoặc một quy trình nhiều bước khi cần độ tin cậy cao. Giao dịch cơ sở dữ liệu cục bộ không tự động bảo đảm một thao tác phân tán được thực hiện đúng một lần.

### Idempotency, retry và xử lý đồng thời

Scheduler, message broker và batch có thể chạy lại sau timeout hoặc sự cố. Một thao tác nên xác định hành vi khi nhận cùng yêu cầu nhiều lần. Ví dụ, phê duyệt một đơn đã được phê duyệt có thể trả lại kết quả hiện tại nếu đó là quy ước đã chọn; hoặc trả xung đột nếu lần gọi lặp phải được coi là lỗi. Điều quan trọng là hành vi phải rõ và nhất quán.

Nếu cần bảo đảm chống lặp ở mức lưu trữ, chỉ kiểm tra trạng thái trong bộ nhớ là chưa đủ. Có thể dùng khóa duy nhất, optimistic locking, bản ghi idempotency hoặc cơ chế claim công việc có thời hạn. Khi nhiều worker cùng xử lý một đơn, cần bảo vệ chuyển trạng thái để không ghi đè kết quả hoặc phát sinh tác dụng phụ hai lần.

Retry chỉ nên áp dụng cho lỗi có khả năng hồi phục, với giới hạn số lần, khoảng chờ và quan sát được. Lỗi nghiệp vụ như đơn không đủ điều kiện không tự biến mất khi thử lại liên tục. Cần tách retry kỹ thuật khỏi yêu cầu người dùng sửa dữ liệu hoặc xin phê duyệt khác.

### Kết quả và lỗi theo từng adapter

Ca sử dụng trả kết quả theo ngôn ngữ ứng dụng. Mỗi adapter quyết định cách trình bày kết quả đó:

| Adapter | Kết quả thành công | Lỗi cần thể hiện |
|---|---|---|
| HTTP | Response body và status code | Ánh xạ lỗi đầu vào, quyền và nghiệp vụ thành mã HTTP theo API. |
| Scheduled job | Log, metric, trạng thái lần chạy | Ghi nhận lỗi từng mục, retry lỗi tạm thời hoặc đánh dấu lần chạy thất bại. |
| CLI | Thông báo cho người vận hành và exit code | Thông báo dễ hiểu; exit code khác 0 khi lệnh thất bại theo hợp đồng CLI. |
| Batch | Báo cáo tổng hợp và kết quả từng dòng | Phân loại dòng lỗi, cho phép tiếp tục hoặc dừng theo chính sách batch. |

Không đưa `ResponseEntity`, exit code hoặc cấu trúc báo cáo CSV vào kết quả của ca sử dụng. Việc chuyển đổi ở adapter giúp một ca sử dụng không bị gắn với một kiểu trình bày cụ thể.

### Theo dõi và kiểm toán

Khi cùng ca sử dụng được gọi từ nhiều nguồn, log cần giúp xác định nguồn khởi chạy, actor, mã tương quan và đối tượng được xử lý. Hãy truyền context cần thiết một cách tường minh hoặc dùng cơ chế context được kiểm soát. Không nên đọc ngầm dữ liệu từ thread-local HTTP request trong dịch vụ ứng dụng, vì scheduler và batch có thể không có request.

Các hành động quan trọng nên ghi nhận actor và kết quả kiểm toán ở nơi đáng tin cậy. Nếu cần phát sự kiện sau khi lưu dữ liệu, hãy cân nhắc transactional outbox để tránh trường hợp dữ liệu đã commit nhưng message không được gửi hoặc message được gửi trước khi transaction rollback.

## 9. Khi nào nên tách thành ca sử dụng khác?

Không phải mọi điểm khởi đầu đều nên gọi cùng một phương thức. Hãy tách ca sử dụng nếu mục tiêu, quy tắc, quyền hoặc cam kết của chúng khác nhau đáng kể. Một vài ví dụ:

- `ApproveOrder` do nhân viên thực hiện có thể yêu cầu quyền quản lý và lý do phê duyệt.
- `AutoApproveEligibleOrders` có thể là ca sử dụng riêng, áp dụng chính sách tự động và actor hệ thống; nó có thể gọi `ApproveOrder` cho từng đơn nếu ngữ nghĩa thực sự tương thích.
- `ImportOrders` có thể chịu trách nhiệm điều phối một quy trình nhập dữ liệu, tổng hợp lỗi và checkpoint; từng đơn hợp lệ sau khi chuyển đổi có thể được chuyển tới ca sử dụng tạo đơn phù hợp.
- `RetryFailedNotifications` là thao tác khác với việc gửi một thông báo lần đầu, vì chính sách retry và trạng thái cần kiểm soát khác nhau.

Tách ca sử dụng không có nghĩa phải sao chép quy tắc. Những quy tắc nghiệp vụ chung có thể được đặt trong mô hình nghiệp vụ hoặc một dịch vụ miền phù hợp. Tầng ứng dụng điều phối chúng theo từng mục tiêu. Không nên tạo một phương thức tổng quát với hàng loạt cờ như `isScheduled`, `isBatch`, `isCli` nếu các cờ đó khiến cùng một thao tác có nhiều nhánh hành vi khó hiểu.

## 10. Kiểm thử khả năng tái sử dụng

Nên kiểm thử tầng ứng dụng qua hợp đồng ca sử dụng, không cần dựng HTTP server, shell hoặc scheduler để xác nhận quy tắc chính:

| Phạm vi kiểm thử | Nội dung | Ví dụ |
|---|---|---|
| Unit test ca sử dụng | Điều phối, quyền và quy tắc nghiệp vụ | Đơn hợp lệ chuyển sang trạng thái đã phê duyệt; actor không có quyền bị từ chối. |
| Test idempotency | Gọi lặp có hành vi xác định | Phê duyệt lại cùng đơn trả kết quả đã định và không tạo tác dụng phụ trùng. |
| Test adapter HTTP | Ánh xạ request/principal thành command | Mã đơn, actor và lý do được chuyển đúng; lỗi ứng dụng thành response đúng. |
| Test scheduled job | Chọn và gọi các mục đến hạn | Job truyền actor hệ thống, giới hạn số mục và ghi nhận lỗi theo chính sách. |
| Test CLI | Phân tích đối số và định dạng kết quả | Mã đơn sai bị từ chối; thành công trả thông báo và exit code phù hợp. |
| Test batch | Ánh xạ từng dòng và phục hồi | Dòng sai được báo cáo, dòng hợp lệ được xử lý; checkpoint tránh xử lý lại ngoài ý muốn. |

Một dấu hiệu tốt là unit test của `ApproveOrderService` không cần thay đổi khi thêm một adapter CLI hoặc batch. Khi thêm adapter, phần cần kiểm thử chủ yếu là cách adapter chuyển đầu vào, actor và kết quả. Nếu phải sửa ca sử dụng chỉ vì đổi định dạng CSV hoặc đổi tên HTTP header, có thể hợp đồng ứng dụng đang bị rò rỉ chi tiết của adapter.

## 11. Tự rà soát thiết kế

Khi muốn gọi một chức năng từ nhiều nguồn, hãy tự hỏi:

1. Các nguồn khởi chạy có thực sự yêu cầu cùng một mục tiêu và cùng cam kết nghiệp vụ không?
2. Có một hợp đồng ứng dụng rõ ràng để mọi adapter gọi trực tiếp không?
3. Command có chứa dữ liệu cần thiết cho ca sử dụng và tránh phụ thuộc vào HTTP, CLI hoặc định dạng tệp không?
4. Danh tính người gọi có được xác thực ở adapter và kiểm tra quyền ở vị trí phù hợp không?
5. Phạm vi giao dịch, retry, idempotency và xử lý đồng thời đã phù hợp với request đơn lẻ hay batch chưa?
6. Mỗi adapter có cách thể hiện kết quả và lỗi riêng mà không làm thay đổi hợp đồng ứng dụng không?
7. Có thể kiểm thử ca sử dụng độc lập với cách khởi chạy không?

Nếu một adapter phải gọi endpoint nội bộ qua HTTP chỉ để dùng lại nghiệp vụ, hãy xem xét gọi hợp đồng ứng dụng trực tiếp khi chúng ở cùng ranh giới triển khai. Nếu nhiều adapter đang sao chép quy tắc, hãy đưa quy tắc về đúng ca sử dụng hoặc mô hình nghiệp vụ. Nếu các hành vi khác mục tiêu, hãy tách ca sử dụng thay vì ép chúng vào một API chung.

## Kết luận

Tầng ứng dụng giúp nhiều điểm khởi đầu dùng chung hành vi bằng cách công bố hợp đồng ca sử dụng độc lập với giao thức. HTTP, scheduler, CLI và batch chuyển dữ liệu riêng của chúng thành command, cung cấp ngữ cảnh người gọi đáng tin cậy rồi gọi cùng hợp đồng khi mục tiêu nghiệp vụ giống nhau. Tầng ứng dụng điều phối quy tắc và giao dịch; từng adapter xử lý cách nhận dữ liệu, xác thực ở ranh giới, hiển thị kết quả và phục hồi lỗi theo đặc thù của nó. Thiết kế này giảm trùng lặp, giữ hành vi nhất quán và cho phép bổ sung cách khởi chạy mới mà không phải viết lại ca sử dụng.
