# Nâng cấp định nghĩa workflow khi còn phiên đang chạy

Trong ứng dụng serverless, workflow có thể điều phối một quy trình kéo dài từ vài giây đến nhiều giờ hoặc nhiều ngày. Trong lúc các execution đang chờ thanh toán, chờ phê duyệt hoặc chờ một event bên ngoài, đội phát triển vẫn cần sửa định nghĩa workflow để bổ sung bước, thay đổi retry, cập nhật timeout hoặc sửa lỗi.

Thách thức là một lần triển khai mới không chỉ ảnh hưởng đến execution được tạo sau đó. Những execution đã bắt đầu có thể vẫn đang giữ state theo định nghĩa cũ, trong khi task handler, event schema hoặc dịch vụ phụ thuộc đã được nâng cấp. Nếu không quản lý phiên bản và tính tương thích, quy trình đang chạy có thể thất bại giữa chừng hoặc tạo side effect trùng lặp.

Bài học này trình bày cách nâng cấp workflow an toàn khi còn execution đang hoạt động: phân biệt workflow definition với execution state, quản lý version, giữ tương thích dữ liệu và task, chọn chiến lược rollout, và chỉ migrate execution đang chạy khi có cơ chế rõ ràng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao workflow definition và execution đang chạy cần được quản lý riêng.
- Phân biệt cập nhật definition, tạo version mới và migrate một execution đang chạy.
- Thiết kế workflow versioning và định tuyến execution mới sang phiên bản phù hợp.
- Giữ tương thích giữa state dữ liệu, event contract và task handler qua nhiều phiên bản.
- Chọn chiến lược drain, backward-compatible rollout hoặc explicit migration.
- Lập kế hoạch triển khai, theo dõi, rollback và ngừng hỗ trợ phiên bản workflow cũ.

## 1. Workflow definition và execution đang chạy là hai thứ khác nhau

**Workflow definition** mô tả quy trình: các state hoặc step, thứ tự chuyển tiếp, điều kiện rẽ nhánh, task được gọi, timeout, retry, catch, parallel branch và quy tắc kết thúc.

**Execution** là một lần chạy cụ thể của workflow. Execution có input riêng, state hiện tại, dữ liệu trung gian, lịch sử các bước đã hoàn thành và những task đang chờ. Nhiều execution có thể cùng chạy từ một definition.

Ví dụ, workflow xử lý đơn hàng có thể gồm:

1. Kiểm tra đơn hàng.
2. Giữ hàng trong kho.
3. Thu tiền.
4. Gửi yêu cầu giao hàng.
5. Đánh dấu đơn hoàn tất.

Một execution có thể đang chờ kết quả thanh toán ở bước 3 khi đội phát triển triển khai definition mới thêm bước kiểm tra rủi ro trước khi giữ hàng. Execution cũ đã đi qua các bước trước đó; nó không thể tự quay lại đầu quy trình để chạy bước mới mà không có một quyết định nghiệp vụ và migration rõ ràng.

| Thành phần | Ý nghĩa | Câu hỏi khi nâng cấp |
|---|---|---|
| Workflow definition | Đồ thị các state, task và transition | Execution mới sẽ dùng định nghĩa nào? |
| Workflow version | Bản definition bất biến đã được phát hành | Có thể tái tạo hoặc rollback về bản này không? |
| Execution state | State hiện tại và dữ liệu của một lần chạy | Dữ liệu có còn hợp lệ với phiên bản mới không? |
| Task implementation | Java function, service hoặc API được task gọi | Execution cũ có còn gọi được handler tương thích không? |
| Event/data contract | Schema input, output và message giữa các bước | Các phiên bản producer/consumer có hiểu dữ liệu của nhau không? |

**Cập nhật definition không đồng nghĩa migrate execution đang chạy.** Nền tảng có thể giữ definition mà execution đã bắt đầu sử dụng, hoặc có semantics cập nhật khác nhau tùy sản phẩm. Cần xác minh hành vi của orchestrator cụ thể trước khi triển khai. Không nên giả định mọi execution sẽ tự động chuyển sang definition mới.

