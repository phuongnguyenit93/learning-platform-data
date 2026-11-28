# Account deletion

## 1. Xóa tài khoản trong IAM có nghĩa gì?

**Account deletion** là quy trình chấm dứt một tài khoản trong phạm vi đã xác định, thu hồi khả năng truy cập và xử lý các dữ liệu gắn với tài khoản theo chính sách áp dụng. Trong một hệ thống IAM phân tán, đây thường là một quy trình nhiều bước, không phải một lệnh xóa một hàng trong bảng `users`.

Một người dùng có thể có danh tính tại IdP, tài khoản trong nhiều ứng dụng, membership tại nhiều tenant, các phiên đang hoạt động, refresh token, API key, credential MFA và dữ liệu đã được đồng bộ qua provisioning. Xóa bản ghi tại một nơi không tự làm các thành phần còn lại biến mất hoặc ngừng chấp nhận quyền truy cập.

Ví dụ, cổng học đã xóa profile của người dùng nhưng API vẫn chấp nhận access token chưa hết hạn. Nếu luồng SSO cho phép tạo tài khoản tự động, lần đăng nhập sau còn có thể tái tạo profile vừa bị xóa. Giao diện báo “đã xóa” trong khi vòng đời truy cập và dữ liệu chưa thật sự được xử lý.

Một quy trình tốt phải trả lời được bốn câu hỏi:

1. Đang xóa tài khoản, membership hay toàn bộ danh tính nào?
2. Quyền truy cập bị chặn từ khi nào và ở những điểm nào?
3. Dữ liệu nào bị xóa, dữ liệu nào được giữ có giới hạn và vì mục đích gì?
4. Bằng chứng nào xác nhận các hệ thống liên quan đã thực hiện đúng?

## 2. Phân biệt xóa với các thao tác vòng đời khác

| Thao tác | Mục tiêu chính | Điều không được mặc định suy ra |
| --- | --- | --- |
| Khóa hoặc vô hiệu hóa | Ngăn một tài khoản tiếp tục truy cập | Dữ liệu hồ sơ và credential đã bị xóa |
| Gỡ membership | Chấm dứt quan hệ với một tenant, nhóm hoặc tổ chức | Danh tính toàn cục cũng phải bị xóa |
| Thu hồi quyền | Loại bỏ role, entitlement hoặc khả năng thực hiện hành động | Phiên và mọi token đã mất hiệu lực ngay lập tức |
| Soft delete | Đánh dấu tài khoản không còn hoạt động trong dữ liệu ứng dụng | Dữ liệu không còn tồn tại hoặc không thể truy cập qua đường khác |
| Hard delete | Loại bỏ bản ghi khỏi kho đang xử lý | Cache, log, replica, backup và ứng dụng khác cũng đã được xử lý |
| Giả danh hóa | Thay dữ liệu định danh bằng tham chiếu ít trực tiếp hơn | Không còn khả năng liên kết hay nhận diện người dùng |
| Xóa tài khoản theo quy trình | Phối hợp chấm dứt truy cập và xử lý dữ liệu trong phạm vi rõ ràng | Mọi dữ liệu ở mọi bên ngoài phạm vi đều đã bị xóa |

Soft delete có thể là một bước kỹ thuật hữu ích để chống race condition hoặc hỗ trợ một giai đoạn phục hồi đã thiết kế. Tuy nhiên, cờ `deleted=true` không tự đáp ứng mục tiêu loại bỏ dữ liệu nếu ứng dụng vẫn giữ toàn bộ hồ sơ và cho phép truy vấn qua báo cáo, công cụ hỗ trợ hoặc endpoint quản trị.

Tương tự, thay email bằng chuỗi ngẫu nhiên nhưng giữ nguyên lịch sử có thể truy ngược không làm dữ liệu tự động trở thành ẩn danh. Cần đánh giá khả năng liên kết và phạm vi xử lý thực tế.

## 3. Xác định đúng đối tượng và phạm vi

### 3.1. Tài khoản ứng dụng khác với danh tính tại IdP

