# Webhook event freshness — Kiểm soát độ mới của sự kiện webhook

## 1. Một webhook hợp lệ chưa chắc còn phù hợp để tạo tác động

Webhook thường báo rằng thanh toán đã được ghi nhận, khoản hoàn tiền đã hoàn tất hoặc quyền truy cập đã thay đổi. Bên nhận cần biết nguồn gửi có hợp lệ, nội dung có bị sửa và thông điệp có còn được phép tác động tới trạng thái hiện tại hay không.

Một request có chữ ký đúng có thể là:

- Lần gửi mới của một sự kiện vừa phát sinh.
- Retry hợp lệ cho một sự kiện đã xảy ra từ lâu.
- Bản sao của một request bị phát lại trong cửa sổ còn hiệu lực.
- Một sự thật lịch sử chưa từng được hệ thống ghi nhận.
- Một sự kiện từng đúng nhưng không còn đủ để cho phép một hành động mới.

**Webhook event freshness** là cách đánh giá thời gian và điều kiện sử dụng webhook để không biến dữ liệu cũ hoặc request bị replay thành tác động nghiệp vụ mới trái quy tắc.

Trong bảo mật logic nghiệp vụ, cần bảo vệ đồng thời ba lớp:

1. **Xác thực lần giao:** request do nguồn được phép ký và được nhận trong cửa sổ thời gian chấp nhận.
2. **Nhận diện sự kiện:** sự kiện đã được tiếp nhận hoặc áp dụng trước đó chưa.
3. **Quyết định nghiệp vụ:** sự thật trong event cho phép thay đổi gì ở trạng thái hiện tại.

Không dùng một phép so timestamp để thay thế cả ba lớp.

### Tình huống xuyên suốt

Nền tảng bán hàng nhận webhook từ cổng thanh toán. Một đơn có thể đã bị hủy trước khi webhook `PaymentCaptured` đến.

Quy tắc ví dụ:

- Webhook cần được xác thực bằng cấu hình tin cậy của endpoint.
- Timestamp dùng để giới hạn replay phải nằm trong dữ liệu được chữ ký bảo vệ.
- Cùng sự kiện không được cộng tiền hoặc mở tác vụ giao hàng nhiều lần.
- Thanh toán đến muộn vẫn cần được ghi nhận và đối soát.
- Việc đã thu tiền không tự động cho phép mở lại đơn đã hủy.
- Nếu muốn giao hàng hoặc hoàn tiền sau đối soát, đó là quyết định nghiệp vụ có điều kiện riêng.

Những giá trị thời gian trong bài chỉ là ví dụ thiết kế, không phải mặc định chung của các nhà cung cấp webhook.

## 2. Tách các mốc thời gian trước khi kiểm tra freshness

### 2.1. Các mốc có ý nghĩa khác nhau

| Mốc | Ý nghĩa | Ai cung cấp? | Có thể dùng trực tiếp để chống replay không? |
| --- | --- | --- | --- |
| `occurredAt` | Sự việc nghiệp vụ xảy ra lúc nào | Hệ thống nguồn | Không đủ; sự kiện có thể được gửi lại hợp lệ rất lâu sau đó |
| `signedAt` | Lần giao được ký lúc nào | Bên gửi theo hợp đồng chữ ký | Có thể, nếu thực sự được ký và có ngữ nghĩa phù hợp |
| `receivedAt` | Bên nhận thấy request lúc nào | Hạ tầng bên nhận | Là mốc so sánh, không tự xác thực nguồn |
| `verifiedAt` | Bên nhận hoàn tất xác thực lúc nào | Bên nhận | Bằng chứng kiểm tra, không thay thế thời điểm tiếp nhận |
| `processedAt` | Worker áp dụng kết quả lúc nào | Bên nhận | Phục vụ độ trễ xử lý và kiểm tra điều kiện nghiệp vụ |
| `validUntil` | Hạn một quyền hoặc command còn được dùng | Nguồn có thẩm quyền theo nghiệp vụ | Chỉ có ý nghĩa nếu được xác thực và đúng loại thông điệp |

Các tên field là ví dụ. Một nhà cung cấp có thể dùng cùng một field timestamp với ngữ nghĩa khác; cần dựa vào hợp đồng giao thức thực tế, không suy từ tên.

### 2.2. Lần giao mới có thể chứa sự kiện cũ

Giả sử:

~~~text
10:00  Thanh toán được ghi nhận ở nguồn.
10:01  Nguồn thử gửi webhook nhưng không tới được ứng dụng.
10:30  Nguồn retry và ký lần giao mới.
10:30  Ứng dụng nhận webhook.
~~~

Nếu timestamp chữ ký biểu diễn lần giao 10:30, request có thể đủ mới dù `occurredAt` là 10:00.

Nếu nhà cung cấp giữ nguyên chữ ký và timestamp cũ khi retry, việc áp dụng cửa sổ ngắn sẽ cho kết quả khác. Không tự giả định mọi nguồn đều ký lại mỗi lần gửi; chính sách phải phù hợp khả năng giao thức.

### 2.3. Độ mới lúc nhận khác độ mới lúc xử lý

Một webhook đến đúng hạn có thể nằm trong hàng đợi nội bộ thêm vài phút hoặc vài giờ. Worker không nên kiểm tra lại chữ ký gốc bằng đồng hồ hiện tại rồi coi request từng được nhận hợp lệ là replay.