## 2. Vì sao nâng cấp khi workflow còn chạy dễ gây lỗi?

Các workflow dài hạn thường tồn tại qua nhiều lần phát hành ứng dụng. Một execution có thể bắt đầu bằng code phiên bản A, chờ một callback trong vài giờ, rồi tiếp tục chạy sau khi hệ thống đã triển khai code phiên bản B.

Những thay đổi sau có thể làm execution đang chạy gặp lỗi:

- **Đổi tên hoặc xóa state:** execution đang lưu tên state cũ có thể không tiếp tục được nếu nền tảng không giữ snapshot definition.
- **Đổi cấu trúc dữ liệu:** bước tiếp theo mong đợi field mới hoặc kiểu dữ liệu khác với state đang lưu.
- **Thay đổi task input/output:** Java handler mới không còn đọc được payload cũ hoặc output mới không tương thích với state transition cũ.
- **Thay đổi retry và timeout:** execution cũ có thể retry theo policy khác hoặc hết hạn sớm hơn dự kiến.
- **Thay đổi nhánh điều kiện:** một execution đang chạy có thể đi vào nhánh mới mà state hiện tại chưa đáp ứng điều kiện.
- **Thay đổi callback/task token:** task đang chờ callback có thể không nhận được tín hiệu theo cách mới.
- **Thay implementation của function:** definition cũ có thể vẫn trỏ đến một alias hoặc endpoint mutable đã được cập nhật sang code mới.
- **Thay đổi side effect:** task được chạy lại sau lỗi có thể gửi thanh toán, email hoặc yêu cầu giao hàng lần thứ hai.

Vấn đề không chỉ nằm ở definition. Một workflow version cũ có thể gọi cùng tên Lambda function hoặc HTTP endpoint đã được cập nhật. Vì thế, quản lý version của workflow mà bỏ qua version của task implementation vẫn chưa đủ để bảo vệ execution cũ.

## 3. Chọn chiến lược nâng cấp

Có ba chiến lược thường dùng. Chọn dựa trên thời gian sống của execution, khả năng tương thích và mức hỗ trợ migration của nền tảng.

| Chiến lược | Cách làm | Khi phù hợp | Đánh đổi |
|---|---|---|---|
| Drain phiên bản cũ | Ngừng tạo execution mới từ definition cũ, chờ execution cũ kết thúc | Quy trình có thời lượng hữu hạn và số execution đang chạy có thể chờ | Cần duy trì phiên bản cũ lâu hơn; quy trình rất dài làm chậm phát hành |
| Backward-compatible rollout | Definition và task mới vẫn hiểu state/input/output của phiên bản cũ | Execution cũ cần tiếp tục chạy trong khi hệ thống đã triển khai bản mới | Phải duy trì tương thích nhiều phiên bản và kiểm thử kỹ |
| Explicit migration | Chuyển execution đang chạy tại checkpoint đã xác định sang workflow version mới | Có yêu cầu nghiệp vụ rõ ràng và nền tảng hoặc ứng dụng hỗ trợ migration | Phức tạp; phải bảo toàn state, side effect, callback và lịch sử |

### Drain phiên bản cũ

Đây thường là cách đơn giản và dễ kiểm soát nhất nếu workflow có thời gian chạy tối đa rõ ràng:

1. Phát hành workflow version mới.
2. Chuyển điểm bắt đầu execution mới sang version mới.
3. Giữ definition, task handler và schema cũ để execution đang chạy tiếp tục.
4. Theo dõi số execution còn hoạt động của version cũ.
5. Chỉ ngừng version cũ khi không còn execution cần nó hoặc đã xử lý các execution quá hạn theo chính sách.

Không nên xóa function, secret, queue hoặc endpoint mà workflow cũ còn cần gọi. Một workflow cũ có thể ở trạng thái chờ rất lâu nên việc “không thấy invocation gần đây” không chứng minh version đó không còn được sử dụng.

### Backward-compatible rollout

