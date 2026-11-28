# Tính lặp lại an toàn khi chạy lại một script

Script tự động hóa thường bị chạy lại vì tiến trình bị ngắt, mạng mất kết nối, người vận hành chưa nhận được kết quả hoặc pipeline cần thử lại sau một lỗi tạm thời. Nếu mỗi lần chạy đều tạo mới tài nguyên, cộng thêm giá trị hoặc gửi lại một thông báo, việc chạy lại có thể gây trùng dữ liệu và side effect ngoài ý muốn.

Một script an toàn khi chạy lại phải đưa hệ thống về trạng thái mong muốn mà không tạo thêm tác động ngoài dự kiến khi cùng một yêu cầu được thực hiện nhiều lần. Thuộc tính này được gọi là **idempotency** (tính lũy đẳng). Spring Shell cung cấp cách đọc và thực thi command từ file; việc bảo đảm chạy lại an toàn thuộc về thiết kế của từng command, service và hệ thống đích.

## Script Spring Shell được thực thi như thế nào?

Trong Spring Shell 3.3.x, command tích hợp `script` nhận một file cục bộ và phát lại các command trong file lần lượt, từng command một. Nội dung file tuân theo cách đọc dòng lệnh của shell: dòng bắt đầu bằng `//` là comment và dòng kết thúc bằng `\` tiếp tục sang dòng kế tiếp.

```text
// scripts/provision-staging.shell
connect
login
environment-use staging
resource-ensure --name customer-api \
                --region ap-southeast-1
