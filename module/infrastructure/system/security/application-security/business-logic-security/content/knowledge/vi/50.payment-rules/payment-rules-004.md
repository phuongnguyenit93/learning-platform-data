# Chuyển trạng thái thanh toán (Payment state transitions)

Một giao dịch thanh toán không trở thành hợp lệ chỉ vì request có chữ ký đúng hoặc API trả về thành công. Hệ thống còn phải bảo đảm rằng **đúng đối tượng, đúng số tiền và đúng điều kiện nghiệp vụ** được chuyển sang trạng thái tiếp theo. Nếu các bước này bị bỏ qua, một đơn có thể được giao khi chưa thu tiền, bị thu hai lần hoặc được hoàn nhiều hơn số đã thu.

Trong chương **Payment Rules**, bài học này tập trung vào state machine của thanh toán và các bất biến bảo vệ nó. Nội dung liên kết quyền theo đối tượng, transaction, idempotency và kiểm thử các tình huống lạm dụng logic. Các trạng thái và mã giả dưới đây là mô hình nghiệp vụ minh họa; khi tích hợp thực tế phải ánh xạ rõ với hợp đồng của phương thức và nhà cung cấp đang dùng.

Sau bài học, bạn có thể:

- Phân biệt ý định thanh toán, lần thử, authorization, capture và refund.
- Xác định tiền điều kiện, bằng chứng và tác động của mỗi chuyển trạng thái.
- Xử lý trạng thái chưa biết kết quả mà không tự tạo thu hoặc hoàn trùng.
- Đồng bộ API response, webhook và đối soát theo cùng bất biến.
- Thiết kế việc giao hàng dựa trên kết quả thanh toán đã được xác nhận.

## 1. Đừng gộp mọi thứ vào một cột status

### 1.1. Các đối tượng có vòng đời khác nhau

| Đối tượng | Vai trò | Điểm cần phân biệt |
| --- | --- | --- |
| Payment intent | Ý định thanh toán một nghĩa vụ tiền cụ thể | Gắn với đơn/hóa đơn, phiên bản giá, số tiền và tiền tệ |
| Payment attempt | Một lần thử thực hiện ý định qua một phương thức | Một intent có thể có nhiều lần thử, nhưng không được thu vượt nghĩa vụ |
| Authorization | Quyền hoặc hạn mức được chấp thuận để có thể thu sau | Được chấp thuận authorization chưa có nghĩa đã capture |
| Capture | Thao tác thu một phần hoặc toàn bộ số tiền được phép | Có định danh và kết quả riêng |
| Void | Hủy phần authorization chưa sử dụng theo khả năng của tích hợp | Không phải refund số tiền đã capture |
| Refund | Hoàn một phần hoặc toàn bộ khoản đã thu đủ điều kiện | Không xóa lịch sử capture |
| Dispute/reversal | Tranh chấp hoặc điều chỉnh do cơ chế thanh toán | Cần mô hình và căn cứ riêng, không giả làm một refund tùy ý |

Một attempt loại `AUTHORIZE_ONLY` có thể thành công trong khi đơn vẫn chưa đủ điều kiện giao vì chưa thu tiền. Một attempt khác của cùng intent có thể thất bại mà không làm mất kết quả thu đã thành công trước đó.

Authorization, capture và refund không phải các tên đồng nghĩa cho “thanh toán xong”. Các phương thức thu ngay có thể không cung cấp một authorization tách biệt cho ứng dụng; mô hình phải phản ánh đúng phương thức thực tế.

### 1.2. Một trạng thái tổng hợp không thay được các con số

Một khoản có thể đồng thời:

```text
captured_amount = 1.000.000
refunded_amount = 200.000
refund_pending_amount = 100.000
dispute_status = OPEN
```

Chỉ lưu `status = REFUNDED` sẽ làm mất khác biệt giữa hoàn toàn bộ, hoàn một phần và hoàn đang xử lý.

Nên tách dữ kiện tiền, trạng thái từng operation và trạng thái hiển thị. Các trạng thái như `PARTIALLY_CAPTURED` hoặc `PARTIALLY_REFUNDED` thường được suy ra từ những số liệu và điều kiện đã xác nhận.

### 1.3. Xác định nguồn bằng chứng đáng tin cậy

Không dùng các dữ liệu sau làm bằng chứng tiền đã thu:

- Query parameter trên trang return, như `success=true`.
- Giá trị `paymentStatus` hoặc `amountPaid` client gửi.
- Việc người dùng đã qua màn hình xác thực.
- Một HTTP `2xx` chỉ xác nhận tiếp nhận tác vụ.
- Webhook có nội dung đúng định dạng nhưng chưa được xác minh và đối chiếu.

Bằng chứng cần đến từ kết quả đã xác thực của nguồn thanh toán có thẩm quyền, được gắn đúng operation, tài khoản merchant, môi trường, số tiền và tiền tệ. Giao diện chỉ hiển thị trạng thái do backend xác định.

## 2. Bất biến tiền và quyền chuyển trạng thái

### 2.1. Định danh và nội dung tài chính phải được cố định

Một operation tối thiểu cần biết:

```text
tenant_id
payment_intent_id
operation_id
operation_type
amount
currency
merchant_account
environment
source_reference
idempotency_scope + idempotency_key
request_fingerprint
```

Số tiền và tiền tệ được server xác định từ nghĩa vụ tiền đã chốt. Nếu giỏ hàng hoặc giá thay đổi, cần một quy trình cập nhật intent có kiểm soát hoặc tạo phiên bản mới; không sửa âm thầm số tiền của operation đã gửi.

