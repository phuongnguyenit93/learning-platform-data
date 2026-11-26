1. TLS bảo vệ một kết nối HTTPS bằng các thuộc tính bảo mật cốt lõi nào?
A. Bí mật nội dung, toàn vẹn thông điệp và xác thực đầu xa.
B. Mã hóa nội dung nhưng không bảo vệ thông điệp khỏi sửa đổi.
C. Xác minh server nhưng không thiết lập khóa mã hóa lưu lượng.
D. Bảo đảm độ tin cậy TCP và sửa lỗi khi gói mạng bị mất.
Đáp án đúng: A

2. Sau handshake TLS, dữ liệu ứng dụng thường được mã hóa theo cơ chế khóa nào?
A. Khóa công khai server được dùng trực tiếp cho mọi TLS record.
B. Khóa riêng root CA được client dùng cho mọi bản tin gửi đi.
C. Khóa riêng DNS resolver được cấp theo từng tên miền truy cập.
D. Khóa đối xứng dẫn xuất riêng cho lưu lượng của phiên TLS.
Đáp án đúng: D

3. Server ký một thông điệp bằng khóa riêng; phía client kiểm tra chữ ký bằng gì?
A. Khóa công khai ứng với khóa riêng đã dùng ký.
B. Khóa riêng của CA tạo ra chứng thư cho máy chủ TLS.
C. Khóa đối xứng tạo cho dữ liệu ứng dụng sau bắt tay.
D. Khóa bí mật do browser gắn với hostname trong DNS.
Đáp án đúng: A

4. Bản thân hàm băm SHA-256 mang lại chức năng mật mã nào?
A. Bản mã khôi phục được nhờ dùng khóa riêng của server.
B. Chữ ký điện tử xác định người gửi mà không cần khóa.
C. Khóa phiên ngẫu nhiên gửi công khai mà vẫn được bảo mật.
D. Digest để nhận biết thay đổi, không mã hóa thông điệp.
Đáp án đúng: D

5. Tại sao TLS dùng AEAD như AES-GCM để mã hóa bản ghi?
A. Tạo chữ ký CA cho chứng thư trước khi mã hóa bản ghi.
B. Giấu nội dung và kiểm tra sửa đổi bằng authentication tag.
C. Đảm bảo mọi IP packet được router gửi đúng thứ tự.
D. Cấp khóa riêng X.509 mới trước mỗi application record.
Đáp án đúng: B

6. ECDHE dùng khóa trao đổi tạm thời trong TLS hỗ trợ đặc tính nào?
A. Khôi phục khóa phiên cũ từ certificate do CA đã phát hành.
B. Forward secrecy dù khóa server dài hạn bị lộ về sau.
C. Tái sử dụng khóa phiên lâu dài mà không cần bắt tay lại.
D. Thay việc kiểm tra hostname bằng chứng thực DNS server.
Đáp án đúng: B

7. Dùng trùng nonce với cùng khóa khi mã hóa AES-GCM có thể gây tác hại gì?
A. Giảm khả năng cache chứng thư và tăng truy vấn OCSP.
B. Khiến server phải cấp lại chứng thư trước hạn NotAfter.
C. Lộ thông tin và làm yếu nghiêm trọng bảo đảm toàn vẹn.
D. Làm tăng số lần gửi lại TCP dù đường truyền không nghẽn.
Đáp án đúng: C

8. Trong chứng thư X.509 công khai của server, loại thông tin nào cần có?
A. Khóa công khai, định danh và chữ ký của bên phát hành.
B. Khóa riêng cùng mật khẩu truy cập máy chủ đang chạy.
C. Traffic secret để client giải mã dữ liệu của các phiên khác.
D. Bộ khóa mã hóa đối xứng chung cho toàn bộ trình duyệt.
Đáp án đúng: A

9. Để khớp hostname khi truy cập HTTPS, client hiện đại kiểm tra phần nào của certificate?
A. Tên nhà cấp phát được ghi ở trường Issuer Common Name.
B. Địa chỉ IP client trùng với serial number của certificate.
C. Tên DNS khớp trong trường Subject Alternative Name.
D. Organization ghi đúng tên doanh nghiệp quản lý website.
Đáp án đúng: C

