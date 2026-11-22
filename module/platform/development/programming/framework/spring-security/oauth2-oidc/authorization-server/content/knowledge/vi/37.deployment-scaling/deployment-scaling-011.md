# Kế hoạch backup, disaster recovery và ứng phó sự cố khóa ký

Authorization Server là thành phần tin cậy trong hệ thống OAuth 2.0 / OpenID Connect. Nếu máy chủ ngừng hoạt động, client có thể không bắt đầu được luồng đăng nhập, đổi authorization code hoặc làm mới token. Nếu database bị mất, máy chủ có thể không còn biết authorization, consent và refresh token nào đang tồn tại. Nếu khóa ký bị mất hoặc bị lộ, việc phát hành và xác minh JWT có thể bị gián đoạn hoặc không còn đáng tin cậy.

Với Spring Authorization Server, kế hoạch khôi phục phải bảo vệ đồng thời dữ liệu nghiệp vụ, khóa ký, cấu hình issuer, bí mật client và hạ tầng cần để phục vụ endpoint. Một bản backup database đơn lẻ không đủ để khôi phục một Authorization Server đang vận hành an toàn.

## 1. Xác định mục tiêu khôi phục và phạm vi sự cố

Trước khi chọn công nghệ backup, đội vận hành cần thống nhất hai chỉ số:

- **RPO (Recovery Point Objective)**: lượng dữ liệu tối đa có thể chấp nhận mất, tính theo thời gian. RPO 5 phút nghĩa là sau sự cố, dữ liệu được khôi phục có thể thiếu tối đa khoảng 5 phút giao dịch gần nhất.
- **RTO (Recovery Time Objective)**: thời gian tối đa cho phép để đưa dịch vụ trở lại trạng thái hoạt động đáp ứng yêu cầu. RTO 30 phút nghĩa là mục tiêu khôi phục dịch vụ trong vòng 30 phút kể từ khi sự cố được xác nhận.

RPO và RTO cần được xác định theo tác động của từng loại dữ liệu. Một Authorization Server có thể chịu được việc phải yêu cầu người dùng consent lại trong một số tình huống, nhưng không thể tùy tiện làm sống lại refresh token đã bị thu hồi. Tương tự, khóa ký có thể được lưu trong HSM hoặc KMS với cơ chế dự phòng riêng, trong khi database được phục hồi từ bản backup và transaction log.

Phân loại các tình huống trước khi viết runbook:

| Tình huống | Tác động chính | Mục tiêu xử lý |
|---|---|---|
| Một instance hoặc một node bị lỗi | Giảm năng lực phục vụ | Chuyển traffic sang node khỏe |
| Mất một vùng triển khai | Dịch vụ không còn sẵn sàng tại vùng đó | Chuyển sang vùng DR |
| Database hỏng hoặc mất dữ liệu | Mất authorization, consent, client hoặc trạng thái token | Phục hồi dữ liệu nhất quán |
| Mất quyền truy cập khóa ký | Không thể ký token mới | Khôi phục quyền truy cập khóa hoặc kích hoạt khóa dự phòng |
| Khóa ký bị lộ | Token có thể bị giả mạo | Cô lập khóa, thay khóa và xử lý token bị ảnh hưởng |
| Cấu hình hoặc chứng thư TLS lỗi | Endpoint hoặc trust chain không hoạt động | Khôi phục cấu hình và chứng thư hợp lệ |

High availability (HA) và disaster recovery (DR) giải quyết hai vấn đề khác nhau. HA giảm gián đoạn do lỗi instance hoặc thành phần đơn lẻ; DR phục hồi sau sự cố lớn làm mất cả vùng, dữ liệu hoặc tài sản mật mã. Một cụm nhiều replica dùng chung database vẫn có thể mất toàn bộ dịch vụ nếu database hoặc KMS ở vùng đó gặp sự cố.

## 2. Kiểm kê những tài sản phải backup

Hãy lập danh mục tài sản, chủ sở hữu, nguồn lưu trữ, mức độ nhạy cảm, tần suất backup và cách phục hồi. Với Spring Authorization Server, tối thiểu cần xem xét:

| Tài sản | Nội dung cần bảo vệ | Hậu quả nếu thiếu |
|---|---|---|
| Registered clients | Client ID, redirect URI, grant type, authentication method, scope, cấu hình token | Client không thể xác thực hoặc yêu cầu quyền đúng |
| Authorization records | Authorization code, access token, refresh token, trạng thái token và metadata liên quan | Luồng refresh, revoke, introspection hoặc truy vết authorization bị ảnh hưởng |
| Consent records | Principal, client và các authority đã được chấp thuận | Người dùng có thể phải consent lại hoặc trạng thái chấp thuận không còn chính xác |
| Khóa ký | Private key hoặc quyền sử dụng khóa trong KMS/HSM; key ID, thuật toán và trạng thái vòng đời | Không thể ký JWT hoặc có nguy cơ mất khả năng xác minh token cũ |
| Cấu hình issuer | Issuer URI, endpoint, thuật toán, TTL, chính sách token | Metadata OIDC/OAuth2 không nhất quán với token đã phát hành |
| Bí mật ứng dụng | Secret kết nối DB, KMS/HSM, mã hóa, hàng đợi và dịch vụ phụ trợ | Dịch vụ không thể kết nối các thành phần sau phục hồi |
| TLS và DNS | Certificate, private key TLS, chain, cấu hình DNS và load balancer | Client/resource server không thể kết nối an toàn |
| Hạ tầng triển khai | Image/version, manifest, policy, network, secret reference và cấu hình runtime | Không thể tái tạo môi trường chạy nhất quán |

Trong Spring Authorization Server, các abstraction lưu trữ như **RegisteredClientRepository**, **OAuth2AuthorizationService** và **OAuth2AuthorizationConsentService** đại diện cho những nhóm dữ liệu khác nhau. Nếu dùng JDBC, cần backup đúng database/schema chứa các bảng tương ứng. Nếu dùng implementation tùy chỉnh, phải kiểm kê cả database, object store hoặc hệ thống bên ngoài mà implementation đó sử dụng.

Không đưa private key, client secret dạng rõ, password database hoặc KMS credential vào cùng một gói backup thông thường. Backup dữ liệu và backup khóa cần có quyền truy cập, mã hóa và quy trình khôi phục riêng. Một bản backup chỉ đọc được khi người quản trị vẫn còn quyền truy cập khóa giải mã mới có giá trị thực tế.

## 3. Thiết kế chiến lược backup

Một chiến lược thường kết hợp ba lớp:

1. **Backup định kỳ**: tạo bản full backup theo lịch, sau đó dùng incremental hoặc differential backup để giảm dung lượng và thời gian.
2. **Point-in-time recovery (PITR)**: giữ transaction log hoặc write-ahead log để phục hồi database tới một thời điểm cụ thể trước khi lỗi xảy ra.
3. **Bản sao tách biệt**: sao chép backup tới vùng hoặc tài khoản lưu trữ độc lập, có chính sách immutable/object lock để giảm nguy cơ bị mã hóa hoặc xóa cùng môi trường production.

Với database quan hệ, ưu tiên cơ chế backup nhất quán của hệ quản trị database. Chỉ copy thư mục dữ liệu đang chạy có thể tạo ra snapshot không nhất quán nếu không phối hợp với cơ chế snapshot/checkpoint của database. Nếu database phân tán hoặc có nhiều schema, phải xác định ranh giới transaction và thứ tự phục hồi giữa các thành phần.

Mỗi bản backup nên có manifest chứa tối thiểu:

- Thời điểm bắt đầu và hoàn thành backup, timezone và backup ID.
- Database/schema, môi trường và phiên bản ứng dụng liên quan.
- Điểm phục hồi hoặc transaction log sequence cần dùng.
- Phiên bản cấu hình issuer, RegisteredClient và chính sách token.
- Phiên bản/key ID của khóa ký hiện hành và danh sách khóa công khai tương ứng.
- Trạng thái mã hóa, vị trí lưu, checksum và kết quả kiểm tra tính toàn vẹn.
- Người hoặc hệ thống tạo backup, kết quả và cảnh báo nếu có.

Đối với khóa ký, dùng khả năng backup/replication được hỗ trợ bởi HSM hoặc KMS. Nếu private key được lưu trong keystore, bảo vệ file keystore và password bằng các hệ thống quản lý bí mật tách biệt. Không lưu password giải mã ngay cạnh file backup. Với khóa không thể export khỏi HSM, kế hoạch DR phải dựa trên cơ chế backup/replication của nhà cung cấp, thiết bị dự phòng hoặc quy trình tạo khóa thay thế đã được phê duyệt.