Dùng số nguyên theo đơn vị nhỏ nhất của tiền tệ hoặc kiểu thập phân chính xác với quy tắc đã xác định. Không dùng số thực dấu phẩy động. Kiểm tra số dương, phạm vi giá trị và tràn số trước khi tính hoặc ghi dữ liệu.

ID của provider phải được ánh xạ trong phạm vi đúng provider, merchant account và môi trường. Không để một kết quả test hoặc một giao dịch ở merchant khác làm đơn thật được đánh dấu đã trả.

### 2.2. Capture không vượt quyền thu còn hiệu lực

Với một authorization trong mô hình hỗ trợ capture từng phần, đặt:

```text
A   = tổng hạn mức capture đã được chấp thuận cho authorization
C_a = tổng capture thành công thuộc authorization đó
K_a = tổng quyền capture đang được giữ bởi các operation chưa rõ kết quả cuối

Điều kiện khi claim capture mới số tiền x:
    x > 0
    C_a + K_a + x <= A
    authorization còn cho phép capture
```

Điều kiện cuối bao gồm hiệu lực thời gian, trạng thái void, giới hạn số lần capture và quy tắc của tích hợp. Công thức số học không biến một authorization đã hết hạn thành còn dùng được.

Không phải nhà cung cấp nào cũng cho capture nhiều lần. Một capture cuối có thể làm phần authorization còn lại không tiếp tục sử dụng được. Hệ thống phải biết lúc nào phần quyền còn lại đã bị đóng, thay vì chỉ lấy `A - C_a` để quyết định.

Refund không tự khôi phục quyền capture cũ. Nếu đã capture 1.000.000 rồi refund 200.000, không mặc nhiên được capture thêm 200.000 trên authorization đã dùng hết.

### 2.3. Refund không vượt phần tiền được phép hoàn

Với một khoản capture trong mô hình cơ bản chưa xét tranh chấp:

```text
C_t = số tiền capture đã thành công của khoản đó
R_t = tổng refund đã thành công
K_r = tổng tiền đã claim cho các refund chưa có kết quả cuối

Điều kiện khi claim refund mới số tiền y:
    y > 0
    R_t + K_r + y <= C_t
```

Các giới hạn nghiệp vụ có thể chặt hơn, chẳng hạn chỉ được hoàn phần của dòng hàng đã hủy hoặc trả hợp lệ. Khi có tranh chấp, reversal, điều chỉnh hoặc hạn chế của phương thức, phải kết hợp các quy tắc liên quan thay vì chỉ dùng công thức cơ bản.

Khoản đang `PENDING` hoặc `UNKNOWN` vẫn giữ ngân sách hoàn. Timeout không phải lý do để giải phóng ngân sách rồi tạo một khoản khác có thể được hoàn thêm lần nữa.

### 2.4. Ngăn thu trùng ở cấp nghĩa vụ tiền

Unique trên idempotency key chỉ chặn retry dùng lại cùng key. Nếu người dùng đổi key, đổi phương thức hoặc đổi provider trong khi lần thu cũ chưa rõ kết quả, hệ thống vẫn có nguy cơ thu hai lần.

Cần quản lý quyền thu ở cấp payment intent hoặc hóa đơn, có kiểm tra số đã thu và các cam kết thu chưa được giải quyết. Không cho mỗi attempt tự xét số tiền còn thiếu từ một bản sao cũ.

Một thiết kế có thể chỉ cho một luồng thu chưa giải quyết tại một thời điểm. Nếu cho phép nhiều luồng, phải cấp phát ngân sách thu dùng chung và xử lý nguy cơ thành công muộn. Khi chuyển quyền từ attempt sang capture, không cộng trùng cùng một quyền thu ở hai cấp.

### 2.5. Quyền theo đối tượng luôn đi cùng state machine

Được đăng nhập không đồng nghĩa được capture hoặc refund mọi giao dịch.

- Người mua có thể được tạo lần thử cho đơn thuộc quyền của mình.
- Service được phép capture cần có phạm vi merchant, tenant và căn cứ phù hợp.
- Nhân viên refund phải có quyền trên giao dịch và hạn mức tương ứng.
- Ngoại lệ có thể cần phê duyệt; approval phải gắn đúng số tiền, tiền tệ và đối tượng.
- Endpoint đọc trạng thái và replay kết quả vẫn phải kiểm tra quyền.

Không tin `tenantId`, `approved=true` hoặc `actorId` do client khai. Tham chiếu tới authorization, capture hoặc order khác phải được kiểm tra quan hệ đầy đủ.

## 3. Xây dựng state machine theo từng đối tượng

### 3.1. Vòng đời của một operation bất đồng bộ

Capture, refund hoặc void có thể dùng khung trạng thái minh họa:

```text
CREATED -> PROCESSING -> PENDING -> SUCCEEDED
                |          |
                |          +----> FAILED_FINAL
                |
                +-> UNKNOWN -> PENDING / SUCCEEDED / FAILED_FINAL
                |
                +-----------> SUCCEEDED / FAILED_FINAL
```

| Trạng thái | Ý nghĩa | Có được tạo tác động tiền lần nữa không? |
| --- | --- | --- |
| `CREATED` | Đã lưu operation và các claim cục bộ cần thiết | Worker thực thi đúng operation đó |
| `PROCESSING` | Đang cố gắng gửi hoặc xử lý; chưa có kết luận cuối | Không tạo operation mới để thay thế tùy tiện |
| `PENDING` | Có bằng chứng nguồn ngoài còn đang xử lý | Tiếp tục theo dõi cùng định danh |
| `UNKNOWN` | Chưa xác định được request đã được áp dụng hay chưa | Retry/tra cứu theo cơ chế chống trùng, giữ claim |
| `SUCCEEDED` | Có bằng chứng hiệu ứng yêu cầu đã thành công | Không áp dụng lại cùng hiệu ứng |
| `FAILED_FINAL` | Có bằng chứng cuối rằng operation đó không tạo hiệu ứng thành công | Chỉ giải phóng claim theo quyết định đã xác minh |