Khi không thể chờ tất cả execution cũ kết thúc, code mới cần hiểu được dữ liệu cũ. Ví dụ, nếu phiên bản cũ không có trường riskLevel, handler mới có thể áp dụng giá trị mặc định có chủ đích.

Một nguyên tắc hữu ích là **mở rộng trước, thu hẹp sau**:

1. Mở rộng handler để đọc cả schema cũ và schema mới.
2. Triển khai consumer/task tương thích.
3. Phát hành workflow definition mới ghi hoặc sử dụng field mới.
4. Chờ execution cũ kết thúc và dữ liệu cũ hết thời hạn cần hỗ trợ.
5. Sau đó mới bỏ nhánh tương thích cũ trong một lần phát hành riêng.

Không đổi nghĩa của field đang tồn tại. Nếu một field đổi đơn vị hoặc ngữ nghĩa, hãy tạo field mới hoặc tăng schema version. Một trường amount đang biểu diễn đồng không thể âm thầm đổi sang đơn vị xu mà không làm hỏng execution cũ.

### Explicit migration

Migration execution là thao tác chuyển một lần chạy đang ở giữa quy trình sang definition mới. Không phải orchestrator nào cũng hỗ trợ sửa hoặc chuyển execution đang chạy. Nếu nền tảng không cung cấp khả năng đó, ứng dụng có thể phải thiết kế checkpoint và cơ chế resume riêng.

Chỉ migrate tại ranh giới ổn định, ví dụ sau khi đã lưu kết quả giữ hàng và trước khi bắt đầu thanh toán. Một quy trình migration cần:

- Xác định execution nào đủ điều kiện và state nào có thể chuyển.
- Chặn hoặc kiểm soát việc execution cũ tiếp tục xử lý trong lúc chuyển.
- Đọc state đã lưu và chuyển đổi sang schema mới một cách có kiểm tra.
- Ghi nhận version nguồn, version đích và migration ID.
- Bảo toàn correlation ID, business ID, deadline và các khóa idempotency.
- Đảm bảo task hoặc side effect đã hoàn tất không bị chạy lại.
- Có cách tiếp tục từ state mới hoặc khôi phục execution cũ nếu migration thất bại.

Không nên chỉnh sửa trực tiếp state của execution đang chạy bằng thao tác ngoài orchestrator nếu nền tảng không hỗ trợ. Làm vậy có thể khiến state lưu trong ứng dụng không khớp với history, task token hoặc checkpoint mà engine quản lý.

## 4. Version hóa workflow definition

Một workflow version nên đại diện cho một definition đã được kiểm thử và phát hành. Sau khi publish, không sửa nội dung của version đó; mọi thay đổi tạo ra version mới.

Có thể dùng quy ước như:

| Version | Thay đổi | Trạng thái |
|---|---|---|
| order-workflow v1 | Kiểm tra đơn, giữ hàng, thu tiền, giao hàng | Đang phục vụ execution cũ |
| order-workflow v2 | Thêm kiểm tra rủi ro và nhánh từ chối | Dùng cho execution mới |
| order-workflow v3 | Thêm xử lý hoàn tiền và cập nhật timeout | Đang thử nghiệm |

Mỗi execution nên có thông tin để xác định nó chạy theo phiên bản nào. Tùy nền tảng, version có thể được lưu trong execution metadata, definition ARN, alias đã resolve hoặc input của workflow. Nếu cần audit, hãy lưu thêm workflowVersion trong dữ liệu nghiệp vụ.

### Version bất biến và alias

Version bất biến giúp execution mới chọn đúng definition. Alias hoặc stage là tên ổn định để định tuyến yêu cầu bắt đầu execution đến một version cụ thể.

Ví dụ:

- order-workflow:prod trỏ đến v2.
- order-workflow:canary trỏ một phần traffic thử nghiệm đến v3.
- order-workflow:v1 vẫn được giữ để execution cũ hoàn tất.

Alias thường hữu ích cho việc chuyển traffic của **execution mới**. Không nên mặc định thay alias sẽ đổi version của execution đã bắt đầu; hãy kiểm tra semantics của nền tảng và cách execution resolve alias tại thời điểm start.