Thay vào đó, lưu bằng chứng đã xác thực tại ingress: thời điểm nhận, kết quả kiểm tra, phiên bản khóa, digest nội dung và định danh nguồn. Worker dựa vào bản ghi tiếp nhận được bảo vệ, đồng thời kiểm tra điều kiện nghiệp vụ tại thời điểm tạo tác động.

Độ trễ xử lý vẫn cần được giám sát. Việc ingress đã xác thực không phải quyền bỏ qua thời hạn của một command hoặc trạng thái hiện tại của đối tượng.

## 3. Cửa sổ thời gian cho lần giao được ký

### 3.1. Timestamp phải thuộc dữ liệu được bảo vệ

Nếu chữ ký chỉ bao phủ body còn timestamp nằm trong header không được ký, kẻ có bản sao request có thể thay header thành thời gian hiện tại. Phép kiểm tra độ mới khi đó không bảo vệ request khỏi replay.

Timestamp có thể nằm trong body hoặc header, nhưng phải được ràng buộc vào thông điệp theo đúng cơ chế xác thực của nguồn. Event ID, tài khoản nguồn và ngữ cảnh endpoint cũng cần được liên kết phù hợp để tránh dùng request hợp lệ sai phạm vi.

Không tự thiết kế lại chuỗi ký cho một dịch vụ đã có giao thức. Khi triển khai, dùng hợp đồng xác thực và thư viện được hỗ trợ của nguồn tương ứng.

### 3.2. So sánh với giới hạn quá khứ và tương lai

Một chính sách minh họa:

~~~text
age = receivedAt - signedAt

Chấp nhận về thời gian khi:
    -futureSkew <= age <= maxDeliveryAge
~~~

Trong đó:

- `maxDeliveryAge`: tuổi tối đa chấp nhận của lần giao.
- `futureSkew`: độ lệch về tương lai được dung sai.
- `receivedAt`: mốc do bên nhận ghi ở ranh giới ingress được xác định.
- `signedAt`: mốc đã được xác thực theo hợp đồng chữ ký.

Ví dụ `maxDeliveryAge = 300 giây`, `futureSkew = 30 giây`:

| Tuổi lần giao | Kết quả thời gian theo ví dụ | Ý nghĩa |
| --- | --- | --- |
| 20 giây | Trong cửa sổ | Vẫn cần chống trùng và kiểm tra nghiệp vụ |
| 300 giây | Trong cửa sổ, nếu chọn ranh giới bao gồm | Cách xử lý biên phải thống nhất |
| 301 giây | Ngoài cửa sổ | Không đi thẳng vào luồng áp dụng mới |
| -10 giây | Trong dung sai tương lai | Có thể do lệch đồng hồ trong giới hạn |
| -31 giây | Ngoài dung sai | Cần xử lý như lỗi thời gian hoặc giao thức |

Không dùng chỉ một điều kiện “timestamp chưa quá cũ” mà quên giới hạn tương lai. Một request mang thời gian rất xa trong tương lai không được sống lâu tùy ý.

### 3.3. Kiểm tra định dạng và đơn vị

Server cần xác định rõ giây, mili giây hoặc định dạng thời gian nào được giao thức dùng; kiểm tra kiểu, miền giá trị, khả năng tràn số và độ chính xác.

Không thử đoán nhiều đơn vị rồi chọn cách diễn giải làm request được chấp nhận. Không nhận timestamp số thực tùy ý hoặc dữ liệu có nhiều giá trị mâu thuẫn nếu hợp đồng không cho phép.

Cần xử lý header trùng, chữ ký thiếu và phiên bản giao thức không hỗ trợ theo quy tắc xác định. Mốc chưa được xác thực chỉ là dữ liệu đầu vào, chưa phải căn cứ tin cậy.

### 3.4. Chọn cửa sổ theo đặc điểm hệ thống

Cửa sổ quá rộng tạo điều kiện replay kéo dài. Cửa sổ quá hẹp có thể loại các lần giao hợp lệ vì độ trễ mạng, proxy, cơ chế ký hoặc sai lệch đồng hồ.

Cần xem xét độ trễ từ lúc ký tới ingress, chính sách retry của nguồn, khả năng đồng bộ giờ và thời gian chuyển qua hạ tầng trung gian. Đo riêng độ trễ hàng đợi sau tiếp nhận; không lấy nó làm lý do tự động nới cửa sổ chữ ký.

Không tự tăng dung sai toàn hệ thống mỗi khi có nhiều request bị từ chối. Trước hết cần xác định mốc nào lệch, cơ chế retry nào đang được dùng và nguồn nào chịu ảnh hưởng.

## 4. Các business invariant cần giữ

### 4.1. Request được áp dụng mới phải có bằng chứng xác thực

~~~text
WebhookApplied
    => TrustedEndpointBinding
       AND VerifiedMessageIntegrity
       AND AcceptedDeliveryTimePolicy
       AND DurableIntakeRecord
       AND AuthorizedBusinessTransition
~~~

Đây là quy tắc cho luồng nhận trực tiếp đã chọn kiểm tra freshness. Một sự kiện cần khôi phục ngoài cửa sổ có thể được xử lý qua luồng đối soát riêng với bằng chứng và quyền thích hợp; không đánh dấu nó như thể đã vượt qua cửa sổ ban đầu.

### 4.2. Trong cửa sổ không có nghĩa chỉ xuất hiện một lần

Một request hợp lệ có thể bị phát lại nhiều lần trong 300 giây. Chữ ký và timestamp vẫn đúng, nhưng tác động không được nhân lên.

