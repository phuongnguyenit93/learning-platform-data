# Ownership denial response: phản hồi khi không có quyền theo ownership

## 1. Từ chối đúng phải bảo vệ cả dữ liệu và hành động

Một người thay ID trên URL để sửa bản nháp của người khác. API trả lỗi, nhưng message ghi rõ tên chủ sở hữu, địa chỉ email và trạng thái bản nháp. Ở một phiên bản khác, API trả `403` sau khi đã cập nhật dữ liệu. Cả hai đều không phải hành vi từ chối an toàn.

**Ownership denial response** là cách hệ thống phản hồi và dừng xử lý khi người gọi không có quan hệ sở hữu hoặc căn cứ truy cập cần thiết đối với một đối tượng.

Một hợp đồng đầy đủ phải bảo đảm:

- Không thực hiện hành động nghiệp vụ mà người gọi chưa được phép.
- Không làm lộ đối tượng, chủ sở hữu hoặc dữ liệu ngoài phạm vi được biết.
- Không tự đổi owner, giả danh người khác hoặc dùng quyền service rộng hơn để hoàn thành request.
- Phân biệt được từ chối chính sách với tình trạng chưa thể đánh giá quan hệ.
- Có dấu vết phục vụ vận hành mà không đưa bí mật vào response hoặc log không được bảo vệ.

Trong bảo vệ logic nghiệp vụ, ownership chỉ là một trong các căn cứ phân quyền. Người là owner vẫn có thể không được tự duyệt, sửa hồ sơ đã chốt hoặc thực hiện lại một khoản chi. Ngược lại, người không phải owner vẫn có thể được xem hoặc thao tác qua một grant hợp lệ.

## 2. Khi nào thực sự phải từ chối?

### 2.1. Không phải owner chưa chắc không có quyền

Không nên triển khai mọi hành động bằng điều kiện:

```text
actorId khác ownerId → từ chối tất cả
```

Một policy có thể cho phép owner, thành viên team có vai trò phù hợp, người được chia sẻ quyền hoặc đại diện được xác minh. Quản trị viên cũng chỉ được phép trong phạm vi quản trị được thiết kế, không mặc định có mọi quyền.

Ví dụ:

| Quan hệ của người gọi | Xem | Sửa bản nháp | Chuyển owner | Duyệt |
|---|---|---|---|---|
| Owner trực tiếp | Có thể được phép | Có thể được phép | Theo quyền chuyển riêng | Không tự được phép; có thể bị cấm tự duyệt |
| Người được chia sẻ chỉ xem | Trong phạm vi grant | Không | Không | Không |
| Đại diện có quyền sửa | Theo phạm vi đại diện | Khi grant và trạng thái phù hợp | Không tự suy ra | Theo policy riêng |
| Không có quan hệ hay grant hợp lệ | Không nếu tài nguyên riêng tư | Không | Không | Không |

Bảng là ví dụ chính sách, không phải mặc định cho mọi ứng dụng.

Từ chối sau khi đã xét các căn cứ truy cập mà policy của hành động chấp nhận. Không dùng ownership để vô hiệu hóa một cơ chế chia sẻ hợp lệ, cũng không dùng quyền chia sẻ hẹp để mở rộng thành quyền owner.

### 2.2. Phân giải được và không có quyền khác với chưa đánh giá được

| Tình huống | Ý nghĩa | Hành vi với lệnh đang xin phép |
|---|---|---|
| Biết owner và biết actor không có quan hệ/grant cần thiết | Có căn cứ từ chối | Không thực hiện |
| Owner reference không hợp lệ | Dữ liệu không đủ để áp dụng policy bình thường | Không tự nhận người gọi làm owner |
| Không phân giải được principal hoặc membership bắt buộc | Chưa xác lập danh tính cần dùng | Không mở quyền mặc định |
| Kho quan hệ hoặc policy tạm thời lỗi | Chưa thể đánh giá điều kiện bắt buộc | Không thực hiện; báo lỗi phù hợp |
| Có grant hợp lệ cho action cụ thể | Không cần là owner trực tiếp | Tiếp tục kiểm tra trạng thái và nghiệp vụ |