deployment-ensure --service customer-api --version 2.7.1
```

Có thể chạy script bằng built-in `script` command trong phiên shell. Spring Shell 3.x cũng có `ScriptShellRunner`, nhận đối số tiến trình bắt đầu bằng `@` như `@scripts/provision-staging.shell`; runner này có ưu tiên cao hơn runner non-interactive và interactive.

```text
java -jar customer-cli.jar @scripts/provision-staging.shell
```

Hai cách gọi trên giúp phát lại các command theo thứ tự trong file. Chúng không tự tạo ra cam kết rằng mỗi command chỉ chạy đúng một lần, không tự cấp transaction bao trùm toàn bộ script và không tự hoàn tác các command đã thành công khi một bước sau thất bại. Hãy thiết kế các thao tác để có thể kiểm tra trạng thái và chạy lại an toàn.

## Idempotency là gì?

Một thao tác idempotent có cùng hiệu ứng lên trạng thái hệ thống dù được thực hiện một lần hay nhiều lần với cùng ý định và dữ liệu đầu vào.

Ví dụ, đặt trạng thái dịch vụ thành `enabled` là idempotent:

```text
service-enable --name customer-api
service-enable --name customer-api
```

Sau lần đầu, dịch vụ đã được bật. Lần thứ hai xác nhận hoặc duy trì cùng trạng thái; không tạo thêm một dịch vụ khác.

Ngược lại, thao tác tăng số lượng là không idempotent:

```text
inventory-add --sku ABC-01 --quantity 10
inventory-add --sku ABC-01 --quantity 10
```

Nếu command cộng thêm 10 ở mỗi lần gọi, chạy lại script làm tồn kho tăng thành 20. Muốn thao tác này an toàn, cần chuyển ngữ nghĩa sang đặt số lượng tuyệt đối hoặc dùng một định danh yêu cầu ổn định để hệ thống nhận ra lần gọi trùng.

| Loại thao tác | Ví dụ | Đặc tính khi chạy lại |
|---|---|---|
| Đặt trạng thái mong muốn | `service-set --enabled true` | Idempotent nếu cùng giá trị đưa hệ thống về cùng trạng thái |
| Đảm bảo tài nguyên tồn tại | `resource-ensure --name api` | Idempotent nếu có khóa duy nhất và thao tác tạo được xử lý an toàn khi trùng |
| Đồng bộ cấu hình | `config-apply --file app.yml` | Idempotent nếu cùng cấu hình tạo ra cùng trạng thái đích |
| Tăng/giảm tương đối | `counter-increment --by 1` | Không idempotent; mỗi lần gọi tạo thêm thay đổi |
| Tạo bản ghi mới không có khóa nghiệp vụ | `order-create` | Có thể tạo bản ghi trùng khi chạy lại |
| Gửi email hoặc phát thông báo | `notification-send` | Có thể gửi nhiều lần nếu không có cơ chế deduplication |
| Xóa tài nguyên đã không còn tồn tại | `resource-delete --name api` | Có thể idempotent nếu trạng thái “không tồn tại” được xem là thành công |

Idempotency nói về **hiệu ứng lên trạng thái**, không bắt buộc output phải giống hệt từng ký tự. Lần đầu command có thể trả `Created`, lần sau trả `Already exists`; hai lần vẫn idempotent nếu trạng thái đích giống nhau và không phát sinh side effect trùng.

## Vì sao script có thể bị chạy lại?

Một pipeline có thể gửi command đến dịch vụ, dịch vụ thực hiện thành công nhưng phản hồi bị mất trên đường về. Từ phía CLI, timeout không cho biết thao tác đã thất bại hay chỉ là phản hồi thất lạc. Nếu chạy lại mà không có idempotency, command có thể tạo thêm tài nguyên.

Các tình huống thường gặp:

- Máy chạy script bị dừng sau khi một số command đã thành công.
- Kết nối bị ngắt sau khi hệ thống đích đã xử lý request nhưng trước khi CLI nhận phản hồi.
- Người vận hành chạy lại vì không chắc lần trước đã hoàn tất chưa.
- Pipeline tự retry khi tiến trình trả lỗi hoặc hết thời gian chờ.
- Một script được chạy trên nhiều agent do cấu hình CI/CD hoặc lịch chạy trùng.
- Một command đã thành công nhưng bước ghi checkpoint hoặc log của script bị lỗi.

Trong những trường hợp này, chỉ nhìn mã thoát hoặc log của tiến trình chưa đủ để kết luận trạng thái thực tế. Cần truy vấn trạng thái ở hệ thống đích hoặc dùng một giao thức idempotency mà dịch vụ hỗ trợ.

## Thiết kế command theo trạng thái mong muốn

Ưu tiên command diễn đạt trạng thái cuối cần đạt thay vì mô tả một thay đổi tương đối. Các tên như `ensure`, `set`, `sync`, `apply` thường gợi ý ngữ nghĩa trạng thái đích; tuy nhiên, tên command không tự làm thao tác trở thành idempotent. Phần triển khai phải thật sự bảo đảm hợp đồng đó.

Ví dụ, command `resource-ensure` có thể kiểm tra tài nguyên theo khóa ổn định rồi bảo đảm nó tồn tại:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

enum EnsureResult {
    CREATED,
    ALREADY_MATCHES,
    UPDATED
}

@ShellComponent
class ResourceCommands {

    private final ResourceService resourceService;

    ResourceCommands(ResourceService resourceService) {
        this.resourceService = resourceService;
    }

    @ShellMethod(key = "resource-ensure")
    public String ensure(
            @ShellOption(value = "--name") String name,
            @ShellOption(value = "--region") String region) {

        EnsureResult result = resourceService.ensureExists(name, region);
        return switch (result) {
            case CREATED -> "Đã tạo tài nguyên " + name;
            case ALREADY_MATCHES -> "Tài nguyên " + name + " đã ở trạng thái mong muốn";
            case UPDATED -> "Đã cập nhật tài nguyên " + name;
        };
    }
}
```

`ResourceService.ensureExists(...)` cần thực hiện thao tác theo khóa duy nhất, ví dụ tên tài nguyên trong phạm vi tenant. Việc kiểm tra rồi tạo phải được bảo vệ bởi unique constraint, upsert hoặc transaction thích hợp. Một chuỗi `find()` rồi `insert()` không có bảo vệ cạnh tranh vẫn có thể tạo trùng khi hai script chạy cùng lúc.

