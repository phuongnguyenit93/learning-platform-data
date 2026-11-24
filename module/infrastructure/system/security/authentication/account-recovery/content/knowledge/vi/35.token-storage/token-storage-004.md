# Token database access — Kiểm soát truy cập cơ sở dữ liệu token khôi phục

## 1. Cơ sở dữ liệu token là một ranh giới cấp quyền

Một bảng token khôi phục không chỉ là nơi lưu vài chuỗi ngẫu nhiên. Nó thường quyết định bí mật nào còn được dùng, thuộc tài khoản nào và có thể đổi lấy hành động gì. Quyền truy cập bảng đó vì thế liên quan trực tiếp đến quyền đặt lại mật khẩu hoặc tiếp tục một tuyến khôi phục.

**Token database access** là việc kiểm soát chủ thể nào được đọc, thêm, thay đổi hoặc xóa dữ liệu token; trong phạm vi nào; qua giao diện nào; và với điều kiện nghiệp vụ gì.

Cần trả lời đồng thời hai nhóm câu hỏi:

- Ai có thể lấy được dữ liệu đủ để đoán, sao chép hoặc sử dụng token?
- Ai có thể thay đổi trạng thái để một token sai, hết hạn, đã dùng hoặc sai mục đích trở thành được chấp nhận?

Chỉ băm token trước khi lưu chưa giải quyết nhóm câu hỏi thứ hai. Một thiết kế có giá trị kiểm chứng tốt nhưng cấp quyền cập nhật tùy ý vẫn có thể để lộ đường chiếm đoạt tài khoản.

OWASP khuyến nghị tài khoản cơ sở dữ liệu của ứng dụng chỉ có quyền tối thiểu cần thiết và không dùng tài khoản quản trị cho hoạt động thông thường. Nguyên tắc đó được áp dụng ở đây cho dữ liệu khôi phục. [OWASP — Database Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html)

Các vai trò, cấu trúc và mã giả trong bài là thiết kế minh họa. Chúng cần được điều chỉnh theo ranh giới dịch vụ và khả năng của hệ quản trị đang sử dụng.

## 2. Phân loại dữ liệu trước khi phân quyền

Một bản ghi token có thể chứa những nhóm dữ liệu khác nhau:

| Nhóm | Ví dụ | Rủi ro khi bị truy cập sai |
| --- | --- | --- |
| Bí mật gốc | Token trong email hoặc mã khôi phục | Có thể trở thành bằng chứng trực tiếp nếu các điều kiện khác đạt |
| Giá trị kiểm chứng | Digest hoặc MAC của bí mật | Có thể hỗ trợ dò offline; không được chấp nhận trực tiếp như token |
| Định danh và phạm vi | Tenant, account, flow, purpose | Có thể bị dùng để đổi đích hoặc mở rộng quyền |
| Trạng thái sử dụng | ACTIVE, CONSUMED, REVOKED, REPLACED | Có thể bị sửa để cho phép dùng lại |
| Thời gian | Thời điểm cấp, hết hạn, tiêu thụ | Có thể bị sửa để kéo dài quyền |
| Phiên bản | Phiên bản bản ghi, generation, security epoch | Có thể liên quan đến kiểm soát đồng thời hoặc thu hồi |
| Dữ liệu vận hành | ID tác vụ gửi, mã lý do, correlation ID | Có thể làm lộ hành vi tài khoản hoặc hỗ trợ điều tra |
| Dữ liệu chuyển phát có thể giải mã | Envelope chứa token để thử gửi lại | Người có dữ liệu và quyền giải mã có thể lấy bí mật gốc |

Không cần cho mọi thành phần nhìn thấy tất cả các nhóm này. Nhân viên hỗ trợ cần biết một liên kết đã hết hạn thường không cần đọc verifier, email đầy đủ hoặc dữ liệu chuyển phát.

Tên cột cũng có thể gây nhầm lẫn. Nếu cột `token_hash` được API chấp nhận nguyên văn làm token, nó đã hoạt động như một bearer secret khác. Quyền đọc cột đó khi ấy có hậu quả khác hẳn một verifier chỉ dùng nội bộ.

## 3. Đọc và ghi gây ra những kiểu rủi ro khác nhau

### Đọc dữ liệu

