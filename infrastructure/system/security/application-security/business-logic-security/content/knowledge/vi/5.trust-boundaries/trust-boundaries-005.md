# Partner integration boundary — Ranh giới tin cậy khi tích hợp đối tác

## 1. Mục tiêu và phạm vi

Trong chương **Trust Boundaries**, ranh giới tích hợp đối tác là nơi dữ liệu, danh tính và yêu cầu đi giữa hệ thống của bạn với một tổ chức khác. Hai bên có thể có hợp đồng và kết nối được xác thực, nhưng không vì thế có cùng quyền quyết định trên mọi đối tượng hoặc mọi quy tắc nghiệp vụ.

Trong phạm vi Business Logic Security, câu hỏi chính là: **thông tin hoặc lệnh từ đối tác được phép tạo ra thay đổi nghiệp vụ nào, trên đối tượng nào, với điều kiện gì?** Cần trả lời câu hỏi này trước khi để callback đổi trạng thái đơn, phản hồi API cập nhật giá hoặc thông báo giao hàng kích hoạt chi trả.

Sau bài học, bạn có thể:

- Xác định ranh giới ở API gọi vào, lời gọi ra ngoài, webhook và công việc bất đồng bộ.
- Phân biệt xác thực nguồn với thẩm quyền trên đối tượng và quyền quyết định nghiệp vụ.
- Gắn tài khoản tích hợp, môi trường, tổ chức và mã đối tượng ngoài với bản ghi nội bộ.
- Chuyển dữ liệu đối tác thành bằng chứng hoặc lệnh nội bộ có phạm vi rõ ràng.
- Xử lý gửi lại, sự kiện sai thứ tự, kết quả chưa rõ và thay đổi hợp đồng tích hợp.
- Thiết kế kiểm thử chứng minh một đối tác được xác thực vẫn không vượt phạm vi được cấp.

Ví dụ xuyên suốt dùng đối tác vận chuyển. Những trạng thái và chính sách được nêu là giả định để học thiết kế; triển khai thực tế phải tuân theo giao thức và ý nghĩa dữ liệu của từng nhà cung cấp.

## 2. Vì sao đối tác vẫn nằm bên ngoài ranh giới quyết định của bạn?

Hệ thống đối tác có quản trị, tài khoản dịch vụ, chu kỳ triển khai và nguồn dữ liệu riêng. Nó có thể gặp lỗi, bị chiếm quyền, cấu hình sai hoặc hiểu một trạng thái khác với cách ứng dụng của bạn đang hiểu.

Ngay cả khi đối tác hoạt động đúng, một giá trị hợp lệ ở phía họ có thể chưa đủ để thực hiện hành động ở phía bạn. “Đã giao” có thể là bằng chứng vận chuyển được chấp nhận, nhưng chưa đồng nghĩa “mọi điều kiện chi trả cho người bán đều đã đạt”.

