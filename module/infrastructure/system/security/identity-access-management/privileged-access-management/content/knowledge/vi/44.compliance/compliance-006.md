# Emergency access evidence — Bằng chứng truy cập khẩn cấp trong PAM

## 1. Vì sao truy cập khẩn cấp cần một hồ sơ riêng?

Khi hệ thống xác thực, vault hoặc quy trình cấp quyền thông thường gặp sự cố, đội vận hành có thể phải sử dụng cơ chế truy cập khẩn cấp, thường gọi là emergency access hoặc break-glass. Quyền này có thể rất rộng và đường truy cập có thể khác đường được giám sát hằng ngày. Vì vậy, việc khôi phục dịch vụ thành công chưa đủ để kết luận lần sử dụng đó được quản lý tốt.

Emergency access evidence là tập bằng chứng giúp một người không tham gia xử lý sự cố dựng lại được:

- Vì sao phải dùng đường khẩn cấp tại thời điểm đó.
- Ai ra quyết định, ai thực hiện và ai giám sát.
- Quyền, tài khoản và tài nguyên nào thực sự được sử dụng.
- Những hành động nào đã xảy ra, với kết quả và tác động gì.
- Việc sử dụng kết thúc khi nào, quyền tạm thời và phiên truy cập được xử lý ra sao.
- Những thiếu hụt nào còn tồn tại, ai chịu trách nhiệm khắc phục và ai rà soát kết luận.

Trong module PAM, hồ sơ này nối hoạt động kiểm kê tài khoản đặc quyền, kiểm soát cấp quyền, vault, giám sát phiên và ứng phó sự cố với khả năng giải trình. Mục tiêu của bài là thiết kế hồ sơ có thể kiểm tra, đặc biệt khi một phần hạ tầng thu thập bằng chứng cũng đang hỏng.

Một nguyên tắc quan trọng: không được sửa lịch sử để hồ sơ trông đầy đủ. Nếu quyết định được ghi bổ sung sau sự kiện, phải giữ cả thời điểm quyết định được cho là đã xảy ra và thời điểm bản ghi được tạo, kèm nguồn xác nhận.

## 2. Phân biệt sự kiện, bằng chứng và kết luận

Ba lớp thông tin thường bị trộn lẫn:

| Lớp | Ví dụ | Giá trị và giới hạn |
| --- | --- | --- |
| Sự kiện nguồn | Hệ thống ghi nhận tài khoản khẩn cấp đăng nhập lúc 02:16 | Chứng minh hệ thống đã ghi sự kiện đó; chưa tự xác định người cầm credential |
| Bằng chứng được bảo quản | Bản xuất log có phạm vi truy vấn, người xuất, thời gian thu thập và mã băm | Giúp kiểm tra nguồn gốc, phạm vi và sự thay đổi của bản xuất |
| Nhận định rà soát | Các thao tác phù hợp phạm vi xử lý sự cố | Là kết luận cần dẫn tới bằng chứng cụ thể, người đánh giá và tiêu chí áp dụng |

Ảnh chụp ticket ghi “đã duyệt” có thể hỗ trợ chứng minh một quyết định được ghi nhận. Nó không tự chứng minh quyết định đã có trước lúc cấp quyền. Bản ghi đăng nhập thành công chứng minh một hoạt động xác thực; nó không chứng minh mọi hành động sau đăng nhập đều hợp lệ.

Bài học thực hành là viết mỗi kết luận theo dạng: nhận định, bằng chứng hỗ trợ, giới hạn và người chịu trách nhiệm. Khi thiếu liên kết giữa các lớp, giữ trạng thái chưa xác định thay vì suy đoán.

## 3. Hồ sơ phải trả lời những câu hỏi nào?

Thiết kế hồ sơ từ các câu hỏi kiểm tra, không chỉ từ những trường mà công cụ PAM đang cung cấp.

| Câu hỏi | Bằng chứng thường dùng | Điểm cần đối chiếu |
| --- | --- | --- |
| Có tình huống khẩn cấp thật không? | Incident, cảnh báo, ghi nhận mất khả năng truy cập bình thường | Mức độ ảnh hưởng, thời điểm và lý do đường chuẩn không dùng được |
| Người sử dụng có thuộc nhóm được phép không? | Danh sách được ủy quyền có phiên bản, lịch trực, xác minh danh tính | Thẩm quyền tại thời điểm sử dụng, không chỉ danh sách hiện tại |
| Việc kích hoạt có đúng quy trình không? | Quyết định, phê duyệt hoặc căn cứ kích hoạt theo runbook | Thời điểm, người có thẩm quyền và loại tình huống |
| Đã sử dụng tài khoản và quyền nào? | Account ID, bản ghi checkout, role assignment, xác thực | Định danh ổn định, tenant hoặc môi trường và tài nguyên đích |
| Đã làm gì? | Audit tại đích, bản ghi phiên, thay đổi cấu hình | Thao tác, kết quả, đối tượng bị thay đổi và phần không quan sát được |
| Có giám sát không? | Cảnh báo, xác nhận của SOC, nhật ký người quan sát | Thời gian gửi, nhận, phản hồi và lỗi chuyển tiếp |
| Đã kết thúc sử dụng an toàn chưa? | Kết thúc phiên, thu hồi quyền tạm, xử lý credential, kiểm thử sau phục hồi | Phân biệt tài khoản thường trực với quyền được cấp thêm trong sự cố |
| Có rà soát độc lập không? | Báo cáo hậu kiểm, quyết định xử lý ngoại lệ | Người đánh giá, phạm vi bằng chứng và các việc còn mở |

