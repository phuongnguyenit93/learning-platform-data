# Untrusted cached state: không lấy cache phía client làm căn cứ nghiệp vụ

## 1. Dữ liệu đã từng đúng có thể không còn dùng được

Một ứng dụng lưu giỏ hàng, giá, quyền người dùng và tiến trình checkout trong bộ nhớ cục bộ. Khi kết nối trở lại, client gửi toàn bộ object đã lưu để server tiếp tục xử lý.

Trong khoảng thời gian đó, giá có thể hết hiệu lực, ownership có thể đã đổi, quyền duyệt có thể bị thu hồi hoặc một thao tác thanh toán đã thành công dù client chưa nhận response. Người dùng cũng có thể chủ động sửa dữ liệu trong cache trước khi gửi.

Nếu server tin `cachedTotal`, `isApproved`, `isOwner` hoặc `lastCompletedStep` như trạng thái có thẩm quyền, người gọi có thể dùng một bản sao cũ hoặc bị sửa để vượt các quy tắc hiện tại.

**Untrusted cached state** là trạng thái được giữ ở môi trường client mà server không được mặc định tin về tính toàn vẹn, ngữ cảnh sử dụng hoặc hiệu lực hiện hành.

Cache vẫn hữu ích cho hiển thị nhanh, giữ bản nháp và làm việc khi kết nối kém. Ranh giới cần giữ là:

```text
Cache phía client hỗ trợ trải nghiệm và biểu đạt ý định.
Quyết định nghiệp vụ phải dựa trên căn cứ được server chấp nhận.
```

Trong bảo vệ logic nghiệp vụ, điều này liên quan trực tiếp tới không tự duyệt, không sửa giá, không dùng quyền của tenant khác, không bỏ bước và không tạo tác động trùng khi đồng bộ lại.

## 2. Những loại trạng thái client thường lưu

Cache có thể nằm trong bộ nhớ ứng dụng, local storage, cơ sở dữ liệu cục bộ, file, bộ nhớ HTTP hoặc một lớp lưu phục vụ offline. Vị trí không tự làm dữ liệu trở nên có thẩm quyền.

| Loại dữ liệu | Giá trị sử dụng hợp lệ | Điều server không được tự tin |
|---|---|---|
| Bản nháp người dùng nhập | Giữ nội dung để gửi lại | Nội dung đã được validation hoặc được phép ghi mọi field |
| Snapshot đối tượng | Hiển thị trạng thái lần cuối biết | Owner, state hoặc version vẫn hiện hành |
| Giá và ưu đãi | Hiển thị căn cứ đã thấy, tham chiếu quote | Giá đó còn áp dụng cho giao dịch mới |
| Role và cờ quyền UI | Điều hướng hoặc ẩn/hiện chức năng | Người gọi vẫn có quyền hành động trên server |
| Tiến trình workflow | Mở lại màn hình đang làm | Các bước đã hoàn tất thật và còn hiệu lực |
| Trạng thái payment/job | Cho biết kết quả lần cuối nhận | Tác động hiện chưa xảy ra hoặc đã thành công |
| Token/snapshot do server phát | Có thể mang bằng chứng trong phạm vi cơ chế | Chỉ cần giữ token là được bỏ qua mọi kiểm tra hiện tại |

### 2.1. Client kiểm soát môi trường của mình

Không cần phá TLS để sửa dữ liệu mà chính client gửi. UI bị khóa, hidden field hoặc một biến `readOnly` trong JavaScript không phải điều kiện authorization.

Cũng không cần có hành vi cố ý để cache trở nên sai. Hai tab, thiết bị khác, cập nhật nền và timeout đều có thể tạo trạng thái cũ hợp lệ về lịch sử nhưng không còn đủ để thực hiện lệnh mới.

### 2.2. Dữ liệu từng đến từ server vẫn là bản sao khi được gửi lại

Một response có `roles`, `ownerId`, `approvedBy` hoặc tổng tiền có thể cần cho hiển thị. Việc client gửi nguyên object đó trở lại không biến mọi field thành đầu vào được phép ghi.

Read model và write contract cần tách rõ. Không bind snapshot cache vào entity rồi lưu chỉ vì snapshot có nguồn ban đầu là API của chính hệ thống.

## 3. Ba câu hỏi khác nhau: toàn vẹn, ràng buộc và hiệu lực

Một bản cache chỉ có thể được sử dụng đúng khi hiểu nó trả lời được câu hỏi nào.

