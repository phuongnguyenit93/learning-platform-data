# Batch result disclosure: kiểm soát dữ liệu được công bố từ kết quả batch

## 1. Mục tiêu bài học

Trong chương **Batch Operations** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **batch result disclosure** là việc quyết định thông tin nào của một lô xử lý được phép trả cho từng caller.

Một batch có thể chứa nhiều đối tượng, thuộc các scope hoặc trạng thái khác nhau. Kết quả không chỉ gồm các bản ghi thành công, mà còn có mã lỗi, thông tin tồn tại, tổng tiền, số lượng, thứ tự, cursor, đường dẫn tải và dữ liệu phục vụ retry.

Nếu chỉ bảo vệ endpoint submit nhưng trả toàn bộ kết quả nội bộ, hệ thống có thể làm lộ dữ liệu ngoài quyền ngay cả khi không thực hiện thay đổi trái phép.

Sau bài học, bạn có thể:

- Phân biệt quyền gửi batch, thực thi từng item, xem tiến độ và đọc kết quả chi tiết.
- Thiết kế kết quả từng item mà không làm lộ sự tồn tại hoặc trạng thái đối tượng ngoài scope.
- Giữ summary, pagination, metadata và export trong cùng biên dữ liệu được phép.
- Công bố trung thực kết quả commit, rollback, pending và chưa xác định.
- Xử lý quyền thay đổi sau khi batch đã chạy mà không phục hồi quyền cũ qua receipt/cache.
- Kiểm thử kết quả batch như một bề mặt đọc dữ liệu độc lập.

## 2. Kết quả batch là một tài nguyên có quyền riêng

Ví dụ một API nhận danh sách refundId để approve. Caller được phép thao tác một số refund, nhưng gửi thêm ID khác.

Server có thể đã chặn các item không hợp lệ. Tuy nhiên, response sau vẫn có thể làm lộ dữ liệu:

~~~json
{
  "results": [
    {
      "inputId": "refund-1",
      "status": "APPROVED",
      "amountMinor": 400000
    },
    {
      "inputId": "refund-2",
      "status": "FORBIDDEN",
      "ownerEmail": "owner@example.test",
      "tenantName": "Tổ chức khác",
      "currentState": "PAID",
      "amountMinor": 9000000
    },
    {
      "inputId": "refund-3",
      "status": "NOT_FOUND"
    }
  ]
}
~~~

Caller ngoài quyền có thể biết refund-2 tồn tại, thuộc tổ chức nào, ai phụ trách, đã chi trả và có số tiền bao nhiêu. Chỉ riêng sự khác nhau giữa FORBIDDEN và NOT_FOUND cũng có thể tạo khả năng dò đối tượng, nếu chính sách không cho phép biết sự tồn tại.

### 2.1. Không chỉ field dữ liệu mới làm lộ thông tin

Các dạng công bố khác:

| Bề mặt | Thông tin có thể bị suy ra |
|---|---|
| Mã lỗi từng item | Tồn tại, trạng thái hoặc bước đã qua |
| Summary | Số item đã chi trả, số tiền, phân loại rủi ro |
| Thứ tự | Xếp theo amount, tenant hoặc trạng thái nội bộ |
| Số dòng/pagination | Số đối tượng thực sự khớp trong dữ liệu ngoài quyền |
| Cursor/link | ID hoặc ngữ cảnh truy vấn của đối tượng bị che |
| Header/cache metadata | Dữ liệu bị che có thay đổi hay không |
| File export | Toàn bộ kết quả thô dù UI đã lọc |
| Retry hint | Item đã chạy, chưa chạy hoặc có thể tạo thêm hiệu ứng |
| Notification | Tên/giá trị/đối tượng nằm trong phần batch ngoài quyền |

Không thể kết luận response an toàn chỉ vì đã bỏ một field amount khỏi JSON.

### 2.2. Batch owner không tự là owner của mọi item

Người tạo batch thường cần biết công việc của mình đang tiến triển. Điều đó không có nghĩa họ được đọc toàn bộ object mà họ đưa ID vào.

Một service có thể được giao xử lý rộng, còn người gửi chỉ được xem một projection hẹp. Ngược lại, một người có quyền đọc dữ liệu chưa chắc được submit batch approve hoặc execute.

Từng quan hệ cần được xác định riêng.

## 3. Tách các loại quyền

Một mô hình có thể định nghĩa:

| Quyền | Ý nghĩa minh họa |
|---|---|
| BATCH_SUBMIT | Tạo một batch thuộc loại hành động được phép |
| BATCH_STATUS_READ | Xem metadata/tiến độ của job trong scope |
| BATCH_ITEM_EXECUTE | Thực hiện action trên một item đủ điều kiện |
| BATCH_ITEM_RESULT_READ | Xem kết quả chi tiết của item theo object/field scope |
| BATCH_RESULT_EXPORT | Xuất tập dữ liệu kết quả trong phạm vi được cấp |
| BATCH_OPERATE | Hỗ trợ vận hành như tạm dừng hoặc phục hồi theo quyền riêng |

Tên quyền tùy sản phẩm. Điểm chính là không gộp chúng thành một cờ isBatchOwner.

