# Validate access sau migration

## 1. Mục tiêu của việc xác thực truy cập

Một đợt migration Privileged Access Management (PAM) chưa hoàn tất chỉ vì vault mới đã nhận đủ tài khoản, connector báo healthy hoặc quản trị viên đăng nhập được. Điều cần chứng minh là người và workload hợp lệ vẫn thực hiện được đúng nhiệm vụ được phê duyệt, trong khi quyền dư, đường truy cập cũ và quyền đã hết hạn không còn sử dụng được.

Trong chương Migration, **validate access** là đối chiếu hành vi truy cập quan sát được sau chuyển đổi với thiết kế quyền đích đã được phê duyệt. Đối tượng cần kiểm tra không chỉ là tên role hoặc danh sách group, mà còn gồm quyền hiệu lực tại tài nguyên, điều kiện kích hoạt, credential được sử dụng, phiên đang tồn tại và bằng chứng để truy vết.

Sau bài này, bạn có thể:

- Xây dựng ma trận kiểm thử từ inventory và chính sách quyền đích.
- Kiểm tra cả hành vi được phép và hành vi phải bị từ chối.
- Xác thực luồng quản trị viên, tài khoản dịch vụ, JIT/JEA và break-glass.
- Phân biệt quyền đã thu hồi trên control plane với quyền thực tế còn dùng được.
- Lập bộ bằng chứng và tiêu chí go/no-go cho từng đợt migration.

Tình huống xuyên suốt: doanh nghiệp chuyển từ hệ thống PAM cũ sang PAM mới cho nhóm máy chủ production và một ứng dụng thanh toán. Nhóm vận hành cần SSH qua session broker, workload cần lấy credential qua cơ chế được quản lý, còn nhà cung cấp chỉ được truy cập staging trong cửa sổ bảo trì. Toàn bộ tên người, máy và mã test trong bài là ví dụ giả định.

## 2. Đừng đồng nhất cấu hình đã migrate với quyền đã đúng

### 2.1. Bốn lớp cần đối chiếu

| Lớp | Câu hỏi cần trả lời | Ví dụ bằng chứng |
|---|---|---|
| Ý định đã phê duyệt | Ai được làm gì, trên tài nguyên nào, trong điều kiện nào? | Ma trận quyền đích, change request, exception còn hiệu lực |
| Cấu hình triển khai | Mapping identity, role, group, policy và target có đúng không? | Export cấu hình đã lọc dữ liệu nhạy cảm, phiên bản policy |
| Quyền hiệu lực | Khi thực hiện hành vi, tài nguyên thực sự cho phép hay từ chối? | Kết quả probe, log xác thực và phân quyền tại target |
| Kiểm soát và bằng chứng | Truy cập có qua đúng đường, hết hạn đúng lúc và truy vết được không? | Approval, session ID, sự kiện vault, audit tại target |

Kiểm tra cấu hình là cần thiết nhưng không thay thế kiểm tra hành vi. Một role trên PAM mới có thể được giới hạn đúng, trong khi tài khoản tại target vẫn nằm trong nhóm quản trị toàn cục. Ngược lại, PAM đã phê duyệt nhưng target chưa nhận mapping mới thì người dùng vẫn không làm được việc.

### 2.2. Quyền đích không nhất thiết bằng quyền cũ

Baseline trước migration mô tả hiện trạng; thiết kế quyền đích mô tả trạng thái cần đạt. Nếu hiện trạng có quyền dư và migration đồng thời áp dụng least privilege, việc loại bỏ quyền dư là kết quả mong muốn, không phải lỗi tương thích cần phục hồi.

Vì vậy, mỗi quyền quan trọng cần có phân loại rõ:

- **Giữ tương đương:** tác vụ nghiệp vụ tiếp tục hoạt động với mức quyền tương đương đã phê duyệt.
- **Thu hẹp:** chỉ còn nhóm tài nguyên, tập lệnh hoặc khoảng thời gian cần thiết.
- **Thay thế cơ chế:** ví dụ thay mật khẩu tĩnh bằng credential có thời hạn hoặc thay đăng nhập trực tiếp bằng phiên được môi giới.
- **Loại bỏ:** tài khoản không còn owner, quyền không còn nhu cầu hoặc exception đã hết hạn.

Nếu một khác biệt chưa có quyết định, kết quả là chưa đủ điều kiện nghiệm thu. Không mặc định coi cấu hình cũ là chuẩn chỉ vì nó từng hoạt động.

### 2.3. Quyền hiệu lực phụ thuộc toàn bộ đường đi

Có thể dùng mô hình tư duy sau:

```text
Identity thực tế + nhóm/role + điều kiện truy cập
                   ↓
Quyết định của các điểm kiểm soát trên đường được chọn
                   ↓
Quyền mà target gán cho principal hoặc credential được sử dụng
                   ↓
Hành vi thực tế: ALLOW / DENY / ERROR
```