Một hợp đồng service có thể diễn đạt như sau:

```java
public EnsureResult ensureExists(String name, String region) {
    // Tìm theo khóa nghiệp vụ ổn định.
    // Nếu chưa có: insert-if-absent/upsert có bảo vệ unique constraint.
    // Nếu đã có: cập nhật các thuộc tính cần hội tụ về trạng thái mong muốn.
    // Nếu đã khớp: không tạo thêm side effect.
}
```

Đây là phác thảo hợp đồng nghiệp vụ; cách triển khai database cụ thể phụ thuộc hệ quản trị và quy tắc sở hữu tài nguyên. Điều quan trọng là tính duy nhất phải được bảo vệ ở nơi lưu trạng thái, không chỉ bằng một lần kiểm tra trong Java.

### Đặt giá trị tuyệt đối thay cho thay đổi tương đối

| Dễ gây lặp tác động | Hướng thiết kế an toàn hơn |
|---|---|
| `replica-increment --by 1` | `replica-set --count 3` |
| `balance-add --amount 100` | `balance-set --expected-version ...` hoặc giao dịch có idempotency key |
| `user-create` không có khóa | `user-ensure --external-id U-1024` |
| `deploy` luôn tạo deployment mới | `deployment-ensure --service api --version 2.7.1` |
| `append-line` thêm nội dung vào file mỗi lần | `file-write --content ...` hoặc ghi theo khóa/marker xác định |

Không phải lúc nào cũng có thể chuyển một nghiệp vụ sang setter. Với thanh toán, đặt hàng, cộng điểm hoặc gửi thông báo, ý định thường là một sự kiện cần được ghi nhận một lần. Khi đó, dùng idempotency key và cơ chế chống trùng ở service xử lý.

## Dùng idempotency key cho thao tác có side effect

Khi một thao tác tạo ra side effect mà không thể biểu diễn đơn giản bằng trạng thái đích, hãy cấp một khóa định danh ổn định cho **một ý định nghiệp vụ**. Mỗi lần retry cùng ý định phải gửi lại đúng khóa đó.

Ví dụ script tạo một yêu cầu triển khai:

```text
deployment-request \
  --service customer-api \
  --version 2.7.1 \
  --idempotency-key release-staging-2026-11-26
```

Nếu request timeout, lần chạy lại phải sử dụng cùng `release-staging-2026-11-26`. Không tạo UUID mới ở mỗi lần retry, vì khi đó dịch vụ sẽ xem mỗi lần gọi là một yêu cầu khác.

Một dịch vụ xử lý idempotency key thường cần:

1. Xác định phạm vi khóa, ví dụ tenant/caller cộng với operation và key.
2. Lưu key cùng dấu vân tay (fingerprint) của các tham số nghiệp vụ.
3. Nếu key chưa tồn tại, ghi nhận yêu cầu và thực hiện thay đổi trong một transaction hoặc giao thức nhất quán tương đương.
4. Nếu key đã tồn tại với cùng tham số, trả lại kết quả trước đó hoặc một phản hồi có cùng ý nghĩa.
5. Nếu key đã tồn tại nhưng payload khác, từ chối với lỗi validation/conflict thay vì âm thầm áp dụng ý định mới.
6. Quy định thời gian lưu key đủ dài để bao phủ khoảng thời gian retry và khôi phục của workflow.

Việc ghi key và thay đổi dữ liệu cần có tính nguyên tử. Nếu lưu key thành công nhưng thao tác nghiệp vụ thất bại, lần retry có thể bị hiểu nhầm là đã hoàn tất. Nếu thao tác nghiệp vụ thành công nhưng key không được lưu, lần retry có thể tạo side effect lần nữa. AWS Builders' Library phân tích rõ yêu cầu này khi thiết kế API có idempotency token.

Idempotency key không phải phép màu ở phía client. Dịch vụ nhận request phải thực thi deduplication, lưu kết quả và xử lý hai request trùng đến đồng thời. Nếu hệ thống đích không hỗ trợ khóa idempotency, CLI cần truy vấn và đối soát trạng thái trước khi quyết định gửi lại thao tác có side effect.

