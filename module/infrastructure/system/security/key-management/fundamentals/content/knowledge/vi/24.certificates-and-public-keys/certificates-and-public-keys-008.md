# Certificate renewal

Trong chương **Certificate và public key** của module `SECURITY_KEY_MANAGEMENT_FUNDAMENTALS`, bài học này giải thích quy trình gia hạn chứng thư số và cách phối hợp việc gia hạn với quản lý khóa mật mã. Chứng thư số có thời hạn hiệu lực; trước khi hết hạn, tổ chức cần cấp và triển khai chứng thư mới để duy trì xác thực TLS, mTLS, ký số hoặc các chức năng PKI khác. Quy trình phải bảo đảm đúng danh tính, đúng public key, đúng mục đích sử dụng và giữ được chuỗi tin cậy trong suốt thời gian chuyển đổi.

## 1. Certificate renewal là gì?

**Certificate renewal** là quá trình yêu cầu CA cấp một chứng thư mới để thay thế hoặc tiếp nối chứng thư đang sử dụng trước khi chứng thư cũ hết hạn hoặc không còn phù hợp với chính sách. Chứng thư mới thường có thời hạn hiệu lực mới, serial number mới và có thể chứa public key mới, subject hoặc Subject Alternative Name (SAN) đã cập nhật.

Chứng thư số là một cấu trúc dữ liệu được CA ký, liên kết danh tính hoặc tên dịch vụ với public key cùng các thuộc tính và giới hạn sử dụng. Chứng thư không phải bản thân khóa riêng. Khi gia hạn, hệ thống cần quyết định có tiếp tục dùng cặp khóa cũ hay tạo cặp khóa mới rồi gửi public key mới trong CSR.

Gia hạn đúng hạn giúp tránh gián đoạn do chứng thư hết hạn. Nó cũng là cơ hội rà soát thuật toán, độ dài khóa, SAN, Extended Key Usage (EKU), chính sách CA và trạng thái bảo mật của khóa riêng. Một chứng thư mới chỉ có giá trị khi được phát hành bởi CA đáng tin cậy và được triển khai đúng trên mọi điểm kết thúc liên quan.

## 2. Phân biệt renewal, rekey và reissue

Các thuật ngữ này có thể được CA hoặc sản phẩm sử dụng hơi khác nhau. Về mặt vận hành, cần xác định rõ thay đổi nào đang được thực hiện:

| Thao tác | Điều thay đổi | Cặp khóa |
|---|---|---|
| Renewal | Cấp chứng thư mới để tiếp nối chứng thư hiện tại, thường giữ mục đích và danh tính tương tự | Có thể giữ nguyên hoặc thay mới tùy chính sách và quy trình |
| Rekey | Tạo cặp khóa mới và yêu cầu chứng thư gắn với public key mới | Thay cặp khóa; private key cũ không được dùng cho chứng thư mới |
| Reissue | CA phát hành lại chứng thư, thường để sửa thông tin, thay public key hoặc thay đổi thuộc tính | Có thể giữ hoặc thay cặp khóa tùy nguyên nhân và chính sách |
| Revoke | Thu hồi trạng thái tin cậy của chứng thư trước khi hết hạn | Không tự động xóa private key; cần xử lý khóa theo quy trình riêng |

Renewal không mặc nhiên đồng nghĩa với rekey. Một số hệ thống tự động gia hạn bằng cùng key pair để giảm thao tác, nhưng giữ private key lâu hơn làm tăng thời gian phơi nhiễm nếu khóa đã bị sao chép. Với chứng thư máy chủ quan trọng, tạo cặp khóa mới trong chu kỳ gia hạn thường là lựa chọn tốt nếu nền tảng và chính sách cho phép.

Nếu private key cũ bị nghi ngờ lộ, không nên chỉ gia hạn chứng thư với cùng public key. Cần tạo cặp khóa mới, cấp chứng thư mới, triển khai nó, thu hồi chứng thư cũ theo quy trình sự cố và đánh giá phạm vi ảnh hưởng.

## 3. Vì sao cần gia hạn đúng hạn?

