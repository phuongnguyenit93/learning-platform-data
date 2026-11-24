# Sequence number — Dùng số thứ tự để ngăn phát lại thông điệp

## 1. Sequence number là gì?

**Sequence number** (số thứ tự) là giá trị tăng dần hoặc duy nhất được gắn vào mỗi thông điệp trong một luồng giao tiếp. Bên nhận dùng nó để nhận biết thông điệp mới, thông điệp đến sai thứ tự và thông điệp đã được xử lý. Trong bảo mật xác thực, sequence number là một cách chống **replay attack**: attacker ghi lại một thông điệp hợp lệ rồi gửi lại để lặp thao tác hoặc giả mạo một lần xác thực mới.

Ví dụ: một ứng dụng nội bộ ký request bằng khóa riêng của client. Request đầu tiên mang sequence number 41, request tiếp theo mang 42. Server xác minh chữ ký và chỉ chấp nhận số thứ tự mới theo trạng thái đã lưu. Nếu attacker sao chép request 41 rồi gửi lại sau đó, server nhận ra số 41 đã được tiêu thụ và từ chối.

Trong chương **Chống replay** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, sequence number kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token và session. Người học cần hiểu cách gắn số thứ tự với đúng principal, credential, key, session và hướng truyền; bảo vệ tính toàn vẹn của thông điệp; xử lý đồng thời, mất gói và khởi động lại; từ đó ngăn replay trong các luồng xác thực và API.

**Sequence number không tự nó là một cơ chế bảo mật.** Attacker có thể sửa số thứ tự nếu nó không được bảo vệ bằng MAC, chữ ký số hoặc AEAD. Bên nhận cũng phải theo dõi trạng thái đã chấp nhận; nếu chỉ kiểm tra chữ ký mà không nhớ sequence number đã dùng, một thông điệp có chữ ký hợp lệ vẫn có thể bị phát lại.

## 2. Replay attack và tác động trong xác thực

Replay attack xảy ra khi attacker ghi lại một thông điệp hoặc bằng chứng xác thực hợp lệ rồi gửi lại sau đó. Attacker không nhất thiết phải biết mật khẩu hay khóa bí mật; họ chỉ cần sao chép được dữ liệu đã được chấp nhận.

Ví dụ trong hệ thống xác thực:

- Gửi lại request đổi mật khẩu đã được ký.
- Phát lại một OTP hoặc mã challenge-response đã dùng.
- Gửi lại API request tạo người dùng, chuyển tiền hoặc cấp quyền.
- Phát lại token exchange hoặc thông điệp đăng ký credential.
- Gửi lại thông điệp giữa hai service để kích hoạt hành động lần thứ hai.
- Phát lại một gói tin cũ trong một phiên giao thức đã xác thực.

Hậu quả phụ thuộc hành động: thao tác bị thực hiện hai lần, session được tạo ngoài ý muốn, quyền được cấp lại, trạng thái tài khoản bị thay đổi hoặc hệ thống xử lý một bằng chứng cũ như thể nó mới.

Replay khác với credential guessing. Guessing cố tìm bí mật; replay sử dụng lại dữ liệu hợp lệ đã quan sát được. Rate limit và mật khẩu mạnh giúp chống guessing, nhưng không thay thế cơ chế chống replay.

## 3. Sequence number giải quyết vấn đề nào?

Trong một luồng có thứ tự, bên gửi gắn số thứ tự vào từng thông điệp. Bên nhận kiểm tra số đó với trạng thái của luồng:

- Số mới hợp lệ: có thể chấp nhận và cập nhật trạng thái.
- Số đã được chấp nhận: phát hiện replay và từ chối hoặc trả kết quả đã lưu theo idempotency policy.
- Số nằm ngoài cửa sổ cho phép: từ chối vì quá cũ hoặc quá xa phía trước.
- Số không hợp lệ hoặc sai luồng: từ chối.

Sequence number giúp bên nhận phân biệt thông điệp mới với thông điệp cũ **nếu** số thứ tự được bảo vệ toàn vẹn và trạng thái chống replay được duy trì đáng tin cậy.

Nó không tự chứng minh ai gửi thông điệp. Danh tính và quyền kiểm soát khóa vẫn cần được xác minh bằng MAC, chữ ký, certificate, token hoặc một cơ chế mật mã phù hợp.

## 4. Các thuộc tính cần có của sequence number an toàn

Một thiết kế tốt cần các thuộc tính sau:

