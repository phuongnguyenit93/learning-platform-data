# Transaction confirmation — Xác nhận giao dịch nhạy cảm theo đúng nội dung

> **Chương:** Step-up  
> **Chủ đề:** Transaction confirmation  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào xác nhận giao dịch nhạy cảm sau đăng nhập: cách gắn bằng chứng xác thực với đúng nội dung giao dịch, giúp người dùng hiểu điều họ đang chấp thuận, ngăn thay đổi dữ liệu sau xác nhận và bảo vệ quy trình từ lúc tạo challenge đến lúc thực thi.

## 1. Transaction confirmation là gì?

**Transaction confirmation (xác nhận giao dịch)** là bước yêu cầu người dùng xem xét và chấp thuận một hành động cụ thể với các thuộc tính quan trọng đã được xác định, chẳng hạn người nhận, số tiền, loại tiền, tài khoản nguồn hoặc nội dung thay đổi. Hệ thống thu thập bằng chứng xác nhận theo policy và chỉ thực hiện đúng giao dịch đã được người dùng chấp thuận.

Ví dụ, Mai đã đăng nhập vào ứng dụng ngân hàng. Cô tạo lệnh chuyển 5.000.000 VND tới tài khoản của An. Trước khi chuyển tiền, ứng dụng hiển thị tên người nhận, số tài khoản đã che một phần, ngân hàng thụ hưởng, số tiền và phí. Mai xác nhận bằng passkey hoặc một phương thức step-up được policy chấp nhận. Server ràng buộc bằng chứng xác nhận với đúng nội dung lệnh chuyển. Nếu số tiền hoặc người nhận thay đổi sau đó, xác nhận cũ không còn hiệu lực.

Transaction confirmation thường được dùng cho thanh toán, chuyển tiền, thêm người thụ hưởng, thay đổi thông tin khôi phục, cấp quyền quản trị, ký hợp đồng hoặc hành động khó đảo ngược.

**Điểm cốt lõi:** bằng chứng xác thực phải gắn với đúng giao dịch mà người dùng đã xem và chấp thuận. Một lần đăng nhập thành công hoặc một OTP hợp lệ chung chung không tự chứng minh người dùng đã chấp thuận một khoản tiền, người nhận hay thay đổi cụ thể.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt đăng nhập, step-up authentication, transaction confirmation và authorization.
2. Xác định những thuộc tính giao dịch phải được hiển thị và ràng buộc với xác nhận.
3. Thiết kế transaction snapshot bất biến và challenge gắn với giao dịch.
4. Giải thích dynamic linking giữa số tiền, người nhận và bằng chứng xác nhận.
5. Chọn phương thức xác nhận phù hợp và hiểu giới hạn của OTP, push approval, passkey và chữ ký giao dịch.
6. Ngăn replay, sửa giao dịch, race condition, TOCTOU và thực thi trùng lặp.
7. Thiết kế trạng thái giao dịch, expiry, cancellation, idempotency, audit và recovery.
8. Kiểm thử end-to-end để bảo đảm chỉ giao dịch đã được chấp thuận mới được thực hiện.

## 2. Transaction confirmation khác đăng nhập và step-up như thế nào?

Các cơ chế này có quan hệ nhưng không thay thế nhau:

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| **Authentication** | Ai đang chứng minh quyền kiểm soát credential? | Người dùng đăng nhập bằng passkey. |
| **Step-up authentication** | Phiên hiện tại có cần bằng chứng mạnh hơn hoặc mới hơn không? | Yêu cầu MFA trước khi đổi thông tin khôi phục. |
| **Transaction confirmation** | Người dùng có chấp thuận đúng hành động và các thuộc tính giao dịch cụ thể không? | Xác nhận chuyển 5.000.000 VND tới người nhận đã hiển thị. |
| **Authorization** | Principal có quyền thực hiện hành động trên tài nguyên này không? | Account có được phép chuyển tiền từ tài khoản nguồn đó không? |
| **Execution** | Hệ thống có thực thi giao dịch đã được kiểm tra và chấp thuận không? | Ghi nợ, ghi có và lưu transaction result. |

Một phiên có thể đã được xác thực mạnh nhưng vẫn cần transaction confirmation cho từng hành động. Ngược lại, người dùng bấm nút “Đồng ý” không có nghĩa họ đã được xác thực hoặc có quyền thực hiện hành động.

Ví dụ, quản trị viên có passkey và session hợp lệ. Điều đó không có nghĩa mọi lệnh cấp quyền đều đã được người đó chấp thuận. Mỗi thao tác đặc quyền cần được kiểm tra authorization; một số thao tác còn cần step-up và xác nhận nội dung cụ thể.

## 3. Threat model: người dùng cần xác nhận điều gì?

Transaction confirmation nhằm giảm các rủi ro như:

- **Session hijacking:** attacker chiếm phiên hợp lệ và cố thực hiện giao dịch.
- **Phishing/relay:** attacker lừa người dùng nhập OTP hoặc chấp thuận một yêu cầu khác.
- **Push fatigue:** gửi nhiều yêu cầu push để người dùng vô tình bấm approve.
- **Transaction substitution:** nội dung hiển thị khác với nội dung server thực hiện.
- **Parameter tampering:** thay số tiền, người nhận, tài khoản nguồn hoặc loại tiền sau khi người dùng xem.
- **Replay:** gửi lại bằng chứng xác nhận đã được sử dụng.
- **Race condition:** giao dịch thay đổi giữa lúc kiểm tra và lúc thực thi.
- **Compromised client:** malware hoặc script thay nội dung trên màn hình hay sửa request.
- **Insider/API abuse:** dịch vụ trung gian hoặc nhân viên thay dữ liệu sau khi xác nhận.
- **Confused deputy:** một service dùng bằng chứng của giao dịch này để thực hiện giao dịch khác.

Cần xác định attacker có thể kiểm soát browser/app, mạng, session, API request, thiết bị phụ hoặc một service downstream đến mức nào. Biện pháp bảo vệ chỉ có ý nghĩa khi ranh giới tin cậy và giả định được nêu rõ.

## 4. Xác định dữ liệu giao dịch cần được xác nhận

Không nên yêu cầu người dùng xác nhận một nhãn mơ hồ như “Tiếp tục?” khi hành động có hậu quả đáng kể. Nội dung hiển thị phải nêu những thuộc tính giúp người dùng hiểu họ đang chấp thuận điều gì.

Với lệnh chuyển tiền, các thuộc tính có thể gồm:

- tài khoản nguồn hoặc tên chủ tài khoản nguồn;
- tên người thụ hưởng;
- số tài khoản hoặc định danh người nhận đã che một phần;
- ngân hàng/đơn vị nhận;
- số tiền và mã tiền tệ;
- phí và tổng số tiền bị ghi nợ nếu có;
- thời điểm thực hiện hoặc lịch thanh toán;
- nội dung chuyển khoản nếu ảnh hưởng quyết định;
- mã giao dịch hoặc tham chiếu dễ đối chiếu.

Với hành động khác, chọn các thuộc tính tương ứng:

| Hành động | Thuộc tính quan trọng cần xác nhận |
| --- | --- |
| Thêm người thụ hưởng | Tên, định danh tài khoản, ngân hàng và phạm vi sử dụng. |
| Đổi email khôi phục | Email mới đã che một phần, account bị tác động và hệ quả bảo mật. |
| Cấp quyền quản trị | Người nhận quyền, vai trò, tenant, tài nguyên và thời hạn. |
| Ký hợp đồng | Tên tài liệu, phiên bản/hash, bên liên quan và ý nghĩa chấp thuận. |
| Phát hành API key | Tên key, scope, audience, thời hạn và dịch vụ có thể dùng key. |
| Xóa dữ liệu | Đối tượng, phạm vi, số lượng và khả năng khôi phục. |

Không cần hiển thị mọi trường kỹ thuật. Hãy hiển thị các thuộc tính quan trọng đối với quyết định của người dùng và bảo đảm chúng tương ứng với dữ liệu server sẽ thực thi.

## 5. Transaction snapshot: đóng băng nội dung được xác nhận

Khi người dùng bắt đầu xác nhận, server cần tạo một **transaction snapshot** hoặc biểu diễn chuẩn của nội dung giao dịch. Snapshot ghi lại các thuộc tính quan trọng tại thời điểm xác nhận bắt đầu.

Ví dụ cấu trúc khái niệm:

~~~json
{
  "transactionId": "txn-2026-00042",
  "transactionType": "TRANSFER",
  "sourceAccount": "account-•••2184",
  "beneficiaryId": "beneficiary-991",
  "beneficiaryName": "An Nguyen",
  "destinationAccount": "••••••4821",
  "destinationBank": "Example Bank",
  "amountMinor": 500000000,
  "currency": "VND",
  "feeMinor": 0,
  "executionDate": "2026-11-22",
  "version": 3,
  "status": "PENDING_CONFIRMATION"
}
~~~

Ví dụ dùng đơn vị tiền nhỏ nhất (minor unit) để tránh sai số số thực; cách biểu diễn cần theo quy tắc của từng currency. Đây là dữ liệu minh họa, không phải schema bắt buộc.

Snapshot nên:
- do server tạo từ dữ liệu đã được xác thực và kiểm tra;
- có transaction ID và version;
- chứa đầy đủ các trường ảnh hưởng đến quyết định;
- không cho client tùy ý ghi đè sau khi phát hành challenge;
- có thời hạn và trạng thái rõ ràng;
- được lưu bền vững hoặc bảo vệ bằng cơ chế integrity phù hợp;
- được dùng làm nguồn dữ liệu duy nhất khi thực thi.

Nếu người dùng sửa số tiền hoặc người nhận, server tạo version/snapshot mới và yêu cầu xác nhận lại. Không giữ bằng chứng xác nhận cũ rồi áp dụng lên nội dung mới.

## 6. Dynamic linking: ràng buộc xác nhận với đúng giao dịch

**Dynamic linking** là nguyên tắc gắn bằng chứng xác nhận với các thuộc tính cụ thể của giao dịch, chẳng hạn số tiền và người nhận. Mục đích là nếu các thuộc tính đó thay đổi, bằng chứng cũ không còn xác nhận được giao dịch mới.

Một cách mô hình hóa là tạo canonical transaction payload rồi tính digest:

~~~text
canonicalTransaction =
  version
  + transactionId
  + transactionType
  + sourceAccountId
  + beneficiaryId
  + amountMinor
  + currency
  + feeMinor
  + executionDate
  + relevantTerms

transactionDigest = SHA-256(canonicalTransaction)
~~~

Challenge xác nhận có thể ràng buộc với transaction ID, version, digest, account, purpose, nonce và expiry. Khi server nhận proof, nó xác minh rằng proof được tạo cho đúng digest đang lưu.

Các lưu ý:
- Canonicalization phải được đặc tả theo byte, không dựa vào chuỗi JSON serialize tùy tiện.
- Thứ tự trường, encoding, đơn vị tiền và giá trị rỗng phải nhất quán.
- Không chỉ ký transaction ID nếu nội dung có thể thay đổi mà ID không đổi.
- Không chỉ ký số tiền nếu người nhận hoặc tài khoản nguồn cũng quan trọng.
- Nếu phí, tỷ giá, lịch thực hiện hoặc điều khoản thay đổi quyết định của người dùng, chúng cũng cần được ràng buộc.
- Bất kỳ thay đổi nào tới trường thuộc snapshot đều phải làm proof cũ mất hiệu lực.

~~~mermaid
flowchart TD
    A["Tạo giao dịch"] --> B["Server xác thực và kiểm tra dữ liệu"]
    B --> C["Tạo snapshot + version"]
    C --> D["Tính transaction digest"]
    D --> E["Hiển thị chi tiết cho người dùng"]
    E --> F["Tạo challenge gắn digest và expiry"]
    F --> G["Người dùng xác nhận bằng phương thức được phép"]
    G --> H["Server xác minh proof + transaction state"]
    H --> I{"Snapshot/version còn đúng?"}
    I -- "Không" --> X["Hủy proof, yêu cầu xác nhận lại"]
    I -- "Có" --> J["Atomic transition sang APPROVED"]
    J --> K["Thực thi đúng snapshot đã duyệt"]
~~~

## 7. Trải nghiệm xác nhận phải hiển thị đúng nội dung

Giao diện xác nhận là một phần của security boundary. Người dùng chỉ có thể đưa ra quyết định có ý nghĩa nếu họ nhìn thấy thông tin quan trọng trước khi chấp thuận.

Một màn hình chuyển tiền nên trình bày rõ:

~~~text
Bạn đang xác nhận giao dịch

Từ:       Tài khoản thanh toán ••••2184
Đến:      An Nguyen
Ngân hàng: Example Bank
Tài khoản: ••••4821
Số tiền:  5.000.000 VND
Phí:      0 VND
Thực hiện: Ngay sau khi xác nhận

[Quay lại chỉnh sửa]       [Xác nhận chuyển tiền]
~~~

Các nguyên tắc UX:
- Dùng nhãn rõ ràng, tránh nút “OK” hoặc “Continue” cho hành động nhạy cảm.
- Hiển thị tên người nhận và số tài khoản đủ để người dùng phân biệt.
- Định dạng số tiền và currency không gây nhầm lẫn.
- Hiển thị phí/tổng tiền nếu có.
- Làm nổi bật các thay đổi so với lần trước.
- Cho phép quay lại chỉnh sửa; chỉnh sửa phải tạo snapshot/challenge mới.
- Không đặt nội dung quan trọng ngoài vùng người dùng nhìn thấy hoặc chỉ trong tooltip.
- Hỗ trợ accessibility và thiết bị màn hình nhỏ.
- Không gây áp lực bằng countdown giả hoặc thông điệp đe dọa.

**Màn hình trên browser không tự động là trusted display.** Nếu malware kiểm soát browser hoặc hệ điều hành, nội dung có thể bị thay trước khi hiển thị. Với giao dịch rủi ro cao, cân nhắc thiết bị/ứng dụng xác nhận độc lập có khả năng hiển thị nội dung được ràng buộc bằng mật mã.

## 8. Phương thức xác nhận giao dịch

Phương thức được chọn phụ thuộc mức rủi ro, thiết bị, khả năng truy cập và yêu cầu assurance.

| Phương thức | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Password/PIN step-up | Dễ triển khai và quen thuộc | Có thể bị phishing, keylogging hoặc tái sử dụng; không tự gắn với giao dịch. |
| TOTP/SMS OTP | Có thể bổ sung yếu tố possession theo mô hình | Mã có thể bị relay/phishing; mã chung chung không tự ràng buộc amount/payee. |
| Push approval | UX thuận tiện, có thể dùng thiết bị thứ hai | Push fatigue, approve nhầm, notification không hiển thị đủ nội dung. |
| Number matching | Giảm một số kiểu approve mù bằng cách yêu cầu đối chiếu mã | Không tự bảo đảm mã được ràng buộc với mọi thuộc tính giao dịch. |
| Passkey/WebAuthn | Chống phishing theo RP ID/origin và dùng public-key credential | Assertion mặc định không bảo đảm authenticator hiển thị amount/payee cho người dùng. |
| Chữ ký giao dịch bằng khóa riêng | Có thể ký digest giao dịch cụ thể | Cần bảo vệ khóa, canonicalization và giao diện hiển thị đáng tin cậy. |
| Device certificate/mTLS | Có thể chứng minh workload/thiết bị kiểm soát khóa | Không tự chứng minh người dùng đã đọc và chấp thuận giao dịch. |

