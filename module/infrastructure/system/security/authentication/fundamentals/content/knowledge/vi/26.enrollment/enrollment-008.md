# Thu hồi enrollment

## 1. Thu hồi enrollment là gì?

**Thu hồi enrollment (enrollment revocation)** là việc chấm dứt hiệu lực của một credential, authenticator hoặc phương thức xác thực đã được đăng ký với tài khoản. Sau khi thu hồi, hệ thống không còn chấp nhận credential đó để xác thực, dù người dùng hoặc thiết bị vẫn giữ bản sao vật lý của nó.

Ví dụ: nhân viên làm mất điện thoại có passkey và ứng dụng TOTP đã đăng ký với cổng công ty. Quản trị viên hoặc người dùng xác minh qua một kênh dự phòng rồi yêu cầu thu hồi hai enrollment trên thiết bị bị mất. Hệ thống đánh dấu credential tương ứng không còn hiệu lực, ngăn đăng nhập mới bằng chúng và đánh giá các session/token đã được cấp trước đó.

Thu hồi là một phần của vòng đời credential: đăng ký, kích hoạt, sử dụng, tạm khóa, thu hồi và thay thế. Nó đặc biệt quan trọng khi thiết bị mất, credential bị lộ, nhân viên rời tổ chức, phương thức xác thực không còn được hỗ trợ hoặc người dùng không còn kiểm soát authenticator.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, thu hồi enrollment nối việc quản lý credential với phòng chống chiếm tài khoản: hệ thống phải biết credential nào được tin cậy, ai có quyền thu hồi, trạng thái được lan truyền ra sao và những session/token nào cần xử lý tiếp.

## 2. Phân biệt thu hồi enrollment với các thao tác gần giống

Các thao tác sau có liên quan nhưng không đồng nghĩa:

| Thao tác | Điều gì bị vô hiệu hóa? | Ví dụ |
| --- | --- | --- |
| **Revoke enrollment/credential** | Một authenticator hoặc phương thức xác thực đã đăng ký. | Thu hồi passkey trên laptop bị mất. |
| **Disable account** | Khả năng sử dụng tài khoản nói chung theo chính sách. | Tạm khóa tài khoản khi có điều tra gian lận. |
| **Revoke session** | Một phiên đăng nhập đã được tạo. | Đăng xuất session trên trình duyệt bị mất. |
| **Revoke token/grant** | Token hoặc quyền ủy quyền đã cấp. | Thu hồi refresh token của ứng dụng bên thứ ba. |
| **Delete credential record** | Xóa dữ liệu lưu về credential. | Dọn dữ liệu theo chính sách lưu giữ sau thời gian cần thiết. |
| **Destroy authenticator key** | Xóa khóa khỏi thiết bị/authenticator. | Người dùng reset security key hoặc xóa passkey khỏi thiết bị. |

Thu hồi enrollment tại RP thường chỉ có nghĩa **RP ngừng tin credential đó**. Nó không nhất thiết xóa private key khỏi thiết bị, xóa passkey khỏi hệ sinh thái đồng bộ hoặc thu hồi chứng chỉ tại CA. Với passkey, ví dụ, RP có thể đánh dấu credential ID đã bị thu hồi; authenticator vẫn có thể giữ private key nhưng assertion mới sẽ bị RP từ chối.

Tương tự, xóa cookie ở trình duyệt không tự thu hồi credential đã đăng ký. Thu hồi credential không tự động chấm dứt mọi session/token đã được cấp trước đó. Cần xác định rõ từng lớp trạng thái.

## 3. Khi nào cần thu hồi enrollment?

Các tình huống thường gặp:

- **Mất hoặc bị đánh cắp thiết bị:** điện thoại, laptop, security key hoặc thiết bị có chứng chỉ client không còn thuộc quyền kiểm soát.
- **Nghi lộ credential:** secret TOTP, recovery code, API key hoặc private key có dấu hiệu bị sao chép.
- **Phishing hoặc chiếm tài khoản:** attacker đã thêm authenticator của họ vào tài khoản nạn nhân.
- **Thay đổi quan hệ công việc:** nhân viên nghỉ việc, nhà thầu hết hợp đồng hoặc thiết bị bị thu hồi khỏi hệ thống quản lý.
- **Thay thế phương thức:** người dùng chuyển sang passkey mới, security key mới hoặc phương thức mạnh hơn.
- **Lỗi enrollment:** credential được gắn nhầm tài khoản, sai tenant hoặc đăng ký trong một phiên không đủ tin cậy.
- **Vi phạm chính sách:** loại authenticator không còn được phép, chứng chỉ hết hạn hoặc thuật toán bị loại bỏ.
- **Yêu cầu của người dùng:** người dùng chủ động xóa phương thức xác thực không còn sử dụng.

