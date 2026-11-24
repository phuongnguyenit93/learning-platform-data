# Consent scope — Phạm vi đồng ý

## Mục tiêu bài học

Trong chương **Consent Rules**, consent scope là phạm vi cụ thể của một quyết định đồng ý: ai đồng ý, cho bên nào, dùng dữ liệu hoặc tài nguyên nào, thực hiện hành động gì, vì mục đích nào, qua kênh nào và trong khoảng thời gian nào.

Một cờ `consent = true` không diễn đạt được các ràng buộc đó. Người dùng đồng ý nhận ưu đãi qua email từ cửa hàng A không có nghĩa là đồng ý nhận SMS, chia sẻ số liên hệ với đối tác B hoặc cho phép một nhân viên truy cập mọi dữ liệu của mình.

Trong bảo mật logic nghiệp vụ, phạm vi đồng ý cần được kiểm tra cùng quyền theo đối tượng, business invariants, state machine, transaction và idempotency. Bài học mô hình hóa các yêu cầu consent đã được sản phẩm xác định thành chính sách kỹ thuật; mỗi loại hành động cần được phân loại rõ thay vì áp dụng một cờ chung cho mọi xử lý.

Sau bài học, bạn có thể:

- Thiết kế scope đủ rõ để backend kiểm tra được.
- Phân biệt phạm vi người dùng đã chọn với phạm vi ứng dụng đang yêu cầu sử dụng.
- Ngăn mở rộng scope, ghép sai nhiều consent và dùng lại consent đã hết hiệu lực.
- Xử lý thay đổi phạm vi, rút lại đồng ý và công việc bất đồng bộ.
- Kiểm thử các tình huống vượt quyền hoặc bỏ qua bước trong vòng đời consent.

## 1. Từ một ô chọn đến một quyền sử dụng có giới hạn

Giả sử người dùng chọn:

> Cho cửa hàng A dùng email đã xác nhận của tôi để gửi ưu đãi qua email trong thời hạn được hiển thị.

Quyết định này có nhiều thành phần độc lập:

- Chủ thể là người dùng đó, không phải mọi thành viên trong tổ chức.
- Bên được phép sử dụng là cửa hàng A.
- Dữ liệu được chọn là email đã xác nhận, không phải toàn bộ hồ sơ.
- Hành động là gửi ưu đãi, không phải xuất danh sách khách hàng cho bên khác.
- Mục đích là liên lạc quảng bá đã được mô tả.
- Kênh là email, không tự bao gồm SMS hoặc cuộc gọi.
- Thời gian hiệu lực và điều kiện rút lại phải được thực thi.

Một hệ thống chỉ lưu `marketingConsent = true` rồi dùng nó để cho phép mọi chiến dịch sẽ đánh mất các ràng buộc này. Lỗi không nằm ở xác thực request mà ở việc biến một quyết định hẹp thành quyền rộng hơn.

Consent cũng không tự cấp quyền vận hành hệ thống. Một nhân viên không có quyền truy cập khách hàng vẫn bị từ chối, dù khách hàng đã đồng ý với một mục đích xử lý cụ thể. Ngược lại, một dịch vụ có quyền kỹ thuật đọc dữ liệu vẫn cần đáp ứng điều kiện consent khi chính sách yêu cầu nó cho hành động đang thực hiện.

## 2. Các chiều cần mô hình hóa

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| Chủ thể dữ liệu | Quyết định này thuộc về ai? | `customer_42`. |
| Người thực hiện quyết định | Ai đang thao tác và có được đại diện không? | Chính chủ qua phiên xác thực hoặc một đại diện đã được kiểm tra thẩm quyền. |
| Tenant | Consent thuộc ranh giới tổ chức nào? | `merchant_A`, không phải mọi cửa hàng. |
| Bên được cấp phạm vi sử dụng | Tổ chức nào được thực hiện mục đích đã mô tả? | Cửa hàng A. |
| Tài nguyên hoặc bộ chọn | Dữ liệu của đối tượng nào được bao phủ? | Một thông tin liên hệ xác định hoặc một tập đối tượng được mô tả rõ. |
| Nhóm dữ liệu | Những loại dữ liệu nào được sử dụng? | Email; không tự thêm số điện thoại hoặc lịch sử mua hàng. |
| Hành động | Được làm gì với dữ liệu? | Gửi thông điệp, dùng để phân nhóm hoặc chia sẻ là các hành động khác nhau. |
| Mục đích | Vì sao thực hiện hành động? | Gửi ưu đãi theo một mục đích được định nghĩa. |
| Kênh | Tương tác qua phương thức nào? | Email, SMS hoặc cuộc gọi. |
| Bên nhận dữ liệu | Dữ liệu được cung cấp cho bên nào trong mô hình? | Chỉ tổ chức đã nêu, không mặc nhiên thêm đối tác độc lập. |
| Thời gian | Bắt đầu, kết thúc và bị rút lại khi nào? | Khoảng hiệu lực do server kiểm tra. |
| Phiên bản | Người dùng đã chọn nội dung và cấu trúc nào? | Phiên bản thông báo, schema scope và revision của grant. |

Trong mô hình minh họa của bài, **bên nhận dữ liệu** là tổ chức nhận quyền sử dụng dữ liệu trong luồng đã mô tả; **địa chỉ nhận email** là tài nguyên liên hệ của chủ thể. Hai khái niệm này không dùng chung một trường `recipient` không rõ nghĩa.