Áp dụng nguyên tắc 3-2-1 khi phù hợp: có nhiều bản sao, lưu trên ít nhất hai loại phương tiện hoặc miền lỗi khác nhau, và có ít nhất một bản sao ngoài site/tài khoản production. Bản sao ngoài site cần có kiểm soát truy cập riêng; tài khoản chạy Authorization Server không nên có quyền xóa backup bất biến.

## 4. Giữ database và khóa ký nhất quán

Authorization Server phát hành token bằng khóa ký và lưu trạng thái authorization/consent trong kho dữ liệu. Hai nhóm tài sản này phải được quản lý như một bộ khôi phục có quan hệ với nhau.

Ví dụ, database được phục hồi về thời điểm T1 nhưng key store chỉ còn khóa được tạo ở T2. Máy chủ có thể vẫn ký được token, nhưng không thể tái dựng đúng lịch sử key ID, trạng thái khóa hoặc cấu hình đã dùng ở T1. Ngược lại, khôi phục database nhưng mất private key cũ có thể khiến hệ thống không còn khả năng tiếp tục ký bằng khóa cũ hoặc phục hồi cấu hình rotation.

Hãy lưu metadata khóa cùng bản backup cấu hình: **kid**, thuật toán, loại khóa, thời điểm tạo, thời điểm bắt đầu ký, thời điểm ngừng ký, trạng thái hiện tại và vị trí lưu khóa. Private key phải được bảo vệ riêng; public key có thể được lưu trong manifest để đối chiếu và công bố lại khi phục hồi.

Với mỗi điểm phục hồi database, cần biết:

- Những RegisteredClient nào tồn tại tại thời điểm đó.
- Authorization và consent đã được lưu tới transaction nào.
- Khóa nào đã được dùng để ký token tại thời điểm đó.
- Những public key nào phải tiếp tục được công bố để xác minh token còn hiệu lực.
- Những khóa nào đã bị thu hồi hoặc không còn được tin cậy.

Không giả định rằng khôi phục database cũ sẽ tự động khôi phục đúng trạng thái token. Một snapshot có thể bỏ sót thao tác revoke diễn ra sau thời điểm snapshot. Nếu refresh token đã bị thu hồi sau snapshot nhưng bản backup cũ được phục hồi, trạng thái cũ có thể khiến token đó xuất hiện như chưa bị thu hồi. Vì vậy, khi phục hồi có mất giao dịch, phải đánh giá tác động đến token và consent trước khi mở lại endpoint.

## 5. Quản lý vòng đời và rotation khóa ký

Spring Authorization Server có thể dùng **JWKSource<SecurityContext>** để cung cấp khóa cho quá trình ký JWT và công bố JWK Set tại endpoint tương ứng. Hệ thống cần duy trì key ring có kiểm soát thay vì tạo một cặp khóa ngẫu nhiên mới mỗi lần ứng dụng khởi động.

Mỗi khóa cần có **kid** duy nhất và thuật toán được cho phép. Private key chỉ được dùng cho hoạt động ký; public key tương ứng được công bố để resource server và client kiểm tra chữ ký. Nếu dùng KMS/HSM, lớp tích hợp cần bảo đảm thao tác ký được thực hiện bởi khóa đã chọn và JWK công bố khớp với public key của khóa đó.

Quy trình rotation thông thường:

1. Tạo khóa mới trong KMS/HSM hoặc keystore được bảo vệ; ghi nhận **kid**, thuật toán và chủ sở hữu.
2. Kiểm tra public key và cấu hình JWK Set. Công bố public key mới trước khi bắt đầu ký bằng khóa đó để resource server có thời gian tải và cache.
3. Chuyển Authorization Server sang ký token mới bằng khóa mới; kiểm tra token header có **kid** mới và chữ ký xác minh được.
4. Tiếp tục công bố public key cũ trong khoảng thời gian cần thiết để xác minh token đã phát hành bằng khóa cũ.
5. Chỉ ngừng công bố public key cũ sau khi mọi token được ký bằng khóa đó đã hết hạn, cộng thêm clock skew, thời gian cache JWKS và khoảng an toàn vận hành.
6. Lưu trữ hoặc hủy private key cũ theo chính sách mật mã và lưu giữ bằng chứng rotation.

Không tái sử dụng **kid** cho một cặp khóa khác. Không xóa public key cũ ngay sau khi bắt đầu ký bằng khóa mới, vì resource server vẫn có thể cần xác minh token còn hiệu lực được ký trước đó.

