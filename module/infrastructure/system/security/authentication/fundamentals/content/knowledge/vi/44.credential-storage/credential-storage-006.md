# Credential trong memory

**Credential trong memory** là bí mật hoặc bằng chứng xác thực đang được nạp vào bộ nhớ của một tiến trình để ứng dụng có thể xử lý, xác minh, ký, giải mã hoặc gửi request. Chúng có thể gồm password vừa nhập, access token, refresh token, session cookie, API key, client secret, TOTP seed, private key, recovery code hoặc khóa dẫn xuất. Dữ liệu có thể chỉ tồn tại trong thời gian ngắn, nhưng trong khoảng đó nó có thể xuất hiện ở heap, stack, native buffer, thư viện TLS, runtime, log hoặc bản sao do hệ điều hành tạo ra.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu nguyên lý xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, identity linking và account recovery. Quản lý credential trong memory là một phần của vòng đời xác thực: ứng dụng cần đưa bí mật vào đúng thành phần, dùng đúng mục đích, giới hạn thời gian tồn tại, tránh sao chép không cần thiết và loại bỏ dữ liệu nhạy cảm ở nơi ứng dụng kiểm soát được.

Điểm cốt lõi: **mã hóa khi lưu trữ không bảo vệ bí mật khỏi một tiến trình đã được phép giải mã và đang sử dụng nó**. Keychain, Keystore, secret manager hoặc KMS giúp bảo vệ credential khi nghỉ và kiểm soát việc sử dụng; khi secret được nạp vào process, vẫn cần sandbox, least privilege, bảo vệ memory, kiểm soát debugger/dump, redaction và thiết kế giảm thời gian phơi lộ.

## 1. Credential trong memory là gì?

Credential là dữ liệu hoặc vật thể mật mã dùng để chứng minh danh tính hay quyền kiểm soát. Khi ứng dụng thực hiện authentication, credential thường phải đi qua một số vùng memory để được đọc, biến đổi hoặc gửi tới thành phần khác.

Ví dụ:
- Người dùng nhập password vào form; UI framework và ứng dụng giữ nội dung trong memory trước khi gửi qua TLS.
- API client đọc access token từ secure storage rồi đặt vào Authorization header.
- Backend lấy client secret để xác thực với token endpoint.
- Service dùng private key để ký client assertion hoặc ký request.
- Authenticator đọc TOTP seed để tạo mã một lần.
- TLS library dùng traffic key trong quá trình mã hóa dữ liệu.
- Ứng dụng giải mã refresh token hoặc khóa dữ liệu local để thực hiện thao tác.

Credential có thể là plaintext, ciphertext, key handle hoặc reference. Certificate công khai thường không cần bí mật; private key tương ứng thì phải được bảo vệ.

### 1.1. Phân biệt secret, identifier và key handle

| Loại dữ liệu | Ví dụ | Có cần giữ bí mật? |
| --- | --- | --- |
| **Secret credential** | Password, API key, client secret, TOTP seed, bearer token. | Có. Ai lấy được có thể xác thực hoặc truy cập. |
| **Private key** | Khóa ký client assertion, khóa mTLS. | Có. Cần bảo vệ quyền sử dụng và khả năng export. |
| **Public key/certificate** | Public key, certificate chain. | Thường không cần bí mật; cần bảo vệ tính toàn vẹn và nguồn gốc. |
| **Identifier** | Client ID, key ID, certificate serial, account ID. | Thường không phải secret; vẫn có thể nhạy cảm về quyền riêng tư. |
| **Key handle/reference** | Handle của Keychain, Keystore, HSM hoặc KMS. | Không nhất thiết là secret độc lập; phải kiểm soát quyền truy cập. |
| **Derived key** | Khóa dẫn xuất từ password hoặc master key. | Có. Cần giới hạn scope, thời gian và nơi sử dụng. |

Key handle không làm lộ private key nếu hệ thống bảo đảm thao tác diễn ra trong keystore. Tuy nhiên, tiến trình có handle vẫn có thể yêu cầu ký hoặc giải mã nếu policy cho phép. Cần kiểm tra quyền sử dụng, caller identity và user-presence requirement, không chỉ kiểm tra key có export được hay không.

### 1.2. Memory exposure window

Khoảng thời gian secret tồn tại trong memory được gọi là exposure window. Càng nhiều bản sao và càng lâu tồn tại, cơ hội bị lộ càng lớn.

Một luồng password có thể đi qua:
1. Keyboard/IME hoặc password manager.
2. UI component và application object.
3. Serialization/request buffer.
4. TLS library và socket buffer.
5. Server request parser.
6. Authentication service và password verifier.
7. Log/error/telemetry nếu xử lý sai.

Không phải mọi tầng đều giữ một bản sao rõ ràng; chi tiết phụ thuộc platform và runtime. Mục tiêu là giảm các lần copy, tránh lưu trữ ngoài ý muốn và xóa dữ liệu ở nơi ứng dụng kiểm soát được.

## 2. Vì sao memory là ranh giới bảo mật?

Khi credential được nạp vào memory, biện pháp at-rest không còn là lớp duy nhất. Attacker có thể nhắm vào process, runtime, thiết bị hoặc quyền quản trị hệ điều hành.

