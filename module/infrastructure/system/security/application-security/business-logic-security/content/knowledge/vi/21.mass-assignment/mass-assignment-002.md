# Command object allowlist — Giới hạn dữ liệu được phép gán vào lệnh nghiệp vụ

## 1. Command object phải giới hạn ý định mà client được biểu đạt

**Command object allowlist** là cách thiết kế đối tượng đầu vào chỉ chứa những trường mà caller được phép đề nghị thay đổi cho một use case cụ thể. Các giá trị nhận dạng chủ thể, trạng thái có thẩm quyền và dữ liệu suy ra được lấy từ nguồn server, không tự động nhận từ payload.

Ví dụ, command sửa nội dung đơn nháp có thể cho đổi tiêu đề, ghi chú và các sản phẩm/số lượng được đề nghị. Nó không nên có `approvedBy`, `tenantId`, `ownerId`, `approvalRequired` hoặc tổng tiền mà client được tự ghi vào entity.

Bài thuộc chương **Mass Assignment** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`. Mục tiêu là ngăn người gọi lợi dụng binding hoặc mapping quá rộng để sửa giá, đổi quyền, chiếm ownership hoặc bỏ qua bước phê duyệt.

Mass assignment không đòi hỏi payload phải sai định dạng. Một field như `approvalState = APPROVED` có thể đúng enum nhưng vẫn không được phép xuất hiện trong command sửa nháp.

OWASP khuyến nghị dùng DTO dành riêng cho những field được phép nhận và allowlist khi binding vào một object có thêm thuộc tính. DTO/allowlist giới hạn dữ liệu ghi được, nhưng không thay thế authorization trên object và operation. [OWASP Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html).

## 2. Mass assignment đi qua ranh giới tin cậy như thế nào?

### 2.1. Ví dụ binding trực tiếp entity

```java
// Ví dụ không an toàn để phân tích.
public PurchaseOrder update(UUID orderId, PurchaseOrder submitted) {
    submitted.setId(orderId);
    return repository.save(submitted);
}
```

Giả sử `submitted` được tạo trực tiếp từ request. Entity có thể chứa cả field người dùng được sửa lẫn field chỉ server được quản lý. Việc ép ID bằng path không tự bảo vệ các field còn lại.

Một payload có thể thử:

```json
{
  "title": "Đề nghị mua thiết bị",
  "approvalState": "APPROVED",
  "approvalRequired": false,
  "ownerPrincipalId": "attacker-controlled-principal",
  "createdByPrincipalId": "another-principal",
  "totalMinorUnits": 1,
  "lines": [
    {
      "productId": "selected-product",
      "quantity": 10,
      "unitPriceMinorUnits": 1,
      "approvedQuantity": 1000
    }
  ]
}
```

Giá trị ID ở đây chỉ minh họa ý đồ; hệ thống thật còn phải parse đúng kiểu. Ngay cả khi mọi giá trị đều được biểu diễn đúng kiểu, các thuộc tính nhạy cảm vẫn không thuộc quyền của action sửa nội dung nháp.

### 2.2. Binding vào immutable object cũng cần xét bề mặt nhận dữ liệu

Không có setter hoặc dùng Java record không tự loại bỏ mass assignment. Nếu constructor nhận `isAdmin`, `ownerId` hoặc `approvalState` từ dữ liệu bên ngoài, attacker vẫn có thể thử cấp giá trị cho chúng.

Điều cần kiểm soát là tập input được chấp nhận và nguồn của từng giá trị, không chỉ hình thức mutable/immutable của class.

### 2.3. Mapping sau DTO có thể mở lại lỗ hổng

Một hệ thống có DTO vẫn có thể không an toàn nếu sau đó:

- Giữ mọi field lạ trong `Map<String, Object>` rồi merge vào entity.
- Dùng một DTO lớn chung cho requester, reviewer và quản trị.
- Tự động copy mọi property cùng tên từ request sang domain.
- Dùng entity trong object lồng nhau hoặc cho ORM attach/merge graph do client cung cấp.
- Nhận một chuỗi đường dẫn property rồi gọi setter/reflection tùy ý.

Mapper không tự là lỗ hổng trong mọi trường hợp. Rủi ro là mapping tự động làm bề mặt ghi mở rộng khi DTO/entity được thêm field, trong khi use case chưa được xem xét lại.

## 3. Phân loại field theo nguồn và ý nghĩa

Ví dụ use case thay toàn bộ nội dung một đơn nháp:

| Field hoặc nhóm dữ liệu | Caller có được đề nghị không? | Cách xử lý |
| --- | --- | --- |
| `title`, `requesterNote` | Có | Kiểm tra độ dài/giá trị và áp vào đúng action |
| `lines[].productId` | Có, như reference được lựa chọn | Xác minh sản phẩm/tenant/quyền sử dụng, không bind product entity |
| `lines[].quantity` | Có | Kiểm tra số lượng, tổng hợp và cap nghiệp vụ |
| `expectedVersion` | Có, như điều kiện trước | So sánh với version server; không gán làm version hiện tại |
| Order ID từ URL | Có, như selector | Tìm trong scope đã xác minh và kiểm tra quyền trên object |
| Tenant và principal thực hiện | Không lấy từ body làm thẩm quyền | Từ xác thực và tenant context đã được kiểm chứng |
| Owner, creator, requester nghiệp vụ | Không đổi qua command này | Action riêng nếu nghiệp vụ cho phép |
| State/phê duyệt/người duyệt | Không | Domain operation tương ứng quyết định |
| Đơn giá, tiền tệ, tổng tiền có thẩm quyền | Không tự ghi từ body | Tra/tính từ dữ liệu server và policy |
| Audit timestamp, lý do cấp quyền, dấu vết nội bộ | Không giả mạo qua payload | Server ghi bằng chứng thật theo operation |

Một field được phép nhập không có nghĩa giá trị của nó đã được phép sử dụng. Product ID hợp lệ vẫn có thể thuộc tenant khác; quantity đúng kiểu vẫn có thể vượt giới hạn sản phẩm.

Đặc biệt, `expectedVersion` là dữ liệu caller được gửi nhưng chỉ để phát hiện stale write. Copy nó vào `entity.version` rồi lưu sẽ làm mất ý nghĩa kiểm soát concurrency.

## 4. Một command cho một ý định nghiệp vụ rõ ràng

### 4.1. Tách sửa nội dung khỏi chuyển trạng thái và đổi quyền

| Use case | Input nghiệp vụ có thể cần | Những giá trị server quyết định |
| --- | --- | --- |
| Thay nội dung draft | Title, note, sản phẩm/số lượng, version kỳ vọng | Tenant, owner, giá, tổng tiền, version mới |
| Submit | Object ID và version/ngữ cảnh cần xác nhận | Trạng thái đích và vòng duyệt |
| Approve | Version/nội dung được xem, mã lý do hoặc bằng chứng cần thiết | Actor reviewer, quyết định được chấp nhận, state tổng hợp |
| Đề nghị chuyển owner | Target ID và epoch/version kỳ vọng | Source owner, actor thật, deadline và policy chuyển |
| Cấp role | Chủ thể đích, role/scope đề nghị, thời hạn trong hợp đồng | Grantor thật và giới hạn được phép cấp |

Không nên gom tất cả thành `UpdatePurchaseOrderRequest` có mọi field rồi dựa vào việc frontend chỉ gửi một phần. Backend phải biết action đang được yêu cầu và quyền tương ứng.

### 4.2. Allowlist theo use case khác allowlist theo vai trò

Một số field có thể hợp lệ với use case đặc biệt, ví dụ đề nghị override giá. Đó không phải lý do đưa `unitPrice` vào command sửa draft của mọi caller.

Có thể tạo command/endpoint riêng với capability, lý do và policy riêng. Nếu sản phẩm cần field-level authorization động trong cùng use case, phải xác minh tập field được đề nghị trước khi mutate, không chỉ bỏ qua field thiếu quyền rồi báo thành công như đã áp toàn bộ ý định.

Trong hợp đồng minh họa của bài, payload chứa field ngoài allowlist bị từ chối cả command. Không có phần cập nhật hợp lệ nào được commit trước khi phát hiện field bị cấm ở cuối payload.

### 4.3. Không dùng denylist làm cơ chế duy nhất

```java
// Dễ bị thiếu khi entity bổ sung field nhạy cảm mới.
copyAllPropertiesExcept(request, entity, "isAdmin", "ownerId");
```

Khi thêm `approvalRequired`, `creditLimit` hoặc một object nested mới, denylist cũ có thể không biết để chặn. Allowlist hướng ngược lại: không có lý do rõ ràng thì field mới không tự trở thành input được phép của use case.

## 5. DTO và command nội bộ trong Java

### 5.1. Request model chỉ có field được phép nhận

Ví dụ dùng Jakarta Validation:

```java
public record ReplaceDraftContentRequest(
    @NotNull @Min(0) Long expectedVersion,
    @NotBlank @Size(max = 120) String title,
    @NotNull @Size(max = 2000) String requesterNote,
    @NotNull @Size(min = 1, max = 50)
    List<@NotNull @Valid RequestedLineRequest> lines
) {}