Nếu private key cũ bị nghi ngờ hoặc xác nhận bị lộ, quy trình khẩn cấp khác với rotation thông thường: cần loại bỏ khả năng tin cậy khóa bị ảnh hưởng và đánh giá token được ký bằng khóa đó. Việc chỉ chuyển sang khóa mới không làm mất hiệu lực những JWT cũ nếu resource server vẫn tin public key cũ.

## 6. Kế hoạch khôi phục Authorization Server

Runbook DR nên chỉ rõ người điều phối, người phụ trách database, người quản lý khóa, người vận hành ứng dụng, người phê duyệt và kênh liên lạc sự cố. Các bước tổng quát như sau:

### Bước 1: Xác nhận sự cố và cô lập phạm vi

Xác định lỗi nằm ở instance, vùng triển khai, database, KMS/HSM, chứng thư hay cấu hình. Nếu có dấu hiệu xâm nhập hoặc khóa bị lộ, giới hạn quyền truy cập và giữ lại log, audit trail, snapshot và bằng chứng liên quan. Không xóa tài nguyên hoặc xoay vòng khóa một cách vội vàng trước khi ghi nhận trạng thái hiện tại.

### Bước 2: Chọn điểm phục hồi

Chọn backup gần nhất đã được kiểm tra tính toàn vẹn và đáp ứng RPO. Nếu cần PITR, xác định chính xác transaction log cần phát lại và thời điểm dừng. Kiểm tra backup khóa ký, metadata key ring, secret cần thiết và cấu hình issuer tương ứng.

Nếu bản backup có thể chứa dữ liệu đã bị xâm nhập, không phục hồi nó vào môi trường production mà chưa đánh giá. Khi có nhiều bản backup, ưu tiên điểm phục hồi sạch đã xác minh thay vì chỉ chọn bản mới nhất.

### Bước 3: Phục hồi hạ tầng và dữ liệu

Tạo môi trường phục hồi có network policy, secret access và quyền tối thiểu. Phục hồi database vào môi trường cô lập trước, chạy kiểm tra integrity và xác nhận schema/version tương thích với ứng dụng. Phục hồi quyền truy cập khóa ký qua HSM/KMS hoặc keystore đã được bảo vệ; kiểm tra **kid**, thuật toán và public key.

Khôi phục cấu hình issuer và endpoint sao cho issuer URI không thay đổi ngoài kế hoạch. Token đã phát hành chứa claim **iss**; nếu issuer sau phục hồi khác issuer trước đó, resource server có thể từ chối token hoặc metadata OIDC không còn nhất quán.

### Bước 4: Khởi động và kiểm chứng trước khi nhận traffic

Khởi động một instance trong môi trường kiểm tra, sau đó xác minh:

- Discovery metadata trả về issuer và endpoint đúng.
- JWKS endpoint công bố các public key cần thiết, có **kid** và thuật toán phù hợp.
- Registered client được tải đúng và có redirect URI, grant type, scope như mong đợi.
- Authorization code flow, PKCE, token exchange và refresh token hoạt động theo cấu hình.
- Consent cũ được đọc đúng.
- Introspection và revocation hoạt động nếu hệ thống sử dụng các endpoint này.
- Audit event được ghi và có thể liên kết với correlation/trace ID.
- Thời gian hệ thống đồng bộ; TLS certificate, DNS, load balancer và kết nối database/KMS đều hợp lệ.

Dùng tài khoản và client kiểm thử được kiểm soát, không dùng token thật trong log hoặc lệnh kiểm tra. Kiểm tra cả đường đi thành công lẫn các trường hợp bị từ chối. Chỉ mở traffic sau khi người chịu trách nhiệm xác nhận dữ liệu và khóa đúng.

### Bước 5: Chuyển traffic và theo dõi sau phục hồi

Chuyển traffic theo từng bước nếu kiến trúc cho phép. Theo dõi tỷ lệ lỗi ở authorization endpoint, token endpoint, JWKS, introspection và revocation; theo dõi lỗi kết nối database/KMS, thời gian phản hồi và số lần refresh thất bại. Giữ khả năng quay lại vùng DR hoặc node cũ cho tới khi trạng thái ổn định và đã có quyết định chính thức.

