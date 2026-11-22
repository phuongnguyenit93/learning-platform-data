# Thu hồi certificate

Thu hồi certificate là thao tác đánh dấu một chứng thư không còn được tin cậy trước khi hết hạn. Trong gRPC chạy qua TLS, việc này đặc biệt quan trọng với mutual TLS (mTLS): client xác minh certificate của server, còn server xác minh certificate của client. Khi private key bị lộ, thiết bị bị mất, nhân sự rời hệ thống hoặc certificate được cấp sai, chỉ chờ certificate hết hạn là không đủ.

Trong Spring gRPC, thu hồi certificate là một quy trình PKI và vận hành kết hợp với TLS trust manager, channel lifecycle và triển khai cấu hình. Cần xác định peer nào phải kiểm tra trạng thái thu hồi, CRL/OCSP được phân phối ra sao, ứng dụng xử lý khi responder không truy cập được và các kết nối HTTP/2 đã thiết lập được đóng như thế nào. Certificate revocation bảo vệ các lần xác thực TLS mới; nó không tự động kết thúc mọi RPC trên một kết nối đã bắt tay thành công.

## 1. Thu hồi certificate giải quyết vấn đề gì?

Certificate X.509 liên kết public key với danh tính và được CA ký. Trust chain xác định CA nào được tin cậy; validity period xác định khoảng thời gian certificate còn hạn. Revocation bổ sung trạng thái thu hồi trong thời hạn đó.

Các nguyên nhân thường gặp:

- Private key bị lộ, sao chép trái phép hoặc lưu trữ không an toàn.
- Máy, pod, workload hoặc thiết bị sở hữu certificate bị xâm nhập.
- Certificate được cấp nhầm SAN, EKU, subject hoặc phạm vi quyền.
- Workload bị xóa, thay thế hoặc chuyển quyền sở hữu.
- CA phát hiện lỗi trong quá trình cấp phát hoặc ký certificate.
- Intermediate CA hoặc CA key bị xâm phạm.

Thu hồi certificate khác với hết hạn. Hết hạn là kết thúc thời gian được ghi trong certificate; thu hồi là quyết định chủ động của CA hoặc tổ chức phát hành trước thời điểm đó. Thay certificate cũng không tự động thu hồi certificate cũ: hai hành động cần được phối hợp theo quy trình rotation.

## 2. Ai kiểm tra trạng thái thu hồi trong gRPC TLS?

Trong kết nối TLS một chiều, client xác minh certificate server. Trong mTLS, cả hai phía xác minh certificate của peer:

| Kết nối | Bên xác minh | Certificate cần kiểm tra |
| --- | --- | --- |
| TLS | gRPC client | Certificate của gRPC server |
| mTLS | gRPC client | Certificate của gRPC server |
| mTLS | gRPC server | Certificate client |
| Gateway/proxy terminate TLS | Gateway/proxy | Certificate của peer TLS kết nối trực tiếp với gateway |

Nếu TLS kết thúc tại ingress hoặc service mesh sidecar, ứng dụng Spring gRPC phía sau có thể chỉ nhận kết nối nội bộ đã được proxy xác thực. Khi đó, nơi thực hiện revocation check là proxy/sidecar; cần xác minh cả hop proxy-to-service và identity được truyền vào ứng dụng. Không giả định certificate của client bên ngoài luôn được kiểm tra tại JVM của service.

Với mTLS trực tiếp giữa hai gRPC process, cả client và server phải có trust configuration cùng chính sách revocation phù hợp. Truststore chỉ chứa CA đáng tin cậy chưa có nghĩa là certificate leaf đã được kiểm tra CRL hoặc OCSP.

## 3. CRL và OCSP

Hai cơ chế phổ biến để truy vấn trạng thái thu hồi là Certificate Revocation List (CRL) và Online Certificate Status Protocol (OCSP).