Không dùng lỗi tải owner như một lý do kết luận “không có owner nên ai cũng được sửa”. Cũng không coi mọi timeout là một quyết định `NOT_OWNER` bình thường, vì điều đó che khuất sự cố vận hành.

## 3. Chọn phản hồi theo quyền được biết sự tồn tại

### 3.1. 401, 403 và 404 phục vụ những tình huống khác nhau

| Tình huống | Phản hồi thường dùng | Điều kiện áp dụng |
|---|---|---|
| Hành động cần danh tính nhưng người gọi chưa được xác thực hợp lệ | `401` | Theo hợp đồng cơ chế xác thực |
| Người gọi được biết đối tượng nhưng thiếu quyền hành động | `403` | Có thể giải thích ở mức thông tin được phép |
| Đối tượng riêng tư không tồn tại trong phạm vi được phép biết | `404` | Dùng nhất quán để che sự tồn tại ngoài quyền |
| Người có quyền đang thao tác trên version/owner revision đã cũ | `409` | Chỉ trả chi tiết sau kiểm tra quyền nhận thông tin |
| Dependency bắt buộc lỗi | Lỗi dịch vụ như `503` hoặc lỗi nội bộ phù hợp | Không tiết lộ dữ liệu đối tượng qua nội dung lỗi |

Một API đọc tài nguyên công khai có thể không cần đăng nhập. Không áp dụng `401` máy móc cho mọi request không có owner identity.

Với `401`, response cần phù hợp cơ chế xác thực của API. Không dùng nó để buộc người đã đăng nhập thử lại vô hạn khi nguyên nhân thực tế là không được phép trên đối tượng.

### 3.2. Ví dụ cho tài nguyên riêng tư

Giả sử policy quy định người ngoài phạm vi không được biết bản nháp có tồn tại hay không. Cả ID không tồn tại và ID của người khác có thể được phản hồi theo cùng hợp đồng:

```http
HTTP/1.1 404 Not Found
Content-Type: application/json
Cache-Control: no-store

{
  "code": "RESOURCE_NOT_AVAILABLE",
  "message": "Không tìm thấy tài nguyên trong phạm vi truy cập của bạn.",
  "correlationId": "req-4a81"
}
```

Không thêm `actualOwnerId`, email owner, tên tài liệu hoặc trạng thái xử lý của đối tượng vào response này.

### 3.3. Ví dụ khi được xem nhưng không được sửa

Một người có grant chỉ xem đã được phép biết đối tượng. Khi họ sửa, `403` với mã như `ACTION_NOT_ALLOWED` có thể phù hợp.

Thông báo có thể giải thích rằng quyền hiện tại không bao gồm thao tác sửa. Không cần tiết lộ cấu hình role nội bộ, danh tính người có thể cấp quyền hoặc toàn bộ danh sách người sở hữu.

Việc chọn `403` hay `404` phụ thuộc chính sách tiết lộ, không phải một công thức áp dụng giống nhau cho mọi đối tượng. Điều quan trọng là nhất quán giữa endpoint, response và dữ liệu được trả.

## 4. Ngăn rò rỉ qua body, header và các đường đọc phụ

### 4.1. Một thông báo lỗi có thể trở thành API dò dữ liệu

Các phản hồi sau làm lộ thông tin ngoài quyền:

```text
Bạn không phải chủ sở hữu. Hồ sơ này thuộc Nguyễn A.
Tài liệu tồn tại nhưng owner đang bị khóa.
Yêu cầu của phòng tài chính đang chờ thanh toán 80 triệu.
Hãy đăng nhập bằng email a***@company.example.
```

Ngay cả gợi ý email bị che một phần cũng có thể giúp liên kết đối tượng với một người. Chỉ cung cấp thông tin như vậy nếu policy chủ động cho phép, không dùng như chi tiết debug mặc định.

