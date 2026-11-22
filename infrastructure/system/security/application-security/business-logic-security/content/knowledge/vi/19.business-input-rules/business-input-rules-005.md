# Conditional field rules: quy tắc trường dữ liệu theo điều kiện nghiệp vụ

## 1. Mục tiêu bài học

Trong chương **Business Input Rules** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **conditional field rules** là các quy tắc quyết định một trường phải có, được có hay không được có tùy theo dữ liệu và ngữ cảnh nghiệp vụ.

Ví dụ, hoàn tiền qua chuyển khoản có thể yêu cầu một đích nhận tiền đã được xác minh, còn hoàn về giao dịch gốc lại không được phép kèm một đích nhận khác. Nếu chỉ kiểm tra “field này không rỗng khi phương thức là chuyển khoản”, hệ thống vẫn có thể xử lý sai các tổ hợp còn lại.

Lỗi điều kiện trường có thể dẫn đến sửa giá, đổi người nhận, bỏ qua phê duyệt, giữ dữ liệu cũ không còn hợp lệ hoặc gửi cùng một ý định qua các nhánh có mức kiểm soát khác nhau.

Sau bài học, bạn có thể:

- Định nghĩa trường bắt buộc, tùy chọn, bị cấm và do server xác lập.
- Phân biệt thiếu trường, null, rỗng, 0 và false theo hợp đồng.
- Xây dựng ma trận điều kiện có cả nhánh đúng lẫn nhánh sai.
- Kiểm tra trạng thái cuối sau PATCH thay vì chỉ kiểm tra các field được gửi.
- Dùng dữ liệu có thẩm quyền để chọn nhánh và giữ quy tắc đúng khi xử lý đồng thời.
- Kiểm thử các cách bỏ trường, thêm trường, đổi discriminator và giữ dữ liệu cũ để vượt quy tắc.

## 2. Quy tắc theo điều kiện bảo vệ điều gì?

Một form có thể hiển thị bankDestinationId chỉ khi người dùng chọn BANK_TRANSFER. Nhưng client có thể gửi trực tiếp:

~~~json
{
  "refundMethod": "ORIGINAL_PAYMENT",
  "bankDestinationId": "destination-selected-by-client"
}
~~~

Nếu backend không quy định tổ hợp này bị cấm, các tầng có thể hiểu khác nhau:

~~~text
Validator thấy ORIGINAL_PAYMENT nên không bắt buộc bankDestinationId.
Mapper vẫn lưu bankDestinationId vì payload có trường đó.
Worker thấy có bankDestinationId nên chuyển tiền theo đích này.
~~~

Các lớp đã chọn nhánh khác nhau. Request hợp lệ về kiểu JSON nhưng không hợp lệ về ý nghĩa nghiệp vụ.

Các lỗi tương tự:

| Quy tắc thiếu | Hậu quả có thể xảy ra |
|---|---|
| Chỉ có if, không có else cho trường không được phép | Dữ liệu của nhánh khác vẫn tác động tới xử lý |
| Xem null giống thiếu field trong mọi thao tác | Không phân biệt giữ nguyên và xóa khi PATCH |
| Kiểm tra điều kiện trên payload thay vì trạng thái cuối | Dữ liệu cũ không hợp lệ vẫn còn |
| Tin requiresApproval do client gửi | Chọn nhánh không cần phê duyệt trái chính sách |
| Cho phép discriminator không nhận diện được rồi dùng mặc định | Né các yêu cầu của một nhánh nhạy cảm |
| Chỉ kiểm tra ID có tồn tại | Liên kết đích nhận hoặc chứng từ sai tenant/người hưởng lợi |
| Mỗi tầng có một bộ điều kiện riêng | Validator, lưu trữ và worker thực thi theo các nghĩa khác nhau |

## 3. Bốn loại quy tắc trường

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Required | Phải có giá trị hợp lệ khi điều kiện áp dụng | BANK_TRANSFER cần bankDestinationId |
| Optional | Có thể bỏ; nếu có vẫn phải hợp lệ | Ghi chú bổ sung nếu chính sách cho phép |
| Forbidden | Không được gửi/gắn giá trị trong ngữ cảnh được quy định | ORIGINAL_PAYMENT không có đích chuyển khoản thay thế |
| Server-controlled | Giá trị do server xác lập, client không được quyết định | approvedBy, tenantId có thẩm quyền, requiresApproval |

Required không chỉ có nghĩa field xuất hiện. Một chuỗi toàn khoảng trắng, một ID không được phép hoặc số tiền không hợp lệ vẫn không đáp ứng yêu cầu.

Optional cũng không có nghĩa có thể gửi bất kỳ giá trị nào. Nếu nhận một ID tùy chọn, server vẫn phải kiểm tra quyền và quan hệ của ID đó khi nó xuất hiện.

### 3.1. Viết đủ hai nhánh khi nghiệp vụ cần

Mô tả chưa đủ:

~~~text
Nếu refundMethod = BANK_TRANSFER thì yêu cầu bankDestinationId.
~~~

Mô tả đầy đủ hơn cho ví dụ:

~~~text
Nếu refundMethod = BANK_TRANSFER:
    bankDestinationId phải có và đủ điều kiện.

Nếu refundMethod = ORIGINAL_PAYMENT:
    không được chọn bankDestinationId;
    đích hoàn lấy từ giao dịch gốc đã được server xác minh.
~~~

Không phải mọi else đều phải Forbidden. Có trường thật sự Optional ở nhánh còn lại; cần chọn theo ngữ nghĩa, không theo tiện lợi của DTO.

### 3.2. Điều kiện có thể đến từ nhiều nguồn