Các đường phơi lộ thường gặp:
- Process memory read bởi debugger, malware hoặc process có quyền cao.
- Core dump, crash dump, heap dump hoặc diagnostic snapshot.
- Log, trace, exception, analytics và telemetry.
- Swap, hibernation image hoặc pagefile không được bảo vệ.
- Memory disclosure do buffer overflow, use-after-free hoặc out-of-bounds read.
- Runtime instrumentation, dynamic hooking hoặc code injection.
- Plugin hoặc thư viện bên thứ ba có quyền chạy trong cùng process.
- Backup hoặc snapshot máy ảo chứa memory state.
- Side-channel hoặc timing behavior tiết lộ thông tin gián tiếp.

Không phải mọi threat model đều cần chống attacker có quyền root/kernel hoặc hypervisor. Hãy xác định attacker, quyền họ có, dữ liệu cần bảo vệ và thời gian credential có giá trị trước khi chọn biện pháp.

## 3. Các vùng memory có thể chứa credential

Một ứng dụng không chỉ có một vùng nhớ duy nhất. Secret có thể đi qua nhiều loại storage trong process và hệ thống.

### 3.1. Stack và heap

- **Stack** thường chứa biến cục bộ, tham số, địa chỉ trả về và dữ liệu tạm của lời gọi hàm. Secret được truyền qua nhiều hàm có thể xuất hiện trong stack frame hoặc register.
- **Heap** thường chứa object có vòng đời động như String, byte array, request object, token model hoặc buffer. Runtime có thể di chuyển hoặc thu gom object theo cơ chế riêng.

Đặt secret trên stack không tự động an toàn hơn heap. Cả hai đều có thể xuất hiện trong dump hoặc bị đọc bởi attacker đủ quyền.

### 3.2. Native memory và thư viện hệ thống

Ứng dụng Java, Kotlin, Swift hoặc JavaScript có thể gọi native code. TLS, compression, crypto provider, database driver và hệ điều hành có thể cấp buffer riêng. Xóa object cấp ứng dụng không bảo đảm bản sao trong native library đã bị xóa.

Khi đánh giá đường đi của credential, cần xem cả managed object, runtime heap, JNI/FFI bridge, native allocation, TLS/socket buffer, crypto provider và IPC message.

### 3.3. Register, cache và bản sao tạm

Compiler và CPU có thể giữ giá trị trong register hoặc cache. Runtime có thể tạo bản sao khi chuyển kiểu, concatenate, encode/decode, serialize hoặc tối ưu hóa. Ứng dụng thường không kiểm soát trực tiếp mọi bản sao này.

Zeroization chỉ có thể nhắm tới vùng memory cụ thể mà ứng dụng kiểm soát. Không nên hứa rằng một lệnh xóa mảng sẽ xóa mọi dấu vết secret khỏi toàn bộ máy.

## 4. Vòng đời credential trong memory

Một vòng đời an toàn thường có các bước rõ ràng:

    Receive
       |
       v
    Validate input and context
       |
       v
    Load or derive credential
       |
       v
    Use for one intended operation
       |
       v
    Clear controlled buffers / release references
       |
       v
    Avoid logging, dumping or caching secret

### 4.1. Receive

Chỉ nhận credential qua kênh và thành phần phù hợp. Password đi qua form bảo vệ bằng TLS; API token lấy từ secure storage hoặc token provider; private key nên được gọi qua handle nếu có thể.

Không nhận secret từ URL query/fragment, command-line argument, log/ticket/chat, analytics hoặc file tạm không có kiểm soát.

### 4.2. Validate

Kiểm tra format, kích thước, audience, scope, expiry hoặc transaction context theo loại credential. Tránh parse không giới hạn vì input lớn có thể làm cạn memory. Không copy secret vào exception message để giúp debug.

### 4.3. Use

Chỉ dùng credential cho mục đích cần thiết. Access token chỉ được gửi tới resource server có audience phù hợp; private key chỉ ký đúng assertion/challenge; TOTP seed chỉ tạo mã cho account đã gắn.

Giới hạn phạm vi hàm, module và thread được phép truy cập secret. Tránh đưa secret vào global singleton hoặc object sống suốt vòng đời ứng dụng nếu thao tác chỉ cần dùng trong một request.

### 4.4. Clear and release

Sau khi dùng:
- Xóa hoặc ghi đè buffer có thể sửa được khi có API phù hợp.
- Giải phóng native buffer theo thư viện đã được đánh giá.
- Xóa field hoặc reference không cần thiết.
- Không đưa secret vào cache, closure, retry queue hoặc background task ngoài ý muốn.
- Không tái sử dụng buffer đã chứa secret cho dữ liệu ít tin cậy nếu chưa xử lý an toàn.
- Kiểm tra mọi nhánh lỗi và cancellation để cleanup vẫn diễn ra.

Đặt reference thành null chỉ giảm khả năng truy cập qua reference đó; nó không ghi đè nội dung memory và không bảo đảm garbage collector thu hồi ngay.

## 5. Managed runtime và giới hạn của garbage collector

Java, Kotlin/JVM, C#, Swift và JavaScript có runtime quản lý memory theo những mô hình khác nhau. Garbage collector hoặc ARC giúp quản lý vòng đời object, nhưng không bảo đảm secret biến mất ngay khi ứng dụng không còn dùng.

