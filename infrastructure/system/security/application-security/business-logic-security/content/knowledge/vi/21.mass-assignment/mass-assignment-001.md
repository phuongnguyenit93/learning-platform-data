# Writable field inventory — Danh mục trường được phép ghi

## 1. Mass assignment bắt đầu từ một ranh giới ghi không rõ ràng

Một request cập nhật đơn hàng có thể chỉ hiển thị địa chỉ nhận, số lượng và ghi chú trên giao diện. Tuy nhiên, nếu backend gắn toàn bộ JSON vào entity hoặc sao chép mọi thuộc tính cùng tên, người gọi có thể gửi thêm `tenantId`, `ownerId`, `state`, `unitPriceMinor` hoặc thông tin phê duyệt.

Các trường đó không trở thành được phép sửa chỉ vì người dùng có quyền cập nhật đơn hàng. **Quyền thực hiện action trên đối tượng khác với quyền ghi mọi thuộc tính của đối tượng.**

Mass assignment là tình huống input có thể tác động tới các thuộc tính ngoài phạm vi được phép thông qua cơ chế gán hoặc ánh xạ quá rộng. Nó có thể xảy ra ở controller, mapper, ORM, import, consumer hoặc một lớp xử lý dữ liệu về sau.

**Writable field inventory** là danh mục xác định rõ mỗi trường đầu vào được dùng để làm gì, có được ghi hay không, ai được dùng, ở action và trạng thái nào, cùng những dữ liệu hoặc tác động mà nó có thể làm thay đổi.

Mục tiêu không chỉ là liệt kê một số field nhạy cảm để chặn. Cần xác định tập field được phép theo hướng đóng: một field mới không tự được mở quyền ghi chỉ vì entity hoặc mapper vừa có thêm thuộc tính.

## 2. Danh mục phải gắn với action, không chỉ với entity

Một đối tượng đơn hàng có nhiều thao tác khác nhau:

```text
CREATE_DRAFT
REPLACE_DRAFT_INPUTS
ADD_CUSTOMER_NOTE
SUBMIT_ORDER
APPROVE_ORDER
REQUEST_CANCELLATION
PROPOSE_PRICE_OVERRIDE
```

Mỗi action có một hợp đồng ghi riêng. Không nên dùng một DTO `OrderUpdate` cho mọi vai trò và mọi bước chỉ vì chúng cùng tác động bảng `purchase_order`.

Ví dụ:

| Dữ liệu | Sửa input bản nháp | Gửi duyệt | Phê duyệt | Ghi nhận thanh toán |
| --- | --- | --- | --- | --- |
| Số lượng sản phẩm | Có điều kiện | Không sửa ngầm | Không sửa ngầm | Không |
| Ghi chú khách hàng | Theo hợp đồng action | Có thể chỉ đọc snapshot | Không tự đổi nội dung được duyệt | Không |
| Giá chốt | Server tính theo nguồn định giá | Chốt theo policy | Gắn với nội dung được duyệt | Đọc đúng nghĩa vụ thanh toán |
| Trạng thái | Không do client chọn | Server thực hiện transition | Server thực hiện transition | Do quy trình xác nhận phù hợp |
| Người duyệt | Không | Không | Server lấy từ danh tính thật | Không |
| Tenant và chủ sở hữu | Không sửa qua action này | Không | Không | Không |

Một trường có thể được thay đổi bởi một quy trình đặc biệt nhưng vẫn không được ghi qua endpoint cập nhật thông thường. Ví dụ sửa giá có thẩm quyền là action riêng, không phải lý do để mở `unitPriceMinor` cho mọi request sửa đơn.

## 3. Phân loại trường trước khi quyết định mapping

| Loại trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Client được đặt theo hợp đồng | Có thể lấy giá trị đề nghị để lưu sau kiểm tra | Ghi chú khách hàng trong giới hạn được phép |
| Client được đề nghị, server quyết định | Input tham gia đánh giá hoặc tính toán, không tự là kết quả có thẩm quyền | Mã giảm giá, số lượng, đề nghị chọn địa chỉ |
| Do server quản lý | Nguồn có thẩm quyền nằm ở server hoặc hệ thống được tin cậy | Tenant, trạng thái, giá tính lại, người phê duyệt |
| Bất biến đối với action | Action này không được thay đổi dù client biết giá trị | ID đơn, chủ sở hữu hiện tại |
| Selector | Dùng để chọn đối tượng cần thao tác, không phải giá trị để gán lại khóa | Order ID trên URL, ID một dòng đang sửa |
| Điều kiện kiểm soát | Dùng để xác nhận tiền đề hoặc nhận diện ý định | Expected version, idempotency key |

`expectedVersion=18` không có nghĩa client được đặt cột `version=18`. Nó yêu cầu server chỉ nhận hành động nếu phiên bản hiện tại phù hợp; khi ghi thành công, server tự tăng version.

Tương tự, `shippingAddressId` không có nghĩa backend được gắn bất kỳ địa chỉ nào tồn tại. Địa chỉ phải đúng tenant, quan hệ khách hàng và điều kiện sử dụng theo policy.

### 3.1. Đừng nhầm trường phản hồi với trường ghi