Một gợi ý chung như kiểm tra lại tài khoản hoặc liên hệ kênh hỗ trợ được công bố có thể đủ, không cần xác nhận tài khoản nào là owner.

### 4.2. Kiểm tra trước response có điều kiện và redirect tải tệp

Không chỉ bảo vệ response `200`. Các request `HEAD`, range download, truy vấn trạng thái, thumbnail và đường tải file cũng phải áp dụng quyền tương ứng.

Đặc biệt, không trả `304 Not Modified` hoặc redirect sang URL tải tệp chỉ vì ETag hay cache key khớp trước khi kiểm tra quyền hiện tại. Người dùng đổi account hoặc mất ownership không được dùng đường này để lấy lại nội dung riêng tư từ một ngữ cảnh không còn được phép.

Nếu dùng URL tải có thời hạn như một capability, cần mô tả phạm vi và khả năng thu hồi của chính URL đó. Một URL đã cấp có thể còn dùng được tới hạn nếu cơ chế không kiểm tra lại; đừng tuyên bố ownership được thu hồi tức thời trong khi vẫn phát capability độc lập còn hiệu lực.

### 4.3. Tìm kiếm, đếm và quan hệ cha–con

Một endpoint trả `404` an toàn vẫn có thể bị vượt về thông tin nếu endpoint tìm kiếm cho biết tên owner, endpoint đếm trả số lượng hoặc đường lấy dòng con bỏ qua quyền đối tượng cha.

Kiểm tra cả danh sách, gợi ý tìm kiếm, lịch sử, bằng chứng, export và trạng thái job. Quyền xem một dòng tổng quan không mặc định cho quyền tải toàn bộ tài liệu gốc.

### 4.4. Khác biệt response không chỉ nằm ở status

Nếu chủ động che sự tồn tại, xem xét cấu trúc lỗi, độ dài không cần thiết, header, link và thời gian xử lý có ý nghĩa. Không khẳng định đổi status sang `404` là đã loại bỏ mọi kênh suy đoán.

Không nhất thiết thêm một độ trễ cố định vào mọi lỗi. Ưu tiên thiết kế không tiết lộ dữ liệu, đường xử lý nhất quán và kiểm thử các khác biệt có thể khai thác trong hệ thống thực tế.

## 5. Không có tác động nghiệp vụ trong nhánh từ chối

### 5.1. Kiểm tra quyền trước khi mutation hoặc phát tác động

Một luồng đúng cần xác lập tenant, đối tượng, quan hệ và quyền hành động trước khi ghi thay đổi hoặc phát lệnh ra ngoài.

Không thực hiện theo thứ tự:

```text
cập nhật bản nháp
→ phát event
→ kiểm tra actor có phải owner không
→ trả 403
```

Response lỗi không thu hồi được event đã gửi hoặc lời gọi mạng đã chạy. Transaction cục bộ cũng không tự rollback mọi tác động bên ngoài.

### 5.2. Những ghi nào vẫn có thể hợp lệ?

Audit từ chối, bộ đếm rate limit hoặc dấu vết request có thể được ghi theo thiết kế. Do đó, điều cần kiểm chứng là không có thay đổi nghiệp vụ trái phép, không phải toàn bộ cơ sở dữ liệu bất biến.

Với một lệnh sửa bị chặn, các trường như trạng thái, owner, basis, nội dung nghiệp vụ và tập quyết định có hiệu lực phải giữ đúng bất biến. Không tự đổi owner về người gọi để “sửa lỗi quyền”.

### 5.3. Không fallback sang quyền rộng hơn

Sau khi bị chặn, không tự retry bằng service token, tài khoản quản trị hoặc chế độ bỏ kiểm tra owner. Đó là biến hệ thống thành bên thực hiện hộ hành động người gọi không có quyền.

Nếu có quy trình quản trị hoặc đại diện hợp lệ, nó phải là hành động có thẩm quyền và audit rõ ràng. Không suy ra quyền đó chỉ vì request gốc thất bại.

### 5.4. Không trả thành công giả