10. Nếu certificate có DNS SAN và CN khác với hostname đang kết nối, điều gì quyết định kiểm tra tên?
A. Hostname được so với CN ngay cả khi SAN đã chứa DNS name.
B. Hostname được so với Organization của bên sở hữu khóa.
C. Hostname được so với SAN, không ưu tiên CN thay cho SAN.
D. Hostname được so với Issuer của CA ký chứng thư server.
Đáp án đúng: C

11. Chuỗi chứng thư thông thường nối leaf, intermediate và root ra sao?
A. Leaf do intermediate ký; chuỗi dẫn tới root được tin cậy.
B. Root do leaf ký; intermediate lưu khóa riêng cho client.
C. Intermediate ký root; leaf chỉ chứa khóa đối xứng của TLS.
D. Leaf do DNS resolver ký; root được lấy từ gói TCP SYN.
Đáp án đúng: A

12. Server quên gửi intermediate cần thiết khi gửi certificate chain. Lỗi nào có thể xuất hiện?
A. Client không phân giải được DNS A của hostname server.
B. Client không thể bắt tay TCP vì SYN-ACK thiếu timestamp.
C. Client không xây được chuỗi chữ ký tới trust anchor.
D. Client không tính được subnet mask cho địa chỉ IP đích.
Đáp án đúng: C

13. Trust store chứa root CA có vai trò gì khi xác thực HTTPS?
A. Cung cấp trust anchor để client kiểm tra chain đã nhận.
B. Cung cấp private key server để client giải mã dữ liệu TLS.
C. Cung cấp địa chỉ IP router mà server phải gửi gói tin.
D. Cung cấp session ticket chung cho các tên miền cùng CA.
Đáp án đúng: A

14. Đồng hồ client chậm khiến ngày hiện tại sớm hơn NotBefore của certificate. Điều gì xảy ra?
A. Client tự tăng NotAfter và tiếp tục xác thực certificate.
B. Server tự phát hành certificate mới để khớp giờ client.
C. DNS resolver đổi bản ghi A để khắc phục sai lệch thời gian.
D. Client có thể từ chối vì chứng thư chưa bắt đầu hiệu lực.
Đáp án đúng: D

15. Extended Key Usage với giá trị serverAuth trong certificate dùng để thể hiện gì?
A. Quyền của chứng thư được phép ký mọi chứng thư root.
B. Dấu hiệu certificate chứa private key của bên phát hành.
C. Mục đích sử dụng chứng thư cho xác thực máy chủ.
D. Quyền lưu lượng HTTPS được bỏ kiểm tra toàn vẹn bản ghi.
Đáp án đúng: C

16. Với SAN là *.example.com, hostname nào khớp wildcard thông thường?
A. example.com, là tên ở gốc không có nhãn phụ nào.
B. a.b.example.com, chứa hai nhãn bên dưới example.com.
C. api.example.com, tức một nhãn nằm dưới example.com.
D. api.example.net, dùng vùng example.net hoàn toàn khác.
Đáp án đúng: C

17. OCSP và CRL hỗ trợ kiểm tra khía cạnh nào trong xác thực certificate?
A. Tình trạng đường TCP có đang bị packet loss hoặc reset.
B. Tình trạng bộ mã TLS có được server chọn sau key share.
C. Tình trạng DNS resolver có giữ bản ghi A trong cache.
D. Tình trạng chứng thư có bị thu hồi trước ngày hết hạn.
Đáp án đúng: D

18. Client kết nối web.example.com, nhưng cert SAN chỉ có api.example.com. Cách xử lý đúng là gì?
A. Tin cậy certificate vì chữ ký root CA vẫn còn hiệu lực.
B. Chấp nhận nếu web và api cùng trả về một địa chỉ IPv4.
C. Thay bản ghi DNS CNAME rồi bỏ bước xác thực hostname.
D. Từ chối tên không khớp và cấp cert đúng hostname.
Đáp án đúng: D

19. Một server dùng nhiều chứng thư trên một IP và port 443. SNI giúp server làm gì?
A. Cấp địa chỉ IP riêng cho mỗi tên miền được client yêu cầu.
B. Chọn chứng thư theo tên host client gửi trong ClientHello.
C. Chọn phiên bản HTTP bằng cách đọc header Host của request.
D. Tự chuyển mỗi luồng HTTPS qua một cổng TCP khác nhau.
Đáp án đúng: B