Bảng trên là mô hình thiết kế cho bài học, không phải một danh sách tự động chứng nhận tuân thủ. Tổ chức phải xác định tiêu chí, thời hạn lưu và yêu cầu bổ sung theo phạm vi hệ thống của mình.

## 4. Chuẩn bị bằng chứng trước khi sự cố xảy ra

### 4.1. Xác định trước cơ chế và chủ sở hữu

Mỗi cơ chế emergency access cần có định danh, chủ sở hữu, tài nguyên được bảo vệ, người được phép kích hoạt, cách lấy credential hoặc phương tiện xác thực và điều kiện sử dụng.

Nên lưu phiên bản runbook và chính sách áp dụng. Sau ba tháng, quy trình có thể đã đổi; chỉ giữ đường dẫn tới phiên bản mới nhất sẽ làm người rà soát khó biết quy trình nào có hiệu lực khi sự kiện xảy ra.

Cần phân biệt ít nhất hai mô hình:

- Tài khoản khẩn cấp luôn được duy trì sẵn, có quyền cần thiết để phục hồi khả năng quản trị.
- Quyền khẩn cấp được cấp tạm hoặc mở rộng trong một khoảng thời gian, có cơ chế hết hạn hay thu hồi.

Kết thúc một lần sử dụng không đồng nghĩa phải vô hiệu hóa mọi tài khoản khẩn cấp. Điều đó có thể phá hỏng khả năng phục hồi của lần sau. Hồ sơ phải ghi chính xác phần nào được kết thúc, phần nào được thu hồi và cấu hình sẵn sàng nào được duy trì theo thiết kế.

### 4.2. Chuẩn bị nguồn ghi nhận độc lập

Nếu mọi nguồn bằng chứng đều phụ thuộc vào cùng IdP, cùng vault và cùng mạng đang gặp sự cố, tổ chức có thể vừa mất đường quản trị vừa mất khả năng quan sát.

Trước sự cố, nên xác định:

1. Nguồn audit tại hệ thống đích.
2. Nguồn đăng nhập hoặc xác thực.
3. Nguồn cấp quyền, checkout hoặc sử dụng phương tiện khẩn cấp.
4. Nơi nhận cảnh báo và người trực.
5. Cách ghi chép thay thế khi ticketing hay SIEM không truy cập được.
6. Cách đồng bộ bản ghi thay thế sau khi hệ thống phục hồi.

Độc lập không có nghĩa mỗi nguồn chắc chắn đầy đủ. Cần ghi rõ nguồn nào tồn tại, ai truy cập được, độ trễ dự kiến và thời gian dữ liệu còn sẵn để xuất.

### 4.3. Kiểm tra bằng diễn tập

Diễn tập phải kiểm tra cả đường truy cập và đường bằng chứng. Một lần đăng nhập thử thành công nhưng không sinh cảnh báo hoặc không xuất được audit vẫn để lại thiếu hụt.

Đánh dấu rõ sự kiện là diễn tập. Giữ phạm vi, người cho phép, kết quả và lỗi phát hiện để tránh nhầm lần thử với sự cố thật.

Trong hướng dẫn riêng cho Microsoft Entra, Microsoft khuyến nghị theo dõi hoạt động đăng nhập và audit của tài khoản emergency access, tạo cảnh báo và rà soát sau khi sử dụng. Đây là ví dụ triển khai theo sản phẩm, không phải yêu cầu cấu hình chung cho mọi hệ thống PAM. [Microsoft Learn — Manage emergency access accounts](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access).

## 5. Thu thập bằng chứng trong lúc kích hoạt và sử dụng

### 5.1. Tạo mã tham chiếu ngay khi có thể

Một lần sử dụng nên có mã sự kiện thống nhất, chẳng hạn EA-DEMO-014. Mã này liên kết incident, ticket khẩn, bản ghi checkout, phiên truy cập, cảnh báo và hồ sơ rà soát.

Không phải hệ thống nào cũng cho gắn mã vào log. Khi đó, lập bảng tương quan bằng các định danh thực:

~~~text
Emergency event: EA-DEMO-014
Incident: INC-DEMO-872
Human operator: person-042
Emergency account: account-bg-02
Target: tenant-lab-a / directory
Sign-in event: signin-2381
Administrative operation: operation-774
Session: not available — direct emergency path
~~~

Các giá trị trong ví dụ là giả lập. Account ID hoặc object ID ổn định thường hữu ích hơn tên hiển thị vì tên có thể đổi. Với hệ thống nhiều tenant, cùng một tên tài khoản không đủ để xác định đúng đối tượng.

### 5.2. Ghi nguyên nhân và căn cứ kích hoạt