| Câu hỏi | Ví dụ | Vì sao cần phân biệt? |
|---|---|---|
| Nội dung có bị đổi ngoài cơ chế cho phép không? | Snapshot có chữ ký kiểm tra được | Nguyên vẹn chưa có nghĩa còn được phép dùng |
| Nội dung dành cho ngữ cảnh nào? | Quote gắn với tenant, khách và giỏ cụ thể | Token đúng của giỏ khác vẫn không dùng được |
| Điều kiện còn hiệu lực không? | Quote còn hạn, membership còn hoạt động | Dữ liệu đúng lúc phát hành có thể đã hết hiệu lực |

### 3.1. UUID, timestamp và version không phải bằng chứng quyền

Một ID khó đoán không chứng minh người gọi được dùng đối tượng. `lastSyncedAt` do client gửi không chứng minh đã đồng bộ thành công. Version khớp chỉ giúp đối chiếu dữ liệu, không tạo quyền sửa.

Người dùng có thể biết version mới nhất mà vẫn không phải owner hoặc không có role cần thiết. Authorization và kiểm tra đồng thời phải cùng tồn tại.

### 3.2. Dấu thời gian của thiết bị không kéo dài quyền

Không dùng đồng hồ client để quyết định coupon, delegation, quote hoặc bằng chứng xác thực còn hạn. Thiết bị có thể sai giờ hoặc dữ liệu thời gian bị sửa.

Một lệnh được xếp hàng lúc client cho rằng còn hạn không tự được server chấp nhận sau hạn. Nếu nghiệp vụ bảo lưu quyền theo một thời điểm đã chốt, cần bằng chứng và chính sách phía server cho điều đó.

### 3.3. Snapshot ký đúng không phải trạng thái hiện tại

Chữ ký có thể hỗ trợ tính toàn vẹn và nguồn phát theo cơ chế đó. Nó không tự chứng minh đối tượng chưa đổi owner, policy chưa thu hồi quyền hoặc snapshot chưa được dùng cho một nghĩa vụ khác.

Ngược lại, snapshot có thể được thiết kế để giữ giá trong một khoảng thời gian. Khi đó dùng giá snapshot còn hợp lệ là đúng hợp đồng, không nhất thiết phải thay bằng catalog mới nhất. Phải phân biệt một cam kết có phạm vi với một bản sao tùy ý.

## 4. Các cách cache cũ hoặc bị sửa làm sai nghiệp vụ

### 4.1. Giá và cấu hình không còn đi cùng nhau

Client cache giá cho sản phẩm A nhưng giỏ hiện tại đã đổi sang biến thể B. Nếu server lấy giá cũ và hàng hóa mới, người dùng có thể trả thiếu.

Căn cứ giá cần gắn với sản phẩm, số lượng, tiền tệ, điều kiện giao và revision liên quan. Không chỉ giữ một con số tổng rồi tái sử dụng cho mọi cấu hình.

### 4.2. Quyền UI biến thành quyền server

Client gửi `canApprove = true` hoặc một danh sách role lấy từ cache. Nếu backend dùng chúng để quyết định, một lần đổi local state có thể trở thành tự cấp quyền.

Server cần xác thực danh tính và đọc/kiểm tra nguồn quyền theo mức độ mới được yêu cầu. Token có claim đã xác minh vẫn cần được dùng đúng semantics về thu hồi và phạm vi, không phải một danh sách role client tự khai.

### 4.3. Workflow được tiếp tục từ bước tự khai

Các field như `step = payment`, `completedSteps`, `isVerified` hoặc `approvalComplete` có thể chỉ phản ánh UI lần cuối.

Server phải dùng lịch sử/trạng thái bền vững và bằng chứng tương ứng. Không cho đi tới bước đặc quyền chỉ vì client cache rằng bước trước đã xong.

### 4.4. Owner hoặc tenant thay đổi trong khi thiết bị offline

Người từng là owner có thể không còn được sửa. Một người thuộc nhiều tenant có thể đã chuyển ngữ cảnh ở tab khác. Cache không được làm lẫn quyền của các phạm vi đó.

Mỗi lệnh cần tenant mục tiêu rõ, được xác minh lại với chủ thể và đối tượng. `currentTenant` được lưu ở client không tự tạo membership.

### 4.5. Client cho rằng lỗi mạng nghĩa là chưa có tác động