20. ALPN được dùng trong kết nối TLS để thống nhất thông tin nào?
A. Địa chỉ IP do DNS A trả về trước khi bắt đầu TCP SYN.
B. Thuật toán cấp phát MAC của switch đang nối với client.
C. Số lượng router nằm giữa client và hostname của server.
D. Giao thức ứng dụng như h2 hoặc http/1.1 của phiên kết nối.
Đáp án đúng: D

21. ClientHello của TLS 1.3 thường mang các thông tin thương lượng nào?
A. Phiên bản, cipher suites và key share client đề xuất.
B. Khóa riêng của server cùng dữ liệu HTTP cần mã hóa ngay.
C. Chứng thư root của máy khách và tất cả TCP sequence number.
D. Lệnh xác minh certificate chain đã hoàn thành tại server.
Đáp án đúng: A

22. ServerHello trong một handshake TLS 1.3 thường có vai trò nào?
A. Gửi dữ liệu HTTP đã mã hóa trước khi client chọn suite.
B. Chọn bộ thông số và cung cấp key share phía máy chủ.
C. Chuyển kết nối TCP đã tạo thành kênh UDP mới cho client.
D. Công bố khóa riêng root CA để client kiểm tra chứng thư.
Đáp án đúng: B

23. CertificateVerify của server trong TLS 1.3 chứng minh điều gì?
A. Server có thể phân giải DNS A của tên miền yêu cầu kết nối.
B. Server đã lưu đầy đủ bản ghi TCP ACK của mọi request HTTPS.
C. Server sở hữu private key qua chữ ký trên handshake transcript.
D. Server gửi private key trong certificate để client đọc được.
Đáp án đúng: C

24. Thông điệp Finished của TLS 1.3 giúp xác nhận điều gì giữa hai bên?
A. Tính toàn vẹn handshake transcript qua khóa bí mật dẫn xuất.
B. Giá trị TTL IP sẽ không bị router thay đổi trên đường đi.
C. Root CA đã kiểm tra tình trạng thu hồi trước mỗi HTTP request.
D. Tên miền DNS được giữ nguyên trong cache tới hết phiên TLS.
Đáp án đúng: A

25. HKDF trong TLS 1.3 được dùng để đạt mục đích nào về khóa?
A. Ký certificate X.509 bằng khóa đối xứng của trình duyệt.
B. Tạo địa chỉ IP và cổng TCP mới cho từng application record.
C. Mã hóa DNS A record trước khi gửi qua liên kết Ethernet.
D. Dẫn xuất secrets và traffic keys từ bí mật của handshake.
Đáp án đúng: D

26. Bộ mã hóa nào phù hợp cho record protection trong TLS 1.3?
A. AEAD như AES-GCM hoặc ChaCha20-Poly1305 dùng cho bản ghi.
B. RSA key transport kết hợp RC4 để mã hóa record trực tiếp.
C. CBC 3DES không có kiểm tra toàn vẹn của phần bản mã.
D. RSA công khai mã hóa từng HTTP body mà không sinh session key.
Đáp án đúng: A

27. Trong TLS 1.2, static RSA key transport có yếu điểm nào so với ECDHE?
A. Mọi phiên TLS 1.2 bắt buộc bỏ qua kiểm tra hostname.
B. Không có forward secrecy nếu khóa riêng server bị lộ.
C. Bản ghi certificate không dùng được với chữ ký SHA-256.
D. Client không thể dùng DNS AAAA để kết nối đến server.
Đáp án đúng: B

28. mTLS khác TLS chỉ xác thực máy chủ ở điểm quan trọng nào?
A. Client gửi khóa riêng cho server để giải mã chứng thư CA.
B. Server cũng xác thực client qua chứng thư do client cung cấp.
C. Server không cần chứng thư nếu client đã đăng nhập ứng dụng.
D. Client và server bỏ mã hóa bản ghi sau khi kiểm tra identity.
Đáp án đúng: B

29. Khi mTLS đã xác minh danh tính của client, dịch vụ còn cần bước bảo mật nào?
A. Mặc định cấp quyền quản trị vì certificate có chữ ký CA.
B. Gán quyền ghi tự động theo Organization của issuer CA.
C. Bỏ kiểm tra role vì mTLS đã thay thế toàn bộ authorization.
D. Phân quyền theo danh tính để quyết định client được thao tác gì.
Đáp án đúng: D