“P1, cần gấp” là lý do quá mơ hồ. Một ghi nhận tốt nên nêu:

- Dịch vụ nào mất khả năng quản trị và ảnh hưởng thực tế.
- Đường cấp quyền chuẩn bị lỗi ở đâu hoặc vì sao không đáp ứng được tình huống.
- Hành động phục hồi dự kiến và phạm vi tài nguyên.
- Người ra quyết định, căn cứ trong runbook và thời gian sử dụng dự kiến.
- Cách liên hệ người giám sát hoặc người có thẩm quyền.

Không yêu cầu người xử lý lặp lại các thao tác gây gián đoạn chỉ để tạo thêm log chứng minh sự cố. Bằng chứng có thể là cảnh báo, kết quả lỗi sẵn có hoặc ghi nhận trực tiếp với giới hạn được nêu rõ.

### 5.3. Phê duyệt và hậu kiểm phải có nhãn đúng

Có thể có các trường hợp khác nhau tùy quy trình đã được tổ chức cho phép:

| Trường hợp | Cách ghi nhận |
| --- | --- |
| Phê duyệt trước | Thời điểm quyết định, người phê duyệt, phạm vi và tham chiếu bản ghi |
| Quyền kích hoạt đã được ủy quyền trước theo runbook | Phiên bản runbook, điều kiện được đáp ứng, người kích hoạt và thông báo |
| Không lấy được phê duyệt trước, có cơ chế ngoại lệ được định nghĩa | Điều kiện ngoại lệ, nỗ lực liên hệ, người ra quyết định và thời hạn rà soát |
| Không có căn cứ cho phép phù hợp | Ghi nhận sai lệch hoặc nghi vấn sử dụng trái phép và chuyển xử lý |

Bản phê duyệt được tạo sau không được đổi nhãn thành “phê duyệt trước”. Người rà soát có thể chấp nhận hoặc không chấp nhận ngoại lệ, nhưng không thể làm thay đổi thứ tự sự kiện đã xảy ra.

Hồ sơ cần tách thời điểm cuộc gọi, thời điểm tạo ticket và thời điểm người liên quan xác nhận lại nội dung cuộc gọi. Nếu thời điểm cuộc gọi chỉ dựa vào lời kể, phải ghi rõ.

### 5.4. Quy trách nhiệm khi dùng tài khoản chung

Log của tài khoản break-glass dùng chung thường chỉ cho thấy tài khoản kỹ thuật. Để quy hoạt động cho một cá nhân, cần thêm chứng cứ như:

- Người nhận phương tiện xác thực hoặc bản ghi custody của thiết bị.
- Người checkout credential từ vault hoặc mở kho dự phòng.
- Thiết bị quản trị và danh tính phiên trên thiết bị.
- Người quan sát hoặc xác nhận độc lập.
- Thời điểm bàn giao nếu thay người thao tác.

Địa chỉ IP không tự chứng minh một người cụ thể, nhất là khi nhiều người dùng chung jump host hoặc đi qua NAT. Lịch trực chứng minh ai được phân công, không tự chứng minh ai đã thao tác.

Nếu nhiều người đồng thời sử dụng cùng tài khoản mà không tách được hoạt động, ghi rõ giới hạn quy trách nhiệm. Không chọn tên một người để lấp trường trống.

### 5.5. Ghi hành động và kết quả

Tùy hệ thống, bằng chứng có thể là bản ghi phiên, audit API, lịch sử lệnh, thay đổi chính sách hoặc audit database. Nên kết hợp nguồn tại đích với nguồn PAM khi có.

Một bản ghi hành động cần giúp hiểu:

~~~text
02:18:11Z — operator person-042, account account-bg-02
Target: tenant-lab-a / policy policy-17
Action: disable newly deployed policy policy-17
Result: success
Reason: restore normal administrative sign-in
Evidence: audit event operation-774; configuration versions v18 -> v19
~~~

Đây là ví dụ mô tả cấu trúc, không phải schema của một nhà cung cấp.

Không đưa password, token, private key hay mã khôi phục vào hồ sơ. Với lệnh có thể chứa secret, cần thiết kế cách ghi nhận và bảo vệ bản gốc từ trước. Bản dùng cho rà soát có thể được che dữ liệu; phải giữ quan hệ giữa bản gốc và bản đã xử lý, thay vì sửa âm thầm bản gốc.

## 6. Kết thúc sử dụng: bằng chứng khép lại cửa sổ đặc quyền

Trạng thái “incident resolved” thường chỉ phản ánh dịch vụ đã phục hồi. Hồ sơ emergency access còn cần xác nhận phần đặc quyền đã được xử lý.

Các hành động phải được lựa chọn theo mô hình truy cập thực tế:

| Đối tượng | Bằng chứng kết thúc phù hợp |
| --- | --- |
| Phiên tương tác | Session end, logout hoặc thao tác chấm dứt phiên với kết quả |
| Quyền được cấp thêm tạm thời | Sự kiện thu hồi hoặc hết hạn, kiểm tra quyền hiệu lực sau đó |
| Credential đã được tiết lộ | Quyết định rotate, reissue hoặc xử lý theo chính sách và kết quả thực hiện |
| Token hoặc phiên còn hiệu lực | Thao tác thu hồi có hỗ trợ, phạm vi tác dụng và phần chưa vô hiệu ngay |
| Thiết bị xác thực dự phòng | Biên bản hoàn trả hoặc tái niêm phong và người tiếp nhận |
| Tài khoản emergency thường trực | Kiểm tra cấu hình sẵn sàng, bảo quản phương tiện và không còn phiên sử dụng ngoài kế hoạch |
| Thay đổi khẩn cấp trên hệ thống đích | Diff, change record, xác minh phục hồi và quyết định giữ lại hoặc rollback |

Đổi mật khẩu không tự chứng minh mọi token hay phiên đã bị vô hiệu hóa. Khả năng thu hồi phụ thuộc hệ thống đích, loại token và cách ứng dụng xác thực. Hồ sơ phải phản ánh thao tác thực sự đã làm và điều gì đã kiểm chứng.

Nếu không thể hoàn tất một việc, ghi chủ sở hữu, hạn xử lý, rủi ro còn lại và người có thẩm quyền quyết định biện pháp tạm thời. Không gắn nhãn “đã thu hồi” chỉ vì đã tạo ticket yêu cầu thu hồi.

Sau khi thay credential hoặc phương tiện, cần xác nhận cơ chế khẩn cấp vẫn sử dụng được theo quy trình kiểm thử được phép. Khép lại lần dùng hiện tại và duy trì khả năng phục hồi là hai mục tiêu cùng phải được xem xét.

## 7. Chuẩn hóa thời gian và tương quan sự kiện

### 7.1. Giữ cả thời gian sự kiện và thời gian thu thập

Một log có thể xảy ra lúc 02:16 nhưng chỉ tới SIEM lúc 02:27. Hai mốc đó trả lời hai câu hỏi khác nhau.

Hồ sơ nên giữ:

- Thời gian sự kiện do hệ thống nguồn ghi.
- Múi giờ hoặc độ lệch UTC trong bản ghi.
- Thời gian SIEM tiếp nhận nếu có.
- Thời gian người thu thập xuất hoặc sao chép dữ liệu.
- Thông tin sai lệch đồng hồ được biết, cùng căn cứ đo.

Không thêm hậu tố Z vào một timestamp giờ địa phương chưa được chuyển đổi. Ví dụ, 09:16:00+07:00 và 02:16:00Z biểu diễn cùng một thời điểm, nhưng 09:16:00Z là thời điểm khác.

Nếu đồng hồ nguồn bị chậm, giữ nguyên giá trị nguồn và tạo cột thời gian chuẩn hóa riêng. Không sửa log gốc. Khi sai lệch chỉ được ước lượng, biểu diễn khoảng bất định thay vì gán độ chính xác giả tạo tới mili giây.

### 7.2. Chọn cửa sổ đủ rộng và ghi phạm vi

Truy vấn chỉ đúng phút đăng nhập có thể bỏ sót chuẩn bị trước đó, đăng nhập thất bại, thay đổi quyền hoặc phiên còn kéo dài sau lúc sự cố được tuyên bố khôi phục.

Ghi rõ thời gian bắt đầu và kết thúc truy vấn, bao gồm hay loại trừ mốc biên, bộ lọc tài khoản, tenant, tài nguyên và nguồn. Khi kiểm tra dữ liệu tới trễ, ghi một lần truy vấn bổ sung và quan hệ của nó với lần xuất trước.

Cần giải thích ý nghĩa của ba tình huống:

- Không tìm thấy sự kiện trong phạm vi truy vấn đã nêu.
- Nguồn xác nhận có dữ liệu bao phủ phạm vi nhưng không có sự kiện phù hợp.
- Không có đủ dữ liệu để kết luận vì nguồn bị gián đoạn hoặc đã hết thời gian lưu.

Ba kết quả này không tương đương.

## 8. Đóng gói và bảo quản bằng chứng

### 8.1. Tách bản gốc, bản phân tích và báo cáo

Một cấu trúc logic cho hồ sơ có thể là:

~~~text
EA-DEMO-014/
  manifest.yml
  source/
    authentication-export.json
    target-audit-export.json
    custody-record.pdf
  derived/
    normalized-timeline.csv
    redacted-review-copy.pdf
  review/
    assessment.md
    action-items.csv
~~~

Đây là mô hình minh họa trong bài học, không phải yêu cầu tạo các file đó khi đọc bài.

Bản xuất từ hệ thống cũng là một sản phẩm thu thập: nó không mặc nhiên chứa toàn bộ log nguồn. Vì vậy, ngoài nội dung cần giữ công cụ, bộ lọc, phân trang, giới hạn số bản ghi và lỗi xuất nếu có.

Báo cáo dẫn tới các artifact bằng ID hoặc đường dẫn ổn định có kiểm soát truy cập. Tránh chỉ dùng link tới một màn hình dashboard có bộ lọc thay đổi hoặc link hết hạn.

### 8.2. Mã băm và giới hạn của nó