Timeout sau khi server commit hoặc sau khi cổng thanh toán xử lý không chứng minh thao tác thất bại. Nếu đồng bộ lại bằng một operation mới, hệ thống có thể tạo đơn hoặc thu tiền lần nữa.

Client chỉ biết “chưa nhận được kết quả”. Server cần idempotency, operation và đối soát để biết điều gì đã thực sự xảy ra.

## 5. Hợp đồng command chỉ nhận ý định được phép

### 5.1. Không gửi entity cache như một lệnh tổng quát

Một request nguy hiểm có thể là:

```json
{
  "expenseId": "expense-17",
  "tenantId": "tenant-A",
  "ownerId": "member-9",
  "state": "APPROVED",
  "isValid": true,
  "completedSteps": ["submit", "review"],
  "lastSyncedAt": "2026-11-22T01:00:00Z"
}
```

Mỗi giá trị có thể đọc được, nhưng payload không phải bằng chứng các bước và quyền tương ứng đã tồn tại.

Thay vào đó, dùng lệnh cụ thể với đầu vào hẹp:

```http
POST /tenants/{tenantId}/expense-requests/{expenseId}/submit
Content-Type: application/json
Idempotency-Key: stable-client-command-key

{
  "expectedVersion": 12
}
```

Server nạp hồ sơ, kiểm tra người được phép gửi, trạng thái và dữ liệu đã lưu. Không nhận cờ valid hoặc trạng thái đích từ cache làm căn cứ.

### 5.2. Field người dùng thực sự được sửa vẫn cần validation

Nếu người dùng chỉnh nội dung bản nháp khi offline, có thể gửi một lệnh cập nhật field được phép trước, rồi dùng version trả về để gửi lệnh submit.

Các field như mục đích, số lượng hoặc lựa chọn sản phẩm là ý định cần xét. Server kiểm tra miền giá trị, quan hệ, trạng thái và nguồn giá liên quan như với request online.

Không dùng `isOffline = true` để giảm yêu cầu validation hay authorization. Phương thức lưu tạm không làm thay đổi quyền của người gọi.

### 5.3. Expected version là điều kiện, không phải sự thật tự khai

Server đối chiếu version với bản ghi đang xử lý. Với API dùng body, xung đột có thể trả `409`; với precondition HTTP như `If-Match`, xử lý theo hợp đồng precondition tương ứng, thường là `412` khi không thỏa mãn.

ETag hay version không chứng minh quyền truy cập. Thực hiện kiểm tra quyền cần thiết trước khi tiết lộ trạng thái hoặc dữ liệu giúp người ngoài phạm vi suy đoán đối tượng.

## 6. Minh họa Java: submit từ trạng thái phía server

Ví dụ tập trung vào bản nháp đã được lưu trên server. Nội dung chỉnh sửa offline phải đi qua lệnh cập nhật hợp lệ trước đó. Các dependency là hợp đồng do ứng dụng triển khai, không phải API thư viện có sẵn.

```java
record SubmitExpenseCommand(long expectedVersion) {}

SubmitReceipt submit(
        UUID tenantId,
        UUID expenseId,
        SubmitExpenseCommand command) {

    ActorContext actor = identity.requireTenantActor(tenantId);
    validateShape(command);

    return transactions.required(() -> {
        ExpenseRequest expense = expenses
                .lockByTenantAndId(actor.tenantId(), expenseId)
                .orElseThrow(NotFound::new);

        submissionPolicy.requireCanSubmit(actor, expense);
        expense.requireVersion(command.expectedVersion());
        expense.requireState(ExpenseState.DRAFT);

        SubmissionBasis basis = submissionRules.buildFromServerRecords(
                actor, expense, clock.instant());

        int changed = expenses.markSubmitted(
                actor.tenantId(), expense.id(), expense.version(), basis);
        if (changed != 1) {
            throw new Conflict("CONCURRENT_MODIFICATION");
        }

        SubmitReceipt result = new SubmitReceipt(
                expense.id(), expense.version() + 1,
                basis.id(), "SUBMITTED");

        audit.appendSubmitted(actor, expense, basis, result);
        outbox.appendExpenseSubmitted(actor.tenantId(), expense, basis);
        return result;
    });
}
```

Các hợp đồng cần giữ:

- Actor và tenant được xác minh; không lấy role, owner hoặc membership từ object cache.
- Policy xét quan hệ hiện hành cần thiết, quyền trong tenant và hành động cụ thể.
- `buildFromServerRecords` dùng dữ liệu có thẩm quyền, kiểm tra chứng từ/quan hệ/giá trị bắt buộc và tạo căn cứ có phiên bản. Nó không nhận `isValid` do client tự tính.
- `markSubmitted` ràng buộc tenant, ID, trạng thái nguồn và version/căn cứ theo triển khai; kiểm tra số dòng cập nhật.
- Mọi đường sửa dữ liệu ảnh hưởng basis phải tham gia cơ chế version/khóa phù hợp.
- Audit thành công, outbox và thay đổi cần cùng transaction nếu muốn nguyên tử như ví dụ.
- Lỗi phải rollback các ghi bắt buộc; không trả thành công rồi để background phát hiện trạng thái cache không hợp lệ.

Ví dụ không có tham số `cachedState`, `approvedBy` hoặc `lastCompletedStep`. Việc client từng hiển thị các giá trị đó không cấp khả năng gửi chúng như lệnh đặc quyền.

### 6.1. Ngữ cảnh quyền vẫn có yêu cầu độ mới riêng

Khóa hàng expense không tự khóa membership, policy hoặc kho danh tính bên ngoài. Nếu cần thu hồi quyền có hiệu lực với transaction đang chạy, cần giao thức đồng bộ đủ mạnh theo cam kết.

Không khẳng định một transaction cục bộ biến mọi nguồn dữ liệu thành snapshot hiện hành. Phải xác định rõ những nguồn được bảo vệ và mức độ trễ được chấp nhận.

### 6.2. Server phải trả căn cứ được chấp nhận

Response nên cho biết version và trạng thái đã được ghi theo hợp đồng, để client thay snapshot hiển thị của mình. Không echo cờ cache như thể chúng là kết quả nghiệp vụ.

Sau lỗi xung đột, client cần tải lại dữ liệu mà nó còn được phép xem và xử lý khác biệt. Không tự thay version mới rồi gửi lại mọi thay đổi mà người dùng chưa xem xét.

## 7. Offline queue và đồng bộ lại

### 7.1. Tách các trạng thái trải nghiệm khỏi kết quả server

Client có thể cần các nhãn:

```text
lưu trên thiết bị
chờ gửi
đang gửi
server đã tiếp nhận
nghiệp vụ đã hoàn tất
cần xử lý xung đột
```

Không gộp “đã lưu offline” thành “đã duyệt” hoặc “đã thanh toán”. Một request được queue nhận cũng không nhất thiết đã tạo tác động cuối cùng.

Nếu sản phẩm chủ ý cho phép một loại nghiệp vụ ngoại tuyến bằng capability/quota đã cấp, phải mô hình hóa phạm vi, thời hạn, gửi lặp và rủi ro đối soát riêng. Một cache tùy ý không trở thành cơ chế ủy nhiệm đó.

### 7.2. Giữ định danh ý định ổn định khi retry

Một lệnh trong queue cần định danh phù hợp để retry không trở thành ý định mới mỗi lần có mạng. Lưu idempotency key cùng nội dung cần gửi theo hợp đồng, thay vì sinh key mới sau mỗi timeout.

Server ràng buộc key với tenant, chủ thể, hành động, đối tượng và fingerprint phù hợp. Nội dung queue vẫn có thể bị sửa, nên mỗi lệnh phải được kiểm tra như dữ liệu đầu vào không đáng tin.

Cùng key nhưng đổi nội dung phải bị phát hiện. Đổi key cũng không được vượt điều kiện trạng thái hoặc tạo thêm tác động cho cùng một nghĩa vụ mà domain cấm lặp.

### 7.3. Lệnh phụ thuộc nhau cần kết quả xác nhận

Nếu cập nhật bản nháp rồi submit, không thể mặc định version sau cập nhật là `oldVersion + 1` theo trí nhớ client trong mọi tình huống. Request khác có thể đã chạy hoặc lệnh cập nhật có thể thất bại.

Chỉ tiến bước phụ thuộc khi có căn cứ server phù hợp. Một chuỗi thao tác lưu cục bộ không chứng minh mọi bước đã commit.

### 7.4. Không last-write-wins cho mọi field

Gộp ghi chú có thể có quy tắc khác gộp số tiền, người nhận, owner hoặc trạng thái phê duyệt. Không dùng timestamp thiết bị làm quyền ghi đè chung.