Không có phương thức nào tự động an toàn cho mọi trường hợp. Cần xem phương thức có độc lập với session đang dùng không, có chống phishing không, proof có gắn nội dung không và người dùng có hiểu điều họ ký hay không.

## 9. Passkey/WebAuthn có xác nhận nội dung giao dịch không?

Passkey/WebAuthn là phương thức xác thực chống phishing mạnh khi triển khai đúng. RP tạo challenge và xác minh assertion theo RP ID/origin. Tuy nhiên, WebAuthn thông thường xác minh quyền kiểm soát credential và user verification theo authenticator; nó **không mặc định hiển thị số tiền, người nhận hoặc nội dung giao dịch trên màn hình đáng tin cậy của authenticator**.

RP có thể ràng buộc challenge với transaction digest và lưu quan hệ challenge → transaction ở server. Như vậy, assertion chỉ có thể hoàn tất giao dịch đang chờ tương ứng nếu server kiểm tra đúng binding. Nhưng điều đó chưa tự chứng minh người dùng đã nhìn thấy hoặc hiểu các chi tiết giao dịch nếu màn hình browser bị thay đổi.

Với giao dịch cần transaction signing mạnh:
- dùng thiết bị/app xác nhận có trusted display hoặc kênh độc lập phù hợp;
- hiển thị chính xác amount/payee/terms trên thiết bị xác nhận;
- ký challenge/digest được tạo từ snapshot;
- xác minh chữ ký và trạng thái transaction ở server;
- không cho client thay dữ liệu sau khi proof được tạo.

Không tự mô tả một WebAuthn assertion thông thường là “người dùng đã ký số số tiền và người nhận” nếu giao thức chỉ chứng minh assertion cho challenge và không có trusted display/transaction semantics tương ứng.

## 10. OTP và push approval: chống phishing và approve mù

### OTP

OTP thường chứng minh người dùng có thể truy cập một kênh hoặc authenticator tạo mã. Nếu OTP chỉ được nhập vào một trang web, attacker có thể relay mã theo thời gian thực. OTP không tự ràng buộc với giao dịch cụ thể trừ khi protocol thiết kế rõ binding đó.

Nếu dùng OTP cho transaction confirmation:
- yêu cầu mã ngắn hạn, một lần và rate limit;
- ràng buộc challenge với transaction ID/version/digest;
- không chấp nhận cùng mã cho giao dịch khác;
- không log OTP;
- hiển thị nội dung giao dịch trước khi nhập;
- cân nhắc rủi ro phishing và phương thức chống phishing mạnh hơn cho giao dịch giá trị cao.

### Push approval

Push notification nên hiển thị đủ thông tin để người dùng nhận biết yêu cầu. Không gửi push liên tục và hy vọng người dùng bấm đúng. Dùng rate limit, cooldown, hiển thị nguồn đăng nhập, amount/payee, number matching hoặc challenge rõ ràng nếu phù hợp. Từ chối nhiều request không rõ nguồn và cảnh báo khi có push ngoài ý muốn.

Number matching giúp giảm approve mù nhưng vẫn cần ràng buộc server-side với đúng transaction snapshot. Một mã số chỉ giúp chọn đúng request trên màn hình; nếu transaction payload có thể đổi sau đó, vẫn có transaction substitution.

## 11. Challenge phải ngẫu nhiên, ngắn hạn và dùng một lần

Challenge là một phần của bằng chứng xác nhận. Server cần tạo challenge mới cho từng giao dịch hoặc lần xác nhận, đủ ngẫu nhiên và gắn với transaction snapshot.

Challenge record có thể chứa:
- challenge ID opaque;
- transaction ID và version;
- transaction digest;
- account/principal;
- purpose cụ thể như `CONFIRM_TRANSFER`;
- phương thức xác nhận được chấp nhận;
- thời điểm tạo và expiry;
- trạng thái pending/consumed/revoked.

Challenge không nên:
- dùng chung cho nhiều giao dịch;
- có thể đoán từ timestamp hoặc transaction ID;
- sống vô hạn;
- được chấp nhận sau khi transaction đã thay đổi;
- được dùng lại sau khi xác nhận hoặc từ chối;
- chỉ gắn với account mà không gắn transaction digest.

Nếu challenge hết hạn, giao dịch cần được tạo challenge mới và người dùng phải xem lại nội dung hiện hành. Không gia hạn challenge cũ trong im lặng nếu nội dung hoặc trạng thái có thể đã thay đổi.

## 12. Trạng thái giao dịch và chuyển trạng thái nguyên tử

Transaction confirmation cần một state machine rõ ràng. Ví dụ:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_CONFIRMATION: submit
    PENDING_CONFIRMATION --> APPROVED: valid proof + atomic check
    PENDING_CONFIRMATION --> REJECTED: user declines
    PENDING_CONFIRMATION --> EXPIRED: deadline passed
    PENDING_CONFIRMATION --> CANCELLED: user/system cancels
    PENDING_CONFIRMATION --> SUPERSEDED: transaction edited
    APPROVED --> EXECUTING: execution worker claims
    EXECUTING --> SUCCEEDED: commit
    EXECUTING --> FAILED: execution error
    APPROVED --> CANCELLED: allowed only before execution claim
    SUCCEEDED --> [*]
    FAILED --> [*]
    REJECTED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    SUPERSEDED --> [*]