Đây không phải công thức tính quyền chung cho mọi sản phẩm. Các hệ thống có quy tắc kế thừa, explicit deny, session policy và cache khác nhau. Bài học quan trọng là phải kiểm tra đường truy cập thực tế; một policy đúng tại broker không tự bảo vệ được đường kết nối trực tiếp đang bỏ qua broker.

## 3. Chuẩn bị hợp đồng nghiệm thu trước khi chạy test

### 3.1. Chốt phạm vi của từng wave

Một wave nên có danh sách identity, workload, target, môi trường và luồng truy cập cụ thể. Ghi cả những tài nguyên chưa được migrate để người kiểm thử không kết luận nhầm rằng toàn bộ hệ thống đã đạt.

Thông tin tối thiểu cho mỗi nhóm kiểm thử:

| Thành phần | Nội dung cần có |
|---|---|
| Identity | Định danh ổn định, loại human/machine/vendor, owner |
| Target | Mã tài nguyên, môi trường, tenant hoặc miền quản trị |
| Hành vi | Đăng nhập, lấy credential, mở phiên, thực hiện tác vụ giới hạn |
| Điều kiện | MFA, approval, thiết bị, mạng, thời gian, ticket nếu áp dụng |
| Đường truy cập | Broker, API, connector, luồng trực tiếp được phép hoặc bị cấm |
| Kết quả mong đợi | ALLOW hoặc DENY, kèm điểm kiểm soát và lý do dự kiến |
| Hậu điều kiện | Không để lại quyền, token, phiên hoặc dữ liệu test ngoài dự kiến |
| Bằng chứng | Mã test, correlation ID, log nguồn, mốc thời gian |

Không ghi mật khẩu, private key, recovery code hay access token vào bảng kiểm thử. Dùng mã tham chiếu credential hoặc phiên bản secret do hệ thống cấp; nội dung bí mật không phải bằng chứng nghiệm thu cần lưu.

### 3.2. Chốt các ngưỡng thời gian

Quyền tạm thời và thu hồi thường có độ trễ lan truyền. Trước test cần thống nhất rõ:

- Thời hạn grant JIT và điểm bắt đầu tính thời hạn.
- Thời gian tối đa cho đồng bộ group, vô hiệu hóa identity hoặc thu hồi grant.
- Cách xử lý phiên đang mở và token đã phát hành.
- Độ trễ tối đa để log hoặc bản ghi phiên xuất hiện trong kho bằng chứng.
- Khoảng quan sát workload sau rotation, restart và chạy lại lịch xử lý.

Không lấy thời gian phản hồi của API thu hồi làm thời điểm quyền chắc chắn hết hiệu lực. Cũng không hợp thức hóa mọi độ trễ bằng lý do eventual consistency. Kết quả phải được so với ngưỡng đã chấp thuận cho đúng loại quyền và luồng truy cập.

### 3.3. Dùng test identity và canary có kiểm soát

Ưu tiên tài khoản kiểm thử đại diện, môi trường thử nghiệm hoặc tài nguyên canary có quyền tương đương. Trên production, chỉ thực hiện probe nằm trong phạm vi đã được phê duyệt và không gây thay đổi nghiệp vụ.

Probe cần chứng minh được hành vi đang kiểm tra. Đọc một trang dashboard không chứng minh người dùng có quyền restart dịch vụ; ngược lại, không cần restart dịch vụ production chỉ để thử quyền nếu có cơ chế kiểm tra quyền được hỗ trợ hoặc target canary tương đương.

Nếu chỉ dùng policy simulation hoặc kiểm tra cấu hình, ghi đó là bằng chứng gián tiếp. Với hành vi rủi ro cao, cần có phương án xác thực tương đương được owner chấp thuận; không gắn nhãn đã kiểm thử thực tế khi chưa thực hiện.

## 4. Xây ma trận từ principal, action, resource và context

Một test có thể mô tả bằng bộ giá trị:

```text
(principal, action, resource, context, access_path, expected_result)
```

Trong đó context chứa các điều kiện như tenant, môi trường, thiết bị, MFA, approval và thời điểm. Chỉ thay một chiều trong từng negative test giúp xác định vì sao truy cập bị từ chối.

### 4.1. Ma trận minh họa