## Tổ chức script để có thể tiếp tục sau lỗi

Một script dài nên chia thành các bước có ranh giới rõ ràng. Mỗi bước nên có thể chạy độc lập, kiểm tra được trạng thái sau khi chạy và có thể thực hiện lại mà không làm hỏng kết quả đã đạt.

```text
// scripts/provision-staging.shell

// 1. Kiểm tra đích triển khai và trạng thái hiện tại
target-show
target-validate --environment staging

// 2. Đảm bảo tài nguyên và cấu hình
resource-ensure --name customer-api --region ap-southeast-1
config-apply --service customer-api --file config/staging.yml

// 3. Đảm bảo phiên bản được triển khai
deployment-ensure --service customer-api --version 2.7.1

// 4. Xác minh trạng thái cuối
deployment-verify --service customer-api --version 2.7.1
```

Các command trong ví dụ phải được ứng dụng triển khai với hợp đồng phù hợp. Đặc biệt, `target-validate` cần từ chối nếu đang trỏ nhầm production; `resource-ensure`, `config-apply` và `deployment-ensure` cần hội tụ về trạng thái mong muốn; `deployment-verify` cần đọc trạng thái từ hệ thống đích.

Không nên giả định script runner tự tạo transaction cho toàn bộ file hoặc tự rollback các bước trước đó. Nếu một bước thất bại, trạng thái có thể đã thay đổi một phần. Khi chạy lại, script cần kiểm tra từng bước và tiếp tục từ trạng thái thực tế thay vì tin rằng lần chạy trước hoặc thất bại hoàn toàn hoặc thành công hoàn toàn.

### Preflight và xác nhận môi trường

Trước khi thực hiện thao tác thay đổi dữ liệu, hãy kiểm tra:

- Đúng endpoint, tenant, account và environment.
- Đúng phiên bản ứng dụng hoặc artifact sẽ triển khai.
- Tài khoản đang dùng có quyền phù hợp.
- Các tài nguyên cần thiết đã tồn tại hoặc có thể tạo.
- Không có một workflow khác đang thay đổi cùng tài nguyên.
- Các tham số của lần chạy khớp với manifest đã được duyệt.

Một command `plan` hoặc `validate` có thể in ra thay đổi dự kiến. Nếu script engine không bảo đảm dừng khi một command trả lỗi, hãy đặt preflight trong wrapper điều phối hoặc làm cho từng command thay đổi tự kiểm tra điều kiện bắt buộc ngay trước khi thực hiện.

### Checkpoint và resume

Với script dài, có thể lưu checkpoint sau mỗi bước đã xác nhận hoàn tất. Checkpoint giúp quan sát tiến độ và xác định nơi cần tiếp tục, nhưng không được dùng thay cho trạng thái thật của hệ thống đích.

Quy tắc an toàn:

- Chỉ ghi checkpoint sau khi đã xác nhận side effect hoàn tất.
- Nếu có thể, ghi trạng thái nghiệp vụ và checkpoint trong cùng transaction.
- Nếu kết quả của request không rõ do timeout, truy vấn trạng thái đích hoặc idempotency key trước khi ghi nhận thất bại.
- Khi resume, xác minh lại các bước đã đánh dấu hoàn thành; không bỏ qua mù quáng nếu tài nguyên có thể đã bị thay đổi bởi actor khác.
- Gắn checkpoint với script version, target environment và fingerprint của input để không dùng nhầm tiến độ của một lần chạy có tham số khác.

Một file checkpoint cục bộ không đủ để điều phối nhiều máy chạy song song. Với pipeline phân tán, lưu trạng thái trong database hoặc hệ thống workflow có kiểm soát concurrency.

## Xử lý lỗi và retry có giới hạn

Không phải lỗi nào cũng nên retry. Retry phù hợp với lỗi tạm thời như timeout, mất kết nối ngắn hoặc dịch vụ tạm thời quá tải. Lỗi validation, sai tham số, thiếu quyền hoặc xung đột nghiệp vụ thường cần dừng và sửa nguyên nhân.