Một thành phần chuyển thư kỹ thuật và một đối tác muốn dùng dữ liệu cho mục đích riêng cũng cần được mô hình hóa khác nhau. Chính sách phải xác định quan hệ và giới hạn của từng bên, không dùng từ “đối tác” để ngầm cho phép mọi mục đích về sau.

### Bộ chọn tài nguyên phải có ngữ nghĩa ổn định

“Các đơn hàng hiện có” và “mọi đơn hàng hiện tại lẫn tương lai” là hai phạm vi khác nhau. Nếu giao diện mô tả một tập hiện tại nhưng backend lưu một truy vấn động bao gồm mọi dữ liệu phát sinh sau này, phạm vi có thể bị mở rộng mà không có quyết định mới.

Có thể dùng danh sách ID cố định, một phiên bản tập dữ liệu hoặc một bộ chọn động được mô tả rõ. Với bộ chọn động, cần đánh giá điều kiện tại thời điểm sử dụng và kiểm soát việc đổi định nghĩa bộ chọn.

Tương tự, consent gắn với một thông tin liên hệ cụ thể có thể cần đánh giá lại khi địa chỉ thay đổi. Nếu sản phẩm chọn mô hình “email đã xác nhận hiện hành của chủ thể”, ngữ nghĩa đó phải được ghi rõ trong scope và chính sách; không tự suy ra từ một trường ID bị bỏ trống.

## 3. Bốn khái niệm không nên trộn lẫn

| Khái niệm | Vai trò |
|---|---|
| Phạm vi được đề nghị | Các lựa chọn và nội dung mà hệ thống đưa ra cho người dùng. |
| Phạm vi đã chọn | Những thành phần người dùng thực sự chấp nhận trong đề nghị đó. |
| Consent grant | Bản ghi bền vững của quyết định, phạm vi và vòng đời hiệu lực. |
| Quyết định cho một lần sử dụng | Kết quả đánh giá grant còn hiệu lực với hành động cụ thể ngay lúc cần thực hiện. |

Đề nghị có ba lựa chọn không có nghĩa người dùng đã đồng ý cả ba. Một grant từng được kích hoạt cũng không phải quyết định cho phép mọi lần sử dụng trong tương lai bất kể thay đổi trạng thái.

Chấp nhận điều khoản tài khoản, xác minh địa chỉ email và đồng ý nhận ưu đãi là các hành động khác nhau nếu chính sách mô hình hóa chúng khác nhau. Không lấy việc hoàn tất một bước làm bằng chứng đã chấp nhận mọi phạm vi của các bước còn lại.

Sự im lặng hoặc request thiếu trường lựa chọn không nên bị tự diễn giải thành một quyết định đồng ý mới. Mọi giá trị mặc định trong backend phải bảo toàn đúng ý nghĩa lựa chọn, thay vì làm rộng phạm vi khi client cũ chưa biết một trường mới.

## 4. Các invariant của consent scope

Một thiết kế nên nêu rõ các điều kiện bắt buộc:

1. Chỉ chủ thể hoặc người đại diện có thẩm quyền đã được xác minh mới được tạo hay thay đổi quyết định của chủ thể đó.
2. Scope được lưu không rộng hơn những lựa chọn đã được chấp nhận theo đúng nội dung đề nghị.
3. Hành động cần consent chỉ được cấp quyết định cho phép khi có grant đang hiệu lực bao phủ đầy đủ hành động đó.
4. Tenant, bên được cấp quyền sử dụng, mục đích, dữ liệu, kênh và bên nhận không được tự mở rộng bằng tham số client.
5. Consent không vượt qua kiểm tra quyền theo đối tượng, trạng thái tài khoản hoặc các invariant nghiệp vụ khác.
6. Grant đã bị rút lại, hết hạn hoặc bị thay thế không được kích hoạt lại bởi retry hay sự kiện cũ.
7. Thay đổi dữ liệu cấu hình không được âm thầm làm ý nghĩa scope đã chọn trở nên rộng hơn.
8. Mọi lần cấp quyết định cần có đủ tham chiếu để giải thích grant và chính sách nào đã được dùng.

Các invariant này cần tồn tại trong dịch vụ nghiệp vụ và lưu trữ, không chỉ trong giao diện cài đặt thông báo.

## 5. Mô hình dữ liệu cho một grant

Ví dụ sau là dữ liệu giả phục vụ thiết kế:

```json
{
  "grantId": "consent_demo_17",
  "tenantId": "merchant_A",
  "subjectId": "customer_42",
  "granteeId": "merchant_A",
  "scope": {
    "resourceSelector": {
      "type": "CONTACT_REF",
      "id": "contact_8",
      "revision": 3
    },
    "dataCategories": ["EMAIL_ADDRESS"],
    "actions": ["SEND_PROMOTION"],
    "purposes": ["PROMOTIONAL_COMMUNICATION"],
    "channels": ["EMAIL"],
    "dataRecipientIds": ["merchant_A"]
  },
  "status": "ACTIVE",
  "validFrom": "2026-11-01T00:00:00Z",
  "validUntil": "2026-12-01T00:00:00Z",
  "noticeVersion": "promotion-email-v3",
  "scopeSchemaVersion": 1,
  "grantRevision": 1
}
```