`PROCESSING` không chứng minh request đã tới provider. Một tiến trình có thể chết sau khi gửi nhưng trước khi lưu response. Cần cơ chế phát hiện operation treo và xác minh kết quả, không dựa vào việc worker cũ còn chạy hay không.

Lỗi validation trước khi gửi, lỗi bị từ chối có kết quả cuối và lỗi timeout là các loại khác nhau. Đừng gom tất cả thành `FAILED`.

### 3.2. Authorization cần quản lý hiệu lực và phần quyền còn lại

Một authorization có thể đang còn hiệu lực, đã sử dụng một phần, đã đóng sau capture cuối, đã void hoặc đã hết hạn. Các trạng thái cụ thể phải phù hợp với nguồn thanh toán.

| Sự kiện hoặc quyết định | Thay đổi cần mô hình hóa |
| --- | --- |
| Authorization được chấp thuận | Ghi quyền thu, tiền tệ, nguồn và điều kiện hiệu lực |
| Capture một phần thành công | Tăng số đã capture; cập nhật phần còn được phép theo chính sách |
| Capture cuối hoặc quyền bị tiêu thụ hết | Đóng quyền capture tiếp theo |
| Void thành công | Đóng phần quyền chưa sử dụng theo kết quả có thẩm quyền |
| Hết hiệu lực | Không cấp capture mới dựa trên quyền đã hết |
| Capture/void chưa rõ kết quả | Giữ trạng thái operation chờ; không suy ra một kết quả đối nghịch |

Void authorization không xóa một capture đã thành công. Nếu đã thu tiền và cần trả lại, dùng quy trình refund hoặc điều chỉnh phù hợp, không chuyển capture thành “chưa từng thu”.

### 3.3. Những trạng thái cuối thuộc đúng operation

Một attempt thất bại không được làm cả intent trở thành chưa thu tiền nếu attempt khác đã capture thành công.

Một capture thành công được giữ như sự kiện tài chính đã xảy ra. Nếu có reversal hoặc điều chỉnh sau đó, ghi nhận bằng sự kiện/operation phù hợp và cập nhật trạng thái tổng hợp theo mô hình; không xóa capture cũ.

Nếu bằng chứng mới mâu thuẫn với một kết luận từng được coi là cuối, cần giữ bằng chứng, đối soát và xử lý ngoại lệ. Không bỏ qua một kết quả thu thật chỉ vì cột local đang là `FAILED_FINAL`; cũng không tự tin nhận mọi event đến sau là đúng hơn.

### 3.4. Trạng thái hiển thị cần phản ánh đúng nghiệp vụ

Các nhãn “chờ xác thực”, “đang xử lý”, “đã giữ hạn mức”, “đã thu một phần”, “đã thu đủ” và “đã hoàn một phần” nên được suy ra từ mô hình trên.

Không đặt một thứ tự số nguyên kiểu `CREATED=1, PAID=2, FAILED=3` rồi lấy trạng thái có số lớn nhất. Trạng thái tiền không phải một thang tuyến tính, và kết quả của các operation khác nhau không được ghi đè lên nhau.

## 4. Đặc tả mỗi chuyển trạng thái như một quyết định nghiệp vụ

Một đặc tả chuyển trạng thái nên có: đối tượng, trạng thái trước, chủ thể được phép, điều kiện tiền, bằng chứng, trạng thái sau và tác động cần commit.

| Quyết định | Tiền điều kiện chính | Tác động hợp lệ |
| --- | --- | --- |
| Tạo capture | Đúng quyền, authorization còn dùng được, đủ ngân sách thu ở các cấp liên quan | Tạo operation và giữ quyền thu; chưa ghi là tiền đã thu |
| Xác nhận capture thành công | Bằng chứng đúng nguồn, đúng operation, đúng tiền và tiền tệ | Ghi nhận hiệu ứng thu một lần; chuyển claim tương ứng thành số đã thu |
| Xác nhận capture thất bại cuối | Có kết quả cuối, xác định không có hiệu ứng thu của operation đó | Đóng operation và giải phóng claim đúng một lần |
| Tạo refund | Capture có thật, căn cứ hoàn hợp lệ, đủ ngân sách hoàn, đúng quyền | Tạo nghĩa vụ/operation hoàn và giữ ngân sách |
| Xác nhận refund thành công | Đúng operation, capture nguồn và kết quả có thẩm quyền | Tăng số đã hoàn một lần, tiêu thụ claim |
| Yêu cầu void | Đúng authorization và phần còn có thể hủy, đã phân xử capture cạnh tranh | Tạo operation void; chưa coi đã void chỉ vì gửi request |
| Hủy đơn | Quyền và state machine của đơn cho phép | Ngăn ý định thu mới theo chính sách; giải quyết các operation đang chạy |
| Authorization hết hiệu lực | Căn cứ hiệu lực phù hợp với tích hợp | Chặn capture mới; vẫn đối soát capture đang chờ kết quả |

Bảng này ngăn những đường tắt như `POST /payments/{id}/status` với body `{"status":"CAPTURED"}`. Client được gửi ý định hợp lệ, còn server kiểm tra và thực thi chuyển trạng thái.

Một lệnh hủy đơn không có quyền tuyên bố rằng request capture đã gửi ra ngoài chưa từng xảy ra. Cần điều phối đóng luồng mới, xác minh luồng cũ và tạo bù trừ nếu phát sinh khoản thu không còn phục vụ đơn.