| Cơ chế | Cách hoạt động | Ưu điểm | Điểm cần vận hành |
| --- | --- | --- | --- |
| CRL | CA phát hành danh sách certificate serial đã bị thu hồi; verifier tải và kiểm tra danh sách | Có thể cache và dùng trong môi trường hạn chế kết nối | Phải cập nhật CRL đúng hạn, kiểm tra nextUpdate và phân phối tới mọi verifier |
| OCSP | Verifier hỏi responder về trạng thái một certificate | Trạng thái có thể mới hơn CRL lớn | Cần responder khả dụng, latency thấp, cache hợp lý và xác minh chữ ký response |
| OCSP stapling | TLS server gửi OCSP response do CA/responder ký cùng handshake | Giảm truy vấn trực tiếp từ client tới responder | Phải xác minh TLS provider/client có hỗ trợ và xử lý response đúng policy |

CRL thường chứa serial number, thời điểm thu hồi và lý do thu hồi. Verifier phải xây dựng đúng certificate path và dùng CRL áp dụng cho issuer tương ứng. CRL hết hạn hoặc không cập nhật không thể được xem như dữ liệu thu hồi đáng tin cậy.

OCSP thường trả về trạng thái GOOD, REVOKED hoặc UNKNOWN. GOOD chỉ có nghĩa responder không ghi nhận certificate bị thu hồi tại thời điểm response; nó không thay thế kiểm tra chữ ký certificate, hostname/SAN, EKU, validity period hay trust chain. UNKNOWN không đồng nghĩa GOOD.

Không có cơ chế revocation nào tự bật chỉ vì ứng dụng dùng TLS. Cần cấu hình trust manager/provider để thực hiện kiểm tra và xác minh rằng provider TLS thực tế có hỗ trợ cơ chế đã chọn.

## 4. Chính sách khi CRL/OCSP không truy cập được

Khi verifier không thể lấy thông tin thu hồi, hệ thống phải có quyết định rõ:

- Fail closed: từ chối handshake nếu không thể xác minh trạng thái thu hồi theo policy.
- Soft fail/fail open: tiếp tục nếu responder hoặc CRL endpoint tạm thời không khả dụng.
- Dùng cache còn hiệu lực: chấp nhận response/CRL đã xác minh nếu vẫn nằm trong thời hạn freshness được policy cho phép.

Fail closed giảm nguy cơ chấp nhận certificate đã bị thu hồi nhưng có thể làm gián đoạn kết nối khi CA/responder gặp sự cố. Fail open tăng khả dụng nhưng mở cửa sổ rủi ro trong thời gian trạng thái không thể xác minh. Đây là quyết định security architecture, không nên để mặc định của thư viện quyết định thay tổ chức.

Định nghĩa cụ thể:

1. CRL/OCSP cache được xem là còn mới trong bao lâu.
2. Cách xử lý response UNKNOWN, chữ ký sai, issuer không khớp hoặc CRL hết hạn.
3. Timeout và retry cho responder, tránh làm handshake chờ quá lâu.
4. Alert khi revocation source lỗi hoặc dữ liệu sắp hết hạn.
5. Quy trình khẩn cấp khi phải từ chối ngay một serial dù responder/cache chưa cập nhật.

Không coi lỗi mạng tới OCSP responder là bằng chứng certificate hợp lệ. Cũng không retry vô hạn trong TLS handshake vì có thể gây cạn thread và làm gián đoạn toàn bộ kết nối mới.

## 5. Bật revocation checking trong Java TLS

Java JSSE có hỗ trợ PKIX revocation checking. Với SunJSSE/PKIX trust manager, các system property thường dùng gồm:

```text
-Dcom.sun.net.ssl.checkRevocation=true
-Dcom.sun.security.enableCRLDP=true
-Docsp.enable=true
```

Các property này yêu cầu JSSE kiểm tra trạng thái thu hồi theo CRL Distribution Points và/hoặc OCSP tùy certificate path và cấu hình provider. Chúng phải được đặt trước khi TLS context/trust manager được khởi tạo. Hãy xác minh hành vi trên đúng JDK, security provider và cấu hình PKIX mà ứng dụng chạy.

Ví dụ khởi động JVM:

```bash
java \
  -Dcom.sun.net.ssl.checkRevocation=true \
  -Dcom.sun.security.enableCRLDP=true \
  -Docsp.enable=true \
  -jar orders-grpc.jar
```

Đây là ví dụ cho JSSE; không được suy ra rằng mọi TLS provider đều tuân theo các property này. grpc-java có thể chạy qua Netty với OpenSSL/native provider hoặc một TrustManagerFactory được cấu hình riêng. Khi dùng provider khác, cần cấu hình revocation tại provider/trust manager đó và kiểm tra bằng certificate test đã bị thu hồi.