Một ứng dụng thường chỉ có quyền quản lý tài khoản cục bộ của mình. Xóa tài khoản ở cổng học không đồng nghĩa ứng dụng được phép xóa người dùng khỏi IdP doanh nghiệp hoặc khỏi các ứng dụng khác.

Trong SSO, có thể giữ danh tính tại IdP nhưng chặn việc truy cập một ứng dụng cụ thể. Ngược lại, xóa người dùng tại IdP chưa chắc đã xóa tài khoản cục bộ, phiên ứng dụng hoặc dữ liệu được đồng bộ từ trước.

Cần xác định nguồn quản trị vòng đời: người dùng tự yêu cầu, quản trị viên được phân quyền, quy trình nhân sự, nguồn provisioning hay một dịch vụ quản lý danh tính trung tâm. Mỗi nguồn có quyền và phạm vi khác nhau.

### 3.2. Danh tính toàn cục khác với membership của tenant

Một người dùng có thể thuộc tenant A và tenant B. Quản trị viên tenant A thường chỉ được xử lý membership và dữ liệu trong tenant A theo quyền được cấp. Không suy rộng quyền đó thành quyền xóa danh tính hoặc dữ liệu tại tenant B.

```text
Danh tính người dùng
  ├─ membership tenant A → tài nguyên và quyền của A
  └─ membership tenant B → tài nguyên và quyền của B

Gỡ membership A không tự đồng nghĩa xóa danh tính dùng chung.
```

Mô hình dữ liệu và API phải biểu diễn sự khác nhau này. Một endpoint tên chung chung như “delete user” dễ gây nhầm nếu phía sau vừa có thao tác gỡ membership vừa có thao tác xóa toàn bộ subject.

### 3.3. Dùng định danh ổn định và có namespace

Định vị mục tiêu bằng tài khoản nội bộ đã liên kết với nguồn danh tính phù hợp, chẳng hạn cặp issuer/subject đã xác minh cùng phạm vi tenant nếu mô hình yêu cầu. Không chỉ dựa vào email, tên hiển thị hoặc số điện thoại do người yêu cầu gửi lên.

Email có thể đổi hoặc được tái cấp. Nếu yêu cầu xóa cũ được xử lý chậm sau khi email đã thuộc người khác, tìm mục tiêu theo email có thể làm xóa nhầm tài khoản. Job xóa cần giữ tham chiếu đến đúng thế hệ tài khoản và đúng mapping đã xác minh.

## 4. Tiếp nhận yêu cầu và xác minh thẩm quyền

### 4.1. Xác thực người yêu cầu chưa đủ

Đăng nhập thành công chỉ xác định chủ thể đang yêu cầu. Hệ thống còn phải kiểm tra người đó có quyền xóa đúng đối tượng trong đúng phạm vi hay không.

Một luồng tự xóa tài khoản cần xác nhận ý định của chủ tài khoản và mức độ tin cậy phù hợp cho thao tác có tác động lớn. Có thể yêu cầu xác thực lại hoặc step-up theo chính sách. Một session đang tồn tại không phải lúc nào cũng đủ bằng chứng nếu phiên đã lâu hoặc có tín hiệu rủi ro.

Luồng quản trị phải kiểm tra quyền xóa, ranh giới tenant, giới hạn đối tượng và yêu cầu phê duyệt nếu có. Không cho phép người có quyền hỗ trợ xem hồ sơ tự động thực hiện xóa tài khoản hoặc xóa bằng chứng kiểm toán.

### 4.2. Bảo vệ thao tác thay đổi trạng thái

Yêu cầu xóa không nên được kích hoạt bằng một liên kết GET có tác dụng phụ. Với giao diện dùng cookie, cần bảo vệ theo thiết kế chống CSRF và xác nhận ý định phù hợp. Với API, kiểm tra credential, quyền, đối tượng và phạm vi ở phía máy chủ.

Không nhận một `user_id` từ client rồi xóa trực tiếp mà không kiểm tra quan hệ với người yêu cầu. Không dùng liên kết khôi phục hoặc email xác nhận không còn hiệu lực như quyền xóa vô thời hạn.

### 4.3. Nêu rõ hệ quả và phạm vi trước khi bắt đầu

