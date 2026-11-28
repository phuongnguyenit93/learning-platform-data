# Post-incident privilege review: rà soát quyền đặc biệt sau sự cố

## 1. Mục tiêu và vị trí trong ứng phó sự cố

Post-incident privilege review là hoạt động rà soát các quyền đặc biệt sau sự cố để xác định quyền nào đã bị lợi dụng, quyền nào vẫn còn tồn tại và quyền nào cần thay đổi trước khi chấp nhận trạng thái vận hành mới. Trong bối cảnh Privileged Access Management (PAM), đối tượng rà soát không chỉ là tài khoản quản trị. Phạm vi còn bao gồm service account, nhóm quản trị, role, quyền ủy nhiệm, credential trong vault, khóa SSH, token, chính sách truy cập và các đường đi cho phép trở thành người quản trị.

Kết quả cần đạt là một tập kết luận có bằng chứng:

- Ai hoặc workload nào còn khả năng thực hiện hành động đặc quyền?
- Khả năng đó đến từ đâu, đi qua những hệ thống nào và có bị giới hạn đúng không?
- Những quyền được tạo tạm trong sự cố đã được thu hồi hoặc chuyển thành quyền chính thức có kiểm soát chưa?
- Biện pháp khắc phục có thực sự chặn đường truy cập cũ hay mới chỉ thay đổi cấu hình trên giấy?
- Rủi ro nào còn tồn tại, ai chấp nhận và đến khi nào phải xử lý?

Rà soát sau sự cố không thay thế containment khẩn cấp. Nếu phát hiện một đường truy cập của đối tượng tấn công còn hoạt động, cần chuyển ngay phát hiện đó về luồng ứng phó sự cố để xử lý theo thẩm quyền. Không đợi hoàn thành báo cáo cuối cùng mới thu hồi một token đang bị lạm dụng.

Hoạt động này cũng không đồng nghĩa với một cuộc họp tổng kết kinh nghiệm. Tổng kết kinh nghiệm tìm nguyên nhân và cải tiến quy trình; privilege review kiểm chứng một tập quyền và khả năng truy cập cụ thể. Hai hoạt động hỗ trợ nhau nhưng cần sản phẩm bàn giao riêng.

## 2. Rà soát quyền được cấp và khả năng thực hiện quyền

Một sai sót phổ biến là chỉ xuất danh sách thành viên nhóm quản trị rồi đánh dấu đã hoàn thành. Danh sách đó mới mô tả một phần cấu hình quyền, chưa chứng minh khả năng truy cập còn hiệu lực.

### 2.1. Quyền được cấp

Quyền được cấp có thể xuất hiện dưới nhiều dạng:

- Thành viên trực tiếp hoặc gián tiếp của nhóm quản trị.
- Role được gán tại tài khoản, dự án, subscription, tenant hoặc tài nguyên.
- Quyền sử dụng một credential trong vault.
- Quyền phê duyệt hoặc tự kích hoạt một role JIT.
- Quyền sửa policy, workflow, pipeline hoặc cấu hình cấp quyền.
- Quyền impersonation, assume role hoặc ủy nhiệm sang một danh tính khác.

### 2.2. Khả năng thực hiện quyền

Khả năng thực hiện quyền phụ thuộc cả trạng thái chạy và chuỗi tin cậy:

- Một phiên quản trị đã được mở trước thời điểm thu hồi role.
- Access token hoặc credential tạm thời còn hiệu lực.
- Mật khẩu hoặc khóa đã được sao chép ra ngoài vault.
- Quyền kế thừa qua nhóm lồng nhau hoặc role cha.
- Một máy trung gian có agent, scheduler hoặc tác vụ chạy với quyền cao.
- Một workload có thể đọc secret của danh tính mạnh hơn.
- Một tài khoản không có role quản trị trực tiếp nhưng có thể sửa pipeline triển khai lên production.

Vì vậy, mỗi kết luận cần tách hai câu hỏi: “quyền được cấp đã thay đổi chưa?” và “khả năng thực hiện hành động cũ đã chấm dứt chưa?”. Hai câu hỏi này phải có bằng chứng riêng nếu cơ chế của hệ thống yêu cầu.

Ví dụ: xóa một tài khoản khỏi nhóm quản trị là bằng chứng thay đổi membership. Điều đó không tự chứng minh mọi phiên và mọi token được phát hành trước đó đã mất hiệu lực. Nhóm xử lý phải kiểm tra cơ chế cụ thể của từng hệ thống, thời gian sống của token và trạng thái phiên tại nơi nhận truy cập.

## 3. Xác định phạm vi từ sự cố, không chỉ từ hệ thống PAM

Phạm vi review nên bắt đầu từ các danh tính, tài sản và đường truy cập liên quan đến sự cố, sau đó mở rộng theo quan hệ tin cậy có bằng chứng.

Có thể chia phạm vi thành ba lớp:

| Lớp | Nội dung rà soát | Câu hỏi trọng tâm |
| --- | --- | --- |
| Trực tiếp | Danh tính bị chiếm, credential bị lộ, hệ thống bị truy cập | Đường truy cập nào đã được sử dụng hoặc có dấu hiệu bị sử dụng? |
| Liên đới | Role có thể assume, secret có thể đọc, máy quản trị có thể tiếp cận | Từ điểm bị chiếm có thể mở rộng đến đâu? |
| Phục hồi | Quyền cấp thêm cho ứng cứu, tài khoản tạm, ngoại lệ chính sách | Sau khi xử lý sự cố, quyền tạm nào vẫn còn? |

Một sự cố liên quan đến service account triển khai có thể yêu cầu rà soát cả pipeline CI/CD, kho secret, artifact registry, cơ chế ký và quyền trên hệ thống đích. Chỉ kiểm tra danh sách tài khoản trong PAM sẽ bỏ sót các đường truy cập nằm ngoài gateway hoặc vault.

Phạm vi cần ghi rõ:

1. Mã sự cố và mục tiêu review.
2. Danh tính người dùng, workload và nhóm có liên quan.
3. Hệ thống cấp quyền và hệ thống thực thi quyền.
4. Tài sản, môi trường và ranh giới tin cậy.
5. Khoảng thời gian rà soát và múi giờ sử dụng.
6. Nguồn dữ liệu đã có, nguồn còn thiếu và mức độ tin cậy.
7. Phần ngoài phạm vi, lý do và người chấp nhận giới hạn đó.

Phạm vi có thể thay đổi khi phát hiện thêm đường truy cập. Mọi lần mở rộng cần cập nhật danh sách tài sản và người phụ trách để không có phần việc bị bỏ lại giữa các đội.

## 4. Bảo toàn bằng chứng và dựng mốc thời gian

Review cần dữ liệu đủ để so sánh trạng thái trước, trong và sau sự cố. Trước khi xóa tài khoản tạm hoặc thay đổi policy, lưu lại bằng chứng phù hợp với quy trình ứng phó sự cố của tổ chức. Nếu rủi ro đang diễn ra đòi hỏi hành động ngay, việc bảo vệ hệ thống được thực hiện theo quyết định của người chỉ huy sự cố; ghi lại hành động, thời điểm và tác động đến bằng chứng.

### 4.1. Những dữ liệu cần thu thập

- Danh sách role, membership, policy và quyền ủy nhiệm.
- Audit log của hệ thống danh tính, PAM, vault và tài nguyên đích.
- Lịch sử checkout secret, rotation và thay đổi ACL của vault.
- Lịch sử cấp, kích hoạt, hết hạn và thu hồi JIT/JEA.
- Metadata phiên quản trị và bản ghi phiên nếu có.
- Lịch sử đăng ký khóa, chứng thư, API key và phương thức xác thực.
- Thay đổi cấu hình pipeline, agent, scheduler và tài khoản chạy dịch vụ.
- Ticket phê duyệt, quyết định khẩn cấp và các ngoại lệ trong thời gian ứng cứu.

Không đưa giá trị secret, private key hoặc token còn hiệu lực vào bảng review. Dùng mã định danh, fingerprint phù hợp, phiên bản credential và đường dẫn đến bằng chứng đã được kiểm soát truy cập.

### 4.2. Dòng thời gian tối thiểu

Một dòng thời gian hữu ích có thể gồm:

| Mốc | Ý nghĩa |
| --- | --- |
| T0 | Trạng thái gần nhất được xác nhận là đáng tin cậy |
| T1 | Dấu hiệu xâm nhập sớm nhất đã biết |
| T2 | Thời điểm phát hiện và bắt đầu ứng phó |
| T3 | Các thay đổi containment, thu hồi hoặc cấp quyền khẩn cấp |
| T4 | Phục hồi dịch vụ và xác minh trạng thái quyền |
| T5 | Đóng review hoặc bàn giao rủi ro tồn dư |

T1 là “sớm nhất đã biết”, không mặc định là thời điểm xâm nhập thật sự bắt đầu. Nếu log chỉ được lưu trong một khoảng ngắn, cần ghi rõ giới hạn quan sát.

Chuẩn hóa thời gian khi đối chiếu log. Lưu cả thời điểm sự kiện, thời điểm thu thập và nguồn phát sinh. Sai lệch đồng hồ hoặc độ trễ ghi log có thể làm thứ tự sự kiện trông khác thực tế.

### 4.3. Chọn baseline có thể tin cậy

Không mặc định cấu hình ngay trước lúc phát hiện là baseline an toàn. Đối tượng tấn công có thể đã thêm role hoặc khóa từ trước đó.

Ưu tiên đối chiếu nhiều nguồn: cấu hình được phê duyệt, lịch sử thay đổi, snapshot đủ sớm, khai báo hạ tầng và xác nhận của chủ hệ thống. Một baseline được lưu trong cùng môi trường đã bị chiếm cần được đánh giá lại tính toàn vẹn. Nếu chưa chứng minh được baseline đáng tin cậy, báo cáo phải thể hiện sự không chắc chắn này.

## 5. Lập sổ rà soát quyền