1. **Tính duy nhất trong phạm vi:** cùng một key/session/direction không dùng lại sequence number trong vòng đời được quy định.
2. **Tính toàn vẹn:** số thứ tự được bao phủ bởi MAC/chữ ký/AEAD cùng với nội dung và ngữ cảnh thông điệp.
3. **Phạm vi rõ ràng:** sequence number gắn với đúng principal, credential, key, session, tenant, giao thức và hướng truyền.
4. **Theo dõi phía nhận:** server lưu hoặc suy ra trạng thái đã chấp nhận để phát hiện số cũ.
5. **Cập nhật nguyên tử:** hai request đồng thời không thể cùng tiêu thụ một sequence number.
6. **Quản lý vòng đời:** reset, rekey, restart và failover không làm tái sử dụng số dưới cùng key.
7. **Chính sách thứ tự:** xác định có cho phép gói đến lệch thứ tự hay phải đúng thứ tự tuyệt đối.
8. **Xử lý lỗi:** mất gói, retry và response timeout không được khiến hệ thống chấp nhận replay.

Sequence number thường không cần bí mật. Giá trị quan trọng là nó không thể bị sửa mà không bị phát hiện và không bị tái sử dụng trong phạm vi key/session.

## 5. Ranh giới tin cậy và luồng xử lý

Trong một API được xác thực bằng chữ ký, client tạo request và ký cả sequence number lẫn nội dung. Server xác minh chữ ký, kiểm tra trạng thái sequence và chỉ sau đó mới thực hiện hành động:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as API server
    participant K as Key / credential registry
    participant D as Replay state store
    C->>C: Tăng sequence number
    C->>C: Ký method, path, body hash và sequence
    C->>S: Request + sequence + proof
    S->>K: Xác minh key thuộc client
    K-->>S: Key và trạng thái credential
    S->>S: Verify MAC/signature/AEAD
    S->>D: Kiểm tra và consume sequence nguyên tử
    D-->>S: Sequence mới hợp lệ
    S->>S: Kiểm tra authorization và thực hiện action
    S-->>C: Response
~~~

Thứ tự này có ý nghĩa: không thực hiện hành động trước khi xác minh tính toàn vẹn và chống replay. Đồng thời, việc consume sequence và commit hành động cần được phối hợp để tránh một request hợp lệ bị tiêu thụ số thứ tự nhưng không có kết quả rõ ràng.

Client không được tự khai sequence state đã được server chấp nhận. Replay state phải do server hoặc verifier có thẩm quyền quản lý.

## 6. Phạm vi sequence number: key, session, sender và direction

Không dùng một bộ đếm chung cho mọi người dùng hoặc mọi kết nối. Sequence number phải thuộc một phạm vi được xác định rõ, ví dụ:

| Phạm vi | Ý nghĩa |
| --- | --- |
| **Per key** | Mỗi credential/key có bộ đếm riêng. |
| **Per session** | Bộ đếm gắn với một phiên đã xác thực. |
| **Per sender** | Mỗi client/service có không gian số riêng. |
| **Per direction** | Client-to-server và server-to-client có bộ đếm độc lập. |
| **Per channel/stream** | Mỗi luồng giao tiếp có trạng thái thứ tự riêng. |
| **Per tenant** | Tách trạng thái theo tenant khi key hoặc session được phân vùng như vậy. |

Một khóa được dùng hai chiều cần sequence space độc lập hoặc quy tắc phối hợp rõ ràng. Nếu client và server cùng tăng một bộ đếm mà không đồng bộ, chúng có thể vô tình dùng trùng số. Nếu nhiều worker dùng chung một client key, cần bộ cấp số tập trung hoặc chia vùng số không giao nhau.

Khóa mới thường bắt đầu một sequence space mới. Trạng thái phải gắn với key identifier hoặc key epoch để sequence number 1 của key mới không bị nhầm là replay của key cũ, đồng thời số cũ dưới key cũ không được chấp nhận sau khi key đã revoke.

## 7. Bảo vệ sequence number bằng MAC, chữ ký hoặc AEAD

Sequence number không được để bên ngoài phần dữ liệu được xác thực. Nếu attacker có thể sửa số 41 thành 42 mà chữ ký chỉ bao phủ body, server có thể bị đánh lừa.

### MAC

Client và server chia sẻ khóa bí mật. MAC phải bao phủ sequence number và toàn bộ ngữ cảnh quan trọng:

~~~text
authenticated_data =
    protocol_version
    || key_id
    || session_id
    || direction
    || sequence_number
    || method
    || canonical_path
    || body_hash