Thông tin xác nhận cần phân biệt: chặn truy cập ngay, xóa dữ liệu đang hoạt động, xử lý hệ thống liên quan và dữ liệu được giữ có giới hạn. Nếu có khoảng thời gian cho phép hủy trước khi xóa không thể đảo ngược, cần định nghĩa rõ điều kiện và cách xác thực yêu cầu hủy.

Không hứa “xóa ngay toàn bộ mọi dữ liệu” nếu hệ thống thực tế còn phải xử lý bất đồng bộ hoặc có dữ liệu giữ lại theo chính sách. Phạm vi hoàn thành phải có thể kiểm chứng bằng trạng thái kỹ thuật và thông tin được cung cấp cho người yêu cầu.

## 5. Kiểm kê những gì gắn với tài khoản

Một deletion plan nên xác định ít nhất các nhóm sau:

| Nhóm | Ví dụ | Hướng xử lý cần xác định |
| --- | --- | --- |
| Trạng thái truy cập | Account status, membership, role, entitlement | Chặn truy cập và ngăn cấp lại ngoài ý muốn |
| Phiên và grant | Session cục bộ, refresh token, quyền ủy quyền đã cấp | Chấm dứt hoặc thu hồi trong phạm vi được quản lý |
| Credential cá nhân | Password hash, public key đăng ký cho passkey, MFA seed, recovery code, API key | Xóa hoặc vô hiệu hóa khả năng sử dụng theo thiết kế |
| Hồ sơ | Tên, email, điện thoại, ảnh, thuộc tính tổ chức | Xóa hoặc giữ tối thiểu theo mục đích còn hiệu lực |
| Mapping tích hợp | Liên kết subject, provisioning ID, tài khoản downstream | Xử lý đúng mục tiêu và chống tái tạo ngoài ý muốn |
| Tài nguyên sở hữu | Nhóm, nội dung, tác vụ tự động, tài nguyên của tổ chức | Chuyển quyền sở hữu hoặc xử lý theo quy tắc nghiệp vụ |
| Dữ liệu vận hành | Cache, chỉ mục tìm kiếm, hàng đợi, bản xuất, ticket | Loại bỏ hoặc hạn chế bản sao theo phạm vi và vòng đời |
| Audit và lưu trữ | Sự kiện bảo mật, backup, bản ghi có yêu cầu giữ | Giữ có giới hạn, kiểm soát truy cập và lịch xử lý rõ ràng |

Quyền sở hữu tài nguyên không đồng nghĩa tài nguyên thuộc riêng cá nhân. Xóa một người quản trị không được kéo theo xóa toàn bộ nhóm, service account hoặc khóa dùng chung của tổ chức nếu không có quyết định riêng về những đối tượng đó.

Đối với workload do người dùng tạo, cần xác định chủ sở hữu mới, vòng đời credential và phụ thuộc nghiệp vụ. Đừng để thao tác xóa người dùng làm mất khả năng quản lý một workload vẫn đang chạy, nhưng cũng không giữ credential cá nhân hoạt động chỉ để tránh xử lý việc chuyển giao.

## 6. Chặn truy cập trước khi dọn dữ liệu

### 6.1. Đặt trạng thái vòng đời có hiệu lực tại điểm kiểm soát

Sau khi yêu cầu và phạm vi đã được xác minh, hệ thống cần chặn đăng nhập, tạo phiên mới, cấp token hoặc cấp lại quyền cho mục tiêu theo thiết kế. Chỉ ẩn tài khoản khỏi danh sách quản trị không tạo ra hiệu lực bảo mật.

Các đường truy cập cần kiểm tra trạng thái vòng đời hoặc nhận được cơ chế thu hồi tương ứng. Nếu chỉ một ứng dụng nhìn thấy trạng thái `deleting`, những ứng dụng khác có thể vẫn tiếp tục hoạt động bằng bản sao cũ.

### 6.2. Phiên, token và credential có cơ chế khác nhau