| Test | Principal và điều kiện | Hành vi, tài nguyên | Kỳ vọng |
|---|---|---|---|
| MIG-ACC-001 | Operator A, MFA hợp lệ, JIT đã duyệt | Mở phiên qua broker đến canary production thuộc wave | ALLOW |
| MIG-ACC-002 | Operator A, chưa có JIT | Mở phiên đến cùng canary | DENY do thiếu grant hợp lệ |
| MIG-ACC-003 | Operator A, JIT chỉ cấp cho ứng dụng A | Truy cập canary thuộc ứng dụng B | DENY do ngoài scope |
| MIG-ACC-004 | Vendor V, quyền staging còn hạn | Truy cập canary production | DENY do sai môi trường |
| MIG-ACC-005 | Workload W, identity và policy hợp lệ | Lấy đúng credential tham chiếu của mình | ALLOW |
| MIG-ACC-006 | Workload W, identity hợp lệ | Lấy credential của workload khác | DENY do sai scope |
| MIG-ACC-007 | Identity đã offboard | Thiết lập truy cập mới sau thời gian thu hồi cho phép | DENY |
| MIG-ACC-008 | Operator A qua đường trực tiếp bị cấm | Kết nối đến cổng quản trị của canary | DENY tại điểm kiểm soát dự kiến |
| MIG-ACC-009 | Phiên đang mở khi grant hết hạn | Tiếp tục hành vi theo chính sách phiên đã phê duyệt | Đúng quy tắc kết thúc hoặc tái xác thực |

Bảng này là khung tham khảo, không phải tập test đủ cho mọi module. Ví dụ cần thêm trường hợp cross-tenant, tài khoản không có owner hoặc công cụ quản trị ngoài SSH nếu chúng tồn tại trong wave.

### 4.2. Negative test phải chứng minh đúng nguyên nhân

Giả sử cần kiểm tra nhà cung cấp bị cấm production. Nếu tài khoản vendor đang bị khóa ở IdP, một lần đăng nhập thất bại chưa chứng minh ranh giới staging/production hoạt động. Phải xác nhận identity hợp lệ cho control test, sau đó quan sát từ chối vì scope production.

Tương tự, kết nối timeout không mặc nhiên là kiểm thử phân quyền thành công. Timeout có thể do DNS sai, target hỏng hoặc firewall test chưa hoạt động như thiết kế. Chỉ coi chặn mạng là PASS khi đó là lớp kiểm soát được dự kiến và có bằng chứng tương ứng.

Đối với một thao tác bị cấm, **ERROR hoặc không đủ bằng chứng không được tự chuyển thành DENY**. Chúng làm kết quả kiểm thử chưa kết luận được.

## 5. Xác thực truy cập của quản trị viên

### 5.1. Identity và ánh xạ tài khoản

Đối chiếu định danh nguồn với principal thực tế tại PAM và target. Chú ý các trường hợp:

- Hai tài khoản trùng tên hiển thị nhưng thuộc miền hoặc tenant khác.
- Role mapping dựa vào group cũ chưa được loại bỏ.
- Tài khoản quản trị dùng chung làm mất khả năng quy trách nhiệm.
- Alias hoặc rename làm policy gắn nhầm người.
- Nhóm lồng nhau hoặc quyền local trên target bổ sung quyền ngoài thiết kế.

Kiểm tra tài khoản đúng không chỉ bằng tên xuất hiện trên giao diện. Dùng identifier phù hợp với hệ thống, phạm vi tenant và sự kiện target để chứng minh đúng chủ thể.

### 5.2. Đi trọn luồng truy cập được phê duyệt

Một positive test cho quản trị viên nên theo luồng hoàn chỉnh:

1. Xác thực bằng identity kiểm thử đại diện và đáp ứng điều kiện MFA/thiết bị theo chính sách.
2. Gửi yêu cầu cấp quyền có scope, thời hạn, lý do và approval cần thiết.
3. Nhận quyền tạm thời rồi thiết lập phiên qua đúng broker hoặc gateway.
4. Xác minh target và principal thực tế của phiên.
5. Thực hiện một tác vụ an toàn thuộc quyền đã cấp.
6. Kết thúc phiên, đối chiếu sự kiện và kiểm tra hậu điều kiện.

Phải ghi scope của grant và thời điểm test, vì một phiên chạy được khi grant khác còn hiệu lực có thể làm sai kết luận về grant vừa migrate.

### 5.3. Kiểm tra JEA bằng tác vụ được phép và ngoài phạm vi

Just Enough Administration (JEA) hướng tới giới hạn hành động cần thiết cho một nhiệm vụ. Nếu role chỉ cho xem trạng thái và điều khiển một dịch vụ canary, cần chứng minh ít nhất hai phía:

- Tác vụ được phép thực hiện được trên đúng dịch vụ.
- Tác vụ ngoài scope bị từ chối bởi điểm kiểm soát có thẩm quyền.

Không suy rằng ẩn một nút trên portal là đã chặn hành động. API, công cụ dòng lệnh và quyền tại target có thể vẫn cho phép. Với thao tác nhạy cảm, dùng fixture an toàn hoặc phương thức kiểm tra quyền được hỗ trợ; không chạy lệnh gây hại để tạo bằng chứng.