| Nhóm lỗi | Hành động gợi ý |
|---|---|
| Timeout, connection reset, HTTP 503/429 theo hợp đồng dịch vụ | Retry có giới hạn, delay và backoff; giữ nguyên idempotency key |
| Sai định dạng hoặc thiếu tham số | Dừng, sửa script hoặc cấu hình |
| Không đủ quyền | Dừng, xử lý quyền; không retry liên tục |
| Tài nguyên tồn tại nhưng cấu hình khác mong muốn | Đối soát và áp dụng update có chủ đích hoặc báo conflict |
| Không rõ request trước đã thành công chưa | Query trạng thái hoặc dùng cùng idempotency key trước khi gửi lại |
| Lỗi logic hoặc invariant bị vi phạm | Dừng và điều tra; retry có thể lặp cùng lỗi |

Retry nên có số lần tối đa, khoảng chờ tăng dần và jitter khi nhiều client có thể retry cùng lúc. Tránh đặt retry độc lập ở mọi tầng: nếu script retry 3 lần và service bên dưới cũng retry 3 lần, số request có thể tăng theo cấp số nhân. Azure Retry pattern khuyến nghị điều chỉnh chiến lược theo loại lỗi, giới hạn số lần và tránh retry làm dịch vụ quá tải thêm.

## Các side effect khó lặp lại

Một số thao tác không thể được làm idempotent chỉ bằng cách kiểm tra “đã tồn tại chưa”:

| Side effect | Rủi ro khi chạy lại | Cách kiểm soát |
|---|---|---|
| Gửi email hoặc SMS | Người nhận nhận nhiều thông báo | Lưu notification key, dùng outbox/dedup ở dịch vụ gửi |
| Thanh toán hoặc hoàn tiền | Giao dịch bị ghi nhận nhiều lần | Idempotency key do caller cấp và dịch vụ thanh toán thực thi |
| Tạo đơn hàng | Tạo nhiều đơn giống nhau | External request ID/unique business key và xử lý trùng ở server |
| Cộng điểm hoặc trừ số dư | Giá trị bị thay đổi nhiều lần | Ledger event có ID duy nhất, transaction và deduplication |
| Xóa hoặc rotate credential | Lần chạy lại có thể xóa nhầm hoặc vô hiệu hóa credential vừa tạo | Kiểm tra version/owner, lưu kết quả và dùng thao tác có điều kiện |
| Gọi webhook hoặc publish event | Hệ thống nhận nhiều event | Event ID ổn định và consumer idempotent |

Với các side effect này, hãy làm rõ liệu yêu cầu là “một lần cho mỗi script”, “một lần cho mỗi release” hay “một lần cho mỗi nghiệp vụ”. Phạm vi đó quyết định cách tạo và lưu khóa. Một khóa quá rộng có thể chặn một hành động hợp lệ mới; một khóa quá ngắn hạn có thể cho phép request cũ bị lặp sau khi hết hạn.

## Tránh hai script chạy đồng thời trên cùng tài nguyên

Idempotency xử lý việc lặp lại cùng một ý định, nhưng không tự giải quyết mọi xung đột giữa hai workflow khác nhau. Hai script có thể cùng đọc trạng thái “chưa tồn tại” rồi cùng tạo tài nguyên. Một script có thể triển khai phiên bản A trong khi script khác triển khai phiên bản B.

Với tài nguyên dùng chung, cân nhắc:

- Distributed lock theo tenant/resource hoặc theo environment.
- Unique constraint và upsert ở database.
- Optimistic locking/version check để từ chối update dựa trên trạng thái cũ.
- Deployment lease hoặc workflow lock có thời hạn và cơ chế giải phóng khi tiến trình chết.
- Kiểm tra lại trạng thái mong muốn ngay trước khi commit thay đổi.