Grant này không bao phủ SMS, dữ liệu số điện thoại, tổ chức khác hoặc một mục đích phân tích chưa được chọn. Khoảng ngày chỉ là ví dụ, không phải thời hạn mặc định cho các sản phẩm.

Ngoài dữ liệu trên, thường cần lưu tham chiếu tới:

- Người thực hiện và căn cứ đại diện nếu có.
- Đề nghị và các option đã chọn.
- Bản nội dung thông báo đúng phiên bản, ngôn ngữ và cách biểu diễn có liên quan.
- Thời điểm server ghi nhận quyết định cùng command ID.
- Sự kiện kích hoạt, rút lại, thay thế hoặc hết hiệu lực.
- Phiên bản điều khiển dùng để phân xử cập nhật đồng thời.

Một giá trị băm có thể hỗ trợ kiểm tra nội dung có bị thay đổi, nhưng không tự chứng minh ai đã thao tác hoặc rằng người đó đã đọc và hiểu toàn bộ nội dung. Cần giữ mối liên hệ với nguồn nội dung và sự kiện đã được xác thực.

Không bắt buộc thu thập mọi thông tin thiết bị hoặc địa chỉ mạng chỉ vì muốn có “bằng chứng”. Chọn dữ liệu đủ cho mục đích kiểm chứng và bảo vệ quyền truy cập hồ sơ đó; lịch sử consent cũng có thể chứa thông tin nhạy cảm.

## 6. Thu nhận consent mà không cho client tự mở rộng scope

Một cách tổ chức là server tạo đề nghị có định danh và các lựa chọn đã xác định. Client gửi những lựa chọn đã chọn, không tự cung cấp một scope có quyền tùy ý:

```json
{
  "commandId": "cmd_consent_104",
  "offerId": "offer_email_31",
  "selectedOptionIds": ["EMAIL_PROMOTION"],
  "expectedControlVersion": 7
}
```

Backend xử lý theo các bước:

1. Xác thực người gọi và xác định subject từ quan hệ tin cậy.
2. Kiểm tra quyền quyết định cho subject và tenant tương ứng.
3. Tải đề nghị đúng phiên bản, kiểm tra còn hiệu lực và có thuộc ngữ cảnh này không.
4. Xác minh mọi option đã chọn nằm trong đề nghị và không bị thay đổi ý nghĩa.
5. Dựng scope chuẩn từ cấu hình server, gắn với các tài nguyên thực tế được phép.
6. Kiểm tra điều kiện xác nhận bổ sung nếu chính sách của luồng yêu cầu.
7. Ghi grant, bằng chứng và kết quả lệnh bằng giao dịch có kiểm soát.

Trường `subjectId` nếu xuất hiện trong request chỉ là đối tượng được yêu cầu, không phải bằng chứng về thẩm quyền. Một nhân viên hỗ trợ không được tự tạo consent thay khách hàng bằng cách biết ID hoặc có quyền sửa hồ sơ thông thường.

Với một liên kết xác nhận có thời hạn, quyền của liên kết cần gắn với đúng subject, contact, đề nghị, scope và hành động. Không lấy một token xác nhận email để chấp nhận một scope mới rộng hơn được cấu hình sau khi token được tạo. Nếu dùng cookie phiên, luồng thay đổi consent cũng cần biện pháp chống yêu cầu giả mạo phù hợp với cơ chế xác thực.

### Giao diện phải giữ được ý nghĩa của lựa chọn

Tách các lựa chọn có mục đích hoặc kênh khác nhau khi chúng là các quyết định khác nhau trong mô hình sản phẩm. Không hiển thị một nhãn hẹp như “nhận email ưu đãi” rồi lưu các option chia sẻ dữ liệu hoặc SMS không được thể hiện.

Server không nên tự bật một option mới khi client cũ gửi payload thiếu trường đó. Việc thêm lựa chọn vào giao diện cần đi cùng phiên bản đề nghị và quy tắc tương thích, không biến giá trị thiếu thành chấp nhận.

## 7. Kiểm tra scope cho một lần sử dụng

### 7.1. Dựng yêu cầu sử dụng từ nghiệp vụ thực tế

Một yêu cầu sử dụng nên mô tả được:

```text
tenant, subject, người thực thi và bên được đại diện,
hành động, tài nguyên, nhóm dữ liệu thực sự cần dùng,
mục đích, kênh, bên nhận dữ liệu, thời điểm và operation ID
```

Các thuộc tính này phải đến từ luồng nghiệp vụ đáng tin cậy. Không để một chiến dịch quảng bá tự khai là thông báo trạng thái đơn hàng để tránh kiểm tra consent. Backend phân loại hành động và mục đích theo nội dung, cấu hình và quyền của dịch vụ, không chỉ theo một header `purpose`.

Đối với hành động không dùng cùng một loại consent, chính sách tương ứng vẫn phải được đánh giá tường minh. “Không tìm thấy cấu hình yêu cầu consent” không được mặc định trở thành cho phép mọi xử lý.

Một biểu thức tổng quát là:

```text
Được thực hiện
  = có quyền vận hành trên đúng đối tượng
    AND thỏa invariant và trạng thái nghiệp vụ
    AND thỏa chính sách xử lý của hành động
    AND, khi chính sách yêu cầu consent,
        có grant hiệu lực bao phủ yêu cầu sử dụng
```

### 7.2. So khớp mọi chiều liên quan

Để grant bao phủ một lần sử dụng, cần kiểm tra:

- Cùng subject và tenant; bên được cấp phạm vi sử dụng phù hợp.
- Hành động, mục đích và kênh nằm trong những lựa chọn được chấp nhận.
- Dữ liệu thực sự dùng là tập con của dữ liệu được cho phép.
- Tài nguyên nằm trong bộ chọn có đúng ngữ nghĩa.
- Bên nhận dữ liệu được bao phủ và người thực thi có quyền đại diện phù hợp.
- Trạng thái hiện tại cho phép sử dụng, chưa bị rút lại hoặc thay thế.
- Thời điểm thuộc khoảng hiệu lực.
- Phiên bản scope được hiểu và tương thích với chính sách hiện hành.

Với quy ước thời gian `[validFrom, validUntil)`, đúng tại thời điểm bắt đầu có thể sử dụng; đúng tại thời điểm kết thúc thì không. Nếu cho phép không có thời điểm kết thúc, đó phải là ý nghĩa được cấu hình rõ, không phải hậu quả của lỗi parse hoặc trường bị thiếu ngoài dự kiến.

Giả mã Java minh họa phần so khớp một grant đã được tải theo snapshot phù hợp:

```java
boolean covers(ConsentGrant grant, DataUse use, Instant now) {
    if (!grant.isActive() || use.dataCategories().isEmpty()) {
        return false;
    }

    boolean inTime = !now.isBefore(grant.validFrom())
        && (grant.validUntil() == null
            || now.isBefore(grant.validUntil()));

    return inTime
        && grant.tenantId().equals(use.tenantId())
        && grant.subjectId().equals(use.subjectId())
        && grant.granteeId().equals(use.granteeId())
        && grant.actions().contains(use.action())
        && grant.purposes().contains(use.purpose())
        && grant.channels().contains(use.channel())
        && grant.dataCategories().containsAll(use.dataCategories())
        && grant.dataRecipientIds().contains(use.dataRecipientId())
        && resourcePolicy.covers(grant.resourceSelector(), use.resourceRef());
}
```

Đây là giả mã về hợp đồng, không phải chương trình chạy độc lập. Nó chưa thực hiện xác thực, phân quyền, kiểm tra phiên bản schema hay giải quyết cạnh tranh. Các giá trị của `DataUse` phải được tạo từ kế hoạch xử lý đã xác minh, bao gồm đầy đủ dữ liệu sẽ dùng; bỏ bớt trường khỏi kế hoạch rồi vẫn đọc dữ liệu đó là một lỗi logic.

Các mã mục đích và hành động nên được quản lý rõ ràng. Không dùng phép kiểm tra chuỗi kiểu “có chứa từ marketing” hoặc coi wildcard do client gửi là một quyền hợp lệ. Giá trị chưa biết phải đi theo quy tắc từ chối hoặc đánh giá lại, thay vì được ánh xạ về một phạm vi chung rộng hơn.

## 8. Không ghép các grant thành một phạm vi chưa từng được chọn

Giả sử có hai grant độc lập:

| Grant | Dữ liệu | Mục đích | Kênh | Bên nhận |
|---|---|---|---|---|
| G1 | Email | Ưu đãi | Email | Cửa hàng A |
| G2 | Số điện thoại | Hỗ trợ | SMS | Đơn vị B |

Một cách triển khai sai là hợp nhất riêng từng cột:

```text
Dữ liệu được phép = email hoặc số điện thoại
Mục đích được phép = ưu đãi hoặc hỗ trợ
Kênh được phép = email hoặc SMS
Bên nhận được phép = A hoặc B
```

Sau đó hệ thống có thể cho B dùng số điện thoại để gửi SMS ưu đãi, dù không grant nào bao phủ tổ hợp đó. Lỗi này là mất quan hệ giữa các chiều khi tạo một tích kết hợp rộng hơn.

Với mô hình đơn giản, một hạng mục xử lý phải có ít nhất một grant bao phủ đầy đủ các chiều của chính hạng mục đó. Nếu hệ thống cho phép kết hợp nhiều grant, quy tắc kết hợp phải giữ các quan hệ và được định nghĩa tường minh; không chỉ lấy hợp của từng danh sách.

Một batch gồm nhiều hạng mục có thể được tách để đánh giá từng phần. Nếu chỉ một phần được phép, hợp đồng phải nêu rõ từ chối toàn bộ hay thực hiện phần hợp lệ. Không gắn nhãn batch là “đã có consent” rồi dùng nhãn đó cho mọi hàng và mọi cột dữ liệu.

Tương tự, email đã được cho phép không tự bao phủ số điện thoại chỉ vì hai trường cùng nằm trong object `contact`. Danh mục dữ liệu cần đủ rõ để một truy vấn lấy thêm trường không âm thầm mở rộng nội dung xử lý.

## 9. State machine và thay đổi phạm vi

Một vòng đời minh họa:

```text
OFFERED -> PENDING_CONFIRMATION -> ACTIVE
OFFERED -----------------------> ACTIVE
ACTIVE -> REVOKED
ACTIVE -> EXPIRED
ACTIVE -> SUPERSEDED
```

Nhánh xác nhận bổ sung chỉ áp dụng khi chính sách của luồng yêu cầu. Chưa hoàn tất bước đó thì chưa được dùng trạng thái chờ như một grant hiệu lực.