### Ví dụ với AWS Step Functions

AWS Step Functions hỗ trợ publish version cho state machine và tạo alias trỏ đến một hoặc nhiều version. Khi bắt đầu execution, có thể sử dụng version ARN hoặc alias ARN để chỉ định bản workflow được chọn.

Java AWS SDK v2 có thể bắt đầu execution qua alias hoặc version ARN:

~~~java
import software.amazon.awssdk.services.sfn.SfnClient;
import software.amazon.awssdk.services.sfn.model.StartExecutionRequest;
import software.amazon.awssdk.services.sfn.model.StartExecutionResponse;

public final class WorkflowStarter {
    private final SfnClient stepFunctions;
    private final String workflowAliasArn;

    public WorkflowStarter(
            SfnClient stepFunctions,
            String workflowAliasArn) {
        this.stepFunctions = stepFunctions;
        this.workflowAliasArn = workflowAliasArn;
    }

    public String start(String inputJson) {
        StartExecutionResponse response = stepFunctions.startExecution(
                StartExecutionRequest.builder()
                        .stateMachineArn(workflowAliasArn)
                        .input(inputJson)
                        .build());

        return response.executionArn();
    }
}
~~~

Giá trị workflowAliasArn được cấu hình theo môi trường, ví dụ ARN alias production của state machine. Pipeline triển khai chịu trách nhiệm cập nhật alias sau khi version mới đã được kiểm tra. Nếu cần execution luôn dùng đúng một version đã chọn, có thể truyền version ARN cụ thể thay vì alias.

Đây là ví dụ riêng cho AWS Step Functions. Với orchestrator khác, hãy tìm cơ chế tương đương như immutable workflow revision, deployment version, release channel hoặc definition snapshot. Cách một execution đang chạy gắn với version có thể khác nhau theo sản phẩm.

## 5. Giữ tương thích state và data contract

Execution đang chạy có thể giữ state đã được serialize từ nhiều giờ trước. Khi definition hoặc task được nâng cấp, cần đảm bảo dữ liệu đó vẫn đọc được.

### Thêm field theo cách tương thích

Giả sử state cũ lưu:

~~~json
{
  "orderId": "ORD-1042",
  "amount": 1250000
}
~~~

Phiên bản mới cần thêm riskLevel. Có thể dùng giá trị mặc định khi field vắng mặt:

~~~json
{
  "orderId": "ORD-1042",
  "amount": 1250000,
  "riskLevel": "STANDARD",
  "schemaVersion": 2
}
~~~

Handler mới cần chấp nhận cả input cũ không có riskLevel và input mới có field này. Nếu logic nghiệp vụ không có default an toàn, hãy chuyển execution cũ qua một nhánh tương thích hoặc yêu cầu migration có kiểm soát thay vì tự đoán.

### Các quy tắc tương thích

- Thêm field tùy chọn với default rõ ràng thường an toàn hơn xóa hoặc đổi tên field.
- Không thay kiểu dữ liệu hoặc đơn vị của field hiện có mà không tăng schema version.
- Giữ khả năng đọc output cũ trong các task mà execution cũ có thể gọi.
- Giữ tên state và transition cần thiết cho execution đã lưu, nếu engine dùng definition hiện tại để tiếp tục.
- Không giả định mọi field trong execution input đều được truyền nguyên vẹn đến mọi task; kiểm tra mapping và payload contract ở từng bước.
- Khi thay đổi event schema, hỗ trợ producer và consumer chạy lệch phiên bản trong khoảng rollout.
- Duy trì các enum value cũ cho đến khi không còn execution hoặc message dùng chúng.

### Tách workflow version khỏi schema version

Workflow version và schema version là hai thứ khác nhau. Một workflow v3 có thể vẫn đọc event schema v1 và v2; một workflow v2 có thể xử lý nhiều loại event cùng schema version nếu hợp đồng nghiệp vụ cho phép.

Nên ghi rõ version ở những ranh giới cần thiết:

~~~json
{
  "workflowVersion": "order-workflow-v2",
  "schemaVersion": 2,
  "correlationId": "corr-71a9",
  "orderId": "ORD-1042"
}
~~~