Với ứng dụng Spring, đặt JVM/security configuration ở môi trường triển khai và khởi tạo SSLContext sau khi cấu hình đã có hiệu lực. Không thêm property vào application config rồi mặc định cho rằng starter hoặc native TLS engine sẽ tự áp dụng.

## 6. Trust manager và gRPC channel/server

Revocation checking phải nằm trong certificate path validation mà TLS trust manager thực hiện. Về mặt triển khai:

- gRPC client dùng trust manager để xác minh certificate server.
- gRPC server dùng trust manager để xác minh certificate client khi bật mTLS.
- Key manager cung cấp certificate/private key cục bộ; trust manager quyết định peer certificate có được tin cậy hay không.
- CRL/OCSP source và cache phải truy cập được từ đúng runtime/container.

Trong grpc-java Netty, TLS context thường được tạo qua SslContextBuilder và có thể nhận TrustManagerFactory. TrustManagerFactory phải được cấu hình với cơ chế PKIX/revocation phù hợp; chỉ truyền truststore CA thông thường chưa đủ chứng minh revocation check đang bật.

Trong Spring gRPC, cách cung cấp SSLContext, TrustManagerFactory hoặc Netty SslContext phụ thuộc starter và phiên bản đang dùng. Dùng extension point thực tế của dự án để cấu hình cả client channel lẫn server listener. Không tự đặt tên property giả định và không chỉ cấu hình client trong khi server mTLS vẫn chấp nhận certificate client bị thu hồi.

Nếu dùng custom X509TrustManager, implementation phải xác minh đầy đủ chain, validity, key usage/EKU, hostname ở phía client và revocation. Một wrapper chỉ kiểm tra serial number trong một list tĩnh nhưng bỏ qua PKIX path validation có thể tạo lỗ hổng nghiêm trọng.

## 7. Thu hồi certificate client trong mTLS

Khi client certificate bị thu hồi, gRPC server là bên cần từ chối certificate đó trong TLS handshake mới. Quy trình tổng quát:

1. CA đánh dấu serial certificate client là REVOKED.
2. CRL/OCSP được cập nhật và công bố.
3. Trust manager của server tải/nhận dữ liệu mới theo freshness policy.
4. Client mở kết nối mTLS mới.
5. Server xác minh certificate chain và trạng thái thu hồi.
6. Handshake bị từ chối trước khi RPC được dispatch.

Nếu TLS terminate tại proxy, proxy là nơi cần kiểm tra client certificate. Service phía sau chỉ có thể dựa vào identity proxy chuyển tiếp nếu proxy-to-service channel được xác thực và header identity không thể bị caller giả mạo.

Certificate client bị thu hồi thường dẫn tới lỗi TLS handshake, không phải một gRPC status nghiệp vụ như PERMISSION_DENIED. Vì handshake có thể thất bại trước khi HTTP/2/gRPC call hình thành, client thường thấy lỗi transport/SSL hoặc UNAVAILABLE tùy channel/provider; test không nên phụ thuộc vào một status code gRPC cố định cho mọi TLS provider.

## 8. Thu hồi certificate server

Khi certificate server bị thu hồi, mỗi gRPC client phải kiểm tra trạng thái certificate server trong quá trình TLS handshake. Cập nhật CRL/OCSP trên server không đủ nếu client trust manager vẫn dùng dữ liệu cũ hoặc không bật revocation checking.

Quy trình:

1. CA thu hồi server certificate bị xâm phạm.
2. Công bố CRL/OCSP mới và xác minh responder trả REVOKED.
3. Cập nhật revocation data/trust configuration cho toàn bộ client fleet.
4. Tạo kết nối TLS mới từ client tới server.
5. Xác minh client từ chối server certificate bị thu hồi.
6. Cấp và triển khai certificate server mới theo quy trình rotation.

Trong mTLS, việc thu hồi server certificate không thay thế việc kiểm tra client certificate ở phía server. Mỗi chiều xác thực có trust manager và dữ liệu thu hồi riêng.

## 9. Certificate đã thu hồi và kết nối HTTP/2 đang mở