Mã băm SHA-256 có thể giúp phát hiện artifact thay đổi so với giá trị đã ghi nhận. Nó không tự chứng minh artifact là thật, đầy đủ hoặc đã được tạo trước sự cố.

Nếu một người có thể sửa cả file và manifest chứa hash mà không để lại dấu vết, việc hai giá trị khớp nhau không đủ bảo đảm tính toàn vẹn lịch sử. Có thể cần nơi lưu có kiểm soát phiên bản, quyền ghi tách biệt, nhật ký truy cập, cơ chế lưu bất biến hoặc ký xác nhận phù hợp thiết kế.

Ví dụ kiểm tra một artifact đã được phép thu thập bằng PowerShell:

~~~powershell
$artifactPath = 'C:\Evidence-Lab\EA-DEMO-014\source\target-audit-export.json'
$artifactHash = Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256
$artifactHash | Select-Object Algorithm, Hash, Path
~~~

Lệnh chỉ tính mã băm của file hiện có. Khi bàn giao, bên nhận tính lại và so với giá trị tham chiếu được bảo vệ. Đừng diễn giải việc hash khớp thành kết luận “mọi hoạt động emergency đều hợp lệ”.

### 8.3. Theo dõi quá trình thu thập và bàn giao

Chuỗi quản lý bằng chứng nên ghi ai lấy dữ liệu từ đâu, thời điểm nào, bằng cách nào, chuyển cho ai và đã làm biến đổi gì.

Với mỗi artifact, có thể ghi:

~~~yaml
artifactId: ev-014-03
eventId: EA-DEMO-014
sourceSystem: tenant-lab-a-audit
sourceKind: administrative-audit
eventWindow:
  startInclusive: "2030-05-16T02:00:00Z"
  endExclusive: "2030-05-16T03:00:00Z"
collection:
  collectedAt: "2030-05-16T03:10:00Z"
  collectorId: person-091
  method: approved-audit-export
  queryRef: query-014-b
  exportComplete: true
  paginationVerified: true
integrity:
  algorithm: SHA-256
  digest: "<gia-tri-hex-64-ky-tu-tu-file-thuc-te>"
classification: restricted-security
storageRef: evidence-store/EA-DEMO-014/ev-014-03
~~~

Ngày tháng và định danh ở đây là giả lập. Trường digest là placeholder, không phải hash hợp lệ. Chỉ đánh dấu exportComplete hoặc paginationVerified sau khi thực sự kiểm tra; nếu công cụ không cho xác định tính đầy đủ, lưu giới hạn đó.

### 8.4. Lưu trữ, truy cập và hủy

Hồ sơ emergency access có thể chứa danh tính, địa chỉ mạng, cấu hình nhạy cảm và dữ liệu xuất hiện trong phiên. Chỉ người có nhiệm vụ mới được xem phần cần thiết; quyền xem báo cáo không mặc nhiên bao gồm quyền tải bản ghi phiên đầy đủ.

Chính sách cần xác định thời gian lưu, chủ sở hữu, phạm vi sao lưu, người được xuất bản sao và cách xử lý yêu cầu giữ dữ liệu phục vụ điều tra. Không tự đặt một thời gian lưu chung cho mọi tổ chức hoặc cho rằng số ngày lưu mặc định của SIEM đáp ứng mọi nghĩa vụ.

Khi hết thời gian lưu và không còn yêu cầu giữ, việc hủy phải theo quy trình áp dụng, bao gồm bản sao liên quan trong phạm vi quản lý. Hồ sơ hủy có thể giữ định danh artifact và quyết định xử lý mà không giữ lại nội dung đã được phép xóa.

## 9. Khi PAM, SIEM hoặc ticketing bị gián đoạn

Emergency access được thiết kế để ứng phó với thất bại của đường thông thường, nên khả năng thu thập bằng chứng trong chế độ suy giảm phải được chuẩn bị trước.

### 9.1. PAM proxy không hoạt động

Nếu runbook cho phép đường truy cập trực tiếp, có thể không có session recording từ PAM. Cần ghi đây là đường trực tiếp và giải thích lý do. Không tạo một session ID giả để hồ sơ giống trường hợp chuẩn.

Nguồn thay thế có thể là audit tại đích, log hệ điều hành, ghi nhận trên máy quản trị và người quan sát. Mỗi nguồn có giới hạn. Bản ghi người quan sát thường không bao phủ mọi API nền hoặc mọi thao tác tự động.

Nếu không có nguồn nào ghi chi tiết hành động, phải thừa nhận khoảng trống. Kết quả khôi phục dịch vụ không bù được việc thiếu lịch sử thao tác.

### 9.2. SIEM không nhận log

Phân biệt lỗi thu thập tập trung với việc hệ thống đích không ghi log. Có thể dữ liệu còn tồn tại tại nguồn và xuất được sau khi phục hồi.

Ghi nhận khoảng gián đoạn, khả năng buffer, thời gian dữ liệu nguồn còn sẵn và người chịu trách nhiệm thu thập. Sau phục hồi, đối chiếu dữ liệu tới trễ, số lượng bản ghi và sự kiện kích hoạt cảnh báo. Không chỉ đính kèm một cảnh báo sinh muộn rồi kết luận cảnh báo đã hoạt động kịp thời.