Không cần đưa version vào mọi object nội bộ nếu không có ích. Nhưng ở ranh giới giữa producer, orchestrator và task handler, metadata version giúp xác định cách diễn giải payload và hỗ trợ điều tra lỗi.

## 6. Task handler cũng phải tương thích với execution cũ

Một lỗi thường gặp là giữ workflow definition v1 nhưng thay code Lambda hoặc HTTP service mà v1 gọi. Nếu task đang chạy dùng một tên function hoặc endpoint mutable, execution cũ có thể gọi code mới dù definition không đổi.

Có thể kiểm soát bằng một số cách:

- **Versioned function target:** workflow v1 gọi function version hoặc alias dành riêng cho v1; workflow v2 gọi target mới.
- **Stable handler contract:** giữ API input/output tương thích, handler mới hiểu cả payload cũ.
- **Adapter theo workflow version:** task nhận metadata version rồi chuyển payload về mô hình nội bộ phù hợp.
- **Drain task implementation cũ:** chỉ gỡ code cũ sau khi không còn execution nào có thể gọi nó.

Ví dụ, handler Java có thể nhận schemaVersion và chuyển về command nội bộ:

~~~java
public record OrderTaskInput(
        String orderId,
        long amount,
        Integer schemaVersion,
        String riskLevel) {
}

public record ProcessOrderCommand(
        String orderId,
        long amount,
        String riskLevel) {
}

public final class OrderTaskAdapter {
    public ProcessOrderCommand adapt(OrderTaskInput input) {
        int version = input.schemaVersion() == null
                ? 1
                : input.schemaVersion();

        if (version == 1) {
            return new ProcessOrderCommand(
                    input.orderId(),
                    input.amount(),
                    "STANDARD");
        }

        if (version == 2) {
            return new ProcessOrderCommand(
                    input.orderId(),
                    input.amount(),
                    input.riskLevel());
        }

        throw new IllegalArgumentException(
                "Unsupported schemaVersion: " + version);
    }
}
~~~

Đây là adapter minh họa. Trong hệ thống thật, cần kiểm tra null, giá trị enum, giới hạn amount và quy tắc default. Nếu schemaVersion không được cung cấp, chỉ dùng mặc định v1 khi hợp đồng cũ đã quy định rõ.

## 7. Retry, timeout và side effect khi nâng cấp

Một workflow đang chờ retry có thể chạy lại task sau khi code đã được cập nhật. Nếu lần chạy trước đã tạo side effect nhưng engine chưa ghi nhận thành công, task có thể được gọi lại.

Ví dụ:

1. Task gọi cổng thanh toán và giao dịch đã thành công.
2. Function timeout trước khi trả kết quả cho orchestrator.
3. Workflow retry task.
4. Handler mới gọi thanh toán lần nữa.

Versioning không giải quyết được trường hợp này. Cần idempotency key ổn định qua các lần retry và qua phiên bản workflow. Ví dụ, dùng orderId cộng với loại thao tác nghiệp vụ làm khóa, thay vì tạo UUID mới mỗi invocation.

Khi thay đổi retry policy, cần đánh giá execution đang chạy:

- Retry count hoặc retry interval đã lưu có được giữ nguyên không?
- Task đang chạy có nhận timeout mới không?
- Catch branch có còn nhận đúng error name và output format không?
- DLQ hoặc compensation path có còn tương thích không?
- Thay đổi timeout có thể khiến side effect bị thực hiện lại không?

Đừng xem rollback definition là rollback side effect. Nếu v2 đã gửi lệnh giao hàng hoặc thu tiền, quay lại v1 không tự hoàn tác các hành động đó. Cần workflow bù trừ (compensation) hoặc quy trình nghiệp vụ riêng để xử lý.

## 8. Quy trình triển khai version mới khi execution cũ còn hoạt động

Một rollout có kiểm soát có thể thực hiện theo các bước:

1. **Lập inventory execution:** đếm execution đang chạy theo workflow version, state hiện tại, thời điểm bắt đầu và thời gian chạy tối đa.
2. **Phân tích thay đổi:** xác định state, field, task, retry, timeout, callback và side effect nào bị ảnh hưởng.
3. **Chuẩn bị tương thích:** cập nhật task handler để đọc payload cũ/mới; bổ sung schema version hoặc adapter nếu cần.
4. **Tạo workflow version mới:** giữ bản cũ bất biến và triển khai definition mới dưới version riêng.
5. **Kiểm tra trước phát hành:** validate definition, kiểm thử đường đi thành công, lỗi, retry, timeout, compensation và execution dùng input cũ.
6. **Canary execution mới:** định tuyến một tỷ lệ nhỏ execution mới sang version mới hoặc chạy trong môi trường staging với dữ liệu đại diện.
7. **Chuyển traffic:** cập nhật alias hoặc routing để execution mới dùng version mới.
8. **Theo dõi song song:** so sánh tỷ lệ thành công, thời gian hoàn thành, lỗi task, retry, timeout và side effect của từng version.
9. **Drain version cũ:** giữ task handler, secret, quyền và endpoint cần thiết cho execution cũ.
10. **Retire có kiểm soát:** chỉ gỡ version cũ khi không còn execution, callback, scheduled start hoặc message nào cần nó.

~~~mermaid
flowchart TD
    A["Đang chạy workflow v1"] --> B["Tạo và kiểm thử v2"]
    B --> C["Task handler hỗ trợ schema cũ và mới"]
    C --> D["Canary execution mới trên v2"]
    D --> E{"Kết quả đạt?"}
    E -->|Không| F["Giữ routing ở v1 / sửa v2"]
    E -->|Có| G["Chuyển execution mới sang v2"]
    G --> H["v1 tiếp tục hoàn tất execution cũ"]
    H --> I["Không còn execution v1"]
    I --> J["Ngừng hỗ trợ v1"]
~~~

### Theo dõi execution theo version

Nên có dashboard hoặc truy vấn vận hành cho biết:

- Số execution RUNNING theo workflow version.
- Số execution ở từng state và tuổi của state đó.
- Execution đang chờ callback, timer hoặc message bên ngoài.
- Tỷ lệ thành công/thất bại và thời gian hoàn thành theo version.
- Task retry, timeout, throttling và lỗi tích hợp.
- Execution quá thời gian dự kiến hoặc mắc kẹt ở một state.
- Các side effect đã phát sinh và trạng thái đối soát tương ứng.

Không chỉ đếm execution đang chạy. Một execution có thể đang ở trạng thái chờ rất lâu và vẫn phụ thuộc vào task handler hoặc secret của version cũ.

## 9. Rollback và phục hồi

Rollback thường có nghĩa là chuyển **execution mới** trở lại version trước. Nó không nhất thiết thay đổi execution v2 đang chạy và không tự đảo ngược dữ liệu hoặc side effect đã xảy ra.

Một kế hoạch rollback nên xác định:

- Điều kiện dừng phát execution mới vào version mới.
- Alias hoặc routing sẽ trỏ về version nào.
- Execution v2 đang chạy sẽ được tiếp tục, drain hay migrate.
- Task handler và schema nào cần giữ để v2 có thể hoàn tất.
- Cách xử lý dữ liệu đã được ghi bởi v2 nhưng không tương thích với v1.
- Cách đối soát hoặc compensation cho thanh toán, giao hàng, notification đã thực hiện.
- Điều kiện cho phép phát hành lại version mới sau khi sửa lỗi.

Nếu v2 đã ghi dữ liệu theo schema mới, không nên xóa field hoặc ép dữ liệu về schema cũ một cách tự động. Hãy dùng migration dữ liệu có kiểm tra và giữ khả năng đọc tương thích trong giai đoạn rollback.

## 10. Ví dụ tình huống: thêm bước kiểm tra rủi ro đơn hàng

Workflow v1:

~~~mermaid
flowchart LR
    A["OrderCreated"] --> B["Reserve inventory"]
    B --> C["Charge payment"]
    C --> D["Create shipment"]
    D --> E["Complete"]