tag = HMAC(key, authenticated_data)
~~~

Server tính lại MAC và so sánh bằng phép so sánh constant-time phù hợp. Không dùng MAC chỉ trên body nếu method, path, audience hoặc sequence number có thể bị thay đổi độc lập.

### Chữ ký số

Với public-key authentication, client ký dữ liệu canonical bao gồm sequence number. Server xác minh chữ ký bằng public key gắn với credential/client đã được tin cậy. Chữ ký hợp lệ vẫn chưa đủ: server phải kiểm tra sequence number chưa được chấp nhận và credential còn active.

### AEAD

Một giao thức mã hóa xác thực có thể đưa sequence number vào nonce, associated data hoặc cả hai theo đặc tả. Không tự thiết kế cách ghép nonce. Đặc biệt, không tái sử dụng cùng nonce dưới cùng khóa AEAD nếu thuật toán yêu cầu nonce duy nhất; việc tái sử dụng có thể làm lộ plaintext hoặc phá tính toàn vẹn.

Sequence number có thể được dùng để tạo nonce theo construction của giao thức, nhưng phải tuân thủ chính xác đặc tả và vòng đời key.

## 8. Monotonic counter và strict ordering

Trong mô hình đơn giản, bên nhận lưu sequence number cuối cùng đã chấp nhận, gọi là last accepted sequence. Một request mới chỉ hợp lệ nếu số của nó lớn hơn số đã lưu và thỏa giới hạn bước nhảy theo policy:

~~~text
if received_sequence <= last_accepted_sequence:
    reject_as_replay()
else:
    verify_and_accept()
    last_accepted_sequence = received_sequence
~~~

Mô hình này phù hợp khi giao thức yêu cầu thứ tự nghiêm ngặt và không có request đồng thời hoặc mất gói cần xử lý. Nó dễ hiểu, nhưng có một hạn chế: nếu request 12 đến trước request 11, server chấp nhận 12 rồi từ chối 11 dù 11 có thể là request hợp lệ chưa từng được nhận.

Với API hoặc mạng có nhiều request đồng thời, strict monotonic ordering có thể gây lỗi cho người dùng hợp lệ. Khi đó cần serialize request, dùng sequence cấp riêng cho từng luồng hoặc sử dụng sliding window.

## 9. Sliding replay window cho thông điệp đến lệch thứ tự

Một **sliding window** cho phép nhận các thông điệp đến lệch thứ tự trong một khoảng giới hạn, đồng thời nhớ số nào đã được chấp nhận.

Trạng thái thường gồm:

- H: sequence number lớn nhất đã chấp nhận.
- W: kích thước cửa sổ.
- Bitmap: đánh dấu các số trong cửa sổ đã được nhận.

Ví dụ cửa sổ W = 8 và H = 100:

~~~text
Sequence:  93 94 95 96 97 98 99 100
Accepted:   1  0  1  1  0  1  0   1
~~~

Trong ví dụ, 93, 95, 96, 98 và 100 đã được chấp nhận; 94, 97 và 99 chưa được nhận. Request 99 có thể được chấp nhận nếu bằng chứng hợp lệ. Request 95 phải bị từ chối vì bitmap cho biết số đó đã được tiêu thụ.

Quy tắc tổng quát:

- Nếu sequence lớn hơn H, dịch cửa sổ về phía trước, xóa các bit đã rơi khỏi cửa sổ và đánh dấu số mới.
- Nếu sequence nằm trong [H - W + 1, H], kiểm tra bit tương ứng; bit đã bật nghĩa là replay.
- Nếu sequence nhỏ hơn cửa sổ, từ chối vì quá cũ.
- Nếu sequence vượt quá bước nhảy tối đa cho phép, từ chối hoặc yêu cầu resynchronization theo protocol.

Sliding window phù hợp với giao thức cho phép reorder. Nó cần được cập nhật nguyên tử để hai bản sao cùng sequence không cùng được chấp nhận.

## 10. Mã giả: kiểm tra sliding window

Mã giả minh họa cách xử lý sau khi đã xác minh MAC/chữ ký của thông điệp:

~~~text
acceptSequence(state, seq):
    lock(state.scope)

    if seq > state.highest:
        delta = seq - state.highest

        if delta > state.maxForwardJump:
            unlock(state.scope)
            return reject("sequence jump too large")

        state.bitmap = shiftWindowLeftBy(delta, state.bitmap)
        state.bitmap = setNewestBit(state.bitmap)
        state.highest = seq
        persistAtomically(state)
        unlock(state.scope)
        return accept

    distance = state.highest - seq

    if distance >= state.windowSize:
        unlock(state.scope)
        return reject("too old")

    if bitIsSet(state.bitmap, distance):
        unlock(state.scope)
        return reject("replay")

    state.bitmap = setBit(state.bitmap, distance)
    persistAtomically(state)
    unlock(state.scope)
    return accept