### 9.3. Ticketing không truy cập được

Dùng biểu mẫu dự phòng đã được chấp thuận hoặc ghi nhận trên kênh liên lạc thay thế theo runbook. Giữ thông tin người tạo, người nhận, thời gian và nội dung quyết định.

Khi nhập lại vào ticketing, giữ mã dự phòng và thời gian tạo bản ghi gốc. Thời gian ticket mới được tạo phải là thời gian nhập lại thực tế. Bản nhập lại là bản bổ sung có nguồn, không phải bằng chứng rằng ticket đã tồn tại trước đó.

### 9.4. Bằng chứng nghi bị can thiệp

Nếu nghi tài khoản đặc quyền đã xóa hoặc sửa audit, cần chuyển xử lý theo quy trình ứng phó sự cố. Bảo toàn các bản sao độc lập còn lại, ghi rõ mức tin cậy và tránh kết luận chỉ từ nguồn có thể đã bị kiểm soát.

Không xóa các artifact mâu thuẫn. Mâu thuẫn giữa hai nguồn có thể là dấu hiệu sai đồng hồ, lỗi tương quan hoặc hành vi đáng điều tra.

## 10. Ví dụ: khôi phục đường quản trị bị khóa

Tình huống giả lập: một thay đổi chính sách khiến đội quản trị không thể đăng nhập bằng đường thông thường. Tài khoản emergency đã được thiết kế sẵn để phục hồi quản trị. PAM proxy đang không khả dụng, nhưng hệ thống đích vẫn ghi audit.

### 10.1. Timeline được dựng từ bằng chứng

| Thời gian UTC | Sự kiện | Bằng chứng | Nhận định ban đầu |
| --- | --- | --- | --- |
| 02:10 | Cảnh báo mất đăng nhập quản trị | ev-014-01, cảnh báo nguồn | Xác nhận có ảnh hưởng; chưa biết nguyên nhân |
| 02:12 | Incident commander quyết định dùng runbook khẩn | ev-014-02, bản ghi kênh dự phòng | Quyết định trước khi lấy phương tiện |
| 02:14 | person-042 nhận phương tiện của account-bg-02 | ev-014-04, custody record | Liên kết con người với tài khoản |
| 02:16 | Đăng nhập emergency thành công | ev-014-05, sign-in event | Chưa tự chứng minh các thay đổi tiếp theo |
| 02:18 | Vô hiệu chính sách mới policy-17 | ev-014-03, operation-774 | Cần đối chiếu diff và phạm vi được phép |
| 02:22 | Xác minh đăng nhập thường hoạt động lại | ev-014-06, kết quả kiểm thử | Chứng minh phục hồi chức năng được kiểm tra |
| 02:24 | Người dùng đăng xuất | ev-014-07, session hoặc audit tương ứng | Cần xét phần phiên/token khác còn hiệu lực |
| 02:27 | SOC nhận cảnh báo đăng nhập emergency | ev-014-08, thời gian tiếp nhận | Cảnh báo tới chậm so với 02:16 |
| 02:35 | Hoàn trả phương tiện; hoàn tất các bước kết thúc được áp dụng | ev-014-09, custody và checklist | Cần kiểm tra từng bước có kết quả |
| 03:10 | Xuất audit để bảo quản | manifest và receipt thu thập | Đây là thời gian thu thập, không phải thời gian hành động |

Việc SOC nhận cảnh báo lúc 02:27 phải được ghi như một độ trễ. Nếu tiêu chí nội bộ yêu cầu nhận sớm hơn, đây là sai lệch cần xử lý dù đội vận hành khôi phục dịch vụ thành công.

### 10.2. Hai kết luận có thể cùng đúng

Kết luận vận hành: đường quản trị đã phục hồi và thay đổi thực hiện phù hợp mục tiêu incident, dựa trên operation-774, diff cấu hình và kiểm thử.

Kết luận bằng chứng: không có session recording vì đường emergency trực tiếp; audit tại đích cho thấy thay đổi được nêu, nhưng không thay thế hoàn toàn quan sát phiên. Cảnh báo tới chậm, cần mở việc khắc phục và kiểm tra lại.

Một hồ sơ trung thực có thể được lập đầy đủ về các thông tin hiện biết, trong khi vẫn mang ngoại lệ kiểm soát chưa xử lý xong. Không ép mọi kết quả thành PASS chỉ để đóng incident.

## 11. Mẫu báo cáo lần sử dụng

Mẫu dưới đây là cấu trúc minh họa để thiết kế hồ sơ, không phải schema bắt buộc của PAM hay tiêu chuẩn chứng nhận.

~~~yaml
event:
  id: EA-DEMO-014
  kind: actual-emergency
  incidentRef: INC-DEMO-872
  environment: lab
  policyVersion: EA-POLICY-v3
  runbookVersion: EA-RUNBOOK-v7

activation:
  reason: normal-admin-sign-in-unavailable
  authorizationMode: prior-decision
  decisionRef: ev-014-02
  operatorId: person-042
  emergencyAccountId: account-bg-02
  custodyRef: ev-014-04
  targetScope:
    - tenant-lab-a/policy-17
  startedAt: "2030-05-16T02:16:00Z"

