# Emergency feature disablement — Vô hiệu hóa khẩn cấp tính năng

Bài học thuộc chương **Incident Response** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Nội dung tập trung vào cách dừng một khả năng đang bị lạm dụng mà vẫn giữ đúng quy tắc về quyền, trạng thái, transaction, phê duyệt và chống thực hiện trùng.

Khi phát hiện một API có thể bỏ qua phê duyệt hoặc hoàn tiền nhiều lần, sửa code thường cần thời gian để triển khai. Một cơ chế vô hiệu hóa khẩn cấp giúp thu hẹp tác hại trong khoảng đó. Tuy nhiên, nút đã chuyển sang “OFF” không chứng minh worker đã dừng gửi lệnh hoặc request đang chạy không còn tạo tác động.

Mục tiêu của bài học là thiết kế một cơ chế có thể trả lời được: **đang chặn hành động nào, ở phạm vi nào, từ điểm quyết định nào và bằng chứng nào cho thấy việc chặn có hiệu lực?**

Sau bài học, bạn cần có thể:

- Chọn phạm vi vô hiệu hóa theo thao tác nghiệp vụ và mức rủi ro.
- Phân biệt dừng tiếp nhận, đóng băng thực thi và xử lý giao dịch đã có tác động.
- Đặt guard tại API, application service, worker và ranh giới tạo tác động.
- Xử lý cấu hình lỗi, cache cũ, node mất kết nối và race với transaction.
- Giữ đúng state machine và idempotency trong thời gian tạm dừng.
- Bảo vệ quyền thay đổi cơ chế khẩn cấp và lưu bằng chứng vận hành.
- Kiểm thử việc kích hoạt, xác minh hiệu lực và mở lại có kiểm soát.

## 1. Vô hiệu hóa khẩn cấp thực sự thay đổi điều gì?

**Emergency feature disablement** là khả năng chuyển một phần hành vi hệ thống sang trạng thái hạn chế theo quy trình đã chuẩn bị trước. Đối tượng bị hạn chế có thể là một thao tác, một phương thức thanh toán, một tenant, một vùng triển khai hoặc một phiên bản luồng xử lý.

Ví dụ:

~~~text
Cho phép xem trạng thái yêu cầu hoàn tiền.
Tạm dừng tạo yêu cầu hoàn tiền tự động mới.
Đóng băng worker gửi lệnh hoàn tiền nếu đường thực thi đang bị khai thác.
Tiếp tục nhận kết quả hợp lệ của lệnh đã gửi để đối soát.
~~~

Đây là một thay đổi chính sách vận hành có ảnh hưởng đến nghiệp vụ. Cần xác định cả hành vi bị chặn lẫn đường xử lý cần duy trì để không mất dấu nghĩa vụ đã phát sinh.

AWS Well-Architected mô tả emergency lever là quy trình nhanh, được kiểm thử trước, dùng để vô hiệu hóa, giới hạn hoặc thay đổi hành vi khi có sự cố; tiêu chí kích hoạt và giải phóng cần rõ ràng. Bài học này áp dụng ý tưởng đó cho việc khoanh vùng lạm dụng logic nghiệp vụ. [AWS: Implement emergency levers](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel05-bp07.html).

### 1.1. Những cơ chế có liên quan

| Cơ chế | Mục đích chính | Điều cần lưu ý khi xử lý sự cố logic |
|---|---|---|
| Feature flag phát hành | Chọn phiên bản hoặc nhóm người dùng được dùng tính năng | Nhánh cũ cũng có thể chứa lỗi; targeting cần đúng phạm vi |
| Công tắc khẩn cấp | Hạn chế hành động gây hại theo hợp đồng định trước | Cần bao phủ mọi đường thực thi và có bằng chứng hiệu lực |
| Circuit breaker | Giảm gọi tới dependency đang lỗi theo tín hiệu vận hành | Dependency khỏe vẫn có thể thực hiện một nghiệp vụ sai |
| Rollback code | Quay về phiên bản phần mềm trước | Không tự đảo ngược dữ liệu hoặc lệnh đã gửi |
| Khóa đối tượng/tenant | Cô lập đối tượng hoặc phạm vi cụ thể | Phải xác minh danh tính và quyền theo đối tượng ở phía server |
| WAF hoặc chặn route | Giảm một kiểu traffic tại biên | Có thể bỏ sót worker, API khác hoặc luồng nội bộ |

Các cơ chế có thể phối hợp. Một flag chỉ trở thành cơ chế khẩn cấp đáng tin khi cách sử dụng, quyền điều khiển, fallback và điểm thực thi đáp ứng hợp đồng của sự cố.

## 2. Bắt đầu từ bất biến đang bị vi phạm

Giả sử hệ thống hoàn tiền tự động phải bảo vệ:

~~~text
Mỗi lần hoàn mới không vượt số tiền còn được hoàn; tổng đã hoàn không vượt giá trị được phép hoàn của đơn.
Yêu cầu thuộc đúng tenant và người có quyền trên đơn.
Phê duyệt cần thiết đã hoàn tất, gắn với đúng số tiền và phiên bản.
Một thao tác nghiệp vụ chỉ tạo một tác động hoàn tiền.
~~~

Sự cố xuất hiện khi hai worker cùng thực thi một yêu cầu hoặc khi dữ liệu số tiền bị thay đổi sau phê duyệt. Thao tác cần ngăn là **tạo thêm tác động hoàn tiền chưa được kiểm soát**, không đơn thuần là truy cập màn hình.

Hãy viết mục tiêu khoanh vùng theo dạng có thể kiểm tra:

~~~text
Phạm vi: hoàn tiền tự động cho tenant T.
Điểm nguy hiểm: gửi lệnh tạo hoàn tiền tới provider.
Mục tiêu: không phát sinh lần gửi mới sau ranh giới hiệu lực đã xác nhận.
Ngoại lệ cần quản lý: lệnh đã gửi trước ranh giới, kết quả chưa rõ.
Đường tiếp tục: xem trạng thái và đối soát kết quả có xác thực.
~~~

Nếu chưa rõ lỗi chỉ ở bước tiếp nhận hay đã nằm trong worker, ưu tiên chọn chế độ chặn phù hợp với đường gây hại. Cho queue cũ tiếp tục chạy là một quyết định nghiệp vụ cần bằng chứng rằng những job đó an toàn.

## 3. Xác định phạm vi và thứ tự ưu tiên

### 3.1. Tắt theo hành động nghiệp vụ