Sau khi dịch vụ hoạt động, tạo một bản backup mới, xác minh lịch backup tiếp tục chạy và ghi lại điểm dữ liệu bị mất (nếu có), thời gian phục hồi thực tế và các hành động cần cải thiện.

## 7. Xử lý hệ quả khi database authorization được phục hồi trễ

Đây là phần cần được đánh giá riêng trước khi mở dịch vụ. JWT access token có thể được resource server xác minh cục bộ bằng chữ ký và thời hạn mà không truy vấn database của Authorization Server. Do đó, database bị phục hồi về trạng thái cũ không nhất thiết làm token JWT đã phát hành tự động mất hiệu lực.

Tuy nhiên, database chứa trạng thái quan trọng cho các thao tác tiếp theo:

- Refresh token có thể không còn khớp với trạng thái rotation hiện tại.
- Token đã bị revoke sau điểm backup có thể bị mất dấu.
- Authorization mới được tạo sau snapshot có thể không tồn tại.
- Consent mới hoặc consent bị gỡ bỏ có thể bị mất.
- Introspection có thể trả kết quả dựa trên dữ liệu cũ nếu nó phụ thuộc kho authorization.

Khi có nguy cơ phục hồi trạng thái cũ, không thể chỉ kiểm tra ứng dụng khởi động thành công rồi mở traffic. Cần so sánh thời điểm snapshot với audit log, transaction log hoặc nguồn sự kiện độc lập để xác định các thao tác revoke và thay đổi consent bị thiếu.

Nếu không thể tái dựng đầy đủ trạng thái, đội vận hành phải chọn biện pháp giảm rủi ro phù hợp, ví dụ vô hiệu hóa các refresh token bị ảnh hưởng, yêu cầu xác thực lại, yêu cầu consent lại khi cần hoặc áp dụng chính sách thu hồi diện rộng. Cơ chế vô hiệu hóa hàng loạt hay kiểm tra phiên toàn cục thường cần được thiết kế ở tầng ứng dụng/resource server; Spring Authorization Server không tự cung cấp một công tắc chung có thể thu hồi tức thì mọi JWT đã phát hành trên mọi resource server.

Ghi rõ phạm vi token và client bị ảnh hưởng, thời điểm bắt đầu/kết thúc, quyết định vận hành và tác động tới người dùng. Không tuyên bố đã thu hồi JWT chỉ vì đã xóa bản ghi authorization trong database: resource server xác minh JWT ngoại tuyến có thể vẫn chấp nhận token cho tới khi hết hạn hoặc có cơ chế kiểm tra trạng thái khác.

## 8. Runbook ứng phó sự cố khóa ký

Các tình huống về khóa ký có mức độ ảnh hưởng khác nhau. Cần phân biệt mất khả năng sử dụng khóa với mất tính bí mật của khóa.

| Sự cố | Dấu hiệu | Hành động ưu tiên |
|---|---|---|
| KMS/HSM tạm thời không truy cập được | Lỗi ký, timeout hoặc lỗi quyền | Chuyển sang vùng/thiết bị dự phòng theo quy trình; giữ nguyên khóa và kiểm tra audit KMS |
| Private key bị mất hoặc không thể khôi phục | Không còn quyền ký bằng **kid** đang hoạt động | Tạo khóa thay thế đã phê duyệt, công bố public key mới và đánh giá token cũ |
| Private key bị nghi ngờ lộ | Truy cập bất thường, export trái phép hoặc dấu hiệu giả mạo JWT | Cô lập khóa, ngừng ký bằng khóa đó, bảo toàn bằng chứng và kích hoạt quy trình compromise |
| Khóa bị xác nhận lộ | Có bằng chứng bên ngoài có thể dùng private key | Loại bỏ trust đối với public key bị ảnh hưởng và xử lý token đã ký bằng khóa đó |
| Public key bị xóa nhầm khỏi JWKS | Resource server không xác minh được token hợp lệ | Khôi phục JWK công khai đúng và kiểm tra cache/refresh của resource server |
| Khóa hết hạn hoặc thuật toán không còn được phép | Lỗi ký/xác minh hoặc policy từ chối | Rotation theo kế hoạch, cập nhật thuật toán và kiểm tra tương thích |

### Khi khóa chỉ tạm thời không truy cập được

