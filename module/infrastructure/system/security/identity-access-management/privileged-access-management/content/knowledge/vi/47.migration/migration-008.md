# Dual-run control trong migration PAM

## 1. Dual-run giải quyết bài toán gì?

Khi thay nền tảng Privileged Access Management (PAM), tổ chức thường không thể chuyển toàn bộ tài khoản quản trị, tài khoản dịch vụ và đường truy cập trong một thời điểm. Hệ cũ vẫn phục vụ một phần công việc; hệ mới phải chứng minh rằng yêu cầu truy cập, phê duyệt, cấp quyền, kết nối, luân chuyển credential và thu hồi hoạt động đúng.

**Dual-run** là giai đoạn vận hành có giới hạn trong đó hai nền tảng cùng tồn tại theo một kế hoạch kiểm soát rõ ràng. Điểm quyết định không phải là có hai giao diện đăng nhập, mà là biết **hệ nào được thực hiện hành động nào trên từng đối tượng tại từng thời điểm**.

Ví dụ: PAM cũ vẫn phục vụ nhóm máy chủ chưa chuyển đổi, còn PAM mới phục vụ nhóm pilot. Đây là dual-run có phân vùng ownership. Ngược lại, cho cả hai hệ tự động đổi mật khẩu cùng một tài khoản quản trị không phải là một phép thử tương đương vô hại. Hai hệ có thể lần lượt ghi mật khẩu khác nhau lên target, làm credential được lưu ở một hoặc cả hai vault mất đồng bộ.

Trong bài này, “hệ cũ” và “hệ mới” chỉ vai trò trong migration, không hàm ý hệ cũ luôn kém an toàn hơn. Các ví dụ dùng môi trường giả định, không gắn với một sản phẩm cụ thể.

Sau bài học, người học cần có khả năng:

- Phân biệt chạy song song để quan sát với chạy song song có quyền tác động.
- Xác định đơn vị chuyển đổi và quyền điều khiển credential, phiên truy cập, entitlement.
- Thiết kế sổ ownership, cơ chế ngăn xung đột và tiêu chí go/no-go.
- Thực hiện cutover, xử lý trạng thái chưa xác định và rollback mà không mở lại quyền quản trị ngoài kiểm soát.
- Thu thập bằng chứng đủ để giải thích ai đã có quyền gì trong toàn bộ cửa sổ migration.

## 2. Vì sao hai PAM cùng hoạt động có thể nguy hiểm?

### 2.1. Credential là trạng thái dùng chung

Giả sử tài khoản quản trị `adm-app-01` trên máy chủ ứng dụng đang được PAM cũ quản lý. PAM mới được cấu hình lại cùng tài khoản để kiểm tra rotation:

1. Hệ cũ đặt mật khẩu mới và lưu vào vault cũ.
2. Hệ mới đặt một mật khẩu khác và lưu vào vault mới.
3. Connector của hệ cũ thử kết nối bằng credential đã lỗi thời.
4. Một lần reconcile của hệ cũ lại đặt mật khẩu khác lên target.
5. Ứng dụng hoặc người vận hành gặp lỗi xác thực, thậm chí khóa tài khoản do retry.

Cả hai job có thể từng báo thành công ở thời điểm riêng của chúng. Điều đó không chứng minh trạng thái cuối vẫn đúng. Vấn đề là có hai tác nhân ghi vào cùng một miền trạng thái mà không có cơ chế điều phối chung.

### 2.2. Quyền truy cập có thể cộng dồn

Hệ cũ cấp quyền quản trị thường trực thông qua một nhóm, còn hệ mới cấp JIT thông qua nhóm khác. Nếu chỉ kiểm tra thời hạn JIT ở hệ mới, người dùng vẫn có thể giữ quyền qua hệ cũ sau khi phiên mới kết thúc.

Tương tự, hai đường phê duyệt có thể cho phép cùng một người tự yêu cầu ở hệ A và tự phê duyệt ở hệ B do ánh xạ vai trò sai. Migration không được làm mất nguyên tắc least privilege hoặc separation of duties.

### 2.3. Một đường truy cập không được ghi hình làm hỏng kết luận

Người dùng có thể vào target qua gateway mới được ghi hình đầy đủ, nhưng cũng còn đường qua gateway cũ hoặc kết nối trực tiếp. Một báo cáo “100% phiên mới đã ghi hình” không nói gì về các phiên đi qua đường còn lại.

Vì vậy, cần đo coverage trên **tập đường truy cập dự kiến và sự kiện thực tế ở target**, không chỉ dựa vào những gì một PAM tự nhìn thấy.

### 2.4. Hai kho bằng chứng tạo ra hai nửa sự thật

Một yêu cầu được phê duyệt trên hệ cũ có thể mở phiên trên hệ mới; tài khoản dùng chung làm target chỉ thấy một username; đồng hồ lệch khiến hai sự kiện trông như diễn ra sai thứ tự. Không có định danh tương quan thì khó giải thích phiên đó thuộc ai và vì sao được cấp.

Dual-run phải bao gồm kiểm soát bằng chứng, không chỉ kiểm soát availability.

## 3. Xác định đơn vị chuyển đổi trước khi chia ownership

### 3.1. Không mặc định một máy chủ là một đơn vị độc lập

Một đối tượng chuyển đổi có thể gồm:

- Target hoặc nhóm target liên quan.
- Tài khoản quản trị, credential và các bản sao của credential.
- Cơ chế rotation/reconcile và các tài khoản có thể reset nó.
- Connector, gateway hoặc proxy dùng để truy cập.
- Quyền JIT/JEA, nhóm đặc quyền và policy phê duyệt.
- Ứng dụng, scheduler, pipeline hoặc dịch vụ tiêu thụ credential.
- Cơ chế ghi phiên, log và vị trí lưu bằng chứng.
- Đường truy cập khẩn cấp đã được kiểm thử.

Nếu hai tài khoản trên hai máy khác nhau thực chất dùng chung một secret, chuyển một máy chưa chắc đã tách được quyền ghi. Nếu một ứng dụng đọc credential từ một endpoint chung, việc đổi endpoint có thể ảnh hưởng nhiều instance cùng lúc.

**Đơn vị chuyển đổi nên bao trùm miền phụ thuộc cần được chuyển cùng nhau để giữ trạng thái nhất quán.** Khi chưa thể tách phụ thuộc, giữ cả nhóm trong cùng một ownership hoặc thiết kế một bước tách riêng trước migration.

### 3.2. Tách các loại quyền điều khiển

Một cột “owner = PAM mới” thường chưa đủ. Cần biết ownership theo từng mặt:

| Mặt điều khiển | Câu hỏi phải trả lời | Rủi ro nếu có hai bên cùng tác động |
|---|---|---|
| Credential lifecycle | Ai được tạo, đổi, reset, reconcile hoặc thay key? | Mất đồng bộ vault-target, khóa tài khoản |
| Credential release | Ai được checkout, inject hoặc trả secret qua API? | Bản sao credential tồn tại ngoài phạm vi theo dõi |
| Session admission | Ai được mở phiên mới tới target? | Bypass gateway, phiên không có phê duyệt |
| Entitlement | Ai được cấp và thu hồi nhóm, role hoặc quyền JIT? | Quyền cộng dồn, hết hạn ở một hệ nhưng còn ở hệ khác |
| Policy decision | Policy nào là chuẩn cho yêu cầu mới? | Phê duyệt không tương đương, tự phê duyệt |
| Evidence | Ai lưu yêu cầu, log, recording và ánh xạ danh tính? | Mất chuỗi truy vết qua thời điểm cutover |

Có thể cho hệ mới chỉ quan sát log trong khi hệ cũ vẫn thực thi toàn bộ. Cũng có thể để hệ cũ lưu recording của phiên đang drain nhưng không nhận phiên mới. Các cách chia này hợp lệ khi được ghi rõ, có thời hạn và đã kiểm tra khả năng thực thi.

### 3.3. Nguyên tắc một bên ghi trên mỗi miền xung đột

Một invariant thực dụng là:

> Trong mọi trạng thái vận hành ổn định, mỗi credential hoặc miền thay đổi đặc quyền có đúng một authority được phép ghi; trong cửa sổ chuyển giao có thể tạm thời không bên nào được ghi, nhưng không cho phép hai bên độc lập cùng ghi.

“Authority” ở đây là bên có khả năng thực tế thực hiện hành động, không chỉ là nhãn trong bảng theo dõi. Tắt một lịch rotation không đủ nếu job đang chạy, retry trong queue, API reconcile thủ công hoặc tài khoản reset của hệ cũ vẫn còn hoạt động.

Đối với credential được chia sẻ bởi nhiều target, invariant phải áp dụng cho cả miền chia sẻ. Đối với JIT, cần kiểm soát quyền hiệu lực sau khi hợp nhất mọi nhóm và mọi đường cấp quyền.

## 4. Chọn mô hình dual-run phù hợp

### 4.1. Shadow: hệ mới quan sát, hệ cũ thực thi

Hệ mới nhập inventory, nhận bản sao sự kiện hoặc đánh giá policy ở chế độ không thực thi. Hệ cũ tiếp tục quyết định và thực hiện truy cập.

Mục tiêu là kiểm tra ánh xạ danh tính, coverage target, phân loại quyền và chênh lệch quyết định mà chưa thay đổi credential hoặc entitlement.

Shadow không có nghĩa là cấp cho hệ mới một tài khoản reset có toàn quyền rồi “hứa không dùng”. Nếu mục tiêu chỉ là quan sát, quyền của connector mới cũng phải phản ánh phạm vi đó.

Kết quả shadow có thể chứng minh dữ liệu được thu thập và policy được diễn giải đúng. Nó **chưa chứng minh** việc inject credential, revoke JIT, rotate hoặc ghi phiên thực tế đã thành công.

### 4.2. Phân vùng theo nhóm tài nguyên

Hệ mới sở hữu đầy đủ nhóm pilot; hệ cũ sở hữu nhóm còn lại. Không có credential, connector ghi hoặc entitlement chung vượt qua ranh giới mà chưa được phân tích.

Ví dụ:

| Nhóm | Nền tảng thực thi | Rotation | Nhận phiên mới | Mục đích |
|---|---|---|---|---|
| Pilot ứng dụng A | PAM mới | PAM mới | PAM mới | Chứng minh vận hành đầu cuối |
| Máy chủ chưa chuyển | PAM cũ | PAM cũ | PAM cũ | Duy trì dịch vụ hiện tại |
| Nhóm chuẩn bị chuyển | PAM cũ | PAM cũ | PAM cũ | Hệ mới chỉ shadow |
| Nhóm vừa cutover | PAM mới | PAM mới | PAM mới | PAM cũ chỉ giữ bằng chứng/phiên drain đã chỉ định |