Không phải mọi trường hợp đều cần xóa toàn bộ enrollment. Nếu chỉ một security key bị mất, có thể thu hồi đúng credential đó và giữ các phương thức độc lập khác. Nếu có bằng chứng tài khoản bị chiếm, cần mở rộng phạm vi sang session, token, recovery method và các enrollment vừa được thêm.

## 4. Vòng đời và trạng thái enrollment

Một enrollment nên có trạng thái rõ ràng, được kiểm tra ở mọi lần xác thực:

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Bắt đầu đăng ký
    Pending --> Active: Xác minh và hoàn tất enrollment
    Pending --> Expired: Hết hạn hoặc bị hủy
    Active --> Suspended: Tạm ngưng để rà soát
    Suspended --> Active: Xác minh lại và khôi phục
    Active --> Revoked: Người dùng/quản trị thu hồi
    Suspended --> Revoked: Xác nhận rủi ro
    Active --> Expired: Hết hạn theo policy
    Revoked --> [*]
    Expired --> [*]
~~~

Ý nghĩa:

- **Pending:** đang đăng ký; chưa được dùng để đăng nhập cho tới khi hoàn tất các bước xác minh.
- **Active:** credential đã được xác minh, gắn với đúng tài khoản và được phép sử dụng.
- **Suspended:** tạm thời không chấp nhận trong khi điều tra hoặc chờ xác minh bổ sung.
- **Revoked:** đã thu hồi; không được kích hoạt lại như credential cũ.
- **Expired:** hết hiệu lực theo thời hạn hoặc chính sách.

Khi người dùng đăng ký lại, hệ thống nên tạo enrollment/credential record mới. Không chuyển một record đã revoked trở lại Active chỉ để tiện vận hành, vì điều đó làm mờ lịch sử và có thể vô tình hồi sinh credential đã bị lộ.

## 5. Ai được phép thu hồi?

Thu hồi là thao tác bảo mật nhạy cảm. Người có quyền xóa authenticator có thể khóa chủ tài khoản khỏi hệ thống hoặc giúp attacker loại bỏ phương thức dự phòng của nạn nhân.

Các nguồn yêu cầu hợp lệ có thể gồm:

| Tác nhân | Điều kiện kiểm soát |
| --- | --- |
| Chủ tài khoản | Xác thực bằng phương thức còn tin cậy hoặc quy trình recovery đã được phê duyệt. |
| Quản trị viên tổ chức | Có quyền quản trị phù hợp, đúng tenant và có audit. |
| Security/incident response | Có quy trình ứng phó sự cố, phạm vi và phê duyệt theo mức độ ảnh hưởng. |
| Hệ thống policy | Tự động thu hồi khi credential hết hạn, bị cấm hoặc có bằng chứng rủi ro đủ mạnh. |
| Bộ phận hỗ trợ | Chỉ qua quy trình xác minh danh tính, phân quyền và kiểm soát ngoại lệ. |

Không nên cho một session mới đăng nhập bằng mật khẩu yếu tự xóa tất cả passkey và security key hiện có. Với thao tác xóa phương thức cuối cùng, thay đổi recovery hoặc tài khoản đặc quyền, có thể cần step-up, xác nhận ngoài băng, phê duyệt kép hoặc thời gian chờ có kiểm soát.

Nếu credential bị nghi chiếm dụng, người dùng có thể không còn khả năng dùng chính credential đó để xác thực lại. Hệ thống phải cung cấp một kênh thay thế được thiết kế trước, như security key dự phòng, recovery process hoặc xác minh hỗ trợ có bảo đảm tương xứng.

## 6. Dữ liệu enrollment cần quản lý

Một credential registry nên giữ đủ thông tin để xác định chính xác credential, chủ sở hữu, trạng thái và lịch sử thu hồi.