Tên như `refund.enabled` dễ tạo cách hiểu khác nhau giữa các đội. Một service hiểu là “không hiện nút”, service khác hiểu là “không tạo yêu cầu”, còn worker vẫn gửi tiền.

Một hợp đồng rõ hơn:

| Hành động | Ví dụ định danh | Ý nghĩa |
|---|---|---|
| Tiếp nhận ý định mới | `CREATE_REFUND` | Tạo yêu cầu hoàn tiền mới |
| Tạo tác động | `EXECUTE_REFUND` | Gửi một lệnh hoàn tiền mới |
| Đọc kết quả | `READ_REFUND_STATUS` | Xem trạng thái trong phạm vi có quyền |
| Đối soát | `RECONCILE_REFUND` | Tra cứu và ghi nhận kết quả thực tế theo workflow |

Tách quyền “tra cứu kết quả” khỏi “gửi lại lệnh”. Một hàm mang tên reconcile nhưng tự resend khi không thấy kết quả có thể mở lại đúng đường đang bị chặn.

### 3.2. Scope phải lấy từ ngữ cảnh đáng tin

Có thể dùng tổ hợp:

~~~text
environment + businessAction + tenant + region + provider
~~~

`tenant`, danh tính actor và quyền đối tượng phải được giải quyết từ ngữ cảnh xác thực cùng dữ liệu phía server. Không để client chọn một header như `X-Emergency-Bypass: true` hoặc đổi tenant trong payload để thoát phạm vi khóa.

Job trong queue phải có liên kết tới đối tượng bền vững; worker kiểm tra lại ngữ cảnh cần thiết theo hợp đồng. Metadata cũ hoặc do client khởi tạo không tự cấp quyền thực thi.

### 3.3. Quyết định hạn chế phải có thứ tự ưu tiên rõ

Ví dụ một mô hình:

~~~text
Mọi deny có hiệu lực trên hành động và scope đều phải được tôn trọng.
Allow phục hồi cục bộ chỉ có tác dụng khi các deny bao phủ đã được điều chỉnh.
Cấu hình phát hành thông thường không được tự ghi đè khóa khẩn cấp.
~~~

Đừng chỉ so số version của hai bản ghi khác scope để chọn một bản “mới nhất”. Khóa toàn hệ thống và khóa riêng tenant có thể cùng có hiệu lực; cần đánh giá tổ hợp chính sách.

## 4. Các chế độ vận hành cần có hợp đồng riêng

Một thiết kế minh họa dùng ba chế độ:

| Chế độ | Tạo yêu cầu mới | Thực thi yêu cầu đã có | Đọc/đối soát có quyền |
|---|---|---|---|
| `NORMAL` | Theo guard thông thường | Theo guard thông thường | Theo guard thông thường |
| `ADMISSION_STOPPED` | Chặn | Có thể tiếp tục nếu được phép drain và mọi guard còn đúng | Duy trì đường đã được đánh giá an toàn |
| `FROZEN` | Chặn | Chặn lần tạo tác động mới | Duy trì đường đã được đánh giá an toàn |

`ADMISSION_STOPPED` phù hợp khi muốn giới hạn đầu vào và đã xác định công việc đang chờ vẫn an toàn. Nếu lỗ hổng nằm ở thực thi, chọn `FROZEN` cho phạm vi đó.

Không chuyển một yêu cầu đang tạm giữ thành `FAILED`, `CANCELLED` hoặc `REFUNDED` chỉ để queue hết backlog. Trạng thái phải mô tả sự thật nghiệp vụ.

### 4.1. Dừng khẩn cấp không đồng nghĩa hủy giao dịch

~~~text
REQUESTED → APPROVED → READY → SUBMITTED → SUCCEEDED
                                      ↘ UNKNOWN → đối soát

READY --bị khóa khẩn cấp--> tạm giữ, chưa gửi lệnh
SUBMITTED/UNKNOWN --------> xác minh tác động đã xảy ra
~~~

Trạng thái tạm giữ có thể là trường điều phối hoặc trạng thái riêng tùy mô hình. Nó cần giữ được trạng thái nghiệp vụ gốc, lý do giữ và điều kiện xử lý tiếp. Không đưa `SUBMITTED` trở lại `READY` khi chưa biết provider đã thực hiện hay chưa.

## 5. Bao phủ mọi đường tạo tác động

Ẩn nút trên giao diện giúp thông báo tình trạng cho người dùng. Việc cưỡng chế cần diễn ra phía server, gồm các đường có thể bỏ qua giao diện:

- REST, GraphQL hoặc API phiên bản cũ.
- Cổng quản trị, công cụ hỗ trợ và batch import.
- Worker, scheduler, retry consumer và job phục hồi.
- Webhook hoặc luồng sự kiện có thể kích hoạt thao tác mới.
- Service nội bộ gọi trực tiếp application service hoặc provider adapter.

OWASP khuyến nghị cưỡng chế authorization phía server và có kiểm soát cuối trước khi thực thi giao dịch. Với khóa khẩn cấp, có thể bổ sung guard vận hành tại ranh giới tương ứng; guard này vẫn phải đi cùng kiểm tra quyền và dữ liệu giao dịch. [OWASP: Transaction Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).

Một luồng có thể bố trí:

~~~text
API: từ chối sớm đầu vào bị khóa
  → Application service: xác thực actor, đối tượng, trạng thái và policy
  → Transaction: kiểm tra dữ liệu và ghi nhận quyết định nhất quán
  → Outbox/queue: giữ ý định bền vững
  → Worker: đánh giá khóa hiện tại trước lần thực thi mới
  → Provider adapter: bảo vệ ranh giới gửi lệnh theo hợp đồng
~~~

Lặp kiểm tra ở các ranh giới khác nhau có ích khi thời gian và trách nhiệm khác nhau. Cần dùng chung ngữ nghĩa policy để tránh API cho rằng đang frozen trong khi worker hiểu là chỉ ngừng nhận mới.

Những guard ở trên không tự tạo tính nguyên tử giữa một hệ thống cấu hình bên ngoài và database hoặc provider. Phần tiếp theo cần xác định bảo đảm thực tế của ranh giới đó.

## 6. Ranh giới hiệu lực và request đang chạy

### 6.1. Phân biệt thời điểm yêu cầu tắt với thời điểm đã chặn

~~~text
t0: người vận hành gửi yêu cầu khóa
t1: control plane ghi nhận revision R
t2: các node trong scope áp dụng R
t3: công việc đã vượt qua điểm quyết định được xử lý hoặc cô lập
t4: xác minh điều kiện containment theo hợp đồng
~~~