Cần khóa chống trùng ở cấp sự kiện và khóa nghiệp vụ ở cấp tác động. Freshness chỉ hạn chế một loại replay theo thời gian.

### 4.3. Không lấy dữ liệu chưa xác thực để chọn tenant có quyền

Endpoint có cấu hình ánh xạ tới nguồn, tài khoản và phạm vi tenant được phép. Có thể dùng một định danh endpoint không bí mật để tìm cấu hình ứng viên, nhưng quyền xử lý phải được xác minh sau đó.

Không đọc `tenantId` hoặc `merchantAccount` từ body rồi tự chọn tenant, khóa ký hoặc tài khoản thanh toán tương ứng mà không đối chiếu ràng buộc tin cậy.

### 4.4. Sự thật đến muộn không được tự tạo quyền hiện tại

`PaymentCaptured` có thể cần được ghi sổ dù đơn đã hủy. Nó không tự cho phép chuyển đơn sang trạng thái giao hàng.

Giá trị giao dịch, tiền tệ, tài khoản nguồn, đối tượng nhận tiền và quan hệ với đơn phải được kiểm tra. Khi cần xác minh thêm, sử dụng API và cấu hình nguồn đã được cấp quyền.

### 4.5. Không được giả mạo thời điểm để làm sự kiện trông mới

Retry hoặc đối soát không được sửa `occurredAt` thành thời gian hiện tại. Giữ riêng thời điểm sự việc, thời điểm tiếp nhận và thời điểm khôi phục để audit phản ánh đúng diễn biến.

## 5. Luồng xác thực và tiếp nhận webhook

### 5.1. Thứ tự kiểm soát ở ingress

Một luồng có thể được tổ chức như sau:

~~~text
Nhận request và ghi receivedAt tại ranh giới tin cậy
    → Giới hạn kích thước và định dạng đầu vào
    → Tìm cấu hình endpoint được quản lý ở server
    → Xác minh chữ ký theo đúng giao thức
    → Kiểm tra signedAt đã xác thực
    → Parse và kiểm tra schema sự kiện
    → Đối chiếu tài khoản, môi trường và phạm vi
    → Ghi tiếp nhận + chống trùng + outbox
    → Trả kết quả nhận theo hợp đồng HTTP
~~~

Không thực hiện tác động tiền bạc hoặc truy vấn tùy ý tới một URL trong payload trước khi xác thực.

Cần giữ đúng bytes mà giao thức yêu cầu khi kiểm tra chữ ký. Parse rồi serialize lại JSON có thể làm thay đổi khoảng trắng, thứ tự field hoặc biểu diễn dữ liệu. Các phép biến đổi body, giải mã và header qua proxy cũng phải phù hợp hợp đồng xác thực.

Nếu có cơ chế nén, phiên bản chữ ký hoặc dạng mã hóa đặc biệt, xử lý theo giao thức cụ thể, không tự thử nhiều cách cho tới khi một cách khớp.

### 5.2. Mã giả cho ranh giới tiếp nhận

Đoạn sau là mã giả theo phong cách Java. Các helper biểu diễn trách nhiệm kiểm soát, không phải API của một nhà cung cấp cụ thể.

~~~java
IntakeReceipt receiveWebhook(HttpRequest request) {
    EndpointConfig endpoint = endpointRegistry.resolve(request.endpointId());

    byte[] rawBody = request.readBodyWithin(
        endpoint.maxBodyBytes(), endpoint.bodyReadTimeout()
    );
    Instant receivedAt = ingress.trustedCompletedRequestAt(request);

    VerifiedDelivery delivery = providerVerifier.verify(
        endpoint, request.headers(), rawBody
    );
    freshness.requireAccepted(
        delivery.signedAt(),
        receivedAt,
        endpoint.maxDeliveryAge(),
        endpoint.futureSkew()
    );

    VerifiedEvent event = eventDecoder.decodeAndValidate(delivery, rawBody);
    bindings.requireExpectedSourceAccountAndEnvironment(endpoint, event);

    return transaction.execute(() -> {
        // Khóa theo sự kiện nghiệp vụ của nguồn, không theo attempt giao.
        InboxResult result = webhookInbox.receiveOrLoad(
            endpoint.consumerPurpose(),
            event.providerId(),
            event.providerAccountId(),
            event.eventId(),
            event.immutableContentFingerprint()
        );

        result.requireConsistentEventIdentity();

        webhookDeliveries.record(
            result.eventRecordId(),
            receivedAt,
            delivery.signedAt(),
            delivery.keyVersion(),
            delivery.rawBodyDigest()
        );

        if (result.isNewEvent()) {
            webhookInbox.storeVerifiedEventAndProof(
                result, event, delivery, receivedAt
            );
            outbox.append(WebhookAccepted.from(result.eventRecordId()));
        }

        return IntakeReceipt.durablyReceived(result.eventRecordId());
    });
}
~~~

`trustedCompletedRequestAt` không đọc tùy ý một header do người ngoài gửi. Nếu dùng timestamp do gateway đóng dấu, cần ranh giới tin cậy rõ, loại bỏ giá trị bên ngoài có thể giả mạo và bảo vệ đường truyền nội bộ.

Hàm verify phải dùng cấu hình và khóa được phép, kiểm tra tính toàn vẹn theo giao thức, và không cho request tự chọn một thuật toán yếu hơn. Nếu cần so giá trị xác thực, dùng cơ chế so sánh phù hợp của thư viện thay vì tự viết phép so dễ rò rỉ.