Đây thường là cách dễ giải thích hơn so với cho hai hệ quản lý cùng credential. Tuy nhiên, ranh giới chỉ đáng tin nếu inventory đã nhận ra account alias, shared secret và consumer chung.

### 4.3. Hai đường truy cập nhưng chỉ một đường được nhận phiên mới

Trong thời gian cutover, phiên cũ có thể còn tồn tại trên gateway cũ, còn mọi phiên mới phải đi qua gateway mới. Đây là một dạng song song có kiểm soát:

- Chặn việc tạo yêu cầu hoặc mở phiên mới trên hệ cũ.
- Giữ riêng danh sách phiên cũ được phép drain.
- Đặt hạn cuối, người chịu trách nhiệm và hành động khi phiên không tự kết thúc.
- Tiếp tục lưu recording và log của các phiên đó.
- Kiểm tra target để tìm phiên không có trong danh sách drain.

Không mặc định đổi mật khẩu sẽ đóng phiên đang tồn tại. Nhiều giao thức giữ phiên sau khi đã xác thực. Thu hồi phiên và thay credential là hai hành động khác nhau, phải kiểm thử riêng.

### 4.4. Cùng target, tài khoản riêng cho mỗi nền tảng

Mô hình này có thể phù hợp cho một pilot giới hạn nếu mỗi bên dùng tài khoản khác nhau và có thể thu hồi độc lập. Nó giảm xung đột rotation của cùng một secret nhưng **không tự giải quyết** tổng quyền hiệu lực, đường bypass hoặc khả năng cả hai tài khoản cùng sửa cấu hình target.

Cần giới hạn thời gian tồn tại tài khoản pilot, ánh xạ từng tài khoản tới người dùng thực và thu hồi tài khoản tạm khi kết thúc. Không dùng tài khoản thứ hai để lách điều kiện kiểm soát của tài khoản chính.

### 4.5. Không mặc định hỗ trợ active-active trên cùng credential

Hai sản phẩm PAM độc lập thường không chia sẻ lock, transaction hay trạng thái retry. Việc cả hai đều có chức năng rotation không tạo ra một giao thức phối hợp an toàn.

Nếu một thiết kế thực sự dùng dịch vụ quản lý credential chung với cơ chế điều phối được hỗ trợ, phải kiểm tra rõ phạm vi bảo đảm, cách ngăn stale writer và hành vi khi lỗi. Không suy ra tính an toàn từ tên tính năng hoặc từ một lần chạy thử thành công.

Trong migration thông thường, giữ một bên ghi và chuyển authority có kiểm chứng là cách thiết kế dễ kiểm soát hơn.

## 5. Sổ ownership: biến ý định thành trạng thái có thể kiểm chứng

### 5.1. Thông tin tối thiểu

Một bản ghi cho mỗi đơn vị chuyển đổi nên có:

| Trường | Ý nghĩa |
|---|---|
| Unit ID | Định danh ổn định, không phụ thuộc tên hiển thị |
| Target/account IDs | Đối tượng chính xác và alias đã đối chiếu |
| Dependency set | Consumer, shared secret, reset account và nhóm quyền liên quan |
| State | Legacy, shadow, frozen, new-owned hoặc trạng thái khác đã định nghĩa |
| Credential writer | Authority duy nhất được phép đổi/reconcile |
| Release/session owner | Bên được trả credential và nhận phiên mới |
| Entitlement owner | Bên được cấp/thu hồi quyền |
| Ownership version | Phiên bản tăng dần cho mỗi lần chuyển authority |
| Freeze/cutover window | Cửa sổ thay đổi, deadline và múi giờ |
| In-flight work | Rotation, checkout, queue, session hoặc JIT chưa kết thúc |
| Verification evidence | Kết quả thử thực thi và thử từ chối |
| Rollback trigger/owner | Điều kiện và người có quyền quyết định |
| Exception expiry | Thời hạn của ngoại lệ nếu có |

Không đưa giá trị mật khẩu, private key hoặc token vào sổ này. Chỉ lưu định danh secret và bằng chứng thao tác; dữ liệu bí mật nằm trong kho được kiểm soát.

Sổ cần có một nguồn chuẩn và lịch sử thay đổi. Hai đội giữ hai bảng riêng rồi trao đổi bằng tin nhắn dễ tạo ra khoảng trống “đội kia đã tắt rồi”.

### 5.2. Ownership version không thay thế cơ chế ngăn ghi

Giả sử unit `U-APP-07` đang ở version 12 do hệ cũ sở hữu. Cutover tạo version 13 cho hệ mới. Một job cũ mang version 12 phải bị từ chối nếu hạ tầng thực thi có hỗ trợ kiểm tra phiên bản.

Tuy nhiên, nếu connector cũ gọi trực tiếp target bằng tài khoản reset có toàn quyền và không có lớp nào kiểm tra version, số 13 trong ledger không chặn được nó. Khi đó cần cơ chế thực tế như thu hồi quyền reset của connector cũ, hạn chế đường mạng phù hợp, hủy job/queue và kiểm tra việc từ chối trên target.

Có thể dùng pseudocode sau để diễn đạt yêu cầu thiết kế:

~~~text
request = {
    unitId,
    expectedOwnershipVersion,
    actor,
    action,
    correlationId
}

current = ownershipLedger.read(unitId)