Đây là các mốc logic; không mặc định timestamp từ nhiều node phản ánh thứ tự chính xác. Dùng thêm revision, operation ID, trạng thái bền vững và sự kiện xác nhận.

Không báo “đã dừng hoàn toàn” chỉ từ t1. Hệ thống cần một tiêu chí quan sát được, ví dụ tất cả executor đang phục vụ scope đã áp dụng R hoặc đã bị cô lập, và không còn lần thực thi mới ngoài tập công việc đã xác định.

### 6.2. Race giữa đọc flag và tạo tác động

~~~text
Worker A đọc NORMAL ở revision 41.
Người vận hành đặt FROZEN ở revision 42.
Worker A tiếp tục gửi lệnh dựa trên quyết định cũ.
~~~

Đọc lại ngay trước gửi giúp thu hẹp cửa sổ nhưng vẫn có khoảng đua. Một yêu cầu “không có tác động nào sau khi control plane nhận lệnh” có thể vượt khả năng của kiến trúc cấu hình bất đồng bộ.

Cần chọn và công bố bảo đảm:

| Bảo đảm mong muốn | Hướng thiết kế cần xem xét |
|---|---|
| Các node ngừng khởi tạo trong một độ trễ vận hành có giới hạn | Phân phối cấu hình, đo độ mới, xác nhận áp dụng và cô lập node cũ |
| Quyết định chấp nhận không vượt qua khóa trên cùng database | Guard cùng ranh giới transaction với cơ chế khóa hoặc tuần tự hóa đã kiểm chứng |
| Executor cũ không tiếp tục ghi sau khi mất quyền | Cơ chế fencing/version được nơi tạo tác động kiểm tra |
| Chặn gửi tới provider ngoài | Điểm egress có cưỡng chế, hoặc cơ chế tương ứng do provider hỗ trợ |

Một lần đọc `enabled` trong transaction thông thường không tự tuần tự hóa với cập nhật policy. Với database, phải kiểm tra isolation, lock, câu lệnh cập nhật và thứ tự cạnh tranh thực tế. Với provider, transaction nội bộ không thể thu hồi một request đã được bên ngoài chấp nhận.

### 6.3. Thao tác đã đi ra ngoài

Phân loại theo bằng chứng:

- Chưa gửi: có thể giữ lại trước lần thực thi mới.
- Đã gửi và xác nhận thành công: ghi nhận đúng, không gửi lại.
- Đã gửi và xác nhận thất bại không tạo tác động: xử lý theo state machine.
- Timeout hoặc mất kết nối, kết quả chưa rõ: đưa vào đường đối soát.

Không biến HTTP timeout thành kết luận “chưa hoàn tiền”. Hủy task cục bộ cũng không chứng minh provider đã hủy tác động.

## 7. Control plane và data plane khi hệ thống đang gặp sự cố

**Control plane** là đường thay đổi chính sách. **Data plane** là nơi thực thi policy cho từng thao tác. Chúng có yêu cầu khác nhau:

| Thành phần | Điều cần chuẩn bị |
|---|---|
| Control plane | Quyền vận hành, xác nhận scope, version, audit và cách truy cập khi đường chính lỗi |
| Phân phối | Khả năng áp dụng revision, độ trễ, reconnect, restart và chống cập nhật lùi |
| Data plane | Quyết định cục bộ/đồng bộ phù hợp, giới hạn cache, fallback và telemetry |
| Xác minh | Quan sát node thực thi và tác động nghiệp vụ, không chỉ trạng thái trang quản trị |

Không để công tắc chỉ có thể thay đổi qua chính API đang bị đóng băng. Đồng thời, đường quản trị dự phòng cần quyền hẹp, được bảo vệ và đã diễn tập; một endpoint bỏ qua authentication tạo thêm đường tấn công.

### 7.1. Cấu hình cần đủ ngữ nghĩa

Ví dụ dưới đây là hợp đồng dữ liệu minh họa, không phải cấu hình của một sản phẩm cụ thể:

~~~json
{
  "policyKey": "automatic-refund",
  "environment": "production",
  "scope": { "tenantId": "tenant-T", "provider": "provider-P" },
  "mode": "FROZEN",
  "revision": 42,
  "incidentId": "INC-EXAMPLE-17",
  "reasonCode": "DUPLICATE_EXECUTION_RISK",
  "reviewRequired": true
}
~~~

Revision hỗ trợ nhận biết cấu hình cũ trong một miền thứ tự đã xác định. Nó không tự bảo đảm chống phát lại, xác thực nguồn hoặc tính nguyên tử với tác động. Cần thiết kế việc lưu revision qua restart và cách xử lý khi nguồn cấu hình bị rollback.

Không đưa token, thông tin thanh toán đầy đủ hoặc mô tả chứa dữ liệu cá nhân vào reason công khai. Người dùng cần thông điệp tình trạng phù hợp; người vận hành cần liên kết tới hồ sơ sự cố có phân quyền.

### 7.2. Mất kết nối và cache cũ

Phải phân biệt:

~~~text
Đọc được NORMAL mới và đáng tin.
Đọc được FROZEN mới và đáng tin.
Chỉ còn NORMAL cũ ngoài giới hạn độ mới.
Không có cấu hình, cấu hình sai schema hoặc không xác minh được nguồn.
~~~

Đối với việc tạo tác động nhạy cảm trong ví dụ, trạng thái không xác định phải chặn hoặc tạm giữ theo hợp đồng. Giữ mãi NORMAL cũ khiến node mất kết nối tiếp tục tạo tác động trong lúc các node khác đã khóa.

Giới hạn độ mới cần dựa trên nguồn đo phù hợp; đồng hồ bị lùi không được làm cache trông mới mãi. Khi restart, không tái sử dụng tick cục bộ từ tiến trình trước. Nếu không xác định được tuổi mẫu, coi chất lượng cấu hình là chưa đủ cho thao tác yêu cầu mẫu mới.

### 7.3. Fallback phụ thuộc ý nghĩa của flag

Một flag `refund.execution.allowed` có thể cần default `false` cho đường tạo tác động. Với tên ngược `refund.execution.blocked`, default an toàn tương ứng lại là `true`.