Revocation check thường được thực hiện khi xác minh certificate trong TLS handshake. gRPC dùng HTTP/2 connection có thể mang nhiều RPC và tồn tại lâu. Khi CA công bố certificate bị thu hồi, kết nối TLS đã bắt tay trước đó không tự động chạy lại certificate validation cho mỗi RPC.

Do đó, xử lý incident cần phối hợp:

- Ngừng cấp call mới trên channel/connection bị ảnh hưởng.
- Đóng hoặc drain channel hiện tại để buộc TLS handshake mới.
- Xóa/refresh connection pool và session cache theo khả năng của provider.
- Khởi động lại hoặc reload client/server TLS context nếu revocation cache/trust manager chỉ được đọc lúc khởi tạo.
- Xác minh mọi replica và proxy đã nhận CRL/OCSP mới trước khi coi incident đã được xử lý.

TLS session resumption cũng cần được xem xét: một phiên được resume có thể không thực hiện đầy đủ certificate validation như full handshake tùy protocol/provider. Với sự cố key compromise, áp dụng biện pháp invalidate session/cache hoặc restart/rotate connection theo khả năng runtime, đồng thời kiểm thử trên TLS provider thực tế.

## 10. Rotation bình thường và thu hồi khẩn cấp

Rotation là thay certificate trước hoặc khi gần hết hạn. Revocation là làm certificate không còn được chấp nhận. Quy trình rotation có thể có giai đoạn overlap để tránh gián đoạn:

| Giai đoạn | Hành động |
| --- | --- |
| Prepare | Cấp certificate mới, xác minh SAN/EKU/chain và phân phối CA cần thiết |
| Deploy | Triển khai certificate mới lên server/client |
| Refresh | Tạo TLS context/channel mới hoặc drain kết nối cũ |
| Verify | Kiểm tra handshake và RPC bằng certificate mới |
| Retire | Ngừng sử dụng certificate cũ |
| Revoke | Thu hồi certificate cũ khi không còn cần hoặc theo policy |

Trong sự cố compromise, không chờ hoàn tất overlap thông thường. Thu hồi ngay certificate cũ, cập nhật revocation source, áp dụng denylist khẩn cấp nếu cần và buộc các kết nối/session bị ảnh hưởng được tái xác thực. Denylist tạm thời ở gateway hoặc trust layer có thể giúp phản ứng nhanh, nhưng phải có owner, thời hạn và quy trình gỡ bỏ để tránh tồn tại vĩnh viễn ngoài PKI.

Nếu private key của CA bị xâm phạm, thu hồi một leaf certificate không đủ. Cần đánh giá toàn bộ certificate do CA đó ký, loại CA/intermediate bị xâm phạm khỏi trust path phù hợp và phân phối truststore mới. Root CA compromise thường yêu cầu thay đổi trust anchor trên toàn fleet.

## 11. Runbook xử lý certificate bị lộ

Khi nhận cảnh báo private key bị lộ:

1. **Xác định phạm vi:** subject, issuer, serial, fingerprint, SAN, EKU, owner, workload và thời hạn certificate.
2. **Khoanh vùng:** xác định mọi server/client, gateway, sidecar và connection pool đang dùng certificate.
3. **Thu hồi:** yêu cầu CA revoke serial và công bố CRL/OCSP mới.
4. **Phân phối:** cập nhật revocation cache/trust manager và xác minh mọi replica nhận dữ liệu mới.
5. **Chặn khẩn cấp:** nếu nguồn revocation chưa kịp cập nhật, áp dụng denylist serial/fingerprint ở trust enforcement point được kiểm soát.
6. **Đóng kết nối cũ:** drain channel, invalidate session/cache hoặc restart thành phần cần thiết để buộc handshake mới.
7. **Thay certificate:** cấp certificate mới và triển khai private key mới qua secret manager.
8. **Xác minh:** certificate cũ bị từ chối; certificate mới kết nối được; RPC hợp lệ hoạt động.
9. **Theo dõi:** kiểm tra handshake failures, lỗi OCSP/CRL, phiên TLS còn tồn tại và các replica chưa cập nhật.
10. **Lưu audit:** ghi serial/fingerprint, thời điểm, người phê duyệt, CA action và kết quả rollout; không ghi private key.

Runbook cần có owner cho CA, platform, service team và security operations. Việc revoke trên CA nhưng không refresh channel/trust manager có thể để kết nối hiện tại tiếp tục hoạt động.