`REVOKED`, `EXPIRED` và `SUPERSEDED` không tự trở về `ACTIVE` khi người dùng đăng nhập lại, worker chạy lại hoặc một callback cũ tới muộn. Nếu người dùng đồng ý lại, tạo một quyết định mới có bằng chứng và quan hệ lịch sử rõ ràng.

### Thu hẹp, mở rộng và sửa nội dung không giống nhau

- **Thu hẹp:** bỏ một mục đích, kênh hoặc nhóm dữ liệu; phải phản ánh ở quyết định sử dụng tiếp theo.
- **Mở rộng:** thêm bên nhận, hành động, kênh hoặc dữ liệu; cần quyết định phù hợp với phạm vi mới, không tự sao chép trạng thái `ACTIVE`.
- **Sửa cách diễn đạt:** có thể giữ nguyên ngữ nghĩa hoặc làm thay đổi ngữ nghĩa; cần quy tắc tương thích được đánh giá, không chỉ nhìn số phiên bản.

Không phải mọi lần tăng phiên bản giao diện đều làm toàn bộ grant hết hiệu lực. Ngược lại, cùng một tên scope không chứng minh rằng ý nghĩa vẫn giữ nguyên. Lưu nội dung bất biến theo phiên bản và một chính sách tương thích rõ ràng giúp phân biệt hai trường hợp.

Một thay đổi như thêm `recipientIds = ALL_PARTNERS` vào cấu hình không được làm các grant cũ tự bao phủ mọi đối tác. Schema hoặc phạm vi mới mà consumer cũ chưa hiểu cũng không được rơi về một boolean cho phép.

## 10. Rút lại đồng ý và ý nghĩa của phạm vi rút lại

Người dùng có thể rút một grant cụ thể hoặc yêu cầu ngừng một mục đích/kênh trong phạm vi rộng hơn. Hai ý định này cần được mô hình hóa và hiển thị chính xác.

Ví dụ, nếu người dùng chọn “ngừng mọi email ưu đãi của cửa hàng A”, chỉ đổi trạng thái một grant cũ có thể chưa đủ nếu còn một grant khác độc lập bao phủ cùng hành động. Hệ thống phải xác định các grant và quy tắc hiệu lực liên quan để kết quả thực tế khớp với phạm vi rút lại đã chọn.

Một thiết kế có thể rút mọi grant hiện hành khớp yêu cầu trong cùng ranh giới điều khiển, đồng thời giữ dấu vết phiên bản để sự kiện hoặc dữ liệu nhập lại cũ không làm chúng hoạt động trở lại. Một quyết định đồng ý mới về sau phải là hành động mới có căn cứ, không phải replay của lệnh chấp nhận trước đó.

Nếu chỉ rút một grant hẹp, không được vô tình hủy các lựa chọn độc lập khác. Giao diện cần mô tả khả năng xử lý còn lại một cách trung thực, không báo “đã tắt toàn bộ” khi vẫn tồn tại một đường cho phép tương đương.

Rút consent không đồng nghĩa tự xóa mọi dữ liệu, hủy mọi giao dịch hoặc dừng mọi loại thông báo. Các luồng như thông báo trạng thái đơn cần được phân loại và đánh giá theo chính sách riêng. Không được đổi nhãn một thông điệp ưu đãi thành thông báo vận hành chỉ để tiếp tục gửi sau khi người dùng đã tắt mục đích đó.

Lịch sử quyết định và dữ liệu nghiệp vụ có vòng đời riêng. Giữ dữ liệu tối thiểu cần thiết để giải thích trạng thái, bảo vệ quyền truy cập và tránh xóa dấu vết khiến hệ thống không biết grant đã bị rút lại. Việc giữ lịch sử không tạo quyền tiếp tục sử dụng dữ liệu cho mục đích đã bị ngừng.

## 11. Transaction, idempotency và cạnh tranh

### 11.1. Áp dụng một quyết định

Luồng ghi tham chiếu trong một cơ sở dữ liệu có thể là:

```text
BEGIN TRANSACTION
  Xác thực và kiểm tra quyền quyết định cho subject/tenant.
  Khóa bản ghi điều khiển consent ổn định của subject trong phạm vi.
  Phân xử commandId và dấu vân tay nội dung.

  Nếu lệnh đã có: trả thông tin lệnh và trạng thái hiện tại được phép xem.
  Nếu cùng commandId nhưng khác nội dung: từ chối xung đột.

  Kiểm tra expectedControlVersion.
  Kiểm tra đề nghị, lựa chọn, xác nhận và chuyển trạng thái.
  Ghi quyết định, scope bất biến tương ứng và hiệu lực mới.
  Tăng phiên bản điều khiển.
  Ghi kết quả lệnh và outbox.
COMMIT
```

Ràng buộc duy nhất hoặc cơ chế tương đương cần bảo vệ cả trường hợp `commandId` chưa tồn tại. Không dựa vào “đọc không thấy rồi insert” ở hai request cạnh tranh mà thiếu phân xử.

Một lệnh đồng ý và một lệnh rút lại cùng dùng phiên bản cũ không nên âm thầm ghi đè nhau theo thứ tự ghi cuối. Kiểm tra phiên bản hoặc cơ chế phân xử tương ứng buộc bên dùng dữ liệu cũ phải đánh giá lại trạng thái mới.

### 11.2. Retry lệnh cũ sau khi đã rút lại