OpenFeature quy định các lần đánh giá flag khi thực thi bất thường trả về default do ứng dụng cung cấp; vì vậy default phải được chọn theo ý nghĩa nghiệp vụ. Một giá trị boolean nhận được không tự chứng minh provider đã hoạt động hoặc cấu hình đủ mới. [OpenFeature: Flag Evaluation API](https://openfeature.dev/specification/sections/flag-evaluation/).

Adapter cần chuyển lỗi, thiếu dữ liệu, schema lạ và tình trạng stale thành kết quả có chủ đích. Những thao tác đọc hoặc đối soát được duy trì cũng phải qua quyền và guard của chúng; không tạo một nhánh bypass tổng quát tên “safe mode”.

## 8. Ví dụ Java: quyết định policy có kết quả tường minh

Ví dụ Java 17 dưới đây mô hình hóa policy cho một scope đã được adapter giải quyết. Nó không gọi SDK feature flag cụ thể và không thực hiện transaction hoặc provider request.

~~~java
import java.util.Objects;

final class EmergencyPolicy {
    enum Action {
        CREATE_REFUND,
        EXECUTE_REFUND,
        READ_REFUND_STATUS,
        RECONCILE_REFUND
    }

    enum Mode {
        NORMAL,
        ADMISSION_STOPPED,
        FROZEN
    }

    enum Quality {
        CURRENT,
        STALE,
        UNAVAILABLE,
        INVALID
    }

    enum Outcome {
        PERMIT,
        BLOCKED,
        POLICY_UNCERTAIN
    }

    record Snapshot(Mode mode, long revision, Quality quality) {
        Snapshot {
            Objects.requireNonNull(mode);
            Objects.requireNonNull(quality);
            if (revision < 0) {
                throw new IllegalArgumentException("negative revision");
            }
        }
    }

    record Decision(Outcome outcome, long revision, String reason) {}

    Decision evaluate(Action action, Snapshot snapshot) {
        Objects.requireNonNull(action);
        long revision = snapshot == null ? -1 : snapshot.revision();

        if (action == Action.READ_REFUND_STATUS
                || action == Action.RECONCILE_REFUND) {
            return new Decision(
                    Outcome.PERMIT, revision, "RECOVERY_PATH_NOT_BLOCKED");
        }

        if (snapshot == null || snapshot.quality() != Quality.CURRENT) {
            return new Decision(
                    Outcome.POLICY_UNCERTAIN,
                    revision,
                    "CURRENT_POLICY_REQUIRED");
        }

        if (snapshot.mode() == Mode.FROZEN) {
            return new Decision(
                    Outcome.BLOCKED, revision, "EXECUTION_FROZEN");
        }

        if (snapshot.mode() == Mode.ADMISSION_STOPPED
                && action == Action.CREATE_REFUND) {
            return new Decision(
                    Outcome.BLOCKED, revision, "ADMISSION_STOPPED");
        }

        return new Decision(Outcome.PERMIT, revision, "POLICY_PERMITS");
    }
}
~~~

### 8.1. Điều kiện để dùng ví dụ đúng

- `Snapshot` đã được giải quyết cho đúng môi trường, hành động và scope từ ngữ cảnh đáng tin.
- Adapter chịu trách nhiệm xác minh nguồn, schema, revision và độ mới; không gán `CURRENT` chỉ vì đọc được JSON.
- Khi adapter không cung cấp được snapshot, truyền kết quả thiếu dữ liệu hoặc ánh xạ thành nhánh `POLICY_UNCERTAIN`; không tạo một snapshot NORMAL giả.
- `PERMIT` chỉ có nghĩa guard khẩn cấp không chặn. Application service vẫn kiểm tra authorization, approval, số tiền, trạng thái và version.
- `RECONCILE_REFUND` trong hợp đồng này chỉ tra cứu, tiếp nhận bằng chứng và cập nhật kết quả hợp lệ; nếu cần gửi một lệnh mới, phải đánh giá `EXECUTE_REFUND`.

Giá trị revision `-1` biểu thị không có snapshot trong kết quả minh họa. Đây là metadata giải thích quyết định, không phải quyền bỏ qua kiểm tra.

### 8.2. Những bảo đảm mã chưa cung cấp

Đọc một snapshot không ngăn policy thay đổi sau đó. Lớp trên chưa thực hiện kiểm soát tranh chấp với việc khóa, không chứng minh mọi node đã nhận revision mới và không bảo vệ ranh giới provider. Cần kiểm thử các lớp thực thi tương ứng trước khi công bố một ranh giới containment.

Không giữ snapshot lấy lúc nhận HTTP request để dùng mãi khi job được chạy nhiều phút sau. Ngược lại, cũng không tự áp policy mới để xóa kết quả nghiệp vụ đã hoàn tất trong quá khứ.

## 9. Ghép guard với transaction và idempotency

Một luồng application service có thể được mô tả bằng mã giả:

~~~text
Xác thực caller và giải quyết tenant từ ngữ cảnh server.
Xác minh quyền truy cập đối tượng và quyền đọc kết quả của command.
Tra cứu idempotency theo scope và fingerprint của command.

Nếu đã có kết quả hoàn tất, cùng payload và caller có quyền:
    Trả kết quả đã lưu; không tạo một thao tác mới.

Nếu key xung đột payload hoặc thao tác đang có kết quả chưa rõ:
    Xử lý theo hợp đồng riêng; không coi là yêu cầu mới.

Với thao tác mới:
    Đánh giá guard khẩn cấp cho CREATE_REFUND.
    Trong ranh giới nhất quán đã thiết kế:
        Kiểm tra state, số tiền còn được hoàn, approval và version.
        Áp guard có thẩm quyền tại điểm quyết định theo hợp đồng.
        Ghi ý định, liên kết idempotency và outbox nhất quán.

Worker trước lần gửi mới:
    Giải quyết lại scope và guard EXECUTE_REFUND.
    Kiểm tra quyền thực thi, state và chống thực hiện trùng.
    Giữ job nếu blocked hoặc policy chưa xác định.
    Chỉ gửi khi mọi điều kiện và cơ chế tranh chấp cần thiết đều đúng.
~~~

Các bước trên thể hiện trách nhiệm, không phải một thuật toán transaction dùng được nguyên xi. Việc claim idempotency key, chống hai worker cùng gửi và cạnh tranh với khóa khẩn cấp phải được hiện thực bằng ràng buộc dữ liệu cùng cơ chế đồng thời phù hợp.

### 9.1. Retry trong lúc frozen

| Tình trạng thao tác | Hành vi cần định nghĩa |
|---|---|
| Key chưa từng được dùng | Tạm chặn/tạm giữ thao tác mới theo policy |
| Cùng key, cùng payload, đã thành công | Có thể trả kết quả đã lưu sau khi xác minh quyền; không gửi lại |
| Cùng key nhưng payload khác | Báo xung đột; không gắn dữ liệu mới vào kết quả cũ |
| Đang xử lý hoặc chưa rõ provider đã làm gì | Trả trạng thái phù hợp hoặc đối soát; không khởi tạo lần gửi mới tùy tiện |
| Key hết thời gian lưu nhưng đối tượng đã hoàn tất | Bất biến trên đối tượng vẫn phải ngăn tác động trùng |

Không xóa bản ghi idempotency để người dùng “thử lại cho sạch”. Một sự cố kéo dài có thể làm cửa sổ lưu key trở nên quan trọng; cần xét retention và ràng buộc nghiệp vụ bền vững.

### 9.2. Approval và số tiền không được đóng băng sai nghĩa

Khi mở lại, một yêu cầu đã chờ lâu có thể hết hạn phê duyệt, hết hạn báo giá hoặc thay đổi phần giá trị còn được hoàn. Chờ trong queue không tự kéo dài hiệu lực.

Nếu nội dung trọng yếu thay đổi, áp quy tắc phê duyệt lại theo nghiệp vụ. Không dùng emergency mode để bỏ qua approval vì muốn xử lý backlog nhanh.

## 10. Queue, outbox và công việc đang chờ

### 10.1. Tạm giữ phải khác lỗi kỹ thuật để retry

Nếu mọi job bị frozen đều lập tức throw exception rồi requeue, hệ thống có thể tạo retry storm, tăng tải và che mất sự cố gốc.

Cần thiết kế cách giữ công việc:

- Dừng hoặc giảm consumer cho đúng scope khi kiến trúc hỗ trợ.
- Lưu trạng thái tạm giữ và lý do trong cơ chế điều phối bền vững.
- Dùng lịch thử lại có giới hạn, phù hợp broker và thời gian phục hồi.
- Giữ liên kết operation ID, idempotency key và trạng thái nghiệp vụ.

Không ACK rồi bỏ mất message nếu chưa có một bản ghi bền vững bảo đảm công việc được tiếp tục. Cũng không giữ lock hoặc transaction database suốt thời gian chờ người vận hành mở lại.

### 10.2. Phân biệt command với event của việc đã xảy ra

~~~text
Command: "hãy thực hiện hoàn tiền"
  → có thể cần tạm giữ trước lần thực thi mới.

Event: "provider đã xác nhận hoàn tiền thành công"
  → cần ghi nhận đúng sự thật và chống xử lý lặp.
~~~

Chặn mọi event có chữ “refund” có thể làm ledger và trạng thái đơn mất nhất quán. Một event cũng có thể kích hoạt tác động tiếp theo; consumer phải nhận diện và áp guard cho tác động mới đó.

Webhook tiếp tục được xử lý chỉ khi xác thực nguồn, kiểm tra replay và đối chiếu operation theo thiết kế. Emergency mode không làm một callback bất kỳ trở thành bằng chứng đáng tin.

### 10.3. Không xóa backlog như một cách khoanh vùng mặc định

Backlog có thể chứa yêu cầu hợp lệ, lệnh đã gửi nhưng chưa rõ kết quả và dữ liệu cần điều tra. Hãy phân loại trước:

| Nhóm công việc | Hướng xử lý |
|---|---|
| Chưa thực thi, còn hợp lệ | Giữ để tái kiểm tra khi phục hồi |
| Hết hạn hoặc không còn được phê duyệt | Kết thúc theo state machine và lưu lý do |
| Có dấu hiệu lạm dụng | Cô lập và giữ bằng chứng theo quy trình |
| Đã gửi, kết quả chưa rõ | Đối soát trước mọi quyết định gửi lại |
| Đã thành công nhưng event bị chậm | Hoàn tất ghi nhận, không thực hiện lại |

## 11. Bảo vệ quyền điều khiển công tắc

Cơ chế có thể dừng một nghiệp vụ quan trọng cũng có thể bị lạm dụng để gây gián đoạn hoặc để mở lại đường tấn công.

### 11.1. Quyền phải được giới hạn theo hành động và scope

Phân biệt quyền:

~~~text
Xem trạng thái và lịch sử policy.
Kích hoạt hạn chế cho một phạm vi được giao.
Mở rộng phạm vi hạn chế.
Thu hẹp hoặc gỡ hạn chế.
Thay đổi chính cơ chế cưỡng chế và fallback.
~~~

Có thể thiết kế quyền kích hoạt khẩn cấp nhanh hơn quyền mở lại, theo chính sách đã phê duyệt trước. Nếu áp dụng cơ chế hai người duyệt, cần có đường xử lý tình huống khẩn cấp rõ ràng để không trì hoãn containment vô thời hạn. Đây là quyết định vận hành của tổ chức, không phải yêu cầu mọi hệ thống đều phải có hai người duyệt.

Đường break-glass cần danh tính riêng có thể truy vết, thời hạn truy cập, phạm vi quyền và cơ chế rà soát. Tránh tài khoản quản trị dùng chung không xác định được người thực hiện.

### 11.2. Cập nhật cạnh tranh và thay đổi ngoài ý muốn

Nếu hai người vận hành cùng sửa policy, một thay đổi dựa trên dữ liệu cũ có thể vô tình mở lại scope vừa được khóa. Dùng cơ chế kiểm tra revision kỳ vọng hoặc điều kiện tương đương; trả xung đột thay vì ghi đè lặng lẽ.

Thao tác điều khiển cũng cần request ID hoặc cách chống thực hiện lặp phù hợp. Mất phản hồi sau cập nhật không có nghĩa cập nhật chưa xảy ra; người vận hành cần đọc trạng thái có thẩm quyền trước khi tiếp tục.

Một bản deploy hoặc lần đồng bộ cấu hình định kỳ không được tự xóa khóa đang hoạt động. Kiểm thử riêng việc khởi động node mới, thay version ứng dụng và phục hồi control plane từ backup.

### 11.3. Review deadline không phải tự động bật lại

Một mốc review giúp nhắc người chịu trách nhiệm đánh giá tình trạng. Nếu sự cố chưa được kiểm soát, đến mốc đó không được tự gỡ khóa chỉ để cấu hình khỏi tồn tại lâu.

Nếu hệ thống dùng TTL cho override, phải định nghĩa rõ trạng thái sau TTL. Với hạn chế bảo mật đang bảo vệ một bất biến, fallback về NORMAL có thể tái mở sự cố. Thời hạn cũng không thay thế điều kiện phục hồi và bằng chứng cần thiết.

## 12. Runbook kích hoạt và xác minh

Một runbook phải đủ cụ thể để người trực ca dùng khi thời gian và khả năng suy nghĩ đều bị giới hạn. Các bước sau là khung thực hành, cần điền tên hệ thống và quyền thực tế trước khi áp dụng.

### Bước 1: Xác định hành vi gây hại và chỉ huy xử lý

Ghi incident ID, người điều phối, tín hiệu phát hiện và bất biến đang có nguy cơ bị vi phạm. Không chờ biết toàn bộ nguyên nhân gốc mới khoanh vùng nếu bằng chứng đã đáp ứng tiêu chí kích hoạt đã chuẩn bị.

### Bước 2: Chọn scope và mode

Xác định môi trường, tenant, provider, vùng và hành động cần hạn chế. Kiểm tra scope có bao phủ đường thực thi đang bị lạm dụng không. Nếu chưa có cơ sở cho phép drain, không chọn chế độ tiếp tục thực thi chỉ vì backlog lớn.

### Bước 3: Ghi chính sách qua đường điều khiển được bảo vệ

Gửi thay đổi kèm lý do, incident ID và revision kỳ vọng. Lưu kết quả cập nhật và định danh người thực hiện. Khi phản hồi timeout, xác minh trạng thái thực tế trước khi tạo thêm thay đổi.

### Bước 4: Kiểm tra mức áp dụng

Theo dõi node API, worker và điểm egress thuộc scope. Xác định node mất kết nối, node mới khởi động hoặc node chưa áp dụng revision mục tiêu. Nếu phải cô lập node, xét cả khả năng nó vẫn còn gửi request ra ngoài; chỉ bỏ node khỏi load balancer không dừng worker của node đó.

### Bước 5: Xác minh hành vi nghiệp vụ

Dùng probe hoặc tài khoản kiểm thử được chuẩn bị, không tạo hoàn tiền thật ngoài ý muốn. Kiểm tra thao tác mới bị chặn và đường đọc/đối soát cần duy trì vẫn hoạt động đúng quyền.

Quan sát dữ liệu bền vững và nơi gửi lệnh để đối chiếu. Nếu chỉ có bằng chứng policy đã áp dụng, báo đúng mức đó; tiếp tục kiểm tra ranh giới tác động trước khi tuyên bố containment.

### Bước 6: Phân loại công việc đang chạy và giữ bằng chứng

Lập tập operation đã gửi, đang giữ, chưa rõ kết quả và đã hoàn tất. Giữ lịch sử cấu hình, log quyết định, trace và liên kết tới provider. Tránh sửa trực tiếp dữ liệu làm mất dấu trạng thái trước sự cố.

### Bước 7: Duy trì hạn chế và chuẩn bị phục hồi

Giao người chịu trách nhiệm review, tiêu chí tiếp tục khóa và điều kiện mở lại. Bản sửa lỗi, đối soát và kế hoạch backlog cần đi cùng nhau. Thông điệp cho người dùng nên mô tả tình trạng và cách xem kết quả, tránh thúc đẩy họ tạo nhiều yêu cầu thay thế.

## 13. Bằng chứng nào cho thấy đã chặn thành công?

Cần kết hợp ít nhất ba góc nhìn:

| Góc nhìn | Bằng chứng | Giới hạn |
|---|---|---|
| Ý định điều khiển | Policy được ghi, revision, actor, scope, reason | Chưa chứng minh executor đã áp dụng |
| Quyết định thực thi | Revision đang dùng, chất lượng snapshot, số lần chặn theo hành động | Chưa chứng minh đường ngoài guard không tồn tại |
| Tác động nghiệp vụ | Lần gửi lệnh mới, operation bền vững, kết quả provider và đối soát | Cần phân biệt tác động khởi tạo trước/sau ranh giới |

Ví dụ các chỉ số nên có:

- Số executor trong scope đã áp dụng revision mục tiêu và danh sách ngoại lệ.
- Độ trễ từ cập nhật đến áp dụng và thời gian tới containment theo hợp đồng.
- Số quyết định blocked, uncertain và permit theo hành động/phạm vi kiểm soát được.
- Số job tạm giữ, tuổi job lâu nhất và dung lượng lưu trữ liên quan.
- Số thao tác có kết quả chưa rõ, số lần gửi mới và số bất biến bị vi phạm.
- Tình trạng hoạt động của đường đọc và đối soát cần duy trì.

Không đưa operation ID hoặc user ID có số lượng lớn vào nhãn metric đại trà; dùng log/trace có phân quyền để truy tìm từng trường hợp. Không ghi bí mật hoặc dữ liệu thanh toán đầy đủ vào log quyết định.

Một record audit có thể chứa:

~~~text
incidentId, changeRequestId, operatorIdentity
policyKey, environment, scope, oldMode, newMode
expectedRevision, committedRevision
decisionPoint, appliedRevision, policyQuality
operationId, outcome, reasonCode
evidenceReference, reviewOwner
~~~

Thiết kế audit cần xét khi nơi lưu audit bị lỗi: thay đổi nào bị từ chối, thay đổi khẩn cấp nào có thể ghi qua đường bền vững dự phòng và cách đối chiếu sau đó. Không dùng lỗi audit như một lý do mặc định để bỏ qua toàn bộ kiểm soát hoặc để vô hiệu hóa cơ chế containment.

Không kết luận an toàn chỉ vì số request thành công giảm về 0. Có thể traffic đã giảm, telemetry bị mất hoặc worker đã chuyển sang một đường gọi chưa được quan sát.

## 14. Mở lại có kiểm soát

Vô hiệu hóa khẩn cấp tạo thời gian để xử lý sự cố. Khôi phục cần xác nhận hệ thống đủ an toàn để tiếp tục, bao gồm dữ liệu và công việc tồn đọng.

### 14.1. Điều kiện trước khi mở

- Đã xác định và sửa đường vi phạm bất biến, có bằng chứng kiểm thử phù hợp.
- Những đường thực thi tương đương và phiên bản cũ đã được xét.
- Operation có kết quả chưa rõ được phân loại và có kế hoạch đối soát.
- Guard về quyền, state, approval, số tiền và chống trùng vẫn hoạt động.
- Node đang phục vụ đã có phiên bản code/policy cần thiết.
- Có người quyết định, người theo dõi và tiêu chí quay lại khóa.

Không dùng “không còn thấy cảnh báo” làm điều kiện duy nhất nếu tính năng vẫn đang bị chặn và chưa có traffic thử an toàn.

### 14.2. Mở theo phạm vi đã xác minh

Ví dụ lộ trình:

~~~text
FROZEN toàn bộ phạm vi bị ảnh hưởng
→ cho phép một scope kiểm thử có kiểm soát
→ mở nhóm nhỏ cùng giới hạn tải và quan sát bất biến
→ mở rộng từng phạm vi
→ trở lại NORMAL khi đủ điều kiện
~~~

Scope phục hồi phải dựa trên dữ liệu đáng tin; client không tự khai mình là canary. Cần điều chỉnh các deny bao phủ theo đúng quy tắc ưu tiên, tránh một allow thử nghiệm vô tình gỡ khóa toàn hệ thống.

### 14.3. Giải phóng backlog bằng tái kiểm tra

Trước mỗi tác động mới, kiểm tra lại điều kiện còn có hiệu lực. Phân bổ công việc với tốc độ phù hợp để không dồn một lượng lớn yêu cầu vào provider hoặc tạo đua dữ liệu mới.

Không gửi lại tất cả thao tác UNKNOWN. Không tái dùng approval cho dữ liệu đã thay đổi. Không đặt trạng thái thành công bằng batch chỉ để số backlog về 0.

Nếu bất biến bị vi phạm trở lại, cơ chế đóng băng phải tiếp tục dùng được. Giữ lịch sử các lần khóa/mở thay vì xóa bằng chứng của lần trước.

## 15. Kiểm thử cơ chế trước khi có sự cố

Kiểm thử cần xét cả quyết định policy lẫn tác động cuối. Unit test gate có thể chứng minh bảng mode/action; kiểm thử tích hợp mới kiểm tra được đường thực thi thật.

| Kịch bản | Kỳ vọng cần kiểm tra |
|---|---|
| API bị frozen, gọi trực tiếp bằng HTTP | Không có ý định hoặc tác động mới trái hợp đồng |
| Bỏ qua UI và gọi endpoint cũ/admin/batch | Guard vẫn được cưỡng chế hoặc đường đó đã được cô lập |
| Job nhận trước khóa nhưng chạy sau khóa | Worker dùng policy tại điểm thực thi đã quy định |
| Một node mất kết nối và giữ NORMAL cũ | Hết độ mới thì chặn/tạm giữ hoặc node bị cô lập theo thiết kế |
| Restart node trong khi scope đang frozen | Không có cửa sổ mặc định NORMAL gây tác động |
| Cấu hình thiếu, sai schema hoặc không đủ tin cậy | Không biến lỗi cấu hình thành quyền thực thi mới |
| Hai người vận hành sửa cùng revision | Xung đột được phát hiện; không ghi đè khóa bằng dữ liệu cũ |
| NORMAL cũ đến sau FROZEN mới | Không tự hạ policy trong cùng miền revision |
| Khóa xuất hiện giữa lần kiểm tra và gửi | Hành vi đúng bảo đảm đã công bố; không tuyên bố mạnh hơn bằng chứng |
| Provider timeout sau khi nhận lệnh | Không gửi lại tùy tiện; chuyển đường kết quả chưa rõ |
| Retry key đã hoàn tất trong lúc frozen | Cùng kết quả, cùng quyền, không có tác động mới |
| Client đổi tenant hoặc khai bypass | Không thoát khóa hoặc vượt quyền đối tượng |
| Job bị giữ nhiều giờ | Không retry storm, không mất job, không giữ transaction dài |
| Deploy/restore cấu hình khi khóa đang bật | Không vô tình gỡ hạn chế đang có hiệu lực |
| Đến review deadline nhưng lỗi chưa sửa | Không tự trở lại NORMAL |
| Mở lại sau khi approval hết hạn | Yêu cầu được tái kiểm tra, không dùng phê duyệt quá hạn |
| Event thành công đến muộn | Ghi nhận đúng một tác động đã xảy ra, không kích hoạt lệnh mới trái policy |

### 15.1. Điều khiển race bằng barrier

Một test xác định có thể dùng latch/barrier tại ranh giới đã chọn:

~~~text
1. Cho worker tới ngay trước ranh giới quyết định/gửi cần kiểm tra.
2. Giữ worker tại barrier do test điều khiển.
3. Áp revision FROZEN và chờ bằng chứng áp dụng cần thiết.
4. Cho worker tiếp tục.
5. Kiểm tra dữ liệu, số lần gọi provider test double và outbox.
6. Retry cùng operation; kiểm tra không phát sinh tác động mới.
~~~

Vị trí barrier quyết định test chứng minh gì. Test đứng trước lần đọc policy chỉ chứng minh lần đọc mới thấy khóa. Muốn kiểm tra request đã có permit cũ, đặt barrier sau lần đọc đó và đánh giá cơ chế cưỡng chế tại ranh giới tiếp theo.

Nếu hợp đồng cho phép một tập request đã vượt qua điểm quyết định tiếp tục, test cần nhận diện tập đó và đối soát chúng. Không viết assert “không tác động sau t0” cho một kiến trúc chỉ bảo đảm hiệu lực sau quá trình lan truyền.

### 15.2. Tiêu chí pass phải gắn với bất biến

Với fixture không có lệnh nào gửi trước khóa, frozen có thể yêu cầu số lệnh mới bằng 0, tổng tiền hoàn không đổi và không có event thành công giả. Với fixture có một lệnh đã được provider chấp nhận, cần ghi nhận kết quả thật đúng một lần và không gửi lệnh thứ hai.

Đồng thời kiểm tra tenant ngoài scope vẫn được phục vụ đúng quyền theo chính sách đã chọn. Containment thành công phải đi cùng khả năng hiểu và quản lý phần ảnh hưởng do việc hạn chế gây ra.

## 16. Tình huống xuyên suốt: hoàn tiền trùng

Đội vận hành phát hiện hai operation khác nhau có thể tạo hoàn tiền cho cùng một yêu cầu do lỗi tranh chấp ở worker. Hệ thống có API tạo yêu cầu, outbox và nhiều consumer.

| Mốc logic | Hành động | Bằng chứng cần có |
|---|---|---|
| Phát hiện | Liên kết các lần hoàn với cùng yêu cầu, xác nhận dấu hiệu vượt bất biến | Operation ID, trạng thái lưu, kết quả provider |
| Kích hoạt | Đặt `FROZEN` cho hoàn tiền tự động trong scope bị ảnh hưởng | Actor, incident ID, scope, revision 42 |
| Lan truyền | Kiểm tra mọi executor; cô lập một consumer chưa nhận policy | Revision đã áp dụng và bằng chứng không còn quyền gửi |
| Xác minh | Probe an toàn và quan sát lần gửi mới | Bị chặn đúng hành động, không chỉ ẩn UI |
| Đối soát | Phân loại lệnh đã gửi, UNKNOWN và job chưa gửi | Tập operation được truy vết tới kết quả thật |
| Sửa và kiểm thử | Khắc phục cạnh tranh cùng ràng buộc chống trùng | Test đồng thời và regression cho retry |
| Phục hồi | Mở scope nhỏ, tái kiểm tra backlog, tăng dần lưu lượng | Bất biến giữ đúng và không có tác động trùng |

Nếu consumer chưa nhận revision chỉ bị bỏ khỏi load balancer nhưng vẫn đọc queue và gọi provider, containment chưa đủ. Nếu callback bị tắt cùng toàn bộ route hoàn tiền, đội vận hành có thể mất tín hiệu để biết lệnh trước khóa đã thành công hay chưa.

Hai quan sát này cho thấy cần kiểm tra ranh giới gửi mới và đường ghi nhận sự thật đã xảy ra một cách riêng rẽ trong cùng runbook.

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ tắt nút giao diện | API và worker tiếp tục hoạt động | Cưỡng chế phía server tại đường nghiệp vụ |
| Gọi mọi chế độ là OFF | Người vận hành không biết queue cũ có chạy không | Đặt mode và hợp đồng theo hành động |
| Dùng default NORMAL khi provider flag lỗi | Mất cấu hình làm mở lại tác động nhạy cảm | Ánh xạ trạng thái không xác định theo rủi ro |
| Đọc flag một lần khi nhận request | Job dùng permit cũ khi thực thi muộn | Kiểm tra tại các điểm quyết định có ý nghĩa |
| Cho rằng đọc lại là nguyên tử với lệnh ngoài | Còn race sau lần đọc | Thiết kế và công bố ranh giới bảo đảm thực tế |
| Retry mọi lỗi frozen ngay lập tức | Tạo bão retry và quá tải | Giữ job bền vững với lịch xử lý phù hợp |
| Chặn cả ghi nhận kết quả đã xảy ra | Mất nhất quán và khó đối soát | Duy trì đường phục hồi được xác thực |
| Xóa key hoặc reset UNKNOWN để gửi lại | Tạo tác động trùng | Đối soát và giữ state/idempotency |
| Cho client chọn scope hoặc bypass | Thoát khóa và vượt quyền | Giải quyết ngữ cảnh phía server |
| Tự bật lại sau một thời gian | Khôi phục đường khai thác khi chưa sửa | Tách review deadline và điều kiện phục hồi |
| Thấy dashboard OFF thì tuyên bố containment | Node cũ hoặc egress vẫn tạo tác động | Kết hợp cấu hình, executor và bằng chứng nghiệp vụ |
| Mở toàn bộ backlog cùng lúc | Quá tải, dùng approval cũ và tăng tranh chấp | Mở từng phạm vi, giới hạn tốc độ và tái kiểm tra |

## 18. Bài tập thực hành

### Bài tập 1: Viết hợp đồng dừng

Chọn tính năng đổi voucher hoặc hoàn tiền. Liệt kê hành động, scope, mode và đường vẫn cần hoạt động. Phân biệt mục tiêu ngừng nhận mới với mục tiêu ngừng tạo tác động.

### Bài tập 2: Vẽ mọi đường thực thi

Vẽ API, admin tool, queue, worker và provider. Đánh dấu nơi lấy policy, nơi kiểm tra quyền và nơi tạo tác động không thể thu hồi bằng rollback nội bộ. Tìm một đường có thể bỏ qua guard ở API.

### Bài tập 3: Cấu hình không đáng tin

Mô phỏng cache NORMAL cũ, mất provider, sai schema, revision đến sai thứ tự và restart khi đang frozen. Định nghĩa expected cho thao tác tạo mới, thực thi và đối soát.

### Bài tập 4: Race và kết quả chưa rõ

Dừng worker sau khi đã đọc permit, kích hoạt khóa rồi cho tiếp tục. Xác định kiến trúc hiện tại chứng minh được điều gì. Bổ sung ca provider đã nhận lệnh nhưng phản hồi timeout; giải thích vì sao retry bằng một key mới là nguy hiểm.

### Bài tập 5: Lập kế hoạch mở lại

Có 1.000 job chưa gửi, 20 operation UNKNOWN và một nhóm approval đã hết hạn. Lập cách phân loại, bằng chứng cần thu thập, thứ tự giải phóng và điều kiện tái khóa. Các con số là fixture bài tập, không phải ngưỡng vận hành khuyến nghị.

## 19. Tự kiểm tra thiết kế

- Có thể nêu chính xác hành động và phạm vi bị khóa.
- Mỗi mode quy định rõ cách xử lý đầu vào mới, job cũ và kết quả đã phát sinh.
- Client không điều khiển scope tin cậy hoặc tự cấp quyền bypass.
- Mọi đường tạo tác động đều có guard hoặc biện pháp cô lập đã kiểm chứng.
- Fallback, độ mới cấu hình, restart và cập nhật lùi đã có hợp đồng.
- Ranh giới containment phù hợp cơ chế nhất quán thực tế của hệ thống.
- Request đang chạy và lệnh có kết quả chưa rõ được truy vết, đối soát.
- Idempotency, approval, quyền đối tượng và state machine vẫn được duy trì.
- Người điều khiển công tắc có quyền phù hợp và lịch sử có thể truy cứu.
- Có test kích hoạt, đường suy giảm, mở lại và tái khóa.
- Phục hồi kiểm tra lại backlog thay vì gửi lại toàn bộ.
- Kết luận hiệu lực dựa trên tác động nghiệp vụ cùng bằng chứng áp dụng policy.

Một cơ chế vô hiệu hóa khẩn cấp hữu ích khi đội ứng cứu có thể dùng nó để chặn đúng đường gây hại, giải thích phần công việc còn đang xử lý và khôi phục mà không phá các bất biến nghiệp vụ. Công tắc là điểm bắt đầu; hợp đồng thực thi và bằng chứng containment quyết định giá trị bảo vệ của nó.