Response có thể chứa `state`, `quotedTotalMinor`, `approvedBy` hoặc `createdAt` để hiển thị. Sự hiện diện trong response không tạo quyền gửi lại những field đó để cập nhật.

API nên công bố rõ model đọc và hợp đồng ghi. Lấy toàn bộ response rồi PUT trở lại không mặc nhiên là một thao tác được hỗ trợ.

## 4. Mỗi mục trong inventory cần chứa gì?

Một mục có thể mô tả:

```text
WritableFieldEntry = {
    input_channel,
    action,
    field_path,
    field_classification,
    source_of_truth,
    allowed_operations,
    subject_and_object_conditions,
    lifecycle_conditions,
    validation_rules,
    affected_data_and_side_effects,
    audit_requirements,
    verification_cases,
    policy_owner
}
```

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Kênh input | Field đến từ body, URL, query, form, file import hay message? |
| Đường dẫn | Là field cấp cao, field con, phần tử mảng hay key trong map? |
| Nguồn có thẩm quyền | Client đề nghị hay server tự lấy từ nguồn nào? |
| Phép ghi | Được tạo, thay thế, xóa, thêm hay chỉ dùng làm điều kiện? |
| Điều kiện chủ thể | Quyền nào, trong tenant và quan hệ đối tượng nào? |
| Điều kiện vòng đời | Chỉ bản nháp, trước giao hàng hay sau một phê duyệt riêng? |
| Tác động | Có đổi giá, tài nguyên, quyền truy cập hoặc làm mất hiệu lực approval không? |
| Bằng chứng kiểm tra | Test nào chứng minh chỉ có các thay đổi được phép? |

Inventory không chỉ là bảng tài liệu. Nó phải được phản ánh trong DTO, parser, mapper, domain method, câu lệnh ghi và các test kiểm tra hành vi thực tế.

## 5. Ví dụ inventory cho input bản nháp đơn hàng

Giả sử action `REPLACE_DRAFT_INPUTS` chỉ cho sửa lựa chọn địa chỉ, các dòng sản phẩm, mã ưu đãi và ghi chú của đơn còn ở `DRAFT`.

| Đường dẫn | Phân loại | Quy tắc ghi và nguồn |
| --- | --- | --- |
| `expectedVersion` | Điều kiện kiểm soát | Bắt buộc; so với version hiện tại, không gán vào entity |
| `shippingAddressId` | Đề nghị tham chiếu | Tra trong phạm vi tenant và khách hàng được phép |
| `lines[*].skuId` | Đề nghị tham chiếu | Chọn SKU dùng được; không sửa SKU catalog |
| `lines[*].quantity` | Client đề nghị | Số nguyên dương và có giới hạn; làm server tính lại giá |
| `couponCode` | Client đề nghị | Có thể để trống theo hợp đồng; server kiểm tra điều kiện áp dụng |
| `customerNote` | Client được đặt | Nội dung và kích thước hợp lệ; không được diễn giải như lệnh |
| `lines[*].unitPriceMinor` | Server quản lý | Không nhận từ action này; lấy từ nguồn định giá |
| `lines[*].discountMinor` | Server quản lý | Server tính theo chính sách, không lấy từ JSON |
| `quotedTotalMinor` | Server quản lý | Tính từ các dòng và chính sách đã kiểm tra |
| `quoteRevision` | Server quản lý | Ghi revision thực sự dùng để định giá |
| `tenantId`, `ownerId` | Không ghi qua action | Lấy và giữ theo ngữ cảnh hoặc dữ liệu hiện tại |
| `state`, `approvalId`, `approvedBy` | Server quản lý | Chỉ thay đổi qua action nghiệp vụ phù hợp |
| `paidAmountMinor`, `paymentStatus` | Server quản lý | Không thuộc hợp đồng sửa draft |

Quyền sửa input không có nghĩa mọi dữ liệu khác phải giữ nguyên tuyệt đối: thay số lượng có thể làm tổng giá server tính lại thay đổi. Inventory phải mô tả cả những phụ thuộc được phép thay đổi để phân biệt hành vi đúng với mass assignment.

### 5.1. Selector của dòng không phải quyền nhận một dòng bất kỳ

Nếu một endpoint cho sửa dòng hiện có bằng line ID, phải kiểm tra dòng thuộc đúng order và tenant. Không merge một entity dòng được client gửi với ID của đơn khác.

Ví dụ thay toàn bộ lựa chọn SKU và số lượng có thể không cần nhận line ID. Nếu sản phẩm cần giữ định danh dòng, hãy thiết kế selector và phép sửa rõ ràng thay vì mở toàn bộ object dòng cho mapper.

## 6. Thu thập inventory từ mọi nguồn ghi

Trong một dự án thực tế, cần lần theo cả đường nhận input lẫn nơi dữ liệu được sử dụng:

1. Endpoint, controller, consumer, import và tác vụ quản trị nhận dữ liệu gì?
2. DTO hoặc schema cho phép những field và cấu trúc con nào?
3. Parser có alias, naming strategy, key động hoặc cơ chế nhận field mở rộng không?
4. Mapper nào chuyển input vào entity, domain command hoặc message khác?
5. Repository hoặc ORM có thể ghi những cột và quan hệ nào?
6. Những field nào còn ảnh hưởng quyết định quyền, định giá hoặc lời gọi bên ngoài?
7. Có đường cập nhật khác sử dụng cùng entity nhưng ít kiểm tra hơn không?

