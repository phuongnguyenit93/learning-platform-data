1. Trong một request đọc secret, các thành phần chính của Vault phối hợp theo cách nào?
A. Storage backend nhận request, tự xác thực client và chọn policy trước khi trả secret cho ứng dụng.
B. Vault nhận request qua listener, xác thực token, kiểm ACL rồi gọi secrets engine theo path.
C. Barrier encryption kiểm tra danh tính người dùng rồi cấp capability cho từng path.
D. Secrets engine xác minh TLS và token, còn listener chỉ chuyển tiếp dữ liệu tới storage.
Đáp án đúng: B

2. Vault đang ở trạng thái sealed; hệ quả vận hành nào được mô tả chính xác nhất?
A. Vault vẫn đọc và ghi secret bình thường nhưng tạm ngừng cấp token mới cho client.
B. Vault chỉ từ chối request ghi dữ liệu, còn request đọc vẫn lấy dữ liệu từ storage.
C. Vault chuyển request sang standby node cho đến khi active node được unseal.
D. Khi sealed, encryption barrier khóa nên Vault không thể xử lý truy cập secret.
Đáp án đúng: D

3. Với Shamir seal, threshold và key shares nên được tổ chức như thế nào?
A. Sao chép toàn bộ key shares lên mỗi node để node nào cũng tự unseal được.
B. Đặt threshold bằng một để giảm thời gian khôi phục khi người giữ khóa vắng mặt.
C. Cần đủ số shares theo threshold và nên phân phối chúng cho người giữ độc lập.
D. Lưu một share trong storage backend và gửi các share còn lại qua client.
Đáp án đúng: C

4. Trong mô hình auto-unseal, recovery keys thường được dùng cho mục đích nào?
A. Recovery keys dùng cho thao tác đặc quyền như tạo root token hoặc rekey recovery keys.
B. Recovery keys thay KMS/HSM để mở encryption barrier mỗi khi Vault khởi động lại trên mọi node.
C. Recovery keys giải mã trực tiếp mọi secret trong storage mà không cần Vault server.
D. Recovery keys xác thực workload hằng ngày thay cho auth method và token.
Đáp án đúng: A

5. Sau khi hoàn tất bootstrap và cấu hình policy, cách xử lý initial root token nào an toàn hơn?
A. Giữ root token làm credential chung để nhóm vận hành xử lý mọi sự cố production.
B. Đặt root token trong pipeline variable để các job tự cấu hình policy khi chạy.
C. Gia hạn root token định kỳ rồi chia sẻ qua email mã hóa cho quản trị viên.
D. Thu hồi initial root token và dùng danh tính riêng với policy hẹp cho vận hành.
Đáp án đúng: D

6. Một Vault listener phục vụ workload production cần cấu hình TLS ra sao?
A. Tắt hostname verification vì listener chỉ nhận request từ subnet nội bộ.
B. Dùng HTTP từ client đến listener rồi mã hóa riêng kết nối proxy đến storage.
C. Chấp nhận mọi certificate do client cung cấp để tránh gián đoạn khi certificate đổi.
D. Bật TLS với certificate hợp lệ, xác minh CA và hostname, gia hạn đúng hạn.
Đáp án đúng: D

7. Vault đặt sau reverse proxy; cách xử lý header chuyển tiếp nào giữ đúng ranh giới tin cậy?
A. Tin mọi X-Forwarded-For từ client vì proxy tự loại bỏ giá trị giả mạo trước khi chuyển request.
B. Tin forwarded headers do proxy tin cậy ghi, không nhận giá trị client tự gửi.
C. Cho phép client tự đặt scheme và host để Vault tạo redirect theo yêu cầu.
D. Tắt xác minh TLS ở listener vì proxy đã xử lý kiểm soát danh tính.
Đáp án đúng: B

8. Một cụm Vault HA dùng Integrated Storage Raft; mô tả nào đúng về vai trò active và standby?
A. Mọi node ghi độc lập vào storage, sau đó hợp nhất dữ liệu theo lịch khi kết nối phục hồi.
B. Standby chỉ giữ snapshot tĩnh và không tham gia quorum Raft của cụm.
C. Mỗi node active quản lý một secrets engine riêng, không có leader chung.
D. Active xử lý ghi; standby chuyển tiếp hoặc nhận vai trò khi failover theo cơ chế HA.
Đáp án đúng: D

9. Cụm Raft có ba node và mất kết nối hai node; điều gì xảy ra với khả năng commit ghi?
A. Node còn lại tự trở thành quorum vì Raft chỉ cần một node đang hoạt động.
B. Node còn lại ghi cục bộ rồi tự đồng bộ khi hai node khác trở lại.
C. Mất quorum nên node còn lại không thể commit các thay đổi ghi mới.
D. Cụm chuyển sang Shamir seal và tiếp tục nhận ghi mà không cần quorum.
Đáp án đúng: C