### 3.1. Redact kết quả không sửa được lỗi thực thi

Một pipeline đúng cần bảo vệ cả hai phía:

~~~text
Trước hiệu ứng:
  kiểm tra tenant, action, object scope, trạng thái và bất biến từng item;
  kiểm tra ràng buộc tổng của batch nếu có.

Khi trả kết quả:
  kiểm tra quyền đọc batch;
  chọn dữ liệu item/field được công bố;
  dựng summary, link và export theo cùng chính sách.
~~~

Không được thực thi mọi item bằng một service account rộng rồi chỉ che những kết quả caller không được phép xem.

### 3.2. Quyền tại thời điểm chạy và quyền tại thời điểm đọc

Batch có thể chạy lúc reviewer còn quyền. Sau đó reviewer bị thu hồi hoặc chuyển scope trước khi tải kết quả.

Cần phân biệt:

- Bằng chứng nội bộ về quyền và dữ liệu lúc thực thi.
- Quyền hiện tại để đọc kết quả.
- Quy tắc lưu giữ/quyền truy cập lịch sử mà sản phẩm đã cấp rõ ràng.

Trong chính sách minh họa của bài, kết quả công khai được dựng theo quyền xem hiện tại. Audit nội bộ vẫn giữ lịch sử thực thi và không bị viết lại.

Nếu một sản phẩm chủ ý cấp quyền đọc receipt lịch sử có hiệu lực độc lập, phải mô hình hóa nguồn quyền đó; không mặc định người tạo batch giữ quyền mọi dữ liệu mãi mãi.

## 4. Phân loại dữ liệu trước khi trả kết quả

Một cấu trúc nội bộ có thể gồm:

~~~text
Batch:
  tenant, initiator, action, manifest, lifecycle, policy/evidence

Item:
  clientItemKey, input reference, canonical resource
  operationId, commit evidence, execution outcome
  domain state, amount, recipient, error details

Delivery:
  progress, summary, cursor, export artifact, retry links
~~~

Mỗi thành phần có một mức nhạy cảm và quyền đọc riêng.

### 4.1. Client item key khác canonical resource ID

clientItemKey giúp caller ghép kết quả với item họ đã gửi. Nó không chứng minh item tồn tại hoặc caller có quyền.

Có thể trả lại key của input ngay cả khi không công bố canonical resource. Nhưng cần giới hạn kiểu/kích thước, xử lý nó như dữ liệu và không dùng nó để chọn quyền.

Không phản chiếu một field do client gửi như thể đó là owner/tenant có thẩm quyền.

### 4.2. Echo dữ liệu đầu vào không nên bị hiểu là kết quả lookup

Nếu API trả inputId nguyên như caller gửi, phải phân biệt nó với canonicalResourceId hoặc resolvedOwner.

Việc canonical hóa alias, trả ID chuẩn hoặc thêm tên đối tượng có thể tiết lộ điều caller chưa biết. Một placeholder theo clientItemKey thường dễ kiểm soát hơn khi cần che kết quả lookup.

### 4.3. Dữ liệu nội bộ không tự là response DTO

Không serialize toàn bộ BatchItemEntity hoặc exception xuống client rồi chỉ xóa một vài field.

Nên có public result model được dựng theo policy. Những trường cần cho audit/worker không tự trở thành trường được phép tải xuống.

## 5. Thiết kế result model theo quyền công bố

### 5.1. Tách disclosure state và execution outcome

Hai câu hỏi khác nhau:

~~~text
Caller được xem gì về item này?
Item thực sự đã được xử lý tới đâu?
~~~

Một mô hình có thể có:

| Chiều | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| Disclosure | DETAILED | Được trả projection chi tiết đã cho phép |
| Disclosure | RECEIPT_ONLY | Chỉ được biết phần receipt được policy cấp riêng |
| Disclosure | UNAVAILABLE | Không công bố chi tiết cho caller này |
| Execution | SUCCEEDED | Hiệu ứng được xác nhận thành công theo hợp đồng action |
| Execution | NOT_APPLIED | Không áp dụng/đã rollback với căn cứ phù hợp |
| Execution | FAILED | Operation kết thúc không đạt mục tiêu theo định nghĩa cụ thể |
| Execution | PENDING | Chưa có kết quả cuối |
| Execution | UNKNOWN | Chưa xác định được kết quả, cần tra cứu/đối soát |

Không gắn outcome=FAILED cho mọi item bị che. Item đã chạy thành công lúc caller còn quyền vẫn có thể hiện UNAVAILABLE khi đọc sau đó.

UNKNOWN là thông tin kết quả thực thi dành cho người được phép biết; nó không đồng nghĩa thiếu quyền xem.

### 5.2. Ví dụ response theo manifest đã gửi

Giả sử caller được xem batch và biết ba client item key mình đã gửi. Chỉ item thứ nhất được phép trả chi tiết; hai item còn lại không được công bố sự tồn tại/trạng thái.