| Thành phần | Việc cần làm | Giới hạn cần biết |
| --- | --- | --- |
| Session phía máy chủ | Hủy session hoặc tăng phiên bản trạng thái để session cũ bị từ chối | Chỉ xóa cookie trong một trình duyệt không chặn mọi session khác |
| Refresh token | Thu hồi token/grant hoặc family liên quan theo thiết kế | Cần xét các client và thiết bị có quyền riêng |
| Access token tự chứa | Áp dụng kiểm tra trạng thái, cơ chế thu hồi được hỗ trợ hoặc thời hạn hiệu lực đã thiết kế | Xóa account không tự làm chữ ký token trở nên không hợp lệ |
| API key cá nhân | Vô hiệu hóa key và xử lý cache xác minh | Các bản sao key ở client không biến mất nhưng phải không dùng được |
| Passkey/MFA đã đăng ký | Gỡ credential hoặc vô hiệu hóa liên kết ở bên xác minh | Xóa đăng ký phía máy chủ không đồng nghĩa xóa được khóa riêng khỏi mọi thiết bị |
| Phiên tại IdP và ứng dụng khác | Phối hợp theo giao thức và quyền quản trị thực tế | Logout ở một RP không tự bảo đảm chấm dứt mọi phiên SSO khác |

Không xoay khóa ký dùng chung của cả hệ thống chỉ để xử lý một tài khoản nếu thiết kế không yêu cầu điều đó; thao tác có thể ảnh hưởng đến mọi người dùng. Cơ chế thu hồi nên phù hợp với phạm vi subject và credential cụ thể.

Nếu API chỉ xác minh JWT ngoại tuyến và không kiểm tra trạng thái nào khác, token đã phát hành có thể tiếp tục được chấp nhận đến khi hết hiệu lực. Đội thiết kế phải biết và xử lý khoảng thời gian này; không báo “truy cập đã bị thu hồi tức thời” khi chưa có cơ chế bảo đảm tương ứng.

### 6.3. Kiểm soát tác vụ đang chạy

Một request, tác vụ batch hoặc consumer có thể đã đọc quyền trước khi tài khoản bị chặn. Với hành động nhạy cảm, cần xác định điểm kiểm tra lại trạng thái hoặc quyền trước bước cam kết có tác động. Không giả định việc hủy session tự dừng mọi công việc đã được đưa vào hàng đợi.

Cũng cần xử lý request tạo credential, liên kết IdP hoặc cập nhật hồ sơ chạy đồng thời. Trạng thái vòng đời và cơ chế đồng bộ phải ngăn chúng tạo thêm khả năng truy cập sau khi tài khoản đã bước vào giai đoạn chặn.

## 7. Điều phối xóa như một quy trình có trạng thái

### 7.1. Trạng thái phải có tiêu chí chuyển rõ ràng

Một mô hình minh họa:

```text
REQUESTED
  → VERIFIED
  → ACCESS_BLOCKED
  → PROPAGATING
  → ACTIVE_SCOPE_VERIFIED
  → RETENTION_PENDING, nếu còn dữ liệu giữ có thời hạn
  → FINALIZED, khi đã đạt toàn bộ điều kiện kết thúc đã công bố
```

`REQUESTED` chỉ ghi nhận ý định; không được xóa dữ liệu trước khi xác minh đối tượng và thẩm quyền. `ACCESS_BLOCKED` xác nhận quyền truy cập đã được chặn trong phạm vi cam kết. `ACTIVE_SCOPE_VERIFIED` xác nhận các hệ thống đang hoạt động trong kế hoạch đã được kiểm tra, không đồng nghĩa mọi backup lịch sử đã hết vòng đời.

`FINALIZED` cần bám theo một định nghĩa cụ thể của sản phẩm. Nếu sản phẩm dùng “hoàn tất” cho phạm vi dữ liệu đang hoạt động, phải công bố riêng trạng thái lưu giữ và lịch xử lý bản sao. Không dùng một nhãn `deleted` duy nhất để che cả lỗi connector, dữ liệu đang chờ và dữ liệu giữ lại có chủ đích.

Các trạng thái lỗi hoặc cần rà soát phải có người chịu trách nhiệm, nguyên nhân và đường tiếp tục. Việc một bước thất bại không nên tự làm tài khoản trở lại `active` hoặc mở lại credential đã thu hồi.

### 7.2. Một job, nhiều kết quả đích