Lock cần có timeout và cơ chế xử lý lock hết hạn. Không giữ lock vô thời hạn nếu agent bị dừng giữa chừng. Nếu dùng optimistic locking, khi version thay đổi cần đọc lại trạng thái và quyết định reconcile thay vì gửi lại update cũ một cách mù quáng.

## Kiểm thử khả năng chạy lại

Một script chỉ nên được xem là an toàn khi đã kiểm thử ít nhất các kịch bản sau:

1. **Chạy lần đầu:** tài nguyên được tạo/cập nhật đúng và command báo kết quả.
2. **Chạy lần hai với cùng input:** trạng thái cuối không đổi ngoài dự kiến; không tạo thêm tài nguyên hoặc side effect.
3. **Dừng sau từng bước:** mô phỏng tiến trình chết sau bước 1, 2, 3 rồi chạy lại toàn bộ script.
4. **Mất phản hồi sau khi server đã xử lý:** mô phỏng timeout và xác nhận retry không tạo tác động lần hai.
5. **Cùng key, cùng payload:** dịch vụ trả kết quả trước đó hoặc phản hồi có cùng ý nghĩa.
6. **Cùng key, payload khác:** dịch vụ từ chối request không khớp.
7. **Hai script đồng thời:** không tạo trùng hoặc ghi đè trạng thái không có chủ đích.
8. **Target sai:** preflight từ chối môi trường ngoài phạm vi.
9. **Dữ liệu đích bị thay đổi thủ công:** lần chạy lại phát hiện drift và reconcile hoặc báo conflict theo chính sách.
10. **Lỗi không thể retry:** validation/authorization thất bại phải dừng, không lặp vô hạn.

Ma trận ví dụ:

| Lần chạy | Trạng thái ban đầu | Kết quả mong đợi |
|---|---|---|
| Lần 1 | Chưa có `customer-api` | Tạo một tài nguyên và lưu cấu hình đích |
| Lần 2 | Tài nguyên đã đúng cấu hình | Không tạo bản sao; báo đã ở trạng thái mong muốn |
| Retry sau timeout | Server đã tạo nhưng client không nhận phản hồi | Cùng idempotency key trả lại kết quả của yêu cầu trước |
| Resume sau khi dừng ở bước cấu hình | Tài nguyên đã có, cấu hình chưa đúng | Giữ tài nguyên, tiếp tục hội tụ cấu hình |
| Chạy song song | Hai process cùng yêu cầu một tài nguyên | Chỉ có một tài nguyên theo khóa duy nhất; process còn lại nhận trạng thái hiện có hoặc conflict rõ ràng |

Nên kiểm thử ở cả hai mức: unit test cho service idempotent và integration test chạy lại chính file script qua Spring Shell. Unit test đơn lẻ không chứng minh rằng parser, script runner, command ordering và hệ thống đích phối hợp đúng khi có lỗi giữa chừng.

## Checklist trước khi đưa script vào CI/CD