Với một lệnh đơn lẻ, trả `200` rồi bỏ qua cập nhật khiến client tưởng thay đổi đã được ghi. Trả “đã xếp hàng” trong khi biết người gọi không có quyền cũng gây hiểu sai nếu không có hợp đồng xử lý tương ứng.

Điều này khác với API danh sách chỉ trả các đối tượng được phép xem. Một danh sách rỗng có thể là truy vấn thành công hợp lệ; một lệnh sửa bị cấm cần outcome rõ ràng.

## 6. Minh họa Java cho lệnh bị che sự tồn tại

Ví dụ chọn policy: bản nháp riêng tư chỉ được sửa khi có quan hệ/grant phù hợp; người ngoài phạm vi không được biết đối tượng tồn tại. Các dependency là hợp đồng của ứng dụng, không phải API thư viện có sẵn.

```java
enum AccessResult {
    PERMIT, DENY, INDETERMINATE
}

DraftReceipt changePurpose(
        UUID routeTenantId,
        UUID expenseId,
        ChangePurposeCommand command) {

    Actor actor = identity.requireAuthenticatedActor();
    TenantContext context = tenantAccess.requireVerifiedContext(
            actor, routeTenantId);
    validateShape(command);

    return transactions.required(() -> {
        ExpenseRequest expense = expenses
                .lockByTenantAndId(context.tenantId(), expenseId)
                .orElseThrow(ResourceNotAvailable::new);

        AccessDecision decision = accessPolicy.evaluate(
                context, "EDIT_DRAFT_PURPOSE", expense);

        switch (decision.result()) {
            case PERMIT -> { }
            case DENY -> throw new ResourceNotAvailable();
            case INDETERMINATE -> throw new AuthorizationUnavailable();
        }

        expense.requireState(ExpenseState.DRAFT);
        expense.requireExpectedVersion(command.expectedVersion());

        int changed = expenses.updatePurpose(
                context.tenantId(), expense.id(), expense.version(),
                expense.ownerReference(), command.validatedPurpose());
        if (changed != 1) {
            throw new Conflict("CONCURRENT_MODIFICATION");
        }

        DraftReceipt result = new DraftReceipt(
                expense.id(), expense.version() + 1);
        audit.appendDraftChanged(context, expense, decision, result);
        return result;
    });
}
```

Các hợp đồng cần được triển khai đúng:

- Tenant context được xác minh phía server, không lấy role hoặc membership tự khai.
- Policy xét owner đã lưu, sharing/delegation hợp lệ và quyền action; không chỉ so một owner ID do body gửi.
- Không có nhánh cập nhật trước khi permit.
- Cập nhật ràng buộc tenant, ID, version, trạng thái và căn cứ owner phù hợp triển khai.
- Các lỗi làm rollback transaction theo hợp đồng; không catch rồi commit phần cập nhật.
- `ResourceNotAvailable` được map ra response che sự tồn tại theo policy này; ứng dụng khác có thể chọn `403` khi người gọi được biết đối tượng.
- Lỗi dependency được xử lý như không đủ căn cứ cho phép, không giả lập permit hoặc nuốt lỗi thành thành công.
- Audit từ chối nằm ở cơ chế phù hợp bên ngoài phần nghiệp vụ bị rollback; không cần tiết lộ owner thật trong response.

Tên kiểu và hàm chỉ biểu đạt hợp đồng. Cần kiểm thử để chứng minh repository, transaction và mapper thực sự giữ các điều kiện đó.

## 7. Ownership đổi giữa lúc kiểm tra và cập nhật

### 7.1. Một lần đọc không tạo quyền lâu dài

Giả sử An mở bản nháp khi đang là owner. Sau đó ownership chuyển cho Bình. Tab cũ của An gửi cập nhật.

Server phải áp dụng policy trên căn cứ hiện hành được bảo vệ, không tin cờ `isOwner` client đã nhận trước đó. Nếu policy không cho former owner sửa, lệnh phải bị chặn hoặc xung đột theo hợp đồng, không tự cập nhật dưới quyền cũ.