### 5.1. Immutable string

Trong Java, String là immutable. Sau khi tạo, ứng dụng không thể ghi đè nội dung String qua API thông thường. Nếu password được tạo thành String, nó có thể tồn tại cho tới khi object được thu gom và vùng memory được tái sử dụng. Việc gán biến sang null không xóa nội dung.

String cũng có thể được copy hoặc giữ bởi UI framework, data binding, logging/formatting, exception message, serialization, debugger và heap dump.

Với secret có thể xử lý bằng buffer mutable, cân nhắc byte array hoặc char array và giảm chuyển đổi sang String. Điều này không loại bỏ mọi bản sao do framework, provider hoặc runtime tạo ra.

### 5.2. Garbage collection không phải secure erase

Garbage collector có thể thu gom object ở thời điểm không xác định, di chuyển object trong compacting GC, giữ object lâu hơn dự kiến do reference còn tồn tại hoặc tạo bản sao trong quá trình resize/copy.

Không dùng “object đã hết scope” làm cam kết secret đã bị xóa. Hãy thiết kế để secret ít được tạo, ít được copy và có thời gian sử dụng ngắn.

### 5.3. Java và Kotlin/JVM

Một số thực hành:
- Tránh chuyển password/token sang String nếu API có thể nhận byte[] hoặc char[].
- Dùng buffer mutable và xóa trong finally khi thao tác kết thúc.
- Tránh giữ credential trong data class, immutable collection, UI state hoặc global cache.
- Không đưa secret vào toString(), exception hoặc structured log.
- Hạn chế heap dump production và bảo vệ dump như dữ liệu nhạy cảm.
- Ưu tiên key handle của Android Keystore/HSM thay vì export private key.
- Xem xét các bản sao do provider/JCA, JNI và HTTP client tạo.

Ví dụ minh họa:

    char[] password = readPasswordIntoMutableBuffer();
    try {
        authenticate(password);
    } finally {
        Arrays.fill(password, '\0');
    }

Đây là biện pháp giảm thời gian lộ của buffer mà ứng dụng sở hữu. Nó không chứng minh UI framework, encoder, network stack hoặc authentication library không còn bản sao.

### 5.4. Native code

Trong C/C++, compiler có thể loại bỏ một thao tác memset nếu thấy nội dung không còn được sử dụng. Dùng primitive secure-zero của platform hoặc thư viện mật mã được kiểm chứng, chẳng hạn explicit_bzero, SecureZeroMemory hoặc hàm tương đương phù hợp môi trường.

Nguyên tắc:
- Xóa đúng length của vùng đã cấp phát.
- Không dùng pointer sau khi free.
- Không giả định xóa một struct sẽ xóa các bản sao ở nơi khác.
- Kiểm tra ownership và lifetime của buffer.
- Dùng RAII/cleanup path để xử lý cả exception/error.
- Tránh trả pointer tới secret ra ngoài phạm vi cần thiết.

Ngay cả secure-zero primitive cũng chỉ xử lý vùng memory được chỉ định. Nó không xóa register, bản sao của thư viện hoặc dump đã được tạo trước đó.

## 6. Password trong memory

Password là credential có giá trị cao và thường được người dùng tái sử dụng. Khi người dùng nhập password, ứng dụng cần giảm thời gian nó tồn tại và tránh biến password thành dữ liệu lâu dài.

### 6.1. Phía client

- Dùng password field phù hợp và TLS.
- Không log giá trị input hoặc request body chứa password.
- Không đưa password vào URL, analytics, crash report hoặc clipboard ngoài ý muốn.
- Tránh lưu password trong local database hoặc preference.
- Xóa UI field và buffer theo khả năng của framework sau khi submit.
- Không giữ password trong state toàn cục để retry tự động.
- Khi retry, yêu cầu nhập lại hoặc dùng flow token/session an toàn theo policy.

Password manager/autofill có thể tương tác với UI framework. Không cố chặn password manager tùy tiện; hãy thiết kế field đúng semantics và tránh tạo bản sao không cần thiết.

### 6.2. Phía server

Server nhận password qua TLS termination point và xử lý để so sánh với password verifier đã lưu. Password phải được xử lý trong memory ngắn nhất có thể và không được ghi plaintext vào database/log.

Verifier nên được tạo bằng password hashing scheme phù hợp như Argon2id, scrypt hoặc bcrypt với tham số được quản lý. Hashing không làm plaintext biến mất ngay khỏi memory; server vẫn cần cleanup buffer, hạn chế dump và tránh ghi request body.

Không dùng SHA-256 đơn thuần làm password hash. Không tự thiết kế password hashing algorithm.

### 6.3. Password reset và change

Password mới cũng là secret. Nếu hệ thống dùng one-time reset token, token đó phải được bảo vệ trong memory, có expiry và consume một lần. Sau khi reset, policy cần quyết định có revoke session/token cũ hay không.

## 7. Access token, refresh token và session credential

Token thường là bearer credential. Một khi token xuất hiện trong memory của app, process có thể sử dụng token đó theo quyền của nó.

### 7.1. Access token