Một trường có thể phụ thuộc:

- Discriminator do client được phép chọn, như loại phương thức.
- Loại đối tượng được đọc từ server.
- Trạng thái hoặc revision hiện tại.
- Quyền actor trong đúng tenant và object scope.
- Chính sách rủi ro/hạn mức áp dụng.
- Giá trị của các trường khác.
- Hành động đang thực hiện: tạo, sửa bản nháp hay xác nhận.

Điều kiện do client đề xuất phải được kiểm tra. Điều kiện có thẩm quyền từ server không được bị thay bằng một flag do client tự khai.

### 3.3. Nhiều quy tắc không được triệt tiêu nhau ngầm

Ví dụ một rule yêu cầu explanation, rule khác lại cấm explanation trong cùng ngữ cảnh. Đây là xung đột cần giải quyết trong chính sách hoặc dữ liệu điều kiện.

Không chọn rule cuối trong danh sách để ghi đè tùy ý. Các ràng buộc cùng áp dụng phải được thỏa đồng thời, hoặc có thứ tự ưu tiên được đặc tả rõ.

Thiếu facts để xác định nhánh không đồng nghĩa chọn nhánh ít kiểm soát hơn.

## 4. Phân biệt trạng thái có mặt của dữ liệu

| Input | Ý nghĩa cần đặc tả |
|---|---|
| Không có key | Caller không cung cấp field; trong PATCH có thể là giữ nguyên |
| key có giá trị null | Caller gửi null; có thể là lệnh xóa nếu hợp đồng cho phép |
| Chuỗi rỗng | Có giá trị chuỗi nhưng không có nội dung |
| Chuỗi chỉ khoảng trắng | Cần chuẩn hóa/kiểm tra nội dung theo hợp đồng |
| Số 0 | Một giá trị số; hợp lệ hay không tùy field |
| Boolean false | Một giá trị boolean có thể hoàn toàn hợp lệ |
| Danh sách rỗng | Có tập rỗng; khác với chưa gửi danh sách |

Không dùng một kiểm tra “falsy” chung để suy ra field bị thiếu. False có thể là câu trả lời hợp lệ, trong khi amount=0 có thể bị cấm bởi quy tắc số tiền dương.

### 4.1. DTO nullable có thể làm mất thông tin

Nếu binder ánh xạ cả không có key và key=null thành cùng một giá trị null, tầng PATCH không còn biết caller muốn giữ nguyên hay xóa.

Có thể dùng kiểu biểu diễn presence rõ ràng, chẳng hạn:

~~~text
FieldUpdate<T> =
    Unspecified
    Clear
    Set(value)
~~~

Tên kiểu tùy dự án. Điều quan trọng là không đánh mất ý định trước khi áp dụng quy tắc.

### 4.2. Chuẩn hóa phải có hợp đồng

Có thể chuẩn hóa khoảng trắng của explanation trước khi kiểm tra độ dài/nội dung. Với discriminator, ID và mã nghiệp vụ, cần quy định rõ có cho phép chuẩn hóa hay phải khớp chính xác.

Không tự sửa một giá trị lạ thành phương thức mặc định. Không loại bỏ field bị cấm trước khi validator kịp phát hiện rồi để một tầng khác vẫn dùng giá trị thô.

Các tầng phải xử lý cùng một biểu diễn đã được chấp nhận.

### 4.3. Đầu vào mơ hồ cần được xử lý sớm

Nếu payload có key trùng nhau hoặc biểu diễn không được hợp đồng hỗ trợ, các parser có thể không thống nhất giá trị hiệu lực.

Với các field quyết định nhánh nhạy cảm, nên dùng chính sách decode rõ ràng và nhất quán, chẳng hạn từ chối key trùng trước khi xử lý nghiệp vụ. Không để gateway kiểm tra một refundMethod còn handler sử dụng refundMethod khác từ cùng payload.

## 5. Ma trận quy tắc cho yêu cầu hoàn tiền

Chính sách dưới đây là ví dụ phục vụ học tập:

- Request được tạo trong tenant đã kiểm chứng và gắn với một payment hợp lệ.
- Có hai phương thức: ORIGINAL_PAYMENT và BANK_TRANSFER.
- Không phải actor/payment nào cũng được dùng BANK_TRANSFER; server xác định tập phương thức được phép.
- Số tiền là số nguyên theo đơn vị nhỏ nhất mà hệ thống quy định cho currency của payment.
- Lý do gồm ORDER_CANCELLED và OTHER.
- ORDER_CANCELLED chỉ được chấp nhận khi facts phía server xác nhận điều kiện hủy đơn phù hợp.
- Cách xác định cần phê duyệt do server thực hiện, không nhận một flag tắt phê duyệt.

### 5.1. Quy tắc khi tạo mới

| Field | ORIGINAL_PAYMENT | BANK_TRANSFER |
|---|---|---|
| paymentId | Bắt buộc; đúng tenant và scope | Bắt buộc; đúng tenant và scope |
| refundMethod | Bắt buộc; đúng enum và được policy cho phép | Bắt buộc; đúng enum và được policy cho phép |
| amountMinor | Bắt buộc; số dương, hợp lệ theo payment | Bắt buộc; số dương, hợp lệ theo payment |
| bankDestinationId | Bị cấm | Bắt buộc; đích nhận đủ điều kiện |
| reasonCode | Bắt buộc, thuộc tập hỗ trợ | Bắt buộc, thuộc tập hỗ trợ |
| explanation | Theo rule reasonCode bên dưới | Theo rule reasonCode bên dưới |
| requiresApproval, approvedBy, status | Client không được quyết định | Client không được quyết định |
| tenantId có thẩm quyền, currency | Server xác lập theo context/payment | Server xác lập theo context/payment |