## 5. Transaction tạo operation: giữ quyền trước, thu thật sau

### 5.1. Luồng capture minh họa

Đoạn dưới là **mã giả**, không phải một API Java có thể chạy trực tiếp:

```text
requestCapture(context, command, idempotencyKey):
    principal = authenticate(context)
    references = resolveAndAuthorizeReferences(principal, command)
    approvedPlan = resolveApprovedCapturePlan(references, command)
    validateMoneyAndCurrency(approvedPlan)

    fingerprint = canonicalBusinessFingerprint(
        authorizationId,
        intentId,
        invoiceVersion,
        amount,
        currency,
        merchantAccount
    )

    response = transaction:
        request = claimIdempotency(
            principal.scope,
            idempotencyKey,
            fingerprint
        )

        if request.alreadyExists:
            require request.fingerprint == fingerprint
            require principal may read request.operation
            return request.savedResponse

        intent = lockPaymentIntent(references.intentId)
        authorization = lockAuthorization(references.authorizationId)

        recheck object relations and current permissions
        require intent still permits this capture plan
        require authorization permits a new capture
        require enough shared collection budget
        require enough authorization capture budget

        claimCollectionAndAuthorizationBudget(amount)

        operation = createImmutableOperation(
            type = CAPTURE,
            state = CREATED,
            amount = approvedPlan.amount,
            currency = approvedPlan.currency,
            source = approvedPlan.authorization
        )

        appendAudit(operation, principal, approvedPlan)
        appendOutbox(EXECUTE_PAYMENT_OPERATION, operation.id)

        response = pendingResponse(operation.id)
        saveIdempotentResponse(request, response)

    return response after successful commit
```

Nội dung operation sau khi tạo phải đủ để retry mà không lấy lại giá hiện tại từ client. Nếu cần capture số khác, tạo quyết định mới theo quy tắc và ngân sách còn lại; không sửa request của operation đang `UNKNOWN`.

Khi nhiều đối tượng cần khóa, các đường capture, void và điều chỉnh phải theo thứ tự khóa thống nhất. Nếu dùng cập nhật có điều kiện hoặc optimistic locking, phải kiểm tra conflict và đánh giá lại, không tiếp tục trên trạng thái cũ.

### 5.2. Ràng buộc lưu trữ hỗ trợ logic

Các ràng buộc hữu ích gồm:

```text
UNIQUE (tenant_id, caller_id, idempotency_key)
UNIQUE (provider, environment, merchant_account, provider_operation_id)
UNIQUE (operation_id, financial_effect_type) cho hiệu ứng cuối phù hợp
FOREIGN KEY operation -> intent / authorization / capture nguồn
CHECK amount > 0 và các số dư không âm theo mô hình
```

Các dòng trên mô tả ý tưởng ràng buộc, không phải DDL hoàn chỉnh. Nếu provider có nhiều lớp ID hoặc operation tạo nhiều hiệu ứng thành phần, khóa duy nhất phải phản ánh đúng phạm vi của chúng.

Unique constraint không tự giữ được tổng capture hoặc refund trên nhiều hàng. Các tổng và claim cần được bảo vệ bằng transaction, khóa hoặc cập nhật nguyên tử phù hợp.

Dấu idempotency, operation, claim và outbox phải commit cùng nhau. Nếu ghi outbox lỗi, không để lại một operation đã giữ ngân sách nhưng không có đường thực thi hay phục hồi được thiết kế.

## 6. Gọi nhà cung cấp và xử lý kết quả chưa chắc chắn

### 6.1. Không giữ transaction database trong lúc gọi mạng

Worker lấy công việc đã lưu, đọc operation bất biến và gửi request ra ngoài. Khóa/lease của worker phục vụ điều phối thực thi; nó không thay thế idempotency của tác động tiền.

Một chu trình minh họa:

```text
1. Đọc operation đã được tạo và claim hợp lệ.
2. Gửi request với provider idempotency key ổn định của operation.
3. Nhận kết quả hoặc lỗi liên lạc.
4. Lưu kết quả qua cùng bộ xử lý chuyển trạng thái.
5. Nếu chưa rõ kết quả, tiếp tục retry/tra cứu/đối soát cùng operation.
```

Provider key phải gắn với operation, không sinh mới mỗi lần worker chạy. Retry giữ nguyên nội dung có ý nghĩa nghiệp vụ và tuân theo hợp đồng chống trùng của tích hợp.

Nếu cơ chế chống trùng bên ngoài có thời hạn, sau thời hạn đó không được mù quáng gửi lại một request chưa rõ kết quả như thể nó chắc chắn sẽ được deduplicate. Cần tra cứu, đối soát hoặc xử lý ngoại lệ theo khả năng thực tế.

### 6.2. Phân loại kết quả theo ý nghĩa, không chỉ mã HTTP

| Kết quả quan sát | Cách xử lý |
| --- | --- |
| Bằng chứng operation đã thành công | Áp dụng chuyển thành công và hiệu ứng đúng một lần |
| Provider xác nhận đang xử lý | Ghi `PENDING`, tiếp tục theo dõi |
| Từ chối cuối có nghĩa rõ theo hợp đồng | Ghi thất bại cuối và giải phóng claim phù hợp |
| Timeout hoặc mất kết nối | `UNKNOWN` nếu chưa có bằng chứng cuối; giữ claim |
| Lỗi máy chủ hoặc response không rõ | Xác định có thể đã áp dụng hay chưa; không tự kết luận thất bại |
| Payload không khớp operation | Giữ bằng chứng, chặn tác động tự động và mở đối soát |

