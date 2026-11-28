# Automated certificate renewal

Automated certificate renewal là quy trình tự động phát hiện chứng thư sắp hết hạn, tạo yêu cầu cấp mới, xác minh chứng thư được cấp, triển khai đến các hệ thống sử dụng và kiểm tra dịch vụ sau khi thay thế. Mục tiêu là duy trì chuỗi tin cậy và tính sẵn sàng mà không phụ thuộc vào thao tác thủ công vào phút cuối.

Trong quản lý khóa mật mã, chứng thư số liên kết danh tính với khóa công khai. Chứng thư hết hạn có thể khiến kết nối TLS, xác thực dịch vụ, chữ ký hoặc quy trình tích hợp bị từ chối. Việc gia hạn vì vậy phải phối hợp giữa vòng đời chứng thư, bảo vệ khóa riêng, CA, hệ thống triển khai và giám sát. Một quy trình chỉ xin được chứng thư mới nhưng không triển khai hoặc không kiểm tra nó vẫn có thể dẫn đến gián đoạn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vòng đời chứng thư và lý do cần tự động gia hạn.
- Phân biệt gia hạn chứng thư, cấp lại chứng thư và xoay vòng khóa riêng.
- Mô tả vai trò của CA, CSR, private key, public key và ACME.
- Thiết kế chu trình tự động từ phát hiện hết hạn đến triển khai và xác minh.
- Bảo vệ khóa riêng trong quá trình tạo CSR, cấp phát và triển khai chứng thư.
- Xử lý nhiều node, nhiều môi trường, lỗi CA, DNS, challenge và triển khai.
- Thiết lập giám sát, cảnh báo, audit và quy trình khôi phục khi renewal thất bại.

## 2. Chứng thư số và thời hạn hiệu lực

Chứng thư số X.509 là cấu trúc dữ liệu được CA ký để liên kết một public key với danh tính hoặc các tên được phép sử dụng. Với chứng thư TLS máy chủ, các trường thường quan trọng gồm:

- Subject và Subject Alternative Name (SAN): danh tính hoặc tên DNS/IP mà chứng thư áp dụng.
- Public key và thuật toán: khóa công khai cùng thuật toán tương ứng.
- Issuer: CA đã phát hành chứng thư.
- Serial number: số sê-ri do CA cấp.
- Not Before và Not After: thời điểm bắt đầu và kết thúc hiệu lực.
- Key Usage và Extended Key Usage (EKU): mục đích sử dụng được cho phép.
- Chữ ký của CA: bằng chứng chứng thư được phát hành trong chuỗi tin cậy.

Khi thời điểm hiện tại vượt quá Not After, client tuân thủ kiểm tra chứng thư sẽ từ chối chứng thư đã hết hạn. Một chứng thư sắp hết hạn vì thế là tín hiệu cần xử lý trước khi dịch vụ bị ảnh hưởng.

Chứng thư và khóa riêng có quan hệ mật thiết nhưng là hai tài sản khác nhau. Chứng thư thường có thể phân phối công khai; khóa riêng phải được bảo vệ. CA nhận CSR và phát hành chứng thư chứa public key, nhưng không cần nhận private key của máy chủ.

## 3. Vì sao cần tự động gia hạn?

Gia hạn thủ công có thể phù hợp với một số chứng thư nội bộ ít thay đổi, nhưng khó duy trì khi có hàng trăm dịch vụ, nhiều vùng triển khai và chứng thư có thời hạn ngắn. Các lỗi vận hành thường gặp gồm quên ngày hết hạn, không biết owner, CSR sai SAN, chứng thư mới không được phân phối đến mọi node hoặc dịch vụ không reload sau khi file thay đổi.

Tự động renewal mang lại:

1. Giảm nguy cơ chứng thư hết hạn gây gián đoạn kết nối.
2. Giảm thao tác lặp lại và lỗi do con người.
3. Tạo quy trình nhất quán cho phát hành, kiểm tra, triển khai và audit.
4. Hỗ trợ chứng thư thời hạn ngắn mà không cần tăng gánh nặng vận hành thủ công.
5. Tạo dữ liệu quan sát về trạng thái chứng thư, thời gian renewal và lỗi.
6. Kết hợp việc cấp chứng thư với xoay vòng khóa riêng theo chính sách.

Tự động hóa không loại bỏ nhu cầu quản trị. Owner, CA, chính sách SAN, quyền cấp chứng thư, lịch triển khai và cơ chế khẩn cấp vẫn cần được xác định rõ.

## 4. Phân biệt renewal, reissue và key rotation

Ba hoạt động này thường diễn ra gần nhau nhưng không đồng nghĩa:

| Hoạt động | Điều thay đổi | Ví dụ |
|---|---|---|
| Renewal | Cấp chứng thư mới để tiếp tục sử dụng danh tính và dịch vụ; có thể giữ hoặc thay key pair tùy policy | Chứng thư TLS mới có Not After mới |
| Reissue | CA phát hành lại chứng thư, thường do thay đổi SAN, thông tin hoặc lỗi trong chứng thư cũ | Thêm tên api.example.test vào SAN |
| Key rotation | Thay key pair, tức tạo private key và public key mới | Sinh RSA/ECDSA key pair mới rồi gửi CSR mới |

Một quy trình renewal có thể giữ nguyên key pair hoặc tạo key pair mới. Việc giữ khóa cũ giảm thay đổi đối với một số hệ thống nhưng kéo dài thời gian sử dụng của cùng private key. Tạo khóa mới giúp giới hạn thời gian phơi lộ của key pair và hỗ trợ thay thế khi có nghi ngờ rủi ro. Lựa chọn phải theo chính sách bảo mật, khả năng tương thích và hướng dẫn của CA.

Không giả định mỗi lần renewal đều tự động xoay vòng private key. Cần cấu hình rõ hành vi này và kiểm tra chứng thư mới có public key tương ứng với key pair dự kiến hay không.

## 5. Thành phần trong quy trình tự động

Một hệ thống automated certificate renewal thường có các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| Certificate inventory | Lưu certificate ID, SAN, issuer, expiry, owner, environment và endpoint sử dụng |
| Renewal scheduler | Kiểm tra ngày hết hạn và quyết định khi nào bắt đầu renewal |
| ACME client hoặc enrollment agent | Tạo order, thực hiện challenge, gửi CSR và nhận chứng thư |
| CA | Xác minh quyền kiểm soát tên hoặc danh tính, ký và phát hành chứng thư |
| Key provider | Tạo, lưu và sử dụng private key; có thể là file bảo vệ, KMS hoặc HSM |
| Secret/certificate store | Lưu chứng thư, chain và private key theo quyền truy cập phù hợp |
| Deployment controller | Phân phối chứng thư đến workload, proxy, ingress hoặc máy chủ |
| Reload/restart controller | Kích hoạt chứng thư mới trong tiến trình đang phục vụ |
| Health checker | Kiểm tra chứng thư đang được trình ra và dịch vụ còn hoạt động |
| Audit and monitoring | Ghi nhận thay đổi, cảnh báo lỗi và theo dõi hạn dùng |

Không phải hệ thống nào cũng cần một dịch vụ riêng cho từng thành phần. Một ACME client có thể đảm nhiệm scheduler và enrollment; nền tảng orchestration có thể đảm nhiệm phân phối và reload. Điều quan trọng là mỗi bước có owner, trạng thái và bằng chứng hoàn tất.

## 6. ACME và các phương thức xác minh

ACME (Automatic Certificate Management Environment) là giao thức tự động hóa việc yêu cầu và quản lý chứng thư giữa ACME client và CA hỗ trợ giao thức này. Một client tạo order cho các identifier, chứng minh quyền kiểm soát theo challenge, gửi CSR và nhận chứng thư khi order được hoàn tất.

Các challenge ACME phổ biến:

### 6.1. HTTP-01

CA yêu cầu client đặt một token tại đường dẫn well-known trên HTTP của tên miền. CA truy cập endpoint đó để xác minh quyền kiểm soát tên.

Phù hợp với website hoặc dịch vụ có thể phục vụ challenge qua cổng 80. Cần đảm bảo load balancer, reverse proxy và firewall chuyển request challenge đến đúng ACME client. Nếu có nhiều node, mọi node hoặc một điểm điều phối chung phải phục vụ cùng nội dung challenge theo yêu cầu của CA.

### 6.2. DNS-01

ACME client tạo TXT record dưới tên challenge của domain. CA truy vấn DNS để xác minh quyền kiểm soát.

Phương thức này hữu ích khi cấp wildcard certificate hoặc khi dịch vụ không thể nhận HTTP challenge từ Internet. Credential API của DNS provider rất nhạy cảm vì có thể cho phép thay đổi bản ghi DNS. Nên giới hạn quyền vào zone và loại record cần thiết, dùng credential riêng, thời hạn ngắn nếu hỗ trợ và lưu trong secret manager.

DNS propagation có thể mất thời gian. Client cần chờ record có thể được resolver của CA quan sát thay vì chỉ kiểm tra từ một máy nội bộ.

### 6.3. TLS-ALPN-01

CA xác minh challenge qua TLS trên cổng 443 bằng ALPN protocol được quy định. Phương thức này phù hợp với một số môi trường có thể điều khiển điểm kết thúc TLS. Cần kiểm tra proxy, load balancer và TLS termination không làm mất challenge trước khi CA xác minh.

### 6.4. Chọn challenge

Chọn phương thức dựa trên topology, quyền kiểm soát DNS, khả năng mở cổng, yêu cầu wildcard và rủi ro credential. Không cấp quyền DNS rộng chỉ để đơn giản hóa renewal nếu có thể dùng một zone hoặc record scope hẹp hơn.