Trong hợp đồng CREATE minh họa, một field bị cấm không được gửi kể cả với null. Chọn chính sách từ chối rõ ràng để caller sửa request và không để dữ liệu của nhánh khác tồn tại trong pipeline.

### 5.2. Quy tắc theo reasonCode

| reasonCode | explanation | Facts bổ sung |
|---|---|---|
| OTHER | Bắt buộc có nội dung sau chuẩn hóa, trong giới hạn độ dài | Các điều kiện hoàn tiền chung vẫn áp dụng |
| ORDER_CANCELLED | Bị cấm trong hợp đồng minh họa | Server xác nhận trạng thái/quan hệ đơn hàng phù hợp |

Ví dụ chọn giới hạn explanation tối đa 1.000 ký tự theo quy ước đếm của ứng dụng. Con số và cách đếm phải được thống nhất giữa API, lưu trữ và UI; không có một giới hạn đúng cho mọi sản phẩm.

Nếu một reason code làm giảm yêu cầu bằng chứng hoặc thay đổi quy trình phê duyệt, server phải có căn cứ cho việc áp dụng nhánh đó. Không coi lời khai reasonCode là bằng chứng sự kiện đã xảy ra.

### 5.3. Bốn tổ hợp cần được hiểu đầy đủ

~~~text
ORIGINAL_PAYMENT + OTHER:
  không có bankDestinationId
  có explanation hợp lệ

ORIGINAL_PAYMENT + ORDER_CANCELLED:
  không có bankDestinationId
  không có explanation
  facts hủy đơn hợp lệ

BANK_TRANSFER + OTHER:
  có bankDestinationId đủ điều kiện
  có explanation hợp lệ

BANK_TRANSFER + ORDER_CANCELLED:
  có bankDestinationId đủ điều kiện
  không có explanation
  facts hủy đơn hợp lệ
~~~

Mỗi tổ hợp vẫn phải đáp ứng quyền actor, trạng thái, số tiền và chính sách phương thức.

Không thể chỉ kiểm thử mỗi BANK_TRANSFER cần destination rồi kết luận toàn bộ ma trận đã an toàn.

## 6. Ví dụ request và cách diễn giải

### 6.1. Hoàn về giao dịch gốc với lý do khác

~~~json
{
  "paymentId": "payment-31",
  "refundMethod": "ORIGINAL_PAYMENT",
  "amountMinor": 150000,
  "reasonCode": "OTHER",
  "explanation": "Điều chỉnh theo kết quả xử lý yêu cầu hỗ trợ."
}
~~~

Request có cấu trúc phù hợp. Server vẫn phải xác minh payment, scope, trạng thái và điều kiện số tiền. Không nhận một tài khoản thay thế từ body để ghi đè đích hoàn của giao dịch gốc.

### 6.2. Chuyển khoản sau khi đơn được hủy

~~~json
{
  "paymentId": "payment-31",
  "refundMethod": "BANK_TRANSFER",
  "amountMinor": 150000,
  "reasonCode": "ORDER_CANCELLED",
  "bankDestinationId": "destination-12"
}
~~~

Ngoài cấu trúc, server cần xác nhận:

- Actor được dùng nhánh BANK_TRANSFER trên payment này.
- Đích destination-12 thuộc đúng quan hệ tenant/người nhận được chính sách cho phép.
- Đích còn active, đã được xác minh và được dùng cho hành động này.
- Facts liên quan đơn hàng đáp ứng reasonCode.
- Số tiền và currency lấy/đối chiếu theo nguồn có thẩm quyền.

Một ID có tồn tại chưa đủ. Cũng không chấp nhận isVerified=true do client gửi để thay cho trạng thái xác minh của đích nhận.

### 6.3. Tổ hợp cần bị chặn

~~~json
{
  "paymentId": "payment-31",
  "refundMethod": "ORIGINAL_PAYMENT",
  "amountMinor": 150000,
  "reasonCode": "OTHER",
  "explanation": "   ",
  "bankDestinationId": "destination-12",
  "requiresApproval": false
}
~~~

Có ít nhất ba vấn đề độc lập:

- explanation không có nội dung hợp lệ.
- bankDestinationId không được phép trong nhánh ORIGINAL_PAYMENT.
- requiresApproval là dữ liệu server kiểm soát.

Không “sửa” request bằng cách đổi phương thức sang BANK_TRANSFER chỉ vì thấy destination. Cũng không bỏ mọi field khó xử rồi thực thi theo cách caller chưa được kiểm chứng.

Có thể trả nhiều lỗi field an toàn trong một response, nhưng không tiết lộ dữ liệu hoặc policy ngoài quyền của actor.

## 7. Kiểm tra trên candidate và facts đã chuẩn hóa

### 7.1. Tách ba loại trách nhiệm

~~~text
Decode/API contract:
  field nào được nhận, kiểu dữ liệu, presence, enum, giới hạn cơ bản.

Conditional domain validation:
  tổ hợp field trong trạng thái cuối có phù hợp không.

Authorization và facts validation:
  actor được chọn nhánh không; đối tượng liên quan có đủ điều kiện không.
~~~

Có thể tổ chức các lớp theo cách khác, nhưng không được bỏ phần nào.

Chỉ dùng annotation “not blank” trên một field không diễn tả được đầy đủ quan hệ giữa method, reason, trạng thái và đối tượng liên quan.

### 7.2. Java minh họa kiểm tra trạng thái ứng viên