| Trường | Mục đích |
| --- | --- |
| `enrollmentId` | Định danh bản ghi enrollment trong hệ thống. |
| `credentialId` / `factorId` | Định danh credential hoặc yếu tố theo loại phương thức. |
| `principalId` / `tenantId` | Gắn credential với đúng tài khoản và tổ chức. |
| `factorType` | Passkey, TOTP, security key, certificate, API key hoặc phương thức khác. |
| `status` | Pending, active, suspended, revoked hoặc expired. |
| `createdAt` / `activatedAt` | Theo dõi thời điểm đăng ký và kích hoạt. |
| `lastUsedAt` | Hỗ trợ quản lý thiết bị và điều tra. |
| `revokedAt` / `revokedBy` | Thời điểm và tác nhân thu hồi. |
| `revocationReason` | Lý do theo danh mục, tránh ghi dữ liệu nhạy cảm không cần thiết. |
| `version` | Hỗ trợ cập nhật đồng thời và kiểm soát race condition. |

Không lưu private key của passkey hoặc secret TOTP ở dạng plaintext trong một bảng enrollment chung. Mỗi loại credential có yêu cầu lưu trữ riêng. Bản ghi registry chỉ chứa metadata cần thiết và tham chiếu tới kho bí mật chuyên dụng khi cần.

Giữ tombstone hoặc bản ghi trạng thái revoked trong thời gian cần thiết để ngăn credential cũ được đăng ký lại do restore backup, đồng bộ chậm hoặc lỗi cache. Xóa vật lý chỉ nên diễn ra theo chính sách lưu giữ và khi không còn cần dữ liệu để xác minh trạng thái, audit hoặc chống hồi sinh credential.

## 7. Thu hồi theo từng loại credential

### 7.1. Passkey và WebAuthn

Với passkey, RP thường lưu credential ID, public key, user handle, metadata và trạng thái. Khi thu hồi:

1. Đánh dấu enrollment/credential là revoked trong credential registry.
2. Mọi lần assertion tiếp theo phải kiểm tra trạng thái và từ chối credential đó.
3. Xóa liên kết credential với luồng chọn tài khoản nếu cần, nhưng giữ tombstone đủ lâu để nhận diện credential đã thu hồi.
4. Thu hồi session/token đáng ngờ được tạo từ credential hoặc trong khoảng thời gian nghi ngờ.
5. Thông báo cho chủ tài khoản qua kênh phù hợp.

RP không thể mặc nhiên xóa private key khỏi authenticator của người dùng từ xa. Người dùng có thể cần xóa passkey khỏi thiết bị hoặc hệ sinh thái đồng bộ. Việc đó là thao tác riêng; biện pháp quyết định là RP không còn chấp nhận public key credential đã bị thu hồi.

### 7.2. TOTP/HOTP và ứng dụng xác thực

Với TOTP/HOTP, server thường lưu secret chia sẻ hoặc dữ liệu được bảo vệ để kiểm tra mã. Khi thu hồi:

- Đánh dấu factor không hoạt động và ngừng chấp nhận mã được tạo từ secret đó.
- Xóa hoặc vô hiệu hóa secret theo chính sách lưu trữ; bảo đảm bản sao backup không làm secret sống lại.
- Thu hồi recovery code liên quan nếu chúng được phát hành cùng lần enrollment hoặc có nguy cơ bị lộ.
- Nếu người dùng đăng ký lại, tạo secret mới và yêu cầu xác minh mã trước khi kích hoạt.

Không tái sử dụng secret TOTP cũ cho enrollment mới. Mã TOTP còn trong cửa sổ thời gian không được chấp nhận sau khi factor đã revoked.

### 7.3. Security key và thiết bị phần cứng

Security key FIDO2 được quản lý tương tự passkey: RP thu hồi credential ID tương ứng. Nếu thiết bị chứa nhiều credential cho nhiều tài khoản/dịch vụ, thu hồi tại một RP không tự thu hồi credential ở các RP khác. Chủ thể cần kiểm tra từng tài khoản hoặc dùng quy trình quản trị tập trung nếu có.

Đối với thiết bị phần cứng do tổ chức quản lý, có thể kết hợp MDM/endpoint management để khóa hoặc xóa thiết bị theo chính sách. Hành động quản lý thiết bị không thay thế việc thu hồi credential ở từng dịch vụ.

### 7.4. Certificate và client certificate