Không quy định cứng rằng mọi `4xx` là thất bại cuối và mọi `5xx` đều có thể retry như request mới. Phải xét ý nghĩa của response theo hợp đồng tích hợp và operation đã được gửi.

Thông báo “không nhận được phản hồi” là sự thật về liên lạc, không phải sự thật rằng chưa thu tiền.

### 6.3. Luồng xác thực bổ sung vẫn không trao quyền cho client

Nếu một attempt yêu cầu người dùng xác thực bổ sung, backend có thể trả bước tiếp theo được phép. Sau khi người dùng quay lại, backend phải xác minh kết quả qua nguồn thanh toán.

Không nhận một token hoặc cờ hoàn tất bất kỳ rồi cập nhật intent thành đã trả. Bước xác thực phải gắn với đúng attempt, nội dung tiền và phạm vi truy cập; nó cũng không tự cho phép sửa số tiền của operation đang xử lý.

Trang return có thể hiển thị “đang xác nhận thanh toán” trong khi backend chờ kết quả. Việc đóng tab không phải hủy một khoản đã được provider chấp nhận.

## 7. Webhook: xác thực nguồn rồi mới xét quyền chuyển trạng thái

### 7.1. Chữ ký hợp lệ chưa đủ để đánh dấu đã trả

Một webhook cần được kiểm tra theo nhiều lớp:

1. Xác minh nguồn theo hợp đồng tích hợp, trên dữ liệu nguyên gốc cần thiết cho việc kiểm tra chữ ký.
2. Kiểm tra ngữ cảnh endpoint, provider, merchant account và môi trường.
3. Tìm operation hoặc đối tượng nguồn bằng ánh xạ server quản lý.
4. Đối chiếu loại hiệu ứng, số tiền, tiền tệ và quan hệ tới intent.
5. Áp dụng tiền điều kiện state machine và ràng buộc chống trùng.
6. Ghi hiệu ứng, thay đổi tổng và outbox trong transaction phù hợp.

Nếu cơ chế chữ ký có thời hạn chống replay, áp dụng đúng cơ chế đó. Thời gian của lần delivery và thời gian nghiệp vụ xảy ra là hai thông tin khác nhau; event hợp lệ đến muộn không được bị biến thành một trạng thái cũ hơn chỉ dựa vào timestamp.

Một payload đã được ký vẫn có thể thuộc một giao dịch khác, chỉ phản ánh authorization hoặc chứa metadata không đủ để xác lập quan hệ tài chính. Không dùng riêng `metadata.orderId` làm bằng chứng thanh toán cho đơn.

### 7.2. Tiếp nhận bền vững và xử lý đúng một hiệu ứng

Một thiết kế có thể xác minh và ghi inbox trước, rồi xử lý bất đồng bộ:

```text
Webhook ingress:
    verify authenticity and delivery context
    persist inbox event with a scoped unique event key
    acknowledge only after durable acceptance

Inbox processor:
    resolve local operation and trusted source mapping
    transaction:
        lock operation and affected payment aggregates
        require event belongs to expected money and account context
        if financial effect already recorded:
            mark delivery processed without applying money again
        else:
            validate transition and evidence
            record financial fact
            update succeeded totals and pending claims
            mark operation state
            mark inbox processed
            append outbox for downstream decisions
```

Khóa chống trùng delivery có thể theo `(provider, environment, merchant_account, event_id)`. Ngoài ra cần chống trùng theo hiệu ứng tài chính của operation: API response và webhook có thể cùng báo một capture thành công, hoặc cùng hiệu ứng có thể xuất hiện trong các event khác ID.

Đánh dấu inbox đã xử lý phải nhất quán với việc áp dụng hiệu ứng. Nếu consumer chết sau khi cập nhật tiền nhưng trước khi ack, lần giao lại không được cộng tiền thêm.

Không gửi ack thành công rồi mới lưu event vào một nơi không bền vững. Ngược lại, ack việc đã tiếp nhận không nhất thiết đồng nghĩa mọi xử lý nghiệp vụ đã hoàn tất, nếu hệ thống đã có inbox và cơ chế phục hồi rõ ràng.

### 7.3. Khi chưa ánh xạ được provider ID

Response có thể bị mất trước khi ứng dụng lưu provider operation ID, trong khi webhook đã tới.

Cần giữ operation reference do server tạo và dùng cơ chế tra cứu/đối chiếu thích hợp. Metadata có thể là gợi ý để tìm, nhưng phải kiểm tra lại qua thông tin có thẩm quyền và nội dung operation.

Nếu chưa khớp được, lưu event vào luồng đối soát. Không tự tạo một intent đã trả dựa vào ID đơn do payload gợi ý.

Khi event cho thấy có khoản thu thật nhưng số tiền hoặc tiền tệ không khớp nghĩa vụ dự kiến, cần ghi nhận và điều tra khoản thu đó đúng bản chất. Chặn giao hàng sai không đồng nghĩa được bỏ mất bằng chứng tiền đã di chuyển.

### 7.4. Sự kiện đến muộn không được ghi đè dữ kiện mới

Ví dụ:

```text
Event 1: capture thành công.
Event 2 đến sau: attempt trước đó từng ở trạng thái processing.
```

Event 2 không làm số đã capture trở về 0. Các event thuộc đối tượng khác nhau phải được áp dụng vào đúng đối tượng.

Không dùng “webhook nhận sau cùng thắng”. Nếu provider có revision hoặc trình tự có ý nghĩa, ánh xạ đúng vào reducer; nếu không đủ thứ tự hoặc bằng chứng mâu thuẫn, tra cứu trạng thái có thẩm quyền hoặc đối soát.