Sổ rà soát là nơi liên kết từng quyền hoặc đường truy cập với quyết định xử lý và bằng chứng xác minh. Một dòng không nhất thiết tương ứng một tài khoản; có thể là một quan hệ “principal → role → tài nguyên” hoặc một đường truy cập có nhiều bước.

Các trường nên có:

| Trường | Mục đích |
| --- | --- |
| Principal ID và loại danh tính | Tránh nhầm tài khoản trùng tên hoặc tài khoản được tạo lại |
| Owner nghiệp vụ và owner kỹ thuật | Xác định người giải thích nhu cầu và người thực hiện thay đổi |
| Tài nguyên, môi trường, phạm vi quyền | Biết quyền áp dụng ở đâu và rộng đến mức nào |
| Nguồn cấp quyền | Role trực tiếp, nhóm, kế thừa, vault, ủy nhiệm hoặc cơ chế khác |
| Quyền hiệu lực và đường nâng quyền | Mô tả khả năng thực tế, không chỉ nhãn role |
| Nhu cầu hợp lệ | Công việc cụ thể cần quyền này |
| Liên hệ với sự cố | Bị sử dụng, có thể bị tiếp cận, hoặc được cấp khi ứng cứu |
| Credential và phiên liên quan | Dùng định danh, phiên bản, thời điểm hết hạn; không lưu secret |
| Quyết định | Giữ, giảm, thu hồi, thay thế hoặc điều tra thêm |
| Hành động, người thực hiện, hạn xử lý | Chuyển kết luận thành công việc có trách nhiệm |
| Bằng chứng trước và sau | Cho phép kiểm tra lại độc lập |
| Trạng thái và rủi ro tồn dư | Phân biệt đã đổi cấu hình với đã xác minh hoàn tất |

Nếu thiếu owner, không tự kết luận quyền đó không còn được sử dụng. Đây là một phát hiện về quản trị cần xử lý. Việc thu hồi có thể vẫn cần thiết vì rủi ro, nhưng phải đánh giá phụ thuộc và chuẩn bị phương án giữ dịch vụ hoạt động.

Một trạng thái hợp lý cho từng dòng là:

```text
DISCOVERED
  -> ANALYZED
  -> DECIDED
  -> IMPLEMENTED
  -> VERIFIED
  -> CLOSED
```

Có thể có nhánh `RISK_ACCEPTED_UNTIL` cho ngoại lệ được phê duyệt có thời hạn. Không dùng nhánh này để biến thiếu bằng chứng thành đã xác minh.

## 6. Phân tích các đường truy cập đặc quyền

### 6.1. Tài khoản con người

Đối với quản trị viên, nhân sự ứng cứu, nhà cung cấp và tài khoản hỗ trợ, cần kiểm tra:

- Tài khoản sử dụng cho công việc thường ngày có bị trộn với tài khoản quản trị không?
- Quyền thường trực có cần thiết hay có thể chuyển sang JIT?
- Điều kiện phê duyệt có còn hiệu lực sau sự cố không?
- Người yêu cầu có thể tự phê duyệt hoặc sửa chính sách để tự cấp quyền không?
- Có nhóm lồng nhau hoặc role kế thừa làm quyền rộng hơn dự kiến không?
- Quyền truy cập qua bastion, gateway, VPN và truy cập trực tiếp có được đánh giá đủ không?

Cần rà soát cả quyền sửa cơ chế kiểm soát: quản trị PAM, quản trị vault, quản trị hệ thống danh tính và quyền sửa audit policy. Một tài khoản có thể không quản trị trực tiếp máy chủ nhưng có khả năng cấp cho chính nó quyền đó.

### 6.2. Danh tính máy và workload

Service account thường có thời gian sống dài, nhiều consumer và ít dấu hiệu tương tác của con người. Review cần xác định:

- Workload nào đang sử dụng danh tính và ai quản lý từng consumer?
- Credential được lấy từ vault, biến môi trường, file cấu hình hay nguồn khác?
- Danh tính có thể đăng nhập tương tác ngoài mục đích thiết kế không?
- Quyền có dùng chung giữa development, staging và production không?
- Có khả năng tạo credential mới, sửa trust policy hoặc impersonate danh tính mạnh hơn không?
- Cơ chế cấp credential ngắn hạn có được cấu hình đúng audience, phạm vi và điều kiện tin cậy không?

Một credential được rotation thành công không có nghĩa mọi bản sao đã trở nên vô dụng. Cần xác nhận credential cũ bị hệ thống đích từ chối và các đường cấp credential mới đã được kiểm soát.

### 6.3. Quyền thông qua cấu hình và chuỗi triển khai

Kiểm tra những quyền gián tiếp như:

```text
Tài khoản phát triển
  -> sửa pipeline
  -> pipeline đọc secret triển khai
  -> assume role production
  -> thay đổi dịch vụ production
```

Nếu review chỉ kiểm tra role của tài khoản phát triển ở production, có thể kết luận sai rằng tài khoản không có đặc quyền. Trong chuỗi này, quyền sửa pipeline là mắt xích cần được phân tích cùng kiểm soát phê duyệt, branch protection, danh tính runner và quyền truy cập secret.