~~~

Đây là mô hình khái niệm. Cần thống nhất quy ước bit direction, xử lý sequence ban đầu, giới hạn số nguyên, lock/transaction và cách persist. Không sao chép mã giả thành thư viện production nếu chưa kiểm thử overflow, race condition, crash recovery và concurrent duplicate.

## 11. Cập nhật replay state phải nguyên tử

Giả sử attacker gửi cùng request có sequence 77 hai lần gần như đồng thời. Nếu hai worker cùng đọc trạng thái “77 chưa dùng” trước khi một worker ghi lại, cả hai có thể cùng thực hiện hành động.

Trình tự không an toàn:

1. Worker A đọc bitmap, thấy sequence chưa dùng.
2. Worker B đọc cùng bitmap, cũng thấy sequence chưa dùng.
3. A chấp nhận và thực hiện action.
4. B chấp nhận theo dữ liệu cũ và thực hiện action lần thứ hai.

Các cách xử lý:

- Database transaction với row lock hoặc compare-and-swap.
- Atomic script/operation trong replay-state store.
- Unique constraint trên (key/session scope, sequence number) nếu mô hình lưu từng sequence.
- Idempotent state transition và transaction ID cho action.
- Serialize request theo key/session nếu thông lượng cho phép.

Việc xác minh chữ ký có thể thực hiện trước lock để giảm thời gian giữ lock, nhưng thao tác kiểm tra và tiêu thụ sequence phải nguyên tử. Chỉ sau khi consume thành công request mới được phép thực hiện action tương ứng.

## 12. Persistence, restart và failover

Nếu server chỉ giữ sequence state trong RAM, restart có thể làm mất thông tin đã nhận. Attacker có thể phát lại một request cũ sau khi node khởi động lại và server tưởng đó là request mới.

Thiết kế cần quyết định:

- Replay state được lưu bền vững ở đâu?
- Khi process restart, state có được khôi phục trước khi nhận traffic không?
- Khi failover sang node khác, node mới có cùng trạng thái không?
- Nếu state store không khả dụng, request nhạy cảm bị từ chối hay xử lý theo cơ chế an toàn nào?
- Backup/restore có thể làm lùi sequence state không?
- Replication có độ trễ khiến hai node cùng chấp nhận một sequence không?

Với xác thực hoặc hành động nhạy cảm, không được fail open bằng cách bỏ kiểm tra replay khi state store lỗi. Có thể tạm từ chối, yêu cầu tạo session/key mới hoặc dùng cơ chế dự phòng đã được thiết kế.

### Không khôi phục replay state từ snapshot cũ một cách mù quáng

Nếu backup được khôi phục về thời điểm trước khi sequence 500 được chấp nhận, request 500 có thể được phát lại. Cần monotonic security epoch, durable log, replicated state hoặc buộc rekey/session rotation sau disaster recovery để không tái sử dụng không gian sequence cũ.

## 13. Reset counter, rekey và epoch

Sequence number hữu hạn và có thể cạn. Một số giao thức dùng counter 32-bit hoặc 64-bit; không được để nó wrap về 0 dưới cùng key nếu điều đó làm số cũ trở nên hợp lệ lại.

Khi cần reset:

1. Kết thúc hoặc đình chỉ luồng/key hiện tại.
2. Thiết lập key mới bằng quy trình rekey đã xác thực.
3. Gắn key mới với key ID hoặc epoch mới.
4. Khởi tạo replay state mới cho key/epoch đó.
5. Từ chối thông điệp của key cũ sau thời điểm chuyển đổi theo policy.
6. Audit thời điểm và lý do rekey.

Epoch giúp phân biệt các vòng đời key/session. Tuy nhiên, epoch cũng phải được xác thực mật mã và quản lý đơn điệu; nếu client tự gửi epoch tùy ý, attacker có thể ép server reset replay window.

Không chấp nhận sequence number quay về giá trị thấp hơn chỉ vì client khởi động lại. Client phải thực hiện resynchronization/rekey có xác thực hoặc dùng counter bền vững.

## 14. Sequence number trong request API đã ký

Một request API có thể mang:

| Thành phần | Mục đích |
| --- | --- |
| key_id | Chọn credential đã đăng ký, không phải bí mật. |
| sequence_number | Phát hiện request cũ hoặc trùng. |
| timestamp | Giới hạn độ mới theo thời gian. |
| method/path | Ràng buộc request vào thao tác và endpoint. |
| body_hash | Ràng buộc nội dung payload. |
| audience/host | Ngăn request bị chuyển sang service khác. |
| session/epoch | Ràng buộc đúng phiên hoặc vòng đời khóa. |
| MAC/signature | Bảo vệ toàn bộ dữ liệu canonical. |

Ví dụ cấu trúc logic:

~~~text
canonical_request =
    protocol_version
    || key_id
    || session_id
    || sequence_number
    || timestamp
    || HTTP_method
    || canonical_path_and_query
    || audience
    || SHA256(body)

proof = Sign(private_key, canonical_request)
~~~

Server xác minh credential, chữ ký, timestamp, audience, session và sequence state trước khi xử lý. Canonicalization phải được đặc tả chính xác để client và server tạo cùng chuỗi; nếu path, query hoặc body được chuẩn hóa khác nhau, có thể phát sinh lỗi xác minh hoặc lỗ hổng ký một request nhưng thực hiện request khác.

Sequence number chống replay trong phạm vi đã định. Timestamp giới hạn độ cũ; nonce có thể cung cấp tính duy nhất cho từng request. Các cơ chế này bổ sung cho nhau và không nên thay thế lẫn nhau một cách tùy tiện.

## 15. Sequence number và idempotency key là hai mục đích khác nhau

Sequence number chống chấp nhận lại một thông điệp trong cùng không gian thứ tự. **Idempotency key** giúp một thao tác nghiệp vụ có thể được retry mà không tạo tác động lặp ngoài ý muốn.

Ví dụ: client gửi request tạo giao dịch với sequence 51. Server đã consume sequence và commit giao dịch, nhưng response bị mất trên mạng. Client retry:

- Nếu gửi lại đúng sequence 51, replay defense có thể từ chối.
- Nếu client tăng lên 52, server có thể coi đó là một thao tác tạo giao dịch mới và tạo bản ghi trùng.
- Nếu request có idempotency key gắn với thao tác nghiệp vụ, server có thể trả lại kết quả đã commit thay vì tạo giao dịch thứ hai.

Do đó:

- Sequence number xác định tính mới của thông điệp trong luồng bảo mật.
- Idempotency key xác định một thao tác nghiệp vụ duy nhất qua nhiều lần retry.
- Cần lưu kết quả idempotency theo principal/client và phạm vi action.
- Không dùng idempotency key thay cho MAC/chữ ký hoặc replay state.
- Không dùng sequence number như idempotency key chung cho nhiều endpoint.

## 16. Timestamp, nonce và sequence number

| Cơ chế | Cách chống replay | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Timestamp** | Chỉ chấp nhận thông điệp trong cửa sổ thời gian. | Dễ kiểm tra độ mới, không cần counter liên tục. | Một thông điệp vẫn có thể bị replay nhiều lần trong cửa sổ nếu không lưu trạng thái. |
| **Nonce** | Yêu cầu giá trị ngẫu nhiên duy nhất và ghi nhận nonce đã dùng. | Không cần thứ tự; phù hợp challenge/request riêng lẻ. | Cần lưu nonce đã tiêu thụ trong thời gian hiệu lực và chống trùng. |
| **Sequence number** | Kiểm tra số thứ tự mới theo trạng thái sender/session. | Phát hiện replay và hỗ trợ phát hiện reorder/gap. | Cần quản lý counter, state bền vững và đồng bộ concurrency. |
| **Challenge-response** | Server tạo challenge mới; client chứng minh sở hữu credential. | Gắn bằng chứng với một lần xác thực cụ thể. | Challenge phải có entropy, expiry, purpose và one-time consumption. |

Có thể kết hợp timestamp + nonce hoặc timestamp + sequence number. Timestamp giúp giới hạn độ cũ; sequence/nonce giúp phát hiện trùng trong cửa sổ. Challenge-response phù hợp cho đăng nhập tương tác; sequence number thường hữu ích cho luồng thông điệp liên tục hoặc API ký request.

## 17. Sequence number không thay thế TLS hoặc token validation

TLS cung cấp bảo vệ kênh như mã hóa, integrity và một số cơ chế chống replay ở cấp giao thức. Nhưng ứng dụng vẫn cần hiểu threat model của request nghiệp vụ:

- TLS không ngăn client hợp lệ gửi lại cùng một thao tác nghiệp vụ qua kết nối mới.
- Token hợp lệ có thể bị sử dụng nhiều lần trong thời hạn nếu là bearer token và resource server cho phép.
- Sequence number ở tầng ứng dụng không thay thế kiểm tra chữ ký token, issuer, audience, expiry và scope.
- Nếu TLS kết thúc tại proxy, cần bảo vệ kênh proxy-to-backend và metadata được chuyển tiếp.
- Replay state ở tầng ứng dụng cần được ràng buộc với credential/session, không chỉ với TCP connection.

Không suy ra rằng một request không thể replay chỉ vì nó đi qua HTTPS. HTTPS bảo vệ đường truyền; chống lặp một hành động cần semantics và trạng thái ở tầng ứng dụng hoặc giao thức phù hợp.

## 18. Ví dụ trong giao thức và hệ thống xác thực

### IPsec ESP

ESP có sequence number trong header để hỗ trợ phát hiện replay. Receiver có thể dùng anti-replay window và xác minh integrity/authentication trước khi chấp nhận gói. Sequence number gắn với Security Association; khi rekey tạo SA mới, trạng thái sequence và key phải được quản lý theo vòng đời SA.

### Giao thức ký request giữa service

Một service dùng client certificate hoặc private key ký method, path, body hash và sequence number. API gateway xác minh certificate/key, chữ ký và trạng thái sequence trước khi chuyển request vào business service. Nếu nhiều instance gateway chia sẻ một client key, replay state phải nhất quán giữa các instance.

### Đăng nhập tương tác

Trong login challenge-response, server tạo challenge ngẫu nhiên dùng một lần và gắn với session đăng nhập. Đây không nhất thiết là sequence number tăng dần, nhưng cùng mục tiêu là đảm bảo bằng chứng chỉ hợp lệ cho đúng giao dịch và không được dùng lại.

### TCP sequence number

TCP có sequence number để đánh số byte, xử lý thứ tự và retransmission. Tuy nhiên, TCP sequence number không phải một cơ chế xác thực mật mã của ứng dụng và không thay thế MAC/chữ ký, TLS hoặc replay defense ở tầng nghiệp vụ. Không nên dùng TCP sequence number để quyết định một request đăng nhập hoặc giao dịch có được phép thực hiện lại hay không.

## 19. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Sequence number không nằm trong MAC/chữ ký | Attacker sửa số để vượt kiểm tra. | Ký/MAC toàn bộ ngữ cảnh và sequence. |
| Chỉ xác minh chữ ký, không lưu replay state | Chữ ký hợp lệ bị phát lại nhiều lần. | Theo dõi và consume sequence/nonce. |
| Dùng một counter chung cho nhiều client | Va chạm, từ chối nhầm hoặc bỏ lọt replay. | Scope theo key/session/sender/direction. |
| Reset counter sau restart dưới cùng key | Request cũ có thể được chấp nhận lại. | Durable counter, epoch hoặc rekey. |
| Cập nhật replay state không nguyên tử | Hai bản sao cùng được chấp nhận. | Atomic consume/transaction/CAS. |
| Strict ordering khi có request song song | Request hợp lệ đến lệch thứ tự bị từ chối. | Serialize hoặc sliding window. |
| Sliding window quá rộng | Replay cũ còn được chấp nhận lâu hơn cần thiết. | Chọn window theo latency/reorder và threat model. |
| Không giới hạn forward jump | Attacker có thể đẩy H quá xa, làm request hợp lệ bị loại. | Max forward jump và resynchronization có xác thực. |
| Cho phép wraparound | Số cũ có thể hợp lệ lại. | Rekey trước khi cạn counter. |
| Chỉ dựa vào timestamp | Replay lặp lại trong cửa sổ thời gian. | Kết hợp nonce/sequence state. |
| Dùng sequence làm idempotency key | Retry tạo duplicate hoặc bị từ chối sai. | Quản lý idempotency riêng. |
| Cache trạng thái cũ trên nhiều node | Node stale chấp nhận replay. | Replication/invalidation và consistency policy. |

## 20. Mã giả: xác minh request ký có sequence number

Mã giả dưới đây thể hiện thứ tự xử lý ở mức khái niệm:

~~~text
handleSignedRequest(request):
    credential = lookupCredential(request.keyId)
    require credential exists and credential.status == "active"
    require request.audience == thisService
    require request.sessionId belongsTo credential.principal
    require request.timestamp withinAllowedWindow

    canonical = canonicalize(
        version,
        keyId,
        sessionId,
        direction,
        sequenceNumber,
        timestamp,
        method,
        pathAndQuery,
        audience,
        hash(request.body)
    )

    require verifyProof(credential.publicKey, canonical, request.proof)

    replayResult = atomicallyCheckAndConsume(
        scope = credential.keyId + sessionId + direction,
        sequence = request.sequenceNumber
    )
    require replayResult == "new"

    require currentAccountAndTenantPolicyAllows(credential.principal)
    require authorizationAllows(credential.principal, request.action)

    return executeWithIdempotencyPolicy(request)
~~~

Trong hệ thống thật, cần xác định thứ tự giữa consume sequence và business transaction. Nếu consume trước rồi business commit thất bại, retry cùng sequence sẽ bị coi là replay. Có thể dùng idempotency record, transaction/outbox hoặc trả trạng thái có thể truy vấn để client biết kết quả. Không được bỏ chống replay chỉ để retry dễ hơn.

## 21. Tình huống thực tế: request đổi MFA bị phát lại

Một ứng dụng quản lý tài khoản cho phép client ký request đổi phương thức MFA. Request gồm principal, action, phương thức mới và chữ ký. Ban đầu, server xác minh chữ ký và thực hiện thay đổi, nhưng không kiểm tra request ID hoặc sequence.

Attacker ghi lại request đã ký qua một thiết bị bị xâm nhập hoặc log không được bảo vệ. Sau đó họ gửi lại request:

- Nếu request vẫn hợp lệ, server có thể thực hiện lại thao tác.
- Nếu endpoint có tác dụng phụ như gửi thông báo, tạo credential hoặc reset recovery state, tác động có thể lặp.
- Nếu request được dùng ở một context khác mà chữ ký không bao phủ audience/session/path, có thể bị chuyển sang endpoint khác.

### Thiết kế phòng thủ

1. Client gắn sequence number riêng cho key/session.
2. Chữ ký bao phủ sequence, method, canonical path, audience, body hash và session context.
3. Server xác minh credential còn active và chữ ký hợp lệ.
4. Server atomically consume sequence trong replay state.
5. Server kiểm tra step-up/authorization và thực hiện thay đổi.
6. Gắn idempotency key với thao tác đổi MFA để retry trả kết quả đã commit, không tạo thay đổi lặp.
7. Ghi audit metadata và thông báo tới kênh đã xác minh.

Nếu attacker phát lại request cũ, sequence đã tiêu thụ nên bị từ chối. Nếu client gửi lại do timeout, idempotency record giúp xác định kết quả của cùng thao tác nghiệp vụ.

## 22. Kiểm thử sequence number và replay protection

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Sequence mới, MAC/chữ ký hợp lệ | Chấp nhận và cập nhật replay state. |
| Sequence đã được chấp nhận | Từ chối replay hoặc trả kết quả idempotent đã lưu theo policy. |
| Sequence cũ ngoài cửa sổ | Từ chối. |
| Sequence đến lệch thứ tự trong window | Chấp nhận nếu chưa dùng và bằng chứng hợp lệ. |
| Sequence bị sửa nhưng body giữ nguyên | MAC/chữ ký thất bại. |
| Body/path/audience bị sửa | Proof thất bại do canonical request không khớp. |
| Hai request cùng sequence đồng thời | Chỉ một request consume thành công. |
| Client restart | Không tái sử dụng sequence dưới cùng key; resync/rekey theo protocol. |
| Server restart | Replay state được khôi phục hoặc key/session cũ bị vô hiệu hóa an toàn. |
| Failover sang node khác | Node mới dùng trạng thái đủ mới; không chấp nhận duplicate. |
| Sequence gần giới hạn tối đa | Thực hiện rekey trước wraparound. |
| Sequence nhảy quá xa | Từ chối hoặc resync có xác thực. |
| Credential suspended/revoked | Từ chối dù sequence mới và chữ ký đúng. |
| Timestamp hợp lệ nhưng sequence lặp | Từ chối replay. |
| Idempotency retry sau response timeout | Trả kết quả của thao tác đã commit, không thực hiện tác dụng phụ lần hai. |
| Replay state store lỗi | Không bỏ kiểm tra replay cho hành động nhạy cảm. |
| Hai hướng truyền dùng chung key | Sequence space tách biệt hoặc được phối hợp không trùng. |
| Key rotation/epoch mới | State mới được khởi tạo; key cũ bị xử lý theo policy. |

### Kiểm thử hiệu năng và vận hành