Chứng thư hết hạn có thể khiến bên xác minh từ chối kết nối hoặc chữ ký, dù private key vẫn hoạt động về mặt toán học.

- **TLS server:** client có thể từ chối HTTPS khi chứng thư hết hạn, gây lỗi kết nối tới API, website hoặc dịch vụ nội bộ.
- **mTLS:** một bên có thể từ chối chứng thư client/server hết hạn, làm hỏng xác thực hai chiều giữa dịch vụ.
- **Email và tài liệu ký số:** ứng dụng có thể không chấp nhận chứng thư hết hạn theo chính sách kiểm tra tại thời điểm xác minh.
- **Thiết bị và hệ thống nhúng:** thiết bị ngoại tuyến hoặc khó cập nhật có thể tiếp tục dùng chứng thư cũ và mất kết nối khi chứng thư hết hạn.
- **Tích hợp đối tác:** chứng thư hết hạn có thể làm gián đoạn kết nối B2B, gateway, VPN hoặc kênh trao đổi dữ liệu.

Gia hạn sớm tạo thời gian xử lý lỗi CSR, xác minh danh tính, phê duyệt, phát hành, triển khai và kiểm thử. Thời điểm bắt đầu renewal cần dựa trên thời hạn chứng thư, SLA của CA, thời gian triển khai và khả năng cập nhật của các client. Không có một mốc ngày duy nhất phù hợp cho mọi hệ thống.

## 4. Các thành phần tham gia renewal

Quy trình renewal thường có nhiều vai trò và hệ thống:

| Thành phần | Trách nhiệm |
|---|---|
| Certificate owner | Chịu trách nhiệm về mục đích, danh tính, SAN, môi trường và thời hạn sử dụng chứng thư |
| PKI/CA | Xác minh yêu cầu, áp dụng certificate policy và phát hành chứng thư |
| Key custodian hoặc HSM administrator | Bảo vệ private key, kiểm soát tạo khóa, import/export và quyền sử dụng |
| Application/platform owner | Triển khai chứng thư và chain vào load balancer, server, gateway hoặc ứng dụng |
| Trust store administrator | Cập nhật trust anchor nếu có thay đổi CA hoặc chain cần thiết |
| Monitoring/operations | Theo dõi thời hạn, cảnh báo, trạng thái triển khai và lỗi xác minh |
| Security/audit | Phê duyệt ngoại lệ, kiểm tra quyền hạn và lưu bằng chứng thay đổi |

Với hệ thống nhỏ, một nhóm có thể đảm nhiệm nhiều vai trò. Tuy nhiên, quyền tạo private key, phê duyệt cấp chứng thư và triển khai chứng thư nhạy cảm nên được phân tách phù hợp với mức độ rủi ro.

## 5. Quy trình certificate renewal

Một quy trình chuẩn có thể được triển khai theo các bước sau.

### Bước 1: Phát hiện chứng thư sắp hết hạn

Kiểm kê chứng thư đang dùng trong CA inventory, certificate manager, load balancer, web server, API gateway, service mesh, thiết bị và ứng dụng. Theo dõi ít nhất subject/SAN, issuer, serial number, fingerprint, Not After, key type, key size, EKU, vị trí triển khai và owner.

Thiết lập cảnh báo theo mức độ quan trọng và thời gian cần thiết để xử lý. Cảnh báo phải gửi tới nhóm chịu trách nhiệm thực tế; chứng thư không có owner hoặc không rõ nơi sử dụng cần được xử lý như một vấn đề quản trị tài sản.

### Bước 2: Rà soát yêu cầu và chính sách

Xác nhận chứng thư vẫn cần thiết, tên miền và danh tính còn đúng, CA vẫn được tin cậy, thuật toán và độ dài khóa còn phù hợp. Kiểm tra SAN, Key Usage, EKU, certificate policy, thời hạn tối đa và yêu cầu xác thực của CA.

Nếu tên miền, tenant, tổ chức hoặc mục đích sử dụng đã thay đổi, renewal cần phản ánh trạng thái hiện tại. Không sao chép nguyên subject/SAN cũ một cách máy móc.

### Bước 3: Quyết định dùng lại hay tạo cặp khóa mới