ACME là một giao thức cụ thể. Với CA nội bộ hoặc PKI doanh nghiệp, enrollment có thể dùng EST, SCEP, API riêng hoặc quy trình cấp chứng thư khác. Các nguyên tắc về xác minh danh tính, bảo vệ private key, kiểm tra chứng thư và triển khai vẫn tương tự.

## 7. Quy trình renewal từ đầu đến cuối

Một quy trình tự động thường gồm các bước sau:

1. Đọc inventory và kiểm tra thời hạn của chứng thư đang sử dụng.
2. Xác định chứng thư đủ điều kiện renewal theo ngưỡng và policy.
3. Kiểm tra owner, SAN, issuer, environment và trạng thái dịch vụ.
4. Tạo hoặc chọn key pair theo chính sách; private key phải được giữ trong nơi bảo vệ.
5. Tạo CSR chứa public key và danh tính/SAN được phê duyệt.
6. Tạo certificate order và hoàn thành challenge để chứng minh quyền kiểm soát identifier.
7. CA xác minh và phát hành chứng thư.
8. Kiểm tra chứng thư mới: chain, SAN, thời hạn, EKU, Key Usage, thuật toán và public key.
9. Đóng gói leaf certificate cùng intermediate chain theo định dạng mà server yêu cầu.
10. Phân phối artifact đến các node hoặc workload bằng cơ chế bảo mật.
11. Kích hoạt cấu hình mới bằng reload hoặc rolling deployment.
12. Kết nối tới endpoint và xác minh chứng thư thực sự được trình ra.
13. Cập nhật inventory, trạng thái renewal và audit record.
14. Theo dõi health check và cảnh báo nếu một node vẫn dùng chứng thư cũ.

Renewal chỉ được xem là hoàn tất khi chứng thư mới đã được triển khai và các endpoint cần thiết đã trình đúng chứng thư. Việc CA trả về chứng thư thành công mới chỉ hoàn thành bước cấp phát.

## 8. Thời điểm bắt đầu renewal

Không nên đợi đến sát Not After mới bắt đầu. Quy trình cần có khoảng đệm để xử lý CA chậm, DNS propagation, lỗi mạng, phê duyệt hoặc triển khai nhiều vùng.

Một cách đơn giản là bắt đầu renewal khi thời gian còn lại nhỏ hơn một ngưỡng:

~~~text
remaining = certificate.notAfter - currentTime

if remaining <= renewalWindow:
    startRenewal()
~~~

renewalWindow cần được chọn theo thời hạn chứng thư, tốc độ cấp của CA, lịch triển khai, khả năng retry và mức độ quan trọng của dịch vụ. Với chứng thư thời hạn ngắn, có thể dùng tỷ lệ của lifetime thay vì một số ngày cố định. Cần kiểm tra policy hiện hành của CA vì thời hạn chứng thư và yêu cầu renewal có thể thay đổi.

Để tránh nhiều node cùng gửi yêu cầu một lúc, dùng jitter trong lịch chạy. Scheduler cần idempotent: nhiều lần kiểm tra cùng một chứng thư không tạo ra nhiều order hoặc nhiều lần deploy không cần thiết.

Đối với chứng thư đã có order đang xử lý, scheduler nên tiếp tục theo dõi trạng thái order thay vì tạo order mới liên tục. Cần có lock hoặc cơ chế điều phối để tránh hai controller đồng thời thay đổi cùng một certificate resource.

## 9. Tạo CSR và bảo vệ private key

CSR (Certificate Signing Request) chứa public key và thông tin danh tính mà requester muốn CA chứng nhận. CSR được ký bằng private key tương ứng để chứng minh requester nắm giữ khóa.

Quy trình đúng:

1. Tạo key pair trong file bảo vệ, KMS hoặc HSM theo yêu cầu.
2. Giữ private key trong ranh giới bảo vệ và giới hạn quyền truy cập.
3. Tạo CSR chứa public key, subject và SAN đã được policy cho phép.
4. Ký CSR bằng private key tương ứng.
5. Gửi CSR đến CA qua kênh được bảo vệ.
6. Nhận chứng thư chứa public key tương ứng.

Private key không cần và không nên được gửi đến CA. Chỉ CSR và thông tin cần thiết để cấp chứng thư được gửi. Nếu dùng HSM hoặc KMS có khả năng tạo và giữ khóa không exportable, CSR có thể được ký thông qua thao tác ký của thiết bị theo tích hợp được hỗ trợ.

### 9.1. Có nên tái sử dụng private key?

Tái sử dụng private key trong nhiều lần renewal có thể giảm thay đổi cấu hình nhưng làm tăng thời gian khóa tồn tại. Nếu private key bị lộ, tất cả chứng thư còn dựa trên key pair đó đều có thể bị ảnh hưởng.