Mỗi hệ thống đích cần trạng thái riêng, chẳng hạn:

```text
PENDING
IN_PROGRESS
DELETED_VERIFIED
RETAINED_BY_POLICY
FAILED_RETRYABLE
REVIEW_REQUIRED
```

`RETAINED_BY_POLICY` cần kèm loại dữ liệu, mục đích giữ, người chịu trách nhiệm và mốc xem xét hoặc hết hạn nếu áp dụng. Nó không được dùng làm nhãn mặc định cho những connector chưa hỗ trợ xóa.

Một đích `FAILED_RETRYABLE` vẫn là công việc chưa hoàn tất. Gửi yêu cầu thành công, nhận thông báo “accepted” hoặc đưa sự kiện vào queue chưa chứng minh hệ thống đích đã xử lý dữ liệu. Cần xác minh trạng thái cuối cùng bằng cơ chế đáng tin cậy của tích hợp.

### 7.3. Độ bền và tính lặp lại an toàn

Job xóa nên có định danh ổn định, tham chiếu mục tiêu, phạm vi, phiên bản kế hoạch và bằng chứng xác minh. Retry cùng job không được tạo một yêu cầu xóa rộng hơn hoặc chuyển sang tài khoản mới chỉ vì email hiện tại đã thay đổi.

Các bước phải có khả năng chạy lại an toàn: nếu đúng tài khoản đã được xác minh là không còn tồn tại ở đích, bước có thể được coi là đạt kết quả mong muốn. Tuy nhiên, không coi mọi `404` là bằng chứng đã xóa; cần biết request đang trỏ đúng hệ thống, đúng namespace, đúng đối tượng và có đủ quyền kiểm tra.

Nếu cập nhật trạng thái cục bộ và gửi sự kiện là hai thao tác riêng biệt, có thể xảy ra tình huống đã chặn tài khoản nhưng không có sự kiện downstream. Một thiết kế như transactional outbox giúp lưu trạng thái cùng ý định gửi trong một giao dịch cục bộ, sau đó phát lại có kiểm soát. Consumer vẫn cần xử lý trùng và thứ tự sự kiện.

## 8. Ngăn tài khoản bị tạo lại ngoài ý muốn

### 8.1. JIT và provisioning có thể đảo ngược kết quả xóa

Luồng Just-in-Time provisioning có thể tạo profile khi người dùng đăng nhập qua IdP. Đồng bộ thư mục hoặc connector provisioning có thể xem tài khoản bị thiếu là cần tạo lại. Nếu các luồng này không hiểu trạng thái xóa, chúng sẽ tái tạo dữ liệu hoặc quyền sau khi cleanup.

Cần xác định quy tắc chặn tạo lại theo đúng nguồn và phạm vi: một membership đã xóa ở tenant A, hay một subject đã được chấm dứt trên toàn bộ miền quản lý. Không dùng một lệnh cấm toàn cục nếu yêu cầu chỉ xử lý một ứng dụng.

### 8.2. Tombstone và deletion ledger

Một hệ thống có thể giữ dấu vết tối thiểu cho biết một mục tiêu đã bị chấm dứt, nhằm từ chối sự kiện cũ và ngăn tái tạo ngoài ý muốn. Dấu vết thường gọi là **tombstone**; deletion ledger theo dõi công việc và bằng chứng của quá trình xóa.

Các bản ghi này cũng có thể là dữ liệu liên kết đến một cá nhân. Chỉ giữ định danh và metadata thật sự cần cho mục đích chống tái tạo, kiểm toán hoặc điều phối; giới hạn quyền truy cập và vòng đời. Không giữ nguyên hồ sơ cá nhân trong tombstone rồi cho rằng đã hoàn thành tối thiểu hóa dữ liệu.

Nếu dùng phép băm hay tham chiếu để đối chiếu, phải xét khả năng đoán, liên kết, quản lý khóa và việc thay đổi định danh. Băm email không tự giải quyết tính ổn định hoặc tính riêng tư của cơ chế chống tái tạo.

### 8.3. Sự kiện đến muộn và tài khoản mới