Không gọi mạng trong lúc đang giữ transaction khóa tiền kéo dài. Có thể tách bước lấy bằng chứng từ provider, rồi mở transaction để kiểm tra lại version và áp dụng quyết định.

## 8. Các cuộc đua cần được phân xử

### 8.1. Timeout rồi đổi key để thử thu lại

```text
T1: Tạo capture C1 = 600.000 và claim quyền thu.
T2: Provider nhận request nhưng response bị mất.
T3: C1 ở UNKNOWN; claim 600.000 vẫn còn.
T4: Client đổi key và yêu cầu thu lại cùng nghĩa vụ.
T5: Provider báo C1 thành công qua webhook.
```

Nếu T4 bỏ qua C1 và tạo một khoản thu thay thế không được kiểm soát, hai khoản có thể cùng thành công. Idempotency ở T1 không bảo vệ được T4 vì key đã thay đổi.

Phải kiểm tra quyền thu chưa giải quyết ở cấp nghĩa vụ tiền. Có thể yêu cầu chờ hoặc đối soát C1 trước khi cho attempt thay thế. Nếu tích hợp cho phép thay thế trong một cơ chế đặc biệt, phải có chính sách kiểm soát rủi ro thu vượt và bù trừ rõ ràng; không giả định khoản cũ chắc chắn thất bại.

### 8.2. Capture cạnh tranh với void hoặc hủy đơn

Capture và void cần phân xử trên cùng authorization và các operation đang chờ. Một lệnh void mới không được tự xóa claim của capture đã gửi ra ngoài.

Nếu provider xác nhận capture đã thành công trước khi void có hiệu lực, phải giữ sự thật đã thu và xử lý phần tiền đó bằng quy trình thích hợp. Không đặt authorization thành `VOIDED` rồi suy ra toàn bộ số đã capture bằng 0.

Tương tự, nếu đơn đã hủy cục bộ nhưng capture thành công muộn, hệ thống phải ghi khoản thu thật. Có thể cần tạo nghĩa vụ hoàn theo quy trình hủy, nhưng không tự cho đơn đã hủy quay lại giao hàng chỉ vì nhận event capture thành công.

### 8.3. Hai refund cùng đọc một số dư cũ

Giả sử còn 600.000 được phép hoàn. Hai worker mỗi bên đọc 600.000 rồi yêu cầu hoàn 400.000.

Nếu kiểm tra và claim không nguyên tử, tổng 800.000 có thể vượt giới hạn. Đúng ra một bên claim 400.000 trước, bên sau chỉ còn 200.000 và không được gửi request 400.000.

Không tự giảm số tiền của request sau mà vẫn trả như đã thực hiện đủ. Việc hoàn một phần khác yêu cầu phải được thể hiện theo hợp đồng và phê duyệt phù hợp.

### 8.4. API response và webhook cùng báo thành công

Cả hai đường vào phải dùng cùng bộ xử lý hiệu ứng hoặc cùng ràng buộc lưu trữ:

```text
operation C1 -> financial effect CAPTURE_SUCCEEDED
```

Một đường ghi trước, đường còn lại nhận ra hiệu ứng đã tồn tại. Kết quả không phải hai dòng capture nghiệp vụ, không giảm claim hai lần và không phát hai lệnh giao hàng độc lập.

## 9. Ví dụ số: capture từng phần và refund

Giả sử phương thức đang dùng cho phép nhiều capture, authorization còn hiệu lực và hai capture dưới đây chưa đóng phần quyền còn lại. Hạn mức được chấp thuận là 1.000.000 đồng.

| Bước | Capture đã thành công | Claim capture chưa giải quyết | Refund đã thành công | Claim refund chưa giải quyết |
| --- | ---: | ---: | ---: | ---: |
| Authorization được chấp thuận | 0 | 0 | 0 | 0 |
| Tạo C1 = 600.000 | 0 | 600.000 | 0 | 0 |
| C1 thành công | 600.000 | 0 | 0 | 0 |
| Tạo C2 = 300.000, response timeout | 600.000 | 300.000 | 0 | 0 |
| Xác nhận C2 thành công | 900.000 | 0 | 0 | 0 |
| Tạo refund R1 = 200.000 từ C1 | 900.000 | 0 | 0 | 200.000 |
| R1 thành công | 900.000 | 0 | 200.000 | 0 |

Các tổng refund trong bảng phục vụ quan sát toàn ví dụ; giới hạn claim thực tế vẫn được kiểm tra trên từng capture nguồn và căn cứ hoàn tương ứng.

Sau cùng:

```text
Tổng capture đã xảy ra = 900.000
Tổng refund đã xảy ra = 200.000
Chênh lệch thu trừ hoàn = 700.000

Phần hạn mức authorization chưa dùng tối đa:
    1.000.000 - 900.000 = 100.000
    chỉ dùng được nếu các điều kiện hiệu lực khác vẫn cho phép
```

Không tính quyền capture tiếp thành 300.000 bằng cách trừ refund khỏi tổng đã capture. Refund trả lại tiền đã thu, không phục hồi authorization đã tiêu thụ.

Cũng không dùng chênh lệch 700.000 để tự kết luận cần thu thêm. Nghĩa vụ tiền hiện tại phụ thuộc chứng từ và các điều chỉnh nghiệp vụ đã được chấp nhận. Nếu refund xuất phát từ hủy hàng, việc thu lại phần vừa hoàn có thể trái với chính nghĩa vụ đã thay đổi.

Khi đối soát, phải phân biệt số liệu lịch sử gộp, khoản tiền đang xử lý và nghĩa vụ còn phải thu. Chúng trả lời các câu hỏi khác nhau.

## 10. Kích hoạt nghiệp vụ sau thanh toán