Tạo key pair mới khi renewal giúp thực hiện key rotation cùng lúc. Cần kiểm tra:

- Dịch vụ có hỗ trợ thay key pair mà không gián đoạn không?
- Có consumer hoặc pinning policy phụ thuộc public key cũ không?
- Chứng thư client hoặc mTLS có cần cập nhật ở cả hai phía không?
- HSM/KMS có hỗ trợ tạo, ký CSR và sử dụng khóa mới theo policy không?
- Có cần giữ chứng thư và khóa cũ trong thời gian chuyển tiếp để tương thích không?

Nếu nghi ngờ private key bị lộ, không chỉ renewal bình thường. Cần tạo key pair mới, cấp chứng thư mới, thu hồi hoặc vô hiệu hóa chứng thư cũ theo quy trình sự cố và đánh giá nơi khóa cũ đã được sử dụng.

## 10. Xác minh chứng thư trước khi triển khai

Không nên triển khai ngay file mà CA vừa trả về. Hệ thống cần xác minh chứng thư theo policy mong đợi:

- SAN chứa đúng toàn bộ DNS name hoặc IP được yêu cầu, không thừa tên ngoài phạm vi.
- Issuer thuộc CA hoặc trust chain được phê duyệt.
- Chữ ký của certificate chain hợp lệ và intermediate chain đầy đủ.
- Not Before và Not After phù hợp; đồng hồ hệ thống được đồng bộ.
- Key Usage và EKU phù hợp vai trò, ví dụ serverAuth hoặc clientAuth.
- Thuật toán và kích thước khóa đáp ứng policy hiện hành.
- Public key trong certificate khớp với private key mà workload sẽ sử dụng.
- Certificate không bị thu hồi theo cơ chế kiểm tra áp dụng.
- Basic Constraints và các extension liên quan phù hợp với loại chứng thư.

Kiểm tra key pair có thể thực hiện bằng cách so sánh public key lấy từ certificate với public key suy ra từ private key, hoặc ký và xác minh một challenge kiểm thử theo cơ chế phù hợp. Không cần xuất private key khỏi HSM chỉ để kiểm tra sự khớp này.

Nếu bất kỳ kiểm tra bắt buộc nào thất bại, đánh dấu issuance là không hợp lệ, giữ chứng thư đang hoạt động và phát cảnh báo. Không ghi đè chứng thư hiện tại bằng artifact chưa được xác minh.

## 11. Triển khai chứng thư đến dịch vụ

Chứng thư mới cần được phân phối đến đúng nơi kết thúc TLS hoặc thực hiện xác thực. Ví dụ:

- Web server hoặc reverse proxy.
- Load balancer hoặc API gateway.
- Kubernetes Ingress hoặc service mesh.
- Client dùng mTLS.
- Agent hoặc workload kết nối PKI nội bộ.

Private key và certificate chain phải được triển khai như một bộ nhất quán. Không ghép chứng thư mới với private key cũ. Phân quyền đọc private key cần giới hạn cho tiến trình thực sự cần sử dụng.

Một phương thức triển khai an toàn:

1. Ghi chứng thư và private key mới vào thư mục phiên bản riêng hoặc secret store version mới.
2. Kiểm tra file permission, owner, định dạng và sự khớp giữa certificate với key.
3. Cập nhật tham chiếu cấu hình đến bộ artifact mới bằng thao tác nguyên tử khi nền tảng hỗ trợ.
4. Reload hoặc rolling restart theo cơ chế của dịch vụ.
5. Kiểm tra process đã nạp certificate mới và không có lỗi TLS.
6. Chỉ sau khi health check thành công mới đánh dấu deployment là active.

Không ghi private key vào log hoặc in nội dung secret khi chẩn đoán. Nếu dùng container, không đóng gói private key vào image vì image có thể được sao chép rộng và tồn tại lâu hơn vòng đời chứng thư.

## 12. Triển khai trên nhiều node và nhiều vùng

Một chứng thư có thể được dùng bởi nhiều node, nhiều load balancer hoặc nhiều vùng. Việc cập nhật chỉ một node không đảm bảo toàn bộ dịch vụ đã renewal.

Hệ thống nên duy trì inventory mapping giữa certificate, endpoint, node và workload. Deployment controller cần:

- Phân phối cùng phiên bản certificate đến tất cả target được đăng ký.
- Theo dõi trạng thái từng target: pending, delivered, activated, verified hoặc failed.
- Dùng rolling update hoặc chiến lược canary nếu dịch vụ cần tính sẵn sàng cao.
- Kiểm tra chứng thư được trình ra từ từng endpoint hoặc từng vùng.
- Cảnh báo khi một node không nhận được artifact hoặc vẫn trình chứng thư cũ.
- Tránh deploy đồng thời vào toàn bộ hệ thống nếu có thể gây gián đoạn.