30. Server muốn tin cậy chứng thư client khi bật mTLS thì phải chuẩn bị điều gì?
A. Trust store chứa các CA phù hợp để xác minh chuỗi client.
B. DNS resolver có bản ghi PTR chính xác của mọi máy khách.
C. Router biết MAC address của tất cả browser ở mạng từ xa.
D. Session ticket của TLS được công khai giữa mọi máy khách.
Đáp án đúng: A

31. TLS resumption bằng PSK hoặc ticket được dùng chủ yếu để làm gì?
A. Bỏ hẳn mã hóa bản ghi vì server đã có lịch sử kết nối.
B. Bắt client gửi private key của server trong ClientHello mới.
C. Giảm chi phí handshake khi kết nối lại theo trạng thái đã tin cậy.
D. Tạo root certificate mới cho mỗi phiên HTTPS được nối lại.
Đáp án đúng: C

32. Khi dùng 0-RTT early data trong TLS 1.3, vì sao POST thanh toán có nguy cơ?
A. Early data tự bỏ kiểm tra certificate chain khi kết nối lại.
B. Early data có thể bị replay nên thao tác cần chống gửi lặp.
C. Early data chỉ được truyền qua UDP không hỗ trợ ACK của TCP.
D. Early data luôn khiến server từ chối mọi cookie của browser.
Đáp án đúng: B

33. Sau handshake, TLS bảo vệ application data ở thành phần giao thức nào?
A. TLS record layer dùng traffic keys để mã hóa và xác thực.
B. DNS resolver dùng public key của root CA để mã hóa response.
C. Router IP dùng session ticket để mã hóa gói trên mỗi chặng.
D. TCP dùng certificate signature để xác minh từng segment.
Đáp án đúng: A

34. Khóa riêng của server HTTPS nên được lưu trữ như thế nào trong vận hành?
A. Bản certificate công khai để client có thể xác minh handshake.
B. Bản ghi TXT của DNS để mọi client đều truy cập được khóa.
C. Access log server để đội vận hành thuận tiện truy vết khóa.
D. Kho khóa an toàn, giới hạn quyền đọc, không đưa vào repository.
Đáp án đúng: D

35. Chứng thư HTTPS gần hết hạn, quy trình gia hạn nào giảm gián đoạn?
A. Đợi NotAfter qua rồi yêu cầu toàn bộ client kết nối lại.
B. Đổi IP của server mà vẫn tiếp tục sử dụng chứng thư cũ.
C. Cấp cert mới, triển khai và kiểm tra SAN cùng chain trước hạn.
D. Kéo dài TLS session timeout để bỏ qua NotAfter của cert.
Đáp án đúng: C

36. Khóa riêng của server đã bị lộ, hướng xử lý sự cố TLS nào là cốt lõi?
A. Gia hạn certificate nhưng tiếp tục sử dụng khóa riêng đã lộ.
B. Chỉnh bản ghi DNS rồi giữ nguyên key pair và trust chain.
C. Tăng TLS log verbosity mà không thay chứng thư hoặc khóa.
D. Thu hồi cert liên quan, tạo khóa mới và triển khai thay thế.
Đáp án đúng: D

37. TLS kết thúc ở reverse proxy, còn proxy gửi HTTP thuần tới backend. Kết luận nào đúng?
A. Toàn bộ đường tới backend vẫn được TLS bảo vệ từ client.
B. TLS tự sinh mTLS giữa proxy và backend mà không cần cấu hình.
C. Đoạn proxy–backend không được TLS bảo vệ khi đi bằng HTTP.
D. Backend nhận lại traffic keys từ client để giải mã HTTP.
Đáp án đúng: C

38. Cần mã hóa cả kết nối từ reverse proxy tới backend. Thiết kế nào đáp ứng?
A. Gửi HTTP backend qua TCP port 443 nhưng không tạo handshake.
B. Thiết lập TLS riêng tới backend và xác minh chứng thư của nó.
C. Gắn X-Forwarded-Proto: https vào mọi HTTP request nội bộ.
D. Giữ TLS đoạn client–proxy và dùng HTTP thuần trong mạng riêng.
Đáp án đúng: B

39. Certificate pinning có thách thức vận hành nào khi thay khóa hợp lệ?
A. Root CA tự đổi DNS A record khi chứng thư được gia hạn.
B. Client không thể kiểm tra chữ ký chứng thư khi đã dùng pin.
C. Client có thể từ chối khóa mới nếu pin chưa được cập nhật.
D. TLS sẽ tự tạo lại private key cũ từ session resumption.
Đáp án đúng: C