### 10.1. Không giao hàng theo trạng thái do client yêu cầu

Một điều kiện giao minh họa có thể gồm:

```text
Đơn ở trạng thái được thực hiện
+ nghĩa vụ tiền đúng phiên bản đã được đáp ứng
+ phương thức thu thỏa chính sách giao hàng
+ không có điều kiện chặn nghiệp vụ liên quan
```

Chính sách có thể cho phép giao sau capture, cho phép một số phương thức trả sau hoặc yêu cầu điều kiện khác. Không mặc định `AUTHORIZED` luôn đủ để giao cho mọi đơn.

Với thanh toán một phần, chỉ phần được phép theo chính sách mới được thực hiện. Không để một capture nhỏ làm toàn bộ đơn lớn được đánh dấu đã thanh toán đủ.

### 10.2. Ghi kết quả và phát sự kiện cùng transaction

Khi áp dụng capture thành công, ghi dữ kiện thu, cập nhật tổng, tiêu thụ claim và ghi outbox trong một transaction cục bộ. Consumer phía order/fulfillment cần chống trùng và kiểm tra trạng thái đơn trước khi tác động.

Delivery ít nhất một lần có thể khiến cùng event tới nhiều lần. Cần ràng buộc nghiệp vụ để không tạo nhiều fulfillment hoặc giao lại chỉ vì payment event bị gửi lại.

Một lần thất bại của attempt cũ không được kéo đơn đã được thanh toán hợp lệ trở lại `UNPAID`. Ngược lại, một event thành công cho phiên bản hóa đơn cũ không tự đáp ứng hóa đơn mới có số tiền khác.

### 10.3. Không coi thanh toán là transaction phân tán tự có

Database của ứng dụng không rollback được một khoản thu đã được provider chấp nhận. Hệ thống thường cần điều phối các bước với trạng thái bền vững, retry và bù trừ có điều kiện.

Nếu ghi nhận tiền thành công nhưng dịch vụ giao hàng chưa xử lý được, giữ dữ kiện đã thu và retry công việc giao theo chính sách. Nếu đơn không thể tiếp tục, mở quy trình giải quyết hoặc hoàn tiền phù hợp. Không sửa capture thành thất bại để làm các bảng trông đồng nhất.

## 11. Audit, đối soát và vận hành

### 11.1. Ghi lại quyết định, không chỉ ghi request

Một chuyển trạng thái nên có:

| Nhóm | Dữ liệu cần thiết |
| --- | --- |
| Đối tượng | Tenant, intent, attempt, authorization/capture/refund nguồn |
| Operation | ID, loại, số tiền, tiền tệ, nội dung bất biến |
| Chủ thể | Người khởi tạo, service thực thi, người duyệt nếu có |
| Quyết định | Trạng thái trước/sau, version, lý do và chính sách |
| Bằng chứng | Provider reference, event ID, loại nguồn bằng chứng, thời điểm ghi nhận |
| Chống trùng | Liên kết request key, fingerprint và hiệu ứng đã áp dụng |
| Nhân quả | Correlation ID, causation ID, liên kết tới tác động xuống order/fulfillment |

Không ghi thông tin thẻ nhạy cảm, mã xác thực hoặc bí mật ký webhook vào audit. Lưu bằng chứng đủ cho điều tra trong phạm vi quyền và chính sách dữ liệu thích hợp.

Ghi nhận attempt bị từ chối, request lỗi và hiệu ứng tiền đã thành công như các loại sự kiện khác nhau. Một dòng log `request sent` không được cộng vào số đã thu.

### 11.2. Đối soát các trạng thái chưa kết thúc

Cần có luồng kiểm tra:

- Operation `PROCESSING` quá lâu hoặc không còn worker thực thi.
- Operation `PENDING`/`UNKNOWN` vượt thời gian dự kiến.
- Provider có capture/refund nhưng local chưa có ánh xạ hoặc chưa áp dụng.
- Tổng đã thu/hoàn không khớp các hiệu ứng đã được ghi nhận.
- Claim còn giữ sau kết quả cuối hoặc bị giải phóng trong khi kết quả còn chưa rõ.
- Outbox chưa gửi, inbox chưa xử lý và event có ngữ cảnh tiền không khớp.
- Đơn bị hủy nhưng còn khoản thu cần giải quyết, hoặc đơn đã giao chưa đáp ứng chính sách tiền.

Đối soát phải so cùng phạm vi tài khoản, tiền tệ và mốc dữ liệu; báo cáo hoặc replica chậm có thể chưa phản ánh kết quả mới. Thời điểm nhận webhook không thay thế thời điểm hiệu ứng tài chính xảy ra.

Đối soát không phải tác vụ tạo mới capture/refund mỗi khi nhìn thấy trạng thái treo. Nó cần tìm lại cùng operation, bằng chứng và kết quả trước khi quyết định hành động.

### 11.3. Sửa sai có căn cứ và không che lịch sử

Công cụ hỗ trợ không nên cho phép gán `CAPTURED` chỉ để “mở khóa đơn”. Nếu khoản thu nằm ngoài luồng tự động, cần quy trình xác minh, liên kết bằng chứng và phê duyệt theo phạm vi được cấp.

Nếu kết luận cũ sai, giữ lịch sử quyết định và ghi sửa sai có lý do. Các fact đã ghi phải được bảo vệ khỏi sửa/xóa tùy ý bởi tài khoản ứng dụng.

Cảnh báo nên ưu tiên sai lệch có ý nghĩa: số tiền bất thường, merchant/môi trường không khớp, claim âm, thu vượt nghĩa vụ, hoàn vượt nguồn hoặc nhiều lần đổi key trong khi operation cũ chưa rõ. Retry mạng hợp lệ không tự là dấu hiệu gian lận.