Đánh giá private key hiện tại có còn an toàn, được bảo vệ đúng cách và phù hợp với chính sách không. Nếu giữ cặp khóa cũ, xác nhận quyền truy cập và nơi lưu private key vẫn được kiểm soát. Nếu rekey, tạo cặp khóa mới bằng CSPRNG và thuật toán được phê duyệt, ưu tiên tạo trực tiếp trong HSM hoặc thiết bị bảo vệ khóa khi yêu cầu bảo mật cần thiết.

Không tạo private key mới bằng cách sao chép file private key hiện có hoặc dùng dữ liệu dự đoán được. Không đưa private key vào CSR, ticket hoặc email.

### Bước 4: Tạo CSR

Certificate Signing Request (CSR) chứa public key và thông tin yêu cầu cấp chứng thư, thường được ký bằng private key tương ứng để chứng minh người yêu cầu nắm giữ khóa riêng. CSR không chứa private key.

Ví dụ tạo cặp khóa RSA và CSR bằng OpenSSL:

```bash
openssl req -new -newkey rsa:3072 -nodes \
  -keyout server-new.key \
  -out server-new.csr \
  -subj "/CN=api.example.com" \
  -addext "subjectAltName=DNS:api.example.com,DNS:api.internal.example.com"
```

Trong ví dụ này `-nodes` tạo private key không được mã hóa bằng passphrase trong file đầu ra. Đây chỉ là ví dụ thao tác; trong môi trường production, cần bảo vệ file ngay từ lúc tạo, giới hạn quyền truy cập, tránh lưu trên máy dùng chung và cân nhắc tạo khóa trong HSM hoặc dùng cơ chế bảo vệ phù hợp. Với EC, chọn curve được policy và CA hỗ trợ.

Thông tin subject/SAN trong CSR là dữ liệu yêu cầu. CA có thể xác minh, giới hạn hoặc thay thế các trường theo certificate policy; không phải mọi CA đều chấp nhận mọi SAN được gửi.

### Bước 5: Gửi CSR và xác minh danh tính

Gửi CSR qua cổng hoặc API được CA phê duyệt. CA xác minh quyền kiểm soát tên miền, danh tính tổ chức, quyền yêu cầu và các điều kiện phát hành theo loại chứng thư. Với chứng thư nội bộ, quy trình có thể yêu cầu ticket, phê duyệt của owner hoặc xác nhận từ quản trị PKI.

Đối với chứng thư TLS công khai, phương thức xác thực có thể gồm DNS challenge, HTTP challenge hoặc xác thực theo cơ chế CA hỗ trợ. Thông tin xác thực challenge phải được quản lý an toàn và chỉ cấp quyền cần thiết.

### Bước 6: Nhận và kiểm tra chứng thư mới

Sau khi CA phát hành, kiểm tra:

- Subject và SAN đúng với dịch vụ hoặc danh tính cần bảo vệ.
- Public key trong chứng thư khớp với private key đang được giữ.
- Issuer, serial number, fingerprint và thời hạn hiệu lực đúng như yêu cầu.
- Key Usage, EKU, Basic Constraints và certificate policy phù hợp.
- Chữ ký và certificate chain dẫn tới trust anchor được chấp nhận.
- Trạng thái thu hồi có thể kiểm tra theo chính sách.

Không chỉ dựa vào tên file hoặc thông báo phát hành thành công của CA. Cần đối chiếu public key trong chứng thư với public key được tạo từ private key hoặc HSM handle tương ứng.

### Bước 7: Triển khai chứng thư và chain

Triển khai chứng thư mới cùng intermediate certificates cần thiết lên đúng endpoint. Bảo đảm private key tương ứng được liên kết đúng và không vô tình thay thế bằng khóa của môi trường khác. Với load balancer hoặc cluster, cập nhật theo cơ chế nhất quán và kiểm soát phiên bản.

Nếu CA hoặc trust anchor không thay đổi, thường không cần cập nhật trust store của client chỉ vì chứng thư máy chủ được gia hạn. Nếu chain chuyển sang CA mới hoặc trust anchor mới, cần phân phối trust anchor trước theo kế hoạch chuyển đổi và kiểm tra các client bị ảnh hưởng.