Không cần chứng minh mọi chuỗi lý thuyết đều đã bị khai thác mới ghi nhận rủi ro. Tuy nhiên, phải phân biệt “đã quan sát”, “được xác nhận có thể thực hiện” và “giả thuyết cần kiểm tra”.

## 7. Rà soát credential, phiên và cơ chế duy trì truy cập

Ba lớp này cần được theo dõi riêng vì cách vô hiệu hóa có thể khác nhau.

| Lớp | Ví dụ | Bằng chứng cần hướng tới |
| --- | --- | --- |
| Credential hoặc khóa dài hạn | Mật khẩu, SSH key, API key, client secret | Credential cũ bị từ chối; consumer hợp lệ dùng bản mới |
| Credential hoặc phiên đã phát hành | Access token, refresh token, phiên web, phiên SSH | Đã thu hồi hoặc chấm dứt theo cơ chế hệ thống; thời gian hiệu lực còn lại được xử lý |
| Cơ chế cấp lại hoặc duy trì | Trust policy, khóa bổ sung, scheduled task, quyền tạo token | Nguồn cấp lại trái phép và đường duy trì đã bị loại bỏ hoặc giới hạn |

### 7.1. Trình tự xử lý cần phản ánh phụ thuộc

Với một service account có nhiều consumer, có thể cần:

1. Xác định danh sách consumer và mức độ quan trọng.
2. Chặn khả năng tạo thêm credential trái phép hoặc cấp lại quyền.
3. Cấp credential mới bằng kênh đáng tin cậy.
4. Chuyển consumer hợp lệ sang credential mới.
5. Vô hiệu hóa credential cũ theo kế hoạch containment.
6. Xử lý phiên và token còn hiệu lực bằng cơ chế phù hợp.
7. Xác minh truy cập hợp lệ và xác minh đường cũ bị từ chối.

Đây là khung ra quyết định, không phải thứ tự cố định áp dụng cho mọi tình huống. Nếu credential đang bị lạm dụng, người chỉ huy có thể quyết định vô hiệu hóa ngay trước khi chuyển đủ consumer. Quyết định phải ghi rõ tác động và phương án duy trì hoặc khôi phục dịch vụ.

### 7.2. Không tái đưa bí mật bị lộ vào hệ thống

Phương án rollback không được đơn giản là bật lại credential đã bị lộ. Nếu cần khôi phục dịch vụ, dùng cơ chế dự phòng đáng tin cậy, credential mới hoặc một đường truy cập khẩn cấp được kiểm soát.

Báo cáo cũng cần ghi rõ các bản sao secret trong pipeline, lịch sử cấu hình, cache hoặc máy quản trị đã được đánh giá thế nào. Việc xóa một bản sao không chứng minh chưa từng có bản sao khác; tính an toàn chủ yếu đến từ vô hiệu hóa credential và kiểm soát nguồn cấp lại.

## 8. Thu hồi quyền khẩn cấp và ngoại lệ trong thời gian ứng cứu

Trong ứng phó sự cố, tổ chức có thể cấp thêm quyền cho đội điều tra, mở quyền truy cập log hoặc nới hạn chế để khôi phục dịch vụ. Những thay đổi này phải nằm trong review dù không do đối tượng tấn công tạo ra.

Mỗi quyền khẩn cấp cần trả lời:

- Được cấp cho ai, khi nào và bởi ai?
- Gắn với nhiệm vụ ứng cứu nào?
- Có thời hạn, điều kiện kết thúc và người thu hồi không?
- Quyền có được sử dụng đúng mục đích không?
- Sau khi hết nhu cầu, đã thu hồi và xác minh chưa?

Đối với tài khoản break-glass, cần kiểm tra lịch sử sử dụng, những người đã tiếp cận credential, tình trạng phiên còn mở và việc phục hồi kiểm soát thông thường. Nếu credential đã được tiết lộ trong quá trình sử dụng, xử lý thay thế theo chính sách phù hợp; không chỉ cất lại cùng giá trị vào vault.

JIT không tự bảo đảm một quyền đã hết hiệu lực đúng như mong đợi. Cần xác minh cả việc role activation kết thúc, quyền tại hệ thống đích được cập nhật và tác động đến phiên hoặc token đã phát hành. JEA cần được rà soát theo tập hành động thực tế được phép thực hiện, bao gồm các hành động có thể dẫn đến chạy lệnh hoặc sửa cấu hình ngoài phạm vi mong muốn.

Nếu một quyền tạm vẫn cần cho vận hành lâu dài, phải đi qua quy trình thiết kế và phê duyệt quyền chính thức. Không gia hạn vô hạn một ticket khẩn cấp.

## 9. Quyết định giữ, giảm hoặc thu hồi quyền

Quyết định phải gắn với nhu cầu công việc và rủi ro, không chỉ dựa trên việc “chưa thấy dùng sai”.

Các câu hỏi đánh giá gồm:

1. Quyền này phục vụ thao tác cụ thể nào?
2. Có thể giới hạn vào tài nguyên, môi trường hoặc tập hành động nhỏ hơn không?
3. Có thể cấp theo thời gian và phê duyệt thay cho thường trực không?
4. Người hoặc workload có cần biết giá trị secret không, hay có thể đi qua cơ chế broker?
5. Có thể tách quyền yêu cầu, phê duyệt, thực thi và quản trị kiểm soát không?
6. Biện pháp giám sát nào phát hiện việc sử dụng ngoài mục đích?

Ví dụ về quyết định:

| Phát hiện | Quyết định phù hợp với bối cảnh |
| --- | --- |
| Nhóm hỗ trợ có quyền quản trị production thường trực nhưng chỉ dùng khi xử lý ticket | Chuyển sang role giới hạn, kích hoạt có thời hạn và phê duyệt |
| Service account dùng chung cho nhiều môi trường | Tách danh tính và phạm vi quyền theo môi trường, chuyển consumer theo kế hoạch |
| Tài khoản có thể tự sửa chính sách JIT rồi kích hoạt role | Tách quyền quản trị policy khỏi quyền yêu cầu và phê duyệt |
| Khóa không có owner, không rõ consumer, có khả năng tiếp cận tài sản quan trọng | Điều tra phụ thuộc, áp dụng kiểm soát tạm thời và lên kế hoạch vô hiệu hóa có xác minh |
| Quyền khẩn cấp đã hết nhu cầu | Thu hồi, chấm dứt khả năng truy cập còn lại và lưu bằng chứng |

Ưu tiên xử lý dựa trên khả năng bị lợi dụng, tác động đến tài sản, phạm vi ảnh hưởng và mức độ kiểm soát hiện có. Một quyền có thể sửa trust policy hoặc tạo credential cho danh tính mạnh hơn thường cần được đánh giá khẩn hơn một quyền đọc log đã giới hạn tốt.

Thiếu log làm tăng độ không chắc chắn; không phải bằng chứng quyền an toàn. Có thể cần kiểm soát bù hoặc phạm vi review rộng hơn.

## 10. Xác minh bằng cả kiểm tra được phép và kiểm tra bị từ chối

Sau khi thực hiện thay đổi, cần kiểm tra trạng thái cấu hình lẫn hành vi có thể quan sát.

### 10.1. Kiểm tra dương tính

Kiểm tra dương tính chứng minh công việc hợp lệ vẫn thực hiện được:

- Workload lấy credential mới qua đường được phê duyệt.
- Quản trị viên kích hoạt role đúng phạm vi và đúng thời gian.
- Dịch vụ hoàn thành thao tác nghiệp vụ cần thiết.
- Log và bằng chứng phiên vẫn được thu thập.

### 10.2. Kiểm tra âm tính

Kiểm tra âm tính chứng minh đường bị thu hồi không còn cho phép truy cập:

- Danh tính không còn thực hiện được thao tác nằm ngoài phạm vi mới.
- Credential cũ bị từ chối qua phép thử đã được cho phép.
- Một đường truy cập trực tiếp không được phê duyệt bị chặn.
- Quyền hết hạn không tiếp tục cho phép tạo phiên mới.
- Tài khoản không thể tự cấp lại quyền đã bị thu hồi.

Phép thử âm tính phải được kiểm soát: xác định hệ thống đích, phương thức thử, thời điểm và người phê duyệt. Không thử credential bị lộ trên hệ thống ngoài phạm vi, không kích hoạt cơ chế khóa tài khoản ngoài dự kiến và không tái hiện hành vi phá hoại. Khi không thể kiểm tra trực tiếp, ghi rõ bằng chứng thay thế và giới hạn kết luận.

### 10.3. Một ma trận xác minh mẫu

| Thay đổi | Kiểm tra cấu hình | Kiểm tra hành vi | Điều kiện chưa được đóng |
| --- | --- | --- | --- |
| Thu hồi role quản trị | Role assignment đã mất tại đúng scope | Hành động quản trị cũ bị từ chối theo phép thử được duyệt | Token hoặc phiên cũ chưa được đánh giá |
| Rotation secret triển khai | Phiên bản mới được kích hoạt, bản cũ bị vô hiệu | Consumer mới chạy được; credential cũ bị từ chối | Chưa xác định đủ consumer |
| Chuyển sang JIT | Policy, người phê duyệt và TTL đúng | Kích hoạt hợp lệ thành công, yêu cầu sai bị chặn | Có đường tự phê duyệt hoặc truy cập ngoài gateway |
| Thu hồi quyền ứng cứu | Assignment và ngoại lệ đã được gỡ | Không còn khả năng sử dụng đường tạm | Thiếu log hoặc còn phiên chưa xử lý |

Một ảnh chụp màn hình “rotation successful” hoặc một ticket đã đóng chỉ là một phần bằng chứng. Kết luận hoàn tất phải dựa trên hiệu lực ở hệ thống đích và trạng thái sử dụng thực tế trong phạm vi kiểm tra.

Nếu cần thời gian để quyền lan truyền hoặc token hết hạn, ghi thời điểm dự kiến có hiệu lực, kiểm soát trong thời gian chờ và phép kiểm tra lại. Không coi thời gian chờ là đã hoàn thành.