Với TLS termination tại load balancer, cần kiểm tra chứng thư ở load balancer thực sự phục vụ traffic. Việc cập nhật secret trong Kubernetes hoặc file trên backend không có nghĩa chứng thư đang được trình ra ở điểm kết thúc TLS đã thay đổi.

## 13. Reload, restart và xác minh sau triển khai

Nhiều dịch vụ không tự đọc lại file certificate khi file thay đổi. Một số hỗ trợ reload graceful; số khác cần restart hoặc thay pod. Automation phải biết cơ chế của từng consumer.

Sau khi kích hoạt, kiểm tra:

1. Tiến trình đã nạp đúng certificate fingerprint hoặc serial number mới.
2. Endpoint trình đúng SAN, issuer và thời hạn.
3. Chain được client xác minh thành công.
4. TLS handshake hoặc mTLS handshake hoạt động.
5. Health check, request nghiệp vụ và metric lỗi vẫn bình thường.
6. Tất cả replica và vùng đã cập nhật.

Có thể kiểm tra endpoint bằng TLS client hoặc công cụ giám sát chứng thư. Cần kiểm tra từ góc nhìn client thực tế, bởi một chứng thư đúng trong file nhưng cấu hình SNI hoặc load balancer sai vẫn có thể khiến client nhận chứng thư khác.

## 14. Máy trạng thái của renewal workflow

Quản lý trạng thái giúp tránh đánh dấu hoàn tất quá sớm và hỗ trợ retry có kiểm soát.

| Trạng thái | Ý nghĩa | Bước tiếp theo |
|---|---|---|
| Active | Chứng thư hiện tại đang được sử dụng | Theo dõi expiry |
| RenewalDue | Đã đến ngưỡng cần renewal | Kiểm tra policy và tạo order |
| OrderPending | CA đang chờ challenge hoặc xử lý | Tiếp tục xác minh challenge |
| Issued | CA đã phát hành chứng thư | Kiểm tra chain và nội dung |
| Validated | Chứng thư mới vượt qua kiểm tra | Chuẩn bị triển khai |
| Deploying | Đang phân phối và kích hoạt | Theo dõi từng target |
| Verifying | Đang kiểm tra endpoint và health | Đánh dấu active khi tất cả điều kiện đạt |
| ActiveNew | Chứng thư mới đang hoạt động | Lưu audit và theo dõi |
| RetryableFailure | Lỗi có thể thử lại | Retry theo backoff và giới hạn |
| Blocked | Lỗi policy hoặc cần can thiệp | Gửi cảnh báo cho owner |
| RevocationPending | Đang xử lý thu hồi chứng thư cũ | Theo dõi kết quả CA |

Workflow nên lưu trạng thái bền vững. Nếu controller restart giữa chừng, nó phải tiếp tục từ trạng thái đã ghi thay vì tạo order hoặc deploy lại một cách mù quáng.

~~~mermaid
flowchart TD
    A[Check certificate expiry] --> B{Renewal due?}
    B -- No --> A
    B -- Yes --> C[Create or resume order]
    C --> D[Complete CA challenge]
    D --> E[Receive certificate]
    E --> F{Validate certificate and key}
    F -- Fail --> G[Keep current certificate and alert]
    F -- Pass --> H[Deploy new certificate]
    H --> I[Reload and verify endpoints]
    I --> J{All targets healthy?}
    J -- No --> K[Retry or rollback]
    J -- Yes --> L[Mark active and audit]
~~~

## 15. Retry, backoff và xử lý lỗi

Renewal có thể thất bại do DNS propagation, HTTP challenge không truy cập được, CA rate limit, API outage, CSR sai, SAN không hợp lệ, hết quyền DNS, secret store lỗi hoặc dịch vụ không reload được.

Phân loại lỗi trước khi retry:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Timeout, DNS propagation, CA unavailable | Retry với exponential backoff và jitter |
| Cấu hình | SAN sai, challenge path sai, chain thiếu | Dừng retry tự động vô hạn; báo owner sửa cấu hình |
| Quyền truy cập | DNS API token hết hạn, IAM deny | Cảnh báo owner, kiểm tra scope và credential |
| Giới hạn CA | Rate limit, quota | Tôn trọng Retry-After hoặc policy của CA; tránh tạo order liên tục |
| Triển khai | File permission sai, secret store lỗi, node offline | Retry theo target, giữ phiên bản đang hoạt động |
| Xác minh | Endpoint trình certificate cũ hoặc handshake lỗi | Không hoàn tất workflow; rollback hoặc giữ chứng thư hiện tại |

Exponential backoff có thể tăng khoảng chờ theo từng lần thất bại nhưng cần giới hạn thời gian và số lần thử. Với lỗi cấu hình hoặc authorization, retry lặp lại thường không giúp ích và có thể làm tăng rate limit hoặc tạo tải không cần thiết.