~~~

Một proof hợp lệ không nên chuyển một giao dịch đã cancelled, expired, superseded hoặc executed sang approved. Server cần kiểm tra và chuyển trạng thái bằng thao tác nguyên tử, ví dụ compare-and-set hoặc transaction database.

Các quy tắc quan trọng:
- Chỉ một request được chuyển PENDING_CONFIRMATION → APPROVED.
- Challenge chỉ được consume một lần.
- Transaction version/digest phải còn khớp.
- Nếu giao dịch bị sửa, challenge và proof cũ bị vô hiệu.
- Nếu hai xác nhận đồng thời tới, chỉ một xác nhận thắng.
- Execution worker chỉ nhận giao dịch ở trạng thái phù hợp.
- Kết quả thực thi phải được lưu để retry không gây side effect trùng.

## 13. Ngăn TOCTOU và transaction substitution

**Time-of-check to time-of-use (TOCTOU)** xảy ra khi dữ liệu được kiểm tra ở một thời điểm nhưng thay đổi trước lúc dùng. Trong transaction confirmation, lỗi này có thể khiến người dùng xác nhận một nội dung nhưng server thực hiện nội dung khác.

Ví dụ lỗi:
1. Server hiển thị 5.000.000 VND tới An.
2. Người dùng xác nhận.
3. Một request khác đổi beneficiary sang Bình hoặc amount thành 50.000.000 VND.
4. Execution service đọc dữ liệu mới nhất thay vì snapshot đã xác nhận.
5. Giao dịch mới được thực hiện bằng proof cũ.

Phòng vệ:
- Snapshot và version được tạo ở server.
- Challenge gắn digest của toàn bộ thuộc tính quan trọng.
- Khi xác nhận, server kiểm tra version/digest còn khớp.
- Approval lưu digest/version đã duyệt.
- Execution chỉ đọc snapshot đã duyệt hoặc kiểm tra digest/version trước commit.
- Không cho service downstream tự dựng lại giao dịch từ request mutable.
- Thay đổi bất kỳ trường quan trọng nào phải tạo transaction version mới và yêu cầu xác nhận lại.

## 14. Idempotency và xử lý retry

Client có thể mất kết nối sau khi server đã nhận xác nhận hoặc đã thực hiện giao dịch. Nếu client retry, hệ thống không được tạo giao dịch hoặc side effect lần hai.

Phân biệt:
- **Challenge one-time use:** ngăn dùng lại bằng chứng xác nhận.
- **Idempotency key:** nhận diện cùng một yêu cầu nghiệp vụ khi client retry.
- **Transaction ID:** định danh giao dịch.
- **Transaction version:** định danh phiên bản nội dung đã được xác nhận.

Ví dụ:
- Lần đầu: transaction T, version 3, proof C1 được xác minh; server chuyển sang APPROVED rồi thực hiện.
- Response bị mất.
- Client retry với cùng idempotency key hoặc transaction reference.
- Server trả trạng thái/kết quả đã lưu, không thực hiện chuyển tiền lần nữa.

Không mở lại challenge đã consume chỉ để retry. Nếu người dùng phải xác nhận lại vì challenge hết hạn hoặc nội dung đổi, tạo challenge mới gắn snapshot/version mới. Cần xử lý trường hợp kết quả thực thi không rõ do downstream timeout bằng trạng thái reconciliation, không gửi side effect mù.

## 15. API và ranh giới giữa client với server

Một API minh họa:

~~~http
POST /transactions
Authorization: Bearer <authenticated-session>
Idempotency-Key: order-2026-0042
Content-Type: application/json

{
  "beneficiaryId": "beneficiary-991",
  "amountMinor": 500000000,
  "currency": "VND"
}
~~~

Server kiểm tra quyền và dữ liệu, sau đó trả về transaction ID và nội dung đã chuẩn hóa:

~~~json
{
  "transactionId": "txn-2026-00042",
  "version": 3,
  "status": "PENDING_CONFIRMATION",
  "display": {
    "beneficiaryName": "An Nguyen",
    "destinationAccountMasked": "••••4821",
    "amount": "5.000.000 VND",
    "fee": "0 VND"
  },
  "confirmationRequired": true
}
~~~

Sau đó client yêu cầu challenge:

~~~http
POST /transactions/txn-2026-00042/confirmation-challenge
Authorization: Bearer <authenticated-session>
Content-Type: application/json

{
  "version": 3,
  "method": "WEBAUTHN"
}
~~~

Server tự lấy snapshot version 3 từ database, tạo challenge và lưu digest. Client không được gửi digest tùy ý để server ký hoặc tin.

Sau khi người dùng xác nhận:

~~~http
POST /transactions/txn-2026-00042/confirm
Authorization: Bearer <authenticated-session>
Content-Type: application/json

{
  "challengeId": "challenge-opaque-81",
  "proof": "<verified-authenticator-response>"
}
~~~