### Bước 8: Kiểm thử sau triển khai

Kiểm tra từ góc nhìn của client thực tế:

1. Kết nối TLS thành công tới đúng hostname hoặc địa chỉ.
2. Máy chủ gửi đúng leaf certificate và intermediate chain.
3. Chứng thư mới còn hiệu lực, có SAN và EKU phù hợp.
4. Client xây dựng được chain tới trust anchor mong muốn.
5. Hostname verification và revocation checking hoạt động theo chính sách.
6. mTLS, nếu có, vẫn xác minh chứng thư ở cả hai chiều.
7. Tất cả node, vùng, listener và endpoint đã chuyển sang chứng thư mới.

Có thể dùng `openssl s_client` để kiểm tra chain và kết nối:

```bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -showcerts \
  -verify_return_error
```

Lệnh này hỗ trợ kiểm tra handshake và chuỗi chứng thư theo trust configuration của OpenSSL trên máy chạy lệnh. Nó không thay thế kiểm thử từ đúng runtime hoặc ứng dụng production, vì mỗi môi trường có thể dùng trust store và chính sách khác nhau.

### Bước 9: Hoàn tất chuyển đổi và xử lý chứng thư cũ

Sau khi xác nhận toàn bộ endpoint và client đã hoạt động với chứng thư mới, đánh dấu chứng thư cũ là retired. Nếu chứng thư cũ bị compromise hoặc không còn đáng tin cậy, thực hiện revoke theo quy trình và thông báo các bên liên quan. Nếu chỉ hết hạn bình thường, vẫn cần loại bỏ cấu hình cũ khỏi endpoint để tránh triển khai nhầm.

Private key cũ phải được giữ hoặc hủy theo mục đích và chính sách. Nếu còn cần xác minh chữ ký lịch sử, giữ chứng thư công khai, thông tin chain, timestamp và bằng chứng liên quan; không mặc định phải giữ private key cũ. Khi private key không còn cần thiết, hủy mọi bản sao có thể phục hồi theo quy trình key destruction.

## 6. Renewal với cùng key pair và renewal có rekey

Lựa chọn dùng lại hay thay cặp khóa có ảnh hưởng đến rủi ro và vận hành.

| Tiêu chí | Giữ key pair | Tạo key pair mới (rekey) |
|---|---|---|
| Private key | Tiếp tục dùng khóa cũ | Tạo và bảo vệ khóa mới |
| Rủi ro tích lũy | Khóa cũ tiếp tục tồn tại lâu hơn | Giảm thời gian sử dụng khóa cũ, giới hạn ảnh hưởng nếu khóa cũ bị lộ |
| Triển khai | Có thể đơn giản hơn nếu cấu hình không đổi | Cần liên kết chứng thư mới với private key mới và triển khai đồng bộ |
| Phụ thuộc | Có thể giữ nguyên các hệ thống dùng key handle hiện tại | Có thể phải cập nhật HSM object, key reference, pinning hoặc cấu hình ứng dụng |
| Khi phù hợp | Khóa vẫn an toàn, policy cho phép và có lý do vận hành rõ ràng | Chu kỳ định kỳ, thay đổi thuật toán, nghi ngờ lộ khóa hoặc yêu cầu giảm thời gian phơi nhiễm |

Với TLS server, rekey theo chu kỳ thường giúp giới hạn thời gian private key được sử dụng. Tuy nhiên, cần cân nhắc các hệ thống pin public key, thiết bị ngoại tuyến và các tích hợp phụ thuộc fingerprint. Nếu có pinning, phải cập nhật pinset theo kế hoạch trước khi đổi key để tránh tự khóa client khỏi dịch vụ.

## 7. Gia hạn chứng thư TLS công khai bằng ACME

ACME (Automatic Certificate Management Environment) cho phép client tự động yêu cầu, xác thực và gia hạn chứng thư từ CA hỗ trợ giao thức. Automation giảm nguy cơ quên gia hạn, nhưng vẫn cần bảo vệ tài khoản ACME, private key, DNS credentials và quy trình triển khai.