Đặt cảnh báo theo thời gian còn lại trước expiry. Nếu renewal vẫn thất bại khi đã vào vùng nguy cơ, nâng mức ưu tiên và kích hoạt runbook khẩn cấp.

## 16. Idempotency và tránh renewal trùng lặp

Automation cần an toàn khi được chạy lại. Một scheduler có thể chạy mỗi giờ, controller có thể restart và nhiều replica có thể cùng quan sát một chứng thư.

Các biện pháp:

- Dùng certificate ID hoặc resource ID ổn định làm khóa điều phối.
- Lưu order ID hiện hành để tiếp tục một order đang xử lý.
- Dùng lock phân tán hoặc leader election để chỉ một controller xử lý một certificate tại một thời điểm.
- Kiểm tra trạng thái hiện tại trước mỗi mutation.
- Chỉ tạo CSR mới khi policy hoặc trạng thái yêu cầu.
- So sánh fingerprint/version để tránh deploy lại artifact đã active.
- Ghi nhận attempt ID và kết quả từng bước.

Idempotency không có nghĩa là bỏ qua kiểm tra. Mỗi lần retry vẫn cần xác minh trạng thái CA, certificate store và deployment target để phát hiện tiến trình đã thay đổi bên ngoài workflow.

## 17. Chứng thư client và mTLS

Với mutual TLS, cả client và server đều trình chứng thư để xác thực lẫn nhau. Vì vậy, renewal phải phối hợp cả hai phía:

- Client nhận certificate mới và private key tương ứng.
- Server trust store hoặc policy cần chấp nhận issuer/chain mới nếu CA hoặc intermediate thay đổi.
- Nếu có certificate pinning, cần cập nhật pin theo kế hoạch tương thích.
- Các replica client và server cần có thời gian chuyển tiếp để tránh một phía chỉ chấp nhận chứng thư cũ.
- Kiểm tra EKU clientAuth/serverAuth và danh tính SAN phù hợp.

Không thu hồi chứng thư client cũ ngay sau khi phát hành mới nếu hệ thống chưa xác minh toàn bộ consumer đã chuyển đổi, trừ khi xử lý sự cố đòi hỏi thu hồi khẩn cấp. Cần thiết kế overlap có thời hạn và có theo dõi.

## 18. Quản lý trust chain và thay đổi CA

Renewal có thể giữ nguyên issuer hoặc chuyển sang intermediate CA khác. Khi chain thay đổi, client cần tin cậy đúng root/intermediate và server phải gửi đủ intermediate certificate theo yêu cầu của giao thức.

Trước khi triển khai:

- Xác minh issuer nằm trong danh sách CA được phê duyệt.
- Kiểm tra chain xây dựng được đến trust anchor mong muốn.
- Đánh giá thay đổi intermediate hoặc root và khả năng tương thích với client cũ.
- Không thêm root certificate mới vào trust store chỉ vì chứng thư mới không được xác minh; phải xác minh nguồn và kế hoạch chuyển đổi CA.
- Theo dõi thời hạn của cả intermediate và root certificate, không chỉ leaf certificate.

Root CA thường có vòng đời dài và quy trình thay đổi đặc biệt. Tự động gia hạn leaf certificate không thay thế kế hoạch quản lý vòng đời CA.

## 19. Thu hồi và xử lý private key bị lộ

Renewal thông thường không tự động thu hồi chứng thư cũ. Sau khi chuyển đổi, có thể giữ chứng thư cũ đến khi hết hạn nếu policy và rủi ro cho phép. Nếu chứng thư hoặc private key bị lộ, cần đánh giá thu hồi ngay.

Quy trình ứng phó:

1. Xác định certificate serial, issuer, SAN, owner và các endpoint đang dùng.
2. Nếu private key có thể bị lộ, tạo key pair mới trong ranh giới bảo vệ.
3. Yêu cầu CA cấp chứng thư mới với public key mới.
4. Triển khai và xác minh chứng thư mới trên toàn bộ consumer.
5. Yêu cầu CA thu hồi chứng thư cũ theo cơ chế hỗ trợ.
6. Kiểm tra trạng thái thu hồi qua OCSP, CRL hoặc cơ chế tương đương mà client thực sự sử dụng.
7. Tìm nguồn rò rỉ và rà soát nơi private key cũ từng được lưu hoặc sao chép.
8. Bảo toàn audit log, ghi nhận thời điểm phát hiện, thay thế và thu hồi.

Thu hồi có thể không có hiệu lực tức thời ở mọi client do cache OCSP/CRL hoặc khác biệt trong chính sách kiểm tra. Cần hiểu cách client kiểm tra revocation và mức độ phụ thuộc của hệ thống vào cơ chế đó.

## 20. Bảo vệ credential của automation