Server kiểm tra:
- session/principal còn active;
- account sở hữu giao dịch;
- transaction đang pending và version đúng;
- challenge đúng transaction, purpose, digest, method và expiry;
- proof hợp lệ theo protocol;
- challenge chưa consume;
- authorization vẫn hợp lệ;
- transition sang approved được thực hiện nguyên tử.

Client không được tự gửi `approved=true`, `mfaPassed=true` hoặc transaction digest do nó tự tính rồi yêu cầu server thực thi.

## 16. Pseudocode xác nhận và thực thi

Ví dụ Java minh họa:

~~~java
ConfirmationResult confirm(
        String transactionId,
        String challengeId,
        AuthenticatedPrincipal principal,
        ConfirmationProof proof) {

    PendingChallenge challenge =
        challengeStore.requireActive(challengeId);

    TransactionSnapshot snapshot =
        transactionStore.loadCurrentSnapshot(transactionId);

    policy.requireOwner(principal, snapshot);
    policy.requirePurpose(challenge, "TRANSACTION_CONFIRMATION");
    policy.requireSameTransaction(challenge, snapshot.id());
    policy.requireSameVersion(challenge, snapshot.version());
    policy.requireSameDigest(challenge, digest(snapshot));
    policy.requireNotExpired(challenge, clock.instant());

    proofVerifier.verify(
        proof,
        challenge,
        principal,
        snapshot);

    // Atomic compare-and-set: chỉ một request có thể approve.
    boolean approved = transactionStore.approveAtomically(
        snapshot.id(),
        snapshot.version(),
        challenge.id(),
        challenge.digest(),
        principal.accountId());

    if (!approved) {
        throw transactionNoLongerConfirmable();
    }

    challengeStore.consumeAtomically(challenge.id());

    return ConfirmationResult.approved(snapshot.id(), snapshot.version());
}
~~~

Đây là pseudocode để giải thích trách nhiệm. Trong production, việc consume challenge và đổi transaction state cần cùng một transaction hoặc một workflow có tính nhất quán rõ ràng. Nếu hai store khác nhau, phải thiết kế failure recovery để không có trạng thái “challenge đã consume nhưng transaction chưa approved” hoặc ngược lại mà không thể reconciliation.

Execution worker:

~~~java
ExecutionResult executeApproved(String transactionId) {
    return transactionStore.withLock(transactionId, tx -> {
        if (tx.status() == Status.SUCCEEDED) {
            return tx.savedResult(); // idempotent retry
        }
        if (tx.status() != Status.APPROVED) {
            throw notExecutable();
        }

        tx.requireApprovedVersionAndDigest();
        tx.markExecuting();

        ExecutionResult result =
            paymentRail.executeOnce(tx.immutableApprovedSnapshot());

        tx.storeResultAndMarkFinal(result);
        return result;
    });
}
~~~

Pseudocode không thay thế transaction boundary, outbox, reconciliation hoặc idempotency contract của payment rail. Với hệ thống phân tán, cần thiết kế rõ điều gì xảy ra khi downstream đã thực hiện nhưng response bị timeout.

## 17. Thay đổi giao dịch sau khi xác nhận

Một giao dịch có thể thay đổi vì người dùng chỉnh sửa, phí thay đổi, tỷ giá thay đổi, người nhận bị cập nhật hoặc policy yêu cầu thêm thông tin.

Quy tắc:
- Nếu thay đổi thuộc tính được xác nhận, tăng version.
- Đánh dấu snapshot cũ là superseded.
- Thu hồi challenge đang pending của version cũ.
- Hiển thị lại toàn bộ thuộc tính liên quan.
- Yêu cầu người dùng xác nhận lại.
- Không mang proof cũ sang version mới.

Với giao dịch có phí/tỷ giá biến động, cần quy định rõ:
- phí/tỷ giá được khóa ở thời điểm tạo hay có thể thay đổi;
- ngưỡng thay đổi nào cần xác nhận lại;
- tổng số tiền cuối cùng được hiển thị ra sao;
- thời hạn quote;
- cách xử lý khi quote hết hạn.

Nếu hệ thống không thể bảo đảm nội dung đã xác nhận còn đúng tại lúc thực thi, cần hủy hoặc yêu cầu xác nhận lại.

## 18. Hủy, từ chối, timeout và recovery

Người dùng phải có lựa chọn rõ ràng để từ chối hoặc hủy. Không coi việc không phản hồi là chấp thuận.

- **Decline:** người dùng chủ động từ chối; transaction chuyển sang REJECTED.
- **Cancel:** người dùng hoặc hệ thống hủy trước khi thực thi; transaction chuyển sang CANCELLED nếu trạng thái cho phép.
- **Expire:** hết thời hạn; challenge và giao dịch pending không còn được chấp nhận.
- **Supersede:** nội dung thay đổi; version cũ không thể được xác nhận.
- **Recovery:** người dùng mất authenticator; cần quy trình phục hồi danh tính/credential theo assurance phù hợp trước khi xác nhận giao dịch mới.

Không cho support staff đánh dấu giao dịch là approved chỉ vì người dùng gọi điện hoặc gửi email. Quy trình recovery phải xác minh account và cấp lại credential; nó không được biến thành đường vòng bỏ qua xác nhận giao dịch.