Nếu enrollment gắn với chứng chỉ X.509 hoặc client certificate, thu hồi có thể liên quan tới:

- Đánh dấu certificate/serial number bị thu hồi tại CA.
- Phát hành CRL hoặc cung cấp trạng thái qua OCSP theo kiến trúc PKI.
- Cập nhật trust store hoặc danh sách certificate được phép ở service.
- Thu hồi mapping giữa certificate subject/SAN và principal nội bộ.
- Cấp certificate mới sau khi xác minh lại private key và danh tính.

Chỉ xóa certificate khỏi bảng ứng dụng chưa chắc đã khiến mọi verifier ngừng chấp nhận nó nếu họ chỉ kiểm tra chữ ký và chuỗi CA. Cần kiểm tra chính sách revocation ở TLS terminator, gateway và service phía sau.

### 7.5. API key và recovery code

Với API key, issuer nên đánh dấu key ID revoked và từ chối mọi request mới, kể cả khi MAC hoặc secret vẫn đúng. Với recovery code, đánh dấu code đã dùng hoặc thu hồi toàn bộ tập code khi có nghi ngờ lộ; cấp bộ code mới sau khi xác minh lại.

Nếu API key hoặc recovery code đã được dùng để tạo session/token, cần đánh giá và thu hồi các trạng thái downstream liên quan. Thu hồi nguồn credential không tự động làm mọi bản sao token biến mất.

## 8. Quy trình thu hồi an toàn

Một luồng self-service tham khảo:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Account service
    participant P as Policy / risk engine
    participant R as Credential registry
    participant S as Session / token service
    U->>A: Yêu cầu thu hồi enrollment
    A->>P: Xác minh quyền, step-up và rủi ro
    P-->>A: Cho phép hoặc yêu cầu recovery/review
    A->>R: Đánh dấu credential revoked (atomic)
    R-->>A: Trạng thái đã cập nhật
    A->>S: Thu hồi session/token liên quan theo policy
    A-->>U: Xác nhận và hướng dẫn enrollment thay thế
~~~

Các bước cần thực hiện:

1. **Xác định mục tiêu:** enrollment ID cụ thể, tài khoản, tenant và loại credential.
2. **Xác thực người yêu cầu:** kiểm tra session hiện tại, step-up hoặc quy trình hỗ trợ được phê duyệt.
3. **Đánh giá tác động:** đây có phải credential cuối cùng, factor duy nhất, phương thức recovery hay credential của tài khoản đặc quyền không?
4. **Ghi nhận yêu cầu:** tạo request ID, tác nhân, thời điểm và lý do theo danh mục.
5. **Thu hồi nguyên tử:** chuyển trạng thái Active sang Revoked với kiểm soát đồng thời.
6. **Lan truyền trạng thái:** cập nhật cache, gateway, verifier và các hệ thống liên quan.
7. **Xử lý session/token:** xác định session được tạo từ credential đó hoặc nằm trong khoảng nghi ngờ.
8. **Thông báo:** gửi xác nhận qua kênh đã xác minh; không đưa secret vào thông báo.
9. **Thay thế:** hướng dẫn đăng ký credential mới qua enrollment flow an toàn.
10. **Audit:** lưu sự kiện đủ để điều tra và tuân thủ, không lưu dữ liệu nhạy cảm không cần thiết.

## 9. Thu hồi session và token liên quan

Sau khi thu hồi enrollment, hệ thống phải quyết định trạng thái của session/token hiện hữu:

- Nếu chỉ thay một authenticator không có dấu hiệu bị lộ, có thể giữ session khác theo policy.
- Nếu thiết bị bị mất hoặc attacker có thể đã sử dụng credential, thu hồi session được tạo từ thiết bị/credential đó.
- Nếu tài khoản bị chiếm, xem xét thu hồi mọi session, refresh token và grant có thể bị ảnh hưởng.
- Với tài khoản đặc quyền, cân nhắc yêu cầu xác thực lại trên tất cả phiên hoặc khóa tạm thời trong khi điều tra.

Một số access token JWT tự chứa có thể tiếp tục hợp lệ tới `exp` nếu resource server chỉ kiểm tra chữ ký và claim tĩnh. Cần TTL ngắn, introspection, denylist, session version hoặc cơ chế thu hồi phù hợp nếu yêu cầu vô hiệu hóa nhanh.

