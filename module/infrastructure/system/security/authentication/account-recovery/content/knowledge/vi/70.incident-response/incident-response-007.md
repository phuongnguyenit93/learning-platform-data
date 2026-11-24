# Post incident recovery review — Rà soát phục hồi tài khoản sau sự cố

## 1. Mục tiêu: chứng minh đã lấy lại quyền kiểm soát và giảm nguy cơ tái diễn

Sau một sự cố khôi phục tài khoản, việc API hoạt động trở lại hoặc người dùng đăng nhập được chưa đủ để kết luận tài khoản đã an toàn. Một session cũ có thể còn quyền, một factor không được phép có thể vẫn tồn tại, hoặc một recovery grant chưa bị vô hiệu có thể mở lại đường truy cập.

Post incident recovery review là quá trình rà soát có cấu trúc nhằm xác định điều gì đã xảy ra, ai hoặc tài nguyên nào bị ảnh hưởng, các biện pháp phục hồi đã có hiệu lực đến đâu và những thay đổi nào cần được thực hiện để giảm nguy cơ lặp lại.

Trong phạm vi SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, review cần bao quát mật khẩu, MFA, passkey, thiết bị xác thực, bằng chứng danh tính, kênh recovery, token dùng một lần và session. Một review tốt nối các phần này thành cùng một lập luận về quyền kiểm soát tài khoản.

Bài học sử dụng mô hình, trạng thái và ví dụ do người viết đề xuất cho một hệ thống giả định. Tên trường, mốc thời gian và tiêu chí đóng phải được điều chỉnh theo chính sách và kiến trúc của sản phẩm.

Sau bài học, người học cần làm được:

- Phân biệt khôi phục dịch vụ, khôi phục quyền kiểm soát tài khoản và đóng sự cố.
- Tái dựng timeline từ bằng chứng đáng tin cậy, giữ rõ phần chưa biết.
- Đánh giá các đường duy trì quyền sau recovery.
- Phân tích nguyên nhân và điều kiện góp phần mà không dừng ở lỗi cá nhân.
- Đặt hành động cải tiến có owner, thời hạn và bằng chứng nghiệm thu.
- Kiểm tra hiệu quả cải tiến bằng test và quan sát sau triển khai.
- Chốt review mà không biến rủi ro chưa được xử lý thành trạng thái PASS.

[NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final) đặt hoạt động ứng phó sự cố trong quản lý rủi ro an ninh mạng, hướng tới cải thiện phát hiện, phản ứng và phục hồi. Bài học áp dụng bối cảnh đó vào đường khôi phục tài khoản; các biểu mẫu dưới đây không phải biểu mẫu bắt buộc do NIST quy định.

## 2. Phân biệt ba kết quả thường bị gộp

| Kết quả | Điều đã đạt | Điều chưa tự được chứng minh |
|---|---|---|
| Dịch vụ hoạt động trở lại | API, provider và giao diện đáp ứng được yêu cầu | Quyền của actor không được phép đã bị loại bỏ |
| Chủ tài khoản lấy lại quyền kiểm soát | Chủ thể được xác minh truy cập được, các đường truy cập trái phép liên quan được xử lý | Nguyên nhân hệ thống đã được khắc phục lâu dài |
| Sự cố được đóng theo chính sách | Gate vận hành, bằng chứng và rủi ro tồn dư đã được xử lý hoặc chấp nhận đúng thẩm quyền | Mọi việc cải tiến dài hạn đều đã hoàn thành |

Không nhất thiết chờ mọi công việc dài hạn hoàn tất mới đóng phần ứng phó vận hành. Tuy nhiên, việc đang mở, rủi ro còn lại, biện pháp bù đắp và người chịu trách nhiệm phải được thể hiện rõ. Không đánh dấu một kiểm soát chưa hiệu lực là PASS chỉ vì đã tạo ticket.

Review có thể bắt đầu khi sự cố đã tương đối ổn định, đồng thời tiếp tục thu thập bằng chứng về các phần chưa phục hồi. Nếu review phát hiện vẫn có quyền trái phép đang hoạt động, đó là thông tin cần quay lại luồng xử lý sự cố, không chỉ là một ghi chú cải tiến cho tương lai.

### 2.1. Bốn câu hỏi trung tâm

1. Những thay đổi credential và quyền nào thực sự đã xảy ra?
2. Ai được phép thực hiện chúng, và bằng chứng nào đã được dùng?
3. Sau biện pháp phục hồi, những quyền nào còn có thể hoạt động?
4. Thay đổi nào sẽ ngăn hoặc hạn chế cùng kiểu sự cố trong lần sau?

Các câu hỏi này giúp tránh review chỉ xoay quanh số lượng email reset hoặc thời gian deploy bản vá.

### 2.2. Review không nhằm tìm một người để quy trách nhiệm