Không chỉ tìm setter công khai. Việc ghi có thể đến từ constructor, builder, reflection, mapper sinh mã, raw map, thao tác merge hoặc cấu hình cascade của quan hệ dữ liệu.

### 6.1. Inventory phải bao gồm input không được lưu trực tiếp

Các field như sau vẫn có thể mang tác động bảo mật:

```text
force
skipApproval
includeAllTenants
onBehalfOf
sendNotificationTo
callbackUrl
```

Chúng có thể thay đổi luồng kiểm tra, phạm vi đọc hoặc hiệu ứng bên ngoài mà không xuất hiện như một cột entity. Nếu chỉ kiểm kê cột dữ liệu, những đường này sẽ bị bỏ sót.

### 6.2. Nguồn đã xác thực vẫn cần hợp đồng ghi

Một message có chữ ký hoặc một webhook đến từ tích hợp hợp lệ không có nghĩa được sửa mọi field của đối tượng. Mỗi loại sự kiện vẫn phải được ánh xạ vào đúng action, tenant, đối tượng và tập dữ liệu có thẩm quyền.

## 7. Hình dạng payload không phải ranh giới duy nhất

### 7.1. Object lồng nhau

Cho phép field `contact` không nên được hiểu là cho phép mọi thuộc tính hiện tại và tương lai của entity contact.

Cần chỉ rõ các lá được phép, chẳng hạn:

```text
contact.displayName
contact.phoneNumber
```

Nếu bên trong contact còn có `ownerId`, `verificationStatus` hoặc quan hệ tới user, chúng không được tự mở quyền chỉ vì object cha đã được chấp nhận.

### 7.2. Mảng

Cho phép `lines[*].quantity` khác với cho phép `lines[*]` như một object tự do. Mỗi dòng cần giới hạn schema, số lượng phần tử và quan hệ tới đối tượng cha.

Batch chứa nhiều order cũng phải kiểm tra từng order. Quyền trên order đầu không bao phủ các phần tử còn lại.

### 7.3. Map mở rộng

Một map `metadata` có thể được cho phép để lưu dữ liệu hiển thị, nhưng không được trở thành đường vòng:

```json
{
  "metadata": {
    "approved": true,
    "effectiveTenant": "another-tenant"
  }
}
```

Những key đó không tự có quyền điều khiển nghiệp vụ. Nếu một lớp xử lý về sau trộn metadata vào entity hoặc dùng nó để chọn tenant, quyền ghi ban đầu đã mở rộng qua một bước trung gian.

Cần giới hạn key, kiểu, kích thước, độ sâu và những nơi metadata được phép ảnh hưởng. Đặt tên “metadata” không làm dữ liệu trở nên vô hại.

### 7.4. Alias và field mơ hồ

Parser có thể hỗ trợ nhiều tên cho cùng thuộc tính. Inventory phải biết những tên thực sự được chấp nhận, không chỉ tên Java hoặc tên trong tài liệu.

Các key JSON trùng lặp hoặc những biểu diễn được các lớp hiểu khác nhau cũng cần chính sách xử lý rõ ràng. Nếu chọn từ chối input mơ hồ, phải kiểm tra hành vi parser thực tế; không đợi đến mapper rồi giả định đã biết duy nhất một giá trị ban đầu.

## 8. Create, PUT và PATCH có ngữ nghĩa ghi khác nhau

### 8.1. Tạo mới

Client có thể đề nghị các dữ liệu ban đầu nhưng server phải tự thiết lập tenant, actor tạo, trạng thái đầu và những giá trị hệ thống theo policy.

Nếu hỗ trợ tạo thay người khác, đó là một khả năng có quyền riêng. Không mở `ownerId` cho mọi caller chỉ để đáp ứng một trường hợp quản trị đặc biệt.

### 8.2. Thay thế input

PUT có thể thay thế phần biểu diễn mà endpoint công bố, không mặc nhiên là thay toàn bộ entity lưu trữ. Một endpoint `/draft-inputs` có thể thay bộ input draft nhưng vẫn giữ nguyên nguồn sở hữu, audit và trạng thái do server quản lý.

Không lấy field thiếu trong payload thay thế làm lý do đặt lại các cột bảo vệ về giá trị mặc định.

### 8.3. Bản vá và trạng thái hiện diện

Với PATCH, cần phân biệt:

```text
Không có field : không sửa, nếu hợp đồng quy định như vậy.
Field là null : yêu cầu xóa, nếu phép xóa được phép.
Field có giá trị : đề nghị đặt giá trị mới.
```

Một mapper biến mọi field vắng mặt thành null hoặc false có thể xóa dữ liệu ngoài ý định, kể cả khi người dùng không gửi một field bảo vệ nào.

Sau khi áp dụng bản vá vào một candidate, phải kiểm tra toàn bộ điều kiện cần thiết trước khi lưu. Không kiểm tra entity cũ rồi mới áp dụng một patch làm nó mất bất biến.