Transaction phải bảo vệ unique constraint, trạng thái inbox và outbox. Nếu hai request cùng sự kiện tới đồng thời, không được tạo hai công việc có cùng tác động. Chỉ một nhánh được tạo sự kiện tiếp nhận mới.

### 5.3. Phản hồi HTTP phản ánh việc đã nhận

Một phản hồi chấp nhận thường nên được trả sau khi sự kiện và trách nhiệm xử lý đã được lưu bền vững. Không trả thành công chỉ vì đã đưa vào bộ nhớ của tiến trình.

Việc nguồn nhận phản hồi thành công không có nghĩa đơn hàng đã thanh toán xong ở mọi hệ thống hoặc mọi hậu xử lý đã hoàn tất. Nó có thể chỉ có nghĩa bên nhận đã nhận trách nhiệm.

Mã phản hồi và hành vi retry phải theo hợp đồng của nguồn. Không áp đặt cùng một mã lỗi hoặc quy tắc retry cho mọi nhà cung cấp.

Với request không qua freshness, không tự đưa vào luồng áp dụng như một event đã được chấp nhận. Nếu chính sách cho phép lưu để đối soát hoặc phản hồi chấp nhận việc cách ly nhằm tránh retry vô ích, trách nhiệm này phải được lưu bền vững và phân biệt rõ với xử lý nghiệp vụ thành công.

### 5.4. Xác thực thất bại không được làm rò dữ liệu

Không trả nội dung giao dịch hoặc trạng thái đơn chỉ vì một request nêu đúng event ID. Request bị thiếu hoặc sai xác thực không được dùng nhánh chống trùng để dò xem sự kiện nào đã tồn tại.

Thông tin lỗi gửi ra ngoài nên đủ cho hợp đồng tích hợp. Chi tiết khóa, tenant và dữ liệu nhạy cảm phục vụ điều tra được giữ trong log được phân quyền.

## 6. Freshness, chống replay và idempotency bổ sung cho nhau

### 6.1. Phân biệt event ID và delivery ID

Một sự kiện có thể được gửi nhiều lần:

~~~text
eventId = evt_capture_781
    delivery A: signedAt 10:00, attempt 1
    delivery B: signedAt 10:05, attempt 2
    delivery C: signedAt 10:30, attempt 3
~~~

Nếu nguồn dùng cách ký mới cho mỗi lần giao, cả ba có thể hợp lệ về thời gian khi đến. Tuy nhiên, chúng vẫn đại diện cho cùng sự kiện.

Khóa chống trùng có thể là:

~~~text
(consumerPurpose, providerId, providerAccountId, eventId)
~~~

`consumerPurpose` được server xác định nếu nhiều consumer có nghĩa vụ xử lý khác nhau. Không lấy một giá trị tùy ý từ request để tạo không gian chống trùng mới.

Delivery ID hỗ trợ truy vết lần gửi và replay của cùng request. Nó không thay thế event ID hoặc khóa tác động.

### 6.2. Một fact có thể xuất hiện trong nhiều event

Nguồn có thể phát các sự kiện khác nhau cùng liên quan đến một khoản thu, hoặc công cụ phát lại có thể có cách định danh riêng. Chống trùng theo event không đủ để chứng minh chỉ có một bút toán.

Cần khóa nghiệp vụ cho tác động, ví dụ:

~~~text
UNIQUE(tenantId, providerAccountId, captureId, postingType)
~~~

Nếu một khoản thanh toán có nhiều capture hợp lệ, khóa cần phân biệt đúng từng capture. Không dùng một khóa quá rộng làm mất các khoản thu hợp lệ.

Bút toán, cập nhật trạng thái và effect record trong cùng cơ sở dữ liệu cần transaction tương ứng. Tác động ngoài cơ sở dữ liệu cần idempotency hoặc đối soát ở ranh giới đó.

### 6.3. Cùng event ID nhưng nội dung khác

Cần kiểm tra tính nhất quán theo hợp đồng nguồn. Nếu cùng event ID bỗng đổi số tiền, tài khoản hoặc đối tượng giao dịch, không dùng “bản đến sau thắng” để ghi đè sự kiện cũ.

Có thể cần cách ly và truy vấn nguồn có thẩm quyền để xác định đó là lỗi, thay đổi biểu diễn được hỗ trợ hay dấu hiệu can thiệp.

Digest raw body phục vụ bằng chứng của từng request. Fingerprint nhận diện nội dung sự kiện có thể cần loại các metadata giao lặp theo hợp đồng và chuẩn hóa field nghiệp vụ. Không mặc định raw body phải giống hệt qua mọi retry, cũng không bỏ qua tùy ý những field làm thay đổi ý nghĩa.

### 6.4. Thời gian lưu chống trùng không bằng cửa sổ chữ ký

Cửa sổ chữ ký 5 phút không có nghĩa có thể xóa event ID sau 5 phút. Nguồn có thể retry sự kiện đó hôm sau với một lần giao mới hoặc người quản trị có thể yêu cầu phát lại.

Thời gian lưu cần xem xét khả năng redelivery, lịch sử đối soát và vòng đời nghiệp vụ. Bằng chứng tác động tài chính thường có giá trị bảo vệ lâu hơn một lần giao HTTP.