- [ ] Mỗi command thay đổi trạng thái có hợp đồng idempotency được ghi rõ.
- [ ] Tài nguyên được nhận diện bằng khóa ổn định hoặc idempotency key.
- [ ] Key được giữ nguyên giữa các lần retry của cùng một ý định.
- [ ] Server từ chối cùng key nhưng khác payload.
- [ ] Tạo key và ghi nhận side effect được phối hợp nguyên tử hoặc có giao thức phục hồi tương đương.
- [ ] Script xác nhận đúng target, tenant, environment và phiên bản input.
- [ ] Có cách phát hiện trạng thái thực tế sau timeout hoặc partial failure.
- [ ] Retry có giới hạn và phân biệt lỗi tạm thời với lỗi không thể retry.
- [ ] Có kiểm soát concurrency khi nhiều pipeline có thể thao tác cùng tài nguyên.
- [ ] Đã thử chạy script hai lần và resume sau khi dừng ở từng bước.
- [ ] Các side effect như email, payment và event publish có cơ chế deduplication riêng.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chạy lại script tạo thêm tài nguyên | Command dùng thao tác create mới mỗi lần | Chuyển sang ensure/upsert với unique key hoặc idempotency token |
| Tồn kho/số dư tăng gấp đôi | Command áp dụng thay đổi tương đối | Dùng setter có version hoặc ledger event ID duy nhất |
| Email được gửi nhiều lần | Gửi thông báo là side effect không có deduplication | Dùng notification ID/outbox và consumer idempotent |
| Retry tạo request mới | Sinh idempotency key ngẫu nhiên ở mỗi lần chạy | Lưu và tái sử dụng key cho cùng một ý định nghiệp vụ |
| Key cũ chặn một yêu cầu hợp lệ | Dùng key quá rộng hoặc không gắn với phạm vi operation | Xác định scope và vòng đời key theo nghiệp vụ |
| Script dừng giữa chừng rồi chạy lại làm sai trạng thái | Giả định toàn bộ file là một transaction | Thiết kế từng bước có thể reconcile và chạy lại |
| Hai pipeline cùng tạo một tài nguyên | Chỉ kiểm tra tồn tại ở phía client | Dùng unique constraint/upsert, lock hoặc optimistic locking |
| Retry làm dịch vụ quá tải | Retry không giới hạn hoặc nhiều tầng retry chồng nhau | Giới hạn số lần, backoff, jitter và chỉ retry lỗi tạm thời |
| Checkpoint báo xong nhưng tài nguyên chưa được tạo | Ghi checkpoint trước khi side effect hoàn tất | Ghi nhận kết quả nguyên tử hoặc xác minh trạng thái trước khi resume |

## Quy trình thiết kế script có thể chạy lại

1. Xác định trạng thái đích của từng tài nguyên và từng command.
2. Phân loại thao tác: đọc, đặt trạng thái, tạo tài nguyên, thay đổi tương đối hay side effect.
3. Chuyển thao tác có thể sang dạng ensure/set/apply; dùng khóa nghiệp vụ ổn định.
4. Với side effect không thể lặp, thiết kế idempotency key ở service nhận request và lưu kết quả.
5. Chia script thành các bước có thể kiểm tra và reconcile độc lập.
6. Thêm preflight, xác nhận target và kiểm tra quyền trước khi thay đổi dữ liệu.
7. Thiết kế retry có giới hạn; không retry lỗi validation hoặc authorization.
8. Thêm khóa hoặc kiểm soát version nếu script có thể chạy đồng thời.
9. Kiểm thử chạy hai lần, timeout, partial failure, resume và payload mismatch.
10. Ghi log theo script run ID, operation ID và idempotency key để có thể điều tra kết quả.

Khi các command hội tụ về trạng thái mong muốn và các side effect có cơ chế chống trùng, việc chạy lại toàn bộ script trở thành một cách phục hồi đáng tin cậy sau gián đoạn. Script runner chỉ phát lại command; tính an toàn đến từ hợp đồng của command và hệ thống thực hiện nghiệp vụ.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Script](https://docs.spring.io/spring-shell/reference/3.3/commands/builtin/script.html): script command đọc file cục bộ và phát lại command lần lượt; hỗ trợ comment `//` và line continuation bằng `\`.
- [Spring Shell 3.4.3 API — ScriptShellRunner](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/ScriptShellRunner.html): runner nhận process argument bắt đầu bằng `@` để chạy file script và có ưu tiên cao hơn các runner khác.
- [AWS Builders' Library — Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/): idempotency key do caller cung cấp, xử lý request trùng, kiểm tra payload và phối hợp nguyên tử giữa key với side effect.
- [AWS Well-Architected — Make all responses idempotent](https://docs.aws.amazon.com/wellarchitected/2023-10-03/framework/rel_prevent_interaction_failure_idempotent.html): dùng idempotency token để retry request mà không tạo bản ghi hoặc side effect trùng.
- [Microsoft Azure Architecture Center — Retry pattern](https://learn.microsoft.com/azure/architecture/patterns/retry): phân biệt lỗi tạm thời, retry có giới hạn, backoff và các rủi ro khi thao tác không idempotent.