### 8.4. Các phép patch tổng quát

Nếu API nhận các phép như `add`, `replace`, `remove`, `move`, `copy` hoặc `test`, inventory phải xác định phép nào được dùng trên path nào.

Với `copy` hoặc `move`, cần xét cả quyền đọc nguồn lẫn ghi đích, cùng các tác động làm thay đổi quan hệ. Một phép `test` trên field bảo vệ cũng có thể tạo tín hiệu suy đoán giá trị nếu được phép thử tùy ý.

Không coi một thư viện áp dụng patch đúng cú pháp là đã cấp quyền đúng cho các path. Với nghiệp vụ nhạy cảm, những command cụ thể thường dễ kiểm soát hơn một cơ chế sửa tùy ý toàn bộ biểu diễn đối tượng.

## 9. Danh sách cho phép phải được thực thi ở đường ghi

Các lớp kiểm soát có thể bổ sung cho nhau:

| Lớp | Vai trò |
| --- | --- |
| Schema hoặc DTO theo action | Giới hạn hình dạng input được hỗ trợ |
| Parser | Áp dụng chính sách field lạ, alias, kiểu và kích thước |
| Mapper tường minh | Chỉ đưa những dữ liệu được chọn vào candidate |
| Authorization | Kiểm tra chủ thể, tenant, đối tượng và quyền sử dụng từng khả năng |
| Domain method | Giữ trạng thái và bất biến khi thay đổi |
| Repository có điều kiện | Chỉ ghi đúng đối tượng và version theo hợp đồng |
| Constraint dữ liệu | Chặn một số trạng thái hoặc quan hệ không hợp lệ |

Một schema có nhãn field chỉ đọc hoặc cấm property bổ sung chỉ có tác dụng khi đường nhận request thực sự áp dụng đúng quy tắc đó. Object con cần được giới hạn tương ứng, không tự thừa hưởng mọi giới hạn của object cấp trên.

Annotation chỉ đọc ở một cơ chế deserialize cũng không bảo vệ được một mapper khác, một form binder hoặc consumer không dùng cơ chế ấy.

### 9.1. Vì sao denylist dễ thiếu?

Một mapper có thể chặn `isAdmin` nhưng sau đó entity được thêm `platformRole`, `approvalBypass` hoặc một quan hệ mới. Nếu mặc định mọi field khác đều được copy, thay đổi model vô tình trở thành thay đổi quyền ghi.

Danh sách cho phép theo action làm ngược lại: field mới không được mở chỉ vì nó tồn tại. Mỗi lần thêm cần xác định ngữ nghĩa, nguồn và tác động trước.

### 9.2. Field lạ: từ chối hay bỏ qua?

Ví dụ trong bài chọn từ chối field ngoài hợp đồng để tránh client tưởng rằng một yêu cầu đã được áp dụng và giúp phát hiện input sai.

Một API có thể chọn bỏ qua để tương thích, nhưng phải chứng minh field đó không được dùng ở bất kỳ bước ghi hay hiệu ứng nào. Bỏ qua ở parser đầu rồi dùng raw body ở lớp khác sẽ phá bảo đảm này.

## 10. Ví dụ Java: DTO input không phải entity đơn hàng

Một hợp đồng input hẹp:

```java
public record DraftLineInput(
        UUID skuId,
        Integer quantity) {
}

public record ReplaceDraftInput(
        Long expectedVersion,
        UUID shippingAddressId,
        List<DraftLineInput> lines,
        String couponCode,
        String customerNote) {
}
```

Không có field giá, trạng thái, tenant, owner hoặc approval. Những kiểu nullable cho phép bộ kiểm tra phân biệt thiếu trường với giá trị số mặc định khi hợp đồng cần điều đó.

DTO vẫn cần kiểm tra danh sách không rỗng, số phần tử, giá trị từng dòng và giới hạn chuỗi. Nó không tự kiểm tra SKU, địa chỉ hoặc coupon có được phép dùng.

Chính sách từ chối field lạ phải được cấu hình và kiểm thử trên parser của endpoint thực tế, kể cả object dòng lồng nhau. Việc định nghĩa record không tự chứng minh mọi cấu hình binding đều từ chối đúng.

### 10.1. Payload có trường bảo vệ phải bị xử lý theo hợp đồng

```json
{
  "expectedVersion": 18,
  "shippingAddressId": "f3c7f40a-4e54-4e7d-9e47-91760271d627",
  "lines": [
    {
      "skuId": "11c1234b-6e31-4de8-bc69-94a1d54a2f5f",
      "quantity": 2,
      "unitPriceMinor": 1
    }
  ],
  "customerNote": "Giao trong giờ làm việc",
  "state": "APPROVED"
}
```

Theo lựa chọn từ chối field ngoài hợp đồng, request này không được áp dụng: `lines[*].unitPriceMinor` và `state` không phải input được ghi qua action.

Không chỉ bỏ `state` rồi để giá giả lọt qua mapper con. Inventory và kiểm tra phải đi đến từng path có thể ảnh hưởng dữ liệu.

## 11. Ví dụ service: ánh xạ tường minh và định giá từ server