Nếu token gốc có entropy cao và máy chủ chỉ lưu verifier một chiều phù hợp, việc đọc được một bản ghi không nhất thiết cho phép suy ra token ngay. Tuy nhiên, điều đó không làm quyền SELECT trở thành vô hại.

Bản sao có thể chứa mã ngắn dễ dò, metadata nhạy cảm, thông tin tài khoản hoặc dữ liệu đã mã hóa mà một thành phần khác có khả năng giải mã. Một truy vấn xuất toàn bộ bảng còn làm tăng phạm vi sự cố từ một token lên toàn hệ thống.

### Ghi dữ liệu

Quyền ghi có thể cho phép:

- Gắn token vào tài khoản hoặc mục đích khác.
- Đổi thời hạn hết hạn.
- Đưa bản ghi đã dùng về trạng thái hiện hành.
- Thay con trỏ token hiện tại của một luồng.
- Xóa thông tin thu hồi hoặc dấu vết tiêu thụ.
- Tạo bản ghi mới có giá trị kiểm chứng do người ghi chọn.

Ví dụ, với thiết kế chỉ dùng digest không khóa, bên có quyền ghi tùy ý có thể chọn bí mật S rồi chèn digest của S vào một bản ghi nhắm tới nạn nhân. Nếu ứng dụng tin toàn bộ bản ghi đó, người ghi có thể đã tự tạo một bằng chứng được ứng dụng chấp nhận.

MAC có khóa bảo vệ một số trường hợp khi khóa nằm ngoài phạm vi dữ liệu bị lộ. Nhưng nó không tự bảo vệ mọi metadata hoặc trạng thái. Những trường không được ràng buộc mật mã vẫn có thể bị sửa; một trạng thái hợp lệ cũ cũng có thể bị phát lại trong một thiết kế không chống rollback.

Vì vậy, không nên kết luận “đã dùng HMAC nên tài khoản ghi cơ sở dữ liệu có thể được cấp rộng”. Cần bảo vệ cả tính bí mật lẫn tính toàn vẹn của quyết định cấp quyền.

## 4. Phân quyền theo thao tác nghiệp vụ

Một ma trận quyền minh họa:

| Chủ thể | Quyền nghiệp vụ cần có | Dữ liệu không nên được truy cập tùy ý |
| --- | --- | --- |
| Thành phần phát hành | Tạo token theo luồng được phép, ghi verifier và metadata đã ràng buộc | Token của các tài khoản khác; sửa lịch sử tiêu thụ |
| Thành phần xác minh và tiêu thụ | Đọc đúng bản ghi cần kiểm chứng, chốt tiêu thụ và tạo quyền hạn chế | Quét toàn bộ bảng; đổi account hoặc purpose |
| Worker chuyển phát | Đọc tác vụ gửi và envelope cần thiết trong thời gian cho phép | Verifier toàn bảng; trạng thái cấp quyền của luồng khác |
| Tác vụ dọn dữ liệu | Xóa dữ liệu đã đủ điều kiện theo chính sách lưu giữ | Cấp token mới; đưa trạng thái về ACTIVE |
| Công cụ hỗ trợ | Đọc metadata đã giảm nhạy cảm; yêu cầu thao tác được cho phép | Token gốc, verifier, quyền sửa trực tiếp mọi cột |
| Thành phần audit | Ghi hoặc đọc sự kiện theo phạm vi được cấp | Sửa ngược lịch sử nghiệp vụ |
| Vai trò migration | Thay đổi schema và quyền theo quy trình triển khai | Không được dùng làm danh tính runtime thường xuyên |

Đây là phân chia **khả năng nghiệp vụ**, không phải yêu cầu mỗi hàng luôn phải trở thành một microservice riêng.

Nếu mọi vai trò dùng chung một thông tin đăng nhập cơ sở dữ liệu có toàn quyền, sự phân chia trong tên lớp Java không tạo ra cách ly quyền. Nếu một tiến trình giữ đủ mọi credential, việc chiếm quyền tiến trình đó cũng có thể vượt qua phần lớn sự tách biệt.