- Chỉ giữ trong memory khi request cần dùng nếu kiến trúc cho phép.
- Gửi tới đúng API/audience.
- Không log Authorization header hoặc token body.
- Không copy token qua nhiều module nếu có thể truyền qua interface hẹp.
- Xóa reference và buffer tạm sau request theo khả năng.
- Dùng lifetime phù hợp và cơ chế revoke/validation ở resource server.

### 7.2. Refresh token

Refresh token thường có quyền cấp access token mới nên cần bảo vệ nghiêm ngặt hơn:
- Chỉ load từ secure storage khi cần refresh.
- Tránh giữ trong global state hoặc background queue.
- Dùng rotation/reuse detection nếu authorization server hỗ trợ.
- Revoke khi logout, device loss hoặc compromise.
- Không đưa vào crash report, analytics hay notification.
- Không gửi tới resource API.

### 7.3. Session cookie

Browser tự gửi cookie theo cookie policy. JavaScript có thể không đọc được cookie HttpOnly, nhưng ứng dụng server và browser vẫn xử lý cookie trong memory. XSS có thể thực hiện request dưới session hiện tại dù không đọc cookie. Vì vậy cần bảo vệ origin, chống CSRF và thu hồi server-side.

### 7.4. Memory-only storage không chống XSS

Lưu access token trong memory thay localStorage có thể giảm persistence sau khi đóng app/tab, nhưng XSS đang chạy trong cùng origin vẫn có thể đọc hoặc sử dụng token tùy kiến trúc. BFF với HttpOnly session cookie có thể giảm việc JavaScript trực tiếp nắm bearer token, nhưng vẫn cần CSRF và XSS defenses.

## 8. Private key và cryptographic key material

Private key là tài sản có giá trị cao. Nếu có thể, ứng dụng nên dùng key handle và yêu cầu keystore/HSM thực hiện thao tác ký hoặc giải mã thay vì export key material vào process.

### 8.1. Non-exportable key

Keychain, Android Keystore, Secure Enclave, TPM, HSM hoặc KMS có thể cho phép:
- Tạo key trong boundary được bảo vệ.
- Không export private key.
- Giới hạn thuật toán và mục đích sử dụng.
- Yêu cầu user presence hoặc device state.
- Audit thao tác ký/giải mã.
- Revoke hoặc retire key theo lifecycle.

Non-exportable không đồng nghĩa không thể bị lạm dụng. Nếu process được phép gọi sign(), malware trong process có thể yêu cầu ký dữ liệu tùy ý trừ khi protocol ràng buộc challenge, audience, transaction và policy.

### 8.2. Derived key và key schedule

Nếu ứng dụng cần dẫn xuất key:
- Dùng KDF chuẩn và salt/context phù hợp.
- Phân tách key theo mục đích (encryption, signing, MAC).
- Không dùng cùng một key cho nhiều protocol không tương thích.
- Giới hạn key trong phạm vi operation.
- Xóa buffer dẫn xuất khi có thể.
- Không ghi key hoặc intermediate secret vào log.

Không dùng password trực tiếp làm encryption key. Dùng KDF được thiết kế cho mục đích tương ứng và tham số đã được đánh giá.

### 8.3. TLS session keys

TLS library giữ traffic keys trong memory để mã hóa/giải mã record. Ứng dụng thường không cần truy cập các key này. Dùng TLS stack được duy trì, tránh debug mode dump key log trong production và bảo vệ process/host. TLS bảo vệ dữ liệu trên đường truyền; nó không che plaintext khỏi endpoint sau khi TLS kết thúc.

## 9. Secret trong biến môi trường và cấu hình runtime

Biến môi trường thường được dùng để truyền cấu hình cho process, nhưng secret trong environment có thể bị lộ qua process inspection, diagnostic tooling, child process hoặc dump tùy OS và quyền.

Tránh:
- Đặt private key hoặc production client secret vào command-line argument.
- In toàn bộ environment khi debug.
- Truyền secret qua shell history hoặc script log.
- Kế thừa secret không cần thiết sang child process.
- Đưa secret vào crash metadata hoặc support bundle.

Ưu tiên secret manager, workload identity hoặc file descriptor/handle có quyền hẹp nếu nền tảng hỗ trợ. Nếu buộc phải dùng environment variable, giới hạn process access, tránh dump/log và không để secret tồn tại trong nhiều tiến trình con.

File cấu hình mã hóa cũng cần key giải mã. Khi ứng dụng giải mã file, plaintext lại xuất hiện trong memory; at-rest encryption không thay thế memory controls.

## 10. Core dump, heap dump, crash report và debugger

Dump có thể chứa snapshot memory hoặc một phần trạng thái process tại thời điểm lỗi. Nếu credential đang nằm trong memory, dump có thể lưu lại bản sao sau khi request kết thúc.

### 10.1. Các dạng dump

- **Core dump:** snapshot process khi crash hoặc theo yêu cầu.
- **Heap dump:** mô tả object trong managed heap.
- **Crash report:** stack trace, register, metadata và đôi khi memory fragment.
- **Diagnostic bundle:** log, configuration, environment và file tạm.
- **Debugger snapshot:** dữ liệu process khi attach debugger.
- **VM/container snapshot:** có thể chứa memory state tùy cách snapshot.

Dump hữu ích để điều tra lỗi, nhưng cần được phân loại như dữ liệu nhạy cảm. Không tải dump production lên dịch vụ bên thứ ba nếu chưa có kiểm soát và phê duyệt.