## 11. Tình huống thực hành: tài khoản triển khai bị chiếm

### 11.1. Bối cảnh

Một doanh nghiệp phát hiện tài khoản `svc-deploy-prod` được dùng để tạo thay đổi ngoài lịch triển khai. Tài khoản có quyền cập nhật dịch vụ production, được pipeline lấy secret từ vault. Trong quá trình ứng cứu, đội vận hành cấp role quản trị tạm cho hai kỹ sư để phục hồi dịch vụ.

Containment ban đầu đã khóa đường lấy secret cũ và khôi phục workload. Tuy nhiên, trước khi đóng sự cố, nhóm cần biết còn đường truy cập nào chưa được xử lý.

### 11.2. Những phát hiện trong review

- Policy cũ cho phép tài khoản triển khai sửa cấu hình có ảnh hưởng đến quyền của workload.
- Một bản secret được sao chép vào cấu hình của một runner dự phòng.
- Có credential tạm được phát hành trước thời điểm containment; hiệu lực chưa được đánh giá đầy đủ.
- Một trong hai role ứng cứu không có thời hạn tự hết hiệu lực.
- Log checkout tại vault có sẵn, nhưng một số hành động tại hệ thống đích chưa được liên kết với mã phiên PAM.

Không gộp tất cả thành phát hiện “đã rotation secret”. Mỗi phát hiện cần một dòng riêng vì cách xử lý và điều kiện xác minh khác nhau.

### 11.3. Kế hoạch xử lý

| Phát hiện | Hành động | Bằng chứng đóng |
| --- | --- | --- |
| Quyền sửa cấu hình quá rộng | Tách quyền triển khai khỏi quyền thay đổi cơ chế cấp quyền | Policy mới, kiểm tra thao tác được phép và bị từ chối |
| Runner dự phòng giữ secret | Chuyển sang nhận credential qua kênh kiểm soát; vô hiệu credential cũ | Consumer được kiểm kê, credential cũ không còn được chấp nhận |
| Credential tạm còn hiệu lực | Đánh giá cơ chế thu hồi, chặn nguồn cấp lại và xử lý hiệu lực còn lại | Trạng thái thu hồi hoặc hết hiệu lực đã được xác minh |
| Role ứng cứu không hết hạn | Thu hồi role sau khi hết nhu cầu, xử lý phiên liên quan | Assignment bị gỡ, khả năng truy cập tạm đã kết thúc |
| Thiếu liên kết log | Bổ sung correlation và kiểm tra bằng một phiên được kiểm soát | Có thể đối chiếu principal, phiên, hành động và tài nguyên |

### 11.4. Kết luận đúng mức

Nếu một credential tạm chưa thể bị thu hồi trực tiếp và vẫn còn hiệu lực, review chưa thể kết luận mọi khả năng truy cập cũ đã chấm dứt. Nhóm cần nêu rõ thời gian hiệu lực còn lại, biện pháp hạn chế tại tài nguyên, giám sát bổ sung và người chịu trách nhiệm kiểm tra lại.

Nếu dịch vụ đã hoạt động nhưng kiểm tra credential cũ chưa hoàn tất, trạng thái phù hợp là “đã phục hồi dịch vụ, xác minh quyền còn mở”. Hai kết quả này không nên dùng thay cho nhau.

## 12. Phân công trách nhiệm và kiểm tra chéo

Một mô hình trách nhiệm rõ ràng giúp tránh tình trạng ai cũng nghĩ đội khác đã thu hồi quyền.

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Người chỉ huy hoặc điều phối sự cố | Chốt phạm vi, ưu tiên, quyết định khẩn cấp và điều kiện bàn giao |
| Đội IAM/PAM | Phân tích nguồn cấp quyền, role, vault, JIT/JEA và phiên được quản lý |
| Chủ hệ thống hoặc workload | Xác nhận nhu cầu hợp lệ, consumer và tác động vận hành |
| Đội điều tra/giám sát | Cung cấp timeline, hành vi quan sát được và khoảng trống bằng chứng |
| Người thực hiện thay đổi | Ghi nhận thay đổi, thời điểm và kết quả kỹ thuật |
| Người kiểm tra độc lập phù hợp | Đối chiếu bằng chứng và kết luận xác minh |
| Người có thẩm quyền chấp nhận rủi ro | Phê duyệt ngoại lệ, thời hạn và điều kiện kiểm soát |

Với thay đổi rủi ro cao, nên có người khác kiểm tra thay vì để người cấp quyền tự xác nhận mọi kết quả. Cách tổ chức cụ thể phụ thuộc quy mô doanh nghiệp, nhưng vẫn phải phân biệt trách nhiệm thực hiện và trách nhiệm chấp nhận rủi ro.

Một người có thể đảm nhiệm nhiều vai trò trong đội nhỏ; báo cáo cần minh bạch điều đó và nêu cách kiểm tra chéo thực tế.

## 13. Theo dõi rủi ro tồn dư và tiêu chí đóng review