- Đo độ trễ của atomic replay-state update.
- Kiểm tra contention khi một key/session có nhiều request đồng thời.
- Kiểm tra dung lượng lưu replay window và thời gian retention.
- Kiểm tra propagation delay khi cập nhật state giữa nhiều node.
- Đo false rejection do request reorder hoặc clock skew.
- Kiểm tra recovery sau crash, backup restore và disaster recovery.
- Xác minh log không chứa secret, private key, token hoặc nội dung nhạy cảm.

## 23. Checklist thiết kế sequence number

- [ ] Xác định threat replay và thông điệp/hành động cần bảo vệ.
- [ ] Scope sequence theo key, principal, session, sender, direction và epoch.
- [ ] Chọn độ rộng counter đủ dùng và có kế hoạch rekey trước wraparound.
- [ ] Bao phủ sequence number cùng method/path/body hash/audience/session trong MAC/chữ ký/AEAD.
- [ ] Xác minh credential và trạng thái active trước khi chấp nhận.
- [ ] Lưu replay state authoritative và cập nhật nguyên tử.
- [ ] Chọn strict ordering hoặc sliding window theo yêu cầu reorder/concurrency.
- [ ] Đặt giới hạn forward jump và xử lý resynchronization có xác thực.
- [ ] Không reset counter dưới cùng key sau restart/restore.
- [ ] Có epoch/key ID để quản lý rekey và vòng đời sequence space.
- [ ] Xử lý retry bằng idempotency riêng; không nhầm idempotency với replay defense.
- [ ] Định nghĩa hành vi khi replay-state store/cache/replication lỗi.
- [ ] Kiểm tra cả request mới và session/token đã được tạo từ credential.
- [ ] Kiểm thử duplicate, out-of-order, race, restart, failover và wraparound.
- [ ] Audit outcome và correlation ID nhưng không ghi secret hoặc token thô.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao sequence number phải nằm trong dữ liệu được ký hoặc MAC?

**Gợi ý:** Nếu không được bảo vệ toàn vẹn, attacker có thể sửa số thứ tự để làm thông điệp cũ trông như mới.

**Câu 2.** Vì sao chỉ xác minh chữ ký là chưa đủ để chống replay?

**Gợi ý:** Một thông điệp cũ vẫn có chữ ký hợp lệ. Server phải theo dõi sequence/nonce đã được chấp nhận.

**Câu 3.** Strict monotonic counter có hạn chế gì khi request đến sai thứ tự?

**Gợi ý:** Khi số lớn hơn đến trước, số nhỏ hơn hợp lệ có thể bị từ chối; sliding window hoặc serialize request có thể phù hợp hơn.

**Câu 4.** Vì sao replay state cần được lưu bền vững qua restart?

**Gợi ý:** Nếu state mất, request cũ có thể được chấp nhận lại. Cần durable state, epoch hoặc rekey trước khi phục vụ traffic.

**Câu 5.** Sequence number và idempotency key khác nhau thế nào?

**Gợi ý:** Sequence chống phát lại thông điệp trong luồng bảo mật; idempotency key ngăn một thao tác nghiệp vụ bị thực hiện nhiều lần khi retry.

**Câu 6.** Vì sao hai request đồng thời cùng sequence phải chỉ có một request được chấp nhận?

**Gợi ý:** Nếu check và update không nguyên tử, cả hai worker có thể đọc trạng thái cũ và cùng thực hiện hành động.

**Câu 7.** Khi counter sắp wraparound, có thể đặt lại về 0 dưới cùng key không?

**Gợi ý:** Không nếu số cũ có thể trở nên hợp lệ lại. Cần rekey/epoch mới và từ chối key cũ theo policy.

## 25. Ghi nhớ

**Sequence number chống replay bằng cách gắn mỗi thông điệp với một vị trí trong luồng và để bên nhận ghi nhớ những số đã chấp nhận.** Cơ chế chỉ an toàn khi sequence được bảo vệ bằng MAC/chữ ký/AEAD, được scope đúng theo key/session/sender/direction, và replay state được cập nhật nguyên tử, bền vững qua restart và failover. Strict ordering phù hợp với luồng tuần tự; sliding window xử lý thông điệp đến lệch thứ tự. Counter cần epoch/rekey trước wraparound; timestamp và nonce có thể bổ sung nhưng không thay thế tùy tiện. Sequence number cũng khác idempotency key: một cơ chế ngăn phát lại thông điệp, cơ chế kia giúp retry thao tác nghiệp vụ không tạo tác động lặp.