deny unless current.version == request.expectedOwnershipVersion
deny unless current.state permits request.action
deny unless current.authorityFor(request.action) == request.actor

execute through a path that enforces the same authority
record result and observed target state
~~~

Đây là mô tả logic, không phải một khóa phân tán hoàn chỉnh. Nếu kiểm tra ledger xong rồi authority thay đổi trước khi lệnh tới target, vẫn có race. Thiết kế phải ngăn job đang chạy vượt qua barrier chuyển giao, hoặc có cơ chế fencing được thực thi ở điểm có thể chặn tác động. Khi chưa chứng minh được điều đó, không cho hai writer hoạt động đồng thời.

### 5.3. Ma trận trạng thái mẫu

| Trạng thái | Hệ cũ | Hệ mới | Điều kiện ra khỏi trạng thái |
|---|---|---|---|
| LEGACY_OWNED | Thực thi theo policy hiện tại | Không tác động | Inventory và phụ thuộc đã rõ |
| SHADOW | Tiếp tục thực thi | Quan sát/đánh giá không ghi | Chênh lệch đã phân tích |
| FROZEN | Dừng thao tác mới thuộc phạm vi chuyển, thu/drain việc đang chạy | Chưa nhận authority ghi | Không còn writer cũ có thể tác động |
| NEW_OWNED | Chỉ giữ phần drain/read-only được cho phép | Nhận authority đã cấp | Kiểm thử đầu cuối và đối chứng đạt |
| STABILIZING | Không nhận việc mới | Vận hành chính, theo dõi tăng cường | Đủ chu kỳ và tiêu chí exit |
| RETIRED | Không còn quyền truy cập target | Vận hành chính | Bằng chứng được lưu theo chính sách |

Trạng thái FROZEN có thể làm gián đoạn mở phiên hoặc rotation trong một khoảng đã phê duyệt. Đây là chi phí cần cân nhắc trong thiết kế, không được che giấu bằng cách gọi là “zero downtime”.

Một unit cũng có thể vào trạng thái `HOLD_UNKNOWN` khi kết quả rotation chưa rõ hoặc không xác định writer cuối. Trong trạng thái đó, không tiếp tục chuyển giao tự động. Cần quan sát target, kiểm tra job và thực hiện reconcile có chủ đích bởi authority được xác nhận.

## 6. Chuẩn bị trước khi bật dual-run

### 6.1. Đối chiếu inventory và phụ thuộc

Với mỗi unit, xác nhận:

1. Target ID, account ID và tên đăng nhập thực tế.
2. Tài khoản cục bộ, tài khoản miền hay tài khoản trên dịch vụ quản lý tập trung.
3. Những bên có thể đổi/reset credential, bao gồm tác vụ ngoài PAM.
4. Nơi credential được tiêu thụ: ứng dụng, job định kỳ, agent, pipeline.
5. Các đường quản trị trực tiếp và đường khẩn cấp.
6. Quyền hiệu lực qua nhóm, role, sudo hoặc cơ chế ủy quyền khác.
7. Những kết nối lâu dài không cần xác thực lại sau khi credential đổi.

Nếu chưa biết consumer của một service account, không dùng rotation trên production để “thử xem cái gì bị hỏng”. Chuyển account đó vào hold, hoàn thiện discovery và kiểm thử có phạm vi trước.

### 6.2. Ánh xạ policy theo kết quả kiểm soát

Không chỉ so sánh tên policy. “Require approval” ở hai hệ có thể khác nhau về người phê duyệt, tự phê duyệt, thời hạn, ràng buộc target hoặc việc tái sử dụng approval.

Cần so sánh các kết quả mong muốn:

- Người yêu cầu được xác định qua danh tính cá nhân.
- MFA và điều kiện truy cập được áp dụng ở điểm phù hợp.
- Đúng người phê duyệt, đúng phạm vi và đúng thời hạn.
- JIT cấp đúng quyền, thu hồi đúng lúc kể cả khi phiên lỗi.
- JEA hoặc giới hạn lệnh giữ được mục tiêu kiểm soát.
- Credential được inject/checkout theo quyền đã duyệt.
- Session, command và hành vi bị từ chối được ghi lại ở mức thiết kế yêu cầu.

Chỗ nào không tương đương phải có quyết định rõ: cấu hình lại, thu hẹp pilot hoặc giữ unit ở hệ cũ. Không tự giảm yêu cầu để làm dashboard migration trông tốt hơn.

### 6.3. Kiểm thử khả năng quay lại trước khi cần dùng

Rollback có thể bị cản bởi credential đã thay, consumer đã đổi endpoint hoặc phiên mới đã tạo trạng thái nghiệp vụ. Chuẩn bị trước:

- Cấu hình và mapping cũ có thể khôi phục theo phiên bản.
- Phương án đưa credential hiện hành tới authority được chọn.
- Cách dừng rotation/reconcile của bên đang sở hữu.
- Cách chuyển consumer mà không phát tán secret qua file hoặc chat.
- Người chịu trách nhiệm xử lý phiên đang tồn tại.
- Đường khẩn cấp và bằng chứng thử truy cập.
- Điểm mà rollback không còn đơn giản và cần forward recovery.

Backup cấu hình không đồng nghĩa backup đó chứa credential còn hợp lệ. Khôi phục bản snapshot vault cũ có thể chỉ khôi phục những secret đã không còn khớp với target.

### 6.4. Đặt tiêu chí trước khi chạy

Một bộ tiêu chí cho pilot có thể bao gồm:

- Mọi account thuộc unit có owner và không có phụ thuộc chưa xác định.
- Mở phiên được phép thành công; mở phiên không được phép bị từ chối.
- Các thao tác rotation/reconcile của authority cũ bị chặn sau transfer.
- Rotation mới thành công và consumer xác thực lại bằng trạng thái hiện hành.
- JIT hết hạn làm quyền hiệu lực biến mất, không chỉ biến mất trên giao diện.
- Recording và log được truy xuất, ánh xạ được tới yêu cầu và người dùng.
- Không có sự cố nghiêm trọng chưa xử lý hoặc ngoại lệ hết hạn.
- Đường khẩn cấp được thử trong phạm vi đã phê duyệt.

Ngưỡng thời gian và số chu kỳ quan sát phụ thuộc môi trường. Một pilot ứng dụng có batch hằng tuần không thể được kết luận đầy đủ chỉ từ vài giờ dùng tương tác.

## 7. Runbook cutover cho một unit

### 7.1. Bước 1 — Xác nhận phạm vi và quyền quyết định

Người điều phối đọc lại unit, target/account IDs, dependency set, trạng thái hiện tại, version ownership và cửa sổ thay đổi. Đội PAM, đội target và chủ ứng dụng xác nhận cùng một phạm vi.

Chỉ định rõ ai có quyền go/no-go, ai vận hành connector, ai xác nhận ứng dụng và ai giữ timeline. Một hành động rollback không nên phát sinh từ hai người tự quyết độc lập trên hai hệ.

### 7.2. Bước 2 — Đặt barrier ở hệ cũ

Dừng nhận thao tác mới thuộc phạm vi chuyển:

- Yêu cầu mở phiên hoặc checkout mới.
- Rotation theo lịch, rotation khi check-in và reconcile tự động.
- Retry đang chờ hoặc job đang nằm trong queue.
- API/manual action có thể đổi credential.
- Cấp mới hoặc gia hạn entitlement/JIT thuộc unit.

Danh sách phải bám vào tính năng thực tế của hệ cũ. Tắt một nút scheduler nhưng bỏ quên hành động đổi mật khẩu khi đóng phiên sẽ để lại một writer muộn.

Chờ hoặc xử lý các thao tác đang chạy; ghi nhận trạng thái cuối. Nếu không biết một lệnh reset đã tới target hay chưa, chuyển unit sang hold để reconcile thay vì giả định nó đã bị hủy.

### 7.3. Bước 3 — Xử lý phiên, checkout và quyền còn hiệu lực

Lập danh sách phiên cũ, credential checkout và JIT chưa hết hạn. Chọn một trong các phương án đã phê duyệt:

- Drain phiên trong thời hạn.
- Kết thúc phiên tại cửa sổ thay đổi.
- Giữ một số phiên được chỉ định với owner, expiry và recording liên tục.

Với credential đã được lộ cho người dùng hoặc consumer, check-in trên giao diện không bảo đảm mọi bản sao đã biến mất. Chính sách có thể yêu cầu rotation trước hoặc sau khi chuyển authority để làm bản sao cũ mất hiệu lực; phải thực hiện theo thứ tự phù hợp với consumer và các phiên drain.

Thu hồi entitlement cũ và kiểm tra quyền hiệu lực. Một phiên cũ có thể giữ token hoặc quyền đã được nạp; cần quyết định riêng về tuổi thọ phiên đó.

### 7.4. Bước 4 — Chứng minh writer cũ đã bị ngăn

Kiểm tra các lớp ngăn phù hợp với kiến trúc:

- Job đang chạy và queue đã được xử lý.
- Connector cũ không còn quyền đổi/reset credential của unit.
- Tài khoản API hoặc operator cũ không thể chạy thao tác ngoài kế hoạch.
- Đường truy cập cũ không còn nhận phiên mới.
- Một phép thử âm có kiểm soát trả về từ chối như dự kiến.

Không thử reset thật bằng cả hai hệ trên một account production để chứng minh “hệ cũ đã tắt”. Có thể dùng account kiểm thử có cùng ràng buộc hoặc phép kiểm tra quyền an toàn phù hợp với sản phẩm, đồng thời đối chiếu chính sách thực tế trên account cần chuyển.

Bằng chứng âm cần thể hiện thao tác bị từ chối vì control đã áp dụng, không chỉ vì connector tình cờ mất mạng.

### 7.5. Bước 5 — Chuyển authority và thiết lập credential hiện hành

Cập nhật ledger theo quyết định chuyển giao, tăng ownership version và bật đúng quyền cần thiết cho hệ mới. Thực hiện onboarding credential theo kênh được kiểm soát; không đưa secret vào ticket, log thao tác hoặc tài liệu migration.

Tùy thiết kế, hệ mới có thể tiếp nhận credential hiện tại rồi rotate, hoặc thiết lập credential mới bằng cơ chế bootstrap được phê duyệt. Cần kiểm tra trạng thái target thực tế sau thao tác.

Nếu rotation thất bại giữa chừng, không tự động bật lại writer cũ. Trước hết xác định:

- Target đã nhận thay đổi chưa?
- Vault mới đã lưu trạng thái hiện hành chưa?
- Consumer nào đã chuyển, consumer nào chưa?
- Có job retry nào còn khả năng tiếp tục ghi không?

Khi chưa xác định được, giữ barrier và xử lý như một sự cố nhất quán trạng thái.