### 11.1. Giả định

Ví dụ sử dụng Spring transaction và dữ liệu cục bộ hoặc snapshot nguồn được bảo vệ theo giao thức phù hợp:

- Người gọi đã có ngữ cảnh tenant được kiểm tra.
- Mọi sửa đổi draft khóa cùng order và dùng version tương ứng.
- Dữ liệu địa chỉ, giá và coupon được đọc theo quy tắc nhất quán của hệ thống.
- Không tạo giữ chỗ tồn kho, thu tiền hoặc gọi dịch vụ bên ngoài trong transaction minh họa.
- Domain không dùng lại approval cũ cho nội dung draft được thay đổi; quyết định về sau phải gắn đúng content version.

### 11.2. Service minh họa

Các repository và kiểu dữ liệu cần được triển khai. Constructor injection được lược bỏ; đây không phải ứng dụng chạy độc lập.

```java
@Service
public class OrderDraftInputService {
    private final OrderRepository orders;
    private final ShippingAddressRepository addresses;
    private final DraftPricingSource pricingSource;
    private final ServerPricingService pricing;
    private final DraftInputPolicy policy;
    private final DraftReplacementFactory replacements;
    private final IdempotencyRepository idempotency;
    private final WorkflowAuditRepository audits;
    private final OutboxRepository outbox;
    private final DatabaseTimeSource databaseTime;
    private final CommandFingerprint fingerprints;

    @Transactional(rollbackFor = Exception.class)
    public DraftUpdateReceipt replaceDraftInputs(
            VerifiedActor actor,
            ReplaceDraftInputsCommand command) {

        actor.requireAuthenticated();
        command.validateSyntaxAndBounds();
        ReplaceDraftInput input = command.input();

        PurchaseOrder order = orders.lockForUpdate(
                actor.tenantId(), command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        // Quyền trên đối tượng; trạng thái cho lần sửa mới kiểm tra riêng.
        policy.requireDraftInputAuthority(actor, order);

        CommandScope keyScope = new CommandScope(
                actor.tenantId(), order.id(),
                actor.canonicalSubjectId(),
                "REPLACE_DRAFT_INPUTS", command.idempotencyKey());
        String fingerprint = fingerprints.forDraftInputs(command);

        var previous = idempotency.find(keyScope);
        if (previous.isPresent()) {
            if (!previous.get().fingerprint().equals(fingerprint)) {
                throw new IdempotencyConflictException();
            }
            return previous.get().receipt();
        }

        order.requireDraftAtVersion(input.expectedVersion());

        ShippingAddress address = addresses.findUsableForOrder(
                actor.tenantId(), order, input.shippingAddressId())
            .orElseThrow(ShippingAddressNotUsableException::new);
        policy.requireCanUseAddress(actor, order, address);

        DraftPricingSnapshot pricingInputs = pricingSource.loadForDraft(
                actor.tenantId(), order,
                input.lines(), input.couponCode());

        Instant checkedAt = databaseTime.currentInstant();
        ServerQuote quote = pricing.quote(
                order, input.lines(), input.couponCode(),
                pricingInputs, checkedAt);

        DraftReplacement replacement = replacements.fromAllowedInputs(
                order, input, address, quote);
        policy.requireValidReplacement(actor, order, replacement);

        int changed = orders.replaceDraftInputs(
                actor.tenantId(), order.id(), order.version(),
                replacement, checkedAt);
        if (changed != 1) {
            throw new ConcurrentOrderChangeException();
        }

        audits.appendDraftInputsReplaced(
                actor, order, replacement, checkedAt);
        outbox.appendOrderDraftChanged(
                UUID.randomUUID(), actor.tenantId(),
                order.id(), order.version() + 1);

        DraftUpdateReceipt receipt = new DraftUpdateReceipt(
                order.id(), order.version() + 1,
                quote.totalMinor(), quote.revision());
        idempotency.insert(keyScope, fingerprint, receipt);
        return receipt;
    }
}
```

Các dependency `final` cần được khởi tạo bằng constructor. Với Spring transaction qua proxy thông thường, lời gọi phải đi qua bean được quản lý, và các repository cần dùng đúng transaction manager.

`fromAllowedInputs()` phải tạo candidate từ từng trường được chọn. Nó không được ẩn một lệnh copy toàn bộ entity hoặc raw map bên trong. `ServerQuote` phải được tạo từ dữ liệu định giá đáng tin cậy, không deserialize từ body rồi coi là kết quả server.

`replaceDraftInputs()` của repository phải giữ phạm vi order, các dòng con và transaction. Nếu thay bộ dòng, chỉ thay các dòng của đúng order và tenant; không dùng ID tùy ý của client để cập nhật entity khác.

### 11.3. SQL parent update có danh sách cột rõ ràng

```sql
UPDATE purchase_order
SET shipping_address_id = :authorizedAddressId,
    coupon_code = :normalizedCouponCode,
    customer_note = :normalizedNote,
    quoted_total_minor = :serverTotalMinor,
    quote_revision = :serverQuoteRevision,
    updated_at = :checkedAt,
    version = version + 1
WHERE tenant_id = :verifiedTenantId
  AND id = :orderId
  AND state = 'DRAFT'
  AND version = :expectedVersion;
```