Với giao dịch đang ở trạng thái EXECUTING, cancel có thể không còn khả thi. UI cần phân biệt “đã gửi xử lý”, “đang đối soát” và “đã hoàn tất”, tránh hứa hủy khi side effect không thể đảo ngược.

## 19. Audit và bằng chứng xác nhận

Audit record nên cho phép trả lời:
- Ai đã khởi tạo giao dịch?
- Account/principal nào đã xác nhận?
- Người dùng được hiển thị snapshot/version nào?
- Các thuộc tính quan trọng và digest nào được xác nhận?
- Phương thức xác nhận và assurance context là gì?
- Challenge được tạo, hết hạn và consume lúc nào?
- Ai hoặc service nào thực thi?
- Kết quả cuối cùng và mã tham chiếu downstream là gì?

Có thể lưu:
- transaction ID/version;
- account ID và tenant đã xác minh;
- snapshot reference hoặc canonical digest;
- thời điểm hiển thị/confirm theo mức có thể tin cậy;
- method và verifier result;
- challenge ID opaque và trạng thái;
- approval actor và execution service;
- idempotency key reference;
- reason code, request/correlation ID và kết quả.

Không log password, OTP, private key, raw session cookie, raw access token hoặc toàn bộ dữ liệu nhạy cảm không cần thiết. Digest không thay thế việc bảo vệ snapshot; cần giữ snapshot hoặc dữ liệu đủ để điều tra theo retention policy.

## 20. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Chỉ yêu cầu đăng nhập lại, không hiển thị giao dịch | Người dùng không biết mình đang chấp thuận điều gì | Hiển thị transaction details rõ ràng. |
| OTP chung cho mọi hành động | OTP có thể bị relay sang giao dịch khác | Ràng buộc challenge với transaction ID/version/digest. |
| Chỉ ký transaction ID | Nội dung có thể đổi trong khi ID giữ nguyên | Ký/ràng buộc digest của các trường quan trọng. |
| Hiển thị một người nhận nhưng thực thi người khác | Transaction substitution | Snapshot bất biến và execution dùng đúng snapshot. |
| Thay amount sau confirmation | Proof cũ áp dụng cho dữ liệu mới | Version/digest check, yêu cầu xác nhận lại. |
| Tin `approved=true` từ client | Client giả trạng thái chấp thuận | Server xác minh proof và transaction state. |
| WebAuthn được mô tả là trusted transaction display | Người dùng có thể không thấy nội dung được ký | Phân biệt challenge binding với trusted display. |
| Push approve không có ngữ cảnh | Push fatigue và approve nhầm | Hiển thị chi tiết, number matching, rate limit. |
| Challenge không hết hạn hoặc dùng lại | Replay | Nonce ngẫu nhiên, expiry và one-time consume. |
| Hai request approve đồng thời | Giao dịch được xử lý hai lần | Atomic state transition và idempotency. |
| Execution đọc mutable request | TOCTOU | Chỉ thực thi immutable approved snapshot. |
| Retry tạo side effect mới | Thanh toán/giao dịch trùng | Idempotency key và kết quả lưu bền vững. |
| Phí/tỷ giá thay đổi không yêu cầu xác nhận lại | Người dùng chấp thuận số tiền khác | Snapshot quote, version và policy thay đổi. |
| Recovery yếu | Attacker bỏ qua transaction confirmation | Recovery assurance tương xứng và audit. |
| Log chứa OTP/proof/token | Lộ bằng chứng xác nhận | Redaction, secret handling và retention. |

## 21. Kiểm thử transaction confirmation

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Người dùng xác nhận snapshot hiện hành bằng proof hợp lệ | Chuyển APPROVED đúng một lần. |
| Proof có chữ ký đúng nhưng transaction ID khác | Từ chối. |
| Proof gắn version cũ | Từ chối và yêu cầu xác nhận lại. |
| Amount thay đổi sau khi challenge tạo | Digest/version mismatch; từ chối. |
| Beneficiary thay đổi sau khi người dùng xem | Proof cũ không còn hiệu lực. |
| Currency hoặc source account thay đổi | Yêu cầu xác nhận mới. |
| Phí/tỷ giá thay đổi vượt policy | Supersede snapshot và xác nhận lại. |
| Challenge hết hạn | Từ chối. |
| Challenge đã consume được gửi lại | Từ chối replay. |
| Hai confirm request tới đồng thời | Chỉ một request approve thành công. |
| Người dùng từ chối | Transaction thành REJECTED; không thực thi. |
| Transaction đã cancelled | Không thể approve bằng proof cũ. |
| Transaction đã succeeded | Retry trả kết quả đã lưu; không thực thi lần hai. |
| Client gửi `approved=true` | Bị bỏ qua; server cần proof hợp lệ. |
| WebAuthn assertion hợp lệ cho challenge khác | Từ chối do challenge/transaction binding. |
| Push approval không khớp transaction | Từ chối. |
| OTP đúng nhưng thuộc giao dịch khác | Từ chối. |
| User session đã revoke | Từ chối xác nhận. |
| Account hoặc beneficiary bị khóa trước commit | Áp dụng policy mới; không thực thi nếu không còn hợp lệ. |
| Authorization bị thu hồi giữa confirm và execution | Execution kiểm tra lại điều kiện bắt buộc theo policy. |
| Downstream timeout sau khi có thể đã thực hiện | Reconcile theo idempotency reference; không gửi side effect mù. |
| Replay từ tenant khác | Từ chối do principal/tenant binding. |
| Audit thiếu snapshot/version/digest | Test vận hành thất bại; không đủ bằng chứng điều tra. |