Mã sau là phác thảo, không phải chương trình độc lập. Candidate đã được chuẩn hóa và giữ đúng ý nghĩa của các thao tác cập nhật. Enum đã được decode nghiêm ngặt; facts đến từ server.

~~~java
void validateCandidate(
        RefundCandidate candidate,
        TrustedRefundFacts facts) {

    var errors = new FieldErrors();

    errors.require(
            facts.allowedMethodsForActor()
                    .contains(candidate.refundMethod()),
            "refundMethod", "METHOD_NOT_ALLOWED");

    errors.require(
            candidate.amountMinor() > 0,
            "amountMinor", "AMOUNT_MUST_BE_POSITIVE");

    errors.require(
            candidate.amountMinor() <= facts.refundableAtSnapshot(),
            "amountMinor", "AMOUNT_EXCEEDS_AVAILABLE");

    switch (candidate.refundMethod()) {
        case ORIGINAL_PAYMENT -> errors.requireAbsent(
                "bankDestinationId",
                candidate.bankDestinationId());

        case BANK_TRANSFER -> {
            errors.requirePresent(
                    "bankDestinationId",
                    candidate.bankDestinationId());
            if (candidate.bankDestinationId() != null) {
                errors.require(
                        facts.destinationEligibleFor(
                                candidate.bankDestinationId()),
                        "bankDestinationId",
                        "DESTINATION_NOT_ELIGIBLE");
            }
        }
    }

    switch (candidate.reasonCode()) {
        case OTHER -> errors.requireMeaningfulText(
                "explanation", candidate.explanation(), 1000);

        case ORDER_CANCELLED -> {
            errors.requireAbsent(
                    "explanation", candidate.explanation());
            errors.require(
                    facts.orderCancellationEligible(),
                    "reasonCode", "REASON_NOT_SUPPORTED_BY_FACTS");
        }
    }

    errors.throwIfAny();
}
~~~

requireAbsent trong ví dụ kiểm tra candidate không còn giá trị miền của field. Việc CREATE cấm cả key=null cần được kiểm tra ở lớp presence trước khi mapper làm mất sự khác biệt đó.

Các helper không dùng Java assert cho kiểm soát bắt buộc. Nguồn facts không truy cập được phải dẫn tới lỗi/chờ phù hợp, không trả true hoặc dùng một hạn mức mặc định rộng hơn.

### 7.3. Validator không thay thế kiểm tra tại thời điểm quyết định

refundableAtSnapshot là số tiền còn lại ở snapshot đang dùng. Lưu một bản nháp không nhất thiết đã giữ chỗ hạn mức.

Khi approve hoặc chi trả, phải kiểm tra lại theo transaction và trạng thái liên quan. Không coi một lần validate lúc tạo draft là quyền tiêu thụ hạn mức vĩnh viễn.

Tương tự, nếu destination có thể đổi thông tin nhận tiền, cần ràng buộc việc duyệt/thực thi với đúng version/snapshot hoặc kiểm chứng lại theo chính sách. Một destinationId hợp lệ hôm qua không tự chứng minh mọi nội dung hiện tại của nó đã được duyệt.

## 8. PATCH phải được kiểm tra trên trạng thái cuối

### 8.1. Hợp đồng PATCH trong ví dụ

Bài học chọn quy ước rõ ràng cho endpoint sửa bản nháp:

~~~text
Không gửi field:
    giữ nguyên giá trị hiện tại.

Gửi field = null:
    yêu cầu xóa, chỉ hợp lệ với field được phép clear.

Gửi field = value:
    đặt giá trị mới sau decode/chuẩn hóa/kiểm tra quyền.
~~~

Đây là hợp đồng minh họa của API, không phải giả định rằng mọi endpoint dùng PATCH đều có cùng ngữ nghĩa.

Trong ví dụ:

- bankDestinationId và explanation có thể nhận lệnh Clear.
- refundMethod, reasonCode và amountMinor không được clear.
- paymentId đã gắn với bản nháp không được đổi bằng PATCH này.
- Trường server-controlled không được cập nhật.
- Chỉ bản nháp ở trạng thái DRAFT được sửa qua endpoint này.

CREATE và PATCH có thể có hợp đồng presence khác nhau. Null của PATCH là một lệnh clear hợp lệ trong một số trường hợp; không có nghĩa CREATE cũng được gửi một field bị cấm với null.

### 8.2. Ghép patch vào bản hiện tại trước khi validate

Giả sử bản nháp hiện có:

~~~json
{
  "refundMethod": "BANK_TRANSFER",
  "bankDestinationId": "destination-12",
  "reasonCode": "OTHER",
  "explanation": "Điều chỉnh theo kết quả hỗ trợ.",
  "amountMinor": 150000
}
~~~

Caller gửi:

~~~json
{
  "refundMethod": "ORIGINAL_PAYMENT"
}
~~~

Nếu chỉ kiểm tra payload, không thấy bankDestinationId và có thể cho qua. Nhưng theo hợp đồng giữ nguyên field không gửi, candidate vẫn có destination-12.

Candidate đó vi phạm quy tắc ORIGINAL_PAYMENT không có đích chuyển khoản thay thế. Request cần bị từ chối hoặc đi qua một command chuyển phương thức có ngữ nghĩa xóa được công bố rõ.

Trong endpoint PATCH minh họa, request phù hợp là:

~~~json
{
  "refundMethod": "ORIGINAL_PAYMENT",
  "bankDestinationId": null
}
~~~

Lệnh Clear làm candidate không còn đích nhận thay thế, sau đó validator kiểm tra toàn bộ tổ hợp.