Consumer nên kiểm tra trạng thái vòng đời, phiên bản hoặc thế hệ tài khoản trước khi áp dụng một cập nhật cũ. Một sự kiện “thêm vào group” được phát trước khi xóa nhưng đến sau không được khôi phục quyền cho subject đã bị chặn.

Nếu sản phẩm cho phép người dùng đăng ký lại, cần tạo vòng đời mới theo chính sách và tránh tái gắn quyền, dữ liệu hoặc lịch sử của tài khoản cũ chỉ vì trùng email. Việc khôi phục hoặc liên kết lại cần một luồng có thẩm quyền và bằng chứng phù hợp, không phải tác dụng phụ của đăng nhập SSO.

## 9. Xử lý dữ liệu lưu giữ, log và backup

### 9.1. Giữ lại phải có phạm vi và mục đích

Một số bản ghi có thể cần giữ để kiểm toán, điều tra sự cố hoặc đáp ứng nhu cầu lưu trữ đã xác định. Đây là quyết định theo chính sách và điều kiện áp dụng của tổ chức; không có một thời hạn duy nhất đúng cho mọi loại tài khoản và dữ liệu.

Hệ thống cần phân loại rõ dữ liệu bị xóa, dữ liệu được giảm bớt định danh, dữ liệu bị hạn chế sử dụng và dữ liệu tiếp tục được giữ cho mục đích cụ thể. Không lấy lý do giữ audit để giữ toàn bộ profile, token và dữ liệu phân tích không liên quan.

Nếu có yêu cầu tạm giữ một phần dữ liệu, cần tách nó khỏi quyền truy cập của tài khoản. Tài khoản vẫn có thể bị chấm dứt truy cập trong khi một tập bằng chứng được bảo vệ riêng. Trạng thái job phải thể hiện điều này thay vì tuyên bố đã xóa toàn bộ hoặc âm thầm mở lại truy cập.

### 9.2. Log cũng nằm trong vòng đời dữ liệu

Không ghi raw token, mật khẩu, MFA secret hoặc toàn bộ hồ sơ vào job và log xóa. Bằng chứng thực thi có thể dùng job ID, tham chiếu mục tiêu, hệ thống đích, hành động, kết quả, thời gian và mã tham chiếu xác minh cần thiết.

Tham chiếu giả danh và lịch sử thao tác vẫn có thể liên kết với một người. Audit cần được phân quyền và lưu trong khoảng thời gian đã xác định, không được xem là dữ liệu không còn cần bảo vệ.

### 9.3. Backup không tự biến mất khi xóa dữ liệu đang hoạt động

Một backup bất biến có thể còn chứa dữ liệu tài khoản đến hết vòng đời của bản sao đó. Kế hoạch xóa cần biết lịch hết hạn, quyền truy cập và cách ngăn dữ liệu cũ quay lại sử dụng nếu phải phục hồi.

```text
Phục hồi snapshot trong môi trường cách ly
  → nạp trạng thái xóa và ledger đủ mới từ nguồn được bảo vệ
  → áp dụng lại chặn truy cập và xử lý mục tiêu đã xóa
  → xác minh các điều kiện trước khi mở dịch vụ phục hồi
```

Nếu cả dữ liệu tài khoản và ledger đều bị khôi phục về cùng một snapshot cũ, hệ thống có thể quên những yêu cầu xóa xảy ra sau snapshot. Thiết kế phục hồi phải bảo đảm tiếp cận được trạng thái xóa đủ mới, thay vì chỉ dựa vào bản ghi nằm trong chính backup đang phục hồi.

Không mở lưu lượng người dùng trước rồi mới tìm cách áp dụng lại các lệnh xóa. Một khoảng truy cập ngắn sau phục hồi cũng có thể làm phiên, token hoặc dữ liệu downstream được tạo lại.

### 9.4. Xóa khóa mã hóa có điều kiện áp dụng

Với thiết kế mã hóa phù hợp, loại bỏ một khóa riêng cho tập dữ liệu có thể làm bản mã không còn giải mã được. Tuy nhiên, cần chứng minh phạm vi khóa, các bản sao khóa, bản rõ, cache và các đường phục hồi đều đã được xử lý.