OWASP API10:2023 cảnh báo việc áp dụng kiểm soát yếu hơn cho dữ liệu API bên thứ ba vì coi nguồn đó đáng tin sẵn. Dữ liệu nhận về vẫn cần được kiểm tra phù hợp với cách ứng dụng sử dụng nó. [Nguồn: OWASP Unsafe Consumption of APIs](https://api-security.owasp.org/editions/2023/en/0xaa-unsafe-consumption-of-apis/).

### 2.1. Bốn câu hỏi cần giữ riêng

| Câu hỏi | Ví dụ | Điều chưa được chứng minh |
| --- | --- | --- |
| Ai gửi? | Thông báo được xác thực là từ tài khoản đối tác `A-03` | Tài khoản đó được cập nhật mọi đơn |
| Họ được tác động tới đâu? | `A-03` có quyền báo trạng thái cho các chuyến đã liên kết | Họ được sửa giá hoặc duyệt hoàn tiền |
| Dữ liệu có ý nghĩa gì? | Đối tác báo chuyến `EXT-73` đã giao | Đã giao đủ mọi dòng trong đơn hoặc không còn tranh chấp |
| Hệ thống được làm gì tiếp? | Ghi bằng chứng và đánh giá điều kiện nội bộ | Tự động bỏ qua bước duyệt hoặc phát tiền |

Một chữ ký hợp lệ trả lời câu hỏi về nguồn và tính toàn vẹn theo giao thức. Nó không tự trả lời tất cả những câu còn lại.

### 2.2. Ranh giới xuất hiện theo cả hai chiều

- **Gọi vào:** đối tác gọi API của bạn để tạo hoặc cập nhật nghiệp vụ.
- **Gọi ra:** ứng dụng gửi yêu cầu tới đối tác rồi sử dụng phản hồi.
- **Callback/webhook:** đối tác chủ động thông báo kết quả sau một khoảng thời gian.
- **Bất đồng bộ:** dữ liệu đã nhận đi tiếp qua inbox, queue, worker và service nội bộ.
- **Quản trị tích hợp:** đăng ký endpoint, cấp quyền, đổi khóa, chuyển môi trường hoặc ngừng hợp tác.

Thông tin không tự mất nguồn gốc bên ngoài chỉ vì đã được lưu vào database hoặc chuyển thành thông điệp trên queue nội bộ.

## 3. Ví dụ xuyên suốt: đối tác vận chuyển báo giao hàng

Giả sử hệ thống bán hàng hỗ trợ nhiều cửa hàng, mỗi cửa hàng có `tenantId`. Đơn `O-605` thuộc `T-01`, có một phần fulfillment được gửi qua đối tác `P-07`, tài khoản tích hợp `A-03`, trong môi trường `PRODUCTION`.

Máy chủ đã tạo liên kết:

```text
partnerId             = P-07
integrationAccountId  = A-03
environment           = PRODUCTION
externalShipmentId    = EXT-73

internalShipmentId    = SH-91
orderId               = O-605
tenantId              = T-01
authorizedContent     = snapshot hàng và người nhận đã chấp nhận
```

Đối tác gửi một sự kiện minh họa:

```json
{
  "eventId": "EV-842",
  "eventType": "shipment.delivered",
  "shipmentId": "EXT-73",
  "occurredAt": "2026-11-21T02:30:00Z"
}
```

Theo chính sách giả định, tài khoản `A-03` được gửi bằng chứng trạng thái cho những chuyến thuộc liên kết của nó. Nó không được tự chọn đơn nội bộ tùy ý, đổi người nhận, sửa tổng tiền hoặc đánh dấu một khoản chi trả đã được phê duyệt.

### 3.1. Dữ liệu nào thuộc thẩm quyền của ai?

| Dữ liệu hoặc quyết định | Nguồn có thể được chấp nhận trong ví dụ | Kiểm tra trước khi sử dụng |
| --- | --- | --- |
| Mã chuyến và trạng thái vận chuyển ngoài | Đối tác được xác thực, trong đúng tài khoản/môi trường | Liên kết nội bộ, loại sự kiện và hợp đồng dữ liệu |
| Tenant và đơn nội bộ bị tác động | Bản ghi liên kết do hệ thống quản lý | Không lấy từ trường tự khai trong payload |
| Nội dung hàng và người nhận đã cho phép | Snapshot fulfillment nội bộ | Đúng phiên bản, phạm vi và ý định |
| Giá bán, giảm giá, tổng tiền đơn | Dữ liệu và chính sách thương mại nội bộ | Không ghi đè bằng dữ liệu vận chuyển |
| Điều kiện hoàn tiền hoặc chi trả | Quy tắc, trạng thái và phê duyệt nội bộ | Bằng chứng vận chuyển chỉ là một đầu vào |
| Phí vận chuyển do đối tác báo | Hợp đồng báo giá/tính phí được hệ thống chấp nhận | Đơn vị tiền, phạm vi phí, giới hạn và đối soát theo chính sách |

Tin cậy cần được xác định theo loại thông tin và phạm vi sử dụng, thay vì một nhãn chung “đối tác đáng tin”.

### 3.2. Chữ ký không chứng minh sự kiện ngoài đời là đúng

Nếu hệ thống đối tác hoặc khóa của họ bị chiếm, thông báo giả vẫn có thể mang chữ ký hợp lệ theo cơ chế xác thực nguồn. Chữ ký giúp xác định thông báo đến từ một bên nắm quyền ký; nó không tự chứng minh kiện hàng đã tới tay người nhận.

Nếu quyết định tiếp theo có giá trị lớn hoặc khó đảo ngược, chính sách có thể yêu cầu thêm bằng chứng, thời gian chờ, đối chiếu hoặc xem xét độc lập. Phạm vi chấp nhận rủi ro này cần được nêu rõ, không che giấu dưới việc “đã verify signature”.

## 4. Mô hình danh tính và quyền tích hợp

### 4.1. Định danh đối tác cần đủ ngữ cảnh

`partnerId` xác định tổ chức tích hợp, nhưng thường chưa đủ. Một đối tác có thể có nhiều tài khoản, nhiều cửa hàng được ủy quyền, nhiều endpoint và hai môi trường thử nghiệm/thật.

Ngữ cảnh đáng tin có thể bao gồm:

```text
partnerId
integrationAccountId
environment
credential hoặc certificate được xác minh
các năng lực được cấp
phạm vi tenant/đối tượng
trạng thái hoạt động và phiên bản cấu hình quyền
```

Khóa cụ thể đang dùng để ký là một phần của việc xác thực và truy vết. Tài khoản tích hợp ổn định là danh tính nghiệp vụ; đổi khóa không nên tự tạo một “đối tác mới” có không gian chống trùng trống.

### 4.2. Xác thực kết nối và phân quyền là hai bước

| Cơ chế | Điều có thể chứng minh khi triển khai đúng | Điều vẫn phải kiểm tra |
| --- | --- | --- |
| API key | Người gọi đang có bí mật được cấp | Bí mật thuộc tài khoản nào, năng lực và phạm vi đối tượng |
| mTLS | Danh tính kết nối theo chứng thư và cấu hình tin cậy | Chứng thư đó được phép gọi hành động nào |
| Access token | Những xác nhận theo issuer, audience và hồ sơ token đã kiểm tra | Quyền hiện hành và quan hệ với tài nguyên cụ thể |
| Chữ ký webhook | Nguồn và tính toàn vẹn của phần dữ liệu được giao thức bảo vệ | Freshness nếu có, chống trùng, liên kết và điều kiện nghiệp vụ |

Không chấp nhận token chỉ vì chữ ký đúng; việc kiểm tra phải theo đúng loại token và giao thức. Không lấy một header `X-Partner-Id` làm danh tính đáng tin nếu bên ngoài có thể tự gửi nó.

OWASP Microservices Security phân biệt danh tính bên gọi với ngữ cảnh người dùng và nhấn mạnh kiểm soát tại service có ngữ cảnh tài nguyên. Nguyên tắc này cũng hữu ích cho adapter nhận dữ liệu đối tác trước khi gọi dịch vụ nghiệp vụ. [Nguồn: OWASP Microservices Security](https://cheatsheetseries.owasp.org/cheatsheets/Microservices_Security_Cheat_Sheet.html).

### 4.3. Trường “khách hàng được đại diện” cần quyền đại diện

Trong một tích hợp B2B, đối tác có thể gửi lệnh thay một cửa hàng hoặc khách hàng. Việc xác thực đối tác không tự chứng minh họ được đại diện cho bất kỳ chủ thể nào được ghi trong request.

Máy chủ phải kiểm tra quan hệ cấp quyền giữa tài khoản tích hợp, hành động, chủ thể được đại diện và đối tượng. Ngữ cảnh đó cần được giữ riêng với danh tính dịch vụ đối tác; không thay mọi người gọi thành `SYSTEM` rồi mất dấu nguồn quyết định.

## 5. Liên kết đối tượng ngoài với đối tượng nội bộ

### 5.1. Mã đối tượng không có ý nghĩa toàn cục mặc định

Mã `EXT-73` có thể trùng ở hai tài khoản hoặc ở môi trường thử nghiệm và thật. Tra cứu chỉ theo mã này có thể nối một callback hợp lệ vào sai đơn.

Khóa tra cứu trong ví dụ là:

```text
(partnerId, integrationAccountId, environment, externalShipmentId)
```

Phạm vi duy nhất phải theo hợp đồng của nhà cung cấp. Nếu họ có thể tái sử dụng mã đối tượng trong một vòng đời khác, cần biểu diễn thêm thế hệ hoặc liên kết vòng đời phù hợp; không mặc định mã theo dõi luôn duy nhất mãi mãi.

### 5.2. Tenant và đơn được suy ra từ liên kết đã được tạo hợp lệ

Khi nhận webhook, máy chủ xác thực tài khoản rồi tìm liên kết trong phạm vi tài khoản đó. Từ liên kết, nó tải `tenantId`, `orderId` và shipment nội bộ.

Không ưu tiên `tenantId` hoặc `orderId` do payload tự khai hơn liên kết nội bộ. Nếu hợp đồng có các trường tham chiếu đó, có thể đối chiếu để phát hiện mâu thuẫn; chúng không thay thế kiểm tra liên kết.

Một tenant trên URL có thể hỗ trợ định tuyến hoặc tìm cấu hình xác thực. Nó vẫn cần được ràng buộc với danh tính được xác minh và đối tượng đích; đổi URL không được làm đối tác A tác động vào tenant B.

### 5.3. Việc tạo và sửa liên kết cũng cần bảo vệ

Nếu một API khác cho phép tùy ý gắn mã chuyến ngoài vào đơn bất kỳ, bước tra cứu webhook có đúng vẫn có thể tác động sai. Tạo liên kết phải xuất phát từ ý định fulfillment được phép hoặc quy trình đối soát được kiểm soát.

Cần ngăn việc chiếm liên kết của tài khoản khác, đổi môi trường của liên kết hoặc chuyển một mã chuyến đang hoạt động sang đơn khác mà thiếu quyết định nghiệp vụ. Lịch sử liên kết và phiên bản cấu hình giúp giải thích một thông báo đã được áp dụng trong ngữ cảnh nào.

## 6. Tiếp nhận dữ liệu qua ranh giới theo từng lớp

Một pipeline khái niệm cho webhook:

```text
1. Áp giới hạn sớm: kích thước, thời gian đọc và tài nguyên xử lý.
2. Chọn cấu hình xác minh từ tập cấu hình được máy chủ quản lý.
3. Xác minh giao thức nguồn trên dữ liệu chính xác mà giao thức yêu cầu.
4. Dựng danh tính tài khoản tích hợp và môi trường đã xác minh.
5. Parse/validate hợp đồng dữ liệu, loại sự kiện và phiên bản được hỗ trợ.
6. Kiểm tra năng lực nhận thông báo và tra cứu liên kết đúng phạm vi.
7. Tiếp nhận bền vững với định danh chống trùng phù hợp.
8. Đánh giá quy tắc và áp dụng thay đổi nội bộ theo transaction.
9. Phát công việc tiếp theo qua outbox khi cần.
```

Các bước có thể được bố trí khác tùy giao thức và kiến trúc, nhưng không được bỏ mất điều kiện bảo vệ tương ứng. Chẳng hạn, có thể parse tối thiểu một trường phục vụ chọn khóa nếu giao thức yêu cầu, song dữ liệu đó chỉ là gợi ý tìm cấu hình, chưa phải danh tính đáng tin.

### 6.1. Xác minh đúng giao thức của nhà cung cấp

Ưu tiên thư viện xác minh được nhà cung cấp duy trì khi có. Nếu giao thức ký raw body, cần giữ đúng byte body để xác minh; parse rồi serialize lại JSON không bảo đảm giữ nguyên dữ liệu đã ký.

Không tự thêm quy tắc ký, bỏ qua phần bắt buộc, chấp nhận thuật toán dự phòng tùy ý hoặc tắt xác minh khi gặp lỗi. Một header chứa tên khóa chỉ được chọn trong kho cấu hình tin cậy có giới hạn; không vì `keyId` hay URL do request đưa vào mà tải khóa từ địa chỉ bất kỳ.

Các giao thức không bảo vệ cùng những thành phần. Phải biết event ID, timestamp hoặc metadata nào thực sự được xác thực. OWASP Webhook Security phân biệt việc xác minh nguồn, chống replay và chống xử lý trùng, đồng thời khuyến nghị tuân theo định dạng ký của nhà cung cấp. [Nguồn: OWASP Webhook Security](https://cheatsheetseries.owasp.org/cheatsheets/Webhook_Security_Cheat_Sheet.html).

### 6.2. Tách thời điểm giao thông báo khỏi thời điểm sự kiện

`occurredAt` mô tả thời điểm mà đối tác báo sự kiện xảy ra. Timestamp của lần giao, nếu được giao thức ký bảo vệ, phục vụ một mục đích khác: đánh giá độ mới của lần giao đó.

Một sự kiện nghiệp vụ cũ có thể được gửi lại bằng một lần giao hợp lệ mới. Không dùng việc `occurredAt` đã xa để kết luận chữ ký không hợp lệ hoặc bỏ qua mọi bằng chứng đến muộn.

Ngược lại, một timestamp mới do người gửi tự khai nhưng không được bảo vệ không tự tạo khả năng chống replay. Nếu giao thức không có timestamp được xác thực, phải hiểu giới hạn đó và dựa thêm vào lưu định danh xử lý cùng các ràng buộc nghiệp vụ.

### 6.3. Schema đúng chưa đủ; ngữ nghĩa cũng phải đúng

Kiểm tra cấu trúc cần giới hạn chuỗi, số phần tử, miền giá trị, enum và phiên bản hợp đồng. Cần có cách xử lý rõ cho trường dư: trường nào được phép bỏ qua, trường nào phải từ chối để tránh ghi đè dữ liệu nhạy cảm.

Sau đó kiểm tra ngữ nghĩa:

- Sự kiện này có áp dụng cho loại đối tượng đã liên kết không?
- Số lượng, đơn vị đo, số tiền hoặc loại tiền có cùng ý nghĩa với hợp đồng không?
- Trường thời gian và phiên bản có đủ giá trị để sử dụng theo cách dự định không?
- Dữ liệu có mâu thuẫn với snapshot, trạng thái hoặc quyết định nội bộ không?

Tránh để hai parser hoặc hai tầng hiểu khác nhau một trường quan trọng. Một tên trạng thái chưa được hỗ trợ không nên rơi vào nhánh mặc định mang ý nghĩa thành công.

### 6.4. Dữ liệu tự do vẫn cần xử lý an toàn ở nơi sử dụng

Tên người nhận, ghi chú, mô tả lỗi và tên tệp từ đối tác vẫn là nội dung bên ngoài. Lưu nó trong database không làm nó an toàn để ghép SQL, hiển thị HTML hoặc ghi thành dòng log tùy ý.

Dùng truy vấn tham số hóa, xử lý đầu ra theo ngữ cảnh và cách ghi log phù hợp. Các biện pháp này bảo vệ kỹ thuật lưu/hiển thị; chúng bổ sung cho kiểm tra quyền và quy tắc nghiệp vụ, không thay thế chúng.

## 7. Ví dụ Java: chuyển thông báo thành bằng chứng có phạm vi

Một adapter nên ánh xạ những trường đã được chấp nhận sang cấu trúc nội bộ có chủ đích. Không gán toàn bộ JSON bên ngoài trực tiếp vào entity `Order`.

Đoạn Java sau chỉ minh họa bước ánh xạ sau xác minh và kiểm tra schema. Các định danh bắt buộc được giả định không rỗng; thời gian và độ dài chuỗi đã được kiểm tra. Lớp xác thực mới được dựng `VerifiedPartnerContext`; tên kiểu dữ liệu tự nó không chứng minh nguồn đáng tin.

```java
import java.time.Instant;
import java.util.UUID;

enum IntegrationEnvironment { SANDBOX, PRODUCTION }

record VerifiedPartnerContext(
        UUID partnerId,
        UUID accountId,
        IntegrationEnvironment environment,
        boolean deliveryEventsAllowed) {}

record PartnerNotice(
        String eventId,
        String externalShipmentId,
        String eventType,
        Instant occurredAt) {}

record ShipmentBinding(
        UUID partnerId,
        UUID accountId,
        IntegrationEnvironment environment,
        String externalShipmentId,
        UUID tenantId,
        UUID orderId,
        UUID shipmentId,
        long revision,
        boolean active) {}

record DeliveryEvidenceCandidate(
        VerifiedPartnerContext source,
        UUID tenantId,
        UUID orderId,
        UUID shipmentId,
        String sourceEventId,
        long bindingRevision,
        Instant reportedOccurredAt) {}

final class PartnerDeliveryMapper {
    static DeliveryEvidenceCandidate map(
            VerifiedPartnerContext source,
            PartnerNotice notice,
            ShipmentBinding binding) {

        if (!source.deliveryEventsAllowed()) {
            throw new IllegalStateException("PARTNER_CAPABILITY_DENIED");
        }
        if (!binding.active()
                || !source.partnerId().equals(binding.partnerId())
                || !source.accountId().equals(binding.accountId())
                || source.environment() != binding.environment()
                || !notice.externalShipmentId()
                          .equals(binding.externalShipmentId())) {
            throw new IllegalStateException("SHIPMENT_SCOPE_MISMATCH");
        }
        if (!"shipment.delivered".equals(notice.eventType())) {
            throw new IllegalStateException("UNSUPPORTED_EVENT_TYPE");
        }

        return new DeliveryEvidenceCandidate(
                source,
                binding.tenantId(),
                binding.orderId(),
                binding.shipmentId(),
                notice.eventId(),
                binding.revision(),
                notice.occurredAt());
    }
}
```

Những điểm quan trọng của ánh xạ:

1. Tenant, đơn và shipment nội bộ đến từ liên kết, không từ thông báo tự khai.
2. Tài khoản và môi trường phải khớp, kể cả khi mã shipment giống nhau.
3. Loại sự kiện được xử lý theo danh sách có chủ đích.
4. Thời điểm từ đối tác được giữ dưới tên `reportedOccurredAt`, không bị biến thành thời điểm máy chủ đã xác minh.
5. Kết quả là ứng viên bằng chứng giao hàng, không phải lệnh chi trả, hoàn tiền hay bỏ bước duyệt.
6. `bindingRevision` được giữ để lớp áp dụng có thể phát hiện liên kết đã đổi trước khi ghi.

Hàm chưa thực hiện chống trùng, transaction hay chính sách chấp nhận bằng chứng. `deliveryEventsAllowed` phải được tính từ cấu hình quyền đáng tin và có hiệu lực theo hợp đồng thu hồi; không lấy từ payload.

Nếu một service nội bộ khác nhận cấu trúc tương tự qua mạng, service đó vẫn cần xác thực bên gọi và kiểm tra phạm vi. Không vì dữ liệu có tên `Verified...` mà tin một client bất kỳ được tự dựng nó.

## 8. Trạng thái đối tác là bằng chứng, không phải bản sao của trạng thái nội bộ

### 8.1. Không ánh xạ enum một cách máy móc

Các trạng thái của hai bên có thể khác ý nghĩa:

| Thông tin nhận từ đối tác | Cách sử dụng có kiểm soát | Điều không tự xảy ra |
| --- | --- | --- |
| Đã tiếp nhận yêu cầu tạo chuyến | Ghi nhận tiến trình đặt vận chuyển | Không khẳng định hàng đã được bàn giao |
| `shipment.delivered` | Ghi bằng chứng cho shipment đã liên kết | Không mặc định mọi phần của đơn đều đã giao |
| Hủy chuyến | Kiểm tra trạng thái, phạm vi và kết quả thực tế | Không tự hoàn tiền hoặc xóa lịch sử đã giao |
| Có điều chỉnh phí | Lưu đề nghị/chi tiết phí để kiểm tra | Không ghi đè giá bán hoặc hạn mức khách |
| Không tìm thấy đối tượng | Điều tra trạng thái liên kết hoặc đồng bộ | Không kết luận tác dụng trước đó chưa từng xảy ra |

Một schema nhận được enum đúng chính tả không chứng minh bước chuyển được phép. Quy tắc cần kiểm tra trên trạng thái nội bộ tại thời điểm áp dụng.

### 8.2. Sự kiện sai thứ tự và điều chỉnh hợp lệ

Nếu đã nhận bằng chứng giao hàng, một thông báo `in_transit` đến muộn không nên kéo tiến trình ngược chỉ vì nó được nhận sau. Chỉ dùng sequence hoặc phiên bản ngoài để so sánh khi nhà cung cấp có bảo đảm tương ứng, đúng phạm vi tài nguyên.

Timestamp đơn thuần không nhất thiết xác định thứ tự. Nếu không có thông tin thứ tự đủ mạnh, có thể cần tra cứu trạng thái theo API đối tác, áp dụng quy tắc chuyển trạng thái an toàn và đối soát các mâu thuẫn.

Không phải mọi trạng thái đều nằm trên một thang chỉ tăng. Đối tác có thể có sự kiện sửa sai hoặc rút lại một xác nhận. Nếu hợp đồng hỗ trợ điều đó, cần mô hình sự kiện điều chỉnh và đánh giá tác động, thay vì bỏ qua vĩnh viễn vì “đã đạt trạng thái cao nhất”.

### 8.3. Đối tượng nội bộ đã bị hủy vẫn có thể có sự kiện thật đến muộn

Một shipment có thể được đối tác giao dù đơn nội bộ đã có yêu cầu hủy. Không nên xóa bỏ bằng chứng thật để giữ giao diện nhất quán, nhưng cũng không được tự đặt đơn trở lại trạng thái trả tiền hoặc mở lại quyền đã thu hồi.

Cần lưu bằng chứng, đánh dấu mâu thuẫn và đưa vào quy trình xử lý như đối soát, thu hồi hoặc xem xét. Quyết định nào còn hợp lệ phải theo máy trạng thái nội bộ và điều kiện của nghiệp vụ.

## 9. Chống replay, chống trùng và tính nguyên tử

### 9.1. Có ba định danh cần phân biệt

| Định danh | Vai trò | Giới hạn |
| --- | --- | --- |
| Lần giao thông báo | Nhận biết một lần HTTP delivery | Có thể thay đổi ở mỗi lần retry |
| Sự kiện logic của đối tác | Nhận biết cùng một sự kiện được gửi lại | Có thể khác giữa hai thông báo cùng mô tả một kết quả nghiệp vụ |
| Quyết định/tác dụng nghiệp vụ | Ngăn cùng một quyền hoặc lợi ích được áp dụng lại | Phải được hệ thống định nghĩa đúng đơn vị |

Một lần ký hợp lệ không ngăn dữ liệu bị gửi lại. Kiểm tra độ mới, nếu giao thức hỗ trợ, cũng không thay cho lưu trạng thái đã xử lý trong cửa sổ retry và lịch sử cần thiết.

### 9.2. Không gian chống trùng phải theo danh tính ổn định

Nếu event ID được đảm bảo duy nhất trong một tài khoản, có thể dùng:

```text
UNIQUE (
  partner_id,
  integration_account_id,
  environment,
  external_event_id
)
```

Các cột trong khóa cần bắt buộc có dữ liệu. Không dùng riêng `external_event_id` nếu hai tài khoản có thể trùng mã. Không dùng key ID làm ranh giới duy nhất, vì thay khóa không được mở lại khả năng áp dụng sự kiện cũ.

Nếu định danh không nằm trong phần được giao thức bảo vệ, phải hiểu rằng nó không có cùng bảo đảm chống giả mạo/replay như một định danh đã được xác thực. Ràng buộc nghiệp vụ phía sau vẫn cần chặn hiệu ứng lặp.

Cùng event ID nhưng nội dung có ý nghĩa khác cần được phát hiện theo hợp đồng, không im lặng ghi đè. Có thể lưu dấu vân tay ngữ nghĩa đã chuẩn hóa; hash raw body phục vụ truy vết không tự chứng minh hai JSON khác khoảng trắng là hai sự kiện khác nhau.

### 9.3. ACK chỉ sau khi đã nhận bền vững theo hợp đồng

Nếu trả phản hồi nhận thành công trước khi lưu sự kiện rồi tiến trình dừng, đối tác có thể coi công việc đã giao xong trong khi ứng dụng làm mất nó.

Một mô hình inbox:

```text
Xác minh nguồn, hợp đồng và ngữ cảnh
  → transaction chèn inbox với khóa duy nhất
  → lưu công việc xử lý bền vững trong cùng cơ chế nhất quán
  → commit
  → ACK theo hợp đồng
```

Với bản trùng đã được nhận bền vững, trả kết quả phù hợp mà không tạo thêm công việc độc lập. Nếu lưu thất bại, không báo đã tiếp nhận thành công. Phản hồi cần theo giao thức và không lộ cấu hình khóa hoặc chi tiết nội bộ.

Nếu chưa tìm thấy liên kết, không tạo hoặc sửa đơn từ mã tự khai. Có thể cách ly sự kiện đã xác thực trong vùng có giới hạn để đối soát, vì callback có thể đến trước khi kết quả tạo đối tượng ngoài được lưu xong. Cơ chế phục hồi phải dựa vào ý định hoặc tham chiếu đã được máy chủ tạo hợp lệ.

### 9.4. Transaction khi áp dụng sự kiện

Worker xử lý inbox nên:

```text
BEGIN TRANSACTION
  1. Nhận quyền xử lý bản ghi và kiểm tra trạng thái chưa hoàn tất.
  2. Tải đối tượng và liên kết trong đúng phạm vi.
  3. Kiểm tra phiên bản liên kết, điều kiện chặn và chính sách còn áp dụng.
  4. Ghi bằng chứng hoặc chuyển trạng thái được phép.
  5. Ghi kết quả xử lý inbox và outbox liên quan.
COMMIT
```

Nếu ghi “đã xử lý” trước thay đổi rồi bị lỗi, có thể mất công việc. Nếu thay đổi trước nhưng ghi trạng thái xử lý trong transaction khác, crash có thể khiến nó chạy lại. Transaction và ràng buộc nghiệp vụ cần bảo vệ cả hai phía.

Khi công việc tiếp theo có tác dụng ngoài cơ sở dữ liệu, dùng ý định/outbox và cơ chế chống trùng riêng phù hợp. Inbox không tự tạo bảo đảm một lần cho mọi dịch vụ phía sau.

## 10. Giữ nguồn gốc tin cậy khi đi qua queue và service nội bộ

Ngữ cảnh đã xác minh cần được lưu cùng sự kiện: tài khoản nguồn, môi trường, cấu hình xác minh đã dùng, thời điểm tiếp nhận, dấu vân tay và liên kết dự kiến. Quyền truy cập inbox và đường gửi thông điệp nội bộ phải được bảo vệ.

Không để một client khác gửi trực tiếp thông điệp tự nhận `signatureVerified=true` rồi bỏ qua bước xác minh. Cờ đó chỉ có giá trị trong một luồng có nguồn phát và ranh giới truy cập được bảo vệ.

Worker có thể chạy sau khi cửa sổ timestamp của lần giao đã qua. Nếu lần giao đã được xác minh và lưu an toàn lúc tiếp nhận, không nên coi backlog tự biến chữ ký ban đầu thành thất bại để bỏ mất sự kiện. Cần phân biệt bằng chứng tiếp nhận với chính sách quyền và điều kiện nghiệp vụ hiện hành khi áp dụng.

Việc khóa tài khoản đối tác có thể yêu cầu dừng áp dụng công việc đang chờ, cho phép tiếp tục một số kết quả đã cam kết hoặc chuyển chúng sang đối soát. Chính sách này phải được định nghĩa; không mặc định mọi thông điệp trên queue đều được phép chạy mãi với quyền cũ.

## 11. Bảo vệ chiều gọi ra và phản hồi API

### 11.1. Chỉ gửi một ý định nội bộ đã được chấp nhận

Trước khi gọi tạo chuyến, hệ thống cần xác định fulfillment nào được phép, nội dung và người nhận nào đã chốt, tài khoản đối tác nào được dùng. Không để client tùy chọn một credential có quyền rộng hoặc đổi payload thành một đơn khác sau khi đã duyệt.

Ý định gọi ra nên có định danh bền vững và phiên bản nội dung. Khi cần retry, dùng lại định danh của cùng ý định theo hợp đồng của đối tác; không tạo một lệnh thương mại mới cho mỗi lần thử mạng.

Thông tin gửi ra cần đủ cho mục đích tích hợp và trong phạm vi được phép. Quyền báo trạng thái vận chuyển không mặc nhiên cho đối tác quyền nhận toàn bộ hồ sơ thanh toán hoặc dữ liệu của khách hàng khác.

### 11.2. HTTP thành công không đồng nghĩa nghiệp vụ thành công

Phản hồi cần được kiểm tra cấu trúc, loại kết quả và liên kết với lệnh đã gửi. Một kết quả “đã xếp hàng” không phải “đã tạo xong chuyến”; một phản hồi đã tạo nhãn không chứng minh đã bàn giao hàng.

Đối chiếu những dữ liệu có ý nghĩa theo hợp đồng, như tài khoản, mã tham chiếu do máy chủ cấp, sản phẩm dịch vụ vận chuyển, số lượng và snapshot người nhận. Không lấy body bên ngoài rồi ghi đè toàn bộ entity đơn.

Các giá trị tiền hoặc đơn vị đo phải có quy ước cụ thể. Một giá trị nguyên có thể biểu diễn đơn vị tiền nhỏ nhất, đơn vị tiền chính hoặc một đơn vị khác. Không tự suy ra chỉ từ tên trường `amount`; sai đơn vị có thể làm sai quyết định hạn mức hoặc chi phí dù JSON vẫn hợp lệ.

### 11.3. Timeout tạo ra sự không chắc chắn, không phải quyền tạo lại

Nếu đối tác đã tạo chuyến nhưng phản hồi bị mất, gửi một ý định mới có thể tạo thêm kiện hoặc giữ thêm tài nguyên.

Cần lưu ý định trước khi gọi, giữ trạng thái chưa rõ, tra cứu bằng tham chiếu được chấp nhận hoặc retry với cùng định danh mà bên nhận hỗ trợ. Phải hiểu phạm vi và thời hạn giữ idempotency của đối tác; hết hạn khóa không chứng minh lệnh cũ chưa thực hiện.

Nếu một đối tác không cung cấp khả năng tra cứu hoặc chống trùng đủ mạnh, cần điểm dừng và quy trình đối soát phù hợp. Không thể suy ra bảo đảm một tác dụng duy nhất chỉ từ transaction trong cơ sở dữ liệu của bạn.

Chuyển sang nhà vận chuyển dự phòng khi kết quả bên cũ chưa rõ cũng có thể tạo hai lần giao. Failover cần xử lý khả năng tác dụng đã xảy ra ở bên cũ, không chỉ thay URL rồi gửi lại cùng nội dung.

### 11.4. URL và nội dung tải về cũng đi qua ranh giới

Đối tác có thể trả URL ảnh bằng chứng, nhãn vận chuyển hoặc endpoint tiếp theo. Những URL đó là đầu vào điều khiển kết nối ra ngoài nếu ứng dụng tự tải chúng.

Cần chính sách đích được phép, kiểm tra giao thức, địa chỉ thực khi kết nối và cách xử lý redirect; không để một URL ngoài tùy ý hướng ứng dụng vào mạng nội bộ hoặc dịch vụ metadata. Thông tin xác thực không được tự chuyển tiếp sang một đích khác chỉ vì có redirect.

Giới hạn kích thước, thời gian, số lần chuyển hướng và chi phí giải nén/parse phản hồi, kể cả phản hồi lỗi. Nội dung đã tải cũng cần được xử lý theo mục đích sử dụng; phần mở rộng tên tệp không tự chứng minh loại dữ liệu.

## 12. Hợp đồng tích hợp và vòng đời cấu hình quyền

### 12.1. Hợp đồng cần mô tả ý nghĩa, không chỉ tên trường

Với mỗi luồng, nên thống nhất:

- Danh tính và phạm vi duy nhất của đối tượng, sự kiện, lần giao và ý định gọi ra.
- Những trường nào được xác thực và cơ chế xác minh chính xác.
- Trạng thái nào là tạm thời, cuối cùng hoặc có thể bị điều chỉnh.
- Quy tắc thứ tự, retry, ACK, lỗi và cửa sổ lưu idempotency.
- Đơn vị số lượng, tiền tệ, múi giờ và độ chính xác thời gian.
- Cách phát hiện và phục hồi sự kiện thiếu, đến muộn hoặc chưa có liên kết.
- Quyền thay đổi endpoint, tài khoản, scope, môi trường và phiên bản hợp đồng.

Một ví dụ JSON minh họa happy path chưa phải hợp đồng đủ để xây kiểm soát nghiệp vụ.

### 12.2. Phiên bản mới không được mở rộng quyền ngầm

Một phiên bản mới có thể thêm enum hoặc đổi ý nghĩa trạng thái. Adapter cần biết phiên bản nào được hỗ trợ và xử lý giá trị chưa hiểu theo chính sách, như từ chối hoặc cách ly có kiểm soát.

Không tự ánh xạ một trạng thái lạ thành `DELIVERED` để tránh lỗi. Cũng không tự cho phép trường mới như `refundApproved`, `overridePrice` hoặc `beneficiaryId` ghi vào nghiệp vụ chỉ vì thư viện ánh xạ hỗ trợ thuộc tính đó.

Khi hỗ trợ đồng thời endpoint cũ và mới, việc chống trùng vẫn cần theo danh tính sự kiện/nghiệp vụ ổn định. Thêm phiên bản parser vào khóa theo cách làm mỗi endpoint có lịch sử trống có thể khiến cùng một kết quả được áp dụng hai lần.

### 12.3. Dữ liệu cũ và luật mới cần được phân biệt

Phát lại sự kiện để phục hồi không có nghĩa được tùy ý tính lại mọi quyết định bằng cấu hình hôm nay. Cần biết sự kiện đã được hiểu theo hợp đồng nào và quyết định nội bộ nào đã được commit.

Việc sửa mapping hoặc bật một tài khoản tích hợp mới cần có kiểm soát thay đổi. Người cấu hình endpoint không mặc nhiên được cấp thêm quyền tài chính cho đối tác; quyền kết nối và quyền thay đổi nghiệp vụ là hai phạm vi khác nhau.

### 12.4. Đổi khóa không đổi danh tính nghiệp vụ

Khóa và bí mật cần được bảo vệ, phân tách theo phạm vi cần thiết và không xuất hiện trong log. Trong đợt đổi khóa có kế hoạch, cách chấp nhận chồng lấn phải theo giao thức và thời gian hiệu lực được quản lý.

Nếu khóa đã bị lộ, không tiếp tục chấp nhận nó chỉ để giữ một khoảng chồng lấn thuận tiện. Cần thu hồi, thay thế và điều tra những sự kiện hoặc tác dụng có thể bị ảnh hưởng.

Tách môi trường thử nghiệm và thật ở credential, endpoint, tài khoản, mapping và đường tác dụng. Một sự kiện sandbox không được tạo giao hàng hoặc chi trả thật dù mã đơn ngoài trùng nhau.

Không đặt key ID vào khóa chống trùng theo cách làm thay khóa đồng nghĩa quên sự kiện cũ. Đồng thời, không tin rằng đổi khóa đã tự sửa các bản ghi liên kết hoặc quyết định sai trước đó.

## 13. Tính sẵn sàng và giới hạn ảnh hưởng khi đối tác lỗi

### 13.1. Giới hạn tài nguyên theo luồng và đối tác

Cần giới hạn đầu vào, công việc đồng thời, độ dài hàng đợi và chi phí gọi ra theo phạm vi phù hợp. Một đối tác gửi lặp hợp lệ vẫn có thể làm cạn tài nguyên nếu mỗi lần đều thực hiện truy vấn đắt hoặc tạo công việc mới.

Có thể tách ngân sách cho tiếp nhận webhook, gọi tạo mới và đối soát kết quả. Dành năng lực cho công việc kết thúc giúp hệ thống không kẹt vì toàn bộ tài nguyên bị dùng để tạo thêm ý định.

Retry cần số lần và thời gian hữu hạn, backoff phù hợp và tránh nhiều tầng cùng khuếch đại tải. Không retry tự động lỗi sai quyền, sai hợp đồng hoặc sai nội dung như thể đó chỉ là lỗi mạng.

### 13.2. Suy giảm chức năng vẫn phải giữ điều kiện an toàn

Nếu không xác minh được nguồn hoặc quyền cần thiết, không được bỏ kiểm tra để tăng tỷ lệ thành công. Nếu đối tác không phản hồi, có thể hiển thị trạng thái nội bộ trung thực, hạn chế tạo mới và ưu tiên đối soát.

Một callback chưa xác minh không trở thành hợp lệ chỉ vì hệ thống cần giải phóng hàng chờ. Một phản hồi lỗi cũng không cho phép tự hủy lịch sử đã thực hiện bên ngoài.

### 13.3. Đình chỉ tích hợp cần có kế hoạch xử lý công việc đang chạy

Khi nghi ngờ đối tác hoặc credential bị chiếm:

1. Giới hạn hoặc đình chỉ phạm vi bị ảnh hưởng theo chính sách.
2. Ngừng nhận quyền mới hoặc tác dụng mới không đủ căn cứ.
3. Phân loại công việc chưa gửi, đang gửi và chưa biết kết quả.
4. Giữ bằng chứng và ngữ cảnh để điều tra; không xóa inbox/outbox nhằm làm sạch số liệu.
5. Đối soát với nguồn hoặc quy trình độc lập phù hợp trước khi mở lại.

Đình chỉ một tài khoản không nên vô tình làm mất mọi đường truy vết kết quả đã xảy ra. Tuy nhiên, quyền tra cứu hoặc đối soát trong sự cố cũng cần được kiểm soát, không phải một đường bỏ qua xác thực.

## 14. Bằng chứng, giám sát và đối soát ranh giới

### 14.1. Giữ đủ dữ liệu để giải thích quyết định

Một bản ghi có thể liên kết:

```text
partnerId, integrationAccountId, environment
externalEventId, externalObjectId
receivedAt, reportedOccurredAt
verificationConfigurationReference
contractVersion, semanticFingerprint
bindingId, bindingRevision
tenantId, internalObjectId
inboxId, operationId, correlationId
action, outcome, reasonCode
stateBefore, stateAfter
outboundIntentId và externalEffectReference nếu có
```

Tham chiếu cấu hình xác minh giúp truy vết nhưng không đòi hỏi lưu bí mật, toàn bộ header chữ ký hoặc token. Tránh ghi toàn bộ body nếu chứa địa chỉ, thông tin cá nhân hoặc dữ liệu không cần thiết. Bằng chứng chi tiết cần có quyền truy cập và chính sách lưu giữ phù hợp.

### 14.2. Những mâu thuẫn đáng cảnh báo

- Xác minh nguồn thất bại tăng mạnh hoặc request cố dùng môi trường sai.
- Tài khoản hợp lệ liên tục gửi mã đối tượng không thuộc phạm vi.
- Một event ID có các nội dung có ý nghĩa mâu thuẫn.
- Loại sự kiện hoặc phiên bản hợp đồng chưa được hỗ trợ xuất hiện nhiều.
- Shipment bị hủy nhưng tiếp tục có thông báo giao hoặc đơn bị mở lại ngoài luồng cho phép.
- Một ý định nội bộ có nhiều tác dụng ngoài không phù hợp mô hình.
- Backlog, tuổi công việc chưa rõ hoặc độ trễ đối soát tăng cao.

Không dùng số lần HTTP thành công làm bằng chứng toàn bộ nghiệp vụ đúng. Cần quan sát số thay đổi được chấp nhận, bị từ chối và đang chờ xử lý mâu thuẫn.

### 14.3. Đối soát theo quan hệ hai chiều

Kiểm tra rằng mỗi đối tượng ngoài đã dùng có liên kết nội bộ hợp lệ, mỗi bằng chứng đã áp dụng có nguồn được chấp nhận và mỗi tác dụng ngoài có ý định được phép tương ứng.

Nếu cần khắc phục dữ liệu, giữ lịch sử quyết định và nguyên nhân. Không sửa đơn về trạng thái “đẹp” rồi mất dấu vì sao đã giao, đã hủy hoặc đã phát một tác vụ tài chính.

## 15. Kiểm thử ranh giới bằng các tình huống lạm dụng

| Tình huống | Điều phải được chứng minh |
| --- | --- |
| Request thiếu hoặc sai xác thực | Không ghi bằng chứng nghiệp vụ hoặc tạo tác dụng từ nguồn chưa được chấp nhận |
| Chữ ký hợp lệ nhưng tài khoản không có năng lực gửi loại sự kiện | Bị chặn theo scope, không chỉ dựa vào xác thực nguồn |
| Đối tác A báo mã đối tượng thuộc B | Không tác động được liên kết của B |
| Cùng mã đối tượng ở sandbox và production | Không ánh xạ chéo hoặc phát tác dụng thật từ sự kiện thử nghiệm |
| Payload tự khai tenant hoặc đơn của bên khác | Không ghi đè tenant/đơn suy ra từ liên kết; xử lý mâu thuẫn theo hợp đồng |
| Payload thêm cờ duyệt hoàn, trả tiền hoặc đổi người nhận | Không mở quyền hoặc gán trường hệ thống từ dữ liệu ngoài |
| Body bị biến đổi sau khi ký trong giao thức yêu cầu raw body | Xác minh thất bại; adapter không dùng dữ liệu parse lại để giả lập nội dung đã ký |
| Timestamp mới nhưng không nằm trong phần xác thực | Không coi riêng nó là bằng chứng chống replay |
| Sự kiện cũ được giao lại hợp lệ | Không áp dụng tác dụng hai lần; vẫn đối soát được bằng chứng đến muộn |
| Retry có delivery ID mới nhưng cùng sự kiện logic | Không tạo một công việc nghiệp vụ độc lập cho mỗi lần giao |
| Hai tài khoản có cùng event ID hợp lệ | Không làm mất sự kiện của một bên do khóa dedup quá rộng |
| Đổi khóa rồi phát lại sự kiện đã xử lý | Không mở lại lịch sử chống trùng theo key ID mới |
| Cùng event ID nhưng nội dung trọng yếu khác | Không ghi đè im lặng; có dấu vết mâu thuẫn |
| Sự kiện sai thứ tự hoặc có điều chỉnh | Không lùi trạng thái sai hoặc bỏ qua điều chỉnh hợp lệ theo mô hình |
| Link bị đổi sau khi adapter đã đọc | Bước áp dụng phát hiện xung đột hoặc dùng cơ chế đồng bộ đúng |
| Tiến trình dừng trước/sau commit inbox | Không ACK giả hoặc làm mất công việc đã báo nhận |
| Tiến trình dừng khi áp dụng thay đổi | Bản ghi xử lý và thay đổi nghiệp vụ nhất quán, không lặp hiệu ứng |
| Đối tác thực hiện lệnh nhưng phản hồi bị mất | Tra cứu/retry cùng ý định theo hợp đồng; không tùy tiện tạo tác dụng mới |
| URL bằng chứng chuyển hướng tới đích không được phép | Không bị dùng làm đường truy cập mạng ngoài chính sách hoặc làm lộ credential |
| Payload, phản hồi hoặc backlog vượt giới hạn | Tài nguyên được chặn ở ngưỡng và không báo xử lý nghiệp vụ giả |
| Quyền tích hợp bị thu hồi khi công việc còn trên queue | Xử lý theo chính sách hiệu lực đã định nghĩa, không mặc định quyền cũ tồn tại mãi |

### 15.1. Chọn tầng kiểm thử theo điều cần chứng minh

**Kiểm thử đơn vị** phù hợp cho mapping nguồn, phạm vi tài khoản/môi trường, phiên bản hợp đồng, bảng trạng thái và chuyển từ dữ liệu ngoài sang lệnh nội bộ có giới hạn.

**Kiểm thử giao thức** dùng dữ liệu và công cụ phù hợp của nhà cung cấp để kiểm tra chữ ký, raw body, định danh, thời gian giao và đổi khóa. Một mock luôn trả `verified = true` không chứng minh khả năng xác minh thật.

**Kiểm thử tích hợp cơ sở dữ liệu/queue** kiểm tra khóa duy nhất, transaction inbox, trạng thái xử lý, rollback và lịch chạy cạnh tranh. Cần các giao dịch độc lập để kiểm tra cùng sự kiện được xử lý đồng thời.

**Kiểm thử lỗi và phục hồi** mô phỏng timeout, mất phản hồi, restart, sự kiện thiếu, sai thứ tự và tích hợp bị đình chỉ. Sau phục hồi, đối chiếu cả kết quả nội bộ lẫn số tác dụng ngoài.

Các tình huống trên là đặc tả kiểm thử cho bài học, không phải báo cáo một triển khai cụ thể đã chạy và đạt. Điều kiện mong đợi phải dựa trên hợp đồng của đối tác đang dùng.

## 16. Mẫu đặc tả một ranh giới tích hợp

```text
Luồng và tài sản:
  Đối tác gửi/nhận gì và thay đổi nào có giá trị có thể xảy ra?

Danh tính:
  Đối tác, tài khoản, môi trường và credential nào?
  Dữ liệu được xác thực bằng giao thức nào, bao gồm những phần gì?

Thẩm quyền:
  Được báo sự kiện hoặc ra lệnh nào, cho tenant và đối tượng nào?
  Trường nào có thể là nguồn sự thật, trường nào chỉ là đề nghị/bằng chứng?

Liên kết:
  Khóa đối tượng ngoài có phạm vi duy nhất nào?
  Liên kết được tạo, đổi, thu hồi và đối soát bằng quyền nào?

Hợp đồng ngữ nghĩa:
  Phiên bản, đơn vị, trạng thái, thứ tự và điều chỉnh được hiểu ra sao?

Áp dụng nội bộ:
  Quy tắc, máy trạng thái và điểm thực thi nào quyết định thay đổi?
  Transaction bảo vệ những dữ liệu nào?

Gửi lại và tác dụng:
  Định danh delivery, sự kiện, ý định và tác dụng khác nhau thế nào?
  Lưu bền vững, ACK, retry và xử lý kết quả chưa rõ ra sao?

Giới hạn và vòng đời:
  Payload, timeout, concurrency, queue và chi phí có giới hạn nào?
  Đổi khóa, đổi hợp đồng, đình chỉ và chấm dứt tích hợp được xử lý thế nào?

Bằng chứng và kiểm thử:
  Làm sao chứng minh đúng nguồn, đúng phạm vi và không lặp hiệu ứng?
  Những trường hợp đối tác được xác thực nhưng không được phép là gì?
```

Ranh giới tích hợp được bảo vệ khi **danh tính nguồn, phạm vi thẩm quyền, ý nghĩa dữ liệu và điều kiện thay đổi nghiệp vụ** được kiểm tra riêng rồi nối lại bằng bằng chứng rõ ràng. Một phản hồi hoặc webhook hợp lệ chỉ nên tạo ra đúng thay đổi mà đối tác được phép góp phần quyết định, trong trạng thái và phạm vi mà hệ thống của bạn đã chấp nhận.