Một luồng tổng quát:

1. Client ACME tạo hoặc sử dụng tài khoản đã đăng ký với CA.
2. Client tạo key pair và CSR cho tên miền cần chứng thư.
3. CA cung cấp challenge để xác minh quyền kiểm soát tên miền.
4. Client hoàn thành challenge, chẳng hạn tạo DNS TXT record hoặc HTTP resource.
5. CA xác minh và phát hành chứng thư.
6. Client tải chứng thư và chain, triển khai vào endpoint.
7. Hook hoặc automation reload dịch vụ, sau đó kiểm tra kết nối.
8. Monitoring tiếp tục theo dõi hạn chứng thư và trạng thái renewal.

Automation cần có các kiểm soát:

- Giới hạn DNS/API token vào đúng zone và thao tác cần thiết.
- Bảo vệ ACME account key và private key của chứng thư.
- Kiểm tra exit code, nội dung chứng thư và chain trước khi deploy.
- Triển khai atomic hoặc có rollback để tránh endpoint nhận file chưa hoàn chỉnh.
- Chỉ reload dịch vụ sau khi kiểm tra cấu hình và cặp khóa/chứng thư khớp nhau.
- Cảnh báo khi renewal thất bại, challenge không hoàn tất hoặc chứng thư mới không được phục vụ.
- Thử nghiệm định kỳ quy trình gia hạn và phục hồi, không chỉ dựa vào lịch chạy job.

Không nên coi job ACME chạy thành công là bằng chứng renewal đã hoàn tất. Cần kiểm tra chứng thư mà client thực sự nhận được từ mọi endpoint.

## 8. Gia hạn chứng thư nội bộ và mTLS

Trong PKI nội bộ, chứng thư có thể được cấp cho service, workload, người dùng, thiết bị hoặc service account. Renewal cần phối hợp với danh tính workload và cơ chế phân phối chứng thư.

Với service mesh hoặc hệ thống mTLS, chứng thư có thể có thời hạn ngắn và được tự động cấp lại. Các thành phần cần phối hợp gồm workload identity, CA issuer, agent cấp chứng thư, secret volume, sidecar/proxy và ứng dụng. Cần bảo đảm chứng thư mới được nạp trước khi chứng thư cũ hết hạn và các kết nối đang hoạt động được xử lý theo chính sách.

Các vấn đề cần kiểm tra:

- SAN hoặc URI SAN phản ánh đúng workload identity.
- EKU và Key Usage cho phép đúng vai trò client/server.
- Trust bundle của peer chứa CA cần thiết để xác minh chứng thư mới.
- Rotation private key và certificate được thực hiện đồng bộ.
- Các proxy, sidecar và ứng dụng có reload chứng thư mà không làm lộ private key.
- Chứng thư cũ được retire hoặc revoke theo chính sách sau khi quá trình chuyển đổi hoàn tất.

Nếu CA nội bộ được thay thế, cần phân phối trust anchor mới tới các workload trước khi cấp chứng thư mới. Renewal leaf certificate không tự động cập nhật trust bundle của client.

## 9. Theo dõi và tự động hóa certificate renewal

Quản lý thủ công dễ bỏ sót chứng thư nằm ngoài inventory hoặc thuộc hệ thống ít được vận hành. Một chương trình quản lý vòng đời nên có inventory tập trung và cảnh báo chủ động.

Các trường cần theo dõi:

- Certificate ID, serial number, fingerprint và issuer.
- Subject, SAN, EKU, Key Usage và certificate policy.
- Not Before, Not After và số ngày còn hiệu lực.
- Key algorithm, key size/curve và tham chiếu tới private key hoặc HSM object.
- Endpoint, môi trường, tenant, application owner và technical owner.
- Trạng thái: requested, issued, deployed, active, expiring, expired, revoked hoặc retired.
- Lần renewal gần nhất, lần kiểm tra endpoint gần nhất và kết quả triển khai.