### Kiểm thử race và TOCTOU

Chạy đồng thời:
- hai request xác nhận cùng challenge;
- một request xác nhận và một request chỉnh sửa transaction;
- một request xác nhận và một request hủy;
- logout/revoke session trong khi confirmation đang chờ;
- worker thực thi cùng lúc với retry;
- update beneficiary trong lúc transaction đang pending.

Kiểm tra database và downstream side effect, không chỉ HTTP status. Mỗi giao dịch chỉ được thực thi tối đa một lần và chỉ theo snapshot đã được chấp thuận.

## 22. Bài tập tình huống

Một ứng dụng cho phép người dùng chuyển tiền. UI hiển thị 2.000.000 VND tới tài khoản của An. Người dùng nhập OTP nhận qua SMS. Backend chỉ xác minh OTP rồi lấy dữ liệu giao dịch mới nhất từ database để thực thi. Một request khác có thể thay beneficiary trước lúc worker xử lý. Khi người dùng không nhận được response, client gửi lại request confirm.

**Yêu cầu phân tích:**

1. Vì sao OTP đúng chưa chứng minh người dùng đã chấp thuận đúng người nhận và số tiền?
2. Những trường nào phải nằm trong transaction snapshot?
3. Làm sao ràng buộc challenge với amount, currency, source và beneficiary?
4. Nếu beneficiary thay đổi sau khi hiển thị, điều gì phải xảy ra?
5. Làm sao ngăn hai request confirm đồng thời?
6. Retry sau timeout cần dùng idempotency như thế nào?
7. Worker phải đọc dữ liệu nào để thực thi?

**Hướng phân tích:** OTP cần gắn với transaction challenge và vẫn có giới hạn chống phishing/relay. Server tạo snapshot bất biến, version và digest của các trường quan trọng; challenge gắn digest và expiry. Thay đổi beneficiary tạo version mới và vô hiệu proof cũ. Atomic compare-and-set chỉ cho một request approve. Retry dùng transaction/idempotency reference và trả kết quả đã lưu. Worker thực thi immutable approved snapshot, không đọc request mutable mới nhất.

## 23. Checklist review

- [ ] Phân biệt authentication, step-up, transaction confirmation, authorization và execution.
- [ ] Người dùng được hiển thị đầy đủ thuộc tính quan trọng trước khi xác nhận.
- [ ] Transaction snapshot do server tạo, có ID/version và trạng thái rõ.
- [ ] Challenge gắn với transaction ID, version, digest, principal, purpose và expiry.
- [ ] Canonicalization và đơn vị tiền được định nghĩa chính xác.
- [ ] Thay đổi thuộc tính quan trọng làm proof cũ mất hiệu lực.
- [ ] Proof được xác minh theo phương thức và policy đã cấu hình.
- [ ] Không tin boolean hoặc digest do client tự khai.
- [ ] WebAuthn challenge binding không bị mô tả nhầm thành trusted transaction display.
- [ ] OTP/push có chống replay, rate limit và giảm approve mù/phishing.
- [ ] Challenge chỉ được consume một lần.
- [ ] Transaction state transition được thực hiện nguyên tử.
- [ ] Execution chỉ dùng snapshot/version/digest đã approved.
- [ ] Idempotency ngăn side effect trùng khi retry.
- [ ] Cancel, decline, expiry và supersede có semantics rõ.
- [ ] Authorization và trạng thái account/beneficiary được kiểm tra theo policy.
- [ ] Audit giữ đủ bằng chứng về nội dung đã xác nhận và kết quả thực thi.
- [ ] Log không chứa OTP, secret, token hoặc raw proof.
- [ ] Có test race, TOCTOU, replay, parameter tampering và downstream timeout.

## 24. Ghi nhớ

**Transaction confirmation phải chứng minh người dùng đã chấp thuận đúng nội dung giao dịch mà hệ thống sẽ thực hiện.** Để đạt điều đó, server tạo snapshot bất biến, hiển thị các thuộc tính quan trọng, ràng buộc challenge/proof với version và digest, kiểm tra trạng thái nguyên tử và thực thi đúng snapshot đã được duyệt. Đăng nhập mạnh hoặc OTP hợp lệ không tự bảo đảm nội dung giao dịch không bị thay đổi.

Khi review, hãy hỏi: **Người dùng đã nhìn thấy chính xác điều gì? Bằng chứng được ràng buộc với amount, payee và các điều khoản nào? Nếu dữ liệu thay đổi sau xác nhận thì proof cũ có bị vô hiệu không? Hai request đồng thời có thể approve hoặc thực thi hai lần không? Retry sau timeout có an toàn không? Bằng chứng audit có cho biết giao dịch nào thực sự được chấp thuận không?**