public record RequestedLineRequest(
    @NotNull UUID productId,
    @NotNull @Min(1) @Max(1000) Integer quantity
) {}
```

Các annotation thuộc Jakarta Validation; `UUID` và `List` thuộc thư viện Java chuẩn. Đây là các kiểu minh họa, có thể đặt ở những file phù hợp khi triển khai thật.

Policy ví dụ là **thay toàn bộ nội dung được phép sửa**: request phải có đủ title, note, lines và expectedVersion. `requesterNote = ""` có thể dùng để xóa nội dung ghi chú; `null` không tự được coi là cùng ý nghĩa. Partial update cần hợp đồng khác.

Nested DTO chỉ có product ID và quantity. Nó không phải `Product` hoặc `PurchaseOrderLine` entity có thêm giá, tenant, association và field nội bộ.

### 5.2. Tạo command bằng mapping tường minh

```java
public record RequestedLine(UUID productId, int quantity) {}

public record ReplaceDraftContentCommand(
    UUID orderId,
    long expectedVersion,
    String title,
    String requesterNote,
    List<RequestedLine> lines
) {
    public ReplaceDraftContentCommand {
        lines = List.copyOf(lines);
    }
}
```

Ví dụ adapter HTTP:

```java
@PutMapping("/purchase-orders/{orderId}/draft-content")
public DraftReceipt replaceDraftContent(
        @PathVariable UUID orderId,
        @Valid @RequestBody ReplaceDraftContentRequest request) {

    TrustedActor actor = authenticatedActors.current();
    VerifiedTenantContext tenant = tenantContexts.currentVerified();

    List<RequestedLine> lines = request.lines().stream()
        .map(line -> new RequestedLine(line.productId(), line.quantity()))
        .toList();

    ReplaceDraftContentCommand command = new ReplaceDraftContentCommand(
        orderId,
        request.expectedVersion(),
        request.title(),
        request.requesterNote(),
        lines);

    return application.replaceDraftContent(
        tenant, actor, command, requestMetadata.idempotencyKey());
}
```

Ở đây actor và verified tenant context là đối số riêng lấy từ cơ chế tin cậy; chúng không được deserialize từ request body. Order ID vẫn là selector do caller chọn và sẽ được kiểm tra trên object trong application service.

Record không làm mọi object chứa bên trong bất biến. Defensive copy giúp command không dùng một list bị thay đổi sau khi đã kiểm tra. Các đường gọi không qua HTTP cũng phải thực hiện validation/domain checks phù hợp, không giả định `@Valid` của controller đã chạy cho tất cả caller.

### 5.3. Không quay lại dùng raw payload sau mapping

Sau khi tạo command, các bước giá, domain và persistence dùng command cùng dữ kiện server. Không truyền thêm `rawBody`, map field thừa hoặc entity client bên cạnh để một helper phía sau tự tìm thuộc tính “còn thiếu”.

Nếu internal command chứa các field do server bổ sung, không tái sử dụng nguyên class đó làm public request model. Việc type có một constructor tiện lợi không có nghĩa mọi constructor argument đều được client quyền quyết định.

## 6. Xử lý tại application service và domain

### 6.1. Kiểm tra trước khi mutate entity

Một luồng xử lý minh họa:

```java
public DraftReceipt replaceDraftContent(
        VerifiedTenantContext tenant,
        TrustedActor actor,
        ReplaceDraftContentCommand cmd,
        String idempotencyKey) {

    commandRules.requireValid(cmd);

    return transactions.execute(tx -> {
        PurchaseOrder draft = orders.lockByTenant(tenant, cmd.orderId());
        access.requireCanReadReceipt(actor, tenant, draft);

        IdempotencyClaim claim = idempotency.claim(
            tenant.id(), actor.principalId(), "REPLACE_DRAFT_CONTENT",
            idempotencyKey, fingerprints.replaceDraftContent(cmd));

        if (claim.isCompleted()) {
            return claim.originalReceipt();
        }

        access.requireCanEditDraft(actor, tenant, draft);
        draft.requireDraftAndVersion(cmd.expectedVersion());

        ProductSelection products = catalog.requirePurchasableProducts(
            tenant, actor, cmd.lines());
        quantityRules.requireAllowed(cmd.lines(), products);

        ReplacementLines replacement = pricing.buildFromServerData(
            tenant, draft, cmd.lines(), products);

        draft.replaceDraftContent(
            cmd.title(), cmd.requesterNote(), replacement);
        draft.invalidateCurrentQuote();

        orders.saveDraftContentOrThrow(tenant, draft, cmd.expectedVersion());

        DraftReceipt receipt = audit.appendDraftContentChanged(
            tenant, actor, draft);
        outbox.appendDraftContentChanged(receipt);
        idempotency.complete(claim, receipt);
        return receipt;
    });
}
```

Đây là khung dùng `TransactionTemplate` của Spring; các dependency là hợp đồng minh họa, chưa phải chương trình hoàn chỉnh có thể chép chạy ngay.

Điểm quan trọng là domain không nhận một entity đã bị client mutate rồi mới xem có hợp lệ không. Các reference, quantity và dữ liệu giá được kiểm tra/tạo trước khi áp thay đổi có chủ đích.

### 6.2. Chỉ ghi các thay đổi thuộc operation

Với header đơn, câu SQL có thể có dạng:

```sql
UPDATE purchase_order
SET title = :validated_title,
    requester_note = :validated_note,
    total_minor_units = :server_calculated_total,
    quote_id = NULL,
    version = version + 1