~~~json
{
  "batchId": "batch-31",
  "jobState": "COMPLETED",
  "submittedItemCount": 3,
  "summaryBasis": "DISCLOSED_ITEMS_ONLY",
  "visibleSummary": {
    "detailedItemCount": 1,
    "succeeded": 1,
    "notApplied": 0,
    "failed": 0,
    "pending": 0,
    "unknown": 0
  },
  "items": [
    {
      "clientItemKey": "row-1",
      "view": "DETAILED",
      "outcome": "SUCCEEDED",
      "resource": {
        "type": "REFUND",
        "id": "refund-1"
      },
      "result": {
        "state": "APPROVED"
      }
    },
    {
      "clientItemKey": "row-2",
      "view": "UNAVAILABLE",
      "message": "Không có kết quả chi tiết để hiển thị."
    },
    {
      "clientItemKey": "row-3",
      "view": "UNAVAILABLE",
      "message": "Không có kết quả chi tiết để hiển thị."
    }
  ]
}
~~~

Trong ví dụ:

- submittedItemCount đến từ manifest caller đã nộp, không từ số resource tìm thấy trong DB.
- jobState=COMPLETED chỉ nói job đã kết thúc xử lý theo hợp đồng, không nói mọi item thành công.
- visibleSummary chỉ tổng hợp các kết quả được công bố trong phạm vi đã định nghĩa.
- UNAVAILABLE không xác nhận resource tồn tại, không nói đã chạy và không hướng dẫn tạo một ý định mới.

Đây là schema minh họa, không phải định dạng bắt buộc.

### 5.3. Placeholder không được mang lỗi nội bộ

Nếu policy cần che cả sự tồn tại, các trường hợp như không tồn tại, ngoài scope hoặc không đủ điều kiện công bố phải không bị phân biệt bằng:

~~~text
public error code
message
canonical resource ID
owner/tenant
state, amount hoặc operation link
độ chi tiết của nested error
~~~

Không bỏ ownerEmail rồi vẫn trả code=ALREADY_PAID cho một đối tượng ngoài quyền.

RECEIPT_ONLY chỉ dùng khi policy thực sự cấp quyền biết phần receipt đó. Nó không phải cách vòng để công bố outcome của một resource mà caller không được biết tồn tại.

### 5.4. Có thể dùng chính sách khác, nhưng phải rõ ngữ nghĩa

Các lựa chọn có thể gồm:

- Trả một dòng theo mỗi input với placeholder an toàn.
- Chỉ trả các dòng được công bố, với pagination/summary theo tập đó.
- Từ chối cả request bằng một lỗi chung theo hợp đồng all-or-nothing.

Không trộn các lựa chọn tùy từng lý do nội bộ mà không kiểm soát. Nếu item bị bỏ khỏi response, client không được tự suy ra item chưa chạy hoặc cần retry.

Một lỗi cú pháp của input có thể được chỉ ra bằng vị trí caller đã gửi. Điều đó khác công bố facts được lookup từ resource ngoài quyền.

## 6. Kết quả phải trung thực về transaction

### 6.1. Không công bố success tạm thời trước commit

Trong batch all-or-nothing:

~~~text
Item A qua kiểm tra và được sửa trong transaction.
Item B làm transaction rollback.
~~~

Kết quả cuối không được giữ A=SUCCEEDED từ một danh sách được dựng trước commit.

Item được phép công bố có thể nhận NOT_APPLIED/BATCH_ROLLED_BACK theo hợp đồng. Không cần tiết lộ một resource ngoài quyền đã gây rollback nếu điều đó vượt chính sách.

### 6.2. Batch từng phần cần outcome từng item

Với hợp đồng từng phần, một số item có thể đã commit còn số khác bị từ chối hoặc đang chờ.

Không nói toàn batch “không có gì xảy ra” chỉ vì response có lỗi. Cũng không nói “mọi item thành công” chỉ vì job đã hoàn tất vòng lặp.

Kết quả từng item phải gắn với bằng chứng đúng operation/transaction, không suy từ thứ tự xử lý hoặc một boolean chung.

### 6.3. Hiệu ứng ngoài có thể còn chưa biết

Một worker gọi nhà cung cấp rồi timeout không có căn cứ tự ghi NOT_APPLIED. Người được phép xem chi tiết có thể thấy PENDING/UNKNOWN/RECONCILING theo hợp đồng.

Điều đó không cho phép trả mọi chi tiết nhà cung cấp, tài khoản hoặc người nhận. Truthfulness và disclosure đều phải được giữ.

## 7. Summary là một truy vấn dữ liệu có quyền riêng

### 7.1. Tổng hợp từ đúng tập và đúng field

Một cách tiếp cận cho chính sách mẫu:

~~~text
Kết quả nội bộ
    → đánh giá disclosure từng item/field
    → public item views
    → summary theo các views được phép
~~~

Không tính totalAmount trên mọi item rồi mới xóa amount khỏi từng dòng.

Nếu một số amount không được công bố, ngay cả summary của các dòng nhìn thấy cũng cần policy riêng cho field số tiền. Được xem state không tự có quyền xem amount.

### 7.2. Tránh phép trừ làm lộ phần bị che

Ví dụ caller thấy:

~~~text
Tổng batch toàn cục = 100 triệu.
Tổng các dòng được xem = 20 triệu.
~~~