### 10.2. Kiểm soát dump

- Tắt hoặc hạn chế core/heap dump production theo risk policy.
- Nếu bắt buộc giữ, lưu trong vùng mã hóa, access-controlled và retention ngắn.
- Chỉ cho phép nhóm điều tra được phê duyệt truy cập.
- Audit mọi lần xem, tải xuống hoặc export.
- Redact secret trước khi gửi crash report nếu công cụ hỗ trợ.
- Tránh bật verbose HTTP/TLS logging trong production.
- Không giữ dump trong thư mục tạm hoặc artifact CI lâu hơn cần thiết.

### 10.3. Debugger và production

Debugger có thể đọc memory, sửa state hoặc gọi hàm trong process. Production process cần chạy với quyền tối thiểu và hạn chế attach/debug theo chính sách hệ điều hành. Quyền admin/root có thể vượt nhiều kiểm soát; hãy xem đó là một phần threat model.

## 11. Swap, hibernation và memory encryption

Memory có thể được ghi ra thiết bị lưu trữ bởi swap/pagefile, hibernation hoặc snapshot. Nếu vùng đó không được bảo vệ, credential có thể tồn tại ngoài RAM.

### 11.1. Swap và pagefile

Tùy hệ điều hành, trang memory ít dùng có thể được ghi xuống swap/pagefile. Các biện pháp:
- Bật mã hóa ổ đĩa và swap theo khả năng platform.
- Hạn chế dump các process nhạy cảm.
- Dùng memory locking cho vùng rất nhạy cảm khi phù hợp và được OS hỗ trợ.
- Kiểm tra quyền đọc pagefile/swap và backup.
- Không giả định mọi runtime buffer đều được lock chỉ vì một vùng memory được lock.

Memory locking như mlock hoặc VirtualLock có giới hạn về quota, quyền và hành vi OS; không phải giải pháp phổ quát.

### 11.2. Hibernation và snapshot

Hibernation có thể ghi memory state xuống disk. VM snapshot và host snapshot cũng có thể lưu memory. Quản lý chúng như backup nhạy cảm: mã hóa storage, hạn chế operator/export, giới hạn retention, có quy trình xóa và không tạo snapshot production chứa secret nếu không cần.

### 11.3. Memory encryption và confidential computing

Một số CPU/cloud platform hỗ trợ mã hóa memory hoặc confidential VM/TEE. Công nghệ này có thể giảm khả năng host hoặc hypervisor đọc plaintext trong một số threat model. Chúng không tự bảo vệ khỏi malware chạy bên trong guest/process, application log, credential bị sử dụng sai bởi process được phép, side-channel ngoài phạm vi hoặc lỗi authorization.

Chọn confidential computing khi threat model yêu cầu bảo vệ data-in-use trước operator/hypervisor cụ thể; không dùng nó thay secure coding và least privilege.

## 12. Process isolation và least privilege

Giảm số thành phần có thể đọc credential là một trong những biện pháp hiệu quả nhất.

### 12.1. Tách secret broker

Có thể tách thành phần giữ secret khỏi thành phần xử lý request:
- API gateway xác minh client nhưng không lưu secret dài hạn.
- Secret broker lấy credential từ vault và chỉ thực hiện thao tác cần thiết.
- Signing service giữ private key và nhận request ký có policy.
- Application process nhận kết quả hoặc token ngắn hạn thay vì master secret.

Mô hình này giảm phạm vi lộ nếu một process bị compromise, nhưng IPC/API giữa các thành phần phải được xác thực, giới hạn quyền và audit.

### 12.2. Least privilege

- Chạy process dưới service account riêng.
- Không cấp quyền đọc memory/process của service khác.
- Tắt capability/debug interface không cần.
- Hạn chế child process và plugin.
- Giới hạn quyền filesystem, socket và network egress.
- Tách production/test secret.
- Xoay credential theo owner và workload.
- Hạn chế người vận hành truy cập host và dump.

Container giúp tổ chức process và filesystem, nhưng không phải ranh giới tuyệt đối trước host/kernel compromise. Các container trên cùng host thường chia sẻ kernel; cần đánh giá runtime, namespace, capability và host trust.

## 13. Logging, tracing và telemetry

Nhiều vụ lộ credential xảy ra không phải do memory exploit mà do ứng dụng tự ghi secret vào hệ thống quan sát.

Không log password, password reset token, Authorization header, bearer/refresh token, session cookie, client secret, API key, TOTP seed, recovery code, private key, HMAC secret, derived key hoặc request/response body chứa credential.

Có thể log credential reference, key ID, issuer, audience, token type, authentication method/outcome, reason code, request/trace ID, certificate fingerprint và policy version nếu cần.

Redaction nên diễn ra trước khi log được ghi vào queue, file hoặc collector. Nếu chỉ mask trong dashboard, secret có thể vẫn nằm trong raw event, archive và backup.

### 13.1. Exception và object serialization

Một object AuthenticationRequest có thể chứa password hoặc token. Nếu logger tự gọi toString() hoặc serializer phản chiếu field, secret có thể xuất hiện ngoài ý muốn.