10. Khi lập kế hoạch backup và phục hồi Vault Integrated Storage, lựa chọn nào phù hợp?
A. Dùng Raft snapshot nhất quán, bảo vệ bản sao và diễn tập restore với seal/KMS material.
B. Dùng performance replication như bản backup độc lập để phục hồi mọi lần xóa nhầm.
C. Sao chép thư mục dữ liệu đang chạy bằng file copy, không cần snapshot nhất quán hay kiểm tra Raft.
D. Chỉ backup listener config vì secret có thể được tạo lại sau khi restore.
Đáp án đúng: A

11. Chọn auth method cho người vận hành và workload nên dựa trên tiêu chí nào?
A. Dùng AppRole cho mọi nhân viên và workload vì chỉ cần một auth method, không cần ánh xạ danh tính.
B. Chọn theo nguồn danh tính: OIDC/LDAP cho người, workload auth phù hợp cho máy.
C. Dùng root token cho pipeline và Kubernetes để tránh identity mapping.
D. Chọn auth method theo secrets engine đã mount, không xét nguồn danh tính.
Đáp án đúng: B

12. Với AppRole, cách bảo vệ SecretID khi bootstrap workload nào hợp lý?
A. Đặt SecretID không hết hạn trong image để mọi instance dùng chung khi khởi động.
B. Lưu SecretID cùng role_id trong repository vì role_id không phải secret.
C. Giới hạn TTL, số lần dùng, CIDR khi cần và truyền qua kênh bảo vệ.
D. Cho phép SecretID dùng lâu dài để pipeline retry khi cần.
Đáp án đúng: C

13. Một Kubernetes workload chỉ được đọc secret của namespace riêng; Vault role nên ràng buộc thế nào?
A. Kiểm tra tên pod vì pod name đã duy nhất trên toàn bộ cluster.
B. Ràng buộc role với service account và namespace cụ thể, gắn policy đúng path.
C. Cho mọi service account trong cluster xác thực rồi dựa vào network policy để giới hạn path.
D. Gắn policy quản trị rộng và để Kubernetes RBAC giới hạn các path Vault.
Đáp án đúng: B

14. Một workload cloud cần xác thực Vault mà không giữ access key dài hạn; cách nào phù hợp?
A. Dùng token quản trị cho workload khi chạy trong cùng cloud account.
B. Dùng cloud auth xác minh workload identity để cấp Vault token ngắn hạn.
C. Dùng token của quản trị viên đã đăng nhập để workload chia sẻ trong runtime.
D. Cho mọi instance trong account dùng chung một role không ràng buộc identity.
Đáp án đúng: B

15. ACL policy của Vault được dùng để kiểm soát điều gì?
A. Capability trên path như read, create, update, delete hoặc list theo nhu cầu.
B. Quyền truy cập mạng đến listener, lựa chọn TLS cipher suite và cấu hình endpoint cho client.
C. Số lượng token được phát hành và thuật toán mã hóa storage backend.
D. Quyền hệ điều hành trên file chứa secret đã render ra máy workload.
Đáp án đúng: A

16. Với KV v2, policy đọc nội dung secret tại một path thường cần trỏ tới đâu?
A. Dùng path gốc của mount vì KV v2 tự ánh xạ capability sang mọi endpoint data và metadata.
B. Dùng path config của mount vì dữ liệu secret được lưu cùng cấu hình engine.
C. Đọc nội dung qua data path; metadata path dùng cho metadata và thao tác liên quan.
D. Dùng path destroy của mount vì thao tác đọc cần xác minh version đã xóa.
Đáp án đúng: C

17. Khi policy dùng wildcard trên nhiều secret path, cách kiểm tra nào giúp tránh cấp quyền quá rộng?
A. Chỉ đọc policy text vì wildcard luôn khớp đúng phạm vi tác giả dự định.
B. Thêm deny rule sau cùng vì policy được đánh giá theo thứ tự khai báo.
C. Kiểm tra bằng root token vì quyền root phản ánh capability workload.
D. Thử bằng token đại diện và kiểm tra capability thực tế trên các path.
Đáp án đúng: D

18. Một token có TTL và max TTL; cách renewal nào mô tả đúng giới hạn vòng đời?
A. Renewal luôn đặt lại TTL vô hạn miễn token chưa bị revoke và policy vẫn còn gắn.
B. Renewal chỉ kéo dài token trong max TTL và điều kiện policy tương ứng.
C. Token hết TTL vẫn hợp lệ nếu client tiếp tục gửi request định kỳ.
D. Max TTL chỉ áp dụng batch token, không áp dụng service token.
Đáp án đúng: B