Họ có thể suy ra 80 triệu thuộc phần bị che.

Tương tự, global counts theo PAID, REJECTED, risk level hoặc tenant có thể làm lộ trạng thái dù từng dòng đã redact.

Nếu có quyền báo cáo tổng hợp độc lập, phải cấp và kiểm soát rõ. Không mặc định dữ liệu tổng hợp luôn an toàn; bộ lọc nhỏ hoặc các truy vấn lặp có thể làm suy ra từng đối tượng.

### 7.3. Đếm input không phải đếm resource tồn tại

Caller đã gửi 100 item có thể được biết submittedItemCount=100 theo policy của job.

Điều đó không tự cho phép trả matchedResourceCount=87, forbiddenCount=10 và notFoundCount=3 nếu các số đó tiết lộ facts ngoài quyền.

Đặt tên và tài liệu hóa đúng basis: manifest đã nộp, các dòng được công bố, trang hiện tại hay một tập báo cáo được cấp riêng.

Không để UI dùng visibleSummary.failed=0 để hiển thị “toàn bộ batch thành công” khi còn item UNAVAILABLE.

## 8. Thứ tự, pagination và metadata cũng phải theo disclosure

### 8.1. Giữ correlation không dùng thuộc tính bí mật

Nếu response vẫn chứa một placeholder cho mỗi input, có thể giữ thứ tự manifest hoặc client item key.

Không sắp toàn bộ item theo amount/owner/risk rồi mới che field. Vị trí của các dòng có thể làm lộ thông tin từ tiêu chí sắp xếp.

Nếu cho sort/filter theo dữ liệu nghiệp vụ, chỉ dùng trong phạm vi mà caller được quyền sử dụng các thuộc tính đó theo chính sách.

### 8.2. Cursor phải bị ràng buộc với view hợp lệ

Cursor cần được kiểm chứng theo hợp đồng, có thể gắn với:

~~~text
batch và tenant
caller hoặc phạm vi view được cấp
query/filter/sort
result snapshot/version
permission/projection version nếu cần
purpose và thời hạn
~~~

Một cursor do một operator rộng quyền nhận không được mở trang dữ liệu đó cho người khác.

Khi quyền/view thay đổi, có thể yêu cầu bắt đầu lại hoặc dựng cursor mới. Không fallback về truy vấn mọi item nếu cursor không còn dùng được.

### 8.3. Count của pagination phải dùng đúng basis

Với view chỉ trả dòng được phép, total/count phải phản ánh đúng tập được công bố hoặc một hợp đồng được cấp riêng, không phải mọi match trong kho kết quả thô.

Với view theo manifest có placeholder, số trang có thể dựa trên manifest mà caller đã biết. Nó không được vô tình thay đổi theo việc resource bí mật có tồn tại hay không.

Không lấy một trang rộng rồi lọc tùy tiện mà vẫn trả total của tập rộng như thể đó là total của view.

### 8.4. Header và cache metadata không được lấy từ dữ liệu thô trái policy

Nếu public view không được tiết lộ thay đổi ở phần bị che, không dựng ETag hoặc thời điểm sửa đổi chỉ từ toàn bộ internal result rồi coi nó vô hại.

Cache/public metadata cần tương ứng với representation được phép hoặc một lifecycle field được policy cấp rõ.

Điều này không phải lời hứa mọi thời gian phản hồi đều giống nhau. Cần nhận diện và kiểm soát những tín hiệu quan sát nằm trong hợp đồng của hệ thống.

## 9. Dựng public projection ở server

### 9.1. Tách internal result khỏi public view

Một pipeline đọc có thể là:

~~~text
Xác thực caller và tenant.
Kiểm tra quyền đọc envelope/manifest của batch.
Kiểm chứng query và cursor.
Nạp trang manifest/kết quả trong đúng batch và tenant.
Lấy facts quyền hiện tại theo cam kết của hệ thống.
Chọn view và field cho từng item.
Dựng summary/link/metadata từ dữ liệu được phép.
Trả public DTO.
~~~

Không cho client truyền allowedFields, isAdmin hoặc canViewAll rồi dùng chúng như quyết định quyền.

Một query do caller yêu cầu có thể thu hẹp view, không tự mở rộng phạm vi được cấp.

### 9.2. Java minh họa

Mã dưới đây là phác thảo với các service giả định, không phải chương trình độc lập. Chính sách mẫu phân trang theo manifest caller được phép thấy và trả placeholder cho item không được công bố.