Khóa hoặc version cần bao phủ thay đổi ownership. Nếu quan hệ nằm ở bảng riêng, mọi đường sửa phải tham gia giao thức tương ứng.

### 7.2. Không lộ owner mới qua lỗi xung đột

Người dùng có thể cần được báo rằng dữ liệu không còn khả dụng hoặc trạng thái đã thay đổi. Điều đó không tự cho phép trả danh tính người nhận ownership mới.

Nếu sau chuyển chủ actor vẫn có quyền xem, có thể trả chi tiết phù hợp. Nếu mất quyền xem, xử lý lại theo chính sách tiết lộ; không mặc định mọi người từng là owner được biết mọi thay đổi sau này.

### 7.3. Cache và dữ liệu đã cấp trước đó

Cache quyền/response cần gắn đúng tenant, actor, action và phiên bản quan hệ cần thiết. Một permit cũ không được dùng quá cam kết độ mới sau chuyển owner hoặc thu hồi grant.

Server không thể thu hồi các byte đã được người dùng tải hợp lệ trước đó. Mục tiêu của kiểm soát hiện hành là ngăn truy cập hoặc tác động mới ngoài quyền, đồng thời quản lý cache client theo thiết kế để tránh hiển thị chéo account trên thiết bị dùng chung.

Không tuyên bố thu hồi tức thời nếu cache, token hay URL capability vẫn còn được chấp nhận mà không kiểm tra hiện hành.

## 8. Retry, idempotency, batch và công việc bất đồng bộ

### 8.1. Idempotency key không phải chứng chỉ ownership

Người biết key không được tự nhận response thành công của một chủ thể khác. Trước khi trả kết quả đã lưu, cần kiểm tra danh tính, tenant và quyền nhận kết quả theo hợp đồng hiện tại.

Nhánh replay không thực hiện lại mutation hoặc bắt trạng thái nguồn cũ còn nguyên như lệnh mới. Nhưng nó cũng không bỏ qua kiểm tra quyền truy cập.

Nếu owner đổi sau lần thành công, policy cần nói rõ former owner còn được nhận biên nhận cũ hay không, và được nhận những trường nào. Không trả nguyên snapshot nhạy cảm chỉ vì lần đầu họ từng có quyền.

### 8.2. Batch phải có outcome đúng từng phạm vi

Một batch có thể chứa đối tượng của người gọi, đối tượng được chia sẻ và ID ngoài quyền. Kiểm tra từng phần tử, không suy từ phần tử đầu.

Nếu toàn bộ hoặc không phần nào, lệnh bị chặn phải không để phần trước đã commit trái hợp đồng. Nếu xử lý từng phần, outcome cần rõ và lỗi của phần ngoài quyền không được tiết lộ owner hay xác nhận sự tồn tại ngoài chính sách.

### 8.3. Export, job status và artifact tải xuống

Một job export hợp lệ lúc được tạo không tự cho mọi người biết job ID được tải kết quả. Các đường xem trạng thái, hủy và tải artifact cần quyền tương ứng.

Cần xác định quyền dựa trên người yêu cầu job, owner tài nguyên hiện tại hay một grant đã được chấp nhận theo phạm vi rõ. Không để worker dùng quyền rộng rồi công khai artifact qua ID khó đoán.

### 8.4. Thao tác cũ đã phát sinh không được xóa khỏi lịch sử

Một request mới bị deny không chứng minh operation trước đó chưa thực hiện. Nếu thanh toán hoặc tác động ngoài hệ thống đã được gửi, service được cấp quyền vẫn phải đối soát theo workflow.

Không xóa operation hoặc tự hoàn tác chỉ vì ownership hiện tại đổi. Hành động bù trừ cần điều kiện và thẩm quyền riêng; quyền nhận kết quả của người gọi được kiểm tra tách biệt.

## 9. Trải nghiệm người dùng sau khi bị chặn

Thông báo nên ngắn, đúng hành động và không hứa rằng dữ liệu đã được lưu. Có thể cung cấp correlation ID để hỗ trợ tra cứu mà không nêu owner thật.