Nếu dọn inbox, phải giữ lớp bằng chứng khác đủ để chặn tác động trùng. Không dựa duy nhất vào cache có TTL ngắn.

## 7. Xử lý bất đồng bộ mà không làm sai freshness

### 7.1. Bằng chứng tiếp nhận được lưu cùng sự kiện

Bản ghi tiếp nhận nên giữ các thông tin phù hợp:

~~~text
nguồn và tài khoản đã được xác minh
định danh endpoint và mục đích consumer
eventId, loại sự kiện, phiên bản schema
occurredAt theo sự kiện
receivedAt, signedAt, verifiedAt
kết quả xác thực và chính sách thời gian đã áp dụng
phiên bản khóa và digest của request
payload cần thiết hoặc tham chiếu bền vững được bảo vệ
~~~

Không lưu secret ký hoặc token truy cập để chứng minh đã verify. Quyền sửa bằng chứng tiếp nhận phải được bảo vệ; nếu bất kỳ worker nào cũng có thể tự đặt `verified=true`, ranh giới ingress mất ý nghĩa.

Đường truyền nội bộ hoặc hàng đợi cần bảo vệ nguồn phát và tính toàn vẹn. Worker có thể đọc bản ghi đã lưu theo ID thay vì tin một cờ xác thực do message tùy ý mang tới.

### 7.2. Trạng thái tiếp nhận khác trạng thái áp dụng

Một mô hình đơn giản:

~~~text
RECEIVED_VERIFIED → PENDING_PROCESSING → APPLIED
                           |
                           ├── WAITING_RECONCILIATION
                           ├── BUSINESS_REJECTED
                           └── NEEDS_INTERVENTION
~~~

`BUSINESS_REJECTED` ở đây có thể nghĩa webhook không được dùng để thực hiện một chuyển trạng thái yêu cầu, không phải phủ nhận sự thật tài chính ở nguồn. Cần lưu hoặc chuyển nghĩa vụ ghi nhận sự thật đó tới đúng quy trình.

Ví dụ đơn đã hủy thì không mở giao hàng, nhưng khoản tiền đã thu vẫn cần được ghi nhận để đối soát hoặc xử lý tiếp.

### 7.3. Worker kiểm tra điều kiện hiện tại

Khi xử lý, worker cần đọc đối tượng trong đúng tenant và kiểm tra:

- Giao dịch nguồn có thuộc tài khoản đã cấu hình và đúng môi trường hay không.
- Số tiền, tiền tệ và liên kết đơn có đáp ứng quy tắc không.
- Fact đã được ghi nhận hoặc effect đã hoàn tất chưa.
- Trạng thái hiện tại cho phép chuyển trạng thái nào.
- Có sự kiện đảo, hủy hoặc điều chỉnh cần đối soát không.
- Nếu tạo hành động mới, quyền và thời hạn của hành động đó còn hợp lệ không.

Việc kiểm tra và cập nhật trong cùng cơ sở dữ liệu phải có ranh giới transaction hoặc điều kiện phiên bản để tránh race. Không kiểm tra đơn chưa hủy rồi gọi một thao tác riêng bỏ qua việc đơn vừa bị hủy.

### 7.4. Timeout sau tiếp nhận không tạo ý định mới

Nếu worker chết sau khi ghi bút toán nhưng trước khi đánh dấu hoàn tất, retry phải dùng cùng khóa tác động. Nếu gọi hệ thống ngoài và chưa biết kết quả, tiếp tục đối soát hoặc retry an toàn theo hợp đồng, không tạo effect key mới.

Một webhook còn mới không được trở thành lý do bỏ qua idempotency ở các bước hậu xử lý.

## 8. Sự kiện đến muộn và đường đối soát

### 8.1. Request ngoài cửa sổ không đồng nghĩa sự kiện giả

Một request có chữ ký đúng nhưng ngoài cửa sổ có thể do replay, đồng hồ lệch hoặc cách retry giữ nguyên chữ ký. Không thể chỉ dựa vào độ cũ để kết luận sự thật trong event chưa từng xảy ra.

Luồng nhận trực tiếp có thể từ chối áp dụng, đồng thời ghi bằng chứng phù hợp và tạo yêu cầu đối soát có giới hạn. Luồng này cần quyền, kiểm soát tài nguyên và khả năng theo dõi riêng.

### 8.2. Truy vấn qua cấu hình nguồn tin cậy

Khi cần đối soát, dùng endpoint API, tài khoản và credential đã được server cấu hình. Chỉ sử dụng định danh giao dịch sau khi đã kiểm tra phạm vi.

Không truy cập URL tùy ý trong webhook. Một trường có tên `resourceUrl` hoặc `verificationUrl` không tự chứng minh đích đó được phép, và có thể làm lộ dữ liệu hoặc tạo truy cập mạng ngoài ý định.

Cần giới hạn tần suất và gộp yêu cầu đối soát trùng. Request không xác thực không được kích hoạt vô hạn các cuộc gọi đặc quyền tới cổng thanh toán.

### 8.3. Đơn đã hủy nhưng thanh toán đã thu

Một kết quả xử lý đúng có thể là:

1. Xác minh khoản thu thực tế thuộc giao dịch và tài khoản mong đợi.
2. Ghi fact tài chính bằng khóa chống trùng phù hợp.
3. Giữ đơn ở trạng thái đã hủy nếu điều kiện mở lại không được thỏa mãn.
4. Tạo nghĩa vụ xử lý tiền đã thu theo chính sách, chẳng hạn chờ nhân viên quyết định hoặc hoàn tiền có kiểm soát.
5. Lưu bằng chứng về độ trễ, trạng thái hiện tại và quyết định.