Giả sử lệnh C1 đã tạo grant G1, sau đó C2 rút G1. Khi C1 được gửi lại vì client cũ retry, idempotency phải nhận diện rằng đó là lệnh đã xử lý; không chạy lại việc kích hoạt.

Phản hồi có thể cho biết C1 từng được chấp nhận và trạng thái hiện tại của G1 là đã rút lại. Không trả một snapshot `ACTIVE` cũ như thể đó là trạng thái hiện hành, khiến client hoặc downstream dùng nó làm quyền xử lý mới.

Nếu hệ thống có nhiều grant, phiên bản điều khiển của subject dùng cho phân xử không thay thế revision riêng của từng grant. Một lần đổi lựa chọn khác có thể yêu cầu đánh giá lại snapshot, nhưng không có nghĩa mọi grant độc lập đều tự bị rút.

### 11.3. Cạnh tranh với một lần sử dụng dữ liệu

Một luồng nguy hiểm:

```text
T1: Worker đọc grant đang ACTIVE.
T2: Người dùng rút lại; giao dịch commit.
T3: Worker dùng kết quả T1 để cấp một quyết định xử lý mới.
```

Nếu yêu cầu là không cấp quyết định sử dụng mới sau khi rút lại có hiệu lực, chỉ đọc trước rồi ghi sau không đủ. Trong thiết kế cùng cơ sở dữ liệu, việc rút lại và việc cấp operation có thể cùng phân xử trên bản ghi điều khiển consent ổn định, với dữ liệu quyền được đọc ở mức nhất quán phù hợp.

Nếu giao dịch cấp operation commit trước, operation thuộc nhóm đã được tiếp nhận trước thay đổi. Nếu giao dịch rút lại commit trước, lần cấp operation sau phải thấy trạng thái mới và bị ngăn khi không còn grant bao phủ. Bảo đảm cần phát biểu theo thứ tự quyết định bền vững, không theo đồng hồ client hoặc thứ tự request bắt đầu.

Transaction cục bộ không tự bao phủ một dịch vụ consent ở xa và cơ sở dữ liệu nghiệp vụ riêng. Khi tách hệ thống, phải thiết kế ranh giới cấp quyết định, cơ chế phiên bản và giới hạn độ trễ; không gọi hai request độc lập là một giao dịch nguyên tử.

## 12. Queue, cache và các lần sử dụng sau đó

### 12.1. Đồng ý lúc tạo job không đủ cho mọi lần thực thi

Một job gửi email có thể được tạo trước khi người dùng rút consent nhưng thực thi sau đó. Theo chính sách minh họa của bài, worker cần đánh giá lại trước khi cấp quyền thực hiện bước gửi. Job không được chỉ mang theo `consent=true` từ lúc tạo.

Operation nên lưu các tham chiếu cần giải thích như subject, tenant, mục đích, nhóm dữ liệu, bên nhận, grant ID/revision, phiên bản quyết định và trạng thái. Chỉ truyền dữ liệu cần thiết tới consumer có đúng quyền; không phát dữ liệu đầy đủ sang một topic chung vì grant từng cho phép một mục đích khác.

Các job đang chờ không còn đủ điều kiện có thể chuyển sang `BLOCKED_BY_CONSENT` hoặc bị hủy theo chính sách. Worker nhận lại cùng job không được tạo thêm tác động; cần khử trùng lặp theo operation ID và bảo vệ chuyển trạng thái.

### 12.2. Giới hạn của việc dừng tác động bên ngoài

Kiểm tra ngay trước khi gửi vẫn có một khoảng cạnh tranh: consent có thể bị rút sau kiểm tra nhưng trước khi nhà cung cấp tạo tác động. Vì vậy, cần phân biệt:

- Không cấp quyết định xử lý mới sau mốc hiệu lực theo ranh giới đã thiết kế.
- Xử lý công việc đã được cấp trước đó theo chính sách trạng thái.
- Khả năng hủy một yêu cầu đã gửi ra hệ thống bên ngoài.

Không thể suy ra rằng không có thông điệp nào tới sau mốc rút lại chỉ từ một câu `if (active)`. Nếu bên ngoài không hỗ trợ hủy hoặc phân xử tương ứng, hệ thống cần thừa nhận giới hạn, giảm khoảng trễ và đối soát công việc đang xử lý. Thông điệp đã gửi hoặc dữ liệu đã được tải không tự biến mất khi cập nhật trạng thái consent.

### 12.3. Cache phải xét phạm vi và độ mới

Khóa cache cho quyết định cần phân biệt subject, tenant và các chiều sử dụng liên quan, cùng phiên bản trạng thái/chính sách. Cache chỉ theo `subjectId` có thể lấy quyết định cho email để cho phép SMS hoặc lấy quyền của cửa hàng A dùng tại B.

Đưa version vào khóa chưa đủ nếu caller vẫn có thể chọn hoặc tiếp tục dùng version cũ mà không kiểm tra nguồn đáng tin cậy. Cần cơ chế biết trạng thái hiện tại và độ trễ được chấp nhận. Với bước nhạy cảm đòi hỏi dừng cấp quyền mới ngay theo nguồn sự thật, cache cho phép đồng bộ trễ không cung cấp cùng bảo đảm.

Sự kiện có thể đến lặp hoặc sai thứ tự. Consumer không được áp dụng sự kiện kích hoạt cũ sau sự kiện rút lại mới. Nếu sự kiện là snapshot đầy đủ, có thể quản lý theo version phù hợp; nếu là thay đổi từng phần, phải xử lý thứ tự hoặc phát hiện khoảng trống và đồng bộ lại để không mất một thay đổi độc lập.