## 6. Xác thực JIT, hết hạn và thu hồi

### 6.1. Kiểm thử vòng đời quyền tạm thời

Để tránh chỉ kiểm tra thời điểm grant đang hoạt động, chia test thành các mốc:

```text
T0: Chưa có grant      → truy cập đặc quyền mới phải bị từ chối
T1: Grant được cấp     → chỉ scope và thời hạn đã duyệt được sử dụng
T2: Grant hết hạn      → kiểm tra truy cập mới và phiên/token đang tồn tại
T3: Thu hồi chủ động   → kiểm tra theo ngưỡng và cơ chế thu hồi đã phê duyệt
```

T2 và T3 có thể được thực hiện bằng hai grant kiểm thử riêng. Không sửa thời gian hệ thống production để giả lập hết hạn. Dùng grant ngắn hạn phù hợp hoặc môi trường thử nghiệm hỗ trợ việc kiểm soát thời gian.

### 6.2. Phân biệt các dạng quyền còn tồn tại

| Đối tượng | Điều cần xác minh sau hết hạn hoặc revoke |
|---|---|
| Grant trên PAM | Không tiếp tục cho phép phát hành truy cập mới ngoài chính sách |
| Group hoặc role tạm ở target | Membership/quyền thực tế được gỡ trong thời gian cho phép |
| Token đã phát hành | Hành vi đúng với thời hạn, introspection hoặc cơ chế revoke của hệ thống |
| Phiên đang mở | Bị chấm dứt, giới hạn hoặc tái xác thực đúng chính sách được phê duyệt |
| Credential từng checkout | Không còn dùng được sau rotation/revoke theo cơ chế đã chọn |
| Cache quyền hoặc kết nối | Không duy trì quyền vượt quá giới hạn đã chấp thuận |

Thu hồi grant không tự bảo đảm mọi loại token và phiên lập tức vô hiệu. Nếu hệ thống đích không hỗ trợ thu hồi một loại token tức thời, thiết kế phải xử lý rủi ro bằng thời hạn ngắn, kiểm soát bổ sung hoặc giới hạn phạm vi được phê duyệt. Test phải thể hiện đúng giới hạn này.

Ví dụ giả định: thiết kế yêu cầu chặn phiên mới trong 60 giây sau revoke, còn phiên broker đang hoạt động phải kết thúc trong 120 giây. Người kiểm thử đo hai kết quả riêng. API revoke trả thành công ở giây thứ 2 không đủ để kết luận đạt cả hai điều kiện.

Các con số trên chỉ minh họa cách ghi hợp đồng nghiệm thu, không phải ngưỡng mặc định cho PAM.

### 6.3. Offboarding và thay đổi chức năng

Ngoài hết hạn grant, cần kiểm tra identity bị vô hiệu hóa hoặc chuyển nhóm công việc. Một người chuyển từ vận hành production sang chỉ hỗ trợ staging không được giữ quyền production qua group phụ, quyền local hoặc credential đã nhận trước đó.

Đối với offboarding, dùng identity kiểm thử chuyên dụng. Ghi rõ thời điểm thay đổi nguồn chuẩn, thời điểm các hệ thống đồng bộ và kết quả probe tại target. Nếu còn phiên hoặc token được phép tồn tại theo chính sách, cần có giới hạn và bằng chứng xử lý tương ứng.

## 7. Xác thực workload và tài khoản dịch vụ

Luồng machine identity thường không có thao tác đăng nhập tương tác. Một màn hình portal thành công không chứng minh ứng dụng sẽ chạy được sau migration.

### 7.1. Định danh và scope

Đối với từng workload quan trọng, kiểm tra:

- Workload thực tế được nhận diện đúng trong môi trường và tenant cần thiết.
- Chỉ lấy được credential hoặc quyền thuộc phạm vi của workload đó.
- Không được đọc secret của ứng dụng khác dù biết mã tham chiếu.
- Không được sử dụng luồng tương tác đặc quyền ngoài thiết kế.
- Quyền cấp tại tài nguyên khớp tác vụ nghiệp vụ tối thiểu.

Không thêm MFA tương tác một cách máy móc cho service account. Hãy kiểm thử cơ chế xác thực workload đã được phê duyệt và các ràng buộc của cơ chế đó.

### 7.2. Rotation, kết nối sống lâu và chạy lại

Một workload có thể vẫn chạy vì connection pool đang giữ kết nối cũ, dù lần xác thực mới đã hỏng. Do đó, cần phân biệt:

| Trạng thái | Ý nghĩa kiểm thử |
|---|---|
| Kết nối đã mở trước cutover | Chứng minh tính liên tục của kết nối hiện có |
| Kết nối mới sau cutover | Chứng minh luồng xác thực mới hoạt động |
| Lấy credential sau rotation | Chứng minh workload nhận phiên bản phù hợp |
| Restart có kiểm soát | Chứng minh quá trình khởi động không còn phụ thuộc credential cũ |
| Job định kỳ chạy lại | Chứng minh luồng ít xuất hiện cũng đã được chuyển đổi |

Thực hiện restart và rotation theo change plan, trên canary hoặc thời điểm đã duyệt. Không ép đóng toàn bộ kết nối production chỉ để thu thập kết quả test.

Cần kiểm tra cả đường thành công và đường lỗi: nếu lấy credential mới thất bại, workload có vô tình quay lại secret cũ trên file cấu hình, biến môi trường hoặc kho cũ không? Nếu chính sách cấm fallback đó, việc ứng dụng vẫn chạy nhờ fallback là lỗi kiểm soát cần xử lý.

### 7.3. Credential cũ phải được xử lý theo thiết kế

Đổi địa chỉ vault không làm credential cũ tự hết hiệu lực tại target. Sau khi tất cả consumer liên quan đã chuyển đổi, việc rotation hoặc vô hiệu hóa credential cũ phải theo dependency map và kế hoạch được duyệt.

Để xác thực, dùng test credential hoặc probe trong phạm vi được phép; không đưa giá trị bí mật vào log. Bằng chứng nên ghi mã credential, phiên bản, thời điểm rotation và kết quả xác thực. Nếu credential dùng chung cho nhiều consumer, chưa xử lý hết phụ thuộc thì chưa thể kết luận đã đóng đường cũ.

## 8. Xác thực đường cũ, đường trực tiếp và fallback

Một migration có thể đạt mọi positive test trên hệ thống mới nhưng vẫn để nguyên đường truy cập ngoài kiểm soát. Các đường cần xem xét tùy inventory gồm:

- Cổng quản trị có thể kết nối trực tiếp ngoài broker.
- Tài khoản local hoặc nhóm quản trị chưa đưa vào quản lý.
- SSH key, certificate hoặc credential cũ còn hiệu lực.
- API key và token có scope rộng hơn quyền mới.
- Automation hoặc công cụ vận hành vẫn trỏ sang hệ thống cũ.
- Quyền khẩn cấp còn được dùng như quyền vận hành thường ngày.

Không phải mọi đường trực tiếp đều cần bị cấm. Có hệ thống sử dụng cơ chế truy cập trực tiếp được kiểm soát theo thiết kế. Tiêu chí là đường đó phải được định danh, có owner, có chính sách và có bằng chứng phù hợp; đường chưa được quản trị không được coi là ngoại lệ mặc định.

Với đường cũ phải đóng, cần quan sát từ vị trí mạng hoặc workload đại diện. Kiểm thử từ một máy vốn không thể tới target không chứng minh người dùng nội bộ đã mất đường bypass.

Trong giai đoạn coexistence, ghi rõ phần quyền còn trên PAM cũ, owner, thời điểm hết hiệu lực và cách theo dõi. Không gắn nhãn hoàn thành cutover cuối cùng nếu quyền cũ vẫn là quyền thường trực chưa có hạn xử lý.

## 9. Break-glass và khả năng ứng cứu

Break-glass cần được xác thực như một đường khẩn cấp có kiểm soát. Migration không được làm mất khả năng ứng cứu cần thiết, nhưng cũng không được biến break-glass thành lối bỏ qua quy trình hằng ngày.

Một buổi diễn tập phù hợp có thể xác nhận:

1. Người được chỉ định biết cách kích hoạt trong kịch bản mất một phụ thuộc đã được chọn.
2. Credential hoặc cơ chế khẩn cấp sử dụng được trên đúng target canary.
3. Hành động kích hoạt tạo cảnh báo, ghi nhận người chịu trách nhiệm và thời gian.
4. Quyền khẩn cấp chỉ có phạm vi và thời hạn được phê duyệt.
5. Sau diễn tập, credential hoặc quyền được thu hồi/rotation theo runbook.
6. Bằng chứng khẩn cấp được đối chiếu với change hoặc incident tương ứng.

Nếu cần kiểm thử khi PAM mới hoặc IdP không khả dụng, thực hiện bằng diễn tập được giới hạn. Không ngắt dịch vụ dùng chung trên production ngoài kế hoạch. Các phụ thuộc chưa được thử phải được ghi thành giới hạn phạm vi, không suy rộng kết quả từ một kịch bản sang mọi kịch bản.

## 10. Bằng chứng: chứng minh được ai, làm gì, ở đâu và vì sao

### 10.1. Chuỗi đối chiếu

Với một luồng truy cập đặc quyền, cần có khả năng nối các sự kiện:

```text
Test ID / Change ID
    → Identity xác thực
    → Request và approval nếu yêu cầu
    → Grant / credential reference
    → Session hoặc kết nối
    → Principal và hành vi tại target
    → Hết hạn / revoke / kết thúc phiên
```

Không phải mọi hệ thống có cùng một correlation ID xuyên suốt. Khi cần ghép bằng nhiều định danh, hãy ghi phương pháp đối chiếu, timestamp và scope. Tài khoản dùng chung càng cần có cầu nối đáng tin cậy từ checkout hoặc session về người thực hiện.

### 10.2. Mẫu bản ghi kết quả

Đoạn YAML dưới đây chỉ minh họa dữ liệu bằng chứng, không phải cấu hình của một sản phẩm:

```yaml
testId: MIG-ACC-003
changeId: CHG-DEMO-024
wave: production-app-a
principalRef: operator-a-test
targetRef: canary-app-b
action: open-admin-session
accessPath: pam-broker-new
policyRevision: policy-demo-17
context:
  authentication: valid
  grantScope: application-a-only
expected:
  decision: DENY
  reason: outside-approved-resource-scope
observed:
  decision: DENY
  reason: resource-scope-mismatch
  sessionCreated: false
evidenceRefs:
  - audit-event-demo-101
  - target-event-demo-202
result: PASS
```

Với mẫu negative test này, cần chứng minh target sẵn sàng và identity hợp lệ bằng control test thích hợp. Nếu sự kiện target không phát sinh vì broker đã chặn trước đó, ghi rõ điều này và dùng bằng chứng tại broker; không tạo một tham chiếu target giả để làm hồ sơ có vẻ đầy đủ.

### 10.3. Recording và log có độ trễ

Phân biệt việc thực thi kiểm soát với việc chuyển bằng chứng bất đồng bộ. Nếu chính sách yêu cầu chỉ mở phiên khi cơ chế recording sẵn sàng, kiểm thử phải chứng minh điều kiện đó. Nếu bản ghi được chuyển sang kho lưu sau khi phiên kết thúc, hãy chờ trong ngưỡng đã chấp thuận rồi xác nhận bản ghi tồn tại, có thể truy xuất và khớp phiên.

Session ID xuất hiện không đồng nghĩa recording đã được lưu đầy đủ. Nếu yêu cầu recording áp dụng mà sau ngưỡng vẫn thiếu hoặc hỏng bản ghi, test bằng chứng không đạt dù người dùng đã thao tác thành công.

### 10.4. Chất lượng và bảo mật của bằng chứng

- Dùng mốc thời gian nhất quán, lưu cả múi giờ khi trình bày cho con người.
- Ghi target, principal và policy revision để tránh nhầm giữa các lần test.
- Chỉ lưu phần log cần thiết; lọc credential và dữ liệu nghiệp vụ nhạy cảm.
- Kiểm soát quyền đọc, thời gian lưu và tính toàn vẹn theo chính sách tổ chức.
- Không coi ảnh chụp giao diện đơn lẻ là bằng chứng đủ cho toàn bộ chuỗi truy cập.

Băm một file bằng chứng giúp phát hiện file thay đổi so với bản đã ghi nhận, nhưng riêng giá trị băm không chứng minh nguồn log là thật hoặc bộ bằng chứng là đầy đủ. Cần kết hợp quyền ghi, nguồn thu thập và quy trình lưu giữ.

## 11. Phân loại kết quả và xử lý sai lệch

### 11.1. Tách quyết định truy cập khỏi kết quả test

| Quan sát | Kết quả test | Cách hiểu |
|---|---|---|
| ALLOW, đúng scope và đầy đủ hậu điều kiện/bằng chứng | PASS cho positive test | Chức năng và kiểm soát đáp ứng yêu cầu của test |
| DENY, đúng điểm kiểm soát và lý do mong đợi | PASS cho negative test | Ranh giới quyền đã được chứng minh |
| ALLOW khi dự kiến DENY | FAIL | Có quyền dư, đường bypass hoặc sai mapping cần điều tra |
| DENY khi dự kiến ALLOW | FAIL | Tác vụ hợp lệ bị gián đoạn |
| Timeout, lỗi phụ thuộc, không rõ principal | INCONCLUSIVE | Chưa chứng minh được allow/deny đúng yêu cầu |
| Chưa thể chạy vì thiếu fixture, quyền test hoặc nguồn bằng chứng | BLOCKED | Cần xử lý điều kiện chạy test |
| Không thực hiện | NOT_RUN | Chưa có bằng chứng kiểm thử |

Một kết nối được phép nhưng thiếu bằng chứng bắt buộc không phải PASS trọn vẹn. Có thể tách subtest chức năng và subtest audit, nhưng gate cuối phải xét cả hai.

### 11.2. Điều tra từ hiện tượng đến lớp kiểm soát

Khi test không đạt, lần lượt xác định:

1. Có đúng identity, target, môi trường và đường truy cập được chỉ định không?
2. Dữ liệu group/role/grant tại thời điểm test có khớp phiên bản dự kiến không?
3. Điểm nào đã cho phép hoặc chặn yêu cầu: IdP, PAM, mạng hay target?
4. Có quyền kế thừa, cache, token hoặc phiên cũ làm lệch kết quả không?
5. Bằng chứng có cùng mã phiên và khoảng thời gian không?

Không xử lý lỗi thiếu quyền bằng cách cấp administrator tạm cho cả nhóm. Sửa tối thiểu mapping hoặc policy gây sai lệch, sau đó chạy lại test thất bại và các test phủ nhận có thể bị ảnh hưởng.

Ví dụ: sửa role để operator truy cập app A có thể vô tình mở rộng app B nếu policy dùng wildcard. Vì vậy, test lại positive case của app A và negative case của app B, không chỉ lặp đúng đường vừa sửa.

## 12. Runbook nghiệm thu cho một wave

### Bước 1 — Khóa phiên bản đầu vào

Chốt ma trận quyền đích, scope wave, policy revision, dependency map, test identities, canary và ngưỡng thời gian. Ghi rõ những thay đổi hợp lệ giữa baseline cũ và thiết kế mới.

### Bước 2 — Xác nhận điều kiện chạy

Kiểm tra target và phụ thuộc sẵn sàng, đồng hồ đủ đồng bộ cho đối chiếu, nguồn log truy xuất được, owner của workload có mặt khi cần và cơ chế phục hồi đã được diễn tập ở mức phù hợp.

Nếu control test chưa hoạt động thì chưa nên dùng các thất bại tiếp theo làm bằng chứng deny.

### Bước 3 — Chạy positive test và đối chiếu principal

Thử các tác vụ nghiệp vụ đại diện qua đúng luồng mới, xác nhận principal tại target, scope thực tế và bằng chứng. Chú ý cả workload ít chạy, tác vụ định kỳ và luồng khởi động mới.

### Bước 4 — Chạy negative test theo từng ranh giới

Kiểm tra thiếu grant, sai scope, sai môi trường, sai workload, quyền ngoài tập tác vụ và đường trực tiếp bị cấm. Dùng tài nguyên an toàn để không phát sinh tác động nghiệp vụ nếu phát hiện lỗi allow.

### Bước 5 — Kiểm thử thay đổi trạng thái

Xác nhận hết hạn, revoke, offboarding, rotation và phiên tồn tại trước chuyển đổi. Đo độ trễ thực tế và so với ngưỡng đã phê duyệt thay vì chỉ chụp trạng thái control plane.

### Bước 6 — Đối soát và đóng quyền cũ

Đối soát inventory với kết quả: principal dự kiến, principal thực tế, quyền còn trên hệ thống cũ và exception. Hoàn tất việc đóng hoặc thu hồi theo change plan, rồi xác thực lại các đường quan trọng.

### Bước 7 — Chốt gate và theo dõi sau cutover

Owner nghiệp vụ xác nhận các tác vụ hợp lệ, owner kiểm soát xác nhận ranh giới quyền và người điều phối change ghi quyết định. Tiếp tục quan sát trong khoảng đã thống nhất để phát hiện job định kỳ, cache và luồng dự phòng chưa được bộc lộ.

Khoảng quan sát cần phù hợp chu kỳ hoạt động. Một giờ không có lỗi không chứng minh job chỉ chạy cuối ngày hoặc cuối tuần đã chuyển đổi thành công.

## 13. Tiêu chí go/no-go và quyền quyết định

Thiết kế gate theo rủi ro từng wave. Một bộ tiêu chí minh họa:

| Gate | Điều kiện nghiệm thu |
|---|---|
| Phạm vi | Mọi identity, workload và target trong wave có owner và trạng thái đối soát |
| Chức năng | Các positive test bắt buộc của tác vụ quan trọng đều PASS |
| Least privilege | Các negative test quan trọng đều PASS; không có unexpected ALLOW chưa xử lý |
| Vòng đời quyền | Grant, token, phiên và credential đáp ứng hợp đồng hết hạn/thu hồi |
| Đường cũ | Đã đóng theo kế hoạch hoặc có exception hợp lệ với thời hạn và owner rõ ràng |
| Bằng chứng | Chuỗi audit, recording khi yêu cầu và thời gian truy xuất đáp ứng chính sách |
| Sẵn sàng vận hành | Có runbook, cơ chế ứng cứu và người tiếp nhận sau cutover |

Không lấy tỷ lệ pass trung bình để che một lỗi nghiêm trọng. Ví dụ 99/100 test đạt nhưng test còn lại cho vendor truy cập production ngoài scope thì không thể mặc định go-live.