Thiết kế:
- Không đưa secret vào toString().
- Dùng DTO log riêng chỉ chứa metadata an toàn.
- Đánh dấu field nhạy cảm trong logging framework nếu hỗ trợ.
- Kiểm thử exception path và debug mode.
- Tránh dump toàn bộ HTTP headers hoặc environment.

## 14. Credential trong memory ở browser và mobile

Browser và mobile app có những đặc điểm riêng.

### 14.1. Browser

JavaScript runtime có thể giữ access token, password hoặc dữ liệu form trong heap. XSS có thể đọc dữ liệu trong origin hoặc thực hiện request bằng quyền hiện tại. HttpOnly cookie giảm khả năng JavaScript đọc cookie, nhưng không chặn request abuse. Browser extension, devtools, crash report và autofill có thể tác động tới dữ liệu.

BFF giúp giữ access/refresh token phía server, browser chỉ giữ session cookie. Không coi memory-only token là an toàn trước XSS; bảo vệ origin, CSP, output encoding, dependency và session policy vẫn cần thiết.

### 14.2. Mobile

Keychain/Keystore bảo vệ key/secret khi lưu và có thể kiểm soát quyền sử dụng. Khi app đọc token để gửi request, token xuất hiện trong process memory. Root/jailbreak, debugger, instrumentation hoặc backup có thể làm tăng rủi ro. Biometric prompt có thể mở quyền dùng key; không nhất thiết trả biometric template cho app.

Secure storage không thay thế revoke server-side khi mất thiết bị. Giữ token trong memory trong thời gian cần thiết, tránh log/clipboard/notification và dùng refresh rotation/revocation.

## 15. Memory safety và lỗi phần mềm

Credential có thể bị lộ qua lỗi memory safety trong native component hoặc thư viện bên thứ ba.

### 15.1. Lỗi phổ biến

- Buffer overflow/underflow.
- Use-after-free.
- Double free.
- Out-of-bounds read.
- Uninitialized memory disclosure.
- Race condition khi buffer được chia sẻ.
- Integer overflow dẫn tới allocation sai kích thước.
- Unsafe serialization/deserialization.

Một lỗi out-of-bounds read có thể làm lộ byte nằm cạnh buffer chứa token hoặc key. Use-after-free có thể khiến attacker đọc lại dữ liệu cũ sau khi object đã được giải phóng.

### 15.2. Phòng ngừa

- Ưu tiên ngôn ngữ và API memory-safe khi phù hợp.
- Dùng thư viện crypto/TLS được duy trì.
- Kiểm tra kích thước và giới hạn input.
- Dùng ownership/borrowing hoặc RAII rõ.
- Tránh tự quản lý raw pointer khi không cần.
- Bật compiler hardening và sanitizer trong môi trường kiểm thử.
- Cập nhật dependency và theo dõi security advisory.
- Fuzz parser, token handling và native bridge.
- Không tự viết primitive mật mã.

Memory-safe language giảm một số lớp lỗi, nhưng không ngăn secret logging, quyền process quá rộng, XSS hoặc logic authorization sai.

## 16. Quy trình thiết kế credential handling an toàn

Một quy trình thực tế có thể áp dụng cho API client, backend service và ứng dụng mobile.

### 16.1. Trước khi nạp secret

1. Xác định loại credential và owner.
2. Xác định process nào thật sự cần sử dụng.
3. Ưu tiên key handle hoặc workload identity thay secret dài hạn.
4. Lấy credential từ nguồn tin cậy qua kênh xác thực.
5. Đặt giới hạn size, lifetime và purpose.
6. Không truyền qua command line, URL hoặc log.

### 16.2. Trong khi sử dụng

1. Giữ secret trong buffer có phạm vi hẹp.
2. Tránh String conversion, formatting và unnecessary copy.
3. Không chia sẻ qua global state hoặc thread không cần.
4. Không ghi request/response body chứa secret.
5. Dùng credential đúng issuer, audience, endpoint và operation.
6. Áp dụng timeout và cancellation có cleanup.

### 16.3. Sau khi sử dụng

1. Xóa buffer mutable trong phạm vi kiểm soát.
2. Giải phóng resource và handle theo API.
3. Xóa reference/cache không cần.
4. Không để retry queue hoặc background task giữ secret.
5. Ghi audit bằng reference/reason code, không ghi secret.
6. Nếu có dấu hiệu lộ, revoke/rotate credential ở issuer và verifier.

### 16.4. Pseudocode

    useCredential():
        credentialHandle = secureProvider.openHandle()
        secretBuffer = null
        try:
            secretBuffer = credentialHandle.readForOperation()
            validatePurposeAndTarget(secretBuffer)
            performOneOperation(secretBuffer)
        finally:
            if secretBuffer is mutable:
                secureEraseOwnedBuffer(secretBuffer)
            credentialHandle.close()
            clearReferences()

Đây là pseudocode minh họa. Trong hệ thống có non-exportable key, không cần đọc key material vào secretBuffer; gọi thao tác sign/decrypt trực tiếp qua handle sẽ tốt hơn. Cleanup chỉ bảo đảm với resource do ứng dụng kiểm soát, không xóa được mọi bản sao do runtime hoặc provider tạo.