Không phải mọi phát hiện đều sửa xong ngay sau sự cố. Một service account dùng chung có thể cần thời gian để tách consumer, hoặc một hệ thống cũ chưa hỗ trợ cơ chế thu hồi mong muốn. Điều quan trọng là không che giấu phần việc này dưới nhãn “đã hoàn tất”.

Ngoại lệ cần tối thiểu:

- Rủi ro cụ thể và tài sản bị ảnh hưởng.
- Lý do chưa xử lý triệt để.
- Biện pháp kiểm soát tạm thời và bằng chứng nó hoạt động.
- Người sở hữu hành động và người chấp nhận rủi ro.
- Ngày hết hạn, mốc kiểm tra lại và điều kiện mở lại sự cố.
- Kế hoạch loại bỏ ngoại lệ.

Review có thể được đóng theo quy trình tổ chức khi phạm vi đã được đối chiếu, các phát hiện được xử lý hoặc được bàn giao với phê duyệt thích hợp, và bằng chứng đủ hỗ trợ kết luận. Việc đóng review không có nghĩa mọi rủi ro tồn dư đã biến mất; báo cáo phải làm rõ trạng thái cuối cùng.

Các điều kiện nên được kiểm tra trước khi đóng:

1. Các danh tính và đường truy cập trong phạm vi đã được kiểm kê.
2. Baseline và giới hạn quan sát đã được ghi nhận.
3. Quyền không còn hợp lệ đã được xử lý, có xác minh tương ứng.
4. Credential, phiên và khả năng cấp lại đã được đánh giá riêng.
5. Quyền ứng cứu và ngoại lệ tạm đã được thu hồi hoặc chuyển sang quản lý chính thức.
6. Công việc hợp lệ vẫn hoạt động ở phạm vi quyền mới.
7. Khoảng trống còn lại có owner, thời hạn và quyết định chấp nhận phù hợp.
8. Bằng chứng được lưu đúng nơi và có thể truy xuất theo quyền được cấp.

Một phát hiện mới về khả năng truy cập đang bị lợi dụng cần được chuyển về ứng phó sự cố ngay, kể cả review trước đó đã đóng.

## 14. Mẫu biên bản review tối giản

Mẫu dưới đây là cấu trúc ghi nhận, không phải dữ liệu để nhập trực tiếp vào bất kỳ công cụ PAM nào:

```text
Mã sự cố:
Mục tiêu review:
Khoảng thời gian và múi giờ:
Danh tính/tài sản trong phạm vi:
Phần ngoài phạm vi và người chấp nhận:

Baseline được sử dụng:
Nguồn bằng chứng:
Giới hạn quan sát:

Phát hiện:
- Mã phát hiện:
- Principal ID / loại danh tính:
- Tài nguyên / môi trường:
- Nguồn cấp quyền / đường truy cập:
- Khả năng thực tế đã xác nhận:
- Quan hệ với sự cố:
- Quyết định và lý do:
- Owner / hạn xử lý:
- Thay đổi đã thực hiện:
- Bằng chứng trước và sau:
- Kiểm tra được phép:
- Kiểm tra bị từ chối:
- Credential / phiên / nguồn cấp lại còn tồn tại:
- Rủi ro tồn dư và phê duyệt:
- Trạng thái xác minh:

Kết luận review:
Công việc được bàn giao:
Ngày kiểm tra lại:
Người kiểm tra và người phê duyệt:
```

Không dán giá trị secret, token, dữ liệu phiên nhạy cảm hoặc toàn bộ log chưa được lọc vào biên bản. Tham chiếu bằng mã bằng chứng và cấp quyền truy cập theo nhu cầu công việc.

## 15. Đo hiệu quả và tránh kết luận sai từ số liệu

Số tài khoản bị khóa không phản ánh đầy đủ chất lượng review. Một tài khoản bị khóa nhưng còn đường cấp lại credential có thể vẫn là rủi ro lớn.

Những chỉ số hữu ích hơn gồm:

- Tỷ lệ danh tính và đường truy cập trong phạm vi đã được rà soát.
- Tỷ lệ phát hiện có owner, quyết định và bằng chứng xác minh.
- Thời gian từ phát hiện quyền không hợp lệ đến khi khả năng sử dụng thực tế bị chặn.
- Số quyền khẩn cấp quá hạn hoặc thiếu bằng chứng thu hồi.
- Số ngoại lệ tồn dư quá hạn.
- Tỷ lệ phép kiểm tra bị từ chối đạt kết quả mong đợi.
- Tỷ lệ phát hiện lặp lại trong những sự cố hoặc kỳ review tiếp theo.

Mỗi tỷ lệ cần có mẫu số rõ ràng và thời điểm đo. “100% đã review” chỉ có ý nghĩa nếu phạm vi đủ tin cậy; nếu còn tài sản chưa được kiểm kê, phải công khai giới hạn đó.

Có thể theo dõi thời gian xử lý theo mức rủi ro để tránh ưu tiên nhiều quyền nhỏ chỉ nhằm làm đẹp số lượng hoàn thành. Chỉ số hỗ trợ quyết định, không thay thế việc đọc bằng chứng của các đường truy cập có tác động cao.