Cách trình bày coverage minh bạch là báo riêng tổng test bắt buộc, số PASS, FAIL, BLOCKED, INCONCLUSIVE và NOT_RUN theo loại kiểm soát. Đối với negative test bảo vệ tài nguyên nhạy cảm, cần xem từng kết quả thay vì chỉ một con số tổng.

Exception phải có phạm vi, lý do, rủi ro tồn dư, biện pháp bù, owner, người chấp nhận và thời điểm hết hiệu lực. Worker kiểm thử không tự biến một test FAIL thành PASS bằng ghi chú “đã biết”. Nếu gate cho phép chấp nhận exception, kết quả test vẫn giữ nguyên và quyết định chấp nhận được ghi riêng bởi đúng thẩm quyền.

## 14. Ví dụ phân tích một wave có kết quả chưa đạt

Wave giả định gồm ba nhóm: operator của app A, vendor staging và workload báo cáo. Kết quả ban đầu:

| Quan sát | Phân tích | Hướng xử lý và test lại |
|---|---|---|
| Operator mở phiên app A qua broker thành công | Positive path đạt về chức năng | Đối chiếu principal, grant và recording trước khi chốt đầy đủ |
| Operator còn truy cập trực tiếp bằng SSH key cũ | Ranh giới đường truy cập chưa đạt | Xử lý key/đường cũ theo kế hoạch, xác thực lại từ vị trí mạng đại diện |
| Vendor bị từ chối production nhưng cũng không vào được staging | Negative test chưa chứng minh ranh giới môi trường; identity có thể đang lỗi | Khôi phục điều kiện test hợp lệ, kiểm tra staging ALLOW rồi production DENY |
| Workload đang chạy bình thường nhưng kết nối mới thất bại | Pool cũ che lỗi xác thực sau migration | Sửa mapping/credential retrieval, kiểm thử kết nối mới và restart canary |
| Grant đã revoke nhưng role local còn tồn tại quá ngưỡng | Thu hồi control plane chưa đạt tại target | Điều tra đồng bộ và cơ chế gỡ role, đo lại thời gian thu hồi |

Trong tình huống này, số phiên thành công không đủ để mở rộng wave. Những việc cần giải quyết là quyền dư, test chưa có giá trị kết luận và phụ thuộc credential cũ.

Nếu cần phục hồi dịch vụ, dùng runbook đã phê duyệt và đánh giá credential hiện hành. Không khôi phục một credential đã bị nghi lộ hoặc tái tạo quyền rộng chỉ vì đó là trạng thái trước cutover. Rollback cũng cần xác thực quyền, bằng chứng và kế hoạch đóng các quyền tạm phát sinh.

## 15. Thực hành: thiết kế bộ test tối thiểu có ý nghĩa

Trong môi trường lab, tạo một operator test, một workload test và hai tài nguyên canary thuộc hai scope khác nhau. Thiết kế quyền đích như sau:

- Operator chỉ được vào canary A qua đường quản trị được kiểm soát khi có grant JIT.
- Workload chỉ được lấy credential tham chiếu cho canary A.
- Canary B nằm ngoài scope của cả hai.
- Credential cũ phải mất hiệu lực sau khi hoàn tất chuyển đổi và rotation theo kế hoạch.

Trước khi chạy, ghi dự kiến cho các tình huống: không có grant, grant hợp lệ, sai canary, grant hết hạn, revoke chủ động, workload lấy secret ngoài scope, kết nối mới sau rotation và đường cũ.

Với mỗi test, lưu principal thực tế, action, resource, context, thời điểm, quyết định quan sát và nguồn bằng chứng. Dùng cùng một test ID để đối chiếu các sự kiện; không lưu giá trị credential.

Bài thực hành đạt khi bạn giải thích được cả hai câu hỏi cho từng ranh giới: **vì sao tác vụ hợp lệ làm được** và **vì sao tác vụ ngoài phạm vi không làm được**. Những trường hợp chưa đủ bằng chứng phải được ghi rõ, không suy diễn từ việc không thấy lỗi trên dashboard.

## 16. Những điểm cần nhớ

Validate access sau migration là xác thực quyền đích bằng hành vi có bằng chứng. Inventory, policy và role mapping là đầu vào; kết quả tại đúng tài nguyên và đúng ngữ cảnh mới chứng minh đường truy cập hoạt động như thiết kế.

Một bộ nghiệm thu PAM cần bao phủ truy cập hợp lệ, ranh giới từ chối, vòng đời quyền, workload, đường cũ và audit. Quyền đã gỡ trên giao diện nhưng vẫn dùng được qua token, phiên hoặc credential cũ là vấn đề phải được đo và xử lý theo hợp đồng thu hồi.

Chỉ chốt wave khi các gate bắt buộc đạt hoặc có quyết định exception đúng thẩm quyền.