Không tự hoàn tiền chỉ vì webhook đến muộn nếu nghiệp vụ yêu cầu kiểm tra khác. Không tự giao hàng chỉ vì webhook báo thu tiền thành công.

### 8.4. Không dùng thời gian sự kiện để bỏ sự thật bất lợi

Một event tranh chấp, đảo giao dịch hoặc điều chỉnh có thể đến sau một thời gian dài. Nếu tự đặt quy tắc “mọi event quá vài phút đều bỏ”, hệ thống có thể mất nghĩa vụ tài chính quan trọng.

Phân loại theo loại sự kiện và ngữ nghĩa. Cửa sổ xác thực của lần giao, thời gian chấp nhận một lệnh và vòng đời của một fact lịch sử là ba chính sách riêng.

## 9. Đồng hồ, khóa và giới hạn của giao thức

### 9.1. Ghi nhận thời điểm nhận ở ranh giới rõ ràng

`receivedAt` nên biểu diễn lúc request đã được nhận đầy đủ tại ranh giới tin cậy mà hệ thống chọn. Không lấy thời điểm mở kết nối rồi cho phép người gửi giữ body chưa hoàn tất trong thời gian không giới hạn.

Cần timeout đọc request, giới hạn kích thước và bảo vệ tài nguyên ingress. Nếu timestamp được ghi ở gateway, phải biết gateway đóng dấu khi nào, dữ liệu nào đã nhận xong và đường truyền tới ứng dụng được bảo vệ ra sao.

Các timestamp từ header chuyển tiếp không được tin chỉ vì tên header nghe giống dữ liệu hệ thống. Giá trị do client tự chèn phải bị loại bỏ hoặc không được dùng làm bằng chứng.

### 9.2. Khi đồng hồ không khỏe

Đồng hồ bên nhận lệch có thể khiến request hợp lệ trông quá cũ hoặc ở tương lai. Cần giám sát chênh lệch thời gian và sức khỏe đồng bộ giờ trên các node tham gia quyết định.

Khi một node không đủ tin cậy về thời gian, xử lý theo chính sách đã định: chuyển tiếp tới ingress khỏe, cách ly có lưu trách nhiệm hoặc hạn chế đường tiếp nhận trực tiếp. Không âm thầm bỏ kiểm tra freshness cho mọi request.

Đối với dữ liệu đã tiếp nhận hợp lệ, giữ nguyên bằng chứng. Một lần chỉnh đồng hồ sau đó không nên tự sửa lại các mốc cũ để làm chúng phù hợp với đồng hồ mới.

### 9.3. Xoay khóa có khoảng chuyển tiếp được kiểm soát

Khóa xác thực phải được quản lý theo endpoint, nguồn và môi trường. Nếu hỗ trợ key ID, chỉ dùng nó để chọn trong tập khóa được server cho phép; không tải khóa từ một URL tùy ý do request đưa vào.

Khi xoay khóa, cần chính sách rõ về khóa cũ, khoảng chồng lấn, thời điểm ngừng chấp nhận và cách xử lý retry. Không thử vô hạn mọi khóa của mọi tenant để tìm một chữ ký khớp.

Khóa bị lộ hoặc bị thu hồi vì sự cố cần được xử lý theo quy trình ứng cứu. Một timestamp còn mới không làm chữ ký từ khóa bị lộ trở nên đáng tin. Kẻ có khóa có thể tự tạo timestamp mới và payload mới.

Freshness giúp hạn chế replay request, không thay thế bảo vệ secret và quyền của bên ký.

### 9.4. Nếu giao thức không có timestamp được ký

Không thể tự thêm một header timestamp không được ký rồi tuyên bố đã có freshness mật mã cho lần giao.

Các biện pháp còn có thể dùng gồm xác thực nguồn theo cơ chế hỗ trợ, chống trùng theo event và business key, kiểm tra state machine, truy vấn nguồn có thẩm quyền và hạn chế tác động trực tiếp. Cần mô tả đúng giới hạn bảo đảm.

Nếu bên gửi chỉ ký thời điểm sự kiện, việc giới hạn tuổi của field đó là chính sách tuổi sự kiện, không tự trở thành chính sách tuổi của lần gửi. Nó có thể loại retry lịch sử hợp lệ và cần đường khôi phục phù hợp.

## 10. Nếu hệ thống của bạn là bên phát webhook

Khi tự thiết kế webhook, nên phân biệt event bất biến với envelope của từng lần giao:

~~~text
Event:
    eventId, occurredAt, eventType, resource reference, event data

Delivery:
    deliveryId, signedAt, endpoint binding, protocol version, signature
~~~

Một retry có thể tạo delivery mới theo giao thức trong khi giữ nguyên event ID và thời điểm sự việc. Bên nhận nhờ đó kiểm tra được lần giao còn mới mà vẫn nhận ra cùng sự kiện.

Các trường ảnh hưởng xác thực, thời gian và ngữ cảnh phải được bảo vệ theo thiết kế giao thức. Định nghĩa rõ bytes được ký, cách biểu diễn thời gian, phạm vi khóa, cách xoay khóa và hành vi khi cùng event được phát lại.

Không thay event ID ở mỗi retry chỉ để bên nhận không coi là trùng. Không đổi `occurredAt` thành thời gian gửi lại.