Monitoring có thể cảnh báo theo nhiều ngưỡng, ví dụ khi còn 30 ngày, 14 ngày, 7 ngày và 1 ngày. Các mốc này là ví dụ; cần điều chỉnh theo thời hạn chứng thư, SLA CA, tốc độ phê duyệt và thời gian rollout. Chứng thư thời hạn ngắn cần lịch tự động hóa dày hơn và cảnh báo theo giờ hoặc ngày.

Nên theo dõi cả hai thời điểm: chứng thư lưu trong inventory và chứng thư endpoint thực sự đang trình bày. Nếu hai giá trị khác nhau, có thể deployment chưa hoàn tất hoặc một node vẫn phục vụ chứng thư cũ.

## 10. Xử lý sự cố trong renewal

### Chứng thư mới được cấp nhưng không khớp private key

Kiểm tra public key trong certificate có khớp với private key hoặc HSM key handle đang được cấu hình không. Không cố dùng chứng thư với khóa khác. Tạo lại CSR bằng đúng private key cần dùng hoặc yêu cầu CA reissue với public key phù hợp.

### Thiếu intermediate certificate

Kiểm tra chain CA cung cấp và cấu hình server. Triển khai đầy đủ intermediate certificates theo hướng dẫn CA. Không giải quyết bằng cách yêu cầu người dùng cài tùy tiện một CA mới vào trust store.

### Chứng thư mới có SAN hoặc EKU sai

Dừng rollout, kiểm tra CSR và profile cấp chứng thư, yêu cầu CA cấp lại đúng thuộc tính. Không tắt hostname verification hoặc nới lỏng policy để làm cho kết nối thành công.

### Một số node vẫn phục vụ chứng thư cũ

Kiểm tra load balancer, listener, ingress, proxy, cache cấu hình, pod/instance và vùng dự phòng. Dùng kiểm tra từ bên ngoài để xác định chứng thư mà từng endpoint đang trả về. Hoàn tất rollout trước khi chứng thư cũ hết hạn.

### CA hoặc private key bị compromise

Đây là sự cố bảo mật, không phải renewal định kỳ. Cô lập khóa, xác định chứng thư và hệ thống bị ảnh hưởng, phát hành key pair và chứng thư thay thế, revoke chứng thư cũ theo chính sách, cập nhật trust store hoặc distrust CA nếu cần, rồi xác minh các client đã áp dụng thay đổi.

## 11. Thu hồi chứng thư cũ và quản lý private key

Chứng thư cũ không phải lúc nào cũng cần revoke khi được thay thế bình thường. Nếu chứng thư hết hạn theo lịch và private key vẫn được bảo vệ, việc retire và ngừng triển khai có thể đủ theo policy. Nếu private key bị lộ, chứng thư phát hành sai hoặc danh tính không còn hợp lệ, cần revoke sớm và cập nhật trạng thái qua CRL/OCSP hoặc cơ chế CA cung cấp.

Sau khi renewal hoàn tất:

- Cập nhật inventory để đánh dấu chứng thư mới active và chứng thư cũ retired/revoked/expired đúng trạng thái.
- Xóa cấu hình và bản sao chứng thư cũ khỏi endpoint khi không còn cần.
- Giữ public certificate, chain, serial, timestamp và audit record khi cần xác minh lịch sử.
- Hủy private key cũ khi không còn nhu cầu hợp lệ, theo chính sách key destruction và kiểm soát backup.
- Nếu private key cũ được giữ để giải mã hoặc xác minh theo yêu cầu đặc thù, giới hạn quyền, mục đích và thời hạn lưu giữ.
- Không hủy CA private key chỉ vì một chứng thư leaf được gia hạn; CA key có vòng đời và phạm vi phụ thuộc riêng.

## 12. Bảo mật và kiểm soát trong quá trình renewal

Renewal là thao tác nhạy cảm vì có thể thay đổi danh tính mà client tin cậy. Cần kiểm soát cả private key và quy trình cấp chứng thư.