Nếu có merge tự động, giới hạn theo field và ý nghĩa đã thiết kế. Các thay đổi cần xác nhận lại hoặc duyệt lại phải tiếp tục đi qua workflow đó.

### 7.5. Queue không được tự đổi chủ khi đổi account

Một lệnh được tạo dưới account/tenant A không nên tự được gửi như ý định của B khi người dùng đăng nhập account khác. Giữ ngữ cảnh nguồn và yêu cầu xác thực/đối chiếu phù hợp trước đồng bộ.

Server vẫn phải chặn lệnh sai quyền ngay cả khi client làm sai. Việc phân vùng queue là lớp hỗ trợ tránh gửi nhầm và lộ dữ liệu trên thiết bị.

## 8. Snapshot có chữ ký và tham chiếu mờ

### 8.1. Dữ liệu toàn vẹn vẫn cần đúng mục đích

Nếu server phát một snapshot/token được bảo vệ toàn vẹn, cần kiểm tra những ràng buộc mà hợp đồng yêu cầu, chẳng hạn:

```text
issuer/mục đích + tenant + subject
+ resource + action + revision/căn cứ
+ thời hạn + điều kiện sử dụng lại
```

Một token để xem bản nháp không tự cho quyền sửa. Quote cho giỏ A không dùng cho giỏ B. Snapshot giá không tự chứng minh người dùng hiện còn quyền phát lệnh mua.

### 8.2. Không đặt bí mật ký trong client rồi coi là bằng chứng server

Một khóa chung có sẵn cho mọi bản client không thể làm request tùy ý của client trở thành quyết định nghiệp vụ của server. Tương tự, ký hoặc mã hóa nguyên dữ liệu chưa kiểm tra không làm nội dung ban đầu đúng.

Cơ chế phát hành cần lấy căn cứ có thẩm quyền và đóng đúng phạm vi. Chữ ký bảo vệ phần đã được ký theo cơ chế đó, không thay toàn bộ authorization và domain validation.

### 8.3. Phiên bản trong token cần được so với nguồn phù hợp

Token có `authzVersion = 10` không chứng minh nguồn chưa lên version 11. Nếu server chỉ dùng số 10 từ token để tìm permit cũ, cache vẫn có thể cho phép ngoài cam kết thu hồi.

Đường thực thi phải biết version hoặc độ mới nào hiện được chấp nhận. Nếu chính nguồn version cũng bị cache, cần quản lý giới hạn cũ của nó, không đẩy vấn đề sang một lớp khác rồi coi đã giải quyết.

### 8.4. ID mờ vẫn chỉ là một tham chiếu

Client có thể lưu quote ID, resume token hoặc operation ID thay vì toàn bộ dữ liệu. Điều này giúp giữ căn cứ phía server, nhưng không tự tạo quyền.

Khi dùng ID, vẫn nạp đúng tenant, kiểm tra liên kết đối tượng và quyền nhận/thực hiện. Với capability có thể dùng chỉ bằng việc nắm giữ, phạm vi và khả năng thu hồi phải được thiết kế rõ, không giả định nó giống một ID thông thường.

## 9. Cache hiển thị, HTTP revalidation và riêng tư giữa account

### 9.1. Namespace cache theo ngữ cảnh phù hợp

Client không nên dùng một key chung như `currentOrder` hoặc chỉ một ID cục bộ nếu dữ liệu có thể thuộc nhiều tenant/account. Phân vùng theo ngữ cảnh đã biết và xóa/bỏ qua dữ liệu khi ngữ cảnh đổi theo chính sách.

Đây là kiểm soát trải nghiệm và riêng tư ở client; server không được dùng key cache client như bằng chứng quyền.

### 9.2. Response đến muộn không được ghi vào ngữ cảnh mới

Tab đang ở tenant A phát request, sau đó người dùng chuyển sang B. Response của A đến muộn có thể bị đưa vào màn hình hoặc cache của B nếu code chỉ ghi vào biến toàn cục.

Giữ ngữ cảnh của request và kiểm tra nó còn phù hợp trước khi cập nhật UI/cache; hủy hoặc bỏ qua kết quả không còn đúng ngữ cảnh theo thiết kế. Server vẫn phải áp dụng quyền cho từng request độc lập.

### 9.3. 304 và HEAD không phải đường bỏ qua quyền