Không xóa một khóa dùng chung cho nhiều người dùng để xử lý một tài khoản. Cũng không coi crypto-erasure là đã xóa mọi metadata, chỉ mục hoặc bản xuất không được mã hóa bằng chính khóa đó. Cơ chế này là một phần của thiết kế lưu trữ, không phải cách thay thế mọi bước kiểm kê và xác minh.

## 10. Ví dụ hợp đồng sự kiện và theo dõi công việc

Một sự kiện nội bộ minh họa:

```json
{
  "event_type": "account_deletion_requested",
  "job_id": "delete-job-example-41",
  "target_ref": "subject-internal-42",
  "target_generation": 3,
  "scope": "application_account",
  "application": "learning-portal",
  "plan_version": "deletion-plan-v2",
  "requested_at": "2026-01-15T08:30:00Z"
}
```

Đây là cấu trúc minh họa, không phải schema chuẩn của một giao thức. Việc có `target_ref` trong sự kiện không chứng minh nguồn gửi được phép yêu cầu xóa. Consumer phải chỉ nhận từ nguồn được tin cậy, kiểm tra phạm vi và xử lý đúng phiên bản hợp đồng.

Sự kiện không chứa email hoặc hồ sơ để mọi consumer tự tìm kiếm mục tiêu. Mapping từ tham chiếu nội bộ sang tài khoản đích cần được quản lý ở đúng thành phần tích hợp. Cũng không chuyển credential người dùng trong event để connector “đăng nhập hộ” rồi xóa.

Một bảng theo dõi đơn giản có thể là:

| Hệ thống | Trạng thái | Bằng chứng cần có |
| --- | --- | --- |
| IAM ứng dụng | `DELETED_VERIFIED` | Tài khoản bị chặn, credential thuộc phạm vi không còn dùng được |
| Kho session | `DELETED_VERIFIED` | Các phiên của tài khoản đã bị hủy hoặc bị từ chối |
| Ứng dụng downstream | `PENDING` | Chưa có kết quả cuối cùng; cần tiếp tục điều phối |
| Chỉ mục tìm kiếm | `DELETED_VERIFIED` | Dữ liệu mục tiêu không còn xuất hiện qua truy vấn được phép kiểm tra |
| Audit | `RETAINED_BY_POLICY` | Mục đích, tập trường và lịch lưu giữ rõ ràng |
| Backup | `RETAINED_BY_POLICY` | Vòng đời bản sao và cơ chế áp dụng lại xóa khi phục hồi |

Trong ví dụ này, không được báo hoàn tất phạm vi dữ liệu đang hoạt động khi downstream vẫn `PENDING`. Các dòng giữ lại cũng phải là kết quả của phân loại chính sách, không phải cách che lỗi kỹ thuật chưa xử lý.

## 11. Tình huống minh họa: xóa tài khoản ở một cổng học SSO

Một người dùng yêu cầu xóa tài khoản cổng học, trong khi danh tính tại IdP doanh nghiệp còn được dùng cho các công cụ khác. Phạm vi được xác nhận là tài khoản ứng dụng và dữ liệu thuộc cổng học, không phải danh tính tại IdP hay toàn bộ tổ chức.

Sau xác minh, cổng học đặt trạng thái ngăn truy cập, hủy session và thu hồi các grant/credential do chính ứng dụng quản lý. API kiểm tra hiệu lực truy cập theo thiết kế để không tiếp tục chấp nhận người dùng chỉ vì access token còn hợp lệ về chữ ký.

Quy trình xóa xử lý profile, membership trong cổng học, dữ liệu cá nhân thuộc phạm vi và các bản sao tại chỉ mục/cache. Nội dung thuộc tổ chức được chuyển quyền sở hữu theo quy tắc đã xác định; không xóa cả nhóm học hoặc tài nguyên của người khác.

Connector thông báo ban đầu gặp lỗi tạm thời. Job vẫn giữ trạng thái đang điều phối, retry có kiểm soát và phát cảnh báo nếu quá giới hạn vận hành. Người dùng nhận trạng thái cho biết truy cập đã chấm dứt nhưng một phần xử lý dữ liệu đang chờ, thay vì thông báo sai rằng mọi hệ thống đã xóa xong.