- **Xác minh CSR:** xác thực người gửi, public key, subject/SAN và mục đích sử dụng.
- **Bảo vệ private key:** giới hạn quyền đọc và sử dụng; ưu tiên HSM hoặc cơ chế non-exportable khi phù hợp.
- **Tách quyền:** người yêu cầu, người phê duyệt và người triển khai không nhất thiết là cùng một người.
- **Bảo vệ kênh cấp phát:** nhận certificate và chain từ CA qua kênh xác thực; kiểm tra fingerprint hoặc chữ ký theo quy trình.
- **Kiểm soát thay đổi:** ghi nhận phiên bản, endpoint, thời điểm triển khai, người thao tác và kết quả.
- **Giới hạn thuật toán:** không cấp chứng thư với thuật toán hoặc độ dài khóa đã bị policy loại bỏ.
- **Bảo vệ automation:** quản lý API token, DNS credential, ACME account key và quyền chạy hook theo nguyên tắc tối thiểu.
- **Kiểm thử thất bại:** mô phỏng CA không khả dụng, challenge thất bại, endpoint reload lỗi và chứng thư sai SAN.

## 13. Ví dụ: gia hạn chứng thư cho API production

Một API doanh nghiệp dùng chứng thư TLS có SAN `api.example.com` và `api.internal.example.com`. Chứng thư còn 30 ngày hiệu lực. Nhóm vận hành cần gia hạn mà không làm gián đoạn kết nối.

1. Inventory phát cảnh báo và xác định owner, endpoint, issuer, SAN và private key hiện tại.
2. Owner xác nhận các SAN còn đúng và CA vẫn được trust store của client chấp nhận.
3. Nhóm vận hành tạo key pair mới trong HSM hoặc môi trường được bảo vệ, rồi tạo CSR chứa SAN cần thiết.
4. CA xác minh quyền kiểm soát tên miền và phát hành chứng thư mới.
5. Nhóm PKI kiểm tra chain, SAN, EKU, thời hạn và public key; đối chiếu với private key mới.
6. Chứng thư mới được triển khai lên staging và kiểm tra bằng client đại diện cho production.
7. Triển khai lần lượt lên các production node, kiểm tra từng endpoint và xác nhận mọi node phục vụ chứng thư mới.
8. Theo dõi lỗi TLS, mTLS và cảnh báo expiry; sau khi ổn định, retire chứng thư cũ và xử lý private key cũ theo policy.
9. Cập nhật inventory, change record và audit evidence.

Nếu CA phát hành chain mới, trust anchor tương ứng cần được phân phối và kiểm thử trước khi chuyển endpoint. Nếu CA không thay đổi và chain vẫn được client tin cậy, thông thường chỉ cần triển khai leaf certificate và intermediate chain đúng cách.

## 14. Checklist certificate renewal

- [ ] Đã kiểm kê chứng thư, endpoint, owner và thời hạn hiệu lực.
- [ ] Đã xác nhận subject, SAN, EKU, Key Usage và certificate policy.
- [ ] Đã đánh giá giữ key pair hay rekey; quyết định có lý do và được phê duyệt.
- [ ] Private key mới được tạo bằng cơ chế an toàn và có quyền truy cập phù hợp.
- [ ] CSR được tạo từ đúng public key và không làm lộ private key.
- [ ] CA đã xác minh danh tính/quyền kiểm soát và phát hành chứng thư đúng yêu cầu.
- [ ] Đã kiểm tra certificate, fingerprint, serial, validity và chain.
- [ ] Chứng thư cùng intermediate chain đã được triển khai lên mọi endpoint.
- [ ] Hostname verification, revocation checking và mTLS đã được kiểm thử.
- [ ] Đã kiểm tra chứng thư endpoint thực tế, không chỉ file trong kho.
- [ ] Đã xử lý chứng thư và private key cũ theo trạng thái, retention và policy.
- [ ] Inventory, audit log, owner và lịch cảnh báo đã được cập nhật.

Certificate renewal duy trì khả năng xác minh danh tính khi chứng thư tiến tới hết hạn. Quy trình an toàn cần kết hợp quản lý private key, CSR, xác minh CA, kiểm tra chain, triển khai đồng bộ và giám sát endpoint thực tế. Khi renewal được phối hợp với rekey phù hợp, thu hồi đúng lúc và quản lý vòng đời có kiểm soát, tổ chức giảm nguy cơ gián đoạn dịch vụ và hạn chế thời gian phơi nhiễm của khóa riêng.