~~~java
PublicBatchView readResults(
        Actor actor, BatchResultQuery query) {

    var batch = batches.findInTenant(
            actor.tenantId(), query.batchId())
            .orElseThrow(NotFound::new);

    batchAccess.requireCanReadResultEnvelope(actor, batch);

    var disclosureContext = disclosureFacts.requireForRead(
            actor, batch);
    var page = manifests.readAuthorizedPage(
            batch, query, disclosureContext);

    var internalResults = results.findForManifestKeys(
            batch.tenantId(), batch.id(), page.itemKeys());

    var publicItems = new ArrayList<PublicItemView>();

    for (var entry : page.entries()) {
        var internal = internalResults.forEntry(entry);
        var viewSpec = disclosure.chooseView(
                actor, batch, entry,
                internal, disclosureContext);

        var itemView = switch (viewSpec.kind()) {
            case DETAILED -> projector.allowedDetails(
                    entry, internal, viewSpec);
            case RECEIPT_ONLY -> projector.allowedReceipt(
                    entry, internal, viewSpec);
            case UNAVAILABLE -> PublicItemView.unavailable(
                    entry.clientItemKey());
        };

        publicItems.add(itemView);
    }

    var summary = summaries.fromDisclosedViews(
            publicItems, disclosureContext.summaryPolicy());
    var nextCursor = cursors.forPublicContinuation(
            page, batch, disclosureContext);

    return batchProjector.publicEnvelope(
            batch, page, publicItems,
            summary, nextCursor, disclosureContext);
}
~~~

### 9.3. Các helper phải giữ đúng hợp đồng

- Quyền đọc envelope bao gồm phần manifest/key/metadata được trả, không mặc định mọi caller biết toàn bộ manifest.
- Query/cursor không được chuyển từ batch này sang batch khác hoặc mở rộng scope.
- chooseView dựa trên dữ liệu quyền có thẩm quyền và policy, không một flag do item/input tự khai.
- allowedDetails cũng kiểm tra field và lý do lỗi; không trả nguyên entity khi item đạt một điều kiện boolean.
- allowedReceipt chỉ công bố phần receipt được cấp riêng.
- unavailable không chứa outcome hoặc canonical resource ngoài quyền.
- Summary dùng đúng basis, không đọc trở lại mọi amount từ internalResults.
- batchProjector chỉ công bố lifecycle/count của job theo quyền envelope.

Facts quyền không đủ để kết luận phải dẫn tới lỗi hoặc view hạn chế theo hợp đồng, không tự chuyển thành cho phép đầy đủ.

### 9.4. Không mutate entity để redact

Mẫu xử lý “đặt amount=null trên entity rồi serialize” có thể làm mất dữ liệu nội bộ hoặc tạo thay đổi ngoài ý định nếu entity được theo dõi persistence.

Dựng public DTO riêng. Internal results vẫn giữ bằng chứng thực thi theo quyền lưu trữ của hệ thống.

Redaction là thao tác công bố dữ liệu, không phải sửa lịch sử batch.

### 9.5. Snapshot quyền cho một lần đọc phải có thời điểm rõ

Một trang kết quả cần được dựng từ ngữ cảnh quyền nhất quán đủ cho hợp đồng.

Nếu membership/scope thay đổi, server cần cơ chế độ mới và thu hồi tương ứng. Transaction đọc cục bộ không tự khóa được nguồn quyền bên ngoài.

Với stream dài, cần quy định lúc nào quyền được đánh giá và cách ngắt/giảm view nếu yêu cầu thu hồi trong quá trình stream. Không hứa thu hồi dữ liệu đã gửi cho caller.

## 10. Cache, receipt và các lần đọc sau

### 10.1. Không trả lại nguyên response rộng quyền đã cache

Một người có thể đã được xem toàn bộ chi tiết khi batch hoàn tất nhưng sau đó mất scope.

Nếu policy là kiểm tra quyền đọc hiện tại, không phục vụ nguyên JSON cũ chỉ vì batchId và userId vẫn giống nhau.

Cache phải phản ánh các phụ thuộc như tenant, caller/view scope, query/projection, phiên bản quyền và kết quả; hoặc cache dữ liệu nguồn rồi dựng view theo policy hiện tại.

Tên role giống nhau cũng không đủ để chia sẻ response cache giữa hai người có object scope khác nhau.

### 10.2. Idempotency của hiệu ứng không bắt buộc view bất biến

Receipt có thể liên kết tới kết quả nội bộ ổn định của command. Khi caller đọc lại, projection có thể hẹp hơn do quyền thay đổi.

Điều này không làm hiệu ứng nghiệp vụ bị thực hiện lại. Idempotency bảo vệ ý định/hiệu ứng, không phải quyền đọc toàn bộ body cũ vô thời hạn.

Nếu hợp đồng cấp quyền đọc một receipt lịch sử độc lập, phải đánh giá đúng grant đó. Không coi việc biết key là quyền.

### 10.3. Operation link và endpoint chi tiết phải cùng scope

Không đủ khi page batch đã che một item nhưng vẫn kèm:

~~~text
/internal-operations/{id}
errorDetailUrl
downloadRawResultUrl
retryToken có dữ liệu giải mã được
~~~

Endpoint theo link phải có kiểm tra riêng. Nếu caller không được biết item tồn tại, chính link hoặc ID liên quan cũng có thể là một phần tiết lộ.

Không để cursor hay operationId trở thành đường tắt bỏ kiểm tra tenant/batch/item.

## 11. Export và notification phải dùng cùng chính sách

### 11.1. UI đã lọc không bảo vệ được file thô

Một file chứa mọi internal item, amount, owner và exception vẫn làm lộ dữ liệu dù bảng trên UI chỉ hiện placeholder.