Đây là phần cập nhật parent minh họa; dữ liệu dòng và những ràng buộc khác phải được xử lý trong cùng transaction. Các dấu `:` là tham số bind của lớp truy cập dữ liệu.

Giá trị giá và revision đến từ quote server, không từ một field có cùng tên trong JSON. Thành công cần số dòng parent update bằng 1.

Danh sách cột cụ thể giúp giới hạn tác động ghi nhưng vẫn không thay thế authorization, kiểm tra địa chỉ, định giá hoặc điều kiện domain.

## 12. Trường nhạy cảm cần những action riêng

Một inventory tốt thường làm lộ ra các nhóm field không nên đi chung trong endpoint cập nhật rộng.

| Nhu cầu | Action có thể tách riêng | Điều kiện cần bảo vệ |
| --- | --- | --- |
| Đổi chủ sở hữu | Chuyển quyền sở hữu | Quyền nguồn và đích, tenant, grant cũ, audit |
| Đổi trạng thái | Submit, approve, cancel | Transition hợp lệ, bằng chứng và version |
| Thay giá đặc biệt | Đề nghị hoặc phê duyệt override | Thẩm quyền, giới hạn, lý do và phê duyệt nếu cần |
| Gán role | Quản trị assignment | Trần quyền, scope và phân tách nhiệm vụ |
| Ghi nhận thanh toán | Xử lý command hoặc xác nhận đã kiểm tra | Nguồn xác nhận, idempotency và hiệu ứng tài chính |
| Chuyển tenant | Quy trình chuyển giao riêng | Toàn bộ quan hệ dữ liệu và miền quản trị |

Tách action không chỉ là đổi URL. DTO, quyền, logic domain và đường ghi của action đó phải thực sự khác hợp đồng cập nhật thông thường.

Không để role admin tự làm mọi field writable. Quản trị tenant cũng có ranh giới, và một quyền vận hành mạnh vẫn không tự cho phép tắt bất biến tài chính hoặc giả mạo actor phê duyệt.

## 13. Lỗi cần tránh ở mapper và ORM

### 13.1. Copy cùng tên không hiểu thẩm quyền

Một công cụ copy thuộc tính có thể biết kiểu dữ liệu nhưng không biết rằng `state` chỉ được đổi sau khi kiểm tra phê duyệt, hoặc `ownerId` không thuộc quyền người gọi.

Nếu dùng mapper sinh mã, cấu hình phải diễn đạt danh sách mapping được cho phép và có kiểm tra phù hợp khi model thay đổi. Không mặc định mọi thuộc tính mới cùng tên đều là một phép ghi an toàn.

### 13.2. Entity detach hoặc quan hệ cascade

Nhận một đồ thị entity từ client rồi merge vào persistence context có thể tác động cả quan hệ và entity con tùy cấu hình. Việc root entity đúng order không chứng minh mọi nút trong đồ thị đều thuộc order đó.

Nên chọn dữ liệu theo command và tải quan hệ có thẩm quyền ở server, thay vì tin đồ thị đối tượng có ID do client dựng.

### 13.3. Giá trị mặc định ghi đè dữ liệu bảo vệ

Một input thiếu `approved` có thể trở thành `false` nếu dùng chung model và mapper không phân biệt hiện diện. Một input thiếu trường quan hệ có thể làm xóa liên kết ngoài ý định.

Vấn đề không chỉ là kẻ tấn công thêm field. Nó còn là cách binder và mapper xử lý field vắng mặt hoặc null làm thay đổi dữ liệu không được phép.

### 13.4. Không đặt lại owner thành người đang sửa

Khi quản trị viên sửa một ghi chú, tự gán `owner=currentActor` cũng là thay đổi sai ngữ nghĩa dù không lấy owner từ client. Nguồn đúng của field có thể là dữ liệu đang có, không phải luôn luôn là actor hiện tại.

## 14. Quyền ghi phụ thuộc trạng thái và dữ liệu hiện tại

Một field trong allowlist vẫn có thể không writable trong hoàn cảnh cụ thể:

- Địa chỉ không đổi được sau mốc giao hàng theo policy.
- Số lượng không đổi được sau khi nội dung đã được phê duyệt, trừ một quy trình sửa đổi riêng.
- Một note chỉ dành cho nhân viên không được khách hàng ghi dù cùng nằm trên order.
- Một mã tham chiếu dùng làm khóa chống trùng có thể không được đổi tùy ý như nhãn hiển thị.

Vì vậy cần kết hợp:

```text
field thuộc hợp đồng action
AND actor có quyền trên đối tượng
AND phép ghi cụ thể được phép
AND trạng thái hiện tại cho phép
AND candidate sau thay đổi giữ các bất biến
```

### 14.1. Kiểm tra rồi ghi phải cùng bảo vệ một phiên bản

Nếu đọc `DRAFT`, chờ một lúc rồi ghi toàn entity khi order đã `APPROVED`, dữ liệu input có thể ghi đè snapshot được duyệt hoặc trạng thái hiện tại.