## 17. Threat model cho credential trong memory

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Heap/core dump exposure** | Dump chứa password, token hoặc key đang nằm trong process. | Credential bị lấy và replay. | Hạn chế dump, mã hóa/lưu dump có kiểm soát, giảm secret lifetime. |
| **Debugger/process inspection** | Attacker có quyền attach hoặc đọc memory. | Lộ credential đang dùng. | Least privilege, OS hardening, production debug controls. |
| **Runtime copy leakage** | String conversion, serialization hoặc buffer copy tạo bản sao. | Secret tồn tại lâu hơn dự kiến. | Mutable buffer, hạn chế copy, không log/format. |
| **GC lifetime uncertainty** | Object nhạy cảm chưa được thu gom hoặc bị di chuyển. | Không thể bảo đảm xóa đúng lúc. | Giảm object creation, clear vùng kiểm soát được, dùng key handle. |
| **Secret in logs** | Exception/logger ghi request hoặc header. | Log trở thành kho bearer credential. | Redaction trước ingestion, safe DTO và log tests. |
| **Swap/hibernation exposure** | Memory page được ghi xuống storage. | Secret còn lại ngoài RAM. | Disk/swap encryption, dump policy và memory locking phù hợp. |
| **Environment/argument leakage** | Secret truyền qua env hoặc command line. | Process inspection hoặc diagnostic lộ secret. | Secret manager, handle/file descriptor và hạn chế inheritance. |
| **Native memory bug** | Buffer overflow/use-after-free/out-of-bounds. | Đọc hoặc sửa memory chứa credential. | Memory-safe code, sanitizer, fuzzing và dependency updates. |
| **XSS/runtime injection** | Script hoặc instrumentation chạy trong process/origin. | Đọc hoặc sử dụng token/session. | CSP, output encoding, process isolation và server-side controls. |
| **Shared process/plugin** | Plugin hoặc thư viện cùng process có thể đọc dữ liệu. | Secret vượt boundary dự kiến. | Tách process, giảm plugin, API hẹp và code review. |
| **Overprivileged service** | Process có quyền đọc dump hoặc memory process khác. | Compromise lan rộng. | Service account riêng, capability hạn chế và host hardening. |
| **Stale credential reference** | Buffer/cache/closure giữ token sau logout hoặc revoke. | Secret cũ vẫn được sử dụng. | Explicit lifecycle, cache invalidation, generation/version và revoke. |

## 18. Tình huống thực hành: access token xuất hiện trong heap dump

**Bối cảnh:** Một ứng dụng backend dùng Java để gọi API thanh toán. Khi debug lỗi production, nhóm vận hành tạo heap dump. Sau đó một bản dump được đưa vào hệ thống phân tích tập trung. Trong dump có object chứa Authorization header và access token còn hạn. Một số log cũng ghi toàn bộ request khi HTTP client gặp lỗi.

**Phân tích:**

1. Token được giữ trong memory để request interceptor thêm vào header.
2. Request object và exception giữ reference tới header/token.
3. Heap dump lưu object trước khi garbage collector thu gom.
4. Log request/header tạo thêm bản sao bên ngoài process.
5. Người có quyền đọc dump/log có thể dùng token trong thời hạn nếu audience và policy cho phép.

**Xử lý:**

- Hạn chế quyền truy cập dump và log; bảo toàn evidence theo incident process.
- Xác định token reference, issuer, audience, expiry và request bị ảnh hưởng mà không phát tán token trong ticket.
- Revoke grant/session hoặc token theo khả năng của authorization server; đánh giá access token offline còn hiệu lực tới khi nào.
- Xóa/rotate artifact chứa token theo retention và incident policy.
- Tắt header/body logging nhạy cảm và thêm redaction trước ingestion.
- Sửa interceptor/exception serialization để không giữ hoặc in Authorization header.
- Giảm thời gian token trong object, tránh cache không cần và kiểm soát heap dump production.
- Kiểm thử bằng synthetic token để xác nhận dump/log pipeline không chứa secret thật.

**Câu hỏi:** Nếu ứng dụng gọi clear() hoặc gán biến token thành null sau request, heap dump đã tạo trước đó có tự mất token không? Không. Dump là bản sao độc lập; cần xử lý artifact đã lưu và thu hồi credential ở issuer/verifier.

## 19. Kiểm thử và xác minh credential memory handling

Kiểm thử không thể chứng minh tuyệt đối rằng không có bản sao nào trong mọi runtime layer, nhưng có thể tìm ra các đường phơi lộ phổ biến.

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| Tìm password trong application log | Không có plaintext hoặc encoded form có thể dùng. |
| Tìm Authorization header trong trace | Không có bearer token. |
| Tạo exception từ HTTP client | Exception không serialize credential. |
| Kiểm tra toString()/JSON serializer | Object auth không in secret field. |
| Heap dump trong test với synthetic credential | Xác định object/reference ngoài dự kiến; dump được bảo vệ. |
| Logout khi background refresh đang chạy | Không giữ hoặc lưu lại token state sau revoke. |
| Hủy request giữa chừng | Cleanup chạy trên cancellation/error path. |
| Rotation secret/key | Process dùng version mới và ngừng dùng version cũ theo policy. |
| Native buffer cleanup | Buffer thuộc quyền sở hữu được xóa bằng primitive phù hợp. |
| Environment inspection | Secret không bị in hoặc kế thừa sang child process không cần. |
| Crash report | Không chứa request header, body hoặc memory fragment nhạy cảm ngoài policy. |
| Backup/snapshot review | Artifact không lưu credential plaintext ngoài thiết kế. |
| Plugin/dependency review | Không có thành phần không cần thiết truy cập credential. |
| Memory-safety testing | Sanitizer/fuzzer không phát hiện lỗi đọc/ghi vượt vùng trong đường xử lý credential. |