WHERE tenant_id = :verified_tenant_id
  AND id = :order_id
  AND state = 'DRAFT'
  AND version = :expected_version;
```

Tenant, owner, creator và approval state không nằm trong tập field được action này ghi từ client. Tổng tiền được cập nhật từ kết quả server, không từ property cùng tên trong request.

Việc thay các dòng hàng cần đúng semantics đã chọn: các dòng mới/được cập nhật phải có tenant, parent, ID và giá do server quản lý. Trong mô hình thay toàn bộ ở đây, payload không được tự gắn một line entity có sẵn của object khác vào đơn.

Kiểm tra số hàng cập nhật và giữ thay đổi header/lines, audit, outbox, idempotency trong cùng transaction. Mọi writer liên quan phải tuân state/version và giao thức khóa tương ứng.

### 6.3. Validation và allowlist bảo vệ những việc khác nhau

`@Min(1)` chặn một quantity âm nhưng không quyết định caller có được sửa quantity trong đơn này không. `@NotNull` trên owner ID không làm field đó thành input được phép.

Ngược lại, DTO không có owner field vẫn chưa ngăn caller sửa object người khác bằng path ID. Cần cả tập field được phép, authorization theo object, validation giá trị và invariant của operation.

## 7. Allowlist phải đi hết object graph

### 7.1. Nested entity là đường mở lại bề mặt ghi

Ví dụ một DTO nhìn có vẻ gọn nhưng vẫn nguy hiểm:

```java
public record EditDraftRequest(
    String title,
    List<PurchaseOrderLine> lines
) {}
```

Nếu `PurchaseOrderLine` có `unitPrice`, `approvedQuantity`, `tenantId` hoặc quan hệ `product.owner`, người gọi có thể thử gán vào những field đó. Root DTO không có `isAdmin` không chứng minh nested graph an toàn.

Mỗi node nhận dữ liệu cần schema/DTO phù hợp với command. Cho phép `lines` không đồng nghĩa cho phép mọi descendant của `lines`.

### 7.2. ID trong nested object chỉ là reference cần xác minh

Nếu use case cho client gửi line ID để sửa một dòng hiện có, phải kiểm tra line thuộc đúng parent và tenant, đồng thời xác định field nào được đổi trên dòng đó.

Nếu chỉ cần chọn sản phẩm, nhận `productId` rồi server tải sản phẩm hợp lệ. Không để object `product` client gửi được ORM merge như một sản phẩm mới hoặc bản cập nhật của catalog.

### 7.3. Cẩn thận với map mở rộng và metadata

Một trường `extensions` hoặc `metadata` có thể hợp lệ để lưu dữ liệu người dùng. Nhưng nó cần namespace, giới hạn kiểu/kích thước và cách dùng rõ ràng.

Không flatten metadata vào entity, trộn nó vào biến policy hoặc diễn giải key như `approvalRequired`, `role` hay đường dẫn property có thẩm quyền. Dữ liệu tùy biến vẫn là dữ liệu, không tự trở thành lệnh quản trị.

## 8. Phân biệt JSON body với form/model binding trong Spring

### 8.1. `@RequestBody` đi qua message converter

Spring đọc và deserialize `@RequestBody` thông qua `HttpMessageConverter`; `@Valid` có thể áp Bean Validation lên đối tượng đã tạo. Vì vậy bề mặt JSON cần được kiểm soát ở request type, converter/parser và mapping phù hợp. [Spring Framework: RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).

Không coi `@Valid` là allowlist field. Nó kiểm tra các constraint của object đã deserialize, không tự tuyên bố field nào là ý định nghiệp vụ hợp lệ.

Với hợp đồng strict của ví dụ, cấu hình và kiểm thử converter để từ chối unknown property cả ở root lẫn nested object, đồng thời xử lý duplicate key và coercion theo hợp đồng. Không giả định mọi cấu hình mặc định của framework/ứng dụng đều giống nhau.

Nếu một API chọn bỏ qua unknown field vì tương thích, việc bỏ qua không tự là mass assignment miễn field đó thật sự không được bind, map hoặc dùng về sau. Tuy nhiên, nó không cung cấp hành vi từ chối rõ của ví dụ và cần được kiểm chứng đến tận đường ghi.

### 8.2. Property binding của `@ModelAttribute` có cơ chế khác

Với một form DTO riêng chỉ chỉnh title/note/version, có thể giới hạn property binding:

```java
@InitBinder("editDraftForm")
void configureEditDraftForm(WebDataBinder binder) {
    binder.setAllowedFields("title", "requesterNote", "expectedVersion");
}
```

Đoạn này dành cho `WebDataBinder` và property binding của model/form tương ứng. Nó không tự trở thành allowlist deserialize JSON cho mọi `@RequestBody`.

Spring khuyến nghị model chuyên cho web binding hoặc constructor binding phù hợp; nếu dùng property binding thì cần giới hạn các property được gán bằng `allowedFields`. Phải xét cả nested graph và các tham số constructor được nhận. [Spring Framework: Model Design và InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html#webmvc-ann-initbinder-model-design).

Nếu yêu cầu từ chối field bị suppress, ứng dụng phải kiểm tra/xử lý kết quả binding phù hợp; việc field không được gán không mặc nhiên có nghĩa request đã bị trả lỗi.

### 8.3. Constructor binding chỉ an toàn với constructor có input đúng

Một form immutable chỉ nhận những field chỉnh sửa hợp lệ có thể giảm bề mặt property binding. Nhưng constructor nhận sẵn `approved`, `ownerId` hoặc `roles` từ request vẫn là một hợp đồng quá rộng cho action sửa nháp.

Đừng dùng “không có setter” hoặc một annotation serialization đơn lẻ như bằng chứng thay cho việc kiểm tra nguồn của từng field và mọi đường binding thực tế.

## 9. Partial update và JSON Patch cần allowlist riêng

### 9.1. Missing, null và giá trị rỗng không giống nhau

| Input trong partial update | Ý nghĩa cần định nghĩa |
| --- | --- |
| Không có field | Giữ nguyên hoặc không yêu cầu thay đổi |
| Field bằng `null` | Xóa giá trị nếu field cho phép, hoặc từ chối |
| Chuỗi rỗng | Một giá trị thật, có thể hợp lệ với note nhưng không hợp lệ với title |
| Array rỗng | Yêu cầu thay tập phần tử thành rỗng, chịu invariant tương ứng |

Một DTO chỉ dùng field nullable có thể không phân biệt được thiếu với null nếu adapter không giữ thông tin hiện diện. Có thể dùng kiểu biểu diễn thay đổi ba trạng thái như giữ nguyên/đặt giá trị/xóa, hoặc một định dạng patch được thiết kế rõ.

Không dùng cách merge tất cả field từ entity tách rời với giá trị mặc định, vì một field bị thiếu có thể làm mất cờ hoặc dữ liệu quan trọng.

### 9.2. JSON Patch không phải quyền sửa mọi path

JSON Patch mô tả một chuỗi operation tác động lên JSON document, với path và một số operation có cả nguồn `from`. Chuẩn đó định nghĩa cách sửa document, không định nghĩa actor được sửa property nghiệp vụ nào. [RFC 6902: JSON Patch](https://www.rfc-editor.org/rfc/rfc6902.html).

Nếu hỗ trợ patch cho nội dung nháp, cần giới hạn operation và path được phép theo profile API. Ví dụ chỉ patch một representation gồm title, note và cấu trúc dòng hàng được phép, sau đó chuyển kết quả thành command đã validate.

Không cho patch trực tiếp representation toàn bộ entity rồi chỉ kiểm tra vài field cuối cùng. Những điểm cần xem xét:

- Path được parse/canonicalize đúng quy tắc JSON Pointer; không chỉ dùng `startsWith("/lines")` để cho mọi nested field.
- `replace /lines` có thể mang một subtree chứa giá hoặc tenant; subtree vẫn phải theo schema allowlist.
- Nếu hỗ trợ `copy` hoặc `move`, cần xét quyền đọc nguồn và thay đổi đích, cùng invariant bị ảnh hưởng.
- `test` trên field bí mật có thể thành một phép dò giá trị; không mặc định mọi operation không ghi đều được phép.
- Các bước patch có thứ tự và có thể đổi vị trí array; policy cần đánh giá đúng target thực tế hoặc giới hạn representation đủ hẹp.

Toàn command phải được kiểm tra và áp nguyên tử theo hợp đồng. Không mutate entity đang managed sau từng operation rồi mới phát hiện một path bị cấm ở cuối.

## 10. Giữ allowlist qua mapper, persistence và xử lý nền

### 10.1. Explicit mapping tạo ranh giới thay đổi dễ rà soát

Thay vì tự động copy mọi property, có thể gọi các phương thức domain có chủ đích hoặc cấu hình mapping chỉ cho các trường đã chọn.

Nếu sau này DTO/entity có thêm `approvalRequired`, việc thêm field đó không nên tự làm nó đi từ payload đến database. Thay đổi contract/mapping phải được xem xét như thay đổi thẩm quyền input, không chỉ là bổ sung một property tiện dùng.

### 10.2. Domain method cần giữ đúng invariant

Một setter công khai `setState()` trong một utility generic có thể mở lại đường bỏ qua workflow. Domain operation như `submit`, `approve`, `replaceDraftContent` phải kiểm tra điều kiện riêng và không nhận một state đích tùy ý do client chọn.

Tương tự, creator/requester, ownership hoặc role không được thay theo một command sửa mô tả. Muốn thay quan hệ đó cần action có permission, binding dữ liệu và audit riêng.

### 10.3. Message và import không phải nguồn mặc định đáng tin

Một worker nhận JSON rồi `convertValue` thành entity có thể lặp lại cùng lỗi mass assignment của controller. Phải xác minh producer/scope, dùng schema command phù hợp và kiểm tra invariant ở application/domain boundary.

Các adapter có thể khác nhau về cách parse, nhưng không được khác nhau về việc field nào có thẩm quyền. Không thêm endpoint admin/import “cập nhật mọi field” rồi dùng nó cho request thông thường để vượt giới hạn của DTO chính.

### 10.4. Database không tự biết field nào caller được phép gửi

Enum, foreign key và `CHECK` có thể xác nhận dữ liệu hợp lệ về kiểu/quan hệ, nhưng `APPROVED` vẫn là một giá trị enum hợp lệ và một owner ID khác vẫn có thể là foreign key tồn tại.

Constraint hỗ trợ invariant lưu trữ, không thay cho command contract và authorization. Quyền database tối thiểu, state/version và các lệnh ghi có chủ đích vẫn cần được kết hợp.

## 11. Audit, idempotency và khả năng thay đổi an toàn

### 11.1. Ghi nhận field bị cấm mà không sao chép payload nhạy cảm

Có thể log action, actor/tenant đã xác minh, field/path bị từ chối ở mức cần thiết, reason code, request ID và version schema/policy. Giới hạn số path, độ dài và nội dung log để payload lồng sâu hoặc rất lớn không gây chi phí lần hai.

Không cần ghi nguyên token, dữ liệu riêng tư hoặc toàn bộ entity để chứng minh có field thừa. Client không có quyền trên object cũng không nên nhận lỗi chứa giá trị nội bộ của object đó.

### 11.2. Replay phải gắn với đúng command đã được chấp nhận

Fingerprint idempotency dùng semantic input đã được định nghĩa rõ cùng order ID/version và namespace tenant/principal/action. Không dùng một map raw rồi thực thi bằng DTO đã loại field theo quy tắc khác mà không có hợp đồng nhất quán.

Trong API strict của ví dụ, payload ngoài allowlist bị từ chối trước khi bước nghiệp vụ thực thi; không có thay đổi nhạy cảm nào được áp chỉ vì key từng hợp lệ.

Retry thành công trả receipt lịch sử theo policy quyền đọc, không chạy mapper lần nữa lên entity hiện tại. Nếu key dùng lại với nội dung khác, từ chối xung đột.

### 11.3. Thêm field là một thay đổi security contract

Khi bổ sung field vào command, cần chỉ rõ nguồn, người được nhập, giá trị cho phép, ảnh hưởng đến state/giá/quyền và các mapping đi xuống.

Một field xuất hiện trong response không có nghĩa phải có trong request. Không dùng chung read model và write command chỉ để giảm số class nếu chúng có thẩm quyền dữ liệu khác nhau.

Các field role-dependent hoặc nested mới cần được kiểm tra ở những adapter hiện có. Không chỉ cập nhật schema tài liệu mà bỏ quên converter, mapper hoặc đường import cũ.

## 12. Kiểm thử allowlist bằng payload đúng kiểu nhưng sai thẩm quyền

### 12.1. Baseline và tập field bị cấm

Bắt đầu bằng một request sửa draft hợp lệ, sau đó thêm lần lượt field nhạy cảm hoặc thay cấu trúc nested. Quan sát cả response và dữ liệu đã commit.

| Tình huống | Kết quả cần bảo đảm |
| --- | --- |
| Title/note/lines hợp lệ trên draft được phép | Chỉ nội dung được phép và dữ liệu server suy ra thay đổi |
| Thêm `approvalState`, `approvedBy`, `approvalRequired` | Không bỏ qua quy trình; API strict từ chối toàn command |
| Thêm tenant/owner/creator/requester trong body | Không đổi quan hệ có thẩm quyền qua action này |
| Thêm đơn giá/tổng tiền ở root hoặc line | Không ghi giá client vào dữ liệu có thẩm quyền |
| Field bị cấm có giá trị giống hệt hiện tại | Vẫn xử lý theo contract field, không mở đường gán về sau |
| Nested product/entity có field nội bộ | Không merge object graph ngoài allowlist |
| Line ID của parent hoặc tenant khác | Không attach/hijack child object |
| Product ID hợp lệ nhưng ngoài phạm vi | Bị authorization/reference policy chặn |
| Field thừa trong array item hoặc sâu trong object | Không chỉ kiểm tra root |
| Map metadata chứa tên field nhạy cảm | Không flatten hoặc diễn giải thành policy/domain property |
| DTO immutable/constructor có input nhạy cảm | Không coi thiếu setter là cơ chế bảo vệ đủ |
| JSON có unknown/duplicate field hoặc coercion bất ngờ | Hành vi đúng contract converter/parser được chọn |
| Form có property path ngoài `allowedFields` | Không gán property; nếu yêu cầu strict thì trả lỗi phù hợp |
| Chỉ đặt `@InitBinder` rồi gửi JSON `@RequestBody` | Kiểm thử xác nhận JSON có cơ chế bảo vệ riêng |
| Partial update thiếu/null/rỗng | Không vô tình xóa hoặc reset dữ liệu ngoài ý định |
| JSON Patch có path/from nhạy cảm hoặc subtree rộng | Không bypass allowlist qua path, copy/move/test hoặc replace cả object |
| Caller có role cao nhưng không quyền trên order | Không nhầm allowlist field với quyền object |
| Order không còn draft hoặc version cũ | Không sửa nội dung dựa trên kiểm tra lỗi thời |
| Lỗi mapper/persistence/audit/outbox | Không có phần cập nhật commit dở dang |
| Retry cùng key, nội dung khác | Không tái dùng kết quả như thể cùng command |
| Thêm field mới vào entity hoặc read DTO | Không tự mở thêm field ghi của command hiện có |
| Gửi cùng ý đồ qua message/import/mobile adapter | Cùng ranh giới input và invariant được giữ |

### 12.2. Quan sát biến đổi, không chỉ mã lỗi

Với payload bị từ chối, kiểm tra owner, tenant, creator, requester, approval state, giá, tổng tiền, child relationships và dữ liệu quyết định vẫn không bị đổi trái phép. Không được có outbox phê duyệt hoặc tác dụng ngoài chỉ vì binder/mapper đã chạy trước khi trả lỗi.

Với request hợp lệ, xác nhận các field chỉ server quản lý vẫn giữ nguồn đúng: actor từ xác thực, tenant từ context, giá từ catalog/policy và version tăng theo lần ghi thành công.

Với concurrency, dùng transaction thật để tạo trường hợp state/owner/version thay đổi trước lần ghi. Command có đúng allowlist vẫn cần quyền và precondition hiện tại.

Các DTO, khung Java và câu SQL trong bài là minh họa thiết kế; chúng chưa được chạy như một ứng dụng hoàn chỉnh.

## 13. Bài tập áp dụng

Một API đang dùng `UpdateOrderDto` chung cho sửa nháp, phê duyệt, chuyển owner và import. DTO có title, lines, owner, tenant, state, reviewer, total và một map metadata. Controller dùng một hàm copy property rồi gọi repository save.

Hãy thiết kế lại:

1. Tách những command nào theo ý định nghiệp vụ và liệt kê field client được phép gửi cho từng command.
2. Chỉ rõ nguồn server cho actor, tenant, ownership, giá, state và audit metadata.
3. Thiết kế nested DTO sao cho client chọn sản phẩm/số lượng nhưng không sửa catalog hoặc attach child object của người khác.
4. Định nghĩa hợp đồng JSON unknown/duplicate field, form binding và partial update nếu cần.
5. Viết mapping tường minh và domain operation thay cho copy toàn bộ property.
6. Giữ authorization, state/version, idempotency và transaction ở đâu để các adapter đều tuân cùng invariant?
7. Bổ sung kiểm thử chứng minh một field mới của entity/read model không tự trở thành quyền ghi mới.

Allowlist của command có giá trị khi nó tạo một ranh giới input rõ từ adapter đến domain và persistence. Chỉ dữ liệu đúng use case được phép đi qua ranh giới đó; giá trị có thẩm quyền được server xác định và mọi thay đổi vẫn phải thỏa quyền trên đối tượng cùng quy tắc nghiệp vụ tại lúc ghi.