1. Xác minh lỗi đến từ KMS/HSM, network, policy hay credential.
2. Kiểm tra audit log của KMS/HSM và tình trạng vùng dự phòng.
3. Chuyển sang endpoint hoặc thiết bị dự phòng theo hướng dẫn của nhà cung cấp.
4. Xác nhận cùng **kid** và public key vẫn được sử dụng trước khi tiếp tục phát hành token.
5. Theo dõi lỗi ký và kiểm tra một token thử nghiệm bằng public key tương ứng.

Không tự động tạo một khóa ngẫu nhiên mới mỗi khi KMS tạm ngừng hoạt động. Nếu ứng dụng khởi động với khóa mới không được quản lý, resource server có thể không biết public key đó và token mới sẽ không xác minh được.

### Khi private key bị mất

1. Xác định khóa nào mất, **kid** nào đang được dùng và các token nào còn hạn.
2. Kiểm tra khả năng phục hồi từ HSM/KMS backup hoặc keystore backup đã xác minh.
3. Nếu không thể phục hồi, tạo khóa mới với quy trình kiểm soát và phê duyệt phù hợp.
4. Công bố public key mới trước khi ký token bằng khóa mới.
5. Quyết định cách xử lý token cũ. Nếu public key cũ vẫn có sẵn và khóa không bị lộ, resource server có thể tiếp tục xác minh token cũ đến khi hết hạn. Nếu public key cũ cũng mất, phải đánh giá cách phục hồi public key từ backup hoặc kế hoạch yêu cầu người dùng xác thực lại.
6. Cập nhật manifest, backup và inventory khóa.

Mất private key không đồng nghĩa khóa đã bị lộ. Nếu có thể xác minh rằng khóa vẫn bí mật, giữ public key cũ trong JWKS cho đến khi token hết hạn giúp giảm gián đoạn. Nếu không thể chứng minh tính bí mật, xử lý như sự cố compromise.

### Khi private key bị lộ hoặc nghi ngờ bị lộ

1. Kích hoạt quy trình incident response và ghi nhận thời điểm nghi ngờ đầu tiên.
2. Cô lập quyền sử dụng khóa bị ảnh hưởng trong KMS/HSM; ngừng phát hành token bằng khóa đó.
3. Tạo khóa mới từ nguồn tin cậy, chuyển sang ký bằng **kid** mới và công bố public key mới.
4. Đánh giá token được ký bằng khóa bị lộ, bao gồm access token, ID Token và token khác sử dụng cùng khóa.
5. Loại public key bị xâm phạm khỏi tập khóa được tin cậy và yêu cầu resource server cập nhật JWKS/cache theo cơ chế của hệ thống.
6. Nếu resource server có thể tiếp tục chấp nhận token từ cache cũ, kích hoạt biện pháp thu hồi bổ sung: introspection, denylist, token version/session epoch hoặc chính sách xác thực lại tùy kiến trúc.
7. Kiểm tra log KMS/HSM, quyền truy cập, pipeline triển khai, secret store và bản backup có thể đã chứa khóa bị ảnh hưởng.
8. Thông báo cho các nhóm phụ thuộc theo quy trình sự cố và ghi lại quyết định, phạm vi ảnh hưởng, thời điểm hoàn tất.

Xóa public key khỏi JWKS không bảo đảm mọi resource server lập tức từ chối token đã ký bằng khóa đó. Resource server có thể cache JWK Set trong một khoảng thời gian. Cần biết cache TTL, cơ chế refresh, khả năng ép tải lại và có phương án xử lý khi resource server vẫn giữ public key cũ.

Việc thay khóa ký cũng không tự động thu hồi mọi loại token theo cùng một cách. JWT đã được phát hành có thể còn được chấp nhận ở resource server xác minh ngoại tuyến; opaque token có thể phụ thuộc introspection và trạng thái authorization. Runbook phải nêu rõ từng loại token và hành vi của resource server.

## 9. Duy trì dịch vụ trong thời gian DR

Tùy yêu cầu RTO, có thể chọn một trong các mô hình:

| Mô hình | Cách vận hành | Đánh đổi |
|---|---|---|
| Cold standby | Môi trường DR được tạo khi có sự cố | Chi phí thấp hơn, RTO dài hơn |
| Warm standby | Hạ tầng và một phần dữ liệu đã sẵn sàng | RTO trung bình, cần đồng bộ định kỳ |
| Hot standby | Môi trường dự phòng chạy liên tục và dữ liệu được sao chép gần thời gian thực | RTO thấp hơn, chi phí và độ phức tạp cao hơn |