BATCH_RESULT_EXPORT cần quyền xuất và phạm vi row/column tương ứng. Quyền export không tự có scope toàn nền tảng.

Có thể dựng file từ cùng public projection hoặc một export projection được cấp riêng. Nếu export rộng hơn UI, quyền đó phải được thể hiện rõ.

### 11.2. Kiểm tra ở lúc tạo và lúc tải theo hợp đồng

File có thể được tạo lúc caller còn quyền nhưng được tải sau khi quyền bị thu hồi.

Các lựa chọn có thể gồm:

- Xác minh quyền hiện tại vẫn bao phủ manifest/field của artifact.
- Dựng lại file theo view hiện tại.
- Từ chối artifact cũ và yêu cầu xuất lại.
- Dùng capability tải có thời hạn/thu hồi theo chính sách được đặc tả.

Không chỉ kiểm tra người dùng là batch owner rồi cấp mọi file liên quan.

Nếu link đã cấp không có cơ chế thu hồi tức thời, không tuyên bố xóa quyền UI sẽ vô hiệu hóa ngay mọi bản link.

### 11.3. Tên file và thông báo cũng là output

Tên file, subject notification, đường dẫn lưu và progress message có thể chứa tên khách hàng, tenant hoặc số tiền ngoài quyền.

Dùng cùng nguyên tắc tối thiểu cần biết. Không gửi thông báo đầy đủ về các item bị che chỉ để báo “batch đã xong”.

Notification nên dẫn tới một view được xác thực, không đính kèm raw result rộng quyền theo mặc định.

## 12. Retry từ kết quả mà không tạo hiệu ứng mới ngoài ý định

### 12.1. Không retry mọi dòng không hiện SUCCEEDED

Một item có thể:

~~~text
UNAVAILABLE vì policy không công bố.
PENDING vì đang xử lý.
UNKNOWN vì chưa xác định hiệu ứng.
SUCCEEDED nhưng chi tiết không còn được xem.
~~~

Nếu client chọn mọi item “không có success” để tạo batch mới, nó có thể gửi lại ý định đã chạy.

Retry UI cần dựa trên kết quả được phép biết và hợp đồng recovery. Server vẫn phải tự xác minh trạng thái nội bộ, quyền hiện tại và idempotency.

### 12.2. Retry endpoint không tin result do client gửi lại

Không nhận một JSON item có outcome=FAILED hoặc canRetry=true rồi thực thi lại vì client nói vậy.

Client chỉ đề nghị target/operation gốc theo hợp đồng. Server nạp kết quả và state có thẩm quyền, kiểm tra action, scope, retryability và định danh hiệu ứng.

Một retry token, nếu có, cần đúng tenant/batch/item/purpose và hiệu lực; nó không thay mọi kiểm tra nghiệp vụ.

### 12.3. Giữ identity của ý định gốc

Một operation chưa rõ kết quả phải được tra/tiếp tục với định danh ổn định theo giao thức. Đổi batchId hoặc tạo key mới không chứng minh lần trước chưa xảy ra.

Nếu nghiệp vụ có business key chống trùng xuyên batch, phải giữ và kiểm tra nó. Chỉ chống trùng trong một batch không bao phủ một batch mới chứa cùng ý định.

Khi retry hợp lệ tạo attempt mới, kết quả và audit cần liên kết attempt cũ, không ghi đè lịch sử như thể chưa từng có timeout hoặc rollback.

## 13. Audit disclosure khác audit execution

Có thể cần hai chuỗi bằng chứng:

~~~text
Execution:
  ai được phép thực hiện gì,
  trên snapshot nào,
  kết quả commit/operation ra sao.

Disclosure:
  ai đọc batch/result/export,
  theo view/policy nào,
  các loại dữ liệu nào được công bố.
~~~

Không ghi raw token hoặc toàn bộ file nhạy cảm vào log chỉ để chứng minh đã export.

Internal reason như OUTSIDE_SCOPE hoặc RESOURCE_ABSENT có thể cần cho điều tra, nhưng chỉ nằm trong phạm vi được cấp. Không để một endpoint hỗ trợ ít được kiểm soát trở thành nơi đọc các reason đã bị che ở API chính.

Các dấu hiệu đáng theo dõi gồm dò nhiều batchId/item key, dùng cursor người khác, tải raw result sau khi scope đổi hoặc liên tục tạo batch mới từ item chưa xác định.

## 14. Kiểm thử disclosure như một bề mặt đọc dữ liệu

### 14.1. Fixture có cả dữ liệu hiện hữu và không hiện hữu

Chuẩn bị batch có manifest gồm ba item:

~~~text
row-1:
  caller được biết outcome và một tập field cụ thể.

row-2:
  resource có tồn tại nhưng nằm ngoài scope công bố.

row-3:
  reference không resolve được tới resource.
~~~

Caller có quyền xem envelope và các input key của chính batch theo chính sách mẫu.

Tạo thêm operator có view rộng hơn và một người hoàn toàn không được xem batch để kiểm tra cursor/cache/export chéo quyền.

### 14.2. Ma trận tình huống