ACME account key, DNS provider token, credential của secret manager và quyền triển khai chứng thư đều có thể mở rộng quyền của automation. Nếu bị lộ, kẻ tấn công có thể xin chứng thư cho tên miền được kiểm soát, thay đổi DNS hoặc thay private key đang dùng.

Áp dụng các nguyên tắc:

- Dùng danh tính riêng cho mỗi automation controller hoặc môi trường.
- Giới hạn DNS token vào zone và hành động cần thiết; không dùng tài khoản DNS quản trị toàn tổ chức.
- Lưu ACME account key và provider credential trong secret manager.
- Ưu tiên workload identity hoặc credential ngắn hạn thay cho secret dài hạn.
- Không đưa private key, DNS token hoặc ACME account key vào source code, image hay log.
- Phân biệt quyền tạo order, quyền đọc certificate store và quyền triển khai.
- Rà soát quyền của automation khi service ngừng hoạt động hoặc thay owner.
- Ghi audit cho việc đọc secret, tạo order, thay đổi DNS và triển khai certificate.

ACME account key dùng để xác thực account với ACME server; nó khác với private key của chứng thư máy chủ. Bảo vệ và xoay vòng hai loại khóa theo vai trò riêng.

## 21. Giám sát và cảnh báo

Monitoring nên theo dõi cả thời hạn chứng thư lẫn trạng thái workflow:

| Metric hoặc tín hiệu | Ý nghĩa | Cảnh báo khi |
|---|---|---|
| Certificate remaining lifetime | Thời gian còn lại đến Not After | Vào ngưỡng renewal nhưng chưa có order |
| Renewal success rate | Tỷ lệ renewal thành công | Giảm dưới mục tiêu vận hành |
| Order age | Thời gian order ở trạng thái pending | Vượt thời gian dự kiến |
| Challenge failure | Challenge không được CA xác minh | Lặp lại hoặc còn ít thời gian trước expiry |
| Deployment coverage | Số target đã nhận và kích hoạt certificate mới | Có node chưa cập nhật |
| Endpoint certificate fingerprint | Chứng thư thực sự đang được trình ra | Khác fingerprint dự kiến sau cutover |
| TLS handshake failure | Lỗi kết nối sau triển khai | Tăng đột biến hoặc vượt ngưỡng |
| Certificate inventory drift | Chứng thư thực tế khác inventory | Xuất hiện certificate không có owner hoặc chưa đăng ký |
| Private key rotation status | Key pair mới đã được tạo và sử dụng đúng chưa | Renewal policy yêu cầu rotation nhưng key cũ vẫn được dùng |

Mỗi cảnh báo cần chỉ rõ certificate ID, SAN, owner, environment, thời gian còn lại và bước xử lý. Tránh chỉ gửi thông báo chung chung như “certificate renewal failed”.

## 22. Audit trail cho automated renewal

Audit trail cần trả lời ai hoặc automation nào đã yêu cầu cấp chứng thư, CA nào đã phát hành, key pair/version nào được sử dụng, chứng thư được triển khai đến đâu và ai phê duyệt ngoại lệ.

Các trường có thể lưu:

- Certificate ID, serial number, issuer, SAN fingerprint và certificate fingerprint.
- Owner, service, environment và danh sách deployment target.
- ACME account hoặc enrollment identity ID, không ghi account secret.
- Order ID, challenge type và kết quả xác minh.
- CSR fingerprint hoặc request ID; không ghi private key.
- Thời điểm tạo, phát hành, validate, deploy, reload, verify và revoke.
- Key version hoặc key provider reference.
- Người hoặc workload thực hiện, approval ID và change ticket.
- Kết quả từng bước, error code và retry count.

Không ghi nội dung private key hoặc credential của DNS provider vào audit log. Audit store cần có kiểm soát truy cập, bảo vệ toàn vẹn và retention phù hợp.

## 23. Ví dụ cấu hình renewal tổng quát

Một cấu hình minh họa có thể mô tả chính sách và target:

~~~yaml
certificate:
  id: billing-api-prod
  identifiers:
    - api.billing.example
  issuer: approved-acme-ca
  environment: production
  owner: billing-platform

renewal:
  enabled: true
  renew_before: 30d
  rotate_private_key: true
  challenge: dns-01
  max_attempts: 6
  backoff: exponential
  jitter: true

key:
  provider: hsm
  exportable: false
  purpose: tls-server-authentication

deployment:
  targets:
    - billing-ingress-a
    - billing-ingress-b
  activation: rolling
  verify_after_reload: true
~~~

Đây là cấu hình khái niệm, không phải schema dùng trực tiếp cho một ACME client hoặc nền tảng cụ thể. Tên trường, cú pháp thời hạn và khả năng tạo CSR trong HSM phụ thuộc công cụ triển khai.

## 24. Kiểm thử và diễn tập