Không nên giả định có thể xác định chính xác mọi token đã được tạo từ một credential nếu hệ thống không lưu quan hệ đó. Thiết kế session/token nên ghi lại principal, authentication event, credential/factor ID hoặc session assurance metadata ở mức cần thiết để hỗ trợ thu hồi có mục tiêu.

## 10. Phân tán trạng thái thu hồi và xử lý đồng thời

Trong hệ thống nhiều node, một verifier có thể vẫn chấp nhận credential nếu cache chưa nhận trạng thái revoked. Cần xác định thời gian lan truyền tối đa và kiểm soát những endpoint có yêu cầu thu hồi tức thời.

Các nguyên tắc:

- **Atomic state transition:** cập nhật trạng thái bằng điều kiện `status = active` hoặc version phù hợp để tránh hai thao tác ghi đè lẫn nhau.
- **Idempotency:** lặp lại cùng yêu cầu thu hồi phải cho kết quả nhất quán; không tạo side effect trùng.
- **Transactional outbox/event:** ghi thay đổi trạng thái và sự kiện cần phát trong cùng giao dịch để tránh DB đã revoke nhưng event bị mất.
- **Cache invalidation:** xóa cache hoặc cập nhật version; TTL cache phải phù hợp với mục tiêu thời gian thu hồi.
- **Fail closed:** nếu verifier không thể xác định credential còn active hay không, endpoint nhạy cảm không nên chấp nhận chỉ dựa trên dữ liệu cũ.
- **Audit ordering:** ghi thời điểm và phiên bản trạng thái để điều tra các request đến đồng thời với lúc thu hồi.

Ví dụ pseudocode:

~~~ts
async function revokeEnrollment(input) {
  return database.transaction(async (tx) => {
    const record = await tx.enrollments.findForUpdate(
      input.enrollmentId,
      input.tenantId
    );

    if (!record) throw new NotFoundError();
    if (record.status === "revoked") return record;
    if (record.status !== "active") {
      throw new ConflictError("Enrollment is not active");
    }

    const revoked = await tx.enrollments.update({
      id: record.id,
      status: "revoked",
      revokedAt: new Date(),
      revokedBy: input.actorId,
      revocationReason: input.reason,
      version: record.version + 1
    });

    await tx.outbox.insert({
      type: "EnrollmentRevoked",
      aggregateId: record.id,
      version: revoked.version
    });

    return revoked;
  });
}
~~~

Đây là pseudocode mô tả giao dịch, không phải implementation hoàn chỉnh. Cần kiểm tra quyền của actor và tenant trước khi gọi; worker outbox phải retry, deduplicate và cập nhật các verifier/session store. Không ghi log secret hoặc private key. Nếu có race giữa xác thực và thu hồi, hệ thống cần quy định thời điểm tuyến tính hóa: request xác thực đã hoàn tất trước commit thu hồi có thể được coi là đã qua, còn request kiểm tra sau commit phải thấy trạng thái revoked.

## 11. Ngăn attacker thu hồi enrollment của nạn nhân

Thu hồi không chỉ là kiểm soát chống chiếm tài khoản; nó cũng có thể bị lạm dụng để gây khóa tài khoản. Attacker có session yếu hoặc chiếm một kênh recovery có thể:

- Xóa passkey và security key của chủ tài khoản.
- Thu hồi factor dự phòng trước khi thêm credential của attacker.
- Xóa recovery code để chủ tài khoản khó khôi phục.
- Gửi hàng loạt yêu cầu thu hồi để gây gián đoạn.
- Lợi dụng nhân viên hỗ trợ để xóa phương thức xác thực sau khi giả danh chủ tài khoản.

Biện pháp:

1. Step-up bằng credential độc lập hoặc quy trình recovery có bảo đảm phù hợp.
2. Yêu cầu phê duyệt bổ sung khi xóa credential cuối cùng hoặc thay đổi toàn bộ phương thức recovery.
3. Thông báo qua kênh độc lập đã xác minh khi enrollment bị thu hồi.
4. Có thời gian chờ hoặc cơ chế review cho hành động rủi ro cao, nhưng vẫn cho phép thu hồi khẩn cấp khi credential bị lộ.
5. Rate limit theo tài khoản, actor, tenant và nguồn request.
6. Không cho phép session vừa được recovery hoặc vừa đổi mật khẩu tự động xóa mọi factor cũ mà không có kiểm soát bổ sung.
7. Giữ một đường recovery có kiểm soát để chủ tài khoản hợp lệ không bị khóa vĩnh viễn.
8. Audit và cảnh báo khi một tác nhân xóa nhiều credential hoặc xóa liên tiếp các factor mạnh.