Dùng synthetic credential trong kiểm thử. Không đưa production password, private key hoặc bearer token thật vào test dump rồi gửi qua hệ thống bên ngoài.

## 20. Checklist thiết kế credential trong memory

- [ ] Inventory password, token, cookie, API key, TOTP seed, private key và derived key.
- [ ] Xác định process, runtime, library và owner cần truy cập từng credential.
- [ ] Ưu tiên non-exportable key handle, workload identity hoặc KMS/HSM khi phù hợp.
- [ ] Giảm số lần copy và thời gian tồn tại trong memory.
- [ ] Tránh immutable String cho secret nếu runtime/API có lựa chọn buffer phù hợp.
- [ ] Hiểu giới hạn của GC, ARC, JIT, native provider và memory allocator.
- [ ] Clear buffer mutable thuộc quyền sở hữu; không tuyên bố xóa sạch mọi bản sao.
- [ ] Dùng secure-zero primitive đã được platform/thư viện hỗ trợ cho native memory.
- [ ] Không log, format, serialize hoặc đưa secret vào exception/toString.
- [ ] Redact trước khi ghi vào queue, file, trace hoặc SIEM.
- [ ] Hạn chế heap/core dump, debugger và production diagnostics.
- [ ] Mã hóa swap/pagefile/hibernation và kiểm soát snapshot theo threat model.
- [ ] Tránh truyền secret qua URL, command line hoặc environment nếu có lựa chọn tốt hơn.
- [ ] Dùng process isolation, service account riêng và least privilege.
- [ ] Bảo vệ browser origin và chống XSS; memory-only token không chặn script độc hại.
- [ ] Quản lý refresh token, session cookie và key lifecycle với revoke/rotation.
- [ ] Kiểm thử cancellation, exception, retry, logout và background task.
- [ ] Kiểm thử log, trace, crash report, heap dump và backup bằng synthetic credential.
- [ ] Theo dõi dependency, native bridge, sanitizer và memory-safety issue.
- [ ] Có incident runbook để revoke credential và xử lý dump/log đã bị lộ.

## 21. Câu hỏi tự kiểm tra

**1. Credential trong memory là gì?**  
Là secret hoặc vật thể mật mã đang được nạp vào memory để ứng dụng xác thực, ký, giải mã hoặc gửi request.

**2. Vì sao mã hóa at-rest không đủ?**  
Vì process cần giải mã hoặc sử dụng credential; khi đó secret xuất hiện trong memory và có thể bị đọc qua dump, debugger, malware hoặc lỗi phần mềm.

**3. Vì sao String trong Java không phù hợp để giữ password lâu?**  
String immutable nên ứng dụng không thể ghi đè nội dung qua API thông thường; object có thể tồn tại tới khi GC thu gom và có thể xuất hiện trong heap dump.

**4. Gán biến secret thành null có xóa dữ liệu memory không?**  
Không. Nó chỉ bỏ một reference; nội dung có thể còn trong heap hoặc bản sao khác.

**5. Zeroization có bảo đảm mọi bản sao secret biến mất không?**  
Không. Nó chỉ xử lý vùng memory được chỉ định; runtime, compiler, library, register hoặc dump có thể chứa bản sao khác.

**6. Vì sao nên dùng non-exportable key?**  
Để private key được sử dụng bên trong keystore/HSM mà không cần export raw key material vào process. Tuy vậy, quyền gọi thao tác ký vẫn phải được kiểm soát.

**7. Memory-only access token có chống XSS không?**  
Không. Script độc hại cùng origin có thể đọc hoặc sử dụng token tùy kiến trúc. Memory-only chủ yếu giảm persistence ở một số trường hợp.

**8. Heap dump có thể làm lộ gì?**  
Password, token, cookie, client secret, object request, key buffer và dữ liệu nhạy cảm còn được tham chiếu trong heap.

**9. Có nên đặt secret trong command-line argument hoặc environment variable không?**  
Tránh nếu có lựa chọn tốt hơn vì chúng có thể bị lộ qua process inspection, diagnostic tooling, child process hoặc dump.

**10. Khi phát hiện token trong dump đã lưu, cần làm gì?**  
Hạn chế quyền và bảo toàn evidence, xác định phạm vi, revoke token/grant/session theo khả năng, xử lý artifact chứa secret và sửa đường logging/dump gây lộ.

**Ghi nhớ:** Credential trong memory là một phần tất yếu của nhiều thao tác xác thực, nhưng exposure window và phạm vi truy cập có thể được giảm đáng kể. Hãy nạp secret từ nguồn tin cậy, dùng trong phạm vi hẹp, ưu tiên key handle, hạn chế bản sao, bảo vệ dump/log/process và cleanup buffer mà ứng dụng kiểm soát. Không có một lệnh xóa đơn lẻ nào thay thế được threat model, least privilege, credential revocation và kiểm soát toàn bộ đường đi của dữ liệu.