Trước khi trả nội dung, `304 Not Modified`, thông tin `HEAD` hoặc redirect tải tệp riêng tư, server cần kiểm tra quyền tương ứng. ETag khớp không làm người gọi trở thành owner.

Một cache HTTP dùng chung không được trả response theo quyền A cho B. Chọn chính sách cache như `private`, `no-store` hoặc cơ chế khác theo loại dữ liệu; các chỉ thị đó không đồng nghĩa mã hóa hay khả năng thu hồi mọi bản sao đã tải.

### 9.4. Lớp offline phải tuân thủ chính sách dữ liệu riêng tư

Một lớp lưu tùy chỉnh có thể chủ động giữ response. Chỉ thêm header không thay việc kiểm tra logic cache của ứng dụng/offline layer.

Khi logout, đổi account hoặc mất quyền, xử lý các bản sao theo chính sách và giới hạn thực tế của môi trường. Không hứa có thể xóa mọi byte mà một người đã tải hợp lệ hoặc chủ động sao chép.

Điều server phải bảo vệ là truy cập và tác động mới theo quyền hiện tại hoặc cam kết có phạm vi đã cấp.

## 10. Transaction, worker và trạng thái tác động bên ngoài

### 10.1. Bản sao client không bảo vệ khoảng kiểm tra–cập nhật

Người gọi có thể gửi đúng snapshot nhưng dữ liệu đổi ngay sau khi server đọc. Cần khóa hoặc cập nhật có điều kiện theo version/căn cứ của domain.

Ví dụ hai client cùng thấy coupon chưa dùng hoặc ngân sách còn đủ. Cả hai request hợp lệ về cú pháp vẫn có thể vi phạm bất biến nếu kiểm tra và tiêu thụ tách rời.

Ràng buộc tenant, uniqueness và các ledger/reservation cần giữ đúng phạm vi. Không đẩy kiểm tra này sang một cờ trong cache client.

### 10.2. Worker không tin trạng thái client chuyển tiếp

Message có `clientSaysApproved = true` không chứng minh hồ sơ đã được duyệt. Worker cần nạp/đối chiếu căn cứ được server chấp nhận hoặc kiểm tra ủy nhiệm thực thi theo hợp đồng.

Phải xác định quyền cần còn ở lúc nhận hay lúc thực thi. Credential service rộng không được tự bù cho việc người dùng không còn được phép.

### 10.3. Payment status do client gửi không phải kết quả thanh toán

Client hiển thị thành công, thất bại hoặc chờ xử lý chỉ là dữ liệu trải nghiệm. Server xác nhận theo operation, nguồn kết quả được xác thực và các thuộc tính như số tiền/loại tiền theo hợp đồng tích hợp.

Timeout không có nghĩa thất bại. Nếu kết quả chưa rõ, tiếp tục đối soát operation cũ; không tạo khoản thu mới chỉ vì cache còn `paid = false`.

### 10.4. Kết quả đã xảy ra cần được giữ như sự thật lịch sử

Quyền hoặc ownership đổi không xóa khoản tiền đã chuyển. Service được cấp quyền vẫn cần hoàn tất/đối soát nghĩa vụ đã phát sinh theo workflow.

Việc người dùng còn được nhận biên nhận nào là một quyết định truy cập riêng. Không trả toàn bộ kết quả idempotency chỉ vì họ còn giữ key cũ.

## 11. Kiểm thử trạng thái cache bị sửa hoặc đã cũ