| Tình huống | Điều phải kiểm chứng |
|---|---|
| Caller chỉ có BATCH_SUBMIT | Không tự có mọi item detail hoặc raw export |
| Được xem batch nhưng không được biết một item tồn tại | Placeholder/lỗi/metadata không xác nhận item đó |
| Item không tồn tại và item ngoài scope | Cùng chính sách public disclosure đã chọn |
| Chỉ được xem state, không được xem amount | Amount không xuất hiện trong dòng, error, summary hay file ngoài quyền |
| Summary tính trên internal result trước khi redact | Test phát hiện totals/counts làm lộ phần bị che |
| Job COMPLETED có item UNAVAILABLE/FAILED | UI/envelope không gọi mọi item thành công |
| Batch all-or-nothing rollback | Không giữ SUCCEEDED tạm thời |
| Batch từng phần có item đã commit | Không gắn toàn bộ kết quả là NOT_APPLIED |
| Timeout ở hệ thống ngoài | Kết quả được phép thấy phản ánh mức chưa xác định |
| Outcome bị che | Không chuyển thành FAILED/retryable chỉ vì không có chi tiết |
| Dùng batchId của tenant/người khác | Không đọc envelope, manifest hoặc artifact ngoài quyền |
| Cursor từ view rộng hơn/người khác | Không mở dữ liệu theo cursor như một capability ngoài hợp đồng |
| Query yêu cầu field/scope rộng hơn | Không mở rộng ngoài quyền server |
| Sort theo field bị cấm | Không tạo thứ tự làm lộ thuộc tính bí mật |
| Pagination/count | Dùng đúng basis, không lộ số match ngoài quyền |
| Cache được tạo trước thu hồi | Không trả lại body rộng quyền trái chính sách hiệu lực |
| Retry cùng command sau khi quyền đọc đổi | Không thực hiện lại; view/receipt theo quyền được cấp |
| Export sau khi UI đã lọc | File không chứa raw result rộng hơn policy export |
| Link/artifact cũ | Hiệu lực đúng hợp đồng tải/thu hồi, không vượt quyền được cấp |
| Notification kết thúc batch | Không lộ item bị che qua tên, số tiền hoặc attachment |
| Projector chạy trên managed entity | Không sửa dữ liệu nội bộ chỉ để redact |
| Client gửi outcome=FAILED/canRetry=true | Retry endpoint vẫn đọc state có thẩm quyền |
| Cùng ý định được đưa sang batch mới | Business key/idempotency và state guard vẫn áp dụng |
| Lỗi khi nạp facts quyền | Không fallback thành trả toàn bộ dữ liệu |

### 14.3. Thay đổi phần bị che rồi so public view

Giữ nguyên row-1, manifest, caller và quyền hiện tại. Chỉ thay các facts nội bộ của row-2, chẳng hạn:

~~~text
amount khác
owner hoặc tên tenant khác
state khác
internal error chi tiết khác
~~~

Theo chính sách mẫu không công bố các facts đó, public representation không được khác theo chúng: cùng placeholder, không có code/state/total/sort/header bổ sung làm lộ thay đổi.

Khi so sánh, chỉ bỏ qua các field biến động đã được xác định là công khai hợp lệ, như request ID. Không bỏ qua mọi metadata một cách rộng rãi rồi vô tình che mất lỗi ETag/count.

Kiểm thử này không chứng minh mọi side channel thời gian đều được loại bỏ, nhưng phát hiện nhiều lỗi công bố trực tiếp và metadata.

### 14.4. Thay trường hợp ngoài scope bằng trường hợp không tồn tại

Với cùng item key và cách công bố đã chọn, so sánh response khi reference trỏ tới một resource ngoài quyền và khi không resolve được.

Không được có một nhánh trả owner, operationId, status=PAID hoặc canonical ID còn nhánh kia chỉ có NOT_FOUND.

Nếu policy cho caller biết sự tồn tại nhưng không cho xem dữ liệu, có thể dùng một view khác được định nghĩa. Kỳ vọng test phải phản ánh policy đó, không ép mọi sản phẩm dùng cùng mức che giấu.

### 14.5. Kiểm thử summary và phép suy ra

Ví dụ public view chỉ có một dòng chi tiết, hai placeholder.

Xác nhận không có:

~~~text
globalSucceeded / globalPaid theo các item bị che
totalAmount của toàn internal batch
breakdown theo tenant/owner/risk ngoài scope
matchedResourceCount phân biệt tồn tại và không tồn tại
~~~

Nếu summary chỉ bao phủ phần được công bố, tên/basis phải nói đúng như vậy.

Field amount không được xem không nên tự biến thành 0 rồi được hiểu là tổng tiền thực. Hãy bỏ, đánh dấu không có projection hoặc dùng một chỉ tiêu có quyền và basis rõ ràng theo hợp đồng.

Kiểm tra cả file export, response header, dashboard và notification, không chỉ JSON item.

### 14.6. Kiểm thử quyền thay đổi sau thực thi

Cho caller xem chi tiết khi batch đã chạy. Sau đó thu hồi object scope hoặc quyền field rồi đọc lại.

Theo chính sách kiểm tra quyền hiện tại:

- Internal outcome/audit không bị sửa.
- Public view được dựng theo quyền mới.
- Cache/receipt không phục vụ lại body chi tiết cũ trái policy.
- Cursor cũ không mở rộng trang tiếp theo ngoài view hiện tại.
- Endpoint operation/export vẫn kiểm tra quyền tương ứng.

Nếu một quyền lịch sử độc lập vẫn còn, test phải xác minh đúng quyền đó và projection của nó, không suy rằng mọi former viewer đều mất mọi dữ liệu trong mọi mô hình.

### 14.7. Kiểm thử redaction không tạo mutation

Ghi nhận dữ liệu internal item trước khi đọc public view hạn chế. Sau đó đọc lại từ storage:

~~~text
amount và state không bị đổi
error evidence không bị xóa
canonical resource/operation vẫn đúng
audit execution không bị viết lại
~~~

Test này phát hiện việc projector đặt null/xóa field trực tiếp trên entity được persistence theo dõi.

Disclosure audit có thể ghi một sự kiện đọc được phép; nó không thay internal business result.

## 15. Tình huống thực hành: tổng tiền vẫn lộ dù từng dòng đã che

Một batch có 10 item. Caller chỉ được xem 2 item, tổng số tiền của chúng là 20 triệu.

UI che 8 item còn lại nhưng API trả:

~~~text
totalAmount = 100 triệu
visibleRowsAmount = 20 triệu
forbiddenCount = 5
notFoundCount = 3
~~~

Các dữ liệu đó cho phép suy ra nhiều điều mà placeholder đã cố che:

- Phần không được xem có tổng 80 triệu nếu định nghĩa tổng bao phủ các item đó.
- Có ít nhất một nhóm resource tồn tại nhưng ngoài quyền.
- Số reference không resolve được khác với số resource bị chặn.

Cần xác định lại public contract:

1. Chỉ trả các chỉ tiêu được policy cấp.
2. Nếu dùng summary của view, ghi rõ basis và không tính từ raw result.
3. Nếu caller đã biết manifest có 10 item, có thể trả submitted count theo quyền đó, không biến nó thành số resource tồn tại.
4. Dùng public trạng thái không công bố nhất quán thay vì breakdown internal reason.
5. Export và metadata phải tuân cùng quyết định.

Nếu sản phẩm thật sự cấp một báo cáo tổng hợp rộng hơn, phải đánh giá và cấp quyền đó riêng, bao gồm khả năng suy ra từ các bộ lọc nhỏ. Không coi việc đổi tên totalAmount thành statistics là đã ẩn dữ liệu.

### 15.1. Không được hiểu “không thấy” là “chưa chạy”

Một owner mất scope sau khi batch thành công có thể chỉ thấy UNAVAILABLE.

Nếu client tạo batch mới cho mọi dòng không hiển thị SUCCEEDED, nó có thể lặp ý định đã xảy ra. Server phải bảo vệ operation/business key và quyền retry; public view cũng cần làm rõ rằng UNAVAILABLE không phải một outcome thất bại.

Thông tin ít hơn không được biến thành một hướng dẫn hành động có thẩm quyền hơn.

## 16. Khung đặc tả batch result disclosure

~~~text
Ai được submit và ai được đọc batch envelope:
Manifest/input metadata nào caller được thấy:
Quyền execute từng item và ràng buộc tổng:

Disclosure policy từng item:
Field/error/outcome/link nào được công bố:
Cách che tồn tại và phân biệt disclosure với execution:
Ngữ nghĩa all-or-nothing hoặc partial result:

Basis của summary/count/amount:
Thứ tự, filter, pagination và cursor:
Header/cache metadata:
Receipt và quyền xem tại thời điểm đọc lại:

Projection export, thời điểm kiểm tra tải và capability:
Notification và các endpoint operation phụ:
Retry/recovery cho pending/unknown/unavailable:
Storage/audit nội bộ và audit disclosure:
Các test thay dữ liệu bị che, đổi quyền, cursor và export:
~~~

## 17. Câu hỏi tự kiểm tra

1. Batch owner được quyền biết những gì về từng item?
2. Quyền submit/execute có bị dùng nhầm như quyền đọc mọi kết quả không?
3. UNAVAILABLE khác UNKNOWN hoặc FAILED như thế nào?
4. Public error code có tiết lộ item ngoài quyền đã PAID hay đang chờ duyệt không?
5. Summary đang tính từ raw results hay từ tập/field được policy cho phép?
6. Tổng tiền, số lượng, thứ tự hoặc ETag có làm lộ thay đổi ở phần bị che không?
7. Cursor, operation link hoặc file export có mở một view rộng hơn trang chính không?
8. Quyền thay đổi sau khi batch chạy được xử lý thế nào khi đọc lại receipt?
9. Client có retry mọi dòng không nhìn thấy success, và server ngăn hiệu ứng lặp ra sao?

Một kết quả batch an toàn phải công bố **đúng dữ liệu, đúng người và đúng mức chắc chắn về thực thi**, trên cả từng item lẫn các thông tin tổng hợp. Che JSON của một dòng chỉ là một phần của ranh giới đó.