Không nên trì hoãn vô điều kiện mọi thao tác thu hồi. Nếu điện thoại bị đánh cắp, trì hoãn có thể kéo dài thời gian attacker dùng credential. Policy cần cân bằng giữa chống sabotage và phản ứng nhanh với sự cố.

## 12. Thông báo, audit và quyền riêng tư

Sự kiện thu hồi nên ghi lại:

- Enrollment ID và loại credential.
- Principal/tenant bị ảnh hưởng.
- Tác nhân yêu cầu và vai trò của họ.
- Thời điểm yêu cầu, thời điểm commit và nguồn request theo chính sách.
- Lý do thu hồi theo danh mục.
- Trạng thái xử lý downstream: session, token, cache, verifier và thông báo.
- Request/correlation ID để nối sự kiện.

Không ghi private key, secret TOTP, API key, recovery code, session cookie hoặc token plaintext vào audit log. Địa chỉ IP, thiết bị và dữ liệu vị trí cũng là dữ liệu nhạy cảm; chỉ lưu khi có mục đích, quyền truy cập và thời hạn rõ ràng.

Thông báo cho người dùng nên nêu phương thức nào đã bị thu hồi, thời điểm, nguồn yêu cầu ở mức phù hợp và cách liên hệ nếu họ không thực hiện thao tác. Không đưa thông tin có thể giúp attacker suy ra secret hoặc vượt qua quy trình hỗ trợ.

## 13. Thay thế enrollment sau khi thu hồi

Thu hồi một factor có thể làm người dùng mất khả năng đăng nhập. Quy trình thay thế phải đủ mạnh để không trở thành đường tắt cho attacker:

1. Xác minh người dùng bằng một factor còn tin cậy hoặc quy trình proofing/recovery được phê duyệt.
2. Đánh giá session, thiết bị và sự kiện bảo mật gần đây.
3. Tạo enrollment mới với challenge mới, liên kết đúng principal và tenant.
4. Yêu cầu người dùng hoàn tất xác minh trên authenticator mới.
5. Kích hoạt credential mới chỉ sau khi server xác minh đầy đủ.
6. Cấp hoặc làm mới recovery code theo policy; thu hồi bộ code cũ nếu có nguy cơ lộ.
7. Thông báo enrollment mới và giữ audit liên kết với sự cố trước đó.
8. Xác nhận người dùng có phương thức dự phòng phù hợp trước khi xóa factor cuối cùng khác.

Không sao chép secret cũ sang enrollment mới. Nếu một credential bị lộ, credential thay thế phải có khóa/secret mới và có liên kết mới trong registry.

## 14. Ví dụ: nhân viên mất điện thoại có passkey và TOTP

Một nhân viên báo mất điện thoại trên đường đi làm. Tài khoản công ty có passkey trên điện thoại, TOTP trong ứng dụng xác thực và security key dự phòng cất tại văn phòng.

**Xử lý:**

1. Nhân viên liên hệ qua kênh hỗ trợ đã công bố hoặc đăng nhập bằng security key dự phòng.
2. Hệ thống xác minh danh tính và quyền yêu cầu thu hồi; nếu có dấu hiệu thiết bị bị đánh cắp cùng trạng thái mở khóa, áp dụng incident policy.
3. Thu hồi enrollment passkey và TOTP gắn với điện thoại bị mất.
4. Thu hồi session/token có liên quan tới thiết bị hoặc các session trong khoảng nghi ngờ; nếu không thể xác định, áp dụng phạm vi thu hồi rộng hơn theo policy.
5. Xóa cache trạng thái credential và phát sự kiện tới các verifier/gateway.
6. Gửi thông báo tới kênh liên hệ độc lập đã xác minh.
7. Nhân viên dùng security key để đăng nhập, đăng ký passkey trên thiết bị mới và xác minh enrollment mới.
8. Kiểm tra recovery code, cập nhật danh sách authenticator và kết thúc incident.