| Tình huống | Kỳ vọng |
|---|---|
| Sửa role, owner, tenant hoặc cờ duyệt trong local state rồi gửi | Không thay căn cứ authorization và workflow phía server |
| Thay giá/tổng tiền hoặc currency của snapshot | Không tạo khoản thu theo dữ liệu không có thẩm quyền |
| Dùng quote còn hạn đúng cam kết nhưng catalog đã đổi | Xử lý theo policy quote, không tự coi là tampering |
| Quote hết hạn hoặc sai cart revision | Không dùng ngoài hợp đồng; yêu cầu làm mới/xác nhận khi cần |
| Sửa `completedSteps` hoặc màn hình hiện tại | Không bỏ bước server chưa xác nhận |
| Membership/ownership đổi khi thiết bị offline | Lệnh mới tuân thủ quyền hiện hành theo cam kết |
| Thiết bị lùi/tiến giờ hoặc giả `lastSyncedAt` | Không kéo dài hiệu lực quyền lợi theo giờ client |
| Hai tab sửa cùng version | Không ghi đè căn cứ mới trái hợp đồng |
| Queue gửi lại cùng lệnh sau mất response | Không tạo quyết định/operation trùng |
| Cùng key nhưng payload queue bị sửa | Phát hiện xung đột nội dung theo hợp đồng |
| Đổi key để gửi lại nghĩa vụ domain chỉ cho một lần | Bất biến trạng thái/uniqueness vẫn chặn lặp |
| Đổi account/tenant trước khi đồng bộ | Không gửi/hiển thị dữ liệu như thuộc ngữ cảnh mới |
| ETag của A được B gửi hoặc cache response bị dùng chéo | Không trả dữ liệu/304 vượt quyền |
| Response A đến sau khi UI đã chuyển sang B | Không ghi vào cache/hiển thị của B trái thiết kế |
| Token/snapshot ký đúng nhưng sai mục đích hoặc đối tượng | Không được dùng ngoài binding |
| Nguồn quyền hoặc baseline bắt buộc không khả dụng | Không fallback sang trạng thái client |
| Cache client ghi payment thất bại nhưng operation đã thành công | Không thu lại; trả/đối soát kết quả đúng quyền |
| Bản nháp hợp lệ và queue retry đúng hợp đồng | Luồng hợp lệ vẫn hoàn tất |

### 11.1. Tách kiểm thử client với kiểm thử server

UI test có thể kiểm tra namespace, account switch, hiển thị trạng thái chờ và merge xung đột. API/integration test cần gửi trực tiếp payload bị sửa để chứng minh có thể bỏ qua toàn bộ UI mà vẫn không vượt quy tắc.

Một mock client luôn gửi state đúng không chứng minh server an toàn. Một server trả lỗi cũng chưa đủ nếu mutation hoặc tác động đã xảy ra trước lỗi.

### 11.2. Kiểm tra business projection và cổng tác động

Sau request bị chặn, kiểm tra state, owner, basis, approval, quyền lợi và operation không bị thay đổi trái hợp đồng. Audit hoặc bộ đếm kỹ thuật có thể được ghi hợp lệ.

Với thanh toán hoặc hệ thống ngoài, quan sát operation và số nghĩa vụ thực tế, không chỉ số lần HTTP được gửi nếu giao thức cho phép gửi lại cùng operation có chống trùng.

### 11.3. Kiểm thử có điều khiển về thời gian và cạnh tranh

Dùng đồng hồ kiểm thử cho hạn quote/delegation. Điều khiển thứ tự đọc–ghi để tái hiện thay owner, sửa basis hoặc tiêu thụ quyền lợi trong lúc lệnh đang xử lý.

Với transaction, khóa và constraint, integration test trên loại cơ sở dữ liệu triển khai có giá trị hơn chỉ dựng một boolean `isStale`. Với cache/account switch, chủ động cho response đến ngược thứ tự.

## 12. Tự rà soát ranh giới tin cậy của cache client

Trước khi dùng dữ liệu từ cache để thực hiện một hành động, hãy trả lời:

1. Dữ liệu này chỉ hỗ trợ hiển thị/ý định hay đang bị dùng làm quyết định có thẩm quyền?
2. Server lấy owner, role, tenant, trạng thái và giá từ nguồn nào?
3. Có field đặc quyền nào được gửi lại nguyên từ response rồi bind vào entity không?
4. Version/ETag có được đối chiếu mà vẫn giữ authorization không?
5. Snapshot/token có đúng nguồn, mục đích, đối tượng, thời hạn và quy tắc dùng lại không?
6. Offline queue có phân biệt đã lưu cục bộ, server chấp nhận và tác động đã hoàn tất không?
7. Retry, xung đột và merge có thể làm mất xác nhận hoặc tạo nghĩa vụ trùng không?
8. Cache/UI có cách ly account/tenant và xử lý response đến muộn không?
9. Worker và callback có đối chiếu căn cứ server thay vì tin cờ client không?
10. Khi nguồn bắt buộc lỗi, có đường nào fallback sang cache không đáng tin để cho phép hành động không?

Cache phía client là bản sao để hỗ trợ sử dụng, không phải quyền quyết định nghiệp vụ. Mỗi hành động cần được kiểm tra bằng danh tính, căn cứ và trạng thái mà server có thẩm quyền chấp nhận, kể cả khi client đang offline, dùng dữ liệu cũ hoặc gửi lại yêu cầu.