Nếu có nút redelivery quản trị, ghi ai yêu cầu, sự kiện gốc, lần giao mới và kết quả. Quyền phát lại không mặc nhiên là quyền tạo một giao dịch hoặc sự kiện nghiệp vụ mới.

Bên gửi cũng cần phân biệt “bên nhận đã tiếp nhận HTTP” với “nghiệp vụ của bên nhận đã hoàn thành”. Không dùng một phản hồi giao thành công làm bằng chứng thay cho quy trình xác nhận nghiệp vụ cần thiết.

## 11. Kiểm thử freshness và tình huống tấn công logic

Kiểm thử cần điều khiển được thời gian bên nhận, timestamp chữ ký, tuổi sự kiện, thứ tự giao và thời điểm worker xử lý.

| Tình huống | Cách kích hoạt | Kết quả cần chứng minh |
| --- | --- | --- |
| Sửa timestamp được ký | Giữ body, đổi thời gian trong phần được bảo vệ | Xác thực thất bại, không áp dụng |
| Header thời gian không được ký | Thay một header do client tùy ý gửi | Không dùng nó làm bằng chứng freshness |
| Quá cũ | Chữ ký đúng nhưng signedAt ngoài cửa sổ | Không vào luồng áp dụng mới; có xử lý phục hồi theo chính sách |
| Quá xa tương lai | signedAt vượt future skew | Không kéo dài hiệu lực tùy ý |
| Đúng ranh giới | Kiểm tra ngay tại và hai phía của max age, future skew | So sánh nhất quán theo đơn vị và quy tắc bao gồm biên |
| Sai đơn vị hoặc tràn số | Gửi mili giây ở nơi yêu cầu giây, số rất lớn | Từ chối định dạng, không đoán để chấp nhận |
| Replay trong cửa sổ | Gửi cùng request nhiều lần | Một sự kiện và một tác động nghiệp vụ |
| Retry có chữ ký mới | Giữ event ID, đổi delivery và signedAt hợp lệ | Nhận diện cùng sự kiện, không tạo tác động lại |
| Event mới cho cùng fact | Event ID khác nhưng cùng capture ID | Khóa nghiệp vụ ngăn bút toán trùng |
| Sự kiện cũ, lần giao mới | occurredAt cũ nhưng signedAt mới hợp lệ theo giao thức | Phân loại đúng; không loại fact chỉ vì tuổi sự kiện |
| Cùng event ID khác số tiền | Phát payload mâu thuẫn có nguồn hợp lệ | Không ghi đè im lặng, có đối soát hoặc cách ly |
| Hàng đợi chậm | Nhận đúng hạn, worker xử lý lâu sau đó | Dùng bằng chứng tiếp nhận; kiểm tra nghiệp vụ hiện tại riêng |
| Chết sau commit trước phản hồi | Sự kiện đã lưu nhưng nguồn chưa nhận HTTP response | Retry không tạo tiếp nhận hoặc effect mới |
| Chết sau bút toán | Worker chưa ghi trạng thái hoàn tất | Transaction và effect key ngăn cộng tiền lại |
| Body bị biến đổi | Parse rồi serialize hoặc đổi bytes trước verify | Kiểm tra theo đúng raw input mà giao thức yêu cầu |
| Giữ kết nối đọc chậm | Mở request sớm nhưng gửi body kéo dài | Có timeout và mốc nhận đầy đủ, không giữ hiệu lực bằng kết nối |
| Giả mốc từ gateway | Client chèn header timestamp nội bộ | Giá trị không được tin ngoài ranh giới cho phép |
| Chéo tenant hoặc tài khoản | Payload hoặc cấu hình nhắm tài khoản khác | Binding ngăn áp dụng ngoài phạm vi |
| Nhầm môi trường | Event thử nghiệm tới endpoint nghiệp vụ thật | Không tạo tác động thật nếu không đúng binding |
| Đơn bị hủy trước xử lý | PaymentCaptured tới sau khi hủy | Ghi nhận hoặc đối soát tiền, không tự mở giao hàng |
| Event điều chỉnh đến muộn | Giao tranh chấp hoặc đảo giao dịch lâu sau sự kiện gốc | Không bỏ nghĩa vụ bằng TTL của command |
| Khóa cũ trong chuyển tiếp | Ký bằng khóa theo các mốc chính sách xoay | Chấp nhận hoặc từ chối đúng phạm vi, không thử khóa tùy tiện |
| Khóa bị thu hồi | Timestamp mới nhưng khóa không còn được phép | Không tin chỉ nhờ độ mới |
| Đồng hồ một node bị lệch | Cho node kiểm tra thời gian sai | Phát hiện và xử lý theo chính sách, không nới cửa sổ vô hạn |
| Request lỗi kích hoạt đối soát | Gửi nhiều event ID hoặc URL giả | Không gọi đặc quyền vô hạn hoặc truy cập URL tùy ý |
| Dọn inbox sớm | Retry sau khi cache hoặc inbox bị dọn | Lớp bằng chứng tác động vẫn ngăn trùng |

Với cửa sổ thời gian, dùng clock có thể điều khiển trong kiểm thử, không chờ nhiều phút theo đồng hồ thực. Cần kiểm thử cả request hợp lệ bị trì hoãn và replay chủ động.

Với unique constraint, transaction và concurrency, dùng cơ sở dữ liệu thực tế của hệ thống. Với nguồn bên ngoài, môi trường kiểm thử hoặc bộ giả lập cần tái hiện được retry giữ chữ ký cũ, ký lại lần giao và timeout sau khi sự thật đã phát sinh.