observation:
  accessPath: direct-emergency
  recordingAvailability: unavailable
  recordingGapReason: pam-proxy-unavailable
  targetAuditRef: ev-014-03
  alertReceiptRef: ev-014-08

closure:
  interactiveUseEndedAt: "2030-05-16T02:24:00Z"
  closureEvidenceRefs:
    - ev-014-07
    - ev-014-09
  temporaryRoleRemoval:
    applicability: not-applicable
    reason: no-additional-temporary-role-was-granted
  standingEmergencyReadiness:
    state: verified
    evidenceRef: ev-014-09
  residualAccessAssessmentRef: assessment-014-access

review:
  reviewerId: person-091
  outcome: findings-open
  findings:
    - alert-delivery-delay
    - session-recording-unavailable-on-direct-path
  assessmentRef: assessment-014
  remediationRef: action-014
~~~

Một số điểm cần đọc đúng:

- actual-emergency phân biệt với diễn tập hoặc một lần sử dụng bị nghi trái phép.
- authorizationMode mô tả cách quyết định được thực hiện, không thay thế bằng chứng quyết định.
- not-applicable phải có lý do. Không dùng nó để che việc quên thu hồi quyền đã cấp.
- evidenceRef phải trỏ tới artifact thực có trong manifest và có thể truy cập theo quyền.
- verified là kết quả kiểm tra có dẫn chứng, không phải lời cam kết.
- findings-open giữ rõ các phát hiện còn tồn tại, ngay cả khi không còn phiên emergency đang hoạt động.

## 12. Rà soát sau sự kiện

Người rà soát nên độc lập với người trực tiếp thao tác ở mức khả thi theo mô hình tổ chức. Nếu không tách được vai trò, ghi xung đột và bố trí kiểm tra bổ sung phù hợp.

Quá trình rà soát nên đi từ lần sử dụng thực tế tới bằng chứng, rồi mới so với tiêu chí:

1. Xác nhận mọi lần sử dụng tài khoản emergency trong cửa sổ đều có mã sự kiện hoặc được điều tra.
2. Đối chiếu người thao tác với danh sách được ủy quyền có hiệu lực.
3. Kiểm tra trình tự quyết định, nhận phương tiện, đăng nhập và hành động.
4. So hành động thực tế với mục tiêu, phạm vi và thay đổi được cho phép.
5. Kiểm tra nguồn bằng chứng, khoảng trống và tính nhất quán thời gian.
6. Xác nhận kết thúc quyền hoặc phiên theo đối tượng thực tế.
7. Ghi kết luận riêng cho tính phù hợp của việc sử dụng và mức đầy đủ của bằng chứng.
8. Giao chủ sở hữu, thời hạn và bằng chứng xác nhận khắc phục cho từng phát hiện.

Việc không tìm thấy ticket cho một log emergency cần được điều tra, không nên loại log đó khỏi mẫu kiểm tra. Ngược lại, ticket có trạng thái đóng nhưng không có log tương ứng cũng cần làm rõ: có thể lần kích hoạt bị hủy, truy cập không thành công, sai phạm vi truy vấn hoặc thiếu dữ liệu.

Rà soát phải bao gồm các lần thất bại, bị từ chối hoặc bị hủy khi chúng nằm trong phạm vi đã xác định. Chỉ xem phiên thành công có thể bỏ sót thử nghiệm credential, sử dụng sai hoặc lỗi của cơ chế khẩn cấp.

## 13. Liên hệ với yêu cầu kiểm soát

Có thể lập bảng liên hệ giữa câu hỏi kiểm soát và bằng chứng, nhưng cần giữ tiêu chí đánh giá tách khỏi kết quả.

| Mục tiêu | Bằng chứng liên quan | Kết quả có thể ghi |
| --- | --- | --- |
| Chỉ người được phép kích hoạt | Danh sách ủy quyền, quyết định và custody | Đủ căn cứ, có sai lệch hoặc chưa xác định |
| Hoạt động đặc quyền có thể truy vết | Sign-in, audit tại đích, timeline và giới hạn | Bao phủ đầy đủ theo tiêu chí hoặc có khoảng trống cụ thể |
| Quyền và phiên được xử lý sau sử dụng | Sự kiện thu hồi, kết thúc phiên và kiểm tra hiệu lực | Đã xác nhận từng đối tượng hoặc còn việc mở |
| Bằng chứng được bảo quản | Manifest, hash, quyền lưu trữ, nhật ký bàn giao | Kiểm tra được các thuộc tính đã thiết kế |
| Sử dụng được rà soát | Báo cáo độc lập, phát hiện và remediation | Hoàn tất rà soát; phát hiện đã đóng hoặc còn mở |

NIST SP 800-53 cung cấp danh mục kiểm soát để tổ chức lựa chọn và điều chỉnh theo bối cảnh. Bảng liên hệ của bài là gợi ý thiết kế hồ sơ, không phải phép chứng minh tự động tương đương một baseline hoặc tiêu chuẩn khác. NIST cũng lưu ý rằng quan hệ mapping giữa các khuôn khổ không mặc nhiên là tương đương. [NIST — SP 800-53 Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final).