## 12. Kiểm thử tình huống tấn công logic

Mỗi ca cần kiểm tra response, trạng thái, claim, dữ kiện thu/hoàn, audit và tác động tới đơn. Chỉ kiểm tra mã HTTP là chưa đủ.

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Client tự gửi `status=CAPTURED` hoặc sửa return URL thành thành công | Không có quyền xác nhận tiền đã thu |
| Đổi tenant, intent hoặc authorization sang đối tượng ngoài quyền | Bị chặn; replay và API đọc trạng thái không làm lộ kết quả |
| Trộn intent hợp lệ với capture/authorization không thuộc nó | Từ chối quan hệ đối tượng sai |
| Sửa amount, currency hoặc invoice version sau khi tạo operation | Không thay nội dung operation đã gửi |
| Cùng key, cùng payload, gửi đồng thời hoặc retry sau mất response | Một operation và một hiệu ứng nghiệp vụ |
| Cùng key nhưng đổi tiền, tiền tệ hoặc nguồn capture | Xung đột, không áp dụng nội dung mới |
| Đổi key/phương thức khi khoản thu cũ còn `UNKNOWN` | Không bỏ qua quyền thu chưa giải quyết |
| Hai capture cùng tranh hạn mức còn lại | Tổng đã thu và claim không vượt giới hạn hợp lệ |
| Capture cạnh tranh với void hoặc hủy đơn | Quyết định theo nguồn có thẩm quyền, không xóa hiệu ứng đã xảy ra |
| Hai refund đồng thời vượt ngân sách còn được hoàn | Chỉ claim phần hợp lệ; không gửi cả hai như đã đủ điều kiện |
| Refund timeout rồi retry với worker khác | Giữ nghĩa vụ và định danh cũ; không hoàn thêm lần nữa |
| API response và webhook cùng báo thành công | Ghi hiệu ứng đúng một lần, không giảm claim hai lần |
| Event trùng ID hoặc cùng hiệu ứng khác event ID | Không cộng tiền hoặc phát công việc nghiệp vụ trùng |
| Webhook chữ ký sai, đúng chữ ký nhưng sai merchant hoặc môi trường | Không làm intent thật chuyển thành đã trả |
| Event chỉ xác nhận authorization | Không được hiểu như capture thành công |
| Event cũ hoặc attempt thất bại đến sau capture thành công | Không làm lùi kết quả tiền đã xác nhận |
| Payload tiền không khớp operation | Chặn áp dụng sai, giữ bằng chứng và đưa vào đối soát |
| Consumer chết sau commit trước ack | Delivery lại không tái áp dụng hiệu ứng |
| Provider đã thu nhưng đơn local vừa hủy | Ghi sự thật đã thu; giải quyết tiền theo quy trình, không tự giao lại |
| Capture một phần nhỏ của đơn | Không tự mở giao toàn bộ nếu chính sách chưa cho phép |

Các ca cạnh tranh phải đưa các tác vụ tới cùng điểm quyết định, không chỉ gọi tuần tự. Cần chèn lỗi trước khi gửi, sau khi provider có thể đã nhận, sau local commit và trước ack/response.

Kiểm tra cả các đường hợp lệ như nhiều capture khi tích hợp hỗ trợ, refund từng phần và retry sau lỗi mạng. Một cơ chế chống trùng quá rộng có thể chặn công việc hợp lệ hoặc khiến nhân viên phải xử lý ngoài luồng chuẩn.

## 13. Bài tập áp dụng

### Bài tập 1: Timeout có cho phép thử thu mới không?

Một capture 500.000 đã được lưu và gửi tới provider. Request timeout, local chuyển operation thành `FAILED`, giải phóng quyền thu và cho người dùng đổi phương thức để trả lại 500.000. Sau đó webhook báo capture đầu thành công.

Hãy xác định lỗi mô hình và cách xử lý đúng.

**Gợi ý giải:** Hệ thống đã biến lỗi liên lạc thành bằng chứng không thu. Operation cần ở `UNKNOWN` khi chưa có kết quả cuối, giữ quyền thu và được retry/tra cứu theo cùng định danh. Không cho attempt thay thế vượt qua claim đang tồn tại. Nếu đã có hai khoản thu thực tế, phải ghi nhận cả sự thật và giải quyết khoản vượt theo quy trình; không xóa một fact hoặc bỏ qua webhook để làm số liệu trông hợp lệ.

### Bài tập 2: Tính ngân sách hoàn trong lúc còn request chờ

Một capture thành công 700.000. Đã hoàn thành công 200.000; còn một refund 100.000 chưa rõ kết quả. Hai worker cùng đề nghị tạo hai refund mới, mỗi khoản 300.000.

Hãy tính ngân sách có thể claim và kết quả của hai request nếu chạy đồng thời.

**Gợi ý giải:** Ngân sách chưa claim là `700.000 - 200.000 - 100.000 = 400.000`. Nếu một worker claim 300.000 trước, phần chưa claim chỉ còn 100.000. Worker sau không được gửi khoản 300.000 nguyên vẹn. Khoản 100.000 chưa rõ kết quả vẫn phải giữ chỗ; việc nó timeout không làm ngân sách tăng.

Một state machine thanh toán an toàn cần giữ đúng sự thật tài chính, quyền trên đối tượng và các claim đang chờ trong mọi đường vào. Mỗi chuyển trạng thái phải có căn cứ và tác động được ghi nhất quán; những kết quả chưa biết phải tiếp tục được xử lý như chưa biết, thay vì bị ép thành thành công hoặc thất bại để kết thúc request.