### 7.6. Bước 6 — Chuyển consumer và mở truy cập mới

Chuyển endpoint, secret reference, connector hoặc cơ chế inject theo kế hoạch đã thử nghiệm. Kiểm tra một lần xác thực mới thực sự, không chỉ tái sử dụng connection pool đã đăng nhập từ trước.

Thử đường được phép và đường bị cấm. Ví dụ, người có approval hợp lệ mở được phiên qua gateway mới; cùng người đó không mở được phiên mới qua gateway cũ hoặc trực tiếp theo đường không được phép.

Với service account, kiểm tra chức năng ứng dụng và hành vi reconnect sau rotation. Chỉ một health check dùng session còn sống có thể bỏ sót credential sai.

### 7.7. Bước 7 — Chạy chu kỳ kiểm chứng đầu cuối

Tối thiểu kiểm tra các hành vi liên quan đến unit:

1. Yêu cầu và phê duyệt.
2. Cấp quyền đúng phạm vi.
3. Mở kết nối và thực hiện thao tác kiểm thử.
4. Ghi phiên/log và ánh xạ danh tính.
5. Đóng phiên, check-in, thu hồi quyền.
6. Rotation hoặc reconcile theo thiết kế.
7. Consumer kết nối lại.
8. Truy xuất bằng chứng và đối chiếu target.

Một account tương tác không có consumer ứng dụng sẽ có bộ thử khác service account. Không ép mọi account theo một checklist kỹ thuật giống nhau, nhưng không được bỏ qua chức năng mà account thực tế sử dụng.

### 7.8. Bước 8 — Theo dõi và đóng cửa sổ

Giữ trạng thái stabilizing trong thời gian đủ đại diện. Tiếp tục tìm truy cập từ connector cũ, rotation không thuộc owner, retry kéo dài, quyền tồn dư và phiên không có correlation.

Khi exit gate đạt, thu hồi quyền cũ còn lại theo phạm vi, cập nhật inventory và runbook vận hành. Bằng chứng cũ cần được lưu hoặc di chuyển có kiểm chứng trước khi bỏ dịch vụ dùng để đọc nó.

## 8. Đo lường để phát hiện sai lệch

### 8.1. Đừng chỉ đo tỷ lệ đăng nhập thành công

Trong dual-run, đăng nhập thành công có thể là dấu hiệu của một đường bypass. Cần kết hợp chỉ số thành công, từ chối đúng và coverage.

| Chỉ số | Cách diễn giải hữu ích | Sai lầm dễ gặp |
|---|---|---|
| Account có ownership rõ | Số account đã đối chiếu owner trên tập account trong phạm vi | Mẫu số chỉ gồm account đã import |
| Writer conflict | Sự kiện ghi credential không khớp authority/version | Chỉ tìm trong log hệ mới |
| Rotation consistency | Rotation thành công và xác thực/reconnect sau đó đạt | Chỉ nhìn trạng thái job SUCCESS |
| Evidence completeness | Phiên cần ghi có yêu cầu, danh tính, target event và recording tương ứng | Có file recording nhưng không tìm được người dùng |
| Entitlement residue | Quyền hiệu lực còn sau expiry/transfer | Kiểm tra membership của một nhóm duy nhất |
| Legacy path usage | Phiên mới qua đường cũ sau cutover | Gộp phiên drain hợp lệ với truy cập mới |
| Consumer health | Chức năng ứng dụng và reconnect bằng credential hiện hành | Chỉ đo process còn chạy |
| Exception age | Ngoại lệ còn hạn và có owner | Giữ ngoại lệ vô thời hạn |

Ví dụ, với 20 phiên thuộc diện phải ghi, 19 phiên có đủ chuỗi bằng chứng thì coverage là 19/20. Không loại phiên thiếu recording khỏi mẫu số chỉ vì PAM mới không nhìn thấy nó. Cần xác định tập phiên bằng các nguồn độc lập phù hợp, như target authentication và gateway logs.

### 8.2. Chênh lệch policy cần được phân loại

Một yêu cầu được hệ cũ cho phép nhưng hệ mới từ chối có thể là:

- Sai ánh xạ role hoặc target.
- Policy mới cố ý chặt hơn và đã được phê duyệt.
- Thiếu dữ liệu về người phê duyệt.
- Khác biệt thời điểm đánh giá.
- Sự cố đồng bộ danh tính.

Không mặc định mọi khác biệt đều là lỗi, cũng không mặc định mọi từ chối đều là cải thiện an toàn. Ghi quyết định xử lý, người xác nhận và phép thử lại.

### 8.3. Cảnh báo phải gắn với hành động

Ví dụ: phát hiện thao tác reset từ connector cũ trên unit đã NEW_OWNED phải kích hoạt hold, chặn job và điều tra trạng thái credential. Một email cuối ngày không đủ cho xung đột writer đang diễn ra.

Ngưỡng pilot minh họa có thể yêu cầu không có writer conflict và không có phiên đặc quyền chưa giải thích được. Đây là điều kiện thiết kế của ví dụ, không phải một chuẩn chung áp dụng cho mọi tổ chức.

## 9. Rollback có kiểm soát và forward recovery

### 9.1. Rollback là chuyển authority lần nữa

Rollback không phải chỉ bật lại lịch rotation cũ. Nó cần một chuyển giao có barrier tương tự cutover:

1. Người có thẩm quyền xác nhận trigger và phạm vi.
2. Ngừng tác động mới từ hệ mới.
3. Kiểm kê job, retry, phiên và quyền do hệ mới tạo.
4. Xác định trạng thái credential hiện hành trên target.
5. Chọn authority phục hồi và thiết lập credential an toàn.
6. Chuyển consumer, session admission và entitlement theo kế hoạch.
7. Kiểm tra đầu cuối rồi mới phục hồi vận hành.

Ownership version vẫn tăng, chẳng hạn từ 13 lên 14 khi quay lại hệ cũ. Không đặt lại version 12 vì các job cũ có thể còn mang định danh đó. “Quay về nền tảng cũ” không có nghĩa là quay ngược lịch sử trạng thái.

### 9.2. Không khôi phục mật khẩu cũ chỉ vì có bản sao

Credential trong snapshot cũ có thể đã bị người dùng checkout, bị thu hồi hoặc không còn khớp target. Đưa nó trở lại có thể phục hồi khả năng truy cập của các bản sao đã tồn tại trước migration.

Một rollback an toàn thường cần authority phục hồi nắm credential hiện hành hoặc thiết lập một credential mới theo quy trình. Consumer phải nhận cập nhật qua kênh chuẩn, rồi xác thực lại. Cách thực hiện cụ thể phụ thuộc cơ chế target và khả năng của PAM.

### 9.3. Phân biệt mất kết nối và trạng thái chưa xác định

Nếu vault mới không trả lời nhưng target vẫn hoạt động, bật vault cũ có credential lỗi thời có thể làm sự cố nặng hơn. Nếu rotation timeout, không biết lệnh đã tới target hay chưa là một vấn đề khác với một lệnh bị từ chối trước khi thực thi.

Dùng đường phục hồi đã thử nghiệm, quan sát trạng thái target và chọn một authority xử lý. Có thể cần dừng cấp phiên mới trong một khoảng để tránh phát tán credential sai.

### 9.4. Khi forward recovery phù hợp hơn

Sau khi nhiều consumer đã đổi cơ chế xác thực hoặc tài khoản cũ đã được loại bỏ, quay lại có thể tốn thời gian và tạo thêm rủi ro. Forward recovery giữ authority ở hệ mới, khắc phục connector, mapping hoặc consumer bị lỗi.

Quyết định cần dựa trên khả năng phục hồi đã chứng minh và trạng thái hiện tại, không chỉ trên mong muốn “trở lại như trước”. Dù chọn hướng nào, không để cả hai hệ tự chạy reconcile để tranh giành trạng thái đúng.

### 9.5. Break-glass vẫn thuộc kiểm soát

Đường khẩn cấp phải có người chịu trách nhiệm, giới hạn phạm vi/thời gian và cơ chế ghi bằng chứng phù hợp. Sau khi dùng, kiểm tra lại quyền và xử lý credential theo quy trình.

Nếu cả hai PAM cùng không dùng được, một đường khẩn cấp độc lập có thể cần thiết. Nó phải được thiết kế và kiểm thử trước, không phải tạo tài khoản quản trị thường trực ngoài inventory trong lúc sự cố.

## 10. Ví dụ: chuyển một nhóm ứng dụng có service account

### 10.1. Bối cảnh

Ứng dụng A chạy trên ba instance và dùng một service account để thực hiện tác vụ nền. PAM cũ quản lý credential và API cấp secret; hệ mới sẽ tiếp quản cả rotation lẫn cấp secret.

Ngoài ra, nhóm vận hành dùng tài khoản quản trị riêng để mở phiên qua gateway. Hai luồng này được lập thành hai unit nếu phụ thuộc cho phép:

- Unit dịch vụ: service account, ba consumer, job nền và cơ chế rotation.
- Unit quản trị: tài khoản quản trị, gateway, approval, JIT và recording.

Không mặc định chuyển gateway là đã chuyển service account. Hai unit có tiêu chí kiểm thử khác nhau.

### 10.2. Giai đoạn shadow

Hệ mới nhập metadata account và nhận log phù hợp; chưa được đổi credential. Đội ứng dụng xác nhận mọi consumer, bao gồm một job chỉ chạy cuối tuần.

Phát hiện này thay đổi thời gian quan sát: kiểm thử tương tác trong ngày không đủ chứng minh job cuối tuần dùng được secret sau rotation. Có thể tạo lần chạy kiểm thử đại diện trong cửa sổ đã phê duyệt thay vì chờ mù.

### 10.3. Cutover unit dịch vụ

Runbook giả định:

1. Đặt freeze trên rotation, reconcile và credential release cũ cho unit.
2. Hoàn tất hoặc hủy có xác minh những job đang chạy.
3. Chứng minh connector cũ không còn khả năng reset account.
4. Tăng version ownership, cấp authority cho hệ mới.
5. Thiết lập credential hiện hành và cập nhật secret reference của ba consumer.
6. Buộc từng consumer thực hiện xác thực mới theo cách kiểm thử an toàn.
7. Chạy rotation mới và kiểm tra reconnect của cả ba instance.
8. Chạy tác vụ nền đại diện và truy xuất log tương quan.

Nếu bước 6 chỉ đạt ở hai instance, chưa được đánh dấu unit hoàn tất. Một connection pool cũ còn sống ở instance thứ ba có thể che giấu cấu hình sai.

### 10.4. Tình huống lỗi

Sau rotation, instance thứ ba không reconnect được. Điều tra thấy nó còn trỏ API cũ, trong khi API cũ đã bị chặn release theo kế hoạch.