Không tự động giữ destination để dùng như fallback nếu hoàn về giao dịch gốc thất bại. Nếu sản phẩm cần fallback thanh toán, nó phải có chính sách, quyền và quy trình riêng.

### 8.3. Đổi reason cũng có vấn đề tương tự

Đang OTHER với explanation có nội dung, caller chỉ gửi:

~~~json
{
  "reasonCode": "ORDER_CANCELLED"
}
~~~

Candidate vẫn còn explanation, nên không hợp lệ theo ma trận ví dụ.

Caller phải gửi lệnh clear phù hợp; server còn phải xác minh facts hủy đơn. Ngược lại, đổi từ ORDER_CANCELLED sang OTHER phải cung cấp explanation nếu candidate chưa có nội dung hợp lệ.

Clear explanation trong khi vẫn OTHER cũng phải bị chặn. Cho phép field nhận lệnh Clear không có nghĩa trạng thái cuối sau Clear luôn hợp lệ.

### 8.4. Không áp dụng default của CREATE cho PATCH

Nếu không có refundMethod trong PATCH, không được tự đặt ORIGINAL_PAYMENT như thể đang tạo request mới.

Một default không đúng ngữ cảnh có thể đổi phương thức, làm mất dữ liệu hoặc tránh điều kiện của nhánh đang lưu mà caller không chủ động yêu cầu.

Tách “không thay đổi” khỏi “đặt về giá trị mặc định”. Nếu cần reset, dùng một thao tác được đặc tả rõ.

### 8.5. Chỉ lưu candidate đã được chấp nhận

Quy trình phù hợp:

~~~text
Đọc bản hiện tại có bảo vệ.
Áp dụng các thao tác Unspecified/Clear/Set vào bản sao ứng viên.
Chuẩn hóa theo hợp đồng.
Kiểm tra quyền đối với các thay đổi thực tế.
Đánh giá toàn bộ conditional rules trên candidate.
Tính giá trị do server quản lý.
Lưu candidate hợp lệ một cách nguyên tử.
~~~

Không lần lượt save method, clear destination rồi mới validate. Một bước thất bại có thể để lại bản ghi nửa chuyển đổi.

Nếu endpoint chuyên biệt tự xóa các field không còn áp dụng, phải công bố rõ hành vi, thực hiện trong cùng transaction và vẫn kiểm tra đầu vào/quyền. Không để mapper hoặc worker tự quyết định việc xóa ở một thời điểm khác.

## 9. Bảo vệ discriminator và dữ liệu có thẩm quyền

### 9.1. Người gọi được chọn nhánh không có nghĩa được chọn mọi nhánh

Một enum decode được chỉ chứng minh giá trị thuộc tập tên được hỗ trợ. Actor vẫn có thể không được dùng BANK_TRANSFER cho payment này.

Tập allowedMethods phải đến từ policy và facts phía server. Ví dụ khả năng hoàn về giao dịch gốc, loại payment hoặc quyền actor có thể ảnh hưởng.

Không nhận một flag như allowBankTransfer, isVerified hoặc requiresApproval để thay các quyết định đó.

### 9.2. Điều kiện dựa trên rủi ro phải được tính từ dữ liệu thực

Mẫu nguy hiểm:

~~~text
Nếu request.requiresApproval = false:
    không bắt buộc approvalReference.
~~~

Client đang tự quyết định có cần kiểm soát hay không.

Thay vào đó:

~~~text
Server tính yêu cầu phê duyệt từ:
  candidate đã hợp lệ
  + payment và trạng thái thực tế
  + policy/hạn mức có thẩm quyền
  + các facts rủi ro cần thiết.
~~~

Nếu phê duyệt là bước riêng, hệ thống tạo trạng thái chờ phê duyệt và chỉ cho bước thực thi đi tiếp sau bằng chứng hợp lệ.

Không chỉ yêu cầu một chuỗi approvalReference có giá trị rồi coi như đã được duyệt. Phải đối chiếu đúng đối tượng, revision, người duyệt, trạng thái và thẩm quyền.

### 9.3. Trường tham chiếu cần kiểm tra quan hệ

Với bankDestinationId hoặc evidenceDocumentId trong một nghiệp vụ khác, cần xác minh nhiều hơn “không null”:

- Đối tượng tham chiếu tồn tại trong biên truy cập phù hợp.
- Quan hệ với tenant, khách hàng hoặc hồ sơ là hợp lệ.
- Actor được sử dụng đối tượng đó cho hành động đang xét.
- Trạng thái và phiên bản phù hợp.
- Nội dung được duyệt/thực hiện không bị đổi nghĩa sau đó.

Không trả lỗi chi tiết tiết lộ một destination ở tenant khác có tồn tại. Có thể dùng mã lỗi an toàn cho caller và lưu lý do đầy đủ hơn trong log được bảo vệ.

### 9.4. Các lớp không được chọn nhánh theo các tín hiệu khác nhau

Validator, domain và worker nên dùng cùng discriminator và snapshot được chấp nhận.

Không để:

~~~text
Validator chọn nhánh từ refundMethod.
Repository suy ra nhánh từ bankDestinationId có null hay không.
Worker chọn nhánh từ một giá trị mặc định riêng.
~~~

Nếu cần chuyển đổi giữa các biểu diễn, phải có ánh xạ rõ ràng và bất biến kiểm tra được.

Các kiểu command theo nhánh có thể giúp giảm trạng thái vô nghĩa, ví dụ một command hoàn về giao dịch gốc không mang field destination thay thế. Dù vậy, quyền, tenant và facts động vẫn cần kiểm tra tại runtime.

## 10. Transaction, trạng thái và xử lý đồng thời

### 10.1. Hai lớp kiểm tra tại hai thời điểm