Tách vai trò chỉ có ý nghĩa khi được thực thi bằng danh tính kết nối, quyền đối tượng, giao diện dịch vụ hoặc ranh giới vận hành phù hợp. Không chỉ đặt tên `TokenReadRepository` rồi kết nối bằng tài khoản chủ sở hữu database.

## 5. Chọn giao diện dữ liệu hẹp

Có ba cách thường được phối hợp:

### Quyền bảng và cột

Chỉ cấp những thao tác, bảng và cột cần thiết. Một thành phần cần đánh dấu tiêu thụ không mặc nhiên cần được sửa `account_id`, `purpose`, `verifier` hoặc `expires_at`.

Tuy nhiên, quyền cập nhật một cột trạng thái vẫn có thể quá rộng nếu caller được đổi bất kỳ hàng nào từ `CONSUMED` về `ACTIVE`. Quyền cột cần đi cùng điều kiện hàng và chuyển trạng thái.

### View dành cho đọc

Một view hỗ trợ có thể chỉ trả:

~~~text
flow_id
token_id
purpose
state
issued_at
expires_at
delivery_status_group
~~~

Nếu caller vẫn có SELECT trực tiếp trên bảng gốc, view không còn là ranh giới che các cột nhạy cảm. Quyền trên các bảng liên kết cũng cần được xem xét để không suy ra dữ liệu đã cố ý ẩn.

### Hàm hoặc API nghiệp vụ có giới hạn

Thay vì cho caller cập nhật tùy ý, có thể cung cấp thao tác như:

~~~text
issueTokenForAllowedFlow(...)
redeemCurrentToken(...)
revokeRecoveryFlow(...)
deleteEligibleExpiredRecords(...)
~~~

Giao diện phải thực thi phạm vi và chuyển trạng thái, không chỉ bọc một câu UPDATE tùy ý.

Một hàm nhận `token_id` và `verified=true` không tự tạo ranh giới chống ứng dụng bị chiếm quyền nếu caller có thể tự khai kết quả kiểm chứng. Cần hiểu thành phần nào được tin để xác minh bí mật và dựa trên bằng chứng gì.

Nếu chuyển việc kiểm chứng vào cơ sở dữ liệu, bí mật truyền vào có thể xuất hiện trong log truy vấn hoặc tham số. Khi đó, bảo vệ giao diện, quyền gọi và hệ thống ghi log là một phần của thiết kế; stored procedure không tự làm bí mật biến mất.

## 6. Truy vấn phải giữ đúng tenant, luồng và mục đích

Một truy vấn tra cứu cần có phạm vi rõ ràng. Ví dụ SQL có tham số:

~~~sql
SELECT
    token_id,
    flow_id,
    account_id,
    purpose,
    verifier,
    verifier_key_version,
    state,
    expires_at,
    row_version
FROM recovery_token
WHERE tenant_id = :trusted_tenant_id
  AND selector = :submitted_selector;
~~~

Đây chỉ là truy vấn minh họa, chưa phải toàn bộ quyết định chấp nhận token.

`:submitted_selector` là dữ liệu đầu vào. Nó chỉ giúp tìm bản ghi; tìm thấy selector không chứng minh người gửi biết phần bí mật.

`:trusted_tenant_id` phải đến từ ngữ cảnh được máy chủ xác định hợp lệ. Không dùng một tenant ID do client tùy ý khai, hoặc một Host header chưa được đối chiếu, làm ranh giới truy cập.

Sau khi tìm được bản ghi, máy chủ vẫn phải kiểm tra:

- Bí mật gửi lên khớp với verifier.
- Tài khoản và luồng đích phù hợp với trạng thái đã lưu.
- Mục đích của token cho phép hành động đang yêu cầu.
- Token còn hiện hành, chưa hết hạn, chưa dùng và chưa thu hồi.
- Các điều kiện bổ sung như ràng buộc ngữ cảnh và chính sách rủi ro còn đạt.

Truy vấn có tham số giúp tách dữ liệu khỏi cấu trúc SQL. Nó không chứng minh người gọi có quyền truy cập bản ghi. Một câu SQL được parameterize hoàn hảo vẫn có thể trả nhầm tenant nếu điều kiện phạm vi bị thiếu.

Không dùng `SELECT *` theo thói quen khi chỉ cần một tập trường nhỏ. Điều đó giúp tránh làm lộ thêm dữ liệu khi schema được mở rộng và giảm việc đối tượng token nhạy cảm bị truyền qua nhiều tầng không cần thiết.