### 9.1. Không tạo quy trình xin quyền như tác dụng phụ ngầm

Nếu sản phẩm có chức năng yêu cầu truy cập, đó là một hành động riêng cần hợp đồng và giới hạn chống lạm dụng. Không tự gửi thông báo cho owner mỗi khi một người dò ID, vì việc đó có thể gây spam và lộ quan hệ.

Một đường hỗ trợ công khai có thể được hiển thị chung. Không nhất thiết trả tên hoặc email người có thể cấp quyền.

### 9.2. Giữ dữ liệu nhập của người dùng đúng phạm vi

Khi lệnh bị chặn, giao diện có thể giữ nội dung người dùng tự nhập để họ không mất công, nếu phù hợp chính sách thiết bị và dữ liệu. Không tự tải thêm dữ liệu riêng tư từ đối tượng để ghép vào một bản sao mới.

Không tự tạo đối tượng thay thế, chuyển owner hoặc ghi bản nháp vào tài nguyên khác để khiến lỗi biến mất. Những hành động đó cần ý định và quyền riêng.

### 9.3. Chuyển account hoặc tenant phải xác thực lại ngữ cảnh

Ứng dụng có thể cho người dùng chọn một account/tenant mà họ được phép dùng. Server vẫn đánh giá lại request với ngữ cảnh mới; không dùng gợi ý client như bằng chứng ownership.

Xóa hoặc phân vùng cache giao diện khi đổi account giúp tránh hiển thị nhầm dữ liệu đã tải. Đây là lớp hỗ trợ trải nghiệm, không thay kiểm tra server cho request tiếp theo.

## 10. Audit và quan sát từ chối

Log nội bộ có thể phân biệt đối tượng không có trong phạm vi, quan hệ không đạt, grant hết hiệu lực, mapping lỗi hoặc dependency không khả dụng. Response không cần chứa cùng mức chi tiết.

Các trường hữu ích gồm:

- Chủ thể thực tế, tenant đã xác minh và action.
- Tham chiếu đối tượng trong phạm vi dữ liệu được phép ghi.
- Owner/reference version và căn cứ quan hệ đã xét khi cần điều tra.
- Kết quả đánh giá, mã lý do, policy version và correlation ID.
- Có hay không một operation liên quan đã tồn tại từ trước.

Không log credential, token hoặc toàn bộ đối tượng chỉ để giải thích một lần bị chặn. Công cụ xem log cũng cần quyền phù hợp vì tham chiếu owner và quan hệ chia sẻ có thể là dữ liệu nhạy cảm.

### 10.1. Từ chối phải còn dấu vết sau rollback

Audit thành công có thể cùng transaction với thay đổi. Audit từ chối cần cơ chế phù hợp để không mất khi nghiệp vụ rollback.

Nếu audit lỗi, hành động không được phép vẫn phải không được thực hiện. Cách báo lỗi hoặc phục hồi log tùy yêu cầu vận hành, không được biến thành fallback allow.

### 10.2. Theo dõi dò ID và sai cấu hình

Nhiều lần truy cập ID ngoài quyền có thể là dò tài nguyên, nhưng cũng có thể do link cũ sau chuyển owner hoặc lỗi đồng bộ. Quan sát theo nhóm nguyên nhân giúp phân biệt.

Rate limit, tổng hợp log và cảnh báo cần bảo vệ tài nguyên vận hành. Không để việc giảm tải log thay đổi quyết định phân quyền hoặc che mất các sự kiện bắt buộc mà không có chủ ý.

## 11. Kiểm thử phản hồi và tác động