Có thể decode và kiểm tra cú pháp/presence cơ bản trước transaction. Những quy tắc dựa trên dữ liệu hiện tại cần được đánh giá với cơ chế nhất quán phù hợp.

Một luồng sửa bản nháp:

~~~text
Xác thực actor và tenant.
Decode nghiêm ngặt, giữ presence.
Bắt đầu transaction.
  Nạp/khóa refund đúng tenant.
  Kiểm tra quyền EDIT_DRAFT và expected version.
  Kiểm tra trạng thái DRAFT.
  Dựng candidate từ dữ liệu hiện tại và patch.
  Lấy policy/facts có thẩm quyền.
  Validate field rules, quan hệ và tham số.
  Tính các giá trị do server xác lập.
  Tăng revision/version phù hợp.
  Lưu, audit và outbox bắt buộc.
Commit.
~~~

Nếu một bước bắt buộc lỗi, không được để lại method mới với destination cũ hoặc explanation đã xóa trong khi reason vẫn yêu cầu.

Transaction cục bộ không tự khóa được dữ liệu ở dịch vụ ngoài. Nếu facts từ ngoài ảnh hưởng quyết định, cần quy định độ mới, kiểm chứng phiên bản hoặc xử lý khi chưa xác định được.

### 10.2. Cuộc đua sửa và submit

Giả sử một request sửa bản nháp còn request khác submit:

~~~text
Nếu sửa thắng:
    submit phải xem revision mới hoặc bị chặn vì version cũ.

Nếu submit thắng:
    đường sửa DRAFT không được thay nội dung đã submit.
~~~

Khóa/version và kiểm tra trạng thái phải phối hợp trên cùng dữ liệu. Validate một bản detached rồi ghi đè sau đó mà không có điều kiện bảo vệ là chưa đủ.

### 10.3. Điều kiện ở draft chưa thay thế điều kiện trước hiệu ứng

Số tiền còn có thể hoàn thay đổi khi các yêu cầu khác được duyệt. Destination hoặc policy cũng có thể đổi trước lúc chi trả.

Khi phát sinh hiệu ứng, kiểm tra lại các điều kiện cần thiết và ràng buộc với nội dung đã được phê duyệt. Nếu có reservation, việc giữ/giải phóng phải dùng transaction và bất biến tương ứng.

Một request đúng field không tự tạo quyền approve, quyền chi trả hay bảo đảm không bị thực hiện trùng.

## 11. Idempotency không được làm mất nghĩa presence

Fingerprint cần dựa trên biểu diễn command chuẩn theo hợp đồng, không chỉ trên JSON thô hoặc một DTO đã mất thông tin.

Với PATCH:

~~~text
Không gửi bankDestinationId:
    giữ nguyên.

Gửi bankDestinationId = null:
    clear.
~~~

Hai lệnh có ý nghĩa khác nhau không được gộp chỉ vì binder biến cả hai thành null.

Có thể chuẩn hóa thứ tự key hoặc giá trị theo quy tắc đã công bố, nhưng phải giữ các khác biệt có ý nghĩa nghiệp vụ.

Retry cùng key và cùng nội dung đã hoàn tất trả kết quả đã lưu theo quyền truy cập hiện tại, không áp dụng patch lần nữa trên một bản ghi có thể đã đổi. Cùng key nhưng khác command phải được phát hiện.

Scope receipt cần ràng buộc tenant, actor/phạm vi và action phù hợp. Biết key không thay thế kiểm tra quyền xem kết quả.

## 12. Những mẫu phụ thuộc thường cần mô tả rõ

### 12.1. Điều kiện một chiều không tự thành hai chiều

Quy tắc “nếu A có thì B phải có” không nói rằng B chỉ được có khi A có.

Nếu nghiệp vụ muốn cả hai chiều, cần viết rõ hoặc dùng một mô hình thể hiện đúng quan hệ.

| Mẫu | Cách kiểm tra ý nghĩa |
|---|---|
| A kéo theo B | Có A thì phải có B |
| Cùng có hoặc cùng không | Presence của A và B phải bằng nhau |
| Ít nhất một | Số trường có giá trị hợp lệ lớn hơn hoặc bằng 1 |
| Chính xác một | Số trường có giá trị hợp lệ bằng 1 |
| Có A thì cấm B | Không chấp nhận tổ hợp A và B cùng có |
| Theo discriminator | Mỗi nhánh có tập required/optional/forbidden riêng |

Ví dụ startDate và endDate cùng có chưa đủ; nếu có còn cần startDate trước endDate theo chính sách.

Hai field đều được ghi Optional cũng không tự tạo quy tắc “phải chọn ít nhất một”.

### 12.2. Trường lồng nhau và danh sách

Nếu mỗi evidence có type=TEXT hoặc type=FILE:

~~~text
TEXT:
  yêu cầu text có nội dung
  cấm fileId

FILE:
  yêu cầu fileId đủ điều kiện
  cấm text
~~~

Cần kiểm tra từng phần tử và điều kiện của cả danh sách, như số lượng, trùng lặp hoặc tổng dung lượng nếu sản phẩm có giới hạn.

Một danh sách có tồn tại nhưng rỗng không đáp ứng quy tắc “phải có ít nhất một bằng chứng”. Một fileId đúng kiểu vẫn có thể thuộc hồ sơ hoặc tenant khác.

Với PATCH dữ liệu lồng nhau, phải đặc tả thay thế hay ghép từng phần; không để validator hiểu replace trong khi mapper lại merge và giữ subfield cũ.

### 12.3. Metadata cho UI chỉ là hướng dẫn tại một thời điểm