Kiểm tra số bút toán, effect record, trạng thái đơn và nghĩa vụ đối soát, không chỉ response HTTP. Một request bị từ chối đúng ở ingress vẫn có thể cần được theo dõi như một tín hiệu sự cố tích hợp.

## 12. Quan sát ba loại độ trễ riêng biệt

### 12.1. Tuổi lần giao

~~~text
deliveryAge = receivedAt - signedAt
~~~

Chỉ số này dùng với timestamp có ngữ nghĩa phù hợp và đã được xác thực. Phân bố tăng bất thường có thể phản ánh độ trễ mạng, cách retry hoặc lệch đồng hồ.

### 12.2. Tuổi sự kiện khi tiếp nhận

~~~text
eventAgeAtIntake = receivedAt - occurredAt
~~~

Tuổi lớn có thể là backlog hoặc redelivery lịch sử hợp lệ. Không tự dùng cùng ngưỡng của delivery age để loại mọi event.

Cũng cần lưu ý độ tin cậy và đồng bộ của các nguồn thời gian trước khi diễn giải giá trị như một phép đo chính xác.

### 12.3. Độ trễ xử lý nội bộ

~~~text
processingLag = processedAt - receivedAt
~~~

Chỉ số này phản ánh khả năng xử lý sau tiếp nhận. Tăng worker hoặc sửa backlog có thể giảm nó; nới cửa sổ chữ ký không giải quyết được nút thắt đó.

Theo dõi thêm:

- Tỷ lệ lỗi chữ ký, quá cũ, quá tương lai và lỗi schema.
- Số delivery trùng, event trùng và xung đột nội dung.
- Số sự kiện chờ đối soát, tuổi chờ cũ nhất và kết quả khôi phục.
- Số tác động bị chặn do trạng thái hiện tại hoặc version.
- Lỗi ánh xạ tài khoản, môi trường và tenant.
- Lịch sử xoay khóa và số request dùng khóa không được phép.
- Chênh lệch giữa sổ cái, trạng thái đơn và dữ liệu nguồn.

Log nên liên kết endpoint, nguồn, tài khoản, event ID, delivery ID nếu có và mã giao dịch. Không đưa secret ký, credential API hoặc toàn bộ thông tin thanh toán nhạy cảm vào log.

## 13. Phục hồi và ví dụ đầy đủ

### 13.1. Khi nhiều webhook bị coi là cũ

Một quy trình xử lý có thể là:

1. Xác định endpoint, nguồn và loại lỗi: chữ ký, timestamp, đồng hồ hay độ trễ.
2. Kiểm tra timestamp được ký có thực sự biểu diễn lần giao không.
3. Đối chiếu receivedAt ở ranh giới tin cậy và sức khỏe đồng hồ các node.
4. Xác định sự kiện nào đã được nhận, đã tạo effect hoặc đang chờ.
5. Yêu cầu redelivery theo khả năng nguồn hoặc truy vấn đối soát qua cấu hình tin cậy.
6. Giữ event ID, khóa nghiệp vụ và lịch sử nguồn; không tạo giao dịch mới để làm dữ liệu trông mới.
7. Theo dõi đến khi các nghĩa vụ còn mở được giải quyết theo quyền.

Nếu phải sửa cấu hình cửa sổ, cần dựa trên nguyên nhân và phạm vi đã xác định. Không tắt kiểm tra chữ ký hoặc thời gian toàn hệ thống để “cho dữ liệu chạy qua”.

### 13.2. Một sự kiện thu tiền tới sau khi đơn đã hủy

Giả sử nguồn hỗ trợ ký mới cho mỗi lần giao:

~~~text
10:00  PaymentCaptured xảy ra ở cổng thanh toán.
10:10  Đơn bị hủy trong ứng dụng.
10:30  Nguồn ký retry cho cùng event và gửi webhook.
10:30  Ingress nhận đầy đủ, xác thực chữ ký và cửa sổ thời gian.
10:31  Một bản sao của request được gửi lại.
11:00  Worker mới xử lý do backlog.
~~~

Kết quả đúng:

- Lần giao 10:30 có thể hợp lệ về freshness, dù sự kiện đã 30 phút tuổi.
- Request lặp 10:31 không tạo thêm sự kiện cần áp dụng hoặc bút toán mới.
- Worker 11:00 dùng bằng chứng tiếp nhận 10:30, không giả vờ request vừa tới hoặc loại nó chỉ vì chữ ký gốc lúc này đã cũ.
- Khoản thu được kiểm chứng và ghi nhận theo đúng giao dịch, tài khoản, tiền tệ và khóa tác động.
- Đơn vẫn chịu state machine hiện tại; không tự mở lại giao hàng.
- Nghĩa vụ xử lý tiền của đơn đã hủy được chuyển tới quy trình có quyền phù hợp.

Một bản request bị phát lại quá cửa sổ không được tạo thêm tác động. Nếu cần khôi phục một fact chưa được ghi nhận, hệ thống đi qua đường đối soát có bằng chứng thay vì sửa timestamp.

Freshness bảo vệ tính hợp lệ theo thời gian của một lần giao. Idempotency bảo vệ trước việc giao và xử lý lặp. State machine, quyền theo đối tượng và transaction quyết định một sự kiện được phép thay đổi điều gì ở nghiệp vụ hiện tại.