**Kết quả mong đợi:** điện thoại cũ có thể vẫn chứa private key và secret trong bộ nhớ, nhưng dịch vụ không còn chấp nhận credential đã bị thu hồi. Session/token liên quan được xử lý theo policy; thiết bị mới nhận credential độc lập.

## 15. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ xóa cookie mà không thu hồi enrollment | Credential cũ vẫn đăng nhập được ở lần sau. | Đánh dấu credential revoked tại verifier/registry. |
| Xóa bản ghi ngay lập tức | Mất dấu vết và có thể không phân biệt được credential cũ khi đồng bộ chậm. | Giữ tombstone theo retention policy. |
| Cho phép kích hoạt lại record revoked | Credential đã lộ có thể sống lại. | Tạo enrollment mới với key/secret mới. |
| Không kiểm tra status ở mọi verifier | Node/cache cũ tiếp tục chấp nhận credential. | Lan truyền revoke, giới hạn TTL và fail closed khi cần. |
| Thu hồi factor nhưng giữ session bị chiếm | Attacker vẫn dùng phiên đã cấp. | Đánh giá session/token theo authentication event và thiết bị. |
| Xóa tất cả factor chỉ bằng một session yếu | Attacker có thể khóa chủ tài khoản. | Step-up, phê duyệt và thông báo độc lập. |
| Nghĩ RP có thể xóa private key passkey từ xa | Đánh giá sai khả năng kiểm soát thiết bị. | Thu hồi public key record tại RP; xử lý xóa thiết bị riêng. |
| Chỉ xóa certificate trong database ứng dụng | TLS/gateway khác vẫn có thể tin certificate. | Đồng bộ CA revocation, CRL/OCSP và trust store. |
| Retry thu hồi tạo side effect lặp | Audit/event hoặc thông báo bị nhân đôi. | Idempotency, unique event ID và transactional outbox. |
| Không có phương thức recovery thay thế | Người dùng bị khóa tài khoản. | Thiết kế backup authenticator và recovery proofing trước sự cố. |
| Log secret hoặc token trong audit | Tạo thêm đường lộ credential. | Chỉ log metadata, correlation ID và trạng thái. |

## 16. Checklist triển khai thu hồi enrollment

Trước khi đưa quy trình thu hồi vào production, hãy kiểm tra:

1. Enrollment/credential nào đang bị thu hồi và nó gắn với đúng principal, tenant, loại factor không?
2. Người yêu cầu có được xác thực và có quyền thu hồi không? Có cần step-up hoặc phê duyệt kép không?
3. Có phân biệt thu hồi credential, khóa tài khoản, thu hồi session/token và xóa vật lý không?
4. Verifier có kiểm tra trạng thái Active/Revoked ở mọi lần xác thực không?
5. Thay đổi trạng thái có nguyên tử, idempotent và có audit không?
6. Tombstone và trạng thái thu hồi có được giữ đủ lâu để tránh credential cũ sống lại sau cache/backup restore không?
7. Cache, gateway, verifier và các region có nhận trạng thái thu hồi trong thời gian mục tiêu không?
8. Khi hệ thống trạng thái không khả dụng, endpoint nhạy cảm có fail closed không?
9. Session, refresh token, access token và grant được đánh giá theo phạm vi rủi ro chưa?
10. Cơ chế thu hồi có phù hợp với passkey, TOTP, security key, certificate, API key và recovery code không?
11. Người dùng có phương thức thay thế an toàn và quy trình enrollment mới không?
12. Có chống attacker thu hồi factor của nạn nhân, rate limit, thông báo và xử lý ngoại lệ không?
13. Audit log có đủ điều tra nhưng không chứa secret, private key, token hoặc dữ liệu cá nhân dư thừa không?
14. Có kiểm thử race giữa authentication và revocation, nhiều node, retry, cache stale, restore backup và credential đã revoked không?

**Kết luận:** Thu hồi enrollment làm cho một credential đã đăng ký không còn được hệ thống chấp nhận. Việc này cần cập nhật trạng thái ở verifier, lan truyền tới các node, đánh giá session/token liên quan và cung cấp đường thay thế an toàn. Thu hồi tại dịch vụ không nhất thiết xóa private key khỏi thiết bị; với mỗi loại credential cần cách xử lý riêng. Quy trình tốt phải vừa ngăn credential bị mất hoặc lộ tiếp tục được dùng, vừa ngăn attacker lợi dụng chức năng thu hồi để khóa chủ tài khoản.