19. Sự khác biệt vận hành điển hình giữa service token và batch token là gì?
A. Batch token có accessor và lưu server-side, còn service token là stateless.
B. Hai loại token có cùng vòng đời, chỉ khác độ dài token string.
C. Service token có accessor và renewal; batch token nhẹ và không renewable.
D. Service token không thể revoke, còn batch token được renew vô hạn.
Đáp án đúng: C

20. Token accessor hỗ trợ tác vụ vận hành nào trong Vault?
A. Dùng accessor thay token để đọc secret theo policy của token gốc.
B. Giải mã token string để lấy identity và toàn bộ capability đã cấp.
C. Accessor tra cứu hoặc revoke token, nhưng không dùng để xác thực.
D. Tạo token con cùng quyền mà không cần auth method hoặc policy.
Đáp án đúng: C

21. Khi nào token orphan có thể hữu ích và cần lưu ý điều gì?
A. Orphan token sống độc lập với parent nên cần quản lý TTL và revoke riêng.
B. Token con bị revoke cùng parent theo TTL, dù quan hệ token đã bị xóa khỏi Vault.
C. Token orphan tự bỏ qua ACL policy và truy cập mọi secrets engine.
D. Batch token dùng accessor để renew sau khi parent đã hết hạn.
Đáp án đúng: A

22. Response wrapping giúp chuyển giao secret bootstrap theo cách nào?
A. Mã hóa payload bằng token gốc rồi cho nhiều client unwrap cùng lúc.
B. Wrapping token có TTL ngắn và chỉ unwrap một lần để chuyển payload.
C. Tạo bản plaintext trong audit log để recipient lấy khi wrapping token hết hạn.
D. Kéo dài TTL SecretID để recipient không cần xác thực khi unwrap.
Đáp án đúng: B

23. Điểm khác biệt quan trọng của KV v2 so với KV v1 là gì?
A. KV v2 có versioning, metadata, soft delete, undelete và destroy.
B. KV v1 hỗ trợ versioning nhiều phiên bản, còn KV v2 chỉ lưu giá trị mới nhất.
C. KV v2 tạo credential động theo lease, còn KV v1 lưu secret tĩnh.
D. KV v1 có check-and-set, còn KV v2 bỏ kiểm soát ghi đồng thời.
Đáp án đúng: A

24. Hai pipeline cùng cập nhật một secret KV v2; check-and-set giúp điều gì?
A. CAS yêu cầu version kỳ vọng để ngăn pipeline ghi đè version mới.
B. Tự hợp nhất hai payload thành một version mà không xử lý xung đột.
C. Khóa toàn bộ mount trong lúc pipeline đầu tiên đang chạy.
D. Mã hóa secret bằng Transit trước khi ghi version mới vào KV.
Đáp án đúng: A

25. Dynamic secrets từ Database secrets engine đem lại lợi ích nào?
A. Dùng một mật khẩu database tĩnh cho mọi workload nhưng ghi nhận lease trong Vault.
B. Tạo tài khoản database không thời hạn để tránh phụ thuộc Vault.
C. Lưu password gốc database trong KV rồi chia sẻ cho từng consumer.
D. Cấp credential riêng có lease cho consumer và thu hồi theo lease.
Đáp án đúng: D

26. Vault không thu hồi được credential động vì database tạm ngừng hoạt động; xử lý nào phù hợp?
A. Coi lease hết hạn là credential đã bị vô hiệu trong database và không cần đối soát.
B. Xóa lease record để giải phóng storage và bỏ qua tài khoản còn lại.
C. Tạo credential mới cho mọi consumer mà không rà soát credential cũ.
D. Ghi nhận revoke chưa hoàn tất, khôi phục DB và reconcile credential còn sống.
Đáp án đúng: D

27. Static role rotation cho tài khoản database hiện hữu cần chú ý điều gì?
A. Đồng bộ đổi DB password, cập nhật Vault secret và consumer.
B. Đổi Vault secret trước, để database tự đồng bộ password.
C. Tạo user database mới mỗi lần rotation rồi bỏ tài khoản cũ ngay lập tức.
D. Giữ credential consumer không đổi để connection pool không bị ảnh hưởng.
Đáp án đúng: A

28. PKI secrets engine dùng certificate role để giới hạn việc cấp chứng chỉ như thế nào?
A. PKI role giới hạn SAN/domain, TTL và thuộc tính chứng chỉ được phép.
B. Cho client tự chọn SAN bất kỳ rồi dựa vào CRL để giới hạn hostname.
C. Dùng role đặt ACL đọc KV và bỏ qua kiểm tra CA khi issue.
D. Chỉ giới hạn độ dài private key vì SAN và TTL do client tự quyết định.
Đáp án đúng: A