Phản ứng phù hợp là giữ writer cũ bị chặn, sửa secret reference của instance thứ ba theo authority hiện tại và kiểm tra lại. Nếu không thể phục hồi trong cửa sổ, kích hoạt quyết định rollback/forward recovery đã quy định.

Phản ứng không phù hợp là cho API cũ trả secret trở lại rồi bật rotation cũ để “cứu một instance”. Hành động này có thể tạo hai nguồn credential và làm hỏng hai instance đang chạy tốt.

### 10.5. Bằng chứng cần giữ

Hồ sơ của unit gồm ownership trước/sau, chứng cứ chặn writer cũ, kết quả rotation, xác thực mới ở ba consumer, kết quả job nền, timeline lỗi và quyết định xử lý.

Với unit quản trị, bổ sung yêu cầu/phê duyệt, phiên qua gateway mới, phép thử từ chối đường cũ, JIT expiry và recording. Không đưa password hay secret response vào hồ sơ.

## 11. Bài tập thực hành: kiểm tra các invariant

Thực hiện trong môi trường lab với account và target có thể phục hồi. Mục tiêu là chứng minh control, không phải tạo xung đột credential trên production.

### 11.1. Dựng phạm vi tối thiểu

Chuẩn bị hai nền tảng hoặc hai bộ điều khiển mô phỏng, một target, một account tương tác và một consumer dịch vụ. Lập ledger và định nghĩa rõ writer, session owner, entitlement owner.

Nếu dùng mô phỏng, ghi rõ giới hạn: kiểm thử logic ownership không chứng minh connector thực của sản phẩm đã thực thi fencing.

### 11.2. Kịch bản và kết quả mong đợi

| Kịch bản | Kết quả mong đợi |
|---|---|
| Hệ mới ở SHADOW gửi yêu cầu rotate | Bị từ chối; target không đổi |
| Job cũ còn trong queue khi bắt đầu freeze | Được phát hiện và xử lý trước transfer |
| Hệ cũ cố nhận phiên mới sau cutover | Bị từ chối bởi control đã thiết kế |
| Một phiên cũ đang drain | Có owner, deadline và bằng chứng liên tục |
| Hệ mới rotate thành công | Target và vault nhất quán; consumer xác thực mới thành công |
| JIT ở hệ mới hết hạn | Quyền hiệu lực được thu hồi, kể cả đường cấp quyền cũ |
| Rotation trả timeout | Unit vào hold cho đến khi xác định trạng thái thực |
| Connector cũ kết nối lại sau một khoảng mất mạng | Không thể ghi theo ownership đã hết hiệu lực |
| Thực hiện rollback | Chỉ authority phục hồi được ghi; version tăng |
| Truy xuất một phiên bất kỳ | Tìm được người yêu cầu, approval, target và recording tương ứng |

### 11.3. Câu hỏi phân tích

- Một cờ `rotationDisabled=true` có đủ chứng minh writer cũ đã bị ngăn không? Hãy liệt kê các đường ghi còn lại.
- Nếu hai PAM dùng tài khoản khác nhau trên cùng target, tổng quyền và khả năng bypass còn cần kiểm tra ở đâu?
- Tại sao job rotation SUCCESS nhưng consumer vẫn lỗi có thể là một thất bại của cutover?
- Khi kết quả reset chưa xác định, dữ liệu nào giúp chọn reconcile, rollback hoặc forward recovery?
- Một phiên drain được chấp nhận cần khác phiên mới trái phép ở những bằng chứng nào?
- Vì sao ledger cần tăng version ngay cả khi authority quay lại hệ cũ?

Bài làm tốt phải chỉ ra được điểm thực thi control và bằng chứng kiểm tra. Chỉ nêu “có quy trình” hoặc “đã thông báo đội vận hành” chưa chứng minh invariant được giữ.

## 12. Điều kiện kết thúc dual-run

Dual-run chỉ nên kết thúc khi các unit trong phạm vi đạt exit gate và không còn đường thực thi cũ chưa giải thích được:

- Ownership, credential writer và entitlement owner đã thống nhất trên nguồn chuẩn.
- Các chu kỳ truy cập, rotation, reconnect và thu hồi đại diện đã chạy thành công.
- Quyền và đường truy cập cũ đã thu hồi hoặc được giữ như ngoại lệ có owner và expiry.
- Những phiên drain đã kết thúc, credential checkout cũ được xử lý theo chính sách.
- Không còn consumer phụ thuộc endpoint cũ ngoài phạm vi được chấp nhận.
- Log, recording và ánh xạ danh tính trước/sau cutover truy xuất được.
- Alerting, runbook, trực vận hành và quy trình sự cố đã chuyển cho đội chịu trách nhiệm.
- Kế hoạch rollback đã được đóng hoặc thay bằng quy trình phục hồi vận hành chính thức.

Không giữ dual-run vô thời hạn chỉ vì cả hai hệ “đều đang chạy ổn”. Càng kéo dài, càng khó biết nền tảng nào là chuẩn và các ngoại lệ có thể trở thành quyền thường trực.

Giá trị cốt lõi của dual-run control là chuyển giao quyền điều khiển đặc quyền theo từng unit với bằng chứng rõ ràng: **một authority ghi tại một thời điểm, đường truy cập được kiểm soát, quyền được thu hồi và trạng thái thực tế được xác minh sau mỗi lần chuyển**.