Với hot standby, cần kiểm soát split-brain. Không để hai Authorization Server độc lập cùng ghi trạng thái authorization hoặc phát hành token theo các key ring khác nhau nếu không có thiết kế đồng bộ và phân vùng rõ ràng. Database replication có độ trễ cũng có thể làm mất thao tác revoke hoặc refresh token mới nhất khi chuyển vùng.

Giữ issuer ổn định giữa production và DR nếu hai vùng đại diện cho cùng một Authorization Server. Đảm bảo DNS, TLS certificate, redirect URI, network policy và resource server đều tương thích với endpoint sau chuyển vùng. Nếu buộc phải thay issuer, đó là thay đổi kiến trúc và cần kế hoạch migration riêng cho client, resource server, discovery metadata và token đang tồn tại.

## 10. Kiểm thử backup và diễn tập disaster recovery

Một backup chỉ được xem là đáng tin khi đã phục hồi thử. Lịch kiểm thử nên bao gồm cả kiểm tra tự động và diễn tập theo kịch bản.

| Kịch bản kiểm thử | Tiêu chí đạt |
|---|---|
| Phục hồi database từ full backup | Schema và dữ liệu đọc được, integrity check thành công |
| PITR tới một thời điểm cụ thể | Dữ liệu khớp với transaction log và điểm phục hồi đã chọn |
| Khôi phục quyền truy cập khóa | KMS/HSM hoặc keystore có thể thực hiện thao tác ký kiểm thử |
| Khôi phục JWK Set | **kid**, thuật toán và public key khớp với token đã phát hành |
| Khôi phục consent và client | Registered client và consent được đọc đúng |
| Phục hồi sau khi mất một vùng | Endpoint, issuer, TLS, database và khóa hoạt động ở vùng DR |
| Phục hồi snapshot cũ | Nhận diện được revoke/refresh/consent bị thiếu và áp dụng chính sách xử lý |
| Ứng phó khóa bị lộ | Khóa bị ảnh hưởng không còn được dùng để ký và resource server từ chối token theo chính sách |
| Chuyển traffic trở lại | Không có split-brain hoặc ghi dữ liệu vào hai nơi không đồng bộ |

Sau mỗi lần diễn tập, đo RPO và RTO thực tế, so sánh với mục tiêu đã thống nhất. Ghi lại thời gian phát hiện, thời gian ra quyết định, thời gian phục hồi database, thời gian khôi phục khóa, thời gian kiểm chứng và thời điểm mở traffic. Các số đo này giúp xác định nút thắt thực sự.

## 11. Checklist vận hành định kỳ

- [ ] Backup database và transaction log chạy đúng lịch; cảnh báo khi job thất bại.
- [ ] Bản backup ngoài site được mã hóa, immutable và có checksum.
- [ ] Quyền truy cập backup tách biệt với quyền runtime của Authorization Server.
- [ ] Khóa ký có inventory gồm **kid**, thuật toán, trạng thái, chủ sở hữu và thời hạn.
- [ ] KMS/HSM có phương án dự phòng và đã kiểm tra quyền khôi phục.
- [ ] Secret giải mã backup được lưu ở nơi độc lập, có kiểm soát truy cập.
- [ ] Public key cũ còn được công bố đủ lâu theo thời hạn token và JWKS cache.
- [ ] Issuer, discovery metadata, DNS và TLS certificate được lưu cấu hình và có người chịu trách nhiệm.
- [ ] Diễn tập restore database, khôi phục khóa và chuyển vùng theo lịch.
- [ ] Runbook có người trực, người phê duyệt, kênh liên lạc và tiêu chí mở lại traffic.
- [ ] Audit trail ghi nhận thao tác backup, restore, key rotation và quyền truy cập khóa.
- [ ] Sau mỗi lần restore, đánh giá nguy cơ token bị revoke hoặc consent thay đổi sau điểm backup.

Kế hoạch backup và disaster recovery của Authorization Server chỉ hoàn chỉnh khi có thể khôi phục đồng thời dữ liệu, quyền sử dụng khóa và cấu hình phát hành token, sau đó chứng minh các luồng OAuth 2.0/OpenID Connect vẫn hoạt động đúng. Diễn tập thường xuyên giúp đội vận hành phát hiện sớm những khoảng trống giữa backup thành công trên hệ thống và khả năng phục hồi dịch vụ thực tế.