Server có thể trả allowedMethods hoặc mô tả trường cần thiết để UI hiển thị đúng. Nhưng lúc command đến, server vẫn kiểm tra lại trên dữ liệu và policy phù hợp.

Không nhận một bản schema/rule từ client làm thẩm quyền cho request của chính client. Nếu rule có thể cấu hình, quyền sửa/công bố rule và version áp dụng cũng cần được quản lý.

Đồng bộ logic hiển thị giúp giảm lỗi người dùng, không thay việc kiểm chứng backend.

## 13. Lỗi phải giúp sửa input mà không mở dữ liệu ngoài quyền

Một lỗi theo field có thể chứa:

~~~json
{
  "errors": [
    {
      "field": "bankDestinationId",
      "code": "FIELD_NOT_ALLOWED",
      "message": "Không được chọn đích chuyển khoản cho phương thức này."
    },
    {
      "field": "explanation",
      "code": "MISSING_CONDITIONAL_FIELD",
      "message": "Cần mô tả có nội dung khi chọn lý do khác."
    }
  ]
}
~~~

Cần phân biệt nội bộ:

- Input không hợp lệ theo rule.
- Actor không được chọn nhánh/hành động.
- Đối tượng liên quan không đủ điều kiện hoặc ngoài scope.
- Version/trạng thái đã thay đổi.
- Thiếu facts do phụ thuộc đang lỗi.
- Chính sách có cấu hình mâu thuẫn.

Không báo một destination “không được phép vì thuộc tenant B, tài khoản số ...” cho người không có quyền biết dữ liệu đó.

Audit/log có thể ghi commandId, tenant, actor, object/revision, rule version, field path và reason code cần thiết. Tránh lưu nguyên thông tin tài khoản nhận tiền, token hoặc tài liệu nhạy cảm.

Không dùng chuỗi thông báo tự do làm hợp đồng duy nhất cho client. Reason code ổn định giúp kiểm thử và hỗ trợ thay đổi ngôn ngữ.

## 14. Kiểm thử conditional field rules

### 14.1. Bắt đầu từ toàn bộ tổ hợp nghiệp vụ

Với hai method và hai reasonCode của ví dụ, chuẩn bị đủ bốn request hợp lệ cùng facts phù hợp.

Sau đó tạo các biến thể có chủ đích:

~~~text
Bỏ từng field required.
Thêm từng field forbidden.
Thay giá trị hợp lệ bằng null/rỗng/khoảng trắng.
Đổi discriminator nhưng giữ field của nhánh cũ.
Đổi quyền hoặc facts trong khi payload giữ nguyên.
~~~

Kết quả mong đợi phải lấy từ ma trận nghiệp vụ độc lập, không gọi lại chính validator đang được kiểm thử để tính expected result.

### 14.2. Ma trận tình huống

| Tình huống | Điều phải kiểm chứng |
|---|---|
| BANK_TRANSFER thiếu destination | Bị chặn, không tạo trạng thái thiếu đích |
| BANK_TRANSFER có destination null/rỗng | Không coi key xuất hiện là đủ |
| ORIGINAL_PAYMENT gửi destination có giá trị | Không lưu hoặc sử dụng đích của nhánh khác |
| CREATE gửi field bị cấm với null | Xử lý đúng hợp đồng presence nghiêm ngặt |
| OTHER thiếu/blank explanation | Không đáp ứng required |
| ORDER_CANCELLED còn explanation | Bị chặn theo ma trận ví dụ |
| ORDER_CANCELLED nhưng facts không hỗ trợ | Không tin reason code như bằng chứng |
| Enum method/reason không nhận diện được | Không fallback sang nhánh dễ hơn |
| Payload có key trùng cho discriminator | Decode theo chính sách đã đặc tả, không chọn khác nhau giữa các tầng |
| Client gửi requiresApproval=false hoặc isVerified=true | Không tắt kiểm soát hoặc giả trạng thái xác minh |
| Actor không được dùng BANK_TRANSFER | Không được qua chỉ vì cấu trúc field đúng |
| Destination tồn tại nhưng sai tenant/người nhận | Không tạo liên kết hoặc chi trả trái phạm vi |
| PATCH đổi method nhưng không clear destination cũ | Validate candidate cuối và chặn tổ hợp sai |
| PATCH clear destination khi vẫn BANK_TRANSFER | Bị chặn vì trạng thái cuối thiếu required |
| PATCH không gửi method | Giữ nguyên theo hợp đồng, không áp default CREATE |
| PATCH amountMinor=null | Không clear field không được phép clear |
| Đổi reason sang OTHER mà không có explanation | Bị chặn dựa trên candidate cuối |
| Sửa và submit đồng thời | Không sửa nhầm revision đã submit |
| Lỗi khi ghi audit/outbox bắt buộc | Không lưu một phần thay đổi |
| Cùng idempotency key nhưng missing/null có ý nghĩa khác | Không gộp thành cùng command ngoài hợp đồng |
| Nguồn policy/facts không trả lời | Không chọn nhánh ít kiểm soát để tiếp tục |
| Job nhận dữ liệu đã lưu | Dùng cùng method/snapshot, không tự suy diễn nhánh từ field thừa |

### 14.3. Quan sát dữ liệu đã commit sau request bị chặn

Với CREATE không hợp lệ, kiểm tra không có refund, reservation hoặc job của lần thử.

Với PATCH không hợp lệ, đọc lại bằng transaction mới:

~~~text
refundMethod giữ nguyên
destination/explanation giữ nguyên
amount và liên kết payment giữ nguyên
revision/version không phản ánh một thay đổi thành công
không có outbox của command bị chặn
không có bước thực thi/phê duyệt phát sinh ngoài ý định
~~~