## 7. RLS là một lớp bảo vệ, không phải lời bảo đảm tuyệt đối

Một số hệ quản trị hỗ trợ row-level security, cho phép giới hạn những hàng mà một vai trò có thể đọc hoặc sửa.

Ví dụ, tài liệu PostgreSQL 18 nêu rằng superuser và vai trò có `BYPASSRLS` bỏ qua RLS; chủ sở hữu bảng thông thường cũng bỏ qua trừ khi áp dụng cơ chế FORCE tương ứng. [PostgreSQL 18 — Row Security Policies](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)

Hệ quả với dữ liệu token:

- Không đánh giá hiệu quả RLS chỉ bằng việc nhìn thấy một policy đã tồn tại.
- Cần biết danh tính kết nối thực tế có phải owner, superuser hoặc thành viên của vai trò có thể nâng quyền hay không.
- Không để vai trò runtime tự thay policy hoặc tùy ý chọn một vai trò mạnh hơn.
- Những thao tác đặc quyền phải được xem xét ngoài phạm vi truy vấn thông thường.

Nếu policy lấy tenant từ một giá trị phiên mà cùng caller có thể tùy ý sửa, policy đó có thể chỉ giúp tránh một số lỗi lập trình, chứ chưa cách ly được một ứng dụng có quyền chạy SQL tùy ý.

Với connection pool, ngữ cảnh tenant hoặc vai trò không được rò từ yêu cầu trước sang yêu cầu sau. Việc đặt và dọn ngữ cảnh phải có ranh giới giao dịch hoặc cơ chế quản lý phù hợp, bao gồm cả nhánh lỗi.

RLS cũng không tự thực hiện tính dùng một lần, kiểm chứng bí mật hoặc quyết định rằng token đặt lại mật khẩu được phép bỏ MFA. Những điều đó vẫn thuộc logic khôi phục.

## 8. Cẩn trọng với hàm chạy bằng quyền chủ sở hữu

Trong PostgreSQL, `SECURITY DEFINER` làm hàm chạy với quyền của chủ sở hữu hàm. Nếu dùng cách này để giới hạn quyền bảng của runtime, chính hàm trở thành một cổng đặc quyền cần được thiết kế chặt.