| Tình huống | Kỳ vọng |
|---|---|
| Người lạ đổi ID trên URL tới bản nháp riêng tư | Không xem/sửa được, không lộ owner |
| Không có credential cho hành động cần đăng nhập | Response xác thực đúng, không tác động |
| Người có grant chỉ xem thử sửa | Deny action, không nhầm thành owner |
| Đại diện có grant sửa hợp lệ | Luồng hợp lệ được phép, tránh chặn mọi non-owner |
| Người khác tenant dùng ID thật | Không lộ thông tin tenant/owner hoặc thay đổi dữ liệu |
| Mapping hoặc kho quan hệ lỗi | Không fallback owner hoặc allow |
| Client gửi `ownerId`, `isOwner`, `approvedBy` giả | Không thay căn cứ quyền phía server |
| HEAD, ETag/304, range hoặc redirect tải file | Không bỏ qua kiểm tra quyền qua đường phụ |
| Response cache dùng giữa hai account | Không trả dữ liệu/kết quả theo quyền của account khác |
| Owner đổi sau khi client mở trang | Không mutation theo quan hệ cũ trái cam kết |
| Replay sau khi mất quyền nhận kết quả | Không lộ response nhạy cảm chỉ vì key hợp lệ |
| Batch chứa ID không tồn tại và ngoài quyền | Outcome đúng hợp đồng, không tiết lộ khác biệt trái policy |
| Worker/export trả artifact qua job ID | Có kiểm tra quyền nhận kết quả phù hợp |
| Audit hoặc một ghi bắt buộc lỗi | Không commit phần nghiệp vụ trái phép |

### 11.1. So sánh phản hồi đúng cách

Khi policy che sự tồn tại, so sánh status và cấu trúc/nội dung được chuẩn hóa giữa trường hợp không tồn tại và ngoài quyền. Correlation ID có thể khác; không cần ép hai response giống từng byte khi có trường động hợp lệ.

Kiểm tra không có tên owner, email, title, số tiền, storage key hoặc URL riêng tư. Đánh giá khác biệt thời gian có ý nghĩa cần phương pháp phù hợp; một lần đo đơn lẻ không chứng minh không có side channel.

### 11.2. Kiểm tra business projection

Sau deny, xác nhận owner, state, version nghiệp vụ theo hợp đồng, nội dung, approval và operation không đổi trái phép. Kiểm tra không có event cho phép tác động được ghi ngoài ý muốn.

Không yêu cầu toàn bộ dữ liệu bất biến nếu audit/rate limit được ghi hợp lệ. Quan sát cổng gọi bên ngoài để phát hiện tác động đã gửi trước khi response lỗi.

### 11.3. Positive test và race có điều khiển

Cần owner hợp lệ và non-owner có grant hợp lệ thực hiện thành công trong phạm vi cho phép. Điều này phát hiện policy chặn quá rộng.

Điều khiển hai transaction đọc owner rồi chuyển owner/thu hồi grant để kiểm tra cam kết nhất quán. Với khóa, version và transaction, integration test trên loại cơ sở dữ liệu triển khai có ý nghĩa hơn chỉ mock một cờ `isOwner`.

## 12. Tự rà soát hợp đồng từ chối

Trước khi coi một endpoint đã bảo vệ ownership, hãy trả lời:

1. Quyền action có xét sharing/delegation hợp lệ hay chỉ kiểm tra owner trực tiếp?
2. Người gọi có được biết đối tượng và owner tồn tại không?
3. Status, body, header, conditional response và đường tải phụ có giữ cùng chính sách tiết lộ không?
4. Nhánh deny có thực sự không mutation, không phát event và không gọi tác động ngoài hệ thống không?
5. Mapping thiếu hoặc dependency lỗi có thể vô tình trở thành allow không?
6. Thay owner, cache, replay và job bất đồng bộ có mở đường dùng quyền cũ không?
7. UI có báo đúng là thao tác chưa thành công, không tự chuyển chủ hay nâng quyền không?
8. Audit có đủ dấu vết sau rollback mà không công khai dữ liệu nhạy cảm không?

Phản hồi từ chối ownership đúng nghĩa phải dừng hành động chưa được phép và chỉ tiết lộ thông tin người gọi có quyền biết. Điều đó cần được giữ qua mọi đường đọc, ghi, gửi lại và xử lý bất đồng bộ, không chỉ ở một mã lỗi HTTP.