Khóa, expected version và cập nhật có điều kiện cần ngăn việc nhận phép ghi trên trạng thái khác với điều kiện đã kiểm tra. Mọi đường sửa liên quan phải tuân theo giao thức phù hợp.

### 14.2. Không dùng field input để tự làm điều kiện cho phép

Không kiểm tra `input.state == DRAFT` để quyết định quyền sửa rồi ghi input vào entity. Trạng thái có thẩm quyền phải lấy từ đối tượng hiện tại.

Tương tự, một cờ `skipRepricing` hoặc `approvedDiscount` không được làm mất bước tính toán bắt buộc chỉ vì đã có trong request.

## 15. Lỗi phản hồi, audit và thay đổi schema

### 15.1. Phản hồi field ngoài hợp đồng

Có thể dùng mã ổn định như `FIELD_NOT_ALLOWED` với path công khai được giới hạn phù hợp. Không trả toàn bộ danh sách thuộc tính nội bộ của entity hoặc stack trace để giải thích field nào không tồn tại.

Field không thuộc hợp đồng khác với field có giá trị sai hoặc field chỉ không sửa được ở trạng thái hiện tại. Hợp đồng lỗi nên giúp client phân biệt mà vẫn giữ chính sách không tiết lộ ngoài quyền.

Không phản chiếu một payload chứa giá giả hoặc trạng thái giả thành read model mà giao diện hiểu là dữ liệu đã được server chấp nhận. Response phải phản ánh kết quả canonical hoặc lỗi thực sự.

### 15.2. Audit ghi những thay đổi được nhận

Audit có thể lưu action, actor, tenant, object ID, version trước và sau, những nhóm field được sửa, nguồn định giá và policy revision.

Nếu một request bị từ chối trước nhận, không phát sự kiện như order đã thay đổi. Nếu audit bắt buộc hoặc outbox ghi lỗi trong transaction, không commit riêng dữ liệu nghiệp vụ còn lại.

Không ghi toàn bộ body hoặc bí mật vào log chỉ để tìm field lạ. Có thể ghi các path được kiểm soát và reason code phù hợp với quyền điều tra.

### 15.3. Thêm field là một thay đổi cần đánh giá quyền ghi

Khi entity, DTO, schema hoặc message có field mới, cần xác định:

- Có phải field client được phép đề nghị không?
- Nếu có, action và điều kiện nào cho phép?
- Có ảnh hưởng quyền, giá, trạng thái hoặc nguồn chống trùng không?
- Nó có mở đường qua nested object hoặc mapper dùng chung không?
- Inventory, mapping, tài liệu và test nào phải cập nhật?

Một thay đổi entity đơn thuần không nên tự mở một khả năng API mới. Đây là lợi ích chính của hợp đồng input đóng và mapping tường minh.

## 16. Kiểm thử mass assignment dựa trên inventory

### 16.1. Kiểm thử trường cấm và các lớp lồng nhau

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Thêm `state=APPROVED` vào action sửa draft | Không chuyển trạng thái hoặc tạo phê duyệt |
| Thêm tenant hoặc owner khác | Không đổi miền sở hữu hoặc truy cập dữ liệu khác |
| Thêm giá đơn vị hoặc tổng tiền giả | Không ảnh hưởng giá được server chấp nhận |
| Thêm permission, role hoặc cờ bypass trong object con | Không tạo năng lực ngoài hợp đồng |
| Thêm field vào từng phần tử `lines` | Kiểm tra đi đến từng object, không chỉ cấp cao |
| Dùng alias hoặc naming style khác | Không đi vòng hợp đồng binding thực tế |
| Dùng metadata rồi để consumer xử lý tiếp | Metadata không được nâng thành thuộc tính có thẩm quyền |
| Dùng selector dòng thuộc order khác | Không cập nhật hoặc gắn nhầm entity con |

Theo chính sách từ chối field lạ của ví dụ, request chứa field cấm bị từ chối toàn bộ và không có thay đổi nghiệp vụ mới. Không chỉ assert mã HTTP; kiểm tra database, event và công việc nền để bảo đảm không có tác động trước khi trả lỗi.

### 16.2. Kiểm thử trường được phép và tác động dẫn xuất

Thay một số lượng hợp lệ phải cập nhật đúng dòng và để server tính lại giá theo policy. Ghi chú hợp lệ chỉ ảnh hưởng những dữ liệu mà inventory cho phép, không đổi owner hoặc trạng thái.

Không viết một test chung yêu cầu mọi field không có trong payload giữ nguyên, vì các dữ liệu dẫn xuất như tổng tiền có thể phải thay đổi. Cần đối chiếu đúng tập tác động được khai báo.

Kiểm tra địa chỉ, SKU và coupon sai tenant, sai quan hệ hoặc không dùng được. Field có trong allowlist không thay thế quyền trên đối tượng tham chiếu.

### 16.3. Kiểm thử PATCH và hiện diện

1. Field vắng mặt không làm reset dữ liệu ngoài ý định.
2. Null chỉ xóa những field và trong những trạng thái được phép.
3. Candidate sau patch vẫn đủ bất biến.
4. Những phép move hoặc copy không đọc nguồn hoặc ghi đích ngoài hợp đồng.
5. Phép test không được dùng trên path bảo vệ ngoài quyền được công bố.
6. Key trùng hoặc cấu trúc mơ hồ được xử lý đúng chính sách parser đã chọn.