Khi nguồn trạng thái không hoạt động, không coi “không đọc được consent” là “đã đồng ý”. Với hành động yêu cầu consent, có thể tạm giữ công việc hoặc từ chối cấp quyết định mới. Hành vi dự phòng cần được xác định theo loại thao tác, đồng thời duy trì đường quản lý lựa chọn và phục hồi trạng thái phù hợp.

## 13. Những lỗi mở rộng scope thường gặp

| Lỗi | Hậu quả | Kiểm soát cần có |
|---|---|---|
| Một boolean cho mọi consent | Mất mục đích, kênh và bên nhận | Grant và yêu cầu sử dụng có các chiều rõ ràng. |
| Tin `subjectId` hoặc tenant do client khai | Quyết định thay người khác hoặc sang tổ chức khác | Xác thực, quyền đại diện và quyền đối tượng. |
| Nhãn giao diện hẹp nhưng scope lưu rộng | Ghi nhận nhiều quyền hơn lựa chọn | Đề nghị có phiên bản, ánh xạ option phía server. |
| Gộp riêng từng chiều của nhiều grant | Tạo tổ hợp chưa từng được chọn | So khớp trọn một hạng mục hoặc quy tắc kết hợp giữ quan hệ. |
| Thêm trường hoặc đối tác vào cấu hình cũ | Grant cũ bị mở rộng âm thầm | Scope bất biến theo revision và đánh giá tương thích. |
| Đổi purpose qua query hoặc header | Né chính sách consent | Phân loại mục đích từ nghiệp vụ đáng tin cậy. |
| Token xác nhận dùng cho scope khác | Bỏ qua bước chấp nhận phạm vi mới | Ràng buộc subject, đề nghị, scope và thời hạn. |
| Retry đồng ý cũ kích hoạt lại grant | Vô hiệu hóa việc rút lại | Idempotency, phiên bản và chuyển trạng thái hợp lệ. |
| Chỉ rút một grant khi người dùng tắt cả mục đích | Một grant trùng khác tiếp tục cho phép | Thực thi đúng phạm vi yêu cầu rút lại và giải thích hiệu lực còn lại. |
| Job giữ boolean lúc tạo | Vẫn xử lý sau thay đổi | Đánh giá lại ở điểm thực thi và chính sách công việc đang chạy. |
| Cache quyết định thiếu chiều hoặc dùng version cũ | Cho phép sai kênh, bên nhận hoặc trạng thái | Khóa đúng ngữ cảnh và kiểm tra độ mới. |
| Gọi dữ liệu dẫn xuất là ngoài scope một cách mặc định | Tiếp tục dùng dữ liệu liên quan cho mục đích khác | Phân loại dữ liệu và hành động dẫn xuất theo chính sách, không chỉ theo tên cột. |

Hash email, mã tham chiếu hoặc một audience được tạo từ dữ liệu cá nhân không tự chứng minh rằng mọi ràng buộc mục đích đã hết áp dụng. Cần xác định dữ liệu và hành động thực sự, thay vì đổi cách biểu diễn để bỏ qua scope.

## 14. Dấu vết và quan sát hiệu lực

Một lần cấp hoặc từ chối quyết định nên có đủ thông tin để đối soát:

- Operation ID, subject và tenant theo cách quản lý truy cập phù hợp.
- Hành động, mục đích, kênh, nhóm dữ liệu và bên nhận được đánh giá.
- Grant ID/revision hoặc mã lý do không có grant bao phủ.
- Phiên bản schema, chính sách và trạng thái liên quan.
- Thời điểm đánh giá và kết quả: cho phép, từ chối hoặc chờ xác minh.

Không cần sao chép email, số liên hệ hoặc toàn bộ nội dung xử lý vào audit chỉ để chứng minh đã có consent. Dùng tham chiếu và dữ liệu tối thiểu phục vụ kiểm chứng, bảo vệ cả log, event và hồ sơ quyết định.

Các chỉ số có ích gồm số lần bị từ chối do sai chiều scope, job bị ngăn sau khi rút lại, độ trễ đồng bộ trạng thái, grant bị kích hoạt lại trái chuyển trạng thái và khoảng thời gian chờ khi nguồn consent gặp lỗi. Phân biệt truy cập màn hình quản lý consent với hành động sử dụng dữ liệu thực tế.

Số grant `ACTIVE` lớn không chứng minh cơ chế đúng. Cần kiểm tra rằng mỗi hành động đã dùng đúng grant, các yêu cầu rút lại có hiệu lực thật và không có đường gọi khác bỏ qua chính sách.

## 15. Kiểm thử tình huống tấn công logic

### 15.1. Ma trận phạm vi

Với grant email ưu đãi của cửa hàng A, kiểm tra từng thay đổi độc lập:

| Yêu cầu sử dụng | Kết quả cần xác minh |
|---|---|
| Đúng subject, email, mục đích, hành động, A và khoảng hiệu lực | Được xét cho phép sau khi các quyền và invariant khác đều đạt. |
| Đổi sang SMS hoặc thêm số điện thoại | Không được bao phủ bởi grant email. |
| Đổi bên nhận sang B | Không được tự cho phép. |
| Giữ email nhưng đổi sang mục đích chưa được chọn | Không dùng lại grant cũ như quyền chung. |
| Đổi subject hoặc tenant | Bị từ chối theo quyền và phạm vi. |
| Đúng tại `validUntil` | Không còn hiệu lực theo quy ước khoảng thời gian đã chọn. |
| Schema hoặc mã mục đích chưa biết | Không rơi về một quyền rộng hơn. |
| Dùng bộ chọn dữ liệu hiện tại để lấy thêm dữ liệu tương lai | Theo đúng ngữ nghĩa đã được chọn, không tự mở rộng. |

Thêm bài kiểm tra G1 và G2 ở phần ghép grant: tổ hợp chưa được grant nào bao phủ phải bị từ chối. Với batch, kiểm tra cả dữ liệu thực sự được đọc và bên thực sự nhận, không chỉ metadata khai báo.

### 15.2. Quyền quyết định và bỏ qua bước

- Đổi `subjectId`, tenant hoặc `offerId` sang đối tượng khác: không tạo grant trái quyền.
- Người chỉ có quyền sửa hồ sơ gọi API consent thay khách hàng: không mặc nhiên được phép.
- Client thêm option không có trong đề nghị hoặc gửi wildcard: từ chối hoặc xử lý theo hợp đồng hạn chế rõ ràng.
- Request thiếu option mới: không tự bật option đó.
- Dùng token xác nhận cũ cho đề nghị, contact hoặc scope khác: không kích hoạt.
- Chưa hoàn tất xác nhận bổ sung mà job đã chạy: không được coi trạng thái chờ là `ACTIVE`.

### 15.3. Đồng thời, retry và rút lại

1. Hai request cùng command và cùng nội dung: một quyết định tương ứng, không nhân bản grant hoặc bằng chứng nghiệp vụ.
2. Cùng command nhưng khác lựa chọn: xung đột, không cập nhật ngầm phạm vi.
3. Đồng ý và rút lại cùng dùng phiên bản cũ: có phân xử hoặc xung đột rõ ràng, không ghi đè mất quyết định.
4. Retry lệnh đồng ý sau khi đã rút lại: không kích hoạt lại; phản hồi không trình bày snapshot cũ như trạng thái hiện tại.
5. Giao dịch rút lại commit trước giao dịch cấp operation: operation cần consent không được tiếp nhận bằng trạng thái cũ trong mô hình nhất quán đã chọn.
6. Operation commit trước khi rút lại: được xử lý theo chính sách công việc đã tiếp nhận; worker đánh giá lại ở bước được quy định.
7. Sự kiện kích hoạt tới sau sự kiện rút lại: dữ liệu chiếu không lùi phiên bản.
8. Rút mọi email ưu đãi khi có nhiều grant trùng phạm vi: không còn một grant cũ làm hành động vẫn được phép ngoài ý định.

Dùng điểm đồng bộ để tái hiện chính xác thứ tự giao dịch và kiểm tra trên cơ chế lưu trữ cần bảo vệ. Chỉ mock `isConsentActive()` trả true/false không bộc lộ lỗi cạnh tranh hay ghép sai phạm vi.

### 15.4. Các đường sử dụng dữ liệu khác

- Danh sách chiến dịch được tạo trước khi rút lại nhưng gửi sau: không dựa mãi vào snapshot boolean.
- Export, API quản trị và consumer nền: cùng chính sách phạm vi tương ứng, không dùng quyền kỹ thuật để mở rộng dữ liệu.
- Cache được tạo cho kênh email: không cho phép dùng tại SMS hoặc tenant khác.
- Nguồn trạng thái không truy cập được: không tự chuyển sang cho phép.
- Worker nhận job lặp: không tạo thêm tác động và không tái kích hoạt grant.
- Dữ liệu hoặc bên nhận thực tế khác kế hoạch đã xét: phát hiện và ngăn việc sử dụng ngoài phạm vi.

Kiểm tra trạng thái bền vững, dữ liệu thực sự được dùng, đích nhận và tác động cuối cùng. Một request có `consentId` hoặc một nhánh code đã gọi policy không đủ chứng minh consent scope được thực thi.

## 16. Bài tập thiết kế

Một người dùng đã đồng ý nhận email ưu đãi từ cửa hàng A, nhưng chưa chọn SMS hoặc chia sẻ với B. Một job chiến dịch được xếp hàng. Sau đó người dùng tắt mọi email ưu đãi của A; đồng thời một callback xác nhận cũ và một request retry đồng ý tới hệ thống.

Hãy mô tả mô hình dữ liệu, điểm phân xử và cách xử lý cho các câu hỏi:

1. Scope phải có những chiều nào để job không tự thêm số điện thoại hoặc bên B?
2. Request retry và callback cũ được ràng buộc thế nào để không kích hoạt lại lựa chọn đã rút?
3. Nếu có hai grant cùng bao phủ email ưu đãi, hành động “tắt mọi email ưu đãi” thay đổi hiệu lực thế nào?
4. Job đã tiếp nhận nhưng chưa gửi cần được đánh giá và chuyển trạng thái ở đâu?
5. Nếu yêu cầu đã ra ngoài, hệ thống có thể bảo đảm điều gì và cần đối soát điều gì?
6. Cache, outbox và consumer dùng phiên bản nào để không áp dụng trạng thái cũ?
7. Bằng chứng tối thiểu nào giải thích được vì sao từng lần sử dụng đã được cho phép hoặc bị ngăn?