Sau khi downstream xác nhận, quy trình kiểm tra lại các đích. Một tombstone tối thiểu ngăn luồng SSO/JIT tự tạo lại tài khoản cũ trong phạm vi cổng học. Audit và backup được xử lý theo chính sách giữ và phục hồi đã công bố; chúng không được dùng cho mục đích hồ sơ hoạt động thông thường.

Nếu sau này người dùng được phép đăng ký lại, hệ thống sử dụng luồng vòng đời mới. Không tự phục hồi quyền cũ hoặc gắn lại tiến độ nhạy cảm chỉ vì IdP trả cùng địa chỉ email.

## 12. Kiểm chứng kết quả theo từng lớp

| Tình huống cần kiểm tra | Kết quả mong muốn |
| --- | --- |
| Người không có quyền gửi yêu cầu xóa | Bị từ chối; mục tiêu không đổi trạng thái |
| Quản trị viên tenant A nhắm tài khoản ở tenant B | Bị chặn theo ranh giới quản trị |
| Người dùng dùng lại session cũ | Không tiếp tục truy cập trong phạm vi đã chặn |
| Refresh token hoặc API key cá nhân cũ được sử dụng | Bị từ chối theo cơ chế thu hồi đã thiết kế |
| Một request tạo credential chạy đồng thời với xóa | Không tạo khả năng truy cập mới sau điểm chặn |
| Gửi lặp cùng job | Không xóa nhầm đối tượng mới, không mở rộng phạm vi |
| Downstream không sẵn sàng | Giữ trạng thái chưa hoàn tất và có đường retry/điều tra |
| Callback SSO hoặc sự kiện provisioning cũ đến sau | Không tái tạo tài khoản/quyền ngoài ý muốn |
| Phục hồi backup trước thời điểm xóa | Áp dụng lại trạng thái xóa trước khi mở dịch vụ |
| Xóa một tài khoản sở hữu tài nguyên dùng chung | Tài nguyên được xử lý theo kế hoạch, không lan sang người khác |

Kiểm chứng không nên chỉ kiểm tra “không tìm thấy hàng trong bảng users”. Cần kiểm tra khả năng truy cập, hiệu lực credential, dữ liệu downstream, đường tái tạo và trạng thái dữ liệu giữ lại. Kết quả không xác định phải được nêu rõ và tiếp tục xử lý, không chuyển thành thành công theo mặc định.

## 13. Những sai lầm thường gặp

- Coi vô hiệu hóa tài khoản hoặc soft delete là đã xóa mọi dữ liệu.
- Xóa theo email mà không xác minh đúng tài khoản, namespace và phạm vi.
- Chỉ hủy cookie ở trình duyệt hiện tại, bỏ qua session và refresh token khác.
- Cho rằng access token tự chứa mất hiệu lực ngay khi hàng tài khoản bị xóa.
- Xóa danh tính toàn cục khi yêu cầu chỉ gỡ membership hoặc tài khoản ứng dụng.
- Cascade xóa tài nguyên dùng chung, service account hoặc khóa của cả tổ chức.
- Đánh dấu hoàn tất ngay khi gửi sự kiện hoặc nhận phản hồi chấp nhận xử lý.
- Để JIT/provisioning tạo lại tài khoản từ lần đăng nhập hoặc sự kiện cũ.
- Giữ hồ sơ đầy đủ trong tombstone và gọi đó là dữ liệu đã xóa.
- Bỏ quên cache, chỉ mục, hàng đợi, bản xuất và vòng đời backup.
- Phục hồi snapshot cũ rồi mở dịch vụ trước khi áp dụng lại trạng thái xóa.
- Giữ dữ liệu vô thời hạn mà không chỉ rõ mục đích, phạm vi và người chịu trách nhiệm.

Xóa tài khoản trong IAM là việc phối hợp vòng đời truy cập với vòng đời dữ liệu. Phạm vi đúng, chặn truy cập có hiệu lực, điều phối có trạng thái và bằng chứng xác minh giúp hệ thống chấm dứt tài khoản mà không làm dữ liệu hoặc quyền cũ quay lại ngoài ý muốn.