~~~

Workflow v2 thêm bước kiểm tra rủi ro:

~~~mermaid
flowchart LR
    A["OrderCreated"] --> B["Risk assessment"]
    B --> C{"Risk acceptable?"}
    C -->|Yes| D["Reserve inventory"]
    D --> E["Charge payment"]
    E --> F["Create shipment"]
    F --> G["Complete"]
    C -->|No| H["Reject / release order"]
~~~

Khi triển khai v2, có thể đồng thời tồn tại:

- Execution v1 đã giữ hàng và đang chờ thanh toán.
- Execution v1 đã thu tiền và đang chờ tạo shipment.
- Execution v2 mới bắt đầu ở bước risk assessment.
- Execution v2 bị từ chối và đang chạy nhánh reject.

Không nên chuyển execution v1 đang chờ thanh toán quay lại bước risk assessment một cách tự động. Việc đó có thể thay đổi quyết định nghiệp vụ sau khi hàng đã được giữ hoặc gây side effect lặp. Nếu yêu cầu mới bắt buộc áp dụng cho đơn cũ, cần một quy trình nghiệp vụ riêng xác định trạng thái nào phải đánh giá lại, có cần release inventory hay hoàn tiền không, và cách ghi nhận quyết định.

Trong tình huống này, chiến lược thường dễ kiểm soát là giữ v1 cho execution cũ, dùng v2 cho execution mới, và chỉ migrate một tập execution được chọn khi đã có quy tắc nghiệp vụ và checkpoint rõ ràng.

## 11. Checklist nâng cấp workflow an toàn

- [ ] Đã xác định definition/version mà từng execution đang chạy sử dụng.
- [ ] Đã xác minh semantics cập nhật definition của orchestrator cụ thể.
- [ ] Version đã phát hành được giữ bất biến và có thể tham chiếu lại.
- [ ] Execution mới được định tuyến rõ ràng đến version mong muốn.
- [ ] Task handler còn tương thích với payload của execution cũ.
- [ ] Schema version, default và quy tắc chuyển đổi dữ liệu đã được định nghĩa.
- [ ] State, task token, callback và checkpoint không bị mất khi rollout.
- [ ] Retry, timeout, catch và compensation đã được kiểm thử cho cả version.
- [ ] Side effect có idempotency key ổn định qua retry và version.
- [ ] Có inventory execution đang chạy và tiêu chí drain version cũ.
- [ ] Canary và dashboard có thể phân biệt lỗi theo workflow version.
- [ ] Rollback đã tính đến execution mới, execution cũ và dữ liệu đã ghi.
- [ ] Không xóa function, secret, policy hoặc endpoint còn được version cũ sử dụng.
- [ ] Chỉ retire version cũ khi đã xác minh không còn execution hoặc trigger phụ thuộc.

## Tự kiểm tra

1. Vì sao cập nhật workflow definition không đồng nghĩa các execution đang chạy tự chuyển sang definition mới?
2. Một execution v1 có thể bị ảnh hưởng như thế nào nếu Lambda function mà nó gọi được cập nhật sang code v2?
3. Khi nào nên drain phiên bản cũ thay vì migrate execution đang chạy?
4. Vì sao thêm field tùy chọn thường dễ tương thích hơn đổi kiểu hoặc đổi nghĩa field cũ?
5. Alias của workflow giúp định tuyến execution mới ra sao và cần kiểm tra điều gì đối với execution đã bắt đầu?
6. Vì sao rollback workflow definition không tự hoàn tác thanh toán hoặc lệnh giao hàng?
7. Những điều kiện nào cần đạt trước khi ngừng hỗ trợ một workflow version cũ?

Khi workflow có thể chạy lâu hơn một lần phát hành ứng dụng, versioning phải bao phủ cả definition, state schema, task handler và side effect. Giữ version cũ đủ lâu cho execution hoàn tất, định tuyến execution mới có chủ đích và chỉ migrate tại checkpoint được kiểm soát giúp đội phát triển nâng cấp quy trình mà không làm gián đoạn các phiên đang chạy.