29. Certificate do Vault PKI gia hạn nhưng workload vẫn dùng certificate cũ; cần kiểm tra điều gì?
A. CA xóa cert cũ khỏi storage nên mọi kết nối tự chuyển sang bản mới.
B. Kiểm tra file cert đã cập nhật và tiến trình đã reload certificate mới chưa.
C. Vault phát hành cert mới nên client luôn tự tải lại mà không cần reload tiến trình hoặc thay file.
D. Token workload đã renew chưa vì certificate TLS phụ thuộc TTL token.
Đáp án đúng: B

30. Sau khi revoke certificate trong Vault PKI, điều gì cần để relying party thực sự áp dụng việc thu hồi?
A. Phân phối CRL hoặc trạng thái thu hồi và bảo đảm client kiểm tra chúng.
B. Xóa file certificate khỏi Vault vì relying party tự biết cert đã bị revoke.
C. Đổi private key CA mà không cập nhật trust store của client.
D. Giảm TTL token Vault vì token hết hạn sẽ vô hiệu certificate đã cấp.
Đáp án đúng: A

31. Transit secrets engine khác KV ở điểm nào?
A. Transit lưu plaintext trong mount, còn KV chỉ lưu ciphertext do client tạo.
B. Transit chỉ quản lý certificate TLS, còn KV mã hóa dữ liệu nghiệp vụ.
C. Transit xử lý crypto qua API, dữ liệu ứng dụng có thể nằm ngoài Vault.
D. Transit phát hành credential động cho database, còn KV quản lý lease.
Đáp án đúng: C

32. Sau khi rotate Transit key, cách xử lý ciphertext cũ nào phù hợp?
A. Rewrap đổi ciphertext sang key version mới mà không lộ plaintext.
B. Xóa key version cũ để ciphertext trước đó tự chuyển sang version mới.
C. Giải mã plaintext ra log rồi mã hóa lại bằng key mới từ client.
D. Giữ key version cũ làm key encrypt mặc định cho mọi dữ liệu.
Đáp án đúng: A

33. Một workload chỉ cần mã hóa dữ liệu qua Transit; policy nên cấp capability nào?
A. Cấp root capability trên mount Transit để client tự chọn mọi key version.
B. Cấp update trên encrypt path của key, không cấp decrypt hoặc đọc key material.
C. Cấp update trên toàn bộ path Vault vì encrypt cần quyền quản trị engine.
D. Cấp quyền đọc key material để workload tự mã hóa ngoài Vault.
Đáp án đúng: B

34. Vault có nhiều audit device; điều gì xảy ra nếu mọi audit device đều không thể ghi log?
A. Vault vẫn xử lý request, chỉ ghi cảnh báo sau khi audit sink lỗi.
B. Vault bỏ audit cho request đọc nhưng vẫn ghi audit cho request ghi.
C. Vault lưu audit record vô hạn trong bộ nhớ rồi tự flush khi thiết bị hồi phục.
D. Nếu mọi audit device đều lỗi ghi, Vault từ chối xử lý request.
Đáp án đúng: D

35. HMAC trong audit log Vault giúp cân bằng khả năng điều tra và bảo vệ dữ liệu thế nào?
A. HMAC cho phép khôi phục plaintext khi auditor có token accessor hợp lệ.
B. HMAC thay TLS listener vì audit record đã được ký trước khi gửi.
C. HMAC thay TLS listener trước khi gửi audit record.
D. HMAC cho phép đối chiếu cùng giá trị mà không lộ giá trị gốc.
Đáp án đúng: D

36. Performance replication và DR replication khác nhau chủ yếu ở mục đích nào?
A. Performance replication là backup, còn DR replica phục vụ đọc thường xuyên.
B. DR secondary ghi song song; performance secondary chỉ chờ failover.
C. Performance replica mở rộng đọc; DR replica chờ promote khi thảm họa.
D. Hai cơ chế chỉ khác số node, không khác cách phục vụ request hay failover.
Đáp án đúng: C

37. Pipeline CI/CD cần lấy secret từ Vault mà không lưu token dài hạn; thiết kế nào phù hợp?
A. Lưu root token trong pipeline variable để job lấy khi deploy.
B. Đặt SecretID dài hạn trong artifact để job khác tái sử dụng.
C. Dùng workload auth để cấp token ngắn hạn với policy hẹp cho pipeline.
D. Dùng một token chung cho mọi repository trong tổ chức để đơn giản hóa phân quyền.
Đáp án đúng: C