## 16. Những sai sót thường gặp

| Sai sót | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ rà soát tài khoản con người | Bỏ sót service account, pipeline và danh tính workload | Kiểm kê cả danh tính máy và quan hệ tin cậy |
| Chỉ kiểm tra membership trực tiếp | Không thấy quyền qua nhóm lồng nhau hoặc role kế thừa | Phân tích quyền hiệu lực và đường nâng quyền |
| Coi rotation là kết thúc sự cố | Token, phiên hoặc nguồn cấp lại vẫn có thể hoạt động | Theo dõi credential, phiên và cơ chế cấp lại riêng |
| Dùng cấu hình gần thời điểm phát hiện làm baseline | Giữ lại quyền đối tượng tấn công đã thêm | Đối chiếu lịch sử và nguồn đáng tin cậy |
| Thu hồi hàng loạt mà không kiểm kê consumer | Gián đoạn dịch vụ, dẫn đến bật lại quyền quá rộng | Lập phụ thuộc và phương án phục hồi có kiểm soát |
| Dùng lại credential đã bị lộ để rollback | Tái mở đường truy cập cho đối tượng tấn công | Dùng credential mới hoặc đường dự phòng đáng tin cậy |
| Đóng ticket thay cho xác minh | Không chứng minh hiệu lực tại hệ thống đích | Yêu cầu bằng chứng cấu hình và hành vi |
| Bỏ quên quyền ứng cứu | Quyền tạm trở thành đặc quyền thường trực | Gắn thời hạn và review toàn bộ thay đổi khẩn cấp |
| Thiếu log nhưng vẫn kết luận không bị dùng | Biến khoảng trống bằng chứng thành khẳng định sai | Ghi độ không chắc chắn và áp dụng kiểm soát phù hợp |
| Ghi secret vào báo cáo | Tạo thêm nơi rò rỉ | Chỉ tham chiếu định danh và kho bằng chứng kiểm soát |

## 17. Bài tập tự kiểm tra

### Tình huống 1: quyền đã bị thu hồi nhưng phiên còn mở

Một quản trị viên bị xóa khỏi nhóm quản trị sau sự cố. Hệ thống IAM cho thấy membership đã cập nhật, nhưng chưa có bằng chứng về phiên trên máy chủ đích.

Hãy xác định thông tin còn thiếu, cơ chế cần kiểm tra và bằng chứng nào cho phép kết luận đường truy cập cũ đã chấm dứt. Trọng tâm là tách thay đổi quyền được cấp khỏi trạng thái phiên; không mặc định một thay đổi membership đã xử lý tất cả.

### Tình huống 2: service account không có owner

Một khóa của service account xuất hiện trong phạm vi bị ảnh hưởng. Không ai nhận quản lý, nhưng log cho thấy có hoạt động định kỳ phục vụ nghiệp vụ.

Hãy đề xuất cách kiểm kê consumer, đánh giá rủi ro trong thời gian điều tra và thay thế credential mà vẫn kiểm soát tác động vận hành. Chỉ rõ ai phải quyết định nếu cần thu hồi khẩn cấp.

### Tình huống 3: role khẩn cấp được gia hạn nhiều lần

Một role cấp cho đội ứng cứu được gia hạn liên tiếp vì nhóm vận hành thấy thuận tiện khi sử dụng.

Hãy phân biệt nhu cầu ứng cứu với nhu cầu vận hành lâu dài. Xác định điều kiện để thu hồi hoặc thiết kế role chính thức theo least privilege, JIT/JEA, phân tách phê duyệt và lưu bằng chứng.

### Tình huống 4: baseline có thể đã bị sửa

Snapshot cấu hình gần nhất có một trust policy rộng hơn tài liệu phê duyệt. Không đủ log để xác định ai đã sửa.

Hãy nêu nguồn đối chiếu bổ sung, cách ghi nhận độ không chắc chắn và quyết định nào cần người có thẩm quyền phê duyệt. Không chọn snapshot làm chuẩn chỉ vì nó là bản mới nhất.

## 18. Kiến thức cần ghi nhớ

Post-incident privilege review kết nối điều tra sự cố với quản trị quyền dài hạn. Công việc chỉ có giá trị khi xác định được khả năng truy cập thực tế, chuyển phát hiện thành thay đổi có owner và kiểm chứng hiệu lực ở nơi quyền được thực thi.

Với mỗi đường truy cập đặc quyền, hãy theo dõi đủ bốn yếu tố: nhu cầu hợp lệ, nguồn cấp quyền, credential hoặc phiên còn hiệu lực và bằng chứng xác minh. Rà soát cả quyền do đối tượng tấn công tạo ra lẫn quyền được cấp để ứng cứu.

Một kết luận tốt nói rõ điều gì đã được chứng minh, điều gì còn chưa biết và ai chịu trách nhiệm xử lý phần còn lại. Đó là cơ sở để thu hẹp đặc quyền, cải thiện JIT/JEA, kiểm soát vault và rotation, tăng khả năng giám sát phiên và tránh lặp lại cùng một đường xâm nhập.