## 12. Kiểm thử revocation

Chuẩn bị test CA và certificate riêng cho môi trường test. Không dùng private key hoặc certificate production trong test. Tạo các trường hợp:

| Certificate/test case | Kết quả mong đợi |
| --- | --- |
| Certificate hợp lệ, chưa thu hồi | TLS handshake thành công |
| Leaf certificate có serial trong CRL | Handshake bị từ chối |
| OCSP trả REVOKED | Handshake bị từ chối |
| OCSP trả UNKNOWN | Xử lý theo policy đã định nghĩa, không mặc định GOOD |
| CRL hết hạn hoặc không mới | Fail theo freshness/fail-open policy |
| OCSP responder timeout | Fail theo timeout và fail-open/closed policy |
| Chữ ký OCSP/CRL sai | Không chấp nhận dữ liệu trạng thái không hợp lệ |
| Certificate hết hạn | Handshake bị từ chối |
| SAN/hostname không khớp | Client từ chối server |
| EKU/key usage không phù hợp | Certificate không được chấp nhận cho vai trò đó |
| Intermediate CA bị thu hồi | Path validation từ chối chain |
| Certificate client bị thu hồi trong mTLS | Server từ chối handshake mới |
| Certificate server bị thu hồi | Client từ chối handshake mới |
| Kết nối HTTP/2 đã mở trước revocation | Chỉ bị ngắt khi channel/session được drain hoặc đóng theo quy trình |

Với handshake failure, xác minh client không thể gọi RPC qua kết nối đó và server/client log có thông tin chẩn đoán đủ dùng nhưng không lộ secret. Kiểm thử CRL/OCSP cache freshness và khả năng refresh sau khi dữ liệu được cập nhật.

## 13. Bài tập vận dụng

Một hệ thống Spring gRPC dùng mTLS giữa OrderClient và OrderService. Certificate client được CA nội bộ cấp; certificate server có SAN orders.internal. Một private key client bị lộ trong sự cố CI, trong khi nhiều pod đang giữ HTTP/2 channel dài hạn.

**Yêu cầu:**

1. Xác định peer nào kiểm tra client certificate và peer nào kiểm tra server certificate.
2. Lập kế hoạch revoke serial client certificate và công bố CRL/OCSP.
3. Xác định TLS provider/trust manager thực tế của client và server; xác minh revocation checking đang bật ở cả hai chiều cần thiết.
4. Chọn fail-open/closed policy cho CRL/OCSP responder failure và freshness.
5. Lập kế hoạch drain channel/session cũ để buộc handshake mới.
6. Cấp certificate client mới, triển khai secret và xác minh mTLS.
7. Viết test chứng minh certificate cũ bị từ chối, certificate mới được chấp nhận.
8. Kiểm tra log/metrics/audit để xác định replica chưa nhận revocation update.

**Câu hỏi tự kiểm tra:**

- CRL khác OCSP ở cách phân phối trạng thái thu hồi thế nào?
- OCSP UNKNOWN có thể được xem như GOOD không?
- Trong mTLS, bên nào kiểm tra certificate client và server?
- Vì sao bật TLS không đồng nghĩa đã bật revocation checking?
- Vì sao phải xác minh provider TLS thực tế thay vì chỉ đặt JSSE property?
- Revocation có tự kết thúc một HTTP/2 connection đã mở không?
- TLS session resumption ảnh hưởng quy trình incident ra sao?
- Khi nào cần loại intermediate/root CA khỏi truststore?
- Vì sao handshake failure không nhất thiết xuất hiện thành một gRPC status nghiệp vụ?
- Cần xác minh những gì sau khi revoke và rotate certificate?

**Ghi nhớ:** Thu hồi certificate cần đồng thời cập nhật trạng thái PKI và buộc các kết nối cần thiết xác thực lại. Kiểm tra CRL/OCSP tại đúng trust manager ở cả client và server mTLS; định nghĩa rõ freshness và fail-open/closed; refresh channel/session sau revocation; rồi xác minh certificate cũ bị từ chối và certificate mới hoạt động. Trong Spring gRPC, cấu hình theo TLS provider/starter thực tế và kiểm thử qua đúng transport production.