Không suy ra rằng có WORM, có hash hoặc có ticket là đã đáp ứng toàn bộ yêu cầu kiểm toán. Mỗi cơ chế chỉ hỗ trợ một số thuộc tính và còn phụ thuộc cấu hình, phạm vi, quyền quản trị và việc thực thi thực tế.

## 14. Các lỗi hồ sơ thường gặp

| Lỗi | Hệ quả | Cách xử lý phù hợp |
| --- | --- | --- |
| Chỉ đính kèm ảnh đăng nhập | Không thấy hành động và kết thúc | Bổ sung audit, phạm vi và bằng chứng kết thúc |
| Tạo ticket sau nhưng ghi như đã duyệt trước | Làm sai trình tự lịch sử | Giữ thời điểm thực, ghi bổ sung có nguồn |
| Dùng display name làm định danh duy nhất | Nhầm tài khoản hoặc tenant | Giữ ID ổn định và môi trường |
| Chỉ giữ log trong SIEM | Có thể mất dữ liệu khi hết thời gian lưu | Xuất và bảo quản theo chính sách đã xác định |
| Chỉ hash file ở cuối kỳ rà soát | Không chứng minh các thay đổi trước thời điểm hash | Ghi thời điểm thu thập, custody và giới hạn |
| Đồng nhất logout với mọi quyền đã hết | Có thể bỏ sót phiên, token hoặc quyền bổ sung | Kiểm tra từng loại quyền và phiên |
| Chỉ ghi “không có log” | Không biết không có sự kiện hay thiếu dữ liệu | Ghi độ bao phủ, truy vấn và tình trạng nguồn |
| Che dữ liệu trực tiếp trên bản gốc | Mất khả năng kiểm tra lại | Tạo bản dẫn xuất và ghi thao tác che |
| Đóng phát hiện khi chỉ mới giao việc | Không có bằng chứng khắc phục | Giữ mở tới khi có kết quả kiểm tra |
| Vô hiệu hóa tài khoản emergency theo thói quen | Có thể mất đường phục hồi | Áp dụng đúng mô hình tài khoản và runbook |
| Loại lần truy cập không có ticket khỏi mẫu | Bỏ sót sự kiện đáng điều tra | Đối chiếu từ log sang hồ sơ và từ hồ sơ sang log |

## 15. Thực hành xây dựng một evidence packet

Sử dụng dữ liệu giả lập, không lấy secret hay bản ghi phiên thật để làm bài tập.

Cho tình huống: một kỹ sư dùng tài khoản emergency trên máy quản trị dùng chung. Log đăng nhập có lúc 10:03:00+07:00; cuộc gọi cho người phụ trách được thuật lại là lúc 10:01; ticket được tạo lúc 10:12; SIEM nhận sự kiện lúc 10:18. Hệ thống đích ghi một thay đổi cấu hình lúc 03:05:00Z. Không có session recording vì proxy không hoạt động. Credential được thay sau xử lý, nhưng chưa có xác nhận về phiên/token còn hiệu lực.

Hãy tạo hồ sơ thể hiện:

1. Timeline giữ nguyên timestamp nguồn và có cột chuẩn hóa UTC.
2. Phân biệt cuộc gọi được thuật lại, bản ghi cuộc gọi nếu có và ticket tạo bổ sung.
3. Những bằng chứng cần thêm để quy hoạt động cho kỹ sư cụ thể trên máy dùng chung.
4. Phạm vi thay đổi, kết quả phục hồi và các nguồn có thể đối chiếu.
5. Khoảng trống session recording cùng giới hạn kết luận.
6. Việc cần làm để xác nhận không còn truy cập ngoài ý định sau thay credential.
7. Manifest và bản ghi bàn giao cho các artifact giả lập.
8. Kết luận rà soát ghi rõ điều đã chứng minh, điều chưa chứng minh và phát hiện còn mở.

Hồ sơ thực hành đạt mục tiêu khi một người khác có thể lần từ mỗi kết luận tới bằng chứng, hiểu được thứ tự sự kiện và nhìn thấy các giới hạn mà không cần hỏi lại người xử lý.

## 16. Nguyên tắc cần nhớ

Bằng chứng emergency access là chuỗi liên kết giữa nguyên nhân, thẩm quyền, danh tính, quyền, hành động và việc kết thúc. Không một artifact đơn lẻ nào thay thế được chuỗi đó.

Hãy thiết kế nguồn ghi nhận trước sự cố, thu thập theo khả năng thực tế trong sự cố và đối chiếu sau phục hồi. Giữ bản gốc, nguồn gốc thu thập, thời gian và các bước bàn giao; bảo vệ dữ liệu nhạy cảm bằng phân quyền và bản dùng cho rà soát được xử lý phù hợp.

Khi bằng chứng thiếu, ghi rõ thiếu ở đâu và ảnh hưởng tới kết luận nào. Một báo cáo nêu đúng giới hạn và giao việc khắc phục có giá trị hơn một báo cáo đánh dấu đầy đủ nhưng không thể kiểm chứng.