40. Khi client bỏ xác thực chain và hostname để vượt lỗi TLS, nguy cơ nào tăng lên?
A. Có thể chấp nhận server giả mạo dù kết nối vẫn mã hóa.
B. Client sẽ mất tính năng retransmission của luồng TCP.
C. Root CA trong trust store sẽ bị xóa sau lần kết nối đó.
D. DNS sẽ tự chuyển toàn bộ bản ghi AAAA thành bản ghi A.
Đáp án đúng: A

41. Cấu hình phiên bản TLS nào phù hợp làm mức nền cho dịch vụ web hiện đại?
A. Bật SSL 3.0 và TLS 1.0 để tăng hỗ trợ client cũ.
B. Bật SSL 2.0 kết hợp certificate có public key dài hơn.
C. Cho phép TLS 1.2/1.3, vô hiệu TLS 1.0/1.1 đã lỗi thời.
D. Dùng TLS 1.1 và tắt TLS 1.3 để giảm chi phí bắt tay.
Đáp án đúng: C

42. Đối với cipher suites hiện đại, nhóm thuật toán nào được khuyến nghị?
A. RC4-MD5 và 3DES-CBC, ưu tiên cipher ra đời từ trước.
B. AES-GCM và ChaCha20-Poly1305, tránh các bộ mã RC4/3DES.
C. NULL cipher cho HTTP và chỉ dùng certificate để xác thực.
D. RSA-EXPORT cipher dùng khóa ngắn để giảm CPU server.
Đáp án đúng: B

43. TLS 1.3 thay đổi gì liên quan tới RSA key transport và chữ ký RSA?
A. Giữ RSA key transport cho mọi suite khi server có cert RSA.
B. Loại RSA key transport nhưng vẫn có thể xác thực bằng chữ ký RSA.
C. Cấm mọi chứng thư có public key RSA làm danh tính máy chủ.
D. Mã hóa toàn bộ HTTP body trực tiếp bằng public key của RSA.
Đáp án đúng: B

44. Muốn xem handshake và SNI của api.example.com qua OpenSSL, lệnh nào hợp lý?
A. openssl s_client -connect api.example.com:443 -no_tls1_3 -quiet
B. openssl x509 -in api.example.com -text -noout -servername api.example.com
C. openssl verify -CAfile api.example.com:443 -servername api.example.com
D. openssl s_client -connect api.example.com:443 -servername api.example.com
Đáp án đúng: D

45. Có tệp PEM server.pem, muốn xem NotBefore/NotAfter và SAN bằng OpenSSL. Dùng lệnh nào?
A. openssl pkey -in server.pem -noout -dates -ext subjectAltName
B. openssl x509 -in server.pem -noout -dates -ext subjectAltName
C. openssl dgst -in server.pem -noout -dates -ext subjectAltName
D. openssl s_client -in server.pem -noout -dates -ext subjectAltName
Đáp án đúng: B

46. Có root.pem, inter.pem và leaf.pem, lệnh nào kiểm tra chain chữ ký bằng OpenSSL phù hợp?
A. openssl verify -CAfile leaf.pem -untrusted inter.pem root.pem
B. openssl x509 -CAfile root.pem -untrusted inter.pem leaf.pem
C. openssl s_client -CAfile root.pem -untrusted inter.pem leaf.pem
D. openssl verify -CAfile root.pem -untrusted inter.pem leaf.pem
Đáp án đúng: D

47. Trong capture TLS 1.3 không có traffic secrets, Wireshark thường quan sát được gì?
A. ClientHello, ServerHello và record; dữ liệu ứng dụng vẫn mã hóa.
B. HTTP body nằm trong encrypted record sau handshake thành công.
C. Private key máy chủ nằm nguyên trong CertificateVerify.
D. Mật khẩu ứng dụng xuất hiện trong trường hostname của SNI.
Đáp án đúng: A

48. Khi gặp TLS alert handshake_failure, trình tự chẩn đoán kỹ thuật nên bắt đầu từ đâu?
A. Đổi DNS A record liên tục để tránh lỗi cipher không tương thích.
B. So log, phiên bản TLS, cipher/groups và yêu cầu client cert.
C. Tăng TTL IPv4 ở client rồi xem lại kết quả xác thực chứng thư.
D. Tắt kiểm tra certificate trên mọi client trước khi kiểm tra log.
Đáp án đúng: B