Security event hoặc attempt log có thể xuất hiện theo thiết kế. Không nhầm nó với audit chứng minh sửa thành công.

Chỉ kiểm tra HTTP response không phát hiện trường hợp handler đã save một phần rồi mới trả lỗi.

### 14.4. Chèn lỗi trong cập nhật chuyển nhánh

Chuẩn bị draft BANK_TRANSFER với destination hợp lệ. Gửi patch đổi sang ORIGINAL_PAYMENT và clear destination.

Gây lỗi có kiểm soát tại bước bắt buộc sau khi cập nhật trong transaction, chẳng hạn insert audit.

Sau khi transaction kết thúc, toàn bộ trạng thái phải trở lại bản trước: method cũ, destination cũ, version cũ và không có event thành công.

Ca này xác nhận method và các field phụ thuộc không bị chia thành các lần commit độc lập.

### 14.5. Kiểm thử cạnh tranh phải chạm đúng điểm quyết định

Dùng hai transaction/kết nối độc lập cho sửa draft và submit. Điều phối để cả hai cạnh tranh tại cùng trạng thái/version.

Sau khi cả hai kết thúc, kiểm tra:

- Nội dung được submit là một candidate đã được validate đầy đủ.
- Không có field của nhánh cũ còn ảnh hưởng trái quy tắc.
- Không có thay đổi DRAFT âm thầm ghi đè bản đã submit.
- Quy tắc phê duyệt được tính cho đúng revision đó.

Không chỉ mock version hoặc gọi hai request nối tiếp rồi kết luận đã an toàn khi chạy đồng thời.

## 15. Tình huống thực hành: giữ field cũ để đổi nhánh kiểm soát

Giả sử một sản phẩm cho phép tự xử lý một số khoản nhỏ hoàn về giao dịch gốc, nhưng mọi BANK_TRANSFER đều phải qua bước review riêng.

Ban đầu bản nháp có:

~~~text
method = BANK_TRANSFER
destination = destination-12
requiresApproval = true, do server tính
~~~

Caller chỉ PATCH method=ORIGINAL_PAYMENT. Một triển khai lỗi có thể:

~~~text
Validator chỉ đọc patch, không thấy destination nên cho qua.
Mapper giữ destination-12 vì field không được gửi.
Server tính requiresApproval=false theo method mới.
Worker thấy destination còn giá trị nên thực hiện chuyển khoản.
~~~

Kết quả là nhánh kiểm soát và nhánh thực thi không còn cùng ý nghĩa.

Cần sửa các điểm liên quan:

1. Dựng và validate candidate sau khi ghép patch.
2. Không cho ORIGINAL_PAYMENT giữ đích nhận thay thế.
3. Tính field server-controlled từ candidate đã hợp lệ và facts có thẩm quyền.
4. Lưu method, field phụ thuộc và revision nhất quán.
5. Worker thực hiện đúng phương thức/snapshot được chấp nhận.
6. Kiểm tra trước hiệu ứng rằng yêu cầu phê duyệt của chính operation đã được đáp ứng.

Nếu caller chủ động clear destination để chuyển hợp lệ sang ORIGINAL_PAYMENT, luồng phải thực sự hoàn về giao dịch gốc theo chính sách. Không tồn tại một fallback chuyển khoản ẩn.

## 16. Khung đặc tả một bộ conditional rules

~~~text
Hành động: CREATE / PATCH / SUBMIT / EXECUTE:
Đối tượng, tenant và trạng thái áp dụng:
Discriminator và nguồn có thẩm quyền:
Tập nhánh được hỗ trợ và quyền chọn mỗi nhánh:

Với từng field:
  required / optional / forbidden / server-controlled
  điều kiện áp dụng
  kiểu và giá trị hợp lệ
  ý nghĩa missing / null / empty / zero / false
  có được clear hoặc sửa không

Rule giữa các field, cấu trúc lồng nhau và danh sách:
Quy tắc normalize và dựng candidate:
Các đối tượng tham chiếu và điều kiện quan hệ:
Giá trị do server tính:

Version/transaction và thời điểm kiểm tra lại:
Fingerprint idempotency giữ presence thế nào:
Lỗi, audit và dữ liệu không được tiết lộ:
Các ca chuyển nhánh, bỏ trường và lỗi giữa chừng:
~~~

## 17. Câu hỏi tự kiểm tra

1. Vì sao “BANK_TRANSFER cần destination” chưa đủ bảo vệ ORIGINAL_PAYMENT?
2. Field Optional có còn cần kiểm tra quyền và quan hệ khi xuất hiện không?
3. Missing và null khác nhau thế nào trong hợp đồng PATCH của bạn?
4. Đổi discriminator có thể để lại những field cũ nào?
5. Server đang dùng facts nào để quyết định nhánh, và client có giả được facts đó không?
6. Candidate nào được validate, candidate nào được lưu và snapshot nào được worker thực hiện?
7. Nếu một field bị cấm chỉ bị UI ẩn, attacker có thể gửi nó qua những đường nào?
8. Những điều kiện nào cần kiểm tra lại ở submit, approve hoặc trước hiệu ứng ngoài?
9. Bộ test có chứng minh request sai không để lại một phần dữ liệu hoặc job không?

Một conditional rule có thể thực thi phải giữ thống nhất **điều kiện chọn nhánh, ý nghĩa từng field và trạng thái cuối được chấp nhận**. Hợp đồng đó phải tồn tại ở server và tiếp tục đúng qua cập nhật, transaction, phê duyệt và xử lý lại.