Tài liệu PostgreSQL yêu cầu chú ý đến `search_path`, tránh schema mà bên không tin cậy có thể ghi, và lưu ý hàm mới mặc định có quyền EXECUTE cho `PUBLIC`. [PostgreSQL 18 — CREATE FUNCTION: Writing SECURITY DEFINER Functions Safely](https://www.postgresql.org/docs/18/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY)

Một thiết kế cho token cần xét ít nhất:

- Ai sở hữu hàm và chủ sở hữu có những quyền nào?
- Vai trò nào được gọi đúng chữ ký hàm?
- Hàm có tự kiểm tra tenant, luồng, trạng thái và hành động không?
- Có SQL động ghép từ dữ liệu không tin cậy không?
- Tên đối tượng có được giải quyết trong phạm vi schema đáng tin không?
- Caller có thể thay định nghĩa hàm hoặc tạo đối tượng gây nhầm tên không?
- Kết quả trả về có vô tình làm lộ verifier hoặc dữ liệu các tài khoản khác không?

Không dùng một hàm có quyền cao để trả về toàn bộ hàng token rồi gọi đó là “truy cập qua giao diện hẹp”. Giới hạn phải nằm trong chính hành vi và dữ liệu trả về.

Nếu chỉ cần một thao tác cụ thể, cũng không cần để chủ sở hữu hàm có quyền quản trị toàn instance. Phạm vi đặc quyền của hàm nên vừa đủ cho nhiệm vụ.

## 9. Tiêu thụ token cần nhất quán với việc cấp quyền

Một lần đọc thấy `state=ACTIVE` không bảo đảm token vẫn còn hiệu lực lúc tạo quyền khôi phục.

Hai node có thể cùng đọc một token chưa dùng. Nếu mỗi node chỉ ghi “đã dùng” sau khi tạo quyền, cả hai có thể đã cấp quyền trước khi phát hiện cạnh tranh.

Một trình tự minh họa:

~~~text
redeemToken(serverScope, submittedToken, requestedAction):
    enforceTrafficLimits()
    parsed = parseStrictly(submittedToken)

    transaction:
        flow = lockAllowedRecoveryFlow(serverScope, parsed.selector)
        token = lockCurrentTokenOfFlow(flow)

        require tokenMatchesSubmittedLocator(token, parsed)
        require verifySecret(parsed.secret, token.verifier)
        require tokenBelongsToExpectedTenantAccountPurpose(token, flow)
        require token.state == ACTIVE
        require tokenIsCurrentGeneration(token, flow)
        require notExpiredAtTrustedDecisionTime(token, flow)
        require notRevokedAndPolicyStillAllows(flow, requestedAction)

        changed = consumeOnlyIfCurrentVersionMatches(token)
        require changed == 1

        grant = insertUniqueRestrictedGrantForApprovedAction(flow)
        saveAuditEventWithoutSecrets()
        commit()

    return grantThroughApprovedMechanism()
~~~

Mọi thao tác thay thế, thu hồi và tiêu thụ có thể cạnh tranh với nhau phải tuân theo ranh giới đồng bộ tương ứng. Khóa flow riêng lẻ là chưa đủ nếu chính sách cần bảo đảm duy nhất trên toàn tài khoản và mục đích.

Có thể dùng khóa, cập nhật có điều kiện, kiểm tra phiên bản hoặc cơ chế giao dịch phù hợp với kho dữ liệu. Tính đúng đắn không đến từ tên kỹ thuật, mà từ việc một trạng thái hợp lệ chỉ tạo được kết quả đã cho phép.

Nếu cập nhật có điều kiện ảnh hưởng 0 hàng, không tiếp tục tạo grant. Không dùng một lần đọc cache sau đó để “xác nhận lại” rằng token có vẻ vẫn ACTIVE.

Nếu hành động thay đổi mật khẩu được thực hiện trực tiếp khi tiêu thụ token, thay đổi được bảo vệ và việc tiêu thụ cần có ranh giới nhất quán phù hợp. Nếu token chỉ đổi lấy G là một quyền hạn chế, bước dùng G cũng cần kiểm soát riêng.

Timeout sau commit là một trạng thái kết quả chưa rõ đối với client. Không tự suy ra giao dịch đã rollback rồi cấp thêm quyền. Cần idempotency hoặc cách tiếp tục giao dịch gắn với đúng ngữ cảnh và thao tác.

## 10. Không dùng replica hoặc cache cũ làm nguồn quyết định cuối

Bản sao đọc có thể chưa nhận trạng thái token vừa được tiêu thụ hoặc thu hồi. Cache có thể vẫn giữ `ACTIVE` sau khi bản ghi chuẩn đã chuyển sang `REVOKED`.

Vì vậy, trong mô hình của bài:

- Dữ liệu tổng hợp phục vụ hỗ trợ có thể dùng bản sao theo chính sách phù hợp.
- Điểm chấp nhận cuối cùng phải dựa trên trạng thái có thẩm quyền và một thao tác nhất quán.
- Một kết quả đọc cũ không được thay thế kết quả cập nhật có điều kiện đã thất bại.
- Thông điệp vô hiệu hóa cache giúp giảm dữ liệu lỗi thời, nhưng không tự bảo đảm dùng một lần.

Trong triển khai nhiều vùng, cần xác định nơi nào có quyền chốt tiêu thụ. Cho hai vùng cùng tự cấp quyền từ bản sao cục bộ rồi hợp nhất sau có thể đã cấp hai quyền trước khi giải quyết xung đột.

Nếu hệ thống không thể kiểm tra trạng thái có thẩm quyền, chưa có cơ sở cho phép token. Không chuyển sang đường cho qua chỉ vì cơ sở dữ liệu chính đang lỗi.

Tính sẵn sàng cần được giải quyết bằng kiến trúc phục hồi và trải nghiệm tiếp tục phù hợp, không bằng cách bỏ điều kiện an ninh lúc kho dữ liệu không khả dụng.

## 11. Credential và kết nối là một phần của quyền truy cập

Quyền trên bảng chỉ có ý nghĩa nếu thông tin đăng nhập được bảo vệ.

Một thiết kế vận hành cần xác định:

- Mỗi ứng dụng hoặc vai trò dùng danh tính nào.
- Credential được cấp, lưu, xoay và thu hồi ra sao.
- Kết nối nào được phép đến database.
- Client kiểm chứng máy chủ như thế nào.
- Connection pool giữ credential và session đặc quyền trong bao lâu.

Không dùng credential migration hoặc tài khoản quản trị trong cấu hình runtime chỉ để tránh lỗi thiếu quyền. Lỗi quyền cần được giải quyết bằng việc xác định thao tác còn thiếu, không bằng cấp toàn quyền cho mọi thành phần.

Các môi trường phát triển, thử nghiệm và production cần được cách ly phù hợp. Không sao chép credential production vào máy cá nhân để xử lý một yêu cầu hỗ trợ.

Với kết nối qua mạng, mã hóa đường truyền phải đi cùng xác minh máy chủ. Bật TLS nhưng chấp nhận mọi chứng chỉ có thể vẫn nối tới một đích không được tin cậy. OWASP đề cập cả TLS và kiểm chứng chứng chỉ cho kết nối database trong [Database Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html).

Khi thu hồi danh tính hoặc thay đổi quyền, cần hiểu tác động đến các kết nối đã có trong pool. Một thay đổi credential không phải lúc nào cũng đồng nghĩa mọi kết nối cũ đã ngừng hoạt động. Quy trình phải xét cơ chế thực tế của hệ quản trị và hạ tầng kết nối.

## 12. Log, bản sao lưu và công cụ hỗ trợ cũng là đường truy cập

Dữ liệu token có thể đi xa hơn bảng chính:

~~~text
Bảng token
    ├── Log truy vấn và tham số
    ├── Trace của ứng dụng hoặc APM
    ├── Read replica
    ├── CDC hoặc luồng sự kiện
    ├── Backup và transaction log
    ├── Công cụ BI hoặc xuất CSV
    └── Giao diện hỗ trợ khách hàng
~~~

Mỗi đường này cần một quyết định quyền và thời gian lưu. Không nên tự đưa verifier hoặc envelope có thể giải mã vào hệ thống phân tích chỉ vì bộ đồng bộ mặc định sao chép mọi cột.

Một câu truy vấn có tham số không bảo đảm tham số bị ẩn khỏi mọi log. Chính sách ghi SQL, driver, công cụ giám sát và đường báo lỗi có thể ghi lại dữ liệu nhạy cảm.

Audit nên tập trung vào thông tin đủ để giải thích quyết định:

| Nên cân nhắc ghi | Tránh ghi nguyên văn |
| --- | --- |
| Actor hoặc service identity | Token gốc |
| Flow ID, token ID không bí mật | Verifier |
| Loại thao tác và mục đích | Khóa MAC hoặc credential database |
| Phiên bản và kết quả chuyển trạng thái | Cookie hoặc grant bearer |
| Correlation ID và thời gian | URL đầy đủ chứa token |
| Mã lý do nội bộ có kiểm soát | Dữ liệu xác minh danh tính không cần thiết |

Nhân viên hỗ trợ nên thực hiện hành động qua giao diện có giới hạn và lưu dấu vết. Không nên có nút hoặc câu SQL “đưa token về ACTIVE” để giải quyết mọi khiếu nại.

Mã hóa ổ đĩa hoặc backup bảo vệ một số tình huống lấy cắp bản lưu. Nó không che dữ liệu khỏi một tài khoản được phép SELECT qua máy chủ đang hoạt động. Tương tự, ai có quyền giải mã backup có thể có khả năng đọc dữ liệu mà vai trò runtime không được đọc.

## 13. Dọn dữ liệu và khôi phục backup không được làm token sống lại

Tác vụ dọn nên có điều kiện rõ: phạm vi thời gian, trạng thái được xóa, nhu cầu lưu dấu vết và giới hạn lượng dữ liệu mỗi lượt. Nó không cần quyền cấp token hoặc thay đổi tài khoản đích.

Xóa hết bảng để “thu hồi mọi token” có thể làm mất bằng chứng điều tra hoặc ảnh hưởng luồng đang xử lý. Nếu cần thu hồi diện rộng, nên có thao tác và ranh giới nhất quán được thiết kế cho mục tiêu đó.

Ngược lại, phục hồi một backup cũ có thể đưa dữ liệu quay về thời điểm trước khi token được tiêu thụ:

~~~text
10:00 — Backup ghi token T đang ACTIVE
10:05 — T được tiêu thụ hợp lệ
10:20 — Phục hồi database về bản 10:00
~~~

Nếu hệ thống chỉ tin bản ghi vừa phục hồi, T có thể bị xem là chưa dùng. Băm hoặc MAC còn hợp lệ không tự phát hiện việc phát lại một trạng thái từng hợp lệ.

Quy trình phục hồi cần có quyết định an ninh riêng, chẳng hạn:

- Làm mất hiệu lực toàn bộ token khôi phục trước mốc phục hồi.
- Dùng một phiên bản an ninh hoặc mốc thu hồi được quản lý sao cho không cùng bị quay lùi.
- Yêu cầu khởi tạo lại những luồng bị ảnh hưởng.
- Đối chiếu trạng thái với nguồn có thẩm quyền khác nếu kiến trúc hỗ trợ.

Không chỉ tăng một giá trị epoch nằm trong cùng backup rồi mặc định nó luôn chống rollback. Phải xác định rõ nguồn chuẩn nào không bị quay lùi theo cùng sự cố và mọi đường xác minh có kiểm tra nó hay không.

Việc phục hồi dữ liệu kỹ thuật và phục hồi quyền sử dụng token là hai quyết định liên quan nhưng khác nhau. Có thể cần giữ bản ghi cũ để điều tra trong khi vẫn từ chối toàn bộ quyền khôi phục cũ.

## 14. Những kết quả cần phân biệt trong vận hành

| Tình huống | Ý nghĩa và cách xử lý |
| --- | --- |
| Công cụ hỗ trợ đọc trạng thái hết hạn | Có thể cho phép qua dữ liệu đã giảm nhạy cảm; không cần verifier |
| Runtime yêu cầu quyền owner để chạy một truy vấn | Cần xem lại thiết kế quyền; không mặc nhiên cấp owner |
| Truy vấn đúng cú pháp nhưng thiếu tenant | Vẫn có nguy cơ sai phạm vi truy cập |
| Role có RLS nhưng đồng thời có BYPASSRLS | Policy không tạo giới hạn như kỳ vọng cho role đó |
| Hàm đặc quyền nhận ID tùy ý rồi cập nhật bất kỳ token nào | Giao diện chưa thực thi quyền nghiệp vụ |
| Bản sao đọc báo ACTIVE nhưng cập nhật chuẩn thất bại | Không cấp quyền từ dữ liệu cũ |
| Hai node cùng nộp một token | Chỉ thao tác chốt hợp lệ được tạo kết quả theo chính sách |
| Log giữ raw token trong tham số | Log đã trở thành kho bí mật cần xử lý |
| Token lưu dạng digest có entropy cao bị đọc | Không đồng nghĩa lập tức suy ra token; vẫn là sự cố truy cập cần đánh giá |
| Bên khác ghi lại trạng thái ACTIVE | Có thể phá vòng đời dùng một lần dù verifier không đổi |
| Restore backup chứa token chưa dùng | Cần quyết định vô hiệu hóa hoặc đối chiếu để tránh hồi sinh quyền |
| Database không truy cập được | Không bỏ qua xác minh để tiếp tục khôi phục |

Trong khôi phục mật khẩu, MFA, passkey hoặc thiết bị xác thực, quyền truy cập dữ liệu phải giữ đúng mức quyền của từng tuyến. Một token chứng minh bước nhận email không tự trở thành quyền thay mọi cấu hình bảo mật chỉ vì các bản ghi cùng nằm trong một database.

Thiết kế truy cập tốt làm rõ danh tính kết nối, dữ liệu tối thiểu, phạm vi hàng, chuyển trạng thái được phép và nguồn quyết định cuối. Các giới hạn đó cần đi theo dữ liệu qua giao dịch, bản sao, log và quy trình phục hồi, vì ở mỗi nơi chúng đều có thể ảnh hưởng đến quyền khôi phục tài khoản.