### 16.4. Kiểm thử concurrency, retry và transaction

Dùng transaction độc lập với barrier hoặc latch để điều khiển cuộc đua:

```text
A. Request sửa draft chờ trong lúc order được gửi hoặc duyệt.
   Kết quả: không ghi input draft lên trạng thái đã thay đổi trái policy.

B. Hai request sửa cùng version.
   Kết quả: xử lý theo giao thức version, không ghi đè dữ liệu mới âm thầm.

C. Request dùng quote hoặc nguồn định giá đã cũ.
   Kết quả: kiểm tra hoặc tính lại theo hợp đồng nguồn giá,
   không dùng một field giá từ client để chữa xung đột.
```

Audit hoặc outbox bắt buộc lỗi phải rollback phần ghi liên quan. Response mất sau commit phải được phục hồi bằng idempotency mà không tạo một lần sửa mới. Cùng key nhưng đổi payload phải xung đột theo fingerprint.

Không dùng `sleep` làm bằng chứng đã kiểm tra concurrency. Mock repository không chứng minh được khóa và ranh giới commit của cơ sở dữ liệu thực.

### 16.5. Kiểm thử mọi điểm vào và sự thay đổi model

Thực hiện những trường hợp liên quan trên API web, mobile, form, import, batch và consumer có thể tạo cùng hiệu ứng.

Khi thêm một field entity mới, xác nhận nó không tự trở thành input writable của endpoint cũ. Với DTO hoặc schema mới, kiểm tra field đã được inventory xác nhận và mapping chỉ thực hiện những thay đổi được phép.

## 17. Các lỗi thiết kế cần tránh

| Cách làm | Vì sao tạo lỗ hổng logic | Hướng thay thế |
| --- | --- | --- |
| Bind request trực tiếp vào entity | Mở cả field và quan hệ ngoài ý định | DTO theo action và mapping tường minh |
| Có quyền update thì sửa mọi field | Bỏ qua quyền trên hành động và thuộc tính | Inventory theo actor, action, đối tượng và trạng thái |
| Chỉ chặn vài field nhạy cảm | Field mới dễ tự mở quyền | Danh sách cho phép đóng |
| Cho object cha là cho mọi field con | Bỏ sót nested mass assignment | Giới hạn từng path và phần tử |
| ID hợp lệ là được gắn quan hệ | Có thể chọn tài nguyên ngoài tenant hoặc ngoài đối tượng cha | Kiểm tra quyền và quan hệ tham chiếu |
| Annotation hoặc tài liệu chỉ đọc là đủ | Có thể có binder hoặc đường ghi khác | Thực thi và test trên mọi kênh |
| Bỏ field lạ ở đầu nhưng dùng raw body về sau | Quyền quay lại qua một lớp trung gian | Một hợp đồng nguồn input xuyên suốt |
| PATCH thiếu field thành null hoặc false | Ghi đè dữ liệu ngoài ý định | Biểu diễn hiện diện và phép xóa rõ ràng |
| Metadata được trộn vào entity | Biến dữ liệu mở rộng thành quyền có thẩm quyền | Tách namespace và giới hạn mọi nơi sử dụng |
| Giá hoặc trạng thái lấy từ client để chọn điều kiện | Người gọi tự quyết định được quyền sửa | Nguồn server và state machine có thẩm quyền |
| Admin được bỏ mọi giới hạn field | Vượt ranh giới tenant và quy trình nghiệp vụ | Action quản trị có scope và trần cụ thể |
| Response lỗi là coi không có tác động | Có thể đã ghi dữ liệu hoặc phát event | Kiểm tra trạng thái sau lỗi và bảo vệ transaction |

## 18. Bài tập lập inventory

Lập danh mục trường cho các action tạo draft, thay input draft, gửi duyệt và đề nghị sửa giá của một hệ thống đơn hàng nhiều tenant.

Với từng field hoặc path, hãy xác định:

1. Nó là dữ liệu client được đặt, đề nghị, selector, điều kiện kiểm soát hay dữ liệu server quản lý?
2. Nó được tạo, thay thế hoặc xóa ở action và trạng thái nào?
3. Nguồn nào quyết định tenant, owner, giá, trạng thái và bằng chứng phê duyệt?
4. Những đối tượng tham chiếu và phần tử con phải được kiểm tra quan hệ ra sao?
5. Nó có thể ảnh hưởng dữ liệu hoặc hiệu ứng nào ngoài cột được lưu trực tiếp?
6. Mapper và repository bảo đảm chỉ ghi tập thay đổi đã khai báo bằng cách nào?
7. Field mới trong entity hoặc metadata có thể xuất hiện ở đường ghi cũ không?
8. Test nào chứng minh payload có giá, trạng thái hoặc owner giả không tạo tác động trái phép, kể cả qua import và queue?

Một inventory đạt yêu cầu phải nối được hợp đồng input với thẩm quyền, nguồn dữ liệu và tác động ghi thực tế, để việc thêm field hoặc mở một action mới không âm thầm mở rộng quyền thao tác nghiệp vụ.