Không nên chỉ kiểm tra automation khi chứng thư production sắp hết hạn. Cần kiểm thử định kỳ bằng CA staging hoặc PKI test để tránh tiêu thụ quota production và giảm nguy cơ làm gián đoạn dịch vụ.

Các tình huống nên diễn tập:

- Renewal thành công với key pair mới.
- Renewal giữ nguyên key pair khi policy cho phép.
- DNS challenge chậm hoặc TXT record sai.
- HTTP challenge không đến được ACME client.
- CA timeout, rate limit hoặc order pending kéo dài.
- Chứng thư trả về sai SAN, thiếu intermediate hoặc sai EKU.
- Secret store không khả dụng.
- Một node offline trong lúc triển khai.
- Reload thất bại hoặc endpoint tiếp tục trình chứng thư cũ.
- Một phía mTLS cập nhật trước phía còn lại.
- Controller restart giữa các trạng thái.
- Private key bị nghi ngờ lộ và cần emergency reissue/revocation.

Sau mỗi lần diễn tập, xác nhận alert đến đúng owner, workflow có thể tiếp tục hoặc rollback và audit trail lưu đủ bằng chứng.

## 25. Những sai lầm thường gặp

- Chỉ tự động xin chứng thư mà không tự động triển khai và xác minh endpoint.
- Đợi đến gần Not After mới bắt đầu renewal.
- Không kiểm tra SAN, EKU, issuer, chain hoặc public key tương ứng.
- Ghi đè chứng thư đang hoạt động trước khi chứng thư mới được xác minh.
- Tạo key pair mới nhưng triển khai nhầm private key cũ.
- Tái sử dụng private key vô thời hạn mà không có policy rotation.
- Cấp DNS API token có quyền thay đổi toàn bộ tài khoản.
- Để ACME account key và certificate private key trong cùng nơi mà không có phân quyền.
- Tạo nhiều order trùng lặp khi controller retry hoặc chạy song song.
- Chỉ kiểm tra một node trong khi dịch vụ có nhiều replica hoặc vùng.
- Bỏ qua reload, health check và xác minh SNI từ phía client.
- Thu hồi chứng thư cũ trước khi consumer chuyển đổi, hoặc không thu hồi khi private key đã bị lộ.
- Không theo dõi hạn dùng của intermediate CA và root CA.

## 26. Checklist vận hành

- [ ] Có inventory chứng thư với SAN, issuer, expiry, owner và target sử dụng.
- [ ] Có ngưỡng renewal đủ sớm và có jitter để tránh dồn tải.
- [ ] Renewal workflow có trạng thái bền vững và idempotent.
- [ ] ACME hoặc enrollment protocol được cấu hình với challenge phù hợp.
- [ ] Credential DNS và ACME account được bảo vệ và giới hạn quyền.
- [ ] CSR chứa đúng danh tính và SAN đã được phê duyệt.
- [ ] Private key được giữ trong file bảo vệ, KMS hoặc HSM theo policy.
- [ ] Policy xác định rõ renewal có xoay vòng private key hay không.
- [ ] Chứng thư mới được kiểm tra chain, SAN, validity, EKU, Key Usage và key pair.
- [ ] Certificate chain và private key được phân phối an toàn, nhất quán.
- [ ] Có reload hoặc rolling deployment cho tất cả consumer.
- [ ] Xác minh chứng thư thực tế đang được trình ra từ từng endpoint.
- [ ] Có retry/backoff cho lỗi tạm thời và dừng có kiểm soát với lỗi cấu hình.
- [ ] Có cảnh báo khi renewal thất bại hoặc còn ít thời gian trước expiry.
- [ ] Có quy trình emergency reissue và revocation khi private key bị lộ.
- [ ] Có audit trail cho order, challenge, issuance, validation, deployment và revocation.
- [ ] Đã diễn tập renewal, rollback và lỗi CA/DNS/endpoint trên môi trường test.

## Kết luận

Automated certificate renewal là quy trình quản lý liên tục từ phát hiện chứng thư sắp hết hạn, xác minh quyền cấp, tạo CSR, nhận chứng thư, kiểm tra nội dung đến triển khai và xác minh endpoint. Tự động hóa chỉ đáng tin cậy khi private key được bảo vệ, challenge được giới hạn đúng quyền, chứng thư mới được kiểm tra trước khi kích hoạt và mọi node đều được xác nhận đã chuyển đổi. Cần phân biệt renewal với key rotation, xử lý lỗi bằng retry có kiểm soát, theo dõi hạn dùng và duy trì audit trail. Với KMS/HSM, private key có thể được tạo và giữ trong ranh giới bảo vệ trong khi ACME hoặc enrollment agent chỉ gửi CSR và nhận chứng thư. Quy trình hoàn chỉnh giúp giảm nguy cơ hết hạn, hỗ trợ thay khóa theo policy và duy trì khả năng xác thực an toàn cho các dịch vụ.