[Google SRE — Postmortem Culture: Learning from Failure](https://sre.google/sre-book/postmortem-culture/) mô tả postmortem như phương tiện ghi nhận sự cố, tìm các nguyên nhân góp phần và tạo hành động phòng ngừa. Cách tiếp cận không quy lỗi cá nhân giúp tập trung vào điều kiện hệ thống và thông tin mà người xử lý thực sự có.

Trong review recovery, “nhân viên hỗ trợ phê duyệt nhầm” chưa phải lời giải thích đầy đủ. Cần hỏi giao diện hiển thị bằng chứng gì, quyền phê duyệt được kiểm tra ở đâu, hệ thống có ràng buộc tenant không và vì sao một quyết định sai có thể tạo tác động lớn.

Không quy lỗi không có nghĩa bỏ qua actor, quyền và hành động. Các dữ kiện đó vẫn cần được ghi chính xác để tái dựng diễn biến; điều cần tránh là thay phân tích cơ chế bằng một nhãn như “thiếu cẩn thận”.

## 3. Chốt phạm vi, tài liệu đầu vào và vai trò

### 3.1. Phạm vi review phải có ranh giới

Một phần phạm vi tối thiểu có thể ghi:

~~~yaml
review:
  incidentRef: synthetic-recovery-incident
  affectedService: account-recovery
  recoveryPaths:
    - password-reset
    - factor-rebind
  timeRange:
    startBasis: first-known-vulnerable-deployment
    endBasis: verified-containment-effective
  subjectScope:
    tenants: under-investigation
    accounts: evidence-based
  excludedAreas:
    - unrelated-authentication-changes
  unresolvedQuestions:
    - whether-all-resources-enforced-session-revocation
~~~

Đây là cấu trúc tài liệu minh họa, không phải thay đổi schema metadata của module.

Nếu sự cố liên quan shared component, cần xác định các endpoint và loại recovery khác dùng cùng thành phần. Một bản vá cho endpoint được báo lỗi chưa chứng minh các đường gọi khác an toàn.

Khoảng thời gian cần phân biệt mốc “bản có lỗi được triển khai”, “hành vi bất thường đầu tiên được quan sát” và “mốc containment đã có hiệu lực”. Các mốc này có thể khác nhau đáng kể.

### 3.2. Đầu vào cần có

| Nhóm đầu vào | Dùng để trả lời |
|---|---|
| Snapshot policy và cấu hình có hiệu lực | Khi đó thao tác nào được phép? |
| Event từ authority credential | Password/factor đã thực sự thay đổi chưa? |
| Grant và recovery transaction | Bằng chứng, scope, trạng thái và vòng đời là gì? |
| Event session và resource | Quyền cũ hoặc quyền mới đã được dùng ở đâu? |
| Thao tác hỗ trợ | Actor nào đã xem, phê duyệt, hủy hoặc ghi đè? |
| Timeline triển khai và cấu hình | Thay đổi hệ thống nào có thể liên quan? |
| Kết quả containment và verification | Biện pháp nào đã có hiệu lực thực tế? |
| Phản hồi chủ tài khoản đã được xác minh | Thao tác nào được hoặc không được chủ thể thừa nhận? |
| Chất lượng telemetry | Có khoảng mù, event đến muộn hoặc dữ liệu thiếu không? |

Không cần đưa mọi dữ liệu thô vào bản review. Lưu reference tới kho bằng chứng được kiểm soát và chỉ trình bày những trường cần cho lập luận.

### 3.3. Người tham gia và quyền quyết định

Review thường cần đại diện recovery/authentication, session hoặc resource liên quan, security/incident response, vận hành và hỗ trợ khách hàng. Nếu provider hoặc quy trình xác minh danh tính góp phần, bổ sung owner phù hợp.

Mỗi phần cần một owner rõ:

- Người điều phối giữ phạm vi và câu hỏi cần giải quyết.
- Người quản lý bằng chứng giữ reference, nguồn và độ tin cậy.
- Owner kỹ thuật giải thích cơ chế cùng kết quả kiểm tra.
- Owner phục hồi account xác nhận từng đường quyền liên quan.
- Người có thẩm quyền quyết định rủi ro tồn dư theo chính sách tổ chức.

Một người có thể giữ nhiều vai trong nhóm nhỏ. Điều cần giữ là trách nhiệm không bị hòa tan thành “team sẽ xử lý”.

## 4. Xây dựng timeline bằng bằng chứng, không bằng trí nhớ đơn lẻ

### 4.1. Ghi riêng sự kiện, quyết định và tác động

Một timeline hữu ích có các cột:

| Mốc | Dữ kiện hoặc quyết định | Nguồn | Độ chắc chắn | Ý nghĩa |
|---|---|---|---|---|
| T0 | Triển khai phiên bản có đường cấp quyền mới | Deployment record | Đã xác nhận | Bắt đầu cửa sổ có khả năng bị ảnh hưởng |
| T1 | Mutation credential đầu tiên được liên kết với finding | Credential authority | Đã xác nhận | Có tác động thực |
| T2 | Nhóm trực nhận cảnh báo | Alert system | Đã xác nhận | Bắt đầu phản ứng vận hành |
| T3 | Yêu cầu revoke session được gửi | Command/audit record | Đã xác nhận yêu cầu | Chưa chứng minh resource đã chặn |
| T4 | Resource từ chối session liên quan | Kết quả kiểm tra và resource audit | Đã xác nhận tại resource được kiểm tra | Bằng chứng hiệu lực |
| T5 | Chủ tài khoản đăng nhập lại đúng điều kiện | Authentication authority | Đã xác nhận | Một phần bằng chứng phục hồi quyền truy cập |

Một event “đã gửi revoke” và một lần gọi resource bị từ chối không có cùng ý nghĩa. Review cần giữ hai mốc để đánh giá khoảng thời gian quyền cũ còn sử dụng được.

### 4.2. Thời gian xảy ra khác thời gian nhận event

Giữ ít nhất thời điểm tại nguồn và thời điểm collector nhận. Nếu log phê duyệt đến sau log thay factor, không được tự kết luận factor đã đổi trước phê duyệt.

Khi cần xác định thứ tự quan trọng, ưu tiên thông tin version, sequence hoặc thứ tự commit tại authority phù hợp. Hai timestamp từ hai máy có thể không đủ chính xác để chứng minh một race.

Dữ kiện chưa đủ cần ghi rõ: “chưa xác định thứ tự hủy và commit”, thay vì ép thành một timeline sạch đẹp nhưng sai.

### 4.3. Tách ba lớp nhận định

~~~text
Dữ kiện:
  Hai business mutation độc lập đã commit với cùng một grant.

Giải thích đang kiểm tra:
  Có thể hai request cùng vượt qua kiểm tra chưa sử dụng.

Kết luận sau tái hiện:
  Trên phiên bản X, hai transaction cùng đọc trạng thái chưa dùng;
  bước thay credential và tiêu thụ grant không cùng ranh giới nguyên tử.
~~~

Không nâng giả thuyết thành kết luận chỉ vì nó phù hợp trực giác. Nếu chưa tái hiện được hoặc không còn đủ dữ liệu, giữ mức chắc chắn tương ứng cùng phương án giảm rủi ro.

### 4.4. Bảo toàn bằng chứng có thể kiểm chứng

Mỗi kết luận quan trọng nên có reference tới nguồn, khoảng thời gian và phương thức lấy dữ liệu. Giữ bản gốc hoặc snapshot theo cơ chế quản lý bằng chứng của tổ chức, cùng dấu hiệu kiểm tra tính toàn vẹn khi phù hợp.

Một checksum có thể giúp phát hiện thay đổi nội dung bản chụp; nó không tự chứng minh nguồn ban đầu đúng, người tạo bản chụp có thẩm quyền hoặc dữ liệu chưa bị sửa trước lúc chụp.

Không đưa password, recovery token, seed TOTP, private key hoặc giấy tờ xác minh vào tài liệu chia sẻ rộng. Dùng định danh giả hoặc reference để người được cấp quyền có thể đối chiếu.

## 5. Đánh giá phạm vi ảnh hưởng một cách có thể kiểm toán

### 5.1. Phân biệt có nguy cơ, có tác động và bị sử dụng trái phép

| Nhóm | Ý nghĩa | Bằng chứng cần |
|---|---|---|
| Có thể chịu ảnh hưởng | Đã đi qua phiên bản hoặc policy có điểm yếu | Cấu hình, deployment, thời gian và đường gọi |
| Có tác động được xác nhận | Credential, factor hoặc quyền đã đổi qua đường liên quan | Mutation hoặc authority record |
| Có sử dụng trái phép được xác nhận | Có bằng chứng đủ về thao tác không được phép | Liên kết actor, quyền, bằng chứng xác minh và hành vi |
| Chưa xác định | Dữ liệu còn thiếu hoặc liên kết chưa đủ | Danh sách khoảng mù và bước kiểm tra tiếp |

Không dùng số grant có nguy cơ để báo số account bị chiếm. Một account có thể có nhiều grant; một grant có thể chưa từng được sử dụng.

Tương tự, một credential mutation thành công không tự chứng minh actor độc hại. Cần đối chiếu thao tác được phép, chủ thể thực hiện và bằng chứng độc lập.

### 5.2. Cách lập cohort ảnh hưởng

Một cách phân tích:

1. Xác định các phiên bản, cấu hình và khoảng thời gian có điểm yếu.
2. Tìm grant, transaction hoặc action thực sự đi qua đường đó.
3. Liên kết tới mutation đã commit bằng định danh nghiệp vụ.
4. Đối chiếu account và tenant từ nguồn authority.
5. Theo dõi session, factor hoặc credential phát sinh sau mutation.
6. Đánh dấu riêng những hồ sơ thiếu dữ liệu hoặc không đủ kết luận.

Không gom account theo email hiển thị nếu hệ thống có tenant. Không đếm lại cùng mutation chỉ vì event được broker giao nhiều lần.

Khi trình bày số liệu, ghi đơn vị rõ ràng: số grant, số transaction, số mutation hay số account duy nhất. Nếu mẫu có dữ liệu thiếu, nêu độ bao phủ và phạm vi của kết luận.

### 5.3. Đừng mở rộng quá mức một điều đã quan sát

Nếu chỉ xác nhận được token recovery dùng lại để đổi password, chưa thể khẳng định dữ liệu nghiệp vụ đã bị lấy. Muốn đánh giá điều đó, cần quan sát quyền truy cập và hoạt động tài nguyên liên quan.

Ngược lại, không thấy log truy cập dữ liệu cũng không chứng minh chưa có truy cập nếu resource không ghi đủ hoặc collector có khoảng mù.

Một câu diễn đạt tốt là: “Đã xác nhận hai mutation ngoài hợp đồng; chưa đủ telemetry để kết luận về toàn bộ hoạt động sau đăng nhập trong khoảng X.” Câu này giữ được cả dữ kiện lẫn giới hạn.

## 6. Rà soát việc phục hồi quyền kiểm soát tài khoản

[OWASP Forgot Password Cheat Sheet — Account Recovery After Suspected Compromise](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise) nhấn mạnh rằng reset password có thể chưa đủ khi actor còn session hoặc đã thay thông tin recovery và MFA. Review cần đối chiếu các đường quyền liên quan, không chỉ xác nhận password mới hoạt động.

### 6.1. Ma trận tài sản và bằng chứng

| Tài sản hoặc đường quyền | Câu hỏi review | Bằng chứng hiệu lực |
|---|---|---|
| Password | Credential được thay theo đúng bằng chứng và policy chưa? | Xác nhận từ authority và đăng nhập đúng điều kiện |
| MFA | Có factor được thêm/xóa trái phép hoặc factor đã xác định bị lộ không? | Đối chiếu mutation, chủ thể đã xác minh và trạng thái factor |
| Passkey | Credential mới thuộc account nào, được cấp bởi quyền nào? | Bản ghi đăng ký, grant liên quan và kết quả kiểm tra xác thực phù hợp |
| Recovery channel | Địa chỉ nào còn an toàn và đã được xác minh? | Quá trình xác minh độc lập, lịch sử thay đổi và quyết định được ghi nhận |
| Recovery code | Bộ mã cũ còn có thể mở lại quyền không? | Trạng thái vòng đời và kiểm tra qua môi trường/quy trình xác minh được phép |
| Grant/token chưa dùng | Những quyền đang lưu hành có cần vô hiệu theo phạm vi sự cố không? | Kết quả tại điểm kiểm tra grant, không chỉ lệnh đã gửi |
| Session/access token | Resource còn chấp nhận phiên phải thu hồi không? | Request kiểm tra tới resource trong phạm vi cần bảo vệ |
| Refresh token | Có thể tái cấp session sau quyết định thu hồi không? | Kết quả refresh và khả năng dùng credential được cấp tiếp |
| API key hoặc credential lâu dài | Có đường duy trì quyền được tạo sau recovery không? | Audit tạo/sử dụng và trạng thái hiệu lực thực tế |
| Quyền hỗ trợ tạm thời | Quyền khẩn cấp hoặc quyền ghi đè đã kết thúc chưa? | Kiểm tra authorization và hết hạn/thu hồi quyền theo policy |

Ma trận là danh sách câu hỏi theo rủi ro, không phải yêu cầu tự động xóa toàn bộ tài sản. Review phải xác định tài sản nào liên quan, hành động nào đã được phép và bằng chứng nào đủ cho kết luận.

Không thử credential nghi ngờ trực tiếp một cách tùy tiện chỉ để hoàn thành checklist. Thiết kế verification phải nằm trong quy trình kiểm tra được phép và tránh tạo thêm tác động vào tài khoản thật.

### 6.2. Xác nhận chủ thể qua bằng chứng phù hợp

Nếu kênh email đang bị nghi chiếm, việc gửi một liên kết tới chính email đó không đủ chứng minh đã trả quyền cho đúng chủ thể.

Review cần biết:

- Bằng chứng nào được dùng để xác minh chủ tài khoản?
- Bằng chứng đó có độc lập với đường đang bị nghi chiếm không?
- Nhân viên hoặc dịch vụ nào đã quyết định chấp nhận?
- Quyết định có đáp ứng yêu cầu của loại account và action không?
- Có thông tin recovery mới thêm nào bị tin cậy quá sớm không?

Không mặc định kênh cũ là an toàn rồi tự khôi phục lại. Người dùng có thể đã đổi vì kênh cũ bị mất hoặc bị chiếm. Phải đối chiếu lại trạng thái đáng tin theo tình huống cụ thể.

### 6.3. Phục hồi passkey không phải khôi phục private key bị mất

Đối với passkey, review thường kiểm tra việc đăng ký credential thay thế và xử lý credential liên quan. Không viết rằng server “khôi phục private key” nếu kiến trúc không thực hiện việc đó.

Cần xem grant đăng ký có đúng account, tenant, purpose và trạng thái không; credential thay thế có được gắn qua bước xác minh giao thức và policy phù hợp không. Nếu chỉ có log “register success” ở controller mà verifier hoặc authority không được đối chiếu, bằng chứng còn thiếu.

Không phải mọi passkey cũ đều phải xóa chỉ vì mất một thiết bị. Phân biệt credential đã được xác định bị chiếm với credential còn an toàn theo đánh giá và chính sách của sản phẩm.

### 6.4. Session revocation phải được kiểm tra tại nơi thực thi

Một review dễ bỏ sót việc UI đã đăng xuất nhưng API vẫn chấp nhận session. Cần kiểm tra các loại client và resource trong phạm vi rủi ro, kể cả refresh path và node có cache khác.

Với access token tự chứa, vô hiệu refresh token không tự làm access token hết hiệu lực ngay. Review phải dựa vào cơ chế thực tế: kiểm tra version, introspection, danh sách thu hồi, TTL hoặc cơ chế khác được triển khai.

Bằng chứng nên ghi:

~~~text
Đối tượng:
  Loại session và resource được kiểm tra.

Mốc:
  Lúc yêu cầu thu hồi, lúc quyết định có hiệu lực,
  lúc thực hiện verification.

Kết quả:
  Session cũ được resource chấp nhận hay bị từ chối.

Độ bao phủ:
  Client/resource đã kiểm tra và những phần chưa được kiểm tra.
~~~

Nếu chỉ kiểm tra một resource đại diện, ghi đúng phạm vi đó. Không tự biến một mẫu đại diện thành bằng chứng mọi resource đều thực thi cùng cơ chế, trừ khi có cơ sở kiến trúc và kiểm tra hỗ trợ.

### 6.5. Giữ cả bằng chứng hoạt động hợp lệ

Cùng lúc chứng minh quyền cũ bị chặn, phải kiểm tra chủ thể hợp lệ vẫn hoàn tất recovery và đăng nhập theo điều kiện hiện hành.

Một hệ thống từ chối mọi người có thể làm nhiều negative test đạt. Vì vậy, verification nên có cặp:

- Credential/grant không còn được phép bị từ chối.
- Credential và bằng chứng hợp lệ cho đúng account vẫn hoạt động.

Tương tự, một bản vá chống replay không nên khiến mọi trường hợp client retry hợp lệ đều tạo hồ sơ mới hoặc mất khả năng hoàn tất tác vụ đã commit.

## 7. Phân tích nguyên nhân theo chuỗi kiểm soát

### 7.1. Tách trigger, cơ chế lỗi và điều kiện góp phần

| Thành phần phân tích | Ví dụ |
|---|---|
| Trigger | Hai request hoàn tất cùng grant đến gần nhau |
| Cơ chế lỗi | Cùng đọc trạng thái chưa dùng rồi cập nhật riêng, tạo hai mutation |
| Điều kiện góp phần | Một endpoint dùng repository path bỏ qua phép consume nguyên tử |
| Khoảng trống phòng ngừa | Test chỉ chạy tuần tự và dùng mock |
| Khoảng trống phát hiện | Giám sát đếm event lỗi, không đối chiếu mutation thành công |
| Điều kiện làm tác động lớn hơn | Grant còn tồn tại lâu, session hoặc credential mới không nằm trong phạm vi xử lý ban đầu |
| Điều kiện làm phục hồi chậm | Không có danh sách account/grant bị tác động theo định danh nghiệp vụ |

Trigger không phải toàn bộ nguyên nhân. Một hệ thống đúng vẫn cần xử lý hai request đồng thời hoặc client retry mà không phá hợp đồng dùng một lần.

### 7.2. Đừng dừng ở “thiếu test”

Thiếu test giải thích vì sao lỗi không bị phát hiện ở một thời điểm, nhưng chưa giải thích vì sao lỗi có thể tạo quyền trái phép.

Một phân tích sâu hơn hỏi:

1. Bất biến nào đáng lẽ phải được giữ?
2. Thành phần nào có đủ dữ liệu và quyền để giữ bất biến đó?
3. Kiểm tra nào được thực hiện, và có cùng ranh giới với tác động không?
4. Đường gọi nào có thể đi vòng qua kiểm tra?
5. Vì sao thiết kế, review, test hoặc giám sát chưa nhận ra?
6. Những điều kiện nào khiến phạm vi hoặc thời gian ảnh hưởng tăng?

Có thể dùng sơ đồ nguyên nhân để tránh ép mọi điều vào một chuỗi tuyến tính:

~~~mermaid
flowchart TD
    A[Consume grant khong nguyen tu] --> X[Hai mutation cung duoc commit]
    B[Endpoint dung duong ghi rieng] --> X
    C[Test khong tao canh tranh] --> D[Loi khong bi chan truoc release]
    D --> X
    E[Chi theo doi verification failure] --> F[Phat hien cham]
    X --> G[Credential va quyen can ra soat]
    F --> G
~~~

Sơ đồ mô tả quan hệ giả định cần được chứng minh bằng code, cấu hình, tái hiện hoặc bằng chứng phù hợp. Nó không thay thế việc xác minh từng cạnh.

### 7.3. Phân tích quyết định trong bối cảnh lúc đó

Đối với thao tác hỗ trợ, ghi những gì nhân viên thấy và quyền họ thực sự có ở thời điểm ra quyết định. Đừng lấy dữ kiện chỉ xuất hiện sau sự cố rồi cho rằng họ đáng lẽ phải biết từ đầu.

Ví dụ, nếu UI chỉ hiển thị “evidence verified” nhưng không hiển thị bằng chứng đã thuộc phiên bản cũ, action item có thể cần sửa cả mô hình trạng thái và cách trình bày quyết định. Một nhắc nhở “đọc kỹ hơn” không xử lý được dữ kiện bị thiếu.

### 7.4. Phân biệt biện pháp tạm và sửa nguyên nhân

Tắt nhánh recovery có thể chặn đường lỗi nhưng làm giảm khả năng lấy lại account. Thêm rate limit có thể giảm lưu lượng nhưng không làm grant dùng một lần trở nên nguyên tử.

Trong review, mỗi biện pháp nên được gắn loại:

- Containment: giảm ngay khả năng tiếp tục gây tác động.
- Remediation: xử lý trạng thái hoặc quyền bị ảnh hưởng.
- Prevention: sửa cơ chế khiến cùng kiểu lỗi tái diễn.
- Detection: rút ngắn thời gian nhận biết hoặc xác định phạm vi.
- Recovery improvement: làm xác minh và phục hồi quyền kiểm soát hiệu quả hơn.

Một công việc có thể phục vụ nhiều mục tiêu, nhưng cần nêu mục tiêu chính và bằng chứng tương ứng.

## 8. Đánh giá hiệu quả ứng phó và phục hồi

### 8.1. Hỏi điều gì đã giúp, điều gì đã cản trở

Review cần giữ cả yếu tố hoạt động tốt: một audit source có đủ mutation ID, một kill switch chỉ tác động đúng nhánh hoặc một playbook giúp xác minh account mà không tin kênh bị chiếm.

Đối với điểm chưa tốt, mô tả ảnh hưởng cụ thể. “Quá trình chậm” kém hữu ích hơn “mất thời gian xác định resource nào thực thi security version vì inventory không đầy đủ”.

Các câu hỏi hữu ích:

- Cảnh báo xuất hiện trước hay sau phản ánh của người dùng?
- Người trực có phân biệt được request và mutation đã commit không?
- Có xác định được cohort ảnh hưởng mà không xuất secret không?
- Lệnh revoke có kết quả hiệu lực và cơ chế kiểm tra lại không?
- Có job hoặc callback cũ tiếp tục chạy sau containment không?
- Có biện pháp nào gây mất quyền truy cập cho người dùng hợp lệ ngoài phạm vi không?
- Có quyền khẩn cấp hoặc bypass tạm thời chưa được thu hồi không?

### 8.2. Đừng dùng thời gian phản hồi làm thước đo duy nhất

Một nhóm có thể phản hồi rất nhanh nhưng chỉ đổi password và bỏ sót refresh token. Một nhóm khác mất thêm thời gian đối chiếu authority nhưng xác định đúng các credential lâu dài.

Cần xem thời gian cùng với mức độ hoàn chỉnh của quyền đã xử lý, độ bao phủ verification, tác động tới người dùng và chất lượng kết luận.

Nếu dữ liệu không cho biết thời điểm xâm nhập đầu tiên, không báo một con số chính xác mang tên “thời gian tồn tại của actor”. Ghi đúng mốc bắt đầu mà số liệu thực sự sử dụng.

### 8.3. Rà soát thông báo và trải nghiệm người dùng

Đối chiếu người nào cần nhận thông báo theo policy, kênh nào được đánh giá còn an toàn và nội dung hướng dẫn có giúp họ thực hiện bước cần thiết không.

Không coi “provider accepted” là “người dùng đã nhận và hiểu”. Các trạng thái tiếp nhận, gửi, giao, mở và phản hồi có ý nghĩa khác nhau, và không phải provider nào cũng cung cấp mọi trạng thái.

Một thông báo không nên buộc người dùng tin vào kênh đang bị nghi chiếm hoặc tiết lộ secret trong nội dung. Review cũng nên xem khả năng tiếp cận, ngôn ngữ và bước hỗ trợ khi người dùng đã mất thiết bị duy nhất.

## 9. Chuyển bài học thành action item có thể nghiệm thu

### 9.1. Mỗi việc cần đầu ra quan sát được

Một action item tối thiểu nên có:

~~~yaml
action:
  id: RECOVERY-ACTION-01
  objective: enforce-single-mutation-per-grant
  ownerRole: credential-service-owner
  category: PREVENTION
  priorityBasis: confirmed-control-violation
  dueAt: agreed-target-date
  dependencies:
    - transactional-grant-repository
  acceptance:
    - concurrent-completion-cannot-create-two-mutations
    - credential-change-and-consume-remain-consistent-on-failure
    - authorized-recovery-still-completes
  verification:
    method: database-integration-and-api-tests
    evidenceRef: pending
  status: PLANNED
  residualRisk:
    temporaryControl: affected-path-restricted
    reviewOwner: incident-risk-owner
~~~

Các giá trị là ví dụ trong bài học. Owner thực tế phải là cá nhân hoặc đơn vị có trách nhiệm rõ theo hệ thống quản lý công việc; một nhãn chung không đủ nếu không ai có nghĩa vụ hoàn thành.

Không ghi status=DONE chỉ vì code đã merge. Acceptance cần được kiểm tra trên đường thực hiện phù hợp, và deployment phải có bằng chứng nếu mục tiêu yêu cầu hiệu lực trong môi trường đang phục vụ.

### 9.2. So sánh action item yếu và mạnh

| Việc quá chung | Cách viết có thể nghiệm thu |
|---|---|
| Cải thiện bảo mật token | Ràng buộc consume với tenant, account, purpose, trạng thái và mutation trong ranh giới nhất quán được chọn |
| Thêm test | Tạo case hai transaction độc lập cùng dùng grant một lần; chỉ một mutation được commit |
| Cải thiện logging | Phát event mutation từ authority với grantRef và businessMutationRef, có kiểm tra thiếu hoặc gửi trùng |
| Đào tạo hỗ trợ viên | Thay bước quyết định và dữ kiện hiển thị để bằng chứng cũ không được chấp nhận như bằng chứng hiện hành; diễn tập quy trình mới |
| Thu hồi mọi session | Xác định chính xác cohort và resource; kiểm chứng hiệu lực thu hồi trong giới hạn policy |
| Giám sát thêm | Phát hiện hai mutation độc lập từ grant một lần mà không đếm event duplicate |

Đào tạo có thể hữu ích nhưng cần đi cùng thay đổi điều kiện hệ thống khi nguyên nhân nằm ở quyền, trạng thái hoặc dữ liệu thiếu.

### 9.3. Ưu tiên theo đường quyền và rủi ro tồn dư

Thường cần xử lý trước đường đang cho phép tạo quyền trái phép hoặc giữ quyền sau containment. Tiếp theo là các việc giúp xác định ảnh hưởng và giảm thời gian phản ứng, rồi cải tiến dài hạn tùy rủi ro.

Không phải mọi sự cố đều cần thay provider, viết lại toàn bộ authentication hoặc rotate mọi key. Mỗi hành động phải gắn với cơ chế lỗi và phạm vi bằng chứng. Một thay đổi quá rộng có thể tạo thêm tác động mà không xử lý được nguyên nhân.

Nếu chưa sửa triệt để, ghi rõ biện pháp bù đắp, giới hạn của nó, owner rủi ro và mốc xem lại. “Đã có workaround” chưa phải bằng chứng rủi ro đã hết.

## 10. Kiểm chứng bản sửa và những hệ quả ngoài ý muốn

### 10.1. Tái hiện trước, kiểm tra sau

Một regression test có giá trị nên thất bại trên bản có lỗi và đạt trên bản sửa vì đúng bất biến đã được bảo vệ.

Với lỗi dùng grant một lần, cần kiểm tra:

1. Một request hợp lệ thay credential đúng account.
2. Request thứ hai không tạo mutation mới.
3. Hai request đồng thời không cùng thắng.
4. Lỗi trước commit không để credential và grant mất nhất quán.
5. Retry sau khi mất response không tạo tác động thứ hai.
6. Grant sai account, tenant hoặc purpose vẫn bị chặn.
7. Recovery hợp lệ vẫn hoạt động sau bản sửa.

Không yêu cầu mọi request lặp đều trả lỗi. Một cơ chế idempotency có thể trả lại kết quả thành công đã lưu, miễn không tạo mutation mới và không nhận payload khác ngoài hợp đồng.

### 10.2. Chọn tầng kiểm tra bắt được cơ chế lỗi

| Mục tiêu | Tầng kiểm tra phù hợp |
|---|---|
| Policy scope và purpose | Unit/domain và API |
| Consume nguyên tử, rollback | Database integration |
| Principal recovery không có quyền nghiệp vụ | API với middleware thật |
| Session cũ bị chặn | Resource và cơ chế session thực |
| Callback/job cũ không mở lại quyền | Tích hợp bất đồng bộ |
| Chủ account hoàn tất recovery đúng điều kiện | Luồng xuyên hệ thống đại diện |
| Detector phân biệt mutation với event duplicate | Replay dữ liệu có gắn nhãn |

Mock có thể giúp test nhanh phần điều phối, nhưng không chứng minh row lock, transaction hay resource revocation hoạt động đúng.

### 10.3. Kiểm tra các đường dùng chung

Sau khi sửa endpoint được phát hiện, tìm các đường sử dụng cùng policy, repository hoặc adapter theo phạm vi review. Ví dụ: reset password, factor rebind, recovery code, hỗ trợ thủ công, API phiên bản cũ và worker.

Chỉ kết luận đường nào đã được kiểm tra hoặc đã được chứng minh dùng chung cơ chế bảo vệ phù hợp. Ghi phần chưa kiểm tra thành rủi ro hoặc việc tiếp theo.

### 10.4. Quan sát sau triển khai

Theo dõi cả kết quả bảo mật và khả năng sử dụng: mutation bất thường, grant bị từ chối đúng lý do, completion rate, thời gian recovery và số yêu cầu hỗ trợ phát sinh.

Không coi một khoảng thời gian không có cảnh báo là bằng chứng duy nhất. Cần biết nguồn telemetry còn đầy đủ, detector đang hoạt động và bản sửa đã tới mọi node hoặc resource cần thiết.

Một canary hoặc rollout theo giai đoạn có thể giới hạn tác động, nhưng tiêu chí chuyển giai đoạn phải dựa trên giả định và rủi ro của thay đổi thực tế.

## 11. Ví dụ xuyên suốt: grant một lần tạo hai thay đổi credential

Ví dụ sau hoàn toàn giả lập. Tất cả thời gian trong timeline dùng UTC.

### 11.1. Diễn biến được xác nhận

| Thời điểm | Sự kiện |
|---|---|
| 09:00 | Phiên bản mới có một đường ghi credential không dùng repository consume chuẩn |
| 09:24 | Hai mutation độc lập được commit cho cùng một grant chỉ cấp một mutation |
| 09:27 | Detector tạo finding sau khi đối chiếu authority |
| 09:32 | Nhóm ứng phó hạn chế đường ghi liên quan |
| 09:37 | Tất cả instance phục vụ đường đó xác nhận cấu hình containment |
| 09:45 | Lệnh thu hồi các quyền liên quan trong cohort đã xác định được phát hành |
| 09:49 | Verification đầu tiên chứng minh resource được kiểm tra từ chối session cũ |
| 10:20 | Chủ account trong mẫu verification hoàn tất xác minh và đăng nhập lại đúng policy |
| 11:00 | Bản sửa được kiểm tra trong môi trường tích hợp; chưa đồng nghĩa đã hiệu lực production |

Review không dùng 09:32 làm mốc containment hoàn toàn nếu các instance khác còn phục vụ. Cũng không dùng 09:45 làm mốc mọi session đã mất quyền khi mới chỉ phát hành lệnh.

Mốc 10:20 chỉ chứng minh tài khoản trong mẫu đó phục hồi thành công. Muốn báo toàn cohort đã được xử lý, cần bằng chứng theo phạm vi tương ứng.

### 11.2. Phân loại phạm vi

Điều tra tìm được 1.200 grant đi qua phiên bản hoặc cấu hình có nguy cơ trong cửa sổ liên quan. Đây là số grant, không phải số account bị chiếm.

Trong số đó, hai grant có mỗi grant hai mutation độc lập, đã được credential authority xác nhận. Review cần tiếp tục xác định các account duy nhất, ai đã thực hiện và những quyền nào phát sinh.

Nếu một chủ account phản đối thao tác nhưng việc xác minh phản đối chưa hoàn tất, báo đúng trạng thái đang điều tra. Không coi phản đối chưa xác minh là bằng chứng cuối cùng, cũng không bỏ qua nó vì log có một lần token được chấp nhận.

### 11.3. Nguyên nhân được chứng minh

Tái hiện trên bản có lỗi cho thấy:

1. Hai transaction cùng đọc grant chưa sử dụng.
2. Mỗi transaction thực hiện thay credential qua một đường ghi riêng.
3. Bước đánh dấu grant đã dùng không cùng ranh giới nguyên tử với thay đổi.
4. Test trước release chỉ dùng các request tuần tự.
5. Detector ban đầu theo dõi verification failure, thiếu kiểm tra cardinality của mutation thành công.

Kết luận chính là một bất biến nghiệp vụ không được thực thi nguyên tử trên mọi đường ghi. “Hai request đến quá gần” chỉ là trigger. “Thiếu test” là một khoảng trống phòng ngừa, không phải toàn bộ cơ chế lỗi.

### 11.4. Kế hoạch hành động và bằng chứng

| Hành động | Mục tiêu | Bằng chứng nghiệm thu |
|---|---|---|
| Gom thay credential và consume grant vào cơ chế nhất quán được chọn | Chặn hai mutation từ cùng quyền một lần | Test cạnh tranh và rollback trên database đại diện |
| Kiểm kê các đường ghi dùng cùng grant | Chặn đường đi vòng | Danh mục endpoint/worker và kết quả đối chiếu |
| Đối chiếu mutation từ authority theo grant | Phát hiện vi phạm đã commit | Replay có duplicate và case sát ranh giới thời gian |
| Bổ sung inventory nơi thực thi session revocation | Rút ngắn phục hồi quyền kiểm soát | Danh sách resource cùng verification được ghi nhận |
| Sửa playbook về cohort và đơn vị đếm | Giảm báo cáo sai phạm vi | Diễn tập phân biệt grant, mutation và account |

Việc đầu tiên có thể hoàn thành trước những việc còn lại. Review phải giữ trạng thái riêng cho từng việc và nêu biện pháp bù đắp nếu một khoảng trống còn tồn tại.

### 11.5. Điều chưa thể kết luận

Nếu thiếu audit của một resource trong một khoảng thời gian, review chưa thể nói mọi dữ liệu liên quan đều không bị truy cập. Cần ghi phạm vi dữ liệu thiếu và cách điều tra tiếp, hoặc quyết định rủi ro được chấp nhận theo thẩm quyền.

Một review có phần chưa biết nhưng được quản lý rõ đáng tin hơn một review tự tuyên bố “không ảnh hưởng” vì chưa tìm thấy event.

## 12. Đo kết quả phục hồi và hiệu quả cải tiến

### 12.1. Định nghĩa mốc trước khi tính

Có thể theo dõi:

~~~text
Thời gian phát hiện quan sát được:
  findingCreatedAt - firstRelevantObservedEventAt

Thời gian containment có hiệu lực:
  containmentEffectiveAt - incidentRecognizedAt

Độ trễ thu hồi:
  revocationEffectiveAt - revocationRequestedAt

Thời gian lấy lại quyền truy cập:
  verifiedOwnerAccessRestoredAt - recoveryRemediationStartedAt
~~~

Những mốc này không tự phản ánh thời điểm actor thực sự bắt đầu xâm nhập. Nếu chỉ có mốc đầu tiên quan sát được, hãy dùng đúng nhãn đó.

Với thời gian từ nhiều nguồn, ghi rõ chuẩn thời gian, sai số hoặc cách dùng version/sequence để xác minh thứ tự. Không báo độ chính xác tới millisecond nếu nguồn chỉ đáng tin ở mức khác.

### 12.2. Đo hiệu quả bảo mật cùng khả năng phục hồi

| Chỉ số | Cách diễn giải hữu ích |
|---|---|
| Số account đã có verification phục hồi đầy đủ | Phạm vi đã có bằng chứng, với tiêu chí đầy đủ được định nghĩa |
| Số account hoặc resource còn chưa xác định | Rủi ro và công việc chưa được giải quyết |
| Tỷ lệ quyền cần thu hồi đã xác minh hiệu lực | Khả năng thực thi containment, không chỉ số command thành công |
| Số vi phạm cùng bất biến sau bản sửa | Dấu hiệu tái diễn, cần kèm độ bao phủ telemetry |
| Recovery completion và yêu cầu hỗ trợ | Bản sửa có gây khó cho người dùng hợp lệ không? |
| Tỷ lệ action item đã được nghiệm thu | Đầu ra cải tiến thực tế, không chỉ trạng thái ticket |
| Thời gian xác định cohort | Khả năng điều tra và khôi phục theo phạm vi |
| Tỷ lệ bài diễn tập đạt cả negative/positive control | Kiểm soát vừa chặn quyền sai vừa giữ đường hợp lệ |

Một tỷ lệ cần có mẫu số rõ ràng. “100% session đã thu hồi” có nghĩa gì nếu inventory chỉ chứa session browser mà bỏ refresh token của ứng dụng di động?

Các account không cần cùng một tập verification. Nhưng điều kiện áp dụng hoặc không áp dụng phải được ghi, tránh loại hồ sơ khó khỏi mẫu số chỉ để tỷ lệ cao hơn.

### 12.3. Không có tái diễn chưa chứng minh đã hết rủi ro

Sự cố có thể hiếm hoặc actor chưa thử lại. Kết luận hiệu quả nên dựa trên kết hợp:

- Kiểm chứng cơ chế tại tầng phù hợp.
- Triển khai đã có hiệu lực ở phạm vi cần thiết.
- Quan sát sau triển khai với dữ liệu đủ.
- Diễn tập hoặc replay những tình huống đã gây lỗi.
- Đánh giá tác động tới recovery hợp lệ.

Không nên kéo dài một cửa sổ “chưa thấy lỗi” rồi dùng nó thay cho một test race có thể tái hiện.

## 13. Viết báo cáo và tổ chức buổi review

### 13.1. Khung báo cáo thực dụng

Một báo cáo tự chứa có thể gồm:

1. Tóm tắt hành vi sai và tác động đã xác nhận.
2. Phạm vi dịch vụ, tenant, account và cửa sổ thời gian.
3. Các sự kiện, quyết định và mốc hiệu lực quan trọng.
4. Phương pháp cùng bằng chứng đánh giá ảnh hưởng.
5. Cơ chế lỗi, nguyên nhân góp phần và khoảng trống kiểm soát.
6. Các biện pháp đã thực hiện và kết quả verification.
7. Điều hoạt động tốt và điều cản trở ứng phó.
8. Action item, owner, thời hạn và tiêu chí nghiệm thu.
9. Rủi ro tồn dư, câu hỏi mở và người chịu trách nhiệm.
10. Điều kiện đóng hoặc mở lại phần xử lý.

Không cần viết dài hơn mức bằng chứng đòi hỏi. Một sự cố nhỏ có thể dùng báo cáo ngắn nhưng vẫn phải rõ cơ chế và hành động.

### 13.2. Chuẩn bị trước buổi họp

Phát hành bản nháp cho những người có trách nhiệm đối chiếu trong phạm vi được phép. Yêu cầu họ sửa dữ kiện, bổ sung reference và đánh dấu nhận định chưa có bằng chứng.

Giữ các câu hỏi cần quyết định thành mục riêng, ví dụ:

~~~text
Cần quyết định:
  Có cho phép mở lại nhánh factor rebind trước khi
  resource R hoàn tất verification revocation không?

Thông tin đã có:
  Bản sửa grant đã qua integration test và đã triển khai.
  Browser/API chính đã có kết quả verification.

Thông tin còn thiếu:
  Refresh path của client cũ chưa được kiểm chứng.

Người quyết định:
  Owner rủi ro theo chính sách.

Biện pháp bù đắp được đề xuất:
  Giữ hạn chế riêng đường client chưa kiểm chứng.
~~~

Đây là ví dụ cách ghi quyết định trong review, không phải một phê duyệt vận hành đã được thực hiện.

### 13.3. Điều phối buổi review

Đi theo logic dữ kiện → cơ chế → tác động → bằng chứng phục hồi → việc cải tiến. Không dành toàn bộ thời gian để tranh luận một thuật ngữ nguyên nhân trong khi chưa xác định quyền nào còn hoạt động.

Mỗi kết luận cần có mức chắc chắn. Mỗi việc cải tiến cần một owner chấp nhận trách nhiệm, cùng tiêu chí và mốc thời gian phù hợp.

Nếu không thống nhất được một dữ kiện, ghi rõ vấn đề và cách kiểm chứng tiếp. Không ép đồng thuận bằng một câu mơ hồ như “có thể do nhiều yếu tố” rồi đóng mục.

### 13.4. Chia sẻ đúng mức dữ liệu

Một bản học hỏi có thể được chia sẻ rộng hơn phần bằng chứng chứa định danh người dùng hoặc hồ sơ xác minh. Giữ đường liên kết có kiểm soát để người cần kiểm tra vẫn truy được.

Không sao chép token hoặc thông tin xác minh nhạy cảm vào comment, ảnh chụp màn hình và công cụ quản lý công việc. Review có thể trở thành một điểm lộ dữ liệu thứ hai nếu gom toàn bộ bằng chứng thô vào một tài liệu chia sẻ rộng.

Việc lưu trữ và chia sẻ thực hiện theo chính sách, phân quyền và yêu cầu áp dụng của tổ chức. Bài học không đặt một thời hạn lưu giữ hoặc nghĩa vụ thông báo pháp lý chung cho mọi hệ thống.

## 14. Chốt review, theo dõi việc mở và điều kiện mở lại

### 14.1. Dùng trạng thái phản ánh bằng chứng

Đối với mỗi kiểm tra phục hồi, có thể dùng các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| VERIFIED_PASS | Có bằng chứng đáp ứng tiêu chí trong phạm vi đã ghi |
| VERIFIED_FAIL | Có bằng chứng tiêu chí chưa đạt |
| UNKNOWN | Chưa đủ dữ liệu hoặc chưa kiểm tra |
| NOT_APPLICABLE | Không áp dụng, có lý do và phạm vi rõ |

UNKNOWN không phải PASS. NOT_APPLICABLE không phải cách né một kiểm tra khó; cần chỉ ra tài sản hoặc đường quyền đó thực sự không tồn tại hay không liên quan.

Có thể biểu diễn một verification record như sau:

~~~yaml
verification:
  control: old-session-denied-after-recovery
  scope:
    resource: protected-api-a
    clientType: mobile-refresh
  expected:
    rule: old-credentials-cannot-regain-access-after-effective-revocation
  result: UNKNOWN
  evidenceRef: null
  reason: resource-verification-not-yet-completed
  followUp:
    ownerRole: session-platform-owner
    actionRef: RECOVERY-ACTION-04
~~~

Không biến record này thành PASS vì session store đã ghi revoked. Tiêu chí đang xét yêu cầu hiệu lực tại resource và refresh path.

### 14.2. Các điều kiện cần quyết định rõ

Trước khi chốt phần ứng phó, cần đối chiếu gate của tổ chức đối với:

- Đường gây tác động tiếp diễn đã được chặn hoặc hạn chế phù hợp.
- Cohort ảnh hưởng đã được xác định tới mức có thể bảo vệ bằng chứng và xử lý rủi ro.
- Các quyền liên quan đã được xử lý, với phần chưa xác minh được ghi rõ.
- Chủ thể hợp lệ có con đường lấy lại truy cập đáp ứng policy.
- Những việc mở và rủi ro tồn dư có owner cùng quyết định phù hợp.
- Telemetry đủ để theo dõi dấu hiệu tiếp diễn.
- Trạng thái triển khai, quyền tạm và exception đã được đối chiếu.

Điều kiện cụ thể có thể khác theo độ nghiêm trọng, kiến trúc và mức rủi ro. Review không tự tạo ngoại lệ thay cho quyết định có thẩm quyền.

### 14.3. Theo dõi action item sau khi đóng vận hành

Khi sự cố vận hành được đóng nhưng việc cải tiến còn mở, cần giữ cơ chế theo dõi trong hệ thống quản lý công việc. Người phụ trách review phải biết khi một deadline bị lỡ hoặc một biện pháp bù đắp sắp hết hiệu lực.

Nghiệm thu action item nên gắn với evidenceRef và người xác minh. Nếu chỉ đổi trạng thái ticket mà không có bằng chứng, bài học có thể không chuyển thành kiểm soát thực sự.

Không xóa câu hỏi mở khỏi báo cáo gốc. Cập nhật kết quả và lý do khi có bằng chứng mới để người đọc thấy quá trình nhận định đã thay đổi thế nào.

### 14.4. Khi nào cần mở lại?

Các trigger minh họa:

- Phát hiện account hoặc tenant mới thuộc cùng cơ chế lỗi.
- Credential hoặc session tưởng đã bị chặn vẫn hoạt động.
- Bản vá chưa tới một đường gọi hoặc một node.
- Bằng chứng mới bác bỏ giả định quan trọng của phạm vi.
- Biện pháp bù đắp hết hiệu lực trước khi sửa lâu dài hoàn tất.
- Cùng bất biến bị vi phạm lại sau triển khai.

Không cần giữ cùng một incident mở vô hạn nếu hệ thống quản lý có cách liên kết sự cố tiếp theo. Điều cần giữ là dữ kiện mới được phản ánh và rủi ro không bị mất trách nhiệm theo dõi.

## 15. Bài tập vận dụng

### Bài tập 1: Password đã đổi nhưng refresh còn hoạt động

Nhóm thông báo phục hồi xong vì chủ account đăng nhập được bằng password mới. Refresh token trước sự cố vẫn cấp access token được resource chấp nhận.

Hãy viết lại kết luận phục hồi và đề xuất bằng chứng cần có.

Gợi ý đáp án: quyền truy cập của chủ account đã được khôi phục một phần nhưng đường quyền cũ chưa đáp ứng yêu cầu thu hồi nếu policy yêu cầu chặn. Cần xác định cohort refresh token, cơ chế revocation, mốc hiệu lực và kết quả kiểm tra tại resource; giữ trạng thái FAIL hoặc UNKNOWN đúng dữ kiện.

### Bài tập 2: Có 1.200 grant có nguy cơ

Một báo cáo viết “1.200 tài khoản bị chiếm” vì tìm thấy 1.200 grant hoạt động trong phiên bản có lỗi.

Hãy chỉ ra các bước phân loại còn thiếu.

Gợi ý đáp án: cần khử trùng account theo tenant, xác định grant thực sự được dùng, liên kết mutation đã commit và phân biệt tác động hợp lệ với sử dụng trái phép. Các grant có nguy cơ là cohort điều tra, không phải số account compromise đã xác nhận.

### Bài tập 3: Action item chỉ ghi “thêm test”

Sự cố do hai request đồng thời dùng một grant, nhưng công việc cải tiến chỉ ghi “thêm unit test cho reset password”.

Hãy viết acceptance cụ thể hơn.

Gợi ý đáp án: hai transaction độc lập cùng cố hoàn tất bằng grant một lần; chỉ một mutation được commit, grant và credential nhất quán khi rollback, retry không tạo mutation mới và một recovery hợp lệ vẫn thành công. Tầng database integration cần kiểm tra được cơ chế cạnh tranh thực.

### Bài tập 4: Nhân viên đã thấy gì?

Một nhân viên phê duyệt vì UI hiển thị “verified”. Sau sự cố mới biết bằng chứng đã bị thay phiên bản trước lúc phê duyệt, nhưng UI không thể hiện điều đó.

Hãy phân tích mà không dừng ở kết luận cá nhân.

Gợi ý đáp án: xác định kiểm tra evidence version ở authority, ranh giới phê duyệt và commit, dữ kiện UI cung cấp, quyền override và audit. Các việc cải tiến có thể cần sửa kiểm tra server, mô hình trạng thái và thông tin quyết định, thay vì chỉ yêu cầu nhân viên cẩn thận hơn.

### Bài tập 5: Có thể đóng khi còn việc mở không?

Đường lỗi đã bị chặn và các quyền liên quan đã được kiểm chứng. Một cải tiến dashboard chưa hoàn tất nhưng có owner và deadline.

Hãy nêu các yếu tố quyết định việc đóng phần vận hành.

Gợi ý đáp án: đối chiếu gate của tổ chức, xác nhận dashboard chưa hoàn tất không để lại đường tác động tiếp diễn hoặc khoảng mù vượt rủi ro được chấp nhận, ghi việc mở và biện pháp bù đắp nếu cần. Không tự yêu cầu mọi cải tiến phải xong, cũng không đóng chỉ vì đã có ticket.

## 16. Kết quả cần giữ lại sau review

Review cần để lại một lập luận có thể kiểm chứng: cơ chế lỗi đã được hiểu tới đâu, phạm vi nào có bằng chứng, quyền kiểm soát nào đã được phục hồi và những việc nào sẽ ngăn hoặc hạn chế tái diễn.

Đối với recovery, điểm chốt không nằm ở việc một biểu mẫu lại hoạt động hay một password đã được thay. Nó nằm ở bằng chứng rằng đúng chủ thể có thể tiếp tục sử dụng tài khoản theo policy, các đường quyền trái phép liên quan đã được xử lý và các khoảng trống còn lại có trách nhiệm quản lý rõ ràng.

## Tài liệu tham khảo

- [NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final): bối cảnh quản lý rủi ro cho phát hiện, phản ứng và phục hồi sự cố.
- [Google SRE — Postmortem Culture: Learning from Failure](https://sre.google/sre-book/postmortem-culture/): học hỏi từ sự cố, phân tích nguyên nhân góp phần và theo dõi việc cải tiến.
- [OWASP Forgot Password Cheat Sheet — Account Recovery After Suspected Compromise](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise): xem xét quyền kiểm soát account khi session, factor hoặc thông tin recovery có thể đã bị chiếm dụng.
